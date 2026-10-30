"""tools/text_audit.py (docs/text-audit.md): what a player reads, and the failure when a key, a placeholder or nothing shows."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import strings_check  # noqa: E402
import text_audit as ta  # noqa: E402


def write_table(folder: Path, name: str, head: list[str], rows: list[list[str]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.txt").write_text("\n".join("\t".join(r) for r in [head, *rows]) + "\n", encoding="utf-8")


STRINGS = ta.Strings(
    {"Zombie": "Zombie", "Bunny": "Bunny", "CouatlInhibitor": "CouatlInhibitor", "Couatl Inhibitor": "Couatl Inhibitor",
     "btor": "btor", "Torch": "Torch", "blah": "blah", "x": "x", "Empty": "", "Blank": "  ", "Bad": "Missing string",
     "Camel": "SnakeCase_Word", "fissure": "fissure", "To The Pandemonium Run 1": "To The Pandemonium Run 1", "Sword": "Sword",
     "NoDesc": "", "strClose": "Close", "Quoted": "ÿc4CrystalBall", "Warn": "Do Not Use Ethereal Items Idiot",
     "mxl2012Echo": "mxl2012:Foo", "Tidy": "ÿc4Tidy Name"},
    own={"CouatlInhibitor", "Couatl Inhibitor", "btor", "Torch", "blah", "x", "Empty", "Blank", "Bad", "Camel", "Bunny",
         "To The Pandemonium Run 1", "NoDesc", "Quoted", "Warn", "mxl2012Echo", "Tidy"})


class KeyLike(unittest.TestCase):
    def test_words_are_not_keys(self):
        for text, key in (("Bunny", "Bunny"), ("Couatl Inhibitor", "CouatlInhibitor"), ("To The Pandemonium Run 1", "To The Pandemonium Run 1"),
                          ("ÿc4Tidy Name", "Tidy"), ("Zoo", "Zoo"), ("Pandora", "Pandora"), ("Dawn", "Dawn"), ("", "x")):
            self.assertFalse(ta.key_like(text, key), text)

    def test_key_shapes(self):
        for text, key in (("CouatlInhibitor", "CouatlInhibitor"), ("btor", "btor"), ("burninglogs", "burninglogs"),
                          ("snake_case", "z"), ("DesertShrineArmor", "q"), ("mxl2012:Foo", "Foo"), ("d2r:Bar", "Bar"),
                          ("ÿc4CrystalBall", "k")):
            self.assertTrue(ta.key_like(text, key), text)

    def test_a_lowercase_word_that_is_not_its_key_is_fine(self):
        self.assertFalse(ta.key_like("orb", "x01"))

    def test_placeholders(self):
        for t in ("blah", "x", "XX", "TBD", "Not used", "ÿc1todo", "???", "..."):
            self.assertTrue(ta.is_placeholder(t), t)
        for t in ("Do Not Use Ethereal Items Idiot", "Box", "Xorn", "Location: ???\nUnknown"):
            self.assertFalse(ta.is_placeholder(t), t)


class Tables(unittest.TestCase):
    def audit(self, tables: dict, allow=None, layouts=None, strings=STRINGS, words=False):
        # the shared STRINGS hold key-shaped texts on purpose; the text-words pass has its own tests (TextWords)
        with tempfile.TemporaryDirectory() as d:
            excel = Path(d) / "excel"
            for (bank, name), (head, rows) in tables.items():
                write_table(excel / bank if bank else excel, name, head, rows)
            found, report = ta.audit(excel, strings, layouts, allow=allow if allow is not None else [])
            return [f for f in found if words or f.kind != "text-words"], report

    def kinds(self, tables, **kw):
        found, _ = self.audit(tables, **kw)
        return sorted((f.kind, f.key) for f in found)

    def test_a_key_shaped_name_is_found_in_both_banks(self):
        t = {("", "monstats"): (["Id", "NameStr", "enabled", "Code"], [["a", "mxl2012:CouatlInhibitor", "1", "AA"], ["b", "Zombie", "1", "ZZ"]]),
             ("base", "objects"): (["Class", "Name", "Selectable0"], [["Torch", "btor", "0"]])}
        found, _ = self.audit(t)
        self.assertEqual([(f.kind, f.where.split()[0], f.key) for f in found],
                         [("key-text", "rotw", "CouatlInhibitor"), ("key-text", "base", "btor")])

    def test_missing_key_and_missing_string(self):
        t = {("", "misc"): (["namestr", "invfile"], [["NoSuchKey", "inv"], ["Bad", "inv"]])}
        self.assertEqual(self.kinds(t), [("missing-key", "NoSuchKey"), ("missing-string", "Bad")])

    def test_placeholder_text_only_for_the_mods_own_keys(self):
        t = {("", "misc"): (["namestr", "invfile"], [["x", "inv"], ["blah", "inv"]])}
        self.assertEqual(self.kinds(t), [("placeholder", "blah"), ("placeholder", "x")])
        theirs = ta.Strings({"x": "x", "Sword": "Sword"}, own=set())
        self.assertEqual(self.kinds(t, strings=theirs), [("missing-key", "blah")])  # D2R's own x is D2R's business

    def test_d2r_own_lowercase_text_is_left_alone(self):
        t = {("", "objects"): (["Class", "Name", "Selectable0"], [["Fissure", "fissure", "0"]])}
        self.assertEqual(self.kinds(t), [])

    def test_empty_names_where_there_is_art(self):
        t = {("", "misc"): (["namestr", "invfile"], [["Empty", "invbig"], ["Empty", ""], ["", "invbig"], ["Blank", "invbig"]]),
             ("", "monstats"): (["Id", "NameStr", "enabled", "Code"], [["a", "", "1", "AA"], ["b", "", "0", "BB"], ["c", "", "1", ""],
                                                                    ["d", "mxl2012:Empty", "1", "DD"]]),
             ("", "skilldesc"): (["skilldesc", "IconCel", "str name"], [["s1", "3", ""], ["s2", "", ""], ["s3", "4", "mxl2012:Empty"]]),
             ("", "objects"): (["Class", "Name", "Selectable0", "Selectable1"], [["O1", "", "1", "0"], ["O2", "", "0", "0"]])}
        found, _ = self.audit(t)
        self.assertEqual(sorted((f.table, f.where.split()[-1]) for f in found if f.kind == "empty-name"),
                         [("misc", "2"), ("misc", "4"), ("misc", "5"), ("monstats", "2"), ("monstats", "5"), ("objects", "2"),
                          ("skilldesc", "2"), ("skilldesc", "4")])

    def test_magic_affixes_with_an_empty_name_are_median_design(self):
        t = {("", "magicprefix"): (["Name"], [["mxl2012:NoDesc"], ["mxl2012:NoDesc"]]),
             ("", "magicsuffix"): (["Name"], [["mxl2012:NoDesc"]])}
        found, report = self.audit(t)
        self.assertEqual(found, [])
        self.assertTrue(any("magicprefix: 2 names" in r for r in report))
        self.assertTrue(any("magicsuffix: 1 names" in r for r in report))

    def test_label_columns_and_the_object_placeholders_are_skipped(self):
        t = {("", "automagic"): (["Name"], [["sockNormal"]]),
             ("", "objects"): (["Class", "Name", "Selectable0"], [["D", "dummy_12", "1"]])}
        self.assertEqual(self.kinds(t), [])

    def test_allow_list_suppresses_and_a_stale_row_fails(self):
        t = {("", "objects"): (["Class", "Name", "Selectable0"], [["Torch", "mxl2012:btor", "0"]])}
        row = {"kind": "key-text", "table": "objects", "column": "Name", "key": "btor", "reason": "kept"}
        found, report = self.audit(t, allow=[row])
        self.assertEqual(found, [])
        self.assertTrue(any("allowed: " in r and "kept" in r for r in report))
        stale = dict(row, key="gone")
        found, _ = self.audit(t, allow=[stale])
        self.assertEqual([f.kind for f in found], ["key-text", "stale-allow"])

    def test_committed_allow_list_is_well_formed(self):
        for r in ta.load_allow():
            self.assertTrue(r["reason"].strip(), r)
            self.assertIn(r["kind"], {"key-text", "placeholder", "empty-name", "missing-key", "missing-string", "layout-at-key",
                                       "skill-name", "rune-letter", "text-words"})


class TextWords(unittest.TestCase):
    """Kind text-words (lane unporteda): a key named inside a text's own words is drawn as it is."""
    def test_keys_inside_the_words(self):
        found = {f.key: f.text for f in ta.audit_text_words(STRINGS)}
        self.assertEqual(found.get("bad"), "Missing string")
        self.assertEqual(found.get("camel"), "SnakeCase_Word")
        self.assertEqual(found.get("mxl2012echo"), "mxl2012:Foo")
        for key in ("bunny", "warn", "to the pandemonium run 1", "tidy", "torch"):
            self.assertNotIn(key, found)

    def test_only_the_mods_own_texts(self):
        s = ta.Strings({"Zed": "zed_word", "Own": "Fine words"}, own={"Own"})
        self.assertEqual(ta.audit_text_words(s), [])

    def test_a_texts_own_key_is_not_flagged(self):
        s = ta.Strings({"CrystalBall": "CrystalBall"}, own={"CrystalBall"})
        self.assertEqual(ta.audit_text_words(s), [])


