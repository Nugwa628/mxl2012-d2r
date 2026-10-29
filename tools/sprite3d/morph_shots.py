#!/usr/bin/env python
"""Screenshot a Druid shapeshift form in game: neutral, walk, run, attack, cast and get hit, in game_ctl's background input mode.

  py -3 tools/sprite3d/morph_shots.py [--slot N] [--skill 1364] [--area 2] [--keep] [--no-start] [--tag wereowl]

`MXL_MORPH_DIRS=1` adds eight short walks (phases dir0..dir7, two frames each) in the eight facings.

The slot's lock must be held by the caller (game_slots.py lock N <owner>, then MXL_RUN=<owner>); this script never takes or
removes a lock. The test character is whoever the slot's first card is (MxlBarb): the harness `class 5` makes it a Druid for
the skill checks, `setskill <skill> 1` gives it the morph skill (D2R skill id of Median's wereowl_form = 1364, werewolf_form
1380, werebear_morph 1375) and `cast <skill> self` morphs it. Frames are written as <tag>_<phase>_<n>.png into the run folder;
`morph.md` lists them. Never touches the real mouse, keyboard or focus (game_checks background mode).
"""
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import game_checks as gc  # noqa: E402
import game_ctl as g  # noqa: E402

g.game_slots.release = lambda *a, **k: None  # the caller holds the slot's lock for the whole lane


def burst(tag, phase, n, pause, rows):
    for j in range(n):
        gc.guard()
        gc.sh("%s_%s_%d" % (tag, phase, j))
        time.sleep(pause)
    rows.append((phase, n))


def ppos():
    p = gc.hstate()["player"]
    return p, p.get("x"), p.get("y")


def god():
    gc.H("stat player 7 set 25600000")
    gc.H("stat player 6 set 25600000")


def run(skill, tag, area, form_state):
    rows = []
    gc.enable_debug()
    gc.goto(area)
    gc.H("class 5")  # Druid skills on the test character
    god()
    for cmd in ("stat player 0 set 400", "stat player 2 set 400"):
        gc.H(cmd)
    # the form needs a knife (skills.txt itypea1 knif; Median code 143 is a knife). A character that already holds one keeps it
    # (the equip is refused: occupied); otherwise both hands are emptied (a shield or off-hand weapon blocks the place too)
    # and the knife equipped.
    if not gc.H("equip 143 rhand")[0]:
        gc.H("unequip lhand")
        gc.H("unequip rhand")
        g.log("knife: %s" % gc.H("equip 143 rhand")[0])
    for sk in (skill, 1367, 1366):
        gc.H("setskill %d 1" % sk)
    g.log("usable %s: %s" % (skill, gc.skill_usable(skill)))
    gc.H("kill nearest")
    gc.sh("%s_before" % tag)
    ok, lines = gc.H("cast %d self" % skill)
    g.log("cast %d: %s %s" % (skill, ok, lines[-2:]))
    time.sleep(0.15)
    burst(tag, "morph", 6, 0.12, rows)  # the transformation (cast mode) itself
    time.sleep(3.0)
    god()
    burst(tag, "neutral", 4, 0.4, rows)
    ok, st = gc.H("state")
    for ln in st:
        if ln.startswith("player"):
            g.log(ln)
    p, x, y = ppos()
    if x is not None:
        gc.H("move %d %d walk" % (x + 8, y + 3))
        burst(tag, "walk", 8, 0.25, rows)
        time.sleep(1.5)
        p, x, y = ppos()
        gc.H("move %d %d" % (x - 9, y - 4))
        burst(tag, "run", 8, 0.2, rows)
        time.sleep(1.5)
        if os.environ.get("MXL_MORPH_DIRS"):  # the form walking in eight directions (a sheet of every facing)
            for k, (dx, dy) in enumerate(((6, 6), (8, 0), (6, -6), (0, -8), (-6, -6), (-8, 0), (-6, 6), (0, 8))):
                p, x, y = ppos()
                gc.H("move %d %d walk" % (x + dx, y + dy))
                time.sleep(0.9)
                burst(tag, "dir%d" % k, 2, 0.2, rows)
            time.sleep(1.5)
    # attack: a target next to the player (Skeleton-class fodder), the form's attack skill then the plain attack
    gc.H("spawn 3 1")
    time.sleep(1.5)
    god()
    for k in range(2):
        gc.H("cast 1367 nearest")
        burst(tag, "attack1_%d" % k, 6, 0.15, rows)
        time.sleep(1.0)
    gc.H("cast 0 nearest")
    burst(tag, "attack_basic", 6, 0.15, rows)
    gc.H("kill nearest")
    # cast mode: a buff with the SC animation
    for k in range(2):
        gc.H("cast 1366 self")
        burst(tag, "cast_%d" % k, 6, 0.12, rows)
        time.sleep(1.0)
    # get hit: a stagger hit through the game's own damage path
    for k in range(3):
        gc.H("hit player phys 5 stagger")
        burst(tag, "gethit_%d" % k, 5, 0.1, rows)
        time.sleep(0.8)
    return rows


def main():
    a = sys.argv[1:]
    skill, area, start, keep, tag = 1364, 2, True, False, "wereowl"
    i = 0
    while i < len(a):
        if a[i] == "--skill":
            skill = int(a[i + 1]); i += 2
        elif a[i] == "--area":
            area = int(a[i + 1]); i += 2
        elif a[i] == "--tag":
            tag = a[i + 1]; i += 2
        elif a[i] == "--no-start":
            start = False; i += 1
        elif a[i] == "--keep":
            keep = True; i += 1
        else:
            i += 1
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
        rows = run(skill, tag, area, None)
    finally:
        gc.WD.stop_flag = True
        run_dir = g.current_run()
        with open(os.path.join(run_dir, "morph.md"), "w", encoding="utf-8") as f:
            f.write("| Phase | Frames |\n|---|---|\n")
            for ph, n in rows:
                f.write("| %s | %d |\n" % (ph, n))
        if not keep:
            g.stop()
        print(gc.WD.summary())
        print("run folder", run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
