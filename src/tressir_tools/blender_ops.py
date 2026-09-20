import copy,json,math
from pathlib import Path
import numpy as np
import bpy
from mathutils import Matrix
from . import clump,sheet,sheet_v4,fields,quality

PROFILE_KEY='s06c_profile_text'

def get_profile(obj):
    if not obj or PROFILE_KEY not in obj:raise ValueError('Select a parameterized hair object; untracked meshes cannot be saved as design parameters.')
    tx=bpy.data.texts.get(obj[PROFILE_KEY])
    if not tx:raise ValueError('The embedded profile text is missing.')
    return json.loads(tx.as_string())

def set_profile(obj,profile):
    tx=bpy.data.texts.get(obj.get(PROFILE_KEY,'')) or bpy.data.texts.new(obj.name+'_profile.json')
    tx.use_fake_user=True
    tx.clear();tx.write(json.dumps(profile,ensure_ascii=False,indent=2));obj[PROFILE_KEY]=tx.name
    obj['schema']=profile['schema'];obj['s06c_kind']='clump' if profile['schema']==clump.SCHEMA else 'sheet'
    obj['provenance']=json.dumps(profile.get('history',[]),ensure_ascii=False)
    for old in ('section_ratio','side_revision'):
        if old in obj:del obj[old]

def generate_mesh(profile,name):
    special=None
    if profile['schema']==clump.SCHEMA:v,f,uv=clump.build_mesh(profile)
    elif profile['schema']==sheet.SCHEMA:v,f,uv,special=sheet.build_mesh(profile)
    elif profile['schema']==sheet_v4.SCHEMA:v,f,uv,special=sheet_v4.build_mesh(profile)
    else:raise ValueError('Unsupported profile schema.')
    check=clump.mesh_checks(v,f)
    if not check['closed_edges'] or check['degenerate_triangles'] or check['volume_m3']<=0:raise ValueError('Geometry validation failed: '+str(check))
    me=bpy.data.meshes.new(name);me.from_pydata(v.tolist(),[],f.tolist());me.update()
    if me.validate():bpy.data.meshes.remove(me);raise ValueError('Blender had to repair the generated topology.')
    for poly in me.polygons:poly.use_smooth=True
    if special:
        for poly in me.polygons:
            if poly.index>=special['smooth_faces']:poly.use_smooth=False
        sharp=me.attributes.new('sharp_edge','BOOLEAN','EDGE')
        for edge in me.edges:sharp.data[edge.index].value=tuple(sorted(edge.vertices)) in special['sharp_edges']
        if 'regions' in special:
            region=me.attributes.new('s06c_face_region','INT','FACE')
            region.data.foreach_set('value',special['regions'])
            check['quality']=special['quality']
    layer=me.uv_layers.new(name='TressIR_ParametricUV')
    for poly,coords in zip(me.polygons,uv):
        for li,co in zip(poly.loop_indices,coords):layer.data[li].uv=co
    return me,check

