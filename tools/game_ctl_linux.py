"""game_ctl's window layer on Linux: the game runs under Proton in a slot's own prefix, on a private X display
(lane linctl, 2026-11-20).

tools/game_ctl.py calls `install(globals())` when game_slots runs its Linux backend. That swaps game_ctl's Windows window
functions (ctypes user32/kernel32) for the ones below; every other function of game_ctl (the smoke scenario, logs,
harness file, hcmd) is the same code on both systems, and the Windows functions themselves are not changed. Slot folder,
prefix, Proton launch, Linux pids and the prefix stop come from game_slots' Linux backend (lane linslots).

- **Private display.** Owner rule (2026-11-20): test games never take focus or come to the front on the owner's
  desktop. On the desktop they did, whatever the prefix's Wine settings (lanes linslots, wineinput). So `start` runs
  each game on its own Xvfb display (linux_window.PrivateDisplay) with linux_window.PRIVATE_ENV (Mesa's CPU-copy present,
  vkd3d-proton without present_wait); the display and its Xvfb pid are kept in the run's state.json, so later
  `game_ctl` commands use the same display, and `stop` ends that Xvfb. A run never uses the owner's display.
- **Owner focus watch.** `start` polls the owner's `_NET_ACTIVE_WINDOW` (game_slots.FocusWatch on linux_window.
  OWNER_DISPLAY); `stop` (or the end of the process) writes focus.json to the run folder and logs the summary. A grab is
  logged as FOCUS STOLEN.
- **Windows, keys, mouse, notice, close** go through the wctl helper inside the slot's prefix (same wineserver as the
  game), so window handles and process ids are Wine's (Windows pids). `game_pids()` returns those Windows pids; it asks
  Wine only when /proc shows the slot's loader running (a stopped slot never gets a wineserver from us). Nothing
  activates, raises or focuses a window: the helper's SetWindowPos always has SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS and only
  HWND_BOTTOM as a z-order change, the notice is answered by a posted TDM_CLICK_BUTTON, the game closed by a posted
  WM_CLOSE.
- **Screenshots** come from the private display only: the game window's own pixmap (XComposite), else that display's
  root cut to the client rect. PrintWindow is black under Wine.

Background input only: `--foreground` / MXL_INPUT=sendinput is refused on Linux."""
import atexit
import json
import ntpath
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402
import linux_window  # noqa: E402
import loader_notice  # noqa: E402

FG_REFUSED = ("foreground input (--foreground / MXL_INPUT=sendinput) is Windows only: on Linux game_ctl posts window "
              "messages to the game and never moves the cursor or takes the focus")
WM_CLOSE = 0x0010
SWP_BOTTOM_QUIET = 0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
SCREEN = os.environ.get("MXL_XVFB_SCREEN", "1920x1080")  # the private display's least size (screen_size() grows it)
FRAME_MARGIN = (64, 96)  # room for Wine's window frame and caption around the client (measured: 12 x 38 at 1600 x 900)

M = None      # game_ctl's module namespace (set by install)
ENV = None    # linux_window.SlotEnv of the slot
_HELPER = None
_VIN = None
_VIN_PID = None
_SC = {}      # virtual key -> scan code (MapVirtualKeyW answers, asked once)
_FOCUS = None  # game_slots.FocusWatch on the owner's display (this process)
_DISPLAY = None  # the run's private display (":N") once known
_NOTICE_SEEN = set()  # D2RLoader dialogs already logged


