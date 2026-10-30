"""Median's rune and signet signs as clean strokes (lane itemart3, round 3), and the chisel that cuts them into D2R art.

Each sign is redrawn by hand from Median's classic picture (the tight crop of the DC6 frame, 24 x 23 px for a rune,
26 x 26 for a signet) as strokes in that picture's pixel coordinates (pixel x, y = its column and row; the centre of a
pixel, the renderer adds 0.5). The strokes follow the classic glyph pixel for pixel where it is clear and its intended
shape where the classic picture is too small to show it (Qor is a skull).

Primitives (w = full stroke width in classic px, default W):
  ("line", [(x, y), ...], w)            an open polyline, ends tapered like a chisel cut
  ("loop", [(x, y), ...], w)            a closed polyline
  ("ring", (cx, cy, rx, ry), w)         an ellipse (a0, a1 in degrees, 0 = right, 90 = down, optional: an arc)
  ("dot", (cx, cy, r))                  a drilled round hole
  ("fill", [(x, y), ...])               a sunk polygon (bevelled walls, flat floor)

`chisel` renders a sign at any size with crisp, supersampled edges: a V-cut groove whose wall facing the light (from the
top left, as D2R's own runes) is lit and whose other wall is in shadow, the floor dark; no blur anywhere.
"""
from __future__ import annotations

import numpy as np

W = 1.75   # stroke width in classic px (D2R's rune strokes are ~7 px of a 98 px stone, ~2 classic px)
SS = 4     # supersampling per output pixel

