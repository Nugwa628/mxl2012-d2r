"""Bake one liquid colour per elixir kind into the shared flask picture, for existing saves as well.

Only the green liquid changes: glass, cork and frame stay, so every kind still reads as an elixir. Normal misc items have
no affix colour, so Transform / InvTrans cannot do this in HD (see shrine_colours.py). Goodberry has its own picture.
Run tables after migration; art after hd_icons and legacy_art (tools/build.py).
"""
import colorsys
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

# code, shown name, colour name, hue in degrees, saturation factor, brightness factor.
# A "Greater" elixir takes a brighter neighbour of its plain kind's hue, so a pair reads as a pair.
KINDS = [('eo7', 'Fire', 'Red-orange', 8, 1.0, 1.2),
         ('eo8', 'Cold', 'Ice blue', 196, 0.75, 1.25),
         ('eo9', 'Lightning', 'Yellow', 56, 1.0, 1.3),
         ('ey1', 'Poison', 'Green (unchanged)', None, 1.0, 1.0),
         ('ey2', 'Experience', 'Violet', 272, 1.0, 1.1),
         ('ey3', 'Greed', 'Magenta', 312, 1.0, 1.1),
         ('ey4', 'Wealth', 'Gold', 48, 1.0, 1.1),
         ('ey5', 'Strength', 'Crimson', 350, 1.0, 0.9),
         ('ey6', 'Dexterity', 'Teal', 170, 1.0, 0.95),
         ('ey7', 'Energy', 'Deep blue', 226, 1.0, 1.1),
         ('ey8', 'Vitality', 'Orange', 30, 1.0, 1.3),
         ('ey9', 'Adrenaline', 'Hot pink', 332, 0.8, 1.3),
         ('et1', 'Concentration', 'Grey-blue', 212, 0.35, 1.05),
         ('0g7', 'Power', 'White', 0, 0.0, 1.6),
         ('0g8', 'Love', 'Pink', 320, 0.55, 1.5),
         ('0g0', 'Greater Experience', 'Blue-violet', 250, 0.8, 1.45),
         ('0g1', 'Greater Greed', 'Bright purple', 295, 0.75, 1.4),
         ('0g2', 'Greater Wealth', 'Pale gold', 48, 0.5, 1.6),
         ('0g3', 'Greater Strength', 'Bright red', 358, 0.85, 1.5),
         ('0g4', 'Greater Dexterity', 'Mint', 152, 0.6, 1.5),
         ('0g5', 'Greater Energy', 'Sky blue', 208, 0.8, 1.5),
         ('0g6', 'Greater Vitality', 'Peach', 22, 0.5, 1.6)]
CODES = {k[0]: i for i, k in enumerate(KINDS)}
SHARED = 'invxyz'


def is_liquid(r, g, b):
    return g > 20 and g > 1.15 * r and g > 1.25 * b


def tint(rgb, kind):
    """The liquid colour `rgb` in `kind`'s colour, its light and dark kept."""
    _, _, _, hue, sat, val = kind
    if hue is None:
        return tuple(rgb)
    _, s, v = colorsys.rgb_to_hsv(*(c / 255.0 for c in rgb))
    out = colorsys.hsv_to_rgb(hue / 360.0, min(s * sat, 1.0), min(v * val, 1.0))
    return tuple(round(c * 255) for c in out)


def palette_map(pal, used, kind):
    """256-byte DC6 remap: each liquid colour in `used` to the palette entry closest to its tinted colour."""
    mapping = bytearray(range(256))
    for i in used:
        if is_liquid(*pal[i]):
            want = tint(pal[i], kind)
            mapping[i] = min(range(1, 256), key=lambda p: sum((a - b) ** 2 for a, b in zip(pal[p], want)))
    return bytes(mapping)


def recolour_rgba(image, kind):
    """A copy of the RGBA array with its liquid pixels tinted; alpha and every other pixel unchanged."""
    import numpy as np
    out = image.copy()
    r, g, b = (image[:, :, c].astype(np.int32) for c in range(3))
    mask = (image[:, :, 3] > 0) & (g > 20) & (100 * g > 115 * r) & (100 * g > 125 * b)
    cache = {}
    for y, x in zip(*np.nonzero(mask)):
        key = tuple(int(c) for c in image[y, x, :3])
        out[y, x, :3] = cache.setdefault(key, tint(key, kind))
    return out


def tables(data):
    for bank in ('', 'base'):
        path = data / 'global/excel' / bank / 'misc.txt'
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f, delimiter='\t')
            fields, rows = reader.fieldnames, list(reader)
        seen = set()
        for r in rows:
            index = CODES.get(r.get('code', ''))
            if index is not None:
                if r['invfile'] not in (SHARED, f'mxlelixir{index:02d}'):
                    raise ValueError(f"unexpected elixir picture: {r['code']}")
                r['invfile'] = f'mxlelixir{index:02d}'
                seen.add(r['code'])
        if len(seen) != len(KINDS):
            raise ValueError(f'{path}: expected {len(KINDS)} elixir codes, got {len(seen)}')
        with path.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fields, delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(f'{path}: {len(seen)} elixir pictures')


def art(data):
    import dc6
    import fxpaths
    from shrine_colours import recolour_block
    from upscale import rows_to_array
    frames = dc6.read_dc6(fxpaths.d2r_file('data/global/items/invxyz.dc6'))
    pal = fxpaths.palette()
    raw = rows_to_array(dc6.decode_frame(frames[0][0], frames[0][1], frames[0][4], pal))
    used = sorted({pal.index(tuple(int(c) for c in p[:3])) for p in raw.reshape(-1, 4) if p[3]})
    sprites = {ext: rows_to_array(dc6.read_sprite(fxpaths.d2r_file('data/hd/global/ui/items/misc/quest/scroll_of_self_resurrect' + ext))[0])
               for ext in ('.sprite', '.lowend.sprite')}
    maps_path = data / 'hd/items/items.json'
    entries = json.loads(maps_path.read_text('utf-8'))
    for index, kind in enumerate(KINDS):
        mapping = palette_map(pal, used, kind)
        dest = data / f'global/items/mxlelixir{index:02d}.dc6'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dc6.build_dc6([(w, h, x, y, recolour_block(b, mapping)) for w, h, x, y, b in frames]))
        asset = f'mxl/elixir{index:02d}'
        for ext, image in sprites.items():
            out = recolour_rgba(image, kind)
            dc6.write_item_sprite(data / ('hd/global/ui/items/misc/' + asset + ext), out.shape[1], out.shape[0], out.tobytes())
        found = 0
        for entry in entries:
            if kind[0] in entry:
                entry[kind[0]]['asset'] = asset
                found += 1
        if found != 1:
            raise ValueError(f'hd/items/items.json: {found} entries for {kind[0]}')
        print(f'{kind[1]}: {kind[2]}')
    maps_path.write_text(json.dumps(entries, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    {'tables': tables, 'art': art}[sys.argv[1]](Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'work/mod/data')
