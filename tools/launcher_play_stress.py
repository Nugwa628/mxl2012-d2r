"""Play stress check of the downloader window without D2R (bug #539, docs/testing.md "Lane dlvanish").

    py -3 tools/launcher_play_stress.py --exe <D2R-XL-2012-Downloader.exe> --fake-loader <fake_loader.exe> --work DIR
                                        [--cycles 20] [--game-seconds 5]

Builds a fake D2R folder in DIR (D2R.exe of a few bytes, .build.info 3.3.93847, the fake loader as D2RLoader.exe, a
mods\\mxl2012 with the downloader's marker), an own --data-dir and an empty --site (the channel is unreachable, so the
installed release counts as up to date). The window is driven only by WM_COMMAND / WM_CLOSE to its own HWND (no input):

  1. WM_CLOSE right after the start-up check: exit code 0, "window: closed (title bar ..." and the exit line in the log.
  2. close-after-start off: `--cycles` times Play, the fake game runs `--game-seconds`, ends, Play is on again. After
     every cycle the process must be alive and its window visible and not minimised.
  3. close-after-start on (the check box): Play, the window closes, "window: closed after Play" and the exit line.

Nothing outside DIR is written; the fake loader starts nothing. Exit code 0 when every check passed.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import time

IdPlay, IdCloseAfterPlay = 113, 114  # launcher/src/win/window.cpp
WM_COMMAND, WM_CLOSE = 0x0111, 0x0010
TITLE = "D2R-XL 2012 Downloader"
BUILD_INFO = ("Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|CDN Key!HEX:16|Install Key!HEX:16|IM Size!DEC:4|"
              "CDN Path!STRING:0|CDN Hosts!STRING:0|CDN Servers!STRING:0|Tags!STRING:0|Armadillo!STRING:0|"
              "Last Activated!STRING:0|Version!STRING:0|KeyRing!HEX:16|Product!STRING:0\n"
              "us|1|0|0|0|0|||||||3.3.93847||osi\n")

user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
results = []


def log(msg):
    print(time.strftime("%H:%M:%S ") + msg, flush=True)


def check(ok, what):
    results.append((bool(ok), what))
    log(("PASS " if ok else "FAIL ") + what)
    return ok


def main_window(pid):
    found = []

    def cb(h, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            b = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, b, 256)
            if b.value.startswith(TITLE):
                found.append(h)
        return True
    user32.EnumWindows(EnumProc(cb), 0)
    return found[0] if found else None


def wait(cond, seconds, step=0.25):
    t0 = time.time()
    while time.time() - t0 < seconds:
        if cond():
            return True
        time.sleep(step)
    return cond()


def make_fake(work, fake_loader, game_seconds):
    d2r, data, site = (os.path.join(work, n) for n in ("d2r", "data", "site"))
    for d in (d2r, data, site):
        if os.path.exists(d):
            shutil.rmtree(d)
    os.makedirs(os.path.join(d2r, "Data"))
    os.makedirs(os.path.join(d2r, "mods", "mxl2012"))
    os.makedirs(data)
    os.makedirs(site)
    with open(os.path.join(d2r, "D2R.exe"), "wb") as f:
        f.write(b"MZ fake")
    with open(os.path.join(d2r, ".build.info"), "w", newline="\n") as f:
        f.write(BUILD_INFO)
    shutil.copy2(fake_loader, os.path.join(d2r, "D2RLoader.exe"))
    with open(os.path.join(d2r, "fake-loader.txt"), "w") as f:
        f.write(str(game_seconds))
    marker = {"made_by": "D2R-XL 2012 Downloader", "id": "stress", "version": "0.0.0-stress"}
    with open(os.path.join(d2r, "mods", "mxl2012", "mxl2012-install.json"), "w") as f:
        json.dump(marker, f)
    return d2r, data, site


def set_close_after_play(data, value):
    p = os.path.join(data, "launcher.json")
    state = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    state["close_after_play"] = value
    json.dump(state, open(p, "w", encoding="utf-8"))


def log_lines(data):
    try:
        return open(os.path.join(data, "launcher.log"), encoding="utf-8").read().splitlines()
    except OSError:
        return []


def loader_starts(d2r):
    try:
        return len(open(os.path.join(d2r, "fake-loader.log"), encoding="utf-8").read().splitlines())
    except OSError:
        return 0


class Window:
    def __init__(self, exe, d2r, data, site):
        self.p = subprocess.Popen([exe, "--game-dir", d2r, "--data-dir", data, "--site", site])
        self.h = None
        wait(lambda: self.find(), 30)

    def find(self):
        self.h = main_window(self.p.pid)
        return self.h is not None

    def play_on(self):
        return bool(user32.IsWindowEnabled(user32.GetDlgItem(self.h, IdPlay)))

    def command(self, cid):
        user32.PostMessageW(self.h, WM_COMMAND, cid, user32.GetDlgItem(self.h, cid))

    def shown(self):
        return self.p.poll() is None and user32.IsWindowVisible(self.h) and not user32.IsIconic(self.h)


def lines_since(data, n0, text):
    return [l for l in log_lines(data)[n0:] if text in l]


def run(args):
    work = os.path.abspath(args.work)
    d2r, data, site = make_fake(work, args.fake_loader, args.game_seconds)
    log(f"fake D2R {d2r}, data {data}, site {site} (empty)")

    # 1. WM_CLOSE
    n0 = len(log_lines(data))
    w = Window(args.exe, d2r, data, site)
    if not check(w.h, "window 1 found"):
        return
    check(wait(w.play_on, 30), "window 1: Play on after the start-up check (channel unreachable, release installed)")
    user32.PostMessageW(w.h, WM_CLOSE, 0, 0)
    check(wait(lambda: w.p.poll() is not None, 15) and w.p.returncode == 0, f"WM_CLOSE: the process ends, exit code {w.p.poll()}")
    check(lines_since(data, n0, "window: closed (title bar"), "WM_CLOSE: its close line is in the log")
    check(lines_since(data, n0, "Downloader ends (exit code 0)"), "WM_CLOSE: the exit line is in the log")

    # 2. close-after-start off: Play / game ends / Play on again, many times
    set_close_after_play(data, False)
    n0 = len(log_lines(data))
    w = Window(args.exe, d2r, data, site)
    if not check(w.h, "window 2 found"):
        return
    check(wait(w.play_on, 30), "window 2: Play on")
    origin = [l for l in log_lines(data)[n0:] if "(window, process" in l]
    check(origin and f"process {w.p.pid}, started by" in origin[-1], "window 2: the start line names the process and its parent")
    ok_cycles = 0
    for i in range(args.cycles):
        starts = loader_starts(d2r)
        w.command(IdPlay)
        started = wait(lambda: loader_starts(d2r) > starts, 10)
        off = wait(lambda: not w.play_on(), 5)
        back = wait(w.play_on, args.game_seconds + 12)
        alive = w.shown()
        if started and off and back and alive:
            ok_cycles += 1
        else:
            log(f"cycle {i + 1}: started {started}, Play off {off}, Play on again {back}, window shown {alive}")
        if w.p.poll() is not None:
            break
    check(ok_cycles == args.cycles, f"close-after-start off: {ok_cycles} of {args.cycles} cycles Play -> game ends -> Play on, window shown")
    check(len(lines_since(data, n0, "is starting (D2RLoader.exe")) == args.cycles, "close-after-start off: one start line per cycle")
    check(not lines_since(data, n0, "window: closed"), "close-after-start off: no close line while it ran")

    # 3. close-after-start on (the check box), Play closes the window
    n1 = len(log_lines(data))
    w.command(IdCloseAfterPlay)
    check(wait(lambda: json.load(open(os.path.join(data, "launcher.json"), encoding="utf-8")).get("close_after_play") is True, 5),
          "check box: close_after_play = true")
    w.command(IdPlay)
    check(wait(lambda: w.p.poll() is not None, 15) and w.p.returncode == 0, f"close-after-start on: the window closes after Play, exit code {w.p.poll()}")
    check(lines_since(data, n1, "window: closed after Play"), "close-after-start on: its close line is in the log")
    check(lines_since(data, n1, "Downloader ends (exit code 0)"), "close-after-start on: the exit line is in the log")
    time.sleep(args.game_seconds + 1)  # the last fake game ends by itself
    check(not [l for l in log_lines(data) if l[20:].startswith("crash:")], "no crash line in the whole log")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--exe", required=True)
    ap.add_argument("--fake-loader", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--cycles", type=int, default=20)
    ap.add_argument("--game-seconds", type=int, default=5)
    args = ap.parse_args()
    if args.game_seconds < 4:
        sys.exit("--game-seconds must be at least 4 (Play counts a loader that ends within 3 s as a failed start)")
    run(args)
    failed = [w for ok, w in results if not ok]
    log(f"{len(results) - len(failed)} of {len(results)} checks passed")
    sys.exit(1 if failed or not results else 0)


if __name__ == "__main__":
    main()
