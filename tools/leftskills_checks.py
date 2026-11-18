"""Check `leftskills` (tools/game_checks.py; docs/left-skills.md): skills that were right-button only, cast from the left
button, and Move Only, on the player path (background clicks) in HD.

Parts, each a row of the report:
  - select: `skill left|right <id>` sends the game's own select packet (0x3c) to the server, which refuses a skill whose
    skills.txt leftskill is not 1: every LS_CAST skill and Move Only are taken on the left, the LS_RIGHT skills (an
    aura, a corpse-targeted totem, Scroll of Identify) are refused there and taken on the right;
  - cast: each LS_CAST skill on the left button, a left click on a zombie (on the ground for the teleports and the totem) and the signs
    that the skill ran: mana spent, a new unit (summon), a new state (buff), a skill mode, the zombie's life, missiles, a
    warp; a skill with no sign is clicked once on the right as a control;
  - Move Only: a left click on the ground walks there; a left and a right click on a zombie walk up to it, the zombie keeps its
    life and no mana is spent; the same for the harness `cast ... unit` (the cast packets' path; the plugin's `moveonly`
    counter of srvstfunc 71 refusals is recorded);
  - pop-ups: the left and the right skill pop-up shot in HD and in legacy graphics (Move Only and the learnt skills shown on
    the left are judged on the shots);
  - save: Save and Exit with a formerly right-only skill of the player's class (LS_SAVE) on the left, back in the game the
    left button still holds it and Move Only is still known.
The gamepad part is `leftskills_pad` (MXL_CHAR on a gamepad UI, harness `pad` / `padui`)."""
import os
import re
import time

LS_CAST = (("Slayer", "summon", "unit"), ("Sacrifices", "missile", "unit"), ("Deathlord", "buff", "unit"),
           ("Bend the Shadows", "teleport", "ground"), ("Cleave", "melee", "unit"), ("Blink", "teleport", "ground"))
# right only: an aura, a corpse-targeted skill (the totems cast nothing from the left) and an item skill
LS_RIGHT = ("Wolf Stance", "Deaths Fury Totem", "Scroll of Identify")
# save: a skill of the player's own class (`h state` class id), formerly right-only where the class has one (the Barbarian has
# none: Aerials Disaster was already on the left). D2 saves only the class's own skills, so a skill of another class given by
# `setskill` (Sacrifices on an Amazon, bug #616) is gone after Save and Exit and the left button falls back to Attack.
LS_SAVE = {0: "Ecstatic Frenzy", 1: "Flamestrike", 2: "Sacrifices", 3: "Tainted Blood", 4: "Aerials Disaster",
           5: "Plague Avatar", 6: "Blink"}
MO = "Move Only"
SKILL_MODES = set(range(9, 17)) | {18}  # BL SC TH KK S1-S4 DD SQ (plrmode.txt): a skill, not a plain attack (A1 / A2)
SUB_X, SUB_Y = 27, 13.5  # HD screen pixels per sub-tile along x - y / x + y (game_checks.click_unit)


def spot(dx, dy):
    """Fractions of the 1600 x 900 client for the sub-tile (player + dx, player + dy)."""
    return (800 + (dx - dy) * SUB_X) / 1600, (405 + (dx + dy) * SUB_Y) / 900


def mana(gc):
    m = re.search(r"mana=(-?\d+)", " ".join(gc.hstate()["lines"]))
    return int(m.group(1)) if m else None


def look(gc, mid=None):
    st = gc.hstate()
    p = st["player"]
    m = re.search(r"mana=(-?\d+)", " ".join(st["lines"]))
    life = next((x.get("life") for x in st["mons"] if x.get("id") == mid), None) if mid else None
    return {"xy": (p.get("x", 0), p.get("y", 0)), "mana": int(m.group(1)) if m else None, "life": life,
            "mons": {x.get("id") for x in st["mons"]}, "mode": p.get("mode"), "states": pstates(gc)}


def pstates(gc):
    _, lines = gc.H("states player", 15)
    return {int(m.group(1)) for ln in lines for m in [re.match(r"server state (\d+):", ln)] if m}


