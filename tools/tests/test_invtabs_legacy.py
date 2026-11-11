"""tools/invtabs_legacy.py: the classic panel geometry of an invtabs tab (sizes it takes and refuses), its layout, the
template for the page host and the classic inventory's button. Pure: no extraction needed.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_invtabs_legacy.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

import invtabs_legacy as il  # noqa: E402

THREE = (il.CHARMS, il.Tab("maps", "Maps", "Maps", "invbsc", 8, 5), il.Tab("potions", "Potions", "Potions", "invhp5", 4, 4))


def widgets(layout: dict) -> dict:
    return {c["name"]: c for c in layout["children"] if isinstance(c, dict)}


class Geometry(unittest.TestCase):
    def test_default_10x6(self):
        g = il.geometry(10, 6)
        self.assertEqual((g["grid"]["x"], g["grid"]["y"]), (16, 198))
        self.assertEqual(g["summary"]["lines"], 5)
        self.assertEqual(len(g["tabs"]["rects"]), il.MAX_TABS)

    def test_grid_ends_on_the_stash_bottom_line(self):
        for rows in range(1, il.max_rows() + 1):
            self.assertEqual(il.grid_origin(10, rows)[1] + rows * il.CELL, il.GRID_BOTTOM)

    def test_charminv_size_is_the_stash_grid(self):
        self.assertEqual(il.grid_origin(10, 4), (16, 256))   # 82 + 6 rows of 29: the stash's own cell lines

    def test_narrow_grids_are_centred(self):
        for cols in range(1, il.MAX_COLS + 1):
            x, _y = il.grid_origin(cols, 4)
            left, right = x - il.INNER_X0, il.INNER_X1 - (x + cols * il.CELL)
            self.assertLessEqual(abs(left - right), 1, cols)

    def test_twelve_tabs_fit_inside_the_frame(self):
        for rows in (1, 4, 6, il.max_rows()):
            x0, y, w, h = il.tab_rect(0, rows)
            x11, _y, _w, _h = il.tab_rect(il.MAX_TABS - 1, rows)
            self.assertGreaterEqual(x0, il.INNER_X0)
            self.assertLessEqual(x11 + w, il.INNER_X1)
            self.assertLess(il.summary_box(rows)[3], y)          # under the summary box
            self.assertLess(y + h, il.grid_origin(10, rows)[1] - il.LINE)  # above the grid's top line
        with self.assertRaises(ValueError):
            il.tab_rect(il.MAX_TABS, 6)

    def test_summary_lines_are_capped(self):
        self.assertEqual(il.summary_lines(1), il.MAX_SUMMARY_LINES)
        self.assertGreaterEqual(il.summary_lines(il.max_rows()), il.MIN_SUMMARY_LINES)

    def test_sizes_up_to_ten_columns_and_max_rows(self):
        self.assertEqual(il.max_rows(), 7)
        for cols in range(1, 11):
            for rows in range(1, il.max_rows() + 1):
                il.check_size(cols, rows)

    def test_refusals_name_the_reason(self):
        for cols, rows, words in ((11, 4, "10 columns"), (16, 16, "10 columns"), (10, 8, "7 rows"), (0, 3, "1 to 16"),
                                  (17, 1, "1 to 16"), (4, 17, "1 to 16")):
            with self.assertRaises(il.ClassicSizeError) as cm:
                il.check_size(cols, rows)
            self.assertIn(words, str(cm.exception))
            if cols <= 16 and rows <= 16 and cols and rows:
                self.assertIn("HD graphics only", str(cm.exception))

    def test_parse_grid(self):
        self.assertEqual(il.parse_grid("10x6"), (10, 6))
        self.assertEqual(il.parse_grid(" 4 X 3 "), (4, 3))
        with self.assertRaises(Exception):
            il.parse_grid("10,6")


class Layout(unittest.TestCase):
    def test_default_layout_checks_clean(self):
        for target in il.TARGETS.values():
            for tab in target.tabs:
                lay = il.panel_layout(target, tab)
                self.assertEqual(il.check_layout(lay, target, tab, target.tabs), [], target.name)

    def test_every_size_and_three_tabs_check_clean(self):
        for cols in (1, 3, 6, 10):
            for rows in range(1, il.max_rows() + 1):
                tab = il.Tab("charms", "Charms", "Charm Inventory", "invchm", cols, rows)
                tabs = (tab,) + THREE[1:]
                self.assertEqual(il.check_layout(il.panel_layout(il.INVTABS, tab, tabs), il.INVTABS, tab, tabs), [], (cols, rows))

    def test_names_and_messages(self):
        lay = il.panel_layout(il.INVTABS, THREE[1], THREE)
        self.assertEqual(lay["name"], "invtabs/Maps")
        w = widgets(lay)
        self.assertEqual(w["invtabs/Close"]["fields"]["onClickMessage"], "PanelManager:ClosePanel:invtabs/Maps")
        self.assertEqual(w["invtabs/Tab0"]["fields"]["onClickMessage"], "PanelManager:OpenPanel:invtabs/Charms")
        self.assertEqual((w["invtabs/Tab1"]["fields"]["normalFrame"], w["invtabs/Tab0"]["fields"]["normalFrame"]), (2, 0))
        self.assertEqual(w["invtabs/Background"]["fields"]["filename"], "PANEL\\invtabs_maps")
        self.assertEqual(w["invtabs/Grid"]["fields"]["cellCount"], {"x": 8, "y": 5})
        self.assertNotIn("invtabs/Tab3", w)  # only the tabs that exist

    def test_charminv_stand_in(self):
        tab = il.CHARMINV.tabs[0]
        lay = il.panel_layout(il.CHARMINV, tab)
        self.assertEqual(lay["name"], "charm-inv/CharmInvPanel")
        self.assertIn("charm-inv/InventoryGrid", widgets(lay))
        self.assertEqual(il.layout_rel(il.CHARMINV, tab).as_posix(), "global/ui/layouts/charm-inv/CharmInvPanel.json")
        self.assertEqual(il.layout_rel(il.INVTABS, il.CHARMS).as_posix(), "global/ui/layouts/invtabs/Charms.json")

    def test_no_at_keys_and_strict_json(self):
        text = il.layout_text(il.panel_layout(il.INVTABS, il.CHARMS, THREE))
        self.assertNotIn("@", text)
        json.loads(text)

    def test_template_has_the_host_placeholders(self):
        text = il.layout_text(il.panel_layout(il.INVTABS, il.CHARMS, THREE, template=True))
        self.assertIn('"name": "@PANEL@"', text)
        self.assertIn("PanelManager:ClosePanel:@PANEL@", text)
        self.assertIn("@GRID@", text)
        self.assertNotIn('"@GRID@"', text)  # unquoted: the host splices an object in
        grid = '{"type": "InventoryGridWidget", "name": "invtabs/Grid", "fields": {"rect": {"x": 16, "y": 198}}}'
        root = json.loads(text.replace("@PANEL@", "invtabs/Area0").replace("@GRID@", grid))
        self.assertEqual(root["name"], "invtabs/Area0")
        self.assertEqual(widgets(root)["invtabs/Tab1"]["fields"]["onClickMessage"], "PanelManager:OpenPanel:invtabs/Maps")

    def test_too_large_tab_is_refused_and_skipped(self):
        big = il.Tab("charms", "Charms", "Charm Inventory", "invchm", 16, 16)
        with self.assertRaises(il.ClassicSizeError):
            il.panel_layout(il.INVTABS, big)
        with tempfile.TemporaryDirectory() as d:
            lines = il.build(Path(d), il.INVTABS, (big,) + THREE[1:])
            self.assertIn("no classic layout", lines[0])
            self.assertFalse((Path(d) / il.layout_rel(il.INVTABS, big)).exists())
            self.assertTrue((Path(d) / il.layout_rel(il.INVTABS, THREE[1])).exists())
            self.assertEqual(il.check(Path(d), il.INVTABS, (big,) + THREE[1:], inventory=False), [])

    def test_check_finds_problems(self):
        lay = il.panel_layout(il.INVTABS, il.CHARMS)
        lay["children"] = [c for c in lay["children"] if c["name"] != "invtabs/Close"]
        widgets(lay)["invtabs/Grid"]["fields"]["cellCount"] = {"x": 9, "y": 6}
        widgets(lay)["invtabs/Summary0"]["fields"]["rect"]["x"] = 310
        problems = " | ".join(il.check_layout(lay, il.INVTABS, il.CHARMS, il.INVTABS.tabs))
        for words in ("close button", "cellCount", "leaves the 320 x 432 panel"):
            self.assertIn(words, problems)

    def test_tabs_without_a_classic_panel_leave_the_row(self):
        tabs = (il.CHARMS, il.Tab("maps", "Maps", "Maps", "invbsc", 16, 16), THREE[2])
        w = widgets(il.panel_layout(il.INVTABS, il.CHARMS, tabs))
        self.assertEqual(w["invtabs/Tab1"]["fields"]["onClickMessage"], "PanelManager:OpenPanel:invtabs/Potions")
        self.assertNotIn("invtabs/Tab2", w)
        self.assertEqual(il.check_layout(il.panel_layout(il.INVTABS, il.CHARMS, tabs), il.INVTABS, il.CHARMS, tabs), [])

    def test_too_many_tabs(self):
        tabs = tuple(il.Tab(f"t{i}", "T", "T") for i in range(il.MAX_TABS + 1))
        with self.assertRaises(ValueError):
            il.panel_layout(il.INVTABS, tabs[0], tabs)

    def test_bad_tab_id(self):
        with self.assertRaises(ValueError):
            il.Tab("Charms!", "C", "C")


class Button(unittest.TestCase):
    TEXT = ('{\n    "type": "Panel", "name": "PlayerInventoryExpansionLayout",\n    "children": [\n'
            '        {"type": "ButtonWidget", "name": "close", "fields": {"rect": {"x": 1, "y": 2}}},\n'
            '        {"type": "ButtonWidget", "name": "MxlSendStash", "fields": {"rect": {"x": 3, "y": 4}}},\n'
            '        {"type": "InventoryGridWidget", "name": "grid"}\n    ]\n}\n')

    def test_inserted_once_after_send_stash(self):
        out = il.add_button_to_layout(self.TEXT)
        self.assertEqual(il.add_button_to_layout(out), out)
        root = json.loads(out)
        names = [c["name"] for c in root["children"]]
        self.assertEqual(names, ["close", "MxlSendStash", il.BUTTON_NAME, "grid"])
        f = root["children"][2]["fields"]
        self.assertEqual(f["onClickMessage"], "PanelManager:TogglePanel:invtabs/Charms")
        self.assertEqual(f["filename"], "PANEL\\invtabs_button")

    def test_after_close_and_at_the_end(self):
        text = ('{"type": "Panel", "children": [\n    {"type": "InventoryGridWidget", "name": "grid"},\n'
                '    {"type": "ButtonWidget", "name": "close"}\n]}\n')
        root = json.loads(il.add_button_to_layout(text, il.CHARMINV).replace(",\n]", "\n]"))
        self.assertEqual(root["children"][-1]["fields"]["onClickMessage"], "PanelManager:TogglePanel:charm-inv/CharmInvPanel")

    def test_check_counts_the_button(self):
        with tempfile.TemporaryDirectory() as d:
            lay = Path(d) / "global" / "ui" / "layouts"
            lay.mkdir(parents=True)
            for n in il.CLASSIC_INVENTORY:
                (lay / n).write_text(il.add_button_to_layout(self.TEXT), "utf-8")
            (lay / il.HD_INVENTORY[0]).write_text(il.add_button_to_layout(self.TEXT), "utf-8")
            il.build(Path(d), il.INVTABS, il.INVTABS.tabs)
            problems = il.check(Path(d), il.INVTABS, il.INVTABS.tabs)
            self.assertEqual(len(problems), 1)
            self.assertIn("HD has its own button", problems[0])

    def test_it_goes_after_send_stash_in_the_built_classic_inventories(self):
        # ui_layouts.py writes the layouts without the button (tools/tests/test_charm_inventory.py); the build's `button`
        # step adds it for the charm inventory invtabs only
        import ui_layouts as ul
        try:
            texts = [ul.inventory_original(ul.table_rows()["Amazon"]), ul.inventory_expansion()]
        except (OSError, KeyError, SystemExit) as e:  # no D2R baseline layouts or no built inventory.txt here
            self.skipTest(f"ui_layouts inputs missing: {e}")
        for text in texts:
            self.assertNotIn(il.BUTTON_NAME, text)
            text = il.add_button_to_layout(text)
            self.assertEqual(text.count(f'"name": "{il.BUTTON_NAME}"'), 1)
            self.assertLess(text.index('"MxlSendStash'), text.index(il.BUTTON_NAME))

    def test_cli_geometry_refuses(self):
        self.assertEqual(il.main(["geometry", "--grid", "10x6"]), 0)
        self.assertEqual(il.main(["geometry", "--grid", "12x4"]), 1)


if __name__ == "__main__":
    unittest.main()
