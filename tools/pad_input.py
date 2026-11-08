#!/usr/bin/env python
"""Scripted gamepad input for game checks (lane padinput): the dev plugin's harness verb `pad` (plugin/src/harness_cmds.cpp)
fakes an XInput pad in controller slot 0 inside the game process. No gamepad, no driver: D2R 3.3 reads pads only through
XInputGetState (XINPUT9_1_0.dll) and the verb swaps that import for its own function while it is on.

Verbs (`h pad ...`): on | off | press <buttons> [ms] | hold <buttons> | release [buttons] | stick L|R <x> <y> |
trigger L|R <0-255>; buttons a b x y lb rb lt rt ls rs start back up down left right, '+' joins (lb+a); sticks in percent
(-100..100, y up). Without arguments: the status line (`pad on=1 hooked=1 polls=... buttons=0x...`).

Scripts (run_script, the command line): words separated by blanks:
  a  lb+a  down:300        press (ms after ':', default 120)
  hold:lb  release  release:lb
  stick:l:0:100            stick L|R x y (percent)
  trigger:r:255
  wait:1.5                 seconds
Each press is followed by a short gap so the game sees the button go up before the next one.

Command line, for a game a run already started (slot lock held by that run):
  MXL_SLOT=2 MXL_RUN=<run> py -3 tools/pad_input.py on | off | status | "<script>"
"""
import re
import sys
import time

GAP_S = 0.25  # after a press: the release reaches the game (polls every frame) before the next press
CONNECT_S = 6.0  # D2R polls a disconnected controller slot every 4 s: `on` waits until a poll came
STATUS_RE = re.compile(r"pad on=(\d+) hooked=(\d+) polls=(\d+) packet=(\d+) buttons=0x([0-9a-f]+) lt=(\d+) rt=(\d+) "
                       r"l=(-?\d+),(-?\d+) r=(-?\d+),(-?\d+) held=0x([0-9a-f]+) pressed=0x([0-9a-f]+) gamepadUi=(-?\d+) device=(-?\d+)")
STATUS_KEYS = ("on", "hooked", "polls", "packet", "buttons", "lt", "rt", "lx", "ly", "rx", "ry", "held", "pressed", "gamepadUi", "device")
HEX_KEYS = ("buttons", "held", "pressed")
BUTTONS = {"a", "b", "x", "y", "lb", "rb", "lt", "rt", "ls", "rs", "l3", "r3", "start", "menu", "back", "view", "up", "down",
           "left", "right", "dup", "ddown", "dleft", "dright"}


def parse_status(lines):
    """The `pad` status line as a dict of ints, or {} when there is none."""
    for ln in lines:
        m = STATUS_RE.search(ln)
        if m:
            return {k: int(v, 16 if k in HEX_KEYS else 10) for k, v in zip(STATUS_KEYS, m.groups())}
    return {}


def _buttons(word):
    if not word or any(b.lower() not in BUTTONS for b in word.split("+")):
        raise ValueError("unknown button in %r" % word)
    return word.lower()


def parse_script(text):
    """A script to [(kind, harness args or seconds)]: kind 'h' = a `pad` verb's arguments (then a gap for a press),
    'wait' = seconds. ValueError on a word it cannot read."""
    steps = []
    for word in text.split():
        parts = word.split(":")
        head = parts[0].lower()
        if head == "wait" and len(parts) == 2:
            steps.append(("wait", float(parts[1])))
        elif head in ("hold", "release") and len(parts) <= 2:
            if head == "hold" and len(parts) != 2:
                raise ValueError("hold needs buttons: %r" % word)
            steps.append(("h", head + ("" if len(parts) == 1 else " " + _buttons(parts[1]))))
        elif head == "stick" and len(parts) == 4 and parts[1].lower() in ("l", "r"):
            x, y = int(parts[2]), int(parts[3])
            if not (-100 <= x <= 100 and -100 <= y <= 100):
                raise ValueError("stick percent out of range: %r" % word)
            steps.append(("h", "stick %s %d %d" % (parts[1].upper(), x, y)))
        elif head == "trigger" and len(parts) == 3 and parts[1].lower() in ("l", "r"):
            v = int(parts[2])
            if not 0 <= v <= 255:
                raise ValueError("trigger out of range: %r" % word)
            steps.append(("h", "trigger %s %d" % (parts[1].upper(), v)))
        elif len(parts) <= 2:
            ms = int(parts[1]) if len(parts) == 2 else 120
            if not 0 <= ms <= 60000:
                raise ValueError("press ms out of range: %r" % word)
            steps.append(("h", "press %s %d" % (_buttons(parts[0]), ms)))
        else:
            raise ValueError("cannot read %r" % word)
    return steps


def pad(H, args, log=None):
    """One `pad` verb through `H(cmd) -> (ok, lines)` (game_checks.H / game_ctl.hcmd); returns (ok, status dict)."""
    ok, lines = H(("pad " + args).strip())
    if log is not None:
        log.append("h pad %s -> %s" % (args, "OK" if ok else "FAIL"))
        log.extend("   " + ln for ln in lines)
    return ok, parse_status(lines)


def on(H, log=None, wait_s=CONNECT_S):
    """Connects the scripted pad and waits until the game polled it (status dict; polls > 0 when it did)."""
    ok, st = pad(H, "on", log)
    if not ok:
        return st
    start = st.get("polls", 0)
    t0 = time.time()
    while time.time() - t0 < wait_s:
        time.sleep(0.5)
        _ok, st = pad(H, "", None)
        if st.get("polls", 0) > start:
            break
    if log is not None:
        log.append("pad on: %s" % st)
    return st


def off(H, log=None):
    return pad(H, "off", log)[1]


def press(H, buttons, ms=120, log=None):
    ok, st = pad(H, "press %s %d" % (_buttons(buttons), ms), log)
    time.sleep(ms / 1000.0 + GAP_S)
    return ok


def run_script(H, text, log=None):
    """Runs a script (module docstring); False at the first verb the harness refused."""
    for kind, arg in parse_script(text):
        if kind == "wait":
            time.sleep(arg)
            continue
        ok, _st = pad(H, arg, log)
        if not ok:
            return False
        if arg.startswith("press "):
            time.sleep(int(arg.rsplit(" ", 1)[1]) / 1000.0 + GAP_S)
    return True


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    import game_ctl
    H = game_ctl.hcmd
    word = argv[1].strip()
    if word == "on":
        print(on(H))
    elif word == "off":
        print(off(H))
    elif word == "status":
        print(pad(H, "")[1])
    else:
        ok = run_script(H, word, [])
        print(("OK " if ok else "FAIL ") + str(pad(H, "")[1]))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
