"""Unit tests of the HD UI tools on synthetic data (no game files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_ui.py" """
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import dc6  # noqa: E402
import skill_tree_art  # noqa: E402
import ui_art  # noqa: E402
import ui_check  # noqa: E402
import ui_layouts  # noqa: E402
import ui_panels  # noqa: E402
from PIL import Image  # noqa: E402

PAL = [(i, 255 - i, i // 2) for i in range(256)]


def flat_block(w: int, h: int, index: int) -> bytes:
    out = bytearray()
    for _ in range(h):
        left = w
        while left:
            n = min(left, 127)
            out += bytes([n]) + bytes([index]) * n
            left -= n
        out.append(0x80)
    return bytes(out)


def set_dc6(sets: int, index: int = 5) -> bytes:
    tiles = [(256, 256), (64, 256), (256, 176), (64, 176)]
    return dc6.build_dc6([(w, h, 0, 0, flat_block(w, h, index + s)) for s in range(sets) for w, h in tiles])


class SkillTreeTests(unittest.TestCase):
    def test_arrows_follow_requirements(self):
        cells = {"A": (0, 0), "B": (1, 0), "C": (2, 0), "D": (0, 2), "E": (3, 0)}
        reqs = {"B": ["A"], "C": ["B", "Missing"], "E": ["Elsewhere"]}
        self.assertEqual(skill_tree_art.page_arrows(cells, reqs), [((0, 0), (1, 0)), ((1, 0), (2, 0)), ((2, 0), (3, 0))])

    def test_no_requirement_no_arrow(self):
        self.assertEqual(skill_tree_art.page_arrows({"A": (0, 0), "B": (1, 0)}, {}), [])

    def test_requirement_on_the_page_beats_the_cell_above(self):
        cells = {"A": (0, 0), "B": (1, 0), "C": (2, 2)}
        self.assertEqual(skill_tree_art.page_arrows(cells, {"C": ["A"]}), [((0, 0), (2, 2))])

    def test_unknown_requirement_without_cell_above_gives_nothing(self):
        self.assertEqual(skill_tree_art.page_arrows({"A": (0, 0)}, {"A": ["Gone"]}), [])

    def test_titles(self):
        self.assertEqual(skill_tree_art.tab_titles("bar"), ["Special / Rage", "Stances / Spirits", "Throw / Melee"])
        recs = skill_tree_art.title_records()
        self.assertEqual(len(recs), 21)
        self.assertEqual(recs[0]["Key"], "d2r:SkillCategoryAm1")
        self.assertEqual(set(recs[0]) - {"Key"}, set(skill_tree_art.LANGS))
        self.assertEqual(len({r["Key"] for r in recs}), 21)

    def test_load_trees_reads_pages(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "skilldesc.txt").write_text("skilldesc\tSkillPage\tSkillRow\tSkillColumn\nd1\t1\t1\t1\nd2\t2\t5\t3\nd3\t0\t1\t1\n", "latin-1")
            (d / "skills.txt").write_text("skill\tcharclass\tskilldesc\treqskill1\treqskill2\n"
                                          "S1\tama\td1\t\t\nS2\tama\td2\tS1\t\nS3\tama\td3\t\t\nS4\t\td1\t\t\nS5\tzzz\td1\t\t\n", "latin-1")
            self.assertEqual(skill_tree_art.load_trees(d), {"ama": {1: {"S1": (0, 0)}, 2: {"S2": (4, 2)}}})
            self.assertEqual(skill_tree_art.load_reqs(d)["S2"], ["S1"])

    def test_arrow_layer_draws_between_cells(self):
        layer = skill_tree_art.draw_arrows([((0, 0), (1, 0))], skill_tree_art.cell_centre, skill_tree_art.SOCKET_HALF,
                                           14, 26, 36, (skill_tree_art.FW, skill_tree_art.FH))
        box = layer.getchannel("A").getbbox()
        cx = skill_tree_art.cell_centre((0, 0))[0]
        self.assertIsNotNone(box)
        self.assertTrue(box[0] <= cx <= box[2])
        self.assertTrue(box[1] > skill_tree_art.cell_centre((0, 0))[1])


class SpriteTests(unittest.TestCase):
    def test_roundtrip_single_and_strip(self):
        with tempfile.TemporaryDirectory() as d:
            one = Image.new("RGBA", (6, 4), (10, 20, 30, 255))
            ui_art.write_sprite(Path(d) / "a.sprite", [one])
            info = dc6.sprite_info(Path(d) / "a.sprite")
            self.assertEqual((info["frame_width"], info["strip_width"], info["frames"]), (6, 6, 1))
            frames = [Image.new("RGBA", (5, 3), (i * 50, 0, 0, 255)) for i in range(3)]
            ui_art.write_sprite(Path(d) / "b.sprite", frames, 7)
            info = dc6.sprite_info(Path(d) / "b.sprite")
            self.assertEqual((info["frame_width"], info["strip_width"], info["frames"]), (5, 21, 3))
            back = ui_art.read_sprite(Path(d) / "b.sprite")
            self.assertEqual([f.getpixel((0, 0)) for f in back], [(0, 0, 0, 255), (50, 0, 0, 255), (100, 0, 0, 255)])


class PanelTests(unittest.TestCase):
    def test_panel_sets_assemble_tiles(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.dc6"
            p.write_bytes(set_dc6(2))
            sets = ui_art.panel_sets(p, PAL)
            self.assertEqual(len(sets), 2)
            self.assertEqual(sets[0].size, (320, 432))
            self.assertEqual(sets[0].getpixel((300, 400))[:3], PAL[5])
            self.assertEqual(sets[1].getpixel((10, 10))[:3], PAL[6])

    def test_panel_sets_reject_wrong_tiles(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.dc6"
            p.write_bytes(dc6.build_dc6([(10, 10, 0, 0, flat_block(10, 10, 1))] * 4))
            with self.assertRaises(ValueError):
                ui_art.panel_sets(p, PAL)
            p.write_bytes(dc6.build_dc6([(256, 256, 0, 0, flat_block(256, 256, 1))] * 3))
            with self.assertRaises(ValueError):
                ui_art.panel_sets(p, PAL)

    def test_scale_keeps_edges_bright(self):
        im = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        for x in range(2):
            for y in range(4):
                im.putpixel((x, y), (200, 200, 200, 255))
        big = ui_panels.scale_panel(im, 16, 16)
        self.assertEqual(big.size, (16, 16))
        self.assertTrue(all(big.getpixel((x, 8))[0] >= 190 for x in range(4) if big.getpixel((x, 8))[3] > 200))


LAYOUT = """{
    "type": "X", "name": "L",
    "children": [
        {
            "type": "InventoryGridWidget", "name": "grid",
            "fields": {
                "rect": { "x": 93, "y": 897 },
                "cellCount": { "x": 10, "y": 4 },
                "cellSize": "$ItemCellSize",
            },
        },
        {
            "type": "InventorySlotWidget", "name": "slot_head",
            "fields": {
                "rect": { "x": 482, "y": 185, "width": 196, "height": 196 },
            }
        },
    ]
}"""


class LayoutTests(unittest.TestCase):
    def test_set_grid_hd(self):
        t = ui_layouts.set_grid(LAYOUT, 70, 740, 10, 6, ui_layouts.GRID_SCALE)
        self.assertIn('"rect": { "x": 70, "y": 740, "scale": 1.0746 }', t)
        self.assertIn('"cellCount": { "x": 10, "y": 6 }', t)
        self.assertIn('"cellSize": { "x": 98, "y": 94 }', t)
        self.assertIn('"name": "slot_head"', t)

    def test_set_grid_classic_keeps_cell_size(self):
        t = ui_layouts.set_grid(LAYOUT, 19, 212, 10, 6, None)
        self.assertIn('"rect": { "x": 19, "y": 212 }', t)
        self.assertIn('"cellSize": "$ItemCellSize"', t)

    def test_set_rect_touches_only_that_widget(self):
        t = ui_layouts.set_rect(LAYOUT, "slot_head", ui_layouts.rect(1, 2, 3, 4, 0.5))
        self.assertIn('"rect": { "x": 1, "y": 2, "width": 3, "height": 4, "scale": 0.5 }', t)
        self.assertIn('"rect": { "x": 93, "y": 897 }', t)
        self.assertEqual(ui_layouts.widget_size(LAYOUT, "slot_head"), (196, 196))

    def test_scale_constants(self):
        self.assertAlmostEqual(ui_layouts.GRID_SCALE * 98, 29 * 1162 / 320, places=6)
        self.assertEqual(ui_layouts.CELL, '{ "x": 98, "y": 94 }')

    def test_cube_title_sits_above_the_panel(self):
        t = """{ "children": [ { "type": "TextBoxWidget", "name": "title", "fields": { "rect": "$InGamePanelTitleRect", "text": "x" } },
            { "type": "ImageWidget", "name": "other", "fields": { "rect": "$InGamePanelTitleRect" } } ] }"""
        out = ui_layouts.set_title_rect(t, ui_layouts.rect(*ui_layouts.CUBE_TITLE))
        self.assertIn('"rect": { "x": 91, "y": -80, "width": 972, "height": 71 }, "text": "x"', out)
        self.assertEqual(out.count("$InGamePanelTitleRect"), 1)  # only the title widget moves
        self.assertLess(ui_layouts.CUBE_TITLE[1] + ui_layouts.CUBE_TITLE[3], 0)  # wholly above the picture

    def test_set_title_replaces_the_key_by_a_literal(self):
        t = """{ "children": [
            { "type": "TextBoxWidget", "name": "title",
              "fields": { "rect": "$InGamePanelTitleRect", "text": "@strpanel4", }, },
            { "type": "TextBoxWidget", "name": "gold_amount", "fields": { "text": "@other" } },
        ] }"""
        self.assertIn('"text": "Horadric Cube"', ui_layouts.set_title(t, "Horadric Cube"))
        self.assertIn('"text": ""', ui_layouts.set_title(t, ""))
        self.assertIn('"text": "@other"', ui_layouts.set_title(t, ""))
        self.assertNotIn("@strpanel4", ui_layouts.set_title(t, ""))
        with self.assertRaises(ValueError):
            ui_layouts.set_title('{ "name": "title", "fields": { } }', "x")

    def test_classic_skilltree_tab_titles_emptied_except_warlock(self):
        classes = ("Am", "So", "Ne", "Pa", "Ba", "Dr", "As", "Wa")
        lists = ",\n".join(f'"textTab{i}": [ ' + ", ".join(f'"@SkillCategory{c}{i + 1}"' for c in classes) + " ]" for i in range(3))
        text = ('{ "fields": { ' + lists + ', "cancelPositionCode": [ 321, 113, 131, 121, 313, 333, 231 ], }, '
                '"children": [ { "type": "TextBoxWidget", "name": "TextTab0" }, '
                '{ "name": "SkillChoicesRemaining", "fields": { "text": "@StrSklTree1 @StrSklTree2 @StrSklTree3" } }, '
                '{ "name": "Tab0", "fields": { "tooltipString": "@StrSklTreea" } } ] }')
        orig = ui_layouts.baseline
        ui_layouts.baseline = lambda name: text if name == "skillstreepanel.json" else orig(name)
        try:
            t = ui_layouts.skilltree_classic()
            self.assertNotIn("@SkillCategoryAm1", t)
            self.assertNotIn("@SkillCategoryAs3", t)
            self.assertEqual(t.count('""'), 21)
            for i, title in enumerate(("Demon", "Eldritch", "Chaos"), 1):   # Warlock's keys are written out too
                self.assertNotIn(f'"@SkillCategoryWa{i}"', t)
                self.assertIn(f'"{title}"', t)
            self.assertIn('"name": "TextTab0"', t)
            self.assertIn('"text": "Skill Choices Remaining"', t)    # a @key in a mod layout draws "Missing string"
            self.assertIn('"tooltipString": "Skill Tab 1"', t)
            ui_layouts.baseline = lambda name: text.replace("@StrSklTreea", "@unknownKey")
            with self.assertRaises(ValueError):
                ui_layouts.skilltree_classic()
            ui_layouts.baseline = lambda name: text.replace('"@SkillCategoryDr2"', '"x"')
            with self.assertRaises(ValueError):
                ui_layouts.skilltree_classic()
        finally:
            ui_layouts.baseline = orig

    def test_classic_skilltree_gets_a_warlock_cancel_position(self):   # bug #498: D2R's array stops at the Assassin
        t = '{ "cancelPositionX": [ 15, 100, 171 ],\n "cancelPositionCode": [ 321, 113, 131, 121, 313, 333, 231 ],\n }'
        out = ui_layouts.warlock_cancel_position(t)
        self.assertIn('"cancelPositionCode": [ 321, 113, 131, 121, 313, 333, 231, 131 ]', out)
        self.assertIn('"cancelPositionX": [ 15, 100, 171 ]', out)
        self.assertEqual(ui_layouts.warlock_cancel_position(out), out)   # 8 entries: left as it is
        with self.assertRaises(ValueError):
            ui_layouts.warlock_cancel_position('{ "cancelPositionCode": [ 1, 2 ] }')
        with self.assertRaises(ValueError):
            ui_layouts.warlock_cancel_position('{ }')

    def test_literalize_writes_every_at_key_out(self):
        t = '{ "a": { "tooltipString": "@strClose", "text": "@strGoldDrop" }, "b": { "text": "@strUiMenu2" }, "c": "plain" }'
        out = ui_layouts.literalize(t, "x.json")
        self.assertEqual(out, '{ "a": { "tooltipString": "Close", "text": "Drop Gold" }, "b": { "text": "Transmute" }, "c": "plain" }')
        with self.assertRaisesRegex(ValueError, "@neverHeardOfIt"):
            ui_layouts.literalize('{ "text": "@neverHeardOfIt" }', "x.json")

    def test_table_rows_and_slot_boxes(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "inventory.txt"
            cols = ["class", "invLeft", "gridX", "gridY"]
            for part in ui_layouts.SLOTS.values():
                cols += [f"{part}Left", f"{part}Right", f"{part}Top", f"{part}Bottom"]
            vals = ["Amazon", "320", "10", "6"] + ["340", "395", "31", "143"] * len(ui_layouts.SLOTS)
            p.write_text("\t".join(cols) + "\r\n" + "\t".join(vals) + "\r\n", "latin-1")
            row = ui_layouts.table_rows(p)["Amazon"]
            self.assertEqual((row["gridX"], row["gridY"]), (10, 6))
            self.assertEqual(ui_layouts.slot_boxes(row)["slot_head"], (20, 31, 75, 143))

    def test_check_cell_counts(self):
        self.assertEqual(ui_check.cell_counts(LAYOUT), [(10, 4)])
        self.assertEqual(ui_check.cell_counts('"cellCount": { "x": 3, "y": 4 }, "cellCount":{"x":10,"y":10}'), [(3, 4), (10, 10)])

    def test_grid_dims(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "inventory.txt"
            p.write_text("class\tgridX\tgridY\nAmazon\t10\t6\nExpansion\t\t\nHireling\t0\t0\n", "latin-1")
            self.assertEqual(ui_check.grid_dims(p), {"Amazon": (10, 6), "Hireling": (0, 0)})



class MedianTreeArtTests(unittest.TestCase):
    """skill_tree_art.median_page: the mod's classic page art in D2R's HD tree frame."""

    def page(self) -> Image.Image:
        im = Image.new("RGBA", (320, 432), (50, 50, 50, 255))
        for r in range(5):
            for c in (0, 2):
                x, y = skill_tree_art.CLASSIC_COL[c], skill_tree_art.CLASSIC_ROW[r]
                im.paste((200, 0, 0, 255), (x, y, x + 48, y + 48))                 # the box hole (red)
                im.paste((0, 0, 200, 255), (x + 44, y + 43, x + 59, y + 58))       # the level box (blue)
        return im

    def test_level_shift_points_at_d2r_box(self):
        dx, dy = skill_tree_art.level_shift()
        self.assertEqual((dx, dy), (10, -11))

    def test_level_boxes_move(self):
        cells = [(0, 0)]
        out = skill_tree_art.move_level_boxes(self.page(), cells)
        x, y = skill_tree_art.CLASSIC_COL[0], skill_tree_art.CLASSIC_ROW[0]
        dx, dy = skill_tree_art.level_shift()
        self.assertEqual(out.getpixel((x + 55 + dx, y + 50 + dy)), (0, 0, 200, 255))   # the box at its new place
        self.assertNotEqual(out.getpixel((x + 56, y + 57)), (0, 0, 200, 255))         # gone from the old corner
        self.assertEqual(out.getpixel((x + 20, y + 20)), (200, 0, 0, 255))            # the box hole stays

    def test_page_cells_land_on_d2r_cells(self):
        cells = [(r, c) for r in range(5) for c in (0, 2)]
        frame = skill_tree_art.median_page(self.page(), cells)
        self.assertEqual(frame.size, (skill_tree_art.FW, skill_tree_art.FH))
        for r, c in cells:   # the middle of each HD icon cell is the box hole's red
            x = skill_tree_art.SKILL_COL[c] - skill_tree_art.ORIGIN[0] + 65
            y = skill_tree_art.SKILL_ROW[r] - skill_tree_art.ORIGIN[1] + 65
            px = frame.getpixel((x, y))
            self.assertGreater(px[0], 150, (r, c, px))
            self.assertLess(px[2], 60, (r, c, px))
        self.assertEqual(frame.getpixel((5, 600))[3], 0)     # left of the page: transparent, D2R's stone shows
        self.assertEqual(frame.getpixel((450, 50))[3], 0)    # the tab strip's place: D2R's strip goes there
        self.assertEqual(frame.getpixel((450, 600))[3], 255)  # column 2's stone, stretched

    def test_median_pages_needs_columns_1_and_3(self):
        with tempfile.TemporaryDirectory() as t:
            orig = skill_tree_art.MOD_UI
            skill_tree_art.MOD_UI = Path(t)
            try:
                self.assertIsNone(skill_tree_art.median_pages("a", {1: {"S": (0, 0)}}, PAL))   # no DC6
                spells = Path(t) / "spells"
                spells.mkdir()
                tiles = [(w - x, h - y) for x, y, w, h in ui_art.TILES]
                frames = [(tw, th, 0, 0, flat_block(tw, th, 5)) for _s in range(4) for tw, th in tiles]
                (spells / "skltree_a_back.dc6").write_bytes(dc6.build_dc6(frames))
                self.assertIsNone(skill_tree_art.median_pages("a", {1: {"S": (0, 1)}}, PAL))   # column 2: not the mod's art
                got = skill_tree_art.median_pages("a", {1: {"S": (0, 0)}, 3: {"T": (4, 2)}}, PAL)
                self.assertEqual(len(got), 3)
                self.assertEqual(got[0].size, (skill_tree_art.FW, skill_tree_art.FH))
            finally:
                skill_tree_art.MOD_UI = orig

    def test_leftmost_tab_shows_page_3(self):
        self.assertEqual([skill_tree_art.page_of(t) for t in range(3)], [3, 2, 1])
        with tempfile.TemporaryDirectory() as t:
            orig = skill_tree_art.MOD_UI
            skill_tree_art.MOD_UI = Path(t)
            try:
                spells = Path(t) / "spells"
                spells.mkdir()
                tiles = [(w - x, h - y) for x, y, w, h in ui_art.TILES]
                frames = [(tw, th, 0, 0, flat_block(tw, th, 9 if s == 3 else 5)) for s in range(4) for tw, th in tiles]
                (spells / "skltree_a_back.dc6").write_bytes(dc6.build_dc6(frames))
                got = skill_tree_art.median_pages("a", {}, PAL)
                page3 = ui_art.panel_sets(spells / "skltree_a_back.dc6", PAL)[3]
                at = (skill_tree_art.SKILL_COL[0] - skill_tree_art.ORIGIN[0] - 20, 600)   # stone just left of column 1
                self.assertEqual(got[0].getpixel(at)[:3], page3.getpixel((5, 200))[:3])   # tab 0: set 3's art
                self.assertNotEqual(got[2].getpixel(at)[:3], got[0].getpixel(at)[:3])
            finally:
                skill_tree_art.MOD_UI = orig


if __name__ == "__main__":
    unittest.main()


class SkillTreeHdTests(unittest.TestCase):
    """skill_tree_hd (lane skillhd): the sharper page candidates, all behind an off switch."""

    def page(self) -> Image.Image:
        return MedianTreeArtTests.page(self)

    def test_switch_ships_off(self):
        import skill_tree_hd
        data = skill_tree_hd.load_switch()
        self.assertFalse(data.get("enabled"))
        self.assertEqual(skill_tree_hd.used_method(data), "lanczos")
        self.assertIn(data.get("method"), skill_tree_hd.METHODS)
        self.assertEqual(skill_tree_hd.used_method({"enabled": True, "method": "d2r"}), "d2r")
        self.assertEqual(skill_tree_hd.used_method(data, "rebuild"), "rebuild")   # a trial build
        with self.assertRaises(SystemExit):
            skill_tree_hd.used_method(data, "nope")

    def test_rebuild_edges_are_crisp(self):
        import numpy as np
        import skill_tree_hd
        im = Image.new("RGBA", (20, 20), (40, 40, 40, 255))
        im.paste((220, 30, 30, 255), (5, 5, 15, 15))
        lz = np.asarray(skill_tree_hd.lanczos(im, (53, 53)), np.int32)
        rb = np.asarray(skill_tree_hd.rebuild(im, (53, 53)), np.int32)
        ramp = lambda a: int(((a[26, :, 0] > 60) & (a[26, :, 0] < 200)).sum())  # noqa: E731  pixels between the two tones
        self.assertLess(ramp(rb), ramp(lz))
        self.assertLessEqual(ramp(rb), 4)
        self.assertEqual(tuple(rb[26, 26, :3]), (220, 30, 30))   # the colours are the page's
        self.assertEqual(tuple(rb[2, 2, :3]), (40, 40, 40))

    def test_candidates_keep_the_cells(self):
        import skill_tree_hd
        cells = [(r, c) for r in range(5) for c in (0, 2)]
        frame = skill_tree_art.hd_page("rebuild", self.page(), cells, None, None, [])
        self.assertEqual(frame.size, (skill_tree_art.FW, skill_tree_art.FH))
        for r, c in cells:
            x = skill_tree_art.SKILL_COL[c] - skill_tree_art.ORIGIN[0] + 65
            y = skill_tree_art.SKILL_ROW[r] - skill_tree_art.ORIGIN[1] + 65
            self.assertGreater(frame.getpixel((x, y))[0], 150)
        art = Image.new("RGBA", (skill_tree_art.FW, skill_tree_art.FH))
        dx = skill_tree_art.SKILL_COL[1] - skill_tree_art.SKILL_COL[0]
        x0, y0, x1, y1 = skill_tree_art.SOCKET_CROP
        art.paste((0, 0, 0, 120), (x0 + dx, y0, x1 + dx, y1))   # a stand-in socket where D2R's art has one
        arrows = [((r, 0), (r + 1, 0)) for r in range(4)]
        d2r = skill_tree_hd.d2r_page(art, cells, arrows, {(0, 0): (200, 0, 0)}, skill_tree_art)
        for r, c in cells:   # a socket on every cell, nothing between the columns
            cx, cy = skill_tree_art.cell_centre((r, c))
            self.assertGreater(d2r.getpixel((cx, cy))[3], 60)
        self.assertEqual(d2r.getpixel((450, 600))[3], 0)
        cx, cy = skill_tree_art.cell_centre((0, 0))
        rim = d2r.getpixel((cx, cy - skill_tree_art.SOCKET_HALF[1] + 1))
        self.assertGreater(rim[0], rim[2] + 50)   # the tree colour on the socket's rim
        cx2, _ = skill_tree_art.cell_centre((0, 2))
        self.assertGreater(d2r.getpixel((cx2 - 74 - 26, cy + 200))[3], 60)   # column 3 has no arrows: the passive frame

    def test_structure_skips_stone_spots(self):
        import skill_tree_hd
        im = self.page()
        im.paste((20, 20, 20, 255), (110, 400, 113, 403))   # a small dark spot on the stone
        x, y = skill_tree_art.CLASSIC_COL[0], skill_tree_art.CLASSIC_ROW[0]
        s = skill_tree_hd.structure(im, [(0, 0)], skill_tree_art.CLASSIC_COL, skill_tree_art.CLASSIC_ROW)
        self.assertTrue(s[y + 20, x + 20])        # the (saturated) box hole
        self.assertFalse(s[401, 111])
        self.assertFalse(s[200, 120])
