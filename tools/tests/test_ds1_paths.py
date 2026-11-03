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


if __name__ == "__main__":
    unittest.main()
