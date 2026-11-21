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

    def test_a_row_marked_shared_may_be_reached_by_anything(self):
        spec = {"skills": ["My Skill"], "missiles": {"mymover": {}, "mydamage": {}, "shared": {"shared": "same art for all"}}}
        rows = table()
        self.assertEqual(ecl.confined(spec, SKILLS + [{"skill": "Thief", "srvmissile": "shared"}], dicts(rows),
                                      [{"Id": "zombie", "MissA1": "shared"}], [], []), [])

    def test_opaque_art_needs_the_spec_to_say_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            excel = Path(tmp)
            (excel / "missiles.txt").write_text("Missile\tCelFile\tTrans\narcher\tLegionTile\t0\n", "utf-8")
            spec = {"skills": [], "missiles": {"archer": {"art": "missiles/LegionTile"}}}
            self.assertTrue(any("Trans is '0'" in b for b in ecl.problems(spec, excel)))
            spec["missiles"]["archer"]["opaque"] = "drawn as colour layers"
            self.assertEqual(ecl.problems(spec, excel), [])

    def test_an_overlay_must_be_shared_and_match_its_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            excel = Path(tmp)
            (excel / "missiles.txt").write_text("Missile\tCelFile\tTrans\n", "utf-8")
            (excel / "overlay.txt").write_text("overlay\tFilename\tCharacter\tTrans\nbarb_1\tvdfeathers\tmonster\t5\n", "utf-8")
            spec = {"skills": [], "missiles": {}, "overlays": {"barb_1": {"art": "overlays/vdfeathers"}}}
            bad = ecl.problems(spec, excel)
            self.assertTrue(any("`shared`" in b for b in bad), bad)          # every state that shows it gets the look
            self.assertTrue(any("Trans is '5'" in b for b in bad), bad)
            spec["overlays"]["barb_1"].update(shared="the stances", opaque="lifted, tinted")
            self.assertEqual(ecl.problems(spec, excel), [])
            spec["overlays"]["barb_1"]["art"] = "overlays/other"
            self.assertTrue(any("Filename is 'vdfeathers'" in b for b in ecl.problems(spec, excel)))
            spec["overlays"] = {"nope": {"art": "overlays/vdfeathers", "shared": "x"}}
            self.assertIn("no overlay.txt row nope", ecl.problems(spec, excel))
            self.assertEqual(ecl.overlay_folder(excel, "BARB_1"), "monster")

    def test_an_overlay_definition_has_no_unit_root(self):
        unit = ef.definition("mxl_fx_x", [{"particle": "data/p.particles", "texture": "data/t.texture", "pos": (0, 1, 0)}], True)
        d = ecl.overlay_definition("Barb_1", unit)
        self.assertEqual((d["type"], d["name"]), ("OverlayDefinition", "barb_1"))
        self.assertEqual([e["name"] for e in d["entities"]], ["entity_vfx1"])
        self.assertEqual(d["dependencies"], unit["dependencies"])

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
            excel = out / "global" / "excel"
            excel.mkdir(parents=True)
            (excel / "overlay.txt").write_text("overlay\tFilename\tCharacter\tTrans\n" + "".join(
                "%s\t%s\tmonster\t5\n" % (o, how["art"].split("/")[-1]) for o, how in self.spec["overlays"].items()), "utf-8")
            facts = ecl.build(self.spec, out, templates)
            for row, how in self.spec["overlays"].items():
                d = json.loads((out / "hd" / "overlays" / "monster" / (row + ".json")).read_text("utf-8"))
                self.assertEqual((d["type"], d["name"]), ("OverlayDefinition", row))
                for kind in ("particles", "textures"):
                    for q in d["dependencies"][kind]:
                        self.assertTrue((out / q["path"][len("data/"):]).is_file(), q["path"])
                self.assertIsNone(facts["overlay:" + row]["was"])          # none there before in this test
                if any(q.get("blend") == "alpha" for q in how.get("parts", [])):   # the coverage atlas goes with it
                    self.assertTrue(any(q["path"].endswith("_alpha.texture") for q in d["dependencies"]["textures"]), d["dependencies"])
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
            # the feathers (#578) are a colour and a coverage atlas (alpha-blended), about 0.27 MB of the total
            self.assertLess(sum(f["deflated"] for f in facts.values()), 1_250_000)


if __name__ == "__main__":
    unittest.main()
