"""Unit tests of tools/hd_recolour.py (gradient tint of a D2R HD effect) on synthetic files (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_hd_recolour.py" """
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import d2r_texture  # noqa: E402
import hd_recolour as hr  # noqa: E402

GRAD = "data/hd/vfx/textures/gradient/T_FX_flame_gradient_01.texture"
GREY = "data/hd/vfx/textures/gradient/T_FX_grey_ramp_gradient.texture"
PART = "data/hd/vfx/particles/missiles/firebolt/vfx_firebolt_trail.particles"


def lp(path: str) -> bytes:
    return bytes([len(path)]) + path.encode()


class Base(unittest.TestCase):
    """A fake D2R tree: one particles file naming a colourful and a grey gradient (both RGBA8 256 x 16, 3 mips)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.d2r, self.cache, self.out = r / "d2r", r / "cache", r / "out"
        red = np.zeros((16, 256, 4), np.uint8)
        red[..., 0], red[..., 1], red[..., 3] = 220, np.arange(256)[None, :] // 4, 255
        grey = np.repeat(np.arange(256, dtype=np.uint8)[None, :, None], 16, 0).repeat(4, 2)
        for path, px in ((GRAD, red), (GREY, grey)):
            d2r_texture.write_rgba(self.cache / path, px, mips=3)
        self.particles = b"PKFX" + b"\0" * 20 + lp(GRAD) + b"\x07" + lp(GREY) + b"tail"
        (self.cache / PART).parent.mkdir(parents=True)
        (self.cache / PART).write_bytes(self.particles)
        self.patches = [mock.patch.object(hr, "D2R", self.d2r), mock.patch.object(hr.fxpaths, "D2R_CACHE", self.cache),
                        mock.patch.dict(os.environ, {"MXL_SLOT": "", "MXL_D2R_GAME": ""})]
        for p in self.patches:
            p.start()
        hr._grad.clear()
        hr._pix.clear()
        hr.ASKED.clear()
        hr.MISSING.clear()
        hr.WRITTEN.clear()
        self.spec = {"hue": 0.5, "sat": 0.0, "val": 0.0, "label": "hue +0.50"}

    def tearDown(self):
        for p in self.patches:
            p.stop()
        hr._grad.clear()
        hr._pix.clear()
        hr.WRITTEN.clear()
        self.tmp.cleanup()


class Reading(Base):
    def test_texture_refs_and_colour_gradients(self):
        self.assertEqual(hr.texture_refs(self.particles), [GRAD, GREY])
        self.assertEqual(hr.recolourable(PART), [GRAD])     # the grey ramp is left alone

    def test_missing_file_is_recorded_not_fatal(self):
        self.assertEqual(hr.casc_read("data/hd/vfx/particles/nothing.particles"), b"")
        self.assertIn("data/hd/vfx/particles/nothing.particles", hr.MISSING)
        self.assertFalse(hr.can_recolour({"entities": [{"components": [
            {"type": "VfxDefinitionComponent", "filename": "data/hd/vfx/particles/nothing.particles"}]}]}))


class Names(unittest.TestCase):
    def test_new_texture_path_keeps_length(self):
        n = hr.new_texture_path(GRAD, "abc123")
        self.assertEqual(len(n), len(GRAD))
        self.assertTrue(n.endswith("_abc123.texture"))

    def test_tags_are_unique_per_source(self):
        spec = {"hue": 0.1, "sat": 0.0, "val": 0.0}
        a = hr.new_texture_path("data/x/T_FX_flame_gradient_01.texture", hr.tag_of(spec, "data/x/T_FX_flame_gradient_01.texture"))
        b = hr.new_texture_path("data/x/T_FX_flame_gradient_02.texture", hr.tag_of(spec, "data/x/T_FX_flame_gradient_02.texture"))
        self.assertNotEqual(a, b)

    def test_recolour_name_keeps_length(self):
        spec = {"hue": 0.1, "sat": 0.0, "val": 0.0}
        self.assertEqual(len(hr.recolour_name("ground_fire_medium", spec)), len("ground_fire_medium"))
        self.assertNotEqual(hr.recolour_name("ground_fire_medium", spec), hr.recolour_name("ground_fire_mediun", spec))
        self.assertTrue(hr.recolour_name("fire", spec).startswith("mxl_fire_c"))

    def test_shift_pixels_rotates_hue_and_keeps_alpha(self):
        a = np.array([[[200, 0, 0, 77]]], np.uint8)
        b = hr.shift_pixels(a, 1 / 3, 0.0, 0.0)
        self.assertEqual(b[0, 0, 3], 77)
        self.assertGreater(b[0, 0, 1], 150)            # red -> green
        self.assertLess(b[0, 0, 0], 30)


class Writing(Base):
    def definition(self):
        return {"dependencies": {"particles": [{"path": PART}], "textures": []}, "type": "UnitDefinition",
                "name": "firebolt_trail", "entities": [{"components": [
                    {"type": "VfxDefinitionComponent", "filename": PART}, {"type": "TransformDefinitionComponent"}]}]}

    def test_dry_run_writes_nothing(self):
        nd = hr.recolour_def(None, self.definition(), self.spec, "firebolt_trail")
        self.assertIsNotNone(nd)
        self.assertFalse(self.out.exists())

    def test_recolour_def_sizes(self):
        d = self.definition()
        nd = hr.recolour_def(self.out, d, self.spec, hr.recolour_name(d["name"], self.spec))
        self.assertLessEqual(hr.size(nd), hr.size(d))   # same-length name, shorter mxl particles folder
        self.assertEqual(nd["dependencies"]["particles"][0]["path"], nd["entities"][0]["components"][0]["filename"])
        self.assertEqual(len(nd["dependencies"]["textures"]), 0)   # renamed in place, never added
        total, larger = hr.sizes(self.out)
        self.assertEqual(larger, [])
        self.assertEqual(len(hr.WRITTEN), 2)   # one gradient, one particles file
        new_part = next(k for k in hr.WRITTEN if k.endswith(".particles"))
        data = (self.out / new_part.split("/", 1)[1]).read_bytes()
        self.assertEqual(len(data), len(self.particles))
        self.assertIn(lp(GREY), data)           # the grey ramp is not touched
        self.assertNotIn(lp(GRAD), data)
        new_tex = next(k for k in hr.WRITTEN if k.endswith(".texture"))
        fmt, w, h, mips = hr.parse_texture((self.out / new_tex.split("/", 1)[1]).read_bytes())
        self.assertEqual((fmt, w, h, len(mips)), (d2r_texture.FMT_RGBA8, 256, 16, 3))
        px = np.frombuffer(mips[0], np.uint8).reshape(16, 256, 4)
        self.assertLess(px[0, 0, 0], px[0, 0, 2])    # red -> cyan / blue side

    def test_fits_refuses_a_larger_definition(self):
        src = self.d2r / "def.json"
        src.parent.mkdir(parents=True)
        src.write_text(json.dumps(self.definition(), separators=(",", ":")), "utf-8")
        self.assertTrue(hr.fits(src, self.definition(), self.spec, "firebolt_trail"))
        self.assertFalse(hr.fits(src, self.definition(), self.spec, "firebolt_trail_with_a_much_longer_name"))

    def test_clean_deletes_what_the_last_run_wrote(self):
        hr.recolour_def(self.out, self.definition(), self.spec, "firebolt_trail")
        rep = self.out.parent / "hd_recolour.json"
        hr.write_report(rep, [], self.out)
        written = list(json.loads(rep.read_text("utf-8"))["written"])
        self.assertEqual(hr.clean(rep, self.out), len(written))
        self.assertFalse(any((self.out / w.split("/", 1)[1]).exists() for w in written))


STOPS = ((0.0, 200, 40, 0), (1.0, 255, 220, 100))


class Overrides(Writing):
    """TINT_OVERRIDES (bug #403): a ramp named by an effect's rule is recoloured along explicit stops, whatever its
    saturation; everything else of the recolour stays as without the rule."""

    def setUp(self):
        super().setUp()
        self.rule = mock.patch.dict(hr.TINT_OVERRIDES, {("firebolt_trail", "fireart"): {"name": "fire",
                                                                                         "ramps": {GREY: STOPS}}})
        self.rule.start()

    def tearDown(self):
        self.rule.stop()
        super().tearDown()

    def test_ramp_pixels_follow_the_stops_and_keep_alpha(self):
        a = np.zeros((2, 3, 4), np.uint8)
        a[..., :3] = np.array([10, 128, 250], np.uint8)[None, :, None]
        a[..., 3] = 77
        r = hr.ramp_pixels(a, STOPS)
        self.assertEqual(r[0, 0, :3].tolist(), [200, 40, 0])       # darkest -> first stop
        self.assertEqual(r[0, 2, :3].tolist(), [255, 220, 100])    # brightest -> last stop
        self.assertTrue(200 < r[0, 1, 0] < 255)
        self.assertTrue((r[..., 3] == 77).all())
        flat = np.full((1, 4, 4), 250, np.uint8)
        self.assertEqual(hr.ramp_pixels(flat, STOPS)[0, 0, :3].tolist(), [255, 220, 100])

    def test_with_override_only_for_the_named_effect_and_art(self):
        self.assertIs(hr.with_override(self.spec, "firebolt_trail", "otherart"), self.spec)
        self.assertIs(hr.with_override(self.spec, "other", "fireart"), self.spec)
        o = hr.with_override(self.spec, "FireBolt_Trail", "FireArt")
        self.assertEqual((o["override"], o["ramps"]), ("fire", {GREY: STOPS}))
        self.assertIn("fire ramp", o["label"])
        self.assertEqual(self.spec, {"hue": 0.5, "sat": 0.0, "val": 0.0, "label": "hue +0.50"})   # not changed

    def test_tag_unchanged_without_override(self):
        import hashlib
        self.assertEqual(hr.tag_of(self.spec, GRAD), hashlib.md5(f"0.5/0.0/0.0/{GRAD}".encode()).hexdigest()[:6])
        self.assertNotEqual(hr.tag_of(hr.with_override(self.spec, "firebolt_trail", "fireart"), GRAD),
                            hr.tag_of(self.spec, GRAD))

    def test_override_recolours_the_grey_ramp_and_leaves_the_rest_as_before(self):
        d = self.definition()
        hr.recolour_def(self.out / "plain", d, self.spec, "firebolt_trail")
        plain = dict(hr.WRITTEN)
        hr.WRITTEN.clear()
        spec = hr.with_override(self.spec, "firebolt_trail", "fireart")
        nd = hr.recolour_def(self.out / "rule", d, spec, "firebolt_trail")
        self.assertEqual(sorted(hr.WRITTEN.values()), sorted([GRAD, GREY, PART]))
        new_part = next(k for k in hr.WRITTEN if k.endswith(".particles"))
        data = (self.out / "rule" / new_part.split("/", 1)[1]).read_bytes()
        self.assertEqual(len(data), len(self.particles))
        self.assertNotIn(lp(GREY), data)
        self.assertNotIn(lp(GRAD), data)
        self.assertEqual(nd["entities"][0]["components"][0]["filename"], new_part)

        def pixels(root, written, src):
            n = next(k for k, v in written.items() if v == src)
            _f, _w, _h, mips = hr.parse_texture((root / n.split("/", 1)[1]).read_bytes())
            return np.frombuffer(mips[0], np.uint8).reshape(16, 256, 4), len(mips)
        grey, nm = pixels(self.out / "rule", hr.WRITTEN, GREY)
        self.assertEqual(nm, 3)
        self.assertEqual(grey[0, 0, :3].tolist(), [200, 40, 0])
        self.assertEqual(grey[0, 255, :3].tolist(), [255, 220, 100])
        a, _ = pixels(self.out / "plain", plain, GRAD)
        b, _ = pixels(self.out / "rule", hr.WRITTEN, GRAD)
        self.assertTrue((a == b).all())     # the colourful gradient gets the same shift as without the rule

    def test_fire_rule_is_a_warm_rising_ramp(self):
        rule = hr.TINT_OVERRIDES[("ice_blast", "newfiremissile")]
        for stops in rule["ramps"].values():
            ts = [s[0] for s in stops]
            self.assertEqual((ts[0], ts[-1]), (0.0, 1.0))
            self.assertEqual(ts, sorted(ts))
            for _t, r, g, b in stops:
                self.assertTrue(r >= g >= b)
            self.assertEqual([sum(s[1:]) for s in stops], sorted(sum(s[1:]) for s in stops))

    def test_violet_rule_is_a_vivid_violet_rising_ramp(self):
        import colorsys
        rule = hr.TINT_OVERRIDES[("frost_nova", "purplefrostnova")]
        self.assertEqual(rule["name"], "violet")
        for stops in rule["ramps"].values():
            ts = [s[0] for s in stops]
            self.assertEqual((ts[0], ts[-1]), (0.0, 1.0))
            self.assertEqual(ts, sorted(ts))
            self.assertEqual([sum(s[1:]) for s in stops], sorted(sum(s[1:]) for s in stops))
            for _t, r, g, b in stops[:-1]:      # every stop but the bright top is violet (blue over red over green)
                h, s, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                self.assertTrue(0.72 <= h <= 0.82 and s >= 0.5, (r, g, b, h, s))
                self.assertTrue(b > r > g)


class PickTints(Writing):
    """A hand pick's `tint` column (lane picktint): the effect's colourful gradients, or the ones named, mapped onto a
    ramp of RAMPS; nothing else of the effect changes."""

    def test_parse_tint(self):
        self.assertIsNone(hr.parse_tint(" "))
        self.assertEqual(hr.parse_tint("Gold"), ("gold", ()))
        self.assertEqual(hr.parse_tint("green:T_FX_a + T_FX_b"), ("green", ("T_FX_a", "T_FX_b")))
        with self.assertRaises(ValueError):
            hr.parse_tint("plaid")

    def test_ramp_alone_takes_the_colourful_gradients(self):
        spec = hr.pick_spec("gold", [PART])
        self.assertEqual(spec["ramps"], {GRAD: hr.GOLD_RAMP})
        self.assertTrue(spec["only"])
        self.assertEqual(hr.recolourable(PART, spec), [GRAD])

    def test_named_gradient_only_even_when_grey(self):
        spec = hr.pick_spec("green:T_FX_grey_ramp_gradient", [PART])
        self.assertEqual(spec["ramps"], {GREY: hr.GREEN_RAMP})
        self.assertEqual(hr.recolourable(PART, spec), [GREY])          # the colourful one is not shifted
        nd = hr.recolour_def(self.out, self.definition(), spec, "firebolt_trail")
        self.assertEqual(sorted(hr.WRITTEN.values()), sorted([GREY, PART]))
        new_part = next(k for k in hr.WRITTEN if k.endswith(".particles"))
        data = (self.out / new_part.split("/", 1)[1]).read_bytes()
        self.assertIn(lp(GRAD), data)
        self.assertNotIn(lp(GREY), data)
        self.assertEqual(len(data), len(self.particles))
        self.assertEqual(nd["entities"][0]["components"][0]["filename"], new_part)

    def test_no_such_gradient_is_none(self):
        self.assertIsNone(hr.pick_spec("red:T_FX_not_there", [PART]))
        self.assertIsNone(hr.pick_spec("red", ["data/hd/vfx/particles/nothing.particles"]))

    def test_tags_differ_from_shift_and_by_ramp(self):
        a, b = hr.pick_spec("gold", [PART]), hr.pick_spec("red", [PART])
        self.assertNotEqual(hr.tag_of(a, GRAD), hr.tag_of(b, GRAD))
        self.assertNotEqual(hr.tag_of(a, GRAD), hr.tag_of(self.spec, GRAD))

    def test_pick_ramps_rise_and_have_their_hue(self):
        import colorsys
        for name, lo, hi in (("gold", 0.07, 0.15), ("green", 0.24, 0.36), ("red", -0.02, 0.03)):
            stops = hr.RAMPS[name]
            self.assertEqual([s[0] for s in stops], sorted(s[0] for s in stops))
            self.assertEqual([sum(s[1:]) for s in stops], sorted(sum(s[1:]) for s in stops))
            for _t, r, g, b in stops[:-1]:
                h, sat, _v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                h = h - 1 if h > 0.5 else h
                self.assertTrue(lo <= h <= hi and sat >= 0.5, (name, r, g, b, h, sat))


if __name__ == "__main__":
    unittest.main()
