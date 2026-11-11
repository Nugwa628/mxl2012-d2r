"""Lane cqol: PyreFly's Controller QOL Updates (bundled, docs/bundled-plugins.md) driven by the scripted gamepad (harness `pad`,
tools/pad_input.py), check `cqol` of tools/game_checks.py.

The run's driver puts the build of tools/build_controllerqol.ps1 and its config into the slot's mods\\mxl2012\\d2rloader\\ (a dev
install has no bundled plugins) and takes them out afterwards. With a RotW character that has the mod's stash tabs
(MXL_CHAR=MedStashA on slot 2):

  - log: controller-qol loaded, its belt shortcuts off (belt_actions = false), every other feature admitted (a "declined" or
    "disabled" line names the feature), the mxl2012 skill profile written to d2rloader\\config\\controller-qol-skills\\;
  - stash with the gamepad UI (padui on): RT / LT through all seven tabs (the real tab from `mxl2012 medtab`), RB / LB on Shared;
  - LB + L3 (Deposit All) on Gems / Materials / Runes / MEDIAN / ORBS: made items of each page leave the backpack;
  - LB + X with the focus on a backpack item beside MEDIAN (the focus by D-pad, judged on the shots);
  - LB + A on the backpack with an Identify tome there identifies a ring; LB + Y moves the focused item into the Cube;
  - ground loot: a dropped item, hold LB (assignment labels, shot), LB + A picks it up;
  - inventory (Start): the focus from the gloves to the send button and the grid, from the boots to gold and the grid (shots),
    A on Send to stash empties the backpack;
  - the same tab paging and a deposit in legacy graphics (the gamepad UI stays HD).
MXL_CQOL_LOG names the plugin's log when it is not in the usual places.
"""
import glob
import os
import re
import time

import game_ctl as g
import medtab_checks as mt
import pad_input as pi
import padinput_checks

# per page: codes made in the backpack for LB + L3 (Median codes from tools/median_tabs.py)
DEPOSITS = {"gems": ["gcv", "gfv"], "materials": ["6o^", "qus"], "runes": ["r01", "r05"], "median": ["eo7", "zkw"],
            "orbs": ["&01", "&a1"]}
TAB_NAMES = mt.TABS
# LB + L3 as a player presses it: LB held first, then the stick clicked
DEPOSIT_ALL = os.environ.get("MXL_CQOL_DEPOSIT", "hold:lb wait:0.5 ls wait:3.0 release")
# the inventory's focus walk (pad_input words, `shot:<name>` takes a shot): from the panel menu's start focus round the gloves,
# the send buttons and the grid, then the boots, gold and the grid; an `a` on the send button sends the backpack to the stash.
# One `left` only (head to the right weapon): a second one is the panel boundary, which leads into the backpack grid while a
# plugin's controller route (CharmInv) is registered (docs/invtabs-pad.md)
INV_NAV = os.environ.get("MXL_CQOL_INV_NAV", "shot:open up up up left shot:weapon down shot:gloves down shot:send down shot:send_down "
                                             "up shot:send_up a wait:1.5 shot:send_a b wait:1.2 start wait:2.0 shot:reopen right "
                                             "right shot:belt4 right shot:gold up shot:boots down shot:boots_down down shot:gold_down")


def qol_log_lines():
    """Controller QOL's own log (D2RLoader writes a plugin's log into the d2rloader\\logs folder next to its plugins folder)."""
    paths = [os.environ.get("MXL_CQOL_LOG", "")]
    for base in (os.path.dirname(g.MXL_LOG), os.path.join(g.GAME_DIR, "d2rloader", "logs")):
        paths += glob.glob(os.path.join(base, "controller-qol*.log"))
    out = []
    for p in paths:
        try:
            with open(p, encoding="utf-8-sig", errors="replace") as f:
                out += [ln.rstrip() for ln in f]
        except OSError:
            pass
    if not out:  # some loaders log a plugin's lines into d2rloader.log
        try:
            with open(g.LOADER_LOG, encoding="utf-8-sig", errors="replace") as f:
                out = [ln.rstrip() for ln in f if "QOL" in ln or "controller-qol" in ln.lower()]
        except OSError:
            pass
    return out


def profile_files():
    base = os.path.join(g.GAME_DIR, "mods", "mxl2012", "d2rloader", "config", "controller-qol-skills")
    return sorted(glob.glob(os.path.join(base, "*.overrides.toml")))


def tab_now(gc, log):
    return mt.status(gc, log).get("tab")


def backpack(gc):
    return [i for i in gc.rp_items_now() if i.get("page") == 0]


def make(gc, log, codes):
    """Items made in the backpack; their ids."""
    before = {i["id"] for i in backpack(gc)}
    for c in codes:
        gc.Hl("item %s inv" % c, log)
        time.sleep(0.4)
    return [i["id"] for i in backpack(gc) if i["id"] not in before]


