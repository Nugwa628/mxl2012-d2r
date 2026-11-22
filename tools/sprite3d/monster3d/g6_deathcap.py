"""Stage 6: a monster's 8 facings with a burst of shots through its death (this lane's own capture step).

  run by g6_gamerun.py (runner=deathcap): python g6_deathcap.py --slot <2|5> all mon_death   (cwd: the framework checkout)

The game-check framework (tools/game_checks.py of the framework checkout: run folder, slot lock, watchdog, helpers; Windows
or Linux backend chosen at run time) is imported read only; nothing there is changed. This file adds one check, `mon_death`, and runs it with that
framework's own main().

mon_death is mon_turn's flow (spawn per facing key on the side that makes the monster face it, MXL_MONTURN_EARLY / _LIVE
shots, the same monturn_index.json labels, so g6_ownersheet.py reads it), with the death taken differently: a grabber thread
keeps client captures (PrintWindow; on Linux the window's X pixmap on the private display) IN MEMORY as fast as they come (no PNG encode between them) from just before the kill for
MXL_DEATHCAP_SECONDS (default 1.6 s), while the main thread polls the harness `facing` of the dying unit; every frame then
gets the unit mode of the nearest poll (DT = 0, DD = 12) and is saved as d00, d01, ... with its time after the kill
(`t_kill`). The corpse shot c0 follows as in mon_turn.
"""
import os
import sys
import threading
import time
from pathlib import Path

# the framework checkout (g6_gamerun.py passes MXL_M3D_FRAMEWORK; default: this checkout, which has lane hdtools-monster's checks)
FWT_TOOLS = Path(os.environ.get("MXL_M3D_FRAMEWORK") or Path(__file__).resolve().parents[3]) / "tools"
sys.path.insert(0, str(FWT_TOOLS))
sys.dont_write_bytecode = True

import game_checks as gc  # noqa: E402

g = gc.g


