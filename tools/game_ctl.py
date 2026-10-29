#!/usr/bin/env python
"""Drive D2R + D2RLoader (D2R-XL 2012) for unattended smoke checks.

Run with `py -3 tools/game_ctl.py <command>`. Commands:
  start                 launch D2RLoader, wait for startup log line and the game window
  shot NAME             screenshot of the game window's client area only
  key KEY [KEY..]       send keys (names: esc enter tab space up down left right f1.. or single chars)
  click FX FY [right]   click at a fraction (0..1) of the client rect
  console CMD           open the developer console (Ctrl+`), type CMD, Enter, close
  stop                  close the game (CloseMainWindow, force after timeout)
  harness on|off        write or remove the plugin test-harness file (for a game started by the launcher)
  logscan               new ERROR/ASSERT lines, mxl2012-core.log summary, new crash files
  smoke                 full scenario, writes report.md in the run folder
Run folders: <repo>\\work\\runs\\<run> (env MXL_RUNS); the current run name is kept in runs\\current.txt.
Privacy: only the game window client rect is ever captured, never the whole desktop.
Input modes: background (default) posts window messages to the game window, captures it with PrintWindow and
never moves the real cursor, sends global keys or takes focus. `--foreground` (anywhere on the command line) or
env MXL_INPUT=sendinput selects the old SendInput + SetCursorPos + SetForegroundWindow path (lanes must not use it).
MXL_RUN=<name> pins the run folder (instead of runs\\current.txt, which is shared between lanes).
Slots: `--slot N` (anywhere on the command line) or env MXL_SLOT=N picks game slot 1 to 5 (tools/game_slots.py).
There is no default slot; a slot whose folder is missing (4 and 5 before they are copied) is refused. MXL_D2R_GAME may only name the folder of the chosen slot. Slot 1 is the owner's own game
(game_slots.OWNER_SLOTS): `start` refuses while any game runs in its folder that this run did not start (the owner may be
playing), and no command attaches to, sends input to, captures, closes or kills such a game (game_pids sees none).
Every function works on that slot's process and window only (found by process, never by title alone) and `start`
takes the slot's run lock (game.lock.N, slot 1 also the old game.lock; shared with the other tools of this machine)
until `stop`.
Sharing with the other mod (tools/slot_share.py): `start` snapshots the slot's game-wide d2rloader\\config and starts the loader
with `-mod mxl2012` on its command line (default_mod in the shared toml is never edited); `stop` restores the snapshot
byte for byte once the game is gone, before the lock is released.
"""
import ctypes
import ctypes.wintypes as wt
import datetime
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402
import slot_share  # noqa: E402
import winapi  # noqa: E402

if "--slot" in sys.argv:
    _i = sys.argv.index("--slot")
    os.environ["MXL_SLOT"] = sys.argv[_i + 1]
    del sys.argv[_i:_i + 2]
SLOT = game_slots.env_slot()  # 1 to 5; an unset or other MXL_SLOT ends the tool here (a missing folder: main())
# MXL_D2R_GAME may only be the folder of the chosen slot (a moved slot folder); any other folder is refused.
GAME_DIR = os.environ.get("MXL_D2R_GAME") or game_slots.slot_dir(SLOT)
if game_slots.slot_of_game_dir(GAME_DIR) != SLOT:
    raise SystemExit(f"MXL_D2R_GAME {GAME_DIR!r} is not the folder of slot {SLOT}: refused")
LOADER_NAME = game_slots.loader_name(GAME_DIR)
LOADER = os.path.join(GAME_DIR, LOADER_NAME)
LOADER_LOG = os.path.join(GAME_DIR, r"d2rloader\logs\d2rloader.log")
MXL_LOG = os.path.join(GAME_DIR, r"mods\mxl2012\d2rloader\logs\mxl2012-core.log")
CRASH_DIR = os.path.join(GAME_DIR, r"d2rloader\crashes")
RUNS = game_slots.RUNS  # run output stays in this repo (work/runs); only the lock folders are shared (machine.json)


def _savepath():
    """This game folder's save folder (modinfo.json savepath; the slot copies use mxl2012-sN). D2R reads
    mxl2012.mpq/modinfo.json; a release / launcher install has only that one, so it comes first."""
    sp = f"mxl2012-s{SLOT}/"
    for rel in (("mxl2012.mpq", "modinfo.json"), ("modinfo.json",)):
        try:
            sp = json.load(open(os.path.join(GAME_DIR, "mods", "mxl2012", *rel)))["savepath"]
            break
        except Exception:
            pass
    return os.path.join(game_slots.SAVE_ROOT, sp.strip("/\\").replace("/", "\\"))


SAVES = _savepath()
LOCK_OWNER = os.environ.get("MXL_RUN") or f"run-{os.getpid()}"
TITLE = "Diablo II: Resurrected"
CLIENT_W, CLIENT_H = 1600, 900
CHAR_NAME = os.environ.get("MXL_CHAR", "Mxl2Barb")  # a lane that must not touch the shared test character names its own

if "--foreground" in sys.argv:
    sys.argv.remove("--foreground")
    os.environ["MXL_INPUT"] = "sendinput"
BG = os.environ.get("MXL_INPUT", "").lower() != "sendinput"

user32 = winapi.Dll("user32")
kernel32 = winapi.Dll("kernel32")
if winapi.available():  # the pure logic imports (and is tested) off Windows too; the DLLs load on first use
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()

# ---------------------------------------------------------------- run state


def current_run(create=False):
    os.makedirs(RUNS, exist_ok=True)
    cur = os.path.join(RUNS, "current.txt")
    if os.environ.get("MXL_RUN"):
        d = os.path.join(RUNS, os.environ["MXL_RUN"])
        os.makedirs(d, exist_ok=True)
        return d
    if create or not os.path.exists(cur):
        name = datetime.datetime.now().strftime("run-%Y%m%d-%H%M%S")
        open(cur, "w").write(name)
    name = open(cur).read().strip()
    d = os.path.join(RUNS, name)
    os.makedirs(d, exist_ok=True)
    return d


def state_path():
    return os.path.join(current_run(), "state.json")