class _View:
    """Attribute view of a module's globals dict (M.log(...), M.SLOT); assignments write the dict."""

    def __init__(self, ns):
        object.__setattr__(self, "_ns", ns)

    def __getattr__(self, k):
        try:
            return self._ns[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self._ns[k] = v


OVERRIDES = ("game_pids", "find_window", "client_rect", "focus", "fit_window", "restore_noactivate", "grab_printwindow",
             "grab_client", "_send_key", "_lparam", "_post_key", "press_bg", "press", "vinput", "click_bg", "wheel_bg",
             "click", "console_bg", "_keep_out_of_front", "start", "stop", "post_message")


def install(ns, env=None):
    """Point game_ctl (its globals dict `ns`) at the Linux window layer. Nothing is started or read here."""
    global M, ENV, _HELPER, _VIN, _VIN_PID, _FOCUS, _DISPLAY
    M, ENV = _View(ns), env or linux_window.slot_env(ns["SLOT"])
    _HELPER, _VIN, _VIN_PID, _FOCUS, _DISPLAY = None, None, None, None, None
    _SC.clear()
    _NOTICE_SEEN.clear()
    live_logs(ns)
    gd = ns["GAME_DIR"]
    ns["SAVES"] = os.path.join(game_slots.save_root(ns["SLOT"]),
                               os.path.basename(ns["SAVES"].replace("\\", "/").rstrip("/")))
    g = globals()
    for name in OVERRIDES:
        ns[name] = g[name]


# ---------------------------------------------------------------- harness words
# game_ctl's own harness_switch writes the words unchanged on Linux too. Lane linharness added `nofakefocus` here because
# the plugin's fake focus (then on by default under Wine) hung startup on Xvfb; since lane linfix the plugin keeps fake
# focus off unless the word `fakefocus` is given, so nothing is added any more.


# ---------------------------------------------------------------- slot logs (the whole-slot restore removes them)

LOG_NAMES = {"LOADER_LOG": ("d2rloader", "logs", "d2rloader.log"),
             "MXL_LOG": ("mods", "mxl2012", "d2rloader", "logs", "mxl2012-core.log"),
             "CRASH_DIR": ("d2rloader", "crashes"),
             "HARNESS_CONSOLE": ("mods", "mxl2012", "d2rloader", "plugins", "mxl2012-testharness-console.txt")}
# what keep_logs copies out of the slot before the restore (relative to the game folder; globs)
KEEP_GLOBS = ("d2rloader/logs/*", "d2rloader/crashes/*", "d2rloader_crashes/*", "mods/mxl2012/d2rloader/logs/*",
              "mods/mxl2012/d2rloader/plugins/*.log", "mods/mxl2012/d2rloader/plugins/*-console.txt", "blz-log.txt")


def live_logs(ns=None, root=None):
    """Point game_ctl's log paths (LOG_NAMES) at the slot's live files, or at the copies under `root`."""
    ns = ns if ns is not None else M._ns
    base = root or ns["GAME_DIR"]
    for k, rel in LOG_NAMES.items():
        ns[k] = os.path.join(base, *rel)


def keep_logs(run=None):
    """Copy the slot's run logs (KEEP_GLOBS) to <run>/slot-logs-<n>/ before slot_share.end restores the whole slot (which
    deletes them: they were not in the snapshot), then point game_ctl's log paths at the copies, so logscan, console_text
    and the report read what the run wrote. start() points them back at the live files. Returns the folder."""
    import glob
    import shutil
    run = run or M.current_run()
    n = 1
    while os.path.exists(os.path.join(run, f"slot-logs-{n}")):
        n += 1
    dest = os.path.join(run, f"slot-logs-{n}")
    gd = M.GAME_DIR
    copied = 0
    for pat in KEEP_GLOBS:
        for src in glob.glob(os.path.join(gd, pat)):
            if os.path.isfile(src):
                to = os.path.join(dest, os.path.relpath(src, gd))
                os.makedirs(os.path.dirname(to), exist_ok=True)
                shutil.copy2(src, to)
                copied += 1
    os.makedirs(dest, exist_ok=True)
    live_logs(M._ns, dest)
    M.log(f"slot logs kept: {copied} files in {dest}")
    return dest


# ---------------------------------------------------------------- private display


def display():
    """The run's private display (":N"): this process's, else the one `start` recorded in state.json while its Xvfb
    still runs. None when there is none (then no helper and no capture: the owner's display is never used)."""
    global _DISPLAY
    if _DISPLAY is None:
        st = M.load_state()
        d, pid = st.get("xvfb_display"), st.get("xvfb_pid")
        if d and linux_window.is_private(d) and linux_window.xvfb_alive(pid, d):
            _DISPLAY = d
    return _DISPLAY


def game_env():
    """What the game and the helper get on top of the slot's Wine environment: the private display + PRIVATE_ENV."""
    d = display()
    if not d:
        raise SystemExit(f"slot {M.SLOT}: no private display for this run (start the game with game_ctl start; the "
                         "owner's display is never used)")
    return dict(linux_window.PRIVATE_ENV, DISPLAY=d)


def display_start():
    """Start the run's Xvfb (its log in the run folder) and record it in state.json."""
    global _DISPLAY
    w, h = screen_size()
    d, pid = linux_window.PrivateDisplay.start(f"{w}x{h}", log_path=os.path.join(M.current_run(), "xvfb.log"))
    st = M.load_state()
    st.update(xvfb_display=d, xvfb_pid=pid, xvfb_screen=[w, h])
    M.save_state(st)
    _DISPLAY = d
    M.log(f"private display {d} (Xvfb pid {pid}, {w}x{h}); game env {linux_window.PRIVATE_ENV}")
    return d


def display_stop():
    """End the run's Xvfb (only the one recorded for this run, checked by its command line)."""
    global _DISPLAY
    st = M.load_state()
    d, pid = st.get("xvfb_display"), st.get("xvfb_pid")
    if d:
        gone = linux_window.PrivateDisplay.stop(pid, d)
        M.log(f"private display {d}: {'ended' if gone else 'STILL RUNNING (pid ' + str(pid) + ')'}")
        if gone:
            st.pop("xvfb_display", None)
            st.pop("xvfb_pid", None)
            M.save_state(st)
    _DISPLAY = None


# ---------------------------------------------------------------- owner focus watch


def focus_watch_start():
    """Poll the owner's _NET_ACTIVE_WINDOW from before the launch (game_slots.FocusWatch on the owner's display)."""
    global _FOCUS
    _FOCUS = game_slots.FocusWatch(M.SLOT, display=linux_window.OWNER_DISPLAY).start()
    M.log(f"owner focus watch on {linux_window.OWNER_DISPLAY}: active window before launch "
          f"{'none' if _FOCUS.before is None else hex(_FOCUS.before)}")
    atexit.register(focus_watch_stop)
    return _FOCUS


def focus_grabs():
    return list(_FOCUS.grabs) if _FOCUS is not None else []


def focus_watch_stop():
    """Stop the watch, write focus.json (run folder) and log the summary; None when no watch runs."""
    global _FOCUS
    if _FOCUS is None:
        return None
    w, _FOCUS = _FOCUS, None
    summary = w.stop()
    rep = {"display": linux_window.OWNER_DISPLAY, "before": w.before, "polls": w.polls, "changes": w.changes,
           "grabs": w.grabs, "summary": summary}
    with open(os.path.join(M.current_run(), "focus.json"), "w") as f:
        json.dump(rep, f, indent=1)
    M.log(("FOCUS STOLEN: " if w.grabs else "owner focus: ") + summary)
    return rep


# ---------------------------------------------------------------- helper


def helper():
    """The slot's wctl helper on the run's private display (started on first use; requests go to the run log)."""
    global _HELPER
    if _HELPER is None:
        _HELPER = linux_window.Helper(ENV, log=M.log, stderr_path=os.path.join(M.current_run(), "wctl-stderr.log"),
                                      extra_env=game_env())
    return _HELPER


def close_helper():
    """End the helper (it keeps the prefix's wineserver busy: close it before waiting for the prefix to go idle)."""
    global _VIN, _VIN_PID, _HELPER
    _VIN, _VIN_PID = None, None
    if _HELPER is not None:
        _HELPER.close()
        _HELPER = None


# ---------------------------------------------------------------- processes / windows


def _in_slot(win_image):
    u = ENV.unix_path(win_image)
    return bool(u) and game_slots.under(u, M.GAME_DIR)


def game_pids():
    """Windows pids (Wine's) of this slot's loader: its image lives in the slot's folder (a drive of the slot's prefix).
    [] when /proc shows no loader of the slot (game_slots.game_pids; Wine is not asked then)."""
    if not game_slots.game_pids(M.SLOT, (M.LOADER_NAME.lower(),)):
        return []
    want = M.LOADER_NAME.lower()
    return [pid for pid, img in helper().procs() if ntpath.basename(img).lower() == want and _in_slot(img)]


def find_window():
    """HWND (Wine's) of the slot's game window: visible, titled TITLE or "TITLE [sN]", owned by the slot's loader."""
    for pid in game_pids():
        r = helper().find(M.TITLE, pid)
        if r:
            return r[0]
    return None


def client_rect(h):
    r = helper().rect(h)
    return r["cx"], r["cy"], r["cx"] + r["cw"], r["cy"] + r["ch"]


def focus(h):
    if M.BG:
        return
    raise SystemExit(FG_REFUSED)


def screen_size(client_w=None, client_h=None, screen=None):
    """(w, h) of the run's private display: MXL_XVFB_SCREEN (1920x1080), grown so a client_w x client_h client and its
    window frame fit (default CLIENT_W x CLIENT_H; MXL_CLIENT=2560x1440 gets a 2624x1536 screen)."""
    sw, sh = (int(v) for v in (screen or SCREEN).lower().split("x"))
    cw = M.CLIENT_W if client_w is None else client_w
    ch = M.CLIENT_H if client_h is None else client_h
    return max(sw, cw + FRAME_MARGIN[0]), max(sh, ch + FRAME_MARGIN[1])


def offscreen(window, screen):
    """Pixels of `window` (l, t, r, b; Wine's screen coordinates are the X root's on the private display: one screen, no
    window manager) that lie outside the screen (w, h), as (right, bottom); (0, 0) when it fits. What lies outside is
    never drawn: lane linharness's slot 5 shots lost 26 x 72 px (1574 x 828 of 1600 x 900) at the cascade spot 340, 220."""
    l, t, r, b = window
    w, h = screen
    return max(0, r - w) + max(0, -l), max(0, b - h) + max(0, -t)


def fit_window(h, x=None, y=None):
    """Client area CLIENT_W x CLIENT_H with the window's top left at (x, y), SWP_NOZORDER | SWP_NOACTIVATE. On Linux each run
    has its own private display, so there is no slot cascade as on Windows: the window goes to 0, 0 (lane linfix). The
    window must lie inside the private screen; when it does not (a client larger than the screen), the shots would miss
    the part outside, which is logged."""
    x = 0 if x is None else x
    y = 0 if y is None else y
    fl = 0x0004 | 0x0010
    hp = helper()
    if hp.rect(h)["iconic"]:
        raise RuntimeError("game window is minimized: background mode will not restore it")
    hp.pos(h, 0, x, y, M.CLIENT_W + 40, M.CLIENT_H + 80, fl)
    time.sleep(0.5)
    r = hp.rect(h)
    wl, wt, wr, wb = r["window"]
    dw, dh = (wr - wl) - r["cw"], (wb - wt) - r["ch"]
    hp.pos(h, 0, x, y, M.CLIENT_W + dw, M.CLIENT_H + dh, fl)
    time.sleep(0.8)
    r = hp.rect(h)
    out = offscreen(r["window"], _screen_now())
    if out != (0, 0):
        M.log(f"window {r['window']} reaches {out[0]} x {out[1]} px past the private screen {_screen_now()}: shots miss that part")
    return client_rect(h)


def _screen_now():
    st = M.load_state()
    return tuple(st.get("xvfb_screen") or screen_size())


def restore_noactivate(h, wait=3.0):
    """Background mode never restores a minimized window (as on Windows); True when it is not minimized."""
    if not helper().rect(h)["iconic"]:
        return True
    if M.BG:
        return False
    raise SystemExit(FG_REFUSED)


# ---------------------------------------------------------------- screenshots


def grab_printwindow(h):
    """Client area of window h, from the run's private display only: the window's own X pixmap (XComposite), else that
    display's root cut to the client rect (Wine's coordinates are the X root's there: one screen, no window manager).
    A minimized window is refused."""
    hp = helper()
    r = hp.rect(h)
    if r["iconic"] or r["cw"] <= 0:
        raise RuntimeError("game window minimized or has no size: cannot capture")
    d = display()
    xid = hp.x11(h)
    if xid:
        try:
            img = linux_window.xcapture(xid, display=d)
            box = linux_window.client_crop(img.width, img.height, r["cw"], r["ch"])
            return img.crop(box) if box else img
        except RuntimeError as e:
            M.log(f"window pixmap capture failed ({e}): private display root, cut to the client")
    return linux_window.root_capture(d, box=(r["cx"], r["cy"], r["cx"] + r["cw"], r["cy"] + r["ch"]))


def grab_client(h=None):
    h = h or M.need_window()
    if not M.BG:
        raise SystemExit(FG_REFUSED)
    return grab_printwindow(h)


# ---------------------------------------------------------------- input (window messages through the helper)


def _send_key(sc, ext, up):
    raise SystemExit(FG_REFUSED)


def _lparam(vk, ext, up, repeat=1):
    if vk not in _SC:
        _SC[vk] = helper().mapvk(vk)
    lp = (repeat & 0xFFFF) | (_SC[vk] << 16) | ((1 if ext else 0) << 24)
    if up:
        lp |= (1 << 30) | (1 << 31)
    return lp


def _post_key(hwnd, name, up, ext=0):
    vk = M.VK[name]
    helper().post(hwnd, M.WM_KEYUP if up else M.WM_KEYDOWN, vk, _lparam(vk, ext, up))


def press_bg(key, hold=0.06, mods=(), char=None):
    """game_ctl.press_bg through the helper."""
    hwnd = M.need_window()
    key = key.lower() if len(key) > 1 or key.isalpha() else key
    ext = M.SC[key][1] if key in M.SC else 0
    M._set_mods(mods)
    for m in mods:
        _post_key(hwnd, m, False)
    time.sleep(0.03)
    _post_key(hwnd, key, False, ext)
    if char:
        helper().post(hwnd, M.WM_CHAR, ord(char), _lparam(M.VK[key], ext, False))
    time.sleep(hold)
    _post_key(hwnd, key, True, ext)
    for m in reversed(mods):
        _post_key(hwnd, m, True)
    M._set_mods(())
    time.sleep(0.15)


def press(key, hold=0.06, mods=(), char=None):
    if M.BG:
        return press_bg(key, hold, mods, char)
    raise SystemExit(FG_REFUSED)


def vinput():
    """The plugin's virtual input block of the game process (linux_window.Block: cells read and written by the
    helper), None when the harness is off. First use turns the virtual cursor on, as on Windows."""
    global _VIN, _VIN_PID
    pids = game_pids()
    if _VIN is not None and _VIN_PID not in pids:
        _VIN = None
    if _VIN is None:
        if not pids:
            return None
        b = linux_window.open_block(helper(), pids[0])
        if b is None:
            return None
        _VIN, _VIN_PID = b, pids[0]
        if not b[1]:
            b[7] = 1
            b[2], b[3], b[1] = 800, 450, 1
    return _VIN


def click_bg(fx, fy, button="left", move_only=False, mods=()):
    """game_ctl.click_bg through the helper: virtual cursor in the plugin's block plus posted mouse messages."""
    h = M.need_window()
    r = helper().rect(h)
    x, y = int(fx * r["cw"]), int(fy * r["ch"])
    lp = lambda a, b: ((b & 0xFFFF) << 16) | (a & 0xFFFF)  # noqa: E731
    v = vinput()
    if v is None:
        raise SystemExit("background mouse needs the plugin test harness (mxl2012-testharness.txt next to mxl2012-core.dll, "
                         "plugin >= test-harness build)")
    hp = helper()
    v[2], v[3], v[1] = x - 4, y - 4, 1
    hp.post(h, M.WM_MOUSEMOVE, 0, lp(x - 4, y - 4))
    time.sleep(0.2)
    v[2], v[3] = x, y
    hp.post(h, M.WM_MOUSEMOVE, 0, lp(x, y))
    time.sleep(0.4)
    if move_only:
        return
    down, up, bit, mk = ((M.WM_LBUTTONDOWN, M.WM_LBUTTONUP, 1, 1) if button == "left"
                         else (M.WM_RBUTTONDOWN, M.WM_RBUTTONUP, 2, 2))
    M._set_mods(mods)
    try:
        v[4] |= bit
        hp.post(h, down, mk, lp(x, y))
        time.sleep(0.08)
        v[4] &= ~bit
        hp.post(h, up, 0, lp(x, y))
        time.sleep(0.4)
    finally:
        M._set_mods(())
    M.log(f"click(bg) {fx:.3f},{fy:.3f} -> client {x},{y} {button}")


def post_message(h, msg, wparam=0, lparam=0):
    """game_ctl.post_message through the helper (Wine's PostMessageW in the slot's prefix)."""
    return helper().post(h, msg, wparam, lparam)


def wheel_bg(fx, fy, notches=-1):
    click_bg(fx, fy, move_only=True)
    h = M.need_window()
    r = helper().rect(h)
    px, py = r["cx"] + int(fx * r["cw"]), r["cy"] + int(fy * r["ch"])
    step = 1 if notches > 0 else -1
    for _ in range(abs(notches)):
        helper().post(h, 0x020A, ((120 * step) & 0xFFFF) << 16, ((py & 0xFFFF) << 16) | (px & 0xFFFF))
        time.sleep(0.15)
    M.log(f"wheel(bg) {fx:.3f},{fy:.3f} {notches}")


def click(fx, fy, button="left", move_only=False, mods=()):
    if M.BG:
        return click_bg(fx, fy, button, move_only, mods)
    raise SystemExit(FG_REFUSED)


def console_bg(cmd, timeout=10):
    """game_ctl.console_bg: the command text goes to byte 64 of the block, then the sequence number (cell 8); the plugin
    answers in cells 9 (sequence) and 10 (1 = handled)."""
    v = vinput()
    if v is None:
        raise SystemExit("background console needs the plugin test harness (mxl2012-testharness.txt next to mxl2012-core.dll)")
    data = cmd.encode("utf-8")[:500].decode("utf-8", "ignore")
    v.text(64, data)
    seq = (v[8] + 1) & 0x7FFFFFFF
    v[8] = seq
    t0 = time.time()
    while time.time() - t0 < timeout:
        if v[9] == seq:
            M.log(f"console(bg) {cmd!r} -> {v[10]}")
            return v[10] == 1
        time.sleep(0.05)
    M.log(f"console(bg) {cmd!r} -> no answer in {timeout}s (not in the game window thread's message loop?)")
    return False


# ---------------------------------------------------------------- D2RLoader notice, start / stop


def notice_windows(pids):
    """loader_notice.notice_windows through the helper: the notice dialogs of these (Windows) pids."""
    hp = helper()
    found = []
    for w in hp.windows():
        if w["pid"] not in pids or w["class"] != loader_notice.DIALOG_CLASS or w["title"] != loader_notice.DIALOG_TITLE:
            continue
        push = [t.replace("&", "") for t in hp.buttons(w["hwnd"], push_only=True)]  # Wine: the check box is a Button
        if w["hwnd"] not in _NOTICE_SEEN:
            _NOTICE_SEEN.add(w["hwnd"])
            M.log(f"D2RLoader dialog {w['hwnd']} (pid {w['pid']}, visible {w['visible']}): push buttons {push}, "
                  f"all buttons {hp.buttons(w['hwnd'])}")
        if loader_notice.is_notice_window(w["class"], w["title"], w["visible"], push):
            found.append(w["hwnd"])
    return found


def notice_watch(started):
    return loader_notice.Watch(M.LOADER_LOG, started=started, find=notice_windows,
                               post=lambda h: helper().post(h, loader_notice.TDM_CLICK_BUTTON, loader_notice.IDOK, 0))


def _keep_out_of_front(prev_fg, wait=60, notice=None):
    """As on Windows (background path): answer the loader's notice, then send the new game window to the bottom of
    the window stack without activating it."""
    t0 = time.time()
    polled = 0.0
    while time.time() - t0 < wait:
        if notice is not None and time.time() - polled >= 0.5:
            polled = time.time()
            said = notice.poll(M.game_pids())
            if said:
                M.log(said)
        h = M.find_window()
        if h:
            helper().pos(h, 1, 0, 0, 0, 0, SWP_BOTTOM_QUIET)
            M.log(f"game window {h} sent to the back")
            return True
        time.sleep(0.25)
    try:
        pids = M.game_pids()
        M.log(f"no game window in {wait} s; loader pids {pids}; visible windows: " + " | ".join(
            f"{w['hwnd']} pid={w['pid']} {w['class']} {w['title']!r}" for w in helper().windows() if w["visible"]))
    except Exception as e:  # diagnostics only
        M.log(f"no game window in {wait} s ({e})")
    return False


def launch(args):
    """Start the slot's loader under Proton on the run's private display (game_slots.launch: the slot's prefix, its
    no-focus settings, D: = the slot folder, extra_env = game_env()); Proton's output and log go to the run folder."""
    run = M.current_run()
    with open(os.path.join(run, "proton.out"), "ab") as out:  # the child keeps its own handle
        proc = game_slots.launch(M.SLOT, list(args), log_dir=run, stdout=out, extra_env=game_env())
    prof, changed = game_slots.LAST_PROFILE.get(M.SLOT, ("?", {}))
    M.log(f"graphics profile {prof}" + (f" ({len(changed)} settings changed)" if changed else " (already set)"))
    mb = game_slots.LAST_VRAM.get(M.SLOT)
    M.log(f"VRAM cap {mb} MB (DXVK dxgi.maxDeviceMemory)" if mb else "VRAM cap none")
    return proc


def start(timeout=120):
    """game_ctl.start on Linux: same lock / slot snapshot / harness / log steps; the game runs on a new private display
    while the owner's focus is watched. env MXL_START_TIMEOUT (s) raises the wait for D2R's startup line (a busy disk
    slows the loader's mod compile; lane vramcap)."""
    timeout = max(timeout, float(os.environ.get("MXL_START_TIMEOUT") or 0))
    foreign = M.game_slots.foreign_game(M.SLOT, M.LOCK_OWNER)
    if foreign:
        M.log(f"slot {M.SLOT}: a game this run did not start is running {foreign}: refused (never attached, closed or killed)")
        return False
    live_logs()
    if game_slots.game_pids(M.SLOT, (M.LOADER_NAME.lower(),)):
        if not display():
            M.log(f"slot {M.SLOT}: a game runs without a private display of this run: not attached")
            return False
        M.log(f"game already running (slot {M.SLOT}, display {display()})")
    else:
        if not M.take_lock():
            return False
        try:
            M.log(M.slot_share.begin(M.SLOT, M.LOCK_OWNER, M.GAME_DIR))
        except SystemExit as e:
            M.log(f"slot {M.SLOT}: {e}")
            M.game_slots.release(M.SLOT, M.LOCK_OWNER)
            return False
        M.snapshot_marks()
        off = M._size(M.LOADER_LOG)
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        M.harness_switch(True)
        args = M.slot_share.launch_args(M.SLOT, M.GAME_DIR)
        try:
            for fn in list(M.PRE_LAUNCH):  # test files into the snapshotted slot (the restore takes them out)
                M.log(f"pre-launch {getattr(fn, '__name__', fn)}: {fn()}")
            display_start()
            focus_watch_start()
            launched = time.time()
            launch(args)
        except (OSError, RuntimeError, SystemExit) as e:
            M.log(f"launch failed: {e}")
            display_stop()
            M.harness_switch(False)
            if M.restore_shared():
                M.game_slots.release(M.SLOT, M.LOCK_OWNER)
            return False
        M.log(f"launched D2RLoader under Proton on {display()} " + " ".join(args))
        M._keep_out_of_front(None, notice=notice_watch(launched))
        if not M.wait_log("D2R startup complete.", timeout, off, since):
            M.log("TIMEOUT waiting for startup line")
            return False
    t0 = time.time()
    h = None
    while time.time() - t0 < 60 and not h:
        h = M.find_window()
        time.sleep(1)
    if not h:
        M.log("no game window")
        return False
    r = M.fit_window(h)
    M.log(f"window ready client rect {r}")
    time.sleep(3)
    return True


def stop(timeout=20):
    """game_ctl.stop on Linux: WM_CLOSE through the helper; if the game is still there after `timeout`, the slot's prefix
    is ended (game_slots.stop_prefix: wineserver -k, this prefix only). Then: helper closed, prefix idle, harness off,
    private display ended, slot restored (slot_share.end), lock released, owner focus result written."""
    foreign = M.game_slots.foreign_game(M.SLOT, M.LOCK_OWNER)
    if foreign:
        M.log(f"slot {M.SLOT}: a game this run did not start is running {foreign}: not closed")
        return
    running = bool(game_slots.game_pids(M.SLOT, (M.LOADER_NAME.lower(),)))
    if running and display():
        try:
            h = M.find_window()
            if h:
                helper().post(h, WM_CLOSE, 0, 0)
        except (linux_window.HelperError, SystemExit) as e:
            M.log(f"WM_CLOSE not sent: {e}")
        t0 = time.time()
        while time.time() - t0 < timeout and game_slots.game_pids(M.SLOT, (M.LOADER_NAME.lower(),)):
            time.sleep(1)
    close_helper()
    if game_slots.game_pids(M.SLOT, (M.LOADER_NAME.lower(),)):
        M.log("forcing: wineserver -k on the slot's own prefix")
        game_slots.stop_prefix(M.SLOT)
    elif not game_slots.wait_prefix_idle(M.SLOT):
        M.log(f"slot {M.SLOT}: prefix still busy: wineserver -k on it")
        game_slots.stop_prefix(M.SLOT)
    M.harness_switch(False)
    display_stop()
    time.sleep(1)
    if not M.game_slots.slot_processes(M.GAME_DIR):
        M.game_slots.clear_launch(M.SLOT)
    if os.path.isfile(os.path.join(M.GAME_DIR, *LOG_NAMES["LOADER_LOG"])):  # a launch wrote logs: keep them
        keep_logs()
    if M.restore_shared():
        M.game_slots.release(M.SLOT, M.LOCK_OWNER)
    focus_watch_stop()
    M.log("stopped" if running else "not running")
