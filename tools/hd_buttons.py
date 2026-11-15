"""HD art of the mod's own square buttons in D2R HD's button style: Send to stash (tools/send_stash.py, also the gamepad
inventory's copy in tools/pad_ui.py) and invtabs' Charms button (tools/invtabs_hdart.py; bug #592).

A button is three layers:
  rim     D2R's HD close button (PANEL\\closebtn_4x, frame 0; greyed: its disabled frame 2): the grey stone bevel with its
          dark inner line, its red inside cut out. Nine-sliced to the size (corners kept, edges stretched along their
          length), so the rim keeps D2R's thickness at the layout's scale; small buttons scale it down a little first
          (D2R's own small buttons have thinner rims), never up.
  well    the dark inside of a cell of D2R's HD stash grid (PANEL\\Stash\\StashPanel_BG_Personal), with an inner shadow on its
          top and left edges, so the inside reads as recessed like the close button's.
  icon    drawn here as vector shapes at 4 x size and shaded as metal / gem by a height map lit from the top left (no
          bitmap of anyone else's): Send to stash an arrow going down into an open chest (wood, gold bands, lock),
          Charms a blue charm stone in a gold setting on a ring.
States: normal; hovered (well and icon lighter, as D2R's hover lights the close button's inside); pressed (the body one
pixel down-right, a shorter shadow, inside darker); greyed (the rim's disabled frame, icon and well grey). A drop shadow
under the body as D2R's buttons carry in their sprites.

D2R's pictures are read at build time (tools/fxpaths.d2r_file); nothing of Blizzard's is in git. `Sources.drawn()` is a
plain stand-in for the unit tests on machines without D2R; builds always use `Sources.d2r()`.

    py -3 -I tools/hd_buttons.py preview [DIR]   both buttons, all states, at 1x and 3x over D2R's inventory stone
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RIM_SOURCE = "data/hd/global/ui/panel/closebtn_4x.sprite"
RIM_BODY = (12, 4, 72, 65)          # the close button's opaque body in its 83 x 84 frame (x1 / y1 exclusive)
RIM_INNER = (9, 8, 10, 13)          # the rim's width left, top, right, bottom inside RIM_BODY (the red inside starts there)
RIM_CORNER = 16                     # corner squares kept as they are when nine-slicing
RIM_FRAMES = {"normal": 0, "greyed": 2}
WELL_SOURCE = "data/hd/global/ui/panel/stash/stashpanel_bg_personal.sprite"
WELL_CELL = (89 + 6, 219 + 6, 89 + 92, 219 + 92)  # inside the first stash cell's gold line (cells of 98 at 89, 219)
KINDS = ("normal", "hovered", "pressed", "greyed")
SS = 4                              # supersampling of the icon shapes


@dataclass
class Sources:
    rim: Image.Image                # RIM_BODY-sized RGBA, normal
    rim_greyed: Image.Image
    well: Image.Image               # RGB texture

    @staticmethod
    def d2r() -> "Sources":
        import fxpaths
        import ui_art
        frames = ui_art.read_sprite(fxpaths.d2r_file(RIM_SOURCE))
        rims = {k: frames[i].convert("RGBA").crop(RIM_BODY) for k, i in RIM_FRAMES.items()}
        bg = ui_art.read_sprite(fxpaths.d2r_file(WELL_SOURCE))[0].convert("RGB")
        return Sources(rims["normal"], rims["greyed"], bg.crop(WELL_CELL))

    @staticmethod
    def drawn() -> "Sources":
        """A flat grey rim and a flat dark well (unit tests without D2R's files)."""
        w, h = RIM_BODY[2] - RIM_BODY[0], RIM_BODY[3] - RIM_BODY[1]
        rims = []
        for grey in (110, 70):
            im = Image.new("RGBA", (w, h), (grey, grey, grey - 6, 255))
            ImageDraw.Draw(im).rectangle([RIM_INNER[0] - 2, RIM_INNER[1] - 2, w - RIM_INNER[2] + 1, h - RIM_INNER[3] + 1],
                                         fill=(8, 8, 8, 255))
            rims.append(im)
        return Sources(rims[0], rims[1], Image.new("RGB", (86, 86), (16, 15, 14)))


_CACHE: dict[str, Sources] = {}


def d2r_sources() -> Sources:
    if "d2r" not in _CACHE:
        _CACHE["d2r"] = Sources.d2r()
    return _CACHE["d2r"]


# ---- rim and well ----------------------------------------------------------------------------------------------------
def nine_slice(src: Image.Image, w: int, h: int, c: int) -> Image.Image:
    """src stretched to w x h with its c x c corners kept and its edges stretched only along their length."""
    sw, sh = src.size
    out = Image.new("RGBA", (w, h))
    xs = [(0, c, 0, c), (c, sw - c, c, w - c), (sw - c, sw, w - c, w)]
    ys = [(0, c, 0, c), (c, sh - c, c, h - c), (sh - c, sh, h - c, h)]
    for sx0, sx1, dx0, dx1 in xs:
        for sy0, sy1, dy0, dy1 in ys:
            if dx1 > dx0 and dy1 > dy0:
                out.paste(src.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.BICUBIC), (dx0, dy0))
    return out


