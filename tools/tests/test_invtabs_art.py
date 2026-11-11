"""tools/invtabs_art.py: the classic art of invtabs (a tab's 320 x 432 panel for its grid size, the 24 x 24 tab buttons and
the 32 x 32 inventory button). The nine-slice is pure; the rest needs D2R's and Median's extractions and skips without them
(fxpaths / MXL_D2R_EXTRACT / MXL_EXTRACT).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_invtabs_art.py" """
import argparse
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import dc6  # noqa: E402
import invtabs_art as ia  # noqa: E402
import invtabs_legacy as il  # noqa: E402
import ui_art  # noqa: E402

PANEL_SIZES = [(x1 - x0, y1 - y0) for x0, y0, x1, y1 in ui_art.TILES]


def inputs():
    """(median data, D2R) as the tool resolves them, or None without the extractions."""
    try:
        med, d2r, _out = ia.resolve_inputs(argparse.Namespace(median=None, d2r=None, out=None))
    except (OSError, SystemExit):
        return None
    need = [med / "global" / "ui" / "panel" / "tradestash.dc6", d2r.data / "global" / "items" / "invchm.dc6",
            d2r.data / "global" / "ui" / "panel" / "buysellbtn.dc6"]
    if not all(p.exists() for p in need) or d2r.font(ia.TITLE_FONT) is None:
        return None
    return med, d2r


class NineSlice(unittest.TestCase):
    def test_corners_kept_edges_stretched(self):
        src = Image.new("RGBA", (12, 10), (0, 0, 0, 255))
        for x in range(12):
            src.putpixel((x, 0), (200, 0, 0, 255))
        src.putpixel((0, 0), (0, 255, 0, 255))
        out = ia.nine_slice(src, 50, 30, corner=4)
        self.assertEqual(out.size, (50, 30))
        self.assertEqual(out.getpixel((0, 0)), (0, 255, 0, 255))
        self.assertEqual(out.getpixel((25, 0)), (200, 0, 0, 255))    # the top rim runs the whole width
        self.assertEqual(out.getpixel((25, 15)), (0, 0, 0, 255))
        with self.assertRaises(ValueError):
            ia.nine_slice(src, 8, 30, corner=4)


class Art(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        got = inputs()
        if got is None:
            raise unittest.SkipTest("D2R / Median extractions not found")
        cls.med, cls.d2r = got
        cls.ts = ui_art.panel_sets(cls.med / "global" / "ui" / "panel" / "tradestash.dc6", cls.d2r.pal)[0]

    def test_panel_for_sizes(self):
        for cols, rows in ((10, 6), (10, 4), (6, 3), (1, 1), (10, il.max_rows())):
            tab = il.Tab("charms", "Charms", "Charm Inventory", "invchm", cols, rows)
            im = ia.panel_image(self.med, self.d2r, tab)
            self.assertEqual(im.size, (il.PANEL_W, il.PANEL_H))
            gx, gy = il.grid_origin(cols, rows)
            a, t = np.asarray(im.convert("RGB")), np.asarray(self.ts.convert("RGB"))
            # the cells are the stash's own (its last rows, its first columns), the header and the bottom band untouched
            tx, ty = il.INNER_X0, il.GRID_BOTTOM - rows * il.CELL
            self.assertTrue((a[gy + 1:gy + rows * il.CELL - 2, gx:gx + cols * il.CELL - 2] ==   # under the top line
                             t[ty + 1:ty + rows * il.CELL - 2, tx:tx + cols * il.CELL - 2]).all(), (cols, rows))
            self.assertTrue((a[il.GRID_BOTTOM + 1:] == t[il.GRID_BOTTOM + 1:]).all())
            self.assertTrue((a[:16] == t[:16]).all())
            # the body above the grid is dark except the summary box rim and the title
            x0, y0, x1, y1 = il.summary_box(rows)
            self.assertGreater(max(a[y, x0 + 20:x1 - 20].mean() for y in range(y0, y0 + 4)), 60)  # the box's rim
            self.assertLess(a[y0 + 6:y1 - 6, x0 + 6:x1 - 6].mean(), 30)  # its dark inside

    def test_title_is_drawn_and_too_long_refused(self):
        tab = il.Tab("charms", "Charms", "Charm Inventory", "invchm", 10, 6)
        a = np.asarray(ia.panel_image(self.med, self.d2r, tab).convert("RGB")).astype(int)
        x0, y0, x1, y1 = il.TITLE_BOX
        self.assertGreater((np.abs(a[y0:y1, x0:x1] - np.array(ia.TITLE_COLOUR)).sum(axis=2) < 90).sum(), 30)
        with self.assertRaises(ValueError):
            ia.panel_image(self.med, self.d2r, il.Tab("charms", "C", "W" * 60, "invchm", 10, 6))

    def test_refused_size(self):
        with self.assertRaises(il.ClassicSizeError):
            ia.panel_image(self.med, self.d2r, il.Tab("charms", "C", "C", "invchm", 12, 6))

    def test_tab_and_button_frames(self):
        frames = ia.tab_frames(self.d2r, il.CHARMS)
        self.assertEqual([f.size for f in frames], [(il.TAB_W, il.TAB_H)] * 3)
        self.assertNotEqual(frames[0].getpixel((0, 0)), frames[2].getpixel((0, 0)))  # this tab: gold rim
        self.assertEqual([f.size for f in ia.button_frames(self.d2r, il.CHARMS)], [(ia.BUTTON, ia.BUTTON)] * 2)

    def test_written_files(self):
        with tempfile.TemporaryDirectory() as d:
            tabs = (il.CHARMS, il.Tab("maps", "Maps", "Maps", "invbsc", 12, 6))  # maps: too wide, no panel
            lines = ia.art(Path(d), self.med, self.d2r, tabs, preview_dir=Path(d) / "prev")
            panel = Path(d) / "global" / "ui" / "panel"
            self.assertTrue(any("maps: no classic panel" in ln for ln in lines))
            self.assertFalse((panel / "invtabs_maps.dc6").exists())
            sizes = lambda n: [(w, h) for w, h, *_ in dc6.read_dc6(panel / f"{n}.dc6")]  # noqa: E731
            self.assertEqual(sizes("invtabs_charms"), PANEL_SIZES)
            self.assertEqual(sizes("invtabs_tab_charms"), [(il.TAB_W, il.TAB_H)] * 3)
            self.assertFalse((panel / "invtabs_tab_maps.dc6").exists())  # no classic panel: no classic tab button either
            self.assertEqual(sizes(il.BUTTON_ART), [(ia.BUTTON, ia.BUTTON)] * 2)
            for name in ("invtabs_charms", "invtabs_tab_charms", il.BUTTON_ART):
                for w, h, _ox, _oy, block in dc6.read_dc6(panel / f"{name}.dc6"):
                    idx = np.array(_indices(w, h, block))
                    self.assertLessEqual(int(idx.max()), 224, name)
            self.assertTrue((Path(d) / "prev" / "mock_charms_10x6_x2.png").exists())


def _indices(w: int, h: int, block: bytes) -> list[list[int]]:
    """Palette indices of a DC6 frame block (rows bottom-up; 0x80 ends a line, 0x80|n skips n, n < 0x80 a run)."""
    rows, row, i = [], [], 0
    while i < len(block) and len(rows) < h:
        b = block[i]
        i += 1
        if b == 0x80:
            rows.append(row + [0] * (w - len(row)))
            row = []
        elif b & 0x80:
            row += [0] * (b & 0x7F)
        else:
            row += list(block[i:i + b])
            i += b
    return rows[::-1]


if __name__ == "__main__":
    unittest.main()
