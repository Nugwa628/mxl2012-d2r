"""tools/package_release.py on a small fake mod folder; no game files, no plugin build."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import json
import os
import shutil
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

    def test_invtabs_cli_conflict_is_early(self):
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--charm-inventory", "charminv", "--invtabs", "missing.dll"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("invtabs and CharmInv cannot be staged together", r.stderr)

    def test_invtabs_opt_in_paths_and_conflict(self):
        mod = self.staged()
        self.assertFalse((mod / pr.INVTABS["dll"]).exists())
        dll = self.tmp / "invtabs.dll"
        dll.write_bytes(b"MZ invtabs\0")
        pr.stage_invtabs(mod, dll)
        self.assertEqual((mod / pr.INVTABS["dll"]).read_bytes(), dll.read_bytes())
        self.assertEqual((mod / pr.INVTABS["config"]).read_bytes(), (pr.ROOT / "invtabs/invtabs.toml").read_bytes())
        self.assertIn(pr.INVTABS["config"], pr.preserve_list(mod))
        with self.assertRaisesRegex(SystemExit, "invtabs and CharmInv cannot be staged together"):
            pr.stage_charminv(mod, self.tmp)
        with self.assertRaisesRegex(SystemExit, "invtabs and CharmInv cannot be staged together"):
            pr.stage(mod, "1", self.dll, self.tmp, no_data=True, invtabs=dll, charminv=self.tmp)
        self.assertTrue((mod / pr.INVTABS["dll"]).exists())  # rejected before clearing stage
        (mod / pr.INVTABS["dll"]).unlink()
        (mod / pr.CHARMINV["dll"]).write_bytes(b"MZ")
        with self.assertRaisesRegex(SystemExit, "invtabs and CharmInv cannot be staged together"):
            pr.stage_invtabs(mod, dll)

    def test_charm_inventory_switch_off_leaves_the_package_as_it_was(self):
        self.assertEqual(pr.CHARM_INVENTORY, "invtabs")  # the default since the release after 0.1.19; CharmInv by request
        mod = self.staged()
        self.assertFalse(any((mod / pr.INVTABS[k]).exists() for k in ("dll", "config")))
        self.assertFalse(any((mod / f"{pr.NAME}.mpq" / "data" / rel).exists() for rel in pr.INVTABS_DATA))
        self.assertNotIn(pr.INVTABS["config"], pr.preserve_list(mod))

    def test_charm_inventory_switch_on_ships_invtabs_and_no_charminv(self):
        dll = self.tmp / "invtabs.dll"
        dll.write_bytes(b"MZ invtabs\0")
        data = self.tmp / "data"
        for rel in ("global/excel/armor.txt",) + pr.INVTABS_DATA:
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_bytes(b"x")
        pr.stage(self.mod, "1.2.3", self.dll, self.tmp, data_from=data, invtabs=dll)
        for k in ("dll", "config"):
            self.assertTrue((self.mod / pr.INVTABS[k]).is_file())
        for rel in pr.INVTABS_DATA:
            self.assertTrue((self.mod / f"{pr.NAME}.mpq" / "data" / rel).is_file(), rel)
        self.assertFalse(any((self.mod / pr.CHARMINV[k]).exists() for k in pr.CHARMINV_FILES))
        entry = pr.invtabs_entry()
        self.assertIn("wild-healer", entry["author"])
        self.assertEqual(entry["upstreamCommit"], "6722cc545f52a012460f5e9a825632a7f5e38eb5")
        self.assertEqual(entry["files"], [pr.INVTABS["dll"], pr.INVTABS["config"]])
        # the build's invtabs steps did not run: refused, naming the file
        (data / pr.INVTABS_DATA[0]).unlink()
        with self.assertRaisesRegex(SystemExit, "tabs.txt is missing"):
            pr.stage(self.mod, "1.2.3", self.dll, self.tmp, data_from=data, invtabs=dll)
        # a --no-data package (CI) has no data to check
        pr.stage(self.mod, "1.2.3", self.dll, self.tmp, no_data=True, invtabs=dll)
        self.assertTrue((self.mod / pr.INVTABS["dll"]).is_file())

    def test_data_built_for_the_other_charm_inventory_is_refused(self):
        import charm_inventory as ci
        import invtabs_legacy as il
        layout = '{"type": "Panel", "children": [\n    {"type": "ButtonWidget", "name": "close"}\n]}\n'
        dll = self.tmp / "invtabs.dll"
        dll.write_bytes(b"MZ invtabs\0")
        data = self.tmp / "data"
        for rel in ("global/excel/armor.txt",) + ci.INVTABS_DATA + ci.CLASSIC_INVENTORY:
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_text(il.add_button_to_layout(layout) if rel in ci.CLASSIC_INVENTORY else "x", "utf-8")
        pr.stage(self.mod, "1.2.3", self.dll, self.tmp, data_from=data, invtabs=dll)  # an invtabs build: fine with invtabs
        # ... and refused for a CharmInv package: invtabs' files and a Charms button that opens nothing
        with self.assertRaisesRegex(SystemExit, "built for invtabs.*opens nothing with CharmInv"):
            pr.stage(self.mod, "1.2.3", self.dll, self.tmp, data_from=data)
        # a CharmInv build (no button, CharmInv's tables) is refused for an invtabs package
        for rel in ci.CLASSIC_INVENTORY:
            (data / rel).write_text(layout, "utf-8")
        with self.assertRaisesRegex(SystemExit, "has no Charms button"):
            pr.stage(self.mod, "1.2.3", self.dll, self.tmp, data_from=data, invtabs=dll)
        for rel in ci.CLASSIC_INVENTORY:
            (data / rel).write_text(il.add_button_to_layout(layout), "utf-8")
        (data / ci.CHARMINV_DATA[0]).parent.mkdir(parents=True)
        (data / ci.CHARMINV_DATA[0]).write_text("x", "utf-8")
        with self.assertRaisesRegex(SystemExit, "is CharmInv's table"):
            pr.stage(self.mod, "1.2.3", self.dll, self.tmp, data_from=data, invtabs=dll)

    def test_charm_inventory_cli(self):
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--charm-inventory", "invtabs", "--charminv", "x"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("invtabs and CharmInv cannot be staged together", r.stderr)
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--charm-inventory", "other"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertEqual(pr.INVTABS_DLL, pr.ROOT / "build" / "invtabs" / "Release" / "invtabs.dll")

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

    def own_plugins(self):
        """--drawcap / --statbook of fake DLLs of this source's versions (not PE images, as self.dll): a package with data
        bundles them, and the tests must not depend on this checkout's build/ folder (an out-of-tree Linux build has none)."""
        dc, sb = self.tmp / "drawcap.dll", self.tmp / "statbook.dll"
        dc.write_bytes(b"MZ...Draw List Cap\0drawcap\0" + pr.drawcap_version().encode() + b"\0...")
        sb.write_bytes(b"MZ...Stat Book\0statbook\0" + pr.statbook_version().encode() + b"\0...")
        return ["--drawcap", str(dc), "--statbook", str(sb)]

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
        dll.write_bytes(b"MZ...legacy169\0...0.1.2\0...")
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
        dll.write_bytes(b"MZ...buff-panel\0..." + pr.BUFFHUD["version"].encode() + b"\0...[buff_panel]\nenabled = true\n")
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
        version = pr.BUFFHUD["version"].encode()
        for body, words in ((b"MZ buff-panel\0 " + version + b"\0", "not our fork"), (b"MZ buff-panel\0 1.0.11\0 [buff_panel]", "version")):
            dll.write_bytes(body)
            problems = pr.check_buffhud(dll)
            self.assertTrue(problems and any(words in p for p in problems), (body, problems))
        dll.write_bytes(b"MZ buff-panel\0 " + version + b"\0 [buff_panel]")
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
                                 "0003-mxl2012-match-first-slot.patch", "0004-mxl2012-count-signatures.patch",
                                 "0005-refill-natives-by-signature.patch", "0006-mxl2012-counts-as-hud-text.patch",
                                 "0007-mxl2012-column-counts-and-reserve.patch"])

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

    def controllerqol_src(self, commit=None, patches=None, profile=b"[aim.amazon]\n"):
        """A fake build/controllerqol-src (tools/build_controllerqol.ps1's export: PINNED_COMMIT, PATCHES, SKILL_PROFILE, the
        patched config, the licences), the skill seed it was built with and a DLL."""
        src = self.tmp / "controllerqol-src"
        (src / "plugins" / "controller-qol").mkdir(parents=True, exist_ok=True)
        (src / "PINNED_COMMIT").write_text((commit or pr.controllerqol_commit()) + "\n", encoding="ascii")
        lines = pr.controllerqol_patches() if patches is None else patches
        (src / "PATCHES").write_text("".join(ln + "\r\n" for ln in lines), encoding="ascii")
        seed = self.tmp / "mxl2012.overrides.toml"
        seed.write_bytes(profile)
        (src / "SKILL_PROFILE").write_text(pr.sha256(seed) + "\r\n", encoding="ascii")
        (src / "plugins" / "controller-qol" / "controller-qol-updates.toml").write_text("[qol]\nbelt_actions = false\n", "utf-8")
        (src / "LICENSE").write_text("Copyright (c) 2026 PyreFly\n", encoding="utf-8")
        (src / "PluginSDK-LICENSE").write_text("MIT License\n", encoding="utf-8")
        dll = self.tmp / "Controller QOL Updates.dll"
        dll.write_bytes(b"MZ...controller-qol-updates\0...1.3.1+rev.95\0...belt_actions = false\n")
        return src, dll, seed

    def test_controllerqol_is_pinned_with_our_patches(self):
        self.assertRegex(pr.controllerqol_commit(), r"^[0-9a-f]{40}$")
        self.assertEqual(pr.CONTROLLERQOL["dll"], "d2rloader/plugins/Controller QOL Updates.dll")
        self.assertEqual(pr.CONTROLLERQOL["config"], "d2rloader/config/controller-qol-updates.toml")
        names = [ln.split("  ")[1] for ln in pr.controllerqol_patches()]
        self.assertEqual(names, ["0001-mxl2012-belt-actions-switch.patch", "0002-mxl2012-median-orbs-tabs.patch",
                                 "0003-mxl2012-hooked-sound-entry.patch"])
        # the shipped config turns the belt actions off (Auto Belt Refill keeps the belt), and the patches keep the CRs of
        # PyreFly's CRLF sources (.gitattributes: -text)
        belt = (pr.CONTROLLERQOL_OURS / "0001-mxl2012-belt-actions-switch.patch").read_bytes()
        self.assertIn(b"\n+belt_actions = false\n", belt)
        self.assertIn(b"\r\n", (pr.CONTROLLERQOL_OURS / "0002-mxl2012-median-orbs-tabs.patch").read_bytes())

    def test_controllerqol_staged_with_its_config_preserved(self):
        mod = self.staged()
        src, dll, seed = self.controllerqol_src()
        pr.stage_controllerqol(mod, dll, seed, src)
        self.assertEqual((mod / pr.CONTROLLERQOL["dll"]).read_bytes(), dll.read_bytes())
        self.assertIn("belt_actions = false", (mod / pr.CONTROLLERQOL["config"]).read_text("utf-8"))
        self.assertIn("PyreFly", (mod / pr.CONTROLLERQOL["licence"]).read_text("utf-8"))
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, False, True))
        self.assertEqual(m["preserve"], ["d2rloader/config/d2rloader.toml", "d2rloader/config/mxl2012-core.toml",
                                         "d2rloader/config/controller-qol-updates.toml"])
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["author"], entry["repo"], entry["path"], entry["commit"]),
                         ("Controller QOL Updates", "PyreFly", "https://github.com/Pyre-Flies/D2R-Mods", "plugins/controller-qol",
                          pr.controllerqol_commit()))
        self.assertEqual(entry["patches"], pr.controllerqol_patches())
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})
        self.assertEqual([b["name"] for b in pr.bundled_plugins(True, True, True, True)],
                         ["D2R Legacy 16:9", "Buff HUD", "Auto Belt Refill", "Controller QOL Updates"])

    def charminv_files(self):
        """Fake CharmInv DLL / MPQ in a folder, and the pins of package_release.CHARMINV patched to their bytes."""
        folder = self.tmp / "charminv"
        folder.mkdir(exist_ok=True)
        (folder / "d2rl-charm-inv.dll").write_bytes(b"MZ charm-inv\0 1.0.1")
        (folder / "d2rl-charm-inv.mpq").write_bytes(b"MPQ\x1a charm-inv")
        pins = mock.patch.dict(pr.CHARMINV, {"sha256": {k: pr.sha256(folder / f"d2rl-charm-inv.{k}") for k in ("dll", "mpq")},
                                             "size": {k: (folder / f"d2rl-charm-inv.{k}").stat().st_size for k in ("dll", "mpq")}})
        pins.start()
        self.addCleanup(pins.stop)
        return folder

    def test_charminv_pins_the_authors_files(self):
        self.assertEqual(pr.CHARMINV["dll"], "d2rloader/plugins/d2rl-charm-inv.dll")
        self.assertEqual(pr.CHARMINV["mpq"], "d2rloader/plugins/d2rl-charm-inv.mpq")
        self.assertEqual(pr.CHARMINV["config"], "d2rloader/config/charm-inv.toml")  # <plugin id>.toml, id charm-inv
        self.assertEqual(pr.CHARMINV["sha256"], {"dll": "b14f6a0bd4c9df0af9c392ea97dc879ad3760592481517dbdb0983595145d88b",
                                                 "mpq": "e01163aac3b0d76c3cbdad56e19350692864b51484d9ad6dfbc41f28023fb0ac"})
        self.assertEqual((pr.CHARMINV["author"], pr.CHARMINV["version"]), ("Dimentio", "1.0.1"))
        readme = (pr.CHARMINV_OURS / "README.md").read_text("utf-8")
        for k in ("dll", "mpq"):
            self.assertIn(pr.CHARMINV["sha256"][k], readme)
        self.assertIn("redistributed with D2RLoader by the owner's decision (author: Dimentio, D2RLoader's author)", readme)
        # our config: charms grant their bonus from the inventory too (owner decision 2026-11-10); the button stays on
        cfg = (pr.CHARMINV_OURS / "charm-inv.toml").read_text("utf-8")
        self.assertIn("[charm-inv]", cfg)
        self.assertIn("\nallow_inventory_charms = true\n", cfg)
        self.assertIn("\ninject_inventory_button = true\n", cfg)
        self.assertIn('\ninactive_charm_tint = "yellow"\n', cfg)

    def test_charminv_staged_with_its_config_preserved(self):
        mod = self.staged()
        folder = self.charminv_files()
        self.assertEqual(pr.check_charminv(folder), [])
        pr.stage_charminv(mod, folder)
        for k in ("dll", "mpq"):
            self.assertEqual((mod / pr.CHARMINV[k]).read_bytes(), (folder / f"d2rl-charm-inv.{k}").read_bytes())
        self.assertIn("allow_inventory_charms = true", (mod / pr.CHARMINV["config"]).read_text("utf-8"))
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, False, False, True))
        self.assertEqual(m["preserve"], ["d2rloader/config/d2rloader.toml", "d2rloader/config/mxl2012-core.toml",
                                         "d2rloader/config/charm-inv.toml"])
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["author"], entry["version"], entry["source"]),
                         ("CharmInv", "Dimentio", "1.0.1", "https://d2rloader.net/hub/plugins/charm-inventory"))
        self.assertEqual(entry["sha256"], pr.CHARMINV["sha256"])
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})
        self.assertEqual([b["name"] for b in pr.bundled_plugins(True, True, True, True, True)],
                         ["D2R Legacy 16:9", "Buff HUD", "Auto Belt Refill", "Controller QOL Updates", "CharmInv"])

    def test_charminv_other_bytes_are_refused(self):
        mod = self.staged()
        folder = self.charminv_files()
        (folder / "d2rl-charm-inv.mpq").write_bytes(b"MPQ\x1a charm-inv 1.0.2")
        self.assertIn("is not CharmInv 1.0.1", "\n".join(pr.check_charminv(folder)))
        with self.assertRaises(SystemExit):
            pr.stage_charminv(mod, folder)
        self.assertFalse((mod / pr.CHARMINV["dll"]).exists())
        (folder / "d2rl-charm-inv.mpq").unlink()
        self.assertIn("no d2rl-charm-inv.mpq", "\n".join(pr.check_charminv(folder)))

    def test_charminv_dir_lookup(self):
        folder = self.charminv_files()
        self.assertEqual(pr.charminv_dir(folder), folder)  # --charminv wins as given
        with mock.patch.dict(os.environ, {"MXL_CHARMINV_DIR": str(folder)}):
            self.assertEqual(pr.charminv_dir(), folder)
        empty = self.tmp / "nothing"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"MXL_CHARMINV_DIR": str(empty)}), \
                mock.patch.object(pr, "CHARMINV_OURS", empty), \
                mock.patch.object(pr.fxpaths.localconfig, "shared_dir", lambda: empty):
            self.assertIsNone(pr.charminv_dir())

    def dof_files(self):
        """A fake Damage Overflow Fix DLL in a folder, and the pins of package_release.DOF patched to its bytes."""
        folder = self.tmp / "dof"
        folder.mkdir(exist_ok=True)
        dll = folder / "d2rl-celestialrayone-damage-overflow-fix.dll"
        dll.write_bytes(b"MZ damage-overflow-fix\0 2.4.0")
        pins = mock.patch.dict(pr.DOF, {"sha256": pr.sha256(dll), "size": dll.stat().st_size})
        pins.start()
        self.addCleanup(pins.stop)
        return folder

    def test_dof_pins_the_authors_release_and_our_settings(self):
        self.assertEqual(pr.DOF["dll"], "d2rloader/plugins/d2rl-celestialrayone-damage-overflow-fix.dll")
        self.assertEqual(pr.DOF["config"], "d2rloader/config/celestialrayone.damage-overflow-fix.toml")
        self.assertEqual((pr.DOF["version"], pr.DOF["sha256"]),
                         ("2.4.0", "cfc95e328230c86d4659f04d223552afd90f3fd4990f3fd62c48e9770f144a58"))
        readme = (pr.DOF_OURS / "README.md").read_text("utf-8")
        for pin in (pr.DOF["sha256"], pr.DOF["commit"], pr.DOF["repo"]):
            self.assertIn(pin, readme)
        self.assertIn("Copyright (c) 2026 Bogdan Bulai", (pr.DOF_OURS / "LICENSE").read_text("utf-8"))
        # the owner's settings (2026-11-16): no per-hit log, no line per site, leech on
        cfg = (pr.DOF_OURS / "celestialrayone.damage-overflow-fix.toml").read_text("utf-8")
        self.assertEqual(pr.dof_config_problems(cfg), [])
        self.assertEqual(len(pr.dof_config_problems(cfg.replace("\ndebug_log = false\n", "\ndebug_log = true\n"))), 1)

    def test_dof_staged_with_licence_and_its_config_preserved(self):
        mod = self.staged()
        folder = self.dof_files()
        self.assertEqual(pr.check_dof(folder), [])
        pr.stage_dof(mod, folder)
        self.assertEqual((mod / pr.DOF["dll"]).read_bytes(), (folder / "d2rl-celestialrayone-damage-overflow-fix.dll").read_bytes())
        self.assertIn("MIT License", (mod / pr.DOF["licence"]).read_text("utf-8"))
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, dof=True))
        self.assertIn(pr.DOF["config"], m["preserve"])
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["version"], entry["commit"]), ("Damage Overflow Fix", "2.4.0", pr.DOF["commit"]))
        self.assertEqual(set(entry["files"]), {pr.DOF[k] for k in pr.DOF_FILES})
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})

    def test_dof_other_bytes_and_settings_are_refused(self):
        mod = self.staged()
        folder = self.dof_files()
        (folder / "d2rl-celestialrayone-damage-overflow-fix.dll").write_bytes(b"MZ damage-overflow-fix\0 2.4.1")
        self.assertIn("is not Damage Overflow Fix 2.4.0", "\n".join(pr.check_dof(folder)))
        with self.assertRaises(SystemExit):
            pr.stage_dof(mod, folder)
        self.assertFalse((mod / pr.DOF["dll"]).exists())
        folder = self.dof_files()
        ours = self.tmp / "dof-ours"
        shutil.copytree(pr.DOF_OURS, ours, ignore=shutil.ignore_patterns("*.dll"))
        cfg = ours / "celestialrayone.damage-overflow-fix.toml"
        cfg.write_text(cfg.read_text("utf-8").replace("\nleech = true\n", "\nleech = false\n"), "utf-8")
        with self.assertRaisesRegex(SystemExit, "leech must be true"):
            pr.stage_dof(mod, folder, ours)

    def test_dof_dir_lookup(self):
        folder = self.dof_files()
        self.assertEqual(pr.dof_dir(folder), folder)
        with mock.patch.dict(os.environ, {"MXL_DOF_DIR": str(folder)}):
            self.assertEqual(pr.dof_dir(), folder)
        empty = self.tmp / "nothing-dof"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"MXL_DOF_DIR": str(empty)}), mock.patch.object(pr, "DOF_OURS", empty), \
                mock.patch.object(pr.fxpaths.localconfig, "shared_dir", lambda: empty):
            self.assertIsNone(pr.dof_dir())

    def test_md_pins_the_authors_release_and_its_default_config(self):
        self.assertEqual(pr.MD["dll"], "d2rloader/plugins/d2rl-celestialrayone-monster-display.dll")
        self.assertEqual((pr.MD["version"], pr.MD["sha256"], pr.MD["commit"]),
                         ("1.0.18", "bc5fa7d7ed6468981f8c165b8c3bdde49e475f68a8371d93e2f2eba3b566eaed", pr.DOF["commit"]))
        readme = (pr.MD_OURS / "README.md").read_text("utf-8")
        for pin in (pr.MD["sha256"], pr.MD["data_sha256"], pr.MD["commit"], pr.MD["repo"]):
            self.assertIn(pin, readme)
        self.assertIn("Copyright (c) 2026 Bogdan Bulai", (pr.MD_OURS / "LICENSE").read_text("utf-8"))
        cfg = (pr.MD_OURS / "celestialrayone.monster-display.toml").read_text("utf-8")
        self.assertEqual(pr.md_config_problems(cfg), [])
        self.assertEqual(len(pr.md_config_problems(cfg.replace('mode = "effective"', 'mode = "monster"'))), 1)
        # Median's 36-39 stay hidden on minions; the author's default list alone is refused
        self.assertIn("minion_hidden_affixes = [9, 17, 18, 26, 27, 28, 36, 37, 38, 39]", cfg)
        author = cfg.replace("[9, 17, 18, 26, 27, 28, 36, 37, 38, 39]", "[9, 17, 18, 26, 27, 28]")
        self.assertEqual(pr.md_config_problems(author),
                         [f"{pr.MD['config']}: minion_hidden_affixes must hold 36, 37, 38, 39"])
        # three layouts and 14 frame sprites, each also in its low-end variant
        self.assertEqual(len(pr.md_package_paths()), 3 + 3 + 28)

    def test_md_staged_into_the_plugins_config_and_data(self):
        import test_verify_package as tvp
        mod = self.staged()
        folder, pins = tvp.fake_md_release(self.tmp)
        pins.start()
        self.addCleanup(pins.stop)
        self.assertEqual(pr.check_md(folder), [])
        pr.stage_md(mod, folder)
        data = mod / f"{pr.NAME}.mpq" / "data"
        self.assertEqual((data / "global/ui/layouts/hudmonsterhealthhd.json").read_bytes(), b"hudmonsterhealthhd_pc.json\n")
        self.assertTrue((data / "hd/global/ui/panel/monsterdisplayframes/boss_mid.lowend.sprite").is_file())
        self.assertIn("MIT License", (mod / pr.MD["licence"]).read_text("utf-8"))
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, md=True))
        self.assertIn(pr.MD["config"], m["preserve"])
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["version"], entry["sha256"]), ("Monster Display", "1.0.18", pr.MD["sha256"]))
        self.assertEqual(set(entry["files"]), set(pr.md_package_paths()))
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})

    def test_md_other_bytes_and_a_mod_layout_of_its_own_are_refused(self):
        import test_verify_package as tvp
        mod = self.staged()
        folder, pins = tvp.fake_md_release(self.tmp)
        pins.start()
        self.addCleanup(pins.stop)
        sprite = folder / "MonsterDisplay" / "monsterdisplayframes" / "boss_mid.sprite"
        sprite.write_bytes(b"other art")
        self.assertIn("files differ", "\n".join(pr.check_md(folder)))
        sprite.unlink()
        self.assertIn("lacks boss_mid.sprite", "\n".join(pr.check_md(folder)))
        with self.assertRaises(SystemExit):
            pr.stage_md(mod, folder)
        self.assertFalse((mod / pr.MD["dll"]).exists())
        sprite.write_bytes(b"boss_mid.sprite\n")
        self.assertEqual(pr.check_md(folder), [])
        own = mod / f"{pr.NAME}.mpq" / "data" / "global/ui/layouts/hudmonsterhealthhd.json"
        own.parent.mkdir(parents=True, exist_ok=True)
        own.write_text("{}", "utf-8")
        with self.assertRaisesRegex(SystemExit, "already in the mod's data"):
            pr.stage_md(mod, folder)
        empty = self.tmp / "nothing-md"
        empty.mkdir()
        with mock.patch.dict(os.environ, {"MXL_MD_DIR": str(empty)}), \
                mock.patch.object(pr.fxpaths.localconfig, "shared_dir", lambda: empty):
            self.assertIsNone(pr.md_dir())
        with mock.patch.dict(os.environ, {"MXL_MD_DIR": str(folder)}):
            self.assertEqual(pr.md_dir(), folder)

    def test_vsr_is_built_from_the_suite_commit_floating_damage_uses(self):
        script = (HERE / "build_vendorstockrefresh.ps1").read_text("utf-8")
        self.assertIn("third_party/RuffnecKk-D2RLoader-Suite", script)
        self.assertEqual(pr.VSR["repo"], pr.FD["repo"])
        self.assertEqual(pr.VSR["mpq_sha256"], "0014c677e24979275307fd2194b4d6c31167a46ab8eb9c0f005b6a8cddedc5f6")
        readme = (pr.VSR_OURS / "README.md").read_text("utf-8")
        for pin in (pr.VSR["mpq_sha256"], pr.fd_commit(), pr.VSR["hub"]):
            self.assertIn(pin, readme)
        self.assertEqual(pr.vsr_config_problems("[plugin]\nenabled = true\n\n[diagnostics]\nenabled = false\n"), [])
        self.assertEqual(len(pr.vsr_config_problems("[plugin]\nenabled = true\n\n[diagnostics]\nenabled = true\n")), 1)

    def test_vsr_staged_with_its_mpq_licence_and_notices(self):
        import test_verify_package as tvp
        mod = self.staged()
        dll, mpq, src, pins = tvp.fake_vsr_build(self.tmp)
        pins.start()
        self.addCleanup(pins.stop)
        self.assertEqual(pr.check_vsr(dll) + pr.check_vsr_mpq(mpq), [])
        pr.stage_vsr(mod, dll, mpq, src)
        for k in pr.VSR_FILES:
            self.assertTrue((mod / pr.VSR[k]).is_file(), k)
        self.assertIn("===== third_party/PluginSDK/LICENSE =====", (mod / pr.VSR["notices"]).read_text("utf-8"))
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, vsr=True))
        self.assertIn(pr.VSR["config"], m["preserve"])
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["commit"], entry["mpqSha256"]),
                         ("Vendor Stock Refresh", pr.fd_commit(), pr.VSR["mpq_sha256"]))
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})

    def test_vsr_other_builds_mpqs_and_settings_are_refused(self):
        import test_verify_package as tvp
        mod = self.staged()
        dll, mpq, src, pins = tvp.fake_vsr_build(self.tmp)
        pins.start()
        self.addCleanup(pins.stop)
        (src / "PINNED_COMMIT").write_text("0" * 40, encoding="ascii")
        with self.assertRaisesRegex(SystemExit, "is not the pinned commit"):
            pr.stage_vsr(mod, dll, mpq, src)
        (src / "PINNED_COMMIT").write_text(pr.fd_commit(), encoding="ascii")
        (mpq / "d2rl-ruffneckk-vendor-stock-refresh.mpq").write_bytes(b"MPQ\x1a other")
        with self.assertRaisesRegex(SystemExit, "companion MPQ"):
            pr.stage_vsr(mod, dll, mpq, src)
        (mpq / "d2rl-ruffneckk-vendor-stock-refresh.mpq").write_bytes(b"MPQ\x1a vendor-stock-refresh")
        (dll.parent / pr.VSR_FROM["config"]).write_text("[plugin]\nenabled = true\n\n[diagnostics]\nenabled = true\n", "utf-8")
        with self.assertRaisesRegex(SystemExit, "diagnostics"):
            pr.stage_vsr(mod, dll, mpq, src)
        dll.write_bytes(b"MZ VendorStockRefresh 2.1.6 by RuffnecKk\0")
        self.assertIn("is not Vendor Stock Refresh 2.1.7", "\n".join(pr.check_vsr(dll)))
        self.assertFalse((mod / pr.VSR["dll"]).exists())

    def test_ehb_is_pinned_with_our_patches(self):
        self.assertEqual((pr.EHB["author"], pr.EHB["licence_id"]), ("Graxy_TV", "GPL-3.0-only"))
        script = (HERE / "build_enemyhealthbars.ps1").read_text("utf-8")
        self.assertIn(f"$pin = '{pr.EHB['commit']}'", script)  # one pin for the build and the manifest
        names = [p.split("  ")[1] for p in pr.ehb_patches()]
        self.assertEqual(names, ["0001-no-build-fingerprint.patch", "0002-dev-keep-visible-unfocused.patch",
                                 "0003-legacy-placement-damaged-only.patch", "0004-dirty-rect-idle-hidden.patch",
                                 "0005-mxl2012-uniques-filter-mode-keys.patch"])
        readme = (pr.EHB_OURS / "README.md").read_text("utf-8")
        self.assertIn(pr.EHB["commit"], readme)
        self.assertIn("GPL-3.0", readme)

    def test_ehb_renderer_sends_only_what_changed(self):
        # 0.1.30 (lane rel0130): the standalone window is made with the first bar, hidden with nothing sent while no bar
        # shows, only the changed area sent while bars show, and idle while the bars are off
        patch = (pr.EHB_OURS / "0004-dirty-rect-idle-hidden.patch").read_text("utf-8")
        self.assertIn("+++ b/src/present_plan.h", patch)
        self.assertIn("UpdateLayeredWindowIndirect", patch)
        self.assertIn("prcDirty=&dirty", patch)
        self.assertIn("-        if(!UpdateLayeredWindow(", patch)  # the whole-window send every pass is gone
        self.assertIn("if(!barsOn){hide();Sleep(50);continue;}", patch)
        self.assertIn("bars::standalone::setEnabled(c.enabled);", patch)
        self.assertIn("no ghost bars", patch)  # its policy_tests case

    def test_ehb_staged_with_licences_and_source(self):
        import test_verify_package as tvp
        mod = self.staged()
        dll, tree = tvp.fake_ehb_build(self.tmp)
        self.assertEqual(pr.check_ehb(dll), [])
        pr.stage_ehb(mod, dll, tree)
        for k in pr.EHB_FILES:
            self.assertTrue((mod / pr.EHB[k]).is_file(), k)
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, ehb=True))
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["author"], entry["licence"], entry["commit"]),
                         ("Enemy Health Bars", "Graxy_TV", "GPL-3.0-only", pr.EHB["commit"]))
        self.assertEqual(entry["patches"], pr.ehb_patches())
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})
        self.assertIn(pr.EHB["config"], m["preserve"])  # a player's show_full_health survives updates

    def test_ehb_defaults_to_damaged_monsters_only_with_a_setting_for_all(self):
        import test_verify_package as tvp
        self.assertEqual(pr.ehb_config_problems(tvp.EHB_CONFIG), [])
        for bad, why in ((tvp.EHB_CONFIG.replace("show_full_health = false", "show_full_health = true"), "show_full_health"),
                         (tvp.EHB_CONFIG.replace("show_full_health = false\n", ""), "show_full_health"),
                         (tvp.EHB_CONFIG.replace("enabled = true", "enabled = false"), "enabled"),
                         (tvp.EHB_CONFIG.replace("uniques_bosses_only = false", "uniques_bosses_only = true"), "uniques_bosses_only"),
                         (tvp.EHB_CONFIG.replace("uniques_bosses_only = false\n", ""), "uniques_bosses_only"),
                         (tvp.EHB_CONFIG + "dev_keep_visible_unfocused = true\n", "test captures only")):
            self.assertIn(why, "\n".join(pr.ehb_config_problems(bad)))
        # the patch sets the default in the plugin and in its config, and places the bars in legacy graphics too
        patch = (pr.EHB_OURS / "0003-legacy-placement-damaged-only.patch").read_text("utf-8")
        self.assertIn("+show_full_health = false", patch)
        self.assertIn("+    bool enabled=true, full=false,", patch)
        self.assertIn("bars::shown(c.full,ratio)", patch)
        self.assertIn("+++ b/src/legacy_projection.h", patch)
        self.assertNotIn("TimeDateStamp", patch)  # placement found by expected bytes, never by build
        mod = self.staged()
        dll, tree = tvp.fake_ehb_build(self.tmp)
        (dll.parent.parent / pr.EHB_FROM["config"]).write_text(tvp.EHB_CONFIG.replace("= false", "= true"), "utf-8")
        with self.assertRaisesRegex(SystemExit, "show_full_health must be false"):
            pr.stage_ehb(mod, dll, tree)

    def test_ehb_builds_that_are_not_ours_are_refused(self):
        import test_verify_package as tvp
        mod = self.staged()
        dll, tree = tvp.fake_ehb_build(self.tmp)
        dll.write_bytes(b"MZ 0.2.6\0")  # the author's build: no patches
        self.assertIn("with our patches", "\n".join(pr.check_ehb(dll)))
        dll.write_bytes(b"MZ " + pr.EHB["version"].encode() + b"\0dev_keep_visible_unfocused\0")  # no legacy placement
        self.assertIn("with our patches", "\n".join(pr.check_ehb(dll)))
        (tree / "PATCHES").write_text(pr.ehb_patches()[0] + "\n", encoding="ascii")
        with self.assertRaisesRegex(SystemExit, "not built with the patches"):
            pr.stage_ehb(mod, dll, tree)
        (tree / "PATCHES").write_text("\n".join(pr.ehb_patches()) + "\n", encoding="ascii")
        (tree / "SOURCE.txt").write_text("commit 0000\n", encoding="ascii")
        with self.assertRaisesRegex(SystemExit, "is not the source of commit"):
            pr.stage_ehb(mod, dll, tree)
        self.assertFalse((mod / pr.EHB["dll"]).exists())

    def test_fd_is_pinned_with_our_patches_and_font(self):
        self.assertEqual(len(pr.fd_commit()), 40)
        names = [p.split("  ")[1] for p in pr.fd_patches()]
        self.assertEqual(names, ["0001-mxl2012-legacy-projection.patch", "0002-mxl2012-bundled-font.patch",
                                 "0003-mxl2012-legacy-dps-counter.patch", "0004-mxl2012-legacy-text-scale.patch",
                                 "0005-mxl2012-missing-system-font.patch", "0006-mxl2012-show-numbers-key.patch"])
        readme = (pr.FD_OURS / "README.md").read_text("utf-8")
        self.assertIn(pr.fd_commit(), readme)
        self.assertIn("SIL Open Font License 1.1", readme)
        self.assertIn("SIL OPEN FONT LICENSE", (pr.FD_OURS / "fonts" / "OFL.txt").read_text("utf-8").upper())

    def test_fd_staged_with_licences_font_and_its_config_preserved(self):
        import test_verify_package as tvp
        mod = self.staged()
        dll, src = tvp.fake_fd_build(self.tmp)
        self.assertEqual(pr.check_fd(dll), [])
        pr.stage_fd(mod, dll, src)
        for k in pr.FD_FILES:
            self.assertTrue((mod / pr.FD[k]).is_file(), k)
        notices = (mod / pr.FD["notices"]).read_text("utf-8")
        self.assertIn("===== third_party/notices/IMGUI-LICENSE.txt =====", notices)
        self.assertIn("===== third_party/PluginSDK/LICENSE =====", notices)
        files = pr.file_list(mod)
        m = pr.manifest("1.2.3", files, self.fake_7z(mod), True, pr.empty_dirs(mod), pr.preserve_list(mod),
                        pr.bundled_plugins(False, False, fd=True))
        self.assertIn(pr.FD["config"], m["preserve"])
        (entry,) = m["bundledPlugins"]
        self.assertEqual((entry["name"], entry["author"], entry["commit"]), ("Floating Damage", "RuffnecKk", pr.fd_commit()))
        self.assertEqual(entry["patches"], pr.fd_patches())
        self.assertTrue(set(entry["files"]) <= {f["path"] for f in files})

    def test_fd_legacy_numbers_ship_two_and_a_half_times_bigger(self):
        import test_verify_package as tvp
        for other in ("legacy_text_scale = 1.0", "# legacy_text_scale = 2.5"):
            bad = tvp.FD_CONFIG.replace("legacy_text_scale = 2.5", other)
            self.assertIn("legacy_text_scale must be 2.5", "\n".join(pr.fd_config_problems(bad)))
        # the key belongs to [appearance]: the same key in another table does not count
        moved = tvp.FD_CONFIG.replace("[appearance]\nlegacy_text_scale = 2.5\n", "").replace(
            "[diagnostics]\n", "[diagnostics]\nlegacy_text_scale = 2.5\n")
        self.assertTrue(pr.fd_config_problems(moved))

    def test_fd_is_on_by_default_with_a_setting_to_turn_it_off(self):
        import test_verify_package as tvp
        self.assertEqual(pr.fd_config_problems(tvp.FD_CONFIG), [])
        off = tvp.FD_CONFIG.replace("[general]\n# Master switch.\nenabled = true", "[general]\nenabled = false")
        self.assertIn("enabled must be true", "\n".join(pr.fd_config_problems(off)))
        # [diagnostics] enabled is another key: without [general] enabled the default is not proven
        self.assertTrue(pr.fd_config_problems("[diagnostics]\nenabled = true\n"))
        # the author's config: its master switch is on; legacy_text_scale is ours (patch 0004), so only that is missing
        author = pr.ROOT / "third_party" / "RuffnecKk-D2RLoader-Suite" / "plugins" / "floating-damage" / "config"
        if (author / "ruffneckk-floating-damage.toml").is_file():
            self.assertEqual(pr.fd_config_problems((author / "ruffneckk-floating-damage.toml").read_text("utf-8")),
                             [f"{pr.FD['config']}: [general] show_numbers must be true (numbers shown by default)",
                              f"{pr.FD['config']}: [appearance] legacy_text_scale must be 2.5"])
        # the config the build ships (all our patches applied)
        built = pr.ROOT / "build" / "floatingdamage" / "Release" / "ruffneckk-floating-damage.toml"
        if built.is_file() and "legacy_text_scale" in built.read_text("utf-8"):
            self.assertEqual(pr.fd_config_problems(built.read_text("utf-8")), [])
        mod = self.staged()
        dll, src = tvp.fake_fd_build(self.tmp)
        (dll.parent / pr.FD_FROM["config"]).write_text(off, "utf-8")
        with self.assertRaisesRegex(SystemExit, "enabled must be true"):
            pr.stage_fd(mod, dll, src)

    def test_fd_builds_that_are_not_ours_are_refused(self):
        import test_verify_package as tvp
        mod = self.staged()
        dll, src = tvp.fake_fd_build(self.tmp)
        dll.write_bytes(b"MZ 1.5.6\0")  # the author's build: no font patch
        self.assertIn("with our patches", "\n".join(pr.check_fd(dll)))
        (src / "PINNED_COMMIT").write_text("0" * 40, encoding="ascii")
        with self.assertRaisesRegex(SystemExit, "is not the pinned commit"):
            pr.stage_fd(mod, dll, src)
        (src / "PINNED_COMMIT").write_text(pr.fd_commit(), encoding="ascii")
        (src / "PATCHES").write_text(pr.fd_patches()[0] + "\n", encoding="ascii")
        with self.assertRaisesRegex(SystemExit, "not built with the patches"):
            pr.stage_fd(mod, dll, src)
        self.assertFalse((mod / pr.FD["dll"]).exists())

    def test_controllerqol_source_of_another_commit_patch_set_or_seed_is_refused(self):
        mod = self.staged()
        for commit, patches in (("0" * 40, None), (None, pr.controllerqol_patches()[:1])):
            src, dll, seed = self.controllerqol_src(commit, patches)
            with self.assertRaises(SystemExit):
                pr.stage_controllerqol(mod, dll, seed, src)
            self.assertFalse((mod / pr.CONTROLLERQOL["dll"]).exists())
        src, dll, seed = self.controllerqol_src()
        seed.write_bytes(b"[aim.sorceress]\n")  # this package's seed differs from the one built in
        for profile in (seed, None):
            with self.assertRaises(SystemExit):
                pr.stage_controllerqol(mod, dll, profile, src)
        self.assertFalse((mod / pr.CONTROLLERQOL["dll"]).exists())

    def test_controllerqol_builds_that_are_not_ours_are_refused(self):
        _src, dll, _seed = self.controllerqol_src()
        self.assertEqual(pr.check_controllerqol(dll), [])
        dll.write_bytes(b"MZ controller-qol-updates\0 1.3.1+rev.94\0 belt_actions = false")
        self.assertTrue(any("version 1.3.1+rev.95" in p for p in pr.check_controllerqol(dll)))
        dll.write_bytes(b"MZ controller-qol-updates\0 1.3.1+rev.95\0")  # PyreFly's own build: no belt switch
        self.assertTrue(any("not our patched build" in p for p in pr.check_controllerqol(dll)))

    def test_legacy169_test_builds_are_refused(self):
        _src, dll = self.legacy169_src()
        self.assertEqual(pr.check_legacy169(dll), [])
        for body, words in ((b"MZ legacy169\0 0.1.2-test\0", "test build"), (b"MZ legacy169-testharness.txt 0.1.2\0", "test build"),
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
                            "--version", "99.0.0", "--data-from", str(data), "--out", str(out), "--charm-inventory", "charminv"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("PluginVersion", r.stdout)
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--plugin", str(self.dll),
                            "--data-from", str(data), "--out", str(out), "--no-bundled", "--charm-inventory", "charminv",
                            *self.own_plugins()],
                           capture_output=True, text=True, env=self.baseline_env())  # this small data tree has nothing of invtabs
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
        # code only: the charm inventory plugin (invtabs by default) is not taken from this machine's build folder
        self.assertFalse([f["path"] for f in man["files"] if "invtabs" in f["path"] or "charm-inv" in f["path"]])

    @unittest.skipUnless(SEVEN, "no 7-Zip on this machine")
    def test_notes_template_and_missing_baseline(self):
        data = self.tmp / "d"
        (data / "global" / "excel").mkdir(parents=True)
        (data / "global" / "excel" / "armor.txt").write_bytes(b"Median armor\n")
        clear_fonts(data)
        out = self.tmp / "dist"
        args = [sys.executable, "-I", str(HERE / "package_release.py"), "--plugin", str(self.dll), "--data-from", str(data),
                "--out", str(out), "--no-bundled", "--charm-inventory", "charminv", *self.own_plugins()]  # nothing of invtabs here
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
        self.assertNotIn("93847", notes)  # no game build or version is required (docs/plugin-plan.md 1.1)
        self.assertNotIn("needs D2R build", notes)
        self.assertIn("tested on D2R 3.3 and 3.4", notes)
        self.assertIn("Don't remind me again for D2R 3.4", notes)
        self.assertIn("this D2RLoader version is not supported", notes)
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
