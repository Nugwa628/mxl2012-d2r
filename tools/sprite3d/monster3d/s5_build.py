"""Stage 5: skin the LOD set to a stock skeleton and write the HD unit (models, textures, unit JSON) as an overlay.

  venv python s5_build.py [--token T] <mesh_lods.npz> <albedo.png> <overlay dir> [--gain 1.25] [--part part.png]
                          [--body-rough 0.82] [--cap-rough 0.82] [--body-gain 1.0] [--normal normal.png] [--axe axe.npz] [--axe-length 7.0] [--axe-bone R_hand_bind_jnt]
                          [--strip 0.125 --corpse-albedo pale.png [--corpse-gain 1.0]] [--cap-scale 1.0]

What differs per monster is in MONSTERS: the donor unit, the rig profile of tools/sprite3d/rig_fit.py (capsule weights,
segments carried to the donor's bind pose), the height in game units, and:
- Hardliner (`~k`, donor Hell Bovine): the axe (--axe) is a rigid piece on the donor's right hand bone R_hand_bind_jnt. The
  donor's own halberd hangs on R_weapon_attach, but that bone is not in the skeleton copy inside the torso model, so a mesh
  cannot be bound to it. The axe is placed where R_weapon_attach holds a weapon in the bind pose: along that bone's own y axis
  like D2R's hell_bovine_battle_axe (head up the shaft, blades in the bone's yz plane, grip at the bone).
- Glowing Fungus (`2(`, donor Dried Corpse mummy1): everything above the plane y = 0.77 + 0.31 z of the upright mesh (height 1)
  is the cap and follows one bone alone, so the walk cannot tear it: `cap_bone` (the donor's jaw, a child of the head that
  no body vertex uses) when the unit gets its own death clip in which the cap falls off (s5_death.py), else the head. --part (project_texture.py's part.png) and
  --body-rough give the body another roughness than the cap in the ORM map (0.82 = the flat default; --cap-rough the cap's), and --body-gain scales
  the body's albedo alone (after --gain), to set its level against classic without touching the cap. --normal takes a
  tangent-space normal map in the albedo's UV layout instead of the flat one (s3_detail.py; the vertex tangents follow the UVs).
--strip F with --corpse-albedo: room in the atlas for s5_death.py's corpse shell. Every UV's u is scaled by (1 - F) and every
map squeezed the same way (common.squash_u), and the top of the right strip (F x F of the atlas) takes a miniature of the
whole corpse albedo (in the old layout, times --corpse-gain), so a copy of the body can show other colours than the live body
with the same material. The normal map is flat there and the ORM the body's. s5_glow.py takes the same --strip.
--cap-scale S: the cap (the rigid part above the cap plane) scaled by S about the centre of its base (x, z: its mean; y: its
lowest point), after the split, so it sits on the stem as before. The Fungus cap was 24 % wider on screen than classic's.
The final albedo (after --strip and the miniature) is also saved as albedo_final.png beside build.json, for previews.
The overlay is laid out like the mod's data folder:
  hd/character/enemy/mxl_m3d_<name>.json
  hd/character/enemy/mxl/m3d/<name>/torso_lod0..4.model, <name>_alb|nrm|orm|sss|msk.texture (the maps the donor's material has)
The index files (monsters.json, model_lod_desc.bin) depend on the installed mod and are added by g6_gamerun.py.
Writes <overlay>/../build.json (counts, sizes, bounds).
"""
import json
import sys
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

import common

sys.path.insert(0, str(common.WT / "tools"))
sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import d2r_mesh  # noqa: E402
import d2r_texture  # noqa: E402
import render_soft  # noqa: E402
import rig_fit  # noqa: E402
import skel_info  # noqa: E402

D2R = common.EV / "d2r" / "data"
# K: the mesh (height 1) in game units; cap: (c, m) with the rigid head part above y = c + m z; keep: donor maps left as they
# are (the Hell Bovine's tint mask is the shared all-black common_ktint; the Dried Corpse's is its own, in its own UV layout)
MONSTERS = {
    "~k": dict(donor="hellbovine", profile="hellbovine", K=9.0, keep={"MaskTexture"}),
    "2(": dict(donor="mummy1", profile="mummy1", K=9.2, cap=(0.77, 0.31), cap_bone="jaw"),
}
KINDS = {"AlbedoTexture": "alb", "NormalTexture": "nrm", "ORMTexture": "orm", "ThicknessTexture": "sss", "MaskTexture": "msk"}


