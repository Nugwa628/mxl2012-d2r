"""Review sheets and candidate pictures for the upscaled HD item pictures (lane itemart; tools/item_art_review.py).

A candidate for a picture is, in this order (docs/hd-icons.md "Picture review"):
  reuse    a D2R HD sprite of the same kind of object: a looser silhouette match than item_reuse's (loose_candidates:
           mask IoU of the two tight crops stretched to one box, times an aspect penalty), scaled to the size of Median's
           picture and recoloured to its mean hue / saturation / brightness (colour_match); judged by eye on the sheet
  method   another upscale setting (upscale.METHODS, or the hybrid with other edge / sharpen values: VARIANTS)
  keep     the current hybrid upscale
Sheet row: Median classic (legacy look: nearest x3.5) | current HD upscale | candidate, all at D2R's HD size (98 px per
cell) on an inventory-like cell grid, the item name and code under the row; written at real pixel size and at 2x
(nearest). At most PER_SHEET rows per sheet (read on a phone). The sheets are game art: keep them out of git.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import upscale  # noqa: E402
from colour_shift import shift_pixels  # noqa: E402
from dc6 import decode_frame, palette, read_dc6, read_sprite  # noqa: E402
from item_art import CELL_CLASSIC, CELL_HD, D2R_ITEMS, MOD_ITEMS, asset_size  # noqa: E402

PER_SHEET = 8
BG, CELL_BG, CELL_LINE, TEXT = (14, 12, 10), (30, 26, 22), (58, 50, 40), (220, 205, 170)
PAD, MIN_COL = 10, 200
MASK = 24
VARIANTS = {  # name -> (base method, upscale module settings)
    "hybrid-crisp": ("hybrid", {"EDGE_LO": 20.0, "EDGE_HI": 60.0, "SHARPEN": 0.8}),
    "hybrid-sharp": ("hybrid", {"SHARPEN": 1.0}),
    "hybrid-smooth": ("hybrid", {"EDGE_LO": 150.0, "EDGE_HI": 250.0, "SHARPEN": 0.3}),  # Scale2x on the outline only
}


# -- pictures -----------------------------------------------------------------------------------------------------
def classic_rgba(key: str, pal: list) -> np.ndarray:
    group, inv = key.split("/", 1)
    w, h, _ox, _oy, block = read_dc6((MOD_ITEMS if group == "mxl" else D2R_ITEMS) / f"{inv}.dc6")[0]
    return upscale.rows_to_array(decode_frame(w, h, block, pal, fill=True))


def nearest(a: np.ndarray, factor: float) -> np.ndarray:
    h, w = a.shape[:2]
    return np.asarray(Image.fromarray(np.ascontiguousarray(a), "RGBA").resize(
        (max(1, round(w * factor)), max(1, round(h * factor))), Image.Resampling.NEAREST))


def upscaled(a: np.ndarray, method: str = upscale.METHOD) -> np.ndarray:
    """`a` at HD size with an upscale method or a VARIANTS name (module settings restored afterwards)."""
    f = CELL_HD / CELL_CLASSIC
    if method not in VARIANTS:
        return upscale.upscale(a, f, method)
    base, settings = VARIANTS[method]
    old = {k: getattr(upscale, k) for k in settings}
    try:
        for k, v in settings.items():
            setattr(upscale, k, v)
        return upscale.upscale(a, f, base)
    finally:
        for k, v in old.items():
            setattr(upscale, k, v)


def crop(a: np.ndarray) -> np.ndarray:
    nz = a[..., 3] > 0
    if not nz.any():
        return a[:0, :0]
    r, c = np.nonzero(nz.any(1))[0], np.nonzero(nz.any(0))[0]
    return a[r[0]:r[-1] + 1, c[0]:c[-1] + 1]


# -- loose silhouette match -----------------------------------------------------------------------------------------
def mask(a: np.ndarray, n: int = MASK) -> np.ndarray:
    """Opaque mask of the tight crop of RGBA `a`, stretched (nearest) to n x n."""
    c = crop(a)
    if c.size == 0:
        return np.zeros((n, n), bool)
    m = c[..., 3] > 0
    ys = (np.arange(n) * m.shape[0] / n).astype(int)
    xs = (np.arange(n) * m.shape[1] / n).astype(int)
    return m[ys][:, xs]


def silhouette_score(a: np.ndarray, b: np.ndarray) -> float:
    """IoU of the stretched masks times exp(-2 |log aspect ratio|): 1 for the same outline, ~0.5 for a loose one."""
    ca, cb = crop(a), crop(b)
    if ca.size == 0 or cb.size == 0:
        return 0.0
    ma, mb = mask(a), mask(b)
    iou = (ma & mb).sum() / max((ma | mb).sum(), 1)
    asp = abs(math.log((ca.shape[1] / ca.shape[0]) / (cb.shape[1] / cb.shape[0])))
    return float(iou * math.exp(-2 * asp))


def loose_candidates(src: np.ndarray, library: dict[str, np.ndarray], n: int = 4, floor: float = 0.55) -> list[tuple[str, float]]:
    """The n library keys whose picture's silhouette is closest to `src` (score >= floor), best first."""
    scored = [(k, silhouette_score(src, v)) for k, v in library.items()]
    return sorted([s for s in scored if s[1] >= floor], key=lambda s: (-s[1], s[0]))[:n]


