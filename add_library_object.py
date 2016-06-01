import bpy, os

from bpy.types import Operator, Menu
from bpy.props import StringProperty

def library_search_path():
    try:
        file_path = os.path.join(os.path.dirname(__file__), 'library')
    except:
        file_path = ''

    return file_path

def library_object_cache(context, reload=False):
    object_cache = library_object_cache._object_cache
    if reload:
        object_cache[:] = []
    if object_cache:
        return object_cache

    dirpath = library_search_path()
    for fn in os.listdir(dirpath):
        if fn.endswith(".blend"):
            filepath = os.path.join(dirpath, fn)
            with bpy.data.libraries.load(filepath) as (data_from, data_to):
                for group_name in data_from.groups:
                    if not group_name.startswith('_'):
                        object_cache.append((filepath, group_name))

    return object_cache
library_object_cache._object_cache = []


def library_object_add(context, filepath, group_name):

    with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
        assert(group_name in data_from.groups)
        data_to.groups = [group_name]
    group = data_to.groups[0]

    bpy.ops.object.group_instance_add(group=group_name,
        view_align=False,
        location=(context.scene.cursor_location))

    #bpy.ops.object.duplicates_make_real()


class LibraryAppendObject(Operator):
    """Add a object from a libraray."""
    bl_idname = "scene.library_object_add"
    bl_label = "Add Library Object"
    bl_description = "Add a object from a library file."
    bl_options = {'REGISTER', 'UNDO'}

    filepath = StringProperty(
        subtype='FILE_PATH')
    group_name = StringProperty(
        )

    def execute(self, context):
        library_object_add(context, self.filepath, self.group_name)

        return {'FINISHED'}

    def invoke(self, context, event):
        library_object_add(context, self.filepath, self.group_name)

        return {'FINISHED'}


class Object_library_add(Menu):
    bl_label = "Leafs"

    def draw(self, context):
        layout = self.layout

        dirpath = library_search_path()
        if dirpath == "":
            layout.label("No Libraray path found")
            return

        for filepath, group_name in library_object_cache(context):
            props = layout.operator(LibraryAppendObject.bl_idname,
                                    text=group_name)
            props.filepath = filepath
            props.group_name = group_name

def add_library_button(self, context):
    self.layout.menu(
        Object_library_add.__name__,
        text="Template",
        icon="PLUGIN")

def register():
    bpy.utils.register_class(LibraryAppendObject)
    bpy.utils.register_class(Object_library_add)

def unregister():
    bpy.utils.unregister_class(LibraryAppendObject)
    bpy.utils.unregister_class(Object_library_add)
