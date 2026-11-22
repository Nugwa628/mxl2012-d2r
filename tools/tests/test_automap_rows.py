"""Tests of tools/automap_render.py, automap_rows.py, automap_art.py and automap_void.py (lanes hdmaps2, automapall):
synthetic tables and files; the Real case needs the D2R and Median extracts and is skipped without them.

  python -m unittest tests.test_automap_rows
"""
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401
import automap_render as ar  # noqa: E402
import automap_rows  # noqa: E402
import automap_art  # noqa: E402
import automap_void  # noqa: E402
import dt1  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_maps import make_dt1  # noqa: E402

HEAD = "LevelName\tTileName\tStyle\tStartSequence\tEndSequence\t*Type1\tCel1\t*Type2\tCel2\t*Type3\tCel3\t*Type4\tCel4"


def keys_of(tiles):
    return [(t.orientation, t.main, t.sub) for t in tiles]


class Lookup(unittest.TestCase):
    def test_exact_sequence_first_then_any(self):
        rows = [("wr", 0, -1, -1, [240]), ("wr", 0, 2, 2, [253]), ("wl", -1, -1, -1, [241])]
        self.assertEqual(ar.lookup(rows, "wr", 0, 2), [253])
        self.assertEqual(ar.lookup(rows, "wr", 0, 5), [240])
        self.assertEqual(ar.lookup(rows, "wl", 31, 0), [241])         # style -1: any style
        self.assertIsNone(ar.lookup(rows, "wr", 31, 0))

    def test_level_type_name(self):
        self.assertEqual(ar.level_type_name("Act 2 - Tomb"), "2 Tomb")


class Write(unittest.TestCase):
    def test_appends_after_base_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            base, out = Path(d) / "base.txt", Path(d) / "out.txt"
            base.write_bytes((HEAD + "\r\n2 Tomb\twr\t0\t-1\t-1\tTmb_WR A\t240\t\t-1\t\t-1\t\t-1\r\n").encode())
            automap_rows.write(base, [("2 Tomb", "wl", 31, 0, 241)], out)
            text = out.read_bytes().decode()
            self.assertTrue(text.startswith(base.read_bytes().decode()))
            last = text.rstrip("\r\n").split("\r\n")[-1].split("\t")
            self.assertEqual(last[:7], ["2 Tomb", "wl", "31", "0", "0", "mxl wl", "241"])
            self.assertEqual(len(last), len(HEAD.split("\t")))
            rows = ar.read_rows(out, "2 Tomb")
            self.assertEqual(ar.lookup(rows, "wl", 31, 0), [241])


def write_automap(path, rows):
    path.write_text(HEAD + "\n" + "".join("%s\t%s\t%d\t-1\t-1\tx\t%s\n" % (lt, code, st, "\t\t".join(
        str(c) for c in (cels + [-1] * 4)[:4])) for lt, code, st, cels in rows), encoding="utf-8")