class StatLines(unittest.TestCase):
    """Bug #140: a property line that prints D2R's `dummy` text (the Buffalo line)."""
    ISC = (["Stat", "*ID", "descfunc", "descstrpos", "descstrneg"],
           [["item_nonclassskill", "97", "28", "", ""], ["item_singleskill", "107", "27", "ItemModifierClassSkill", "ItemModifierClassSkill"],
            ["item_addclassskills", "83", "13", "", ""], ["hpregen", "74", "", "", ""]])
    PROPS = (["code", "*Id", "func1", "stat1"], [["oskill", "247", "22", "item_nonclassskill"], ["skill", "123", "22", "item_singleskill"]])
    SKILLS = (["skill", "*Id", "skilldesc"], [["Attack", "0", "attack"], ["Pyroclastic Flow", "1", "pyro"], ["Hidden", "2", ""],
                                             ["Blank", "3", "blank"]])
    DESC = (["skilldesc", "str name"], [["attack", "Bunny"], ["pyro", "Sword"], ["blank", ""]])

    def found(self, isc=ISC, uniques=None):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            for name, (head, rows) in (("itemstatcost", isc), ("properties", self.PROPS), ("skills", self.SKILLS),
                                       ("skilldesc", self.DESC), ("uniqueitems", uniques or (["index", "prop1", "par1", "min1", "max1"], []))):
                write_table(f, name, head, rows)
            return sorted((x.kind, x.column, x.key, x.text) for x in ta.audit_stat_lines(f, "rotw", STRINGS))

    def test_a_format_cell_left_blank_is_found_but_not_for_own_text_functions(self):
        self.assertEqual([(k, c, key) for k, c, key, _ in self.found()],
                         [("stat-format", "descstrneg", "item_nonclassskill"), ("stat-format", "descstrpos", "item_nonclassskill")])

    def test_a_property_naming_a_skill_without_a_name(self):
        u = (["index", "prop1", "par1", "min1", "max1", "prop2", "par2", "min2", "max2"],
             [["Good", "oskill", "1", "3", "3", "skill", "Pyroclastic Flow", "1", "1"],
              ["Bad", "oskill", "2", "3", "3", "oskill", "Fire Ball", "1", "1"], ["Worse", "skill", "3", "1", "1", "oskill", "", "1", "1"]])
        hits = [(c, key, t) for k, c, key, t in self.found(uniques=u) if k == "skill-name"]
        # a name no table has and a blank cell are skill 0 in both games (bug #180), and Attack reads "Bunny": no finding
        self.assertEqual(hits, [("prop1", "oskill 2", "skill 'Hidden': no skilldesc"), ("prop1", "skill 3", "skill 'Blank': blank str name")])

    def test_the_parameter_is_read_as_the_loaders_read_it(self):
        """Bug #180: 1.14d 0x6336a0 / D2R 0x320310: atoi, else skills / montype / states name, else 0."""
        u = (["index", "prop1", "par1", "min1", "max1"],
             [["Num", "oskill", "3abc", "1", "1"], ["Mon", "oskill", "Undead", "1", "1"], ["State", "oskill", "Frozen", "1", "1"],
              ["None", "oskill", "Fire Ball", "1", "1"], ["Neg", "oskill", "-1", "1", "1"]])
        extra = {"montype": (["type"], [["demon"], ["undead"]]), "states": (["state"], [["none"], ["freeze"], ["frozen"]])}
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            for name, (head, rows) in (("itemstatcost", self.ISC), ("properties", self.PROPS), ("skills", self.SKILLS),
                                       ("skilldesc", self.DESC), ("uniqueitems", u), *extra.items()):
                write_table(f, name, head, rows)
            hits = sorted((x.key, x.text) for x in ta.audit_stat_lines(f, "rotw", STRINGS) if x.kind == "skill-name")
        # Undead -> montype 1 = Pyroclastic Flow (readable); Fire Ball -> 0 = Attack (readable)
        self.assertEqual(hits, [("oskill -1", "no skills row"), ("oskill 3abc", "skill 'Blank': blank str name"),
                                ("oskill Frozen", "a states name, read as 2: skill 'Hidden': no skilldesc")])

    def test_a_name_read_as_skill_0_is_found_when_skill_0_has_no_name(self):
        skills = (["skill", "*Id", "skilldesc"], [["Attack", "0", ""], ["Pyroclastic Flow", "1", "pyro"]])
        u = (["index", "prop1", "par1", "min1", "max1"], [["Trang", "oskill", "Fire Ball", "1", "1"], ["Ok", "oskill", "Pyroclastic Flow", "1", "1"]])
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            for name, (head, rows) in (("itemstatcost", self.ISC), ("properties", self.PROPS), ("skills", skills),
                                       ("skilldesc", self.DESC), ("uniqueitems", u)):
                write_table(f, name, head, rows)
            hits = [(x.key, x.text) for x in ta.audit_stat_lines(f, "rotw", STRINGS) if x.kind == "skill-name"]
        self.assertEqual(hits, [("oskill Fire Ball", "names nothing, read as 0: skill 'Attack': no skilldesc")])

    def test_the_migration_fills_the_format_keys(self):
        import txt_migrate
        self.assertEqual(txt_migrate.FORMAT_KEY_FUNCS, {"27": "ItemModifierClassSkill", "28": "ItemModifierNonClassSkill"})
        self.assertNotIn("27", ta.OWN_FORMAT_DESCFUNCS)
        self.assertNotIn("28", ta.OWN_FORMAT_DESCFUNCS)


