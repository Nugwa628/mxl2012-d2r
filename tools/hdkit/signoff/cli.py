"""python -m hdkit.signoff <command> <token> [options]: in-game sign-off of a 3D unit against hdkit.view.

Commands:
  all <token>     prep + run + views: the whole sign-off, one sheet
  prep <token>    lay out the unit's build overlay (a monster3d stage: its small files, its large ones from the art store
                  by the stage folder's ART-MANIFEST.json, hash-checked) as <ev>/build/<stage>/overlay + build.json
  run <token>     one foreground game run on a test slot (run.py; the backend is chosen at run time, config.backend):
                  Linux: the slot tools of the framework (slot lock, whole-slot snapshot, overlay and dev plugin laid in
                  before the launch, private X display, captures from that display only, restore, unlock);
                  Windows: the heavy lock -> run.py -> monster3d g6_gamerun.py (CPU check, slot lock, overlay laid over
                  and restored byte for byte, dev plugin, stop, unlock). Both run check `signoff` (gamecheck.py): spawn,
                  cast the modes, kill, frames per facing key, labelled by the harness verb `facing`
  views <token>   render every captured (key, mode) in hdkit.view at the polled dir64 and time, compare
                  (hdkit.view.compare), one sheet game | viewer | outlines with the numbers

Options (defaults come from the settings, hdkit.signoff.config: the site adapter, HDKIT_SIGNOFF_CONFIG or --config):
  --modes nu,a1,gh,dt,dd   unit modes (codes)        --facings 0,2,4,6   facing keys (0 = screen bottom, clockwise)
  --area N --spot x,y      level id and sub-tile spot --tod-wait S        wait S seconds in the area first (time of day)
  --reach 3                spawn distance (sub-tiles) --tries 3           attempts per facing key: the character is
                           put where the spawned unit faces the asked key; missing or wrong-key modes are tried again
  --slot N                 test slot (one of `slots`) --tag NAME          run tag (default signoff-<unit>-<time>)
  --stage <stage under m3d_ev>  --id <monstats Id>    (defaults for the units the settings know by token)
  --rig game --no-glow     viewer rig and glow       --glow-off          test build without particle glow
                                                     (hdkit.view has no particle runtime)       --sheet <png>       sheet path (default <ev>/sheet_<tag>.png)
  --ev DIR                 evidence folder           --dll PATH          Linux: plugin DLL laid over the slot for the run
  --config JSON            settings over the site's

Run with a python that has wgpu (the viewer); on Windows `run` starts the game part with `py -3` itself.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config

HERE = Path(__file__).resolve().parent


def store_root(s=None) -> Path:
    return Path(config.need(s or config.settings(), "art_store"))


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build_name(stage: str, glow_off: bool) -> str:
    return Path(stage).name + ("-glowoff" if glow_off else "")


def prep(stage: str, ev: Path, log=print, glow_off: bool = False, s=None) -> Path:
    """<ev>/build/<stage name>[-glowoff]/overlay (+ build.json): the stage's overlay, complete. Returns the overlay folder.
    glow_off: a test copy with every renderer of every .particles file switched off (tools/hd_particles.py `hide *`),
    because hdkit.view has no particle runtime yet; the stage itself and the slot's mod are not changed."""
    s = s or config.settings()
    m3d = Path(config.need(s, "m3d_ev"))
    src = m3d / stage
    dest = Path(ev) / "build" / build_name(stage, glow_off)
    over = dest / "overlay"
    man = json.loads((m3d / "ART-MANIFEST.json").read_text(encoding="utf-8"))
    pre = stage.rstrip("/") + "/overlay/"
    want = {e["path"][len(pre):]: e["sha256"] for e in man["files"] if e["path"].startswith(pre)}
    n_local = n_store = 0
    for f in (src / "overlay").rglob("*"):
        if f.is_file():
            t = over / f.relative_to(src / "overlay")
            t.parent.mkdir(parents=True, exist_ok=True)
            if not t.is_file() or t.stat().st_size != f.stat().st_size or sha(t) != sha(f):
                shutil.copyfile(f, t)
            n_local += 1
    for rel, digest in want.items():
        t = over / rel
        if t.is_file() and sha(t) == digest:
            n_store += 1
            continue
        obj = store_root(s) / "objects" / "sha256" / digest[:2] / digest
        if not obj.is_file():
            raise SystemExit("art store object missing for %s%s" % (pre, rel))
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(obj, t)
        if sha(t) != digest:
            raise SystemExit("store object differs: %s%s" % (pre, rel))
        n_store += 1
    shutil.copyfile(src / "build.json", dest / "build.json")
    hidden = []
    if glow_off:
        sys.path.insert(0, str(HERE.parents[1]))
        import hd_particles
        for f in sorted(over.rglob("*.particles")):
            f.write_bytes(hd_particles.apply(f.read_bytes(), {"hide": "*"}))
            hidden.append(f.name)
    log("overlay %s: %d local files, %d from the art store%s" % (over, n_local, n_store,
                                                               "; particles off: %s" % hidden if glow_off else ""))
    return over


