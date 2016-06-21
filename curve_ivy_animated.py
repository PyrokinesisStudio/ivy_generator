
###########################################################
import bpy, bmesh
import numpy as np
import asyncio as aio
from bpy.types import Operator, Panel, PropertyGroup
from bpy.props import BoolProperty, EnumProperty, StringProperty, IntProperty, FloatProperty, PointerProperty, FloatVectorProperty
from bpy.app.handlers import persistent
from mathutils import Vector, Matrix, Euler, noise
from mathutils.bvhtree import BVHTree
from mathutils.geometry import distance_point_to_plane
from random import random, seed

#uncomment in update_ivy to avoid endless adding
#dspl = bpy.types.WindowManager.display

###########################################################
_DEBUG = False
def printd(*args):
    if _DEBUG: print(*args)
###########################################################
def update_func(self, context):
    context.scene.frame_set(context.scene.frame_current)

def update_func_endframe(self, context):
    opt = context.active_object.ivy
    if opt.end < opt.start:
        opt.end = opt.start+1
        return
    context.scene.frame_set(context.scene.frame_current)

#this does not work (do not know how to set the value)
def update_on_set(self, value):
    self = value
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)
    return None

def rvec():
    return Vector((random()-.5, random()-.5, random()-.5)).normalized()

def new_spline(splines, coords):
    spline = splines.new('POLY')
    spline.points.add(count=len(coords)-1)
    coords = [co.to_4d() for co in coords]
    array = []
    [array.extend(v) for v in coords]
    spline.points.foreach_set('co', array)
    spline.points[-1].radius = 0
    if len(spline.points) > 1:
        spline.points[-2].radius = 0.5
        if len(spline.points) > 2:
            spline.points[-3].radius = 0.75
    return spline

def create_splines(ivy, coords_list):
    splines = ivy.data.splines
    splines.clear()

    for coords in coords_list:
        new_spline(splines, coords)

def get_spline_coords(ivy, branchidx):
    '''Does work now, but not used'''
    splines = ivy.data.splines
    if branchidx > len(splines)-1:
        return []
    spline = splines[branchidx]
    coords = [0]*len(spline.points)*4
    spline.points.foreach_get('co', coords)
    return coords


#COLLIDER IN IVY_SPACE
def collider_in_ivy_space(context, ivy):
    if ivy.ivy.collider:
        if not ivy.ivy.collider in context.scene.objects:
            return None
        collider = context.scene.objects[ivy.ivy.collider]
        me = collider.to_mesh(context.scene, True, settings='PREVIEW')
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(collider.matrix_world)
        bm.transform(ivy.matrix_world.inverted())
        return bm
    return None

#Fallof curve
def sigmoid( x, weight=1, offset=0, derivative=False):
    """weight=10, offset=0.5 for 0-1 S-curve"""
    if not derivative:
        return 1 / (1 + np.exp(-(x-offset)*weight))
    else:
        out = sigmoid(x, weight, offset)
        return out * (1 - out)


### GROWTH VECTOR
def growvec(opt, coords, bvh, freefloatinglength):
    
    #RANDOM Vector
    vec_random = rvec()
    vec_random *= opt.scale_random

    #UP Vector
    vec_up = Vector((0,0,1))
    if freefloatinglength and opt.stiffness_up:
        stiffness_range = opt.stiffness_up / freefloatinglength
        up_influence = sigmoid(stiffness_range, 10, 0.5)
        vec_up *= 1 - up_influence
    vec_up *= opt.scale_up
    #dspl.add_edge([coords[-1], coords[-1]+vec_up])

    #STRAIGHT Vector
    if len(coords) > 1:
        vec_straight = (coords[-1] - coords[-2]).normalized()
    else:
        vec_straight = Vector((0,0,0))
    vec_straight *= opt.scale_straight
    
    #GRAVITY Vector
    vec_grav = Vector((0,0,-1))
    if freefloatinglength and opt.scale_gravity and opt.stiffness_gravity:
        stiffness_range = opt.stiffness_gravity / freefloatinglength
        grav_influence = sigmoid(stiffness_range, -10, 0.5)
        vec_grav *= grav_influence
    vec_grav *= opt.scale_gravity
    #dspl.add_edge([coords[-1], coords[-1]+vec_grav])

    #ADHESION Vector
    vec_adhesion = Vector((0,0,0))
    if opt.has_collider:
        vec_adhesion = adhesion(opt, coords[-1], bvh, freefloatinglength)

    #COMBINE TO GROWTH VECTOR
    vec_grow = vec_random + vec_up + vec_straight + vec_grav + vec_adhesion

    #SET SCALE
    vec_grow = vec_grow.normalized()
    vec_grow.length = opt.scale
    return vec_grow


