"""fxpaths.ci: a table's mixed-case name finds the lower-case extraction file on a case-sensitive file system."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402


class CiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "data" / "hd" / "missiles").mkdir(parents=True)
        (self.root / "data" / "hd" / "missiles" / "chainlightningbolt.json").write_text("{}", "utf-8")
        fxpaths._LISTINGS.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def test_existing_path_is_returned_unchanged(self):
        p = self.root / "data" / "hd" / "missiles" / "chainlightningbolt.json"
        self.assertEqual(fxpaths.ci(p), p)

    def test_mixed_case_name_finds_the_lower_case_file(self):
        asked = self.root / "data" / "HD" / "missiles" / "chainlightningBolt.json"
        got = fxpaths.ci(asked)
        self.assertTrue(got.is_file())
        self.assertEqual(got.read_text("utf-8"), "{}")
        if os.name != "nt":  # Windows: the asked path exists as it is (the file system ignores case)
            self.assertEqual(got.name, "chainlightningbolt.json")

    def test_missing_file_gives_the_asked_path(self):
        asked = self.root / "data" / "hd" / "missiles" / "NoSuchBolt.json"
        self.assertEqual(fxpaths.ci(asked), asked)
        self.assertFalse(fxpaths.ci(asked).exists())
        missing_dir = self.root / "nothere" / "x.json"
        self.assertEqual(fxpaths.ci(missing_dir), missing_dir)

    def test_relative_path(self):
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            got = fxpaths.ci(Path("data/hd/missiles/ChainLightningBolt.json"))
            self.assertTrue(got.is_file())
        finally:
            os.chdir(cwd)


class CiDestTests(unittest.TestCase):
    """fxpaths.ci_dest: a write lands in the folder another step made in other case, as on Windows."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mon = Path(self.tmp.name) / "data" / "global" / "monsters"
        (self.mon / "$G" / "cof").mkdir(parents=True)  # state_translvl.write_palshifts: the token's code, upper case
        (self.mon / "$G" / "cof" / "palshift.dat").write_bytes(b"x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_existing_folder_in_other_case_is_used(self):
        got = fxpaths.ci_dest(self.mon / "$g" / "cof" / "$gnuhth.cof")
        if os.name == "nt":
            self.assertEqual(got, self.mon / "$g" / "cof" / "$gnuhth.cof")  # NTFS merges the two by itself
        else:
            self.assertEqual(got, self.mon / "$G" / "cof" / "$gnuhth.cof")

    def test_missing_folders_keep_the_asked_spelling(self):
        self.assertEqual(fxpaths.ci_dest(self.mon / "$G" / "tr" / "x.dcc"), self.mon / "$G" / "tr" / "x.dcc")
        self.assertEqual(fxpaths.ci_dest(self.mon / "new" / "cof" / "y.cof"), self.mon / "new" / "cof" / "y.cof")


class NtfsOrderTests(unittest.TestCase):
    def test_folder_by_folder_names_ignoring_case(self):
        base = Path("/x/missiles")
        got = fxpaths.ntfs_order([base / "b" / "a.dcc", base / "Zed.dcc", base / "a.dcc", base / "B" / "c.dcc",
                                  base / "b" / "deep" / "q.dcc", base / "_u.dcc"], base)
        self.assertEqual([p.relative_to(base).as_posix() for p in got],
                         ["a.dcc", "Zed.dcc", "_u.dcc", "b/a.dcc", "B/c.dcc", "b/deep/q.dcc"])


if __name__ == "__main__":
    unittest.main()
