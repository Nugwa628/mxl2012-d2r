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
        s = re.search(r"devmenu sockets (.*)$", ln)  # its own line: the harness keeps 400 characters a line
        if s:
            out.update({k: int(v, 0) for k, v in re.findall(r"(\w+)=(0x[0-9a-fA-F]+|-?\d+)\b", s.group(1))})
            continue
        m = re.search(r"devmenu (on=.*)$", ln)
        if m:
            out.update({k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)\b", m.group(1))})
            s = re.search(r'status="(.*)"', m.group(1))
            out["status"] = s.group(1) if s else ""
            k = re.search(r"rowkinds=(\S+)", m.group(1))
            out["rowkinds"] = k.group(1) if k and k.group(1) != "-" else ""
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


def row_of(st, kind):
    """The first shown row of a kind (I item, H heading, U uber level, A area), as the plugin reports it; -1 when none."""
    return st.get("rowkinds", "").find(kind)


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


def click_input(gc, mode):
    """A real (posted) mouse click on the search / level box, at the position the layout puts it."""
    built = devmenu_layout.layout(mode)
    m = built["metrics"]
    rect = next(c for c in built["root"]["children"] if c["name"] == devmenu_layout.INPUT)["fields"]["rect"]
    l, t, r, b = gc.g.client_rect(gc.g.need_window())
    width, height = r - l, b - t
    scale = height / 2160.0 if mode == "hd" else min(height / 600.0, width / 800.0)
    x = width / 2.0 + (m["panelX"] + rect["x"] + rect["width"] / 2.0) * scale
    y = height / 2.0 + (m["panelY"] + rect["y"] + rect["height"] / 2.0) * scale
    gc.g.click(x / width, y / height)


def click_tab(gc, mode, index):
    """A real (posted) mouse click on a tab button, a little inside its top left corner."""
    built = devmenu_layout.layout(mode)
    m = built["metrics"]
    rect = next(c for c in built["root"]["children"] if c["name"] == "Btn_tab%d" % index)["fields"]["rect"]
    l, t, r, b = gc.g.client_rect(gc.g.need_window())
    width, height = r - l, b - t
    scale = height / 2160.0 if mode == "hd" else min(height / 600.0, width / 800.0)
    x = width / 2.0 + (m["panelX"] + rect["x"] + (90 if mode == "hd" else 50)) * scale
    y = height / 2.0 + (m["panelY"] + rect["y"] + (20 if mode == "hd" else 12)) * scale
    gc.g.click(x / width, y / height)


def click_empty_panel(gc, mode):
    """A click on an empty part of the menu (under the status lines): the text box loses the keyboard."""
    m = devmenu_layout.layout(mode)["metrics"]
    l, t, r, b = gc.g.client_rect(gc.g.need_window())
    width, height = r - l, b - t
    scale = height / 2160.0 if mode == "hd" else min(height / 600.0, width / 800.0)
    x = width / 2.0 + (m["panelX"] + m["panelW"] * 0.5) * scale
    y = height / 2.0 + (m["panelY"] + m["panelH"] - 12) * scale
    gc.g.click(x / width, y / height)


def strips(gc, mode):
    """The game picture left and right of the menu, where a panel opened by a hotkey (character on the left, inventory on the right) shows
    (1600 x 900: the HD menu spans x 426 to 1174; the classic one 230 to 1370 inside the 800 x 600 picture at x 200 to 1400)."""
    boxes = {"hd": ((40, 120, 400, 760), (1200, 120, 1560, 760)), "sd": ((204, 100, 226, 800), (1374, 100, 1396, 800))}[mode]
    grabbed = gc.g.grab_client(gc.g.need_window()).convert("RGB")
    return [grabbed.crop(box) for box in boxes]


def changed(before, after):
    """True when a side strip changed like a panel appearing (not town animation): mean per-channel difference."""
    from PIL import ImageChops, ImageStat
    return any(max(ImageStat.Stat(ImageChops.difference(a, b)).mean) > 12.0 for a, b in zip(before, after))


def _query(gc, log):
    m = re.search(r'query="(.*?)" status=', " ".join(gc.Hl("devmenu state", log)[1]))
    return m.group(1) if m else None


def clear_box(gc, log):
    """Backspace (real key messages) until the focused box is empty. The shown query follows the box a tick later (and after `devmenu box` it can
    still be the harness search), so the first round always clears more than the longest query the checks type, and empty must be read twice.
    The click that focused the box put the caret where it landed, so the caret first goes to the end (Right arrow, an editing key)."""
    presses, empty = 32, 0
    for _ in range(6):
        for _ in range(presses):
            gc.g.press("right", hold=0.02)
        for _ in range(presses):
            gc.g.press("backspace", hold=0.02)
        time.sleep(0.5)
        left = _query(gc, log) or ""
        empty = empty + 1 if not left else 0
        if empty >= 2:
            return
        presses = len(left) + 2


def type_keys(gc, text):
    """Types the way a keyboard does: only key down / key up for a character the key makes by itself (letters, digits, space, punctuation), as
    the game's message loop turns each key down into its character (TranslateMessage). game_ctl.type_text also posts the character, a second
    copy that lands out of order when a frame is slow. A shifted character still needs its posted character: posted Shift is not in the
    thread's keyboard state that TranslateMessage reads."""
    for ch in text:
        if ch == " ":
            gc.g.press("space")
        elif ch in gc.g.VK and not ch.isupper():
            gc.g.press(ch)
        else:
            gc.g.type_text(ch)


def typed(gc, log, text):
    """Types with real key messages into the focused box; returns what the box then holds."""
    type_keys(gc, text)
    t0 = time.time()
    got = _query(gc, log)
    while got != text and time.time() - t0 < 2.0:
        time.sleep(0.25)
        got = _query(gc, log)
    return got, None


def open_menu(gc, log):
    gc.g.press("f12", mods=("ctrl",))
    st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
    if st.get("open") != 1:
        log.append("Ctrl+F12 did not reach the plugin; `devmenu open`")
        verb(gc, log, "open")
        st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
    time.sleep(0.8)
    return st


CORNERSTONE_GHOST_ARROW = 1803  # uniqueitems record of "Cornerstone of the World" with oskill Ghost Arrow (work/mod catalog.tsv)


def cornerstone(gc, log, row, shots):
    """Items tab, typed into the focused box: "cornerstone" lists one row per skill, a skill name finds its row, the row spawns that exact jewel;
    the jewel's tooltip in the inventory shows the skill."""
    do(gc, log, "tab0")
    do(gc, log, "cat0")
    click_input(gc, "hd")
    time.sleep(0.4)
    clear_box(gc, log)
    got, _ = typed(gc, log, "cornerstone")
    time.sleep(0.4)
    st = state(gc, log)
    row("cornerstone lists rows by skill", got == "cornerstone" and st.get("rows", 0) >= 12, "query=%r rows=%s" % (got, st.get("rows")))
    shots.append(gc.sh("devmenu_cornerstone_list"))
    clear_box(gc, log)
    got, _ = typed(gc, log, "ghost arrow")
    time.sleep(0.4)
    st = state(gc, log)
    row("skill name finds the cornerstone", got == "ghost arrow" and st.get("rows", 0) >= 1, "query=%r rows=%s" % (got, st.get("rows")))
    clear_box(gc, log)
    got, _ = typed(gc, log, "cornerstone ghost arrow")
    time.sleep(0.4)
    shots.append(gc.sh("devmenu_cornerstone_ghost_arrow"))
    ops0 = state(gc, log).get("ops", 0)
    do(gc, log, "row0")
    st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 6.0)
    items = [i for i in gc.rc_items(log) if i.get("code") == "jew" and i.get("quality") == 7 and i.get("page") == gc.RC_PAGE_INV]
    jewel = next((i for i in items if i.get("index") == CORNERSTONE_GHOST_ARROW), None)
    row("cornerstone Ghost Arrow spawned", "Ghost Arrow" in st.get("status", "") and jewel is not None,
        "%s; jewels %s" % (st.get("status", ""), [(i.get("index"), i.get("x"), i.get("y")) for i in items]))
    if jewel is not None:
        verb(gc, log, "close")
        wait(gc, log, lambda x: x.get("open") == 0, 3.0)
        time.sleep(0.5)
        gc.rc_open_inventory()
        px, py = gc.inv_px(jewel["x"], jewel["y"])
        gc.hover_px(px, py)
        shots.append(gc.sh("devmenu_cornerstone_tooltip"))
        gc.g.click(0.5, 0.05, move_only=True)
        gc.close_right_panel()
        time.sleep(0.6)
        open_menu(gc, log)