### ADHESION
def adhesion(opt, co, bvh, freefloatinglength):
    ### BASIS ADHESION VECTOR
    hit, normal, face, distance = bvh.find_nearest(co)
    vec_adhesion = (hit - co).normalized() * opt.scale

    ### DISTANCE MODIFICATION
    if opt.max_dist_adhesion:
        #this atenuates the force from max dist (no influence) to zero dist (max influence)
        relative_distance = distance / opt.max_dist_adhesion
        distance_influence = sigmoid(relative_distance, weight=-10, offset=0.5)
        vec_adhesion *= distance_influence

    ### CORNERS  - BACKFACING MODIFICATION
    ray_hit, ray_normal, ray_face, ray_distance = bvh.ray_cast(co, -normal, distance*2)
    if ray_hit is None:
        if (co-hit).dot(normal) > 0:
            angle = (co-hit).angle(normal)
            angle_range = angle / (np.pi/2)
            angle_influence = sigmoid(angle_range, weight=10, offset=0.5) * opt.adhesion_angle_influence
            vec_adhesion *= angle_influence
        else:
            vec_adhesion *= 0

    ### FREE FLOATING DISTANCE MODIFICATION
    #modify by freefloatingdistance
    if freefloatinglength and opt.adhesion_floating_influence and opt.adhesion_floating_length:
        relative_distance = freefloatinglength / opt.adhesion_floating_length
        floating_influence = sigmoid(relative_distance, -10, 0.5) * opt.adhesion_floating_influence
        vec_adhesion *= floating_influence
        #dspl.add_edge([co, co+vec_adhesion], k=[round(freefloatinglength,4), np.round(floating_influence,4)])
        
    ### GLOBAL ADHESION SCALE
    vec_adhesion *= opt.scale_adhesion

    #dspl.add_edge([co, co+vec_adhesion])
    return vec_adhesion


### COLLISION
def collision(opt, last_co, next_co, bvh):
    is_not_climbing = True
    segment_vec = next_co - last_co

    #TEST COLLISION
    ray_hit, ray_normal, ray_face, ray_distance = bvh.ray_cast(last_co, segment_vec, segment_vec.length)
    if ray_hit:
        is_not_climbing = False
        mirror = (last_co-ray_hit).reflect(ray_normal)
        mirror += ray_hit
        reflected = ray_hit-mirror

        reflected.length += opt.collision_margin
        reflected += mirror

        coll_vec = reflected - last_co
        if coll_vec.dot(ray_normal) > 0:
            coll_vec.length = opt.scale
            
        next_co = last_co+coll_vec

    #PUSH TO COLLISION MARGIN
    near_hit_next, near_normal_next, near_face_next, near_distance_next = bvh.find_nearest(next_co)
    if near_distance_next < opt.collision_margin:
        is_not_climbing = False
        next_co += near_normal_next * (opt.collision_margin - near_distance_next)

    return next_co, is_not_climbing

#################################################################
#### PARALLEL UPDATE FOR EACH BRANCH <--> SPLINE
@aio.coroutine
def grow_branch(context, branchidx, ivy, bvh=None):
    '''
    Should have two branches maybe.
    Test if only the next coordinate is missing:
        if yes only calculate that one.
        Reduce computation per frame update

        if not recalc spline points from start
        as is done now
    '''
    opt = ivy.ivy
    seed_val = opt.seed + branchidx + 1
    seed(seed_val)
    noise.seed_set(seed_val)

    ### GET BRANCH-NUMSTEPS FOR THIS FRAME
    if opt.animated:
        #this is fixed steps along animation range
        anim_frames_total = opt.end - opt.start
        anim_frame_current = context.scene.frame_current - opt.start
        numsteps = int((anim_frame_current / anim_frames_total) * opt.fixed_steps)
    else:
        numsteps = opt.fixed_steps

    ### CUTOFF NUMSTEPS
    cutoff = random()
    if opt.steps_random_cutoff <= cutoff:
        #cut this one off
        cutoffamount = (1 - cutoff) * opt.cutoffamount
        cutoff += cutoffamount
        numsteps = int(cutoff * numsteps)

    uvec = noise.random_unit_vector()
    start_co = Vector((uvec.x * opt.root_area.x,
                                  uvec.y * opt.root_area.y,
                                  uvec.z * opt.root_area.z))
    coords = [start_co]
    #free = [True]

    def recalc_all():
        freefloatinglength = 0
        for step in range(numsteps):
            last_co = coords[-1]
            vec_grow = growvec(opt, coords, bvh, freefloatinglength)
            next_co = last_co + vec_grow
            if opt.has_collider:
                next_co, is_free = collision(opt, last_co, next_co, bvh)
                if is_free:
                    freefloatinglength += (last_co - next_co).length
                else:
                    freefloatinglength = 0
            else:
                freefloatinglength += (last_co - next_co).length

            coords.append(next_co)

    recalc_all()

    return coords

