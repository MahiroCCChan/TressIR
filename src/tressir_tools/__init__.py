bl_info={'name':'TressIR Hair Tools','author':'TressIR project','version':(0,1,0),'blender':(5,2,0),'location':'View3D > Sidebar > Hair Tools','description':'Structured hair authoring, deterministic geometry, and recoverable parametric assets','category':'Object'}
import json,math
from pathlib import Path
import bpy
from bpy.props import StringProperty,FloatProperty,IntProperty,PointerProperty,BoolProperty
from bpy_extras.io_utils import ImportHelper,ExportHelper
from . import clump,sheet,sheet_v4,fields,blender_ops as ops,review,production,trace,structure_ui

def hair_object(context):
    ob=context.active_object
    if ob and ops.PROFILE_KEY in ob:return ob
    if ob and ob.get('s06c_owner'):return bpy.data.objects.get(ob['s06c_owner'])
    if ob:
        for child in ob.children:
            if ops.PROFILE_KEY in child:return child
    return None

def activate(context,obj):
    for o in context.selected_objects:o.select_set(False)
    obj.select_set(True);context.view_layer.objects.active=obj

def read_control(self,context):
    try:
        p=ops.get_profile(hair_object(context));s=context.scene
        if p.get('part_id'):s.s06c_part_id=p['part_id']
        if p['schema']==clump.SCHEMA:
            e=p['edit_controls'][min(s.s06c_control,len(p['edit_controls'])-1)]
            s.s06c_dx,s.s06c_dy,s.s06c_dz=[x*1000 for x in e['offset_m']]
            s.s06c_scale_a,s.s06c_scale_b=e['axis_scale'];s.s06c_angle=math.degrees(e['angle_offset_rad'])
        else:
            cfg=p['design'];unit=cfg['placement']['depth_unit_m']*1000
            if cfg['ridge_guides']:
                g=cfg['ridge_guides'][min(s.s06c_ridge,len(cfg['ridge_guides'])-1)];s.s06c_ridge_height=g['height']*unit
            s.s06c_thickness=cfg['shell_thickness']*unit
            if 'depth_field' in p:
                f=p['depth_field'];i=min(s.s06c_field_index,len(f['knots'])-5)
                s.s06c_field_x=f['coefficients']['center_x_m'][i]*1000;s.s06c_field_y=f['coefficients']['center_y_m'][i]*1000
                s.s06c_field_half=math.exp(f['coefficients']['half_depth_m'][i])*1000;s.s06c_field_angle=math.degrees(f['coefficients']['rotation_rad'][i])
    except (ValueError,KeyError,IndexError):pass

class S06C_OT_import(bpy.types.Operator,ImportHelper):
    bl_idname='s06c.import_profile';bl_label='Import JSON as candidate';bl_options={'REGISTER','UNDO'}
    filename_ext='.json';filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:
            p=json.loads(Path(self.filepath).read_text(encoding='utf-8-sig'))
            if 'centerline' in p and 'base_samples' not in p:p=clump.from_legacy(p)
            part=p.get('part_id') or context.scene.s06c_part_id
            ob=production.build_candidate(context,p,part,project_path(context));activate(context,ob);read_control(None,context);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_export(bpy.types.Operator,ExportHelper):
    bl_idname='s06c.export_profile';bl_label='Export profile + guides';filename_ext='.json'
    filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:ops.export_profile(hair_object(context),self.filepath);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_read(bpy.types.Operator):
    bl_idname='s06c.read_control';bl_label='Read selected control'
    def execute(self,context):read_control(None,context);return {'FINISHED'}