UBER_WARPS = (("fauztinville", 55, "Stony Tomb Level 1", "entrance"), ("toraja", 111, "Frigid Highlands", "red portal"))


def player_area(gc, log):
    _ok, lines = gc.Hl("state", log)
    m = re.search(r"area=(\d+)", " ".join(lines))
    return int(m.group(1)) if m else None


def uber_warps(gc, log, row, shots):
    """Travel tab: "uber" lists the uber levels under their heading; an uber level's row puts the player in the area right before it
    (Fauztinville: Stony Tomb Level 1; Welcome to Toraja: Frigid Highlands, its red portal), never inside."""
    open_menu(gc, log)
    do(gc, log, "tab1")
    search(gc, log, "uber")
    time.sleep(0.4)
    st = state(gc, log)
    kinds = st.get("rowkinds", "")
    row("uber levels listed under their heading", kinds.startswith("H") and kinds.count("U") == len(kinds) - 1 and len(kinds) >= 9,
        "rowkinds=%s" % kinds)
    shots.append(gc.sh("devmenu_uber_list"))
    for query, entry, name, what in UBER_WARPS:
        if state(gc, log).get("open") != 1:
            open_menu(gc, log)
            do(gc, log, "tab1")
        search(gc, log, query)
        time.sleep(0.4)
        st = state(gc, log)
        index = row_of(st, "U")
        shots.append(gc.sh("devmenu_uber_%s_row" % query))
        ops0 = st.get("ops", 0)
        do(gc, log, "row%d" % max(index, 0))
        st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 30.0)
        area = player_area(gc, log)
        row("uber warp %s: lands in %s" % (query, name), index > 0 and area == entry and "right before" in st.get("status", "") and what in st.get("status", ""),
            "row %d; area %s; %s" % (index, area, st.get("status", "")))
        verb(gc, log, "close")
        wait(gc, log, lambda x: x.get("open") == 0, 3.0)
        time.sleep(7.0)  # the server reports the area before the client's loading screen is gone (act 5)
        shots.append(gc.sh("devmenu_uber_%s_landed" % query))


