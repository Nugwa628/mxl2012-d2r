"""tools/github_release.py (the release text from CHANGELOG.md) and tools/release.sh (its argument and version checks). No
network, no GitHub, no forge: the pieces that build the text and refuse a bad call."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import contextlib
import io
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import github_release as gr

HERE = Path(__file__).resolve().parent
CHANGELOG = """# Changelog

## Unreleased

### 0.3.0 (not yet)
draft, not this one

## D2R-XL 2012

### 0.2.0 (2026-11-01)
Fixed [a thing](docs/bugs.md).
- more

### 0.1.0
First release.

## D2R-XL 2012 Downloader

### 0.1.0 downloader
Only the downloader.
"""


class ChangelogTests(unittest.TestCase):
    def test_section_is_the_first_heading_of_that_version(self):
        self.assertEqual(gr.changelog_section(CHANGELOG, "0.2.0"), "Fixed [a thing](docs/bugs.md).\n- more")
        self.assertEqual(gr.changelog_section(CHANGELOG, "0.1.0"), "First release.")  # not the downloader's 0.1.0

    def test_missing_section_stops(self):
        with self.assertRaises(SystemExit) as e:
            gr.changelog_section(CHANGELOG, "9.9.9")
        self.assertIn("### 9.9.9", str(e.exception))

    def test_a_longer_version_is_not_a_match(self):
        with self.assertRaises(SystemExit):
            gr.changelog_section("### 0.10.0\ntext\n", "0.1.0")

    def test_release_body_links_this_products_site_and_names(self):
        body = gr.release_body("0.2.0", "Fixed [a thing](docs/bugs.md).", "0.3.1")
        self.assertIn("https://github.com/Nugwa628/mxl2012-d2r/blob/main/docs/bugs.md", body)
        self.assertIn("https://files.werdegames.com/mxl2012/launcher/0.3.1/D2R-XL-2012-Downloader.exe", body)
        self.assertIn("https://files.werdegames.com/mxl2012/releases/0.2.0/D2R-XL-2012-0.2.0.7z", body)
        self.assertIn("mods\\mxl2012", body)
        self.assertIn("build 93847", body)
        self.assertNotIn("/mxl/", body)  # another product's folder

    def test_dry_run_prints_the_tag_and_text(self):
        out = io.StringIO()
        with mock.patch.object(gr, "ROOT", self._root()), mock.patch("sys.argv", ["github_release.py", "0.2.0", "--commit", "abc",
                                                                                   "--dry-run"]), contextlib.redirect_stdout(out):
            self.assertEqual(gr.main(), 0)
        self.assertTrue(out.getvalue().startswith("v0.2.0 on abc"))
        self.assertIn("Fixed [a thing]", out.getvalue())

    def _root(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(tmp, ignore_errors=True))
        (tmp / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
        return tmp


def find_bash():
    """A bash that understands the script's path (Git Bash); the WSL launcher in System32 does not."""
    exe = shutil.which("bash")
    if not exe:
        return None
    r = subprocess.run([exe, "-n", (HERE / "release.sh").as_posix()], capture_output=True)
    return exe if r.returncode == 0 else None


BASH = find_bash()


@unittest.skipUnless(BASH, "no bash that can read tools/release.sh")
class ReleaseScriptTests(unittest.TestCase):
    def run_sh(self, *args):
        r = subprocess.run([BASH, (HERE / "release.sh").as_posix(), *args], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_no_version_prints_usage(self):
        rc, out = self.run_sh()
        self.assertEqual(rc, 2)
        self.assertIn("--check-only", out)
        self.assertIn("MXL_PUBLISH_TARGET", out)

    def test_version_must_be_x_y_z(self):
        for bad in ("1.0", "v1.0.0", "1.0.0-rc1", "1.0.0; echo"):
            rc, out = self.run_sh(bad)
            self.assertEqual(rc, 1, bad)
            self.assertIn("version must be x.y.z", out)

    def test_options_are_checked_before_anything_runs(self):
        self.assertEqual(self.run_sh("1.0.0", "--channel", "beta")[0], 1)
        self.assertEqual(self.run_sh("1.0.0", "--channel", "test", "--with-github")[0], 1)
        self.assertEqual(self.run_sh("1.0.0", "--bogus")[0], 2)
        self.assertEqual(self.run_sh("1.0.0", "1.0.1")[0], 2)

    def test_script_has_lf_line_endings_and_the_safety_flags(self):
        raw = (HERE / "release.sh").read_bytes()
        self.assertNotIn(b"\r", raw)
        self.assertIn(b"set -euo pipefail", raw)
        for line in raw.decode("utf-8").splitlines():
            if "publish_release.py" in line and not line.lstrip().startswith("#"):
                self.assertNotRegex(line, r"\|\s*(tail|head|grep|sed|tee)", line)


if __name__ == "__main__":
    unittest.main()
