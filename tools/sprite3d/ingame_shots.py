#!/usr/bin/env python
"""Spawn Median monsters in the Blood Moor and screenshot their animation modes, in game_ctl's background input mode.

  py -3 tools/sprite3d/ingame_shots.py [--slot N] [--area 2] [--secs 25] [--no-start] [--keep] [--difficulty N] id [id ...]

The slot's lock must be held by the caller (game_slots.py lock N <owner>, then MXL_RUN=<owner>); this script never takes
or removes a lock. For each id: `cheat mspawn <id>`, then a burst of screenshots with the monster's mode read from
`h state` (neutral / walk / attack / cast come by themselves when the AI meets the player), then a forced hit (get hit),
then `h kill` (death). --no-start uses a game that is already running in a game; --keep leaves it running. Frames are written as <id>_<mode name>_<n>.png into the run folder, and `modes.md` lists them.
The first frame of every mode is also copied to <id>_<mode name>.png.
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import game_checks as gc  # noqa: E402
import game_ctl as g  # noqa: E402

# The caller holds the slot's lock for the whole lane: game_ctl.stop must not give it back.
g.game_slots.release = lambda *a, **k: None

MODE = {0: "death", 1: "neutral", 2: "walk", 3: "gethit", 4: "attack1", 5: "attack2", 6: "block", 7: "cast", 8: "skill1",
        9: "skill2", 10: "skill3", 11: "skill4", 12: "dead", 13: "knockback", 15: "run"}


def mons_of(st, mid=None):
    out = [m for m in st["mons"] if m.get("npc", 0) == 0]
    return [m for m in out if mid is None or m.get("id") == mid]


def find_new(st, known):
    """The unit `mspawn` made: the lowest new id (minions of a boss come after it)."""
    new = [m for m in mons_of(st) if m.get("id") not in known]
    return min(new, key=lambda m: m["id"]) if new else None


def shoot(mid, tag, log, firsts):
    st = gc.hstate()
    m = mons_of(st, mid)
    mode = m[0].get("mode") if m else None
    name = MODE.get(mode, "mode%s" % mode) if m else "gone"
    n = log.setdefault(name, 0)
    log[name] = n + 1
    p = os.path.join(g.current_run(), gc.sh("%s_%s_%d" % (tag, name, n)))
    firsts.setdefault(name, p)
    return name


def run(ids, area, secs, diff=0, clean=True, god=True):
    rows = []
    gc.enable_debug()
    if diff:
        gc.H("difficulty %d" % diff)  # Hell rules give bosses their life (Normal rows have none): a hit does not kill
    st = gc.goto(area)
    g.log("area %s" % st["player"].get("area"))
    for uid in ids:
        gc.revive_if_dead()
        if gc.hstate()["player"].get("area") != area:
            gc.goto(area)
        if god:
            gc.H("stat player 7 set 25600000")
            gc.H("stat player 6 set 25600000")
        known = {m.get("id") for m in mons_of(gc.hstate())}
        gc.cheat("mspawn %s" % uid)
        time.sleep(2.5)
        st = gc.hstate()
        m = find_new(st, known)
        if not m:
            rows.append((uid, "no monster appeared", {}))
            continue
        mid = m["id"]
        if clean:  # minions of a boss are in the way of the picture
            for o in mons_of(st):
                if o["id"] not in known and o["id"] != mid:
                    gc.H("kill %d" % o["id"])
        g.log("%s spawned: unit %s class %s" % (uid, mid, m.get("class")))
        if diff:  # the life was rolled with Hell rules at the spawn; back to Normal rules so that its hits do not kill the player
            gc.H("difficulty 0")
        log, firsts = {}, {}
        for j in range(16):  # the first seconds: a monster that comes for the player walks / runs, no `h state` in between
            p = os.path.join(g.current_run(), gc.sh("%s_approach_%d" % (uid, j)))
            firsts.setdefault("approach", p)
            log["approach"] = log.get("approach", 0) + 1
            time.sleep(0.2)
        t0 = time.time()
        while time.time() - t0 < secs:
            gc.guard()
            shoot(mid, uid, log, firsts)
            if gc.revive_if_dead():
                gc.goto(area)
                if god:
                    gc.H("stat player 7 set 25600000")
                    gc.H("stat player 6 set 25600000")
        # get hit: a stagger hit through the game's own damage path; the GH animation is short, so no `h state` between shots
        for k in range(3):
            gc.H("hit mon:%d phys 256 stagger" % mid)
            for j in range(4):
                p = os.path.join(g.current_run(), gc.sh("%s_gethit_%d" % (uid, k * 4 + j)))
                firsts.setdefault("gethit", p)
                log["gethit"] = log.get("gethit", 0) + 1
            time.sleep(0.6)
        ok, _l = gc.H("kill %d" % mid)
        for j in range(14):
            p = os.path.join(g.current_run(), gc.sh("%s_death_%d" % (uid, j)))
            firsts.setdefault("death", p)
            log["death"] = log.get("death", 0) + 1
            time.sleep(0.12 if j < 10 else 1.0)
        for name, p in firsts.items():
            dst = os.path.join(os.path.dirname(p), "%s_%s.png" % (uid, name))
            shutil.copyfile(p, dst)
        rows.append((uid, "class %s, killed %s" % (m.get("class"), ok), log))
    return rows


def main():
    a = [x for x in sys.argv[1:]]
    area, secs, start, keep, diff = 2, 25, True, False, 0
    ids = []
    i = 0
    while i < len(a):
        if a[i] == "--area":
            area = int(a[i + 1]); i += 2
        elif a[i] == "--secs":
            secs = int(a[i + 1]); i += 2
        elif a[i] == "--no-start":
            start = False; i += 1
        elif a[i] == "--difficulty":
            diff = int(a[i + 1]); i += 2
        elif a[i] == "--keep":
            keep = True; i += 1
        else:
            ids.append(a[i]); i += 1
    gc.new_run()
    gc.WD = gc.Watchdog()
    gc.WD.start()
    rows = []
    try:
        if start:
            if not gc.to_menu():
                print("game did not reach the main menu")
                return 2
            if not gc.enter_game():
                print("the character did not enter the game")
                return 2
        else:
            gc.STATE["in_game"] = True
        rows = run(ids, area, secs, diff)
    finally:
        gc.WD.stop_flag = True
        run_dir = g.current_run()
        with open(os.path.join(run_dir, "modes.md"), "w", encoding="utf-8") as f:
            f.write("| Id | Result | Frames per mode |\n|---|---|---|\n")
            for uid, note, log in rows:
                f.write("| %s | %s | %s |\n" % (uid, note, ", ".join("%s %d" % kv for kv in sorted(log.items()))))
        if not keep:
            g.stop()
        print(gc.WD.summary())
        print(open(os.path.join(run_dir, "modes.md"), encoding="utf-8").read())
        print("run folder", run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
