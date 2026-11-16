#!/usr/bin/env python
"""D2R HD models (`.model`, RAD Granny GR2) to glTF 2.0 binary (`.glb`) and back (docs/hd-effects-authoring.md section 8).

A `.model` holds Meshes (vertices, triangles, material bindings, bone bindings) behind one or more Models; tools/d2r_model.py
reads and writes the whole object tree. `export` writes every mesh of the file into a `.glb` that Blender (File > Import >
glTF 2.0) and other open tools read: positions, normals, tangents and UVs as floats, one primitive per triangle group
(material), the material's texture game paths as image URIs plus `extras.d2r.maps` (usage -> game path), and the skin of a
skinned part as the custom attributes `_JOINTS` / `_WEIGHTS` (indices into `extras.d2r.bones`, the mesh's bone bindings).
`import` puts the meshes of an edited `.glb` back into the original file (the donor, which keeps everything the `.glb` does
not carry: skeleton, materials, model placement, extended data): a mesh is matched by name, its vertices and triangles are
replaced (any count), its bounds and bone boxes recomputed, and its texture paths taken from the `.glb` material.

  py -3 tools/hd_gltf.py export <file.model> <out.glb>
  py -3 tools/hd_gltf.py import <donor.model> <in.glb> <out.model>
  py -3 tools/hd_gltf.py edit <in.glb> <out.glb> [--scale S] [--offset X Y Z] [--map USAGE=game/path.texture ...]
  py -3 tools/hd_gltf.py check <file-or-folder>...   (export -> import of every .model: the tree must come back equal)

Vertex encoding (static and skinned): Position int16[4], value = q / 32767 * VertexScale (mesh ExtendedData; w =
round(log2(VertexScale) / 13 * 32767)), Normal / Tangent int8[4] / 127 (tangent w = handedness), UV raw half floats, skinned
parts BoneIndices / BoneWeights uint8[4] (weights sum 255). New vertices with no `_JOINTS` take the skin of the nearest
original vertex. A new game path for the file (not an override of D2R's own) needs a data/hd/model_lod_desc.bin entry
(tools/model_lod_desc.py, docs/d2r-addresses.md section 23).
"""
import argparse
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_model as dm  # noqa: E402

GLB_MAGIC, CHUNK_JSON, CHUNK_BIN = 0x46546C67, 0x4E4F534A, 0x004E4942
FLOAT, UBYTE, UINT = 5126, 5121, 5125
COMP = {FLOAT: np.float32, UBYTE: np.uint8, UINT: np.uint32, 5123: np.uint16, 5122: np.int16, 5120: np.int8}
NCOMP = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


# ---- vertex codec -------------------------------------------------------------------------------------------------------------

def vertex_scale_of(mesh) -> float:
    ed = mesh["ExtendedData"].obj if mesh.get("ExtendedData") is not None else None
    return float(ed["VertexScale"]) if ed is not None and "VertexScale" in ed.f else 1.0


def decode_mesh(mesh) -> dict:
    """Float arrays of a mesh: pos (N,3), nrm (N,3), tan (N,4), uv (N,2), tris (M,3), groups [(material, first, count)],
    joints / weights (N,4) when skinned."""
    vs = mesh["PrimaryVertexData"]["Vertices"].obj
    names = vs[0].td.members if vs else []
    has = {m.name for m in names}
    s = vertex_scale_of(mesh)
    out = {}
    p = np.array([v["Position"][:3] for v in vs], float).reshape(-1, 3)
    out["pos"] = p / 32767.0 * s
    out["nrm"] = (np.array([v["Normal"][:3] for v in vs], float).reshape(-1, 3) / 127.0 if "Normal" in has
                  else np.zeros((len(vs), 3)))
    out["tan"] = (np.array([v["Tangent"] for v in vs], float).reshape(-1, 4) / 127.0 if "Tangent" in has
                  else np.zeros((len(vs), 4)))
    out["uv"] = (np.array([v["TextureCoordinates0"] for v in vs], np.uint16).reshape(-1, 2).view(np.float16).astype(np.float32)
                 if "TextureCoordinates0" in has else np.zeros((len(vs), 2), np.float32))
    if "DiffuseColor0" in has:
        out["col"] = np.array([v["DiffuseColor0"] for v in vs], int).reshape(-1, 4)
    if "BoneIndices" in has:
        out["joints"] = np.array([v["BoneIndices"] for v in vs], int).reshape(-1, 4)
        out["weights"] = np.array([v["BoneWeights"] for v in vs], int).reshape(-1, 4)
    topo = mesh["PrimaryTopology"]
    idx = topo["Indices16"] or topo["Indices"]
    key = "Int16" if topo["Indices16"] else "Int32"
    out["tris"] = np.array([i[key] for i in idx], int).reshape(-1, 3)
    if key == "Int16":  # the 16-bit indices are an Int16 member: unsigned values above 32767 read as negative
        out["tris"] &= 0xFFFF
    out["groups"] = [(g["MaterialIndex"], g["TriFirst"], g["TriCount"]) for g in topo["Groups"]]
    return out


