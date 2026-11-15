"""Unit tests of tools/missile_release.py (missiles another missile makes start where they are in HD, bug #569) on synthetic rows,
plus the audit of the built mod when one exists.
Run: py -3 -m unittest discover -s tools/tests -p "test_missile_release.py" """
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import effects_hd as fx  # noqa: E402
import fxpaths  # noqa: E402
import missile_looks as ml  # noqa: E402
import missile_release as mr  # noqa: E402

TRACKS = {"type": "UnitDefinition", "name": "arrow", "entities": [
    {"name": "entity_root", "components": [{"type": "UnitRootComponent"}]},
    {"name": "entity_vfx", "components": [{"type": "ModelDefinitionComponent", "filename": "arrow.model"},
                                          {"type": "TransformDefinitionComponent", "scale": {"x": 1.25}},
                                          {"type": mr.TRACK, "transitionTime": 0.5}]}]}
STILL = {"type": "UnitDefinition", "name": "blast", "entities": [{"components": [{"type": "VfxDefinitionComponent", "filename": "x"}]}]}
DEFS = {"arrow": TRACKS, "mxl_arrow_s140": {**TRACKS, "name": "mxl_arrow_s140"}, "blast": STILL}


def missiles():
    return [{"Missile": "legionmaker"},  # the skill's missile: walks and leaves tiles
            {"Missile": "legiontile", "SubMissile1": "legionpewpew"},
            {"Missile": "legionpewpew", "ExplosionMissile": "pewblast"},  # the archer's shot: made by the tile
            {"Missile": "pewblast"},
            {"Missile": "multishot", "SubMissile1": "multishot"},  # a skill's own missile that also makes itself
            {"Missile": "bladefragment1"},  # D2R's own row
            {"Missile": "bladefury1", "HitSubMissile1": "bladefragment1"},
            {"Missile": "bonearrow", "HitSubMissile1": "boneshard"},
            {"Missile": "boneshard"}]


CURRENT = {"legiontile": "blast", "legionpewpew": "arrow", "pewblast": "blast", "multishot": "arrow", "bladefragment_1": "arrow",
           "boneshard": "mxl_arrow_s140"}
SKILLS = [{"skill": "Phalanx", "srvmissilea": "legionmaker"}, {"skill": "Multiple Shot", "srvmissile": "multishot"}]
MONSTERS = [{"Id": "skeletonarcher", "MissA1": "bonearrow"}]


class Rules(unittest.TestCase):
    def setUp(self):
        self.launched = mr.thrown(SKILLS, MONSTERS, [], missiles())
        self.decided = dict(mr.decide(missiles(), self.launched, {"bladefragment1"}, CURRENT, DEFS.get))

    def test_tracks(self):
        self.assertTrue(mr.tracks(TRACKS))
        self.assertFalse(mr.tracks(STILL))
        self.assertFalse(mr.tracks(None))

    def test_made_by_another_missile_no_longer_tracks(self):
        self.assertEqual(self.decided.get("legionpewpew"), "arrow")
        self.assertEqual(self.decided.get("boneshard"), "mxl_arrow_s140", "a scaled variant is copied too")

    def test_kept(self):
        self.assertNotIn("multishot", self.decided, "a skill throws it: the glide from the hand is right")
        self.assertNotIn("bladefragment1", self.decided, "D2R's own row keeps D2R's model")
        self.assertNotIn("pewblast", self.decided, "its model has no glide")
        self.assertNotIn("legiontile", self.decided)

    def test_launched_by_units_and_items(self):
        rows = missiles() + [{"Missile": "throwknife", "*ID": "40"}]
        got = mr.thrown([], MONSTERS, [{"missiletype": "40"}, {"missiletype": ""}], rows)
        self.assertEqual(got, {"bonearrow", "throwknife"})

    def test_free_copy_drops_only_the_glide(self):
        d = mr.free_copy(TRACKS, "arrow_free")
        self.assertEqual(d["name"], "arrow_free")
        self.assertFalse(mr.tracks(d))
        kinds = [c["type"] for e in d["entities"] for c in e["components"]]
        self.assertEqual(kinds, ["UnitRootComponent", "ModelDefinitionComponent", "TransformDefinitionComponent"])
        self.assertTrue(mr.tracks(TRACKS), "the original is not changed")

    def test_apply_writes_copies_and_both_keys(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            final, written = mr.apply(sorted(self.decided.items()), CURRENT, out, DEFS.get)
            self.assertEqual(written, 2)
            self.assertEqual(final["legionpewpew"], "arrow_free")
            self.assertEqual(final[fx.norm_key("boneshard")], "mxl_arrow_s140_free")
            self.assertTrue((out / "arrow_free.json").exists())
            self.assertFalse(mr.tracks(fx.load_json(out / "mxl_arrow_s140_free.json")))
            self.assertEqual(final["multishot"], "arrow")

    def test_look_steps_see_through_the_copy(self):
        self.assertEqual(ml.scaled_base("arrow_free"), "arrow")
        self.assertEqual(ml.scaled_base("mxl_arrow_s140_free"), "arrow")
        self.assertEqual(ml.scaled_base("mxl_arrow_s140"), "arrow")


class BuiltMod(unittest.TestCase):
    """The audit on the built mod: no row only a missile makes starts in the caster's hand."""

    def test_built_mod(self):
        mj = fxpaths.MOD / "data" / "hd" / "missiles" / "missiles.json"
        if not mj.exists():
            self.skipTest("no built mod (work/mod)")
        r = subprocess.run([sys.executable, str(Path(mr.__file__)), "--check"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
