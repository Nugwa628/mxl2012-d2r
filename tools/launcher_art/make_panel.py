"""popup-window.png (500 x 170, RGBA): the dark stone plaque behind the status text and the progress bar.

Drawn at (230,262) over the background: status text 270..690 x 284..360, line 363..383, bar 389..398, so the
frame stays within ~24 px of the edges. Original: chamfered iron-and-bronze frame, angular corner brackets with
rivets, twelve-tick eclipse emblem on the bottom edge, stone texture from value noise.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from art_common import add, blur, fbm, over, rng, REPO

W, H = 500, 170
S = 4  # supersampling for the drawn shapes
CH = 15  # corner chamfer
SEED = 2012


def mask(fn) -> np.ndarray:
    im = Image.new("L", (W * S, H * S), 0)
    fn(ImageDraw.Draw(im))
    return np.asarray(im.resize((W, H), Image.BOX), np.float32) / 255.0


def shape_pts(inset: float, ch: float = CH):
    i, c = inset, ch
    return [(i + c, i), (W - i - c, i), (W - i, i + c), (W - i, H - i - c), (W - i - c, H - i), (i + c, H - i), (i, H - i - c), (i, i + c)]


def poly(d: ImageDraw.ImageDraw, pts, fill=255):
    d.polygon([(x * S, y * S) for x, y in pts], fill=fill)


def line(d: ImageDraw.ImageDraw, pts, width: float, fill=255):
    d.line([(x * S, y * S) for x, y in pts], fill=fill, width=max(1, int(round(width * S))), joint="curve")


def ring(d: ImageDraw.ImageDraw, c, r, width, fill=255):
    d.ellipse([(c[0] - r) * S, (c[1] - r) * S, (c[0] + r) * S, (c[1] + r) * S], outline=fill, width=int(width * S))


def disc(d: ImageDraw.ImageDraw, c, r, fill=255):
    d.ellipse([(c[0] - r) * S, (c[1] - r) * S, (c[0] + r) * S, (c[1] + r) * S], fill=fill)


def corner_brackets(d: ImageDraw.ImageDraw, inset: float):
    """Angular brackets in each corner: an L that steps once, a diamond at the elbow, a rivet."""
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        ox = inset if sx > 0 else W - inset
        oy = inset if sy > 0 else H - inset

        def P(x, y):  # local coords (toward the inside) -> image
            return (ox + sx * x, oy + sy * y)

        line(d, [P(CH + 2, 6), P(34, 6), P(40, 11), P(58, 11)], 1.6)  # along the top/bottom edge
        line(d, [P(6, CH + 2), P(6, 34), P(11, 40), P(11, 58)], 1.6)  # along the side edge
        poly(d, [P(11, 11), P(16, 6), P(21, 11), P(16, 16)])  # diamond at the elbow
        disc(d, P(28, 11), 1.5)
        disc(d, P(11, 28), 1.5)


def build() -> Image.Image:
    # --- shapes
    outer = mask(lambda d: poly(d, shape_pts(0.5)))
    band = mask(lambda d: (poly(d, shape_pts(0.5)), poly(d, shape_pts(4.0, CH - 3), fill=0)))  # the 3.5 px iron band
    bronze = mask(lambda d: line(d, shape_pts(5.5, CH - 4) + [shape_pts(5.5, CH - 4)[0]], 1.4))
    inner = mask(lambda d: line(d, shape_pts(11.5, CH - 8) + [shape_pts(11.5, CH - 8)[0]], 0.8))
    # break the thin inner line near the middle of the top and bottom edges: a gap, with a diamond in it
    gap = mask(lambda d: [poly(d, [(W / 2 - 40, 0), (W / 2 + 40, 0), (W / 2 + 40, H), (W / 2 - 40, H)])])
    inner = inner * (1 - gap)
    brackets = mask(lambda d: corner_brackets(d, 5.5))
    mid = mask(
        lambda d: (
            poly(d, [(W / 2 - 7, 11.5), (W / 2, 5), (W / 2 + 7, 11.5), (W / 2, 18)]),  # top diamond
            line(d, [(W / 2 - 38, 11.5), (W / 2 - 10, 11.5)], 0.8),
            line(d, [(W / 2 + 10, 11.5), (W / 2 + 38, 11.5)], 0.8),
        )
    )
    # eclipse emblem on the bottom edge: dark disc, ember ring, twelve ticks
    ecx, ecy, er = W / 2, H - 11.5, 8.0

    def emblem(d):
        disc(d, (ecx, ecy), er + 3.5)
        for k in range(12):
            a = math.radians(k * 30)
            line(d, [(ecx + (er + 3.5) * math.cos(a), ecy + (er + 3.5) * math.sin(a)), (ecx + (er + 6.5) * math.cos(a), ecy + (er + 6.5) * math.sin(a))], 1.0)

    emb_back = mask(emblem)
    emb_disc = mask(lambda d: disc(d, (ecx, ecy), er))
    emb_ring = mask(lambda d: ring(d, (ecx, ecy), er, 1.3))
    emb_wings = mask(
        lambda d: (
            line(d, [(W / 2 - 74, H - 11.5), (W / 2 - 22, H - 11.5), (W / 2 - 17, H - 6)], 0.9),
            line(d, [(W / 2 + 74, H - 11.5), (W / 2 + 22, H - 11.5), (W / 2 + 17, H - 6)], 0.9),
        )
    )

    # --- stone texture
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    n1 = fbm(W, H, SEED + 40, base=6, octaves=6)
    n2 = fbm(W, H, SEED + 41, base=40, octaves=3)
    veins = np.exp(-(((fbm(W, H, SEED + 42, base=5, octaves=4) - 0.5) / 0.012) ** 2))
    r = rng(SEED + 43)
    speck = (r.random((H, W)) - 0.5) * 7
    tone = 0.62 + 0.55 * n1 + 0.2 * n2
    col = np.stack([32 * tone, 28 * tone, 33 * tone], -1) + speck[..., None]
    col *= (1.12 - 0.22 * yy / H)[..., None]  # a little lighter at the top
    col = add(col, (60, 52, 58), veins * 0.22)
    # inner shadow: the stone sits inside the frame
    edge_dark = 1 - np.clip(blur(band, 7) * 1.6, 0, 1)
    col = col * (0.55 + 0.45 * edge_dark)[..., None]

    img = col.copy()
    # iron band: dark, with a bevel (light from the top-left)
    iron = np.stack([22 + 16 * (1 - yy / H), 19 + 13 * (1 - yy / H), 22 + 15 * (1 - yy / H)], -1) * (0.7 + 0.6 * n2[..., None])
    img = over(img, iron, band)
    grad = np.clip(1 - (xx / W * 0.5 + yy / H * 0.5), 0, 1)
    bz = np.stack([74 + 130 * grad, 46 + 92 * grad, 28 + 56 * grad], -1)
    img = over(img, bz, bronze)
    img = over(img, (96, 62, 40), inner * 0.85)
    orn = np.clip(brackets + mid + emb_wings, 0, 1)
    img = over(img, np.stack([110 + 100 * grad, 70 + 74 * grad, 42 + 40 * grad], -1), orn)
    # eclipse emblem
    img = over(img, (14, 11, 14), emb_back)
    img = over(img, (2, 1, 3), emb_disc)
    img = over(img, (232, 160, 84), emb_ring)
    img = add(img, (255, 120, 40), blur(emb_ring, 2.5) * 0.45)

    alpha = outer * 250.0  # the stone is nearly opaque
    alpha = np.maximum(alpha, band * 255.0)  # the frame itself is opaque
    alpha = np.clip(alpha, 0, 255)
    out = np.dstack([np.clip(img, 0, 255), alpha]).astype(np.uint8)
    out[alpha < 1] = 0
    return Image.fromarray(out, "RGBA")


def main(out: str) -> None:
    im = build()
    assert im.size == (W, H)
    im.save(out, optimize=True)
    print("panel:", out, im.size, im.mode)


if __name__ == "__main__":
    import sys

    main(sys.argv[1] if len(sys.argv) > 1 else str(REPO / "launcher" / "res" / "popup-window.png"))
