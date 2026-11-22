"""hdkit.view animation and classic side on synthetic data: Granny curve sampling (exact B-spline against an independent
Cox-de Boor basis), the D4n quaternion decode, the knot scale, local-space blends, the state-machine player, COF reading,
PL2 rows and the game camera constants. No game data and no GPU needed."""
import math
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.view import camera, classic, curves, gr2, player  # noqa: E402


def cox_de_boor(T, j, p, t):
    """Standard B-spline basis N_{j,p}(t) over knot vector T (half-open spans)."""
    if p == 0:
        return 1.0 if T[j] <= t < T[j + 1] else 0.0
    out = 0.0
    if T[j + p] > T[j]:
        out += (t - T[j]) / (T[j + p] - T[j]) * cox_de_boor(T, j, p - 1, t)
    if T[j + p + 1] > T[j + 1]:
        out += (T[j + p + 1] - t) / (T[j + p + 1] - T[j + 1]) * cox_de_boor(T, j + 1, p - 1, t)
    return out


def curve(degree, knots, controls):
    C = np.asarray(controls, float)
    if C.ndim == 1:
        C = C[:, None]
    return curves.Curve("DaK32fC32f", degree, np.asarray(knots, float), C, C.shape[1])


class Sampling(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        self.k = np.cumsum(rng.uniform(0.05, 0.3, 12))
        self.k -= self.k[0]
        self.c = rng.normal(size=(12, 3))

    def test_deboor_equals_basis(self):
        """Granny's window: span [K[i-1], K[i]) blends C[i-p..i]; a standard B-spline with T[j] = K[j-1]."""
        K, C = self.k, self.c
        T = np.concatenate([[K[0] - 1.0], K, [K[-1] + 1.0]])   # T[j] = K[j-1]
        for p in (1, 2, 3):
            for i in range(p, len(K) - p + 1):
                for s in (0.0, 0.3, 0.71):
                    t = K[i - 1] + s * (K[i] - K[i - 1])
                    ref = sum(cox_de_boor(T, j, p, t) * C[j] for j in range(i - p, i + 1))
                    np.testing.assert_allclose(curves.deboor(K, C, p, i, t), ref, atol=1e-12)

    def test_quadratic_closed_form(self):
        """Degree 2 on uniform knots: weights (1-s)^2/2, (1+2s-2s^2)/2, s^2/2."""
        K = np.arange(8.0)
        C = np.arange(8.0)[:, None] ** 2
        i, s = 4, 0.25
        w = np.array([(1 - s) ** 2 / 2, (1 + 2 * s - 2 * s * s) / 2, s * s / 2])
        np.testing.assert_allclose(curves.deboor(K, C, 2, i, K[i - 1] + s), w @ C[i - 2:i + 1], atol=1e-12)

    def test_clamped_ends(self):
        c = curve(2, self.k, self.c)
        np.testing.assert_allclose(curves.sample(c, self.k[0]), self.c[0], atol=1e-12)
        np.testing.assert_allclose(curves.sample(c, self.k[-1]), self.c[-1], atol=1e-12)
        np.testing.assert_allclose(curves.sample(c, self.k[-1] + 5), self.c[-1], atol=1e-12)
        np.testing.assert_allclose(curves.sample(c, -3), self.c[0], atol=1e-12)

    def test_degree2_is_smooth_and_not_interpolating(self):
        c = curve(2, self.k, self.c)
        mid = self.k[5]
        a, b = curves.sample(c, mid - 1e-7), curves.sample(c, mid + 1e-7)
        np.testing.assert_allclose(a, b, atol=1e-5)
        self.assertGreater(np.abs(curves.sample(c, mid) - self.c[5]).max(), 1e-3)

    def test_degree1_lerp_and_degree0_step(self):
        c1 = curve(1, [0, 1, 2], [0, 10, 30])
        self.assertAlmostEqual(float(curves.sample(c1, 1.5)[0]), 20.0)
        c0 = curve(0, [0, 1, 2], [0, 10, 30])
        self.assertAlmostEqual(float(curves.sample(c0, 1.5)[0]), 10.0)
        self.assertAlmostEqual(float(curves.sample(c0, 0.99)[0]), 0.0)

    def test_keys_method_reads_controls_at_knots(self):
        c = curve(2, self.k, self.c)
        np.testing.assert_allclose(curves.sample(c, self.k[4], method="keys"), self.c[4], atol=1e-12)

    def test_loop_wraps_continuously(self):
        C = self.c.copy()
        C[-1] = C[0]                       # first and last key are the same instant of the loop
        c = curve(2, self.k, C)
        D = self.k[-1] - self.k[0]
        end = curves.sample(c, self.k[-1] - 1e-7, loop=True, duration=D)
        start = curves.sample(c, self.k[0], loop=True, duration=D)
        np.testing.assert_allclose(end, start, atol=1e-5)
        np.testing.assert_allclose(curves.sample(c, 0.4 + D, loop=True, duration=D),
                                   curves.sample(c, 0.4, loop=True, duration=D), atol=1e-12)

    def test_quaternions_normalised(self):
        q = np.array([[0, 0, 0, 1], [0, 0.7071, 0, 0.7071], [0, 1, 0, 0]], float)
        c = curves.Curve("D4nK8uC7u", 2, np.array([0.0, 1.0, 2.0]), q, 4)
        self.assertAlmostEqual(float(np.linalg.norm(curves.sample(c, 0.8))), 1.0, places=12)
        self.assertEqual(curves.quat_flips(c), 0)
        c.controls[2] *= -1
        self.assertEqual(curves.quat_flips(c), 1)


class Decode(unittest.TestCase):
    def test_knot_scale_trunc(self):
        self.assertEqual(curves.knot_scale_trunc(0x3F80), 1.0)
        self.assertEqual(curves.knot_scale_trunc(0x4120), 10.0)
        self.assertEqual(curves.knot_scale_trunc(0x41F0), 30.0)

    def test_d4n_swizzle_and_sign(self):
        """Sign bits of the 2nd and 3rd words pick the rebuilt component; the 1st word's top bit negates it."""
        for bits, top in ((8, 0x80), (16, 0x8000)):
            mid = (top - 1) // 2 + 1           # about 0 after scale 0.7071 and offset -0.3536 (table entry 1)
            sel = 0x1111
            for b_sign, c_sign, slot in ((0, 0, 0), (0, 1, 1), (1, 0, 2), (1, 1, 3)):
                for a_neg in (False, True):
                    a = mid | (top if a_neg else 0)
                    kc = np.array([0, a, mid | (top * b_sign), mid | (top * c_sign)], float)
                    q = curves._quat_d4n(kc, 1, sel, bits)[0]
                    self.assertAlmostEqual(float(np.linalg.norm(q)), 1.0, places=5)
                    self.assertEqual(int(np.argmax(np.abs(q))), slot)
                    self.assertEqual(q[slot] < 0, a_neg)


class Blend(unittest.TestCase):
    def test_blend_locals(self):
        e = np.eye(3).ravel()
        qa = np.array([0, 0, 0, 1.0])
        qb = np.array([0, math.sin(0.5), 0, math.cos(0.5)])
        a = [(np.zeros(3), qa, e)]
        b = [(np.ones(3), -qb, 2 * e)]                  # other hemisphere: must still take the short way
        p, q, s = gr2.blend_locals(a, b, 0.5)[0]
        np.testing.assert_allclose(p, 0.5)
        np.testing.assert_allclose(s, 1.5 * e)
        self.assertAlmostEqual(float(np.linalg.norm(q)), 1.0)
        self.assertAlmostEqual(abs(2 * math.atan2(q[1], q[3])), 0.5, places=6)
        np.testing.assert_allclose(gr2.blend_locals(a, b, 0.0)[0][1], qa)


class FakeClip:
    def __init__(self, duration):
        self.duration = duration


SM = {"name": "t", "states": [
    {"name": "idle", "stateId": 1, "modeId": 1, "loopCount": 0, "animationBindings": {"hth": ["idle"]}},
    {"name": "hit", "stateId": 2, "modeId": 4, "loopCount": 1, "animationBindings": {"hth": ["atk", "atk2"]}}],
    "transitions": [{"from": 1, "settings": [{"to": 2, "crossfadeSeconds": 0.2}]}]}


class Player(unittest.TestCase):
    def setUp(self):
        self.sm = player.StateMachine.from_json(SM)
        self.pl = player.Player(self.sm, {"idle": FakeClip(4.0), "atk": FakeClip(0.8)},
                                classic={"a1": {"frames": 15, "speed": 200}})

    def test_states(self):
        self.assertTrue(self.sm.state("nu").loop)
        self.assertFalse(self.sm.state(4).loop)
        self.assertEqual(self.sm.clip_name("a1", variant=1), "atk2")
        self.assertEqual(self.sm.crossfade[(1, 2)], 0.2)

    def test_timing(self):
        self.assertAlmostEqual(self.pl.length("a1"), 0.8)
        self.pl.timing = "classic"
        self.assertAlmostEqual(self.pl.length("a1"), 15 / (25 * 200 / 256))
        self.assertAlmostEqual(self.pl.clip_time("a1", self.pl.length("a1")), 0.8)

    def test_timeline_crossfade(self):
        fr = self.pl.timeline([("nu", 0.4), ("a1", 0.4)], fps=25)
        self.assertEqual(len(fr), 20)
        self.assertEqual(fr[9].clip, "idle")
        self.assertEqual(fr[10].prev_clip, "idle")
        self.assertAlmostEqual(fr[10].weight, 0.0)
        self.assertAlmostEqual(fr[12].weight, 0.4)
        self.assertAlmostEqual(fr[10].prev_t, 0.4)          # idle frozen where it was left
        self.assertEqual(fr[15].prev_clip, "")
        self.assertEqual(fr[0].prev_clip, "")


class Classic(unittest.TestCase):
    def test_read_cof(self):
        n, frames, dirs = 2, 3, 2
        head = bytes([n, frames, dirs]) + bytes(21) + struct.pack("<I", 200)
        lay = bytes([0, 1, 0, 0, 5]) + b"hth\0" + bytes([1, 0, 0, 1, 2]) + b"hth\0"
        events = bytes([0, 1, 0])
        order = bytes([0, 1] * (frames * dirs))
        order = order[:-2] + bytes([1, 0])                  # last frame of the last direction: torso first
        cof = classic.read_cof(head + lay + events + order)
        self.assertEqual([l.comp for l in cof.layers], ["hd", "tr"])
        self.assertTrue(cof.layers[0].shadow)
        self.assertTrue(cof.layers[1].transparent)
        self.assertEqual(cof.layers[1].effect, 2)
        self.assertEqual(cof.layers[0].wclass, "hth")
        self.assertAlmostEqual(cof.fps, 25 * 200 / 256)
        self.assertEqual(cof.order[0][0], ["hd", "tr"])
        self.assertEqual(cof.order[1][2], ["tr", "hd"])
        self.assertEqual(cof.events, events)

    def test_pl2_rows(self):
        pal = np.zeros((256, 4), np.uint8)
        pal[:, 0] = np.arange(256)
        rows = np.zeros((32, 256), np.uint8)
        rows[31] = np.arange(256)
        rows[0] = 0
        pl2 = classic.Pl2(pal.tobytes() + rows.tobytes())
        idx = np.array([[5, 200]], np.uint8)
        self.assertEqual(pl2.rgb(idx)[0, 1, 0], 200)
        self.assertEqual(pl2.rgb(idx, light=0)[0, 1, 0], 0)


class GameCamera(unittest.TestCase):
    def test_re_camera(self):
        self.assertEqual(camera.GAME_EL, 30.0)
        self.assertEqual(camera.OrthoCamera().el, 30.0)
        self.assertAlmostEqual(camera.k_for_height(900), camera.K_1600x900, delta=0.01)
        self.assertAlmostEqual(camera.k_for_height(1080), 20.37, delta=0.01)
        r, u, w = camera.basis(camera.GAME_AZ, camera.GAME_EL)
        np.testing.assert_allclose(-np.asarray(w) / np.linalg.norm(w),
                                   np.array([-1, -math.tan(math.radians(30)) * math.sqrt(2), -1])
                                   / np.linalg.norm([-1, -math.tan(math.radians(30)) * math.sqrt(2), -1]), atol=1e-9)


if __name__ == "__main__":
    unittest.main()