def _catalog_picks():
    """From the built catalog: a normal weapon and armour with their maximum sockets (4 or more) and an item without sockets (a ring), each a
    name that the menu's search finds alone in its category."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "work" / "mod" / "data"
    lines = [ln.split("\t") for ln in (root / "mxl2012-devmenu" / "catalog.tsv").read_text("utf-8").splitlines() if ln.startswith("I\t")]

    def codes(name):
        rows = (root / "global" / "excel" / (name + ".txt")).read_text("utf-8-sig", errors="replace").splitlines()
        col = rows[0].split("\t").index("code")
        return {r.split("\t")[col] for r in rows[1:] if r.count("\t") >= col}

    weapons, armor = codes("weapons"), codes("armor")

    def alone(cat, name):
        words = name.lower().split()
        return sum(1 for f in lines if f[1] == cat and all(w in f[6].lower() for w in words)) == 1

    def pick(cat, test):
        return next(((f[6], f[2], int(f[5]), {"B": "cat5", "Q": "cat4"}[cat]) for f in lines if f[1] == cat and test(f) and alone(cat, f[6])), None)

    return (pick("B", lambda f: f[2] in weapons and int(f[5]) >= 4), pick("B", lambda f: f[2] in armor and int(f[5]) >= 4),
            pick("Q", lambda f: f[2] in ("amu", "rin") and f[5] == "0") or pick("Q", lambda f: f[2] in weapons | armor and f[5] == "0")
            or pick("B", lambda f: f[5] == "0"))


def socketed_items(gc, log, row, shots):
    """A weapon and an armour come with their maximum sockets, a ring with none; their tooltips are screenshotted in the inventory."""
    picks = _catalog_picks()
    log.append("socket picks %s" % (picks,))
    spawned = []
    for label, pick in (("weapon", picks[0]), ("armour", picks[1]), ("unsocketable", picks[2])):
        if pick is None:
            row("sockets " + label, False, "no catalog row to pick")
            continue
        name, code, want, cat = pick
        do(gc, log, "tab0")
        do(gc, log, cat)
        search(gc, log, name)
        before = {i["id"] for i in gc.rc_items(log)}
        ops0 = state(gc, log).get("ops", 0)
        do(gc, log, "row0")
        st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 6.0)
        new = [i for i in gc.rc_items(log) if i["id"] not in before and i.get("code") == code and i.get("page") == gc.RC_PAGE_INV]
        got = new[0].get("sockets") if new else None
        flags = new[0].get("flags", 0) if new else 0
        # real sockets: the count and D2's socketed flag (0x800, what "Socketed (N)" and putting a gem in need); identified like any base
        real = want == 0 or (flags & SOCKETED_FLAG) != 0
        row("sockets %s: %s" % (label, name), new != [] and got == want and real and new[0].get("identified") == 1 and not st.get("sockfails"),
            "want %d, item sockets %s, flags 0x%x, identified %s, sockfails %s; %s" % (
                want, got, flags, new[0].get("identified") if new else None, st.get("sockfails"), st.get("status", "")))
        if new:
            spawned.append((label, new[0]))
    verb(gc, log, "close")
    wait(gc, log, lambda x: x.get("open") == 0, 3.0)
    time.sleep(0.5)
    gc.rc_open_inventory()
    for label, item in spawned:
        px, py = gc.inv_px(item["x"], item["y"])
        gc.hover_px(px, py)
        shots.append(gc.sh("devmenu_sockets_%s_tooltip" % label))
    gc.g.click(0.5, 0.05, move_only=True)
    weapon = next((it for label, it in spawned if label == "weapon"), None)
    if weapon is not None:
        insert_gem(gc, log, row, shots, weapon)
    gc.close_right_panel()
    time.sleep(0.6)
    open_menu(gc, log)


SOCKETED_FLAG = 0x800
GEM = "gsv"  # Amethyst (misc.txt, type gema)


def insert_gem(gc, log, row, shots, weapon):
    """A gem clicked onto the spawned weapon as a player does: it goes into a socket (it leaves the backpack, the weapon stays), and the
    weapon's tooltip shows the gem."""
    _ok, lines = gc.Hl("item %s inv" % GEM, log)
    made = gc.parse_items(lines)
    if not made:
        row("gem into a spawned socket", False, "no gem made (`item %s inv`)" % GEM)
        return
    gem = next((i for i in gc.rc_items(log) if i["id"] == made[0]["id"]), made[0])
    gc.rc_insert(gem, weapon, log)
    time.sleep(0.8)
    after = gc.rc_items(log)
    gone = all(i["id"] != gem["id"] for i in after)
    still = next((i for i in after if i["id"] == weapon["id"]), None)
    held = gc.held_item()
    row("gem into a spawned socket", gone and still is not None and held is None,
        "gem id %d %s; weapon %s; cursor %s" % (gem["id"], "gone from the backpack" if gone else "still in the backpack", still, held))
    gc.rc_open_inventory()
    px, py = gc.inv_px(weapon["x"], weapon["y"])
    gc.hover_px(px, py)
    shots.append(gc.sh("devmenu_sockets_weapon_gem_tooltip"))
    gc.g.click(0.5, 0.05, move_only=True)


