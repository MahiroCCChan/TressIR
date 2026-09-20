"""Fixed camera review and silhouette diagnostics. Uses Blender and NumPy only."""
import json,math
from pathlib import Path
import numpy as np
import bpy
from mathutils import Vector

VIEWS=[('Front',0),('Front30',30),('Front60',60),('Side',90),('Back60',120),('Back30',150),('Back',180),('LeftBack',240),('LeftSide',270),('LeftFront',300),('FrontL30',330),('Top',None)]

def link_dependencies(scene,obj):
    pending=[obj];seen=set()
    while pending:
        o=pending.pop()
        if o.name in seen:continue
        seen.add(o.name)
        if o.name not in scene.objects:scene.collection.objects.link(o)
        if o.parent:pending.append(o.parent)
        for m in o.modifiers:
            if m.type=='SURFACE_DEFORM' and m.target:pending.append(m.target)
            if m.type=='LATTICE' and m.object:pending.append(m.object)

def make_rig(context,obj,reference):
    if not obj or not reference or obj==reference:raise ValueError('Choose a generated object and a separate mesh reference.')
    if obj.type!='MESH' or reference.type!='MESH':raise ValueError('Both review objects must be meshes.')
    name='TRESSIR_REVIEW_'+obj.name
    scene=bpy.data.scenes.get(name)
    if scene:
        scene.s06c_project_dir=context.scene.s06c_project_dir
        link_dependencies(scene,obj)
        return scene
    scene=bpy.data.scenes.new(name);scene.use_fake_user=True
    scene.s06c_project_dir=context.scene.s06c_project_dir
    link_dependencies(scene,obj)
    # The reference is a frozen evaluated snapshot; the generated object stays live.
    dg=context.evaluated_depsgraph_get();eo=reference.evaluated_get(dg)
    me=bpy.data.meshes.new_from_object(eo,depsgraph=dg)
    ref=bpy.data.objects.new(name+'_REFERENCE_SNAPSHOT',me);scene.collection.objects.link(ref)
    ref.matrix_world=reference.matrix_world.copy();ref.color=(.66,.68,.71,1)
    ref['provenance']='Frozen evaluated reference snapshot for multi-view comparison; not generated geometry.'
    ref['source_object']=reference.name
    scene['s06c_generated']=obj.name;scene['s06c_reference_snapshot']=ref.name;scene['s06c_review']=True
    scene.s06c_reference=ref
    scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_x=640;scene.render.resolution_y=640;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA';scene.render.film_transparent=True
    scene.display.shading.light='STUDIO';scene.display.shading.color_type='OBJECT';scene.display.shading.show_shadows=False
    scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH'
    scene.world=bpy.data.worlds.new(name+'_World');scene.world.color=(.10,.11,.14)
    scene.display.shading.background_type='WORLD'
    points=[o.matrix_world@Vector(corner) for o in (obj,reference) for corner in o.bound_box]
    lo=Vector(tuple(min(p[k] for p in points) for k in range(3)));hi=Vector(tuple(max(p[k] for p in points) for k in range(3)))
    center=(lo+hi)/2;radius=max((p-center).length for p in points);distance=max(radius*4,.15)
    for label,angle in VIEWS:
        ca=bpy.data.cameras.new('TRESSIR_'+label);cam=bpy.data.objects.new(name+'_'+label,ca);scene.collection.objects.link(cam)
        direction=Vector((0,0,1)) if angle is None else Vector((math.sin(math.radians(angle)),-math.cos(math.radians(angle)),0))
        cam.location=center+direction*distance;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
        ca.type='ORTHO';ca.ortho_scale=radius*2.24;ca.clip_start=.001;ca.clip_end=100
        cam['s06c_view_label']=label
    scene.camera=next(o for o in scene.objects if o.type=='CAMERA' and o.get('s06c_view_label')=='Front')
    return scene

def set_view(context,scene,index):
    label=VIEWS[index%len(VIEWS)][0];cam=next(o for o in scene.objects if o.type=='CAMERA' and o.get('s06c_view_label')==label)
    context.window.scene=scene;scene.camera=cam
    generated=bpy.data.objects[scene['s06c_generated']]
    for ob in context.selected_objects:ob.select_set(False)
    generated.select_set(True);context.view_layer.objects.active=generated
    for area in (context.screen.areas if context.screen else []):
        if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='CAMERA'
    return label

def read_pixels(path):
    im=bpy.data.images.load(str(path),check_existing=False);w,h=im.size
    a=np.empty(w*h*4,np.float32);im.pixels.foreach_get(a);bpy.data.images.remove(im)
    return np.flipud(a.reshape(h,w,4)).copy()

def save_pixels(path,a):
    h,w=a.shape[:2];im=bpy.data.images.new('TressIR_Diagnostic',width=w,height=h,alpha=True)
    im.pixels.foreach_set(np.flipud(a).astype(np.float32).ravel());im.file_format='PNG';im.filepath_raw=str(path);im.save();bpy.data.images.remove(im)

