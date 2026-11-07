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


def clear_fonts(data: Path) -> None:
    """A valid clear legacy font set (synthetic glyphs): a full package refuses data without it."""
    import struct
    import dc6
    import legacy_fonts
    tbl = b"Woo!" + struct.pack("<IHBB", 1, 256, 11, 1)
    tbl += b"".join(struct.pack("<HBBBBHHI", i, 0, 1, 1, 1, 0, i, 0) for i in range(256))
    picture = dc6.build_dc6([(1, 1, 0, 0, bytes((1, 1, 0x80)))] * 256)
    folder = data / legacy_fonts.CLEAR
    folder.mkdir(parents=True, exist_ok=True)
    for name in legacy_fonts.SHIPPED:
        (folder / (name + ".tbl")).write_bytes(tbl)
        (folder / (name + ".dc6")).write_bytes(picture)
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
        self.assertIn("[d2rcore.stash]\nadd_shared_tabs = 2", toml)  # bugs.md #535
        self.assertIn("[d2rcore.player]\nalways_enable_rotw_legacy_graphics_keybind = true", toml)  # bugs.md #498
        self.assertIn("[d2rcore.items]\nitem_stat_ranges = true", toml)  # bugs.md #528
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

    def legacy169_src(self, commit=None):
        """A fake build/legacy169-src: the default toml and the PINNED_COMMIT tools/build_legacy169.ps1 writes."""
        src = self.tmp / "legacy169-src"
        src.mkdir(exist_ok=True)
        (src / "legacy169.toml").write_text("[legacy169]\nenabled = true\nreset_screen = true\n", encoding="utf-8")
        (src / "PINNED_COMMIT").write_text((commit or pr.legacy169_commit()) + "\n", encoding="ascii")
        dll = self.tmp / "legacy169.dll"
        dll.write_bytes(b"MZ...legacy169\0...0.1.1\0...")
        return src, dll

    def test_legacy169_is_pinned(self):
        self.assertRegex(pr.legacy169_commit(), r"^[0-9a-f]{40}$")
        self.assertEqual(pr.LEGACY169["dll"], "d2rloader/plugins/legacy169.dll")
        self.assertEqual(pr.LEGACY169["config"], "d2rloader/config/legacy169.toml")

    def test_legacy169_staged_with_its_config_preserved(self):
        mod = self.staged()
        src, dll = self.legacy169_src()
        pr.stage_legacy169(mod, dll, src)
        self.assertEqual((mod / pr.LEGACY169["dll"]).read_bytes(), dll.read_bytes())
        self.assertIn("enabled = true", (mod / pr.LEGACY169["config"]).read_text())
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod))
        self.assertEqual(m["preserve"], ["d2rloader/config/d2rloader.toml", "d2rloader/config/mxl2012-core.toml", "d2rloader/config/legacy169.toml"])
        self.assertTrue(set(m["preserve"]) <= {f["path"] for f in files})
        self.assertEqual(pr.preserve_list(self.staged()), pr.PRESERVE)  # a package without it: only our own two configs

    def test_legacy169_source_of_another_commit_is_refused(self):
        mod = self.staged()
        src, dll = self.legacy169_src("0" * 40)
        with self.assertRaises(SystemExit):
            pr.stage_legacy169(mod, dll, src)
        self.assertFalse((mod / pr.LEGACY169["dll"]).exists())

    def buffhud_src(self, commit=None):
        """A fake build/buffhud-src (tools/build_buffhud.ps1's export) and a fork DLL with its MPQ next to it."""
        src = self.tmp / "buffhud-src"
        (src / "external" / "PluginSDK").mkdir(parents=True, exist_ok=True)
        (src / "buff-panel.toml").write_text("[buff_panel]\nenabled = true\n", encoding="utf-8")
        (src / "LICENSE").write_text("MIT License\n\nCopyright (c) 2026 \u0141ukasz\n", encoding="utf-8")
        (src / "external" / "PluginSDK" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
        (src / "PINNED_COMMIT").write_text((commit or pr.buffhud_commit()) + "\n", encoding="ascii")
        dll = self.tmp / "d2rl-buff-panel.dll"
        dll.write_bytes(b"MZ...buff-panel\0...1.1.0\0...[buff_panel]\nenabled = true\n")
        dll.with_suffix(".mpq").write_bytes(b"MPQ\x1a...")
        return src, dll

    def test_buffhud_is_pinned(self):
        self.assertRegex(pr.buffhud_commit(), r"^[0-9a-f]{40}$")
        self.assertEqual(pr.BUFFHUD["dll"], "d2rloader/plugins/d2rl-buff-panel.dll")
        self.assertEqual(pr.BUFFHUD["mpq"], "d2rloader/plugins/d2rl-buff-panel.mpq")
        self.assertEqual(pr.BUFFHUD["config"], "d2rloader/config/buff-panel.toml")

    def test_buffhud_staged_with_licences_and_its_config_preserved(self):
        mod = self.staged()
        src, dll = self.buffhud_src()
        pr.stage_buffhud(mod, dll, src)
        self.assertEqual((mod / pr.BUFFHUD["dll"]).read_bytes(), dll.read_bytes())
        self.assertEqual((mod / pr.BUFFHUD["mpq"]).read_bytes(), dll.with_suffix(".mpq").read_bytes())
        self.assertIn("\u0141ukasz", (mod / pr.BUFFHUD["licence"]).read_text(encoding="utf-8"))
        self.assertTrue((mod / pr.BUFFHUD["sdk_licence"]).is_file())
        self.assertIn("enabled = true", (mod / pr.BUFFHUD["config"]).read_text())
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, True))
        self.assertEqual(m["preserve"], ["d2rloader/config/d2rloader.toml", "d2rloader/config/mxl2012-core.toml", "d2rloader/config/buff-panel.toml"])
        paths = {f["path"] for f in files}
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["author"], entry["commit"]), ("Buff HUD", "Lukaszpg", pr.buffhud_commit()))
        self.assertTrue(set(entry["files"]) <= paths, set(entry["files"]) - paths)
        self.assertEqual([b["name"] for b in pr.bundled_plugins(True, True)], ["D2R Legacy 16:9", "Buff HUD"])

    def test_buffhud_source_of_another_commit_is_refused(self):
        mod = self.staged()
        src, dll = self.buffhud_src("0" * 40)
        with self.assertRaises(SystemExit):
            pr.stage_buffhud(mod, dll, src)
        self.assertFalse((mod / pr.BUFFHUD["dll"]).exists())

    def test_buffhud_builds_that_are_not_ours_are_refused(self):
        _src, dll = self.buffhud_src()
        self.assertEqual(pr.check_buffhud(dll), [])
        for body, words in ((b"MZ buff-panel\0 1.1.0\0", "not our fork"), (b"MZ buff-panel\0 1.0.11\0 [buff_panel]", "version")):
            dll.write_bytes(body)
            problems = pr.check_buffhud(dll)
            self.assertTrue(problems and any(words in p for p in problems), (body, problems))
        dll.write_bytes(b"MZ buff-panel\0 1.1.0\0 [buff_panel]")
        dll.with_suffix(".mpq").write_bytes(b"PK")
        self.assertTrue(any("not a packed MPQ" in p for p in pr.check_buffhud(dll)))
        dll.with_suffix(".mpq").unlink()
        self.assertTrue(any("d2rl-buff-panel.mpq" in p for p in pr.check_buffhud(dll)))

    def beltrefill_src(self, commit=None, patches=None):
        """A fake build/beltrefill-src (tools/build_beltrefill.ps1's export: PINNED_COMMIT and PATCHES) and a DLL."""
        src = self.tmp / "beltrefill-src"
        src.mkdir(exist_ok=True)
        (src / "PINNED_COMMIT").write_text((commit or pr.beltrefill_commit()) + "\n", encoding="ascii")
        lines = pr.beltrefill_patches() if patches is None else patches
        (src / "PATCHES").write_text("".join(ln + "\r\n" for ln in lines), encoding="ascii")
        dll = self.tmp / "d2rl-auto-belt-refill.dll"
        dll.write_bytes(b"MZ...auto-belt-refill\0...Auto Belt Refill\0...0.35.9\0...")
        return src, dll

    def test_beltrefill_is_pinned_with_our_patches(self):
        self.assertRegex(pr.beltrefill_commit(), r"^[0-9a-f]{40}$")
        self.assertEqual(pr.BELTREFILL["dll"], "d2rloader/plugins/d2rl-auto-belt-refill.dll")
        self.assertEqual(pr.BELTREFILL["config"], "d2rloader/config/auto-belt-refill.toml")
        names = [ln.split("  ")[1] for ln in pr.beltrefill_patches()]
        self.assertEqual(names, ["0001-pluginsdk-1.3.1.patch", "0002-mxl2012-belt-rows.patch",
                                 "0003-mxl2012-match-first-slot.patch"])

    def test_beltrefill_config_matches_the_first_slot(self):
        import tomllib
        text = (pr.BELTREFILL_OURS / "auto-belt-refill.toml").read_text("utf-8")
        cfg = tomllib.loads(text)
        g = cfg["general"]
        self.assertEqual((g["enabled"], g["fill_key"], g["snapshot_key"], g["auto_refill"], g["debug_logs"],
                          g["match_first_slot"], g["belt_counts"]), (True, "", "", True, False, True, True))
        # no fixed columns: every column follows its first slot
        self.assertEqual([k for k in cfg if k.startswith("column")], [])
        # the elixirs and the Goodberry (#541) are never refilled
        elixirs = [f"ey{n}" for n in range(1, 10)] + ["eo7", "eo8", "eo9", "et1"] + [f"0g{n}" for n in range(9)]
        self.assertEqual(sorted(g["never_refill"]), sorted(elixirs + ["b@b"]))
        # the plugin's parser reads one line per value
        self.assertEqual([ln for ln in text.splitlines() if ln.startswith("never_refill")][0].count('"'), 2 * 23)

    def test_beltrefill_staged_with_its_config_preserved(self):
        mod = self.staged()
        src, dll = self.beltrefill_src()
        pr.stage_beltrefill(mod, dll, src)
        self.assertEqual((mod / pr.BELTREFILL["dll"]).read_bytes(), dll.read_bytes())
        self.assertIn("match_first_slot = true", (mod / pr.BELTREFILL["config"]).read_text("utf-8"))
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, True))
        self.assertEqual(m["preserve"], ["d2rloader/config/d2rloader.toml", "d2rloader/config/mxl2012-core.toml",
                                         "d2rloader/config/auto-belt-refill.toml"])
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["author"], entry["repo"], entry["commit"]),
                         ("Auto Belt Refill", "jaycachou-svg", "https://github.com/jaycachou-svg/auto-belt-refill",
                          pr.beltrefill_commit()))
        self.assertEqual(entry["patches"], pr.beltrefill_patches())
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})
        self.assertEqual([b["name"] for b in pr.bundled_plugins(True, True, True)],
                         ["D2R Legacy 16:9", "Buff HUD", "Auto Belt Refill"])

    def test_beltrefill_source_of_another_commit_or_patch_set_is_refused(self):
        mod = self.staged()
        for commit, patches in (("0" * 40, None), (None, pr.beltrefill_patches()[:1]), (None, ["0" * 64 + "  0001-x.patch"])):
            src, dll = self.beltrefill_src(commit, patches)
            with self.assertRaises(SystemExit):
                pr.stage_beltrefill(mod, dll, src)
            self.assertFalse((mod / pr.BELTREFILL["dll"]).exists())

    def test_beltrefill_builds_that_are_not_ours_are_refused(self):
        _src, dll = self.beltrefill_src()
        self.assertEqual(pr.check_beltrefill(dll), [])
        dll.write_bytes(b"MZ auto-belt-refill\0 0.35.8\0")
        self.assertTrue(any("version 0.35.9" in p for p in pr.check_beltrefill(dll)))
        with mock.patch.object(pr, "BELTREFILL_AUTHOR_DLL", pr.sha256(dll)):
            self.assertTrue(any("author's prebuilt" in p for p in pr.check_beltrefill(dll)))

    def test_legacy169_test_builds_are_refused(self):
        _src, dll = self.legacy169_src()
        self.assertEqual(pr.check_legacy169(dll), [])
        for body, words in ((b"MZ legacy169\0 0.1.1-test\0", "test build"), (b"MZ legacy169-testharness.txt 0.1.1\0", "test build"),
                            (b"MZ legacy169\0 0.0.9\0", "version")):
            dll.write_bytes(body)
            problems = pr.check_legacy169(dll)
            self.assertTrue(problems and any(words in p for p in problems), (body, problems))
        self.assertTrue(pr.FORBIDDEN.search("d2rloader/plugins/legacy169-testharness.txt"))

    def test_d2rloader_block_is_installable(self):
        self.assertEqual(pr.loader_problems(pr.D2RLOADER), [])
        self.assertEqual(pr.D2RLOADER["url"], "https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip")
        good = dict(pr.D2RLOADER)
        for field, value, words in (("version", "", "version"), ("url", "", "https"), ("sha256", "", "sha256"),
                                    ("sha256", "g" * 64, "sha256"), ("size", 0, "size"), ("size", "47652455", "size"),
                                    ("url", "http://d2rloader.net/download/D2RLoader-1.3.1-beta.zip", "https"),
                                    ("url", "https://example.com/D2RLoader-1.3.1-beta.zip", "d2rloader.net"),
                                    ("url", "https://evild2rloader.net/D2RLoader.zip", "d2rloader.net"),
                                    ("url", "https://d2rloader.net/download.html", ".zip")):
            problems = pr.loader_problems(dict(good, **{field: value}))
            self.assertTrue(problems and any(words in p for p in problems), (field, value, problems))
        missing = {k: v for k, v in good.items() if k != "sha256"}
        self.assertIn("d2rloader.sha256 is not 64 hex digits", pr.loader_problems(missing))

    def test_manifest_refuses_a_broken_d2rloader_block(self):
        mod = self.staged()
        with mock.patch.object(pr, "D2RLOADER", dict(pr.D2RLOADER, sha256="")):
            with self.assertRaisesRegex(ValueError, "d2rloader.sha256"):
                pr.manifest("1.2.3", pr.file_list(mod), self.fake_7z(mod), True)

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
        clear_fonts(data)
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
                            "--data-from", str(data), "--out", str(out), "--no-bundled"], capture_output=True,
                           text=True, env=self.baseline_env())
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
        clear_fonts(data)
        out = self.tmp / "dist"
        args = [sys.executable, "-I", str(HERE / "package_release.py"), "--plugin", str(self.dll), "--data-from", str(data),
                "--out", str(out), "--no-bundled"]
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
