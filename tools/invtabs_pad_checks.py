"""invtabs: the controller (gamepad) charm tab in game, check `invtabs_pad` of tools/game_checks.py (docs/invtabs-pad.md).

Needs invtabs.dll without CharmInv (`install_mod.py --invtabs <dll>`) and a fresh MXL_CHAR. Driven by the scripted gamepad
(harness `pad`, tools/pad_input.py), HD, background input:

  - the status line says the controller route is registered (`pad closed`);
  - Start opens the menu on Inventory; the menu's next-tab key opens the Charm Inventory tab (our panel open, our grid
    drawn), the previous-tab key goes back, the next one opens it again (the tab strip is in the shot `menu`). D2R pages
    the menu with RB / LB; with Controller QOL Updates (bundled in releases) it is RT / LT: the check uses what works;
  - with the backpack full of the test charm: D-pad right from our grid crosses into the backpack, A picks up a charm,
    left crosses back, A places it in the tab (page 6 gets it);
  - moved to cell 0,0, the menu closed and opened again, the first A picks it up: the focus lands on our grid;
  - A in the tab, right into the backpack, A: the charm leaves page 6 (taken back);
  - the summary: `invtabs summary` has the charm's line, the controller panel's summary rows were found (no "has no row"
    line for invtabs/Pad0), shot `summary`;
  - the mod's Send to stash button in the gamepad inventory still empties the backpack (tools/cqol_checks.py's route).
The test charm is a normal-quality a55 with +5 Strength (not a carry1 unique: the page refuses their second copy). The
harness `item` generator's
`wPrefix != 0 || wSuffix != 0` assert (bug #35) is reported as a harness note, not as this check's failure.
"""
import re
import time

import pad_input as pi
import padinput_checks

