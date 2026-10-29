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
"""
import ctypes
import fnmatch
import ctypes.wintypes as wt
import datetime
import json
import os
import shutil
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


def require_machine(tool="game_slots"):
    """Exits unless machine.json has the slot safety keys (shared lock folder, protected mod and save folders)."""
    return localconfig.require_machine(tool=tool)


def protected(name, saves=False):
    """True when `name` is another mod's folder (or, saves=True, its save folder) that no tool may write."""
    pats = PROTECTED_SAVES if saves else PROTECTED_MODS
    return any(fnmatch.fnmatch(name.lower(), p.lower()) for p in pats)


def require_slot(n):
    """The slot number as an int; exits with an error for anything but 1 to 5."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        raise SystemExit(f"no game slot given ({n!r}): pass --slot 1|2|3|4|5 or set MXL_SLOT")
    if n not in SLOTS:
        raise SystemExit(f"game slot {n} refused: only slots 1 to 5 exist")
    return n


def env_slot():
    """The slot of env MXL_SLOT, refused unless 1 to 5. There is no default: an unset MXL_SLOT is an error."""
    return require_slot(os.environ.get("MXL_SLOT"))


def slot_dir(n):
    require_slot(n)
    return os.environ.get(f"MXL_SLOT{n}_DIR", DEFAULTS[n])


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
    return os.path.join(SAVE_ROOT, save_name(n))


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


ALL_IMAGES = ("d2rloader.exe", "d2r.exe") + tuple(f"d2rloader-s{n}.exe" for n in SLOTS if n not in OWNER_SLOTS)


def loader_name(game):
    """Slots 2 to 5 run a renamed copy of the loader (D2RLoader-sN.exe), made by `setup`. Older tools that look for
    every D2RLoader.exe (to wait for it, close it or kill it) then never see the test instances of other lanes, and
    the instances never see theirs. Slot 1 (the owner's folder) runs the plain D2RLoader.exe, as the other mod's runs do:
    no copy is written into it."""
    n = slot_of_game_dir(game)
    alt = f"D2RLoader-s{n}.exe"
    return alt if n and n not in OWNER_SLOTS and os.path.exists(os.path.join(game, alt)) else "D2RLoader.exe"


def processes(names=ALL_IMAGES):
    """[(pid, exe name, full image path)] of processes with these image names (none off Windows: the game cannot run there)."""
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
    return p.startswith(f.rstrip("\\") + "\\")


def slot_processes(game, names=ALL_IMAGES):
    """Processes whose image lives in this game folder."""
    return [(pid, nm) for pid, nm, path in processes(names) if path and under(path, game)]


def pid_alive(pid):
    if not winapi.available():
        return False
    h = _k32.OpenProcess(0x1000, False, pid)
    if not h:
        return False
    code = wt.DWORD()
    _k32.GetExitCodeProcess(ctypes.c_void_p(h), ctypes.byref(code))
    _k32.CloseHandle(ctypes.c_void_p(h))
    return code.value == 259  # STILL_ACTIVE


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


def acquire(n, owner, pid=None):
    """Take the lock of slot N. Returns (ok, message). Stale locks (owner pid gone) are replaced. pid=0 marks a manual
    lock (command line `lock N`): it is never treated as stale and lasts until `unlock N`."""
    os.makedirs(LOCK_ROOT, exist_ok=True)
    pid = os.getpid() if pid is None else pid
    info = lock_info(n)
    if info:
        path, txt = info
        op = _owner_pid(txt)
        if txt and txt.split()[0] == owner:
            return True, f"lock {path} already ours"
        if op is not None and op != 0 and not pid_alive(op):  # pid 0: manual lock, never stale
            for p in lock_paths(n):
                shutil.rmtree(p, ignore_errors=True)
        else:
            return False, f"lock {path} held by {txt or 'someone (no owner.txt)'}"
    made = []
    for p in lock_paths(n):
        try:
            os.mkdir(p)
        except FileExistsError:
            for q in made:
                shutil.rmtree(q, ignore_errors=True)
            return False, f"lock {p} taken just now"
        made.append(p)
        with open(os.path.join(p, "owner.txt"), "w", encoding="utf-8") as f:
            f.write(f"{owner} pid={pid} {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    return True, f"lock {made[0]} taken by {owner}"


def release(n, owner=None, manual=False):
    """Remove the lock if it is ours (owner given: only a lock whose owner.txt names that owner) or, with owner None
    (command line `unlock N`), whatever is there. A lock somebody made by hand (no owner.txt) is never removed by a
    run that merely used it, and neither is a manual lock (`lock N OWNER`, pid=0): a lane holds the slot with it for a
    whole session (setup, several runs, restore), and the runs inside it (game_ctl / game_checks with MXL_RUN=OWNER)
    must not open the slot for another lane between them. Only `unlock N [OWNER]` (manual=True) removes it."""
    info = lock_info(n)
    if not info:
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
    for p in lock_paths(n):
        shutil.rmtree(p, ignore_errors=True)
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
        print(f"slot {n}: {game} ok; running {procs or '-'}; "
              f"lock {lk[1] or 'held (no owner.txt)' if lk else 'free'}; savepath {sp}"
              + (f"; shared files PENDING restore (snapshot of {man['owner']} {man['at']})" if man else ""))


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
