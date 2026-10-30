"""Slot selection/refusal checks; no game files or saves are written."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import game_slots
import install_mod
import machine_fixture  # a neutral machine.json: CI has none


class InstallSlotTests(unittest.TestCase):
    def setUp(self):
        machine_fixture.use_neutral_machine(self)
        self.env = patch.dict(os.environ, MXL_SLOT="3", MXL_RUN="waypoints")
        self.env.start()
        self.addCleanup(self.env.stop)
        p = patch.object(game_slots, "present", return_value=True)  # slot 3's folder need not exist on this PC
        p.start()
        self.addCleanup(p.stop)

    def test_environment_selects_slot_three(self):
        with patch.object(sys, "argv", ["install_mod.py"]), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(install_mod, "install_one", return_value=0) as install, \
                patch.object(game_slots, "setup"):
            self.assertEqual(install_mod.main(), 0)
            self.assertEqual(install.call_args.args[:3], (Path(game_slots.slot_dir(3)), "mxl2012", "mxl2012-s3/"))

    def test_foreign_lock_refuses_before_file_changes(self):
        with patch.object(game_slots, "lock_info", return_value=("lock", "another pid=0")), \
                patch.object(Path, "exists", side_effect=AssertionError("refused install probed game files")), \
                patch.object(install_mod.shutil, "rmtree") as remove:
            self.assertEqual(install_mod.install_one(Path(game_slots.slot_dir(3)), "mxl2012", "mxl2012-s3/"), 1)
            remove.assert_not_called()

    def test_running_game_refuses_even_with_our_lock(self):
        with patch.object(game_slots, "lock_info", return_value=("lock", "waypoints pid=0")), \
                patch.object(game_slots, "slot_processes", return_value=[(123, "D2RLoader-s3.exe")]), \
                patch.object(Path, "exists", side_effect=AssertionError("running game files were probed")), \
                patch.object(install_mod.shutil, "rmtree") as remove:
            self.assertEqual(install_mod.install_one(Path(game_slots.slot_dir(3)), "mxl2012", "mxl2012-s3/"), 1)
            remove.assert_not_called()

    def test_refused_install_does_not_change_slot_config(self):
        with patch.object(sys, "argv", ["install_mod.py"]), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(install_mod, "install_one", return_value=1), \
                patch.object(game_slots, "setup") as setup:
            self.assertEqual(install_mod.main(), 1)
            setup.assert_not_called()

    def test_refuses_without_machine_json(self):
        missing = os.path.join(game_slots.REPO, "work", "no-such-machine.json")
        with patch.dict(os.environ, {"MXL_MACHINE": missing}), \
                patch.object(sys, "argv", ["install_mod.py", "--placeholder"]), \
                patch.object(install_mod, "install_one") as install, \
                patch.object(game_slots, "setup") as setup:
            with self.assertRaises(SystemExit) as cm:
                install_mod.main()
            self.assertIn("refusing to run", str(cm.exception))
            self.assertIn("shared_lock_dir", str(cm.exception))
            install.assert_not_called()
            setup.assert_not_called()


class SaveFormatKeyTests(unittest.TestCase):
    """docs/bugs.md #512: a d2rloader.toml without the save format gets D2RLoader's extended mode back."""

    def ensure_all(self, text):
        for section, key, value, _ in install_mod.TOML_KEYS:
            text = install_mod.ensure_toml_key(text, section, key, value)
        return text

    def test_another_mods_file_gets_extended_mode(self):
        out = self.ensure_all('[d2rloader]\ndefault_mod = "OtherMod"\n')
        self.assertIn('[d2rcore.save_format]\nmode = "extended"', out)
        self.assertIn('default_mod = "OtherMod"', out)

    def test_commented_mode_is_replaced(self):
        out = self.ensure_all('[d2rcore.save_format]\n# mode = "extended"\n')
        self.assertIn('[d2rcore.save_format]\nmode = "extended"\n', out)

    def test_installed_file_unchanged(self):
        text = '[d2rcore.save_format]\nmode = "extended"\n\n[d2rcore.player]\nalways_enable_rotw_legacy_graphics_keybind = true\n'
        self.assertEqual(self.ensure_all(text), text)


if __name__ == "__main__":
    unittest.main()
