"""Unit tests of tools/map_tint.py (each retextured map's own key light) and tools/dt1_pixels.py on synthetic data.

  py -3 -I -m unittest discover -s tools/tests -p "test_map_tint.py" -v
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
import dt1_pixels  # noqa: E402
import map_tint  # noqa: E402
import maps_hd  # noqa: E402
import walls_hd  # noqa: E402

CHARISMATIC = "expansion/zakarum/charismatic.ds1"


def light(name, rgb, power, mask):
    return {"type": "Entity", "name": name, "id": 1, "components": [
        {"type": "DirectionalLightDefinitionComponent", "name": name + "_l", "color": dict(zip("xyz", rgb)), "power": power,
         "lightMask": mask},
        {"type": "TransformDefinitionComponent", "name": name + "_t"}]}


def vis(name="act4_fort_day"):
    return {"dependencies": {"other": [{"path": "data/hd/env/lut/default.dds"}]}, "type": "VisualDataDefinition", "name": name,
            "entities": [{"type": "Entity", "name": "vis_data", "components": [{"type": "VisualDataComponent", "exposureValue": 4.0}]},
                         light("global_key_light", (1.0, 1.0, 1.0), 25.0, 9),
                         light("player_key_light", (1.0, 0.94, 0.88), 30.0, 68)]}


def biome(name="act4_fort"):
    slots = ["day", "dawn1", "night"]
    return {"dependencies": {"json": [{"path": "data/hd/env/tilemasks/tile_masks.json"}] +
                             [{"path": "data/hd/env/vis/%s_%s.json" % (name, s)} for s in slots]},
            "type": "Biome", "name": name, "tileMaskFilename": "data/hd/env/tilemasks/tile_masks.json",
            "visualDataFilenames": [{"type": "BiomeVisualDataFile", "name": "f%d" % i,
                                     "visualDataFilename": "data/hd/env/vis/%s_%s.json" % (name, s)} for i, s in enumerate(slots)]}


def reader(files):
    def read(rel):
        if rel not in files:
            raise KeyError(rel)
        return json.loads(json.dumps(files[rel]))
    return read


D2R = {"data/hd/env/biome/act4_fort.json": biome(), "data/hd/env/vis/act4_fort_day.json": vis()}


class Pixels(unittest.TestCase):
    def test_iso_floor_block_is_a_diamond_of_256(self):
        px = dt1_pixels.block_pixels(1, bytes(range(256)))
        self.assertEqual(len(px), 256)
        self.assertEqual(px[0], (14, 0, 0))                 # first row: 4 pixels from x 14
        self.assertEqual([p for p in px if p[1] == 7][0], (0, 7, 112))  # widest row: 32 pixels from x 0, after 4+8+...+28
        self.assertEqual(max(p[1] for p in px), 14)

    def test_rle_block_skips_and_rows(self):
        data = bytes([2, 3, 7, 8, 9, 0, 0, 1, 1, 5])        # row 0: skip 2, 3 pixels; row 1: skip 1, 1 pixel
        self.assertEqual(dt1_pixels.block_pixels(5, data), [(2, 0, 7), (3, 0, 8), (4, 0, 9), (1, 1, 5)])

    def test_tiles_reads_blocks_at_their_offsets(self):
        ptr = 0x114
        tile_hdr = ptr
        blocks = tile_hdr + 96
        data_at = blocks + 20
        rle = bytes([0, 2, 11, 12])
        buf = bytearray(data_at + len(rle))
        struct.pack_into("<ii", buf, 0, 7, 6)
        struct.pack_into("<ii", buf, 0x10C, 1, ptr)
        struct.pack_into("<iii", buf, tile_hdr + 20, 3, 4, 5)                  # orientation, style, sequence
        struct.pack_into("<iii", buf, tile_hdr + 72, blocks, 20 + len(rle), 1)  # block pointer, length, count
        struct.pack_into("<hhhBBhihi", buf, blocks, 32, -64, 0, 1, 0, 5, len(rle), 0, 20)
        buf[data_at:] = rle
        self.assertEqual(dt1_pixels.tiles(bytes(buf)), {(3, 4, 5): [(32, -64, 11), (33, -64, 12)]})


class Light(unittest.TestCase):
    def test_tints_cover_the_retextured_maps(self):
        self.assertEqual(set(map_tint.TINTS), set(walls_hd.RETEXTURED))
        for m, t in map_tint.TINTS.items():
            self.assertTrue(all(0.0 <= c <= 1.0 for c in t.rgb) and max(t.rgb) == 1.0, m)
            self.assertTrue(0.3 <= t.power <= 2.0, m)

    def test_tinted_vis_changes_only_the_key_light(self):
        t = map_tint.TINTS[CHARISMATIC]
        out = map_tint.tinted_vis(vis(), "mxl2012_tint_charismatic", t)
        lights = {e["name"]: e["components"][0] for e in out["entities"] if e["name"].endswith("light")}
        self.assertEqual(lights["global_key_light"]["color"], dict(zip("xyz", t.rgb)))
        self.assertAlmostEqual(lights["global_key_light"]["power"], 25.0 * t.power)
        self.assertEqual(lights["player_key_light"], vis()["entities"][2]["components"][0])
        self.assertEqual(out["name"], "mxl2012_tint_charismatic")
        self.assertEqual(out["entities"][0], vis()["entities"][0])

    def test_tinted_vis_without_key_light_fails(self):
        v = vis()
        v["entities"] = v["entities"][:1]
        with self.assertRaises(ValueError):
            map_tint.tinted_vis(v, "x", map_tint.TINTS[CHARISMATIC])

    def test_tinted_biome_names_one_vis_in_every_slot(self):
        out = map_tint.tinted_biome(biome(), "mxl2012_tint_x", "data/hd/env/vis/mxl2012_tint_x.json")
        self.assertEqual({v["visualDataFilename"] for v in out["visualDataFilenames"]}, {"data/hd/env/vis/mxl2012_tint_x.json"})
        self.assertEqual(len(out["visualDataFilenames"]), 3)
        self.assertEqual([d["path"] for d in out["dependencies"]["json"]],
                         ["data/hd/env/tilemasks/tile_masks.json", "data/hd/env/vis/mxl2012_tint_x.json"])
        self.assertEqual(out["tileMaskFilename"], biome()["tileMaskFilename"])
        self.assertEqual(map_tint.day_vis(biome()), "data/hd/env/vis/act4_fort_day.json")

    def test_apply_writes_biome_and_vis(self):
        with tempfile.TemporaryDirectory() as td:
            name = map_tint.apply(Path(td), CHARISMATIC, "act4_fort", reader(D2R))
            self.assertEqual(name, "mxl2012_tint_charismatic")
            b = json.loads((Path(td) / "hd/env/biome/mxl2012_tint_charismatic.json").read_text())
            v = json.loads((Path(td) / "hd/env/vis/mxl2012_tint_charismatic.json").read_text())
            self.assertEqual(b["visualDataFilenames"][0]["visualDataFilename"], "data/hd/env/vis/mxl2012_tint_charismatic.json")
            self.assertEqual(v["entities"][1]["components"][0]["color"]["z"], 1.0)

    def test_apply_starts_from_a_generated_biome_in_data_dir(self):
        with tempfile.TemporaryDirectory() as td:
            own = biome("act4_fort")
            own["name"], own["tileMaskFilename"] = "mxl2012_act4_fort", "data/hd/env/tilemasks/mxl2012_act4_fort_masks.json"
            p = Path(td) / "hd/env/biome/mxl2012_act4_fort.json"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps(own))
            map_tint.apply(Path(td), CHARISMATIC, "mxl2012_act4_fort", reader(D2R))
            b = json.loads((Path(td) / "hd/env/biome/mxl2012_tint_charismatic.json").read_text())
            self.assertEqual(b["tileMaskFilename"], "data/hd/env/tilemasks/mxl2012_act4_fort_masks.json")

    def test_apply_leaves_other_maps_alone(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(map_tint.apply(Path(td), "act3/jungle/dungrm6a.ds1", "act3_jungle", reader({})), "act3_jungle")
            self.assertEqual(list(Path(td).iterdir()), [])

    def test_base_biome_of_a_scene_tinted_before(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(map_tint.base_biome(Path(td), "act4_fort", "act4_fort"), "act4_fort")
            self.assertEqual(map_tint.base_biome(Path(td), "mxl2012_tint_charismatic", "act4_fort"), "act4_fort")
            p = Path(td) / "hd/env/biome/mxl2012_act4_fort.json"
            p.parent.mkdir(parents=True)
            p.write_text("{}")
            self.assertEqual(map_tint.base_biome(Path(td), "mxl2012_tint_charismatic", "act4_fort"), "mxl2012_act4_fort")

    def test_walls_build_twice_gives_the_same_light(self):
        lib = walls_hd.Library()
        with tempfile.TemporaryDirectory() as td:
            for _ in range(2):
                walls_hd.build(Path(td), [{"map": CHARISMATIC, "biome": "act4_fort"}], {CHARISMATIC: {}}, lib, read=reader(D2R))
            v = json.loads((Path(td) / "hd/env/vis/mxl2012_tint_charismatic.json").read_text())
            self.assertAlmostEqual(v["entities"][1]["components"][0]["power"], 25.0 * map_tint.TINTS[CHARISMATIC].power)

    def test_walls_build_names_the_tinted_biome(self):
        lib = walls_hd.Library()
        with tempfile.TemporaryDirectory() as td:
            st = walls_hd.build(Path(td), [{"map": CHARISMATIC, "biome": "act4_fort"}], {CHARISMATIC: {}}, lib, read=reader(D2R))
            scene = json.loads((Path(td) / "hd/env/preset/expansion/zakarum/charismatic.json").read_text())
            self.assertEqual(scene["biomeFilename"], "data/hd/env/biome/mxl2012_tint_charismatic.json")
            self.assertEqual(st[CHARISMATIC]["biome"], "mxl2012_tint_charismatic")


class Measure(unittest.TestCase):
    PAL_A = [(i, i, i) for i in range(256)]
    PAL_B = [(255 - i, 255 - i, 255 - i) for i in range(256)]

    def test_same_colour_under_other_index_is_no_change(self):
        new = {(0, 1, 2): [(0, 0, 10), (1, 0, 20)]}
        old = {(0, 1, 2): [(0, 0, 245), (1, 0, 235), (2, 0, 9)]}     # PAL_B: 245 -> 10, 235 -> 20; one pixel only the donor has
        r = map_tint.compare(new, old, self.PAL_A, self.PAL_B, shared=frozenset({10})).row()
        self.assertEqual((r["pixels"], r["mean_dist"], r["far"]), (2, 0.0, 0.0))
        self.assertEqual(r["moved"], 0.5)
        self.assertEqual(r["shared"], 0.5)

    def test_far_pixels_and_brightness(self):
        r = map_tint.compare({(0, 0, 0): [(0, 0, 100)]}, {(0, 0, 0): [(0, 0, 50)]}, self.PAL_A, self.PAL_A).row()
        self.assertEqual(r["far"], 1.0)
        self.assertGreater(r["dval"], 0.19)
        self.assertEqual(r["dhue"], 0.0)                               # grey: no hue counted

    def test_shared_entries(self):
        a = [(i, 0, 0) for i in range(256)]
        b = list(a)
        b[7] = (1, 2, 3)
        self.assertEqual(map_tint.shared_entries([a, b]), frozenset(range(1, 256)) - {7})

    def test_cells_per_file_resolves_in_level_type_order(self):
        Tile = collections.namedtuple("Tile", "key")

        class Ds:
            def wall_layers(self):
                return [([(2 << 20) | (3 << 8), 0], [1, 0])]

            def floor_layers(self):
                return [[(2 << 20) | (3 << 8), 5 << 8]]

        tiles = {"a.dt1": [Tile((1, 2, 3))], "b.dt1": [Tile((1, 2, 3)), Tile((0, 2, 3)), Tile((0, 0, 5))]}
        self.assertEqual(map_tint.cells_per_file(Ds(), ["a.dt1", "b.dt1"], tiles.get), collections.Counter({"a.dt1": 1, "b.dt1": 2}))

    def test_act_of_and_map_name(self):
        self.assertEqual((map_tint.act_of("act3/kurast/walls.dt1"), map_tint.act_of("expansion/town/ground.dt1")), (3, 5))
        self.assertEqual(map_tint.map_name(CHARISMATIC), "charismatic")
        self.assertTrue(maps_hd.BIOME % "x" == map_tint.BIOME % "x")


if __name__ == "__main__":
    unittest.main()
