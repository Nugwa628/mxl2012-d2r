"""Blender (headless) turntable of one textured GLB: N azimuths at a fixed camera elevation, orthographic, Workbench.

    blender -b -P tools/sprite3d/render_tex.py -- <mesh.glb> <out prefix> [--elev 30] [--n 8] [--size 640] [--bg 1,1,1]

Writes <out prefix>_<azimuth, 3 digits>.png. Azimuth 0 is the camera in front of the model (+z in model space), 90 on its +x side.
The model is centred and scaled to unit height; the glTF importer turns y-up into Blender's z-up and +z (front) into -y.
"""
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


src, prefix = argv[0], argv[1]
elev, n, size = float(opt("--elev", 30)), int(opt("--n", 8)), int(opt("--size", 640))
bg = [float(x) for x in opt("--bg", "1,1,1").split(",")]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        lo = Vector(map(min, lo, w))
        hi = Vector(map(max, hi, w))
ctr = (lo + hi) / 2
h = max(hi.z - lo.z, 1e-6)
pivot = bpy.data.objects.new("pivot", None)
bpy.context.scene.collection.objects.link(pivot)
for o in objs:
    o.parent = pivot
    o.location -= ctr
pivot.scale = (1 / h,) * 3
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sh = sc.display.shading
sh.light = "STUDIO"
sh.color_type = "TEXTURE"
sh.show_cavity = False
sh.show_specular_highlight = False
sc.render.resolution_x = sc.render.resolution_y = size
sc.world = bpy.data.worlds.new("w")
sc.world.color = bg
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
cam.data.ortho_scale = 1.35
tgt = bpy.data.objects.new("t", None)
sc.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO")
c.target = tgt
c.track_axis = "TRACK_NEGATIVE_Z"
c.up_axis = "UP_Y"
for k in range(n):
    az = 360.0 * k / n
    a, e = math.radians(az), math.radians(elev)
    cam.location = (math.sin(a) * 3 * math.cos(e), -math.cos(a) * 3 * math.cos(e), 3 * math.sin(e))
    sc.render.filepath = "%s_%03d.png" % (prefix, round(az))
    bpy.ops.render.render(write_still=True)
