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


def make_ds1(w, h, walls, files=(), version=18, floor=None):
    """walls: [(cells, orientations)] per wall layer (w*h dwords each); one floor layer (`floor`: w*h dwords, else empty);
    header lists `files`."""
    n = w * h
    out = struct.pack("<iiii", version, w - 1, h - 1, 0) + struct.pack("<i", 0)
    out += struct.pack("<i", len(files)) + b"".join(f.encode() + b"\0" for f in files)
    out += struct.pack("<ii", len(walls), 1)
    for wc, oc in walls:
        out += struct.pack("<%dI" % n, *wc) + struct.pack("<%dI" % n, *oc)
    out += struct.pack("<%dI" % n, *(floor or [0] * n)) + struct.pack("<%dI" % n, *([0] * n))   # floor, shadow
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

    def test_floor_cells_skip_walls_and_unresolved(self):
        w = 3
        floor = [cell(5, 0), cell(2, 1), cell(7, 7), 0, cell(2, 1), 0]
        ds = ds1_remap.Ds1(make_ds1(w, 2, [layer(w, 2, {(0, 0): (cell(2, 0), 1)})], floor=floor))
        tiles = {"mod/new/floor.dt1": dt1.parse(make_dt1([(0, 5, 0, 8, 8, b"f"), (0, 2, 1, 8, 8, b"g")])),
                 "act1/caves/cave.dt1": dt1.parse(make_dt1([(1, 2, 0, 8, 8, b"w")]))}
        donor = lambda p: "act1/caves/cave.dt1" if p.startswith("mod/") else p   # noqa: E731
        cells = walls_hd.map_cells(ds, ["mod/new/floor.dt1", "act1/caves/cave.dt1"], tiles.get, donor)
        self.assertEqual(cells[(0, 0)], (("act1/caves", 1, 2, 0),))      # the wall wins: no floor key on a wall cell
        self.assertEqual(cells[(1, 0)], (("act1/caves", 0, 2, 1),))
        self.assertNotIn((2, 0), cells)                                    # floor tile in no file
        self.assertEqual(set(cells), {(0, 0), (1, 0), (1, 1)})
        self.assertTrue(walls_hd.is_floor(cells[(1, 0)]))
        self.assertFalse(walls_hd.is_floor(cells[(0, 0)]))

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

    def test_model_variations_count_as_models(self):
        e = entity(WALL, 1, 1)
        e["components"] = [c for c in e["components"] if c["type"] != "ModelDefinitionComponent"]
        e["components"].append({"type": "ModelVariationDefinitionComponent", "name": "v", "variations": [
            {"type": "ModelVariationEntry", "weight": 0.5, "filename": WALL}, {"type": "ModelVariationEntry", "weight": 0.5,
                                                                              "filename": PILLAR}]})
        self.assertEqual(walls_hd.model_of(e), WALL)
        self.assertEqual(walls_hd.models_of(e), [WALL, PILLAR])
        self.assertEqual(len(walls_hd.wall_entities({"entities": [e]})), 1)
        s = walls_hd.strip_entity(e)
        self.assertIn("ModelVariationDefinitionComponent", [c["type"] for c in s["components"]])
        scene = json.loads(walls_hd.scene_json("act3_kurast", walls_hd.place([(s, 0.0, 0.0)], 1, 1, 0)))
        self.assertEqual(scene["dependencies"]["models"], [{"path": PILLAR}, {"path": WALL}])

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


    def test_floor_cells_are_counted_apart(self):
        lib = walls_hd.Library()
        f_wall, f_bare = (("act1/caves", 0, 2, 0),), (("act1/caves", 0, 5, 0),)
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): f_wall, (1, 0): f_bare}, {"entities": [entity(WALL, 5, 5)]})
        cells = {(2, 2): f_wall, (3, 2): f_bare, (4, 2): (("act1/caves", 0, 9, 9),), (5, 2): (("z", 1, 1, 1),)}
        text, st = walls_hd.build_scene(cells, lib, "act1_caves")
        self.assertEqual(len(json.loads(text)["entities"]), 1)
        self.assertEqual((st["floor_cells"], st["floor_walls"], st["cells"], st["uncovered"]), (3, 1, 1, 1))
        self.assertEqual(lib.pick((("act1/caves", 0, 9, 9),)), ((), "floor"))   # a floor D2R never has stays bare


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

    def test_the_seventeen_maps(self):
        self.assertEqual((len(walls_hd.RETEXTURED), len(walls_hd.STOCK), len(set(walls_hd.MAPS))), (8, 9, 17))
        self.assertTrue(all(m.startswith("expansion/") and m.endswith(".ds1") for m in walls_hd.RETEXTURED))
        self.assertTrue(all(m.endswith(".ds1") for m in walls_hd.STOCK))


