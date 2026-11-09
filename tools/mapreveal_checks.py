"""The level map reveal (check `mapreveal` of tools/game_checks.py; plugin part `mapreveal`, plugin/src/map_reveal.cpp,
docs/plugin-plan.md section 34).

The Controls action "Reveal Level Map" (default L) reveals the current level's automap on every press, from the arrival on
(bug #559, owner 2026-11-08: no explored share, no threshold). Only levels in mxl2012-core.toml [mapreveal] exclude (empty by
default) are refused. The five act towns are revealed by themselves on each arrival, with no key (owner, 2026-11-08).

Each level: arrive, the automap shot (Tab) right away, a real background press of L (the harness `mapreveal press`, the same
code, when the press does not reach the plugin), the automap shot after, then a second press and a few steps with the game
alive. The automap cell count of D2R's current layer (`h mapreveal` cells=) is read before and after: a level that is not
drawn whole on arrival must gain cells; a town must be whole before any key press (`h mapreveal` townreveals= grew, every room
made, no press and no chat line) and L adds nothing to it.

HD: Catacombs Level 1 (34, a maze), Catacombs Level 4 (37, a small preset level), the Rogue Encampment (1), then Act 3: Kurast
Sewers Level 1 (92, a maze), Kurast Docks (75), and the arrival only in the other three towns. Legacy: Sewers Level 2 (93, a
small preset level), Kurast Docks (75), then Act 1: Catacombs Level 2 (35, a maze), the Rogue Encampment (1). Each town round
comes from another level, so it is a real arrival; the HD tour changes act each time. In every town L must add no cell: the
counters alone cannot tell whether the map was drawn. Lut Gholein, the Fortress and Harrogath have few cells (17, 29, 6).
"""
import os
import re
import time

HD_LEVELS = [(34, "catacombs_1", False), (37, "catacombs_4", False), (1, "rogue_encampment", True), (92, "kurast_sewers_1", False),
             (75, "kurast_docks", True)]
LEGACY_LEVELS = [(93, "kurast_sewers_2", False), (75, "kurast_docks", True), (35, "catacombs_2", False), (1, "rogue_encampment", True)]
HD_TOWNS = [(40, "lut_gholein"), (103, "pandemonium_fortress"), (109, "harrogath"), (1, "rogue_encampment_from_act5")]  # act changes


