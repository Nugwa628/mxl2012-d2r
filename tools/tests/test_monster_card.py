"""tools/monster_card.py and tools/monster_sheet.py: the card's geometry, its texture canvas, the unit file and the COF reader
(no game data needed)."""
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401
import monster_card as mc  # noqa: E402
import monster_sheet as ms  # noqa: E402

DONOR = {"dependencies": {"particles": [], "models": [{"path": "data/hd/character/enemy/wakeofdestruction/torso.model"}],
                          "skeletons": [{"path": "s.skeleton"}], "animations": [],
                          "textures": [{"path": "data/hd/character/common/common_ktint.texture"}, {"path": "old_alb.texture"}],
                          "physics": [], "json": [{"path": "sm.json"}, {"path": "data/hd/missiles/flamethrower.json"}],
                          "variantdata": [{"path": "v.json"}], "objecteffects": [], "other": []},
         "type": "UnitDefinition", "name": "infernosentry",
         "entities": [{"type": "Entity", "name": "entity_root", "id": 1, "components": [
             {"type": "UnitRootComponent", "state_machine_filename": "sm.json", "doNotInheritRotation": False,
              "rotationOverride": {"x": 0.0, "y": 0.38, "z": 0.0, "w": 0.92}},
             {"type": "SkeletonDefinitionComponent", "filename": "s.skeleton"},
             {"type": "VariantDefinitionComponent", "filename": "v.json"},
             {"type": "DefinitionPreloadComponent", "missiles": [{"filename": "data/hd/missiles/flamethrower.json"}]},
             {"type": "AimLayersComponent", "aimLayers": []}]},
             {"type": "Entity", "name": "entity_torso", "id": 2, "components": [
                 {"type": "UnitPartComponent", "part": "torso", "variant": "lit"},
                 {"type": "ModelDefinitionComponent", "filename": "data/hd/character/enemy/wakeofdestruction/torso.model",
                  "shadowMask": 3},
                 {"type": "TransformDefinitionComponent", "scale": {"x": 0.8, "y": 0.8, "z": 0.8}}]}]}


class Mesh(unittest.TestCase):
    def test_every_corner_lands_on_its_sprite_pixel(self):
        for w, h, x0, y0 in ((52, 85, -33, -74), (183, 154, -91, -91), (40, 30, -20, -60)):
            verts, tris = mc.card_mesh(w, h, x0, y0, (0.0, 0.0, 1.0, 1.0))
            want = ((x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h))
            for (pos, _n, _t, _uv), (px, py) in zip(verts, want):
                u, v = mc.screen_of(pos)
                self.assertAlmostEqual(u, px, places=4)
                self.assertAlmostEqual(v, py, places=4)
            self.assertEqual(len(tris), 2)

    def test_the_card_stands_on_the_ground_and_is_upright(self):
        verts, _ = mc.card_mesh(52, 85, -33, -74, (0, 0, 1, 1))
        ys = [v[0][1] for v in verts]
        self.assertAlmostEqual(min(ys), 0.0)
        self.assertAlmostEqual(max(ys), 85 / mc.PX_HEIGHT)
        for pos, _n, _t, _uv in verts:       # one vertical plane across the screen's right axis: X + Z is the same everywhere
            self.assertAlmostEqual(pos[0] + pos[2], 2 * 11 / mc.PX_DEPTH)

    def test_a_frame_that_ends_above_the_anchor_floats(self):
        verts, _ = mc.card_mesh(40, 30, -20, -60, (0, 0, 1, 1))
        self.assertAlmostEqual(min(v[0][1] for v in verts), 30 / mc.PX_HEIGHT)
        self.assertAlmostEqual(verts[0][0][0] + verts[0][0][2], 0.0)

    def test_uv_and_winding(self):
        verts, tris = mc.card_mesh(10, 10, -5, -10, (0.25, 0.5, 0.75, 1.0))
        self.assertEqual([v[3] for v in verts], [(0.25, 0.5), (0.75, 0.5), (0.75, 1.0), (0.25, 1.0)])
        for a, b, c in tris:                 # facing the camera (which stands at +X, +Z)
            pa, pb, pc = (np.array(verts[i][0]) for i in (a, b, c))
            n = np.cross(pb - pa, pc - pa)
            self.assertGreater(n[0] + n[2], 0)


