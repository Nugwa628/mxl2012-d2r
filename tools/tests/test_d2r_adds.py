import pathlib as _pl, sys as _sys; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1])); import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("d2r_adds", Path(__file__).resolve().parents[1] / "d2r_adds.py")
adds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adds)

ZONES = {"type": "DesecratedZonesConfigs", "desecrated_zones": [{
    "seed": 16665365343970128666,
    "game_difficulties": {
        "expansion": {"hell": {"ladder_enabled": True, "non_ladder_enabled": True, "max_herald_tiers": 0}},
        "rotw": {"hell": {"ladder_enabled": True, "non_ladder_enabled": False, "max_herald_tiers": 5}}},
    "zones": [{"id": "Act1-BurialGrounds", "levels": [{"level_id": 17}]}]}]}


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class D2rAddsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.mod, self.d2r, self.out = root / "mod", root / "d2r", root / "out"
        self.put(self.d2r, "data/hd/global/excel/desecratedzones.json", json.dumps(ZONES))
        for bank in ("", "base/"):
            self.put(self.mod, f"data/global/excel/{bank}monstats.txt", tsv(
                ["Id", "CannotDesecrate", "CannotHerald", "TreasureClassDesecrated", "TreasureClassHerald"],
                ["skeleton1", "", "", "Act 1 Desecrated A", "Herald TC"],
                ["Expansion", "", "", "", ""]))
            self.put(self.mod, f"data/global/excel/{bank}superuniques.txt", tsv(
                ["Superunique", "TC", "TC Desecrated", "TC(H) Desecrated"], ["Bishibosh", "Act 1 Super A", "x", "y"]))
            self.put(self.mod, f"data/global/excel/{bank}setitems.txt", tsv(
                ["index", "set", "firstLadderSeason", "lastLadderSeason"], ["Angelic Sickle", "Angelical Raiment", "15", "16"]))
            self.put(self.mod, f"data/global/excel/{bank}states.txt", tsv(
                ["state", "sunderfull", "sunder-res-reduce"], ["amplifydamage", "1", ""], ["passive_3", "", "1"]))
            self.put(self.mod, f"data/global/excel/{bank}hireling.txt", tsv(
                ["Hireling", "equivalentcharclass"], ["Rogue Scout", "ama"]))
            gems_h = ["name", "letter", "code", "weaponMod1Code"]
            self.put(self.mod, f"data/global/excel/{bank}gems.txt", tsv(
                gems_h, ["Chipped Saphire", "", "gcb", "mana-kill"], ["Chipped Sapphire", "", "gcb", "cold"]))
            self.put(self.d2r, f"data/global/excel/{bank}gems.txt", tsv(
                gems_h + ["*eol"], ["Chipped Sapphire", "", "gcb", "cold", "0"], ["Chipped Ruby", "", "gcr", "fire", "0"]))
            books_h = ["Name", "ScrollSpellCode", "BookSpellCode", "pSpell"]
            self.put(self.mod, f"data/global/excel/{bank}books.txt", tsv(
                books_h, ["unused", "tsc", "tbk", "2"], ["unused", "", "", ""],
                ["Tome of Town Portal", "tsc", "tbk", "2"], ["Tome of Resurrect", "", "", "-1"]))
            self.put(self.d2r, f"data/global/excel/{bank}books.txt", tsv(
                books_h, ["Tome of Town Portal", "tsc", "tbk", "2"], ["Tome of Resurrect", "", "", "-1"]))
            self.put(self.mod, f"data/global/excel/{bank}experience.txt", tsv(
                ["Level", "Amazon", "Warlock", "ExpRatio"], ["MaxLvl", "120", "99", "10"], ["120", "666666666", "", "32"]))
            ch = ["class", "hpadd", "LifePerLevel", "StatPerLevel", "SkillsPerLevel", "str", "StartSkill"]
            items = [f"item{k}{s}" for k in range(1, 11) for s in ("", "loc", "count", "quality")]
            amazon = ["Amazon", "50", "100", "5", "1", "25", ""] + sum(
                ([c, loc, n, "2"] for c, loc, n in [("box", "", "1"), ("hp1", "", "8"), ("tsc", "", "10"),
                                                     ("zen", "", "1"), ("600", "tors", "1"), ("160", "rarm", "1"),
                                                     ("aqv", "larm", "1"), ("01-", "", "1"), ("0", "", "0"),
                                                     ("0", "", "0")]), [])
            warlock = ["Warlock", "30", "8", "5", "1", "15", "Miasma Bolt"] + sum(
                ([c, loc, n, "2"] for c, loc, n in [("dgr", "rarm", "1"), ("hp1", "", "4"), ("tsc", "", "1"),
                                                     ("isc", "", "1")] + [("0", "", "0")] * 6), [])
            self.put(self.mod, f"data/global/excel/{bank}charstats.txt", tsv(ch + items, amazon, warlock))
            self.put(self.mod, f"data/global/excel/{bank}misc.txt", tsv(
                ["name", "code", "AdvancedStashStackable"], ["El Rune", "r01", "1"]))

    def put(self, root, name, text):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    def table(self, root, name):
        t = adds.Table(root / "data/global/excel" / name)
        return t.header, t.rows

    def test_full_run(self):
        adds.run(self.mod, self.out, self.d2r)
        zones = json.loads((self.out / adds.ZONES).read_text(encoding="utf-8"))
        hell = zones["desecrated_zones"][0]["game_difficulties"]
        for version in ("expansion", "rotw"):
            self.assertFalse(hell[version]["hell"]["ladder_enabled"])
            self.assertFalse(hell[version]["hell"]["non_ladder_enabled"])
            self.assertEqual(hell[version]["hell"]["max_herald_tiers"], 0)
        self.assertEqual(zones["desecrated_zones"][0]["seed"], 16665365343970128666)  # UInt64 kept exact
        for bank in ("", "base/"):
            _, mon = self.table(self.out, f"{bank}monstats.txt")
            self.assertEqual(mon[0], ["skeleton1", "1", "1", "", ""])
            self.assertEqual(mon[1][0], "Expansion")
            self.assertEqual(mon[1][1:], ["", "", "", ""])
            self.assertEqual(self.table(self.out, f"{bank}superuniques.txt")[1][0], ["Bishibosh", "Act 1 Super A", "", ""])
            self.assertEqual(self.table(self.out, f"{bank}setitems.txt")[1][0][2:], ["", ""])
            self.assertEqual([r[1:] for r in self.table(self.out, f"{bank}states.txt")[1]], [["", ""], ["", ""]])
            self.assertEqual(self.table(self.out, f"{bank}hireling.txt")[1][0], ["Rogue Scout", ""])
            gems = self.table(self.out, f"{bank}gems.txt")[1]
            self.assertEqual([g[0] for g in gems], ["Chipped Saphire"])
            books = self.table(self.out, f"{bank}books.txt")[1]
            self.assertEqual([b[0] for b in books], ["unused", "unused"])
            exp = self.table(self.out, f"{bank}experience.txt")[1]
            self.assertEqual([r[2] for r in exp], ["120", "666666666"])
            h, cs = self.table(self.out, f"{bank}charstats.txt")
            war = dict(zip(h, cs[1]))
            self.assertEqual((war["hpadd"], war["LifePerLevel"], war["str"], war["StartSkill"]),
                             ("50", "100", "15", "Miasma Bolt"))  # Median rules, Warlock identity
            kit = [(war[f"item{k}"], war[f"item{k}loc"], war[f"item{k}count"]) for k in range(1, 11)]
            self.assertEqual(kit[:7], [("box", "", "1"), ("hp1", "", "8"), ("tsc", "", "10"), ("zen", "", "1"),
                                       ("600", "tors", "1"), ("142", "rarm", "1"), ("01-", "", "1")])
            self.assertEqual(kit[7:], [("0", "", "0")] * 3)
            self.assertEqual(self.table(self.out, f"{bank}misc.txt")[1][0][2], "1")  # stack tab kept by default
        # input untouched, CRLF kept
        self.assertEqual(self.table(self.mod, "monstats.txt")[1][0][1], "")
        self.assertIn(b"\r\n", (self.out / "data/global/excel/monstats.txt").read_bytes())
        self.assertTrue((self.out / "d2r_adds_report.md").exists())

    def test_idempotent_in_place(self):
        adds.run(self.mod, self.mod, self.d2r)
        before = {p: p.read_bytes() for p in (self.mod / "data").rglob("*.txt")}
        log = adds.run(self.mod, self.mod, self.d2r)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.mod / "data").rglob("*.txt")})
        self.assertIn("dup_codes: 0 D2R rows dropped", log)

    def test_advanced_stash_off_and_only(self):
        adds.run(self.mod, self.out, self.d2r, advanced_stash="off", only=["advanced_stash"])
        self.assertEqual(self.table(self.out, "misc.txt")[1][0][2], "")
        self.assertFalse((self.out / adds.ZONES).exists())  # other steps did not run
        self.assertEqual(self.table(self.out, "states.txt")[1][0][1], "1")

    def test_missing_tables_stop(self):
        with self.assertRaises(SystemExit):
            adds.run(self.out, self.out, self.d2r)


if __name__ == "__main__":
    unittest.main()
