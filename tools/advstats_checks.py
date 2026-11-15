"""The character sheet's Advanced Stats panel (check `advstats` of tools/game_checks.py; data: itemstatcost `advdisplay`, set by
tools/txt_migrate.py advanced_stats from data/advanced_stats.tsv).

Set-up (SHORTCUT, named in the note): the worn items are made and worn by the harness (`equip`), a copy of the first ring is made in
the backpack (`item ... inv`); the panels are opened as a player does: C, a background click on the sheet's Advanced Stats
button, G for legacy graphics, I and a hover over the ring copy for its tooltip. Shots: `advstats_hd_sheet`, `advstats_hd_panel`,
`advstats_hd_panel_down` (the list scrolled), `advstats_legacy_*`, `advstats_hd_tooltip`. The log holds the client's value of
every stat worn (`stat player`), to compare with the panel's rows and the tooltip on the shots.
"""
import re
import time

# Worn items: (body location, base code, stats). Median stat names of the built itemstatcost, sent as their row ids (older
# harness builds read ids only; up to 8 stats an item).
GEAR = [("rring", "rin", [("item_fastercastrate", 20), ("item_magicbonus", 50), ("item_goldbonus", 100),
                          ("item_fastergethitrate", 30), ("lifedrainmindam", 8), ("item_fasterattackrate", 15)]),
        ("lring", "rin", [("fireresist", 30), ("maxfireresist", 5), ("passive_fire_mastery", 15), ("item_strength_percent", 10),
                          ("item_absorbfire_percent", 10), ("item_attackertakesfiredamage", 25), ("skill_minion_dmg_percent", 20),
                          ("item_find_magic_perlevel", 8)]),  # folded into MF (stat 80): no row of its own
        ("neck", "amu", [("passive_fire_pierce", 12), ("item_crushingblow", 10), ("item_deadlystrike", 15),
                         ("item_reducedprices", 5), ("item_lightradius", 2), ("item_cannotbefrozen", 1), ("item_healafterkill", 3),
                         ("item_fastermovevelocity", 20)])]
# The sheet's Advanced Stats button (D2R's characterstatspanelhd.json: ButtonWidget AdvancedStats at 1108,711, the sprite about
# 70 x 110) and the panel's scroll bar (advancedstatspanelhd.json ScrollBar 765,160 36 x 1233; the panel sits 1162 to the right of
# the sheet, both on $LeftPanelAnchor), in the sheet's layout units; game_checks.sp2_xy maps a left panel's units to the client.
HD_BUTTON = (1108 + 35, 711 + 55)
HD_SCROLL_LOW = (1162 + 765 + 18, 160 + 1150)


def stat_ids(gc):
    """Stat name -> row of the slot's built itemstatcost."""
    import os
    p = os.path.join(gc.EXCEL, "itemstatcost.txt")
    with open(p, encoding="utf-8", errors="replace") as f:
        names = [line.split("\t", 1)[0] for line in f.read().splitlines()[1:]]
    return {n: i for i, n in enumerate(names)}