def load_state():
    try:
        return json.load(open(state_path()))
    except Exception:
        return {}


def save_state(s):
    json.dump(s, open(state_path(), "w"))


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with open(os.path.join(current_run(), "game_ctl.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ---------------------------------------------------------------- processes / windows


def game_pids():
    """PIDs of this slot's loader (image path inside the slot's game folder: other slots' games are not ours). On slot 1
    a game this run did not start (the owner's own) gives none: no command ever touches it."""
    pids = [pid for pid, _ in game_slots.slot_processes(GAME_DIR, (LOADER_NAME.lower(),))]
    if pids and game_slots.foreign_game(SLOT, LOCK_OWNER):
        return []
    return pids


def find_window():
    """HWND of this slot's game window: a visible top-level window titled TITLE that belongs to one of the slot's
    processes (matched by PID, so several instances never mix)."""
    pids = set(game_pids())
    found = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(h, _):
        if not user32.IsWindowVisible(h):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value not in pids:
            return True
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        if buf.value == TITLE or buf.value.startswith(TITLE + " ["):  # "... [s2]": the harness tags the test slots
            found.append((h, pid.value))
        return True

    if pids:
        user32.EnumWindows(cb, 0)
    return found[0][0] if found else None


def client_rect(h):
    """Client rect in screen coords: (left, top, right, bottom)."""
    r = wt.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(pt))
    return pt.x, pt.y, pt.x + r.right, pt.y + r.bottom


def focus(h):
    if BG:
        return  # background mode never takes focus
    if user32.IsIconic(h):
        user32.ShowWindow(h, 9)
    # Alt-key trick so SetForegroundWindow is allowed
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(h)
    user32.BringWindowToTop(h)
    time.sleep(0.3)


def fit_window(h, x=None, y=None):
    """Resize so the client area is CLIENT_W x CLIENT_H, placed at (x, y) on the primary monitor (the slots cascade)."""
    x = 100 + 60 * (SLOT - 1) if x is None else x
    y = 60 + 40 * (SLOT - 1) if y is None else y
    fl = 0x0004 | (0x0010 if BG else 0)  # SWP_NOZORDER (| SWP_NOACTIVATE in background mode)
    if user32.IsIconic(h):
        if BG:
            raise RuntimeError("game window is minimized: background mode will not restore it")
        user32.ShowWindow(h, 1)  # SW_SHOWNORMAL
    elif not BG:
        user32.ShowWindow(h, 1)
    user32.SetWindowPos(h, 0, x, y, CLIENT_W + 40, CLIENT_H + 80, fl)
    time.sleep(0.5)
    l, t, r, b = client_rect(h)
    wr = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(wr))
    dw = (wr.right - wr.left) - (r - l)
    dh = (wr.bottom - wr.top) - (b - t)
    user32.SetWindowPos(h, 0, x, y, CLIENT_W + dw, CLIENT_H + dh, fl)
    time.sleep(0.8)
    return client_rect(h)


def need_window(wait=20):
    """The slot's game window; waits up to `wait` seconds while the game is running (the window is briefly gone or
    hidden when D2R switches between its startup screens)."""
    t0 = time.time()
    while True:
        h = find_window()
        if h:
            return h
        if time.time() - t0 > wait or not game_pids():
            raise SystemExit(f"game window of slot {SLOT} not found" + (" (game not running)" if not game_pids() else ""))
        time.sleep(0.5)


# ---------------------------------------------------------------- screenshots


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


RESTORES = []  # one entry per restore_noactivate(): (window, foreground window before, foreground window after, handed back)
FG_GRACE_UNTIL = 0.0  # time.time() until which the game window may be the foreground window (game_checks' watchdog reads it)


