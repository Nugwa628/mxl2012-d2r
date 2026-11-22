"""Window control for a game slot that runs under Proton on Linux (lane linctl, 2026-11-20).

Used by tools/game_ctl_linux.py (game_ctl's Linux window layer); slot folders, prefixes, Proton and the Linux pids come
from tools/game_slots.py (Linux backend, lane linslots).

- `Helper`: wctl.exe (tools/wctl/wctl.c, built by tools/wctl/build.sh) running inside the slot's prefix, so it shares
  the game's wineserver: window handles, Windows process ids and the plugin's named input block are the game's own. One
  `wctl.exe serve` process per slot, kept open while the game runs and closed before the prefix must go idle. Every
  request that changes something and its answer go to the `log` callback. A request without an answer in `timeout`
  seconds ends the helper (HelperError) instead of hanging the run.
- `PrivateDisplay`: the game runs on its own Xvfb display, never on the owner's desktop (owner rule 2026-11-20: test
  games never take focus; on the desktop the loader's dialog and the game window took it whatever the prefix settings).
  D2R renders there with Mesa's CPU-copy present (MESA_VK_WSI_DEBUG=sw) once vkd3d-proton does not use
  VK_KHR_present_wait, whose waits never end there and stalled the game's UI thread (PRIVATE_ENV; lane linctl x1/x2/x3).
- `xcapture()` / `root_capture()`: screenshots from the private display only (refused for the owner's display). The
  window's own pixmap via XComposite (PrintWindow returns black under Wine, WineHQ bug 46257), or the private display's
  root cropped to the window.

The game window never gets the focus and the real cursor never moves: the helper posts window messages and sizes with
SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS only."""
import ctypes as C
import os
import select
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Environment of a game on a private display (with DISPLAY). Measured 2026-11-20 (lane linctl, slot 5): with only
# MESA_VK_WSI_DEBUG=sw the frame stays black and the UI thread stalls (also lane wineinput run4); with present_wait hidden
# from vkd3d-proton the Blizzard intro and Gamma Calibration render (x2, x3). Xvfb's Present extension and FIFO can stay.
PRIVATE_ENV = {"MESA_VK_WSI_DEBUG": "sw", "VKD3D_DISABLE_EXTENSIONS": "VK_KHR_present_wait,VK_KHR_present_wait2"}


def wctl_exe():
    """The helper's Linux path: env MXL_WCTL, else tools/wctl/wctl.exe (tools/wctl/build.sh's default output, where
    slot_share.window_helper looks too)."""
    return os.environ.get("MXL_WCTL") or os.path.join(REPO, "tools", "wctl", "wctl.exe")


def to_wine_path(path):
    """A Linux path as Wine sees it through the Z: drive (Proton prefixes map Z: to /)."""
    return "Z:" + os.path.abspath(path).replace("/", "\\")


class SlotEnv:
    """A Linux game slot as the helper needs it: game folder, Proton folder (STEAM_COMPAT_DATA_PATH), Wine prefix (its
    pfx) and Proton build; defaults from game_slots' Linux backend (linux_slot, proton_dir). env() is game_slots.wine_env
    plus `extra`."""

    def __init__(self, n, slot_dir=None, compat=None, proton_dir=None):
        import game_slots
        self.n = int(n)
        self.slot_dir = slot_dir or game_slots.slot_dir(self.n)
        self.compat = compat or game_slots.compat_dir(self.n)
        self.prefix = os.path.join(self.compat, "pfx")
        self.proton_dir = proton_dir or game_slots.proton_dir()
        self.wine = os.path.join(self.proton_dir, "files", "bin", "wine")
        self.wineserver = os.path.join(self.proton_dir, "files", "bin", "wineserver")

    def env(self, base=None, **extra):
        import game_slots
        e = dict(os.environ if base is None else base)
        e.update(STEAM_COMPAT_DATA_PATH=self.compat, STEAM_COMPAT_CLIENT_INSTALL_PATH=game_slots.steam_dir(),
                 WINEPREFIX=self.prefix, SteamAppId="0", SteamGameId="0")
        e.setdefault("WINEDEBUG", "-all")
        e.update(extra)
        return e

    def unix_path(self, win_path):
        """A Windows path of this prefix ("D:\\D2RLoader.exe") as a Linux path, through the prefix's dosdevices links;
        None when the drive is not mapped."""
        if len(win_path) < 2 or win_path[1] != ":":
            return None
        link = os.path.join(self.prefix, "dosdevices", win_path[0].lower() + ":")
        if not (os.path.islink(link) or os.path.isdir(link)):
            return None
        root = os.path.realpath(link)
        rest = win_path[2:].replace("\\", "/").lstrip("/")
        return os.path.join(root, rest) if rest else root