def create_object(context,profile,name=None,restore=True):
    p=copy.deepcopy(profile);name=name or p.get('name','TressIR_LegacyHair')
    if p['schema']==sheet_v4.SCHEMA:p=sheet_v4.upgrade(p)
    transform=np.asarray(p.get('matrix_world',np.eye(4)),float)
    if transform.shape!=(4,4) or not np.isfinite(transform).all() or abs(np.linalg.det(transform))<1e-12:raise ValueError('The part needs a finite, invertible 4x4 placement matrix.')
    # Place the transform handle at the clump root, including legacy world-like meshes.
    if p['schema']==clump.SCHEMA:
        pivot=np.asarray(p.get('root_cap_m',p['base_samples'][0]['center_m']),float)
        if np.linalg.norm(pivot)>1e-10:
            shift=Matrix.Translation(pivot)
            p['matrix_world']=[list(r) for r in Matrix(p.get('matrix_world',np.eye(4).tolist()))@shift]
            for row in p['base_samples']:row['center_m']=(np.asarray(row['center_m'])-pivot).tolist()
            p['tip_m']=(np.asarray(p['tip_m'])-pivot).tolist();p['root_cap_m']=[0.,0.,0.]
            for state in p.get('deformers',[]):state['matrix_relative_to_part']=[list(r) for r in shift.inverted()@Matrix(state['matrix_relative_to_part'])]
            p.setdefault('history',[]).append({'operation':'rebase-origin-to-root','preserves_world_geometry':True})
    me,check=generate_mesh(p,name+'_Mesh')
    root=bpy.data.objects.new(name+'_HANDLE',None);context.scene.collection.objects.link(root)
    root.matrix_world=Matrix(p.get('matrix_world',np.eye(4).tolist()));root.empty_display_type='PLAIN_AXES';root.empty_display_size=.012
    obj=bpy.data.objects.new(name,me);context.scene.collection.objects.link(obj);obj.parent=root
    obj.matrix_basis=Matrix.Identity(4);obj.color=(.10,.58,.77,1);obj['s06c_handle']=root.name
    set_profile(obj,p);obj['s06c_last_geometry_check']=json.dumps(check)
    context.view_layer.update()
    if restore:
        try:restore_deformers(context,obj,p.get('deformers',[]))
        except Exception:
            tx=bpy.data.texts.get(obj.get(PROFILE_KEY,''));guides=[o for o in bpy.data.objects if o.get('s06c_owned_guide') and o.get('s06c_owner')==obj.name]
            bpy.data.objects.remove(obj,do_unlink=True)
            for guide in guides:
                data=guide.data;bpy.data.objects.remove(guide,do_unlink=True)
                if data.users==0:
                    if isinstance(data,bpy.types.Mesh):bpy.data.meshes.remove(data)
                    elif isinstance(data,bpy.types.Lattice):bpy.data.lattices.remove(data)
            bpy.data.objects.remove(root,do_unlink=True)
            if me.users==0:bpy.data.meshes.remove(me)
            if tx:bpy.data.texts.remove(tx)
            raise
    return obj

def current_deformers(obj):
    result=[]
    for mod in obj.modifiers:
        if mod.type=='SURFACE_DEFORM' and mod.target and 's06c_bind_vertices' in mod.target:
            target=mod.target
            result.append({'type':'surface','name':mod.name,'guide_name':target.name,'matrix_relative_to_part':[list(r) for r in obj.matrix_world.inverted()@target.matrix_world],
                           'bind_vertices':json.loads(target['s06c_bind_vertices']),'current_vertices':[list(v.co) for v in target.data.vertices],
                           'faces':[list(p.vertices) for p in target.data.polygons],
                           'subdivision':next((m.levels for m in target.modifiers if m.type=='SUBSURF'),0),
                           'strength':mod.strength,'falloff':mod.falloff,'show_viewport':mod.show_viewport,'show_render':mod.show_render})
        elif mod.type=='LATTICE' and mod.object and mod.object.get('s06c_owned_guide',False):
            target=mod.object;lat=target.data
            result.append({'type':'lattice','name':mod.name,'guide_name':target.name,'matrix_relative_to_part':[list(r) for r in obj.matrix_world.inverted()@target.matrix_world],
                           'resolution':[lat.points_u,lat.points_v,lat.points_w],'points':[list(p.co_deform) for p in lat.points],
                           'strength':mod.strength,'show_viewport':mod.show_viewport,'show_render':mod.show_render})
    return result

