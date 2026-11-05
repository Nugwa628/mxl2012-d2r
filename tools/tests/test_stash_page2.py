"""tools/stash_page2.py: personal stash page 2's layouts, the committed plugin header, the strip in the stock stash layouts."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import stash_page2 as sp  # noqa: E402


def find(node, name):
    if node.get("name") == name:
        return node
    for c in node.get("children", []):
        hit = find(c, name)
        if hit:
            return hit
    return None


class StashPage2Test(unittest.TestCase):
    def test_header_is_current(self):
        self.assertEqual(sp.HEADER.read_text("utf-8"), sp.header(), "run `py -3 tools/stash_page2.py header`")

    def test_panels(self):
        for lay in (sp.panel_hd(), sp.panel_sd()):
            json.loads(json.dumps(lay))  # strict JSON
            self.assertEqual(lay["name"], "mxl2012-core/StashPage2")  # D2RCore: <plugin id>/<local id>
            grid = find(lay, sp.GRID)["fields"]
            self.assertEqual(grid["cellCount"], {"x": 10, "y": 10})
            # an overlay on the open stock stash (bug #543): the strip and the grid only, so the stock tabs, gold box and X
            # under it keep their clicks
            self.assertEqual([c["name"] for c in lay["children"]], [sp.PAGE_STRIP, sp.GRID])
            self.assertGreater(lay["fields"]["priority"], 5)  # over the stock stash (bankoriginallayout(hd).json: 5)
            strip = find(lay, sp.PAGE_STRIP)
            self.assertEqual({c["fields"].get("onClickMessage") for c in strip["children"] if c["type"] == "ButtonWidget"},
                             {"PanelManager:ClosePanel:mxl2012-core/StashPage2"})
            self.assertEqual(find(strip, "MxlPageText")["fields"]["text"], "2 / 2")
            self.assertNotIn('"@', json.dumps(lay))  # no string keys in a served layout (bug #30)
        self.assertEqual(find(sp.panel_hd(), sp.GRID)["fields"]["rect"], {"x": 89, "y": 219})  # bankexpansionlayouthd.json grid
        self.assertEqual(find(sp.panel_sd(), sp.GRID)["fields"]["rect"], {"x": 15, "y": 63})    # bankexpansionlayout.json grid

    def test_stock_strips(self):
        for strip in (sp.stock_strip_hd(), sp.stock_strip_sd()):
            self.assertEqual(strip["name"], "MxlPersonalNavigation")
            self.assertIsNone(find(strip, "MxlPageText"))  # D2R's "Page n / m" shows there on the Shared tab
            self.assertEqual({c["fields"].get("onClickMessage") for c in strip["children"] if c["type"] == "ButtonWidget"},
                             {"PanelManager:OpenPanel:mxl2012-core/StashPage2"})
        # at D2R's shared stash arrows (StashNavigation), which the Personal tab does not show
        self.assertEqual(sp.stock_strip_hd()["fields"]["rect"], {"x": 369, "y": 1211, "width": 420, "height": 93})
        self.assertEqual(sp.stock_strip_sd()["fields"]["rect"], {"x": 15, "y": 385, "width": 164, "height": 32})

    def test_hd_stash_layout_has_the_strip(self):
        import ui_layouts
        if not (ui_layouts.BASE_UI / "layouts" / "bankexpansionlayouthd.json").exists():
            self.skipTest("no D2R baseline (py -3 tools/hd_ui.py baseline <extraction>)")
        from rotw_stash_legacy import lenient_json
        lay = lenient_json(ui_layouts.stash_hd())
        box = find(lay, "basicstash_container")
        self.assertEqual([c["name"] for c in box["children"]][-2:], ["MxlPersonalNavigation", "SharedStashTabContainer"])
        ctl = ui_layouts.stash_hd("controller/bankexpansionlayouthd.json")
        self.assertNotIn("MxlPersonalNavigation", ctl)  # the gamepad layout has no arrows to click


if __name__ == "__main__":
    unittest.main()
