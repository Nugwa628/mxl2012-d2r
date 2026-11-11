"""tools/invtabs_pad.py: the controller panel layout of an invtabs tab (docs/invtabs-pad.md)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import invtabs_pad as ip  # noqa: E402


def child(lay, name):
    return next(c for c in lay["children"] if c["name"] == name)


class InvtabsPadTests(unittest.TestCase):
    def test_default_is_ten_by_six_at_full_size(self):
        lay = ip.layout()
        self.assertEqual(lay["name"], "invtabs/Pad0")
        self.assertEqual(lay["fields"]["rect"], "$ConsoleLeftPanelRect")
        self.assertEqual(lay["fields"]["defaultWidget"], "invtabs/Grid")
        grid = child(lay, "invtabs/Grid")["fields"]
        self.assertEqual(grid["cellCount"], {"x": 10, "y": 6})
        self.assertEqual(grid["rect"], {"x": 163, "y": 783})  # 10 x 98 centred in 1305, bottom at 1371; no scale
        self.assertEqual(grid["navigation"], {"right": {"panelBoundary": True}})
        self.assertEqual(grid["chronicleFlourishOffset"], {"x": 7400, "y": 7400})

    def test_summary_sits_above_the_grid(self):
        for cols, rows in ((10, 6), (10, 4), (12, 8), (16, 16), (1, 1), (16, 2), (4, 16)):
            g = ip.geometry(ip.Spec(cols, rows))
            sx, sy, sw, sh = g["summary"]
            gx, gy, gw, gh = g["grid"]
            with self.subTest(size=(cols, rows)):
                self.assertGreaterEqual(sh, ip.SUMMARY_MIN)
                self.assertEqual(sy + sh + ip.GAP, gy)
                self.assertEqual(gy + gh, ip.GRID_BOTTOM)
                self.assertGreaterEqual(gx, ip.MARGIN)
                self.assertLessEqual(gx + gw, ip.PANEL_W - ip.MARGIN)
                self.assertLessEqual(g["scale_milli"], 1000)

    def test_big_tabs_scale_down(self):
        g = ip.geometry(ip.Spec(16, 16))
        self.assertEqual(g["scale_milli"], 663)  # (1371 - 330) / (16 * 98)
        rect = child(ip.layout(ip.Spec(16, 16)), "invtabs/Grid")["fields"]["rect"]
        self.assertEqual(rect["scale"], 0.663)
        self.assertEqual(ip.geometry(ip.Spec(12, 8))["scale_milli"], 1000)  # 12 columns still fit at full size
        self.assertLess(ip.geometry(ip.Spec(13, 4))["scale_milli"], 1000)

    def test_scale_text(self):
        self.assertEqual([ip.scale_text(m) for m in (1000, 663, 700, 50, 5)], ["1", "0.663", "0.7", "0.05", "0.005"])

    def test_slot_names_panel_and_marker(self):
        spec = ip.Spec(8, 8, 5)
        lay = ip.layout(spec)
        self.assertEqual(lay["name"], "invtabs/Pad5")
        self.assertEqual(ip.layout_path(spec), "data/global/ui/layouts/invtabs/Pad5hd.json")
        self.assertEqual(child(lay, "invtabs/Grid")["fields"]["chronicleFlourishOffset"], {"x": 7405, "y": 7400})
        self.assertEqual(child(lay, "invtabs/PadBackground")["fields"]["filename"], "d2rloader\\invtabs\\pad_8x8")

    def test_bad_sizes(self):
        for bad in ((0, 6), (17, 6), (10, 0), (10, 17)):
            with self.assertRaises(ValueError):
                ip.Spec(*bad)
        with self.assertRaises(ValueError):
            ip.Spec(10, 6, 64)

    def test_compact_json_round_trips(self):
        text = ip.dumps(ip.layout())
        self.assertNotIn(" ", text.replace("PANEL\\\\gemsocket", ""))
        self.assertEqual(json.loads(text), ip.layout())

    def test_art_spec_cells(self):
        art = ip.art_spec()
        self.assertEqual(art["size"], [1305, 1421])
        self.assertEqual(len(art["cells"]), 60)
        self.assertEqual(art["cells"][0], [163, 783, 98, 98])
        self.assertEqual(art["cells"][-1], [163 + 9 * 98, 783 + 5 * 98, 98, 98])
        self.assertEqual(art["sprite"], "data/hd/global/ui/d2rloader/invtabs/pad_10x6.sprite")

    def test_golden_file_is_current(self):
        self.assertTrue(ip.GOLDEN.exists(), "run `py -3 -I tools/invtabs_pad.py golden`")
        self.assertEqual(ip.GOLDEN.read_text("utf-8"), ip.golden_text())


if __name__ == "__main__":
    unittest.main()
