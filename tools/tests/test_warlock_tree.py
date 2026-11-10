"""Unit tests of the Warlock's classic tree (warlock_tree.py) and the gamepad UI's trees (pad_skill_trees.py) on synthetic
data (no game files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_warlock_tree.py" """
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import install_mod  # noqa: E402
import pad_skill_trees as pst  # noqa: E402
import warlock_tree as wt  # noqa: E402

COLS, ROWS = [15, 84, 153], [14, 82, 150, 218, 287, 355]   # D2R's classic skillColumn / skillRow + 240
LAYOUT = {"fields": {"skillRow": [-226, -158, -90, -22, 47, 115], "skillColumn": [15, 84, 153],
                     "cancelPositionX": [15, 100, 171]},
          "children": [{"name": "Background", "fields": {"rect": {"x": 0, "y": -240}}},
                       {"name": "Tab0", "fields": {"activationRect": {"x": 231, "y": -132, "width": 90, "height": 108}}},
                       {"name": "Tab1", "fields": {"activationRect": {"x": 231, "y": -24, "width": 90, "height": 108}}},
                       {"name": "Tab2", "fields": {"activationRect": {"x": 231, "y": 84, "width": 90, "height": 108}}}]}


def synthetic_box() -> Image.Image:
    """A Median-like box for the detector: light 2-px bevel left of the icon, dark level box at its lower right."""
    a = np.zeros((75, 75, 4), np.uint8)
    a[6:58, 6:8] = (160, 160, 160, 255)            # x -2..-1 (piece origin = icon - 8)
    a[50:72, 50:72] = (28, 28, 28, 255)            # level box
    return Image.fromarray(a, "RGBA")


class WarlockClassicTreeTests(unittest.TestCase):
    def test_geometry_from_the_classic_layout(self):
        cols, rows, tabs = wt.geometry(LAYOUT)
        self.assertEqual((cols, rows), (COLS, ROWS))
        self.assertEqual(tabs, [(108, 216), (216, 324), (324, 432)])

    def test_links_are_same_page_prerequisites_only(self):
        cells = {"A": (0, 0), "B": (1, 0), "C": (2, 1)}
        reqs = {"B": ["A"], "C": ["B", "Elsewhere"], "A": []}
        self.assertEqual(wt.links(cells, reqs), [((0, 0), (1, 0)), ((1, 0), (2, 1))])

    def test_cancel_code_keeps_the_close_button_off_row_6_skills(self):
        pages = {1: {"a": (5, 0), "b": (5, 2)}, 2: {"c": (5, 1)}, 3: {"d": (5, 0), "e": (5, 2)}}
        self.assertEqual(wt.cancel_code(pages, LAYOUT), 212)   # the Warlock's own rows 6
        self.assertEqual(wt.cancel_code({1: {}, 2: {"x": (5, 0)}, 3: {}}, LAYOUT), 121)
        with self.assertRaises(ValueError):
            wt.cancel_code({1: {"a": (5, 0), "b": (5, 1), "c": (5, 2)}, 2: {}, 3: {}}, LAYOUT)

    def test_box_and_arrow_detection_on_a_drawn_page(self):
        stone = Image.new("RGBA", (320, 432), (90, 90, 90, 255))
        cells = [(0, 2), (1, 1), (3, 1), (5, 0)]
        arrows = [((0, 2), (1, 1)), ((1, 1), (3, 1)), ((3, 1), (5, 0))]
        page = wt.page_picture(stone, synthetic_box(), cells, arrows, COLS, ROWS)
        for r in range(6):
            for c in range(3):
                self.assertEqual(wt.cell_has_box(page, COLS[c], ROWS[r]), (r, c) in cells, (r, c))
        for a, b in arrows:
            self.assertTrue(wt.arrow_seen(page, a, b, COLS, ROWS), (a, b))
        self.assertFalse(wt.arrow_seen(page, (0, 0), (1, 0), COLS, ROWS))   # no arrow drawn there

    def test_split_letters_cuts_touching_letters_at_the_thinnest_columns(self):
        # three letters of widths 5, 7, 2 touching with faint joins (ink 3) between them
        ink = [9, 9, 9, 9, 9, 3, 9, 9, 9, 9, 9, 9, 9, 3, 9, 9]
        self.assertEqual(wt.split_letters(ink, "AMI"), [(0, 5), (6, 13), (14, 16)])
        with self.assertRaises(ValueError):
            wt.split_letters([9, 9], "ABCDE")

    def test_lettering_sets_letters_one_pixel_apart(self):
        g = {"A": np.ones((7, 5)), "B": np.ones((7, 4))}
        im = wt.lettering(g, "ABA")
        self.assertEqual(im.size, (5 + 4 + 5 + 2, 7))
        self.assertEqual(np.asarray(im)[3, 5, 3], 0)       # the gap column
        with self.assertRaises(ValueError):
            wt.lettering(g, "AC")

    def test_icons_are_classic_size_and_median_toned(self):
        hd = Image.new("RGBA", (130, 130), (120, 80, 40, 255))
        hd.paste((250, 250, 250, 255), (40, 40, 90, 90))
        im = wt.icon48(hd)
        self.assertEqual(im.size, (48, 48))
        a = np.asarray(im)
        self.assertTrue((a[..., 0] == a[..., 1]).all() and (a[..., 1] == a[..., 2]).all())   # grey
        self.assertLess(a[2, 2, 0], 80)                    # the plate dark
        self.assertGreater(a[24, 24, 0], 200)              # the glyph white


