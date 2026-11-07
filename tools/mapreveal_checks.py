"""Lane mapreveal: the pity map reveal (check `mapreveal` of tools/game_checks.py; plugin part `mapreveal`,
plugin/src/map_reveal.cpp, docs/plugin-plan.md section 34).

The Controls action "Reveal Level Map" (default L) reveals the rest of the current level's automap once the level is explored to
the threshold (mxl2012-core.toml [mapreveal] threshold, default 70). One chat line says when the reveal is available, one answers
each press (refused with the percent, or done).

Set-up (SHORTCUT, named in the note): the threshold is lowered with the harness `mapreveal threshold N` to the level's current
share (walking 70 % of a level by script takes too long); the settings file is not written and 70 is set back after each level.
The key is a real background press of L (InputService), with the harness `mapreveal press` (the same code) when the press does
not reach the plugin. Each level: arrive, walk a little, a refused press at 70 (the percent in the line), a refused press at 101
(off), the automap shot before, the threshold at the current share and the "available" line, the press that reveals, the automap
shot after, a second press ("already revealed"), a few steps more with the game alive. Town: the "no reveal" line.

HD: Cold Plains (3, a big outdoor level) and the Den of Evil (8, a dungeon); legacy: Blood Moor (2) and Cave Level 1 (9).
"""
import re
import time

TOWN = 1
HD_LEVELS = [(3, "cold_plains", 14, 0), (8, "den_of_evil", 0, 14)]
LEGACY_LEVELS = [(2, "blood_moor", 14, 0), (9, "cave_level_1", 0, 14)]


