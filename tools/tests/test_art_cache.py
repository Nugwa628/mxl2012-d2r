"""Unit tests of the art statistics cache in tools/effects_hd.py: a cache written by other measuring code is not reused.
Run: py -3 -m unittest discover -s tools/tests -p "test_art_cache.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import effects_hd as fx  # noqa: E402

ENTRY = {"n": 1, "w": 31, "h": 56}
KEY = "d2r/missiles/arrow"


class StaleCache(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "art.json"

    def write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data), "utf-8")

    def test_file_without_a_version_is_dropped_and_rewritten(self):
        self.write({KEY: ENTRY})
        art = fx.ArtCache(self.path)
        self.assertNotIn(KEY, art.d)
        art.save()
        self.assertEqual(json.loads(self.path.read_text("utf-8")), {fx.STATS_KEY: fx.stats_version()})

    def test_file_of_other_code_is_dropped(self):
        self.write({fx.STATS_KEY: "other", KEY: ENTRY})
        self.assertNotIn(KEY, fx.ArtCache(self.path).d)

    def test_file_of_this_code_is_kept_untouched(self):
        self.write({fx.STATS_KEY: fx.stats_version(), KEY: ENTRY})
        art = fx.ArtCache(self.path)
        self.assertEqual(art.d[KEY], ENTRY)
        self.assertFalse(art.dirty)

    def test_missing_file_is_not_written_for_nothing(self):
        art = fx.ArtCache(self.path)
        art.save()
        self.assertFalse(self.path.exists())

    def test_version_follows_the_measuring_code(self):
        before = fx.stats_version()
        with mock.patch.object(fx, "_hues", lambda rgb, mx, mn: rgb):
            self.assertNotEqual(fx.stats_version(), before)


class Height(unittest.TestCase):
    def test_art_wholly_above_its_anchor_measures_its_own_height(self):
        art = fx.ArtCache(Path("does-not-exist.json"))
        art.pal = np.full((256, 3), 200.0)
        frame = (0, -20, 3, 2, bytes([9] * 6))
        data = bytes(2) + bytes([1]) + (1).to_bytes(4, "little") + bytes(8) + (0).to_bytes(4, "little") + bytes(4)
        with mock.patch("dcc.decode_direction", return_value=(0, -20, 3, 2, [frame])):
            st = art.stats(data)
        self.assertEqual((st["w"], st["h"]), (3, 2))


if __name__ == "__main__":
    unittest.main()
