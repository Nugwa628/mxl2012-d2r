"""Unit tests of tools/rotw_stash_legacy.py on synthetic data (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_rotw_stash_legacy.py" """
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

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
        im = Image.new("RGBA", size, (120, 100, 60, 255))
        if rel.endswith("consumables"):  # D2R's Materials page: a recess (91-wide dark inside, light frame) on each slot
            d = ImageDraw.Draw(im)
            for c in rs.find(HD, "advancedstash_materials")["children"]:
                r = c["fields"]["rect"]
                x, y, h = r["x"] + 3, r["y"] + 3, (r.get("height", 98) - 6 if r.get("height", 98) > 98 else 91)
                d.rectangle((x - 3, y - 3, x + 93, y + h + 2), fill=(150, 120, 80, 255))
                d.rectangle((x, y, x + 90, y + h - 1), fill=(12, 11, 10, 255))
        ui_art.write_sprite(hd / f"{rel}.sprite", [im] * n, stride=size[0] + 2 if n > 1 else None)


def fake_mod(mod: Path) -> None:
    """The mod's cube picture (cells of 29 with a 3-pixel line: index 60 lines, 20 insides) and an inventory.txt row for it."""
    panel, excel = mod / "global" / "ui" / "panel", mod / "global" / "excel"
    panel.mkdir(parents=True, exist_ok=True)
    excel.mkdir(parents=True, exist_ok=True)
    im = np.full((432, 320), 40, np.int32)
    left, top = 15, 50
    im[top - 3:top + 8 * 29 + 3, left - 3:left + 10 * 29 + 3] = 60
    for i in range(10):
        for j in range(8):
            im[top + j * 29 + 1:top + j * 29 + 28, left + i * 29 + 1:left + i * 29 + 28] = 20
    (panel / "supertransmogrifier.dc6").write_bytes(rs.dc6_bytes([im[y0:y1, x0:x1] for x0, y0, x1, y1 in ui_art.TILES]))
    (excel / "inventory.txt").write_text("class\tinvLeft\tgridLeft\tgridTop\tgridX\tgridY\tgridBoxWidth\tgridBoxHeight\n"
                                         "Transmogrify Box Page 1\t0\t15\t50\t10\t8\t29\t29\n", "utf-8")


