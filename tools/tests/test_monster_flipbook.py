"""tools/monster_flipbook.py and tools/monster_upscale.py: the frame and direction timing, the cards' geometry, the state
machine and the sprite upscale's colour and alpha handling (no game data, no outside scaler needed)."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401
import monster_card as mc  # noqa: E402
import monster_flipbook as mf  # noqa: E402
import monster_sheet as ms  # noqa: E402
import monster_upscale as mu  # noqa: E402


def on_at(knots, on, t):
    """The state of a linear on / off curve at time t (on: above half way)."""
    return np.interp(t, knots, [1.0 if o else 0.0 for o in on]) > 0.5


class Timing(unittest.TestCase):
    def test_exactly_one_frame_is_on_at_any_time(self):
        n, dt = 15, mf.TICK
        curves = [mf.frame_keys(f, n, dt) for f in range(n)]
        for step in range(n * 20):
            t = (step + 0.5) * dt / 20
            lit = [f for f, (knots, on) in enumerate(curves) if on_at(knots, on, t)]
            self.assertEqual(lit, [int(t / dt)], t)

    def test_frame_knots_rise_and_span_the_clip(self):
        for n in (1, 2, 16):
            for f in range(n):
                knots, on = mf.frame_keys(f, n, mf.TICK)
                self.assertEqual(knots, sorted(knots))
                self.assertEqual((knots[0], knots[-1]), (0.0, n * mf.TICK))
                self.assertEqual(len(knots), len(on))

    def test_one_direction_sector_is_on_away_from_the_start(self):
        n, length = 8, mf.AIM_SECONDS
        curves = [mf.sector_keys(j, n, length) for j in range(n)]
        for step in range(1, 160):
            t = step * length / 160
            if t < length / n * mf.EDGE or abs((t / (length / n)) % 1 - 0.5) < 0.05:   # the start pose, a sector edge
                continue
            lit = [j for j, (knots, on) in enumerate(curves) if on_at(knots, on, t)]
            self.assertEqual(lit, [int(round(t / (length / n))) % n], t)

    def test_every_direction_is_on_in_the_first_pose(self):
        self.assertTrue(all(mf.sector_keys(j, 8, 1.0)[1][0] for j in range(8)))


class Bones(unittest.TestCase):
    def test_direction_bones_first_then_frames_by_mode(self):
        names = mf.bone_names({"nu": 2, "a1": 1}, (4, 0))
        self.assertEqual(names, ["d4", "d0", "fnu00", "fnu01", "fa100"])
        self.assertEqual(len(set(names)), len(names))

    def test_a_card_hangs_on_its_direction_and_frame_bone(self):
        where = {("nu", 4, 0): (0, 0, 10, 20, -5, -20, 10, 20), ("nu", 0, 1): (10, 0, 10, 20, -5, -20, 10, 20)}
        bones = mf.bone_names({"nu": 2}, (4, 0))
        verts, tris = mf.mesh(where, (32, 32), bones)
        self.assertEqual((len(verts), len(tris)), (8, 4))
        pairs = {v[-1] for v in verts}
        self.assertEqual(pairs, {(bones.index("d0"), bones.index("fnu01")), (bones.index("d4"), bones.index("fnu00"))})
        self.assertTrue(all(max(t) < len(verts) for t in tris))


class Turning(unittest.TestCase):
    def test_a_positive_turn_takes_forward_to_the_right(self):
        x, y, z = mf.turned((0.0, 3.0, 1.0), math.radians(90))
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 3.0)
        self.assertAlmostEqual(z, 0.0)

    def test_the_eight_directions_are_45_degrees_apart(self):
        yaws = [math.degrees(mf.unit_yaw(d)) for d in ms.CLOCKWISE_8]
        self.assertEqual([round(a) for a in yaws], [45 - 45 * k for k in range(8)])

    def test_a_turned_back_card_faces_the_camera_again(self):
        where = {("nu", d, 0): (0, 0, 10, 20, -5, -20, 10, 20) for d in (4, 6)}
        bones = mf.bone_names({"nu": 1}, (4, 6))
        flat, _ = mf.mesh(where, (32, 32), bones)
        turn = {d: mf.unit_yaw(d) for d in (4, 6)}
        fan, _ = mf.mesh(where, (32, 32), bones, turn)
        for a, b in zip(flat, fan):
            d = int(bones[b[-1][0]][1:])
            back = mf.turned(b[0], turn[d])          # what the engine does to the model of a unit that faces d
            for p, q in zip(a[0], back):
                self.assertAlmostEqual(p, q, places=4)

    def test_leaning_narrows_the_window_of_a_one_sided_card(self):
        self.assertAlmostEqual(mf.cull_window(0.0), 90.0)
        self.assertAlmostEqual(mf.cull_window(50.77), 45.0, places=1)
        self.assertEqual(mf.cull_window(61.0), 0.0)
        self.assertGreater(mf.cull_window(30.0), mf.cull_window(45.0))

    def test_a_leaned_point_stays_on_the_ground_line(self):
        self.assertEqual(mf.leaned((2.0, 0.0, 5.0), 40.0), (2.0, 0.0, 5.0))
        x, y, z = mf.leaned((0.0, 10.0, 0.0), 40.0)
        self.assertGreater(x, 0.0)                    # towards the camera
        self.assertAlmostEqual(x, z)

    def test_the_marker_lies_on_the_ground_along_both_axes(self):
        verts, tris = mf.marker((0.1, 0.1, 0.2, 0.2), 3)
        self.assertEqual((len(verts), len(tris)), (8, 4))
        self.assertEqual({v[0][1] for v in verts}, {0.05})
        self.assertEqual(max(v[0][0] for v in verts), 8.0)
        self.assertEqual(max(v[0][2] for v in verts), 4.0)
        self.assertEqual({v[-1] for v in verts}, {(3, 3)})


class Atlas(unittest.TestCase):
    def test_gain_brightens_the_colour_and_keeps_alpha(self):
        px = np.zeros((2, 2, 4), np.uint8)
        px[..., :3], px[..., 3] = (100, 200, 10), 77
        out = mf.brightened(px, 1.5)
        self.assertEqual(out[0, 0].tolist(), [150, 255, 15, 77])
        self.assertEqual(px[0, 0].tolist(), [100, 200, 10, 77])

    def test_solid_uv_lies_inside_an_opaque_block(self):
        px = np.zeros((16, 16, 4), np.uint8)
        px[4:12, 6:14, 3] = 255
        u0, v0, u1, v1 = mf.solid_uv(px)
        self.assertTrue(6 / 16 < u0 < u1 < 14 / 16 and 4 / 16 < v0 < v1 < 12 / 16)
        with self.assertRaises(ValueError):
            mf.solid_uv(np.zeros((8, 8, 4), np.uint8))


class Machine(unittest.TestCase):
    def setUp(self):
        self.sm = mf.state_machine("x_statemachine", "data/hd/x", ["neutral", "walk", "attack1", "death", "dead"],
                                   {"nu": 15, "wl": 16, "a1": 15, "dt": 20})

    def test_every_mode_but_the_sequence_has_a_state(self):
        modes = {s["modeId"] for s in self.sm["states"]}
        self.assertEqual(modes, set(mf.MODE_IDS.values()) - {mf.MODE_IDS["sq"]})

    def test_a_mode_without_frames_plays_its_fallback(self):
        clip = {s["_name"]: s["animationBindings"]["hth"][0] for s in self.sm["states"]}
        self.assertEqual((clip["GH"], clip["A2"], clip["RN"], clip["S3"], clip["KB"]),
                         ("neutral", "attack1", "walk", "attack1", "neutral"))
        self.assertEqual((clip["DT"], clip["DD"]), ("death", "dead"))

    def test_no_transition_blends(self):
        fades = {i["crossfadeSeconds"] for g in self.sm["transitions"] for i in g["settings"]}
        self.assertEqual(fades, {0.0})
        self.assertEqual(len(self.sm["transitions"]), len(self.sm["states"]))

    def test_the_aim_state_comes_only_when_asked(self):
        self.assertNotIn("State_AIM", [s["name"] for s in self.sm["states"]])
        aim = mf.state_machine("x", "data/hd/x", ["neutral", "additive_aim"], {"nu": 1}, aim=True)
        self.assertIn("State_AIM", [s["name"] for s in aim["states"]])

    def test_dependencies_name_every_clip(self):
        self.assertEqual([d["path"] for d in self.sm["dependencies"]["animations"]],
                         [a["filename"] for a in self.sm["animations"]])


class TurningMachine(unittest.TestCase):
    def setUp(self):
        self.clips = [mf.facing_clip(b, k) for b in ("neutral", "walk", "attack1", "death", "dead") for k in range(8)]
        self.sm = mf.state_machine("x_statemachine", "data/hd/x", self.clips, {"nu": 15, "wl": 16, "a1": 15, "dt": 20}, turn=True)
        self.states = {s["_name"]: s for s in self.sm["states"]}

    def test_a_clip_without_a_facing_keeps_its_name(self):
        self.assertEqual((mf.facing_clip("walk", None), mf.facing_clip("walk", 0), mf.facing_clip("walk", 7)),
                         ("walk", "walk_0", "walk_7"))

    def test_every_state_binds_its_eight_facings_in_the_engines_key_order(self):
        self.assertEqual(mf.WEAPON_KEYS, ("hth", "bow", "1hs", "1ht", "stf", "2hs", "2ht", "xbw"))
        for s in self.sm["states"]:
            self.assertEqual(list(s["animationBindings"]), list(mf.WEAPON_KEYS), s["name"])
        self.assertEqual(self.states["WL"]["animationBindings"], {key: ["walk_%d" % k] for k, key in enumerate(mf.WEAPON_KEYS)})

    def test_a_monsters_own_weapon_class_shows_the_first_facing(self):
        self.assertEqual(self.states["NU"]["animationBindings"]["hth"], ["neutral_0"])

    def test_a_mode_without_frames_plays_its_fallback_in_every_facing(self):
        self.assertEqual(self.states["GH"]["animationBindings"]["1ht"], ["neutral_3"])
        self.assertEqual(self.states["RN"]["animationBindings"]["xbw"], ["walk_7"])
        self.assertEqual(self.states["DD"]["animationBindings"]["bow"], ["dead_1"])

    def test_every_bound_clip_exists(self):
        bound = {c for s in self.sm["states"] for clips in s["animationBindings"].values() for c in clips}
        self.assertLessEqual(bound, set(self.clips))
        self.assertEqual([a["name"] for a in self.sm["animations"]], self.clips)

    def test_states_loop_a_counted_number_of_times(self):
        # the engine plays a state again under another key only when its loop count is above 0
        self.assertEqual(self.states["DT"]["loopCount"], 1)
        self.assertTrue(all(s["loopCount"] == mf.LOOPS for n, s in self.states.items() if n != "DT"))
        self.assertGreater(mf.LOOPS, 0)

    def test_a_state_follows_itself_without_a_blend(self):
        pairs = {(g["from"], i["to"]): i["crossfadeSeconds"] for g in self.sm["transitions"] for i in g["settings"]}
        ids = [s["stateId"] for s in self.sm["states"]]
        self.assertEqual(set(pairs), {(a, b) for a in ids for b in ids})
        self.assertEqual(set(pairs.values()), {0.0})
        for g in self.sm["transitions"]:   # the engine searches the pairs in order
            self.assertEqual([i["to"] for i in g["settings"]], sorted(i["to"] for i in g["settings"]))

    def test_without_turn_loops_are_endless(self):
        plain = mf.state_machine("x", "data/hd/x", ["neutral", "death"], {"nu": 1, "dt": 2})
        self.assertEqual({s["_name"]: s["loopCount"] for s in plain["states"]}["NU"], 0)


class Upscale(unittest.TestCase):
    def sprite(self):
        px = np.zeros((12, 10, 4), np.uint8)
        px[3:9, 2:8] = (200, 40, 20, 255)
        return px

    def test_bleed_pushes_the_colour_outward_and_keeps_the_inside(self):
        px = self.sprite()
        rgb = mu.bleed(px, 3)
        self.assertEqual(rgb[5, 5].tolist(), [200, 40, 20])
        self.assertEqual(rgb[2, 1].tolist(), [200, 40, 20])        # one pixel outside, diagonally
        self.assertEqual(rgb[5, 0].tolist(), [200, 40, 20])        # two pixels outside

    def test_alpha_stays_hard_inside_and_outside(self):
        a = mu.alpha_up(self.sprite()[..., 3], 4)
        self.assertEqual(a.shape, (48, 40))
        self.assertEqual(int(a[24, 20]), 255)
        self.assertEqual(int(a[2, 2]), 0)
        self.assertIs(mu.alpha_up(self.sprite()[..., 3], 1).dtype, np.dtype(np.uint8))

    def test_the_edge_of_an_upscaled_frame_has_no_dark_halo(self):
        for method in ("lanczos", "nearest", "dedither+lanczos"):
            big = mu.upscale([self.sprite()], 4, method)[0]
            self.assertEqual(big.shape, (48, 40, 4))
            seen = big[big[..., 3] > 0][:, :3].astype(int)
            self.assertGreater(len(seen), 500)
            self.assertLess(np.abs(seen - (200, 40, 20)).max(), 12, method)   # also the half-covered pixels keep the colour

    def test_scale_one_returns_the_frames(self):
        f = self.sprite()
        self.assertIs(mu.upscale([f], 1, "lanczos")[0], f)

    def test_the_step_is_a_soft_threshold(self):
        x = np.array([0.0, 0.5 - mu.SOFT, 0.5, 0.5 + mu.SOFT, 1.0], np.float32)
        self.assertEqual(mu._step(x).tolist(), [0, 0, 128, 255, 255])

    def test_over_and_trimmed(self):
        px = self.sprite()
        self.assertEqual(mu.over(px, 128)[0, 0].tolist(), [128, 128, 128])
        self.assertEqual(mu.over(px, 128)[5, 5].tolist(), [200, 40, 20])
        self.assertEqual(mu.trimmed(px, 1).shape, (8, 8, 4))

    def test_dedither_keeps_flat_colour_and_edges(self):
        rgb = np.zeros((9, 9, 3), np.uint8)
        rgb[:, :4], rgb[:, 4:] = (20, 20, 20), (220, 220, 220)
        out = mu.dedither(rgb)
        self.assertEqual(out.shape, rgb.shape)
        self.assertLess(int(out[4, 1].max()), 30)
        self.assertGreater(int(out[4, 7].min()), 210)


if __name__ == "__main__":
    unittest.main()
