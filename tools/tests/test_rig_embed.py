"""Lane rigaudit: rig_fit's carry and its inverse, and rig_embed's embedding, weights and leg IK, on synthetic data (no game
files). Run: python -I -m unittest discover -s tools/tests -p "test_rig_embed.py"
The embedding and IK tests need the monster3d venv (scikit-image for marching cubes, numba for the stage modules); they
are skipped without it."""
import importlib
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SP = ROOT / "tools" / "sprite3d"
M3D = SP / "monster3d"
for p in (ROOT / "tools", SP, M3D):
    sys.path.insert(0, str(p))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import rig_fit  # noqa: E402

PROFILE = rig_fit.PROFILES["mummy1"]
# a mummy1-like T-pose skeleton (bind units): the bones the profile names, with the end bones rig_embed reads
JOINTS = {
    "pelvis": (0, 4.2, 0), "spine_01": (0, 4.6, 0), "spine_02": (0, 5.1, 0), "chest": (0, 5.6, 0), "neck": (0, 6.4, 0),
    "head": (0, 6.8, 0), "jaw": (0, 6.7, 0.2),
    "L_Clavicle": (0.2, 6.2, 0), "L_UpperArm": (0.95, 6.2, 0), "L_ForeArm": (1.9, 6.2, 0), "L_Wrist": (3.0, 6.2, 0),
    "L_Wrist_END": (3.6, 6.2, 0),
    "L_Thigh": (0.45, 4.2, 0), "L_Calf": (0.45, 2.2, 0), "L_Foot": (0.45, 0.5, 0), "L_Ball": (0.45, 0.1, 0.5),
    "L_Toe_END": (0.45, 0.05, 0.9),
}
PARENT = {"pelvis": None, "spine_01": "pelvis", "spine_02": "spine_01", "chest": "spine_02", "neck": "chest", "head": "neck",
          "jaw": "head", "L_Clavicle": "chest", "L_UpperArm": "L_Clavicle", "L_ForeArm": "L_UpperArm", "L_Wrist": "L_ForeArm",
          "L_Wrist_END": "L_Wrist", "L_Thigh": "pelvis", "L_Calf": "L_Thigh", "L_Foot": "L_Calf", "L_Ball": "L_Foot",
          "L_Toe_END": "L_Ball"}


def skeleton():
    names = list(JOINTS)
    for n in list(names):
        if n.startswith("L_"):
            names.append("R_" + n[2:])
    out = []
    for i, n in enumerate(names):
        src = "L_" + n[2:] if n.startswith("R_") else n
        p = np.array(JOINTS[src], float)
        if n.startswith("R_"):
            p[0] = -p[0]
        par = PARENT[src]
        if par is not None and n.startswith("R_") and par.startswith("L_"):
            par = "R_" + par[2:]
        out.append({"i": i, "name": n, "parent": names.index(par) if par else -1, "pos": [float(x) for x in p]})
    return out


class Carry(unittest.TestCase):
    def test_uncarry_inverts_fit(self):
        bones = skeleton()
        rng = np.random.default_rng(1)
        # points around the profile's posed joints (the Fungus table), so every joint gets weight
        inst = rig_fit.instances(PROFILE, bones)
        centres = np.array([v[0] for v in inst.values()])
        pos = centres[rng.integers(0, len(centres), 3000)] + rng.normal(0, 0.25, (3000, 3))
        nrm = rng.normal(0, 1, (3000, 3))
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        tris = np.arange(2997).reshape(-1, 3)
        out, _on, bidx, wts, names, _inst, _cols = rig_fit.fit(PROFILE, bones, pos, nrm, tris)
        back = rig_fit.uncarry(PROFILE, bones, out, bidx, wts, names)
        self.assertLess(np.abs(back - pos).max(), 1e-8)

    def test_carry_maps_stretch_is_clipped(self):
        maps = rig_fit.carry_maps(PROFILE, skeleton())
        for key, (_b, M, _c, name) in maps.items():
            s = np.linalg.svd(M, compute_uv=False)
            self.assertTrue(np.all(s >= PROFILE["smin"] ** max(PROFILE["girth"], 1) - 1e-9), key)
            self.assertTrue(np.all(s <= PROFILE["smax"] + 1e-9), key)


def capsule_field(P, segs):
    d = np.full(len(P), np.inf)
    for a, b, r in segs:
        a, b = np.array(a, float), np.array(b, float)
        ab = b - a
        t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
        d = np.minimum(d, np.linalg.norm(P - (a + t[:, None] * ab), axis=1) - r)
    return d


def stick_figure():
    """A crouching biped of capsules (game units, height about 8): arms hanging close beside the thighs, legs apart."""
    segs = [((0, 3.6, 0), (0, 5.8, 0), 0.75), ((0, 5.8, 0), (0, 7.3, 0.2), 0.45)]
    for s in (1, -1):
        segs += [((s * 0.5, 5.9, 0), (s * 1.25, 5.8, 0), 0.32), ((s * 1.25, 5.8, 0), (s * 1.45, 4.2, -0.3), 0.27),
                 ((s * 1.45, 4.2, -0.3), (s * 1.45, 2.4, 0.2), 0.24),
                 ((s * 0.45, 3.6, 0), (s * 0.75, 2.2, 0.6), 0.36), ((s * 0.75, 2.2, 0.6), (s * 0.75, 0.45, 0), 0.3),
                 ((s * 0.75, 0.45, 0), (s * 0.75, 0.25, 0.9), 0.22)]
    return segs


