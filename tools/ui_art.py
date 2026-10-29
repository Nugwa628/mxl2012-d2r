"""Shared picture helpers of the UI tools (Pillow): classic DC6 panel sets, D2R sprites, quantising back to DC6.

A classic panel picture is 320 x 432 (D2R's classic panel; the virtual screen is 640 x 480), stored as sets of 4 DC6
frames: 256 x 256, 64 x 256, 256 x 176, 64 x 176 (2 x 2 tiles). `skltree_<x>_back.dc6` has 4 sets (set 0 only the tab
column, sets 1-3 one tab each), `invchar6.dc6` 2 (character sheet, inventory), `supertransmogrifier.dc6` and
`tradestash.dc6` 1.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402

import dc6  # noqa: E402

PANEL_W, PANEL_H = 320, 432
TILES = ((0, 0, 256, 256), (256, 0, 320, 256), (0, 256, 256, 432), (256, 256, 320, 432))  # box in the panel, per frame of a set


def palette(path: Path) -> list[tuple[int, int, int]]:
    if not Path(path).exists():
        sys.exit(f"{path} missing: run `py -3 tools/hd_ui.py baseline <a D2R 93847 extraction>` first (or tools/hd_icons.py baseline)")
    return dc6.palette(path)


def to_image(rows: dc6.Rows) -> Image.Image:
    im = Image.new("RGBA", (len(rows[0]), len(rows)))
    im.putdata([p for r in rows for p in r])
    return im


def panel_sets(path: Path, pal) -> list[Image.Image]:
    """Every set of a classic panel DC6 as a 320 x 432 RGBA image (index 0 = transparent)."""
    frames = dc6.read_dc6(path)
    if len(frames) % 4:
        raise ValueError(f"{path}: {len(frames)} frames is not a whole number of 4-tile sets")
    out = []
    for s in range(len(frames) // 4):
        im = Image.new("RGBA", (PANEL_W, PANEL_H))
        for t, (x, y, w, h) in enumerate(TILES):
            fw, fh, _ox, _oy, block = frames[s * 4 + t]
            if (fw, fh) != (w - x, h - y):
                raise ValueError(f"{path}: set {s} tile {t} is {fw}x{fh}, expected {w - x}x{h - y}")
            im.paste(to_image(dc6.decode_frame(fw, fh, block, pal)), (x, y))
        out.append(im)
    return out


def read_sprite(path: Path) -> list[Image.Image]:
    """Frames of a D2R .sprite (version 31, RGBA) as images (frame width from the header, stride = strip width / frames)."""
    info = dc6.sprite_info(path)
    d = Path(path).read_bytes()
    sw, h, n, fw = info["strip_width"], info["height"], info["frames"], info["frame_width"]
    if len(d) < dc6.HEADER + sw * h * 4:
        raise ValueError(f"{path}: truncated")
    strip = Image.frombytes("RGBA", (sw, h), d[dc6.HEADER:dc6.HEADER + sw * h * 4])
    stride = sw // n
    return [strip.crop((i * stride, 0, i * stride + fw, h)) for i in range(n)]


def write_sprite(path: Path, frames: list[Image.Image], stride: int | None = None) -> None:
    """Frames side by side in stride-wide cells. A single picture: frame width = its width; a strip: frame width
    stride - 2 (D2R's skill tree strip: 895 in 897)."""
    w, h = frames[0].size
    stride = stride or w
    strip = Image.new("RGBA", (stride * len(frames), h))
    for i, f in enumerate(frames):
        strip.paste(f, (i * stride, 0))
    fw = w if len(frames) == 1 else stride - 2
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(dc6.sprite_bytes(fw, strip.width, h, len(frames), strip.tobytes()))


def save_png(path: Path, im: Image.Image, bg=(60, 0, 60)) -> None:
    """A preview PNG over a flat background colour (so transparent areas are visible)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    base = Image.new("RGBA", im.size, bg + (255,))
    base.alpha_composite(im)
    base.convert("RGB").save(path)
