"""Lane sendstash: the inventory's "Send storable/stackable items to stash" button (checks `sendstash` and `sendstashclassic` of
tools/game_checks.py; plugin part `sendstash`, plugin/src/send_stash.cpp).

A click sends every backpack item that has a slot on a Reign of the Warlock stash page (Gems / Materials / Runes, Median's pages)
with D2R's own deposit packet (0x63 sub 0), one item at a time, the stash closed; a full slot (99) keeps its item; one summary
line goes to the chat.

Set-up (SHORTCUT, named in the note): the items are made in the backpack by the harness (`item <code> inv`) and the backpack is
emptied with `packclear`; the button is a background click on its place (HD_CLICK / LEGACY_CLICK, measured on the run's shots) and
the harness `sendstash press` runs the same code path when a click place is not known. Each round reads the backpack (`items`),
the part's counters and summary line (`sendstash`). The part reads no slot counts (none found on the client), so a full slot is
shown by its refusal: El runes are sent until one stays.

`sendstash` (a RotW character): outside town, HD: slot items and other items, the click; El runes until the slot is full (the
rest stay: "stack full (El Rune ...)"); 99 and one more; Save and Exit, one more El still stays (the full slot was kept) and a
shot of the stash's Runes page; legacy graphics: the button's shot and a click; the stash OPEN (bug #554), HD and legacy: a
click sends slot items, Mystic Orbs and Elixirs (MEDIAN / ORBS slots) too. `sendstashclassic` (an expansion character,
MXL_CHAR=StashTab): the greyed button, its tooltip on hover (shot) and a click that moves nothing but answers with the reason
line (bug #554: the hidden live button used to take the greyed one's click and hover).
"""
import os
import re
import time

OPEN_ITEMS = ["r04", "gcb", "&01", "0g7", "eo7"]  # Nef, Chipped Sapphire, a Mystic Orb, two Elixirs (ORBS / MEDIAN slots)
SLOT_ITEMS = ["r01", "r02", "gcr", "gcr", "gfv", "r03"]  # El, Eld, 2 Chipped Ruby, Flawed Amethyst, Tir: all have a RotW slot
OTHER_ITEMS = ["hp1", "key"]  # a potion and a key: no slot, they stay
NAMES = {"r01": "El Rune", "gcr": "Chipped Ruby"}
CAP = 99
OUTSIDE = 2  # Blood Moor
# 1600 x 900 client, inventory open: the button's centre (HD: the bottom-left square, measured on crophd.png). Legacy: measured on
# the sendstash_legacy_inventory shot; MXL_SS_LEGACY_XY=x,y overrides it (another legacy aspect).
HD_CLICK = (1071, 669)
LEGACY_CLICK = (897, 690)  # 4:3 legacy (pillarboxed 1200 x 900), run checks-20261106-014339-s2
LEGACY169_CLICK = (1096, 690)  # 16:9 legacy (the bundled legacy169 puts the inventory at the right edge), lane sendopen
NOSLOTS_LINE = "Send to stash works in Reign of the Warlock games only"


