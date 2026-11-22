"""Slot rules of tools/game_slots.py: slots 1 to 5 exist (slot 1 is the owner's own game, approved 2026-10-28), there is
no default slot, the locks are the machine's shared lock folder (shared game.lock.N, slot 1 also the old game.lock),
the machine's protected folders are refused and run output stays in the repo. No game is started and no real lock or slot folder is touched: the locks, runs and slot
folders of the lock / owner-slot tests are temp folders inside the project (tools/projtemp.py)."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import game_slots  # noqa: E402


_PIN = contextlib.ExitStack()


def setUpModule():  # the Windows slot rules: Windows backend on every platform (the Linux classes below switch themselves)
    _PIN.enter_context(game_slots.backend("windows"))


def tearDownModule():
    _PIN.close()


class SlotRules(unittest.TestCase):
    def test_junk_is_refused(self):
        for bad in (0, 6, "-1", "x", None, ""):
            with self.assertRaises(SystemExit, msg=repr(bad)):
                game_slots.require_slot(bad)

    def test_slots_one_two_and_three_pass(self):
        self.assertEqual(game_slots.require_slot(1), 1)
        self.assertEqual(game_slots.require_slot("1"), 1)
        self.assertEqual(game_slots.require_slot(2), 2)
        self.assertEqual(game_slots.require_slot("3"), 3)

    def test_no_default_slot(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MXL_SLOT", None)
            with self.assertRaises(SystemExit):
                game_slots.env_slot()
        with patch.dict(os.environ, {"MXL_SLOT": "6"}):
            with self.assertRaises(SystemExit):
                game_slots.env_slot()
        with patch.dict(os.environ, {"MXL_SLOT": "1"}):
            self.assertEqual(game_slots.env_slot(), 1)
        with patch.dict(os.environ, {"MXL_SLOT": "3"}):
            self.assertEqual(game_slots.env_slot(), 3)

    def test_every_slot_function_refuses_junk(self):
        for fn in (game_slots.slot_dir, game_slots.save_name, game_slots.save_dir, game_slots.mod_dir, game_slots.lock_paths,
                   game_slots.lock_info, game_slots.launch_marker, game_slots.foreign_game):
            for bad in (0, 6):
                with self.assertRaises(SystemExit, msg=f"{fn.__name__}({bad})"):
                    fn(bad) if fn is not game_slots.foreign_game else fn(bad, "x", [])

    def test_names(self):
        self.assertEqual(game_slots.MOD, "mxl2012")
        self.assertEqual(game_slots.save_name(1), "mxl2012-s1")  # never another mod's own slot 1 folder
        self.assertEqual(game_slots.save_name(2), "mxl2012-s2")
        for n in game_slots.SLOTS:
            self.assertTrue(game_slots.mod_dir(n).endswith(os.path.join("mods", "mxl2012")))
            for other in game_slots.PROTECTED_MODS:
                self.assertNotIn(os.sep + other + os.sep, game_slots.mod_dir(n) + os.sep)
                self.assertNotEqual(os.path.basename(game_slots.save_dir(n)).lower(), other.lower())

    def test_protected_folders_are_refused(self):
        with patch.object(game_slots, "PROTECTED_MODS", ["OtherMod"]), \
                patch.object(game_slots, "PROTECTED_SAVES", ["OtherMod", "OtherMod-s*"]):
            self.assertTrue(game_slots.protected("othermod"))
            self.assertTrue(game_slots.protected("OtherMod-s2", saves=True))
            self.assertFalse(game_slots.protected("mxl2012"))
            self.assertFalse(game_slots.protected("mxl2012-s2", saves=True))
            with patch.object(game_slots, "MOD", "OtherMod"):
                with self.assertRaises(SystemExit):
                    game_slots.mod_dir(2)
                with self.assertRaises(SystemExit):
                    game_slots.save_dir(2)

    def test_commands_refuse_without_the_machine_safety_keys(self):
        with patch.dict(os.environ, {"MXL_MACHINE": os.path.join(game_slots.REPO, "work", "no-such-machine.json")}), \
                patch.object(sys, "argv", ["game_slots.py", "status"]):
            with self.assertRaises(SystemExit) as cm:
                game_slots.main()
            self.assertIn("shared_lock_dir", str(cm.exception))
        with patch.object(game_slots, "LOCK_ROOT", ""), \
                patch.dict(os.environ, {"MXL_MACHINE": os.path.join(game_slots.REPO, "work", "no-such-machine.json")}):
            with self.assertRaises(SystemExit):
                game_slots.lock_paths(2)

    def test_slot_one_folder_and_override(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MXL_SLOT1_DIR", None)
            self.assertEqual(game_slots.slot_dir(1), r"C:\Program Files (x86)\Diablo II Resurrected")
        with patch.dict(os.environ, {"MXL_SLOT1_DIR": r"E:\elsewhere"}):
            self.assertEqual(game_slots.slot_dir(1), r"E:\elsewhere")

    def test_owner_slot_is_never_in_the_default_set(self):
        self.assertEqual(game_slots.OWNER_SLOTS, (1,))
        self.assertEqual(game_slots.DEFAULT_SET, (2, 3, 4, 5))

    def test_locks_are_shared_and_runs_are_local(self):
        with patch.object(game_slots, "LOCK_ROOT", game_slots.LOCK_ROOT or os.path.join(game_slots.REPO, "work", "locks")):
            self.assertEqual(os.path.basename(game_slots.lock_paths(2)[0]), "game.lock.2")
            self.assertEqual([os.path.basename(p) for p in game_slots.lock_paths(1)], ["game.lock.1", "game.lock"])
            self.assertEqual(len(game_slots.lock_paths(3)), 1)
        if not (os.environ.get("MXL_LOCKS") or os.environ.get("MXL_RUNS")):
            self.assertEqual(game_slots.LOCK_ROOT, game_slots.MACHINE.get("shared_lock_dir") or "")  # machine.json's folder
            self.assertTrue(game_slots.RUNS.startswith(game_slots.REPO))  # run output is not written there

    def test_slot_of_game_dir(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("MXL_SLOT1_DIR", "MXL_SLOT2_DIR"):
                os.environ.pop(k, None)
            self.assertEqual(game_slots.slot_of_game_dir(game_slots.slot_dir(2)), 2)
            self.assertEqual(game_slots.slot_of_game_dir(r"C:\Program Files (x86)\Diablo II Resurrected"), 1)
            self.assertIsNone(game_slots.slot_of_game_dir(r"C:\Program Files (x86)\Diablo II Resurrected\mods"))


class TempRoot(unittest.TestCase):
    """Locks, runs and slot folders in a temp folder inside the project."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gameslots-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.locks = os.path.join(self.tmp, "locks")
        self.runs = os.path.join(self.tmp, "runs")
        self.slot1 = os.path.join(self.tmp, "Diablo II Resurrected")
        for p in (patch.object(game_slots, "LOCK_ROOT", self.locks), patch.object(game_slots, "RUNS", self.runs),
                  patch.dict(os.environ, {"MXL_SLOT1_DIR": self.slot1})):
            p.start()
            self.addCleanup(p.stop)


