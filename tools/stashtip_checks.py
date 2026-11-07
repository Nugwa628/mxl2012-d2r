"""Lane orbtab (bug #551): the hover text of the RotW stash's advanced slots shows the item's whole tooltip, as the backpack does
(check `stashtip` of tools/game_checks.py; plugin part `stashtip`, plugin/src/stash_tip.cpp).

Set-up (SHORTCUT, named in the note): the items are made in the backpack by the harness (`item <code> inv`); everything else is
background input as a player makes it: the stash object, the tabs, a hover over the backpack item, Ctrl-click into its slot, a
hover over the slot. Per item two shots: `stashtip_<mode>_inv_<code>` (the backpack tooltip) and `stashtip_<mode>_slot_<code>`
(the slot tooltip), judged side by side: the slot's text must hold the backpack's lines (the effect text of each orb) and
D2R's move hints, nothing twice. The part's counters (`mxl2012`: slot tooltips built) must grow with the slot hovers.

`stashtip` (a RotW character, MXL_CHAR=MedStashA on slot 2): HD then legacy graphics; four different orbs on ORBS, an elixir on
MEDIAN, a rune on Runes, a gem on Gems, an oil on the Materials tab's Median page. The items stay in their slots (stacks of the
shared stash, as in check `medtab`).
"""
import re
import time
from pathlib import Path

import medtab_checks as mt
import rotw_stash_legacy as rsl

HD_ITEMS = [("orbs", "&01"), ("orbs", "&50"), ("orbs", "&a1"), ("orbs", "&95"), ("median", "eo7"), ("runes", "r01"), ("gems", "gcw"),
            ("materials", "6o^")]
LEGACY_ITEMS = [("orbs", "&02"), ("orbs", "&60"), ("runes", "r02"), ("gems", "gcg")]
PAGES = {"orbs": "advancedstash_runes", "median": "advancedstash_runes", "runes": "advancedstash_runes", "gems": "advancedstash_gems",
         "materials": "advancedstash_materials"}
SD_PANEL = (318, 90, 1.5)  # classic stash panel -> 1600 x 900 client: origin x, y and scale (lane medstash)


def layout(gc, legacy):
    rel = rsl.SD_LAYOUT if legacy else rsl.HD_LAYOUT
    path = Path(gc.g.GAME_DIR) / "mods" / "mxl2012" / "mxl2012.mpq" / rel
    return rsl.lenient_json(path.read_text("utf-8"))


def slot_rect(lay, page, code):
    """The rect of `code`'s AdvancedStashSlotWidget among the direct children of `page` (layout codes write "@" as "_")."""
    want = code.replace("@", "_")
    node = rsl.find(lay, page)
    for w in node.get("children", []):
        f = w.get("fields", {})
        if w.get("type") == "AdvancedStashSlotWidget" and f.get("itemCode") == want:
            r = f["rect"]
            return r["x"], r["y"], r.get("width", 98), r.get("height", 98)
    return None


def slot_xy(gc, lay, page, code, legacy):
    r = slot_rect(lay, page, code)
    if r is None:
        return None
    cx, cy = r[0] + r[2] / 2, r[1] + r[3] / 2
    if legacy:
        return (SD_PANEL[0] + SD_PANEL[2] * cx) / 1600.0, (SD_PANEL[1] + SD_PANEL[2] * cy) / 900.0
    return gc.sp2_xy(cx, cy)


def hover(gc, xy):
    gc.g.click(*xy, move_only=True)
    time.sleep(1.0)


def park(gc):
    gc.g.click(0.5, 0.97, move_only=True)
    time.sleep(0.4)


def built(gc, log):
    """The part's count of slot tooltips built (`mxl2012`), None when the line is missing."""
    import game_ctl
    text = game_ctl.console_text("mxl2012") or ""
    m = re.search(r"stashtip (.*)", text)
    log.append("status: %s" % (m.group(0)[:300] if m else "no stashtip line"))
    n = re.search(r"slot tooltips (\d+)", text)
    return int(n.group(1)) if n else None


def one(gc, log, shots, mode, tab, code, lay, legacy):
    """Makes `code` in the backpack, hovers it, Ctrl-clicks it into its slot, hovers the slot. True when it went in and the slot
    was hovered."""
    mt.tab(gc, tab)
    if tab == "materials" and "Median" not in (mt.status(gc, log).get("page") or ""):
        mt.selector(gc)
    before = mt.backpack_ids(gc)
    gc.Hl("item %s inv" % code, log)
    time.sleep(0.6)
    new = [i for i in gc.rp_items_now() if i.get("page") == 0 and i["id"] not in before]
    if not new:
        log.append("%s: not made" % code)
        return False
    it = new[0]
    grid = mt.SD_INV if legacy else gc.RP_INV
    xy = gc.rp_inv_xy(it["x"], it["y"], grid)
    hover(gc, xy)
    shots.append(gc.sh("stashtip_%s_inv_%s" % (mode, code.replace("&", "o").replace("^", "x"))))
    gc.g.click(*xy, mods=("ctrl",))
    time.sleep(1.0)
    if it["id"] in mt.backpack_ids(gc):
        log.append("%s: still in the backpack after the Ctrl-click" % code)
        return False
    sxy = slot_xy(gc, lay, PAGES[tab], code, legacy)
    if sxy is None:
        log.append("%s: no slot in the layout's %s" % (code, PAGES[tab]))
        return False
    hover(gc, sxy)
    shots.append(gc.sh("stashtip_%s_slot_%s" % (mode, code.replace("&", "o").replace("^", "x"))))
    park(gc)
    return True


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
        gc.finish("stashtip", False, "the stash did not open", mark, shots, log)
        return
    n0 = built(gc, log)
    row("part on", n0 is not None, "stashtip line in mxl2012: %s" % n0)
    lay = layout(gc, False)
    res = [(code, one(gc, log, shots, "hd", tab, code, lay, False)) for tab, code in HD_ITEMS]
    n1 = built(gc, log)
    row("hd slots hovered", all(ok for _c, ok in res), "%s" % res)
    row("hd slot tooltips through the part", n0 is not None and n1 is not None and n1 > n0, "built %s -> %s" % (n0, n1))

    if gc.set_graphics("legacy"):  # switched with the stash open (the stash object click is placed for HD)
        time.sleep(1.0)
        lay = layout(gc, True)
        res = [(code, one(gc, log, shots, "legacy", tab, code, lay, True)) for tab, code in LEGACY_ITEMS]
        n2 = built(gc, log)
        row("legacy slots hovered", all(ok for _c, ok in res), "%s" % res)
        row("legacy slot tooltips through the part", n1 is not None and n2 is not None and n2 > n1, "built %s -> %s" % (n1, n2))
        gc.close_right_panel()
    else:
        row("legacy", False, "legacy graphics or the stash not reached")
    gc.set_graphics("hd")
    gc.close_right_panel()
    gc.H("packclear")
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
    gc.finish("stashtip", ok, note + "; the tooltip text judged on the shots (REVIEW); SHORTCUT: items made by the harness", mark, shots,
              log, partial="tooltip text (shots)")
