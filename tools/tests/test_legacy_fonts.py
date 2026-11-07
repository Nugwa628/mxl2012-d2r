"""Clear legacy fonts: staging beside D2R's names, and zero nominal line height never reaching a D2R release."""
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401
import dc6  # noqa: E402
import legacy_fonts as fonts  # noqa: E402
import package_release  # noqa: E402


def pair(height=11):
    tbl = b"Woo!" + struct.pack("<IHBB", 1, 256, height, 1)
    tbl += b"".join(struct.pack("<HBBBBHHI", i, 0, 0 if i == 32 else 1, 1, 1, 0, i, 0) for i in range(256))
    picture = dc6.build_dc6([(1, 1, 0, 0, b"\x01\x01\x80")] * 256)
    return tbl, picture


class LegacyFontsTests(unittest.TestCase):
    def test_divisor_rejects_zero_not_legal_zero_space_advance(self):
        fonts.validate_font(*pair())
        with self.assertRaisesRegex(ValueError, "zero line height.*0x0A"):
            fonts.validate_font(*pair(0), "fontformal11")

    def test_frame_reference_and_zero_frame_size_rejected(self):
        tbl, picture = pair()
        bad = bytearray(tbl)
        struct.pack_into("<H", bad, 12 + 8, 256)
        with self.assertRaisesRegex(ValueError, "out of range"):
            fonts.validate_font(bad, picture)
        picture = dc6.build_dc6([(0, 1, 0, 0, b"\x80")] * 256)
        with self.assertRaisesRegex(ValueError, "nonempty"):
            fonts.validate_font(tbl, picture)

    def test_stock_fallback_hash_drift_and_reversible_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "local.zip"
            tbl, picture = pair(0)
            good, _ = pair()
            files = {"fontformal11.tbl": tbl, "fontformal11.dc6": picture, "font6.tbl": good, "font6.dc6": picture,
                     "fontformal8.tbl": good, "fontformal8.dc6": picture}
            pin = {"files": {n: {"size": len(b), "sha256": fonts.digest(b)} for n, b in files.items()}}
            with zipfile.ZipFile(archive, "w") as z:
                for n, b in files.items():
                    z.writestr("font/latin/" + n, b)
            output = fonts.prepare(archive, pin)
            self.assertEqual(sorted(output), ["font6.dc6", "font6.tbl"])  # formal11 stays stock, formal8 has no D2R font id
            self.assertEqual(output["font6.tbl"], good)
            pinfile = root / "pin.json"
            pinfile.write_text(json.dumps(pin), encoding="utf-8")
            mod = root / "mod"
            with mock.patch.object(fonts, "PIN", pinfile):
                fonts.apply(mod, True, archive)
                fonts.check_tree(mod / "data")
                self.assertFalse((mod / "data" / fonts.LATIN / "font6.tbl").exists())  # never under D2R's own name
                path = mod / "data" / fonts.CLEAR / "font6.tbl"
                path.write_bytes(b"user edited")
                with self.assertRaisesRegex(ValueError, "changed since staging"):
                    fonts.apply(mod, False)
                self.assertEqual(path.read_bytes(), b"user edited")
                path.write_bytes(output["font6.tbl"])
                fonts.apply(mod, False)
                self.assertFalse(path.exists())
                self.assertFalse((mod / "data" / fonts.CLEAR).exists())
                self.assertFalse((mod / fonts.STATE).exists())
            pin["files"]["fontformal11.tbl"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "untested font bytes"):
                fonts.prepare(archive, pin)

    def test_earlier_build_option_files_are_moved_to_the_clear_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good, picture = pair()
            files = {"font6.tbl": good, "font6.dc6": picture}
            pin = {"files": {n: {"size": len(b), "sha256": fonts.digest(b)} for n, b in files.items()}}
            archive = root / "local.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for n, b in files.items():
                    z.writestr("data/local/font/latin/" + n, b)
            pinfile = root / "pin.json"
            pinfile.write_text(json.dumps(pin), encoding="utf-8")
            mod = root / "mod"
            latin = mod / "data" / fonts.LATIN
            latin.mkdir(parents=True)
            for n, b in files.items():
                (latin / n).write_bytes(b)
            (mod / fonts.STATE).write_text(json.dumps({n: fonts.digest(b) for n, b in files.items()}), encoding="utf-8")
            with mock.patch.object(fonts, "PIN", pinfile):
                fonts.apply(mod, True, archive)
            self.assertFalse((latin / "font6.tbl").exists())
            self.assertEqual((mod / "data" / fonts.CLEAR / "font6.tbl").read_bytes(), good)
            self.assertEqual(json.loads((mod / fonts.STATE).read_text(encoding="utf-8")),
                             {"clear/font6.dc6": fonts.digest(picture), "clear/font6.tbl": fonts.digest(good)})

    def test_missing_clear_set_and_bad_clear_font(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            self.assertEqual(len(fonts.missing_clear(data)), 2 * len(fonts.SHIPPED))
            folder = data / fonts.CLEAR
            folder.mkdir(parents=True)
            good, picture = pair()
            for name in fonts.SHIPPED:
                (folder / (name + ".tbl")).write_bytes(good)
                (folder / (name + ".dc6")).write_bytes(picture)
            self.assertEqual(fonts.missing_clear(data), [])
            fonts.check_tree(data)
            (folder / "font8.tbl").write_bytes(pair(0)[0])
            with self.assertRaisesRegex(ValueError, "zero line height"):
                fonts.check_tree(data)

    def test_pin_covers_the_shipped_set(self):
        pin = json.loads(fonts.PIN.read_text(encoding="utf-8"))
        for name in fonts.SHIPPED:
            self.assertIn(name + ".tbl", pin["files"])
            self.assertIn(name + ".dc6", pin["files"])
        self.assertFalse(set(fonts.SHIPPED) & fonts.STOCK)

    def test_packager_rejects_hand_copied_crashing_font_before_replacing_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            folder = data / fonts.LATIN
            folder.mkdir(parents=True)
            tbl, picture = pair(0)
            (folder / "fontformal11.tbl").write_bytes(tbl)
            (folder / "fontformal11.dc6").write_bytes(picture)
            stage = root / "stage"
            stage.mkdir()
            (stage / "keep.txt").write_text("existing package", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "zero line height"):
                package_release.stage(stage, "test", root / "missing.dll", root, data_from=data)
            self.assertTrue((stage / "keep.txt").exists())


if __name__ == "__main__":
    unittest.main()