def run(a, overlay: Path) -> int:
    """One game run on a test slot; the backend (config.backend) picks the slot tools of this platform."""
    s = a.settings
    env = {"HDKIT_SIGNOFF_MODES": a.modes, "HDKIT_SIGNOFF_KEYS": a.facings, "HDKIT_SIGNOFF_AREA": "%d" % a.area,
           "HDKIT_SIGNOFF_TODWAIT": "%g" % a.tod_wait, "HDKIT_SIGNOFF_REACH": "%d" % a.reach,
           "HDKIT_SIGNOFF_TRIES": "%d" % a.tries}
    if a.spot:
        env["HDKIT_SIGNOFF_SPOT"] = a.spot
    t0 = time.time()
    if config.backend(s) == "linux":
        from . import run as R
        print("linux backend: slot %d, run %s, evidence %s" % (a.slot, a.tag, a.ev / "game"), flush=True)
        rc = R.run_linux(s, a.tag, a.slot, a.token, a.id, overlay, a.ev / "game", env, dll=a.dll)
    else:
        w = s["windows"]
        cmd = ["py", "-3", config.need(s, "windows", "heavy_lock"), w.get("heavy_token") or "game", s["lock_holder"], "--",
               "py", "-3", str(HERE / "run.py"), a.tag, "--slot", str(a.slot), "--token", a.token, "--id", a.id,
               "--overlay", str(overlay), "--ev", str(a.ev / "game")] + ["%s=%s" % kv for kv in env.items()]
        print(" ".join(cmd), flush=True)
        rc = subprocess.run(cmd, cwd=str(Path(config.need(s, "windows", "worktree_root")))).returncode
    print("game run exit %d after %d s" % (rc, time.time() - t0), flush=True)
    return rc


def shots_dir(a) -> Path:
    return a.ev / "game" / a.name / "shots" / a.tag


def views(a, overlay: Path) -> dict:
    from . import views as V
    sd = shots_dir(a)
    index = json.loads((sd / "signoff_index.json").read_text(encoding="utf-8"))
    build = json.loads((overlay.parent / "build.json").read_text(encoding="utf-8"))
    asset = "hd/character/enemy/%s.json" % build["unit"]
    roots = ["build=%s" % overlay, "base=%s" % config.need(a.settings, "base_root")]
    res = V.render_all(index, sd, roots, asset, a.ev / "views" / a.tag, a.rig, a.glow)
    modes = [m for m in a.modes.split(",") if m]
    keys = [int(k) for k in a.facings.split(",") if k]
    title = "In-game sign-off: %s (token %s, %s) on slot %d, area %d, run %s | viewer: hdkit.view, rig %s" % (
        a.id, a.token, build_name(a.stage, a.glow_off), a.slot, a.area, a.tag, a.rig)
    path = V.sheet(res, a.sheet or a.ev / ("sheet_%s.png" % a.tag), title, modes, keys)
    summary = {"tag": a.tag, "token": a.token, "id": a.id, "stage": a.stage, "slot": a.slot, "area": a.area,
               "modes": modes, "keys": keys, "sheet": str(path), "shots": str(sd), "results": res}
    (a.ev / ("signoff_%s.json" % a.tag)).write_text(json.dumps(summary, indent=1, default=str) + "\n", encoding="utf-8")
    print("sheet: %s" % path)
    return summary


