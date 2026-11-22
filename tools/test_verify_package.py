"""tools/verify_package.py on a small fake package; no game files, no plugin build."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import package_release as pr
import verify_package as vp


SEVEN = pr.find_7z()


# the shipped defaults: health bars only on damaged monsters, Floating Damage on
EHB_CONFIG = ("[bars]\nenabled = true\n# true = every enemy\nshow_full_health = false\nuniques_bosses_only = false\n"
              "hide_with_side_panels = true\n")
FD_CONFIG = ("[general]\n# Master switch.\nenabled = true\nshow_numbers = true\n\n[appearance]\nlegacy_text_scale = 2.5\n\n"
             "[diagnostics]\nenabled = false\n")


def fake_ehb_build(tmp: Path):
    """What tools/build_enemyhealthbars.ps1 leaves: build/enemyhealthbars (DLL, licences, notices, source zip) and the patched
    tree with PATCHES / SOURCE.txt. Returns (dll, tree)."""
    build = tmp / "enemyhealthbars"
    for k, rel in pr.EHB_FROM.items():
        (build / rel).parent.mkdir(parents=True, exist_ok=True)
        (build / rel).write_bytes(b"MZ " + pr.EHB["version"].encode()
                                  + b"\0dev_keep_visible_unfocused\0legacy graphics placement\0Mxl2012EnemyBarsSetModeV1\0" if k == "dll"
                                  else EHB_CONFIG.encode() if k == "config" else k.encode() + b"\n")
    tree = tmp / "enemyhealthbars-src" / "EnemyHealthBars"
    tree.mkdir(parents=True)
    (tree / "PATCHES").write_text("\n".join(pr.ehb_patches()) + "\n", encoding="ascii")
    (tree / "SOURCE.txt").write_text(f"Upstream: {pr.EHB['repo']} commit {pr.EHB['commit']}\n", encoding="ascii")
    return build / pr.EHB_FROM["dll"], tree


def fake_fd_build(tmp: Path):
    """What tools/build_floatingdamage.ps1 leaves: build/floatingdamage/Release (DLL, licences, font, config) and the exported
    source with PINNED_COMMIT / PATCHES and the third-party notices. Returns (dll, src)."""
    rel = tmp / "floatingdamage" / "Release"
    rel.mkdir(parents=True)
    for k, name in pr.FD_FROM.items():
        (rel / name).write_bytes(b"MZ " + pr.FD["version"].encode() + b"\0ruffneckk-floating-damage-font.ttf\0Mxl2012FloatingDamageSetShownV1\0" if k == "dll"
                                 else FD_CONFIG.encode() if k == "config" else k.encode() + b"\n")
    src = tmp / "floatingdamage-src"
    (src / "third_party" / "notices").mkdir(parents=True)
    (src / "third_party" / "PluginSDK").mkdir(parents=True)
    (src / "THIRD_PARTY_NOTICES.md").write_text("# Third-Party Notices\n", encoding="utf-8")
    (src / "third_party" / "notices" / "IMGUI-LICENSE.txt").write_text("The MIT License (MIT)\n", encoding="utf-8")
    (src / "third_party" / "PluginSDK" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (src / "PINNED_COMMIT").write_text(pr.fd_commit(), encoding="ascii")
    (src / "PATCHES").write_text("\n".join(pr.fd_patches()) + "\n", encoding="ascii")
    return rel / pr.FD_FROM["dll"], src


VSR_CONFIG = "[plugin]\nenabled = true\n\n[diagnostics]\nenabled = false\n\n[d2rl]\nmatch = true\n"


def fake_md_release(tmp: Path):
    """The author's release folder of Monster Display (fakes): the DLL and MonsterDisplay/ with its layouts and frames.
    Returns (folder, pins): pins patches package_release.MD to these bytes (start it in the test)."""
    folder = tmp / "md-release"
    (folder / "MonsterDisplay" / "monsterdisplayframes").mkdir(parents=True)
    dll = folder / "d2rl-celestialrayone-monster-display.dll"
    dll.write_bytes(b"MZ monster-display\0 1.0.18")
    for source in pr.md_data(folder):
        source.write_bytes(source.name.encode() + b"\n")
    pins = mock.patch.dict(pr.MD, {"sha256": pr.sha256(dll), "size": dll.stat().st_size,
                                   "data_sha256": pr.md_data_digest(folder)})
    return folder, pins


def fake_vsr_build(tmp: Path):
    """What tools/build_vendorstockrefresh.ps1 leaves (build/vendorstockrefresh/Release: DLL, licence, config; the exported
    source with PINNED_COMMIT and the notices) and the hub MPQ in a folder. Returns (dll, mpq_dir, src, pins): pins patches
    package_release.VSR's MPQ hash to the fake (start it in the test)."""
    rel = tmp / "vendorstockrefresh" / "Release"
    rel.mkdir(parents=True)
    for k, name in pr.VSR_FROM.items():
        (rel / name).write_bytes(b"MZ VendorStockRefresh " + pr.VSR["version"].encode() + b" by RuffnecKk active\0"
                                 if k == "dll" else VSR_CONFIG.encode() if k == "config" else b"MIT License\n")
    mpq = tmp / "vsr-mpq"
    mpq.mkdir()
    f = mpq / "d2rl-ruffneckk-vendor-stock-refresh.mpq"
    f.write_bytes(b"MPQ\x1a vendor-stock-refresh")
    src = tmp / "vendorstockrefresh-src"
    (src / "third_party" / "notices").mkdir(parents=True)
    (src / "third_party" / "PluginSDK").mkdir(parents=True)
    (src / "THIRD_PARTY_NOTICES.md").write_text("# Third-Party Notices\n", encoding="utf-8")
    (src / "third_party" / "notices" / "MINHOOK-LICENSE.txt").write_text("MinHook\n", encoding="utf-8")
    (src / "third_party" / "PluginSDK" / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (src / "PINNED_COMMIT").write_text(pr.fd_commit(), encoding="ascii")
    pins = mock.patch.dict(pr.VSR, {"mpq_sha256": pr.sha256(f), "mpq_size": f.stat().st_size})
    return rel / pr.VSR_FROM["dll"], mpq, src, pins


class VerifyPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.dll = self.tmp / "mxl2012-core.dll"
        self.dll.write_bytes(b"MZ..." + pr.plugin_version().encode() + b"\0...")
        data = self.tmp / "data"
        files = {"global/excel/armor.txt": b"Median armor\n", "global/dataversionbuild.txt": b"93847",
                 pr.STATBOOK_DATA: b"statbook\t1\n",
                 **{f"local/lng/{rel % 'mxl2012'}": b"[]" for rel in vp.STRING_FILES}}
        for rel, body in files.items():
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_bytes(body)
        self.mod = self.tmp / "stage" / "mxl2012"
        drawcap = self.tmp / "drawcap.dll"
        drawcap.write_bytes(b"MZ Draw List Cap" + bytes(1) + b"drawcap" + bytes(1) + pr.drawcap_version().encode() + bytes(1))
        statbook = self.tmp / "statbook.dll"
        statbook.write_bytes(b"MZ Stat Book" + bytes(1) + b"statbook" + bytes(1) + pr.statbook_version().encode() + bytes(1))
        pr.stage(self.mod, pr.plugin_version(), self.dll, self.tmp, data_from=data, drawcap=drawcap, statbook=statbook)
        # this fixture is a CharmInv package; the default is invtabs, which a test sets back where it is its subject
        switch = mock.patch.object(pr, "CHARM_INVENTORY", "charminv")
        switch.start()
        self.addCleanup(switch.stop)
        src = self.tmp / "legacy169-src"  # what tools/build_legacy169.ps1 exports
        src.mkdir()
        (src / "legacy169.toml").write_text("[legacy169]\nenabled = true\n", encoding="utf-8")
        (src / "PINNED_COMMIT").write_text(pr.legacy169_commit(), encoding="ascii")
        (self.tmp / "legacy169.dll").write_bytes(b"MZ legacy169\0 0.1.2\0")
        pr.stage_legacy169(self.mod, self.tmp / "legacy169.dll", src)
        buff = self.tmp / "buffhud-src"  # what tools/build_buffhud.ps1 exports
        (buff / "external" / "PluginSDK").mkdir(parents=True)
        for rel in ("buff-panel.toml", "LICENSE", "external/PluginSDK/LICENSE"):
            (buff / rel).write_text("x\n", encoding="utf-8")
        (buff / "PINNED_COMMIT").write_text(pr.buffhud_commit(), encoding="ascii")
        (self.tmp / "d2rl-buff-panel.dll").write_bytes(b"MZ buff-panel\0 " + pr.BUFFHUD["version"].encode() + b"\0 [buff_panel]")
        (self.tmp / "d2rl-buff-panel.mpq").write_bytes(b"MPQ\x1a")
        pr.stage_buffhud(self.mod, self.tmp / "d2rl-buff-panel.dll", buff)
        belt = self.tmp / "beltrefill-src"  # what tools/build_beltrefill.ps1 exports
        belt.mkdir()
        (belt / "PINNED_COMMIT").write_text(pr.beltrefill_commit(), encoding="ascii")
        (belt / "PATCHES").write_text("\n".join(pr.beltrefill_patches()), encoding="ascii")
        (self.tmp / "d2rl-auto-belt-refill.dll").write_bytes(b"MZ auto-belt-refill\0 0.35.9\0")
        pr.stage_beltrefill(self.mod, self.tmp / "d2rl-auto-belt-refill.dll", belt)
        cq = self.tmp / "controllerqol-src"  # what tools/build_controllerqol.ps1 exports
        (cq / "plugins" / "controller-qol").mkdir(parents=True)
        for rel in ("plugins/controller-qol/controller-qol-updates.toml", "LICENSE", "PluginSDK-LICENSE"):
            (cq / rel).write_text("x\n", encoding="utf-8")
        (cq / "PINNED_COMMIT").write_text(pr.controllerqol_commit(), encoding="ascii")
        (cq / "PATCHES").write_text("\n".join(pr.controllerqol_patches()), encoding="ascii")
        seed = self.tmp / "mxl2012.overrides.toml"
        seed.write_text("[aim.amazon]\n", encoding="utf-8")
        (cq / "SKILL_PROFILE").write_text(pr.sha256(seed), encoding="ascii")
        (self.tmp / "Controller QOL Updates.dll").write_bytes(b"MZ controller-qol-updates\0 1.3.1+rev.95\0 belt_actions = false")
        pr.stage_controllerqol(self.mod, self.tmp / "Controller QOL Updates.dll", seed, cq)
        ci = self.tmp / "charminv"  # the author's two files (fakes, pinned for the test)
        ci.mkdir()
        (ci / "d2rl-charm-inv.dll").write_bytes(b"MZ charm-inv\0")
        (ci / "d2rl-charm-inv.mpq").write_bytes(b"MPQ\x1a charm-inv")
        pins = mock.patch.dict(pr.CHARMINV, {"sha256": {k: pr.sha256(ci / f"d2rl-charm-inv.{k}") for k in ("dll", "mpq")},
                                             "size": {k: (ci / f"d2rl-charm-inv.{k}").stat().st_size for k in ("dll", "mpq")}})
        pins.start()
        self.addCleanup(pins.stop)
        pr.stage_charminv(self.mod, ci)
        dof = self.tmp / "dof"  # the author's DLL (a fake, pinned for the test)
        dof.mkdir()
        (dof / "d2rl-celestialrayone-damage-overflow-fix.dll").write_bytes(b"MZ damage-overflow-fix\0")
        pins = mock.patch.dict(pr.DOF, {"sha256": pr.sha256(dof / "d2rl-celestialrayone-damage-overflow-fix.dll"),
                                        "size": (dof / "d2rl-celestialrayone-damage-overflow-fix.dll").stat().st_size})
        pins.start()
        self.addCleanup(pins.stop)
        pr.stage_dof(self.mod, dof)
        ehb_dll, ehb_src = fake_ehb_build(self.tmp)
        pr.stage_ehb(self.mod, ehb_dll, ehb_src)
        fd_dll, fd_src = fake_fd_build(self.tmp)
        pr.stage_fd(self.mod, fd_dll, fd_src)
        md, pins = fake_md_release(self.tmp)
        pins.start()
        self.addCleanup(pins.stop)
        pr.stage_md(self.mod, md)
        vsr_dll, vsr_mpq, vsr_src, pins = fake_vsr_build(self.tmp)
        pins.start()
        self.addCleanup(pins.stop)
        pr.stage_vsr(self.mod, vsr_dll, vsr_mpq, vsr_src)

    def test_invtabs_replaces_charminv_only_when_present(self):
        dll = self.tmp / "invtabs.dll"
        dll.write_bytes(b"MZ invtabs\0")
        for k in pr.CHARMINV_FILES:
            (self.mod / pr.CHARMINV[k]).unlink()
        pr.stage_invtabs(self.mod, dll)
        missing = vp.check_mod_folder(self.mod, pr.plugin_version())
        self.assertEqual(len(missing), len(pr.INVTABS_DATA))  # invtabs' mod data is required with it
        for rel in pr.INVTABS_DATA:
            (self.mod / f"{pr.NAME}.mpq" / "data" / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.mod / f"{pr.NAME}.mpq" / "data" / rel).write_bytes(b"x")
        self.assertEqual(vp.check_mod_folder(self.mod, pr.plugin_version()), [])
        (self.mod / pr.CHARMINV["dll"]).write_bytes(b"MZ")
        self.assertIn("invtabs and CharmInv cannot be staged together", vp.check_mod_folder(self.mod, pr.plugin_version()))
        (self.mod / pr.CHARMINV["dll"]).unlink()
        (self.mod / pr.INVTABS["config"]).unlink()
        self.assertIn(pr.INVTABS["config"]+" is missing", vp.check_mod_folder(self.mod, pr.plugin_version()))

    def test_the_data_must_be_built_for_the_charm_inventory_in_the_package(self):
        import charm_inventory as ci
        import invtabs_legacy as il
        data = self.mod / f"{pr.NAME}.mpq" / "data"
        layout = '{"type": "Panel", "children": [\n    {"type": "ButtonWidget", "name": "close"}\n]}\n'
        (data / ci.CLASSIC_INVENTORY[0]).parent.mkdir(parents=True, exist_ok=True)
        (data / ci.CLASSIC_INVENTORY[0]).write_text(il.add_button_to_layout(layout), "utf-8")
        # a CharmInv package with the classic Charms button: the button would open nothing
        problems = vp.check_mod_folder(self.mod, pr.plugin_version())
        self.assertEqual(len(problems), 1)
        self.assertIn("opens nothing with CharmInv", problems[0])
        # the same data with invtabs instead of CharmInv, and invtabs' files: fine; without the button: refused
        for k in pr.CHARMINV_FILES:
            (self.mod / pr.CHARMINV[k]).unlink()
        dll = self.tmp / "invtabs.dll"
        dll.write_bytes(b"MZ invtabs\0")
        pr.stage_invtabs(self.mod, dll)
        for rel in ci.INVTABS_DATA:
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_bytes(b"x")
        self.assertEqual(vp.check_mod_folder(self.mod, pr.plugin_version()), [])
        (data / ci.CLASSIC_INVENTORY[0]).write_text(layout, "utf-8")
        self.assertIn("has no Charms button", "; ".join(vp.check_mod_folder(self.mod, pr.plugin_version())))

    def test_switch_on_requires_invtabs(self):
        with mock.patch.object(pr, "CHARM_INVENTORY", "invtabs"):
            self.assertIn(pr.INVTABS["dll"] + " is missing (package_release.CHARM_INVENTORY is invtabs)",
                          vp.check_mod_folder(self.mod, pr.plugin_version()))

    def test_a_staged_package_is_a_player_mod_folder(self):
        self.assertEqual(vp.check_mod_folder(self.mod, pr.plugin_version()), [])

    def test_mod_folder_problems(self):
        (self.mod / "modinfo.json").write_text(json.dumps({"name": "mxl2012", "savepath": "mxl2012-s2/"}))
        (self.mod / "d2rloader" / "plugins" / "mxl2012-core.dll").write_bytes(b"MZ mxl2012-testharness.txt\0")
        (self.mod / "Hero.d2s").write_bytes(b"x")
        (self.mod / pr.LEGACY169["dll"]).write_bytes(b"MZ legacy169\0 0.1.2-test\0")
        (self.mod / pr.LEGACY169["config"]).unlink()
        (self.mod / pr.BUFFHUD["mpq"]).write_bytes(b"PK")
        (self.mod / pr.BUFFHUD["licence"]).unlink()
        (self.mod / pr.BELTREFILL["dll"]).write_bytes(b"MZ auto-belt-refill\0 0.35.8\0")
        (self.mod / pr.BELTREFILL["config"]).unlink()
        (self.mod / pr.CONTROLLERQOL["dll"]).write_bytes(b"MZ controller-qol-updates\0 1.3.1+rev.95\0")
        (self.mod / pr.CONTROLLERQOL["licence"]).unlink()
        (self.mod / pr.DRAWCAP["dll"]).write_bytes(b"MZ Draw List Cap" + bytes(1) + b"drawcap" + bytes(1) + b"0.0.0" + bytes(1))
        (self.mod / pr.DRAWCAP["config"]).unlink()
        (self.mod / pr.STATBOOK["dll"]).unlink()
        (self.mod / pr.STATBOOK["config"]).unlink()
        (self.mod / pr.CHARMINV["mpq"]).write_bytes(b"MPQ\x1a other")
        (self.mod / pr.CHARMINV["config"]).write_text("[charm-inv]\nallow_inventory_charms = false\n", encoding="utf-8")
        problems = vp.check_mod_folder(self.mod, "9.9.9")
        text = "\n".join(problems)
        for want in ("modinfo.json", "modVersion", "test harness", "PluginVersion", "Hero.d2s", "legacy169 test build",
                     "legacy169.toml is missing",
                     "not a packed MPQ", "d2rl-buff-panel-LICENSE.txt is missing",
                     "Auto Belt Refill version 0.35.9", "auto-belt-refill.toml is missing",
                     "not our patched build", "Controller QOL Updates-LICENSE.txt is missing",
                     "is not drawcap", "drawcap.toml is missing", "statbook.dll is missing", "statbook.toml is missing",
                     "d2rl-charm-inv.mpq is not CharmInv 1.0.1", "lacks allow_inventory_charms = true"):
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
        for rel in vp.BUNDLED:  # install_mod.py does not install the bundled legacy169: not a difference
            (ref / rel).unlink()
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