def parse_state(lines):
    """`h sendstash` -> {show, host, running, clicks, runs, sent, full, nottaken, busy, lines, linefails, faults, last}."""
    out = {}
    for ln in lines:
        ln = ln.strip()
        m = re.match(r"sendstash show=(\S+) (.*)", ln)
        if m:
            out["show"] = m.group(1)
            out.update({k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", m.group(2))})
            continue
        m = re.match(r'sendstash last="(.*)"$', ln)
        if m:
            out["last"] = m.group(1)
    return out


def backpack(items):
    """The backpack's item codes, without the character's Horadric Cube (box): `packclear` keeps it and no run moves it."""
    return sorted(i.get("code") for i in items if i.get("page") == 0 and i.get("code") != "box")


def state(gc, log, verb="sendstash"):
    _ok, lines = gc.Hl(verb, log)
    return parse_state(lines)


def wait_run(gc, log, runs_before, timeout):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = state(gc, log)
        if st.get("runs", 0) > runs_before and not st.get("running"):
            return st
        time.sleep(0.5)
    return state(gc, log)


def make(gc, log, codes):
    for c in codes:
        gc.Hl("item %s inv" % c, log)
    time.sleep(0.6)


def send(gc, log, shots, name, trigger, items):
    """One run: trigger(), wait for it, shot of the chat line. Returns (counter delta, state after)."""
    s0 = state(gc, log)
    trigger()
    s1 = wait_run(gc, log, s0.get("runs", 0), 2.5 * items + 6)
    shots.append(gc.sh("sendstash_" + name))
    delta = {k: s1.get(k, 0) - s0.get(k, 0) for k in ("clicks", "runs", "sent", "full", "nottaken", "lines", "linefails", "faults")}
    return delta, s1


def press(gc, log):
    return lambda: gc.Hl("sendstash press", log)


def click(gc, xy):
    return lambda: gc.g.click(xy[0] / 1600, xy[1] / 900)


def open_inventory(gc):
    gc.close_right_panel()
    gc.g.press("i")
    time.sleep(1.2)


def pillarboxed(gc):
    """Legacy graphics drawn 4:3 with black side bars (legacy169 off or missing); in 16:9 (legacy169 on) the picture has none.
    Reliable in a lit place (the town)."""
    a = gc.grab()
    w = a.shape[1]
    return float(a[:, : w // 10].mean()) < 6.0 and float(a[:, w - w // 10:].mean()) < 6.0


def legacy_xy(gc=None):
    env = os.environ.get("MXL_SS_LEGACY_XY")
    if env:
        x, y = env.split(",")
        return int(x), int(y)
    if gc is not None and not pillarboxed(gc):
        return LEGACY169_CLICK
    return LEGACY_CLICK


def open_stash(gc, log, legacy=False):
    """The stash and the inventory open: HD, the Act 1 chest clicked as a player does; legacy, D2R's own panel message (the
    harness's walk misses in 16:9 legacy, and its panel test reads HD pixels: the round's shots show the stash)."""
    if not legacy and gc.sp2_open_stash(log):
        return True
    _ok, lines = gc.Hl("stashpage uia PanelManager OpenPanel BankExpansionLayout", log)
    time.sleep(1.5)
    return gc.right_panel_open() or (legacy and "= 0" in " ".join(lines))


def stash_open_round(gc, log, shots, row, mode, xy):
    """Bug #554: the stash open, the button clicked: slot items, orbs and elixirs go into their slots."""
    gc.close_right_panel()
    gc.H("packclear")
    if not open_stash(gc, log, legacy=mode == "legacy"):
        row("%s stash open" % mode, False, "the stash did not open")
        return
    make(gc, log, OPEN_ITEMS + ["hp1"])
    shots.append(gc.sh("sendstash_%s_stashopen_before" % mode))
    d, s1 = send(gc, log, shots, "%s_stashopen" % mode, click(gc, xy), len(OPEN_ITEMS))
    left = backpack(gc.rc_items(log))
    stayed = [c for c in left if c in OPEN_ITEMS]  # a slot already at 99 from an earlier run keeps its item
    row("%s stash open" % mode, d.get("clicks") == 1 and d.get("sent", 0) == len(OPEN_ITEMS) - len(stayed)
        and d.get("full", 0) == len(stayed) and [c for c in left if c not in OPEN_ITEMS] == ["hp1"],
        "click at %s: counters %s, backpack %s, line %r" % (xy, d, left, s1.get("last")))
    gc.close_right_panel()
    gc.H("packclear")


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
    st = state(gc, log)
    row("button shown", st.get("show") == "button" and st.get("host", 0) > 0, "RotW game, own game: %s" % st)

    # 1. outside town, HD, inventory open, stash closed: the click sends the slot items, the others stay (an item whose slot is
    # already full from an earlier run stays too, and is named in the line)
    gc.goto(OUTSIDE, timeout=60)
    open_inventory(gc)
    make(gc, log, SLOT_ITEMS + OTHER_ITEMS)
    pack0 = backpack(gc.rc_items(log))
    shots.append(gc.sh("sendstash_hd_inventory"))
    d, s1 = send(gc, log, shots, "hd_outside_click", click(gc, HD_CLICK), len(SLOT_ITEMS))
    if d.get("clicks") == 0:  # the click did not reach the button: the harness press runs the same code
        log.append("the HD click did not reach the button (clicks +0): `sendstash press`")
        d, s1 = send(gc, log, shots, "hd_outside_press", press(gc, log), len(SLOT_ITEMS))
    pack1 = backpack(gc.rc_items(log))
    stayed = [c for c in pack1 if c in SLOT_ITEMS]
    ok = (sorted(c for c in pack1 if c not in SLOT_ITEMS) == sorted(OTHER_ITEMS) and d.get("sent") == len(SLOT_ITEMS) - len(stayed)
          and d.get("full") == len(stayed) and (s1.get("last") or "").startswith("Sent %d item" % d.get("sent")))
    row("hd outside town", ok, "area %d, backpack %s -> %s, counters %s, line %r" % (OUTSIDE, pack0, pack1, d, s1.get("last")))
    row("summary line", d.get("lines") == 1 and d.get("linefails") == 0, "chat line sent (shot sendstash_hd_outside_*): %s" % d)
    row("click reaches the button", d.get("clicks", 0) >= 1, "HD click at %s: clicks +%s" % (HD_CLICK, d.get("clicks")))

    # 2. El runes until the slot is full: the rest stay, "stack full (El Rune ...)"
    gc.H("packclear")
    filled = None
    for k in range(4):  # 4 x 30 > 99
        make(gc, log, ["r01"] * 30)
        d, s1 = send(gc, log, shots, "fill%d" % k, press(gc, log), 30)
        left = backpack(gc.rc_items(log))
        if d.get("full", 0) > 0:
            filled = (d, s1, left)
            break
        gc.H("packclear")
    if filled:
        d, s1, left = filled
        row("full slot", left == ["r01"] * d.get("full") and d.get("sent") + d.get("full") == 30
            and "stayed: stack full (El Rune" in (s1.get("last") or ""),
            "counters %s, backpack %d El, line %r" % (d, len(left), s1.get("last")))
    else:
        row("full slot", False, "120 El runes went without a refusal")
    gc.H("packclear")
    make(gc, log, ["r01"])
    d, s1 = send(gc, log, shots, "hd_full_99", press(gc, log), 1)
    left = backpack(gc.rc_items(log))
    row("slot at 99", left == ["r01"] and d.get("sent") == 0 and d.get("full") == 1
        and s1.get("last") == "Sent 0 items. 1 stayed: stack full (El Rune).", "backpack %s, counters %s, line %r" % (left, d, s1.get("last")))
    gc.H("packclear")
    make(gc, log, ["hp1"])
    d, s1 = send(gc, log, shots, "hd_nothing", press(gc, log), 0)
    row("nothing to send", d.get("sent") == 0 and s1.get("last") == "No storable/stackable items in the backpack.",
        "counters %s, line %r" % (d, s1.get("last")))
    gc.H("packclear")

    # 3. Save and Exit, back in: the full El slot is kept (one more El still stays), the stash's Runes page by eye
    gc.close_right_panel()
    if gc.leave_and_reenter():
        time.sleep(3)
        st = state(gc, log)
        row("button after reload", st.get("show") == "button", "%s" % st)
        make(gc, log, ["r01"])
        d, s1 = send(gc, log, shots, "reload_full", press(gc, log), 1)
        left = backpack(gc.rc_items(log))
        row("reload keeps the items", left == ["r01"] and d.get("full") == 1 and d.get("sent") == 0,
            "after the reload one El stays (slot still 99): backpack %s, counters %s, line %r" % (left, d, s1.get("last")))
        gc.H("packclear")
        if gc.sp2_open_stash(log):
            gc.sp2_tab(4)
            shots.append(gc.sh("sendstash_reload_stash_runes"))
            gc.close_right_panel()
    else:
        row("reload keeps the items", False, "Save and Exit did not leave the game")

    # 4. HD, the stash open (bug #554)
    gc.goto(1, timeout=60)
    stash_open_round(gc, log, shots, row, "hd", HD_CLICK)

    # 5. legacy graphics (town): the button's place (4:3, or 16:9 with the bundled legacy169), a click, the stash open
    if gc.set_graphics("legacy"):
        open_inventory(gc)
        shots.append(gc.sh("sendstash_legacy_inventory"))
        xy = legacy_xy(gc)
        if xy is not None:
            make(gc, log, ["gcr", "r02"])
            d, s1 = send(gc, log, shots, "legacy_click", click(gc, xy), 2)
            left = backpack(gc.rc_items(log))
            row("legacy click", d.get("clicks") == 1 and d.get("sent") == 2 and left == [],
                "click at %s: counters %s, backpack %s, line %r" % (xy, d, left, s1.get("last")))
        else:
            row("legacy click", None, "skipped: the legacy place is not measured yet (shot sendstash_legacy_inventory)")
        stash_open_round(gc, log, shots, row, "legacy", xy)
        gc.close_right_panel()
        gc.set_graphics("hd")
    else:
        row("legacy", False, "legacy graphics not reached")

    gc.H("packclear")
    st = state(gc, log)
    log.append("final %s" % st)
    judged = [r for r in rows if r[1] is not None]
    skipped = [r[0] for r in rows if r[1] is None]
    ok = bool(judged) and all(r[1] for r in judged) and not st.get("faults")
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else ("skipped" if r[1] is None else "FAIL")) for r in rows)
    gc.finish("sendstash", ok, note + "; SHORTCUT: items made by the harness", mark, shots, log, partial=", ".join(skipped) or None)


def run_classic(gc):
    """An expansion character: the greyed button with its reason, a click does nothing."""
    mark = gc.engine_mark()
    log, shots, rows = [], [], []
    gc.goto(1, timeout=60)
    gc.H("packclear")
    st = state(gc, log)
    rows.append(("greyed", st.get("show") == "noslots", "%s" % st))
    for mode in ("hd", "legacy"):
        if not gc.set_graphics(mode):
            rows.append((mode, False, "%s graphics not reached" % mode))
            continue
        open_inventory(gc)
        shots.append(gc.sh("sendstash_classic_%s" % mode))
        gc.close_right_panel()
    gc.set_graphics("hd")
    make(gc, log, ["r01"])
    s0 = state(gc, log)
    open_inventory(gc)
    gc.g.click(HD_CLICK[0] / 1600, HD_CLICK[1] / 900, move_only=True)  # the greyed button's own tooltip (bug #554)
    time.sleep(1.5)
    shots.append(gc.sh("sendstash_classic_hd_hover"))
    gc.g.click(HD_CLICK[0] / 1600, HD_CLICK[1] / 900)
    time.sleep(1.5)
    s1 = state(gc, log)
    left = backpack(gc.rc_items(log))
    rows.append(("click moves nothing", s1.get("runs") == s0.get("runs") and left == ["r01"],
                 "runs %s -> %s, backpack %s" % (s0.get("runs"), s1.get("runs"), left)))
    rows.append(("click says why", s1.get("refused", 0) == s0.get("refused", 0) + 1 and (s1.get("last") or "").startswith(NOSLOTS_LINE),
                 "refused %s -> %s, line %r" % (s0.get("refused"), s1.get("refused"), s1.get("last"))))
    shots.append(gc.sh("sendstash_classic_reason"))
    gc.close_right_panel()
    gc.H("packclear")
    for r in rows:
        log.append("ROW %s %s: %s" % (r[0], "PASS" if r[1] else "FAIL", r[2]))
    gc.finish("sendstashclassic", all(r[1] for r in rows), "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
              + "; greyed tooltip judged on the shots", mark, shots, log)