def _inside(pos, t, x, z):
    a, b, c = (pos[i] for i in t)
    d = (b[2] - c[2]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[2] - c[2])
    u = ((b[2] - c[2]) * (x - c[0]) + (c[0] - b[0]) * (z - c[2])) / d
    v = ((c[2] - a[2]) * (x - c[0]) + (a[0] - c[0]) * (z - c[2])) / d
    return u > 0 and v > 0 and u + v < 1


def _template():
    """D2R's sancte terrain model from the D2R extraction or the shared cache, None without them."""
    try:
        import fxpaths
        rel = "data/hd/env/preset/act2/arcane/sancte/terrain_lod0.model"
        for p in (fxpaths.D2R / rel, fxpaths.D2R_CACHE / rel):
            if p.exists():
                return p.read_bytes()
    except Exception:   # noqa: BLE001  (no local D2R paths configured)
        return None
    return None


TEMPLATE = _template()


def raised(model, x, y, z, name="e"):
    e = entity(model, x, z, name=name)
    e["components"][0]["position"]["y"] = y
    return e


class GroundTest(unittest.TestCase):
    """D2R's terrain heights and the entities moved down to the gameplay plane (lane walls3)."""

    def slope(self):
        # two triangles over x, z in 0..20: y = x (a ramp), and a vertex at y = 7 far from it
        pos = [(0.0, 0.0, 0.0), (20.0, 20.0, 0.0), (20.0, 20.0, 20.0), (0.0, 0.0, 20.0), (60.0, 7.0, 60.0)]
        return walls_hd.Ground(pos, [(0, 2, 1), (0, 3, 2)])

    def test_height_inside_outside_and_far(self):
        g = self.slope()
        self.assertAlmostEqual(g.height(5.0, 5.0), 5.0)
        self.assertAlmostEqual(g.height(15.0, 2.0), 15.0)
        self.assertAlmostEqual(g.height(65.0, 60.0), 7.0)     # no triangle: the nearest vertex within 15 units
        self.assertEqual(g.height(200.0, 200.0), 0.0)        # nothing near: flat

    def test_highest_triangle_wins(self):
        pos = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 0.0, 10.0), (0.0, 4.0, 0.0), (10.0, 4.0, 0.0), (0.0, 4.0, 10.0)]
        self.assertAlmostEqual(walls_hd.Ground(pos, [(0, 1, 2), (3, 4, 5)]).height(2.0, 2.0), 4.0)

    def test_wall_entities_move_down_the_isometric_diagonal(self):
        g = walls_hd.Ground([(0.0, 35.0, 0.0), (100.0, 35.0, 0.0), (0.0, 35.0, 100.0)], [(0, 1, 2)])
        scene = {"entities": [raised(WALL, 45.0, 35.0, 40.0)]}
        (e, x, z), = walls_hd.wall_entities(scene, g)
        self.assertEqual((x, z), (10.0, 5.0))
        self.assertEqual(walls_hd.transform(e)["position"], {"x": 10.0, "y": 0.0, "z": 5.0})
        self.assertEqual(walls_hd.transform(scene["entities"][0])["position"]["x"], 45.0)    # the scene is not changed
        (_e, x, z), = walls_hd.wall_entities(scene)                                            # no ground: as it is
        self.assertEqual((x, z), (45.0, 40.0))

    def test_learn_with_ground_puts_raised_walls_on_their_tile(self):
        g = walls_hd.Ground([(0.0, 30.0, 0.0), (100.0, 30.0, 0.0), (0.0, 30.0, 100.0)], [(0, 1, 2)])
        key = (("act4/fort", 1, 2, 0),)
        lib = walls_hd.Library()
        lib.learn("m", {(1, 1): key}, {"entities": [raised(WALL, 45.0, 30.0, 42.0)]}, g)    # drawn 3 tiles off its cell
        self.assertEqual(lib.pick(key), (((WALL, 5.0, 2.0),), "exact"))

    def test_terrain_mesh_decodes_int16_positions(self):
        class O(dict):
            def __init__(self, d=None, obj=None):
                super().__init__(d or {})
                self.obj = obj

        vert = [O({"Position": [32767, 0, 16384, 0]}), O({"Position": [0, 32767, 0, 0]}), O({"Position": [0, 0, 32767, 0]})]
        mesh = O({"ExtendedData": O(obj=O({"VertexScale": 50.0})), "PrimaryVertexData": O({"Vertices": O(obj=vert)}),
                  "PrimaryTopology": O({"Indices16": [O({"Int16": i}) for i in (0, 1, 2)]})})
        pos, tris = walls_hd.terrain_mesh({"Meshes": [mesh]})
        self.assertEqual(tris, [(0, 1, 2)])
        self.assertEqual([round(c, 2) for c in pos[0]], [50.0, 0.0, 25.0])
        self.assertEqual([round(c, 2) for c in pos[1]], [0.0, 50.0, 0.0])

    def test_terrain_path(self):
        scene = {"terrain": {"components": [{"type": "ModelDefinitionComponent",
                                             "filename": "data/hd/env/preset/act2/arcane/sanctE/terrain.model"}]}}
        self.assertEqual(walls_hd.terrain_path(scene), "data/hd/env/preset/act2/arcane/sancte/terrain_lod0.model")
        self.assertIsNone(walls_hd.terrain_path({"terrain": {}}))
        self.assertIsNone(walls_hd.terrain_path({}))
        self.assertIsNone(walls_hd.d2r_ground("x", {"terrain": {}}))


