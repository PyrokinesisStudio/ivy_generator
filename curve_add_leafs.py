bl_info = {
    "name": "Add Leafs along Curve",
    "author": "Florian Felix Meyer (tstscr)",
    "version": (1, 0),
    "blender": (2, 76, 2),
    "location": "View3D > Add > Curve > Add Leaves",
    "description": "Add Leafs along Curve",
    "warning": "",
    "wiki_url": "",
    "category": "User",
    }
###########################################################
import bpy, bmesh, time
import asyncio as aio
from concurrent.futures import ProcessPoolExecutor
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, EnumProperty, StringProperty, IntProperty, FloatProperty, PointerProperty, FloatVectorProperty
from mathutils import Vector, Matrix, Euler, noise
from mathutils.bvhtree import BVHTree
from mathutils.geometry import distance_point_to_plane, interpolate_bezier
from random import random, seed
###########################################################
_DEBUG = False
def printd(*args):
    if _DEBUG: print(*args)
###########################################################
def aio_get_loop():
    loop = aio.new_event_loop()
    aio.set_event_loop(loop)
    loop = aio.get_event_loop()
    return loop

###########################################################

###########################################################################

#crossvecs not used atm
def crossvecs(coords):
    crossvecs = []
    #generate crossvecs left - right if possible
    if len(coords) > 2:
        for i, co in enumerate(coords):
            if i == 0: #first co
                co1 = co - coords[i+1]
                co2 = coords[i+2] - coords[i+1]
                cross = co1.cross(co2)
            elif i == len(coords)-1: #last co
                co1 = coords[i-2] - coords[i-1]
                co2 = co - coords[i-1]
                cross = co1.cross(co2)
            else: #middle co
                co1 = coords[i-1] - co
                co2 = coords[i+1] - co
                cross = co1.cross(co2)
            crossvecs.append(cross)
    return crossvecs

def rvec():
    #return random_unit_vector()
    return Vector((random()-.5, random()-.5, random()-.5)).normalized()

def axisangle(v1,v2):
    if v1.length == 0 or v2.length == 0: return None
    axis = v1.cross(v2).normalized()
    angle = v1.angle(v2)
    return axis, angle

def get_axis_aligned_bm(mat):
    '''
    helper bmesh object
    with unit-verts at the positive axis
    '''
    bm = bmesh.new()
    axisco = [Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1))]
    [bm.verts.new(co) for co in axisco]
    bm.transform(mat.to_4x4())
    bm.verts.ensure_lookup_table()
    return bm

#### BRUTE FORCE  --> BETTER IDEAS SOMEONE?
def align(aligny=Vector((0,1,0)), alignz=Vector((0,0,1))):
    '''
    Get a Rotation Matrix.
    The Matrix Local +Y Axis gets aligned with aligny.
    The +Z Local Axis gets aligned with alignz as best as possible,
    without disturbing the Y alignment.
    This implementation looks a little brutish to the Coders eyes.
    Better ideas are very welcome.
    '''
    X=Vector((1,0,0))
    Y=Vector((0,1,0))
    Z=Vector((0,0,1))
    if alignz.length == 0:
        alignz = Z.copy()
    mat = Matrix().to_3x3()
    #Align local-Y axis with aligny
    axis, angle = axisangle(Y, aligny)
    if axis.length == 0:
        axis = X
    rot_to_y = Matrix.Rotation(angle,3,axis)
    bm1 = get_axis_aligned_bm(rot_to_y)
    #Align local-Z with projected alignz
    eul = rot_to_y.to_euler()
    target_localx = aligny.cross(alignz).normalized()
    target_localz = target_localx.cross(aligny).normalized()
    angle = target_localz.angle(bm1.verts[2].co)
    ### NEED SOME TEST FOR ANGLE FLIPPING
    eul.rotate_axis('Y', angle)
    mat = eul.to_matrix().to_4x4()
    ### Test if rotation is good
    bmf = get_axis_aligned_bm(mat)
    dist = distance_point_to_plane(bmf.verts[2].co, target_localz, target_localz.cross(alignz))
    error = 1e-06
    ### Flip the angle
    if abs(dist)>error:
        eul = rot_to_y.to_euler()
        eul.rotate_axis('Y', -angle)
        mat = eul.to_matrix().to_4x4()
    bm1.free()
    bmf.free()
    return mat.to_4x4()
