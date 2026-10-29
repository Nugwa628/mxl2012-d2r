"""Blender (headless): decimated LODs of a UV-mapped mesh (and, without --keep-uv, a Smart UV Project unwrap first).

    blender -b -P tools/sprite3d/unwrap.py -- <in.obj> <out prefix> [--ratios 0.5,0.25,0.12,0.06] [--angle 66] [--margin 0.004] [--smooth 40] [--keep-uv]

The sprite texture uses tools/sprite3d/project_texture.py's atlas (xatlas, one chart per camera), so the usual call is `--keep-uv`
on that mesh: LOD 0 is written unchanged and LODs 1-4 are Decimate results that keep its UVs. The Smart UV path is kept for meshes
without an atlas; it shatters bumpy generated meshes into thousands of islands, hence the smoothing.

Writes `<prefix>_lod0.obj` (Smart UV Project of the input, smooth normals) and `<prefix>_lod<k>.obj` for each ratio (Decimate,
collapse, UVs kept; a LOD keeps LOD 0's texture so one set of maps serves all five). tools/sprite3d/obj_npz.py turns them into
the .npz that tools/d2r_mesh.py reads.
"""
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, prefix = argv[0], argv[1]
ratios = [float(x) for x in argv[argv.index("--ratios") + 1].split(",")] if "--ratios" in argv else [0.5, 0.25, 0.12, 0.06]
angle = float(argv[argv.index("--angle") + 1]) if "--angle" in argv else 66.0
margin = float(argv[argv.index("--margin") + 1]) if "--margin" in argv else 0.004
smooth = int(argv[argv.index("--smooth") + 1]) if "--smooth" in argv else 40
keep_uv = "--keep-uv" in argv

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.obj_import(filepath=src, forward_axis="NEGATIVE_Z", up_axis="Y")  # keep the file's axes: x right, y up, z front
ob = bpy.context.selected_objects[0]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
bpy.ops.object.shade_smooth()
for p in ob.data.polygons:
    p.use_smooth = True
if not keep_uv:
    orig = [v.co.copy() for v in ob.data.vertices]
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    # Generated meshes are bumpy: Smart UV Project on them gives thousands of tiny islands. The islands are cut on a smoothed
    # copy (same topology) and the UVs are kept when the vertices go back to their places.
    if smooth:
        bpy.ops.mesh.vertices_smooth(factor=1.0, repeat=smooth)
    bpy.ops.uv.smart_project(angle_limit=angle * 3.14159265 / 180, island_margin=margin, area_weight=0.6, correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.uv.pack_islands(margin=margin)
    bpy.ops.object.mode_set(mode="OBJECT")
    for v, co in zip(ob.data.vertices, orig):
        v.co = co
    ob.data.update()


def export(path):
    bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True, export_uv=True, export_normals=True,
                          export_materials=False, forward_axis="NEGATIVE_Z", up_axis="Y", apply_modifiers=True)


export(prefix + "_lod0.obj")
print("lod0", len(ob.data.polygons), "faces,", len(ob.data.vertices), "verts")
for k, r in enumerate(ratios, 1):
    m = ob.modifiers.new("dec", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = r
    m.use_collapse_triangulate = True
    export("%s_lod%d.obj" % (prefix, k))
    ob.modifiers.remove(m)
    print("lod%d" % k, "ratio", r)
