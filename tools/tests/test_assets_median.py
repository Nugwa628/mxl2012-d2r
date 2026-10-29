"""Checks of the real asset pack's Median tree (assets/median: tools/mpq_extract.py of the ModDB original's patch_d2.mpq).

Skipped when assets/ is not there (a fresh checkout, CI without the MXL_ASSETS_TOKEN secret); with MXL_ASSETS_REQUIRED=1
(CI's `assets` job after its fetch, tools/ci_assets.sh) a missing tree fails instead. The byte check of every file is
`tools/asset_pack.py verify --full`; these tests check what the tree is and that the build's first steps can read it without
any Blizzard file: the manifest says v005 original, the 1.13c tables parse with tools/mxl2012_prep.py, the .tbl strings
read with tools/tbl2json.py.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_assets_median.py"
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import mpq_extract  # noqa: E402

ROOT = TOOLS.parent
MEDIAN = ROOT / "assets" / "median"
PRESENT = (MEDIAN / "_manifest.json").is_file()
REQUIRED = os.environ.get("MXL_ASSETS_REQUIRED") == "1"


def setUpModule():
    if not PRESENT and REQUIRED:
        raise AssertionError(f"MXL_ASSETS_REQUIRED=1 but {MEDIAN} is missing: the asset pack was not fetched")


@unittest.skipUnless(PRESENT, "assets/median not fetched (tools/asset_pack.py fetch, docs/setup.md step 4)")
class MedianTree(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((MEDIAN / "_manifest.json").read_text("utf-8"))

    def test_source_is_the_v005_original(self):
        src = self.manifest["source"]
        self.assertEqual((src["sha256"], src["size"]), (mpq_extract.ORIGINAL_SHA256, mpq_extract.ORIGINAL_SIZE))
        self.assertTrue(src["original_v005"])

    def test_counts(self):
        m = self.manifest
        self.assertEqual((m["hash_table_entries"], m["extracted"], len(m["unnamed"]), m["failed"]), (2363, 2362, 19, []))

    def test_every_file_of_the_extraction_is_there(self):
        missing = [rel for rel, f in self.manifest["files"].items()
                   if not (MEDIAN / rel).is_file() or (MEDIAN / rel).stat().st_size != f["size"]]
        self.assertEqual(missing, [])

    def test_strings_read(self):
        import tbl2json
        lng = MEDIAN / "data" / "local" / "lng" / "eng"
        counts = {n: len(tbl2json.read_tbl(lng / f"{n}.tbl")) for n in ("string", "expansionstring", "patchstring")}
        self.assertTrue(all(c > 100 for c in counts.values()), counts)

    def test_tables_prepare(self):
        (ROOT / "work").mkdir(exist_ok=True)   # mxl2012_prep.py keeps its rename list in work/
        with tempfile.TemporaryDirectory() as out:
            r = subprocess.run([sys.executable, "-I", str(TOOLS / "mxl2012_prep.py"),
                                "--src", str(MEDIAN / "data" / "global" / "excel"), "--out", out],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            names = {p.stem for p in Path(out).glob("*.txt")}
        for t in ("skills", "monstats", "itemstatcost", "misc", "uniqueitems", "cubemain", "levels", "missiles"):
            self.assertIn(t, names)


if __name__ == "__main__":
    unittest.main()
