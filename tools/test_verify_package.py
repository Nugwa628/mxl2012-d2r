"""tools/verify_package.py on a small fake package; no game files, no plugin build."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import package_release as pr
import verify_package as vp


SEVEN = pr.find_7z()


class VerifyPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.dll = self.tmp / "mxl2012-core.dll"
        self.dll.write_bytes(b"MZ..." + pr.plugin_version().encode() + b"\0...")
        data = self.tmp / "data"
        files = {"global/excel/armor.txt": b"Median armor\n", "global/dataversionbuild.txt": b"93847",
                 **{f"local/lng/{rel % 'mxl2012'}": b"[]" for rel in vp.STRING_FILES}}
        for rel, body in files.items():
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_bytes(body)
        self.mod = self.tmp / "stage" / "mxl2012"
        pr.stage(self.mod, pr.plugin_version(), self.dll, self.tmp, data_from=data)

    def test_a_staged_package_is_a_player_mod_folder(self):
        self.assertEqual(vp.check_mod_folder(self.mod, pr.plugin_version()), [])

    def test_mod_folder_problems(self):
        (self.mod / "modinfo.json").write_text(json.dumps({"name": "mxl2012", "savepath": "mxl2012-s2/"}))
        (self.mod / "d2rloader" / "plugins" / "mxl2012-core.dll").write_bytes(b"MZ mxl2012-testharness.txt\0")
        (self.mod / "Hero.d2s").write_bytes(b"x")
        problems = vp.check_mod_folder(self.mod, "9.9.9")
        text = "\n".join(problems)
        for want in ("modinfo.json", "modVersion", "test harness", "PluginVersion", "Hero.d2s"):
            self.assertIn(want, text)

    def test_archive_paths_must_stay_in_the_mod_folder(self):
        self.assertEqual(vp.bad_archive_paths(["mxl2012", "mxl2012/modinfo.json"]), [])
        self.assertEqual(vp.bad_archive_paths(["mxl2012/../x", "other/a", "C:/x", "/abs"]),
                         ["mxl2012/../x", "other/a", "C:/x", "/abs"])

    def test_scratch_must_be_inside_the_project(self):
        self.assertTrue(vp.allowed_scratch(vp.install_mod.ROOT / "work" / "verify"))
        self.assertFalse(vp.allowed_scratch(vp.install_mod.ROOT))
        self.assertFalse(vp.allowed_scratch(Path(vp.install_mod.ROOT.anchor) / "elsewhere"))

    def test_reference_comparison(self):
        ref = self.tmp / "ref" / "mxl2012"
        shutil.copytree(self.mod, ref)
        (ref / "d2rloader" / "metadata.json").write_text("{dev}")  # differs by design
        extract = self.tmp / "extract"
        (extract / "data" / "global" / "excel").mkdir(parents=True)
        (extract / "data" / "global" / "excel" / "sounds.txt").write_bytes(b"vanilla\n")
        (ref / "mxl2012.mpq" / "data" / "global" / "excel" / "sounds.txt").write_bytes(b"vanilla\n")  # left out: D2R's own
        problems, stats = vp.compare_reference(self.mod, ref, extract, self.tmp / "no-cache")
        self.assertEqual(problems, [])
        self.assertEqual(stats["blizzardCopiesLeftOut"], 1)
        (ref / "mxl2012.mpq" / "data" / "global" / "excel" / "levels.txt").write_bytes(b"ours")  # missing from the package
        (ref / "mxl2012.mpq" / "data" / "global" / "excel" / "armor.txt").write_bytes(b"other")
        (self.mod / "extra.txt").write_bytes(b"x")
        problems, _ = vp.compare_reference(self.mod, ref, extract, self.tmp / "no-cache")
        self.assertEqual(len(problems), 3, problems)

    @unittest.skipUnless(SEVEN, "no 7-Zip on this machine")
    def test_manifest_check_against_a_real_7z(self):
        out = self.tmp / "dist"
        out.mkdir()
        seven = out / "D2R-XL-2012-1.2.3.7z"
        pr.write_7z(self.mod, seven)
        man = pr.manifest("1.2.3", pr.file_list(self.mod), seven, True, pr.empty_dirs(self.mod))
        sums = out / "SHA256SUMS"
        sums.write_text(f"{pr.sha256(seven)}  {seven.name}\n")
        unpacked = self.tmp / "unpacked"
        __import__("subprocess").run([SEVEN, "x", "-y", f"-o{unpacked}", str(seven)], check=True, capture_output=True)
        self.assertEqual(vp.archive_paths(SEVEN, seven) and vp.bad_archive_paths(vp.archive_paths(SEVEN, seven)), [])
        self.assertEqual(vp.check_manifest(unpacked / "mxl2012", man, seven, sums), [])
        man["files"] = man["files"][1:]
        sums.write_text(f"{'0' * 64}  {seven.name}\n")
        problems = vp.check_manifest(unpacked / "mxl2012", man, seven, sums)
        self.assertTrue(any("does not list" in p for p in problems), problems)
        self.assertTrue(any("SHA256SUMS" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
