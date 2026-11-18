"""Unit tests of tools/effect_flipbook.py and tools/effect_chain.py on pictures and table rows made here (no game files;
the two tests that edit D2R's own particle files skip when the extraction is not there).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_effect_flipbook.py" """
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import effect_chain as ec  # noqa: E402
import effect_flipbook as ef  # noqa: E402
import fxpaths  # noqa: E402
import hd_cbvm as cb  # noqa: E402
import hd_particles as hp  # noqa: E402


def glow(size: int = 24, colour=(40, 100, 255)) -> np.ndarray:
    """A round one-hue glow on black."""
    y, x = np.mgrid[:size, :size]
    v = np.clip(1.0 - np.hypot(x - size / 2, y - size / 2) / (size / 2), 0, 1)
    return (v[..., None] * np.asarray(colour)).astype(np.uint8)


def d2r(path: str) -> bytes | None:
    try:
        return fxpaths.d2r_file(path).read_bytes()
    except (OSError, KeyError, ValueError, SystemExit):   # d2r_file exits when neither the extraction nor the cache has it
        return None


class Colour(unittest.TestCase):
    def test_levels_tell_blue_from_white(self):
        px = np.array([[[0, 0, 255], [255, 255, 255], [0, 0, 0], [10, 20, 30]]], np.uint8)
        self.assertEqual(ef.levels(px, "mean").tolist(), [[85, 255, 0, 20]])
        self.assertEqual(ef.levels(px, "max").tolist(), [[255, 255, 0, 30]])
        self.assertEqual(ef.levels(px, "g").tolist(), [[0, 255, 0, 20]])

    def test_own_ramp_gives_a_one_hue_picture_back(self):
        g = glow()
        ramp = ef.own_ramp(g)
        self.assertEqual(ramp.shape, (256, 4))
        self.assertEqual(ramp[0, :3].tolist(), [0, 0, 0])
        self.assertLess(ef.ramp_error(g, ramp), 1.0)
        self.assertLess(ef.hue_spread([g]), ef.MULTI_HUE)

    def test_two_hues_at_one_level_need_layers(self):
        both = np.concatenate([glow(colour=(255, 255, 255)), glow(colour=(0, 60, 255))], axis=1)
        self.assertGreater(ef.hue_spread([both]), ef.MULTI_HUE)

    def test_channel_layers_add_up_to_the_picture(self):
        both = np.concatenate([glow(colour=(255, 255, 255)), glow(colour=(0, 60, 255))], axis=1)
        grey = np.arange(256)
        back = np.dstack([grey[ef.levels(both, c)] for c in "rgb"])
        self.assertTrue(np.array_equal(back, both))


class Picture(unittest.TestCase):
    def test_grid_and_atlas(self):
        frames = [glow(20) for _ in range(7)]
        pixels, grid, cell = ef.atlas(frames, 1)
        self.assertGreaterEqual(grid[0] * grid[1], 7)
        self.assertEqual(pixels.shape[:2], (grid[1] * cell, grid[0] * cell))
        self.assertGreaterEqual(cell, 20 + 2 * ef.MARGIN)

    def test_upscale_keeps_black_black_and_mixes(self):
        frames = [np.pad(glow(16), ((8, 8), (8, 8), (0, 0)))]
        sharp = ef.upscale(frames, 2, "lanczos")[0]
        self.assertEqual(sharp.shape, (64, 64, 3))
        self.assertEqual(int(sharp[:4, :4].max()), 0)
        mixed = ef.upscale(frames, 2, "mix:0.5:lanczos")[0]
        self.assertLessEqual(int(np.abs(mixed.astype(int) - sharp.astype(int)).max()), 1)
        soft = ef.upscale(frames, 2, "blur:2:lanczos")[0]
        self.assertLess(int(soft.max()), int(sharp.max()))
        self.assertIs(ef.upscale(frames, 1, "lanczos")[0], frames[0])