def slot_env(n):
    return SlotEnv(n)


class HelperError(RuntimeError):
    pass


class Helper:
    """`wctl.exe serve` inside the slot's prefix. request(*fields) -> (answer words after "ok", list lines).
    A request that ends in "err ..." raises HelperError (except where the caller asks for the raw reply)."""

    def __init__(self, env, log=None, exe=None, popen=subprocess.Popen, stderr_path=None, timeout=20.0, extra_env=None):
        self.env, self.log, self.exe, self._popen = env, log or (lambda m: None), exe or wctl_exe(), popen
        self.extra_env = dict(extra_env or {})  # e.g. DISPLAY of the game's private display
        self.stderr_path = stderr_path
        self.timeout = timeout
        self.p = None
        self._buf = b""
        self.lock = threading.Lock()

    def _start(self):
        if not os.path.isfile(self.exe):
            raise HelperError(f"{self.exe} missing: build it with tools/wctl/build.sh (docs/testing.md, Linux window control)")
        err = open(self.stderr_path, "ab") if self.stderr_path else subprocess.DEVNULL
        self._buf = b""
        self.p = self._popen([self.env.wine, to_wine_path(self.exe), "serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=err, env=self.env.env(**self.extra_env), cwd=os.path.dirname(self.exe))
        if err is not subprocess.DEVNULL:
            err.close()  # the child has its own handle
        first = self._readline(60.0)  # the first start of a prefix's wine can take a while
        if not first.startswith("ok wctl"):
            self.close()
            raise HelperError(f"wctl did not start: {first!r}")
        self.log(f"wctl: helper up in prefix {self.env.prefix} ({first[3:]})")

    def _readline(self, timeout=None):
        """One answer line; HelperError when the helper ends or says nothing for `timeout` seconds (then it is ended:
        a request that waits on a busy game must not hang the run)."""
        timeout = self.timeout if timeout is None else timeout
        out = self.p.stdout
        if not hasattr(out, "fileno"):  # a test double
            line = out.readline()
            if not line:
                raise HelperError("wctl ended (the prefix's wineserver is gone?)")
            return line.decode("utf-8", "replace").rstrip("\r\n")
        fd = out.fileno()
        end = time.time() + timeout
        while b"\n" not in self._buf:
            left = end - time.time()
            if left <= 0 or not select.select([fd], [], [], left)[0]:
                self.close(hard=True)
                raise HelperError(f"wctl gave no answer in {timeout:.0f} s: helper ended")
            chunk = os.read(fd, 65536)
            if not chunk:
                raise HelperError("wctl ended (the prefix's wineserver is gone?)")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8", "replace").rstrip("\r")

    def request(self, *fields, quiet=False, check=True):
        msg = "\t".join(str(f) for f in fields)
        if "\n" in msg:
            raise ValueError("newline in a wctl request")
        with self.lock:
            if self.p is None or self.p.poll() is not None:
                self._start()
            self.p.stdin.write(msg.encode("utf-8") + b"\n")
            self.p.stdin.flush()
            items = []
            while True:
                line = self._readline()
                if line.startswith("- "):
                    items.append(line[2:])
                    continue
                break
        if not quiet:
            self.log(f"wctl: {msg.replace(chr(9), ' ')} -> {line}")
        if line.startswith("ok"):
            return line[2:].strip().split(" ") if line[2:].strip() else [], items
        if check:
            raise HelperError(f"wctl {fields[0]}: {line}")
        return None, items

    def close(self, hard=False):
        p, self.p = self.p, None
        if p is None:
            return
        try:
            if not hard and p.poll() is None:
                p.stdin.write(b"quit\n")
                p.stdin.flush()
                p.wait(10)
        except Exception:
            pass
        if p.poll() is None:
            p.kill()  # our own helper process only
            p.wait(5)
        for f in (p.stdin, p.stdout):
            try:
                f.close()
            except Exception:
                pass

    # ---- typed requests

    def procs(self):
        """[(Windows pid, image path)] of every process of the slot's wineserver."""
        _, items = self.request("procs", quiet=True)
        out = []
        for it in items:
            pid, _, img = it.partition("\t")
            out.append((int(pid), img))
        return out

    def find(self, title, pid=0):
        """(hwnd, pid, x11 id, client w, client h, iconic) of the visible window titled `title` (or "title [..."),
        None when there is none."""
        words, _ = self.request("find", title, pid, quiet=True, check=False)
        if words is None:
            return None
        return int(words[0]), int(words[1]), int(words[2], 16), int(words[3]), int(words[4]), words[5] == "1"

    def windows(self):
        _, items = self.request("windows", quiet=True)
        out = []
        for it in items:
            f = it.split("\t")
            if len(f) >= 9:
                out.append({"hwnd": int(f[0]), "pid": int(f[1]), "visible": f[2] == "1", "iconic": f[3] == "1",
                            "x11": int(f[4], 16), "w": int(f[5]), "h": int(f[6]), "class": f[7], "title": "\t".join(f[8:])})
        return out

    def buttons(self, hwnd, push_only=False):
        """Texts of the visible child buttons. push_only: push buttons only (BS_PUSHBUTTON / BS_DEFPUSHBUTTON); Wine's
        task dialog makes its check box a Button too, which Windows' does not show as one."""
        out = []
        for it in self.request("buttons", hwnd, quiet=True)[1]:
            style, _, text = it.partition("\t")
            if not push_only or style in ("0", "1"):
                out.append(text)
        return out

    def rect(self, hwnd):
        """dict: cw, ch (client size), cx, cy (client origin on the screen), window (l, t, r, b), iconic, visible."""
        w = [int(v) for v in self.request("rect", hwnd, quiet=True)[0]]
        return {"cw": w[0], "ch": w[1], "cx": w[2], "cy": w[3], "window": tuple(w[4:8]), "iconic": bool(w[8]),
                "visible": bool(w[9])}

    def pos(self, hwnd, after, x, y, w, h, flags):
        """SetWindowPos in the prefix. The helper always adds SWP_NOACTIVATE and turns any `after` but HWND_BOTTOM (1)
        into SWP_NOZORDER: it cannot activate or raise a window."""
        return self.request("pos", hwnd, after, x, y, w, h, flags)[0][:1] == ["1"]

    def post(self, hwnd, msg, wparam, lparam):
        return self.request("post", hwnd, f"{msg:#x}", f"{wparam:#x}", f"{lparam:#x}")[0] == ["1"]

    def mapvk(self, vk):
        return int(self.request("mapvk", vk, quiet=True)[0][0])

    def alive(self, hwnd):
        return self.request("alive", hwnd, quiet=True)[0] == ["1"]

    def x11(self, hwnd):
        return int(self.request("x11", hwnd, quiet=True)[0][0], 16)


class Block:
    """The plugin test harness's virtual input block (int32 cells), read and written through the helper: `v[4] |= 1`
    works as on Windows (one get and one set). `text(off, s)` writes a NUL-terminated UTF-8 string at byte `off`."""

    def __init__(self, helper, pid):
        self.h, self.pid = helper, pid

    def __getitem__(self, i):
        return int(self.h.request("vget", int(i), quiet=True)[0][0])

    def __setitem__(self, i, v):
        self.h.request("vset", int(i), int(v))

    def text(self, off, s):
        self.h.request("vtext", int(off), s)


def open_block(helper, pid):
    """Block of game process `pid` (Windows pid), None when the harness is off (no block)."""
    words, _ = helper.request("vopen", pid, check=False)
    return None if words is None else Block(helper, pid)


# ---------------------------------------------------------------- capture (XComposite, window only)


class _XWA(C.Structure):  # XWindowAttributes up to map_state (+ padding for the rest)
    _fields_ = [("x", C.c_int), ("y", C.c_int), ("width", C.c_int), ("height", C.c_int), ("border_width", C.c_int),
                ("depth", C.c_int), ("visual", C.c_void_p), ("root", C.c_ulong), ("class_", C.c_int),
                ("bit_gravity", C.c_int), ("win_gravity", C.c_int), ("backing_store", C.c_int),
                ("backing_planes", C.c_ulong), ("backing_pixel", C.c_ulong), ("save_under", C.c_int),
                ("colormap", C.c_ulong), ("map_installed", C.c_int), ("map_state", C.c_int), ("pad", C.c_byte * 64)]


class _XImage(C.Structure):
    _fields_ = [("width", C.c_int), ("height", C.c_int), ("xoffset", C.c_int), ("format", C.c_int), ("data", C.c_void_p),
                ("byte_order", C.c_int), ("bitmap_unit", C.c_int), ("bitmap_bit_order", C.c_int), ("bitmap_pad", C.c_int),
                ("depth", C.c_int), ("bytes_per_line", C.c_int), ("bits_per_pixel", C.c_int)]


_X = None


def _xlibs():
    global _X
    if _X is None:
        x11, xc = C.CDLL("libX11.so.6"), C.CDLL("libXcomposite.so.1")
        x11.XOpenDisplay.restype = C.c_void_p
        x11.XOpenDisplay.argtypes = [C.c_char_p]
        x11.XCloseDisplay.argtypes = [C.c_void_p]
        x11.XGetImage.restype = C.POINTER(_XImage)
        x11.XGetImage.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_ulong, C.c_int]
        x11.XGetWindowAttributes.argtypes = [C.c_void_p, C.c_ulong, C.c_void_p]
        x11.XSync.argtypes = [C.c_void_p, C.c_int]
        x11.XFreePixmap.argtypes = [C.c_void_p, C.c_ulong]
        x11.XDestroyImage.argtypes = [C.POINTER(_XImage)]
        x11.XFree.argtypes = [C.c_void_p]
        x11.XSetErrorHandler.argtypes = [C.c_void_p]
        x11.XSetErrorHandler.restype = C.c_void_p
        xc.XCompositeNameWindowPixmap.restype = C.c_ulong
        xc.XCompositeNameWindowPixmap.argtypes = [C.c_void_p, C.c_ulong]
        xc.XCompositeRedirectWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_int]
        xc.XCompositeUnredirectWindow.argtypes = [C.c_void_p, C.c_ulong, C.c_int]
        _X = (x11, xc)
    return _X


