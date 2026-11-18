"""Unit tests of tools/effects_classic.py: the private rows, the refusal when another skill reaches a row, and a build of
the committed spec (that one skips when Median's art or the D2R particle templates are not on this machine).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_effects_classic.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import effect_sheet  # noqa: E402
import effects_classic as ecl  # noqa: E402
import effect_flipbook as ef  # noqa: E402
import fxpaths  # noqa: E402

HEADER = ["Missile", "*ID", "CelFile", "Trans", "ExplosionMissile", "SubMissile1"]
WANTED = {"mystar": {"copy": "shared", "at": [["mydamage", "ExplosionMissile"]]}}


def table() -> list[list[str]]:
    return [["mymover", "0", "Orb", "1", "", "mydamage"],
            ["mydamage", "1", "null", "1", "shared", ""],
            ["shared", "2", "Teeth", "1", "", ""],
            ["other", "3", "null", "1", "shared", ""]]


def dicts(rows: list[list[str]]) -> list[dict]:
    return [dict(zip(HEADER, r)) for r in rows]


SPEC = {"skills": ["My Skill"], "missiles": {"mymover": {}, "mydamage": {}, "mystar": {}}}
SKILLS = [{"skill": "My Skill", "srvmissile": "mymover"}, {"skill": "Other Skill", "srvmissile": "other"}]


class Rows(unittest.TestCase):
    def test_a_private_row_is_a_copy_with_the_next_id_and_only_its_owner_moves(self):
        rows = table()
        done = ecl.add_rows(HEADER, rows, WANTED)
        self.assertEqual(done, ["mystar: copy of shared"])
        self.assertEqual(rows[4], ["mystar", "4", "Teeth", "1", "", ""])
        self.assertEqual(rows[1][4], "mystar")                 # the skill's own missile now makes the private row
        self.assertEqual(rows[3][4], "shared")                 # every other user keeps the shared one
        self.assertEqual(rows[2], table()[2])                  # the shared row itself is untouched

    def test_a_second_run_changes_nothing(self):
        rows = table()
        ecl.add_rows(HEADER, rows, WANTED)
        once = [list(r) for r in rows]
        self.assertEqual(ecl.add_rows(HEADER, rows, WANTED), ["mystar: there already"])
        self.assertEqual(rows, once)

    def test_a_row_that_stopped_being_a_copy_is_refused(self):
        rows = table()
        ecl.add_rows(HEADER, rows, WANTED)
        rows[2][3] = "0"
        with self.assertRaises(SystemExit):
            ecl.add_rows(HEADER, rows, WANTED)

    def test_an_owner_that_names_something_else_is_refused(self):
        rows = table()
        rows[1][4] = "elsewhere"
        with self.assertRaises(SystemExit):
            ecl.add_rows(HEADER, rows, WANTED)


class Confined(unittest.TestCase):
    def test_only_the_skill_reaches_its_rows(self):
        rows = table()
        ecl.add_rows(HEADER, rows, WANTED)
        self.assertEqual(ecl.confined(SPEC, SKILLS, dicts(rows), [], [], []), [])

    def test_a_shared_row_in_the_spec_is_refused(self):
        spec = {"skills": ["My Skill"], "missiles": {"mymover": {}, "mydamage": {}, "shared": {}}}
        bad = ecl.confined(spec, SKILLS, dicts(table()), [], [], [])
        self.assertEqual(bad, ["missile other.ExplosionMissile -> shared"])

    def test_other_skills_monsters_states_and_items_are_seen(self):
        rows = table()
        ecl.add_rows(HEADER, rows, WANTED)
        bad = ecl.confined(SPEC, SKILLS + [{"skill": "Thief", "cltmissilea": "MyMover"}], dicts(rows),
                           [{"Id": "zombie", "MissA1": "mystar"}], [{"code": "jav", "missiletype": "1"}],
                           [{"state": "glow", "missile": "mydamage"}])
        self.assertEqual(len(bad), 4, bad)


class CommittedSpec(unittest.TestCase):
    def setUp(self):
        self.spec = ecl.load_spec()

    def test_the_spec_is_lanczos_and_every_private_row_is_drawn(self):
        self.assertEqual(self.spec.get("method", "lanczos"), "lanczos")       # nothing a build needs a GPU or a model for
        for row, how in self.spec["rows"].items():
            self.assertIn(row, self.spec["missiles"])
            self.assertNotIn(how["copy"], self.spec["missiles"])             # the shared row keeps its own effect
        names = [m["name"] for m in self.spec["missiles"].values()]
        self.assertEqual(len(names), len(set(names)))

    def test_the_build_writes_every_file_and_touches_only_its_rows(self):
        try:
            for how in self.spec["missiles"].values():
                if how.get("art"):
                    effect_sheet.art_path(how["art"])
            templates = {"flipbook": fxpaths.d2r_file(ef.TEMPLATE).read_bytes(),
                         "light": fxpaths.d2r_file(ef.LIGHT_TEMPLATE).read_bytes()}
        except (OSError, KeyError, ValueError, SystemExit):
            self.skipTest("no Median art or no D2R particle templates on this machine")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "data"
            mj = out / "hd" / "missiles" / "missiles.json"
            mj.parent.mkdir(parents=True)
            before = {"teethexplodeblue": "teethexplode", "firebolt": "fire_bolt", "bioneticmover": "psi_orb"}
            mj.write_text(json.dumps(before), "utf-8")
            facts = ecl.build(self.spec, out, templates)
            after = json.loads(mj.read_text("utf-8"))
            for row, how in self.spec["missiles"].items():
                self.assertEqual(after[row], how["name"])
                d = json.loads((out / "hd" / "missiles" / (how["name"] + ".json")).read_text("utf-8"))
                for kind in ("particles", "textures"):
                    for q in d["dependencies"][kind]:
                        self.assertTrue((out / q["path"][len("data/"):]).is_file(), q["path"])
                lights = [c for e in d["entities"] for c in e["components"] if c.get("filename", "").endswith("_light.particles")]
                self.assertEqual(len(lights), 1 if how.get("light") else 0)
            self.assertEqual({k: v for k, v in after.items() if k not in self.spec["missiles"]},
                             {"teethexplodeblue": "teethexplode", "firebolt": "fire_bolt"})
            self.assertEqual(facts["bioneticmover"]["was"], "psi_orb")
            self.assertLess(sum(f["deflated"] for f in facts.values()), 1_000_000)


if __name__ == "__main__":
    unittest.main()