class S06C_OT_apply(bpy.types.Operator):
    bl_idname='s06c.apply_control';bl_label='Apply parameter edit';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            ob=hair_object(context);p=ops.get_profile(ob);s=context.scene
            if p['schema']==clump.SCHEMA:
                e=p['edit_controls'][s.s06c_control];e['offset_m']=[s.s06c_dx/1000,s.s06c_dy/1000,s.s06c_dz/1000]
                e['axis_scale']=[s.s06c_scale_a,s.s06c_scale_b];e['angle_offset_rad']=math.radians(s.s06c_angle)
            else:
                cfg=p['design'];unit=cfg['placement']['depth_unit_m']*1000
                if cfg['ridge_guides']:cfg['ridge_guides'][s.s06c_ridge]['height']=s.s06c_ridge_height/unit
                cfg['shell_thickness']=s.s06c_thickness/unit
                if cfg['shell_thickness']<cfg['edge_thickness']:raise ValueError('Shell thickness cannot be below edge thickness.')
            p.setdefault('history',[]).append({'operation':'direct-parametric-repair','control_index':s.s06c_control if p['schema']==clump.SCHEMA else s.s06c_ridge})
            ops.rebuild(context,ob,p);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_rebuild(bpy.types.Operator):
    bl_idname='s06c.rebuild';bl_label='Rebuild from embedded JSON';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:ob=hair_object(context);ops.rebuild(context,ob,ops.get_profile(ob));return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_surface(bpy.types.Operator):
    bl_idname='s06c.add_surface_guide';bl_label='Add editable surface guide';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            ob=hair_object(context)
            if any(m.type=='SURFACE_DEFORM' and m.target and m.target.get('s06c_owned_guide') for m in ob.modifiers):raise ValueError('This part already has a surface guide.')
            guide=ops.add_surface_guide(context,ob);activate(context,guide);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_lattice(bpy.types.Operator):
    bl_idname='s06c.add_lattice';bl_label='Add lattice cage';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:guide=ops.add_lattice(context,hair_object(context));activate(context,guide);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_fit(bpy.types.Operator):
    bl_idname='s06c.fit_reference';bl_label='Measure reference -> new clump';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            ref=context.scene.s06c_reference
            if not ref:raise ValueError('Choose the reference object first.')
            obj=ops.fit_from_reference(context,ref);activate(context,obj);read_control(None,context);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_review(bpy.types.Operator):
    bl_idname='s06c.make_review';bl_label='Open fixed-camera review'
    def execute(self,context):
        try:
            scene=review.make_rig(context,hair_object(context),context.scene.s06c_reference);review.set_view(context,scene,0);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_next_view(bpy.types.Operator):
    bl_idname='s06c.next_view';bl_label='Next review camera'
    def execute(self,context):
        scene=context.scene
        if not scene.get('s06c_review'):self.report({'ERROR'},'Open a review scene first.');return {'CANCELLED'}
        scene.s06c_view=(scene.s06c_view+1)%len(review.VIEWS);review.set_view(context,scene,scene.s06c_view);return {'FINISHED'}

class S06C_OT_batch(bpy.types.Operator):
    bl_idname='s06c.batch_review';bl_label='Render 12 views + errors'
    def execute(self,context):
        try:
            scene=context.scene
            if not scene.get('s06c_review'):raise ValueError('Open a review scene first.')
            path=Path(bpy.path.abspath(scene.s06c_review_dir))
            report=review.batch_review(context,scene,path);self.report({'INFO'},f'Saved 12 views; mean silhouette IoU {report["mean_silhouette_iou"]:.3f}');return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_display(bpy.types.Operator):
    bl_idname='s06c.review_display';bl_label='Review visibility'
    mode:StringProperty(default='BOTH')
    def execute(self,context):
        scene=context.scene
        if not scene.get('s06c_review'):return {'CANCELLED'}
        ob=bpy.data.objects[scene['s06c_generated']];ref=bpy.data.objects[scene['s06c_reference_snapshot']]
        ob.hide_set(self.mode=='REFERENCE');ref.hide_set(self.mode=='GENERATED')
        for m in ob.modifiers:
            guide=m.target if m.type=='SURFACE_DEFORM' else m.object if m.type=='LATTICE' else None
            if guide:guide.hide_set(True)
        return {'FINISHED'}