class PadSkillTreeTests(unittest.TestCase):
    GEO = ([451, 789, 1125], [179, 368, 560, 750, 939, 1129], (268, 3))

    def pieces(self):
        w, h = pst.SOCKET_CROP[2] - pst.SOCKET_CROP[0], pst.SOCKET_CROP[3] - pst.SOCKET_CROP[1]
        sock = np.zeros((h, w, 4), np.uint8)
        x0, y0 = -pst.SOCKET_CROP[0], -pst.SOCKET_CROP[1]
        bx0, by0, bx1, by1 = pst.SOCKET_BOX
        sock[y0 + by0:y0 + by1 + 1, x0 + bx0:x0 + bx1 + 1] = (200, 200, 200, 255)
        sock[y0 + by0 + 12:y0 + by1 - 11, x0 + bx0 + 12:x0 + bx1 - 11, 3] = 60     # the socket's see-through middle
        arrow = np.zeros((pst.ARROW_CROP[3] - pst.ARROW_CROP[1], pst.ARROW_CROP[2] - pst.ARROW_CROP[0], 4), np.uint8)
        arrow[:, 25:45] = (180, 180, 180, 255)
        return Image.fromarray(sock, "RGBA"), Image.fromarray(arrow, "RGBA")

    def test_layout_geometry(self):
        lay = {"fields": {"skillColumn": [451, 789, 1125], "skillRow": [179, 368, 560, 750, 939, 1129]},
               "children": [{"name": "Tab0", "fields": {"rect": {"x": 19, "y": 5}},
                             "children": [{"name": "Background", "fields": {"rect": {"x": 249, "y": -2}}}]}]}
        self.assertEqual(pst.layout_geometry(lay), self.GEO)

    def test_frame_has_sockets_on_skills_only_and_arrows_on_links_only(self):
        sock, arrow = self.pieces()
        strip = Image.new("RGBA", (1259, 1277), (0, 0, 0, 0))
        cells = [(r, c) for r in range(5) for c in (0, 2)]
        links = [((r, 0), (r + 1, 0)) for r in range(4)]
        im = pst.frame(strip, cells, links, sock, arrow, self.GEO)
        a = np.asarray(im)[..., 3]
        cols, rows, (fx, fy) = self.GEO
        ref = pst.socket_box(a, cols[0] - fx, rows[0] - fy)
        for r in range(6):
            for c in range(3):
                x, y = cols[c] - fx, rows[r] - fy
                self.assertEqual(pst.socket_at(a, x, y), (r, c) in cells, (r, c))
                if (r, c) in cells:
                    self.assertEqual(pst.socket_box(a, x, y), ref)
        for r in range(1, 6):
            for c in range(3):
                self.assertEqual(pst.arrow_at(a, cols[c] - fx, rows[r] - fy), ((r - 1, c), (r, c)) in links, (r, c))
        with self.assertRaises(ValueError):        # only links to the cell right below are drawn
            pst.frame(strip, cells, [((0, 0), (2, 0))], sock, arrow, self.GEO)


class PackagingTests(unittest.TestCase):
    def test_the_new_files_ship_with_the_mod(self):
        """install_mod.build_data (the dev install and package_release.py) copies work/mod/data whole: the files the step
        writes there reach the mod."""
        new = [Path("global") / wt.OUT_BACK.relative_to("global"), Path("global") / wt.OUT_ICONS.relative_to("global")]
        new += [Path("hd/global/ui") / pst.V2 / f"{p}skilltree{s}.sprite" for p in pst.PREFIXES.values() for s in ("", ".lowend")]
        self.assertEqual(len(new), 16)
        with tempfile.TemporaryDirectory() as tmp:
            src, empty = Path(tmp) / "src", Path(tmp) / "median"
            (src / "global" / "tiles").mkdir(parents=True)
            empty.mkdir()
            for rel in new:
                (src / rel).parent.mkdir(parents=True, exist_ok=True)
                (src / rel).write_bytes(b"x")
            with mock.patch.object(install_mod, "SRC", src), mock.patch.object(install_mod, "MXL_GLOBAL", empty):
                install_mod.build_data(Path(tmp) / "out", Path(tmp))
            for rel in new:
                self.assertTrue((Path(tmp) / "out" / rel).exists(), rel)


if __name__ == "__main__":
    unittest.main()
