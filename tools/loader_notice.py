"""D2RLoader's notice for a D2R version it has not been tested with, answered without focus (docs/port-3.4.md 2.2).

On a D2R newer than the one a D2RLoader release was made for (D2R 3.4 with D2RLoader 1.3.1), D2RLoader writes

    [WARN] This D2R version hasn't been fully tested yet. You're running Diablo II: Resurrected 3.4. The latest
    version officially supported by D2RLoader is 3.3.

to d2rloader.log and opens a Windows task dialog (class #32770, title "D2RLoader", heading "This D2R version hasn't
been fully tested yet", a check box "Don't remind me again for D2R <version>", one OK button) before it starts the game,
and waits. A player clicks OK. An automated run cannot click: it never takes the foreground or moves the cursor.

`Watch.poll(pids)` answers that dialog of our own launch with the task dialog's own message for "press this button"
(TDM_CLICK_BUTTON, IDOK), posted to the dialog window: no focus, no cursor, no key state, no hook, and nothing is
written to D2RLoader's settings (the check box stays unticked, so the player's own choice is not changed). It answers
only when all of this holds, and only once per launch:

- the window belongs to one of the given processes (the loader this run started),
- it is a visible dialog titled "D2RLoader" whose only button is OK,
- d2rloader.log holds the warning line above with a time stamp of this launch.

So another D2RLoader dialog (an error) is never answered. slot_share.bootcheck and game_ctl.start call it while they
wait for the game."""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import winapi  # noqa: E402

NOTICE_LOG = "This D2R version hasn't been fully tested yet"
DIALOG_CLASS, DIALOG_TITLE = "#32770", "D2RLoader"
TDM_CLICK_BUTTON = 0x0400 + 102  # WM_USER + 102
IDOK = 1
SETTLE = 0.7  # seconds between first seeing the dialog and answering it: it is shown before it takes messages


def _setup(lib):
    lib.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    lib.PostMessageW.restype = wt.BOOL


user32 = winapi.Dll("user32", _setup)


def is_notice_window(cls, title, visible, buttons):
    """True for a window that looks like the notice: a visible dialog titled D2RLoader with OK as its only button."""
    return bool(visible) and cls == DIALOG_CLASS and title == DIALOG_TITLE and list(buttons) == ["OK"]


def log_has_notice(path, started):
    """True when d2rloader.log holds the warning line of this launch: a line "[YYYY-MM-DD HH:MM:SS.mmm] [WARN] ..." stamped
    at or after `started` (the launch's time.time(), one second of slack). The previous run's lines are older."""
    since = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started - 1))
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            return any(NOTICE_LOG in ln and ln[1:20] >= since for ln in f)
    except OSError:
        return False


def _text(h):
    n = user32.GetWindowTextLengthW(h)
    b = ctypes.create_unicode_buffer(n + 2)
    user32.GetWindowTextW(h, b, n + 2)
    return b.value


def _class(h):
    b = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, b, 256)
    return b.value


def notice_windows(pids):
    """HWNDs of the given processes' top-level windows that look like the notice."""
    pids, found = set(pids), []
    proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def buttons(h):
        out = []

        @proc
        def child(c, _):
            if _class(c) == "Button" and user32.IsWindowVisible(c):
                out.append(_text(c))
            return True
        user32.EnumChildWindows(h, child, 0)
        return out

    @proc
    def top(h, _):
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids and is_notice_window(_class(h), _text(h), user32.IsWindowVisible(h), buttons(h)):
            found.append(h)
        return True
    user32.EnumWindows(top, 0)
    return found


class Watch:
    """One launch's notice: poll() while waiting for the game; it answers at most once."""

    def __init__(self, log_path, started=None, find=notice_windows, post=None, clock=time.time):
        self.log_path = log_path
        self.started = clock() if started is None else started
        self.answered = False
        self._seen = {}
        self._find, self._clock = find, clock
        self._post = post or (lambda h: user32.PostMessageW(h, TDM_CLICK_BUTTON, IDOK, 0))

    def poll(self, pids):
        """Returns a line for the run's log when the notice was answered in this call, else None."""
        if self.answered or not pids:
            return None
        now = self._clock()
        for h in self._find(pids):
            first = self._seen.setdefault(h, now)
            if now - first < SETTLE or not log_has_notice(self.log_path, self.started):
                continue
            self._post(h)
            self.answered = True
            return (f"D2RLoader's notice for a D2R version it has not tested (window {int(h)}) answered with OK in the "
                    "background (TDM_CLICK_BUTTON to our own launch's dialog; its check box is left unticked)")
        return None
