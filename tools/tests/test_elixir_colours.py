import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401
import elixir_colours as ec  # noqa: E402
import median_tabs  # noqa: E402


class ElixirColoursTests(unittest.TestCase):
    def test_kinds_are_the_stash_elixirs_with_distinct_pictures(self):
        self.assertEqual(set(ec.CODES), set(median_tabs.ELIXIRS) - {'b@b'})
        self.assertEqual(len(ec.KINDS), 22)
        self.assertEqual(len({k[3:6] for k in ec.KINDS}), 22)
        self.assertEqual(len({k[2] for k in ec.KINDS}), 22)

    def test_tables_change_only_the_picture_in_both_banks_and_are_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            rows = [dict(code=k[0], invfile='invxyz', Transform='0', InvTrans='0', spelldescstr='kept') for k in ec.KINDS]
            rows += [dict(rows[0], code='xyz'), dict(rows[0], code='ice')]
            for bank in ('', 'base'):
                path = data / 'global/excel' / bank / 'misc.txt'
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open('w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, rows[0].keys(), delimiter='\t')
                    writer.writeheader()
                    writer.writerows(rows)
            ec.tables(data)
            before = path.read_bytes()
            ec.tables(data)
            self.assertEqual(before, path.read_bytes())
            for bank in ('', 'base'):
                with (data / 'global/excel' / bank / 'misc.txt').open(encoding='utf-8') as f:
                    changed = list(csv.DictReader(f, delimiter='\t'))
                for old, new in zip(rows, changed):
                    i = ec.CODES.get(old['code'])
                    self.assertEqual(new, dict(old, invfile='invxyz' if i is None else f'mxlelixir{i:02d}'))

    def test_tables_refuse_an_unknown_picture(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            path = data / 'global/excel/misc.txt'
            path.parent.mkdir(parents=True)
            path.write_text('code\tinvfile\neo7\tother\n', encoding='utf-8')
            with self.assertRaises(ValueError):
                ec.tables(data)

    def test_tint_keeps_light_and_dark_and_poison_stays_as_it_was(self):
        poison = next(k for k in ec.KINDS if k[0] == 'ey1')
        self.assertEqual(ec.tint((24, 100, 8), poison), (24, 100, 8))
        fire = next(k for k in ec.KINDS if k[0] == 'eo7')
        dark, light = ec.tint((10, 50, 5), fire), ec.tint((40, 200, 20), fire)
        self.assertGreater(dark[0], dark[1])
        self.assertLess(sum(dark), sum(light))

    def test_palette_map_moves_only_liquid_colours(self):
        pal = [(i, i, i) for i in range(256)]
        pal[10], pal[20], pal[30], pal[40] = (24, 100, 8), (200, 150, 60), (250, 40, 20), (9, 30, 30)
        mapping = ec.palette_map(pal, [10, 20, 40], next(k for k in ec.KINDS if k[0] == 'eo7'))
        self.assertNotEqual(mapping[10], 10)
        self.assertEqual(mapping[20], 20)  # the frame
        self.assertEqual(mapping[40], 40)
        self.assertEqual(mapping[30], 30)  # not used in the picture
        self.assertEqual(mapping[0], 0)

    def test_art_writes_every_format_and_only_recolours_the_liquid(self):
        import dc6
        import fxpaths
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pal = [(i, i, i) for i in range(256)]
            pal[10], pal[20] = (24, 100, 8), (200, 150, 60)
            frame = (2, 1, 3, 4, bytes([2, 10, 20, 128]))
            legacy = root / 'invxyz.dc6'
            legacy.write_bytes(dc6.build_dc6([frame]))
            pixels = bytes([24, 100, 8, 255, 200, 150, 60, 128, 0, 0, 0, 0])
            sources = {}
            for ext in ('.sprite', '.lowend.sprite'):
                sources[ext] = root / ('src' + ext)
                dc6.write_item_sprite(sources[ext], 3, 1, pixels)

            def source(rel):
                if rel.endswith('.dc6'):
                    return legacy
                return sources['.lowend.sprite' if rel.endswith('.lowend.sprite') else '.sprite']
            old = 'quest/scroll_of_self_resurrect'
            entries = [{k[0]: {'asset': old}} for k in ec.KINDS] + [{'xyz': {'asset': old}}]
            maps = root / 'hd/items/items.json'
            maps.parent.mkdir(parents=True)
            maps.write_text(json.dumps(entries), encoding='utf-8')
            with patch.object(fxpaths, 'd2r_file', side_effect=source), patch.object(fxpaths, 'palette', return_value=pal):
                ec.art(root)
            result = json.loads(maps.read_text(encoding='utf-8'))
            self.assertEqual(result[-1], entries[-1])
            for i, kind in enumerate(ec.KINDS):
                self.assertEqual(result[i][kind[0]]['asset'], f'mxl/elixir{i:02d}')
                for ext in ('.sprite', '.lowend.sprite'):
                    rgba = (root / (f'hd/global/ui/items/misc/mxl/elixir{i:02d}' + ext)).read_bytes()[40:]
                    self.assertEqual(rgba[3::4], pixels[3::4])
                    self.assertEqual(rgba[4:8], pixels[4:8])
                    self.assertEqual(rgba[:3], bytes(ec.tint((24, 100, 8), kind)))
                out = dc6.read_dc6(root / f'global/items/mxlelixir{i:02d}.dc6')[0]
                self.assertEqual(out[:4], frame[:4])
                self.assertEqual(out[4][2], 20)
                self.assertEqual(out[4][1], ec.palette_map(pal, [10, 20], kind)[10])


if __name__ == '__main__':
    unittest.main()
