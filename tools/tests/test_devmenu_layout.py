"""The developer menu's generated panel header and the catalog exporter's pure parts (tools/devmenu_layout.py, tools/devmenu_catalog.py)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401
import devmenu_catalog as cat  # noqa: E402
import devmenu_layout as lay  # noqa: E402


class Layout(unittest.TestCase):
    def test_header_current(self):
        self.assertEqual(lay.HEADER.read_text("utf-8"), lay.header_text(), "run: py -3 -I tools/devmenu_layout.py header")

    def test_panels_are_strict_json_with_every_button(self):
        for mode in ("hd", "sd"):
            root = json.loads(json.dumps(lay.layout(mode)["root"]))
            self.assertEqual(root["name"], lay.PANEL)
            self.assertEqual(root["type"], "Panel")
            names = {c["name"] for c in root["children"]}
            self.assertIn(lay.INPUT, names)
            for i in range(lay.ROWS[mode]):
                self.assertIn(f"Btn_row{i}", names)
            for b in ("close", "prev", "next", "raise", "unlock", "quests", "confirm", "tab4", "cat6"):
                self.assertIn(f"Btn_{b}", names)

    def test_every_text_line_is_an_empty_text_box_before_the_arrows(self):
        for mode in ("hd", "sd"):
            children = lay.layout(mode)["root"]["children"]
            order = [c["name"] for c in children]
            wanted = [f"RowText{i}" for i in range(lay.ROWS[mode])] + ["HeaderText"] + [f"StatusText{i}" for i in range(lay.STATUS_LINES)]
            for name in wanted:
                child = next(c for c in children if c["name"] == name)
                self.assertEqual(child["type"], "TextBoxWidget")
                self.assertEqual(child["fields"]["text"], "")
                self.assertLess(order.index(name), order.index("Btn_row0"), "text boxes stay under the arrows")

    def test_text_lines_stay_inside_the_panel(self):
        for mode in ("hd", "sd"):
            built = lay.layout(mode)
            width, height = built["root"]["fields"]["rect"]["width"], built["root"]["fields"]["rect"]["height"]
            for child in built["root"]["children"]:
                if child["type"] == "TextBoxWidget" and child["name"].startswith(("RowText", "HeaderText", "StatusText")):
                    rect = child["fields"]["rect"]
                    self.assertLessEqual(rect["x"] + rect["width"], width, child["name"])
                    self.assertLessEqual(rect["y"] + rect["height"], height, child["name"])

    def test_warning_text_and_messages(self):
        self.assertIn("rewards not guaranteed", dict(lay.ACTIONS)["quests"])
        for i, name in enumerate(lay.BUTTONS):
            self.assertTrue(lay.message(name).endswith(f"DevMenuB_{i}"))


class Catalog(unittest.TestCase):
    def test_clean(self):
        self.assertEqual(cat.clean("ÿc4Laser  Focus"), "Laser Focus")
        self.assertEqual(cat.clean("Right Click to learn\nBook of Skill"), "Book of Skill")
        self.assertEqual(cat.clean("a\tb"), "a b")
        self.assertEqual(cat.clean(""), "")

    def test_native_records_skip_expansion(self):
        rows = [{"index": "A"}, {"index": "Expansion"}, {"index": "B"}, {"index": ""}]
        self.assertEqual([r["index"] for r in cat.native_records(rows)], ["A", "B"])

    def test_equiv_chain(self):
        types = {"amu": {"Equiv1": "misc", "Equiv2": ""}, "misc": {"Equiv1": "", "Equiv2": ""}}
        self.assertEqual(cat.equiv_chain(types, "amu"), {"amu", "misc"})

    def test_kit_base(self):
        types = {"tors": {"Equiv1": "armo", "Equiv2": ""}, "armo": {"Equiv1": "", "Equiv2": ""}, "swor": {"Equiv1": "", "Equiv2": ""}}
        cands = [(2, 3, 5, "big", "tors", "", 4), (2, 2, 9, "small", "tors", "", 3), (1, 3, 1, "sw", "swor", "", 6)]
        self.assertEqual(cat.kit_base(types, cands, ["tors"], [], 3), "small", "smallest area with enough sockets")
        self.assertEqual(cat.kit_base(types, cands, ["armo"], ["swor"], 4), "big")
        self.assertEqual(cat.kit_base(types, cands, ["tors"], [], 6), "big", "no base holds six: the most sockets")
        self.assertIsNone(cat.kit_base(types, cands, ["helm"], [], 1))

    def test_counts(self):
        self.assertEqual(cat.counts(["#devmenu\t1\ta", "I\tU\tx", "I\tU\ty", "L\t1"]), {"#devmenu": 1, "U": 2, "L": 1})

    def test_tables_of_a_sample(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "x.txt").write_text("a\tb\n1\t2\n\n", "utf-8")
            old = cat.EXCEL
            cat.EXCEL = Path(d)
            try:
                self.assertEqual(cat.table("x"), [{"a": "1", "b": "2"}])
            finally:
                cat.EXCEL = old


if __name__ == "__main__":
    unittest.main()