class S06C_PT_tools(bpy.types.Panel):
    bl_label='TressIR 0.1';bl_idname='S06C_PT_tools';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Hair Tools'
    def draw(self,context):
        l=self.layout;s=context.scene;ob=hair_object(context)
        box=l.box();box.label(text='LLM image trace');box.operator('s06c.prepare_trace');box.prop(s,'s06c_trace_file')
        box.operator('s06c.preview_trace');box.operator('s06c.open_trace_review');box.prop(s,'s06c_trace_candidate');box.operator('s06c.generate_trace')
        row=l.row();row.operator('s06c.import_profile');row.operator('s06c.export_profile')
        if ob:
            try:p=ops.get_profile(ob)
            except (ValueError,KeyError) as e:l.label(text=str(e),icon='ERROR');return
            l.label(text=ob.name);box=l.box()
            box.enabled=context.mode=='OBJECT'
            if p['schema']==clump.SCHEMA:
                box.prop(s,'s06c_control');box.operator('s06c.read_control')
                box.label(text='Center offsets (mm)')
                row=box.row(align=True);row.prop(s,'s06c_dx');row.prop(s,'s06c_dy');row.prop(s,'s06c_dz')
                box.prop(s,'s06c_scale_a');box.prop(s,'s06c_scale_b');box.prop(s,'s06c_angle')
            else:
                if p['design']['ridge_guides']:box.prop(s,'s06c_ridge');box.prop(s,'s06c_ridge_height')
                if 'depth_field' not in p:box.prop(s,'s06c_thickness')
                box.operator('s06c.read_control')
                if p['schema']==sheet.SCHEMA:box.operator('s06c.upgrade_sheet')
                if p['schema']==sheet_v4.SCHEMA:
                    box.prop(s,'s06c_fit_controls');box.prop(s,'s06c_fit_smoothing');box.operator('s06c.fit_sheet_depth')
                    if 'depth_field' in p:
                        d=box.box();d.label(text='Compact depth field');d.prop(s,'s06c_field_index')
                        d.prop(s,'s06c_field_x');d.prop(s,'s06c_field_y');d.prop(s,'s06c_field_half');d.prop(s,'s06c_field_angle');d.operator('s06c.apply_depth_control')
            box.operator('s06c.apply_control');box.operator('s06c.rebuild')
            row=l.row();row.operator('s06c.add_surface_guide');row.operator('s06c.add_lattice')
            l.label(text='Edit the orange guide in Edit Mode.')
            l.label(text='Move the HANDLE to place the whole part.')
            production_box=l.box();production_box.label(text='Production assets')
            production_box.prop(s,'s06c_project_dir');production_box.prop(s,'s06c_part_id');production_box.prop(s,'s06c_checkpoint')
            production_box.label(text='State: '+ob.get('s06c_lifecycle','untracked'))
            row=production_box.row();row.operator('s06c.quality');row.operator('s06c.accept_part')
            production_box.operator('s06c.discard_candidate')
        if not ob and context.active_object and context.active_object.type=='MESH':l.operator('s06c.quality')
        l.prop(s,'s06c_project_dir');l.operator('s06c.restore_active');l.operator('s06c.check_depth_order')
        l.separator();l.prop(s,'s06c_reference');l.operator('s06c.fit_reference');l.operator('s06c.make_review')
        if s.get('s06c_review'):
            row=l.row(align=True)
            for mode,label in [('REFERENCE','Reference'),('GENERATED','Generated'),('BOTH','Overlay')]:row.operator('s06c.review_display',text=label).mode=mode
            l.label(text='Camera: '+review.VIEWS[s.s06c_view%len(review.VIEWS)][0]);l.operator('s06c.next_view')
            l.prop(s,'s06c_review_dir');l.operator('s06c.batch_review')

def project_path(context):return Path(bpy.path.abspath(context.scene.s06c_project_dir)).resolve()