STAIRS = "data/hd/env/model/act1/caves/act1_caves_walls/back_stairs01.model"


class AnchorTest(unittest.TestCase):
    """Pieces that stand on no learnt cell hang on the rarest key next to them (lane walls3: the caves' stairs)."""

    def lib(self, maps=3, with_stairs=3):
        lib = walls_hd.Library()
        floor, stairs = (("act1/caves", 0, 5, 0),), (("act1/caves", 0, 3, 8),)
        for n in range(maps):
            cells = {(x, y): floor for x in range(6) for y in range(4)}
            cells[(5, 2)] = stairs
            del cells[(3, 1)]                            # the void cell the stairs model stands on
            ents = [raised(STAIRS, 32.0, 0.0, 18.0)] if n < with_stairs else []
            lib.learn("m%d" % n, cells, {"entities": ents})
        lib.anchor()
        return lib, floor, stairs

    def test_homeless_piece_hangs_on_the_rare_key(self):
        lib, floor, stairs = self.lib()
        self.assertEqual([(walls_hd.model_of(e), dx, dz) for e, dx, dz in lib.anchored[stairs]], [(STAIRS, -18.0, -2.0)])
        self.assertNotIn(floor, lib.anchored)
        self.assertEqual(lib.maps, {})
        text, st = walls_hd.build_scene({(4, 4): floor, (7, 3): stairs}, lib, "act1_caves")
        self.assertEqual((st["anchored"], st["entities"]), (1, 1))
        p = walls_hd.transform(json.loads(text)["entities"][0])["position"]
        self.assertEqual((p["x"], p["z"]), (52.0, 28.0))

    def test_too_rare_or_too_few_stay_out(self):
        self.assertEqual(self.lib(maps=2, with_stairs=2)[0].anchored, {})       # fewer than SET_PIECE_CELLS
        self.assertEqual(self.lib(maps=10, with_stairs=3)[0].anchored, {})      # on 3 of 10 cells of the key


