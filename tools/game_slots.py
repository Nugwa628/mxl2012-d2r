#!/usr/bin/env python
"""Game slots: up to five D2R test instances side by side (docs/testing.md, "Parallel slots").

A slot is a full D2R 3.3 build 93847 folder with D2RLoader and the D2R-XL 2012 mod, its own save folder and its own
run lock:

  slot 1  C:\\Program Files (x86)\\Diablo II Resurrected          saves  Saved Games\\Diablo II Resurrected\\mods\\mxl2012-s1
  slot 2  D:\\D2R-93847                                            saves  ...\\mods\\mxl2012-s2
  slot 3  D:\\D2R-93847-s3                                         saves  ...\\mods\\mxl2012-s3
  slot 4  D:\\D2R-93847-s4                                         saves  ...\\mods\\mxl2012-s4
  slot 5  D:\\D2R-93847-s5                                         saves  ...\\mods\\mxl2012-s5

Slots 4 and 5 (owner-approved 2026-10-28, GPU permitting) are copies of slot 2's folder made by the coordinator, set up and
run exactly like slot 3. Other tools sharing the lock folder may not know them (they never take game.lock.4 / .5):
harmless, nothing of theirs lives there. A slot whose folder (or its D2RLoader.exe) does not exist is shown as MISSING by `status`
and refused by every tool that would use it (require_present), so the code works before the copies exist.

Slot 1 is the PC owner's own Battle.net install (approved for this project's tests by the owner on 2026-10-28; another
mod's tests use it as their slot 1 too). It has the safety of slots 2 to 5 plus three rules of its own (OWNER_SLOTS): its runs use the
plain D2RLoader.exe (no renamed copy is made in the owner's folder), a game running there that no run of ours started
(the owner playing) is never attached to, closed or killed (foreign_game), and a write the folder refuses (Program Files:
writes may need administrator rights) ends the tool with a clear message (need_write); nothing is ever elevated or retried
another way. There is no default slot: each command needs --slot N or env MXL_SLOT=N (require_slot refuses anything
but 1 to 5). The mod folder is mods\\mxl2012; the other mods' folders and save folders (machine.json
protected_mod_folders / protected_save_folders, tools/localconfig.py) are never touched.

Machine-local safety settings: every command (and every tool that uses the slots: game_ctl, install_mod, slot_share,
release_install, parallel_smoke) refuses to run while machine.json lacks shared_lock_dir, protected_mod_folders or
protected_save_folders (require_machine), so a checkout on a machine without them never touches a slot.

Folders can be moved with env MXL_SLOTn_DIR (MXL_SLOT1_DIR ... MXL_SLOT5_DIR). The run locks are directories game.lock.<n>
under LOCK_ROOT, the folder shared with the other tools of this machine (machine.json shared_lock_dir; env MXL_LOCKS
overrides), so all of them queue on the same game.lock.N. Slot 1 also honours the old single `game.lock` other tools
still take: a lock is held when either folder exists, and taking it makes both. A lock holds an
`owner.txt` (`<owner> pid=<pid> <time>`); a lock without that file (made by hand with mkdir) is respected as "someone
holds it". Run output (run folders, logs, screenshots) goes to RUNS (default <repo>/work/runs, env MXL_RUNS), never into
the shared lock folder.

Linux (docs/testing.md "Linux slots"): the backend is picked by platform (BACKEND; env MXL_SLOT_BACKEND=windows|linux
overrides, for tests). On Linux only the slots of LINUX_SLOTS exist (2, 5, 6 and 7; temporary 10 and up only with env
MXL_EXTRA_SLOTS; <locks>/slots.json says which numbers are ours, another project's number is refused): each is a D2R 3.4 + D2RLoader folder
(default /d2work/slots/sN) run under Proton Experimental in its own prefix (STEAM_COMPAT_DATA_PATH, default
/d2work/prefixes/sN; Wine prefix <that>/pfx, drive D: -> the slot folder), saves in the prefix's Saved Games\\...\\mods\\
mxl2012-sN. Slots 1, 3 and 4 are refused there with a clear message. Overrides (one place, linux_slot()): env
MXL_SLOTn_DIR / MXL_SLOTn_COMPAT / MXL_SLOTn_SNAPSHOT, machine.json "linux_slots" {"N": {"dir", "compat", "snapshot"}}
and "proton_dir", env MXL_PROTON. Processes are found in /proc (a Wine process of the slot's prefix whose command line
names the image); the run's snapshot is the whole slot folder (tools/slot_share.py). Functions for the window layer
(game_ctl): slot_dir, compat_dir, prefix_dir, save_root, wine_env, proton_cmd, wine_cmd, windows_path, ensure_drive,
game_pids, prefix_pids, launch, stop_prefix, wait_prefix_idle, and for the owner's no-focus rule apply_launch_settings
and FocusWatch (the run's _NET_ACTIVE_WINDOW must never become a game window).

Shared seats (lane slotcap, 2026-11-21; <locks>/README.md, agreed with D2RGS): with <locks>/budget.json
{"max_games": N} every slot lock comes with a seat game.seat.K (K = 1..N, owner.txt `<owner> pid=<pid> <time> slot=<n>`):
taken first, the lock after it (a failure between gives the seat back), released after the lock; stale when its pid is
gone, pid 0 never. No free seat: acquire() waits up to seat_wait / env MXL_SEAT_WAIT seconds (default 0), then refuses.
Without budget.json nothing changes. `status` shows the budget and the seats held.

Commands (py -3 tools/game_slots.py ...):
  status                    per slot: folder, running processes, lock, save folder
  setup [N ...]             (default slots 2 to 5, a missing one reported and skipped; slot 1 only when named; a named
                            missing slot exits 1) make slots ready: modinfo savepath of mods\\mxl2012, our save folder,
                            the renamed loader copy D2RLoader-sN.exe when missing (slots 2 to 5 only). The slot's game-wide d2rloader\\config is shared with the other mod and is NOT edited: every run
                            picks the mod on the loader's command line (tools/slot_share.py)
  lock N [OWNER]            take the lock of slot N (exit 1 when held; a missing slot is refused)
  unlock N [OWNER]          release it (only the owner, or with OWNER omitted a stale one); a pending snapshot of the
                            shared files (tools/slot_share.py) is restored first, and the lock stays when that fails
  install [N ...]           run tools/install_mod.py for those slots (default: slots 2 to 5 that exist; a named missing slot is refused)
  profile N [test|visual]   Linux: write a graphics profile (tools/slot_profiles) into slot N's Settings.json now (default
                            env MXL_PROFILE, else test); every launch writes it again (MXL_PROFILE / --profile)
"""
import collections
import contextlib
import ctypes
import fnmatch
import ctypes.wintypes as wt
import datetime
import json
import os
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import localconfig  # noqa: E402  (machine.json: shared lock folder, protected folders)
import winapi  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MACHINE = localconfig.machine()
# Lock directories are shared with the other tools of this machine (the same game.lock.N files); run output stays in this
# repo. Empty when machine.json has no shared_lock_dir: then lock_paths and every command refuse (require_machine).
LOCK_ROOT = os.environ.get("MXL_LOCKS") or MACHINE.get("shared_lock_dir") or ""
PROTECTED_MODS = localconfig.machine_list("protected_mod_folders")   # other mods' folders inside a slot's mods folder
PROTECTED_SAVES = localconfig.machine_list("protected_save_folders")  # their save folders (fnmatch patterns)
if os.environ.get("MXL_LOCKS"):
    print(f"MXL_LOCKS override: {LOCK_ROOT}", file=sys.stderr)
RUNS = os.environ.get("MXL_RUNS") or os.path.join(REPO, "work", "runs")
SLOTS = (1, 2, 3, 4, 5)
DEFAULTS = {1: r"C:\Program Files (x86)\Diablo II Resurrected", 2: r"D:\D2R-93847", 3: r"D:\D2R-93847-s3",
            4: r"D:\D2R-93847-s4", 5: r"D:\D2R-93847-s5"}  # 4 and 5: copies of slot 2, may not exist yet
