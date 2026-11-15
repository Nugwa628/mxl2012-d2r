"""The Stat Book plugin (check `statbook` of tools/game_checks.py; statbook/, docs/statbook.md).

The plugin's own console command answers, without its layouts: `statbook` (one line per part: image, sheetres, advstats, book,
block, pad) and `statbook page <n>` (the page's lines with the client player's values, `sbline ...`). The check reads both, plays an
Amazon with a shield and set dexterity (SHORTCUT: shield worn and stats set by the harness) and compares the book's Chance to Block
with D2R's own GetBlockRate (harness `cblock`) and a few rows with the client's stat values (`stat player`). Shots: the HD sheet
with the resistance rows (`statbook_hd_sheet`) and the Advanced Stats panel (`statbook_hd_advstats`).
"""
import os
import re
import time

import advstats_checks

DEX, FIRE_RES, FCR = 2, 39, 105  # D2R's stat ids (the built mod keeps D2R's rows first)


def text(gc):
    return gc.statbook_text().splitlines()


def part(lines, word):
    return next((ln for ln in lines if ln.startswith(word + " ")), "")


def page_lines(gc, log, title):
    """The `sbline` rows of the book page whose title is `title`, as {label: value}; None when there is no such page."""
    head = text(gc)
    m = re.search(r"statbook page: 0 \.\. (\d+)", gc.g.console_text("statbook page 99", settle=1.0))
    last = int(m.group(1)) if m else 8
    for n in range(last + 1):
        out = gc.g.console_text("statbook page %d" % n, settle=1.0).splitlines()
        log.extend(out)
        if any(re.match(r"statbook page %d %s:" % (n, re.escape(title)), ln) for ln in out):
            rows = {}
            for ln in out:
                for label, value in re.findall(r"(?:\| |; )([^|;=]+?) = ([^ (;]+)", ln):
                    rows[label.strip()] = value
            return rows
    log.append("no page %r in %s" % (title, head[:3]))
    return None


def shield_code(gc):
    """A shield base of the built armor.txt (type shie)."""
    return next((r.get("code") for r in gc.table("armor") if r.get("type") == "shie" and r.get("code")), None)


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    lines = text(gc)
    log.extend("statbook: " + ln for ln in lines)
    row("plugin loaded", bool(part(lines, "statbook")), part(lines, "statbook")[:160] or "no statbook line")
    row("image", "image supported" in part(lines, "statbook"), part(lines, "statbook")[:160])
    for word in ("sheetres", "advstats", "block"):
        ln = part(lines, word)
        row("part " + word, (word + " on") in ln, ln[:200] or "no %s line" % word)
    for word in ("book", "pad"):
        ln = part(lines, word)
        row("line " + word, bool(ln), ln[:200] or "no %s line" % word)

    if gc.be_class(0):
        gc.goto(1, timeout=60)
        gc.set_graphics("hd")
        gc.close_right_panel()
        code = shield_code(gc)
        gc.H("unequip lhand")
        ok, _ = gc.Hl("equip %s lhand" % code, log) if code else (False, [])
        row("shield worn", ok, "base %s" % code)
        # a ring for the item stats (a server-only `stat ... set` of FCR never reaches the client), dexterity set
        gc.H("unequip rring")
        ok, _ = gc.Hl("equip rin %d=25 %d=37 rring" % (FCR, FIRE_RES), log)
        row("ring worn", ok, "Faster Cast Rate 25, Fire Resistance 37")
        saved = {DEX: gc.rd("player", DEX)}
        gc.setstat("player", DEX, 200)
        time.sleep(1.0)
        gc.H("state")  # the harness learns the player id for `cblock`
        _ok, cb = gc.Hl("cblock", log)
        m = re.search(r"client block game=(-?\d+)", " ".join(cb))
        game = int(m.group(1)) if m else None
        defense = page_lines(gc, log, "Defense") or {}
        book = defense.get("Chance to Block")
        row("Chance to Block = GetBlockRate", game is not None and book == "%d%%" % game, "book %s, game %s" % (book, game))
        res = page_lines(gc, log, "Resistances") or {}
        fire = next((v for k, v in res.items() if k.startswith("Fire")), None)
        client_fire = gc.rd("player", FIRE_RES)
        row("Fire Resistance row", fire is not None and fire == "%d%%" % (client_fire or 0), "row %s, client stat %s (ring 37)" % (fire, client_fire))
        spells = page_lines(gc, log, "Spells") or {}
        fcr = next((v for k, v in spells.items() if "Cast" in k), None)
        row("Faster Cast Rate row", fcr == "25%", "row %s (ring 25)" % fcr)
        offense = page_lines(gc, log, "Offense") or {}
        ias = offense.get("Attack Speed from Skills")
        row("skill speed row from 100", ias == "%+d%%" % ((gc.rd("player", 68) or 100) - 100), "row %s" % ias)
        gc.g.press("c")
        time.sleep(1.5)
        shots.append(gc.sh("statbook_hd_sheet"))
        gc.g.click(*gc.sp2_xy(*advstats_checks.HD_BUTTON))
        time.sleep(1.5)
        shots.append(gc.sh("statbook_hd_advstats"))
        gc.g.click(0.5, 0.97, move_only=True)
        advstats_checks.close_panels(gc)
        for s, v in saved.items():
            gc.setstat("player", s, v or 0)
        gc.H("unequip lhand")
        gc.H("unequip rring")
    else:
        row("Amazon", False, "could not play an Amazon")

    lines = text(gc)
    log.extend("statbook after: " + ln for ln in lines)
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else ("shots" if r[1] is None else "FAIL")) for r in rows)
    gc.finish("statbook", ok, note + "; SHORTCUT: shield worn and stats set by the harness", mark, shots, log,
              partial="sheet rows and Advanced Stats panel (shots)")


