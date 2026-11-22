"""Stage 6: a monster's walk, attacks and get-hit in its 8 facings, as bursts of shots (this lane's own capture step).

  run by g6_gamerun.py (check=mon_moves): python g6_movecap.py --slot <2|5> all mon_moves   (cwd: the framework checkout)

As g6_deathcap.py, the game-check framework (tools/game_checks.py of the framework checkout) is imported read only; this file
adds the check `mon_moves` and runs it with that framework's main().

Per facing key (mon_turn's spawn spots and sides, so the monster faces the key), in HD and in legacy graphics:
- bg: one shot of the empty spot before the spawn;
- burst `w` (MXL_MOVES_WALK s, default 4.0): spawned MXL_MOVES_REACH sub-tiles away (default 14), the monster walks to the
  player and starts its own attacks;
- burst `a` (MXL_MOVES_ATTACK s, default 3.4): `mcast 0 4` (A1) at once and `mcast 0 5` (A2) half-way (mcast's second
  argument is the unit mode the monster is put in: 4 A1, 5 A2, 3 GH; the first run showed 6 / 7 give BL / SC);
- burst `g` (MXL_MOVES_HIT s, default 2.6): `mcast 0 3` (GH) at 0.1 s and half-way. The player's own hits are not used:
  a monster whose life is raised so it survives them does not enter GH.
A grabber thread keeps client captures (PrintWindow / X pixmap) in memory while the main thread polls `facing` (mode, dir, x, y and the
player's x, y). After a burst each frame gets the nearest poll and is saved as a 300 x 300 cut around the unit
(g6_turnsheet.cut's place), with the unit mode, the time from the burst's start and from the start of each mode run.
monturn_index.json gets one row per saved cut (what = w00, a00, h00, ...; `mode`, `t_burst`, `t_mode`, `mode_run`).
"""
import json
import os
import re
import sys
import threading
import time

from PIL import Image
from pathlib import Path

# the framework checkout (g6_gamerun.py passes MXL_M3D_FRAMEWORK; default: this checkout, which has lane hdtools-monster's checks)
FWT_TOOLS = Path(os.environ.get("MXL_M3D_FRAMEWORK") or Path(__file__).resolve().parents[3]) / "tools"
sys.path.insert(0, str(FWT_TOOLS))
sys.dont_write_bytecode = True

import game_checks as gc  # noqa: E402

g = gc.g


def client_scale():
    """the client's size over 1600 x 900, the size the screen placement below was read at (MXL_CLIENT, e.g. 3840x2160
    for the visual4k profile: 2.4; round 18's first 4K run cut the screen's corner instead of the unit)."""
    c = os.environ.get("MXL_CLIENT", "")
    try:
        return int(c.lower().split("x")[0]) / 1600.0
    except ValueError:
        return 1.0


def screen_xy(lab):
    dx, dy = lab["x"] - lab["px"], lab["y"] - lab["py"]
    s = client_scale()
    return 800 * s + 24 * s * (dx - dy), 428 * s + 12 * s * (dx + dy)


