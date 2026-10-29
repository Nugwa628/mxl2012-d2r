"""Unit tests of the map tools (tools/dt1.py, ds1_remap.py, maps_hd.py) on synthetic .ds1 / .dt1 bytes: no game files.

  py -3 -I -m unittest discover -s tools/tests -p "test_maps.py" -v
"""
import json
import struct
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import ds1_remap  # noqa: E402
import dt1  # noqa: E402
import maps_hd  # noqa: E402


def cell(style, seq):
    return (style << 20) | (seq << 8)


def make_ds1(w, h, act=0, walls=None, floors=None, objects=(), version=18, nfiles=1):
    """walls: list of (cells, orient) per wall layer; floors: list of cells; cells = list of w*h dwords."""
    n = w * h
    walls = walls if walls is not None else [([0] * n, [0] * n)]
    floors = floors if floors is not None else [[0] * n]
    out = struct.pack("<iiii", version, w - 1, h - 1, act) + struct.pack("<i", 0)      # tag_type 0
    out += struct.pack("<i", nfiles) + b"".join(b"x%d.dt1\0" % i for i in range(nfiles))
    out += struct.pack("<ii", len(walls), len(floors))
    for wc, oc in walls:
        out += struct.pack("<%dI" % n, *wc) + struct.pack("<%dI" % n, *oc)
    for fc in floors:
        out += struct.pack("<%dI" % n, *fc)
    out += struct.pack("<%dI" % n, *([0] * n))                                           # shadow
    out += struct.pack("<i", len(objects))
    for o in objects:
        out += struct.pack("<5i", *o)
    return out


def make_dt1(tiles, junk=b"\0"):
    """tiles: [(orientation, main, sub, width, height, pixels)]; `junk` fills the unused header bytes 65-71 and 84-95."""
    head = struct.pack("<ii", 7, 6).ljust(0x10C, b"\0") + struct.pack("<ii", len(tiles), 0x114)
    table_at = 0x114
    data_at = table_at + 96 * len(tiles)
    table, blob = b"", b""
    for o, m, s, wd, ht, px in tiles:
        hdr = bytearray(96)
        struct.pack_into("<ii", hdr, 8, ht, wd)
        struct.pack_into("<iii", hdr, 20, o, m, s)
        hdr[65:72] = (junk * 7)[:7]
        struct.pack_into("<ii", hdr, 72, data_at + len(blob), len(px))
        hdr[84:96] = (junk * 12)[:12]
        table += bytes(hdr)
        blob += px
    return head + table + blob


class FakeIdMap:
    """The part of idmap.IdMap that ds1_remap.Maps.from_idmap reads."""

    def __init__(self, **ids):
        self.spaces = {e: SimpleNamespace(ids=(lambda d=d: d)) for e, d in ids.items()}


class Dt1Test(unittest.TestCase):
    def test_parse_keys_sizes_and_digest(self):
        ts = dt1.parse(make_dt1([(0, 1, 2, 160, 80, b"abc"), (1, 3, 0, 32, 64, b"zz")]))
        self.assertEqual([t.key for t in ts], [(0, 1, 2), (1, 3, 0)])
        self.assertEqual((ts[0].width, ts[0].height), (160, 80))
        self.assertEqual(len(ts[0].digest), 20)
        self.assertNotEqual(ts[0].digest, ts[1].digest)

    def test_meta_ignores_unused_header_bytes_and_pixels(self):
        a = dt1.parse(make_dt1([(0, 1, 2, 8, 8, b"abc")], junk=b"\0"))[0]
        b = dt1.parse(make_dt1([(0, 1, 2, 8, 8, b"xyz")], junk=b"\x7f"))[0]
        self.assertEqual(a.meta, b.meta)
        self.assertNotEqual(a.digest, b.digest)

    def test_rejects_other_versions_and_truncation(self):
        bad = bytearray(make_dt1([(0, 1, 2, 8, 8, b"abc")]))
        bad[0] = 4
        with self.assertRaises(ValueError):
            dt1.parse(bytes(bad))
        with self.assertRaises(ValueError):
            dt1.parse(make_dt1([(0, 1, 2, 8, 8, b"abc")])[:0x120])
        with self.assertRaises(ValueError):
            dt1.parse(b"\0" * 8)


