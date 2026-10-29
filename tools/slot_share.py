#!/usr/bin/env python
"""Share game slots 1 to 5 with another mod's tests without disturbing them (docs/testing.md, slot sharing).

A slot folder (C:\\Program Files (x86)\\Diablo II Resurrected, D:\\D2R-93847, D:\\D2R-93847-s3, -s4, -s5) holds both mods side by side: the other mod's folder (machine.json protected_mod_folders: never touched)
and mods\\mxl2012 (ours). What both share is the slot's game-wide D2RLoader state:

  d2rloader\\config\\         d2rloader.toml (default_mod, launch_arguments, developer console, logs ...), debugsettings.json,
                             input-bindings.toml (every plugin's hotkeys are stored here on registration), imgui.ini.
                             D2RLoader rewrites d2rloader.toml at every start ("Configuration synchronized") and the others
                             while it runs: a run changes them even when no tool does.
  d2rloader\\plugins\\, patches\\  global extensions: load with EVERY mod (allow_global_extensions). Both are empty and must stay
                             so: mxl2012-core.dll lives only in mods\\mxl2012\\d2rloader\\plugins (loads only with mod mxl2012),
                             the other mod's plugin only in its own mod folder.

Every mxl2012 run (game_ctl start ... stop, so also game_checks / parallel_smoke) works like this while it holds the slot lock:
  begin(n, owner)   refuses unless `owner` holds game.lock.N; refuses when a global plugin/patch folder holds a plugin of
                    either project; refuses when this process may not write the shared files or our mod folder (slot 1
                    is in Program Files: game_slots.need_write, never elevated); copies d2rloader\\config\\ to <runs>\\slot-share-sN\\snapshot\\ with a manifest (sha256,
                    size, mtime per file). A snapshot still pending from a killed run is restored first.
  launch_args()     the loader's command line for the run: our launch arguments the shared toml does not already add, then
                    `-mod mxl2012`. D2RLoader takes the mod from its own command line (checked on slot 2: active mod
                    mxl2012 while default_mod names the other mod), so default_mod is never edited. It puts the toml's
                    launch_arguments in front of our words, so a run that must NOT have one of them (release run without
                    -txt) sets launch_arguments for that run only, inside the snapshot.
  end(n, owner)     after the game has exited: every file of the snapshot is put back byte for byte (with its mtime), files
                    the run created in d2rloader\\config\\ are removed, then the folder is compared with the manifest again;
                    only a clean comparison drops the pending snapshot. Returns what the run had changed.
`game_slots.py unlock N` and `game_ctl stop` call end() too, so a crashed or killed tool is restored before the lock goes.

CLI: py -3 tools/slot_share.py status|diff|restore N     (restore needs MXL_RUN = the lock owner)
     MXL_RUN=<owner> py -3 tools/slot_share.py bootcheck N   start the loader minimized with -mod mxl2012 (no window or
                                                          input calls), wait for the log's mod mount, kill it, restore
     py -3 tools/slot_share.py scan N OUT.json            list every file of the slot (size, mtime) for a before/after report
     py -3 tools/slot_share.py compare A.json B.json      what changed between two scans
"""
import hashlib
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402

SHARED_DIRS = ("d2rloader/config",)  # restored exactly after every run
GLOBAL_EXT = ("d2rloader/plugins", "d2rloader/patches")  # must hold no plugin of either project
# Launch arguments of our runs (the shared toml's launch_arguments are the other mod's and stay as they are). -w: windowed (the
# harness sizes and captures the window); -txt: compile the mod's TXT tables (developer install).
DEV_ARGS = ("-w", "-txt")


def state_dir(n):
    return os.path.join(game_slots.RUNS, f"slot-share-s{game_slots.require_slot(n)}")


def manifest_path(n):
    return os.path.join(state_dir(n), "snapshot.json")