class PartialFallbackTest(unittest.TestCase):
    def test_a_bare_partial_wall_gets_the_generic_wall(self):
        lib = walls_hd.Library()
        a, b, c = ("act4/fort", 1, 4, 0), ("act4/fort", 1, 4, 3), ("act4/fort", 1, 1, 0)
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): (a, ("act4/fort", 8, 3, 0)), (1, 0): (c,)}, {"entities": [entity(WALL, 12, 2)]})
        self.assertEqual(lib.pick((a, b)), (((WALL, 2.0, 2.0),), "generic"))    # shares a bare key only: the tile set's wall
        self.assertEqual(lib.pick((a, ("act4/fort", 8, 3, 0))), ((), "exact"))  # D2R draws that one bare: stays bare


class TerrainTest(unittest.TestCase):
    def test_terrain_cells_drop_lone_corner_tiles(self):
        cells = {(0, 0), (5, 5), (5, 6), (6, 6), (47, 47)}
        self.assertEqual(walls_hd.terrain_cells(cells), {(5, 5), (5, 6), (6, 6)})

    def test_terrain_entity_and_dependency(self):
        path = "data/hd/env/preset/act2/arcane/belial/terrain.model"
        scene = json.loads(walls_hd.add_terrain(walls_hd.scene_json("act2_arcane", []), path))
        self.assertEqual(scene["terrain"]["name"], "terrain")
        types = [c["type"] for c in scene["terrain"]["components"]]
        self.assertEqual(types, ["TransformDefinitionComponent", "TerrainDefinitionComponent", "ModelDefinitionComponent"])
        self.assertIn({"path": path}, scene["dependencies"]["models"])     # where D2R's own scenes name their terrain
        self.assertNotIn({"path": path}, scene["dependencies"].get("other", []))
        self.assertEqual(walls_hd.terrain_path(scene), "data/hd/env/preset/act2/arcane/belial/terrain_lod0.model")

    def test_half_floats(self):
        self.assertEqual((walls_hd._half(1.0), walls_hd._half(0.5), walls_hd._half(0.0)), (15360, 14336, 0))

    @unittest.skipUnless(TEMPLATE, "D2R's sancte terrain model is in neither the D2R extraction nor the cache")
    def test_terrain_model_over_the_cells(self):
        import d2r_model
        out = walls_hd.terrain_model(TEMPLATE, {(3, 4), (4, 4), (4, 5)}, 13, 13)
        tree = d2r_model.parse_tree(d2r_model.Gr2File.read(out))
        pos, tris = walls_hd.terrain_mesh(tree)
        self.assertEqual((len(tris), len(pos)), (6, 8))                     # corners shared
        self.assertEqual({round(p[1], 3) for p in pos}, {0.0})
        for x, z in ((35.0, 45.0), (45.0, 55.0)):
            self.assertTrue(any(_inside(pos, t, x, z) for t in tris), (x, z))
        self.assertFalse(any(_inside(pos, t, 35.0, 55.0) for t in tris))   # (3, 5) is not covered
        ed = tree["Meshes"][0]["ExtendedData"].obj
        self.assertEqual([round(v, 2) for v in ed["bbMin"] + ed["bbMax"]], [30.0, 0.0, 40.0, 50.0, 0.0, 60.0])
        self.assertEqual(tree["Models"][0]["InitialPlacement"].position, (65.0, 0.0, 65.0))
        for a, b, c in tris:                                                # wound as D2R's
            p, q, r = pos[a], pos[b], pos[c]
            self.assertLess((q[0] - p[0]) * (r[2] - p[2]) - (q[2] - p[2]) * (r[0] - p[0]), 0)

    @unittest.skipUnless(TEMPLATE, "D2R's sancte terrain model is in neither the D2R extraction nor the cache")
    def test_padded_to_the_template_with_the_biome(self):
        """Lane tunnels: the template's vertex and index counts, so its model_lod_desc.bin entry fits; the material names the
        scene's biome."""
        import d2r_model
        tpl = d2r_model.parse_tree(d2r_model.Gr2File.read(TEMPLATE))["Meshes"][0]
        out = walls_hd.terrain_model(TEMPLATE, {(3, 4), (4, 4), (4, 5)}, 13, 13, pad=True, biome="act2_arcane")
        tree = d2r_model.parse_tree(d2r_model.Gr2File.read(out))
        mesh = tree["Meshes"][0]
        self.assertEqual(len(mesh["PrimaryVertexData"]["Vertices"].obj), len(tpl["PrimaryVertexData"]["Vertices"].obj))
        self.assertEqual(len(mesh["PrimaryTopology"]["Indices16"]), len(tpl["PrimaryTopology"]["Indices16"]))
        pos, tris = walls_hd.terrain_mesh(tree)
        self.assertEqual(len([t for t in tris if len(set(t)) == 3]), 6)       # the padding is degenerate
        self.assertEqual([round(v, 2) for v in mesh["ExtendedData"].obj["bbMin"]], [30.0, 0.0, 40.0])
        self.assertEqual(tree["Textures"][0]["FromFileName"], "data/hd/env/biome/act2_arcane.json")
        with self.assertRaises(ValueError):
            walls_hd.terrain_model(TEMPLATE, {(x, y) for x in range(20) for y in range(20)}, 21, 21, pad=True)