class RuneLetters(unittest.TestCase):
    """Bug #330: the rune letter line reads the gems `letter` cell as a key of D2R's own namespace."""
    D2R = ta.Strings({"r01L": "El", "r34L": "Sha", "Taha": "Taha", "Bad": "Missing string"}, own={"Taha"},
                     d2r={"r01L": "El", "r34L": "Sha", "Bad": "Missing string", "Shaad1": "Shaad"})
    MISC = (["name", "code", "type"], [["El Rune", "r01", "rune"], ["Sha Rune", "r34", "rune"], ["Taha Rune", "r51", "rune"],
                                       ["Elixir", "elx", "elix"]])

    def found(self, gems):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            write_table(f, "misc", *self.MISC)
            write_table(f, "gems", ["name", "letter", "code"], gems)
            return sorted((x.table, x.key, x.text) for x in ta.audit_rune_letters(f, "rotw", self.D2R))

    def test_d2r_keys_are_clean(self):
        self.assertEqual(self.found([["El Rune", "r01L", "r01"], ["Sha Rune", "r34L", "r34"], ["Taha Rune", "r01L", "r51"]]), [])

    def test_literal_names_and_the_mods_own_keys_are_found(self):  # Median's cells; a mxl2012 key does not reach the field
        self.assertEqual(self.found([["El Rune", "El", "r01"], ["Sha Rune", "Bad", "r34"], ["Taha Rune", "Taha", "r51"]]),
                         [("gems", "Bad", "Missing string"), ("gems", "El", "Missing string"), ("gems", "Taha", "Missing string")])

    def test_too_long_blank_and_missing_rows(self):
        self.assertEqual(self.found([["El Rune", "Shaad1", "r01"], ["Sha Rune", "", "r34"]]),
                         [("gems", "", "Missing string"), ("gems", "Shaad1", "Shaad"), ("misc", "r51", "no gems row")])

    def test_a_literal_name_that_is_another_key(self):  # rune Xar reads D2R's item name `xar`; No reads D2R's `NO`
        d2r = ta.Strings({}, own=set(), d2r={"xar": "Ornate Plate", "No": "NO", "r01L": "El"})
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            write_table(f, "misc", ["name", "code", "type"], [["Xar Rune", "r47", "rune"], ["No Rune", "r43", "rune"]])
            write_table(f, "gems", ["name", "letter", "code"], [["Xar Rune", "Xar", "r47"], ["No Rune", "No", "r43"]])
            self.assertEqual([(x.key, x.text) for x in ta.audit_rune_letters(f, "rotw", d2r)], [("Xar", "Ornate Plate")])

    def test_the_d2r_namespace_defaults_to_all_texts(self):
        self.assertEqual(ta.Strings({"A": "a"}, own=set()).d2r, {"a": "a"})


