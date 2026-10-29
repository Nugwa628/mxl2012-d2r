"""The asset cache reader (tools/cache_probe.py) and game_checks' `cache_route` helpers (bug #360); no game is started.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_cache_probe.py" """
import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import cache_probe as cp  # noqa: E402
import game_checks as gc  # noqa: E402

LOG = r"""[2026-10-28 07:23:33.084] [ERROR]
+--------------------------------------------------------------------------------------------------+
| ASSERTION - a game check failed                                                                  |
| Message : BC_ASSERT: 0                                                                           |
| Location: Fog\include\Fog\AssetCache.h:187                                                       |
| Caller  : D2RLoader-s3.exe+0x689C27                                                              |
| Details:                                                                                         |
| "The size of the asset cache has been exceeded! Significantly more assets are being loaded than  |
| expected."                                                                                       |
| DefaultCapacity = 128 (0x0000000000000080)                                                       |
| m_capacity = 128 (0x0000000000000080)                                                            |
| path = "data/hd/character/enemy/diablo/diablo_variant.json"                                      |
|                                                                                                  |
| Stack (most recent call first):                                                                  |
+--------------------------------------------------------------------------------------------------+
| Message : BC_ASSERT: activeUnit                                                                  |
| Location: InventoryItemWidget.cpp:378                                                            |
| Stack (most recent call first):                                                                  |
"""


class Log(unittest.TestCase):
    def test_asset_cache_asserts_only(self):
        self.assertEqual(cp.asserts_in_log(LOG), [{"default": 128, "capacity": 128,
                                                   "path": "data/hd/character/enemy/diablo/diablo_variant.json"}])
        self.assertEqual(cp.asserts_in_log("nothing"), [])

    def test_kind_of_path(self):
        self.assertEqual(cp.kind_of_path("data/hd/character/enemy/diablo/diablo_variant.json"), "VariantTransformTable")
        self.assertEqual(cp.kind_of_path("data/hd/character/enemy/mxl/v_0682ddc5.json"), "VariantTransformTable")
        self.assertEqual(cp.kind_of_path("data/hd/character/enemy/arach1/torso.model"), "ModelAsset")
        self.assertIsNone(cp.kind_of_path("data/hd/x.texture"))


class Header(unittest.TestCase):
    @staticmethod
    def raw(nb, arr, count, cap):
        b = bytearray(0x78)
        struct.pack_into("<QQQ", b, cp.OFF_BUCKETS_N, nb, arr, count)
        struct.pack_into("<Q", b, cp.OFF_CAPACITY, cap)
        return bytes(b)

    def test_header_and_plausible(self):
        h = cp.cache_header(self.raw(128, 0x1000, 102, 128))
        self.assertEqual(h, (128, 0x1000, 102, 128))
        self.assertTrue(cp.plausible(h))
        self.assertTrue(cp.plausible(cp.cache_header(self.raw(256, 0x1000, 129, 192))))  # 128 grown once
        self.assertFalse(cp.plausible(cp.cache_header(self.raw(100, 0x1000, 1, 128))))  # bucket count not a power of two
        self.assertFalse(cp.plausible(cp.cache_header(self.raw(128, 0x1000, 200, 128))))  # more entries than room
        self.assertFalse(cp.plausible(cp.cache_header(self.raw(128, 0x1000, 1, 100))))  # not a known capacity

    def test_growth(self):
        self.assertTrue(cp.grown(128, 192) and cp.grown(128, 288) and not cp.grown(128, 200))
        self.assertEqual(cp.overflows(128, 128), 0)
        self.assertEqual(cp.overflows(128, 192), 1)
        self.assertEqual(cp.overflows(128, 288), 2)
        self.assertIsNone(cp.overflows(128, 200))


class Route(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(gc.cache_route_steps(""), ["t1", "t2", "t3", "t4", "t5", "andariel"])
        self.assertEqual(gc.cache_route_steps(" v1, v5 ,c4click,"), ["v1", "v5", "c4click"])

    def test_tiles(self):
        lines = ["tile id=12 class=53 mode=0 at 22460,9510 dist=14 area=36", "tile junk", "tiles 1"]
        self.assertEqual(gc.cache_tiles(lines), [{"id": 12, "class": 53, "mode": 0, "x": 22460, "y": 9510, "area": 36}])

    def test_tile_class_from_levels(self):
        saved = gc._TABLES.get("levels")
        try:
            row = {"Id": "36"}
            row.update({"Vis%d" % i: "0" for i in range(8)})
            row.update({"Warp%d" % i: "-1" for i in range(8)})
            row.update({"Vis0": "35", "Warp0": "21", "Vis1": "37", "Warp1": "22"})
            gc._TABLES["levels"] = [row]
            self.assertEqual(gc.cache_tile_class(36, 37), 22)
            self.assertEqual(gc.cache_tile_class(36, 35), 21)
            self.assertIsNone(gc.cache_tile_class(36, 99))
            self.assertIsNone(gc.cache_tile_class(5, 37))
        finally:
            if saved is None:
                gc._TABLES.pop("levels", None)
            else:
                gc._TABLES["levels"] = saved


class Peaks(unittest.TestCase):
    RECS = [{"t": "01:00:00", "caches": {"0x11618": [80, 128], "0x26780": [10, 512], "0x26648": [700, 2750]}},
            {"t": "01:00:03", "caches": {"0x11618": [128, 128], "0x26780": [12, 512], "0x26648": [650, 2750]}},
            {"t": "01:00:06", "caches": {"0x11618": [130, 192], "0x26780": [11, 512], "0x26648": [690, 2750]}}]

    def test_names(self):
        self.assertEqual(cp.cache_name(0x11618, 128), "VariantTransformTable")
        self.assertEqual(cp.cache_name("0x26780", 768), "cache512@0x26780")
        self.assertEqual(cp.default_of(192), 128)
        self.assertIsNone(cp.default_of(200))

    def test_peaks(self):
        pk = cp.peaks(self.RECS)
        self.assertEqual(pk["VariantTransformTable"], {"peak": 130, "capacity": 192, "default": 128, "t": "01:00:06",
                                                       "overflows": 1})
        self.assertEqual(pk["cache512@0x26780"]["peak"], 12)
        self.assertEqual(pk["ModelAsset"]["t"], "01:00:00")
        txt = cp.peaks_text(pk)
        self.assertTrue(txt.startswith("VariantTransformTable 130/128 (1 overflow, capacity 192)"))

    def test_poll_writes_records(self):
        import tempfile
        snaps = iter([{"caches": {"0x11618": [5, 128]}, "variants": ["a_variant.json"]},
                      {"error": "gone"},
                      {"caches": {"0x11618": [6, 128]}, "variants": ["a_variant.json", "data/hd/character/enemy/mxl/v_1.json"]}])
        calls = []
        saved = cp.snapshot
        cp.snapshot = lambda pid: next(snaps)
        try:
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "p.jsonl")
                pk = cp.poll(lambda: 7, path, every=0, stop=lambda: calls.append(1) or len(calls) > 3, tag_fn=lambda: "step")
                recs = cp.read_poll(path)
        finally:
            cp.snapshot = saved
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["new"], ["a_variant.json"])
        self.assertEqual(recs[1]["new"], ["data/hd/character/enemy/mxl/v_1.json"])
        self.assertEqual((recs[1]["variants_mxl"], recs[1]["tag"]), (1, "step"))
        self.assertEqual(pk["VariantTransformTable"]["peak"], 6)


if __name__ == "__main__":
    unittest.main()