def lod_table(path, bb=(0.0, 0.0, 0.0, 9.0, 0.0, 9.0)):
    """A model_lod_desc.bin with one entry (`path`), one 12-byte and one 32-byte stream record (tools/model_lod_desc.py)."""
    import model_lod_desc
    a1, a2, a3 = 24, 24 + 44, 24 + 44 + 12
    e = struct.pack("<I6f", model_lod_desc.fnv(path), *bb) + bytes([2, 0, 0, 0]) + struct.pack("<3I", 1, a2 - (a1 + 36), 1)
    rec2 = struct.pack("<3I", 7, 1, a3 - (a2 + 8))
    rec3 = struct.pack("<6f2I", *bb, 1, 0x200001)
    return struct.pack("<6i", 1, a1 - 4, 1, a2 - 12, 1, a3 - 20) + e + rec2 + rec3


class LodDescTest(unittest.TestCase):
    """Lane tunnels: a generated terrain gets an entry in the mod's model_lod_desc.bin, else the engine never draws it."""
    DONOR = "data/hd/env/preset/act3/jungle/pygn2/terrain.model"

    def test_entry_added_with_own_bounds_and_the_donor_records(self):
        import model_lod_desc
        new = "data/hd/env/preset/act2/arcane/belial/terrain.model"
        with tempfile.TemporaryDirectory() as d:
            n = walls_hd.write_lod_desc(Path(d), [(new, self.DONOR, ((110.0, 0.0, 60.0), (220.0, 0.0, 320.0)))],
                                        d2r_read=lambda rel: lod_table(self.DONOR) if rel == walls_hd.LOD_DESC else None)
            data = (Path(d) / "hd" / "model_lod_desc.bin").read_bytes()
        self.assertEqual(n, 1)
        entries, a2, a3, _counts = model_lod_desc.parse(data)
        self.assertEqual(len(entries), 2)
        e, donor = model_lod_desc.find(entries, new), model_lod_desc.find(entries, self.DONOR)
        self.assertEqual(struct.unpack_from("<6f", e, 4), (110.0, 0.0, 60.0, 220.0, 0.0, 320.0))
        self.assertEqual(e[28:36], donor[28:36])                              # LOD mask and count
        target = [24 + i * 44 + 36 + struct.unpack_from("<I", x, 36)[0] for i, x in enumerate(entries) if x in (e, donor)]
        self.assertEqual(len(set(target)), 1)                                 # the same stream record

    def test_nothing_written_without_entries(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(walls_hd.write_lod_desc(Path(d), [], d2r_read=lambda rel: self.fail("read")), 0)
            self.assertFalse((Path(d) / "hd").exists())

    def test_no_terrain_ships(self):
        # the indexed belial mesh changed nothing in game (docs/maps-hd.md item 12), so no map gets one and the game's own
        # model_lod_desc.bin is not replaced
        self.assertEqual(walls_hd.TERRAIN_MAPS, {})
        self.assertEqual(walls_hd.terrain_maps({}), {})

    def test_the_switch_adds_belial(self):
        # lane tunnels65: the belial terrain is tried again behind MXL2012_BELIAL_TERRAIN=1 (default off)
        self.assertEqual(walls_hd.terrain_maps({walls_hd.TERRAIN_SWITCH: "1"}), {"act2/arcane/belial.ds1": "act3/jungle/pygn2"})
        self.assertEqual(walls_hd.terrain_maps({walls_hd.TERRAIN_SWITCH: "0"}), {})


def square(x0, x1, y0, y1):
    """Opaque pixels of a rectangle, as dt1_pixels.tiles gives them."""
    return [(x, y, 1) for x in range(x0, x1) for y in range(y0, y1)]


ARCH = "data/hd/env/model/act4/fort/fortress/arch01.model"
TREE = "data/hd/env/model/expansion/town/expansion_tree_dead05.model"
HUT = "data/hd/env/model/act4/fort/fortress/hut_blacksmith01.model"


class LookalikeTest(unittest.TestCase):
    """Lane walls4: a wall tile D2R never has borrows the variant of the learnt tile with the same silhouette."""

    def lib(self):
        lib = walls_hd.Library()
        f = "act4/fort"
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): ((f, 1, 3, 1),), (1, 0): ((f, 1, 3, 0),), (2, 0): ((f, 1, 3, 5),)},
                      {"entities": [entity(ARCH, 2, 2), entity(WALL, 12, 2), entity(WALL, 22, 2)]})
        arch, wall = square(0, 32, -64, 0), square(64, 96, -64, 0)
        lib.pixels_of = lambda folder: {(1, 3, 1): arch, (1, 3, 0): wall, (1, 3, 5): wall, (1, 4, 2): arch,
                                        (1, 4, 3): square(0, 30, -60, 0), (1, 4, 0): square(0, 32, -32, 0)} if folder == f else {}
        return lib, f

    def test_same_silhouette_gets_the_learnt_variant(self):
        lib, f = self.lib()
        self.assertEqual(lib.pick(((f, 1, 4, 2),)), (((ARCH, 2.0, 2.0),), "lookalike"))
        self.assertEqual(lib.pick(((f, 1, 4, 3),)), (((ARCH, 2.0, 2.0),), "lookalike"))     # IoU 0.88

    def test_other_silhouettes_and_orientations_stay_generic(self):
        lib, f = self.lib()
        self.assertEqual(lib.pick(((f, 1, 4, 0),)), (((WALL, 2.0, 2.0),), "generic"))       # IoU 0.5 with the arch
        self.assertEqual(lib.pick(((f, 2, 4, 2),)), (None, None))                          # nothing of orientation 2
        lib.pixels_of = None
        lib._pixels, lib._lookalike = {}, {}
        self.assertEqual(lib.pick(((f, 1, 4, 2),)), (((WALL, 2.0, 2.0),), "generic"))      # no pixels: as before

    def test_two_layers_draw_both(self):
        lib, f = self.lib()
        sig, how = lib.pick(((f, 1, 4, 0), (f, 1, 4, 2)))
        self.assertEqual((sorted(sig), how), (sorted([(WALL, 2.0, 2.0), (ARCH, 2.0, 2.0)]), "lookalike"))
        text, st = walls_hd.build_scene({(3, 3): ((f, 1, 4, 0), (f, 1, 4, 2))}, lib, "act4_fort")
        self.assertEqual((st["lookalike"], st["entities"]), (1, 2))