def run_typing(gc):
    """Real key messages into the search / level box, HD and legacy: bound keys type instead of running their commands, Esc and Ctrl+F12 still
    close the menu, the keys work as before without the box's focus and with the menu closed, and a typed level is applied."""
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    gc.goto(1, timeout=60)
    target = {"hd": 60, "sd": 70}
    for mode, graphics in (("hd", "hd"), ("sd", "legacy")):
        if not gc.set_graphics(graphics):
            row(mode + " graphics", False, "not reached")
            continue
        time.sleep(1.5)
        st = open_menu(gc, log)
        row(mode + " open", st.get("open") == 1, "open=%s" % st.get("open"))
        verb(gc, log, "box")
        time.sleep(0.4)
        shots.append(gc.sh("devmenu_type_%s_layout" % mode))

        # not focused: the key is the game's
        base = strips(gc, mode)
        gc.g.press("i")
        time.sleep(1.0)
        after = strips(gc, mode)
        row(mode + " unfocused: i opens the inventory", changed(base, after) and _query(gc, log) == "", "changed=%s query=%r" % (changed(base, after), _query(gc, log)))
        shots.append(gc.sh("devmenu_type_%s_unfocused_i" % mode))
        gc.g.press("i")
        time.sleep(1.0)

        # the box: every bound key types, nothing fires
        click_input(gc, mode)
        time.sleep(0.5)
        st = state(gc, log)
        row(mode + " one click gives the box the keyboard", st.get("boxfocus") == 1 and st.get("boxclicked") == 1,
            "boxfocus=%s boxclicked=%s" % (st.get("boxfocus"), st.get("boxclicked")))
        base = strips(gc, mode)
        for text, name in (("a", "a"), ("A", "A"), ("75", "digits"), ("staff", "word"), ("ictqmw1234", "bound keys")):
            clear_box(gc, log)
            got, _ = typed(gc, log, text)
            after = strips(gc, mode)
            fired = changed(base, after)
            st = state(gc, log)
            row("%s types %s" % (mode, name), got == text and not fired, "query=%r fired=%s keysheld=%s keystaken=%s" % (got, fired, st.get("keysheld"), st.get("keystaken")))
            if name in ("a", "digits", "word", "bound keys"):
                shots.append(gc.sh("devmenu_type_%s_%s" % (mode, name.replace(" ", "_"))))
        clear_box(gc, log)

        # Backspace and Enter edit in the box; Enter does not open the chat line
        type_keys(gc, "ab")
        gc.g.press("backspace")
        time.sleep(0.4)
        gc.g.press("enter")
        time.sleep(0.6)
        got = _query(gc, log)
        row(mode + " Backspace and Enter stay in the box", got == "a", "query=%r" % got)
        shots.append(gc.sh("devmenu_type_%s_enter" % mode))
        clear_box(gc, log)

        # a click on a tab button: the box lets go of the keyboard and the keys are the game's again
        click_tab(gc, mode, 0)
        time.sleep(0.6)
        st = state(gc, log)
        log.append("after a tab click: boxfocus=%s boxclicked=%s" % (st.get("boxfocus"), st.get("boxclicked")))
        base = strips(gc, mode)
        gc.g.press("i")
        time.sleep(1.0)
        after = strips(gc, mode)
        st = state(gc, log)
        row(mode + " click on a tab: i opens the inventory", changed(base, after) and _query(gc, log) == "",
            "changed=%s boxfocus=%s query=%r" % (changed(base, after), st.get("boxfocus"), _query(gc, log)))
        shots.append(gc.sh("devmenu_type_%s_clicked_out_i" % mode))
        gc.g.press("i")
        time.sleep(1.0)

        if mode == "hd":
            cornerstone(gc, log, row, shots)
            socketed_items(gc, log, row, shots)
            verb(gc, log, "box")
            click_input(gc, mode)
            time.sleep(0.4)
            clear_box(gc, log)

        # a typed level, applied
        do(gc, log, "tab2")
        time.sleep(0.3)
        click_input(gc, mode)
        time.sleep(0.4)
        text = str(target[mode])
        got, _ = typed(gc, log, text)
        shots.append(gc.sh("devmenu_type_%s_level_typed" % mode))
        ops0 = state(gc, log).get("ops", 0)
        do(gc, log, "raise")
        st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 6.0)
        _ok, statline = gc.Hl("state", log)
        level = re.search(r"level=(\d+)", " ".join(statline))
        row(mode + " typed level applied", got == text and "level %s" % text in st.get("status", "") and level is not None and level.group(1) == text,
            "typed=%r %s %s" % (got, st.get("status", ""), level.group(0) if level else "?"))
        shots.append(gc.sh("devmenu_type_%s_level_applied" % mode))
        do(gc, log, "tab0")

        # Esc and Ctrl+F12 from the focused box
        click_input(gc, mode)
        time.sleep(0.4)
        gc.g.press("esc")
        st = wait(gc, log, lambda x: x.get("open") == 0, 3.0)
        row(mode + " Esc closes from the box", st.get("open") == 0, "open=%s" % st.get("open"))
        if st.get("open") != 0:
            verb(gc, log, "close")
            wait(gc, log, lambda x: x.get("open") == 0, 3.0)
        time.sleep(0.6)
        open_menu(gc, log)
        click_input(gc, mode)
        time.sleep(0.4)
        gc.g.press("f12", mods=("ctrl",))
        st = wait(gc, log, lambda x: x.get("open") == 0, 3.0)
        row(mode + " Ctrl+F12 closes from the box", st.get("open") == 0, "open=%s" % st.get("open"))
        if st.get("open") != 0:
            verb(gc, log, "close")
            wait(gc, log, lambda x: x.get("open") == 0, 3.0)
        time.sleep(0.8)

        # closed menu: keybinds as before
        base = strips(gc, mode)
        gc.g.press("i")
        time.sleep(1.0)
        after = strips(gc, mode)
        row(mode + " closed menu: i opens the inventory", changed(base, after), "changed=%s" % changed(base, after))
        shots.append(gc.sh("devmenu_type_%s_closed_i" % mode))
        gc.g.press("i")
        time.sleep(0.8)

    gc.set_graphics("hd")
    uber_warps(gc, log, row, shots)
    st = state(gc, log)
    log.append("final %s" % st)
    ok = all(r[1] for r in rows if r[1] is not None) and not st.get("faults")
    gc.finish("devmenutype", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows), mark, shots, log)