# -- colour match -----------------------------------------------------------------------------------------------------
def hsv_stats(a: np.ndarray) -> tuple[float, float, float]:
    """(mean hue in turns weighted by saturation x value, mean saturation, mean value) of the opaque pixels."""
    op = a[..., 3] > 0
    rgb = a[..., :3][op].astype(np.float64) / 255
    if not len(rgb):
        return 0.0, 0.0, 0.0
    mx, mn = rgb.max(1), rgb.min(1)
    d = mx - mn
    dd = np.maximum(d, 1e-9)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0.0)
    w = s * mx
    hue = math.atan2((w * np.sin(2 * np.pi * h)).sum(), (w * np.cos(2 * np.pi * h)).sum()) / (2 * np.pi) % 1.0
    return float(hue), float(s.mean()), float(mx.mean())


def colour_match(src: np.ndarray, cand: np.ndarray) -> dict:
    """{"hue", "sat" (factor), "val" (log2)} that brings `cand`'s mean colour to `src`'s (as item_reuse's shift)."""
    hs, ss, vs = hsv_stats(src)
    hc, sc, vc = hsv_stats(cand)
    dh = (hs - hc + 0.5) % 1.0 - 0.5
    return {"hue": round(dh, 3), "sat": round(min(max(ss / max(sc, 1e-6), 0.0), 4.0), 3),
            "val": round(math.log2(max(vs, 1e-6) / max(vc, 1e-6)), 3)}


def _hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rgb = rgb.astype(np.float64) / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    dd = np.maximum(d, 1e-9)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    return np.where(d == 0, 0.0, h) % 1.0, np.where(mx > 0, d / np.maximum(mx, 1e-9), 0.0), mx


