"""In-game part of the sign-off: the game check `signoff`, run inside the project's game-check framework.

  python gamecheck.py --slot <N> all signoff          (cwd: the framework's tools folder, read only; started by run.py:
                                                      on Linux by run_linux, on Windows through monster3d's g6_gamerun.py
                                                      with check name mon_moves, which owns lock, overlay and restore)

The framework (HDKIT_SIGNOFF_FWT: a tools folder with game_checks.py: harness commands, window captures, background input;
on Linux the game runs on a private X display and is captured from it) is imported read only. This file only adds the
check, maps g6_gamerun's check name onto it, and on Linux lays the run's plan into the slot before the launch.

Environment (all optional unless named):
  HDKIT_SIGNOFF_ID      monstats Id of the unit (required)
  HDKIT_SIGNOFF_MODES   unit modes to capture, codes (default nu,a1,gh,dt,dd)
  HDKIT_SIGNOFF_KEYS    facing keys 0..7 (0 = screen bottom, clockwise; default 0,2,4,6)
  HDKIT_SIGNOFF_AREA    area (level id) of the spot (default 1)
  HDKIT_SIGNOFF_SPOT    x,y sub-tiles to walk to after arriving (default: where goto lands)
  HDKIT_SIGNOFF_REACH   spawn distance in sub-tiles from the character (default 3, diagonal steps 0.7 of it: inside
                        the unit's attack reach, so it casts where it stands and faces the character, i.e. the key)
  HDKIT_SIGNOFF_HOLD    seconds per cast mode (default 1.6)
  HDKIT_SIGNOFF_TRIES   attempts per facing key (default 3): an attempt captures the modes still missing
  HDKIT_SIGNOFF_SIDE    x,y sub-tiles from the character to spawn the unit at (default: the key's side at REACH; a unit
                        spawned further out wanders before it casts, run s8e)
  HDKIT_SIGNOFF_TODWAIT seconds to wait in the area before the first shot (time of day; default 0)
  HDKIT_SIGNOFF_STEP    sub-tiles between the fresh spots of the attempts (default 14)
  HDKIT_SIGNOFF_CAPTURE JSON of the capture constants (settings `capture`: client, feet_px, player_box)
  HDKIT_SIGNOFF_TABLES  folder of the built tables (global/excel) used when the framework's own (gc.EXCEL) is missing
  HDKIT_SIGNOFF_PLAN    Linux: JSON {"game": slot folder, "files": [[destination, source], ...]} laid into the slot by
                        game_ctl.PRE_LAUNCH after the whole-slot snapshot (the restore takes it out again)

Exact facings: a unit casting at the character faces it, and its dir64 is the angle of the sub-tile vector to the
character (capture.py). The game moves the spawn spot, so the unit is spawned beside the character (SIDE) and its real
spot is polled; the character is then put (`place`) on a spot round the unit that makes it face the key
(capture.spots_for), checked again after each move, and the burst starts when the unit stands still. The twin shot was taken before that move: its cut is then taken round the unit's ground in the twin's own
camera (capture.twin_cut) and the twin's character box is left out too (`exclude`). Only frames whose polled key is the
asked key are kept; modes with none (wrong key, no steady frame) are tried again at a fresh spot, up to TRIES attempts,
and each miss is named per attempt (signoff_attempts.json, the check's problems).

Per facing key: the character walks to a fresh spot (monster rows of mon_turn), the area's monsters near it are killed, a
full-frame twin shot of the empty spot is taken, the unit is spawned on the side that makes it face that key, and one
burst of PrintWindow frames runs while the main thread polls `facing` (mode, dir64, x, y, the character's x, y):
`mcast 0 <mode>` for each cast mode (NU, A1, A2, GH, SC, S1-S4; one every HOLD s, so the unit stays at its spot), a short
walk if WL is asked, then `kill` and the death (DT) and the corpse (DD). Each frame is kept as a 400 x 400 cut around the
unit's feet (feet at 200, 300 of the cut). Per asked mode the frame in the middle of that mode's first steady run is saved
with its twin cut: signoff_<id>_k<key>_<mode>.png / _twin.png; signoff_index.json lists them with the poll (dir64,
positions), the time since the mode started, and the feet pixel in the cut.
"""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

FWT_TOOLS = Path(os.environ.get("HDKIT_SIGNOFF_FWT") or Path(__file__).resolve().parents[2])
sys.path.insert(0, str(FWT_TOOLS))
sys.dont_write_bytecode = True

import game_checks as gc  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import capture  # noqa: E402
from capture import (CAST, MODE_INDEX, box_of, covers, feet_px, key_toward, label, pick, spots_for,  # noqa: E402
                     twin_cut)

