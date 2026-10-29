"""Game slots 4 and 5 (owner-approved 2026-10-28, copies of slot 2's folder): set up and run like slot 3, and a slot whose
folder does not exist yet is shown as MISSING by `status` and refused cleanly by every tool, before anything is locked or
written. The slot folders, locks, runs and saves are temp folders inside the project (tools/projtemp.py); no game starts."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import d2r_game  # noqa: E402
import game_ctl  # noqa: E402
import game_slots  # noqa: E402
import machine_fixture  # noqa: E402  (a neutral machine.json: CI has none)
import install_mod  # noqa: E402
import lane_setup  # noqa: E402
import localconfig  # noqa: E402
import parallel_smoke  # noqa: E402
import release_install  # noqa: E402
import slot_share  # noqa: E402


class Names(unittest.TestCase):
    def setUp(self):
        machine_fixture.use_neutral_machine(self)
        p = patch.object(game_slots, "LOCK_ROOT", localconfig.machine()["shared_lock_dir"])
        p.start()
        self.addCleanup(p.stop)

    def test_slots_four_and_five_are_like_three(self):
        self.assertEqual(game_slots.SLOTS, (1, 2, 3, 4, 5))
        with patch.dict(os.environ, {}, clear=False):
            for n in (4, 5):
                os.environ.pop(f"MXL_SLOT{n}_DIR", None)
            self.assertEqual(game_slots.slot_dir(4), r"D:\D2R-93847-s4")
            self.assertEqual(game_slots.slot_dir(5), r"D:\D2R-93847-s5")
        for n in (4, 5):
            self.assertEqual(game_slots.require_slot(str(n)), n)
            self.assertEqual(game_slots.save_name(n), f"mxl2012-s{n}")
            self.assertEqual([os.path.basename(p) for p in game_slots.lock_paths(n)], [f"game.lock.{n}"])
            self.assertIn(f"d2rloader-s{n}.exe", game_slots.ALL_IMAGES)
            self.assertEqual(game_slots.foreign_game(n, "x", [(1, "D2RLoader-s4.exe")]), [], "not an owner slot")
        with patch.dict(os.environ, {"MXL_SLOT5_DIR": r"E:\five"}):
            self.assertEqual(game_slots.slot_dir(5), r"E:\five")
        self.assertEqual(release_install.RELEASE_SLOTS, (2, 3, 4, 5))


class TempSlots(unittest.TestCase):
    """Slot 4 is a fake D2R folder, slot 5 does not exist."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="slots45-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        machine_fixture.use_neutral_machine(self, shared_lock_dir=os.path.join(self.tmp, "locks"))
        self.s4, self.s5 = os.path.join(self.tmp, "D2R-93847-s4"), os.path.join(self.tmp, "D2R-93847-s5")
        g = Path(self.s4)
        (g / "mods" / "mxl2012" / "mxl2012.mpq").mkdir(parents=True)
        (g / "D2RLoader.exe").write_bytes(b"MZ loader")
        self.locks, self.saves = os.path.join(self.tmp, "locks"), os.path.join(self.tmp, "saves")
        for p in (patch.object(game_slots, "LOCK_ROOT", self.locks), patch.object(game_slots, "RUNS", os.path.join(self.tmp, "runs")),
                  patch.object(game_slots, "SAVE_ROOT", self.saves),
                  patch.dict(os.environ, {"MXL_SLOT4_DIR": self.s4, "MXL_SLOT5_DIR": self.s5, "MXL_RUN": "lane-a",
                                          **{f"MXL_SLOT{n}_DIR": os.path.join(self.tmp, f"none-{n}") for n in (1, 2, 3)}})):
            p.start()
            self.addCleanup(p.stop)

    def cli(self, mod, argv, capture=True):
        out = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(out) if capture else contextlib.nullcontext():
            try:
                rc = mod.main()
            except SystemExit as e:
                return e.code, out.getvalue()
        return rc, out.getvalue()

    def assertRefused(self, fn, *a):
        with self.assertRaises(SystemExit) as cm:
            fn(*a)
        self.assertIn("game slot 5 is missing", str(cm.exception))
        self.assertIn("does not exist", str(cm.exception))
        self.assertFalse(os.path.exists(self.s5), "nothing made for a missing slot")
        self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock.5")), "a missing slot is never locked")

    def test_setup_makes_the_renamed_loader_and_the_save_folder(self):
        msg = game_slots.setup(4)
        self.assertIn("loader D2RLoader-s4.exe", msg)
        self.assertEqual((Path(self.s4) / "D2RLoader-s4.exe").read_bytes(), b"MZ loader")
        self.assertTrue(os.path.isdir(os.path.join(self.saves, "mxl2012-s4")))
        self.assertIn('"savepath": "mxl2012-s4/"', (Path(self.s4) / "mods" / "mxl2012" / "modinfo.json").read_text(encoding="utf-8"))
        self.assertEqual(game_slots.loader_name(self.s4), "D2RLoader-s4.exe")
        self.assertEqual(game_slots.slot_of_game_dir(self.s4), 4)

    def test_status_and_setup_report_the_missing_slot(self):
        rc, out = self.cli(game_slots, ["game_slots.py", "status"])
        line5 = next(line for line in out.splitlines() if line.startswith("slot 5:"))
        self.assertIn("MISSING", line5)
        self.assertIn("does not exist", line5)
        self.assertIn("lock free", line5)
        self.assertIn(" ok;", next(line for line in out.splitlines() if line.startswith("slot 4:")))
        self.assertIn("MISSING", game_slots.setup(5))
        rc, out = self.cli(game_slots, ["game_slots.py", "setup", "5"])
        self.assertEqual(rc, 1)
        rc, out = self.cli(game_slots, ["game_slots.py", "setup", "4"])
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(self.s5))

    def test_present_set_skips_the_missing_slot(self):
        with patch.object(game_slots, "DEFAULT_SET", (4, 5)):
            self.assertEqual(game_slots.present_set(), [4])
        self.assertEqual(game_slots.require_present(4), 4)
        self.assertRefused(game_slots.require_present, 5)

    def test_lock_and_install_cli_refuse_the_missing_slot(self):
        for argv in (["game_slots.py", "lock", "5", "lane-a"], ["game_slots.py", "install", "5"]):
            with patch.object(game_slots.subprocess, "call", side_effect=AssertionError("installer started")):
                rc, _ = self.cli(game_slots, argv)
            self.assertIn("game slot 5 is missing", str(rc))
            self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock.5")))
        rc, _ = self.cli(game_slots, ["game_slots.py", "lock", "4", "lane-a"])
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isdir(os.path.join(self.locks, "game.lock.4")))
        self.assertEqual(self.cli(game_slots, ["game_slots.py", "unlock", "4", "lane-a"])[0], 0)
        self.assertEqual(self.cli(game_slots, ["game_slots.py", "unlock", "5"])[0], 0, "unlock of a missing slot is harmless")

    def test_install_mod_refuses_and_all_skips_the_missing_slot(self):
        with patch.object(install_mod, "SRC", Path(self.tmp)), patch.object(Path, "exists", return_value=True), \
                patch.object(install_mod, "install_one", return_value=0) as one, patch.object(game_slots, "setup"):
            rc, _ = self.cli(install_mod, ["install_mod.py", "--slot", "5"])
            self.assertIn("game slot 5 is missing", str(rc))
            one.assert_not_called()
            with patch.object(game_slots, "DEFAULT_SET", (4, 5)):
                self.assertEqual(self.cli(install_mod, ["install_mod.py", "--slot", "all"])[0], 0)
            self.assertEqual([c.args[0] for c in one.call_args_list], [Path(self.s4)])

    def test_slot_share_begin_refuses_the_missing_slot(self):
        self.assertRefused(slot_share.begin, 5, "lane-a")

    def test_game_ctl_refuses_the_missing_slot_and_tags_slot_four(self):
        with patch.object(game_ctl, "SLOT", 5), patch.object(game_ctl, "GAME_DIR", self.s5):
            rc, _ = self.cli(game_ctl, ["game_ctl.py", "start"], capture=False)  # main() reconfigures the real stdout
        self.assertIn("game slot 5 is missing", str(rc))
        plugins = Path(self.s4, "mods", "mxl2012", "d2rloader", "plugins")
        plugins.mkdir(parents=True)
        with patch.object(game_ctl, "SLOT", 4), patch.object(game_ctl, "GAME_DIR", self.s4), patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MXL_HARNESS_WORDS", None)
            os.environ.pop("MXL_CONTROL", None)
            game_ctl.harness_switch(True)
            self.assertEqual((plugins / "mxl2012-testharness.txt").read_text(), "volserial tag=s4")
            game_ctl.harness_switch(False)
        self.assertFalse((plugins / "mxl2012-testharness.txt").exists())

    def test_d2r_game_parallel_smoke_lane_setup_and_release_install_refuse(self):
        with patch.dict(os.environ, {"MXL_SLOT": "5"}):
            os.environ.pop("MXL_D2R_GAME", None)
            self.assertRefused(d2r_game.read_game_dir)
        with patch.dict(os.environ, {"MXL_D2R_GAME": self.s5}):
            self.assertRefused(d2r_game.read_game_dir)
        with patch.dict(os.environ, {"MXL_SLOT": "4"}):
            os.environ.pop("MXL_D2R_GAME", None)
            self.assertEqual(d2r_game.read_game_dir(), self.s4)
        self.assertRefused(parallel_smoke.main, ["--slots", "4,5", "--name", "x"])
        self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock.4")), "nothing locked before the refusal")
        self.assertRefused(lane_setup.main, ["--cache-from-slot", "5"])
        rc, _ = self.cli(release_install, ["release_install.py", "install", "--slot", "5"])
        self.assertIn("game slot 5 is missing", str(rc))
        rc, _ = self.cli(release_install, ["release_install.py", "install", "--slot", "1"])
        self.assertIn("--slot 2, 3, 4 or 5", str(rc))
        with patch.object(release_install, "install", return_value=0) as inst:
            self.assertEqual(self.cli(release_install, ["release_install.py", "install", "--slot", "4"])[0], 0)
        inst.assert_called_once()


if __name__ == "__main__":
    unittest.main()
