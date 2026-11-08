"""The mod's gamepad inventory and stash layouts (tools/pad_ui.py, bugs #556 / #557): Median's 10 x 6 backpack inside D2R's
gamepad art, the Send to stash buttons, and the seven stash tabs with the PC pages moved to the gamepad page."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import median_tabs  # noqa: E402
import pad_ui  # noqa: E402
import send_stash  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D2R_CTRL = Path(fxpaths.D2R) / "data" / pad_ui.CONTROLLER
BUILT = ROOT / "work" / "mod" / "data"
HAVE_D2R = (D2R_CTRL / "playerinventoryoriginallayouthd.json").is_file()


def names(node):
    yield node.get("name")
    for c in node.get("children", []):
        yield from names(c)


class Geometry(unittest.TestCase):
    def test_grid_fits_under_the_belt_row_in_the_art(self):
        gx, gy = pad_ui.grid_origin()
        cell = pad_ui.CELL * pad_ui.GRID_SCALE
        self.assertGreaterEqual(gy, pad_ui.BAND_TOP)
        self.assertLessEqual(gy + pad_ui.GRID_ROWS * cell, pad_ui.ART_H)
        self.assertGreaterEqual(gx, 0)
        self.assertLessEqual(gx + 10 * cell, pad_ui.ART_W)

    def test_send_buttons_carry_the_plugin_names(self):
        want = {b["name"] for b in send_stash.widgets(hd=True)}
        got = pad_ui.send_buttons()
        self.assertEqual({b["name"] for b in got}, want)
        for b in got:
            self.assertEqual(b["fields"]["filename"], "PANEL\\mxl\\" + pad_ui.SEND_ART)
            self.assertEqual(b["fields"]["navigation"]["down"], {"name": "grid"})

    def test_seven_tabs_fit_d2rs_tab_row(self):
        self.assertLessEqual(pad_ui.PAD_TAB_W * median_tabs.HD_TABS, 5 * 215)


@unittest.skipUnless(HAVE_D2R, "D2R's extracted controller layouts not found (fxpaths.D2R)")
class Inventory(unittest.TestCase):
    def test_original_has_median_grid_and_buttons(self):
        lay = pad_ui.inventory_original((D2R_CTRL / "playerinventoryoriginallayouthd.json").read_text("utf-8-sig"))
        grid = pad_ui.child(lay, "grid")["fields"]
        self.assertEqual(grid["cellCount"], {"x": 10, "y": 6})
        self.assertEqual(grid["rect"]["scale"], pad_ui.GRID_SCALE)
        self.assertNotIn("down", grid.get("navigation", {}))
        order = [c.get("name") for c in lay["children"]]
        at = order.index("gold_button")
        self.assertEqual(order[at + 1:at + 4], [b["name"] for b in send_stash.widgets(hd=True)])
        self.assertEqual(pad_ui.child(lay, "slot_feet")["fields"]["navigation"]["down"], {"name": "gold_button"})

    def test_expansion_names_the_send_buttons(self):
        lay = pad_ui.inventory_expansion((D2R_CTRL / "playerinventoryexpansionlayouthd.json").read_text("utf-8-sig"))
        self.assertTrue({b["name"] for b in send_stash.widgets(hd=True)} <= set(names(lay)))
        self.assertEqual(pad_ui.child(lay, "background")["fields"]["filename"], "PANEL\\mxl\\padinventory")


@unittest.skipUnless((BUILT / pad_ui.CONTROLLER / "bankexpansionlayouthd.json").is_file(), "no built mod (tools/build.py)")
class BuiltStash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pad = pad_ui.load((BUILT / pad_ui.CONTROLLER / "bankexpansionlayouthd.json").read_text("utf-8-sig"))
        cls.pc = pad_ui.load((BUILT / pad_ui.LAYOUTS / "bankexpansionlayouthd.json").read_text("utf-8-sig"))

    def test_seven_tabs_with_the_pc_names(self):
        tabs = median_tabs.find(self.pad, "BankTabs")["fields"]
        self.assertEqual(tabs["tabCount"], median_tabs.HD_TABS)
        self.assertEqual(tabs["textStrings"], median_tabs.find(self.pc, "BankTabs")["fields"]["textStrings"])

    def test_pages_and_medtab_widgets_match_the_pc_layout(self):
        for page in pad_ui.PAGES:
            pc = [c.get("name") for c in median_tabs.find(self.pc, page)["children"]]
            self.assertEqual([c.get("name") for c in median_tabs.find(self.pad, page)["children"]], pc)
        pc_med = sorted(n for n in names(self.pc) if n and n.startswith("medtab_"))
        self.assertEqual(sorted(n for n in names(self.pad) if n and n.startswith("medtab_")), pc_med)

    def test_rebuild_refuses_a_finished_layout(self):
        with self.assertRaises(ValueError):
            pad_ui.stash(json.loads(json.dumps(self.pad)), self.pc)


if __name__ == "__main__":
    unittest.main()