###########################################################

### ADD ANIMATION
def add_dupli_animation(self, context, duplis):
    '''
    This gets the duplis of one spline
    and adds the scaling animation.
    '''
    #printd('Adding Animation to %d Leave duplis' %len(duplis))

    num_duplis = len(duplis)
    anim_range = self.end - self.start

    for i, dupli in enumerate(duplis):
        start = int((i / num_duplis) * anim_range) + self.start + self.start_offset

        dupli.keyframe_insert('delta_scale', frame = start)
        dupli.keyframe_insert('delta_scale', frame = start + self.duration)
        action = dupli.animation_data.action

        for fcurve in action.fcurves:
            fcurve.keyframe_points[0].co.y = 0
            fcurve.update()

### CREATE DUPLIS
def create_leaf_duplis(self, context, mats):
    '''
    For the incoming Matrizies dupli objects are created
    and added to the scene.
    If multiple groups are given a random one is chosen.
    '''
    #printd('Creating %d Leaf duplis' %len(mats))
    duplis = []
    new = bpy.data.objects.new

    def select_dupli_group():
        numgroups = len(self.dupli_groups)
        if numgroups == 1:
            return self.dupli_groups[-1]
        elif numgroups > 1:
            #choose random
            pick = int(random() * numgroups)
            return self.dupli_groups[pick]
        else:
            return None

    def new_dupli():
        dupli_g = select_dupli_group()
        if dupli_g:
            dupli = new(dupli_g.name+'_dupli', None)
            #dupli.leaf.is_leaf = True
            dupli.dupli_group = dupli_g
            dupli.empty_draw_type = 'ARROWS'
            dupli.empty_draw_size = 0.01
            dupli.dupli_type = 'GROUP'
            context.scene.objects.link(dupli)
            dupli.select = True
        return dupli

    #Parent Empty for the duplis
    parent = new('dupli_parent', None)
    parent.empty_draw_type = 'ARROWS'
    parent.empty_draw_size = 0.1
    context.scene.objects.link(parent)
    parent.select = True
    parent.matrix_world = self.curve.matrix_world

    for mat in mats:
        dupli = new_dupli()
        dupli.matrix_world = mat
        dupli.parent = parent
        duplis.append(dupli)

    return duplis

### COLLIDER ALIGNED ROTATIONS
def get_collider_aligned_rots(self, context, coords, directions):
    '''
    Takes the location coordinates and the
    corresponding direction vectors.
    Creates a left and a right rotation Matrix
    aligned to the surface of the collider Mesh.
    '''
    mat_rots = []
    for co, direction in zip(coords, directions):
        hit, normal, face, distance = self.bvh.find_nearest(co)
        vec_left = -direction.cross(normal).normalized()
        vec_right = direction.cross(normal).normalized()

        vec_left = direction.lerp(vec_left, self.rot_align_left_right).normalized()
        vec_right = direction.lerp(vec_right, self.rot_align_left_right).normalized()

        vec_left = vec_left.lerp(normal, self.rot_align_normal).normalized()
        vec_right = vec_right.lerp(normal, self.rot_align_normal).normalized()

        vec_left += noise.random_unit_vector() * self.rot_random
        vec_right += noise.random_unit_vector() * self.rot_random

        mat_left = align(vec_left, normal)
        mat_right = align(vec_right, normal)

        mat_rots.extend([mat_left, mat_right])

    return mat_rots

### COLLECT MATRIZIES
# the nested coroutine does not work
@aio.coroutine
def aio_get_mats_for_segment(self, context, segment, splinetype):
    mats = get_mats_for_segment(self, context, segment, splinetype)
    return mats

