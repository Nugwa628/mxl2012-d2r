"""Background mode of tools/game_ctl.py (the default) must not take, move or steal anything on the user's desktop: a simulated start,
a refused minimized-window restore, key presses and a click run against a mocked user32, and none of SetForegroundWindow, SetActiveWindow,
SetCursorPos, keybd_event, mouse_event or SendInput may be called. The old path (MXL_INPUT=sendinput) is still there and is checked to
use them, so the test cannot pass because the mock saw nothing. No game is started and no real window is touched."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ["MXL_SLOT"] = "2"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import game_ctl  # noqa: E402

FORBIDDEN = {"SetForegroundWindow", "SetActiveWindow", "SetCursorPos", "keybd_event", "mouse_event", "SendInput"}
GAME_HWND, OTHER_HWND = 1111, 2222


def fake_user32():
    u = MagicMock(name="user32")
    u.GetForegroundWindow.return_value = GAME_HWND  # the game took the foreground: a give-back would fire here
    u.IsIconic.return_value = False
    u.SendInput.return_value = 1
    return u


def called(u):
    return sorted({c[0] for c in u.method_calls} & FORBIDDEN)


@unittest.skipUnless(sys.platform == "win32", "launch path uses subprocess.STARTUPINFO (Windows only)")
class Nofocus(unittest.TestCase):
    def run_scenario(self, bg):
        u = fake_user32()
        popen = MagicMock(name="Popen")
        stack = [
            patch.object(game_ctl, "user32", u), patch.object(game_ctl, "BG", bg),
            patch.object(game_ctl, "log"), patch.object(game_ctl, "save_state"),
            patch.object(game_ctl, "load_state", return_value={}), patch.object(game_ctl, "game_pids", return_value=[]),
            patch.object(game_ctl, "take_lock", return_value=True), patch.object(game_ctl, "harness_switch"),
            patch.object(game_ctl, "snapshot_marks"), patch.object(game_ctl, "wait_log", return_value=True),
            patch.object(game_ctl, "find_window", return_value=GAME_HWND), patch.object(game_ctl, "need_window", return_value=GAME_HWND),
            patch.object(game_ctl, "vinput", return_value=[0] * 8), patch.object(game_ctl.slot_share, "begin", return_value="begin"),
            patch.object(game_ctl.slot_share, "launch_args", return_value=["-mod", "mxl2012"]),
            patch.object(game_ctl.subprocess, "Popen", popen), patch.object(game_ctl.time, "sleep"),
        ]
        for p in stack:
            p.start()
        self.addCleanup(patch.stopall)
        u.GetForegroundWindow.side_effect = [OTHER_HWND] + [GAME_HWND] * 400  # before the launch, then the game owns it
        self.assertTrue(game_ctl.start())
        u.IsIconic.side_effect = None
        u.IsIconic.return_value = True
        result = game_ctl.restore_noactivate(GAME_HWND, wait=0.0)
        if bg:
            self.assertFalse(result)
        u.IsIconic.return_value = False
        game_ctl.key("esc", "ctrl+f1")
        game_ctl.type_text("Ab")
        game_ctl.click(0.5, 0.5)
        return u, popen

    def test_default_path_calls_none_of_the_focus_and_input_apis(self):
        u, popen = self.run_scenario(bg=True)
        self.assertEqual(called(u), [], "background mode touched the desktop")
        # the loader is started without activation
        si = popen.call_args.kwargs["startupinfo"]
        self.assertTrue(si.dwFlags & game_ctl.subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(si.wShowWindow, 4)  # SW_SHOWNOACTIVATE
        u.ShowWindow.assert_not_called()

    def test_minimized_window_is_never_restored_for_capture_or_resize(self):
        u = fake_user32()
        u.IsIconic.return_value = True
        with patch.object(game_ctl, "user32", u), patch.object(game_ctl, "BG", True):
            with self.assertRaisesRegex(RuntimeError, "minimized"):
                game_ctl.fit_window(GAME_HWND)
            with self.assertRaisesRegex(RuntimeError, "minimized"):
                game_ctl.grab_printwindow(GAME_HWND)
        u.ShowWindow.assert_not_called()
        self.assertEqual(called(u), [])

    def test_old_sendinput_path_is_still_there_behind_the_opt_in(self):
        u, _ = self.run_scenario(bg=False)
        self.assertTrue(set(called(u)) >= {"SetForegroundWindow", "SetCursorPos", "SendInput"}, called(u))

    def test_default_is_background_unless_opted_in(self):
        self.assertEqual(game_ctl.BG, os.environ.get("MXL_INPUT", "").lower() != "sendinput")


if __name__ == "__main__":
    unittest.main()