def args(ids, stats):
    return " ".join("%d=%d" % (ids[name], v) for name, v in stats)


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
    ids = stat_ids(gc)
    worn = []
    for loc, code, stats in GEAR:
        gc.H("unequip %s" % loc)
        ok, _ = gc.Hl("equip %s %s %s" % (code, args(ids, stats), loc), log)
        worn.append(ok)
    row("gear worn", all(worn), "%s" % worn)
    loc, code, stats = GEAR[0]
    _ok, made = gc.Hl("item %s %s inv" % (code, args(ids, stats)), log)
    spot = next((gc.kv(ln) for ln in made if ln.lstrip().startswith("item id=") and "page=0" in ln), None)
    gc.H("state")
    for _loc, _code, stats in GEAR:
        for name, _v in stats:
            gc.Hl("stat player %d" % ids[name], log)
    gc.Hl("stat player 12", log)  # character level, for the per-level rows
    for sid in (79, 80, 239, 240):
        gc.Hl("stat player %d" % sid, log)

    gc.g.press("c")
    time.sleep(1.5)
    shots.append(gc.sh("advstats_hd_sheet"))
    gc.g.click(*gc.sp2_xy(*HD_BUTTON))
    time.sleep(1.5)
    shots.append(gc.sh("advstats_hd_panel"))
    gc.g.click(*gc.sp2_xy(*HD_SCROLL_LOW))
    time.sleep(1.0)
    gc.g.click(*gc.sp2_xy(*HD_SCROLL_LOW))
    time.sleep(1.0)
    shots.append(gc.sh("advstats_hd_panel_down"))
    gc.g.click(0.5, 0.97, move_only=True)

    if gc.set_graphics("legacy"):
        time.sleep(1.0)
        shots.append(gc.sh("advstats_legacy_open"))
        gc.g.press("esc")
        time.sleep(1.0)
        gc.g.press("c")
        time.sleep(1.5)
        shots.append(gc.sh("advstats_legacy_sheet"))
        gc.g.press("esc")
        time.sleep(1.0)
        row("legacy", None, "judged on the shots")
    else:
        row("legacy", False, "legacy graphics not reached")
    gc.set_graphics("hd")

    gc.g.press("i")
    time.sleep(1.5)
    copy = [spot] if spot else []
    if copy:
        gc.g.click(*gc.rp_inv_xy(int(copy[0]["x"]), int(copy[0]["y"])), move_only=True)
        time.sleep(1.2)
        shots.append(gc.sh("advstats_hd_tooltip"))
        gc.g.click(0.5, 0.97, move_only=True)
    row("ring copy in the backpack", bool(copy), "%s" % copy[:1])
    gc.close_right_panel()
    for loc, _code, _stats in GEAR:
        gc.H("unequip %s" % loc)
    gc.H("packclear")
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else ("shots" if r[1] is None else "FAIL")) for r in rows)
    gc.finish("advstats", ok, note + "; SHORTCUT: gear made and worn by the harness", mark, shots, log,
              partial="panel rows and values (shots)")


# Check `advgroups` (bugs #581 / #582, plugin part advstats): the panel in groups, a buff that changes it, Avoid.
EF_SKILL, EF_STATS = 324, {67: "velocitypercent", 68: "attackrate", 182: "armor_override_percent", 52: "magicmindam", 53: "magicmaxdam"}
PB_SKILL, PB_STATS = 350, {338: "passive_dodge", 339: "passive_avoid", 340: "passive_evade"}


def open_panel(gc, shots, name):
    """C, then a background click on the sheet's Advanced Stats button (HD)."""
    gc.close_right_panel()
    gc.g.press("c")
    time.sleep(1.5)
    gc.g.click(*gc.sp2_xy(*HD_BUTTON))
    time.sleep(1.5)
    gc.g.click(0.5, 0.97, move_only=True)
    time.sleep(0.5)
    shots.append(gc.sh(name))


def close_panels(gc):
    gc.g.press("esc")
    time.sleep(1.0)
    gc.close_right_panel()


def read_stats(gc, stats):
    return {sid: gc.rd("player", sid) for sid in stats}


def part_line(gc):
    return gc.mxl_part(gc.statbook_text().splitlines(), "advstats")


