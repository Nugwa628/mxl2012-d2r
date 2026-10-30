"""Sharper HD skill tree pages (lane skillhd, docs/hd-ui.md "Skill trees: HD page candidates"). OFF in the shipped build.

The shipped pages (skill_tree_art.median_page) are Median's classic page art scaled x 2.63 with Lanczos: the right place
and look, but soft (a 1 px frame line becomes a 3 px blur). The candidates here keep the page geometry of median_page
(the same three parts, the same cells, the moved level boxes), only the picture changes:

  rebuild        Median's page, rebuilt edge-aware (the idea of rune_hd) on its structure (frames, coloured rims,
                 arrows, box holes, level boxes: `structure`): every colour channel is taken apart in TONES levels,
                 each level's mask is EPX-scaled twice (staircases -> diagonals), smoothed and cut with an anti-aliased
                 edge at the HD size, the levels are stacked again and what lies between two levels comes back
                 bilinear: crisp straight edges, every colour Median's (no new palette). The stone between is Lanczos
                 with an unsharp mask (the decomposition makes stone look posterised).
  rebuild-stone  `rebuild` for the page's structure (frames, coloured rims, arrows, box holes: `structure`), and on the
                 stone between them D2R's own HD stone (panel_skilltreebg, the picture that shows behind D2R's tree, at
                 the same place) carrying Median's stone tone: Median's stone low-passed + D2R's stone high-passed.
  d2r            D2R's HD skill tree look with Median's layout: the page is left transparent so D2R's stone shows, every
                 skill gets D2R's own engraved socket + level box (cut from its frame 1), every arrow of Median's chains
                 D2R's own short arrow (cut from the same frame, the shaft stretched to the gap), Median's tree colours
                 (the coloured rim of each tree's boxes, sampled from the classic page) as a thin rim round the socket,
                 and a column without arrows (page 3's passives) inside an engraved frame as Median draws it.

Switch: tools/data/skill_tree_proposals.json (`enabled` false = the shipped Lanczos pages; `method` names the candidate it
would ship). A trial build: `skill_tree_art.py --try METHOD` or MXL2012_SKILLTREE_TRY=METHOD for `hd_ui.py build` /
`build.py` (owner review only, never committed on). Only numpy and Pillow.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from rune_hd import components, dilate, epx, gauss, resize_f

METHODS = ("lanczos", "rebuild", "rebuild-stone", "d2r")
PROPOSALS = Path(__file__).resolve().parent / "data" / "skill_tree_proposals.json"
SHARP = (2, 80, 2)  # rebuild: the stone's unsharp mask (radius HD px, percent, threshold)
TONES = 12          # levels per colour channel of the rebuild
SMOOTH = 0.35       # classic px: Gaussian on each level mask (at 4x) before the cut
AA = 0.7            # HD px: half-width of the cut's anti-aliasing ramp
PAD = 3             # classic px round each cropped part (no edge effects at the cuts)
STRUCT_BRIGHT, STRUCT_DARK, STRUCT_SAT = 135, 34, 38  # a classic pixel brighter / darker / more saturated is structure
CELL_REGION = (-5, -5, 76, 56)  # classic px round a cell's icon top left: its box and moved level box
COLUMN_MARGIN = 32  # classic px round a column's cells (page 3's passive frame runs 30 px left of column 3)
BORDER_REGION = 6   # classic px: the page's edge band
ARROW_REGION = (10, 74)  # classic px: half-width of the arrow gap below a cell, its bottom (from the icon's top)
STRUCT_MIN = 40     # pixels: smaller groups of such pixels are the stone's own spots
STONE_LOW = 3.0     # classic px: Gaussian of Median's stone (its tone, without its grain)
STONE_HIGH = 9.0    # HD px: D2R's stone minus its Gaussian of this = its grain
STONE_GAIN = 1.0    # strength of D2R's grain
D2R_ART = ("so", 1)  # D2R's sprite and frame the d2r sockets and arrow are cut from (Sorceress tab 2: both are on it)
BG_AT = (64, 15)    # the tree frame's origin in panel_skilltreebg (layout: frame at 132, 160, TreeBackground at 68, 145)
TINT_SAT, TINT_MIN = 40, 20  # a cell's tree colour: the mean of its box pixels more saturated than this (at least TINT_MIN)
TINT_ALPHA = 0.55   # d2r: strength of the tree colour rim
TINT_W = 4          # d2r: rim width (HD px)
FRAME_MARGIN = 26   # d2r: the passive frame's distance round the sockets (HD px)


def load_switch(path: Path = PROPOSALS) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {"enabled": False, "method": "lanczos"}


def used_method(data: dict, trial: str = "") -> str:
    """The method a build uses: `trial` (a trial build), else the switch's `method` when it is on, else lanczos."""
    m = trial.strip() or (data.get("method", "lanczos") if data.get("enabled") else "lanczos")
    if m not in METHODS:
        raise SystemExit(f"unknown skill tree method {m!r} (known: {', '.join(METHODS)})")
    return m