# the built tables (monstats) the check reads: the framework's own place, else the installed mod's (the slot's copy of
# the same build; a fresh checkout has no built mod of its own)
if os.environ.get("HDKIT_SIGNOFF_TABLES") and not os.path.isdir(gc.EXCEL):
    gc.EXCEL = os.environ["HDKIT_SIGNOFF_TABLES"]
if os.environ.get("HDKIT_SIGNOFF_CAPTURE"):
    capture.configure(**json.loads(os.environ["HDKIT_SIGNOFF_CAPTURE"]))

g = gc.g


def env(name, default=None):
    return os.environ.get("HDKIT_SIGNOFF_" + name) or default


def lay_plan(path=None):
    """game_ctl.PRE_LAUNCH hook (Linux): copies the plan's files into the slot (the whole-slot snapshot is already taken,
    so the restore takes them out). Every destination must lie inside this run's game folder. Writes signoff_plan.json
    (destination, source, sha256) into the run folder."""
    import hashlib
    import shutil
    try:
        plan = json.loads(Path(path or env("PLAN")).read_text(encoding="utf-8"))
        game = os.path.realpath(g.GAME_DIR)
        if os.path.realpath(plan["game"]) != game:
            raise RuntimeError("the plan is for %s, this run's game folder is %s" % (plan["game"], game))
        done = []
        for dest, src in plan["files"]:
            d = os.path.realpath(dest)
            if not d.startswith(game + os.sep):
                raise RuntimeError("plan destination outside the game folder: %s" % dest)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(src, d)
            with open(d, "rb") as f:
                done.append({"dest": os.path.relpath(d, game), "source": src, "sha256": hashlib.sha256(f.read()).hexdigest()})
        with open(os.path.join(g.current_run(), "signoff_plan.json"), "w", encoding="utf-8") as fh:
            json.dump(done, fh, indent=1)
        return "%d files laid into the slot" % len(done)
    except (OSError, ValueError, KeyError) as e:
        raise RuntimeError("signoff plan not laid: %r" % (e,))