def get_collider_bvh(context, ivy):
    opt = ivy.ivy
    if opt.has_collider:
        #collider in ivy space returns theoretically the
        #correct mesh. But somehow rotations still mock
        #up the collsions.
        bm = collider_in_ivy_space(context, ivy)
        bvh = BVHTree()
        bvh = bvh.FromBMesh(bm)
        #from object does not take transforms into account
        #bvh = bvh.FromObject(context.scene.objects[opt.collider], context.scene)
        return bvh
    else:
        return None


#### PARALLEL UPDATE FOR EACH IVY
@aio.coroutine
def update_ivy(context, ivy):
    #dspl.clear()
    #dspl.set_transform(ivy.matrix_world)

    if not ensure_integrity(context, ivy): return
    printd('UPDATING "%s"  Frame: %d' %(ivy.name, context.scene.frame_current))

    opt = ivy.ivy
    bvh = get_collider_bvh(context, ivy)

    branch_tasks = [aio.async(grow_branch(context, branchidx, ivy, bvh=bvh)) \
                    for branchidx in range(opt.num_roots)]
    branches = yield from aio.gather(*branch_tasks)

    create_splines(ivy, branches)


#### INEGRITY CHECK FOR OPTIONS
def ensure_integrity(context, ivy):
    opt = ivy.ivy

    #Check Integrity of end frame of ivy
    if opt.end <= opt.start:
        opt.end = opt.start + 1

    #Check validity of collider mesh
    if opt.collider:
        if not opt.collider in context.scene.objects:
            opt.has_collider = False
        elif context.scene.objects[opt.collider].type != 'MESH':
            opt.has_collider = False
        else:
            opt.has_collider = True
    else:
        opt.has_collider=False

    #Check if inside of animation range
    if opt.animated:
        if context.scene.frame_current < opt.start:
            ivy.data.splines.clear()
            return False
        elif context.scene.frame_current > opt.end:
            return False

    #All is well
    return True

#################################################################
### FRAME CHANGE UPDATE HANDLER
#################################################################
@persistent
def ivy_update(scene):
    context = bpy.context
    if not context.mode == 'OBJECT':
        return

    ivies = [ob for ob in scene.objects if ob.ivy.use_as_ivy]

    loop = aio.new_event_loop()
    aio.set_event_loop(loop)
    loop = aio.get_event_loop()

    tasks = [aio.async(update_ivy(context, ivy)) \
            for ivy in ivies]

    if tasks:
        loop.run_until_complete(aio.wait(tasks))
        loop.close()

    context.scene.update()

#### NO ANIMATION --> FIXED STEPSIZE
def non_animated_update(self, context):
    if not context.mode == 'OBJECT':
        return

    ivies = [context.scene.objects.active]

    loop = aio.new_event_loop()
    aio.set_event_loop(loop)
    loop = aio.get_event_loop()

    tasks = [aio.async(update_ivy(context, ivy)) \
            for ivy in ivies]

    if tasks:
        loop.run_until_complete(aio.wait(tasks))
        loop.close()

    context.scene.update()