def parse_state(lines):
    """`h mapreveal` -> {key, last, and the numbers (level, presses, reveals, lastmade, lastrooms, cells, ...)}."""
    out = {}
    for ln in lines:
        ln = ln.strip()
        m = re.search(r'mapreveal last="(.*)"$', ln)
        if m:
            out["last"] = m.group(1)
            continue
        if "mapreveal on=" in ln:
            out.update({k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)\b", ln)})
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


def automap(gc):
    """The automap (Tab) open or closed; the plugin does not report it, so Tab is pressed once per change."""
    gc.g.key("tab")
    time.sleep(1.0)


def town_arrived(gc, log, row, tag, area, before):
    """The town's map was revealed by the arrival alone. Returns the state, reached with no key press."""
    s = wait_for(gc, log, lambda x: x.get("town") == area and x.get("townreveals", 0) > before.get("townreveals", 0), 12.0)
    row(tag + " revealed on arrival, no key", s.get("town") == area and s.get("townreveals", 0) > before.get("townreveals", 0)
        and s.get("townrooms", 0) > 0 and s.get("townmade", -1) == s.get("townrooms") and s.get("presses") == before.get("presses")
        and s.get("lines") == before.get("lines") and s.get("faults", 0) == before.get("faults", 0),
        "town %s, %s of %s rooms made, %s town reveals so far, presses %s -> %s, chat lines %s -> %s, automap cells %s" % (
            s.get("town"), s.get("townmade"), s.get("townrooms"), s.get("townreveals"), before.get("presses"), s.get("presses"),
            before.get("lines"), s.get("lines"), s.get("cells")))
    return s


def town_tour(gc, log, shots, row, mode, area, name, how):
    before = state(gc, log)
    st = gc.goto(area, timeout=60)
    tag = "%s %s" % (mode, name)
    if st["player"].get("area") != area:
        row(tag, False, "area %d not reached" % area)
        return how
    s0 = town_arrived(gc, log, row, tag, area, before)
    automap(gc)
    shots.append(gc.sh("mapreveal_%s_%s_arrival" % (mode, name)))
    s, how = press(gc, log, how)
    time.sleep(1.0)
    s = state(gc, log)
    shots.append(gc.sh("mapreveal_%s_%s_after_key" % (mode, name)))
    row(tag + " whole before the key", s.get("cells", 0) == s0.get("cells", 0) and s.get("cells", 0) > 0 and s.get("faults", 0) == 0,
        "automap cells %s on arrival -> %s after L (layer %s)" % (s0.get("cells"), s.get("cells"), s.get("layer")))
    automap(gc)
    return how


def level_round(gc, log, shots, row, mode, area, name, town, how):
    before = state(gc, log)
    st = gc.goto(area, timeout=60)
    tag = "%s %s" % (mode, name)
    if st["player"].get("area") != area:
        row(tag, False, "area %d not reached" % area)
        return how
    time.sleep(1.5)  # the arrival: no walking before the press
    s0 = town_arrived(gc, log, row, tag, area, before) if town else state(gc, log)
    automap(gc)
    shots.append(gc.sh("mapreveal_%s_%s_arrival" % (mode, name)))
    v0, f0 = s0.get("reveals", 0), s0.get("faults", 0)
    s, how = press(gc, log, how)
    time.sleep(1.5)
    s = state(gc, log)
    shots.append(gc.sh("mapreveal_%s_%s_revealed" % (mode, name)))
    grew = s.get("cells", 0) > s0.get("cells", 0)
    row(tag + " revealed at arrival", s.get("level") == area and s.get("reveals", 0) == v0 + 1 and s.get("faults", 0) == f0
        and s.get("lastrooms", 0) > 0 and s.get("lastmade", -1) == s.get("lastrooms") and s.get("last") == "Map: level revealed."
        and (s.get("cells", 0) == s0.get("cells", 0) if town else grew),
        "press by %s: level %s, %s of %s rooms made in %s ms, automap cells %s -> %s%s, line %r" % (
            how, s.get("level"), s.get("lastmade"), s.get("lastrooms"), s.get("lastms"), s0.get("cells"), s.get("cells"),
            " (a town: whole before the key)" if town else "", s.get("last")))
    if not town:
        row(tag + " no reveal by itself", s.get("townreveals") == s0.get("townreveals"), "town reveals %s -> %s" % (
            s0.get("townreveals"), s.get("townreveals")))

    c1 = s.get("cells", 0)
    s, how = press(gc, log, how)
    time.sleep(0.8)
    s = state(gc, log)
    row(tag + " second press", s.get("reveals", 0) == v0 + 2 and s.get("last") == "Map: level revealed." and s.get("cells", 0) >= c1
        and s.get("faults", 0) == f0, "line %r, cells %s -> %s" % (s.get("last"), c1, s.get("cells")))
    automap(gc)

    walk(gc, 10, 0, 2)  # the game goes on: a few steps on the revealed level
    walk(gc, 0, 10, 1)
    st = gc.hstate()["player"]
    s = state(gc, log)
    row(tag + " game goes on", st.get("area") == area and s.get("faults", 0) == f0,
        "area %s after 3 steps, faults %s" % (st.get("area"), s.get("faults")))
    return how


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    gc.cheat("god 1")  # the dungeons' monsters at the arrival: the check judges the map, not the fight
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    st = state(gc, log)
    cfg = os.path.join(gc.g.GAME_DIR, "mods", "mxl2012", "d2rloader", "config", "mxl2012-core.toml")
    try:
        cfg_text = open(cfg, encoding="utf-8").read()
    except OSError:
        cfg_text = ""
    old = bool(re.search(r"(?m)^\s*threshold\s*=", cfg_text))
    report = [ln for ln in (gc.g._read_from(gc.g.MXL_LOG, 0) or "").splitlines() if "mapreveal on:" in ln or "mapreveal off" in ln][-1:]
    report = report[0] if report else ""
    row("part on", st.get("on") == 1 and st.get("key") == "L" and st.get("excluded") == 0 and "mapreveal on:" in report
        and (("old threshold ignored" in report) == old),
        "key %s, excluded %s; the settings file %s an old threshold line; report %r" % (
            st.get("key"), st.get("excluded"), "has" if old else "has no", report[-160:]))

    how = "key"
    for area, name, town in HD_LEVELS:
        how = level_round(gc, log, shots, row, "hd", area, name, town, how)
    for area, name in HD_TOWNS:
        how = town_tour(gc, log, shots, row, "hd", area, name, how)

    if gc.set_graphics("legacy"):
        for area, name, town in LEGACY_LEVELS:
            how = level_round(gc, log, shots, row, "legacy", area, name, town, how)
        gc.set_graphics("hd")
    else:
        row("legacy", False, "legacy graphics not reached")
    gc.goto(1, timeout=60)

    st = state(gc, log)
    log.append("final %s" % st)
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged) and not st.get("faults")
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
    note += "; key press by %s" % how
    gc.finish("mapreveal", ok, note, mark, shots, log)