def get_mats_for_segment(self, context, segment, splinetype):
    '''
    Creates the Matrizies for a spline segment.
    '''
    #printd('Creating transforms for segment', splinetype)
    mats = []

    p1 = segment[0]
    p2 = segment[1]


    count = self.leafs_per_segment
    if self.bvh:
        count *= 2

    ### TRANSLATION #################
    if splinetype == 'BEZIER':
        coordsb = interpolate_bezier(p1.co, p1.handle_right, p2.handle_left, p2.co, count+1)
        coords = [coordsb[i].lerp(coordsb[i+1], random()*self.loc_random)
                  for i in range(len(coordsb)-1)]

    elif splinetype == 'POLY':
        if count > 1:
            positions = [i / count for i in range(count)]
        else:
            positions = [0.5]
        #printd('POLY-segment: Lerp-positions', positions)
        coords = [p1.co.lerp(p2.co, positions[i]+(random() * self.loc_random)).to_3d()
                  for i in range(count)]

    mat_locs = [Matrix.Translation(co) for co in coords]


    ### SCALE #################
    mat_scales = [Matrix.Scale(self.scale+(random()*self.scale_random), 4)
                  for i in range(len(mat_locs))]

    ### ROTATION #################
    if splinetype == 'BEZIER':
        directions = [(coordsb[i+1] - coordsb[i]).normalized()
                      for i in range(len(coordsb)-1)]
    elif splinetype == 'POLY':
        directions = [(p2.co - p1.co).to_3d().normalized()]*len(coords)

    #COLLISION -> align leaves to surface
    if self.bvh:
        #printd('COLLISION')
        mat_rots = get_collider_aligned_rots(self, context, coords[:int(count/2)], directions)

    #NO COLLISION
    else:
        vecs_target = directions.copy()

        #direction + random for y alignment
        vecs_target = [vt.lerp(vt+noise.random_unit_vector(), self.rot_random).normalized()
                       for vt in vecs_target]

        #up versus random for z alignment
        vecs_alignz = [Vector((0,0,1)).lerp(noise.random_unit_vector(), self.rot_align_normal_random).normalized()
                       for i in range(len(directions))]

        #return alignz towards the direction vector
        vecs_alignz = [va.lerp(d, self.rot_align_normal).normalized()
                       for va, d in zip(vecs_alignz, directions)]

        mat_rots = [align(vt, va) for vt, va in zip(vecs_target, vecs_alignz)]
        #printd('FREE ROTATION Mats:', len(mat_rots))

    #COMBINED
    mats = [l*s*r for l,s,r in zip(mat_locs, mat_scales, mat_rots)]
    mats = [m for m in mats if not random() > self.leafs_per_segment_random]
    #printd('MATS: ', len(mats), len(mat_locs), len(mat_scales), len(mat_rots))
    return mats


### GENERATE MATRIZIES
def get_dupli_transforms(self, context, spline):
    #printd('get_dupli_transforms')
    if spline.points:
        splinetype = 'POLY'
        points = spline.points
    elif spline.bezier_points:
        splinetype = 'BEZIER'
        points = spline.bezier_points

    segments = [[points[i], points[i+1]] for i, p in enumerate(points[:-1])]
    #printd('Gathering transforms', splinetype, len(points), 'Points', '%d Segments' %len(segments))

    mats = []

    for segment in segments:
        segment_mats = get_mats_for_segment(self, context, segment, splinetype)
        mats.extend(segment_mats)

    '''
    #This is 10% slower than the above for loop:
    loop = aio.new_event_loop()
    tasks = [aio.async(aio_get_mats_for_segment(self, context, segment, splinetype), loop=loop)
            for segment in segments]
    matresult = loop.run_until_complete(aio.gather(*tasks))
    loop.close()
    [mats.extend(ms) for ms in matresult]
    '''

    return mats


### ADD DUPLIS PER SPLINE
@aio.coroutine
def aio_add_leafs_to_spline(self, context, spline, i):
    #printd('START: ', i)
    #printd('RETRIEVE TRANSFORMS')
    mats = get_dupli_transforms(self, context, spline)
    #printd('CREATE DUPLIS')
    duplis = create_leaf_duplis(self, context, mats)
    if self.animated:
        #printd('ADD ANIMATION')
        add_dupli_animation(self, context, duplis)
    #printd('SPLINE FINISHED')
    #printd('END:   ', i)
    context.window_manager.progress_update(i)
    return i

