"""Lane padinput: the gamepad UI driven by a scripted gamepad (harness verb `pad`, tools/pad_input.py), HD.

Check `padprobe`: runs MXL_PAD_PROBE (a pad_input script plus `shot:<name>` words) in town with the gamepad UI on, to find
out which button does what. Check `padinput`: the pad alone switches D2R to its gamepad UI; then, with `padui on` keeping it
there, the panel menu opened by Start, focus moved with the D-pad (item tooltips by focus), A picks up and puts back, RB / LB
between the menu's panels; the stash opened at its object, LT / RT between its tabs, RB / LB between shared pages. Shots judged by hand (REVIEW).

Run with a RotW character that has items in the backpack and the mod's stash tabs (MXL_CHAR=MedStashA on slot 2).
"""
import os
import re
import time

import pad_input as pi


def steps(gc, text, log, shots, prefix):
    """A pad_input script whose `shot:<name>` words take a shot (padin_<prefix>_<name>) in between."""
    chunk = []
    for word in text.split() + ["shot:"]:
        if word.startswith("shot:"):
            if chunk and not pi.run_script(gc.H, " ".join(chunk), log):
                log.append("script refused: %s" % " ".join(chunk))
                return False
            chunk = []
            if word[5:]:
                time.sleep(0.8)
                shots.append(gc.sh("padin_%s_%s" % (prefix, re.sub(r"\W", "_", word[5:]))))
        else:
            chunk.append(word)
    return True


def status(gc, log):
    return pi.pad(gc.H, "", log)[1]


def start(gc, log, rows, shots):
    """Town, HD, pad on (polled), then the pad alone switches the UI; `padui on` keeps it for the harness's own clicks."""
    gc.enable_debug()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    gc.close_right_panel()
    st = pi.on(gc.H, log)
    rows.append(("pad polled by the game", st.get("hooked") == 1 and st.get("polls", 0) > 0, "%s" % st))
    before = st.get("gamepadUi")
    pi.run_script(gc.H, "stick:l:0:40 wait:0.4 stick:l:0:0 wait:2.5", log)  # a short walk north
    st = status(gc, log)
    rows.append(("stick walk (info)", True, "gamepadUi %s -> %s, device %s" % (before, st.get("gamepadUi"), st.get("device"))))
    pi.run_script(gc.H, "start wait:2.5", log)  # Start opens the gamepad panel menu
    st = status(gc, log)
    rows.append(("gamepad UI by a pad button alone", before == 0 and st.get("gamepadUi") == 1,
                 "gamepadUi %s -> %s, device %s" % (before, st.get("gamepadUi"), st.get("device"))))
    shots.append(gc.sh("padin_start_menu"))
    pi.run_script(gc.H, "b wait:1.5", log)  # B closes it
    gc.Hl("padui on", log)
    time.sleep(2.5)


def finish(gc, name, rows, mark, shots, log):
    pi.off(gc.H, log)
    gc.Hl("padui off", log)
    time.sleep(2.0)
    st = status(gc, log)
    rows.append(("pad off: import back, UI back", st.get("hooked") == 0 and st.get("on") == 0, "%s" % st))
    gc.close_right_panel()
    for r in rows:
        log.append("ROW %s %s: %s" % (r[0], "PASS" if r[1] else "FAIL", r[2]))
    ok = all(r[1] for r in rows)
    gc.finish(name, ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows), mark, shots, log,
              partial="navigation, tooltips and tabs (shots)")


def run_probe(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []
    start(gc, log, rows, shots)
    shots.append(gc.sh("padin_probe_town"))
    rows.append(("probe script", steps(gc, os.environ.get("MXL_PAD_PROBE", "start shot:start b shot:b"), log, shots, "probe"), ""))
    finish(gc, "padprobe", rows, mark, shots, log)


# Defaults found with `padprobe` (lane padinput, 2026-11-07); each can be changed by env for another layout.
OPEN_INV = os.environ.get("MXL_PAD_OPEN_INV", "start wait:1.5")
INV_NAV = os.environ.get("MXL_PAD_INV_NAV", "shot:open right shot:right1 right shot:right2 a shot:a_pick a shot:a_put "
                                            "down shot:down1 down shot:down2 rb shot:rb1 lb shot:lb1 lb shot:lb2 rb shot:rb2")
STASH_NAV = os.environ.get("MXL_PAD_STASH_NAV", "shot:open rt shot:rt1 rb shot:rb1 lb shot:lb1 rt shot:rt2 rt shot:rt3 rt shot:rt4 "
                                                "lt shot:lt1 lt shot:lt2 lt shot:lt3 down shot:down1 right shot:right1")


def run(gc):
    mark = gc.engine_mark()
    log, shots, rows = [], [], []
    start(gc, log, rows, shots)
    shots.append(gc.sh("padin_town"))
    steps(gc, OPEN_INV, log, shots, "inv")
    rows.append(("inventory steps", steps(gc, INV_NAV, log, shots, "inv"), OPEN_INV + " | " + INV_NAV))
    pi.run_script(gc.H, "b wait:1.5", log)
    gc.Hl("padui on", log)
    time.sleep(1.5)
    if not gc.sp2_open_stash(log):
        log.append("stash did not open by the object click: OpenPanel")
        gc.Hl("stashpage uia PanelManager OpenPanel BankExpansionLayout", log)
        time.sleep(1.5)
    rows.append(("stash steps", steps(gc, STASH_NAV, log, shots, "stash"), STASH_NAV))
    pi.run_script(gc.H, "b wait:1.5", log)
    gc.sp2_close(log)
    finish(gc, "padinput", rows, mark, shots, log)
