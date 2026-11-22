"""game_ctl's Linux window layer (tools/game_ctl_linux.py, tools/linux_window.py) without a game, Wine or X:

- the wctl helper protocol against a fake `wctl.exe serve` (requests, list replies, errors, every request logged, quit,
  a helper that stops answering is ended instead of hanging);
- the private display: never the owner's display, Xvfb start / stop of our own process only, captures refused there;
- game_ctl's window functions with a fake helper: find by Windows pid, fit, keys, mouse with the virtual cursor block,
  console, the D2RLoader notice (Wine's check box is a Button too), launch on the private display, stop (WM_CLOSE,
  helper closed, prefix idle, display ended), the owner focus watch, foreground refused, nothing ever activates;
- the client crop of a captured X window.
The Linux layer is installed into game_ctl only under game_slots' Linux backend; those tests are skipped elsewhere."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("MXL_SLOT", "2")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import linux_window  # noqa: E402

import game_slots  # noqa: E402

LINUX = game_slots.LINUX


class FakeServe:
    """A Popen stand-in for `wine wctl.exe serve`: answers each request line from a dict of handlers."""

    def __init__(self, answers):
        self.answers, self.sent, self.ended = answers, [], False
        self._out = io.BytesIO(b"ok wctl 2 ready\n")
        self.stdout = self
        self.stdin = self
        self.args = None
        self._buf = b""

    # stdin
    def write(self, b):
        self._buf += b

    def flush(self):
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            req = line.decode()
            self.sent.append(req)
            f = req.split("\t")
            if f[0] == "quit":
                self.ended = True
                reply = "ok bye"
            else:
                reply = self.answers.get(f[0], "err unknown request")
                reply = reply(f) if callable(reply) else reply
            pos = self._out.tell()
            self._out.seek(0, 2)
            self._out.write(reply.encode() + b"\n")
            self._out.seek(pos)

    # stdout
    def readline(self):
        return self._out.readline()

    def poll(self):
        return 0 if self.ended else None

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.ended = True


def make_helper(answers, log=None):
    env = linux_window.SlotEnv(5, slot_dir="/nonexistent/s5", compat="/nonexistent/p5", proton_dir="/nonexistent/proton")
    serve = FakeServe(answers)

    def popen(args, **kw):
        serve.args = args
        serve.kw = kw
        return serve

    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        exe = f.name
    h = linux_window.Helper(env, log=log, exe=exe, popen=popen)
    return h, serve, exe


class HelperProtocol(unittest.TestCase):
    def test_requests_lists_errors_and_log(self):
        lines = []
        h, serve, exe = make_helper({
            "buttons": "- 1\tOK\n- 3\tDon't remind me again\nok",
            "procs": "- 32\tC:\\windows\\syswow64\\start.exe\n- 340\tD:\\D2RLoader.exe\nok 2",
            "find": lambda f: "ok 852144 340 0xea00004 1600 900 0" if f[1] == "Diablo II: Resurrected" else "err none",
            "post": "ok 1",
            "rect": "ok 1600 900 100 60 99 30 1701 961 0 1",
        }, log=lines.append)
        self.addCleanup(os.remove, exe)
        self.assertEqual(h.procs(), [(32, "C:\\windows\\syswow64\\start.exe"), (340, "D:\\D2RLoader.exe")])
        self.assertEqual(h.find("Diablo II: Resurrected", 340), (852144, 340, 0xea00004, 1600, 900, False))
        self.assertIsNone(h.find("Other"))
        self.assertEqual(h.buttons(7, push_only=True), ["OK"])
        self.assertEqual(h.buttons(7), ["OK", "Don't remind me again"])
        self.assertTrue(h.post(852144, 0x100, 0x0D, 0x1C0001))
        r = h.rect(852144)
        self.assertEqual((r["cw"], r["ch"], r["cx"], r["cy"], r["window"]), (1600, 900, 100, 60, (99, 30, 1701, 961)))
        with self.assertRaises(linux_window.HelperError):
            h.request("bogus", 1)
        h.close()
        self.assertTrue(serve.ended)
        self.assertEqual(serve.sent[-1], "quit")
        # the helper runs in the slot's prefix, through Proton's wine, by its Z: path
        self.assertEqual(serve.args[0], "/nonexistent/proton/files/bin/wine")
        self.assertEqual(serve.args[1:], [linux_window.to_wine_path(exe), "serve"])
        self.assertEqual(serve.kw["env"]["WINEPREFIX"], "/nonexistent/p5/pfx")
        # what was sent to the game is in the log; quiet lookups are not
        self.assertTrue(any(ln.startswith("wctl: post 852144 0x100 0xd 0x1c0001 -> ok 1") for ln in lines), lines)
        self.assertFalse(any("procs" in ln for ln in lines))

    def test_missing_exe_says_how_to_build(self):
        h = linux_window.Helper(linux_window.SlotEnv(5), exe="/nonexistent/wctl.exe")
        with self.assertRaisesRegex(linux_window.HelperError, "tools/wctl/build.sh"):
            h.request("ping")

    def test_newline_refused(self):
        h, _, exe = make_helper({})
        self.addCleanup(os.remove, exe)
        with self.assertRaises(ValueError):
            h.request("vtext", 64, "a\nb")

    def test_block(self):
        cells = {}

        def vset(f):
            cells[int(f[1])] = int(f[2])
            return f"ok {f[2]}"

        h, serve, exe = make_helper({"vopen": "ok Local\\mxl2012-testharness-input-340", "vset": vset,
                                     "vget": lambda f: f"ok {cells.get(int(f[1]), 0)}", "vtext": "ok 5"})
        self.addCleanup(os.remove, exe)
        b = linux_window.open_block(h, 340)
        b[4] = 2
        b[4] |= 1
        self.assertEqual(b[4], 3)
        b.text(64, "h hp")
        self.assertIn("vtext\t64\th hp", serve.sent)
        h2, _, exe2 = make_helper({"vopen": "err no harness input block"})
        self.addCleanup(os.remove, exe2)
        self.assertIsNone(linux_window.open_block(h2, 340))


class SlotParts(unittest.TestCase):
    def test_unix_path(self):
        root = tempfile.mkdtemp()
        slot = os.path.join(root, "s5")
        compat = os.path.join(root, "p5")
        os.makedirs(os.path.join(compat, "pfx", "dosdevices"))
        os.makedirs(slot)
        os.symlink(slot, os.path.join(compat, "pfx", "dosdevices", "d:"))
        env = linux_window.SlotEnv(5, slot_dir=slot, compat=compat, proton_dir="/nonexistent/proton")
        self.assertEqual(env.unix_path("D:\\D2RLoader.exe"), os.path.join(os.path.realpath(slot), "D2RLoader.exe"))
        self.assertIsNone(env.unix_path("Q:\\x.exe"))
        self.assertIsNone(env.unix_path("relative"))

    def test_client_crop(self):
        self.assertIsNone(linux_window.client_crop(1600, 900, 1600, 900))
        self.assertEqual(linux_window.client_crop(1602, 931, 1600, 900), (1, 30, 1601, 930))
        self.assertIsNone(linux_window.client_crop(800, 600, 1600, 900))
        self.assertEqual(linux_window.client_crop(632, 326, 632, 307), (0, 19, 632, 326))  # notepad: menu bar on top


class SilentServe(FakeServe):
    """A helper that starts, then never answers (a request waiting on a busy game): stdout is a real pipe."""

    def __init__(self):
        super().__init__({})
        r, w = os.pipe()
        os.write(w, b"ok wctl 2 ready\n")
        self._w = w
        self.stdout = os.fdopen(r, "rb", buffering=0)
        self.killed = False

    def flush(self):
        self._buf = b""  # swallow the request

    def kill(self):
        self.killed = self.ended = True
        os.close(self._w)


class HelperTimeout(unittest.TestCase):
    def test_no_answer_ends_the_helper(self):
        env = linux_window.SlotEnv(5, slot_dir="/nonexistent/s5", compat="/nonexistent/p5", proton_dir="/nonexistent/proton")
        serve = SilentServe()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            exe = f.name
        self.addCleanup(os.remove, exe)
        h = linux_window.Helper(env, exe=exe, popen=lambda a, **k: serve, timeout=0.3)
        with self.assertRaisesRegex(linux_window.HelperError, "no answer"):
            h.request("pos", 1, 0, 0, 0, 10, 10, 0)
        self.assertTrue(serve.killed)
        self.assertIsNone(h.p)


class PrivateDisplayTests(unittest.TestCase):
    def test_owner_display_never_private(self):
        self.assertFalse(linux_window.is_private(":0"))
        self.assertFalse(linux_window.is_private(":0.0"))
        self.assertFalse(linux_window.is_private(":7", owner=":7.0"))
        self.assertTrue(linux_window.is_private(":101", owner=":0"))
        self.assertFalse(linux_window.is_private("junk"))
        with patch.dict(os.environ, {"DISPLAY": ":0"}):
            with self.assertRaisesRegex(RuntimeError, "not a private display"):
                linux_window.xcapture(0x123)
        with self.assertRaisesRegex(RuntimeError, "owner"):
            linux_window.root_capture(":0")

    def test_start_and_stop_our_xvfb_only(self):
        xdir = tempfile.mkdtemp()
        open(os.path.join(xdir, "X100"), "w").close()  # :100 is taken
        self.assertEqual(linux_window.free_display(xdir=xdir), ":101")
        calls = []

        def popen(argv, **kw):
            calls.append((argv, kw))
            open(os.path.join(xdir, "X101"), "w").close()  # the server's socket appears
            return MagicMock(pid=777, poll=MagicMock(return_value=None))
        d, pid = linux_window.PrivateDisplay.start("1920x1080", popen=popen, xdir=xdir)
        self.assertEqual((d, pid), (":101", 777))
        self.assertEqual(calls[0][0], ["Xvfb", ":101", "-screen", "0", "1920x1080x24", "-nolisten", "tcp"])
        self.assertTrue(calls[0][1]["start_new_session"])
        with self.assertRaisesRegex(RuntimeError, "owner"):
            linux_window.PrivateDisplay.start(display=":0", popen=popen, xdir=xdir)
        killed = []
        state = {"alive": True}
        self.assertTrue(linux_window.PrivateDisplay.stop(777, ":101", kill=lambda p, s: (killed.append(p), state.update(alive=False)),
                                                         alive=lambda p, d: state["alive"]))
        self.assertEqual(killed, [777])
        killed.clear()  # a pid that is not our Xvfb (any more) is never signalled
        self.assertTrue(linux_window.PrivateDisplay.stop(778, ":101", kill=lambda p, s: killed.append(p), alive=lambda p, d: False))
        self.assertEqual(killed, [])

    def test_xvfb_alive_reads_cmdline(self):
        proc = tempfile.mkdtemp()
        for pid, argv in ((10, b"Xvfb\0:101\0-screen\0"), (11, b"/usr/bin/Xvfb\0:102\0"), (12, b"bash\0:101\0")):
            os.makedirs(os.path.join(proc, str(pid)))
            with open(os.path.join(proc, str(pid), "cmdline"), "wb") as f:
                f.write(argv)
        self.assertTrue(linux_window.xvfb_alive(10, ":101", proc=proc))
        self.assertFalse(linux_window.xvfb_alive(10, ":102", proc=proc))
        self.assertTrue(linux_window.xvfb_alive(11, ":102", proc=proc))
        self.assertFalse(linux_window.xvfb_alive(12, ":101", proc=proc))
        self.assertFalse(linux_window.xvfb_alive(13, ":101", proc=proc))

    def test_private_env(self):
        self.assertEqual(linux_window.PRIVATE_ENV["MESA_VK_WSI_DEBUG"], "sw")
        self.assertIn("VK_KHR_present_wait", linux_window.PRIVATE_ENV["VKD3D_DISABLE_EXTENSIONS"].split(","))


class FakeHelper:
    """The typed helper calls game_ctl_linux uses, recorded."""

    def __init__(self):
        self.calls = []
        self.cells = {0: 0x4d58}
        self.iconic = False
        self.window = (100, 60, 1700, 960)  # before fit: a client of 1600 x 900 filling the window
        self.client = (100, 60, 1600, 900)  # x, y on the screen, width, height

    def procs(self):
        return [(32, "C:\\windows\\syswow64\\start.exe"), (340, "D:\\D2RLoader.exe"), (77, "C:\\other\\D2RLoader.exe")]

    def find(self, title, pid=0):
        self.calls.append(("find", title, pid))
        return (5000, 340, 0xea00004, 1600, 900, False) if pid == 340 else None

    def rect(self, h):
        cx, cy, cw, ch = self.client
        return {"cw": cw, "ch": ch, "cx": cx, "cy": cy, "window": self.window, "iconic": self.iconic, "visible": True}

    def pos(self, h, after, x, y, w, hh, flags):
        self.calls.append(("pos", h, after, x, y, w, hh, flags))
        self.window = (x, y, x + w, y + hh)
        self.client = (x + 1, y + 30, w - 2, hh - 31)  # a frame of 2 x 31 around the client
        return True

    def post(self, h, msg, wp, lp):
        self.calls.append(("post", h, msg, wp, lp))
        return True

    def mapvk(self, vk):
        return {0x0D: 0x1C, 0x1B: 0x01, 0x10: 0x2A}.get(vk, 0x10)

    def x11(self, h):
        return 0xea00004

    def windows(self):
        return [{"hwnd": 7, "pid": 340, "visible": True, "class": "#32770", "title": "D2RLoader"},
                {"hwnd": 8, "pid": 340, "visible": True, "class": "#32770", "title": "Error"},
                {"hwnd": 9, "pid": 999, "visible": True, "class": "#32770", "title": "D2RLoader"}]

    def buttons(self, h, push_only=False):
        return ["OK"] if push_only else ["OK", "Don't remind me again for D2R 3.4"]  # Wine: the check box is a Button

    def request(self, *f, quiet=False, check=True):
        self.calls.append(("request",) + f)
        if f[0] == "vopen":
            return ["Local\\mxl2012-testharness-input-340"], []
        if f[0] == "vget":
            return [str(self.cells.get(int(f[1]), 0))], []
        if f[0] == "vset":
            self.cells[int(f[1])] = int(f[2])
            return [f[2]], []
        if f[0] == "vtext":
            return ["1"], []
        raise AssertionError(f)

    def close(self):
        self.calls.append(("close",))

    def posts(self):
        return [c[2:] for c in self.calls if c[0] == "post"]


@unittest.skipUnless(LINUX, "the Linux window layer is installed under game_slots' Linux backend only")
class GameCtlLinux(unittest.TestCase):
    def setUp(self):
        import game_ctl
        import game_ctl_linux
        self.gc, self.gl = game_ctl, game_ctl_linux
        root = tempfile.mkdtemp()
        self.slot = os.path.join(root, "s")
        os.makedirs(os.path.join(root, "p", "pfx", "dosdevices"))
        os.makedirs(self.slot)
        os.symlink(self.slot, os.path.join(root, "p", "pfx", "dosdevices", "d:"))
        env = linux_window.SlotEnv(game_ctl.SLOT, slot_dir=self.slot, compat=os.path.join(root, "p"),
                                   proton_dir="/nonexistent/proton")
        self.ns_game_dir = game_ctl.GAME_DIR
        game_ctl.GAME_DIR = self.slot
        game_ctl_linux.install(vars(game_ctl), env=env)
        self.fake = FakeHelper()
        game_ctl_linux._HELPER = self.fake
        game_ctl_linux._DISPLAY = ":101"
        self.logs = []
        self.running = [True]
        run = os.path.join(root, "run")
        os.makedirs(run)
        self.state = {}
        for p in (patch.object(game_ctl, "log", self.logs.append), patch.object(game_ctl.time, "sleep"),
                  patch.object(game_ctl, "current_run", return_value=run),
                  patch.object(game_ctl, "load_state", side_effect=lambda: dict(self.state)),
                  patch.object(game_ctl, "save_state", side_effect=lambda st: (self.state.clear(), self.state.update(st))),
                  patch.object(game_slots, "game_pids", side_effect=lambda *a, **k: [4242] if self.running[0] else []),
                  patch.object(game_slots, "stop_prefix", return_value=True),
                  patch.object(game_slots, "wait_prefix_idle", return_value=True),
                  patch.object(game_ctl.game_slots, "foreign_game", return_value=[]),
                  # the fake helper's loader is D2RLoader.exe; the real slot may hold a renamed D2RLoader-sN.exe
                  # (game_slots.setup), which game_ctl read at import (lane linharness: the start test spun 60 s per wait)
                  patch.object(game_ctl, "LOADER_NAME", "D2RLoader.exe")):
            p.start()
        self.addCleanup(self.restore)

    def restore(self):
        patch.stopall()
        self.gc.GAME_DIR = self.ns_game_dir
        self.gl.install(vars(self.gc))

    def stop_patches(self):
        return [patch.object(self.gc, "harness_switch"), patch.object(self.gc, "restore_shared", return_value=True),
                patch.object(self.gc.game_slots, "release"), patch.object(self.gc.game_slots, "clear_launch"),
                patch.object(self.gc.game_slots, "slot_processes", return_value=[]),
                patch.object(linux_window.PrivateDisplay, "stop", return_value=True)]

    def test_installed(self):
        for name in self.gl.OVERRIDES:
            self.assertIs(getattr(self.gc, name), getattr(self.gl, name), name)
        self.assertEqual(self.gc.LOADER_LOG, os.path.join(self.slot, "d2rloader", "logs", "d2rloader.log"))
        self.assertTrue(self.gc.SAVES.endswith(os.path.join("Saved Games", "Diablo II Resurrected", "mods",
                                                            f"mxl2012-s{self.gc.SLOT}")), self.gc.SAVES)

    def test_pids_and_window_by_windows_pid(self):
        with patch.object(self.gc, "LOADER_NAME", "D2RLoader.exe"):
            self.assertEqual(self.gc.game_pids(), [340])  # C:\other is not the slot folder; start.exe is not the loader
            self.assertEqual(self.gc.find_window(), 5000)
        self.assertIn(("find", "Diablo II: Resurrected", 340), self.fake.calls)

    def test_not_running_never_asks_wine(self):
        self.running[0] = False
        self.gl._HELPER = MagicMock(name="helper")
        self.assertEqual(self.gc.game_pids(), [])
        self.assertIsNone(self.gc.find_window())
        self.assertEqual(self.gl._HELPER.method_calls, [])

    def test_no_private_display_no_helper(self):
        self.gl._HELPER, self.gl._DISPLAY = None, None
        with self.assertRaisesRegex(SystemExit, "no private display"):
            self.gl.helper()
        self.state.update(xvfb_display=":0", xvfb_pid=1)  # the owner's display is never taken from a state file
        with self.assertRaisesRegex(SystemExit, "no private display"):
            self.gl.helper()
        self.state.update(xvfb_display=":101", xvfb_pid=1)
        with patch.object(linux_window, "xvfb_alive", return_value=True):
            self.assertEqual(self.gl.display(), ":101")
            self.assertEqual(self.gl.game_env()["DISPLAY"], ":101")

    def test_fit_window(self):
        r = self.gc.fit_window(5000)
        pos = [c for c in self.fake.calls if c[0] == "pos"]
        x, y = 0, 0  # lane linfix: own private display per run, no slot cascade (slot 5's cascade spot cut the client)
        self.assertEqual(pos[0][3:], (x, y, self.gc.CLIENT_W + 40, self.gc.CLIENT_H + 80, 0x14))
        self.assertEqual(pos[1][3:], (x, y, self.gc.CLIENT_W + 2, self.gc.CLIENT_H + 31, 0x14))  # NOZORDER | NOACTIVATE
        self.assertEqual(r, (x + 1, y + 30, x + 1 + self.gc.CLIENT_W, y + 30 + self.gc.CLIENT_H))
        self.fake.iconic = True
        with self.assertRaises(RuntimeError):
            self.gc.fit_window(5000)
        self.assertFalse(self.gc.restore_noactivate(5000))

    def test_fit_window_inside_the_private_screen(self):
        """Lane linfix: at slot 5's Windows cascade spot (340, 220) a 1600 x 900 client reached past the 1920 x 1080 private
        screen (shots 1574 x 828). fit_window puts it at 0, 0 now, and logs a window that does not fit."""
        logs = []
        with patch.object(self.gc, "log", side_effect=logs.append):
            self.gc.fit_window(5000)
            self.assertFalse(any("past the private screen" in ln for ln in logs), logs)
            self.assertEqual(self.gl.offscreen(self.fake.window, self.gl.screen_size()), (0, 0))
            self.gc.fit_window(5000, 340, 220)  # the old cascade spot of slot 5
        self.assertTrue(any("past the private screen" in ln for ln in logs), logs)
        self.assertEqual(self.gl.offscreen((340, 220, 1942, 1151), (1920, 1080)), (22, 71))

    def test_screen_size_grows_for_a_large_client(self):
        self.assertEqual(self.gl.screen_size(1600, 900, "1920x1080"), (1920, 1080))
        self.assertEqual(self.gl.screen_size(1920, 1080, "1920x1080"), (1984, 1176))
        self.assertEqual(self.gl.screen_size(2560, 1440, "1920x1080"), (2624, 1536))
        self.assertEqual(self.gl.screen_size(1600, 900, "3000x2000"), (3000, 2000))
        self.assertEqual(self.gl.offscreen((0, 0, 1612, 938), (1920, 1080)), (0, 0))
        self.assertEqual(self.gl.offscreen((-5, 0, 100, 100), (1920, 1080)), (5, 0))

    def test_keys(self):
        self.gc.key("enter", "shift+a")
        posts = self.fake.posts()
        self.assertEqual(posts[0], (0x100, 0x0D, 1 | (0x1C << 16)))
        self.assertEqual(posts[1], (0x101, 0x0D, 1 | (0x1C << 16) | (1 << 30) | (1 << 31)))
        self.assertEqual([p[:2] for p in posts[2:]], [(0x100, 0x10), (0x100, 0x41), (0x101, 0x41), (0x101, 0x10)])
        self.fake.calls.clear()
        self.gc.type_text("x")
        self.assertIn((0x102, ord("x")), [p[:2] for p in self.fake.posts()])  # WM_CHAR for text fields

    def test_click_uses_block_and_messages(self):
        self.gc.click(0.5, 0.25)
        c = self.fake.cells
        self.assertEqual((c[1], c[7], c[2], c[3], c[4]), (1, 1, 800, 225, 0))
        posts = self.fake.posts()
        self.assertEqual([p[0] for p in posts], [0x200, 0x200, 0x201, 0x202])
        self.assertEqual(posts[2], (0x201, 1, (225 << 16) | 800))
        sets = [c[2:] for c in self.fake.calls if c[0] == "request" and c[1] == "vset" and c[2] == 4]
        self.assertEqual(sets, [(4, 1), (4, 0)])  # button down in the block, then up
        self.gc.click(0.1, 0.1, "right", mods=("ctrl",))
        self.assertEqual(self.fake.posts()[-2][:2], (0x204, 2))
        self.assertEqual(self.fake.cells[5], 0)  # modifiers released after the click

    def test_console(self):
        orig = self.fake.request

        def req(*f, **kw):
            if f[0] == "vget" and f[1] in (9, 10):  # the plugin answers the new sequence number, handled
                self.fake.calls.append(("request",) + f)
                return [str(self.fake.cells.get(8, 0)) if f[1] == 9 else "1"], []
            return orig(*f, **kw)
        self.fake.request = req
        self.assertTrue(self.gc.console_bg("h state"))
        self.assertIn(("request", "vtext", 64, "h state"), self.fake.calls)

    def test_notice_only_loader_dialog_of_our_pids(self):
        self.assertEqual(self.gl.notice_windows([340]), [7])
        self.assertTrue(any("check box" in ln or "all buttons" in ln for ln in self.logs), self.logs)
        w = self.gl.notice_watch(started=0)
        with patch.object(self.gl.loader_notice, "log_has_notice", return_value=True), \
                patch.object(w, "_clock", side_effect=[0.0, 1.0]):
            self.assertIsNone(w.poll([340]))   # first seen: let it settle
            self.assertIn("answered", w.poll([340]))
        self.assertIn(("post", 7, 0x0400 + 102, 1, 0), self.fake.calls)

    def test_stop_closes_window_helper_display_and_waits(self):
        post = self.fake.post

        def post_close(h, msg, wp, lp):  # the game ends on WM_CLOSE
            if msg == 0x10:
                self.running[0] = False
            return post(h, msg, wp, lp)
        self.fake.post = post_close
        ps = self.stop_patches()
        for p in ps:
            p.start()
        self.gc.stop()
        self.assertIn(("post", 5000, 0x10, 0, 0), self.fake.calls)
        self.assertIn(("close",), self.fake.calls)
        game_slots.stop_prefix.assert_not_called()  # the game closed by itself
        game_slots.wait_prefix_idle.assert_called_once()
        self.gc.harness_switch.assert_called_with(False)
        self.gc.game_slots.release.assert_called_once()
        self.assertIsNone(self.gl._HELPER)

    def test_stop_forces_only_our_prefix(self):
        ps = self.stop_patches()
        for p in ps:
            p.start()
        with patch.object(self.gl.time, "time", side_effect=[0.0] + [100.0] * 50):
            self.gc.stop()
        game_slots.stop_prefix.assert_called_once_with(self.gc.SLOT)
        self.gc.game_slots.release.assert_called_once()

    def test_stop_ends_the_runs_xvfb(self):
        self.running[0] = False
        self.state.update(xvfb_display=":101", xvfb_pid=777)
        ps = self.stop_patches()
        for p in ps:
            p.start()
        self.gc.stop()
        linux_window.PrivateDisplay.stop.assert_called_once_with(777, ":101")
        self.assertNotIn("xvfb_display", self.state)

    def test_foreground_refused(self):
        with patch.object(self.gc, "BG", False):
            for call in (lambda: self.gc.click(0.5, 0.5), lambda: self.gc.press("esc"), lambda: self.gc.grab_client(5000),
                         lambda: self.gc.focus(5000)):
                with self.assertRaises(SystemExit):
                    call()
        self.assertEqual(self.fake.posts(), [])

    def test_never_activates_or_raises(self):
        """Every SetWindowPos keeps SWP_NOACTIVATE and either SWP_NOZORDER or HWND_BOTTOM with NOSIZE | NOMOVE; no
        activation message is ever posted."""
        self.gc.fit_window(5000)
        self.gc._keep_out_of_front(None, wait=1)
        pos = [c for c in self.fake.calls if c[0] == "pos"]
        self.assertGreaterEqual(len(pos), 3)
        for _, _, after, _, _, _, _, fl in pos:
            self.assertTrue(fl & 0x0010, pos)                                       # SWP_NOACTIVATE
            self.assertTrue(fl & 0x0004 or (after == 1 and fl & 0x3 == 0x3), pos)  # NOZORDER, or to the bottom only
        msgs = {c[2] for c in self.fake.calls if c[0] == "post"}
        self.assertFalse(msgs & {0x0006, 0x0007, 0x0086, 0x001C})  # WM_ACTIVATE, WM_SETFOCUS, WM_NCACTIVATE, WM_ACTIVATEAPP

    def test_wctl_source_has_no_activation(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wctl", "wctl.c")).read()
        code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("//"))
        for bad in ("SetForegroundWindow", "SetActiveWindow", "SetFocus", "BringWindowToTop", "ShowWindow", "SendInput",
                    "SetCursorPos", "keybd_event", "mouse_event", "AttachThreadInput", "SwitchToThisWindow", "HWND_TOP"):
            self.assertNotIn(bad, code, bad)
        self.assertIn("| SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)", code)
        self.assertIn("if (after != HWND_BOTTOM) { fl |= SWP_NOZORDER;", code)

    def test_capture_private_display_only(self):
        from PIL import Image
        self.fake.client = (0, 0, 1600, 900)
        img = Image.new("RGB", (1602, 931), (9, 9, 9))
        img.paste((200, 0, 0), (1, 30, 1601, 930))
        with patch.object(linux_window, "xcapture", return_value=img) as xc:
            got = self.gc.grab_client(5000)
        xc.assert_called_once_with(0xea00004, display=":101")
        self.assertEqual(got.size, (1600, 900))
        self.assertEqual(got.getextrema(), ((200, 200), (0, 0), (0, 0)))
        self.fake.client = (5, 7, 100, 50)  # no window pixmap: the private root, cut to the client
        with patch.object(linux_window, "xcapture", side_effect=RuntimeError("no composite")), \
                patch.object(linux_window, "root_capture", return_value=img) as rc:
            self.gc.grab_client(5000)
        rc.assert_called_once_with(":101", box=(5, 7, 105, 57))

    def test_launch_on_private_display(self):
        with patch.object(game_slots, "launch", return_value=MagicMock()) as gl:
            self.gl.launch(["-mod", "mxl2012"])
        (n, args), kw = gl.call_args
        self.assertEqual((n, args), (self.gc.SLOT, ["-mod", "mxl2012"]))
        self.assertEqual(kw["extra_env"], dict(linux_window.PRIVATE_ENV, DISPLAY=":101"))
        self.assertEqual(kw["log_dir"], self.gc.current_run())

    def test_game_slots_launch_takes_the_private_env(self):
        with patch.object(game_slots, "ensure_drive"), patch.object(game_slots, "apply_launch_settings"), \
                patch.object(game_slots, "apply_profile", return_value=("test", {})), \
                patch.object(game_slots.subprocess, "Popen") as po:
            game_slots.launch(self.gc.SLOT, ["-mod", "mxl2012"], extra_env={"DISPLAY": ":101", "MESA_VK_WSI_DEBUG": "sw"})
        env = po.call_args[1]["env"]
        self.assertEqual((env["DISPLAY"], env["MESA_VK_WSI_DEBUG"]), (":101", "sw"))
        self.assertEqual(env["WINEPREFIX"], game_slots.prefix_dir(self.gc.SLOT))

    def test_start_watches_owner_focus_and_stop_writes_it(self):
        self.running[0] = False
        self.gl._DISPLAY = None
        watch = MagicMock(name="watch")
        watch.start.return_value = watch
        watch.before, watch.polls, watch.changes, watch.grabs = 0xa600030, 50, [], []
        watch.stop.return_value = "focus kept: _NET_ACTIVE_WINDOW never went to a game window (50 polls ...)"

        def started(*a, **k):
            self.running[0] = True
            return MagicMock()
        post = self.fake.post

        def post_close(h, msg, wp, lp):
            if msg == 0x10:
                self.running[0] = False
            return post(h, msg, wp, lp)
        self.fake.post = post_close
        ps = self.stop_patches() + [
            patch.object(game_slots, "FocusWatch", return_value=watch) , patch.object(game_slots, "launch", side_effect=started),
            patch.object(linux_window.PrivateDisplay, "start", return_value=(":101", 777)),
            patch.object(linux_window, "xvfb_alive", return_value=True),
            patch.object(self.gc, "take_lock", return_value=True), patch.object(self.gc, "wait_log", return_value=True),
            patch.object(self.gc, "snapshot_marks"), patch.object(self.gc.slot_share, "begin", return_value="begin"),
            patch.object(self.gc.slot_share, "launch_args", return_value=["-mod", "mxl2012"])]
        for p in ps:
            p.start()
        self.assertTrue(self.gc.start())
        game_slots.FocusWatch.assert_called_once_with(self.gc.SLOT, display=linux_window.OWNER_DISPLAY)
        self.assertEqual(self.state["xvfb_display"], ":101")
        self.gc.stop()
        watch.stop.assert_called_once()
        with open(os.path.join(self.gc.current_run(), "focus.json")) as f:
            rep = json.load(f)
        self.assertEqual((rep["polls"], rep["grabs"]), (50, []))
        self.assertTrue(any(ln.startswith("owner focus: focus kept") for ln in self.logs), self.logs)

    # ---- lane viewerlinux: game_ctl.PRE_LAUNCH runs after the slot snapshot and before the launch

    def _start_patches(self, order):
        def started(*a, **k):
            order.append("launch")
            self.running[0] = True
            return MagicMock()
        watch = MagicMock(name="watch")
        watch.start.return_value = watch
        return self.stop_patches() + [
            patch.object(game_slots, "FocusWatch", return_value=watch), patch.object(game_slots, "launch", side_effect=started),
            patch.object(linux_window.PrivateDisplay, "start", side_effect=lambda *a, **k: order.append("display") or (":101", 777)),
            patch.object(linux_window, "xvfb_alive", return_value=True),
            patch.object(self.gc, "take_lock", return_value=True), patch.object(self.gc, "wait_log", return_value=True),
            patch.object(self.gc, "snapshot_marks"),
            patch.object(self.gc.slot_share, "begin", side_effect=lambda *a: order.append("snapshot") or "begin"),
            patch.object(self.gc.slot_share, "launch_args", return_value=["-mod", "mxl2012"])]

    def test_pre_launch_runs_after_snapshot_before_launch(self):
        self.running[0] = False
        self.gl._DISPLAY = None
        order = []
        for p in self._start_patches(order):
            p.start()

        def lay():
            order.append("lay")
            return "2 files laid"
        with patch.object(self.gc, "PRE_LAUNCH", [lay]):
            self.assertTrue(self.gc.start())
        self.assertEqual(order, ["snapshot", "lay", "display", "launch"])
        self.assertIn("pre-launch lay: 2 files laid", self.logs)

    def test_pre_launch_error_stops_the_launch_and_restores(self):
        self.running[0] = False
        self.gl._DISPLAY = None
        order = []
        for p in self._start_patches(order):
            p.start()

        def bad():
            raise RuntimeError("plan not laid")
        with patch.object(self.gc, "PRE_LAUNCH", [bad]):
            self.assertFalse(self.gc.start())
        self.assertEqual(order, ["snapshot"])          # no display, no launch
        self.gc.restore_shared.assert_called_once()
        self.gc.game_slots.release.assert_called_once()
        self.assertTrue(any("launch failed: plan not laid" in ln for ln in self.logs), self.logs)

    # ---- lane linharness: harness words, slot logs kept before the restore, post_message

    def test_harness_switch_words_unchanged(self):
        folder = os.path.join(self.slot, "mods", "mxl2012", "d2rloader", "plugins")
        os.makedirs(folder)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MXL_HARNESS_WORDS", None)
            self.gc.harness_switch(True)
            self.assertNotIn("MXL_HARNESS_WORDS", os.environ)  # the env is put back
        with open(os.path.join(folder, "mxl2012-testharness.txt")) as f:
            self.assertEqual(f.read(), f"volserial tag=s{self.gc.SLOT}")  # no nofakefocus: the plugin's default is off
        with patch.dict(os.environ, {"MXL_HARNESS_WORDS": "volserial diag"}):
            self.gc.harness_switch(True)
            self.assertEqual(os.environ["MXL_HARNESS_WORDS"], "volserial diag")
        with open(os.path.join(folder, "mxl2012-testharness.txt")) as f:
            self.assertEqual(f.read(), "volserial diag")
        self.gc.harness_switch(False)
        self.assertFalse(os.path.exists(os.path.join(folder, "mxl2012-testharness.txt")))

    def test_stop_keeps_slot_logs_and_points_logscan_at_them(self):
        self.running[0] = False
        files = {"d2rloader/logs/d2rloader.log": "D2R startup complete.\n",
                 "mods/mxl2012/d2rloader/logs/mxl2012-core.log": "mxl2012-core loaded\n",
                 "mods/mxl2012/d2rloader/plugins/mxl2012-testharness-console.txt": "h: state OK\n",
                 "mods/mxl2012/d2rloader/plugins/mxl2012-testharness-diag-340.log": "x\n",
                 "d2rloader/crashes/crash.log": "c\n", "mods/mxl2012/d2rloader/plugins/mxl2012-core.dll": "dll"}
        for rel, text in files.items():
            p = os.path.join(self.slot, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(text)
        restored = []
        ps = self.stop_patches()
        for p in ps:
            p.start()
        self.gc.restore_shared.side_effect = lambda: restored.append(os.path.exists(self.gc.LOADER_LOG)) or True
        self.gc.stop()
        kept = os.path.join(self.gc.current_run(), "slot-logs-1")
        for rel in files:
            self.assertEqual(os.path.exists(os.path.join(kept, *rel.split("/"))), not rel.endswith(".dll"), rel)
        self.assertEqual(self.gc.LOADER_LOG, os.path.join(kept, "d2rloader", "logs", "d2rloader.log"))
        self.assertEqual(self.gc.CRASH_DIR, os.path.join(kept, "d2rloader", "crashes"))
        self.assertEqual(restored, [True])  # copied before the slot restore
        self.assertIn("D2R startup complete.", self.gc._read_from(self.gc.LOADER_LOG, 0))
        self.gl.live_logs()  # start() points them back at the slot
        self.assertEqual(self.gc.LOADER_LOG, os.path.join(self.slot, "d2rloader", "logs", "d2rloader.log"))

    def test_post_message_through_helper(self):
        self.assertTrue(self.gc.post_message(5000, 0x201, 1, 0x10002))
        self.assertIn(("post", 5000, 0x201, 1, 0x10002), self.fake.calls)
        self.assertEqual(self.gc.client_size(5000), (1600, 900))


class HarnessWords(unittest.TestCase):
    def test_no_linux_word_wrapper(self):
        import game_ctl_linux as gl
        self.assertNotIn("harness_switch", gl.OVERRIDES)  # game_ctl's own words, fake focus is off in the plugin
        self.assertFalse(hasattr(gl, "harness_words"))


if __name__ == "__main__":
    unittest.main()
