#!/usr/bin/env python
"""In-game check of a map's automap with test automap files (lane hdmaps2; Linux slots).

MXL_AUTOMAP_OVERLAY=DIR: a mod data folder (data/global/excel/automap.txt, data/global/ui/automap/*.dc6,
data/hd/global/ui/automap/defaultNN/*.sprite, data/global/tiles/... as tools/automap_rows.py, automap_art.py and
automap_void.py write them). Its files are laid into the slot's mods/mxl2012/mxl2012.mpq/data/ by a game_ctl.PRE_LAUNCH
hook, after the run's whole-slot snapshot, so the run's restore takes them out again (also when the run fails). Without
it the check looks at what the slot has installed (the "before").

Check `automap_fauz` (Fauztinville, level 59): god mode, travel there (`h level`), hop over the town's cells
(MXL_AUTOMAP_SPOTS, map cells; default: the r3 round's crops) so their rooms reveal, then at each of MXL_AUTOMAP_SHOTS
cells a Tab (full automap) screenshot, in HD and in legacy graphics. Judged by hand: walls, doors, no lines into the void.

  MXL_RUN=hdmaps2 MXL_SLOT=6 MXL_CHAR=<throwaway> MXL_AUTOMAP_OVERLAY=<dir> python tools/automap_gamecheck.py all automap_fauz
"""
import hashlib
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_checks as gc  # noqa: E402
import game_ctl as g  # noqa: E402

LEVEL = 59
SPOTS = [(8, 20), (40, 14), (64, 20), (92, 24), (24, 40), (80, 40), (15, 60), (62, 62), (12, 72), (20, 96), (56, 80),
         (8, 116), (100, 100), (120, 104)]
SHOTS = [(62, 62), (24, 40), (80, 40), (20, 96), (100, 100)]


def _cells(env, default):
    v = os.environ.get(env, "")
    if not v.strip():
        return default
    return [tuple(int(c) for c in p.split(",")) for p in v.split(";") if p.strip()]


def lay_overlay():
    """game_ctl.PRE_LAUNCH hook: the overlay folder's files into the slot's mod data (inside this run's game folder only).
    Writes automap_overlay.json (destination, sha256) into the run folder."""
    src = os.path.realpath(os.environ["MXL_AUTOMAP_OVERLAY"])
    game = os.path.realpath(g.GAME_DIR)
    dest_root = os.path.join(game, "mods", "mxl2012", "mxl2012.mpq", "data")
    if not os.path.isdir(dest_root):
        raise RuntimeError("no mod data folder at %s" % dest_root)
    done = []
    for base, _dirs, files in os.walk(src):
        for f in files:
            s = os.path.join(base, f)
            d = os.path.realpath(os.path.join(dest_root, os.path.relpath(s, src)))
            if not d.startswith(game + os.sep):
                raise RuntimeError("overlay destination outside the game folder: %s" % d)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(s, d)
            with open(d, "rb") as fh:
                done.append({"dest": os.path.relpath(d, game), "sha256": hashlib.sha256(fh.read()).hexdigest()})
    with open(os.path.join(g.current_run(), "automap_overlay.json"), "w", encoding="utf-8") as fh:
        json.dump(done, fh, indent=1)
    return "%d automap test files laid into the slot" % len(done)


def _origin():
    rooms = [(int(r["x"]), int(r["y"])) for r in (gc.kv(ln) for ln in gc.H("presets rooms")[1] if ln.startswith("room x="))]
    return (min(x for x, _ in rooms), min(y for _, y in rooms)) if rooms else None


def _to_cell(origin, cx, cy):
    tx, ty = origin[0] + 5 * cx + 2, origin[1] + 5 * cy + 2
    at = gc.wall_place(tx, ty)
    if abs(at[0] - tx) > 6 or abs(at[1] - ty) > 6:
        at = gc.wall_hop(tx, ty)
    time.sleep(1.5)
    return at


def visit(mode, log, shots):
    st = gc.goto(LEVEL, timeout=60)
    if st["player"].get("area") != LEVEL:
        log.append("%s: level %d not reached (area %s)" % (mode, LEVEL, st["player"].get("area")))
        return False
    time.sleep(5)
    origin = _origin()
    if not origin:
        log.append("%s: no preset rooms listed" % mode)
        return False
    log.append("%s: origin %s" % (mode, origin))
    for cx, cy in _cells("MXL_AUTOMAP_SPOTS", SPOTS):           # reveal the town's rooms
        at = _to_cell(origin, cx, cy)
        log.append("%s: cell %d,%d -> %s" % (mode, cx, cy, at))
    for cx, cy in _cells("MXL_AUTOMAP_SHOTS", SHOTS):
        _to_cell(origin, cx, cy)
        gc.wall_settle(log, "%s cell %d,%d" % (mode, cx, cy), mode)
        g.press("tab")
        time.sleep(1.5)
        shots.append(gc.sh("automap_fauz_%s_%d_%d" % (mode, cx, cy)))
        g.press("tab")
        time.sleep(0.7)
    shots.append(gc.sh("automap_fauz_%s_world" % mode))
    return True