class Locks(TempRoot):
    def test_slot_one_takes_both_locks(self):
        ok, msg = game_slots.acquire(1, "lane-a", pid=0)
        self.assertTrue(ok, msg)
        for name in ("game.lock.1", "game.lock"):
            self.assertTrue(Path(self.locks, name, "owner.txt").read_text(encoding="utf-8").startswith("lane-a pid=0 "))
        self.assertTrue(game_slots.release(1, "lane-a", manual=True))
        self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock.1")))
        self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock")))

    def test_slot_two_takes_only_its_own(self):
        self.assertTrue(game_slots.acquire(2, "lane-a", pid=0)[0])
        self.assertEqual(sorted(os.listdir(self.locks)), ["game.lock.2"])
        self.assertTrue(game_slots.acquire(1, "lane-b", pid=0)[0], "slot 2's lock does not hold slot 1")

    def test_legacy_lock_of_another_tool_holds_slot_one(self):
        os.makedirs(os.path.join(self.locks, "game.lock"))
        Path(self.locks, "game.lock", "owner.txt").write_text("other-lane pid=0 2026-10-28 10:00:00", encoding="utf-8")
        info = game_slots.lock_info(1)
        self.assertEqual(os.path.basename(info[0]), "game.lock")
        ok, msg = game_slots.acquire(1, "lane-a")
        self.assertFalse(ok)
        self.assertIn("other-lane", msg)
        self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock.1")), "nothing taken while the legacy lock is held")
        self.assertFalse(game_slots.release(1, "lane-a"), "another owner's lock is never removed")
        self.assertTrue(os.path.isdir(os.path.join(self.locks, "game.lock")))
        self.assertIsNone(game_slots.lock_info(2))

    def test_hand_made_legacy_lock_is_respected(self):
        os.makedirs(os.path.join(self.locks, "game.lock"))  # mkdir game.lock by hand: no owner.txt
        self.assertEqual(game_slots.lock_info(1)[1], None)
        ok, msg = game_slots.acquire(1, "lane-a")
        self.assertFalse(ok)
        self.assertIn("no owner.txt", msg)
        self.assertFalse(game_slots.release(1, "lane-a"))
        self.assertTrue(os.path.isdir(os.path.join(self.locks, "game.lock")))

    def test_stale_legacy_lock_is_replaced_with_both(self):
        os.makedirs(os.path.join(self.locks, "game.lock"))
        Path(self.locks, "game.lock", "owner.txt").write_text("gone pid=999999 2026-10-28 10:00:00", encoding="utf-8")
        with patch.object(game_slots, "pid_alive", return_value=False):
            ok, msg = game_slots.acquire(1, "lane-a", pid=4242)
        self.assertTrue(ok, msg)
        for name in ("game.lock.1", "game.lock"):
            self.assertTrue(Path(self.locks, name, "owner.txt").read_text(encoding="utf-8").startswith("lane-a pid=4242 "))

    def test_new_lock_held_by_another_tool_holds_slot_one(self):
        os.makedirs(os.path.join(self.locks, "game.lock.1"))
        Path(self.locks, "game.lock.1", "owner.txt").write_text("other pid=0 x", encoding="utf-8")
        self.assertFalse(game_slots.acquire(1, "lane-a")[0])
        self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock")))

    def test_legacy_lock_appearing_in_between_undoes_ours(self):
        real_mkdir = os.mkdir

        def racing_mkdir(p, *a, **k):
            if os.path.basename(p) == "game.lock":  # another tool took the old lock between our check and our mkdir
                real_mkdir(p)
            return real_mkdir(p, *a, **k)
        with patch.object(game_slots.os, "mkdir", side_effect=racing_mkdir):
            ok, msg = game_slots.acquire(1, "lane-a")
        self.assertFalse(ok)
        self.assertIn("taken just now", msg)
        self.assertFalse(os.path.exists(os.path.join(self.locks, "game.lock.1")), "our half is removed again")

    def test_run_inside_a_manual_session_keeps_it(self):
        self.assertTrue(game_slots.acquire(1, "lane-a", pid=0)[0])
        self.assertTrue(game_slots.release(1, "lane-a"))  # a run's end
        self.assertTrue(os.path.isdir(os.path.join(self.locks, "game.lock.1")))
        self.assertTrue(os.path.isdir(os.path.join(self.locks, "game.lock")))
        self.assertTrue(game_slots.release(1, "lane-a", manual=True))
        self.assertEqual(os.listdir(self.locks), [])