# Small raster labels keep the diagnostic generator dependency-free inside Blender.
FONT={
'A':['01110','10001','10001','11111','10001','10001','10001'],
'B':['11110','10001','10001','11110','10001','10001','11110'],
'C':['01111','10000','10000','10000','10000','10000','01111'],
'D':['11110','10001','10001','10001','10001','10001','11110'],
'E':['11111','10000','10000','11110','10000','10000','11111'],
'F':['11111','10000','10000','11110','10000','10000','10000'],
'G':['01111','10000','10000','10111','10001','10001','01111'],
'I':['11111','00100','00100','00100','00100','00100','11111'],
'K':['10001','10010','10100','11000','10100','10010','10001'],
'L':['10000','10000','10000','10000','10000','10000','11111'],
'M':['10001','11011','10101','10101','10001','10001','10001'],
'N':['10001','11001','10101','10011','10001','10001','10001'],
'O':['01110','10001','10001','10001','10001','10001','01110'],
'P':['11110','10001','10001','11110','10000','10000','10000'],
'R':['11110','10001','10001','11110','10100','10010','10001'],
'S':['01111','10000','10000','01110','00001','00001','11110'],
'T':['11111','00100','00100','00100','00100','00100','00100'],
'U':['10001','10001','10001','10001','10001','10001','01110'],
'V':['10001','10001','10001','10001','10001','01010','00100'],
'W':['10001','10001','10001','10101','10101','11011','10001'],
'X':['10001','10001','01010','00100','01010','10001','10001'],
'Y':['10001','10001','01010','00100','00100','00100','00100'],
'0':['01110','10001','10011','10101','11001','10001','01110'],
'1':['00100','01100','00100','00100','00100','00100','01110'],
'2':['01110','10001','00001','00010','00100','01000','11111'],
'3':['11110','00001','00001','01110','00001','00001','11110'],
'4':['00010','00110','01010','10010','11111','00010','00010'],
'5':['11111','10000','10000','11110','00001','00001','11110'],
'6':['01110','10000','10000','11110','10001','10001','01110'],
'7':['11111','00001','00010','00100','01000','01000','01000'],
'8':['01110','10001','10001','01110','10001','10001','01110'],
'9':['01110','10001','10001','01111','00001','00001','01110'],
'.':['00000','00000','00000','00000','00000','00100','00100'],
'%':['11001','11010','00100','01000','10110','00110','00000'],
'-':['00000','00000','00000','11111','00000','00000','00000']}

def draw_label(a,x,y,label,scale=2,color=(.86,.89,.94,1)):
    for char in label.upper():
        glyph=FONT.get(char)
        if glyph:
            for row,line in enumerate(glyph):
                for col,value in enumerate(line):
                    if value=='1':a[y+row*scale:y+(row+1)*scale,x+col*scale:x+(col+1)*scale]=color
        x+=6*scale

def batch_review(context,scene,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    obj=bpy.data.objects[scene['s06c_generated']];ref=bpy.data.objects[scene['s06c_reference_snapshot']]
    original_scene=context.window.scene;oldhide=(obj.hide_render,ref.hide_render);oldcam=scene.camera
    context.window.scene=scene;context.view_layer.update();entries=[];overlays=[]
    try:
        for label,_ in VIEWS:
            scene.camera=next(o for o in scene.objects if o.type=='CAMERA' and o.get('s06c_view_label')==label)
            images=[]
            for suffix,target in [('reference',ref),('generated',obj)]:
                obj.hide_render=target!=obj;ref.hide_render=target!=ref
                scene.render.filepath=str(folder/f'{label}-{suffix}.png');bpy.ops.render.render(write_still=True,scene=scene.name)
                images.append(read_pixels(folder/f'{label}-{suffix}.png'))
            a=images[0][:,:,3]>.5;b=images[1][:,:,3]>.5
            union=int((a|b).sum());intersection=int((a&b).sum());iou=intersection/union if union else 1.
            overlay=np.zeros_like(images[0]);overlay[:]=(.055,.067,.09,1)
            overlay[a&b]=(.70,.76,.81,1);overlay[a&~b]=(.98,.52,.14,1);overlay[b&~a]=(.08,.66,.94,1)
            save_pixels(folder/f'{label}-overlay.png',overlay);overlays.append(overlay)
            entries.append({'view':label,'silhouette_iou':iou,'reference_pixels':int(a.sum()),'generated_pixels':int(b.sum()),'intersection_pixels':intersection,'union_pixels':union})
            print(f'TRESSIR_REVIEW {label}: silhouette IoU {iou:.4f}',flush=True)
    finally:
        obj.hide_render,ref.hide_render=oldhide;scene.camera=oldcam;context.window.scene=original_scene
    tile=320;header=42;grid=np.zeros((3*(tile+header)+52,4*tile,4),np.float32);grid[:]=(.055,.067,.09,1)
    for i,(a,e) in enumerate(zip(overlays,entries)):
        x=(i%4)*tile;y=(i//4)*(tile+header)
        draw_label(grid,x+12,y+13,e['view']+' '+f'{100*e["silhouette_iou"]:.1f}'+'%',2)
        yi=np.linspace(0,a.shape[0]-1,tile).astype(int);xi=np.linspace(0,a.shape[1]-1,tile).astype(int)
        grid[y+header:y+header+tile,x:x+tile]=a[yi][:,xi]
    draw_label(grid,18,grid.shape[0]-32,'GRAY OVERLAP - ORANGE REFERENCE ONLY - BLUE GENERATED ONLY',2)
    save_pixels(folder/'review-grid.png',grid)
    report={'reference':ref['source_object'],'generated':obj.name,'resolution':[scene.render.resolution_x,scene.render.resolution_y],
            'camera_policy':'Fixed orthographic positions and scale established from the initial pair bounds; includes both sides and top.',
            'entries':entries,'mean_silhouette_iou':float(np.mean([e['silhouette_iou'] for e in entries])),
            'limits':'Silhouette agreement is not a 3D surface error, collision test, or artistic approval. The reference is a frozen snapshot; the generated object evaluates live modifiers.'}
    (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
