"""tools/build_thirdparty_linux.py: its output layout is the one package_release.py reads, and it covers every build_*.ps1
of a bundled third-party plugin. No build here (that needs msvc-wine)."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import re
import tempfile
import unittest
from pathlib import Path

import build_thirdparty_linux as btl
import package_release as pr

HERE = Path(__file__).resolve().parent
# build_<ps1 name> -> the Linux builder's plugin name
PS1 = {"legacy169": "legacy169", "buffhud": "buffhud", "beltrefill": "beltrefill", "controllerqol": "controllerqol",
       "enemyhealthbars": "ehb", "floatingdamage": "fd", "vendorstockrefresh": "vsr"}


class LayoutTest(unittest.TestCase):
    def test_every_plugin_script_has_a_linux_builder(self):
        for ps1 in HERE.glob("build_*.ps1"):
            name = ps1.stem[len("build_"):]
            if name in ("plugin", "native"):  # our own plugins and the native libs: /d2work/toolchains/scripts
                continue
            self.assertIn(name, PS1, f"{ps1.name} has no Linux builder in build_thirdparty_linux.py")
            self.assertIn(PS1[name], btl.BUILDERS)

    def test_outputs_where_package_release_reads_them(self):
        src = (HERE / "build_thirdparty_linux.py").read_text("utf-8")
        rel = {pr.LEGACY169_BUILD: "legacy169", pr.BUFFHUD_BUILD: "buffhud", pr.BELTREFILL_BUILD: "beltrefill",
               pr.CONTROLLERQOL_BUILD: "controllerqol", pr.FD_BUILD: "floatingdamage", pr.EHB_BUILD: "enemyhealthbars"}
        for build, folder in rel.items():
            self.assertEqual(build.name, folder)
            self.assertIn(f'a.out / "{folder}"', src)
        for folder in ("legacy169-src", "buffhud-src", "beltrefill-src", "controllerqol-src", "floatingdamage-src",
                       "enemyhealthbars-src"):
            self.assertIn(f'a.out / "{folder}"', src)
        for name in [Path(pr.LEGACY169["dll"]).name, Path(pr.BUFFHUD["dll"]).name, Path(pr.BELTREFILL["dll"]).name,
                     *pr.FD_FROM.values()]:
            self.assertIn(name, src)

    def test_ehb_pins_match_package_release(self):
        self.assertEqual(btl.EHB_PIN, pr.EHB["commit"])
        self.assertEqual(btl.EHB_URL, pr.EHB["repo"])
        ps1 = (HERE / "build_enemyhealthbars.ps1").read_text("utf-8")
        for value in (btl.EHB_PIN, *btl.EHB_SHARE, *btl.EHB_SOURCE):
            self.assertIn(value, ps1)

    def test_patches_record_as_package_release_reads_them(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "PATCHES"
            patches = sorted((HERE.parent / "third_party" / "auto-belt-refill-mxl2012").glob("*.patch"))
            btl.write_patches(patches, out)
            lines = [ln.strip() for ln in out.read_text("ascii").splitlines() if ln.strip()]
            self.assertEqual(lines, pr.beltrefill_patches())

    def test_wine_only_tests_named_in_controller_qol(self):
        src = (HERE / "build_thirdparty_linux.py").read_text("utf-8")
        names = re.search(r'wine_only = "\^\(([^)]*)\)\$"', src).group(1).split("|")
        self.assertEqual(len(names), 3)


if __name__ == "__main__":
    unittest.main()
