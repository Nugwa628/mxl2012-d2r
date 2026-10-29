"""tools/package_release.py on a small fake mod folder; no game files, no plugin build."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import package_release as pr


HERE = Path(__file__).resolve().parent
SEVEN = pr.find_7z()


class PackageReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.dll = self.tmp / "mxl2012-core.dll"
        self.dll.write_bytes(b"MZ..." + pr.plugin_version().encode() + b"\0...")
        self.mod = self.tmp / "stage" / "mxl2012"

    def staged(self, files=None):
        data = self.tmp / "data"
        for rel, body in (files or {"global/excel/armor.txt": b"Median armor\n"}).items():
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_bytes(body)
        pr.stage(self.mod, "1.2.3", self.dll, self.tmp, data_from=data)
        return self.mod

    def test_layout_matches_install_mod(self):
        mod = self.staged()
        self.assertEqual(json.loads((mod / "mxl2012.mpq" / "modinfo.json").read_text()), {"name": "mxl2012", "savepath": "mxl2012/"})
        meta = json.loads((mod / "d2rloader" / "metadata.json").read_text())
        self.assertEqual(meta["namespace"], "mxl2012")
        self.assertEqual(meta["metadata"]["modVersion"], "1.2.3")
        self.assertEqual(meta["metadata"]["website"], "https://github.com/Nugwa628/mxl2012-d2r")
        toml = (mod / "d2rloader" / "config" / "d2rloader.toml").read_text()
        self.assertIn('[d2rcore.save_format]\nmode = "extended"', toml)
        self.assertNotIn("add_shared_tabs", toml)
        self.assertIn("[d2rcore.player]\nalways_enable_rotw_legacy_graphics_keybind = true", toml)  # bugs.md #498
        self.assertTrue((mod / "d2rloader" / "plugins" / "mxl2012-core.dll").is_file())
        self.assertTrue((mod / "d2rloader" / "patches").is_dir())

    def baseline_env(self):
        """An environment whose MXL_D2R_EXTRACT is a small fake D2R baseline (a package with data needs one)."""
        ext = self.tmp / "d2r-extract"
        (ext / "data" / "global" / "excel").mkdir(parents=True, exist_ok=True)
        (ext / "data" / "global" / "excel" / "sounds.txt").write_bytes(b"vanilla\n")
        return {**os.environ, "MXL_D2R_EXTRACT": str(ext), "MXL_D2R_CACHE": str(self.tmp / "no-cache")}

    def fake_7z(self, mod):
        out = self.tmp / "D2R-XL-2012-1.2.3.7z"
        out.write_bytes(b"7z fake")
        return out

    def test_manifest_lists_every_file(self):
        mod = self.staged()
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod))
        self.assertEqual(m["schemaVersion"], 2)
        self.assertNotIn("zip", m)
        self.assertEqual(m["d2r"]["build"], "93847")
        self.assertEqual(m["d2rloader"]["version"], "1.3.1-beta")
        self.assertEqual(len(m["d2rloader"]["sha256"]), 64)
        paths = [f["path"] for f in files]
        self.assertEqual(paths, sorted(paths))
        self.assertIn("mxl2012.mpq/data/global/excel/armor.txt", paths)
        self.assertIn("d2rloader/plugins/mxl2012-core.dll", paths)
        armor = next(f for f in files if f["path"].endswith("armor.txt"))
        self.assertEqual(armor["size"], len(b"Median armor\n"))
        self.assertEqual(m["fileCount"], len(files))
        self.assertTrue(set(m["preserve"]) <= set(paths))
        self.assertEqual(m["emptyDirs"], ["d2rloader/patches"])

    def test_manifest_archive_entry(self):
        mod = self.staged()
        seven = self.fake_7z(mod)
        m = pr.manifest("1.2.3", pr.file_list(mod), seven, True)
        self.assertEqual(m["archive"], {"format": "7z", "name": "D2R-XL-2012-1.2.3.7z", "size": 7, "sha256": pr.sha256(seven)})

    def test_no_7zip_is_an_error(self):
        mod = self.staged()
        out = self.tmp / "r.7z"
        with mock.patch.object(pr, "find_7z", return_value=None):
            with self.assertRaises(RuntimeError) as e:
                pr.write_7z(mod, out)
        self.assertIn("no 7-Zip found", str(e.exception))
        self.assertFalse(out.exists())

    def test_main_stops_early_without_7zip(self):
        out = self.tmp / "dist"
        argv = ["package_release.py", "--no-data", "--plugin", str(self.dll), "--version", "1.2.3", "--out", str(out)]
        code = (f"import sys; sys.path.insert(0, {str(HERE)!r}); import package_release as pr; pr.find_7z = lambda: None; "
                f"sys.argv = {argv!r}; sys.exit(pr.main())")
        r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("no 7-Zip found", r.stdout)
        self.assertFalse(out.exists(), "nothing staged")

    def test_find_7z_looks_in_program_files_then_path(self):
        pf = self.tmp / "pf"
        (pf / "7-Zip").mkdir(parents=True)
        (pf / "7-Zip" / "7z.exe").write_bytes(b"")
        none = {"ProgramFiles": str(self.tmp / "none"), "ProgramFiles(x86)": ""}
        with mock.patch.dict("os.environ", {"ProgramFiles": str(pf)}), mock.patch.object(pr.shutil, "which", return_value="x"):
            self.assertEqual(pr.find_7z(), str(pf / "7-Zip" / "7z.exe"))
        with mock.patch.dict("os.environ", none), \
                mock.patch.object(pr.shutil, "which", side_effect=lambda n: "/bin/7zz" if n == "7zz" else None):
            self.assertEqual(pr.find_7z(), "/bin/7zz")
        with mock.patch.dict("os.environ", none), mock.patch.object(pr.shutil, "which", return_value=None):
            self.assertIsNone(pr.find_7z())

    def test_failing_7zip_raises_and_leaves_nothing(self):
        mod = self.staged()
        out = self.tmp / "r.7z"
        fake = self.tmp / "fail.py"
        fake.write_text("import sys; print('boom'); sys.exit(2)")
        if sys.platform == "win32":
            script = self.tmp / "fail.cmd"
            script.write_text(f'@"{sys.executable}" "{fake}"\r\n')
        else:
            script = self.tmp / "fail.sh"
            script.write_text(f'#!/bin/sh\n"{sys.executable}" "{fake}"\n')
            script.chmod(0o755)
        with self.assertRaises(RuntimeError):
            pr.write_7z(mod, out, str(script))
        self.assertFalse(out.exists())

    @unittest.skipUnless(SEVEN, "no 7-Zip on this machine")
    def test_real_7z_holds_the_mod_folder_and_is_reproducible(self):
        mod = self.staged({"global/excel/armor.txt": b"Median armor\n" * 5000, "global/ui/a.json": b"{}"})
        a, b = self.tmp / "a.7z", self.tmp / "b.7z"
        pr.write_7z(mod, a)
        for p in mod.rglob("*"):  # other mtimes: write_7z sets them again, the bytes stay
            os.utime(p, (1.5e9, 1.5e9))
        pr.write_7z(mod, b)
        self.assertEqual(pr.sha256(a), pr.sha256(b))
        listing = subprocess.run([SEVEN, "l", "-slt", str(a)], capture_output=True, text=True).stdout
        self.assertIn("Method = LZMA2", listing)
        self.assertIn("Solid = +", listing)
        paths = {ln[7:].replace("\\", "/") for ln in listing.splitlines() if ln.startswith("Path = ")} - {a.as_posix()}
        self.assertTrue(all(n == "mxl2012" or n.startswith("mxl2012/") for n in paths), paths)
        out = self.tmp / "unpacked"
        subprocess.run([SEVEN, "x", "-y", f"-o{out}", str(a)], check=True, capture_output=True)
        self.assertEqual(pr.file_list(out / "mxl2012"), pr.file_list(mod))
        self.assertTrue((out / "mxl2012" / "d2rloader" / "patches").is_dir())

    @unittest.skipUnless(SEVEN, "no 7-Zip on this machine")
    def test_main_writes_the_7z_only(self):
        data = self.tmp / "d"
        (data / "global" / "excel").mkdir(parents=True)
        (data / "global" / "excel" / "armor.txt").write_bytes(b"Median armor\n" * 1000)
        out = self.tmp / "dist"
        out.mkdir()
        (out / "D2R-XL-2012-1.2.2.zip").write_bytes(b"an earlier packager's zip")
        v = pr.plugin_version()
        # a player release whose --version is not PluginVersion is refused before anything is written
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--plugin", str(self.dll),
                            "--version", "99.0.0", "--data-from", str(data), "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("PluginVersion", r.stdout)
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--plugin", str(self.dll),
                            "--data-from", str(data), "--out", str(out)], capture_output=True, text=True,
                           env=self.baseline_env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        seven = out / f"D2R-XL-2012-{v}.7z"
        self.assertEqual(sorted(p.name for p in out.iterdir()),
                         [f"D2R-XL-2012-{v}.7z", f"RELEASE_NOTES-{v}.md", "SHA256SUMS", "release-manifest.json"])
        man = json.loads((out / "release-manifest.json").read_text())
        self.assertEqual(man["schemaVersion"], 2)
        self.assertNotIn("zip", man)
        self.assertEqual(man["archive"], {"format": "7z", "name": seven.name, "size": seven.stat().st_size,
                                          "sha256": pr.sha256(seven)})
        sums = (out / "SHA256SUMS").read_text().splitlines()
        self.assertIn(f"{pr.sha256(seven)}  {seven.name}", sums)
        self.assertEqual(len(sums), 3)
        notes = (out / f"RELEASE_NOTES-{v}.md").read_text()
        self.assertIn(f"`D2R-XL-2012-{v}.7z`", notes)
        self.assertIn("Windows 11 opens .7z files", notes)
        self.assertNotIn("Unzip", notes)
        self.assertIn("as 7z", r.stdout)

    @unittest.skipUnless(SEVEN, "no 7-Zip on this machine")
    def test_no_data_package_is_a_nodata_7z(self):
        out = self.tmp / "dist"
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--no-data", "--plugin", str(self.dll),
                            "--version", "1.2.3", "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name for p in out.glob("*.7z")), ["D2R-XL-2012-1.2.3-nodata.7z"])
        man = json.loads((out / "release-manifest.json").read_text())
        self.assertFalse(man["complete"])
        self.assertEqual(man["archive"]["name"], "D2R-XL-2012-1.2.3-nodata.7z")

    @unittest.skipUnless(SEVEN, "no 7-Zip on this machine")
    def test_notes_template_and_missing_baseline(self):
        data = self.tmp / "d"
        (data / "global" / "excel").mkdir(parents=True)
        (data / "global" / "excel" / "armor.txt").write_bytes(b"Median armor\n")
        out = self.tmp / "dist"
        args = [sys.executable, "-I", str(HERE / "package_release.py"), "--plugin", str(self.dll), "--data-from", str(data),
                "--out", str(out)]
        env = {**os.environ, "MXL_D2R_EXTRACT": str(self.tmp / "nothing-here")}
        r = subprocess.run(args, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("baseline", r.stdout)
        self.assertFalse((out / "stage").exists())
        r = subprocess.run(args + ["--notes", str(HERE / "data" / "release_notes_alpha.md")], capture_output=True, text=True,
                           env=self.baseline_env())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        v = pr.plugin_version()
        notes = (out / f"RELEASE_NOTES-{v}.md").read_text("utf-8")
        self.assertIn(f"# D2R-XL 2012 {v} (alpha)", notes)
        self.assertIn(f"`D2R-XL-2012-{v}.7z`", notes)
        self.assertIn("build 93847", notes)
        self.assertIn("D2RLoader 1.3.1-beta", notes)
        self.assertIn("mods\\mxl2012/", notes)
        self.assertNotIn("{", notes)
        self.assertNotIn("Downloader", notes)

    def test_test_and_player_files_are_refused(self):
        mod = self.staged({"global/excel/armor.txt": b"x", "global/x.txt": b"y"})
        self.assertEqual(pr.forbidden_files(mod), [])
        for rel in ("d2rloader/plugins/mxl2012-testharness.txt", "d2rloader/plugins/mxl2012-core-off.txt", "Hero.d2s",
                    "d2rloader/logs/mxl2012-core.log", "d2rloader/config/input-bindings.toml", "Hero.map", "Hero.d2rl", "Hero.ctl"):
            (mod / rel).parent.mkdir(parents=True, exist_ok=True)
            (mod / rel).write_text("x")
        self.assertEqual(len(pr.forbidden_files(mod)), 8)

    def test_byte_copies_of_d2r_files_are_left_out(self):
        mod = self.staged({"global/excel/armor.txt": b"Median armor\n", "global/excel/sounds.txt": b"vanilla\n",
                           "global/dataversionbuild.txt": b"93847"})
        extract = self.tmp / "extract"
        for rel, body in {"global/excel/sounds.txt": b"vanilla\n", "global/excel/armor.txt": b"vanilla armor\n",
                          "global/dataversionbuild.txt": b"93847"}.items():
            (extract / "data" / rel).parent.mkdir(parents=True, exist_ok=True)
            (extract / "data" / rel).write_bytes(body)
        self.assertEqual(pr.drop_blizzard_copies(mod, extract, self.tmp / "no-cache"), 1)
        data = mod / "mxl2012.mpq" / "data"
        self.assertFalse((data / "global/excel/sounds.txt").exists())
        self.assertTrue((data / "global/excel/armor.txt").exists())
        self.assertTrue((data / "global/dataversionbuild.txt").exists())

    def test_byte_copies_of_cached_d2r_files_are_left_out(self):
        mod = self.staged({"global/animdata.d2": b"vanilla animdata", "hd/missiles/missiles.json": b"{merged}",
                           "global/tiles/town/a.ds1": b"vanilla ds1"})
        extract, cache = self.tmp / "extract", self.tmp / "cache"
        (extract / "data").mkdir(parents=True)
        for rel, body in {"global/animdata.d2": b"vanilla animdata", "hd/missiles/missiles.json": b"{vanilla}"}.items():
            (cache / "data" / rel).parent.mkdir(parents=True, exist_ok=True)
            (cache / "data" / rel).write_bytes(body)
        (extract / "data" / "global/tiles/town").mkdir(parents=True)
        (extract / "data" / "global/tiles/town/a.ds1").write_bytes(b"vanilla ds1")
        self.assertEqual(pr.drop_blizzard_copies(mod, extract, cache), 2)
        data = mod / "mxl2012.mpq" / "data"
        self.assertFalse((data / "global/tiles").exists(), "emptied folders go too")
        self.assertEqual(pr.empty_dirs(mod), ["d2rloader/patches"])
        self.assertFalse((data / "global/animdata.d2").exists())
        self.assertTrue((data / "hd/missiles/missiles.json").exists())
        self.assertEqual(pr.baselines(self.tmp / "none", self.tmp / "none2"), [])

    def test_harness_plugin_is_refused(self):
        self.assertEqual(pr.check_release_plugin(self.dll, pr.plugin_version()), [])
        dev = self.tmp / "dev.dll"
        dev.write_bytes(self.dll.read_bytes() + b"mxl2012-testharness.txt\0")
        self.assertEqual(len(pr.check_release_plugin(dev, pr.plugin_version())), 1)
        self.assertEqual(len(pr.check_release_plugin(self.dll, "9.9.9")), 1)


if __name__ == "__main__":
    unittest.main()