class OwnerSlot(TempRoot):
    PROCS = [(111, "D2RLoader.exe"), (112, "D2R.exe")]

    def test_a_game_nobody_of_ours_started_is_foreign(self):
        self.assertEqual(game_slots.foreign_game(1, "lane-a", self.PROCS), self.PROCS)
        self.assertEqual(game_slots.foreign_game(1, None, self.PROCS), self.PROCS)
        self.assertEqual(game_slots.foreign_game(1, "lane-a", []), [])

    def test_our_launch_is_not_foreign_and_another_lanes_is(self):
        game_slots.mark_launch(1, "lane-a", 111)
        self.assertTrue(game_slots.launch_marker(1).startswith(self.runs))
        self.assertEqual(game_slots.launched_by(1), ("lane-a", 111))
        self.assertEqual(game_slots.foreign_game(1, "lane-a", self.PROCS), [])
        self.assertEqual(game_slots.foreign_game(1, "lane-b", self.PROCS), self.PROCS)
        game_slots.clear_launch(1)
        game_slots.clear_launch(1)  # twice is fine
        self.assertEqual(game_slots.foreign_game(1, "lane-a", self.PROCS), self.PROCS)

    def test_stale_marker_of_a_crashed_run_does_not_claim_the_owners_game(self):
        game_slots.mark_launch(1, "lane-a", 4242)  # our loader 4242 is gone; the owner now plays (111, 112)
        self.assertEqual(game_slots.foreign_game(1, "lane-a", self.PROCS), self.PROCS)
        Path(game_slots.launch_marker(1)).write_text("{broken", encoding="utf-8")
        self.assertEqual(game_slots.launched_by(1), (None, None))
        self.assertEqual(game_slots.foreign_game(1, "lane-a", self.PROCS), self.PROCS)

    def test_slots_two_and_three_have_no_owner_rule(self):
        self.assertEqual(game_slots.foreign_game(2, "lane-a", self.PROCS), [])
        self.assertEqual(game_slots.foreign_game(3, None, self.PROCS), [])

    def test_slot_one_runs_the_plain_loader_and_setup_makes_no_copy(self):
        g = Path(self.slot1)
        (g / "mods" / "mxl2012" / "mxl2012.mpq").mkdir(parents=True)
        (g / "D2RLoader.exe").write_bytes(b"MZ")
        (g / "D2RLoader-s1.exe").write_bytes(b"MZ")  # even if one were there, slot 1 does not use it
        self.assertEqual(game_slots.loader_name(self.slot1), "D2RLoader.exe")
        (g / "D2RLoader-s1.exe").unlink()
        saves = os.path.join(self.tmp, "saves")
        with patch.object(game_slots, "SAVE_ROOT", saves):
            msg = game_slots.setup(1)
        self.assertIn("loader D2RLoader.exe", msg)
        self.assertEqual(sorted(p.name for p in g.iterdir()), ["D2RLoader.exe", "mods"])
        self.assertTrue(os.path.isdir(os.path.join(saves, "mxl2012-s1")))
        self.assertIn('"savepath": "mxl2012-s1/"', (g / "mods" / "mxl2012" / "modinfo.json").read_text(encoding="utf-8"))
        self.assertIn('"savepath": "mxl2012-s1/"',
                      (g / "mods" / "mxl2012" / "mxl2012.mpq" / "modinfo.json").read_text(encoding="utf-8"))


