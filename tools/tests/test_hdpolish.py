"""Unit tests of lane hdpolish's changes on synthetic data (no game files): the skill icon sheets and the HD panels on the
pixel-art upscaler, and the classic remap of palette indices 225-254 by neighbour fill.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_hdpolish.py" """
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import dc6  # noqa: E402
import legacy_art as la  # noqa: E402
import skill_icons  # noqa: E402
import ui_panels  # noqa: E402
import upscale  # noqa: E402
from test_icons import block  # noqa: E402

# units-like palette: 1-224 a red ramp with a few distinct colours, 225-254 black (as D2R's units palette)
UNITS = [(0, 0, 0)] + [(i, 0, 0) for i in range(1, 225)] + [(0, 0, 0)] * 30 + [(255, 255, 255)]
UNITS[40] = (0, 200, 0)      # green
UNITS[50] = (0, 0, 200)      # blue
UNITS[60] = (0, 100, 100)    # the green-blue mean


class SkillSheetScaleTests(unittest.TestCase):
    def test_skill_icons_use_the_pixel_art_upscaler(self):
        self.assertIs(skill_icons.scale, upscale.scale_rows)

    def test_scale_rows_size_centring_and_format(self):
        rows = [[(200, 10, 10, 255)] * 6 for _ in range(4)]
        out = upscale.scale_rows(rows, 20, 20, 2.5)
        self.assertEqual((len(out), len(out[0])), (20, 20))
        self.assertIsInstance(out[0][0], tuple)
        self.assertEqual(out[0][0], (0, 0, 0, 0))         # 15 x 10 picture centred: the top rows stay empty
        self.assertEqual(out[10][10][3], 255)
        self.assertEqual(upscale.scale_rows([], 5, 3, 2.0), [[(0, 0, 0, 0)] * 5] * 3)

    def test_scale_rows_keeps_a_hard_edge_sharper_than_bilinear(self):
        rows = [[(255, 255, 255, 255) if x < 4 else (0, 0, 0, 255) for x in range(8)] for _ in range(8)]
        new = upscale.rows_to_array(upscale.scale_rows(rows, 22, 22, 22 / 8))
        old = upscale.rows_to_array(dc6.scale(rows, 22, 22, 22 / 8))
        grey = lambda a: int(((a[8:14, :, 0] > 40) & (a[8:14, :, 0] < 215)).sum())  # noqa: E731
        self.assertLess(grey(new), grey(old))

    def test_sheet_layout_unchanged(self):
        """The frame count, stride and icon size of a sheet do not depend on the scaler."""
        self.assertEqual(skill_icons.strip_geometry(118), (132, 130))


class PanelScaleTests(unittest.TestCase):
    def test_hybrid_panel_size_and_old_method(self):
        a = np.zeros((12, 10, 4), np.uint8)
        a[..., 3] = 255
        a[:, 5:, :3] = 200
        im = Image.fromarray(a, "RGBA")
        new, old = ui_panels.scale_panel(im, 36, 44), ui_panels.scale_panel(im, 36, 44, method="lanczos")
        self.assertEqual(new.size, (36, 44))
        self.assertEqual(old.size, (36, 44))
        self.assertEqual(new.mode, "RGBA")


class LegacyFillTests(unittest.TestCase):
    def frame(self, lines):
        return dc6.build_dc6([(len(lines[0]), len(lines), 0, 0, block(lines))])

    def test_hazard_takes_the_neighbours_colour_not_black(self):
        data = self.frame([[40, 40, 40], [40, 230, 40], [40, 40, 40]])
        m = la.nearest_map(UNITS)
        self.assertEqual(UNITS[m[230]], (1, 0, 0))     # the old remap: nearest to black
        out = la.remap_dc6(data, m, UNITS)
        self.assertEqual(len(out), len(data))
        (w, h, _x, _y, blk), = dc6.parse_dc6(out)
        self.assertEqual(list(blk), list(block([[40, 40, 40], [40, 40, 40], [40, 40, 40]])))

    def test_mean_of_mixed_neighbours_and_clusters(self):
        # bottom-up lines: the left half green, the right half blue, a 2-pixel hazard cluster in the middle
        data = self.frame([[40, 40, 50, 50], [40, 231, 232, 50], [40, 40, 50, 50]])
        out = la.remap_dc6(data, la.nearest_map(UNITS), UNITS)
        idx = [c for c in dc6.parse_dc6(out)[0][4] if c < 0x80 and c != 4]  # literal bytes (run length 4 skipped)
        self.assertNotIn(231, idx)
        self.assertNotIn(232, idx)
        self.assertIn(60, idx)                           # a pixel between green and blue -> the green-blue colour

    def test_isolated_hazard_falls_back_to_the_map(self):
        data = self.frame([[None, None, None], [None, 240, None]])
        m = la.nearest_map(UNITS)
        out = la.remap_dc6(data, m, UNITS)
        self.assertIn(m[240], dc6.parse_dc6(out)[0][4])
        self.assertEqual(la.remap_dc6(data, m), out)     # without a palette: the plain map, as before

    def test_copy_plan_passes_the_palette(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            src = t / "med" / "global" / "items" / "invpink.dc6"
            src.parent.mkdir(parents=True)
            src.write_bytes(self.frame([[40, 40], [40, 230]]))
            e = la.Entry(rel="global/items/invpink.dc6", kind="item", action="copy", why="", src=src, size=0, pink=1)
            plan = la.Plan(entries=[e])
            la.copy_plan(plan, t / "out", la.nearest_map(UNITS), UNITS)
            got = dc6.parse_dc6((t / "out" / e.rel).read_bytes())[0][4]
            self.assertEqual(sorted(c for c in got if c < 0x80 and c != 2), [40, 40, 40, 40])


if __name__ == "__main__":
    unittest.main()
