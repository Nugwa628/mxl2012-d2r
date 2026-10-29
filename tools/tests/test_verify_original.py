import pathlib as _pl, sys as _sys; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1])); import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location("verify_original", Path(__file__).resolve().parents[1] / "verify_original.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = self.root / "original"
        self.repack = self.root / "repack"
        self.original.mkdir()
        self.repack.mkdir()
        self.zip = self.root / "original.zip"
        with zipfile.ZipFile(self.zip, "w") as archive:
            archive.writestr("test.txt", "synthetic")

    def put(self, root, name, data):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_identical_and_inventory(self):
        self.put(self.original, "wrapper/patch_d2.mpq", b"same")
        self.put(self.repack, "other/patch_d2.mpq", b"same")
        self.put(self.original, "only.ini", b"original")
        self.put(self.repack, "only.dll", b"repack")
        text, verdict, valid = verify.report(self.zip, self.original, self.repack)
        self.assertEqual(verdict, "patch_d2.mpq identical")
        self.assertFalse(valid)
        self.assertIn("MISMATCH", text)
        self.assertIn("only.ini", text)
        self.assertIn("only.dll", text)
        self.assertIn(verify.digest(self.zip), text)

    def test_changed_mpq_contents(self):
        self.put(self.original, "patch_d2.mpq", b"one")
        self.put(self.repack, "patch_d2.mpq", b"two")
        a, b = self.root / "a", self.root / "b"
        a.mkdir(); b.mkdir()
        self.put(a, "data/file.txt", b"one")
        self.put(b, "data/file.txt", b"two")
        self.put(a, "new.txt", b"new")
        text, verdict, _ = verify.report(self.zip, self.original, self.repack, a, b)
        self.assertEqual(verdict, "patch_d2.mpq not identical")
        self.assertIn("data/file.txt", text)
        self.assertIn("new.txt", text)
        self.assertIn("### Changed files", text)
        pending, _, _ = verify.report(self.zip, self.original, self.repack)
        self.assertIn("comparison pending", pending)

    def test_duplicate_names_rejected(self):
        self.put(self.original, "a/patch_d2.mpq", b"a")
        self.put(self.original, "b/PATCH_D2.MPQ", b"b")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            verify.inventory(self.original, True)

    def test_fresh_destination_and_nested_archive(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            if command[1] == "x" and len([c for c in calls if c[1] == "x"]) == 1:
                (destination / "installer.exe").write_bytes(b"fake")
            return mock.Mock(returncode=0, stderr="", stdout="")
        destination = self.root / "fresh"
        with mock.patch.object(verify.subprocess, "run", side_effect=run):
            verify.extract(self.zip, destination, Path("7z"))
        self.assertEqual([c[1] for c in calls], ["x", "t", "x"])
        with self.assertRaises(FileExistsError):
            verify.extract(self.zip, destination, Path("7z"))

    def test_matching_md5(self):
        with mock.patch.object(verify, "EXPECTED_MD5", verify.digest(self.zip, "md5")):
            _, _, valid = verify.report(self.zip, self.original, self.repack)
        self.assertTrue(valid)


if __name__ == "__main__":
    unittest.main()
