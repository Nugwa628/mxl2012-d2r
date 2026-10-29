"""The game tools (game_slots, game_ctl, game_checks) drive a Windows game, but their pure logic is unit-tested on the Linux CI runner,
where ctypes has no `windll`. A subprocess removes windll/WinDLL/WINFUNCTYPE from ctypes (what Linux looks like) and checks that the
modules still import, that the process helpers answer "no game running", and that a real DLL call says it needs Windows.
Nothing here touches the game or a window."""
import os
import subprocess
import sys
import unittest

TOOLS = os.path.dirname(os.path.abspath(__file__))

NO_WINDOWS = r"""
import ctypes, sys
for name in ("windll", "oledll", "WinDLL", "OleDLL", "WINFUNCTYPE", "WinError", "FormatError", "GetLastError"):
    if hasattr(ctypes, name):
        delattr(ctypes, name)
sys.path.insert(0, sys.argv[1])
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import winapi, game_slots, game_ctl, game_checks
assert not winapi.available()
assert game_slots.processes() == [] and game_slots.slot_processes(game_slots.slot_dir(2)) == []
assert game_slots.pid_alive(4) is False
for call in (lambda: game_ctl.user32.GetForegroundWindow(), lambda: game_ctl.kernel32.GetCurrentThreadId()):
    try:
        call()
    except OSError as e:
        assert "only available on Windows" in str(e), e
    else:
        raise AssertionError("a DLL call must fail off Windows")
print("ok")
"""


class WithoutWindows(unittest.TestCase):
    def test_game_tools_import_and_degrade_without_windll(self):
        env = dict(os.environ, MXL_SLOT="2")
        r = subprocess.run([sys.executable, "-I", "-c", NO_WINDOWS, TOOLS], capture_output=True, text=True, env=env)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "ok"), r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
