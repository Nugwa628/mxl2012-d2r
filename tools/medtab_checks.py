"""Lane medtab: the stash's MEDIAN / ORBS tabs and the Materials tab's Vanilla / Median selector (checks `medtab` and
`medtabclassic` of tools/game_checks.py; plugin part `medtab`, plugin/src/median_tabs.cpp; docs/median-stash-tab.md).

Set-up (SHORTCUT, named in the note): the items are made in the backpack by the harness (`item <code> inv`); everything else is
background clicks as a player makes them: the stash object, the tabs, the selector arrows, Ctrl-click from the backpack, a click
on a slot to take one out. An item has gone into its slot when it left the backpack with the stash open on that tab (D2R's own
Ctrl-click moves it nowhere else). The part's status (`mxl2012 medtab`) gives the tab, the selector page and its counters.

`medtab` (a RotW character, MXL_CHAR=MedStashA on slot 2): HD then legacy graphics: per new page two of one code (a stack) and
other codes, among them codes with "@" (Goodberry b@b on MEDIAN, Skinrender's Sigil l@l on the Median Materials page), a D2R
material Ctrl-clicked while the Median page shows (it goes to its Vanilla slot), a take-out from MEDIAN, shots of every tab and
page (cube on both Materials pages, none on MEDIAN / ORBS: judged on the shots); Save and Exit, back in: the pages' shots again and
the backpack still without the items. `medtabclassic` (an expansion character, MXL_CHAR=StashTab): tabs 6 and 7 hidden, no bounce
needed, shots HD and legacy.
"""
import re
import time

MEDIAN_ITEMS = ["eo7", "eo7", "b@b", "zkw", "^01", "A0+"]   # an elixir twice, Goodberry ("@"), a signet, a trophy, a full shrine
ORBS_ITEMS = ["&01", "&01", "&a1"]
MAT_MEDIAN_ITEMS = ["6o^", "6o^", "qus", "2x5", "l@l"]       # an oil twice, an arcane crystal, a brain, a sigil ("@")
MAT_VANILLA_ITEM = "rvs"                                     # a D2R material: its Vanilla slot also from the Median page
LEGACY_ITEMS = {"median": "eo9", "orbs": "&03", "materials": "3o^"}
TABS = ["personal", "shared", "gems", "materials", "runes", "median", "orbs"]
# 1600 x 900 client (probe of lane medtab, runs checks-20261106-02*): the selector's right arrow; legacy tab row and arrow
HD_SEL = (211, 646)
SD_SEL = (436, 672)
SD_TAB_Y = 106
SD_INV = (829, 405, 43.5, 43.6)  # legacy backpack grid (x, y, cell w, h), measured on medtab_legacy_median_deposited.png
HD_FIRST_SLOT = (97.95 + 0.4163 * (89 + 49), 86.8 + 0.4163 * (219 + 49))  # MEDIAN's first slot (eo7), HD


def sd_tab_x(k):
    return round(320 + 1.5 * (45 * k + 22))


def parse_status(text):
    """`mxl2012 medtab` -> {tab, live, page, updates, nomark, bounces, cube, toggles, applies, restored, on}."""
    out = {}
    m = re.search(r"medtab (on|FAILED|guard only)", text)
    if m:
        out["on"] = m.group(1)
    m = re.search(r"\| tab (-?\d+) \((live|tabs 5 / 6 hidden)\), materials (\w+)", text)
    if m:
        out.update(tab=int(m.group(1)), live=m.group(2) == "live", page=m.group(3))
    for key, pat in (("updates", r"updates (\d+)"), ("nomark", r"no layout mark (\d+)"), ("bounces", r"bounces (\d+)"),
                     ("cube", r"cube hidden (\d+)"), ("toggles", r"toggles (\d+)"), ("applies", r"applies (\d+)"),
                     ("restored", r"'@' codes restored (\d+)")):
        m = re.search(pat, text)
        if m:
            out[key] = int(m.group(1))
    return out


def status(gc, log):
    import game_ctl
    st = parse_status(game_ctl.console_text("mxl2012 medtab") or "")
    log.append("medtab status %s" % st)
    return st


