"""Slot part of the sign-off: one foreground game run of check `signoff` (gamecheck.py). Two backends, chosen at run time
(config.backend: by platform unless the settings name one):

Linux, run_linux() (called in-process by cli.py):
  the framework's own slot tools (settings linux.framework_tools: game_checks.py, game_ctl.py with game_ctl_linux.py,
  game_slots.py, slot_share.py). The run's flow is game_checks' Linux flow: slot lock -> whole-slot snapshot -> the plan
  laid in by a pre-launch hook (game_ctl.PRE_LAUNCH: the unit's overlay with the two index files made from the installed
  mod's own, and the dev plugin) -> the game on a private X display (never the owner's desktop; captures come from that
  display only, focus watched) -> the check -> stop -> whole-slot restore, verified byte-equal -> unlock. The restore takes
  the plan out again, also when the run fails. A run left pending (killed check) is stopped and restored here.

Windows, main() (started by cli.py under the heavy lock):
  py -3 run.py <tag> --slot N --token T --id <monstats Id> --overlay <dir with build.json beside it> [KEY=VALUE ...]
  one foreground game run through monster3d's g6_gamerun.py (settings windows.gamerun), unchanged: CPU check, slot lock,
  overlay backed up, laid over and restored byte for byte (also on failure), the dev plugin (dll=1, for the harness verb
  `facing`), stop, unlock. This driver only names the lock holder (settings lock_holder), adds the unit's token -> monstats
  Id, points g6_gamerun's runner for `mon_moves` at gamecheck.py and sends the evidence to --ev.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))            # the folder holding the hdkit package (also when run as a script)

from hdkit.signoff import config  # noqa: E402


# ---------------------------------------------------------------- Linux

def cpu_load() -> int:
    """The 1-minute load average as a share of the CPUs, in % (the Linux stand-in for g6_gamerun's CPU counter)."""
    return int(round(100.0 * os.getloadavg()[0] / (os.cpu_count() or 1)))


def overlay_plan(overlay: Path, build: dict, mid: str, mod_data: Path, work: Path, model_lod_desc) -> list:
    """[(destination, source)] of the unit's overlay over the slot's mod data: a copy of the overlay in `work` with
    hd/character/monsters.json (the monstats Id -> the new unit) and hd/model_lod_desc.bin (the new model with the donor's
    entry and the new bounds) made from the INSTALLED mod's own files, as monster3d's g6_gamerun does."""
    table_file, lod_file = mod_data / "hd/character/monsters.json", mod_data / "hd/model_lod_desc.bin"
    for f in (table_file, lod_file):
        if not f.is_file():
            raise SystemExit("the installed mod has no %s" % f)
    if work.exists():
        raise SystemExit("%s exists: the tag was used before" % work)
    shutil.copytree(overlay, work)
    table = json.loads(table_file.read_text(encoding="utf-8"))
    table[mid] = build["unit"]
    (work / "hd/character").mkdir(parents=True, exist_ok=True)
    (work / "hd/character/monsters.json").write_text(json.dumps(table, indent=4), encoding="utf-8")
    lo, hi = build["bounds"]
    u = build["u"]
    (work / "hd/model_lod_desc.bin").write_bytes(model_lod_desc.add(
        lod_file.read_bytes(), {build["model"]: build["donor_model"]},
        {build["model"]: ([v * u for v in lo], [v * u for v in hi])}))
    return [(mod_data / p.relative_to(work), p) for p in sorted(work.rglob("*")) if p.is_file()]


def copy_run(runs: Path, slot: int, t0: float, dest: Path) -> int:
    """The run folder's small files (png, md, json, txt, log) of this run -> dest (the sheet reads them there)."""
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in runs.glob("checks-*-s%d/*" % slot):
        if f.is_file() and f.stat().st_mtime >= t0 and f.suffix.lower() in (".png", ".md", ".json", ".txt", ".log"):
            shutil.copy2(f, dest / f.name)
            n += 1
    return n


def run_linux(s: dict, tag: str, slot: int, token: str, mid: str, overlay: Path, ev: Path, env: dict, dll=None,
              log=print) -> int:
    """One sign-off game run on a Linux test slot (see the module text). ev = <evidence>/game; the unit's files land in
    ev/<name>/{shots/<tag>, logs, runs, scratch} as on Windows. Returns the check's exit code (2: busy, 3: slot locked)."""
    fw = Path(config.need(s, "linux", "framework_tools"))
    fe = s["framework_env"]
    holder = s["lock_holder"]
    if str(fw) not in sys.path:
        sys.path.insert(0, str(fw))
    import game_slots
    import model_lod_desc
    import slot_share
    helper = fw / "wctl" / "wctl.exe"
    if not helper.is_file():   # the window helper under Wine (git-ignored, built per checkout): without it no clean stop
        log("no %s: build it with %s first (no run)" % (helper, fw / "wctl" / "build.sh"))
        return 4
    known = s["units"].get(token) or {}
    name = known.get("name") or "".join(c if c.isalnum() else "%02x" % ord(c) for c in token.lower())
    home = Path(ev) / name
    for d in ("logs", "shots", "runs", "scratch"):
        (home / d).mkdir(parents=True, exist_ok=True)
    load = cpu_load()
    log("cpu %d%% (load average over %d CPUs)" % (load, os.cpu_count() or 1))
    if load >= int(s["linux"].get("cpu_max") or 60):
        log("busy: no run")
        return 2
    info = game_slots.lock_info(slot)
    if info:
        log("slot %d is locked (%s): no run" % (slot, info[1]))
        return 3
    mod_root = Path(game_slots.mod_dir(slot))
    mod_data = mod_root / config.need(s, "linux", "mod_data")
    build = json.loads((Path(overlay).parent / "build.json").read_text(encoding="utf-8"))
    plan = overlay_plan(Path(overlay), build, mid, mod_data, home / "scratch" / ("overlay-" + tag), model_lod_desc)
    dll = dll or s["linux"].get("dev_plugin")
    if dll:
        if not Path(dll).is_file():
            raise SystemExit("dev plugin %s is missing" % dll)
        plan.append((mod_root / config.need(s, "linux", "plugin_dest"), Path(dll)))
    plan_file = home / "scratch" / ("plan-%s.json" % tag)
    plan_file.write_text(json.dumps({"slot": slot, "game": str(game_slots.slot_dir(slot)),
                                     "files": [[str(d), str(p)] for d, p in plan]}, indent=1), encoding="utf-8")
    log("plan: %d files into slot %d (%s)%s" % (len(plan), slot, plan_file, "; plugin %s" % dll if dll else ""))
    e = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HDKIT_SIGNOFF_ID=mid, HDKIT_SIGNOFF_PLAN=str(plan_file),
             HDKIT_SIGNOFF_FWT=str(fw), HDKIT_SIGNOFF_CAPTURE=json.dumps(s["capture"]),
             HDKIT_SIGNOFF_TABLES=str(mod_data / "global" / "excel"))
    e.update({fe["run"]: holder, fe["slot"]: str(slot), fe["runs"]: str(home / "runs")})
    e.update({k: str(v) for k, v in (s["linux"].get("env") or {}).items()})
    e.update(env)
    t0 = time.time()
    run_log = home / "logs" / ("run-%s.log" % tag)
    runs_before = game_slots.RUNS      # the check's run state (snapshot manifest, restore record) is under its own runs
    game_slots.RUNS = str(home / "runs")
    try:
        return _run_check(s, slot, holder, fw, e, t0, run_log, home, tag, game_slots, slot_share, log)
    finally:
        game_slots.RUNS = runs_before