def split_cap(pos, nrm, uv, tris, c, m):
    """The cap comes off in the death clip, so no triangle may join it to the body: a triangle with corners on both sides
    goes to the side most of its corners are on, and its other corners are copied for it (same place, normal and uv)."""
    cap = pos[:, 1] > c + m * pos[:, 2]
    side = cap[tris]
    on_cap = side.sum(1) >= 2
    mixed = side.any(1) & ~side.all(1)
    pos, nrm, uv, tris = list(pos), list(nrm), list(uv), tris.copy()
    copies = {}
    for f in np.nonzero(mixed)[0]:
        for k in range(3):
            v = tris[f, k]
            if cap[v] != on_cap[f]:
                key = (v, bool(on_cap[f]))
                if key not in copies:
                    copies[key] = len(pos)
                    pos.append(pos[v])
                    cap = np.append(cap, on_cap[f])
                    nrm.append(nrm[v])
                    uv.append(uv[v])
                tris[f, k] = copies[key]
    return np.array(pos), np.array(nrm), np.array(uv), tris, cap


def write_torso(k, donor_dir, P, N, U, T, I, Wt, names, out, folder, stem, keep=()):
    """torso_lod<k>.model from the donor's: its body mesh replaced, every map pointed at the unit's own textures.
    Returns (bytes, the maps of the material, the usages written)."""
    gr2, tree = d2r_mesh.load_model(D2R / donor_dir / ("torso_lod%d.model" % k))
    # the body mesh has another name in the lower LODs: the one with the most vertices
    donor_mesh = max(tree["Meshes"], key=lambda m: len(m["PrimaryVertexData"]["Vertices"].obj or []))["Name"]
    d2r_mesh.replace_with_mesh(tree, donor_mesh, P, N, U, T, bone_idx=I, weights=Wt, bones=names)
    maps = next(m for m in tree["Meshes"] if m["Name"] == donor_mesh)["MaterialBindings"][0]["Material"]["Maps"]
    used = [mp["Usage"] for mp in maps if mp["Map"].get("Texture") and mp["Usage"] in KINDS and mp["Usage"] not in keep]
    d2r_mesh.set_maps(tree, donor_mesh, {u: "%s_%s.texture" % (stem, KINDS[u]) for u in used})
    size = d2r_mesh.write_model(gr2, tree, out / folder / ("torso_lod%d.model" % k))
    return size, maps, used


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    cfg = MONSTERS[common.TOKEN]
    name, donor, K = common.NAME, cfg["donor"], cfg["K"]
    unit_name, folder = "mxl_m3d_" + name, "hd/character/enemy/mxl/m3d/" + name
    model, donor_dir = "data/" + folder + "/torso.model", "hd/character/enemy/" + donor
    lods, out = np.load(a[0]), Path(a[2])
    gain, axe_len, axe_bone = float(opt("--gain", "1.25")), float(opt("--axe-length", "7.0")), opt("--axe-bone", "R_hand_bind_jnt")
    axe = np.load(opt("--axe", "")) if "--axe" in a else None
    profile = rig_fit.PROFILES[cfg["profile"]]
    bones = skel_info.bones(D2R / donor_dir / "skeleton" / (donor + ".skeleton"))
    if axe is not None:
        world = np.array(next(b for b in bones if b["name"] == "R_weapon_attach")["world"])
        rot = world[:3, :3] / np.linalg.norm(world[:3, :3], axis=1, keepdims=True)
        # axe: upright-frame position -> its local frame (both are affine images of the generated piece)
        A, *_ = np.linalg.lstsq(np.hstack([axe["pos"], np.ones((len(axe["pos"]), 1))]), axe["local"], rcond=None)
    report = {"unit": unit_name, "donor": donor, "u": profile["u"], "lods": [], "files": {}}
    if axe is not None:
        report["axe_bone"] = axe_bone
    stem = "data/" + folder + "/" + name
    bounds = used = None
    strip = float(opt("--strip", "0")) if "--corpse-albedo" in a else 0.0
    for k in range(5):
        s = "" if k == 0 else "_%d" % k
        pos, nrm, uv, tris = lods["pos" + s], lods["nrm" + s], lods["uv" + s].copy(), lods["tris" + s]
        uv[:, 0] *= 1 - strip
        if "cap" in cfg and cfg.get("cap_bone"):
            pos, nrm, uv, tris, cap_mask = split_cap(pos, nrm, uv, tris, *cfg["cap"])
        else:
            cap_mask = None
        cap_scale = float(opt("--cap-scale", "1.0"))
        if cap_mask is not None and cap_scale != 1.0:
            base = np.array([pos[cap_mask, 0].mean(), pos[cap_mask, 1].min(), pos[cap_mask, 2].mean()])
            pos = pos.copy()
            pos[cap_mask] = base + cap_scale * (pos[cap_mask] - base)
            report["cap_scale"] = cap_scale
        is_axe = (uv[:, 1] > 0.75) if axe is not None else np.zeros(len(pos), bool)
        fa = is_axe[tris]
        if (fa.any(1) & ~fa.all(1)).any():
            raise SystemExit("lod %d: a triangle joins the body and the axe" % k)
        bi = np.nonzero(~is_axe)[0]
        ai = np.nonzero(is_axe)[0]
        remap = -np.ones(len(pos), int)
        remap[bi] = np.arange(len(bi))
        tb = remap[tris[~fa.all(1)]]
        rigid = None
        if "cap" in cfg:
            c, m = cfg["cap"]
            rigid = {"head": cap_mask[bi] if cap_mask is not None else pos[bi, 1] > c + m * pos[bi, 2]}
        bp, bn, bidx, bw, names, inst, cols = rig_fit.fit(profile, bones, pos[bi] * K, nrm[bi], tb, rigid=rigid)
        names = list(names)
        if rigid and cfg.get("cap_bone"):
            # the cap was carried with the head (same place in the bind pose); it is bound to its own bone instead
            names.append(cfg["cap_bone"])
            bidx = bidx.copy()
            bidx[rigid["head"], 0] = len(names) - 1
        P, N, I, Wt, U = bp, bn, bidx, bw, uv[bi]
        ta = np.zeros((0, 3), int)
        if axe is not None:
            local = np.hstack([pos[ai], np.ones((len(ai), 1))]) @ A
            ap = (local * axe_len) @ rot + world[3, :3]
            remap[ai] = len(bi) + np.arange(len(ai))
            ta = remap[tris[fa.all(1)]] - len(bi)
            names.append(axe_bone)
            P = np.vstack([bp, ap])
            N = np.vstack([bn, render_soft.vertex_normals(ap, ta)])
            I = np.vstack([bidx, np.tile([len(names) - 1, 0, 0, 0], (len(ai), 1))])
            Wt = np.vstack([bw, np.tile([1.0, 0, 0, 0], (len(ai), 1))])
            U = np.vstack([uv[bi], uv[ai]])
        T = remap[tris]
        size, maps, used = write_torso(k, donor_dir, P, N, U, T, I, Wt, names, out, folder, stem, cfg.get("keep", ()))
        dest = out / folder / ("torso_lod%d.model" % k)
        # every LOD's skinned mesh, for s5_death.py (its preview and the corpse shell, which rewrites the models)
        np.savez(out.parent / ("skinned_lod%d.npz" % k), pos=P, nrm=N, uv=U, tris=T, bone_idx=I, weights=Wt, bones=np.array(names))
        if k == 0:
            bounds = (P.min(0).tolist(), P.max(0).tolist())
            report["maps"] = [(mp["Usage"], mp["Map"]["Texture"]["FromFileName"]) for mp in maps if mp["Map"].get("Texture")]
            if rigid:
                report["rigid_head_vertices"] = int(rigid["head"].sum())
        report["lods"].append({"lod": k, "vertices": len(P), "triangles": len(T), "axe_triangles": int(len(ta)),
                               "bones": len(names), "bytes": size, "deflated": len(zlib.compress(dest.read_bytes(), 6))})
        print("lod %d: %d vertices, %d triangles, %d bones, %d bytes" % (k, len(P), len(T), len(names), size), flush=True)
    report["bounds"] = bounds

    # textures: the projected albedo (BC3 with mips) and the flat maps of tools/sprite3d/make_textures.py; the ORM map takes
    # the body's roughness from --body-rough where --part says "not the part"
    alb = np.asarray(Image.open(a[1]).convert("RGB")).astype(np.float32) * gain
    body_gain = float(opt("--body-gain", "1.0"))
    if "--part" in a and body_gain != 1.0:
        part_px = np.asarray(Image.open(opt("--part", "")).convert("L").resize(alb.shape[1::-1], Image.BILINEAR))
        alb *= (body_gain + (1 - body_gain) * part_px.astype(np.float32) / 255)[..., None]
        report["body_gain"] = body_gain
    alb = np.dstack([np.clip(alb, 0, 255), np.full(alb.shape[:2], 255, np.float32)]).astype(np.uint8)
    if strip:
        alb = common.squash_u(alb, strip)
        pale = np.asarray(Image.open(opt("--corpse-albedo", "")).convert("RGB")).astype(np.float32) * float(opt("--corpse-gain", "1.0"))
        h, w = alb.shape[:2]
        mw, mh = w - int(round(w * (1 - strip))), int(round(h * strip))
        mini = np.asarray(Image.fromarray(np.clip(pale, 0, 255).astype(np.uint8)).resize((mw, mh), Image.LANCZOS))
        alb[:, w - mw:, :3] = mini.reshape(-1, 3).mean(0).astype(np.uint8)
        alb[:mh, w - mw:, :3] = mini
        alb[..., 3] = 255
        report.update(strip=strip, corpse_albedo=opt("--corpse-albedo", ""), corpse_gain=float(opt("--corpse-gain", "1.0")),
                      corpse_mini_px=[mw, mh])
    Image.fromarray(alb).save(out.parent / "albedo_final.png")
    flat = np.zeros((256, 256, 4), np.uint8)
    nrm, orm, sss, msk = flat.copy(), flat.copy(), flat.copy(), flat.copy()
    # D2R's normal maps are DXT5nm (format 61): red 255, green = y, blue 0, alpha = x, 128 = 0. Their y points UP the
    # texture (against the atlas rows) with tangents like d2r_mesh.tangents (checked on mummy1: the stored tangents and
    # handedness agree with it, and the curl of (x, y) is smallest with y up). A flat map is (255, 128, 0, 128).
    nrm[...] = (255, 128, 0, 128)
    if "--normal" in a:     # a tangent-space normal map in the albedo's UV layout (s3_detail.py), RGB, +y = +v (v down)
        src = np.asarray(Image.open(opt("--normal", "")).convert("RGB"))
        nrm = np.zeros(src.shape[:2] + (4,), np.uint8)
        nrm[..., 0] = 255
        nrm[..., 1] = 255 - src[..., 1]     # y down the rows -> y up
        nrm[..., 3] = src[..., 0]           # x -> alpha
        nrm = common.squash_u(nrm, strip, (255, 128, 0, 128))
        report["normal_map"] = opt("--normal", "")
        report["normal_encoding"] = "DXT5nm (255, 255-G, 0, R) of the RGB map"
    orm[...] = (255, 209, 0, 255)
    sss[..., 3] = msk[..., 3] = 255
    rough, cap_rough = float(opt("--body-rough", "0.82")), float(opt("--cap-rough", "0.82"))
    if "--part" in a and (rough != 0.82 or cap_rough != 0.82):
        part = common.squash_u(np.asarray(Image.open(opt("--part", "")).convert("L")), strip)
        part = np.asarray(Image.fromarray(part).resize((1024, 1024), Image.BILINEAR)).astype(np.float32) / 255
        orm = np.zeros((1024, 1024, 4), np.uint8)
        orm[...] = (255, 0, 0, 255)
        orm[..., 1] = np.round(255 * (cap_rough * part + rough * (1 - part)))
        report["cap_roughness"] = cap_rough
        report["body_roughness"] = rough
    pix = {"alb": (alb, False), "nrm": (nrm, True), "orm": (orm, True), "sss": (sss, True), "msk": (msk, True)}
    for usage in used:
        kind = KINDS[usage]
        px, linear = pix[kind]
        dest = out / folder / ("%s_%s.texture" % (name, kind))
        d2r_texture.write_bc3(dest, px, int(np.log2(px.shape[0])) + 1, linear=linear)
        report["files"][dest.name] = {"px": list(px.shape[:2]), "bytes": dest.stat().st_size,
                                      "deflated": len(zlib.compress(dest.read_bytes(), 6))}

    # unit: the donor's, root and torso only (the Hell Bovine's weapon parts are gone: the axe is in the torso mesh). The torso
    # is scaled so that root scale x torso scale = the profile's u.
    unit = json.loads((D2R / (donor_dir + ".json")).read_text(encoding="utf-8"))
    unit["name"] = unit_name
    unit["entities"] = [e for e in unit["entities"] if e["name"] in ("entity_root", "entity_torso")]
    root, torso = unit["entities"]
    for c in torso["components"]:
        if c["type"] == "ModelDefinitionComponent":
            c["filename"] = model
    base = next((c["scale"]["x"] for c in root["components"] if c["type"] == "TransformDefinitionComponent"), 1.0)
    u = profile["u"] / base
    torso["components"].append({"type": "TransformDefinitionComponent", "name": "entity_torso_TransformDefinition",
                                "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                                "scale": {"x": u, "y": u, "z": u}, "inheritOnlyPosition": False})
    dep = unit["dependencies"]
    dep["models"] = [{"path": model}] + [m for m in dep["models"] if "/%s/" % donor not in m["path"]]
    dep["textures"] = [t for t in dep["textures"] if "/%s/" % donor not in t["path"]] + [
        {"path": "%s_%s.texture" % (stem, KINDS[usage])} for usage in used]
    dep["json"] = [j for j in dep["json"] if "/items/" not in j["path"]]
    dest = out / "hd/character/enemy" / (unit_name + ".json")
    dest.write_text(json.dumps(unit, separators=(",", ":")), encoding="utf-8")
    for p in sorted((out / folder).glob("*.model")):
        report["files"][p.name] = {"bytes": p.stat().st_size, "deflated": len(zlib.compress(p.read_bytes(), 6))}
    report["model"], report["donor_model"] = model, "data/" + donor_dir + "/torso.model"
    report["root_scale"], report["torso_scale"] = base, u
    (out.parent / "build.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print("unit", dest, "maps", report.get("maps"))


if __name__ == "__main__":
    main()
