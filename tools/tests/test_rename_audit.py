"""tools/rename_audit.py: the .bin value reader, the asset path candidates and the alternategfx body-location rule."""
import struct
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import rename_audit as ra  # noqa: E402


def bin_table(records: list[bytes], size: int = 16) -> bytes:
    return struct.pack("<I", len(records)) + b"".join(r.ljust(size, b"\0") for r in records)


class BinValueTests(unittest.TestCase):
    def setUp(self):
        # Name at 0, Token at 8: like objects.bin (row 194 "stair" / "sl")
        self.t = ra.BinTable(bin_table([b"Dummy\0\0\0NU", b"stair\0\0\0sl", b"chest\0\0\0C5"]))

    def test_record_layout(self):
        self.assertEqual((self.t.n, self.t.size), (3, 16))
        self.assertIsNone(self.t.record(3))

    def test_vanilla_holds_median_value(self):
        self.assertEqual(ra.vanilla_value(self.t.record(1), "sl", "9c"), "M")

    def test_vanilla_holds_d2r_value(self):
        self.assertEqual(ra.vanilla_value(self.t.record(2), "zz", "C5"), "D")
        self.assertEqual(ra.vanilla_value(self.t.record(2), "zz", "c5"), "D")  # case-insensitive

    def test_neither_or_no_record(self):
        self.assertEqual(ra.vanilla_value(self.t.record(1), "ab", "cd"), "?")
        self.assertEqual(ra.vanilla_value(None, "sl", "9c"), "?")

    def test_string_must_start_a_field(self):
        # "ir" is inside "stair": not a field of its own
        self.assertIsNone(ra.find_str(self.t.record(1), "ir"))
        self.assertEqual(ra.find_str(self.t.record(1), "sl"), 8)

    def test_keyed_lookup(self):
        t = ra.BinTable(bin_table([b"\0\0\0\0hax", b"\0\0\0\0axe", b"\0\0\0\0" b"2ax"]))
        t.index_keys("hax", [])
        self.assertEqual(t.by_key, {"hax": 0, "axe": 1, "2ax": 2})


class CandidateTests(unittest.TestCase):
    def test_object_token(self):
        files, dirs = ra.candidates("objtoken", "SL")
        self.assertIn("data/global/objects/sl/cof/slnuhth.cof", files)
        self.assertEqual(dirs, ["data/global/objects/sl/cof/"])

    def test_missile_extension_dropped(self):
        files, _ = ra.candidates("missile", "extra\\FireSmoke.dcc")
        self.assertEqual(files[0], "data/global/missiles/extra/firesmoke.dcc")

    def test_sound_wav_and_flac(self):
        files, _ = ra.candidates("sfx", "cursor\\pass.wav")
        self.assertIn("data/global/sfx/cursor/pass.flac", files)
        self.assertIn("data/local/sfx/cursor/pass.wav", files)

    def test_none_sound_is_empty(self):
        self.assertIn(ra.norm("none.flac"), ra.EMPTY)


class AltGfxTests(unittest.TestCase):
    TYPES = {"helm": ({"head"}, ["armo", ""]), "armo": (set(), ["", ""]), "glov": ({"glov"}, ["armo", ""]),
             "circ": (set(), ["helm", ""]), "shie": ({"rarm", "larm"}, ["armo", ""])}

    def test_drawn_locations(self):
        self.assertTrue(ra.alt_drawn("helm", self.TYPES))
        self.assertTrue(ra.alt_drawn("circ", self.TYPES))  # through Equiv1
        self.assertTrue(ra.alt_drawn("shie", self.TYPES))

    def test_not_drawn(self):
        self.assertFalse(ra.alt_drawn("glov", self.TYPES))
        self.assertFalse(ra.alt_drawn("", self.TYPES))
        self.assertFalse(ra.alt_drawn("nope", self.TYPES))


if __name__ == "__main__":
    unittest.main()
