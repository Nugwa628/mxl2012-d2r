"""Unit tests of tools/flac.py and tools/sounds_port.py on synthetic data (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_sounds_port.py" """
import hashlib
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import flac  # noqa: E402
import sounds_port as sp  # noqa: E402

HEADER = ["Sound", "*Index", "Redirect", "Channel", "FileName", "Volume Min", "Volume Max", "Group Size"]


def write_wav(path: Path, samples, rate=22050, width=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        x = np.asarray(samples)
        w.writeframes((x + 128).astype(np.uint8).tobytes() if width == 1 else x.astype("<i2").tobytes())


def tsv(path: Path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    sp.write_tsv(path, header, rows)


class FlacTests(unittest.TestCase):
    def roundtrip(self, x, rate=22050, bps=16):
        data = flac.encode(x, rate, bps)
        flac.check(data, x)
        return data

    def test_sizes(self):
        rng = np.random.default_rng(7)
        for n in (1, 2, 5, 16, 17, 4095, 4096, 4097, 9000):
            x = np.cumsum(rng.integers(-200, 200, n)).clip(-32768, 32767)
            self.roundtrip(x)

    def test_extremes_and_silence(self):
        self.roundtrip(np.array([-32768, 32767] * 3000))
        self.roundtrip(np.zeros(5000, dtype=np.int64))

    def test_stereo_and_8_bit(self):
        rng = np.random.default_rng(3)
        self.roundtrip(rng.integers(-32768, 32768, (5000, 2)), 44100)
        self.roundtrip(rng.integers(-128, 128, 3000), 11025, 8)

    def test_streaminfo(self):
        x = (np.sin(np.arange(10000) / 7) * 9000).astype(np.int64)
        data = self.roundtrip(x, 22028)
        info = flac.streaminfo(data)
        self.assertEqual((info["rate"], info["channels"], info["bits"], info["samples"]), (22028, 1, 16, 10000))
        self.assertEqual(info["md5"], hashlib.md5(x.astype("<i2").tobytes()).digest())
        self.assertLess(len(data), 10000 * 2 // 2)  # a smooth tone compresses well below half

    def test_wav(self):
        with tempfile.TemporaryDirectory() as d:
            x = (np.sin(np.arange(3000) / 5) * 20000).astype(np.int64)
            write_wav(Path(d) / "a.wav", x, 11025)
            info = flac.wav_to_flac(Path(d) / "a.wav", Path(d) / "out" / "a.flac")
            self.assertEqual((info["rate"], info["channels"], info["samples"]), (11025, 1, 3000))
            got, rate = flac.decode((Path(d) / "out" / "a.flac").read_bytes())
            self.assertEqual(rate, 11025)
            self.assertTrue(np.array_equal(got[:, 0], x))

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            flac.decode(b"RIFF....")
        data = bytearray(flac.encode(np.arange(100), 22050))
        data[-3] ^= 0xFF
        with self.assertRaises(ValueError):
            flac.check(bytes(data))


class RowTests(unittest.TestCase):
    def test_stem(self):
        self.assertEqual(sp.stem("taunt\\Holy_Boink.wav"), "taunt/holy_boink")
        self.assertEqual(sp.stem("taunt\\ecstaticfrenzy1,.flac"), "taunt/ecstaticfrenzy1,")
        self.assertEqual(sp.stem("a.b\\noext"), "a.b/noext")

    def test_own_rows(self):
        rows = [["vanilla", "1", "", "sfx/x_sd", "object\\a.flac", "", "", "0"],
                ["reuse", "2", "", "", "object\\a.flac", "", "", "0"],  # Median row on a D2R file: sound_rows' job
                ["own", "3", "", "", "taunt\\b.flac", "", "", "0"],
                ["nofile", "4", "", "", "", "", "", "0"],
                ["", "", "", "", "taunt\\c.flac", "", "", ""]]
        self.assertEqual(sp.own_rows(HEADER, rows, {"vanilla"}, {"object/a"}), [2])

    def test_channel_for(self):
        self.assertEqual(sp.channel_for({"monsounds.Taunt", "skills.stsound"}), sp.CHANNEL_MONSTER)
        self.assertEqual(sp.channel_for({"misc.usesound", "uniqueitems.dropsound"}), sp.CHANNEL_ITEMS)
        self.assertEqual(sp.channel_for({"uniqueitems.dropsound", "states.onsound"}), sp.CHANNEL_SKILLS)
        self.assertEqual(sp.channel_for(set()), sp.CHANNEL_SKILLS)

    def test_group_heads(self):
        rows = [["a", "", "", "", "", "", "", "3"], ["b", "", "", "", "", "", "", "0"], ["c", "", "", "", "", "", "", ""],
                ["d", "", "", "", "", "", "", "0"]]
        self.assertEqual(sp.group_heads(HEADER, rows), {1: 0, 2: 0})


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.median, self.d2r, self.mod = t / "median", t / "d2r" / "data" / "global" / "excel", t / "mod" / "data"
        sfx = self.median / "data" / "global" / "sfx"
        self.tone = (np.sin(np.arange(2000) / 3) * 8000).astype(np.int64)
        write_wav(sfx / "taunt" / "Boink.wav", self.tone)
        write_wav(sfx / "taunt" / "chant.wav", self.tone[::-1], 22028)
        write_wav(sfx / "item" / "gem.wav", self.tone)  # Median's replacement of a vanilla file: D2R's row keeps D2R's
        for bank in ("", "base"):
            tsv(self.d2r / bank / "sounds.txt", HEADER, [["gem", "1", "", "sfx/items_sd", "item\\gem.flac", "1", "1", "0"]])
            tsv(self.mod / "global" / "excel" / bank / "sounds.txt", HEADER, [
                ["gem", "1", "", "sfx/items_sd", "item\\gem.flac", "1", "1", "0"],
                ["shrine_boink", "2", "", "", "taunt\\Boink.flac", "128", "128", "0"],
                ["chant_1", "3", "", "", "taunt\\chant.flac", "255", "255", "2"],
                ["chant_2", "4", "", "", "taunt\\chant.flac", "255", "255", "0"],
                ["robot_taunt", "5", "", "", "taunt\\resistanceisfutile.flac", "255", "255", "0"]])
            ex = self.mod / "global" / "excel" / bank
            tsv(ex / "misc.txt", ["name", "usesound"], [["Book", "shrine_boink"]])
            tsv(ex / "states.txt", ["state", "onsound"], [["chant", "chant_1"]])
            tsv(ex / "monsounds.txt", ["Id", "Taunt"], [["robot", "robot_taunt"]])

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, bank=""):
        h, rows = sp.read_tsv(self.mod / "global" / "excel" / bank / "sounds.txt")
        return {r[0]: dict(zip(h, r)) for r in rows}

    def test_plan_writes_nothing(self):
        errors, report = sp.run(self.median, self.d2r, self.mod, write=False)
        self.assertEqual(errors, 0)
        self.assertFalse((self.mod / "global" / "sfx").exists())
        self.assertEqual(self.rows()["shrine_boink"]["Channel"], "")
        self.assertIn("4 rows play Median's own audio, 3 with a file", report[2])

    def test_build(self):
        errors, report = sp.run(self.median, self.d2r, self.mod, write=True)
        self.assertEqual(errors, 0)
        out = self.mod / "global" / "sfx" / "taunt"
        self.assertEqual(sorted(p.name for p in (self.mod / "global" / "sfx").rglob("*") if p.is_file()),
                         ["boink.flac", "chant.flac"])  # gem stays D2R's, the missing file is not invented
        got, rate = flac.decode((out / "chant.flac").read_bytes())
        self.assertEqual(rate, 22028)
        self.assertTrue(np.array_equal(got[:, 0], self.tone[::-1]))
        for bank in ("", "base"):
            r = self.rows(bank)
            self.assertEqual(r["gem"]["Channel"], "sfx/items_sd")
            self.assertEqual((r["shrine_boink"]["FileName"], r["shrine_boink"]["Channel"]), ("taunt\\boink.flac", sp.CHANNEL_ITEMS))
            self.assertEqual(r["chant_1"]["Channel"], sp.CHANNEL_SKILLS)
            self.assertEqual(r["chant_2"]["Channel"], sp.CHANNEL_SKILLS)  # group member: the head's channel
            self.assertEqual((r["robot_taunt"]["FileName"], r["robot_taunt"]["Channel"]),
                             ("taunt\\resistanceisfutile.flac", sp.CHANNEL_MONSTER))
            self.assertEqual(r["shrine_boink"]["Volume Min"], "128")
        text = "\n".join(report)
        self.assertIn("taunt/resistanceisfutile", text)
        self.assertIn("| chant_2 | taunt/chant.flac | Median | sfx/player-skills_sd | states.onsound (group of chant_1) |", text)

    def test_rerun_is_stable(self):
        sp.run(self.median, self.d2r, self.mod, write=True)
        first = (self.mod / "global" / "excel" / "sounds.txt").read_bytes()
        sp.run(self.median, self.d2r, self.mod, write=True)
        self.assertEqual(first, (self.mod / "global" / "excel" / "sounds.txt").read_bytes())


if __name__ == "__main__":
    unittest.main()
