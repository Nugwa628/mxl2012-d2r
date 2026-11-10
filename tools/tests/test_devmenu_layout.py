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
            wanted = [f"RowText{i}" for i in range(lay.ROWS[mode])] + [f"HeaderText{i}" for i in range(lay.HEADER_LINES)] + [f"StatusText{i}" for i in range(lay.STATUS_LINES)]
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

    def test_one_background_behind_everything(self):
        for mode in ("hd", "sd"):
            children = lay.layout(mode)["root"]["children"]
            self.assertEqual(children[0]["name"], "Background", "the background is the first child, so it draws under every other widget")
            self.assertEqual([c["name"] for c in children if c["name"].startswith("Background")], ["Background"], "one background, no stacked panels")
            for child in children:
                self.assertNotIn("Modal_BG", str(child["fields"].get("filename", "")), "no stacked modal art")

    def test_input_box_starts_native_editing(self):
        # a plain box: alwaysAcceptsKeyInput would keep D2R from entering its text editing state on a click (the plugin keeps the bindings off)
        for mode in ("hd", "sd"):
            box = next(c for c in lay.layout(mode)["root"]["children"] if c["name"] == lay.INPUT)
            self.assertNotIn("alwaysAcceptsKeyInput", box["fields"])
            self.assertFalse(box["fields"].get("focusOnMouseOver"), "the pointer passing over the box must not take the keyboard")

    def test_classic_panel_above_the_hud(self):
        built = lay.layout("sd")
        top = 300 + built["metrics"]["panelY"]
        self.assertGreaterEqual(top, 0)
        self.assertLessEqual(top + built["metrics"]["panelH"], 505, "the 800 x 600 HUD's orbs start below 505")

    def test_longest_page_line_fits_its_lines(self):
        longest = "Sure? Completes this difficulty's quests with the loader's cheat. REWARDS ARE NOT GUARANTEED."
        for mode in ("hd", "sd"):
            metrics = lay.layout(mode)["metrics"]
            self.assertLessEqual(len(longest), metrics["headerChars"] * lay.HEADER_LINES, mode)

    def test_warning_text_and_messages(self):
        self.assertTrue(dict(lay.ACTIONS)["quests"].startswith("Advanced"))
        # the warning is the Quests tab's page line, shown right under the button, and Confirm's
        source = (lay.ROOT / "plugin" / "src" / "devmenu.cpp").read_text("utf-8")
        self.assertIn("Rewards are not guaranteed.", source)
        self.assertIn("REWARDS ARE NOT GUARANTEED.", source)
        for i, name in enumerate(lay.BUTTONS):
            self.assertTrue(lay.message(name).endswith(f"DevMenuB_{i}"))


def _children(mode):
    return {c["name"]: c for c in lay.layout(mode)["root"]["children"]}


def _boxes(mode, prefix):
    kids = _children(mode)
    return [lay.widget_box(mode, kids[n]) for n in sorted((n for n in kids if n.startswith(prefix)), key=lambda n: int(n[len(prefix):]))]


# Rows as the plugin writes them (devmenu.cpp, devmenu_logic.h UberRowText): the longest of the built catalog of 2026-11-10
LONG_ROWS = ["Cathedral of Vanity (Underground Passage Level 1)", "Welcome to Old Bremmtown (Arreat Plateau portal)",
             "Cornerstone of the World: APF-10 'Maelstrom' MkIV (Assassin)", "Cornerstone of the World: Symphony of Destruction (Paladin)",
             "[Kit] Secret Jewel Bonus!: base + 2 runes, socket in order",
             "Welcome to Old Bremmtown  (Act 5)  [map only, the fight needs its normal summon]"]


