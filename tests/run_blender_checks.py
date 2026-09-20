"""Run ONLY in a separate background Blender. Exercises the reusable tools, not user assets."""
import sys,json,copy,hashlib,uuid
from pathlib import Path
import numpy as np
import bpy
from mathutils import Matrix
if not bpy.app.background:raise RuntimeError('Verification requires a separate --background --factory-startup Blender process.')
REPO=Path(__file__).resolve().parents[1]
SRC=REPO/'src'
FIXTURES=REPO/'examples'/'profiles'
sys.path.insert(0,str(SRC))
import tressir_tools as addon
from tressir_tools import fields,sheet_v4,clump,quality,depth_order,production,blender_ops as ops
addon.register()
OUT=REPO/'tests'/'_artifacts';OUT.mkdir(parents=True,exist_ok=True)
results={}
def record(name,value,valid=True):
    results[name]=value;print('CHECK',name,value,flush=True)
    assert valid,name+': '+str(value)
def fails(name,callback):
    try:callback()
    except (ValueError,OSError) as e:record(name,str(e));return
    raise AssertionError(name+' did not reject invalid input')
def world_hash(ob):
    v,f=production._geometry(bpy.context,ob)
    return production._mesh_hash(v,f),[list(r) for r in ob.matrix_world]

if '--restore-only' in sys.argv:
    expectation=json.loads((OUT/'restore_expectation.json').read_text());project=Path(expectation['project'])
    before=set(bpy.data.objects.keys());restored=production.restore(bpy.context,project)
    for part,name in restored['objects'].items():
        obj=bpy.data.objects[name];actual=world_hash(obj);expected=expectation['parts'][part]
        record('fresh_process_'+part,actual[0],actual[0]==expected[0] and np.allclose(actual[1],expected[1]))
    second=production.restore(bpy.context,project);record('restore_idempotent',second['new_objects'],second['new_objects']==0)
    record('unrelated_scene_objects_preserved',sorted(before),before.issubset(set(bpy.data.objects.keys())))
    (OUT/'fresh_restore.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print('FRESH_RESTORE_OK',flush=True)
    raise SystemExit(0)

# Smooth noisy measurements while preserving explicit anchors and positive thickness.
u=np.linspace(0,1,241);rng=np.random.default_rng(916)
truth=-.025*np.sin(u*1.8);noise=rng.normal(0,.0018,len(u));noisy=truth+noise
samples={'u':u.tolist(),'center_y_m':noisy.tolist(),'half_depth_m':(.0018+.0003*np.cos(u*4)).tolist(),
         'rotation_rad':(((3.10+.12*u+np.pi)%(2*np.pi))-np.pi).tolist()}
anchors=[{'u':0.,'center_y_m':float(truth[0])},{'u':1.,'center_y_m':float(truth[-1])}]
field=fields.fit_depth_field(samples,18,1e-5,anchors);evaluated=fields.evaluate(field,u)
raw_error=float(np.sqrt(np.mean(noise**2)));fit_error=float(np.sqrt(np.mean((evaluated['center_y_m']-truth)**2)))
record('noise_reduction',{'raw_rms_m':raw_error,'fitted_rms_m':fit_error},fit_error<raw_error*.4)
record('field_end_anchors_m',evaluated['center_y_m'][[0,-1]].tolist(),np.allclose(evaluated['center_y_m'][[0,-1]],truth[[0,-1]],atol=1e-10))
record('rotation_unwrap_step_rad',float(np.abs(np.diff(evaluated['rotation_rad'])).max()),np.abs(np.diff(evaluated['rotation_rad'])).max()<.01)
record('positive_half_depth',float(evaluated['half_depth_m'].min()),(evaluated['half_depth_m']>0).all())
edited=fields.set_control(field,5,{'center_y_m':.01});ed=fields.evaluate(edited,[0,1])
record('edit_preserves_field_anchors',ed['center_y_m'].tolist(),np.allclose(ed['center_y_m'],truth[[0,-1]],atol=1e-10))
bad=copy.deepcopy(samples);bad['half_depth_m'][10]=-1;fails('negative_depth_rejected',lambda:fields.fit_depth_field(bad))

# New outlines use the same generator; no named user part is hard-coded.
outlines=[
    [(-20,0),(20,0),(24,38),(10,80),(0,58),(-14,88),(-23,40)],
    [(-24,0),(24,0),(27,35),(18,80),(12,64),(4,94),(-3,65),(-17,86),(-26,45)],
    [(-28,0),(28,0),(30,38),(24,85),(20,69),(12,94),(8,76),(0,100),(-6,74),(-16,93),(-20,70),(-28,82),(-31,37)]
]
profiles=[]
for count,outline in zip((2,3,5),outlines):
    feature_indices=[i for i in range(3,len(outline)-1)]
    anchors=[{'id':'anchor_'+str(i),'kind':'tip' if i%2 else 'notch','xy':list(outline[i])} for i in feature_indices]
    p=sheet_v4.new_profile(outline,anchors,'Generic_'+str(count),'TIPS'+str(count));p['depth_field']=copy.deepcopy(field)
    v,f,uv,special=sheet_v4.build_mesh(p);q=special['quality'];profiles.append(p)
    record('outline_'+str(count),{'vertices':len(v),'anchors':q['anchors'],'quality':q['regions'],'blocking':q['blocking']},not q['blocking'] and max(q['anchors'].values())<1e-8)
    (OUT/('generated_sheet_'+str(count)+'_tips.json')).write_text(json.dumps(p,indent=2),encoding='utf-8')
    doubled=np.vstack([f,f[:1]]);qbad=quality.analyze(v,doubled)
    record('duplicate_gate_'+str(count),qbad['blocking'],'duplicate_faces' in qbad['blocking'] and 'non_manifold_edges' in qbad['blocking'])
crossed=sheet_v4.new_profile([(0,0),(20,40),(0,40),(20,0)])
before=len(bpy.data.objects);fails('crossed_outline_rejected',lambda:production.build_candidate(bpy.context,crossed,'BAD'))
record('failed_build_did_not_add_objects',len(bpy.data.objects),len(bpy.data.objects)==before)

# Legacy geometry remains on the original decoder, rather than changing on import.
legacy=json.loads((FIXTURES/'legacy_clump.json').read_text());v,f,uv=clump.build_mesh(legacy)
legacy_obj=ops.create_object(bpy.context,legacy,'LEGACY_COMPAT')
from mathutils import Vector
actual=np.array([tuple(legacy_obj.matrix_world@Vector(x.co)) for x in legacy_obj.data.vertices])
record('legacy_world_geometry_error_m',float(np.linalg.norm(actual-v,axis=1).max()),np.linalg.norm(actual-v,axis=1).max()<2e-6)

# Fairing must preserve locked features, obey the displacement budget, and reduce roughness.
xx,zz=np.meshgrid(np.linspace(0,.05,17),np.linspace(0,.08,21));pts=np.column_stack([xx.ravel(),zz.ravel()]);tf=[]
for row in range(20):
    for col in range(16):
        a=row*17+col;tf.extend([(a,a+1,a+18),(a,a+18,a+17)])
tf=np.array(tf);locked=(pts[:,0]==0)|(pts[:,0]==.05)|(pts[:,1]==0)|(pts[:,1]==.08)|(pts[:,0]==.025)
y=rng.normal(0,.00025,len(pts));out=quality.constrained_fair(y,pts,tf,locked,.4,.001)
raw_rough=float(np.square(np.diff(y.reshape(21,17),n=2,axis=1)).mean());new_rough=float(np.square(np.diff(out.reshape(21,17),n=2,axis=1)).mean())
record('fairing_locked_exact',bool(np.array_equal(out[locked],y[locked])),np.array_equal(out[locked],y[locked]))
record('fairing_roughness',{'before':raw_rough,'after':new_rough},new_rough<raw_rough*.7)
record('fairing_displacement_budget_m',float(np.abs(out-y).max()),np.abs(out-y).max()<=.001+1e-12)

# Production lifecycle: one visible candidate, accepted immutable revision, native-guide round trip.
project=OUT/('production-'+uuid.uuid4().hex[:8]);p=profiles[1]
obj=production.build_candidate(bpy.context,p,'FRINGE',project);ops.add_surface_guide(bpy.context,obj)
guide=next(m.target for m in obj.modifiers if m.type=='SURFACE_DEFORM');guide.data.vertices[22].co.y-=.002;guide.data.update()
obj.modifiers[0].strength=.65
first=production.accept(bpy.context,obj,project,'FRINGE',checkpoint=True)
record('checkpoint_saved',first['checkpoint'],first['checkpoint'] is not None and Path(first['checkpoint']).exists())
record('checkpoint_did_not_switch_file',bpy.data.filepath,bpy.data.filepath=='')
candidate=production.build_candidate(bpy.context,ops.export_profile(obj),'FRINGE',project)
record('candidate_preview_hides_previous',{'old_hidden':obj.hide_get(),'candidate_hidden':candidate.hide_get()},obj.hide_get() and not candidate.hide_get())
production.discard_candidate(bpy.context,candidate);record('discard_restores_active_visibility',not obj.hide_get(),not obj.hide_get())
p2=copy.deepcopy(p);p2['generation']['edge_thickness_m']*=1.3
candidate=production.build_candidate(bpy.context,p2,'FRINGE',project)
second=production.accept(bpy.context,candidate,project,'FRINGE',checkpoint=False)
record('accepted_supersedes_previous',{'old':obj['s06c_lifecycle'],'new':candidate['s06c_lifecycle']},obj['s06c_lifecycle']=='archived' and candidate['s06c_lifecycle']=='active')
record('old_revision_preserved',first['revision']!=second['revision'],first['revision']!=second['revision'])

# An interrupted manifest write must leave the previous accepted set intact.
third=production.build_candidate(bpy.context,p,'FRINGE',project);previous=(project/'active.json').read_bytes();original_atomic=production._atomic
def interrupted(path,data):
    if Path(path).name=='active.json':raise OSError('simulated interruption before manifest replacement')
    return original_atomic(path,data)
production._atomic=interrupted
try:fails('interrupted_commit',lambda:production.accept(bpy.context,third,project,'FRINGE',checkpoint=False))
finally:production._atomic=original_atomic
record('manifest_unchanged_after_failure',(project/'active.json').read_bytes()==previous,(project/'active.json').read_bytes()==previous)
restored=production.restore(bpy.context,project);record('restore_after_failure',restored['restored_parts'],restored['restored_parts']==1)

# Direct unrecorded vertex edits cannot be silently accepted as old parameters.
badmesh=production.build_candidate(bpy.context,p,'BADMESH',project);badmesh.data.vertices[20].co.y+=.002
fails('unrecorded_vertex_edit_rejected',lambda:production.accept(bpy.context,badmesh,project,'BADMESH',checkpoint=False));production.discard_candidate(bpy.context,badmesh)
untracked=bpy.data.objects.get('Cube');fails('untracked_source_mesh_rejected',lambda:production.accept(bpy.context,untracked,project,'SOURCE',checkpoint=False))

# Save a second accepted kind and verify complete rebuilding in a fresh process.
other=production.build_candidate(bpy.context,legacy,'CLUMP',project);ops.add_lattice(bpy.context,other)
cage=other.modifiers[0].object;cage.data.points[52].co_deform.x+=.06;cage.data.update_tag()
production.accept(bpy.context,other,project,'CLUMP',checkpoint=False)
assets=production.manifest(project);expectation={'project':str(project),'parts':{}}
for part in assets['parts']:
    ob=next(o for o in bpy.data.objects if o.get('s06c_project_id')==assets['project_id'] and o.get('s06c_part_id')==part and o.get('s06c_lifecycle')=='active')
    expectation['parts'][part]=world_hash(ob)
(OUT/'restore_expectation.json').write_text(json.dumps(expectation,indent=2),encoding='utf-8')
entry=assets['parts']['FRINGE'];asset=project/entry['path'];content=asset.read_bytes();asset.write_bytes(content+b' ')
before=len(bpy.data.objects);fails('tampered_revision_rejected',lambda:production.restore(bpy.context,project));asset.write_bytes(content)
record('tampered_restore_no_scene_change',len(bpy.data.objects),len(bpy.data.objects)==before)

# Declared local front/back relations are enforced during acceptance.
order_project=OUT/('ordering-'+uuid.uuid4().hex[:8]);production.set_depth_order(order_project,[{'front':'A','back':'B','axis':'Y','front_sign':-1,'gap_m':.001}])
rectangle=sheet_v4.new_profile([(-10,0),(10,0),(10,50),(-10,50)],name='Order fixture')
a=production.build_candidate(bpy.context,rectangle,'A',order_project);a.parent.location.y=-.004;bpy.context.view_layer.update();production.accept(bpy.context,a,order_project,'A',False)
b=production.build_candidate(bpy.context,rectangle,'B',order_project);b.parent.location.y=-.005;bpy.context.view_layer.update()
fails('depth_flip_rejected',lambda:production.accept(bpy.context,b,order_project,'B',False))
b.parent.location.y=.001;bpy.context.view_layer.update();production.accept(bpy.context,b,order_project,'B',False)
ordered=production.check_depth_order(bpy.context,order_project);record('depth_order_passes',ordered,ordered[0]['overlap_samples']>0 and ordered[0]['violations']==0)

# Public UI operators are callable, and invalid input does not masquerade as success.
fixture=sheet_v4.new_profile([(-20,0),(20,0),(20,60),(-20,60)],name='Measured reference fixture')
fixture['depth_field']=fields.fit_depth_field({'u':u.tolist(),'center_y_m':(-.01*np.sin(u*2)).tolist(),'half_depth_m':(.002+u*.0002).tolist(),'rotation_rad':(.08+u*.04).tolist()},18,1e-6)
source=ops.create_object(bpy.context,fixture,'SOURCE_MEASUREMENT_FIXTURE');source_hash=world_hash(source)
target=production.build_candidate(bpy.context,sheet_v4.new_profile([(-20,0),(20,0),(20,60),(-20,60)]),'MEASURED')
addon.activate(bpy.context,target);bpy.context.scene.s06c_reference=source
record('public_measure_depth',str(bpy.ops.s06c.fit_sheet_depth()))
measured=ops.get_profile(target);actual=fields.evaluate(measured['depth_field'],u);ideal=fields.evaluate(fixture['depth_field'],u)
record('measured_center_rms_m',float(np.sqrt(np.mean((actual['center_y_m']-ideal['center_y_m'])**2))),np.sqrt(np.mean((actual['center_y_m']-ideal['center_y_m'])**2))<.0005)
record('measurement_source_unchanged',world_hash(source)==source_hash,world_hash(source)==source_hash)
before_hash=world_hash(target);bpy.context.scene.s06c_field_index=8;addon.read_control(None,bpy.context);bpy.context.scene.s06c_field_y+=.8
record('public_apply_depth_control',str(bpy.ops.s06c.apply_depth_control()))
record('depth_control_changes_geometry',world_hash(target)!=before_hash,world_hash(target)!=before_hash)
ops.add_surface_guide(bpy.context,target);live_guide=target.modifiers[0].target;live_guide.data.vertices[22].co.y-=.001;live_guide.data.update()
before_hash=world_hash(target);ops.rebuild(bpy.context,target,ops.get_profile(target))
record('rebuild_preserves_guide_deformation',world_hash(target)==before_hash,world_hash(target)==before_hash)
bad_state=ops.export_profile(target);bad_state['deformers']=[{'type':'unknown'}]
before_objects=set(bpy.data.objects);before_meshes=set(bpy.data.meshes);before_texts=set(bpy.data.texts)
fails('invalid_guide_build_rejected',lambda:production.build_candidate(bpy.context,bad_state,'BAD_GUIDE'))
record('failed_guide_build_cleans_owned_data',True,set(bpy.data.objects)==before_objects and set(bpy.data.meshes)==before_meshes and set(bpy.data.texts)==before_texts)
addon.activate(bpy.context,untracked);record('quality_on_untracked_mesh',str(bpy.ops.s06c.quality()),bpy.ops.s06c.quality()=={'FINISHED'})
# A review scene keeps the linked generated part; acceptance does not link the whole project into it.
home_scene=bpy.context.scene
rig=addon.review.make_rig(bpy.context,b,a);addon.review.set_view(bpy.context,rig,1)
record('review_carries_project_path',str(addon.project_path(bpy.context)),addon.project_path(bpy.context)==order_project.resolve())
production.accept(bpy.context,b,order_project,'B',False)
record('accept_in_review_keeps_part_link',b.name in rig.objects,b.name in rig.objects)
record('accept_in_review_does_not_link_other_parts',a.name not in rig.objects,a.name not in rig.objects)
bpy.context.window.scene=home_scene
addon.activate(bpy.context,b);bpy.context.scene.s06c_project_dir=str(order_project)
record('public_quality_operator',str(bpy.ops.s06c.quality()),bpy.ops.s06c.quality()=={'FINISHED'})
record('public_restore_operator',str(bpy.ops.s06c.restore_active()),bpy.ops.s06c.restore_active()=={'FINISHED'})
(OUT/'checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('TOOL_CHECKS_OK',flush=True)
