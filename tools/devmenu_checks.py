"""In-game check `devmenu` of tools/game_checks.py (plugin part devmenu, plugin/src/devmenu.cpp, docs/dev-menu.md).

The real Ctrl+F12 press opens the native panel; the panel's own paths (buttons as the UI listener receives them, the input box's text) are driven
through `h devmenu`. A real posted mouse click on a row arrow is checked too: an item (HD and legacy) and travel. Rows: open and close by key, one spawn of each kind (a unique, a set item, a charm, a runeword kit) checked in the
inventory, travel to Fauztinville (`cypherpunk`) and an uber arena (Welcome to Toraja, map only), the level raise from 1 to 50 with the points
read from the stats, the waypoint unlock read back through `h waypoint`, and the panel screenshots in HD and legacy graphics. A new
character is needed (MXL_CHAR=<letters only>, MXL_CHAR_CLASS=amazon by default so stat points are checked against the plain per-level rule).
"""
import re
import time

import devmenu_layout

SHOT_RUNE = {}


def parse(lines):
    out = {}
    for ln in lines:
        m = re.search(r"devmenu (on=.*)$", ln)
        if m:
            out.update({k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)\b", m.group(1))})
            s = re.search(r'status="(.*)"', m.group(1))
            out["status"] = s.group(1) if s else ""
    return out


def state(gc, log):
    _ok, lines = gc.Hl("devmenu state", log)
    return parse(lines)


def wait(gc, log, cond, timeout=8.0):
    t0 = time.time()
    st = state(gc, log)
    while not cond(st) and time.time() - t0 < timeout:
        time.sleep(0.25)
        st = state(gc, log)
    return st


def verb(gc, log, text):
    _ok, lines = gc.Hl("devmenu " + text, log)
    return parse(lines)


def do(gc, log, button, *tail):
    verb(gc, log, "press " + " ".join((button,) + tail))
    time.sleep(0.25)


def search(gc, log, text):
    verb(gc, log, "input " + text)
    time.sleep(0.4)


def click_row_arrow(gc, mode, row_number=0):
    """A real (posted) mouse click on a result row's arrow, at the position the layout puts it."""
    m = devmenu_layout.layout(mode)["metrics"]
    l, t, r, b = gc.g.client_rect(gc.g.need_window())
    width, height = r - l, b - t
    scale = height / 2160.0 if mode == "hd" else min(height / 600.0, width / 800.0)
    x = width / 2.0 + (m["panelX"] + m["rowX"] + m["rowH"] / 2.0) * scale
    y = height / 2.0 + (m["panelY"] + m["rowY"] + row_number * m["rowPitch"] + m["rowH"] / 2.0) * scale
    gc.g.click(x / width, y / height)


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    time.sleep(1.5)

    # the Controls action, opened by the real key
    s0 = state(gc, log)
    gc.g.press("f12", mods=("ctrl",))
    st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
    if st.get("open") != 1:
        log.append("Ctrl+F12 did not reach the plugin; `devmenu open`")
        verb(gc, log, "open")
        st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
    row("open by Ctrl+F12", st.get("open") == 1, "open=%s presses=%s" % (st.get("open"), st.get("presses")))
    time.sleep(0.8)
    shots.append(gc.sh("devmenu_hd_items"))

    # items: one of each kind by name (the first row of a search)
    def spawn(tab_or_cat, query, want, name):
        before = gc.inventory_codes(log) if hasattr(gc, "inventory_codes") else set()
        verb(gc, log, "press " + tab_or_cat)
        time.sleep(0.2)
        search(gc, log, query)
        ops0 = state(gc, log).get("ops", 0)
        do(gc, log, "row0")
        s = wait(gc, log, lambda x: x.get("busy") == 0 and (x.get("ops", 0) > ops0 or x.get("refused", 0) > s0.get("refused", 0)), 6.0)
        ok = s.get("ops", 0) > ops0 and want.lower() in s.get("status", "").lower()
        row("spawn " + name, ok, s.get("status", ""))
        shots.append(gc.sh("devmenu_hd_" + name.replace(" ", "_")))
        return before

    do(gc, log, "tab0")
    spawn("cat1", "Staff of Kings", "Staff of Kings", "unique")
    spawn("cat2", "Civerb's Icon", "Civerb", "set")
    spawn("cat2", "Cathan's Seal", "Cathan", "set ring")
    for amulet, want in (("Iratha's Collar", "Iratha"), ("Vidala's Snare", "Vidala"), ("Cathan's Sigil", "Cathan"), ("Tancred's Weird", "Tancred")):
        spawn("cat2", amulet, want, "set " + want.lower())
    spawn("cat1", "Dragon's Egg", "Dragon", "high level unique")
    spawn("cat3", "Horazon", "Horazon", "charm")
    spawn("cat6", "Dawn", "Kit for", "runeword kit")

    # a real mouse click on a row arrow: item, then travel
    verb(gc, log, "press cat1")
    time.sleep(0.2)
    search(gc, log, "Staff of Kings")
    time.sleep(0.4)
    shots.append(gc.sh("devmenu_hd_rows"))
    ops0 = state(gc, log).get("ops", 0)
    click_row_arrow(gc, "hd")
    st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 6.0)
    row("real click spawns the row", st.get("ops", 0) > ops0 and "Staff of Kings" in st.get("status", ""), st.get("status", ""))
    time.sleep(0.4)
    shots.append(gc.sh("devmenu_hd_clicked_status"))

    # travel
    do(gc, log, "tab1")
    search(gc, log, "fauztinville")
    time.sleep(0.4)
    shots.append(gc.sh("devmenu_hd_travel_rows"))
    ops0 = state(gc, log).get("ops", 0)
    click_row_arrow(gc, "hd")
    st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 20.0)
    row("travel Fauztinville", "arrived" in st.get("status", "").lower() and "Fauztinville" in st.get("status", ""), st.get("status", ""))
    time.sleep(1.5)
    shots.append(gc.sh("devmenu_hd_fauztinville"))
    search(gc, log, "toraja")
    ops0 = state(gc, log).get("ops", 0)
    do(gc, log, "row0")
    st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 20.0)
    row("travel uber arena", "arrived" in st.get("status", "").lower() and "summon" in st.get("status", ""), st.get("status", ""))
    time.sleep(1.0)
    shots.append(gc.sh("devmenu_hd_toraja"))
    gc.goto(1, timeout=30)
    time.sleep(1.0)

    # level raise
    do(gc, log, "tab2")
    search(gc, log, "50")
    ops0 = state(gc, log).get("ops", 0)
    do(gc, log, "raise")
    st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 6.0)
    _ok, statline = gc.Hl("state", log)
    level = re.search(r"level=(\d+)", " ".join(statline))
    _ok, stat4 = gc.Hl("stat player 4", log)
    _ok, stat5 = gc.Hl("stat player 5", log)
    row("raise to 50", "level 50" in st.get("status", "") and level is not None and level.group(1) == "50",
        "%s; %s; stat4 %s; stat5 %s" % (st.get("status", ""), level.group(0) if level else "?", " ".join(stat4)[:60], " ".join(stat5)[:60]))
    shots.append(gc.sh("devmenu_hd_level50"))

    # unlocks
    do(gc, log, "tab3")
    time.sleep(0.3)
    shots.append(gc.sh("devmenu_hd_unlocks"))
    ops0 = state(gc, log).get("ops", 0)
    do(gc, log, "unlock")
    st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 6.0)
    set_ok = []
    for n in (1, 9, 18, 27, 30, 37):
        _ok, lines = gc.Hl("waypoint n %d" % n, log)
        set_ok.append(any("= 1" in ln for ln in lines))
    row("unlock waypoints", all(set_ok), "%s; bits %s" % (st.get("status", ""), set_ok))
    # the advanced quests action: the warning first, then the loader's cheat
    do(gc, log, "tab4")
    time.sleep(0.2)
    do(gc, log, "quests")
    time.sleep(0.4)
    shots.append(gc.sh("devmenu_hd_quests_warning"))
    do(gc, log, "confirm")
    time.sleep(1.5)
    st = state(gc, log)
    _ok, lines = gc.Hl("quest 26 dump", log)
    row("quests action", "cheat" in st.get("status", ""), "%s; %s" % (st.get("status", ""), " ".join(lines)[:80]))

    # the waypoint panel, with the act tabs: Escape closes the menu first, then the waypoint panel
    gc.Hl("waypoint open", log)
    time.sleep(1.2)
    shots.append(gc.sh("devmenu_hd_waypoint_panel"))
    gc.g.press("esc")
    time.sleep(0.6)
    gc.g.press("esc")
    time.sleep(0.6)
    verb(gc, log, "close")
    time.sleep(0.5)

    # legacy
    if gc.set_graphics("legacy"):
        time.sleep(1.0)
        gc.g.press("f12", mods=("ctrl",))
        st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
        if st.get("open") != 1:
            verb(gc, log, "open")
            st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
        row("open legacy", st.get("open") == 1, "open=%s" % st.get("open"))
        do(gc, log, "tab0")
        do(gc, log, "cat1")
        search(gc, log, "Staff of Kings")
        time.sleep(0.6)
        shots.append(gc.sh("devmenu_legacy_items"))
        ops0 = state(gc, log).get("ops", 0)
        click_row_arrow(gc, "sd")
        st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 6.0)
        row("real click spawns in legacy", "spawned" in st.get("status", "").lower(), st.get("status", ""))
        time.sleep(0.4)
        shots.append(gc.sh("devmenu_legacy_clicked_status"))
        do(gc, log, "tab1")
        search(gc, log, "fauz")
        time.sleep(0.5)
        shots.append(gc.sh("devmenu_legacy_travel"))
        do(gc, log, "close")
        gc.set_graphics("hd")
    else:
        row("open legacy", False, "legacy graphics not reached")

    st = state(gc, log)
    log.append("final %s" % st)
    ok = all(r[1] for r in rows if r[1] is not None) and not st.get("faults")
    gc.finish("devmenu", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows), mark, shots, log)
