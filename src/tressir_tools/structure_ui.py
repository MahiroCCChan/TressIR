"""Blender panel for explicit multi-part image structures."""
from pathlib import Path
import json
import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper
from . import structure, production, blender_ops


class S06C_OT_structure_prepare(bpy.types.Operator,ImportHelper):
    bl_idname='s06c.structure_prepare';bl_label='Prepare structured reference'
    filter_glob:StringProperty(default='*.png;*.jpg;*.jpeg',options={'HIDDEN'})
    def execute(self,context):
        try:
            source=Path(self.filepath).resolve();s=context.scene
            group=production._id(s.s06c_part_id)
            out=Path(bpy.path.abspath(s.s06c_project_dir)).resolve()/'structures'/(group+'_'+structure.trace._sha(source)[:10])
            prepared=structure.prepare(source,out,group)
            s['s06c_structure_input']=prepared['structure']
            self.report({'INFO'},'Fill '+prepared['structure']+'; then Preview structure JSON.')
            return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}


class S06C_OT_structure_preview(bpy.types.Operator,ImportHelper):
    bl_idname='s06c.structure_preview'
    bl_label='Preview structure JSON'
    filename_ext='.json'
    filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:
            result=structure.preview(self.filepath)
            context.scene.s06c_structure_manifest_path=result['manifest']
            context.scene['s06c_structure_preview_result']=json.dumps(result)
            self.report({'INFO'} if result['ready_to_generate'] else {'WARNING'},
                        'Structure preview saved. '+('Depth checks passed.' if result['ready_to_generate'] else 'Inspect failed overlap checks before generation.'))
            return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}


class S06C_OT_structure_open(bpy.types.Operator):
    bl_idname='s06c.structure_open'
    bl_label='Open structure overlay'
    def execute(self,context):
        try:
            path=Path(bpy.path.abspath(context.scene.s06c_structure_manifest_path)).parent/'structure-review.png'
            if not path.is_file():raise ValueError('Preview the structure first.')
            bpy.ops.wm.path_open(filepath=str(path))
            return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}


class S06C_OT_structure_generate(bpy.types.Operator):
    bl_idname='s06c.structure_generate'
    bl_label='Generate all structure parts'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            s=context.scene
            result=structure.generate(context,bpy.path.abspath(s.s06c_structure_manifest_path),
                                      Path(bpy.path.abspath(s.s06c_project_dir)).resolve())
            for obj in context.selected_objects:obj.select_set(False)
            for name in result['objects'].values():bpy.data.objects[name].select_set(True)
            context.view_layer.objects.active=bpy.data.objects[list(result['objects'].values())[-1]]
            s['s06c_structure_last_generation']=json.dumps(result)
            self.report({'INFO'},str(len(result['objects']))+' independent candidates created; existing objects preserved.')
            return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}


class S06C_OT_structure_check(bpy.types.Operator):
    bl_idname='s06c.structure_check'
    bl_label='Check current group overlaps'
    def execute(self,context):
        try:
            active=context.active_object
            if not active:raise ValueError('Select a part mesh in the generated structure group.')
            if active.get('s06c_structure_instance'):
                instance=active['s06c_structure_instance']
                members=[o for o in context.scene.objects if o.get('s06c_structure_instance')==instance]
            else:
                p=blender_ops.get_profile(active);group=p.get('structure',{}).get('id')
                if not group:raise ValueError('Select a structure part mesh.')
                members=[]
                for o in context.scene.objects:
                    if blender_ops.PROFILE_KEY in o and o.get('s06c_project_id')==active.get('s06c_project_id') and o.get('s06c_lifecycle')==active.get('s06c_lifecycle'):
                        if blender_ops.get_profile(o).get('structure',{}).get('id')==group:members.append(o)
            objects={o['s06c_part_id']:o for o in members}
            if len(objects)!=len(members):raise ValueError('Multiple versions of the same part are visible; select a single current group.')
            report=structure.check_current(context,objects)
            tx=bpy.data.texts.get('TRESSIR_STRUCTURE_CHECK.json') or bpy.data.texts.new('TRESSIR_STRUCTURE_CHECK.json')
            tx.clear();tx.write(json.dumps(report,indent=2));tx.use_fake_user=True
            passed=all(r['passed'] for r in report)
            self.report({'INFO'} if passed else {'WARNING'},'Sampled overlaps: '+('PASS' if passed else 'CHECK REQUIRED')+'; see TRESSIR_STRUCTURE_CHECK.json')
            return {'FINISHED'}
        except Exception as e:self.report({'ERROR'},str(e));return {'CANCELLED'}


class S06C_PT_structure(bpy.types.Panel):
    bl_label='Image structure - multiple parts'
    bl_idname='S06C_PT_structure'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Hair Tools'
    def draw(self,context):
        l=self.layout;s=context.scene
        l.label(text='Shared scale, explicit depth, separate parts')
        l.prop(s,'s06c_part_id',text='New group ID')
        l.operator('s06c.structure_prepare')
        l.operator('s06c.structure_preview')
        l.prop(s,'s06c_structure_manifest_path')
        l.operator('s06c.structure_open')
        l.prop(s,'s06c_project_dir')
        l.operator('s06c.structure_generate')
        l.operator('s06c.structure_check')
        l.label(text='Edit/save each part in the main Hair Tools panel.')


CLASSES=(S06C_OT_structure_prepare,S06C_OT_structure_preview,S06C_OT_structure_open,S06C_OT_structure_generate,S06C_OT_structure_check,S06C_PT_structure)


def register():
    for cls in CLASSES:
        if getattr(cls,'is_registered',False):bpy.utils.unregister_class(cls)
        bpy.utils.register_class(cls)
    bpy.types.Scene.s06c_structure_manifest_path=StringProperty(name='Structure manifest',subtype='FILE_PATH')


def unregister():
    if hasattr(bpy.types.Scene,'s06c_structure_manifest_path'):del bpy.types.Scene.s06c_structure_manifest_path
    for cls in reversed(CLASSES):
        if getattr(cls,'is_registered',False):bpy.utils.unregister_class(cls)
