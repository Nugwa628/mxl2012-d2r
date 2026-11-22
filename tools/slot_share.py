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

Linux slots (game_slots.LINUX, docs/testing.md "Linux slots"): the slot folder is ours alone, so the snapshot is the WHOLE
slot folder, not only d2rloader\\config: every file except the CASC archives Data/data/data.NNN is copied with rsync to the
slot's snapshot folder (game_slots.linux_slot: /d2work/slots/.snap-sN, kept between runs so the next copy is quick), the
archives get a size + mtime manifest. The game itself rewrites small files in Data/ (Data/data/*.idx, shmem) and D2RLoader
writes Data/hd/objects/dummy/d2rloader_stash_proxy.json, so Data/ is not skipped. The pending manifest sits beside the
snapshot (<snapshot>.json), so every checkout sees it. end() rsyncs back with --delete --checksum and verifies with a
checksum dry run (must list nothing) plus the archive manifest. A pending snapshot of the lane linuxslots prototype
(linslot.py, .snap-sN.data.json) refuses begin().

CLI: py -3 tools/slot_share.py status|diff|restore N     (restore needs MXL_RUN = the lock owner)
     MXL_RUN=<owner> py -3 tools/slot_share.py probe N add DLL...  the one exception to the empty global folders (lane
                                                          globalplugins): our own test plugins (gp-probe-*.dll of tools/gp_probe,
                                                          a mxl2012-core*.dll copy) go in d2rloader\\plugins for runs of this
                                                          lock only; `probe N clear` and every unlock remove them
     MXL_RUN=<owner> py -3 tools/slot_share.py bootcheck N   start the loader minimized with -mod mxl2012 (no window or
                                                          input calls), wait for the log's mod mount, kill it, restore
     py -3 tools/slot_share.py scan N OUT.json            list every file of the slot (size, mtime) for a before/after report
     py -3 tools/slot_share.py compare A.json B.json      what changed between two scans
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402
import loader_notice  # noqa: E402

SHARED_DIRS = ("d2rloader/config",)  # restored exactly after every run
GLOBAL_EXT = ("d2rloader/plugins", "d2rloader/patches")  # must hold no plugin of either project
# Launch arguments of our runs (the shared toml's launch_arguments are the other mod's and stay as they are). -w: windowed (the
# harness sizes and captures the window); -txt: compile the mod's TXT tables (developer install).
DEV_ARGS = ("-w", "-txt")


def state_dir(n):
    return os.path.join(game_slots.RUNS, f"slot-share-s{game_slots.require_slot(n)}")


def manifest_path(n):
    if game_slots.LINUX:  # beside the whole-slot snapshot: one per slot, seen by every checkout
        return game_slots.linux_slot(n)["snapshot"] + ".json"
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


def probe_path(n):
    return os.path.join(state_dir(n), "probe.json")


def probes(n):
    """{file name: sha256} of the test plugins `probe add` put in the slot's global plugin folder (lane globalplugins)."""
    try:
        with open(probe_path(n), encoding="utf-8") as f:
            return json.load(f)["files"]
    except (FileNotFoundError, ValueError, KeyError):
        return {}


def probe_add(n, owner, srcs, game=None):
    """The one exception to "the global folders stay empty" (docs/testing.md "Lane globalplugins"): with the slot lock held,
    copy test plugins into <slot>\\d2rloader\\plugins and list them (name and sha256) in probe.json. Only is_probe_name()
    (our own throw-away test DLLs of tools/gp_probe, and a copy of mxl2012-core for the second-copy check) and only into
    an empty folder or over files listed already. begin() lets exactly the listed files through; `probe clear` and every
    unlock remove them."""
    n = game_slots.require_slot(n)
    game = game or game_slots.slot_dir(n)
    _need_lock(n, owner)
    if game_slots.slot_processes(game):
        raise SystemExit(f"slot {n}: stop the game before test plugins are added")
    listed = probes(n)
    plug = os.path.join(game, "d2rloader", "plugins")
    for f in (os.listdir(plug) if os.path.isdir(plug) else []):
        if f not in listed:
            raise SystemExit(f"slot {n}: d2rloader\\plugins holds {f}, not a test plugin of ours: nothing added")
    for src in srcs:
        name = os.path.basename(src)
        if not is_probe_name(name):
            raise SystemExit(f"{name}: only gp-probe-*.dll and mxl2012-core*.dll may go in a global folder for a test")
        os.makedirs(plug, exist_ok=True)
        shutil.copy2(src, os.path.join(plug, name))
        listed[name] = sha256(os.path.join(plug, name))
    os.makedirs(state_dir(n), exist_ok=True)
    with open(probe_path(n), "w", encoding="utf-8") as f:
        json.dump({"slot": n, "owner": owner, "files": listed}, f, indent=1)
    return f"slot {n}: test plugins in d2rloader\\plugins: {', '.join(sorted(listed))}"


def probe_clear(n, game=None):
    """Remove the test plugins of probe.json from the global plugin folder (only files with the listed sha256), then
    probe.json. Refuses while the game runs (the DLLs are loaded)."""
    n = game_slots.require_slot(n)
    listed = probes(n)
    if not listed:
        return f"slot {n}: no test plugins"
    game = game or game_slots.slot_dir(n)
    if game_slots.slot_processes(game):
        raise SystemExit(f"slot {n}: game still running: stop it before the test plugins are removed")
    plug = os.path.join(game, "d2rloader", "plugins")
    for name, digest in listed.items():
        p = os.path.join(plug, name)
        if os.path.exists(p):
            if sha256(p) != digest:
                raise SystemExit(f"slot {n}: {p} changed since `probe add`: left in place, remove it by hand")
            os.remove(p)
    for name in listed:  # D2RLoader's log of a global test plugin (d2rloader\logs\<id>.log); copied to the run folder by the check
        log = os.path.join(game, "d2rloader", "logs", os.path.splitext(name)[0] + ".log")
        if name.lower().startswith("gp-probe-") and os.path.exists(log):
            os.remove(log)
    os.remove(probe_path(n))
    return f"slot {n}: test plugins removed ({', '.join(sorted(listed))})"


def is_probe_name(name):
    low = name.lower()
    return low.endswith(".dll") and (low.startswith("gp-probe-") or low.startswith("mxl2012-core"))


def foreign_extensions(game, n=None):
    """Problems with plugins that would cross between the two projects: a DLL in a global extension folder (loads with
    every mod), or a copy of mxl2012-core in another mod's folder. With slot `n`, the test plugins `probe add` listed
    (same name and sha256, in d2rloader\\plugins) are no problem."""
    bad = []
    listed = probes(n) if n is not None else {}
    for d in GLOBAL_EXT:
        root = os.path.join(game, *d.split("/"))
        for dirpath, _, files in os.walk(root):
            for f in files:
                p = os.path.join(dirpath, f)
                if d == "d2rloader/plugins" and dirpath == root and f in listed and sha256(p) == listed[f]:
                    continue
                bad.append(f"{os.path.relpath(p, game)}: global extension, loads with every mod")
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
    bad = foreign_extensions(game, n)
    if bad:
        raise SystemExit(f"slot {n}: refusing the run, " + "; ".join(bad))
    # end() must be able to put every shared file back, and the run writes the harness file into our mod folder
    game_slots.need_write([os.path.join(game, *d.split("/")) for d in SHARED_DIRS] + sorted(shared_files(game).values())
                          + [os.path.join(game, "mods", game_slots.MOD)], f"slot {n}: refusing the run", root=game)
    if game_slots.LINUX:
        return msg + linux_begin(n, owner, game)
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
    if man.get("kind") == "slot":
        return linux_diff(man, game)
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
    if man.get("kind") == "slot":
        return linux_end(n, owner, game, man)
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


# ---------------------------------------------------------------- Linux: the whole slot folder

ARCHIVES = ("Data", "data")  # the CASC archives data.NNN: 27 GB, only read by the game: size + mtime manifest
RSYNC_EXCLUDE = "/Data/data/data.[0-9]*"


def archives(game):
    """{name: [size, mtime_ns]} of the CASC archives Data/data/data.NNN."""
    base = os.path.join(game, *ARCHIVES)
    out = {}
    for f in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        if f.startswith("data.") and f[5:].isdigit():
            st = os.lstat(os.path.join(base, f))
            out[f] = [st.st_size, st.st_mtime_ns]
    return out


def rsync(*args):
    """rsync -a --delete of a slot (the CASC archives excluded on both sides); returns the CompletedProcess."""
    try:
        return subprocess.run(["rsync", "-a", "--delete", "--exclude", RSYNC_EXCLUDE, *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise SystemExit("rsync is not installed: the Linux slot snapshot needs it")


def linslot_marker(n):
    """The pending-snapshot marker of the lane linuxslots prototype (linslot.py), beside the same snapshot folder."""
    snap = game_slots.linux_slot(n)["snapshot"]
    return os.path.join(os.path.dirname(snap), f".snap-s{n}.data.json")


def itemized(lines):
    """[(rel, what)] from `rsync -n -i` lines run snapshot -> slot: what the run did to the slot."""
    out = []
    for line in lines:
        if not line.strip():
            continue
        item, _, rel = line.partition(" ")
        rel = rel.strip()
        if item == "*deleting":
            out.append((rel, "created"))
        elif "+++++++" in item:
            out.append((rel, "deleted"))
        elif len(item) > 3 and (item[2] == "c" or item[3] == "s"):
            out.append((rel, "changed"))
        else:
            out.append((rel, "touched (same bytes, other mtime or mode)"))
    return out


def linux_diff(man, game):
    """[(rel, what)] of everything in the slot folder that differs from the whole-slot snapshot (checksums), plus CASC
    archives whose size or mtime moved."""
    r = rsync("-n", "-i", "--checksum", man["snapshot"].rstrip("/") + "/", game.rstrip("/") + "/")
    if r.returncode:
        raise SystemExit(f"slot {man['slot']}: rsync compare failed: {r.stderr.strip()}")
    out = itemized(r.stdout.splitlines())
    now, old = archives(game), man.get("archives", {})
    out += [("/".join(ARCHIVES + (k,)), "archive changed (size or mtime)" if k in now and k in old else
             "archive created" if k in now else "archive deleted") for k in sorted(set(now) | set(old)) if now.get(k) != old.get(k)]
    return out


def linux_begin(n, owner, game):
    """The whole-slot snapshot of a Linux slot (see the module text); writes the pending manifest last."""
    if os.path.exists(linslot_marker(n)):
        raise SystemExit(f"slot {n}: linslot.py has a snapshot pending ({linslot_marker(n)}): run its `restore {n}` first")
    snap = game_slots.linux_slot(n)["snapshot"]
    os.makedirs(snap, exist_ok=True)
    r = rsync(game.rstrip("/") + "/", snap + "/")
    if r.returncode:
        raise SystemExit(f"slot {n}: snapshot copy failed: {r.stderr.strip()}")
    man = {"slot": n, "owner": owner, "game": os.path.abspath(game), "at": time.strftime("%Y-%m-%d %H:%M:%S"),
           "kind": "slot", "snapshot": snap, "archives": archives(game)}
    left = linux_diff(man, game)
    if left:
        raise SystemExit(f"slot {n}: snapshot differs from the slot right after the copy (something writes it?): {left[:10]}")
    man["count"] = sum(len(f) for _, _, f in os.walk(snap))
    tmp = manifest_path(n) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    os.replace(tmp, manifest_path(n))
    return f"slot {n}: whole slot snapshotted ({man['count']} files in {snap}, {len(man['archives'])} CASC archives by size+mtime)"


def linux_end(n, owner, game, man):
    if game_slots.prefix_pids(n):
        raise SystemExit(f"slot {n}: processes still run in the prefix {game_slots.prefix_dir(n)}: stop them first "
                         "(game_slots.stop_prefix)")
    changes = linux_diff(man, game)
    bad = [c for c in changes if c[1].startswith("archive")]
    if bad:
        raise SystemExit(f"slot {n}: CASC archives changed, they are not in the snapshot: {bad} (snapshot kept, fix by hand "
                         "from an identical copy)")
    r = rsync("--checksum", man["snapshot"].rstrip("/") + "/", game.rstrip("/") + "/")
    if r.returncode:
        raise SystemExit(f"slot {n}: restore failed: {r.stderr.strip()} (snapshot kept in {man['snapshot']})")
    left = linux_diff(man, game)
    if left:
        raise SystemExit(f"slot {n}: restore incomplete, still different: {left[:20]} (snapshot kept in {man['snapshot']})")
    os.makedirs(state_dir(n), exist_ok=True)
    report = {"slot": n, "owner": owner, "snapshot_at": man["at"], "restored_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "changed_by_run": changes, "verified": f"rsync checksums of all {man.get('count')} files (empty dry run), "
              f"size+mtime of {len(man['archives'])} CASC archives"}
    with open(os.path.join(state_dir(n), "last-restore.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    os.replace(manifest_path(n), os.path.join(state_dir(n), "last-snapshot.json"))
    return (f"slot {n}: whole slot restored and verified byte-equal ({man.get('count')} files, {len(man['archives'])} "
            f"archives); the run had changed {len(changes)} entries" + (": " + ", ".join(f"{r} ({w})" for r, w in changes[:12])
                                                                        + (" ..." if len(changes) > 12 else "") if changes else ""))


def window_helper():
    """The Win32 window helper run inside a slot's prefix (tools/wctl/wctl.exe, built by tools/wctl/build.sh, or env
    MXL_WCTL), or None. bootcheck uses it only to answer D2RLoader's notice and to close the game window."""
    p = os.environ.get("MXL_WCTL") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "wctl", "wctl.exe")
    return p if os.path.isfile(p) else None


def helper_notice(helper):
    """(find, post) for loader_notice.Watch through a linux_window.Helper: the prefix holds only this run's processes,
    so a visible #32770 dialog titled D2RLoader whose only push button is OK is our launch's notice (Wine's task
    dialog makes its check box a Button too; the log line of this launch is still required by Watch)."""
    def find(pids):
        return [w["hwnd"] for w in helper.windows()
                if w["visible"] and w["class"] == loader_notice.DIALOG_CLASS and w["title"] == loader_notice.DIALOG_TITLE
                and [t.replace("&", "") for t in helper.buttons(w["hwnd"], push_only=True)] == ["OK"]]

    def post(h):
        return helper.post(h, loader_notice.TDM_CLICK_BUTTON, loader_notice.IDOK, 0)
    return find, post


def helper_close(helper):
    """WM_CLOSE posted to the game window through the helper; a short note for the report."""
    r = helper.find("Diablo II: Resurrected")
    if not r:
        return "no game window"
    helper.post(r[0], 0x0010, 0, 0)
    return f"WM_CLOSE to window {r[0]}"


def bootcheck_linux(n, owner, timeout=90, hold=0):
    """bootcheck on a Linux slot: start the loader under Proton in the slot's prefix (launch_args), answer D2RLoader's
    3.4 notice through the window helper (when there is one), wait for the mod mount in d2rloader.log with the game
    process alive (/proc; on 3.4 that is D2RLoader itself, it runs the game in-process), keep it `hold` seconds,
    measure focus all along (game_slots.FocusWatch: a grab stops the run and fails it), close it (WM_CLOSE through the helper, else and after 30 s
    `wineserver -k` of this prefix only), wait for the prefix to be idle, restore and verify the whole slot."""
    n = game_slots.require_slot(n)
    game = game_slots.slot_dir(n)
    if game_slots.slot_processes(game) or game_slots.prefix_pids(n):
        raise SystemExit(f"slot {n}: something already runs in the prefix {game_slots.prefix_dir(n)}")
    log = os.path.join(game, "d2rloader", "logs", "d2rloader.log")
    exe = window_helper()
    print(begin(n, owner, game))
    out_dir = os.path.join(state_dir(n), "bootcheck")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    lines, ok, pids, seen = [], False, [], {}
    focus = game_slots.FocusWatch(n).start()  # owner rule: the game never takes focus; measured from before the launch
    import linux_window  # the game runs on a private display (never the owner's: there it takes the focus)
    xdisplay, xpid, helper = None, None, None
    try:
        xdisplay, xpid = linux_window.PrivateDisplay.start(log_path=os.path.join(out_dir, "xvfb.log"))
        game_env = dict(linux_window.PRIVATE_ENV, DISPLAY=xdisplay)
        print(f"private display {xdisplay} (Xvfb pid {xpid})")
        if exe:
            helper = linux_window.Helper(linux_window.slot_env(n), exe=exe, extra_env=game_env,
                                         stderr_path=os.path.join(out_dir, "wctl-stderr.log"))
        args = launch_args(n)
        with open(os.path.join(out_dir, "proton.out"), "w") as out:
            proc = game_slots.launch(n, args, log_dir=out_dir, stdout=out, extra_env=game_env)
        print(f"launched D:\\{game_slots.loader_name(game)} {' '.join(args)} under Proton (prefix {game_slots.prefix_dir(n)}, "
              f"display {xdisplay})")
        notice = loader_notice.Watch(log, started=t0, find=helper_notice(helper)[0], post=helper_notice(helper)[1]) \
            if helper else None
        while time.time() - t0 < timeout:
            time.sleep(1)
            if focus.grabs:
                print("the game took focus: stopping the run (owner rule: no focus stealing)")
                ok = False
                break
            procs = game_slots.slot_processes(game)
            for pid, nm in procs:
                seen.setdefault(pid, nm)
            pids = [p for p, _ in procs]
            if notice:
                said = notice.poll(pids)
                if said:
                    print(said)
            elif loader_notice.log_has_notice(log, t0):
                print("D2RLoader shows its notice for an untested D2R and there is no window helper (MXL_WCTL): stopping")
                break
            try:
                if os.stat(log).st_mtime < t0 - 1:
                    continue
                with open(log, encoding="utf-8-sig", errors="replace") as f:
                    lines = f.read().splitlines()
            except OSError:
                continue
            ok = any("[CASC]" in l and "paths:" in l for l in lines)
            if ok and procs:  # D2RLoader 1.3.1 on 3.4 runs the game inside its own process (no separate D2R.exe)
                print(f"game up after {time.time() - t0:.0f} s: " + ", ".join(f"{nm} pid {p}" for p, nm in sorted(seen.items())))
                end_hold = time.time() + hold
                while time.time() < end_hold and not focus.grabs:
                    time.sleep(0.5)
                break
            if proc.poll() is not None and not procs:
                break  # the game ended by itself
    finally:
        closed = ""
        if helper and game_slots.slot_processes(game):
            try:
                closed = helper_close(helper)
            except linux_window.HelperError as e:
                closed = f"helper: {e}"
            for _ in range(60):
                if not game_slots.slot_processes(game):
                    break
                time.sleep(0.5)
        if game_slots.slot_processes(game) or game_slots.prefix_pids(n):
            idle = game_slots.wait_prefix_idle(n, 20) if closed else False
            if not idle:
                closed += "; wineserver -k (this prefix only)"
                game_slots.stop_prefix(n)
        if helper:
            helper.close()
        print(f"closed: {closed or 'nothing left running'}; prefix idle: {not game_slots.prefix_pids(n)}")
        if xpid:
            print(f"private display {xdisplay}: {'ended' if linux_window.PrivateDisplay.stop(xpid, xdisplay) else 'STILL RUNNING'}")
        said = focus.stop()
        print(said)
        with open(os.path.join(out_dir, "focus.json"), "w", encoding="utf-8") as f:
            json.dump({"before": focus.before, "polls": focus.polls, "changes": focus.changes, "grabs": focus.grabs}, f, indent=1)
        msg = end(n, owner, game)
    keep = [l for l in lines if any(k in l for k in ("D2RLoader command line", "D2R command line", "| name ", "modinfo.",
                                                       "default_mod", "launch_arguments", "plugins:", "[PLUGIN]", "paths:",
                                                       "patches:", "Active mod", "hasn't been fully tested"))]
    keep.append("game processes seen: " + (", ".join(f"{nm} pid {p}" for p, nm in sorted(seen.items())) or "none"))
    keep.append(said)
    return ok and not focus.grabs, keep, msg


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
    shared files and verify them. On a D2R that this D2RLoader has not been tested with (3.4 with D2RLoader 1.3.1) the
    loader first shows a notice and waits: it is answered in the background (loader_notice.py).
    Returns (ok, log excerpt lines, restore message)."""
    if game_slots.LINUX:
        return bootcheck_linux(n, owner, timeout, hold=float(os.environ.get("MXL_BOOTCHECK_HOLD") or 0))
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
        notice = loader_notice.Watch(log, started=t0)
        while time.time() - t0 < timeout:
            time.sleep(0.5)
            said = notice.poll([pid for pid, _ in game_slots.slot_processes(game)])
            if said:
                print(said)
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
        print(f"slot {n}: " + (f"PENDING snapshot of {man['owner']} at {man['at']} ({man.get('count', len(man.get('files', {})))} files)" if man
                               else "no pending snapshot"))
        bad = foreign_extensions(game_slots.slot_dir(n))
        print("extensions: " + ("; ".join(bad) if bad else "no plugin in the global folders, none of ours in another mod"))
        if probes(n):
            print("test plugins (probe add): " + ", ".join(sorted(probes(n))))
    elif c == "probe" and len(a) >= 3 and a[2] == "add":
        print(probe_add(n, os.environ.get("MXL_RUN"), a[3:]))
    elif c == "probe" and len(a) >= 3 and a[2] == "clear":
        _need_lock(n, os.environ.get("MXL_RUN"))
        print(probe_clear(n))
    elif c == "diff":
        print("\n".join(f"{w:8} {r}" for r, w in diff(n)) or "no difference (or no pending snapshot)")
    elif c == "restore":
        print(end(n, os.environ.get("MXL_RUN")))
    elif c == "bootcheck":
        ok, keep, msg = bootcheck(n, os.environ.get("MXL_RUN"))
        print("\n".join(keep))
        print(msg)
        passed = ok and any(f'mod="{game_slots.MOD}"' in l for l in keep)
        print("BOOTCHECK " + ("PASS" if passed else "FAIL"))
        if game_slots.LINUX and not passed:
            return 1  # Linux: scripts stop on a failed boot or a focus grab
    elif c == "scan":
        json.dump(scan(game_slots.slot_dir(n)), open(a[2], "w", encoding="utf-8"))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
