"""Stage 3 finish (round 13): the body's material, matte, in classic's colours; the rigid part (the cap) untouched.

  python s3_bodymat.py labels <stage dir> <out png> [--bone jaw] [--px 2048] [--gutter 6] [--arms b,b,..] [--legs b,b,..]
  python s3_bodymat.py apply <stage dir> [--bone jaw] [--arms b,b,...] [--legs b,b,...]
        [--torso-rgb 34,36,42] [--torso-span 0.35,1.9] [--limb-rgb 92,108,130] [--limb-hi 178,206,226]
        [--limb-span 0.45,1.0] [--limb-top 0.10] [--leg-rgb 40,44,54] [--leg-hi 120,140,170] [--leg-span 0.4,1.4]
        [--leg-top 0.04] [--gamma 1.0] [--blur 0] [--rough 225] [--spec 30] [--glow-body keep|limbs|off]
        [--report <json>]

Why (round 12, Glowing Fungus, owner: "the body looks totally messed up"): the body's ORM had metal 1 on 44 % of its
texels (an earlier "dark metal" pass) and its albedo carried baked white streaks, so the viewer drew it as black chrome
with white glints. Classic's body is matte: near-black and dark grey on the torso, blue-grey to pale blue-white on the
arms, hands, lower legs and feet (classic body pixels, NU, full light: L < 25 half of them at (12,12,12); 25..60 a
third at (40,40,42); 60..110 a sixth at (72,81,95); above 110 4 % at (131..171,181..212,188..224)).

labels: rasterises skinned_lod0.npz's triangles into the albedo's UV layout (u, v as s3_capcolor.py: v down) with one
label per triangle: 1 part (all three vertices fully on --bone), 2 torso, 3 arm, 4 leg (the majority of its vertices'
main bone in --arms, else in --legs: calves, feet, toes; the thighs stay torso, dark as classic's). The part is drawn last, so a texel any part triangle covers stays part. Gutter texels within --gutter
of a triangle take the nearest label (mip bleed); everything else is 0. The corpse strip (u >= 1 - strip) is 0.

apply (in place on <stage>: its overlay's *_alb.texture, *_orm.texture and, with --glow-body, the body glow mask):
1. ORM, body texels (labels 2 and 3, at the ORM's size): B (metal) 0, G (roughness) --rough, A (specular level) --spec.
   R (occlusion) is kept. Part and corpse texels are not touched.
2. albedo: each body texel keeps its own detail order: its luminance rank q among its label's texels (0..1) sets
   its new luminance. Torso: L = Lt x lerp(span) at q ^ gamma, Lt = luminance of --torso-rgb, colour --torso-rgb
   (charcoal slate). Arms: L from --limb-span the same way, colour from --limb-rgb (blue-grey) to --limb-hi (pale
   blue-white) by q; the top --limb-top share by rank is --limb-hi (classic's few bright limb pixels). Legs: the same
   with the --leg-* values (darker: classic's lower legs are dark with pale knees and feet).
   --blur S: the old luminance is first blurred (Gaussian, S texels) inside its label, so thin baked streaks become
   broad soft patches. The old texel's own colour is dropped (it held the baked streaks and the brown/purple tint); its rank keeps the
   painted folds and creases.
3. --glow-body: keep (as is), limbs (the body glow mask only on arm texels), off (zero on the body).
measure <label>=<glob> ...: body pixel statistics (luminance bands, mean colour, saturation) of classic frames or
viewer renders, with the same body test on both (opaque, not cap, below the cap), for the calibration in the viewer.
The part (the cap) stays exact: body texels in a 4x4 block (albedo, ORM) that holds a part texel are left as they
were, and every compressed block whose footprint holds no changed texel is copied from the old file byte for byte (a
re-encode is lossy). At every mip level the texels over the part are the old file's own (decoded) texels before the
level is encoded, so the part's look at a distance stays; only blocks on its outline are re-encoded there.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd

import common

sys.path.insert(0, str(common.WT / "tools"))
import d2r_texture  # noqa: E402

LUM = np.array([0.2126, 0.7152, 0.0722], np.float32)
ARMS = "L_UpperArm,R_UpperArm,L_ForeArm,R_ForeArm,L_Wrist,R_Wrist"
LEGS = "L_Calf,R_Calf,L_Foot,R_Foot,L_Ball,R_Ball"


def opt(a, name, default):
    return a[a.index(name) + 1] if name in a else default


def vec(s):
    return np.array([float(x) for x in s.split(",")], np.float32)


def tex_path(stage: Path, kind: str) -> Path:
    hits = sorted(Path(stage, "overlay").rglob("*_%s.texture" % kind))
    hits = [h for h in hits if "vfx" not in h.parts]
    if len(hits) != 1:
        raise SystemExit("expected one *_%s.texture under %s/overlay, found %d" % (kind, stage, len(hits)))
    return hits[0]


def labels(stage: Path, bone: str, arms, legs, px: int, gutter: int):
    z = np.load(Path(stage) / "skinned_lod0.npz")
    bones = list(z["bones"])
    b = bones.index(bone)
    on = (z["bone_idx"][:, 0] == b) & (z["weights"][:, 0] > 0.99)
    main = z["bone_idx"][np.arange(len(z["weights"])), np.argmax(z["weights"], 1)]
    is_arm = np.isin(main, [bones.index(n) for n in arms if n in bones])
    is_leg = np.isin(main, [bones.index(n) for n in legs if n in bones])
    tris, uv = z["tris"], z["uv"]
    part = on[tris].all(1)
    arm = (is_arm[tris].sum(1) >= 2) & ~part
    leg = (is_leg[tris].sum(1) >= 2) & ~part & ~arm
    im = Image.new("L", (px, px), 0)
    d = ImageDraw.Draw(im)
    for lab, sel in ((2, ~part & ~arm & ~leg), (3, arm), (4, leg), (1, part)):
        for t in tris[sel]:
            d.polygon([(uv[i, 0] * px, uv[i, 1] * px) for i in t], fill=lab)
    L = np.asarray(im).copy()
    dist, (iy, ix) = nd.distance_transform_edt(L == 0, return_indices=True)
    fill = (L == 0) & (dist <= gutter)
    L[fill] = L[iy[fill], ix[fill]]
    strip = float(json.loads((Path(stage) / "build.json").read_text()).get("strip", 0.125))
    L[:, int(round(px * (1 - strip))):] = 0
    return L


def block_any(m, bh, bw):
    """(bh, bw) grid: does any texel of m under each block (m's size a multiple of the grid) hold True."""
    h, w = m.shape
    return m.reshape(bh, h // bh, bw, w // bw).any((1, 3))


def write_spliced(path, fmt, w, h, new_levels, old_levels, changed, bpb):
    """Write a BCn .texture whose blocks are the old file's own bytes wherever the level-0 footprint of the block holds
    no changed texel (every mip): a re-encode of unchanged content is not byte-exact (round 13: 0.4 % of the cap's
    texels moved by up to 189 levels), so the part keeps its exact compressed blocks. Returns copied/new block counts."""
    out, kept, new = [], 0, 0
    for m, (nl, ol) in enumerate(zip(new_levels, old_levels)):
        wm, hm = max(1, w >> m), max(1, h >> m)
        bw, bh = max(1, (wm + 3) // 4), max(1, (hm + 3) // 4)
        if len(nl) != len(ol) or len(nl) < bw * bh * bpb or h % bh or w % bw:
            out.append(nl)
            new += bw * bh
            continue
        ch = block_any(changed, bh, bw).ravel()
        A = np.frombuffer(nl, np.uint8)[:bw * bh * bpb].reshape(-1, bpb).copy()
        B = np.frombuffer(ol, np.uint8)[:bw * bh * bpb].reshape(-1, bpb)
        A[~ch] = B[~ch]
        kept += int((~ch).sum())
        new += int(ch.sum())
        out.append(A.tobytes() + nl[bw * bh * bpb:])
    d2r_texture.write_texture(path, fmt, w, h, out)
    return {"blocks_kept": kept, "blocks_new": new}


def levels_keeping_part(new, old_fmt, old_levels, part, kind="DXT5"):
    """Compressed mip levels of `new` in which, at every level, the texels over the part (the part mask resized to the
    level, nearest) are the old file's own decoded texels: the part's look at a distance (coarse mips) stays as it was,
    only blocks on its outline are re-encoded."""
    chain = d2r_texture.mip_chain(new, len(old_levels))
    h, w = new.shape[:2]
    out = []
    for m, lvl in enumerate(chain):
        lvl = np.ascontiguousarray(lvl).copy()
        wm, hm = lvl.shape[1], lvl.shape[0]
        if wm >= 4 and hm >= 4:
            old = d2r_texture.decode(old_fmt, wm, hm, old_levels[m])
            pm = np.asarray(Image.fromarray(part.astype(np.uint8)).resize((wm, hm), Image.NEAREST)) > 0
            lvl[pm] = old[pm][:, :lvl.shape[-1]] if lvl.ndim == 3 else old[pm][:, 0]
        if kind == "BC4":
            out.append(d2r_texture.bc4_encode(lvl).ljust(8, b"\0"))
        else:
            out.append(d2r_texture._dds_levels(lvl, 1, "DXT5", "RGBA")[0])
    return out


def ranks(x):
    o = np.argsort(x, kind="stable")
    r = np.empty(len(x), np.float32)
    r[o] = (np.arange(len(x)) + 0.5) / len(x)
    return r


def cmd_labels(a):
    stage, out = Path(a[0]), Path(a[1])
    L = labels(stage, opt(a, "--bone", "jaw"), opt(a, "--arms", ARMS).split(","), opt(a, "--legs", LEGS).split(","),
               int(opt(a, "--px", "2048")), int(opt(a, "--gutter", "6")))
    pal = np.array([[0, 0, 0], [60, 110, 255], [90, 90, 96], [200, 220, 235], [120, 140, 170]], np.uint8)
    Image.fromarray(pal[L]).save(out)
    print({k: int((L == i).sum()) for i, k in enumerate(["none", "part", "torso", "arm", "leg"])})


def cmd_apply(a):
    stage = Path(a[0])
    bone, arms, legs = opt(a, "--bone", "jaw"), opt(a, "--arms", ARMS).split(","), opt(a, "--legs", LEGS).split(",")
    gutter = int(opt(a, "--gutter", "6"))
    t_rgb, t_span = vec(opt(a, "--torso-rgb", "34,36,42")), vec(opt(a, "--torso-span", "0.35,1.9"))
    l_rgb, l_hi = vec(opt(a, "--limb-rgb", "92,108,130")), vec(opt(a, "--limb-hi", "178,206,226"))
    l_span, l_top = vec(opt(a, "--limb-span", "0.45,1.0")), float(opt(a, "--limb-top", "0.10"))
    g_rgb, g_hi = vec(opt(a, "--leg-rgb", "40,44,54")), vec(opt(a, "--leg-hi", "120,140,170"))
    g_span, g_top = vec(opt(a, "--leg-span", "0.4,1.4")), float(opt(a, "--leg-top", "0.04"))
    gamma = float(opt(a, "--gamma", "1.0"))
    rough, spec = float(opt(a, "--rough", "225")), float(opt(a, "--spec", "30"))
    glow = opt(a, "--glow-body", "keep")
    rep = {k: opt(a, "--" + k, None) for k in ("torso-rgb", "torso-span", "limb-rgb", "limb-hi", "limb-span", "limb-top",
                                              "leg-rgb", "leg-hi", "leg-span", "leg-top", "gamma", "rough", "spec",
                                              "glow-body")}

    # albedo
    src = tex_path(stage, "alb")
    fmt, w, h, mips = d2r_texture.read_texture(src)
    alb = d2r_texture.decode(fmt, w, h, mips[0])
    L = labels(stage, bone, arms, legs, w, gutter)
    rgb = alb[..., :3].astype(np.float32)
    lum = rgb @ LUM
    res = rgb.copy()
    blur = float(opt(a, "--blur", "0"))
    rep["blur"] = blur
    for lab, nm, base, hi, span, top in ((2, "torso", t_rgb, None, t_span, 0), (3, "arm", l_rgb, l_hi, l_span, l_top),
                                         (4, "leg", g_rgb, g_hi, g_span, g_top)):
        m = L == lab
        if not m.any():
            continue
        src_l = lum
        if blur > 0:
            # the old luminance blurred inside its label only (normalised convolution): broad soft patches keep the
            # painted folds, the thin baked streaks melt into their surroundings
            src_l = nd.gaussian_filter(np.where(m, lum, 0), blur) / np.maximum(nd.gaussian_filter(m.astype(np.float32), blur), 1e-6)
        q = ranks(src_l[m]) ** gamma
        k = span[0] + (span[1] - span[0]) * q
        if hi is None:
            col = base[None] * k[:, None]
        else:
            # dark end -> bright end along the rank, scaled by the span; the top share by rank at the bright end
            mix = q[:, None]
            col = (base[None] * (1 - mix) + hi[None] * mix) * k[:, None]
            col[q >= 1 - top] = hi
        res[m] = col
        rep["%s_texels" % nm] = int(m.sum())
        rep["%s_before" % nm] = rgb[m].mean(0).round(1).tolist()
        rep["%s_after" % nm] = res[m].mean(0).round(1).tolist()
    alb2 = alb.copy()
    alb2[..., :3] = np.clip(np.round(res), 0, 255).astype(np.uint8)
    part = L == 1
    # body texels in a 4x4 block that holds any part texel stay as they were: the part's level-0 blocks stay exact
    near = np.kron(block_any(part, h // 4, w // 4), np.ones((4, 4), bool))
    alb2[near] = alb[near]
    rep["body_texels_kept_next_to_part"] = int((near & np.isin(L, (2, 3, 4))).sum())
    assert (alb2[part] == alb[part]).all()
    changed = (alb2 != alb).any(-1)
    new_levels = levels_keeping_part(alb2, fmt, mips, part)
    rep["alb_blocks"] = write_spliced(src, fmt, w, h, new_levels, mips, changed, 16)
    Image.fromarray(alb2[..., :3]).save(stage / "albedo_bodymat.png")

    # ORM (its own size)
    osrc = tex_path(stage, "orm")
    fo, wo, ho, lo = d2r_texture.read_texture(osrc)
    O = d2r_texture.decode(fo, wo, ho, lo[0])
    Lo = np.asarray(Image.fromarray(L).resize((wo, ho), Image.NEAREST))
    # a texel of the smaller map is body only if every albedo texel under it is body (the cap's ORM stays exact)
    any_part = block_any(L == 1, ho, wo)                       # ORM texel over any part texel
    near_o = np.kron(block_any(any_part, ho // 4, wo // 4), np.ones((4, 4), bool))   # ORM block holding one
    body = np.isin(Lo, (2, 3, 4)) & ~near_o
    rep["orm_body_before"] = O[body].mean(0).round(1).tolist()
    rep["orm_metal_share_before"] = round(float((O[body][:, 2] > 128).mean()), 3)
    O2 = O.copy()
    O2[body, 1] = rough
    O2[body, 2] = 0
    O2[body, 3] = spec
    rep["orm_body_after"] = O2[body].mean(0).round(1).tolist()
    rep["orm_texels"] = int(body.sum())
    rep["part_unchanged"] = bool((O2[~body] == O[~body]).all() and (alb2[part] == alb[part]).all())
    ch_o = (O2 != O).any(-1)
    part_o = np.asarray(Image.fromarray((L == 1).astype(np.uint8)).resize((wo, ho), Image.NEAREST)) > 0
    rep["orm_blocks"] = write_spliced(osrc, fo, wo, ho, levels_keeping_part(O2, fo, lo, part_o), lo, ch_o, 16)

    # body glow mask
    if glow != "keep":
        msk = next(Path(stage, "overlay").rglob("*_glow_body_mask.texture"))
        fm, wm, hm, lm = d2r_texture.read_texture(msk)
        M = d2r_texture.decode(fm, wm, hm, lm[0])
        M = (M[..., 0] if M.ndim == 3 else M).copy()
        Lm = np.asarray(Image.fromarray(L).resize((wm, hm), Image.NEAREST))
        rep["glow_body_before"] = round(float(M.mean()), 3)
        kill = np.isin(Lm, (2, 3, 4)) if glow == "off" else np.isin(Lm, (2, 4))
        M0 = M.copy()
        M[kill] = 0
        rep["glow_body_after"] = round(float(M.mean()), 3)
        lv = [d2r_texture.bc4_encode(x).ljust(8, b"\0") for x in d2r_texture.mip_chain(M, len(lm))]
        rep["glow_blocks"] = write_spliced(msk, fm, wm, hm, lv, lm, M != M0, 8)
    (stage / "bodymat.json").write_text(json.dumps(rep, indent=1))
    if "--report" in a:
        Path(opt(a, "--report", "")).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))


def body_pixels(paths):
    """Body pixels of sprite or viewer images: opaque, not the cap rim (s5_corpsefit.rim_mask), not the blue part
    colour, below the cap's lowest row (the test s3_levels.classic_body uses on classic's frames)."""
    from s5_corpsefit import rim_mask
    out = []
    for p in paths:
        im = np.asarray(Image.open(p).convert("RGBA"))
        cap = rim_mask(im)
        body = (im[..., 3] > 128) & ~cap
        blue = im[..., 2].astype(int) - np.maximum(im[..., 0], im[..., 1]).astype(int)
        body &= ~((im[..., 2] >= 120) & (blue > 50))
        ys = np.nonzero(cap)[0]
        if len(ys):
            body[:ys.max() + 1] = False
        out.append(im[body][:, :3].astype(np.float32))
    return np.vstack(out)


BANDS = ((0, 25), (25, 60), (60, 110), (110, 256))


def stats(pix):
    L = pix @ LUM
    r = {"n": int(len(pix)), "mean_rgb": pix.mean(0).round(1).tolist(),
         "L_pct_10_25_50_75_90_97": [round(float(np.percentile(L, q)), 1) for q in (10, 25, 50, 75, 90, 97)]}
    mx, mn = pix.max(1), pix.min(1)
    r["sat_mean"] = round(float(((mx - mn) / np.maximum(mx, 1)).mean()), 3)
    for lo, hi in BANDS:
        m = (L >= lo) & (L < hi)
        r["L%d_%d" % (lo, hi)] = {"share": round(float(m.mean()), 3),
                                  "rgb": pix[m].mean(0).round(1).tolist() if m.any() else None}
    return r


def cmd_measure(a):
    """measure <label>=<glob> [...] [--json out]: body pixel stats per image set (classic frames or viewer renders)."""
    import glob
    res = {}
    for x in a:
        if "=" not in x or x.startswith("--"):
            continue
        k, g = x.split("=", 1)
        res[k] = stats(body_pixels(sorted(glob.glob(g))))
    print(json.dumps(res, indent=1))
    if "--json" in a:
        Path(opt(a, "--json", "")).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"labels": cmd_labels, "apply": cmd_apply, "measure": cmd_measure}[sys.argv[1]](sys.argv[2:])
