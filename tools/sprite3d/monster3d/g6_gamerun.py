"""Stage 6: one short game run of a 3D monster on a test slot (a game check of lane hdtools-monster).

  python g6_gamerun.py [--token T] <slot 2|5> <tag> <overlay dir> [check=mon_card] [dll=1|<dll>] [on="<words>"]
                       [framework=<checkout>] [KEY=VALUE ...]

Under the slot lock: the overlay of s5_build.py gets the two index files it needs, made from the INSTALLED mod's own
(hd/character/monsters.json: the monster's monstats Id -> the new unit; hd/model_lod_desc.bin: the new model path with the
donor's entry and the new bounds); what the overlay replaces is backed up, the overlay is copied in, the check runs, everything
is put back byte for byte (also when the run fails) and the slot is unlocked. The check itself is read from the framework
checkout (framework=<dir>, else MXL_M3D_FRAMEWORK, else this checkout: lane hdtools-monster's checks mon_card / mon_turn are
merged here) and run without writing bytecode there; its run folder, the shots and the logs land in this monster's evidence
folder.
check=mon_turn (the 8 facings of monsterdir\\CAPTURE.md) needs the dev plugin with the harness word `facing`: dll=1 lays
MXL_M3D_DLL (machine.json m3d_dll), else the framework's build/plugin/Release/mxl2012-core.dll, over the slot's plugin for the
run (dll=<path> names another build); on=... writes mxl2012-core-on.txt next to it.
check=mon_death runs this lane's own capture step (g6_deathcap.py: mon_turn's flow with a burst of frames through the death)
through the same framework, slot tools and lock; it also needs dll=1. check=mon_moves runs g6_movecap.py the same way (bursts
of walk, attack and get-hit per facing).
Other KEY=VALUE pairs are extra environment of the check.

One code path on both systems: tools/game_slots.py picks the slot backend at run time. On Linux the check's game_ctl starts
the game on a private Xvfb display (never the owner's), snapshots the whole slot and restores it byte-equal, and copies the
slot's logs into the run folder before that restore (slot-logs-N/); this script reads the logs and crash reports from there.
The lock is taken with `game_slots.py lock` (a session lock the check's own unlock keeps), so this script's restore of the
overlay still runs under it.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import common

WT = common.WT
EV = common.HOME
LOCK = "hdtools-monster3d"
IDS = {"~k": "hardliner", "2(": "fungus1"}   # monstats Id: the key of hd/character/monsters.json
ARGS = [a for a in sys.argv[1:] if a not in ("--token", common.TOKEN)]
SLOT = int(ARGS[0])
TAG = ARGS[1]
OVERLAY = Path(ARGS[2])
EXTRA = dict(a.split("=", 1) for a in ARGS[3:])
# read only: its tools/game_checks.py has the checks (mon_card, mon_turn), its build the dev plugin
FWT = Path(EXTRA.pop("framework", "") or os.environ.get("MXL_M3D_FRAMEWORK") or WT).resolve()
DLL_ARG = EXTRA.pop("dll", "")
DLL = (Path(common.setting("MXL_M3D_DLL", "m3d_dll") or FWT / "build" / "plugin" / "Release" / "mxl2012-core.dll")
       if DLL_ARG == "1" else Path(DLL_ARG) if DLL_ARG else None)
ON = EXTRA.pop("on", "")
CHECK = EXTRA.pop("check", "mon_card")
if SLOT not in (2, 5):
    raise SystemExit("slot %d is not a 3.3 test slot of this lane" % SLOT)
sys.path.insert(0, str(WT / "tools"))
sys.path.insert(0, str(FWT / "tools"))      # the framework's slot tools first (seats: lanes linux-integration and later)
sys.dont_write_bytecode = True


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def py(*args, env=None, log=None, cwd=WT) -> int:
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", MXL_RUNS=str(EV / "runs"), **(env or {}))
    if log:
        with open(log, "w", encoding="utf-8", errors="replace") as f:
            return subprocess.run([sys.executable, *args], cwd=cwd, env=e, stdout=f, stderr=subprocess.STDOUT).returncode
    return subprocess.run([sys.executable, *args], cwd=cwd, env=e).returncode


def run_logs(runs: Path, t0: float):
    """{name: path} of the loader log, the plugin log and crash reports of this launch: the slot's live files (Windows),
    or the copies game_ctl made in the run folder before the whole-slot restore (Linux: <run>/slot-logs-N/)."""
    rel = {"loader": ("d2rloader", "logs", "d2rloader.log"), "mxl": ("mods", "mxl2012", "d2rloader", "logs", "mxl2012-core.log")}
    game = Path(game_slots.slot_dir(SLOT))
    roots = [game]
    for run in sorted(runs.glob("checks-*-s%d" % SLOT)):
        if run.is_dir() and run.stat().st_mtime >= t0 - 60:
            roots += sorted(run.glob("slot-logs-*"), key=lambda p: p.stat().st_mtime)
    out = {}
    for k, parts in rel.items():
        got = [r.joinpath(*parts) for r in roots if r.joinpath(*parts).is_file() and r.joinpath(*parts).stat().st_mtime >= t0 - 30]
        if got:
            out[k] = max(got, key=lambda p: p.stat().st_mtime)
    crashes = []
    for r in roots:
        for d in (r / "d2rloader" / "crashes", r / "d2rloader_crashes"):
            crashes += [f for f in (d.iterdir() if d.is_dir() else []) if f.is_file() and f.stat().st_mtime >= t0 - 30]
    return out, crashes


def main() -> int:
    load = common.cpu_percent()
    print("cpu %d%%" % load)
    if load >= 60:
        print("busy: no run")
        return 2
    backup = EV / "scratch" / ("backup-" + TAG)
    if backup.exists():
        raise SystemExit("tag %s was used before" % TAG)
    for d in ("logs", "shots", "runs", "scratch"):
        (EV / d).mkdir(exist_ok=True)
    os.environ["MXL_RUNS"] = str(EV / "runs")      # the check's run folder: here, not in the other lane's worktree
    global game_slots
    import game_slots
    # the slot lock and its seat (<locks>/budget.json) as a SESSION lock (pid 0, game_slots.release): the check's own
    # game_ctl stop leaves it, so the slot stays ours from laying the overlay until its restore, with no gap in which
    # another lane can take it (round 18: hdmaps2 took slot 5 between the check's unlock and our relock, and the
    # overlay was restored under its lock). It is removed only by our manual release at the end. If this script is
    # killed hard, the lock stays (never stale): `game_slots.py unlock N hdtools-monster3d` after restoring by hand
    # from <scratch>/backup-<tag>/state.json.
    def relock(wait):
        ok, msg = game_slots.acquire(SLOT, LOCK, pid=0, seat_wait=wait)
        print("lock:", msg)
        return ok

    def ours():
        info = game_slots.lock_info(SLOT)
        return bool(info) and bool(info[1]) and info[1].split()[0] == LOCK
    if not relock(float(os.environ.get("MXL_SEAT_WAIT") or 0)):
        print("slot %d is locked or no seat is free: no run" % SLOT)
        return 3
    import model_lod_desc
    mod_root = Path(game_slots.mod_dir(SLOT))
    mod = mod_root / "mxl2012.mpq" / "data"
    plugins = mod_root / "d2rloader" / "plugins"
    state = {"added": [], "replaced": {}, "dirs": []}
    rc = 1
    t0 = time.time()
    try:
        build = json.loads((OVERLAY.parent / "build.json").read_text(encoding="utf-8"))
        over = EV / "scratch" / ("overlay-" + TAG)
        shutil.copytree(OVERLAY, over)
        table_file, lod_file = mod / "hd/character/monsters.json", mod / "hd/model_lod_desc.bin"
        for f in (table_file, lod_file):
            if not f.is_file():
                raise SystemExit("the installed mod has no %s" % f.relative_to(mod))
        table = json.loads(table_file.read_text(encoding="utf-8"))
        mid = IDS[common.TOKEN]
        print("%s in the installed mod: %s -> %s" % (mid, table.get(mid), build["unit"]))
        table[mid] = build["unit"]
        (over / "hd/character/monsters.json").write_text(json.dumps(table, indent=4), encoding="utf-8")
        lo, hi = build["bounds"]
        u = build["u"]
        (over / "hd/model_lod_desc.bin").write_bytes(model_lod_desc.add(
            lod_file.read_bytes(), {build["model"]: build["donor_model"]},
            {build["model"]: ([v * u for v in lo], [v * u for v in hi])}))
        # (destination, source) of everything laid over the slot
        plan = [(mod / p.relative_to(over), p) for p in sorted(over.rglob("*")) if p.is_file()]
        backup.mkdir(parents=True, exist_ok=True)
        if DLL:
            if not DLL.is_file():
                raise SystemExit("dev plugin %s not found (dll=<path>, MXL_M3D_DLL or machine.json m3d_dll)" % DLL)
            plan.append((plugins / "mxl2012-core.dll", DLL))
        if ON:
            (backup / "mxl2012-core-on.txt").write_text(ON + "\n", encoding="ascii")
            plan.append((plugins / "mxl2012-core-on.txt", backup / "mxl2012-core-on.txt"))
        for n, (dest, _src) in enumerate(plan):
            key = str(dest)
            if dest.is_file():
                keep = backup / "files" / ("%04d_%s" % (n, dest.name))
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dest, keep)
                state["replaced"][key] = [str(keep), sha(dest)]
            else:
                state["added"].append(key)
                d = dest.parent
                while not d.exists():
                    state["dirs"].append(str(d))
                    d = d.parent
        (backup / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
        for dest, src in plan:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        print("laid over the slot: %d added, %d replaced%s" % (len(state["added"]), len(state["replaced"]),
                                                                "; plugin " + sha(plugins / "mxl2012-core.dll")[:12] if DLL else ""))
        # MXL_KEEP_RUN_FILES: the Linux run clean-up must not drop capture frames the sheets read
        env = {"MXL_RUN": LOCK, "MXL_SLOT": str(SLOT), "MXL_CHAR": "Montest", "MXL_DRAWCAP_PROBE": "1",
               "MXL_KEEP_RUN_FILES": "1", "MXL_M3D_FRAMEWORK": str(FWT), **EXTRA}
        t0 = time.time()
        own = {"mon_death": "g6_deathcap.py", "mon_moves": "g6_movecap.py"}
        runner = str(Path(__file__).resolve().parent / own[CHECK]) if CHECK in own else "tools/game_checks.py"
        rc = py(runner, "--slot", str(SLOT), "all", CHECK, env=env, log=EV / "logs" / ("run-%s.log" % TAG),
                cwd=FWT)
        print("game_checks exit %d after %d s" % (rc, time.time() - t0))
        dest = EV / "shots" / TAG
        dest.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in Path(game_slots.RUNS).glob("checks-*-s%d/*" % SLOT):
            if f.is_file() and f.stat().st_mtime >= t0 and f.suffix.lower() in (".png", ".md", ".json", ".txt"):
                shutil.copy2(f, dest / f.name)
                n += 1
        print("%d files of the run copied to %s" % (n, dest))
        try:
            py("tools/game_ctl.py", "--slot", str(SLOT), "stop", env={"MXL_RUN": LOCK, "MXL_SLOT": str(SLOT)}, cwd=FWT)
        except Exception as e:  # noqa: BLE001
            print("stop:", e)
        logs, crashes = run_logs(Path(game_slots.RUNS), t0)
        for k, p in logs.items():  # both logs start anew with each launch
            shutil.copyfile(p, EV / "logs" / ("%s-%s.log" % (k, TAG)))
        for f in crashes:          # crash reports of this launch, read only, for the evidence
            shutil.copy2(f, dest / f.name)
            print("crash report of this launch:", f.name)
    finally:
        try:
            py("tools/game_ctl.py", "--slot", str(SLOT), "stop", env={"MXL_RUN": LOCK, "MXL_SLOT": str(SLOT)}, cwd=FWT)
        except Exception as e:  # noqa: BLE001
            print("stop:", e)
        if not ours():
            # never touch a slot another lane holds: leave the restore to be done by hand under our lock later
            print("ERROR: slot %d's lock is not ours (%s); the overlay is NOT restored. Restore from %s once the slot "
                  "is ours again." % (SLOT, game_slots.lock_info(SLOT), backup / "state.json"))
            return 4
        bad = []
        for key in state["added"]:
            p = Path(key)
            if p.is_file():
                p.unlink()
        for key, (keep, digest) in state["replaced"].items():
            shutil.copyfile(keep, key)
            if sha(Path(key)) != digest:
                bad.append(key)
        for d in sorted(set(state["dirs"]), key=len, reverse=True):
            try:
                os.rmdir(d)
            except OSError:
                pass
        left = [k for k in state["added"] if Path(k).exists()] + [d for d in state["dirs"] if os.path.isdir(d)]
        print("restore: %d replaced files back byte-equal, %d added files removed; mismatches %s; left over %s"
              % (len(state["replaced"]) - len(bad), len(state["added"]), bad or "none", left or "none"))
        game_slots.release(SLOT, LOCK, manual=True)
        print("lock released:", game_slots.lock_info(SLOT) is None or game_slots.lock_info(SLOT))
    return rc


if __name__ == "__main__":
    sys.exit(main())