LOOK_SIZES = ((1600, 900), (1280, 720))


def run_look(gc):
    """The panel at 1600 x 900 and 1280 x 720 (the window's client size), HD and legacy: each tab, the Items tab with a Cornerstone search, the
    Travel tab with the uber list, and the Quests tab armed (Confirm shown, not pressed). Screenshots `devmenu_look_<w>_<mode>_<view>`, judged by
    eye; the rows check that the menu opened, that each tab and search took and that a long row is shown whole (rowChars)."""
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.goto(1, timeout=60)
    h = gc.g.need_window()
    try:
        for w, hgt in LOOK_SIZES:
            gc.g.CLIENT_W, gc.g.CLIENT_H = w, hgt
            r = gc.g.fit_window(h)
            time.sleep(2.0)
            row("%dx%d window" % (w, hgt), (r[2] - r[0], r[3] - r[1]) == (w, hgt), "client rect %s" % (r,))
            for mode, graphics in (("hd", "hd"), ("sd", "legacy")):
                if not gc.set_graphics(graphics):
                    row("%d %s graphics" % (w, mode), False, "not reached")
                    continue
                time.sleep(1.5)
                st = open_menu(gc, log)
                tag = "%d_%s" % (w, mode)
                row(tag + " open", st.get("open") == 1, "open=%s" % st.get("open"))
                for tab, view in enumerate(("items", "travel", "character", "unlocks", "quests")):
                    do(gc, log, "tab%d" % tab)
                    search(gc, log, "")
                    if tab == 0:
                        do(gc, log, "cat0")
                    if tab == 4:
                        do(gc, log, "quests")
                    time.sleep(0.6)
                    st = state(gc, log)
                    row("%s %s" % (tag, view), st.get("tab") == tab, "tab=%s rows=%s status=%r" % (st.get("tab"), st.get("rows"), st.get("status")))
                    shots.append(gc.sh("devmenu_look_%s_%s" % (tag, view)))
                do(gc, log, "tab0")
                do(gc, log, "cat0")
                search(gc, log, "cornerstone")
                time.sleep(0.6)
                st = state(gc, log)
                row(tag + " cornerstone search", st.get("rows", 0) >= 8, "rows=%s" % st.get("rows"))
                shots.append(gc.sh("devmenu_look_%s_cornerstone" % tag))
                do(gc, log, "tab1")
                search(gc, log, "uber")
                time.sleep(0.6)
                st = state(gc, log)
                row(tag + " uber list", st.get("rowkinds", "").startswith("HU"), "rowkinds=%s" % st.get("rowkinds"))
                shots.append(gc.sh("devmenu_look_%s_uber" % tag))
                search(gc, log, "")
                do(gc, log, "tab0")
                verb(gc, log, "close")
                wait(gc, log, lambda x: x.get("open") == 0, 3.0)
                time.sleep(0.5)
    finally:
        gc.g.CLIENT_W, gc.g.CLIENT_H = 1600, 900
        gc.g.fit_window(h)
        time.sleep(1.0)
        gc.set_graphics("hd")
    st = state(gc, log)
    log.append("final %s" % st)
    ok = all(r[1] for r in rows if r[1] is not None) and not st.get("faults")
    gc.finish("devmenulook", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows), mark, shots, log)