# The owner's own game (slot 1): plain D2RLoader.exe, a game we did not start is never touched (foreign_game), the
# legacy game.lock counts as its lock too.
OWNER_SLOTS = (1,)
LEGACY_LOCK = {1: "game.lock"}  # the old single lock of slot 1 other tools still take
DEFAULT_SET = tuple(n for n in SLOTS if n not in OWNER_SLOTS)  # `setup` / `install` / install_mod --slot all / parallel_smoke
# (`install` and the tools: only those that exist, present_set): slot 1 only by name
SAVE_ROOT = os.path.join(os.environ.get("USERPROFILE", ""), r"Saved Games\Diablo II Resurrected\mods")
MOD = "mxl2012"

# ---------------------------------------------------------------- backend (Windows folders, or Linux slots under Proton)

WINDOWS_SLOTS, WINDOWS_OWNER_SLOTS = SLOTS, OWNER_SLOTS
LINUX_SLOTS = (2, 5, 6, 7)  # the slots that exist on Linux (MXL's numbers in <locks>/slots.json); 1, 3 and 4 do not
# Temporary measurement slots (lane slotcap: copies of slot 5 numbered 10 and up) exist only while env MXL_EXTRA_SLOTS
# names them ("10,11"); slots.json lists them as "MXL (temporary, slotcap measurement)" for that time.
EXTRA_LINUX_SLOTS = tuple(int(x) for x in os.environ.get("MXL_EXTRA_SLOTS", "").replace(" ", "").split(",") if x.isdigit())
LINUX_SLOT_ROOT = "/d2work/slots"  # defaults; env and machine.json override them per slot (linux_slot)
LINUX_PREFIX_ROOT = "/d2work/prefixes"
PROTON_DEFAULT = os.path.join("~", ".local", "share", "Steam", "steamapps", "common", "Proton - Experimental")
# inside the prefix: Saved Games of Proton's user (steamuser), the same layout as the Windows SAVE_ROOT
PREFIX_SAVES = ("drive_c", "users", "steamuser", "Saved Games", "Diablo II Resurrected", "mods")
GAME_DRIVE = "d:"  # the slot folder is drive D: of its prefix (dosdevices/d: -> slot folder)
BACKEND = None
LINUX = False


def use_backend(name=None):
    """Pick the slot backend: "windows" (the folders of DEFAULTS, Win32 process calls) or "linux" (LINUX_SLOTS under
    Proton, /proc). None: env MXL_SLOT_BACKEND, else by platform. Sets SLOTS, OWNER_SLOTS and DEFAULT_SET; returns the name."""
    global BACKEND, LINUX, SLOTS, OWNER_SLOTS, DEFAULT_SET
    name = name or os.environ.get("MXL_SLOT_BACKEND") or ("linux" if sys.platform.startswith("linux") else "windows")
    if name not in ("windows", "linux"):
        raise SystemExit(f"MXL_SLOT_BACKEND={name!r}: windows or linux")
    BACKEND, LINUX = name, name == "linux"
    SLOTS = (LINUX_SLOTS + EXTRA_LINUX_SLOTS) if LINUX else WINDOWS_SLOTS
    OWNER_SLOTS = () if LINUX else WINDOWS_OWNER_SLOTS
    DEFAULT_SET = tuple(n for n in SLOTS if n not in OWNER_SLOTS)
    return name


@contextlib.contextmanager
def backend(name):
    """Use backend `name` (also for tools started from here: env MXL_SLOT_BACKEND) and restore the previous one after.
    The unit tests of the Windows slot rules run under the Windows backend on every platform."""
    old_env, old = os.environ.get("MXL_SLOT_BACKEND"), BACKEND
    os.environ["MXL_SLOT_BACKEND"] = name
    use_backend(name)
    try:
        yield
    finally:
        if old_env is None:
            os.environ.pop("MXL_SLOT_BACKEND", None)
        else:
            os.environ["MXL_SLOT_BACKEND"] = old_env
        use_backend(old)


use_backend()


def require_machine(tool="game_slots"):
    """Exits unless machine.json has the slot safety keys (shared lock folder, protected mod and save folders)."""
    return localconfig.require_machine(tool=tool)


def protected(name, saves=False):
    """True when `name` is another mod's folder (or, saves=True, its save folder) that no tool may write."""
    pats = PROTECTED_SAVES if saves else PROTECTED_MODS
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in pats)


def require_slot(n):
    """The slot number as an int; exits with an error for a number that is no slot of this backend (Windows 1 to 5,
    Linux SLOTS) or that <locks>/slots.json gives to another project."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise SystemExit(f"no game slot given ({n!r}): pass --slot N or set MXL_SLOT")
    if not LINUX and n not in WINDOWS_SLOTS:
        raise SystemExit(f"game slot {n} refused: only slots 1 to 5 exist")
    if LINUX and n not in SLOTS:
        raise SystemExit(f"game slot {n} refused: it does not exist on Linux (only slots "
                         f"{', '.join(map(str, SLOTS))}, D2R under Proton; slots 1, 3 and 4 are Windows folders)")
    other = slot_project(n) if LINUX else None  # slots.json numbers the Linux slots (/d2work/slots/sN)
    if other and not other.upper().startswith("MXL"):
        raise SystemExit(f"game slot {n} refused: slots.json gives it to {other}")
    return n


def env_slot():
    """The slot of env MXL_SLOT, refused unless 1 to 5. There is no default: an unset MXL_SLOT is an error."""
    return require_slot(os.environ.get("MXL_SLOT"))


def slot_dir(n):
    require_slot(n)
    if LINUX:
        return linux_slot(n)["dir"]
    return os.environ.get(f"MXL_SLOT{n}_DIR", DEFAULTS[n])


def linux_slot(n):
    """The Linux slot table entry of slot N, all paths: dir (the game folder, drive D:), compat (STEAM_COMPAT_DATA_PATH),
    prefix (the Wine prefix, compat/pfx), snapshot (the run snapshot folder of tools/slot_share.py). Defaults under
    LINUX_SLOT_ROOT / LINUX_PREFIX_ROOT; machine.json "linux_slots" {"N": {...}} and env MXL_SLOTn_DIR / _COMPAT /
    _SNAPSHOT override them (env wins)."""
    n = require_slot(n)
    if n not in LINUX_SLOTS + EXTRA_LINUX_SLOTS:
        raise SystemExit(f"game slot {n} is not a Linux slot")
    cfg = (MACHINE.get("linux_slots") or {}).get(str(n)) or {}
    d = {"dir": os.path.join(LINUX_SLOT_ROOT, f"s{n}"), "compat": os.path.join(LINUX_PREFIX_ROOT, f"s{n}"),
         "snapshot": os.path.join(LINUX_SLOT_ROOT, f".snap-s{n}")}
    for k in d:
        d[k] = os.path.expanduser(os.environ.get(f"MXL_SLOT{n}_{k.upper()}") or cfg.get(k) or d[k])
    d["prefix"] = os.path.join(d["compat"], "pfx")
    return d


def present(n, game=None):
    """The slot's folder holds a D2RLoader.exe (game: the folder to check instead of slot_dir(n))."""
    require_slot(n)
    return os.path.isfile(os.path.join(game or slot_dir(n), "D2RLoader.exe"))


def missing_note(n, game=None):
    g = game or slot_dir(n)
    return f"{g} {'does not exist' if not os.path.isdir(g) else 'has no D2RLoader.exe'}"


def require_present(n, what="", game=None):
    """The slot number; exits with a clear message when its folder or D2RLoader.exe is missing (slots 4 and 5 before the
    coordinator copied slot 2's folder there, a moved or unplugged drive). Nothing is created or locked before."""
    n = require_slot(n)
    if not present(n, game):
        raise SystemExit(f"{what + ': ' if what else ''}game slot {n} is missing: {missing_note(n, game)} "
                         f"(copy a full D2R 93847 + D2RLoader folder there, then `py -3 tools/game_slots.py setup {n}`)")
    return n


