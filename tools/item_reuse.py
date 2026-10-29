"""Which of the pictures item_art would upscale are really vanilla art, so D2R's own HD picture can be used instead.

item_art converts two groups of classic pictures to HD: `mxl` (the mod's DC6) and `classic` (D2R's classic DC6 of an
invfile no D2R item maps to an HD sprite). Some of them are vanilla pictures: unchanged (invrvex), recoloured (Median's
extra gem colours are D2R's gems in another colour) or resized. Each source picture is compared, by its palette
indices, with every D2R classic picture that has an HD sprite (tools/art_provenance.compare: silhouette IoU, index
equality, index-mapping consistency, brightness and detail correlation) and accepted as

  exact      the same picture: D2R's HD sprite as it is
  recolour   the same silhouette, colours mapped consistently: D2R's HD sprite with the hue / saturation / brightness
             shift of the index mapping (art_provenance.shift_of's hue and brightness; the saturation as a ratio, as
             D2R's HD art is more saturated than its classic art; applied by colour_shift.shift_pixels, the recolour of
             the HD effects); also a near silhouette (IoU >= NEAR_IOU) when brightness and detail agree strongly
             (Median redrew a few edge pixels of a gem)
  rescale    the same picture at another size (Median's half-size spellbook): D2R's HD sprite scaled the same way,
             recoloured when the colours differ

An exact match whose D2R sprite already has the right size and folder is used directly (the item map points at D2R's
asset, no file); everything else is rendered from D2R's HD sprite (and its lowend sprite) onto the item's cells and
written where item_art would have written the upscale. D2R's HD sprites are read from the D2R extraction
(fxpaths.D2R_DATA, read-only). Needs numpy and Pillow.
"""
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import art_provenance as ap  # noqa: E402
import upscale  # noqa: E402
from colour_shift import shift_pixels  # noqa: E402
from dc6 import read_dc6, read_sprite  # noqa: E402

NEAR_IOU = 0.93     # same-size silhouettes this close count as a recolour when ...
NEAR_CORR = 0.90    # ... brightness correlates this well and ...
NEAR_DETAIL = 0.80  # ... the fine structure (3 x 3 high-pass) correlates this well
RESCALE_IOU, RESCALE_CORR, RESCALE_DETAIL = 0.93, 0.75, 0.60  # another size: detail is lost in Median's resample
NEUTRAL = 0.02      # a shift smaller than this (hue turns, saturation, log2 brightness) is no recolour


@dataclass
class Match:
    d2r_inv: str
    folder: str           # D2R's folder of the HD sprite (weapon / armor / misc)
    asset: str            # D2R's asset under that folder
    kind: str             # exact / recolour / rescale
    scale: float          # source picture size / D2R classic picture size
    q: float
    shift: dict | None = field(default=None)  # {"hue", "sat" (factor), "val" (log2)} source relative to D2R; None = same colours

    def label(self) -> str:
        s = f"{self.kind} of {self.folder}/{self.asset} ({self.d2r_inv}, q {self.q:.2f}"
        if abs(self.scale - 1) > 0.03:
            s += f", scale {self.scale:.2f}"
        if self.shift:
            s += f", hue {self.shift['hue']:+.2f} sat x{self.shift['sat']:.2f} val {self.shift['val']:+.2f}"
        return s + ")"


def indices(path: Path) -> np.ndarray:
    """Palette indices (h, w) of frame 0 of a DC6; 0 where nothing is drawn."""
    w, h, _ox, _oy, block = read_dc6(path)[0]
    a = np.zeros((h, w), np.uint8)
    x, y, i = 0, h - 1, 0
    while i < len(block) and y >= 0:
        b = block[i]
        i += 1
        if b == 0x80:
            x, y = 0, y - 1
        elif b & 0x80:
            x += b & 0x7F
        else:
            run = block[i:i + b]
            if 0 <= y < h and x < w:
                n = min(len(run), w - x)
                a[y, x:x + n] = np.frombuffer(run[:n], np.uint8)
            x += b
            i += b
    return a


def tight(a: np.ndarray) -> np.ndarray | None:
    nz = a > 0
    if not nz.any():
        return None
    r, c = np.nonzero(nz.any(1))[0], np.nonzero(nz.any(0))[0]
    return a[r[0]:r[-1] + 1, c[0]:c[-1] + 1]


def _co(m: np.ndarray, v: np.ndarray) -> np.ndarray:
    th, tw = min(m.shape[0], v.shape[0]), min(m.shape[1], v.shape[1])
    m, v = ap.nn_resize(m, th, tw), ap.nn_resize(v, th, tw)
    both = (m > 0) & (v > 0)
    return np.bincount(m[both].astype(np.int64) * 256 + v[both], minlength=65536).reshape(256, 256)