PAD_RE = re.compile(r"(?:sheet|menu) messages (\d+), actions (\d+), last (-?\d+), tab buttons (\d+), tab steps (\d+)")


def pad_counts(gc):
    """(sheet actions, last action id, tab buttons, tab steps, sheet messages) from the `pad` line of `statbook`; None without one."""
    m = PAD_RE.search(part(text(gc), "pad"))
    return tuple(int(x) for x in m.groups()[1:] + m.groups()[:1]) if m else None


def run_pad(gc):
    """Check `statbook_pad`: the scripted gamepad (harness `pad`, tools/pad_input.py) on the character sheet. With pad_log = true
    in the installed statbook.toml every action the sheet gets is in statbook.log ("sheet controller action N"): Start opens the
    menu, RB pages it until the sheet's handler gets actions, then LT, RT, LB, RB one at a time (each one's id is the `last` of
    the status). With the tab ids set in statbook.toml the status' `tab buttons` counts the presses the hook took as tab
    buttons (the sheet's own tabs are not there yet: D2R still gets them)."""
    import pad_input as pi
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("INFO" if ok is None else "FAIL"), note))

    def shot(name):
        time.sleep(0.6)
        shots.append(gc.sh("statbook_pad_" + name))

    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    log.append("pad line: " + part(text(gc), "pad"))
    p = pi.on(gc.H, log)
    row("pad polled", p.get("hooked") == 1 and p.get("polls", 0) > 0, "%s" % p)
    pi.run_script(gc.H, "start wait:2.0 b wait:1.5", log)
    gc.Hl("padui on", log)
    time.sleep(2.0)

    # the menu opens on Inventory; Character is the tab before it (Quest Log, Character, Inventory, ...): one LB
    pi.run_script(gc.H, "start wait:2.5 lb wait:2.0", log)
    shot("sheet")
    c0 = pad_counts(gc)
    log.append("sheet open: %s" % (c0,))
    ids = {}
    for b in ("lt", "rt", "up", "down", "x", "lb", "rb"):
        before = pad_counts(gc)
        pi.run_script(gc.H, b + " wait:2.0", log)
        after = pad_counts(gc)
        log.append("%s: %s -> %s" % (b, before, after))
        if before and after and after[0] > before[0]:
            ids[b] = after[1]
        if b == "lb":  # the bumpers page the menu in plain D2R: back to the sheet for the next button
            shot("after_lb")
            pi.run_script(gc.H, "rb wait:2.0", log)
    shot("after_rb")
    c = pad_counts(gc)
    row("the sheet's handler gets controller actions (the hook)", bool(ids), "status on the sheet %s, at the end %s" % (c0, c))
    row("button ids seen by the hook", None, " ".join("%s=%s" % (b.upper(), ids.get(b, "?")) for b in ("lb", "rb", "lt", "rt", "up", "down", "x")))
    final = pad_counts(gc)
    row("tab buttons matched by the configured ids", None if final is None else (final[2] > 0 if os.environ.get("SB_PAD_EXPECT") else None),
        "status %s (tab buttons = presses the hook took as tab buttons)" % (final,))
    try:
        with open(os.path.join(gc.g.GAME_DIR, r"mods\mxl2012\d2rloader\logs\statbook.log"), encoding="utf-8", errors="replace") as f:
            tail = [ln.rstrip() for ln in f if "controller action" in ln or "pad" in ln.lower()][-40:]
        log.extend("statbook.log: " + ln for ln in tail)
    except OSError as e:
        log.append("statbook.log: %s" % e)
    pi.run_script(gc.H, "b wait:1.5", log)
    pi.off(gc.H, log)
    gc.Hl("padui off", log)
    gc.close_right_panel()
    log.append("PADIDS " + " ".join("%s=%s" % (b, ids.get(b, "?")) for b in ("lb", "rb", "lt", "rt", "up", "down", "x")))
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    gc.finish("statbook_pad", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else ("info" if r[1] is None else "FAIL")) for r in rows),
              mark, shots, log, partial="the ids are D2R's controller action ids as the sheet's handler gets them")


