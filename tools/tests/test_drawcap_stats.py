"""tools/drawcap_stats.py (the drawcap plugin's stats file) and the drawcap plugin's place in install_mod / package_release."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import drawcap_stats  # noqa: E402
import install_mod  # noqa: E402
import package_release  # noqa: E402
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

CSV = """# drawcap 0.1.0, image 0x6ab3782c, build 0x21bae0, count +0x17750, cap 3000, interval 1000 ms
t_ms,mode,frames,max,mean,over,dropped,cap,view_w,view_h,grid
1000,legacy,60,1200,1100.0,0,0,3000,800,600,34
2000,legacy,60,3400,2900.5,10,1500,3000,800,600,34
2000,hd,2,500,450.0,0,0,3000,1600,900,43
bad,line
3000,hd,58,600,550.0,0,0,3000,1600,900,43
"""


class DrawcapStatsTest(unittest.TestCase):
    def test_parse_skips_comments_and_bad_lines(self):
        rows = drawcap_stats.parse(CSV)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[1]["max"], 3400)
        self.assertEqual(rows[1]["mean"], 2900.5)
        self.assertEqual(rows[2]["mode"], "hd")

    def test_summary_per_mode(self):
        rows = drawcap_stats.parse(CSV)
        s = drawcap_stats.summary(rows, "legacy")
        self.assertEqual((s["frames"], s["max"], s["over"], s["dropped"], s["cap"]), (120, 3400, 10, 1500, 3000))
        self.assertAlmostEqual(s["mean"], 2000.2, places=1)
        self.assertEqual(s["views"], [(800, 600)])
        self.assertEqual(s["peak_t_ms"], 2000)
        self.assertEqual(s["fps"], 120.0)
        hd = drawcap_stats.summary(rows, "hd")
        self.assertEqual((hd["frames"], hd["max"]), (60, 600))
        self.assertIn("legacy: 120 frames", drawcap_stats.describe(s))

    def test_empty(self):
        s = drawcap_stats.summary([], "legacy")
        self.assertEqual((s["frames"], s["max"], s["mean"], s["fps"]), (0, 0, 0.0, None))


class DrawcapInstallTest(unittest.TestCase):
    def test_write_mod_files_puts_drawcap_next_to_the_core_plugin(self):
        with tempfile.TemporaryDirectory(dir=install_mod.ROOT) as d:
            mod, dll = Path(d) / "mod", Path(d) / "drawcap.dll"
            dll.write_bytes(b"MZ drawcap test")
            install_mod.write_mod_files(mod, "x", "x/", Path(d) / "missing.dll", drawcap=dll)
            self.assertEqual((mod / "d2rloader" / "plugins" / "drawcap.dll").read_bytes(), b"MZ drawcap test")
            cfg = mod / "d2rloader" / "config" / "drawcap.toml"
            self.assertIn("probe = false", cfg.read_text("utf-8"))
            cfg.write_text("[drawcap]\nprobe = true\n", encoding="utf-8")  # a player's change stays
            install_mod.write_mod_files(mod, "x", "x/", Path(d) / "missing.dll", drawcap=dll)
            self.assertIn("probe = true", cfg.read_text("utf-8"))

    def test_without_drawcap(self):
        with tempfile.TemporaryDirectory(dir=install_mod.ROOT) as d:
            mod = Path(d) / "mod"
            install_mod.write_mod_files(mod, "x", "x/", Path(d) / "missing.dll", drawcap=None)
            self.assertFalse((mod / "d2rloader" / "plugins" / "drawcap.dll").exists())
            self.assertFalse((mod / "d2rloader" / "config" / "drawcap.toml").exists())

    def test_default_config_ships_patch_on_probe_off(self):
        text = install_mod.DRAWCAP_CONFIG.read_text("utf-8")
        self.assertIn("[drawcap]", text)
        self.assertIn("probe = false", text)
        self.assertIn("patch = true", text)
        self.assertIn("cap = 12000", text)


class DrawcapPackageTest(unittest.TestCase):
    def test_check_drawcap(self):
        version = package_release.drawcap_version()
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        with tempfile.TemporaryDirectory(dir=install_mod.ROOT) as d:
            good, bad = Path(d) / "good.dll", Path(d) / "bad.dll"
            good.write_bytes(b"MZ\0Draw List Cap\0drawcap\0" + version.encode() + b"\0")
            bad.write_bytes(b"MZ\0Draw List Cap\0drawcap\x009.9.9\0")
            self.assertEqual(package_release.check_drawcap(good), [])
            self.assertEqual(len(package_release.check_drawcap(bad)), 1)

    def test_manifest_resource(self):
        """The built DLLs carry the plugin manifest D2RLoader needs (the core DLL as the control)."""
        self.assertIsNone(package_release.plugin_manifest_abi(b"MZ drawcap"))
        built = [p for p in (install_mod.ROOT / "build" / "plugin" / "Release" / "mxl2012-core.dll", install_mod.DRAWCAP) if p.is_file()]
        if not built:
            self.skipTest("no built plugin DLLs")
        for dll in built:
            self.assertEqual(package_release.plugin_manifest_abi(dll.read_bytes()), 4, dll)

    def test_probe_files_never_ship(self):
        for path in ("d2rloader/plugins/drawcap-probe.txt", "d2rloader/plugins/drawcap-nopatch.txt", "d2rloader/logs/drawcap-stats.csv"):
            self.assertTrue(package_release.FORBIDDEN.search(path), path)
        self.assertFalse(package_release.FORBIDDEN.search(package_release.DRAWCAP["dll"]))

    def test_config_is_preserved(self):
        with tempfile.TemporaryDirectory(dir=install_mod.ROOT) as d:
            mod = Path(d)
            (mod / "d2rloader" / "config").mkdir(parents=True)
            (mod / package_release.DRAWCAP["config"]).write_text("[drawcap]\n", encoding="utf-8")
            self.assertIn(package_release.DRAWCAP["config"], package_release.preserve_list(mod))


if __name__ == "__main__":
    unittest.main()
