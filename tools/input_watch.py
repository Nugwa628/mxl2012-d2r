#!/usr/bin/env python
"""Evidence that unattended game runs leave the user's mouse and focus alone.

Samples the real cursor position and the foreground window every 25 ms and notes
  - the cursor before / after / min..max range, and how often it moved (the user may be working on the PC),
  - samples with the cursor over any D2R game window rectangle (windows of D2RLoader.exe / D2R.exe processes; the
    games are placed on the primary monitor, so a resting cursor can sit under one without having been moved there),
  - samples where the cursor moved while over a game window,
  - TELEPORTS into a game window: the cursor changes by >= 300 px between two samples less than 60 ms apart (what
    SetCursorPos does; a hand sweeping across the screen is not that fast) and then stays put (within 3 px) for 0.5 s
    inside the game window rectangle,
  - samples with a D2R window as the foreground window.
Both are violations: the watcher writes `<out>.abort` (a runner should stop the games) and, as a program, ends with
exit code 2. The user is expected to keep using the PC while this runs; sweeping through a game window is only counted.
Only reads (GetCursorPos, GetForegroundWindow, EnumWindows); it never moves or activates anything.

  py -3 tools/input_watch.py OUT.json [--seconds N] [--stop-file F] [--slots 2,3]     runs until N seconds pass or F exists
Importable: Watcher(out).start() / .stop() -> summary dict.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys
import threading
import time

user32 = ctypes.windll.user32
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402


def _game_windows(pids):
    out = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(h):
            r = wt.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            out.append((h, r.left, r.top, r.right, r.bottom, pid.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


class Watcher:
    def __init__(self, out, period=0.025, folders=None):
        """folders: only games installed in these folders count (default: every D2R process)."""
        self.out, self.period, self.folders = out, period, folders
        self.stop_evt = threading.Event()
        self.thread = None
        self.s = {"samples": 0, "cursor_first": None, "cursor_last": None, "x_range": None, "y_range": None,
                  "cursor_moves": 0, "cursor_in_game_window": 0, "cursor_moved_in_game_window": 0, "teleports_into_game_window": 0, "game_foreground": 0, "max_gap_ms": 0,
                  "first_violation": None, "game_windows_seen": 0}

    def start(self):
        if os.path.exists(self.out + ".abort"):
            os.remove(self.out + ".abort")
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.stop_evt.set()
        self.thread.join(5)
        self.s["seconds"] = round(time.time() - self.t0, 1)
        json.dump(self.s, open(self.out, "w"), indent=1)
        return self.s

    def _violation(self, what):
        if not self.s["first_violation"]:
            self.s["first_violation"] = f"{time.strftime('%H:%M:%S')} {what}"
            open(self.out + ".abort", "w").write(self.s["first_violation"])

    def _run(self):
        s = self.s
        self.t0 = time.time()
        pt = wt.POINT()
        wins, pids, next_refresh, last, prev, pending = [], set(), 0, time.perf_counter(), None, None
        while not self.stop_evt.is_set():
            now = time.perf_counter()
            if now >= next_refresh:
                pids = {p for p, _, path in game_slots.processes() if not self.folders or any(game_slots.under(path, f) for f in self.folders)}
                wins = _game_windows(pids)
                s["game_windows_seen"] = max(s["game_windows_seen"], len(wins))
                next_refresh = now + 0.5
            user32.GetCursorPos(ctypes.byref(pt))
            c = (pt.x, pt.y)
            s["samples"] += 1
            if s["cursor_first"] is None:
                s["cursor_first"], s["x_range"], s["y_range"] = c, [c[0], c[0]], [c[1], c[1]]
            s["cursor_last"] = c
            s["x_range"] = [min(s["x_range"][0], c[0]), max(s["x_range"][1], c[0])]
            s["y_range"] = [min(s["y_range"][0], c[1]), max(s["y_range"][1], c[1])]
            moved = prev is not None and c != prev
            fast = moved and max(abs(c[0] - prev[0]), abs(c[1] - prev[1])) >= 300 and (now - last) < 0.06
            if moved:
                s["cursor_moves"] += 1
            prev = c
            inside = None
            for h, l, t, r, b, pid in wins:
                if l <= c[0] < r and t <= c[1] < b:
                    s["cursor_in_game_window"] += 1
                    if moved:
                        s["cursor_moved_in_game_window"] += 1
                    inside = (h, pid, (l, t, r, b))
                    break
            if fast and inside:
                pending = (now, c, inside)
            if pending and now - pending[0] >= 0.5:
                p0, pc, pin = pending
                pending = None
                if abs(c[0] - pc[0]) <= 3 and abs(c[1] - pc[1]) <= 3 and inside:
                    s["teleports_into_game_window"] += 1
                    self._violation(f"cursor teleported to {pc} and stayed inside game window {pin[0]:#x} (pid {pin[1]}) rect {pin[2]}")
            elif pending and (not inside or abs(c[0] - pending[1][0]) > 3 or abs(c[1] - pending[1][1]) > 3):
                pending = None  # it moved on: a hand sweeping through, not a teleport
            fg = user32.GetForegroundWindow()
            if fg:
                fpid = wt.DWORD()
                user32.GetWindowThreadProcessId(fg, ctypes.byref(fpid))
                if fpid.value in pids:
                    s["game_foreground"] += 1
                    self._violation(f"game window {fg:#x} (pid {fpid.value}) is the foreground window")
            s["max_gap_ms"] = max(s["max_gap_ms"], int((now - last) * 1000))
            last = now
            time.sleep(max(0, self.period - (time.perf_counter() - now)))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 0
    seconds = float(a[a.index("--seconds") + 1]) if "--seconds" in a else 1e9
    stopf = a[a.index("--stop-file") + 1] if "--stop-file" in a else None
    folders = a[a.index("--slots") + 1].split(",") if "--slots" in a else None
    w = Watcher(a[0], folders=[game_slots.slot_dir(int(n)) for n in folders] if folders else None).start()
    t0 = time.time()
    while time.time() - t0 < seconds and not (stopf and os.path.exists(stopf)) and not os.path.exists(a[0] + ".abort"):
        time.sleep(0.2)
    s = w.stop()
    print(json.dumps(s))
    return 2 if s["first_violation"] else 0


if __name__ == "__main__":
    sys.exit(main())