def parse_state(lines):
    """`h mapreveal` -> {gate, key, last, and the numbers (level, rooms, percent, threshold, presses, reveals, ...)}."""
    out = {}
    for ln in lines:
        ln = ln.strip()
        m = re.match(r'mapreveal last="(.*)"$', ln)
        if m:
            out["last"] = m.group(1)
            continue
        if ln.startswith("mapreveal on="):
            out.update({k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)\b", ln)})
            m = re.search(r"gate=(\w+)", ln)
            out["gate"] = m.group(1) if m else None
            m = re.search(r"key=(\S+)", ln)
            out["key"] = m.group(1) if m else None
    return out


def state(gc, log, verb="mapreveal"):
    _ok, lines = gc.Hl(verb, log)
    return parse_state(lines)


def wait_for(gc, log, cond, timeout=4.0):
    t0 = time.time()
    st = state(gc, log)
    while not cond(st) and time.time() - t0 < timeout:
        time.sleep(0.4)
        st = state(gc, log)
    return st


def press(gc, log, how):
    """One press of the key; returns (state after, how it went: "key" or "harness")."""
    s0 = state(gc, log)
    if how == "key":
        gc.g.press("l")
        st = wait_for(gc, log, lambda s: s.get("presses", 0) > s0.get("presses", 0), 3.0)
        if st.get("presses", 0) > s0.get("presses", 0):
            return st, "key"
        log.append("the background L press did not reach the plugin (presses +0): `mapreveal press`")
    gc.Hl("mapreveal press", log)
    return wait_for(gc, log, lambda s: s.get("presses", 0) > s0.get("presses", 0), 3.0), "harness"


def walk(gc, dx, dy, steps):
    for _ in range(steps):
        st = gc.hstate()["player"]
        gc.H("move %d %d" % (st["x"] + dx, st["y"] + dy))
        time.sleep(1.2)


def automap(gc, on):
    """The automap (Tab) open or closed; the plugin does not report it, so Tab is pressed once per change."""
    gc.g.key("tab")
    time.sleep(1.0)


def level_round(gc, log, shots, row, mode, area, name, dx, dy, how):
    st = gc.goto(area, timeout=60)
    if st["player"].get("area") != area:
        row("%s %s" % (mode, name), False, "area %d not reached" % area)
        return how
    time.sleep(2)
    walk(gc, dx, dy, 6)
    s = wait_for(gc, log, lambda s: s.get("level") == area)
    tag = "%s %s" % (mode, name)
    row(tag + " counted", s.get("level") == area and s.get("rooms", 0) > 0 and 0 < s.get("seenarea", 0) <= s.get("area", 0)
        and s.get("gate") in ("below", "ready"),
        "level %s, %s rooms, %s of %s tiles active = %s%%, gate %s" % (s.get("level"), s.get("rooms"), s.get("seenarea"), s.get("area"),
                                                                     s.get("percent"), s.get("gate")))

    # refused at 70 (the share is far below after a few steps), the percent in the line
    gc.Hl("mapreveal threshold 70", log)
    r0 = s.get("refusals", 0)
    s, how = press(gc, log, how)
    want = "Map: %d%% of this level explored (70%% needed)." % s.get("percent", -1)
    row(tag + " refused at 70", s.get("gate") == "below" and s.get("refusals", 0) == r0 + 1 and s.get("last") == want
        and not s.get("revealed"), "press by %s, line %r, %s%%" % (how, s.get("last"), s.get("percent")))
    shots.append(gc.sh("mapreveal_%s_%s_refused" % (mode, name)))

    # threshold 101: off
    gc.Hl("mapreveal threshold 101", log)
    s = wait_for(gc, log, lambda s: s.get("gate") == "off")
    s, how = press(gc, log, how)
    row(tag + " off at 101", s.get("gate") == "off" and s.get("last") == "Map: the level reveal is off (mxl2012-core.toml)."
        and not s.get("revealed"), "line %r" % s.get("last"))

    # the automap before; the threshold at the current share: the "available" line, then the reveal
    automap(gc, True)
    shots.append(gc.sh("mapreveal_%s_%s_before" % (mode, name)))
    s = state(gc, log)
    pct = s.get("percent", 0)
    a0 = s.get("announces", 0)
    gc.Hl("mapreveal threshold %d" % pct, log)
    s = wait_for(gc, log, lambda s: s.get("announces", 0) > a0 and s.get("held", 0) == 0, 6.0)
    row(tag + " available line", s.get("gate") == "ready" and s.get("announced") == 1 and s.get("announces", 0) == a0 + 1
        and (s.get("last") or "").startswith("Map: %d%% of this level explored. Press " % s.get("percent", -1)),
        "threshold %d: line %r" % (pct, s.get("last")))
    v0, f0 = s.get("reveals", 0), s.get("faults", 0)
    s, how = press(gc, log, how)
    time.sleep(1.5)
    shots.append(gc.sh("mapreveal_%s_%s_after" % (mode, name)))
    s = state(gc, log)
    row(tag + " revealed", s.get("reveals", 0) == v0 + 1 and s.get("revealed") == 1 and s.get("faults", 0) == f0
        and s.get("lastmade", -1) == s.get("lastrooms", -2) == s.get("rooms") and (s.get("last") or "").startswith("Map: rest of the level revealed"),
        "press by %s: %s of %s rooms made in %s ms, line %r" % (how, s.get("lastmade"), s.get("lastrooms"), s.get("lastms"), s.get("last")))

    s, how = press(gc, log, how)
    row(tag + " second press", s.get("reveals", 0) == v0 + 1 and s.get("last") == "Map: this level is already revealed.",
        "line %r" % s.get("last"))
    automap(gc, False)

    # the game goes on: a few steps on the revealed level
    walk(gc, -dx, -dy, 3)
    st = gc.hstate()["player"]
    s = state(gc, log)
    row(tag + " game goes on", st.get("area") == area and s.get("faults", 0) == f0 and s.get("revealed") == 1,
        "area %s after 3 steps, faults %s" % (st.get("area"), s.get("faults")))
    gc.Hl("mapreveal threshold 70", log)
    return how


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    gc.goto(TOWN, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    st = state(gc, log)
    row("part on", st.get("on") == 1 and st.get("threshold") == 70 and st.get("key") == "L",
        "threshold %s (mxl2012-core.toml), key %s" % (st.get("threshold"), st.get("key")))

    # town: no reveal
    how = "key"
    s, how = press(gc, log, how)
    row("town refused", s.get("gate") == "excluded" and s.get("last") == "Map: no reveal in this area." and not s.get("revealed"),
        "press by %s, line %r" % (how, s.get("last")))
    shots.append(gc.sh("mapreveal_hd_town_refused"))

    for area, name, dx, dy in HD_LEVELS:
        how = level_round(gc, log, shots, row, "hd", area, name, dx, dy, how)

    gc.goto(TOWN, timeout=60)
    if gc.set_graphics("legacy"):
        for area, name, dx, dy in LEGACY_LEVELS:
            how = level_round(gc, log, shots, row, "legacy", area, name, dx, dy, how)
        gc.goto(TOWN, timeout=60)
        gc.set_graphics("hd")
    else:
        row("legacy", False, "legacy graphics not reached")

    gc.Hl("mapreveal threshold 70", log)
    st = state(gc, log)
    log.append("final %s" % st)
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged) and not st.get("faults")
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
    note += "; key press by %s; SHORTCUT: threshold set by the harness to the level's share" % how
    gc.finish("mapreveal", ok, note, mark, shots, log)
