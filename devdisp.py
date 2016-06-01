import bpy, bgl, blf
import numpy as np
from bpy_extras.view3d_utils import location_3d_to_region_2d
from bgl import glEnable, glDisable, glColor3f, glColor4f, glVertex3f, glPointSize, glLineWidth, glBegin, glEnd, glLineStipple, GL_POINTS, GL_LINE_STRIP, GL_LINES, GL_LINE_STIPPLE

from mathutils import Vector, Matrix
draw_handle = []

### STORAGE
points = {}
segments = {}
chains = {}
plots = {}
transform = Matrix()
textdraw = True
gldraw = True

### STORAGE CONTROL
def clear():
    points.clear()
    segments.clear()
    chains.clear()
    global plot
    plot = None
    tag_redraw_all_view3d()

def set_transform(matrix):
    global transform
    if type(matrix) == Matrix:
        transform = matrix

def linear(value):
    return value

def plot_add(funcy=linear, rangex=[0,1], resolution=0.1, k=''):
    if not k:
        k = next_int_key(plots.keys())
        
    X = np.arange(*rangex, resolution).tolist()
    Y = [funcy(x) for x in X]

    plots[k] = [X,Y]
    
    tag_redraw_all_view3d()

def points_add(value, k=''):
    if not k:
        k = next_int_key(points.keys())
    #if transform:
    value = transform * value
    points[str(k)] = value

    tag_redraw_all_view3d()

def segments_add(value, k=''):
    if not k:
        k = next_int_key(segments.keys())
    #if transform:
    value = [transform*v for v in value]
    segments[str(k)] = value

def point_chain_add(values, k=''):
    values = create_segment_list(values)
    if not k:
        k = next_int_key(chains.keys())
    chains[k] = values

### UTILS
def create_segment_list(values=[]):
    values = [list(v) for v in values]
    segments = list(zip(values[:-1], values[1:]))
    return segments

def next_int_key(keys):
    nums = []
    for k in keys:
        try:
            num = int(k)
            nums.append(num)
        except:
            pass
    if nums:
        return sorted(nums)[-1] + 1
    return 0



### DRAWING
def show_text(value):
    global textdraw
    textdraw = bool(value)

def show_gl(value):
    global gldraw
    gldraw = bool(value)

def tag_redraw_all_view3d():
    context = bpy.context
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()


def draw_start():
    SpaceView3D = bpy.types.SpaceView3D
    if draw_handle:
        return

    handle_pixel = SpaceView3D.draw_handler_add(draw_devdisp_px, (), 'WINDOW', 'POST_PIXEL')
    handle_view = SpaceView3D.draw_handler_add(draw_devdisp_view, (), 'WINDOW', 'POST_VIEW')
    draw_handle[:] = [handle_pixel, handle_view]
    tag_redraw_all_view3d()


def draw_stop():
    SpaceView3D = bpy.types.SpaceView3D
    if not draw_handle:
        return

    handle_pixel, handle_view = draw_handle
    SpaceView3D.draw_handler_remove(handle_pixel, 'WINDOW')
    SpaceView3D.draw_handler_remove(handle_view, 'WINDOW')
    draw_handle[:] = []

    tag_redraw_all_view3d()

### GL PRIMITIVES
def draw_line(v1, v2, width=1, color=(0,1,0)):
    glColor3f(*color)
    glLineWidth(width)
    glBegin(GL_LINE_STRIP)
    glVertex3f(*v1)
    glVertex3f(*v2)
    glEnd()
    glLineWidth(1)

def draw_vert(v1, width=5.0, color=(1,0,0)):
    glColor3f(*color)
    glBegin(GL_POINTS)
    glPointSize(width)
    glVertex3f(*v1)
    glEnd()

### VIEW DRAW
def draw_devdisp_view():
    if not gldraw:
        return

    #context = bpy.context
    #region = context.region
    #region3d = context.space_data.region_3d
    #region_mid_width = region.width / 2.0
    #region_mid_height = region.height / 2.0
    #perspective_matrix = region3d.perspective_matrix.copy()

    if points:
        #glColor3f(1, 0, 0)
        for k,v in points.items():
            draw_vert(Vector(v).to_3d(), color=(1, 0, 0))

    if segments:
        #glColor3f(0, 1, 0)
        for k,v in segments.items():
            draw_line(*v, color=(0,1,0))

    if chains:
        #glColor3f(0, 0, 1)
        for k,v in chains.items():
            if v:
                for s in v:
                    draw_line(*v, color=(0,0,1))

    if plots:
        for k,v in plots.items():
            draw_plot(v)

    tag_redraw_all_view3d()

### TEXT PRIMITIVE
def draw_text(text, vec):
    context = bpy.context
    region = context.region
    region3d = context.space_data.region_3d
    
    font_id=0
    vec = Vector(vec)
    vec = location_3d_to_region_2d(region, region3d, vec)

    blf.position(font_id, vec.x + 5, vec.y - 5, 1)
    blf.size(font_id, 11, 72)
    blf.draw(font_id, text)

### PIXEL DRAW
def draw_devdisp_px():
    #context = bpy.context
    #region = context.region
    #region3d = context.space_data.region_3d

    if textdraw:
        if points:
            for k,v in points.items():
                draw_text(k,v)

        if segments:
            for k,v in segments.items():
                draw_text(k, (v[0]+v[1])/2)

        if chains:
            for k,v in chains.items():
                if v:
                    draw_text(k, (v[0][0] + v[0][1]) / 2)

#    if plot:
#        draw_plot()

    tag_redraw_all_view3d()

def draw_plot(plot):
    #context = bpy.context
    #region = context.region
    #region3d = context.space_data.region_3d
    #region_mid_width = region.width / 2.0
    #region_mid_height = region.height / 2.0
    #perspective_matrix = region3d.perspective_matrix.copy()

    veclist = [Vector((x,y,0)) for x,y in zip(plot[0], plot[1])]
    plotlineedges = create_segment_list(veclist)

    for e in plotlineedges:
        draw_line(*e, color=(1,0,0))
