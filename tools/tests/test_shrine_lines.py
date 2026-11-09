import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import projtemp  # noqa: E402,F401
import shrine_lines as sl  # noqa: E402

# the 20 kinds' recipe mods, as in Median's cubemain (the blessings rows carry the same stats)
RECIPES = {
    "A": ["str", "str%", "crush"], "B": ["dex", "dex%", "att%"], "C": ["vit", "vit%", "pot-rate"], "D": ["enr", "enr%", "enr-factor"],
    "E": ["dmg-max", "dmg-min", "dmg%"], "F": ["uninterrupt", "red-dmg", "ac%"], "G": ["dmg-minion", "att%-minion"],
    "H": ["extra-fire", "pierce-fire", "mana%"], "I": ["extra-ltng", "pierce-ltng", "mana%"], "J": ["extra-cold", "pierce-cold", "mana%"],
    "K": ["extra-pois", "pierce-pois", "mana%"], "L": [], "M": ["gold%", "mag%"], "N": ["hp-minion", "res-all-minion"], "O": [], "P": [],
    "Q": ["reanimate-rand"], "R": ["res-all", "red-mag"], "S": [], "T": []}
LINES = {
    "A": "Cube: Strength, Crushing Blow", "B": "Cube: Dexterity, Attack Rating", "C": "Cube: Vitality, Apple Healing",
    "D": "Cube: Energy, Energy Factor", "E": "Cube: Damage", "F": "Cube: Damage Reduced, Defense",
    "G": "Cube: Minion Damage, Minion Attack", "H": "Cube: Fire Damage, Pierce, Mana", "I": "Cube: Lightning Damage, Pierce, Mana",
    "J": "Cube: Cold Damage, Pierce, Mana", "K": "Cube: Poison Damage, Pierce, Mana", "L": "Cube: 6 Sockets, Doubled Orbs",
    "M": "Cube: Gold Find, Magic Find", "N": "Cube: Minion Life, Minion Resists", "O": "Cube: 6 Sockets, Doubled Orbs",
    "P": "Cube: 6 Sockets, Doubled Orbs", "Q": "Cube: Reanimate", "R": "Cube: All Resists, Magic Reduced",
    "S": "Cube: 6 Sockets, Doubled Orbs", "T": "Cube: 6 Sockets, Doubled Orbs"}


def rows_for(recipes):
    """Crafting and blessing rows with the shared mods in front, as the real table has them."""
    rows = []
    for kind, mods in recipes.items():
        for charge in (0, 9):
            code = f"{kind}{charge}+"
            craft = {"input 1": "ct1a,crf", "input 2": code, "mod 1": "sock", "mod 2": "desc-honorific"}
            bless = {"input 1": "ct1a,crf,noe", "input 2": code, "input 3": "qum", "mod 1": "blessings-counter"}
            for k, m in enumerate(mods):
                craft[f"mod {k + 3}"] = m
                bless[f"mod {k + 2}"] = m
            rows += [craft, bless]
    return rows