def check_mon_death():
    import drawcap_stats
    import json
    import re
    mark = gc.engine_mark()
    log, rows, bad, shots, index = [], [], [], [], []
    mid = os.environ.get("MXL_MONTURN_ID") or "fungus1"
    area = int(os.environ.get("MXL_MONTURN_AREA") or 2)
    modes = [m.strip().lower() for m in (os.environ.get("MXL_MONTURN_MODES") or "hd,legacy").split(",") if m.strip()]
    keys = [int(k) for k in (os.environ.get("MXL_MONTURN_KEYS") or "0,1,2,3,4,5,6,7").split(",")]
    early = int(os.environ.get("MXL_MONTURN_EARLY") or 3)
    live = int(os.environ.get("MXL_MONTURN_LIVE") or 6)
    step = int(os.environ.get("MXL_MONTURN_STEP") or 14)
    reach = int(os.environ.get("MXL_MONTURN_REACH") or 10)
    clear = int(os.environ.get("MXL_MONTURN_CLEAR") or 8)
    secs = float(os.environ.get("MXL_DEATHCAP_SECONDS") or 1.6)
    _, csv_path = gc.drawcap_files()
    index_path = os.path.join(g.current_run(), "monturn_index.json")
    row = gc.row_of("monstats", "Id", mid)
    if row is None:
        return gc.finish("mon_death", False, "%s: not in the built monstats" % mid, mark)

    def facing(uid):
        ok, ln = gc.H("facing %s" % uid)
        f = gc.kv(" ".join(ln)) if ok else {}
        return {k: int(f[k]) for k in ("mode", "dir", "key", "x", "y", "px", "py") if re.fullmatch(r"-?\d+", f.get(k, ""))}

    def tag(graphics, key, uid):
        return "monturn_%s_%s_n%02dk%d" % (mid, graphics, len({r["id"] for r in index} | {uid}), key)

    def snap(uid, graphics, key, what, t0):
        before = facing(uid)
        name = gc.sh("%s_%s" % (tag(graphics, key, uid), what))
        after = facing(uid)
        shots.append(name)
        index.append({"shot": name, "monster": mid, "id": uid, "graphics": graphics, "spawn_key": key, "what": what,
                      "t": round(time.time() - t0, 2), "before": before, "after": after})
        return bool(before and after)

    def death_burst(uid, graphics, key, t0):
        """kill the unit while a thread grabs frames into memory; label each frame with the nearest `facing` poll."""
        h = g.need_window()
        frames, polls, stop = [], [], threading.Event()

        def grab():
            while not stop.is_set():
                try:
                    frames.append((time.time(), g.grab_client(h)))
                except Exception as e:  # noqa: BLE001
                    log.append("grab: %r" % (e,))
                    time.sleep(0.02)

        pre = facing(uid)
        th = threading.Thread(target=grab, daemon=True)
        th.start()
        time.sleep(0.05)
        tk = time.time()
        gc.H("kill %s" % uid)
        tk1 = time.time()
        while time.time() - tk < secs:
            f = facing(uid)
            polls.append((time.time(), f))
        stop.set()
        th.join(5)
        n = 0
        for tf, img in frames:
            near = min(polls, key=lambda p: abs(p[0] - tf))[1] if polls else {}
            lab = dict(pre, **{k: v for k, v in near.items() if k == "mode"}) if tf >= tk else dict(pre)
            name = "%s_d%02d.png" % (tag(graphics, key, uid), n)
            img.save(os.path.join(g.current_run(), name))
            shots.append(name)
            index.append({"shot": name, "monster": mid, "id": uid, "graphics": graphics, "spawn_key": key,
                          "what": "d%02d" % n, "t": round(tf - t0, 3), "t_kill": round(tf - tk, 3),
                          "kill_ack": round(tk1 - tk, 3), "before": lab, "after": lab})
            n += 1
        modes_seen = [p[1].get("mode") for p in polls]
        dt = [p[0] - tk for p in polls if p[1].get("mode") == 0]
        log.append("key %d (%s): %d frames in %.2f s (%.1f/s), kill ack %.2f s, %d polls, DT seen %s..%s s, modes %s" % (
            key, graphics, n, secs, n / secs, tk1 - tk, len(polls), round(min(dt), 2) if dt else None,
            round(max(dt), 2) if dt else None, sorted(set(m for m in modes_seen if m is not None))))
        return n

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
            seen = 0
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
                fx, fy = gc.MON_TURN_FACE[key % 8]
                r = reach if 0 in (fx, fy) else max(2, round(reach * 0.7))
                px, py = gc.player_xy()
                _, sp = gc.Hl("spawn %s 1 %d %d" % (row["*hcIdx"], px - fx * r, py - fy * r), log)
                t0 = time.time()
                uid = gc.first(sp, r"id=(\d+)")
                if uid is None:
                    bad.append("%s (%s, key %d): not spawned" % (mid, mode, key))
                    continue
                seen += 1
                read = 0
                for i in range(early):
                    read += snap(uid, mode, key, "e%d" % i, t0)
                for i in range(live):
                    time.sleep(0.25)
                    read += snap(uid, mode, key, "l%d" % i, t0)
                if death_burst(uid, mode, key, t0) < 4:
                    bad.append("%s (%s, key %d): death burst under 4 frames" % (mid, mode, key))
                time.sleep(0.6)
                read += snap(uid, mode, key, "c0", t0)
                if read < 4:
                    bad.append("%s (%s, key %d): %d shots with a facing" % (mid, mode, key, read))
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(index, f, indent=1)
                if not gc.game_alive():
                    bad.append("the game died at key %d (%s)" % (key, mode))
                    break
            a1 = gc.pot_asserts()
            na = (a1 - a0) if a0 is not None and a1 is not None else None
            msgs = gc.pot_assert_lines(na or 0)
            fps = drawcap_stats.summary(drawcap_stats.read(csv_path)[n0:], mode).get("fps") if n0 is not None else None
            rows.append("%s (area %d, %s): %d of %d spawned, asserts %s%s, render fps %s, private MB %s" % (
                mid, area, mode, seen, len(keys), na if na is not None else "?", " %s" % msgs if msgs else "", fps,
                gc.game_private_mb()))
            if na is None or na > 0:
                bad.append("%s (%s): %s engine asserts" % (mid, mode, na))
            if bad and "game died" in bad[-1]:
                break
    if gc.game_alive():
        gc.goto(1)
        if gc.graphics_mode() != "hd":
            gc.set_graphics("hd")
        gc.cheat("god 0")
    gc.finish("mon_death", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots,
              rows + log[-300:], partial="the death frames are judged on the sheets of g6_ownersheet.py")


gc.CHECKS += [("mon_death", check_mon_death)]

if __name__ == "__main__":
    gc.main()