class NeedWrite(TempRoot):
    def setUp(self):
        super().setUp()
        self.game = Path(self.slot1)
        (self.game / "mods").mkdir(parents=True)
        self.f = self.game / "d2rloader.toml"
        self.f.write_bytes(b"x = 1\n")
        os.utime(self.f, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))

    def test_writable_paths_pass_and_nothing_changes(self):
        game_slots.need_write([str(self.f), str(self.game / "mods"), str(self.game / "mods" / "mxl2012")], "test")
        self.assertEqual(self.f.read_bytes(), b"x = 1\n")
        self.assertEqual(os.stat(self.f).st_mtime_ns, 1_600_000_000_000_000_000)
        self.assertEqual(sorted(p.name for p in self.game.rglob("*")), ["d2rloader.toml", "mods"], "no probe left, nothing made")

    def test_refused_write_ends_with_a_clear_message(self):
        real_open = open

        def denied(p, mode="r", *a, **k):
            if "x" in mode or "+" in mode:
                raise PermissionError(13, "Access is denied", p)
            return real_open(p, mode, *a, **k)
        for target in (str(self.f), str(self.game / "mods" / "mxl2012")):
            with patch("builtins.open", side_effect=denied), self.assertRaises(SystemExit) as cm:
                game_slots.need_write([target], "refusing install into slot 1")
            text = str(cm.exception)
            self.assertIn("refusing install into slot 1: no write access to", text)
            self.assertIn("never ask for administrator rights", text)

    def test_never_probes_above_the_slot_folder(self):
        shutil.rmtree(self.game)
        with self.assertRaises(SystemExit) as cm:
            game_slots.need_write([os.path.join(self.slot1, "mods", "mxl2012")], "test")
        self.assertIn("does not exist", str(cm.exception))
        self.assertEqual(os.listdir(self.tmp), [], "nothing written into the folder above the slot")


# ---------------------------------------------------------------- the Linux backend (slots 2 and 5 under Proton)


class Backend(unittest.TestCase):
    def test_backend_is_picked_by_platform_and_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MXL_SLOT_BACKEND", None)
            with game_slots.backend(game_slots.BACKEND):
                os.environ.pop("MXL_SLOT_BACKEND", None)
                with patch.object(sys, "platform", "linux"):
                    self.assertEqual(game_slots.use_backend(), "linux")
                    self.assertEqual((game_slots.SLOTS, game_slots.OWNER_SLOTS, game_slots.DEFAULT_SET), ((2, 5, 6, 7), (), (2, 5, 6, 7)))
                with patch.object(sys, "platform", "win32"):
                    self.assertEqual(game_slots.use_backend(), "windows")
                    self.assertEqual((game_slots.SLOTS, game_slots.OWNER_SLOTS, game_slots.DEFAULT_SET),
                                     ((1, 2, 3, 4, 5), (1,), (2, 3, 4, 5)))
                with patch.object(sys, "platform", "win32"), patch.dict(os.environ, {"MXL_SLOT_BACKEND": "linux"}):
                    self.assertEqual(game_slots.use_backend(), "linux")
                with self.assertRaises(SystemExit):
                    game_slots.use_backend("macos")
        self.assertEqual(game_slots.BACKEND, "windows", "this module's pin is back")

    def test_windows_images_do_not_depend_on_the_backend(self):
        self.assertEqual(game_slots.ALL_IMAGES, ("d2rloader.exe", "d2r.exe", "d2rloader-s2.exe", "d2rloader-s3.exe",
                                                 "d2rloader-s4.exe", "d2rloader-s5.exe"))