def _run_check(s, slot, holder, fw, e, t0, run_log, home, tag, game_slots, slot_share, log) -> int:
    rc = 1
    try:
        with open(run_log, "w", encoding="utf-8", errors="replace") as f:
            rc = subprocess.run([sys.executable, str(HERE / "gamecheck.py"), "--slot", str(slot), "all", "signoff"],
                                cwd=str(fw), env=e, stdout=f, stderr=subprocess.STDOUT).returncode
    finally:
        # the check stops, restores and unlocks itself; a check that died before (killed, crashed) left it pending
        if slot_share.pending(slot) or (game_slots.lock_info(slot) or ("", ""))[1].split(" ")[0] == holder:
            log("slot %d left pending by the check: game_ctl stop (restore, unlock)" % slot)
            subprocess.run([sys.executable, str(fw / "game_ctl.py"), "--slot", str(slot), "stop"], cwd=str(fw),
                           env=dict(e))
    log("check exit %d after %d s (log %s)" % (rc, time.time() - t0, run_log))
    dest = home / "shots" / tag
    n = copy_run(home / "runs", slot, t0, dest)
    restore = Path(slot_share.state_dir(slot)) / "last-restore.json"
    if restore.is_file() and restore.stat().st_mtime >= t0:
        shutil.copy2(restore, dest / "slot-restore.json")
        r = json.loads(restore.read_text(encoding="utf-8"))
        log("restore: %s; the run had changed %d entries" % (r.get("verified"), len(r.get("changed_by_run") or [])))
    else:
        log("restore: NO restore record of this run in %s" % restore)
    info = game_slots.lock_info(slot)
    log("%d files of the run copied to %s; slot %d lock %s; snapshot pending: %s" % (
        n, dest, slot, "held by %s" % info[1] if info else "free", bool(slot_share.pending(slot))))
    return rc


