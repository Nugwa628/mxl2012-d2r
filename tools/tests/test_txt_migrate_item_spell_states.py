"""Bug #191: misc item spells whose timed state 1.13c skipped in silence and D2R verifies (`spellState > 0`, SkillItem.cpp:545 /
:823; `len` > 0, :548 / :826). pSpell 6 rows keep their cures and get the inert state for 1 frame; pSpell 9 rows get pSpell 0."""
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

# the built states.txt after clean_references: Median has no antidote / thawing / innersight / firepot
STATES = {"none", "freeze", "poison", "cold", "skilldelay", "healthpot", "regenpotion", "adrpot", "celerity", "magpot"}
INERT = tm.ITEM_SPELL_INERT_STATE


def row(**cells):
    return {"pSpell": "", "state": "", "cstate1": "", "cstate2": "", "len": "", "stat1": "", "calc1": "", **cells}


class ItemSpellStateTests(unittest.TestCase):
    def test_antidote_cures_poison_only(self):
        # yps: Median names D2R's `antidote` (emptied by clean_references), cstate1 poison, no len
        self.assertEqual(tm.item_spell_fix(row(pSpell="6", cstate1="poison"), STATES), {"state": INERT, "len": "1"})

    def test_thawing_cures_freeze_and_cold(self):
        fix = tm.item_spell_fix(row(pSpell="6", state="thawing", cstate1="freeze", cstate2="cold"), STATES)
        self.assertEqual(fix, {"state": INERT, "len": "1"})

    def test_adrenaline_without_len_keeps_its_cure(self):
        # ey9: adrpot exists but len is empty: 1.14d applied no state and still removed skilldelay
        fix = tm.item_spell_fix(row(pSpell="6", state="adrpot", cstate1="skilldelay"), STATES)
        self.assertEqual(fix, {"state": INERT, "len": "1"})

    def test_stats_of_a_skipped_state_are_not_applied(self):
        fix = tm.item_spell_fix(row(pSpell="6", cstate1="poison", len="500", stat1="hpregen", calc1="10"), STATES)
        self.assertEqual(fix, {"state": INERT, "len": "1", "stat1": "", "calc1": ""})

    def test_cure_without_any_valid_state_is_no_spell(self):
        self.assertEqual(tm.item_spell_fix(row(pSpell="6", state="antidote", cstate1="gone"), STATES), {"pSpell": "0"})

    def test_timed_state_missing_is_no_spell(self):
        # hrb (innersight), eo7 (firepot), 0g3 (strpot): 1.13c's handler returned 0, the item stayed
        self.assertEqual(tm.item_spell_fix(row(pSpell="9", len="1000", stat1="velocitypercent", calc1="25"), STATES),
                         {"pSpell": "0"})
        self.assertEqual(tm.item_spell_fix(row(pSpell="9", state="firepot", len="500"), STATES), {"pSpell": "0"})
        self.assertEqual(tm.item_spell_fix(row(pSpell="9", state="magpot", len="0"), STATES), {"pSpell": "0"})

    def test_working_rows_stay(self):
        healing = row(pSpell="6", state="regenpotion", cstate1="poison", cstate2="regenpotion", len="250",
                      stat1="hpregen", calc1="(stat('maxhp'.accr)/250)")
        self.assertEqual(tm.item_spell_fix(healing, STATES), {})
        self.assertEqual(tm.item_spell_fix(row(pSpell="9", state="celerity", len="750"), STATES), {})  # vps
        self.assertEqual(tm.item_spell_fix(row(pSpell="9", state="magpot", len="stat('x'.accr)"), STATES), {})  # a calc
        for p in ("", "0", "3", "8", "10", "-1"):
            self.assertEqual(tm.item_spell_fix(row(pSpell=p), STATES), {}, p)

    def test_inert_state_is_not_a_potion_state(self):
        self.assertEqual(INERT, "healthpot")
        self.assertNotIn(INERT, {"regenpotion", "adrpot", "celerity"})


if __name__ == "__main__":
    unittest.main()
