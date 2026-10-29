"""tools/mpq_extract.py without StormLib: finding the archive, refusing anything but the v005 original, the names list.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_mpq_extract.py" """
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import mpq_extract  # noqa: E402


class MpqExtract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_find_mpq(self):
        self.assertIsNone(mpq_extract.find_mpq(self.dir))
        mpq = self.dir / "Median XL" / "Patch_D2.mpq"
        mpq.parent.mkdir()
        mpq.write_bytes(b"MPQ\x1a")
        self.assertEqual(mpq_extract.find_mpq(self.dir), mpq)
        self.assertEqual(mpq_extract.find_mpq(mpq), mpq)
        (self.dir / "patch_d2.mpq").write_bytes(b"MPQ\x1a")   # two candidates: the caller must name one
        self.assertIsNone(mpq_extract.find_mpq(self.dir))

    def test_refuses_other_archives(self):
        mpq = self.dir / "patch_d2.mpq"
        mpq.write_bytes(b"MPQ\x1a" + b"\0" * 60)
        out = self.dir / "out"
        with contextlib.redirect_stdout(io.StringIO()) as buf:
            rc = mpq_extract.extract(mpq, out)
        self.assertEqual(rc, 1)
        self.assertIn("not Median XL 2012 v005", buf.getvalue())
        self.assertFalse(out.exists())

    def test_names_list(self):
        names = mpq_extract.NAMES.read_text("ascii").splitlines()
        self.assertEqual(len(names), 49)
        self.assertEqual(names, sorted(names))
        self.assertTrue(all(n.startswith("data\\") and "/" not in n for n in names))   # MPQ names use backslashes


if __name__ == "__main__":
    unittest.main()