def build_parser(s=None):
    s = s or config.settings()
    ap = argparse.ArgumentParser(prog="python -m hdkit.signoff")
    ap.add_argument("cmd", choices=("all", "prep", "run", "views"))
    ap.add_argument("token")
    ap.add_argument("--id", default=None)
    ap.add_argument("--stage", default=None)
    ap.add_argument("--modes", default=s["modes"])
    ap.add_argument("--facings", default=s["facings"])
    ap.add_argument("--area", type=int, default=s["area"])
    ap.add_argument("--spot", default=None)
    ap.add_argument("--tod-wait", type=float, default=0.0)
    ap.add_argument("--reach", type=int, default=s["reach"])
    ap.add_argument("--tries", type=int, default=s["tries"], help="attempts per facing key (missing or wrong-key modes again)")
    slots = [int(n) for n in s["slots"]]
    ap.add_argument("--slot", type=int, default=s["slot"] if s["slot"] is not None else (slots[0] if slots else None),
                    choices=slots or None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--rig", default="game")
    ap.add_argument("--no-glow", dest="glow", action="store_false", default=True)
    ap.add_argument("--glow-off", action="store_true", help="test build: particle glow off in game and viewer")
    ap.add_argument("--sheet", default=None)
    ap.add_argument("--ev", type=Path, default=Path(s["ev"]) if s["ev"] else None)
    ap.add_argument("--dll", default=None, help="Linux backend: plugin DLL laid over the slot for the run "
                                                "(default: setting linux.dev_plugin)")
    ap.add_argument("--config", default=None, help="JSON settings file over the site's (hdkit.signoff.config)")
    return ap


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", default=None)
    s = config.settings(pre.parse_known_args(argv)[0].config)
    a = build_parser(s).parse_args(argv)
    a.settings = s
    if a.ev is None:
        raise SystemExit("hdkit.signoff: no evidence folder: give --ev or set runs_root / ev")
    if a.slot is None and a.cmd in ("all", "run"):
        raise SystemExit("hdkit.signoff: no test slot: give --slot or set slots")
    known = s["units"].get(a.token)
    if (a.id is None or a.stage is None) and known is None:
        raise SystemExit("token %s: give --id <monstats Id> and --stage <monster3d stage>" % a.token)
    a.id = a.id or known["id"]
    a.stage = a.stage or known["stage"]
    a.name = known["name"] if known else "".join(c if c.isalnum() else "%02x" % ord(c) for c in a.token.lower())
    a.tag = a.tag or "signoff-%s-%s" % (a.name, time.strftime("%m%d-%H%M"))
    overlay = a.ev / "build" / build_name(a.stage, a.glow_off) / "overlay"
    if a.glow_off:
        a.glow = False
    if a.cmd in ("all", "prep"):
        overlay = prep(a.stage, a.ev, glow_off=a.glow_off, s=s)
    if a.cmd in ("all", "run"):
        rc = run(a, overlay)
        if not (shots_dir(a) / "signoff_index.json").is_file():
            print("no signoff_index.json from the run (exit %d): no sheet" % rc)
            return rc or 1
    if a.cmd in ("all", "views"):
        views(a, overlay)
    return 0


if __name__ == "__main__":
    sys.exit(main())