def export_profile(obj,path=None):
    p=get_profile(obj);p['matrix_world']=[list(r) for r in obj.matrix_world];p['deformers']=current_deformers(obj)
    if path:
        from .production import _atomic
        _atomic(Path(path),json.dumps(p,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
    set_profile(obj,p)
    return p

def bind_surface(context,obj,guide,name='TressIR_SurfaceDeform',falloff=4.):
    mod=obj.modifiers.new(name,'SURFACE_DEFORM');mod.target=guide;mod.falloff=falloff
    context.view_layer.update()
    with context.temp_override(object=obj,active_object=obj,selected_objects=[obj],selected_editable_objects=[obj]):
        bpy.ops.object.surfacedeform_bind(modifier=mod.name)
    if not mod.is_bound:
        obj.modifiers.remove(mod);raise ValueError('Surface Deform did not bind.')
    return mod

def add_surface_guide(context,obj,nu=5,nv=9):
    profile=get_profile(obj)
    if profile['schema']==sheet.SCHEMA:points=sheet.guide_grid(profile,nu,nv)
    elif profile['schema']==sheet_v4.SCHEMA:points=sheet_v4.guide_grid(profile,nu,nv)
    else:
        centers,axes,angles=clump.evaluated_samples(profile);t=[r['t'] for r in profile['base_samples']];q=np.linspace(0,t[-1],nv)
        c=clump.interpolate(t,centers,q);a=clump.interpolate(t,axes[:,0],q);ang=clump.interpolate(t,angles,q)
        a=np.maximum(a*1.35,max(a)*.28);points=[]
        for center,width,angle in zip(c,a,ang):
            for u in np.linspace(-1,1,nu):points.append(center+u*width*np.array([np.cos(angle),np.sin(angle),0]))
        points=np.asarray(points)
    faces=[]
    for row in range(nv-1):
        for col in range(nu-1):
            a=row*nu+col;b=a+1;c=b+nu;d=a+nu;faces.append((a,b,c,d))
    state={'type':'surface','name':'TressIR_SurfaceDeform','guide_name':obj.name+'_SURFACE','matrix_relative_to_part':np.eye(4).tolist(),'bind_vertices':points.tolist(),'current_vertices':points.tolist(),'faces':faces,'subdivision':2}
    return restore_deformers(context,obj,[state])[0]

def add_lattice(context,obj,resolution=(5,3,6)):
    v=np.array([list(p.co) for p in obj.data.vertices]);lo=v.min(axis=0);hi=v.max(axis=0)
    transform=Matrix.Translation((lo+hi)/2)@Matrix.Diagonal([*((hi-lo)*1.12),1.])
    state={'type':'lattice','name':'TressIR_Lattice','guide_name':obj.name+'_CAGE','matrix_relative_to_part':[list(r) for r in transform],'resolution':list(resolution),'points':None}
    return restore_deformers(context,obj,[state])[0]

def restore_deformers(context,obj,states):
    guides=[]
    for state in states:
        if state['type']=='surface':
            me=bpy.data.meshes.new(state['guide_name']+'_Mesh');me.from_pydata(state['bind_vertices'],[],state['faces']);me.update()
            guide=bpy.data.objects.new(state['guide_name'],me)
        elif state['type']=='lattice':
            lat=bpy.data.lattices.new(state['guide_name']+'_Data');lat.points_u,lat.points_v,lat.points_w=state['resolution']
            lat.interpolation_type_u=lat.interpolation_type_v=lat.interpolation_type_w='KEY_BSPLINE'
            guide=bpy.data.objects.new(state['guide_name'],lat)
        else:raise ValueError('Unknown deformation guide kind.')
        context.scene.collection.objects.link(guide);guide.parent=obj.parent
        guide.matrix_world=obj.matrix_world@Matrix(state['matrix_relative_to_part']);guide.display_type='WIRE';guide.hide_render=True;guide.show_in_front=True
        guide.color=(.98,.55,.12,1);guide['s06c_owner']=obj.name;guide['s06c_owned_guide']=True
        if state['type']=='surface':
            guide['s06c_bind_vertices']=json.dumps(state['bind_vertices'])
            if state.get('subdivision',0):
                sub=guide.modifiers.new('Smooth control surface','SUBSURF');sub.levels=state['subdivision'];sub.render_levels=sub.levels
            tri=guide.modifiers.new('Planar binding faces','TRIANGULATE')
            mod=bind_surface(context,obj,guide,state['name'],state.get('falloff',4.))
            for vertex,co in zip(guide.data.vertices,state['current_vertices']):vertex.co=co
            guide.data.update()
        else:
            mod=obj.modifiers.new(state['name'],'LATTICE');mod.object=guide
            if state.get('points'):
                if len(state['points'])!=len(guide.data.points):raise ValueError('Lattice resolution does not match its saved points.')
                for point,co in zip(guide.data.points,state['points']):point.co_deform=co
        mod.strength=state.get('strength',1.);mod.show_viewport=state.get('show_viewport',True);mod.show_render=state.get('show_render',True)
        guides.append(guide)
    context.view_layer.update()
    return guides

def rebuild(context,obj,profile):
    # Validate/build before replacing anything in the scene.
    if profile['schema']==sheet_v4.SCHEMA:profile=sheet_v4.upgrade(profile)
    me,check=generate_mesh(profile,obj.name+'_Mesh')
    states=current_deformers(obj);owned=[]
    # Verify the binding on a disposable candidate while the original still exists.
    if states:
        from . import production
        trial=copy.deepcopy(profile);trial['matrix_world']=[list(r) for r in obj.matrix_world];trial['deformers']=states
        try:temp=production.build_candidate(context,trial,'REBUILD_CHECK',preview=False)
        except Exception:
            bpy.data.meshes.remove(me);raise
        production.discard_candidate(context,temp)
    for mod in list(obj.modifiers):
        guide=mod.target if mod.type=='SURFACE_DEFORM' else (mod.object if mod.type=='LATTICE' else None)
        if guide and guide.get('s06c_owned_guide',False):owned.append(guide);obj.modifiers.remove(mod)
    old=obj.data;obj.data=me
    if old.users==0:bpy.data.meshes.remove(old)
    for guide in owned:
        # Guides created here are per-part. Do not remove an independently shared object.
        used=any((m.type=='SURFACE_DEFORM' and m.target==guide) or (m.type=='LATTICE' and m.object==guide) for other in bpy.data.objects for m in other.modifiers)
        if not used:bpy.data.objects.remove(guide,do_unlink=True)
    restore_deformers(context,obj,states)
    from .review import link_dependencies
    for scene in bpy.data.scenes:
        if obj.name in scene.objects:link_dependencies(scene,obj)
    p=copy.deepcopy(profile);p['deformers']=current_deformers(obj);set_profile(obj,p);obj['s06c_last_geometry_check']=json.dumps(check)
    return check

def evaluated_geometry(context,obj):
    context.view_layer.update();dg=context.evaluated_depsgraph_get();eo=obj.evaluated_get(dg);me=eo.to_mesh()
    v=np.array([list(vertex.co) for vertex in me.vertices]);f=[list(face.vertices) for face in me.polygons];eo.to_mesh_clear()
    return v,f

def fit_from_reference(context,reference,name='TressIR_SourceFit'):
    vertices,faces=evaluated_geometry(context,reference)
    p=clump.fit_reference(vertices,faces,[list(r) for r in reference.matrix_world],name)
    p['history'][-1]['source_object']=reference.name
    return create_object(context,p,name)

def fit_sheet_depth(context,obj,reference,controls=18,smoothing=1e-5):
    p=sheet_v4.upgrade(get_profile(obj));poly,_,_=sheet_v4._outline(p)
    vertices,faces=evaluated_geometry(context,reference)
    transform=obj.matrix_world.inverted()@reference.matrix_world
    from mathutils import Vector
    vertices=np.array([tuple(transform@Vector(v)) for v in vertices])
    scale=p['design']['placement']['height_unit_m'];top=-poly[:,1].min()*scale;bottom=-poly[:,1].max()*scale
    field,measurements=fields.measure_sheet_field(vertices,faces,top,bottom,controls,smoothing)
    p['depth_field']=field;p.setdefault('history',[]).append({'operation':'source_measured_then_control_fit','source_object':reference.name,'measurements':len(measurements['u']),'controls':controls,'smoothing':smoothing})
    rebuild(context,obj,p)
    return field['fit']

def object_quality(context,obj):
    if not obj or obj.type!='MESH':raise ValueError('Select a mesh for quality inspection.')
    v,faces=evaluated_geometry(context,obj)
    f=np.array([(p[0],p[i],p[i+1]) for p in faces for i in range(1,len(p)-1)],int)
    region=obj.data.attributes.get('s06c_face_region')
    tags=[int(x.value) for x in region.data] if region and len(region.data)==len(f) else None
    report=quality.analyze(v,f,tags);obj['s06c_quality_report']=json.dumps(report)
    return report
