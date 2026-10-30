"""Unit tests of tools/rotw_stash_legacy.py on synthetic data (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_rotw_stash_legacy.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import dc6  # noqa: E402
import rotw_stash_legacy as rs  # noqa: E402
import ui_art  # noqa: E402

PAL = [(i, 255 - i, i // 2) for i in range(256)]


def slot(code, x, y, w=98, h=98):
    return {"type": "AdvancedStashSlotWidget", "name": code, "fields": {"rect": {"width": w, "height": h, "x": x, "y": y},
                                                                         "itemCode": code}}


HD = {"basedOn": "BankOriginalLayoutHD.json", "type": "BankPanel", "name": "BankExpansionLayout",
      "fields": {"backgroundFile": ["P", "S", "G", "C", "R"], "tabNotificationDurationSeconds": 0.33},
      "children": [
          {"type": "TabBarWidget", "name": "BankTabs", "fields": {
              "tabCount": 5, "disabledFrames": [-1, 0, 0, 0, 0], "textStrings": ["@personal", "@shared", "@gems", "@materials", "@runes"],
              "onSwitchTabMessage": "BankPanelMessage:SelectTab"}},
          {"type": "Widget", "name": "advancedstash_gems", "children": [slot("gcw", 164, 232), slot("gfw", 164, 330)]},
          {"type": "Widget", "name": "advancedstash_materials", "children": [slot("pk1", 102, 232, 98, 196), slot("rvs", 102, 596)]},
          {"type": "Widget", "name": "advancedstash_runes", "children": [slot("r01", 114, 268), slot("r02", 218, 272)]},
          {"type": "Widget", "name": "advancedstash_horadriccube", "children": [
              {"type": "InventoryGridWidget", "name": "horadriccube_grid", "fields": {
                  "rect": {"x": 431, "y": 784}, "cellCount": {"x": 3, "y": 4}}},
              {"type": "ButtonWidget", "name": "convert", "fields": {"rect": {"x": 520, "y": 1239},
                                                                     "onClickMessage": "BankPanelMessage:Convert"}},
              {"type": "ButtonWidget", "name": "withdraw_button", "fields": {
                  "rect": {"x": 398, "y": 1381}, "onClickMessage": "BankPanelMessage:WithdrawStash"}}]}]}
SD = {"basedOn": "BankOriginalLayout.json", "type": "BankPanel", "name": "BankExpansionLayout",
      "fields": {"backgroundFile": ["PANEL\\expandedstash", "PANEL\\additionalstash"]},
      "children": [{"type": "ClickCatcherWidget", "name": "click_catcher"},
                   {"type": "GridImageWidget", "name": "background", "fields": {"filename": "PANEL\\expandedstash"}},
                   {"type": "TextBoxWidget", "name": "gold_max", "fields": {"rect": {"x": 78, "y": 35}}},
                   {"type": "TextBoxWidget", "name": "gold_amount", "fields": {"rect": {"x": 40, "y": 358}}},
                   {"type": "ButtonWidget", "name": "gold_withdraw", "fields": {"rect": {"x": 15, "y": 357}}},
                   {"type": "ButtonWidget", "name": "close", "fields": {"rect": {"x": 272, "y": 384}}},
                   {"type": "InventoryGridWidget", "name": "grid", "fields": {"rect": {"x": 15, "y": 63},
                                                                             "cellCount": {"x": 10, "y": 10}}},
                   {"type": "TabBarWidget", "name": "BankTabs", "fields": {"tabCount": 2}},
                   {"type": "Widget", "name": "SharedStashTabContainer", "children": [
                       {"type": "TextBoxWidget", "name": "CurrentSharedStashText", "fields": {"text": "@SharedStashPage"}}]}]}
BASE = {"type": "BankPanel", "name": "BankOriginalLayout", "children": [
    {"type": "ButtonWidget", "name": "gold_withdraw", "fields": {"rect": {"x": 75, "y": 218}, "filename": "PANEL\\goldcoinbtn",
                                                                 "tooltipString": "@strGoldWithdraw"}}]}


def fake_d2r(root: Path) -> None:
    """A D2R extraction with the files the step reads (flat colours)."""
    d = root / "data"
    (d / "global" / "palette" / "units").mkdir(parents=True)
    (d / "global" / "palette" / "units" / "pal.dat").write_bytes(bytes(c for r, g, b in PAL for c in (b, g, r)))
    lay = d / "global" / "ui" / "layouts"
    lay.mkdir(parents=True)
    (lay / "bankexpansionlayouthd.json").write_text(json.dumps(HD).replace("0.33}", "0.33,}"), "utf-8")  # a trailing comma
    (lay / "bankexpansionlayout.json").write_text("// D2R's comment\n" + json.dumps(SD), "utf-8")
    (lay / "bankoriginallayout.json").write_text(json.dumps(BASE), "utf-8")
    panel = d / "global" / "ui" / "panel"
    panel.mkdir(parents=True)
    tiles = [np.full((y1 - y0, x1 - x0), 40, np.int32) for x0, y0, x1, y1 in ui_art.TILES]
    for n in ("expandedstash", "additionalstash"):
        (panel / f"{n}.dc6").write_bytes(rs.dc6_bytes(tiles))
    for n, frames in (("miniconvert", 2), ("buysellbtn", 12), ("gemsocket", 1), ("goldcoinbtn", 2)):
        (panel / f"{n}.dc6").write_bytes(rs.dc6_bytes([np.full((32, 32), 9, np.int32)] * frames))
    hd = d / "hd" / "global" / "ui"
    for rel, size, n in (("panel/stash/additionalstash/panel_additionalstash_gems", (1162, 1507), 1),
                         ("panel/stash/additionalstash/panel_additionalstash_consumables", (1162, 1507), 1),
                         ("panel/stash/additionalstash/panel_additionalstash_runes", (1162, 1507), 1),
                         ("panel/stash/mkb_tabs_195_tga", (195, 73), 2),
                         ("panel/stash/additionalstash/horadriccubecover", (296, 393), 1),
                         ("frontend/hd/final/frontend_buttonsmall", (366, 93), 4),
                         ("panel/stash/additionalstash/stashnotification", (195, 62), 1)):
        ui_art.write_sprite(hd / f"{rel}.sprite", [Image.new("RGBA", size, (120, 100, 60, 255))] * n, stride=size[0] + 2 if n > 1 else None)


class EncodeTests(unittest.TestCase):
    def test_frame_round_trip(self):
        idx = np.zeros((5, 300), np.int32)
        idx[0, :200] = 7          # a run longer than 127
        idx[2, 10:20] = 3         # transparent lead, then a run
        idx[4, 150:] = 200        # a lead of 150 transparent pixels (two skips)
        rows = dc6.decode_frame(300, 5, rs.encode_frame(idx), PAL)
        back = np.array([[PAL.index(p[:3]) if p[3] else 0 for p in r] for r in rows])
        self.assertTrue((back == idx).all())

    def test_quantise_keeps_to_safe_indices(self):
        im = Image.new("RGBA", (16, 4), (0, 0, 0, 255))
        im.putpixel((0, 0), (0, 0, 0, 0))
        idx = rs.quantise(im, PAL)
        self.assertEqual(idx[0, 0], 0)
        self.assertTrue(((idx[0, 1:] >= 1) & (idx[0, 1:] <= 224)).all())


class LayoutTests(unittest.TestCase):
    def test_classic_box_is_classic_cells(self):
        self.assertEqual(rs.classic_box((164, 232, 98, 98))[2:], (28, 28))
        self.assertEqual(rs.classic_box((102, 232, 98, 196))[2:], (28, 57))
        x, y, _w, _h = rs.classic_box((164, 232, 98, 98))
        self.assertAlmostEqual(x + 14, (164 + 49) * 320 / 1162, delta=1)
        self.assertAlmostEqual(y + 14, (232 + 49) * 432 / 1507, delta=1)

    def test_layout_follows_hd(self):
        lay = rs.classic_layout(HD, SD, BASE)
        text = json.dumps(lay)
        self.assertNotIn('"@', text)
        self.assertEqual(lay["fields"]["backgroundFile"][2:], ["PANEL\\rotwstash_gems", "PANEL\\rotwstash_materials",
                                                               "PANEL\\rotwstash_runes"])
        self.assertEqual([c["name"] for c in rs.find(lay, "advancedstash_runes")["children"]], ["r01", "r02"])
        tabs = rs.find(lay, "BankTabs")["fields"]
        self.assertEqual((tabs["tabCount"], tabs["textStrings"][3]), (5, "Materials"))
        box = rs.find(lay, "basicstash_container")
        self.assertEqual([c["name"] for c in box["children"]],
                         ["gold_max", "gold_amount", "gold_withdraw", "grid", "SharedStashTabContainer"])
        gw = rs.find(lay, "gold_withdraw")["fields"]   # base fields carried, the expansion's rect wins, the key written out
        self.assertEqual((gw["rect"], gw["filename"], gw["tooltipString"]), ({"x": 15, "y": 357}, "PANEL\\goldcoinbtn", "Withdraw"))
        self.assertEqual(rs.find(lay, "CurrentSharedStashText")["fields"]["text"], "Page %u / %u")
        self.assertEqual(sum(1 for c in lay["children"] if c["name"] == "grid"), 0)

    def test_unknown_key_is_an_error(self):
        sd = json.loads(json.dumps(SD))
        sd["children"][-1]["children"][0]["fields"]["text"] = "@NoSuchKey"
        with self.assertRaises(ValueError):
            rs.classic_layout(HD, sd, BASE)


class BuildTests(unittest.TestCase):
    def test_build_and_check(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            fake_d2r(root / "d2r")
            d2r = rs.D2R(root / "d2r")
            out, mod = root / "stage" / "data", root / "mod" / "data"   # staged as tools/build.py does by default
            rs.build(d2r, out)
            panel = out / "global" / "ui" / "panel"
            self.assertEqual([f[:2] for f in dc6.read_dc6(panel / "rotwstash_gems.dc6")],
                             [(256, 256), (64, 256), (256, 176), (64, 176)])
            self.assertEqual([f[:2] for f in dc6.read_dc6(panel / "rotwstash_tabs.dc6")], [(63, 24)] * 2)
            self.assertEqual([f[:2] for f in dc6.read_dc6(panel / "rotwstash_cubecover.dc6")], [(87, 116)])
            problems, notes = rs.check(d2r, out, mod)
            self.assertEqual(problems, [])
            self.assertTrue(any("no built tables" in n for n in notes))
            # the tables: one item with a picture, one without
            excel, items = mod / "global" / "excel", mod / "global" / "items"
            excel.mkdir(parents=True)
            items.mkdir(parents=True)
            (excel / "misc.txt").write_text("name\tcode\tinvfile\tAdvancedStashStackable\nEl Rune\tr01\tinvrEl\t1\n"
                                            "Eld Rune\tr02\tinvrEld\t1\n", "utf-8")
            (items / "invrel.dc6").write_bytes(rs.dc6_bytes([np.full((28, 28), 5, np.int32)]))
            problems, _notes = rs.check(d2r, out, mod)
            self.assertEqual(problems, ["r02: classic picture invrEld.dc6 missing"])
            # a slot moved onto its neighbour
            lp = out / "global" / "ui" / "layouts" / "bankexpansionlayout.json"
            lay = json.loads(lp.read_text("utf-8"))
            a, b = rs.find(lay, "advancedstash_gems")["children"]
            b["fields"]["rect"] = dict(a["fields"]["rect"])
            lp.write_text(json.dumps(lay), "utf-8")
            problems, _notes = rs.check(d2r, out, mod)
            self.assertIn("page gems: gfw overlaps gcw", problems)


if __name__ == "__main__":
    unittest.main()