class Embed(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from skimage.measure import marching_cubes
        except ImportError:
            raise unittest.SkipTest("scikit-image not installed")
        cls.re = importlib.import_module("rig_embed")
        h = 0.06
        g = np.mgrid[-2.4:2.4:h, -0.2:8.2:h, -1.6:1.8:h]
        P = g.reshape(3, -1).T
        segs = stick_figure()
        f = capsule_field(P, segs).reshape(g.shape[1:])
        v, t, _n, _ = marching_cubes(f, 0.0, spacing=(h, h, h))
        cls.P = v + np.array([-2.4, -0.2, -1.6])
        cls.T = t[:, ::-1].copy()
        cls.segs = segs
        cls.res, cls.vol = cls.re.embed(cls.P, cls.T, {}, PROFILE, skeleton(), None, K=8.0)

    def test_tips_are_named(self):
        tips = {k: np.array(v) for k, v in self.res["info"]["tips"].items()}
        self.assertLess(tips["L_hand_end"][1], 3.0)
        self.assertGreater(tips["L_hand_end"][0], 1.0)
        self.assertLess(tips["R_hand_end"][0], -1.0)
        self.assertLess(tips["L_toe_end"][1], 0.6)
        self.assertGreater(tips["L_toe_end"][2], 0.6)      # the toe, not the heel
        self.assertGreater(tips["head_end"][1], 7.0)

    def test_elbows_and_knees_at_the_bends(self):
        J = {k: np.array(v) for k, v in self.res["posed"].items()}
        for s in (1, -1):
            side = "L" if s > 0 else "R"
            self.assertLess(np.linalg.norm(J[side + "_forearm"] - (s * 1.45, 4.2, -0.3)), 0.45)
            self.assertLess(np.linalg.norm(J[side + "_calf"] - (s * 0.75, 2.2, 0.6)), 0.45)
            self.assertLess(np.linalg.norm(J[side + "_upperarm"] - (s * 1.25, 5.8, 0)), 0.5)

    def test_hand_next_to_thigh_stays_on_the_arm(self):
        re = self.re
        J = {k: np.array(v) for k, v in self.res["posed"].items()}
        curves = re.bone_curves(J, self.res, self.vol, PROFILE)
        names, Dist = re.voxel_distances(self.vol, curves, limit=6.0)
        nrm = np.zeros_like(self.P)           # no inward offset: the nearest voxel of the vertex itself
        bidx, wts, wn = re.vertex_weights(self.P, nrm, self.T, self.vol, names, Dist, 4.0, 2)
        # vertices of the lower forearm (y 2.5 .. 3.2, outer side) and of the thigh/calf next to them
        arm = (np.abs(self.P[:, 0]) > 1.45) & (self.P[:, 1] > 2.5) & (self.P[:, 1] < 3.2)
        leg = (np.abs(self.P[:, 0]) < 0.9) & (np.abs(self.P[:, 0]) > 0.4) & (self.P[:, 1] > 1.0) & (self.P[:, 1] < 2.0)
        legbones = {n for n in wn if "Thigh" in n or "Calf" in n or "Foot" in n or "Ball" in n}
        armbones = {n for n in wn if "Arm" in n or "Wrist" in n or "Clavicle" in n}

        def share(sel, group):
            idx = [wn.index(n) for n in group]
            return float((wts[sel] * np.isin(bidx[sel], idx)).sum(1).mean())
        self.assertGreater(share(arm, armbones), 0.97)
        self.assertGreater(share(leg, legbones), 0.97)


class TwoBone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            importlib.import_module("rig_embed")
        except ImportError as e:          # the stage modules need the monster3d venv (numba)
            raise unittest.SkipTest(str(e))
    def test_reaches_and_keeps_lengths(self):
        re = importlib.import_module("rig_embed")
        H = np.array([0.3, 4.0, 0.0])
        tgt = np.array([0.4, 1.0, 0.5])
        K, A = re.two_bone(H, tgt, 2.2, 1.9, np.array([0, 0, 1.0]))
        self.assertAlmostEqual(np.linalg.norm(K - H), 2.2, 6)
        self.assertAlmostEqual(np.linalg.norm(A - K), 1.9, 6)
        self.assertLess(np.linalg.norm(A - tgt), 1e-3)
        self.assertGreater((K - H)[2], 0.3)                  # bent toward the pole

    def test_out_of_reach_straightens(self):
        re = importlib.import_module("rig_embed")
        H = np.zeros(3)
        K, A = re.two_bone(H, np.array([0, -10.0, 0]), 2.0, 1.5, np.array([0, 0, 1.0]))
        self.assertAlmostEqual(np.linalg.norm(A - H), 3.5, 3)


if __name__ == "__main__":
    unittest.main()
