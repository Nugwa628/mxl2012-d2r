"""Unit tests of tools/walls_hd.py (HD wall scenes from D2R's own wall entities) on synthetic .ds1 / .dt1 / scene data.

  py -3 -I -m unittest discover -s tools/tests -p "test_walls_hd.py" -v
"""
import collections
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import ds1_remap  # noqa: E402
import dt1  # noqa: E402
import maps_hd  # noqa: E402
import walls_hd  # noqa: E402
from tests.test_maps import cell, make_dt1  # noqa: E402


def make_ds1(w, h, walls, files=(), version=18):
    """walls: [(cells, orientations)] per wall layer (w*h dwords each); one empty floor layer; header lists `files`."""
    n = w * h
    out = struct.pack("<iiii", version, w - 1, h - 1, 0) + struct.pack("<i", 0)
    out += struct.pack("<i", len(files)) + b"".join(f.encode() + b"\0" for f in files)
    out += struct.pack("<ii", len(walls), 1)
    for wc, oc in walls:
        out += struct.pack("<%dI" % n, *wc) + struct.pack("<%dI" % n, *oc)
    out += struct.pack("<%dI" % n, *([0] * n)) * 2          # floor, shadow
    out += struct.pack("<i", 0)
    return out


def layer(w, h, put):
    """put: {(x, y): (cell dword, orientation)} -> (cells, orientations) of one wall layer."""
    c, o = [0] * (w * h), [0] * (w * h)
    for (x, y), (v, ori) in put.items():
        c[y * w + x], o[y * w + x] = v, ori
    return c, o


def entity(model, x, z, wall=False, physics=True, name="e"):
    comps = [{"type": "TransformDefinitionComponent", "name": name + "_t", "position": {"x": x, "y": 0.0, "z": z},
              "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": 1.0, "y": 1.0, "z": 1.0}},
             {"type": "ModelDefinitionComponent", "name": name + "_m", "filename": model}]
    if physics:
        comps.append({"type": "PhysicsBodyDefinitionComponent", "name": name + "_p"})
    if wall:
        comps.append({"type": "WallTransparencyComponent", "name": name + "_w"})
    return {"type": "Entity", "name": name, "id": 1, "components": comps}


WALL = "data/hd/env/model/act3/kurast/act3_kurast_walls/wall01.model"
PILLAR = "data/hd/env/model/act3/kurast/act3_kurast_architecture/pillar01.model"
IVY = "data/hd/env/model/global/prop/act3/act3_ivy/act3_ivy_hanging01.model"


class TilesTest(unittest.TestCase):
    def test_header_dt1_normalises_paths(self):
        ds = ds1_remap.Ds1(make_ds1(1, 1, [layer(1, 1, {})], files=[
            "/d2/data/global/tiles/Act3/Kurast/Walls.tg1", "C:\\x\\data\\global\\tiles\\act3\\kurast\\floors.dt1", "nonsense.txt",
            "/d2/data/global/tiles/Act3/Kurast/Walls.tg1"]))
        self.assertEqual(walls_hd.header_dt1(ds), ["act3/kurast/walls.dt1", "act3/kurast/floors.dt1"])

    def test_wall_index_first_file_wins_and_skips_floors(self):
        tiles = {"a/x.dt1": dt1.parse(make_dt1([(0, 1, 1, 8, 8, b"f"), (1, 2, 0, 8, 8, b"w")])),
                 "a/y.dt1": dt1.parse(make_dt1([(1, 2, 0, 8, 8, b"v"), (3, 2, 0, 8, 8, b"u")]))}
        idx = walls_hd.wall_index(["a/x.dt1", "a/y.dt1"], tiles.get)
        self.assertEqual(idx, {(1, 2, 0): "a/x.dt1", (3, 2, 0): "a/y.dt1"})

    def test_wall_cells_layers_donor_folder_and_unresolved(self):
        w = 3
        ds = ds1_remap.Ds1(make_ds1(w, 2, [layer(w, 2, {(0, 0): (cell(2, 0), 1), (2, 1): (cell(9, 9), 1)}),
                                            layer(w, 2, {(0, 0): (cell(2, 0), 3)})]))
        idx = {(1, 2, 0): "mod/new/walls.dt1", (3, 2, 0): "act3/kurast/walls.dt1"}
        cells = walls_hd.wall_cells(ds, idx, lambda p: "act3/kurast/walls.dt1" if p.startswith("mod/") else p)
        self.assertEqual(cells[(0, 0)], (("act3/kurast", 1, 2, 0), ("act3/kurast", 3, 2, 0)))
        self.assertEqual(cells[(2, 1)], ((None, 1, 9, 9),))
        self.assertEqual(len(cells), 2)

    def test_orientation_uses_low_byte(self):
        ds = ds1_remap.Ds1(make_ds1(1, 1, [layer(1, 1, {(0, 0): (cell(2, 0), 0x0501)})]))
        self.assertEqual(walls_hd.wall_cells(ds, {(1, 2, 0): "a/b.dt1"})[(0, 0)], (("a", 1, 2, 0),))


