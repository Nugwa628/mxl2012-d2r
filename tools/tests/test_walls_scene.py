"""Tests of tools/walls_scene.py: the classic structure finder, the kit learnt from a D2R-like scene, and the placement."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

import walls_scene as ws  # noqa: E402

F = "act1/monastry"
WALL = "data/hd/env/model/act1/monastry/wall01.model"
GATE = "data/hd/env/model/act1/monastry/gateway01.model"
JUNCTION = "data/hd/env/model/act1/monastry/wall_junction01.model"
SPIKES = "data/hd/env/model/act1/monastry/wall_spikes.model"
BOXES = {WALL: ((-41.5, 0.0, -13.7), (0.9, 35.6, 0.2)), GATE: ((-71.1, -0.5, -7.2), (5.8, 28.1, 4.6)),
         JUNCTION: ((-6.4, 0.0, -10.5), (4.5, 36.6, 0.0)), SPIKES: ((-34.8, 27.4, -3.2), (0.0, 39.4, 0.0))}


def entity(model, x, z, yaw=0.0, sx=1.0, y=0.0):
    return {"name": "e", "components": [
        {"type": "TransformDefinitionComponent", "name": "e_t", "position": {"x": x, "y": y, "z": z},
         "orientation": ws.quat(yaw), "scale": {"x": sx, "y": 1.0, "z": 1.0}},
        {"type": "ModelDefinitionComponent", "name": "e_m", "filename": model}]}


def model_of(e):
    return next(c["filename"] for c in e["components"] if c["type"] == "ModelDefinitionComponent")


def row(y, x0, seqs, o=2, style=6):
    return {(x0 + i, y): ((F, o, style, q),) for i, q in enumerate(seqs)}


def kit_from(cells, ents):
    kit = ws.Kit(BOXES.get, model_of)
    kit.add("d2r", cells, [(e, ws._transform(e)["position"]["x"], ws._transform(e)["position"]["z"]) for e in ents])
    kit.finish()
    return kit


class StructureTest(unittest.TestCase):
    def test_runs_follow_edges_and_break_on_gaps_and_folders(self):
        cells = row(34, 55, [8, 9, 10, 11, 12])
        cells.update(row(34, 61, [19, 20]))                          # x 60 empty: a new run
        cells[(55, 34)] = ((F, 1, 6, 1), (F, 2, 6, 8))               # the corner cell also starts a left wall
        cells.update({(55, 35 + i): ((F, 1, 6, 2),) for i in range(3)})
        cells[(63, 34)] = (("act1/caves", 2, 1, 0),)                 # another tile set ends the run
        runs = ws.find_runs(cells)
        xs = [(r.line, r.start, len(r.tiles)) for r in runs if r.axis == "x"]
        self.assertEqual(xs, [(34, 55, 5), (34, 61, 2), (34, 63, 1)])
        zs = [(r.line, r.start, len(r.tiles)) for r in runs if r.axis == "z"]
        self.assertEqual(zs, [(55, 34, 4)])
        self.assertEqual(ws.run_cells(runs[-1])[:2], [(55, 34), (55, 35)])

    def test_posts(self):
        cells = {(60, 34): ((F, 2, 6, 8), (F, 7, 2, 0)), (61, 34): ((None, 7, 2, 0),)}
        self.assertEqual(ws.find_posts(cells), [((60, 34), (F, 7, 2, 0))])

    def test_swap_is_its_own_inverse_and_mirrors_the_box(self):
        m = {"du": 3.0, "dv": -2.0, "yaw": 30.0, "scale": (1.0, 1.0, 1.0)}
        self.assertEqual(ws.swap_member(ws.swap_member(m))["yaw"], 30.0)
        # a wall along x (yaw 0) becomes one along z
        b = ws.world_box(BOXES[WALL], 0, 0, 0.0, (1, 1, 1))
        s = ws.swap_member({"du": 0, "dv": 0, "yaw": 0.0, "scale": (1.0, 1.0, 1.0)})
        b2 = ws.world_box(BOXES[WALL], 0, 0, s["yaw"], s["scale"])
        self.assertAlmostEqual(b2[1], b[0], 3)   # z range of the swapped = x range of the original
        self.assertAlmostEqual(b2[3], b[2], 3)
        self.assertAlmostEqual(b2[0], b[1], 3)

    def test_fit(self):
        self.assertEqual(ws.fit(4, 4), (1, 1.0))
        self.assertEqual(ws.fit(8, 4), (2, 1.0))
        k, s = ws.fit(5, 4)
        self.assertEqual((k, s), (1, 1.25))
        k, s = ws.fit(2, 4)
        self.assertEqual((k, s), (1, ws.STRETCH[0]))     # one piece at its minimum, centred
        k, s = ws.fit(14, 4)
        self.assertEqual(k, 4)
        self.assertAlmostEqual(s, 14 / 16)


class KitTest(unittest.TestCase):
    def d2r(self):
        """facade1-like: a gate of 6 tiles (seq 7-12) at x 51-56 and plain wall seq 16/27/28/21 x 60-67, junctions."""
        cells = row(10, 51, [7, 8, 9, 10, 11, 12])
        cells.update(row(10, 60, [16, 27, 28, 21, 16, 27, 28, 21]))
        cells[(57, 10)] = ((F, 7, 6, 0),)
        ents = [entity(GATE, 575.0, 104.0), entity(WALL, 640.0, 104.0), entity(SPIKES, 640.0, 104.0, y=0.0),
                entity(WALL, 680.0, 104.0), entity(JUNCTION, 640.5, 109.0), entity(JUNCTION, 575.5, 109.0)]
        return cells, ents

    def test_learns_pieces_slots_and_joints(self):
        kit = kit_from(*self.d2r())
        gate = kit.slot((F, 2, 6, 8))
        self.assertIsNotNone(gate)
        pid, slot = gate
        self.assertEqual(kit.pieces[pid]["members"][0]["model"], GATE)
        self.assertEqual(slot, 1)                                  # seq 7 is slot 0 (x 51)
        wall = kit.slot((F, 2, 6, 27))
        self.assertEqual(sorted(m["model"] for m in kit.pieces[wall[0]]["members"]), [WALL, SPIKES])   # spikes ride along
        self.assertEqual(kit.pieces[wall[0]]["cells"], 4)
        self.assertIsNotNone(kit.joint(F))
        self.assertEqual(kit.family_piece((F, 2, 6, 99)), wall[0])   # the tile set's most used piece

    def test_compose_rebuilds_the_classic_layout(self):
        kit = kit_from(*self.d2r())
        # Duncraig-like: two 5-tile gates (seq 8-12) and an 8-tile wall of sequences D2R never draws
        cells = row(34, 55, [8, 9, 10, 11, 12, 8, 9, 10, 11, 12])
        cells.update(row(34, 65, [40, 41, 42, 43, 40, 41, 42, 43]))
        cells[(60, 34)] = cells[(60, 34)] + ((F, 7, 6, 0),)
        placed, done, st = ws.compose(cells, kit)
        gates = sorted(x for e, x, y, z, yaw, sc in placed if model_of(e) == GATE)
        self.assertEqual(len(gates), 2)                           # one gate per classic gateway, in the same place
        self.assertLess(abs((gates[1] - gates[0]) - 50.0), 0.01)
        walls = [(x, z, sc) for e, x, y, z, yaw, sc in placed if model_of(e) == WALL]
        self.assertEqual(len(walls), 2)                           # 8 family cells: two 4-tile walls
        for x, z, sc in walls:
            self.assertTrue(650 <= x <= 730)
            self.assertAlmostEqual(z, 344.0, 3)                   # same distance from the run line as in D2R (104 - 100)
        self.assertEqual(st["cells_opening"], 10)
        self.assertEqual(st["cells_plain"], 8)
        self.assertTrue(st["joints"] >= 3)
        self.assertEqual(len(done), 18)
        # no gap: the wall pieces cover the classic run end to end
        spans = sorted(ws.world_box(BOXES[WALL], x, z, 0.0, sc)[0:3:2] for x, z, sc in walls)
        self.assertLessEqual(spans[0][0], 650.0 + 1.0)
        self.assertGreaterEqual(spans[-1][1], 730.0 - 1.0)
        self.assertLessEqual(spans[1][0], spans[0][1] + 0.5)

    def test_left_walls_get_the_mirrored_piece(self):
        kit = kit_from(*self.d2r())
        cells = {(20, 10 + i): ((F, 1, 6, 27),) for i in range(4)}
        placed, _done, _st = ws.compose(cells, kit)
        wall = [p for p in placed if model_of(p[0]) == WALL]
        self.assertEqual(len(wall), 1)
        _e, x, _y, z, yaw, sc = wall[0]
        b = ws.world_box(BOXES[WALL], x, z, yaw, sc)
        self.assertGreater(b[3] - b[1], 35)                       # long along z
        self.assertLess(b[2] - b[0], 15)
        self.assertTrue(195 <= b[0] <= 205 or 195 <= b[2] <= 205)  # on the x = 200 edge
        self.assertTrue(98 <= b[1] <= 102 and 138 <= b[3] <= 142)

    def test_pieces_lower_than_the_classic_wall_are_not_used(self):
        kit = kit_from(*self.d2r())
        cells = row(34, 65, [16, 27, 28, 21])
        kit.heights = {t: 500 for k in cells.values() for t in k}          # 500 px classic tiles need 14 units, wall01 has 35.6
        self.assertEqual(ws.compose(cells, kit)[2]["cells_plain"], 4)
        kit.heights = {t: 2000 for k in cells.values() for t in k}         # 2000 px need 56: the per-tile walls stay
        placed, done, st = ws.compose(cells, kit)
        self.assertEqual((placed, len(done), st["cells_too_low"]), ([], 0, 4))
        gaps = set()
        ws.compose(cells, kit, gaps=gaps)
        self.assertEqual(gaps, set(cells))                                  # too low: sprite walls may fill them

    def test_gaps_are_the_cells_compose_leaves_to_the_per_tile_pick(self):
        kit = kit_from(*self.d2r())
        cells = row(34, 65, [16, 27, 28, 21])
        cells[(5, 5)] = ((F, 7, 9, 0),)                                     # a post with no learnt post
        cells[(80, 80)] = (("other/folder", 2, 1, 1),)                       # a tile set the kit has no piece for
        gaps = set()
        _placed, done, _st = ws.compose(cells, kit, gaps=gaps)
        self.assertEqual(gaps, {(5, 5), (80, 80)})
        self.assertTrue(set(row(34, 65, [16, 27, 28, 21])) <= set(done))

    def test_posts_without_a_learnt_post_stay_with_the_per_tile_walls(self):
        kit = kit_from(*self.d2r())
        _placed, done, _st = ws.compose({(5, 5): ((F, 7, 9, 0),)}, kit)
        self.assertEqual(len(done), 0)

    def test_entities_have_fresh_names_and_transforms(self):
        kit = kit_from(*self.d2r())
        placed, _done, _st = ws.compose(row(34, 55, [8, 9, 10, 11, 12, 13]), kit)
        ents = ws.entities(placed)
        self.assertEqual(len({e["name"] for e in ents}), len(ents))
        self.assertEqual(len({e["id"] for e in ents}), len(ents))
        t = ws._transform(ents[0])
        self.assertAlmostEqual(ws.yaw_of(t) % 360, placed[0][4] % 360, 3)
        self.assertTrue(all(0x6D700000 <= e["id"] < 0x6D780000 for e in ents))
        self.assertEqual(math.floor(t["position"]["x"] / 10), math.floor(placed[0][1] / 10))

    def test_entities_keep_a_few_model_variations(self):
        e = entity(WALL, 0.0, 0.0)
        e["components"].append({"type": "ModelVariationDefinitionComponent", "name": "v", "variations": list(range(20))})
        out = ws.entities([(e, 5.0, 0.0, 5.0, 0.0, (1.0, 1.0, 1.0))])
        var = [c for c in out[0]["components"] if c["type"] == "ModelVariationDefinitionComponent"][0]
        self.assertEqual(var["variations"], [0, 1, 2][:ws.VARIATIONS_KEEP])
        self.assertEqual(len(e["components"][-1]["variations"]), 20)         # the kit's own entity is untouched


class FloorTest(unittest.TestCase):
    def test_overrides_only_where_the_tile_set_has_another_biome(self):
        folders = {(0, 0): "act1/caves", (1, 0): "act1/cathedrl", (2, 0): "act1/river", (0, 1): "act1/cathedrl"}
        biome_of = {"act1/caves": "act1_caves", "act1/cathedrl": "act1_cathedral"}.get
        ov = ws.biome_overrides(folders, "act1_caves", biome_of)
        self.assertEqual([(o["tileX"], o["tileY"]) for o in ov], [(1, 0), (0, 1)])
        self.assertEqual(ov[0]["biomeFilename"], "data/hd/env/biome/act1_cathedral.json")

    def test_overrides_keep_the_two_biomes_with_most_cells(self):
        # Fauztinville asserted (too many biomes in view) with its scene biome plus 3 or 4 override biomes
        folders = {(x, y): "s%d" % y for y in range(4) for x in range(y + 1)}       # set s0: 1 cell ... s3: 4 cells
        ov = ws.biome_overrides(folders, "own", lambda f: "b" + f[1:])
        self.assertEqual(ws.OVERRIDE_BIOMES, 2)
        self.assertEqual(sorted({o["biomeFilename"] for o in ov}), ["data/hd/env/biome/b%d.json" % i for i in (2, 3)])
        self.assertEqual(len(ov), 3 + 4)

    def test_add_overrides_stays_within_the_byte_budget(self):
        import json
        text = json.dumps({"dependencies": {"json": [{"path": "data/hd/env/biome/act1_caves.json"}]}, "entities": [],
                           "biomeFilename": "data/hd/env/biome/act1_caves.json", "perTileBiomeOverrides": []})
        ov = ws.biome_overrides({(x, 0): "b" for x in range(100)}, "a", lambda f: "act1_cathedral")
        out, n = ws.add_overrides(text, ov, 4000)
        self.assertLessEqual(len(out.encode("utf-8")), 4000)
        self.assertTrue(0 < n < 100)
        scene = json.loads(out)
        self.assertEqual(len(scene["perTileBiomeOverrides"]), n)
        self.assertIn({"path": "data/hd/env/biome/act1_cathedral.json"}, scene["dependencies"]["json"])


if __name__ == "__main__":
    unittest.main()