def encode_vertices(vtd, pos, nrm, tan, uv, joints, weights, scale, w=None, col=None, like=None):
    """Vertex Objs of struct type `vtd` (only the members it has) for float geometry; w: the Position w to keep (default from
    the scale); col (N,4) uint8 vertex colours; like: per vertex an original vertex whose other members are copied."""
    has = {m.name for m in vtd.members}
    q = np.clip(np.round(np.asarray(pos, float) / scale * 32767), -32767, 32767).astype(int)
    if w is None:
        w = int(round(math.log2(scale) / 13 * 32767))
    n8 = np.clip(np.round(np.asarray(nrm, float) * 127), -127, 127).astype(int)
    t8 = np.clip(np.round(np.asarray(tan, float) * 127), -127, 127).astype(int)
    h = np.asarray(uv, np.float32).astype(np.float16).view(np.uint16).astype(int)
    out = []
    for i in range(len(q)):
        f = {}
        if "Position" in has:
            f["Position"] = [int(q[i, 0]), int(q[i, 1]), int(q[i, 2]), w]
        if "BoneWeights" in has:
            f["BoneWeights"] = [int(x) for x in weights[i]]
        if "BoneIndices" in has:
            f["BoneIndices"] = [int(x) for x in joints[i]]
        if "Normal" in has:
            f["Normal"] = [int(n8[i, 0]), int(n8[i, 1]), int(n8[i, 2]), 0]
        if "Tangent" in has:
            f["Tangent"] = [int(x) for x in t8[i]]
        if "TextureCoordinates0" in has:
            f["TextureCoordinates0"] = [int(h[i, 0]), int(h[i, 1])]
        if "DiffuseColor0" in has and col is not None:
            f["DiffuseColor0"] = [int(x) for x in col[i]]
        base = like[i].f if like is not None else {}
        out.append(dm.Obj(vtd, {m.name: f[m.name] if m.name in f else base.get(m.name) for m in vtd.members}))
    return out


def norm_weights(wt) -> np.ndarray:
    """uint8 weights that add up to exactly 255 per vertex (from any non-negative floats or ints)."""
    wt = np.asarray(wt, float)
    wt = wt / np.maximum(wt.sum(1, keepdims=True), 1e-12)
    w8 = np.round(wt * 255).astype(int)
    w8[np.arange(len(w8)), w8.argmax(1)] += 255 - w8.sum(1)
    return w8


def tangents(pos, nrm, uv, tris) -> np.ndarray:
    """(N,4) tangents with handedness from the UV layout (for a .glb without TANGENT)."""
    import d2r_mesh
    t, hand = d2r_mesh.tangents(np.asarray(pos, float), np.asarray(nrm, float), np.asarray(uv, float), np.asarray(tris, int))
    return np.concatenate([t, np.asarray(hand, float)[:, None]], 1)


# ---- glb container ------------------------------------------------------------------------------------------------------------

