"""Slot rules of tools/game_slots.py: slots 1 to 5 exist (slot 1 is the owner's own game, approved 2026-10-28), there is
no default slot, the locks are the machine's shared lock folder (shared game.lock.N, slot 1 also the old game.lock),
the machine's protected folders are refused and run output stays in the repo. No game is started and no real lock or slot folder is touched: the locks, runs and slot
folders of the lock / owner-slot tests are temp folders inside the project (tools/projtemp.py)."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import game_slots  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
