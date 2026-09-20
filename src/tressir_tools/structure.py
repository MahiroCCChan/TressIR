"""Explicit image structure -> independently editable v4 parts in one shared frame.

Reuses the reviewed contour compiler, depth fields, mesh validation and production
objects. No inference service is invoked. Input is authored by a person or LLM.
"""
import copy, json, os, uuid
import shutil
from pathlib import Path
import numpy as np
from . import trace, sheet_v4, depth_order, production, review

SCHEMA = 'sword06c.structure.v1'
MANIFEST_SCHEMA = 'sword06c.structure-preview.v1'
COLORS = [(0.18,0.58,0.75,1), (0.82,0.48,0.18,1),
          (0.51,0.36,0.75,1), (0.12,0.64,0.46,1), (0.80,0.27,0.45,1)]


def prepare(image_path,output_dir,group_id='HAIR_GROUP',height_mm=100):
    """Prepare an unchanged source and a blank explicit structure document."""
    out=Path(output_dir).resolve();production._id(group_id)
    if (out/'structure.json').exists():raise ValueError('structure.json already exists; keep the existing interpretation or choose a new folder.')
    prepared=trace.prepare(image_path,out,group_id,height_mm)
    old=json.loads(Path(prepared['trace']).read_text(encoding='utf-8'))
    doc={'schema':SCHEMA,'id':group_id,'source':old['source'],'calibration':old['calibration'],
         'interpretation':'','parts':[],'overlaps':[]}
    trace._write(out/'structure.json',doc)
    prompt=Path(__file__).with_name('LLM_STRUCTURE_PROMPT.txt')
    if prompt.exists():shutil.copy2(prompt,out/prompt.name)
    return {'structure':str(out/'structure.json'),'source':prepared['source'],'grid':prepared['grid']}


def _document(path):
    path = Path(path).resolve()
    doc = json.loads(path.read_text(encoding='utf-8-sig'))
    if doc.get('schema') != SCHEMA:
        raise ValueError('Expected '+SCHEMA)
    production._id(doc['id'])
    source, pixels = trace._read_source(doc, path)
    trace._projection(doc)
    return doc, source, pixels


def _rules(doc, ids):
    origin, scale = trace._projection(doc)
    result = []
    for r in doc.get('overlaps', []):
        if r['front'] not in ids or r['back'] not in ids or r['front'] == r['back']:
            raise ValueError('Overlap must name two different existing parts.')
        if r.get('basis') not in ('observed','inferred') or not str(r.get('note','')).strip():
            raise ValueError('An overlap needs an interpretation basis and note.')
        gap = float(r.get('gap_mm', .2)) / 1000
        if not np.isfinite(gap) or not 0 <= gap <= .02:
            raise ValueError('Overlap gap must be finite, 0..20 mm.')
        rule = {'front':r['front'], 'back':r['back'], 'axis':'Y',
                'front_sign':-1, 'gap_m':gap, 'resolution':96}
        if 'region_uv' in r:
            box = np.asarray(r['region_uv'], float)
            if box.shape != (4,) or not np.isfinite(box).all() or (box<0).any() or (box>1000).any() or box[0]>=box[2] or box[1]>=box[3]:
                raise ValueError('region_uv is [left, top, right, bottom], 0..1000.')
            a = (box[:2]-origin)*scale/1000
            b = (box[2:]-origin)*scale/1000
            rule['bounds_2d_m'] = [[float(a[0]), float(-b[1])], [float(b[0]), float(-a[1])]]
        result.append(rule)
    return result


def _checks(meshes, rules):
    results = []
    for rule in rules:
        options = {k:v for k,v in rule.items() if k not in ('front','back')}
        a,b = meshes[rule['front']], meshes[rule['back']]
        report = depth_order.compare(a[0],a[1],b[0],b[1],**options)
        report['front'],report['back'] = rule['front'],rule['back']
        report['passed'] = report['overlap_samples'] > 0 and report['violations'] == 0
        results.append(report)
    return results


