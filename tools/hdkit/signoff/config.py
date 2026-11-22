"""Settings of the in-game sign-off: what a project and a machine add to the general tool (no mod names in signoff/).

  settings(path=None) -> dict    DEFAULTS, then the site adapter's `signoff_settings()` (module `hdkit_site` beside the
                                 hdkit package, optional), then a JSON file (`path`, else env HDKIT_SIGNOFF_CONFIG); each
                                 layer is merged into the one before (dicts key by key, everything else replaced)

Keys (paths are strings; None = not set):
  runs_root        the project's runs folder (evidence defaults live under it)
  ev               default evidence folder of the sign-off (default <runs_root>/hdkit/signoff)
  m3d_ev           where the monster stages live (<m3d_ev>/<stage>/overlay, build.json) with their ART-MANIFEST.json
  base_root        the base game data root hdkit.view reads besides the build (default <m3d_ev>/d2r/data)
  art_store        the content-addressed store large stage files come from (default hdkit.store.root())
  units            {token: {"id": monstats Id, "name": short name, "stage": stage under m3d_ev}}: units known by token
  area, slot, slots, tries, reach, modes, facings      run defaults; `slots` = the test slots a run may use
  lock_holder      the name the slot lock and the run carry
  capture          {"client": [w, h], "feet_px": [x, y], "player_box": [x0, y0, x1, y1]} of the game captures
                   (defaults: D2R's HD camera at 1600x900, hdkit.view.camera)
  backend          "auto" (by platform), "linux" or "windows": how a game run is made (run.py)
  windows          {"heavy_lock": script, "heavy_token": token, "worktree_root": dir, "gamerun": monster3d g6_gamerun.py,
                    "framework_tools": tools dir with game_checks.py, "m3d_env": env name g6_gamerun reads its folder from,
                    "framework_env": env name g6_gamerun reads its framework checkout from, "check": the check name
                    g6_gamerun is given (this runner answers it with `signoff`), "runner": the capture script of
                    that check g6_gamerun would start (replaced by gamecheck.py)}
  linux            {"framework_tools": tools dir with game_checks.py / game_ctl.py / game_slots.py, "dev_plugin": plugin
                    DLL laid over the slot for the run (harness verbs facing/spawn/place/mcast/kill), "plugin_dest": its
                    path relative to the slot's mod folder, "mod_data": the mod's data folder relative to the mod folder,
                    "cpu_max": load limit in %, "env": extra environment of the check (e.g. the test character)}
  framework_env    names of the framework's environment: {"run": lock holder, "slot": slot, "runs": run folder root}
"""
import copy
import importlib
import json
import os
from pathlib import Path

DEFAULTS = {
    "runs_root": None, "ev": None, "m3d_ev": None, "base_root": None, "art_store": None,
    "units": {},
    "area": 1, "slot": None, "slots": [], "tries": 3, "reach": 3, "modes": "nu,a1,gh,dt,dd", "facings": "0,2,4,6",
    "lock_holder": "hdkit-signoff",
    "capture": {"client": [1600, 900], "feet_px": [800.0, 437.5], "player_box": [752, 278, 848, 450]},
    "backend": "auto",
    "windows": {"heavy_lock": None, "heavy_token": "game", "worktree_root": None, "gamerun": None, "framework_tools": None,
                "m3d_env": None, "framework_env": None, "check": None, "runner": None},
    "linux": {"framework_tools": None, "dev_plugin": None, "plugin_dest": None, "mod_data": None, "cpu_max": 60,
              "env": {}},
    "framework_env": {"run": None, "slot": None, "runs": None},
}


def merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def site_settings() -> dict:
    try:
        site = importlib.import_module("hdkit_site")
    except ImportError:
        return {}
    fn = getattr(site, "signoff_settings", None)
    return fn() if fn else {}


def settings(path=None) -> dict:
    s = merge(DEFAULTS, site_settings())
    path = path or os.environ.get("HDKIT_SIGNOFF_CONFIG")
    if path:
        s = merge(s, json.loads(Path(path).read_text(encoding="utf-8")))
    if s["runs_root"] and not s["ev"]:
        s["ev"] = str(Path(s["runs_root"]) / "hdkit" / "signoff")
    if s["m3d_ev"] and not s["base_root"]:
        s["base_root"] = str(Path(s["m3d_ev"]) / "d2r" / "data")
    if not s["art_store"]:
        from .. import store
        r = store.root()
        s["art_store"] = str(r) if r else None
    return s


def backend(s: dict, platform: str | None = None) -> str:
    """'linux' or 'windows': the setting, or by platform when it is 'auto'."""
    import sys
    b = s.get("backend") or "auto"
    if b != "auto":
        return b
    return "windows" if (platform or sys.platform) == "win32" else "linux"


def need(s: dict, *keys) -> object:
    """s[k1][k2]...; exits with a clear message when it is not set."""
    v = s
    for k in keys:
        v = v.get(k) if isinstance(v, dict) else None
    if v in (None, "", [], {}):
        raise SystemExit("hdkit.signoff: setting %s is not set (site adapter hdkit_site.signoff_settings, HDKIT_SIGNOFF_CONFIG"
                         " or the command line)" % ".".join(keys))
    return v
