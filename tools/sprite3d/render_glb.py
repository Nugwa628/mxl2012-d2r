"""Blender (headless) turntable of GLB meshes: front / 3-4 / side / back as one PNG strip per mesh.

    blender -b -P tools/sprite3d/render_glb.py -- <out dir> <mesh.glb> [mesh.glb ...] [--size 360] [--tex]

Workbench engine, flat grey (or --tex: base colour texture) with cavity shading; the mesh is centred and scaled to unit height. glTF is Y-up; Blender's
importer converts to Z-up, so the default is z (the creature stands on +Z).
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
size = 360
if "--size" in argv:
    i = argv.index("--size"); size = int(argv[i + 1]); del argv[i:i + 2]
tex = "--tex" in argv
if tex:
    argv.remove("--tex")
out = Path(argv[0]).resolve(); out.mkdir(parents=True, exist_ok=True)
AZ = [0, 45, 90, 180]


def render_one(path: Path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    lo = Vector((1e9,) * 3); hi = Vector((-1e9,) * 3)
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    ctr = (lo + hi) / 2; h = max(hi.z - lo.z, 1e-6)
    pivot = bpy.data.objects.new("pivot", None); bpy.context.scene.collection.objects.link(pivot)
    for o in objs:
        o.parent = pivot
        o.location -= ctr
    pivot.scale = (1 / h,) * 3
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"; sh.color_type = "TEXTURE" if tex else "SINGLE"; sh.single_color = (0.75, 0.72, 0.65)
    sh.show_cavity = True; sh.cavity_type = "BOTH"
    sc.render.resolution_x = sc.render.resolution_y = size
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("w"); sc.world.color = (0.16, 0.16, 0.18)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.type = "ORTHO"; cam.data.ortho_scale = 1.25
    tgt = bpy.data.objects.new("t", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    tiles = []
    for k, az in enumerate(AZ):
        a = math.radians(az); el = math.radians(20)
        # glTF front faces +Y after import? keep camera on -Y at az 0 (Blender front view)
        cam.location = (math.sin(a) * 3 * math.cos(el), -math.cos(a) * 3 * math.cos(el), 3 * math.sin(el))
        sc.render.filepath = str(out / f"_{path.stem}_{k}.png")
        bpy.ops.render.render(write_still=True)
        tiles.append(sc.render.filepath)
    img = bpy.data.images
    strip = bpy.data.images.new("strip", size * len(tiles), size)
    import numpy as np
    buf = np.zeros((size, size * len(tiles), 4), np.float32)
    for k, t in enumerate(tiles):
        im = bpy.data.images.load(t)
        px = np.array(im.pixels[:], np.float32).reshape(size, size, 4)
        buf[:, k * size:(k + 1) * size] = px
        Path(t).unlink()
    strip.pixels = buf.ravel()
    strip.filepath_raw = str(out / f"{path.stem}.png"); strip.file_format = "PNG"; strip.save()
    print("rendered", path.stem, "verts", sum(len(o.data.vertices) for o in objs))


for m in argv[1:]:
    render_one(Path(m).resolve())
