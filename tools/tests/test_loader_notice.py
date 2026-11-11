"""tools/loader_notice.py: when D2RLoader's "not fully tested" notice is answered (docs/port-3.4.md 2.2).

Host-independent (CI runs this on Linux): the window list and the posted message are stand-ins, no DLL is loaded.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import loader_notice  # noqa: E402

TEXT = ("[WARN] This D2R version hasn't been fully tested yet. You're running Diablo II: Resurrected 3.4. "
        "The latest version officially supported by D2RLoader is 3.3.")


def line(t, text=TEXT):
    """A d2rloader.log line stamped at time t."""
    return time.strftime("[%Y-%m-%d %H:%M:%S", time.localtime(t)) + ".123] " + text + "\n"


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t


class LoaderNoticeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = os.path.join(self.tmp.name, "d2rloader.log")
        self.clock = Clock()
        self.posted = []
        self.windows = [4242]

    def watch(self):
        return loader_notice.Watch(self.log, find=lambda pids: list(self.windows) if 7 in pids else [],
                                   post=self.posted.append, clock=self.clock)

    def write(self, text, mode="w"):
        with open(self.log, mode, encoding="utf-8-sig" if mode == "w" else "utf-8") as f:
            f.write(text)

    def test_window_shape(self):
        ok = loader_notice.is_notice_window
        self.assertTrue(ok("#32770", "D2RLoader", True, ["OK"]))
        self.assertFalse(ok("#32770", "D2RLoader", False, ["OK"]), "hidden")
        self.assertFalse(ok("#32770", "D2RLoader", True, ["Yes", "No"]), "a question is not the notice")
        self.assertFalse(ok("#32770", "D2RLoader", True, []), "no button")
        self.assertFalse(ok("#32770", "Diablo II: Resurrected", True, ["OK"]), "another title")
        self.assertFalse(ok("OsWindow", "D2RLoader", True, ["OK"]), "not a dialog")

    def test_answered_once_after_the_settle_time(self):
        w = self.watch()
        self.write(line(self.clock.t, "[INFO] D2RLoader v1.3.1-beta (Release, Release) started.") + line(self.clock.t))
        self.assertIsNone(w.poll([7]), "first sight: not yet")
        self.assertEqual(self.posted, [])
        self.clock.t += loader_notice.SETTLE + 0.1
        said = w.poll([7])
        self.assertIn("answered with OK in the background", said)
        self.assertEqual(self.posted, [4242])
        self.clock.t += 5
        self.assertIsNone(w.poll([7]), "only once per launch")
        self.assertEqual(self.posted, [4242])

    def test_not_without_the_warning_line(self):
        w = self.watch()
        self.write(line(self.clock.t, "[INFO] start") + line(self.clock.t, "[ERROR] a plugin failed"))
        w.poll([7])
        self.clock.t += 5
        self.assertIsNone(w.poll([7]), "another D2RLoader dialog (an error) is not answered")
        self.assertEqual(self.posted, [])
        self.write(line(self.clock.t), "a")
        self.assertIsNotNone(w.poll([7]), "answered once the log holds the warning")

    def test_only_this_launch(self):
        self.write(line(self.clock.t - 600) + line(self.clock.t - 600, "[INFO] the previous run"))
        w = self.watch()
        w.poll([7])
        self.clock.t += 5
        self.assertIsNone(w.poll([7]), "the previous run's warning does not count")
        self.assertEqual(self.posted, [])
        self.write(line(self.clock.t - 5, "[INFO] start") + line(self.clock.t - 5))  # the log of this launch replaced it
        self.assertIsNotNone(w.poll([7]))

    def test_only_our_processes_and_no_window(self):
        w = self.watch()
        self.write(line(self.clock.t))
        self.assertIsNone(w.poll([]), "no process of ours")
        self.assertIsNone(w.poll([8]), "another process's dialog")
        self.clock.t += 5
        self.assertIsNone(w.poll([8]))
        self.windows = []
        self.assertIsNone(w.poll([7]), "no dialog (D2R 3.3, or the player ticked the box)")
        self.assertEqual(self.posted, [])

    def test_missing_log(self):
        self.assertFalse(loader_notice.log_has_notice(os.path.join(self.tmp.name, "none.log"), self.clock.t))


if __name__ == "__main__":
    unittest.main()
