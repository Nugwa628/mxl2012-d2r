"""game_checks.made_name: the character name the game actually saved after Create (bug #251 run: typed IlvlAma, made IlvlAamma);
no game is started.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_game_checks_made_name.py" """
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc  # noqa: E402


class MadeName(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.t = time.time() - 100

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, name):
        p = os.path.join(self.dir, name + ".d2s")
        Path(p).write_bytes(b"\x55\xaa\x55\xaa")
        self.t += 10
        os.utime(p, (self.t, self.t))

    def test_newest_first(self):
        self.save("Old")
        self.save("Newer")
        self.assertEqual(gc.save_names(self.dir), ["Newer", "Old"])

    def test_typed_name_kept(self):
        self.save("IlvlOld")
        before = gc.save_names(self.dir)
        self.save("IlvlAma")
        self.assertEqual(gc.made_name(before, "IlvlAma", self.dir), "IlvlAma")

    def test_stray_input_name(self):
        self.save("IlvlOld")
        self.save("IlvlAma")  # an earlier character with the asked name is not the new one
        before = gc.save_names(self.dir)
        self.save("IlvlAamma")
        self.assertEqual(gc.made_name(before, "IlvlAma", self.dir), "IlvlAamma")

    def test_no_new_save_yet(self):
        self.save("IlvlOld")
        before = gc.save_names(self.dir)
        self.assertEqual(gc.made_name(before, "IlvlAma", self.dir), "IlvlAma")


if __name__ == "__main__":
    unittest.main()