def _give_back_focus(before, h):
    """Foreground back to `before` after the game window took it. A plain SetForegroundWindow is refused (returns 0: this process has no
    foreground right then); attaching this thread's input queue to the two windows' threads for the call makes it work. No input is sent."""
    me = ctypes.windll.kernel32.GetCurrentThreadId()
    t_game = user32.GetWindowThreadProcessId(h, None)
    t_before = user32.GetWindowThreadProcessId(before, None)
    user32.AttachThreadInput(me, t_game, True)
    user32.AttachThreadInput(me, t_before, True)
    try:
        user32.SetWindowPos(h, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        return bool(user32.SetForegroundWindow(before))
    finally:
        user32.AttachThreadInput(me, t_game, False)
        user32.AttachThreadInput(me, t_before, False)


def restore_noactivate(h, wait=3.0):
    """Foreground opt-in only: restore a minimized window with SW_SHOWNOACTIVATE, then send it to the bottom so it does
    not cover the user's windows (PrintWindow does not need it on top). D2R activates its window by itself when it is restored (as it
    does when it is created, see _keep_out_of_front); if the foreground window is the game window right after, the foreground goes back to
    the window that had it (only with MXL_INPUT=sendinput: background mode never calls SetForegroundWindow, so it cannot give the focus back). FG_GRACE_UNTIL tells the
    watchdog of game_checks to let those few milliseconds pass. Records (window, foreground before, foreground after, handed back) in
    RESTORES. Background mode refuses to restore. True when the window has a size afterwards."""
    global FG_GRACE_UNTIL
    if not user32.IsIconic(h):
        return True
    if BG:
        return False  # restoring can make D2R activate itself
    before = user32.GetForegroundWindow()
    FG_GRACE_UNTIL = time.time() + wait + 2.0
    user32.ShowWindow(h, 4)  # SW_SHOWNOACTIVATE
    user32.SetWindowPos(h, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_BOTTOM, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    t0 = time.time()
    handed = False
    while time.time() - t0 < wait:  # D2R takes the focus a moment after the restore: watch the whole time, not only until it has a size
        if not BG and before and before != h and user32.GetForegroundWindow() == h:
            handed = _give_back_focus(before, h) or handed
        time.sleep(0.01)
    time.sleep(0.5)  # the first frame after the restore
    if not BG and before and before != h and user32.GetForegroundWindow() == h:
        handed = _give_back_focus(before, h) or handed
        time.sleep(0.2)
    after = user32.GetForegroundWindow()
    RESTORES.append((h, before, after, handed))
    FG_GRACE_UNTIL = time.time() + 0.5
    log(f"window {h} was minimized: restored (foreground window {before} -> {after}, focus handed back: {handed})")
    return not user32.IsIconic(h)


def grab_printwindow(h):
    """Client area of window h via PrintWindow(PW_RENDERFULLCONTENT): works with the window behind others or on
    another monitor, needs no focus and never touches the desktop. A minimized window is refused.
    Returns an RGB PIL image."""
    from PIL import Image
    if user32.IsIconic(h):
        raise RuntimeError("game window is minimized: background capture will not restore it")
    gdi = ctypes.windll.gdi32
    wr = wt.RECT()
    user32.GetWindowRect(h, ctypes.byref(wr))
    W, H = wr.right - wr.left, wr.bottom - wr.top
    cr = wt.RECT()
    user32.GetClientRect(h, ctypes.byref(cr))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(pt))
    ox, oy = pt.x - wr.left, pt.y - wr.top
    if W <= 0 or H <= 0 or cr.right <= 0 or user32.IsIconic(h):
        raise RuntimeError("game window minimized or has no size: cannot capture")
    dc = user32.GetDC(h)
    mdc = gdi.CreateCompatibleDC(dc)
    bmp = gdi.CreateCompatibleBitmap(dc, W, H)
    gdi.SelectObject(mdc, bmp)
    try:
        user32.PrintWindow(h, mdc, 2)
        bi = _BITMAPINFOHEADER(40, W, -H, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(W * H * 4)
        gdi.GetDIBits(mdc, bmp, 0, H, buf, ctypes.byref(bi), 0)
    finally:
        gdi.DeleteObject(bmp)
        gdi.DeleteDC(mdc)
        user32.ReleaseDC(h, dc)
    img = Image.frombuffer("RGBA", (W, H), buf, "raw", "BGRA", 0, 1).convert("RGB")
    return img.crop((ox, oy, ox + cr.right, oy + cr.bottom))


def grab_client(h=None):
    """Client-area image of the game window (background: PrintWindow; foreground: desktop grab of the client rect)."""
    h = h or need_window()
    if BG:
        return grab_printwindow(h)
    from PIL import ImageGrab
    focus(h)
    l, t, r, b = client_rect(h)
    return ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)


def shot(name):
    h = need_window()
    img = grab_client(h)
    path = os.path.join(current_run(), name if name.lower().endswith(".png") else name + ".png")
    img.save(path)
    log(f"shot {os.path.basename(path)} {img.size}")
    return path


# ---------------------------------------------------------------- input (SendInput)

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE = 1, 2, 8

# name -> (scancode, extended)
SC = {"esc": (0x01, 0), "enter": (0x1C, 0), "tab": (0x0F, 0), "space": (0x39, 0), "backspace": (0x0E, 0),
      "ctrl": (0x1D, 0), "shift": (0x2A, 0), "alt": (0x38, 0), "`": (0x29, 0), "-": (0x0C, 0), "=": (0x0D, 0),
      "up": (0x48, 1), "down": (0x50, 1), "left": (0x4B, 1), "right": (0x4D, 1),
      ".": (0x34, 0), ",": (0x33, 0), "/": (0x35, 0), ";": (0x27, 0), "'": (0x28, 0)}
for i, c in enumerate("qwertyuiop"):
    SC[c] = (0x10 + i, 0)
for i, c in enumerate("asdfghjkl"):
    SC[c] = (0x1E + i, 0)
for i, c in enumerate("zxcvbnm"):
    SC[c] = (0x2C + i, 0)
for i, c in enumerate("1234567890"):
    SC[c] = (0x02 + i, 0)
for i in range(1, 11):
    SC[f"f{i}"] = (0x3A + i, 0)

SHIFT_CHARS = {"_": "-", "+": "="}


def _send_key(sc, ext, up):
    fl = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if ext else 0) | (KEYEVENTF_KEYUP if up else 0)
    i = INPUT(1, _U(ki=KEYBDINPUT(0, sc, fl, 0, 0)))
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


WM_KEYDOWN, WM_KEYUP, WM_CHAR, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x102, 0x104, 0x105
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP = 0x200, 0x201, 0x202, 0x204, 0x205

