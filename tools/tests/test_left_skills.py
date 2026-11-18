"""Left-button skills and Move Only (docs/left-skills.md): skill_rules gives every right-button skill but the auras and the
scroll / book skills leftskill 1; Migrator.move_only adds the Move Only row to skills.txt and skilldesc.txt and gives it to
every class through charstats.txt; tools/move_only.py has its texts in the 13 languages."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import move_only  # noqa: E402
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

COLS = ["skill", "*Id", "charclass", "skilldesc", "srvstfunc", "srvdofunc", "srvstopfunc", "srvmissile", "srvmissilea",
        "cltstfunc", "cltdofunc", "cltstopfunc", "cltmissilea", "aura", "passivestate", "passivestat1", "anim", "seqtrans",
        "monanim", "range", "TargetableOnly", "AttackNoMana", "interrupt", "reqlevel", "maxlvl", "restrict", "leftskill",
        "rightskill", "InTown", "InGame", "SelectProc", "TargetCorpse"]
DESC_COLS = ["skilldesc", "SkillPage", "SkillRow", "SkillColumn", "ListRow", "IconCel", "str name", "str short", "str long",
             "str alt"]
CHAR_COLS = ["class", "Skill 1", "Skill 2", "Skill 3"]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


def row(name, sid, left="", right="", aura="", do="", passive="", **extra):
    r = dict.fromkeys(COLS, "")
    r.update(extra)
    r.update({"skill": name, "*Id": sid, "leftskill": left, "rightskill": right, "aura": aura, "srvdofunc": do,
              "passivestate": passive, "anim": "SC", "seqtrans": "SC"})
    return [r[c] for c in COLS]


class LeftSkillRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        tm.OUT, tm.D2R = root / "out", root / "d2r"
        rows = [row("Attack", "0", "1", "1", do="1"), row("Blackstorm", "1", "", "", do="12"),
                row("Bone Spirit", "2", "", "1", do="8"), row("Hex Bane", "3", "0", "1", do="9"),
                row("Might", "4", "", "1", aura="1"), row("Fanaticism", "5", "0", "1", aura="1"),
                row("Iron Skin", "6", "", "", passive="12"), row("Scroll of Identify", "7", "", "1", do="113"),
                row("Townportal O Skill", "8", "0", "1", do="109"), row("Left Hand Swing", "9", "1", "0", do="1"),
                row("Kick", "10", "", "0", do="2"),
                row("Deaths Fury Totem", "11", "", "1", do="31", SelectProc="2", TargetCorpse="1"),
                row("Engorge", "12", "0", "1", do="37", SelectProc="1", TargetCorpse="1")]
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "skills.txt").write_text(tsv(COLS, *rows), encoding="utf-8")
            e = tm.D2R / bank
            e.mkdir(parents=True, exist_ok=True)
            (e / "skills.txt").write_text(tsv(COLS, row("Attack", "0", "1", "1", do="1")), encoding="utf-8")
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def flags(self, bank):
        h, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / "skills.txt")
        return {r[0]: (r[h.index("leftskill")], r[h.index("rightskill")]) for r in rows if r[0]}

    def test_right_button_skills_go_on_the_left_too(self):
        self.mig.skill_rules()
        for bank in ("base", ""):
            got = self.flags(bank)
            # castable: blank rightskill filled (bug #16), then both buttons; D2R's explicit leftskill 0 included
            for name in ("Attack", "Blackstorm", "Bone Spirit", "Hex Bane"):
                self.assertEqual(got[name], ("1", "1"), name)
            # auras run from the right button; passives on neither; the scroll / book / portal skills right only
            self.assertEqual(got["Might"], ("", "1"))
            self.assertEqual(got["Fanaticism"], ("0", "1"))
            self.assertEqual(got["Iron Skin"], ("", "0"))
            self.assertEqual(got["Scroll of Identify"], ("", "1"))
            self.assertEqual(got["Townportal O Skill"], ("0", "1"))
            # corpse-targeted skills: a left click picks no corpse (the totems cast nothing from the left in game)
            self.assertEqual(got["Deaths Fury Totem"], ("", "1"))
            self.assertEqual(got["Engorge"], ("0", "1"))
            # left-only and neither-button rows keep what they have
            self.assertEqual(got["Left Hand Swing"], ("1", "0"))
            self.assertEqual(got["Kick"], ("", "0"))
        self.assertIn("3 right-button skills", " ".join(self.mig.report))


class MoveOnlyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        tm.OUT = Path(self.temp.name) / "out"
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "skills.txt").write_text(tsv(COLS, row("Attack", "0", "1", "1"), ["Expansion"] + [""] * (len(COLS) - 1),
                                              row("Throw", "1", "1", "1")), encoding="utf-8")
            (d / "skilldesc.txt").write_text(tsv(DESC_COLS, ["attack"] + [""] * (len(DESC_COLS) - 1)), encoding="utf-8")
            (d / "charstats.txt").write_text(tsv(CHAR_COLS, ["Amazon", "Throw", "Kick", ""], ["Barbarian", "Throw", "", ""],
                                                 ["Expansion", "", "", ""], ["Warlock", "Throw", "Kick", ""]), encoding="utf-8")
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def read(self, bank, table):
        return tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / f"{table}.txt")

    def test_row_and_classes(self):
        self.mig.move_only()
        self.mig.move_only()  # a second run changes nothing
        for bank in ("base", ""):
            h, rows = self.read(bank, "skills")
            mo = [r for r in rows if r[0] == move_only.SKILL]
            self.assertEqual(len(mo), 1)
            r = dict(zip(h, mo[0]))
            self.assertEqual(r["*Id"], "2")  # after the two records; the Expansion line is not a record
            self.assertEqual((r["leftskill"], r["rightskill"], r["srvstfunc"], r["srvdofunc"]), ("1", "1", "71", ""))
            self.assertEqual((r["TargetableOnly"], r["charclass"], r["skilldesc"]), ("1", "", "move_only"))
            dh, drows = self.read(bank, "skilldesc")
            d = dict(zip(dh, [x for x in drows if x[0] == "move_only"][0]))
            self.assertEqual((d["SkillPage"], d["str name"]), ("0", "SkillnameMoveOnly"))
            ch, crows = self.read(bank, "charstats")
            got = {x[0]: x[1:] for x in crows if x[0] not in ("", "Expansion")}
            self.assertEqual(got, {"Amazon": ["Throw", "Kick", "Move Only"], "Barbarian": ["Throw", "Move Only", ""],
                                   "Warlock": ["Throw", "Kick", "Move Only"]})
        self.assertIn("Move Only: skill 2 (srvstfunc 71), starting skill of Amazon, Barbarian, Warlock", self.mig.report[-1])

    def test_full_class_row_raises(self):
        h, rows = CHAR_COLS, [["Amazon", "Throw", "Kick", "Unsummon"]]
        with self.assertRaises(ValueError):
            move_only.add_to_classes(h, rows)

    def test_start_slot_taken_raises(self):
        rows = [row("Flash", "0")]
        rows[0][COLS.index("srvstfunc")] = "71"
        with self.assertRaises(ValueError):
            move_only.add_skill(COLS, rows)

    def test_unknown_column_raises(self):
        with self.assertRaises(ValueError):
            move_only.make_row(["skill"], {"nosuch": "1"})


BUILT_SKILLS = TOOLS.parent / "work" / "mod" / "data" / "global" / "excel" / "skills.txt"
NAMED_SKILLS = TOOLS.parent / "work" / "named" / "skills.txt"


@unittest.skipUnless(BUILT_SKILLS.exists() and NAMED_SKILLS.exists(), "needs a built mod (tools/build.py)")
class SaveSkillTests(unittest.TestCase):
    """Bug #616: the `leftskills` save part puts a skill of the player's own class on the left. D2 saves only the class's own
    skills, so a skill of another class (Sacrifices on an Amazon) was dropped by Save and Exit and the left button read Attack."""

    def test_each_class_saves_one_of_its_own_left_skills(self):
        import leftskills_checks as lc
        codes = ("ama", "sor", "nec", "pal", "bar", "dru", "ass")  # `h state` class ids 0-6 (game_checks.CLASSES)
        self.assertEqual(sorted(lc.LS_SAVE), list(range(len(codes))))
        h, built = tm.read_tsv(BUILT_SKILLS)
        nh, named = tm.read_tsv(NAMED_SKILLS)
        rows = {r[0]: dict(zip(h, r)) for r in built if r and r[0]}
        before = {r[0]: dict(zip(nh, r)) for r in named if r and r[0]}
        for cls, name in lc.LS_SAVE.items():
            r = rows.get(name)
            self.assertIsNotNone(r, name)
            self.assertEqual(r["charclass"], codes[cls], name)
            self.assertEqual(r["leftskill"], "1", name)
            self.assertNotEqual(r["aura"], "1", name)
            if codes[cls] != "bar":  # every Barbarian skill on the left was there in Median already
                self.assertNotEqual(before[name].get("leftskill"), "1", "%s: not formerly right-only" % name)


class MoveOnlyTextTests(unittest.TestCase):
    def test_every_language_has_its_own_text(self):
        recs = move_only.string_records()
        self.assertEqual([r["Key"] for r in recs], ["SkillnameMoveOnly", "SkillsdMoveOnly", "SkillldMoveOnly"])
        for r in recs:
            self.assertEqual(set(r) - {"Key"}, set(move_only.LANGS))
            self.assertTrue(all(r[lang].strip() for lang in move_only.LANGS))
        name = recs[0]
        self.assertEqual(name["enUS"], "Move Only")
        self.assertNotEqual(name["deDE"], name["enUS"])
        self.assertEqual(name["zhTW"], "\U000050c5\U000079fb\U000052d5")
        self.assertIn("\n", recs[2]["enUS"])  # two tooltip lines

    def test_missing_language_raises(self):
        with self.assertRaises(ValueError):
            move_only.string_records(move_only.LANGS + ("xxXX",))

    def test_source_stays_ascii(self):
        (TOOLS / "move_only.py").read_bytes().decode("ascii")


if __name__ == "__main__":
    unittest.main()
