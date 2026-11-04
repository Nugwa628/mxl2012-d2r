"""Unit tests of tools/ds1_paths.py (bug #525): which .ds1 files move (D2R has the path with other bytes), the lvlprest File cells,
the HD scenes that move or are copied from D2R, and the hole2_room helpers of tools/game_checks.py that judge the room in game.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_ds1_paths.py" """
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import ds1_paths as D  # noqa: E402

LVLPREST = ("Name\tDef\tFile1\tFile2\tFile3\r\n"
            "Act 1 - Cave Treasure 4\t106\tAct1/Caves/CaveRoom4.ds1\t0\t0\r\n"
            "Act 1 - Cave Treasure 5\t107\tAct1/Caves/CaveRoom5.ds1\t0\t0\r\n"
            "Act 3 - Dungeon Treasure 1\t703\tAct3\\Jungle\\DungRm6A.ds1\tAct3/Jungle/DungRm6A.ds1\t0\r\n")


class RewriteTests(unittest.TestCase):
    def test_moved_cells_prefixed_case_kept(self):
        out, n = D.rewrite_lvlprest(LVLPREST, {"act1/caves/caveroom4.ds1", "act3/jungle/dungrm6a.ds1"})
        self.assertEqual(n, 3)
        rows = out.split("\r\n")
        self.assertEqual(rows[1].split("\t")[2], "mxl2012/Act1/Caves/CaveRoom4.ds1")
        self.assertEqual(rows[2], "Act 1 - Cave Treasure 5\t107\tAct1/Caves/CaveRoom5.ds1\t0\t0")  # not moved: as it was
        self.assertEqual(rows[3].split("\t")[2:4], ["mxl2012/Act3/Jungle/DungRm6A.ds1"] * 2)
        self.assertTrue(out.endswith("\r\n"))

    def test_nothing_moved(self):
        self.assertEqual(D.rewrite_lvlprest(LVLPREST, set()), (LVLPREST, 0))

    def test_scene_path(self):
        self.assertEqual(D.scene_rel("act1/caves/caveroom4.ds1"), "hd/env/preset/act1/caves/caveroom4.json")


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.mod, self.d2r = root / "mod", root / "d2r"
        files = {"act1/caves/caveroom4.ds1": (b"median room", b"d2r room"),   # edited: moves, own scene
                 "act2/tomb/duriel.ds1": (b"median lair", b"d2r lair"),       # edited: moves, D2R's scene copied
                 "act1/caves/caveroom5.ds1": (b"same", b"same"),              # equal to D2R's: stays
                 "expansion/morework/epicwhiners.ds1": (b"median only", None)}  # only the mod has it: stays
        lines = []
        for rel, (mine, theirs) in files.items():
            (self.mod / "global/tiles" / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.mod / "global/tiles" / rel).write_bytes(mine)
            if theirs is not None:
                (self.d2r / "data/global/tiles" / rel).parent.mkdir(parents=True, exist_ok=True)
                (self.d2r / "data/global/tiles" / rel).write_bytes(theirs)
                lines.append("data:data/global/tiles/" + rel)
        (self.d2r / "filelist.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        scene = self.mod / "hd/env/preset/act1/caves/caveroom4.json"
        scene.parent.mkdir(parents=True)
        scene.write_text('{"name": "median scene"}', encoding="utf-8")
        for t in D.LVLPREST:
            (self.mod / t).parent.mkdir(parents=True, exist_ok=True)
            (self.mod / t).write_bytes(("Name\tFile1\tFile2\r\nA\tAct1/Caves/CaveRoom4.ds1\t0\r\nB\tAct2/Tomb/Duriel.ds1\t0\r\n"
                                        "C\tAct1/Caves/CaveRoom5.ds1\t0\r\n").encode("latin-1"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_build(self):
        fake = mock.Mock()
        fake.d2r_bytes = lambda rel: b'{"name": "d2r scene"}' if rel == "data/hd/env/preset/act2/tomb/duriel.json" else None
        with mock.patch.dict(sys.modules, {"walls_hd": fake}):
            return D.build(self.mod, self.d2r)

    def test_moves_edited_maps_only(self):
        self.assertEqual(D.shadowed(self.mod, self.d2r, D.d2r_paths(self.d2r / "filelist.txt")),
                         ["act1/caves/caveroom4.ds1", "act2/tomb/duriel.ds1"])
        self.assertEqual(self.run_build(), 0)
        t = self.mod / "global/tiles"
        self.assertEqual((t / "mxl2012/act1/caves/caveroom4.ds1").read_bytes(), b"median room")
        self.assertFalse((t / "act1/caves/caveroom4.ds1").exists())
        self.assertTrue((t / "act1/caves/caveroom5.ds1").exists())
        self.assertTrue((t / "expansion/morework/epicwhiners.ds1").exists())
        p = self.mod / "hd/env/preset"
        self.assertIn("median scene", (p / "mxl2012/act1/caves/caveroom4.json").read_text(encoding="utf-8"))
        self.assertFalse((p / "act1/caves/caveroom4.json").exists())
        self.assertIn("d2r scene", (p / "mxl2012/act2/tomb/duriel.json").read_text(encoding="utf-8"))
        for lp in D.LVLPREST:
            text = (self.mod / lp).read_bytes().decode("latin-1")
            self.assertIn("A\tmxl2012/Act1/Caves/CaveRoom4.ds1\t0\r\n", text)
            self.assertIn("B\tmxl2012/Act2/Tomb/Duriel.ds1\t0\r\n", text)
            self.assertIn("C\tAct1/Caves/CaveRoom5.ds1\t0\r\n", text)

    def test_second_build_changes_nothing(self):
        self.run_build()
        before = {p: p.read_bytes() for p in self.mod.rglob("*") if p.is_file()}
        self.assertEqual(self.run_build(), 0)
        self.assertEqual({p: p.read_bytes() for p in self.mod.rglob("*") if p.is_file()}, before)

    def test_missing_d2r_scene_stops(self):
        (self.d2r / "data/global/tiles/act2/tomb/duriel.ds1").write_bytes(b"d2r lair")
        fake = mock.Mock()
        fake.d2r_bytes = lambda rel: None
        with mock.patch.dict(sys.modules, {"walls_hd": fake}), self.assertRaises(SystemExit):
            D.build(self.mod, self.d2r)


class RoomCheckTests(unittest.TestCase):
    """game_checks.hole2_room's judgement: which .ds1 the level's preset spots belong to."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
        import game_checks
        cls.gc = game_checks

    def test_spots_relative_to_level_corner(self):
        lines = ["room x=7580 y=13820", "room x=7500 y=13740", "preset type=2 class=37 x=7546 y=13854",
                 "preset type=5 class=4 x=7592 y=13790", "presets level 15 rooms 9 units 2"]
        self.assertEqual(self.gc.preset_spots(lines), {(46, 114), (92, 50)})

    def test_source_from_the_live_level(self):
        # Hole Level 2 before the fix (run checks of 2026-11-03): 8 of 9 spots are D2R's caveroom4, none Median's
        spots = {(75, 95), (50, 109), (46, 114), (92, 50), (101, 52), (93, 58), (66, 73), (69, 23), (60, 16)}
        median = {(31, 31), (45, 55), (22, 37), (19, 66), (35, 66), (39, 66)}
        d2r = {(22, 37), (46, 114), (50, 109), (14, 73), (60, 16), (69, 23), (75, 95), (25, 50), (93, 58), (101, 52), (66, 73),
               (32, 103)}
        self.assertEqual(self.gc.ds1_source(spots, [("mod", median), ("d2r", d2r)]), "d2r")
        self.assertEqual(self.gc.ds1_source({(a + 7, b + 3) for a, b in median}, [("mod", median), ("d2r", d2r)]), "mod")
        self.assertIsNone(self.gc.ds1_source({(500, 500)}, [("mod", median), ("d2r", d2r)]))

    def test_edit_hits_tell_maps_that_share_most_spots(self):
        # cathy3: every D2R spot is also Median's, so the overlap share alone ties; the Median-only spots decide
        d2r = {(10, 10), (20, 30), (40, 12), (55, 70)}
        median = d2r | {(65, 60), (68, 20)}
        live = {(a + 4500, b + 3100) for a, b in median}
        self.assertEqual(self.gc.edit_hits(live, median, d2r), (2, 0, (4500, 3100)))
        # Duriel's Lair: D2R's 6 braziers (only D2R's) found, Median's firetowers not
        median = {(135, 218), (78, 88), (59, 114), (93, 114)}
        d2r = {(135, 218), (78, 88), (73, 153), (87, 153)}
        live = {(a + 10, b + 20) for a, b in d2r}
        self.assertEqual(self.gc.edit_hits(live, median, d2r), (0, 2, (10, 20)))
        self.assertEqual(self.gc.edit_hits(set(), median, d2r), (0, 0, None))

    def test_edit_source_from_missing_spots(self):
        # Duriel's Lair in run checks-20261104-085859-s2: Duriel, Duriel's door and flies show, none of either map's own spots;
        # D2R's braziers next to Duriel would be listed with them, so the map is Median's
        shared = {(135, 218), (110, 207), (120, 193), (139, 184), (141, 205)}
        median = shared | {(59, 114), (93, 114), (79, 181)}
        d2r = shared | {(112, 216), (116, 195), (148, 177), (73, 153)}
        live = {(a + 22500, b + 15500) for a, b in shared}
        self.assertEqual(self.gc.edit_source(live, median, d2r), ("mod", 0, 0, (22500, 15500)))
        live_d2r = live | {(112 + 22500, 216 + 15500)}
        self.assertEqual(self.gc.edit_source(live_d2r, median, d2r)[0], "d2r")
        self.assertEqual(self.gc.edit_source({(1, 1)}, {(500, 500)}, {(600, 600)})[0], "unknown")

    def test_maps10_verdict(self):
        # run checks-20261104-092801-s2 (slot 2), shortened
        trace = [(0.0, 22638, 15693, (22635, 15717, 24)), (0.5, 22638, 15693, (22636, 15710, 17)),
                 (1.4, 22638, 15693, (22638, 15697, 4))]
        res = {16: {"hd": "reached", "src_hd": "mod", "walk_hd": "stopped 29 away"},
               64: {"hd": "reached", "src_hd": "unknown", "walk_hd": "no spots"},
               73: {"hd": "reached", "src_hd": "mod", "walk_hd": "reached", "trace_hd": trace}}
        bad, notes = self.gc.maps10_verdict(res)
        self.assertEqual(bad, [])
        self.assertIn("16 hd walk stopped 29 away", notes)
        self.assertIn("73 hd: Duriel first seen at (22635, 15717), 24 from the player, within 5 after 1.4 s", notes)
        res[90] = {"hd": "reached", "src_hd": "d2r", "walk_hd": "reached"}
        res[96] = {"hd": "not reached"}
        self.assertEqual(self.gc.maps10_verdict(res)[0], ["90 hd: d2r map", "96 hd not reached"])
        self.assertEqual(self.gc.duriel_first([(0.0, 1, 2, None)]), (None, None, None))

    def test_maps10_names_each_moved_map_once(self):
        rels = [r for rels, _spot, _n in self.gc.MAPS10.values() for r in rels]
        self.assertEqual(len(rels), len(set(rels)))
        # the 11 maps tools/ds1_paths.py moves: these plus caveroom4 (check hole2_room) and bivouac (no level of its own)
        self.assertEqual(set(rels) | {"act1/caves/caveroom4.ds1", "act1/outdoors/bivouac.ds1"},
                         {"act1/caves/caveroom4.ds1", "act1/caves/caveroom5.ds1", "act1/cathedrl/cathy3.ds1",
                          "act1/outdoors/bivouac.ds1", "act2/maggot/magqueen.ds1", "act2/palace/harem2.ds1",
                          "act2/tomb/duriel.ds1", "act3/jungle/dungrm6a.ds1", "act3/temple/temple5.ds1",
                          "act3/temple/temple6.ds1", "act4/diab/heart.ds1"})


if __name__ == "__main__":
    unittest.main()