# name -> virtual key (background mode)
VK = {"esc": 0x1B, "enter": 0x0D, "tab": 0x09, "space": 0x20, "backspace": 0x08, "ctrl": 0x11, "shift": 0x10,
      "alt": 0x12, "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "`": 0xC0, "-": 0xBD, "=": 0xBB,
      ".": 0xBE, ",": 0xBC, "/": 0xBF, ";": 0xBA, "'": 0xDE}
for _i in range(1, 11):
    VK[f"f{_i}"] = 0x6F + _i
for _c in "abcdefghijklmnopqrstuvwxyz0123456789":
    VK[_c] = ord(_c.upper())


def _lparam(vk, ext, up, repeat=1):
    sc = user32.MapVirtualKeyW(vk, 0)
    lp = (repeat & 0xFFFF) | (sc << 16) | ((1 if ext else 0) << 24)
    if up:
        lp |= (1 << 30) | (1 << 31)
    return lp


def _post_key(hwnd, name, up, ext=0):
    vk = VK[name]
    user32.PostMessageW(hwnd, WM_KEYUP if up else WM_KEYDOWN, vk, _lparam(vk, ext, up))


def press_bg(key, hold=0.06, mods=(), char=None):
    """Key press as window messages (no global input). char: also post WM_CHAR (text fields)."""
    hwnd = need_window()
    key = key.lower() if len(key) > 1 or key.isalpha() else key
    ext = SC[key][1] if key in SC else 0
    _set_mods(mods)  # GetKeyState answers for the modifiers come from the plugin's virtual block (when it is on)
    for m in mods:
        _post_key(hwnd, m, False)
    time.sleep(0.03)
    _post_key(hwnd, key, False, ext)
    if char:
        user32.PostMessageW(hwnd, WM_CHAR, ord(char), _lparam(VK[key], ext, False))
    time.sleep(hold)
    _post_key(hwnd, key, True, ext)
    for m in reversed(mods):
        _post_key(hwnd, m, True)
    _set_mods(())
    time.sleep(0.15)


def press(key, hold=0.06, mods=(), char=None):
    if BG:
        return press_bg(key, hold, mods, char)
    key = key.lower() if len(key) > 1 or key.isalpha() else key
    sc, ext = SC[key]
    for m in mods:
        _send_key(SC[m][0], SC[m][1], 0)
    time.sleep(0.03)
    _send_key(sc, ext, 0)
    time.sleep(hold)
    _send_key(sc, ext, 1)
    for m in reversed(mods):
        _send_key(SC[m][0], SC[m][1], 1)
    time.sleep(0.15)


def key(*names, focus_first=True):
    if focus_first:
        focus(need_window())
    for n in names:
        if "+" in n and len(n) > 1:
            *mods, k = n.split("+")
            press(k, mods=[m.lower() for m in mods])
        else:
            press(n)


def type_text(s):
    for ch in s:
        if ch == " ":
            press("space", char=ch)
        elif ch.isupper():
            press(ch.lower(), mods=("shift",), char=ch)
        elif ch in SHIFT_CHARS:
            press(SHIFT_CHARS[ch], mods=("shift",), char=ch)
        else:
            press(ch, char=ch)


_VIN = None
_VIN_PID = None


def vinput():
    """The plugin's virtual input block ('Local\\mxl2012-testharness-input-<game PID>', one per game process,
    plugin/src/testharness.cpp) as an int32[8]:
    [magic, active, x, y, buttons, mods, seq, 0]. D2R reads the mouse position with GetCursorPos and the buttons and
    modifiers with GetKeyState; with the harness on the plugin answers those from this block, so the real cursor
    never has to move. None when the plugin's test harness is off (no mxl2012-testharness.txt next to mxl2012-core.dll)."""
    global _VIN, _VIN_PID
    pids = game_pids()
    if _VIN is not None and _VIN_PID not in pids:
        _VIN = None  # the game restarted: a new process with a new block
    if _VIN is None:
        if not pids:
            return None
        kernel32.OpenFileMappingW.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.restype = ctypes.c_void_p
        kernel32.MapViewOfFile.argtypes = [ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_size_t]
        hm = kernel32.OpenFileMappingW(0xF001F, False, f"Local\\mxl2012-testharness-input-{pids[0]}")
        if not hm:
            # plugins before the per-process block (0.46.0 as released) use one shared name: fine for a single instance
            hm = kernel32.OpenFileMappingW(0xF001F, False, "Local\\mxl2012-testharness-input")
        if not hm:
            return None
        p = kernel32.MapViewOfFile(ctypes.c_void_p(hm), 0xF001F, 0, 0, 576)
        if not p:
            return None
        _VIN_PID = pids[0]
        _VIN = (ctypes.c_int32 * 144).from_address(p)
        if _VIN[0] != 0x4d58:
            _VIN = None
        elif not _VIN[1]:
            _VIN[7] = 1  # D2R may not bring its own window to the front (SetForegroundWindow suppressed)
            _VIN[2], _VIN[3], _VIN[1] = 800, 450, 1  # from now on the real mouse and modifier keys are ignored by D2R
    return _VIN


def _set_mods(mods):
    v = vinput()
    if v is not None:
        bits = {"shift": 1, "ctrl": 2, "alt": 4}
        v[5] = sum(bits[m] for m in mods)


def click_bg(fx, fy, button="left", move_only=False):
    """Mouse without the real mouse: the virtual cursor in the plugin's input block (position and button state as
    D2R's GetCursorPos / GetKeyState see them) plus WM_MOUSEMOVE / WM_xBUTTON messages with client coordinates.
    Messages alone are ignored by D2R (it takes the position from GetCursorPos, not from lParam)."""
    h = need_window()
    cr = wt.RECT()
    user32.GetClientRect(h, ctypes.byref(cr))
    x, y = int(fx * cr.right), int(fy * cr.bottom)
    lp = lambda a, b: ((b & 0xFFFF) << 16) | (a & 0xFFFF)
    v = vinput()
    if v is None:
        raise SystemExit("background mouse needs the plugin test harness (mxl2012-testharness.txt next to mxl2012-core.dll, "
                         "plugin >= test-harness build); use --foreground otherwise")
    v[2], v[3], v[1] = x - 4, y - 4, 1  # D2R buttons ignore a click that arrives without a hover first
    user32.PostMessageW(h, WM_MOUSEMOVE, 0, lp(x - 4, y - 4))
    time.sleep(0.2)
    v[2], v[3] = x, y
    user32.PostMessageW(h, WM_MOUSEMOVE, 0, lp(x, y))
    time.sleep(0.4)
    if move_only:
        return
    down, up, bit, mk = (WM_LBUTTONDOWN, WM_LBUTTONUP, 1, 1) if button == "left" else (WM_RBUTTONDOWN, WM_RBUTTONUP, 2, 2)
    v[4] |= bit
    user32.PostMessageW(h, down, mk, lp(x, y))
    time.sleep(0.08)
    v[4] &= ~bit
    user32.PostMessageW(h, up, 0, lp(x, y))
    time.sleep(0.4)
    log(f"click(bg) {fx:.3f},{fy:.3f} -> client {x},{y} {button}")


def click(fx, fy, button="left", move_only=False):
    if BG:
        return click_bg(fx, fy, button, move_only)
    h = need_window()
    focus(h)
    l, t, r, b = client_rect(h)
    x = int(l + fx * (r - l))
    y = int(t + fy * (b - t))
    user32.SetCursorPos(x - 4, y - 4)  # D2R buttons ignore a click that arrives without a hover first
    time.sleep(0.2)
    user32.SetCursorPos(x, y)
    time.sleep(0.4)
    if move_only:
        return
    down, up = (0x0002, 0x0004) if button == "left" else (0x0008, 0x0010)
    user32.mouse_event(down, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(up, 0, 0, 0, 0)
    time.sleep(0.4)
    log(f"click {fx:.3f},{fy:.3f} -> screen {x},{y} {button}")


# ---------------------------------------------------------------- log handling


def _size(p):
    try:
        return os.path.getsize(p)
    except OSError:
        return 0


def _read_from(p, off):
    try:
        if _size(p) < off:
            off = 0  # log was rotated/truncated at launch
        with open(p, "rb") as f:
            f.seek(off)
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def wait_log(needle, timeout=90, off=0, since=None):
    """since: 'YYYY-MM-DD HH:MM:SS' local time; only lines stamped at or after it count (the loader log may still
    hold the previous run's lines for a moment after launch)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        for ln in _read_from(LOADER_LOG, off).splitlines():
            if needle in ln and (since is None or ln[1:20] >= since):
                return True
        time.sleep(1)
    return False


def snapshot_marks():
    s = load_state()
    s["marks"] = {"loader": _size(LOADER_LOG), "mxl": _size(MXL_LOG),
                  "crashes": sorted(os.listdir(CRASH_DIR)) if os.path.isdir(CRASH_DIR) else []}
    save_state(s)


def logscan(update=True):
    s = load_state()
    m = s.get("marks", {"loader": 0, "mxl": 0, "crashes": []})
    out = []
    new = _read_from(LOADER_LOG, m["loader"] if _size(LOADER_LOG) >= m["loader"] else 0)
    errs = [ln for ln in new.splitlines() if "ERROR" in ln or "ASSERT" in ln.upper() or "FATAL" in ln.upper()]
    out.append(f"d2rloader.log: {len(new.splitlines())} new lines, {len(errs)} ERROR/ASSERT lines")
    out += ["  " + e for e in errs[:40]]
    mx = _read_from(MXL_LOG, m["mxl"] if _size(MXL_LOG) >= m["mxl"] else 0)
    mlines = mx.splitlines()
    bad = [ln for ln in mlines if any(k in ln.lower() for k in ("error", "fail", "assert", "exception"))]
    out.append(f"mxl2012-core.log: {len(mlines)} new lines, {len(bad)} with error/fail/assert")
    out += ["  " + e[:240] for e in bad[:40]]
    for ln in mlines:
        if any(k in ln.lower() for k in ("loaded", "version", "installed", "on:", "functions")):
            out.append("  [summary] " + ln[:200])
            if len(out) > 120:
                break
    crashes = sorted(os.listdir(CRASH_DIR)) if os.path.isdir(CRASH_DIR) else []
    newc = [c for c in crashes if c not in m.get("crashes", [])]
    out.append(f"crash files: {len(newc)} new {newc}")
    text = "\n".join(out)
    open(os.path.join(current_run(), "logscan.txt"), "w", encoding="utf-8").write(text)
    print(text)
    return {"errors": errs, "bad": bad, "crashes": newc, "text": text}


# ---------------------------------------------------------------- start / stop / console


def _keep_out_of_front(prev_fg, wait=60):
    """D2R activates its window as soon as it is created, whatever the launch flags. Right after it appears,
    send it to the bottom of the z-order (no activation) and hand the foreground back to the window that had it
    before the launch. The hand-back is the old behaviour and only runs with MXL_INPUT=sendinput (not BG): the default
    background path never calls SetForegroundWindow, it only sends the window to the bottom without activating it."""
    t0 = time.time()
    while time.time() - t0 < wait:
        h = find_window()
        if h:
            user32.SetWindowPos(h, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_BOTTOM, NOSIZE|NOMOVE|NOACTIVATE
            if not BG and prev_fg and user32.GetForegroundWindow() == h:
                user32.SetForegroundWindow(prev_fg)
            log(f"game window {h} sent to the back" + ("" if BG else f", foreground given back to {prev_fg}"))
            return True
        time.sleep(0.05)
    return False


def take_lock():
    """Slot run lock (game.lock.N). A lock somebody made by hand (mkdir, no owner.txt) is
    taken to mean the caller holds it (the older lanes do that before running game_ctl); a lock owned by another
    run stops the launch."""
    ok, msg = game_slots.acquire(SLOT, LOCK_OWNER)
    if not ok and msg.endswith("(no owner.txt)"):
        log(f"slot {SLOT}: {msg}; assuming the caller holds it")
        return True
    log(f"slot {SLOT}: {msg}")
    return ok


def start(timeout=120):
    foreign = game_slots.foreign_game(SLOT, LOCK_OWNER)
    if foreign:  # slot 1: the owner's own game (or another mod's run) is never attached to
        log(f"slot {SLOT}: a game this run did not start is running {foreign}: refused (never attached, closed or killed)")
        return False
    if game_pids():
        log(f"game already running (slot {SLOT})")
    else:
        if not take_lock():
            return False
        try:
            log(slot_share.begin(SLOT, LOCK_OWNER, GAME_DIR))
        except SystemExit as e:
            log(f"slot {SLOT}: {e}")
            game_slots.release(SLOT, LOCK_OWNER)
            return False
        snapshot_marks()
        off = _size(LOADER_LOG)
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        prev_fg = None if BG else user32.GetForegroundWindow()  # only the sendinput path hands focus back
        harness_switch(BG)  # background mode needs the plugin test harness; foreground runs keep it off
        si = subprocess.STARTUPINFO()
        if BG:
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 4  # SW_SHOWNOACTIVATE: do not start minimized, since restoring may activate D2R
        args = slot_share.launch_args(SLOT, GAME_DIR)
        try:
            proc = subprocess.Popen([LOADER] + args, cwd=GAME_DIR, startupinfo=si)
        except OSError as e:
            log(f"launch failed: {e}")
            restore_shared()
            return False
        if SLOT in game_slots.OWNER_SLOTS:  # slot 1: only a game with this marker is ours to touch
            game_slots.mark_launch(SLOT, LOCK_OWNER, proc.pid)
        log("launched D2RLoader " + " ".join(args))
        if BG:
            _keep_out_of_front(prev_fg)
        if not wait_log("D2R startup complete.", timeout, off, since):
            log("TIMEOUT waiting for startup line")
            return False
    t0 = time.time()
    h = None
    while time.time() - t0 < 60 and not h:
        h = find_window()
        time.sleep(1)
    if not h:
        log("no game window")
        return False
    r = fit_window(h)
    focus(h)
    log(f"window ready client rect {r}")
    time.sleep(3)
    return True


def restore_shared():
    """Put the slot's shared D2RLoader files back (tools/slot_share.py). True when restored or nothing was pending."""
    try:
        log(slot_share.end(SLOT, LOCK_OWNER, GAME_DIR))
        return True
    except SystemExit as e:
        log(f"slot {SLOT}: SHARED FILES NOT RESTORED: {e}; the lock stays (py -3 tools/slot_share.py restore {SLOT})")
        return False


def stop(timeout=20):
    foreign = game_slots.foreign_game(SLOT, LOCK_OWNER)
    if foreign:  # slot 1: not ours (the owner playing): never closed or killed, the lock stays as it is
        log(f"slot {SLOT}: a game this run did not start is running {foreign}: not closed")
        return
    pids = game_pids()
    if not pids:
        harness_switch(False)  # also when the game already ended: normal play never runs with the harness on
        log("not running")
        if not game_slots.slot_processes(GAME_DIR):
            game_slots.clear_launch(SLOT)
        if restore_shared():
            game_slots.release(SLOT, LOCK_OWNER)
        return
    h = find_window()
    if h:
        user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE == CloseMainWindow
    t0 = time.time()
    while time.time() - t0 < timeout and game_pids():
        time.sleep(1)
    if game_pids():
        log("forcing kill")
        for p in game_pids():
            subprocess.run(["taskkill", "/F", "/PID", str(p)], capture_output=True)
        time.sleep(2)
    # D2R may leave a child process named D2R.exe; only the ones in this slot's folder (other slots run their own)
    for pid, nm in game_slots.slot_processes(GAME_DIR):
        log(f"{nm} {pid} still alive, killing")
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    harness_switch(False)  # normal play never runs with the harness on
    time.sleep(1)  # the loader's last config writes
    if not game_slots.slot_processes(GAME_DIR):
        game_slots.clear_launch(SLOT)
    if restore_shared():
        game_slots.release(SLOT, LOCK_OWNER)
    log("stopped")


def harness_switch(on: bool) -> None:
    """Create or remove mxl2012-testharness.txt next to mxl2012-core.dll (the plugin test harness reads it at load). Its text
    is a list of words: `volserial` (slots 2 to 5: D2RLoader derives the key of the Battle.net session
    cookie from the volume serial of the drive it runs from and dies on another drive, see docs/testing.md; the plugin
    then reports the serial of C:, the same for every slot, so the word has no per-slot value),
    `tag=sN` (distinct per slot: window title "Diablo II: Resurrected [s2]", so other tools never pick this window), `nocookie` (hide
    the cookie instead) and `diag` (env MXL_HARNESS_WORDS sets the words by hand, e.g. "volserial tag=s2 diag").
    Env MXL_CONTROL ("afford hcdeath") also writes those words to mxl2012-core-off.txt: a control run with those parts left out."""
    folder = os.path.join(GAME_DIR, "mods", "mxl2012", "d2rloader", "plugins")
    p = os.path.join(folder, "mxl2012-testharness.txt")
    off = os.path.join(folder, "mxl2012-core-off.txt")
    try:
        if on:
            words = os.environ.get("MXL_HARNESS_WORDS")  # explicit override, e.g. "diag" for investigations
            if words is None:  # slot 1 runs from the drive its Battle.net session was made on: no volserial fix
                words = f"tag=s{SLOT}" if SLOT in game_slots.OWNER_SLOTS else f"volserial tag=s{SLOT}"
            open(p, "w").write(words)
            # control runs: MXL_CONTROL="afford hcdeath" writes mxl2012-core-off.txt for this launch (removed again with the harness)
            control = os.environ.get("MXL_CONTROL")
            if control:
                open(off, "w").write(control)
        else:
            for q in (p, off) if os.environ.get("MXL_CONTROL") else (p,):  # a hand-made off file stays
                if os.path.exists(q):
                    os.remove(q)
    except OSError as e:
        log(f"harness switch {'on' if on else 'off'} failed: {e}")


def console_bg(cmd, timeout=10):
    """Run a developer-console line through the plugin (D2RCore's ExecuteConsoleCommand on the game's UI thread).
    D2R takes no Ctrl+` from posted messages, so the panel is never opened: the command runs, its output is only
    visible when the panel is open (it stays closed here). Returns True when the console handled the line."""
    v = vinput()
    if v is None:
        raise SystemExit("background console needs the plugin test harness (mxl2012-testharness.txt next to mxl2012-core.dll)")
    data = cmd.encode("utf-8")[:500] + b"\0"
    ctypes.memmove(ctypes.addressof(v) + 64, data, len(data))
    seq = (v[8] + 1) & 0x7FFFFFFF
    v[8] = seq
    t0 = time.time()
    while time.time() - t0 < timeout:
        if v[9] == seq:
            log(f"console(bg) {cmd!r} -> {v[10]}")
            return v[10] == 1
        time.sleep(0.05)
    log(f"console(bg) {cmd!r} -> no answer in {timeout}s (not in the game window thread's message loop?)")
    return False


HARNESS_CONSOLE = os.path.join(GAME_DIR, r"mods\mxl2012\d2rloader\plugins\mxl2012-testharness-console.txt")


def console_text(cmd, settle=0.6):
    """console_bg() plus the lines the plugin's own `mxl2012` command printed for it (the plugin appends them to
    mxl2012-testharness-console.txt). Output of D2R / D2RLoader commands (cheats, help) is not captured: it only goes to
    the console panel, which cannot be opened without Ctrl+`."""
    mark = _size(HARNESS_CONSOLE)
    console_bg(cmd)
    time.sleep(settle)
    text = _read_from(HARNESS_CONSOLE, mark)
    if text:
        log(f"console(bg) output of {cmd!r}:\n" + text.rstrip())
    return text


def hcmd(cmd, timeout=15):
    """Run one plugin test-harness gameplay command (plugin/src/harness_cmds.cpp, docs/testing.md "Harness commands"):
    `hcmd("kill nearest 156")`. The plugin calls the game's own functions (no mouse or keyboard), appends "h: ..."
    lines to mxl2012-testharness-console.txt and ends with "h: <verb> OK" or "h: <verb> FAIL <reason>".
    Returns (ok, lines): ok is True for an OK last line, lines are the "h: " lines with the prefix removed."""
    mark = _size(HARNESS_CONSOLE)
    console_bg("h " + cmd, timeout)
    verb = cmd.split()[0]
    lines = []
    t0 = time.time()
    while time.time() - t0 < timeout:  # server-side verbs finish on the game thread's next frame
        text = _read_from(HARNESS_CONSOLE, mark) or ""
        lines = [ln[3:] for ln in text.splitlines() if ln.startswith("h: ")]
        if lines and (lines[-1].startswith(verb + " OK") or lines[-1].startswith(verb + " FAIL")):
            break
        time.sleep(0.1)
    else:
        lines.append(f"{verb} FAIL no answer in {timeout} s (not in a game?)")
    ok = bool(lines) and lines[-1].startswith(verb + " OK")
    log(f"hcmd {cmd!r} -> {'OK' if ok else 'FAIL'}: " + " | ".join(lines)[:400])
    return ok, lines


def console(cmd):
    if BG:
        return console_text(cmd)
    focus(need_window())
    press("`", mods=("ctrl",))
    time.sleep(0.5)
    type_text(cmd)
    press("enter")
    time.sleep(0.6)
    press("`", mods=("ctrl",))