def present_set():
    """The slots of DEFAULT_SET that exist (the default of install / install_mod --slot all / parallel_smoke)."""
    return [n for n in DEFAULT_SET if present(n)]


def save_name(n):
    """The mod's save folder name inside Saved Games\\Diablo II Resurrected\\mods (mxl2012-sN)."""
    return f"{MOD}-s{require_slot(n)}"


def save_dir(n):
    if protected(save_name(n), saves=True):
        raise SystemExit(f"save folder {save_name(n)} is protected (machine.json): refused")
    return os.path.join(save_root(n), save_name(n))


def save_root(n):
    """The folder holding the mods' save folders for slot N: SAVE_ROOT on Windows, the prefix's
    drive_c/users/steamuser/Saved Games/Diablo II Resurrected/mods on Linux."""
    if LINUX:
        return os.path.join(prefix_dir(n), *PREFIX_SAVES)
    require_slot(n)
    return SAVE_ROOT


def mod_dir(n):
    if protected(MOD):
        raise SystemExit(f"mod folder {MOD} is protected (machine.json): refused")
    return os.path.join(slot_dir(n), "mods", MOD)


def slot_of_game_dir(game):
    g = os.path.normcase(os.path.abspath(game))
    for n in SLOTS:
        if os.path.normcase(os.path.abspath(slot_dir(n))) == g:
            return n
    return None


# ---------------------------------------------------------------- processes

def _k32_setup(k):
    k.OpenProcess.restype = ctypes.c_void_p
    k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k.CloseHandle.argtypes = [ctypes.c_void_p]


_k32 = winapi.Dll("kernel32", _k32_setup)  # loaded on first use: the pure slot/lock logic imports (and is tested) off Windows


class _PE(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", wt.LONG), ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]


def image_path(pid):
    h = _k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = wt.DWORD(1024)
        _k32.QueryFullProcessImageNameW(ctypes.c_void_p(h), 0, buf, ctypes.byref(n))
        return buf.value
    finally:
        _k32.CloseHandle(h)


ALL_IMAGES = ("d2rloader.exe", "d2r.exe") + tuple(f"d2rloader-s{n}.exe" for n in WINDOWS_SLOTS if n not in WINDOWS_OWNER_SLOTS)


def loader_name(game):
    """Slots 2 to 5 run a renamed copy of the loader (D2RLoader-sN.exe), made by `setup`. Older tools that look for
    every D2RLoader.exe (to wait for it, close it or kill it) then never see the test instances of other lanes, and
    the instances never see theirs. Slot 1 (the owner's folder) runs the plain D2RLoader.exe, as the other mod's runs do:
    no copy is written into it."""
    n = slot_of_game_dir(game)
    alt = f"D2RLoader-s{n}.exe"
    return alt if n and n not in OWNER_SLOTS and os.path.exists(os.path.join(game, alt)) else "D2RLoader.exe"


def processes(names=ALL_IMAGES):
    """[(pid, exe name, full image path)] of processes with these image names (Linux: Wine processes found in /proc, the
    path mapped to the Linux file through the prefix's drive letters; neither backend available: none)."""
    if LINUX:
        return linux_processes(names)
    if not winapi.available():
        return []
    snap = _k32.CreateToolhelp32Snapshot(2, 0)
    out = []
    pe = _PE()
    pe.dwSize = ctypes.sizeof(_PE)
    ok = _k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(pe))
    while ok:
        if pe.szExeFile.lower() in names:
            out.append((pe.th32ProcessID, pe.szExeFile, image_path(pe.th32ProcessID)))
        ok = _k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(pe))
    _k32.CloseHandle(ctypes.c_void_p(snap))
    return out


def under(path, folder):
    p, f = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return p.startswith(f.rstrip(os.sep) + os.sep)  # os.sep: "\\" on Windows (normcase made every "/" one), "/" on Linux


def slot_processes(game, names=ALL_IMAGES):
    """Processes whose image lives in this game folder."""
    return [(pid, nm) for pid, nm, path in processes(names) if path and under(path, game)]


def pid_alive(pid):
    if LINUX:
        return os.path.isdir(os.path.join(PROC, str(int(pid))))
    if not winapi.available():
        return False
    h = _k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = wt.DWORD()
    _k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
    _k32.CloseHandle(ctypes.c_void_p(h))
    return code.value == 259  # STILL_ACTIVE


# ---------------------------------------------------------------- Linux: /proc, Proton, the slot's prefix

PROC = "/proc"


def _read(path, mode="rb"):
    try:
        with open(path, mode) as f:
            return f.read()
    except OSError:  # gone, or another user's process
        return None


def proc_info(pid, proc=None):
    """(argv list, environ dict) of a Linux process, or None when it is gone or not readable."""
    base = os.path.join(proc or PROC, str(pid))
    cmd, env = _read(os.path.join(base, "cmdline")), _read(os.path.join(base, "environ"))
    if cmd is None or env is None:
        return None
    argv = [a.decode("utf-8", "replace") for a in cmd.split(b"\0") if a]
    envd = {}
    for kv in env.split(b"\0"):
        k, eq, v = kv.partition(b"=")
        if eq:
            envd[k.decode("utf-8", "replace")] = v.decode("utf-8", "replace")
    return argv, envd


def unix_path(prefix, winpath):
    """The Linux path of a Windows path ("D:\\D2R.exe") inside a Wine prefix (its dosdevices drive links), or "" when the
    drive is not mapped. Paths without a drive letter give ""."""
    if len(winpath) < 3 or winpath[1] != ":" or winpath[2] not in "\\/":
        return ""
    drive = os.path.join(prefix, "dosdevices", winpath[0].lower() + ":")
    if not os.path.exists(drive):
        return ""
    root = os.path.realpath(drive)
    rest = [p for p in winpath[3:].replace("\\", "/").split("/") if p]
    return os.path.join(root, *rest)


def wine_image(argv):
    """The Windows image path of a Wine process: Wine sets argv[0] of a program's process to its Windows path
    (e.g. D:\\D2RLoader.exe); "" for anything else."""
    a0 = argv[0] if argv else ""
    return a0 if len(a0) > 2 and a0[1] == ":" else ""


def linux_processes(names=ALL_IMAGES, proc=None):
    """[(pid, exe name, Linux image path)] of the Wine processes with these image names (any prefix)."""
    out = []
    root = proc or PROC
    try:
        pids = [int(d) for d in os.listdir(root) if d.isdigit()]
    except OSError:
        return []
    for pid in sorted(pids):
        info = proc_info(pid, proc)
        if not info:
            continue
        argv, env = info
        img = wine_image(argv)
        exe = img.replace("/", "\\").rsplit("\\", 1)[-1]
        if not img or exe.lower() not in names or not env.get("WINEPREFIX"):
            continue
        out.append((pid, exe, unix_path(env["WINEPREFIX"], img)))
    return out


def compat_dir(n):
    """STEAM_COMPAT_DATA_PATH of Linux slot N (Proton's folder; the Wine prefix is its pfx)."""
    return linux_slot(n)["compat"]


def prefix_dir(n):
    """The Wine prefix (WINEPREFIX) of Linux slot N."""
    return linux_slot(n)["prefix"]


def prefix_pids(n, proc=None):
    """Linux pids of every process running in slot N's prefix (wineserver, services, the game ...)."""
    want = os.path.realpath(prefix_dir(n))
    out = []
    root = proc or PROC
    for d in (os.listdir(root) if os.path.isdir(root) else []):
        if d.isdigit():
            info = proc_info(int(d), proc)
            if info and info[1].get("WINEPREFIX") and os.path.realpath(info[1]["WINEPREFIX"]) == want:
                out.append(int(d))
    return sorted(out)