RUNES: dict[str, list] = {
    # Nih: a tall rounded box
    "mxl/r-a-01": [("loop", [(9.6, 8.2), (13.6, 8.2), (13.6, 14.2), (9.6, 14.2)], 1.9)],
    # Lai: a stem with a left arm, a crossbar and a bowl under it
    "mxl/r-a-02": [("line", [(11.6, 6.0), (11.6, 13.0)]), ("line", [(11.2, 7.2), (8.6, 10.4)]),
                   ("line", [(8.0, 13.0), (14.1, 13.0), (14.1, 15.3), (12.8, 16.4), (10.6, 16.4), (9.2, 15.4)])],
    # On: three bars, a hook under the top one, the bottom one a flat cup
    "mxl/r-a-03": [("line", [(9.8, 8.5), (15.6, 8.5)]), ("line", [(13.6, 8.6), (14.0, 10.4)]),
                   ("line", [(8.4, 12.6), (16.0, 12.6)]),
                   ("line", [(8.8, 14.8), (8.8, 16.6), (16.0, 16.6), (16.0, 14.8)])],
    # Sha: a long S-hook down to a straight stem, a short right branch
    "mxl/r-a-05": [("line", [(10.0, 3.8), (11.4, 5.8), (9.6, 8.6), (8.4, 11.4), (9.3, 13.3), (10.9, 15.0),
                             (10.9, 19.8)]),
                   ("line", [(12.0, 6.9), (13.3, 8.5), (13.3, 11.2)], 1.4)],
    # Lah: an arch over a stem, a diagonal down to a foot
    "mxl/r-a-06": [("line", [(7.5, 8.6), (7.8, 6.3), (9.2, 4.7), (13.9, 4.7), (15.5, 6.3), (15.6, 8.6)]),
                   ("line", [(10.6, 9.0), (10.6, 18.6)]),
                   ("line", [(11.2, 11.4), (12.6, 14.6), (13.8, 17.3), (15.6, 17.3), (15.6, 15.4)])],
    # Kur: two hooks on top, a stem, a cup at the bottom
    "mxl/r-a-07": [("line", [(7.2, 5.2), (9.4, 5.2), (11.2, 7.6), (12.4, 9.6), (12.9, 12.4)]),
                   ("line", [(13.3, 5.8), (14.4, 7.6)]), ("line", [(14.6, 5.3), (16.3, 6.4), (16.3, 9.8)]),
                   ("line", [(10.6, 9.6), (10.6, 15.0)]),
                   ("line", [(9.2, 15.8), (9.2, 18.7), (14.9, 18.7), (14.9, 15.8)])],
    # Ix: a thick X over a stem
    "mxl/r-a-08": [("line", [(8.2, 5.2), (13.8, 13.4)], 2.1), ("line", [(14.2, 5.4), (8.6, 13.4)], 2.1),
                   ("line", [(10.8, 15.2), (10.8, 19.6)], 2.0)],
    # Thur: a 3
    "mxl/r-a-09": [("line", [(8.8, 6.6), (10.2, 4.4), (13.8, 4.4), (15.4, 6.2), (15.4, 8.8), (13.8, 10.6), (10.6, 11.0)]),
                   ("line", [(13.8, 11.2), (15.4, 13.0), (15.4, 16.0), (13.8, 17.8), (10.2, 17.8), (8.8, 15.8)])],
    # Nas: a trident: a stem with a cap, a left arm down to the base, a right arm into the stem
    "mxl/r-a-10": [("line", [(9.8, 4.3), (13.8, 4.3)]), ("line", [(11.8, 4.3), (11.8, 15.5), (11.5, 20.0)], 2.0),
                   ("line", [(6.6, 7.0), (6.7, 10.6), (8.4, 12.2), (9.3, 13.6), (9.3, 19.5)]),
                   ("line", [(16.6, 7.0), (16.6, 10.5), (15.3, 12.0), (12.6, 12.4)])],
    # Ath: a loop over a right stem, a bar across, a sunk bar at the bottom
    "mxl/r-a-11": [("line", [(9.2, 8.6), (9.2, 5.4), (10.3, 4.3), (13.3, 4.3), (15.2, 6.0), (15.2, 15.4)]),
                   ("line", [(9.8, 12.0), (15.2, 12.0)]),
                   ("fill", [(9.3, 15.0), (14.6, 15.0), (14.6, 17.6), (9.9, 17.6)])],
    # Kra: four arms from a sunk centre
    "mxl/r-a-12": [("line", [(7.6, 3.4), (9.4, 6.0), (10.6, 10.0)]), ("line", [(16.3, 5.6), (14.6, 9.0), (12.8, 10.6)]),
                   ("line", [(9.0, 12.6), (6.8, 15.0), (5.6, 18.2)]), ("line", [(12.8, 13.0), (14.4, 15.6), (16.9, 18.4)]),
                   ("fill", [(9.0, 10.0), (13.6, 9.6), (13.2, 13.2), (9.0, 13.6)])],
    # Vith: a ring on a short stem, a dot inside
    "mxl/r-a-13": [("line", [(11.6, 5.0), (11.6, 10.0)], 1.9), ("ring", (11.8, 13.8, 3.9, 3.6), 1.7),
                   ("dot", (11.6, 12.6, 1.0))],
    # No: an arch, the left leg long, a bar inside, a stem below
    "mxl/r-a-14": [("line", [(7.8, 16.4), (7.8, 7.0), (9.2, 5.4), (14.6, 5.3), (16.6, 7.0), (16.6, 12.4)]),
                   ("line", [(10.0, 10.3), (13.9, 10.3)]), ("line", [(11.6, 14.0), (11.6, 19.6)], 2.0)],
    # Yul: a squared 3
    "mxl/r-a-15": [("line", [(9.5, 6.4), (13.2, 6.3), (14.2, 7.5), (14.2, 14.0), (13.2, 15.3), (9.4, 15.6)]),
                   ("line", [(9.3, 10.6), (14.2, 10.6)], 2.0)],
    # Thai: a box with its top bar running out left, two bars below
    "mxl/r-a-16": [("loop", [(10.3, 8.3), (15.2, 8.3), (15.2, 13.5), (10.3, 13.5)]), ("line", [(8.0, 8.3), (10.3, 8.3)]),
                   ("line", [(8.0, 16.2), (15.2, 16.2)]), ("line", [(10.3, 18.3), (15.2, 18.3)])],
    # Rha: a squared G with an inner curl
    "mxl/r-a-17": [("line", [(14.2, 8.6), (13.6, 6.4), (9.6, 6.3), (8.3, 7.6), (8.3, 18.3), (14.3, 18.3), (14.3, 14.0)]),
                   ("line", [(10.9, 12.2), (13.0, 12.2), (14.3, 13.6)], 1.5)],
    # Xar: a small loop over a box with a bar and a curl inside
    "mxl/r-a-18": [("ring", (11.4, 5.0, 3.0, 1.5), 1.5),
                   ("line", [(7.0, 17.2), (7.0, 9.3), (15.6, 9.3), (15.6, 17.0)]), ("line", [(9.6, 13.1), (15.6, 13.1)]),
                   ("line", [(10.0, 15.4), (11.0, 17.2), (13.3, 18.0), (15.6, 17.0)])],
    # Taha: a bar with a stem down on the left and a short drop on the right
    "mxl/r-d-02": [("line", [(8.0, 8.6), (15.6, 8.6)]), ("line", [(9.6, 8.8), (10.2, 14.0), (10.9, 17.4)]),
                   ("line", [(14.0, 9.0), (13.2, 11.6)])],
    # Auhe: an eight-armed star around a sunk centre
    "mxl/r-d-04": [("fill", [(10.4, 9.4), (13.0, 9.4), (14.4, 10.8), (14.4, 13.2), (13.0, 14.6), (10.4, 14.6),
                             (9.0, 13.2), (9.0, 10.8)]),
                   ("line", [(11.7, 6.4), (11.7, 9.6)]), ("line", [(6.3, 12.0), (9.2, 12.0)]),
                   ("line", [(17.0, 12.0), (14.2, 12.0)]), ("line", [(11.7, 17.4), (11.7, 14.4)]),
                   ("line", [(8.0, 8.2), (9.9, 10.0)], 1.4), ("line", [(15.4, 8.6), (13.6, 10.0)], 1.4),
                   ("line", [(8.2, 16.0), (9.9, 14.0)], 1.4), ("line", [(15.0, 15.6), (13.5, 14.0)], 1.4)],
    # Ghal: six drilled holes around a centre
    "mxl/r-d-05": [("dot", (11.7, 7.6, 1.25)), ("dot", (8.0, 10.1, 1.25)), ("dot", (15.4, 10.1, 1.25)),
                   ("dot", (8.0, 14.0, 1.25)), ("dot", (15.4, 14.0, 1.25)), ("dot", (11.7, 16.4, 1.25))],
    # Krys: a wide U on a stem
    "mxl/r-d-07": [("line", [(6.5, 7.8), (6.6, 11.6), (8.2, 13.4), (10.4, 14.4), (12.6, 14.4), (15.0, 13.3),
                             (16.5, 11.0), (16.9, 6.6)]),
                   ("line", [(11.6, 14.4), (11.6, 19.6)], 2.0)],
    # Qor: a skull and crossbones (the classic picture's skull over a cross of bones)
    "mxl/r-d-11": [("loop", [(9.3, 13.0), (8.6, 11.0), (8.6, 8.8), (9.8, 6.9), (11.7, 6.1), (13.6, 6.9), (14.8, 8.8),
                             (14.8, 11.0), (14.1, 13.0), (13.4, 13.8), (10.0, 13.8)], 1.6),
                   ("dot", (10.6, 9.9, 1.15)), ("dot", (12.8, 9.9, 1.15)),
                   ("fill", [(11.7, 11.2), (12.25, 12.5), (11.15, 12.5)]),
                   ("line", [(8.2, 15.0), (15.2, 18.3)], 1.6), ("line", [(15.2, 15.0), (8.2, 18.3)], 1.6),
                   ("dot", (7.7, 14.7, 0.95)), ("dot", (15.7, 14.7, 0.95)), ("dot", (7.7, 18.6, 0.95)),
                   ("dot", (15.7, 18.6, 0.95))],
    # Sha'ad: a lightning bolt from the top right down to the bottom left
    "mxl/r-d-12": [("line", [(15.9, 5.8), (9.4, 11.4), (12.8, 12.0), (5.4, 18.4)], 2.0)],
}