class Canvas(unittest.TestCase):
    def test_power_of_two_centred_and_bled(self):
        rgba = np.zeros((85, 52, 4), np.uint8)
        rgba[..., :] = (200, 10, 10, 255)
        px, (x, y) = mc.canvas(rgba)
        self.assertEqual(px.shape, (128, 64, 4))
        self.assertEqual((x, y), (6, 21))
        self.assertTrue((px[y:y + 85, x:x + 52] == rgba).all())
        self.assertEqual(tuple(px[y - 1, x]), (200, 10, 10, 0))      # colour bled, still transparent
        self.assertEqual(tuple(px[0, 0]), (0, 0, 0, 0))

    def test_never_under_the_smallest_texture(self):
        px, _ = mc.canvas(np.full((5, 5, 4), 255, np.uint8))
        self.assertEqual(px.shape[:2], (mc.MIN_SIDE, mc.MIN_SIDE))

    def test_flat_maps(self):
        nrm, orm = mc.flat_maps((512, 256))
        self.assertEqual(nrm.shape, (128, 64, 4))
        self.assertEqual(tuple(nrm[0, 0]), (255, 128, 0, 128))
        self.assertEqual(tuple(orm[0, 0]), (255, 217, 0, 255))


class Unit(unittest.TestCase):
    def test_the_unit_keeps_the_world_axes_and_draws_the_card(self):
        tex = {"alb": "a_alb.texture", "nrm": "a_nrm.texture", "orm": "a_orm.texture"}
        u = mc.unit_json(DONOR, "mxl_card_x", "data/hd/character/enemy/mxl/card/x/torso.model", tex)
        root, torso = u["entities"]
        self.assertEqual([c["type"] for c in root["components"]], list(mc.KEEP))
        self.assertTrue(root["components"][0]["doNotInheritRotation"])
        self.assertEqual(root["components"][0]["rotationOverride"], {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0})
        self.assertEqual(torso["components"][1]["filename"], "data/hd/character/enemy/mxl/card/x/torso.model")
        self.assertEqual(torso["components"][2]["scale"], {"x": 1.0, "y": 1.0, "z": 1.0})
        self.assertEqual(u["dependencies"]["models"], [{"path": "data/hd/character/enemy/mxl/card/x/torso.model"}])
        self.assertEqual([t["path"] for t in u["dependencies"]["textures"]],
                         ["data/hd/character/common/common_ktint.texture", "a_alb.texture", "a_nrm.texture", "a_orm.texture"])
        self.assertEqual(u["dependencies"]["json"], [{"path": "sm.json"}])
        self.assertEqual(DONOR["name"], "infernosentry")             # the donor is not changed
        self.assertFalse(DONOR["entities"][0]["components"][0]["doNotInheritRotation"])

    def test_bare_root(self):
        u = mc.unit_json(DONOR, "x", "m.model", {}, keep=mc.KEEP[:2])
        self.assertEqual([c["type"] for c in u["entities"][0]["components"]], ["UnitRootComponent", "SkeletonDefinitionComponent"])


class Cof(unittest.TestCase):
    def test_header_layers_and_draw_order(self):
        layers, frames, dirs = 2, 3, 2
        head = bytes([layers, frames, dirs, 20]) + b"\0" * 4 + struct.pack("<4i", -10, -20, 30, 40) + struct.pack("<I", 256)
        lay = b"".join(bytes([comp, 1, 1, 0, 0]) + b"hth\0" for comp in (1, 2))      # TR, LG
        keys = bytes(frames)
        order = bytes([1, 2] * frames + [2, 1] * frames)
        cof = ms.parse_cof(head + lay + keys + order)
        self.assertEqual((cof["frames"], cof["dirs"], cof["speed"]), (3, 2, 256))
        self.assertEqual([la["comp"] for la in cof["layers"]], ["tr", "lg"])
        self.assertEqual(cof["order"][0][0], [1, 2])
        self.assertEqual(cof["order"][1][2], [2, 1])

    def test_safe_names(self):
        self.assertEqual(ms.safe("~k"), "7ek")
        self.assertEqual(ms.safe("sk"), "sk")


if __name__ == "__main__":
    unittest.main()
