"""Bug #565: a shapeshift form with bossinv draws the character's weapon and shield on the form in HD. The build clears bossinv on
the forms a skill gives its own caster and validate.py refuses any that are left."""
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

STATES = ["state", "*ID", "transform", "gfxtype", "gfxclass", "bossinv"]
SKILLS = ["skill", "aurastate", "auratargetstate"]
BUILT = TOOLS.parent / "work" / "mod" / "data" / "global" / "excel"


def rows():
    return [["tritonstate", "243", "1", "1", "1707", "1"], ["trapratstate", "281", "1", "1", "1706", "1"],
            ["porkulator", "184", "1", "1", "1764", "1"], ["deadringer", "157", "1", "2", "5", "1"],
            ["markwolf", "300", "", "", "", "1"], ["bear", "140", "1", "1", "431", ""]]


SKILL_ROWS = [["Treewarden Form", "tritonstate", ""], ["Trap Rat Form", "trapratstate", ""], ["Porkulator", "", "porkulator"],
              ["Dead Ringer", "deadringer", ""], ["Mark", "markwolf", ""], ["Merc Werebear", "bear", ""]]


def read(path):
    lines = path.read_text("utf-8-sig", errors="replace").splitlines()
    table = [line.split("\t") for line in lines]
    return table[0], table[1:]


class FormStateGear(unittest.TestCase):
    def test_a_form_showing_gear_is_found(self):
        self.assertEqual(tm.form_states_showing_gear(STATES, rows(), SKILLS, SKILL_ROWS), ["tritonstate", "trapratstate"])

    def test_the_fix_clears_only_the_caster_forms(self):
        r = rows()
        self.assertEqual(tm.form_state_gear_fix(STATES, r, SKILLS, SKILL_ROWS), ["tritonstate", "trapratstate"])
        self.assertEqual([x[5] for x in r], ["", "", "1", "1", "1", ""])
        self.assertEqual(tm.form_states_showing_gear(STATES, r, SKILLS, SKILL_ROWS), [])

    def test_a_form_put_on_a_target_keeps_its_boss_immunity(self):
        r = rows()
        tm.form_state_gear_fix(STATES, r, SKILLS, SKILL_ROWS)
        self.assertEqual(next(x for x in r if x[0] == "porkulator")[5], "1")

    def test_tables_without_the_columns_are_left_alone(self):
        self.assertEqual(tm.form_states_showing_gear(["state"], [["a"]], SKILLS, SKILL_ROWS), [])

    def test_validate_uses_the_same_rule(self):
        spec_v = importlib.util.spec_from_file_location("validate", TOOLS / "validate.py")
        v = importlib.util.module_from_spec(spec_v)
        spec_v.loader.exec_module(v)
        self.assertTrue(v.form_states_showing_gear.__code__.co_filename.endswith("txt_migrate.py"))

    @unittest.skipUnless((BUILT / "states.txt").exists() and (BUILT / "skills.txt").exists(), "needs a built mod")
    def test_no_form_of_the_built_mod_shows_gear(self):
        for bank in (BUILT, BUILT / "base"):
            self.assertEqual(tm.form_states_showing_gear(*read(bank / "states.txt"), *read(bank / "skills.txt")), [], bank)


if __name__ == "__main__":
    unittest.main()