#################################################################
class IvyProperties(PropertyGroup):
    has_collider = BoolProperty(
        name='has valid collider',
        default=False,
        options={'HIDDEN'},
        description='__internal__')
    added_as_ivy = BoolProperty(
        name='Added as Ivy',
        default=False,
        options={'HIDDEN'},
        description='__internal__')

    #GENERAL PROPERTIES
    use_as_ivy = BoolProperty(
        name='Ivy',
        default=False,
        update=update_func,
        description='Update Ivy on frame change and when tweaking settings.\n'
            'Turn off when no updates are needed ot save CPU-cycles.\n'
            'WARNING: Destroys/Re-Creates Curve Geometry.')
    num_roots = IntProperty(
        name='Root Count',
        default=3,
        min=1, soft_min=1,
        update=update_func,
        #set=update_on_set, #no good implementation found
        description='Number of root branches to grow')
    root_area = FloatVectorProperty(
        name='Root Area',
        size=3,
        subtype='XYZ',
        default=(0.0, 0.0, 0.0),
        min=0,
        update=update_func,
        description='X-Y-Z radius of sphere from where the branches start')
    scale = FloatProperty(
        name='Scale',
        default=0.05,
        precision=3,
        min=0.00001, soft_min=0.00001,
        update=update_func,
        description='Ivy scale.\n'
            'The desired distance between curve points.')
    seed = IntProperty(
        name='Seed',
        default=1,
        min=0, soft_min=0,
        update=update_func,
        description='Random Seed')


    #COLLIDER
    collider = StringProperty(
        name='Collider',
        default='',
        update=update_func,
        description='Mesh Collider object Name.\n'
            'IMPORTANT: Apply Rotation of collider to work reliably.\n')
    collision_margin = FloatProperty(
        name='Collision Margin',
        default=0.03,
        min=0, soft_min=0,
        update=update_func,
        description='Distance to Colidder after Collision')

    #GROWTH VECTOR PROPS
    scale_random = FloatProperty(
        name='Random',
        default=0.40,
        min=0, soft_min=0,
        update=update_func,
        description='Random ivy scale.\n'
            'More random --> more random :)')
    scale_gravity = FloatProperty(
        name='Gravity',
        default=0.10,
        min=0, soft_min=0,
        update=update_func,
        description='Gravity influence.\n'
            'Zero disables gravity.')
    stiffness_gravity = FloatProperty(
        name='Gravity stiffness',
        default=0.5,
        min=0, soft_min=0,
        update=update_func,
        description='Free floating distance until gravity is at full influence.\n'
            'Zero disables gravity.')
    scale_up = FloatProperty(
        name='Up',
        default=0.2,
        min=0, soft_min=0,
        update=update_func,
        description='Scale of up-vector force (in ivy-local-space)')
    stiffness_up = FloatProperty(
        name='Up stiffness',
        default=0,
        min=0, soft_min=0,
        update=update_func,
        description='Free floating distance until Up-Force is at full influence.\n'
            'Zero disables stiffnes (uniform up force over all).')
    scale_straight = FloatProperty(
        name='Straight',
        default=1,
        min=0, soft_min=0,
        update=update_func,
        description='Straight ivy scale.\n'
            'The "straighter" the less wiggly.')

    #ADHESION
    scale_adhesion = FloatProperty(
        name='Adhesion Strength',
        default=1,
        min=0, soft_min=0,
        #max=1,
        update=update_func,
        description='Adhesion scale.\n'
            'The adhesion Properties can be very dependent on the\n'
            'character of the mesh (sharp corners, non.manifold, ...)')
    adhesion_angle_influence = FloatProperty(
        name='Adhesion angle',
        default=1,
        #min=0, soft_min=0,
        #max=1, soft_max=1,
        update=update_func,
        description='Deals mainly with corners and open collider mesh edges.\n'
            'At negative values adhesion is inverted on sharp corners/open boundaries.\n'
            'With positive values the branch is "pulled" around the corner.\n'
            'Still backfacing faces never apply adhesion to the branch.')
    adhesion_floating_influence = FloatProperty(
        name='Adhesion floating Influence',
        default=1,
        #min=-1, soft_min=-1,
        #max=1, soft_max=1,
        update=update_func,
        description='Above zero: increase adhesion at small floating length.\n'
            'Below zero: invert adhesion at small floating length (push from surface).\n'
            'zero: disabled\n'
            'Adhesion is scaled towards zero at Adhesion floating length')
    adhesion_floating_length = FloatProperty(
        name='Adhesion floating length',
        default=1,
        min=0, soft_min=0,
        #max=1, soft_max=1,
        update=update_func,
        description='Length setting for Adhesion floating Influence.\n'
            'The length of a branch from either the root or the last collision.')
    max_dist_adhesion = FloatProperty(
        name='Adhesion Max Distance',
        default=1,
        min=0, soft_min=0,
        update=update_func,
        description='Adhesion Max Distance. 0 disables.\n'
            'The maximum distance to the collider mesh where adhesion applies force.')

    #ANIMATION
    animated = BoolProperty(
        name='Animated',
        default=False,
        update=update_func,
        description='Use start-end for animation of ivy.')
    steps = IntProperty(
        name='Steps',
        default=1,
        min=1, soft_min=1,
        update=update_func,
        description='Steps per Branch')
    start = IntProperty(
        name='Start Frame',
        default=1,
        #min=1, soft_min=0,
        update=update_func,
        description='Start Frame of Ivy growth')
    end = IntProperty(
        name='End Frame',
        default=100,
        #min=1, soft_min=0,
        update=update_func_endframe,
        description='End Frame of Ivy growth')

    #BRANCHPROPERTIES
    fixed_steps = IntProperty(
        name='Fixed Steps',
        default=100,
        min=1, soft_min=1,
        #update=update_func,
        update=non_animated_update,
        description='Steps of Ivy growth')
    steps_random_cutoff = FloatProperty(
        name='Random Cutoff',
        subtype='FACTOR',
        default=1,
        min=0, soft_min=0,
        max=1, soft_max=1,
        update=update_func,
        description='Probability of branches to reach final step-length.')
    cutoffamount = FloatProperty(
        name='Cutoff Amount',
        subtype='FACTOR',
        default=0.5,
        min=0, soft_min=0,
        max=1, soft_max=1,
        update=update_func,
        description='Factor of cutoff.')