# ---------------------------------------------------------------- Windows (monster3d g6_gamerun.py)

def main(argv=None) -> int:
    s = config.settings()
    w = s["windows"]
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--slot", type=int, default=s["slot"])
    ap.add_argument("--token", required=True)
    ap.add_argument("--id", required=True, help="monstats Id")
    ap.add_argument("--overlay", required=True)
    ap.add_argument("--ev", default=os.environ.get("HDKIT_SIGNOFF_EV") or str(Path(config.need(s, "ev")) / "game"))
    ap.add_argument("kv", nargs="*")
    a = ap.parse_args(argv)
    if s["slots"] and a.slot not in [int(n) for n in s["slots"]]:
        raise SystemExit("slot %d is not one of the test slots %s of the settings" % (a.slot, s["slots"]))
    gamerun = Path(config.need(s, "windows", "gamerun"))
    os.environ[config.need(s, "windows", "m3d_env")] = a.ev
    fwt = Path(config.need(s, "windows", "framework_tools"))
    os.environ["HDKIT_SIGNOFF_FWT"] = str(fwt)
    if w.get("framework_env"):         # g6_gamerun's own framework = the one gamecheck.py drives (tools/..)
        os.environ[w["framework_env"]] = str(fwt.parent)
    check, runner = config.need(s, "windows", "check"), config.need(s, "windows", "runner")
    os.environ["HDKIT_SIGNOFF_ALIAS"] = check
    os.environ["HDKIT_SIGNOFF_CAPTURE"] = json.dumps(s["capture"])
    Path(a.ev).mkdir(parents=True, exist_ok=True)
    sys.argv = [str(gamerun), "--token", a.token, str(a.slot), a.tag, a.overlay, "check=" + check,
                "dll=1", "HDKIT_SIGNOFF_ID=" + a.id] + list(a.kv)
    sys.path.insert(0, str(gamerun.parent))
    sys.dont_write_bytecode = True
    import g6_gamerun as gr
    gr.LOCK = s["lock_holder"]
    Path(gr.EV).mkdir(parents=True, exist_ok=True)      # a fresh evidence folder: g6_gamerun makes only its subfolders
    gr.IDS.setdefault(a.token, a.id)
    _py = gr.py

    def py(*args, **kw):
        if args and Path(str(args[0])).name == runner:
            args = (str(HERE / "gamecheck.py"),) + args[1:]
        return _py(*args, **kw)

    gr.py = py
    return gr.main()


if __name__ == "__main__":
    sys.exit(main())