### MAIN
def add_leafs_to_curve(self, context):
    '''
    Main.
    Creates asyncio Tasks per spline
    for parallel processing.
    '''
    printd('Adding Leafs to', self.curve.name)
    starttime = time.time()

    splines = self.curve.data.splines
    context.window_manager.progress_begin(0, len(splines))

    loop = aio_get_loop()
    self.loop = loop

    if self.single_branch:
        tasks = [aio.async(aio_add_leafs_to_spline(self, context, splines[0], 0))]
    else:
        tasks = [aio.async(aio_add_leafs_to_spline(self, context, spline, i)) \
                for i, spline in enumerate(splines)]

    if tasks:
        indizies = loop.run_until_complete(aio.gather(*tasks))
        printd('Finished Splines:', indizies)
        loop.close()

    context.window_manager.progress_end()
    printd('TIME', time.time()-starttime)
    self.curve.select = False

### SETUP
def setup_self(self, context):
    '''
    Setup:
    Set needed Values and prepare and store some data.
    '''
    self.curve = context.active_object
    groups = bpy.data.groups
    names = [n.strip() for n in self.leafgroupname.split(',')]
    self.dupli_groups = [groups[n] for n in names
                         if n in groups]

    #printd(self.dupli_groups)
    seed(self.seed)
    noise.seed_set(self.seed)

    #this is only if the scripts are not together in a moduke
    #if 'curve_ivy_animated' in context.user_preferences.addons.keys():
    self.ivy_loaded = True
    #printd('Animated Ivy Addon loaded ok', self.ivy_loaded)
    self.ivyopt = self.curve.ivy
    #else:
    #self.ivy_loaded = False

    ### CHECK FOR COLLIDER
    selected = context.selected_objects
    if len(selected) == 2:
        collider = [ob for ob in selected if ob != self.curve][-1]
        collider.select = False
        if collider.type == 'MESH':
            bm = bmesh.new()
            bm.from_object(collider, context.scene)
            bm.transform(collider.matrix_world)
            bm.transform(self.curve.matrix_world.inverted())
            bvh = BVHTree()
            bvh = bvh.FromBMesh(bm)
            self.bvh = bvh
    else:
        self.bvh = None

    ### TAKE ANIMATION FROM GROWING IVY IF AVAILABLE
    if self.ivy_loaded:
        if self.ivyopt.added_as_ivy: #was indeed intended as growing ivy
            if self.ivyopt.animated:
                print('taking animation from ivy')
                self.animated = self.ivyopt.animated
                self.start = self.ivyopt.start
                self.end = self.ivyopt.end

    #if no leafgroup found create simple leaf
    if not self.dupli_groups:
        pass
        #self.dupli_groups = [create_leaf_plane(context)]

### VALIDITY CHECKS
def check_self(self, context):
    ok = True
    if not self.curve.type == 'CURVE':
        self.report({'WARNING'}, 'Active Object not a Curve: %s' %self.curve.name)
        ok = False
    if len(self.dupli_groups) == 0:
        self.report({'WARNING'}, 'No Groups with matching Names exists')
        ok = False

    printd('CHECK', ok)
    return ok

