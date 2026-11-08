"""Lane padui: D2R's controller (gamepad) UI on the mod's panels, without a gamepad (check `padui` of tools/game_checks.py).

The harness verb `padui on` (plugin/src/harness_cmds.cpp) makes D2R take every input as gamepad input, so it switches to
its gamepad UI (layouts/controller, the gamepad HUD) and stays there while background keys and the virtual mouse drive it.
Navigation itself needs gamepad events, which background input cannot send: this check only takes the shots, the look is
judged on them (REVIEW). Shots per graphics mode: town, inventory, character sheet, skill tree, the stash with each of its
tabs, the cube; the same screens with the PC UI first for comparison.

Run with a RotW character that has the mod's stash tabs and a cube (the lane used MXL_CHAR=MedStashA on slot 2).
"""
import re
import time

import medtab_checks as mt

def pad(gc, log, on):
    """`padui on|off`; returns the status line's numbers {forced, gamepadUi, pending, device}."""
    gc.Hl("padui %s" % ("on" if on else "off"), log)
    time.sleep(2.5)  # the switch lands on the next PanelManager update and reloads every layout
    _ok, lines = gc.Hl("padui", log)
    m = next((re.search(r"forced=(\d+) gamepadUi=(\d+) pending=(-?\d+) device=(-?\d+)", ln) for ln in lines if "forced=" in ln), None)
    return dict(zip(("forced", "gamepadUi", "pending", "device"), map(int, m.groups()))) if m else {}


def panels(gc, log, shots, mode):
    """Town, inventory, character sheet and skill tree, each opened by its key and closed with Esc."""
    shots.append(gc.sh("padui_%s_town" % mode))
    for key, name in (("i", "inventory"), ("c", "charsheet"), ("t", "skilltree")):
        gc.g.key(key)
        time.sleep(1.5)
        shots.append(gc.sh("padui_%s_%s" % (mode, name)))
        gc.g.key("esc")
        time.sleep(1.0)
    gc.close_right_panel()


def cube(gc, log, shots, mode):
    """The cube opened by a right click on it in the backpack (inventory open)."""
    items = gc.rp_items_now()
    box = next((it for it in items if it.get("code") == "box" and it.get("page") == 0), None)
    if box is None:
        log.append("%s: no cube in the backpack" % mode)
        return False
    gc.g.key("i")
    time.sleep(1.5)
    gc.g.click(*gc.rp_inv_xy(box["x"], box["y"], mt.SD_INV if mode.startswith("legacy") else gc.RP_INV), button="right")
    time.sleep(1.5)
    shots.append(gc.sh("padui_%s_cube" % mode))
    gc.g.key("esc")
    time.sleep(1.0)
    gc.close_right_panel()
    return True


def stash(gc, log, shots, mode, pad_on):
    """The stash opened at the Act 1 stash object, then each tab as a player picks it (a click; in the gamepad UI the
    click is tried as well, since a mouse click is how a keyboard player would reach the tabs there)."""
    if not gc.sp2_open_stash(log):
        log.append("%s: stash did not open by the object click" % mode)
        gc.Hl("stashpage uia PanelManager OpenPanel BankExpansionLayout", log)
        time.sleep(1.5)
    shots.append(gc.sh("padui_%s_stash" % mode))
    for name in ("gems", "materials", "runes", "median", "orbs"):
        try:
            mt.tab(gc, name)
        except Exception as e:  # a tab the gamepad layout moved: the shot shows what is there
            log.append("%s: tab %s: %s" % (mode, name, e))
        time.sleep(1.0)
        shots.append(gc.sh("padui_%s_stash_%s" % (mode, name)))
    st = mt.status(gc, log)
    log.append("%s stash medtab status (pad=%s): %s" % (mode, pad_on, st))
    gc.sp2_close(log)


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    gc.enable_debug()
    gc.goto(1, timeout=60)
    for graphics in ("hd", "legacy"):
        if not gc.set_graphics(graphics):
            row("%s graphics" % graphics, False, "not reached")
            continue
        gc.close_right_panel()
        panels(gc, log, shots, graphics + "_pc")
        stash(gc, log, shots, graphics + "_pc", False)
        cube(gc, log, shots, graphics + "_pc")
        st = pad(gc, log, True)
        row("%s gamepad UI on" % graphics, st.get("gamepadUi") == 1 and st.get("forced") == 1, "%s" % st)
        panels(gc, log, shots, graphics + "_pad")
        stash(gc, log, shots, graphics + "_pad", True)
        cube(gc, log, shots, graphics + "_pad")
        st = pad(gc, log, False)
        row("%s gamepad UI off again" % graphics, st.get("gamepadUi") == 0 and st.get("forced") == 0, "%s" % st)
    gc.set_graphics("hd")
    gc.close_right_panel()
    judged = [r for r in rows if r[1] is not None]
    ok = bool(judged) and all(r[1] for r in judged)
    note = "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows)
    gc.finish("padui", ok, note, mark, shots, log, partial="the gamepad UI's look (shots)")


NATIVE_PANELS = ("PlayerInventoryExpansionLayout", "CharacterStatsPanel", "SkillsTreePanel", "HoradricCubeLayout")


def run_native(gc):
    """`padui2`: keys do not open panels in the gamepad UI, so each panel is opened by D2R's own UI message (PanelManager
    OpenPanel, the `stashpage uia` verb), shot, and closed the same way; then a backpack item is hovered (tooltip)."""
    mark = gc.engine_mark()
    log, shots = [], []
    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    st = pad(gc, log, True)
    opened = []
    for name in NATIVE_PANELS:
        ok, _lines = gc.Hl("stashpage uia PanelManager OpenPanel %s" % name, log)
        time.sleep(1.5)
        shots.append(gc.sh("padui2_%s" % name.lower()))
        if name == "PlayerInventoryExpansionLayout":
            items = [it for it in gc.rp_items_now() if it.get("page") == 0 and it.get("code") != "box"]
            for it in items[:2]:
                gc.g.click(*gc.rp_inv_xy(it["x"], it["y"], gc.RP_INV), move_only=True)
                time.sleep(1.0)
                shots.append(gc.sh("padui2_tooltip_%s" % it.get("code", "item").replace("&", "o")))
        gc.Hl("stashpage uia PanelManager ClosePanel %s" % name, log)
        time.sleep(1.0)
        opened.append("%s %s" % (name, "sent" if ok else "FAIL"))
    pad(gc, log, False)
    gc.close_right_panel()
    gc.finish("padui2", st.get("gamepadUi") == 1, "; ".join(opened), mark, shots, log, partial="the panels' look (shots)")