HARNESS_ASSERTS = {"wPrefix != 0 || wSuffix != 0": "bug #35 (the harness item generator, not the plugin)"}


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, {True: "PASS", False: "FAIL", None: "INFO"}[ok], note))

    def status():
        return gc._invtabs_status_line(log)

    def pad_state(line):
        m = re.search(r"; pad (\w+)", line)
        return m.group(1) if m else None

    def drawn(line):
        m = re.search(r"; drawn ([^;]+)", line)
        return m.group(1).strip() if m else None

    def page6():
        return [(c["code"], c["x"], c["y"]) for c in gc._invtabs_page6(log)]

    def shot(name):
        time.sleep(0.6)
        shots.append(gc.sh("invtabs_pad_" + name))

    # a normal-quality charm with +5 Strength (the summary checks' a55): many copies may sit on the page, unlike a carry1
    # unique, whose second copy the custom page refuses (docs/invtabs.md H)
    tcode, tmake = "a55", "item a55 normal inv 0=5"
    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    gc.release_held_item()
    gc.H("packclear")
    if page6():
        return gc.finish("invtabs_pad", False, "page 6 is not empty: use a fresh MXL_CHAR", mark, shots, log)
    st = status()
    row("controller route registered", pad_state(st) == "closed", st[st.find("status:"):][:220])

    p = pi.on(gc.H, log)
    row("pad polled", p.get("hooked") == 1 and p.get("polls", 0) > 0, "%s" % p)
    pi.run_script(gc.H, "start wait:2.0 b wait:1.5", log)
    gc.Hl("padui on", log)
    time.sleep(2.0)

    # the menu: Inventory first, then our tab with the menu's tab keys (RB / LB in D2R; RT / LT with Controller QOL Updates)
    pi.run_script(gc.H, "start wait:2.5", log)
    s0 = status()
    shot("menu")
    nxt, prv = "rb", "lb"
    pi.run_script(gc.H, "rb wait:2.0", log)
    s1 = status()
    if pad_state(s1) != "open":
        nxt, prv = "rt", "lt"
        pi.run_script(gc.H, "rt wait:2.0", log)
        s1 = status()
    shot("tab")
    pi.run_script(gc.H, prv + " wait:2.0", log)
    s2 = status()
    pi.run_script(gc.H, nxt + " wait:2.0", log)
    s3 = status()
    seq = [(pad_state(s), drawn(s)) for s in (s0, s1, s2, s3)]
    row("the Charm Inventory tab comes after Inventory (%s opens it, %s goes back)" % (nxt.upper(), prv.upper()),
        seq[0][0] == "closed" and seq[1] == ("open", "charms hd") and seq[2][0] == "closed" and seq[3] == ("open", "charms hd"),
        "start, %s, %s, %s: %s" % (nxt, prv, nxt, seq))

    # the backpack full of the test charm (whatever cell the D-pad lands on holds one); the tab is empty
    pi.run_script(gc.H, "b wait:1.5", log)
    gc.Hl("remove box 1", log)
    made = 0
    for _ in range(80):
        _, lines = gc.H(tmake)
        if not any(" page=0 " in ln for ln in lines):
            break
        made += 1
    if gc.held_item():
        gc.release_held_item()
    log.append("backpack filled with %d x %s" % (made, tcode))

    def open_tab():
        pi.run_script(gc.H, "start wait:2.5", log)
        if pad_state(status()) != "open":
            pi.run_script(gc.H, nxt + " wait:2.0", log)
        return pad_state(status()) == "open"

    # from the tab, right crosses into the backpack: A picks up a charm there; left back into the tab, A places it
    open_tab()
    pi.run_script(gc.H, " ".join(["right wait:0.35"] * 10) + " wait:0.5 a wait:1.2", log)
    picked = gc.held_item()
    shot("crossed_right")
    steps = 0
    for steps in range(1, 14):
        pi.run_script(gc.H, "left wait:0.5 a wait:1.2", log)  # inside the backpack an A swaps charms: one stays held
        if page6():
            break
    first_place = page6()
    shot("placed_from_backpack")
    row("right crosses into the backpack, A picks up a charm; left crosses back, A places it in the tab",
        bool(picked) and picked[1] == tcode and len(first_place) == 1 and not gc.held_item(),
        "picked %s; page 6 %s after %d left(s)" % (picked, first_place, steps))

    # move it to the tab's cell 0,0 with the pad, then: reopened, the first A picks it up (the focus is on our grid)
    cx, cy = (int(first_place[0][1]), int(first_place[0][2])) if first_place else (0, 0)
    # exactly cx lefts and cy ups: one more up from the top row leaves the grid for the menu's tab strip
    pi.run_script(gc.H, " ".join(["a wait:1.0"] + ["left wait:0.3"] * cx + ["up wait:0.3"] * cy + ["a wait:1.2"]), log)
    at00 = page6()
    pi.run_script(gc.H, "b wait:1.5", log)
    open_tab()
    pi.run_script(gc.H, "a wait:1.2", log)
    focus = gc.held_item()
    shot("focus_pickup")
    row("focus at open is on our grid: the first A picks up the charm at 0,0", at00 == [(tcode, "0", "0")] and bool(focus) and not page6(),
        "page 6 before %s; held after the first A %s; page 6 after %s" % (at00, focus, page6()))

    # taken back: right x10 into the backpack, A there (a swap: the tab's charm is in the backpack); then left, A into the tab
    pi.run_script(gc.H, "a wait:1.0", log)  # back to 0,0 first if it was picked up
    pi.run_script(gc.H, "a wait:1.0", log)  # pick it up again
    held0 = gc.held_item()
    pi.run_script(gc.H, " ".join(["right wait:0.35"] * 10) + " wait:0.5 a wait:1.2", log)
    back = (page6(), gc.held_item())
    shot("taken_back")
    row("A picks it up in the tab, right crosses, A puts it into the backpack", bool(held0) and not back[0],
        "held %s; page 6 %s, held after %s" % (held0, back[0], back[1]))
    for _ in range(13):
        if page6() or not gc.held_item():
            break
        pi.run_script(gc.H, "left wait:0.5 a wait:1.2", log)

    # the summary on the controller panel
    size = gc._invtabs_size()
    pi.run_script(gc.H, "b wait:1.2", log)
    open_tab()
    time.sleep(1.5)
    shot("summary")
    since = gc._invtabs_log_since(size)
    shown = [x for x in since if "on the controller panel" in x]
    norow = [x for x in since if "Pad0 has no row" in x or "setting row" in x]
    counted, skipped, lines = gc._invtabs_summary(log)
    row("summary on the controller panel: the charm's line, its rows set", bool(counted) and any(x.endswith("to Strength") for x in lines) and bool(shown) and not norow,
        "page 6 %s; counted %s, left out %s, lines %s; %s; row errors %s" % (page6(), counted, skipped, lines, shown[-1:], norow[:2]))
    pi.run_script(gc.H, "b wait:1.5", log)
    if gc.held_item():
        gc.release_held_item()
    gc.H("packclear")
    for it in gc._invtabs_backpack(log, tcode):
        gc.Hl("remove %s 1" % tcode, log)

    # Send to stash in the stock gamepad inventory (cqol's route)
    import cqol_checks
    gc.Hl("padui on", log)
    for code in ("hp1", "mp1", "r02"):
        gc.Hl("item %s inv" % code, log)
        time.sleep(0.4)
    n0 = len([i for i in gc.rp_items_now() if i.get("page") == 0])
    pi.run_script(gc.H, "start wait:2.0", log)
    if pad_state(status()) == "open":  # the menu came back on our tab: LT to Inventory
        pi.run_script(gc.H, "lt wait:2.0", log)
    ok_walk = padinput_checks.steps(gc, cqol_checks.INV_NAV, log, shots, "invtabs_pad_inv")
    n1 = len([i for i in gc.rp_items_now() if i.get("page") == 0])
    row("A on Send to stash (gamepad inventory)", ok_walk and n1 < n0, "backpack %d -> %d" % (n0, n1))
    pi.run_script(gc.H, "b wait:1.5", log)

    pi.off(gc.H, log)
    gc.Hl("padui off", log)
    gc.close_right_panel()
    if gc.held_item():
        gc.release_held_item()
    ok = all(r[1] is not False for r in rows)
    gc.finish("invtabs_pad", ok, "; ".join("%s %s" % (r[0], {True: "ok", False: "FAIL", None: "info"}[r[1]]) for r in rows), mark,
              shots, log, partial="the tab strip order and the summary text on the panel (shots menu, summary)", harness=HARNESS_ASSERTS)
