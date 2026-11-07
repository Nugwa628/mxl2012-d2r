"""Lane tabhl (bug #550): after a Ctrl-click from the backpack into the RotW stash's advanced pages, the tab that flashes is the
tab the item went to (check `tabflash` of tools/game_checks.py; plugin part `tabflash`, plugin/src/tab_flash.cpp).

Set-up (SHORTCUT, named in the note): the items are made in the backpack by the harness (`item <code> inv`); everything else is
background input as a player makes it: the stash object, the tabs, Ctrl-click from the backpack. The stash shows PERSONAL (or the
tab of the row) while the item goes in, so D2R flashes the item's tab. Per deposit the tab row is grabbed before the click and
about every 0.1 s for 1.5 s after it; the tab whose box changed most is the flashed one (`tabflash_<mode>_<code>.png`: the frame
with the strongest change; judged on the shots too). The part's status (`mxl2012 tabflash`: flashes, last tab) must agree.
Legacy graphics draw no tab flash (D2R's classic tab bar has no highlight; control run checks-20261107-144748-s2: no tab box
changed for any deposit, D2R's own Gems / Runes included), so there the shots must show no change and the part's status
judges the tab.

`tabflash` (a RotW character, MXL_CHAR=<throwaway> on slot 2): HD then legacy graphics, a gem, a D2R material, a Median material
(oil), a rune, an orb and an elixir from PERSONAL; in HD also a rune with MEDIAN shown (Runes flashes) and an elixir with
MEDIAN shown (nothing flashes, as D2R on its own tabs). Control run: MXL_CONTROL=tabflash (the part off) shows D2R's flash
(RUNES for the orb and the elixir).
"""
import os
import re
import time

import medtab_checks as mt

# (code, tab shown while it goes in, tab expected to flash: None = none)
HD_ITEMS = [("gcr", "personal", "gems"), ("rvs", "personal", "materials"), ("6o^", "personal", "materials"), ("r09", "personal", "runes"),
            ("&04", "personal", "orbs"), ("ey1", "personal", "median"), ("r10", "median", "runes"), ("ey2", "median", None)]
LEGACY_ITEMS = [("gcb", "personal", "gems"), ("7o^", "personal", "materials"), ("r11", "personal", "runes"), ("&05", "personal", "orbs"),
                ("ey3", "personal", "median")]
SP2_HD = (0.4163, 97.95, 86.8)  # HD stash layout -> 1600 x 900 client (game_checks.SP2_HD)
FRAMES = 14
MIN_CHANGE = 4.0  # mean absolute change of a tab box (0-255) that counts as a flash


def tab_boxes(legacy):
    """Per tab (0-6) its box on a 1600 x 900 client: (x0, y0, x1, y1)."""
    out = []
    for k in range(7):
        if legacy:
            cx, cy, hw, hh = mt.sd_tab_x(k), mt.SD_TAB_Y, 26, 9
        else:
            s = SP2_HD[0]
            cx, cy, hw, hh = SP2_HD[1] + (82 + 139 * (k + 0.5)) * s, SP2_HD[2] + (146 + 36) * s, 24, 11
        out.append((cx - hw, cy - hh, cx + hw, cy + hh))
    return out


def change(a, b, box):
    from PIL import ImageChops, ImageStat
    sx, sy = a.size[0] / 1600.0, a.size[1] / 900.0
    r = (int(box[0] * sx), int(box[1] * sy), int(box[2] * sx), int(box[3] * sy))
    d = ImageChops.difference(a.crop(r).convert("L"), b.crop(r).convert("L"))
    return ImageStat.Stat(d).mean[0]


def flashed(base, frames, legacy):
    """(tab or None, per-tab strongest change, index of the frame with the strongest change)."""
    boxes = tab_boxes(legacy)
    best = [0.0] * 7
    best_frame = [0] * 7
    for i, f in enumerate(frames):
        for k, box in enumerate(boxes):
            c = change(base, f, box)
            if c > best[k]:
                best[k], best_frame[k] = c, i
    k = max(range(7), key=lambda j: best[j])
    return (k if best[k] >= MIN_CHANGE else None), best, best_frame[k]


