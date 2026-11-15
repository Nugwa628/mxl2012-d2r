"""Checks of the generated files and the shipped art: the plain D2R book (src/default_book.inc) and panel layouts
(src/statbook_plain_layout.h) are what the tools make, every sprite the plain layouts name is in data/hd/..., the release
zip's layout. The two "is current" checks need D2R's own files (D2R_DATA, tools/d2r_paths.py) and are skipped without them.

  py -3 -m unittest discover -s tools/tests -v
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import advanced_stats  # noqa: E402
import d2r_paths  # noqa: E402
import package  # noqa: E402
import statbook  # noqa: E402
import statbook_layout as L  # noqa: E402

ART = ROOT / package.ART


def have(rel: str) -> bool:
    try:
        d2r_paths.d2r_file(rel)
        return True
    except SystemExit:
        return False


def widgets(node):
    yield node
    for c in node.get("children", []):
        yield from widgets(c)


class PlainBook(unittest.TestCase):
    def test_book_parses(self):
        book = L.plain_book()
        self.assertEqual(len(L.tabs(book)), len(book["pages"]) + 2)   # Character, the pages, All Stats
        self.assertTrue(book["pages"] and book["all"])
        self.assertTrue(all(len(L.page_lines(recs)) <= L.LINES for _p, _t, recs in book["pages"]))

    def test_all_stats_rows_read(self):
        rows = advanced_stats.read_rows()
        self.assertTrue(rows)
        self.assertTrue(all(r["group"] in advanced_stats.GROUPS for r in rows))

    @unittest.skipUnless(have("data/global/excel/itemstatcost.txt"), "needs D2R's itemstatcost.txt (D2R_DATA)")
    def test_default_book_is_current(self):
        self.assertEqual(statbook.main(["check"]), 0, "src/default_book.inc is out of date: py -3 tools/statbook.py default")


class PlainLayouts(unittest.TestCase):
    @unittest.skipUnless(have(L.FONTS["Formal"]) and have(L.FONTS[""]), "needs D2R's fonts (D2R_DATA)")
    def test_header_is_current(self):
        self.assertEqual(L.PLAIN_HEADER.read_text("utf-8"), L.plain_header_text(),
                         "src/statbook_plain_layout.h is out of date: py -3 -I tools/statbook_layout.py plain")

    def test_every_own_sprite_shipped(self):
        book = L.plain_book()
        for make in (L.plain_layout, L.plain_side_layout):
            for w in widgets(make(book)):
                fn = w.get("fields", {}).get("filename", "")
                if fn.startswith(L.ART):
                    art = fn[len(L.ART):]
                    self.assertIn(art, L.PLAIN_OWN_ART, fn)
        for art in L.PLAIN_OWN_ART:
            for ext in (".sprite", ".lowend.sprite"):
                self.assertTrue((ART / (art.lower() + ext)).is_file(), art + ext)

    def test_header_names_the_shipped_sprites(self):
        text = L.PLAIN_HEADER.read_text("utf-8")
        files = set(re.findall(r'\{"([a-z]+\.sprite)", R"SBJSON', text))
        self.assertEqual(files, {a.lower() + ".sprite" for a in L.PLAIN_OWN_ART})


class Package(unittest.TestCase):
    def test_zip_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            dll = Path(tmp) / "statbook.dll"
            dll.write_bytes(b"MZ")
            names = [n for n, _ in package.entries(dll)]
        base = "mods/" + package.MOD
        for n in ("modinfo.json", f"{package.MOD}.mpq/modinfo.json", "d2rloader/plugins/statbook.dll",
                  "d2rloader/config/statbook.toml", "README.md", "LICENSE"):
            self.assertIn(f"{base}/{n}", names)
        art = [n for n in names if n.startswith(f"{base}/{package.MOD}.mpq/data/hd/global/ui/panel/statbook/")]
        self.assertEqual(len(art), 2 * len(L.PLAIN_OWN_ART))
        self.assertRegex(package.version(), r"^\d+\.\d+\.\d+$")

    def test_cmake_builds_every_source(self):
        cmake = (ROOT / "CMakeLists.txt").read_text("utf-8")
        for p in list((ROOT / "src").glob("*.cpp")) + list((ROOT / "src" / "shared").glob("*.cpp")):
            self.assertIn(p.relative_to(ROOT).as_posix(), cmake)
        tests = re.findall(r"add_executable\((\w+)", (ROOT / "tests" / "CMakeLists.txt").read_text("utf-8"))
        self.assertEqual(set(tests), set(re.search(r"foreach\(t ([\w ]+)\)", cmake).group(1).split()))


if __name__ == "__main__":
    unittest.main()