_ERRORS = []
_HANDLER = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda d, e: _ERRORS.append(1) or 0)


def client_crop(xw, xh, client_w, client_h):
    """Box (l, t, r, b) of the client area inside the captured X window (xw x xh): the client centred horizontally and
    bottom-aligned (a menu bar or caption Wine drew sits on top; Wine's screen coordinates are not the X root's on a
    multi-monitor desktop, so positions cannot be compared). None when the sizes match (the whole image is the client)
    or the client is larger (no crop is safe)."""
    if (xw, xh) == (client_w, client_h) or client_w <= 0 or client_h <= 0:
        return None
    if client_w > xw or client_h > xh:
        return None
    left = (xw - client_w) // 2
    top = xh - client_h - left  # equal side and bottom borders
    top = max(0, min(top, xh - client_h))
    return left, top, left + client_w, top + client_h


def xcapture(xid, display=None):
    """RGB PIL image of X11 window `xid` only (its own composite pixmap) on `display` (default: DISPLAY). RuntimeError
    when that cannot be done (then there is no image, never a fallback to the screen), and for the owner's display."""
    from PIL import Image
    if not is_private(display or os.environ.get("DISPLAY", ":0")):
        raise RuntimeError("capture refused: not a private display (the owner's screen is never captured)")
    x11, xc = _xlibs()
    d = x11.XOpenDisplay(display.encode() if display else None)
    if not d:
        raise RuntimeError("no X display")
    del _ERRORS[:]
    old = x11.XSetErrorHandler(C.cast(_HANDLER, C.c_void_p))
    redirected = False
    pm = 0
    try:
        a = _XWA()
        if not x11.XGetWindowAttributes(d, xid, C.byref(a)) or a.map_state != 2:
            raise RuntimeError(f"X window {xid:#x} is not viewable (minimized or unmapped): no shot")
        xc.XCompositeRedirectWindow(d, xid, 0)  # CompositeRedirectAutomatic: this window only, still shown as before
        redirected = True
        x11.XSync(d, 0)
        pm = xc.XCompositeNameWindowPixmap(d, xid)
        x11.XSync(d, 0)
        if _ERRORS or not pm:
            raise RuntimeError("cannot name the window's pixmap: no shot")
        img = x11.XGetImage(d, pm, 0, 0, a.width, a.height, 0xFFFFFFFF, 2)  # ZPixmap
        x11.XSync(d, 0)
        if _ERRORS or not img:
            raise RuntimeError("XGetImage of the window pixmap failed: no shot")
        im = img.contents
        try:
            if im.bits_per_pixel != 32:
                raise RuntimeError(f"unexpected {im.bits_per_pixel} bits per pixel: no shot")
            raw = C.string_at(im.data, im.bytes_per_line * im.height)
            return Image.frombuffer("RGB", (im.width, im.height), raw, "raw", "BGRX", im.bytes_per_line, 1).copy()
        finally:
            x11.XDestroyImage(img)
    finally:
        if pm:
            x11.XFreePixmap(d, pm)
        if redirected:
            xc.XCompositeUnredirectWindow(d, xid, 0)
        x11.XSync(d, 0)
        x11.XSetErrorHandler(old)
        x11.XCloseDisplay(d)