class LinuxRoot(unittest.TestCase):
    """A fake Linux slot 5 (and 2) with its own prefix, snapshot folder and lock folder, all in a temp folder; a fake /proc."""

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(game_slots.backend("linux"))
        self.tmp = tempfile.mkdtemp(prefix="linslots-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = os.path.join(self.tmp, "slots", "s5")
        self.compat = os.path.join(self.tmp, "prefixes", "s5")
        os.makedirs(os.path.join(self.game, "mods", "mxl2012"))
        os.makedirs(os.path.join(self.compat, "pfx", "dosdevices"))
        os.symlink("../drive_c", os.path.join(self.compat, "pfx", "dosdevices", "c:"))
        for f in ("D2R.exe", "D2RLoader.exe"):
            Path(self.game, f).write_bytes(b"MZ")
        self.locks = os.path.join(self.tmp, "locks")
        self.runs = os.path.join(self.tmp, "runs")
        self.proc = os.path.join(self.tmp, "proc")
        os.makedirs(self.proc)
        for p in (patch.dict(os.environ, {"MXL_SLOT5_DIR": self.game, "MXL_SLOT5_COMPAT": self.compat,
                                          "MXL_SLOT5_SNAPSHOT": os.path.join(self.tmp, "slots", ".snap-s5"),
                                          "MXL_SLOT2_DIR": os.path.join(self.tmp, "slots", "s2"),
                                          "MXL_SLOT2_COMPAT": os.path.join(self.tmp, "prefixes", "s2")}),
                  patch.object(game_slots, "LOCK_ROOT", self.locks), patch.object(game_slots, "RUNS", self.runs),
                  patch.object(game_slots, "PROC", self.proc)):
            stack.enter_context(p)

    def fake_proc(self, pid, argv, env):
        d = os.path.join(self.proc, str(pid))
        os.makedirs(d)
        Path(d, "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        Path(d, "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in env.items()) + b"\0")


