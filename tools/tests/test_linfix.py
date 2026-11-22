"""Lane linfix (2026-11-20): fake focus off by default under Wine, the per-launch first-chance report (Stat Book's child
list scan) and the run cleanup, the private display's window placement (the 1574 x 828 frames) and the clickmap check, and
stop_prefix's fallback for orphaned prefix processes. No game, Wine or X needed."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc  # noqa: E402
import game_slots  # noqa: E402
import run_cleanup  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

# the head of a report lane linharness's runs wrote at every launch (r15, statbook b3); the stack is left out
FINDKIDS_REPORT = """D2R last-resort crash report
Record: 1 of at most 2
Generated UTC: 2026-11-20 03:41:05.301
Process: 340
Thread: 344

First-Chance Exception
  Code: 0xC0000005 (EXCEPTION_ACCESS_VIOLATION)
  Address: 00006FFFFBEC5599
  Flags: 0x00000000
  Allocation Base: 00006FFFFBEB0000 + 0x15599
  RIP: 0x00006FFFFBEC5599

Exception Parameters
  [00] 0x0000000000000000
  [01] 0x0000000000000013
"""
REAL_CRASH = """D2R crash report
Generated: 2026-11-20 13:01:24.747
Kind: unhandled exception
Process: 340
"""


def write(path, text=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


class KnownHandled(unittest.TestCase):
    def test_findkids_report_is_known(self):
        self.assertIn("FindKids", run_cleanup.known_handled(FINDKIDS_REPORT))

    def test_diag_probe_report_is_known(self):
        diag = FINDKIDS_REPORT.replace("00006FFFFBEB0000 + 0x15599", "00006FFFFC050000 + 0x65FC4").replace(
            "0x0000000000000013", "0x0000000000000017")
        self.assertIn("diag", run_cleanup.known_handled(diag))

    def test_others_are_evidence(self):
        self.assertIsNone(run_cleanup.known_handled(REAL_CRASH))
        self.assertIsNone(run_cleanup.known_handled(FINDKIDS_REPORT.replace("+ 0x15599", "+ 0x2976D")))  # bug #399's kind
        self.assertIsNone(run_cleanup.known_handled(FINDKIDS_REPORT.replace("0x0000000000000013", "0x0000000000616D41")))
        self.assertIsNone(run_cleanup.known_handled(FINDKIDS_REPORT.replace("[00] 0x0000000000000000", "[00] 0x0000000000000001")))
        self.assertIsNone(run_cleanup.known_handled(FINDKIDS_REPORT.replace("0xC0000005", "0xC0000094")))
        # bug #517 / run p2's kind: a last-resort record at a game image offset, a read of 0x10C
        self.assertIsNone(run_cleanup.known_handled(FINDKIDS_REPORT.replace("+ 0x15599", "+ 0x1462D3D")))


class RunCleanup(unittest.TestCase):
    def make_run(self, report=None, ctl_log="13:00 stopped\n"):
        d = tempfile.mkdtemp()
        if report is not None:
            write(os.path.join(d, "report.md"), report)
        write(os.path.join(d, "game_ctl.log"), ctl_log)
        write(os.path.join(d, "focus.json"), "{}")
        write(os.path.join(d, "logscan.txt"), "d2rloader.log: 0 ERROR")
        write(os.path.join(d, "steam-0.log"), "steam")
        write(os.path.join(d, "xvfb.log"), "x")
        write(os.path.join(d, "proton.out"), "")
        write(os.path.join(d, "intro_end.png"), "png")
        write(os.path.join(d, "mxl2012.png"), "png")
        write(os.path.join(d, "slot-logs-1", "blz-log.txt"), "b")
        write(os.path.join(d, "slot-logs-1", "d2rloader", "logs", "d2rloader.log"), "log")
        write(os.path.join(d, "slot-logs-1", "d2rloader", "crashes", "d2r-lastresort-crash-report (x pid-340).log"), FINDKIDS_REPORT)
        write(os.path.join(d, "slot-logs-1", "d2rloader", "crashes", "d2r-crash-report (y).log"), REAL_CRASH)
        write(os.path.join(d, "slot-logs-1", "d2rloader", "crashes", "d2r-crash-report (y).dmp"), "MDMP")
        return d

    def left(self, d):
        return sorted(os.path.relpath(os.path.join(r, f), d).replace(os.sep, "/") for r, _, fs in os.walk(d) for f in fs)

    def test_passed_run(self):
        d = self.make_run("| Check | Result | Note | Evidence |\n|---|---|---|---|\n| mxl2012 | PASS | ok | mxl2012.png |\n")
        lines = []
        n, size = run_cleanup.clean(d, log=lines.append)
        self.assertEqual(self.left(d), ["focus.json", "game_ctl.log", "logscan.txt", "mxl2012.png", "report.md",
                                        "slot-logs-1/d2rloader/crashes/d2r-crash-report (y).dmp",
                                        "slot-logs-1/d2rloader/crashes/d2r-crash-report (y).log"])
        self.assertEqual(n, 7)
        self.assertGreater(size, 0)
        self.assertTrue(lines and lines[0].startswith("run cleanup: 7 files"), lines)
        self.assertIn("known handled exception", lines[0])
        self.assertFalse(os.path.isdir(os.path.join(d, "slot-logs-1", "d2rloader", "logs")))  # emptied folders go

    def test_failed_run_keeps_its_logs(self):
        d = self.make_run("| Check | Result | Note | Evidence |\n|---|---|---|---|\n| clickmap | FAIL | no | x.png |\n")
        run_cleanup.clean(d, log=lambda s: None)
        left = self.left(d)
        self.assertIn("steam-0.log", left)
        self.assertIn("slot-logs-1/d2rloader/logs/d2rloader.log", left)
        self.assertIn("intro_end.png", left)
        self.assertNotIn("proton.out", left)  # empty
        self.assertNotIn("slot-logs-1/d2rloader/crashes/d2r-lastresort-crash-report (x pid-340).log", left)
        self.assertIn("slot-logs-1/d2rloader/crashes/d2r-crash-report (y).log", left)

    def test_driver_run_without_report(self):
        ok = self.make_run(None, "13:00 STEP enter True\n13:01 DRIVER: done rc=0\n")
        bad = self.make_run(None, "13:00 TIMEOUT waiting for startup line\n13:01 DRIVER: done rc=1\n")
        self.assertTrue(run_cleanup.run_passed(ok))
        self.assertFalse(run_cleanup.run_passed(bad))
        self.assertFalse(run_cleanup.run_passed(tempfile.mkdtemp()))

    def test_cited_shots_and_dry_run(self):
        d = self.make_run(None, "DRIVER: done rc=0\n")
        n, _ = run_cleanup.clean(d, cited_texts=["see intro_end.png"], dry_run=True, log=lambda s: None)
        self.assertIn("intro_end.png", self.left(d))
        self.assertIn("steam-0.log", self.left(d))  # dry run: nothing removed
        self.assertNotIn("intro_end.png", [os.path.basename(p) for p, _ in run_cleanup.plan(d, ["see intro_end.png"])])
        self.assertIn("mxl2012.png", [os.path.basename(p) for p, _ in run_cleanup.plan(d)])

    def test_a_run_a_report_names_keeps_everything(self):
        d = self.make_run(None, "DRIVER: done rc=0\n")
        name = os.path.basename(d)
        kept = [os.path.basename(p) for p, _ in run_cleanup.plan(d, ["evidence: `runs/%s` (diag)" % name])]
        self.assertEqual(sorted(kept), ["d2r-lastresort-crash-report (x pid-340).log", "proton.out"])  # the always-rules only
        self.assertIn("steam-0.log", [os.path.basename(p) for p, _ in run_cleanup.plan(d, ["runs/%s0 other" % name])])

    def test_game_checks_calls_it_on_linux_only(self):
        with patch.object(gc.g, "current_run", return_value="/nonexistent"), patch("run_cleanup.clean") as c:
            with patch.object(gc.g.game_slots, "LINUX", True), patch.dict(os.environ, {"MXL_KEEP_RUN_FILES": ""}):
                gc.run_cleanup_linux()
            self.assertEqual(c.call_count, 1)
            with patch.object(gc.g.game_slots, "LINUX", True), patch.dict(os.environ, {"MXL_KEEP_RUN_FILES": "1"}):
                gc.run_cleanup_linux()
            with patch.object(gc.g.game_slots, "LINUX", False):
                gc.run_cleanup_linux()
            self.assertEqual(c.call_count, 1)
        src = (REPO / "tools" / "game_checks.py").read_text(encoding="utf-8")
        body = src[src.index("def run_all("):src.index("def run_cleanup_linux(")]
        self.assertIn("run_cleanup_linux()", body.split("write_report(")[-1])  # after the report


class Clickmap(unittest.TestCase):
    def test_direction(self):
        c = (800, 430)
        self.assertTrue(gc.clickmap_direction((40, 40), c, (-6, 0)))     # up left: world x down
        self.assertTrue(gc.clickmap_direction((1560, 40), c, (0, -4)))   # up right: world y down
        self.assertTrue(gc.clickmap_direction((40, 700), c, (0, 4)))     # down left
        self.assertTrue(gc.clickmap_direction((1560, 700), c, (26, -4)))  # down right
        self.assertFalse(gc.clickmap_direction((40, 40), c, (6, 0)))
        self.assertIsNone(gc.clickmap_direction((40, 40), c, (0, 0)))

    def test_full_frame_and_diff(self):
        from PIL import Image
        full = Image.new("RGB", (1600, 900), (60, 60, 60))
        cut = Image.new("RGB", (1600, 900), (0, 0, 0))
        cut.paste(full.crop((0, 0, 1574, 828)))  # lane linharness's slot 5 frames
        self.assertTrue(gc.clickmap_full_frame(full))
        self.assertFalse(gc.clickmap_full_frame(cut))
        self.assertEqual(gc.clickmap_diff(full, full, gc.CLICKMAP_LEFT), 0)
        self.assertAlmostEqual(gc.clickmap_diff(full, cut, (1580, 0, 1600, 900)), 60, places=3)
        half = full.resize((800, 450))  # the boxes scale with the shot
        self.assertEqual(gc.clickmap_diff(half, half.copy(), gc.CLICKMAP_RIGHT), 0)

    def test_orb(self):
        from PIL import Image
        img = Image.new("RGB", (1600, 900), (20, 20, 20))
        self.assertFalse(gc.clickmap_orb(img))
        img.paste((200, 30, 30), (376, 783, 424, 828))
        self.assertTrue(gc.clickmap_orb(img))

    def test_registered_and_spots_inside_the_client(self):
        self.assertIn("clickmap", [n for n, _ in gc.CHECKS])
        for x, y in list(gc.CLICKMAP_SPOTS.values()) + list(gc.CLICKMAP_CORNERS.values()):
            self.assertTrue(0 <= x < 1600 and 0 <= y < 900)
        self.assertTrue(any(y > 828 for _, y in gc.CLICKMAP_SPOTS.values()))  # the strip the cut frames never showed

    def test_game_checks_layout(self):
        src = (REPO / "tools" / "game_checks.py").read_text(encoding="utf-8")
        names = re.findall(r"^def (\w+)\(", src, re.M)
        self.assertEqual(len(names), len(set(names)), [n for n in set(names) if names.count(n) > 1])
        self.assertTrue(src.rstrip().endswith('if __name__ == "__main__":\n    main()'))


class StopPrefixFallback(unittest.TestCase):
    def test_orphans_are_killed(self):
        idle = iter([False, True])
        with patch.object(game_slots.subprocess, "run"), patch.object(game_slots, "wineserver_cmd", return_value=["ws", "-k"]), \
                patch.object(game_slots, "wine_env", return_value={}), \
                patch.object(game_slots, "wait_prefix_idle", side_effect=lambda n, t=0: next(idle)), \
                patch.object(game_slots, "prefix_pids", return_value=[111, 222]), patch.object(game_slots.os, "kill") as kill:
            self.assertTrue(game_slots.stop_prefix(5, timeout=1))
        self.assertEqual([c.args for c in kill.call_args_list], [(111, 9), (222, 9)])

    def test_nothing_killed_when_wineserver_ends_them(self):
        with patch.object(game_slots.subprocess, "run"), patch.object(game_slots, "wineserver_cmd", return_value=["ws", "-k"]), \
                patch.object(game_slots, "wine_env", return_value={}), \
                patch.object(game_slots, "wait_prefix_idle", return_value=True), patch.object(game_slots.os, "kill") as kill:
            self.assertTrue(game_slots.stop_prefix(5, timeout=1))
        kill.assert_not_called()


class PluginSources(unittest.TestCase):
    def test_fake_focus_off_by_default(self):
        logic = (REPO / "plugin" / "src" / "testharness_logic.h").read_text(encoding="utf-8")
        self.assertIn("inline auto WantFakeFocus(const char* mode) noexcept -> bool", logic)
        harness = (REPO / "plugin" / "src" / "testharness.cpp").read_text(encoding="utf-8")
        self.assertIn("g_fakeFocus = harness_logic::WantFakeFocus(mode);", harness)
        import game_ctl_linux
        self.assertNotIn("harness_switch", game_ctl_linux.OVERRIDES)  # no tool-side nofakefocus any more

    def test_statbook_scan_reads_no_junk_pair(self):
        src = (REPO / "statbook" / "src" / "sheet_host.cpp").read_text(encoding="utf-8")
        body = src[src.index("auto FindKids("):src.index("auto Kids(")]
        self.assertIn("ListAt(panel, off, false, &b, &e)", body)
        self.assertLess(body.index("ListAt("), body.index("__try"))  # checked before any read under SEH
        self.assertIn("sheet_host::PlausibleList(", src)


if __name__ == "__main__":
    unittest.main()