def check_signoff():
    mark = gc.engine_mark()
    log, bad, shots, index = [], [], [], []
    mid = env("ID")
    if not mid:
        return gc.finish("signoff", False, "HDKIT_SIGNOFF_ID (the unit's monstats Id) is not set", mark)
    modes = [m.strip().lower() for m in env("MODES", "nu,a1,gh,dt,dd").split(",") if m.strip()]
    keys = [int(k) for k in env("KEYS", "0,2,4,6").split(",") if k.strip()]
    area = int(env("AREA", 1))
    spot = env("SPOT")
    reach = int(env("REACH", 3))
    hold = float(env("HOLD", 1.6))
    tod = float(env("TODWAIT", 0))
    step = int(env("STEP", 14))
    tries = max(1, int(env("TRIES", 3)))
    side = [int(v) for v in env("SIDE").split(",")] if env("SIDE") else None
    attempts = []
    unknown = [m for m in modes if m not in MODE_INDEX]
    if unknown:
        return gc.finish("signoff", False, "unknown mode codes %s" % unknown, mark)
    run_dir = g.current_run()
    index_path = os.path.join(run_dir, "signoff_index.json")
    row = gc.row_of("monstats", "Id", mid)
    if row is None:
        return gc.finish("signoff", False, "%s: not in the built monstats" % mid, mark)

    def facing(uid):
        ok, ln = gc.H("facing %s" % uid)
        f = gc.kv(" ".join(ln)) if ok else {}
        return {k: int(f[k]) for k in ("mode", "dir", "key", "x", "y", "px", "py") if re.fullmatch(r"-?\d+", f.get(k, ""))}

    def settle(limit=20):
        last = None
        for _ in range(limit):
            time.sleep(0.3)
            now = gc.player_xy()
            if now == last:
                break
            last = now
        time.sleep(1.5)        # the HD camera eases after the character stops
        return gc.player_xy()

    def still(uid, most=4.0):
        """Polls `facing` until the unit's spot stays the same for 1 s (at most `most` s); the last poll."""
        last, same, t_end, f = None, 0, time.time() + most, {}
        while time.time() < t_end:
            f = facing(uid)
            now = (f.get("x"), f.get("y"))
            same = same + 1 if now == last else 0
            if same >= 5:
                break
            last = now
            time.sleep(0.2)
        return f

    def burst(uid, actions, secs):
        h = g.need_window()
        frames, polls, stop = [], [], threading.Event()
        state = {"box": None}

        def grab():
            while not stop.is_set():
                try:
                    img = g.grab_client(h)
                    b = state["box"]
                    if b is not None:
                        frames.append((time.time(), b, img.crop(b)))
                except Exception as e:  # noqa: BLE001
                    log.append("grab: %r" % (e,))
                    time.sleep(0.02)

        th = threading.Thread(target=grab, daemon=True)
        f0 = facing(uid)
        if all(k in f0 for k in ("x", "y", "px", "py")):
            state["box"] = box_of(feet_px(f0))
        th.start()
        t0 = time.time()
        todo = sorted(actions)
        acts = []
        while time.time() - t0 < secs:
            while todo and time.time() - t0 >= todo[0][0]:
                _t, cmd = todo.pop(0)
                ok, ln = gc.H(cmd)
                acts.append({"t": round(time.time() - t0, 3), "cmd": cmd, "ok": bool(ok), "out": " ".join(ln)[:160]})
            f = facing(uid)
            if all(k in f for k in ("x", "y", "px", "py")):
                polls.append((time.time(), f))
                state["box"] = box_of(feet_px(f))
        stop.set()
        th.join(5)
        return t0, frames, polls, acts

    gc.enable_debug()
    gc.cheat("god 1")
    gc.goto(1)
    gc.Hl("asserttrace on", log)
    with gc.Tank():
        if gc.graphics_mode() != "hd" and not gc.set_graphics("hd"):
            return gc.finish("signoff", False, "graphics mode hd not reached", mark)
        gc.goto(area)
        time.sleep(2.0)
        if spot:
            sx, sy = (int(v) for v in spot.split(","))
            gc.H("move %d %d" % (sx, sy))
            settle()
        if tod > 0:
            log.append("waiting %.0f s in the area (time of day)" % tod)
            time.sleep(tod)
        base = gc.player_xy()
        a0 = gc.pot_asserts()
        spot_n = 0
        for key in keys:
            todo, tried = list(modes), []
            for attempt in range(1, tries + 1):
                if not todo:
                    break
                ox, oy = capture.SPOTS[spot_n % len(capture.SPOTS)]
                if spot_n:
                    gc.H("move %d %d" % (base[0] + ox * step, base[1] + oy * step))
                spot_n += 1
                for _ in range(10):
                    if not gc.H("kill nearest")[0]:
                        break
                px, py = settle()
                twin_full, twin_at = g.grab_client(g.need_window()), (px, py)
                fx, fy = capture.FACE[key % 8]
                # on the side that faces the key (within reach, so the unit casts where it stands); the game may move it,
                # and the character then steps to the spot the unit's real place asks for (below). SIDE overrides.
                r = reach if 0 in (fx, fy) else max(2, round(reach * 0.7))
                qx, qy = (px + side[0], py + side[1]) if side else (px - fx * r, py - fy * r)
                _, sp = gc.Hl("spawn %s 1 %d %d" % (row["*hcIdx"], qx, qy), log)
                uid = gc.first(sp, r"id=(\d+)")
                tr = {"attempt": attempt, "modes": list(todo), "spawn_ask": [qx, qy], "placed": []}
                tried.append(tr)
                if uid is None:
                    tr["why"] = "not spawned"
                    continue
                # where the unit really stands (the game moves the spawn spot), and the character's spot that makes it
                # face the key: derived from the facing geometry (capture.spots_for), checked again after each `place`
                time.sleep(0.3)
                f = facing(uid)
                if all(k in f for k in ("x", "y")):
                    tr["unit"] = [f["x"], f["y"]]
                    far = max(abs(f["x"] - px), abs(f["y"] - py)) > reach + 1
                    if far or key_toward((f["x"], f["y"]), (px, py)) != key:
                        for sx, sy in spots_for((f["x"], f["y"]), key, reach):
                            ok, ln = gc.H("place %d %d" % (sx, sy))
                            settle()
                            f = facing(uid)
                            if not all(k in f for k in ("x", "y", "px", "py")):
                                break
                            px, py = f["px"], f["py"]
                            tr["placed"].append({"ask": [sx, sy], "ok": bool(ok), "player": [px, py],
                                                 "unit": [f["x"], f["y"]],
                                                 "key": key_toward((f["x"], f["y"]), (px, py))})
                            if tr["placed"][-1]["key"] == key:
                                break
                    tr["geom_key"] = key_toward((f.get("x", 0), f.get("y", 0)), (f.get("px", px), f.get("py", py)))
                    if tr["geom_key"] != key:
                        log.append("key %d attempt %d: no character spot round the unit at %s gives key %d (%d tried)" % (
                            key, attempt, tr["unit"], key, len(tr["placed"])))
                moved = bool(tr["placed"])
                f = still(uid)              # the unit may have walked on: start the burst when it stands
                if all(k in f for k in ("x", "y", "px", "py")):
                    tr["start"] = {"unit": [f["x"], f["y"]], "player": [f["px"], f["py"]], "dir": f.get("dir"),
                                   "key": key_toward((f["x"], f["y"]), (f["px"], f["py"]))}
                if moved and all(k in f for k in ("x", "y")):
                    # the twin's character (shot before the move) must not stand on the unit: its box is left out
                    # (a retry does not clear it: the spawn lands near that spot again, run s8e), so it is recorded per cell
                    tr["twin_cover"] = round(covers(twin_cut((f["x"], f["y"]), twin_at)[1]), 3)
                cast = [m for m in todo if m in CAST]
                acts, t = [], 0.0
                for m in cast:
                    acts.append((t, "mcast 0 %d unit %s" % (MODE_INDEX[m], uid)))
                    t += hold
                if "wl" in todo:
                    t += 1.0
                die = "dt" in todo or "dd" in todo
                if die:
                    acts.append((t, "kill %s" % uid))
                    t += 3.0
                t0, frames, polls, done = burst(uid, acts, t + 0.2)
                lab = label(t0, frames, polls)
                seen = sorted({(fr["poll"].get("mode"), fr["poll"].get("key")) for fr in lab})
                log.append("key %d attempt %d: %d frames, %d polls, (mode, key) seen %s, character moved %s, actions %s" % (
                    key, attempt, len(lab), len(polls), seen, moved,
                    [(x["t"], x["cmd"].split(" unit")[0], x["ok"]) for x in done]))
                tr["missed"] = {}
                for m in list(todo):
                    fr = pick(lab, m, key)
                    if fr is None:
                        anyk = pick(lab, m)
                        tr["missed"][m] = ("steady only at key %s" % anyk["poll"].get("key")) if anyk else "no steady frame"
                        continue
                    todo.remove(m)
                    name = "signoff_%s_k%d_%s" % (mid, key, m)
                    fr["img"].save(os.path.join(run_dir, name + ".png"))
                    pb = capture.PLAYER_BOX
                    excl = [[pb[0] - fr["box"][0], pb[1] - fr["box"][1], pb[2] - fr["box"][0], pb[3] - fr["box"][1]]]
                    tb, cover = fr["box"], 0.0
                    if moved:      # the twin was shot before the character moved: its cut follows the unit's ground
                        tb, tpb = twin_cut((fr["poll"]["x"], fr["poll"]["y"]), twin_at)
                        excl.append(tpb)
                        cover = round(covers(tpb), 3)
                    twin_full.crop(tb).save(os.path.join(run_dir, name + "_twin.png"))
                    fp = feet_px(fr["poll"])
                    shots += [name + ".png", name + "_twin.png"]
                    index.append({"shot": name + ".png", "twin": name + "_twin.png", "monster": mid, "id": uid,
                                  "spawn_key": key, "mode": m, "poll": fr["poll"], "dir64": fr["poll"].get("dir"),
                                  "key": fr["poll"].get("key"), "t_mode": fr["t_mode"], "t_burst": fr["t_burst"],
                                  "box": list(fr["box"]), "feet": [fp[0] - fr["box"][0], fp[1] - fr["box"][1]],
                                  "player_box": excl[0], "exclude": excl, "twin_box": list(tb),
                                  "attempt": attempt, "retries": attempt - 1, "character_moved": moved, "twin_cover": cover,
                                  "area": area, "player": [px, py]})
                if not die:
                    gc.H("kill %s" % uid)
                with open(index_path, "w", encoding="utf-8") as fh:
                    json.dump(index, fh, indent=1)
                if not gc.game_alive():
                    bad.append("the game died at key %d" % key)
                    break
            attempts.append({"key": key, "attempts": tried})
            with open(os.path.join(run_dir, "signoff_attempts.json"), "w", encoding="utf-8") as fh:
                json.dump(attempts, fh, indent=1)
            for m in todo:
                why = "; ".join("attempt %d: %s" % (x["attempt"], x.get("why") or (x.get("missed") or {}).get(m, "?"))
                                for x in tried)
                bad.append("key %d mode %s: not captured at key %d in %d attempts (%s)" % (key, m.upper(), key, len(tried), why))
            if not gc.game_alive():
                break
        a1 = gc.pot_asserts()
        na = (a1 - a0) if a0 is not None and a1 is not None else None
        if na is None or na > 0:
            bad.append("%s engine asserts" % na)
    if gc.game_alive():
        gc.goto(1)
        gc.cheat("god 0")
    note = "%s: %d of %d (key, mode) frames, area %d, asserts %s" % (mid, len(index), len(keys) * len(modes), area, na)
    gc.finish("signoff", not bad, note + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log[-300:],
              partial="game | viewer judged on the sign-off sheet (hdkit.signoff)")


gc.CHECKS += [("signoff", check_signoff)]

if __name__ == "__main__":
    if env("PLAN"):
        g.PRE_LAUNCH.append(lay_plan)
    # g6_gamerun names its own check (settings windows.check, HDKIT_SIGNOFF_ALIAS); this runner answers it with `signoff`
    alias = env("ALIAS")
    if alias:
        sys.argv = [("signoff" if a == alias else a) for a in sys.argv]
    gc.main()