def parse_status(text):
    """`mxl2012 tabflash` -> {on, flashes, last, shown, median, orbs}."""
    out = {}
    m = re.search(r"tabflash (on|FAILED|off)", text)
    if m:
        out["on"] = m.group(1)
    for key, pat in (("flashes", r"flashes (\d+)"), ("last", r"last tab (-?\d+)"), ("shown", r"on the shown tab (\d+)"),
                     ("median", r"MEDIAN kinds (\d+)"), ("orbs", r"ORBS kinds (\d+)")):
        m = re.search(pat, text)
        if m:
            out[key] = int(m.group(1))
    return out


def status(gc, log):
    import game_ctl
    text = game_ctl.console_text("mxl2012 tabflash") or ""
    st = parse_status(text)
    log.append("tabflash status %s" % st)
    return st


def deposit(gc, log, shots, mode, code, shown, want):
    """One item: made in the backpack, the stash on `shown`, Ctrl-clicked; returns (ok, note)."""
    before = mt.backpack_ids(gc)
    gc.Hl("item %s inv" % code, log)
    time.sleep(0.6)
    new = [i for i in gc.rp_items_now() if i.get("page") == 0 and i["id"] not in before]
    if not new:
        return False, "%s not made" % code
    mt.tab(gc, shown)
    time.sleep(2.5)  # an earlier flash has faded
    st0 = status(gc, log)
    it = new[0]
    legacy = mode == "legacy"
    xy = gc.rp_inv_xy(it["x"], it["y"], mt.SD_INV if legacy else gc.RP_INV)
    gc.g.click(*xy, move_only=True)
    time.sleep(0.5)
    win = gc.g.need_window()
    base = gc.g.grab_client(win)
    gc.g.click(*xy, mods=("ctrl",))
    frames = []
    for _ in range(FRAMES):
        time.sleep(0.1)
        frames.append(gc.g.grab_client(win))
    went = it["id"] not in mt.backpack_ids(gc)
    tab, best, fi = flashed(base, frames, legacy)
    name = "tabflash_%s_%s" % (mode, code.replace("&", "o").replace("^", "x"))
    path = os.path.join(gc.g.current_run(), name + ".png")
    frames[fi].save(path)
    shots.append(os.path.basename(path))
    st = status(gc, log)
    want_k = mt.TABS.index(want) if want else None
    seen_k = None if legacy else want_k  # legacy draws no flash
    got = mt.TABS[tab] if tab is not None else None
    flashes = st.get("flashes", 0) - st0.get("flashes", 0) if "flashes" in st else None
    part_ok = st.get("on") != "on" or (flashes == (1 if want else 0) and (want is None or st.get("last") == want_k))
    note = "%s from %s: went in %s, flashed %s (want %s), change %s; part flashes +%s last %s" % (
        code, shown, went, got, want, ["%.1f" % b for b in best], flashes, st.get("last"))
    return went and tab == seen_k and part_ok, note


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else "FAIL", note))

    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    gc.H("packclear")
    if not gc.sp2_open_stash(log):
        gc.finish("tabflash", False, "the stash did not open", mark, shots, log)
        return
    st = status(gc, log)
    control = st.get("on") != "on"
    row("part", True, "tabflash %s%s" % (st.get("on", "off"), " (control run: D2R's flash)" if control else ""))
    mst = mt.status(gc, log)
    row("medtab live", mst.get("live") is True, "%s" % mst)
    for code, shown, want in HD_ITEMS:
        ok, note = deposit(gc, log, shots, "hd", code, shown, want)
        row("hd %s" % code, ok, note)
    mt.tab(gc, "personal")
    if gc.set_graphics("legacy"):  # switched with the stash open (the stash object click is placed for HD)
        time.sleep(1.0)
        for code, shown, want in LEGACY_ITEMS:
            ok, note = deposit(gc, log, shots, "legacy", code, shown, want)
            row("legacy %s" % code, ok, note)
        mt.tab(gc, "personal")
        gc.close_right_panel()
    else:
        row("legacy", False, "legacy graphics or the stash not reached")
    gc.set_graphics("hd")
    gc.close_right_panel()
    gc.H("packclear")
    ok = all(r[1] for r in rows)
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
    gc.finish("tabflash", ok, note + "; SHORTCUT: items made by the harness", mark, shots, log)
