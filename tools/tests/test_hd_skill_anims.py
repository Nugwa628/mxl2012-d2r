"""Bug #526: a Median sequence skill whose id D2R also uses for another, unanimated skill (Batstrike 326 = D2R's BearSmite,
Bloodbath 65 = Cold Mastery) gets its own HD state; an id the class's state machine already animates keeps D2R's state."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import hd_skill_anims as H  # noqa: E402

COLS = ["skill", "*Id", "charclass", "anim", "seqnum", "skilldesc"]


def tsv(path, *rows):
    path.write_text("\r\n".join("\t".join(r) for r in [COLS, *rows]) + "\r\n", encoding="latin-1")


def machine():
    states = [{"stateId": 0, "name": "PMODE_NEUTRAL", "modeId": 0, "skillIndex": -1},
              {"stateId": 1, "name": "PMODE_SEQUENCE_BLADES_OF_ICE", "modeId": 18, "skillIndex": 274}]
    trans = [{"from": s["stateId"], "name": "from_%d" % s["stateId"],
              "settings": [{"to": t["stateId"], "name": "to_%d" % t["stateId"]} for t in states]} for s in states]
    return {"states": states, "transitions": trans}


class SequenceStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        d2r, mod = root / "d2r_skills.txt", root / "mod_skills.txt"
        tsv(d2r, ["Cold Mastery", "65", "sor", "", "", "cold mastery"], ["Blades of Ice", "274", "ass", "SQ", "16", "blades of ice"],
            ["BearSmite", "326", "", "", "", ""])
        tsv(mod, ["Innate Bloodbath", "65", "", "SQ", "16", "innatebloodbath"], ["Blades of Ice", "274", "ass", "SQ", "16", "x"],
            ["Batstrike", "326", "ass", "SQ", "16", "batstrike"], ["Other Class", "900", "sor", "SQ", "16", "y"])
        sm_file = root / "assassin_state_machine.json"
        sm_file.write_text(json.dumps(machine()), encoding="utf-8")
        names = ("D2R_SKILLS", "MOD_SKILLS", "OUT", "REPORT", "CLASSES")
        old = {k: getattr(H, k) for k in names}
        old_file = H.fxpaths.d2r_file

        def restore():
            for k, v in old.items():
                setattr(H, k, v)
            H.fxpaths.d2r_file = old_file
        self.addCleanup(restore)
        H.D2R_SKILLS, H.MOD_SKILLS, H.OUT, H.REPORT = d2r, mod, root / "out", root / "report.md"
        H.CLASSES = {"assassin": "ass"}
        H.fxpaths.d2r_file = lambda path: sm_file
        self.root = root

    def test_ids_d2r_does_not_animate_get_a_state(self):
        self.assertEqual(H.main(), 0)
        sm = json.loads((self.root / "out" / "assassin" / "assassin_state_machine.json").read_text("utf-8"))
        by_skill = {s["skillIndex"]: s for s in sm["states"]}
        self.assertIn(65, by_skill)   # Bloodbath: D2R's 65 is a passive with no sequence state
        self.assertIn(326, by_skill)  # Batstrike: D2R's 326 is a monster skill
        self.assertEqual(by_skill[326]["modeId"], 18)
        self.assertEqual(sum(1 for s in sm["states"] if s["skillIndex"] == 274), 1)  # D2R's own state kept, no copy
        self.assertNotIn(900, by_skill)  # another class's skill


if __name__ == "__main__":
    unittest.main()