class SceneTest(unittest.TestCase):
    def test_decor_dropped_unless_it_fades_with_the_wall(self):
        scene = {"entities": [entity(WALL, 5, 5), entity(IVY, 6, 6), entity(IVY, 7, 7, wall=True),
                              {"type": "Entity", "name": "terrain", "components": [
                                  {"type": "TransformDefinitionComponent", "position": {"x": 0, "y": 0, "z": 0}},
                                  {"type": "ModelDefinitionComponent", "filename": "t.model"}]}]}
        got = [(walls_hd.model_of(e), x) for e, x, _z in walls_hd.wall_entities(scene)]
        self.assertEqual(got, [(WALL, 5.0), (IVY, 7.0)])

    def test_strip_keeps_drawing_components_only(self):
        e = walls_hd.strip_entity(entity(WALL, 1, 1, wall=True))
        self.assertEqual([c["type"] for c in e["components"]],
                         ["TransformDefinitionComponent", "ModelDefinitionComponent", "WallTransparencyComponent"])
        self.assertEqual(e["components"][2]["name"], "e_w")      # D2R's own is kept

    def test_strip_adds_wall_transparency(self):
        e = walls_hd.strip_entity(entity(WALL, 1, 1))
        wt = [c for c in e["components"] if c["type"] == "WallTransparencyComponent"]
        self.assertEqual(len(wt), 1)
        self.assertEqual((wt[0]["drawOrder"], wt[0]["wallTileLocalCoord"]), (0, {"x": -1, "y": -1}))

    def test_learn_assigns_entities_to_their_tile_with_offsets(self):
        lib = walls_hd.Library()
        key = (("act3/kurast", 1, 2, 0),)
        lib.learn("m", {(1, 2): key, (0, 0): ((None, 1, 9, 9),)}, {"entities": [entity(WALL, 13.5, 21.25), entity(PILLAR, 55, 55)]})
        sig, how = lib.pick(key)
        self.assertEqual(how, "exact")
        self.assertEqual(sig, ((WALL, 3.5, 1.25),))
        self.assertEqual(lib.sources["m"], 1)          # the unresolved cell is not learnt
        self.assertEqual(lib.pick(((None, 1, 9, 9),)), (None, None))

    def test_choose_prefers_models_from_a_third_of_the_cells(self):
        a, b = ((WALL, 1.0, 1.0),), ((WALL, 2.0, 1.0),)
        self.assertEqual(walls_hd.choose(collections.Counter({(): 4, a: 2, b: 1})), a)    # 3 of 7 have models
        self.assertEqual(walls_hd.choose(collections.Counter({(): 5, a: 1, b: 1})), ())   # 2 of 7
        self.assertEqual(walls_hd.choose(collections.Counter({(): 1})), ())

    def test_partial_match_through_a_single_tile(self):
        lib = walls_hd.Library()
        t1, t2 = ("d", 1, 2, 0), ("d", 3, 2, 0)
        lib.learn("m", {(0, 0): (t1,)}, {"entities": [entity(WALL, 2, 2)]})
        sig, how = lib.pick((t1, t2))
        self.assertEqual((sig, how), (((WALL, 2.0, 2.0),), "partial"))
        lib2 = walls_hd.Library()
        lib2.learn("m", {(0, 0): (t1, t2)}, {"entities": [entity(PILLAR, 4, 4)]})
        self.assertEqual(lib2.pick((t2, ("d", 9, 9, 9))), (((PILLAR, 4.0, 4.0),), "partial"))

    def test_place_moves_names_and_ids(self):
        variant = [(walls_hd.strip_entity(entity(WALL, 0, 0, wall=True)), 3.5, 1.25),
                   (walls_hd.strip_entity(entity(PILLAR, 0, 0)), 0.0, 0.0)]
        out = walls_hd.place(variant, 4, 7, 3)
        t = walls_hd.transform(out[0])["position"]
        self.assertEqual((t["x"], t["z"]), (43.5, 71.25))
        self.assertEqual(out[0]["name"], "mxw_4_7_0")
        self.assertNotEqual(out[0]["id"], out[1]["id"])
        self.assertTrue(all(c["name"].startswith("mxw_4_7_0_") for c in out[0]["components"]))
        self.assertEqual(walls_hd.transform(variant[0][0])["position"]["x"], 0)   # the library's copy is untouched

    def test_build_scene_counts_and_dependencies(self):
        lib = walls_hd.Library()
        k_wall, k_empty = (("d", 1, 2, 0),), (("d", 1, 2, 1),)
        for m in ("m1", "m2", "m3"):     # a model on fewer than 3 D2R wall cells is a set piece (test below)
            lib.learn(m, {(0, 0): k_wall, (1, 0): k_empty}, {"entities": [entity(WALL, 5, 5), entity(PILLAR, 6, 6)]})
        cells = {(2, 2): k_wall, (3, 2): k_empty, (4, 2): (("z", 1, 1, 1),)}
        text, st = walls_hd.build_scene(cells, lib, "act3_kurast")
        scene = json.loads(text)
        self.assertEqual(scene["biomeFilename"], "data/hd/env/biome/act3_kurast.json")
        self.assertEqual(scene["dependencies"]["models"], [{"path": PILLAR}, {"path": WALL}])
        self.assertEqual(len(scene["entities"]), 2)
        self.assertEqual((st["exact"], st["empty"], st["uncovered"], st["cells"], st["entities"], st["set_pieces"]), (2, 1, 1, 3, 2, 0))
        self.assertEqual(sorted(walls_hd.transform(e)["position"]["x"] for e in scene["entities"]), [25.0, 26.0])
        self.assertTrue(all(c["type"] != "PhysicsBodyDefinitionComponent" for e in scene["entities"] for c in e["components"]))