class S06C_OT_upgrade(bpy.types.Operator):
    bl_idname='s06c.upgrade_sheet';bl_label='New v4 sheet candidate';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            source=hair_object(context);p=sheet_v4.upgrade(ops.export_profile(source))
            ob=production.build_candidate(context,p,source.get('s06c_part_id') or context.scene.s06c_part_id,project_path(context));activate(context,ob);read_control(None,context);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_sheet_depth(bpy.types.Operator):
    bl_idname='s06c.fit_sheet_depth';bl_label='Fit depth from reference';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            ob=hair_object(context);ref=context.scene.s06c_reference
            if not ref or ref==ob:raise ValueError('Select a separate reference mesh.')
            ops.fit_sheet_depth(context,ob,ref,context.scene.s06c_fit_controls,context.scene.s06c_fit_smoothing);read_control(None,context);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_depth_control(bpy.types.Operator):
    bl_idname='s06c.apply_depth_control';bl_label='Apply depth control';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            ob=hair_object(context);p=ops.get_profile(ob);s=context.scene
            p['depth_field']=fields.set_control(p['depth_field'],s.s06c_field_index,{'center_x_m':s.s06c_field_x/1000,'center_y_m':s.s06c_field_y/1000,'half_depth_m':s.s06c_field_half/1000,'rotation_rad':math.radians(s.s06c_field_angle)})
            p.setdefault('history',[]).append({'operation':'direct_depth_control_edit','index':s.s06c_field_index})
            ops.rebuild(context,ob,p);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_quality(bpy.types.Operator):
    bl_idname='s06c.quality';bl_label='Check mesh quality'
    def execute(self,context):
        try:
            report=ops.object_quality(context,hair_object(context) or context.active_object);tx=bpy.data.texts.get('TRESSIR_QUALITY_REPORT.json') or bpy.data.texts.new('TRESSIR_QUALITY_REPORT.json')
            tx.clear();tx.write(json.dumps(report,indent=2));tx.use_fake_user=True
            self.report({'INFO'},'Mesh validity: '+('PASS' if report['valid'] else ', '.join(report['blocking']))+'; full report in TRESSIR_QUALITY_REPORT.json');return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_accept(bpy.types.Operator):
    bl_idname='s06c.accept_part';bl_label='Accept + save parameters'
    def execute(self,context):
        try:
            ob=hair_object(context);result=production.accept(context,ob,project_path(context),ob.get('s06c_part_id') or context.scene.s06c_part_id,context.scene.s06c_checkpoint)
            message='Accepted '+result['part_id']+'; parameters and active manifest saved.'
            if result.get('checkpoint_error'):message+=' Checkpoint failed: '+result['checkpoint_error']
            self.report({'WARNING'} if result.get('checkpoint_error') else {'INFO'},message);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_restore(bpy.types.Operator):
    bl_idname='s06c.restore_active';bl_label='Restore active hair from JSON'
    def execute(self,context):
        try:
            result=production.restore(context,project_path(context));self.report({'INFO'},'Restored '+str(result['restored_parts'])+' active parts.');return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_depth_order(bpy.types.Operator):
    bl_idname='s06c.check_depth_order';bl_label='Check depth order'
    def execute(self,context):
        try:
            result=production.check_depth_order(context,project_path(context));tx=bpy.data.texts.get('TRESSIR_DEPTH_ORDER.json') or bpy.data.texts.new('TRESSIR_DEPTH_ORDER.json')
            tx.clear();tx.write(json.dumps(result,indent=2));tx.use_fake_user=True
            self.report({'INFO'},'Checked '+str(len(result))+' declared relations; '+str(sum(x['violations'] for x in result))+' sampled violations.');return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_discard(bpy.types.Operator):
    bl_idname='s06c.discard_candidate';bl_label='Discard selected candidate';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:production.discard_candidate(context,hair_object(context));return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_trace_prepare(bpy.types.Operator,ImportHelper):
    bl_idname='s06c.prepare_trace';bl_label='Prepare reference for LLM'
    filter_glob:StringProperty(default='*.png;*.jpg;*.jpeg',options={'HIDDEN'})
    def execute(self,context):
        try:
            import hashlib
            source=Path(self.filepath);part=context.scene.s06c_part_id
            production._id(part)
            out=project_path(context)/'traces'/(part+'-'+hashlib.sha256(source.read_bytes()).hexdigest()[:10])
            result=trace.prepare(source,out,part);context.scene.s06c_trace_file=result['trace'];context.scene.s06c_trace_manifest=''
            self.report({'INFO'},'Prepared trace.json and coordinate-grid.png in '+str(out));return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_trace_preview(bpy.types.Operator):
    bl_idname='s06c.preview_trace';bl_label='Preview LLM contour'
    def execute(self,context):
        try:
            result=trace.preview(bpy.path.abspath(context.scene.s06c_trace_file));context.scene.s06c_trace_manifest=result['manifest']
            context.scene.s06c_trace_candidate=result['candidates'][0]
            self.report({'INFO'},'Review ready: '+result['html']);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_trace_open(bpy.types.Operator):
    bl_idname='s06c.open_trace_review';bl_label='Open contour review'
    def execute(self,context):
        try:
            import webbrowser
            path=Path(bpy.path.abspath(context.scene.s06c_trace_manifest)).parent/'review.html'
            if not path.is_file():raise ValueError('Generate a contour preview first.')
            webbrowser.open(path.resolve().as_uri());return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