class _Buf:
    def __init__(self):
        self.data = bytearray()
        self.views, self.accessors = [], []

    def add(self, arr, comp, kind, target=None, minmax=False) -> int:
        a = np.ascontiguousarray(np.asarray(arr, COMP[comp]))
        while len(self.data) % 4:
            self.data.append(0)
        view = {"buffer": 0, "byteOffset": len(self.data), "byteLength": a.nbytes}
        if target:
            view["target"] = target
        self.data += a.tobytes()
        self.views.append(view)
        acc = {"bufferView": len(self.views) - 1, "componentType": comp, "count": int(a.shape[0]), "type": kind}
        if minmax and len(a):
            acc["min"] = [float(x) for x in a.reshape(len(a), -1).min(0)]
            acc["max"] = [float(x) for x in a.reshape(len(a), -1).max(0)]
        self.accessors.append(acc)
        return len(self.accessors) - 1


def write_glb(gltf: dict, binary: bytes) -> bytes:
    gltf = dict(gltf)
    gltf["buffers"] = [{"byteLength": len(binary)}]
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binary = bytes(binary) + b"\0" * (-len(binary) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    return (struct.pack("<III", GLB_MAGIC, 2, total) + struct.pack("<II", len(js), CHUNK_JSON) + js
            + struct.pack("<II", len(binary), CHUNK_BIN) + binary)


def read_glb(data: bytes) -> tuple[dict, bytes]:
    magic, ver, total = struct.unpack_from("<III", data, 0)
    if magic != GLB_MAGIC or ver != 2:
        raise ValueError("not a glTF 2.0 binary")
    off, gltf, binary = 12, None, b""
    while off < min(total, len(data)):
        n, kind = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + n]
        if kind == CHUNK_JSON:
            gltf = json.loads(chunk)
        elif kind == CHUNK_BIN:
            binary = chunk
        off += 8 + n
    if gltf is None:
        raise ValueError("glb without a JSON chunk")
    return gltf, binary


def accessor(gltf: dict, binary: bytes, i: int) -> np.ndarray:
    a = gltf["accessors"][i]
    v = gltf["bufferViews"][a["bufferView"]]
    dt = np.dtype(COMP[a["componentType"]])
    n = NCOMP[a["type"]]
    start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = v.get("byteStride", 0) or dt.itemsize * n
    raw = np.frombuffer(binary, np.uint8, count=stride * (a["count"] - 1) + dt.itemsize * n if a["count"] else 0, offset=start)
    if stride == dt.itemsize * n:
        out = raw.view(dt).reshape(a["count"], n)
    else:
        out = np.stack([raw[k * stride: k * stride + dt.itemsize * n].view(dt) for k in range(a["count"])])
    if a.get("normalized"):
        out = out.astype(float) / float(np.iinfo(dt).max)
    return out if n > 1 else out.reshape(-1)


# ---- model <-> glb ------------------------------------------------------------------------------------------------------------

def _maps(material) -> dict:
    return {mp["Usage"]: ((mp["Map"] or {}).get("Texture") or {}).get("FromFileName") if mp["Map"] else None
            for mp in (material["Maps"] if material is not None else [])}


