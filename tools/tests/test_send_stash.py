"""tools/send_stash.py: the send-to-stash buttons in the inventory layouts, the committed plugin header, the art."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import median_stash  # noqa: E402
import median_tabs  # noqa: E402
import send_stash as ss  # noqa: E402
import sendstash_checks as sc  # noqa: E402
import ui_layouts  # noqa: E402

INVENTORY_LAYOUTS = {"playerinventoryoriginallayouthd.json": True, "playerinventoryexpansionlayouthd.json": True,
                     "playerinventoryoriginallayout.json": False, "playerinventoryexpansionlayout.json": False}


def find(node, name):
    if node.get("name") == name:
        return node
    for c in node.get("children", []):
        hit = find(c, name)
        if hit:
            return hit
    return None


def have_baseline():
    return (ui_layouts.BASE_UI / "layouts" / "bankexpansionlayouthd.json").exists()


class SendStashTest(unittest.TestCase):
    def test_widgets(self):
        for hd in (True, False):
            ws = ss.widgets(hd)
            json.loads(json.dumps(ws))
            self.assertEqual([w["name"] for w in ws], [ss.NO_SLOTS, ss.JOINED, ss.BUTTON])  # the live one on top
            self.assertNotIn('"@', json.dumps(ws))  # literal text in a served layout (bug #30)
            *greyed, live = ws
            self.assertEqual(live["fields"]["onClickMessage"], "PanelManager:OpenPanel:mxl2012-core/SendStash")
            self.assertEqual(live["fields"]["tooltipString"], "Send storable/stackable items to stash")  # owner's wording
            self.assertNotIn("visible", live["fields"])
            for w in greyed:
                self.assertNotIn("onClickMessage", w["fields"])
                self.assertIs(w["fields"]["visible"], False)  # the plugin shows the one that fits
                self.assertTrue(w["fields"]["tooltipString"].startswith(ss.TIP + "\n"))
                self.assertEqual(w["fields"]["rect"], live["fields"]["rect"])
            self.assertIn("Reign of the Warlock", ws[0]["fields"]["tooltipString"])
            self.assertIn("joined", ws[1]["fields"]["tooltipString"])

    def test_places(self):
        # HD: inside the bottom-left square of the inventory picture (classic 17..50 x 386..417 scaled)
        x, y, w, h = ss.HD_RECT
        self.assertGreaterEqual(x, 17 * ui_layouts.SX)
        self.assertLessEqual(x + w, 50 * ui_layouts.SX)
        self.assertGreaterEqual(y, 386 * ui_layouts.SY)
        self.assertLessEqual(y + h, 417 * ui_layouts.SY)
        # classic: between the close button (18, 384, 32 x 32) and the gold box (coin recess from 82; its frame from 80)
        x, y, w, h = ss.SD_RECT
        self.assertGreater(x, 18 + 32)
        self.assertLess(x + w, 80)
        self.assertLessEqual(abs((y + h / 2) - (384 + 16)), 2)  # on the close button's centre line
        self.assertLessEqual(y + h, 432)

    def test_art(self):
        frames = ss.hd_frames()
        self.assertEqual(len(frames), 4)
        self.assertEqual({f.size for f in frames}, {ss.HD_RECT[2:]})
        self.assertEqual(len(set(f.tobytes() for f in frames)), 4)

    def test_sd_frames(self):
        pal = [(i, i, i) for i in range(256)]
        frames = ss.sd_frames(pal)
        self.assertEqual(len(frames), 3)
        for f in frames:
            self.assertEqual(f.shape, (ss.SD_RECT[3], ss.SD_RECT[2]))
            self.assertGreaterEqual(int(f.min()), 1)  # opaque, palette 1-224 (rotw_stash_legacy.quantise)
            self.assertLessEqual(int(f.max()), 224)

    def test_slot_codes(self):
        lay = {"children": [{"type": "AdvancedStashSlotWidget", "fields": {"itemCode": "r01"}},
                            {"type": "Widget", "children": [{"type": "AdvancedStashSlotWidget", "fields": {"itemCode": "gcv"}},
                                                            {"type": "AdvancedStashSlotWidget", "fields": {"itemCode": "r01"}}]},
                            {"type": "ButtonWidget", "fields": {"itemCode": "xxx"}}]}
        self.assertEqual(ss.slot_codes(lay), ["r01", "gcv"])
        text = ss.header(["r01", "g$a"])
        self.assertIn('"r01 ", "g$a "', text)
        self.assertIn("CodeCount = 2;", text)
        with self.assertRaises(ValueError):
            ss.header(["toolong"])

    def test_header_is_current(self):
        if not have_baseline():
            self.skipTest("no D2R baseline (py -3 tools/hd_ui.py baseline <extraction>)")
        self.assertEqual(ss.HEADER.read_text("utf-8"), ss.header(), "run `py -3 tools/send_stash.py header`")
        codes = ss.mod_stash_layout_codes()
        self.assertTrue(set(median_stash.CODES) <= set(codes))
        self.assertTrue(set(median_tabs.CODES) <= set(codes))  # the "@" codes as their real codes
        self.assertFalse([c for c in codes if median_tabs.PLACEHOLDER in c])
        self.assertGreaterEqual(len(codes), 91 + len(median_stash.CODES) + len(median_tabs.CODES))

    def test_layouts(self):
        if not have_baseline():
            self.skipTest("no D2R baseline (py -3 tools/hd_ui.py baseline <extraction>)")
        from rotw_stash_legacy import lenient_json
        for name, hd in INVENTORY_LAYOUTS.items():
            text = ss.add_to_layout(ui_layouts.baseline(name), hd)
            self.assertEqual(ss.add_to_layout(text, hd), text)  # once
            lay = lenient_json(re.sub(r"/\*.*?\*/", "", text, flags=re.S))  # the baseline has /* */ blocks too
            for w in ss.widgets(hd):
                self.assertEqual(find(lay, w["name"]), w, name)
            self.assertIsNotNone(find(lay, "close"), name)
            self.assertEqual(text.count(ss.BUTTON + '"'), 1, name)


class ParseTest(unittest.TestCase):
    def test_state(self):
        lines = ["sendstash show=button host=1 running=0 clicks=2 runs=3 sent=14 full=3 nottaken=0 busy=0 lines=3 linefails=0 faults=0",
                 'sendstash last="Sent 14 items. 3 stayed: stack full (El Rune, Chipped Ruby x2)."']
        st = sc.parse_state(lines)
        self.assertEqual(st["show"], "button")
        self.assertEqual((st["sent"], st["full"], st["clicks"], st["host"]), (14, 3, 2, 1))
        self.assertEqual(st["last"], "Sent 14 items. 3 stayed: stack full (El Rune, Chipped Ruby x2).")

    def test_backpack(self):
        items = [{"code": "r01", "page": 0}, {"code": "box", "page": 0}, {"code": "gcr", "page": 4}]
        self.assertEqual(sc.backpack(items), ["r01"])


if __name__ == "__main__":
    unittest.main()