class Templates(unittest.TestCase):
    def test_most_used_ties_siblings_generic(self):
        full = [(automap_rows.GENERIC, c, 0, [100 + i]) for i, c in enumerate(automap_rows.WALL_CODES)]
        rows = full + [
            ("2 Tomb", "wl", 0, [241]), ("2 Tomb", "wl", 1, [241, 252]), ("2 Tomb", "wl", 2, [252]),   # 241 x2
            ("2 Tomb", "wld", 0, [247]), ("2 Tomb", "wld", 1, [241]),                                  # tie: first
            *[("2 Tomb", c, 0, [200 + i]) for i, c in enumerate(["wr", "wtlr", "wtr", "wbl", "wbr"])],  # no wtll, co
            ("5 Lava", "wl", 0, [1483])]                                                               # core missing
        with tempfile.TemporaryDirectory() as d:
            write_automap(Path(d) / "a.txt", rows)
            t = automap_rows.templates(Path(d) / "a.txt")
        self.assertEqual(t["2 Tomb"]["wl"], 241)
        self.assertEqual(t["2 Tomb"]["wld"], 247)
        self.assertEqual(t["2 Tomb"]["wtll"], t["2 Tomb"]["wtlr"])        # sibling
        self.assertEqual(t["2 Tomb"]["co"], t["2 Tomb"]["wbr"])
        self.assertEqual(t["2 Tomb"]["wre"], t["2 Tomb"]["wr"])           # wre -> wrd (none) -> wr
        self.assertEqual(t["5 Lava"], t[automap_rows.GENERIC])            # whole generic set
        self.assertEqual(set(t["2 Tomb"]), set(automap_rows.WALL_CODES))

    def test_bright_cels(self):
        tpl = {"2 Tomb": dict(zip(automap_rows.WALL_CODES, range(240, 252))),
               "9 Dim": {c: (20 if c in ("wtll", "wtlr") else 30 + i) for i, c in enumerate(automap_rows.WALL_CODES)}}
        free = [5, 6, 1100] + list(range(1176, 1200))
        b = automap_rows.bright_cels(["9 Dim", "2 Tomb"], tpl, free)
        self.assertEqual(b["2 Tomb"], automap_rows.PINNED["2 Tomb"])          # pinned first, whatever the order
        self.assertEqual(b["9 Dim"]["wtll"], b["9 Dim"]["wtlr"])              # one cel per template cel
        self.assertEqual(set(b["9 Dim"]), set(automap_rows.BRIGHT_ORDER))
        self.assertLessEqual(len(set(b["9 Dim"].values())), automap_rows.BRIGHT_MAX)
        self.assertFalse(set(b["9 Dim"].values()) & set(b["2 Tomb"].values()))
        self.assertTrue(all(c >= 1183 for c in b["9 Dim"].values()))         # from FIRST_BRIGHT up, past the pinned
        with self.assertRaises(SystemExit):
            automap_rows.bright_cels(["9 Dim"], tpl, [5, 6])

    def test_bright_cels_shared_per_act_and_gain(self):
        t = dict(zip(automap_rows.WALL_CODES, range(20, 32)))
        tpl = {"1 Crypt": t, "1 Cathedral": t, "3 Kurast": t}
        free = list(range(1176, 1240))
        b = automap_rows.bright_cels(["1 Crypt", "1 Cathedral", "3 Kurast"], tpl, free,
                                     {"1 Crypt": 1.6, "1 Cathedral": 1.6, "3 Kurast": 1.6})
        self.assertEqual(b["1 Crypt"], b["1 Cathedral"])             # same act, template and gain
        self.assertFalse(set(b["1 Crypt"].values()) & set(b["3 Kurast"].values()))   # another act's palette
        b2 = automap_rows.bright_cels(["1 Crypt", "1 Cathedral"], tpl, free, {"1 Crypt": 1.6, "1 Cathedral": 2.0})
        self.assertFalse(set(b2["1 Crypt"].values()) & set(b2["1 Cathedral"].values()))

    def test_gain(self):
        self.assertEqual(automap_rows.gain_of(0.207), automap_rows.GAIN_MAX)   # the Tomb: capped, as shipped
        self.assertEqual(automap_rows.gain_of(0.504), 1.6)
        self.assertEqual(automap_rows.gain_of(0.9), 1.0)

    def test_prest_type(self):
        types = ["None", "Act 2 - Desert", "Act 2 - Tomb", "Act 5 - Ice Caves", "Act 5 - Lava"]
        self.assertEqual(automap_rows.prest_type("Act 2 - Tomb NSEW", types), "Act 2 - Tomb")
        self.assertEqual(automap_rows.prest_type("Act 5 - Ice Prev W", types), "Act 5 - Ice Caves")
        self.assertEqual(automap_rows.prest_type("Act 2 - Desert Tomb 1", types), "Act 2 - Desert")
        self.assertIsNone(automap_rows.prest_type("Act 4 - Diablo Wing", types))

    def test_ice_caves_name(self):
        self.assertEqual(ar.level_type_name("Act 5 - Ice Caves"), "5 Ice")
        self.assertEqual(ar.level_type_name("Act 5 - Lava"), "5 Lava")
        self.assertEqual(automap_rows.act_of("5 Ice"), 5)


D2R_AM = ar.D2R / "global" / "excel" / "automap.txt"