PROP = "data/hd/env/model/act3/kurast/props/book02.model"
BUTTRESS = "data/hd/env/model/act3/kurast/walls/wall_stone_buttress01.model"
ELEVATION = "data/hd/env/model/act3/kurast/walls/wall_elevation_stone01.model"


class CapTest(unittest.TestCase):
    def ents(self, counts):
        out = []
        for model, n in counts:
            out += [walls_hd.strip_entity(entity(model, i * 10, 0)) for i in range(n)]
        return out

    def test_tiers(self):
        self.assertEqual([walls_hd.tier(m) for m in (PROP, BUTTRESS, PILLAR, ELEVATION, WALL)], [0, 1, 1, 2, 2])
        self.assertEqual(walls_hd.tier("x/expansion_town_walls/wall_segment_short.model"), 2)
        self.assertEqual(walls_hd.tier("x/cliff_inside_corner02.model"), 2)

    def test_spread_halves_then_quarters(self):
        self.assertEqual([walls_hd.spread(i) for i in range(4)], [0.5, 0.25, 0.75, 0.125])

    def test_cap_under_the_limit_is_a_no_op(self):
        ents = self.ents([(WALL, 3)])
        self.assertIs(walls_hd.cap(ents, 3), ents)

    def test_cap_drops_props_then_details_and_keeps_walls(self):
        ents = self.ents([(ELEVATION, 10), (BUTTRESS, 8), (PROP, 4)])
        kept = walls_hd.cap(ents, 12)
        c = collections.Counter(walls_hd.model_of(e) for e in kept)
        self.assertEqual(c, {ELEVATION: 10, BUTTRESS: 2})
        self.assertEqual([e["name"] for e in kept], [e["name"] for e in ents if e in kept])   # order kept
        xs = sorted(walls_hd.transform(e)["position"]["x"] for e in kept if walls_hd.model_of(e) == BUTTRESS)
        self.assertGreaterEqual(xs[1] - xs[0], 30)            # spread over the map, not two neighbours

    def test_cap_thins_every_model_of_a_tier_alike(self):
        kept = walls_hd.cap(self.ents([(BUTTRESS, 40), (PILLAR, 20)]), 30)
        c = collections.Counter(walls_hd.model_of(e) for e in kept)
        self.assertEqual(sum(c.values()), 30)
        self.assertTrue(18 <= c[BUTTRESS] <= 22 and 8 <= c[PILLAR] <= 12, c)

    def test_build_scene_caps_placed_models_and_bytes(self):
        lib = walls_hd.Library()
        k = (("d", 1, 2, 0),)
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): k}, {"entities": [entity(ELEVATION, 5, 5), entity(BUTTRESS, 6, 6), entity(PROP, 7, 7, wall=True)]})
        cells = {(x, y): k for x in range(10) for y in range(10)}           # 100 cells x 3 pieces
        text, st = walls_hd.build_scene(cells, lib, "act3_kurast", limit=150)
        scene = json.loads(text)
        c = collections.Counter(walls_hd.model_of(e) for e in scene["entities"])
        self.assertEqual((st["placed"], st["capped"], st["entities"], st["models"]), (300, 150, 150, 2))
        self.assertEqual(c, {ELEVATION: 100, BUTTRESS: 50})
        self.assertNotIn({"path": PROP}, scene["dependencies"]["models"])
        full = len(walls_hd.build_scene(cells, lib, "act3_kurast")[0].encode())
        text, st = walls_hd.build_scene(cells, lib, "act3_kurast", max_bytes=full // 2)
        self.assertLessEqual(len(text.encode()), full // 2)
        self.assertEqual(collections.Counter(walls_hd.model_of(e) for e in json.loads(text)["entities"])[ELEVATION], 100)

    def test_docktown3_is_the_cap(self):
        self.assertEqual((walls_hd.MAX_PLACED, walls_hd.MAX_BYTES), (4423, 4651080))


class GenericTest(unittest.TestCase):
    def lib(self):
        lib = walls_hd.Library()
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): (("expansion/town", 1, 5, 0),), (1, 0): (("expansion/town", 1, 6, 0),),
                          (2, 0): (("expansion/siege", 2, 1, 0),), (3, 0): (("expansion/town", 7, 1, 0),)},
                      {"entities": [entity(WALL, 2, 2), entity(WALL, 12, 2), entity(ELEVATION, 22, 2), entity(PROP, 32, 2)]})
        return lib

    def test_same_folder_and_orientation(self):
        self.assertEqual(self.lib().pick((("expansion/town", 1, 3, 0),)), (((WALL, 2.0, 2.0),), "generic"))

    def test_same_act_when_the_folder_has_none(self):
        self.assertEqual(self.lib().pick((("expansion/town", 2, 3, 0),)), (((ELEVATION, 2.0, 2.0),), "generic"))

    def test_props_specials_and_other_acts_stay_uncovered(self):
        lib = self.lib()
        self.assertEqual(lib.pick((("expansion/town", 7, 3, 0),)), (None, None))      # only a prop learnt there
        self.assertEqual(lib.pick((("expansion/town", 14, 14, 16),)), (None, None))   # orientation 14: not a wall
        self.assertEqual(lib.pick((("act3/kurast", 2, 3, 0),)), (None, None))        # nothing of act3 learnt
        self.assertEqual(lib.pick(((None, 1, 3, 0),)), (None, None))

    def test_set_pieces_are_not_generic(self):
        lib = walls_hd.Library()
        lib.learn("m", {(0, 0): (("act3/kurast", 1, 5, 0),)}, {"entities": [entity(WALL, 2, 2)]})   # 1 cell: set piece
        self.assertEqual(lib.pick((("act3/kurast", 1, 3, 0),)), (None, None))