def classify(m: np.ndarray, v: np.ndarray) -> tuple[str, float, float, np.ndarray | None] | None:
    """(kind, q, scale, index co-occurrence or None) of source crop m against D2R crop v, None when unrelated."""
    ap.TRACE = []
    try:
        r = ap.compare(m, v)
        t = ap.TRACE[-1] if ap.TRACE else None
    finally:
        ap.TRACE = None
    if r:
        kind = {"rescale+recolour": "rescale"}.get(r["kind"], r["kind"])
        co = r["co"] if r["co"] is not None else (_co(m, v) if kind == "rescale" else None)
        return kind, r["q"], r["scale"], co
    if t is None or t[6] is not None:
        return None
    iou, _eq, _cons, corr, detail, scale, _k = t
    same = abs(scale - 1) < 0.03 and abs(math.log((m.shape[1] / v.shape[1]) / (m.shape[0] / v.shape[0]))) < 0.12
    if same and iou >= NEAR_IOU and corr >= NEAR_CORR and detail >= NEAR_DETAIL:
        return "recolour", 0.5 * iou + 0.5 * corr, scale, _co(m, v)
    if not same and 0.3 <= scale <= 3.5 and iou >= RESCALE_IOU and corr >= RESCALE_CORR and detail >= RESCALE_DETAIL:
        return "rescale", 0.5 * iou + 0.5 * corr, scale, _co(m, v)
    return None


def find(sources: dict[str, Path], library: dict[str, tuple[str, str]], lib_dir: Path) -> dict[str, Match]:
    """Source key -> Match for the sources that are vanilla pictures. `sources`: key -> DC6 path; `library`: D2R invfile ->
    (folder, HD asset), its classic DC6 in lib_dir. The best kind wins (exact > recolour > rescale), then the quality."""
    lib = {}
    for inv, fa in sorted(library.items()):
        p = Path(lib_dir) / f"{inv}.dc6"
        if p.exists() and (c := tight(indices(p))) is not None:
            lib[inv] = (c, fa)
    rank = {"exact": 0, "recolour": 1, "rescale": 2}
    out = {}
    for k, path in sorted(sources.items()):
        m = tight(indices(path))
        if m is None:
            continue
        best = None
        for inv, (v, fa) in lib.items():
            if f"classic/{inv}" == k:
                continue
            if (r := classify(m, v)) and (best is None or (rank[r[0]], -r[1]) < (rank[best[1][0]], -best[1][1])):
                best = (inv, r, fa)
        if best:
            inv, (kind, q, scale, co), (folder, asset) = best
            shift = None
            if co is not None and co.sum():
                s = shift_of(co)
                if max(abs(s["hue"]), abs(math.log2(s["sat"])), abs(s["val"])) >= NEUTRAL:
                    shift = s
            out[k] = Match(inv, folder, asset, kind, round(scale, 3), round(q, 3), shift)
    return out


def shift_of(co: np.ndarray) -> dict:
    """{"hue" (turns), "sat" (factor), "val" (log2 factor)}: art_provenance.shift_of's hue and brightness, the saturation as
    the ratio of the pixel-weighted mean saturations (source indices / their most frequent D2R index)."""
    s = ap.shift_of(co)
    _h, sat, _v = ap.pal_hsv()
    w, best = co.sum(axis=1).astype(np.float64), co.argmax(axis=1)
    ratio = float((w * sat).sum() / max((w * sat[best]).sum(), 1e-6))
    return {"hue": round(s["hue"], 3), "sat": round(min(max(ratio, 0.0), 4.0), 3), "val": round(s["val"], 3)}


def direct(m: Match, folder: str, size: tuple[int, int], hd_items: Path) -> bool:
    """True when the item map can point at D2R's own asset: same picture, folder and sprite size."""
    if m.kind != "exact" or m.folder != folder or abs(m.scale - 1) > 0.03:
        return False
    p = Path(hd_items) / m.folder / f"{m.asset}.sprite"
    if not p.exists():
        return False
    from dc6 import sprite_info
    i = sprite_info(p)
    return (i["strip_width"], i["height"]) == size


def render(m: Match, out_w: int, out_h: int, lowend: bool, hd_items: Path) -> np.ndarray:
    """D2R's HD (or lowend) sprite of the match, scaled and recoloured as the match says, on an out_w x out_h canvas.
    A same-size sprite keeps D2R's placement; otherwise the picture is cropped to its content and centred."""
    p = Path(hd_items) / m.folder / f"{m.asset}{'.lowend' if lowend else ''}.sprite"
    a = upscale.rows_to_array(read_sprite(p)[0])
    if m.shift:
        a = shift_pixels(a, m.shift["hue"], 0.0, m.shift["val"], m.shift["sat"])
    if abs(m.scale - 1) <= 0.03 and a.shape[:2] == (out_h, out_w):
        return a
    nz = a[..., 3] > 0
    if nz.any():
        r, c = np.nonzero(nz.any(1))[0], np.nonzero(nz.any(0))[0]
        a = a[r[0]:r[-1] + 1, c[0]:c[-1] + 1]
    if abs(m.scale - 1) > 0.03:
        a = upscale.resize(a, max(1, round(a.shape[1] * m.scale)), max(1, round(a.shape[0] * m.scale)))
    return upscale.place(a, out_w, out_h)