class TreeTest(unittest.TestCase):
    """Lane walls4: orientation-14 trees get D2R's tree on the trunk tile; crown pieces stay without."""
    T, TRUNK, CROWN, OTHER = "expansion/town", ("expansion/town", 14, 14, 12), ("expansion/town", 14, 14, 16), ("expansion/town", 14, 15, 3)

    def lib(self, tree_maps=3, maps=3):
        lib = walls_hd.Library()
        for n in range(maps):
            ents = [entity(TREE, 3.8, 1.0)] if n < tree_maps else []
            lib.learn("m%d" % n, {(0, 0): (self.TRUNK,), (1, 0): (self.CROWN,)}, {"entities": ents})
        trunk, crown = square(0, 16, -40, -10), square(0, 16, -200, -120)
        lib.pixels_of = lambda folder: {self.TRUNK[1:]: trunk, self.CROWN[1:]: crown, self.OTHER[1:]: trunk, (14, 14, 17): crown}
        return lib

    def test_trunk_crown_and_folder_fallback(self):
        lib = self.lib()
        self.assertEqual([(walls_hd.model_of(e), dx, dz) for e, dx, dz in lib.tree_pick(self.TRUNK)], [(TREE, 3.8, 1.0)])
        self.assertEqual(lib.tree_pick(self.CROWN), [])
        self.assertEqual([(walls_hd.model_of(e), dx, dz) for e, dx, dz in lib.tree_pick(self.OTHER)], [(TREE, 3.8, 1.0)])
        self.assertEqual(lib.tree_pick(("act2/jungle", 14, 1, 0)), [])

    def test_a_tree_on_too_few_cells_is_not_the_tiles(self):
        self.assertEqual(self.lib(tree_maps=1, maps=10).tree_pick(self.TRUNK), [])        # 1 of 10 < MIN_MODEL_SHARE

    def test_build_scene_counts_tree_cells(self):
        crown = (self.T, 14, 14, 17)                                               # keys D2R never has: no exact pick
        text, st = walls_hd.build_scene({(5, 5): (self.OTHER,), (6, 5): (crown,)}, self.lib(), "expansion_town")
        self.assertEqual((st["trees"], st["tree_cells"], st["uncovered"], st["entities"]), (1, 2, 0, 1))
        p = walls_hd.transform(json.loads(text)["entities"][0])["position"]
        self.assertEqual((p["x"], p["z"]), (53.8, 51.0))

    def test_a_tree_the_variant_has_is_not_doubled(self):
        lib = self.lib()
        oak = "data/hd/env/model/act1/graveyard/act1_tree_oak04.model"            # not decor: also in the exact variant
        lib.seen[(self.TRUNK,)] = collections.Counter({((oak, 3.8, 1.0),): 3})
        lib.variants[((oak, 3.8, 1.0),)] = [(entity(oak, 0, 0), 3.8, 1.0)]
        lib.trees[self.TRUNK] = collections.Counter({(oak, 3.8, 1.0): 3})
        lib.tree_items[(self.TRUNK, oak, 3.8, 1.0)] = entity(oak, 0, 0)
        lib.model_cells[oak] = 3
        _text, st = walls_hd.build_scene({(5, 5): (self.TRUNK,)}, lib, "act1_graveyard")
        self.assertEqual((st["trees"], st["entities"]), (0, 1))

    def test_a_tree_cell_draws_only_its_tree(self):
        lib = self.lib()
        seg = "data/hd/env/model/expansion/town/expansion_town_walls/wall_segment_short.model"   # a neighbour's wall
        lib.seen[(self.TRUNK,)] = collections.Counter({((seg, 9.1, 3.6),): 3})
        lib.variants[((seg, 9.1, 3.6),)] = [(entity(seg, 0, 0), 9.1, 3.6)]
        lib.model_cells[seg] = 3
        text, st = walls_hd.build_scene({(5, 5): (self.TRUNK,)}, lib, "expansion_town")
        self.assertEqual((st["trees"], st["tree_cells"], st["exact"]), (1, 1, 0))
        self.assertEqual([walls_hd.model_of(e) for e in json.loads(text)["entities"]], [TREE])


