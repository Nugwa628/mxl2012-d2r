"""The character sheet's Advanced Stats panel (check `advstats` of tools/game_checks.py; data: itemstatcost `advdisplay`, set by
tools/txt_migrate.py advanced_stats from data/advanced_stats.tsv).

Set-up (SHORTCUT, named in the note): the worn items are made and worn by the harness (`equip`), a copy of the first ring is made in
the backpack (`item ... inv`); the panels are opened as a player does: C, a background click on the sheet's Advanced Stats
button, G for legacy graphics, I and a hover over the ring copy for its tooltip. Shots: `advstats_hd_sheet`, `advstats_hd_panel`,
`advstats_hd_panel_down` (the list scrolled), `advstats_legacy_*`, `advstats_hd_tooltip`. The log holds the client's value of
every stat worn (`stat player`), to compare with the panel's rows and the tooltip on the shots.
"""
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
