bl_info = {
    "name": "Ivy Generator (Extended)",
    "author": "Multiple Authors",
    "version": (0, 3, 0),
    "blender": (2, 74, 5),
    "location": "View3D > Add > Curve > Ivy Generator",
    "description": "Add ivy",
    "warning": "",
    "wiki_url": "",
    "category": "Add Curve",
}

if "bpy" in locals():
    import importlib
    importlib.reload(add_curve_ivygen)
    importlib.reload(curve_add_leafs)
    importlib.reload(curve_ivy_animated)
    importlib.reload(mesh_add_leaf)
    importlib.reload(add_library_object)
else:
    from . import add_curve_ivygen
    from . import curve_add_leafs
    from . import curve_ivy_animated
    from . import mesh_add_leaf
    from . import add_library_object

import bpy, os

class INFO_MT_ivy_generator_menu(bpy.types.Menu):
    '''A Collection of tools for Ivys'''
    bl_idname = "INFO_MT_ivy_generator_menu"
    bl_label = "Ivy Generator"

    def draw(self, context):
        pcoll = preview_collections["main"]
        layout = self.layout
        col = layout.column()

        ivy_gen_icon = pcoll['ivy_gen']
        col.operator('curve.ivy_gen',
            text="Add Ivy to Mesh",
            icon_value=ivy_gen_icon.icon_id,).updateIvy = True

        ivy_anim_icon = pcoll["ivy_anim"]
        col.operator('curve.add_animated_ivy',
            icon_value=ivy_anim_icon.icon_id,)

        ivy_curve_leafs_icon = pcoll['ivy_curve_leafs']
        col.operator('curve.add_leafs',
            icon_value=ivy_curve_leafs_icon.icon_id,)

        ivy_leaf_icon = pcoll['ivy_leaf']
        #col.operator('object.create_leaf',
        #    icon_value=ivy_leaf_icon.icon_id)

        col.menu('Object_library_add',
            icon_value=ivy_leaf_icon.icon_id)


def menu_func(self, context):
    pcoll = preview_collections["main"]
    ivy_addon_icon = pcoll['ivy_addon']
    self.layout.menu('INFO_MT_ivy_generator_menu',
            icon_value=ivy_addon_icon.icon_id)

preview_collections = {}

def register():
    #register sub-scripts
    add_curve_ivygen.register()
    curve_ivy_animated.register()
    curve_add_leafs.register()
    mesh_add_leaf.register()
    add_library_object.register()

    #load custom icons
    import bpy.utils.previews
    pcoll = bpy.utils.previews.new()
    my_icons_dir = os.path.join(os.path.dirname(__file__), "icons")
    pcoll.load("ivy_addon", os.path.join(my_icons_dir, "ivy_addon.png"), 'IMAGE')
    pcoll.load("ivy_gen", os.path.join(my_icons_dir, "ivy_gen.png"), 'IMAGE')
    pcoll.load("ivy_anim", os.path.join(my_icons_dir, "ivy_anim.png"), 'IMAGE')
    pcoll.load("ivy_curve_leafs", os.path.join(my_icons_dir, "ivy_curve_leafs.png"), 'IMAGE')
    pcoll.load("ivy_leaf", os.path.join(my_icons_dir, "ivy_leaf.png"), 'IMAGE')
    preview_collections["main"] = pcoll

    #register this files UI
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_curve_add.prepend(menu_func)


def unregister():
    #un-register sub-scripts
    add_curve_ivygen.unregister()
    curve_ivy_animated.unregister()
    curve_add_leafs.unregister()
    mesh_add_leaf.unregister()
    add_library_object.unregister()

    #delete custom icons
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

    #remove this file
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_mesh_add.remove(menu_func)

if __name__ == "__main__":
    register()