def _rgb(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    out = np.zeros(h.shape + (3,))
    for k, (ra, ga, ba) in enumerate([(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]):
        m = i == k
        out[..., 0][m], out[..., 1][m], out[..., 2][m] = ra[m], ga[m], ba[m]
    return np.clip(np.rint(out * 255), 0, 255).astype(np.uint8)


def colour_by_position(hd: np.ndarray, src: np.ndarray) -> np.ndarray:
    """`hd` (a cropped D2R HD picture) with the hue and saturation of Median's picture `src` at the same relative
    position (src's colours smoothed and stretched over hd's box; transparent src pixels take the nearest opaque
    colour), hd's own brightness scaled to src's mean: D2R's form and shading, Median's colours (a gem of many colours)."""
    c = crop(src)
    big = upscale.resize(c, hd.shape[1], hd.shape[0], Image.Resampling.BILINEAR)
    blur = np.asarray(Image.fromarray(np.ascontiguousarray(big), "RGBa").filter(
        ImageFilter.GaussianBlur(max(hd.shape[:2]) / 40))).astype(np.float64)
    al = np.maximum(blur[..., 3:4], 1e-6)
    col = np.clip(blur[..., :3] / al * 255, 0, 255)
    hs, ss, _v = _hsv(col)
    hh, sh, vh = _hsv(hd[..., :3])
    _h0, s0, v0 = hsv_stats(src)
    _h1, s1, v1 = hsv_stats(hd)
    sat = np.clip(np.maximum(ss, sh) * (1.0 if s0 > s1 else s0 / max(s1, 1e-6)), 0, 1)
    val = np.clip(vh * (v0 / max(v1, 1e-6)), 0, 1)
    out = hd.copy()
    out[..., :3] = _rgb(hs, sat, val)
    return out


def render_reuse(hd: np.ndarray, src: np.ndarray, out_w: int, out_h: int, shift: dict | None,
                 by_position: bool = False) -> np.ndarray:
    """D2R HD sprite `hd` cropped, scaled so its area matches Median's picture `src` at HD size, recoloured, centred."""
    c, s = crop(hd), crop(src)
    f = CELL_HD / CELL_CLASSIC
    k = math.sqrt((s.shape[0] * f * s.shape[1] * f) / max(c.shape[0] * c.shape[1], 1))
    k = min(k, out_w / c.shape[1], out_h / c.shape[0])
    a = upscale.resize(c, max(1, round(c.shape[1] * k)), max(1, round(c.shape[0] * k)))
    if by_position:
        a = colour_by_position(a, src)
    elif shift:
        a = shift_pixels(a, shift["hue"], 0.0, shift["val"], shift["sat"])
    return upscale.place(a, out_w, out_h)


def hd_sprite(hd_items: Path, folder_asset: str) -> np.ndarray:
    return upscale.rows_to_array(read_sprite(Path(hd_items) / f"{folder_asset}.sprite")[0])


# -- candidates of one picture -------------------------------------------------------------------------------------
def candidate(prop: dict | None, src: np.ndarray, out_w: int, out_h: int, hd_items: Path) -> tuple[np.ndarray, str]:
    """(image, label) of a proposal entry; the current upscale for none / keep."""
    if prop and prop.get("reuse"):
        r = prop["reuse"]
        shift = {k: r[k] for k in ("hue", "sat", "val")} if "hue" in r else None
        img = render_reuse(hd_sprite(hd_items, f"{r['folder']}/{r['asset']}"), src, out_w, out_h, shift,
                           r.get("colour") == "by position")
        return img, f"D2R {r['asset'].split('/')[-1]}" + (", Median's colours" if r.get("colour") == "by position" else "")
    if prop and prop.get("method"):
        return upscale.place(upscaled(src, prop["method"]), out_w, out_h), prop["method"]
    return upscale.place(upscaled(src), out_w, out_h), "keep (no better)"


# -- sheet drawing --------------------------------------------------------------------------------------------------
def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def grid(cw: int, ch: int) -> Image.Image:
    """An inventory-like cw x ch cell field at HD size (98 px cells)."""
    im = Image.new("RGBA", (cw * CELL_HD, ch * CELL_HD), (*CELL_BG, 255))
    d = ImageDraw.Draw(im)
    for i in range(cw + 1):
        d.line([(i * CELL_HD - (i == cw), 0), (i * CELL_HD - (i == cw), ch * CELL_HD)], (*CELL_LINE, 255))
    for j in range(ch + 1):
        d.line([(0, j * CELL_HD - (j == ch)), (cw * CELL_HD, j * CELL_HD - (j == ch))], (*CELL_LINE, 255))
    return im


def on_grid(img: np.ndarray, cw: int, ch: int) -> Image.Image:
    g = grid(cw, ch)
    g.alpha_composite(Image.fromarray(np.ascontiguousarray(img), "RGBA"))
    return g


def wrap(text: str, font, width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """`text` broken into lines no wider than `width` pixels (at spaces)."""
    lines, cur = [], ""
    for word in text.split(" "):
        t = f"{cur} {word}".strip()
        if cur and draw.textlength(t, font=font) > width:
            lines.append(cur)
            cur = word
        else:
            cur = t
    return lines + ([cur] if cur else [])


def draw_sheet(rows: list[dict], title: str) -> Image.Image:
    """rows: {"cells": (cw, ch), "images": [3 RGBA arrays at cw*98 x ch*98], "caption": str, "labels": [3 str]}.
    Columns at least MIN_COL wide (labels wrapped above each picture), the caption wrapped under the row."""
    col_w = max(MIN_COL, max(r["cells"][0] for r in rows) * CELL_HD)
    width = PAD + 3 * (col_w + PAD)
    f, fs = _font(15), _font(13)
    d0 = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lay = []
    for r in rows:
        labels = [wrap(t, fs, col_w, d0) for t in r["labels"]]
        cap = wrap(r["caption"], f, width - 2 * PAD, d0)
        lab_h = 16 * max(len(x) for x in labels) + 4
        lay.append((labels, cap, lab_h, lab_h + r["cells"][1] * CELL_HD + 6 + 19 * len(cap) + PAD))
    head = wrap(title, f, width - 2 * PAD, d0)
    top = 8 + 19 * len(head) + 4
    im = Image.new("RGBA", (width, top + sum(x[3] for x in lay) + PAD), (*BG, 255))
    d = ImageDraw.Draw(im)
    for i, line in enumerate(head):
        d.text((PAD, 8 + 19 * i), line, (*TEXT, 255), font=f)
    y = top
    for r, (labels, cap, lab_h, rh) in zip(rows, lay):
        cw, ch = r["cells"]
        for i, img in enumerate(r["images"]):
            x = PAD + i * (col_w + PAD)
            for j, line in enumerate(labels[i]):
                d.text((x, y + 16 * j), line, (160, 150, 128, 255), font=fs)
            im.alpha_composite(on_grid(img, cw, ch), (x + (col_w - cw * CELL_HD) // 2, y + lab_h))
        for j, line in enumerate(cap):
            d.text((PAD, y + lab_h + ch * CELL_HD + 6 + 19 * j), line, (*TEXT, 255), font=f)
        y += rh
    return im


def save_pair(im: Image.Image, path: Path) -> list[Path]:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    z = path.with_name(path.stem + "_2x.png")
    im.resize((im.width * 2, im.height * 2), Image.Resampling.NEAREST).save(z)
    return [path, z]


def caption(p) -> str:
    named = []
    for u in p.users:
        s = f"{u['name']} ({u['code']})"
        if s not in named:
            named.append(s)
    more = f" + {len(named) - 2} more" if len(named) > 2 else ""
    return f"{p.key}: " + ", ".join(named[:2]) + more


def write_all(out: Path, plan, order: list, proposals: dict) -> int:
    """Review sheets of `order` ((rank, picture, has a proposal), item_art_review.review_order), PER_SHEET rows each:
    first the pictures with a proposal, then the ones kept as they are (their own sheets)."""
    pal = palette(Path(__file__).resolve().parent.parent / "work" / "d2r-baseline" / "palette" / "pal.dat")
    props = proposals.get("pictures", {})
    groups: dict[bool, list] = {True: [], False: []}
    for n, p, has in order:
        src = classic_rgba(p.key, pal)
        cw, ch = asset_size(src.shape[1], src.shape[0], *plan.needs[(p.folder, *p.key.split("/", 1))])
        W, H = cw * CELL_HD, ch * CELL_HD
        legacy = upscale.place(nearest(src, CELL_HD / CELL_CLASSIC), W, H)
        current = upscale.place(upscaled(src), W, H)
        cand, label = candidate(props.get(p.key), src, W, H, plan.hd_items)
        groups[has].append({"cells": (cw, ch), "images": [legacy, current, cand], "caption": f"#{n} {caption(p)}",
                            "labels": ["Median classic (legacy)", "current HD upscale", f"candidate: {label}"]})
    written, k = [], 0
    for has, what in ((True, "candidates"), (False, "no better picture found (kept)")):
        rows = groups[has]
        for i in range(0, len(rows), PER_SHEET):
            k += 1
            title = f"D2R-XL item pictures {k}: {what}, real pixel size (98 px per cell)"
            written += save_pair(draw_sheet(rows[i:i + PER_SHEET], title), Path(out) / f"sheet_{k:02}.png")
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "sheets.json").write_text(json.dumps([str(w) for w in written], indent=1), "utf-8")
    for w in written:
        print(w)
    return 0
