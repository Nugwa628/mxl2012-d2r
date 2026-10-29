"""icon.ico (256, 128, 64, 48, 32, 16, all 32-bit with alpha) and assets/icon.png (512): an eclipse in an X.

Two gold diagonals make the X of "XL"; the black eclipse disc with its ember rim sits on the crossing, on a dark
bronze-edged tile. Like common launcher icons: the 256 entry is PNG-compressed, the smaller ones are plain
BMP/DIB (works with every resource compiler, llvm-rc included).
"""
from __future__ import annotations

import io
import math
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from art_common import REPO

SIZES = (256, 128, 64, 48, 32, 16)


def render(n: int) -> Image.Image:
    ss = max(2, min(16, 1024 // n))  # supersampling: about 1024 px working size, so small icons get more
    N = n * ss
    bold = 1.0 + max(0.0, (48 - n) / 48.0) * 0.9  # thicker strokes on small sizes
    c = N / 2

    def L():
        return Image.new("L", (N, N), 0)

    def glow(mask, radius, color, strength) -> Image.Image:
        g = mask.filter(ImageFilter.GaussianBlur(radius * ss))
        lay = Image.new("RGBA", (N, N), color + (0,))
        lay.putalpha(g.point(lambda v: int(min(255, v * strength))))
        return lay

    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    # tile
    tile = L()
    ImageDraw.Draw(tile).rounded_rectangle([N * 0.03, N * 0.03, N * 0.97, N * 0.97], radius=N * 0.19, fill=255)
    grad = Image.new("RGBA", (N, N))
    gp = np.zeros((N, N, 4), np.uint8)
    t = np.linspace(0, 1, N)[:, None]
    gp[..., 0] = (34 - 24 * t).astype(np.uint8)
    gp[..., 1] = (15 - 8 * t).astype(np.uint8)
    gp[..., 2] = (24 - 12 * t).astype(np.uint8)
    gp[..., 3] = 255
    grad = Image.fromarray(gp, "RGBA")
    img.paste(grad, (0, 0), tile)
    edge = tile.copy()
    inner = L()
    w = max(1.0, N * 0.034 * (1 + (bold - 1) * 0.3))
    ImageDraw.Draw(inner).rounded_rectangle([N * 0.03 + w, N * 0.03 + w, N * 0.97 - w, N * 0.97 - w], radius=N * 0.19 - w, fill=255)
    edge_arr = np.clip(np.asarray(edge, np.int16) - np.asarray(inner, np.int16), 0, 255).astype(np.uint8)
    bronze = Image.new("RGBA", (N, N))
    bp = np.zeros((N, N, 4), np.uint8)
    d = np.linspace(1, 0, N)[None, :] * 0.5 + np.linspace(1, 0, N)[:, None] * 0.5
    bp[..., 0] = (80 + 120 * d).astype(np.uint8)
    bp[..., 1] = (50 + 86 * d).astype(np.uint8)
    bp[..., 2] = (30 + 50 * d).astype(np.uint8)
    bp[..., 3] = 255
    bronze = Image.fromarray(bp, "RGBA")
    img.paste(bronze, (0, 0), Image.fromarray(edge_arr, "L"))

    # glow behind the mark
    mark_glow = L()
    gdr = ImageDraw.Draw(mark_glow)
    r0 = N * 0.215
    gdr.ellipse([c - r0 * 1.5, c - r0 * 1.5, c + r0 * 1.5, c + r0 * 1.5], fill=170)
    img.alpha_composite(glow(mark_glow, N * 0.07 / ss, (190, 60, 30), 1.0))

    # the X: two gold bars with chamfered ends
    xm = L()
    xd = ImageDraw.Draw(xm)
    a, b = N * 0.21, N * 0.79
    th = N * 0.092 * bold
    for p0, p1 in (((a, a), (b, b)), ((b, a), (a, b))):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        ln = math.hypot(dx, dy)
        nx, ny = -dy / ln * th / 2, dx / ln * th / 2
        ux, uy = dx / ln * th * 0.5, dy / ln * th * 0.5
        # a bar with pointed ends
        xd.polygon([(p0[0] - ux, p0[1] - uy), (p0[0] + nx, p0[1] + ny), (p1[0] + nx, p1[1] + ny), (p1[0] + ux, p1[1] + uy), (p1[0] - nx, p1[1] - ny), (p0[0] - nx, p0[1] - ny)], fill=255)
    gold = np.zeros((N, N, 4), np.uint8)
    tt = np.linspace(0, 1, N)[:, None]
    gold[..., 0] = (255 - 70 * tt).astype(np.uint8)
    gold[..., 1] = (226 - 110 * tt).astype(np.uint8)
    gold[..., 2] = (150 - 100 * tt).astype(np.uint8)
    gold[..., 3] = 255
    # dark outline of the X so it separates from the glow
    outline = xm.filter(ImageFilter.MaxFilter(int(N * 0.02) * 2 + 1))
    out_layer = Image.new("RGBA", (N, N), (10, 4, 6, 0))
    out_layer.putalpha(outline)
    img.alpha_composite(out_layer)
    xl = Image.fromarray(gold, "RGBA")
    img.paste(xl, (0, 0), xm)
    # bevel highlight on the upper-left side of each bar
    hl = np.clip(np.asarray(xm, np.int16) - np.asarray(xm.transform(xm.size, Image.AFFINE, (1, 0, -N * 0.012, 0, 1, -N * 0.012)), np.int16), 0, 255).astype(np.uint8)
    hlay = Image.new("RGBA", (N, N), (255, 246, 215, 0))
    hlay.putalpha(Image.fromarray(hl, "L").point(lambda v: int(v * 0.8)))
    img.alpha_composite(hlay)

    # the eclipse: dark disc, ember corona, thin hot rim, a bead
    r = N * 0.205
    ring = L()
    ImageDraw.Draw(ring).ellipse([c - r - N * 0.02, c - r - N * 0.02, c + r + N * 0.02, c + r + N * 0.02], fill=255)
    img.alpha_composite(glow(ring, N * 0.045 / ss, (255, 110, 36), 1.15))
    disc = L()
    ImageDraw.Draw(disc).ellipse([c - r, c - r, c + r, c + r], fill=255)
    black = Image.new("RGBA", (N, N), (2, 1, 4, 0))
    black.putalpha(disc)
    img.alpha_composite(black)
    rim = L()
    rd = ImageDraw.Draw(rim)
    rw = max(1.0, N * 0.022 * bold)
    rd.ellipse([c - r - rw / 2, c - r - rw / 2, c + r + rw / 2, c + r + rw / 2], outline=255, width=int(rw))
    rimlay = Image.new("RGBA", (N, N), (255, 214, 150, 0))
    rimlay.putalpha(rim)
    img.alpha_composite(rimlay)
    if n >= 48:  # twelve ticks round the disc (XII)
        tk = L()
        td = ImageDraw.Draw(tk)
        for k in range(12):
            ang = math.radians(k * 30)
            r_a, r_b = r + N * 0.045, r + N * (0.07 if k % 3 == 0 else 0.058)
            td.line([(c + r_a * math.cos(ang), c + r_a * math.sin(ang)), (c + r_b * math.cos(ang), c + r_b * math.sin(ang))], fill=255, width=max(1, int(N * 0.011)))
        tl = Image.new("RGBA", (N, N), (255, 200, 130, 0))
        tl.putalpha(tk.point(lambda v: int(v * 0.85)))
        img.alpha_composite(tl)
    ba = math.radians(-38)
    bx, by = c + r * math.cos(ba), c + r * math.sin(ba)
    bead = L()
    br = max(1.5, N * 0.026 * bold)
    ImageDraw.Draw(bead).ellipse([bx - br, by - br, bx + br, by + br], fill=255)
    img.alpha_composite(glow(bead, N * 0.035 / ss, (255, 220, 160), 1.4))
    bl = Image.new("RGBA", (N, N), (255, 245, 225, 0))
    bl.putalpha(bead)
    img.alpha_composite(bl)
    return img.resize((n, n), Image.LANCZOS)


def dib(im: Image.Image) -> bytes:
    n = im.size[0]
    a = np.asarray(im.convert("RGBA"), np.uint8)
    bgra = a[..., [2, 1, 0, 3]][::-1]  # BGRA, bottom-up
    hdr = struct.pack("<IiiHHIIiiII", 40, n, n * 2, 1, 32, 0, bgra.nbytes, 0, 0, 0, 0)
    mask_row = ((n + 31) // 32) * 4
    return hdr + bgra.tobytes() + bytes(mask_row * n)  # all-zero AND mask: the alpha channel does the cutting


def write_ico(path: str, images: dict[int, Image.Image]) -> None:
    blobs = []
    for n in SIZES:
        if n >= 256:
            buf = io.BytesIO()
            images[n].save(buf, "PNG", optimize=True)
            blobs.append((n, buf.getvalue()))
        else:
            blobs.append((n, dib(images[n])))
    out = bytearray(struct.pack("<HHH", 0, 1, len(blobs)))
    off = 6 + 16 * len(blobs)
    for n, data in blobs:
        out += struct.pack("<BBBBHHII", 0 if n >= 256 else n, 0 if n >= 256 else n, 0, 0, 1, 32, len(data), off)
        off += len(data)
    for _, data in blobs:
        out += data
    Path(path).write_bytes(bytes(out))


def main(ico: str, png: str | None = None) -> None:
    imgs = {n: render(n) for n in SIZES}
    write_ico(ico, imgs)
    print("icon:", ico, [n for n in SIZES])
    if png:
        render(512).save(png, optimize=True)
        print("icon png:", png)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(REPO / "launcher" / "res" / "icon.ico"), sys.argv[2] if len(sys.argv) > 2 else None)