@unittest.skipUnless(D2R_AM.is_file(), "needs D2R's extract")
class Real(unittest.TestCase):
    """On the game's own tables: the derivation keeps hdmaps2's Tomb cels, and the rows leave every stock level alone."""

    def test_tomb_template_as_shipped(self):
        self.assertEqual(automap_rows.templates(D2R_AM)["2 Tomb"], {
            "wr": 240, "wl": 241, "wbl": 242, "wtr": 243, "wtll": 244, "wtlr": 244, "wbr": 245, "wrd": 246, "wld": 247,
            "wre": 248, "wle": 249, "co": 250})

    def test_free_cels(self):
        free = automap_rows.free_cels(ar.D2R)
        self.assertGreaterEqual(len(free), 200)
        self.assertTrue(set(automap_rows.PINNED["2 Tomb"].values()) <= set(free))

    def test_rows_and_stock_levels(self):
        try:
            maps = automap_rows.map_list()
        except Exception as e:                                   # no Median extract
            self.skipTest("needs the Median extract: %s" % e)
        self.assertIn("expansion/ghetto/cypherpunk", maps)
        self.assertIn("act2/tomb/duriel", maps)
        rows, plan = automap_rows.new_rows(maps, D2R_AM)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "automap.txt"
            automap_rows.write(D2R_AM, rows, out)
            problems, nmaps, _n = automap_rows.check_stock(D2R_AM, out, list(plan["report"]))
        self.assertEqual(problems, [])
        self.assertGreater(nmaps, 100)
        for lt, code, st, sq, _cel in rows:                      # Median keys only, never a stock tile set's
            self.assertNotIn((code, st, sq), automap_rows.stock_keys(plan["types"][lt]["level_type"]))
        fauz = plan["maps"]["expansion/ghetto/cypherpunk"]["keys"]["2 Tomb"]
        self.assertEqual(len(fauz), 57)                          # Fauztinville as lane hdmaps2 shipped it
        self.assertEqual(plan["types"]["2 Tomb"]["bright"], automap_rows.PINNED["2 Tomb"])
        self.assertEqual(plan["types"]["2 Tomb"]["gain"], automap_rows.GAIN_MAX)
        for lt, t in plan["types"].items():                      # every changed type reads dimmer in legacy: bright
            self.assertLess(t["ink_ratio"], automap_rows.INK_TARGET)
            self.assertTrue(t["bright"] and 1.0 < t["gain"] <= automap_rows.GAIN_MAX, lt)
        self.assertEqual(plan["types"]["1 Crypt"]["bright"], plan["types"]["1 Cathedral"]["bright"])   # one act: shared
        cels = {c for t in plan["types"].values() for c in t["bright"].values()}
        self.assertLessEqual(len(cels), len(automap_rows.free_cels(ar.D2R)))
        stock = {c for r in automap_rows.automap_rows_all(D2R_AM) for c in r[3]}
        self.assertFalse(cels & stock)


class Art(unittest.TestCase):
    PLAN = {"types": {"2 Tomb": {"act": 2, "template": {"wr": 240, "wl": 241, "co": 250},
                                 "bright": {"wr": 1176, "wl": 1177, "co": 1182}}}}

    def test_bright_of(self):
        self.assertEqual(automap_art.bright_of(self.PLAN)["2 Tomb"]["wl"], (1177, 241))

    def test_check_flags_used_and_shared(self):
        with tempfile.TemporaryDirectory() as d:
            ex = Path(d) / "global" / "excel"
            ex.mkdir(parents=True)
            write_automap(ex / "automap.txt", [("1 Town", "wl", 0, [1177])])
            (ex / "objects.txt").write_text("Class\tAutoMap\nx\t0\n", encoding="latin-1")
            plan = {"types": dict(self.PLAN["types"])}
            plan["types"]["9 X"] = {"act": 2, "template": {"wr": 240}, "bright": {"wr": 1176}, "gain": 1.6}
            probs = automap_art.check(Path(d), plan)
        self.assertTrue(any("1177 is used" in p for p in probs))
        self.assertTrue(any("two different templates" in p for p in probs))

