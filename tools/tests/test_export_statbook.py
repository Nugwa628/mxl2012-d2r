"""tools/export_statbook.py: the exported Stat Book tree holds the expected files, every #include resolves inside it, no
internal note or monorepo path is left, and its Python tools run without this repository."""
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import export_statbook as E  # noqa: E402
import statbook_layout as L  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MUST = {"CMakeLists.txt", "README.md", "LICENSE", ".gitignore", ".github/workflows/build.yml", "statbook.toml",
        "src/statbook.cpp", "src/sheet_host.cpp", "src/statbook_plain_layout.h", "src/statbook_plain_legacy.h", "src/default_book.inc",
        "src/shared/panel_shared.cpp", "src/shared/panel_shared.h", "src/shared/panel_logic.h",
        "src/shared/block_rate_logic.h", "src/shared/hd_mode.h", "tests/CMakeLists.txt", "tests/book_test.cpp",
        "tools/statbook.py", "tools/statbook_layout.py", "tools/d2r_ui.py", "tools/d2r_paths.py", "tools/advanced_stats.py",
        "tools/package.py", "tools/tests/test_statbook_layout.py", "data/statbook_pages.tsv", "data/advanced_stats.tsv",
        "docs/statbook.md", "docs/statbook-layout.md"}
MUST_NOT = {"src/testharness.cpp", "src/testharness.h", "src/shared/rotw_stash_logic.h"}


class ExportTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        art, images = base / "art", base / "images"
        art.mkdir()
        images.mkdir()
        for a in L.PLAIN_OWN_ART:
            for ext in (".sprite", ".lowend.sprite"):
                (art / f"{a.lower()}{ext}").write_bytes(b"SpA1")
        for n in E.legacy_art_names():
            (art / n).write_bytes(b"\x06\x00\x00\x00")
        (images / "shot.png").write_bytes(b"\x89PNG")
        cls.out = base / "repo"
        cls.result = E.export(cls.out, art=art, build_art=False, images=images)
        cls.files = set(cls.result["files"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_no_problems(self):
        self.assertEqual(self.result["problems"], [])

    def test_expected_files(self):
        self.assertLessEqual(MUST, self.files, MUST - self.files)
        self.assertFalse(MUST_NOT & self.files)
        self.assertIn("docs/images/shot.png", self.files)
        art = {f for f in self.files if f.startswith(E.ART_DIR.as_posix() + "/")}
        self.assertEqual(len(art), 2 * len(L.PLAIN_OWN_ART))
        dc6 = {f for f in self.files if f.startswith(E.LEGACY_ART_DIR.as_posix() + "/")}
        self.assertEqual(dc6, {f"{E.LEGACY_ART_DIR.as_posix()}/{n}" for n in E.legacy_art_names()})
        # every source and test of statbook/ but the harness, nothing else under src/ and tests/
        want = {f"src/{p.name}" for p in (ROOT / "statbook" / "src").iterdir() if p.name not in E.SKIP_SRC}
        want |= {f"tests/{p.name}" for p in (ROOT / "statbook" / "tests").iterdir() if p.is_file()}
        want |= {f"src/shared/{s}" for s in E.SHARED} | {"src/shared/hd_mode.h"}
        self.assertEqual({f for f in self.files if f.startswith(("src/", "tests/"))}, want)

    def test_includes_resolve_inside(self):
        for rel in self.files:
            if not rel.endswith((".cpp", ".h", ".rc", ".inc")):
                continue
            p = self.out / rel
            for inc in re.findall(r'^\s*#\s*include\s+"([^"]+)"', p.read_text("utf-8"), flags=re.M):
                if inc in E.SKIP_SRC:         # the harness include, inside #ifdef STATBOOK_TEST_HARNESS (never defined there)
                    continue
                found = [d / inc for d in (p.parent, self.out / "src", self.out / "src" / "shared") if (d / inc).is_file()]
                self.assertTrue(found, f"{rel}: #include \"{inc}\" does not resolve inside the export")
                self.assertTrue(all(self.out in f.resolve().parents for f in found), f"{rel}: {inc} leaves the export")

    def test_no_monorepo_paths(self):
        for rel in self.files:
            if rel.startswith((E.ART_DIR.as_posix(), E.LEGACY_ART_DIR.as_posix(), "docs/images/")):
                continue
            text = (self.out / rel).read_text("utf-8")
            if rel not in E.VERBATIM:
                rx = r"\.\./\.\./plugin|plugin/src/|statbook/src/|^\s*import (fxpaths|median_stash|ui_art|pad_ui)$"
                self.assertIsNone(re.search(rx, text, re.M), rel)
            self.assertEqual(E.forbidden_hits(rel, text), [])
            self.assertNotIn("\r\n", text, rel)

    def test_public_check_of_the_tree_is_clean(self):
        import check_public
        self.assertEqual(check_public.scan_dir(self.out, check_public.load_allow()), [])

    def test_tools_run_without_this_repository(self):
        # -I: no user site, no PYTHONPATH; the export's own tools folder only
        code = ("import sys; sys.path.insert(0, 'tools'); import statbook_layout as L, statbook, advanced_stats, package; "
                "assert 'fxpaths' not in sys.modules; b = L.plain_book(); print(len(L.tabs(b)), len(advanced_stats.read_rows()))")
        r = subprocess.run([sys.executable, "-I", "-c", code], cwd=self.out, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split()[0], str(len(L.tabs(L.plain_book()))))
        r = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, 'tools'); import d2r_ui, d2r_paths"],
                           cwd=self.out, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_public_check_finds_a_planted_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a.txt").write_text("mail someone" + "@example.org\n", "utf-8")   # split: this file is scanned too
            import check_public
            self.assertEqual([r for _w, r, _s, _l in check_public.scan_dir(tmp, [])], ["email"])

    def test_refuses_a_full_folder(self):
        with self.assertRaises(SystemExit):
            E.export(self.out, build_art=False)


class Rewrites(unittest.TestCase):
    def test_paths(self):
        have = {"docs/statbook.md", "tools/statbook.py", "tests/sheet_resist_test.cpp"}
        t = E.rewrite_paths("see docs/statbook.md, docs/hd-ui.md, statbook/src/a.h, plugin/src/panel_logic.h, "
                            "plugin/tests/sheet_resist_test.cpp, panel statbook/StatBook", have)
        self.assertEqual(t, "see docs/statbook.md, D2R-XL 2012's docs/hd-ui.md, src/a.h, src/shared/panel_logic.h, "
                            "tests/sheet_resist_test.cpp, panel statbook/StatBook")

    def test_imports(self):
        self.assertEqual(E.rewrite_imports("    import ui_art\nimport fxpaths\nimport pad_ui as p\n"),
                         "    import d2r_ui as ui_art\nimport d2r_paths as fxpaths\nimport pad_ui as p\n")

    def test_scrub_rule_that_no_longer_matches_fails(self):
        with self.assertRaises(SystemExit):
            E.scrub("src/advstats.h", "nothing to scrub here")


if __name__ == "__main__":
    unittest.main()