class PieceTest(unittest.TestCase):
    """Lane walls4: one-off D2R pieces (a Fortress hut with its roof) placed where the map repeats the wall tiles under them."""
    KEYS = [(("act4/fort", 1, 3, n),) for n in range(6)]

    def lib(self):
        lib = walls_hd.Library()
        cells = {(2 + n % 3, 2 + n // 3): k for n, k in enumerate(self.KEYS)}
        lib.learn("fort", cells, {"entities": [entity(HUT, 25, 25)]})
        lib.learn_pieces(lambda m: ((-5.0, 0.0, -5.0), (25.0, 0.0, 15.0)) if m == HUT else None)
        return lib

    def test_footprint_turns_with_the_yaw(self):
        walls = {(x, z): (("f", 1, 1, x * 10 + z),) for x in range(4) for z in range(6)}
        e = entity(HUT, 5, 35)
        e["components"][0]["orientation"] = {"x": 0.0, "y": 2 ** -0.5, "z": 0.0, "w": 2 ** -0.5}   # 90 degrees
        foot = walls_hd.footprint(e, 5.0, 35.0, ((0.0, 0.0, 0.0), (25.0, 0.0, 5.0)), walls)
        self.assertEqual(set(foot), {(dx, dy) for dx in (0, 1) for dy in (-2, -1, 0)})
        self.assertIsNone(walls_hd.footprint(e, 5.0, 35.0, None, walls))
        self.assertIsNone(walls_hd.footprint(entity(HUT, 5, 5), 5.0, 5.0, ((0.0, 0.0, 0.0), (1.0, 0.0, 1.0)), walls))

    def test_learnt_and_fitted(self):
        lib = self.lib()
        self.assertEqual(len(lib.pieces), 1)
        cells = {(10 + n % 3, 7 + n // 3): k for n, k in enumerate(self.KEYS) if n != 5}      # 5 of 6 cells
        self.assertEqual([(walls_hd.model_of(e), x, y, dx, dz) for e, x, y, dx, dz in lib.fit(cells)], [(HUT, 10, 7, 5.0, 5.0)])
        text, st = walls_hd.build_scene(cells, lib, "act4_fort")
        self.assertEqual(st["pieces"], 1)
        hut = [e for e in json.loads(text)["entities"] if walls_hd.model_of(e) == HUT]
        self.assertTrue(hut[0]["name"].startswith("mxp_10_7_"))
        self.assertEqual((walls_hd.transform(hut[0])["position"]["x"], walls_hd.transform(hut[0])["position"]["z"]), (105.0, 75.0))

    def test_too_few_cells_or_keys_do_not_fit(self):
        lib = self.lib()
        self.assertEqual(lib.fit({(10 + n, 7): k for n, k in enumerate(self.KEYS[:3])}), [])
        self.assertEqual(lib.fit({(10 + n % 3, 7 + n // 3): self.KEYS[0] for n in range(6)}), [])
        self.assertEqual(walls_hd.learn_library.__defaults__[-1], None)                  # no boxes: no set pieces by layout


if __name__ == "__main__":
    unittest.main()