class ArtFiles(unittest.TestCase):
    def test_brighten_keeps_shape(self):
        pal = [(i, i // 4, i // 8) for i in range(256)]
        idx = np.array([[0, 40, 0], [60, 0, 60]], np.uint8)
        out = automap_art.brighten(idx, pal, 2.0)
        self.assertTrue(((out > 0) == (idx > 0)).all())
        self.assertEqual(int(out[0, 1]), 80)
        self.assertTrue(all(int(v) in automap_art.PAL_RANGE for v in out[out > 0]))

    def test_patch_dc6_one_frame(self):
        import dc6
        from rotw_stash_legacy import encode_frame
        frames = [(2, 2, 0, 0, encode_frame(np.array([[i + 1, 0], [0, i + 1]], np.uint8))) for i in range(3)]
        data = dc6.build_dc6(frames)
        new = (2, 2, 0, 0, encode_frame(np.array([[9, 9], [9, 9]], np.uint8)))
        self.assertEqual(dc6.parse_dc6(automap_art.patch_dc6(data, {1: new})), [frames[0], new, frames[2]])
        self.assertEqual(automap_art.patch_dc6(data, {}), data)
        self.assertEqual(automap_art._indices(2, 2, new[4]).tolist(), [[9, 9], [9, 9]])

    def test_patch_sprite_frame_only(self):
        import dc6
        fw, n, h = 4, 3, 2
        sw = (fw + 2) * n
        strip = (np.arange(sw * h * 4) % 251).astype(np.uint8).reshape(h, sw, 4)
        data = dc6.sprite_bytes(fw, sw, h, n, strip.tobytes())
        out = automap_art.patch_sprite(data, {1: np.full((h, fw, 4), 7, np.uint8)})
        self.assertEqual(len(out), len(data))
        self.assertTrue((automap_art.sprite_frame(out, 1) == 7).all())
        a = np.frombuffer(data, np.uint8, sw * h * 4, dc6.HEADER).reshape(h, sw, 4)
        b = np.frombuffer(out, np.uint8, sw * h * 4, dc6.HEADER).reshape(h, sw, 4)
        keep = np.ones(sw, bool)
        keep[fw + 2:fw + 2 + fw] = False
        self.assertTrue((a[:, keep] == b[:, keep]).all())
        self.assertEqual(out[:dc6.HEADER], data[:dc6.HEADER])


class Void(unittest.TestCase):
    def test_add_tile_copies_one(self):
        data = make_dt1([(4, 31, 0, 160, -96, b"AAAA"), (0, 4, 18, 160, -80, b"BBBBBB")])
        out = automap_void.add_tile(data, (4, 31, 0), 63)
        tiles, old = dt1.parse(out), dt1.parse(data)
        self.assertEqual(keys_of(tiles), [(4, 31, 0), (0, 4, 18), (4, 31, 63)])
        self.assertEqual([t.digest for t in tiles[:2]], [t.digest for t in old])
        self.assertEqual(tiles[2].meta[:28], old[0].meta[:28])
        self.assertEqual(tiles[2].meta[32:], old[0].meta[32:])
        bp, bl = struct.unpack_from("<ii", out, 0x114 + 2 * 96 + 72)
        self.assertEqual(out[bp:bp + bl], b"AAAA")
        twice = automap_void.add_tile(out, (0, 4, 18), 62)
        self.assertEqual(keys_of(dt1.parse(twice))[-1], (0, 4, 62))
        for i, want in ((0, b"AAAA"), (1, b"BBBBBB"), (2, b"AAAA"), (3, b"BBBBBB")):
            bp, bl = struct.unpack_from("<ii", twice, 0x114 + i * 96 + 72)
            self.assertEqual(twice[bp:bp + bl], want)

    def test_find_walls_far_from_walkable_floor(self):
        w, h = 12, 3
        floor = np.zeros((h, w), np.uint32)
        floor[:, :2] = (1 << 20) | (1 << 8) | 1       # style 1 seq 1: walkable
        floor[:, 2:] = (2 << 20) | (1 << 8) | 1       # style 2 seq 1: blocked everywhere
        wall = np.zeros((h, w), np.uint32)
        wall[1, :] = (31 << 20) | 1
        orient = np.full((h, w), 2, np.int32)         # wr
        ds = SimpleNamespace(width=w, height=h, floors=lambda: [floor], walls=lambda: [wall],
                             orientation=lambda j: orient)
        orig = automap_void._walkable
        automap_void._walkable = lambda paths: {(1, 1): True, (2, 1): False}
        try:
            hits = automap_void.find(ds, [])
        finally:
            automap_void._walkable = orig
        self.assertEqual(sorted(x for x, *_ in hits), list(range(2 + automap_void.REACH, w)))
        automap_void._walkable = lambda paths: {(1, 1): True, (2, 1): False}
        try:
            far = automap_void.find(ds, [], 6)                  # a wider reach (REACH_MAP) keeps more walls
        finally:
            automap_void._walkable = orig
        self.assertEqual(sorted(x for x, *_ in far), list(range(2 + 6, w)))

    def test_reach_map_keys_are_maps(self):
        for k, v in automap_void.REACH_MAP.items():
            self.assertTrue(k.startswith("expansion/") and v > automap_void.REACH)


if __name__ == "__main__":
    unittest.main()
