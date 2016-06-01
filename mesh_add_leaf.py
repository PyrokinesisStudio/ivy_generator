bl_info = {
    "name": "Leaf Generator",
    "author": "Florian Felix Meyer (tstscr)",
    "version": (0, 1),
    "blender": (2, 6, 3),
    "location": "",
    "description": "",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "User"}
###########################################################################
import bpy, bmesh, os
from bpy_extras import image_utils
from bpy.props import *
from bpy.types import Operator
###########################################################################
_DEBUG = False
def printd(*args):
    if _DEBUG: print(*args)
###########################################################################
def del_nodes(node_tree):
    for node in node_tree.nodes:
        node_tree.nodes.remove(node)
    
def create_simple_leaf_material(self, context):
    texture_path = os.path.join(os.path.dirname(__file__), 'textures/Leaf_Texture.png')
    
    img = image_utils.load_image(texture_path)

    mat = bpy.data.materials.new(name='Simple Leaf Material')
    mat.game_settings.alpha_blend = 'ALPHA_ANTIALIASING'
    mat.use_nodes = True
    tree = mat.node_tree
    del_nodes(tree)

    frame1 = tree.nodes.new('NodeFrame')
    frame2 = tree.nodes.new('NodeFrame')
    frame3 = tree.nodes.new('NodeFrame')

    out = tree.nodes.new('ShaderNodeOutputMaterial')
    out.location = (300, 320)
    tex = tree.nodes.new('ShaderNodeTexImage')
    tex.location = (-1750, 320)
    tex.image = img
    
    mix1 = tree.nodes.new('ShaderNodeMixShader')
    mix1.location = (-40, 320)
    mix1.parent = frame3
    transp = tree.nodes.new('ShaderNodeBsdfTransparent')
    transp.location = (-300, 275)
    transp.parent = frame3
    
    info = tree.nodes.new('ShaderNodeObjectInfo')
    info.location = (-1750, 600)
    info.parent = frame1
    mathmult = tree.nodes.new('ShaderNodeMath')
    mathmult.location = (-1500, 600)
    mathmult.operation = 'MULTIPLY'
    mathmult.inputs[1].default_value = 0.1
    mathmult.parent = frame1
    mathadd = tree.nodes.new('ShaderNodeMath')
    mathadd.location = (-1250, 600)
    mathadd.inputs[1].default_value = 0.4
    mathadd.parent = frame1
    hsv = tree.nodes.new('ShaderNodeHueSaturation')
    hsv.location = (-1000, 600)
    hsv.parent = frame1
    
    add1 = tree.nodes.new('ShaderNodeAddShader')
    add1.location = (-300, 100)
    add1.parent = frame2
    diff = tree.nodes.new('ShaderNodeBsdfDiffuse')
    diff.location = (-600, 100)
    diff.parent = frame2
    transl = tree.nodes.new('ShaderNodeBsdfTranslucent')
    transl.location = (-600, -50)
    transl.parent = frame2
    


    #random chain
    tree.links.new(info.outputs['Random'], mathmult.inputs[0])
    tree.links.new(mathmult.outputs['Value'], mathadd.inputs[0])
    tree.links.new(mathadd.outputs['Value'], hsv.inputs[0])
    tree.links.new(tex.outputs['Color'], hsv.inputs['Color'])

    #hsv to shaders
    tree.links.new(hsv.outputs['Color'], diff.inputs['Color'])
    tree.links.new(hsv.outputs['Color'], transl.inputs['Color'])

    #alpha to mix
    tree.links.new(tex.outputs['Alpha'], mix1.inputs['Fac'])

    #shaders to addshader
    tree.links.new(transl.outputs['BSDF'], add1.inputs[1])
    tree.links.new(diff.outputs['BSDF'], add1.inputs[0])
    
    tree.links.new(transp.outputs['BSDF'], mix1.inputs[1])
    tree.links.new(add1.outputs['Shader'], mix1.inputs[2])
    
    tree.links.new(mix1.outputs['Shader'], out.inputs['Surface'])

    return mat


def create_leaf_plane(self, context):
    bpy.ops.mesh.primitive_plane_add(radius=self.size*0.5)
    ob = context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.uv.unwrap()
    bpy.ops.object.mode_set(mode='OBJECT')
    me = ob.data
    bm = bmesh.new()
    bm.from_object(ob, context.scene)
    bm.verts.ensure_lookup_table()
    y_offset = -bm.verts[0].co.y
    for v in bm.verts:
        v.co.y += y_offset
    bm.to_mesh(ob.data)
    bm.free()
    
    if not 'Simple Leaf Material' in bpy.data.materials:
        material = create_simple_leaf_material(self, context)
    else:
        material = bpy.data.materials['Simple Leaf Material']
    
    bpy.ops.object.material_slot_add()
    ob.material_slots[0].material = material

    ob.name = ob.data.name = 'leaf'

def create_new_leaf(self,context):
    if self.leaf_type == 'PLANE':
        create_leaf_plane(self, context)

class CreateLeafMesh(Operator):
    """Add a Mesh Leaf.
If used for the ivy make sure to add the leaf to
a group (named \"leaf\")
and to correctly set the group offset."""
    bl_idname = "object.create_leaf"
    bl_label = "Add Leaf"
    bl_options = {'REGISTER', 'UNDO'}
    
    leaf_type = EnumProperty(
        name='Leaf Type',
        items=[
        ('PLANE', 'simple Plane', ''),
        ('HP_1', 'high Poly 1', ''),
        ],
        default='PLANE',
        options={'HIDDEN'}
        )
    
    size = FloatProperty(
    name='Size',
    default=0.1,
    )
    
    ##### POLL #####
    @classmethod
    def poll(cls, context):
        return context
    
    ##### EXECUTE #####
    def execute(self, context):
        create_new_leaf(self,context)
        return {'FINISHED'}

    def invoke(self, context, event):
        self.execute(context)
        #wm = context.window_manager
        #wm.invoke_props_dialog(self, 300)
        return {'RUNNING_MODAL'}





###########################################################################
def register():
    #bpy.utils.register_module(__name__)
    bpy.utils.register_class(CreateLeafMesh)
    
def unregister():
    #bpy.utils.unregister_module(__name__)
    bpy.utils.unregister_class(CreateLeafMesh)

if __name__ == "__main__":
    register()