class LearnLibraryTest(unittest.TestCase):
    def test_learns_only_maps_with_a_scene_and_a_needed_folder(self):
        w = 2
        walls_dt1 = make_dt1([(1, 2, 0, 8, 8, b"w")])
        stock = maps_hd.TileStore({
            "act3/kurast/walls.dt1": walls_dt1,
            "act3/kurast/a.ds1": make_ds1(w, 1, [layer(w, 1, {(1, 0): (cell(2, 0), 1)})], files=["/d2/data/global/tiles/Act3/Kurast/Walls.tg1"]),
            "act3/kurast/noscene.ds1": make_ds1(w, 1, [layer(w, 1, {(0, 0): (cell(2, 0), 1)})], files=["/d2/data/global/tiles/Act3/Kurast/Walls.tg1"]),
            "act1/other/b.ds1": make_ds1(w, 1, [layer(w, 1, {(0, 0): (cell(2, 0), 1)})], files=["/d2/data/global/tiles/Act1/Other/x.tg1"]),
        })
        inp = maps_hd.Inputs([], [], [], maps_hd.TileStore({}), [], [], stock, {"act3/kurast/a", "act1/other/b"}, set())
        asked = []

        def scene_of(key):
            asked.append(key)
            return {"entities": [entity(WALL, 12, 3)]}
        lib = walls_hd.learn_library(inp, {"act3/kurast"}, scene_of)
        self.assertEqual(asked, ["act3/kurast/a"])
        self.assertEqual(lib.pick((("act3/kurast", 1, 2, 0),)), (((WALL, 2.0, 3.0),), "exact"))

    def test_set_piece_models_are_left_out(self):
        lib = walls_hd.Library()
        k = (("d", 1, 2, 0),)
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): k}, {"entities": [entity(WALL, 5, 5), entity(PILLAR, 6, 6)]})
        lib.learn("duriel", {(0, 0): k}, {"entities": [entity(WALL, 5, 5), entity(PILLAR, 6, 6), entity(IVY, 7, 7, wall=True)]})
        self.assertTrue(lib.set_piece(IVY))           # on 1 D2R wall cell
        self.assertFalse(lib.set_piece(WALL))         # on 4
        _text, st = walls_hd.build_scene({(0, 0): k}, lib, "act3_kurast")
        self.assertEqual((st["entities"], st["set_pieces"]), (2, 0))      # the common variant has no set piece
        duriel = next(sig for sig in lib.seen[k] if len(sig) == 3)
        lib.seen[k] = collections.Counter({duriel: 9})                    # make duriel's variant the pick
        _text, st = walls_hd.build_scene({(0, 0): k}, lib, "act3_kurast")
        self.assertEqual((st["entities"], st["set_pieces"]), (2, 1))

    def test_decor_props(self):
        for m in ("expansion_town_containers/chest01.model", "town/sword01.model", "SnowProps/slush_pile_04.model"):
            self.assertTrue(walls_hd.is_decor(entity("data/hd/env/model/x/" + m, 0, 0)), m)
        self.assertFalse(walls_hd.is_decor(entity("data/hd/env/model/x/expansion_town_walls/wall_segment_short.model", 0, 0)))
        for m in ("act2_arcane_supports/skull_arch01.model", "ruins/rubble_wall02.model", "act3_treeline/small_cluster01.model"):
            self.assertFalse(walls_hd.is_decor(entity("data/hd/env/model/x/" + m, 0, 0)), m)    # structural, kept

    def test_build_writes_scene_per_map(self):
        lib = walls_hd.Library()
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): (("d", 1, 2, 0),)}, {"entities": [entity(WALL, 5, 5)]})
        with tempfile.TemporaryDirectory() as td:
            st = walls_hd.build(Path(td), [{"map": "expansion/x/y.ds1", "biome": "act4_fort"}], {"expansion/x/y.ds1": {(1, 1): (("d", 1, 2, 0),)}}, lib)
            p = Path(td) / "hd" / "env" / "preset" / "expansion" / "x" / "y.json"
            self.assertTrue(p.exists())
            self.assertEqual(st["expansion/x/y.ds1"]["bytes"], len(p.read_bytes()))
            self.assertEqual(walls_hd.transform(json.loads(p.read_text())["entities"][0])["position"]["x"], 15.0)

    def test_build_keeps_the_floor_biome_of_maps_hd(self):
        lib = walls_hd.Library()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "hd" / "env" / "preset" / "expansion" / "x" / "y.json"
            p.parent.mkdir(parents=True)
            p.write_text(maps_hd.scene_json("mxl2012_act4_fort"))
            st = walls_hd.build(Path(td), [{"map": "expansion/x/y.ds1", "biome": "act4_fort"}], {"expansion/x/y.ds1": {}}, lib)
            self.assertEqual(st["expansion/x/y.ds1"]["biome"], "mxl2012_act4_fort")
            self.assertEqual(json.loads(p.read_text())["biomeFilename"], "data/hd/env/biome/mxl2012_act4_fort.json")

    def test_the_eight_maps_are_median_paths(self):
        self.assertEqual(len(walls_hd.MAPS), 8)
        self.assertTrue(all(m.startswith("expansion/") and m.endswith(".ds1") for m in walls_hd.MAPS))


if __name__ == "__main__":
    unittest.main()