def tab(gc, name):
    k = TABS.index(name)
    if gc.graphics_mode() == "legacy":
        gc.g.click(sd_tab_x(k) / 1600, SD_TAB_Y / 900)
        time.sleep(1.2)
    else:
        gc.sp2_tab(k)


def selector(gc):
    x, y = SD_SEL if gc.graphics_mode() == "legacy" else HD_SEL
    gc.g.click(x / 1600, y / 900)
    time.sleep(1.0)


def backpack_ids(gc):
    return {i["id"]: i.get("code") for i in gc.rp_items_now() if i.get("page") == 0}


def ctrl_move(gc, log, code):
    """An item made in the backpack and Ctrl-clicked: True when it left the backpack."""
    before = backpack_ids(gc)
    gc.Hl("item %s inv" % code, log)
    time.sleep(0.6)
    new = [i for i in gc.rp_items_now() if i.get("page") == 0 and i["id"] not in before]
    if not new:
        log.append("%s: not made" % code)
        return False
    it = new[0]
    grid = SD_INV if gc.graphics_mode() == "legacy" else gc.RP_INV
    gc.g.click(*gc.rp_inv_xy(it["x"], it["y"], grid), mods=("ctrl",))
    time.sleep(1.0)
    return it["id"] not in backpack_ids(gc)


def shot(gc, shots, name):
    gc.g.click(0.5, 0.97, move_only=True)
    time.sleep(0.4)
    shots.append(gc.sh("medtab_" + name))


