"""game_checks on Linux (lane linharness): the watchdog fed by the owner focus watch, private memory from /proc, no direct
user32 calls on the run path; plus source checks of the plugin harness fixes found on Linux (Stat Book's shared stub check,
the diag logger's lock order). No game, Wine or X needed."""
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc  # noqa: E402

REPO = Path(__file__).resolve().parents[2]


class PrivateMemory(unittest.TestCase):
    def test_smaps_rollup(self):
        proc = tempfile.mkdtemp()
        os.makedirs(os.path.join(proc, "4242"))
        with open(os.path.join(proc, "4242", "smaps_rollup"), "w") as f:
            f.write("5555-6666 ---p 00000000 00:00 0  [rollup]\nRss:  900000 kB\nPrivate_Clean:  102400 kB\n"
                    "Private_Dirty:  1945600 kB\nSwap:  1024 kB\n")
        self.assertEqual(gc.linux_private_mb([1, 4242], proc=proc), (102400 + 1945600 + 1024) // 1024)
        self.assertIsNone(gc.linux_private_mb([1], proc=proc))
        self.assertIsNone(gc.linux_private_mb([], proc=proc))


class LinuxWatchdog(unittest.TestCase):
    def run_watchdog(self, grabs_seq):
        import game_ctl_linux
        seq = iter(grabs_seq)
        last = [[]]

        def grabs():
            try:
                last[0] = next(seq)
            except StopIteration:
                pass
            return last[0]
        with patch.object(gc.g.game_slots, "LINUX", True), patch.object(game_ctl_linux, "focus_grabs", side_effect=grabs):
            wd = gc.Watchdog()
            wd.start()
            t0 = time.time()
            while wd.samples < len(grabs_seq) + 1 and time.time() - t0 < 10:
                time.sleep(0.05)
            wd.stop_flag = True
            wd.join(5)
        return wd

    def test_focus_kept(self):
        wd = self.run_watchdog([[], [], []])
        self.assertIsNone(wd.abort)
        self.assertIn("private X display", wd.summary())
        self.assertIn("0 grabs", wd.summary())

    def test_grab_aborts(self):
        wd = self.run_watchdog([[], [{"t": 2.8, "window": "0xee00001", "pid": 559263}]])
        self.assertIn("owner's active window went to a game window", wd.abort)
        with self.assertRaises(RuntimeError):
            with patch.object(gc, "WD", wd):
                gc.guard()


class NoUser32OnTheRunPath(unittest.TestCase):
    def test_no_direct_user32_calls(self):
        src = (REPO / "tools" / "game_checks.py").read_text(encoding="utf-8")
        self.assertNotIn("g.user32.", src)  # hc_hold posts through g.post_message (Windows: PostMessageW, Linux: the helper)
        # the remaining ctypes users sit behind a LINUX branch: the Watchdog's Windows loop and game_private_mb
        self.assertIn("if g.game_slots.LINUX:\n            return self._run_linux()", src)
        self.assertIn("if g.game_slots.LINUX:\n        return linux_private_mb(", src)

    def test_if_main_stays_last(self):
        src = (REPO / "tools" / "game_checks.py").read_text(encoding="utf-8").rstrip()
        self.assertTrue(src.endswith('if __name__ == "__main__":\n    main()'))
        names = re.findall(r"^def (\w+)\(", src, re.M)
        self.assertEqual(sorted(n for n in set(names) if names.count(n) > 1), [])


class HarnessSources(unittest.TestCase):
    def test_statbook_shares_the_stub_check(self):
        src = (REPO / "statbook" / "src" / "testharness.cpp").read_text(encoding="utf-8")
        self.assertIn('#include "testharness_logic.h"', src)
        self.assertIn("harness_logic::ClassifyStub(code)", src)
        self.assertNotIn("0xc3, 0xcd, 0x2e, 0xc3}", src)  # its own Windows-only copy of the shape is gone
        cm = (REPO / "statbook" / "CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("../plugin/src", cm)

    def test_diag_line_built_before_the_lock(self):
        src = (REPO / "plugin" / "src" / "testharness.cpp").read_text(encoding="utf-8")
        body = src[src.index("void DiagLine("):]
        body = body[:body.index("\n}\n")]
        self.assertLess(body.index("ModuleOf("), body.index("AcquireSRWLockExclusive(&g_diagLock)"))
        locked = body[body.index("AcquireSRWLockExclusive"):body.index("ReleaseSRWLockExclusive")]
        self.assertNotIn("ModuleOf", locked)


if __name__ == "__main__":
    unittest.main()
