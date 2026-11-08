import csv
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp
import tempfile
import shrine_colours as sc


class ShrineColoursTests(unittest.TestCase):
    def test_all_charges_banks_idempotent_and_only_picture_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            rows = [dict(code=f'{chr(65+i)}{charge}+', invfile='jbscross', Transform='0', InvTrans='0',
                         name=f'{sc.NAMES[i]} Shrine ({10-charge} Charges)', flippyfile='flpjbi', spelldescstr='unchanged')
                    for i in range(20) for charge in range(10)]
            rows.append(dict(rows[0], code='foo', invfile='other'))
            for bank in ('', 'base'):
                path = data / 'global/excel' / bank / 'misc.txt'
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, rows[0].keys(), delimiter='\t')
                    writer.writeheader(); writer.writerows(rows)
            sc.tables(data)
            before = path.read_bytes()
            sc.tables(data)
            self.assertEqual(before, path.read_bytes())
            for bank in ('', 'base'):
                with (data / 'global/excel' / bank / 'misc.txt').open(encoding='utf-8') as f:
                    changed = list(csv.DictReader(f, delimiter='\t'))
                for old, new in zip(rows, changed):
                    i = sc.shrine_index(old['code'])
                    self.assertEqual(new, dict(old, invfile=old['invfile'] if i is None else f'mxlshrine{i:02d}'))
            self.assertEqual(len(set(c for _, c in sc.COLOURS)), 20)
            self.assertNotIn(3, [c for _, c in sc.COLOURS])  # black is unreadable

    def test_dc6_remap_preserves_run_and_transparency_bytes(self):
        mapping = bytes(reversed(range(256)))
        block = bytes([0x82, 3, 0, 128, 255, 0x80])
        self.assertEqual(sc.recolour_block(block, mapping), bytes([0x82, 3, 255, 127, 0, 0x80]))

    def test_code_boundaries(self):
        for code in ('', 'A+', 'A0', 'a0+', 'U0+', 'A:+', 'AA+', 'A00+'):
            self.assertIsNone(sc.shrine_index(code))
        self.assertEqual(sc.shrine_index('A9+'), 0)
        self.assertEqual(sc.shrine_index('T0+'), 19)

    def test_hd_lowend_mapping_alpha_geometry_and_legacy_pixels(self):
        import dc6
        import fxpaths
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'items').mkdir()
            (root / 'items/jbscross.dc6').write_bytes(dc6.build_dc6([(2, 1, 3, 4, bytes([2, 10, 20, 128]))]))
            transform = root / 'grey.dat'
            transform.write_bytes(bytes((i+c) % 256 for c in range(21) for i in range(256)))
            entries = [{f'{chr(65+i)}{n}+': {'asset': 'mxl/jbscross'}} for i in range(20) for n in range(10)]
            entries.append({'foo': {'asset': 'unrelated'}})
            maps = root / 'hd/items/items.json'
            maps.parent.mkdir(parents=True)
            maps.write_text(json.dumps(entries))
            pixels = bytes([10, 10, 10, 255, 20, 20, 20, 128, 0, 0, 0, 0])
            for ext in ('.sprite', '.lowend.sprite'):
                dc6.write_item_sprite(root / ('hd/global/ui/items/misc/mxl/jbscross'+ext), 3, 1, pixels)
            with patch.object(fxpaths, 'MXL', root), patch.object(fxpaths, 'd2r_file', return_value=transform), \
                 patch.object(fxpaths, 'palette', return_value=[(i, i, i) for i in range(256)]):
                sc.art(root)
            result = json.loads(maps.read_text())
            self.assertEqual(result[-1], entries[-1])
            for i, (_, c) in enumerate(sc.COLOURS):
                for n in range(10):
                    self.assertEqual(result[i*10+n][f'{chr(65+i)}{n}+']['asset'], f'mxl/shrine{i:02d}')
                for ext in ('.sprite', '.lowend.sprite'):
                    sprite = root / (f'hd/global/ui/items/misc/mxl/shrine{i:02d}'+ext)
                    self.assertEqual(len(dc6.read_sprite(sprite)[0][0]), 3)
                    rgba = sprite.read_bytes()[40:]
                    self.assertEqual(rgba[3::4], pixels[3::4])
                    self.assertEqual(rgba[:3], bytes([10+c]*3))
                    self.assertEqual(rgba[-4:], bytes(4))
                frame = dc6.read_dc6(root / f'global/items/mxlshrine{i:02d}.dc6')[0]
                self.assertEqual(frame[:4], (2, 1, 3, 4))
                self.assertEqual(frame[4], bytes([2, 10+c, 20+c, 128]))


if __name__ == '__main__':
    unittest.main()