# ---- the gamepad on the sheet host (check `statbook_host_pad`) ------------------------------------------------------------

def run_host_pad(gc):
    """Check `statbook_host_pad`: the scripted gamepad (tools/pad_input.py) on the gamepad character sheet with the sheet host
    bound. SB_PAD_SETUP=cqol: Controller QOL Updates is in the mod (the tabs on LB / RB, the menu pages on LT / RT), cqol-after:
    the same, loaded after the Stat Book (an INFO row names the load order from the loader log); else plain D2R-XL 2012 (tabs
    on LT / RT, pages on LB / RB). Next, next, previous step the host's tab (shots statbook_pad_<setup>_tab<n>), then the
    paging buttons still page D2R's menu (away and back to the sheet)."""
    import pad_input as pi
    setup = os.environ.get("SB_PAD_SETUP") or "plain"
    cqol = setup.startswith("cqol")
    prev_b, next_b = ("lb", "rb") if cqol else ("lt", "rt")
    page_l, page_r = ("lt", "rt") if cqol else ("lb", "rb")
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("INFO" if ok is None else "FAIL"), note))

    def shot(name):
        time.sleep(0.8)
        shots.append(gc.sh("statbook_pad_%s_%s" % (setup, name)))

    if cqol:
        try:
            with open(gc.g.LOADER_LOG, encoding="utf-8", errors="replace") as f:
                order = re.findall(r"\[DETAIL\]\s+([^;]+\.dll); id=", f.read())
            seen = [o for o in order if "Controller QOL" in o or o == "statbook.dll"][-2:]
        except OSError as e:
            seen = ["(loader log: %s)" % e]
        row("plugin load order", None, " then ".join(seen))
    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    log.append("pad line: " + part(text(gc), "pad"))
    p = pi.on(gc.H, log)
    row("pad polled", p.get("hooked") == 1 and p.get("polls", 0) > 0, "%s" % p)
    pi.run_script(gc.H, "stick:l:0:40 wait:0.4 stick:l:0:0 wait:2.5", log)
    gc.Hl("padui on", log)
    time.sleep(2.5)
    # the menu opens on Inventory; Character is the page before it
    pi.run_script(gc.H, "start wait:2.5 %s wait:2.5" % page_l, log)
    st = host(gc, log)
    row("bound on the gamepad sheet", st.get("bound") == 1 and st.get("layout") == "gamepad", "%s" % st)
    shot("tab%d" % st.get("tab", -1))
    seen = [st.get("tab")]
    for b in (next_b, next_b, prev_b):
        pi.run_script(gc.H, b + " wait:1.5", log)
        st = host(gc, log)
        seen.append(st.get("tab"))
        shot("tab%d_after_%s" % (st.get("tab", -1), b))
    row("%s / %s step the book's tab" % (prev_b.upper(), next_b.upper()), seen == [0, 1, 2, 1], "tabs %s" % seen)
    pad_line = part(text(gc), "pad")
    log.append("pad line after: " + pad_line)
    row("the tab buttons were taken (not paging D2R's menu)", "tab steps 3" in pad_line or bool(re.search(r"tab steps [3-9]", pad_line)), pad_line[:200])
    pi.run_script(gc.H, "%s wait:2.0" % page_r, log)
    away = host(gc, log)
    shot("paged_away")
    pi.run_script(gc.H, "%s wait:2.0" % page_l, log)
    back = host(gc, log)
    shot("paged_back")
    row("%s / %s still page D2R's menu" % (page_l.upper(), page_r.upper()),
        away.get("calib", "").endswith("sheet open 0") and back.get("calib", "").endswith("sheet open 1") and back.get("tab") == 1,
        "away: %s; back: %s" % (away.get("calib"), back))
    pi.run_script(gc.H, "b wait:1.5", log)
    pi.off(gc.H, log)
    time.sleep(1.5)
    gc.Hl("padui off", log)
    gc.close_right_panel()
    try:
        with open(os.path.join(gc.g.GAME_DIR, "mods", "mxl2012", "d2rloader", "logs", "statbook.log"), encoding="utf-8", errors="replace") as f:
            tail = [ln.rstrip() for ln in f if "controller action" in ln or "host" in ln][-30:]
        log.extend("statbook.log: " + ln for ln in tail)
    except OSError as e:
        log.append("statbook.log: %s" % e)
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    gc.finish("statbook_host_pad", ok, setup + ": " + "; ".join("%s %s" % (r[0], "ok" if r[1] else ("info" if r[1] is None else "FAIL")) for r in rows),
              mark, shots, log)