def deposits(gc, log, codes):
    res = [(c, ctrl_move(gc, log, c)) for c in codes]
    return all(ok for _c, ok in res), res


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    gc.H("packclear")
    if not gc.sp2_open_stash(log):
        gc.finish("medtab", False, "the stash did not open", mark, shots, log)
        return
    st = status(gc, log)
    row("part on, live", st.get("on") == "on" and st.get("live") is True, "%s" % st)
    row("'@' codes restored", st.get("restored", 0) >= 9, "the 9 '@' slots read through the hook: %s" % st.get("restored"))

    # HD: Materials, both pages
    tab(gc, "materials")
    shot(gc, shots, "hd_materials_vanilla")
    st0 = status(gc, log)
    selector(gc)
    st = status(gc, log)
    shot(gc, shots, "hd_materials_median")
    row("selector", st.get("tab") == 3 and st.get("page") != st0.get("page") and st.get("toggles", 0) > st0.get("toggles", 0),
        "page %s -> %s" % (st0.get("page"), st.get("page")))
    if st.get("page") != "Median":
        selector(gc)
    ok, res = deposits(gc, log, MAT_MEDIAN_ITEMS)
    row("hd materials median deposits", ok, "%s" % res)
    ok = ctrl_move(gc, log, MAT_VANILLA_ITEM)
    shot(gc, shots, "hd_materials_median_deposited")
    row("routing: vanilla code from the Median page", ok, "%s left the backpack" % MAT_VANILLA_ITEM)
    selector(gc)
    shot(gc, shots, "hd_materials_vanilla_back")
    # MEDIAN, ORBS
    tab(gc, "median")
    st = status(gc, log)
    ok, res = deposits(gc, log, MEDIAN_ITEMS)
    shot(gc, shots, "hd_median")
    row("hd median deposits", ok and st.get("tab") == 5, "tab %s, %s" % (st.get("tab"), res))
    gc.g.click(HD_FIRST_SLOT[0] / 1600, HD_FIRST_SLOT[1] / 900)
    time.sleep(1.0)
    held = gc.held_item()
    gc.release_into_inventory(log)
    back = [c for c in backpack_ids(gc).values() if c == "eo7"]
    shot(gc, shots, "hd_median_withdrawn")
    row("hd median take-out", held is not None and held[1] == "eo7" and len(back) == 1, "held %s, backpack eo7 x%d" % (held, len(back)))
    if gc.sp2_open_stash(log):
        tab(gc, "median")
        taken = [i for i in gc.rp_items_now() if i.get("page") == 0 and i.get("code") == "eo7"]
        if taken:  # the taken one goes back by Ctrl-click
            gc.g.click(*gc.rp_inv_xy(taken[0]["x"], taken[0]["y"]), mods=("ctrl",))
            time.sleep(1.0)
        left = [c for c in backpack_ids(gc).values() if c == "eo7"]
        row("hd median put back", bool(taken) and not left, "eo7 in the backpack after the Ctrl-click: %d" % len(left))
    tab(gc, "orbs")
    st = status(gc, log)
    ok, res = deposits(gc, log, ORBS_ITEMS)
    shot(gc, shots, "hd_orbs")
    row("hd orbs deposits", ok and st.get("tab") == 6, "tab %s, %s" % (st.get("tab"), res))
    for t in ("runes", "gems"):
        tab(gc, t)
        shot(gc, shots, "hd_" + t)
    st = status(gc, log)
    row("cube hidden on 6 / 7", st.get("cube", 0) > 0, "cube hidden %s (judged on the shots too)" % st.get("cube"))

    # legacy graphics, switched with the stash open (the stash object click is placed for HD)
    if gc.set_graphics("legacy"):  # the panel test of right_panel_open is for HD: the status line judges the tabs
        time.sleep(1.0)
        for name, code in LEGACY_ITEMS.items():
            tab(gc, name)
            if name == "materials":
                selector(gc)
            shot(gc, shots, "legacy_%s" % name)
            ok = ctrl_move(gc, log, code)
            shot(gc, shots, "legacy_%s_deposited" % name)
            st = status(gc, log)
            row("legacy %s deposit" % name, ok and st.get("tab") == TABS.index(name), "%s, tab %s" % (code, st.get("tab")))
            if name == "materials":
                selector(gc)
        gc.close_right_panel()
    else:
        row("legacy", False, "legacy graphics or the stash not reached")
    gc.set_graphics("hd")

    # Save and Exit, back in
    gc.close_right_panel()
    if gc.leave_and_reenter():
        time.sleep(3)
        if gc.sp2_open_stash(log):
            tab(gc, "materials")
            shot(gc, shots, "reload_materials_vanilla")
            selector(gc)
            shot(gc, shots, "reload_materials_median")
            selector(gc)
            for t in ("median", "orbs"):
                tab(gc, t)
                shot(gc, shots, "reload_" + t)
        left = sorted(c for c in backpack_ids(gc).values() if c in set(MEDIAN_ITEMS + ORBS_ITEMS + MAT_MEDIAN_ITEMS) | set(LEGACY_ITEMS.values()))
        row("reload", not left, "deposited codes in the backpack after the reload: %s (stacks: shots and the .d2i)" % left)
    else:
        row("reload", False, "Save and Exit did not leave the game")
    gc.close_right_panel()
    gc.H("packclear")
    st = status(gc, log)
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
    gc.finish("medtab", ok, note + "; SHORTCUT: items made by the harness", mark, shots, log)


def run_classic(gc):
    """An expansion character: tabs 6 and 7 hidden in HD and legacy, nothing bounced back."""
    mark = gc.engine_mark()
    log, shots, rows = [], [], []
    gc.goto(1, timeout=60)
    for mode in ("hd", "legacy"):  # legacy switched with the stash open (the stash object click is placed for HD)
        if not gc.set_graphics(mode) or (mode == "hd" and not gc.sp2_open_stash(log)):
            rows.append((mode, False, "%s graphics or the stash not reached" % mode))
            continue
        time.sleep(1.0)
        shot(gc, shots, "classic_%s" % mode)
        st = status(gc, log)
        rows.append(("%s tabs hidden" % mode, st.get("live") is False and st.get("tab") in (0, 1), "%s" % st))
    gc.close_right_panel()
    gc.set_graphics("hd")
    st = status(gc, log)
    rows.append(("no bounce", st.get("bounces", 1) == 0, "bounces %s (a hidden tab cannot be clicked)" % st.get("bounces")))
    for r in rows:
        log.append("ROW %s %s: %s" % (r[0], "PASS" if r[1] else "FAIL", r[2]))
    gc.finish("medtabclassic", all(r[1] for r in rows), "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
              + "; the hidden tabs judged on the shots", mark, shots, log)
