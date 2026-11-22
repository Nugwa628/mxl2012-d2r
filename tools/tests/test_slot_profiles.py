"""Graphics profiles of the Linux slots (lane lowprofile, 2026-11-21): tools/slot_profiles/{test,visual}.json hold only
graphics keys; game_slots.apply_profile writes one into a slot's Settings.json (other keys kept, D2R's layout, refused
while the prefix runs); launch() applies MXL_PROFILE (default test); game_checks asks for "visual" for HD visual checks;
parallel_smoke passes a profile per slot. Temp files inside the project, no game."""
import json
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

# keys a profile must never carry: the player's gamma, sound, key bindings, the legacy toggle the checks switch, ...
NOT_GRAPHICS = ("Gamma", "GammaHD", "Legacy Graphics Mode", "Graphics Mode", "Master Volume", "Language",
                "Default Key Bindings", "Aux Battle.net", "User Last Online")


class Profiles(unittest.TestCase):
    def test_files_hold_the_same_graphics_keys_only(self):
        t, v = game_slots.load_profile("test"), game_slots.load_profile("visual")
        self.assertEqual(set(t), set(v))
        for k in NOT_GRAPHICS:
            self.assertNotIn(k, t)

    def test_window_stays_1600x900_windowed(self):  # the checks click fixed spots of the 1600 x 900 client
        for name in game_slots.PROFILES:
            p = game_slots.load_profile(name)
            # visual4k (lane hdmaps2): 3840x2160 for map captures, run with MXL_CLIENT=3840x2160 (the click tables are
            # fractions of the client, so a 16:9 client keeps them)
            self.assertEqual(p["Screen Resolution (Windowed)"], "3840x2160" if name == "visual4k" else "1600x900")
            self.assertEqual(p["Window Mode"], 1)

    def test_test_profile_is_the_low_windows_profile(self):
        p = game_slots.load_profile("test")
        self.assertEqual((p["Framerate Cap"], p["Framerate Target"], p["VSync"]), (1, 30, 0))
        self.assertEqual(p["Resolution Scale"], 50)
        for k in ("Texture Quality", "Ambient Occlusion Quality", "Anti Aliasing", "Shadow Quality", "Vfx Quality",
                  "Character Detail", "Atmospherics Quality"):
            self.assertEqual(p[k], 0, k)
        v = game_slots.load_profile("visual")
        self.assertEqual((v["Resolution Scale"], v["Texture Quality"], v["Framerate Cap"]), (100, 4, 0))

    def test_profile_name(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MXL_PROFILE", None)
            self.assertEqual(game_slots.profile_name(), "test")
            os.environ["MXL_PROFILE"] = "Visual"
            self.assertEqual(game_slots.profile_name(), "visual")
            self.assertEqual(game_slots.profile_name("test"), "test")
            with self.assertRaises(SystemExit):
                game_slots.profile_name("ultra")

    def test_visual_checks_ask_for_visual(self):
        self.assertEqual(game_slots.profile_for_checks(["mxl2012", "acts"]), "test")
        self.assertEqual(game_slots.profile_for_checks(None), "test")
        self.assertEqual(game_slots.profile_for_checks(["mxl2012", "signoff"]), "visual")
        self.assertEqual(game_slots.profile_for_checks(["hdl_look"]), "visual")
        self.assertEqual(game_slots.profile_for_checks(["hdl_look"], explicit="test"), "test")  # MXL_PROFILE wins


class Apply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="profiles-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "mxl2012-s6", "Settings.json")
        os.makedirs(os.path.dirname(self.path))
        self.orig = dict(game_slots.load_profile("visual"), **{"Gamma": 155, "Legacy Graphics Mode": 1, "Always Run": 0})
        Path(self.path).write_text(json.dumps(self.orig, indent=4))
        p = patch.object(game_slots, "prefix_pids", lambda n, proc=None: [])
        p.start()
        self.addCleanup(p.stop)

    def read(self):
        return json.loads(Path(self.path).read_text())

    def test_writes_graphics_keys_and_keeps_the_rest(self):
        prof, changed = game_slots.apply_profile(6, "test", path=self.path)
        self.assertEqual(prof, "test")
        self.assertEqual(changed["Resolution Scale"], (100, 50))
        got = self.read()
        self.assertEqual({k: got[k] for k in game_slots.load_profile("test")}, game_slots.load_profile("test"))
        self.assertEqual((got["Gamma"], got["Legacy Graphics Mode"], got["Always Run"]), (155, 1, 0))
        self.assertEqual(list(got), list(self.orig))  # key order kept
        text = Path(self.path).read_text()
        self.assertTrue(text.startswith('{\n    "'))
        self.assertTrue(text.endswith("}"))  # D2R's layout: no newline at the end
        self.assertFalse(os.path.exists(self.path + ".mxl2012-tmp"))

    def test_back_to_visual_and_nothing_to_do_twice(self):
        game_slots.apply_profile(6, "test", path=self.path)
        game_slots.apply_profile(6, "visual", path=self.path)
        self.assertEqual(self.read(), self.orig)
        self.assertEqual(game_slots.apply_profile(6, "visual", path=self.path), ("visual", {}))

    def test_refused_while_the_prefix_runs(self):
        with patch.object(game_slots, "prefix_pids", lambda n, proc=None: [4242]):
            with self.assertRaises(SystemExit):
                game_slots.apply_profile(6, "test", path=self.path)
            self.assertEqual(self.read(), self.orig)
            # nothing to change: no write, so no refusal either
            self.assertEqual(game_slots.apply_profile(6, "visual", path=self.path), ("visual", {}))

    def test_missing_file_gets_the_profile_keys(self):
        os.remove(self.path)
        game_slots.apply_profile(6, "test", path=self.path)
        self.assertEqual(self.read(), game_slots.load_profile("test"))

    def test_launch_applies_the_env_profile(self):
        with game_slots.backend("linux"), \
                patch.object(game_slots, "ensure_drive"), patch.object(game_slots, "apply_launch_settings"), \
                patch.object(game_slots, "settings_path", lambda n: self.path), \
                patch.object(game_slots, "slot_dir", lambda n: self.tmp), \
                patch.object(game_slots, "loader_name", lambda g: "D2RLoader-s6.exe"), \
                patch.object(game_slots, "windows_path", lambda n, p: "D:\\D2RLoader-s6.exe"), \
                patch.object(game_slots, "wine_env", lambda n, log_dir=None: {}), \
                patch.object(game_slots.subprocess, "Popen") as popen, \
                patch.dict(os.environ, {"MXL_PROFILE": "test"}):
            game_slots.launch(6, ["-mod", "mxl2012"])
            self.assertTrue(popen.called)
        self.assertEqual(self.read()["Resolution Scale"], 50)
        self.assertEqual(game_slots.LAST_PROFILE[6][0], "test")


class ParallelSmoke(unittest.TestCase):
    def test_profile_arguments(self):
        a = parallel_smoke.parse_args(["--slots", "2,5", "--visual-slots", "5"])
        self.assertIsNone(a.profile)
        self.assertEqual(a.visual_slots, "5")
        self.assertEqual(parallel_smoke.parse_args(["--profile", "visual"]).profile, "visual")
        with self.assertRaises(SystemExit), patch("sys.stderr"):
            parallel_smoke.parse_args(["--profile", "ultra"])


if __name__ == "__main__":
    unittest.main()