def fake_font(adv: int) -> tuple[bytes, list]:
    """A classic font whose every glyph advances `adv` with `adv - 1` columns of ink (cells 12 x 10)."""
    tbl = b"Woo!\x01\x00\x00\x00\x00\x01\x0a\x14" + b"".join(
        struct.pack("<HBBBBHHI", c, 0, adv, 10, 0, 0, c, 0) for c in range(256))
    cell = np.zeros((10, 12), np.int32)
    cell[1:9, :adv - 1] = 200
    return tbl, [(12, 10, 0, 0, rs.encode_frame(cell))] * 256


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
        tabs = rs.find(lay, "BankTabs")["fields"]   # the names in the art: D2R draws no text (and the Personal one clear)
        self.assertEqual((tabs["tabCount"], tabs["textStrings"], tabs["activeFrames"]), (5, [""] * 5, [5, 6, 7, 8, 9]))
        self.assertEqual((tabs["inactiveFrames"], tabs["disabledFrames"]), ([0, 1, 2, 3, 4], [-1, 1, 2, 3, 4]))
        self.assertEqual(tabs["activeTextColor"]["a"], 0)
        plain = rs.find(rs.classic_layout(HD, SD, BASE, named_tabs=False), "BankTabs")["fields"]
        self.assertEqual((plain["textStrings"][3], plain["activeFrames"]), ("Materials", [1] * 5))
        box = rs.find(lay, "basicstash_container")
        self.assertEqual([c["name"] for c in box["children"]],
                         ["gold_max", "gold_amount", "gold_withdraw", "grid", "SharedStashTabContainer"])
        gw = rs.find(lay, "gold_withdraw")["fields"]   # base fields carried, the expansion's rect wins, the key written out
        self.assertEqual((gw["rect"], gw["filename"], gw["tooltipString"]), ({"x": 15, "y": 357}, "PANEL\\goldcoinbtn", "Withdraw"))
        self.assertEqual(rs.find(lay, "CurrentSharedStashText")["fields"]["text"], "Page %u / %u")
        self.assertEqual(sum(1 for c in lay["children"] if c["name"] == "grid"), 0)
        # bug #515: the whole 10 x 8 cube small in the frame (the plugin draws the items at the grid's scale), on the
        # cube's own cells; the cover after both (D2R shows it without a cube), no lid
        _box, frame = rs.cube_grid(HD)
        self.assertEqual(frame[2:], (87, 116))
        cube = rs.find(lay, "advancedstash_horadriccube")["children"]
        self.assertEqual([c["name"] for c in cube], ["horadriccube_cells", "horadriccube_grid", "convert", "horadriccube_cover",
                                                     "withdraw_button"])
        cells, grid = cube[0]["fields"], cube[1]["fields"]
        self.assertEqual((cells["rect"], cells["filename"]), ({"x": frame[0], "y": frame[1]}, f"PANEL\\{rs.CELLS}"))
        self.assertEqual((grid["cellCount"], grid["cellSize"]), ({"x": 10, "y": 8}, "$ItemCellSize"))
        # 8 pixels a cell: 80 x 64, centred inside the 1-pixel edge of the 87 x 116 frame
        self.assertEqual(grid["rect"], {"x": frame[0] + 1 + 2, "y": frame[1] + 1 + 25, "scale": round(8 / 29, 4)})

    def test_cube_cells_follow_the_grid(self):
        frame = (100, 200, 87, 116)
        gx, gy, s = rs.mini_grid(frame)
        self.assertEqual((gx, gy, round(s * 29)), (103, 226, 8))
        with self.assertRaises(ValueError):
            rs.mini_grid((0, 0, 60, 60))
        with tempfile.TemporaryDirectory() as t:
            fake_mod(Path(t))
            picture, row = rs.cube_picture(Path(t), PAL, Path(t) / "global" / "excel" / "inventory.txt")
        im = np.asarray(rs.cube_cells(picture, row, frame)).astype(int)
        self.assertEqual(im.shape, (116, 87, 4))
        self.assertEqual((im[0, 0, 3], im[1, 1, 3], tuple(im[5, 5, :3])), (0, 255, (0, 0, 0)))   # edge clear, black inside
        # cell (0, 0) is 103..110 x 226..233 in the panel: its middle is the cells' inside, the row above it the line
        near = lambda px, rgb, tol: self.assertLess(sum(abs(a - b) for a, b in zip(px[:3], rgb)), tol, (tuple(px), rgb))
        near(im[226 - 200 + 4, 103 - 100 + 4], PAL[20], 40)
        near(im[226 - 200 - 1, 103 - 100 + 4], PAL[60], 80)
        self.assertEqual(tuple(im[226 - 200 + 64 + 3, 103 - 100 + 4, :3]), (0, 0, 0))   # below the cube: black

    def test_tab_names_fit(self):
        # 6-pixel advances: MATERIALS = 9 * 6 - 1 = 53 of ink, inside 63 less 3 + 3; 7 pixels: 62, too wide
        fit = rs.tab_label_fit(rs.Font(*fake_font(6), PAL))
        self.assertEqual([(t, w) for t, w, _ok in fit],
                         [("PERSONAL", 47), ("SHARED", 35), ("GEMS", 23), ("MATERIALS", 53), ("RUNES", 29)])
        self.assertTrue(all(ok for *_x, ok in fit))
        wide = {t: ok for t, _w, ok in rs.tab_label_fit(rs.Font(*fake_font(7), PAL))}
        self.assertEqual((wide["MATERIALS"], wide["PERSONAL"], wide["SHARED"]), (False, True, True))

    def test_named_frames_carry_the_names(self):
        font = rs.Font(*fake_font(6), PAL)
        art = [Image.new("RGBA", (63, 24), (40, 40, 40, 255)), Image.new("RGBA", (63, 24), (90, 80, 60, 255))]
        frames = rs.named_tab_frames(art, font, PAL)
        self.assertEqual((len(frames), frames[0].shape), (10, (24, 63)))
        spans = []
        for i, f in enumerate(frames):
            cols = np.nonzero((f != rs.quantise(art[i // 5], PAL)).any(axis=0))[0]
            spans.append((int(cols[0]), int(cols[-1]) - int(cols[0]) + 1))
        self.assertEqual([w for _x, w in spans[:5]], [47, 35, 23, 53, 29])   # each name whole on its own frame
        self.assertEqual(spans[5:], spans[:5])
        self.assertEqual(spans[3][0], 5)   # MATERIALS centred: 5 free columns on each side

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
            fake_mod(mod)
            with self.assertRaises(FileNotFoundError):   # the cells need the mod's cube picture
                rs.build(d2r, out, inventory=mod / "global" / "excel" / "inventory.txt")
            rs.build(d2r, out, mod, mod / "global" / "excel" / "inventory.txt")
            panel = out / "global" / "ui" / "panel"
            self.assertEqual([f[:2] for f in dc6.read_dc6(panel / "rotwstash_gems.dc6")],
                             [(256, 256), (64, 256), (256, 176), (64, 176)])
            self.assertEqual([f[:2] for f in dc6.read_dc6(panel / "rotwstash_tabs.dc6")], [(63, 24)] * 2)
            self.assertEqual([f[:2] for f in dc6.read_dc6(panel / "rotwstash_cubecover.dc6")], [(87, 116)])
            self.assertEqual([f[:2] for f in dc6.read_dc6(panel / "rotwstash_cubecells.dc6")], [(87, 116)])
            problems, notes = rs.check(d2r, out, mod)
            self.assertEqual(problems, [])
            self.assertTrue(any("no built tables" in n for n in notes))
            # the tables: one item with a picture, one without
            excel, items = mod / "global" / "excel", mod / "global" / "items"
            excel.mkdir(parents=True, exist_ok=True)
            items.mkdir(parents=True)
            (excel / "misc.txt").write_text("name\tcode\tinvfile\tAdvancedStashStackable\nEl Rune\tr01\tinvrEl\t1\n"
                                            "Eld Rune\tr02\tinvrEld\t1\n", "utf-8")
            (items / "invrel.dc6").write_bytes(rs.dc6_bytes([np.full((28, 28), 5, np.int32)]))
            problems, _notes = rs.check(d2r, out, mod)
            self.assertEqual(problems, ["r02: classic picture invrEld.dc6 missing"])
            # a slot moved onto its neighbour
            lp = out / "global" / "ui" / "layouts" / "bankexpansionlayout.json"
            lay = json.loads(lp.read_text("utf-8"))
            a, b = rs.find(lay, "advancedstash_gems")["children"][:2]
            b["fields"]["rect"] = dict(a["fields"]["rect"])
            lp.write_text(json.dumps(lay), "utf-8")
            problems, _notes = rs.check(d2r, out, mod)
            self.assertIn("page gems: gfw overlaps gcw", problems)

    def test_build_with_the_classic_font(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            fake_d2r(root / "d2r")
            fonts = root / "d2r" / "data" / "local" / "font" / "latin"
            fonts.mkdir(parents=True)
            tbl, frames = fake_font(6)
            (fonts / "font6.tbl").write_bytes(tbl)
            (fonts / "font6.dc6").write_bytes(dc6.build_dc6(frames))
            d2r = rs.D2R(root / "d2r")
            out = root / "stage" / "data"
            fake_mod(out)
            rs.build(d2r, out, inventory=out / "global" / "excel" / "inventory.txt")
            self.assertEqual([f[:2] for f in dc6.read_dc6(out / "global" / "ui" / "panel" / "rotwstash_tabs.dc6")],
                             [(63, 24)] * 10)
            problems, notes = rs.check(d2r, out)
            self.assertEqual(problems, [])
            self.assertTrue(any(n.startswith("tab names in font6: PERSONAL 47") for n in notes))
            # a font too wide: the check names the tab
            tbl, frames = fake_font(7)
            (fonts / "font6.tbl").write_bytes(tbl)
            (fonts / "font6.dc6").write_bytes(dc6.build_dc6(frames))
            problems, _notes = rs.check(rs.D2R(root / "d2r"), out)
            self.assertEqual(problems, ["tab name MATERIALS: 62 wide in font6, more than 57"])


if __name__ == "__main__":
    unittest.main()