# ---------------------------------------------------------------- smoke scenario

# Fractional click targets (fx, fy) of the 1600x900 client rect. "seen" ones were measured from screenshots;
# "guess" ones are untested (the 2026-10-21 run was blocked by D2R's 30-day online license check before the menu).
UI = {  # fractions of the 1600 x 900 client rect, measured 2026-10-21
    "calib_continue": (0.500, 0.838),   # Gamma / Screen Space / Color Blind calibration screens
    "license_ok": (0.498, 0.537),       # "not been online in the last 30 days" dialog (OK quits the game)
    "menu_play": (0.394, 0.897),        # main menu Play (plays the selected character)
    "char_create": (0.895, 0.867),      # main menu Create New
    "barb_class": (0.450, 0.480),       # hero select: the Barbarian
    "name_box": (0.500, 0.830),         # hero select: Character Name
    "create_ok": (0.893, 0.930),        # hero select: Create (enters the game, Normal)
    "save_exit": (0.500, 0.440),        # Esc menu: Save and Exit
    "skill_tab0": (0.683, 0.190),       # skill tree: first of 8 tabs
    "skill_tab_dx": 0.0259,             # skill tree: tab spacing
}


UI["difficulty_normal"] = (0.500, 0.421)  # "Select Difficulty" dialog after Play (shown when the character has more than one)


