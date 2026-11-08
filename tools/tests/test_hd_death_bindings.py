"""Bug #34: the death states of a stand-in's state machine must also bind hth, the class of Median's death COFs."""
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import hd_units as hu  # noqa: E402


def machine(death, neutral):
    return {"name": "m", "states": [
        {"name": "State_Death", "modeId": 0, "animationBindings": dict(death)},
        {"name": "State_Neutral", "modeId": 1, "animationBindings": dict(neutral)},
        {"name": "State_Dead", "modeId": 12, "animationBindings": dict(death)}]}


class DeathBindingTests(unittest.TestCase):
    def test_bow_only_death_lacks_hth(self):
        self.assertTrue(hu.death_lacks_hth(machine({"bow": ["death"], "hth": []}, {"bow": ["neutral"]})))

    def test_hth_death_is_fine(self):
        self.assertFalse(hu.death_lacks_hth(machine({"hth": ["death"], "bow": []}, {"2hs": ["neutral"]})))

    def test_adapted_machine_binds_hth_on_the_death_states_only(self):
        sm = machine({"bow": ["death"]}, {"bow": ["neutral"]})
        out = hu.adapt_state_machine(sm, None, "sm_x")
        self.assertEqual(out["states"][0]["animationBindings"]["hth"], ["death"])
        self.assertEqual(out["states"][2]["animationBindings"]["hth"], ["death"])
        self.assertNotIn("hth", out["states"][1]["animationBindings"])
        self.assertNotIn("hth", sm["states"][0]["animationBindings"])   # the donor's machine is not touched
        self.assertEqual(out["name"], "sm_x")

    def test_weapon_binding_still_added_and_existing_hth_kept(self):
        sm = machine({"hth": ["dead2"]}, {"hth": ["neutral"]})
        out = hu.adapt_state_machine(sm, "1hs", "sm_y")
        self.assertEqual(out["states"][1]["animationBindings"]["1hs"], ["neutral"])
        self.assertEqual(out["states"][0]["animationBindings"]["hth"], ["dead2"])


class DeathClipTests(unittest.TestCase):
    """Bug #560: a stand-in whose Death / Dead states bind no clip it has (D2R's `wolf`) leaves its dead monsters standing."""

    def test_wolf_like_machine_is_unplayable(self):
        sm = machine({"hth": ["death"]}, {"hth": ["neutral"]})
        self.assertTrue(hu.death_unplayable(sm, {"neutral", "knockback", "gethit"}))

    def test_machine_with_death_clips_is_fine(self):
        sm = machine({"hth": ["death"]}, {"hth": ["neutral"]})
        self.assertFalse(hu.death_unplayable(sm, {"neutral", "death", "dead"}))
        self.assertFalse(hu.death_unplayable(sm, None))   # clips not indexed: nothing to judge

    def test_binding_names_resolve_to_animation_files(self):
        sm = machine({"hth": ["dead001"]}, {"hth": ["neutral"]})   # bonefetish1 binds animation names, not clip names
        sm["animations"] = [{"name": "dead001", "filename": "data/hd/character/enemy/bonefetish1/animation/dead.animation"}]
        self.assertFalse(hu.death_unplayable(sm, {"neutral", "dead"}))
        self.assertTrue(hu.death_unplayable(sm, {"neutral"}))

    def test_committed_mapping_has_no_deathless_stand_in(self):
        """Every stand-in donor in the committed mapping whose tokens die has death clips (D2R's `wolf` had none)."""
        import json
        clips = json.loads((TOOLS / "data" / "d2r_unit_clips.json").read_text("utf-8"))["folders"]
        tokens = json.loads((TOOLS / "data" / "hd_monster_tokens.json").read_text("utf-8"))["tokens"]
        bad = [(t, e["donor"]) for t, e in tokens.items()
               if e.get("donor") in clips and not ({"death", "dead"} <= {c.lower() for c in clips[e["donor"]]})
               and e.get("ids_mapped", e.get("stand_in_ids"))]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