class Geometry(unittest.TestCase):
    """The panel's geometry: labels on one line, symmetric button rows, rows that fit, and the panel on the screen."""

    def test_tab_category_and_action_labels_fit_on_one_line(self):
        for mode in ("hd", "sd"):
            for name, child in _children(mode).items():
                if child["type"] == "ButtonWidget" and "textString" in child["fields"]:
                    _x, _y, w, _h = lay.widget_box(mode, child)
                    self.assertLessEqual(lay.label_width(mode, child), w * lay.BUTTON_TEXT_SHARE, f"{mode} {name}: {child['fields']['textString']!r}")

    def test_multi_frame_buttons_have_a_size(self):
        # a multi-frame classic button takes no size from its art: without one its label wrapped after every letter
        for mode in ("hd", "sd"):
            for name, child in _children(mode).items():
                if child["fields"].get("multiFrame"):
                    self.assertIn("width", child["fields"]["rect"], f"{mode} {name}")
                    self.assertIn("height", child["fields"]["rect"], f"{mode} {name}")

    def test_button_rows_are_even_and_centred(self):
        for mode in ("hd", "sd"):
            width = lay.layout(mode)["metrics"]["panelW"]
            for prefix in ("Btn_tab", "Btn_cat"):
                boxes = _boxes(mode, prefix)
                self.assertEqual(len({(b[2], b[3], b[1]) for b in boxes}), 1, f"{mode} {prefix}: one size, one line")
                gaps = {boxes[i + 1][0] - (boxes[i][0] + boxes[i][2]) for i in range(len(boxes) - 1)}
                self.assertEqual(len(gaps), 1, f"{mode} {prefix}: equal gaps")
                self.assertGreater(min(gaps), 0, f"{mode} {prefix}: buttons do not touch")
                left, right = boxes[0][0], width - (boxes[-1][0] + boxes[-1][2])
                self.assertLessEqual(abs(left - right), 1, f"{mode} {prefix}: centred ({left} / {right})")
            kids = _children(mode)
            first, last = lay.widget_box(mode, kids["Btn_row0"]), lay.widget_box(mode, kids["Btn_next"])
            self.assertEqual(first[0], width - (last[0] + last[2]), f"{mode}: page arrows as far from either edge")

    def test_search_label_has_its_full_width(self):
        per_char = {"hd": 19.5, "sd": lay.SD_CHAR["8pt"]}  # HD MediumFontSize: "Search / leve" measured 13 characters in 250 units
        for mode in ("hd", "sd"):
            kids = _children(mode)
            lx, _ly, lw, _lh = lay.widget_box(mode, kids["InputLabel"])
            self.assertGreaterEqual(lw, len("Search / level") * per_char[mode], mode)
            frame = kids["InputSlot" if mode == "hd" else "InputFrame"]
            fx, _fy, fw, _fh = lay.widget_box(mode, frame)
            self.assertLessEqual(lx + lw, fx, f"{mode}: the box starts after the label")
            self.assertEqual(kids["InputLabel"]["fields"]["style"]["alignment"]["h"], "right", f"{mode}: the label ends at the box")
            width = lay.layout(mode)["metrics"]["panelW"]
            self.assertLessEqual(abs(lx - (width - (fx + fw))), 1, f"{mode}: label and box centred as one group")
            bx, _by, bw, _bh = lay.widget_box(mode, kids[lay.INPUT])
            self.assertTrue(fx <= bx and bx + bw <= fx + fw, f"{mode}: the text box inside its frame")

    def test_sections_do_not_overlap(self):
        for mode in ("hd", "sd"):
            built = lay.layout(mode)
            m, kids = built["metrics"], _children(mode)
            bottom = lambda name: lay.widget_box(mode, kids[name])[1] + lay.widget_box(mode, kids[name])[3]  # noqa: E731
            top = lambda name: lay.widget_box(mode, kids[name])[1]  # noqa: E731
            self.assertLessEqual(bottom("Title"), top("Btn_tab0") + 4, mode)
            self.assertLess(bottom("Btn_tab0"), top("InputLabel"), mode)
            self.assertLess(bottom("InputSlot" if mode == "hd" else "InputFrame"), top("Btn_cat0"), mode)
            self.assertLess(bottom("Btn_cat0"), m["rowY"], mode)
            self.assertLessEqual(m["rowY"] + m["rows"] * m["rowPitch"], m["headerY"], mode)
            self.assertLessEqual(bottom("Btn_prev"), m["statusY"] + 4, mode)
            self.assertLessEqual(m["headerY"] + lay.HEADER_LINES * kids["HeaderText0"]["fields"]["rect"]["height"], m["statusY"], mode)
            inner_bottom = m["panelH"] - (round(68 * lay.HD_BG_SCALE) if mode == "hd" else 2)  # HD: above the art's bottom frame
            self.assertLessEqual(m["statusY"] + lay.STATUS_LINES * kids["StatusText0"]["fields"]["rect"]["height"], inner_bottom, mode)
            self.assertLessEqual(bottom("Btn_confirm"), m["headerY"], f"{mode}: the actions above the page line")
            self.assertLessEqual(bottom("Btn_quests"), top("Btn_confirm"), mode)

    def test_every_widget_inside_the_panel(self):
        for mode in ("hd", "sd"):
            m = lay.layout(mode)["metrics"]
            for name, child in _children(mode).items():
                if name == "ClickCatcher":
                    continue
                x, y, w, h = lay.widget_box(mode, child)
                self.assertTrue(x >= 0 and y >= 0 and x + w <= m["panelW"] + 1 and y + h <= m["panelH"] + 1, f"{mode} {name}: {(x, y, w, h)}")

    def test_longest_rows_fit_one_line(self):
        for mode in ("hd", "sd"):
            m = lay.layout(mode)["metrics"]
            for text in LONG_ROWS:
                self.assertLessEqual(len(text), m["rowChars"], f"{mode}: {text}")

    def test_built_catalog_rows_fit_one_line(self):
        path = lay.ROOT / "work" / "mod" / "data" / "mxl2012-devmenu" / "catalog.tsv"
        if not path.exists():
            self.skipTest("no built catalog (tools/build.py)")
        cols = [ln.split("\t") for ln in path.read_text("utf-8").splitlines() if not ln.startswith("#")]
        levels = {c[1]: c for c in cols if c[0] == "L"}
        notes = {"0": "", "1": "  [map only, the fight needs its normal summon]", "2": "  [portal area]"}
        texts = [c[6] + (f"  ({c[7]})" if len(c) > 7 and c[7] else "") for c in cols if c[0] == "I"]
        texts += [f"{c[5]}  (Act {int(c[2]) + 1}){notes[c[3]]}" for c in levels.values()]
        texts += [f"{c[4]} ({levels[c[2]][5] if c[2] in levels else 'level ' + c[2]}{' portal)' if c[3] == '1' else ')'}" for c in cols if c[0] == "U"]
        texts += [f"[Kit] {c[4]}: base + {len(c[3].split(','))} runes, socket in order" for c in cols if c[0] == "K"]
        longest = max(texts, key=len)
        for mode in ("hd", "sd"):
            self.assertLessEqual(len(longest), lay.layout(mode)["metrics"]["rowChars"], f"{mode}: {longest}")

    def test_panel_fits_1280x720_and_1600x900(self):
        # HD UI units: the screen is 2160 high and (16:9) 3840 wide at both sizes; the side panels end at y 1833, so does the menu
        for w, h in ((1280, 720), (1600, 900)):
            m = lay.layout("hd")["metrics"]
            units_w = 2160 * w / h
            left, top = units_w / 2 + m["panelX"], 1080 + m["panelY"]
            self.assertTrue(left >= 0 and left + m["panelW"] <= units_w, (w, h))
            self.assertTrue(top >= 0 and top + m["panelH"] <= 1834, (w, h))
            # classic: the 800 x 600 picture, scaled to fit the window
            s = lay.layout("sd")["metrics"]
            self.assertTrue(400 + s["panelX"] >= 0 and 400 + s["panelX"] + s["panelW"] <= 800, (w, h))
            self.assertGreaterEqual(400 + s["panelX"], 20, "the classic side strips stay free for the checks (devmenu_checks.strips)")


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

    def test_uber_levels_and_their_entry_areas(self):
        names = {"Cave2Tr": "Duncraig", "Tomb1Tr": "Fauztinville", "Hell1": "Welcome to Toraja", "Cave2": "Cave Level 1",
                 "ToDanger": cat.UBER_WARP_TEXT, "ToCave2": "To The Cave Level 1"}.get

        def level(lid, name, warp, *vis):
            row = {"Id": str(lid), "Name": "row" + str(lid), "LevelName": name, "LevelWarp": warp}
            row.update({f"Vis{i}": str(v) for i, v in enumerate(vis)})
            return row

        levels = [level(9, "Cave2", "ToCave2", 3, 13), level(13, "Cave2Tr", "ToDanger", 9), level(59, "Tomb1Tr", "ToDanger", 55),
                  level(125, "Hell1", "ToDanger")]
        self.assertEqual(cat.uber_entries(levels, lambda ref: names(ref, "")),
                         [(13, 9, 0, "Duncraig"), (59, 55, 0, "Fauztinville"), (125, 111, 1, "Welcome to Toraja")],
                         "only levels whose entrance says DANGER; the entry is the Vis link or the red portal's level")
        with self.assertRaises(SystemExit):
            cat.uber_entries([level(77, "Tomb1Tr", "ToDanger")], lambda ref: names(ref, ""))

    def test_built_catalog_lists_every_uber_level(self):
        built = cat.ROOT / "work" / "mod" / "data" / "mxl2012-devmenu" / "catalog.tsv"
        if not built.exists():
            self.skipTest("no built catalog (tools/build.py)")
        lines = [ln.split("\t") for ln in built.read_text("utf-8").splitlines()]
        ubers = {int(f[1]): (int(f[2]), f[4]) for f in lines if f[0] == "U"}
        levels = {int(f[1]) for f in lines if f[0] == "L"}
        self.assertEqual(ubers[59], (55, "Fauztinville"))
        self.assertEqual(ubers[60], (57, "Tran Athulua"))
        self.assertEqual(ubers[125], (111, "Welcome to Toraja"))
        self.assertEqual(len(ubers), 16)
        self.assertTrue(all(entry in levels and entry not in ubers for entry, _ in ubers.values()), "every entry is an ordinary area")

    def test_skill_label(self):
        self.assertEqual(cat.skill_label("Cornerstone of the World", ("Ghost Arrow", "Amazon")), "Cornerstone of the World: Ghost Arrow (Amazon)")
        self.assertEqual(cat.skill_label("Cornerstone of the World", ("Lava Pit", "")), "Cornerstone of the World: Lava Pit")

    def test_row_skill(self):
        skills = {"301": ("Ghost Arrow", "Amazon"), "ghost arrow": ("Ghost Arrow", "Amazon")}
        self.assertEqual(cat.row_skill({"prop1": "oskill", "par1": "301", "prop2": "levelreq"}, skills), ("Ghost Arrow", "Amazon"))
        self.assertIsNone(cat.row_skill({"prop1": "oskill", "par1": "301", "prop2": "oskill", "par2": "302"}, skills), "two skills: no single skill")
        self.assertIsNone(cat.row_skill({"prop1": "str", "par1": ""}, skills))

    def test_cornerstone_rows_listed_by_skill(self):
        with tempfile.TemporaryDirectory() as d:
            head = "index\tspawnable\tdisabled\tcode\tprop1\tpar1\tprop2\tpar2\n"
            (Path(d) / "uniqueitems.txt").write_text(head +
                                                    "Stone\t1\t\tjew\toskill\t301\tlevelreq\t\n"
                                                    "Expansion\t\t\t\t\t\t\t\n"
                                                    "Stone\t1\t\tjew\toskill\t64\t\t\n"
                                                    "Stone\t\t\tjew\toskill\t65\t\t\n"
                                                    "Ring\t1\t\trin\toskill\t301\t\t\n", "utf-8")
            old = cat.EXCEL
            cat.EXCEL = Path(d)
            try:
                names = lambda ref: {"Stone": "Cornerstone of the World", "Ring": "Archer's Ring"}.get(ref, "")
                bases = {"jew": ("jewl", "", 1, 1), "rin": ("ring", "", 1, 1)}
                skills = {"301": ("Ghost Arrow", "Amazon"), "64": ("Frozen Orb", "Sorceress"), "65": ("Hidden", "Sorceress")}
                lines = cat.collect_uniques(names, {}, bases, skills)
            finally:
                cat.EXCEL = old
        self.assertEqual(lines, ["I\tU\tjew\t7\t0\t0\tCornerstone of the World: Ghost Arrow (Amazon)",
                                 "I\tU\tjew\t7\t1\t0\tCornerstone of the World: Frozen Orb (Sorceress)",
                                 "I\tU\trin\t7\t3\t0\tArcher's Ring"],
                         "one row per skill with its native row id; a row not spawnable in the mod is left out; a unique name is not relabelled")

    def test_max_sockets(self):
        sword = {"MaxSockets1": "3", "MaxSocketsLevelThreshold1": "25", "MaxSockets2": "4", "MaxSocketsLevelThreshold2": "40", "MaxSockets3": "6"}
        self.assertEqual(cat.max_sockets(sword, "6", 99), 6, "high item level: the third column")
        self.assertEqual(cat.max_sockets(sword, "6", 30), 4, "item level 26-40: the second column")
        self.assertEqual(cat.max_sockets(sword, "6", 25), 3, "item level up to 25: the first column")
        self.assertEqual(cat.max_sockets(sword, "2", 99), 2, "never more than the base's own gemsockets")
        ring = {"MaxSockets1": "0", "MaxSockets2": "0", "MaxSockets3": "0", "MaxSocketsLevelThreshold1": "25", "MaxSocketsLevelThreshold2": "40"}
        self.assertEqual(cat.max_sockets(ring, "1", 99), 0, "a type without sockets")
        self.assertEqual(cat.max_sockets(sword, "", 99), 0, "a base without gemsockets")
        self.assertEqual(cat.max_sockets(None, "6", 99), 0, "an unknown type")

    def test_sample_items_get_their_sockets(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "weapons.txt").write_text("name\tcode\tnamestr\ttype\tgemsockets\nShort Sword\tssd\tssd\tswor\t2\nGiant Sword\tgis\tgis\tswor\t6\n", "utf-8")
            (Path(d) / "armor.txt").write_text("name\tcode\tnamestr\ttype\tgemsockets\nLarge Shield\tlrg\tlrg\tshie\t4\n", "utf-8")
            (Path(d) / "misc.txt").write_text("name\tcode\tnamestr\ttype\tgemsockets\nRing\trin\trin\tring\t1\nHoradric Cube\tbox\tbox\tbox\t0\n", "utf-8")
            six = {"MaxSockets1": "6", "MaxSockets2": "6", "MaxSockets3": "6", "MaxSocketsLevelThreshold1": "25", "MaxSocketsLevelThreshold2": "40"}
            none = {"MaxSockets1": "0", "MaxSockets2": "0", "MaxSockets3": "0", "MaxSocketsLevelThreshold1": "25", "MaxSocketsLevelThreshold2": "40"}
            types = {"swor": six, "shie": six, "ring": none, "box": none}
            names = {"ssd": "Short Sword", "gis": "Giant Sword", "lrg": "Large Shield", "rin": "Ring", "box": "Horadric Cube"}.get
            old = cat.EXCEL
            cat.EXCEL = Path(d)
            try:
                bases = cat.collect_bases(names, types)
                misc = cat.collect_misc(names, types)
            finally:
                cat.EXCEL = old
        self.assertEqual(bases, ["I\tB\tlrg\t0\t-1\t4\tLarge Shield", "I\tB\tssd\t0\t-1\t2\tShort Sword", "I\tB\tgis\t0\t-1\t6\tGiant Sword"])
        self.assertEqual(misc, ["I\tQ\trin\t0\t-1\t0\tRing", "I\tQ\tbox\t0\t-1\t0\tHoradric Cube"])

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