SIGNETS: dict[str, list] = {
    # Learning: a slanted stem with a tick, a bowl at its foot (a b)
    "mxl/sigil1b": [("line", [(8.8, 9.6), (10.6, 9.2)], 1.4),
                    ("line", [(10.2, 9.0), (11.4, 11.4), (12.2, 13.8), (12.2, 18.6)], 1.6),
                    ("ring", (14.1, 16.6, 1.9, 2.1), 1.5)],
    # Greater Gold: a stem between two half-moons
    "mxl/sigil2b": [("line", [(12.5, 8.0), (12.5, 17.6)], 1.8),
                    ("ring", (12.5, 12.5, 3.8, 3.8, 165, 245), 1.4), ("ring", (12.5, 12.5, 3.8, 3.8, 295, 375), 1.4)],
    # Gold: a cross over a stem that curls right and down (as Saturn's sign)
    "mxl/sigil3b": [("line", [(10.0, 9.3), (14.8, 9.3)], 1.5),
                    ("line", [(12.3, 7.8), (12.3, 12.4), (13.8, 12.8), (15.0, 14.2), (14.8, 15.8), (13.4, 17.0),
                              (12.2, 17.5)], 1.5)],
    # Skill: a hooked arch with a bar across its foot
    "mxl/sigil4b": [("line", [(10.2, 10.8), (10.6, 9.2), (12.2, 8.3), (14.2, 8.4), (15.3, 9.8), (15.3, 16.4),
                              (16.5, 16.4)], 1.5),
                    ("line", [(10.4, 14.6), (15.3, 14.6)], 1.5), ("line", [(10.4, 14.6), (10.4, 16.3), (11.8, 16.3)], 1.5)],
    # Experience: a cup on a long stem, a guard whose ends bend down
    "mxl/sigil5b": [("line", [(10.2, 7.8), (10.2, 9.4), (14.6, 9.4), (14.6, 7.8)], 1.4),
                    ("line", [(12.4, 9.4), (12.4, 19.0)], 1.9),
                    ("line", [(8.6, 13.4), (8.6, 10.8), (16.4, 10.8), (16.4, 13.4)], 1.4)],
    # Greater Experience: two zig-zags side by side
    "mxl/sigil6b": [("line", [(9.0, 8.8), (11.2, 11.2), (9.4, 12.6), (9.4, 15.2), (11.4, 17.2)], 1.4),
                    ("line", [(13.4, 8.2), (15.6, 10.6), (14.2, 12.4), (14.4, 15.2), (15.8, 17.0)], 1.4)],
    # Greater Learning: two arches on three posts over a base with turned-out feet
    "mxl/sigilxl": [("line", [(9.3, 15.3), (9.3, 9.3), (10.3, 8.3), (11.8, 8.3), (12.6, 9.3), (12.6, 15.3)], 1.4),
                    ("line", [(12.6, 9.3), (13.4, 8.3), (14.8, 8.3), (15.6, 9.3), (15.6, 15.3)], 1.4),
                    ("line", [(7.0, 16.6), (9.0, 15.4), (15.9, 15.4), (17.5, 16.6), (17.6, 17.4)], 1.4)],
}

