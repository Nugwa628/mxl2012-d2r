"""Blender side of s4_hdbody.py (round 17). Run headless:
  blender -b --factory-startup -noaudio --python hdbody_bl.py -- model W
  blender -b --factory-startup -noaudio --python hdbody_bl.py -- bake W [--size 2048] [--ao-samples 64]

model: the design graph (W/graph.json) through the skin modifier and subdivision; low = level LOW (game mesh),
       high = level HIGH (bake source). Writes W/low_base.npz, W/high_base.npz (V, T triangles of the quads) and
       W/model.blend.
bake:  loads W/model.blend and the shaped positions and paint (W/low_shaped.npz, W/high_shaped.npz), unwraps the low
       mesh, packs its islands into the free atlas texels (W/occupied.npy, the cap's texels), bakes normal (tangent,
       OpenGL), AO, albedo, glow and roughness from high to low at the atlas size, decimates LODs and writes
       W/bake_*.png and W/lod{k}.npz (pos, nrm, uv (v down), tris).
"""
import json
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np

LOW, HIGH = 2, 4


def args():
    a = sys.argv[sys.argv.index("--") + 1:]
    return a[0], Path(a[1]), a[2:]


def opt(a, n, d):
    return a[a.index(n) + 1] if n in a else d


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def mesh_arrays(ob):
    me = ob.data
    V = np.zeros(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", V)
    me.calc_loop_triangles()
    T = np.zeros(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", T)
    return V.reshape(-1, 3), T.reshape(-1, 3)


def apply_mods(ob):
    bpy.context.view_layer.objects.active = ob
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def model(W, a):
    clear()
    G = json.loads((W / "graph.json").read_text())
    # bind space is y up (game); Blender is z up: (x, y, z)_game -> (x, -z, y)_blender
    P = np.array([n["p"] for n in G["nodes"]])
    Pb = np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)
    me = bpy.data.meshes.new("graph")
    me.from_pydata(Pb.tolist(), [tuple(e) for e in G["edges"]], [])
    me.update()
    ob = bpy.data.objects.new("body", me)
    bpy.context.scene.collection.objects.link(ob)
    sk = ob.modifiers.new("skin", "SKIN")
    sk.branch_smoothing = float(opt(a, "--branch", "0.6"))
    sk.use_smooth_shade = True
    sv = me.skin_vertices[0].data
    for i, n in enumerate(G["nodes"]):
        sv[i].radius = (n["r"], n["r"])
        sv[i].use_root = (i == G.get("root", 0))
    ss = ob.modifiers.new("sub", "SUBSURF")
    ss.levels = LOW
    ss.render_levels = LOW
    apply_mods(ob)
    ob.name = "low"
    ob.data.name = "low"
    V, T = mesh_arrays(ob)
    np.savez(W / "low_base.npz", V=np.stack([V[:, 0], V[:, 2], -V[:, 1]], 1), T=T)
    hi = ob.copy()
    hi.data = ob.data.copy()
    hi.name = "high"
    hi.data.name = "high"
    bpy.context.scene.collection.objects.link(hi)
    s2 = hi.modifiers.new("sub", "SUBSURF")
    s2.levels = HIGH - LOW
    s2.render_levels = HIGH - LOW
    apply_mods(hi)
    V, T = mesh_arrays(hi)
    np.savez(W / "high_base.npz", V=np.stack([V[:, 0], V[:, 2], -V[:, 1]], 1), T=T)
    bpy.ops.wm.save_as_mainfile(filepath=str(W / "model.blend"))
    print("MODEL low %d high %d" % (len(ob.data.vertices), len(hi.data.vertices)))


def g2b(V):
    V = np.asarray(V, float)
    return np.stack([V[:, 0], -V[:, 2], V[:, 1]], 1)


def load_shaped(W):
    bpy.ops.wm.open_mainfile(filepath=str(W / "model.blend"))
    lo, hi = bpy.data.objects["low"], bpy.data.objects["high"]
    for ob, which in ((lo, "low"), (hi, "high")):
        z = np.load(W / ("%s_shaped.npz" % which))
        ob.data.vertices.foreach_set("co", g2b(z["V"]).astype(np.float32).ravel())
        ob.data.update()
        if which == "high":
            n = len(ob.data.vertices)
            for name, data in (("col", np.c_[z["col"], np.ones(n)]),
                               ("aux", np.c_[z["glow"], z["rough"], np.zeros(n), np.ones(n)])):
                at = ob.data.color_attributes.new(name, "FLOAT_COLOR", "POINT")
                at.data.foreach_set("color", data.astype(np.float32).ravel())
    return lo, hi


def preview(W, a):
    lo, hi = load_shaped(W)
    lo.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.display.shading.light = "STUDIO"
    sc.display.shading.color_type = "VERTEX"
    sc.display.shading.show_cavity = True
    sc.render.resolution_x, sc.render.resolution_y = 1000, 1400
    sc.world = bpy.data.worlds.new("w")
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = float(opt(a, "--ortho", "9.5"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    import math
    for name, ang in (("front", 0), ("side", 90), ("back", 180), ("q", 35)):
        r = math.radians(ang)
        cam.location = (12 * math.sin(r), -12 * math.cos(r), float(opt(a, "--cz", "3.8")))
        cam.rotation_euler = (math.radians(90), 0, r)
        sc.render.filepath = str(W / ("preview_%s.png" % name))
        bpy.ops.render.render(write_still=True)
    print("PREVIEW done")


# ------------------------------------------------------------------------------------------------------------ bake
def islands(me, uvl):
    """face -> island id: faces joined across edges whose two UV corners match."""
    nf = len(me.polygons)
    parent = list(range(nf))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    uv = np.zeros(len(me.loops) * 2)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    lv = np.zeros(len(me.loops), int)
    me.loops.foreach_get("vertex_index", lv)
    edge_seen = {}
    for f in me.polygons:
        ls = list(f.loop_indices)
        for k in range(len(ls)):
            a, b = ls[k], ls[(k + 1) % len(ls)]
            va, vb = lv[a], lv[b]
            key = (min(va, vb), max(va, vb))
            ua = tuple(np.round(uv[a], 6)) if va < vb else tuple(np.round(uv[b], 6))
            ub = tuple(np.round(uv[b], 6)) if va < vb else tuple(np.round(uv[a], 6))
            if key in edge_seen:
                g, uu = edge_seen[key]
                if uu == (ua, ub):
                    ra, rb = find(g), find(f.index)
                    if ra != rb:
                        parent[ra] = rb
            else:
                edge_seen[key] = (f.index, (ua, ub))
    return np.array([find(i) for i in range(nf)]), uv, lv


def fill_tris(m, polys):
    """set the cells of mask m covered by polygons (fans of triangles), conservative (cell centres within 0.5)."""
    H, Wd = m.shape
    for p in polys:
        p = np.asarray(p, float)
        for k in range(1, len(p) - 1):
            a, b, c = p[0], p[k], p[k + 1]
            x0, y0 = np.floor(np.minimum(np.minimum(a, b), c)).astype(int) - 1
            x1, y1 = np.ceil(np.maximum(np.maximum(a, b), c)).astype(int) + 1
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, Wd), min(y1, H)
            if x1 <= x0 or y1 <= y0:
                continue
            yy, xx = np.mgrid[y0:y1, x0:x1]
            px, py = xx + 0.5, yy + 0.5
            d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
            if abs(d) < 1e-12:
                m[int(np.clip(a[1], 0, H - 1)), int(np.clip(a[0], 0, Wd - 1))] = True
                continue
            l1 = ((b[1] - c[1]) * (px - c[0]) + (c[0] - b[0]) * (py - c[1])) / d
            l2 = ((c[1] - a[1]) * (px - c[0]) + (a[0] - c[0]) * (py - c[1])) / d
            l3 = 1 - l1 - l2
            # tolerance in barycentric units ~ half a cell over the triangle's size
            tol = 0.75 / max(np.ptp([a[0], b[0], c[0]]) + np.ptp([a[1], b[1], c[1]]), 1e-6)
            m[y0:y1, x0:x1] |= (l1 >= -tol) & (l2 >= -tol) & (l3 >= -tol)
    return m


def raster(polys, shape, grow):
    m = fill_tris(np.zeros(shape, bool), polys)
    for _ in range(grow):
        m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    return m


def place(occ_s, isl):
    """first fit (top rows first) of island mask isl into the free cells of occ_s (True = taken); None if none."""
    H, Wd = occ_s.shape
    h, w = isl.shape
    if h > H or w > Wd:
        return None
    fo = np.fft.rfft2(occ_s.astype(np.float32))
    k = np.zeros((H, Wd), np.float32)
    k[:h, :w] = isl[::-1, ::-1]
    conv = np.fft.irfft2(fo * np.fft.rfft2(k), s=(H, Wd))
    # conv[y + h - 1, x + w - 1] = overlap of the island placed at (y, x)
    ok = conv[h - 1:, w - 1:] < 0.5
    ys, xs = np.nonzero(ok)
    if not len(ys):
        return None
    j = np.argmin(ys * Wd + xs)
    return int(ys[j]), int(xs[j])


def pack(me, uvl, occ, size, margin, a):
    fid, uv, lv = islands(me, uvl)
    ids = np.unique(fid)
    # game convention: v down; work in (u, 1 - v)
    g = np.c_[uv[:, 0], 1 - uv[:, 1]]
    polys = {i: [] for i in ids}
    for f in me.polygons:
        polys[fid[f.index]].append(list(f.loop_indices))
    S = int(opt(a, "--pack-scale", "2"))         # pack on a grid S times coarser than the atlas
    occ_s = occ.reshape(size // S, S, size // S, S).any((1, 3))
    area = sum(((g[ls].max(0) - g[ls].min(0)).prod()) for i in ids for ls in polys[i][:0]) or 1
    tot = 0.0
    for i in ids:
        for ls in polys[i]:
            q = g[ls]
            tot += 0.5 * abs(np.dot(q[:, 0], np.roll(q[:, 1], 1)) - np.dot(q[:, 1], np.roll(q[:, 0], 1)))
    free = (~occ_s).sum()
    dens = np.sqrt(free * float(opt(a, "--fill", "0.55")) / tot)       # cells per uv unit
    order = sorted(ids, key=lambda i: -np.ptp(np.vstack([g[ls] for ls in polys[i]]), 0).prod())
    for attempt in range(8):
        taken = occ_s.copy()
        out = {}
        okall = True
        for i in order:
            pts = np.vstack([g[ls] for ls in polys[i]])
            lo = pts.min(0)
            best = None
            for rot in (0, 1):
                P_ = [(g[ls] - lo) * dens for ls in polys[i]]
                if rot:
                    P_ = [np.c_[p[:, 1], p[:, 0]] for p in P_]
                ext = np.ceil(np.max([p.max(0) for p in P_], 0)).astype(int) + 2 * margin + 2
                m = raster([p[:, ::1] + margin + 1 for p in P_], (ext[1], ext[0]), margin)
                pos = place(taken, m)
                if pos is not None and (best is None or pos[0] * 10000 + pos[1] < best[0][0] * 10000 + best[0][1]):
                    best = (pos, rot, m)
            if best is None:
                okall = False
                break
            (y, x), rot, m = best
            taken[y:y + m.shape[0], x:x + m.shape[1]] |= m
            out[i] = (y, x, rot, lo)
        if okall:
            break
        dens *= 0.9
        print("PACK retry dens %.1f" % dens, flush=True)
    newuv = np.zeros_like(uv)
    for i, (y, x, rot, lo) in out.items():
        for ls in polys[i]:
            q = (g[ls] - lo) * dens
            if rot:
                q = np.c_[q[:, 1], q[:, 0]]
            q = (q + margin + 1 + np.array([x, y])) * S / size
            newuv[ls] = np.c_[q[:, 0], 1 - q[:, 1]]
    uvl.data.foreach_set("uv", newuv.astype(np.float32).ravel())
    print("PACK islands %d density %.1f texels/uv (atlas) fill %.2f" % (len(ids), dens * S, (taken & ~occ_s).sum() / free), flush=True)
    return len(ids), dens * S


def node_img(mat, name, size, noncolor):
    img = bpy.data.images.new(name, size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = "Non-Color" if noncolor else "sRGB"
    nt = mat.node_tree
    for n in nt.nodes:
        n.select = False
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = img
    tn.select = True
    nt.nodes.active = tn
    return img


def bake(W, a):
    import math
    lo, hi = load_shaped(W)
    size = int(opt(a, "--size", "2048"))
    occ = np.load(W / "occupied.npy")
    sc = bpy.context.scene
    # unwrap the low mesh
    bpy.context.view_layer.objects.active = lo
    for ob in bpy.data.objects:
        ob.select_set(ob == lo)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(float(opt(a, "--angle", "60"))), island_margin=0.002,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    uvl = lo.data.uv_layers.active
    nis, dens = pack(lo.data, uvl, occ, size, int(opt(a, "--margin", "2")), a)
    # body texel mask (placed islands, grown by the bake margin)
    uv = np.zeros(len(lo.data.loops) * 2)
    uvl.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    polys = [np.c_[uv[list(f.loop_indices), 0] * size, (1 - uv[list(f.loop_indices), 1]) * size] for f in lo.data.polygons]
    np.save(W / "body_texels.npy", fill_tris(np.zeros((size, size), bool), polys))
    # materials
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
    hi.data.materials.clear()
    hi.data.materials.append(mh)
    ml = bpy.data.materials.new("lm")
    ml.use_nodes = True
    lo.data.materials.clear()
    lo.data.materials.append(ml)
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.render.threads_mode = "FIXED"
    sc.render.threads = int(opt(a, "--threads", "16"))
    bk = sc.render.bake
    bk.use_selected_to_active = True
    bk.cage_extrusion = float(opt(a, "--cage", "0.12"))
    bk.max_ray_distance = float(opt(a, "--ray", "0.3"))
    bk.margin = int(opt(a, "--bake-margin", "4"))
    bk.margin_type = "EXTEND"
    bpy.context.view_layer.objects.active = lo
    for ob in bpy.data.objects:
        ob.select_set(ob in (lo, hi))

    def run(kind, name, noncolor, samples=1, **kw):
        img = node_img(ml, name, size, noncolor)
        sc.cycles.samples = samples
        bpy.ops.object.bake(type=kind, **kw)
        img.filepath_raw = str(W / ("bake_%s.png" % name))
        img.file_format = "PNG"
        img.save()
        print("BAKED", name, flush=True)
    run("NORMAL", "nrm", True, normal_space="TANGENT")
    run("EMIT", "alb", False)
    attr.attribute_name = "aux"
    run("EMIT", "aux", True)
    # AO: the high mesh's own occlusion
    hm2 = bpy.data.materials.new("hm2")
    hm2.use_nodes = True
    hi.data.materials[0] = hm2
    run("AO", "ao", True, samples=int(opt(a, "--ao-samples", "48")))
    # LODs: copies of the low mesh, decimated, triangulated, split at UV seams
    ratios = [float(x) for x in opt(a, "--lods", "1,0.5,0.26,0.15,0.09").split(",")]
    for k, r in enumerate(ratios):
        ob = lo.copy()
        ob.data = lo.data.copy()
        sc.collection.objects.link(ob)
        if r < 1:
            dmod = ob.modifiers.new("dec", "DECIMATE")
            dmod.ratio = r
            dmod.use_collapse_triangulate = True
        tmod = ob.modifiers.new("tri", "TRIANGULATE")
        apply_mods(ob)
        me = ob.data
        nv = len(me.vertices)
        V = np.zeros(nv * 3)
        me.vertices.foreach_get("co", V)
        V = V.reshape(-1, 3)
        N = np.zeros(nv * 3)
        me.vertices.foreach_get("normal", N)
        N = N.reshape(-1, 3)
        lv = np.zeros(len(me.loops), int)
        me.loops.foreach_get("vertex_index", lv)
        uv = np.zeros(len(me.loops) * 2)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        key = np.c_[lv, np.round(uv * 1e6).astype(np.int64)]
        _u, first, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
        pos = V[lv[first]]
        nrm = N[lv[first]]
        uvo = uv[first]
        tris = inv.reshape(-1, 3)
        np.savez(W / ("lod%d.npz" % k), pos=np.stack([pos[:, 0], pos[:, 2], -pos[:, 1]], 1),
                 nrm=np.stack([nrm[:, 0], nrm[:, 2], -nrm[:, 1]], 1), uv=np.c_[uvo[:, 0], 1 - uvo[:, 1]], tris=tris)
        print("LOD", k, len(pos), len(tris), flush=True)
    (W / "bake.json").write_text(json.dumps({"islands": int(nis), "texels_per_uv": dens, "size": size}))
    print("BAKE done")


if __name__ == "__main__":
    cmd, W, rest = args()
    {"model": model, "preview": preview, "bake": bake}[cmd](W, rest)