# ---- the sheet host (check `statbook_host`; docs/statbook.md "Sheet host", docs/statbook-layout.md) ----------------------------

PANEL_UNITS = (236.0, 208.4)  # the HD left panel's top left in units of a 2160-unit-high 16:9 screen (game_checks SP2_HD)
ADV_ARROW = (1108 + 35, 711 + 55)  # the Advanced Stats arrow on the HD sheet (advstats_checks.HD_BUTTON)
HOST_RE = re.compile(r"bound (\d) \((\w+)\), tab (-?\d+) of (\d+), query \"([^\"]*)\"; (.*?); ticks (\d+), opens (\d+), tab changes (\d+), "
                     r"clicks (\d+) \(missed (\d+)\), arrows (\d+), typed reads (\d+)")
HOST_KEYS = ("bound", "layout", "tab", "tabs", "query", "calib", "ticks", "opens", "changes", "clicks", "missed", "arrows", "reads")


def parse_host(out):
    """The `statbook host` status line as a dict (HOST_KEYS); {} without one."""
    m = HOST_RE.search(out)
    if not m:
        return {}
    return {k: (v if k in ("layout", "query", "calib") else int(v)) for k, v in zip(HOST_KEYS, m.groups())}


def host(gc, log=None):
    out = gc.g.console_text("statbook host", settle=1.0)
    if log is not None:
        log.extend("host: " + ln for ln in out.splitlines() if ln.startswith("host "))
    return parse_host(out)


def sheet_xy(ux, uy):
    """A point of the HD sheet (its layout units) as client fractions; the client is 16:9."""
    return (PANEL_UNITS[0] + ux) / 3840.0, (PANEL_UNITS[1] + uy) / 2160.0


