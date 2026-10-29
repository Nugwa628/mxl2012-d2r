"""Blender (headless): render a mesh .npz (pos, tris, optionally nrm, uv) from a few azimuths: the static reference of the in-game comparisons.

    blender -b -P tools/sprite3d/render_npz.py -- <mesh.npz> <out prefix> [--az 0,90,180,270] [--elev 20] [--size 600] [--wire]
            [--albedo a.png] [--normal n.png [--green gl|dx]] [--orm o.png] [--ortho 8.5] [--eevee]

Axes as in the build (y up, +z front; the object is turned into Blender's z-up); azimuth 0 looks at the front, 90 at the character's +x side. Default Workbench (studio light, flat
grey or the albedo texture); `--wire` overlays the edges; `--normal` / `--orm` switch to Eevee with a Principled material (normal map,
occlusion x albedo, roughness): what the game roughly does with the same maps. The same camera and key light are used for the
high-poly (`hi.npz`, no uv: grey) so the sheets compare like with like. Writes <prefix>_<az>.png.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_common as bc  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
opt = lambda n, d: type(d)(a[a.index(n) + 1]) if n in a else d
bpy.ops.wm.read_factory_settings(use_empty=True)
d = np.load(a[0])
ob = bc.mesh_object("m", d["pos"], d["tris"], d["uv"] if "uv" in d.files else None, d["nrm"] if "nrm" in d.files else None)
if "nrm" not in d.files:
    bpy.ops.object.shade_smooth()
ob.rotation_euler = (math.radians(90), 0, 0)  # y up -> Blender z up, +z front -> -y (the camera sits at -y for azimuth 0)
sc = bpy.context.scene
tex = {k: opt("--" + k, "") for k in ("albedo", "normal", "orm")}
use_eevee = "--eevee" in a or tex["normal"] or tex["orm"]
if use_eevee:
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    mat = bpy.data.materials.new("mat")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.67
    bsdf.inputs["Base Color"].default_value = (0.35, 0.3, 0.27, 1)

    def image(path, cs):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path)
        n.image.colorspace_settings.name = cs
        return n

    base = None
    if tex["albedo"]:
        base = image(tex["albedo"], "sRGB")
    if tex["orm"]:
        o = image(tex["orm"], "Non-Color")
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(o.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
        mul.inputs["Factor"].default_value = 1.0
        if base:
            nt.links.new(base.outputs["Color"], mul.inputs["A"])
        else:
            mul.inputs["A"].default_value = (0.5, 0.45, 0.4, 1)
        nt.links.new(sep.outputs["Red"], mul.inputs["B"])
        nt.links.new(mul.outputs["Result"], bsdf.inputs["Base Color"])
    elif base:
        nt.links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    if tex["normal"]:
        n = image(tex["normal"], "Non-Color")
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nm.uv_map = "UVMap"
        if opt("--green", "gl") == "dx":
            sp = nt.nodes.new("ShaderNodeSeparateColor")
            cb = nt.nodes.new("ShaderNodeCombineColor")
            inv = nt.nodes.new("ShaderNodeMath")
            inv.operation = "SUBTRACT"
            inv.inputs[0].default_value = 1.0
            nt.links.new(n.outputs["Color"], sp.inputs["Color"])
            nt.links.new(sp.outputs["Red"], cb.inputs["Red"])
            nt.links.new(sp.outputs["Green"], inv.inputs[1])
            nt.links.new(inv.outputs["Value"], cb.inputs["Green"])
            nt.links.new(sp.outputs["Blue"], cb.inputs["Blue"])
            nt.links.new(cb.outputs["Color"], nm.inputs["Color"])
        else:
            nt.links.new(n.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    ob.data.materials.append(mat)
else:
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light, sh.show_specular_highlight, sh.show_cavity = "STUDIO", False, False
    if tex["albedo"]:
        mat = bpy.data.materials.new("mat")
        mat.use_nodes = True
        n = mat.node_tree.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(tex["albedo"])
        mat.node_tree.links.new(n.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
        ob.data.materials.append(mat)
        sh.color_type = "TEXTURE"
    else:
        sh.color_type = "SINGLE"
        sh.single_color = (0.7, 0.68, 0.64)
if "--wire" in a:
    w = ob.copy()
    w.data = ob.data.copy()
    sc.collection.objects.link(w)
    wm = w.modifiers.new("w", "WIREFRAME")
    wm.thickness = 0.004
    dark = bpy.data.materials.new("wire")
    dark.diffuse_color = (0.02, 0.02, 0.02, 1)
    w.data.materials.clear()
    w.data.materials.append(dark)
    w.display_type = "SOLID"
sc.render.resolution_x = sc.render.resolution_y = opt("--size", 600)
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.06, 0.06, 0.07) if use_eevee else (0.25, 0.25, 0.27)
sc.world.use_nodes = False
if use_eevee:
    sc.world.use_nodes = True
    bgn = sc.world.node_tree.nodes["Background"]
    bgn.inputs["Color"].default_value = (0.35, 0.36, 0.4, 1)
    bgn.inputs["Strength"].default_value = 0.5
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(55), 0, math.radians(35))
    sc.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type, cam.data.ortho_scale = "ORTHO", opt("--ortho", 9.0)
ctr = Vector((0, 0, 3.3))
tgt = bpy.data.objects.new("t", None)
tgt.location = ctr
sc.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO")
c.target, c.track_axis, c.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
elev = math.radians(opt("--elev", 20))
for az in [float(x) for x in opt("--az", "0,90,180,270").split(",")]:
    r = math.radians(az)
    cam.location = ctr + Vector((math.sin(r) * math.cos(elev), -math.cos(r) * math.cos(elev), math.sin(elev))) * 20
    sc.render.filepath = "%s_%03d.png" % (a[1], round(az))
    bpy.ops.render.render(write_still=True)