def rim_scale(bw: int, bh: int) -> float:
    """1 from a body of 80 px up; smaller bodies a thinner rim, down to 0.8 (the inside must keep room for the icon)."""
    return max(0.8, min(1.0, min(bw, bh) / 80))


def body(src: Sources, bw: int, bh: int, greyed: bool) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """The rim at bw x bh with the inside cut out, and the inside's box (x0, y0, x1, y1 exclusive)."""
    rim = (src.rim_greyed if greyed else src.rim).copy()
    rw, rh = rim.size
    il, it, ir, ib = RIM_INNER
    ImageDraw.Draw(rim).rectangle([il, it, rw - ir - 1, rh - ib - 1], fill=(0, 0, 0, 0))
    s = rim_scale(bw, bh)
    if s < 1:
        rim = rim.resize((round(rw * s), round(rh * s)), Image.LANCZOS)
    c = round(RIM_CORNER * s)
    out = nine_slice(rim, bw, bh, c)
    return out, (round(il * s), round(it * s), bw - round(ir * s), bh - round(ib * s))


def well(src: Sources, w: int, h: int, light: float, greyed: bool) -> Image.Image:
    """The stash cell's dark inside at w x h with an inner shadow on the top and left (recessed)."""
    tex = np.asarray(src.well.resize((w, h), Image.LANCZOS), dtype=np.float32)
    if greyed:
        tex = tex.mean(axis=2, keepdims=True).repeat(3, axis=2) * 0.8
    tex = tex * light
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    edge = np.minimum(xx / max(1.0, w * 0.18), yy / max(1.0, h * 0.18))
    tex *= (0.45 + 0.55 * np.clip(edge, 0, 1))[..., None]
    if not greyed and light > 1:  # hover: a faint warm glow from the middle, as D2R's lit insides
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
        tex += (np.clip(1 - r, 0, 1) ** 1.5 * 50)[..., None] * np.array([1.0, 0.75, 0.4], np.float32)
    return Image.fromarray(np.clip(tex, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


# ---- shading ---------------------------------------------------------------------------------------------------------
def _mask(size: tuple[int, int], draw) -> np.ndarray:
    """A shape drawn by draw(ImageDraw, P) at SS x into an alpha mask at size (0..1). P maps 0..1 icon units to pixels."""
    w, h = size
    m = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(m)
    draw(d, lambda x, y: (x * w * SS, y * h * SS), lambda v: v * min(w, h) * SS)
    return np.asarray(m.resize((w, h), Image.LANCZOS), dtype=np.float32) / 255


def _blur(a: np.ndarray, r: float) -> np.ndarray:
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(r))
    return np.asarray(im, dtype=np.float32) / 255


def _shift(a: np.ndarray, dx: int, dy: int) -> np.ndarray:
    out = np.zeros_like(a)
    h, w = a.shape
    out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = a[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return out


def shaded(mask: np.ndarray, top: tuple, bottom: tuple, bevel: float = 1.6, gloss: float = 0.0) -> np.ndarray:
    """RGBA float (h, w, 4) of a shape lit from the top left: a vertical colour ramp over the shape's box, its edges
    raised (a blurred height map: lit on the top-left slopes, dark on the bottom-right ones), gloss = a soft highlight."""
    h, w = mask.shape
    ys = np.nonzero(mask.max(axis=1) > 0.05)[0]
    y0, y1 = (ys[0], ys[-1]) if len(ys) else (0, h - 1)
    t = np.clip((np.arange(h, dtype=np.float32) - y0) / max(1, y1 - y0), 0, 1)[:, None, None]
    col = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    col = np.broadcast_to(col, (h, w, 3)).copy()
    hm = _blur(mask, bevel)
    slope = _shift(hm, 1, 1) - _shift(hm, -1, -1)  # > 0 where the height rises towards the top left
    col *= (1 + 1.6 * slope)[..., None]
    if gloss:
        col += (np.clip(slope, 0, None) ** 0.7 * 255 * gloss)[..., None]
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = np.clip(col, 0, 255)
    out[..., 3] = mask
    return out


def flat(mask: np.ndarray, rgb: tuple) -> np.ndarray:
    out = np.zeros(mask.shape + (4,), np.float32)
    out[..., :3] = rgb
    out[..., 3] = mask
    return out


def over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """src over dst, both RGBA float with alpha 0..1 (straight colour)."""
    a, b = src[..., 3:4], dst[..., 3:4]
    out_a = a + b * (1 - a)
    rgb = (src[..., :3] * a + dst[..., :3] * b * (1 - a)) / np.maximum(out_a, 1e-6)
    return np.concatenate([rgb, out_a], axis=2)


def outline(mask: np.ndarray, width: int = 1) -> np.ndarray:
    """The shape grown by width pixels (a dark rim drawn under the shape)."""
    m = Image.fromarray(np.clip(mask * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(2 * width + 1))
    return np.asarray(m, dtype=np.float32) / 255


GOLD = ((255, 230, 150), (150, 98, 36))
GOLD_DARK = ((205, 160, 80), (110, 70, 26))
WOOD = ((132, 80, 44), (72, 40, 20))
INK = (22, 13, 6)


# ---- icons -----------------------------------------------------------------------------------------------------------
def chest_icon(size: tuple[int, int]) -> np.ndarray:
    """An arrow going down into an open chest: the lid standing open behind, the arrow's head going into the chest."""
    def lid(d, P, L):
        d.ellipse([P(0.12, 0.14), P(0.88, 0.42)], fill=255)
        d.rectangle([P(0.12, 0.28), P(0.88, 0.58)], fill=255)

    def lid_inside(d, P, L):
        d.ellipse([P(0.18, 0.20), P(0.82, 0.42)], fill=255)
        d.rectangle([P(0.18, 0.31), P(0.82, 0.58)], fill=255)

    def mouth(d, P, L):
        d.polygon([P(0.12, 0.53), P(0.88, 0.53), P(0.90, 0.61), P(0.10, 0.61)], fill=255)

    def arrow(d, P, L):
        d.rectangle([P(0.405, 0.0), P(0.595, 0.40)], fill=255)
        d.polygon([P(0.21, 0.36), P(0.79, 0.36), P(0.50, 0.71)], fill=255)

    def front(d, P, L):
        d.rectangle([P(0.08, 0.59), P(0.92, 0.97)], fill=255)

    def bands(d, P, L):
        d.rectangle([P(0.08, 0.59), P(0.92, 0.655)], fill=255)        # the rim of the front
        d.rectangle([P(0.08, 0.59), P(0.18, 0.97)], fill=255)         # corner straps
        d.rectangle([P(0.82, 0.59), P(0.92, 0.97)], fill=255)
        d.rectangle([P(0.08, 0.905), P(0.92, 0.97)], fill=255)        # foot band
        d.rounded_rectangle([P(0.39, 0.63), P(0.61, 0.84)], radius=L(0.03), fill=255)  # lock plate

    def keyhole(d, P, L):
        d.ellipse([P(0.465, 0.68), P(0.535, 0.75)], fill=255)
        d.polygon([P(0.48, 0.72), P(0.52, 0.72), P(0.535, 0.80), P(0.465, 0.80)], fill=255)

    def planks(d, P, L):
        for y in (0.745, 0.825):
            d.line([P(0.18, y), P(0.39, y)], fill=255, width=max(1, round(L(0.014))))
            d.line([P(0.61, y), P(0.82, y)], fill=255, width=max(1, round(L(0.014))))

    m = {k: _mask(size, f) for k, f in (("lid", lid), ("lid_inside", lid_inside), ("mouth", mouth), ("arrow", arrow),
                                       ("front", front), ("bands", bands), ("keyhole", keyhole), ("planks", planks))}
    h, w = m["front"].shape
    ow = max(1, round(min(size) / 36))
    img = np.zeros((h, w, 4), np.float32)
    # the open lid (gold rim, its dark wooden inside) and the dark mouth of the chest
    img = over(img, flat(outline(np.maximum(m["lid"], m["mouth"]), ow), INK))
    img = over(img, shaded(m["lid"], *GOLD_DARK, bevel=1.0, gloss=0.15))
    img = over(img, shaded(m["lid_inside"], (70, 42, 22), (40, 22, 10), bevel=1.4))
    img = over(img, flat(m["mouth"], (12, 8, 5)))
    # the arrow, then the chest's front over its tip
    img = over(img, flat(outline(m["arrow"], ow), INK))
    img = over(img, shaded(m["arrow"], *GOLD, bevel=1.8, gloss=0.35))
    img = over(img, flat(outline(m["front"], ow), INK))
    img = over(img, shaded(m["front"], *WOOD, bevel=1.0))
    img = over(img, flat(m["planks"] * 0.8, (40, 22, 10)))
    img = over(img, flat(outline(m["bands"], 1) * m["front"], (40, 26, 12)))
    img = over(img, shaded(m["bands"], *GOLD_DARK, bevel=1.2, gloss=0.2))
    img = over(img, flat(m["keyhole"], (18, 10, 4)))
    return img


def charm_icon(size: tuple[int, int]) -> np.ndarray:
    """A charm: a blue stone in a gold oval setting, hung on a gold ring."""
    def ring(d, P, L):
        d.ellipse([P(0.39, 0.03), P(0.61, 0.25)], outline=255, width=max(1, round(L(0.055))))

    def bail(d, P, L):
        d.polygon([P(0.43, 0.20), P(0.57, 0.20), P(0.60, 0.30), P(0.40, 0.30)], fill=255)

    def setting(d, P, L):
        d.ellipse([P(0.20, 0.25), P(0.80, 0.97)], fill=255)

    def stone(d, P, L):
        d.ellipse([P(0.28, 0.335), P(0.72, 0.885)], fill=255)

    def shine(d, P, L):
        d.ellipse([P(0.36, 0.40), P(0.50, 0.53)], fill=255)

    m = {k: _mask(size, f) for k, f in (("ring", ring), ("bail", bail), ("setting", setting), ("stone", stone), ("shine", shine))}
    h, w = m["setting"].shape
    img = np.zeros((h, w, 4), np.float32)
    metal = np.maximum(np.maximum(m["ring"], m["bail"]), m["setting"])
    img = over(img, flat(outline(metal, 1), INK))
    img = over(img, shaded(m["ring"], *GOLD, bevel=0.8, gloss=0.3))
    img = over(img, shaded(np.maximum(m["bail"], m["setting"]), *GOLD, bevel=1.6, gloss=0.35))
    img = over(img, flat(outline(m["stone"], 1) * m["setting"], (60, 36, 12)))
    # the stone: deep blue, lighter towards its lower right (light through the stone), a white glint top left
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cy, cx = 0.66 * h, 0.56 * w
    r = np.clip(np.hypot((xx - cx) / (0.30 * w), (yy - cy) / (0.36 * h)), 0, 1)[..., None]
    blue = np.array([96, 168, 255], np.float32) * (1 - r) + np.array([14, 30, 96], np.float32) * r
    gem = shaded(m["stone"], (255, 255, 255), (255, 255, 255), bevel=2.2)
    gem[..., :3] = np.clip(blue * gem[..., :3] / 255, 0, 255)
    img = over(img, gem)
    sh = _blur(m["shine"], 0.6)
    img = over(img, flat(sh * 0.85, (235, 245, 255)))
    return img


ICONS = {"sendstash": chest_icon, "charms": charm_icon}


# ---- the button ------------------------------------------------------------------------------------------------------
def _icon_state(icon: np.ndarray, kind: str) -> np.ndarray:
    out = icon.copy()
    if kind == "hovered":
        out[..., :3] = np.clip(out[..., :3] * 1.18 + 10, 0, 255)
    elif kind == "pressed":
        out[..., :3] *= 0.82
    elif kind == "greyed":
        grey = out[..., :3] @ np.array([0.30, 0.59, 0.11], np.float32)
        out[..., :3] = (grey * 0.55 + 18)[..., None]
    return out


def button(icon: str, w: int, h: int, kind: str, src: Sources | None = None) -> Image.Image:
    """One state of a w x h button (the sprite frame: body, drop shadow and transparent margin)."""
    if kind not in KINDS:
        raise ValueError(f"state {kind!r}: one of {KINDS}")
    src = src or d2r_sources()
    pad_r, pad_b = max(3, round(w * 0.05)), max(4, round(h * 0.07))  # room for the drop shadow
    bw, bh = w - 1 - pad_r, h - 1 - pad_b
    pressed = kind == "pressed"
    ox, oy = (2, 2) if pressed else (1, 1)
    rim, (ix0, iy0, ix1, iy1) = body(src, bw, bh, kind == "greyed")
    light = {"normal": 1.0, "hovered": 1.35, "pressed": 0.8, "greyed": 0.9}[kind]
    inside = well(src, ix1 - ix0, iy1 - iy0, light, kind == "greyed")
    face = Image.new("RGBA", (bw, bh))
    face.paste(inside, (ix0, iy0))
    # the icon in the inside, a margin of a tenth around it, its own drop shadow
    m = max(2, round(min(ix1 - ix0, iy1 - iy0) * 0.06))
    iw, ih = ix1 - ix0 - 2 * m, iy1 - iy0 - 2 * m
    side = min(iw, ih)
    ic = _icon_state(ICONS[icon]((side, side)), kind)
    ic_img = Image.fromarray(np.dstack([ic[..., :3], ic[..., 3:] * 255]).clip(0, 255).astype(np.uint8), "RGBA")
    shadow = Image.new("RGBA", ic_img.size, (0, 0, 0, 0))
    shadow.putalpha(ic_img.getchannel("A").point(lambda v: v * 150 // 255).filter(ImageFilter.GaussianBlur(1.2)))
    px, py = ix0 + m + (iw - side) // 2 + (1 if pressed else 0), iy0 + m + (ih - side) // 2 + (1 if pressed else 0)
    face.alpha_composite(shadow, (px + 2, py + 2))
    face.alpha_composite(ic_img, (px, py))
    face.alpha_composite(rim)
    # the drop shadow of the body (D2R's buttons carry a soft one to the bottom right)
    out = Image.new("RGBA", (w, h))
    sa = Image.new("L", (w, h), 0)
    sa.paste(255, (ox + (1 if pressed else 3), oy + (1 if pressed else 4), ox + bw + (1 if pressed else 3), oy + bh + (1 if pressed else 4)))
    sa = sa.filter(ImageFilter.GaussianBlur(2.0 if pressed else 3.0)).point(lambda v: v * 170 // 255)
    out.putalpha(sa)
    out.alpha_composite(face, (ox, oy))
    return out


def frames(icon: str, w: int, h: int, order: tuple[str, ...], src: Sources | None = None) -> list[Image.Image]:
    return [button(icon, w, h, k, src) for k in order]


def lowend(frames_: list[Image.Image]) -> list[Image.Image]:
    """The .lowend half (D2R's low texture quality)."""
    return [f.resize((f.width // 2, f.height // 2), Image.LANCZOS) for f in frames_]


# ---- preview ---------------------------------------------------------------------------------------------------------
def preview(out_dir: Path) -> list[Path]:
    """Both buttons, every state, at 1x (top) and 3x (below), over a stone patch of D2R's HD inventory picture."""
    import fxpaths
    import send_stash
    import ui_art
    import invtabs_hdart
    stone = ui_art.read_sprite(fxpaths.d2r_file("data/hd/global/ui/panel/inventory/background.sprite"))[0].convert("RGBA")
    sets = [frames("sendstash", *send_stash.HD_RECT[2:], KINDS), frames("charms", invtabs_hdart.BUTTON, invtabs_hdart.BUTTON, KINDS)]
    out = []
    for scale in (1, 3):
        cw = sum(f.width * scale + 16 for f in sets[0])
        ch = sum(fs[0].height * scale + 16 for fs in sets)
        sheet = stone.crop((40, 1300, 40 + cw, 1300 + ch)).resize((cw, ch)) if scale == 1 else Image.new("RGBA", (cw, ch), (40, 38, 36, 255))
        y = 8
        for fs in sets:
            x = 8
            for f in fs:
                g = f.resize((f.width * scale, f.height * scale), Image.NEAREST)
                sheet.alpha_composite(g, (x, y))
                x += g.width + 16
            y += fs[0].height * scale + 16
        p = Path(out_dir) / f"hd_buttons_x{scale}.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        sheet.convert("RGB").save(p)
        out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "preview" and len(argv) <= 2:
        out = Path(argv[1]) if len(argv) == 2 else ROOT / "work" / "hd_buttons"
        for p in preview(out):
            print(p)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