def root_capture(display, box=None, owner=None):
    """RGB image of the root window of a PRIVATE display (box: (l, t, r, b) to crop). Refused for the owner's display
    (`owner`, default the DISPLAY this process started with) and :0."""
    from PIL import Image
    if not is_private(display, owner):
        raise RuntimeError(f"display {display} is the owner's: no capture")
    x11, _ = _xlibs()
    x11.XDefaultRootWindow.argtypes = [C.c_void_p]
    x11.XDefaultRootWindow.restype = C.c_ulong
    d = x11.XOpenDisplay(display.encode())
    if not d:
        raise RuntimeError(f"cannot open display {display}")
    try:
        root = x11.XDefaultRootWindow(d)
        a = _XWA()
        x11.XGetWindowAttributes(d, root, C.byref(a))
        img = x11.XGetImage(d, root, 0, 0, a.width, a.height, 0xFFFFFFFF, 2)
        if not img:
            raise RuntimeError("XGetImage of the private root failed")
        im = img.contents
        try:
            raw = C.string_at(im.data, im.bytes_per_line * im.height)
            pic = Image.frombuffer("RGB", (im.width, im.height), raw, "raw", "BGRX", im.bytes_per_line, 1).copy()
        finally:
            x11.XDestroyImage(img)
    finally:
        x11.XCloseDisplay(d)
    return pic.crop(box) if box else pic