def page_to(gc, log, want, shots, prefix, legacy=False):
    """RT / LT until the stash shows tab `want` (at most 9 presses); True when it got there."""
    for _ in range(9):
        cur = tab_now(gc, log)
        if cur == want:
            return True
        if cur is None:
            return False
        pi.run_script(gc.H, ("rt" if cur < want else "lt") + " wait:1.0", log)
    return tab_now(gc, log) == want


def reopen_stash(gc, log):
    """B closes the gamepad menu (stash or Cube), the stash object opens it again."""
    pi.run_script(gc.H, "b wait:1.2", log)
    gc.sp2_close(log)
    gc.Hl("padui on", log)
    if not gc.sp2_open_stash(log):
        gc.Hl("stashpage uia PanelManager OpenPanel BankExpansionLayout", log)
    time.sleep(1.5)


def shot(gc, shots, name):
    time.sleep(0.6)
    shots.append(gc.sh("cqol_" + name))


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("INFO" if ok is None else "FAIL"), note))

    lines = qol_log_lines()
    log += ["qol log: " + ln[:200] for ln in lines[-200:]]
    row("controller-qol loaded", any("[QOL" in ln for ln in lines), "%d log lines" % len(lines))
    row("belt shortcuts off", any("Potion shortcuts off (belt_actions = false)" in ln for ln in lines), "")
    bad = [ln for ln in lines if re.search(r"declin|disabled|unavailable|refus", ln, re.I) and "belt_actions" not in ln]
    row("features declined (info)", None, "; ".join(ln[-140:] for ln in bad[:12]) or "none")

    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    gc.H("packclear")
    st = pi.on(gc.H, log)
    row("pad polled", st.get("hooked") == 1 and st.get("polls", 0) > 0, "%s" % st)
    pi.run_script(gc.H, "start wait:2.0 b wait:1.5", log)
    gc.Hl("padui on", log)
    time.sleep(2.0)
    profs = profile_files()
    text = open(profs[0], encoding="utf-8").read() if profs else ""
    row("mxl2012 skill profile seeded", "# Mod: mxl2012" in text and '"1109"' in text,
        "%s (%d bytes)" % (profs, len(text)))

    # ground loot: hold LB shows assignments, LB + A picks the item up
    gc.rp_ground_item("r10", log)
    time.sleep(1.0)
    pi.run_script(gc.H, "hold:lb wait:1.2", log)
    shot(gc, shots, "ground_lb_held")
    before = len(backpack(gc))
    pi.run_script(gc.H, "lb+a wait:2.5 release", log)
    row("LB + A ground loot", len(backpack(gc)) > before, "backpack %d -> %d" % (before, len(backpack(gc))))

    # stash: RT / LT through the seven tabs
    gc.H("packclear")
    if not gc.sp2_open_stash(log):
        gc.Hl("stashpage uia PanelManager OpenPanel BankExpansionLayout", log)
        time.sleep(1.5)
    seen = [tab_now(gc, log)]
    shot(gc, shots, "hd_tab%s" % seen[-1])
    for _ in range(7):
        pi.run_script(gc.H, "rt wait:1.2", log)
        seen.append(tab_now(gc, log))
        shot(gc, shots, "hd_rt_tab%s" % seen[-1])
    back = []
    for _ in range(3):
        pi.run_script(gc.H, "lt wait:1.2", log)
        back.append(tab_now(gc, log))
    row("RT reaches MEDIAN (5) and ORBS (6)", 5 in seen and 6 in seen, "RT tabs %s, LT %s" % (seen, back))
    want_back = [(seen[-1] - k) % 7 for k in (1, 2, 3)] if seen[-1] is not None else []
    row("LT pages back (wraps past Personal to ORBS)", back == want_back, "LT %s, want %s" % (back, want_back))

    # Deposit All (LB + L3) per advanced page
    for page in ("gems", "materials", "runes", "median", "orbs"):
        want = TAB_NAMES.index(page)
        got = page_to(gc, log, want, shots, page)
        ids = make(gc, log, DEPOSITS[page])
        pi.run_script(gc.H, DEPOSIT_ALL, log)
        left = [i for i in ids if i not in {b["id"] for b in backpack(gc)}]
        shot(gc, shots, "hd_deposit_%s" % page)
        row("LB + L3 deposit on %s" % page.upper(), got and ids and len(left) == len(ids),
            "tab %s; made %d, deposited %d (%s)" % (tab_now(gc, log), len(ids), len(left), DEPOSITS[page]))
        gc.H("packclear")
        reopen_stash(gc, log)  # a refused LB + L3 is D2R's own L3: the Cube replaces the stash

    # LB + X on a focused backpack item beside MEDIAN
    page_to(gc, log, 5, shots, "median")
    ids = make(gc, log, ["eo8"])
    pi.run_script(gc.H, "down wait:0.8 right wait:0.8", log)  # into the backpack (the Cube), then the next item
    shot(gc, shots, "hd_median_focus1")
    for i in range(4):
        if not ids or ids[0] not in {b["id"] for b in backpack(gc)}:
            break
        pi.run_script(gc.H, "hold:lb wait:0.4 x wait:2.0 release", log)
        if ids[0] not in {b["id"] for b in backpack(gc)}:
            break
        pi.run_script(gc.H, "left wait:0.6", log)
        shot(gc, shots, "hd_median_focus%d" % (i + 2))
    row("LB + X stores a focused item into MEDIAN", bool(ids) and ids[0] not in {b["id"] for b in backpack(gc)},
        "eo8 %s" % ("left the backpack" if ids and ids[0] not in {b["id"] for b in backpack(gc)} else "stayed"))
    gc.H("packclear")
    pi.run_script(gc.H, "b wait:1.5", log)
    gc.sp2_close(log)

    # LB + A (identify by the tome) and LB + Y (into the carried Cube), focus walked through the backpack
    gc.Hl("padui on", log)
    made = make(gc, log, ["ibk"])
    gc.Hl("item rin magic inv unid", log)
    time.sleep(0.6)
    rings = [i for i in backpack(gc) if i.get("code") == "rin"]
    pi.run_script(gc.H, "start wait:2.0 down wait:0.8", log)
    done = False
    for k in range(6):
        pi.run_script(gc.H, "hold:lb wait:0.4 a wait:2.0 release", log)
        now = {i["id"]: i for i in backpack(gc)}
        done = bool(rings) and now.get(rings[0]["id"], {}).get("identified") == 1
        shot(gc, shots, "inv_lba_%d" % k)
        if done:
            break
        pi.run_script(gc.H, "right wait:0.6", log)
    row("LB + A identifies (tome in the backpack)", done, "ring %s, tome %s" % (rings[:1], made))
    before_cube = len([i for i in gc.rp_items_now() if i.get("page") == 3])
    pi.run_script(gc.H, "hold:lb wait:0.4 y wait:2.0 release", log)
    after_cube = len([i for i in gc.rp_items_now() if i.get("page") == 3])
    shot(gc, shots, "inv_lby")
    row("LB + Y moves the focused item into the Cube", after_cube > before_cube, "cube items %d -> %d" % (before_cube, after_cube))
    pi.run_script(gc.H, "b wait:1.5", log)
    gc.H("packclear")

    # inventory: the focus round the send button and gold (shots), A on Send to stash when INV_NAV ends on it
    gc.Hl("padui on", log)
    make(gc, log, ["hp1", "mp1", "r02"])
    n0 = len(backpack(gc))
    pi.run_script(gc.H, "start wait:2.0", log)
    row("inventory focus walk (shots)", padinput_checks.steps(gc, INV_NAV, log, shots, "cqol_inv"), INV_NAV)
    n1 = len(backpack(gc))
    row("A on Send to stash", (n1 < n0) if " a " in " %s " % INV_NAV else None, "backpack %d -> %d" % (n0, n1))
    pi.run_script(gc.H, "b wait:1.5", log)
    gc.H("packclear")

    # legacy: paging and one deposit
    gc.set_graphics("legacy")
    gc.H("packclear")
    if not gc.sp2_open_stash(log):
        gc.Hl("stashpage uia PanelManager OpenPanel BankExpansionLayout", log)
        time.sleep(1.5)
    seen_l = [tab_now(gc, log)]
    for _ in range(7):
        pi.run_script(gc.H, "rt wait:1.2", log)
        seen_l.append(tab_now(gc, log))
    shot(gc, shots, "legacy_tab%s" % seen_l[-1])
    row("legacy: RT reaches MEDIAN and ORBS", 5 in seen_l and 6 in seen_l, "RT tabs %s" % seen_l)
    page_to(gc, log, 6, shots, "orbs")
    ids = make(gc, log, ["&02"])
    pi.run_script(gc.H, DEPOSIT_ALL, log)
    row("legacy: LB + L3 deposit on ORBS", bool(ids) and ids[0] not in {b["id"] for b in backpack(gc)}, "&02")
    shot(gc, shots, "legacy_deposit_orbs")
    pi.run_script(gc.H, "b wait:1.5", log)
    gc.sp2_close(log)
    gc.set_graphics("hd")

    pi.off(gc.H, log)
    gc.Hl("padui off", log)
    time.sleep(1.5)
    st = pi.pad(gc.H, "", log)[1]
    row("pad off: import back", st.get("hooked") == 0 and st.get("on") == 0, "%s" % st)
    tail = qol_log_lines()[len(lines):]
    log += ["qol log (run): " + ln[:200] for ln in tail]
    gc.close_right_panel()
    ok = all(r[1] is not False for r in rows)
    gc.finish("cqol", ok, "; ".join("%s %s" % (r[0], {True: "ok", False: "FAIL", None: "info"}[r[1]]) for r in rows), mark,
              shots, log, partial="focus walks, ground labels and the gamepad pages (shots)")