#################################################################

class IvyPanel(Panel):
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "modifier"
    bl_label = 'Animated Ivy'
    #bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ob = context.object
        return ob and ob.type == 'CURVE' and ob.ivy.added_as_ivy

    def draw_header(self, context):
        layout = self.layout
        layout.prop(context.object.ivy, 'use_as_ivy', text='', icon='PARTICLE_PATH')

    def draw(self, context):
        scene = context.scene
        ob = scene.objects.active
        opt = ob.ivy
        layout = self.layout
        layout.active = opt.use_as_ivy

        col = layout.column(align=True)

        row = col.row(align=True)
        row.prop(opt, 'seed')
        row.prop(opt, 'num_roots')
        col.separator()

        #col.prop(opt, 'collider', icon='OBJECT_DATA')
        col.prop_search(opt, "collider", scene, "objects", text="Collider")
        if opt.has_collider:
            col.prop(opt, 'collision_margin')

        col.separator()
        col.prop(opt.id_data.data, 'bevel_depth')
        col.separator()
        col.prop(opt, 'scale')
        col.prop(opt, 'scale_up')
        col.prop(opt, 'stiffness_up')

        col.prop(opt, 'scale_straight')
        col.prop(opt, 'scale_random')

        col.prop(opt, 'scale_gravity')
        col.prop(opt, 'stiffness_gravity')
        if opt.has_collider:
            col.separator()
            col.prop(opt, 'scale_adhesion')
            col.prop(opt, 'adhesion_angle_influence')
            col.prop(opt, 'max_dist_adhesion')
            col.prop(opt, 'adhesion_floating_influence')
            col.prop(opt, 'adhesion_floating_length')

        col.separator()
        row=col.row()
        row.prop(opt, 'root_area')

        col.separator()
        row = col.row(align=True)
        row.prop(opt, 'fixed_steps', text='Steps')
        row.prop(opt, 'steps_random_cutoff')
        row.prop(opt, 'cutoffamount')

        col.separator()
        col.prop(opt, 'animated')
        if opt.animated:
            row = col.row(align=True)
            row.active = opt.animated
            row.prop(opt, 'start')
            row.prop(opt, 'end')

        col.separator()
        col.operator('curve.add_leafs', icon='PARTICLE_POINT')


def add_animated_ivy(self, context):
    sel = context.object
    collider = ''
    if sel:
        if sel.type == 'MESH':
            collider = sel.name

    bpy.ops.curve.primitive_bezier_curve_add()
    ivy = context.scene.objects.active
    ivy.name = 'Ivy'
    ivy.data.name = ivy.name
    ivy.data.fill_mode = 'FULL'
    ivy.ivy.use_as_ivy = True
    ivy.ivy.added_as_ivy = True
    ivy.ivy.collider = collider
    bpy.ops.object.modifier_add(type='SUBSURF')
    mod = ivy.modifiers[-1]
    mod.levels = 0
    mod.show_only_control_edges = True
    mod.show_expanded = False

class OBJECT_OT_add_growing_ivy(Operator):
    """Create a growing Ivy.
Selected Mesh Object acts as collider.
Options in the Modifier Panel."""
    bl_idname = "curve.add_animated_ivy"
    bl_label = "Add Animated Ivy"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT'

    def execute(self, context):
        add_animated_ivy(self, context)
        return {'FINISHED'}
###########################################################

def register():
    bpy.utils.register_class(OBJECT_OT_add_growing_ivy)
    bpy.utils.register_class(IvyPanel)
    bpy.utils.register_class(IvyProperties)

    bpy.types.Object.ivy = PointerProperty(type=IvyProperties)
    bpy.app.handlers.frame_change_post.append(ivy_update)

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_add_growing_ivy)
    bpy.utils.unregister_class(IvyPanel)
    bpy.utils.unregister_class(IvyProperties)

    bpy.app.handlers.frame_change_post.remove(ivy_update)
    del(bpy.types.Object.ivy)

if __name__ == "__main__":
    register()