# ---------------------------------------------------------------- private display (owner rule: no focus stealing)

OWNER_DISPLAY = os.environ.get("DISPLAY", ":0")  # the display this process was started on: the owner's desktop


def _dnum(display):
    try:
        return int(str(display).split(":", 1)[1].split(".", 1)[0])
    except (IndexError, ValueError):
        return None


def is_private(display, owner=None):
    """True for a display that is not the owner's (not `owner` / OWNER_DISPLAY and not :0)."""
    n = _dnum(display)
    return n is not None and n != 0 and n != _dnum(owner or OWNER_DISPLAY)


def free_display(start=100, xdir="/tmp/.X11-unix"):
    """The first display :N from `start` with no X socket or lock file."""
    n = start
    while os.path.exists(os.path.join(xdir, f"X{n}")) or os.path.exists(f"/tmp/.X{n}-lock"):
        n += 1
    return f":{n}"


def xvfb_alive(pid, display, proc="/proc"):
    """True when `pid` is an Xvfb serving `display` (checked from its command line before it is ever signalled)."""
    try:
        with open(os.path.join(proc, str(pid), "cmdline"), "rb") as f:
            argv = f.read().split(b"\0")
    except OSError:
        return False
    return bool(argv) and os.path.basename(argv[0]) == b"Xvfb" and str(display).encode() in argv


class PrivateDisplay:
    """Start / stop an Xvfb display for one game run. start() returns (display, pid); the Xvfb runs in its own
    session, so it outlives a `game_ctl start` process (game_ctl keeps both in the run's state.json)."""

    @staticmethod
    def start(size="1920x1080", display=None, log_path=None, popen=subprocess.Popen, wait=10.0, xdir="/tmp/.X11-unix"):
        display = display or free_display(xdir=xdir)
        if not is_private(display):
            raise RuntimeError(f"display {display} is the owner's: refused")
        out = open(log_path, "ab") if log_path else subprocess.DEVNULL
        try:
            p = popen(["Xvfb", display, "-screen", "0", f"{size}x24", "-nolisten", "tcp"], stdout=out,
                      stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            if out is not subprocess.DEVNULL:
                out.close()
        sock = os.path.join(xdir, "X" + str(_dnum(display)))
        end = time.time() + wait
        while time.time() < end and not os.path.exists(sock):
            if p.poll() is not None:
                raise RuntimeError(f"Xvfb {display} ended at start (exit {p.returncode})")
            time.sleep(0.1)
        if not os.path.exists(sock):
            raise RuntimeError(f"Xvfb {display} did not come up in {wait:.0f} s")
        return display, p.pid

    @staticmethod
    def stop(pid, display, kill=os.kill, alive=xvfb_alive, wait=10.0):
        """End our Xvfb (only when `pid` still is the Xvfb of `display`). True when it is gone."""
        if not pid or not alive(pid, display):
            return True
        kill(pid, signal.SIGTERM)
        end = time.time() + wait
        while time.time() < end and alive(pid, display):
            time.sleep(0.1)
        return not alive(pid, display)
