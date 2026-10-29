"""tools/projtemp.py: temp files stay inside the project (CLAUDE.md rule 1) in both test discovers, with nobody setting TMP/TEMP.

Run by `unittest discover -s tools/tests`; tools/test_temp_inside_repo.py makes the same check for `-s tools`.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402

ROOT = TOOLS.parent


class TempInsideRepoTests(unittest.TestCase):
    def test_gettempdir_is_inside_the_repo(self):
        self.assertTrue(projtemp.inside(tempfile.gettempdir(), ROOT), tempfile.gettempdir())

    def test_temp_files_and_folders_are_created_there(self):
        with tempfile.TemporaryDirectory() as d, tempfile.NamedTemporaryFile() as f:
            self.assertTrue(projtemp.inside(d, ROOT), d)
            self.assertTrue(projtemp.inside(f.name, ROOT), f.name)

    def test_child_processes_inherit_it(self):
        for v in projtemp.VARS:
            self.assertTrue(projtemp.inside(os.environ[v], ROOT), v)

    def test_every_test_module_imports_projtemp(self):
        missing = []
        for p in [*sorted(TOOLS.glob("test_*.py")), *sorted((TOOLS / "tests").glob("test_*.py"))]:
            if not re.search(r"^(\S.*; )?import projtemp\b", p.read_text("utf-8"), re.M):
                missing.append(p.name)
        self.assertEqual(missing, [], "add `import projtemp` (after the sys.path set-up) to these test modules")


class ChooseTests(unittest.TestCase):
    def test_default_is_work_tmp_of_the_repo(self):
        self.assertEqual(projtemp.choose({}), ROOT / "work" / "tmp")

    def test_system_temp_is_ignored(self):
        self.assertEqual(projtemp.choose({"TEMP": "/somewhere/else", "TMP": "/somewhere/else"}), ROOT / "work" / "tmp")

    def test_a_temp_inside_the_repo_or_runs_folder_is_kept(self):
        inside_repo = str(ROOT / "work" / "mine")
        self.assertEqual(projtemp.choose({"TMP": inside_repo}), Path(inside_repo))
        runs = str(projtemp.runs_dir() / "tmp")
        self.assertEqual(projtemp.choose({"TEMP": runs}), Path(runs))

    def test_mxl_tmp_wins(self):
        self.assertEqual(projtemp.choose({"MXL_TMP": "/x/y", "TEMP": str(ROOT / "work" / "mine")}), Path("/x/y"))

    def test_inside_does_not_confuse_prefixes(self):
        self.assertFalse(projtemp.inside(str(ROOT) + "-other", ROOT))
        self.assertTrue(projtemp.inside(ROOT / "a" / ".." / "work", ROOT))


if __name__ == "__main__":
    unittest.main()