def layout_rects(root):
    """statbook-layout.json's PC rectangles from the built mod (work/mod)."""
    import json
    path = os.path.join(root, "work", "mod", "data", "hd", "global", "ui", "panel", "statbook", "statbook-layout.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)["pc"]


def run_host(gc):
    """Check `statbook_host`: the Stat Book on the HD character sheet. Every tab clicked (shots statbook_<page>), All Stats with a
    typed search, the Advanced Stats arrow, an All Stats row's arrow, the sheet closed and opened again on a page, the
    group-hides-children test (`statbook vis`), the client at 1920 x 1080 and 2560 x 1440 and the legacy sheet (page 1 only)."""
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("INFO" if ok is None else "FAIL"), note))

    def shot(name, wait=0.8):
        time.sleep(wait)
        shots.append(gc.sh("statbook_" + name))

    def away():
        gc.g.click(0.97, 0.5, move_only=True)

    def click_tab(i):
        x, y, w, h = rects["tabs"][i]
        gc.g.click(*sheet_xy(x + w / 2, y + h / 2))
        time.sleep(0.6)
        away()
        return host(gc, log)

    rects = layout_rects(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gc.enable_debug()
    lines = text(gc)
    log.extend("statbook: " + ln for ln in lines)
    book = part(lines, "book")
    row("host installed", "host on" in book, book[:300])
    if not gc.be_class(0):
        row("Amazon", False, "could not play an Amazon")
    else:
        gc.goto(1, timeout=60)
        gc.set_graphics("hd")
        gc.close_right_panel()
        # a ring for item stats on the pages and in All Stats (Faster Cast Rate 25, Fire Resistance 37)
        gc.H("unequip rring")
        ok, _ = gc.Hl("equip rin %d=25 %d=37 rring" % (FCR, FIRE_RES), log)
        row("ring worn", ok, "Faster Cast Rate 25, Fire Resistance 37")
        for _ in range(3):  # a posted key is now and then lost (the first one after the loading screen)
            gc.g.press("c")
            time.sleep(1.5)
            st = host(gc, log)
            if st.get("calib", "").endswith("sheet open 1"):
                break
        row("bound on the HD sheet", st.get("bound") == 1 and st.get("tab") == 0, "%s" % st)
        shot("character")
        names = ["character", "offense", "spells", "defense", "resistances", "skills", "utility", "allstats"]
        tabs = st.get("tabs", 8)
        seen = []
        for i in list(range(1, tabs)) + [0]:
            st = click_tab(i)
            seen.append((i, st.get("tab")))
            if i:
                shot(names[i] if i < len(names) else "tab%d" % i)
        row("each tab click selects its tab", all(a == b for a, b in seen), "clicked -> tab %s" % seen)

        # the Advanced Stats arrow on the Character tab: All Stats
        gc.g.click(*sheet_xy(*ADV_ARROW))
        time.sleep(0.8)
        away()
        st = host(gc, log)
        row("the Advanced Stats arrow opens All Stats", st.get("tab") == tabs - 1 and st.get("arrows", 0) >= 1, "%s" % st)
        shot("arrow_allstats")

        # a typed search, after the core's developer menu has been open once: then two panel_shared copies (core's and the
        # Stat Book's) have subclassed the game window, and the typing must still reach the Stat Book's box once
        import devmenu_checks
        if devmenu_checks.state(gc, log).get("on") is not None:
            dm = devmenu_checks.open_menu(gc, log)
            shot("devmenu_open")
            gc.g.press("f12", mods=("ctrl",))
            time.sleep(1.0)
            row("core's developer menu opened and closed first", dm.get("open") == 1, "%s" % dm)
            if "sheet open 1" not in gc.g.console_text("statbook host", settle=0.5):
                gc.g.press("c")
                time.sleep(1.5)
        x, y, w, h = rects["search"]
        gc.g.click(*sheet_xy(x + w / 2, y + h / 2))
        time.sleep(0.5)
        devmenu_checks.type_keys(gc, "fire")
        time.sleep(1.0)
        st = host(gc, log)
        typed = st.get("query") == "fire"
        row("typing in the search box (each key once)", typed, "%s" % st)
        if not typed:
            gc.g.console_text("statbook find fire", settle=0.5)
            log.append("console find instead: %s" % host(gc, log))
        shot("allstats_search")
        # the first kept row's arrow (row 1: row 0 is the group heading): the page with that stat
        x, y, w, h = rects["allRowRects"][1]
        gc.g.click(*sheet_xy(x + w - 30, y + h / 2))
        time.sleep(0.8)
        away()
        st = host(gc, log)
        row("an All Stats row's arrow opens its page", 1 <= st.get("tab", -1) < tabs - 1, "%s" % st)
        shot("allstats_row_go")

        # closed and opened again on a page: every widget's visibility set again on the opening
        click_tab(3)
        before = host(gc, log).get("opens", 0)
        gc.g.press("c")
        time.sleep(1.0)
        gc.g.press("c")
        time.sleep(1.5)
        st = host(gc, log)
        row("opened again on its page", st.get("opens", 0) > before and st.get("tab") == 3, "opens %s -> %s, %s" % (before, st.get("opens"), st))
        shot("reopened_defense")

        # does hiding a group hide its children? StatBookPage held hidden, its lines not touched; then one heading leaf alone
        gc.g.console_text("statbook vis StatBookPage 0", settle=1.0)
        shot("vis_group_hidden")
        gc.g.console_text("statbook vis StatBookPage -1", settle=1.0)
        gc.g.console_text("statbook vis SbLine00HeadingText 0", settle=1.0)
        shot("vis_leaf_hidden")
        gc.g.console_text("statbook vis SbLine00HeadingText -1", settle=1.0)
        shot("vis_leaf_released")
        row("group-hides-children shots", None, "statbook_vis_group_hidden: StatBookPage hidden; statbook_vis_leaf_hidden: one heading text "
            "hidden; statbook_vis_leaf_released: the heading back")

        # the client at 1080p and 1440p
        old = (gc.g.CLIENT_W, gc.g.CLIENT_H)
        try:
            for w, h in ((1920, 1080), (2560, 1440)):
                gc.g.CLIENT_W, gc.g.CLIENT_H = w, h
                got = gc.g.fit_window(gc.g.need_window())
                time.sleep(2.0)
                size = (got[2] - got[0], got[3] - got[1])
                log.append("client %dx%d asked, %s got" % (w, h, size))
                click_tab(2)
                shot("spells_%dp" % h, 1.0)
                st = click_tab(tabs - 1)
                shot("allstats_%dp" % h, 1.0)
                row("tabs at %dp" % h, st.get("tab") == tabs - 1, "client %s, %s" % (size, st))
        finally:
            gc.g.CLIENT_W, gc.g.CLIENT_H = old
            gc.g.fit_window(gc.g.need_window())
            time.sleep(2.0)
        click_tab(0)
        gc.g.press("c")
        time.sleep(1.0)

        # legacy: D2R's page 1, the host not bound
        gc.set_graphics("legacy")
        gc.g.press("c")
        time.sleep(1.5)
        st = host(gc, log)
        row("legacy sheet: not bound (page 1 only)", st.get("bound") == 0, "%s" % st)
        shot("legacy_page1")
        gc.g.press("c")
        time.sleep(0.8)
        gc.set_graphics("hd")
        gc.H("unequip rring")

    lines = text(gc)
    log.extend("statbook after: " + ln for ln in lines)
    host(gc, log)
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    gc.finish("statbook_host", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else ("info" if r[1] is None else "FAIL")) for r in rows), mark, shots, log,
              partial="the pages are judged from the shots")