def game_pids(n, names=ALL_IMAGES):
    """Linux pids of the game processes (D2RLoader*.exe, D2R.exe) of slot N."""
    return [pid for pid, _ in slot_processes(slot_dir(n), names)]


def proton_dir():
    """Proton Experimental's folder (env MXL_PROTON, machine.json proton_dir, else Steam's default)."""
    return os.path.expanduser(os.environ.get("MXL_PROTON") or MACHINE.get("proton_dir") or PROTON_DEFAULT)


def steam_dir():
    return os.path.expanduser(os.environ.get("STEAM_COMPAT_CLIENT_INSTALL_PATH") or os.path.join("~", ".local", "share", "Steam"))


def wine_env(n, base=None, log_dir=None):
    """The environment for a Proton / Wine process in slot N's prefix (a copy of `base`, default os.environ). log_dir:
    Proton's own log (PROTON_LOG) goes there; else WINEDEBUG=-all and no Proton log."""
    env = dict(os.environ if base is None else base)
    env.update(STEAM_COMPAT_DATA_PATH=compat_dir(n), STEAM_COMPAT_CLIENT_INSTALL_PATH=steam_dir(), WINEPREFIX=prefix_dir(n),
               SteamAppId="0", SteamGameId="0")
    env.setdefault("WINEDEBUG", "-all")
    if log_dir:
        env.update(PROTON_LOG="1", PROTON_LOG_DIR=log_dir)
    return env


def proton_cmd(*args):
    """argv for `proton run ...` (Proton's script is Python)."""
    return ["python3", os.path.join(proton_dir(), "proton"), "run", *args]


def wine_cmd(*args):
    """argv for Proton's own wine binary (helpers such as a window tool inside the slot's prefix; use with wine_env)."""
    return [os.path.join(proton_dir(), "files", "bin", "wine"), *args]


def wineserver_cmd(*args):
    return [os.path.join(proton_dir(), "files", "bin", "wineserver"), *args]


def windows_path(n, path):
    """The Windows path of a Linux file for slot N's prefix: D:\\... inside the slot folder, Z:\\... (Wine's root drive)
    elsewhere."""
    path = os.path.abspath(path)
    game = os.path.abspath(slot_dir(n))
    if path == game or under(path, game):
        rel = os.path.relpath(path, game)
        return GAME_DRIVE.upper() + "\\" + ("" if rel == "." else rel.replace("/", "\\"))
    return "Z:" + path.replace("/", "\\")


def ensure_drive(n):
    """Drive D: of slot N's prefix points at the slot folder (made when missing). Exits when it points elsewhere."""
    link = os.path.join(prefix_dir(n), "dosdevices", GAME_DRIVE)
    game = slot_dir(n)
    if os.path.islink(link) or os.path.exists(link):
        if os.path.realpath(link) != os.path.realpath(game):
            raise SystemExit(f"slot {n}: {link} points at {os.path.realpath(link)}, not the slot folder {game}: fix it by hand")
        return link
    if not os.path.isdir(os.path.dirname(link)):
        raise SystemExit(f"slot {n}: no Wine prefix at {prefix_dir(n)} (dosdevices missing): set up the prefix first "
                         "(docs/testing.md \"Linux slots\")")
    os.symlink(game, link)
    return link


# ---------------------------------------------------------------- Linux: no focus stealing (owner rule, 2026-11-20)
# Test games start in the background on the owner's desktop and never take keyboard focus or come to the front. The
# start side is the slot prefix's own Wine registry (HKCU\Software\Wine\X11 Driver), written by launch() every time:
#   UseTakeFocus=N    Wine does not answer the window manager's WM_TAKE_FOCUS by focusing its window
#   GrabPointer=N     no pointer grab of a Wine window (a grab would take the owner's mouse)
#   GrabFullscreen=N  no pointer confinement for a full-screen window
# Wine itself marks windows mapped without user input with _NET_WM_USER_TIME 0, so the window manager does not focus
# them. FocusWatch measures it every run: _NET_ACTIVE_WINDOW of the root window must never become a window of the
# slot's prefix. Desktop / window-manager settings are never changed.
X11_DRIVER_KEY = "Software\\\\Wine\\\\X11 Driver"  # as user.reg spells it
NO_FOCUS_VALUES = (("UseTakeFocus", "N"), ("GrabPointer", "N"), ("GrabFullscreen", "N"))


def set_reg_values(text, key, values, stamp=None):
    """user.reg text with string `values` [(name, data)] set in [key] (key as user.reg spells it, backslashes doubled);
    the section is added at the end when missing, other values and sections are kept as they are."""
    lines = text.split("\n")
    head = f"[{key}]"
    start = next((i for i, l in enumerate(lines) if l.startswith(head + " ") or l == head), None)
    if start is None:
        stamp = int(time.time()) if stamp is None else stamp
        while lines and lines[-1] == "":
            lines.pop()
        lines += ["", f"{head} {stamp}"] + [f'"{k}"="{v}"' for k, v in values] + [""]
        return "\n".join(lines) + ("" if lines[-1] == "" else "\n")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    while end > start + 1 and lines[end - 1] == "":
        end -= 1
    for k, v in values:
        want = f'"{k}"="{v}"'
        at = next((i for i in range(start + 1, end) if lines[i].lower().startswith(f'"{k.lower()}"=')), None)
        if at is None:
            lines.insert(end, want)
            end += 1
        else:
            lines[at] = want
    return "\n".join(lines)


def reg_values(text, key):
    """{name: data} of the string values in [key] of a user.reg text."""
    out, inside = {}, False
    for l in text.split("\n"):
        if l.startswith("["):
            inside = l.startswith(f"[{key}]")
        elif inside and l.startswith('"') and '"="' in l:
            k, v = l[1:].split('"="', 1)
            out[k] = v.rstrip('"')
    return out


def apply_launch_settings(n):
    """Write NO_FOCUS_VALUES into slot N's prefix registry (user.reg) unless they are there already. Only while nothing
    runs in the prefix: a running wineserver would write its own copy over the file. Returns what was changed."""
    reg = os.path.join(prefix_dir(n), "user.reg")
    if not os.path.isfile(reg):
        raise SystemExit(f"slot {n}: no {reg}: set up the prefix first (docs/testing.md \"Linux slots\")")
    with open(reg, encoding="utf-8", newline="") as f:
        text = f.read()
    have = reg_values(text, X11_DRIVER_KEY)
    missing = [(k, v) for k, v in NO_FOCUS_VALUES if have.get(k) != v]
    if not missing:
        return []
    if prefix_pids(n):
        raise SystemExit(f"slot {n}: the prefix runs, its registry cannot be changed now: stop it first")
    tmp = reg + ".mxl2012-tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(set_reg_values(text, X11_DRIVER_KEY, NO_FOCUS_VALUES))
    os.replace(tmp, reg)
    return missing


# Graphics profiles of the Linux slots (lane lowprofile, 2026-11-21): tools/slot_profiles/<name>.json hold only the
# graphics keys of D2R's Settings.json. "test" (the default) is the low Windows test profile of 2026-10-28 at 1600x900:
# it lets more games share the GPU. "visual" is the high quality the slots had before; HD visual checks and the hdkit
# sign-off ask for it (VISUAL_CHECKS, game_checks.run_all). Settings.json sits in the prefix's save folder, outside the
# slot snapshot, so every launch writes the profile again (apply_profile) instead of trusting the last run's.
PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "slot_profiles")
PROFILES = ("test", "visual", "visual4k")   # visual4k: visual at 3840x2160 (lane hdmaps2: map captures for 4K; counts as the one visual game)
DEFAULT_PROFILE = "test"
# game_checks check names that judge HD looks (effects, models, item art, tints, draw lists): run with "visual"
VISUAL_CHECKS = frozenset({"signoff", "hdl_look", "tint_hd", "ua_look", "itemart_pics", "itemart_mons", "hdit_icons",
                           "standin_mons", "drawcap", "hm2_monsters", "hm3_monsters", "mon_card"})


