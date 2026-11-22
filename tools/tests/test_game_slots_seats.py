"""Shared seats of tools/game_slots.py (lane slotcap, 2026-11-21; <locks>/README.md): with <locks>/budget.json every slot
lock comes with a seat game.seat.K (K = 1..max_games), taken first and released after the lock; a failure between the
two gives the seat back; a seat whose pid is gone is stale, pid 0 never; without budget.json nothing changes. slots.json
refuses another project's slot. Both backends; temp lock folders inside the project, no game, no real lock."""
import contextlib
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
import resource_sample_linux  # noqa: E402
import parallel_smoke  # noqa: E402


class SeatsBase:
    BACKEND = "linux"
    SLOT_A, SLOT_B, SLOT_C = 2, 5, 6
    SLOT_D = 7

    def setUp(self):
        stack = contextlib.ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(game_slots.backend(self.BACKEND))
        self.tmp = tempfile.mkdtemp(prefix="seats-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.locks = os.path.join(self.tmp, "locks")
        os.makedirs(self.locks)
        self.proc = os.path.join(self.tmp, "proc")
        os.makedirs(self.proc)
        self.alive = set()
        stack.enter_context(patch.object(game_slots, "LOCK_ROOT", self.locks))
        stack.enter_context(patch.object(game_slots, "RUNS", os.path.join(self.tmp, "runs")))
        stack.enter_context(patch.object(game_slots, "PROC", self.proc))
        stack.enter_context(patch.object(game_slots, "pid_alive", lambda pid: int(pid) in self.alive))

    def budget(self, n):
        Path(self.locks, "budget.json").write_text(json.dumps({"max_games": n, "set_by": "test", "measured": "-"}))

    def seat_owners(self):
        return {k: (t.split()[0], game_slots._seat_slot(t)) for k, t in game_slots.seats()}

    # ------------------------------------------------------------ tests

    def want(self, proj, pid, count):
        d = Path(self.locks, f"game.want.{proj}")
        d.mkdir()
        (d / "owner.txt").write_text(f"{proj} pid={pid} 2026-11-21 12:00:00 count={count}")

    def test_yields_to_a_waiting_project(self):
        self.budget(4)
        self.alive.update({111, 222, 333})
        self.want("D2RGS", 333, 2)
        self.assertTrue(game_slots.acquire(self.SLOT_A, "run-a", pid=111)[0])
        self.assertTrue(game_slots.acquire(self.SLOT_B, "run-b", pid=222)[0])
        ok, msg = game_slots.acquire(self.SLOT_C, "run-c", pid=222)  # 2 free, D2RGS wants 2: yield
        self.assertFalse(ok, msg)
        self.assertIn("yielding: D2RGS waits for 2", msg)
        self.assertEqual(len(game_slots.seats()), 2)
        self.alive.discard(333)  # the waiter is gone: its want no longer counts
        self.assertTrue(game_slots.acquire(self.SLOT_C, "run-c", pid=222)[0])

    def test_want_count_is_capped_at_two_and_ours_is_ignored(self):
        self.budget(4)
        self.alive.update({111, 333})
        self.want("D2RGS", 333, 4)
        self.want("MXL", 111, 2)
        self.assertEqual(game_slots.wanted_by_others()[0], 2)
        self.assertTrue(game_slots.acquire(self.SLOT_A, "run-a", pid=111)[0])
        self.assertTrue(game_slots.acquire(self.SLOT_B, "run-b", pid=111)[0])
        self.assertFalse(game_slots.acquire(self.SLOT_C, "run-c", pid=111)[0])

    def test_a_want_for_one_leaves_one(self):
        self.budget(4)
        self.alive.update({111, 333})
        self.want("D2RGS", 333, 1)
        for n in (self.SLOT_A, self.SLOT_B, self.SLOT_C):
            self.assertTrue(game_slots.acquire(n, f"run-{n}", pid=111)[0])
        self.assertFalse(game_slots.acquire(self.SLOT_D, "run-d", pid=111)[0])

    def test_without_budget_no_seat_is_taken(self):
        self.assertIsNone(game_slots.max_games())
        ok, msg = game_slots.acquire(self.SLOT_A, "run-a", pid=0)
        self.assertTrue(ok, msg)
        self.assertEqual(game_slots.seats(), [])
        self.assertNotIn("(seat", msg)
        self.assertTrue(game_slots.release(self.SLOT_A, "run-a", manual=True))

    def test_seat_comes_with_the_lock_and_goes_with_it(self):
        self.budget(2)
        self.alive.add(111)
        ok, msg = game_slots.acquire(self.SLOT_A, "run-a", pid=111)
        self.assertTrue(ok, msg)
        self.assertIn("seat 1 of 2", msg)
        txt = Path(self.locks, "game.seat.1", "owner.txt").read_text()
        self.assertRegex(txt, rf"^run-a pid=111 \d{{4}}-\d\d-\d\d \d\d:\d\d:\d\d slot={self.SLOT_A}$")
        self.assertTrue(game_slots.release(self.SLOT_A, "run-a"))
        self.assertIsNone(game_slots.lock_info(self.SLOT_A))
        self.assertEqual(game_slots.seats(), [])

    def test_no_free_seat_refuses_and_takes_no_lock(self):
        self.budget(1)
        self.alive.add(111)
        self.assertTrue(game_slots.acquire(self.SLOT_A, "run-a", pid=111)[0])
        ok, msg = game_slots.acquire(self.SLOT_B, "run-b", pid=111, seat_wait=0)
        self.assertFalse(ok)
        self.assertIn("no free seat", msg)
        self.assertIsNone(game_slots.lock_info(self.SLOT_B))
        self.assertEqual(self.seat_owners(), {1: ("run-a", self.SLOT_A)})

    def test_waiting_for_a_seat_times_out(self):
        self.budget(1)
        Path(self.locks, "game.seat.1").mkdir()
        Path(self.locks, "game.seat.1", "owner.txt").write_text("other pid=0 2026-11-21 01:00:00 slot=3")
        with patch.object(game_slots.time, "sleep") as sl:
            ok, msg = game_slots.acquire(self.SLOT_A, "run-a", pid=0, seat_wait=0.2)
        self.assertFalse(ok)
        self.assertTrue(sl.called, "it waited before refusing")
        self.assertIn("1: other pid=0", msg)

    def test_a_seat_freed_while_waiting_is_taken(self):
        self.budget(1)
        Path(self.locks, "game.seat.1").mkdir()
        Path(self.locks, "game.seat.1", "owner.txt").write_text("other pid=0 2026-11-21 01:00:00 slot=3")

        def free(_):
            shutil.rmtree(os.path.join(self.locks, "game.seat.1"), ignore_errors=True)
        with patch.object(game_slots.time, "sleep", side_effect=free):
            ok, msg = game_slots.acquire(self.SLOT_A, "run-a", pid=0, seat_wait=30)
        self.assertTrue(ok, msg)
        self.assertEqual(self.seat_owners(), {1: ("run-a", self.SLOT_A)})

    def test_held_slot_takes_no_seat(self):
        self.budget(2)
        self.assertTrue(game_slots.acquire(self.SLOT_A, "lane-x", pid=0)[0])
        ok, msg = game_slots.acquire(self.SLOT_A, "run-b", pid=0)
        self.assertFalse(ok)
        self.assertEqual(self.seat_owners(), {1: ("lane-x", self.SLOT_A)})

    def test_lock_taken_between_the_steps_gives_the_seat_back(self):
        self.budget(2)
        real = game_slots.take_seat

        def seat_then_race(n, owner, pid, wait=None):
            r = real(n, owner, pid, wait)
            for p in game_slots.lock_paths(n):  # someone else's lock appears after our seat
                os.makedirs(p, exist_ok=True)
                Path(p, "owner.txt").write_text("racer pid=0 2026-11-21 01:00:00")
            return r
        with patch.object(game_slots, "take_seat", seat_then_race):
            ok, msg = game_slots.acquire(self.SLOT_A, "run-a", pid=0)
        self.assertFalse(ok, msg)
        self.assertEqual(game_slots.seats(), [], "the seat is released again")

    def test_stale_seat_is_replaced_and_pid_zero_never(self):
        self.budget(2)
        for k, txt in ((1, "dead pid=4242 2026-11-21 01:00:00 slot=3"), (2, "hand pid=0 2026-11-21 01:00:00 slot=4")):
            Path(self.locks, f"game.seat.{k}").mkdir()
            Path(self.locks, f"game.seat.{k}", "owner.txt").write_text(txt)
        ok, msg = game_slots.acquire(self.SLOT_A, "run-a", pid=0)
        self.assertTrue(ok, msg)
        self.assertEqual(self.seat_owners(), {1: ("run-a", self.SLOT_A), 2: ("hand", 4)})
        ok, msg = game_slots.acquire(self.SLOT_B, "run-b", pid=0)
        self.assertFalse(ok, "pid 0 is never stale")
        self.assertIsNone(game_slots.lock_info(self.SLOT_B))

    def test_stale_lock_goes_with_its_seat(self):
        self.budget(1)
        self.alive.add(500)
        self.assertTrue(game_slots.acquire(self.SLOT_A, "crashed", pid=500)[0])
        self.alive.discard(500)  # the run died: lock and seat are stale
        ok, msg = game_slots.acquire(self.SLOT_A, "run-b", pid=0)
        self.assertTrue(ok, msg)
        self.assertEqual(self.seat_owners(), {1: ("run-b", self.SLOT_A)})
        self.assertEqual(game_slots.lock_info(self.SLOT_A)[1].split()[0], "run-b")

    def test_manual_session_lock_keeps_its_seat_until_unlock(self):
        self.budget(2)
        self.assertTrue(game_slots.acquire(self.SLOT_A, "lane-x", pid=0)[0])
        self.assertTrue(game_slots.acquire(self.SLOT_A, "lane-x")[0])  # a run inside the session: already ours
        self.assertEqual(len(game_slots.seats()), 1, "no second seat for the same lock")
        self.assertTrue(game_slots.release(self.SLOT_A, "lane-x"))  # the run's end keeps the session lock
        self.assertEqual(len(game_slots.seats()), 1)
        self.assertTrue(game_slots.release(self.SLOT_A, "lane-x", manual=True))
        self.assertEqual(game_slots.seats(), [])

    def test_unlock_without_owner_drops_the_seat_of_that_slot_only(self):
        self.budget(3)
        self.assertTrue(game_slots.acquire(self.SLOT_A, "lane-x", pid=0)[0])
        self.assertTrue(game_slots.acquire(self.SLOT_B, "lane-y", pid=0)[0])
        self.assertTrue(game_slots.release(self.SLOT_A, None, manual=True))
        self.assertEqual(self.seat_owners(), {2: ("lane-y", self.SLOT_B)})

    def test_bad_budget_means_no_budget(self):
        for txt in ("{", '{"max_games": 0}', '{"max_games": "x"}', "[]"):
            Path(self.locks, "budget.json").write_text(txt)
            self.assertIsNone(game_slots.max_games(), txt)

class LinuxSeats(SeatsBase, unittest.TestCase):
    BACKEND = "linux"
    SLOT_A, SLOT_B, SLOT_C = 2, 6, 7
    SLOT_D = 5

    def test_linux_slots(self):
        self.assertEqual(game_slots.SLOTS, (2, 5, 6, 7))
        for n in (1, 3, 4, 8, 10):
            with self.assertRaises(SystemExit):
                game_slots.require_slot(n)
        self.assertEqual(game_slots.linux_slot(7)["dir"], os.path.join(game_slots.LINUX_SLOT_ROOT, "s7"))

    def test_slots_json_refuses_another_projects_slot(self):
        Path(self.locks, "slots.json").write_text(json.dumps({"slots": {str(self.SLOT_A): "D2RGS"}}))
        with self.assertRaises(SystemExit) as cm:
            game_slots.require_slot(self.SLOT_A)
        self.assertIn("D2RGS", str(cm.exception))
        Path(self.locks, "slots.json").write_text(json.dumps({"slots": {str(self.SLOT_A): "MXL"}}))
        self.assertEqual(game_slots.require_slot(self.SLOT_A), self.SLOT_A)

    def test_temporary_slots_only_by_env(self):
        with patch.object(game_slots, "EXTRA_LINUX_SLOTS", (10, 11)):
            game_slots.use_backend("linux")
            try:
                self.assertEqual(game_slots.require_slot(11), 11)
                self.assertEqual(game_slots.linux_slot(10)["compat"], os.path.join(game_slots.LINUX_PREFIX_ROOT, "s10"))
            finally:
                pass
        game_slots.use_backend("linux")
        with self.assertRaises(SystemExit):
            game_slots.require_slot(10)


class WindowsSeats(SeatsBase, unittest.TestCase):
    BACKEND = "windows"
    SLOT_A, SLOT_B, SLOT_C = 2, 3, 4
    SLOT_D = 5

    def test_slots_json_is_linux_numbering_only(self):
        Path(self.locks, "slots.json").write_text(json.dumps({"slots": {"3": "D2RGS"}}))
        self.assertEqual(game_slots.require_slot(3), 3, "Windows slot 3 is a different folder")

    def test_slot_one_seat_covers_both_locks(self):
        self.budget(1)
        ok, msg = game_slots.acquire(1, "run-a", pid=0)
        self.assertTrue(ok, msg)
        self.assertEqual(len(game_slots.lock_paths(1)), 2)
        self.assertEqual(self.seat_owners(), {1: ("run-a", 1)})
        self.assertTrue(game_slots.release(1, "run-a", manual=True))
        self.assertEqual(game_slots.seats(), [])


class Sampler(unittest.TestCase):
    def test_summary_and_memory_alarm(self):
        s = [{"t": i, "cpu": 10.0 * i, "cores": 32, "load1": 1.0 + i, "availMB": 50000 - 1000 * i, "swapMB": 300,
              "vramMB": 2700 + 5000 * min(i, 1), "gttMB": 220, "gpuBusy": 50,
              "games": {"2": {"cpu": 300.0, "pssMB": 3700, "vramMB": 5100, "procs": 9}},
              "xvfb": {"cpu": 30.0, "rssMB": 100, "n": 1}} for i in range(4)]
        r = resource_sample_linux.summarize(s, [2])
        self.assertEqual(r["avail_min_mb"], 47000)
        self.assertEqual(r["vram_peak_mb"], 7700)
        self.assertEqual(r["games"]["2"]["cpu_mean"], 300.0)
        self.assertIsNone(parallel_smoke.memory_alarm(s, 4096))
        self.assertIn("MemAvailable", parallel_smoke.memory_alarm(s, 48000))
        s[-1] = dict(s[-1], swapMB=900)
        self.assertIn("swap", parallel_smoke.memory_alarm(s, 4096))

    def test_real_proc_sample(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("Linux /proc")
        sm = resource_sample_linux.Sampler([])
        x = sm.sample()
        self.assertGreater(x["availMB"], 0)
        self.assertIn("xvfb", x)


if __name__ == "__main__":
    unittest.main()
