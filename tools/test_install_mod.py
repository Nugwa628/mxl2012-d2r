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
        for section, key, value, forced, _ in install_mod.TOML_KEYS:
            text = install_mod.apply_toml_key(text, section, key, value, forced)
        return text

    def test_another_mods_file_gets_extended_mode(self):
        out = self.ensure_all('[d2rloader]\ndefault_mod = "OtherMod"\n')
        self.assertIn('[d2rcore.save_format]\nmode = "extended"', out)
        self.assertIn('default_mod = "OtherMod"', out)

    def test_commented_mode_is_replaced(self):
        out = self.ensure_all('[d2rcore.save_format]\n# mode = "extended"\n')
        self.assertIn('[d2rcore.save_format]\nmode = "extended"\n', out)

    def test_installed_file_unchanged(self):
        text = ('# mxl2012 migration: ctrl-stat-ranges-on-v1\n[d2rcore.save_format]\nmode = "extended"\n\n[d2rcore.player]\nalways_enable_rotw_legacy_graphics_keybind = true\n'
                '\n[d2rcore.items]\nitem_stat_ranges = true\n\n[d2rcore.stash]\nadd_shared_tabs = 2\n')
        self.assertEqual(self.ensure_all(text), text)

    def test_stat_ranges_on(self):
        """docs/bugs.md #528 (owner decision 2026-11-07): D2RLoader's Ctrl stat ranges are on in the mod's config."""
        out = self.ensure_all('[d2rcore.save_format]\nmode = "extended"\n')
        self.assertIn("[d2rcore.items]\nitem_stat_ranges = true\n", out)
        out = self.ensure_all("[d2rcore.items]\n# item_stat_ranges = true\nmaximum_sockets = true\n")
        self.assertIn("[d2rcore.items]\nitem_stat_ranges = true\nmaximum_sockets = true\n", out)

    def test_ranges_migration_then_player_choice(self):
        marker = "# mxl2012 migration: ctrl-stat-ranges-on-v1"
        for text in ("[d2rcore.items]\n  item_stat_ranges = false # mine",
                     "d2rcore.items.item_stat_ranges = false # mine\n[x]\nitem_stat_ranges = false\n",
                     "\ufeff[d2rcore.items]\r\n  item_stat_ranges = false # mine"):
            out = install_mod.apply_toml_key(text, "d2rcore.items", "item_stat_ranges", "true", "once")
            bom = "\ufeff" if text.startswith("\ufeff") else ""
            nl = "\r\n" if "\r\n" in text else "\n"
            self.assertEqual(out, bom + marker + nl + text[len(bom):].replace("false", "true", 1))
            self.assertEqual(install_mod.apply_toml_key(out, "d2rcore.items", "item_stat_ranges", "true", "once"), out)
            edited = out.replace("item_stat_ranges = true", "item_stat_ranges = false", 1)
            self.assertEqual(install_mod.apply_toml_key(edited, "d2rcore.items", "item_stat_ranges", "true", "once"), edited)
        self.assertEqual(install_mod.apply_toml_key(marker + "\n", "d2rcore.items", "item_stat_ranges", "true", "once"), marker + "\n")

    ROTW = "always_enable_rotw_legacy_graphics_keybind"

    def test_rotw_legacy_toggle_from_the_commented_template(self):
        """docs/bugs.md #498: the owner's kept mod file had only the commented template line; the global file's false won."""
        for line in (f"# {self.ROTW} = true", f"#{self.ROTW}=true", f"  ##  {self.ROTW} = false  # template"):
            text = f"[d2rcore.player]\n# Keep the Toggle Renderer keybind ...\n{line}\n\n[d2rcore.stash]\nadd_shared_tabs = 0\n"
            out = install_mod.ensure_toml_key(text, "d2rcore.player", self.ROTW, "true")
            self.assertEqual(out, text.replace(line, f"{self.ROTW} = true"), line)

    def test_rotw_legacy_toggle_added_under_header_or_as_table(self):
        out = install_mod.ensure_toml_key("[d2rcore.player]\nenable_respec = false\n", "d2rcore.player", self.ROTW, "true")
        self.assertEqual(out, f"[d2rcore.player]\n{self.ROTW} = true\nenable_respec = false\n")
        out = install_mod.ensure_toml_key('[d2rloader]\ndefault_mod = "x"\n', "d2rcore.player", self.ROTW, "true")
        self.assertEqual(out, f'[d2rloader]\ndefault_mod = "x"\n\n[d2rcore.player]\n{self.ROTW} = true\n')
        self.assertEqual(install_mod.ensure_toml_key("", "d2rcore.player", self.ROTW, "true"),
                         f"[d2rcore.player]\n{self.ROTW} = true\n")
        self.assertIn(f"[d2rcore.player]\n{self.ROTW} = true\n", self.ensure_all('[d2rcore.save_format]\nmode = "extended"\n'))

    def test_unforced_key_set_by_hand_is_kept(self):
        for text in (f"[d2rcore.player]\n{self.ROTW} = false # mine\n", f"d2rcore.player.{self.ROTW} = false\n[a]\nb = 1\n",
                     f"[d2rcore.player] # player\n  {self.ROTW}= false\n"):
            self.assertEqual(install_mod.ensure_toml_key(text, "d2rcore.player", self.ROTW, "true"), text)

    def test_shared_tabs_at_least_rotw(self):
        """docs/bugs.md #535 (owner 2026-11-04): 2 shared pages after D2R's 3 (5, as a RotW game has); never fewer than set."""
        self.assertEqual(install_mod.EXTRA_SHARED_TABS, 2)
        mode = {key: f for _, key, _, f, _ in install_mod.TOML_KEYS}
        self.assertEqual(mode["add_shared_tabs"], "min")
        out = self.ensure_all('[d2rcore.save_format]\nmode = "extended"\n')
        self.assertIn("[d2rcore.stash]\nadd_shared_tabs = 2\n", out)
        tmpl = "[d2rcore.stash]\n# Add more shared stash tabs after the vanilla tabs.\n# add_shared_tabs = 0\n\n# x\nset_materials_limit = 99\n"
        self.assertEqual(install_mod.ensure_toml_min(tmpl, "d2rcore.stash", "add_shared_tabs", "2"),
                         tmpl.replace("# add_shared_tabs = 0", "add_shared_tabs = 2"))
        for low, want in (("add_shared_tabs = 0", "add_shared_tabs = 2"), ("add_shared_tabs = 1 # mine", "add_shared_tabs = 2 # mine"),
                          ('add_shared_tabs = "x"', "add_shared_tabs = 2")):
            self.assertEqual(install_mod.ensure_toml_min(f"[d2rcore.stash]\n{low}\n", "d2rcore.stash", "add_shared_tabs", "2"),
                             f"[d2rcore.stash]\n{want}\n", low)
        # A larger value stays: lowering it would hide the items on the pages past the new count (another mod's 100 tabs, bug #512)
        for keep in ("[d2rcore.stash]\nadd_shared_tabs = 2\n", "[d2rcore.stash]\nadd_shared_tabs = 100  # big stash\n",
                     "d2rcore.stash.add_shared_tabs = 7\n[a]\nb = 1\n", "﻿[d2rcore.stash]\r\nadd_shared_tabs = 3\r\n"):
            self.assertEqual(install_mod.ensure_toml_min(keep, "d2rcore.stash", "add_shared_tabs", "2"), keep)
        self.assertEqual(install_mod.ensure_toml_min("d2rcore.stash.add_shared_tabs = 1\n", "d2rcore.stash", "add_shared_tabs", "2"),
                         "d2rcore.stash.add_shared_tabs = 2\n")
        self.assertEqual(install_mod.ensure_toml_min("[d2rcore.other]\nadd_shared_tabs = 9\n", "d2rcore.stash", "add_shared_tabs", "2"),
                         "[d2rcore.other]\nadd_shared_tabs = 9\n\n[d2rcore.stash]\nadd_shared_tabs = 2\n")

    def test_forced_keys(self):
        """Owner decision 2026-11-04 (#498): the G toggle and save format stay forced; ranges migrate once."""
        forced = {key: f for _, key, _, f, _ in install_mod.TOML_KEYS}
        self.assertEqual(forced["item_stat_ranges"], "once")
        self.assertTrue(forced["mode"] and forced[self.ROTW])

    def test_rotw_legacy_toggle_set_by_hand_becomes_true(self):
        """Owner decision 2026-11-04 (#498): a hand-set or template false ends as true; indent and comment stay."""
        for text, want in ((f"[d2rcore.player]\n{self.ROTW} = false # mine\n", f"[d2rcore.player]\n{self.ROTW} = true # mine\n"),
                           (f"d2rcore.player.{self.ROTW} = false\n[a]\nb = 1\n", f"d2rcore.player.{self.ROTW} = true\n[a]\nb = 1\n"),
                           (f"[d2rcore.player] # player\n  {self.ROTW}= false\n", f"[d2rcore.player] # player\n  {self.ROTW} = true\n"),
                           (f"[d2rcore.player]\n{self.ROTW} = true # mine\n", f"[d2rcore.player]\n{self.ROTW} = true # mine\n")):
            self.assertEqual(install_mod.ensure_toml_key(text, "d2rcore.player", self.ROTW, "true", True), want, text)
        # D2RLoader 1.3.1's template line is uncommented: `always_enable_rotw_legacy_graphics_keybind = false`
        template = f"[d2rcore.player]\n# Keep the Toggle Renderer keybind ...\n{self.ROTW} = false\nenable_respec = false\n"
        self.assertIn(f"{self.ROTW} = true\nenable_respec = false\n", self.ensure_all(template))
        self.assertNotIn(f"{self.ROTW} = false", self.ensure_all(template))

    def test_forced_value_with_crlf_and_quotes(self):
        out = install_mod.ensure_toml_key(f"[d2rcore.player]\r\n{self.ROTW} = false\r\n", "d2rcore.player", self.ROTW, "true", True)
        self.assertEqual(out, f"[d2rcore.player]\r\n{self.ROTW} = true\r\n")
        out = install_mod.ensure_toml_key('[d2rcore.save_format]\nmode = "retail # x" # was\n', "d2rcore.save_format", "mode",
                                          '"extended"', True)
        self.assertEqual(out, '[d2rcore.save_format]\nmode = "extended" # was\n')

    def test_bom_and_crlf_stay(self):
        text = f"﻿[d2rcore.player]\r\n# {self.ROTW} = true\r\nenable_respec = false\r\n"
        out = install_mod.ensure_toml_key(text, "d2rcore.player", self.ROTW, "true")
        self.assertEqual(out, f"﻿[d2rcore.player]\r\n{self.ROTW} = true\r\nenable_respec = false\r\n")
        out = install_mod.ensure_toml_key("﻿[d2rloader]\r\n", "d2rcore.player", self.ROTW, "true")
        self.assertEqual(out, f"﻿[d2rloader]\r\n\r\n[d2rcore.player]\r\n{self.ROTW} = true\r\n")


if __name__ == "__main__":
    unittest.main()