###########################################################
#ADD LEAVES OPERATOR ######################################
class OBJECT_OT_add_leafes(Operator):
    """Add Leafs to a (active) Curve.
Selected Mesh Object acts as alignment collider.
First create a group (preferably named \'leaf\')
with some objects in it.
If added to an animated Ivy make sure to
add the leafs on the last animation frame."""

    bl_idname = "curve.add_leafs"
    bl_label = "Add Leafs to Curve"
    bl_options = {'REGISTER', 'UNDO', 'PRESET'}


    single_branch = BoolProperty(
        name='Single Branch',
        default=True,
        description='Only create Leafs for a single branch for faster updates.',
        )
    leafgroupname = StringProperty(
        name='Leaf Group Names',
        default='leaf',
        description='Groups to use as Leafs.\n'
                    'Comma separated list of group names.\n'
                    'Does not work if no group is found.\n'
                    'Create a <leaf> group with some leaf objects in it.',
        )
    seed = IntProperty(
        name='Random Seed',
        default=1,
        min=1, soft_min=1,
        description='Seed Value for randomization',
        )
    leafs_per_segment = IntProperty(
        name='Leaves per segment',
        default=1,
        min=1, soft_min=1,
        description='How many Leaves to generate per spline segment. \nDoubled with Collider present: Create Left-Right Leaves.',
        )
    leafs_per_segment_random = FloatProperty(
        name="Leaf Count Random",
        #subtype='FACTOR',
        min=0, max=1,
        default=1,
        description='Chance of leaves on segment',
        )
    scale = FloatProperty(
        name="Leaf Scale",
        min=0.001,
        default=1.0,
        description='Scale factor of duplicated leaves',
        )
    loc_random = FloatProperty(
        name="Location Random Factor",
        min=0,
        default=0,
        description='Random factor for Scale',
        )
    scale_random = FloatProperty(
        name="Scale Random Factor",
        min=0,
        default=1,
        description='Random factor for Scale',
        )
    rot_random = FloatProperty(
        name="Rotation Random Factor",
        min=0,
        default=0.5,
        description='Random factor for Rotation',
        )
    rot_align_left_right = FloatProperty(
        name="Align Left-Right Factor",
        min=0,
        default=0.5,
        description='Factor for Left-Right Alignment',
        )
    rot_align_normal = FloatProperty(
        name="Align to Normal Factor",
        min=0,
        default=0.1,
        description='Factor for Alignment to Normal',
        )
    rot_align_normal_random = FloatProperty(
        name="Align to Normal Random",
        min=0,
        default=0.1,
        description='Random Factor for Alignment to Normal',
        )
    animated = BoolProperty(
        name='Animated',
        default=False,
        description='Add "Animate On" animations.\n'
                    'If the source curve is an animated ivy curve\n'
                    'the animation settings are taken from the ivy settings.\n'
                    'If animation is unwanted for the leafs turn the ivy animation of first.',
        )
    start = IntProperty(
        name='Start Frame',
        default=1,
        min=1, soft_min=0,
        description='Start Frame Animation')
    end = IntProperty(
        name='End Frame',
        default=100,
        min=1, soft_min=0,
        description='End Frame of Animation')
    duration = IntProperty(
        name='Duration',
        default=15,
        min=1, soft_min=0,
        description='Length of Animation.\n'
                            'How long the leafs are\n'
                            'animating on.')
    start_offset = IntProperty(
        name='Offset',
        default=0,
        description='Frame Offset for animation start.\n'
                            'Set positive to delay,\n'
                            'negative to start early.')

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob and ob.type == 'CURVE'

    def execute(self, context):
        printd('\n_______START______')
        setup_self(self, context)
        if not check_self(self, context): return {'CANCELLED'}
        add_leafs_to_curve(self, context)
        printd('\n_______END________')
        return {'FINISHED'}

    def invoke(self, context, event):
        #print('dialog request')
        self.ivyopt = context.active_object.ivy
        if self.ivyopt.added_as_ivy: #was indeed intended as growing ivy
            if self.ivyopt.animated:
                #print('taking animation from ivy')
                self.animated = self.ivyopt.animated
                self.start = self.ivyopt.start
                self.end = self.ivyopt.end
        wm = context.window_manager
        wm.invoke_props_dialog(self, 300)
        return {'RUNNING_MODAL'}
#################################################################
#PER LEAF PROPERTIES ############################################
'''
Not really needed anymore

class LeafProperties(PropertyGroup):
    is_leaf = BoolProperty(
        name='Added as Leaf',
        default=False,
        options={'HIDDEN'},
        description='__internal__')

class LeafPanel(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"
    bl_label = 'Leaf'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob.type == 'EMPTY' and ob.leaf.is_leaf

    def draw(self, context):
        scene = context.scene
        ob = scene.objects.active
        opt = ob.leaf
        layout = self.layout
        col = layout.column()

'''
#################################################################
def add_leafs_button(self, context):
    self.layout.operator(
    OBJECT_OT_add_leafes.bl_idname,
    icon='PARTICLE_POINT'
    )

def register():
    #bpy.utils.register_module(__name__)
    bpy.utils.register_class(OBJECT_OT_add_leafes)


    #bpy.types.INFO_MT_curve_add.prepend(add_leafs_button)
    #bpy.types.Object.leaf = PointerProperty(type=LeafProperties)

def unregister():
    #bpy.utils.unregister_module(__name__)
    bpy.utils.unregister_class(OBJECT_OT_add_leafes)

    #bpy.types.INFO_MT_curve_add.remove(add_leafs_button)
    #del(bpy.types.Object.leaf)

if __name__ == "__main__":
    register()