class Layouts(unittest.TestCase):
    def test_an_at_key_in_a_served_layout_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.json").write_text('{\n "text": "@strClose",\n "b": "@strClose @Nope",\n "c": "plain",\n}\n', encoding="utf-8")
            found = ta.audit_layouts(Path(d), STRINGS)
            self.assertEqual([(f.kind, f.key) for f in found],
                             [("layout-at-key", "@strClose"), ("layout-at-key", "@strClose"), ("layout-key-missing", "@Nope")])
            self.assertIn("a.json line 2", found[0].where)

    def test_a_layout_of_literals_is_clean(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.json").write_text('{ "text": "Close", "item": "x" }', encoding="utf-8")
            self.assertEqual(ta.audit_layouts(Path(d), STRINGS), [])


class StringsCheckFailsTheBuild(unittest.TestCase):
    def test_strings_check_runs_the_audit_only_for_rewritten_tables(self):
        src = Path(strings_check.__file__).read_text("utf-8")
        self.assertIn("text_audit.audit(", src)
        self.assertIn("args.rewritten", src)
        self.assertIn('errors += [f"text audit: {f}" for f in found]', src)


class ColourCodes(unittest.TestCase):
    """Bug #398: Median's `ÿc/` (colour -1 in 1.13c) printed as "*/" (HD) / "Ø/" (classic); tbl2json maps it, the audit fails on
    any colour code D2R cannot draw."""
    def test_the_map_turns_slash_into_white_and_keeps_the_rest(self):
        import strings_ns
        self.assertEqual(strings_ns.map_colours("ÿc/stance - poison"), "ÿc0stance - poison")
        self.assertEqual(strings_ns.map_colours("ÿc1requires a staffÿc/\nmelee"), "ÿc1requires a staff\nÿc0melee")
        keep = "ÿc0ÿc1ÿc2ÿc3ÿc4ÿc5ÿc7ÿc8ÿc9ÿc:ÿc;ÿcMÿcU 50/50 c/o"
        self.assertEqual(strings_ns.map_colours(keep), keep)

    def test_a_code_that_ends_a_line_moves_behind_the_line_break(self):  # D2R drops it there, 1.14d colours the next line
        import strings_ns
        self.assertEqual(strings_ns.map_colours("aÿc0ÿc2\nbÿc/\n\nc ÿc4"), "a\nÿc0ÿc2b\n\nÿc0c ÿc4")  # a text's last code stays
        s = ta.Strings({"Enfilade": "ÿc1javelinÿc2\nhold", "Moved": "ÿc1javelin\nÿc2hold"}, own={"Enfilade", "Moved"})
        self.assertEqual([(f.key, f.text) for f in ta.audit_colours(s)], [("enfilade", "ÿc2 before a line break")])

    def test_every_mapped_code_lands_on_a_colour_d2r_draws(self):
        import strings_ns
        self.assertTrue(set(strings_ns.COLOUR_MAP.values()) <= strings_ns.D2R_COLOURS)
        self.assertFalse(set(strings_ns.COLOUR_MAP) & strings_ns.D2R_COLOURS)

    def test_bad_colours(self):
        import strings_ns
        self.assertEqual(strings_ns.bad_colours("ÿc/a ÿc4b ÿc=c"), ["/", "="])
        self.assertEqual(strings_ns.bad_colours("ÿc0ÿc;ÿc:ÿcMÿcU"), [])
        self.assertEqual(strings_ns.bad_colours("dangling ÿc"), [""])
        self.assertEqual(strings_ns.bad_colours("ÿc"), [])  # string 3994 `colorcode`: the code appends the colour
        self.assertEqual(strings_ns.bad_colours(strings_ns.map_colours("ÿc/a ÿc1b")), [])

    def test_the_audit_finds_the_mods_own_texts_only(self):
        s = ta.Strings({"SkillsdSnake": "ÿc/stance - poison", "Fixed": "ÿc0stance", "D2ROwn": "ÿc/D2R's business",
                        "Twice": "ÿc/a ÿc<b ÿc/c"},
                       own={"SkillsdSnake", "Fixed", "Twice"})
        got = sorted((f.kind, f.key, f.text) for f in ta.audit_colours(s))
        self.assertEqual(got, [("colour-code", "skillsdsnake", "ÿc/"), ("colour-code", "twice", "ÿc/, ÿc<")])

    def test_the_audit_runs_it(self):
        s = ta.Strings({"SkillsdSnake": "ÿc/stance"}, own={"SkillsdSnake"})
        with tempfile.TemporaryDirectory() as d:
            found, _ = ta.audit(Path(d) / "excel", s, allow=[])
        self.assertEqual([(f.kind, f.key) for f in found], [("colour-code", "skillsdsnake")])

    def test_tbl2json_maps_before_writing(self):
        src = Path(ta.__file__).with_name("tbl2json.py").read_text("utf-8")
        self.assertIn("texts = {k: strings_ns.map_colours(t) for k, t in texts.items()}", src)


if __name__ == "__main__":
    unittest.main()


class SkillLines(unittest.TestCase):
    """Bug #396: the skill tooltip lines read as D2R's line renderer (0x287a50) reads them."""
    S = ta.Strings({"StrSkill82": "Fire Duration: %d seconds", "StrSkill82_mxl": "Fire Duration: ", "StrSkill3": "Mana Cost: %d",
                    "StrSkill3_mxl": "Mana Cost: ", "Pct": "%d%% Chance", "Plain": "Radius: "},
                   own={"StrSkill82_mxl", "StrSkill3_mxl", "Pct", "Plain"})
    DESC = ["skilldesc", "descline1", "desctexta1", "desctextb1", "descline2", "desctexta2", "desctextb2",
            "dsc2line1", "dsc2texta1", "dsc2textb1"]

    def found(self, desc_rows, skills=None, handled=True):
        old = ta.FIXED_LABELS_HANDLED
        ta.FIXED_LABELS_HANDLED = handled
        self.addCleanup(setattr, ta, "FIXED_LABELS_HANDLED", old)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d)
            write_table(f, "skills", ["skill", "skilldesc", "mana", "lvlmana"],
                        skills or [["Fire Wall", "fire wall", "22", "1"], ["Free", "free", "0", ""]])
            write_table(f, "skilldesc", self.DESC, desc_rows)
            return sorted((x.kind, x.column, x.key, x.text) for x in ta.audit_skill_lines(f, "rotw", self.S))

    def test_fire_wall_before_the_fix(self):  # blank mana label, Fire Duration's raw %d, the hard-coded type 27 label
        got = self.found([["fire wall", "1", "", "", "30", "StrSkill82", "", "27", "", ""]], handled=False)
        self.assertEqual([(c, k) for _kind, c, k, _t in got], [("desctexta1", "fire wall"), ("desctexta2", "StrSkill82"),
                                                                ("dsc2line1", "fire wall")])
        self.assertTrue(all(kind == "skill-desc" for kind, *_ in got))

    def test_fire_wall_after_the_fix(self):
        self.assertEqual(self.found([["fire wall", "1", "mxl2012:StrSkill3_mxl", "", "30", "mxl2012:StrSkill82_mxl", "", "27", "", ""]]), [])

    def test_a_blank_mana_label_without_a_mana_cost_is_not_drawn(self):
        self.assertEqual(self.found([["free", "1", "", "", "", "", "", "", "", ""]]), [])

    def test_formatting_types_read_their_format_slot_only(self):
        # 75 formats text A (D2R's own text is right there) and never reads text B; 36 must hold a number
        self.assertEqual(self.found([["fire wall", "75", "StrSkill82", "StrSkill82", "36", "Plain", "", "", "", ""]]),
                         [("skill-desc", "desctexta2", "Plain", "type 36 formats 'Radius: ': no number")])

    def test_a_row_no_skill_names_is_skipped(self):
        self.assertEqual(self.found([["unused", "30", "StrSkill82", "", "", "", "", "", "", ""]]), [])

    def test_the_format_table(self):
        import strings_ns
        self.assertEqual(strings_ns.skilldesc_format(30), "")
        self.assertEqual(strings_ns.skilldesc_format(13), "A")
        self.assertEqual(strings_ns.skilldesc_format(77), "AB")
        self.assertIn(27, strings_ns.SKILLDESC_FIXED_LABELS)