class S06C_OT_trace_generate(bpy.types.Operator):
    bl_idname='s06c.generate_trace';bl_label='Generate reviewed candidate';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            s=context.scene;obj=trace.generate(context,bpy.path.abspath(s.s06c_trace_manifest),s.s06c_trace_candidate,project_path(context))
            activate(context,obj);read_control(None,context);return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}

CLASSES=(S06C_OT_import,S06C_OT_export,S06C_OT_read,S06C_OT_apply,S06C_OT_rebuild,S06C_OT_surface,S06C_OT_lattice,S06C_OT_fit,S06C_OT_review,S06C_OT_next_view,S06C_OT_batch,S06C_OT_display,S06C_OT_upgrade,S06C_OT_sheet_depth,S06C_OT_depth_control,S06C_OT_quality,S06C_OT_accept,S06C_OT_restore,S06C_OT_depth_order,S06C_OT_discard,S06C_OT_trace_prepare,S06C_OT_trace_preview,S06C_OT_trace_open,S06C_OT_trace_generate,S06C_PT_tools)
PROPS={
's06c_trace_file':StringProperty(name='LLM trace JSON',subtype='FILE_PATH'),
's06c_trace_manifest':StringProperty(name='Reviewed manifest',subtype='FILE_PATH'),
's06c_trace_candidate':StringProperty(name='Candidate ID',default='A'),
's06c_project_dir':StringProperty(name='Project folder',default='//TressIR-production'),
's06c_part_id':StringProperty(name='Part ID for new candidate',default='PART01'),
's06c_checkpoint':BoolProperty(name='Save blend checkpoint on acceptance',default=True),
's06c_fit_controls':IntProperty(name='Depth coefficients',default=18,min=4,max=64),
's06c_fit_smoothing':FloatProperty(name='Depth regularization',default=.00001,min=0,max=.01,precision=6),
's06c_field_index':IntProperty(name='Depth control index',default=8,min=0,max=63,update=read_control),
's06c_field_x':FloatProperty(name='Section center X (mm)'),
's06c_field_y':FloatProperty(name='Section center Y (mm)'),
's06c_field_half':FloatProperty(name='Body half-depth (mm)',default=1,min=.001,max=1000),
's06c_field_angle':FloatProperty(name='Section tilt (degrees)'),
's06c_reference':PointerProperty(name='Reference mesh',type=bpy.types.Object),
's06c_control':IntProperty(name='Control 0-11',min=0,max=11,default=5,update=read_control),
's06c_dx':FloatProperty(name='X',default=0),'s06c_dy':FloatProperty(name='Y',default=0),'s06c_dz':FloatProperty(name='Z',default=0),
's06c_scale_a':FloatProperty(name='Section axis A scale',default=1,min=.05,max=8),
's06c_scale_b':FloatProperty(name='Section axis B scale',default=1,min=.05,max=8),
's06c_angle':FloatProperty(name='Section rotation offset (deg)',default=0,min=-180,max=180),
's06c_ridge':IntProperty(name='Ridge index',min=0,max=63,default=1,update=read_control),
's06c_ridge_height':FloatProperty(name='Ridge height (mm)',default=3,min=0,max=20),
's06c_thickness':FloatProperty(name='Base thickness (mm)',default=.9,min=.05,max=10),
's06c_review_dir':StringProperty(name='Review output',default='//reviews'),
's06c_view':IntProperty(default=0,min=0,max=11)}

def register():
    for cls in CLASSES:
        if getattr(cls,'is_registered',False):bpy.utils.unregister_class(cls)
        existing=getattr(bpy.types,cls.__name__,None)
        if existing:bpy.utils.unregister_class(existing)
        bpy.utils.register_class(cls)
    for name,prop in PROPS.items():setattr(bpy.types.Scene,name,prop)
    structure_ui.register()

def unregister():
    structure_ui.unregister()
    for name in PROPS:
        if hasattr(bpy.types.Scene,name):delattr(bpy.types.Scene,name)
    for cls in reversed(CLASSES):
        if getattr(cls,'is_registered',False):bpy.utils.unregister_class(cls)
