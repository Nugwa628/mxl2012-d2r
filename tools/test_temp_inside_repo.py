"""`unittest discover -s tools`: temp files stay inside the project (the full checks are in tools/tests/test_projtemp.py)."""
import tempfile
import unittest

import projtemp


class TempInsideRepoTests(unittest.TestCase):
    def test_gettempdir_is_inside_the_repo(self):
        self.assertTrue(projtemp.inside(tempfile.gettempdir(), projtemp.ROOT), tempfile.gettempdir())

    def test_temporary_directory_is_inside_the_repo(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(projtemp.inside(d, projtemp.ROOT), d)


if __name__ == "__main__":
    unittest.main()