def profile_name(name=None):
    """The graphics profile of a launch: `name`, else env MXL_PROFILE, else "test". An unknown name is an error."""
    p = (name or os.environ.get("MXL_PROFILE") or DEFAULT_PROFILE).strip().lower()
    if p not in PROFILES:
        raise SystemExit(f"unknown graphics profile {p!r} (MXL_PROFILE / --profile): one of {', '.join(PROFILES)}")
    return p


def profile_for_checks(names, explicit=None):
    """The profile a game_checks run needs: `explicit` (MXL_PROFILE) when given, else "visual" when one of the checks
    named is a visual check, else "test"."""
    if explicit:
        return profile_name(explicit)
    return "visual" if VISUAL_CHECKS.intersection(names or ()) else DEFAULT_PROFILE


def load_profile(name):
    with open(os.path.join(PROFILE_DIR, profile_name(name) + ".json"), encoding="utf-8") as f:
        return json.load(f)


def settings_path(n):
    """D2R's Settings.json of slot N (in the slot's save folder inside the prefix)."""
    return os.path.join(save_dir(n), "Settings.json")


def apply_profile(n, name=None, path=None):
    """Write the graphics keys of profile `name` (profile_name) into slot N's Settings.json, every other key kept as
    it is, in D2R's own layout (4-space JSON, no newline at the end). Only while the prefix is idle: the running game
    writes its settings back on exit. A slot without Settings.json gets one with only these keys (D2R fills the rest).
    Returns (profile, {key: (old, new)} of what changed)."""
    prof = profile_name(name)
    want = load_profile(prof)
    path = path or settings_path(n)
    try:
        with open(path, encoding="utf-8-sig") as f:
            cur = json.load(f, object_pairs_hook=collections.OrderedDict)
    except FileNotFoundError:
        cur = collections.OrderedDict()
    changed = {k: (cur.get(k), v) for k, v in want.items() if cur.get(k) != v}
    if not changed:
        return prof, {}
    if prefix_pids(n):
        raise SystemExit(f"slot {n}: the prefix runs, its Settings.json cannot be changed now: stop it first")
    cur.update(want)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".mxl2012-tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(cur, indent=4))
    os.replace(tmp, path)
    return prof, changed


def xprop(*args, display=None):
    """stdout of xprop (empty when it fails or is missing)."""
    env = dict(os.environ, DISPLAY=display) if display else None
    try:
        return subprocess.run(["xprop", *args], capture_output=True, text=True, timeout=5, env=env).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_active(out):
    """The window id of `xprop -root _NET_ACTIVE_WINDOW` output (0 for none), or None when there is no such property."""
    if "window id #" not in out:
        return None
    return int(out.split("window id #", 1)[1].split(",")[0].strip(), 16)


def parse_window(out):
    """(pid or None, WM_CLASS text) of `xprop -id W _NET_WM_PID WM_CLASS` output."""
    pid, cls = None, ""
    for l in out.splitlines():
        if l.startswith("_NET_WM_PID") and "=" in l:
            try:
                pid = int(l.split("=", 1)[1].strip())
            except ValueError:
                pass
        elif l.startswith("WM_CLASS") and "=" in l:
            cls = l.split("=", 1)[1].strip()
    return pid, cls


def is_game_window(pid, cls, game_pids_):
    """A window of the slot's prefix: its _NET_WM_PID is one of the prefix's processes, or its WM_CLASS names a Windows
    program (Wine sets WM_CLASS to the .exe name)."""
    return (pid is not None and pid in game_pids_) or ".exe" in cls.lower()


class FocusWatch:
    """Polls _NET_ACTIVE_WINDOW of the root window during a run (a thread; `interval` seconds). Every change is recorded
    as (seconds since start, window id, pid, WM_CLASS, game?); `grabs` lists those that went to a window of slot N's
    prefix. stop() returns a one-line summary for the run's report."""

    def __init__(self, n, interval=0.2, display=None, query=None, pids=None):
        import threading
        self.n, self.interval, self.display = n, interval, display
        self._query = query or (lambda *a: xprop(*a, display=display))
        self._pids = pids or (lambda: set(prefix_pids(n)))
        self.t0 = time.time()
        self.before = parse_active(self._query("-root", "_NET_ACTIVE_WINDOW"))
        self.changes, self.grabs, self.polls = [], [], 0
        self._last = self.before
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def poll(self):
        """One measurement; returns the grab it found, else None."""
        self.polls += 1
        now = parse_active(self._query("-root", "_NET_ACTIVE_WINDOW"))
        if now == self._last:
            return None
        self._last = now
        pid, cls = parse_window(self._query("-id", hex(now), "_NET_WM_PID", "WM_CLASS")) if now else (None, "")
        game = bool(now) and is_game_window(pid, cls, self._pids())
        rec = (round(time.time() - self.t0, 2), now, pid, cls, game)
        self.changes.append(rec)
        if game:
            self.grabs.append(rec)
            return rec
        return None

    def _run(self):
        while not self._stop.is_set():
            self.poll()
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(5)
        return self.summary()

    def summary(self):
        b = "none" if self.before is None else hex(self.before)
        if self.grabs:
            return (f"FOCUS GRAB: _NET_ACTIVE_WINDOW went to a game window {len(self.grabs)}x "
                    f"({', '.join(f'{hex(w)} pid {p} {c} at {t}s' for t, w, p, c, _ in self.grabs)}); before launch {b}")
        return (f"focus kept: _NET_ACTIVE_WINDOW never went to a game window ({self.polls} polls over "
                f"{time.time() - self.t0:.0f} s, {len(self.changes)} changes by the owner; before launch {b})")


# ---------------------------------------------------------------- VRAM cap (lane vramcap, 2026-11-21)
# D2R sizes its texture streaming pool from the adapter's DedicatedVideoMemory. Under Proton, D3D12 runs on vkd3d-proton
# with DXVK's dxgi.dll, whose option dxgi.maxDeviceMemory (MB) lowers that number (env DXVK_CONFIG; checked with a DXGI
# probe: the adapter description follows it, IDXGIAdapter3::QueryVideoMemoryInfo's budget does not). Our Proton game
# launches get the cap of their profile (VRAM_DEFAULTS) unless env MXL_VRAM_MB says otherwise (a number of MB, or
# 0 / none / off for no cap). Measured in docs/testing.md, "Lane vramcap".
VRAM_DEFAULTS = {"test": 2048, "visual": 3072, "visual4k": 4096}  # lane vramcap: visual at 2048 drew black tiles
VRAM_MIN_MB = 256


def vram_mb(profile=None, value=None):
    """The VRAM cap in MB of a launch with graphics profile `profile`, or None for no cap: `value` when given, else env
    MXL_VRAM_MB, else VRAM_DEFAULTS of the profile. "0", "none", "off" mean no cap. A cap below VRAM_MIN_MB is an error."""
    v = value if value is not None else os.environ.get("MXL_VRAM_MB")
    if v is None or str(v).strip() == "":
        return VRAM_DEFAULTS.get(profile_name(profile))
    s = str(v).strip().lower()
    if s in ("0", "none", "off", "no"):
        return None
    try:
        mb = int(s)
    except ValueError:
        raise SystemExit(f"MXL_VRAM_MB / --vram-mb: {v!r} is not a number of MB (or 0 / none for no cap)")
    if mb < VRAM_MIN_MB:
        raise SystemExit(f"MXL_VRAM_MB / --vram-mb: {mb} MB is below {VRAM_MIN_MB} MB")
    return mb