class ShrineLineTests(unittest.TestCase):
    def test_every_kind_has_its_line_from_the_recipes(self):
        lines = sl.lines_for(rows_for(RECIPES), {})
        self.assertEqual({k: v["enUS"] for k, v in lines.items()}, LINES)

    def test_lines_fit(self):
        for kind, text in LINES.items():
            self.assertLessEqual(sl.display_width(text), sl.MAX_WIDTH, kind)

    def test_an_unknown_recipe_mod_stops_the_build(self):
        with self.assertRaises(SystemExit):
            sl.kind_labels(rows_for({"A": ["nosuchmod"]}))

    def test_the_approved_style_for_creepy(self):
        y = chr(0xff)
        old = f"{y}c8by heavenly faith \nStrength is bolstered \nCreepy Shrine (10 Charges)"
        self.assertEqual(sl.with_line(old, LINES["A"]), f"{y}c3Cube: Strength, Crushing Blow\n{old}")
        self.assertEqual(sl.with_line(sl.with_line(f"{y}c8a\nb\nc", "Cube: X"), "Cube: Y"), f"{y}c3Cube: Y\n{y}c8a\nb\nc")

    def test_wide_lines_stop_the_build(self):
        with self.assertRaises(SystemExit):
            sl.lines_for(rows_for(RECIPES), {"Strength": {"jaJP": chr(0x7b4b) * 20}})

    def test_translation_uses_the_game_word_and_english_otherwise(self):
        word = "St" + chr(0xe4) + "rke"
        table = {"Strength": {"enUS": "Strength", "deDE": word}}
        self.assertEqual(sl.line(["Strength", "Crushing Blow"], "deDE", table), f"Cube: {word}, Crushing Blow")
        self.assertEqual(sl.line([], "deDE", table), "Cube: " + sl.NO_STATS)

    def test_apply_adds_the_line_to_all_200_strings_in_both_folders(self):
        y = chr(0xff)
        verse = f"{y}c8v2\nv1\nName"
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            excel = data / "global/excel"
            excel.mkdir(parents=True)
            rows = rows_for(RECIPES)
            fields = sorted({k for r in rows for k in r})
            with (excel / "cubemain.txt").open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fields, delimiter="\t", lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            lng = data / "lng"
            (lng / "strings").mkdir(parents=True)
            (lng / "strings/ui.json").write_text(json.dumps([
                {"Key": key, "enUS": label, "deDE": label.lower()} for label, key in sl.TRANSLATED.items()]), "utf-8")
            recs = [{"Key": f"{k}{c}+", "enUS": verse, "deDE": verse} for k in sl.KINDS for c in range(10)]
            recs.append({"Key": "other", "enUS": f"{y}c8keep"})
            for rel in sl.STRING_FILES:
                path = data / "local/lng" / rel
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(recs, ensure_ascii=False), "utf-8")
            sl.apply(data, lng)
            sl.apply(data, lng)  # a second run keeps one line
            for rel in sl.STRING_FILES:
                done = {r["Key"]: r for r in json.loads((data / "local/lng" / rel).read_text("utf-8-sig"))}
                self.assertEqual(done["A5+"]["enUS"], f"{y}c3Cube: Strength, Crushing Blow\n{verse}")
                self.assertEqual(done["A5+"]["deDE"], f"{y}c3Cube: strength, Crushing Blow\n{verse}")
                self.assertEqual(done["T9+"]["enUS"].count("Cube:"), 1)
                self.assertEqual(done["other"]["enUS"], f"{y}c8keep")
                self.assertEqual(sum(1 for k in done if sl.CODE.match(k)), 200)


class BuiltDataTests(unittest.TestCase):
    """The strings of a built mod match the built recipe table: skipped when there is no build."""

    MOD = ROOT / "work/mod/data"

    @unittest.skipUnless((MOD / "global/excel/cubemain.txt").exists(), "no build")
    def test_built_strings_match_the_recipes(self):
        y = chr(0xff)
        with (self.MOD / "global/excel/cubemain.txt").open(encoding="utf-8-sig", newline="") as f:
            labels = sl.kind_labels(list(csv.DictReader(f, delimiter="\t")))
        for rel in sl.STRING_FILES:
            recs = {r["Key"]: r for r in json.loads((self.MOD / "local/lng" / rel).read_text("utf-8-sig"))}
            for kind in sl.KINDS:
                expect = sl.line(labels[kind], "enUS", {})
                self.assertEqual(expect, LINES[kind], kind)  # the built table still says what the list above says
                for charge in range(10):
                    rec = recs[f"{kind}{charge}+"]
                    for loc, text in rec.items():
                        if loc == "Key":
                            continue
                        first = text.split("\n", 1)[0]
                        self.assertTrue(first.startswith(y + "c3" + sl.PREFIX), (kind, loc))
                        self.assertLessEqual(sl.display_width(first[3:]), sl.MAX_WIDTH, (kind, loc))
                    self.assertEqual(rec["enUS"].split("\n", 1)[0], y + "c3" + expect, kind)


if __name__ == "__main__":
    unittest.main()
