"""Stand-ins bind only clips their D2R unit has, and never use a unit D2R ships no model for (lane hdmon2)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import hd_monsters as hm  # noqa: E402
import hd_units as hu  # noqa: E402


def machine(folder="u"):
    def st(mode, name, clip):
        return {"name": f"State_{name}", "_name": name, "modeId": mode, "animationBindings": {"hth": [clip], "bow": []}}
    return {"name": "m", "animations": [{"name": c, "filename": f"data/hd/character/enemy/{folder}/animation/{c}.animation"}
                                        for c in ("neutral", "attack1", "attack2", "gethit", "death", "look")],
            "states": [st(1, "Neutral", "neutral"), st(4, "Attack1", "attack1"), st(5, "Attack2", "attack2"),
                       st(3, "GetHit", "gethit"), st(0, "Death", "death"), st(100, "Look", "look")]}


class ClipFill(unittest.TestCase):
    def test_missing_clips_take_the_first_fallback_the_unit_has(self):
        fill = hu.clip_fill(machine(), {"neutral", "attack1", "knockback", "death"})
        self.assertEqual(fill, {"attack2": "attack1", "gethit": "knockback"})

    def test_adapted_machine_rebinds_plain_modes_only(self):
        sm = machine()
        out = hu.adapt_state_machine(sm, None, "sm_u_fill", {"neutral", "attack1", "death"})
        b = {s["_name"]: s["animationBindings"]["hth"] for s in out["states"]}
        self.assertEqual(b["Attack2"], ["attack1"])
        self.assertEqual(b["GetHit"], ["neutral"])
        self.assertEqual(b["Look"], ["look"])          # layers / sequences (modeId 100, 14) are left alone
        self.assertEqual(sm["states"][2]["animationBindings"]["hth"], ["attack2"])   # donor's machine untouched

    def test_no_clip_data_means_no_change(self):
        self.assertEqual(hu.clip_fill(machine(), None), {})
        self.assertIsNone(hu.sm_clips(machine("other"), {"u": ["neutral"]}))

    def test_sm_clips_ignore_case(self):
        self.assertEqual(hu.sm_clips(machine(), {"u": ["Neutral", "attack1"]}), {"neutral", "attack1"})

    def test_has_model(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "data/hd/character/enemy").mkdir(parents=True)
            for u, model in (("a", "data/hd/character/enemy/a/torso.model"), ("b", "data/hd/character/enemy/b/torso.model")):
                (root / f"data/hd/character/enemy/{u}.json").write_text(
                    json.dumps({"dependencies": {"models": [{"path": model}]}}), "utf-8")
            hu.configure(root)
            files = {"data/hd/character/enemy/a/torso_lod0.model"}
            self.assertTrue(hu.has_model("a", files))
            self.assertFalse(hu.has_model("b", files))
            self.assertFalse(hu.has_model("c", files))



def numbered(states):
    """A machine of (stateId, modeId, name, clip) states, each with transitions to every state (lane hdmon3)."""
    ids = [s[0] for s in states]
    return {"name": "m", "animations": [],
            "states": [{"type": "AnimationState", "name": f"State_{n}", "_name": n, "stateId": i, "modeId": m, "skillIndex": 7,
                        "stepIndex": 1, "enterEvents": ["vfx"], "exitEvents": [], "animationBindings": {"1hs": [c], "hth": []}}
                       for i, m, n, c in states],
            "transitions": [{"type": "AnimationTransitionGroup", "name": f"{i}_transitions", "from": i,
                             "settings": [{"type": "AnimationTransitionItem", "name": f"{i}_to_{j}", "crossfadeSeconds": 0.2, "to": j}
                                          for j in ids if j != i]} for i in ids]}


FULL = [(0, 0, "Death", "death"), (1, 1, "Neutral", "neutral"), (2, 100, "Walk", "walk"), (3, 3, "GetHit", "gethit"),
        (4, 4, "Attack1", "attack1"), (12, 12, "Dead", "dead"), (13, 13, "Knockback", "knockback")]


class StateFill(unittest.TestCase):
    def test_a_mode_played_only_as_a_sequence_gets_that_clip(self):
        # frozenhorror1: attack2 is State_Attack2 with modeId 14 (a skill sequence); Median's Shardspawn uses mode A2
        sm = numbered(FULL + [(5, 14, "Attack2_Sequence", "attack2")])
        self.assertEqual(hu.state_fill(sm)[5], 5)

    def test_a_mode_without_any_state_takes_the_fallback_clip(self):
        # colbarbwhirl: no Block / Cast / Skill states; cast falls back to attack2, block to gethit
        sm = numbered(FULL + [(5, 5, "Attack2", "attack2")])
        f = hu.state_fill(sm)
        self.assertEqual((f[6], f[7], f[8], f[11]), (3, 5, 5, 5))
        self.assertNotIn(5, f)
        self.assertNotIn(2, f)            # walk / run are named layers in many machines: never filled by modeId

    def test_added_states_are_plain_copies_with_the_copied_state_transitions(self):
        sm = numbered(FULL + [(5, 14, "Attack2_Sequence", "attack2")])
        out = hu.adapt_state_machine(sm, "hth", "sm_x_fill")
        new = [s for s in out["states"] if s["_name"].endswith("_Fill")]
        a2 = next(s for s in new if s["modeId"] == 5)
        self.assertEqual((a2["skillIndex"], a2["stepIndex"], a2["enterEvents"]), (-1, 0, []))
        self.assertEqual(a2["animationBindings"]["hth"], ["attack2"])     # bound for Median's weapon class as well
        self.assertEqual(len({s["stateId"] for s in out["states"]}), len(out["states"]))
        groups = {g["from"]: g for g in out["transitions"]}
        self.assertIn(a2["stateId"], groups)
        self.assertIn(a2["stateId"], [i["to"] for i in groups[1]["settings"]])
        self.assertEqual(len(sm["transitions"]), len(FULL) + 1)           # donor's machine untouched

    def test_complete_machine_is_left_alone(self):
        sm = numbered(FULL + [(5, 5, "Attack2", "attack2"), (6, 6, "Block", "block"), (7, 7, "Cast", "cast")]
                      + [(k, k, f"Skill{k - 7}", f"skill{k - 7}") for k in range(8, 12)])
        self.assertEqual(hu.state_fill(sm), {})


class Committed(unittest.TestCase):
    def test_clip_index_is_well_formed(self):
        idx = hm.load_clips()
        self.assertGreater(len(idx), 100)
        for folder, clips in idx.items():
            self.assertEqual(clips, sorted(set(clips)), folder)

    @unittest.skipUnless((Path(str(fxpaths.D2R)) / "data/hd/character/enemy").exists(), "no D2R baseline extract")
    def test_every_standin_donor_has_a_model(self):
        hu.configure(Path(str(fxpaths.D2R)))
        files = hm.d2r_files(Path(str(fxpaths.D2R)))
        tokens = json.loads(hm.TOKENS_JSON.read_text("utf-8"))["tokens"]
        for tok, e in tokens.items():
            if e.get("donor") and e["class"] != "noart":
                self.assertTrue(hu.has_model(e["donor"], files), f"{tok}: {e['donor']} has no model in D2R")

    @unittest.skipUnless((Path(str(fxpaths.D2R)) / "data/hd/character/enemy").exists(), "no D2R baseline extract")
    def test_state_fill_of_the_committed_donors(self):
        # lane hdmon3: the donors with a mode that has no state at all (docs/hd-monsters.md section 11)
        hu.configure(Path(str(fxpaths.D2R)))
        tokens = json.loads(hm.TOKENS_JSON.read_text("utf-8"))["tokens"]
        got = {}
        for e in tokens.values():
            if e.get("donor") and e["donor"] not in got and hu.unit_info(e["donor"]):
                f = hu.state_fill(hu.load_json(Path(str(fxpaths.D2R)) / hu.unit_info(e["donor"])["sm"]))
                if f:
                    got[e["donor"]] = sorted(f)
        self.assertEqual(got, {"frozenhorror1": [5]})   # colbarbwhirl (no Block / Cast / Skill states) is no donor since hdmon3


class LookChecks(unittest.TestCase):
    def test_hm_check_lists_name_the_committed_stand_ins(self):
        # game_checks hm2_monsters / hm3_monsters (lanes hdmon2 / hdmon3): each Id belongs to a token whose committed donor is
        # the stand-in the list says, so the shots are judged against the right unit (`monsters`: the Ids the mapping names)
        os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
        import game_checks as gc
        tokens = json.loads(hm.TOKENS_JSON.read_text("utf-8"))["tokens"]
        donor = {mid: e.get("donor") for e in tokens.values() for mid in e.get("monsters", [])}
        for area, mid, what in gc.HM2_MONSTERS + gc.HM3_MONSTERS:
            self.assertIn(mid, donor, mid)
            self.assertEqual(donor[mid], what.split(",")[0], mid)
        self.assertEqual(len({m for _a, m, _w in gc.HM3_MONSTERS}), len(gc.HM3_MONSTERS))


if __name__ == "__main__":
    unittest.main()