def export_glb(tree) -> bytes:
    """A .glb of every mesh of a parsed .model tree."""
    buf = _Buf()
    gltf = {"asset": {"version": "2.0", "generator": "D2R-XL 2012 tools/hd_gltf.py"}, "scene": 0,
            "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [], "textures": [], "images": []}
    images = {}
    for mi, mesh in enumerate(tree["Meshes"]):
        d = decode_mesh(mesh)
        att = {"POSITION": buf.add(d["pos"], FLOAT, "VEC3", 34962, minmax=True),
               "NORMAL": buf.add(d["nrm"], FLOAT, "VEC3", 34962),
               "TANGENT": buf.add(d["tan"], FLOAT, "VEC4", 34962),
               "TEXCOORD_0": buf.add(d["uv"], FLOAT, "VEC2", 34962)}
        if "col" in d:
            att["COLOR_0"] = buf.add(d["col"], UBYTE, "VEC4", 34962)
            buf.accessors[att["COLOR_0"]]["normalized"] = True
        if "joints" in d:
            att["_JOINTS"] = buf.add(d["joints"], UBYTE, "VEC4", 34962)
            att["_WEIGHTS"] = buf.add(d["weights"], UBYTE, "VEC4", 34962)
        prims = []
        for (mat, first, count) in d["groups"]:
            binding = mesh["MaterialBindings"][mat] if mat < len(mesh["MaterialBindings"]) else None
            material = binding["Material"] if binding is not None else None
            maps = _maps(material)
            m = {"name": (material["Name"] if material is not None else None) or f"material_{mat}",
                 "pbrMetallicRoughness": {"metallicFactor": 0.0},
                 "extras": {"d2r": {"maps": maps, "binding": mat}}}
            alb = maps.get("AlbedoTexture")
            if alb:
                if alb not in images:
                    gltf["images"].append({"uri": alb, "name": Path(alb).stem})
                    gltf["textures"].append({"source": len(gltf["images"]) - 1})
                    images[alb] = len(gltf["textures"]) - 1
                m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": images[alb]}
            gltf["materials"].append(m)
            idx = d["tris"][first: first + count].reshape(-1)
            prims.append({"attributes": att, "indices": buf.add(idx, UINT, "SCALAR", 34963),
                          "material": len(gltf["materials"]) - 1})
        gltf["meshes"].append({"name": mesh["Name"], "primitives": prims,
                               "extras": {"d2r": {"bones": [b["BoneName"] for b in mesh["BoneBindings"]],
                                                  "vertex_scale": vertex_scale_of(mesh)}}})
        gltf["nodes"].append({"name": mesh["Name"], "mesh": mi})
        gltf["scenes"][0]["nodes"].append(mi)
    for k in ("materials", "textures", "images"):
        if not gltf[k]:
            del gltf[k]
    gltf["bufferViews"], gltf["accessors"] = buf.views, buf.accessors
    return write_glb(gltf, bytes(buf.data))


def glb_meshes(gltf: dict, binary: bytes) -> dict:
    """name -> {pos, nrm, tan|None, uv, tris, groups [(binding, first, count)], joints|None, weights|None, maps per group}.
    Primitives that share their attribute accessors share one vertex list (as written by export); others are appended."""
    out = {}
    for me in gltf.get("meshes", []):
        verts, cols, tris, groups, maps = {}, {k: [] for k in ("pos", "nrm", "tan", "uv", "col", "joints", "weights")}, [], [], []
        base = 0
        for p in me["primitives"]:
            if p.get("mode", 4) != 4:
                raise ValueError(f"mesh {me.get('name')}: only triangle lists are supported")
            att = p["attributes"]
            key = tuple(sorted(att.items()))
            if key not in verts:
                n = len(accessor(gltf, binary, att["POSITION"]))
                verts[key] = base
                cols["pos"].append(accessor(gltf, binary, att["POSITION"]).astype(float))
                cols["nrm"].append(accessor(gltf, binary, att["NORMAL"]).astype(float) if "NORMAL" in att else None)
                cols["tan"].append(accessor(gltf, binary, att["TANGENT"]).astype(float) if "TANGENT" in att else None)
                cols["uv"].append(accessor(gltf, binary, att["TEXCOORD_0"]).astype(np.float32) if "TEXCOORD_0" in att
                                  else np.zeros((n, 2), np.float32))
                cols["col"].append(accessor(gltf, binary, att["COLOR_0"]) if "COLOR_0" in att else None)
                cols["joints"].append(accessor(gltf, binary, att["_JOINTS"]).astype(int) if "_JOINTS" in att else None)
                cols["weights"].append(accessor(gltf, binary, att["_WEIGHTS"]).astype(float) if "_WEIGHTS" in att else None)
                base += n
            off = verts[key]
            idx = (accessor(gltf, binary, p["indices"]).astype(int) if "indices" in p
                   else np.arange(len(accessor(gltf, binary, att["POSITION"])))) + off
            mat = gltf.get("materials", [])[p["material"]] if "material" in p else {}
            d2r = (mat.get("extras") or {}).get("d2r") or {}
            groups.append((d2r.get("binding", len(groups)), sum(len(t) for t in tris), len(idx) // 3))
            tris.append(idx.reshape(-1, 3))
            mp = dict(d2r.get("maps") or {})
            tex = (mat.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
            if tex is not None:
                uri = gltf["images"][gltf["textures"][tex["index"]]["source"]].get("uri")
                if uri and uri.startswith("data/hd/"):
                    mp["AlbedoTexture"] = uri
            maps.append(mp)
        d = {"pos": np.concatenate(cols["pos"]), "uv": np.concatenate(cols["uv"]),
             "tris": np.concatenate(tris) if tris else np.zeros((0, 3), int), "groups": groups, "maps": maps,
             "bones": ((me.get("extras") or {}).get("d2r") or {}).get("bones")}
        for k in ("nrm", "tan", "col", "joints", "weights"):
            d[k] = None if any(c is None for c in cols[k]) else np.concatenate(cols[k])
        out[me.get("name")] = d
    return out


def _vertex_normals(pos, tris):
    n = np.zeros_like(pos)
    f = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    for k in range(3):
        np.add.at(n, tris[:, k], f)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def put_mesh(tree, mesh, g: dict, old: dict) -> None:
    """Replace the geometry of `mesh` (in `tree`) with glb mesh `g`; `old` is decode_mesh(mesh) before the change."""
    pos, tris = g["pos"], g["tris"]
    if len(pos) > 65535 and mesh["PrimaryTopology"]["Indices16"]:
        raise ValueError(f"mesh {mesh['Name']}: {len(pos)} vertices do not fit its 16-bit indices")
    nrm = g["nrm"] if g["nrm"] is not None else _vertex_normals(pos, tris)
    tan = g["tan"] if g["tan"] is not None else tangents(pos, nrm, g["uv"], tris)
    skinned = "joints" in old
    if skinned:
        if g["joints"] is not None and g["weights"] is not None:
            joints, weights = g["joints"], g["weights"]
            if g["weights"].max(initial=0) <= 1.0 + 1e-6:  # float weights (an editor that rewrote them)
                weights = norm_weights(weights)
            elif not (np.asarray(weights).sum(1) == 255).all():
                weights = norm_weights(weights)
        else:  # new geometry without a skin: each vertex takes the skin of the nearest original vertex
            near = np.argmin(((pos[:, None, :] - old["pos"][None, :, :]) ** 2).sum(2), axis=1)
            joints, weights = old["joints"][near], old["weights"][near]
    else:
        joints = weights = None
    s = vertex_scale_of(mesh)
    vd = mesh["PrimaryVertexData"]
    w = vd["Vertices"].obj[0]["Position"][3] if vd["Vertices"].obj else None
    if np.abs(pos).max(initial=0) > s * (1 + 1e-6):  # no longer fits the quantisation range: grow it
        s, w = float(np.abs(pos).max()) * 1.0001, None
    olds = vd["Vertices"].obj
    vtd = olds[0].td
    if len(pos) == len(old["pos"]):
        like = olds
    else:  # members the glb does not carry come from the nearest original vertex
        like = [olds[k] for k in np.argmin(((pos[:, None, :] - old["pos"][None, :, :]) ** 2).sum(2), axis=1)]
    col = None
    if "col" in old:
        c = g.get("col")
        if c is None:
            col = np.array([v["DiffuseColor0"] for v in like], int).reshape(-1, 4)
        else:
            c = np.asarray(c)
            col = (np.clip(np.round(c * 255), 0, 255) if c.dtype.kind == "f" else c).astype(int)
            if col.shape[1] == 3:
                col = np.concatenate([col, np.full((len(col), 1), 255)], 1)
    vd["Vertices"].obj = encode_vertices(vtd, pos, nrm, tan, g["uv"], joints, weights, s, w, col, like)
    topo = mesh["PrimaryTopology"]
    if topo["Indices16"]:
        td = topo["Indices16"][0].td
        topo["Indices16"] = [dm.Obj(td, {"Int16": int(i) - 65536 if i > 32767 else int(i)}) for i in tris.reshape(-1)]
    else:
        td = topo["Indices"][0].td
        topo["Indices"] = [dm.Obj(td, {"Int32": int(i)}) for i in tris.reshape(-1)]
    tmpl = topo["Groups"][0]
    topo["Groups"] = [dm.Obj(tmpl.td, {**tmpl.f, "MaterialIndex": int(b), "TriFirst": int(f), "TriCount": int(c)})
                      for (b, f, c) in g["groups"]]
    changed = len(pos) != len(old["pos"]) or len(tris) != len(old["tris"]) or not np.array_equal(tris, old["tris"])
    if changed:  # adjacency tables (empty in D2R's files) would no longer match
        for k in ("VertexToVertexMap", "VertexToTriangleMap", "SideToNeighborMap", "PolygonIndexStarts", "PolygonIndices",
                  "BonesForTriangle", "TriangleToBoneIndices"):
            if topo.get(k):
                topo[k] = []
    if changed or not np.allclose(pos, old["pos"], atol=1e-7):
        inv = {b["Name"]: np.array(b["InverseWorldTransform"], float).reshape(4, 4)
               for sk in tree["Skeletons"] for b in sk["Bones"]}
        for bi, b in enumerate(mesh["BoneBindings"]):
            sel = ((joints == bi) & (weights > 0)).any(1) if skinned else np.ones(len(pos), bool)
            pts = pos[sel] if sel.any() else pos
            if b["BoneName"] in inv:
                m = inv[b["BoneName"]]
                pts = pts @ m[:3, :3] + m[3, :3]  # the box is in the bone's own space (row vectors)
            b["OBBMin"] = [float(x) for x in pts.min(0)]
            b["OBBMax"] = [float(x) for x in pts.max(0)]
        ed = mesh["ExtendedData"].obj if mesh.get("ExtendedData") is not None else None
        if ed is not None:
            if "bbMin" in ed.f:
                ed["bbMin"] = [float(x) for x in pos.min(0)]
                ed["bbMax"] = [float(x) for x in pos.max(0)]
            if "VertexScale" in ed.f:
                ed["VertexScale"] = float(s)
    for (b, _f, _c), mp in zip(g["groups"], g["maps"]):
        if b >= len(mesh["MaterialBindings"]) or not mp:
            continue
        for slot in (mesh["MaterialBindings"][b]["Material"] or {"Maps": []})["Maps"]:
            if slot["Map"] is None or not (slot["Map"].get("Texture")):
                continue
            want = mp.get(slot["Usage"])
            if want and want != slot["Map"]["Texture"]["FromFileName"]:
                slot["Map"]["Texture"]["FromFileName"] = want  # the file's Textures entry (shared by every map that uses it)


def import_glb(tree, glb: bytes) -> list[str]:
    """Put the meshes of `glb` into the parsed donor `tree` (by mesh name). Returns the names replaced."""
    gltf, binary = read_glb(glb)
    meshes = glb_meshes(gltf, binary)
    by_name = {m["Name"]: m for m in tree["Meshes"]}
    unknown = [n for n in meshes if n not in by_name]
    if unknown:
        raise ValueError(f"glb meshes not in the donor: {unknown} (the donor has {sorted(by_name)})")
    done = []
    for name, g in meshes.items():
        mesh = by_name[name]
        put_mesh(tree, mesh, g, decode_mesh(mesh))
        done.append(name)
    return done


def edit_glb(glb: bytes, scale: float = 1.0, offset=(0.0, 0.0, 0.0), maps: dict | None = None) -> bytes:
    """The scripted stand-in for an edit in Blender: every position scaled about the origin then moved, texture paths set."""
    gltf, binary = read_glb(glb)
    binary = bytearray(binary)
    done = set()
    for me in gltf.get("meshes", []):
        for p in me["primitives"]:
            i = p["attributes"]["POSITION"]
            if i in done:
                continue
            done.add(i)
            a = gltf["accessors"][i]
            v = gltf["bufferViews"][a["bufferView"]]
            start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
            if v.get("byteStride", 12) != 12 or a["componentType"] != FLOAT:
                raise ValueError("edit expects tightly packed float positions (as export writes them)")
            arr = np.frombuffer(bytes(binary[start: start + 12 * a["count"]]), np.float32).reshape(-1, 3).astype(float)
            arr = arr * scale + np.asarray(offset, float)
            binary[start: start + 12 * a["count"]] = arr.astype(np.float32).tobytes()
            a["min"], a["max"] = [float(x) for x in arr.min(0)], [float(x) for x in arr.max(0)]
    for m in gltf.get("materials", []):
        if maps:
            m.setdefault("extras", {}).setdefault("d2r", {}).setdefault("maps", {}).update(maps)
            alb = maps.get("AlbedoTexture")
            tex = (m.get("pbrMetallicRoughness") or {}).get("baseColorTexture")
            if alb and tex is not None:
                gltf["images"][gltf["textures"][tex["index"]]["source"]]["uri"] = alb
    return write_glb(gltf, bytes(binary))


# ---- files --------------------------------------------------------------------------------------------------------------------

def load(path):
    g = dm.Gr2File.read(Path(path).read_bytes())
    return g, dm.parse_tree(g)


def save(gr2, tree, path) -> int:
    out = dm.Writer(gr2).build(tree).write()
    dm.parse_tree(dm.Gr2File.read(out))  # well formed
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    return len(out)


def roundtrip(data: bytes) -> str | None:
    """export -> import of unchanged geometry; None when the tree comes back equal, else the first difference."""
    g = dm.Gr2File.read(data)
    tree = dm.parse_tree(g)
    if not tree["Meshes"]:
        return None
    glb = export_glb(tree)
    g2 = dm.Gr2File.read(data)
    tree2 = dm.parse_tree(g2)
    import_glb(tree2, glb)
    out = dm.Writer(g2).build(tree2).write()
    return dm.tree_equal(dm.parse_tree(dm.Gr2File.read(out)), dm.parse_tree(dm.Gr2File.read(data)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("export"); a.add_argument("model"); a.add_argument("out")
    a = sub.add_parser("import"); a.add_argument("donor"); a.add_argument("glb"); a.add_argument("out")
    a = sub.add_parser("edit"); a.add_argument("glb"); a.add_argument("out")
    a.add_argument("--scale", type=float, default=1.0); a.add_argument("--offset", type=float, nargs=3, default=(0, 0, 0))
    a.add_argument("--map", action="append", default=[], help="USAGE=data/hd/....texture (AlbedoTexture, ORMTexture ...)")
    a = sub.add_parser("check"); a.add_argument("paths", nargs="+")
    args = ap.parse_args()
    if args.cmd == "export":
        _g, tree = load(args.model)
        b = export_glb(tree)
        Path(args.out).write_bytes(b)
        print(f"{args.out}: {len(tree['Meshes'])} meshes, {len(b)} bytes")
    elif args.cmd == "import":
        g, tree = load(args.donor)
        names = import_glb(tree, Path(args.glb).read_bytes())
        print(f"{args.out}: {save(g, tree, args.out)} bytes; meshes replaced: {', '.join(names)}")
    elif args.cmd == "edit":
        maps = dict(m.split("=", 1) for m in args.map)
        Path(args.out).write_bytes(edit_glb(Path(args.glb).read_bytes(), args.scale, args.offset, maps))
        print(f"{args.out}: scale {args.scale}, offset {tuple(args.offset)}, maps {maps or '-'}")
    else:
        files = [f for p in args.paths for f in (sorted(Path(p).rglob("*.model")) if Path(p).is_dir() else [Path(p)])]
        bad = 0
        for f in files:
            if f.stat().st_size == 0:  # D2R ships empty placeholders for LODs it does not have
                continue
            try:
                diff = roundtrip(f.read_bytes())
            except Exception as e:  # noqa: BLE001 (report every file)
                diff = f"{type(e).__name__}: {e}"
            if diff:
                bad += 1
                if bad <= 20:
                    print(f"{f}: {diff}")
        print(f"{len(files)} files, {bad} differ")
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