def dist(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def tank(gc):
    import skill_sweep
    for s, v in ((7, skill_sweep.LIFE_MAX), (6, skill_sweep.LIFE_MAX), (9, skill_sweep.MANA), (8, skill_sweep.MANA)):
        gc.setstat("player", s, v << 8)
    gc.setstat("player", 13, skill_sweep.EXP_120)
    gc.setstat("player", 12, 120)


def target(gc, log, dx=4):
    px, py = gc.player_xy()
    _, sp = gc.Hl("spawn 5 1 %d %d" % (px + dx, py), log)
    mid = gc.first(sp, r"id=(\d+)")
    if mid is not None:
        for s in (7, 6):
            gc.setstat("mon:%d" % mid, s, 30000 << 8)
    return mid


def save_skill(gc):
    """(class id, LS_SAVE name, skill id) for the player in the game; the id is None for a class LS_SAVE does not name."""
    cls = gc.hstate()["player"].get("class")
    name = LS_SAVE.get(cls)
    sid, _ = gc.pic_skill(name) if name else (None, None)
    return cls, name, sid


def moveonly_counter(gc):
    m = re.search(r"moveonly .*casts refused (\d+)", gc.mxl_text())
    return int(m.group(1)) if m else None


def wake(gc, log):
    """After a waypoint warp the player stands in the town modes (TN / TW, 5 / 6) until the first step, and no skill is used
    there: one left step on the ground with no skill on the buttons."""
    for _ in range(3):
        if look(gc)["mode"] not in (5, 6):
            return
        gc.Hl("skill left 0", log)
        gc.g.click(*spot(3, 1))
        time.sleep(1.2)


def clear(gc):
    for _ in range(20):
        if not gc.H("kill nearest", 8)[0]:
            break


def cast_left(gc, name, kind, how, log):
    """One formerly right-only skill on the left button, used by left clicks; (ok, note). A skill that shows nothing on the
    left is clicked once more on the right as a control (the note says which)."""
    sid, _sk = gc.pic_skill(name)
    if sid is None:
        return False, "%s: not in the built tables" % name
    gc.learn(sid, 1)
    ok, _ = gc.Hl("skill left %d" % sid, log)
    if not ok:
        return False, "%s (%s): not taken on the left" % (name, kind)
    signs = click_signs(gc, how, "left", log)
    note = "%s (%s, id %d): %s" % (name, kind, sid, ", ".join(sorted(signs)) or "no sign")
    if not signs:
        gc.Hl("skill right %d" % sid, log)
        control = click_signs(gc, how, "right", log)
        gc.Hl("skill right 0", log)
        note += "; right-click control: %s" % (", ".join(sorted(control)) or "no sign either")
    return bool(signs), note


def click_signs(gc, how, button, log):
    """Two clicks (the second only when the first shows nothing) with `button` at a zombie or the ground; the signs seen."""
    clear(gc)
    tank(gc)
    mid = target(gc, log) if how == "unit" else None
    time.sleep(0.8)  # the client shows the new monster (the hover needs it on screen)
    gc.Hl("missiles reset", log)
    before = look(gc, mid)
    signs = set()
    for _ in range(2):
        if how == "unit":
            gc.click_unit(mid, button=button)
        else:
            gc.g.click(*spot(8, -2), button=button)
        time.sleep(0.35)
        quick = look(gc, mid)
        if quick["mode"] in SKILL_MODES:
            signs.add("mode %s" % quick["mode"])
        if how == "ground" and dist(quick["xy"], before["xy"]) >= 5:
            signs.add("warp %d" % dist(quick["xy"], before["xy"]))
        time.sleep(1.6)
        after = look(gc, mid)
        if before["mana"] is not None and after["mana"] is not None and after["mana"] < before["mana"]:
            signs.add("mana %d->%d" % (before["mana"], after["mana"]))
        new = after["mons"] - before["mons"] - {mid}
        if new:
            signs.add("new units %d" % len(new))
        if after["states"] - before["states"]:
            signs.add("states %s" % sorted(after["states"] - before["states"]))
        if mid and before["life"] and after["life"] is not None and after["life"] < before["life"]:
            signs.add("target life %d->%d" % (before["life"], after["life"]))
        _, ml = gc.Hl("missiles", log)
        seen = gc.missiles_seen(ml)
        if seen:
            signs.add("missiles %s" % sum(seen.values()))
        if signs:
            break
    if mid:
        gc.H("kill %s" % mid)
    return signs


def move_only(gc, log, rows, bad):
    mo, _ = gc.pic_skill(MO)
    if mo is None:
        bad.append("no Move Only row")
        return
    for side in ("right", "left"):
        ok, _ = gc.Hl("skill %s %d" % (side, mo), log)
        rows.append("Move Only taken on the %s: %s" % (side, ok))
        if not ok:
            bad.append("Move Only not on the %s" % side)
    clear(gc)
    tank(gc)
    # a ground click walks
    b = look(gc)
    gc.g.click(*spot(7, 0))
    time.sleep(2.5)
    a = look(gc)
    walked = dist(a["xy"], b["xy"])
    rows.append("Move Only ground click: moved %d sub-tiles (%s -> %s), mana %s -> %s" % (walked, b["xy"], a["xy"], b["mana"], a["mana"]))
    if walked < 4:
        bad.append("Move Only ground click did not walk")
    shots = []
    for button in ("left", "right"):
        gc.Hl("skill %s %d" % (button, mo), log)
        mid = target(gc, log, dx=8)
        n0 = moveonly_counter(gc)
        b = look(gc, mid)
        for _ in range(3):
            gc.click_unit(mid, button=button)
            time.sleep(1.5)
        a = look(gc, mid)
        n1 = moveonly_counter(gc)
        shots.append(gc.sh("leftskills_moveonly_%s" % button))
        mon_xy = next(((x.get("mx"), x.get("my")) for x in gc.hstate()["mons"] if x.get("id") == mid), None)
        near = dist(a["xy"], mon_xy) if mon_xy and None not in mon_xy else None
        rows.append("Move Only %s click on a zombie: player %s -> %s (zombie %s, %s sub-tiles), life %s -> %s, mana %s -> %s, "
                    "refused casts %s -> %s" % (button, b["xy"], a["xy"], mon_xy, near, b["life"], a["life"], b["mana"], a["mana"], n0, n1))
        if a["life"] is None or b["life"] is None or a["life"] < b["life"]:
            bad.append("Move Only %s click hurt the zombie (or it is gone)" % button)
        if near is None or near > 3:
            bad.append("Move Only %s click did not walk up to the zombie" % button)
        if a["mana"] is not None and b["mana"] is not None and a["mana"] < b["mana"] - 1:
            bad.append("Move Only %s click spent mana" % button)
        gc.H("kill %s" % mid)
    # the server side: the cast packets' own path (harness `cast ... unit`). Move Only's anim WL puts the player in the walk
    # mode (2) and the game starts no skill, so srvstfunc 71 (the plugin's refusal) is not reached: its counter is recorded only
    mid = target(gc, log, dx=2)
    time.sleep(0.8)
    n0, b = moveonly_counter(gc), look(gc, mid)
    for _ in range(3):
        gc.Hl("cast %d unit %d" % (mo, mid), log)
        time.sleep(0.6)
    n1, a = moveonly_counter(gc), look(gc, mid)
    rows.append("Move Only server cast at a zombie (3 times): life %s -> %s, mana %s -> %s, refused casts %s -> %s"
                % (b["life"], a["life"], b["mana"], a["mana"], n0, n1))
    if a["mana"] is not None and b["mana"] is not None and a["mana"] < b["mana"] - 1:
        bad.append("Move Only server cast spent mana")
    if a["life"] is None or b["life"] is None or a["life"] < b["life"]:
        bad.append("Move Only server cast hurt the zombie (or it is gone)")
    gc.H("kill %s" % mid)
    return shots


def selection(gc, log, rows, bad):
    for name in LS_RIGHT:
        sid, _ = gc.pic_skill(name)
        if sid is None:
            bad.append("no %s row" % name)
            continue
        gc.learn(sid, 1)
        left, _ = gc.Hl("skill left %d" % sid, log)
        right, _ = gc.Hl("skill right %d" % sid, log)
        rows.append("%s (id %d): left %s, right %s" % (name, sid, left, right))
        if left:
            bad.append("%s taken on the left" % name)
        if not right:
            bad.append("%s not taken on the right" % name)


def run(gc):
    mark = gc.engine_mark()
    if not gc.need_game():
        return gc.add("leftskills", "BLOCKED", "not in a game")
    log, rows, bad, shots = [], [], [], []
    gc.set_graphics("hd")
    gc.goto(2)
    tank(gc)
    gc.Hl("skill left 0", log)
    gc.Hl("skill right 0", log)
    for name, kind, how in LS_CAST:
        wake(gc, log)
        ok, note = cast_left(gc, name, kind, how, log)
        rows.append("cast from the left: " + note)
        if not ok:
            bad.append(note)
        gc.revive_if_dead()
        gc.goto(2)
    shots.append(gc.sh("leftskills_cast_end"))
    selection(gc, log, rows, bad)
    shots += move_only(gc, log, rows, bad) or []
    # pop-ups: Move Only on the left, the learnt formerly right-only skills listed there
    mo, _ = gc.pic_skill(MO)
    gc.Hl("skill left %d" % mo, log)
    gc.goto(1)
    for mode in ("hd", "legacy"):
        if not gc.pic_popups(mode, log, shots):
            bad.append("graphics mode %s not reached" % mode)
    gc.set_graphics(os.environ.get("MXL_GRAPHICS") or "hd")  # the save part in the run's graphics mode
    # save: a formerly right-only skill of the player's class on the left survives Save and Exit
    cls, name, sid = save_skill(gc)
    if sid is None:
        bad.append("no save skill for class %s" % cls)
        sid = 0
    else:
        gc.learn(sid, 1)
    picked, _ = gc.Hl("skill left %d" % sid, log)
    rows.append("save skill of class %s: %s (id %d) on the left: %s" % (cls, name, sid, picked))
    gc.Hl("skill right %d" % mo, log)
    gc.leave_and_reenter()
    time.sleep(2)
    _, lines = gc.Hl("skill", log)
    m = re.search(r"left=(-?\d+) right=(-?\d+)", " ".join(lines))
    got = (int(m.group(1)), int(m.group(2))) if m else None
    rows.append("after Save and Exit: buttons %s (wanted left %d, right %d)" % (got, sid, mo))
    if not got or got[0] != sid:
        bad.append("left skill not kept by Save and Exit: %s" % (got,))
    ok, _ = gc.Hl("skill left %d" % mo, log)
    rows.append("Move Only known after the reload: %s" % ok)
    if not ok:
        bad.append("Move Only gone after the reload")
    time.sleep(6)  # the HUD is drawn some seconds after the harness answers (a shot at once caught the loading screen)
    shots.append(gc.sh("leftskills_after_reload"))
    if not gc.game_alive():
        bad.append("the game died")
    gc.finish("leftskills", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log,
              partial="the pop-up shots (Move Only and the learnt skills in the left pop-up, HD and legacy) are judged by hand")


# Gamepad: a pad script (tools/pad_input.py words) with a shot after each step ('|' separates the steps). The default: Start
# (the first press only switches to the gamepad UI) opens the panel menu, RB twice to the Skill Tree (past Charm Inventory),
# RT three times to General Skills, the D-pad onto a skill, X (Bind Skill) opens the rebind dialog, B binds it to B.
LS_PAD_STEPS = ("start wait:1 | start wait:1 | rb wait:0.6 | rb wait:1 | rt wait:0.6 | rt wait:0.6 | rt wait:1 | down wait:1 | "
                "right wait:1 | x wait:1.5 | b wait:1 | b wait:1")


def run_pad(gc):
    """Check `leftskills_pad`: the gamepad's skill assignment with every skill now on both buttons. A pad script
    (MXL_LS_PAD, default LS_PAD_STEPS) runs step by step with a shot after each; `skill` reads the buttons afterwards."""
    import pad_input as pi
    mark = gc.engine_mark()
    if not gc.need_game():
        return gc.add("leftskills_pad", "BLOCKED", "not in a game")
    log, rows, shots = [], [], []
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    mo, _ = gc.pic_skill(MO)
    _, _, sid = save_skill(gc)
    if sid is not None:
        gc.learn(sid, 1)
    gc.Hl("skill left 0", log)
    gc.Hl("skill right 0", log)
    st = pi.on(gc.H, log)
    rows.append("pad on: %s" % st)
    pi.run_script(gc.H, "stick:l:0:40 wait:0.4 stick:l:0:0 wait:2", log)
    for n, step in enumerate((os.environ.get("MXL_LS_PAD") or LS_PAD_STEPS).split("|")):
        pi.run_script(gc.H, step.strip(), log)
        shots.append(gc.sh("leftskills_pad_%02d" % n))
        _, lines = gc.Hl("skill", log)
        rows.append("step %d %r: %s" % (n, step.strip(), " ".join(lines)[-60:]))
    pi.off(gc.H, log)
    gc.finish("leftskills_pad", True, "; ".join(rows) + "; Move Only id %s" % mo, mark, shots, rows + log,
              partial="the gamepad assignment is judged on the shots")