class LinuxSlots(LinuxRoot):
    def test_only_slots_two_five_six_and_seven_exist(self):
        for n in (2, 5, "5", 6, 7):
            self.assertEqual(game_slots.require_slot(n), int(n))
        for n in (1, 3, 4):
            with self.assertRaises(SystemExit) as cm:
                game_slots.require_slot(n)
            self.assertIn("does not exist on Linux", str(cm.exception))
            for fn in (game_slots.slot_dir, game_slots.save_dir, game_slots.lock_paths, game_slots.prefix_dir):
                with self.assertRaises(SystemExit, msg=f"{fn.__name__}({n})"):
                    fn(n)
        for bad in (0, 8, 10, "x", None):
            with self.assertRaises(SystemExit):
                game_slots.require_slot(bad)
        with patch.dict(os.environ, {"MXL_SLOT": "1"}), self.assertRaises(SystemExit):
            game_slots.env_slot()

    def test_slot_table_defaults_and_overrides(self):
        with patch.dict(os.environ, {}, clear=False):
            for k in ("DIR", "COMPAT", "SNAPSHOT"):
                os.environ.pop(f"MXL_SLOT2_{k}", None)
            with patch.object(game_slots, "MACHINE", {}):
                self.assertEqual(game_slots.linux_slot(2), {
                    "dir": "/d2work/slots/s2", "compat": "/d2work/prefixes/s2", "snapshot": "/d2work/slots/.snap-s2",
                    "prefix": "/d2work/prefixes/s2/pfx"})
            with patch.object(game_slots, "MACHINE", {"linux_slots": {"2": {"dir": "/elsewhere/two", "compat": "~/pfx2"}}}):
                t = game_slots.linux_slot(2)
                self.assertEqual(t["dir"], "/elsewhere/two")
                self.assertEqual(t["prefix"], os.path.join(os.path.expanduser("~/pfx2"), "pfx"))
                with patch.dict(os.environ, {"MXL_SLOT2_DIR": "/env/wins"}):
                    self.assertEqual(game_slots.slot_dir(2), "/env/wins")
        self.assertEqual(game_slots.slot_dir(5), self.game)
        self.assertEqual(game_slots.prefix_dir(5), os.path.join(self.compat, "pfx"))

    def test_saves_live_in_the_prefix(self):
        self.assertEqual(game_slots.save_dir(5), os.path.join(self.compat, "pfx", "drive_c", "users", "steamuser",
                                                              "Saved Games", "Diablo II Resurrected", "mods", "mxl2012-s5"))
        self.assertTrue(game_slots.mod_dir(5).endswith(os.path.join("s5", "mods", "mxl2012")))

    def test_wine_env_and_commands(self):
        env = game_slots.wine_env(5, base={"HOME": "/h", "WINEDEBUG": "+seh"}, log_dir="/logs")
        self.assertEqual(env["WINEPREFIX"], os.path.join(self.compat, "pfx"))
        self.assertEqual(env["STEAM_COMPAT_DATA_PATH"], self.compat)
        self.assertEqual((env["PROTON_LOG"], env["PROTON_LOG_DIR"], env["WINEDEBUG"], env["HOME"]), ("1", "/logs", "+seh", "/h"))
        self.assertEqual(game_slots.wine_env(5, base={})["WINEDEBUG"], "-all")
        with patch.dict(os.environ, {"MXL_PROTON": "/opt/proton-x"}):
            self.assertEqual(game_slots.proton_cmd("D:\\D2RLoader.exe", "-mod", "mxl2012"),
                             ["python3", "/opt/proton-x/proton", "run", "D:\\D2RLoader.exe", "-mod", "mxl2012"])
            self.assertEqual(game_slots.wine_cmd("Z:\\x.exe")[0], "/opt/proton-x/files/bin/wine")
        self.assertEqual(game_slots.windows_path(5, os.path.join(self.game, "D2RLoader.exe")), "D:\\D2RLoader.exe")
        self.assertEqual(game_slots.windows_path(5, os.path.join(self.game, "mods", "mxl2012")), "D:\\mods\\mxl2012")
        self.assertEqual(game_slots.windows_path(5, "/d2work/runs/w.exe"), "Z:\\d2work\\runs\\w.exe")

    def test_drive_d_is_made_and_a_wrong_one_refused(self):
        link = game_slots.ensure_drive(5)
        self.assertEqual(os.path.realpath(link), os.path.realpath(self.game))
        self.assertEqual(game_slots.ensure_drive(5), link, "a second call keeps it")
        os.remove(link)
        os.symlink(self.tmp, link)
        with self.assertRaises(SystemExit):
            game_slots.ensure_drive(5)

    def test_processes_are_found_in_proc_by_prefix(self):
        game_slots.ensure_drive(5)
        pfx5 = os.path.join(self.compat, "pfx")
        other = os.path.join(self.tmp, "otherpfx")
        os.makedirs(os.path.join(other, "dosdevices"))
        os.symlink(self.tmp, os.path.join(other, "dosdevices", "d:"))
        self.fake_proc(100, ["D:\\D2RLoader.exe", "-mod", "mxl2012"], {"WINEPREFIX": pfx5})
        self.fake_proc(101, ["D:\\D2R.exe", "-w", "-mod", "mxl2012"], {"WINEPREFIX": pfx5})
        self.fake_proc(102, ["C:\\windows\\system32\\services.exe"], {"WINEPREFIX": pfx5})
        self.fake_proc(103, ["/usr/bin/python3", "D2R.exe"], {"WINEPREFIX": pfx5})  # not a Wine image
        self.fake_proc(104, ["D:\\D2R.exe"], {"WINEPREFIX": other})  # the same name in another prefix
        self.fake_proc(105, ["D:\\D2R.exe"], {})  # no prefix
        os.makedirs(os.path.join(self.proc, "106"))  # gone / not readable
        found = game_slots.linux_processes()
        self.assertEqual([(p, n) for p, n, _ in found], [(100, "D2RLoader.exe"), (101, "D2R.exe"), (104, "D2R.exe")])
        self.assertEqual(found[1][2], os.path.join(os.path.realpath(self.game), "D2R.exe"))
        self.assertEqual(game_slots.slot_processes(self.game), [(100, "D2RLoader.exe"), (101, "D2R.exe")])
        self.assertEqual(game_slots.game_pids(5), [100, 101])
        self.assertEqual(game_slots.game_pids(5, ("d2r.exe",)), [101])
        self.assertEqual(game_slots.prefix_pids(5), [100, 101, 102, 103])
        self.assertEqual(game_slots.prefix_pids(2), [])
        self.assertTrue(game_slots.pid_alive(100))
        self.assertFalse(game_slots.pid_alive(99))

    def test_unix_path(self):
        pfx = os.path.join(self.compat, "pfx")
        game_slots.ensure_drive(5)
        self.assertEqual(game_slots.unix_path(pfx, "D:\\mods\\mxl2012\\x.dll"),
                         os.path.join(os.path.realpath(self.game), "mods", "mxl2012", "x.dll"))
        self.assertEqual(game_slots.unix_path(pfx, "Q:\\x.exe"), "")
        self.assertEqual(game_slots.unix_path(pfx, "x.exe"), "")

    def test_locks_are_linslot_compatible(self):
        self.assertEqual(game_slots.lock_paths(5), [os.path.join(self.locks, "game.lock.5")])  # no legacy lock
        ok, _ = game_slots.acquire(5, "linslots", pid=0)
        self.assertTrue(ok)
        txt = Path(self.locks, "game.lock.5", "owner.txt").read_text()
        self.assertRegex(txt, r"^linslots pid=0 \d{4}-\d\d-\d\d \d\d:\d\d:\d\d$")
        self.assertFalse(game_slots.acquire(5, "wineinput")[0])
        self.assertTrue(game_slots.release(5, "linslots", manual=True))
        # a lock written by linslot.py (lane linuxslots): same format, held
        os.makedirs(os.path.join(self.locks, "game.lock.2"))
        Path(self.locks, "game.lock.2", "owner.txt").write_text("wineinput pid=0 2026-11-20 09:00:00")
        self.assertEqual(game_slots.lock_info(2)[1].split()[0], "wineinput")
        self.assertFalse(game_slots.acquire(2, "linslots")[0])

    def test_a_dead_owner_pid_is_stale_and_a_live_one_holds(self):
        os.makedirs(os.path.join(self.locks, "game.lock.5"))
        Path(self.locks, "game.lock.5", "owner.txt").write_text("crashed pid=4242 2026-11-20 09:00:00")
        self.assertTrue(game_slots.acquire(5, "linslots", pid=77)[0], "pid 4242 is not in /proc")
        game_slots.release(5, "linslots")
        Path(self.proc, "4243").mkdir()
        os.makedirs(os.path.join(self.locks, "game.lock.5"))
        Path(self.locks, "game.lock.5", "owner.txt").write_text("busy pid=4243 2026-11-20 09:00:00")
        self.assertFalse(game_slots.acquire(5, "linslots")[0])

    def test_status_lists_only_the_linux_slots(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            game_slots.status()
        lines = out.getvalue().splitlines()
        self.assertEqual([l.split(":")[0] for l in lines], ["budget", "slot 2", "slot 5", "slot 6", "slot 7"])
        self.assertIn("none (no budget.json)", lines[0])
        self.assertIn("MISSING", lines[1])
        self.assertIn("prefix " + os.path.join(self.compat, "pfx"), lines[2])

    def test_data_tools_never_read_d2r_files_from_a_linux_slot(self):
        import d2r_game
        Path(self.game, "D2RLoader.exe").write_bytes(b"MZ")
        with patch.dict(os.environ, {"MXL_SLOT": "5"}), self.assertRaises(SystemExit) as cm:
            d2r_game.read_game_dir()  # the slots hold D2R 3.4; the data tools want build 93847's files
        self.assertIn("not build 93847", str(cm.exception))

    def test_setup_makes_the_loader_copy_and_the_save_folder_in_the_prefix(self):
        os.makedirs(os.path.join(self.game, "mods", "mxl2012", "mxl2012.mpq"))
        msg = game_slots.setup(5)
        self.assertIn("D2RLoader-s5.exe", msg)
        self.assertTrue(os.path.isdir(game_slots.save_dir(5)))
        self.assertEqual(game_slots.loader_name(self.game), "D2RLoader-s5.exe")
        self.assertIn('"savepath": "mxl2012-s5/"', Path(self.game, "mods", "mxl2012", "modinfo.json").read_text())


USER_REG = ('WINE REGISTRY Version 2\n;; All keys relative to REGISTRY\\\\User\\\\S-1\n\n#arch=win64\n\n'
            '[Software\\\\Wine\\\\DllOverrides] 1794497076\n#time=1dd\n"d3d12"="native,builtin"\n\n'
            '[Volatile Environment] 1794497076\n"USERNAME"="steamuser"\n')


class LinuxNoFocus(LinuxRoot):
    """Owner rule (2026-11-20): test games never take focus. The launch writes the prefix's X11 Driver settings; a
    FocusWatch measures _NET_ACTIVE_WINDOW."""

    def reg(self):
        return os.path.join(self.compat, "pfx", "user.reg")

    def test_settings_are_added_once_and_other_keys_kept(self):
        Path(self.reg()).write_text(USER_REG)
        self.assertEqual(game_slots.apply_launch_settings(5), list(game_slots.NO_FOCUS_VALUES))
        text = Path(self.reg()).read_text()
        self.assertEqual(game_slots.reg_values(text, game_slots.X11_DRIVER_KEY),
                         {"UseTakeFocus": "N", "GrabPointer": "N", "GrabFullscreen": "N"})
        self.assertIn('[Software\\\\Wine\\\\X11 Driver] ', text)
        self.assertTrue(text.startswith(USER_REG.rstrip("\n")), "everything else as it was")
        self.assertEqual(game_slots.apply_launch_settings(5), [], "nothing to do the second time")
        self.assertEqual(Path(self.reg()).read_text(), text)

    def test_an_existing_section_is_updated_in_place(self):
        text = USER_REG + '\n[Software\\\\Wine\\\\X11 Driver] 1\n"UseTakeFocus"="Y"\n"Decorated"="Y"\n\n[Zzz] 2\n"a"="b"\n'
        out = game_slots.set_reg_values(text, game_slots.X11_DRIVER_KEY, game_slots.NO_FOCUS_VALUES)
        self.assertEqual(game_slots.reg_values(out, game_slots.X11_DRIVER_KEY),
                         {"UseTakeFocus": "N", "Decorated": "Y", "GrabPointer": "N", "GrabFullscreen": "N"})
        self.assertEqual(game_slots.reg_values(out, "Zzz"), {"a": "b"})
        self.assertEqual(out.count("[Software\\\\Wine\\\\X11 Driver]"), 1)

    def test_settings_refused_while_the_prefix_runs_and_without_a_prefix(self):
        with self.assertRaises(SystemExit):
            game_slots.apply_launch_settings(5)  # no user.reg yet
        Path(self.reg()).write_text(USER_REG)
        with patch.object(game_slots, "prefix_pids", return_value=[7]), self.assertRaises(SystemExit):
            game_slots.apply_launch_settings(5)
        self.assertEqual(Path(self.reg()).read_text(), USER_REG)

    def test_launch_writes_the_settings_before_proton_starts(self):
        Path(self.reg()).write_text(USER_REG)
        seen = {}

        def popen(argv, **kw):
            seen["reg"] = game_slots.reg_values(Path(self.reg()).read_text(), game_slots.X11_DRIVER_KEY)
            seen["argv"], seen["env"] = argv, kw["env"]
            return "proc"
        with patch.object(game_slots.subprocess, "Popen", side_effect=popen), patch.dict(os.environ, {"MXL_PROTON": "/p"}):
            self.assertEqual(game_slots.launch(5, ["-mod", "mxl2012"]), "proc")
        self.assertEqual(seen["reg"]["UseTakeFocus"], "N")
        self.assertEqual(seen["argv"], ["python3", "/p/proton", "run", "D:\\D2RLoader.exe", "-mod", "mxl2012"])
        self.assertEqual(seen["env"]["WINEPREFIX"], os.path.join(self.compat, "pfx"))

    def test_xprop_parsers(self):
        self.assertEqual(game_slots.parse_active("_NET_ACTIVE_WINDOW(WINDOW): window id # 0xa600030, 0x0\n"), 0xa600030)
        self.assertEqual(game_slots.parse_active("_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0\n"), 0)
        self.assertIsNone(game_slots.parse_active("_NET_ACTIVE_WINDOW:  not found.\n"))
        self.assertEqual(game_slots.parse_window('_NET_WM_PID(CARDINAL) = 521884\nWM_CLASS(STRING) = "d2rloader-s5.exe", '
                                                 '"d2rloader-s5.exe"\n'), (521884, '"d2rloader-s5.exe", "d2rloader-s5.exe"'))
        self.assertEqual(game_slots.parse_window("_NET_WM_PID:  not found.\n"), (None, ""))
        self.assertTrue(game_slots.is_game_window(5, "", {5}))
        self.assertTrue(game_slots.is_game_window(None, '"explorer.exe", "explorer.exe"', set()))
        self.assertFalse(game_slots.is_game_window(9, '"xfce4-terminal", "Xfce4-terminal"', {5}))

    def fake_x(self, active, windows):
        def query(*a):
            if a[0] == "-root":
                return f"_NET_ACTIVE_WINDOW(WINDOW): window id # {hex(active[0])}\n"
            pid, cls = windows[int(a[1], 16)]
            return f"_NET_WM_PID(CARDINAL) = {pid}\nWM_CLASS(STRING) = {cls}\n"
        return query

    def test_focus_watch_ignores_the_owner_and_catches_the_game(self):
        active = [0x100]
        windows = {0x100: (11, '"code", "Code"'), 0x200: (12, '"xfce4-terminal", "Xfce4-terminal"'),
                   0x300: (500, '"d2rloader-s5.exe", "d2rloader-s5.exe"')}
        w = game_slots.FocusWatch(5, query=self.fake_x(active, windows), pids=lambda: {500, 501})
        self.assertEqual(w.before, 0x100)
        self.assertIsNone(w.poll())
        active[0] = 0x200  # the owner switched windows: fine
        self.assertIsNone(w.poll())
        self.assertIn("focus kept", w.summary())
        active[0] = 0x300  # the game window became active
        grab = w.poll()
        self.assertEqual(grab[1:], (0x300, 500, '"d2rloader-s5.exe", "d2rloader-s5.exe"', True))
        self.assertEqual(len(w.changes), 2)
        self.assertIn("FOCUS GRAB", w.summary())

    def test_focus_watch_thread_stops(self):
        active = [0x100]
        w = game_slots.FocusWatch(5, interval=0.01, query=self.fake_x(active, {0x100: (1, '"x", "X"')}), pids=set).start()
        time.sleep(0.05)
        self.assertIn("focus kept", w.stop())
        self.assertGreater(w.polls, 0)


if __name__ == "__main__":
    unittest.main()
