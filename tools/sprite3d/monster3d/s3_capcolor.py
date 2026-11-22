"""Stage 3 finish (round 12): recolour the pale texels of a self-coloured rigid part (the Glowing Fungus cap) toward the
part's own saturated hue, keeping only the brightest specks as near-white highlights.

  python s3_capcolor.py masks <stage dir> <out dir> [--bone jaw] [--px 2048]
  python s3_capcolor.py apply <stage dir> <out stage dir> [--bone jaw] [--hue 35,80,240] [--hi 150,205,255]
                              [--sat-max 0.45] [--l-min 70] [--white-top 0.04] [--top-only-white] [--sheet <png>]

Why: in round 11 the cap's outer rim and its side band (the lower lip) held pale grey-green texels with white dots (from the
unified texture of 8 stitched views). Classic draws that band as a saturated electric blue with only a few white pixels.
Under the game's glow the pale texels read light blue; in the viewer and on the corpse (no glow) they read grey-white specks.

masks: rasterises the part's triangles (vertices weighted fully to --bone in skinned_lod0.npz) into the albedo's UV
layout, split by bind normal: top (ny > 0.5), side (|ny| <= 0.5), under (ny < -0.5). Writes cap_top/side/under.png.

apply: reads the stage's overlay albedo (<stage>/overlay/.../<name>_alb.texture), and inside the part mask moves every
texel with luminance >= --l-min and saturation <= --sat-max toward the part colour: its new colour is a blend of --hue
(dark end) and --hi (bright end) by its luminance, so shading and speck pattern stay, only the hue and chroma change. The
brightest --white-top share of the pale texels (by luminance) keeps a lighter tint (half way between --hi and white):
the few white highlights classic has. Texels already saturated (the blue ring, the green inner ring, the dark core) are
not touched. The out stage is a copy of the stage with only <name>_alb.texture rewritten (BC3 sRGB, full mip chain, as
s5_build.py writes it); a report json lists the texel counts and the mean colour before and after.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import common

sys.path.insert(0, str(common.WT / "tools"))
import d2r_texture  # noqa: E402


def opt(a, name, default):
    return a[a.index(name) + 1] if name in a else default


def alb_path(stage: Path) -> Path:
    hits = sorted(Path(stage, "overlay").rglob("*_alb.texture"))
    if len(hits) != 1:
        raise SystemExit("expected one *_alb.texture under %s/overlay, found %d" % (stage, len(hits)))
    return hits[0]


def part_masks(stage: Path, bone: str, px: int):
    z = np.load(Path(stage) / "skinned_lod0.npz")
    bones = list(z["bones"])
    b = bones.index(bone)
    on = (z["bone_idx"][:, 0] == b) & (z["weights"][:, 0] > 0.99)
    tris = z["tris"][on[z["tris"]].all(1)]
    uv, nrm = z["uv"], z["nrm"]
    ny = nrm[tris].mean(1)[:, 1]
    out = {}
    for name, sel in (("top", ny > 0.5), ("side", np.abs(ny) <= 0.5), ("under", ny < -0.5)):
        im = Image.new("L", (px, px), 0)
        d = ImageDraw.Draw(im)
        for t in tris[sel]:
            d.polygon([(uv[i, 0] * px, uv[i, 1] * px) for i in t], fill=255)
        out[name] = np.asarray(im) > 0
    return out


def masks(a):
    stage, out = Path(a[0]), Path(a[1])
    out.mkdir(parents=True, exist_ok=True)
    m = part_masks(stage, opt(a, "--bone", "jaw"), int(opt(a, "--px", "2048")))
    for k, v in m.items():
        Image.fromarray((v * 255).astype(np.uint8)).save(out / ("cap_%s.png" % k))
        print(k, int(v.sum()), "texels")


def rgb3(s):
    return np.array([float(x) for x in s.split(",")], np.float32)


def apply(a):
    stage, out = Path(a[0]), Path(a[1])
    hue, hi = rgb3(opt(a, "--hue", "35,80,240")), rgb3(opt(a, "--hi", "150,205,255"))
    sat_max, l_min, white_top = float(opt(a, "--sat-max", "0.45")), float(opt(a, "--l-min", "70")), float(opt(a, "--white-top", "0.04"))
    src = alb_path(stage)
    fmt, w, h, mips = d2r_texture.read_texture(src)
    alb = d2r_texture.decode(fmt, w, h, mips[0])
    m = part_masks(stage, opt(a, "--bone", "jaw"), w)
    part = m["top"] | m["side"] | m["under"]
    rgb = alb[..., :3].astype(np.float32)
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    pale = part & (lum >= l_min) & (sat <= sat_max)
    # blend --hue -> --hi by the texel's luminance between l_min and its 99th percentile among the pale texels
    l_hi = np.percentile(lum[pale], 99) if pale.any() else 255.0
    t = np.clip((lum - l_min) / max(1.0, l_hi - l_min), 0, 1)[..., None]
    new = hue * (1 - t) + hi * t
    if pale.any() and white_top > 0:
        # by rank, not by a luminance cut: many pale texels share the same top luminance after BC3
        idx = np.flatnonzero(pale)
        order = np.argsort(lum.ravel()[idx], kind="stable")
        white = np.zeros(pale.size, bool)
        white[idx[order[len(idx) - int(round(white_top * len(idx))):]]] = True
        white = white.reshape(pale.shape)
        new[white] = (hi + 255.0) / 2
    else:
        white = np.zeros_like(pale)
    res = rgb.copy()
    res[pale] = new[pale]
    before, after = rgb[part].mean(0), res[part].mean(0)
    alb2 = alb.copy()
    alb2[..., :3] = np.clip(np.round(res), 0, 255).astype(np.uint8)
    if out.resolve() != stage.resolve():
        if out.exists():
            raise SystemExit("%s exists" % out)
        shutil.copytree(stage, out)
    dest = out / src.relative_to(stage)
    d2r_texture.write_bc3(dest, alb2, int(np.log2(w)) + 1, linear=False)
    Image.fromarray(alb2[..., :3]).save(out / "albedo_capcolor.png")
    rep = {"source": str(src), "hue": hue.tolist(), "hi": hi.tolist(), "sat_max": sat_max, "l_min": l_min,
           "white_top": white_top, "part_texels": int(part.sum()), "pale_texels": int(pale.sum()),
           "white_texels": int(white.sum()), "part_mean_before": before.round(1).tolist(),
           "part_mean_after": after.round(1).tolist()}
    (out / "capcolor.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))
    if "--sheet" in a:
        ys, xs = np.nonzero(part)
        box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
        l = Image.fromarray(alb[..., :3]).crop(box)
        r = Image.fromarray(alb2[..., :3]).crop(box)
        s = Image.new("RGB", (l.width * 2 + 8, l.height), (16, 17, 20))
        s.paste(l, (0, 0))
        s.paste(r, (l.width + 8, 0))
        s.save(opt(a, "--sheet", ""))


def core(a):
    """Speckle the dark core of the part's top face, as classic's cap: dark navy specks, densest next to the ring, few at
    the centre. In place on <stage> (its *_alb.texture), report core.json."""
    from scipy import ndimage as nd
    stage = Path(a[0])
    col = rgb3(opt(a, "--rgb", "25,35,110"))
    dens_rim, dens_mid = float(opt(a, "--dens-rim", "0.45")), float(opt(a, "--dens-mid", "0.06"))
    depth, cell = float(opt(a, "--depth", "220")), int(opt(a, "--cell", "12"))
    l_dark = float(opt(a, "--l-dark", "30"))
    src = alb_path(stage)
    fmt, w, h, mips = d2r_texture.read_texture(src)
    alb = d2r_texture.decode(fmt, w, h, mips[0])
    top = part_masks(stage, opt(a, "--bone", "jaw"), w)["top"]
    rgb = alb[..., :3].astype(np.float32)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    dark = top & (lum < l_dark)
    # distance (texels) from the nearest lit texel of the top face: 0 at the ring's inner edge, larger toward the centre
    dist = nd.distance_transform_edt(dark)
    dens = dens_mid + (dens_rim - dens_mid) * np.clip(1 - dist / depth, 0, 1)
    rng = np.random.default_rng(int(opt(a, "--seed", "12")))
    n = rng.random((-(-h // cell), -(-w // cell)))
    n = np.kron(n, np.ones((cell, cell)))[:h, :w]
    n = nd.gaussian_filter(n, cell * 0.15)        # round the blocks a little
    shade = 0.6 + 0.4 * rng.random((-(-h // cell), -(-w // cell)))
    shade = np.kron(shade, np.ones((cell, cell)))[:h, :w]
    speck = dark & (n < dens)
    res = rgb.copy()
    res[speck] = col * shade[speck][:, None]
    alb2 = alb.copy()
    alb2[..., :3] = np.clip(np.round(res), 0, 255).astype(np.uint8)
    d2r_texture.write_bc3(src, alb2, int(np.log2(w)) + 1, linear=False)
    Image.fromarray(alb2[..., :3]).save(stage / "albedo_core.png")
    rep = {"rgb": col.tolist(), "dens_rim": dens_rim, "dens_mid": dens_mid, "depth": depth, "cell": cell,
           "dark_texels": int(dark.sum()), "speck_texels": int(speck.sum()),
           "core_mean_before": float(lum[dark].mean()), "core_mean_after": float((res[dark] @ np.array([0.2126, 0.7152, 0.0722])).mean())}
    (stage / "core.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))


def corpse_hue(a):
    """Turn the corpse miniature's cyan texels (the corpse shell's albedo in the strip, s5_build.py --strip: the top-right
    strip x strip block of the albedo) to classic's pale periwinkle body colour. Hue in [--from-lo, --from-hi] degrees
    moves to --to degrees, saturation x --sat; value kept. In place on <stage>, report corpse_hue.json."""
    from PIL import Image as _I
    stage = Path(a[0])
    lo, hi, to, satk = (float(opt(a, k, d)) for k, d in (("--from-lo", "165"), ("--from-hi", "205"), ("--to", "226"),
                                                          ("--sat", "0.6")))
    strip = float(json.loads((stage / "build.json").read_text()).get("strip", 0.125))
    src = alb_path(stage)
    fmt, w, h, mips = d2r_texture.read_texture(src)
    alb = d2r_texture.decode(fmt, w, h, mips[0])
    mw, mh = w - int(round(w * (1 - strip))), int(round(h * strip))
    blk = alb[:mh, w - mw:, :3]
    hsv = np.asarray(_I.fromarray(blk).convert("HSV")).astype(np.float32)
    deg = hsv[..., 0] * 360 / 255
    sel = (deg >= lo) & (deg <= hi) & (hsv[..., 1] > 25)
    hsv[..., 0][sel] = to * 255 / 360
    hsv[..., 1][sel] *= satk
    new = np.asarray(_I.fromarray(np.clip(hsv, 0, 255).astype(np.uint8), "HSV").convert("RGB"))
    alb2 = alb.copy()
    alb2[:mh, w - mw:, :3] = np.where(sel[..., None], new, blk)
    d2r_texture.write_bc3(src, alb2, int(np.log2(w)) + 1, linear=False)
    rep = {"block_px": [mw, mh], "from_deg": [lo, hi], "to_deg": to, "sat": satk, "texels": int(sel.sum()),
           "mean_before": blk[sel].mean(0).round(1).tolist() if sel.any() else None,
           "mean_after": new[sel].mean(0).round(1).tolist() if sel.any() else None}
    (stage / "corpse_hue.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep))


if __name__ == "__main__":
    if sys.argv[1] == "corpse-hue":
        corpse_hue(sys.argv[2:])
        sys.exit(0)
    cmd, rest = sys.argv[1], sys.argv[2:]
    {"masks": masks, "apply": apply, "core": core}[cmd](rest)
