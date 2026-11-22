"""VRAM cap of the Linux slots (lane vramcap, 2026-11-21): game_slots.vram_mb picks the cap (MXL_VRAM_MB, else the
profile's default), vram_env turns it into DXVK_CONFIG dxgi.maxDeviceMemory, launch() passes it to the game only, and
parallel_smoke --vram-mb hands it on. Temp files inside the project, no game."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import game_slots  # noqa: E402
import parallel_smoke  # noqa: E402


def no_env():
    env = {k: v for k, v in os.environ.items() if k not in ("MXL_VRAM_MB", "DXVK_CONFIG", "MXL_PROFILE")}
    return patch.dict(os.environ, env, clear=True)


class VramMb(unittest.TestCase):
    def test_profile_defaults(self):
        with no_env():
            self.assertEqual(game_slots.vram_mb("test"), 2048)
            self.assertEqual(game_slots.vram_mb("visual"), 3072)
            self.assertEqual(game_slots.vram_mb(), 2048)  # default profile test

    def test_env_and_value_override(self):
        with no_env(), patch.dict(os.environ, {"MXL_VRAM_MB": "1536"}):
            self.assertEqual(game_slots.vram_mb("visual"), 1536)
            self.assertEqual(game_slots.vram_mb("visual", "4096"), 4096)  # an explicit value wins over the env
        for off in ("0", "none", "OFF", "no"):
            with no_env(), patch.dict(os.environ, {"MXL_VRAM_MB": off}):
                self.assertIsNone(game_slots.vram_mb("test"))
            with no_env():
                self.assertIsNone(game_slots.vram_mb("test", off))

    def test_bad_values(self):
        for bad in ("lots", "100", "-5"):
            with no_env(), self.assertRaises(SystemExit):
                game_slots.vram_mb("test", bad)


class VramEnv(unittest.TestCase):
    def test_none_adds_nothing(self):
        self.assertEqual(game_slots.vram_env(None, {}), {})

    def test_cap(self):
        self.assertEqual(game_slots.vram_env(2048, {}), {"DXVK_CONFIG": "dxgi.maxDeviceMemory = 2048"})

    def test_keeps_other_options_and_replaces_its_own(self):
        base = {"DXVK_CONFIG": "dxgi.maxFrameRate = 30; dxgi.maxDeviceMemory = 999"}
        self.assertEqual(game_slots.vram_env(3072, base)["DXVK_CONFIG"],
                         "dxgi.maxFrameRate = 30; dxgi.maxDeviceMemory = 3072")


class Launch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def launch(self, env, **kw):
        with game_slots.backend("linux"), no_env(), patch.dict(os.environ, env), \
                patch.object(game_slots, "ensure_drive"), patch.object(game_slots, "apply_launch_settings"), \
                patch.object(game_slots, "settings_path", lambda n: os.path.join(self.tmp, "Settings.json")), \
                patch.object(game_slots, "prefix_pids", lambda n, proc=None: []), \
                patch.object(game_slots, "slot_dir", lambda n: self.tmp), \
                patch.object(game_slots, "loader_name", lambda g: "D2RLoader-s6.exe"), \
                patch.object(game_slots, "windows_path", lambda n, p: "D:\\D2RLoader-s6.exe"), \
                patch.object(game_slots, "wine_env", lambda n, log_dir=None: {"WINEPREFIX": "/x"}), \
                patch.object(game_slots.subprocess, "Popen") as popen:
            game_slots.launch(6, ["-mod", "mxl2012"], **kw)
        return popen.call_args.kwargs["env"]

    def test_profile_default_reaches_the_game(self):
        self.assertEqual(self.launch({"MXL_PROFILE": "visual"})["DXVK_CONFIG"], "dxgi.maxDeviceMemory = 3072")
        self.assertEqual(game_slots.LAST_VRAM[6], 3072)
        self.assertEqual(self.launch({})["DXVK_CONFIG"], "dxgi.maxDeviceMemory = 2048")

    def test_env_off_and_explicit(self):
        self.assertNotIn("DXVK_CONFIG", self.launch({"MXL_VRAM_MB": "none"}))
        self.assertIsNone(game_slots.LAST_VRAM[6])
        self.assertEqual(self.launch({}, vram="1024")["DXVK_CONFIG"], "dxgi.maxDeviceMemory = 1024")

    def test_wine_env_alone_has_no_cap(self):  # helpers (wctl, setup) in the prefix are not given the cap
        with game_slots.backend("linux"), no_env(), patch.object(game_slots, "compat_dir", lambda n: "/c"), \
                patch.object(game_slots, "prefix_dir", lambda n: "/p"):
            self.assertNotIn("DXVK_CONFIG", game_slots.wine_env(6, base={}))


class SwapRule(unittest.TestCase):
    def test_swap_rule_can_be_off(self):
        s = [{"availMB": 40000, "swapMB": 1000}, {"availMB": 40000, "swapMB": 3000}]
        self.assertIn("swap", parallel_smoke.memory_alarm(s, 8192))
        self.assertIsNone(parallel_smoke.memory_alarm(s, 8192, 0))
        self.assertIn("MemAvailable", parallel_smoke.memory_alarm(s, 48000, 0))
        self.assertEqual(parallel_smoke.parse_args([]).abort_swap_mb, 256)


class ParallelSmokeArg(unittest.TestCase):
    def test_vram_arg(self):
        self.assertIsNone(parallel_smoke.parse_args([]).vram_mb)
        self.assertEqual(parallel_smoke.parse_args(["--vram-mb", "2048"]).vram_mb, "2048")


if __name__ == "__main__":
    unittest.main()