class Ds1Test(unittest.TestCase):
    def test_parse_and_pack_roundtrip(self):
        n = 6
        data = make_ds1(3, 2, act=2, walls=[([cell(2, 1)] * n, [3] * n)], floors=[[cell(1, 0)] * n],
                        objects=[(1, 7, 4, 5, 0), (2, 16, 1, 1, 0)])
        d = ds1_remap.Ds1(data)
        self.assertEqual((d.version, d.width, d.height, d.act, d.walls, d.floors), (18, 3, 2, 2, 1, 1))
        self.assertEqual(d.objects, [[1, 7, 4, 5, 0], [2, 16, 1, 1, 0]])
        self.assertEqual(ds1_remap.cell_key(cell(2, 1)), (2, 1))
        self.assertEqual(d.wall_layers()[0][0], (cell(2, 1),) * n)
        self.assertEqual(d.floor_layers()[0], (cell(1, 0),) * n)
        self.assertEqual(d.pack(), data)

    def test_truncated_object_block_is_an_error(self):
        data = make_ds1(1, 1, objects=[(1, 7, 0, 0, 0)])
        with self.assertRaises(ValueError):
            ds1_remap.Ds1(data[:-8])

    def test_remap_renumbers_drops_and_counts(self):
        ids = {970: 1067, 980: 980}
        maps = ds1_remap.Maps(ids.get, {1: 5}, {1: {16, 17}})
        data = make_ds1(1, 1, act=0, objects=[
            (1, 3, 0, 0, 0),      # below the act's MonPreset count: a preset row, kept
            (1, 970, 1, 0, 0),    # raw MonStats row: renumbered
            (1, 980, 2, 0, 0),    # raw row that keeps its id
            (1, -1, 3, 0, 0),     # negative: dropped
            (1, 99999, 4, 0, 0),  # no such row in the ID map: dropped
            (2, 16, 5, 0, 0),
            (2, 999, 6, 0, 0),    # not an ObjPreset slot: counted, kept
        ])
        stats = Counter()
        out = ds1_remap.remap_bytes(data, maps, stats)
        self.assertEqual(dict(stats), {"type1_renumbered": 1, "type1_dropped": 2, "type2_unresolved": 1})
        self.assertEqual([o[:2] for o in ds1_remap.Ds1(out).objects],
                         [[1, 3], [1, 1067], [1, 980], [2, 16], [2, 999]])

    def test_unchanged_file_is_the_same_object(self):
        maps = ds1_remap.Maps({5: 5}.get, {1: 0})
        data = make_ds1(1, 1, objects=[(1, 5, 0, 0, 0)])
        self.assertIs(ds1_remap.remap_bytes(data, maps, Counter()), data)

    def test_act_selects_the_preset_count(self):
        maps = ds1_remap.Maps({50: 77}.get, {1: 10, 2: 100})
        self.assertEqual(maps.monster_new(0, 50), 77)       # act 1: 50 is a raw row
        self.assertEqual(maps.monster_new(1, 50), 50)       # act 2: 50 is a preset row

    def test_remap_tree(self):
        maps = ds1_remap.Maps({970: 1067}.get, {1: 5})
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a" / "x.ds1"
            p.parent.mkdir()
            p.write_bytes(make_ds1(1, 1, objects=[(1, 970, 0, 0, 0)]))
            self.assertEqual(ds1_remap.remap_tree(Path(d), maps, write=False)["files_changed"], 1)
            self.assertEqual(ds1_remap.Ds1(p.read_bytes()).objects[0][1], 970)
            s = ds1_remap.remap_tree(Path(d), maps)
            self.assertEqual((s["files"], s["files_changed"], s["type1_renumbered"]), (1, 1, 1))
            self.assertEqual(ds1_remap.Ds1(p.read_bytes()).objects[0][1], 1067)