def compile_document(doc):
    """Compile all parts before any scene mutation. No implicit generic bend."""
    if doc.get('schema') != SCHEMA:
        raise ValueError('Expected '+SCHEMA)
    parts = doc['parts']
    if not 1 <= len(parts) <= 32:
        raise ValueError('A structure group needs 1..32 parts.')
    ids = [production._id(p['id']) for p in parts]
    if len(set(ids)) != len(ids):
        raise ValueError('Part IDs must be unique.')
    compiled, meshes = {}, {}
    for part in parts:
        if not str(part.get('role','')).strip():
            raise ValueError(part['id']+': explain the part role, not just its outline.')
        if not part.get('depth') or part['depth'].get('basis') != 'estimated' or not str(part['depth'].get('note','')).strip():
            raise ValueError(part['id']+': explicit estimated depth with a reason is required.')
        if 'ridges' not in part or not str(part.get('surface_note','')).strip():
            raise ValueError(part['id']+': declare ridges (possibly []) and explain the surface interpretation.')
        candidate = {k:copy.deepcopy(part[k]) for k in ('name','nodes','notes','depth','ridges') if k in part}
        candidate['id'] = 'A'
        local = {'schema':trace.SCHEMA, 'part_id':part['id'], 'source':copy.deepcopy(doc['source']),
                 'calibration':copy.deepcopy(doc['calibration']), 'candidates':[candidate]}
        p,meta = trace.compile_candidate(local,'A')
        # The existing generator owns triangulation. A group can request a
        # finer common budget without replacing its geometry implementation.
        if 'generation' in doc:
            allowed=set(sheet_v4.DEFAULTS)
            if not set(doc['generation']).issubset(allowed):
                raise ValueError('Unknown v4 generation setting in structure input.')
            p['generation'].update(copy.deepcopy(doc['generation']))
        p['structure'] = {'id':doc['id'],'part_id':part['id'],'role':part['role'],
                          'surface_note':part['surface_note'],'overlaps':copy.deepcopy(doc.get('overlaps',[]))}
        p['history'].append({'operation':'explicit-image-structure','group':doc['id'],
                             'depth_is_estimated':True,'source_mesh_measured':False})
        vertices,faces,_,special = sheet_v4.build_mesh(p)
        meta.update(vertices=len(vertices),triangles=len(faces),quality=special['quality'])
        meshes[part['id']] = (vertices, faces)
        compiled[part['id']] = (p,meta)
    rules = _rules(doc,ids)
    checks = _checks(meshes,rules)
    return compiled, rules, checks


def _overview(pixels, compiled, output):
    base = trace._opaque(pixels)
    h,w = base.shape[:2]
    all_points = np.vstack([m['points_uv'] for _,m in compiled.values()])*[w/1000,h/1000]
    lo = np.maximum(0,np.floor(all_points.min(axis=0)-35).astype(int))
    hi = np.minimum([w,h],np.ceil(all_points.max(axis=0)+35).astype(int))
    overlay = base.copy()
    for index,(pid,(p,meta)) in enumerate(compiled.items()):
        color = COLORS[index%len(COLORS)]
        for segment in p['trace_review']['segments']:
            points = np.asarray(segment['points_uv'])*[w/1000,h/1000]
            for j,(a,b) in enumerate(zip(points[:-1],points[1:])):
                if segment['basis']=='observed' or j%5<3:
                    trace._line(overlay,a,b,color,2)
        tip = next((n for n in p['trace_review']['nodes'] if n.get('kind')=='tip'),p['trace_review']['nodes'][0])
        point = np.array(tip['point'])*[w/1000,h/1000]
        trace._line(overlay,point,point,color,5)
        review.draw_label(overlay,int(np.clip(point[0]+7,0,w-60)),int(np.clip(point[1]-15,0,h-24)),str(index+1),2,color)
    a=base[lo[1]:hi[1],lo[0]:hi[0]];b=overlay[lo[1]:hi[1],lo[0]:hi[0]]
    ch,cw=a.shape[:2]
    board=np.ones((ch+48,cw*2+20,4),np.float32)
    board[48:,:cw]=a;board[48:,cw+20:]=b
    review.draw_label(board,8,15,'SOURCE',2,(.12,.16,.2,1))
    review.draw_label(board,cw+28,15,'STRUCTURE',2,(.12,.16,.2,1))
    review.save_pixels(output,board)


def preview(structure_path, output_dir=None):
    """Export each canonical profile + composite structure drawing + depth checks."""
    path=Path(structure_path).resolve();doc,image,pixels=_document(path)
    compiled,rules,checks=compile_document(doc)
    out=Path(output_dir).resolve() if output_dir else path.parent/'reviews'/trace._sha(path)[:16]
    out.mkdir(parents=True,exist_ok=True)
    manifest={'schema':MANIFEST_SCHEMA,'id':doc['id'],'structure_path':os.path.relpath(path,out),
              'structure_sha256':trace._sha(path),'source_path':os.path.relpath(image,out),
              'source_sha256':trace._sha(image),'parts':{},'depth_rules':rules,'depth_checks':checks,
              'ready_to_generate':all(c['passed'] for c in checks)}
    for index,(pid,(p,meta)) in enumerate(compiled.items()):
        filename=pid+'.profile.json';trace._write(out/filename,p)
        manifest['parts'][pid]={'path':filename,'sha256':trace._sha(out/filename),'color':COLORS[index%len(COLORS)],
                                'quality':meta['quality'],'vertices':meta['vertices'],'triangles':meta['triangles']}
        trace._preview_png(pixels,p,meta,out/(pid+'-review.png'))
    _overview(pixels,compiled,out/'structure-review.png')
    trace._write(out/'structure_manifest.json',manifest)
    return {'manifest':str(out/'structure_manifest.json'),'overview':str(out/'structure-review.png'),
            'parts':list(compiled),'depth_checks':checks,'ready_to_generate':manifest['ready_to_generate']}


