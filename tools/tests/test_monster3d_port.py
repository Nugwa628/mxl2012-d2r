"""Lane m3dlinux: the monster3d stage scripts on Windows and Linux (settings instead of drive paths, the Linux gate reading,
the framework checkout of the capture scripts, the run logs g6_gamerun keeps on Linux)."""
import importlib
import json
import os
import re
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
M3D = ROOT / "tools" / "sprite3d" / "monster3d"
sys.path.insert(0, str(ROOT / "tools"))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)


def load_common():
    sys.path.insert(0, str(M3D))
    sys.modules.pop("common", None)
    return importlib.import_module("common")


class NoWindowsPaths(unittest.TestCase):
    def test_scripts_name_no_drive_or_py_launcher(self):
        drive = re.compile(r"""r?["'][A-Za-z]:[\\/]""")
        bad = []
        for p in sorted(M3D.glob("*.py")):
            text = p.read_text(encoding="utf-8")
            for n, line in enumerate(text.splitlines(), 1):
                if drive.search(line) or '"py", "-3"' in line or "Scripts\\python" in line or "py -3 " in line:
                    bad.append("%s:%d: %s" % (p.name, n, line.strip()))
        self.assertEqual(bad, [])

    def test_capture_scripts_default_to_this_checkout(self):
        for name in ("g6_deathcap.py", "g6_movecap.py"):
            text = (M3D / name).read_text(encoding="utf-8")
            self.assertIn('os.environ.get("MXL_M3D_FRAMEWORK") or Path(__file__).resolve().parents[3]', text, name)
            self.assertNotIn('"hdtools-monster" / "tools"', text, name)
        self.assertEqual((M3D / "g6_movecap.py").resolve().parents[3], ROOT)

    def test_framework_has_the_monster_checks(self):
        text = (ROOT / "tools" / "game_checks.py").read_text(encoding="utf-8")
        for name in ("check_mon_card", "check_mon_turn", "MON_TURN_FACE", "MON_TURN_SPOTS"):
            self.assertIn(name, text)


class Settings(unittest.TestCase):
    def setUp(self):
        self.common = load_common()
        self.tmp = tempfile.TemporaryDirectory()
        self.machine = Path(self.tmp.name) / "machine.json"
        self.machine.write_text(json.dumps({"art_store": "/store/from/machine", "m3d_dir": "/ev/from/machine"}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_env_then_machine_then_default(self):
        c = self.common
        with mock.patch.dict(os.environ, {"MXL_MACHINE": str(self.machine)}):
            os.environ.pop("MXL_ART_STORE", None)
            self.assertEqual(c.setting("MXL_ART_STORE", "art_store"), "/store/from/machine")
            os.environ["MXL_ART_STORE"] = "/store/from/env"
            self.assertEqual(c.setting("MXL_ART_STORE", "art_store"), "/store/from/env")
            self.assertEqual(c.setting("MXL_NOT_SET_X", "not_a_key", "dflt"), "dflt")

    def test_module_paths_follow_the_settings(self):
        env = {"MXL_MACHINE": str(self.machine), "MXL_BLENDER": "/opt/b/blender", "MXL_TRIPOSG_SRC": "/t/src"}
        with mock.patch.dict(os.environ, env):
            for k in ("MXL_ART_STORE", "MXL_M3D_DIR"):
                os.environ.pop(k, None)
            c = load_common()
            self.assertEqual(c.STORE, Path("/store/from/machine"))
            self.assertEqual(c.EV, Path("/ev/from/machine"))
            self.assertEqual(c.BLENDER, Path("/opt/b/blender"))
            self.assertEqual(c.TRIPOSG_SRC, Path("/t/src"))
            self.assertEqual(c.object_path("ab" + "0" * 62), Path("/store/from/machine/objects/sha256/ab/ab" + "0" * 62))

    def test_no_store_is_a_clear_error(self):
        empty = Path(self.tmp.name) / "empty.json"
        empty.write_text("{}")
        with mock.patch.dict(os.environ, {"MXL_MACHINE": str(empty)}):
            os.environ.pop("MXL_ART_STORE", None)
            c = load_common()
            self.assertIsNone(c.STORE)
            with self.assertRaises(SystemExit):
                c.object_path("0" * 64)


class LinuxGate(unittest.TestCase):
    def test_reading_from_gpugate(self):
        c = load_common()
        fake = types.SimpleNamespace(read_linux=lambda: (12.4, "amdgpu", 30.6))
        with mock.patch.dict(sys.modules, {"hdkit.gpugate": fake, "hdkit": types.SimpleNamespace(gpugate=fake)}):
            self.assertEqual(c._linux_reading(), (12, 31))

    def test_failed_reading_closes_the_gate(self):
        c = load_common()

        def boom():
            raise OSError("no sysfs")
        fake = types.SimpleNamespace(read_linux=boom)
        with mock.patch.dict(sys.modules, {"hdkit.gpugate": fake, "hdkit": types.SimpleNamespace(gpugate=fake)}), \
                mock.patch("builtins.print"):
            self.assertEqual(c._linux_reading(), (-1, -1))
        with mock.patch.object(c, "WINDOWS", False), mock.patch.object(c, "_linux_reading", return_value=(-1, -1)), \
                mock.patch.object(c.subprocess, "run", return_value=types.SimpleNamespace(stdout="slot 5: x; lock free;\n")), \
                mock.patch("builtins.print"):
            self.assertFalse(c.gpu_gate(0))


class GamerunLogs(unittest.TestCase):
    def test_linux_logs_come_from_the_run_folder_copies(self):
        load_common()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(sys, "argv", ["g6_gamerun.py", "5", "t", tmp]):
            sys.modules.pop("g6_gamerun", None)
            gr = importlib.import_module("g6_gamerun")
            game, runs = Path(tmp) / "slot", Path(tmp) / "runs"
            game.mkdir()
            kept = runs / "checks-20261120-195121-s5" / "slot-logs-1"
            files = {"loader": kept / "d2rloader" / "logs" / "d2rloader.log",
                     "mxl": kept / "mods" / "mxl2012" / "d2rloader" / "logs" / "mxl2012-core.log"}
            crash = kept / "d2rloader" / "crashes" / "report.log"
            for f in list(files.values()) + [crash]:
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("x")
            gr.game_slots = types.SimpleNamespace(slot_dir=lambda n: str(game))
            got, crashes = gr.run_logs(runs, time.time() - 5)
            self.assertEqual(got, files)
            self.assertEqual(crashes, [crash])
            self.assertEqual(gr.SLOT, 5)
            self.assertEqual(gr.FWT, ROOT)
            self.assertIsNone(gr.DLL)


if __name__ == "__main__":
    unittest.main()
