"""Bake D2's grey.dat colour transforms into shrine pictures, including existing saves.

Transform/InvTrans select a palette family (0..8), NOT a colour. Normal misc
items have no affix colour, so setting those cells alone cannot colour shrines.
No affixes are added: only invfile changes, in both banks. Ground art stays intact.
Run tables after migration; art after hd_icons and legacy_art (tools/build.py).
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))

NAMES = 'Creepy Abandoned Quiet Eerie Weird Gloomy Tainted Fascinating Ornate Sacred Shimmering Mysterious Spiritual Magical Enchanted Divine Hidden Stone Religious Cryptic'.split()
# Every D2 colour except black, which disappears on the stash background.
COLOURS = [('Dark Red', 8), ('Light Grey', 1), ('Light Blue', 4), ('Dark Purple', 18),
           ('Crystal Red', 9), ('Dark Blue', 5), ('Dark Green', 11), ('Orange', 19),
           ('Light Gold', 15), ('Crystal Blue', 6), ('White', 0), ('Light Purple', 17),
           ('Light Green', 10), ('Crystal Green', 12), ('Light Yellow', 13), ('Bright White', 20),
           ('Light Red', 7), ('Dark Grey', 2), ('Dark Gold', 16), ('Dark Yellow', 14)]


def shrine_index(code):
    return ord(code[0]) - 65 if len(code) == 3 and code[0] in 'ABCDEFGHIJKLMNOPQRST' and code[1] in '0123456789' and code[2] == '+' else None


def recolour_block(block, mapping):
    """Remap only DC6 pixel runs, preserving transparency and scanline markers."""
    out = bytearray(block)
    i = 0
    while i < len(out):
        count = out[i]
        i += 1
        if count < 128:
            out[i:i + count] = bytes(mapping[x] for x in out[i:i + count])
            i += count
    return bytes(out)


def tables(data):
    for bank in ('', 'base'):
        path = data / 'global/excel' / bank / 'misc.txt'
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f, delimiter='\t')
            fields, rows = reader.fieldnames, list(reader)
        seen = set()
        for r in rows:
            index = shrine_index(r.get('code', ''))
            if index is not None:
                if r['invfile'] not in ('jbscross', f'mxlshrine{index:02d}'):
                    raise ValueError(f"unexpected shrine picture: {r['code']}")
                r['invfile'] = f'mxlshrine{index:02d}'
                seen.add(r['code'])
        if len(seen) != 200:
            raise ValueError(f'{path}: expected 200 shrine charge codes, got {len(seen)}')
        with path.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fields, delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        print(f'{path}: 200 shrine pictures')


def art(data):
    import dc6
    import fxpaths
    import numpy as np
    from upscale import rows_to_array
    source = fxpaths.MXL / 'items/jbscross.dc6'
    frames = dc6.read_dc6(source)
    transforms = fxpaths.d2r_file('data/global/items/palette/grey.dat').read_bytes()
    if len(transforms) != 21 * 256:
        raise ValueError('grey.dat: expected 21 colour transforms')
    pal = fxpaths.palette()
    w, h, _, _, block = frames[0]
    raw = rows_to_array(dc6.decode_frame(w, h, block, pal))
    # Only palette colours actually used by the source; avoids unrelated palette
    # ramps winning the nearest-colour match on antialiased HD edge pixels.
    colours = sorted(set(tuple(p[:3]) for p in raw.reshape(-1, 4) if p[3]))
    indices = [pal.index(c) for c in colours]
    maps_path = data / 'hd/items/items.json'
    entries = json.loads(maps_path.read_text('utf-8'))
    for index, (name, colour) in enumerate(COLOURS):
        mapping = transforms[colour * 256:(colour + 1) * 256]
        dest = data / f'global/items/mxlshrine{index:02d}.dc6'
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(dc6.build_dc6([(fw, fh, x, y, recolour_block(b, mapping)) for fw, fh, x, y, b in frames]))
        asset = f'mxl/shrine{index:02d}'
        for ext in ('.sprite', '.lowend.sprite'):
            src = data / ('hd/global/ui/items/misc/mxl/jbscross' + ext)
            image = rows_to_array(dc6.read_sprite(src)[0]).copy()
            rgb = image[:, :, :3].astype(np.int32)
            distance = ((rgb[:, :, None, :] - np.array(colours)[None, None, :, :]) ** 2).sum(axis=3)
            closest = distance.argmin(axis=2)
            mapped = np.array([pal[mapping[i]] for i in indices], dtype=np.uint8)[closest]
            image[:, :, :3] = np.where(image[:, :, 3, None] > 0, mapped, 0)
            dc6.write_item_sprite(data / ('hd/global/ui/items/misc/' + asset + ext), image.shape[1], image.shape[0], image.tobytes())
        for entry in entries:
            for code, value in entry.items():
                if shrine_index(code) == index:
                    value['asset'] = asset
        print(f'{NAMES[index]}: {name} (grey.dat {colour})')
    maps_path.write_text(json.dumps(entries, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    {'tables': tables, 'art': art}[sys.argv[1]](Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'work/mod/data')
