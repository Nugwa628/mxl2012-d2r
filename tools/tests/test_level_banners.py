"""tools/level_entries.py: every level's red "Entering ..." banner reads its Median XL 2012 name (bug #612)."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import level_entries as le  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
LANGS = ["enUS", "deDE", "frFR"]
HEAD = ["Name", "*StringName", "Id", "LevelName", "LevelWarp", "LevelEntry"]
# Id, LevelName key, LevelEntry key (as txt_migrate writes them)
LEVELS = [("1", "Rogue Encampment", "EnteringTheRogueEncampment"),       # Median keeps vanilla's name
          ("13", "Cave Level 2", "EnteringTheCaveLevel2"),               # Median: "Duncraig"
          ("39", "Moo Moo Farm", "EnteringTheMooMooFarm"),               # Median: "The Secret Cow Level"
          ("108", "Chaos Sanctum", "EnteringChaosSanctum"),              # Median: "The Chaos Sanctuary", D2R "Chaos Sanctuary"
          ("125", "Hell1", "EnteringHell1"),                             # Median: "Welcome to Toraja"
          ("140", "mxl2012:OwnLevel", "mxl2012:OwnLevel")]               # a Median-only name is its own banner
D2R = {"Rogue Encampment": "Rogue Encampment", "EnteringTheRogueEncampment": "Entering The Rogue Encampment",
       "Cave Level 2": "Cave Level 2", "EnteringTheCaveLevel2": "Entering The Cave Level 2",
       "Moo Moo Farm": "Moo Moo Farm", "EnteringTheMooMooFarm": "Entering The Moo Moo Farm",
       "Chaos Sanctum": "Chaos Sanctuary", "EnteringChaosSanctum": "Entering Chaos Sanctuary",
       "Hell1": "Abaddon", "EnteringHell1": "Entering Abaddon"}
OVERRIDES = {"Cave Level 2": "Duncraig", "Moo Moo Farm": "The Secret Cow Level", "Chaos Sanctum": "The Chaos Sanctuary",
             "Hell1": "Welcome to Toraja", "Rogue Encampment": "Rogue Encampment"}


def write_json(path: Path, recs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("﻿" + json.dumps(recs, ensure_ascii=False), encoding="utf-8")


def make_tree(root: Path) -> tuple[Path, Path]:
    mod, lng = root / "mod", root / "lng"
    ns = mod / "data" / "local" / "lng" / "strings" / "mxl2012"
    write_json(ns / "overrides.json", [{"Key": "d2r:" + k, **{lang: v for lang in LANGS}} for k, v in OVERRIDES.items()])
    write_json(ns / "median.json", [{"Key": "OwnLevel", **{lang: "Duncraig Depths" for lang in LANGS}}])
    write_json(lng / "strings" / "levels.json",
               [{"id": i, "Key": k, "enUS": v, "deDE": "de " + v, "frFR": "fr " + v} for i, (k, v) in enumerate(D2R.items())])
    # the Chinese region's renames come first by name and must not count
    write_json(lng / "strings" / "chinese-overlay.json", [{"id": 1, "Key": "EnteringTheRogueEncampment", "enUS": "Entering Elsewhere"}])
    for bank in ("", "base"):
        d = mod / "data" / "global" / "excel" / bank
        d.mkdir(parents=True, exist_ok=True)
        lines = ["\t".join(HEAD)] + ["\t".join([f"Level {i}", "", i, n, "", e]) for i, n, e in LEVELS]
        (d / "levels.txt").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return mod, lng


class Banner(unittest.TestCase):
    def test_reads(self):
        self.assertTrue(le.banner_reads("Rogue Encampment", "Entering The Rogue Encampment"))
        self.assertTrue(le.banner_reads("The Chaos Sanctuary", "Entering Chaos Sanctuary"))
        self.assertTrue(le.banner_reads("Duncraig Depths", "Duncraig Depths"))
        self.assertFalse(le.banner_reads("Duncraig", "Entering The Cave Level 2"))
        self.assertFalse(le.banner_reads("Duncraig", ""))
        self.assertFalse(le.banner_reads("", "Entering Duncraig"))

    def test_text(self):
        self.assertEqual(le.banner_for("Duncraig"), "Entering Duncraig")
        self.assertEqual(le.banner_for("The Secret Cow Level"), "Entering The Secret Cow Level")
        self.assertEqual(le.banner_for("Welcome to Toraja"), "Welcome to Toraja")
        for name in ("Duncraig", "The Secret Cow Level", "Welcome to Toraja", "Azmodan's Reliquary"):
            self.assertTrue(le.banner_reads(name, le.banner_for(name)), name)


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mod, self.lng = make_tree(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def entries(self):
        return le.check(self.mod, self.lng)

    def test_before(self):
        wrong = {(e["bank"], e["id"]) for e in self.entries() if not e["ok"]}
        self.assertEqual(wrong, {(b, i) for b in ("rotw", "base") for i in ("13", "39", "125")})

    def test_apply_fixes_every_level(self):
        self.assertEqual(le.main(["apply", "--mod", str(self.mod), "--d2r-lng", str(self.lng)]), 0)
        entries = self.entries()
        self.assertEqual([e for e in entries if not e["ok"]], [])
        banner = {e["id"]: e["banner"] for e in entries}
        self.assertEqual(banner["13"], "Entering Duncraig")
        self.assertEqual(banner["39"], "Entering The Secret Cow Level")
        self.assertEqual(banner["125"], "Welcome to Toraja")
        self.assertEqual(banner["1"], "Entering The Rogue Encampment")  # untouched: D2R's own, translated text stays
        ns = self.mod / "data" / "local" / "lng" / "strings" / "mxl2012"
        recs = {r["Key"]: r for r in json.loads((ns / "overrides.json").read_text("utf-8-sig"))}
        self.assertNotIn("d2r:EnteringTheRogueEncampment", recs)
        self.assertNotIn("d2r:EnteringChaosSanctum", recs)
        # every language the mod ships gets the banner (Median's names are English in all of them)
        self.assertEqual({lang: recs["d2r:EnteringTheCaveLevel2"][lang] for lang in LANGS},
                         {lang: "Entering Duncraig" for lang in LANGS})
        # the extra file is folded in and parked: D2RLoader would load a second copy of the key from the namespace folder
        self.assertFalse((ns / le.OUT_FILE).exists())
        self.assertTrue((self.mod / "string_extras" / le.OUT_FILE).exists())
        # idempotent
        self.assertEqual(le.main(["apply", "--mod", str(self.mod), "--d2r-lng", str(self.lng)]), 0)
        self.assertEqual(len(json.loads((ns / "overrides.json").read_text("utf-8-sig"))), len(recs))

    def test_shared_key_with_two_names_is_a_problem(self):
        entries = self.entries() + [{"bank": "rotw", "id": "99", "name_key": "X", "name": "Other", "entry_key": "EnteringTheCaveLevel2",
                                     "banner": "Entering The Cave Level 2", "ok": False}]
        want, problems = le.plan(entries)
        self.assertNotIn("EnteringTheCaveLevel2", want)
        self.assertTrue(any("shared" in p for p in problems))


BUILT = ROOT / "work" / "mod" / "data" / "local" / "lng" / "strings" / "mxl2012" / "overrides.json"
D2R_LNG = Path(fxpaths.D2R) / "data" / "local" / "lng"


@unittest.skipUnless(BUILT.exists() and (D2R_LNG / "strings" / "levels.json").exists(), "needs a build (tools/build.py) and D2R's strings")
class BuiltMod(unittest.TestCase):
    def test_every_level_banner_reads_its_median_name(self):
        entries = le.check(ROOT / "work" / "mod", D2R_LNG)
        self.assertGreater(len(entries), 200)
        self.assertEqual([f"{e['bank']} {e['id']}: {e['name']!r} / {e['banner']!r}" for e in entries if not e["ok"]], [])
        duncraig = [e for e in entries if e["id"] == "13"]
        self.assertEqual({e["banner"] for e in duncraig}, {"Entering Duncraig"})


if __name__ == "__main__":
    unittest.main()
