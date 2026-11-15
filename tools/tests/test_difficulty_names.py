"""Median 2012's difficulty names (Hatred, Terror, Destruction) on D2R's difficulty strings (median-rules-audit DF13).

The data check reads data/d2r_string_fixes.json; the build check reads the built overrides.json in work/mod (skipped when the
build has not run) and wants every language of every difficulty key to carry the classic name."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "wiki"))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import merge_string_overrides as m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
BUILT = ROOT / "work" / "mod" / "data" / "local" / "lng" / "strings" / "mxl2012" / "overrides.json"
ACTS = ["I", "II", "III", "IV", "V"]
NAMES = {"Normal": "Hatred", "Nightmare": "Terror", "Hell": "Destruction"}

EXPECTED = {
    "d2r:strCreateGameNormalText": "Hatred",
    "d2r:strCreateGameNightmareText": "Terror",
    "d2r:strCreateGameHellText": "Destruction",
    "d2r:strCreateGameNormalTextPatch": "HATRED",
    "d2r:strCreateGameNightmareTextPatch": "TERROR",
    "d2r:strCreateGameHellTextPatch": "DESTRUCTION",
    "d2r:strgamefailillegaljoinXE":
        "Unable to enter game. Your character must kill Baal in Terror difficulty to play in a Destruction game.",
    "d2r:strgamefailillegaljoinXD": "Unable to enter game. Your character must kill Baal to play in a Terror difficulty game.",
    "d2r:strgamefailillegaljoinE":
        "Unable to enter game. Your character must kill Diablo in Terror difficulty to play in a Destruction game.",
    "d2r:strgamefailillegaljoinD": "Unable to enter game. Your character must kill Diablo to play in a Terror difficulty game.",
}
# presence-states.json (Battle.net rich presence, "Act I - Normal") is not loaded by the game's string table: an override of
# its keys stops the whole string table (lane diffnames run checks-20261113-231341-s3), so those keys stay D2R's.
NOT_OVERRIDDEN = [f"d2r:presenceA{i}{d2r}" for d2r in NAMES for i in range(1, len(ACTS) + 1)]
# D2R keys whose Normal / Nightmare / Hell is not a difficulty: they keep their wording.
UNRELATED = ["d2r:NormalQuality", "d2r:LootFilterNormalQuality", "d2r:WeaponAttackNormal", "d2r:WingedNightmare",
             "d2r:Hell Bovine", "d2r:hellgate", "d2r:strmpjoingamewrongtype", "d2r:strgamefailillegaljoinB"]


class DifficultyNameTests(unittest.TestCase):
    def test_fixes_carry_the_classic_names(self):
        fixes = {f["key"]: f["text"] for f in json.loads(m.FIXES.read_text("utf-8"))}
        for key, text in EXPECTED.items():
            self.assertEqual(fixes.get(key), text, key)
        for key in UNRELATED + NOT_OVERRIDDEN:
            self.assertNotIn(key, fixes)

    def test_presence_states_are_not_loaded_keys(self):
        import strings_ns
        self.assertIn("presence-states.json", strings_ns.NOT_LOADED)

    def test_built_strings_carry_the_classic_names_in_every_language(self):
        if not BUILT.exists():
            self.skipTest(f"{BUILT} not built (py -3 tools/build.py)")
        recs = {r["Key"]: r for r in json.loads(BUILT.read_text("utf-8-sig"))}
        for key, text in EXPECTED.items():
            self.assertIn(key, recs, key)
            langs = {k: v for k, v in recs[key].items() if k != "Key"}
            self.assertEqual(len(langs), 13, key)
            for lang, value in langs.items():
                self.assertEqual(value, text, f"{key} {lang}")
        for key in NOT_OVERRIDDEN:
            self.assertNotIn(key, recs)
        for key in UNRELATED:
            for word in ("Hatred", "Terror", "Destruction"):
                self.assertNotIn(word, recs.get(key, {}).get("enUS", ""), key)

    def test_wiki_cube_minimum_difficulty_uses_the_classic_names(self):
        import cube
        self.assertEqual(cube.DIFFICULTY, {"1": "Terror", "2": "Destruction"})


if __name__ == "__main__":
    unittest.main()