def _load_review(manifest_path):
    path=Path(manifest_path).resolve();m=json.loads(path.read_text(encoding='utf-8'))
    if m.get('schema')!=MANIFEST_SCHEMA:
        raise ValueError('Expected a structure preview manifest.')
    for file,sha in (('structure_path','structure_sha256'),('source_path','source_sha256')):
        if trace._sha(path.parent/m[file])!=m[sha]:
            raise ValueError('Structure or source changed: preview again.')
    doc,_,_=_document(path.parent/m['structure_path'])
    ids=[p['id'] for p in doc['parts']]
    if set(ids)!=set(m['parts']) or m['id']!=doc['id']:
        raise ValueError('Manifest no longer matches the structure group.')
    profiles,meshes={},{}
    for pid in ids:
        entry=m['parts'][pid];file=(path.parent/entry['path']).resolve()
        if not file.is_relative_to(path.parent) or trace._sha(file)!=entry['sha256']:
            raise ValueError('Reviewed part changed: preview again.')
        p=json.loads(file.read_text(encoding='utf-8'))
        if p.get('part_id')!=pid or p.get('structure',{}).get('id')!=doc['id']:
            raise ValueError('Reviewed part identity mismatch.')
        v,f,_,_=sheet_v4.build_mesh(p);meshes[pid]=(v,f);profiles[pid]=p
    # Recompute the checks from source declarations; a stale pass flag is not proof.
    rules=_rules(doc,ids);checks=_checks(meshes,rules)
    if any(not c['passed'] for c in checks):
        raise ValueError('Declared overlap has no sampled overlap or insufficient clearance. Inspect the preview report.')
    return m,profiles,checks


def generate(context, manifest_path, project_root):
    """Build a complete group, rolling back this new group on a build failure.

Existing scene objects and accepted assets are never hidden or discarded here.
The returned parts remain ordinary independently editable production candidates.
"""
    m,profiles,checks=_load_review(manifest_path)
    created={};instance=uuid.uuid4().hex
    try:
        for index,(pid,p) in enumerate(profiles.items()):
            obj=production.build_candidate(context,p,pid,project_root,preview=False)
            created[pid]=obj
            obj['s06c_structure_id']=m['id'];obj['s06c_structure_instance']=instance
            obj['s06c_structure_manifest']=str(Path(manifest_path).resolve())
            obj['s06c_structure_profile_sha256']=m['parts'][pid]['sha256']
            obj.color=COLORS[index%len(COLORS)]
    except Exception:
        for obj in list(created.values()):production.discard_candidate(context,obj)
        raise
    return {'objects':{pid:o.name for pid,o in created.items()},'depth_checks':checks,
            'instance':instance,'state':'candidate','accepted':False}


def check_current(context, objects, manifest_path=None):
    """Recheck actual evaluated geometry after independent part/guide edits."""
    from mathutils import Vector
    if manifest_path is not None:
        m,_,_=_load_review(manifest_path)
        doc,_,_=_document(Path(manifest_path).resolve().parent/m['structure_path'])
        ids=list(m['parts'])
    else:
        # Accepted/restored profiles retain declarations even when the original
        # review bundle is unavailable. Check those saved declarations, not a
        # subsequently edited source document.
        from . import blender_ops
        saved={pid:blender_ops.get_profile(obj) for pid,obj in objects.items()}
        if not saved:raise ValueError('No current structure objects supplied.')
        first=next(iter(saved.values()));definition=first['structure']
        doc={'source':first['trace_review']['source'],'calibration':first['trace_review']['calibration'],
             'overlaps':definition['overlaps']}
        for pid,p in saved.items():
            if p.get('part_id')!=pid or p.get('structure',{}).get('id')!=definition['id'] or p['structure']['overlaps']!=doc['overlaps'] or p['trace_review']['calibration']!=doc['calibration'] or p['trace_review']['source']!=doc['source']:
                raise ValueError('Current parts do not share the same saved structure declarations.')
        ids=list(saved)
    meshes={}
    for pid in ids:
        if pid not in objects:raise ValueError('Missing current group part: '+pid)
        obj=objects[pid]
        v,f=production._geometry(context,obj)
        v=np.array([list(obj.matrix_world@Vector(x)) for x in v])
        meshes[pid]=(v,f)
    return _checks(meshes,_rules(doc,ids))