# ---- top / side tabs (check `statbook_side`; docs/statbook.md "Side host") ----------------------------------------------------

SIDE_LEFT = 1162.0  # the side panel's left edge in the sheet's units (statbook/SbSidePanel at x 1398 of the left panel anchor)
TABS_RE = re.compile(r"tabs (top|side) \(side (\w+), panel (\w+), opens (\d+), fails (\d+), toggles (\d+)\)")


def side_xy(ux, uy):
    """A point of the side panel (its layout units) as client fractions; the client is 16:9."""
    return sheet_xy(SIDE_LEFT + ux, uy)


def tabs_state(gc, log=None):
    """{tabs, showing, panel, opens, fails, toggles} from `statbook host`, with the host's own keys."""
    out = gc.g.console_text("statbook host", settle=1.0)
    if log is not None:
        log.extend("host: " + ln for ln in out.splitlines() if ln.startswith("host "))
    st = parse_host(out)
    m = TABS_RE.search(out)
    if m:
        st.update(mode=m.group(1), showing=m.group(2), panel=m.group(3), sopens=int(m.group(4)), sfails=int(m.group(5)),
                  toggles=int(m.group(6)))
    m = re.search(r"sheet open (\d)", out)
    if m:
        st["open"] = int(m.group(1))
    return st