def pending(n):
    """The pending snapshot's manifest, or None."""
    try:
        with open(manifest_path(n), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def shared_files(game):
    """{rel path with '/': absolute path} of every file in the shared folders."""
    out = {}
    for d in SHARED_DIRS:
        root = os.path.join(game, *d.split("/"))
        for dirpath, _, files in os.walk(root):
            for f in files:
                p = os.path.join(dirpath, f)
                out[os.path.relpath(p, game).replace("\\", "/")] = p
    return out


def foreign_extensions(game):
    """Problems with plugins that would cross between the two projects: a DLL in a global extension folder (loads with
    every mod), or a copy of mxl2012-core in another mod's folder."""
    bad = []
    for d in GLOBAL_EXT:
        root = os.path.join(game, *d.split("/"))
        for dirpath, _, files in os.walk(root):
            for f in files:
                bad.append(f"{os.path.relpath(os.path.join(dirpath, f), game)}: global extension, loads with every mod")
    mods = os.path.join(game, "mods")
    for m in (os.listdir(mods) if os.path.isdir(mods) else []):
        if m.lower() == game_slots.MOD.lower():
            continue
        plug = os.path.join(mods, m, "d2rloader", "plugins")
        for f in (os.listdir(plug) if os.path.isdir(plug) else []):
            if f.lower().startswith("mxl2012-core"):
                bad.append(f"mods\\{m}\\d2rloader\\plugins\\{f}: our plugin in another mod's folder")
    return bad


def _lock_owner(n):
    info = game_slots.lock_info(n)
    return info[1].split()[0] if info and info[1] else None


def _need_lock(n, owner):
    if not owner or _lock_owner(n) != owner:
        raise SystemExit(f"slot {n}: shared files are only snapshotted or restored by the lock owner "
                         f"(game.lock.{n} is held by {_lock_owner(n)!r}, this run is {owner!r})")


def begin(n, owner, game=None):
    """Snapshot the shared files before a run. Returns a short message."""
    n = game_slots.require_slot(n)
    game = game or game_slots.slot_dir(n)
    game_slots.require_present(n, f"slot {n}: refusing the run", game)
    _need_lock(n, owner)
    msg = ""
    if pending(n):
        msg = "pending snapshot of an earlier run restored first: " + end(n, owner, game) + "; "
    bad = foreign_extensions(game)
    if bad:
        raise SystemExit(f"slot {n}: refusing the run, " + "; ".join(bad))
    # end() must be able to put every shared file back, and the run writes the harness file into our mod folder
    game_slots.need_write([os.path.join(game, *d.split("/")) for d in SHARED_DIRS] + sorted(shared_files(game).values())
                          + [os.path.join(game, "mods", game_slots.MOD)], f"slot {n}: refusing the run", root=game)
    snap = os.path.join(state_dir(n), "snapshot")
    shutil.rmtree(snap, ignore_errors=True)
    files = {}
    for rel, p in sorted(shared_files(game).items()):
        dst = os.path.join(snap, *rel.split("/"))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(p, dst)
        st = os.stat(p)
        files[rel] = {"sha256": sha256(p), "size": st.st_size, "mtime_ns": st.st_mtime_ns}
        if sha256(dst) != files[rel]["sha256"]:
            raise SystemExit(f"slot {n}: snapshot copy of {rel} differs (changed while copying?)")
    man = {"slot": n, "owner": owner, "game": os.path.abspath(game), "at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": files}
    tmp = manifest_path(n) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    os.replace(tmp, manifest_path(n))  # the manifest appears only once the copy is complete
    return msg + f"slot {n}: {len(files)} shared files snapshotted"


def diff(n, game=None, man=None):
    """[(rel, what)] of the shared files that differ from the pending snapshot: changed / created / deleted."""
    man = man or pending(n)
    if not man:
        return []
    game = game or man["game"]
    now = shared_files(game)
    out = []
    for rel, info in man["files"].items():
        if rel not in now:
            out.append((rel, "deleted"))
        elif os.path.getsize(now[rel]) != info["size"] or sha256(now[rel]) != info["sha256"]:
            out.append((rel, "changed"))
        elif os.stat(now[rel]).st_mtime_ns != info["mtime_ns"]:
            out.append((rel, "touched (same bytes, other mtime)"))
    out += [(rel, "created") for rel in sorted(set(now) - set(man["files"]))]
    return out


def end(n, owner, game=None, running=None):
    """Put the shared files back exactly as the pending snapshot has them. Refuses while a game runs in the slot
    (D2RLoader would write them again). Returns a short message naming what the run had changed."""
    n = game_slots.require_slot(n)
    man = pending(n)
    if not man:
        return f"slot {n}: no pending snapshot"
    game = game or man["game"]
    _need_lock(n, owner)
    procs = game_slots.slot_processes(game) if running is None else running
    if procs:
        raise SystemExit(f"slot {n}: game still running {procs}: stop it before the shared files are restored")
    changes = diff(n, game, man)
    try:
        _put_back(n, game, man, changes)
    except PermissionError as e:  # never elevated or retried another way: the snapshot and the lock stay
        raise SystemExit(f"slot {n}: restore refused, no write access to {e.filename} ({e.strerror}); snapshot kept in "
                         f"{state_dir(n)}; {game_slots.ELEVATION_NOTE}")
    left = diff(n, game, man)
    if left:
        raise SystemExit(f"slot {n}: restore incomplete, still different: {left} (snapshot kept in {state_dir(n)})")
    report = {"slot": n, "owner": owner, "snapshot_at": man["at"], "restored_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "changed_by_run": changes, "verified": "byte for byte and mtime, all %d files" % len(man["files"])}
    with open(os.path.join(state_dir(n), "last-restore.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    os.replace(manifest_path(n), os.path.join(state_dir(n), "last-snapshot.json"))
    return (f"slot {n}: shared files restored and verified ({len(man['files'])} files); the run had changed "
            + (", ".join(f"{r} ({w})" for r, w in changes) or "nothing"))


def _put_back(n, game, man, changes):
    """Write the snapshot's files back over `changes`, remove the files and empty folders the run created."""
    snap = os.path.join(state_dir(n), "snapshot")
    for rel, what in changes:
        dst = os.path.join(game, *rel.split("/"))
        if what == "created":
            os.remove(dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(snap, *rel.split("/")), dst)
            os.utime(dst, ns=(man["files"][rel]["mtime_ns"], man["files"][rel]["mtime_ns"]))
    # empty folders the run made inside the shared folders go too
    for d in SHARED_DIRS:
        root = os.path.join(game, *d.split("/"))
        for dirpath, dirs, files in sorted(os.walk(root), key=lambda t: -len(t[0])):
            if dirpath != root and not os.listdir(dirpath):
                rel = os.path.relpath(dirpath, game).replace("\\", "/") + "/"
                if not any(f.startswith(rel) for f in man["files"]):
                    os.rmdir(dirpath)


def release_state(n):
    """release-install.json of tools/release_install.py when the slot holds a player install, else None."""
    try:
        with open(os.path.join(game_slots.RUNS, f"release-install-s{n}", "release-install.json"), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return None


def wanted_args(n=None):
    """The launch arguments a mxl2012 run wants: env MXL_LAUNCH_ARGS, else the release's (release_install.py, slot n holds
    a player install), else DEV_ARGS."""
    words = os.environ.get("MXL_LAUNCH_ARGS")
    rel = release_state(n) if n is not None and words is None else None
    if words is None and rel is not None:
        words = rel.get("launch_arguments", "-w")
    args = list(DEV_ARGS) if words is None else words.split()
    if any(a.lower() == "-mod" for a in args):
        raise SystemExit("launch arguments must not name a mod: the mod of a mxl2012 run is always " + game_slots.MOD)
    return args


def toml_value(text, section, key):
    """The string value of `key` in [section] of a TOML text (uncommented line), or None."""
    cur = None
    for line in text.splitlines():
        t = line.strip().lstrip("\ufeff")
        if t.startswith("["):
            cur = t.strip("[] ")
        elif cur == section and not t.startswith("#") and "=" in t and t.split("=", 1)[0].strip() == key:
            v = t.split("=", 1)[1].strip()
            return json.loads(v) if v.startswith('"') else v
    return None


def launch_args(n, game=None):
    """The loader's command line words for a mxl2012 run (after the exe), ending in `-mod mxl2012`.

    D2RLoader starts the game with `<launch_arguments of the shared toml> <its own command line>` (slot 2, 2026-10-28:
    `D2RLoader-s2.exe -w -txt -mod mxl2012` -> `D2R command line: ... -w -txt -w -txt -mod mxl2012`), so words can only be
    added on the command line. When the shared toml already has every word it has, only the missing ones are passed.
    When it has a word the run must not have (a release run without -txt while the other mod keeps "-w -txt"), launch_arguments
    is set for this run only: that needs the pending snapshot of begin(), and end() puts the line back."""
    n = game_slots.require_slot(n)
    game = game or game_slots.slot_dir(n)
    want = wanted_args(n)
    toml = os.path.join(game, "d2rloader", "config", "d2rloader.toml")
    try:
        with open(toml, "rb") as f:
            text = f.read().decode("utf-8-sig")
    except FileNotFoundError:
        text = ""
    have = (toml_value(text, "d2rloader", "launch_arguments") or "").split()
    if all(w in want for w in have):
        return [w for w in want if w not in have] + ["-mod", game_slots.MOD]
    if not pending(n):
        raise SystemExit(f"slot {n}: the shared launch_arguments {have} hold words this run must not have ({want}); "
                         "they can only be changed inside a snapshot (begin)")
    new = game_slots.set_toml_value(text, "d2rloader", "launch_arguments", json.dumps(" ".join(want)))
    with open(toml, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    return ["-mod", game_slots.MOD]


# ---------------------------------------------------------------- before/after scans (reports only, read-only)

SCAN_SKIP = ("Data",)  # the CASC game data: read-only for D2R, large


def scan(game):
    out = {}
    for dirpath, dirs, files in os.walk(game):
        if os.path.normcase(dirpath) == os.path.normcase(game):
            dirs[:] = [d for d in dirs if d not in SCAN_SKIP]
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out[os.path.relpath(p, game).replace("\\", "/")] = [st.st_size, st.st_mtime_ns]
    return out


def compare(a, b):
    lines = []
    for rel in sorted(set(a) | set(b)):
        if rel not in a:
            lines.append(f"created  {rel} ({b[rel][0]} bytes)")
        elif rel not in b:
            lines.append(f"deleted  {rel}")
        elif a[rel] != b[rel]:
            lines.append(f"changed  {rel} ({a[rel][0]} -> {b[rel][0]} bytes)")
    return lines


def bootcheck(n, owner, timeout=90):
    """Start the slot's loader with launch_args() (no window, focus or input calls at all: SW_SHOWMINNOACTIVE), wait
    until d2rloader.log names the active mod and the mod's archive mount, kill the processes of this launch, restore the
    shared files and verify them. Returns (ok, log excerpt lines, restore message)."""
    import subprocess
    n = game_slots.require_slot(n)
    game = game_slots.slot_dir(n)
    if game_slots.slot_processes(game):
        raise SystemExit(f"slot {n}: a game is already running")
    loader = os.path.join(game, game_slots.loader_name(game))
    log = os.path.join(game, "d2rloader", "logs", "d2rloader.log")
    print(begin(n, owner, game))
    t0 = time.time()
    lines, ok = [], False
    try:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        args = launch_args(n)
        subprocess.Popen([loader] + args, cwd=game, startupinfo=si)
        print("launched " + os.path.basename(loader) + " " + " ".join(args))
        while time.time() - t0 < timeout:
            time.sleep(0.5)
            try:
                if os.stat(log).st_mtime < t0 - 1:
                    continue
                with open(log, encoding="utf-8-sig", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue
            if any("[CASC]" in l and "paths:" in l for l in lines):
                ok = True
                break
            if lines and not game_slots.slot_processes(game):
                break  # the game ended by itself
    finally:
        procs = game_slots.slot_processes(game)  # we hold the lock and nothing ran before: these are this launch's
        for pid, _ in procs:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        for _ in range(40):
            if not game_slots.slot_processes(game):
                break
            time.sleep(0.5)
        time.sleep(1)
        msg = end(n, owner, game)
    keep = [l for l in lines if any(k in l for k in ("D2RLoader command line", "D2R command line", "| name ", "modinfo.",
                                                       "default_mod", "launch_arguments", "plugins:", "[PLUGIN]", "paths:",
                                                       "patches:", "Active mod"))]
    return ok, keep, msg


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return 0
    c = a[0]
    game_slots.require_machine(f"slot_share {c}")
    if c == "compare":
        print("\n".join(compare(json.load(open(a[1])), json.load(open(a[2])))) or "no change")
        return 0
    n = game_slots.require_slot(a[1])
    if c == "status":
        man = pending(n)
        print(f"slot {n}: " + (f"PENDING snapshot of {man['owner']} at {man['at']} ({len(man['files'])} files)" if man
                               else "no pending snapshot"))
        bad = foreign_extensions(game_slots.slot_dir(n))
        print("extensions: " + ("; ".join(bad) if bad else "no plugin in the global folders, none of ours in another mod"))
    elif c == "diff":
        print("\n".join(f"{w:8} {r}" for r, w in diff(n)) or "no difference (or no pending snapshot)")
    elif c == "restore":
        print(end(n, os.environ.get("MXL_RUN")))
    elif c == "bootcheck":
        ok, keep, msg = bootcheck(n, os.environ.get("MXL_RUN"))
        print("\n".join(keep))
        print(msg)
        print("BOOTCHECK " + ("PASS" if ok and any(f'mod="{game_slots.MOD}"' in l for l in keep) else "FAIL"))
    elif c == "scan":
        json.dump(scan(game_slots.slot_dir(n)), open(a[2], "w", encoding="utf-8"))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