# ---- the edge-aware rebuild -----------------------------------------------------------------------------------------
def crisp_mask(m: np.ndarray, sw: int, sh: int) -> np.ndarray:
    """Coverage 0..1 at sw x sh of a boolean classic mask: EPX x 4, smoothed, scaled, cut with an AA edge."""
    big = Image.fromarray((epx(epx(m)) * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(SMOOTH * 4))
    f = np.asarray(big.resize((sw, sh), Image.Resampling.BICUBIC), np.float64) / 255
    gy, gx = np.gradient(f)
    return np.clip((f - 0.5) / (2 * AA * np.maximum(np.hypot(gx, gy), 0.05)) + 0.5, 0, 1)


def crisp_channel(v: np.ndarray, sw: int, sh: int, tones: int = TONES) -> np.ndarray:
    """One channel (0..255 floats, classic size) at sw x sh by threshold decomposition (module text)."""
    step = 255 / tones
    out = np.zeros((sh, sw))
    q = np.zeros_like(v)
    for i in range(1, tones + 1):
        t = i * step - step / 2      # a level counts a pixel at least half a step above the one below
        m = v >= t
        if not m.any():
            break
        q += step * m
        out += step * (np.ones((sh, sw)) if m.all() else crisp_mask(m, sw, sh))
    return out + resize_f(v - q, sw, sh, Image.Resampling.BILINEAR)


def rebuild(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """An RGBA picture (opaque, the page) rebuilt at `size` (module text, `rebuild`)."""
    a = np.asarray(im.convert("RGBA"), np.float64)
    sw, sh = size
    out = np.zeros((sh, sw, 4))
    for c in range(3):
        out[..., c] = crisp_channel(a[..., c], sw, sh)
    out[..., 3] = resize_f(a[..., 3], sw, sh, Image.Resampling.BILINEAR)
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGBA")


def lanczos(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    return im.resize(size, Image.LANCZOS)


def sharp(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Lanczos with an unsharp mask (SHARP_*): the stone of `rebuild`."""
    return lanczos(im, size).filter(ImageFilter.UnsharpMask(*SHARP))


def padded(scale):
    """`scale` applied to a crop with PAD classic px of its surroundings (the caller passes them), the pad cut off again."""
    def run(im: Image.Image, size: tuple[int, int], pad: tuple[int, int, int, int] = (0, 0, 0, 0)) -> Image.Image:
        w, h = im.width - pad[0] - pad[2], im.height - pad[1] - pad[3]
        kx, ky = size[0] / w, size[1] / h
        big = scale(im, (round(im.width * kx), round(im.height * ky)))
        x0, y0 = round(pad[0] * kx), round(pad[1] * ky)
        return big.crop((x0, y0, x0 + size[0], y0 + size[1]))
    return run


# ---- structure and stone (rebuild-stone) ----------------------------------------------------------------------------
def regions(shape: tuple[int, int], cells, col, row) -> np.ndarray:
    """Where a classic page draws its frame, boxes and arrows: its edge (BORDER_REGION px), each column's band of cells
    (COLUMN_MARGIN px round them), round each cell (box, moved level box: CELL_REGION from its icon's
    top left) and the arrow gap below it."""
    m = np.zeros(shape, bool)
    b = BORDER_REGION  # the page's own frame line
    m[:b], m[-b:], m[:, :b], m[:, -b:] = True, True, True, True
    x0, y0, x1, y1 = CELL_REGION
    cols: dict = {}
    for r, c in cells:
        cols.setdefault(c, []).append(r)
    for c, rows in cols.items():  # the column's band (page 3's passive frame runs round it)
        bx0, bx1 = CELL_REGION[0] - COLUMN_MARGIN, CELL_REGION[2] + COLUMN_MARGIN
        by0, by1 = row[min(rows)] + y0 - COLUMN_MARGIN, row[max(rows)] + y1 + COLUMN_MARGIN
        m[max(0, by0):by1, max(0, col[c] + bx0):col[c] + bx1] = True
    for r, c in cells:
        x, y = col[c], row[r]
        m[max(0, y + y0):y + y1, max(0, x + x0):x + x1] = True
        m[y + 48:y + ARROW_REGION[1], max(0, x + 24 - ARROW_REGION[0]):x + 24 + ARROW_REGION[0]] = True
    return m


def structure(page: Image.Image, cells=(), col=(), row=()) -> np.ndarray:
    """Boolean mask of a classic page's drawn structure, grown by 1 px: bright pixels anywhere (frames, the page border,
    the passive frame), and round the cells (`regions`) also dark (box holes, arrows) and saturated ones (the coloured
    rims); groups of fewer than STRUCT_MIN pixels are the stone's own spots."""
    a = np.asarray(page.convert("RGB"), np.int32)
    lum = a.mean(-1)
    near = regions(lum.shape, cells, col, row)
    s = (lum > STRUCT_BRIGHT) | (near & ((lum < STRUCT_DARK) | (a.max(-1) - a.min(-1) > STRUCT_SAT)))
    keep = np.zeros(s.shape, bool)
    for comp in components(s):
        if comp.sum() >= STRUCT_MIN:
            keep |= comp
    return dilate(keep, 1)


def mask_picture(page: Image.Image, cells=(), col=(), row=()) -> Image.Image:
    """The structure mask as an opaque RGBA picture (white = structure), to go through the same cut as the page."""
    m = (structure(page, cells, col, row) * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([m, m, m, np.asarray(page.convert("RGBA"))[..., 3]]), "RGBA")


def stone_picture(page: Image.Image, cells=(), col=(), row=()) -> Image.Image:
    """Median's stone tone: the page's colour averaged over its stone pixels only (STONE_LOW), structure filled in."""
    a = np.asarray(page.convert("RGBA"), np.float64)
    stone = ~structure(page, cells, col, row)
    w = gauss(stone, STONE_LOW)
    low = [np.where(w > 1e-4, gauss(a[..., c] * stone, STONE_LOW) / np.maximum(w, 1e-9), a[..., c]) for c in range(3)]
    return Image.fromarray(np.clip(np.rint(np.dstack(low + [a[..., 3]])), 0, 255).astype(np.uint8), "RGBA")


def d2r_grain(bg: Image.Image, size: tuple[int, int]) -> np.ndarray:
    """D2R's stone grain (high pass, mean 0, RGB) under a tree frame of `size`, from panel_skilltreebg."""
    crop = np.asarray(bg.convert("RGB").crop((BG_AT[0], BG_AT[1], BG_AT[0] + size[0], BG_AT[1] + size[1])), np.float64)
    if crop.shape[:2] != (size[1], size[0]):
        raise ValueError("panel_skilltreebg is smaller than the tree frame")
    return np.dstack([crop[..., c] - gauss(crop[..., c], STONE_HIGH) for c in range(3)])


def with_stone(crisp: Image.Image, mask: Image.Image, stone: np.ndarray) -> Image.Image:
    """The rebuilt frame where the (HD) mask says structure, `stone` (RGB array) elsewhere."""
    c = np.asarray(crisp, np.float64)
    w = np.asarray(mask, np.float64)[..., :1] / 255
    rgb = w * c[..., :3] + (1 - w) * stone
    return Image.fromarray(np.clip(np.rint(np.dstack([rgb, c[..., 3]])), 0, 255).astype(np.uint8), "RGBA")


# ---- d2r: D2R's sockets and arrows on Median's cells ----------------------------------------------------------------
def tree_colour(page: Image.Image, x: int, y: int) -> tuple[int, int, int] | None:
    """The colour of the rim of Median's box at classic (x, y) (icon top left), None for a grey box."""
    a = np.asarray(page.convert("RGB").crop((x - 4, y - 4, x + 52, y + 52)), np.int32)
    sat = a.max(-1) - a.min(-1) > TINT_SAT
    if sat.sum() < TINT_MIN:
        return None
    m = a[sat].mean(0)
    m = m * (200 / max(m.max(), 1))  # the hue at a fixed brightness (the rims are dark and light)
    return tuple(int(round(v)) for v in m)


def arrow_piece(d2r_frame: Image.Image, centre, row_top) -> Image.Image:
    """D2R's short down arrow between column 1's rows 2 and 3 of D2R_ART (the gap between the two sockets)."""
    cx, _ = centre((1, 0))
    top = centre((1, 0))[1] + 73
    bottom = row_top(2)
    return d2r_frame.crop((cx - 44, top, cx + 44, bottom))


def union(layer: np.ndarray, piece: Image.Image, at: tuple[int, int]) -> None:
    """Black shading `piece` merged into `layer` (alpha) by its maximum: overlapping pieces do not darken twice."""
    p = np.asarray(piece, np.float64)[..., 3]
    x, y = at
    h, w = p.shape
    x0, y0, x1, y1 = max(0, x), max(0, y), min(layer.shape[1], x + w), min(layer.shape[0], y + h)
    if x1 > x0 and y1 > y0:
        layer[y0:y1, x0:x1] = np.maximum(layer[y0:y1, x0:x1], p[y0 - y:y1 - y, x0 - x:x1 - x])


def d2r_page(d2r_frame: Image.Image, cells, arrows, tints: dict, geo) -> Image.Image:
    """One frame: D2R's sockets on `cells`, cut from `d2r_frame` (frame 1 of D2R's soskilltree: D2R_ART), D2R's arrow on `arrows`, tree colours `tints` {cell: rgb}, passive frames.
    geo: skill_tree_art (SOCKET_CROP, SOCKET_AT, SOCKET_HALF, cell_centre, SKILL_COL / ROW, ORIGIN, FW, FH)."""
    shade = np.zeros((geo.FH, geo.FW))
    dx = geo.SKILL_COL[1] - geo.SKILL_COL[0]  # the art's socket of column 2, row 1 (column 1 is empty on row 1)
    sock = d2r_frame.crop((geo.SOCKET_CROP[0] + dx, geo.SOCKET_CROP[1], geo.SOCKET_CROP[2] + dx, geo.SOCKET_CROP[3]))

    def row_top(r):  # top of the socket square of row r
        return geo.SKILL_ROW[r] - geo.ORIGIN[1] + geo.SOCKET_AT[1]
    piece = arrow_piece(d2r_frame, geo.cell_centre, row_top)
    for r, c in cells:
        union(shade, sock, (geo.SKILL_COL[c] - geo.ORIGIN[0] + geo.SOCKET_AT[0], row_top(r)))
    for (r0, c0), (r1, _c1) in arrows:
        cx = geo.cell_centre((r0, c0))[0]
        top, bottom = geo.cell_centre((r0, c0))[1] + geo.SOCKET_HALF[1], row_top(r1)
        gap = bottom - top
        p = piece
        if gap > p.height:  # a longer gap: the shaft (the piece's top row) repeated above
            p = Image.new("RGBA", (piece.width, gap))
            p.paste(piece.crop((0, 0, piece.width, 1)).resize((piece.width, gap - piece.height + 1)), (0, 0))
            p.paste(piece, (0, gap - piece.height))
        elif gap < p.height:
            p = piece.crop((0, piece.height - gap, piece.width, piece.height))
        union(shade, p, (cx - piece.width // 2, top))
    out = np.zeros((geo.FH, geo.FW, 4))
    out[..., 3] = shade
    # passive frames: a column of cells without any arrow gets an engraved frame round its sockets
    cols = {}
    for r, c in cells:
        cols.setdefault(c, []).append(r)
    linked = {c for (_a, (_r, c)) in arrows}
    rim = Image.new("L", (geo.FW, geo.FH))
    rd = ImageDraw.Draw(rim)
    for c, rows in cols.items():
        if c in linked or len(rows) < 2:
            continue
        x0 = geo.SKILL_COL[c] - geo.ORIGIN[0] + geo.SOCKET_AT[0] - FRAME_MARGIN
        x1 = geo.SKILL_COL[c] - geo.ORIGIN[0] + geo.SOCKET_AT[0] + sock.width + FRAME_MARGIN
        y0, y1 = row_top(min(rows)) - FRAME_MARGIN, row_top(max(rows)) + sock.height + FRAME_MARGIN
        rd.rounded_rectangle((x0, y0, x1, y1), radius=10, outline=255, width=7)
    groove = np.asarray(rim.filter(ImageFilter.GaussianBlur(1.2)), np.float64) / 255
    out[..., 3] = np.maximum(out[..., 3], groove * 120)
    # tree colours: a thin rim round each socket square
    tint = np.zeros((geo.FH, geo.FW, 3))
    gsum = np.zeros((geo.FH, geo.FW))
    for (r, c), rgb in tints.items():
        if rgb is None:
            continue
        cx, cy = geo.cell_centre((r, c))
        hx, hy = geo.SOCKET_HALF
        ring = Image.new("L", (geo.FW, geo.FH))
        ImageDraw.Draw(ring).rectangle((cx - hx, cy - hy, cx + hx, cy + hy), outline=255, width=TINT_W)
        g = np.asarray(ring.filter(ImageFilter.GaussianBlur(1.0)), np.float64) / 255
        tint += g[..., None] * np.array(rgb, np.float64)
        gsum += g
    col = tint / np.maximum(gsum, 1e-9)[..., None]
    ta = np.minimum(gsum, 1) * TINT_ALPHA
    a = out[..., 3] / 255
    fa = ta + a * (1 - ta)                      # the rim over the black shading
    rgb = col * (ta / np.maximum(fa, 1e-9))[..., None]
    out = np.dstack([rgb, fa * 255])
    return Image.fromarray(np.clip(np.rint(out), 0, 255).astype(np.uint8), "RGBA")