def vram_env(mb, base=None):
    """The environment entries that tell the game it has `mb` MB of VRAM: DXVK_CONFIG with dxgi.maxDeviceMemory (an
    existing DXVK_CONFIG of `base`, default os.environ, is kept, its own maxDeviceMemory replaced). {} for no cap."""
    if not mb:
        return {}
    base = os.environ if base is None else base
    keep = [o.strip() for o in (base.get("DXVK_CONFIG") or "").split(";")
            if o.strip() and o.split("=", 1)[0].strip() != "dxgi.maxDeviceMemory"]
    return {"DXVK_CONFIG": "; ".join(keep + [f"dxgi.maxDeviceMemory = {int(mb)}"])}


LAST_VRAM = {}  # slot -> VRAM cap in MB (None: no cap) of the last launch(), for the caller's log
LAST_PROFILE = {}  # slot -> (profile, changed keys) of the last launch(), for the caller's log


def launch(n, args, log_dir=None, stdout=None, extra_env=None, profile=None, vram=None):
    """Start `D:\\<loader> args...` of slot N under Proton in its prefix (cwd the slot folder); returns the Popen of
    Proton's script. The caller holds the slot lock and has begun the run's snapshot (slot_share.begin). The prefix's
    no-focus settings (apply_launch_settings) are written first, every launch; measure with FocusWatch.
    extra_env: added to the game's environment; game runs pass the private display (DISPLAY + linux_window.PRIVATE_ENV,
    see linux_window.PrivateDisplay): on the owner's desktop the game takes the focus whatever the prefix settings.
    profile: the graphics profile written into the slot's Settings.json first (apply_profile; default env MXL_PROFILE,
    else "test").
    vram: the VRAM cap in MB (vram_mb: default env MXL_VRAM_MB, else the profile's VRAM_DEFAULTS; 0 / "none": no cap),
    passed to DXVK's dxgi as DXVK_CONFIG dxgi.maxDeviceMemory (vram_env)."""
    game = slot_dir(n)
    ensure_drive(n)
    apply_launch_settings(n)
    LAST_PROFILE[n] = apply_profile(n, profile)
    exe = windows_path(n, os.path.join(game, loader_name(game)))
    env = wine_env(n, log_dir=log_dir)
    env.update(extra_env or {})
    LAST_VRAM[n] = vram_mb(LAST_PROFILE[n][0], vram)
    env.update(vram_env(LAST_VRAM[n], env))
    return subprocess.Popen(proton_cmd(exe, *args), cwd=game, env=env,
                            stdout=stdout or subprocess.DEVNULL, stderr=subprocess.STDOUT)


def stop_prefix(n, timeout=60):
    """End every process of slot N's prefix (`wineserver -k`: only that prefix's processes; the lock holder started
    them) and wait until the prefix is idle. Returns True when nothing of the prefix runs any more."""
    subprocess.run(wineserver_cmd("-k"), env=wine_env(n), capture_output=True, timeout=timeout)
    if wait_prefix_idle(n, timeout):
        return True
    # Lane linfix (2026-11-20, run p2): after a startup crash the prefix's wineserver was gone and its clients (the
    # loader in a pipe read, services, explorer) stayed, so `-k` reached nobody. They are this slot prefix's processes
    # (WINEPREFIX), started by the lock holder's launch: end them directly.
    left = prefix_pids(n)
    for pid in left:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    print(f"slot {n}: wineserver -k left {len(left)} process(es) of the slot prefix: SIGKILL {left}", file=sys.stderr)
    return wait_prefix_idle(n, 15)


def wait_prefix_idle(n, timeout=120):
    """Wait until no process of slot N's prefix runs (its wineserver has gone); True when idle."""
    end = time.time() + timeout
    while time.time() < end:
        if not prefix_pids(n):
            return True
        time.sleep(0.5)
    return not prefix_pids(n)


# ---------------------------------------------------------------- locks


def lock_paths(n):
    """The lock folders of slot N: game.lock.N, and for slot 1 also the old single game.lock (both are taken,
    either one held means the slot is held)."""
    n = require_slot(n)
    if not LOCK_ROOT:
        require_machine("game slot locks")
    paths = [os.path.join(LOCK_ROOT, f"game.lock.{n}")]
    if n in LEGACY_LOCK:
        paths.append(os.path.join(LOCK_ROOT, LEGACY_LOCK[n]))
    return paths


def lock_info(n):
    """None when free, else (path, owner text or None for a lock without owner.txt)."""
    for p in lock_paths(n):
        if os.path.isdir(p):
            try:
                with open(os.path.join(p, "owner.txt"), encoding="utf-8") as f:
                    txt = f.read().strip()
            except OSError:
                txt = None
            return p, txt
    return None


def _owner_pid(txt):
    for part in (txt or "").split():
        if part.startswith("pid="):
            try:
                return int(part[4:])
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------- shared seats (lane slotcap, 2026-11-21)
# One machine-wide budget of games for every project that runs D2R here (<locks>/README.md, agreed with D2RGS):
#   <locks>/budget.json   {"max_games": N, "set_by": ..., "measured": <run folder>}; missing: no budget (old behaviour)
#   <locks>/game.seat.K   K = 1..max_games, a directory with owner.txt `<owner> pid=<pid> <time> slot=<N>`, taken like a
#                         slot lock (mkdir); stale when its pid is gone (pid 0: taken by hand, never stale)
# Order: seat first, then game.lock.N; a failure between the two releases the seat. Release: game.lock.N first, then the
# seat. A seat is the lock's companion: it lives exactly as long as the slot lock.
SEAT_WAIT = float(os.environ.get("MXL_SEAT_WAIT") or 0)  # default seconds acquire() waits for a free seat (0: refuse)


