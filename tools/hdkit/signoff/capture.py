"""Pure helpers of the in-game sign-off (no game, no framework): mode codes, the feet pixel of a polled unit, the cut box
around it, labelling of burst frames by their nearest `facing` poll, and the pick of one steady frame per mode.
gamecheck.py imports this file by path; the tests import it as hdkit.signoff.capture."""

MODE_INDEX = {"dt": 0, "nu": 1, "wl": 2, "gh": 3, "a1": 4, "a2": 5, "bl": 6, "sc": 7, "s1": 8, "s2": 9, "s3": 10,
              "s4": 11, "dd": 12, "kb": 13, "sq": 14, "rn": 15}
CAST = ("nu", "a1", "a2", "gh", "bl", "sc", "s1", "s2", "s3", "s4")
CUT = (400, 400)
CUT_FEET = (200, 300)
FEET = (800.0, 437.5)      # hdkit.view.camera.FEET_1600x900 (kept here: this file runs without hdkit on the path)
CLIENT = (1600, 900)       # the game client size the constants here are for (settings capture.client)


def feet_px(f, scale=1.0):
    """Screen pixel of a polled unit's feet in a 1600x900 HD capture (hdkit.view.camera.unit_pixel)."""
    dx, dy = f["x"] - f["px"], f["y"] - f["py"]
    return scale * (FEET[0] + 24.0 * (dx - dy)), scale * (FEET[1] + 12.0 * (dx + dy))


def box_of(feet):
    x0, y0 = int(round(feet[0] - CUT_FEET[0])), int(round(feet[1] - CUT_FEET[1]))
    return x0, y0, x0 + CUT[0], y0 + CUT[1]


def pick(frames, mode_code, key=None):
    """The frame in the middle of the first steady run of `mode_code` (both neighbour polls agree on mode, dir, x, y);
    with `key`, only frames whose polled facing key is that key count."""
    want = MODE_INDEX[mode_code]
    runs, cur = [], []
    for fr in frames:
        p = fr["poll"]
        if p.get("mode") == want and fr["steady"] and (key is None or (p.get("dir", -1) >= 0 and key_of(p["dir"]) == key)):
            cur.append(fr)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    if not runs:
        return None
    run = max(runs[:2], key=len) if mode_code != "dd" else runs[-1]
    return run[len(run) // 2] if mode_code != "dd" else run[-1]


def label(t0, frames, polls):
    """Each frame gets its nearest poll, whether both neighbour polls agree, and the time since its mode run began."""
    runs, last = [], None
    for tp, f in polls:
        if f.get("mode") != last:
            runs.append(tp)
            last = f.get("mode")
    out = []
    for tf, b, img in frames:
        if not polls:
            break
        i = min(range(len(polls)), key=lambda j: abs(polls[j][0] - tf))
        p = polls[i]
        nb = [polls[j][1] for j in (i - 1, i + 1) if 0 <= j < len(polls)]
        keyset = ("mode", "dir", "x", "y", "px", "py")
        steady = all(all(n.get(k) == p[1].get(k) for k in keyset) for n in nb)
        start = max((r for r in runs if r <= tf + 0.02), default=runs[0])
        out.append({"t": tf, "t_burst": round(tf - t0, 3), "t_mode": round(max(0.0, tf - start), 3), "box": b,
                    "img": img, "poll": p[1], "steady": steady})
    return out


# --- exact facings. A unit casting at the character faces it: the polled dir64 is the angle of the sub-tile vector from
# the unit to the character, dir 0 along (+1, +1) (screen down), clockwise on screen (phase 8 polls: (-1, 3) -> 11,
# (-2, -1) -> 29, (0, -3) -> 40, (3, -1) -> 52). key = sprite_dir_logic.h KeyOf. So the spot that gives a key is derived
# from where the unit really stands, not retried blind.
FACE = ((1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0))   # the step towards each key
# fresh spots (in steps) the character walks to between attempts, round the first spot (game_checks.MON_TURN_SPOTS)
SPOTS = ((0, 0), (1, 0), (2, 0), (2, 1), (1, 1), (0, 1), (0, 2), (1, 2), (2, 2), (3, 2), (3, 1), (3, 0))
PLAYER_BOX = (752, 278, 848, 450)   # the character in a 1600x900 capture (screen centre)


def configure(client=None, feet_px=None, player_box=None):
    """Sets the capture constants from the settings (hdkit.signoff.config `capture`); None keeps a value. Callers read them
    through the module (capture.PLAYER_BOX), never by a copy made at import time."""
    global CLIENT, FEET, PLAYER_BOX
    if client:
        CLIENT = tuple(int(v) for v in client)
    if feet_px:
        FEET = tuple(float(v) for v in feet_px)
    if player_box:
        PLAYER_BOX = tuple(int(v) for v in player_box)


def key_of(dir64):
    return ((int(dir64) & 63) + 4) >> 3 & 7


def dir64_of(vx, vy):
    """dir64 of a unit at the origin facing the sub-tile vector (vx, vy) (towards the character)."""
    import math
    return int(round((math.degrees(math.atan2(vy, vx)) - 45.0) / 5.625)) % 64


def key_toward(unit_xy, player_xy):
    return key_of(dir64_of(player_xy[0] - unit_xy[0], player_xy[1] - unit_xy[1]))


def spots_for(unit_xy, key, reach, most=6):
    """Character spots round a unit standing at unit_xy that make it face `key` when it casts at the character: integer
    sub-tile vectors whose dir64 is within 2 of the key's centre (8 * key; the bin is +-4) and whose length is near
    `reach`, best first."""
    import math
    out = []
    for vx in range(-reach - 2, reach + 3):
        for vy in range(-reach - 2, reach + 3):
            ln = math.hypot(vx, vy)
            if ln < 2 or ln > reach + 1.5:
                continue
            err = abs(((dir64_of(vx, vy) - 8 * key) + 32) % 64 - 32)
            if err <= 2:
                out.append((err, abs(ln - reach), (unit_xy[0] + vx, unit_xy[1] + vy)))
    out.sort()
    return [s for _e, _l, s in out[:most]]


def twin_cut(unit_xy, twin_player_xy):
    """Box of the twin shot (taken with the character at twin_player_xy) that shows the ground under a unit at unit_xy at
    the cut's feet pixel, and the character's box of that twin inside the cut (to leave out when it moved since)."""
    b = box_of(feet_px({"x": unit_xy[0], "y": unit_xy[1], "px": twin_player_xy[0], "py": twin_player_xy[1]}))
    return b, [PLAYER_BOX[0] - b[0], PLAYER_BOX[1] - b[1], PLAYER_BOX[2] - b[0], PLAYER_BOX[3] - b[1]]


UNIT_CORE = (CUT_FEET[0] - 60, CUT_FEET[1] - 140, CUT_FEET[0] + 60, CUT_FEET[1] + 10)   # the unit's body in a cut


def covers(box, core=UNIT_CORE):
    """Share of `core` (the unit's body in a cut) that `box` covers."""
    w = max(0, min(box[2], core[2]) - max(box[0], core[0]))
    h = max(0, min(box[3], core[3]) - max(box[1], core[1]))
    return w * h / float((core[2] - core[0]) * (core[3] - core[1]))