def run_uber(gc):
    """The uber warps alone (a new character raised to 60 first): `uber_warps`."""
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    open_menu(gc, log)
    do(gc, log, "tab2")
    search(gc, log, "60")
    do(gc, log, "raise")
    time.sleep(1.0)
    verb(gc, log, "close")
    time.sleep(0.5)
    with gc.Tank():  # the entry areas have monsters next to the arrival spot, and the check waits there for the screenshot
        uber_warps(gc, log, row, shots)
    st = state(gc, log)
    log.append("final %s" % st)
    ok = all(r[1] for r in rows if r[1] is not None) and not st.get("faults")
    gc.finish("devmenuuber", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows), mark, shots, log)


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
    st = state(gc, log)
    ops0 = st.get("ops", 0)
    click_row_arrow(gc, "hd", max(row_of(st, "A"), 0))  # the area itself, below the uber level's row
    st = wait(gc, log, lambda x: x.get("busy") == 0 and x.get("ops", 0) > ops0, 20.0)
    row("travel Fauztinville", "arrived" in st.get("status", "").lower() and "Fauztinville" in st.get("status", ""), st.get("status", ""))
    time.sleep(1.5)
    shots.append(gc.sh("devmenu_hd_fauztinville"))
    search(gc, log, "toraja")
    st = state(gc, log)
    ops0 = st.get("ops", 0)
    do(gc, log, "row%d" % max(row_of(st, "A"), 0))
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