def _locks_json(name):
    try:
        with open(os.path.join(LOCK_ROOT, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def slot_project(n):
    """The project <locks>/slots.json gives slot N to ({"slots": {"N": "MXL" | "D2RGS" | ...}}), or None."""
    if not LOCK_ROOT:
        return None
    d = _locks_json("slots.json") or {}
    v = (d.get("slots") or {}).get(str(n))
    return v if isinstance(v, str) else None


def max_games():
    """The machine-wide game budget of <locks>/budget.json, or None when there is none (no seats are taken)."""
    if not LOCK_ROOT:
        return None
    d = _locks_json("budget.json")
    try:
        m = int(d["max_games"])
    except (TypeError, KeyError, ValueError):
        return None
    return m if m > 0 else None


def seat_path(k):
    return os.path.join(LOCK_ROOT, f"game.seat.{k}")


def _owner_text(path):
    try:
        with open(os.path.join(path, "owner.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def _seat_slot(txt):
    for part in (txt or "").split():
        if part.startswith("slot="):
            try:
                return int(part[5:])
            except ValueError:
                pass
    return None


def seats():
    """[(K, owner text or None)] of every game.seat.K directory in the lock folder (also K above the budget)."""
    out = []
    try:
        names = os.listdir(LOCK_ROOT)
    except OSError:
        return out
    for nm in names:
        if nm.startswith("game.seat.") and nm[10:].isdigit() and os.path.isdir(os.path.join(LOCK_ROOT, nm)):
            out.append((int(nm[10:]), _owner_text(os.path.join(LOCK_ROOT, nm))))
    return sorted(out)


def _seat_stale(txt):
    op = _owner_pid(txt)
    return op is not None and op != 0 and not pid_alive(op)


def our_seat(n, owner):
    """K of the seat `owner` holds for slot N, else None."""
    for k, txt in seats():
        if txt and txt.split()[0] == owner and _seat_slot(txt) == n:
            return k
    return None


OUR_PROJECT = "MXL"  # this project's name in <locks>/slots.json and game.want.<project>


def wanted_by_others():
    """Seats other projects are waiting for: the sum of count=C (1 or 2) over every game.want.<project> (not ours) whose
    pid is alive (pid 0: by hand, always counts). <locks>/README.md "Waiting for seats" (owner, 2026-11-21): D2RGS may
    hold 1 or 2 seats, never more; while it waits we take no seat that would leave it fewer free than it wants."""
    total, notes = 0, []
    try:
        names = os.listdir(LOCK_ROOT)
    except OSError:
        return 0, notes
    for nm in sorted(names):
        proj = nm[len("game.want."):] if nm.startswith("game.want.") else None
        if not proj or proj == OUR_PROJECT or not os.path.isdir(os.path.join(LOCK_ROOT, nm)):
            continue
        txt = _owner_text(os.path.join(LOCK_ROOT, nm))
        if _seat_stale(txt):
            continue
        c = 1
        for part in (txt or "").split():
            if part.startswith("count="):
                try:
                    c = int(part[6:])
                except ValueError:
                    pass
        c = max(1, min(2, c))
        total += c
        notes.append(f"{proj} waits for {c}")
    return total, notes


def take_seat(n, owner, pid, wait=None):
    """Take a free game.seat.K (K = 1..max_games) for slot N. Returns (K or None, message). K 0: no budget.json, nothing
    taken. A stale seat (pid gone, not 0) is replaced. No free seat: wait up to `wait` seconds (default SEAT_WAIT), then
    refuse."""
    m = max_games()
    if m is None:
        return 0, "no budget.json"
    k = our_seat(n, owner)
    if k:
        return k, f"seat {k} already ours"
    end = time.time() + (SEAT_WAIT if wait is None else wait)
    while True:
        held = []
        want, want_notes = wanted_by_others()
        free = sum(1 for k in range(1, m + 1)
                   if not os.path.isdir(seat_path(k)) or _seat_stale(_owner_text(seat_path(k))))
        if want and free - 1 < want:  # leave the waiting project the seats it asked for
            held.append(f"yielding: {', '.join(want_notes)}, {free} free")
        for k in (range(1, m + 1) if not (want and free - 1 < want) else ()):
            p = seat_path(k)
            txt = _owner_text(p) if os.path.isdir(p) else None
            if os.path.isdir(p):
                if not _seat_stale(txt):
                    held.append(f"{k}: {txt or 'no owner.txt'}")
                    continue
                shutil.rmtree(p, ignore_errors=True)
            try:
                os.mkdir(p)
            except FileExistsError:
                held.append(f"{k}: taken just now")
                continue
            tmp = os.path.join(p, f"owner.txt.{os.getpid()}")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(f"{owner} pid={pid} {datetime.datetime.now():%Y-%m-%d %H:%M:%S} slot={n}")
            os.replace(tmp, os.path.join(p, "owner.txt"))
            return k, f"seat {k} of {m} taken by {owner}"
        if time.time() >= end:
            return None, f"no free seat (max_games {m} in budget.json): " + "; ".join(held)
        time.sleep(min(5.0, max(0.1, end - time.time())))


def release_seat(n, owner):
    """Remove the seat(s) `owner` holds for slot N (owner None: every seat of slot N)."""
    for k, txt in seats():
        if _seat_slot(txt) == n and (owner is None or (txt and txt.split()[0] == owner)):
            shutil.rmtree(seat_path(k), ignore_errors=True)


def acquire(n, owner, pid=None, seat_wait=None):
    """Take the lock of slot N. Returns (ok, message). Stale locks (owner pid gone) are replaced. pid=0 marks a manual
    lock (command line `lock N`): it is never treated as stale and lasts until `unlock N`. With <locks>/budget.json a
    seat (game.seat.K) is taken first and released again when the slot lock cannot be taken (take_seat; seat_wait
    seconds of waiting for one, default env MXL_SEAT_WAIT or 0)."""
    os.makedirs(LOCK_ROOT, exist_ok=True)
    pid = os.getpid() if pid is None else pid
    info = lock_info(n)
    if info:
        path, txt = info
        op = _owner_pid(txt)
        if txt and txt.split()[0] == owner:
            return True, f"lock {path} already ours"
        if not (op is not None and op != 0 and not pid_alive(op)):  # pid 0: manual lock, never stale
            return False, f"lock {path} held by {txt or 'someone (no owner.txt)'}"
    k, seat_msg = take_seat(n, owner, pid, seat_wait)
    if k is None:
        return False, seat_msg
    seat_note = f" ({seat_msg})" if k else ""

    def give_back(msg):
        if k:
            release_seat(n, owner)
        return False, msg + seat_note
    info = lock_info(n)
    if info:  # stale (checked above), or taken while we waited for a seat
        path, txt = info
        op = _owner_pid(txt)
        if op is not None and op != 0 and not pid_alive(op):
            for p in lock_paths(n):
                shutil.rmtree(p, ignore_errors=True)
            if txt:  # the dead owner's seat goes with its lock
                release_seat(n, txt.split()[0])
        else:
            return give_back(f"lock {path} held by {txt or 'someone (no owner.txt)'}")
    made = []
    for p in lock_paths(n):
        try:
            os.mkdir(p)
        except FileExistsError:
            for q in made:
                shutil.rmtree(q, ignore_errors=True)
            return give_back(f"lock {p} taken just now")
        made.append(p)
        with open(os.path.join(p, "owner.txt"), "w", encoding="utf-8") as f:
            f.write(f"{owner} pid={pid} {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    return True, f"lock {made[0]} taken by {owner}{seat_note}"


def release(n, owner=None, manual=False):
    """Remove the lock if it is ours (owner given: only a lock whose owner.txt names that owner) or, with owner None
    (command line `unlock N`), whatever is there. A lock somebody made by hand (no owner.txt) is never removed by a
    run that merely used it, and neither is a manual lock (`lock N OWNER`, pid=0): a lane holds the slot with it for a
    whole session (setup, several runs, restore), and the runs inside it (game_ctl / game_checks with MXL_RUN=OWNER)
    must not open the slot for another lane between them. Only `unlock N [OWNER]` (manual=True) removes it. The lock's
    seat (game.seat.K naming the same owner and slot) is removed right after the lock."""
    info = lock_info(n)
    if not info:
        if owner is not None:
            release_seat(n, owner)  # a seat left by a failure between the two steps
        return True
    path, txt = info
    if owner is not None and (not txt or txt.split()[0] != owner):
        return False
    if owner is not None and not manual and _owner_pid(txt) == 0:
        return True  # the lane's session lock: kept until its own `unlock N`
    import slot_share
    if slot_share.pending(n):  # a run's snapshot of the shared D2RLoader files: back before anyone else gets the slot
        try:
            print(slot_share.end(n, txt.split()[0] if txt else owner))
        except SystemExit as e:
            print(f"lock kept: {e}")
            return False
    if slot_share.probes(n):  # test plugins of `slot_share probe add` (lane globalplugins) never outlive the lock
        try:
            print(slot_share.probe_clear(n))
        except SystemExit as e:
            print(f"lock kept: {e}")
            return False
    for p in lock_paths(n):
        shutil.rmtree(p, ignore_errors=True)
    if txt:
        release_seat(n, txt.split()[0])
    return True


# ---------------------------------------------------------------- the owner's slot (slot 1)


def launch_marker(n):
    """<RUNS>/slot-share-sN/launched.json: written by game_ctl right after it started the slot's loader, removed by its
    stop once the slot's processes are gone. On an owner slot only a game with this marker (of the same run) is ours."""
    return os.path.join(RUNS, f"slot-share-s{require_slot(n)}", "launched.json")


def mark_launch(n, owner, pid):
    p = launch_marker(n)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"slot": n, "owner": owner, "pid": pid, "at": time.strftime("%Y-%m-%d %H:%M:%S")}, f)


def launched_by(n):
    """(owner, loader pid) of the slot's launch marker, or (None, None)."""
    try:
        with open(launch_marker(n), encoding="utf-8") as f:
            m = json.load(f)
        return m.get("owner"), m.get("pid")
    except (OSError, ValueError, AttributeError):
        return None, None


def clear_launch(n):
    try:
        os.remove(launch_marker(n))
    except FileNotFoundError:
        pass


def foreign_game(n, owner, procs=None):
    """On an owner slot (slot 1): the game processes running in the slot folder that no run of `owner` started (the owner
    playing their own game, or a run of another mod's tools), else []. Such a game is never attached to, closed or
    killed. Ours means: the marker names `owner` and the loader it launched is still among the processes (the loader
    lives as long as the game), so a marker left by a crashed run never makes the owner's later game look like ours.
    Slots 2 to 5 return [] (there the lock alone says whose game it is)."""
    n = require_slot(n)
    if n not in OWNER_SLOTS:
        return []
    procs = slot_processes(slot_dir(n)) if procs is None else procs
    who, pid = launched_by(n)
    if not procs or (owner and who == owner and pid in {p for p, _ in procs}):
        return []
    return procs


ELEVATION_NOTE = ("the tools never ask for administrator rights and never retry another way: ask the PC owner to give "
                  "this user write access to that folder, or use slot 2, 3, 4 or 5")


def need_write(paths, what, root=None):
    """Exit with a clear message unless every path can be written by this (never elevated) process. A file is opened
    for writing and closed again (no byte and no time stamp changes); a folder gets a probe file that is removed at
    once; a missing path is checked at its nearest existing parent folder, never above `root` (default the slot folder
    the path is in, else the path itself). Program Files folders (slot 1) may refuse
    writes without administrator rights; Python has a manifest, so Windows does not redirect its writes to the
    VirtualStore: the write fails with an access error, which ends up here."""
    for p in paths:
        top = root or next((slot_dir(n) for n in SLOTS if under(p, slot_dir(n))), p)
        q = p
        while not os.path.exists(q) and under(q, top):
            q = os.path.dirname(q)
        if not os.path.exists(q):
            raise SystemExit(f"{what}: {top} does not exist")
        try:
            if os.path.isdir(q):
                probe = os.path.join(q, f".mxl2012-write-probe-{os.getpid()}")
                with open(probe, "x"):
                    pass
                os.remove(probe)
            else:
                with open(q, "r+b"):
                    pass
        except PermissionError as e:
            raise SystemExit(f"{what}: no write access to {q} ({e.strerror or e}); {ELEVATION_NOTE}")


# ---------------------------------------------------------------- setup


def set_savepath(n):
    """modinfo.json (mod root and inside the folder MPQ) points the mod at this slot's own save folder."""
    mod = mod_dir(n)
    text = json.dumps({"name": MOD, "savepath": save_name(n) + "/"}, indent=2)
    for target in (os.path.join(mod, f"{MOD}.mpq", "modinfo.json"), os.path.join(mod, "modinfo.json")):
        if os.path.isdir(os.path.dirname(target)):
            with open(target, "w", encoding="utf-8") as f:
                f.write(text)


def set_toml_value(text, section, key, value):
    """`text` with `key = value` in [section]: an existing (or commented template) line is replaced, else the key is
    added under the header (the section appended when missing)."""
    lines = text.splitlines()
    head = f"[{section}]"
    start = next((i for i, l in enumerate(lines) if l.strip() == head), None)
    if start is None:
        return text.rstrip("\n") + f"\n\n{head}\n{key} = {value}\n"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    for i in range(start + 1, end):
        bare = lines[i].strip().lstrip("#").strip()
        if bare.startswith(key) and bare[len(key):].lstrip().startswith("="):
            lines[i] = f"{key} = {value}"
            break
    else:
        lines.insert(start + 1, f"{key} = {value}")
    return "\n".join(lines) + "\n"


def setup(n):
    game = slot_dir(n)
    if not present(n):
        return f"slot {n}: MISSING, {missing_note(n)} (copy a full D2R 93847 + D2RLoader folder there first, docs/testing.md)"
    # Only our own things: the game-wide d2rloader\config (default_mod, launch_arguments, console ...) belongs to the slot
    # and the other mod uses it too, so it is left alone (each run names the mod on the loader's command line, slot_share.py).
    if os.path.isdir(mod_dir(n)):
        need_write([mod_dir(n)], f"slot {n} setup")
    set_savepath(n)
    os.makedirs(save_dir(n), exist_ok=True)
    if n in OWNER_SLOTS:  # the owner's folder: no loader copy, runs use D2RLoader.exe
        return f"slot {n}: {game}, saves {save_dir(n)}, loader {loader_name(game)}"
    src_exe, dst_exe = os.path.join(game, "D2RLoader.exe"), os.path.join(game, f"D2RLoader-s{n}.exe")
    note = ""
    if not os.path.exists(dst_exe):
        shutil.copy2(src_exe, dst_exe)
    elif os.path.getsize(dst_exe) != os.path.getsize(src_exe):
        note = f" (NOTE: {os.path.basename(dst_exe)} differs from D2RLoader.exe; it is shared with the other mod and left as it is)"
    return f"slot {n}: {game}, saves {save_dir(n)}, loader {loader_name(game)}{note}"


# ---------------------------------------------------------------- cli


def status():
    m = max_games()
    held = seats()
    print(f"budget: {'none (no budget.json)' if m is None else f'max_games {m}'}; seats held: "
          + ("; ".join(f"{k}: {t or 'no owner.txt'}" for k, t in held) or "-"))
    for n in SLOTS:
        game = slot_dir(n)
        lk = lock_info(n)
        if not present(n):
            print(f"slot {n}: MISSING ({missing_note(n)}); lock {lk[1] or 'held (no owner.txt)' if lk else 'free'}")
            continue
        procs = slot_processes(game)
        try:
            with open(os.path.join(mod_dir(n), "modinfo.json"), encoding="utf-8") as f:
                sp = json.load(f)["savepath"]
        except Exception:
            sp = "?"
        import slot_share
        man = slot_share.pending(n)
        where = f"; prefix {prefix_dir(n)}{'' if os.path.isdir(prefix_dir(n)) else ' MISSING'}" if LINUX else ""
        what = "slot" if LINUX else "shared files"
        print(f"slot {n}: {game} ok{where}; running {procs or '-'}; "
              f"lock {lk[1] or 'held (no owner.txt)' if lk else 'free'}; savepath {sp}"
              + (f"; {what} PENDING restore (snapshot of {man['owner']} {man['at']})" if man else ""))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 0
    c = a[0]
    require_machine(f"game_slots {c}")
    if c == "status":
        status()
    elif c == "setup":
        rc = 0
        for n in [require_slot(x) for x in a[1:]] or list(DEFAULT_SET):
            msg = setup(n)
            print(msg)
            rc |= bool(a[1:]) and " MISSING, " in msg  # a slot named on the command line must exist; the default set skips
        return int(rc)
    elif c == "lock":
        # pid 0: this command exits right away, so its own pid would make the lock look stale at once
        n = require_present(a[1], "lock")  # a missing slot is never locked (`unlock` still works, for a stale lock)
        ok, msg = acquire(n, a[2] if len(a) > 2 else "manual", pid=0)
        print(msg)
        return 0 if ok else 1
    elif c == "unlock":
        return 0 if release(require_slot(a[1]), a[2] if len(a) > 2 else None, manual=True) else 1
    elif c == "profile":  # profile N [test|visual]: write a graphics profile into the slot's Settings.json now (Linux)
        if not LINUX:
            print("graphics profiles are for the Linux slots only")
            return 1
        prof, changed = apply_profile(require_present(a[1], "profile"), a[2] if len(a) > 2 else None)
        print(f"slot {a[1]}: profile {prof}; " + (", ".join(f"{k} {o} -> {v}" for k, (o, v) in changed.items()) or "already set"))
    elif c == "install":
        here = os.path.dirname(os.path.abspath(__file__))
        rc = 0
        for n in [require_present(x, "install") for x in a[1:]] or present_set():
            rc |= subprocess.call([sys.executable, os.path.join(here, "install_mod.py"), "--slot", str(n)])
        return rc
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