def check_mon_moves():
    import drawcap_stats
    mark = gc.engine_mark()
    log, rows, bad, shots, index = [], [], [], [], []
    mid = os.environ.get("MXL_MONTURN_ID") or "fungus1"
    area = int(os.environ.get("MXL_MONTURN_AREA") or 2)
    modes = [m.strip().lower() for m in (os.environ.get("MXL_MONTURN_MODES") or "hd,legacy").split(",") if m.strip()]
    keys = [int(k) for k in (os.environ.get("MXL_MONTURN_KEYS") or "0,1,2,3,4,5,6,7").split(",")]
    step = int(os.environ.get("MXL_MONTURN_STEP") or 14)
    reach = int(os.environ.get("MXL_MOVES_REACH") or 14)
    clear = int(os.environ.get("MXL_MONTURN_CLEAR") or 8)
    t_walk = float(os.environ.get("MXL_MOVES_WALK") or 4.0)
    t_att = float(os.environ.get("MXL_MOVES_ATTACK") or 3.4)
    t_hit = float(os.environ.get("MXL_MOVES_HIT") or 2.6)
    index_path = os.path.join(g.current_run(), "monturn_index.json")
    _, csv_path = gc.drawcap_files()
    row = gc.row_of("monstats", "Id", mid)
    if row is None:
        return gc.finish("mon_moves", False, "%s: not in the built monstats" % mid, mark)

    def facing(uid):
        ok, ln = gc.H("facing %s" % uid)
        f = gc.kv(" ".join(ln)) if ok else {}
        return {k: int(f[k]) for k in ("mode", "dir", "key", "x", "y", "px", "py") if re.fullmatch(r"-?\d+", f.get(k, ""))}

    def tag(graphics, key, uid):
        return "monturn_%s_%s_n%02dk%d" % (mid, graphics, len({r["id"] for r in index} | {uid}), key)

    def burst(uid, graphics, key, what, secs, actions):
        """grab frames for `secs` while polling the unit; `actions` = [(seconds after start, harness command)]."""
        h = g.need_window()
        frames, polls, stop = [], [], threading.Event()

        def grab():
            while not stop.is_set():
                try:
                    frames.append((time.time(), g.grab_client(h)))
                except Exception as e:  # noqa: BLE001
                    log.append("grab: %r" % (e,))
                    time.sleep(0.02)

        th = threading.Thread(target=grab, daemon=True)
        th.start()
        t0 = time.time()
        todo = sorted(actions)
        acts = []
        while time.time() - t0 < secs:
            while todo and time.time() - t0 >= todo[0][0]:
                _t, cmd = todo.pop(0)
                ok, ln = gc.H(cmd)
                acts.append({"t": round(time.time() - t0, 3), "cmd": cmd, "ok": bool(ok), "out": " ".join(ln)[:200]})
            f = facing(uid)
            if f:
                polls.append((time.time(), f))
        stop.set()
        th.join(5)
        # mode runs from the polls: the start time of each run of the same mode
        runs, last = [], None
        for tp, f in polls:
            if f.get("mode") != last:
                runs.append((tp, f.get("mode")))
                last = f.get("mode")
        n = 0
        for tf, img in frames:
            if not polls:
                break
            near = min(polls, key=lambda p: abs(p[0] - tf))[1]
            if not all(k in near for k in ("x", "y", "px", "py")):
                continue
            run = max((r for r in runs if r[0] <= tf + 0.02), key=lambda r: r[0], default=runs[0])
            sx, sy = screen_xy(near)
            name = "%s_%s%02d.png" % (tag(graphics, key, uid), what, n)
            cs = client_scale()       # the same 300 x 300 cut at any client size (a larger client's cut scaled down)
            img.crop((int(sx - 150 * cs), int(sy - 225 * cs), int(sx + 150 * cs), int(sy + 75 * cs))).resize(
                (300, 300), Image.LANCZOS).save(os.path.join(g.current_run(), name))
            shots.append(name)
            index.append({"shot": name, "cut": True, "monster": mid, "id": uid, "graphics": graphics, "spawn_key": key,
                          "what": "%s%02d" % (what, n), "mode": near.get("mode"), "t_burst": round(tf - t0, 3),
                          "t_mode": round(tf - run[0], 3), "mode_run": runs.index(run), "before": near, "after": near})
            n += 1
        seen = [f.get("mode") for _t, f in polls]
        log.append("key %d (%s) %s: %d frames in %.1f s, %d polls, modes %s, runs %s, actions %s" % (
            key, graphics, what, n, secs, len(polls), sorted(set(m for m in seen if m is not None)),
            [(round(t - t0, 2), m) for t, m in runs], acts))
        return set(seen)

    gc.enable_debug()
    gc.cheat("god 1")
    gc.goto(1)
    gc.Hl("asserttrace on", log)
    with gc.Tank():
        for mode in modes:
            gc.goto(1)
            if gc.graphics_mode() != mode and not gc.set_graphics(mode):
                bad.append("graphics mode %s not reached" % mode)
                continue
            gc.goto(area)
            time.sleep(2.0)
            base = gc.player_xy()
            a0 = gc.pot_asserts()
            n0 = len(drawcap_stats.read(csv_path)) if os.path.isfile(csv_path) else None
            seen_units, modes_seen = 0, set()
            for n, key in enumerate(keys):
                sx, sy = gc.MON_TURN_SPOTS[n % len(gc.MON_TURN_SPOTS)]
                if n:
                    gc.H("move %d %d" % (base[0] + sx * step, base[1] + sy * step))
                    last = None
                    for _ in range(16):
                        time.sleep(0.3)
                        now = gc.player_xy()
                        if now == last:
                            break
                        last = now
                for _ in range(clear):
                    if not gc.H("kill nearest")[0]:
                        break
                bgname = gc.sh("monturn_%s_%s_k%d_bg" % (mid, mode, key))
                shots.append(bgname)
                index.append({"shot": bgname, "monster": mid, "id": None, "graphics": mode, "spawn_key": key, "what": "bg",
                              "before": {}, "after": {}, "player": list(gc.player_xy())})
                fx, fy = gc.MON_TURN_FACE[key % 8]
                r = reach if 0 in (fx, fy) else max(2, round(reach * 0.7))
                px, py = gc.player_xy()
                _, sp = gc.Hl("spawn %s 1 %d %d" % (row["*hcIdx"], px - fx * r, py - fy * r), log)
                uid = gc.first(sp, r"id=(\d+)")
                if uid is None:
                    bad.append("%s (%s, key %d): not spawned" % (mid, mode, key))
                    continue
                seen_units += 1
                modes_seen |= burst(uid, mode, key, "w", t_walk, [])
                modes_seen |= burst(uid, mode, key, "a", t_att, [(0.0, "mcast 0 4 unit %s" % uid),
                                                                 (t_att / 2, "mcast 0 5 unit %s" % uid)])
                modes_seen |= burst(uid, mode, key, "g", t_hit, [(0.1, "mcast 0 3 unit %s" % uid),
                                                                 (t_hit / 2, "mcast 0 3 unit %s" % uid)])
                gc.H("kill %s" % uid)
                time.sleep(0.4)
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(index, f, indent=1)
                if not gc.game_alive():
                    bad.append("the game died at key %d (%s)" % (key, mode))
                    break
            a1 = gc.pot_asserts()
            na = (a1 - a0) if a0 is not None and a1 is not None else None
            msgs = gc.pot_assert_lines(na or 0)
            fps = drawcap_stats.summary(drawcap_stats.read(csv_path)[n0:], mode).get("fps") if n0 is not None else None
            rows.append("%s (area %d, %s): %d of %d spawned, modes seen %s, asserts %s%s, render fps %s, private MB %s" % (
                mid, area, mode, seen_units, len(keys), sorted(m for m in modes_seen if m is not None),
                na if na is not None else "?", " %s" % msgs if msgs else "", fps, gc.game_private_mb()))
            if na is None or na > 0:
                bad.append("%s (%s): %s engine asserts" % (mid, mode, na))
            if bad and "game died" in bad[-1]:
                break
    if gc.game_alive():
        gc.goto(1)
        if gc.graphics_mode() != "hd":
            gc.set_graphics("hd")
        gc.cheat("god 0")
    gc.finish("mon_moves", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots,
              rows + log[-400:], partial="walk, attack and get-hit are judged on the sheets of this lane")


gc.CHECKS += [("mon_moves", check_mon_moves)]

if __name__ == "__main__":
    gc.main()
