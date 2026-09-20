"""Versioned parameter assets and recoverable active sets; never auto-delete source meshes."""
import copy,hashlib,json,os,re,uuid,time
from pathlib import Path
from contextlib import contextmanager
import numpy as np
import bpy
from mathutils import Vector
from . import blender_ops as ops,quality,depth_order

SCHEMA='sword06c.production.v1'
def _bytes(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def _hash(value):return hashlib.sha256(_bytes(value)).hexdigest()
def _id(value):
    value=str(value).strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}',value) or '..' in value:raise ValueError('Part ID: use 1..80 letters, digits, _, . or -; no path segments.')
    return value
def _atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.tmp-'+uuid.uuid4().hex)
    try:
        with tmp.open('wb') as file:file.write(data);file.flush();os.fsync(file.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()

@contextmanager
def _lock(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);file=(root/'.production.lock').open('a+b')
    file.seek(0,2)
    if file.tell()==0:file.write(b'0');file.flush()
    file.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(file.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:file.close();raise ValueError('Another operation holds this project; retry after it completes.')
    try:yield
    finally:
        file.seek(0)
        if os.name=='nt':msvcrt.locking(file.fileno(),msvcrt.LK_UNLCK,1)
        else:fcntl.flock(file.fileno(),fcntl.LOCK_UN)
        file.close()

def manifest(root):
    path=Path(root)/'active.json'
    if not path.exists():return {'schema':SCHEMA,'project_id':uuid.uuid5(uuid.NAMESPACE_URL,str(Path(root).resolve())).hex,'sequence':0,'parts':{},'depth_order':[]}
    m=json.loads(path.read_text(encoding='utf-8'))
    if m.get('schema')!=SCHEMA:raise ValueError('Unsupported active manifest.')
    for part in m['parts']:_id(part)
    return m

def _asset(root,entry):
    root=Path(root).resolve();path=(root/entry['path']).resolve()
    if not path.is_relative_to(root):raise ValueError('Revision asset escapes its project directory.')
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Revision checksum failed: '+entry['path'])
    return json.loads(data)

def _geometry(context,obj):
    v,faces=ops.evaluated_geometry(context,obj)
    f=np.array([(p[0],p[i],p[i+1]) for p in faces for i in range(1,len(p)-1)],int)
    return v,f

def _mesh_hash(v,f):return _hash({'vertices':np.asarray(v).tolist(),'triangles':np.asarray(f).tolist()})

def _qa(context,obj):
    v,f=_geometry(context,obj);region=obj.data.attributes.get('s06c_face_region')
    tags=[int(x.value) for x in region.data] if region and len(region.data)==len(f) else None
    return quality.analyze(v,f,tags),_mesh_hash(v,f)

def _reconstructable(obj,profile):
    unsupported=[m.name for m in obj.modifiers if (m.show_viewport or m.show_render) and m.type not in ('SURFACE_DEFORM','LATTICE')]
    if unsupported:raise ValueError('These enabled modifiers are not serialized yet: '+', '.join(unsupported))
    if obj.data.shape_keys:raise ValueError('Shape keys are not serialized by this parameter format.')
    for mod in obj.modifiers:
        if getattr(mod,'vertex_group',''):raise ValueError('Weighted vertex groups are not serialized; use full-part guides or explicit profile controls.')
        target=mod.target if mod.type=='SURFACE_DEFORM' else mod.object if mod.type=='LATTICE' else None
        if target and not target.get('s06c_owned_guide'):raise ValueError('Use owned surface/lattice guides so the saved part can be rebuilt.')
    # Detect direct vertex edits: silently storing only the old parameters would lose work.
    me,_=ops.generate_mesh(profile,'TRESSIR_RECONSTRUCTABILITY_CHECK')
    try:
        a=np.array([tuple(v.co) for v in me.vertices]);b=np.array([tuple(v.co) for v in obj.data.vertices])
        fa=[tuple(p.vertices) for p in me.polygons];fb=[tuple(p.vertices) for p in obj.data.polygons]
        if a.shape!=b.shape or fa!=fb or not np.allclose(a,b,atol=2e-8,rtol=0):raise ValueError('The base mesh differs from its parameters. Save the mesh separately, or express the edit through the profile/guide before accepting.')
    finally:bpy.data.meshes.remove(me)

def _tree(obj):
    result={obj}
    if obj.parent and obj.get('s06c_handle')==obj.parent.name:result.add(obj.parent)
    for m in obj.modifiers:
        g=m.target if m.type=='SURFACE_DEFORM' else m.object if m.type=='LATTICE' else None
        if g and g.get('s06c_owned_guide'):result.add(g)
    return result

def _collection(context,label,project_id,scene=None):
    scene=scene or context.scene
    name='TRESSIR_'+label+'_'+project_id[:8];col=bpy.data.collections.get(name)
    if not col:col=bpy.data.collections.new(name)
    if col.name not in scene.collection.children:scene.collection.children.link(col)
    return col

def _status(context,obj,state,project_id):
    home=bpy.data.scenes.get(obj.get('s06c_home_scene','')) or context.scene
    col=_collection(context,'ACTIVE' if state=='active' else 'ARCHIVE',project_id,home)
    for item in _tree(obj):
        if item.name not in col.objects:col.objects.link(item)
        for old in list(item.users_collection):
            managed=old.name.endswith(project_id[:8]) and old.name.startswith(('TRESSIR_ACTIVE_','TRESSIR_ARCHIVE_','S06C_ACTIVE_','S06C_ARCHIVE_'))
            if old!=col and (old==home.collection or managed):old.objects.unlink(item)
        item['s06c_project_id']=project_id
        # Native guide meshes remain excluded from render while still editable.
        item.hide_render=state!='active' or bool(item.get('s06c_owned_guide'))
        for scene in bpy.data.scenes:
            if item.name in scene.objects:
                for layer in scene.view_layers:
                    if item.name in layer.objects:item.hide_set(state!='active',view_layer=layer)
    obj['s06c_lifecycle']=state

def _check_order(context,objects,constraints):
    result=[]
    for rule in constraints:
        front,back=rule['front'],rule['back']
        if front not in objects or back not in objects:
            result.append({'rule':rule,'status':'pending_missing_part','violations':0});continue
        world=[]
        for obj in (objects[front],objects[back]):
            v,f=_geometry(context,obj);v=np.array([tuple(obj.matrix_world@Vector(x)) for x in v]);world.append((v,f))
        options={k:rule[k] for k in ('axis','front_sign','gap_m','resolution','bounds_2d_m') if k in rule}
        check=depth_order.compare(*world[0],*world[1],**options);check['rule']=rule;result.append(check)
    return result

def set_depth_order(root,rules):
    for rule in rules:
        _id(rule['front']);_id(rule['back'])
        if rule['front']==rule['back']:raise ValueError('A part cannot occlude itself.')
    with _lock(root):
        m=manifest(root);m['depth_order']=copy.deepcopy(rules);m['sequence']+=1;_atomic(Path(root)/'active.json',_bytes(m))
    return m

def build_candidate(context,profile,part_id,root=None,preview=True):
    part_id=_id(part_id);p=copy.deepcopy(profile);p['part_id']=part_id
    m=manifest(root) if root is not None else None
    obj=ops.create_object(context,p,'TRESSIR_CANDIDATE_'+part_id)
    obj['s06c_home_scene']=context.scene.name
    obj['s06c_part_id']=part_id;obj['s06c_lifecycle']='candidate';obj['s06c_instance_id']=uuid.uuid4().hex
    if root is not None:
        obj['s06c_project_id']=m['project_id'];context.scene['s06c_production_root']=str(Path(root).resolve())
        context.scene.s06c_project_dir=str(Path(root).resolve())
        if preview:
            for old in list(bpy.data.objects):
                if old!=obj and old.get('s06c_project_id')==m['project_id'] and old.get('s06c_part_id')==part_id and ops.PROFILE_KEY in old:
                    for item in _tree(old):
                        item.hide_render=True
                        if item.name in context.view_layer.objects:item.hide_set(True)
                    if old.get('s06c_lifecycle')=='candidate':_status(context,old,'archived',m['project_id'])
    return obj

def accept(context,obj,root,part_id=None,checkpoint=True):
    if not obj:raise ValueError('Select a parameterized candidate.')
    root=Path(root).resolve();part_id=_id(part_id or obj.get('s06c_part_id',''))
    # Read guide state without changing the canonical text until commit succeeds.
    p=copy.deepcopy(ops.get_profile(obj));p['matrix_world']=[list(r) for r in obj.matrix_world];p['deformers']=ops.current_deformers(obj);p['part_id']=part_id
    _reconstructable(obj,p);report,mesh_hash=_qa(context,obj)
    if report['blocking']:raise ValueError('Candidate failed mesh validity: '+', '.join(report['blocking']))
    # Rebuild the serialized representation before committing it. This catches
    # unsupported modifier/guide edits that a base-mesh comparison cannot see.
    verification=build_candidate(context,p,part_id)
    try:
        rebuilt_report,rebuilt_hash=_qa(context,verification)
        if rebuilt_report['blocking'] or rebuilt_hash!=mesh_hash:raise ValueError('The serialized parameters/guides do not reproduce the evaluated mesh; candidate was not accepted.')
    finally:discard_candidate(context,verification)
    with _lock(root):
        m=manifest(root);objects={o.get('s06c_part_id'):o for o in bpy.data.objects if o.get('s06c_project_id')==m['project_id'] and o.get('s06c_lifecycle')=='active'}
        # Unloaded active parts are restored temporarily for depth checks only if needed.
        missing={r[k] for r in m['depth_order'] for k in ('front','back') if r[k] in m['parts'] and r[k] not in objects and r[k]!=part_id}
        if missing:raise ValueError('Restore the active set before acceptance so its depth constraints can be checked: '+', '.join(sorted(missing)))
        objects[part_id]=obj;orders=_check_order(context,objects,m['depth_order'])
        if any(r['violations'] for r in orders):raise ValueError('Candidate violates a declared depth order; run Check depth order for details.')
        p.setdefault('history',[]).append({'operation':'accepted','part_id':part_id,'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
        payload={'schema':'sword06c.revision.v1','profile':p,'quality':report,'depth_order_checks':orders,'evaluated_mesh_sha256':mesh_hash,'generator_version':[4,0,0]}
        data=_bytes(payload);digest=hashlib.sha256(data).hexdigest();rel='revisions/'+part_id+'/'+digest+'.json'
        _atomic(root/rel,data)
        next_m=copy.deepcopy(m);next_m['parts'][part_id]={'path':rel,'sha256':digest,'revision':digest,'object_name':obj.name};next_m['sequence']+=1
        # The manifest switches only after the complete immutable asset is durable.
        _atomic(root/'active.json',_bytes(next_m))
    for old in list(bpy.data.objects):
        if old!=obj and old.get('s06c_project_id')==m['project_id'] and old.get('s06c_part_id')==part_id:_status(context,old,'archived',m['project_id'])
    obj['s06c_part_id']=part_id;obj['s06c_revision']=digest;_status(context,obj,'active',m['project_id']);ops.set_profile(obj,p)
    context.scene['s06c_production_root']=str(root)
    context.scene.s06c_project_dir=str(root)
    result={'part_id':part_id,'revision':digest,'manifest':str(root/'active.json'),'quality':report,'depth_order':orders,'checkpoint':None}
    if checkpoint:
        path=root/'checkpoints'/('stage-'+str(next_m['sequence'])+'-'+uuid.uuid4().hex[:8]+'.blend');path.parent.mkdir(exist_ok=True)
        try:
            bpy.ops.wm.save_as_mainfile(filepath=str(path),copy=True,check_existing=False);result['checkpoint']=str(path)
        except Exception as e:result['checkpoint_error']=str(e)
    return result

def check_depth_order(context,root):
    m=manifest(root);objects={o.get('s06c_part_id'):o for o in bpy.data.objects if o.get('s06c_project_id')==m['project_id'] and o.get('s06c_lifecycle')=='active'}
    return _check_order(context,objects,m['depth_order'])

def restore(context,root):
    root=Path(root).resolve();m=manifest(root);staged=[];chosen={};assets={}
    # Validate every checksum before touching the scene.
    for part,entry in m['parts'].items():assets[part]=_asset(root,entry)
    try:
        for part,payload in assets.items():
            entry=m['parts'][part]
            existing=[o for o in bpy.data.objects if o.get('s06c_project_id')==m['project_id'] and o.get('s06c_part_id')==part and o.get('s06c_revision')==entry['revision'] and o.name in context.scene.objects]
            match=None
            for candidate in existing:
                # An unsaved guide edit is archived, never silently mistaken for the saved revision.
                _,digest=_qa(context,candidate)
                if digest==payload['evaluated_mesh_sha256'] and np.allclose(candidate.matrix_world,payload['profile']['matrix_world'],atol=1e-8):match=candidate;break
            if match is None:
                match=build_candidate(context,payload['profile'],part);staged.append(match)
                q,digest=_qa(context,match)
                if q['blocking'] or digest!=payload['evaluated_mesh_sha256']:raise ValueError('Rebuild differs from accepted geometry: '+part)
            chosen[part]=match
        orders=_check_order(context,chosen,m['depth_order'])
        if any(x['violations'] for x in orders):raise ValueError('The saved active set violates its current depth-order rules.')
    except Exception:
        for obj in staged:discard_candidate(context,obj)
        raise
    for obj in list(bpy.data.objects):
        if obj.get('s06c_project_id')==m['project_id'] and ops.PROFILE_KEY in obj and obj not in chosen.values():_status(context,obj,'archived',m['project_id'])
    for part,obj in chosen.items():
        obj['s06c_part_id']=part;obj['s06c_revision']=m['parts'][part]['revision'];_status(context,obj,'active',m['project_id'])
    context.scene['s06c_production_root']=str(root)
    context.scene.s06c_project_dir=str(root)
    return {'restored_parts':len(chosen),'new_objects':len(staged),'objects':{k:v.name for k,v in chosen.items()},'depth_order':orders}

def discard_candidate(context,obj):
    if obj.get('s06c_lifecycle') not in ('candidate','archived'):raise ValueError('Only an explicit candidate/archive can be discarded; active/source objects are protected.')
    project_id=obj.get('s06c_project_id');part_id=obj.get('s06c_part_id');tree=_tree(obj)
    for item in list(tree):
        if item==obj:continue
        shared=any((m.type=='SURFACE_DEFORM' and m.target==item) or (m.type=='LATTICE' and m.object==item) for other in bpy.data.objects if other not in tree for m in other.modifiers)
        if shared or any(child not in tree for child in item.children):tree.remove(item)
    tx=bpy.data.texts.get(obj.get(ops.PROFILE_KEY,''));data=[o.data for o in tree if o.data]
    for item in tree:bpy.data.objects.remove(item,do_unlink=True)
    if tx and not any(o.get(ops.PROFILE_KEY)==tx.name for o in bpy.data.objects):bpy.data.texts.remove(tx)
    for item in data:
        if item.users==0:
            if isinstance(item,bpy.types.Mesh):bpy.data.meshes.remove(item)
            elif isinstance(item,bpy.types.Lattice):bpy.data.lattices.remove(item)
    if project_id:
        candidates=[o for o in bpy.data.objects if o.get('s06c_project_id')==project_id and o.get('s06c_part_id')==part_id and o.get('s06c_lifecycle')=='candidate']
        if not candidates:
            for old in list(bpy.data.objects):
                if old.get('s06c_project_id')==project_id and old.get('s06c_part_id')==part_id and old.get('s06c_lifecycle')=='active':_status(context,old,'active',project_id)