def run_groups(gc):
    """The Advanced Stats panel in groups (plugin part advstats). An Amazon learns Ecstatic Frenzy (skill 324, `setskill`
    with the level raised to 30) and casts it in town with the panel open: the Speed rows "Attack / Movement Speed from Skills",
    the magic adds and "Total Character Defense = 0" must come up (shots before / after, the client's stats in the log). An
    Assassin learns Perfect Being (350): the Defense group gets the Avoid line. Then legacy graphics (D2R has no Advanced
    Stats panel there: the sheet's shot). SHORTCUT: skills, level and mana set by the harness."""
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    line = part_line(gc)
    row("part on", "advstats on" in line, line[:200] or "no advstats line")

    # Amazon, Ecstatic Frenzy
    if gc.be_class(0):
        gc.goto(1, timeout=60)
        gc.set_graphics("hd")
        with gc.Level(30):
            got = gc.learn(EF_SKILL, 1)
            row("Ecstatic Frenzy learnt", got == 1, "base level %s" % got)
            before = read_stats(gc, EF_STATS)
            open_panel(gc, shots, "advgroups_hd_amazon_before")
            gc.g.click(*gc.sp2_xy(*HD_SCROLL_LOW))
            time.sleep(1.0)
            gc.g.click(0.5, 0.97, move_only=True)
            shots.append(gc.sh("advgroups_hd_amazon_before_down"))
            max_mana = gc.rd("player", 9) or 0
            gc.setstat("player", 9, max(max_mana, 200 << 8))  # a new level-1 Amazon has 15 mana, less than the skill costs
            gc.setstat("player", 8, max(max_mana, 200 << 8))  # mana full
            gc.Hl("cast %d self" % EF_SKILL, log)
            time.sleep(2.0)
            after = read_stats(gc, EF_STATS)
            shots.append(gc.sh("advgroups_hd_amazon_buff"))
            gc.g.click(*gc.sp2_xy(1162 + 765 + 18, 160 + 40))  # scroll bar top
            time.sleep(1.0)
            gc.g.click(0.5, 0.97, move_only=True)
            shots.append(gc.sh("advgroups_hd_amazon_buff_top"))
            note = ", ".join("%s %s -> %s" % (EF_STATS[k], before[k], after[k]) for k in EF_STATS)
            row("buff stats on the client", (after[68] or 0) > (before[68] or 0) and (after[67] or 0) > (before[67] or 0), note)
            row("skill speed rows", None, "the shot must read %+d%% Attack Speed / %+d%% Movement Speed from Skills (value - 100)"
                % ((after[68] or 100) - 100, (after[67] or 100) - 100))
            line = part_line(gc)
            m = re.search(r"rebuilt on a change (\d+)", line)
            row("panel rebuilt after the cast", bool(m) and int(m.group(1)) > 0, line[:220])
            close_panels(gc)
            gc.setstat("player", 9, max_mana)
            gc.setstat("player", 8, max_mana)
            if gc.set_graphics("legacy"):
                time.sleep(1.0)
                gc.g.press("c")
                time.sleep(1.5)
                shots.append(gc.sh("advgroups_legacy_sheet"))
                gc.g.press("esc")
                time.sleep(1.0)
                row("legacy", None, "D2R has no Advanced Stats panel in legacy graphics (judged on the shot)")
            else:
                row("legacy", False, "legacy graphics not reached")
            gc.set_graphics("hd")
    else:
        row("Amazon", False, "could not play an Amazon")

    # Assassin, Perfect Being
    if gc.be_class(6):
        gc.goto(1, timeout=60)
        gc.set_graphics("hd")
        with gc.Level(30):
            got = gc.learn(PB_SKILL, 1)
            row("Perfect Being learnt", got == 1, "base level %s" % got)
            time.sleep(1.0)
            avoid = read_stats(gc, PB_STATS)
            row("avoid stats on the client", any(avoid.values()), ", ".join("%s %s" % (PB_STATS[k], avoid[k]) for k in PB_STATS))
            open_panel(gc, shots, "advgroups_hd_assassin_avoid")
            gc.g.click(*gc.sp2_xy(*HD_SCROLL_LOW))
            time.sleep(1.0)
            gc.g.click(0.5, 0.97, move_only=True)
            shots.append(gc.sh("advgroups_hd_assassin_avoid_down"))
            close_panels(gc)
    else:
        row("Assassin", False, "could not play an Assassin")

    line = part_line(gc)
    log.append("advstats: " + line)
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else ("shots" if r[1] is None else "FAIL")) for r in rows)
    gc.finish("advgroups", ok, note + "; SHORTCUT: skills, level and mana set by the harness", mark, shots, log,
              partial="panel rows and values (shots)")