class IdMapInterfaceTest(unittest.TestCase):
    def test_from_idmap_uses_the_monstats_space(self):
        maps = ds1_remap.Maps.from_idmap(FakeIdMap(monstats={410: 410, 1000: 1097}, objects={0: 0, 1: 1},
                                                   superuniques={0: 0, 42: 42, 43: 43, 44: 44}), {1: 59})
        self.assertEqual(maps.monster_new(0, 1000), 1097)
        self.assertEqual(maps.monster_new(0, 12), 12)
        self.assertIsNone(maps.monster_new(0, 1001))
        self.assertEqual(maps.moved_objects(), [])
        self.assertEqual(maps.shifted_superuniques(), [(43, 43), (44, 44)])

    def test_moved_objects_are_reported(self):
        maps = ds1_remap.Maps.from_idmap(FakeIdMap(monstats={}, objects={0: 0, 5: 6}), {})
        self.assertEqual(maps.moved_objects(), [(5, 6)])

    def test_load_reads_idmap_json_and_tables(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "idmap.json").write_text(json.dumps({"spaces": {"monstats": {"rows": [{"row": 7, "id": 9}]}}}), "utf-8")
            (d / "monpreset.txt").write_text("Act\tPlace\n1\ta\n1\tb\n2\tc\n", "utf-8")
            (d / "objpreset.txt").write_text("Act\tIndex\tObjectClass\n1\t0\tx\n1\t1\ty\n2\t5\tz\n", "utf-8")
            maps = ds1_remap.Maps.load(d / "idmap.json", d, d)
            self.assertEqual(maps.presets, {1: 2, 2: 1})
            self.assertEqual(maps.monster_new(0, 7), 9)
            self.assertTrue(maps.object_valid(0, 1))
            self.assertFalse(maps.object_valid(0, 5))
            self.assertTrue(maps.object_valid(1, 5))

    def test_object_slots_of_reads_the_base_bank_and_is_none_without_it(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertIsNone(ds1_remap.object_slots_of(d))
            (d / "base").mkdir()
            (d / "base" / "objpreset.txt").write_text("Act\tIndex\n3\t4\n", "utf-8")
            self.assertEqual(ds1_remap.object_slots_of(d), {3: {4}})


class TileSetTest(unittest.TestCase):
    STOCK = [(0, 1, 0, 160, 80, b"f"), (1, 2, 0, 32, 64, b"w"), (1, 2, 1, 32, 64, b"w2")]

    def tiles(self, spec, **kw):
        return dt1.parse(make_dt1(spec, **kw))

    def test_donor_is_the_most_similar_stock_set_and_class_copy(self):
        stock = {"act1/cathedrl/floor.dt1": self.tiles(self.STOCK),
                 "act2/ruin/floor.dt1": self.tiles([(0, 9, 9, 160, 80, b"q")])}
        new = {"expansion/x/floor.dt1": self.tiles(self.STOCK, junk=b"\x05")}      # retextured: same keys, other junk bytes
        d = maps_hd.donor_table(new, stock)["expansion/x/floor.dt1"]
        self.assertEqual(d["donor"], "act1/cathedrl/floor.dt1")
        self.assertEqual((d["jaccard"], d["tiles"], d["meta_same"]), (1.0, 3, 3))
        self.assertEqual(maps_hd.donor_class(d), "copy")

    def test_donor_class_levels(self):
        self.assertEqual(maps_hd.donor_class({"jaccard": 1.0, "meta_same": 0, "tiles": 10}), "copy-layout")
        self.assertEqual(maps_hd.donor_class({"jaccard": 0.9, "meta_same": 10, "tiles": 10}), "similar")
        self.assertEqual(maps_hd.donor_class({"jaccard": 0.3, "meta_same": 10, "tiles": 10}), "none")

    def test_size_difference_lowers_the_match(self):
        stock = {"s.dt1": self.tiles(self.STOCK)}
        new = {"n.dt1": self.tiles([(0, 1, 0, 160, 80, b"f"), (1, 2, 0, 64, 64, b"w"), (1, 2, 1, 32, 64, b"w2")])}
        self.assertLess(maps_hd.donor_table(new, stock)["n.dt1"]["jaccard"], 0.999)

    def test_tile_index_and_resolve(self):
        files = [(1, "a.dt1"), (2, "b.dt1")]
        tiles = {"a.dt1": self.tiles([(0, 1, 0, 8, 8, b"f"), (1, 2, 0, 8, 8, b"w")]),
                 "b.dt1": self.tiles([(0, 1, 0, 8, 8, b"g"), (1, 5, 0, 8, 8, b"v")])}
        floor, wall = maps_hd.tile_index(files, tiles.get)
        self.assertEqual(floor[(1, 0)], "a.dt1")       # the first file in order wins
        self.assertEqual(wall[(5, 0)], "b.dt1")
        ds = ds1_remap.Ds1(make_ds1(2, 1, walls=[([cell(2, 0), cell(7, 7)], [1, 1])], floors=[[cell(1, 0), 0]]))
        res = maps_hd.resolve_tiles(ds, floor, wall)
        self.assertEqual((dict(res["floor"]), dict(res["wall"])), ({"a.dt1": 1}, {"a.dt1": 1}))
        self.assertEqual((res["floor_missing"], res["wall_missing"]), (0, 1))


class SceneTest(unittest.TestCase):
    BIOMES = {"act1_cathedral", "act1_barracks", "act1_outdoors", "act2_ruin"}

    def test_biome_for_dir(self):
        self.assertEqual(maps_hd.biome_for_dir("act1/cathedrl", self.BIOMES), "act1_cathedral")
        self.assertEqual(maps_hd.biome_for_dir("act2/ruin", self.BIOMES), "act2_ruin")
        self.assertIsNone(maps_hd.biome_for_dir("act1/river", self.BIOMES))        # shared set: no vote
        self.assertIsNone(maps_hd.biome_for_dir("act9/nothing", self.BIOMES))
        self.assertFalse(any("/" in b for b in maps_hd.BIOME_BY_LEVELTYPE.values()))
        self.assertNotIn("act1/barracks/warp", maps_hd.SHARED_TILEDIRS)

    def test_vote_goes_through_the_stand_in_and_falls_back_to_the_level_type(self):
        res = {"floor": Counter({"expansion/x/f.dt1": 5}), "wall": Counter({"act2/ruin/w.dt1": 2}),
               "floor_missing": 0, "wall_missing": 0}
        donor_of = lambda p: "act1/cathedrl/f.dt1" if p.startswith("expansion") else p   # noqa: E731
        b, how, alt = maps_hd.vote_biome(res, donor_of, self.BIOMES, [1])
        self.assertEqual((b, alt), ("act1_cathedral", "act1_outdoors"))
        self.assertIn("act1/cathedrl 5", how)
        empty = {"floor": Counter(), "wall": Counter(), "floor_missing": 0, "wall_missing": 0}
        self.assertEqual(maps_hd.vote_biome(empty, donor_of, self.BIOMES, [7])[:2][0], "act1_barracks")
        self.assertEqual(maps_hd.vote_biome(empty, donor_of, self.BIOMES, [])[0], maps_hd.LEVELTYPE_FALLBACK)

    def test_floor_cells_vote_before_walls(self):
        # cypherpunk: walls of Kurast, floors of Docktown -> the floor's biome (Kurast's painted its floors as grass)
        res = {"floor": Counter({"act2/ruin/f.dt1": 5}), "wall": Counter({"act1/cathedrl/w.dt1": 50}),
               "floor_missing": 0, "wall_missing": 0}
        b, how, _alt = maps_hd.vote_biome(res, lambda p: p, self.BIOMES, [1])
        self.assertEqual(b, "act2_ruin")
        self.assertTrue(how.startswith("floor cells"))
        res["floor"] = Counter({"act1/river/f.dt1": 5})           # floors only of a shared set: walls decide
        b, how, _alt = maps_hd.vote_biome(res, lambda p: p, self.BIOMES, [1])
        self.assertEqual((b, how.split(":")[0]), ("act1_cathedral", "floor+wall cells"))

    def test_shared_dirs_do_not_vote(self):
        res = {"floor": Counter({"act1/river/f.dt1": 50}), "wall": Counter({"act1/cathedrl/w.dt1": 1}),
               "floor_missing": 0, "wall_missing": 0}
        self.assertEqual(maps_hd.vote_biome(res, lambda p: p, self.BIOMES, [1])[0], "act1_cathedral")

    def test_scene_json_is_the_empty_preset_shape(self):
        s = json.loads(maps_hd.scene_json("act1_cathedral"))
        self.assertEqual(s["biomeFilename"], "data/hd/env/biome/act1_cathedral.json")
        self.assertEqual(s["entities"], [])
        self.assertEqual(s["dependencies"]["json"], [{"path": s["biomeFilename"]}])

    def test_selected_files_follow_the_mask_and_skip_empty_slots(self):
        row = {"File 1": "A\\One.dt1", "File 2": "0", "File 3": "b.dt1", "File 4": "c.dt1"}
        self.assertEqual(maps_hd.selected_files(row, 0b1111), [(1, "a/one.dt1"), (3, "b.dt1"), (4, "c.dt1")])
        self.assertEqual(maps_hd.selected_files(row, 0b0100), [(3, "b.dt1")])
        self.assertEqual(maps_hd.selected_files(row, 0), [])


class DiffTest(unittest.TestCase):
    def test_same_edited_and_resized(self):
        base = make_ds1(2, 2, floors=[[cell(1, 0)] * 4], objects=[(1, 1, 0, 0, 0)])
        self.assertEqual(maps_hd.ds1_diff(base, base)["cls"], "tiles same")
        edited = make_ds1(2, 2, floors=[[cell(1, 0), cell(1, 1), cell(1, 0), cell(1, 0)]],
                          objects=[(1, 1, 0, 0, 0), (2, 3, 1, 1, 0)])
        d = maps_hd.ds1_diff(edited, base)
        self.assertEqual(d["cls"], "tiles changed")
        self.assertEqual((d["objects_added"], d["objects_removed"]), (1, 0))
        # one changed floor cell out of (wall style + floor) layers x 4 cells
        self.assertAlmostEqual(d["visual_changed"], 1 / 8)
        big = make_ds1(3, 2, floors=[[0] * 6])
        self.assertEqual(maps_hd.ds1_diff(big, base)["cls"], "size changed")

    def test_layer_count_change(self):
        base = make_ds1(2, 2, floors=[[cell(1, 0)] * 4])
        two = make_ds1(2, 2, floors=[[cell(1, 0)] * 4, [0] * 4])
        self.assertEqual(maps_hd.ds1_diff(two, base)["cls"], "layers differ")


STOCK_TILES = [(0, 1, 0, 160, 80, b"f"), (1, 2, 0, 32, 64, b"w")]


def mini_inputs(id_maps=None):
    """Three levels: 1 uses a stock and a new .dt1 (map a: new map resolved by stock tiles; map c: unchanged D2R map),
    2 only a new .dt1 (map b: needs custom art); map e is a D2R map the mod edited a lot."""
    cells_a = make_ds1(2, 1, walls=[([cell(2, 0), 0], [1, 0])], floors=[[cell(1, 0), cell(1, 0)]],
                       objects=[(1, 970, 0, 0, 0), (2, 16, 1, 1, 0)])
    cells_c = make_ds1(1, 1, floors=[[cell(1, 0)]])
    e_d2r = make_ds1(2, 1, floors=[[cell(1, 0), cell(1, 0)]])
    e_mod = make_ds1(2, 1, walls=[([cell(2, 0), cell(2, 0)], [1, 1])], floors=[[0, 0]])
    mod = maps_hd.TileStore({
        "act1/cathedrl/a.ds1": cells_a, "act1/cathedrl/b.ds1": cells_a, "act1/cathedrl/c.ds1": cells_c,
        "act1/cathedrl/e.ds1": e_mod, "expansion/x/floor.dt1": make_dt1(STOCK_TILES, junk=b"\x03")})
    d2r = maps_hd.TileStore({
        "act1/cathedrl/c.ds1": cells_c, "act1/cathedrl/e.ds1": e_d2r, "act1/cathedrl/floor.dt1": make_dt1(STOCK_TILES)})
    types = [{"Id": "1", "Name": "Cathedral", "File 1": "act1\\cathedrl\\floor.dt1", "File 2": "expansion\\x\\floor.dt1"},
             {"Id": "2", "Name": "Cathedral2", "File 1": "expansion\\x\\floor.dt1"}]
    levels = [{"Id": "1", "Name": "L1", "LevelType": "1", "Act": "0", "DrlgType": "2"},
              {"Id": "2", "Name": "L2", "LevelType": "2", "Act": "0", "DrlgType": "2"}]
    prest = [{"Name": "pa", "Def": "0", "LevelId": "1", "Dt1Mask": "3", "File1": "act1\\cathedrl\\a.ds1"},
             {"Name": "pb", "Def": "1", "LevelId": "2", "Dt1Mask": "1", "File1": "act1\\cathedrl\\b.ds1"},
             {"Name": "pc", "Def": "2", "LevelId": "1", "Dt1Mask": "3", "File1": "act1\\cathedrl\\c.ds1"},
             {"Name": "pe", "Def": "3", "LevelId": "1", "Dt1Mask": "3", "File1": "act1\\cathedrl\\e.ds1"}]
    dprest = [{"Name": "pc", "LevelId": "1", "File1": "act1\\cathedrl\\c.ds1"}]
    names = [""] * 1100
    names[970] = "quest_laser"
    return maps_hd.Inputs(levels, prest, types, mod, levels, dprest, d2r, {"act1/cathedrl/c", "act1/cathedrl/e"},
                          {"act1_cathedral", "act1_outdoors"}, names, {1: 5}, {1: {16: "chest"}}, {"chest": 20}, 574, (),
                          id_maps)


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.id_maps = ds1_remap.Maps({970: 1067}.get, {1: 5}, {1: {16}})
        self.inp = mini_inputs(self.id_maps)
        self.maps, self.dt1s, self.levels = maps_hd.plan(self.inp)
        self.by = {e["map"][:-4].rsplit("/", 1)[1]: e for e in self.maps}

    def test_actions(self):
        self.assertEqual(self.by["c"]["action"], "D2R scene")
        self.assertEqual(self.by["c"]["kind"], "D2R map, unchanged")
        self.assertEqual(self.by["e"]["kind"], "D2R map, edited by Median")
        self.assertEqual(self.by["e"]["action"], "minimal scene")          # every wall/floor cell changed
        for k in ("a", "b"):
            self.assertEqual(self.by[k]["kind"], "Median map")
            self.assertEqual((self.by[k]["action"], self.by[k]["biome"]), ("minimal scene", "act1_cathedral"))

    def test_art_class(self):
        self.assertEqual(self.by["a"]["art_class"], "generate")    # resolves through the stock .dt1 listed first
        self.assertEqual(self.by["b"]["art_class"], "custom")      # only the retextured .dt1
        self.assertEqual(self.by["b"]["tiles"]["new_dt1_used"], ["expansion/x/floor.dt1"])

    def test_dt1_stand_in(self):
        (d,) = self.dt1s
        self.assertEqual((d["path"], d["donor"], d["cls"]), ("expansion/x/floor.dt1", "act1/cathedrl/floor.dt1", "copy"))
        self.assertEqual(d["maps"], ["act1/cathedrl/b.ds1"])
        self.assertEqual(d["level_types"], ["Cathedral", "Cathedral2"])
        self.assertEqual(d["biome"], "act1_cathedral")

    def test_ids_go_through_the_id_map(self):
        a = self.by["a"]
        self.assertEqual(a["monster_raw_rows"], [970])
        self.assertEqual(a["monster_raw_new"], [1067])
        self.assertEqual(a["monster_raw_names"], ["quest_laser"])
        self.assertEqual(a["remap"], {"type1_renumbered": 1})
        self.assertEqual(a["objects"], 1)
        self.assertEqual(a["objects_unresolved"], 0)
        rows = maps_hd.monster_rows(self.maps)
        self.assertEqual(rows[970]["new_id"], 1067)
        self.assertEqual(sorted(rows[970]["maps"]), ["act1/cathedrl/a.ds1", "act1/cathedrl/b.ds1"])

    def test_audit_is_clean_and_flags_id_map_problems(self):
        self.assertEqual([f for f in maps_hd.audit(self.inp, self.maps) if f[0] == "PROBLEM"], [])
        bad = ds1_remap.Maps({}.get, {1: 5}, {1: {16}}, object_ids={3: 4})
        self.inp.id_maps = bad
        maps, _d, _l = maps_hd.plan(self.inp)
        problems = [t for s, t in maps_hd.audit(self.inp, maps) if s == "PROBLEM"]
        self.assertTrue(any("moves Objects row 3" in t for t in problems))
        self.assertTrue(any("raw monster rows [970]" in t for t in problems))

    def test_build_writes_scenes_only_for_minimal_ones(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(maps_hd.build(Path(d), self.maps), 3)
            f = Path(d) / "hd" / "env" / "preset" / "act1" / "cathedrl" / "a.json"
            self.assertEqual(json.loads(f.read_text("utf-8"))["biomeFilename"], "data/hd/env/biome/act1_cathedral.json")
            self.assertFalse((Path(d) / "hd" / "env" / "preset" / "act1" / "cathedrl" / "c.json").exists())

    def fake_d2r(self):
        biome = {"name": "act1_cathedral", "tileMaskFilename": "data/hd/env/tilemasks/tile_masks.json",
                 "dependencies": {"json": [{"path": "data/hd/env/tilemasks/tile_masks.json"}, {"path": "data/hd/env/vis/v.json"}]}}
        entry = [{"type": "PathMaskEntry", "style": 0, "sequence": 1, "variants": [{"mask_type": 1, "weight": 1.0}]}]
        mask = {"type": "TileMaskData", "path_masks": {"data\\global\\tiles\\Act1\\Cathedrl\\Floor.dt1": entry},
                "wall_masks": {}, "filters": {"data\\global\\tiles\\act1\\cathedrl\\floor.dt1": False}}
        files = {"data/hd/env/biome/act1_cathedral.json": biome, "data/hd/env/tilemasks/tile_masks.json": mask}
        asked = []

        def read(rel):
            asked.append(rel)
            return json.loads(json.dumps(files[rel]))
        return read, asked, entry

    def test_floor_biome_gives_new_floors_their_donors_mask(self):
        self.assertEqual(maps_hd.native_floors(self.by["b"], self.dt1s), [("expansion/x/floor.dt1", "act1/cathedrl/floor.dt1")])
        self.assertEqual(maps_hd.native_floors(self.by["a"], self.dt1s), [])
        read, asked, entry = self.fake_d2r()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(maps_hd.build(Path(d), self.maps, self.dt1s, read), 3)
            env = Path(d) / "hd" / "env"
            b = json.loads((env / "preset" / "act1" / "cathedrl" / "b.json").read_text("utf-8"))
            a = json.loads((env / "preset" / "act1" / "cathedrl" / "a.json").read_text("utf-8"))
            self.assertEqual(b["biomeFilename"], "data/hd/env/biome/mxl2012_act1_cathedral.json")
            self.assertEqual(a["biomeFilename"], "data/hd/env/biome/act1_cathedral.json")    # no new floor: stock biome
            self.assertEqual(maps_hd.scene_biome(Path(d), "act1/cathedrl/b.ds1"), "mxl2012_act1_cathedral")
            self.assertIsNone(maps_hd.scene_biome(Path(d), "act1/cathedrl/zz.ds1"))
            biome = json.loads((env / "biome" / "mxl2012_act1_cathedral.json").read_text("utf-8"))
            self.assertEqual(biome["tileMaskFilename"], "data/hd/env/tilemasks/mxl2012_act1_cathedral_masks.json")
            self.assertEqual(biome["dependencies"]["json"][0]["path"], "data/hd/env/tilemasks/mxl2012_act1_cathedral_masks.json")
            mask = json.loads((env / "tilemasks" / "mxl2012_act1_cathedral_masks.json").read_text("utf-8"))
            self.assertEqual(mask["path_masks"]["data/global/tiles/expansion/x/floor.dt1"], entry)
            self.assertIn("data\\global\\tiles\\Act1\\Cathedrl\\Floor.dt1", mask["path_masks"])   # D2R's own kept
            self.assertIs(mask["filters"]["data/global/tiles/expansion/x/floor.dt1"], False)
        self.assertEqual(asked, ["data/hd/env/biome/act1_cathedral.json", "data/hd/env/tilemasks/tile_masks.json"])

    def test_no_copy_when_the_donor_has_no_mask_entry(self):
        mask = {"path_masks": {"data/global/tiles/act1/other/f.dt1": []}, "wall_masks": {}, "filters": {}}
        self.assertIsNone(maps_hd.floor_biome({"tileMaskFilename": "m"}, mask, [("expansion/x/floor.dt1", "act1/cathedrl/floor.dt1")], "n"))
        self.assertEqual(mask["path_masks"], {"data/global/tiles/act1/other/f.dt1": []})   # D2R's mask untouched

    def test_tables_and_docs_splice(self):
        text = maps_hd.md_tables(self.maps, self.dt1s, self.levels, maps_hd.audit(self.inp, self.maps),
                                 maps_hd.monster_rows(self.maps))
        for needle in ("act1/cathedrl/a.ds1", "expansion/x/floor.dt1", "| 970 | quest_laser | 1067 |", "D2R's stock walls in HD"):
            self.assertIn(needle, text)
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "maps-hd.md"
            f.write_text("intro\n%s\nold\n%s\noutro\n" % (maps_hd.DOCS_BEGIN, maps_hd.DOCS_END), "utf-8")
            self.assertTrue(maps_hd.update_docs(f, text))
            self.assertFalse(maps_hd.update_docs(f, text))             # idempotent
            out = f.read_text("utf-8")
            self.assertTrue(out.startswith("intro\n") and out.endswith("outro\n") and "old" not in out)
            f.write_text("no markers", "utf-8")
            with self.assertRaises(SystemExit):
                maps_hd.update_docs(f, text)

    def test_biome_override_is_applied_to_inarius_only(self):
        self.assertIn("act1/cathedrl/inarius", maps_hd.BIOME_OVERRIDE)
        self.assertEqual(maps_hd.BIOME_OVERRIDE["act1/cathedrl/inarius"][0], "act1_cathedral")


if __name__ == "__main__":
    unittest.main()