def play_selected():
    """Play the selected character; answer the difficulty dialog with Normal (a click on empty menu scenery when
    the dialog is not there)."""
    click(*UI["menu_play"])
    time.sleep(1.5)
    click(*UI["difficulty_normal"])


def in_game() -> bool:
    """The red life orb (bottom left of the HUD) is on screen, or else the plugin harness answers `h state` (it fails
    outside a game). The orb test alone misses a character with almost no life: the sampled upper part is empty."""
    from PIL import ImageStat
    img = grab_client()
    w, h = img.size
    box = (int(.235 * w), int(.87 * h), int(.265 * w), int(.92 * h))
    rr, gg, bb = ImageStat.Stat(img.crop(box).convert("RGB")).mean
    if rr > 90 and rr > 2 * gg and rr > 2 * bb:
        return True
    if BG and vinput() is not None:
        return hcmd("state", timeout=3)[0]
    return False


class Report:
    def __init__(self):
        self.rows = []

    def add(self, step, ok, shots, note=""):
        self.rows.append((step, ok, shots, note))
        log(f"STEP {step}: {'PASS' if ok else 'FAIL'} {note}")

    def write(self, extra=""):
        p = os.path.join(current_run(), "report.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(f"# Smoke run {os.path.basename(current_run())}\n\n")
            f.write("| Step | Result | Screenshots | Note |\n|---|---|---|---|\n")
            for step, ok, shots, note in self.rows:
                f.write(f"| {step} | {'PASS' if ok else 'FAIL'} | {', '.join(shots)} | {note} |\n")
            f.write("\n" + extra + "\n")
        log(f"report {p}")


# Signature of the main menu: the left button panel (Options / Cinematics / Credits / Exit; fixed art, the scene behind
# the panel changes) as 12 x 16 grey cells. The menu matches with a mean difference of 0; dimmed behind a dialog it is
# about 27, the in-game screens 25 or more. The calibration screens' Continue button is NOT a menu feature: the scenery
# in that box is bright too.
MENU_SIG = bytes.fromhex(
    "192e2f35373b3d37332e2c152137465a6f6f69615847361d1d2c30385753564f"
    "3a2f2e19152523272a292828252522131b3030373a3f3f3a36302d151f37465d"
    "676e68605746361c1b2c2e3f4f5c4c4e432e2e18142221242626262522241f12"
    "1b343741444b4a43403731161f384153666b665e5141381b1a292d35474f4543"
    "362d2b17142222242625252422231e121930343e414645403c352e141f384855"
    "676e635d5545381b1b293d443d4f534e41342c17142221242625252422231f11")


def menu_visible() -> bool:
    """The main menu is up and no dialog dims it."""
    from PIL import Image
    img = grab_client()
    w, h = img.size
    c = img.crop((int(.0375 * w), int(.372 * h), int(.172 * w), int(.633 * h))).convert("L").resize((12, 16), Image.BOX)
    return sum(abs(a - b) for a, b in zip(c.tobytes(), MENU_SIG)) / len(MENU_SIG) < 8


def clear_intro(timeout=120):
    """Calibration screens (first launches), skippable intro cinematics (hold a key), title screen. Done when the main
    menu is recognised (menu_visible); Continue is clicked at most 6 times and Esc held at most 4 times, so a bright
    menu scene cannot make this loop. Returns False if the game quit (license check dialog: OK closes the game)."""
    from PIL import ImageStat

    def button_visible():
        img = grab_client()
        w, h = img.size
        box = (int(.45 * w), int(.82 * h), int(.55 * w), int(.86 * h))
        return ImageStat.Stat(img.crop(box).convert("L")).mean[0] > 50

    t0 = time.time()
    clicks = escs = 0
    last_esc = 0.0
    while time.time() - t0 < timeout:
        if not game_pids():
            return False
        if menu_visible():
            time.sleep(1)
            if menu_visible():  # stable for a second: not a frame of the intro
                shot("intro_end")
                return True
        elif button_visible() and clicks < 6:
            click(*UI["calib_continue"])
            clicks += 1
            time.sleep(3)
            continue
        elif escs < 4 and time.time() - last_esc > 12 and time.time() - t0 > 20:
            press("esc", hold=3)  # "Hold any button to skip"
            escs += 1
            last_esc = time.time()
        time.sleep(1)
    shot("intro_end")
    if not game_pids():
        return False
    # Blizzard license dialog: only OK, which quits. Detect by clicking it and seeing whether the game exits.
    click(*UI["license_ok"])
    time.sleep(6)
    return bool(game_pids())


def step_shot(rep, step, name, key_name=None, wait=1.5):
    if key_name:
        key(key_name)
    time.sleep(wait)
    p = shot(name)
    rep.add(step, True, [os.path.basename(p)], "screenshot taken, review by eye")


def main():
    # stdout may be a file opened by parallel_smoke.py (or a cp932 console); log text can hold characters cp932 cannot
    # encode, and a print() that raises here must not cost the run its report
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    game_slots.require_machine(f"game_ctl {a[0]}")
    game_slots.require_present(SLOT, "game_ctl", GAME_DIR)  # e.g. slot 4 or 5 before its folder was copied
    c = a[0]
    if c == "start":
        current_run(create=True)
        sys.exit(0 if start() else 1)
    elif c == "shot":
        shot(a[1])
    elif c == "key":
        key(*a[1:])
    elif c == "click":
        click(float(a[1]), float(a[2]), a[3] if len(a) > 3 else "left")
    elif c == "console":
        console(" ".join(a[1:]))
    elif c == "stop":
        stop()
    elif c == "harness":  # by hand, for a game this script does not start (the launcher's, docs/launcher.md "Testing")
        harness_switch(a[1:2] == ["on"])
    elif c == "logscan":
        logscan()
    elif c == "smoke":
        run_smoke()
    else:
        print(__doc__)


def run_smoke():
    current_run(create=True)
    rep = Report()
    try:
        ok = start()
        rep.add("1a start (log line + window)", ok, [])
        if not ok:
            return
        if not clear_intro():
            rep.add("1b main menu reached", False, ["intro_end.png"],
                    "BLOCKED: D2R shows 'You have not been online in the last 30 days. Please start the game while "
                    "online to verify the product license.' and OK quits the game. Needs one online launch "
                    "(Battle.net) by the user; not attempted by this script.")
            return
        rep.add("1b main menu reached", True, [os.path.basename(shot("menu"))])
        time.sleep(2)
        click(0.62, 0.40)  # warm-up on empty scenery: the menu swallows its first click
        time.sleep(1)
        if os.path.exists(os.path.join(SAVES, CHAR_NAME + ".d2s")):
            play_selected()  # the character exists and is selected
        else:
            click(*UI["char_create"]); time.sleep(3)
            click(*UI["barb_class"]); time.sleep(2)
            click(*UI["name_box"]); type_text(CHAR_NAME); time.sleep(1)
            shot("create")
            click(*UI["create_ok"])
        time.sleep(16)
        if not in_game() and os.path.exists(os.path.join(SAVES, CHAR_NAME + ".d2s")):
            play_selected(); time.sleep(16)  # retry once
        ok = in_game()
        rep.add("2 enter game", ok, [os.path.basename(shot("town"))], "" if ok else "life orb not found: not in game")
        if not ok:
            return
        if BG:  # the console panel cannot be opened without Ctrl+`: the plugin runs the line and records mxl's output
            txt = console_text("mxl2012")
            rep.add("3a console command mxl (plugin harness)", "mxl2012-core" in txt, [], txt.splitlines()[0][:100] if txt else "no output")
        step_shot(rep, "3b character sheet (C)", "charsheet", "c")
        key("esc"); time.sleep(0.8)
        step_shot(rep, "3c skill tree (T)", "skilltree", "t")
        x0, y0 = UI["skill_tab0"]
        for i in range(8):
            click(x0 + UI["skill_tab_dx"] * i, y0)
            step_shot(rep, f"3d skill tab {i + 1}", f"skilltab{i + 1}", wait=1.0)
        key("esc"); time.sleep(0.8)
        step_shot(rep, "3e inventory (I)", "inventory", "i")
        key("esc"); time.sleep(0.8)
        key("esc"); time.sleep(1.5)
        shot("escmenu")
        click(*UI["save_exit"]); time.sleep(8)
        saved = os.path.exists(os.path.join(SAVES, CHAR_NAME + ".d2s")) and not in_game()
        rep.add("4a save and exit", saved, [os.path.basename(shot("charselect2"))])
        play_selected(); time.sleep(16)
        ok = in_game()
        rep.add("4b reload", ok, [os.path.basename(shot("town_reload"))], "" if ok else "life orb not found")
        if ok:
            step_shot(rep, "4c inventory after reload", "inventory_reload", "i")
            key("esc"); time.sleep(0.8)
            key("esc"); time.sleep(1.5)
            click(*UI["save_exit"]); time.sleep(8)
    finally:
        # every step below is guarded: the report is written whatever happened above
        try:
            stop()
        except Exception as e:
            log(f"stop failed: {e!r}")
        try:
            extra = "## logscan\n\n```\n" + logscan()["text"] + "\n```"
        except Exception as e:
            log(f"logscan failed: {e!r}")
            extra = f"## logscan\n\nlogscan failed: {e!r}"
        rep.write(extra)


if __name__ == "__main__":
    main()