def run_side(gc):
    """Check `statbook_side`: the top / side toggle on the book (both hosts, both ways, the hover tooltip), every side page,
    the side All Stats with a typed search, a row's arrow, the Advanced Stats arrow, the side tab kept over a close and reopen,
    statbook.toml written back, a switch with the sheet closed (`statbook tabs`), and the top tabs correct after switching back."""
    import json
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("INFO" if ok is None else "FAIL"), note))

    def shot(name, wait=0.8):
        time.sleep(wait)
        shots.append(gc.sh("statbook_side_" + name))

    def away():
        gc.g.click(0.97, 0.5, move_only=True)

    def click(xy, wait=0.8):
        gc.g.click(*xy)
        time.sleep(wait)
        away()
        return tabs_state(gc, log)

    def mid(r, dx=None):
        x, y, w, h = r
        return x + (w / 2 if dx is None else dx), y + h / 2

    def sheet_to(want, wait=1.5):
        """C until the sheet is open (want) or closed: a posted key is now and then lost (the first one after the
        loading screen); the state is read back after each press."""
        st = {}
        for _ in range(3):
            gc.g.press("c")
            time.sleep(wait)
            st = tabs_state(gc, log)
            if st.get("open") == (1 if want else 0):
                return st
        log.append("sheet_to(%s): still %s" % (want, st.get("open")))
        return st

    def toml_tabs():
        p = os.path.join(gc.g.GAME_DIR, "mods", "mxl2012", "d2rloader", "config", "statbook.toml")
        try:
            with open(p, encoding="utf-8") as f:
                m = re.search(r'(?m)^tabs = "(\w+)"', f.read())
            return m.group(1) if m else "(no tabs line)"
        except OSError as e:
            return "(%s)" % e

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "work", "mod", "data", "hd", "global", "ui", "panel", "statbook", "statbook-layout.json"), encoding="utf-8") as f:
        geo = json.load(f)
    pc, side = geo["pc"], geo["side"]
    names = ["character", "offense", "spells", "defense", "resistances", "skills", "utility", "allstats"]
    gc.enable_debug()
    lines = text(gc)
    log.extend("statbook: " + ln for ln in lines)
    row("host installed with the side panel", "side panel ok" in part(lines, "book") or "side panel ok" in " ".join(lines), part(lines, "book")[:300])
    if not gc.be_class(0):
        row("Amazon", False, "could not play an Amazon")
    else:
        gc.goto(1, timeout=60)
        gc.set_graphics("hd")
        gc.close_right_panel()
        gc.H("unequip rring")
        ok, _ = gc.Hl("equip rin %d=25 %d=37 rring" % (FCR, FIRE_RES), log)
        row("ring worn", ok, "Faster Cast Rate 25, Fire Resistance 37")
        log.append(gc.g.console_text("statbook tabs top", settle=1.0))
        sheet_to(True)
        time.sleep(1.5)
        tabs = tabs_state(gc, log).get("tabs", 8)

        # top tabs: the toggle on a page, its tooltip, then clicked: side
        st = click(sheet_xy(*mid(pc["tabs"][1])))
        row("top: Offense", st.get("tab") == 1 and st.get("mode") == "top", "%s" % st)
        shot("top_offense_toggle")
        gc.g.click(*sheet_xy(*mid(pc["toggle"])), move_only=True)
        shot("top_toggle_tooltip", 1.8)
        st = click(sheet_xy(*mid(pc["toggle"])), 1.5)
        row("toggle on the sheet: side, live", st.get("mode") == "side" and st.get("showing") == "showing" and st.get("panel") == "open" and st.get("tab") == 1,
            "%s" % st)
        shot("switched_top_to_side", 0.6)
        row("statbook.toml written: side", toml_tabs() == "side", toml_tabs())

        # every side page
        seen = []
        for i in range(1, tabs):
            st = click(side_xy(*mid(side["tabs"][i])))
            seen.append((i, st.get("tab")))
            shot(names[i] if i < len(names) else "tab%d" % i)
        row("each side tab click selects its tab", all(a == b for a, b in seen), "%s" % seen)

        # the Advanced Stats arrow (D2R's page 1 is shown on the sheet): All Stats
        click(side_xy(*mid(side["tabs"][1])))
        st = click(sheet_xy(*ADV_ARROW))
        row("side: the Advanced Stats arrow opens All Stats", st.get("tab") == tabs - 1, "%s" % st)
        shot("arrow_allstats")

        # search, a row's arrow
        import devmenu_checks
        gc.g.click(*side_xy(*mid(side["search"])))
        time.sleep(0.5)
        devmenu_checks.type_keys(gc, "fire")
        time.sleep(1.0)
        st = tabs_state(gc, log)
        typed = st.get("query") == "fire"
        row("side: typing in the search box", typed, "%s" % st)
        if not typed:
            gc.g.console_text("statbook find fire", settle=0.5)
        shot("allstats_search")
        x, y, w, h = side["allRowRects"][1]
        st = click(side_xy(x + w - 30, y + h / 2))
        row("side: an All Stats row's arrow opens its page", 1 <= st.get("tab", -1) < tabs - 1, "%s" % st)
        shot("allstats_row_go")

        # the side toggle's tooltip; close and reopen keeps the side tab
        st = click(side_xy(*mid(side["tabs"][3])))
        gc.g.click(*side_xy(*mid(side["toggle"])), move_only=True)
        shot("side_toggle_tooltip", 1.8)
        away()
        before = st.get("sopens", 0)
        sheet_to(False)
        time.sleep(1.2)
        closed = tabs_state(gc, log)
        shot("sheet_closed")
        sheet_to(True)
        time.sleep(1.8)
        st = tabs_state(gc, log)
        row("side: closed with the sheet", closed.get("panel") == "closed", "%s" % closed)
        row("side: reopened on its tab", st.get("tab") == 3 and st.get("sopens", 0) > before and st.get("panel") == "open", "%s" % st)
        shot("reopened_defense")

        # side -> top on the side toggle: the top tabs on the same tab, the side panel gone
        st = click(side_xy(*mid(side["toggle"])), 1.5)
        row("toggle on the side panel: top, live", st.get("mode") == "top" and st.get("showing") == "off" and st.get("panel") == "closed" and st.get("tab") == 3,
            "%s" % st)
        shot("switched_side_to_top", 0.6)
        row("statbook.toml written: top", toml_tabs() == "top", toml_tabs())
        st = click(sheet_xy(*mid(pc["tabs"][tabs - 1])))
        shot("top_after_allstats")
        st = click(sheet_xy(*mid(pc["tabs"][0])))
        row("top after switching back: Character", st.get("tab") == 0, "%s" % st)
        shot("top_after_character")
        st = click(sheet_xy(*mid(pc["tabs"][1])))
        shot("top_after_offense")

        # with the sheet closed (the Controls action's path: `statbook tabs toggle`), then live back
        sheet_to(False)
        time.sleep(1.0)
        log.append(gc.g.console_text("statbook tabs toggle", settle=1.0))
        sheet_to(True)
        time.sleep(1.8)
        st = tabs_state(gc, log)
        row("switched while closed: the sheet opens with the side panel", st.get("mode") == "side" and st.get("panel") == "open" and st.get("tab") == 1, "%s" % st)
        shot("closed_switch_side")
        log.append(gc.g.console_text("statbook tabs toggle", settle=1.5))
        st = tabs_state(gc, log)
        row("switched back live: top", st.get("mode") == "top" and st.get("panel") == "closed", "%s" % st)
        shot("live_switch_top")
        out = gc.g.console_text("statbook tabs", settle=1.0)
        row("Controls action registered", "action mxl_statbook_tabs" in out, out.strip()[-200:])
        click(sheet_xy(*mid(pc["tabs"][0])))
        sheet_to(False)
        time.sleep(0.8)
        gc.H("unequip rring")
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    gc.finish("statbook_side", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else ("info" if r[1] is None else "FAIL")) for r in rows), mark, shots, log,
              partial="the pages are judged from the shots")