def automap_fauz():
    mark = gc.engine_mark()
    log, shots = [], []
    gc.enable_debug()
    gc.cheat("god 1")
    gc.goto(1, timeout=60)
    ok = {}
    for mode, gfx in (("hd", "hd"), ("classic", "legacy")):
        gc.goto(1, timeout=60)
        if not gc.set_graphics(gfx):
            log.append("%s: graphics not set" % mode)
            ok[mode] = False
            continue
        ok[mode] = visit(mode, log, shots)
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.cheat("god 0")
    note = "overlay %s; HD %s, legacy %s" % (os.environ.get("MXL_AUTOMAP_OVERLAY") or "none (installed files)",
                                            "reached" if ok.get("hd") else "NOT reached",
                                            "reached" if ok.get("classic") else "NOT reached")
    gc.rc_finish("automap_fauz", all(ok.values()) and len(ok) == 2, note, mark, shots, log,
                 ["travel by `h level` / `place`", "god mode (cheat god 1)"],
                 judged_by_hand="automap_fauz_* shots: walls, doors, nothing into the void, legacy as clear as HD")


# the r3 round's crops (rounds/r3-fauztinville): name -> map cell (the crop's centre)
TOUR = [("01_north_pier", 8, 20), ("02_north_arcade", 40, 14), ("03_northeast_blocks", 64, 20), ("04_east_annex", 92, 24),
        ("05_north_street", 24, 40), ("06_east_street", 80, 40), ("07_kerbs", 15, 60), ("08_centre", 62, 62),
        ("09_hall_roof", 12, 72), ("10_west_market", 20, 96), ("11_central_roofs", 56, 80), ("12_southwest_trees", 8, 116),
        ("13_south_bridge", 100, 100), ("14_south_end", 120, 104)]


def debug_off():
    """D2RLoader's debug mode draws its menu bar and frame counters over the picture: toggled off for each shot only. Its
    cheats (god mode) end with it: a 4K run with debug off all along died to Fauztinville's turrets on arrival."""
    if gc.DEBUG_ON["v"]:
        gc.con("debug_mode")
        time.sleep(0.8)
        gc.DEBUG_ON["v"] = False


def tour(mode, log, shots):
    st = gc.goto(LEVEL, timeout=60)
    if st["player"].get("area") != LEVEL:
        log.append("%s: level %d not reached (area %s)" % (mode, LEVEL, st["player"].get("area")))
        return 0
    time.sleep(8)
    origin = _origin()
    if not origin:
        log.append("%s: no preset rooms listed" % mode)
        return 0
    n = 0
    only = {v.strip() for v in os.environ.get("MXL_TOUR_ONLY", "").split(",") if v.strip()}
    for name, cx, cy in TOUR:
        if only and name not in only:
            continue
        done = False
        for attempt in range(3):          # a death screen is never kept: revive, travel back, take the spot again
            if gc.revive_if_dead() or gc.hstate()["player"].get("area") != LEVEL:
                gc.goto(LEVEL, timeout=60)
                time.sleep(5)
            gc.enable_debug()             # god mode lives only while debug mode is on: on for travel and settling
            gc.cheat("god 1")
            at = _to_cell(origin, cx, cy)
            want = (origin[0] + 5 * cx + 2, origin[1] + 5 * cy + 2)
            gc.wall_settle(log, "%s %s" % (mode, name), mode)
            time.sleep(float(os.environ.get("MXL_TOUR_SETTLE", "4")))
            p = gc.hstate()["player"]
            if not p or gc.player_dead(p) or p.get("area") != LEVEL:
                log.append("%s %s: try %d: dead or not in the level before the shot (%s); again" % (mode, name, attempt + 1, p))
                continue
            debug_off()                   # off for the picture only (no debug bar), on again right after
            path = gc.sh("tour_%s_%s" % (name, mode))
            gc.enable_debug()
            gc.cheat("god 1")
            p = gc.hstate()["player"]
            if not p or gc.player_dead(p):
                log.append("%s %s: try %d: died around the shot; again" % (mode, name, attempt + 1))
                continue
            shots.append(path)
            log.append("%s %s: cell %d,%d wanted at %s, player at %s (try %d)" % (mode, name, cx, cy, want, at, attempt + 1))
            done = True
            break
        if done:
            n += 1
        else:
            log.append("%s %s: no clean shot in 3 tries" % (mode, name))
    return n


def fauz_tour():
    """Fauztinville in the real game at the r3 crops' spots, the player standing there in the map's own light and the
    player's light: an HD shot per spot, then the same spots in legacy graphics. For a 4K capture run it with
    MXL_PROFILE=visual4k MXL_CLIENT=3840x2160 (alone on the PC: tools/slots_reserve.py). D2RLoader's debug bar is off for
    the shots (debug_off). SHORTCUT: harness travel and god mode, as wall_maps."""
    mark = gc.engine_mark()
    log, shots = [], []
    gc.enable_debug()
    gc.cheat("god 1")
    got = {}
    for mode, gfx in (("hd", "hd"), ("classic", "legacy")):
        gc.goto(1, timeout=60)
        if not gc.set_graphics(gfx):
            log.append("%s: graphics not set" % mode)
            got[mode] = 0
            continue
        got[mode] = tour(mode, log, shots)
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.enable_debug()
    gc.cheat("god 0")
    note = "overlay %s; spots shot: HD %d, legacy %d of %d" % (os.environ.get("MXL_AUTOMAP_OVERLAY") or "none",
                                                            got.get("hd", 0), got.get("classic", 0), len(TOUR))
    gc.rc_finish("fauz_tour", got.get("hd") and got.get("classic"), note, mark, shots, log,
                 ["travel by `h level` / `place`", "god mode (cheat god 1)"],
                 judged_by_hand="tour_<spot>_hd / _classic shots against the r3 crops")


gc.CHECKS += [("automap_fauz", automap_fauz), ("fauz_tour", fauz_tour)]

if __name__ == "__main__":
    if os.environ.get("MXL_AUTOMAP_OVERLAY"):
        g.PRE_LAUNCH.append(lay_overlay)
    gc.main()