GLYPHS = {**RUNES, **SIGNETS}


# -- signed distance (classic px; < 0 inside the cut) -------------------------------------------------------------
def _seg_dist(px: np.ndarray, py: np.ndarray, a: tuple, b: tuple) -> tuple[np.ndarray, np.ndarray]:
    """Distance from points to segment a-b, and the parameter (0..1) of the nearest point."""
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = np.zeros_like(px) if ll == 0 else np.clip(((px - ax) * dx + (py - ay) * dy) / ll, 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy)), t


def _ellipse(cx, cy, rx, ry, a0=0.0, a1=360.0) -> list[tuple[float, float]]:
    n = max(8, int(abs(a1 - a0) / 6))
    a = np.radians(np.linspace(a0, a1, n + 1))
    return list(zip(cx + rx * np.cos(a), cy + ry * np.sin(a)))


def _polyline_sd(px, py, pts, w, taper: bool) -> np.ndarray:
    """Signed distance to a stroke of width w along pts; open strokes narrow towards their ends (a chisel's cut)."""
    pts = [(x + 0.5, y + 0.5) for x, y in pts]
    seg = [np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
    total, run = sum(seg) or 1.0, 0.0
    best = np.full(px.shape, np.inf)
    for (a, b), ln in zip(zip(pts, pts[1:]), seg):
        d, t = _seg_dist(px, py, a, b)
        hw = np.full(px.shape, w / 2)
        if taper:
            s = run + t * ln
            end = np.minimum(s, total - s)
            hw = w / 2 * (0.72 + 0.28 * np.clip(end / max(w * 0.9, 1e-6), 0, 1))
        best = np.minimum(best, d - hw)
        run += ln
    return best


def _polygon_sd(px, py, pts) -> np.ndarray:
    pts = [(x + 0.5, y + 0.5) for x, y in pts]
    d = np.full(px.shape, np.inf)
    inside = np.zeros(px.shape, bool)
    for a, b in zip(pts, pts[1:] + pts[:1]):
        d = np.minimum(d, _seg_dist(px, py, a, b)[0])
        cross = ((a[1] > py) != (b[1] > py)) & (px < (b[0] - a[0]) * (py - a[1]) / ((b[1] - a[1]) or 1e-9) + a[0])
        inside ^= cross
    return np.where(inside, -d, d)


def signed_distance(glyph: list, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """Signed distance (classic px) of points px, py (classic coordinates, pixel corners at integers) to the sign."""
    sd = np.full(px.shape, np.inf)
    for p in glyph:
        kind = p[0]
        if kind in ("line", "loop"):
            pts = list(p[1]) + ([p[1][0]] if kind == "loop" else [])
            sd = np.minimum(sd, _polyline_sd(px, py, pts, p[2] if len(p) > 2 else W, kind == "line"))
        elif kind == "ring":
            e = p[1]
            arc = len(e) > 4
            pts = _ellipse(*e) if arc else _ellipse(*e[:4])
            sd = np.minimum(sd, _polyline_sd(px, py, pts, p[2] if len(p) > 2 else W, arc))
        elif kind == "dot":
            cx, cy, r = p[1]
            sd = np.minimum(sd, np.hypot(px - cx - 0.5, py - cy - 0.5) - r)
        elif kind == "fill":
            sd = np.minimum(sd, _polygon_sd(px, py, p[1]))
    return sd


# -- the chisel ---------------------------------------------------------------------------------------------------
LIGHT = np.array([-1.0, -1.0]) / np.sqrt(2)   # from the top left, as D2R's runes


def chisel(rgb: np.ndarray, glyph: list, to_classic, wall: float = 0.55, floor: float = 0.12, lit: float = 0.9,
           shadow: float = 0.35, lip: float = 0.22, inside: np.ndarray | None = None) -> np.ndarray:
    """`rgb` (H x W x 3, float or uint8) with `glyph` cut in. `to_classic(x, y)` maps output pixel coordinates (floats,
    pixel corners at integers) to the classic picture's. The cut: a V groove whose outer `wall` (classic px) is a slope
    lit by LIGHT on its far side and shadowed on its near side, then a dark floor (`floor` x the surface); edges are
    supersampled SS x SS, nothing is blurred. `inside` (H x W bool) limits the cut."""
    h, w = rgb.shape[:2]
    o = (np.arange(SS) + 0.5) / SS
    ys = (np.arange(h)[:, None] + o[None, :]).reshape(-1)
    xs = (np.arange(w)[:, None] + o[None, :]).reshape(-1)
    X, Y = np.meshgrid(xs, ys)
    cx, cy = to_classic(X, Y)
    sd = signed_distance(glyph, cx, cy)
    gy, gx = np.gradient(sd)
    n = np.hypot(gx, gy)
    n[n == 0] = 1
    facing = -(gx * LIGHT[0] + gy * LIGHT[1]) / n   # > 0: the slope faces the light (the cut's far side)
    depth = np.clip(-sd / wall, 0, 1)                 # 0 at the edge, 1 where the floor starts
    slope = np.where(facing > 0, 1 + lit * facing, shadow + (1 - shadow) * (1 + facing) / 2)
    k = np.where(depth < 0.5, slope, floor)            # the slope, then the floor: two crisp steps
    k = np.where(sd < 0, k, np.where((sd < lip) & (facing > 0), 1 + 0.35 * facing, 1.0))  # a lit lip outside, far side
    k = k.reshape(h, SS, w, SS).mean(axis=(1, 3))
    cut = (sd < 0).reshape(h, SS, w, SS).mean(axis=(1, 3)) > 0
    if inside is not None:
        k = np.where(inside, k, 1.0)
        cut &= inside
    out = rgb.astype(np.float64) * k[..., None]
    return out, cut