class Definition(unittest.TestCase):
    def test_layers_and_a_light_in_one_definition(self):
        parts = [{"particle": "data/hd/a.particles", "texture": "data/hd/a.texture", "pos": (0.0, 3.5, 0.0)},
                 {"particle": "data/hd/a_light.particles", "texture": None, "pos": (0.0, 1.0, 0.0)}]
        d = ef.definition("mxl_fx_a", parts, True)
        self.assertEqual([p["path"] for p in d["dependencies"]["particles"]], ["data/hd/a.particles", "data/hd/a_light.particles"])
        self.assertEqual([p["path"] for p in d["dependencies"]["textures"]], ["data/hd/a.texture"])
        vfx = [c for e in d["entities"] for c in e["components"] if c["type"] == "VfxDefinitionComponent"]
        self.assertEqual(len(vfx), 2)
        self.assertTrue(all(c["hardKillOnDestroy"] for c in vfx))
        ids = [e["id"] for e in d["entities"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_light_of_a_missiles_row(self):
        self.assertIsNone(ef.light_of({"Light": "", "Blue": "255"}))
        lamp = ef.light_of({"Light": "7", "Red": "0", "Green": "0", "Blue": "255"})
        self.assertEqual(lamp["rgb"], (0.0, 0.0, 1.0))
        self.assertEqual(lamp["range"], 7 * ef.LIGHT_REACH)
        self.assertEqual(ef.light_of({"Light": "3"})["rgb"], (1.0, 1.0, 1.0))


class GameFiles(unittest.TestCase):
    def test_point_light_carries_colour_and_reach(self):
        tpl = d2r(ef.LIGHT_TEMPLATE)
        if tpl is None:
            self.skipTest("no D2R extraction")
        pf = hp.ParticleFile(ef.point_light(tpl, (0.0, 0.0, 1.0), 21.0))
        consts = [cb._const_text(c) for s in cb.scripts(pf) for c in s.consts]
        self.assertTrue(any(c.startswith("f 0.0 0.0 1.0 1.0") for c in consts))
        self.assertTrue(any(c.startswith("f 21.0") for c in consts))
        self.assertFalse(any(c.startswith("f 0.89000") for c in consts))

    def test_particles_reads_no_input_from_the_life_stream(self):
        tpl = d2r(ef.TEMPLATE)
        if tpl is None:
            self.skipTest("no D2R extraction")
        for mode in ("loop", "once"):
            data = ef.particles(tpl, "data/hd/vfx/textures/mxl/flipbook/x.texture", (4, 3), 11, mode, 4.0,
                                gradient="data/hd/vfx/textures/gradient/mxl_fb_x.texture")
            self.assertIn(b"mxl/flipbook/x.texture", data)
            self.assertGreater(len(hp.ParticleFile(data).objects), 50)


class Chain(unittest.TestCase):
    SKILLS = [{"skill": "Bionetic Slam", "id": "329", "srvmissilea": "Mover", "cltmissilea": "mover"}]
    MISSILES = [{"missile": "mover", "celfile": "PsiOrb", "explosionmissile": "boom", "hitsubmissile1": "damage"},
                {"missile": "boom", "celfile": "PsiOrbExplode"},
                {"missile": "damage", "celfile": "null", "explosionmissile": "teeth"},
                {"missile": "teeth", "celfile": "TeethExplode", "submissile1": "mover"},
                {"missile": "other", "celfile": "X"}]

    def test_a_skill_reaches_the_missiles_behind_its_missiles(self):
        start = ec.skill_missiles(self.SKILLS, "329")
        self.assertEqual(start, ["mover", "mover"])
        links = ec.chain(self.MISSILES, start)
        self.assertEqual([link["missile"] for link in links], ["mover", "boom", "damage", "teeth"])
        self.assertEqual(links[3]["via"], "damage.explosionmissile")
        self.assertEqual(ec.skill_missiles(self.SKILLS, "bionetic slam"), start)

    def test_a_name_without_a_row_is_reported(self):
        links = ec.chain(self.MISSILES, ["gone"])
        self.assertEqual(links, [{"missile": "gone", "via": "", "row": None}])
        with self.assertRaises(KeyError):
            ec.skill_missiles(self.SKILLS, "999")


if __name__ == "__main__":
    unittest.main()
