"""Blender side of s4_hdcap.py (round 18). Run headless:
  blender -b --factory-startup -noaudio --python hdcap_bl.py -- preview W [--body]   vertex-colour renders (cap high,
        with the body's high mesh when --body and W/high_shaped.npz exist): W/cappreview_*.png
  blender -b --factory-startup -noaudio --python hdcap_bl.py -- bake W [--size 2048] [--ao-samples 48]
        bakes the cap (W/cap_high.npz -> W/cap_lod0.npz with its disc UVs): W/capbake_{nrm,alb,aux,ao}.png
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hdbody_bl as hb  # noqa: E402


def g2b(V):
    V = np.asarray(V, float)
    return np.stack([V[:, 0], -V[:, 2], V[:, 1]], 1)


def make_mesh(name, V, T, uv=None, attrs=()):
    me = bpy.data.meshes.new(name)
    V = g2b(V).astype(np.float32)
    T = np.asarray(T, np.int32)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.ravel())
    me.loops.add(len(T) * 3)
    me.loops.foreach_set("vertex_index", T.ravel())
    me.polygons.add(len(T))
    me.polygons.foreach_set("loop_start", np.arange(0, len(T) * 3, 3, dtype=np.int32))
    me.update(calc_edges=True)
    me.validate(clean_customdata=False)
    if uv is not None:
        ul = me.uv_layers.new(name="UVMap")
        lv = T.ravel()
        u = np.asarray(uv, float)[lv]
        ul.data.foreach_set("uv", np.c_[u[:, 0], 1 - u[:, 1]].astype(np.float32).ravel())
    for an, data in attrs:
        at = me.color_attributes.new(an, "FLOAT_COLOR", "POINT")
        at.data.foreach_set("color", np.asarray(data, np.float32).ravel())
    me.shade_smooth() if hasattr(me, "shade_smooth") else None
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def high(W):
    z = np.load(W / "cap_high.npz")
    n = len(z["V"])
    return make_mesh("cap_high", z["V"], z["T"], attrs=(("col", np.c_[z["col"], np.ones(n)]),
                                                        ("aux", np.c_[z["glow"], z["rough"], np.zeros(n), np.ones(n)])))


def preview(W, a):
    hb.clear()
    high(W)
    if "--body" in a and (W / "high_shaped.npz").is_file():
        zb = np.load(W / "high_shaped.npz")
        T = np.load(W / "high_base.npz")["T"]
        n = len(zb["V"])
        make_mesh("body_high", zb["V"], T, attrs=(("col", np.c_[zb["col"], np.ones(n)]),))
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "VERTEX"
    sc.display.shading.show_cavity = True
    sc.display.shading.cavity_type = "BOTH"
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("w")
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    sc.collection.objects.link(cam)
    sc.camera = cam
    # (name, yaw deg, elevation deg, ortho scale, centre z, size)
    views = [("iso", 0, 35, 9.5, 4.6, (1000, 1200)), ("iso_r", 90, 35, 9.5, 4.6, (1000, 1200)),
             ("iso_b", 200, 35, 9.5, 4.6, (1000, 1200)), ("front", 0, 0, 9.5, 4.6, (1000, 1200)),
             ("top", 0, 89, 6.5, 7.6, (1100, 1100)), ("under", 20, -40, 7.0, 7.4, (1100, 1000)),
             ("cap_close", 30, 30, 4.2, 7.7, (1400, 1100))]
    if "--views" in a:
        keep = a[a.index("--views") + 1].split(",")
        views = [v for v in views if v[0] in keep]
    for name, yaw, el, osc, cz, (rx, ry) in views:
        sc.render.resolution_x, sc.render.resolution_y = rx, ry
        cam.data.ortho_scale = osc
        y, e = math.radians(yaw), math.radians(el)
        d = 20
        cam.location = (d * math.sin(y) * math.cos(e), -d * math.cos(y) * math.cos(e), cz + d * math.sin(e))
        cam.rotation_euler = (math.radians(90) - e, 0, y)
        sc.render.filepath = str(W / ("cappreview_%s.png" % name))
        bpy.ops.render.render(write_still=True)
    print("CAPPREVIEW done")


def bake(W, a):
    hb.clear()
    size = int(hb.opt(a, "--size", "2048"))
    hi = high(W)
    z = np.load(W / "cap_lod0.npz")
    lo = make_mesh("cap_low", z["pos"], z["tris"], uv=z["uv"])
    # the low mesh's own normals are the smooth ones (custom normals not needed: smooth shading of the same grid)
    sc = bpy.context.scene
    mh = bpy.data.materials.new("hm")
    mh.use_nodes = True
    nt = mh.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "col"
    nt.links.new(attr.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], outn.inputs["Surface"])
    hi.data.materials.append(mh)
    ml = bpy.data.materials.new("lm")
    ml.use_nodes = True
    lo.data.materials.append(ml)
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.threads_mode = "FIXED"
    sc.render.threads = int(hb.opt(a, "--threads", "16"))
    bk = sc.render.bake
    bk.use_selected_to_active = True
    bk.cage_extrusion = float(hb.opt(a, "--cage", "0.12"))
    bk.max_ray_distance = float(hb.opt(a, "--ray", "0.3"))
    bk.margin = int(hb.opt(a, "--bake-margin", "4"))
    bk.margin_type = "EXTEND"
    bpy.context.view_layer.objects.active = lo
    for ob in bpy.data.objects:
        ob.select_set(ob in (lo, hi))

    def run(kind, name, noncolor, samples=1, **kw):
        img = hb.node_img(ml, name, size, noncolor)
        sc.cycles.samples = samples
        bpy.ops.object.bake(type=kind, **kw)
        img.filepath_raw = str(W / ("capbake_%s.png" % name))
        img.file_format = "PNG"
        img.save()
        print("BAKED", name, flush=True)
    run("NORMAL", "nrm", True, normal_space="TANGENT")
    run("EMIT", "alb", False)
    attr.attribute_name = "aux"
    run("EMIT", "aux", True)
    hm2 = bpy.data.materials.new("hm2")
    hm2.use_nodes = True
    hi.data.materials[0] = hm2
    run("AO", "ao", True, samples=int(hb.opt(a, "--ao-samples", "48")))
    print("CAPBAKE done")


def lookdev(W, a):
    """the game asset as built: cap_lod0 + body lod0 (bind pose) with the baked maps (bake_* / capbake_* composed by
    the cap's texel mask), Principled BSDF + emission from the glow, Cycles. W/lookdev_*.png"""
    hb.clear()
    cap = np.load(W / "cap_texels.npy")
    imgs = {}
    for name in ("alb", "nrm", "aux", "ao"):
        from_body = np.asarray(bpy.data.images.load(str(W / ("bake_%s.png" % name))).pixels[:], np.float32)
        from_cap = np.asarray(bpy.data.images.load(str(W / ("capbake_%s.png" % name))).pixels[:], np.float32)
        n = int(np.sqrt(len(from_body) // 4))
        m = np.repeat(cap[::-1].ravel(), 4)          # Blender pixels run bottom-up
        px = np.where(m, from_cap, from_body)
        im = bpy.data.images.new("c_" + name, n, n, alpha=False, float_buffer=False)
        im.colorspace_settings.name = "sRGB" if name == "alb" else "Non-Color"
        im.pixels.foreach_set(px)
        im.pack()
        imgs[name] = im
    mat = bpy.data.materials.new("m")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]

    def tex(name):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = imgs[name]
        return t
    ta, tn, tx, to = tex("alb"), tex("nrm"), tex("aux"), tex("ao")
    mul = nt.nodes.new("ShaderNodeMixRGB")
    mul.blend_type = "MULTIPLY"
    mul.inputs[0].default_value = 1.0
    nt.links.new(ta.outputs["Color"], mul.inputs[1])
    nt.links.new(to.outputs["Color"], mul.inputs[2])
    nt.links.new(mul.outputs["Color"], bsdf.inputs["Base Color"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tx.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(ta.outputs["Color"], bsdf.inputs["Emission Color"])
    em = nt.nodes.new("ShaderNodeMath")
    em.operation = "MULTIPLY"
    em.inputs[1].default_value = float(hb.opt(a, "--glow", "1.5"))
    nt.links.new(sep.outputs["Red"], em.inputs[0])
    nt.links.new(em.outputs[0], bsdf.inputs["Emission Strength"])
    z = np.load(W / "cap_lod0.npz")
    zb = np.load(W / "lod0.npz")
    for nm_, zz in (("cap", z), ("body", zb)):
        ob = make_mesh(nm_, zz["pos"], zz["tris"], uv=zz["uv"])
        ob.data.materials.append(mat)
        ob.data.shade_smooth()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = int(hb.opt(a, "--samples", "48"))
    sc.cycles.use_denoising = False         # OIDN reserves more address space than the 10 GB job limit
    sc.render.threads_mode = "FIXED"
    sc.render.threads = int(hb.opt(a, "--threads", "12"))
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.02, 0.025, 0.04, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.world = w
    for nm_, rot, en in (("key", (math.radians(50), 0, math.radians(30)), 3.0),
                         ("fill", (math.radians(70), 0, math.radians(-140)), 0.8)):
        L = bpy.data.objects.new(nm_, bpy.data.lights.new(nm_, "SUN"))
        L.data.energy = en
        L.rotation_euler = rot
        sc.collection.objects.link(L)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    sc.collection.objects.link(cam)
    sc.camera = cam
    views = [("iso", 0, 35, 9.5, 4.6, (1600, 1900)), ("cap_close", 30, 30, 4.2, 7.7, (2400, 1900)),
             ("cap_front", -20, 12, 5.6, 7.4, (2400, 1700)), ("under", 20, -40, 7.0, 7.4, (1600, 1450))]
    if "--views" in a:
        keep = a[a.index("--views") + 1].split(",")
        views = [v for v in views if v[0] in keep]
    for name, yaw, el, osc, cz, (rx, ry) in views:
        sc.render.resolution_x, sc.render.resolution_y = rx, ry
        cam.data.ortho_scale = osc
        y, e = math.radians(yaw), math.radians(el)
        d = 20
        cam.location = (d * math.sin(y) * math.cos(e), -d * math.cos(y) * math.cos(e), cz + d * math.sin(e))
        cam.rotation_euler = (math.radians(90) - e, 0, y)
        sc.render.filepath = str(W / ("lookdev_%s.png" % name))
        bpy.ops.render.render(write_still=True)
    print("LOOKDEV done")


if __name__ == "__main__":
    cmd, W, rest = hb.args()
    {"preview": preview, "bake": bake, "lookdev": lookdev}[cmd](W, rest)
