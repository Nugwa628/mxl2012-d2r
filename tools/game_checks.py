#!/usr/bin/env python
"""Scripted in-game checks for D2R-XL 2012, in game_ctl's BACKGROUND input mode (docs/testing.md).

This is a game-check framework: the run folder, the slot lock, the watchdog that aborts a run
when the real cursor enters the game window or the game window takes the foreground, the report, menu / character / NPC helpers
and run_all. A check for a Median XL 2012 feature
is a function that calls add(...) and goes into CHECKS at the end of this file.

Everything goes through tools/game_ctl.py's background path: console lines run through the plugin test harness
(`g.console_bg`, `g.console_text`), keys and mouse are window messages plus the plugin's virtual cursor, screenshots
are PrintWindow captures. This script never presses Ctrl+`, never calls SetForegroundWindow / SetCursorPos and never
uses ImageGrab.

A game slot is required: MXL_SLOT=1 to 5 (or --slot N; slot 1 is the owner's own game: a game there that this run did
not start is never touched, tools/game_ctl.py); hold the slot's lock first
(`py -3 tools/game_slots.py lock N <lane>`). Run with `py -3 tools/game_checks.py all [check ...]` (writes report.md,
screenshots and logs into the run folder, work/runs/checks-<time>-sN/).
Checks: mxl2012 cltdostub rockshock cltdo83 srvhit23 frenzy cltnomis srvhit6spawn terrorzones pandewp skillprog classes textnames
melttrail elixirs uniquecarry whirlwind cubeclasses acts playthrough mercs (docs/plugin-plan.md section 10.1; results in docs/testing.md); lane rulescheck (player-path
verdicts of docs/median-rules-audit.md): rcbook rcdelay rctoken rclife rcscroll rchire rcdeath rclevels rprunes runeletters rpdarkring rpcharm
rpnames rpequip; bug #395 load probe: swarm; lane rulescheck2 (a SET-UP character, tools/rc_setup.py): rc2setup rc2quest rc2refund rc2delay rc2death; lane realpath (player-path checks, no god mode, no Tank, no `item ... inv`: docs/testing.md
"Player-path checks"): rp_items rp_vendors rp_death rp_areas rp_persist rp_use; lane isinside (bug #242): ins_levels; lane identify (bug #485): identify; lane elvensong (bug #487): elvensong; lane uiplus (bugs #488 / #489): lvlup_ui; lane unported (unported.md item use, ME9 mercenary level): iu_use ml_merc; lane totems (bug #493): totem_spread.
"""
import ctypes
import ctypes.wintypes as wt
import datetime
import hashlib
import math
import os
import re
import shutil
import struct
import sys
import threading
import time
import cube_game  # noqa: E402
import game_ctl as g  # noqa: E402
import winapi  # noqa: E402


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
LOCK = os.path.join(g.RUNS, "game.lock")
SAVES = g.SAVES
user32 = winapi.Dll("user32")


def new_run():
    """Own run folder for this process (runs/current.txt is shared between lanes)."""
    name = "checks-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-s%d" % g.SLOT  # two slots may start in the same second
    d = os.path.join(g.RUNS, name)
    os.makedirs(d, exist_ok=True)
    g.current_run = lambda create=False: d
    return d


def backup_saves():
    dst = os.path.join(g.RUNS, "save-backup-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-s%d" % g.SLOT)
    if os.environ.get("MXL_CHAR"):
        from pathlib import Path
        os.makedirs(dst, exist_ok=True)
        for p in Path(SAVES).glob(g.CHAR_NAME + ".*"):
            if p.is_file():
                shutil.copy2(p, dst)
    else:
        shutil.copytree(SAVES, dst)
    return dst


class Watchdog(threading.Thread):
    """Samples the real cursor and the foreground window every 25 ms."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop_flag = False
        self.abort = None
        self.first = self.last = None
        self.min = [10 ** 9, 10 ** 9]
        self.max = [-10 ** 9, -10 ** 9]
        self.fg_changes = 0
        self.samples = 0
        self.cursor_moves = 0
        self._fg = None
        self.inside_prev = False
        self.rest_inside = None

    def run(self):
        pt = wt.POINT()
        prev = None
        while not self.stop_flag:
            user32.GetCursorPos(ctypes.byref(pt))
            cur = (pt.x, pt.y)
            fg = user32.GetForegroundWindow()
            self.samples += 1
            if self.first is None:
                self.first = cur
            self.last = cur
            self.min = [min(self.min[0], cur[0]), min(self.min[1], cur[1])]
            self.max = [max(self.max[0], cur[0]), max(self.max[1], cur[1])]
            if prev is not None and cur != prev:
                self.cursor_moves += 1
            prev = cur
            if self._fg is not None and fg != self._fg:
                self.fg_changes += 1
            self._fg = fg
            h = g.find_window()
            if h:
                l, t, r, b = g.client_rect(h)
                inside = l <= cur[0] < r and t <= cur[1] < b
                if inside and not self.inside_prev and prev is not None and cur != prev and not self.abort:
                    # the real cursor MOVED into the game window. A cursor the user left resting over the window
                    # (never moved by this run) is not an abort reason; a move into it is, whoever made it.
                    self.abort = "real cursor moved %s -> %s into the game window %s" % (prev, cur, (l, t, r, b))
                self.inside_prev = inside
                if fg == h and not self.abort and time.time() >= g.FG_GRACE_UNTIL:
                    self.abort = "the game window became the foreground window"
            time.sleep(0.025)

    def summary(self):
        return ("%d samples at 25 ms; cursor before %s, after %s, range x %s..%s y %s..%s, %d cursor changes (the user's own "
                "mouse); foreground window changed %d times; abort: %s" % (
                    self.samples, self.first, self.last, self.min[0], self.max[0], self.min[1], self.max[1],
                    self.cursor_moves, self.fg_changes, self.abort))
WD = None


def guard():
    if WD is not None and WD.abort:
        raise RuntimeError("ABORT: " + WD.abort)


def grab():
    import numpy as np
    return np.asarray(g.grab_client().convert("RGB")).astype(int)


def clusters(a, b, region, thr=120, minblocks=3):
    """Changed regions between two captures inside region (fractions): [(fx, fy, blocks)] sorted top to bottom."""
    import numpy as np
    h, w, _ = a.shape
    m = np.abs(a - b).sum(axis=2) > thr
    mask = np.zeros_like(m)
    mask[int(region[1] * h):int(region[3] * h), int(region[0] * w):int(region[2] * w)] = True
    m &= mask
    S = 8
    gh, gw = h // S, w // S
    blocks = m[:gh * S, :gw * S].reshape(gh, S, gw, S).sum(axis=(1, 3)) >= 8
    seen = np.zeros_like(blocks)
    out = []
    for y in range(gh):
        for x in range(gw):
            if blocks[y, x] and not seen[y, x]:
                st, pts = [(y, x)], []
                seen[y, x] = True
                while st:
                    cy, cx = st.pop()
                    pts.append((cy, cx))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < gh and 0 <= nx < gw and blocks[ny, nx] and not seen[ny, nx]:
                                seen[ny, nx] = True
                                st.append((ny, nx))
                if len(pts) >= minblocks:
                    ys = [p[0] for p in pts]
                    xs = [p[1] for p in pts]
                    out.append((((min(xs) + max(xs) + 1) * S / 2) / w, ((min(ys) + max(ys) + 1) * S / 2) / h, len(pts)))
    return sorted(out, key=lambda t: (t[1], t[0]))
DEBUG_ON = {"v": False}


def con(cmd):
    """Run a console line. D2R's output is not readable in background mode."""
    guard()
    return g.console_bg(cmd)


def cheat(args):
    return con("cheat " + args)


def enable_debug():
    """`debug_mode` TOGGLES debug mode for the whole process; send it once per launch (the state cannot be read back:
    the effect of the next cheat is the check)."""
    if not DEBUG_ON["v"]:
        con("debug_mode")
        time.sleep(0.8)
        DEBUG_ON["v"] = True


def mxl_text():
    """The plugin's `mxl2012` command output (feature lines with their counters)."""
    return g.console_text("mxl2012", settle=1.0)


def mxl_mark():
    return g._size(g.MXL_LOG)


def mxl_lines_since(off):
    return [ln for ln in g._read_from(g.MXL_LOG, off).splitlines() if ln.strip()]


def counter(text, key, pattern):
    import re
    for ln in text.splitlines():
        if key in ln:
            m = re.search(pattern, ln)
            if m:
                return int(m.group(1))
    return None
DIFF_Y = {"normal": 0.42, "nightmare": 0.482, "hell": 0.542}
# MXL_ATTACH=1: the first start uses a game that is already running (one the Median XL launcher started, docs/launcher.md
# "Testing"; `game_ctl.py harness on` writes the harness file before that launch) instead of restarting it
ATTACH = {"v": os.environ.get("MXL_ATTACH") == "1"}


def to_menu():
    if ATTACH["v"] and g.game_pids():
        ATTACH["v"] = False
    elif g.game_pids():
        g.stop()
        time.sleep(2)
    DEBUG_ON["v"] = False
    if not g.start():
        return False
    if not g.clear_intro():
        return False
    time.sleep(2)
    g.click(0.62, 0.40)  # the menu swallows the first click
    time.sleep(1)
    return True


def wait_in_game(timeout=45):
    t0 = time.time()
    while time.time() - t0 < timeout:
        guard()
        if g.in_game():
            return True
        time.sleep(2)
    return False


def play(difficulty="normal"):
    g.click(*g.UI["menu_play"])
    if wait_in_game(8):
        return True
    time.sleep(2)
    g.click(0.5, DIFF_Y[difficulty])
    if wait_in_game(45):
        return True
    g.click(*g.UI["menu_play"])
    time.sleep(3)
    g.click(0.5, DIFF_Y[difficulty])
    return wait_in_game(45)
STATE = {"in_game": False}


MAX_CARDS = 9  # character cards the main menu shows without scrolling (1600 x 900 client, card n at y 0.076 + 0.091 * (n - 1))


def card_y(card):
    """Client fraction of the n-th character card; None for a card the list does not show (a click there selects nothing and Play
    starts whatever character is selected: lane acts 2026-10-28 played another lane's character that way)."""
    return 0.076 + 0.091 * (card - 1) if 1 <= card <= MAX_CARDS else None


def enter_game(card=1, difficulty="normal"):
    """From the main menu: play the selected character (card 1: the slot's most recently played one; card n: the n-th most recently
    played, see `card_of`) in Normal (or the difficulty named: it must be unlocked, rc_setup.set_progression). Refuses a card the
    list does not show."""
    y = card_y(card)
    if y is None:
        g.log("card %d is not on the visible character list: not played" % card)
        return False
    g.click(0.87, y)
    time.sleep(0.8)
    ok = play(difficulty)
    STATE["in_game"] = ok
    return ok


def card_of(name):
    """Position (1 = first) of a character on the main menu's list: the list is ordered by the time the character was last saved,
    newest first (what the .d2s files' modification times say). None when the character does not exist in this slot."""
    import glob
    files = sorted(glob.glob(os.path.join(SAVES, "*.d2s")), key=os.path.getmtime, reverse=True)
    names = [os.path.splitext(os.path.basename(f))[0] for f in files]
    return names.index(name) + 1 if name in names else None


def save_names(folder=None):
    """Names of the characters saved in the slot's save folder (the .d2s files), newest first."""
    import glob
    files = sorted(glob.glob(os.path.join(folder or SAVES, "*.d2s")), key=os.path.getmtime, reverse=True)
    return [os.path.splitext(os.path.basename(f))[0] for f in files]


def made_name(before, typed, folder=None):
    """The name of the character the game actually made: the newest save that was not there before Create (`before` = save_names()
    then). Stray key presses (real input on the PC while typing) can change the typed name, e.g. IlvlAma -> IlvlAamma. The typed name
    when no new save is there (yet)."""
    new = [n for n in save_names(folder) if n not in set(before)]
    return typed if typed in new or not new else new[0]
# Hero select (fractions of the client rect, measured on slot 3 2026-10-24): the class figures stand in a row
HERO_X = {"amazon": 0.166, "assassin": 0.26, "necromancer": 0.35, "barbarian": 0.44, "paladin": 0.556, "sorceress": 0.65, "druid": 0.866}


def create_character(cls, name):
    """From the main menu: Create New, pick the class figure, type the name, Create (enters the game in Normal). The first click on
    the menu is swallowed, so one goes to empty scenery first."""
    g.click(0.62, 0.40)
    time.sleep(1)
    g.click(*g.UI["char_create"])
    time.sleep(3)
    g.click(HERO_X[cls], 0.50)
    time.sleep(2)
    before = save_names()
    g.click(*g.UI["name_box"])
    for _ in range(16):  # the box keeps stray letters: empty it (16 = D2R's longest name) before typing
        g.press("backspace")
    g.type_text(name)
    time.sleep(1)
    g.click(*g.UI["create_ok"])
    ok = wait_in_game(60)
    STATE["in_game"] = ok
    STATE["char_name"] = made_name(before, name)  # what the game saved; callers that go on by name use this one
    if STATE["char_name"] != name:
        g.log("create_character: typed %r but the game made %r (stray input); going on with %r" % (name, STATE["char_name"],
                                                                                                    STATE["char_name"]))
    return ok


def cinematic_playing():
    """A cut scene plays in the game (the Act 5 one after the Tyrael walk): letterboxed, so the strip at the bottom where the HUD
    orbs are is black. Esc then skips the scene instead of opening the game menu."""
    from PIL import ImageStat
    im = g.grab_client(g.need_window()).convert("L")
    w, h = im.size
    return ImageStat.Stat(im.crop((0, int(.93 * h), w, h))).mean[0] < 3 and ImageStat.Stat(im.crop((0, int(.2 * h), w, int(.8 * h)))).mean[0] > 8


def skip_cinematic():
    n = 0
    while n < 12 and cinematic_playing():
        g.log("a cut scene plays: Esc held (%d)" % (n + 1))
        g.press("esc", hold=3)  # "Hold any button to skip"
        time.sleep(5)
        n += 1
    return n


def switch_character(name, cls, class_id):
    """Save and Exit, then play another character of the slot (created first when it does not exist); True when the game shows that
    class (`h state` class). A character that is already open is left as it is."""
    p = hstate()["player"]
    if p.get("class") == class_id:
        return True
    for attempt in range(3):
        skip_cinematic()
        g.key("esc")
        time.sleep(1.5)
        g.click(*g.UI["save_exit"])
        time.sleep(6)
        for _ in range(12):  # the save of a character with a long session behind it takes longer than 9 s
            if not g.in_game():
                break
            time.sleep(3)
        if not g.in_game():
            break
    if g.in_game():
        return False
    STATE["in_game"] = False
    time.sleep(2)
    if not g.menu_visible():  # after a long session the game can come back to the intro cinematic (morphdeath_blocked.png): skip it
        g.clear_intro(60)
        time.sleep(2)
        g.click(0.62, 0.40)  # the menu swallows the first click
        time.sleep(1)
    card = card_on_list(name, card_of(name))  # skillprog's paladin was card 18 of 29: the click hit nothing (2026-10-28)
    ok = create_character(cls, name) if card is None else enter_game(card)
    return bool(ok) and hstate()["player"].get("class") == class_id


def _checksum(d):
    d = bytearray(d)
    d[8:12] = len(d).to_bytes(4, "little")
    d[12:16] = b"\0\0\0\0"
    c = 0
    for b in d:
        c = ((c << 1) | (c >> 31)) & 0xffffffff
        c = (c + b) & 0xffffffff
    d[12:16] = c.to_bytes(4, "little")
    return bytes(d)


def patch_quests(name, quests):
    """Set 16-bit quest words {(difficulty, quest): word} in a closed character ('Woo!' section, 48 words per
    difficulty after 10 header bytes), fix the checksum and D2RLoader's `.d2rl` sidecar (docs/save-format.md)."""
    p = os.path.join(SAVES, name + ".d2s")
    s = bytearray(open(p, "rb").read())
    i = bytes(s).find(b"Woo!")
    for (diff, q), w in quests.items():
        struct.pack_into("<H", s, i + 10 + diff * 96 + q * 2, w)
    s = bytearray(_checksum(bytes(s)))
    open(p, "wb").write(bytes(s))
    sp = os.path.join(SAVES, name + ".d2rl")
    r = bytearray(open(sp, "rb").read())
    struct.pack_into("<I", r, 0x34, struct.unpack_from("<I", s, 12)[0])
    struct.pack_into("<I", r, 0x38, len(s))
    r[0x3c:0x5c] = hashlib.sha256(bytes(s)).digest()
    r[0x0c:0x2c] = hashlib.sha256(bytes(r[0x2c:])).digest()
    open(sp, "wb").write(bytes(r))


def H(cmd, timeout=15):
    """One harness gameplay command (plugin/src/harness_cmds.cpp): (ok, lines). No mouse, no keyboard."""
    guard()
    return g.hcmd(cmd, timeout)


def kv(line):
    return {k: v for k, v in re.findall(r"(\w+)=(\S+)", line)}


def hstate():
    """`h state` parsed: player dict, items (dicts), mons, objs, plugin counters, npc menu."""
    ok, lines = H("state")
    st = {"ok": ok, "player": {}, "items": [], "mons": [], "corpses": [], "objs": [], "plugin": "", "menu": {}, "lines": lines}
    for ln in lines:
        if ln.startswith("player "):
            st["player"] = {k: (int(v) if re.fullmatch(r"-?\d+", v) else v) for k, v in kv(ln).items()}
        elif ln.startswith("item "):
            st["items"].append({k: (int(v) if re.fullmatch(r"-?\d+", v) else v) for k, v in kv(ln).items()})
        elif ln.startswith("mon "):
            mon = {k: int(v) for k, v in kv(ln).items() if re.fullmatch(r"-?\d+", v)}
            lm = re.search(r"life=(\d+)/(\d+)", ln)
            if lm:
                mon["life"], mon["maxlife"] = int(lm.group(1)), int(lm.group(2))
            st["mons"].append(mon)
        elif ln.startswith("corpse "):  # dead monsters (mode 0 / 12) near the player
            st["corpses"].append({k: int(v) for k, v in kv(ln).items() if re.fullmatch(r"-?\d+", v)})
        elif ln.startswith("obj "):
            st["objs"].append({k: int(v) for k, v in kv(ln).items() if re.fullmatch(r"-?\d+", v)})
        elif ln.startswith("plugin "):
            st["plugin"] = ln
        elif ln.startswith("npcmenu "):
            st["menu"] = {k: int(v) for k, v in kv(ln).items()}
    p = st["player"]
    if isinstance(p.get("x"), int) and isinstance(p.get("y"), int) and p.get("area") is not None:
        prev = STATE.get("last_pos")  # every real move goes on the search walk's map, fights' moves too (walk_map_link)
        if prev and prev[0] == p["area"] and max(abs(prev[1] - p["x"]), abs(prev[2] - p["y"])) <= 20:
            walk_map_link(p["area"], prev[1:], (p["x"], p["y"]))
        STATE["last_pos"] = (p["area"], p["x"], p["y"])
    return st


def items(st, code, page=None):
    return [i for i in st["items"] if str(i.get("code")) == code and (page is None or i.get("page") == page)]


def ensure_cube():
    """The cube checks put items in the Horadric Cube (`item <code> cube`), which fails with "placing failed" when the
    character carries no cube (a fresh test character does not; an earlier check that removed it leaves none): give it one."""
    if not items(hstate(), "box"):
        H("item box inv")


def ground_count(code):
    """Items of this code lying on the ground (`h dump ground` lists every item unit; mode 3 / 5 = on the ground): the quest
    bonus drops land there (one per player)."""
    ok, lines = H("dump ground")
    return len([l for l in lines if l.startswith("ground ") and ("code=%s " % code) in l and re.search(r"mode=[35] ", l)])


def stat_of(lines):
    m = re.search(r"= (-?\d+)", lines[0]) if lines else None
    return int(m.group(1)) if m else None


def player_dead(p):
    """The server's player unit is dead: mode 0 / 17, or life 0."""
    life = str(p.get("life", "1")).split("/")[0]
    return p.get("mode") in (0, 17) or life == "0"


def revive_if_dead(timeout=20):
    """A dead test character (player mode 0 / 17) closes the game on `cheat goto` and ignores hits, menus and hiring. Returns True
    when it was dead.
    Two kinds of death. A real one (life 0, the client shows the death state): Esc is the respawn request (the plugin holds it
    back for 5 s), pressed every 3 s. A harness-made one: a check that sets the life stat (`stat player 6`) after the character
    died leaves the server unit in mode 17 with life above 0 while the client believes the character is alive (a screenshot shows
    it standing, Esc opens the pause menu instead and `state` stops answering for 15 s); no respawn request can come from the
    client then. Save and Exit + Play loads the character in the town, which is what a respawn does."""
    p = hstate()["player"]
    if not p or not player_dead(p):
        return False
    life = str(p.get("life", "0")).split("/")[0]
    g.log("the test character is dead (mode %s, life %s)" % (p.get("mode"), life))
    if life == "0":
        t0 = time.time()
        while time.time() - t0 < timeout:
            g.press("esc")
            time.sleep(3)
            st = hstate()
            if not st["player"]:  # `state` does not answer: Esc paused the game (the character was not dead for the client)
                break
            if not player_dead(st["player"]):
                return True
    p = hstate()["player"]
    if p and not player_dead(p):
        return True
    g.log("no respawn request is possible (the client does not know the death): Save and Exit + Play")
    leave_and_reenter(menu_open=not hstate()["player"])  # `state` silent: the pause menu is already open
    return True
def held_item():
    """(unit id, code) of the item on the player's cursor, None when the cursor is empty."""
    ok, lines = H("cursor")
    m = re.search(r"cursor id=(\d+) code=(\S+)", " ".join(lines))
    return (int(m.group(1)), m.group(2)) if m else None


def release_held_item():
    """An item held on the cursor makes the server unit busy (0x4249f0): skill casts are refused (`cast` code 1: no cast
    animation, no mana, no missile), an NPC click opens no menu, left clicks drop the item instead of attacking. A character
    saved while it holds an item (a check that aborted between a lift and a drop) comes back holding it; slot 1's
    MxlBarb did for a whole suite (2026-10-23: cotr, a unique left by an earlier uniquelimits run). Drops it (client packet
    0x17 + id, onto the ground at the player's feet). Returns the (id, code) dropped, None when the cursor was empty, and
    raises when the item cannot be put down."""
    held = held_item()
    if held is None:
        return None
    for _ in range(3):
        H("pkt 17 " + " ".join("%02x" % b for b in struct.pack("<I", held[0])))
        time.sleep(1.0)
        if held_item() is None:
            return held
    raise RuntimeError("the item %d (%s) on the cursor cannot be dropped" % held)


def right_panel_open():
    """The inventory (or stash / cube) panel is open: the dark-red banner of the right-hand panel, 1600 x 900 client (0.09 of the
    pixels of that strip; 0.00 on every scene screenshot of earlier runs, 0.04 for a cube-only panel)."""
    full = g.grab_client(g.need_window()).convert("RGB")
    px = list(full.crop((840, 100, 1260, 160)).getdata())
    if sum(1 for r, gr, b in px if r > 50 and r > 2 * gr and r > 2 * b) > 0.03 * len(px):
        return True
    # D2R-XL 2012's HD inventory panel has no red banner: its red close button at (1476-1494, 94-112) is 0.23 red with the
    # panel open, 0.0 without (lane rulescheck, slot 3); the banner test above never fired on this mod
    return close_button_red(full) > 0.1


def close_button_red(im):
    px = list(im.crop((1476, 94, 1494, 112)).getdata())
    return sum(1 for r, gr, b in px if r > 120 and r > 2 * gr and r > 2 * b) / max(1, len(px))


def close_right_panel():
    """Closes the inventory panel with the `i` key when the banner shows (a toggle, so only when it is open). Returns True when it
    was open. A panel on the right half moves the player to the left of the screen: every check that clicks at the player's
    projected position (monster hover) and the Save and Exit path miss their targets."""
    if not right_panel_open():
        return False
    g.press("i")
    time.sleep(1.0)
    if right_panel_open():
        g.press("esc")  # a stash or cube panel: one Esc closes it and the inventory with it
        time.sleep(0.8)
    return True


def clean_start_state(label, report_dead=False):
    """The state a check needs the test character to be in: alive, in its own shape, nothing on the cursor. Repairs what it can and
    returns the notes of what it repaired (an empty list when the character was clean); a state it cannot repair raises. Called before
    the first check and before every check (the check that leaves a state behind shows up as the row of the next one)."""
    notes = []
    if revive_if_dead() and report_dead:  # a check that kills the character on purpose (deathcrash) is revived silently
        notes.append("the character was dead (revived)")
    try:  # a check that left the character at 1 life point (soak run 2026-10-25, slot 3: scrollportals before monhover) lets the next monster kill it
        if label.startswith("rp_"):  # not before a player-path check: no life is ever set there
            raise StopIteration
        life, top = rd("player", 6), rd("player", 7)
        if top and life is not None and life < top // 2:
            setstat("player", 6, top)
            notes.append("life was %d of %d points (set to full)" % (life >> 8, top >> 8))
    except StopIteration:
        pass
    except Exception as e:
        g.log("start state before %s: life test failed: %r" % (label, e))
    held = release_held_item()
    if held:
        notes.append("item %d (%s) was held on the cursor (dropped; it blocks skill casts and NPC menus)" % held)
    try:
        if close_right_panel():
            notes.append("the inventory panel was open (closed with `i`; it covers the right half of the client)")
    except Exception as e:  # no window grab: the check that needs the screen will say so
        g.log("start state before %s: panel test failed: %r" % (label, e))
    try:  # what the character wears: a check that leaves an item on shows up as the row of the next one (it changes mana, masteries, resistances)
        worn = sorted("%s@%s" % (it.get("code"), it.get("body")) for it in hstate()["items"] if it.get("page") == 255 and it.get("body"))
        if STATE.get("worn") is not None and worn != STATE["worn"]:
            notes.append("worn items changed since the check before: %s -> %s" % (STATE["worn"], worn))
        STATE["worn"] = worn
    except Exception as e:
        g.log("start state before %s: worn test failed: %r" % (label, e))
    if notes:
        g.log("start state before %s: %s" % (label, "; ".join(notes)))
    return notes




def goto(area, timeout=40):
    """Move the character to an area: the harness `level` first (the waypoint warp inside an act, the NPC travel across acts,
    bug #5), D2R's own `cheat goto` (debug mode, same act) as the fallback. Waits until `h state` says so."""
    revive_if_dead()
    st = hstate()
    if st["player"].get("area") == area:
        return st
    for attempt in range(2):
        if attempt == 0:
            H("level %d" % area)
        else:
            enable_debug()
            con("cheat goto %d" % area)
        time.sleep(3)  # no second travel while one loads (it can hang the game)
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(2)
            st = hstate()
            if st["player"].get("area") == area:
                time.sleep(2)
                return st
    return hstate()


def wait_menu(timeout=60):
    """The NPC menu opens when the NPC's speech has played; returns the `menu list` lines or None."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        guard()
        ok, lines = g.hcmd("menu list", 5)
        if ok:
            return lines
        time.sleep(3)
    return None


def npc_menu(npc_class, spawn=True, attempts=4):
    """Stand next to an NPC (spawn it when it is not loaded), talk, wait for the menu. Returns the menu lines.
    The menu opens when the NPC's speech has played, and the click that starts the speech can be lost (the first talk of a long
    speech, an NPC that is still walking, an earlier menu still open): every attempt closes what is open, talks again and waits
    a shorter time; a dead character (it cannot talk) is revived first."""
    revive_if_dead()
    for attempt in range(attempts):
        close_menu()
        ok, lines = H("interact %d" % npc_class)  # the town's own NPC: its speech ends with the menu
        if not ok and spawn:
            H("spawn %d" % npc_class)
            time.sleep(1)
            ok, lines = H("interact %d" % npc_class)
        if not ok:
            time.sleep(2)
            continue
        menu = wait_menu(30 if attempt == 0 else 15)
        if menu is not None:
            return menu
    return None


def npc_within(npc_class, reach=6):
    """True when an NPC of that class stands within `reach` of the character (`h state` lists the units around it)."""
    near = [m for m in hstate()["mons"] if m.get("class") == npc_class]
    return bool(near) and near[0].get("dist", 99) <= reach


def npc_menu_near(npc_class, attempts=3):
    """npc_menu() for NPCs that stand far from the town's arrival point (Gheed, Charsi, Akara: 70+ units, the walk of an `interact`
    can take longer than the menu wait or end at a wall): walk next to the NPC first (`moveto`, repeated), a copy of the NPC next
    to the character when the walk does not get there, then talk; when the menu still does not open the whole round is repeated
    with a copy (the client has to learn a new unit before it can talk to it). Returns the menu lines or None."""
    revive_if_dead()
    if hstate()["player"].get("area") != 1:
        goto(1)
    close_menu()
    for attempt in range(attempts):
        for _ in range(5):
            ok, _l = H("moveto nearest %d" % npc_class)
            if not ok:
                break  # not loaded
            time.sleep(4)
            if npc_within(npc_class):
                break
        if not npc_within(npc_class) or attempt > 0:
            H("spawn %d" % npc_class)  # out of reach (behind a wall) or not loaded: a copy next to the character
            time.sleep(4)
        menu = npc_menu(npc_class, attempts=2)
        if menu is not None:
            return menu
    return None


def close_menu():
    g.hcmd("menu cancel", 5)


def kill_all_near():
    for _ in range(6):
        ok, _l = H("kill nearest")
        if not ok:
            break


class Result:
    def __init__(self, name, status, note, shots=(), log=()):
        self.name, self.status, self.note, self.shots, self.log = name, status, note, list(shots), list(log)
RESULTS = []


def add(name, status, note, shots=(), log=()):
    RESULTS.append(Result(name, status, note, shots, log))
    g.log("CHECK %s: %s %s" % (name, status, note))


def sh(name):
    return os.path.basename(g.shot(name))


def need_game():
    if not STATE["in_game"]:
        return False
    st = hstate()
    return st["ok"]


def rd(ref, stat, layer=None):
    """Value of a stat of player / merc / mon:<id> (the base the checks restore afterwards)."""
    _, lines = H("stat %s %d%s" % (ref, stat, (" %d" % layer) if layer is not None else ""))
    return stat_of(lines)


def setstat(ref, stat, value, layer=None):
    H("stat %s %d%s set %d" % (ref, stat, (" %d" % layer) if layer is not None else "", value))


def leave_and_reenter(menu_open=False, difficulty="normal"):
    """Esc menu -> Save and Exit -> character select -> Play (the same character, in `difficulty`). `menu_open`: the pause menu
    is already up."""
    if not menu_open:
        g.key("esc")
        time.sleep(1.5)
    left = False
    for attempt in range(3):  # a click the game did not take (seen once in a full group1 run) is repeated: first on the open menu, then with a new Esc
        if attempt == 2:
            g.key("esc")
            time.sleep(1.5)
        g.click(*g.UI["save_exit"])
        time.sleep(9)
        for _ in range(8):  # the save of a character with a long session behind it takes longer than 9 s
            if not g.in_game():
                break
            time.sleep(3)
        left = not g.in_game()
        if left:
            break
    STATE["in_game"] = False
    if not left:  # the click did not leave the game (a dead character has no pause menu): the game goes on
        STATE["in_game"] = True
        return False
    time.sleep(2)
    return enter_game(difficulty=difficulty)
import json  # noqa: E402


def _setskill(skill, level):
    """`setskill`: the base level the game's own point function stopped at."""
    for _ in range(2):
        ok, lines = H("setskill %d %d" % (skill, level))
        m = re.search(r"base level (-?\d+)", " ".join(lines))
        if m:
            return int(m.group(1))
        time.sleep(1)
    return None


def graphics_mode():
    """'legacy' when the capture is pillarboxed (legacy graphics draw 4:3 with black side bars), else 'hd'. Only reliable in a lit
    area (the town): in a dark cave HD's own edges are black too."""
    import numpy as np
    a = grab()
    h, w, _ = a.shape
    bars = np.concatenate([a[:, : w // 10], a[:, w - w // 10:]], axis=1)
    return "legacy" if float(bars.mean()) < 6.0 else "hd"


def set_graphics(mode, tries=3):
    """G toggles legacy / HD graphics (a posted key, background mode). Call it in the town (see graphics_mode)."""
    for _ in range(tries):
        if graphics_mode() == mode:
            return True
        g.press_bg("g", hold=0.1)
        time.sleep(4.0)
    return graphics_mode() == mode


def write_report(extra=""):
    p = os.path.join(g.current_run(), "report.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write("# Game checks (background input, harness commands) %s\n\n" % os.path.basename(g.current_run()))
        f.write("| Check | Result | Note | Evidence |\n|---|---|---|---|\n")
        for r in RESULTS:
            f.write("| %s | %s | %s | %s |\n" % (r.name, r.status, r.note.replace("|", "/"), ", ".join(r.shots)))
        f.write("\n" + extra + "\n")
        for r in RESULTS:
            if r.log:
                f.write("\n### log: %s\n\n```\n%s\n```\n" % (r.name, "\n".join(x[:230] for x in r.log)))
    g.log("report " + p)
    return p


def lock(wait_s=1800):
    """The slot's run lock (tools/game_slots.py): wait, retry every 30 s."""
    t0 = time.time()
    while True:
        ok, msg = g.game_slots.acquire(g.SLOT, g.LOCK_OWNER)
        if ok:
            return True
        if time.time() - t0 > wait_s:
            g.log("slot %d: %s; giving up" % (g.SLOT, msg))
            return False
        g.log("slot %d lock is held (%s), waiting 30 s" % (g.SLOT, msg))
        time.sleep(30)


def unlock():
    g.game_slots.release(g.SLOT, g.LOCK_OWNER)


def card_on_list(name, card):
    """The character's card; off the visible list its OWN save files get the newest time first, so the list shows it as card 1."""
    if card is None or card_y(card) is not None:
        return card
    now = time.time()
    import glob
    for f in glob.glob(os.path.join(SAVES, glob.escape(name) + ".*")):
        os.utime(f, (now, now))
    new = card_of(name)
    g.log("%s was off the character list (card %s); its own saves touched, now card %s" % (name, card, new))
    return new


def enter_initial_character():
    """An explicit lane character must never fall back to the selected save."""
    if not os.environ.get("MXL_CHAR"):
        return enter_game()
    card = card_of(g.CHAR_NAME)
    if card is None:
        return create_character(os.environ.get("MXL_CHAR_CLASS") or "barbarian", g.CHAR_NAME)  # a new lane character's class
    card = card_on_list(g.CHAR_NAME, card)
    if card_y(card or 0) is None or not enter_game(card):
        return False
    want = save_class(g.CHAR_NAME)
    got = hstate()["player"].get("class")
    if want is not None and got != want:  # another character is in the game: no check may touch it
        g.log("the game plays class %s, %s is class %s: leaving without a check" % (got, g.CHAR_NAME, want))
        STATE["in_game"] = False
        return False
    return True


def save_class(name):
    """Class byte (+0x18) of a character save of the slot, None when there is none."""
    try:
        with open(os.path.join(SAVES, name + ".d2s"), "rb") as f:
            head = f.read(0x19)
        return head[0x18] if len(head) > 0x18 else None
    except OSError:
        return None


# ---------------------------------------------------------------- Median XL 2012 checks (docs/plugin-plan.md section 10.1)
# Row, skill and level numbers are the built tables' (after tools/idmap.py). Every check FAILs on a new crash file, a new engine
# assert in d2rloader.log (except the known open ones below), an `h: ... FAIL crashed` line or a `mxl2012-core: ... FAILED` line.

EXCEL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "work", "mod", "data", "global", "excel")
CLASSES = ["amazon", "sorceress", "necromancer", "paladin", "barbarian", "druid", "assassin"]  # `h state` class, d2s +0x18
KNOWN_ASSERTS = {"uniqueItemsTbl": "bug #7",  # open bugs owned by another lane: reported in the note, not a FAIL
                 "nDirectionIndex < nDirections": "bugs #54/#73 (srvdofunc 15, masked right after the assert)",
                 "nListNo < TARGET_LISTNO_MAX_REGULAR": "bug #270 (srvdo 119 from hit 23: 1.14d skips the same list add silently)",
                 "s_StatsPool.IsEmpty()": "exit-only pool leak check at Save and Exit (docs/testing.md: ignore)",
                 "AssetCache": "bug #72 (D2R's asset cache fills up in a long launch)",
                 "ptCreate->hSource": "bug #394 (not a bug: D2R logs and makes no missile, as 1.14d makes none; lane hsource394)"}
_TABLES = {}


def table(name):
    """A built table (work/mod, what install_mod.py put into the slot) as a list of dicts."""
    if name not in _TABLES:
        import csv
        with open(os.path.join(EXCEL, name + ".txt"), encoding="latin-1", newline="") as f:
            _TABLES[name] = list(csv.DictReader(f, delimiter="\t"))
    return _TABLES[name]


def missile_id(name):
    for r in table("missiles"):
        if r["Missile"] == name:
            return int(r["*ID"])
    return None


def row_of(name, key, value):
    return next((r for r in table(name) if r.get(key) == str(value)), None)


def engine_mark():
    return {"loader": g._size(g.LOADER_LOG), "mxl": g._size(g.MXL_LOG),
            "crashes": set(os.listdir(g.CRASH_DIR)) if os.path.isdir(g.CRASH_DIR) else set()}


def engine_asserts(mark):
    """[(message, location)] of the engine asserts d2rloader.log got since the mark."""
    text = g._read_from(g.LOADER_LOG, mark["loader"]) or ""
    msgs = re.findall(r"\| Message : (.*?)\s*\|\s*$", text, re.M)
    locs = re.findall(r"\| Location: (.*?)\s*\|\s*$", text, re.M)
    return list(zip(msgs, locs + [""] * (len(msgs) - len(locs))))


def engine_issues(mark, lines=()):
    """What makes any check FAIL, since the mark: (blocking issues, notes about known open asserts)."""
    bad, known = [], []
    for msg, loc in engine_asserts(mark):
        tag = next((b for k, b in KNOWN_ASSERTS.items() if k in msg), None)
        (known if tag else bad).append("%s%s (%s)" % ("%s: " % tag if tag else "", msg[:90], loc.split("\\")[-1]))
    mx = g._read_from(g.MXL_LOG, mark["mxl"]) or ""
    bad += ["log: " + ln.strip()[:120] for ln in mx.splitlines() if "mxl2012-core" in ln and "FAILED" in ln]
    crashes = set(os.listdir(g.CRASH_DIR)) if os.path.isdir(g.CRASH_DIR) else set()
    bad += ["crash file %s" % c for c in sorted(crashes - mark["crashes"])]
    bad += ["harness: " + ln for ln in lines if "FAIL crashed" in ln]
    return bad, known


def finish(name, ok, note, mark, shots=(), log=(), partial=None):
    """add() with the engine verdict folded in: FAIL on a new assert / crash, PARTIAL when `partial` names what was not judged."""
    log = list(log)
    bad, known = engine_issues(mark, log)
    if known:
        note += "; known open asserts: %s" % ", ".join(sorted(set(known)))
    if bad:
        return add(name, "FAIL", note + "; ENGINE: " + "; ".join(bad[:6]), shots, log)
    status = "PASS" if ok and not partial else ("PARTIAL" if ok else "FAIL")
    add(name, status, note + ("; not judged: " + partial if partial else ""), shots, log)


def Hl(cmd, log, timeout=15):
    """H() that keeps the lines for the check's log."""
    ok, lines = H(cmd, timeout)
    log.append("h %s -> %s" % (cmd, "OK" if ok else "FAIL"))
    log.extend("   " + ln for ln in lines)
    return ok, lines


def first(lines, pattern, group=1, cast=int):
    for ln in lines:
        m = re.search(pattern, ln)
        if m:
            return cast(m.group(group))
    return None


class Tank:
    """Life and mana high enough for a check (a level-1 test character dies to a summoned uber in a second; Rock Shock costs 40
    mana, Soulshatter / Blackstorm 200); the base values come back at the end."""
    STATS = ((7, 30000), (6, 30000), (9, 5000), (8, 5000))

    def __enter__(self):
        self.saved = [(s, rd("player", s)) for s, _ in self.STATS]
        for s, v in self.STATS:
            setstat("player", s, v << 8)
        return self

    def __exit__(self, *a):
        for s, v in self.saved:
            if v is not None:
                setstat("player", s, v)
        return False


class Level:
    """The character level stat (12) raised for a check (skills with a level requirement); the old value comes back at the end."""

    def __init__(self, level):
        self.level = level

    def __enter__(self):
        self.saved = rd("player", 12)
        setstat("player", 12, self.level)
        return self

    def __exit__(self, *a):
        if self.saved is not None:
            setstat("player", 12, self.saved)
        return False


def learn(skill_id, level=1, depth=0):
    """`setskill` with the skill's prerequisites first (skills.txt reqskill1-3 name rows); returns the base level reached."""
    r = row_of("skills", "*Id", skill_id)
    for k in ("reqskill1", "reqskill2", "reqskill3"):
        name = (r or {}).get(k)
        req = next((x for x in table("skills") if x["skill"] == name), None) if name else None
        if req and depth < 8:
            learn(int(req["*Id"]), 1, depth + 1)
    return _setskill(skill_id, level)


def click_unit(mon_id, button="left"):
    """A background click on a monster's spot: the player stands at (800, 405) of the 1600 x 900 HD client and one subtile is
    about 27 px along x - y and 13.5 px along x + y (measured in Blood Moor, slot 2, 2026-10-28). False when the monster is
    not near."""
    st = hstate()
    p = st["player"]
    m = next((m for m in st["mons"] if m.get("id") == mon_id), None)
    if m is None:
        return False
    dx, dy = m["mx"] - p["x"], m["my"] - p["y"]
    g.click((800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5) / 900, button=button)
    return True


def player_xy():
    p = hstate()["player"]
    return p.get("x", 0), p.get("y", 0)


def missiles_seen(lines):
    """{class: count} of the `missiles` summary line."""
    m = first(lines, r"seen=\d+\+? tracking=.*?\[(.*)\]", cast=str) or ""
    return {int(c): int(n) for c, n in re.findall(r"class (\d+) x(\d+)", m)}


def wall_calls(lines):
    return first(lines, r"client wall calls=(\d+)")


def save_classes():
    """{class id: newest character name} of the slot's saves (class byte at +0x18, docs/save-format.md)."""
    import glob
    out = {}
    for f in sorted(glob.glob(os.path.join(SAVES, "*.d2s")), key=os.path.getmtime, reverse=True):
        with open(f, "rb") as fh:
            b = fh.read(0x20)
        if len(b) > 0x18:
            out.setdefault(b[0x18], os.path.splitext(os.path.basename(f))[0])
    return out


def be_class(class_id):
    """Play a character of that class (Save and Exit, then its card; made when the slot has none)."""
    name = save_classes().get(class_id) or "Mxl2" + CLASSES[class_id][:3].capitalize()
    return switch_character(name, CLASSES[class_id], class_id)


def check_mxl2012():
    """Console `mxl2012`: version line, every v0.1 part on, no FAILED install, no other plugin, no build number / image stamp."""
    mark = engine_mark()
    if not need_game():
        return add("mxl2012", "BLOCKED", "not in a game")
    txt = mxl_text()
    lines = txt.splitlines()
    want = [("version line", r"^mxl2012-core \d+\.\d+\.\d+ \(dev\) \| game: Diablo II: Resurrected 3\.3, engine changes on"),
            ("environment ok", r"^environment ok"),
            ("pluginguard", r"^pluginguard ok: no conflicting plugin in the game"),
            ("cltdo22", r"^cltdo22 cltdofunc 113 client wall"),
            ("cltdostub", r"^cltdostub empty slots skipped: missile client do 14 of 91, server hit 10 of 71"),
            ("cltnomis", r"^cltnomis cltdofunc 30 curse without client missile; cltstfunc 18 start without client missile"),
            ("melttrail", r"^melttrail state 22 without a list skill makes 1\.14d's trail \(missile 143, skill 173\)"),
            ("whirlwind", r"^whirlwind srvdofunc 76 hits as 1\.13c .*0x56ac00 hooked\)"),
            ("cubedupe", r"^cubedupe on: a second useitem output copies output a"),
            ("ilvl", r"^ilvl item levels 100-127 kept by the item serializer \(clamp 99 -> 127 at 0x37d744\)$"),
            ("runeletter", r"^runeletter on: rune letters without a D2R key drawn from the gems cell"),
            ("skilltext", r"^skilltext skill tooltip labels in 1\.13c's words \(0x287a50 hooked\)"),
            ("dursync", r"^dursync worn items' durability loss reaches the client \(layer argument stored whole at 0x441c4b\)$"),
            ("other plugins", r"^other plugins: none")]
    missing = [n for n, p in want if not any(re.search(p, ln) for ln in lines)]
    failed = [ln for ln in lines if "FAILED" in ln]
    leak = [ln for ln in lines if re.search(r"0x6ab3782c|93847", re.sub(r"[A-Za-z]:\\\S+", "<path>", ln))]
    ok = not missing and not failed and not leak
    finish("mxl2012", ok, "%d lines; missing %s; FAILED %s; build number / stamp outside a path %s; line 1: %s" % (
        len(lines), missing or "none", failed or "none", leak or "none", lines[0][:110] if lines else "-"), mark, [sh("mxl2012")], lines)


def check_cltdostub():
    """`missilescan` 0 rows on an empty slot (client hit 0 = no function, bug #8); stuckarrow / footprint (pCltDoFunc 0) fly."""
    mark = engine_mark()
    log = []
    _, scan = Hl("missilescan", log, 30)
    cdo = first(scan, r"missilescan: (\d+) rows call an empty client do slot")
    chit = first(scan, r"missilescan: (\d+) rows call an empty client hit slot")
    srv = first(scan, r"missilescan: (\d+) rows call an empty server hit slot")
    goto(2)
    _, s0 = Hl("state", log)
    stubs0 = first(s0, r"client do (\d+), server hit")
    for row in (83, 84):
        Hl("missile %d" % row, log)
    time.sleep(3)
    _, s1 = Hl("state", log)
    stubs1 = first(s1, r"client do (\d+), server hit")
    mx = g._read_from(g.MXL_LOG, mark["mxl"]) or ""
    logged = [ln.strip()[:140] for ln in mx.splitlines() if re.search(r"row 8[34]\b", ln)]
    log += ["mxl2012-core.log: " + ln for ln in logged]
    ok = (cdo, chit, srv) == (0, 0, 0)
    finish("cltdostub", ok, "missilescan rows on an empty client do / client hit / server hit slot: %s / %s / %s; rows 83 and 84 fired, "
           "stub client do counter %s -> %s; log lines naming the rows: %d" % (cdo, chit, srv, stubs0, stubs1, len(logged)),
           mark, [sh("cltdostub")], log)


def check_rockshock():
    """Rock Shock (28) / ParasiteSkill (480) on client do 113 (CltDoWall): table, `cltdo`, and a real cast at a monster."""
    mark = engine_mark()
    log = []
    _, l22 = Hl("slot cltdo 22", log)
    _, l113 = Hl("slot cltdo 113", log)
    slot_ok = any("plugin" in ln for ln in l113)
    direct = {}
    Hl("state", log)  # the client verbs need the player id the server frame saw
    for sk in (28, 480):
        ok, ln = Hl("cltdo %d" % sk, log)
        direct[sk] = ok and any("cltdofunc=113" in x and "entry=plugin" in x and "wall calls +1" in x for x in ln)
    rock = missile_id(row_of("skills", "*Id", 28)["srvmissilea"])
    owners = [r["Id"] for r in table("monstats") if "ParasiteSkill" in [r.get("Skill%d" % i) for i in range(1, 9)]]
    goto(2)
    seen, wall_delta, life_drop, srv_seen = {}, None, None, {}
    with Tank():
        Hl("setskill 28 1", log)
        px, py = player_xy()
        _, sp = Hl("spawn 5 1 %d %d" % (px + 2, py - 1), log)
        mon = first(sp, r"id=(\d+)")
        # server-side cast (the harness `cast`): the server half; the game runs no client function of the local player for it
        Hl("missiles reset", log)
        Hl("cast 28 unit %s" % mon, log)
        time.sleep(2.5)
        _, ms = Hl("missiles", log)
        srv_seen = missiles_seen(ms)
        # the real path: Rock Shock on the left button, a background click on the zombie (the client runs cltdofunc 113)
        Hl("skill left 28", log)
        _, s0 = Hl("state", log)
        w0 = wall_calls(s0)
        life0 = first(s0, r"mon id=%s class=5 .*?life=(\d+)/" % mon)
        Hl("missiles reset", log)
        for _ in range(3):
            if not click_unit(int(mon)):
                break
            time.sleep(2.0)
        _, ms = Hl("missiles", log)
        seen = missiles_seen(ms)
        _, s1 = Hl("state", log)
        life1 = first(s1, r"mon id=%s class=5 .*?life=(\d+)/" % mon)
        wall_delta = (wall_calls(s1) or 0) - (w0 or 0)
        life_drop = None if life0 is None else life0 - (life1 if life1 is not None else 0)
        shot = sh("rockshock_cast")
        if mon:
            H("kill %s" % mon)
    real = rock in seen and wall_delta > 0
    note = ("slot cltdo 22: %s; slot cltdo 113: %s; cltdo 28 / 480 -> CltDoWall: %s / %s; client cast (left click on a zombie, Blood Moor): missile "
            "rockshock (%s) seen %s, client wall calls +%s, monster life lost %s (server-side `cast`: rockshock seen %s); monsters "
            "owning ParasiteSkill: %s" % (
                first(l22, r"slot cltdo 22: (\S+)", cast=str), first(l113, r"slot cltdo 113: (\S+)", cast=str), direct[28], direct[480],
                rock, seen.get(rock, 0), wall_delta, life_drop, srv_seen.get(rock, 0), owners or "none (no mcast)"))
    finish("rockshock", slot_ok and direct[28] and direct[480] and real, note, mark, [shot], log,
           partial=None if owners else "mcast of ParasiteSkill (no monster owns it); the section 2.1 controls and the look need the owner's eyes")


class Mana:
    """Mana raised for a check (Soulshatter costs 200); life is left as it is (the player path: no god mode)."""
    STATS = ((9, 5000), (8, 5000))

    def __enter__(self):
        self.saved = [(s, rd("player", s)) for s, _ in self.STATS]
        for s, v in self.STATS:
            setstat("player", s, v << 8)
        return self

    def __exit__(self, *a):
        for s, v in self.saved:
            if v is not None:
                setstat("player", s, v)
        return False


# the oskills the checks wear on a Dagger (Grade 1) (`142`, no requirement): Median gives them by Cornerstone jewels
# (uniqueitems.txt oskill rows); stat 97 (item_nonclassskill) with the skill as its layer
OSKILLS = {"Titan Strike": 8, "Soulshatter": 18, "Mana Sweep": 546, "Bloodspeakers Mark": 658, "Feral Strike": 783}


def wear_oskills(log, code="142"):
    """A weapon (default the dagger) with the oskills in the right hand (the old right- and left-hand items are taken off). True
    when worn. Bloodspeakers Mark needs a spear (itypea1 spea): `137`, Spear (Grade 1)."""
    Hl("unequip rhand", log)
    Hl("unequip lhand", log)
    ok, _ = Hl("equip %s normal " % code + " ".join("97:%d=1" % i for i in OSKILLS.values()) + " rhand", log)
    return ok


def watched(log):
    """(calls, non-zero returns, last second argument) of `watch`."""
    _, ln = Hl("watch", log)
    m = next((re.search(r"calls=(\d+) nonzero=(\d+) last=(-?\d+)", x) for x in ln if "calls=" in x), None)
    return tuple(int(v) for v in m.groups()) if m else (None, None, None)


def zombie_near(log, dx=3):
    px, py = player_xy()
    _, sp = Hl("spawn 5 1 %d %d" % (px + dx, py), log)
    return first(sp, r"id=(\d+)")


def mon_life(mon):
    return first(hstate()["lines"], r"mon id=%s class=\d+ .*?life=(\d+)/" % mon) if mon else None


def use_three_ways(sk, log, slot_cmd, wait=1.8, target=None):
    """The skill used three ways on a fresh zombie each: background left clicks, background right clicks (the player path) and the
    harness' server-side `cast <id> unit` (the game's own cast-on-unit function, whose skill packet goes back to the client). Per
    way: clicks / casts, the watched slot's calls, non-zero returns, last argument, server missiles and the zombie's life.
    `target`: a function that makes the unit to use it on instead (its id)."""
    out = {}
    for way in ("left", "right", "server"):
        mon = target(log) if target else zombie_near(log)
        if way != "server":
            Hl("skill %s %d" % (way, sk), log)
        Hl(slot_cmd, log)
        Hl("missiles reset", log)
        life0 = mon_life(mon)
        n = 0
        for _ in range(3):
            if not mon:
                break
            if way == "server":
                c, _ = Hl("cast %d unit %s" % (sk, mon), log)
            else:
                c = click_unit(int(mon), button=way)
            n += 1 if c else 0
            time.sleep(wait)
        calls, made, last = watched(log)
        _, ms = Hl("missiles", log)
        out[way] = {"n": n, "calls": calls, "made": made, "last": last, "seen": missiles_seen(ms), "life": (life0, mon_life(mon))}
        if mon:
            H("kill %s" % mon)
    Hl("watch off", log)
    return out


def ways_text(res):
    return "; ".join("%s: %s" % (n, ", ".join("%s %s uses, calls %s, with missiles %s (last %s), server missiles %s, target life %s" % (
        w, r["n"], r["calls"], r["made"], r["last"], r["seen"], r["life"]) for w, r in ways.items())) for n, ways in res.items())


def check_cltdo83():
    """Client do 83 (lane triage): Titan Strike 8 (no cltmissile), Soulshatter 18 (cltmissile coupdegracebomb) and Mana Sweep 546
    (cltmissile sweepcenter), each learnt with `setskill` where the game gives the point (else the dagger's oskill), used by
    background left clicks, right clicks and the server-side cast on a zombie; `watch cltdo 83` counts the calls of the slot's own
    entry and the calls that made client missiles (D2R 0x2b25e0 = 1.14d 0x4f2fe0 returns 1 after its missiles, 0 without a client
    missile or a target unit). Controls on client do 19: Aerials Disaster (learnt) and Bloodspeakers Mark (oskill). Known limits
    (runs 3-7, 2026-10-28): an oskill clicked runs the client's previously selected skill (the client follows `skill left|right` only
    for a skill in its own list), so oskills never reach their slot here; Soulshatter starts only on the player's own pet
    (srvstfunc 3 = Unsummon's start, TargetPet), so at a zombie it does nothing; Mana Sweep is a sorceress skill (`setskill` refused on
    the barbarian). The server-side cast reaches no client do at all (the cltdo 19 control too). PASS: the slot is D2R's 0x2b25e0,
    Titan Strike reaches it and makes no missile (as 1.14d), and a cltmissile skill reaches it with missiles; PARTIAL without the
    last."""
    mark = engine_mark()
    log = []
    _, sl = Hl("slot cltdo 83", log)
    entry = first(sl, r"slot cltdo 83: (\S+)", cast=str)
    rets = {}
    for sk in (8, 18, 546):
        ok, ln = Hl("cltdo %d" % sk, log)
        rets[sk] = first(ln, r"returned=(-?\d+)") if ok else "FAIL"
    goto(2)
    res, ctrl, how = {}, {}, {}
    with Mana(), Level(30):
        worn = wear_oskills(log)  # the dagger: Soulshatter's weapon type (knif); the oskills are a fallback
        # learnt first (`setskill`): the client follows the harness' `skill left|right` only for a skill in its own list; an
        # oskill cast by a click runs the client's previously selected skill (run 3: last 351), so the slot is never reached
        for name in ("Titan Strike", "Soulshatter", "Mana Sweep"):
            sk = OSKILLS[name]
            how[name] = "setskill" if _setskill(sk, 1) else "oskill"
            res[name] = use_three_ways(sk, log, "watch cltdo 83")
        shots = [sh("cltdo83")]
        # controls on client do 19: Aerials Disaster (351, barbarian, learnt) and Bloodspeakers Mark (658, the spear's oskill)
        if learn(351):
            ctrl["Aerials Disaster (learnt)"] = use_three_ways(351, log, "watch cltdo 19")
        if wear_oskills(log, "137"):
            ctrl["Bloodspeakers Mark (oskill)"] = use_three_ways(658, log, "watch cltdo 19", wait=2.0)
    best = {n: max(ways.values(), key=lambda r: ((r["calls"] or 0), (r["made"] or 0))) for n, ways in res.items()}
    with_mis = [n for n in ("Soulshatter", "Mana Sweep") if (best[n]["made"] or 0) >= 1 and best[n]["last"] == OSKILLS[n]]
    titan = best["Titan Strike"]
    base = (entry == "exe+0x2b25e0" and worn and all(v != "FAIL" for v in rets.values()) and (titan["calls"] or 0) >= 1 and
            titan["made"] == 0 and titan["last"] == 8)
    note = "slot cltdo 83: %s; `cltdo` without a target returned %s; dagger worn: %s; %s; controls: %s" % (
        entry, rets, worn, ways_text({"%s (%s)" % (n, how[n]): w for n, w in res.items()}), ways_text(ctrl) or "none")
    # PASS needs a cltmissile skill's missiles too; with Titan Strike alone the slot is reached and right, the rest PARTIAL
    finish("cltdo83", base, note, mark, shots, log, partial=None if with_mis else
           "no skill with a cltmissile reached the slot (Soulshatter / Mana Sweep: see the per-way lines)")


def check_srvhit23():
    """Server hit 23 (lane triage): Bloodspeakers Mark (658, srvdofunc 11, itypea1 spea) as an oskill of a worn spear, used by
    background left clicks, right clicks and the server-side cast on a zombie; its bolt `bloodspeakerbolt` (1393, sHitPar1 119)
    hits, hit 23 (D2R 0x4533c0 = 1.14d 0x5acfc0) runs skill server do 119 (summon) with the missile's skill and level:
    Bloodspeakers Mark's `bloodspeakerpet` appears (petmax 1). `watch srvhit 23` counts the hits. `leapingjumper` (2241, sHitPar1
    27) is fired by no Median skill or missile (only the harness `missile` reaches it). srvdo 119 has no petmax test in either game
    (D2R 0x575990 = 1.14d 0x5c7390; petmax is a start-function rule), so every hit adds a pet. PASS: the hits reach the slot, the
    last is 1393, pets made, no new assert (#270 is D2R's assert on the list add 1.14d skips silently)."""
    mark = engine_mark()
    log = []
    _, sl = Hl("slot srvhit 23", log)
    entry = first(sl, r"slot srvhit 23: (\S+)", cast=str)
    pet = next((i for i, r in enumerate(table("monstats")) if r.get("Id") == "bloodspeakerpet"), None)
    bolt = missile_id("bloodspeakerbolt")
    goto(3)
    with Mana(), Level(30):
        worn = wear_oskills(log, "137")
        pets0 = {m.get("id") for m in hstate()["mons"] if m.get("class") == pet}
        res = {"Bloodspeakers Mark": use_three_ways(658, log, "watch srvhit 23", wait=2.0)}
        st = hstate()
        log += ["   " + ln for ln in st["lines"] if ln.startswith("mon ")]
        new_pets = [m for m in st["mons"] if m.get("class") == pet and m.get("id") not in pets0]
        shot = sh("srvhit23")
        # leapingjumper: the harness fires the unused row once (no skill or missile of Median's tables names it)
        Hl("watch srvhit 23", log)
        Hl("missile %d 6 0" % missile_id("leapingjumper"), log)
        time.sleep(2.5)
        jcalls, _, jlast = watched(log)
        Hl("watch off", log)
        for m in new_pets:
            H("kill %d" % m["id"])
    ways = res["Bloodspeakers Mark"]
    hit = [w for w, r in ways.items() if (r["calls"] or 0) >= 1 and r["last"] == bolt]
    ok = entry == "exe+0x4533c0" and worn and hit and len(new_pets) >= 1
    finish("srvhit23", ok, "slot srvhit 23: %s; spear with the oskills worn: %s; %s; bloodspeakerbolt = %s; new bloodspeakerpet (class %s) "
           "alive at the end: %d; leapingjumper fired by the harness: hit 23 calls %s (last %s)" % (
               entry, worn, ways_text(res), bolt, pet, len(new_pets), jcalls, jlast), mark, [shot], log)


def town_portals():
    return [o for o in hstate()["objs"] if o.get("class") in (59, 60)]


def check_frenzy():
    """Skill server do 109 -> 9 and start 64 / (37, 109) -> 67 (engine-triage #1 / #2, lane triage): D2R's 109 opens a town portal
    ("Townportal O Skill"), 1.13c's was the frenzy attack. Feral Strike (783, the dagger's oskill) by background left clicks on a
    zombie, then a Thorn Hulk's MonFrenzy (215) at the player and a Blood Lord's BloodLordFrenzy (268): the hits land (life drops),
    no town portal appears, no assert."""
    mark = engine_mark()
    log, parts, good = [], [], True
    goto(2)
    with Tank(), Level(30):  # Tank: the Thorn Hulk / Blood Lord hits must land on a live player
        worn = wear_oskills(log)
        mon = zombie_near(log)
        Hl("skill left 783", log)
        tp0 = len(town_portals())
        life0 = first(hstate()["lines"], r"mon id=%s class=5 .*?life=(\d+)/" % mon) if mon else None
        clicks = 0
        for _ in range(3):
            if not mon or not click_unit(int(mon)):
                break
            clicks += 1
            time.sleep(1.6)
        st = hstate()
        life1 = first(st["lines"], r"mon id=%s class=5 .*?life=(\d+)/" % mon) if mon else None
        hit = life0 is not None and (life1 is None or life1 < life0)
        tp = len(town_portals()) - tp0
        good = good and worn and clicks > 0 and hit and tp == 0
        parts.append("Feral Strike: %d clicks, zombie life %s -> %s, new town portals %d" % (clicks, life0, life1, tp))
        if mon:
            H("kill %s" % mon)
        modes = {"A1": 6, "A2": 7, "SC": 9, "S1": 10}
        for cls_name, skill, name in (("thornhulk1", 215, "MonFrenzy"), ("bloodlord1", 268, "BloodLordFrenzy")):
            ms = table("monstats")
            cls = next((i for i, r in enumerate(ms) if r.get("Id") == cls_name), None)
            row = ms[cls] if cls is not None else {}
            k = next((i for i in range(1, 9) if row.get("Skill%d" % i) == name), None)
            mode = modes.get(row.get("Sk%dmode" % k, ""), 6) if k else 6
            px, py = player_xy()
            _, sp = Hl("spawn %s 1 %d %d" % (cls, px + 2, py), log)
            mid = first(sp, r"id=(\d+)")
            tp0 = len(town_portals())
            plife0 = hstate()["player"].get("life")
            casts = 0
            for _ in range(3):
                c, _ = Hl("mcast %d %d unit %s" % (skill, mode, mid), log) if mid else (False, [])
                casts += 1 if c else 0
                time.sleep(1.2)
            plife1 = hstate()["player"].get("life")
            tp = len(town_portals()) - tp0
            good = good and casts > 0 and tp == 0
            parts.append("%s (%s, class %s, mode %d): %d casts taken, player life %s -> %s, new town portals %d" % (
                name, cls_name, cls, mode, casts, plife0, plife1, tp))
            if mid:
                H("kill %s" % mid)
            revive_if_dead()
    finish("frenzy", good, "; ".join(parts), mark, [sh("frenzy")], log)


def srvhit6_rows():
    """(built row, Median 2012 row, Median sHitPar1, built sHitPar1, sHitPar2) of the four rows the spec names."""
    spec = [(1388, 1330, 1107), (1668, 1610, 1222), (1671, 1613, 1221), (1359, 1301, 1)]
    out = []
    for row, mrow, mpar in spec:
        r = row_of("missiles", "*ID", row)
        out.append((row, mrow, mpar, int(r["sHitPar1"]), int(r["sHitPar2"] or 0)))
    return out


def check_srvhit6spawn():
    """Hit-6 spawners (D2R's hit 6 spawns sHitPar1 as a monster, sHitPar2 = the mode): the idmapped class, one per hit; a mode-0 row
    (demon seed on ground) leaves a corpse (bug #11)."""
    mark = engine_mark()
    log = []
    goto(4)  # Stony Field: the unkillable dark_kid stays there, away from the other checks' levels
    results, alive = [], []
    with Tank():
        for row, mrow, mpar, par1, par2 in srvhit6_rows():
            before = hstate()
            ids0 = {m.get("id") for m in before["mons"] + before["corpses"]}
            Hl("missile %d 4 0" % row, log)
            time.sleep(3)
            after = hstate()
            log += ["   " + ln for ln in after["lines"] if ln.startswith(("mon ", "corpse "))]
            new_live = [m for m in after["mons"] if m.get("id") not in ids0 and m.get("class") == par1]
            new_dead = [m for m in after["corpses"] if m.get("id") not in ids0 and m.get("class") == par1]
            stray = [m for m in after["mons"] + after["corpses"] if m.get("id") not in ids0 and m.get("class") == mpar and mpar != par1]
            right = new_dead if par2 == 0 else new_live
            ok_dump, _ = Hl("dump mon %d" % par1, log)
            results.append((row, mrow, mpar, par1, par2, len(right), len(stray), len(right) == 1 and not stray and ok_dump))
            alive += [m["id"] for m in new_live]
        shot = sh("srvhit6spawn")
        kills = []
        for mid in alive:
            ok, ln = H("kill %d" % mid)
            kills.append("%d:%s" % (mid, "dead" if ok else (first(ln, r"(left class \d+ alive)", cast=str) or "FAIL")))
    note = "; ".join("row %d (Median %d, sHitPar1 %d -> %d, sHitPar2 %d): %d %s of class %d%s" % (
        row, mrow, mpar, par1, par2, n, "corpse" if par2 == 0 else "live", par1, ", %d of the unmapped class" % s if s else "")
        for row, mrow, mpar, par1, par2, n, s, _ in results)
    finish("srvhit6spawn", all(r[-1] for r in results), note + "; kill: " + ", ".join(kills), mark, [shot], log)


def check_cltnomis():
    """Bug #6: D2R's client curse (cltdofunc 30) and client start 18 assert (SkillsNec.cpp) for a row without a client missile.
    Controls first (D2R's own functions past the wrappers raise the assert), then the table entries (no assert), then the case
    the bug was seen in: monsters of the hit-6 summoners fighting zombies for 25 s."""
    log = []
    Hl("state", log)
    res = {}
    for cmd in ("cltst 551 orig", "cltdo 551 1 orig", "cltst 551", "cltdo 551"):
        m = engine_mark()
        ok, _ = Hl(cmd, log)
        time.sleep(0.5)
        a = [x for x in engine_asserts(m) if "nMissile" in x[0]]
        res[cmd] = (ok, len(a), a[0][1].split("\\")[-1] if a else "")
    controls_ok = res["cltst 551 orig"][1] > 0 and res["cltdo 551 1 orig"][1] > 0
    tables_ok = res["cltst 551"][1] == 0 and res["cltdo 551"][1] == 0 and res["cltst 551"][0] and res["cltdo 551"][0]
    mark = engine_mark()  # the controls raise asserts on purpose: the engine is judged from here on
    goto(4)
    with Tank():
        px, py = player_xy()
        Hl("spawn 5 3 %d %d" % (px + 4, py), log)
        Hl("missile 1668 4 0", log)  # dark_kid
        Hl("missile 1671 4 0", log)  # edyrems
        time.sleep(25)
        Hl("state", log)
        natural = [x for x in engine_asserts(mark) if "nMissile" in x[0]]
        skips = first(mxl_text().splitlines(), r"calls skipped (\d+)")
        shot = sh("cltnomis")
    note = "; ".join("%s: %s, nMissile asserts %d %s" % (k, "OK" if v[0] else "FAIL", v[1], v[2]) for k, v in res.items())
    note += "; summoned dark_kid / edyrems + 3 zombies 25 s: nMissile asserts %d; wrapper calls skipped %s" % (len(natural), skips)
    finish("cltnomis", controls_ok and tables_ok and not natural, note, mark, [shot], log)


def blackstorm_signals():
    """Resolve Blackstorm's state and missiles from the installed build's tables."""
    skill = row_of("skills", "*Id", 514)
    names = {v for k, v in skill.items() if k.startswith(("srvmissile", "cltmissile")) and v}
    missiles = {r["Missile"]: int(r["*ID"]) for r in table("missiles")
                if r.get("Skill") == skill["skill"] or r["Missile"] in names}
    state = row_of("states", "state", skill["aurastate"])
    return int(state["*ID"]), missiles


def blackstorm_observed(prg, states, seen, state_id, missile_ids):
    """Slot 28 reaching skill 514, its state, or one of its missiles is sufficient."""
    return bool((prg[0] and prg[0] > 0 and prg[2] == 514)
                or state_id in states or any(seen.get(v, 0) for v in missile_ids.values()))


def check_skillprog():
    """Batstrike (326, assassin: srvprg 22/119/51, cltprg 25, progressive charges) and Blackstorm (514, paladin: cltprg 28)."""
    mark = engine_mark()
    log, parts, shots, good, blocked = [], [], [], True, []
    for cid, skill, label in ((6, 326, "Batstrike"), (3, 514, "Blackstorm")):
        if not be_class(cid):
            parts.append("%s: could not play a %s" % (label, CLASSES[cid]))
            good = False
            continue
        if skill == 326:  # Batstrike needs a claw (itypea1 h2h): `j20`, worn by the harness (its equip update reaches the
            # client at once since bug #391's fix: no Save and Exit + Play)
            setstat("player", 0, 1000)
            setstat("player", 2, 1000)
            Hl("unequip rhand", log)
            Hl("unequip lhand", log)
            Hl("equip j20 rhand", log)
        goto(2)
        with Mana(), Level(30):  # mana only (Blackstorm costs 200): no god mode for the verdict (owner rule)
            got = learn(skill)
            px, py = player_xy()
            Hl("spawn 5 4 %d %d" % (px + 3, py), log)
            Hl("missiles reset", log)
            charges, casts, states = [], 0, set()
            state_id, blackstorm_missiles = blackstorm_signals() if skill == 514 else (None, {})

            def prog():
                return tuple(rd("player", s) or 0 for s in (318, 320, 321, 322, 323))

            def zombie():
                zs = sorted((m for m in hstate()["mons"] if m.get("class") == 5), key=lambda m: m.get("dist", 99))
                return zs[0]["id"] if zs else None
            # the client progression function (cltprgfunc1 25 / 28 index the skill client do table) counted on its slot
            Hl("watch cltdo %d" % (25 if skill == 326 else 28), log)
            if skill == 326:  # Batstrike: four hits charge it (left clicks, the player path; else server-side casts), then
                # the finishing skill Attack (0) releases
                Hl("skill left %d" % skill, log)
                for _ in range(4):
                    z = zombie()
                    c = z is not None and click_unit(z)
                    if not c:
                        c, _ = Hl("cast %d nearest 5" % skill, log)
                    casts += 1 if c else 0
                    time.sleep(1.6)
                    charges.append(prog())
                Hl("skill left 0", log)  # skills.txt finishing: Attack, used the way a player does (left click on the zombie)
                for _ in range(4):
                    z = zombie()
                    if z is None or not click_unit(z):
                        break
                    time.sleep(1.5)
                    charges.append(prog())
                    if not any(charges[-1]):
                        break
            else:  # Blackstorm: right button only (no leftskill), periodic; cast by right clicks next to a zombie
                selected, _ = Hl("skill right %d" % skill, log)
                for _ in range(4 if selected else 0):  # an unset right button + a right click raises `ptSkill` (bug #9)
                    z = zombie()
                    if z is not None and click_unit(z, button="right"):
                        casts += 1
                    time.sleep(1.8)
                    charges.append(prog())
                    states.update(server_states(log))
                if not selected:
                    c, _ = Hl("cast %d" % skill, log)  # the server-side cast on the spot, for the record
                    blocked.append("%s: the game selects it on no button (`skill right %d` refused) and refuses the server-side cast (%s)" % (
                        label, skill, "taken" if c else "code 1"))
            _, ms = Hl("missiles", log)
            seen = missiles_seen(ms)
            prg = watched(log)
            Hl("watch off", log)
            shots.append(sh("skillprog_%s" % label.lower()))
            mis = [row_of("skills", "*Id", skill).get(k) for k in ("srvmissile", "srvmissilea", "srvmissileb")]
            mis_ids = {m: missile_id(m) for m in mis if m}
            if skill == 514:
                mis_ids = blackstorm_missiles
            kill_all_near()
        fired = any(seen.get(v, 0) for v in mis_ids.values())
        if skill == 514:
            fired = blackstorm_observed(prg, states, seen, state_id, mis_ids)
            parts.append("Blackstorm state %s seen %s" % (state_id, state_id in states))
        good = good and casts == 4 and fired
        parts.append("%s: setskill base level %s, %d of 4 casts%s, progressive stats 318/320-323 after each %s, skill missiles %s "
                     "seen %s, all seen %s; client prg slot %d calls %s (non-zero %s, last skill %s)" % (
                         label, got, casts, " (+ Attack clicks until released)" if skill == 326 else " (right clicks)", charges, mis_ids,
                         {k: seen.get(v, 0) for k, v in mis_ids.items()}, seen, 25 if skill == 326 else 28, prg[0], prg[1], prg[2]))
    finish("skillprog", good, "; ".join(parts), mark, shots, log,
           partial="; ".join(blocked + ["the client progression visuals (cltprg 25 / 28) need eyes on the screenshots"]))


def find_waypoint_object():
    ids = {int(r["*ID"]) for r in table("objects") if r.get("OperateFn") == "23" and r.get("*ID", "").isdigit()}
    _, ln = H("objects")
    for x in ln:
        m = re.search(r"object id=(\d+) class=(\d+) mode=(\d+) dist=(\d+)", x)
        if m and int(m.group(2)) in ids:
            return int(m.group(1)), int(m.group(2)), int(m.group(4))
    return None


def check_pandewp():
    """Pandemonium 2 (134) has NO waypoint object, as in 1.13c: the server's room preset loop (1.14d 0x5559a0, D2R 0x48f2de) skips
    object class 402 (WaypointDesertValley, the Valley's KingWarp.ds1 centre) in level 134 (bug #13). Median's levels.txt row keeps
    the Valley's waypoint number 17 from the copied row, so bit 17 is the Valley's: set by number it reads 1 in the Valley."""
    mark = engine_mark()
    log = []
    goto(109, timeout=60)  # Harrogath (NPC travel across acts), then the waypoint warp's arrival at Pande 2's waypoint spot (kind 13)
    for s_, v in ((7, 60000), (6, 60000)):  # Median's uber Duriel stands at the arrival point
        setstat("player", s_, v << 8)
    Hl("level 134 warp 13", log)
    time.sleep(8)
    st = hstate()
    area = st["player"].get("area")
    if area != 134:
        return finish("pandewp", False, "could not reach Pandemonium 2 (area %s after `level 134 warp 13`)" % area, mark,
                      [sh("pandewp_travel")], log)
    shots = [sh("pandewp_arrived")]
    Hl("waypoint n 17 clear", log)
    wp = find_waypoint_object()
    _, l402 = Hl("objects 402", log)
    n402 = first(l402, r"objects (\d+)")
    log.append("waypoint object: %s; class 402 objects: %s" % (wp, n402))
    Hl("waypoint n 17 set", log)  # what the Valley's waypoint does; Pande 2 has none to operate
    st = goto(46, timeout=60)
    _, ln = Hl("waypoint n 17 get", log)
    valley = first(ln, r"= (\d)")
    Hl("waypoint open", log)
    time.sleep(2)
    shots.append(sh("pandewp_valley_panel"))
    g.key("esc")
    time.sleep(1)
    in_valley = st["player"].get("area") == 46
    goto(1, timeout=60)
    ok = in_valley and valley == 1 and wp is None and n402 == 0
    finish("pandewp", ok, "arrived in 134 by the waypoint warp (kind 13); waypoint object (objects.txt OperateFn 23) %s, class 402 objects "
           "%s (1.13c: none, the preset loop skips 402 in level 134); Valley reached: %s, bit 17 there: %s" % (
               wp, n402, in_valley, valley), mark, shots, log, partial="the Valley's panel list (screenshot)")


TEXT_MONSTERS = ["quest_crystal", "quest_icedemon", "couatlfather1", "couatlfather2", "bunny", "injuredbarb1", "boneprison1",
                 "dark_kid"]  # monstats Ids (lane text): the former raw names, the blank bone prison, the description line.
# `crusaders` (Crusader Spirit, AI NecroPet) is left out: a harness spawn without an owner raises bug #19's assert
TEXT_ITEMS = ["hpo", "rps", "0g3", "0g6"]  # misc codes: two beta potions, two Greater Elixirs (PotFireReloadedDesc / PotPoisReloadedDesc)
INV_CELL = (1049, 393, 44, 42)  # HD inventory grid of the 1600 x 900 client (measured on the mod's panel): left, top, cell w, cell h
INV_BUTTONS = [("close", 1484, 103), ("gold", 1160, 668)]  # tooltips that were `@strClose` / `@strGoldDrop`


def hover(fx, fy):
    """Move the virtual cursor (a client-area fraction) without clicking: the game draws the hover label / tooltip."""
    g.click(fx, fy, move_only=True)
    time.sleep(1.0)


def hover_px(x, y):
    hover(x / 1600, y / 900)


def hover_unit(mon_id, dy_px=0):
    st = hstate()
    p = st["player"]
    m = next((m for m in st["mons"] if m.get("id") == mon_id), None)
    if m is None:
        return False
    dx, dy = m["mx"] - p["x"], m["my"] - p["y"]
    hover((800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5 + dy_px) / 900)
    return True


def check_textnames():
    """docs/text-audit.md: the names that used to show their key (monsters hovered in the Rogue Encampment, a monster with a
    blank name, a monster with the new description line), item names and the Greater Elixir line in the inventory, the inventory's
    Close / Drop Gold tooltips that were `@key`s. Judged by eye from the screenshots (REVIEW)."""
    mark = engine_mark()
    log, shots = [], []
    enable_debug()
    cheat("god 1")
    goto(1, timeout=60)
    ids = {r["Id"]: int(r["*hcIdx"]) for r in table("monstats") if r.get("Id") in TEXT_MONSTERS}
    seen = []
    for name in TEXT_MONSTERS:
        cls = ids.get(name)
        if cls is None:
            log.append("%s: not in the built monstats" % name)
            continue
        Hl("spawn %d" % cls, log)
        time.sleep(2.5)
        mon = next((m for m in hstate()["mons"] if m.get("class") == cls), None)
        if mon is None:
            log.append("%s (class %d): not in the unit list after spawn" % (name, cls))
            continue
        for k, off in enumerate((0, -22, 22)):  # the body of a stand-in sprite is not where its feet are
            ok = hover_unit(mon["id"], off)
            shots.append(sh("text_mon_%s_%d" % (name, k)))
        seen.append("%s=%s" % (name, "hovered" if ok else "no unit"))
        Hl("kill nearest %d" % cls, log)
        time.sleep(1.0)
    cells = {}
    for code in TEXT_ITEMS:
        _, ln = Hl("item %s inv" % code, log)  # the verb answers `item id=.. code=.. page=0 x=<cell> y=<cell> ..`
        x, y = first(ln, r" x=(\d+) y="), first(ln, r" y=(\d+) quality")
        if x is not None and y is not None:
            cells[code] = (x, y)
    g.press("i")
    time.sleep(1.5)
    shots.append(sh("text_inventory"))
    for code, (cx, cy) in cells.items():
        left, top, cw, ch = INV_CELL
        hover_px(left + (cx + 0.5) * cw, top + (cy + 0.5) * ch)
        shots.append(sh("text_item_%s" % code))
    for name, x, y in INV_BUTTONS:
        hover_px(x, y)
        shots.append(sh("text_inv_%s" % name))
    g.press("i")
    time.sleep(1.0)
    finish("textnames", True, "monsters hovered: %s; items spawned %s; %d screenshots" % (", ".join(seen), ", ".join(TEXT_ITEMS), len(shots)),
           mark, shots, log, partial="the names and lines on the screenshots are read by hand")


def check_terrorzones():
    """No terror zone: idle in a field level (MXL_TZ_MINUTES, default 3), `state` every minute; no terror / tremor / herald line."""
    mark = engine_mark()
    log = []
    goto(2)
    minutes = int(os.environ.get("MXL_TZ_MINUTES", "3"))
    for _ in range(minutes):
        time.sleep(60)
        Hl("state", log)
        revive_if_dead()
    words = re.compile(r"terror|tremor|desecrat|herald", re.I)
    hits = [ln.strip()[:140] for p, off in ((g.LOADER_LOG, mark["loader"]), (g.MXL_LOG, mark["mxl"]))
            for ln in (g._read_from(p, off) or "").splitlines() if words.search(ln) and "Excel file" not in ln and "reused" not in ln]
    json_in = os.path.exists(os.path.join(g.GAME_DIR, r"mods\mxl2012\mxl2012.mpq\data\hd\global\excel\desecratedzones.json"))
    finish("terrorzones", not hits and json_in, "%d min in Blood Moor; the mod's desecratedzones.json installed: %s; terror / tremor / "
           "herald lines: %s" % (minutes, json_in, hits or "none"), mark, [sh("terrorzones")], log + hits)


def check_classes():
    """One character per class the account allows (Warlock needs Reign of the Warlock: not on this account)."""
    mark = engine_mark()
    made = []
    for cid, cls in enumerate(CLASSES):
        if cid not in save_classes() and be_class(cid):
            made.append(cls)
    have = save_classes()
    missing = [CLASSES[c] for c in range(7) if c not in have]
    finish("classes", not missing, "characters: %s; made now: %s; missing: %s; Warlock skipped (account without RotW)" % (
        ", ".join("%s=%s" % (CLASSES[c], n) for c, n in sorted(have.items()) if c < 7), made or "none", missing or "none"), mark)

ELIXIRS = [("0g3", "passive_fire_mastery"), ("0g4", "passive_cold_mastery"), ("0g5", "passive_ltng_mastery"), ("0g6", "passive_pois_mastery")]
ELIXIR_CONTROL = ("0g1", "item_magicbonus")  # Greater Elixir of Greed: its state `magpot` exists, it works in the original


def stat_id(name):
    r = row_of("itemstatcost", "Stat", name)
    return int(r["*ID"]) if r else None


def inventory_count(code, log):
    """Items of this code in the player's inventory (`items` lists every item the player carries; `state` does not)."""
    _, ln = Hl("items", log)
    return len([l for l in ln if l.startswith("item ") and ("code=%s " % code) in l])


def server_states(log):
    """The states the server's player unit has (`states player`): the numbers of the `server state N:` lines."""
    _, ln = Hl("states player", log)
    return sorted(int(m.group(1)) for l in ln for m in [re.match(r"server state (\d+):", l)] if m)


def check_elixirs():
    """Bug #104, owner 2026-10-28 'match the original': the Greater Elixirs of Strength / Dexterity / Energy / Vitality (`0g3`-`0g6`) as
    Median XL 2012 v005 ran them. Their misc rows name states (`strpot` ...) that states.txt does not have and description keys no .tbl
    defines, so the original (1.14d Game.exe 0x5beda0 / 0x4863a8 stand in for 1.13c) shows NO description line and the use does nothing:
    the item stays, no state, no stat. The control `0g1` (Greater Elixir of Greed, state `magpot`) is drunk and used up, with its state.
    Each elixir is put into the inventory, hovered (screenshot: name only, no effect line), right-clicked (the player's own use path),
    then the item count, the elixir's stat and the player's states are compared with before."""
    mark = engine_mark()
    log, shots, rows = [], [], []
    enable_debug()
    cheat("god 1")
    goto(1, timeout=60)
    for code, stat in ELIXIRS + [ELIXIR_CONTROL]:
        sid = stat_id(stat)
        if sid is None:
            rows.append((code, False, "stat %s not in the built itemstatcost" % stat))
            continue
        s0 = rd("player", sid)
        st0 = server_states(log)
        _, ln = Hl("item %s inv" % code, log)
        cx, cy = first(ln, r" x=(\d+) y="), first(ln, r" y=(\d+) quality")
        if cx is None or cy is None:
            rows.append((code, False, "item not placed in the inventory"))
            continue
        n0 = inventory_count(code, log)
        g.press("i")
        time.sleep(1.5)
        left, top, cw, ch = INV_CELL
        px, py = left + (cx + 0.5) * cw, top + (cy + 0.5) * ch
        hover_px(px, py)
        shots.append(sh("elixir_%s_tip" % code))
        g.click(px / 1600, py / 900, button="right")  # use it, as a player does
        time.sleep(2.0)
        shots.append(sh("elixir_%s_used" % code))
        n1 = inventory_count(code, log)
        s1 = rd("player", sid)
        st1 = server_states(log)
        g.press("i")
        time.sleep(1.0)
        gained = sorted(set(st1) - set(st0))
        kept = n1 == n0 and s1 == s0 and not gained
        used = n1 == n0 - 1 and gained and (s1 or 0) > (s0 or 0)
        rows.append((code, kept if code != ELIXIR_CONTROL[0] else bool(used),
                     "%s: %s; items of the code %d -> %d; stat %s %s -> %s; new states %s" % (
                         code, "used up" if n1 < n0 else "kept", n0, n1, stat, s0, s1, gained or "none")))
    ok = all(r[1] for r in rows) and len(rows) == len(ELIXIRS) + 1
    finish("elixirs", ok, "; ".join(r[2] if len(r) > 2 else r[0] for r in rows) + "; expected: the four Greater Elixirs do nothing (item kept, no stat, no state), "
           "the control is used up with its state", mark, shots, log,
           partial="the tooltips (name only, no description line) are read by hand from the screenshots")


def check_melttrail():
    """Bug #52 (lane melttrail): Median's `raptured` (state 22) units leave 1.14d's melt trail while they walk: missile 143
    `spidergoolay` (Median's IceBreakSmallMelt) one step off (the step table's direction), level = the unit's skill 173 (plugin part melttrail,
    melt_trail.cpp). Paladin with Rapture: a control walk without the state (no trail), Rapture at a zombie, `states player 22`,
    then the same walk (background ground clicks with Attack on the left button; each step must move the paladin). PASS: the
    client trail counter rises only in state 22, no assert. The server counter and missile 143 are reported, not required: D2R
    (`0x445d20`, slot WL of the monster mode table `0x1d1a200`) and 1.14d (`0x5a8490`, monster mode table `0x6e2264`) run the
    state-22 trail on the server only in a walking MONSTER's step, so a raptured player makes none in either game (lane integ).
    The look of the trail (a light-blue melt behind the paladin, as Median 2012 on 1.13c / 1.14d) is judged from the screenshot."""
    mark = engine_mark()
    log = []
    rap = row_of("skills", "skill", "Rapture")
    goo = missile_id("spidergoolay")
    if rap is None or goo != 143:
        return add("melttrail", "FAIL", "built tables: Rapture row %s, spidergoolay id %s (1.14d's code makes 143)" % (
            rap and rap.get("*Id"), goo))
    rid = int(rap["*Id"])
    if not be_class(3):
        return add("melttrail", "BLOCKED", "could not play a paladin")

    def trails():
        lines = mxl_text().splitlines()
        return (first(lines, r"trails made: client (\d+)") or 0, first(lines, r"trails made: client \d+, server (\d+)") or 0)

    def walk(steps=4):  # 6 subtiles east, then back west (screen offsets as click_unit); the subtiles actually walked
        moved = 0
        for i in range(steps):
            dx, dy = (6, 1) if i % 2 == 0 else (-6, 1)
            a = player_xy()
            g.click((800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5) / 900)
            time.sleep(1.6)
            b = player_xy()
            moved += abs(b[0] - a[0]) + abs(b[1] - a[1])
        log.append("walked %d subtiles" % moved)
        return moved

    goto(2)
    with Tank(), Level(60):
        got = learn(rid)
        Hl("skill left 0", log)
        _, before = Hl("states player 22", log)
        c0 = trails()
        moved0 = walk()
        c1 = trails()
        px, py = player_xy()
        _, sp = Hl("spawn 5 1 %d %d" % (px + 3, py), log)
        mon = first(sp, r"id=(\d+)")
        Hl("skill right %d" % rid, log)
        if mon:
            click_unit(int(mon), button="right")
            time.sleep(1.2)
        Hl("cast %d %s" % (rid, ("unit %s" % mon) if mon else "self"), log)
        time.sleep(1.5)
        _, held = Hl("states player 22", log)
        Hl("missiles reset", log)
        t0 = trails()
        moved1 = walk(6)
        shot = sh("melttrail_walk")
        t1 = trails()
        _, ms = Hl("missiles", log)
        seen = missiles_seen(ms)
        if mon:
            H("kill %s" % mon)
    in22 = any(re.search(r"server state 22: bit=1", ln) for ln in held)
    control = (c1[0] - c0[0], c1[1] - c0[1])
    walked = (t1[0] - t0[0], t1[1] - t0[1])
    ok = in22 and moved0 > 0 and moved1 > 0 and control == (0, 0) and walked[0] > 0
    note = ("Rapture %d level %s; state 22 before: %s, after the cast: %s; walked %d / %d subtiles; trails (client, server) on the control "
            "walk %s, in state 22 %s (server: monsters only, as 1.14d); server missiles seen %s" % (
                rid, got, any("bit=1" in ln for ln in before), in22, moved0, moved1, control, walked, seen))
    finish("melttrail", ok, note, mark, [shot], log, partial="the trail's look (light-blue melt behind the paladin) in the screenshot")


MELT_MONSTER = "elite_zakarumcleric4"  # Median's Zakarum cleric with Rapture (Sk3mode S1, Sk3lvl 4): the walking raptured monster


def check_meltmon():
    """Bug #52 server half (lane fixes3): plugin part melttrail's server hook (`0x578680`) runs in the walking MONSTER's step only
    (D2R `0x445d20`, 1.14d `0x5a8490`). Median's Zakarum cleric (`elite_zakarumcleric4`, has Rapture) is spawned beside a
    paladin and casts Rapture on itself through its AI's skill use (`mcast <Rapture> 8`, mode S1; once more if the state is not there
    after a few seconds); the paladin then walks back and forth (background clicks) so the cleric's Vampire AI follows. PASS:
    state 22 on the monster, the server trail counter rises, missile 143 (`spidergoolay`) made on the server, no assert. Cost:
    20 clerics raptured at once, game frames per second of wall time over the same walk as with the single cleric (reported)."""
    mark = engine_mark()
    log = []
    rap = row_of("skills", "skill", "Rapture")
    cleric = row_of("monstats", "Id", MELT_MONSTER)
    if rap is None or cleric is None or missile_id("spidergoolay") != 143:
        return add("meltmon", "FAIL", "built tables: Rapture %s, %s %s, spidergoolay %s" % (
            rap and rap.get("*Id"), MELT_MONSTER, cleric and cleric.get("*hcIdx"), missile_id("spidergoolay")))
    rid, cls = int(rap["*Id"]), int(cleric["*hcIdx"])
    if not be_class(3):
        return add("meltmon", "BLOCKED", "could not play a paladin")

    def trails():
        return first(mxl_text().splitlines(), r"trails made: client \d+, server (\d+)") or 0

    def frame():
        return hstate()["player"].get("frame", 0)

    def walk(steps):  # 6 subtiles east and back (screen offsets as click_unit), 1.6 s a step
        for i in range(steps):
            dx, dy = (6, 1) if i % 2 == 0 else (-6, 1)
            g.click((800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5) / 900)
            time.sleep(1.6)

    def walk_rate(steps=6):
        f0, t0 = frame(), time.time()
        walk(steps)
        return (frame() - f0) / (time.time() - t0)

    def sturdy(mid):  # the clerics' own Diseased Cattle clouds kill a bunched group in seconds
        for st in (7, 6):
            H("stat mon:%s %d set %d" % (mid, st, 30000 << 8))

    def rapture(mid, polls=4, tries=3):  # the state comes with the cast's frame event; a fresh monster may ignore a use
        for _ in range(tries):
            Hl("mcast %d 8 unit %s at %s" % (rid, mid, mid), log)   # 8 = S1 (monmode row), the cleric's Sk3mode
            for _ in range(polls):
                time.sleep(1.0)
                _, st = Hl("states mon:%s 22" % mid, log)
                if any("bit=1" in ln for ln in st):
                    return True
        return False

    goto(2)
    with Tank():
        H("skill left 0")
        px, py = player_xy()
        Hl("missiles reset", log)
        s0 = trails()   # before the spawn: the cleric's own AI may cast Rapture as soon as it sees the paladin
        _, sp = Hl("spawn %d 1 %d %d" % (cls, px + 8, py + 2), log)
        mon = first(sp, r"id=(\d+)")
        if mon is None:
            return finish("meltmon", False, "could not spawn %s (%d)" % (MELT_MONSTER, cls), mark, (), log)
        sturdy(mon)
        time.sleep(2)
        in22 = rapture(mon)
        base = walk_rate()
        s1 = trails()
        _, ms = Hl("missiles", log)
        seen = missiles_seen(ms)
        shot = sh("meltmon_walk")
        H("kill %s" % mon)
        # cost: 20 clerics; the game frame rate over the same walk before and after Rapture on all of them
        px, py = player_xy()
        _, sp = Hl("spawn %d 20 %d %d" % (cls, px + 10, py - 4), log)
        ids = re.findall(r"id=(\d+)", " ".join(sp))
        for i in ids:   # Rapture right away: a bunched group dies to its own Diseased Cattle clouds within ~10 s
            sturdy(i)
        raptured = sum(rapture(i, polls=1, tries=1) for i in ids)
        c0 = trails()
        hot = walk_rate()
        c1 = trails()
        for i in ids:
            H("kill %s" % i)
    ok = in22 and s1 > s0 and seen.get(143, 0) > 0
    note = ("%s (%d) Rapture %d: state 22 %s, server trails %d -> %d (spawn to the end of the walk), server missiles seen %s; cost: %d of %d "
            "clerics raptured, game frames/s %.1f with one, %.1f with them (%d server trails over that walk)" % (
                MELT_MONSTER, cls, rid, in22, s0, s1, seen, raptured, len(ids), base, hot, c1 - c0))
    finish("meltmon", ok, note, mark, [shot], log)


# ---------------------------------------------------------------- mercenaries and town services (lane mercs2, docs/testing.md)
# Player path, no god mode: the NPC click (`interact`, packet 0x2f), the menu line's own client handler (`menu <n>`), the hire
# button (`hire`, packet 0x36); equipping the mercenary, buying, selling and gambling are background clicks on the panels.
# Fixtures (noted in the result): gold set before each payment, the test items made in the backpack (`item <code> inv`) and
# a few spawned monsters to fight. Item codes are v005's Grade 1 bases (weapons.txt / armor.txt, requirements below a hired
# mercenary's strength and dexterity).
MERC_HIRERS = [  # act, town area, hirer class, name, mercenary monster class
    (1, 1, 150, "Kashya", 271), (2, 40, 198, "Greiz", 338), (3, 75, 252, "Asheara", 359), (5, 109, 515, "Qual-Kehk", 561)]
# 1.13c / v005 hireling.txt WType1 / WType2 per class: Rogue bow; Desert Mercenary polearm, spear; Iron Wolf sword, shield;
# Barbarian sword. (code, body location, allowed, what)
MERC_GEAR = {
    271: [("615", 1, True, "Cap (helm)"), ("600", 3, True, "Quilted Armor"), ("101", 4, False, "Scimitar (sword)"),
          ("l53", 4, False, "Crossbow"), ("164", 4, True, "Short Battle Bow (bow)")],
    338: [("615", 1, True, "Cap (helm)"), ("600", 3, True, "Quilted Armor"), ("164", 4, False, "Short Battle Bow (bow)"),
          ("101", 4, False, "Scimitar (sword)"), ("156", 4, True, "Bardiche (polearm)"), ("137", 4, True, "Spear (spear)")],
    359: [("615", 1, True, "Cap (helm)"), ("600", 3, True, "Quilted Armor"), ("164", 4, False, "Short Battle Bow (bow)"),
          ("137", 4, False, "Spear (spear)"), ("101", 4, True, "Scimitar (sword)"), ("621", 5, True, "Buckler (shield)")],
    561: [("w15", 1, False, "Jawbone Cap (Barbarian helm, a class item)"), ("615", 1, True, "Cap (helm)"),
          ("600", 3, True, "Quilted Armor"), ("115", 4, False, "Axe"), ("621", 5, False, "Buckler (shield)"),
          ("101", 4, True, "Scimitar (sword)")],
}
TOWN_VENDORS = {  # act: (town area, trader class, name, gambler class, name)
    1: (1, 154, "Charsi", 147, "Gheed"), 2: (40, 178, "Fara", 199, "Elzix"), 3: (75, 253, "Hratli", 254, "Alkor"),
    4: (103, 257, "Halbu", 405, "Jamella"), 5: (109, 511, "Larzuk", 512, "Anya")}
# 1600 x 900 HD client, measured on slot 2 2026-10-28 (screenshots merc_panel / trade_panel of the run): the hireling panel (O)
# on the left, the inventory (I) on the right; the vendor / gamble panel replaces the hireling panel.
MERC_SLOT = {1: (0.2125, 0.228), 3: (0.2125, 0.361), 4: (0.114, 0.339), 5: (0.311, 0.339)}
INV_GRID = (1047.0, 393.0, 44.0, 42.0)  # x0, y0, cell width, cell height (px) of the 10 x 6 backpack grid
SHOP_GRID = (135.0, 183.0, 41.0)  # the vendor / gambler grid at 1600 x 900: left, top, cell (10 x 10 cells; measured on trade_hratli.png)
SHOP_DROP = (0.170, 0.420)  # an empty part of the vendor grid: a held item clicked here is sold


def inv_cell(x, y, w=1, h=1):
    x0, y0, cw, ch = INV_GRID
    return (x0 + (x + w / 2.0) * cw) / 1600.0, (y0 + (y + h / 2.0) * ch) / 900.0


def shop_cell(x, y, w=1, h=1):
    x0, y0, c = SHOP_GRID
    return (x0 + (x + w / 2.0) * c) / 1600.0, (y0 + (y + h / 2.0) * c) / 900.0


def item_lines(lines):
    return [{k: (int(v) if re.fullmatch(r"-?\d+", v) else v) for k, v in kv(l).items()} for l in lines if l.lstrip().startswith("item ")]


def merc_info(dead=False):
    """(merc dict, [item dicts]) of `merc`, (None, []) without one."""
    ok, lines = H("merc dead" if dead else "merc")
    if not ok:
        return None, []
    m = next(({k: (int(v) if re.fullmatch(r"-?\d+", v) else v) for k, v in kv(l).items()} for l in lines if l.startswith("merc id=")), None)
    if m is not None:
        lm = re.search(r"life=(\d+)/(\d+)", " ".join(lines))
        if lm:
            m["life"], m["maxlife"] = int(lm.group(1)), int(lm.group(2))
    return m, item_lines(lines)


def gold():
    """Carried plus stash gold: what the game pays a price from."""
    p = hstate()["player"]
    return p.get("gold", 0) + p.get("bank", 0)


def set_gold(n):
    """n gold in all: carried up to the character's cap (level x 10,000; more is thrown away), the rest in the stash."""
    cap = 10000 * max(1, hstate()["player"].get("level", 1))
    setstat("player", 14, min(n, cap))
    setstat("player", 15, max(0, n - cap))


def panels_closed():
    close_menu()
    for _ in range(2):
        g.press("esc")
        time.sleep(0.8)
        if not hstate()["ok"]:  # Esc opened the pause menu: close it again
            g.press("esc")
            time.sleep(0.8)
            break


def talk(npc_class, log):
    """`interact` (the click on the NPC), then the menu once the greeting has played; the menu lines, None when it did not open."""
    for attempt in range(5):
        close_menu()
        ok, lines = Hl("interact %d" % npc_class, log)
        far = first(lines, r"distance ([\d.]+)", cast=float)
        if (not ok or far is None or far > 6) and attempt < 2:  # the real NPC first: the player walks to it, also to an
            acts_approach(npc_class)                             # unloaded one's preset spot (a copy's gamble sold nothing)
            continue
        if not ok or far is None or far > 6:  # not loaded, or no path to it: a copy next to the player
            Hl("spawn %d" % npc_class, log)
            log.append("   fixture: a copy of NPC %d spawned next to the player" % npc_class)
            time.sleep(2)
            continue
        menu = wait_menu(25 if attempt == 0 else 12)
        if menu is not None:
            log.extend("   " + ln for ln in menu)
            return menu
    return None


def menu_lines(menu):
    return [int(m.group(1)) for ln in menu or () for m in [re.search(r"line (\d+) string=", ln)] if m]


MENU_TRADE, MENU_GAMBLE = 0x112f30, 0x112c80  # client handlers of the Trade and Gamble lines (`menu list` handler=image+...)


def menu_line_of(menu, handler):
    """The line whose client handler is `handler` (Halbu's menu has Trade as its only line), None when there is none."""
    for ln in menu or ():
        m = re.search(r"line (\d+) string=0x[0-9a-f]+ handler=image\+0x([0-9a-f]+)", ln)
        if m and int(m.group(2), 16) == handler:
            return int(m.group(1))
    return None


def new_item(code, log):
    """An item of this code in the backpack (a fixture: `item <code> inv`); its line (id, x, y) or None."""
    ok, lines = Hl("item %s inv" % code, log)
    its = [i for i in item_lines(lines) if str(i.get("code")) == code]
    return its[-1] if ok and its else None


def drop_held(log):
    held = held_item()
    if held:
        Hl("pkt 17 " + " ".join("%02x" % b for b in struct.pack("<I", held[0])), log)
        time.sleep(0.8)
    return held


def equip_by_click(code, body, log, shots, tag):
    """Item made in the backpack -> left click on its cell (to the cursor) -> left click on the hireling panel's slot. Returns
    (equipped, note): equipped = the mercenary wears that item id at that body location afterwards."""
    it = new_item(code, log)
    if it is None:
        return None, "the item could not be made"
    w, h = item_size(code)
    g.click(*inv_cell(it["x"], it["y"], w, h))
    time.sleep(0.8)
    held = held_item()
    if not held or held[0] != it["id"]:
        drop_held(log)
        return None, "the click on the backpack cell %s,%s did not pick it up (cursor %s)" % (it["x"], it["y"], held)
    g.click(*MERC_SLOT[body])
    time.sleep(1.2)
    shots.append(sh("merc_%s_%s" % (tag, code)))
    _m, worn = merc_info()
    on = any(i.get("id") == it["id"] and i.get("page") == 255 for i in worn)
    left = drop_held(log)  # a refused item stays on the cursor; an accepted one may hand the old one back (swap)
    return on, "worn" if on else ("refused, back on the cursor (dropped)" if left and left[0] == it["id"] else "not worn, cursor %s" % (left,))


def kill_class(cls, most=12):
    """Harness kills of the spawned fixture monsters of one class only (`kill_all_near` would also kill the mercenary)."""
    for _ in range(most):
        ok, _l = H("kill nearest %d" % cls)
        if not ok:
            break


LEVEL_AREA = 6  # Black Marsh (Act 1): a spawned monster takes the area's level, so a kill is worth more than in Blood Moor.
# Not an area of another act: the harness's cross-act travel `level 110` with a live mercenary crashed the game twice (image+0x1255802).


def level_player(want, log, rows):
    """Kills by the player (Andariel copies in Blood Moor, the game's death function with the player as the killer) until the
    character has `want` levels: Kashya's hire gate in D2R's NPC table is Burial Grounds or level 8."""
    goto(LEVEL_AREA)
    l0 = hstate()["player"].get("level", 0)
    for _ in range(40):
        if hstate()["player"].get("level", 0) >= want:
            break
        H("spawn 5 3")  # zombies of the area's level: experience without killing a low-level mercenary
        time.sleep(0.4)
        for _k in range(3):
            H("kill nearest 5")
        time.sleep(0.4)
    kill_class(5)
    rows.append("player level %s -> %s by kills" % (l0, hstate()["player"].get("level")))


# Hirer gates D2R reads from its NPC table (0x237ea60, byte +0x10 quest + 1, +0x11 level): Kashya the Burial Grounds quest or
# level 8, Greiz and Asheara none, Qual-Kehk Rescue on Mount Arreat and no level. The check sets the quest bits (a fixture).
HIRE_QUEST = {150: (2, 0), 515: (36, 0)}  # the table byte is the quest id + 1 (Kashya 3 = the Burial Grounds quest, quest 2)


def hire_in(act, area, npc, name, cls, log, rows, bad):
    st = goto(area)
    if st["player"].get("area") != area:
        bad.append("act %d: could not reach the town (area %s)" % (act, st["player"].get("area")))
        return None
    panels_closed()
    set_gold(max(gold(), 30000))  # fixture: the hire price (D2R's price function decides it)
    if npc in HIRE_QUEST:
        Hl("quest %d %d set" % HIRE_QUEST[npc], log)
        rows.append("%s: quest %d bit %d set (fixture: the hire gate)" % ((name,) + HIRE_QUEST[npc]))
    g0 = gold()
    menu = talk(npc, log)
    if menu is None:
        bad.append("%s: no menu" % name)
        return None
    # the Hire line is the one whose handler makes the hire list; the list itself is what `hire` reads, its button is packet 0x36
    hired = None
    for n in range(6):
        ok, lines = Hl("hire %d %d reopen" % (npc, n), log)
        if ok:
            hired = lines
            break
        if any("no free entry" in ln for ln in lines):
            break
    close_menu()
    m, _w = merc_info()
    if hired is None or m is None:
        bad.append("%s: no mercenary hired" % name)
        return None
    price = first(hired, r"price=(\d+)")
    rows.append("act %d %s: hired class %s level %s for %s gold (gold %d -> %d)" % (act, name, m.get("class"), m.get("level"), price, g0, gold()))
    if m.get("class") != cls:
        bad.append("%s: mercenary class %s, want %d" % (name, m.get("class"), cls))
    if price is not None and g0 - gold() != price:
        bad.append("%s: paid %d, the price said %d" % (name, g0 - gold(), price))
    return m


def merc_panel_open(log, shots, tag):
    panels_closed()
    g.press("o")
    time.sleep(1.2)
    g.press("i")
    time.sleep(1.2)
    shots.append(sh("merc_panel_%s" % tag))


def fight_and_level(log, rows, bad):
    """Blood Moor: weak monsters spawned next to the mercenary (it fights them), then the player's kills give the mercenary its
    share of experience; the mercenary's level may not pass the player's (1.13c and D2R)."""
    goto(2)
    time.sleep(3)
    for _ in range(20):  # the mercenary follows a few seconds after the area change
        m, _w = merc_info()
        if m:
            break
        time.sleep(1)
    m0, _w = merc_info()
    if not m0:
        bad.append("fight: no mercenary in Blood Moor")
        return
    for _ in range(30):  # it walks over from the town entrance
        if any(x.get("id") == m0["id"] and x.get("dist", 99) <= 8 for x in hstate()["mons"]):
            break
        time.sleep(1)
    p0 = hstate()["player"]
    Hl("spawn 5 4", log)  # zombies (slow melee)
    t0, killed = time.time(), 0
    while time.time() - t0 < 40:
        time.sleep(4)
        st = hstate()
        alive = [x for x in st["mons"] if x.get("class") == 5]
        killed = 4 - len(alive)
        if not alive:
            break
    m1, _w = merc_info()
    rows.append("fight: 4 zombies next to the mercenary, %d dead after %.0f s; mercenary life %s -> %s, exp %s -> %s" % (
        killed, time.time() - t0, m0.get("life"), m1.get("life") if m1 else "-", m0.get("exp"), m1.get("exp") if m1 else "-"))
    if killed == 0:
        bad.append("fight: the mercenary killed none of the 4 zombies in 40 s")
    kill_class(5)
    # experience: the player's kills where monsters are worth it (the mercenary follows and takes its share); its level stays at
    # or below the player's
    level_player(m0.get("level", 1) + 4, log, rows)
    for _ in range(20):
        m2, _w = merc_info()
        if m2 and m2.get("level", 0) > m0.get("level", 0):
            break
        H("spawn 5 3")
        time.sleep(0.4)
        for _k in range(3):
            H("kill nearest 5")
        time.sleep(0.4)
    m2, _w = merc_info()
    p2 = hstate()["player"]
    rows.append("level: player %s -> %s, mercenary %s -> %s (exp %s -> %s)" % (p0.get("level"), p2.get("level"), m0.get("level"),
                                                                             m2.get("level") if m2 else "-", m0.get("exp"), m2.get("exp") if m2 else "-"))
    if not m2 or m2.get("level", 0) <= m0.get("level", 0):
        bad.append("the mercenary did not level up (%s -> %s)" % (m0.get("level"), m2.get("level") if m2 else "-"))
    elif m2["level"] > p2.get("level", 0) + 0:
        bad.append("the mercenary's level %d passed the player's %d" % (m2["level"], p2.get("level", 0)))


def merc_death(log, rows, bad):
    """Monsters that outclass a low-level mercenary fight it until it dies (a harness kill only when that takes over 90 s)."""
    m, _w = merc_info()
    if not m:
        bad.append("death: no mercenary")
        return None
    Hl("spawn 156 3", log)
    t0, how = time.time(), None
    while time.time() - t0 < 90:
        time.sleep(3)
        revive_if_dead()  # the player may die too: it comes back in town, the mercenary stays where it fell
        if merc_info()[0] is None:
            how = "killed by the spawned monsters in %.0f s" % (time.time() - t0)
            break
    if how is None:
        Hl("kill %d" % m["id"], log)
        time.sleep(1)
        how = "the harness kill (the monsters did not finish it in 90 s)"
    kill_class(156)
    dead, _w = merc_info(dead=True)
    rows.append("death: level %s mercenary %s; afterwards: %s" % (m.get("level"), how, "dead" if merc_info()[0] is None else "ALIVE"))
    if merc_info()[0] is not None:
        bad.append("the mercenary did not die")
    return dead or m


def merc_revive(npc, name, area, log, rows, bad):
    goto(area)
    panels_closed()
    _o, lines = Hl("mercprice", log)
    price = first(lines, r"price=(-?\d+)")
    want = first(lines, r"expected113=(-?\d+)")
    level = first(lines, r"level=(\d+)")
    set_gold(max(price or 0, 0) + 5000)  # fixture: enough for the price
    g0 = gold()
    menu = talk(npc, log)
    if menu is None:
        bad.append("revive: %s's menu did not open" % name)
        return
    revived_by = None
    for n in menu_lines(menu)[1:]:  # line 0 is Talk; the Resurrect line's handler revives at once and charges
        Hl("menu %d" % n, log)
        time.sleep(2.5)
        if merc_info()[0] is not None:
            revived_by = n
            break
        panels_closed()
        menu = talk(npc, log)
    close_menu()
    paid = g0 - gold()
    rows.append("revive at %s: menu line %s, price %s for level %s (1.13c formula %s), paid %d" % (name, revived_by, price, level, want, paid))
    if revived_by is None:
        bad.append("revive: no menu line of %s revived the mercenary" % name)
    if price != want:
        bad.append("revive price %s differs from 1.13c's %s" % (price, want))
    if revived_by is not None and paid != price:
        bad.append("revive: paid %d, price %s" % (paid, price))


def vendor_round(act, log, rows, bad, shots):
    """Open the trader's panel, buy one item by right click, sell it back (held item clicked on the vendor grid), then gamble
    one item at the act's gambler (right click on an offer)."""
    area, trader, tname, gambler, gname = TOWN_VENDORS[act]
    st = goto(area)
    if st["player"].get("area") != area:
        bad.append("act %d vendors: could not reach the town" % act)
        return
    panels_closed()
    set_gold(100000)  # fixture
    menu = talk(trader, log)
    if menu is None:
        bad.append("%s: no menu" % tname)
        return
    opened = False
    for _ in range(3):
        n = menu_line_of(menu, MENU_TRADE)
        if n is None:
            break
        Hl("menu %d" % n, log)
        for _w in range(8):  # the panel comes with the server's answer (the first time with the stock made)
            time.sleep(1)
            if trade_panel_open():
                opened = True
                break
        if opened:
            break
        panels_closed()
        menu = talk(trader, log)
    shots.append(sh("trade_%s" % tname.lower()))
    _ok, stock = Hl("shop %d" % trader, log)
    wares = [i for i in item_lines(stock) if i.get("page") in (0, 1, 2, 3, 4)]
    if not opened:
        bad.append("%s: the trade panel did not open (%d stock items)" % (tname, len(wares)))
        close_menu()
        return
    # buy: right click on a 1 x 1 ... 2 x 3 item of the open tab
    g0 = gold()
    _ok, il = H("items")
    ids0 = {i.get("id") for i in item_lines(il)}
    bought = None
    for it in wares[:6]:
        w, h = item_size(str(it.get("code")))
        g.click(*shop_cell(it["x"], it["y"], w, h), button="right")
        time.sleep(1.5)
        if gold() < g0:
            bought = it
            break
    g1 = gold()
    rows.append("act %d %s: trade panel open, %d stock items, buy %s for %d gold" % (act, tname, len(wares), bought.get("code") if bought else "NOTHING", g0 - g1))
    if not bought:
        bad.append("%s: the right clicks bought nothing" % tname)
    else:  # sell it back: the newest backpack item to the cursor, then onto the vendor grid
        _ok, il = H("items")
        mine = [i for i in item_lines(il) if i.get("page") == 0 and i.get("id") not in ids0]
        if not mine:
            bad.append("%s: the bought item is not in the backpack (%d items listed)" % (tname, len(item_lines(il))))
        if mine:
            it = mine[-1]
            w, h = item_size(str(it["code"]))
            g.click(*inv_cell(it["x"], it["y"], w, h))
            time.sleep(0.8)
            g.click(*SHOP_DROP)
            time.sleep(1.5)
            sold = gold() - g1
            rows.append("act %d %s: sold it back for %d gold" % (act, tname, sold))
            if sold <= 0:
                bad.append("%s: the sale paid nothing" % tname)
            drop_held(log)
    g.press("esc")
    time.sleep(1)
    close_menu()
    # gamble
    menu = talk(gambler, log)
    if menu is None:
        bad.append("%s: no menu" % gname)
        return
    offers = []
    for _ in range(2):
        n = menu_line_of(menu, MENU_GAMBLE)
        if n is None:
            break
        Hl("menu %d" % n, log)
        time.sleep(2.5)
        ok, gl = H("gamble")
        offers = item_lines(gl)
        if ok and offers and trade_panel_open():
            break
        panels_closed()
        menu = talk(gambler, log)
    shots.append(sh("gamble_%s" % gname.lower()))
    g0 = gold()
    got = None
    for it in offers[:6]:
        w, h = item_size(str(it.get("code")))
        g.click(*shop_cell(it["x"], it["y"], w, h), button="right")
        time.sleep(1.5)
        if gold() < g0:
            got = it
            break
    rows.append("act %d %s: %d gamble offers, gambled %s for %d gold" % (act, gname, len(offers), got.get("code") if got else "NOTHING", g0 - gold()))
    if not offers:
        bad.append("%s: no gamble offers" % gname)
    elif not got:
        bad.append("%s: the right clicks gambled nothing" % gname)
    g.press("esc")
    time.sleep(1)
    close_menu()


def check_mercs():
    name = "mercs"
    mark = engine_mark()
    if not need_game():
        return add(name, "BLOCKED", "not in a game")
    rows, bad, log, shots = [], [], [], []
    only = os.environ.get("MXL_MERCS_PARTS", "hire,equip,fight,death,revive,reload,vendors").split(",")
    acts = [int(x) for x in os.environ.get("MXL_MERCS_ACTS", "1,2,3,4,5").split(",")]  # hirers / towns of these acts only
    revive_if_dead()
    last = None
    for act, area, npc, hname, cls in MERC_HIRERS:
        if "hire" not in only:
            break
        if act not in acts:
            continue
        m = hire_in(act, area, npc, hname, cls, log, rows, bad)
        if m is None:
            continue
        last = (act, area, npc, hname, cls)
        if "equip" in only:
            Hl("packclear", log)  # fixture: room for the test items (the check's character is reused)
            merc_panel_open(log, shots, hname.lower())
            for code, body, allowed, what in MERC_GEAR[cls]:
                on, note = equip_by_click(code, body, log, shots, hname.lower())
                rows.append("%s: %s on body %d: %s" % (hname, what, body, note))
                if on is None:
                    bad.append("%s: %s: %s" % (hname, what, note))
                elif on != allowed:
                    bad.append("%s: %s %s (want %s)" % (hname, what, "WORN" if on else "refused", "worn" if allowed else "refused"))
            panels_closed()
        if act == 1:
            if "fight" in only:
                fight_and_level(log, rows, bad)
            if "death" in only:
                merc_death(log, rows, bad)
            if "revive" in only:
                merc_revive(npc, hname, area, log, rows, bad)
    if "reload" in only and last:
        m0, w0 = merc_info()
        worn0 = sorted("%s@%s" % (i.get("code"), i.get("body")) for i in w0 if i.get("page") == 255)
        leave_and_reenter()
        time.sleep(4)
        m1, w1 = None, []
        for _ in range(15):
            m1, w1 = merc_info()
            if m1:
                break
            time.sleep(2)
        worn1 = sorted("%s@%s" % (i.get("code"), i.get("body")) for i in w1 if i.get("page") == 255)
        rows.append("Save and Exit + Play: mercenary class %s level %s wearing %s -> class %s level %s wearing %s" % (
            m0.get("class") if m0 else "-", m0.get("level") if m0 else "-", worn0, m1.get("class") if m1 else "-",
            m1.get("level") if m1 else "-", worn1))
        if not m0 or not m1 or (m0.get("class"), m0.get("level"), worn0) != (m1.get("class"), m1.get("level"), worn1):
            bad.append("the mercenary or its gear changed over Save and Exit")
    if "vendors" in only:
        for act in sorted(a for a in TOWN_VENDORS if a in acts):
            vendor_round(act, log, rows, bad, shots)
    finish(name, not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else "") +
           "; fixtures: gold set before payments, backpack cleared and test items made in it, spawned monsters (harness kills of"
           " the spawned ones after each step)", mark, shots, log)


def carry1_rows():
    """(row, code, index, carry1) of the built uniqueitems.txt rows with a carry1 number. row = the 0-based record (Expansion
    lines not counted), what the harness `item ... unique <row>` takes; the built `*ID` column is blank (Median's table has none)."""
    recs = [r for r in table("uniqueitems") if (r.get("index") or "") not in ("", "Expansion")]
    return [(i, r["code"], r["index"], r["carry1"].strip()) for i, r in enumerate(recs) if (r.get("carry1") or "").strip() not in ("", "0")]


def check_uniquecarry():
    """Bug #280 (data: txt_migrate.carry_numbers): D2R compares carry1 as a number and Median XL 2012 has 1 on all 45 carry1
    uniques (relics, quest charms), so with Median's cells only one of them fits in the backpack. The build gives each carry1 row
    its own number (record index + 1). PASS: the built numbers are distinct, three different carry1 uniques are placed in the
    backpack (D2R's placement test 0x473960, `item ... inv`), a fourth different one lying on the ground is picked up by a
    background click (the player path: the ground pickup 0x471950 with its to-inventory flag), and a second copy of the first is
    refused (`item: placing failed`), as in 1.13c. Control: a build with Median's 1 in every carry1 cell refuses the second
    different unique (lane pluginplan2's run with the old plugin part switched off, docs/testing.md)."""
    mark = engine_mark()
    log, shots = [], []
    rows = carry1_rows()
    if len(rows) < 4:
        return add("uniquecarry", "FAIL", "built uniqueitems.txt has %d carry1 rows (Median 2012: 45)" % len(rows))
    nums = [n for _, _, _, n in rows]
    distinct = len(nums) == len(set(nums))
    goto(1)
    # the character keeps what earlier runs placed (no verb removes an item): take carry1 uniques it does not carry yet
    _, il = Hl("items", log)
    carried = {int(m.group(1)) for x in il for m in [re.search(r" quality=7 index=(\d+) ", x)] if m}
    free = [r for r in rows if r[0] not in carried]
    if len(free) < 4:
        return finish("uniquecarry", False, "the character already carries %d of the %d carry1 uniques: use a fresh MXL_CHAR" % (
            len(rows) - len(free), len(rows)), mark, [], log)
    a, b, c, d = free[0], free[1], free[2], free[3]
    if carried & {r[0] for r in rows}:
        log.append("already carried carry1 uniques (earlier runs): %s" % sorted(carried & {r[0] for r in rows}))
    placed = {}
    for r in (a, b, c):
        ok, ln = Hl("item %s unique %d inv" % (r[1], r[0]), log)
        placed[r[2]] = ok and not any("placing failed" in x for x in ln)
    ok2, ln2 = Hl("item %s unique %d inv" % (a[1], a[0]), log)
    second_refused = (not ok2) and any("placing failed" in x for x in ln2)
    # the player path: the fourth lies on the ground next to the player; a left click on the item's own spot (the `item` reply has
    # its subtile; screen mapping as click_unit) walks there and picks it up, a few pixel offsets around it in case the label hides it
    n0 = inventory_count(d[1], log)
    _, gl = Hl("item %s unique %d ground" % (d[1], d[0]), log)
    ix, iy = first(gl, r" x=(\d+) "), first(gl, r" y=(\d+) ")
    picked = False
    where = None
    if ix is not None and iy is not None:
        for px_off, py_off in ((0, 0), (0, -10), (0, 10), (-14, 0), (14, 0), (0, -20), (-14, -10), (14, -10)):
            px, py = player_xy()
            dx, dy = ix - px, iy - py
            where = (dx, dy)
            g.click((800 + (dx - dy) * 27 + px_off) / 1600, (405 + (dx + dy) * 13.5 + py_off) / 900)
            time.sleep(1.5)
            if inventory_count(d[1], log) > n0:
                picked = True
                break
    log.append("ground item at %s, %s; offset from the player at the last click %s" % (ix, iy, where))
    shots.append(sh("uniquecarry_backpack"))
    ok = distinct and all(placed.values()) and second_refused and picked
    note = ("built carry1 numbers of %d rows distinct: %s; three different carry1 uniques placed: %s; a second %s refused: %s; a fourth "
            "(%s) picked up from the ground by a click: %s" % (len(nums), distinct, placed, a[2], second_refused, d[2], picked))
    finish("uniquecarry", ok, note, mark, shots, log, partial=None if picked else "the ground pickup (no click reached the item)")


def check_whirlwind():
    """Bug #281 (plugin part whirlwind, whirlwind.cpp): D2R 2.4 waits the weapon's whole attack animation between Whirlwind
    hits; Median XL 2012 runs 1.13c's srvdofunc 76 (Whirlwind, Spin To Win, Danse Macabre, Harvest), a hit every 4-16 frames
    by 1.13c's table. Barbarian with a weapon, Whirlwind on the left button, background clicks through a few zombies. PASS: the
    `mxl2012` counter of hit delays answered rises, the last delay is one of 1.13c's table values and not above D2R's frame
    count, and the log has the first spins' `mxl2012-core whirlwind:` lines (stat 68 base, both speeds). The feel against classic
    Median and the hits per spin are for the owner (screenshot)."""
    mark = engine_mark()
    log = []
    ww = row_of("skills", "skill", "Whirlwind")
    if ww is None or ww.get("srvdofunc") != "76":
        return add("whirlwind", "FAIL", "built skills.txt: Whirlwind row %s, srvdofunc %s" % (ww and ww.get("*Id"), ww and ww.get("srvdofunc")))
    wid = int(ww["*Id"])
    weapon = next((r["code"] for r in table("weapons") if r.get("type") in ("axe", "swor", "mace") and (r.get("2handed") or "0") == "0"
                   and int(r.get("levelreq") or 0) <= 60 and (r.get("spawnable") or "1") == "1" and (r.get("quest") or "0") == "0"), None)  # a plain one-handed weapon
    if not be_class(4):
        return add("whirlwind", "BLOCKED", "could not play a barbarian")

    def counter_now():
        lines = mxl_text().splitlines()
        return (first(lines, r"hit delays answered (\d+)") or 0, first(lines, r"last: D2R (\d+) frames") or 0,
                first(lines, r"last: D2R \d+ frames -> (\d+)") or 0)

    mx0 = g._size(g.MXL_LOG)
    goto(2)
    with Tank(), Level(60):
        if weapon:
            Hl("equip %s normal rhand" % weapon, log)  # refused when the hand already holds a weapon: that one is used
        got = learn(wid)
        Hl("skill left %d" % wid, log)
        px, py = player_xy()
        _, sp = Hl("spawn 5 3 %d %d" % (px + 4, py), log)
        mons = [int(m) for m in re.findall(r"id=(\d+)", " ".join(sp))]
        c0 = counter_now()
        for _ in range(4):
            if not mons or not click_unit(mons[0]):
                break
            time.sleep(2.0)
        shot = sh("whirlwind_spin")
        c1 = counter_now()
        for m in mons:
            H("kill %d" % m)
    logged = [ln.strip() for ln in (g._read_from(g.MXL_LOG, mx0) or "").splitlines() if "mxl2012-core whirlwind:" in ln]
    answered = c1[0] - c0[0]
    ok = answered > 0 and c1[2] in (4, 6, 8, 10, 12, 14, 16) and c1[2] <= max(c1[1], 4) and logged
    note = ("Whirlwind %d level %s; hit delays answered +%d; last D2R %d frames -> %d; first log lines: %s" % (
        wid, got, answered, c1[1], c1[2], logged[:2] or "none"))
    finish("whirlwind", ok, note, mark, [shot], log, partial="the feel against classic Median (hits per spin) in the screenshot")


# ---------------------------------------------------------------- cube recipe classes (lane cube; tools/cube_game.py)
CUBE_TRANSMUTE = (340, 487)  # the cube panel's Transmute button (HD, 1600 x 900 client; measured by lane realpath)
_CUBE_PANEL = {"open": False}
CUBE_GRID = (122, 107, 44, 42)  # Median's 10 x 8 cube grid in the HD cube panel: left, top, cell w, cell h (lane realpath)


def _le(*vals):
    return " ".join("%02x" % b for v in vals for b in struct.pack("<I", v & 0xffffffff))


def _all_items(log):
    _ok, lines = Hl("items", log)
    return [cube_game.kv(ln) for ln in lines if ln.startswith("item ")], lines


def _cube_now(log):
    _items, lines = _all_items(log)
    return cube_game.cube_items(lines)


def _cube_clear(log, keep=()):
    for it in _cube_now(log):
        if it.get("id") not in keep:
            Hl("remove id %d" % it["id"], log)


def _ground_pos(iid, log):
    _ok, lines = Hl("ground", log)
    for ln in lines:
        d = cube_game.kv(ln)
        if ln.startswith("ground ") and d.get("id") == iid:
            m = re.search(r"dist=([\d.]+)", ln)
            return d.get("x"), d.get("y"), float(m.group(1)) if m else 99.0
    return None


def _cube_put(spec, cell, log):
    """`item <spec> ground` (the generator's drop), the pick-up click (0x16 to the cursor, after a walk next to it when the drop
    landed away), the click on a cube cell (0x18 page 3). Returns the item's unit id once it is in the cube, else None."""
    nosock = spec.endswith(" !nosock")
    spec = spec.replace(" !nosock", "")
    for _ in range(12 if nosock else 1):
        ok, lines = Hl("item %s ground" % spec, log)
        iid = cube_game.item_id(lines) if ok else None
        if iid is None or not nosock or " sockets=0 " in " ".join(lines):
            break
    if iid is None:
        return None
    pos = _ground_pos(iid, log)
    if pos and pos[2] > 2.5:
        Hl("move %d %d" % (pos[0], pos[1]), log)
        time.sleep(1.0)
    Hl("pickup %d" % iid, log)
    for _ in range(10):
        time.sleep(0.3)
        held = held_item()
        if held and held[0] == iid:
            break
    else:
        return None
    x, y = cube_game.CUBE_CELLS[cell]
    Hl("pkt 18 " + _le(iid, x, y, 3), log)
    time.sleep(0.5)
    if any(it.get("id") == iid for it in _cube_now(log)):
        return iid
    release_held_item()
    return None


def _cube_panel_open(log):
    """A right click on the cube in the backpack (the inventory panel first), as a player opens it."""
    items, _ = _all_items(log)
    box = next((it for it in items if it.get("code") == "box" and it.get("page") == 0), None)
    if box is None:
        return False
    if not right_panel_open():
        g.press("i")
        time.sleep(1.0)
    left, top, cw, chh = INV_CELL
    g.click((left + (box["x"] + 0.5) * cw) / 1600, (top + (box["y"] + 0.5) * chh) / 900, button="right")
    time.sleep(1.5)
    return True


def _cube_panel_close():
    for _ in range(2):
        if not right_panel_open():
            return
        g.press("esc")
        time.sleep(0.8)


def _cube_types():
    out = {}
    for t in ("weapons", "armor", "misc"):
        for r in table(t):
            if r.get("code"):
                out[r["code"]] = tuple(x for x in (r.get("type"), r.get("type2")) if x)
    return out


def _unique_code(index):
    r = row_of("uniqueitems", "index", "mxl2012:" + index) or row_of("uniqueitems", "index", index)
    return r["code"] if r else None


def _skill_id(name):
    r = row_of("skills", "skill", name)
    return int(r["*Id"]) if r else None


def _type_chain(code, types):
    """The item types of a base and their Equiv parents (itemtypes.txt)."""
    eq = {r["Code"]: [r.get("Equiv1"), r.get("Equiv2")] for r in table("itemtypes")}
    seen, todo = set(), list(types.get(code, ()))
    while todo:
        t = todo.pop()
        if t and t not in seen:
            seen.add(t)
            todo += eq.get(t, [])
    return seen


def _cube_case(case, types, log, shots, keep=()):
    """One recipe: inputs into the cube, Transmute, judgement. Returns (passed, note, cube items afterwards)."""
    want = dict(case)
    want["cube"] = [(_unique_code(w[1:]) or w) if w.startswith("@") else w for w in case["cube"]]
    if str(want.get("out", "")).startswith("@"):
        want["out"] = _unique_code(want["out"][1:]) or want["out"]
    _cube_clear(log, keep)
    if not _CUBE_PANEL["open"]:  # opened once and kept open: closing and reopening per recipe lost every second click
        if not _cube_panel_open(log):
            return False, "no Horadric Cube in the backpack", []
        _CUBE_PANEL["open"] = True
    cell = len(keep)
    for spec in case["inputs"]:
        if spec.startswith("@"):
            continue
        iid = _cube_put(spec, cell, log)
        if iid is None:
            return False, "input %s did not reach the cube" % spec, []
        cell += 1
    before = _cube_now(log)
    g.click(CUBE_TRANSMUTE[0] / 1600, CUBE_TRANSMUTE[1] / 900)
    time.sleep(2.0)
    shots.append(sh("cube_%d" % case["row"]))
    after = _cube_now(log)
    stats, skill = {}, None
    out = cube_game.output_item(want, after, types, {i.get("id") for i in before})
    if out is not None:
        for name in list(case.get("stats") or {}) + list(case.get("stats_min") or {}) + list(case.get("also") or []):
            sid = stat_id(name)
            if sid is not None:
                _ok, ln = Hl("istat %d %d" % (out["id"], sid), log)
                stats[name] = cube_game.istat_value(ln)
                if not stats[name]:  # the total read 0: every layer, so a value held elsewhere is seen (zomghelp, row 580)
                    _ok, ln = Hl("istat %d %d scan" % (out["id"], sid), log)
                    layers = cube_game.istat_layers(ln)
                    if layers:
                        stats[name] = layers.get(0, next(iter(layers.values())))
                        log.append("istat %s: total 0, layers %s" % (name, layers))
        if case.get("skill_layer"):
            sname, skname = case["skill_layer"]
            r = row_of("itemstatcost", "Stat", sname)
            _ok, ln = Hl("istat %d %d scan" % (out["id"], stat_id(sname)), log)
            skill = (_skill_id(skname), cube_game.skill_ids(cube_game.istat_layers(ln), (r or {}).get("Encode", "")))
    if out is not None:  # the output's tooltip in the cube (read by hand)
        hover_px(CUBE_GRID[0] + (out.get("x", 0) + 0.5) * CUBE_GRID[2], CUBE_GRID[1] + (out.get("y", 0) + 0.5) * CUBE_GRID[3])
        shots.append(sh("cube_%d_tip" % case["row"]))
    ok, note = cube_game.judge(want, before, after, types, stats, skill)
    also = ["%s %s" % (n, stats.get(n)) for n in case.get("also") or []]
    return ok, note + ("; also read: " + ", ".join(also) if also else ""), after


def _inv_right_click(iid, log, shots, tag):
    """A right click on a backpack item (the inventory panel opened first), as a player uses it. True when it is gone after."""
    items, _ = _all_items(log)
    it = next((i for i in items if i.get("id") == iid), None)
    if it is None or it.get("page") != 0:
        return False
    if not right_panel_open():
        g.press("i")
        time.sleep(1.0)
    left, top, cw, chh = INV_CELL
    px, py = left + (it["x"] + 0.5) * cw, top + (it["y"] + 0.5) * chh
    hover_px(px, py)
    shots.append(sh(tag + "_tip"))
    g.click(px / 1600, py / 900, button="right")
    time.sleep(2.0)
    items, _ = _all_items(log)
    return not any(i.get("id") == iid for i in items)


def _respec_points(log, shots):
    """Spent points for the Token to give back (bug #240), on the player path: a Signet of Learning (`zkq`, +1 stat point, misc
    pSpell 3) dropped, picked up into the backpack and used by a right click, the point put into Strength (packet 0x3a, the
    character screen's + button). Returns (strength, statpts) after spending, or a reason string."""
    ok, lines = Hl("item zkq ground", log)
    iid = cube_game.item_id(lines) if ok else None
    if iid is None:
        return "no Signet of Learning dropped"
    pos = _ground_pos(iid, log)
    if pos and pos[2] > 2.5:
        Hl("move %d %d" % (pos[0], pos[1]), log)
        time.sleep(1.0)
    Hl("pickup %d inv" % iid, log)
    time.sleep(0.8)
    pts0 = rd("player", 4)
    if not _inv_right_click(iid, log, shots, "zkq"):
        return "the Signet of Learning was not used up (statpts %s)" % pts0
    pts1 = rd("player", 4)
    if not pts1 or pts1 <= (pts0 or 0):
        return "the Signet gave no stat point (statpts %s -> %s)" % (pts0, pts1)
    str0 = rd("player", 0)
    Hl("pkt 3a 00 00 00 00", log)  # stat 0, count field 0 = one point (D2R: 5 bytes)
    time.sleep(0.8)
    str1, pts2 = rd("player", 0), rd("player", 4)
    if str1 != (str0 or 0) + 1:
        return "the stat point did not go into Strength (%s -> %s, statpts %s)" % (str0, str1, pts2)
    log.append("respec setup: statpts %s -> %s by the signet, Strength %s -> %s, statpts %s" % (pts0, pts1, str0, str1, pts2))
    return (str1, pts2)


def _cube_use_token(after, log, shots):
    """The Token of Absolution from the cube into the backpack (clicks on its cube cell and a free backpack cell) and used by a right click; a
    spent stat point first (_respec_points), so the respec shows: Strength back, the point unspent again."""
    tok = next((i for i in after if i.get("code") == "toa"), None)
    if tok is None:
        return "no token to use"
    # lifted by a click on its cube cell and dropped by a click on a free backpack cell, as rulescheck's `rctoken` (the
    # packet 0x19 forms asserted `len == sizeof(command)` or did not move it, run checks-20261028-162149-s2)
    tx, ty = cube_px(tok["x"], tok["y"])
    g.click(tx / 1600, ty / 900)
    time.sleep(0.8)
    held = held_item()
    if not held or held[0] != tok["id"]:
        return "the token did not come onto the cursor (click on its cube cell)"
    fx, fy = inv_px(*(free_inv_cell(rc_items(log), 1, 1) or (5, 5)))
    g.click(fx / 1600, fy / 900)
    time.sleep(1.0)
    _cube_panel_close()
    _CUBE_PANEL["open"] = False
    items, _ = _all_items(log)
    it = next((i for i in items if i.get("id") == tok["id"]), None)
    if it is None or it.get("page") != 0:
        release_held_item()
        return "the token did not go into the backpack"
    spent = _respec_points(log, shots)
    if isinstance(spent, str):
        return "respec not set up: " + spent
    str1, pts1 = spent
    gone = _inv_right_click(tok["id"], log, shots, "toa")
    str2, pts2, sk2 = rd("player", 0), rd("player", 4), rd("player", 5)
    respec = str2 is not None and str2 == str1 - 1 and pts2 is not None and pts2 == (pts1 or 0) + 1
    shots.append(sh("toa_after"))
    return "token used up by the right click: %s; respec: %s (Strength %s -> %s, statpts %s -> %s, skill points %s)" % (
        "yes" if gone else "NO (still in the backpack)", "yes" if respec else "NO", str1, str2, pts1, pts2, sk2)


def check_cubeclasses():
    """Lane cube: one representative recipe per Horadric Cube recipe class on the player path (tools/cube_game.py CASES): inputs
    dropped by the generator, picked up and clicked into the cube, the panel's Transmute button clicked, the cube's contents and the
    output's stats read. MXL_CUBE_ONLY=<row,row> runs some rows only. Rulescheck's real-path classes are not repeated here."""
    mark = engine_mark()
    log, shots, rows = [], [], []
    types = _cube_types()
    _cube_panel_close()
    _CUBE_PANEL["open"] = False
    only = {int(x) for x in os.environ.get("MXL_CUBE_ONLY", "").split(",") if x.strip().isdigit()}
    enable_debug()
    goto(1, timeout=60)
    ensure_cube()
    H("packclear")
    level = rd("player", 12)
    made = {}
    wu = next((r["code"] for r in table("uniqueitems") if r.get("code") in types and "weap" in _type_chain(r["code"], types)
               and r.get("lvl", "").isdigit() and int(r["lvl"]) <= 20), None)
    for case in cube_game.CASES:
        if only and case["row"] not in only:
            continue
        keep, label = (), "%s (row %d, %s)" % (case["name"], case["row"], case["cls"])
        if case.get("level") is not None and level != case["level"]:
            rows.append((label, None, "skipped: the row needs character level %d, the character is %s" % (case["level"], level)))
            continue
        c = dict(case)
        if "@honorific" in case["inputs"]:
            ok, note, after = _cube_case(cube_game.PREP_HONORIFIC, types, log, shots)
            rows.append((cube_game.PREP_HONORIFIC["name"] + " (row 8394)", ok, note))
            hon = cube_game.output_item(cube_game.PREP_HONORIFIC, after, types)
            if not ok or hon is None:
                rows.append((label, False, "no honorific weapon to test with"))
                continue
            keep = (hon["id"],)
            c["cube"], c["out"] = ["type:pmac"], "type:pmac"
        elif "@dupe" in case["inputs"]:
            if not made.get("dupe"):
                rows.append((label, None, "skipped: the dupe step made no copy"))
                continue
            keep = (made["dupe"],)
        elif "@weapon_unique" in case["inputs"] or "@shield_unique" in case["inputs"]:
            code = wu if "@weapon_unique" in case["inputs"] else cube_game.SHIELD
            c["inputs"] = [("%s unique ilvl=99" % code) if s.startswith("@") else s for s in case["inputs"]]  # unique lvl <= ilvl
        ok, note, after = _cube_case(c, types, log, shots, keep)
        if case.get("again"):  # the refusal step runs on a duped item even when no second copy came out
            copies = [i for i in after if i.get("code") == cube_game.WEAPON]
            made["dupe"] = copies[0]["id"] if copies else None
            for extra in copies[1:]:
                Hl("remove id %d" % extra["id"], log)
        if case.get("use") and ok:
            used = _cube_use_token(after, log, shots)
            ok = "used up by the right click: yes" in used and "respec: yes" in used
            note += "; " + used
        rows.append((label, ok, note))
        if not game_alive():
            rows.append(("game", False, "the game died at row %d" % case["row"]))
            break
    _cube_clear(log)
    _cube_panel_close()
    _CUBE_PANEL["open"] = False
    bad = [r for r in rows if r[1] is False]
    skipped = [r for r in rows if r[1] is None]
    note = " | ".join("%s: %s - %s" % (r[0], "PASS" if r[1] else ("SKIP" if r[1] is None else "FAIL"), r[2]) for r in rows)
    finish("cubeclasses", bool(rows) and not bad, note, mark, shots, log,
           partial=("skipped: " + "; ".join(r[0] for r in skipped)) if skipped else None)


def game_alive():
    return bool(g.game_pids()) and hstate()["ok"]


# ---------------------------------------------------------------- lane rulescheck: Median's character rules on the player path
# docs/median-rules-audit.md "Characters: in-game checks". Owner rule for these verdicts: the player path only. No god mode, no
# stat or level set by the harness, items picked up from the ground by a click and used by a right click in the inventory, the
# real cube, skill tree and NPC dialogs, a mortal character. What the harness still does is named in each note as a SHORTCUT
# (getting an item onto the ground, travel to an area, monsters placed next to the character) and the check is PARTIAL then.
# Run with a fresh character (MXL_CHAR, letters only; the lane used a Druid, MXL_CHAR_CLASS=druid).
RC_STATS = {"newskills": 5, "statpts": 4, "hitpoints": 6, "maxhp": 7, "mana": 8, "maxmana": 9, "level": 12, "experience": 13,
            "gold": 14, "goldbank": 15, "fireresist": 39, "lightresist": 41, "coldresist": 43, "poisonresist": 45,
            "potion_stat_cap": 370, "potion_skill_cap": 371}
RC_RESISTS = ("fireresist", "lightresist", "coldresist", "poisonresist")
RC_PAGE_INV, RC_PAGE_CUBE, RC_PAGE_BODY = 0, 3, 255
RC_FORMS = (448, 463)  # Trap Rat Form, Treewarden Form: Druid, required level 1, localdelay 250 (Median `delay` 250)
RC_KASHYA = 150  # monstats row of Kashya (D2R and Median)


def parse_items(lines):
    """`h items` / `h item` lines -> [{id, code, page, x, y, quality, ...}] (ints where the value is a number)."""
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln.startswith("item id="):
            continue
        out.append({k: (int(v, 0) if k != "code" and re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", v) else v) for k, v in kv(ln).items()})
    return out


def rc_items(log=None):
    ok, lines = Hl("items", log) if log is not None else H("items")
    return parse_items(lines)


def rc_of(code, page=None, log=None):
    return [i for i in rc_items(log) if i.get("code") == code and (page is None or i.get("page") == page)]


def rc_stats(names=None, log=None):
    """The player's stats by RC_STATS name (`stat player <id>`, the unit's value with items, 1/256 for life and mana)."""
    out = {}
    for n in names or RC_STATS:
        _, ln = Hl("stat player %d" % RC_STATS[n], log) if log is not None else H("stat player %d" % RC_STATS[n])
        out[n] = stat_of(ln)
    return out


def rc_obtain(code, log, shortcut, quality=""):
    """SHORTCUT (named in the note): the harness puts a new item on the ground next to the character (as a drop would). Then the
    player path: a left click on it picks it up into the inventory. Returns the inventory item dict or None."""
    log.append("%s dropped next to the character by `item %s ground` (stands in for a monster drop)" % (code, code))
    close_right_panel()
    _, ln = Hl("item %s %s ground" % (code, quality) if quality else "item %s ground" % code, log)
    made = parse_items(ln)
    if not made:
        return None
    gid = made[0]["id"]
    for k in range(4):  # the ground item's world spot (x, y of the answer) projected like a monster's; hover first, then click
        p = hstate()["player"]
        dx, dy = made[0]["x"] - p["x"], made[0]["y"] - p["y"]
        px, py = 800 + (dx - dy) * 27, 405 + (dx + dy) * 13.5 + 8
        hover_px(px, py)
        g.click(px / 1600, py / 900)  # the player walks to the item and picks it up
        time.sleep(2.5)
        new = next((i for i in rc_items() if i["id"] == gid and i.get("page") == RC_PAGE_INV), None)
        if new:
            log.append("picked up %s id %d at inventory %d,%d by a click at %d,%d" % (code, gid, new["x"], new["y"], px, py))
            return new
    log.append("%s id %d not picked up (the game may refuse it: 'I can't')" % (code, gid))
    return None


def inv_px(x, y):
    left, top, cw, ch = INV_CELL
    return left + (x + 0.5) * cw, top + (y + 0.5) * ch


def rc_open_inventory():
    if not right_panel_open():
        g.press("i")
        time.sleep(1.2)
    return right_panel_open()


def rc_use(item, log, shots, label):
    """Right click on the item in the open inventory, as a player uses a book, potion or scroll."""
    rc_open_inventory()
    px, py = inv_px(item["x"], item["y"])
    hover_px(px, py)
    shots.append(sh("%s_tip" % label))
    g.click(px / 1600, py / 900, button="right")
    time.sleep(2.0)
    shots.append(sh("%s_used" % label))
    log.append("right click on %s id %d at %d,%d (px %d,%d)" % (item["code"], item["id"], item["x"], item["y"], px, py))
    close_right_panel()


def rc_note(base, shortcut):
    return base + ("; SHORTCUT: " + "; ".join(shortcut) if shortcut else "; no shortcut")


def rc_finish(name, ok, note, mark, shots, log, shortcut, judged_by_hand=None):
    """finish() with the verdict rule of the lane: a check that needed a harness shortcut is PARTIAL ('shortcut only'), never PASS."""
    partial = judged_by_hand
    if shortcut and ok:
        partial = (partial + "; " if partial else "") + "shortcut only: " + "; ".join(shortcut)
    finish(name, ok, rc_note(note, []) if not shortcut else note, mark, shots, log, partial=partial)


def check_rcbook():
    """#240 SK8 / QU2: a Book of Skill (`ass`, misc pSpell 10 since the fix) dropped next to the character, picked up by a click,
    read by a right click: +1 skill point (stat newskills). Lane rulescheck, slot 3: D2R answers the click with "I can't" for
    `ass`, `xyz` and `tr2` (quest 15 / 19 / 32, questdiffcheck 1, the same cells as D2R's own rows) while `bks` and every
    non-quest item is picked up; `h item ass inv` fails too ("placing failed"). The check is then BLOCKED, not FAIL: a character
    has to reach the quest (Radament, Anya, Malah) for the player path."""
    rc_quest_use("rcbook", "ass", lambda s0, s1: (s1["newskills"] or 0) - (s0["newskills"] or 0) == 1, ["newskills"], "+1 skill point")


def rc_skill_level(skill, log):
    """1 when the character has the skill (the game selects it on the right button: `h skill right` answers OK), else 0. The
    harness has no reader for a skill's base level."""
    ok, _ln = Hl("skill right %d" % skill, log)
    return 1 if ok else 0


def rc_cast_right(skill, log):
    """Right click next to the character with `skill` on the right button (set by `h skill right`: the skill bar pick has no rule
    of its own); returns (mana before, mana after) in 1/256."""
    Hl("skill right %d" % skill, log)
    time.sleep(0.4)
    m0 = rc_stats(["mana"], log)["mana"]
    g.click(0.56, 0.48, button="right")
    time.sleep(0.8)
    m1 = rc_stats(["mana"], log)["mana"]
    return m0, m1


def delay_verdict(first_ok, second_ok, second_ok_later):
    """CH13 / SK6 as 1.13c: a skill with a delay puts EVERY skill with a delay on hold for that delay (the unit's `skilldelay`
    state). True when the second delay skill is refused inside the first one's delay and works after it; None when the first
    cast did not happen (nothing to judge)."""
    if not first_ok:
        return None
    return (not second_ok) and second_ok_later


def check_rcdelay():
    """CH13 / SK6: Trap Rat Form (delay 250) cast by a right click outside town, Treewarden Form right after: 1.13c refuses the
    second (one unit-wide delay), D2R casts it after charstats MinimumCastingDelay (12 frames) unless skills.txt `globaldelay` holds
    the delay too (the build fills only `localdelay`). SHORTCUT: both forms learnt by `h setskill` (a level-1 character has no
    points). Lane rulescheck, slot 3: the game answered both casts with "Impossible." (red icon, mana unchanged), in town and in
    Blood Moor, so the rule was not reached: BLOCKED."""
    mark = engine_mark()
    log, shots, shortcut = [], [], ["forms learnt by `h setskill`", "travel to Blood Moor by `h level 2`"]
    for s in RC_FORMS:
        Hl("setskill %d 1" % s, log)
    goto(2)
    a0, a1 = rc_cast_right(RC_FORMS[0], log)
    shots.append(sh("delay_first"))
    b0, b1 = rc_cast_right(RC_FORMS[1], log)
    shots.append(sh("delay_second"))
    time.sleep(11)
    c0, c1 = rc_cast_right(RC_FORMS[1], log)
    shots.append(sh("delay_later"))
    goto(1)
    spent = lambda x, y: x is not None and y is not None and y < x
    v = delay_verdict(spent(a0, a1), spent(b0, b1), spent(c0, c1))
    note = ("Trap Rat Form mana %s -> %s; Treewarden Form right after %s -> %s; 11 s later %s -> %s; 1.13c: the second refused "
            "inside the first one's delay" % (a0, a1, b0, b1, c0, c1))
    if v is None:
        return add("rcdelay", "BLOCKED", note + "; the first cast did not happen (the game said 'Impossible.')", shots, log)
    rc_finish("rcdelay", v, note, mark, shots, log, shortcut)


def check_rctoken():
    """#240 SK9: Oil of Absolution (`8o^`) and an El rune (`r01`) picked up from the ground, each clicked onto the Horadric Cube in
    the inventory, Transmute (cubemain "ToA creation"), the Token of Absolution (`toa`, pSpell 13 since the fix) lifted out of the
    cube into the inventory and used by a right click: it is used up (before the fix the right click did nothing). The refund
    (all stat and skill points back) needs points spent first: reported, judged only when the character had any."""
    mark = engine_mark()
    log, shots = [], []
    goto(1)
    s0 = rc_stats(["newskills", "statpts", "level"], log)
    cube = (rc_of("box", RC_PAGE_INV) or [None])[0]
    if cube is None:
        return add("rctoken", "BLOCKED", "no Horadric Cube in the inventory (starting kit)")
    got = [rc_obtain(c, log, []) for c in ("8o^", "r01")]
    if None in got:
        return finish("rctoken", False, "inputs not picked up: %s" % got, mark, shots, log)
    for it in got:
        rc_insert(it, cube, log)
    inside = rc_transmute(cube, log, shots, "token_cube_after")
    toa = rc_of("toa", RC_PAGE_CUBE, log)
    if not toa:
        return finish("rctoken", False, "cube after Transmute %s, no token" % inside, mark, shots, log)
    rc_open_inventory()  # open the cube again, lift the token, drop it into a free inventory cell
    cx, cy = inv_px(cube["x"] + 0.5, cube["y"] + 0.5)
    g.click(cx / 1600, cy / 900, button="right")
    time.sleep(1.5)
    tx, ty = cube_px(toa[0]["x"], toa[0]["y"])
    g.click(tx / 1600, ty / 900)
    time.sleep(0.8)
    fx, fy = inv_px(*(free_inv_cell(rc_items(log), 1, 1) or (5, 5)))
    g.click(fx / 1600, fy / 900)
    time.sleep(1.0)
    g.press("esc")
    time.sleep(1.0)
    tok = next((i for i in rc_items(log) if i["id"] == toa[0]["id"] and i.get("page") == RC_PAGE_INV), None)
    if tok is None:
        return finish("rctoken", False, "token made but not moved into the inventory", mark, shots, log)
    rc_use(tok, log, shots, "token")
    s1 = rc_stats(["newskills", "statpts"], log)
    used = not any(i["id"] == tok["id"] for i in rc_items(log))
    spent_before = (s0["level"] or 1) > 1
    finish("rctoken", used, "cube -> %s; token %s; skill points %s -> %s, stat points %s -> %s (level %s)" % (
        inside, "used up" if used else "kept", s0["newskills"], s1["newskills"], s0["statpts"], s1["statpts"], s0["level"]),
        mark, shots, log, partial=None if spent_before else
        "the refund itself: a level-1 character has no spent points (levelling is out of reach on the player path in a lane)")


CUBE_CELL = (121, 107, 44, 42)  # HD cube grid 10 x 8: left, top, cell w, cell h (px, measured lane rulescheck)


def cube_px(x, y):
    left, top, cw, ch = CUBE_CELL
    return left + (x + 0.5) * cw, top + (y + 0.5) * ch


def release_into_inventory(log):
    """An item on the cursor goes into the inventory: open it and click the top-left cell of the largest free block (main's harness
    has no `cursor` verb, so the click is made whether or not something is held: on an empty cursor it does nothing)."""
    rc_open_inventory()
    free = free_inv_cell(rc_items(log))
    if free is None:
        return False
    px, py = inv_px(*free)
    g.click(px / 1600, (py - 15) / 900)
    time.sleep(1.0)
    return True


def free_inv_cell(items, w=2, h=4, grid=(10, 6)):
    """Top-left (x, y) of a free w x h block of the inventory grid (item sizes from the built tables, 1 x 1 when unknown)."""
    taken = set()
    for i in items:
        if i.get("page") != RC_PAGE_INV:
            continue
        iw, ih = item_size(i.get("code"))
        taken |= {(i["x"] + a, i["y"] + b) for a in range(iw) for b in range(ih)}
    for y in range(grid[1] - h + 1):
        for x in range(grid[0] - w + 1):
            if not any((x + a, y + b) in taken for a in range(w) for b in range(h)):
                return x, y
    return None


def item_size(code):
    for t in ("weapons", "armor", "misc"):
        r = row_of(t, "code", code)
        if r:
            try:
                return max(1, int(r.get("invwidth") or 1)), max(1, int(r.get("invheight") or 1))
            except ValueError:
                return 1, 1
    return 1, 1


def check_rclife():
    """#240 QU2: Potion of Life (`xyz`, pSpell 11): +20 maximum life, the potion used up. Refused like the Book (see rcbook)."""
    rc_quest_use("rclife", "xyz", lambda s0, s1: (s1["maxhp"] or 0) - (s0["maxhp"] or 0) == 20 << 8, ["maxhp", "hitpoints"],
                 "+20 max life (1.13c and D2R pSpell 11)")


def check_rcscroll():
    """#240 QU2: Malah's scroll (`tr2`, pSpell 12): +10 to all four resistances, the scroll used up. Refused like the Book."""
    rc_quest_use("rcscroll", "tr2", lambda s0, s1: all((s1[r] or 0) - (s0[r] or 0) == 10 for r in RC_RESISTS), list(RC_RESISTS),
                 "+10 all resistances")


def rc_quest_use(name, code, rule, stats, expected):
    mark = engine_mark()
    log, shots = [], []
    goto(1)
    s0 = rc_stats(stats, log)
    it = rc_obtain(code, log, [])
    if it is None:
        shots.append(sh("%s_refused" % name))
        return add(name, "BLOCKED", "%s not picked up: the game refuses this quest item to a character outside its quest ('I can't'); "
                   "the use (%s) is not reached on the player path" % (code, expected), shots, log)
    rc_use(it, log, shots, name)
    s1 = rc_stats(stats, log)
    left = [i for i in rc_of(code) if i["id"] == it["id"]]
    ok = rule(s0, s1) and not left
    finish(name, ok, "%s: %s; item %s; expected %s" % (code, ", ".join("%s %s -> %s" % (k, s0[k], s1[k]) for k in stats),
                                                      "kept" if left else "used up", expected), mark, shots, log)


def check_rcdeath():
    """XP5: a real death (no god mode; the Blood Moor's own monsters) and the experience before and after. On Normal Median and
    vanilla both lose nothing (DeathExpPenalty 0); the Median rule that differs (1 % on Nightmare / Hell) needs a character there,
    which the player path cannot reach in a lane. SHORTCUT: travel to Blood Moor by `h level 2`."""
    mark = engine_mark()
    log, shots, shortcut = [], [], ["travel to Blood Moor by `h level 2`"]
    goto(2)
    xp0 = rc_stats(["experience"], log)["experience"]
    t0, dead, k = time.time(), False, 0
    while time.time() - t0 < 180:  # walk around and attack what comes near: the character fights until it dies
        st = hstate()
        if player_dead(st["player"]):
            dead = True
            break
        near = [m for m in st["mons"] if m.get("dist", 99) < 14]
        if near:
            click_unit(min(near, key=lambda m: m["dist"])["id"])
            time.sleep(0.7)
            continue
        dx, dy = ((6, 0), (0, 6), (-6, 0), (0, -6))[(k // 4) % 4]
        k += 1
        g.click((800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5) / 900)
        time.sleep(1.2)
    shots.append(sh("death"))
    xp1 = rc_stats(["experience"], log)["experience"]
    revive_if_dead()
    xp2 = rc_stats(["experience"], log)["experience"]
    note = "Normal: experience %s before, %s at death, %s after the respawn (died: %s)" % (xp0, xp1, xp2, dead)
    if not dead:
        return add("rcdeath", "BLOCKED", note + "; no death in 180 s", shots, log)
    rc_finish("rcdeath", xp1 == xp0 and xp2 == xp0, note, mark, shots, log, shortcut,
              judged_by_hand=None if xp0 else "the loss itself: the character had no experience to lose (Median's 1 % applies "
                                                  "on Nightmare / Hell only)")


def check_rchire():
    """#241 ME4 / ME8: Kashya's hire list. Real path: the character walks next to Kashya (left clicks on the ground), a left click
    on her, her menu (screenshot). Lane rulescheck, slot 3: a fresh character's menu has Talk and Cancel only; as in 1.13c she
    hires only after the Burial Grounds quest, so the list is not reached: BLOCKED with the menu screenshot."""
    log, shots = [], []
    goto(1)
    st = hstate()
    k = [m for m in st["mons"] if m.get("class") == RC_KASHYA]
    if not k:
        return add("rchire", "BLOCKED", "Kashya not near the arrival point")
    walk_next_to(k[0]["id"], log)
    click_unit(k[0]["id"])
    time.sleep(18)  # her greeting plays first, then the menu
    shots.append(sh("hire_menu"))
    g.press("esc")
    add("rchire", "BLOCKED", "Kashya's menu in hire_menu.png (Hire is offered only after the Burial Grounds quest); "
        "expected on the list: every Rogue level 3 for a level-1 player (3-6 would be bug #241)", shots, log)
ITEM_FLAG_RUNEWORD = 0x04000000  # item data flags (`h item` flags=): the runeword bit, as 1.13c's IFLAG_RUNEWORD


def rc_drop(item, log):
    """Lift the item from the open inventory and drop it on the ground left of the panel (a player clearing space)."""
    rc_open_inventory()
    px, py = inv_px(item["x"], item["y"])
    g.click(px / 1600, py / 900)
    time.sleep(0.8)
    g.click(0.30, 0.55)
    time.sleep(1.2)
    log.append("dropped %s id %d" % (item["code"], item["id"]))


def rc_insert(filler, target, log):
    """Lift `filler` (rune / jewel) in the open inventory and click it onto `target`: the game sockets it, as a player does."""
    rc_open_inventory()
    px, py = inv_px(filler["x"], filler["y"])
    g.click(px / 1600, py / 900)
    time.sleep(0.8)
    tx, ty = inv_px(target["x"], target["y"])
    g.click(tx / 1600, (ty + 10) / 900)
    time.sleep(1.2)
    log.append("clicked %s id %d onto %s id %d" % (filler["code"], filler["id"], target["code"], target["id"]))


RP_CHARM = ("s0m", 176, 596)  # Scroll of Summons (type summ, Charm 1 in Median): unique row 176, level 1, oskill 596
EQUIP_SLOT_RHAND = (1090, 205)  # HD inventory panel: the weapon slot (left column, top), 1600 x 900


def charm_verdict(inv, cube, ground):
    """RP5 / IB7 as 1.13c: a charm's stats apply while it is in the inventory, not in the cube nor on the ground."""
    return inv and not cube and not ground


def check_rpcharm():
    """RP5 (IB7): Median's charm flag. The Scroll of Summons is picked up from the ground (its oskill 596 must be usable), clicked
    onto the cube (inside it: no skill), lifted out again into the inventory, then dropped (no skill)."""
    mark = engine_mark()
    log, shots = [], []
    goto(1)
    code, row, skill = RP_CHARM
    it = rc_obtain(code, log, [], "unique %d" % row)
    if it is None:
        return finish("rpcharm", False, "charm not picked up", mark, shots, log)
    inv = rc_skill_level(skill, log)
    hover_px(*inv_px(it["x"], it["y"]))
    shots.append(sh("charm_tip"))
    cube = (rc_of("box", RC_PAGE_INV) or [None])[0]
    rc_insert(it, cube, log)  # into the cube
    in_cube = any(i["id"] == it["id"] and i.get("page") == RC_PAGE_CUBE for i in rc_items(log))
    cub = rc_skill_level(skill, log)
    close_right_panel()
    cx, cy = inv_px(cube["x"] + 0.5, cube["y"] + 0.5)  # open the cube, lift the charm out, back into the inventory
    rc_open_inventory()
    g.click(cx / 1600, cy / 900, button="right")
    time.sleep(1.5)
    c = next(i for i in rc_items(log) if i["id"] == it["id"])
    g.click(cube_px(c["x"], c["y"])[0] / 1600, cube_px(c["x"], c["y"])[1] / 900)
    time.sleep(0.8)
    g.press("esc")
    time.sleep(1.0)
    release_into_inventory(log)
    back = next((i for i in rc_items(log) if i["id"] == it["id"] and i.get("page") == RC_PAGE_INV), None)
    inv2 = rc_skill_level(skill, log)
    if back:
        rc_drop(back, log)
    close_right_panel()
    gnd = rc_skill_level(skill, log)
    ok = charm_verdict(inv and inv2, cub, gnd) and in_cube
    finish("rpcharm", ok, "oskill %d: inventory %s, in the cube %s (inside: %s), inventory again %s, on the ground %s; expected only in the "
           "inventory" % (skill, inv, cub, in_cube, inv2, gnd), mark, shots, log)


def check_rpnames():
    """RP6 (AF3, AF5; bugs #310): a magic ring shows its base name without a double space; the Sacred amulet (automagic group 401)
    and Anya's reward amulet (494) show an automagic line. Picked up from the ground, hovered in the inventory: read by hand."""
    mark = engine_mark()
    log, shots, rows = [], [], []
    goto(1)
    for code, q in (("rin", "magic"), ("qmu", "normal"), ("dr1", "normal")):
        it = rc_obtain(code, log, [], q)
        if it is None:
            rows.append("%s not picked up" % code)
            continue
        rc_open_inventory()
        hover_px(*inv_px(it["x"], it["y"]))
        shots.append(sh("name_%s" % code))
        rows.append("%s %s picked up (quality %s)" % (code, q, it.get("quality")))
        rc_drop(it, log)
    close_right_panel()
    finish("rpnames", all("picked up (" in r for r in rows), "; ".join(rows), mark, shots, log,
           partial="the names and automagic lines in name_rin / name_qmu / name_dr1.png are read by hand")


def check_rpequip():
    """RP1 (IB5): equip by click. A Short Sword (no requirement) goes onto the weapon slot; a Broad Sword (Strength 48, the Druid
    has less) is refused and stays on the cursor (put back into the inventory)."""
    mark = engine_mark()
    log, shots, rows = [], [], []
    goto(1)
    worn = [i for i in rc_items(log) if i.get("page") == RC_PAGE_BODY and i.get("x") in (4, 5)]
    for w in worn:  # free the weapon slots first: a click on a worn item lifts it, then into the inventory
        rc_open_inventory()
        g.click(EQUIP_SLOT_RHAND[0] / 1600, EQUIP_SLOT_RHAND[1] / 900)
        time.sleep(0.8)
        release_into_inventory(log)
    for code, want in (("100", True), ("bsd", False)):
        it = rc_obtain(code, log, [], "normal")
        if it is None:
            rows.append((code, False, "not picked up"))
            continue
        rc_open_inventory()
        px, py = inv_px(it["x"], it["y"])
        g.click(px / 1600, py / 900)
        time.sleep(0.8)
        g.click(EQUIP_SLOT_RHAND[0] / 1600, EQUIP_SLOT_RHAND[1] / 900)
        time.sleep(1.2)
        shots.append(sh("equip_%s" % code))
        now = next((i for i in rc_items(log) if i["id"] == it["id"]), {})
        on = now.get("page") == RC_PAGE_BODY
        rows.append((code, on == want, "%s worn: %s (want %s)" % (code, on, want)))
        if not on:
            release_into_inventory(log)
        else:  # take it off again
            g.click(EQUIP_SLOT_RHAND[0] / 1600, EQUIP_SLOT_RHAND[1] / 900)
            time.sleep(0.8)
            release_into_inventory(log)
    close_right_panel()
    finish("rpequip", len(rows) == 2 and all(r[1] for r in rows), "; ".join(r[2] for r in rows), mark, shots, log)


def rc_transmute(cube, log, shots, label):
    """Open the cube (right click on it in the inventory), press Transmute, close; returns the codes in the cube afterwards."""
    rc_open_inventory()
    cx, cy = inv_px(cube["x"] + 0.5, cube["y"] + 0.5)
    g.click(cx / 1600, cy / 900, button="right")
    time.sleep(1.5)
    g.click(CUBE_TRANSMUTE[0] / 1600, CUBE_TRANSMUTE[1] / 900)
    time.sleep(1.8)
    shots.append(sh(label))
    g.press("esc")
    time.sleep(1.0)
    close_right_panel()
    inside = sorted(i["code"] for i in rc_items(log) if i.get("page") == RC_PAGE_CUBE)
    log.append("%s: cube holds %s" % (label, inside))
    return inside


DARK_RING = (["l@l", "m@m", "p@p", "q@q"], ("r@r", 1791), ("s@s", 1792), "r01")  # cubemain 10627 after bug #311


def check_rpdarkring():
    """RP3 (CU10, bug #311): "upgrade dark ring" has numinputs 6 and five named inputs (Ingredient Rings 1, 2, 4, 5 and the Boss
    Killer Ring); input 3 names nothing (Median's `oµo`), so 1.13c and D2R take ANY sixth item. Real cube: the five alone make
    nothing (the count), the five plus an El rune make the Upgraded Boss Killer Ring."""
    mark = engine_mark()
    log, shots = [], []
    goto(1)
    cube = (rc_of("box", RC_PAGE_INV) or [None])[0]
    rings, (bkr, bkr_row), (up, _up_row), sixth = DARK_RING
    got = [rc_obtain(c, log, []) for c in rings] + [rc_obtain(bkr, log, [], "unique %d" % bkr_row)]
    if cube is None or None in got:
        return finish("rpdarkring", False, "not all inputs picked up: %s" % [g_["code"] if g_ else None for g_ in got], mark, shots, log)
    for it in got:
        rc_insert(it, cube, log)
    five = rc_transmute(cube, log, shots, "darkring_five")
    s = rc_obtain(sixth, log, [])
    if s is None:
        return finish("rpdarkring", False, "sixth item not picked up; five alone: %s" % five, mark, shots, log)
    rc_insert(s, cube, log)
    six = rc_transmute(cube, log, shots, "darkring_six")
    ok = up not in five and up in six
    finish("rpdarkring", ok, "five inputs -> cube %s; plus %s -> cube %s; expected %s only with the sixth item" % (five, sixth, six, up),
           mark, shots, log)


def runeword_rounds():
    """RP2 (RW1): (label, base code, item args, fillers in order, runeword expected)."""
    return [("Dawn, El in a grey 1-socket Short Sword", "100", "normal 194=1", ["r01"], True),
            ("Dawn, jewel jewel El in a 3-socket Broad Sword", "bsd", "normal 194=3", ["jew", "jew", "r01"], True),
            ("no Dawn, El first in a 3-socket Broad Sword", "bsd", "normal 194=3", ["r01", "jew", "jew"], False),
            ("no Dawn, El in a magic 1-socket Short Sword", "100", "magic 194=1", ["r01"], False),
            ("Kyrie, Taha Taha in a 2-socket Long Staff", "152", "normal 194=2", ["r51", "r51"], True)]


def check_rprunes():
    """RP2: runewords made on the player path. Each base and filler is picked up from the ground with a click, each filler clicked onto
    the base in the inventory in order; the result is the item's runeword flag (and its name in the screenshot)."""
    mark = engine_mark()
    log, shots, rows = [], [], []
    goto(1)
    for label, base, args, fillers, want in runeword_rounds():
        b = rc_obtain(base, log, [], args)
        fs = [rc_obtain(f, log, []) for f in fillers]
        if b is None or None in fs:
            rows.append((label, False, "not picked up"))
            continue
        for f in fs:
            cur = next((i for i in rc_items(log) if i["id"] == b["id"]), b)
            rc_insert(f, cur, log)
        it = next((i for i in rc_items(log) if i["id"] == b["id"]), None)
        if it is None:
            rows.append((label, False, "base gone"))
            continue
        made = bool(it["flags"] & ITEM_FLAG_RUNEWORD)
        left = [f["code"] for f in fs if any(i["id"] == f["id"] for i in rc_items(log) if i.get("page") == RC_PAGE_INV)]
        hover_px(*inv_px(it["x"], it["y"]))
        shots.append(sh("rw_%d" % len(rows)))
        rows.append((label, made == want, "runeword flag %s (want %s), fillers still loose %s" % (made, want, left or "none")))
        rc_drop(it, log)
        for f in fs:
            loose = next((i for i in rc_items(log) if i["id"] == f["id"] and i.get("page") == RC_PAGE_INV), None)
            if loose:
                rc_drop(loose, log)
        close_right_panel()
    finish("rprunes", len(rows) == len(runeword_rounds()) and all(r[1] for r in rows),
           "; ".join("%s: %s" % (r[0], r[2]) for r in rows), mark, shots, log,
           partial="runeword names in the rw_*.png tooltips are read by hand")


def rune_letter_rounds():
    """Bug #334: (label, base code, item args, runes in order, letters the tooltip's quoted line must read)."""
    return [("Dawn, El (r01, D2R's r01L)", "100", "normal 194=1", ["r01"], "El"),
            ("Gehenna, Xar (r47, a literal that is D2R's item key xar)", "100", "normal 194=1", ["r47"], "Xar"),
            ("Kyrie, Taha Taha (r51, a Great Rune without a D2R key)", "152", "normal 194=2", ["r51", "r51"], "TahaTaha")]


def rune_letter_counts(text):
    """(drawn from the cell, D2R keys kept) of the `mxl2012` runeletter line, or None when the line is missing or off."""
    m = re.search(r"^runeletter on:.*letters drawn from the cell (\d+), D2R keys kept (\d+)", text or "", re.M)
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_runeletters():
    """#334: the rune letters of a runeword's tooltip. Each runeword is made on the player path (as rprunes) and its tooltip hovered;
    the plugin part runeletter counts the letters it drew from the gems cell (Xar, Taha) and the D2R keys it left alone (El, r01L).
    PASS needs every runeword made, both counters grown while hovering, and no assert / crash; the letters themselves ("El",
    "Xar", "TahaTaha" between the quotes, not "Missing string" / "Ornate Plate") are read by hand in rl_*.png."""
    mark = engine_mark()
    if not need_game():
        return add("runeletters", "BLOCKED", "not in a game")
    log, shots, rows = [], [], []
    goto(1)
    before = rune_letter_counts(mxl_text())
    log.append("runeletter counters before: %s" % (before,))
    for label, base, args, fillers, letters in rune_letter_rounds():
        b = rc_obtain(base, log, [], args)
        fs = [rc_obtain(f, log, []) for f in fillers]
        if b is None or None in fs:
            rows.append((label, False, "not picked up"))
            continue
        for f in fs:
            cur = next((i for i in rc_items(log) if i["id"] == b["id"]), b)
            rc_insert(f, cur, log)
        it = next((i for i in rc_items(log) if i["id"] == b["id"]), None)
        if it is None:
            rows.append((label, False, "base gone"))
            continue
        made = bool(it["flags"] & ITEM_FLAG_RUNEWORD)
        hover_px(*inv_px(it["x"], it["y"]))
        time.sleep(1.0)
        shots.append(sh("rl_%d" % len(rows)))
        counts = rune_letter_counts(mxl_text())
        rows.append((label, made, "runeword flag %s, want '%s', counters %s" % (made, letters, counts)))
        rc_drop(it, log)
        close_right_panel()
    after = rune_letter_counts(mxl_text())
    log.append("runeletter counters after: %s" % (after,))
    grown = before is not None and after is not None and after[0] > before[0] and after[1] > before[1]
    finish("runeletters", len(rows) == len(rune_letter_rounds()) and all(r[1] for r in rows) and grown,
           "; ".join("%s: %s" % (r[0], r[2]) for r in rows) + "; counters %s -> %s" % (before, after), mark, shots, log,
           partial="the letters between the quotes in rl_0.png (El), rl_1.png (Xar), rl_2.png (TahaTaha) are read by hand")


def check_rclevels():
    """LV2-LV4 (#242): Kurast 3000 BA (level 84: Median outdoors, rain and mud) and levels 125-127 (Median indoors). SHORTCUT: the
    harness travels there (`h level`); what is judged is the look (daylight / weather / indoor light), by hand from the screenshots.
    D2R reads no IsInside (plugin-plan section 15), so a FAIL of the look is the known gap, not a new one."""
    mark = engine_mark()
    log, shots, shortcut = [], [], ["travel by `h level`"]
    reached = []
    for lv in (84, 125, 126, 127):
        st = goto(lv, timeout=60)
        if st["player"].get("area") != lv:
            reached.append("%d not reached" % lv)
            continue
        time.sleep(4)
        shots.append(sh("level_%d" % lv))
        reached.append("%d reached" % lv)
    goto(1, timeout=60)
    rc_finish("rclevels", all("reached" in r and "not" not in r for r in reached), "; ".join(reached), mark, shots, log, shortcut,
              judged_by_hand="daylight, rain and mud in level_84.png, indoor light in level_125-127.png")


def walk_next_to(mon_id, log, reach=5, steps=12):
    """Left clicks on the ground towards a unit (<= 6 subtiles per click) until it is within `reach`."""
    for _ in range(steps):
        st = hstate()
        p = st["player"]
        m = next((m for m in st["mons"] if m.get("id") == mon_id), None)
        if m is None:
            return False
        dx, dy = m["mx"] - p["x"], m["my"] - p["y"]
        d = max(abs(dx), abs(dy))
        if d <= reach:
            return True
        f = min(1.0, 6.0 / d)
        sx, sy = dx * f, dy * f
        g.click((800 + (sx - sy) * 27) / 1600, (405 + (sx + sy) * 13.5) / 900)
        time.sleep(1.6)
    return False


# ---------------------------------------------------------------- acts (lane acts): Acts 2-5 and the difficulties on the player path
# `py -3 tools/game_checks.py all acts` with MXL_CHAR=<throwaway> (a new Barbarian is made) and MXL_ACTS=<stage,stage> (default: all,
# in order). The owner's rule (docs/testing.md "Acts 2-5"): no god mode, no invulnerability, no easykill. Harness help that is
# allowed and named in every row: travel (`level`, `place`), experience (`xp`) and gear (`equip` with stats). Quest steps, boss
# kills (the game's own Attack skill through the cast packet path), rewards and NPC dialogs (talk packet + the menu line's own
# handler) go through the game. A step that needed a shortcut says "shortcut only".

ACT_TOWNS = {1: 1, 2: 40, 3: 75, 4: 103, 5: 109}
# Town NPCs per act (monstats ids of the built table).
TOWN_NPCS = {1: {146: "cain1", 147: "gheed", 148: "akara", 150: "kashya", 154: "charsi", 155: "warriv1"},
             2: {175: "warriv2", 176: "atma", 177: "drognan", 178: "fara", 198: "greiz", 199: "elzix", 201: "jerhyn", 202: "lysander",
                 210: "meshif1", 244: "cain2"},
             3: {245: "cain3", 252: "asheara", 253: "hratli", 254: "alkor", 255: "ormus", 264: "meshif2", 297: "natalya"},
             4: {246: "cain4", 367: "tyrael2", 405: "jamella", 257: "halbu"},
             5: {511: "larzuk", 512: "drehya", 513: "malah", 514: "nihlathak", 520: "cain6", 521: "tyrael3"}}
TOWN_WAYPOINT_OBJ = {1: 119, 2: 156, 3: 237, 4: 398, 5: 429}  # objects.txt waypoint classes of the five towns
# stage: (act, boss level, boss class, character level the run gives, quest whose bits the kill must change). Mephisto's quest is
# The Guardian, 22 (17-22 are Act 3's six, 23 the travel to Act 4): his kill in run checks-20261029-021145-s2 left 23 unchanged
ACT_BOSSES = {"andariel": (1, 37, 156, 50, 6), "duriel": (2, 73, 211, 60, 14), "mephisto": (3, 102, 242, 70, 22),
              "diablo": (4, 108, 243, 90, 26), "baal": (5, 132, 544, 90, 40)}
# act travel through an NPC's menu: stage -> (from town, NPC class, destination town)
ACT_TRAVEL = {"travel12": (1, 155, 40), "travel23": (40, 210, 75), "travel45": (103, 367, 109)}
ACTS_STAGES = ["build", "towns", "andariel", "travel12", "duriel", "travel23", "mephisto", "mephmelee", "travel34", "diablo", "travel45",
               "ancients", "throne", "baal", "nightmare"]
ACTS_ASKED_ONLY = ("build", "mephmelee")  # stages that run only when MXL_ACTS names them (the build's calibration)
BAAL_THRONE = 543  # monstats: Baal on his throne (Throne of Destruction, 131), who calls the five waves
ACTS_END_PLUS_SKILLS = 10  # lane endgame: the level 80-98 build died 3-6 times at Diablo, the throne waves and Baal (runs
# checks-20261030-034855-s3, -041902-s2); the given amulet adds +10 to all skills (stat 127) for those three stages
ACTS_BOSS_RETRIES = 4  # goes at a boss after deaths (Mephisto lost 26,000 of 56,440 life per go and does not heal it back)
ACTS_REGEN = 5  # replenish life per character level on the given ring (Median's Normal Durance / Chaos / throne killed the
# character with 25 vitality per level within 15-120 s, runs of lane acts2)
ACTS_VIT = 60  # vitality per character level on the given ring
ACTS_BOW, ACTS_ARROWS = "161", "aqv"  # Hunter's Bow (Grade 1) and Arrows: Mephisto across the moat
ACTS_RANGED = ("mephisto",)  # boss stages fought with the bow
ACTS_WEAPON = "115"  # Axe (Grade 1): a one-hander any class holds; the damage comes from the given stats
ANCIENTS_ALTAR = 546  # objects.txt: the Arreat Summit altar


def parse_menu(lines):
    """`menu list` lines -> {"npc": class, "lines": [(index, string id, handler)]}; None when there is no menu line."""
    head = next((kv(ln) for ln in lines if ln.startswith("menu npc ")), None)
    if head is None:
        return None
    out = {"npc": int(head.get("class", -1)), "lines": []}
    for ln in lines:
        m = re.match(r"\s*line (\d+) string=0x([0-9a-f]+) handler=(\S+)", ln)
        if m:
            out["lines"].append((int(m.group(1)), int(m.group(2), 16), m.group(3)))
    return out


def parse_quest_dump(lines):
    """`quest <id> dump` -> (quest, "0101..." bits 0-15) or None."""
    for ln in lines:
        m = re.match(r"quest (\d+) bits0-15 ([01]{16})", ln)
        if m:
            return int(m.group(1)), m.group(2)
    return None


def parse_presets(lines):
    """`presets` lines -> [{"type", "class", "x", "y"}]."""
    return [{k: int(v) for k, v in kv(ln).items()} for ln in lines if ln.startswith("preset type=")]


def parse_objects(lines):
    """`objects` lines -> [{"id", "class", "mode", "dist", "x", "y"}]."""
    out = []
    for ln in lines:
        m = re.match(r"object id=(\d+) class=(\d+) mode=(\d+) dist=(\d+) at (\d+),(\d+)", ln)
        if m:
            out.append(dict(zip(("id", "class", "mode", "dist", "x", "y"), map(int, m.groups()))))
    return out


def parse_xp(lines):
    """`xp` answer -> {"level", "experience", "statpoints", "skillpoints"} or {}."""
    for ln in lines:
        if ln.startswith("xp level="):
            return {k: int(v) for k, v in kv(ln).items()}
    return {}


def new_menu_lines(before, after):
    """(index, string id) of the lines a menu gained (an act travel line appears when the quest allows it)."""
    have = {s for _i, s, _h in (before or {"lines": []})["lines"]}
    return [(i, s) for i, s, _h in (after or {"lines": []})["lines"] if s not in have]


def acts_stages(env=None):
    """The stages MXL_ACTS asks for, in the run's order (unknown names are dropped)."""
    want = [s.strip() for s in (os.environ.get("MXL_ACTS", "") if env is None else env).split(",") if s.strip()]
    return [s for s in ACTS_STAGES if (s in want if want else s not in ACTS_ASKED_ONLY)]


def quest_bits(q):
    _ok, lines = H("quest %d dump" % q)
    r = parse_quest_dump(lines)
    return r[1] if r else None


def step_towards(px, py, tx, ty, step=60):
    """The next point of a walk from (px, py) to (tx, ty) at most `step` sub-tiles away (the server paths each `move`)."""
    dx, dy = tx - px, ty - py
    d = (dx * dx + dy * dy) ** 0.5
    if d <= step:
        return tx, ty
    return int(px + dx * step / d), int(py + dy * step / d)


WALL_AIS = ("BoneWall",)  # a monster's Bone Wall (344 in the throne room): the Attack skill does not hurt it, it expires by itself


def unkillable_classes():
    """monstats rows with `killable` off (Median's `mephistospirit` around Mephisto, effects, dummies): never fought."""
    if "unkillable" not in STATE:
        try:
            STATE["unkillable"] = {i for i, r in enumerate(table("monstats")) if not (r.get("killable") or "").strip()
                                   or (r.get("AI") or "") in WALL_AIS}
        except Exception:
            STATE["unkillable"] = set()
    return STATE["unkillable"]


def hostiles_near(st, radius, skip=(), unkillable=None):
    """Monsters of a `state` within `radius` that can die (no NPCs in the dungeons the walks go through), nearest first."""
    bad = unkillable_classes() if unkillable is None else unkillable
    return sorted((m for m in st["mons"] if m.get("dist", 99) <= radius and m.get("class") not in skip and m.get("life", 1) > 0
                   and m.get("class") not in bad), key=lambda m: m.get("dist", 99))


def parse_moveto(lines):
    """`moveto` answer -> {"id", "class", "x", "y"} of the unit the character runs to, or None."""
    for ln in lines:
        m = re.search(r"moveto unit id=(\d+) class=(\d+) at (\d+),(\d+)", ln)
        if m:
            return dict(zip(("id", "class", "x", "y"), map(int, m.groups())))
    return None


def acts_mon_life(mon_id):
    """Life of a monster unit (1/256 points), None when the unit is gone (`stat mon:<id>` finds no unit)."""
    ok, lines = H("stat mon:%d 6" % mon_id)
    return stat_of(lines) if ok else None


def acts_clear(radius=14, skip=(), timeout=120):
    """Fight what attacks the character on a walk (the Attack skill, as acts_fight). False when the character died."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = hstate()
        if st["player"] and player_dead(st["player"]):
            STATE["acts_deaths"] = STATE.get("acts_deaths", 0) + 1
            return False
        near = hostiles_near(st, radius, skip)
        if not near:
            return True
        _k, d, _s = acts_fight(near[0]["id"], 40)
        if d:
            return False
    return True


def acts_walk(tx, ty, reach=6, timeout=90, fight=False, skip=()):
    """Run to (tx, ty) with `move` (the walk packet's server call), one leg at a time; True when within `reach`. With `fight`
    the monsters in reach are fought first (a dungeon); False when the character died."""
    t0 = time.time()
    last, stuck = None, 0
    while time.time() - t0 < timeout:
        st = hstate()
        p = st["player"]
        if STATE.get("walk_seen") is not None:
            for m in st["mons"]:
                STATE["walk_seen"].setdefault(m.get("class"), "walk life %s" % p.get("life"))
        if STATE.get("walk_spots") is not None:  # a town sweep: where each unit stands
            for m in st["mons"]:
                if m.get("mx"):
                    STATE["walk_spots"].setdefault(m.get("class"), (m["mx"], m["my"]))
        if p and player_dead(p):
            STATE["acts_deaths"] = STATE.get("acts_deaths", 0) + 1
            return False
        if fight and hostiles_near(st, 14, skip) and not acts_clear(14, skip):
            return False
        px, py = p.get("x", 0), p.get("y", 0)
        crumbs = STATE.setdefault("crumbs", [])  # where the walks went (acts_walk_back)
        if not crumbs or max(abs(crumbs[-1][0] - px), abs(crumbs[-1][1] - py)) >= 8:
            crumbs.append((px, py, p.get("area")))
            del crumbs[:-60]
        if last is not None:
            walk_map_link(p.get("area"), last, (px, py))
        if abs(px - tx) <= reach and abs(py - ty) <= reach:
            return True
        if last == (px, py):  # stuck at a wall: a detour leg, each time another direction and farther
            stuck += 1
            dx, dy = WALK_DETOURS[stuck % len(WALK_DETOURS)]
            k = 1 + stuck // len(WALK_DETOURS)
            H("move %d %d" % (px + dx * k, py + dy * k))
            time.sleep(2)
        else:
            stuck = 0
        last = (px, py)
        H("move %d %d" % step_towards(px, py, tx, ty, 60 if stuck < 2 else 30))
        time.sleep(2.5)
    return False


# The search walk's map (lane acts5): the Chaos Sanctuary's walls kept the straight walks and their detour legs pinned for 10-20
# minutes (7709-7739, 5266-5269 in runs checks-20261029-114925-s2 and -135256-s2; 7804-7819, 5223-5260 in the second; 7821, 5223
# in -124850-s2). Every walk links the cells it really moved between (STATE["walk_map"][area]: cell -> cells), so the way out
# of a wing is the way in; a refused leg is searched as lane vendors3's click route does (ven_route_pick).
WALK_CELL, WALK_STEP = 6, 12


def walk_cell(x, y):
    return (int(x) // WALK_CELL, int(y) // WALK_CELL)


def walk_centre(c):
    return c[0] * WALK_CELL + WALK_CELL // 2, c[1] * WALK_CELL + WALK_CELL // 2


def walk_map(area):
    return STATE.setdefault("walk_map", {}).setdefault(area, {"edges": {}, "tried": set()})


def walk_map_link(area, a, b):
    """The character really moved from a to b (`state` positions): both cells are linked, both ways."""
    ca, cb = walk_cell(*a), walk_cell(*b)
    if ca == cb or max(abs(a[0] - b[0]), abs(a[1] - b[1])) > 40:  # a `place` or a level change is no walk
        return
    e = walk_map(area)["edges"]
    e.setdefault(ca, set()).add(cb)
    e.setdefault(cb, set()).add(ca)


def walk_search_pick(c, m, tx, ty):
    """Dijkstra over the walked links from cell c, then the reached cell + untried direction with the least (way there + leg +
    straight distance after it). Returns (the cell to walk to next, direction to try from it or None) or None."""
    import heapq
    dist, first, heap = {c: 0.0}, {c: None}, [(0.0, c)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, 1e18):
            continue
        for v in m["edges"].get(u, ()):
            nd = d + math.hypot((v[0] - u[0]) * WALK_CELL, (v[1] - u[1]) * WALK_CELL)
            if nd < dist.get(v, 1e18):
                dist[v], first[v] = nd, first[u] if first[u] is not None else v
                heapq.heappush(heap, (nd, v))
    best = None
    for u, d in dist.items():
        ux, uy = walk_centre(u)
        if math.hypot(ux - tx, uy - ty) < WALK_STEP / 2:
            v = (d, u, None)
        else:
            v = None
            for k, (dx, dy) in enumerate(VEN_DIRS):
                if (u, k) in m["tried"]:
                    continue
                w = d + WALK_STEP + math.hypot(ux + dx * WALK_STEP - tx, uy + dy * WALK_STEP - ty)
                if v is None or w < v[0]:
                    v = (w, u, k)
        if v is not None and (best is None or v[0] < best[0]):
            best = v
    if best is None:
        return None
    _w, u, k = best
    return (first[u] if u != c else None), k


def acts_search_walk(tx, ty, log, budget_s=180, reach=8, fight=True):
    """Walk to (tx, ty) by `move` legs over the walk map: back along walked links to the most promising cell, then one untried
    WALK_STEP leg in one of 16 directions from it (a leg that ends in the same cell is not tried again). True when within reach;
    False when the budget is spent, nothing is left to try or the character died."""
    t0, legs = time.time(), 0
    while time.time() - t0 < budget_s:
        st = hstate()
        p = st["player"]
        if not p or player_dead(p):
            return False
        if fight and hostiles_near(st, 14, ()) and not acts_clear(14, ()):
            return False
        px, py, area = p.get("x", 0), p.get("y", 0), p.get("area")
        if abs(px - tx) <= reach and abs(py - ty) <= reach:
            log.append("search walk to %d,%d: there after %d legs, %d s" % (tx, ty, legs, time.time() - t0))
            return True
        m, c = walk_map(area), walk_cell(px, py)
        pick = walk_search_pick(c, m, tx, ty)
        if pick is None:
            break
        nxt, k = pick
        if nxt is not None:  # along a walked link first
            qx, qy = walk_centre(nxt)
        elif k is None:  # this cell is the target's: the last bit straight
            H("move %d %d" % (tx, ty))
            nx, ny = ven_wait_still(4.0) or (px, py)
            if max(abs(nx - tx), abs(ny - ty)) > reach:
                break
            continue
        else:
            m["tried"].add((c, k))
            qx, qy = px + VEN_DIRS[k][0] * WALK_STEP, py + VEN_DIRS[k][1] * WALK_STEP
        H("move %d %d" % (qx, qy))
        legs += 1
        nx, ny = ven_wait_still(4.0) or (px, py)
        walk_map_link(area, (px, py), (nx, ny))
        if nxt is not None and walk_cell(nx, ny) == c:  # a walked link that does not take any more (a unit in the way)
            m["edges"].get(c, set()).discard(nxt)
    p = hstate()["player"]
    log.append("search walk to %d,%d: not there after %d legs, %d s (at %s,%s, %d cells mapped)" % (
        tx, ty, legs, time.time() - t0, p.get("x"), p.get("y"), len(walk_map(p.get("area"))["edges"])))
    return False


# Detour legs of a stuck walk (`state` units), turning round: the server refuses a leg through a wall (Lut Gholein's docks wall
# kept the walk to Meshif at 5163,5076 for 18 min with one fixed sideways leg, run of lane acts2)
WALK_DETOURS = ((15, -15), (-15, -25), (25, 15), (-25, 25), (0, -30), (30, 0), (0, 30), (-30, 0))


EXPLORE_LEGS = ((0, -150), (150, 0), (0, 150), (-150, 0), (150, -150), (-150, -150), (150, 150), (-150, 150))


def acts_approach(npc_class, reach=5, spot=None, explore=True):
    """Walk up to an NPC: `moveto` while it is loaded and far, else to the spot a town sweep saw it at, else towards its preset
    spot, else (with `explore`) one look around the arrival (an NPC that is not in the town, e.g. Act 1's Cain before Tristram,
    costs one round of legs, not more)."""
    explored, far_tried = not explore, False
    for _ in range(12):
        near = [m for m in hstate()["mons"] if m.get("class") == npc_class]
        if near and near[0].get("dist", 99) <= reach:
            return True
        if near:
            H("moveto %d" % near[0]["id"])
            time.sleep(3)
            continue
        if spot is None and not far_tried:  # loaded but beyond the `state` list (Jerhyn in the palace, 120 away): its spot
            far_tried = True
            u = parse_moveto(H("moveto nearest %d" % npc_class)[1])
            spot = (u["x"], u["y"]) if u else None
        if spot:
            if not acts_walk(spot[0], spot[1], reach=10, timeout=60):
                H("place %d %d" % spot)  # a town wall the walk does not get round: travel help
                time.sleep(2)
            spot = None
            continue
        pres = [q for q in parse_presets(H("presets 1")[1]) if q["class"] == npc_class]
        if pres:
            if not acts_walk(pres[0]["x"], pres[0]["y"], reach=10, timeout=60):
                H("place %d %d" % (pres[0]["x"], pres[0]["y"]))  # a town wall the walk does not get round: travel help
                time.sleep(2)
            continue
        if explored:
            return False
        explored = True
        p = hstate()["player"]  # not placed by the map (Lut Gholein's Meshif stands at the docks): look around the arrival
        for dx, dy in EXPLORE_LEGS:
            acts_walk(p["x"] + dx, p["y"] + dy, reach=15, timeout=40)
            if parse_moveto(H("moveto nearest %d" % npc_class)[1]):
                break
        else:
            return False
    near = [m for m in hstate()["mons"] if m.get("class") == npc_class]
    return bool(near) and near[0].get("dist", 99) <= reach


def acts_menu(npc_class, wait=40, spot=None, explore=True):
    """Walk up to an NPC, talk to it (the server's talk packet) and wait for its menu; the parsed menu or None. Only the first
    attempt explores (a second round of legs per NPC made the towns stage take an hour)."""
    for attempt in range(3):
        close_menu()
        if not acts_approach(npc_class, spot=spot, explore=explore and attempt == 0) and attempt == 0                 and not parse_moveto(H("moveto nearest %d" % npc_class)[1]):
            return None  # not in this town (yet)
        ok, _l = H("interact %d" % npc_class)
        if not ok:
            continue
        lines = wait_menu(wait if attempt == 0 else 20)
        menu = parse_menu(lines or [])
        if menu:
            return menu
    return None


def acts_level_up(level):
    """Experience through the game's own award until the character level is reached (allowed help, named in the rows)."""
    lvl, amount = hstate()["player"].get("level", 0), 50000
    for _ in range(60):
        if lvl >= level:
            break
        r = parse_xp(H("xp %d" % amount)[1])
        lvl = r.get("level", lvl)
        amount = min(amount * 2, 2000000000)
    acts_build_setup([])  # the spell build spends the new points (no-op on a class without one)
    return hstate()["player"].get("level", 0)


def acts_gear_ranged(level, log=None):
    """acts_gear with a bow instead of the axe (Mephisto stands across the Durance 3 lava moat: a melee swing gets no path,
    run checks-20261028-221216-s2 stood 6 from him for 3 minutes without a hit, as a player shoots across it): Hunter's Bow
    with the same damage stats in the weapon hand, arrows in the other. Returns the damage, or 0 when the bow did not go on."""
    dmg = acts_gear(level)
    H("unequip rhand")
    H("unequip lhand")
    ok, lines = H("equip %s 21=%d 22=%d 119=400 60=20 93=60 rhand" % (ACTS_BOW, dmg, dmg * 2))  # bows read 21 / 22 too; open: the
    # cast path shot for 4 life a hit (run checks-20261028-224031-s2) and mostly not at all at 17 from Mephisto (23 / 24, 22:56 run)
    ok2, lines2 = H("equip %s 70=500 lhand" % ACTS_ARROWS)
    if log is not None:
        log.append("bow: %s / %s" % ((lines or ["-"])[-1], (lines2 or ["-"])[-1]))
    return dmg if ok and ok2 else 0


def acts_gear(level):
    """Gear for a level: a weapon with damage, 400 % attack rating, 20 % life leech (Median divides it by 4 on Normal) and 60 %
    attack speed; a ring with vitality, strength, 75 resistances, 50 % damage reduction, flat physical / magic reduction (2 / 1 per
    level) and 200 % faster hit recovery (Median's crowds hit-lock a character without it). No invulnerability; worn by `equip`
    (the game's place function gives the owner the stats). Life filled once."""
    dmg = 40 + level * 12
    H("unequip rhand")
    H("equip %s 21=%d 22=%d 119=400 60=20 93=60 rhand" % (ACTS_WEAPON, dmg, dmg * 2))
    H("unequip rring")
    H("equip rin 3=%d 0=200 36=50 34=%d 35=%d 99=200 74=%d rring" % (level * ACTS_VIT, level * 2, level, level * ACTS_REGEN))
    H("unequip neck")
    plus = STATE.get("acts_plus_skills", 0)  # lane endgame: +all skills (stat 127) for the end bosses, named in the rows
    H("equip amu 39=75 41=75 43=75 45=75%s neck" % (" 127=%d" % plus if plus else ""))  # the harness takes up to 8 stats per item
    top = rd("player", 7)
    if top:
        setstat("player", 6, top)
    if STATE.get("acts_build"):  # the spell build: no weapon (its damage comes from the skills), the ring and amulet stay
        H("unequip rhand")
        H("unequip lhand")
        H("unequip lring")
        H("equip rin 27=%d lring" % ACTS_BUILD_MANA_REGEN)
        return 0
    return dmg


# ---------------------------------------------------------------- lane acts3: a character with a real build (coordinator decision)
# The Barbarian with only Attack died in Durance, Chaos Sanctuary and the Throne; Mephisto stays across the lava moat. A Sorceress
# (MXL_CHAR_CLASS=sorceress) plays the acts with her own skills instead: the character level comes from the game's xp award as
# before, the stat and skill points that level gives are spent by the harness (SET-UP, named in every row: stat points through
# the character screen's packet 0x3a, skills with `setskill` and the same number of skill points taken off), and every hit comes
# from a skill used by a background right click on the monster's spot, as a player casts. No weapon damage, no god mode.
# Skills, prerequisites first (skills.txt ids of the build): Flamefront 1, Living Flame (passive: +life), Cold Blood 1, Frigid
# Sphere (cold, the main skill: the wave bosses 1148 / 803 / 1290 / 1281 / 1289 are immune to lightning, fire, magic or poison,
# none to cold), Ice Queen (passive: +life %), Forked Lightning 1, Thunderstone 1, Tempest (lightning, for cold immunes), Warp
# Armor (passive: dodge / avoid / evade). Damage of each grows with the character level and Energy (skills.txt EDmgSymPerCalc).
# Lane acts5: Lord De Seis (1699) is cold immune and magic resistant (monumod 8: +40 fire / cold / lightning), and Tempest took
# about 500 a click, too slow for his pack of six (31,000 + 5 x 10,500 life, run checks-20261029-081719-s1). Second tree:
# Moonstrike 1, Familiar 1, Arcane Torrent (magic bolts plus physical, both scaled by the mana pool; he resists neither).
ACTS_BUILD_SKILLS = {1: ((523, 1), (524, 20), (529, 1), (530, 20), (543, 1), (544, 1), (545, 20), (528, 6), (533, 1), (534, 1),
                         (535, 20), (536, 20))}
ACTS_BUILD_MAIN = {1: (530, 545, 535)}  # the skill on the right button: the first one the monster is not immune to
ACTS_BUILD_ENERGY = 250  # Energy first up to this (the skills' damage term saturates: 260 * (E + 10) / (E + 250)), the rest Vitality
ACTS_BUILD_MANA_REGEN = 300  # % mana regeneration (stat 27) on a second given ring: spell casters live on mana (named help)
ACTS_SPELL_REACH = 12  # sub-tiles: the monster's spot is on the screen (the click lands on it) and in the spells' reach
RES_COLUMNS = {530: "ResCo", 545: "ResMa", 535: "ResLi"}  # monstats column (Normal) of the build skills' element


def acts_build_skills(cls_id=None):
    """The build of the character's class, or None (the Attack path)."""
    if cls_id is None:
        cls_id = hstate()["player"].get("class")
    return ACTS_BUILD_SKILLS.get(cls_id)


def acts_build_levels(levels=None):
    """The build's skill levels this slot's character got from earlier runs ({skill: base level}; the harness has no reader for a
    base level): read, or written when `levels` is given. Kept in the runs folder per slot and character, next to the saves'
    backups."""
    path = os.path.join(g.RUNS, "acts-build-s%d-%s.json" % (g.SLOT, g.CHAR_NAME))
    if levels is None:
        try:
            with open(path, encoding="utf-8") as f:
                return {int(k): v for k, v in json.load(f).items()}
        except (OSError, ValueError):
            return {}
    with open(path, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in levels.items()}, f)
    return levels


def acts_has_build():
    """True for a class with a spell build (set before acts_level_up's set-up fills STATE["acts_build"])."""
    return bool(STATE.get("acts_build") or acts_build_skills(hstate()["player"].get("class")))


def acts_build_setup(log):
    """SET-UP: spend the stat and skill points the character's level gave (no-op for a class without a build). Stats through
    packet 0x3a (one point per packet, the + button of the character screen); skills raised with `setskill` (the game's own skill
    point function) up to the build's levels as far as the unspent points reach, those points then taken off (stat 5). Returns a
    note for the rows."""
    p = hstate()["player"]
    build = acts_build_skills(p.get("class"))
    if not build:
        STATE["acts_build"] = None
        return ""
    STATE["acts_build"] = p.get("class")
    pts = rd("player", 4) or 0
    energy0 = rd("player", 1) or 0
    spent_e = spent_v = 0
    for _ in range(pts):
        stat = 1 if (rd("player", 1) or 0) < ACTS_BUILD_ENERGY else 3
        H("pkt 3a %02x 00 00 00" % stat)  # stat id, count field 0 = one point (D2R: 5 bytes, as the signet check)
        if stat == 1:
            spent_e += 1
        else:
            spent_v += 1
    left = rd("player", 4)
    skp = rd("player", 5) or 0
    spent_s, levels = 0, []
    known = acts_build_levels()
    for sid, want in build:
        have = known.get(sid, 0)
        want = min(want, have + skp - spent_s)
        if want <= have:
            levels.append((sid, have))
            continue
        got = _setskill(sid, want) or have
        spent_s += max(got - have, 0)
        known[sid] = got
        levels.append((sid, got))
    if spent_s:
        setstat("player", 5, max(skp - spent_s, 0))
    acts_build_levels(known)
    note = ("SET-UP: %d stat points spent by packet 0x3a (Energy +%d from %d, Vitality +%d; %s left), %d skill points spent by "
            "setskill (%s)" % (pts, spent_e, energy0, spent_v, left, spent_s, ", ".join("%d:%d" % x for x in levels)))
    log.append(note)
    if pts or spent_s or not STATE.get("acts_build_note"):
        STATE["acts_build_note"] = note
    return STATE["acts_build_note"]


def acts_build_skill_for(mon_cls):
    """The build skill for this monster class: the first main skill whose element the monster does not resist fully (Normal)."""
    mains = ACTS_BUILD_MAIN.get(STATE.get("acts_build"), ())
    try:
        row = table("monstats")[mon_cls]
    except Exception:
        row = {}
    for sid in mains:
        if int((row.get(RES_COLUMNS.get(sid, "")) or "0") or 0) < 100:
            return sid
    return mains[0] if mains else 0


def acts_near_boss(u, boss_id):
    """The server finds no path to a spot next to a boss beyond the lava, but it paths to a unit: run (`moveto`, the walk to a
    unit) to the monster that stands nearest the boss (Mephisto's council at the moat's edge: run checks-20261028-232449-s2 stood
    7 from him 15 s after such a walk). True when the character got closer."""
    st = hstate()
    p = st["player"]
    d0 = abs(p.get("x", 0) - u["x"]) + abs(p.get("y", 0) - u["y"])
    others = sorted((m for m in st["mons"] if m.get("id") != boss_id and m.get("mx")),
                    key=lambda m: abs(m["mx"] - u["x"]) + abs(m["my"] - u["y"]))
    for m in others[:3]:
        H("moveto %d" % m["id"])
        time.sleep(4)
        p = hstate()["player"]
        if abs(p.get("x", 0) - u["x"]) + abs(p.get("y", 0) - u["y"]) < d0 - 10:
            return True
    return False


def short_of(px, py, tx, ty, dist):
    """The point `dist` sub-tiles short of (tx, ty) on the line from (px, py): a walk aimed at the boss's own spot is refused
    when he stands beyond the lava (Mephisto, run checks-20261028-233533-s2: 10 minutes at the Durance 3 arrival)."""
    dx, dy = px - tx, py - ty
    d = (dx * dx + dy * dy) ** 0.5
    if d <= dist:
        return px, py
    return int(tx + dx * dist / d), int(ty + dy * dist / d)


def on_screen(m, p):
    """The monster's spot is inside the screen (click_unit's offsets), clear of the skill bar at the bottom."""
    dx, dy = m.get("mx", 0) - p.get("x", 0), m.get("my", 0) - p.get("y", 0)
    fx, fy = (800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5) / 900
    return 0.03 < fx < 0.97 and 0.05 < fy < 0.85


def acts_spell_fight(mon_id, timeout=240, focus=False):
    """acts_fight for the spell build: closes in to ACTS_SPELL_REACH (walking, fighting what is in the way), puts the skill for
    the monster on the right button (`skill right`) and right-clicks the monster's spot on the screen (click_unit, background
    input). A death ends the fight. Returns (killed, deaths, seconds); the casts and mana spent go to STATE["acts_casts"]."""
    t0, deaths, last, chosen = time.time(), 0, None, None
    area0 = hstate()["player"].get("area")
    d_start = STATE.get("acts_deaths", 0)
    casts = STATE.setdefault("acts_casts", {})
    while time.time() - t0 < timeout:
        acts_load_sample()
        st = hstate()
        p = st["player"]
        if p and player_dead(p):
            deaths += 1
            STATE["acts_deaths"] = STATE.get("acts_deaths", 0) + 1
            revive_if_dead()
            return False, deaths, int(time.time() - t0)
        if p.get("area") != area0:  # revived in town by a walk inside the fight (acts_planned_walk's clearing): a death too
            if p.get("area") in ACT_TOWNS.values() and area0 not in ACT_TOWNS.values():
                deaths += 1
                if STATE.get("acts_deaths", 0) == d_start:  # acts_clear counts the deaths it sees itself
                    STATE["acts_deaths"] = d_start + 1
            return False, deaths, int(time.time() - t0)
        life = acts_mon_life(mon_id)
        if life is not None and life <= 0:
            return True, deaths, int(time.time() - t0)
        if life is None:
            return (last is not None and last < ACTS_GONE_LOW), deaths, int(time.time() - t0)
        last = life
        m = next((m for m in st["mons"] if m.get("id") == mon_id), None)
        if m is None or m.get("dist", 99) > ACTS_SPELL_REACH or not on_screen(m, p):
            if focus:  # a boss: walk up without stopping for every minion (Durance 3 sends them without end, run
                u = parse_moveto(H("moveto %d" % mon_id)[1])  # checks-20261028-232449-s2 spent 4 minutes on them)
                if u:  # the run to the unit is accepted (mode 3) and a command right after it cancels it (run
                    time.sleep(4)  # checks-20261029-010614-s2: 8 minutes at the Durance 3 arrival): let it run first
                    q = hstate()["player"]
                    if abs(q.get("x", 0) - u["x"]) + abs(q.get("y", 0) - u["y"]) >= abs(p.get("x", 0) - u["x"]) + abs(p.get("y", 0) - u["y"]) - 5:
                        H("move %d %d" % (u["x"], u["y"]))  # his own spot: the walk there was taken in run checks-20261028-232449-s2
                        time.sleep(4)
                        q2 = hstate()["player"]
                        if abs(q2.get("x", 0) - q.get("x", 0)) + abs(q2.get("y", 0) - q.get("y", 0)) < 5:
                            if acts_clear_blockers(mon_id):  # run checks-20261029-013841-s2: 10 minutes on the arrival
                                chosen = None  # stairs with a monster next to the character and every walk refused
                                continue
                            tx, ty = short_of(q.get("x", 0), q.get("y", 0), u["x"], u["y"], ACTS_SPELL_REACH - 2)
                            if not acts_walk(tx, ty, reach=4, timeout=20) and not acts_planned_walk(
                                    u["x"], u["y"], STATE.setdefault("fight_walk_log", []), budget=90, reach=ACTS_SPELL_REACH - 2):
                                acts_near_boss(u, mon_id)  # the planned walk: lane endgame (Diablo at the star)
            elif not acts_close_in(mon_id, reach=ACTS_SPELL_REACH):
                continue
            m = next((m for m in hstate()["mons"] if m.get("id") == mon_id), None)
            if m is None or not on_screen(m, hstate()["player"]):
                time.sleep(1)
                continue
        sid = acts_build_skill_for(m.get("class"))
        if sid != chosen:
            H("skill right %d" % sid)
            chosen = sid
        if click_unit(mon_id, "right"):
            casts[sid] = casts.get(sid, 0) + 1
        time.sleep(0.3)
    return False, deaths, int(time.time() - t0)


def acts_load_sample(every=10):
    """Bug #395 (long-fight load): every `every` s of a boss fight, (time, game frame, newest missile id near the character, live
    server missiles, private MB) into STATE["acts_load"]. Read-only harness reads."""
    now = time.time()
    if now - STATE.get("acts_load_t", 0) < every:
        return
    STATE["acts_load_t"] = now
    ok, st = H("state", 20)
    _, ms = H("missiles", 20)
    STATE.setdefault("acts_load", []).append((now, first(st, r"frame=(\d+)") if ok else None, first(st, r"mis id=(\d+)") if ok else None,
                                              first(ms, r"missiles live=(\d+)"), game_private_mb()))


def acts_load_note():
    """Summary of STATE["acts_load"] for a row: fight length sampled, frames per second, missile ids per second, live missiles,
    private MB; reset for the next fight."""
    smp = STATE.pop("acts_load", [])
    STATE.pop("acts_load_t", None)
    if len(smp) < 2:
        return "load: %d samples" % len(smp)
    fps, ids = [], []
    for a, b in zip(smp, smp[1:]):
        dt = b[0] - a[0]
        if dt > 0 and None not in (a[1], b[1]) and b[1] >= a[1]:
            fps.append((b[1] - a[1]) / dt)
        if dt > 0 and None not in (a[2], b[2]) and b[2] >= a[2]:
            ids.append((b[2] - a[2]) / dt)
    lives = [x[3] for x in smp if x[3] is not None]
    mems = [x[4] for x in smp if x[4] is not None]
    med = lambda v: round(sorted(v)[len(v) // 2], 1) if v else None
    return ("load (bug #395) over %d s, %d samples: frames/s median %s min %s; missile ids/s median %s max %s; live server missiles "
            "median %s max %s; private MB %s -> %s, max %s; harness reads failed %d" % (
                int(smp[-1][0] - smp[0][0]), len(smp), med(fps), round(min(fps), 1) if fps else None, med(ids),
                round(max(ids)) if ids else None, med(lives), max(lives) if lives else None, mems[0] if mems else None,
                mems[-1] if mems else None, max(mems) if mems else None, sum(1 for x in smp if x[1] is None)))


def acts_clear_blockers(boss_id, clicks=6):
    """The walk to a boss is refused: right-click the nearest other living monster on the screen within ACTS_SPELL_REACH a few
    times (it may stand in the way). Returns True when there was one."""
    st = hstate()
    p = st["player"]
    near = sorted((m for m in st["mons"] if m.get("id") != boss_id and m.get("life", 1) > 0
                   and m.get("dist", 99) <= ACTS_SPELL_REACH and on_screen(m, p)), key=lambda m: m.get("dist", 99))
    if not near:
        return False
    m = near[0]
    sid = acts_build_skill_for(m.get("class"))
    H("skill right %d" % sid)
    casts = STATE.setdefault("acts_casts", {})
    for _ in range(clicks):
        if click_unit(m["id"], "right"):
            casts[sid] = casts.get(sid, 0) + 1
        time.sleep(0.4)
    STATE["acts_blockers"] = STATE.get("acts_blockers", 0) + 1
    return True


def acts_build_row_note(lvl, cls, life0, killed, secs, deaths, quest, q0, q1):
    """The boss row's note for the spell build: the set-up help, the skills used by right clicks, the result."""
    casts = STATE.get("acts_casts", {})
    return ("level %d Sorceress (xp award); %s; given gear: no weapon, a ring (+%d vitality, replenish life, 75 resistances, 50%% "
            "and flat damage reduction, 200%% hit recovery), a ring with %d%% mana regeneration, an amulet%s; boss class %d life %s at "
            "the start; right clicks with the build's skills so far %s; %s after %d s, %d deaths; quest %d bits %s -> %s"
            % (lvl, STATE.get("acts_build_note", "-"), lvl * ACTS_VIT, ACTS_BUILD_MANA_REGEN,
               " (+%d to all skills)" % STATE["acts_plus_skills"] if STATE.get("acts_plus_skills") else "", cls, life0,
               dict(casts), "killed it" if killed else "did not kill it", secs, deaths, quest, q0, q1))


def acts_build_calibrate():
    """Stage `build`: the set-up once, then each main skill right-clicked 6 times at a zombie (class 5, life raised: the target)
    in the Blood Moor: life taken per cast and mana per cast, for the record (INFO; the bosses' verdicts come from their stages)."""
    log, mark = [], engine_mark()
    lvl = acts_level_up(int(os.environ.get("MXL_ACTS_BUILD_LEVEL", "70")))
    note = acts_build_setup(log)  # the level-up spent the points already: its note
    if not STATE.get("acts_build"):
        add("acts build: the spell build", "BLOCKED", "class %s has no build (MXL_CHAR_CLASS=sorceress)" % hstate()["player"].get("class"))
        return
    acts_gear(lvl)
    goto(2)
    out = []
    for sid in ACTS_BUILD_MAIN[STATE["acts_build"]]:
        p = hstate()["player"]
        _ok, sp = Hl("spawn 5 1 %d %d" % (p.get("x", 0) + 5, p.get("y", 0)), log)
        time.sleep(1)
        mon = next((m for m in hstate()["mons"] if m.get("class") == 5), None)
        if mon is None:
            out.append("%d: no zombie" % sid)
            continue
        setstat("mon:%d" % mon["id"], 7, 200000 << 8)
        setstat("mon:%d" % mon["id"], 6, 200000 << 8)
        H("skill right %d" % sid)
        l0, m0 = acts_mon_life(mon["id"]), rd("player", 8)
        n = 0
        for _ in range(6):
            n += 1 if click_unit(mon["id"], "right") else 0
            time.sleep(0.6)
        time.sleep(1.5)
        l1, m1 = acts_mon_life(mon["id"]), rd("player", 8)
        out.append("skill %d: %d clicks, zombie life %s -> %s (%s a click), mana %s -> %s" % (
            sid, n, (l0 or 0) >> 8, (l1 or 0) >> 8, ((l0 or 0) - (l1 or 0)) // 256 // max(n, 1), (m0 or 0) >> 8, (m1 or 0) >> 8))
        H("kill %d" % mon["id"])
        time.sleep(1)
    m0 = rd("player", 8)
    time.sleep(10)
    m1 = rd("player", 8)
    shot = sh("acts_build")
    finish("acts build: the spell build at level %d" % lvl, True, "%s; %s; mana regenerated in 10 s: %s -> %s; max mana %s, max life %s"
           % (note, "; ".join(out), (m0 or 0) >> 8, (m1 or 0) >> 8, (rd("player", 9) or 0) >> 8, (rd("player", 7) or 0) >> 8),
           mark, [shot], log)


def acts_fight(mon_id, timeout=240, ranged=False, focus=False):
    """Fight one monster with the Attack skill (skill 0 through the cast path: the server walks the character up and swings), or
    with the spell build's skills by right clicks (acts_spell_fight) when the character has one. Returns (killed, deaths,
    seconds). A death ends the fight (revived in town); nothing heals the character mid-fight."""
    if STATE.get("acts_build"):
        return acts_spell_fight(mon_id, timeout, focus)
    t0, deaths, last = time.time(), 0, None
    area0 = hstate()["player"].get("area")
    while time.time() - t0 < timeout:
        st = hstate()
        p = st["player"]
        if p and player_dead(p):
            deaths += 1
            STATE["acts_deaths"] = STATE.get("acts_deaths", 0) + 1
            revive_if_dead()
            return False, deaths, int(time.time() - t0)
        if p.get("area") != area0:  # revived elsewhere / moved: the unit is out of reach, not dead
            return False, deaths, int(time.time() - t0)
        life = acts_mon_life(mon_id)  # not the `state` list: it holds the units within 40 only
        if life is not None and life <= 0:  # at 0 life (it stays a moment before its death mode)
            return True, deaths, int(time.time() - t0)
        if life is None:  # gone: a kill only when the last read was already low (a unit whose room unloaded is not dead)
            return (last is not None and last < ACTS_GONE_LOW), deaths, int(time.time() - t0)
        last = life
        if not acts_close_in(mon_id, reach=ACTS_BOW_REACH if ranged else ACTS_MELEE_REACH):
            continue  # died on the way (counted above) or still walking
        H("cast 0 unit %d" % mon_id)
        time.sleep(1.0)
    return False, deaths, int(time.time() - t0)


ACTS_GONE_LOW = 64 * 256  # a unit that vanishes below 64 life died (the corpse is removed); above, its room unloaded (Mephisto
# after the character's death, run checks-20261028-215641-s2: "killed" with 30,200 life left, quest 23 unchanged)
ACTS_BOW_REACH = 30  # a bow shoots from here (the arrival of Durance 3 is 50 from Mephisto)
ACTS_MELEE_REACH = 14  # beyond this the cast path does not walk a melee attacker up: Mephisto at 50 from the Durance 3 arrival
# stood still for 240 s (run checks-20261028-191050-s2, every cast "mode now 1"); it was read as a hit-lock before


def acts_close_in(mon_id, reach=ACTS_MELEE_REACH):
    """Walk (the walk packet's server call, legs of 60, fighting what is in the way) until the monster is within `reach`.
    False when it did not get there in 90 s or the character died."""
    u = parse_moveto(H("moveto %d" % mon_id)[1])
    if u is None:
        return True  # not in the loaded rooms: let the cast try
    p = hstate()["player"]
    if abs(p.get("x", 0) - u["x"]) <= reach and abs(p.get("y", 0) - u["y"]) <= reach:
        return True
    nested = STATE.get("closing_in", False)  # a fight on the way closes in once, without fighting again (no recursion)
    STATE["closing_in"] = True
    try:
        return acts_walk(u["x"], u["y"], reach=reach, timeout=90, fight=not nested, skip=(u["class"],))
    finally:
        STATE["closing_in"] = nested


def acts_find(cls, log, tries=6):
    """The level's own monster of a class: the preset list says where the map puts its units, the character runs there (`move`,
    the walk packet's server call; `place` only when the walk gets stuck), `state` finds the unit. Returns the monster or None."""
    st = hstate()
    area0 = st["player"].get("area")

    def loaded():  # the level's unit of the class when its room is loaded, whatever the distance
        u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1])
        if u:
            u["life"] = acts_mon_life(u["id"])
        return u if u and u.get("life") else None
    mon = loaded()
    if mon:
        return mon
    pres = parse_presets(Hl("presets 1", log)[1])
    first = [p for p in pres if p["class"] == cls] + [p for p in pres if p["class"] != cls]
    for pr in first[:tries]:
        if not acts_walk(pr["x"], pr["y"], reach=25, timeout=180, fight=True, skip=(cls,)):  # the walk loads the rooms on the way
            p = hstate()["player"]
            if player_dead(p) or p.get("area") != area0:
                log.append("the character died on the way to the preset %s (now area %s)" % (pr, p.get("area")))
                return None
            Hl("place %d %d" % (pr["x"], pr["y"]), log)
        time.sleep(2.5)
        mon = loaded()
        if mon:
            log.append("found class %d near preset %s" % (cls, pr))
            return mon
    return None


def acts_boss(stage):
    act, area, cls, level, quest = ACT_BOSSES[stage]
    log, mark = [], engine_mark()
    STATE["acts_plus_skills"] = ACTS_END_PLUS_SKILLS if stage in ("diablo", "baal") and acts_has_build() else 0
    lvl = acts_level_up(level)
    ranged = stage in ACTS_RANGED and not STATE.get("acts_build")  # the spell build reaches across the moat by itself
    gear = (lambda: acts_gear_ranged(lvl, log) or acts_gear(lvl)) if ranged else (lambda: acts_gear(lvl))
    dmg = gear()
    q0 = quest_bits(quest)
    entry = None
    if stage == "baal" and STATE.get("throne_portal"):  # the player's way in: the portal Baal leaves after the waves
        if hstate()["player"].get("area") != 131:  # the throne stage ended with a death (revived in Harrogath)
            goto(131)
        entry = acts_baal_portal(log)
        st = hstate()
    else:
        st = goto(area)
        if stage == "baal":
            entry = ("harness travel `level 132` (help: the waves were not done in this run; it set no quest 40 bit without the "
                     "kill in lane endgame's runs)")
    if st["player"].get("area") != area:
        finish("acts %s: reach level %d" % (stage, area), False, "the character did not get to level %d (area %s)%s" % (
            area, st["player"].get("area"), "; %s" % entry if entry else ""), mark, log=log)
        return False
    seals = acts_open_seals(log) if stage == "diablo" else None
    route = acts_route(BAAL_ROUTE, log) if stage == "baal" and not STATE.get("throne_portal") else None
    if entry:
        log.append("entry: %s" % entry)
    mon = acts_find(cls, log)
    if mon is None and seals and seals.get("centre"):
        sx, sy = seals["centre"]
        how = "walk"
        if not acts_walk(sx, sy, reach=20, timeout=120, fight=True, skip=(cls,)):
            how = "planned walk"
            if not acts_planned_walk(sx, sy, log, budget=600, reach=15):
                how = "not reached"
                if acts_place_near(sx, sy, log):  # travel help, named in the row
                    how = "place (travel help)"
        p = hstate()["player"]
        seals["star"] = "%s, at %s,%s (star %d,%d)" % (how, p.get("x"), p.get("y"), sx, sy)
        for _ in range(40):  # he rises at the pentagram some seconds after the last seal / seal boss
            mon = acts_find(cls, log, tries=0)
            if mon:
                break
            time.sleep(3)
    if mon is None:
        if seals is not None:
            log.append("seals: %s" % seals)
        finish("acts %s: the level's own boss (class %d)" % (stage, cls), False,
               "no unit of class %d found in level %d (presets and places in the log)%s" % (cls, area, "; seals %s" % {
                   k: v for k, v in seals.items() if k not in ("centre", "walk")} if seals else ""), mark, [sh("acts_%s_nofind" % stage)], log)
        return False
    pre_died = False
    if stage in ("baal", "diablo"):  # Baal on the chamber's middle platform, open only to the south (BAAL_ROUTE); Diablo at the
        p = hstate()["player"]  # star, 54 below a character the north corridor's wall held (run checks-20261029-234838-s2)
        if max(abs(p.get("x", 0) - mon["x"]), abs(p.get("y", 0) - mon["y"])) > (12 if stage == "baal" else 30):  # nearer, the
            d_before = STATE.get("acts_deaths", 0)  # fight walks up
            acts_planned_walk(mon["x"], mon["y"] + (6 if stage == "baal" else 0), log, budget=300, reach=10)
            p = hstate()["player"]
            if player_dead(p) or p.get("area") != area:  # died to his pack on the walk (run checks-20261030-030049-s2: Baal's
                if STATE.get("acts_deaths", 0) == d_before:  # minions; the fight then started in town and counted nothing)
                    STATE["acts_deaths"] = d_before + 1
                revive_if_dead()
                pre_died = True
                log.append("died on the walk up to him")

    def reenter():
        """Back into the boss level after a death: for Baal through the throne's portal again when the waves were done in this
        run (a player's way back: Worldstone Keep 3 waypoint, here harness travel to 131, then the portal click)."""
        if stage == "baal" and STATE.get("throne_portal"):
            goto(131)
            log.append("back in: %s" % acts_baal_portal(log))
        else:
            goto(area)

    shot0 = sh("acts_%s_found" % stage)
    fight_s = 600 if STATE.get("acts_build") else 480 if ranged else 240  # the council of Durance 3 comes first
    killed, deaths, secs = (False, 1, 0) if pre_died else acts_fight(mon["id"], fight_s, ranged=ranged, focus=True)
    while not killed and 0 < deaths <= ACTS_BOSS_RETRIES:  # back after a death, as a player does (the corpse run is skipped:
        gear()                                             # the gear is given again); the boss keeps the life it lost
        reenter()
        mon2 = acts_find(cls, log)
        if not mon2:
            break
        log.append("retry %d: boss life %s" % (deaths, mon2.get("life")))
        k2, d2, s2 = acts_fight(mon2["id"], fight_s, ranged=ranged, focus=True)
        killed, deaths, secs = k2, deaths + d2, secs + s2
        if not d2:
            break
    for lost in range(3):  # the unit left the loaded rooms with no death (Diablo walked off the star while the character was
        if killed:  # held at the north wall, run checks-20261029-234838-s2): find him again and walk up on the planned walk
            break
        p = hstate()["player"]
        if player_dead(p) or p.get("area") != area:
            break
        acts_rest(log)  # his pack drove the character to 498 life and 54 away, where his room unloads (run
        if seals and seals.get("centre"):  # checks-20261030-010437-s2): life back, then to the star, where he stays
            sx, sy = seals["centre"]
            if not acts_planned_walk(sx, sy, log, budget=240, reach=20):
                acts_place_near(sx, sy, log)  # travel help, named in the log
        u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1]) or acts_find(cls, log, tries=2)
        if not u or not acts_mon_life(u["id"]):
            log.append("lost %d: no living unit of class %d found" % (lost + 1, cls))
            break
        acts_planned_walk(u["x"], u["y"], log, budget=240, reach=10)
        log.append("lost %d: boss unit %d life %s" % (lost + 1, u["id"], acts_mon_life(u["id"])))
        k2, d2, s2 = acts_fight(u["id"], fight_s, ranged=ranged, focus=True)
        killed, deaths, secs = k2, deaths + d2, secs + s2
        if d2:
            break
    log.extend(STATE.pop("fight_walk_log", []))
    STATE.setdefault("acts_killed", set())
    if killed:
        STATE["acts_killed"].add(stage)
    time.sleep(4)
    q1 = quest_bits(quest)
    note = ("%slevel %d character (xp award), given gear (weapon %d-%d damage, 20%% leech; ring: +%d vitality, replenish life, 75 resistances, 50%% and flat damage reduction, 200%% hit recovery); "
            "boss class %d life %s at the start; Attack skill %s after %d s, %d deaths; quest %d bits %s -> %s"
            % ("bow and arrows (ranged across the moat); " if ranged else "", lvl, dmg, dmg * 2, lvl * ACTS_VIT, cls, mon.get("life"), "killed it" if killed else "did not kill it", secs, deaths, quest, q0, q1))
    if STATE.get("acts_build"):
        note = acts_build_row_note(lvl, cls, mon.get("life"), killed, secs, deaths, quest, q0, q1)
    note += "; " + acts_load_note()
    if seals is not None:
        note += "; seals %s" % {k: v for k, v in seals.items() if k != "centre"}
    if route is not None:
        note += "; route to him %s" % route
    if entry:
        note += "; way in: %s" % entry
    finish("acts %s: boss fight in level %d" % (stage, area), killed and q1 != q0, note, mark, [shot0, sh("acts_%s_after" % stage)], log)
    return killed


DIABLO_SEALS = (392, 393, 394, 395, 396)  # objects.txt: the five Chaos Sanctuary seals (OperateFn 54 / 52 / 55 / 52 / 56)


DIABLO_START = 255  # objects: the Diablo start point (the pentagram's middle), in Median's heart.ds1 at (53, 53)
CHAOS_STAR = (7793, 5293)  # where it stood in every run (lane acts3), used when `presets 2` does not list it
# The seals in the wing maps of the Chaos Sanctuary (lvlprest 858 / 861 / 859, Median's act4/diab/wing*.ds1, act 4 object ids
# 47-51 = objects 392-396; two variants per wing, one chosen per game), as offsets from the heart map's origin (the start point
# minus (53, 53)); each wing is a 24 x 24 tile map (120 sub-tiles) next to the heart: W at x - 120, N at y - 120, E at x + 120.
# Wing: (offsets, seals in the wing): Vizier W 50 / 51 at (35, 35) and (35, 75) in both; De Seis N 49 at (33, 35) or (75, 35);
# Infector E 48 at (55, 35), 47 at (55, 75) or (33, 73).
SEAL_WINGS = (("vizier", ((-85, 35), (-85, 75)), 2), ("infector", ((175, 35), (175, 75), (153, 73)), 2),
              ("seis", ((33, -85), (75, -85)), 1))
# De Seis's wing last (lane acts5, checks-20261029-093507-s2): the walk back out of it stuck for 15 minutes at 7790-7810,
# 5187-5240 next to a pack member that never moved (unit 146 at 7774, 5215) and the Infector wing was never reached
# The way from the start point into each wing, as offsets from the start point: the corridors leave the heart in the middle of
# its sides (the walk to the Vizier went 7803,5303 -> 7746,5290 -> 7711,5294 -> 7662,5281, run checks-20261028-233533-s2); the
# straight walk back out of a wing got stuck for 20 minutes, so every wing is left by the same legs backwards. North: no free
# spot at 7793,5165; the walk stood at 7810,5179 (run checks-20261029-002644-s2).
SEAL_CLASSES = {"vizier": (395, 396), "seis": (394,), "infector": (392, 393)}
# North (lane acts5): Median's wingn1 / wingn2.ds1 have a wall along tile row 13 (wingn1, x tiles 6-12) or row 10 (wingn2, 10-12),
# i.e. y 5185 / 5170 at x 7770-7805: the straight walk north stopped at 7794, 5187 in both runs of 2026-10-29 (the seal was
# reached only by `place` once, and `place` found no spot the next time). wingn1 also has walls along tile rows 18-19 at x tiles
# 10-15 (x 7790-7815, y 5210-5220): the way up east at x 7822 was refused at 7821, 5223 for 3 minutes and crossed only by
# `place` (run checks-20261029-124850-s2). The opening is west of them, x tiles 6-9 (x 7770-7790), where De Seis's pack
# spawns and walks (units at 7768-7800, 5195-5221 in that run); wingn2's stub at x tiles 6-7, row 18 leaves x 7786 clear.
# Then up east of the row-13 wall (x 7808-7820, walked in that run) and back west along row 8 (y 5160).
SEAL_ROUTES = {"vizier": ((-48, 0), (-78, 1), (-103, -1), (-128, -3)), "seis": ((0, -48), (-7, -61), (-7, -81), (-5, -95), (19, -98),
                                                                               (23, -115), (27, -128), (2, -133)),
               "infector": ((48, 0), (78, 1), (103, -1), (128, -3))}


SEALS_BUDGET_S = 3600  # the whole seal walk (30 min skipped the Infector wing, run checks-20261029-081719-s1); a wing not started by then is skipped (named in the row)
SEAL_CLICK_UP = (0, 30, 60, 90)  # pixels above a seal's foot for the clicks (run checks-20261028-233533-s2: the foot did nothing)


def seal_spots(log):
    """[(wing, seals in it, [(x, y) spots])] of this game's Chaos Sanctuary, from the start point's preset (CHAOS_STAR without)."""
    star = [q for q in parse_presets(Hl("presets 2", log)[1]) if q["class"] == DIABLO_START]
    sx, sy = (star[0]["x"], star[0]["y"]) if star else CHAOS_STAR
    hx, hy = sx - 53, sy - 53
    return [(wing, n, [(hx + dx, hy + dy) for dx, dy in offs], [(sx + dx, sy + dy) for dx, dy in SEAL_ROUTES[wing]])
            for wing, offs, n in SEAL_WINGS], (sx, sy)


def acts_rest(log, frac=0.7, wait_s=150):
    """Wait (out of the fight, the given ring's replenish life) until the character's life is back to `frac` of its top, at
    most `wait_s` seconds, as a player waits before going back in. Returns the life fraction reached."""
    t0 = time.time()
    while time.time() - t0 < wait_s:
        p = hstate()["player"]
        m = re.match(r"(\d+)/(\d+)", str(p.get("life", "")))
        if not m or player_dead(p) or int(m.group(1)) >= frac * int(m.group(2)):
            break
        time.sleep(3)
    p = hstate()["player"]
    log.append("rested %d s, life %s" % (time.time() - t0, p.get("life")))
    return p.get("life")


def acts_planned_walk(tx, ty, log, budget=300, reach=10, rounds=4):
    """Lane endgame: left clicks to (tx, ty) on paths planned on the game's own walk collision (relp_walk_to over `walkmap`,
    merged as the walk goes), fighting what comes near before each waypoint. The straight `move` legs and the search walk
    stayed pinned at the Chaos Sanctuary's wing walls for 10-50 minutes (lane acts5: 7812,5201; 7804-7819,5223-5260; the pocket
    at 7716-7739,5255-5320), as the click search did at Hratli's house (bug #434, lane bugsweep). True when within `reach`."""
    import playthrough as pt
    c = pt.Ctx(sys.modules[__name__], 0, log)
    area0 = c.player().get("area")

    def there():
        p = c.player()
        return abs(p.get("x", 0) - tx) <= reach and abs(p.get("y", 0) - ty) <= reach

    def fight():
        if hostiles_near(hstate(), 14):
            acts_clear(14)

    t0 = time.time()
    for _ in range(rounds):
        left = budget - (time.time() - t0)
        if there() or left < 20:
            break
        H("skill left 0")  # a left click on the ground walks, on a monster it attacks
        relp_walk_to(c, tx, ty, there, log, budget=left, fight=fight)
        p = c.player()
        if player_dead(p) or p.get("area") != area0:
            break
    p = c.player()
    log.append("planned walk to %d,%d: %s after %d s (at %s,%s)" % (tx, ty, "there" if there() else "not there", time.time() - t0,
                                                                   p.get("x"), p.get("y")))
    return there()


def acts_legs(points, out, log, walk_s=60):
    """Walk through the points in order (fighting on the way); a leg the walk does not finish in walk_s goes by the planned walk
    (acts_planned_walk), then the search walk, then it is placed (acts_place_near, travel help, counted in out["placed"]). False
    when the character died."""
    for x, y in points:
        if acts_walk(x, y, reach=8, timeout=walk_s, fight=True):
            continue
        p = hstate()["player"]
        if player_dead(p) or p.get("area") != 108:
            return False
        if acts_planned_walk(x, y, log, budget=max(walk_s * 3, 60), reach=8):
            out["planned"] = out.get("planned", 0) + 1
            continue
        p = hstate()["player"]
        if player_dead(p) or p.get("area") != 108:
            return False
        if acts_search_walk(x, y, log, budget_s=max(walk_s * 3, 1)):
            out["searched"] = out.get("searched", 0) + 1
            continue
        if acts_walk_back(log) and acts_walk(x, y, reach=8, timeout=walk_s, fight=True):
            out["walked_back"] = out.get("walked_back", 0) + 1
            continue
        if acts_place_near(x, y, log):
            out["placed"] = out.get("placed", 0) + 1
        elif out.get("centre") and acts_place_near(out["centre"][0], out["centre"][1], log):  # the leg's room is not loaded:
            out["placed"] = out.get("placed", 0) + 1  # back to the pentagram first (run checks-20261029-060640-s4: 19 min against
            if acts_walk(x, y, reach=8, timeout=walk_s, fight=True) or acts_place_near(x, y, log):  # the west wing's wall)
                out["placed"] += 1
    return True


def acts_walk_back(log, n=12, walk_s=15):
    """Walk back along the last spots the walks passed (STATE["crumbs"]), newest first: run checks-20261029-115315-s2 was pinned
    for 20 minutes at 7709-7739, 5266-5269 north of the Vizier corridor after a fight pulled it there, every walk east refused
    and `place` answering OK without moving the player (bug #438). Returns the number of crumbs reached."""
    p = hstate()["player"]
    area = p.get("area")
    got = 0
    for x, y, a in reversed(STATE.get("crumbs", [])[-n:]):
        if a != area or max(abs(x - p.get("x", 0)), abs(y - p.get("y", 0))) < 6:
            continue
        if acts_walk(x, y, reach=5, timeout=walk_s):
            got += 1
        p = hstate()["player"]
    log.append("walked back along %d of the last %d spots, now at %s,%s" % (got, n, p.get("x"), p.get("y")))
    return got


def click_object(obj, button="left", up_px=0):
    """A background click on an object's spot (screen offsets as click_unit), `up_px` pixels above its foot (the sprite a player
    points at is drawn above it). False when it is off the screen."""
    p = hstate()["player"]
    dx, dy = obj["x"] - p.get("x", 0), obj["y"] - p.get("y", 0)
    fx, fy = (800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5 - up_px) / 900
    if not (0.03 < fx < 0.97 and 0.05 < fy < 0.85):
        return False
    g.click(fx, fy, button=button)
    return True


def acts_open_seals(log):
    """Chaos Sanctuary (108): Diablo is no map unit; the quest code calls him when all five seals are open. `level 108` puts the
    character at the pentagram, and a seal is listed only once its room is loaded: walk (fighting what comes) to the seal spots
    of the wing maps (seal_spots), click each seal found there (a background left click on it; the interact packet 0x13, then
    the object's own OperateFn by harness, only when the click did not change its mode: named), fight what it called (the seal
    bosses). Returns {"found", "opened", "modes", "deaths", "centre", "walk"}."""
    wings, star = seal_spots(log)
    out = {"found": [], "opened": [], "modes": {}, "deaths": 0, "centre": star, "walk": [], "placed": 0}
    fns = {int(r.get("*ID") or -1): int(r.get("OperateFn") or 0) for r in table("objects") if (r.get("*ID") or "").isdigit()}
    done, t_start = set(), time.time()
    for wing, n, spots, route in wings:
        if time.time() - t_start > SEALS_BUDGET_S:
            out.setdefault("skipped", []).append(wing)
            continue
        got, pending = 0, []
        if not acts_legs(route, out, log):  # into the wing
            out["deaths"] += 1
            revive_if_dead()
            acts_gear(hstate()["player"].get("level", 80))
            goto(108)
            acts_legs(route, out, log)
        for x, y in spots:
            if got >= n:
                break
            ok = acts_walk(x, y, reach=8, timeout=120, fight=True)
            p = hstate()["player"]
            if not ok and (player_dead(p) or p.get("area") != 108):
                out["deaths"] += 1
                revive_if_dead()
                acts_gear(hstate()["player"].get("level", 80))
                goto(108)
                acts_legs(route, out, log)
                ok = acts_walk(x, y, reach=8, timeout=120, fight=True)
            p = hstate()["player"]
            out["walk"].append((wing, (x, y), ok, (p.get("x"), p.get("y"))))
            near = [o for o in parse_objects(Hl("objects", log)[1]) if o["class"] in SEAL_CLASSES[wing] and o["id"] not in done]
            # any seal of the wing whose room is loaded, wherever the walk ended (the spot itself may be out of reach)
            for obj in near:
                done.add(obj["id"])
                got += 1
                out["found"].append(obj["class"])
                if obj["mode"] != 0:  # open before any click (seal 396 stood in mode 2 at the first look, run checks-20261028-233533-s2)
                    out["modes"][obj["class"]] = (obj["mode"], obj["mode"], "open already")
                    out["opened"].append(obj["class"])
                    continue
                if not acts_walk(obj["x"], obj["y"] + 2, reach=3, timeout=90, fight=True):
                    q = hstate()["player"]
                    if not player_dead(q) and q.get("area") == 108 and abs(q.get("x", 0) - obj["x"]) + abs(q.get("y", 0) - obj["y"]) > 12:
                        Hl("place %d %d" % (obj["x"], obj["y"] + 3), log)  # travel help, counted
                        out["placed"] += 1
                        time.sleep(1.5)
                after, how = {}, None
                H("skill left 0")  # a left click on an object with Attack on the left button uses it
                for up in SEAL_CLICK_UP:  # a background left click on the seal, at its foot and higher up its sprite
                    if not click_object(obj, up_px=up):
                        continue
                    time.sleep(3)
                    after = seal_now(obj, log)
                    if after.get("mode") not in (None, obj["mode"]):
                        how = "mouse click (%d px above its foot)" % up
                        break
                if how is None:
                    Hl("pkt 13 " + _le(2, obj["id"]), log)  # the click's interact packet 0x13 (unit type 2 = object, id)
                    how = "click packet (the mouse clicks did not open it)"
                    time.sleep(3)
                    after = seal_now(obj, log)
                if after.get("mode") == obj["mode"]:  # not used by the packet: the object's own operate function (harness, named)
                    Hl("operate %d %d" % (obj["id"], fns.get(obj["class"], 52)), log)
                    time.sleep(3)
                    after = seal_now(obj, log)
                    how = "harness operate"
                if after.get("mode") is None:  # not listed after the click (run checks-20261029-072606-s1: seal 394 read as
                    p2 = hstate()["player"]  # "opened" with no mode, De Seis never came): stand at it and read again
                    Hl("place %d %d" % (obj["x"], obj["y"] + 3), log)
                    out["placed"] += 1
                    time.sleep(2)
                    after = seal_now(obj, log)
                    if after.get("mode") == obj["mode"]:
                        Hl("pkt 13 " + _le(2, after["id"]), log)
                        time.sleep(3)
                        after = seal_now(obj, log)
                        how = "click packet after standing at it (from %s, %s)" % (p2.get("x"), p2.get("y"))
                out["modes"][obj["class"]] = (obj["mode"], after.get("mode"), how)
                if after.get("mode") not in (None, obj["mode"]):
                    out["opened"].append(obj["class"])
                else:
                    pending.append(obj)
                killed, deaths = fight_all(seal_boss_classes(), log, timeout=240)  # the seal's boss and its pack, when it called one
                out.setdefault("killed", []).extend(killed)
                out["deaths"] += deaths
                if deaths:
                    acts_gear(hstate()["player"].get("level", 80))
                    goto(108)
                    acts_legs(route, out, log)
        for obj in pending:  # a seal the clicks did not open (393 not listed after the click packet, run
            acts_seal_retry(obj, out, log)  # checks-20261029-110311-s2: Diablo waits for all five): once more at its foot
        p = hstate()["player"]
        if p.get("area") == 108 and not player_dead(p):
            acts_seal_bosses(wing, out, log, route=route)  # the wing's boss before leaving it: Diablo waits for all three (see below)
        p = hstate()["player"]
        if p.get("area") == 108 and not player_dead(p):  # back to the heart: the walk out of a wing got stuck in every run
            acts_legs(list(reversed(route)), out, log, walk_s=40)  # (the Vizier's: runs checks-20261029-002644-s2 ..
    out["quest26"] = quest_bits(26)  # checks-20261029-021145-s2); back along the route's legs, as `place` reaches only loaded
    return out  # rooms (one far `place` to the heart failed in run checks-20261029-021145-s2)


# The seal bosses (superuniques.txt rows by name -> their monstats class): the seals with OperateFn 54 / 55 / 56 (392 Infector,
# 394 De Seis, 396 Vizier) call them. In run checks-20261029-025925-s2 all five seals went 0 -> 2 by the mouse click (they were
# closed when first listed; the row's "open at first sight" read the mode after the click) and Diablo never came: the boss pack
# fight after each seal skipped the Infector (unit 107, class 1763) after it took no damage. D2 calls Diablo only when the seal
# bosses are dead as well, so each wing's boss is hunted by class before the walk back.
SEAL_BOSS_NAMES = {"infector": "Infector of Souls", "seis": "Lord De Seis", "vizier": "Grand Vizier of Chaos"}


def seal_boss_classes(wing=None):
    """monstats classes of the seal bosses (all three, or the wing's), from the built superuniques table."""
    if "seal_bosses" not in STATE:
        ids = {r.get("Id") or r.get("﻿Id"): i for i, r in enumerate(table("monstats"))}
        found = {}
        for r in table("superuniques"):
            for w, name in SEAL_BOSS_NAMES.items():
                if r.get("Superunique") == name and r.get("Class") in ids:
                    found[w] = ids[r["Class"]]
        STATE["seal_bosses"] = found
    found = STATE["seal_bosses"]
    return tuple(found[w] for w in ([wing] if wing else SEAL_BOSS_NAMES) if w in found)


def acts_seal_bosses(wing, out, log, timeout=600, route=()):  # Lord De Seis: cold immune, Arcane Torrent (lane acts5)
    """Hunt the wing's seal boss class (moveto nearest, the spell / Attack fight) until no living unit of it is loaded. A unit
    the walks cannot reach from the wing is tried again from each point of the wing's route (acts_boss_from_route). Records
    {class: "killed n" / "alive" / "not seen"} in out["bosses"]."""
    t0 = time.time()
    for cls in seal_boss_classes(wing):
        acts_boss_hunt(cls, wing, out, log, t0, timeout)
        u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1])
        if u and acts_mon_life(u["id"]) and route:
            out.setdefault("from_route", []).append(acts_boss_from_route(cls, route, out, log))
        u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1])
        if u and acts_mon_life(u["id"]):
            out.setdefault("bosses", {})[cls] = "alive"
        elif out.get("bosses", {}).get(cls) == "alive":  # gone without a seen kill: killed from the route, or the Sanctum clear
            out["bosses"][cls] = "none left (the last from the route, or gone: %s)" % (out.get("from_route") or ["-"])[-1]


def acts_boss_from_route(cls, route, out, log, per_point=90):
    """Lane acts5, run checks of 2026-10-29 (De Seis wing): a pack member of class 1699 stood at 7774, 5215, between the wing
    and the heart, and every walk from the wing to it was refused for 10 minutes (life unchanged). Walk the route's points from
    the wing back to the heart and fight each living unit of the class that is in spell reach from there. Returns a note."""
    kills, tried, notes = 0, 0, []
    for x, y in reversed(route):
        acts_walk(x, y, reach=8, timeout=60, fight=True)
        p = hstate()["player"]
        if player_dead(p) or p.get("area") != 108:
            break
        while True:
            u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1])
            if not u or not acts_mon_life(u["id"]):
                return "class %d: none left after %d kills from the route" % (cls, kills)
            if max(abs(p.get("x", 0) - u["x"]), abs(p.get("y", 0) - u["y"])) > 40:
                break
            tried += 1
            res = acts_cast_from_here(u, per_point)
            notes.append(res)
            if res.startswith("died"):
                revive_if_dead()
                acts_gear(hstate()["player"].get("level", 80))
                out["deaths"] += 1
                return "class %d: died on the route (%d kills; %s)" % (cls, kills, notes)
            if not res.startswith("killed"):
                break
            kills += 1
            p = hstate()["player"]
    for _ in range(6):  # still alive: spots around the unit itself (run checks-20261029-124915-s2: unit 129 at 7770, 5221 was off
        u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1])  # the screen from every route point)
        if not u or not acts_mon_life(u["id"]):
            return "class %d: none left after %d kills (route and spots around it; %s)" % (cls, kills, notes)
        res = None
        for dx, dy in RING_SPOTS:
            acts_walk(u["x"] + dx, u["y"] + dy, reach=3, timeout=25)
            p = hstate()["player"]
            if player_dead(p) or p.get("area") != 108:
                return "class %d: died near it (%d kills; %s)" % (cls, kills, notes)
            if max(abs(p.get("x", 0) - u["x"]), abs(p.get("y", 0) - u["y"])) <= 14:
                res = acts_cast_from_here(u, per_point)
                notes.append("from %d,%d: %s" % (p.get("x", 0), p.get("y", 0), res))
                if res.startswith("killed") or res.startswith("died"):
                    break
        if not res or not res.startswith("killed"):
            break
        kills += 1
    return "class %d: %d kills from the route, %d tries, still alive (%s)" % (cls, kills, tried, notes)


RING_SPOTS = ((10, 0), (0, 10), (-10, 0), (0, -10), (7, 7), (-7, 7), (7, -7), (-7, -7))


def acts_cast_from_here(u, secs):
    """Right-click the build's skill at the unit from where the character stands (no walk up: the unit may stand where no walk
    goes), while its spot is on the screen. Returns "killed ...", "died ..." or "life a -> b, n clicks"."""
    sid = acts_build_skill_for(u.get("class"))
    H("skill right %d" % sid)
    casts = STATE.setdefault("acts_casts", {})
    l0 = acts_mon_life(u["id"])
    n, t0 = 0, time.time()
    while time.time() - t0 < secs:
        p = hstate()["player"]
        if player_dead(p):
            STATE["acts_deaths"] = STATE.get("acts_deaths", 0) + 1
            return "died after %d clicks" % n
        life = acts_mon_life(u["id"])
        if not life:
            return "killed unit %d by %d clicks from %d,%d" % (u["id"], n, p.get("x", 0), p.get("y", 0))
        if not on_screen({"mx": u["x"], "my": u["y"]}, p) or not click_unit(u["id"], "right"):
            return "unit %d at %d,%d off the screen from %d,%d" % (u["id"], u["x"], u["y"], p.get("x", 0), p.get("y", 0))
        n += 1
        casts[sid] = casts.get(sid, 0) + 1
        time.sleep(0.4)
    return "unit %d life %s -> %s after %d clicks of skill %d" % (u["id"], (l0 or 0) >> 8, (acts_mon_life(u["id"]) or 0) >> 8, n, sid)


def acts_boss_hunt(cls, wing, out, log, t0, timeout):
    """The hunt of one seal boss class from where the character stands (moveto nearest, fight) until none is left or a fight
    does not kill."""
    kills, seen = 0, False
    while time.time() - t0 < timeout:
        u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1])
        life = acts_mon_life(u["id"]) if u else None
        if not u or not life:
            break
        seen = True
        k, d, _s = acts_fight(u["id"], max(30, min(240, int(timeout - (time.time() - t0)))), focus=True)  # one unit out of reach
        # (behind a wall) must not take the whole budget: the route retry comes after
        out["deaths"] += d
        if d:
            revive_if_dead()
            acts_gear(hstate()["player"].get("level", 80))
            break
        kills += 1 if k else 0
        if not k:
            break
    u = parse_moveto(Hl("moveto nearest %d" % cls, log)[1])
    alive = bool(u and acts_mon_life(u["id"]))
    out.setdefault("bosses", {})[cls] = "alive" if alive else ("killed %d" % kills if kills or seen else "not seen")


def acts_seal_retry(obj, out, log):
    """Second try at a seal that did not open: walk to its foot (travel help `place` when the walk fails, counted), list it,
    background left clicks at its foot and higher up. Updates out["modes"] / out["opened"]."""
    if not acts_walk(obj["x"], obj["y"] + 2, reach=3, timeout=60, fight=True):
        if Hl("place %d %d" % (obj["x"], obj["y"] + 3), log)[0]:
            out["placed"] += 1
        time.sleep(2)
    now = seal_now(obj, log)
    how = "second try: not listed at its foot"
    if now.get("mode") == 0:
        H("skill left 0")
        how = "second try: clicks did nothing"
        for up in SEAL_CLICK_UP:
            if click_object(now, up_px=up):
                time.sleep(3)
                if seal_now(obj, log).get("mode") not in (None, 0):
                    how = "second try: mouse click (%d px above its foot)" % up
                    out["opened"].append(obj["class"])
                    break
    elif now.get("mode") not in (None,):
        how = "second try: found in mode %d" % now["mode"]
        out["opened"].append(obj["class"])
    out["modes"][obj["class"]] = out["modes"].get(obj["class"], ()) + (how,)
    killed, deaths = fight_all(seal_boss_classes(), log, timeout=240)
    out.setdefault("killed", []).extend(killed)
    out["deaths"] += deaths


def seal_now(obj, log):
    """The seal as listed now: the object of its class on its spot (the unit id changes when its room is reloaded: 395 was 77,
    then 353 in run checks-20261029-072606-s1); {} when it is not listed."""
    return next((o for o in parse_objects(Hl("objects %d" % obj["class"], log)[1])
                 if abs(o["x"] - obj["x"]) <= 2 and abs(o["y"] - obj["y"]) <= 2), {})


def acts_place_near(x, y, log):
    """`place` at the spot or one of four spots next to it (travel help). True when one was taken and the player is there (bug
    #438: `place` answered OK with the player still 60 away, run checks-20261029-115315-s2)."""
    for dx, dy in ((0, 0), (-5, 5), (5, 5), (0, 10), (5, -5)):
        if Hl("place %d %d" % (x + dx, y + dy), log)[0]:
            time.sleep(1.5)
            p = hstate()["player"]
            if max(abs(p.get("x", 0) - x - dx), abs(p.get("y", 0) - y - dy)) <= 12:
                return True
    return False


def acts_town_sweep(act, log):
    """One round of legs around the town's arrival (EXPLORE_LEGS, back to the arrival between legs): where each of the town's
    NPCs stands ({class: (x, y)}, from the `state` units within 40 of the character). The NPC walks then go straight there."""
    p0 = hstate()["player"]
    seen = {}
    STATE["walk_spots"] = seen
    try:
        acts_walk(p0["x"], p0["y"], reach=99, timeout=5)  # the units around the arrival
        for dx, dy in EXPLORE_LEGS:
            if all(c in seen for c in TOWN_NPCS[act]):
                break
            acts_walk(p0["x"] + dx, p0["y"] + dy, reach=15, timeout=40)
    finally:
        STATE.pop("walk_spots", None)
    spots = {c: xy for c, xy in seen.items() if c in TOWN_NPCS[act]}
    log.append("town sweep act %d: %s" % (act, spots))
    return spots


def acts_town(act):
    """One town: every NPC answers a talk with its menu; the waypoint object stands there and its panel opens."""
    town = ACT_TOWNS[act]
    log, mark = [], engine_mark()
    st = goto(town)
    if st["player"].get("area") != town:
        finish("acts town act %d" % act, False, "the character did not get to area %d" % town, mark, log=log)
        return {}
    talked, silent, menus = [], [], {}
    spots = acts_town_sweep(act, log)
    for cls, name in TOWN_NPCS[act].items():
        menu = acts_menu(cls, spot=spots.get(cls), explore=False)
        if menu is None:
            silent.append(name)
            continue
        menus[cls] = menu
        talked.append("%s(%s)" % (name, ",".join("%x" % s for _i, s, _h in menu["lines"])))
        log.append("%s menu %s" % (name, menu))
        close_menu()
        time.sleep(1)
    wps = parse_objects(Hl("objects %d" % TOWN_WAYPOINT_OBJ[act], log)[1])
    if not wps:
        wp = [q for q in parse_presets(Hl("presets 2", log)[1]) if q["class"] == TOWN_WAYPOINT_OBJ[act]]
        if wp:
            acts_walk(wp[0]["x"], wp[0]["y"], reach=10)
            wps = parse_objects(Hl("objects %d" % TOWN_WAYPOINT_OBJ[act], log)[1])
    if wps:
        acts_walk(wps[0]["x"] + 2, wps[0]["y"] + 2, reach=4, timeout=40)
        Hl("operate %d 23" % wps[0]["id"], log)  # objects.txt OperateFn 23, as the click on the waypoint does
        time.sleep(2)
    Hl("waypoint open", log)
    time.sleep(2)
    wshot = sh("acts_town%d_waypoint" % act)
    g.press("esc")
    time.sleep(1)
    finish("acts town act %d (area %d)" % (act, town), not silent and bool(wps),
           "talked (menu string ids): %s; no menu: %s; waypoint objects of class %d: %d; waypoint panel %s"
           % ("; ".join(talked), ", ".join(silent) or "none", TOWN_WAYPOINT_OBJ[act], len(wps), wshot), mark, [wshot], log)
    return menus


# Talks the act's last quest needs before the travel line: (area, NPC class, where to look, quest whose bits are logged).
# Tyrael (tyrael1) is no preset the `presets` list shows in Duriel's Lair: Median's own act2/tomb/duriel.ds1 puts him 57 west and
# 130 north of Duriel's preset (ds1 objects (78, 88) and (135, 218)). Jerhyn is no map unit either: Lut Gholein's maps
# (lut2 / lutn / lutw) hold two placeholder objects, 121 (outside the palace) and 122 (inside), where the quest code puts him.
# D2R's Meshif line ("sail east") and its server gate need quest 14 (The Seven Tombs) bit 0, set by the Jerhyn talk after Duriel.
DURIEL_TO_TYRAEL = (-57, -130)
JERHYN_SPOTS = (122, 121)  # objects: Jerhyn's placeholders, inside the palace first (after Duriel he waits there)
# NPCs a `moveto` from the arrival does not path to: the map's own spot (Lut Gholein's maps lut2 / lutn / lutw put Meshif at
# (213, 78), the town's origin is 5000, 5000: Warriv's preset (146, 200) is at 5146, 5200)
TOWN_NPC_SPOTS = {(40, 210): (5213, 5078)}
JERHYN_MAP_SPOTS = ((5071, 5148), (5147, 5191))  # the placeholders of lutn / lutw ((71, 148), (147, 191)) when `presets 2`
# does not list them (the rooms already placed their objects: run of lane acts2 22:00)
ACT_END_TALKS = {"travel23": ((73, 251, "tyrael", 14), (40, 201, "jerhyn", 14)), "travel45": ((103, 367, None, 26),)}


def acts_talk_spots(kind, log):
    """Where to walk for an end-of-act talk: [(x, y)] in `state` units, nearest guess first."""
    if kind == "tyrael":
        dur = [q for q in parse_presets(Hl("presets 1", log)[1]) if q["class"] == ACT_BOSSES["duriel"][2]]
        return [(d["x"] + DURIEL_TO_TYRAEL[0], d["y"] + DURIEL_TO_TYRAEL[1]) for d in dur[:1]]
    if kind == "jerhyn":
        objs = parse_presets(Hl("presets 2", log)[1])
        return [(q["x"], q["y"]) for c in JERHYN_SPOTS for q in objs if q["class"] == c] or list(JERHYN_MAP_SPOTS)
    return []


def acts_end_talk(area, who, kind, quest, log):
    """Walk to the NPC (to its spot, fighting on the way; `place` there only when the walk gets stuck: travel help), talk, wait
    for the speech and the menu. Logs the quest bits before and after. Returns the menu or None."""
    goto(area)
    q0 = quest_bits(quest)
    if kind == "tyrael":  # Duriel is back at the lair's arrival in every new game: a player kills him again first
        acts_gear(acts_level_up(ACT_BOSSES["duriel"][3]))
        dur = acts_find(ACT_BOSSES["duriel"][2], log, tries=1)
        if dur:
            k, d, secs = acts_fight(dur["id"])
            log.append("the lair's Duriel first: killed %s, deaths %d, %d s" % (k, d, secs))
            if not k:
                return None
    unit = None
    for x, y in acts_talk_spots(kind, log):
        unit = parse_moveto(Hl("moveto nearest %d" % who, log)[1])
        if unit:
            break
        if not acts_walk(x, y, reach=12, timeout=150, fight=True):
            p = hstate()["player"]
            if player_dead(p) or p.get("area") != area:
                log.append("the walk to %s ended in area %s (dead: %s)" % (kind, p.get("area"), player_dead(p)))
                return None
            Hl("place %d %d" % (x, y), log)
            time.sleep(2)
    unit = unit or parse_moveto(Hl("moveto nearest %d" % who, log)[1])
    m = acts_menu(who, spot=(unit["x"], unit["y"]) if unit else None)  # Jerhyn after Duriel: inside the palace, (5080, 5151)
    time.sleep(3)
    log.append("talk to %d in area %d: menu %s; quest %d bits %s -> %s" % (who, area, m, quest, q0, quest_bits(quest)))
    close_menu()
    time.sleep(1)
    return m


def acts_travel(stage):
    """Act travel through the NPC's menu: first the line the quest added (against the menu `towns` kept), then every line;
    passes when the character arrives in the next town. travel45: then Tyrael's red portal (object 566) by mouse click."""
    frm, npc, dest = ACT_TRAVEL[stage]
    log, mark = [], engine_mark()
    talks = []
    for area, who, kind, quest in ACT_END_TALKS.get(stage, ()):  # the quest's own dialogs (Tyrael in Duriel's lair, Jerhyn)
        talks.append("%d:%s" % (who, "menu" if acts_end_talk(area, who, kind, quest, log) else "none"))
    goto(frm)
    menu = acts_menu(npc, spot=TOWN_NPC_SPOTS.get((frm, npc)))
    if menu is None:
        finish("acts %s: NPC %d menu" % (stage, npc), False, "no menu after the talk", mark, log=log)
        return False
    log.append("menu %s" % (menu,))
    before = STATE.get("menus", {}).get(npc)
    added = new_menu_lines(before, menu)
    order = list(dict.fromkeys([i for i, _s in added] + [i for i, _s, _h in reversed(menu["lines"])]))
    tried = []
    for i in order:
        if hstate()["player"].get("area") != frm or (tried and acts_menu(npc, spot=TOWN_NPC_SPOTS.get((frm, npc))) is None):
            break
        g.hcmd("menu %d" % i, 5)
        tried.append(i)
        for _ in range(10):
            time.sleep(2)
            if hstate()["player"].get("area") == dest:
                break
        if hstate()["player"].get("area") == dest:
            break
        g.press("esc")  # a Talk / Trade line opened a panel
        time.sleep(1)
    portal = ""
    if stage == "travel45" and hstate()["player"].get("area") != dest:  # LoD: no menu line; Tyrael opens a red portal
        portal = "; " + acts_click_portal(TYRAEL_PORTAL, frm, dest, log)
    area = hstate()["player"].get("area")
    if area == dest:
        time.sleep(5)  # the act change's loading screen (run checks-20261030-075910-s3's shot was black)
    finish("acts %s: travel by NPC %d's %s" % (stage, npc, "portal" if portal else "menu"), area == dest,
           "talks first %s (quest bits in the log); menu lines %s, new since the start %s, tried %s, now in area %s (want %d)%s" % (
               talks, [(i, "%x" % s) for i, s, _h in menu["lines"]], [(i, "%x" % s) for i, s in added], tried, area, dest, portal),
           mark, [sh("acts_%s" % stage)], log)
    return area == dest


TYRAEL_PORTAL = 566  # objects: NotKiddingLastPortal "Harrogath" (OperateFn 73), the red portal by Tyrael after Diablo's death;
# Tyrael's menu keeps Talk only (LoD has no travel line on him; run checks-20261030-075529-s3, acts_travel45.png)


def acts_click_portal(cls, frm, dest, log):
    """Walk up to the nearest object `cls` and take it by background left clicks on it (then the click packet 0x13, named).
    Returns a note; the caller reads the area."""
    objs = [o for o in parse_objects(Hl("objects %d" % cls, log)[1])]
    if not objs:
        return "no object %d in area %d" % (cls, frm)
    obj = objs[0]
    if not acts_walk(obj["x"], obj["y"] + 3, reach=4, timeout=60):
        acts_planned_walk(obj["x"], obj["y"] + 3, log, budget=120, reach=5)
    H("skill left 0")
    for up in (0, 40, 80, 120):
        if click_object(obj, up_px=up):
            for _ in range(4):
                time.sleep(2)
                if hstate()["player"].get("area") == dest:
                    return "portal %d at %d,%d by a mouse click %d px above its foot" % (cls, obj["x"], obj["y"], up)
    Hl("pkt 13 " + _le(2, obj["id"]), log)
    for _ in range(4):
        time.sleep(2)
        if hstate()["player"].get("area") == dest:
            return "portal %d by the click packet 0x13 (the mouse clicks did not take the character)" % cls
    p = hstate()["player"]
    return "portal %d at %d,%d (mode %s): clicks and the click packet did not take the character (at %s,%s, area %s)" % (
        cls, obj["x"], obj["y"], obj.get("mode"), p.get("x"), p.get("y"), p.get("area"))


ACT4_GATE = 342  # objects: the portal Mephisto's death opens in Durance of Hate 3 (OperateFn 46)


def acts_portal_a4():
    """After Mephisto: the portal his death opens in Durance of Hate 3 leads to the Pandemonium Fortress."""
    log, mark = [], engine_mark()
    if "mephisto" not in STATE.get("acts_killed", set()):
        add("acts travel34: Mephisto's portal to Act 4", "BLOCKED", "Mephisto was not killed in this run (his death opens the portal)")
        return
    revive_if_dead()  # `enter` with a dead character crashed the game (BC_ASSERT hnd->IsValid(), run checks-20261028-215641-s2)
    if hstate()["player"].get("area") != 102:
        goto(102)
    t0 = time.time()
    while True:  # the portal comes with his death's quest code: none 12 s after the kill in run checks-20261029-021145-s2
        objs = parse_objects(Hl("objects", log)[1])
        gate = [o for o in objs if o["class"] == ACT4_GATE]
        if gate or time.time() - t0 > 30:
            break
        time.sleep(3)
    if not gate:  # a map object (InitFn 44) whose room may not be loaded from where he died: walk to its preset spot
        pre = [q for q in parse_presets(Hl("presets 2", log)[1]) if q["class"] == ACT4_GATE]
        log.append("portal presets: %s" % pre)
        for q in pre[:1]:
            if not acts_walk(q["x"], q["y"], reach=8, timeout=120, fight=True):
                acts_place_near(q["x"], q["y"], log)  # travel help, named in the log
            time.sleep(2)
            objs = parse_objects(Hl("objects", log)[1])
            gate = [o for o in objs if o["class"] == ACT4_GATE]
    bridge = acts_raise_bridge(log) if gate else "not looked at (no portal)"
    if gate:
        acts_walk(gate[0]["x"], gate[0]["y"], reach=5, timeout=120, fight=True)
    lines, setup = ["no portal object %d" % ACT4_GATE, bridge], []
    if gate and not player_dead(hstate()["player"]):
        lines = ["portal mode %d" % gate[0]["mode"], bridge]
        if acts_gate_click(gate[0], log):
            lines.append("the click took the character")
        else:  # run checks-20261029-053521-s4: the portal stood open (mode 2), the character in it said "I can't" to the click.
            # (`enter` on it ran the level change with dest 0: BC_VERIFY ptDrlgLevel->ptRoomFirst, Drlg.cpp:882; not used any more.)
            # The character came to Act 3 by `level` (travel help) with no Act 1 / 2 quest done: find the quest record the gate
            # wants by SET-UP steps (named in the row), clicking again after each
            log.append("quests before the set-up: %s" % {q: quest_bits(q) for q in ACT4_GATE_QUESTS})
            for step in ACT4_GATE_SETUP:
                for q, bit in step:
                    Hl("quest %d %d set" % (q, bit), log)
                setup.append(step)
                if acts_gate_click(gate[0], log):
                    lines.append("the click took the character after SET-UP quest bits %s" % setup)
                    break
            else:
                lines.append("the click did not take the character, also after SET-UP quest bits %s" % setup)
    time.sleep(2)
    area = hstate()["player"].get("area")
    finish("acts travel34: Mephisto's portal to Act 4", area == 103, "help: travel to Durance 3 by `level`, level 80 build (as the "
           "Mephisto row); objects loaded: %d; %s; now in area %s (want 103)" % (len(objs), "; ".join(lines), area), mark,
           [sh("acts_travel34")], log)


MEPHISTO_BRIDGE = 341  # objects: the bridge over the lava to the portal (InitFn 45)
# The bridge does not rise by itself when Mephisto dies: in 1.14d's Act 3 quest code its object event 7 runs every 24 frames and,
# once his death set the portal's mode to 2, raises the bridge (mode 0 -> 1 -> 2, its collision freed) only for a player in the
# bridge's room closer than 18. The runs of lane acts4 stood 66 away at the moat, so the bridge stayed in mode 0 in the game of
# the kill (checks-20261029-053521-s4, checks-20261029-072606-s1) and the portal across the lava refused the click. Not a port
# fault (his death is keyed on class 242, not on his AI, which is `Vampire` in Median 2012): walk up to the bridge first.
BRIDGE_REACH = 18
BRIDGE_APPROACH = ((0, 0), (-10, 0), (0, -10), (-10, -10), (10, 0), (0, 10), (-16, 6), (6, -16))


def acts_raise_bridge(log, walk_s=40):
    """Walk up to Mephisto's bridge (object 341) until it rises (mode 2); returns a note for the row."""
    br = parse_objects(Hl("objects %d" % MEPHISTO_BRIDGE, log)[1])
    if not br:
        return "no bridge object %d loaded" % MEPHISTO_BRIDGE
    b = br[0]
    if b["mode"] == 2:
        return "bridge %d up already (mode 2, %d away)" % (MEPHISTO_BRIDGE, b["dist"])
    best = None
    for dx, dy in BRIDGE_APPROACH:
        acts_walk(b["x"] + dx, b["y"] + dy, reach=4, timeout=walk_s, fight=True)
        p = hstate()["player"]
        if player_dead(p) or p.get("area") != 102:
            return "bridge %d mode %d: the character died / left on the walk to it" % (MEPHISTO_BRIDGE, b["mode"])
        d = max(abs(p.get("x", 0) - b["x"]), abs(p.get("y", 0) - b["y"]))
        best = d if best is None else min(best, d)
        for _ in range(4 if d < BRIDGE_REACH else 1):
            time.sleep(1.5)
            now = seal_now(b, log)
            if now.get("mode") == 2:
                return "bridge %d mode %d -> 2 with the character %d from it (walked to %d,%d)" % (
                    MEPHISTO_BRIDGE, b["mode"], d, p.get("x", 0), p.get("y", 0))
    return "bridge %d stayed in mode %s (the walk came %s from it)" % (MEPHISTO_BRIDGE, seal_now(b, log).get("mode"), best)


MEPHISTO = 242  # monstats: Mephisto (Median 2012: AI `Vampire`, size 3, MeleeRng 3)


def line_blocked(x0, y0, x1, y1, log):
    """Cells of the game's walk collision (`walkmap`, step 1) the straight line between two points crosses that read blocked
    (`#`) or not loaded (`?`): the moat between the character and Mephisto. Returns (blocked, unknown, cells)."""
    half = max(abs(x1 - x0), abs(y1 - y0)) // 2 + 3
    wm = relp_walkmap((x0 + x1) // 2, (y0 + y1) // 2, half=min(max(half, 4), 60), step=1)
    if wm is None:
        return None
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    blocked = unknown = 0
    for i in range(1, n):
        x, y = x0 + (x1 - x0) * i // n, y0 + (y1 - y0) * i // n
        r, c = y - wm["y0"], x - wm["x0"]
        ch = wm["grid"][r][c] if 0 <= r < len(wm["grid"]) and 0 <= c < len(wm["grid"][r]) else "?"
        blocked += ch == "#"
        unknown += ch == "?"
    return blocked, unknown, n - 1


def meph_melee_round(mid, secs, log):
    """Left clicks with Attack (skill 0, an axe in the hand) on Mephisto's spot for `secs` seconds from where the character
    stands, plus the cast path (`cast 0 unit`, harness) every 4th tick. Returns a dict: life before / after, distances, player
    and Mephisto modes, the collision cells on the line between them."""
    H("skill left 0")
    l0 = acts_mon_life(mid)
    out = {"life0": (l0 or 0) >> 8, "clicks": 0, "casts": 0, "pmodes": {}, "mmodes": {}, "dist": []}
    t0, k = time.time(), 0
    while time.time() - t0 < secs:
        st = hstate()
        p = st["player"]
        if player_dead(p):
            out["died"] = True
            STATE["acts_deaths"] = STATE.get("acts_deaths", 0) + 1
            break
        m = next((m for m in st["mons"] if m.get("id") == mid), None)
        if m is None or not acts_mon_life(mid):
            out["gone"] = True
            break
        d = max(abs(p.get("x", 0) - m["mx"]), abs(p.get("y", 0) - m["my"]))
        out["dist"].append(d)
        if k == 0:
            out["at"] = (p.get("x"), p.get("y"), m["mx"], m["my"])
            out["line"] = line_blocked(p.get("x", 0), p.get("y", 0), m["mx"], m["my"], log)
        k += 1
        if k % 4 == 0:
            H("cast 0 unit %d" % mid)
            out["casts"] += 1
        elif click_unit(mid, "left"):
            out["clicks"] += 1
        time.sleep(0.35)
        q = hstate()
        pm = q["player"].get("mode")
        mm = next((x.get("mode") for x in q["mons"] if x.get("id") == mid), None)
        out["pmodes"][pm] = out["pmodes"].get(pm, 0) + 1
        out["mmodes"][mm] = out["mmodes"].get(mm, 0) + 1
        time.sleep(0.25)
    out["life1"] = (acts_mon_life(mid) or 0) >> 8
    p = hstate()["player"]
    out["end"] = (p.get("x"), p.get("y"))
    dd = out.pop("dist")
    out["dist"] = (min(dd), max(dd)) if dd else None
    return out


def acts_meph_melee():
    """Lane endgame, item 4: does a melee hit cross the Durance 3 moat? Mephisto (Normal) with an axe and Attack by left clicks:
    (1) from where the walk towards him ends (the moat edge when he stands across it), (2) after `place` next to him (travel
    help, named; after a death on the walk, first `place` on the free spot nearest to him, the moat edge when he is across it).
    Reads his life, both modes and the collision cells on the line between them. INFO row: the comparison is
    the result (1.13c: melee does not reach across the moat, the "moat trick" is for ranged attacks)."""
    log, mark = [], engine_mark()
    lvl = acts_level_up(80)
    acts_gear(lvl)
    dmg = 40 + lvl * 12
    H("unequip rhand")
    H("equip %s 21=%d 22=%d 119=400 60=20 93=60 rhand" % (ACTS_WEAPON, dmg, dmg * 2))
    goto(102)
    mon = acts_find(MEPHISTO, log)
    if mon is None:
        finish("acts mephmelee: melee across the Durance 3 moat", False, "Mephisto not found", mark, [sh("acts_mephmelee_nofind")], log)
        return
    rounds, shots = [], []
    for phase in ("walk towards him", "placed on the free spot nearest to him (help)", "placed next to him (help)"):
        if phase.startswith("placed on") and rounds and isinstance(rounds[-1][1], dict):
            continue  # the walk got to the moat edge itself
        if hstate()["player"].get("area") != 102:  # after a death on the walk: back with the gear, as acts_boss does
            acts_gear(lvl)
            H("unequip rhand")
            H("equip %s 21=%d 22=%d 119=400 60=20 93=60 rhand" % (ACTS_WEAPON, dmg, dmg * 2))
            goto(102)
        u = parse_moveto(Hl("moveto %d" % mon["id"], log)[1]) or mon
        if phase.startswith("walk"):
            acts_walk(u["x"], u["y"], reach=2, timeout=120, fight=True, skip=(MEPHISTO,))
            acts_planned_walk(u["x"], u["y"], log, budget=120, reach=3)
        elif not acts_place_near(u["x"] + (3 if phase.endswith("next to him (help)") else 0),
                                 u["y"] + (3 if phase.endswith("next to him (help)") else 0), log):
            rounds.append((phase, "place found no spot"))
            continue
        if player_dead(hstate()["player"]) or hstate()["player"].get("area") != 102:
            revive_if_dead()
            rounds.append((phase, "died on the way"))
            continue
        res = meph_melee_round(mon["id"], 40, log)
        rounds.append((phase, res))
        shot = sh("acts_mephmelee_%d" % len(rounds))
        shots.append(shot)
        log.append("%s: %s (%s)" % (phase, res, shot))
        if res.get("died") or res.get("gone"):
            break
    hit = [ph for ph, r in rounds if isinstance(r, dict) and r["life1"] < r["life0"]]
    finish("acts mephmelee: melee across the Durance 3 moat", bool(hit),
           "axe %d-%d damage, Attack by left clicks (+ `cast 0 unit` every 4th tick); Mephisto life %s at the start; rounds %s; "
           "melee damage landed in: %s" % (dmg, dmg * 2, (mon.get("life") or 0) >> 8, rounds, hit or "none"), mark, shots, log,
           partial="the moat comparison with 1.13c (judged in docs/testing.md, lane endgame)")


ACT4_GATE_QUESTS = (6, 7, 14, 15, 22, 23)
# SET-UP steps tried in order when the open portal refuses the click ("I can't"): the earlier acts' boss quests done (bit 0),
# then their act-end records (7 / 15), then Act 3's own (23)
ACT4_GATE_SETUP = (((6, 0), (14, 0)), ((7, 0), (15, 0)), ((23, 0),))


def acts_gate_click(obj, log):
    """A background left click on the portal (then its click packet 0x13); True when the character arrived in Act 4."""
    H("skill left 0")
    for up in (0, 40, 80):
        if click_object(obj, up_px=up):
            for _ in range(4):
                time.sleep(2)
                if hstate()["player"].get("area") == 103:
                    log.append("mouse click %d px above the portal's foot took the character" % up)
                    return True
    Hl("pkt 13 " + _le(2, obj["id"]), log)
    for _ in range(4):
        time.sleep(2)
        if hstate()["player"].get("area") == 103:
            log.append("the click packet 0x13 took the character")
            return True
    return False


SUMMIT_DOOR = 564  # objects: the Arreat Summit door at the arrival; D2R's MtnTop.ds1 puts the altar 9 west and 49 north of it
ANCIENT_CLASSES = (540, 541, 542)


def fight_all(classes, log, timeout=600):
    """Fight every unit of these classes wherever it walks in the loaded level (`moveto nearest`), then whatever else is in reach.
    Returns (killed classes, deaths)."""
    killed, deaths, t0, skip = [], 0, time.time(), set()
    while time.time() - t0 < timeout:
        if player_dead(hstate()["player"]):
            deaths += 1
            break
        target = None
        for c in classes:
            u = parse_moveto(Hl("moveto nearest %d" % c, log)[1])
            if u and u["id"] not in skip and (acts_mon_life(u["id"]) or 0) > 0:
                target = u
                break
        if target is None:
            near = [m for m in hostiles_near(hstate(), 30) if m["id"] not in skip]
            if not near:
                break
            target = near[0]
        k, d, _s = acts_fight(target["id"], max(20, min(180, int(timeout - (time.time() - t0)))))
        deaths += d
        if d:
            break
        if k:
            killed.append(target.get("class"))
        else:  # out of reach (behind a wall: run checks-20261029-013841-s2 chased one in the Vizier wing for 20 minutes)
            skip.add(target["id"])
    return killed, deaths


def acts_ancients():
    """Arreat Summit (120): the altar's speech, then the statues come alive. D2R's quest code spawns superuniques 43-45 by number;
    before bug #362's fix Median's rows sat one above (Siege Boss + Ancients 1 and 2 came). Records the classes, fights them,
    and passes when quest 39 changes and the gateway (547) takes the character to the Worldstone Keep (128)."""
    log, mark = [], engine_mark()
    lvl = acts_level_up(85)
    acts_gear(lvl)
    q0 = quest_bits(39)
    goto(120)
    door = next((o for o in parse_objects(Hl("objects %d" % SUMMIT_DOOR, log)[1])), None)
    if door:
        acts_walk(door["x"] - 9, door["y"] - 40, reach=8, timeout=150, fight=True)
    objs = parse_objects(Hl("objects %d" % ANCIENTS_ALTAR, log)[1])
    if not objs:
        finish("acts ancients: the altar (object %d)" % ANCIENTS_ALTAR, False, "no altar object near the summit (door %s)" % door,
               mark, [sh("acts_ancients_noaltar")], log)
        return
    altar = objs[0]
    acts_walk(altar["x"], altar["y"] + 3, reach=4, timeout=40)
    fn = next((int(r.get("OperateFn") or 0) for r in table("objects") if r.get("*ID") == str(ANCIENTS_ALTAR)), 65)
    Hl("operate %d %d" % (altar["id"], fn), log)
    summoned = []
    for _ in range(20):  # the speech plays first (about 30 s)
        time.sleep(3)
        summoned = sorted({m.get("class") for m in hostiles_near(hstate(), 40)})
        if summoned:
            break
    time.sleep(3)
    summoned = sorted({m.get("class") for m in hostiles_near(hstate(), 40)})
    shot = sh("acts_ancients_summoned")
    killed, deaths = fight_all(ANCIENT_CLASSES + tuple(c for c in summoned if c not in ANCIENT_CLASSES), log)
    time.sleep(5)
    q1 = quest_bits(39)
    gw = parse_objects(Hl("objects 547", log)[1])
    area = None
    if gw:
        acts_walk(gw[0]["x"], gw[0]["y"] + 3, reach=5, timeout=60)
        gfn = next((int(r.get("OperateFn") or 0) for r in table("objects") if r.get("*ID") == "547"), 66)
        for _ in range(3):  # the first use opens the gate (mode 1), the next one moves the character
            Hl("operate %d %d" % (gw[0]["id"], gfn), log)
            time.sleep(6)
            area = hstate()["player"].get("area")
            if area == 128:
                break
    ok = all(c in summoned for c in ANCIENT_CLASSES) and q1 != q0 and area == 128
    finish("acts ancients: altar, the three Ancients, the gateway", ok,
           "level %d; summoned classes %s (Ancients are 540-542); killed %s; %d deaths; quest 39 bits %s -> %s; gateway -> area %s (want 128)"
           % (lvl, summoned, killed, deaths, q0, q1, area), mark, [shot, sh("acts_ancients_after")], log)


THRONE_XY = (15090, 5045)  # in front of Baal's throne: D2R's wthrone.ds1 places him at (90, 11), the room's origin is 15000, 5000
# `presets` lists no units in levels 131 / 132 (their rooms come from one fixed map each, D2R's wthrone.ds1 / wstone01.ds1; the
# level's origin is levels.txt OffsetX / OffsetY (3000, 1000 / 3000, 1152 tiles) * 5). Routes read from those maps (floor and
# wall layers): the throne hall runs straight north from the arrival (103, 213) up tile column 17-18 to the throne (90, 11); the
# straight walk to THRONE_XY drifted into the west side rooms (run checks-20261029-041546-s4 ended at 15043, 5138). Baal in the
# Worldstone Chamber (monster preset 33 at (135, 160), seen at 15135, 5920) stands on the middle platform, open only to the
# south: from the east room down to the long corridor (row 36), west along it, then north to him (the same run stood at about
# 15165, 5900, 36 away, for 712 s).
THRONE_ROUTE = ((15092, 5200), (15087, 5170), (15087, 5140), (15087, 5110), (15090, 5080), (15092, 5050))
BAAL_ROUTE = ((15192, 5900), (15192, 5925), (15185, 5932), (15160, 5932), (15142, 5932), (15140, 5925))


def acts_route(points, log, walk_s=60):
    """Walk the legs in order (fighting on the way); a leg the walk does not finish is placed (travel help, counted). Returns
    {"legs", "walked", "placed", "end", "died"}."""
    out = {"legs": len(points), "walked": 0, "placed": 0}
    area0 = hstate()["player"].get("area")
    for x, y in points:
        if acts_walk(x, y, reach=8, timeout=walk_s, fight=True, skip=(BAAL_THRONE,)):
            out["walked"] += 1
            continue
        p = hstate()["player"]
        if player_dead(p) or p.get("area") != area0:
            out["died"] = True
            break
        if acts_place_near(x, y, log):
            out["placed"] += 1
    p = hstate()["player"]
    out["end"] = (p.get("x"), p.get("y"))
    return out
WAVE_CLASSES = (1289, 1148, 803, 1290, 1281)  # the wave bosses: superuniques 61-65 of the built table (docs/testing.md, lane acts)
THRONE_ROOM_RADIUS = 45  # the waves come when the throne room is empty of monsters (D2's Baal throne AI): fight all within this


BAAL_PORTAL = 563  # objects: "baals portal" to the Worldstone Chamber (OperateFn 70), opened behind the throne after the fifth wave


def acts_throne(waves_s=2700):
    """Throne of Destruction (131): walk to Baal's throne, then clear the room and fight what comes, until Baal has left the throne
    and his portal (object 563) stands, or `waves_s` seconds. Records the classes of every monster seen, when each wave boss came
    and died. Passes with the fifth wave boss gone (the waves come in order; one can die out of the character's sight) and the
    portal listed; the portal is then the `baal` stage's way in (lane endgame: the harness travel into 132 sets quest 40 without
    a kill, lane nmhell3). A death is counted: the character is revived in Harrogath (the "teleport" of run checks-20261028-191050-s2 was such a death), rests and
    goes back, at most 8 times."""
    log, mark = [], engine_mark()
    STATE.pop("throne_portal", None)
    STATE["acts_plus_skills"] = ACTS_END_PLUS_SKILLS if acts_has_build() else 0
    lvl = acts_level_up(90)  # 80 died on the route (run 3 of lane endgame); Baal's stage uses 90 too
    acts_gear(lvl)
    d0 = STATE.get("acts_deaths", 0)
    seen, t0, waves, died, left_at = {}, time.time(), {}, {}, None
    STATE.pop("acts_load", None)
    thr, tx, ty, route, walked, back = [], THRONE_XY[0], THRONE_XY[1], None, False, []

    def to_throne():
        """Into 131 (harness travel: the stand-in for the Worldstone Keep 3 waypoint) and walk to the throne; True when there."""
        nonlocal thr, tx, ty, route
        goto(131)
        thr = [q for q in parse_presets(Hl("presets 1", log)[1]) if q["class"] == BAAL_THRONE]
        tx, ty = (thr[0]["x"], thr[0]["y"] + 30) if thr else THRONE_XY
        STATE["walk_seen"] = seen  # acts_walk records the classes it meets (first second of the stage)
        route = None if thr else acts_route(THRONE_ROUTE, log)
        ok = not (route or {}).get("died") and acts_walk(tx, ty, reach=15, timeout=240, fight=True, skip=(BAAL_THRONE,))
        if not ok and not (route or {}).get("died"):
            ok = acts_planned_walk(tx, ty, log, budget=300, reach=15)
        STATE.pop("walk_seen", None)
        return ok

    def back_after_death(why):
        """A death (or leaving 131): revive in town, rest, then back to the throne, at most 8 times. The waves stay where they
        were (D2 keeps the throne's wave count in the level)."""
        p = hstate()["player"]
        if player_dead(p):
            STATE["acts_deaths"] = STATE.get("acts_deaths", 0) + 1
        revive_if_dead()
        if len(back) >= 8:
            return False
        acts_gear(lvl)  # the given gear stays on the corpse (run 4: life 15787 -> 4027 after the first death, then 5 more deaths)
        acts_rest(log)
        ok = to_throne()
        back.append("%s at %d s: back at the throne %s" % (why, time.time() - t0, ok))
        return ok

    walked = to_throne()
    while not walked and len(back) < 8:
        walked = back_after_death("route")
    empty_since, portal, baal_gone = None, [], None
    while walked and time.time() - t0 < waves_s:
        st = hstate()
        p = st["player"]
        if (p and player_dead(p)) or p.get("area") != 131:
            left_at = int(time.time() - t0)
            if back_after_death("death" if p and player_dead(p) else "left 131"):
                continue
            break
        now = int(time.time() - t0)
        alive = {m.get("class") for m in st["mons"] if m.get("life", 1) > 0}
        for m in st["mons"]:
            seen.setdefault(m.get("class"), now)
            if m.get("class") in WAVE_CLASSES:
                waves.setdefault(m.get("class"), now)
        for c in waves:
            if c not in died and c not in alive and parse_moveto(H("moveto nearest %d" % c)[1]) is None:
                died[c] = now
        if baal_gone is None and BAAL_THRONE not in alive and parse_moveto(H("moveto nearest %d" % BAAL_THRONE)[1]) is None:
            baal_gone = now
        acts_load_sample()
        near = hostiles_near(st, THRONE_ROOM_RADIUS, skip=(BAAL_THRONE,))
        if near:
            empty_since = None
            _k, d, _s = acts_fight(near[0]["id"], 60)
            if d:
                left_at = int(time.time() - t0)
                if back_after_death("death in a fight"):
                    continue
                break
            continue
        empty_since = empty_since or now
        portal = [o for o in parse_objects(H("objects %d" % BAAL_PORTAL)[1])]
        if portal and WAVE_CLASSES[-1] in died:  # not "Baal gone": run 10 read him gone (out of reach) with 3 waves to come
            break
        if abs(p.get("x", 0) - tx) > 15 or abs(p.get("y", 0) - ty) > 15:
            acts_walk(tx, ty, reach=10, timeout=40, fight=True, skip=(BAAL_THRONE,))
        time.sleep(2)
    deaths = STATE.get("acts_deaths", 0) - d0
    shot = sh("acts_throne")
    left = any(m.get("class") == BAAL_THRONE for m in hstate()["mons"])
    if not portal:
        portal = [o for o in parse_objects(Hl("objects %d" % BAAL_PORTAL, log)[1])]
    if portal:
        STATE["throne_portal"] = portal[0]
    others = [o for o in parse_objects(Hl("objects", log)[1]) if o["class"] in (59, 60, 564, 569)]
    cleared = WAVE_CLASSES[-1] in died  # the waves come in order: the fifth gone = done (run 7 timed out with it alive: the portal
    if portal and not cleared:  # object stands all along, its click took nobody then
        STATE.pop("throne_portal", None)
    finish("acts throne: Baal's waves in the Throne of Destruction", cleared and bool(portal),
           "level %d%s; throne preset %s; route %s; walk reached the throne: %s; wave bosses seen at s %s, gone at s %s (of %s); "
           "room empty since %s s; Baal left the throne at %s s (still there at the end: %s); portal %d %s; deaths %d (last left "
           "the throne at %s s; back: %s); %d s in the stage; classes seen (first second): %s; other portal objects %s; %s"
           % (lvl, " (+%d to all skills on the given amulet)" % STATE["acts_plus_skills"] if STATE.get("acts_plus_skills") else "",
              thr[:1], route, walked, waves, died, list(WAVE_CLASSES), empty_since, baal_gone, left, BAAL_PORTAL,
              portal[:1], deaths, left_at, back, time.time() - t0, sorted(seen.items()), others, acts_load_note()),
           mark, [shot], log)


def acts_baal_portal(log):
    """The throne stage's portal (object 563) into the Worldstone Chamber, on the player path: walk up to it, background left
    clicks on it (then the click packet 0x13, named). Returns a note; the caller reads the area."""
    obj = STATE.get("throne_portal")
    if hstate()["player"].get("area") != 131:
        return "not in the Throne of Destruction any more (area %s): no portal to click" % hstate()["player"].get("area")
    now = parse_objects(Hl("objects %d" % BAAL_PORTAL, log)[1]) or [obj]
    obj = now[0]
    if not acts_walk(obj["x"], obj["y"] + 3, reach=4, timeout=90, fight=True, skip=(BAAL_THRONE,)):
        acts_planned_walk(obj["x"], obj["y"] + 3, log, budget=180, reach=5)
    H("skill left 0")
    for up in (0, 40, 80, 120):
        if click_object(obj, up_px=up):
            for _ in range(4):
                time.sleep(2)
                if hstate()["player"].get("area") == 132:
                    return "portal %d at %d,%d by a mouse click %d px above its foot" % (BAAL_PORTAL, obj["x"], obj["y"], up)
    Hl("pkt 13 " + _le(2, obj["id"]), log)
    for _ in range(4):
        time.sleep(2)
        if hstate()["player"].get("area") == 132:
            return "portal %d by the click packet 0x13 (the mouse clicks did not take the character)" % BAAL_PORTAL
    p = hstate()["player"]
    return "portal %d at %d,%d: clicks and the click packet did not take the character (at %s,%s, area %s)" % (
        BAAL_PORTAL, obj["x"], obj["y"], p.get("x"), p.get("y"), p.get("area"))


def acts_nightmare():
    """Save and Exit after Baal, then Play: the difficulty dialog offers Nightmare and the character enters it."""
    log, mark = [], engine_mark()
    q40 = quest_bits(40)
    g.key("esc")
    time.sleep(1.5)
    g.click(*g.UI["save_exit"])
    time.sleep(10)
    STATE["in_game"] = False
    card = card_of(g.CHAR_NAME)  # just saved: the newest save, card 1
    if card_y(card or 0) is None:
        finish("acts nightmare: enter Nightmare after Baal", False, "%s is not on the visible character list (card %s)" % (g.CHAR_NAME, card), mark, log=log)
        return
    g.click(0.87, card_y(card))
    time.sleep(0.8)
    g.click(*g.UI["menu_play"])
    time.sleep(3)
    dshot = sh("acts_difficulty_dialog")
    g.click(0.5, DIFF_Y["nightmare"])
    ok = wait_in_game(45)
    STATE["in_game"] = ok
    p = hstate()["player"] if ok else {}
    if ok and p.get("class") != save_class(g.CHAR_NAME):
        STATE["in_game"] = False
        finish("acts nightmare: enter Nightmare after Baal", False, "another character is in the game (class %s): stopped" % p.get("class"), mark, log=log)
        return
    finish("acts nightmare: enter Nightmare after Baal", ok and p.get("difficulty") == 1,
           "quest 40 bits before %s; difficulty dialog %s; in game %s, difficulty %s, area %s" % (q40, dshot, ok, p.get("difficulty"), p.get("area")),
           mark, [dshot] + ([sh("acts_nightmare_town")] if ok else []), log)


def check_acts():
    """Lane acts: towns, act bosses, act travel, the Ancients and the Nightmare unlock on the player path (block comment above)."""
    if not need_game():
        add("acts", "BLOCKED", "not in the game")
        return
    STATE.setdefault("menus", {})
    for stage in acts_stages():
        try:
            guard()
            clean_start_state("acts " + stage)
            if stage == "towns":
                for act in (1, 2, 3, 4, 5):
                    for cls, menu in acts_town(act).items():  # the menus before any boss: a line a quest adds is told apart by them
                        STATE["menus"].setdefault(cls, menu)
            elif stage in ACT_BOSSES:
                acts_boss(stage)
            elif stage in ACT_TRAVEL:
                acts_travel(stage)
            elif stage == "travel34":
                acts_portal_a4()
            elif stage == "ancients":
                acts_ancients()
            elif stage == "throne":
                acts_throne()
            elif stage == "mephmelee":
                acts_meph_melee()
            elif stage == "nightmare":
                acts_nightmare()
            elif stage == "build":
                acts_build_calibrate()
        except Exception as e:
            add("acts " + stage, "BLOCKED", "script error: %r" % (e,))
            if WD.abort:
                break
# ---------------------------------------------------------------- lane rulescheck2: mid-game rules with a SET-UP character
# Coordinator ruling (lane_rules "PLAYER PATH vs SET-UP", 2026-10-28): the character may be SET UP by harness or by a save written
# with our own tools (tools/rc_setup.py: level, points, quest flags, difficulty unlocked, gear, a hired mercenary); the ACTION being
# judged stays on the player path (clicks, NPC dialog, pickup and use, a mortal character). Every set-up step is named in the note
# ("SET-UP: ..."). Run with MXL_CHAR=<letters> MXL_CHAR_CLASS=paladin (the lane used `Rcpala`), rc2setup first.
import rc_setup  # noqa: E402

RC2_LEVEL = 30
RC2_SKILLS = ((503, 1), (505, 1), (504, 1), (518, 1), (519, 1), (520, 1), (521, 1))  # Paladin, prerequisites first: Arcane Strike,
# Lemures, Black Sleep; Judgement, Rapture, Light and Shadow, Holy Armor
RC2_DELAY = (471, 521)  # Mythal (Druid, delay max(250-blvl*5,125) = 245 frames at level 1, mana 350) and Holy Armor (delay par4 =
# 750 frames, mana 136, self): casts with a clear mana cost and no weapon class. `setskill` (the game's own skill-point function)
# gives the paladin Mythal; it refused Divine Apparition and Retaliate, and Black Sleep needs a melee weapon (itypea1 `mele`)
RC2_STR_SPENT = 20  # strength points the set-up "spends" for the refund check


def exp_start(level):
    """Experience at which `level` starts (experience.txt row level-1)."""
    return int(row_of("experience", "Level", str(level - 1))["Paladin"])


def rc2_set_level(level, log, frac=0.5):
    """SET-UP by harness: level, experience inside that level (frac of its span), no unspent points."""
    lo, hi = exp_start(level), exp_start(level + 1)
    for stat, val in ((12, level), (13, lo + int((hi - lo) * frac)), (4, 0), (5, 0)):
        Hl("stat player %d set %d" % (stat, val), log)
    return lo, hi


def rc2_save_exit():
    """Esc -> Save and Exit, back on the main menu. True when the game was left."""
    for _attempt in range(3):
        g.key("esc")
        time.sleep(1.5)
        g.click(*g.UI["save_exit"])
        for _ in range(10):
            time.sleep(3)
            if not g.in_game():
                STATE["in_game"] = False
                time.sleep(2)
                return True
    return False


def rc2_closed_edit(fn, log, difficulty="normal"):
    """SET-UP by save: Save and Exit, close the game, edit the closed .d2s with our own code (rc_setup.edit: checksum and `.d2rl`
    made again), start the game and Play in `difficulty`."""
    if not rc2_save_exit():
        raise RuntimeError("Save and Exit did not leave the game")
    g.stop()
    time.sleep(2)
    rc_setup.edit(SAVES, g.CHAR_NAME, fn)
    if not to_menu():
        raise RuntimeError("the game did not come back to the menu after the save edit")
    ok = enter_game(card_of(g.CHAR_NAME) or 1, difficulty)
    log.append("save edited while closed; entered %s: %s" % (difficulty, ok))
    return ok


def check_rc2setup():
    """SET-UP only (no verdict): level 30 and the skills of the delay check by harness; by a save edit progression 10 (Nightmare and
    Hell unlocked) and the quest flags the rules need: Normal Burial Grounds done (Kashya hires), Radament bit 5, Golden
    Bird bit 5, Prison of Ice bit 8 (the three quest items may be picked up: 1.14d `0x55cc90`, D2R `0x4734f0`, bug #332); Nightmare
    and Hell Burial Grounds done."""
    log = []
    goto(1)
    rc2_set_level(RC2_LEVEL, log)
    for s, lv in RC2_SKILLS:
        Hl("setskill %d %d" % (s, lv), log)
    Hl("stat player 9 set %d" % (400 << 8), log)  # maximum mana 400 (Holy Armor costs 136)
    Hl("stat player 8 set %d" % (400 << 8), log)

    def edit(s):
        s = rc_setup.set_progression(s, "hell")
        for diff in (0, 1, 2):
            s = rc_setup.set_quest_bits(s, diff, rc_setup.Q_BURIAL, rc_setup.DONE)
        for _code, (word, bit) in rc_setup.QUEST_ITEM_GATE.items():
            s = rc_setup.set_quest_bits(s, 0, word, 1 << bit)
        return s
    ok = rc2_closed_edit(edit, log)
    p = hstate()["player"]
    st = rc_stats(["level", "experience", "maxmana"], log)
    add("rc2setup", "INFO" if ok and st["level"] == RC2_LEVEL else "BLOCKED",
        "SET-UP: level %s, experience %s, max mana %s, skills %s by harness; save: progression 10, quest flags (Normal 2 done, 9 bit 5, "
        "20 bit 5, 37 bit 8; Nightmare / Hell 2 done); in game: %s, area %s" % (
            st["level"], st["experience"], (st["maxmana"] or 0) >> 8, RC2_SKILLS, ok, p.get("area")), [sh("rc2setup")], log)


def check_rc2quest():
    """#240 SK8 / QU2 on the player path with the set-up's quest flags (bug #332: the pickup gate of these three items is 1.13c's
    own). Each item lands next to the character (harness drop, as a monster's), is picked up by a left click and used by a right
    click in the inventory."""
    rc_quest_use("rc2book", "ass", lambda s0, s1: (s1["newskills"] or 0) - (s0["newskills"] or 0) == 1, ["newskills"],
                 "+1 skill point")
    rc_quest_use("rc2life", "xyz", lambda s0, s1: (s1["maxhp"] or 0) - (s0["maxhp"] or 0) == 20 << 8, ["maxhp"], "+20 max life")
    rc_quest_use("rc2scroll", "tr2", lambda s0, s1: all((s1[r] or 0) - (s0[r] or 0) == 10 for r in RC_RESISTS), list(RC_RESISTS),
                 "+10 all resistances")


# engine-triage #24: misc pSpell 3 (signets: stat1/calc1 and stat2/calc2 added) and pSpell 10 (Apple, as Book of Skill) on the player
# path. (code, what, {stat: gain}) for a FRESH level-1 character with 0 gold and both potion caps 0, in this order: misc.txt's
# calc1 / calc2 at level 1 (Signet of Gold min(150, 10000 - gold), Experience 250, Learning 1 - cap / 500 = 1 and its cap + 1,
# Bling Bling 5 - cap / 25 = 5 with the cap at 1 by then, Buyable Signet of Gold 150 into the bank, Signet of Skill 1 - cap / 3 = 1).
# The Apple must be used up without a skill point (D2R's pSpell 10 is the Book of Skill; docs/plugin-plan.md section 25).
RP_SIGNETS = [("zkw", "Signet of Gold", {"gold": 150}),
              ("zku", "Signet of Experience", {"experience": 250}),
              ("zkq", "Signet of Learning", {"statpts": 1, "potion_stat_cap": 1}),
              ("quz", "Bling Bling Signet", {"statpts": 5, "potion_stat_cap": 5}),
              ("zka", "Buyable Signet of Gold", {"goldbank": 150}),
              ("!@B", "Signet of Skill (New)", {"newskills": 1, "potion_skill_cap": 1}),
              ("dog", "Apple (pSpell 10: 1.13c starts skill 47 Apple Healing Spell, no skill point; bug #499)", {"newskills": 0})]


def signet_verdict(gains, s0, s1):
    """True when every stat named in `gains` grew by exactly its gain (a missing read counts as 0)."""
    return all((s1.get(k) or 0) - (s0.get(k) or 0) == v for k, v in gains.items())


def check_rpsignets():
    """engine-triage #24: signets (pSpell 3) and the Apple (pSpell 10) used on the player path: each item dropped next to the
    character (harness, as a monster's drop), picked up by a left click, used by a right click in the inventory; the stats of its
    stat1 / stat2 read before and after. MXL_CHAR must be a NEW character (level 1, no gold, caps 0)."""
    for code, what, gains in RP_SIGNETS:
        rule = (lambda s0, s1, g_=gains: signet_verdict(g_, s0, s1) and apple_state(None)["on"]) if code == "dog" else \
            (lambda s0, s1, g_=gains: signet_verdict(g_, s0, s1))
        rc_quest_use("rpsig_%s" % re.sub(r"\W", "_", code), code, rule, list(gains),
                     "%s: %s%s" % (what, ", ".join("%s +%d" % kv for kv in gains.items()),
                                   ", state mega_apple (%d) on the player" % APPLE_STATE if code == "dog" else ""))


# Bug #499 (plugin part `appleuse`): the Apple (`dog`, misc pSpell 10) casts skills row 47 `Apple Healing Spell` as 1.13c's item
# spell 10 did: state `mega_apple` for auralencalc 15000 frames (10 minutes) with aurastat1-5 = hpregen
# ((maxhp.accr / 3000) * (100 + item_faster_potions.accr)) / 100, item_vitality_percent = skill_bloodymary_bonus, damagepercent =
# skill_elixirs_synergy, item_energy_percent = skill_paganheart_bonus, item_allskills = skill_paganheart_synergy.
APPLE_STATE, APPLE_FRAMES = 44, 15000
APPLE_STATS = {74: "hpregen", 393: "item_vitality_percent", 25: "damagepercent", 392: "item_energy_percent", 127: "item_allskills"}
APPLE_SYNERGY = {393: (444, 7), 25: (498, 9), 392: (445, 11), 127: (461, 1)}  # aurastat -> (source stat, SET-UP value)
APPLE_FASTER_POTIONS = 523


def apple_hpregen(maxhp_raw, faster_potions):
    """skills.txt row 47 aurastatcalc1 in the engine's integer arithmetic (stats in their raw units, life * 256)."""
    return int(maxhp_raw / 3000) * (100 + faster_potions) // 100


def apple_state(log):
    """The player's state 44 from `states player 44`: {on, end, stats {stat: value}} (end = the list's end frame)."""
    _, ln = Hl("states player %d" % APPLE_STATE, log) if log is not None else H("states player %d" % APPLE_STATE)
    line = next((l for l in ln if l.startswith("server state %d:" % APPLE_STATE)), "")
    on = "bit=1" in line
    end = first([line], r"end=(-?\d+)") if line else None
    stats = {int(s): int(v) for s, _l, v in re.findall(r" (\d+):(\d+)=(-?\d+)", line.split("stat:layer=value", 1)[-1])} if line else {}
    return {"on": on, "end": end, "stats": stats, "line": line}


def apple_buy(npc, nm, log, shots):
    """A vendor's Trade panel (talk 0x2f, menu line Trade), the Apple found in `shop` and bought by a right click as a player does.
    SET-UP: `gold set` pays for it. Returns the new inventory item dict or None."""
    H("packclear")
    menu = rp_npc_menu(npc, log)
    line = rp_menu_line(menu, RP_TRADE) if menu else None
    if line is None:
        log.append("%s: no Trade line" % nm)
        return None
    Hl("menu %d" % line, log)
    for _ in range(12):
        time.sleep(1.5)
        if trade_panel_open():
            break
    if not trade_panel_open():
        log.append("%s: the trade panel did not open" % nm)
        return None
    H("gold set 900000 0")
    stock = [kv(l) for l in Hl("shop %d" % npc, log)[1] if l.startswith("item ")]
    apples = [s for s in stock if s.get("code") == "dog"]
    shots.append(sh("apple_shop"))
    got = None
    for s in apples[:1]:
        page, x, y = int(s["page"]), int(s["x"]), int(s["y"])
        g.click(RP_SHOP_TABS[page][0] / 1600, RP_SHOP_TABS[page][1] / 900)
        time.sleep(0.8)
        ids0 = {i.get("id") for i in rp_items_now()}
        gold0 = first(H("gold get")[1], r"carried=(\d+)")
        g.click(*rp_inv_xy(x, y, RP_SHOP), button="right")
        time.sleep(1.5)
        gold1 = first(H("gold get")[1], r"carried=(\d+)")
        got = next((i for i in rp_items_now() if i.get("id") not in ids0 and i.get("page") == 0 and i.get("code") == "dog"), None)
        log.append("%s: Apple in stock %s; bought %s for %s" % (nm, s, got, (gold0 - gold1) if gold0 and gold1 else "?"))
    if not apples:
        log.append("%s: no Apple in %d stock items" % (nm, len(stock)))
    rp_close_trade()
    return got


def check_apple_use():
    """Bug #499 on the player path: buy an Apple from Charsi (Trade, right click), use it by a right click in the inventory, then
    read state `mega_apple` (44) on the server's player: its end frame (15000 frames from the use), its five stats against skills row
    47's formulas, and the player's hpregen. SET-UP by harness: gold for the purchase, the four synergy source stats (444 / 498 /
    445 / 461 = 7 / 9 / 11 / 1, so aurastat2-5 are not 0). Then Save and Exit and back in: the Apple stays used up and the game runs
    (1.13c saves no states: `mega_apple` is expected gone after the reload)."""
    mark = engine_mark()
    log, shots, bad = [], [], []
    goto(1)
    for _aura, (src, v) in APPLE_SYNERGY.items():
        Hl("stat player %d set %d" % (src, v), log)
    n0 = len(rc_of("dog", RC_PAGE_INV, log))
    it = apple_buy(154, "Charsi", log, shots)
    if it is None:
        return add("apple_use", "BLOCKED", "no Apple bought from Charsi: %s" % (log[-1] if log else "?"), shots, log)
    s0 = rc_stats(["newskills", "maxhp"], log)
    regen0 = stat_of(Hl("stat player 74", log)[1]) or 0
    fp = stat_of(Hl("stat player %d" % APPLE_FASTER_POTIONS, log)[1]) or 0
    frame0 = first(Hl("state", log)[1], r"frame=(\d+)")
    rc_use(it, log, shots, "apple")
    st = apple_state(log)
    frame1 = first(Hl("state", log)[1], r"frame=(\d+)")
    s1 = rc_stats(["newskills", "maxhp"], log)
    regen1 = stat_of(Hl("stat player 74", log)[1]) or 0
    left = [i for i in rc_of("dog", RC_PAGE_INV, log) if i["id"] == it["id"]]
    want = {74: apple_hpregen(s0["maxhp"] or 0, fp)}
    want.update({aura: v for aura, (_src, v) in APPLE_SYNERGY.items()})
    if left:
        bad.append("the Apple was not used up")
    if not st["on"]:
        bad.append("no state mega_apple (%d) after the use" % APPLE_STATE)
    for sid, v in want.items():
        if st["stats"].get(sid) != v:
            bad.append("%s %s, want %s" % (APPLE_STATS[sid], st["stats"].get(sid), v))
    rest = (st["end"] or 0) - (frame1 or 0)
    if not (frame0 and frame1 and APPLE_FRAMES - (frame1 - frame0) - 2 <= rest <= APPLE_FRAMES):
        bad.append("state lasts %s frames from now (used between frames %s and %s), want %d from the use" % (rest, frame0, frame1, APPLE_FRAMES))
    if regen1 - regen0 != want[74]:
        bad.append("player hpregen %s -> %s, want +%d" % (regen0, regen1, want[74]))
    if (s1["newskills"] or 0) != (s0["newskills"] or 0):
        bad.append("skill points %s -> %s (the Book's effect)" % (s0["newskills"], s1["newskills"]))
    note = ("Apple bought from Charsi (%d in the backpack before), used by a right click: %s; state %d %s, end frame %s at frame %s "
            "(%s frames left, used after frame %s); stats %s (want %s); player hpregen %s -> %s; skill points %s -> %s" % (
                n0, "kept" if left else "used up", APPLE_STATE, "on" if st["on"] else "OFF", st["end"], frame1, rest, frame0,
                {APPLE_STATS[k]: v for k, v in st["stats"].items() if k in APPLE_STATS}, {APPLE_STATS[k]: v for k, v in want.items()},
                regen0, regen1, s0["newskills"], s1["newskills"]))
    log.append("state 44 line: %s" % st["line"])
    shots.append(sh("apple_after"))
    for _aura, (src, _v) in APPLE_SYNERGY.items():
        Hl("stat player %d set 0" % src, log)
    finish("apple_use", not bad, "SET-UP: gold and the synergy source stats %s by harness; " % {s_: v for s_, v in APPLE_SYNERGY.values()}
           + note + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log)
    # Save and Exit, then back in (own row: Save and Exit's pool asserts are exit-only, the mark is taken after the reload)
    log, shots = [], []
    if not rc2_save_exit():
        return add("apple_save", "FAIL", "Save and Exit did not leave the game", shots, log)
    back = enter_game(card_of(g.CHAR_NAME) or 1, "normal")
    mark = engine_mark()
    st2 = apple_state(log) if back else {"on": None}
    still = [i for i in rc_of("dog", RC_PAGE_INV, log) if i["id"] == it["id"]] if back else []
    shots.append(sh("apple_reload"))
    finish("apple_save", back and game_alive() and not still,
           "Save and Exit and back in: %s; the used Apple %s; state mega_apple after the reload: %s (1.13c saves no states)" % (
               "entered" if back else "NOT entered", "is back" if still else "stays gone", "on" if st2["on"] else "off"),
           mark, shots, log)


def refund_verdict(before, after, spent_stats, spent_skills):
    """#240 SK9 as 1.13c: the token gives back every spent stat point (strength back where it started) and every hard skill point.
    True when both pools grew by exactly what was spent."""
    return (after["statpts"] - before["statpts"] == spent_stats and after["newskills"] - before["newskills"] == spent_skills
            and after["strength"] == before["strength"] - spent_stats)


def check_rc2refund():
    """#240 SK9: the Token of Absolution's refund. SET-UP by harness: strength +20 with no unspent stat points ("spent"), the set-up
    skills (hard points), no unspent skill points. Player path: Oil of Absolution and an El rune picked up, clicked onto the cube,
    Transmute, the token lifted into the inventory and used by a right click (`check_rctoken`, its own row)."""
    mark = engine_mark()
    log, shots = [], []
    goto(1)
    st0 = stat_of(Hl("stat player 0", log)[1])
    Hl("stat player 0 set %d" % (st0 + RC2_STR_SPENT), log)
    Hl("stat player 4 set 0", log)
    Hl("stat player 5 set 0", log)
    before = dict(rc_stats(["statpts", "newskills"], log), strength=stat_of(Hl("stat player 0", log)[1]))
    skills = sum(lv for _s, lv in RC2_SKILLS)
    known = [s for s, _lv in RC2_SKILLS if rc_skill_level(s, log)]
    check_rctoken()
    after = dict(rc_stats(["statpts", "newskills"], log), strength=stat_of(Hl("stat player 0", log)[1]))
    left = [s for s, _lv in RC2_SKILLS if rc_skill_level(s, log)]
    shots.append(sh("refund_after"))
    ok = refund_verdict(before, after, RC2_STR_SPENT, skills)
    finish("rc2refund", ok, "SET-UP: strength %s -> %s (+%d spent), %d hard skill points %s, no unspent points; token used: stat points "
           "%s -> %s, skill points %s -> %s, strength %s -> %s, skills held after %s; 1.13c gives back %d stat and %d skill points" % (
               st0, before["strength"], RC2_STR_SPENT, skills, known, before["statpts"], after["statpts"], before["newskills"],
               after["newskills"], before["strength"], after["strength"], left, RC2_STR_SPENT, skills), mark, shots, log)


RC2_SKILLDELAY = 121  # states.txt `skilldelay`: D2R's unit-wide hold, set from a skill's `globaldelay` (1.13c's one delay)


def rc2_frame(log):
    """The server frame (25 per second) from `h state`."""
    return first(Hl("state", log)[1], r"frame=(\d+)")


def rc2_cooldown(skill, log):
    """D2R's own cooldown of `skill`: stat 359 (skill_cooldown) at layer = skill id holds the end frame of its `localdelay` (docs
    d2r-addresses.md, cooldown start 0x439500); 0 when none was started."""
    return stat_of(Hl("stat player 359 %d" % skill, log)[1]) or 0


def rc2_held(log):
    """True when the player carries state `skilldelay` (the unit-wide hold a `globaldelay` starts)."""
    return any("state %d:" % RC2_SKILLDELAY in ln for ln in Hl("states player", log)[1])


def rc2_wait_ready(skills, log, limit=40):
    """Wait (at most `limit` s) until no skill of `skills` is on its own cooldown, so a refusal can only come from the other one."""
    for _ in range(limit):
        now = rc2_frame(log) or 0
        if all(rc2_cooldown(s, log) <= now for s in skills) and not rc2_held(log):
            return True
        time.sleep(1)
    return False


def rc2_try(skill, log):
    """A right click with `skill` on the right button. The cast happened when the skill's own cooldown got a new end frame (Holy
    Armor's mana use does not show in stat 8, lane rulescheck2 probe s9). Returns (cast, end frame before, end frame after, frame,
    skilldelay state after)."""
    Hl("skill right %d" % skill, log)
    time.sleep(0.4)
    e0, now = rc2_cooldown(skill, log), rc2_frame(log)
    g.click(0.56, 0.48, button="right")
    time.sleep(1.2)
    e1 = rc2_cooldown(skill, log)
    return e1 != e0 and e1 > (now or 0), e0, e1, now, rc2_held(log)


def check_rc2delay():
    """CH13 / SK6 with two delay skills, every cast a right click (the skill put on the right button by `h skill right`, as the skill
    bar does): Mythal, Holy Armor at once; 13 s later (Mythal's 245 frames are over) Mythal, Holy Armor at once. A cast is read from
    the skill's own D2R cooldown (stat 359 at layer = skill gets a new end frame), the unit-wide hold from state `skilldelay`.
    SET-UP: skills by `setskill` (Mythal is a Druid skill the game's skill-point function gives the paladin), mana 1000, both skills
    off cooldown first. 1.13c (one unit-wide delay): both Holy Armor casts refused, both Mythal casts work. D2R with only `localdelay`
    filled: each skill keeps its own cooldown, so the first Holy Armor goes through."""
    mark = engine_mark()
    log, shots = [], []
    goto(2)
    for s, lv in RC2_SKILLS + ((RC2_DELAY[0], 1),):
        Hl("setskill %d %d" % (s, lv), log)
    Hl("stat player 9 set %d" % (1000 << 8), log)
    ready = rc2_wait_ready(RC2_DELAY, log)
    casts = []
    for label, skill, wait in (("Mythal", RC2_DELAY[0], 0), ("Holy Armor at once", RC2_DELAY[1], 0),
                               ("Mythal after 13 s", RC2_DELAY[0], 13), ("Holy Armor at once", RC2_DELAY[1], 0)):
        time.sleep(wait)
        Hl("stat player 8 set %d" % (1000 << 8), log)
        casts.append((label,) + rc2_try(skill, log))
        shots.append(sh("delay2_%d" % len(casts)))
    goto(1)
    did = [x[1] for x in casts]
    note = "SET-UP: skills by setskill (Mythal given to the paladin), mana 1000, both off cooldown first (%s); " % ready + "; ".join(
        "%s at frame %s: %s (own cooldown end %s -> %s, skilldelay state %s)" % (lab, now, "cast" if ok else "refused", e0, e1, held)
        for lab, ok, e0, e1, now, held in casts)
    if not ready or not did[0] or not did[2]:
        return add("rc2delay", "BLOCKED", note + "; a Mythal cast did not happen or a cooldown was still running", shots, log)
    finish("rc2delay", not did[1] and not did[3], note + "; 1.13c: both Holy Armor casts refused inside Mythal's delay (one unit-wide "
           "delay)", mark, shots, log)


RC2_DEATH_PCT = {"nightmare": 1, "hell": 1}  # difficultylevels DeathExpPenalty, Median 2012 (vanilla 5 / 10)


def death_loss(exp, level_start, next_start, pct):
    """1.13c's death penalty: pct % of the current level's span, never below the level's start."""
    return min(exp - level_start, (next_start - level_start) * pct // 100)


def rc2_death(difficulty):
    """XP5 on `difficulty`: Save and Exit, Play in that difficulty (unlocked by rc2setup's save edit), experience half-way through
    level 30 (harness SET-UP), zombies placed next to the character (SET-UP), then the character stands until the monsters kill it
    (a real death: no god mode) and respawns by Esc. Median: 1 % of the level span (lost at death), vanilla 5 % / 10 %."""
    log, shots = [], []
    if not rc2_save_exit():
        return add("rc2death_" + difficulty, "BLOCKED", "Save and Exit did not leave the game", shots, log)
    ok = enter_game(card_of(g.CHAR_NAME) or 1, difficulty)
    p = hstate()["player"]
    if not ok or str(p.get("difficulty")) != str({"nightmare": 1, "hell": 2}[difficulty]):
        return add("rc2death_" + difficulty, "BLOCKED", "not in %s (entered %s, difficulty %s)" % (difficulty, ok, p.get("difficulty")),
                   shots, log)
    mark = engine_mark()  # after Save and Exit: its pool asserts are exit-only (docs/testing.md)
    goto(2)
    lo, hi = rc2_set_level(RC2_LEVEL, log)
    xp0 = rc_stats(["experience"], log)["experience"]
    px, py = player_xy()
    Hl("spawn 5 6 %d %d" % (px + 2, py), log)
    t0, dead = time.time(), False
    while time.time() - t0 < 120:
        if player_dead(hstate()["player"]):
            dead = True
            break
        time.sleep(1)
    shots.append(sh("death_" + difficulty))
    xp1 = rc_stats(["experience"], log)["experience"]
    revive_if_dead()
    xp2 = rc_stats(["experience"], log)["experience"]
    want = death_loss(xp0, lo, hi, RC2_DEATH_PCT[difficulty])
    note = ("SET-UP: %s, level 30 with experience %s (level span %s-%s), zombies placed; experience %s at death, %s after the respawn "
            "(died: %s); Median loses %d (1 %% of the span), vanilla %d" % (
                difficulty, xp0, lo, hi, xp1, xp2, dead, want, death_loss(xp0, lo, hi, 5 if difficulty == "nightmare" else 10)))
    goto(1)
    if not dead:
        return add("rc2death_" + difficulty, "BLOCKED", note + "; no death in 120 s", shots, log)
    finish("rc2death_" + difficulty, xp0 - xp2 == want, note, mark, shots, log)


def check_rc2death():
    """XP5 on Nightmare and Hell (rc2_death), then back to Normal."""
    rc2_death("nightmare")
    rc2_death("hell")
    if rc2_save_exit():
        enter_game(card_of(g.CHAR_NAME) or 1, "normal")


# ---------------------------------------------------------------- player-path checks (lane realpath, docs/testing.md "Player-path checks")
# Players can hit crashes that shortcut checks never reach: items made straight into the
# backpack (`item X inv`), god mode / huge life (Tank), harness spawns and warps. These checks take the paths a player's client
# takes: an item lies on the ground and is picked up with the pick-up packet 0x16 (what a click on it sends), moved with the
# cursor packets 0x18 / 0x19 / 0x1a / 0x1c, hovered with the (virtual) mouse for its tooltip; vendors, gambling, potions and the
# cube are used with background mouse clicks on the real panels; damage is taken from natural monsters, the character dies and
# respawns; areas are reached by waypoint (operate + 0x49) and walked. No god mode, no Tank, no `stat ... life`, no `item ... inv`.
# Set-up shortcuts that stay (each check says when it uses one): the character's level comes from `xp` (the engine's own experience
# award, so level-ups, life and stat points are natural) and the points are spent with the stat panel's packet 0x3a; `gold set`
# pays for purchases and gambles; waypoint bits of later acts are set before their waypoints are used; `level <id> warp` puts the
# character at a level's entrance where no waypoint goes (the cave entrance's own server warp); items are made on the GROUND by the
# harness generator (as a monster drop would).
RP_BODY = {"head": 1, "neck": 2, "tors": 3, "rarm": 4, "larm": 5, "rrin": 6, "lrin": 7, "belt": 8, "feet": 9, "glov": 10}
RP_HANDS = {4, 5}  # rarm, larm
RP_CLASS = {"ama": "amazon", "sor": "sorceress", "nec": "necromancer", "pal": "paladin", "bar": "barbarian", "dru": "druid", "ass": "assassin"}
RP_CHARS = {"amazon": ("RpAma", 0), "sorceress": ("RpSor", 1), "necromancer": ("RpNec", 2), "paladin": ("RpPal", 3),
            "barbarian": ("RpBarb", 4), "druid": ("RpDru", 5), "assassin": ("RpAss", 6)}
RP_INV = (1049, 393, 44, 42)       # HD backpack grid (1600 x 900 client): left, top, cell w, cell h (INV_CELL)
RP_CUBE = (122, 107, 44, 42)       # Median's 10 x 8 cube grid in the HD cube panel
RP_TRANSMUTE = (340, 487)          # the cube panel's Transmute button
RP_SHOP = (137, 183, 40.8, 40.9)   # the vendor panel's grid (HD): left, top, cell w, cell h (measured on Gheed's panel 2026-10-28)
RP_SHOP_TABS = [(185, 170), (289, 170), (393, 170), (497, 170)]  # vendor tabs (page 0-3: armour, weapons, (magic), misc)
RP_SHOP_CLOSE = (563, 103)
RP_FREE_CELL = (4, 3)              # a backpack cell the test characters keep empty (items pass through it)
RP_LEVEL = 120                     # the item checks' characters: `xp` up to about this level (requirements of most bases)


def _rp_rows(name):
    try:
        return table(name)
    except OSError:
        return []


def rp_type_chain(itypes, code, seen=None):
    """The item type and every type it is equivalent to (Equiv1 / Equiv2, recursively)."""
    seen = seen if seen is not None else []
    if not code or code in seen or code not in itypes:
        return seen
    seen.append(code)
    for k in ("Equiv1", "Equiv2"):
        rp_type_chain(itypes, itypes[code].get(k, ""), seen)
    return seen


def rp_item_info(itypes, base):
    """(body location name or '', class name or '') of a base row (weapons / armor / misc): the first type in the chain with a
    BodyLoc1 / Class."""
    chain = rp_type_chain(itypes, base.get("type", "")) + rp_type_chain(itypes, base.get("type2", ""))
    loc = next((itypes[t].get("BodyLoc1", "") for t in chain if itypes[t].get("Body") == "1" and itypes[t].get("BodyLoc1")), "")
    cls = next((itypes[t].get("Class", "") for t in chain if itypes[t].get("Class")), "")
    return loc, RP_CLASS.get(cls, cls)


def rp_item_plan(itypes_rows, bases, uniques, sets, hd_entries):
    """The representative items of the player-path item check: one base per itemtypes row (a base whose type / type2 is that row,
    spawnable first, then the lowest level requirement), one more per HD item table asset not covered yet, one unique row per base
    type and one set row per base type. Each: dict(code, args (for `item`), why, loc, cls). Types without a base of their own
    (abstract ones such as `weap`) are returned in `abstract`."""
    itypes = {r["Code"]: r for r in itypes_rows if r.get("Code")}
    by_code = {b["code"]: b for b in bases if b.get("code")}

    def rank(b):
        lv = b.get("levelreq") or b.get("level") or "0"
        return (0 if b.get("spawnable") == "1" else 1, int(lv) if lv.lstrip("-").isdigit() else 999, b["code"])

    plan, have, abstract = [], set(), []

    def add_item(code, args, why):
        b = by_code[code]
        loc, cls = rp_item_info(itypes, b)
        plan.append({"code": code, "args": args, "why": why, "loc": loc, "cls": cls, "type": b.get("type", ""),
                     "noinv": "0" in (b.get("invwidth"), b.get("invheight"))})

    for code in itypes:
        cands = sorted((b for b in by_code.values() if code in (b.get("type"), b.get("type2"))), key=rank)
        if not cands:
            abstract.append(code)
            continue
        c = cands[0]["code"]
        if c not in have:
            have.add(c)
            add_item(c, c, "itemtypes %s" % code)
    assets = {}
    for e in hd_entries:
        for code, v in e.items():
            if code in by_code:
                assets.setdefault((v or {}).get("asset", ""), []).append(code)
    for asset, codes in sorted(assets.items()):
        if not any(c in have for c in codes):
            c = sorted(codes, key=lambda x: rank(by_code[x]))[0]
            have.add(c)
            add_item(c, c, "hd asset %s" % asset)
    for rows, key, quality in ((uniques, "code", "unique"), (sets, "item", "set")):
        seen_types = set()
        for i, r in enumerate(rows):
            code = r.get(key, "")
            if code not in by_code or r.get("disabled", "") not in ("", "0") or not (r.get("index") or r.get("*ID")):
                continue
            t = by_code[code].get("type", "")
            if t in seen_types:
                continue
            seen_types.add(t)
            add_item(code, "%s %s %d" % (code, quality, i), "%s row %d (%s, type %s)" % (quality, i, r.get("index", ""), t))
    return plan, abstract


def rp_plan_from_tables():
    import json as _json
    bases = _rp_rows("weapons") + _rp_rows("armor") + _rp_rows("misc")
    hd = []
    p = os.path.normpath(os.path.join(EXCEL, "..", "..", "hd", "items", "items.json"))
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            hd = _json.load(f)
    return rp_item_plan(_rp_rows("itemtypes"), bases, _rp_rows("uniqueitems"), _rp_rows("setitems"), hd)


def rp_recover(label, log):
    """After a crash: back into the game with the same character (the next item goes on)."""
    log.append("RECOVER after %s" % label)
    STATE["in_game"] = False
    try:
        g.stop()
    except Exception:
        pass
    time.sleep(3)
    lock(60)
    return to_menu() and enter_initial_character()


def rp_ready(level=RP_LEVEL, split=(0.5, 0.35, 0.15)):
    """Natural progress for an item character: `xp` until the level (the engine's level-ups give life, mana and the points), then
    the unused stat points spent with the stat panel's packet 0x3a (shift-click = 5 points) on Strength / Dexterity / Vitality."""
    p = hstate()["player"]
    if p.get("level", 1) < level:
        for amount in (100000, 1000000, 10000000, 100000000) + (2000000000,) * 8:
            ok, l = H("xp %d" % amount)
            lv = first(l, r"level=(\d+)")
            if lv is not None and lv >= level:
                break
    pts = rd("player", 4) or 0
    for stat, share in zip((0, 2, 3), split):
        for _ in range(int(pts * share) // 5):
            H("pkt 3a %02x 00 04 00" % stat)
    for _ in range((rd("player", 4) or 0) // 5):
        H("pkt 3a 03 00 04 00")
    return hstate()["player"]


def rp_be(cls):
    """Play the lane's character of that class (made when missing) and make it ready."""
    name, cid = RP_CHARS[cls]
    if hstate()["player"].get("class") != cid or g.CHAR_NAME != name:
        g.CHAR_NAME = name
        if not switch_character(name, cls, cid):
            return None
    goto(1)
    STATE.pop("rp_stats", None)
    STATE.pop("rp_panel", None)
    return rp_ready()


def rp_inv_xy(x, y, grid=RP_INV):
    return (grid[0] + (x + 0.5) * grid[2]) / 1600.0, (grid[1] + (y + 0.5) * grid[3]) / 900.0


def rp_items_now():
    """The player's items (`h items`: backpack page 0, cube 3, stash 4, worn 255 with x = body location); our `state` lists none."""
    _ok, lines = H("items")
    return [{k: (int(v) if re.fullmatch(r"-?\d+", v) else v) for k, v in kv(ln).items()} for ln in lines if ln.startswith("item ")]


def rp_item_line(iid):
    return next((it for it in rp_items_now() if it.get("id") == iid), None)


def rp_ground_item(args, log):
    """`item <args> ground`: the generator's item on the ground next to the player; returns its unit id or None."""
    ok, lines = Hl("item %s ground" % args, log)
    text = " ".join(lines)
    m = re.search(r"item id=(\d+)", text)
    off = re.search(r"asked for quality 5 row (\d+), the generator made quality 5 index (\d+)", text)
    if not ok and m and off and int(off.group(2)) == int(off.group(1)) - 1:
        ok = True  # setitems.txt's separator row: the set item index is the file row - 1 past it (the same item)
    return int(m.group(1)) if ok and m else None


def rp_ground_pos(iid):
    """(x, y, distance) of an item lying on the ground (`h ground`), None when it is not there."""
    _ok, lines = H("ground")
    for ln in lines:
        m = re.match(r"ground id=%d code=\S+ mode=\d+ x=(\d+) y=(\d+) dist=([\d.]+)" % iid, ln)
        if m:
            return int(m.group(1)), int(m.group(2)), float(m.group(3))
    return None


def rp_pickup(iid, log, to_inv=False):  # noqa: C901
    """A click on the item: the character walks next to it first (a drop lands up to a few sub-tiles away), then the pick-up packet
    0x16 (to the cursor; `to_inv`: a plain click, into the backpack or onto an empty body location). True when it left the ground."""
    if held_item():  # a pick-up with an item on the cursor is refused
        release_held_item()
    pos = rp_ground_pos(iid)
    if pos is None:
        return False
    if pos[2] > 2.5:
        Hl("move %d %d" % (pos[0], pos[1] - 1), log)
        time.sleep(1.0)
    Hl("pickup %d%s" % (iid, " inv" if to_inv else ""), log)
    for _ in range(10):
        time.sleep(0.4)
        held = held_item()
        if held and held[0] == iid:
            return True
        if rp_ground_pos(iid) is None:
            return True
    return False


def rp_stow(iid, log):
    """The item on the cursor back into the backpack's free cell (0x18), then taken away (`remove id`); dropped at the feet only
    when the backpack refuses it."""
    held = held_item()
    for x, y in (RP_FREE_CELL, (6, 2), (6, 0)):
        if not held or held[0] != iid:
            break
        Hl("pkt 18 " + _le(iid, x, y, 0), log)
        time.sleep(0.5)
        held = held_item()
    Hl("remove id %d" % iid, log)
    if held_item():
        release_held_item()


def rp_requirements(code, args=""):
    """{name: (needed, the character's)} of a base's Strength / Dexterity / level requirement (the base row; a unique or set row's
    own level requirement is higher, see `lvl req`)."""
    b = row_of("weapons", "code", code) or row_of("armor", "code", code) or row_of("misc", "code", code) or {}
    if "rp_stats" not in STATE:
        STATE["rp_stats"] = (rd("player", 0) or 0, rd("player", 2) or 0, rd("player", 12) or 0)
    st, dx, lv = STATE["rp_stats"]
    num = lambda v: int(v) if str(v).lstrip("-").isdigit() else 0
    level = num(b.get("levelreq"))
    m = re.search(r" (unique|set) (\d+)", args)
    if m:  # the unique / set row's own level requirement
        rows = table("uniqueitems" if m.group(1) == "unique" else "setitems")
        level = max(level, num(rows[int(m.group(2))].get("lvl req")) if int(m.group(2)) < len(rows) else 0)
    return {"Str": (num(b.get("reqstr")), st), "Dex": (num(b.get("reqdex")), dx), "level": (level, lv)}


def rp_tooltip_shot(iid, label, shots, sample):
    """The item in the backpack hovered with the virtual mouse (inventory panel open): the game builds its tooltip. A screenshot
    for every `sample`-th item (the tooltip text stays a manual look)."""
    it = rp_item_line(iid)
    if not it or it.get("page") != 0:
        return False
    if not STATE.get("rp_panel") or sample:  # the panel stays open between items (checked again on screenshot items)
        STATE["rp_panel"] = right_panel_open()
    if not STATE["rp_panel"]:
        STATE["rp_panel"] = True
        g.press("i")
        time.sleep(1.0)
    g.click(*rp_inv_xy(it.get("x", 0), it.get("y", 0)), move_only=True)
    time.sleep(0.5)
    if sample:
        shots.append(sh("rp_tip_%s" % re.sub(r"[^A-Za-z0-9]+", "_", label)[:40]))
    g.click(0.45, 0.30, move_only=True)  # away from the item
    return True


def rp_item_round(spec, log, shots, sample):
    """One item the way a player handles it. Returns (status, note): PASS, REFUSED (the game refused to wear it: requirements /
    class), FAIL (wrong state), CRASH."""
    code, args, loc = spec["code"], spec["args"], spec["loc"]
    pids = sorted(g.game_pids())
    steps = []

    def dead():  # the process is gone or changed (a harness command that times out raises and is a crash too)
        return not g.game_pids() or sorted(g.game_pids()) != pids

    H("packclear")  # room in the backpack (the test character's own items go too)
    iid = rp_ground_item(args, log)
    if iid is None:
        return "FAIL", "the generator made no item (%s)" % args
    steps.append("ground")
    if not rp_pickup(iid, log):
        return ("CRASH" if dead() else "FAIL"), "pick-up 0x16 did not take the item (%s)" % " / ".join(steps)
    steps.append("picked up")
    if dead():
        return "CRASH", "the game died at the pick-up (0x16)"
    for x, y in (RP_FREE_CELL, (6, 2), (6, 0)):  # cursor -> backpack (the click on a backpack cell); a 4-row item fits only at row 0
        held = held_item()
        if not held or held[0] != iid:
            break
        Hl("pkt 18 " + _le(iid, x, y, 0), log)
        time.sleep(0.5)
    it = rp_item_line(iid)
    if dead():
        return "CRASH", "the game died putting the item into the backpack (0x18)"
    if it is None or it.get("page") != 0:
        release_held_item()
        return "FAIL", "the item did not land in the backpack (cursor %s)" % (held_item(),)
    steps.append("backpack")
    rp_tooltip_shot(iid, spec["why"], shots, sample)
    if dead():
        return "CRASH", "the game died hovering the item (tooltip)"
    steps.append("tooltip")
    status, note = "PASS", ""
    if loc in RP_BODY:
        body = RP_BODY[loc]
        Hl("unequip %d" % body, log)  # the slot empty (the character's own starting item is freed)
        if body in RP_HANDS:  # both hands empty: 1.13c's rules refuse a two-hander next to anything but its own ammunition, a
            # second shield, and a quiver next to a weapon that does not shoot it (an earlier round left a quiver or katar there)
            Hl("unequip %d" % (RP_HANDS - {body}).pop(), log)
        Hl("pkt 19 " + _le(iid, it.get("x", 0), it.get("y", 0), 0), log)  # backpack -> cursor
        time.sleep(0.4)
        Hl("pkt 1a " + _le(iid, body), log)  # cursor -> body location
        time.sleep(0.8)
        if dead():
            return "CRASH", "the game died wearing the item (0x1a, %s)" % loc
        worn = rp_item_line(iid)
        if worn is not None and worn.get("page") == 255:
            steps.append("worn")
            time.sleep(0.6)  # drawn on the character for a few frames
            Hl("pkt 1c " + _le(iid, body), log)  # body -> cursor (the click on the worn item)
            time.sleep(0.5)
            if dead():
                return "CRASH", "the game died taking the item off (0x1c)"
            if held_item() and held_item()[0] == iid:
                steps.append("taken off")
            else:
                status, note = "FAIL", "0x1c did not take the item off"
        else:
            req = rp_requirements(code, args)
            short = [k for k, (need, have) in req.items() if need > have]
            status, note = ("REFUSED", "not worn: requirement above the character's (%s)" % ", ".join(
                "%s %d > %d" % (k, req[k][0], req[k][1]) for k in short)) if short else (
                "FAIL", "not worn although the character meets the requirements %s" % req)
    rp_stow(iid, log)
    if dead():
        return "CRASH", "the game died after %s" % " / ".join(steps)
    return status, (note or " / ".join(steps))


def check_rp_items():
    """Player path (a): every representative item (rp_item_plan) dropped on the ground, picked up (0x16), into the backpack (0x18),
    its tooltip hovered, worn (0x19 / 0x1a) by a character of a class that can wear it and taken off (0x1c). MXL_RP_ONLY=<code,...>
    limits the items, MXL_RP_CLASSES=<class,...> the characters, MXL_RP_SLICE=<a>:<b> each class's items a..b-1 (long runs in
    batches), MXL_RP_SHOTS=n takes a tooltip screenshot every n-th item."""
    mark = engine_mark()
    plan, abstract = rp_plan_from_tables()
    only = set(filter(None, (os.environ.get("MXL_RP_ONLY") or "").split(",")))
    if only:
        plan = [p for p in plan if p["code"] in only]
    classes = [c for c in (os.environ.get("MXL_RP_CLASSES") or ",".join(RP_CHARS)).split(",") if c in RP_CHARS]
    every = int(os.environ.get("MXL_RP_SHOTS") or 25)
    log, shots, rows, results = [], [], [], {}
    for cls in classes:
        mine = [p for p in plan if p["cls"] == cls or (p["cls"] == "" and cls == "barbarian")]
        cut = (os.environ.get("MXL_RP_SLICE") or ":").split(":")
        mine = mine[int(cut[0] or 0):int(cut[1]) if len(cut) > 1 and cut[1] else None]
        if not mine:
            continue
        p = rp_be(cls)
        if not p:
            rows.append("%s: could not play the class character" % cls)
            continue
        rows.append("%s: level %s, Str %s Dex %s, life %s, %d items" % (cls, p.get("level"), rd("player", 0), rd("player", 2), p.get("life"), len(mine)))
        H("packclear")
        for n, spec in enumerate(mine):
            g.log("RP item %s (%s) as %s" % (spec["code"], spec["why"], cls))
            if spec.get("noinv"):  # Median's cm1-cm3: 0 x 0 cells, in no treasure class, shop or recipe; picked up they crash (#393)
                results[(cls, spec["code"], spec["args"])] = ("SKIP", "0 x 0 inventory size, no player source (bug #393)", spec)
                rows.append("%s %s [%s]: SKIP (0 x 0 inventory size, bug #393)" % (cls, spec["code"], spec["why"]))
                continue
            try:
                status, note = rp_item_round(spec, log, shots, n % every == 0)
            except Exception as e:  # the harness stopped answering: a crash
                status, note = ("CRASH" if not g.game_pids() else "FAIL"), "script: %r" % (e,)
            results[(cls, spec["code"], spec["args"])] = (status, note, spec)
            rows.append("%s %s [%s] %s: %s %s" % (cls, spec["code"], spec["why"], spec["loc"] or "-", status, note))
            if status == "CRASH":
                shots_crash = []
                try:
                    shots_crash = [sh("rp_crash_%s" % spec["code"])]
                except Exception:
                    pass
                shots += shots_crash
                if not rp_recover(spec["code"], log) or not rp_be(cls):
                    rows.append("%s: no way back into the game after the crash" % cls)
                    break
                H("packclear")
    counts = {}
    for st, _n, _s in results.values():
        counts[st] = counts.get(st, 0) + 1
    report = os.path.join(g.current_run(), "rp_items.tsv")
    with open(report, "w", encoding="utf-8") as f:
        f.write("class\tcode\targs\twhy\tloc\tstatus\tnote\n")
        for (cls, code, args), (st, note, spec) in sorted(results.items()):
            f.write("\t".join((cls, code, args, spec["why"], spec["loc"], st, note.replace("\t", " "))) + "\n")
    crashes = [k for k, v in results.items() if v[0] == "CRASH"]
    fails = [k for k, v in results.items() if v[0] == "FAIL"]
    note = "%d representative items (%d itemtypes rows without a base of their own: %s), results %s; per item: rp_items.tsv" % (
        len(results), len(abstract), ",".join(abstract[:12]), counts)
    if crashes:
        note += "; CRASHES: %s" % ", ".join("%s/%s" % (k[0], k[1]) for k in crashes[:10])
    if fails:
        note += "; FAIL: %s" % ", ".join("%s/%s" % (k[0], k[1]) for k in fails[:10])
    finish("rp_items", not crashes and not fails, note, mark, shots[:30], rows + log[-400:])


# --- (b) vendors ----------------------------------------------------------------------------------------------------------
RP_VENDORS = {1: [(148, "Akara"), (154, "Charsi"), (147, "Gheed")], 40: [(177, "Drognan"), (178, "Fara"), (199, "Elzix"), (202, "Lysander")],
              75: [(255, "Ormus"), (254, "Alkor"), (252, "Asheara"), (253, "Hratli")], 103: [(405, "Jamella"), (257, "Halbu")],
              109: [(511, "Larzuk"), (513, "Malah"), (512, "Drehya")]}
RP_TOWN_WP = {1: 0, 40: 9, 75: 18, 103: 27, 109: 30}


def trade_panel_open():
    """The vendor / gamble panel's red close button (X) is on screen (HD)."""
    im = g.grab_client(g.need_window()).convert("RGB").crop((552, 92, 576, 114))
    px = list(im.getdata())
    return sum(1 for r, gr, b in px if r > 50 and r > 2 * gr and r > 2 * b) > 0.15 * len(px)  # open 41 %, closed 0 %


def rp_menu_line(menu, wanted):
    """Index of a menu line by its handler (the line's text differs: Trade 0xd44 at Gheed, Trade/Repair 0xd06 at Charsi, both open
    the trade panel through image+0x112f30; Gamble image+0x112c80)."""
    for ln in menu or []:
        m = re.search(r"line (\d+) string=0x[0-9a-f]+ handler=image\+0x([0-9a-f]+)", ln)
        if m and int(m.group(2), 16) in wanted:
            return int(m.group(1))
    return None


RP_TRADE = {0x112f30}
RP_GAMBLE = {0x112c80}


def rp_close_trade():
    """The trade / gamble / waypoint panel closed with its X (Esc as the fallback), then the NPC menu."""
    for _ in range(3):
        if not trade_panel_open():
            break
        g.click(RP_SHOP_CLOSE[0] / 1600, RP_SHOP_CLOSE[1] / 900)
        time.sleep(1.0)
        if trade_panel_open():
            g.key("esc")
            time.sleep(0.8)
    close_menu()


def rp_walk_to(x, y, reach=4, tries=6):
    """`move` (the walk packets' server function) until the character stands within `reach` of the point."""
    for _ in range(tries):
        p = hstate()["player"]
        if abs(p.get("x", 0) - x) + abs(p.get("y", 0) - y) <= reach:
            return True
        H("move %d %d" % (x, y))
        time.sleep(2.0)
    p = hstate()["player"]
    return abs(p.get("x", 0) - x) + abs(p.get("y", 0) - y) <= reach + 2


def rp_server_walk(npc, log, tries=8):
    """`moveto nearest <npc>` until the NPC is in `state`'s view; each call walks one server path leg. False when it is not
    loaded (None) or the character stops getting closer (False)."""
    best = None
    for _ in range(tries):
        to = parse_moveto(Hl("moveto nearest %d" % npc, log)[1])
        if not to:
            return None
        time.sleep(4)
        p = hstate()["player"]
        d = max(abs(p.get("x", 0) - to["x"]), abs(p.get("y", 0) - to["y"]))
        if any(m.get("class") == npc for m in hstate()["mons"]):
            return True
        if best is not None and d >= best:
            log.append("rp_server_walk: %d stalled at %d" % (npc, d))
            return False
        best = d
    return False


RP_RING = [(dx * r, dy * r) for r in (20, 10) for dx, dy in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (-1, 1), (1, -1), (-1, -1))]


def rp_ring_approach(npc, log):
    """The server path stalled at a wall (Drognan 34 away, Larzuk 42, runs checks-20261029-000330-s3): walk to points round the
    NPC (radius 20, then 10) and try the server path from each, so the side with the door is found. True when it is in view."""
    to = parse_moveto(H("moveto nearest %d" % npc)[1])
    if not to:
        return False
    for k, (dx, dy) in enumerate(RP_RING):
        acts_walk(to["x"] + dx, to["y"] + dy, reach=4, timeout=20)
        rp_server_walk(npc, log, tries=3)
        if any(m.get("class") == npc and m.get("dist", 99) <= 8 for m in hstate()["mons"]):
            log.append("rp_ring_approach: %d reached from ring point %d (%+d,%+d)" % (npc, k, dx, dy))
            return True
    return False


def rp_npc_menu(npc, log=None):
    """Walk up to the town's NPC (`moveto nearest`, repeated: no copy spawned), then talk (0x2f) and wait for the menu."""
    log = log if log is not None else []
    close_menu()
    for _ in range(8):
        if npc_within(npc, 5):
            break
        if not any(m.get("class") == npc for m in hstate()["mons"]):
            # not in view (`state` lists units within 40): the server's own path first (`moveto nearest` finds a loaded NPC out of
            # view and walks round walls; straight legs stuck at a Lut Gholein wall 70 from Drognan, run checks-20261028-211447-s3),
            # then legs round the arrival for an NPC whose rooms are not loaded yet (not acts_approach: its straight legs to the
            # preset spot take 12 x 90 s at a wall)
            walked = rp_server_walk(npc, log)
            if walked is None:  # its rooms are not loaded: lane acts' legs round the arrival until the server knows it
                p = hstate()["player"]
                for dx, dy in EXPLORE_LEGS:
                    acts_walk(p["x"] + dx, p["y"] + dy, reach=15, timeout=40)
                    walked = rp_server_walk(npc, log)
                    if walked is not None:
                        break
                else:
                    log.append("rp_npc_menu: %d not found walking the town" % npc)
                    return None
            if walked is False:
                break  # stalled out of view: the ring of approach points, then the click towards it, below
            continue
        ok, l = Hl("moveto nearest %d" % npc, log)
        if not ok:
            log.append("rp_npc_menu: %d not found" % npc)
            return None
        time.sleep(3.5)
        near = [m for m in hstate()["mons"] if m.get("class") == npc]
        if near and near[0].get("dist", 99) > 8:  # the server path stalled (Larzuk at 42): walk legs toward where it stands
            acts_walk(near[0]["mx"], near[0]["my"], reach=4, timeout=30)
    near = [m for m in hstate()["mons"] if m.get("class") == npc]
    log.append("rp_npc_menu: %d near: %s" % (npc, near[:1]))
    if not near:
        to = parse_moveto(H("moveto nearest %d" % npc)[1])
        near = [{"mx": to["x"], "my": to["y"], "dist": 99}] if to else []
    if near and near[0].get("dist", 99) > 8 and rp_ring_approach(npc, log):
        near = [m for m in hstate()["mons"] if m.get("class") == npc]
    if near and near[0].get("dist", 99) > 5 and not trade_panel_open():  # the server path stalled: click the NPC as a player does
        if rp_click_toward(near[0]["mx"], near[0]["my"], lambda: g.hcmd("menu list", 5)[0], tries=10):
            return wait_menu(10)
    for attempt in range(3):
        close_menu()
        ok, l = Hl("interact %d" % npc, log)
        if not ok:
            time.sleep(2)
            continue
        menu = wait_menu(25 if attempt == 0 else 12)
        if menu is not None:
            return menu
    return None


RP_WP_TAB = (196, 72, 184)  # act tabs of the waypoint panel: x of act I, step, y (act I measured; II-V from the panel's tab strip)
RP_WP_ROW = (222, 51.3)  # the waypoint panel's first row (y) and row pitch (HD); the panel opens on the current act's tab
RP_ACT_TOWN = {1: 1, 2: 40, 3: 75, 4: 103, 5: 109}


def rp_waypoints():
    """{level: (act, waypoint number, row in the act's tab)} from levels.txt (Waypoint column; Pandemonium 2 shares the Valley's 17)."""
    out, by_act = {}, {}
    for i, r in enumerate(table("levels")):
        w = r.get("Waypoint", "")
        if w in ("", "255") or i == 134 or not w.isdigit():
            continue
        act = int(r.get("Act", "0") or 0) + 1
        by_act.setdefault(act, []).append((int(w), i))
    for act, rows in by_act.items():
        for k, (w, lvl) in enumerate(sorted(rows)):
            out[lvl] = (act, w, k)
    return out


def rp_screen_xy(x, y, p=None):
    """A map position on the 1600 x 900 HD client (no panel open: the player stands at 800, 405; click_unit's projection)."""
    p = p or hstate()["player"]
    dx, dy = x - p.get("x", 0), y - p.get("y", 0)
    return (800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5) / 900


RP_SAFE = (120, 90, 1480, 680)  # the part of the 1600 x 900 HD client a click may go to (no HUD, orbs or belt)


def rp_click_toward(x, y, done, tries=14, step_px=260):
    """Walk as a player does, with left clicks: while the map point is off the safe part of the screen, click toward it (at most
    `step_px` from the character); once it is on screen, click it (an object or NPC there is operated / talked to: D2R walks
    up first). `done()` ends it. Returns done()."""
    for _ in range(tries):
        if done():
            return True
        p = hstate()["player"]
        fx, fy = rp_screen_xy(x, y, p)
        px, py = fx * 1600, fy * 900
        if not (RP_SAFE[0] <= px <= RP_SAFE[2] and RP_SAFE[1] <= py <= RP_SAFE[3]):
            vx, vy = px - 800, py - 405
            k = step_px / max(1.0, (vx * vx + vy * vy) ** 0.5)
            px, py = 800 + vx * k, 405 + vy * k
            px, py = min(max(px, RP_SAFE[0]), RP_SAFE[2]), min(max(py, RP_SAFE[1]), RP_SAFE[3])
        g.click(px / 1600, py / 900)
        time.sleep(1.6)
    return done()


def rp_object_xy(oid):
    """Position of an object (`h objects`: every object of the game, `state` lists only the near ones)."""
    _ok, lines = H("objects")
    for ln in lines:
        m = re.match(r"object id=%d class=\d+ mode=\d+ dist=\d+ at (\d+),(\d+)" % oid, ln)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def rp_waypoint_to(level, log):
    """Travel as a player does. Inside the act: walk to the area's waypoint (`moveto`), click it (the panel opens), click the
    destination's row. Another act: the town's NPC travel first (`level <town>`: D2R shows only the acts the character's quests
    opened in the panel). Returns the area reached."""
    wps = rp_waypoints()
    st = hstate()
    here = st["player"].get("area")
    if here == level:
        return level
    if level not in wps:
        return goto(level)["player"].get("area")
    act = wps[level][0]
    if here not in wps or wps[here][0] != act:
        if here != RP_ACT_TOWN[act]:
            goto(RP_ACT_TOWN[act])
        if level == RP_ACT_TOWN[act]:
            return hstate()["player"].get("area")
    for attempt in range(3):
        close_right_panel()
        wp = find_waypoint_object()
        if wp is None:
            log.append("no waypoint object near in area %s" % hstate()["player"].get("area"))
            break
        xy = rp_object_xy(wp[0])  # (`moveto <id>` would take a monster of the same id: ids are per unit type)
        if xy is None:
            continue
        rp_click_toward(xy[0], xy[1], trade_panel_open)  # walks up and clicks the waypoint: its panel opens
        time.sleep(0.5)
        if not trade_panel_open():
            log.append("the waypoint panel did not open (attempt %d)" % (attempt + 1))
            continue
        act_, _w, row = wps[level]
        if act_ > 1:  # the act's tab (the panel opens on act I's; packet 0x49 alone moves nobody)
            g.click((RP_WP_TAB[0] + RP_WP_TAB[1] * (act_ - 1)) / 1600, RP_WP_TAB[2] / 900)
            time.sleep(0.8)
        g.click(295 / 1600, (RP_WP_ROW[0] + RP_WP_ROW[1] * row) / 900)  # the destination's row
        for _ in range(10):
            time.sleep(2)
            a = hstate()["player"].get("area")
            if a == level:
                return a
        log.append("the waypoint row did not move the character to %d" % level)
        g.key("esc")
    a = hstate()["player"].get("area")
    if a != level:
        log.append("WAYPOINT FALLBACK: `level %d` (town / waypoint warp) instead of the panel" % level)
        a = goto(level)["player"].get("area")
    return a


def rp_vendor_round(npc, nm, log, shots, talk=None):
    """Talk (0x2f; `talk(npc, log)` instead when given: lane vendors3's click route and click talk), Trade, buy one item by right
    click on the panel, sell it back by click (lift, drop on the panel), and, at a gamble vendor, gamble one item by right click.
    Returns (problems, notes)."""
    talk = talk or rp_npc_menu
    bad, notes = [], []
    H("packclear")
    menu = talk(npc, log)
    if menu is None:
        return ["%s: no menu" % nm], notes
    line = rp_menu_line(menu, RP_TRADE)
    if line is None:
        close_menu()
        return [], ["%s: no Trade line (%s)" % (nm, "; ".join(menu[1:4]))]
    for attempt in range(2):  # Jamella's line returned 1 but no panel within 9 s (round 1): wait longer, then talk again once
        Hl("menu %d" % line, log)
        opened = False
        for _ in range(12):
            time.sleep(1.5)
            if trade_panel_open():
                opened = True
                break
        if opened:
            break
        shots.append(sh("rp_notrade_%s_%d" % (nm.lower(), attempt)))
        rp_close_trade()
        menu = talk(npc, log) if attempt == 0 else None
        if menu is None or rp_menu_line(menu, RP_TRADE) is None:
            break
        line = rp_menu_line(menu, RP_TRADE)
    if not trade_panel_open():
        bad.append("%s: the trade panel did not open" % nm)
        rp_close_trade()
        return bad, notes
    _ok, stock_l = Hl("shop %d" % npc, log)
    stock = [kv(l) for l in stock_l if l.startswith("item ")]
    shots.append(sh("rp_shop_%s" % nm.lower()))
    H("gold set 900000 0")
    bought = None
    for s in stock:
        page, x, y = int(s["page"]), int(s["x"]), int(s["y"])
        if page >= len(RP_SHOP_TABS):
            continue
        g.click(RP_SHOP_TABS[page][0] / 1600, RP_SHOP_TABS[page][1] / 900)
        time.sleep(0.8)
        if not trade_panel_open():  # no tab there (Akara has no armour tab): the click closed the panel
            notes.append("%s: tab %d closed the panel" % (nm, page))
            menu = talk(npc, log)
            if menu is None or rp_menu_line(menu, RP_TRADE) is None:
                break
            Hl("menu %d" % rp_menu_line(menu, RP_TRADE), log)
            time.sleep(2.0)
            continue
        gold0 = first(H("gold get")[1], r"carried=(\d+)")
        ids0 = {i.get("id") for i in rp_items_now()}
        g.click(*rp_inv_xy(x, y, RP_SHOP), button="right")
        time.sleep(1.5)
        gold1 = first(H("gold get")[1], r"carried=(\d+)")
        it = rp_item_line(int(s["id"]))
        if it is None or it.get("page") != 0:  # endless stock (potions, keys, scrolls): the bought copy has a new id
            it = next((i for i in rp_items_now() if i.get("id") not in ids0 and i.get("page") == 0), None)
        if gold1 is not None and gold0 is not None and gold1 < gold0 and it is not None:
            bought = (it, gold0 - gold1, s["code"])
            break
        if not game_alive():
            return ["%s: the game died buying %s" % (nm, s["code"])], notes
    if bought is None:
        bad.append("%s: the right click bought nothing (%d stock items)" % (nm, len(stock)))
    else:
        it, price, code = bought
        notes.append("%s: bought %s for %d" % (nm, code, price))
        gold0 = first(H("gold get")[1], r"carried=(\d+)")
        qty = first(H("istat %d 70" % it["id"])[1], r"= (-?\d+)")  # the stack's quantity (keys, arrows)
        g.click(*rp_inv_xy(it["x"], it["y"]))  # lift it ...
        time.sleep(0.8)
        lifted = held_item()
        g.click(340 / 1600, 400 / 900)  # ... and drop it on the vendor's panel: sold
        time.sleep(1.5)
        gold1 = first(H("gold get")[1], r"carried=(\d+)")
        if rp_item_line(it["id"]) is None and not held_item() and gold1 is not None and gold0 is not None and gold1 > gold0:
            notes.append("sold back for %d" % (gold1 - gold0))
        else:
            left = rp_item_line(it["id"])
            bad.append("%s: selling %s back failed (quantity %s, lifted %s, gold %s -> %s, cursor %s, item %s)" % (
                nm, code, qty, lifted, gold0, gold1, held_item(), "page %s at %s,%s" % (left.get("page"), left.get("x"), left.get("y"))
                if left else "gone"))
            release_held_item()
    rp_close_trade()
    gline = rp_menu_line(menu, RP_GAMBLE)
    if gline is not None:
        talk(npc, log)
        Hl("menu %d" % gline, log)
        time.sleep(2.5)
        _ok, offers_l = Hl("gamble", log)
        offers = [kv(l) for l in offers_l if l.startswith("item ")]
        shots.append(sh("rp_gamble_%s" % nm.lower()))
        got = None
        for o in offers[:6]:
            gold0 = first(H("gold get")[1], r"carried=(\d+)")
            g.click(*rp_inv_xy(int(o["x"]), int(o["y"]), RP_SHOP), button="right")
            time.sleep(2.0)
            gold1 = first(H("gold get")[1], r"carried=(\d+)")
            if gold0 is not None and gold1 is not None and gold1 < gold0:
                got = (o["code"], gold0 - gold1)
                break
        if got:
            notes.append("gambled %s for %d" % got)
        else:
            bad.append("%s: %d gamble offers, the right click gambled none" % (nm, len(offers)))
        rp_close_trade()
    return bad, notes


def check_rp_vendors():
    """Player path (b): in every act's town (reached by the town waypoint, 0x13 + 0x49), every vendor: talk, Trade, buy by right
    click, sell back, gamble where offered. Median XL 2012 items do not lose durability (no Repair line expected; a Trade/Repair
    line is noted). Set-up: `gold set`, the town waypoint bits."""
    mark = engine_mark()
    log, shots, rows, bad = [], [], [], []
    rp_be("barbarian")
    for n in RP_TOWN_WP.values():
        H("waypoint n %d set" % n)
    towns = [int(t) for t in (os.environ.get("MXL_RP_TOWNS") or "").split(",") if t]
    for town, vendors in RP_VENDORS.items():
        if towns and town not in towns:
            continue
        area = rp_waypoint_to(town, log)
        if area != town:
            bad.append("could not reach town %d (area %s)" % (town, area))
            continue
        for npc, nm in vendors:
            try:
                b, notes = rp_vendor_round(npc, nm, log, shots)
            except Exception as e:
                b, notes = ["%s: script %r" % (nm, e)], []
            bad += b
            rows.append("%d %s: %s%s" % (town, nm, "; ".join(notes), (" | " + "; ".join(b)) if b else ""))
            if not game_alive():
                bad.append("the game died at %s" % nm)
                rp_recover(nm, log)
                rp_be("barbarian")
                break
    rp_waypoint_to(1, log)
    finish("rp_vendors", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots[:30], rows + log[-300:])


# --- (c) a real death ---------------------------------------------------------------------------------------------------------
# Screen offsets (HD client, the character at 800, 405) of the clicks that look for the body after a reload: the game lays it
# next to the character at the arrival spot; our `state` lists no player units, so the clicks go round the character, nearest first
RP_CORPSE_OFFSETS = [(dx, dy) for r in (30, 55, 80, 110) for dx, dy in ((r, 0), (-r, 0), (0, r // 2), (0, -r // 2), (r, r // 2),
                                                                          (-r, r // 2), (r, -r // 2), (-r, -r // 2))]


def rp_worn():
    return sorted("%s@%s" % (it.get("code"), it.get("x")) for it in rp_items_now() if it.get("page") == 255)


def rp_corpse_pickup(worn0):
    """Left clicks round the character until the worn gear is back (a click on the body takes it all back). The character may
    walk on a click that misses: it is put back on its arrival spot with a walk (`move`) after each miss. (clicks, worn after)."""
    p0 = hstate()["player"]
    x0, y0 = p0.get("x", 0), p0.get("y", 0)
    n = 0
    for dx, dy in RP_CORPSE_OFFSETS:
        n += 1
        g.click((800 + dx) / 1600, (405 + dy) / 900)
        time.sleep(1.5)
        worn = rp_worn()
        if worn == worn0:
            return n, worn
        p = hstate()["player"]
        if abs(p.get("x", 0) - x0) + abs(p.get("y", 0) - y0) > 1:
            H("move %d %d" % (x0, y0))
            time.sleep(1.5)
    return n, rp_worn()


def check_rp_death():
    """Player path (c): a level-1 character walks into natural monsters (Blood Moor / Cold Plains, no harness spawn), takes their
    damage until it dies, respawns with Esc, then Save and Exit + reload (D2R gives the body back at the load) and the gear is
    on it again. No god mode, no life set."""
    mark = engine_mark()
    log, shots, rows, bad = [], [], [], []
    name, cid = "RpDie", 1
    g.CHAR_NAME = name
    if not switch_character(name, "sorceress", cid):
        return finish("rp_death", False, "could not play the death test character", mark, [], log)
    worn0 = sorted("%s@%s" % (it.get("code"), it.get("x")) for it in rp_items_now() if it.get("page") == 255)
    for wp in (1, 2, 3, 4):  # natural packs of the act 1 wilderness, by waypoint where the character has them
        H("waypoint n %d set" % wp)
    died = False
    for area in (3, 4, 5, 6):  # Cold Plains, Stony Field, Dark Wood, Black Marsh: denser than the Blood Moor
        if rp_waypoint_to(area, log) != area:
            continue
        t0 = time.time()
        while time.time() - t0 < 120:
            st = hstate()
            p = st["player"]
            if player_dead(p):
                died = True
                break
            mons = [m for m in st["mons"] if m.get("mode") not in (0, 12) and m.get("life", 1) > 0]
            if mons:
                m = min(mons, key=lambda m: m.get("dist", 99))
                H("move %d %d" % (m["mx"], m["my"]))  # into the pack: they hit back
            else:
                H("move %d %d" % (p.get("x", 0) + 25, p.get("y", 0) + 15))
            time.sleep(2.5)
        rows.append("area %d: %s after %.0f s" % (area, "died" if died else "alive", time.time() - t0))
        if died:
            break
    shots.append(sh("rp_death"))
    if not died:
        bad.append("the character did not die within the time (natural monsters too weak or not found)")
    else:
        alive = game_alive()
        rows.append("death: game %s, last log line %s" % ("alive" if alive else "GONE", (g._read_from(g.MXL_LOG, mark["mxl"]) or "").strip().splitlines()[-1:]))
        if not alive:
            bad.append("the game died at the player's death")
        else:
            revive_if_dead(40)
            time.sleep(3)
            p = hstate()["player"]
            rows.append("after Esc: area %s mode %s life %s" % (p.get("area"), p.get("mode"), p.get("life")))
            shots.append(sh("rp_respawn"))
            if player_dead(p):
                bad.append("no respawn")
            worn1 = sorted("%s@%s" % (it.get("code"), it.get("x")) for it in rp_items_now() if it.get("page") == 255)
            rows.append("worn before %s, after respawn %s (the body keeps them)" % (worn0, worn1))
            leave_and_reenter()
            time.sleep(3)
            worn2 = sorted("%s@%s" % (it.get("code"), it.get("x")) for it in rp_items_now() if it.get("page") == 255)
            rows.append("after Save and Exit + reload: worn %s" % worn2)
            shots.append(sh("rp_death_reload"))
            if worn2 != worn0:  # the gear lies on the body (a player unit, not a ground item): click it, as a player does
                clicks, worn3 = rp_corpse_pickup(worn0)
                rows.append("after the reload the gear is on the body; corpse clicks %d, worn now %s" % (clicks, worn3))
                shots.append(sh("rp_death_corpse"))
                if worn3 != worn0:
                    _ok, gl = H("ground")
                    rows.append("ground near: %s" % gl[-3:])
                    bad.append("the gear did not come back from the body (%s vs %s)" % (worn3, worn0))
    g.CHAR_NAME = RP_CHARS["barbarian"][0]
    finish("rp_death", died and not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-200:])


# --- (d) real areas, natural packs, bosses -----------------------------------------------------------------------------------
RP_AREAS = [  # (act, level, how, boss classes (monstats Id) that must come into view, label)
    (1, 2, "walk", (), "Blood Moor"),
    (1, 8, "warp", ("corpsefire",), "Den of Evil (Corpsefire)"),
    (1, 17, "warp", ("bloodraven",), "Burial Grounds (Blood Raven)"),
    (1, 37, "warp", ("andariel",), "Catacombs 4 (Andariel)"),
    (2, 73, "warp", ("duriel",), "Duriel's Lair (Duriel)"),
    (3, 102, "warp", ("mephisto",), "Durance of Hate 3 (Mephisto)"),
    (4, 108, "warp", ("diablo",), "Chaos Sanctum (Diablo: comes only after the seals, noted)"),
    (5, 110, "walk", (), "Bloody Foothills"),
    (5, 124, "warp", ("nihlathakboss",), "Halls of Vaught (Nihlathak)"),
]


def rp_acts():
    """The acts MXL_RP_ACTS names (e.g. `1` or `2,3`; all five when unset): one rp_areas run per act fits a slot lock."""
    want = [int(a) for a in (os.environ.get("MXL_RP_ACTS") or "").split(",") if a.strip().isdigit()]
    return [a for a in (1, 2, 3, 4, 5) if not want or a in want]


def rp_class_ids(names):
    ids = set()
    for i, r in enumerate(table("monstats")):
        if r.get("Id") in names or r.get("BaseId") in names:
            ids.add(i)
    for r in _rp_rows("superuniques"):
        if (r.get("Superunique") or "").lower().replace(" ", "") in names or (r.get("Name") or "").lower() in names:
            cls = r.get("Class")
            ids |= {i for i, m in enumerate(table("monstats")) if m.get("Id") == cls}
    return ids


def rp_fight(area, seconds, want, log, rows):
    """Walk the area and fight what comes: the nearest live monster is attacked with real left clicks (the character's own attack
    skill) until it dies or the time is up; with nothing near, walk on in a widening square. Returns (kills, seen boss ids, alive)."""
    # the left button must hold Attack (skill 0), as a player selects it: RpBarb's save came back with Throw (2), and a left click
    # with Throw and a non-throwing axe does nothing (act 1, run checks-20261029-015018-s3: 0 kills in 4 areas)
    Hl("skill left 0", log)
    t0 = time.time()
    kills, seen, step, leg = 0, set(), 0, 0
    pids = sorted(g.game_pids())
    known_dead = set()
    while time.time() - t0 < seconds:
        if not g.game_pids() or sorted(g.game_pids()) != pids:
            return kills, seen, False
        st = hstate()
        if not st["ok"]:
            return kills, seen, False
        p = st["player"]
        if player_dead(p):
            rows.append("area %d: the character died (natural damage) after %.0f s" % (area, time.time() - t0))
            revive_if_dead(40)
            return kills, seen, game_alive()
        for c in st["corpses"]:
            if c.get("id") not in known_dead:
                known_dead.add(c.get("id"))
                kills += 1
        live = [m for m in st["mons"] if m.get("mode") not in (0, 12) and m.get("life", 1) > 0 and m.get("dist", 99) < 30]
        seen |= {m.get("class") for m in live if m.get("class") in want}
        if live:
            m = min(live, key=lambda m: m.get("dist", 99))
            if m.get("dist", 99) > 3:
                H("move %d %d" % (m["mx"], m["my"]))
                time.sleep(0.8)
            click_unit(m["id"])
            time.sleep(0.7)
        else:
            dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[leg % 4]
            step += 1
            length = 12 * (1 + leg // 2)
            H("move %d %d" % (p.get("x", 0) + dx * length, p.get("y", 0) + dy * length))
            leg += 1
            time.sleep(2.0)
    return kills, seen, True


# quest words that open the waypoint panel's tab of an act (D2R draws only the acts the character's quests opened): 7, 15, 23 =
# acts I-III completed opened tabs II-IV (wptabs, 2026-10-28); 28 alone did not open V, Diablo's quest (26) with it did (2026-10-29)
RP_ACT_OPEN = {2: (7,), 3: (15,), 4: (23,), 5: (26, 28)}


def quest_done(save, word, difficulty=0):
    """Bit 0 (done) of a quest word in a save; False for a new character's save, which has no quest section until its first
    Save and Exit (the closed edit saves first, then finds it; run checks-20261029-224054-s2)."""
    try:
        return bool(rc_setup.get_quest(save, difficulty, word) & 1)
    except ValueError:
        return False


def rp_open_acts(acts, log):
    """SET-UP by save (rc_setup, coordinator rule "PLAYER PATH vs SET-UP"): the act-completed quest words of Normal for the acts
    before the highest one asked for, so the waypoint panel has those acts' tabs (round 1: only tab I was drawn, the row click
    landed in act I's list). Done once per character (the words stay in its save). Returns the words set ([] = none needed)."""
    need = [w for a in range(2, max(acts) + 1) for w in RP_ACT_OPEN[a]]
    path = os.path.join(SAVES, g.CHAR_NAME + ".d2s")
    if not need or not os.path.isfile(path):
        return []
    with open(path, "rb") as f:
        save = f.read()
    missing = [w for w in need if not quest_done(save, w)]
    if not missing:
        return []

    def edit(s):
        for w in missing:
            s = rc_setup.set_quest_bits(s, 0, w, rc_setup.DONE)
        return s
    rc2_closed_edit(edit, log)
    return missing


def check_rp_areas():
    """Player path (d): every act's waypoint used (0x13 + 0x49, normal difficulty; set-up: the waypoint bits), then the areas of
    RP_AREAS walked with the natural monsters fought by real left clicks (no harness kill, no spawn): Corpsefire, Blood Raven,
    Andariel and Mephisto must come into view and the game must stay up. Kills of the bosses are reported (a natural level-85
    Barbarian with the starting axe may not kill an act boss in the time: noted, not a FAIL)."""
    mark = engine_mark()
    log, shots, rows, bad = [], [], [], []
    rp_be("barbarian")
    acts = rp_acts()
    opened = rp_open_acts(acts, log)
    rows.append("acts %s%s" % (acts, "; SET-UP: quest words %s (acts completed) set in the save" % opened if opened else ""))
    wps = rp_waypoints()
    waypoints = sorted((w, lvl) for lvl, (a, w, _k) in wps.items() if a in acts)
    for n, _lvl in waypoints:
        H("waypoint n %d set" % n)
    reached = []
    for n, lvl in waypoints:
        a = rp_waypoint_to(lvl, log)
        reached.append((lvl, a == lvl))
        if not game_alive():
            bad.append("the game died taking the waypoint to %d" % lvl)
            rp_recover("waypoint %d" % lvl, log)
            rp_be("barbarian")
    rows.append("waypoints: %d of %d reached (%s); by the panel %d, fallback warps %d" % (
        sum(1 for _l, ok in reached if ok), len(reached), ",".join(str(l) for l, ok in reached if not ok) or "all",
        len(reached) - sum(1 for ln in log if ln.startswith("WAYPOINT FALLBACK")), sum(1 for ln in log if ln.startswith("WAYPOINT FALLBACK"))))
    shots.append(sh("rp_waypoints_end"))
    for act, lvl, how, bosses, label in RP_AREAS:
        if act not in acts:
            continue
        rp_waypoint_to(RP_ACT_TOWN[act], log)
        if how == "walk":
            goto(lvl)
        else:
            Hl("level %d warp" % lvl, log)
            time.sleep(6)
        if hstate()["player"].get("area") != lvl:
            rows.append("%s: not reached" % label)
            continue
        want = rp_class_ids(set(bosses))
        kills, seen, alive = rp_fight(lvl, int(os.environ.get("MXL_RP_AREA_SECS") or 240), want, log, rows)
        shots.append(sh("rp_area_%d" % lvl))
        rows.append("%s: %d kills, bosses seen %s of %s, game %s" % (label, kills, sorted(seen), sorted(want), "up" if alive else "GONE"))
        if not alive:
            bad.append("the game died in %s" % label)
            rp_recover(label, log)
            rp_be("barbarian")
        elif want and not seen:
            rows.append("%s: the boss did not come into view in the time (not a FAIL)" % label)
    rp_waypoint_to(1, log)
    finish("rp_areas", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-300:])


# --- (e) Save and Exit, reload, items kept -------------------------------------------------------------------------------------
def rp_inventory_sig():
    return sorted("%s@%s:%s,%s" % (it.get("code"), it.get("page"), it.get("x"), it.get("y")) for it in rp_items_now())


def check_rp_persist():
    """Player path (e): each lane character (RP_CHARS present in the slot) picks a few items up from the ground, wears one, then
    Save and Exit + reload: the backpack and the worn items are the same."""
    mark = engine_mark()
    log, rows, bad, shots = [], [], [], []
    have = {os.path.splitext(os.path.basename(p))[0] for p in __import__("glob").glob(os.path.join(SAVES, "*.d2s"))}
    for cls, (name, cid) in RP_CHARS.items():
        if name not in have:
            continue
        if not rp_be(cls):
            bad.append("%s: could not play %s" % (cls, name))
            continue
        for args in ("rin", "amu", "gcv"):
            iid = rp_ground_item(args, log)
            if iid is not None:
                rp_pickup(iid, log, to_inv=True)
        time.sleep(1)
        release_held_item()
        before = rp_inventory_sig()
        leave_and_reenter()
        time.sleep(3)
        after = rp_inventory_sig()
        shots.append(sh("rp_persist_%s" % cls))
        rows.append("%s: %d items before, %d after%s" % (name, len(before), len(after), "" if before == after else
                                                          " DIFF -%s +%s" % (sorted(set(before) - set(after))[:5], sorted(set(after) - set(before))[:5])))
        if before != after:
            bad.append("%s: items changed across Save and Exit" % name)
    finish("rp_persist", not bad and bool(rows), "; ".join(rows) or "no lane character in the slot (run rp_items first)", mark, shots, rows + log[-100:])


# --- (f) sockets, cube, potions, scrolls, tomes ------------------------------------------------------------------------------
RP_RECIPES = [169, 173, 28]  # cubemain rows: 2 Chipped Amethysts -> Flawed, 2 Chipped Rubies -> Flawed, Median's summoning scroll


def rp_cube_open():
    box = next((it for it in rp_items_now() if it.get("code") == "box" and it.get("page") == 0), None)
    if box is None:
        return False
    if not right_panel_open():
        g.press("i")
        time.sleep(1.0)
    g.click(*rp_inv_xy(box["x"], box["y"]), button="right")
    time.sleep(1.5)
    return True


def rp_packclear(log):
    """`packclear` (set-up: room in the backpack) only with every panel closed (rp_use 2026-10-28: the harness stopped answering
    after a packclear right behind the cube panel's Esc); the inventory panel is opened again afterwards."""
    close_right_panel()
    time.sleep(0.5)
    Hl("packclear", log)
    if not game_alive():
        rp_recover("packclear", log)
        rp_be("barbarian")
    if not right_panel_open():
        g.press("i")
        time.sleep(1.0)


def check_rp_use():
    """Player path (f): runes and gems socketed by a click (picked up from the ground onto the cursor, clicked onto a socketed item in
    the backpack), cube recipes (inputs picked up from the ground into the cube with 0x16 + 0x18 page 3, the Transmute button
    clicked), potions / elixirs drunk and scrolls / tomes read by right click in the backpack."""
    mark = engine_mark()
    log, rows, bad, shots = [], [], [], []
    rp_be("barbarian")
    H("packclear")
    if not right_panel_open():
        g.press("i")
        time.sleep(1.0)
    # sockets: a 3-socket body armour in the backpack, then a rune, a gem and a jewel clicked onto it
    target = None
    for _ in range(10):
        iid = rp_ground_item("%s normal 194=3" % "fld", log)
        if iid and rp_pickup(iid, log):
            Hl("pkt 18 " + _le(iid, 0, 3, 0), log)
            time.sleep(0.6)
            target = rp_item_line(iid)
            break
    if target is None:
        bad.append("no socketed armour in the backpack")
    else:
        for filler in ("r01", "gcv", "jew"):
            fid = rp_ground_item(filler, log)
            if fid is None or not rp_pickup(fid, log):
                bad.append("socket: no %s on the cursor" % filler)
                continue
            g.click(*rp_inv_xy(target["x"], target["y"]))
            time.sleep(1.2)
            ok = held_item() is None and rp_item_line(fid) is None
            rows.append("socket %s into fld: %s" % (filler, "in" if ok else "NOT (cursor %s)" % (held_item(),)))
            if not ok:
                bad.append("socketing %s failed" % filler)
                release_held_item()
            if not game_alive():
                bad.append("the game died socketing %s" % filler)
                return finish("rp_use", False, "; ".join(rows + bad), mark, shots, log)
        hover(*rp_inv_xy(target["x"], target["y"]))
        shots.append(sh("rp_socketed_tip"))
        Hl("remove id %d" % target["id"], log)
    # cube recipes: lane cube's flow (inputs dropped, picked up, clicked into the cube; the panel opened once and kept open:
    # closing and reopening it per recipe lost clicks, and the backpack is cleared only with every panel closed)
    cm = table("cubemain")
    rp_packclear(log)
    if not _cube_panel_open(log):
        bad.append("no cube")
    else:
        for row in RP_RECIPES:
            r = cm[row]
            ins = [x for x in (r.get("input %d" % k, "") for k in range(1, 8)) if x]
            _cube_clear(log)  # an earlier recipe's output: the cube must hold only this recipe's inputs
            cell, missing = 0, []
            for spec in ins:
                code = spec.split(",")[0]
                qty = int((re.search(r"qty=(\d+)", spec) or [None, "1"])[1])
                for _ in range(qty):
                    if _cube_put(code, cell, log) is None:
                        missing.append(code)
                    else:
                        cell += 1
            if missing:
                bad.append("recipe %d: %s did not reach the cube" % (row, missing))
            g.click(RP_TRANSMUTE[0] / 1600, RP_TRANSMUTE[1] / 900)
            time.sleep(2.0)
            shots.append(sh("rp_cube_%d" % row))
            cube = [it.get("code") for it in _cube_now(log)]
            out = r.get("output", "").split(",")[0].strip('"')
            if out.startswith("mxl2012:"):  # a unique (or set) item named by its index: the base code is what the cube holds
                out = _unique_code(out[len("mxl2012:"):]) or out
            rows.append("recipe %d (%s): cube after Transmute %s, output %s" % (row, r.get("description", "")[:40], cube, out))
            if not game_alive():
                bad.append("the game died at recipe %d" % row)
                rp_recover("recipe %d" % row, log)
                break
            if not missing and out and out not in cube and not out.startswith(("useitem", "usetype")):
                bad.append("recipe %d: no %s in the cube after Transmute" % (row, out))
        _cube_clear(log)
        _cube_panel_close()
    # potions, elixirs, scrolls, tomes: right click in the backpack
    if not right_panel_open():
        g.press("i")
        time.sleep(1.0)
    uses = [r["code"] for r in table("misc") if r.get("type") in ("hpot", "mpot", "rpot", "elix", "scro", "book", "spot", "apot", "wpot") and r.get("spawnable") == "1"]
    seen_types = set()
    for code in uses:
        t = row_of("misc", "code", code).get("type")
        if t in seen_types and t not in ("elix",):
            continue
        seen_types.add(t)
        rp_packclear(log)
        iid = rp_ground_item(code, log)
        if iid is None or not rp_pickup(iid, log):
            bad.append("use: no %s" % code)
            continue
        if held_item():
            Hl("pkt 18 " + _le(iid, 2, 0, 0), log)
            time.sleep(0.5)
        it = rp_item_line(iid)
        if it is None:
            bad.append("use: %s not in the backpack" % code)
            continue
        g.click(*rp_inv_xy(it["x"], it["y"]), button="right")
        time.sleep(1.5)
        gone = rp_item_line(iid) is None
        rows.append("use %s (%s): %s" % (code, t, "used" if gone else "still there" + (" (a Town Portal does not open in town)"
                                                                                  if t in ("scro", "book") else "")))
        if not gone and t not in ("scro", "book"):
            bad.append("use: %s stayed in the backpack" % code)
        if not game_alive():
            bad.append("the game died using %s" % code)
            break
        g.key("esc")  # a town portal / identify cursor / waypoint panel the use opened
        time.sleep(0.5)
        if not right_panel_open():
            g.press("i")
            time.sleep(1.0)
    shots.append(sh("rp_use_end"))
    close_right_panel()
    finish("rp_use", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-300:])


CHECKS = [("mxl2012", check_mxl2012), ("cltdostub", check_cltdostub), ("rockshock", check_rockshock), ("cltdo83", check_cltdo83),
          ("srvhit23", check_srvhit23), ("frenzy", check_frenzy), ("cltnomis", check_cltnomis), ("srvhit6spawn", check_srvhit6spawn),
          ("terrorzones", check_terrorzones), ("pandewp", check_pandewp), ("skillprog", check_skillprog), ("classes", check_classes),
          ("textnames", check_textnames), ("melttrail", check_melttrail), ("elixirs", check_elixirs),
          ("meltmon", check_meltmon), ("uniquecarry", check_uniquecarry), ("whirlwind", check_whirlwind),
          ("cubeclasses", check_cubeclasses)]
# lane rulescheck: the character rules (rc*) and the item real-path checks RP1-RP6 (rp*) on the player path
CHECKS += [("rcbook", check_rcbook), ("rcdelay", check_rcdelay), ("rctoken", check_rctoken), ("rclife", check_rclife),
           ("rcscroll", check_rcscroll), ("rchire", check_rchire), ("rcdeath", check_rcdeath), ("rclevels", check_rclevels),
           ("rprunes", check_rprunes), ("rpdarkring", check_rpdarkring), ("rpcharm", check_rpcharm), ("rpnames", check_rpnames),
           ("rpequip", check_rpequip)]
CHECKS += [("runeletters", check_runeletters)]  # lane runeletters: bug #334
CHECKS += [("rpsignets", check_rpsignets)]  # lane phase3: engine-triage #24, signets (pSpell 3) and the Apple (pSpell 10)
CHECKS += [("apple_use", check_apple_use)]  # lane apple: bug #499, the Apple bought, used, Save and Exit
CHECKS += [("acts", check_acts)]
# lane rulescheck2: the same rules with a SET-UP character (rc2setup first: it edits the save)
CHECKS += [("rc2setup", check_rc2setup), ("rc2quest", check_rc2quest), ("rc2refund", check_rc2refund), ("rc2delay", check_rc2delay),
           ("rc2death", check_rc2death)]


def check_playthrough():
    """Lane playtest: the player path per classic class (tools/playthrough.py): a fresh Normal character kills monsters with its own
    skill, picks up a real drop, wears it, trades with a vendor, uses a waypoint, cubes a recipe, saves and reloads, dies once.
    MXL_PT_CLASSES=0,4 runs a subset (class numbers of `h state`)."""
    import playthrough
    playthrough.run(sys.modules[__name__])


CHECKS += [("playthrough", check_playthrough)]

# lane realpath: the player-path checks (docs/testing.md "Player-path checks")
CHECKS += [("rp_items", check_rp_items), ("rp_vendors", check_rp_vendors), ("rp_death", check_rp_death), ("rp_areas", check_rp_areas),
           ("rp_persist", check_rp_persist), ("rp_use", check_rp_use)]



# --- lane identify (bug #485): Scroll / Tome of Identify on the player path ---------------------------------------------------
ID_LEGACY_CELL = (829, 406, 43.4, 43.3)  # legacy (classic) backpack grid at 1600 x 900: left, top, cell w, cell h (hdit_inv_legacy.png)


def id_px(x, y, gfx):
    if gfx != "legacy":
        return inv_px(x, y)
    left, top, cw, ch = ID_LEGACY_CELL
    return left + (x + 0.5) * cw, top + (y + 0.5) * ch


def id_item(iid, log):
    return next((i for i in rc_items(log) if i["id"] == iid), None)


def id_round(src, target, gfx, log, shots, tag):
    """Right click the identify item `src` (item dict) in the open inventory, then a left click on the unidentified `target`: the
    player path of 1.13c / D2R. Returns (identified after, source item after or None, charges before, charges after)."""
    tome = src["code"] == "ibk"
    qty0 = first(H("istat %d 70" % src["id"])[1], r"= (-?\d+)") if tome else None
    if gfx != "legacy":  # legacy: right_panel_open() reads the HD panel only, check_identify opens / closes it once
        rc_open_inventory()
    px, py = id_px(src["x"], src["y"], gfx)
    hover_px(px, py)
    g.click(px / 1600, py / 900, button="right")
    time.sleep(1.0)
    tx, ty = id_px(target["x"], target["y"], gfx)
    hover_px(tx, ty)  # the cursor over the target: the identify cursor (or the hand) shows in the shot
    time.sleep(0.5)
    shots.append(sh("%s_cursor" % tag))
    _ok, cur = Hl("cursor", log)
    g.click(tx / 1600, ty / 900)
    time.sleep(1.5)
    hover_px(tx, ty)
    time.sleep(0.5)
    shots.append(sh("%s_after" % tag))
    _ok, cur2 = Hl("cursor", log)
    after = id_item(target["id"], log)
    src_after = id_item(src["id"], log)
    qty1 = first(H("istat %d 70" % src["id"])[1], r"= (-?\d+)") if (tome and src_after) else None
    log.append("%s: right click %s id %d at %d,%d, left click %s id %d at %d,%d -> identified %s, %s %s, cursor before %s after %s%s" % (
        tag, src["code"], src["id"], src["x"], src["y"], target["code"], target["id"], target["x"], target["y"],
        after.get("identified") if after else "gone", src["code"], "kept" if src_after else "used up", cur[:1], cur2[:1],
        ", charges %s -> %s" % (qty0, qty1) if tome else ""))
    if cur2 and cur2[0].startswith("cursor id="):  # whatever ended on the cursor goes back into the backpack
        fx, fy = id_px(*(free_inv_cell(rc_items(log), 1, 1) or (5, 5)), gfx)
        g.click(fx / 1600, fy / 900)
        time.sleep(1.0)
    if gfx != "legacy":
        close_right_panel()
    return (after or {}).get("identified"), src_after, qty0, qty1


def check_identify():
    """Bug #485 (play test 0.1.0): a Scroll of Identify (`isc`, misc pSpell 1) right clicked in the inventory, then a left click on
    an unidentified magic ring: identified, the scroll used up. Same with a Tome of Identify (`ibk`, 5 charges: one charge less).
    One round of each in HD, then the same in legacy graphics (G). MXL_ID_HD_ONLY=1 skips the legacy rounds.
    SHORTCUT: the scrolls, the tome and the rings are put on the ground by `item ... ground` (stand-ins for drops / a vendor) and
    picked up by clicks (in HD)."""
    mark = engine_mark()
    log, shots, notes, bad = [], [], [], []
    goto(1)
    shortcut = ["scrolls, tome and rings dropped by the harness"]
    modes = ["hd"] if os.environ.get("MXL_ID_HD_ONLY") else ["hd", "legacy"]
    if not set_graphics("hd"):
        bad.append("could not switch to HD graphics")
    if rc_of("ibk", RC_PAGE_INV, log):  # a carried tome takes picked-up scrolls in (D2's rule): use a fresh character
        bad.append("the character already carries a Tome of Identify; run with a new MXL_CHAR")
    plan = []  # (gfx, code, source dict, ring dict)
    scrolls = {gfx: rc_obtain("isc", log, shortcut) for gfx in modes}  # all scrolls before the tome
    tome = rc_obtain("ibk", log, shortcut, "70=5")
    for gfx in modes:
        for code in ("isc", "ibk"):
            ring = rc_obtain("rin", log, shortcut, "magic unid")
            src = tome if code == "ibk" else scrolls[gfx]
            if ring is None or src is None:
                bad.append("%s %s round: set-up items not picked up" % (gfx, code))
                continue
            if ring.get("identified") != 0:
                bad.append("%s %s round: the ring came identified (%s)" % (gfx, code, ring.get("identified")))
                continue
            plan.append((gfx, code, src, ring))
    legacy_open = False
    for gfx, code, src, ring in plan:
        if graphics_mode() != gfx and not set_graphics(gfx):
            bad.append("could not switch to %s graphics" % gfx)
            break
        if gfx == "legacy" and not legacy_open:
            g.press("i")  # the legacy inventory, opened once for the legacy rounds
            time.sleep(1.2)
            legacy_open = True
        src = id_item(src["id"], log) or src  # where it lies now
        ident, src_after, q0, q1 = id_round(src, ring, gfx, log, shots, "id_%s_%s" % (code, gfx))
        if code == "isc":
            ok = ident == 1 and src_after is None
            notes.append("%s scroll: ring identified %s, scroll %s" % (gfx, ident, "used up" if src_after is None else "kept"))
        else:
            ok = ident == 1 and q0 is not None and q1 == q0 - 1
            notes.append("%s tome: ring identified %s, charges %s -> %s" % (gfx, ident, q0, q1))
        if not ok:
            bad.append(notes[-1])
    if legacy_open:
        g.press("i")
        time.sleep(1.0)
    if graphics_mode() != "hd":
        set_graphics("hd")
    note = "; ".join(notes) + ("; PROBLEMS: " + "; ".join(bad) if bad else "")
    rc_finish("identify", not bad, note, mark, shots, log, shortcut)


CHECKS += [("identify", check_identify)]

# --- bug #395: the Heretics' skull swarm load (harness measurement, not a player-path verdict) --------------------------------
SWARM_MONSTER = "cultist2"  # Heretic, monstats MissA1 skullswarmcenter (FetishBlowgun AI)


def game_private_mb():
    """Private bytes of this slot's game process in MB (None when it cannot be read)."""
    class PMC(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [(n, ctypes.c_size_t) for n in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.OpenProcess.restype = wt.HANDLE
    for pid in g.game_pids():
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            continue
        pmc = PMC()
        pmc.cb = ctypes.sizeof(pmc)
        ok = psapi.GetProcessMemoryInfo(wt.HANDLE(h), ctypes.byref(pmc), pmc.cb)
        k32.CloseHandle(wt.HANDLE(h))
        if ok:
            return pmc.PrivateUsage // (1 << 20)
    return None


def check_swarm():
    """Bug #395: MXL_SWARM_N (10) Heretics spawned next to a Tank'd character in the Blood Moor for MXL_SWARM_SECS (180) s;
    every ~5 s the game frame, the newest missile id near the character, the live server missiles, the game's private
    memory and the life lost since the last sample (read before life is set back to full: lane srcdamage, the first
    version read it right after the reset, so it saw well under a second of damage). MXL_SWARM_LIFE (30000) is the
    character's life and maximum; MXL_SWARM_MONSTER (cultist2) another monstats Id to spawn. Harness-only (spawned monsters,
    life kept full): "seen with the harness", not a verification."""
    n, secs = int(os.environ.get("MXL_SWARM_N", "10")), int(os.environ.get("MXL_SWARM_SECS", "180"))
    life = int(os.environ.get("MXL_SWARM_LIFE", "30000"))
    mark, log, samples, lost, deaths = engine_mark(), [], [], [], 0
    het = row_of("monstats", "Id", os.environ.get("MXL_SWARM_MONSTER", SWARM_MONSTER))
    cls = int(het["*hcIdx"])
    skulls = {r["Missile"]: (r["Param1"], r["NextDelay"]) for r in table("missiles") if r["Missile"].startswith("skullswarm")}
    goto(2)
    with Tank():
        px, py = player_xy()
        _, sp = Hl("spawn %d %d %d %d" % (cls, n, px + 6, py), log)
        made = len([ln for ln in sp if "spawned class" in ln])
        t0, fails = time.time(), 0
        setstat("player", 7, life << 8)
        setstat("player", 6, life << 8)
        while time.time() - t0 < secs and fails < 3:
            ok, st = H("state", 20)
            _, ms = H("missiles", 20)
            fails = 0 if ok else fails + 1
            now, mode = first(st, r"life=(\d+)/"), first(st, r" mode=(\d+)")
            if mode in (0, 17):  # death / dead: the life read is not a loss
                deaths += 1
            elif now is not None and samples:
                lost.append(life - now)
            row = (round(time.time() - t0), first(st, r"frame=(\d+)"), first(st, r"mis id=(\d+)"),
                   first(ms, r"missiles live=(\d+)"), game_private_mb(), now, mode)
            samples.append(row)
            log.append("swarm t=%s frame=%s mis_id=%s live=%s private_mb=%s life=%s mode=%s" % row)
            setstat("player", 6, life << 8)
            time.sleep(5)
        shot = sh("swarm")
    rates = []
    for a, b in zip(samples, samples[1:]):
        if None not in (a[1], b[1], a[2], b[2]) and b[1] > a[1] and b[0] > a[0]:
            rates.append(((b[2] - a[2]) / (b[1] - a[1]), (b[1] - a[1]) / (b[0] - a[0])))
    lives = [s[3] for s in samples if s[3] is not None]
    mems = [s[4] for s in samples if s[4] is not None]
    fps = [r[1] for r in rates]
    note = ("%d of %d %s (class %d) for %d s; skull Param1 / impact NextDelay %s / %s; missile ids per frame median %s; "
            "live server missiles median %s, max %s; frames per second median %s, min %s; private MB %s -> %s, max %s" % (
                made, n, het["Id"], cls, samples[-1][0] if samples else 0, skulls.get("skullswarm0", ("?",))[0],
                skulls.get("skullswarmimpact", ("", "?"))[1],
                round(sorted(r[0] for r in rates)[len(rates) // 2]) if rates else None,
                sorted(lives)[len(lives) // 2] if lives else None, max(lives) if lives else None,
                round(sorted(fps)[len(fps) // 2], 1) if fps else None, round(min(fps), 1) if fps else None,
                mems[0] if mems else None, mems[-1] if mems else None, max(mems) if mems else None))
    note += "; life %d, lost per sample median %s, max %s; deaths %d; impact SrcDamage %s" % (
        life, sorted(lost)[len(lost) // 2] if lost else None, max(lost) if lost else None, deaths,
        next((r["SrcDamage"] for r in table("missiles") if r["Missile"] == "skullswarmimpact"), "?"))
    finish("swarm", made > 0 and fails < 3 and bool(rates), note, mark, [shot], log,
           partial="harness load probe (spawned monsters, life kept full): not a player-path verdict")


CHECKS += [("swarm", check_swarm)]  # bug #395

# --- crash-audit rows that need a game look (docs/crash-audit.md C14, C17, C18) -------------------------------------------------
CR_MORPHS = [(448, "Trap Rat Form"), (463, "Treewarden Form")]  # the Druid's transform skills (states trapratstate / tritonstate)
CR_WITCH = [1722, 1740]  # monstats rows with a Median-only Neutral sound (l4dwitchsnd, malewitchsnd), crash-audit C17


def mxl_part(lines, word):
    return next((ln for ln in lines if ln.startswith(word + " ")), "")


def check_crashrows():
    """Crash-audit rows that need the game (lane realpath2). C14 `transguard`: the Druid morphs by right click (Trap Rat Form, then
    Treewarden Form), Save and Exit in the morph, Play again, three rounds: the game stays up, the part's counters are read. C17
    `soundguard`: the loaded sounds table against ours (the part's own line) and a Median-only Neutral sound monster in view (a
    harness spawn: a look, not a player-path verdict). C18: the cube opened by right click and closed with Esc five times, then
    played on. Set-up: the skills learnt with `setskill` (skill points), the lane's level-120 Druid (rp_items)."""
    mark = engine_mark()
    log, shots, rows, bad = [], [], [], []
    txt = mxl_text().splitlines()
    for w in ("transguard", "soundguard"):
        ln = mxl_part(txt, w)
        rows.append("%s: %s" % (w, ln[:220] or "NO LINE"))
        if not ln or "FAILED" in ln or "not installed" in ln or ln.startswith(w + " off"):
            bad.append("%s not on" % w)
    # C14
    if rp_be("druid"):
        for rnd in range(3):
            for sk, nm in CR_MORPHS:
                learn(sk)
                ok, _l = Hl("skill right %d" % sk, log)
                g.click(0.55, 0.45, button="right")  # the cast, as a player's right click
                time.sleep(2.0)
                st = server_states(log)
                rows.append("round %d %s: selected %s, states %s" % (rnd + 1, nm, ok, st[:8]))
            shots.append(sh("crash_c14_morph_%d" % rnd))
            leave_and_reenter()
            time.sleep(3)
            if not game_alive():
                bad.append("C14: the game died at Save and Exit in the morph (round %d)" % (rnd + 1))
                rp_recover("c14", log)
                break
        rows.append("C14 after: %s" % mxl_part(mxl_text().splitlines(), "transguard")[-60:])
    else:
        bad.append("C14: could not play the Druid")
    # C17
    goto(2)
    px, py = player_xy()
    for cls in CR_WITCH:
        Hl("spawn %d 1 %d %d" % (cls, px + 6, py), log)
    time.sleep(6)
    seen = sorted({m.get("class") for m in hstate()["mons"] if m.get("class") in CR_WITCH})
    shots.append(sh("crash_c17_witch"))
    sg = mxl_part(mxl_text().splitlines(), "soundguard")
    rows.append("C17: witches in view %s, game %s; %s" % (seen, "up" if game_alive() else "GONE", sg[-120:]))
    if not game_alive():
        bad.append("C17: the game died with a Median Neutral sound monster in view")
        rp_recover("c17", log)
    goto(1)
    # C18
    rp_packclear(log)
    iid = rp_ground_item("box", log)
    if iid is not None and rp_pickup(iid, log):
        if held_item():
            Hl("pkt 18 " + _le(iid, 0, 0, 0), log)
            time.sleep(0.5)
        if not right_panel_open():
            g.press("i")
            time.sleep(1.0)
        opened = 0
        for _ in range(5):
            it = rp_item_line(iid)
            if it is None:
                break
            g.click(*rp_inv_xy(it["x"], it["y"]), button="right")
            time.sleep(1.2)
            opened += 1
            g.key("esc")
            time.sleep(1.0)
            if not game_alive():
                bad.append("C18: the game died after a cube panel close")
                break
            if not right_panel_open():
                g.press("i")
                time.sleep(1.0)
        close_right_panel()
        H("move %d %d" % (hstate()["player"].get("x", 0) + 10, hstate()["player"].get("y", 0)))
        time.sleep(3)
        rows.append("C18: cube opened and closed %d times, game %s" % (opened, "up" if game_alive() else "GONE"))
    else:
        rows.append("C18: no cube picked up")
    finish("crashrows", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-300:])


def check_wptabs():
    """A look for rp_areas: the waypoint panel opened in the Rogue Encampment (every waypoint bit set) and a screenshot after a
    click on each act tab at RP_WP_TAB's spots, so the tab positions of acts II-V can be measured. Not a verdict (PARTIAL)."""
    mark = engine_mark()
    log, shots = [], []
    rp_be("barbarian")
    opened = rp_open_acts([5], log)
    for n, _lvl in sorted((w, lvl) for lvl, (_a, w, _k) in rp_waypoints().items()):
        H("waypoint n %d set" % n)
    goto(1)
    close_right_panel()
    wp = find_waypoint_object()
    xy = rp_object_xy(wp[0]) if wp else None
    if xy:
        rp_click_toward(xy[0], xy[1], trade_panel_open)
        time.sleep(0.8)
    shots.append(sh("wptabs_open"))
    for act in (2, 3, 4, 5, 1):
        g.click((RP_WP_TAB[0] + RP_WP_TAB[1] * (act - 1)) / 1600, RP_WP_TAB[2] / 900)
        time.sleep(0.8)
        shots.append(sh("wptabs_act%d" % act))
    g.key("esc")
    finish("wptabs", bool(xy), "SET-UP quest words %s; waypoint %s; screenshots %s" % (opened, xy, shots), mark, shots, log, partial="tab positions are read from the shots")


CHECKS += [("crashrows", check_crashrows), ("wptabs", check_wptabs)]


CHECKS += [("mercs", check_mercs)]


# ---------------------------------------------------------------- lane acts5: Glacial Trail (player bugs #494, #495, 0.1.1)
# Glacial Trail is level 115 (Ice Cave 2; Median's key "Crystalized Cavern Level 2", shown by D2R's string override). Its
# links are D2R's (levels.txt Vis 113 / 117 / 116 by warps 73 / 74 / 75; lvlwarp rows 71-75 equal to D2R's); Median's own
# changes: 8 maze rooms (D2R 10), its side level 116 is a 64 x 64 preset ("Sunless Sea", rockisdead.ds1, D2R a maze), and
# 17 Act 3 / 4 tile files added to lvltypes "Act 5 - Ice Caves" (none of them has a warp tile: orientation 10 / 11).
# The check: harness travel to Crystalline Passage (113, a waypoint level) only, then each level by real left clicks on its warp tile
# (Glacial Trail 115, Frozen Tundra 117), then MXL_GLACIAL_ROUNDS round trips 117 -> 115 -> 117 by clicks with
# a fight walk in 115 between; in HD and in legacy graphics (MXL_GLACIAL_MODES, default "hd,legacy").
GLACIAL_HOPS = ((115, 117),)  # the reported exit; MXL_GLACIAL_HOPS="113-115,115-117" adds Crystalline Passage's way into
# Glacial Trail first (a control: run 17 walked 35 min there and listed one of its warps only)
GLACIAL_FIGHT_LEGS = ((25, 0), (0, 25), (-25, 0), (0, -25))
# The exits' spots: the harness `tiles` verb reads no tile in this build (bug #399: the hash at 0x6c6 holds 65 empty buckets and
# then other data, run checks of 2026-10-29 16:51). Every warp of D2R's ice cave maps (Ice{N,S,E,W}{ahead,back,down}01.ds1) has
# two IceCaveTorch1 (ds1 preset 75 of act 5 = objects.txt 480) beside it, 10 apart, the warp's cells between them (e.g.
# IceNahead01: torches at 41,51 and 41,61, warp cells at tile 8,10-11). So `presets 2` names every warp of the level.
GLACIAL_TORCH = 480
GLACIAL_EXPLORE_S = 1500  # the walk round a cave level until its warps' torches are listed
GLACIAL_CLICK_RING = [(0, 0)] + [(r * ux, r * uy) for r in (3, 6) for ux, uy in ((0, -1), (-1, 0), (-1, -1), (1, -1), (-1, 1), (1, 0),
                                                                                 (0, 1), (1, 1))]
GLACIAL_CLICK_UP = (40, 80, 0)


def glacial_merge_spots(known, found):
    """Adds the newly listed warps to `known` (kept in place) and returns it."""
    for sp in found:
        if all(max(abs(sp[0] - k[0]), abs(sp[1] - k[1])) > 4 for k in known):
            known.append(sp)
    return known


def glacial_spot_order(spots, at, came_at=None, exit_at=None):
    """The warps to try: the one that led to the destination before first, the one the character came in by last, the rest
    nearest first."""
    def key(sp):
        near = lambda q: q is not None and max(abs(sp[0] - q[0]), abs(sp[1] - q[1])) <= 4  # noqa: E731
        return (not near(exit_at), came_at is not None and max(abs(sp[0] - came_at[0]), abs(sp[1] - came_at[1])) < 20,
                abs(sp[0] - at[0]) + abs(sp[1] - at[1]))
    return sorted(spots, key=key)


def glacial_warp_spots(presets):
    """Midpoints of the IceCaveTorch1 pairs (two torches at most 12 apart) of `presets 2` dicts: the level's warps."""
    t = [(q["x"], q["y"]) for q in presets if q["class"] == GLACIAL_TORCH]
    spots, used = [], set()
    for i, (x, y) in enumerate(t):
        if i in used:
            continue
        for j in range(i + 1, len(t)):
            if j not in used and max(abs(t[j][0] - x), abs(t[j][1] - y)) <= 12:
                used.update((i, j))
                spots.append(((x + t[j][0]) // 2, (y + t[j][1]) // 2))
                break
    return spots


def glacial_fight_walk(log):
    """A short walk round the spot in Glacial Trail, fighting what comes (the reports say it crashes "often" there)."""
    p = hstate()["player"]
    for dx, dy in GLACIAL_FIGHT_LEGS:
        acts_walk(p.get("x", 0) + dx, p.get("y", 0) + dy, reach=6, timeout=25, fight=True)
    log.append("glacial: fight walk in %s, life %s, deaths so far %s" % (hstate()["player"].get("area"), hstate()["player"].get("life"),
                                                                      STATE.get("acts_deaths", 0)))


def glacial_click_spot(x, y, dest):
    """Real left clicks round (x, y), on the ground and above it (the warp's select box lies above its foot: lvlwarp SelectY
    -110 .. +5). Returns (clicks, area now)."""
    clicks = 0
    for up in GLACIAL_CLICK_UP:
        for ox, oy in GLACIAL_CLICK_RING:
            fx, fy = rp_screen_xy(x + ox, y + oy)
            fy -= up / 900
            g.click(min(max(fx, RP_SAFE[0] / 1600), RP_SAFE[2] / 1600), min(max(fy, RP_SAFE[1] / 900), RP_SAFE[3] / 900))
            clicks += 1
            for _ in range(3):
                time.sleep(1)
                a = hstate()["player"].get("area")
                if a != STATE.get("glacial_src"):
                    return clicks, a
    return clicks, hstate()["player"].get("area")


def glacial_place_near(x, y):
    """`place` within 8 of the warp at (x, y) (the ring of GLACIAL_PLACE_RING, first that holds). Returns where, or "failed"."""
    for ox, oy in GLACIAL_PLACE_RING:
        H("place %d %d" % (x + ox, y + oy))
        time.sleep(1)
        p = hstate()["player"]
        if max(abs(p.get("x", 0) - x), abs(p.get("y", 0) - y)) <= 8:
            return "at %s,%s" % (p.get("x"), p.get("y"))
    return "failed"


GLACIAL_PLACE_RING = [(r * ux, r * uy) for r in (4, 6) for ux, uy in ((1, 1), (0, 1), (1, 0), (-1, 1), (1, -1), (-1, 0), (0, -1), (-1, -1))]


def glacial_click_exit(src, dest, log, came_at=None):
    """In `src` (harness travel when not there yet): every warp of the level by its torches, the nearest first (the one at
    `came_at`, the way in, last); walk up to it (search walk, fighting) and click it. A warp to another level is noted and the
    character comes back by harness travel. Returns (entered, note)."""
    if hstate()["player"].get("area") != src:
        goto(src)
    if hstate()["player"].get("area") != src:
        return False, "harness travel to %d failed" % src
    STATE["glacial_src"] = src
    known = STATE.setdefault("glacial_warps", {}).setdefault(src, [])  # the rooms unload again: what an earlier walk listed
    spots = glacial_merge_spots(known, glacial_warp_spots(parse_presets(Hl("presets 2", log)[1])))
    explored, t0, rooms, done, tried = 0, time.time(), None, [], []
    way_in = lambda sp: came_at is not None and max(abs(sp[0] - came_at[0]), abs(sp[1] - came_at[1])) < 20  # noqa: E731
    while True:
        p = hstate()["player"]
        todo = [sp for sp in glacial_spot_order(spots, (p.get("x", 0), p.get("y", 0)), came_at,
                                                STATE.get("glacial_exit", {}).get((src, dest))) if sp not in done]
        if not [sp for sp in todo if not way_in(sp)] and time.time() - t0 < GLACIAL_EXPLORE_S:
            # no untried warp but the way in: the far rooms list their presets only once loaded, walk to the next room's middle
            if rooms is None:
                rooms = [(int(m.group(1)) + 40, int(m.group(2)) + 40) for m in
                         (re.match(r"room x=(-?\d+) y=(-?\d+)", ln) for ln in Hl("presets rooms", log)[1]) if m]
            if rooms:
                rooms.sort(key=lambda r: abs(r[0] - p.get("x", 0)) + abs(r[1] - p.get("y", 0)))
                rx, ry = rooms.pop(0)
                if not (acts_walk(rx, ry, reach=12, timeout=45, fight=True) or acts_search_walk(rx, ry, log, budget_s=90, reach=12)):
                    if player_dead(hstate()["player"]):
                        rooms = []
                explored += 1
                lines = Hl("presets 2", log)[1]
                spots = glacial_merge_spots(known, glacial_warp_spots(parse_presets(lines)))
                p = hstate()["player"]
                log.append("glacial: room %d,%d -> at %s,%s; %s" % (rx, ry, p.get("x"), p.get("y"), (lines or ["-"])[-1]))
                continue
        if not todo:
            break
        x, y = todo[0]
        done.append((x, y))
        walked = acts_walk(x, y, reach=6, timeout=60, fight=True) or acts_search_walk(x, y, log, budget_s=240, reach=6)
        how = "walked up"
        if not walked:  # SET-UP: the walk ended in a pocket beside the warp's room (run 18: below the exit's ledge); `place` by it
            how = "NOT reached by the walk, placed %s" % glacial_place_near(x, y)
        clicks, area = glacial_click_spot(x, y, dest)
        tried.append("%d,%d (%s, %d clicks -> %s)" % (x, y, how, clicks, area))
        if area == dest:
            STATE.setdefault("glacial_exit", {})[(src, dest)] = (x, y)
            return True, "%d -> %d by clicks on the warp at %d,%d (warps by torches: %d, %d rooms walked to; %s)" % (
                src, dest, x, y, len(spots), explored, "; ".join(tried))
        if area != src:
            goto(src)
            if hstate()["player"].get("area") != src:
                return False, "%d: harness travel back failed after the warp at %d,%d led to %s" % (src, x, y, area)
    return False, "%d -> %d NOT entered: warps by torches %d (after walking to %d rooms), tried %s" % (
        src, dest, len(spots), explored, "; ".join(tried) or "none")


def check_glacial():
    if not need_game():
        add("glacial", "BLOCKED", "not in the game")
        return
    if os.environ.get("MXL_GLACIAL_PROBE"):  # bug #399: what the harness `tiles` reads in Glacial Trail
        mark, log = engine_mark(), []
        goto(115)
        found = []
        for a, b in ((0, 0x400), (0x900, 0x2000), (0x2000, 0x4000), (0x4000, 0x8000)):
            ok, lines = Hl("hashscan %d %d" % (a, b), log)
            found += [ln for ln in lines if ln.startswith("hash 0x") and " type 5 " in ln] + [ln for ln in lines if ln.startswith("hashscan ")]
        finish("glacial_probe", True, "SET-UP harness travel to 115; `hashscan` type 5: %s" % " / ".join(found[:130]), mark, [], log)
        return
    modes = [m.strip() for m in (os.environ.get("MXL_GLACIAL_MODES") or "hd,legacy").split(",") if m.strip()]
    rounds = int(os.environ.get("MXL_GLACIAL_ROUNDS") or 3)
    acts_build_setup([])  # the fights with the build's spells (else the Attack skill: minutes per cave monster, run 16)
    hops = [tuple(int(a) for a in h.split("-")) for h in os.environ["MXL_GLACIAL_HOPS"].split(",")]         if os.environ.get("MXL_GLACIAL_HOPS") else list(GLACIAL_HOPS)
    for mode in modes:
        mark, log, shots, steps = engine_mark(), [], [], []
        goto(109)
        gfx = set_graphics(mode)
        ok, came, got = True, None, False
        for src, dest in hops:
            got, note = glacial_click_exit(src, dest, log, came_at=came)
            p = hstate()["player"]
            came = (p.get("x", 0), p.get("y", 0)) if got else None
            steps.append(note)
            shots.append(sh("glacial_%s_%d" % (mode, dest)))
            ok = ok and got
        trips = 0
        for r in range(rounds if got else 0):  # the rounds need the reported exit (the last hop), not the control
            goto(115)  # Glacial Trail's own waypoint (34)
            glacial_fight_walk(log)
            got, note = glacial_click_exit(115, 117, log)
            steps.append("round %d: %s" % (r + 1, note))
            if not got:
                ok = False
                break
            trips += 1
        shots.append(sh("glacial_%s_end" % mode))
        finish("glacial_%s" % mode, ok, "SET-UP harness travel to %s (waypoint) and to Glacial Trail's "
               "waypoint (34) for each round, warps found by their torches (bug #399), `place` beside a warp the walk did not reach (named per try), level 80 Sorceress of the acts build; graphics %s (asked %s); judged: real left clicks on the exit; %s; "
               "rounds with a fight walk in Glacial Trail: %d of %d" % (hops[0][0], "set" if gfx else "NOT set", mode, "; ".join(steps), trips, rounds),
               mark, shots, log)


CHECKS += [("glacial", check_glacial)]


# ---------------------------------------------------------------- lane cache360: D2R's HD asset caches over a session (bug #360)
# MXL_CACHE_ROUTE: comma-separated steps, default the route of bug #360 ("t1,t2,t3,t4,t5,andariel" = the acts check's five towns
# with every NPC talk, then its Andariel stage, which takes the harness `level 37`). Steps: tN = acts_town(N) (harness travel,
# walk, talks); vN = act N's town visited (harness travel and the sweep walk, no talks); andariel = acts_boss("andariel");
# L<id> = harness `level <id>` and a short walk; c4click = harness travel to Catacombs 3, a walk next to its stairs down, then a
# real left click on the stairs (the player's way into Catacombs 4); with MXL_CACHE_GOD=1 an L step walks without fighting. After every step tools/cache_probe.py reads the cache counts
# and the cached variant tables of the running game (cache_route.json in the run folder).
CACHE_ROUTE_DEFAULT = "t1,t2,t3,t4,t5,andariel"
# MXL_CACHE_POLL=<seconds>: for the whole run a thread reads the cache counts every <seconds> (tools/cache_probe.py poll, read
# only) into cache_poll.jsonl of the run folder, each record labelled with CACHE_POLL["tag"] (the check and its step); the
# peak of every cache goes into the report. MXL_CACHE_GOD=1: cache_route plays in god mode (a long route with a low character).
CACHE_POLL = {"tag": "", "stop": False, "thread": None, "peaks": None}


def cache_tag(tag):
    CACHE_POLL["tag"] = tag


def cache_poll_start():
    import threading
    import cache_probe
    try:
        every = float(os.environ.get("MXL_CACHE_POLL") or 0)
    except ValueError:
        every = 0
    if every <= 0 or CACHE_POLL["thread"]:
        return
    path = os.path.join(g.current_run(), "cache_poll.jsonl")
    CACHE_POLL["stop"] = False

    def run():
        CACHE_POLL["peaks"] = cache_probe.poll(lambda: (g.game_pids() or [None])[0], path, every,
                                               stop=lambda: CACHE_POLL["stop"], tag_fn=lambda: CACHE_POLL["tag"])
    CACHE_POLL["thread"] = threading.Thread(target=run, name="cache_poll", daemon=True)
    CACHE_POLL["thread"].start()


def cache_poll_stop():
    """Stops the poll thread; the peaks as report text ("" when no poll ran)."""
    import cache_probe
    t = CACHE_POLL["thread"]
    if not t:
        return ""
    CACHE_POLL["stop"] = True
    t.join(30)
    CACHE_POLL["thread"] = None
    return "## Asset caches (MXL_CACHE_POLL)\n\n" + (cache_probe.peaks_text(CACHE_POLL["peaks"] or {}) or "no reads") + \
        "\n\n(cache_poll.jsonl in the run folder; `py -3 tools/cache_probe.py peaks <file>`)\n\n"


def cache_route_steps(env=None):
    raw = os.environ.get("MXL_CACHE_ROUTE", "") if env is None else env
    return [s.strip() for s in (raw or CACHE_ROUTE_DEFAULT).split(",") if s.strip()]


def cache_new_asserts(mark):
    """The AssetCache.h:187 asserts of d2rloader.log since `mark` (tools/cache_probe.asserts_in_log)."""
    import cache_probe
    return cache_probe.asserts_in_log(g._read_from(g.LOADER_LOG, mark["loader"]) or "")


def cache_snapshot(step, mark, prev_keys, rows):
    """Cache counts and variant tables after a step; returns (record, variant keys)."""
    import cache_probe
    pids = g.game_pids()
    snap = cache_probe.snapshot(pids[0]) if pids else {"error": "no game"}
    keys = snap.get("variants") or []
    rec = {"step": step, "area": hstate()["player"].get("area"), "caches": snap.get("caches"), "error": snap.get("error"),
           "variants": len(keys), "variants_mxl": sum(1 for k in keys if "/mxl/" in k),
           "new_variants": sorted(set(keys) - set(prev_keys)), "asserts": cache_new_asserts(mark)}
    rows.append("%s (area %s): variant tables %d (%d ours)%s%s" % (
        step, rec["area"], rec["variants"], rec["variants_mxl"],
        "; caches %s" % ",".join("%s=%d/%d" % (o, n, c) for o, (n, c) in sorted((rec["caches"] or {}).items())) if rec["caches"] else "",
        "; ASSERT %s" % "; ".join("%s/%s %s" % (a["default"], a["capacity"], a["path"]) for a in rec["asserts"]) if rec["asserts"] else ""))
    return rec, keys


def cache_tile_class(level, dest):
    """The warp tile class (lvlwarp Id) that leads from `level` to `dest`: levels.txt Vis<i> == dest -> Warp<i>."""
    row = next((r for r in table("levels") if r.get("Id") == str(level)), None)
    if not row:
        return None
    for i in range(8):
        if row.get("Vis%d" % i) == str(dest):
            w = row.get("Warp%d" % i)
            return int(w) if w and w.lstrip("-").isdigit() and int(w) >= 0 else None
    return None


def cache_tiles(lines):
    """`tiles` lines -> [{"id", "class", "mode", "x", "y", "area"}]."""
    out = []
    for ln in lines:
        m = re.match(r"tile id=(\d+) class=(-?\d+) mode=(\d+) at (\d+),(\d+) dist=\S+ area=(\d+)", ln)
        if m:
            out.append(dict(zip(("id", "class", "mode", "x", "y", "area"), map(int, m.groups()))))
    return out


def cache_click_into(src, dest, log):
    """Harness travel to `src`, a walk next to the warp tile to `dest`, then real left clicks on it. True when in `dest`."""
    goto(src)
    if hstate()["player"].get("area") != src:
        log.append("cache_click_into: not in %d" % src)
        return False
    want = cache_tile_class(src, dest)
    tile = None
    for _ in range(6):
        tiles = [t for t in cache_tiles(Hl("tiles", log)[1]) if t["area"] == src and (want is None or t["class"] == want)]
        if tiles:
            tile = tiles[0]
            break
        pre = [q for q in parse_presets(Hl("presets 5", log)[1])]
        if pre:  # not loaded yet: walk (harness move) towards the nearest warp preset
            p = hstate()["player"]
            q = min(pre, key=lambda q: (q["x"] - p["x"]) ** 2 + (q["y"] - p["y"]) ** 2)
            acts_walk(q["x"], q["y"], reach=12, timeout=60, fight=True)
        else:
            break
    if tile is None:
        log.append("cache_click_into: no warp tile of class %s in %d" % (want, src))
        return False
    log.append("cache_click_into: tile %s" % tile)
    acts_walk(tile["x"], tile["y"], reach=8, timeout=60, fight=True)
    p = hstate()["player"]
    if max(abs(p.get("x", 0) - tile["x"]), abs(p.get("y", 0) - tile["y"])) > 10:  # a wall the walk does not get round
        x0, y0 = p.get("x", 0), p.get("y", 0)
        for frac in (0.35, 0.7, 1.0):  # travel help (harness) in steps: the rooms near the stairs load as the character nears
            tx, ty = int(x0 + (tile["x"] - x0) * frac), int(y0 + (tile["y"] - y0) * frac)
            ring = [(0, 0)] if frac < 1.0 else []
            if frac == 1.0:  # the stairs' own side: rings round the tile (the floor next to a warp is often a separate room)
                ring = [(r * ux, r * uy) for r in (4, 7, 10, 14, 18) for ux, uy in ((0, 1), (1, 0), (1, 1), (-1, 1), (1, -1), (0, -1), (-1, 0), (-1, -1))]
            for dx, dy in ring:
                if Hl("place %d %d" % (tx + dx, ty + dy), log)[0]:
                    break
            time.sleep(2)
        log.append("cache_click_into: TRAVEL HELP `place` next to the tile, player now %s" % {k: hstate()["player"].get(k) for k in ("x", "y")})
    in_dest = lambda: hstate()["player"].get("area") == dest  # noqa: E731
    rp_click_toward(tile["x"], tile["y"], in_dest, tries=6)
    if not in_dest():  # the stairs in a fenced pit: click the pit's floor in front of them first (D2R paths round), then them
        for ox, oy in ((0, 60), (-80, 50), (80, 50), (-140, 20)):
            fx, fy = rp_screen_xy(tile["x"], tile["y"], hstate()["player"])
            px, py = min(max(fx * 1600 + ox, RP_SAFE[0]), RP_SAFE[2]), min(max(fy * 900 + oy, RP_SAFE[1]), RP_SAFE[3])
            g.click(px / 1600, py / 900)
            time.sleep(4)
            rp_click_toward(tile["x"], tile["y"], in_dest, tries=2)
            if in_dest():
                break
    if not in_dest():  # the pit may open to another side: travel help to wider rings round the tile, real clicks from each spot
        tried, t0 = set(), time.time()
        for r in (20, 26, 32, 40):
            for ux, uy in ((1, 0), (0, 1), (1, 1), (0, -1), (1, -1), (-1, 1), (-1, -1), (-1, 0)):
                if in_dest() or len(tried) >= 12 or time.time() - t0 > 480:
                    break
                if not Hl("place %d %d" % (tile["x"] + r * ux, tile["y"] + r * uy), log)[0]:
                    continue
                time.sleep(2)
                p = hstate()["player"]
                spot = (p.get("x", 0) // 4, p.get("y", 0) // 4)
                if spot in tried:
                    continue
                tried.add(spot)
                log.append("cache_click_into: TRAVEL HELP `place` on ring %d, player %s,%s" % (r, p.get("x"), p.get("y")))
                rp_click_toward(tile["x"], tile["y"], in_dest, tries=4)
    for _ in range(5):
        if in_dest():
            break
        time.sleep(2)
    log.append("cache_click_into: real clicks on the tile, now in area %s" % hstate()["player"].get("area"))
    return in_dest()


def cache_route_step(step, log):
    if re.fullmatch(r"t[1-5]", step):
        acts_town(int(step[1]))
    elif re.fullmatch(r"v[1-5]", step):
        goto(ACT_TOWNS[int(step[1])])
        acts_town_sweep(int(step[1]), log)
    elif step == "andariel":
        acts_boss("andariel")
    elif re.fullmatch(r"L\d+", step):
        st = goto(int(step[1:]))
        p = st["player"]
        fight = os.environ.get("MXL_CACHE_GOD") != "1"  # god mode: walk past the monsters (a fight of a low character never ends)
        for dx, dy in ((20, 0), (0, 20), (-20, 0), (0, -20)):
            acts_walk(p.get("x", 0) + dx, p.get("y", 0) + dy, reach=6, timeout=20, fight=fight)
    elif step == "c4click":
        ok = cache_click_into(36, 37, log)
        log.append("c4click: %s" % ("entered Catacombs 4 by the click" if ok else "NOT entered by a click"))
        if ok:
            p = hstate()["player"]
            for dx, dy in ((15, 0), (0, 15)):
                acts_walk(p.get("x", 0) + dx, p.get("y", 0) + dy, reach=6, timeout=20, fight=True)
            time.sleep(5)
    else:
        log.append("unknown step %s" % step)


def check_cache_route():
    """Lane cache360 (bug #360): the route of MXL_CACHE_ROUTE in one launch, D2R's asset caches read after each step."""
    import json
    if not need_game():
        add("cache_route", "BLOCKED", "not in the game")
        return
    mark0 = engine_mark()
    log, rows, recs, keys = [], [], [], []
    god = os.environ.get("MXL_CACHE_GOD") == "1"
    if god:
        enable_debug()
        cheat("god 1")
    rec, keys = cache_snapshot("start", mark0, keys, rows)
    recs.append(rec)
    for step in cache_route_steps():
        mark = engine_mark()
        cache_tag("cache_route " + step)
        try:
            guard()
            cache_route_step(step, log)
        except Exception as e:
            if WD.abort:
                raise
            log.append("step %s: script error %r" % (step, e))
        rec, keys = cache_snapshot(step, mark, keys, rows)
        recs.append(rec)
        g.log("cache_route " + rows[-1])
    if god:
        cheat("god 0")
    with open(os.path.join(g.current_run(), "cache_route.json"), "w", encoding="utf-8") as f:
        json.dump({"route": cache_route_steps(), "steps": recs, "final_variants": keys}, f, indent=1)
    n_assert = sum(len(r["asserts"]) for r in recs)
    entered = any("entered Catacombs 4 by the click" in ln for ln in log)
    finish("cache_route %s" % ",".join(cache_route_steps()), n_assert == 0,
           "AssetCache asserts %d; %s%s" % (n_assert, "; ".join(rows), "; c4click: entered by a real click" if entered else ""),
           mark0, [sh("cache_route_end")], rows + log[-200:] + (["SET-UP: god mode (MXL_CACHE_GOD=1)"] if god else []))


CHECKS += [("cache_route", check_cache_route)]

# --- lane relprep: the release candidate's Act 1 town path, clicks only ------------------------------------------------------
RELP_CLASSES = ("sorceress", "barbarian")  # MXL_RELP_CLASSES=amazon,paladin for others
RELP_NPCS = ((148, "Akara"), (154, "Charsi"))
RELP_PANELS = (("c", "character"), ("i", "inventory"), ("t", "skilltree"))
RELP_DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))  # map directions tried out of the camp


def relp_wait_loaded(timeout=60):
    """True once the client draws the game: the Loading screen is black outside its picture, the game's bottom bar is not."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        a = grab()
        h, w = a.shape[0], a.shape[1]
        if a[int(h * 0.93):int(h * 0.99), int(w * 0.3):int(w * 0.7)].mean() > 15:
            time.sleep(1.0)
            return True
        time.sleep(1.0)
    return False


def relp_click_walk(c, x, y, done, clicks=25):
    """Left clicks toward the map point (at most ~260 px from the character, the safe part of the screen) until done() or the
    character stops moving for 4 clicks. Returns done()."""
    import playthrough as pt
    still, last = 0, None
    for _ in range(clicks):
        guard()
        if done():
            return True
        p = c.player()
        if not p or player_dead(p):
            return False
        here = (p.get("x"), p.get("y"))
        still = still + 1 if here == last else 0
        if still >= 4:
            break
        last = here
        c.g.click(*pt.clamp_towards(*pt.project(p, x, y)))
        time.sleep(1.5)
    return done()


def relp_walkmap(x, y, half=120, step=4):
    """`walkmap` (a read: the game's own walk collision of the loaded rooms round (x, y)) -> {"grid", "x0", "y0", "step", "level",
    "others" {letter: level id}} or None (an older DLL without the verb)."""
    ok, lines = H("walkmap %d %d %d %d" % (x, y, half, step), timeout=20)
    rows = [ln.split(" ", 2)[2] for ln in lines if ln.startswith("wm y=") and ln.count(" ") >= 2]
    meta = next((kv(ln) for ln in lines if ln.startswith("walkmap x0=")), None)
    if not ok or not rows or not meta:
        return None
    others = {}
    if meta.get("others", "none") != "none":
        others = {k: int(v) for k, v in (e.split("=") for e in meta["others"].split(","))}
    return {"grid": rows, "x0": int(meta["x0"]), "y0": int(meta["y0"]), "step": int(meta["step"]), "level": int(meta["level"]),
            "others": others}


def relp_merge(known, wm):
    """Adds a `walkmap` grid to `known` {(x, y) map point on the step grid: "." | "#" | level id}: what the game answered once
    stays known when the character walks on (the game's collision reaches only its own room and the next ones). The game's
    test is the straight walk from the character to the spot (free cells come in rays round it), so a free answer from any
    place wins over a blocked one: "#" is only "not seen free yet". Returns known."""
    if wm is None:
        return known
    st = wm["step"]
    for r, row in enumerate(wm["grid"]):
        for c, ch in enumerate(row):
            if ch == "?":
                continue
            key = (int(round((wm["x0"] + c * st) / st)) * st, int(round((wm["y0"] + r * st) / st)) * st)
            if ch == "#" and known.get(key, "#") != "#":
                continue
            known[key] = wm["others"].get(ch, ch) if ch not in ".#" else ch
    return known


def relp_known_wm(known, step=4):
    """The `known` map points (relp_merge) as a `walkmap`-shaped dict for relp_plan; cells never answered read `?`."""
    if not known:
        return None
    xs, ys = [k[0] for k in known], [k[1] for k in known]
    x0, y0 = min(xs), min(ys)
    w, h = (max(xs) - x0) // step + 1, (max(ys) - y0) // step + 1
    letters, others = {}, {}
    grid = [["?"] * w for _ in range(h)]
    for (x, y), v in known.items():
        if not isinstance(v, str):
            ch = letters.setdefault(v, "ABCDEFGH"[min(len(letters), 7)])
            others[ch] = v
            v = ch
        grid[(y - y0) // step][(x - x0) // step] = v
    return {"grid": ["".join(r) for r in grid], "x0": x0, "y0": y0, "step": step, "level": 0, "others": others}


def relp_plan(wm, start, dest_level, avoid=(), target=None, far_from=None, avoid_r=30, hidden="?"):
    """Breadth-first path on a `walkmap` grid from the map point `start` to the nearest free cell of `dest_level` (with `target`:
    to the nearest free cell within 5 of that map point); when none is in the loaded rooms, to the reachable cell at the edge of
    what is known (beside a `?` cell or the window's edge) that lies farthest from `far_from` (default `start`; with `target`:
    nearest to it) and is not within 30 of a point in `avoid` (frontiers tried before). Diagonal steps only between two free
    cells (no corner cutting through a palisade post). Returns (map points of the path, "level" | "target" | "frontier") or (None, why)."""
    grid, x0, y0, st = wm["grid"], wm["x0"], wm["y0"], wm["step"]
    h, w = len(grid), max(len(r) for r in grid)
    goal = {k for k, v in wm["others"].items() if v == dest_level}

    def free(r, c):
        return 0 <= r < h and 0 <= c < len(grid[r]) and grid[r][c] not in "#?"

    sr, sc = int(round((start[1] - y0) / st)), int(round((start[0] - x0) / st))
    if not free(sr, sc):  # the character's own cell may read blocked (its own body): the nearest free cell instead
        near = [(abs(r - sr) + abs(c - sc), r, c) for r in range(max(0, sr - 3), min(h, sr + 4)) for c in range(max(0, sc - 3), sc + 4)
                if free(r, c)]
        if not near:
            return None, "no free cell at the character (%s)" % (start,)
        _, sr, sc = min(near)
    prev = {(sr, sc): None}
    queue, k = [(sr, sc)], 0
    while k < len(queue):
        r, c = queue[k]
        k += 1
        for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nr, nc = r + dr, c + dc
            if (nr, nc) in prev or not free(nr, nc) or (dr and dc and not (free(r + dr, c) and free(r, c + dc))):
                continue
            prev[(nr, nc)] = (r, c)
            queue.append((nr, nc))

    def path_to(cell):
        out = []
        while cell is not None:
            out.append((x0 + cell[1] * st, y0 + cell[0] * st))
            cell = prev[cell]
        return out[::-1]

    def at(cell):
        return x0 + cell[1] * st, y0 + cell[0] * st

    if target is not None:
        hits = [cell for cell in queue if abs(at(cell)[0] - target[0]) <= 5 and abs(at(cell)[1] - target[1]) <= 5]
        if hits:
            return path_to(hits[0]), "target"
    else:
        hits = [cell for cell in queue if grid[cell[0]][cell[1]] in goal]
        if hits:
            return path_to(hits[0]), "level"

    def edge(r, c):
        return any(not (0 <= r + dr < h and 0 <= c + dc < len(grid[r + dr])) or grid[r + dr][c + dc] in hidden
                   for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0)))

    fronts = [cell for cell in queue if edge(*cell)]
    pts = [(cell, (x0 + cell[1] * st, y0 + cell[0] * st)) for cell in fronts]
    pts = [(cell, p) for cell, p in pts if all(abs(p[0] - a[0]) + abs(p[1] - a[1]) > avoid_r for a in avoid)]
    if not pts:
        return None, "no new frontier (%d cells reachable)" % len(queue)
    if target is not None:
        cell, _ = min(pts, key=lambda q: (q[1][0] - target[0]) ** 2 + (q[1][1] - target[1]) ** 2)
    else:
        far = far_from or start
        cell, _ = max(pts, key=lambda q: (q[1][0] - far[0]) ** 2 + (q[1][1] - far[1]) ** 2)
    return path_to(cell), "frontier"


def relp_waypoints(path, reach=10):
    """Every `reach`-th point of a path (and its end): the click targets, near enough to stay on the screen."""
    if not path:
        return []
    pts = path[reach::reach]
    if not pts or pts[-1] != path[-1]:
        pts.append(path[-1])
    return pts


def relp_follow(c, path, done, log, fight=None):
    """Left clicks along a planned path (relp_plan): one click per waypoint until the character is within 4 of it, done() or it
    stops. `fight()` (act1_hour) runs before each waypoint and fights what came near. Returns done()."""
    for wx, wy in relp_waypoints(path, 3):
        if done():
            return True
        if fight is not None:
            fight()
        near = lambda: done() or abs(c.player().get("x", 0) - wx) + abs(c.player().get("y", 0) - wy) <= 4  # noqa: E731
        if not relp_click_walk(c, wx, wy, near, clicks=8):
            p = c.player()
            log.append("relp_follow: stopped at %s on the way to %s,%s" % ((p.get("x"), p.get("y")), wx, wy))
            return done()
    return done()


def relp_walk_to(c, x, y, done, log, budget=120, fight=None):
    """Left clicks to the map point (x, y) on paths planned on `walkmap` (relp_plan with a target), planning again from each stop.
    Without `walkmap` (an older DLL) plain clicks toward the point. Returns done()."""
    t0, tried, plans, known = time.time(), [], 0, {}
    while not done() and time.time() - t0 < budget and plans < 8:
        p = c.player()
        wm0 = relp_walkmap(p["x"], p["y"])
        if wm0 is None:
            return relp_click_walk(c, x, y, done, clicks=40)
        wm = relp_known_wm(relp_merge(known, wm0), wm0["step"])
        path, kind = relp_plan(wm, (p["x"], p["y"]), None, tried, target=(x, y), avoid_r=12, hidden="?#")
        plans += 1
        log.append("relp_walk_to %s,%s: plan %d from %s: %s" % (x, y, plans, (p["x"], p["y"]),
                                                              kind if path is None else "%s path of %d cells" % (kind, len(path))))
        if path is None:
            break
        tried.append(path[-1])
        relp_follow(c, path, done, log, fight)
        if kind == "target":
            break
    return done()


def relp_walk_level(c, level, log, budget=420, fight=None, anchor=None, plans_max=14, tried=None, known=None):
    """Into the level `level` by left clicks only, on paths planned on the game's walk collision (`walkmap`, a read), merged
    over the walk (relp_merge; a caller's `known` carries over between calls): to the level's free cells when they are known,
    else to the edge of the known map farthest from `anchor` (default: where the walk started), then plan again. Returns
    (reached, note)."""
    p0 = c.player()
    anchor = anchor or (p0["x"], p0["y"])
    t0, planned = time.time(), 0
    tried = [] if tried is None else tried  # frontiers walked to (a caller's list carries over between calls)
    known = {} if known is None else known
    there = lambda: c.player().get("area") == level  # noqa: E731
    while not there() and time.time() - t0 < budget and planned < plans_max:
        p = c.player()
        wm0 = relp_walkmap(p["x"], p["y"])
        if wm0 is None:
            return False, "no `walkmap` answer"
        wm = relp_known_wm(relp_merge(known, wm0), wm0["step"])
        path, kind = relp_plan(wm, (p["x"], p["y"]), level, tried, far_from=anchor, avoid_r=12, hidden="?#")
        planned += 1
        if path is None:
            log.append("relp_walk_level %d: plan %d from %s: %s" % (level, planned, (p["x"], p["y"]), kind))
            break
        log.append("relp_walk_level %d: plan %d from %s: %s path of %d cells to %s (others %s)" % (
            level, planned, (p["x"], p["y"]), kind, len(path), path[-1], wm["others"]))
        tried.append(path[-1])
        relp_follow(c, path, there, log, fight)
        if kind == "level" and not there():  # next to the level's cell but not over the border yet: a few more clicks on it
            relp_click_walk(c, path[-1][0], path[-1][1], there, clicks=6)
    return there(), "%s after %.0f s, %d plans" % ("area %d reached" % level if there() else "still in area %s" % c.player().get("area"),
                                                   time.time() - t0, planned)


def relp_walk_out(c, log, budget=420, fight=None):
    """Rogue Encampment -> Blood Moor by left clicks only (relp_walk_level 2: the gate is found on the game's walk collision).
    Falls back to relp_walk_out_search when the DLL has no `walkmap`. Returns (reached, the last town position, note)."""
    p0 = c.player()
    last = {"town": (p0["x"], p0["y"])}

    def track():
        p = c.player()
        if p.get("area") == 1:
            last["town"] = (p["x"], p["y"])
        if fight is not None:
            fight()

    if relp_walkmap(p0["x"], p0["y"], half=8, step=4) is None:
        log.append("relp_walk_out: no `walkmap` answer, the direction search instead")
        return relp_walk_out_search(c, log, budget)
    ok, note = relp_walk_level(c, 2, log, budget, track, plans_max=40)  # a map reaches about a room round the character
    return ok, last["town"], note


def relp_walk_out_search(c, log, budget=420):
    """Rogue Encampment -> Blood Moor by left clicks only, without a map: toward a Blood Moor monster when one is in view, else out along the
    eight map directions in turn (back to the start between them). Returns (reached, the last town position, note)."""
    p0 = c.player()
    start, last_town = (p0["x"], p0["y"]), (p0["x"], p0["y"])
    t0 = time.time()

    def out():
        nonlocal last_town
        p = c.player()
        if p.get("area") == 1:
            last_town = (p["x"], p["y"])
        return p.get("area") == 2

    rooms = [(int(r["x"]), int(r["y"])) for r in (kv(ln) for ln in H("presets rooms")[1] if ln.startswith("room x="))]
    if rooms:  # the camp's own rooms (a read): head for the outermost ones, spread around the camp, then on outward
        cx, cy = sum(x for x, _ in rooms) / len(rooms), sum(y for _, y in rooms) / len(rooms)
        far = sorted(rooms, key=lambda r: -((r[0] - cx) ** 2 + (r[1] - cy) ** 2))
        picks = []
        for r in far:
            if all(abs(r[0] - q[0]) + abs(r[1] - q[1]) > 60 for q in picks):
                picks.append(r)
        log.append("relp_walk_out: %d town rooms, centre %.0f,%.0f, edge rooms %s" % (len(rooms), cx, cy, picks[:8]))
        for rx, ry in picks[:8]:
            if time.time() - t0 > budget:
                break
            if relp_click_walk(c, rx, ry, out, clicks=40):
                break
            ox, oy = rx - cx, ry - cy
            k = 120.0 / max(1.0, (ox * ox + oy * oy) ** 0.5)
            if relp_click_walk(c, rx + ox * k, ry + oy * k, out, clicks=20):
                break
            log.append("relp_walk_out: edge room %s,%s ended at %s" % (rx, ry, (c.player().get("x"), c.player().get("y"))))
    for d in RELP_DIRS if c.player().get("area") != 2 else ():
        if time.time() - t0 > budget:
            break
        bm = [m for m in hstate()["mons"] if m.get("area") == 2]
        if bm:
            m = min(bm, key=lambda m: m.get("dist", 99))
            log.append("relp_walk_out: Blood Moor monster in view at %s,%s" % (m.get("mx"), m.get("my")))
            if relp_click_walk(c, m["mx"], m["my"], out, clicks=30):
                break
        if relp_click_walk(c, start[0] + 150 * d[0], start[1] + 150 * d[1], out, clicks=30):
            break
        log.append("relp_walk_out: direction %s ended at %s" % (d, (c.player().get("x"), c.player().get("y"))))
        relp_click_walk(c, start[0], start[1], lambda: abs(c.player().get("x", 0) - start[0]) + abs(c.player().get("y", 0) - start[1]) < 6)
    ok = c.player().get("area") == 2
    return ok, last_town, "%s after %.0f s" % ("Blood Moor reached" if ok else "still in area %s" % c.player().get("area"), time.time() - t0)


def relp_npc_offsets():
    """Client-fraction offsets round an NPC's projected feet, nearest first: the body stands above the feet, and in town the
    drawn NPC was seen up to ~170 px below the projected spot (slot 3, Akara, 2026-10-29)."""
    pts = [(dx * 0.03, dy * 0.045) for dy in range(-3, 5) for dx in range(-3, 4)]
    return sorted(pts, key=lambda d: abs(d[0]) * 1.6 + abs(d[1] + 0.03))


def relp_npc_spot(c, fx, fy, budget=40):
    """A point on screen where hovering shows a unit's name in the top-centre box (D2 draws the hovered unit's name there),
    searched round (fx, fy); None when no hover shows a name within `budget` seconds."""
    t0 = time.time()
    for dx, dy in relp_npc_offsets():
        if time.time() - t0 > budget:
            break
        x, y = fx + dx, fy + dy
        if not (0.05 < x < 0.95 and 0.12 < y < 0.80):
            continue
        c.g.click(0.04, 0.06, move_only=True)
        time.sleep(0.15)
        a = grab()
        c.g.click(x, y, move_only=True)
        time.sleep(0.35)
        b = grab()
        if clusters(a, b, (0.36, 0.0, 0.64, 0.07), thr=120, minblocks=2):
            return x, y
    return None


def relp_talk(c, npc, who, log):
    """Walk to the NPC with clicks (a round of the town when not in view), click them, wait for the menu (its gold frame), click
    Trade (the second line), see the trade window open, close it. Returns (status, note)."""
    import playthrough as pt
    def near():
        return next((u for u in sorted(hstate()["mons"], key=lambda u: u.get("dist", 99)) if u.get("class") == npc), None)

    m = near()
    # where the NPC stands (`find`, a read, no move; older DLLs: the map preset, which a loaded room has already used up)
    pres = [{"x": int(q["mx"]), "y": int(q["my"])} for q in (kv(ln) for ln in H("find %d" % npc)[1] if ln.startswith("found id="))]
    pres = pres or [q for q in parse_presets(H("presets 1")[1]) if q["class"] == npc]
    tried, known, p0 = [], {}, c.player()
    for _ in range(8 if m is None and not pres else 0):  # not spawned yet (its room not loaded): walk the camp's unknown edges
        relp_walk_level(c, 9999, log, budget=60, anchor=(p0["x"], p0["y"]), plans_max=1, tried=tried, known=known)
        m = near()
        pres = [{"x": int(q["mx"]), "y": int(q["my"])} for q in (kv(ln) for ln in H("find %d" % npc)[1] if ln.startswith("found id="))]
        if m or pres:
            log.append("relp_talk: %s found after %d walks round the camp" % (who, len(tried)))
            break
    if m is None and pres:
        log.append("relp_talk: %s stands at %s,%s" % (who, pres[0]["x"], pres[0]["y"]))
        relp_walk_to(c, pres[0]["x"], pres[0]["y"], lambda: (near() or {}).get("dist", 99) < 12, log)
        m = near()
    for d in RELP_DIRS if m is None else ():
        p = c.player()
        pt.walk_to(c, p["x"] + 15 * d[0], p["y"] + 15 * d[1], reach=4, timeout=15)
        m = near()
        if m:
            break
    if m is None:
        return "BLOCKED", "%s not found in town (preset %s)" % (who, (pres[0]["x"], pres[0]["y"]) if pres else "none")
    relp_walk_to(c, m["mx"], m["my"], lambda: (near() or {}).get("dist", 99) <= 5, log, budget=90)  # round a forge wall
    pt.walk_to(c, m["mx"], m["my"], reach=5, timeout=20)
    frame = None
    for k in range(3):
        m = next((u for u in hstate()["mons"] if u.get("id") == m["id"]), m)
        p = c.player()
        fx, fy = pt.project(p, m["mx"], m["my"])
        spot = relp_npc_spot(c, fx, fy)
        log.append("relp_talk: %s projected at %.3f,%.3f, name label at %s" % (who, fx, fy, spot))
        if spot:
            c.g.click(*spot)
        elif k == 0:
            click_unit(m["id"])
        else:  # on the NPC's body, above the feet: next to the character a click on the feet can land on the character
            c.g.click(fx, fy - 0.05 * k)
        c.g.click(0.04, 0.06, move_only=True)
        for _ in range(8):
            time.sleep(2)
            frame = pt.menu_frame(grab().tolist(), min_run=60)  # Akara's menu box is ~77 px wide, Charsi's ~120
            if frame:
                break
        if frame:
            break
    if not frame:
        c.shot("%s_nomenu" % who.lower())
        return "FAIL", "no menu after 3 clicks on %s" % who
    c.shot("%s_menu" % who.lower())
    c.g.click(frame[0] / 1600.0, (frame[1] + pt.MENU_TRADE_PX) / 900.0)
    time.sleep(2.5)
    opened = pt.inventory_open(c)
    c.shot("%s_trade" % who.lower())
    pt.close_panels(c)
    return ("PASS", "%s: menu, Trade window open" % who) if opened else ("FAIL", "%s: Trade did not open the trade window" % who)


def relp_town_class(cls, stamp):
    """One fresh character of the class: create, UI panels, Akara and Charsi, out of the camp and back by clicks, Save and Exit +
    reload. Returns (Ctx, name, rows, bad)."""
    import playthrough as pt
    cid = pt.CLASS_NAMES.index(cls)
    log, rows, bad = [], [], []
    c = pt.Ctx(sys.modules[__name__], cid, log)
    name = "Rl" + pt.char_name(cls, stamp)[2:]
    pt.step_create(c, name)
    if c.steps.get("create", ("",))[0] != "PASS":
        return c, name, ["create: %s" % (c.steps.get("create"),)], ["%s could not be created" % name]
    rows.append("create PASS %s" % c.steps["create"][1])
    if not relp_wait_loaded():
        rows.append("loading screen still up after 60 s (panel shots may show it)")
    for key, label in RELP_PANELS:
        g.key(key)
        time.sleep(1.5)
        c.shot("panel_%s" % label)
        g.key("esc")
        time.sleep(1.0)
    rows.append("panels c / i / t opened and shot (judged on the screenshots)")
    for npc, who in RELP_NPCS:
        st, note = relp_talk(c, npc, who, log)
        rows.append("talk %s %s" % (st, note))
        if st == "FAIL":
            bad.append(note)
        if not game_alive():
            bad.append("the game died at %s" % who)
            return c, name, rows, bad
    ok, edge, note = relp_walk_out(c, log)
    c.shot("walk_out")
    rows.append("walk out of town %s: %s" % ("PASS" if ok else "BLOCKED", note))
    if ok:
        back = relp_walk_to(c, edge[0], edge[1], lambda: c.player().get("area") == 1, c.log, budget=90)
        rows.append("walk back into town %s" % ("PASS" if back else "BLOCKED (harness `level 1`)"))
        if not back:
            goto(1)
    else:
        goto(1)
    if not game_alive():
        bad.append("the game died walking out of town")
        return c, name, rows, bad
    pt.step_reload(c, name)
    st, note = c.steps.get("reload", ("NOT RUN", ""))
    rows.append("save and reload %s %s" % (st, note))
    if st != "PASS":
        bad.append("reload: %s %s" % (st, note))
    c.shot("reloaded")
    return c, name, rows, bad


def check_relp_town():
    """Lane relprep: the release candidate's Act 1 town as a new player meets it, left clicks only (the harness reads state and
    makes no move): per class of MXL_RELP_CLASSES a fresh Normal character, the character / inventory / skill tree panels, talk to
    Akara and Charsi and open their Trade windows, walk out of the Rogue Encampment into the Blood Moor and back, Save and Exit +
    reload. Fighting, drops, the waypoint, buy / sell and death are `playthrough`'s steps."""
    classes = [x for x in (os.environ.get("MXL_RELP_CLASSES") or ",".join(RELP_CLASSES)).split(",") if x]
    stamp = int(time.time())
    for k, cls in enumerate(classes):
        mark = engine_mark()
        c, name, rows, bad = relp_town_class(cls, stamp + 7 * k)
        blocked = [r for r in rows if "BLOCKED" in r or "loading screen" in r]
        finish("relp_town %s (%s)" % (cls, name), not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""),
               mark, c.shots, rows + c.log[-200:], partial="; ".join(blocked) or None)
        if not g.game_pids():
            to_menu()


CHECKS += [("relp_town", check_relp_town)]


# lane act1start: a play tester's first hour of Act 1 on the player path (tools/act1_hour.py; docs/testing.md "Act 1 start").
# MXL_HOUR_CLASSES=sorceress,barbarian,amazon MXL_HOUR_MIN=20 (minutes per class).
def act1_hour_check():
    import act1_hour
    act1_hour.run(sys.modules[__name__])


CHECKS += [("act1_hour", act1_hour_check)]


# ---------------------------------------------------------------- lane isinside: levels.txt IsInside (bug #242, LV2-LV4)
INS_LEVELS = (84, 125, 126, 127)  # Median: 84 outdoors (Rain 1, Mud 1), 125-127 indoors; D2R reads no IsInside
INS_SPIDER_FOREST = 76  # Spider Forest: waypoint 19, Vis0 = 84 (Median's Kurast 3000 BA in the Arachnid Lair slot)
INS_TP_OBJECTS = (59, 60)  # objects.txt TownPortal / PermanentTownPortal


def ins_portal_objects(log):
    return [o for o in parse_objects(Hl("objects", log)[1]) if o["class"] in INS_TP_OBJECTS and o.get("dist", 99) <= 12]


def ins_read_tp(lvl, log, shots, shortcut):
    """A Scroll of Town Portal (`tsc`) used by a right click in the inventory; True when a town portal object stands next to the
    character afterwards. No scroll in the inventory: one is dropped on the ground and picked up by a click (named shortcut)."""
    tsc = (rc_of("tsc", RC_PAGE_INV, log) or [None])[0]
    if tsc is None:
        tsc = rc_obtain("tsc", log, shortcut)
        shortcut.append("tsc dropped on the ground in %d" % lvl)
    if tsc is None:
        return None
    before = {o["id"] for o in ins_portal_objects(log)}
    rc_use(tsc, log, shots, "ins_tp_%d" % lvl)
    time.sleep(2)
    new = [o for o in ins_portal_objects(log) if o["id"] not in before]
    log.append("town portal objects new in %d: %s" % (lvl, new))
    return bool(new)


def ins_look(lvl, label, log, shots, rain_shots=3):
    """Screenshots of an area: the look now, the automap (Tab), and `rain_shots` more 15 s apart (rain comes and goes)."""
    close_right_panel()
    time.sleep(3)
    shots.append(sh("ins_%s" % label))
    g.press("tab")
    time.sleep(1.2)
    shots.append(sh("ins_%s_automap" % label))
    g.press("tab")
    for k in range(rain_shots):
        time.sleep(15)
        shots.append(sh("ins_%s_t%d" % (label, k + 1)))
    log.append("look of %s (area %s) in %d shots" % (label, hstate()["player"].get("area"), 2 + rain_shots))


def check_ins_levels():
    """Bug #242 (LV4, LV3): what D2R does on the four levels whose IsInside Median changed. Static finding (docs/bugs.md #242): 1.14d
    loads the column into its levels record (+8) and no code reads it; D2R does not load it. So the check documents the look, the
    automap and a town portal on each level, judged by hand from the screenshots. Player path for 84: the Act III waypoint to the
    Spider Forest (set-up: the waypoint bit, character level by `xp`), then the forest's entrance warp into 84 (`level 84 warp`, the
    cave entrance's own server warp, as rp_areas). 125-127 have no entrance a player walks to (uberquest portals): `h level`."""
    mark = engine_mark()
    log, shots, rows, shortcut = [], [], [], []
    rp_ready(int(os.environ.get("MXL_INS_LEVEL") or 90))
    H("waypoint n %d set" % rp_waypoints()[INS_SPIDER_FOREST][1])
    a = rp_waypoint_to(INS_SPIDER_FOREST, log)
    rows.append("Spider Forest by waypoint: %s" % (a == INS_SPIDER_FOREST))
    if a == INS_SPIDER_FOREST:
        ins_look(INS_SPIDER_FOREST, "lv76", log, shots, rain_shots=1)
    reached = {}
    for lvl in INS_LEVELS:
        if lvl == 84 and hstate()["player"].get("area") == INS_SPIDER_FOREST:
            Hl("level 84 warp", log)
            time.sleep(6)
            how = "entrance warp from 76"
        else:
            goto(lvl, timeout=60)
            how = "h level"
            shortcut.append("%d by `h level`" % lvl)
        here = hstate()["player"].get("area")
        reached[lvl] = here == lvl
        if not reached[lvl]:
            rows.append("%d not reached (%s; area %s)" % (lvl, how, here))
            continue
        ins_look(lvl, "lv%d" % lvl, log, shots, rain_shots=3 if lvl == 84 else 1)
        tp = ins_read_tp(lvl, log, shots, shortcut)
        rows.append("%d reached (%s), town portal opened: %s" % (lvl, how, tp))
        if not game_alive():
            rows.append("the game died in %d" % lvl)
            break
    goto(1, timeout=60)
    rc_finish("ins_levels", all(reached.get(l) for l in INS_LEVELS), "; ".join(rows), mark, shots, log, shortcut,
              judged_by_hand="light, rain and mud (ins_lv84*.png against ins_lv76*.png), indoor light in ins_lv125-127*.png, "
                             "the automap shots")


CHECKS += [("ins_levels", check_ins_levels)]


# lane nmhell: Nightmare and Hell progression with a SET-UP character (tools/nmh_checks.py; docs/testing.md "Nightmare/Hell").
# MXL_CHAR=<letters> MXL_CHAR_CLASS=barbarian, in order: nmhsetup nmhnm nmhhell (MXL_NMH_STEPS picks steps).
def nmh_check_setup():
    import nmh_checks
    nmh_checks.setup(sys.modules[__name__])


def nmh_check_nightmare():
    import nmh_checks
    nmh_checks.run(sys.modules[__name__], "nightmare")


def nmh_check_hell():
    import nmh_checks
    nmh_checks.hell(sys.modules[__name__])


CHECKS += [("nmhsetup", nmh_check_setup), ("nmhnm", nmh_check_nightmare), ("nmhhell", nmh_check_hell)]

# lane hditems: HD item pictures (docs/hd-icons.md "Picture quality"). A graphics check with harness set-up (items made by `item`),
# not a player-path verification: the screenshots are judged by hand.
HDIT_CODES = [("5$a", "Chipped Amber: D2R's chipped sapphire recoloured"), ("5$e", "Perfect Amber: D2R HD recolour"),
              ("g$d", "Flawless Onyx: D2R HD recolour, grey"), ("g$e", "Perfect Onyx: D2R HD recolour, grey"),
              ("r26", "Vex Rune: D2R's own sprite"), ("a57", "Book of Akarat: D2R's Book of Skill at half size"),
              ("a59", "Laser Focus Crystal: D2R's soul stone recoloured"), ("r48", "Nih Rune: upscale, unused-index fill"),
              ("zkq", "Signet of Learning: upscale"), ("10-", "Clue Gem: upscale, unused-index fill"),
              ("qux", "Brilliant Arcane Crystal: upscale, unused-index fill"), ("l@l", "Ingredient Ring 1: upscale"),
              ("qum", "Multi Shards: upscale, unused-index fill"), ("p@p", "Ingredient Ring 4: upscale, unused-index fill"),
              ("x2x", "Sunstone of Ice: D2R classic, upscale"),
              ("yq7", "Jolly Roger (2 x 2): upscale")]


def hdit_icons():
    """Lane hditems: a dozen Median items with each kind of HD picture (D2R HD art reused / recoloured / rescaled, the new upscale,
    the palette 225-254 fill) put in the backpack with the harness (`item <code> inv`), the inventory opened and screenshot in HD
    and in legacy graphics (G). PASS: every item made, the game alive, no new engine assert; the pictures are judged by hand
    (hdit_inv_hd.png against hdit_inv_legacy.png: same item in the same cell, HD crisp, no black specks). The panel test
    (right_panel_open) reads HD coordinates, so the panel is closed in HD before the toggle and opened blind in legacy."""
    mark = engine_mark()
    log, shots, bad = [], [], []
    goto(1)
    Hl("packclear", log)
    for code, _what in HDIT_CODES:
        _ok, ln = Hl("item %s inv" % code, log)
        if not any(("code=%s " % code) in x for x in ln):
            bad.append("%s not made" % code)
    if not set_graphics("hd"):
        bad.append("graphics mode hd not reached")
    if not right_panel_open():
        g.press("i")
        time.sleep(1.5)
    shots.append(sh("hdit_inv_hd"))
    close_right_panel()
    time.sleep(1.0)
    if not set_graphics("legacy"):
        bad.append("graphics mode legacy not reached")
    time.sleep(1.5)
    g.press("i")
    time.sleep(2.0)
    shots.append(sh("hdit_inv_legacy"))
    g.press("i")
    time.sleep(1.0)
    set_graphics("hd")
    close_right_panel()
    if not game_alive():
        bad.append("the game died")
    Hl("packclear", log)
    finish("hdit_icons", not bad, "items: " + ", ".join("%s (%s)" % c for c in HDIT_CODES) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""),
           mark, shots, log, partial="the pictures in hdit_inv_hd.png / hdit_inv_legacy.png are judged by hand")


CHECKS += [("hdit_icons", hdit_icons)]

# ---------------------------------------------------------------- lanes walls / hdwalls2: HD wall scenes of Median's 17 own maps
# level -> map (tools/walls_hd.py MAPS, levels from docs/maps-hd.md); level 96 loads temple5 or temple6 (the same map in Median)
WALL_MAPS = {60: "desertpeak", 59: "cypherpunk", 95: "glados", 18: "downtown", 98: "moskvich", 126: "borgir", 125: "macumba",
             127: "charismatic", 90: "dungrm6a", 96: "temple5", 15: "caveroom4", 84: "excelsior3", 65: "belial", 13: "epicwhiners",
             14: "inarius", 116: "rockisdead"}
WALL_OFFSETS = ((0, 0), (12, 12), (-12, 12))   # subtiles from the arrival: three views per map (`place`, travel help)


def wall_visit(mode, log, shots):
    """Every map of WALL_MAPS in the current graphics mode: travel by `h level`, three screenshots, the asserts per map.
    -> {level: 'reached' | 'not reached'}."""
    seen = {}
    only = {int(v) for v in os.environ.get("MXL_WALL_LEVELS", "").split(",") if v.strip().isdigit()}  # e.g. "60,59": a re-run
    for lv, name in WALL_MAPS.items():
        if only and lv not in only:
            continue
        mark = engine_mark()
        cache_tag("wall_maps %s %d %s" % (mode, lv, name))
        st = goto(lv, timeout=60)
        p = st["player"]
        if p.get("area") != lv:
            seen[lv] = "not reached"
            log.append("%s %d %s: not reached (area %s)" % (mode, lv, name, p.get("area")))
            continue
        time.sleep(5)  # the scene and its models stream in
        x0, y0 = p.get("x"), p.get("y")
        for n, (dx, dy) in enumerate(WALL_OFFSETS):
            if n and x0 is not None:
                H("place %d %d" % (x0 + dx, y0 + dy))
                time.sleep(3)
            shots.append(sh("wall_%s_%s_%d" % (name, mode, n)))
        bad, known = engine_issues(mark)
        caches = ["AssetCache DefaultCapacity %s capacity %s path %s" % (a["default"], a["capacity"], a["path"])
                  for a in cache_new_asserts(mark)]  # which cache overflowed (bug #360)
        seen[lv] = "reached"
        log.append("%s %d %s: reached at %s,%s; asserts: %s" % (mode, lv, name, x0, y0, "; ".join(bad + known + caches) or "none"))
    return seen


def wall_maps():
    """Median's own maps (the 8 it retextured and the 9 on stock tiles), in HD (wall scenes of tools/walls_hd.py: D2R's own
    wall models on the map's wall cells) and in classic graphics (Median's own tiles); MXL_WALL_LEVELS=90,96 for some only. SHORTCUT: the harness travels there (`h level`, `place`);
    this is a graphics check, not a player path. What is judged by hand from the screenshots: walls drawn where the classic
    view has them, nothing floating or blocking a walkable floor, no black holes. FAIL on an engine assert or crash.
    SET-UP: D2R's `god 1` cheat, so the level-1 test character lives through the screenshots (Amazon Warriors kill it on
    arrival in desertpeak); the check judges graphics, not combat."""
    mark = engine_mark()
    log, shots = [], []
    enable_debug()
    cheat("god 1")
    goto(1, timeout=60)
    hd_ok = set_graphics("hd")
    hd = wall_visit("hd", log, shots) if hd_ok else {}
    goto(1, timeout=60)
    legacy_ok = set_graphics("legacy")
    classic = wall_visit("classic", log, shots) if legacy_ok else {}
    goto(1, timeout=60)
    set_graphics("hd")
    cheat("god 0")
    reached = [lv for lv in WALL_MAPS if hd.get(lv) == "reached" and classic.get(lv) == "reached"]
    wanted = [lv for lv in WALL_MAPS if lv in hd or lv in classic] or list(WALL_MAPS)
    note = "HD %s, classic %s; maps reached in both: %s" % (
        "on" if hd_ok else "NOT SET", "on" if legacy_ok else "NOT SET", ", ".join(WALL_MAPS[lv] for lv in reached) or "none")
    rc_finish("wall_maps", hd_ok and legacy_ok and len(reached) == len(wanted), note, mark, shots, log, ["travel by `h level` / `place`", "god mode (cheat god 1)"],
              judged_by_hand="the walls in wall_<map>_hd_*.png against wall_<map>_classic_*.png")


CHECKS += [("wall_maps", wall_maps)]

# ---- lane tints: per-TransLvl colours (tools/hd_translvl.py) and gradient-tinted effects (tools/hd_recolour.py) -----------
def tint_class(mid):
    """The monster class (row of the built monstats.txt) of a monstats Id, or None."""
    return next((i for i, r in enumerate(table("monstats")) if r.get("Id") == mid), None)


def tint_reports():
    """(hd_translvl.json, the recolours of hd_recolour.json) of the build in work/mod (what install_mod.py installed)."""
    mod = os.path.dirname(os.path.dirname(os.path.dirname(EXCEL)))
    with open(os.path.join(mod, "hd_translvl.json"), encoding="utf-8") as f:
        levels = json.load(f)
    with open(os.path.join(mod, "hd_recolour.json"), encoding="utf-8") as f:
        recolours = json.load(f)["recolours"]
    return levels, recolours


def tint_pairs(levels):
    """[(level-0 Id, filled-level Id, unit, level)] of hd_translvl.json."""
    return [(e["level0"], x["ids"][0], u, lvl) for u, e in sorted(levels.items()) for lvl, x in sorted(e["levels"].items())
            if e.get("level0") and x.get("ids")]


def tint_missile_pairs(recolours, known=None):
    """[(tinted row, a row drawing the untinted source effect, recoloured effect)] of the missile tints. `known`: the row
    names of the built missiles.txt; the source is the first of `src_rows` (Median rows on the source effect) and then
    `src_row` (the D2R row it came from) that the table has."""
    out = []
    for r in recolours:
        if r["kind"] != "missile" or not r["rows"]:
            continue
        cands = [*r.get("src_rows", []), *([r["src_row"]] if r.get("src_row") else [])]
        src = next((c for c in cands if known is None or c in known), None)
        if src:
            out.append((r["rows"][0], src, r["to"]))
    return out


TINT_AREAS = (2, 3, 4, 5, 6, 27, 29, 32, 35)  # Blood Moor and Act 1 waypoint areas: one per monster pair, so corpses of pairs never mix


def tint_monsters(pair, log, shots, missing):
    """A level-0 monster (screen right) and one of the filled level (screen left) of a pair: shot alive in HD, killed, the
    corpses shot in HD and in legacy graphics. Returns how many were spawned."""
    low, high, u, lvl = pair
    toggle = [set_graphics("hd")]
    px, py = player_xy()
    ids = []
    for (dx, dy), mid in (((3, -3), low), ((-3, 3), high)):
        cls = tint_class(mid)
        if cls is None:
            missing.append(mid)
            continue
        _, sp = Hl("spawn %d 1 %d %d" % (cls, px + dx, py + dy), log)
        m = first(sp, r"id=(\d+)")
        if m:
            ids.append(m)
    time.sleep(0.7)
    shots.append(sh("tint_mon_%s_L%s_alive_hd" % (u, lvl)))
    for m in ids:
        H("kill %s" % m)
    time.sleep(2.5)
    for mode in ("hd", "legacy"):
        toggle.append(set_graphics(mode))
        shots.append(sh("tint_mon_%s_L%s_%s" % (u, lvl, mode)))
    return len(ids), all(toggle)


def tint_fire(rows, dx, dy, log):
    """Fire the first row of `rows` the table has towards (dx, dy) by the harness `missile` at skill level 10. Returns
    (how, ok). (Giving the player Median's monster skills by `setskill` to cast them asserted nDesc < skillDescTbl.size()
    and crashed the game: run checks-20261029-032744-s2; not done.)"""
    mid = next((missile_id(r) for r in rows if missile_id(r) is not None), None)
    if mid is None:
        return "none", False
    ok, _ = Hl("missile %d %d %d 0 10" % (mid, dx, dy), log)
    return "missile %d" % mid, ok


def tint_burst(name, shots, n=5, gap=0.15):
    for i in range(n):
        shots.append(sh("%s_%d" % (name, i)))
        time.sleep(gap)


def check_tint_hd():
    """Seen with the harness (not a player path). Monsters: per filled TransLvl, a level-0 monster of the same HD unit (screen
    right) and one of the filled level (screen left) in an Act 1 area of their own: shot alive in HD, then killed and the
    corpses shot in HD and in legacy graphics (G) (`tint_mon_<unit>_L<level>_*`). Missiles: each gradient-tinted effect
    (towards screen right) beside the untinted source effect (screen left) by the harness `missile`, a burst of 5 shots per mode (`tint_fx<n>_<effect>_<mode>_<i>`). The colours are judged by eye."""
    mark = engine_mark()
    log, shots, missing, how = [], [], [], []
    levels, recolours = tint_reports()
    pairs = tint_pairs(levels)
    fx = [r for r in recolours if r["kind"] == "missile" and r["rows"]]
    spawned, fired, toggles = 0, 0, []
    with Tank():
        for k, pair in enumerate(pairs):
            goto(TINT_AREAS[k % len(TINT_AREAS)])
            n, ok = tint_monsters(pair, log, shots, missing)
            spawned += n
            toggles.append(ok)
        goto(2)
        for mode in ("hd", "legacy"):
            toggles.append(set_graphics(mode))
            for n, r in enumerate(fx):
                h1, ok1 = tint_fire(r["rows"], 6, -6, log)
                h2, ok2 = tint_fire([*r.get("src_rows", []), *([r["src_row"]] if r.get("src_row") else [])], -6, 6, log)
                fired += int(ok1) + int(ok2)
                if mode == "hd":
                    how.append("%s: %s / %s" % (r["to"], h1, h2))
                tint_burst("tint_fx%02d_%s_%s" % (n, r["to"], mode), shots)
                time.sleep(2.5)
        toggles.append(set_graphics("hd"))
    want_mon, want_fx = 2 * len(pairs), 4 * len(fx)
    ok = spawned == want_mon and all(toggles) and not missing
    note = ("%d level pairs (%s): %d of %d monsters spawned (level 0 right, filled level left); %d missile tints, %d of %d "
            "fired (tinted right / source left: %s); graphics toggles ok %s; not in the tables: %s" % (
                len(pairs), ", ".join("%s L%s" % (u, lvl) for _a, _b, u, lvl in pairs), spawned, want_mon, len(fx), fired,
                want_fx, "; ".join(how), all(toggles), missing or "none"))
    finish("tint_hd", ok, note, mark, shots, log, partial="the colours are judged by eye from the shots (harness evidence)")


CHECKS += [("tint_hd", check_tint_hd)]


# lane nmhell2: hit log on Andariel / Duriel Nightmare, the difficulty dialog per character card, boss kills with a stronger build.
def nmh_check_hitlog():
    import nmh_checks
    nmh_checks.hitlog(sys.modules[__name__])


def nmh_check_dialog():
    import nmh_checks
    nmh_checks.dialog(sys.modules[__name__])


def nmh_check_kill():
    import nmh_checks
    nmh_checks.kill(sys.modules[__name__])


CHECKS += [("nmhhitlog", nmh_check_hitlog), ("nmhdialog", nmh_check_dialog), ("nmhkill", nmh_check_kill)]


# lane uiplus (bugs #488 / #489): the level-up + buttons, 1600 x 900 client pixels per graphics mode (stat button, skill button),
# measured on the shots of checks-20261029-155405-s4 (docs/bugs.md #488): classic left of the stamina bar / right of the belt (D2R's
# hudpanel.json StatUp / SkillUp, 1.13's place), HD D2R's floating buttons above the skill bar
LVLUP_XY = {"legacy": ((532, 866), (1068, 866)), "hd": ((388, 683), (1205, 683))}


def lvlup_points(log):
    _, lines = Hl("stat player 4", log)
    stats = stat_of(lines)
    _, lines = Hl("stat player 5", log)
    return stats, stat_of(lines)


def lvlup_panel_change(before, after, which):
    """Mean pixel change of the half where the button's panel opens (stat: left, skill: right), rows 100-700 of the client."""
    import numpy as np
    box = (200, 100, 800, 700) if which == "stat" else (800, 100, 1400, 700)
    a = np.asarray(before.convert("RGB").crop(box), dtype=np.int16)
    b = np.asarray(after.convert("RGB").crop(box), dtype=np.int16)
    return float(np.abs(a - b).mean())


def lvlup_click(mode, which, xy, log, shots):
    """A click on one + button and a shot (`lvlup_<mode>_<which>_clicked`). Returns True when the half of the screen where its
    panel opens changed (the panel opened; it is closed again by Esc), False when the click did nothing, None without a spot."""
    if xy[0] is None:
        return None
    before = g.grab_client(g.need_window())
    g.click(xy[0] / 1600, xy[1] / 900)
    time.sleep(1.2)
    shots.append(sh("lvlup_%s_%s_clicked" % (mode, which)))
    change = lvlup_panel_change(before, g.grab_client(g.need_window()), which)
    log.append("click %s %s at %s: panel area change %.1f" % (mode, which, xy, change))
    if change < 20:
        return False
    g.key("esc")
    time.sleep(0.8)
    return True


def check_lvlup_ui():
    """Bugs #488 / #489 (lane uiplus): the control panel's level-up + buttons. In town: unspent points set to 0 (harness set-up),
    a shot per graphics mode (`lvlup_<mode>_before`, the unlit buttons), then, in legacy graphics, a level-up by D2R's own award
    (`xp`), and per mode legacy, HD, legacy again (after the G round trip: `legacy2`) a shot (`lvlup_<mode>_points`) and a click on
    each button (LVLUP_XY; `MXL_LVLUP_XY=lx,ly,lx2,ly2,hx,hy,hx2,hy2` overrides) with its shot (`..._clicked`). A click counts when
    the half of the screen where its panel opens changed. PASS: the level went up, stat and skill points are there and every click
    opened its panel. `MXL_LVLUP_SETSTAT=1` adds a diagnosis shot with points set by the harness in legacy (`lvlup_legacy_setstat`);
    `MXL_LVLUP_PROBE=1` logs harness `lvlbtn` (the two widgets' disabled byte, lit mask, Update / Draw counts) around the level-up,
    then runs their Update once by hand (`lvlup_legacy_probe` / `_forced`). The log ends with the plugin's `lvlupui` line."""
    mark = engine_mark()
    log, shots = [], []
    xy = dict(LVLUP_XY)
    env = os.environ.get("MXL_LVLUP_XY")
    if env:
        v = [int(x) for x in env.split(",")]
        xy = {"legacy": ((v[0], v[1]), (v[2], v[3])), "hd": ((v[4], v[5]), (v[6], v[7]))}
    if hstate()["player"].get("level", 0) >= 120:  # the slot's own character is often at the cap: a Sorceress of the check's own
        g.CHAR_NAME = "UiPlusSor"
        if not switch_character("UiPlusSor", "sorceress", 1):
            return finish("lvlup_ui", False, "no character below the level cap", mark, shots, log)
    goto(1)
    time.sleep(3.0)  # the area's loading screen
    close_right_panel()
    if any(lvlup_points(log)):  # harness set-up: no unspent points, so the shots before show the unlit buttons
        setstat("player", 4, 0)
        setstat("player", 5, 0)
    p0 = lvlup_points(log)
    for mode in ("hd", "legacy"):  # the level-up below happens in legacy graphics, as the player of #488 plays
        set_graphics(mode)
        time.sleep(1.0)
        shots.append(sh("lvlup_%s_before" % mode))
    if os.environ.get("MXL_LVLUP_SETSTAT"):  # diagnosis: unspent points set by the harness, no level-up, in legacy graphics
        setstat("player", 4, 5)
        setstat("player", 5, 2)
        time.sleep(1.5)
        shots.append(sh("lvlup_legacy_setstat"))
        setstat("player", 4, 0)
        setstat("player", 5, 0)
        time.sleep(1.0)
    probe = bool(os.environ.get("MXL_LVLUP_PROBE"))  # diagnosis: harness `lvlbtn` (the widgets' state, Update / Draw counts)
    if probe:
        Hl("lvlbtn count", log)
        Hl("lvlbtn", log)
    lvl0 = hstate()["player"].get("level", 0)
    lvl, amount = lvl0, 50000
    for _ in range(40):
        if lvl > lvl0:
            break
        r = parse_xp(Hl("xp %d" % amount, log)[1])
        lvl = r.get("level", lvl)
        amount = min(amount * 2, 2000000000)
    time.sleep(1.5)
    p1 = lvlup_points(log)
    if probe:
        Hl("lvlbtn", log)
        time.sleep(2.0)
        Hl("lvlbtn", log)
        shots.append(sh("lvlup_legacy_probe"))
        Hl("lvlbtn update", log)
        time.sleep(1.0)
        shots.append(sh("lvlup_legacy_forced"))
    clicked = {}
    for mode in ("legacy", "hd", "legacy"):  # the second legacy pass: after a G round trip (the widgets made again)
        tag = mode if mode not in clicked else mode + "2"
        set_graphics(mode)
        time.sleep(1.0)
        shots.append(sh("lvlup_%s_points" % tag))
        if probe:
            Hl("lvlbtn", log)
        clicked[tag] = [lvlup_click(tag, which, b, log, shots) for which, b in zip(("stat", "skill"), xy[mode])]
    set_graphics("hd")
    if probe:
        Hl("lvlbtn count off", log)
    log.append("plugin: " + (mxl_part(mxl_text().splitlines(), "lvlupui") or "no lvlupui line"))
    ok = lvl > lvl0 and (p1[0] or 0) > 0 and (p1[1] or 0) > 0 and all(all(v) for v in clicked.values())
    finish("lvlup_ui", ok, "level %s -> %s; stat / skill points %s -> %s; panel opened by the clicks (stat, skill) %s" % (
        lvl0, lvl, p0, p1, clicked), mark, shots, log, partial="lit buttons and their place are judged by eye from the shots")


CHECKS += [("lvlup_ui", check_lvlup_ui)]


def unknown_checks(only):
    """Names in a check list that are not in CHECKS ('-' is the internal 'run nothing' marker)."""
    known = {name for name, _ in CHECKS}
    return [n for n in only or [] if n != "-" and n not in known]


def run_all(only=None):
    global WD
    bad_names = unknown_checks(only)
    if bad_names:  # before the lock, the game and the run folder: a misspelt name used to be skipped without a word
        print("unknown check name(s): %s (not in the CHECKS list at the end of tools/game_checks.py)" % ", ".join(bad_names))
        return 2
    new_run()
    if not lock():
        print("game lock held for 30 min, giving up")
        return 2
    WD = Watchdog()
    WD.start()
    try:
        backup_saves()
        if g.game_pids() and not ATTACH["v"]:
            g.stop()
            time.sleep(2)
        g.snapshot_marks()
        if not to_menu():
            add("start game", "BLOCKED", "game did not reach the main menu")
        elif not enter_initial_character():
            add("enter game", "BLOCKED", "the character did not enter the game")
        else:
            try:
                notes = clean_start_state("the first check", report_dead=True)
                if notes:
                    add("Test character start state (an earlier run saved it like this)", "REVIEW", "; ".join(notes))
            except Exception as e:
                add("Test character start state", "BLOCKED", "cannot be repaired: %r" % (e,))
                only = ["-"]  # no check runs on a character that cannot be put in a clean state
            p0 = hstate()["player"]
            gfx = os.environ.get("MXL_GRAPHICS")  # "legacy": the whole run in legacy graphics (G), as a player who plays that way
            if gfx:
                goto(1)
                add("Graphics mode for the run: %s" % gfx, "INFO" if set_graphics(gfx) else "BLOCKED",
                    "graphics_mode() reads %s" % graphics_mode(), [sh("graphics_%s" % gfx)])
            if os.environ.get("MXL_ASSERT_TRACE"):  # every engine assert of the run gets its call chain in mxl2012-core.log (harness `asserttrace`)
                H("asserttrace on")
            cache_poll_start()
            for name, fn in CHECKS:
                if only and name not in only:
                    continue
                cache_tag(name)
                try:
                    guard()
                    notes = clean_start_state(name)
                    if notes:
                        add("Start state before %s (left by the check before)" % name, "REVIEW", "; ".join(notes))
                    fn()
                except Exception as e:
                    add(name, "BLOCKED", "script error: %r" % (e,))
                    if WD.abort:
                        break
            try:  # the test character is saved on exit: nothing may stay on the cursor
                release_held_item()
            except Exception:
                pass
    finally:
        WD.stop_flag = True
        try:
            g.stop()
        finally:
            unlock()
            r = g.logscan()
            write_report(cache_poll_stop() + "## Real input watchdog\n\n" + WD.summary() + "\n\n## logscan\n\n```\n" + r["text"] + "\n```")
            print(WD.summary())
    return 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    if a[0] == "all":
        g.game_slots.require_present(g.SLOT, "game_checks", g.GAME_DIR)  # e.g. slot 4 or 5 before its folder was copied
        sys.exit(run_all(a[1:] or None))
    print(__doc__)


# lane potions191: bug #191, each item spell drunk on its own (asserttrace counts every engine assert per drink)
# (code, expected: "used" | "kept", cure set-up: None | (monster class, skill name, monmode, state names the drink must remove))
POT_CODES = [("yps", "used", ("gnat1", "Poison Flash", 6, ("poison",))),
             ("wms", "used", ("shadowwarrior", "Ice Lance", 9, ("cold", "freeze"))),
             ("ey9", "used", None), ("elx", "used", None), ("vps", "used", None), ("hp1", "used", None),
             ("mp1", "used", None), ("rvs", "used", None), ("hrb", "kept", None), ("eo7", "kept", None)]


def pot_asserts():
    _ok, lines = H("asserttrace count", 8)
    m = re.search(r"count (\d+)", " ".join(lines))
    return int(m.group(1)) if m else None


def pot_assert_lines(n):
    if n <= 0:
        return []
    _ok, lines = H("asserttrace show %d" % min(n, 32), 10)
    return [ln.split(" | ")[0][:110] for ln in lines if ln.startswith("assert #")]


def pot_state_ids(names):
    st = table("states")
    return {i: n for i, r in enumerate(st) for n in names if r.get("state") == n}


def pot_inflict(setup, log):
    """Harness set-up (not the action judged): a monster that owns the skill uses it on the character until one of the states is on.
    Returns (state ids found on the player, note)."""
    cls, skill, mode, names = setup
    ids = pot_state_ids(names)
    sk = row_of("skills", "skill", skill)
    if sk is None or not ids:
        return set(), "no skill %s / states %s in the built tables" % (skill, names)
    sid = int(sk.get("*Id") or table("skills").index(sk))
    row = next((i for i, r in enumerate(table("monstats")) if r.get("Id") == cls), None)  # `spawn` takes the row number
    if row is None:
        return set(), "no monster %s in the built monstats" % cls
    for area in (1, 2):
        goto(area)
        px, py = player_xy()
        _, sp = Hl("spawn %d 1 %d %d" % (row, px + 3, py), log)
        mid = first(sp, r"id=(\d+)")
        if mid is None:
            continue
        for _ in range(4):
            Hl("mcast %d %d unit %s" % (sid, mode, mid), log)
            time.sleep(1.5)
            on = set(server_states(log)) & set(ids)
            if on:
                H("kill %s" % mid)
                goto(1)
                time.sleep(1.0)
                on = set(server_states(log)) & set(ids)  # a cold / freeze may wear off on the way back
                return on, "%s by %s (%s) in area %d" % ("/".join(ids[i] for i in sorted(on)) or "worn off", cls, skill, area)
        H("kill %s" % mid)
    goto(1)
    return set(), "%s never put %s on the character" % (cls, names)


def pot_use_check():
    """Bug #191 (lane potions191): each potion / elixir with an item spell, alone, picked up from the ground into the backpack and
    drunk by a right click (the player's own use), `asserttrace` counting every engine assert of that one drink (D2RLoader's log
    names only the first of a kind per launch). Before the Antidote (`yps`) and the Thawing Potion (`wms`) a monster that owns a
    poison / cold skill uses it on the character (harness set-up `spawn` + `mcast`, the character stays mortal); the drink must take
    the state off. PASS: no assert on any drink, the `used` codes used up (cures done), the `kept` codes (pSpell 0: hrb, eo7, as
    1.13c's handler refused them) stay. MXL_POT_ONLY=<code,...> runs a subset."""
    mark = engine_mark()
    log, rows, bad, shots = [], [], [], []
    only = set(filter(None, (os.environ.get("MXL_POT_ONLY") or "").split(",")))
    rp_be("barbarian")
    H("packclear")
    _, ln = H("asserttrace on")
    log.append("asserttrace on: %s" % " ".join(ln))
    for code, expect, setup in POT_CODES:
        if only and code not in only:
            continue
        r = row_of("misc", "code", code) or {}
        spell = "pSpell %s state %s cstates %s/%s len %s" % (r.get("pSpell"), r.get("state") or "-", r.get("cstate1") or "-",
                                                             r.get("cstate2") or "-", r.get("len") or "-")
        rp_packclear(log)
        cured, note = set(), ""
        if setup:
            cured, note = pot_inflict(setup, log)
            if not cured:
                bad.append("%s: set-up failed (%s)" % (code, note))
        if not right_panel_open():
            g.press("i")
            time.sleep(1.0)
        iid = rp_ground_item(code, log)
        if iid is None or not rp_pickup(iid, log):
            bad.append("%s: not picked up" % code)
            continue
        if held_item():
            Hl("pkt 18 " + _le(iid, 2, 0, 0), log)
            time.sleep(0.5)
        it = rp_item_line(iid)
        if it is None:
            bad.append("%s: not in the backpack" % code)
            continue
        a0 = pot_asserts()
        g.click(*rp_inv_xy(it["x"], it["y"]), button="right")
        time.sleep(1.5)
        a1 = pot_asserts()
        gone = rp_item_line(iid) is None
        left = set(server_states(log)) & cured
        n = (a1 - a0) if a0 is not None and a1 is not None else None
        msgs = pot_assert_lines(n or 0)
        rows.append("%s (%s): %s, asserts %s%s%s" % (
            code, spell, "used up" if gone else "kept", n if n is not None else "?",
            " %s" % msgs if msgs else "", "; cure: %s -> %s" % (note, "still on %s" % sorted(left) if left else "removed") if setup else ""))
        if n is None or n > 0:
            bad.append("%s: %s engine asserts" % (code, n))
        if gone != (expect == "used"):
            bad.append("%s: %s, expected %s" % (code, "used up" if gone else "kept", expect))
        if setup and cured and left:
            bad.append("%s: %s still on after the drink" % (code, sorted(left)))
        if not game_alive():
            bad.append("the game died after %s" % code)
            break
        g.key("esc")
        time.sleep(0.5)
    shots.append(sh("pot_use_end"))
    close_right_panel()
    finish("pot_use", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-300:])


CHECKS += [("pot_use", pot_use_check)]



# --- lane vendors3: every vendor on the player path (docs/testing.md "Vendors, lane vendors3") ------------------------------------
# Walk there with left clicks only (no `moveto` / `move` / `interact`), talk by clicking the NPC, then rp_vendor_round's Trade, buy,
# sell back and gamble, and Repair at the smiths. SET-UP (coordinator rule "PLAYER PATH vs SET-UP"): `xp` level, the town waypoint
# bits, act-open quest words (rp_open_acts), Prison of Ice done (word 37) for Anya in Harrogath, `gold set`, for the Repair a
# Circlet worn down by natural hits of harness-spawned Zombies outside the town (ven_wear).
VEN_NPCS = {1: [(154, "Charsi"), (148, "Akara"), (147, "Gheed")],
            40: [(177, "Drognan"), (178, "Fara"), (199, "Elzix"), (202, "Lysander")],
            75: [(255, "Ormus"), (254, "Alkor"), (252, "Asheara"), (253, "Hratli")],
            109: [(511, "Larzuk"), (513, "Malah"), (512, "Anya")]}
VEN_REPAIR = {"Charsi", "Fara", "Hratli", "Larzuk"}
VEN_DIRS = [(round(math.cos(a * math.pi / 8), 3), round(math.sin(a * math.pi / 8), 3)) for a in range(16)]
VEN_CELL, VEN_STEP = 6, 9      # the click route's map grid and click leg (`state` units; a 9-unit leg stays on screen)
VEN_REPAIR_ALL = (490, 640)    # the repair vendor panel's Repair All button (HD; (190, 640) is Repair one item: a hammer cursor)
VEN_REFUSAL_OK = (490, 630)    # Continue under the panel's "I cannot complete that request."
VEN_HEAD_SLOT = (1262 / 1600, 140 / 900)  # the head slot of the inventory panel (HD)
VEN_WEAR_ITEM = "k21"          # Circlet (Grade 6): maximum durability 10, cost 37815 (one point is a visible repair price)
VEN_WEAR_AREA = {1: 2, 40: 41, 75: 76, 109: 110}  # the area next to each town, for the wear set-up
VEN_ANYA_WORD = 37             # Prison of Ice: Anya stands in Harrogath once it is done
VEN_HRATLI_WORD = 16           # Act 3 intro: Hratli leaves the pier for his house once it is done
# Where an NPC stands while it is out of `state`'s view (the route's target until it is in view): Lut Gholein and the Docks from
# D2R's town maps (lut2 / docktown3 presets + the level origin measured from Fara, Lysander, Ormus, Alkor), the code-placed ones
# (Hratli, Larzuk, Anya) from `moveto nearest` in run ven-probe-s3 (2026-10-29). Hratli stands on the pier by the waypoint
# until the Act 3 intro (quest word 16) is done, then at his house in the north-east (reached the long way round,
# bug #434: ven_planned_walk)
VEN_HOME = {177: (5090, 5022), 178: (5117, 5076), 199: (5028, 5098), 202: (5115, 5103), 252: (5034, 5096), 253: (5219, 5038),
            254: (5084, 5014), 255: (5119, 5091), 511: (5142, 5044), 512: (5106, 5115), 513: (5077, 5024)}


def ven_npc_spot(npc, log=None):
    """(x, y, dist) of the NPC: its unit when `state` lists it (within 40), else VEN_HOME, its map preset (`presets 1`) or a
    harness look-up (dist None)."""
    m = next((m for m in hstate()["mons"] if m.get("class") == npc), None)
    if m:
        return m["mx"], m["my"], m.get("dist", 99)
    if npc in VEN_HOME:
        return VEN_HOME[npc] + (None,)
    _ok, lines = H("presets 1")
    for ln in lines:
        mm = re.match(r"preset type=1 class=(\d+) x=(-?\d+) y=(-?\d+)", ln)
        if mm and int(mm.group(1)) == npc:
            return int(mm.group(2)), int(mm.group(3)), None
    # the Rogue Encampment is laid out anew each game and Akara's tent has no preset: look the position up with the harness
    # (`moveto nearest` starts a server walk; the `move` to the character's own spot stops it at once) and keep it
    spots = STATE.setdefault("ven_spots", {})
    area = hstate()["player"].get("area")
    if (area, npc) not in spots:
        p = hstate()["player"]
        to = parse_moveto(H("moveto nearest %d" % npc)[1])
        H("move %d %d" % (p.get("x", 0), p.get("y", 0)))
        if to:
            spots[(area, npc)] = (to["x"], to["y"])
            if log is not None:
                log.append("ven_npc_spot: %d looked up at %d,%d (no preset, out of view)" % (npc, to["x"], to["y"]))
    if (area, npc) in spots:
        return spots[(area, npc)] + (None,)
    if log is not None:
        log.append("ven_npc_spot: %d neither in view, a preset nor loaded (%d preset lines)" % (npc, len(lines)))
    return None


def ven_wait_still(timeout=7.0):
    """The character's position once it stopped moving after a click."""
    last, t0 = None, time.time()
    while time.time() - t0 < timeout:
        time.sleep(0.6)
        p = hstate()["player"]
        xy = (p.get("x", 0), p.get("y", 0))
        if xy == last:
            return xy
        last = xy
    return last


def ven_menu_npc():
    """Class of the NPC whose menu is open, None when no menu is open."""
    ok, lines = g.hcmd("menu list", 5)
    return first(lines, r"menu npc id=\d+ class=(\d+)") if ok else None


def ven_route_pick(c, edges, tried, h, pred):
    """The next leg of the click route: Dijkstra over the legs the clicks really walked (cell -> [(dir, cell)]) from cell c,
    then the visited cell + untried direction with the least (way there + leg + straight distance after it). Returns
    (first dir to click, cell it was aimed from) or None when nothing is left to try."""
    import heapq
    dist, first_k, heap = {c: 0.0}, {c: None}, [(0.0, c)]
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist.get(u, 1e18):
            continue
        for k, v in edges.get(u, []):
            nd = d + VEN_STEP
            if nd < dist.get(v, 1e18):
                dist[v], first_k[v] = nd, first_k[u] if first_k[u] is not None else k
                heapq.heappush(heap, (nd, v))
    best = None
    for u, d in dist.items():
        for k in range(len(VEN_DIRS)):
            if (u, k) in tried:
                continue
            v = d + VEN_STEP + h(pred(u, k))
            if best is None or v < best[0]:
                best = (v, u, k)
    if best is None:
        return None
    _v, u, k = best
    return (k if u == c else first_k[u]), u == c


def ven_click_route(npc, log, budget=120, reach=12):
    """Walk to the NPC as a player does: left clicks on the ground, one leg of VEN_STEP in one of 16 directions at a time. The
    clicks build a map of the legs they really walked (cell -> cell on a VEN_CELL grid; a click into a wall or the Docks' water
    ends short or nowhere); each step walks back along known legs to the visited cell whose next untried leg looks closest to
    the NPC, then tries that leg (real-time search with backtracking: lane realpath2's server path stopped at Drognan's and
    Larzuk's walls, a straight-distance walk kept clicking at the end of the Docks' pier for 110 clicks, run ven-probe-s3).
    A click that opens another NPC's menu or a panel is undone (Esc / close) and that leg is not tried again.
    Returns (reached, clicks, note)."""
    edges, tried = {}, set()

    def cell(x, y):
        return (int(x) // VEN_CELL, int(y) // VEN_CELL)

    def centre(k):
        return k[0] * VEN_CELL + VEN_CELL / 2, k[1] * VEN_CELL + VEN_CELL / 2
    first_spot, explore = None, 0
    for n in range(budget):
        spot = ven_npc_spot(npc, log)
        if spot is None:
            # not loaded yet (Akara's tent: the Rogue Encampment has no preset for her and is laid out anew each game): walk
            # the legs round the arrival by clicks, as a player looks round, until the server knows where she stands
            if explore >= 4 * len(EXPLORE_LEGS):
                return False, n, "no NPC position after %d exploring clicks" % explore
            p = hstate()["player"]
            lx, ly = EXPLORE_LEGS[(explore // 4) % len(EXPLORE_LEGS)]
            f = VEN_STEP / math.hypot(lx, ly)
            g.click(*rp_screen_xy(p.get("x", 0) + lx * f, p.get("y", 0) + ly * f, p))
            ven_wait_still()
            if ven_menu_npc() is not None:
                close_menu()
            if trade_panel_open():
                rp_close_trade()
            explore += 1
            continue
        tx, ty, d = spot
        first_spot = first_spot or (tx, ty)
        if d is not None and d <= reach:
            return True, n, "in view at %d after %d clicks" % (d, n)
        talking = ven_menu_npc()
        if talking == npc:
            return True, n, "a click on the way talked to it"
        p = hstate()["player"]
        px, py = p.get("x", 0), p.get("y", 0)
        c = cell(px, py)

        def h(k, tx=tx, ty=ty):
            x, y = centre(k)
            return math.hypot(x - tx, y - ty)

        def pred(u, k):
            x, y = centre(u)
            return cell(x + VEN_DIRS[k][0] * VEN_STEP, y + VEN_DIRS[k][1] * VEN_STEP)
        pick = ven_route_pick(c, edges, tried, h, pred)
        if pick is None:
            return False, n, "every leg tried (%d cells reached)" % len(edges)
        k, new = pick
        qx, qy = px + VEN_DIRS[k][0] * VEN_STEP, py + VEN_DIRS[k][1] * VEN_STEP
        g.click(*rp_screen_xy(qx, qy, p))
        nx, ny = ven_wait_still() or (px, py)
        other = ven_menu_npc()
        if other is not None and other != npc:  # the leg's click talked to someone else: cancel, never that leg again
            close_menu()
            tried.add((c, k))
            continue
        if trade_panel_open():  # it hit a waypoint or a stash: close it, as a player would
            rp_close_trade()
            tried.add((c, k))
            continue
        tried.add((c, k))
        d2 = cell(nx, ny)
        if d2 == c:  # a known leg that does not move any more (an NPC in the way, another start inside the cell): forget it
            edges[c] = [e for e in edges.get(c, []) if e[0] != k]
        elif (k, d2) not in edges.setdefault(c, []):
            edges[c].append((k, d2))
        if n % 10 == 0:
            log.append("ven_click_route %d: click %d at %d,%d -> %d,%d (npc %d,%d)%s" % (
                npc, n, px, py, nx, ny, tx, ty, "" if new else " (back along known legs)"))
    return False, budget, "click budget spent (npc first seen at %s, %d cells reached)" % (first_spot, len(edges))


def ven_click_talk(npc, log, tries=8):
    """Talk as a player does: a left click on the NPC (D2R walks up first); returns the menu lines or None."""
    close_menu()
    for t in range(tries):
        m = next((m for m in hstate()["mons"] if m.get("class") == npc), None)
        if m is None:
            log.append("ven_click_talk: %d out of view" % npc)
            return None
        fx, fy = rp_screen_xy(m["mx"], m["my"])
        g.click(fx, fy - 30 / 900)  # the body, above the feet
        menu = wait_menu(6 if t < tries - 1 else 20)
        if menu is not None:
            return menu
        if trade_panel_open():
            rp_close_trade()
    return None


# Legs of the long way round to an NPC the click search does not find, measured on the walk that reached it: Hratli's house in
# the Kurast Docks, east along the south pier, north through the east market (run checks-20261029-203319-s1, bug #434)
VEN_VIA = {253: [(5173, 5165), (5172, 5131), (5217, 5135), (5219, 5082)]}


def ven_planned_walk(npc, town, log, rounds=4):
    """From the town arrival, left clicks to the NPC on paths planned on the game's own walk collision (relp_walk_to,
    `walkmap`): through its VEN_VIA legs, then a few rounds to its spot. Hratli's house in the Kurast Docks is reached only the
    long way round, which the click search does not find, bug #434 (lane bugsweep). Returns whether it is in view."""
    import playthrough as pt
    spot = ven_npc_spot(npc, log)
    if spot is None:
        return False
    if town in VEN_WEAR_AREA:  # a stop deep in the market walls plans no way out (run checks-20261029-204457-s1)
        goto(VEN_WEAR_AREA[town])
        goto(town)
    c = pt.Ctx(sys.modules[__name__], 0, log)
    seen = lambda: npc_within(npc, 12)  # noqa: E731
    for vx, vy in VEN_VIA.get(npc, []):
        near = lambda vx=vx, vy=vy: seen() or abs(c.player()["x"] - vx) + abs(c.player()["y"] - vy) <= 6  # noqa: E731
        relp_walk_to(c, vx, vy, near, log, budget=90)
    for _ in range(rounds):
        if relp_walk_to(c, spot[0], spot[1], seen, log, budget=240):
            return True
    return seen()


def ven_reach_and_talk(npc, nm, log, paths):
    """The click route, then the click talk; `paths[nm]` says how it went. Returns the menu or None. An NPC with measured legs
    (VEN_VIA) or reached by the planned walk before goes by the planned walk first (the click routes spend ~8 minutes each
    failing on Hratli, bug #434); the click routes stay its fallback the first time."""
    if npc_within(npc, 8):
        paths.setdefault(nm, "standing next to it")
        ok = True
    else:
        town = hstate()["player"].get("area")
        ok = False
        planned_before = npc in STATE.get("ven_planned", ())
        if planned_before or npc in VEN_VIA:
            ok = ven_planned_walk(npc, town, log)
            paths[nm] = paths.get(nm, "") + "; " * (nm in paths) + "%swalk planned on `walkmap`: %s" % (
                "again by the " if planned_before else "", "in view" if ok else "not reached")
        if not ok and not planned_before:
            ok, _clicks, note = ven_click_route(npc, log)
            paths[nm] = paths.get(nm, "") + "; " * (nm in paths) + "click route: %s" % note
            if not ok and town in VEN_WEAR_AREA:
                # once more from the town's arrival spot (harness warp out and back: set-up); Hratli's route from Asheara's corner
                # of the Docks spent its clicks in the market's walls, run checks-20261029-061635-s3
                goto(VEN_WEAR_AREA[town])
                goto(town)
                ok, _clicks, note = ven_click_route(npc, log)
                paths[nm] += "; again from the town arrival: %s" % note
            if not ok and npc not in VEN_VIA:
                ok = ven_planned_walk(npc, town, log)
                paths[nm] += "; walk planned on `walkmap`: %s" % ("in view" if ok else "not reached")
        if ok and "walkmap`: in view" in paths[nm]:
            STATE.setdefault("ven_planned", set()).add(npc)
    if not ok:
        STATE.setdefault("ven_shots", []).append(sh("ven_noreach_%s" % nm.lower()))
        return None
    menu = ven_click_talk(npc, log)
    if menu is None:
        paths[nm] = paths.get(nm, "") + "; the click talk opened no menu"
    return menu


def ven_wear(town, log, want=8, timeout=200):
    """SET-UP for the Repair: wear the Circlet (VEN_WEAR_ITEM, maximum durability 10) as the only armour, step out of town (the
    harness warp) and let natural hits wear it (harness-spawned Zombies, VEN_WEAR_AREA): the damage is the engine's own wear,
    not a stat edit (`equip ... 72=` puts a minus into the item's magic list, the base stays full and the server refuses that
    repair, run ven-probe-s3). Back in town by the harness warp. Returns (item id, durability, maximum) or None.
    MXL_VEN_WEAR=click (bug #433): the Circlet is dropped next to the character, picked up and worn by clicks instead of the
    harness `equip`, and a tooltip screenshot of the worn Circlet is taken back in town (STATE["ven_shots"])."""
    H("unequip head")
    H("unequip body")
    H("packclear")
    if os.environ.get("MXL_VEN_WEAR") == "click":
        goto(town)
        it = rc_obtain(VEN_WEAR_ITEM, log, [])
        if it is None:  # the pick-up click can put it straight on the empty head (body=1; slot 3, 2026-10-29, lane act1start)
            on = next((i for i in rc_of(VEN_WEAR_ITEM, RC_PAGE_BODY, log) if i.get("body") == 1), None)
            if on is None:
                return None
            iid = on["id"]
            log.append("%s id %d worn by the pick-up click itself (the head was empty)" % (VEN_WEAR_ITEM, iid))
        else:
            iid = it["id"]
            rc_open_inventory()
            px, py = inv_px(it["x"], it["y"])
            g.click(px / 1600, py / 900)  # lift it ...
            time.sleep(0.8)
            g.click(*VEN_HEAD_SLOT)  # ... and wear it
            time.sleep(1.2)
        on = next((i for i in rc_items(log) if i["id"] == iid), {})
        log.append("%s id %d worn by clicks: page %s" % (VEN_WEAR_ITEM, iid, on.get("page")))
        close_right_panel()
        if on.get("page") != RC_PAGE_BODY:
            return None
    else:
        _ok, l = Hl("equip %s head" % VEN_WEAR_ITEM, log)
        iid = first(l, r"item id=(\d+)")
    if iid is None:
        return None

    def dur(i=None, client=False):
        return first(H("%s %d 72" % ("cistat" if client else "istat", iid if i is None else i))[1], r"= (-?\d+)")
    full = first(H("istat %d 73" % iid)[1], r"= (-?\d+)")
    # MXL_VEN_WEAR_WEAPON=1 (lane dursync): the worn right-hand weapon too, worn down by the player's own left clicks on the
    # Zombies (a weapon loses durability on its hits, armour when it is hit)
    weapon = os.environ.get("MXL_VEN_WEAR_WEAPON") == "1"
    wid = next((i["id"] for i in rp_items_now() if i.get("page") == RC_PAGE_BODY and i.get("x") == 4), None) if weapon else None
    w0 = dur(wid) if wid is not None else None
    if weapon:
        log.append("weapon (right hand) id %s durability %s" % (wid, w0))
    watch = os.environ.get("MXL_VEN_DURWATCH", "1") == "1"
    if watch:  # counts packet 0x3e for durability: server send, client handler, client apply (bug #433)
        Hl("durwatch on", log)
    goto(VEN_WEAR_AREA[town])
    zombie = next((i for i, r in enumerate(table("monstats")) if r.get("Id") == "zombie1"), None)
    p = hstate()["player"]
    if zombie is not None:
        Hl("spawn %d 12 %d %d" % (zombie, p["x"] + 3, p["y"]), log)
    t0 = time.time()

    def weapon_done():
        return wid is None or w0 is None or (dur(wid) or 0) < w0
    far = 0
    while time.time() - t0 < timeout and ((dur() or 0) > want or not weapon_done()) and not player_dead(hstate()["player"]):
        if wid is None:
            time.sleep(8)
            continue
        st = hstate()
        p = st["player"]
        if p.get("area") != VEN_WEAR_AREA[town]:  # a stray click took a cave entrance: back to the field
            goto(VEN_WEAR_AREA[town])
            continue
        mons = [m for m in st["mons"] if m.get("class") == zombie and "mx" in m and m.get("life", 1) > 0]
        if (not mons or far >= 4) and zombie is not None:  # none left, or none came near for 4 looks: fresh ones beside him
            Hl("spawn %d 6 %d %d" % (zombie, p["x"] + 2, p["y"]), log)
            far = 0
            time.sleep(2)
            continue
        # only a Zombie next to the character, clicked inside RP_SAFE (no HUD, no far-off cave entrance)
        near = sorted(mons, key=lambda m: abs(m["mx"] - p["x"]) + abs(m["my"] - p["y"]))[0]
        fx, fy = rp_screen_xy(near["mx"], near["my"], p)
        if abs(near["mx"] - p["x"]) + abs(near["my"] - p["y"]) > 6 or \
                not (RP_SAFE[0] <= fx * 1600 <= RP_SAFE[2] and RP_SAFE[1] <= fy * 900 <= RP_SAFE[3]):
            far += 1
            time.sleep(1.5)  # let them come
            continue
        far = 0
        for _ in range(4):
            g.click(fx, fy)
            time.sleep(0.6)
    srv, cli = dur(), dur(client=True)
    log.append("after the fight: server durability %s, client %s; weapon server %s, client %s" % (
        srv, cli, dur(wid) if wid is not None else "-", dur(wid, True) if wid is not None else "-"))
    for ln in H("cistat %d 72 scan" % iid)[1]:  # the layers of the client's stat 72 (bug #433: a wrong layer)
        log.append(ln)
    STATE.setdefault("ven_wear_sync", []).append((srv, cli) + ((dur(wid), dur(wid, True), w0) if wid is not None else ()))
    for ln in Hl("durwatch show", log)[1] if watch else []:
        log.append(ln)
    for ln in mxl_text().splitlines():
        if ln.startswith("dursync"):
            log.append(ln)
    if watch:
        Hl("durwatch off", log)
    for _ in range(16):
        if not H("kill nearest")[0]:
            break
    revive_if_dead()
    goto(town)
    rc_open_inventory()  # what the client shows of the worn Circlet: its tooltip on the head slot (bug #433)
    hover_px(VEN_HEAD_SLOT[0] * 1600, VEN_HEAD_SLOT[1] * 900)
    time.sleep(0.8)
    STATE.setdefault("ven_shots", []).append(sh("ven_wear_tooltip_%d" % town))
    close_right_panel()
    return iid, dur(), full


def ven_repair_all(iid):
    """Click the vendor panel's Repair All button (hover first); (durability after, gold paid, the panel's own refusal seen)."""
    gold0 = first(H("gold get")[1], r"carried=(\d+)")
    g.click(VEN_REPAIR_ALL[0] / 1600, VEN_REPAIR_ALL[1] / 900, move_only=True)
    time.sleep(0.8)
    g.click(VEN_REPAIR_ALL[0] / 1600, VEN_REPAIR_ALL[1] / 900)
    time.sleep(2.0)
    gold1 = first(H("gold get")[1], r"carried=(\d+)")
    refused = not trade_panel_open() or gold1 == gold0
    if gold1 == gold0:  # "I cannot complete that request." / Continue: dismiss it
        g.click(VEN_REFUSAL_OK[0] / 1600, VEN_REFUSAL_OK[1] / 900)
        time.sleep(0.8)
    return first(H("istat %d 72" % iid)[1], r"= (-?\d+)"), (gold0 or 0) - (gold1 or 0), refused


def ven_repair(npc, nm, town, log, shots, paths):
    """Repair as a player does: Trade/Repair, then the panel's Repair All button, on a Circlet worn down by natural hits. First as
    it comes back from the fight; when that is refused (the client still shows full durability, bug #433), once more after lifting
    the Circlet off the head and putting it back (the client then reads the server's durability). Returns (problems, notes)."""
    worn = ven_wear(town, log)
    if worn is None or worn[1] is None or worn[2] is None or worn[1] >= worn[2]:
        return ["%s: the wear set-up gave no damaged item (%s)" % (nm, worn)], []
    iid, dur0, full = worn
    menu = ven_reach_and_talk(npc, nm, log, paths)
    if menu is None:
        return ["%s: not reached / no menu for the repair" % nm], []
    line = rp_menu_line(menu, RP_TRADE)
    if line is None:
        close_menu()
        return [], ["%s: no Trade/Repair line" % nm]
    Hl("menu %d" % line, log)
    for _ in range(10):
        time.sleep(1.0)
        if trade_panel_open():
            break
    g.click(VEN_REPAIR_ALL[0] / 1600, VEN_REPAIR_ALL[1] / 900, move_only=True)
    time.sleep(0.8)
    shots.append(sh("ven_repair_%s_hover" % nm.lower()))
    dur1, paid1, _r = ven_repair_all(iid)
    notes = ["%s: Repair All on the worn %s (%d of %d): %s" % (nm, VEN_WEAR_ITEM, dur0, full, "repaired to %s for %d gold" % (dur1, paid1)
                                                               if dur1 == full and paid1 > 0 else "refused, durability %s" % dur1)]
    if dur1 != full:
        g.click(*VEN_HEAD_SLOT, button="left")  # lift the Circlet ...
        time.sleep(0.8)
        g.click(*VEN_HEAD_SLOT, button="left")  # ... and wear it again
        time.sleep(1.0)
        g.click(VEN_REPAIR_ALL[0] / 1600, VEN_REPAIR_ALL[1] / 900, move_only=True)
        time.sleep(0.8)
        shots.append(sh("ven_repair_%s_hover2" % nm.lower()))
        dur1, paid1, _r = ven_repair_all(iid)
        notes.append("after lifting and wearing it again: %s" % ("repaired to %s for %d gold" % (dur1, paid1)
                                                                if dur1 == full and paid1 > 0 else "refused, durability %s" % dur1))
    rp_close_trade()
    if held_item():
        release_held_item()
    bad = [] if dur1 == full and paid1 > 0 else ["%s: Repair All did not repair the worn %s (%s of %s)" % (nm, VEN_WEAR_ITEM, dur1, full)]
    return bad, notes


def ven_setup(towns, log):
    """SET-UP (named in the note): the act-open quest words and, for Harrogath, Prison of Ice done (Anya), by save; level by
    `xp`; the town waypoint bits."""
    notes = []
    later = [a for a, t in RP_ACT_TOWN.items() if t in towns and a > 1]
    if later:
        words = rp_open_acts([max(later)], log)
        if words:
            notes.append("quest words %s set by save" % words)
    if 109 in towns:
        with open(os.path.join(SAVES, g.CHAR_NAME + ".d2s"), "rb") as f:
            save = f.read()
        if not quest_done(save, VEN_ANYA_WORD):
            rc2_closed_edit(lambda s: rc_setup.set_quest_bits(s, 0, VEN_ANYA_WORD, rc_setup.DONE), log)
            notes.append("quest word %d (Prison of Ice) done by save" % VEN_ANYA_WORD)
    if 75 in towns and os.environ.get("MXL_VEN_HRATLI_PIER") == "1":
        # Hratli by the waypoint again (his house is reached only the long way round, bug #434); the Act 3 intro word cleared by save
        def clear(s, w=VEN_HRATLI_WORD):
            s = bytearray(s)
            struct.pack_into("<H", s, rc_setup.quest_offset(s, 0, w), 0)
            return bytes(s)
        rc2_closed_edit(clear, log)
        notes.append("quest word %d (Act 3 intro, Hratli) cleared by save" % VEN_HRATLI_WORD)
    elif 75 in towns and os.environ.get("MXL_VEN_HRATLI_HOUSE") == "1":
        # a new character: the Act 3 intro done by save, so Hratli stands at his house (the long way round, bug #434)
        with open(os.path.join(SAVES, g.CHAR_NAME + ".d2s"), "rb") as f:
            save = f.read()
        if not quest_done(save, VEN_HRATLI_WORD):
            rc2_closed_edit(lambda s: rc_setup.set_quest_bits(s, 0, VEN_HRATLI_WORD, rc_setup.DONE), log)
            notes.append("quest word %d (Act 3 intro, Hratli) done by save" % VEN_HRATLI_WORD)
    rp_ready()
    for n in RP_TOWN_WP.values():
        H("waypoint n %d set" % n)
    return notes


def check_ven_vendors():
    """Lane vendors3: every vendor of acts 1-3 and 5 on the player path: the click route there (ven_click_route), the click talk,
    Trade, buy by right click, sell back (lift, drop on the panel), gamble where offered, Repair at the smiths. Towns are reached
    by the waypoint panel (rp_waypoint_to). MXL_VEN_TOWNS=1,40,... and MXL_VEN_NPCS=Name,... pick a part."""
    mark = engine_mark()
    log, shots, rows, bad, paths = [], [], [], [], {}
    towns = [int(t) for t in (os.environ.get("MXL_VEN_TOWNS") or "1,40,75,109").split(",") if t]
    only = {n for n in (os.environ.get("MXL_VEN_NPCS") or "").split(",") if n}
    setup = ven_setup(towns, log)
    STATE["ven_shots"] = []
    for town in towns:
        for npc, nm in VEN_NPCS[town]:
            if only and nm not in only:
                continue
            area = rp_waypoint_to(town, log)  # (back) in the town: a vendor's route starts where the last one ended
            if area != town:
                bad.append("could not reach town %d (area %s)" % (town, area))
                break
            start = hstate()["player"]
            try:
                b, notes = rp_vendor_round(npc, nm, log, shots, talk=lambda n, lg, nm=nm: ven_reach_and_talk(n, nm, lg, paths))
                if nm in VEN_REPAIR and not any("no menu" in x for x in b):
                    rb, rn = ven_repair(npc, nm, town, log, shots, paths)
                    b, notes = b + rb, notes + rn
            except Exception as e:
                b, notes = ["%s: script %r" % (nm, e)], []
            bad += b
            rows.append("%d %s [%s; from %s,%s]: %s%s" % (town, nm, paths.get(nm, "?"), start.get("x"), start.get("y"),
                                                         "; ".join(notes), (" | " + "; ".join(b)) if b else ""))
            if not game_alive():
                bad.append("the game died at %s" % nm)
                rp_recover(nm, log)
                break
    shots += STATE.pop("ven_shots", [])
    finish("ven_vendors", not bad, ("SET-UP: %s; " % "; ".join(setup) if setup else "") + "; ".join(rows)
           + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots[:40], rows + log[-400:])


CHECKS += [("ven_vendors", check_ven_vendors)]


def relp_npcs_check():
    """Lane rc3 diagnostic (harness, not the player path): does the Rogue Encampment hold each town NPC of RELP_NPCS? Per NPC: the
    map preset (`presets 1`), then the server's own search (`moveto nearest <class>`, a harness move) and whether the NPC then
    stands within 40 of the character. PASS when every NPC is found."""
    mark = engine_mark()
    log, rows, bad = [], [], []
    rp_be("barbarian")
    goto(1)
    pres = parse_presets(Hl("presets 1", log)[1])
    for npc, who in RELP_NPCS:
        pr = [(q["x"], q["y"]) for q in pres if q["class"] == npc]
        u = parse_moveto(Hl("moveto nearest %d" % npc, log)[1])
        time.sleep(6)
        near = [m for m in hstate()["mons"] if m.get("class") == npc]
        rows.append("%s (%d): preset %s, moveto %s, in view %s" % (who, npc, pr or "none", (u["x"], u["y"]) if u else "none",
                                                                  (near[0]["mx"], near[0]["my"]) if near else "no"))
        if not u and not near:
            bad.append("%s not in town" % who)
    shot = sh("relp_npcs")
    finish("relp_npcs", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, [shot], rows + log[-100:])


CHECKS += [("relp_npcs", relp_npcs_check)]

# lane hdmon2: Act 1-2 Normal HD stand-ins (docs/hd-monsters.md section 8). A graphics check with harness set-up (`spawn`, Tank),
# not a player-path verification: the look is judged by hand on the screenshots.
# (area, monstats Id, what the stand-in is now)
HM2_MONSTERS = [(2, "robedagger", "councilmember1"), (2, "cloakdagger", "councilmember1"), (2, "zombierags", "zombie1"),
                (2, "greenzombie", "zombie1"), (2, "orkshaman", "fallenshaman1"), (2, "hell_dragonknight", "doomknight2"),
                (2, "corpseworm", "maggotbaby1"), (2, "cultist1", "councilmember1, SC fill"), (2, "troll1", "thornhulk1"),
                (41, "deathwing1", "vulture1"), (41, "centaur1", "clawviper1"), (41, "dead3", "sandraider1"),
                (41, "firewizard1", "firegolem")]
# lane act1start: rows run only when MXL_HM2_ONLY names them (tints2's look owed: Inarius `(1`, the donors' own units)
HM2_EXTRA = [(2, "quest_inarius", "doomknight2, `(1`"), (2, "brute2", "own unit YE"), (2, "arach1", "own unit SP")]


def hm2_monsters():
    """Lane hdmon2: each changed Act 1-2 stand-in spawned beside a tanked character in HD (Blood Moor / Rocky Waste), left to walk
    up and fight (screenshots after 2.5 s and 5 s), then killed (screenshot of the death). `asserttrace` counts the engine
    asserts per monster. SET-UP: `god 1` as in wall_maps. PASS: every monster spawned, no assert, the game alive; whether each looks right and animates in every
    mode is judged by hand on the hm2_<id>_*.png shots. MXL_HM2_ONLY=<id,...> runs a subset (HM2_EXTRA rows only when named);
    MXL_HM2_MODES=hd,legacy shoots each monster in every mode named (default hd; shots hm2_<id>_<mode>_*.png past the first)."""
    hm_monsters("hm2", HM2_MONSTERS, HM2_EXTRA)


def hm_monsters(tag, monsters, extra=()):
    """The stand-in look check of hm2_monsters / hm3_monsters over a list of (area, monstats Id, what the stand-in is); `extra`
    rows run only when MXL_<TAG>_ONLY names them, MXL_<TAG>_MODES=hd,legacy shoots every mode named (MXL_HM_GRAPHICS=legacy
    alone, lane hdmonlook's switch, is the same as MXL_<TAG>_MODES=legacy; shots past the first mode are <tag>_<id>_<mode>_*)."""
    mark = engine_mark()
    log, rows, bad, shots = [], [], [], []
    only = set(filter(None, (os.environ.get("MXL_%s_ONLY" % tag.upper()) or "").split(",")))
    enable_debug()
    cheat("god 1")  # a zombie pack killed the tanked character in the first run; the check judges graphics, not combat
    goto(1)
    modes = [m.strip().lower() for m in (os.environ.get("MXL_%s_MODES" % tag.upper()) or os.environ.get("MXL_HM_GRAPHICS")
                                         or "hd").split(",") if m.strip()]
    Hl("asserttrace on", log)
    todo = [(mode, e) for mode in modes for e in list(monsters) + [e for e in extra if e[1] in only]]
    with Tank():
        for k, (mode, (area, mid, what)) in enumerate(todo):
            if only and mid not in only:
                continue
            if graphics_mode() != mode:  # G in the town (set_graphics)
                goto(1)
                if not set_graphics(mode):
                    bad.append("graphics mode %s not reached" % mode)
            stag = mid if mode == modes[0] else "%s_%s" % (mid, mode)
            row = row_of("monstats", "Id", mid)
            if row is None:
                bad.append("%s: not in the built monstats" % mid)
                continue
            goto(area)
            a0 = pot_asserts()
            px, py = player_xy()
            # spawned 8 subtiles to the screen right or left (alternating), so the "far" shot shows the monster on its own, away
            # from the player's effects and the corpses of the ones before (lane hdmonlook: next to the player it was hidden)
            dx = 8 if k % 2 == 0 else -8
            _, sp = Hl("spawn %s 1 %d %d" % (row["*hcIdx"], px + dx, py - dx), log)
            uid = first(sp, r"id=(\d+)")
            if uid is None:
                bad.append("%s: not spawned" % mid)
                continue
            time.sleep(0.6)
            shots.append(sh("%s_%s_far" % (tag, stag)))
            time.sleep(1.9)
            shots.append(sh("%s_%s_near" % (tag, stag)))
            time.sleep(2.5)
            shots.append(sh("%s_%s_fight" % (tag, stag)))
            H("kill %s" % uid)
            time.sleep(1.5)
            shots.append(sh("%s_%s_death" % (tag, stag)))
            a1 = pot_asserts()
            n = (a1 - a0) if a0 is not None and a1 is not None else None
            msgs = pot_assert_lines(n or 0)
            rows.append("%s (%s, area %d, %s): spawned, asserts %s%s" % (mid, what, area, mode, n if n is not None else "?",
                                                                     " %s" % msgs if msgs else ""))
            if n is None or n > 0:
                bad.append("%s: %s engine asserts" % (mid, n))
            if not game_alive():
                bad.append("the game died after %s" % mid)
                break
    goto(1)
    if graphics_mode() != "hd":
        set_graphics("hd")
    cheat("god 0")
    finish("%s_monsters" % tag, not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-300:],
           partial="the look and the animation of each mode are judged by hand on the %s_*.png shots" % tag)


CHECKS += [("hm2_monsters", hm2_monsters)]

# lane hdmon3: Act 3-5 Normal HD stand-ins (docs/hd-monsters.md section 11), the same graphics check as hm2_monsters (harness
# `spawn`, god mode, judged by hand on the shots). All spawned in the Blood Moor: the HD unit and its colour table do not depend on
# the area, and the harness reaches Acts 3-5 only through the quest chain. (area, monstats Id, what the stand-in is now)
HM3_MONSTERS = [(2, "couatlfather1", "clawviper1, SC fill"), (2, "belial", "baalminion1"),
                (2, "combatdrone1", "irongolem"), (2, "combatdrone2", "irongolem"), (2, "cube1", "arach1"),
                (2, "rathma_primus", "vampire1"), (2, "mahasattva", "clawviper1"), (2, "dragonknight3", "doomknight2"),
                (2, "brainpower", "bloodlord1"), (2, "harlequin2", "sandraider1"), (2, "shardspawn", "frozenhorror1, A2 state fill"),
                (2, "l_priest", "sandraider1")]  # lane hdmonlook: the Priest 1! moved to the Harlequin's donor


def hm3_monsters():
    """Lane hdmon3: each changed Act 3-5 stand-in (and the Shardspawn, whose A2 now has a state) spawned in HD beside a tanked
    character in the Blood Moor, shots near / fight / death as hm2_monsters. PASS: every monster spawned, no engine assert, the
    game alive; the look is judged by hand on the hm3_<id>_*.png shots. MXL_HM3_ONLY=<id,...> runs a subset."""
    hm_monsters("hm3", HM3_MONSTERS)


CHECKS += [("hm3_monsters", hm3_monsters)]
# ---------------------------------------------------------------- lane skilltips: skill tooltip lines (bug #396)
# `py -3 tools/game_checks.py all stip_tooltips` (MXL_STIP_CLASSES=amazon,... for others; one class fits a 10-minute run;
# MXL_STIP_LIMIT=15 shoots every skill of a tab instead of the first 6, lane colourcode: the necromancer's Widowmaker is cell 14). Positions
# of the 1600 x 900 client, read from lane hdicons2's screenshots: the right skill button, the first popup cell (HD: the cell left
# of the button, the columns going right; classic: the right-most column, the columns going left) and its step, and per graphics
# mode the skill tree's tab buttons and its 3 x 5 grid. Classic's popup draws the skill name only, so classic is read in the tree.
STIP_CLASSES = ("sorceress", "amazon", "necromancer")
STIP_FIRE_WALL = 51  # skills.txt *Id: class-less in Median 2012, learnt (set-up) so the popup shows it
STIP_RIGHT_BUTTON = {"hd": (858, 866), "legacy": (1190, 862)}
STIP_POPUP = {"hd": (857, 738, 56, 1), "legacy": (1244, 735, 72, -1)}
STIP_TREE = {"hd": (((1137, 175), (1262, 175), (1386, 175)),
                    tuple((x, y) for y in (235, 310, 385, 460, 535) for x in (1150, 1259, 1368))),
             "legacy": (((1230, 295), (1230, 455), (1230, 615)),
                        tuple((x, y) for y in (147, 250, 352, 455, 557) for x in (857, 960, 1065)))}
STIP_TOOLTIP_SHARE = 0.04  # share of the client that changes when a tooltip box opens (a skill tooltip covers about a tenth)


def stip_popup_cells(mode, cols=5, rows=6):
    x0, y0, step, way = STIP_POPUP[mode]
    return tuple((x0 + way * step * c, y0 - step * r) for r in range(rows) for c in range(cols))


def stip_labels_cut(text=None):
    """The plugin part skilltext's counter (`mxl2012` line 'skilltext ... (0x287a50 hooked); labels cut N'), None when the part
    is off or failed. `text`: the command's output (read from the game when None)."""
    m = re.search(r"^skilltext skill tooltip labels.*hooked\); labels cut (\d+)", mxl_text() if text is None else text, re.M)
    return int(m.group(1)) if m else None


def stip_changed(a, b, thr=40):
    """Share of the pixels that differ between two captures."""
    import numpy as np
    return float((np.abs(a - b).sum(axis=2) > thr).mean())


def stip_scan(cells, tag, shots, log, limit=10):
    """Hovers each cell and keeps a screenshot when a tooltip box opened (against the frame with the cursor parked on the left
    edge). Returns the tooltips seen."""
    hover(0.02, 0.45)
    base, seen = grab(), 0
    for k, (x, y) in enumerate(cells):
        hover_px(x, y)
        share = stip_changed(base, grab())
        if share > STIP_TOOLTIP_SHARE:
            shots.append(sh("stip_%s_%d" % (tag, k)))
            log.append("%s cell %d (%d, %d): tooltip (%.2f of the client changed)" % (tag, k, x, y, share))
            seen += 1
            if seen >= limit:
                break
    hover(0.02, 0.45)
    return seen


def stip_popup(mode, tag, shots, log):
    """Opens the right skill button's popup (a left click on the button), hovers its cells, closes it with a second click."""
    bx, by = STIP_RIGHT_BUTTON[mode]
    g.click(bx / 1600, by / 900)
    time.sleep(1.5)
    shots.append(sh("stip_%s_popup" % tag))
    seen = stip_scan(stip_popup_cells(mode), tag, shots, log)
    g.click(bx / 1600, by / 900)
    time.sleep(1.0)
    return seen


def stip_tree(mode, tag, shots, log):
    """The skill tree (T): each tab, every cell hovered (unlearned skills show their first-level lines). right_panel_open reads HD
    positions, so in classic the tree is opened and closed blind (as hdit_icons does)."""
    seen = 0
    tabs, cells = STIP_TREE[mode]
    if mode != "hd" or not right_panel_open():
        g.key("t")
        time.sleep(1.5)
    for i, (x, y) in enumerate(tabs):
        g.click(x / 1600, y / 900)
        time.sleep(1.0)
        seen += stip_scan(cells, "%s_tab%d" % (tag, i + 1), shots, log, limit=int(os.environ.get("MXL_STIP_LIMIT") or 6))
    if mode == "hd":
        close_right_panel()
    else:
        g.key("t")
        time.sleep(1.0)
    return seen


def stip_tooltips():
    """Lane skilltips, bug #396: the skill tooltip lines on the player path. Per class of MXL_STIP_CLASSES a fresh level-1 Normal
    character (mortal). SET-UP: the sorceress learns Fire Wall (harness `setskill`, Median 2012 gives it no class). Then the
    right skill button's popup in HD (classic draws names only there) and the three tabs of the skill tree in HD and in classic
    graphics, each skill hovered and its tooltip shot. PASS: every class made, tooltips seen in each view, the plugin part
    skilltext's counter grown, no assert / crash. The lines themselves (no
    `%d`, no "FLYING POLAR BUFFALO ERROR", 1.13c's words: "Fire Duration: 0.3 seconds", "Average Fire Damage: 70-93 per second",
    "Mana Cost: 44") are read by hand in stip_*.png and the numbers compared with 1.13c's formulas on the data."""
    import playthrough as pt
    classes = [x for x in (os.environ.get("MXL_STIP_CLASSES") or ",".join(STIP_CLASSES)).split(",") if x]
    stamp = int(time.time())
    for k, cls in enumerate(classes):
        mark = engine_mark()
        log, rows, bad = [], [], []
        c = pt.Ctx(sys.modules[__name__], pt.CLASS_NAMES.index(cls), log)
        name = "St" + pt.char_name(cls, stamp + 7 * k)[2:]
        pt.step_create(c, name)
        if c.steps.get("create", ("",))[0] != "PASS":
            finish("stip_tooltips %s" % cls, False, "could not create %s: %s" % (name, c.steps.get("create")), mark, c.shots, log)
            continue
        if cls == "sorceress":
            rows.append("SET-UP: Fire Wall learnt by `setskill` (base level %s)" % learn(STIP_FIRE_WALL, 1))
            time.sleep(1.0)
        before = stip_labels_cut()
        shots = c.shots
        for mode in ("hd", "legacy"):
            if not set_graphics(mode):
                bad.append("graphics mode %s not reached" % mode)
                continue
            if mode == "hd":
                n = stip_popup(mode, "%s_hd_pop" % cls[:3], shots, log)
                rows.append("hd popup: %d tooltips" % n)
                if n == 0:
                    bad.append("no tooltip in the HD popup")
            n = stip_tree(mode, "%s_%s_tree" % (cls[:3], mode), shots, log)
            rows.append("%s tree: %d tooltips" % (mode, n))
            if n == 0:
                bad.append("no tooltip in the %s skill tree" % mode)
        set_graphics("hd")
        after = stip_labels_cut()
        rows.append("skilltext labels cut %s -> %s" % (before, after))
        if before is None or after is None or after <= before:
            bad.append("the skilltext counter did not grow")
        if not game_alive():
            bad.append("the game died")
        finish("stip_tooltips %s (%s)" % (cls, name), not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""),
               mark, shots, rows + log[-200:], partial="the lines in stip_*.png are read by hand")
        if not g.game_pids():
            to_menu()


CHECKS += [("stip_tooltips", stip_tooltips)]
# ---- lane procicons: the closest icon of the skills Median's items put on the skill bar (tools/data/item_skill_icons.tsv) ----
# (item code, body location, skill): items with charges, stat 204 (item_charged_skill, layer = skill id << 6 | level, value =
# charges << 8 | maximum), worn by `equip`. The oskill skills are learnt by `setskill` instead: `equip` sets an item's stats after
# the game took the item on, so the game never adds its oskills (stat 97), also not after Save and Exit, and the harness' own items
# are refused by a click ("I can't use this yet"; runs of 2026-10-29). The pop-up draws a skill's icon from its skilldesc row, the
# same for a learnt skill, an oskill or a charge.
PIC_ITEMS = (("rin", "rring", "Apocalypse"), ("rin", "lring", "Summon Fallen"), ("amu", "neck", "Lightning Shield"))
PIC_LEARNT = ("Ice Lance", "Spin To Win", "Summon Treewarden")
# the left / right skill buttons (fractions of the client area; 1600 x 900)
PIC_BUTTONS = {"hd": {"left": (0.466, 0.962), "right": (0.536, 0.962)},
               "legacy": {"left": (0.256, 0.958), "right": (0.744, 0.958)}}


def pic_skill(name):
    """(id, built skills.txt row) of a Median skill: `<name>_mxl` when txt_migrate renamed it (D2R has a skill of that name)."""
    sk = row_of("skills", "skill", name + "_mxl") or row_of("skills", "skill", name)
    return (int(sk.get("*Id") or table("skills").index(sk)), sk) if sk else (None, None)


def pic_icon_note(sk):
    """Where the skill's icon comes from: its built skilldesc row, IconCel and the shared_icons.json entry."""
    mod = os.path.dirname(os.path.dirname(os.path.dirname(EXCEL)))
    with open(os.path.join(mod, "shared_icons.json"), encoding="utf-8") as f:
        plan = json.load(f)
    desc = row_of("skilldesc", "skilldesc", sk.get("skilldesc")) or {}
    p = plan["skills"].get(sk["skill"], {})
    icon = plan["icons"][p["cel"] // 2] if p else None
    return "%s: skilldesc %s IconCel %s, %s (%s)" % (sk["skill"], sk.get("skilldesc"), desc.get("IconCel"), p.get("method", "not in the plan"),
                                                    "%(origin)s %(sheet)s frame %(cel)s" % icon if icon else "-")


def pic_popups(mode, log, shots):
    """Opens the left and the right skill pop-up in one graphics mode (a background click on each skill button), a shot of
    each, the pop-up closed by a second click."""
    if not set_graphics(mode):
        return False
    time.sleep(2.0)
    for side, (fx, fy) in PIC_BUTTONS[mode].items():
        g.click(fx, fy)
        time.sleep(1.5)
        shots.append(sh("pic_popup_%s_%s" % (side, mode)))
        g.click(fx, fy)
        time.sleep(1.0)
        g.click(0.80, 0.40, move_only=True)
        time.sleep(0.5)
    log.append("%s: pop-ups shot" % mode)
    return True


def pic_skillbar():
    """Lane procicons: 6 skills of Median's items that had the "?" icon in the skill pop-ups, shot in HD and in legacy graphics
    (G): 3 with charges on worn items (two rings, an amulet; Apocalypse is the renamed Apocalypse_mxl) and 3 oskill skills
    learnt (PIC_LEARNT, see above). SET-UP by the harness (`equip` with the stats, `setskill`; level 0 again at the end): a
    graphics check, not a player path. PASS: every item worn, every skill learnt, the game alive, no new engine assert; the
    icons are judged by hand (pic_popup_*_hd.png against pic_popup_*_legacy.png: each skill on its picture from
    tools/data/item_skill_icons.tsv, the same in both modes, no "?")."""
    mark = engine_mark()
    log, shots, bad, notes, learnt = [], [], [], [], []
    goto(1)
    for code, body, name in PIC_ITEMS:
        sid, sk = pic_skill(name)
        if sid is None:
            bad.append("no skill %s in the built tables" % name)
            continue
        notes.append("charges: %s on %s" % (pic_icon_note(sk), code))
        Hl("unequip %s" % body, log)
        ok, _ = Hl("equip %s normal 204:%d=%d %s" % (code, sid << 6 | 10, 20 << 8 | 20, body), log)
        if not ok:
            bad.append("%s not worn on %s" % (code, body))
    for name in PIC_LEARNT:
        sid, sk = pic_skill(name)
        ok = sid is not None and Hl("setskill %d 1" % sid, log)[0]
        if not ok:
            bad.append("%s not learnt" % name)
            continue
        learnt.append(sid)
        notes.append("learnt (an oskill of Median's items): %s" % pic_icon_note(sk))
    time.sleep(1.0)
    for mode in ("hd", "legacy"):
        if not pic_popups(mode, log, shots):
            bad.append("graphics mode %s not reached" % mode)
    set_graphics("hd")
    for _code, body, _s in PIC_ITEMS:
        Hl("unequip %s" % body, log)
    for sid in learnt:
        Hl("setskill %d 0" % sid, log)
    if not game_alive():
        bad.append("the game died")
    finish("pic_skillbar", not bad, "; ".join(notes) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, notes + log,
           partial="the icons in pic_popup_*_hd.png / pic_popup_*_legacy.png are judged by hand (seen with the harness)")


CHECKS += [("pic_skillbar", pic_skillbar)]


# ---- lane skilluse: skills D2R's usability test (0x33f360) refuses for the gear or a lock state, on the player path
# (tools/skill_use_audit.py lists them statically). A refused skill on a button turns a click on a monster into a plain Attack.
SU_AXE, SU_AXE_DMG = ACTS_WEAPON, 400  # Axe (Grade 1), one-handed; damage 400-800 by its stats (help, named)
SU_MODE_SQ, SU_PLAIN = 18, {7, 8}  # plrmode SQ (Blood Hatred's sequence); A1 / A2 (Attack)
SU_MANA = 200  # whole points, max and current: the sweep's 5000 regenerates a few mana between two looks, a skill's cost is lost


def su_tank(sess):
    """The sweep's tank, then mana SU_MANA (max and current) so that a cost shows against regeneration."""
    sess.tank()
    for s_ in (9, 8):
        setstat("player", s_, SU_MANA << 8)


def su_click(sess, mid, button, own, log, looks=6):
    """One background click on monster `mid`: the modes seen in the next ~1 s, mana spent (whole points, the lowest mana seen
    against the mana before), the target's life drop and the skill's own missiles (`own`)."""
    import skill_sweep
    sess.g.hcmd("missiles reset", 8)
    before = skill_sweep.snapshot(sess, mid)
    click_unit(mid, button=button)
    modes, manas = [], []
    for _ in range(looks):
        time.sleep(0.18)
        mode, _x, _y, mana = skill_sweep.quick_look(sess)
        modes.append(mode)
        manas.append(mana)
    time.sleep(0.6)
    after = skill_sweep.snapshot(sess, mid, missiles=True)
    m0 = before["mana"]
    low = min([m for m in manas + [after["mana"]] if m is not None], default=m0)
    t = {"modes": modes, "manas": [m0, *manas, after["mana"]], "mana_spent": (m0 - low) if None not in (m0, low) else None,
         "damage": (before["target"] - (after["target"] or 0)) if before["target"] is not None else None,
         "own_missiles": sorted(set(after["missiles"]) & set(own))}
    log.append("click %s at %s: %s" % (button, mid, t))
    return t


def su_clicks(sess, sid, button, n, log):
    """`n` clicks with skill `sid` on `button`, each at a fresh zombie (life raised), the character tanked before each."""
    import skill_sweep
    row = row_of("skills", "*Id", sid)
    own = skill_sweep.own_missiles(row, table("missiles"))
    out = []
    for _ in range(n):
        su_tank(sess)
        sess.clear_monsters()
        mid = sess.spawn_target()
        time.sleep(0.8)  # the client shows the new monster
        out.append(su_click(sess, mid, button, own, log) if mid is not None else {"modes": [], "error": "no target"})
    return out


def su_usable(sess, sid, log):
    """The server's usability code of `sid` (harness `cast` at a point 5 sub-tiles west, record only: it is help)."""
    p = hstate()["player"]
    ok, lines = Hl("cast %d %d %d" % (sid, p.get("x", 0) - 5, p.get("y", 0)), log)
    return first(lines, r"usable=(-?\d+)")


def su_spent(clicks):
    return any((c.get("mana_spent") or 0) > 0 or c.get("own_missiles") for c in clicks)


def su_summary(clicks):
    return "; ".join("modes %s mana -%s dmg %s%s" % ("/".join(str(m) for m in sorted(set(c.get("modes", [])) - {None})),
                                                      c.get("mana_spent"), c.get("damage"),
                                                      " missiles %s" % c["own_missiles"] if c.get("own_missiles") else "")
                     for c in clicks)


def su_verdicts(r):
    """{step: ok} from the step results of su_check_skilluse (pure, unit-tested)."""
    one, two = r.get("bh_one_axe", []), r.get("bh_two_axes", [])
    v = {
        "Blood Hatred, one axe: no SQ, no mana": bool(one) and all(SU_MODE_SQ not in c["modes"] and not su_spent([c]) for c in one),
        "Blood Hatred, two axes: SQ, mana and damage": any(SU_MODE_SQ in c["modes"] for c in two) and su_spent(two)
        and any((c.get("damage") or 0) > 0 for c in two),
    }
    if "bc_stance" in r:
        v["Bear Claw under Bear Stance (state 47): refused"] = r.get("stance_on") is True and not su_spent(r["bc_stance"])
        v["Bear Claw without the stance: cast"] = r.get("stance_off") is True and su_spent(r["bc_free"])
    if "fortress" in r:
        v["Fortress: cast (state 58, mana)"] = r.get("fort_state") is True and su_spent(r["fortress"])
        v["Bear Claw during Fortress's state 58: refused"] = r.get("fort_state_at_bc") is True and not su_spent(r["bc_fort"])
    return v


def su_check_skilluse():
    """Lane skilluse, player path: a level-120 barbarian (the sweep's Session: level, life and mana raised, never above a
    level-120 character's life; Blood Moor; zombies with raised life as targets; skills by setskill; gear by `equip`: help,
    named) right-clicks a zombie with
      1. Blood Hatred (352, Median: "requires two melee weapons", itypea1 / itypeb1 `mele`) and one axe: D2R refuses the
         skill (code 2) and the click swings Attack (A1 / A2), no mana;
      2. the same with a second axe in the left hand: the SQ sequence (mode 18), mana and damage;
      3. Bear Claw (443, a throwing axe) by left clicks while Bear Stance (431, aura on the right button) holds state 47
         `aura_2` (states `restrict`): refused (restrict 0, code 4); then with Attack on the right button (stance off): cast;
      4. Fortress (440) by a right click: state 58 `unfortunate` (states `restrict`) and mana; Bear Claw during it: refused.
    Median's own texts: Bear Stance and Fortress "only allow the use of melee, summoning and buff/debuff skills"."""
    import skill_sweep
    mark = engine_mark()
    log, shots, r = [], [], {}
    if not need_game():
        return add("su_use", "BLOCKED", "not in a game")
    if hstate()["player"].get("class") != 4 and not be_class(4):
        return add("su_use", "BLOCKED", "could not play a barbarian")
    sess = skill_sweep.Session(sys.modules[__name__], g, g.current_run())
    sess.prepare()
    for s_, v in ((skill_sweep.STAT_STR, 1000), (skill_sweep.STAT_DEX, 1000)):
        setstat("player", s_, v)
    levels = {}
    for sid, lv in ((352, 20), (431, 20), (443, 20), (440, 1)):
        levels[sid] = sess.ensure_learned(row_of("skills", "*Id", sid), lv)
    log.append("skill levels %s" % levels)
    for loc in ("rhand", "lhand"):
        H("unequip %s" % loc)
    axe = "equip %s 21=%d 22=%d rhand" % (SU_AXE, SU_AXE_DMG, SU_AXE_DMG * 2)
    Hl(axe, log)
    H("skill left 0")
    Hl("skill right 352", log)
    r["bh_one_axe"] = su_clicks(sess, 352, "right", 3, log)
    r["bh_one_axe_usable"] = su_usable(sess, 352, log)
    shots.append(sh("su_bh_one_axe"))
    Hl(axe.replace("rhand", "lhand"), log)
    Hl("skill right 352", log)
    r["bh_two_axes"] = su_clicks(sess, 352, "right", 3, log)
    r["bh_two_axes_usable"] = su_usable(sess, 352, log)
    shots.append(sh("su_bh_two_axes"))
    for loc in ("rhand", "lhand"):
        H("unequip %s" % loc)
    code, stack, _chain = sess.base_for("taxe", "bar")
    ok_t, _l = Hl("equip %s %s21=%d 22=%d rhand" % (code, ("%d=%d " % (skill_sweep.STAT_QUANTITY, stack)) if stack else "",
                                                     SU_AXE_DMG, SU_AXE_DMG * 2), log) if code else (False, [])
    if ok_t:
        Hl("skill right 431", log)
        time.sleep(1.5)
        r["stance_on"] = 47 in sess.states()
        Hl("skill left 443", log)
        r["bc_stance"] = su_clicks(sess, 443, "left", 2, log)
        r["bc_stance_usable"] = su_usable(sess, 443, log)
        Hl("skill right 0", log)
        time.sleep(1.5)
        r["stance_off"] = 47 not in sess.states()
        Hl("skill left 443", log)
        r["bc_free"] = su_clicks(sess, 443, "left", 2, log)
        # Fortress at level 1: its state lasts max(175 - 5 x level, 75) frames (6.8 s), Bear Claw is clicked on the same zombie
        Hl("skill right 440", log)
        su_tank(sess)
        sess.clear_monsters()
        mid = sess.spawn_target()
        time.sleep(0.8)
        r["fortress"] = [su_click(sess, mid, "right", skill_sweep.own_missiles(row_of("skills", "*Id", 440), table("missiles")),
                                  log, looks=3)]
        r["fort_state"] = r["fort_state_at_bc"] = 58 in sess.states()
        r["bc_fort"] = [su_click(sess, mid, "left", skill_sweep.own_missiles(row_of("skills", "*Id", 443), table("missiles")),
                                 log, looks=3)]
        r["bc_fort_usable"] = su_usable(sess, 443, log) if 58 in sess.states() else None
        shots.append(sh("su_fortress"))
        Hl("skill right 0", log)
    sess.clear_monsters()
    v = su_verdicts(r)
    note = ("SET-UP (help): level 120, strength / dexterity 1000, mana %d (max and current, before each click), skills by setskill %s, gear by equip (axe %s %d-%d; throwing axe %s); "
            "server usability codes by `cast` (help, record only): Blood Hatred one axe %s, two axes %s, Bear Claw in Bear Stance %s, "
            "in Fortress %s. " % (SU_MANA, levels, SU_AXE, SU_AXE_DMG, SU_AXE_DMG * 2, code, r.get("bh_one_axe_usable"), r.get("bh_two_axes_usable"),
                                   r.get("bc_stance_usable"), r.get("bc_fort_usable")))
    note += "; ".join("%s: %s" % (k, "ok" if ok else "NO") for k, ok in v.items())
    for k in ("bh_one_axe", "bh_two_axes", "bc_stance", "bc_free", "fortress", "bc_fort"):
        if k in r:
            note += " | %s: %s" % (k, su_summary(r[k]))
    finish("su_use", all(v.values()) and ok_t, note, mark, shots, log,
           partial=None if ok_t else "steps 3-4 (no throwing axe could be worn)")


CHECKS += [("su_use", su_check_skilluse)]


# ---- lane manacost: a Sorceress spell costs its skills.txt mana on the player path (acts3's "mana stays at 2,187": Median's
# 20 s ManaRegen and a +300 % manarecoverybonus ring refilled the bar between two looks)
SM_SKILLS = ((530, 10), (535, 10))  # Frigid Sphere, Tempest at skill level 10 (MXL_SM_SKILLS=530:1,530:20 for others)


def skill_mana_cost(row, level):
    """1.13c's SKILLS_GetManaCosts in whole points: (mana + (level - 1) * lvlmana) << manashift, at least minmana << 8, / 256."""
    def n(col):
        v = (row.get(col) or "").strip()
        return int(v) if re.fullmatch(r"-?\d+", v) else 0
    return max((n("mana") + (level - 1) * n("lvlmana")) << n("manashift"), n("minmana") << 8) / 256


def sm_bracket(click):
    """(low, high) whole points one click spent, from the look before it (frame f0, mana m0) and the looks after it
    [(frame, mana), ...] (pure, unit-tested). Regeneration runs between the charge and the first look that shows the drop, so
    low = the drop seen, high = low + the regeneration rate of the next rising looks x the frames since f0. None: no drop."""
    m0, f0, looks = click.get("m0"), click.get("f0"), [x for x in click.get("looks", []) if None not in x]
    i = next((k for k, (_f, m) in enumerate(looks) if m0 is not None and m < m0), None)
    if i is None or f0 is None:
        return None
    f1, m1 = looks[i]
    rise = [(b[1] - a[1]) / (b[0] - a[0]) for a, b in zip(looks[i:], looks[i + 1:]) if b[0] > a[0] and m0 > b[1] > a[1]]
    rate = max(rise, default=0.0)
    return m0 - m1, m0 - m1 + rate * (f1 - f0)


def sm_verdicts(r):
    """{step: ok} from su_check_manacost's {(sid, level): (cost, clicks)} (pure, unit-tested): at least two clicks whose
    bracket (sm_bracket) holds the cost (1 point of rounding), and no click whose drop alone is more than the cost."""
    v = {}
    for (sid, lv), (cost, clicks) in sorted(r.items()):
        br = [b for b in map(sm_bracket, clicks) if b]
        v["skill %d level %d costs %g" % (sid, lv, cost)] = (sum(lo - 1 <= cost <= hi + 1 for lo, hi in br) >= 2
                                                            and all(lo <= cost + 1 for lo, _hi in br))
    return v


def sm_click(sess, mid, log, looks=8):
    """One background right click on monster `mid`: frame and mana before, then (frame, mana) of `looks` quick looks."""
    p = hstate()["player"]
    t = {"f0": p.get("frame"), "m0": p.get("mana"), "looks": []}
    click_unit(mid, button="right")
    for _ in range(looks):
        time.sleep(0.05)
        q = hstate()["player"]
        t["looks"].append((q.get("frame"), q.get("mana")))
    t["bracket"] = sm_bracket(t)
    log.append("click right at %s: %s" % (mid, t))
    return t


def su_check_manacost():
    """Lane manacost, player path: a level-120 sorceress (the sweep's Session; Blood Moor; zombies with raised life as targets;
    skills by setskill: help, named), mana SU_MANA (max and current) before each click, right-clicks a zombie 3 times with
    Frigid Sphere (530) and with Tempest (535) at skill level 10. Each click must lower the mana by the 1.13c cost of the
    built skills.txt row (skill_mana_cost): the drop seen <= the cost <= the drop + the regeneration since the click (sm_bracket,
    from the `state` frame counter of quick looks)."""
    import skill_sweep
    mark = engine_mark()
    log, shots, r = [], [], {}
    if not need_game():
        return add("su_mana", "BLOCKED", "not in a game")
    if hstate()["player"].get("class") != 1 and not be_class(1):
        return add("su_mana", "BLOCKED", "could not play a sorceress")
    sess = skill_sweep.Session(sys.modules[__name__], g, g.current_run())
    sess.prepare()
    want = [tuple(int(x) for x in p.split(":")) for p in os.environ.get("MXL_SM_SKILLS", "").split(",") if p] or SM_SKILLS
    levels = {}
    H("skill left 0")
    for sid, lv in want:
        row = row_of("skills", "*Id", sid)
        levels[(sid, lv)] = got = sess.ensure_learned(row, lv)
        for st_ in (9, 26, 27):  # max mana, manarecovery, manarecoverybonus (record only)
            Hl("stat player %d" % st_, log)
        Hl("skill right %d" % sid, log)
        clicks = []
        for _ in range(3):
            su_tank(sess)
            sess.clear_monsters()
            mid = sess.spawn_target()
            time.sleep(0.8)  # the client shows the new monster
            clicks.append(sm_click(sess, mid, log) if mid is not None else {})
        r[(sid, lv)] = (skill_mana_cost(row, got or lv), clicks)
        su_tank(sess)
        Hl("cast %d %d %d" % (sid, hstate()["player"].get("x", 0) - 5, hstate()["player"].get("y", 0)), log)  # record only (help)
        shots.append(sh("su_mana_%d_%d" % (sid, lv)))
    Hl("skill right 0", log)
    sess.clear_monsters()
    v = sm_verdicts(r)
    note = ("SET-UP (help): level 120, mana %d (max and current, before each click), skills by setskill %s. " % (SU_MANA, levels)
            + "; ".join("%s: %s" % (k, "ok" if ok else "NO") for k, ok in v.items())
            + "".join(" | %d level %d (cost %g): spent %s" % (sid, lv, cost, ", ".join(
                "%d-%.0f" % b if b else "none" for b in (c.get("bracket") for c in clicks)))
                      for (sid, lv), (cost, clicks) in sorted(r.items())))
    finish("su_mana", all(v.values()) and all(got == lv for (_s, lv), got in levels.items()), note, mark, shots, log)


CHECKS += [("su_mana", su_check_manacost)]


# ---- lane hdlook: today's HD work looked at in game, as a player meets it (docs/testing.md "Lane hdlook") ----------------
# SET-UP (named in the notes): each class's own character (HdlAma / HdlPal / HdlNec / HdlAss, made when missing), level 120 by the game's xp
# award, stat points by the stat packet (rp_ready), skill points by `setskill` (the game's point function), mana refilled with
# `setstat` before a cast, travel to the Blood Moor by `level`, a target zombie spawned (life raised so it stays). JUDGED: the
# skill picked on the right button with packet 0x3c (what the skill bar sends) and cast by a background right click on the target.
HDL_CHARS = {"amazon": ("HdlAma", 0), "sorceress": ("HdlSor", 1), "paladin": ("HdlPal", 3), "necromancer": ("HdlNec", 2),
             "barbarian": ("HdlBar", 4), "assassin": ("HdlAss", 6)}
# class -> [(skill id, name, tinted missile rows it draws)] (hd_recolour.json rows reached from skills.txt srvmissile*)
HDL_FX = {"amazon": [(312, "Balefire", ("balefireball", "balefirebolt", "balefiretiny")),
                     (313, "Better Bloodstorm", ("bettercenter",))],
          "paladin": [(509, "Ring of Light", ("barringmakerflame",)), (510, "Holy Trap Advanced", ("holytrail", "sunflames"))],
          # Blackheart is a wand, and Median's wands are Necromancer-only (itemtypes.txt Class nec): a Paladin cannot wear it
          "necromancer": [(669, "Dark Power (Blackheart's oskill)", ("darkpowernova",))],
          "assassin": [(339, "Fireball Sentry", ("sentryfireballbolt",)), (614, "Vampiric Icon", ("vampflame",))]}
# stage `picks` (lane hdlook3): the skills that draw lane hdfx2's hand-picked stand-ins (docs/hd-effects.md section 9,
# data/hd-effects-picks.tsv); rows = the picked missiles they fire (art in the comment). Magic Missiles: its cast flash, the
# overlay `mooncast`, and its missiles (lane picktint: red glows, bug #483); Miasma also puts the overlay `poisondark` on its target
HDL_PICKS = {"amazon": [(314, "Magic Missiles (cast flash mooncast)", ("magicmissile", "teethexplodered"))],
             "paladin": [(518, "Judgement", ("zomgpewpewmallet",)),                 # lightandshadowstrike
                         (499, "Hammerstrike", ("hammerstrikenova",))],            # extra/cursehit
             "sorceress": [(539, "Lorenado", ("lorenado", "lorenadobookflip")),    # lorenado, flipbook
                           (527, "Firedance", ("firedancecenter",)),               # bonfire
                           (540, "Miasma", ("newhexgraphical",)),                  # gore20 (+ overlay poisondark)
                           (542, "Swarm", ("swarm emitted",))],                    # swarmhovers
             "barbarian": [(443, "Bear Claw", ("bearbolt",))]}                     # extra/cursemissle
# the overlay `cursenightmare` (art expansion/steamthick_a) is the curse of skill 677 Nightmare, which no class has: the
# Skeletons (skeleton1, Skill3) cast it; spawned next to the player (harness) so they curse the player
HDL_NIGHTMARE = ("skeleton1", 4)
HDL_OSKILL_ITEM = {669: ("l13", 866, "rhand")}   # Dark Power: worn Blackheart (Grim Wand, uniqueitems row 866), `equip` set-up
HDL_TREE_CLASSES = ("amazon", "paladin")
HDL_LEARN_STATS = (504, 505)  # learn_ennead, learn_blackroad (itemstatcost ids of the build)
HDL_TREE_TABS = {"hd": ((1136, 170), (1260, 170), (1384, 170)),          # D2R's strip of 3 tabs (run checks-20261029-042207-s3)
                 "legacy": ((1230, 294), (1230, 454), (1230, 614))}     # the classic column: the first label of each page


def hdl_stages(env=None):
    """The stages MXL_HDL asks for (default all), in the given order; unknown names are dropped."""
    env = os.environ if env is None else env
    known = ("fx", "mons", "ui", "items", "walls", "picks")
    return [s for s in (env.get("MXL_HDL") or ",".join(known)).split(",") if s in known]


def hdl_be(cls, log):
    """The class's lane character in town, level 120 (set-up, rp_ready); None when it could not be played."""
    name, cid = HDL_CHARS[cls]
    if hstate()["player"].get("class") != cid:
        g.CHAR_NAME = name
        if not switch_character(name, cls, cid):
            log.append("could not play %s" % name)
            return None
    goto(1)
    return rp_ready(120)


def hdl_mana():
    for s in (9, 8):
        setstat("player", s, 4000 << 8)


def hdl_tough(life=200000):
    """Life and max life raised and refilled (set-up), so a shot among strong monsters is not a death screen; the character
    stays mortal."""
    for s in (7, 6):
        setstat("player", s, life << 8)


def hdl_clear(log):
    """Every monster near the player killed by the harness (set-up for the wall shots: the maps' hordes of Median's
    late-game monsters killed a 200,000-life Paladin within seconds, run checks-20261029-091110-s1). Returns how many."""
    ms = [m["id"] for m in hstate()["mons"] if "id" in m]
    for mid in ms:
        H("kill %d" % mid)
    if ms:
        log.append("walls: %d monsters killed (set-up)" % len(ms))
    return len(ms)


def hdl_target(log, dx=5, dy=0):
    """A zombie (class 5) next to the player, its life raised so the casts do not kill it at once (set-up)."""
    px, py = player_xy()
    _ok, sp = Hl("spawn 5 1 %d %d" % (px + dx, py + dy), log)
    mid = first(sp, r"id=(\d+)")
    if mid is not None:
        for s in (7, 6):
            setstat("mon:%d" % mid, s, 200000 << 8)
    return mid


def hdl_drawn(rows, seen):
    """{row name: count} of the wanted missile rows among the classes `missiles` saw ({class: count})."""
    return {r: seen.get(missile_id(r), 0) for r in rows if missile_id(r) is not None}


def hdl_cast(cls, sid, rows, mode, log, shots):
    """One skill: picked on the right button (packet 0x3c), mana refilled, two right clicks on a target zombie, a burst of shots
    after each. Returns (picked, {tinted row: missiles seen})."""
    ok, _ = Hl("skill right %d" % sid, log)
    if not ok:
        return False, {}
    mid = hdl_target(log)
    time.sleep(0.8)
    Hl("missiles reset", log)
    tag = "hdl_fx_%s_%d_%s" % (cls[:3], sid, mode)
    for k in range(2):
        hdl_mana()
        if mid is None or not click_unit(mid, button="right"):
            g.click(0.62, 0.52, button="right")
        for i in range(4):
            time.sleep(0.25)
            shots.append(sh("%s_%d" % (tag, 4 * k + i)))
        time.sleep(0.8)
    _ok, ln = Hl("missiles", log)
    drawn = hdl_drawn(rows, missiles_seen(ln))
    if mid is not None:
        H("kill %d" % mid)
    return True, drawn


def hdl_skill_ui(cls, mode, shots):
    """The skill bar, then the skill tree (T): the page it opens on and each tab of HDL_TREE_TABS clicked."""
    close_right_panel()
    shots.append(sh("hdl_bar_%s_%s" % (cls[:3], mode)))
    g.press("t")
    time.sleep(1.5)
    shots.append(sh("hdl_tree_%s_%s_0" % (cls[:3], mode)))
    for n, (x, y) in enumerate(HDL_TREE_TABS.get(mode, ())):
        g.click(x / 1600, y / 900)
        time.sleep(1.0)
        shots.append(sh("hdl_tree_%s_%s_tab%d" % (cls[:3], mode, n)))
    g.press("t")
    time.sleep(1.0)


def hdl_fx_stage(log, shots, rows, bad, table=None, tree=True):
    only = [c for c in (os.environ.get("MXL_HDL_CLASSES") or "").split(",") if c]
    for cls, skills in (table or HDL_FX).items():
        if only and cls not in only:
            continue
        if hdl_be(cls, log) is None:
            bad.append("%s: character not played" % cls)
            continue
        for sid, _nm, _r in skills:
            if sid in HDL_OSKILL_ITEM:
                code, uniq, loc = HDL_OSKILL_ITEM[sid]
                Hl("unequip %s" % loc, log)
                Hl("equip %s uniq=%d %s" % (code, uniq, loc), log)
            else:
                for st in HDL_LEARN_STATS:  # Median's Ennead / Black Road skills ask for these quest stats (set-up)
                    setstat("player", st, 1)
                log.append("setskill %d -> %s" % (sid, learn(sid, 20) or learn(sid, 5)))
        for mode in ("hd", "legacy"):
            goto(1)
            if not set_graphics(mode):
                bad.append("%s: graphics %s not reached" % (cls, mode))
            if tree and cls in HDL_TREE_CLASSES:
                hdl_skill_ui(cls, mode, shots)
            goto(2)
            time.sleep(3)
            for sid, nm, mrows in skills:
                picked, drawn = hdl_cast(cls, sid, mrows, mode, log, shots)
                rows.append("%s %s %s (%d): %s; tinted rows seen %s" % (cls, mode, nm, sid, "picked" if picked else "NOT PICKED",
                                                                   drawn or "none"))
                if not picked:
                    bad.append("%s %s: skill %d not usable" % (cls, mode, sid))
                if not game_alive():
                    bad.append("the game died after %s" % nm)
                    return
        goto(1)
        set_graphics("hd")


def hdl_picks_stage(log, shots, rows, bad):
    """Lane hdfx2's hand picks: the skills of HDL_PICKS cast as in stage fx, then Skeletons spawned next to the player so
    their Nightmare curse (overlay cursenightmare) lands on the player (shots hdl_pick_nightmare_*)."""
    hdl_fx_stage(log, shots, rows, bad, table=HDL_PICKS, tree=False)
    only = [c for c in (os.environ.get("MXL_HDL_CLASSES") or "").split(",") if c]
    if only and "nightmare" not in only:
        return
    mon, n = HDL_NIGHTMARE
    cls = tint_class(mon)
    if cls is None or hdl_be("paladin", log) is None:
        bad.append("picks: no %s or no character" % mon)
        return
    for mode in ("hd", "legacy"):
        goto(1)
        set_graphics(mode)
        goto(2)
        time.sleep(3)
        hdl_tough()
        px, py = player_xy()
        _ok, sp = Hl("spawn %d %d %d %d" % (cls, n, px + 4, py), log)
        made = re.findall(r"id=(\d+)", " ".join(sp))
        for i in range(8):
            time.sleep(1.5)
            hdl_tough()
            shots.append(sh("hdl_pick_nightmare_%s_%d" % (mode, i)))
        rows.append("nightmare %s: %d %s spawned" % (mode, len(made), mon))
        for u in made:
            H("kill %s" % u)
    goto(1)
    set_graphics("hd")


# Quill Rats 1-5 (quillbear1-5) and Wisps 1-4 (willowisp1-4): unit quillbear1 / willowisp1 levels 0-4 (hd_translvl.json)
HDL_MONS = (("quill", ("quillbear1", "quillbear2", "quillbear3", "quillbear4", "quillbear5")),
            ("wisp", ("willowisp1", "willowisp2", "willowisp3", "willowisp4")))


def hdl_mons_stage(log, shots, rows, bad):
    """Harness spawns in a row (level 0 on the right, then each level up the screen to the left) in the Blood Moor / Cold
    Plains, their life raised; shot alive in HD and in classic."""
    for k, (tag, ids) in enumerate(HDL_MONS):
        goto(1)
        set_graphics("hd")
        goto(3 if k else 2)
        time.sleep(3)
        px, py = player_xy()
        made = []
        for n, mid in enumerate(ids):
            cls = tint_class(mid)
            if cls is None:
                bad.append("%s not in monstats" % mid)
                continue
            _ok, sp = Hl("spawn %d 1 %d %d" % (cls, px + 5 - 2 * n, py - 5 + 2 * n), log)
            u = first(sp, r"id=(\d+)")
            if u is not None:
                made.append(u)
                for s in (7, 6):
                    setstat("mon:%d" % u, s, 100000 << 8)
        time.sleep(1.0)
        for mode in ("hd", "legacy"):
            ok = set_graphics(mode)
            for i in range(3):
                shots.append(sh("hdl_mon_%s_%s_%d" % (tag, mode, i)))
                time.sleep(0.6)
            rows.append("%s: %d of %d spawned, %s %s" % (tag, len(made), len(ids), mode, "on" if ok else "NOT SET"))
        for u in made:
            H("kill %d" % u)
    goto(1)
    set_graphics("hd")


def hdl_ui_stage(log, shots, rows, bad):
    """Inventory and Horadric Cube panels with Median items (HDIT_CODES, `item <code> inv`, set-up), HD and classic; the cube
    opened by a right click on it (its HD cell: in classic the panel is shot as the inventory only)."""
    if hdl_be("paladin", log) is None:
        bad.append("ui: paladin not played")
        return
    Hl("packclear", log)
    H("item box inv")
    for code, _w in HDIT_CODES[:10]:
        Hl("item %s inv" % code, log)
    for mode in ("hd", "legacy"):
        if not set_graphics(mode):
            bad.append("ui: graphics %s not reached" % mode)
        close_right_panel()
        g.press("i")
        time.sleep(1.5)
        shots.append(sh("hdl_inv_%s" % mode))
        if mode == "hd":
            _cube_panel_open(log)
            time.sleep(1.5)
            shots.append(sh("hdl_cube_%s" % mode))
        g.key("esc")
        time.sleep(1.0)
        close_right_panel()
    set_graphics("hd")
    rows.append("inventory (HD, classic) and cube (HD) panels shot")


def hdl_stash_open(log):
    """Walk to the Rogue Encampment's stash (object 267) by left clicks and click it, as a player does."""
    _ok, lines = H("objects")
    sid = next((int(m.group(1)) for m in (re.match(r"object id=(\d+) class=267 ", ln) for ln in lines) if m), None)
    xy = rp_object_xy(sid) if sid is not None else None
    if xy is None:
        log.append("no stash object")
        return False
    return rp_click_toward(xy[0], xy[1], right_panel_open)


HDL_STASH = (122, 107, 44, 42)   # the HD stash grid's top-left cell, 1600 x 900 client (as the cube panel's grid, RP_CUBE)
HDL_STASH_CELL = (3, 4)          # a stash cell well inside the grid, below the panel's tabs


def hdl_stash_item(items):
    """The backpack item to put into the stash: the first that is not the cube; None when the stash already holds one."""
    if any(it.get("page") == 4 for it in items):
        return None
    return next((it for it in items if it.get("page") == 0 and it.get("code") != "box"), None)


def hdl_stash_fill(log):
    """With the stash open: a backpack item picked up by a left click and put into the stash by a left click, as a player
    does (so the stash shots have an item picture to judge). True when the stash then holds an item."""
    it = hdl_stash_item(rp_items_now())
    if it is not None:
        g.click(*rp_inv_xy(it["x"], it["y"]))
        time.sleep(1.0)
        g.click(*rp_inv_xy(HDL_STASH_CELL[0], HDL_STASH_CELL[1], HDL_STASH))
        time.sleep(1.0)
        log.append("stash: %s %s moved" % (it.get("code"), it.get("id")))
    return any(x.get("page") == 4 for x in rp_items_now())


def hdl_items_stage(log, shots, rows, bad):
    """Vendor windows (Charsi and Akara: talk, Trade, the tabs) and the stash, HD and classic; a Median item made in the
    backpack (set-up) when there is none, put into the stash by the player's clicks before the HD stash shot."""
    if hdl_be("paladin", log) is None:
        bad.append("items: paladin not played")
        return
    items = rp_items_now()
    if not any(it.get("page") == 4 for it in items) and hdl_stash_item(items) is None:
        Hl("item %s inv" % HDIT_CODES[0][0], log)
    for mode in ("hd", "legacy"):
        goto(1)
        if not set_graphics(mode):
            bad.append("items: graphics %s not reached" % mode)
        for npc, nm in ((154, "charsi"), (148, "akara")):
            menu = rp_npc_menu(npc, log)
            line = rp_menu_line(menu, RP_TRADE) if menu else None
            if line is None:
                bad.append("%s %s: no Trade line" % (nm, mode))
                close_menu()
                continue
            Hl("menu %d" % line, log)
            time.sleep(4)
            tabs = RP_SHOP_TABS if mode == "hd" else ()  # the classic panel's tabs sit elsewhere: its first page only
            shots.append(sh("hdl_shop_%s_%s_0" % (nm, mode)))
            for t, (x, y) in enumerate(tabs[1:], 1):
                g.click(x / 1600, y / 900)
                time.sleep(1.0)
                shots.append(sh("hdl_shop_%s_%s_%d" % (nm, mode, t)))
            rp_close_trade()
            time.sleep(1.0)
        opened = hdl_stash_open(log)
        time.sleep(1.5)
        stashed = hdl_stash_fill(log) if opened and mode == "hd" else None
        shots.append(sh("hdl_stash_%s" % mode))
        rows.append("stash %s: %s%s" % (mode, "opened by a click" if opened else "NOT OPENED",
                                         "" if stashed is None else ", item put in: %s" % ("yes" if stashed else "NO")))
        g.key("esc")
        time.sleep(1.0)
        close_right_panel()
    set_graphics("hd")


HDL_WALLS = ((3, 18, "downtown"), (80, 95, "glados"))   # (waypoint level, map level, map): the map's entrance is in the first


def hdl_walls_stage(log, shots, rows, bad):
    """Two retextured maps by the player's route: the waypoint panel to the outer level (its bit set: set-up), then the entrance's
    own server warp (`level <id> warp`, a shortcut for the walk to it); three shots (arrival, two left-click walks) per mode."""
    wps = rp_waypoints()
    for wlv, lv, name in HDL_WALLS:
        if wlv in wps:
            H("waypoint n %d set" % wps[wlv][1])
        for mode in ("hd", "legacy"):
            rp_waypoint_to(RP_ACT_TOWN[wps[wlv][0]] if wlv in wps else 1, log)
            set_graphics(mode)
            a = rp_waypoint_to(wlv, log)
            hdl_tough()   # the maps' monsters (Citizen, AC-2 Rivet Bot) killed a level-120 Paladin at once (lane hdlook2)
            Hl("level %d warp" % lv, log)
            time.sleep(3)
            hdl_clear(log)
            time.sleep(5)
            here = hstate()["player"].get("area")
            for i, (dx, dy) in enumerate(WALL_OFFSETS):
                hdl_clear(log)
                hdl_tough()
                if i:
                    x0, y0 = player_xy()
                    rp_click_toward(x0 + dx, y0 + dy, lambda: False, tries=2)
                    hdl_clear(log)
                    time.sleep(1.5)
                shots.append(sh("hdl_wall_%s_%s_%d" % (name, mode, i)))
            rows.append("%s %s: waypoint to %s -> %s, entrance -> area %s" % (name, mode, wlv, a, here))
            if here != lv:
                bad.append("%s %s: not reached (area %s)" % (name, mode, here))
    rp_waypoint_to(1, log)
    set_graphics("hd")


def check_hdl_look():
    """Lane hdlook (block comment above): stages MXL_HDL=fx,mons,ui,items,walls. PASS needs every stage done without an engine
    assert; the pictures are judged by hand from the hdl_* shots."""
    mark = engine_mark()
    log, shots, rows, bad = [], [], [], []
    stages = {"fx": hdl_fx_stage, "mons": hdl_mons_stage, "ui": hdl_ui_stage, "items": hdl_items_stage, "walls": hdl_walls_stage,
              "picks": hdl_picks_stage}
    for s in hdl_stages():
        try:
            stages[s](log, shots, rows, bad)
        except Exception as e:
            bad.append("%s: script error %r" % (s, e))
        g.log("hdl stage %s done" % s)
    finish("hdl_look", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-400:],
           partial="the pictures in the hdl_* shots are judged by hand")


CHECKS += [("hdl_look", check_hdl_look)]


# --- bug #487 (play test 0.1.1): Elvensong's elfin spirit "works like Mind Blast, no conversion" -----------------------------
ELV_SKILL, ELV_SPELL, ELV_SPIRIT, ELV_CONVERSION = 469, 1095, "friendlyelvensong", 53


def elv_sample(spirit_cls, zombies, log):
    """(spirits alive [(id, mode)], spirit corpses, {zombie id: (alive, life, converted)}) right now."""
    st = hstate()
    spirits = [(m["id"], m.get("mode")) for m in st["mons"] if m.get("class") == spirit_cls]
    dead = len([c for c in st["corpses"] if c.get("class") == spirit_cls])
    alive = {m["id"]: m.get("life") for m in st["mons"]}
    zs = {}
    for z in zombies:
        conv = None
        if z in alive:
            _, ln = H("states mon:%s %d" % (z, ELV_CONVERSION))
            conv = any("bit=1" in x for x in ln)
        zs[z] = (z in alive, alive.get(z), conv)
    return spirits, dead, zs


def elv_round(name, spirit_cls, n_zombies, log, shots, secs=10.0):
    """Clear the monsters near, spawn n zombies 2 sub-tiles from the character, right click (Elvensong on the right button) on an
    empty spot beside the character, then sample every ~0.4 s. Returns a summary dict."""
    for _ in range(30):
        ok, _l = H("kill nearest")
        if not ok:
            break
    px, py = player_xy()
    zombies = []
    if n_zombies:
        _, sp = Hl("spawn 5 %d %d %d" % (n_zombies, px + 2, py + 1), log)
        zombies = [int(x) for x in re.findall(r"id=(\d+)", " ".join(sp))]
    mana0 = rd("player", 8)
    g.click(0.53, 0.47, button="right")
    t0, rows, first_spirit, gone_at, conv_seen = time.time(), [], None, None, {}
    shot_at = (1.0, 3.0)
    taken = set()
    while time.time() - t0 < secs:
        spirits, dead, zs = elv_sample(spirit_cls, zombies, log)
        t = round(time.time() - t0, 1)
        if spirits and first_spirit is None:
            first_spirit = t
        if first_spirit is not None and not spirits and gone_at is None:
            gone_at = t
        for z, (a, life, c) in zs.items():
            if c:
                conv_seen.setdefault(z, []).append(t)
        rows.append("t=%s spirits=%s spirit_corpses=%d zombies=%s" % (t, spirits, dead, zs))
        for s in shot_at:
            if t >= s and s not in taken:
                taken.add(s)
                shots.append(sh("%s_%ss" % (name, s)))
        time.sleep(0.25)
    log.extend("   " + r for r in rows)
    mana1 = rd("player", 8)
    out = {"spawned": len(zombies), "mana": (mana0 >> 8 if mana0 else mana0, mana1 >> 8 if mana1 else mana1),
           "spirit_first": first_spirit, "spirit_gone": gone_at, "converted": {z: (ts[0], ts[-1]) for z, ts in conv_seen.items()},
           "zombies_dead": len([z for z, v in zs.items() if not v[0]]) if zombies else 0}
    log.append("%s: %s" % (name, out))
    return out


def check_elvensong():
    """Bug #487 (play test 0.1.1, "Charm doesn't work ... works like mindblast, no conversion"): a Druid with Elvensong (469,
    MXL_ELV_LEVEL, default 20; Poison Flash first) casts it by background right clicks in the Blood Moor. Round 1: nothing near
    (Median's text: the spirit "sings 10 times or until no target is nearby", so it may leave at once). Round 2: 5 zombies 2
    sub-tiles away: the spirit (`friendlyelvensong`, AI Trap-Poison) casts Elvensong Spell (1095, srvdofunc 51) and zombies get
    state 53 (conversion) for Param3 75 frames + rand(Param4): about 3 s, as the skill text says. PASS when the spirit is summoned
    and at least one zombie is converted. SHORTCUT: skill points, level and life / mana (Tank) set by the harness; zombies spawned."""
    mark, log, shots, notes, bad = engine_mark(), [], [], [], []
    lvl = int(os.environ.get("MXL_ELV_LEVEL", "20"))
    spirit_cls = int(row_of("monstats", "Id", ELV_SPIRIT)["*hcIdx"])
    spell = row_of("skills", "*Id", ELV_SPELL)
    notes.append("Elvensong Spell calc1 %r calc2 %r Param3 %s Param4 %s Param5/6 %s/%s" % (
        spell["calc1"], spell["calc2"], spell["Param3"], spell["Param4"], spell["Param5"], spell["Param6"]))
    goto(2)
    with Tank(), Level(60):
        got = learn(ELV_SKILL, lvl)
        notes.append("Elvensong base level %s" % got)
        Hl("skill right %d" % ELV_SKILL, log)
        H("skill left 0")
        empty = elv_round("elv_empty", spirit_cls, 0, log, shots, secs=4.0)
        notes.append("empty spot: spirit seen at %s s, gone at %s s, mana %s -> %s" % (
            empty["spirit_first"], empty["spirit_gone"], empty["mana"][0], empty["mana"][1]))
        near = elv_round("elv_near", spirit_cls, 5, log, shots, secs=12.0)
        notes.append("5 zombies: spirit seen at %s s, gone at %s s; converted %d of %d %s; zombies dead %d" % (
            near["spirit_first"], near["spirit_gone"], len(near["converted"]), near["spawned"], near["converted"],
            near["zombies_dead"]))
        if near["spirit_first"] is None:
            bad.append("no spirit summoned next to the zombies")
        if not near["converted"]:
            bad.append("no zombie converted")
        for _ in range(30):
            ok, _l = H("kill nearest")
            if not ok:
                break
    note = "; ".join(notes) + ("; PROBLEMS: " + "; ".join(bad) if bad else "")
    finish("elvensong", not bad, note, mark, shots, log,
           partial="harness set-up (skill level, Tank, spawned zombies)")


CHECKS += [("elvensong", check_elvensong)]


# lane unported: unported.md "Item use pSpell 3 / 10" (engine-triage #24). Median's misc rows with pSpell 3 (stat += calc), each
# picked up from the ground and used by a right click; the deltas against Median's own calcs (integer arithmetic). The Apple (dog,
# pSpell 10) is not here: its Median row has no state, len or stat, its regeneration came from code outside the txt (bugs.md 499).
IU_LEVEL = 30
IU_ITEMS = ("zkq", "zky", "zku", "zkw", "!@B", "zog", "zoh")
IU_ROOM = 1000 << 8  # max life / mana for the packs, so the pack's add is not cut by the cap
IU_STATS = ("statpts", "newskills", "experience", "gold", "hitpoints", "mana", "potion_stat_cap", "potion_skill_cap")
IU_FIXED = ("hitpoints", "mana")  # 1/256 units in `stat player`


def iu_expected(code, lvl, st):
    """{stat: delta} by Median 2012's misc.txt calc of `code` for a character of level `lvl` with the stats `st` before the use."""
    c, s, gold = st.get("potion_stat_cap") or 0, st.get("potion_skill_cap") or 0, st.get("gold") or 0
    if code == "zkq":  # Signet of Learning
        return {"statpts": max(1 - c // 500, 0), "potion_stat_cap": max(1 - c // 501, 0)}
    if code == "zky":  # Greater Signet of Learning
        return {"statpts": max(25 - (c // 250) * 5, 5), "potion_stat_cap": max(25 - (c // 250) * 5, 5)}
    if code == "zku":  # Signet of Experience
        return {"experience": 250 * lvl}
    if code == "zkw":  # Signet of Gold
        return {"gold": min(lvl * 150, lvl * 10000 - gold)}
    if code == "!@B":  # Signet of Skill (New)
        return {"newskills": max(1 - s // 3, 0), "potion_skill_cap": max(1 - s // 4, 0)}
    if code == "zog":  # Life Pack
        return {"hitpoints": lvl * 10}
    if code == "zoh":  # Mana Pack
        return {"mana": lvl * 10}
    raise KeyError(code)


def iu_read(log):
    ids = dict(RC_STATS, potion_stat_cap=stat_id("potion_stat_cap"), potion_skill_cap=stat_id("potion_skill_cap"))
    out = {}
    for n in IU_STATS:
        v = stat_of(Hl("stat player %d" % ids[n], log)[1]) or 0
        out[n] = v / 256.0 if n in IU_FIXED else v
    return out


def iu_verdict(code, lvl, before, after):
    """[problem, ...]: every stat of Median's calc must change by its delta, every other read stat must stay."""
    want = iu_expected(code, lvl, before)
    bad = []
    for n in IU_STATS:
        d = after[n] - before[n]
        exp = want.get(n, 0)
        if abs(d - exp) > (1 if n in IU_FIXED else 0):
            bad.append("%s %s: %+g, Median %+g" % (code, n, d, exp))
    return bad


def check_iu_use():
    """unported.md "Item use pSpell 3 / 10": Signets of Learning / Greater Learning / Experience / Gold / Skill, Life and Mana Pack
    (pSpell 3) on the player path: each dropped next to the character, picked up by a click into the
    backpack and used by a right click. PASS: each used up and its stats moved by Median's calc, nothing else, no engine assert.
    SET-UP: level IU_LEVEL by harness (the calcs read the level); max life / mana raised to IU_ROOM, life / mana lowered before
    the packs; mana regeneration off; the item drop."""
    mark, log, rows, bad, shots = engine_mark(), [], [], [], []
    goto(1)
    rc2_set_level(int(os.environ.get("MXL_IU_LEVEL", IU_LEVEL)), log)
    only = set(filter(None, (os.environ.get("MXL_IU_ONLY") or "").split(",")))
    rp_packclear(log)
    Hl("stat player %d set -100" % stat_id("manarecoverybonus"), log)  # mana regenerates tens a second: off for the measurement
    for code in IU_ITEMS:
        if only and code not in only:
            continue
        r = row_of("misc", "code", code) or {}
        lvl = stat_of(Hl("stat player 12", log)[1])
        if code == "zog":
            Hl("stat player 7 set %d" % IU_ROOM, log)
            Hl("stat player 6 set %d" % (IU_ROOM // 4), log)
        if code == "zoh":
            Hl("stat player 9 set %d" % IU_ROOM, log)
            Hl("stat player 8 set 0", log)
        if not right_panel_open():
            g.press("i")
            time.sleep(1.0)
        iid = rp_ground_item(code, log)
        if iid is None or not rp_pickup(iid, log):
            bad.append("%s: not made / not picked up" % code)
            continue
        if held_item():
            Hl("pkt 18 " + _le(iid, 2, 0, 0), log)
            time.sleep(0.5)
        it = rp_item_line(iid)
        if it is None:
            bad.append("%s: not in the backpack" % code)
            continue
        before = iu_read(log)
        g.click(*rp_inv_xy(it["x"], it["y"]), button="right")
        time.sleep(1.5)
        after = iu_read(log)
        gone = rp_item_line(iid) is None
        moved = {n: round(after[n] - before[n], 2) for n in IU_STATS if after[n] != before[n]}
        rows.append("%s %s (pSpell %s, level %s): %s, moved %s, Median %s" % (
            code, r.get("name"), r.get("pSpell"), lvl, "used up" if gone else "KEPT", moved, iu_expected(code, lvl, before)))
        if not gone:
            bad.append("%s: not used up" % code)
        bad += iu_verdict(code, lvl, before, after)
        shots.append(sh("iu_%s" % code.replace("!", "x").replace("@", "a")))
        if not game_alive():
            bad.append("the game died after %s" % code)
            break
        rp_packclear(log)
    close_right_panel()
    # the signets' caps (potion_stat_cap, potion_skill_cap) are Median-only saved stats: they must come back after Save and Exit
    caps0 = {n: v for n, v in iu_read(log).items() if n.startswith("potion_")}
    caps1 = caps0 if only and not only & {"zkq", "zky", "!@B"} else None
    if caps1 is None:
        caps1 = {n: v for n, v in iu_read(log).items() if n.startswith("potion_")} if leave_and_reenter() else {}
        rows.append("Save and Exit + Play: %s -> %s (ids %s / %s)" % (caps0, caps1, stat_id("potion_stat_cap"),
                                                                       stat_id("potion_skill_cap")))
        if caps1 != caps0:
            bad.append("the potion caps changed over Save and Exit")
    Hl("stat player %d set 0" % stat_id("manarecoverybonus"), log)
    finish("iu_use", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-300:],
           partial="harness set-up (level, life / mana lowered, item dropped on the ground)")


CHECKS += [("iu_use", check_iu_use)]


# lane unported: unported.md "Mercenary level above 99 (ME9)". Median's hireling rows have Exp/Lvl 1, so level L starts at
# L * L * (L + 1) experience (rc_setup.merc_exp_for_level); the player is level 120 in Median. The engine stops a mercenary's
# experience one level below experience.txt's MaxLvl (1.13c: 98 under MaxLvl 99), so Median's mercenary ends at 119.
ML_STEPS = (100, 110, 119, 120)  # levels the mercenary is pushed to, one experience point short each time
ML_MAX = 119


def ml_start(level):
    return level * level * (level + 1)


def ml_want(target, player_level):
    """The level Median expects after the push to `target`: the mercenary's level never passes the player's, nor ML_MAX
    (1.13c)."""
    return min(target, player_level, ML_MAX)


# Median's ExpRatio leaves a mercenary near 119 nothing of a Blood Moor zombie: r_alpha (Exp 2000) in the act 5 Siege (level 41)
ML_AREA = int(os.environ.get("MXL_ML_AREA", 110))
ML_MON = os.environ.get("MXL_ML_MON", "1183")
ML_PLAYER = int(os.environ.get("MXL_ML_PLAYER", 120))  # a lower player level checks the cap at the player's own level


def ml_gain(mid, log, rounds=36):
    """Experience for the mercenary: the player's kills next to it (it takes its share), then D2R's own award (`xp`). Returns
    the merc dict afterwards."""
    for _ in range(rounds):
        m, _w = merc_info()
        Hl("spawn %s 1" % ML_MON, log)
        H("kill nearest %s" % ML_MON)
        time.sleep(0.6)
        m2, _w = merc_info()
        if m and m2 and m2.get("exp", 0) > m.get("exp", 0):
            return m2
    Hl("xp 100000000", log)
    time.sleep(1.0)
    return merc_info()[0]


def check_ml_merc():
    """unported.md ME9: Median's mercenary follows the player past 99, to 119 (ML_MAX). SET-UP: Kashya's hire (gold and her
    quest gate by harness, the hire itself by her menu), the player at level ML_PLAYER, the mercenary's experience (stat 13)
    put one point below each step's start, its level (stat 12) one below and its life raised. Judged: the level the game gives
    the mercenary after experience from kills, and the level and experience after Save and Exit + Play."""
    mark, log, rows, bad, shots = engine_mark(), [], [], [], []
    goto(1)
    m = merc_info()[0] or hire_in(1, 1, 150, "Kashya", 271, log, rows, bad)
    if m is None:
        return finish("ml_merc", False, "; ".join(rows + bad), mark, shots, log)
    rc2_set_level(ML_PLAYER, log)
    goto(ML_AREA)
    time.sleep(4)
    steps = [int(x) for x in (os.environ.get("MXL_ML_STEPS") or "").split(",") if x] or ML_STEPS
    for target in steps:
        m = merc_info()[0]
        if not m:
            bad.append("no mercenary before step %d" % target)
            break
        mid = m["id"]
        Hl("stat mon:%d 7 set %d" % (mid, 100000 << 8), log)  # the spawns hit back: the mercenary must outlive them
        Hl("stat mon:%d 6 set %d" % (mid, 100000 << 8), log)
        Hl("stat mon:%d 13 set %d" % (mid, ml_start(target) - 1), log)
        Hl("stat mon:%d 12 set %d" % (mid, target - 1), log)
        m2 = ml_gain(mid, log) or {}
        want = ml_want(target, ML_PLAYER)
        rows.append("push to %d: level %s exp %s -> level %s exp %s (Median %d)" % (
            target, target - 1, ml_start(target) - 1, m2.get("level"), m2.get("exp"), want))
        if m2.get("level") != want:
            bad.append("step %d: level %s, Median %d" % (target, m2.get("level"), want))
        shots.append(sh("ml_merc_%d" % target))
    m0 = merc_info()[0] or {}
    leave_and_reenter()
    time.sleep(4)
    m1 = {}
    for _ in range(15):
        m1 = merc_info()[0] or {}
        if m1:
            break
        time.sleep(2)
    rows.append("Save and Exit + Play: level %s exp %s -> level %s exp %s" % (m0.get("level"), m0.get("exp"), m1.get("level"),
                                                                            m1.get("exp")))
    if (m0.get("level"), m0.get("exp")) != (m1.get("level"), m1.get("exp")):
        bad.append("the mercenary's level / experience changed over Save and Exit")
    finish("ml_merc", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, rows + log[-300:],
           partial="harness set-up (hire gate and gold, player level, mercenary experience / level / life, spawned monsters)")


CHECKS += [("ml_merc", check_ml_merc)]


# ---------------------------------------------------------------- lane sound: bugs #501 (Raid's charged Blink) / #502 (spirit summons)
# A dev DLL started with MXL_SOUND_TRACE=<file> (sound_guard.cpp) writes, about once a second, how often each sound id went
# through the client's sound functions; snd_trace() reads it ({} without the trace) and snd_delta() lists the ids that grew.
SND_ANCIENT_DEATH_HD = 6754  # sounds.txt *Index of ancient_death_hd (plugin sound_guard_logic.h AncientDeathHd)
SND_SPIRITS = (433, 434, 435)  # Guardian / Defender / Protector Spirit: monsters 1085-1087, drawn with D2R's HD Ancients
SND_BLINK = 346  # Blink: Raid's charged skill (runes.txt mxl2012:Raid, charged 346 level 5)
SND_JAVELIN = "132"  # Javelin (Grade 1), a Raid base


def snd_trace():
    """{sound id: (variant picks, client plays)} of the MXL_SOUND_TRACE file, {} when there is none."""
    path, out = os.environ.get("MXL_SOUND_TRACE"), {}
    try:
        for ln in open(path or ""):
            p = [int(x) for x in ln.split()]
            if len(p) == 8:
                out[p[0]] = (p[5], p[7])
    except (OSError, ValueError):
        pass
    return out


def snd_ids():
    """{sounds.txt name: id}: the id is the *Index column (a blank row is id 0), read without quote handling as the game does."""
    import csv
    with open(os.path.join(EXCEL, "sounds.txt"), encoding="latin-1", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    ix = rows[0].index("*Index")
    return {r[0]: int(r[ix]) for r in rows[1:] if len(r) > ix and r[0] and r[ix].isdigit()}


def snd_delta(a, b):
    """{id: (variant picks, client plays)} that grew between two snd_trace() snapshots."""
    return {i: (v[0] - a.get(i, (0, 0))[0], v[1] - a.get(i, (0, 0))[1]) for i, v in b.items() if v != a.get(i, (0, 0))}


def snd_skipped():
    """The plugin's spiritsound skip count (`mxl2012` line '...; plays skipped N'), None without the line."""
    line = mxl_part(mxl_text().splitlines(), "spiritsound")
    m = re.search(r"plays skipped (\d+)", line)
    return (int(m.group(1)) if m else None), line


def check_snd_spirits():
    """Bug #502 (lane sound): the Barbarian's spirit summons played D2R's Ancients death roar (ancient_death_hd) in HD each time
    one died or was cast again. SET-UP: a Barbarian of the check's own (SndBarb), the three spirit skills at level 10 by harness
    `setskill`. Per graphics mode in town: each spirit is cast by a right click, cast again 8 times (the old one dies) and the
    spirits are killed by harness. PASS: the plugin's `spiritsound` count grew in HD, and with MXL_SOUND_TRACE the trace shows no
    variant pick of ancient_death_hd in either mode; the game alive."""
    mark, log, shots, rows, bad = engine_mark(), [], [], [], []
    if not switch_character("SndBarb", "barbarian", 4):
        return finish("snd_spirits", False, "no Barbarian", mark, shots, log)
    traced = bool(os.environ.get("MXL_SOUND_TRACE"))
    with Tank(), Level(120):  # a new Barbarian: level 1 refuses the skill points, 5 mana casts nothing (regress013 runB / runB2)
        snd_spirit_modes(traced, log, shots, rows, bad)
    set_graphics("hd")
    if not game_alive():
        bad.append("the game is gone")
    finish("snd_spirits", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log,
           partial=None if traced else "no MXL_SOUND_TRACE: the HD death roar judged by the plugin's count only")


def snd_spirit_modes(traced, log, shots, rows, bad):
    """check_snd_spirits per graphics mode: cast, re-cast and kill the spirits; rows / bad filled."""
    for mode in ("hd", "legacy"):
        set_graphics(mode)
        goto(1)
        time.sleep(3)
        n0, _ = snd_skipped()
        t0 = snd_trace()
        for sid in SND_SPIRITS:
            learn(sid, 10)
            Hl("skill right %d" % sid, log)
            g.click(0.56, 0.47, button="right")
            time.sleep(2)
        for k in range(8):
            g.click(0.56 if k % 2 == 0 else 0.44, 0.47, button="right")
            time.sleep(1.5)
        shots.append(sh("snd_spirits_%s" % mode))
        for m in [m for m in hstate()["mons"] if m.get("class") in (1085, 1086, 1087)]:
            Hl("kill %d" % m["id"], log)
        time.sleep(4)
        n1, line = snd_skipped()
        d = snd_delta(t0, snd_trace()).get(SND_ANCIENT_DEATH_HD, (0, 0))
        rows.append("%s: spiritsound skips %s -> %s, ancient_death_hd variant picks %s, client plays %s%s" % (
            mode, n0, n1, d[0], d[1], "" if traced else " (no trace)"))
        if mode == "hd" and (n0 is None or n1 is None or n1 <= n0):
            bad.append("HD: no ancient_death_hd play skipped (%s)" % (line or "no spiritsound line"))
        if traced and d[0] > 0:
            bad.append("%s: ancient_death_hd played %d times" % (mode, d[0]))


CHECKS += [("snd_spirits", check_snd_spirits)]


def check_snd_blink():
    """Bug #501 (lane sound): Raid (runeword, javelin) gives Blink (346) as level 5 charges. SET-UP: an Amazon of the check's own
    (SndAma), a Javelin with 60 charges of Blink level 5 by harness `equip` in the right hand, selected for the right button with
    the item's id (as the game's charged-skill list does). Per graphics mode outside town: 12 Blinks by right click. PASS: Blink
    selected, the player moved, the charges went down, the Blink sounds (baal_teleport, druid_shockwave) resolved when traced,
    no new assert, the game alive."""
    mark, log, shots, rows, bad = engine_mark(), [], [], [], []
    if not switch_character("SndAma", "amazon", 0):
        return finish("snd_blink", False, "no Amazon", mark, shots, log)
    names = snd_ids()
    for mode in ("hd", "legacy"):
        set_graphics(mode)
        goto(2)
        time.sleep(3)
        item = None
        for code, body, extra in ((SND_JAVELIN, "rhand", " 70=60"), ("rin", "rring", "")):  # the ring when the javelin is refused
            Hl("unequip %s" % body, log)
            _ok, lines = Hl("equip %s normal%s 204:%d=%d %s" % (code, extra, SND_BLINK << 6 | 5, 60 << 8 | 60, body), log)
            item = first(lines, r"item id=(\d+)")
            if item:
                rows.append("%s: Blink charges on %s" % (mode, code))
                break
        sel, _ = Hl("skill right %d %d" % (SND_BLINK, item or 0), log)
        if not (item and sel):
            bad.append("%s: the charged Blink was not selected (item %s)" % (mode, item))
            continue
        t0, p0 = snd_trace(), hstate()["player"]
        moved = 0
        for k in range(12):
            dx = 5 if k % 2 == 0 else -5
            before = hstate()["player"]
            g.click((800 + dx * 27) / 1600, (405 - dx * 13.5) / 900, button="right")
            time.sleep(1.4)
            after = hstate()["player"]
            moved += (before.get("x"), before.get("y")) != (after.get("x"), after.get("y"))
        shots.append(sh("snd_blink_%s" % mode))
        d = snd_delta(t0, snd_trace())
        heard = {n: d.get(names.get(n), (0, 0))[0] for n in ("baal_teleport", "druid_shockwave", "fingermage_hit_1")}
        rows.append("%s: item %s, moved on %d of 12 Blinks, sounds %s" % (mode, item, moved, heard if d else "(no trace)"))
        if moved < 6:
            bad.append("%s: the player moved on %d of 12 Blinks" % (mode, moved))
        if d and not heard["baal_teleport"]:
            bad.append("%s: no baal_teleport" % mode)
        if not game_alive():
            bad.append("%s: the game is gone" % mode)
            break
    set_graphics("hd")
    finish("snd_blink", not bad, "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log,
           partial="the sound itself is judged by the client's sound calls, not by ear")


CHECKS += [("snd_blink", check_snd_blink)]


# --- bug #493 (play test 0.1.1): totems "slow / lose effects" after Bend the Shadows ---------------------------------------------
TS_TOTEMS = (488, 495, 493, 497)  # Death's Fury, Fireheart, Frostclaw, Stormeye: each needs a corpse (TargetCorpse)
TS_BLINK = 486  # Bend the Shadows: teleport to a minion; pettype `totemic` warp 1 gathers the totems to the player


def ts_totems():
    """(player (x, y), [(class, id, mx, my), ...]) of the living totems (monstats 1072-1080) right now."""
    st = hstate()
    p = st["player"]
    tms = [(m["class"], m["id"], m.get("mx"), m.get("my")) for m in st["mons"]
           if 1072 <= (m.get("class") or 0) <= 1080 and m.get("mode") not in (0, 12)]
    return (p.get("x"), p.get("y")), tms


def ts_judge(ox, oy, after, tag):
    """The problems of one gather: totems sharing a sub-tile, one on or next to the player's sub-tile (within one, the plugin's
    "on the owner"; bug #509 left one at +1,-1), one not gathered."""
    bad, spots = [], [(x, y) for _c, _i, x, y in after]
    if len(set(spots)) != len(spots):
        bad.append("%s: totems share a sub-tile" % tag)
    on = [(x - ox, y - oy) for x, y in spots if max(abs(x - ox), abs(y - oy)) <= 1]
    if on:
        bad.append("%s: a totem is on the player's spot %s" % (tag, on))
    far = [(x, y) for x, y in spots if max(abs(x - ox), abs(y - oy)) > 9]
    if far:
        bad.append("%s: totems not gathered: %s" % (tag, far))
    return bad


def check_totem_spread():
    """Bug #493 (player: "Totems slow / lose effects after Shadow Blink"; owner ruling 2026-10-29: they still warp with the
    player but must not stack). A Necromancer casts the four totems on zombie corpses 3 sub-tiles apart, then Bend the Shadows
    (486) by a background right click on the first totem. D2R's gather (0x500a40) puts every totem on the player's own sub-tile;
    the plugin part `petspread` moves each to a free spot round the player. Bug #509: next to the rocks and torch of the Blood Moor
    spot one totem stayed on the player now and then, so the check blinks `MXL_TS_ROUNDS` times (default 6), each time onto the
    next totem, which stands on a ring spot near the rocks. PASS when after every blink all totems were gathered (none farther than
    9 sub-tiles), no two share a sub-tile, none is within one sub-tile of the player, and the `petspread` line counts spread totems and
    no missed one. SHORTCUT: skill levels, level 120 and Tank by the harness, corpses from spawned zombies, the totems cast by `cast`."""
    mark, log, shots, notes, bad = engine_mark(), [], [], [], []
    ln = mxl_part(mxl_text().splitlines(), "petspread")
    notes.append("plugin: %s" % (ln[:200] or "no petspread line"))
    if not ln or "FAILED" in ln or ln.startswith("petspread off"):
        bad.append("petspread not on")
    rounds = max(1, int(os.environ.get("MXL_TS_ROUNDS", "6")))
    goto(2)
    with Tank(), Level(120):
        for sid in TS_TOTEMS + (TS_BLINK,):
            learn(sid, 20)
        for _ in range(30):
            ok, _l = H("kill nearest")
            if not ok:
                break
        px, py = player_xy()
        for k, sid in enumerate(TS_TOTEMS):
            _, sp = Hl("spawn 5 1 %d %d" % (px - 4 + 3 * k, py + 4), log)
            cid = first(sp, r"id=(\d+)")
            time.sleep(0.4)
            Hl("kill %s" % cid, log)
            time.sleep(1.0)
            Hl("cast %d unit %s" % (sid, cid), log)
            time.sleep(1.2)
        _, before = ts_totems()
        notes.append("before: %s" % [(c, x, y) for c, _i, x, y in before])
        shots.append(sh("totem_spread_before"))
        if len(before) < 4:
            bad.append("only %d totems cast" % len(before))
        Hl("skill right %d" % TS_BLINK, log)
        after, blinks = before, 0
        for r in range(rounds):
            if not after:
                break
            p0 = player_xy()
            target = after[r % len(after)]
            click_unit(target[1], button="right")
            time.sleep(1.5)
            (ox, oy), after = ts_totems()
            notes.append("blink %d onto %d: player %s -> %s; after: %s" % (r + 1, target[0], p0, (ox, oy),
                                                                          [(x - ox, y - oy) for _c, _i, x, y in after]))
            if r == 0:
                shots.append(sh("totem_spread_after"))
            if (ox, oy) == p0:
                notes.append("blink %d: the right click did not blink the player" % (r + 1))
                continue
            blinks += 1
            got = ts_judge(ox, oy, after, "blink %d" % (r + 1))
            if got:
                shots.append(sh("totem_spread_bad_%d" % (r + 1)))
            bad += got
        if blinks == 0:
            bad.append("the right click did not blink the player")
        notes.append("blinks %d of %d" % (blinks, rounds))
        ln = mxl_part(mxl_text().splitlines(), "petspread")
        notes.append("plugin after: %s" % ln[ln.find("onto the owner"):])
        m = re.search(r"spread (\d+)", ln)
        if not m or int(m.group(1)) == 0:
            bad.append("petspread counted no spread")
        m = re.search(r"missed (\d+)", ln)
        if m and int(m.group(1)) > 0:
            bad.append("petspread missed %s totem(s)" % m.group(1))
        for _c, i, _x, _y in after:
            H("kill %d" % i)
    note = "; ".join(notes) + ("; PROBLEMS: " + "; ".join(bad) if bad else "")
    finish("totem_spread", not bad, note, mark, shots, log, partial="harness set-up (skill levels, level, Tank, spawned corpses, totems cast by `cast`)")


CHECKS += [("totem_spread", check_totem_spread)]

# Owner ruling 2026-10-29 (lane apple): `petspread` moves totems only. Median XL 2012 has no golem skill (D2R's golem rows 290-292
# are made by no Median skill), so the walking necromancer pet is Summon Shadows (473, pettype `shadowspet`, warp 1).
PK_PET = 473
PK_COUNTERS = ("owner moves with pets", "pet warps", "onto the owner", "spread", "other pets left")


def pk_counts():
    """The `petspread` line's counters {name: n} and the line."""
    ln = mxl_part(mxl_text().splitlines(), "petspread")
    return {k: int(v) for k, v in re.findall(r"(%s) (\d+)" % "|".join(PK_COUNTERS), ln)}, ln


def pk_pets(ids):
    """(player (x, y), {id: (class, mx, my, distance in sub-tiles)}) of the given monster ids right now."""
    st = hstate()
    p = st["player"]
    px, py = p.get("x"), p.get("y")
    return (px, py), {m["id"]: (m.get("class"), m.get("mx"), m.get("my"), max(abs(m["mx"] - px), abs(m["my"] - py)))
                      for m in st["mons"] if m.get("id") in ids and m.get("mx") is not None}


def pk_step(what, ids, c0, notes, bad):
    """After an owner move: the pets' spots right away and the counter changes. Other pets must not be spread."""
    (px, py), pets = pk_pets(ids)
    c1, ln = pk_counts()
    d = {k: c1.get(k, 0) - c0.get(k, 0) for k in PK_COUNTERS}
    notes.append("%s: player at %s,%s; pets %s; petspread +%s" % (what, px, py, pets, d))
    if d["spread"]:
        bad.append("%s: petspread moved %d pet(s) that are no totems" % (what, d["spread"]))
    return c1, d, pets


def check_pet_keep():
    """Owner ruling 2026-10-29: only totems leave the owner's spot. A Necromancer with a Kashya mercenary and Summon Shadows (473)
    moves twice: Bend the Shadows (486, right click on the shadow pet: D2R's owner move `0x491ca0` -> `0x500a40`) and a real
    waypoint (Rogue Encampment -> Cold Plains). After each the `petspread` line must count no spread (the mercenary and the shadow
    keep D2R's placement: `onto the owner` / `other pets left` count them when D2R set them on the player's sub-tile), and their
    spots right after the move are noted. SET-UP: the hire gate quest bit and gold (hire_in), skill levels, level 120 and Tank by
    the harness, the shadow cast by `cast`, the Cold Plains waypoint bit."""
    mark, log, shots, notes, bad = engine_mark(), [], [], [], []
    goto(1)
    merc = merc_info()[0] or hire_in(1, 1, 150, "Kashya", 271, log, notes, bad)
    if merc is None:
        return add("pet_keep", "BLOCKED", "no mercenary: " + "; ".join(notes + bad), shots, log)
    with Tank(), Level(120):
        learn(PK_PET, 20)
        learn(TS_BLINK, 20)
        goto(2)
        ids0 = {m["id"] for m in hstate()["mons"]}
        Hl("cast %d self" % PK_PET, log)
        time.sleep(2.0)
        merc = merc_info()[0] or merc
        shadows = [m for m in hstate()["mons"] if m["id"] not in ids0 and m["id"] != merc.get("id") and m.get("mode") not in (0, 12)]
        ids = {merc.get("id")} | {m["id"] for m in shadows}
        notes.append("mercenary id %s class %s; shadow pets %s" % (merc.get("id"), merc.get("class"), [(m["id"], m.get("class")) for m in shadows]))
        if not shadows:
            bad.append("Summon Shadows made no pet")
        c0, ln = pk_counts()
        if not ln or "FAILED" in ln or ln.startswith("petspread off"):
            bad.append("petspread not on (%s)" % ln[:80])
        # 1) Bend the Shadows onto the shadow pet, about 10 sub-tiles away first
        if shadows:
            px, py = player_xy()
            Hl("move %d %d" % (px + 10, py), log)
            time.sleep(2.5)
            Hl("skill right %d" % TS_BLINK, log)
            p0 = player_xy()
            for _ in range(3):  # the shadow walks after its owner: click its spot of the moment again until the player blinks
                click_unit(shadows[0]["id"], button="right")
                time.sleep(1.0)
                if player_xy() != p0:
                    break
            c0, d, _pets = pk_step("Bend the Shadows", ids, c0, notes, bad)
            shots.append(sh("pet_keep_blink"))
            if player_xy() == p0:
                bad.append("the right click did not blink the player")
            elif not d["owner moves with pets"]:
                bad.append("Bend the Shadows: the owner move brought no pets")
            elif d["other pets left"] < 1:
                bad.append("Bend the Shadows: petspread left no pet to D2R")
        # 2) a real waypoint: Rogue Encampment -> Cold Plains
        H("waypoint n 1 set")
        area = rp_waypoint_to(3, log)
        time.sleep(0.3)
        _c, d, pets = pk_step("waypoint to Cold Plains (area %s)" % area, ids, c0, notes, bad)
        shots.append(sh("pet_keep_waypoint"))
        if area != 3:
            bad.append("the waypoint did not reach Cold Plains (area %s)" % area)
        if merc.get("id") not in pets:
            bad.append("the mercenary did not come along")
        # the spots above are read after the arrival, when the mercenary may already walk off (16 sub-tiles in run
        # checks-20261030-005939-s3, 4 in -005552-s3): the counters say where D2R set them
        if d["other pets left"] < len(ids):
            bad.append("waypoint: petspread left %d pet(s) to D2R, want %d (the mercenary and the shadow)" % (d["other pets left"], len(ids)))
        goto(1)
    finish("pet_keep", not bad, "; ".join(notes) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log,
           partial="harness set-up (hire gate, skill levels, level, Tank, the shadow cast by `cast`)")


CHECKS += [("pet_keep", check_pet_keep)]


# ---------------------------------------------------------------- lane unporteda: the class (a) rows of docs/unported.md
# `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all ua_look` (MXL_UA=<stages>, default all of
# `mons ui item maps drop`). Graphics checks seen with the harness (spawn / travel shortcuts, god mode), judged by hand on the shots;
# `item` reads the tooltip text through `itemdesc` (the inventory tooltip's own builder) and needs no hand.
# (area, monstats Id, why it is looked at). Not here: the D2R-native Ids without an HD unit (chaoshorde1-4, suckernest1-4, familiar,
# poisonorb, firebeast, iceglobe) are disabled rows (bugs.md #70): they never spawn, and a harness spawn only asserts.
UA_MONSTERS = [(2, "quest_butcher", "token BU: Butcher art not shipped, blunderbore1 in HD"),
               (2, "super_kabraxis", "token BU: megademon1 in HD"),
               (2, "sarandesh1", "!7: odd-sized s1 / sc COFs"), (2, "psychorbM", "X+: odd-sized dt COF")]
UA_STAGES = ("mons", "horned", "ui", "item", "maps", "drop")
# (code, why, {stat: allowed values}): group 401 has two rows of equal frequency per pattern, one with the socket and one without
UA_ITEMS = [("7@5", "bswd: automagic sockBarSW (str-add 76, sock 1 or none)", {"strength_bonus_wpn": (76,), "item_numsockets": (0, 1)}),
            ("614", "tors: automagic sockNormal (sock 1 or none)", {"item_numsockets": (0, 1)})]
UA_AUTOMAP = {84: "excelsior3", 60: "desertpeak"}


def ua_stages(env=None):
    v = (env if env is not None else os.environ).get("MXL_UA", "")
    want = [s.strip() for s in v.split(",") if s.strip()]
    return [s for s in UA_STAGES if not want or s in want]


def ua_ui(log, shots):
    """Classic (and HD for comparison) inventory with the weapon swap tabs, and the skill tree's opening page with its tab labels."""
    for mode in ("legacy", "hd"):
        goto(1)
        if not set_graphics(mode):
            log.append("graphics %s not reached" % mode)
            continue
        close_right_panel()
        g.press("i")
        time.sleep(1.5)
        shots.append(sh("ua_inv_%s" % mode))
        g.press("i")
        time.sleep(0.8)
        g.press("t")
        time.sleep(1.5)
        shots.append(sh("ua_tree_%s" % mode))
        g.press("t")
        time.sleep(0.8)
        log.append("ui %s: inventory and skill tree shot" % mode)


def ua_item(log, shots, rows):
    """A normal-quality base of each automagic group 401 pattern: the item's stats (`istat`) hold the automagic roll; its tooltip
    line is judged by hand on the ua_item_* shot (Median's `strength_bonus_wpn` line is white by its own string, ÿc0)."""
    goto(1)
    for code, why, want_stats in UA_ITEMS:
        _, ln = Hl("item %s q=2 inv" % code, log)
        made = parse_items(ln)
        if not made:
            rows.append((code, False, "%s not made" % code))
            continue
        it = made[0]
        got = {}
        for name in want_stats:
            _, ln = Hl("istat %d %d" % (it["id"], stat_id(name)), log)
            got[name] = cube_game.istat_value(ln) or 0
        rc_open_inventory()
        hover_px(*inv_px(it["x"], it["y"]))
        time.sleep(0.8)
        shots.append(sh("ua_item_%s" % code))
        close_right_panel()
        want = all(got[n] in ok for n, ok in want_stats.items())
        rows.append((code, want, "%s (%s): %s" % (code, why, ", ".join("%s %s" % kv for kv in got.items()))))
        H("remove %s" % code)


def ua_maps(log, shots, rows):
    """charismatic (127): the preset objects the header act resolved, in HD; automap (Tab) on two Median maps in HD."""
    st = goto(127, timeout=60)
    if st["player"].get("area") != 127:
        rows.append(("charismatic", False, "not reached"))
    else:
        time.sleep(5)
        names = []
        for o in parse_presets(Hl("presets 2", log)[1]):
            r = row_of("objects", "*ID", o["class"]) or {}
            names.append("%d %s" % (o["class"], r.get("Name") or "?"))
        for o in parse_objects(Hl("objects", log)[1]):
            r = row_of("objects", "*ID", o["class"]) or {}
            names.append("near %d %s" % (o["class"], r.get("Name") or "?"))
        shots.append(sh("ua_charismatic_0"))
        rows.append(("charismatic", True, "objects: %s" % ", ".join(sorted(set(names)))[:600]))
    for lv, name in UA_AUTOMAP.items():
        st = goto(lv, timeout=60)
        p = st["player"]
        if p.get("area") != lv:
            rows.append(("automap " + name, False, "not reached"))
            continue
        time.sleep(4)
        x0, y0 = p.get("x"), p.get("y")
        for dx, dy in ((10, 0), (10, 10), (0, 10), (0, 0)):  # walk the arrival a little so the automap has cells
            H("place %d %d" % (x0 + dx, y0 + dy))
            time.sleep(1.5)
        g.press("tab")
        time.sleep(1.2)
        shots.append(sh("ua_automap_%s" % name))
        g.press("tab")
        time.sleep(0.5)
        rows.append(("automap " + name, True, "Tab shot after a short walk (judged by hand: ua_automap_%s)" % name))


def ua_horned(log, shots, rows):
    """`hornedgods` (8@: 5 COFs of 1 frame against animdata, bugs.md #110) is a Trap-Poison ally that dies at its first tick with no
    enemy in range (bugs.md #41): monstats class 1 (lane fixes2's `spawn 1 3`) is spawned first, then it beside them. PASS: alive
    (not a corpse) in both modes. Lane unporteda saw it alive and drawn in neither mode: its monprop `fade` (stat 181) hides it, as
    the helper it is (pettype hornedgodspet, no summon skill, no preset: nothing on the player path spawns it)."""
    row = row_of("monstats", "Id", "hornedgods")
    for mode in ("legacy", "hd"):
        goto(1)
        if not set_graphics(mode):
            rows.append(("hornedgods " + mode, False, "graphics mode not reached"))
            continue
        goto(2)
        px, py = player_xy()
        Hl("spawn 1 3 %d %d" % (px + 10, py - 10), log)
        _, sp = Hl("spawn %s 1 %d %d" % (row["*hcIdx"], px + 6, py - 6), log)
        uid = first(sp, r"id=(\d+)")
        if uid is None:
            rows.append(("hornedgods " + mode, False, "not spawned"))
            continue
        alive = []
        for k, wait in enumerate((0.6, 2.0, 3.0)):
            time.sleep(wait)
            shots.append(sh("ua_horned_%s_%d" % (mode, k)))
            st = hstate()
            alive.append(any(str(m.get("id")) == str(uid) for m in st["mons"]))
            log.append("hornedgods %s t%d: mons %s; corpses %s" % (mode, k, [(m.get("id"), m.get("class"), m.get("mode")) for m in st["mons"]],
                                                              [(m.get("id"), m.get("class")) for m in st["corpses"]]))
            log.extend("hornedgods %s t%d: %s" % (mode, k, ln) for ln in st["lines"] if "id=%s " % uid in ln)
        H("kill %s" % uid)
        time.sleep(1.5)
        shots.append(sh("ua_horned_%s_death" % mode))
        rows.append(("hornedgods " + mode, alive[0], "unit %s alive at 0.6 / 2.6 / 5.6 s: %s (judged by hand: ua_horned_%s_*)"
                     % (uid, alive, mode)))


def ua_drop():
    """Owner 2026-10-29: `cougar` dropped (enabled 0): the harness spawn of its row makes no unit. D2R answers a disabled row with
    one `MONFLAG_ENABLED` assert (bugs.md #70, as for its own disabled rows): that assert is the expected answer here, any other
    fails the check. Own result `ua_drop`."""
    mark = engine_mark()
    log = []
    goto(2)
    r = row_of("monstats", "Id", "cougar")
    if r is None:
        return add("ua_drop", "FAIL", "the cougar row is missing (it must stay: the ids after it)", (), log)
    _, sp = Hl("spawn %s 1" % r["*hcIdx"], log)
    uid = first(sp, r"id=(\d+)")
    if uid is not None:
        H("kill %s" % uid)
    asserts = engine_asserts(mark)
    other = [m for m, _ in asserts if "MONFLAG_ENABLED" not in m]
    bad, _known = engine_issues(mark, log)
    bad = [b for b in bad if "MONFLAG_ENABLED" not in b]
    ok = uid is None and r.get("enabled") == "0" and not bad
    add("ua_drop", "PASS" if ok else "FAIL", "cougar row %s enabled=%s; spawn: %s; MONFLAG_ENABLED asserts %d, other engine issues: %s" % (
        r["*hcIdx"], r.get("enabled"), "no unit" if uid is None else "unit %s" % uid,
        len(asserts) - len(other), "; ".join(bad) or "none"), (), log)


def ua_look():
    """Lane unporteda: the look / check rows of docs/unported.md class (a). Stages (MXL_UA): `mons` the monsters of UA_MONSTERS in
    HD and classic (hm_monsters: spawn beside, far / near / fight / death shots, asserts counted); `ui` classic and HD inventory
    (weapon swap tabs) and skill tree (tab labels); `item` the automagic roll of group 401 bases (istat); `maps`
    charismatic's objects and the automap of two Median maps; `drop` the dropped cougar row spawns nothing (own result
    `ua_drop`); `horned` hornedgods beside enemy skeletons (it dies alone, bugs.md #41). SET-UP: god mode, the
    harness travels, spawns and makes items. PASS needs no engine assert; looks are judged by hand on the ua_* shots."""
    stages = ua_stages()
    if "mons" in stages:
        os.environ.setdefault("MXL_UA_MODES", "hd,legacy")
        hm_monsters("ua", UA_MONSTERS)
    if "drop" in stages:
        ua_drop()
    if not set(stages) & {"horned", "ui", "item", "maps"}:
        return
    mark = engine_mark()
    log, shots, rows = [], [], []
    enable_debug()
    cheat("god 1")
    if "horned" in stages:
        ua_horned(log, shots, rows)
    if "ui" in stages:
        ua_ui(log, shots)
    goto(1)
    set_graphics("hd")
    if "item" in stages:
        ua_item(log, shots, rows)
    if "maps" in stages:
        ua_maps(log, shots, rows)
    goto(1)
    cheat("god 0")
    rc_finish("ua_look", all(r[1] for r in rows), "; ".join("%s %s: %s" % (r[0], "ok" if r[1] else "BAD", r[2]) for r in rows),
              mark, shots, log, ["harness item / travel / spawn", "god mode (cheat god 1)"],
              judged_by_hand="the ua_horned_* / ua_inv_* / ua_tree_* / ua_item_* / ua_automap_* / ua_charismatic_* shots")


CHECKS += [("ua_look", ua_look)]


# lane itemart: candidate HD item pictures (docs/hd-icons.md "Picture review"). A graphics check with harness set-up, not a
# player-path verification: run it on a slot whose installed sprites carry the candidates (mxl2012-runs/itemart/trial.py,
# restored afterwards); the screenshots are judged by hand next to the D2R items in the same backpack.
ITEMART_SETS = [
    ("crystals", ["qus", "qut", "quy", "qux", "zkq", "dog", "yo1", "yo2", "yo3", "yo4", "yo5",
                  "gsb", "gpb", "gpw", "jew", "rin", "amu"]),
    ("runes", ["r34", "r35", "r36", "r37", "r38", "r39", "r40", "r41", "r42", "r43", "r44", "r45", "r46", "r47",
               "r48", "r49", "r50", "r01", "r10", "r26"]),
    # lane itemart2: the five Rainbow Stones (D2R's HD sapphires in Median's colours) beside D2R's five sapphires and gems
    ("rainbow", ["yo1", "yo2", "yo3", "yo4", "yo5", "gcb", "gfb", "gsb", "glb", "gpb", "gpr", "gpg", "gpy", "gpv", "gpw"]),
]


def itemart_pics():
    """Lane itemart: the candidate pictures (arcane crystals, signet, apple, rainbow stones, Median runes) in the backpack
    with D2R's own gems / charm / jewel / ring / amulet / runes, one backpack per set, shot in HD and in legacy graphics (G).
    PASS: every item made, the game alive; the pictures are judged by hand (itemart_<set>_hd.png against _legacy.png).
    MXL_ITEMART_SETS=<name>[,<name>]: only those sets (rainbow: lane itemart2's Rainbow Stones)."""
    mark = engine_mark()
    log, shots, bad = [], [], []
    goto(1)
    only = [x for x in os.environ.get("MXL_ITEMART_SETS", "").split(",") if x]  # e.g. MXL_ITEMART_SETS=rainbow
    sets = [(n, c) for n, c in ITEMART_SETS if not only or n in only]
    for name, codes in sets:
        Hl("packclear", log)
        for code in codes:
            _ok, ln = Hl("item %s inv" % code, log)
            if not any(("code=%s " % code) in x for x in ln):
                bad.append("%s not made" % code)
        if not set_graphics("hd"):
            bad.append("graphics mode hd not reached")
        if not right_panel_open():
            g.press("i")
            time.sleep(1.5)
        shots.append(sh("itemart_%s_hd" % name))
        close_right_panel()
        time.sleep(1.0)
        if not set_graphics("legacy"):
            bad.append("graphics mode legacy not reached")
        time.sleep(1.5)
        g.press("i")
        time.sleep(2.0)
        shots.append(sh("itemart_%s_legacy" % name))
        g.press("i")
        time.sleep(1.0)
        set_graphics("hd")
        close_right_panel()
    if not game_alive():
        bad.append("the game died")
    Hl("packclear", log)
    finish("itemart_pics", not bad, "sets: " + ", ".join("%s (%d items)" % (n, len(c)) for n, c in sets)
           + ("; PROBLEMS: " + "; ".join(bad) if bad else ""),
           mark, shots, log, partial="the pictures in itemart_*_hd.png / itemart_*_legacy.png are judged by hand")


CHECKS += [("itemart_pics", itemart_pics)]

# lane itemart (report only, no monster change): the most-seen Median-only monster stand-ins not judged by lane hdmonlook,
# ranked by the number of areas whose levels.txt mon / nmon / umon columns name them (docs/hd-monsters.md section 16).
ITEMART_MONSTERS = [(2, "centaur1", "clawviper1, `9!`, 24 areas"), (2, "darkfey1", "councilmember1, `!2`, 17 areas"),
                    (2, "creepshow1", "clawviper1, `#5`, 10 areas"), (2, "onyxknight1", "sandraider1, `0n`, 10 areas"),
                    (2, "fellfiend1", "warputriddefiler, `08`, 11 areas"), (2, "wyrdwolf1", "wolf, `^3`, 10 areas"),
                    (2, "fungus1", "thornhulk1, `2(`, 8 areas"), (2, "runepriest1", "councilmember1, `9(`, 8 areas"),
                    (2, "cavetroll1", "brute2, `~2`, 7 areas"), (2, "porkchop_elite2", "siegebeast1, `5$`, 7 areas"),
                    (2, "treeppl1", "thornhulk1, `!8`, 6 areas"), (2, "sarandesh1", "fetishblow1, `!7`, 5 areas"),
                    (2, "l4dwitch", "wraith1, `@1`, 4 areas"), (2, "magmademon1", "deathmauler1, `(l`, 18 areas"),
                    (2, "gargoylebeast1", "batdemon1, `!a`, 15 areas"), (2, "berserk1", "brute2, `(o`, 9 areas"),
                    (2, "flit1", "druidhawk, `(g`, 8 areas"), (2, "pest1", "brute2, `g7`, 8 areas"),
                    (2, "bugbear1", "brute2, `@f`, 8 areas"), (2, "crystal1", "cantor1, `b#`, 5 areas"),
                    (2, "deathwing1", "vulture1, `&b`, 7 areas")]


def itemart_mons():
    """Lane itemart: hm_monsters over ITEMART_MONSTERS (MXL_ITEMART_MODES=hd,legacy for both looks); judged by hand."""
    hm_monsters("itemart", ITEMART_MONSTERS)


CHECKS += [("itemart_mons", itemart_mons)]

# --- lane uppass: bug #511 / #292, the client's "Could not get act!" exit on entering the Underground Passage ---------------
# The player (0.1.3, legacy graphics, a mercenary with them) entered Underground Passage Level 1 (10) and the game closed: the
# client's handler of server command 0x15 (unit reassign; D2R table entry 0x22bbe38, code 0x12ab40) moved a unit and found no
# room for it (`0x34b440`), asserted "Could not get act!" (SCmd.cpp:1254) and called the exit (`0x12e5278(-1)` -> the fatal
# stub `0x12557f0`, image +0x1255802). This check walks into 10 (and 10 -> 14) the way the player did: a live, equipped
# Rogue, legacy graphics, the walk up to the warp tile and real left clicks on it, several rounds.
UP_ROUTES = "4-10,5-10,10-14"
UP_CLICK_RING = [(0, 0)] + [(r * ux, r * uy) for r in (2, 4) for ux, uy in ((1, 1), (-1, -1), (1, -1), (-1, 1), (1, 0), (0, 1), (-1, 0), (0, -1))]


def up_alive():
    """The game process still runs and the harness answers."""
    if not g.game_pids():
        return False
    try:
        return bool(hstate()["ok"])
    except Exception:
        return False


def up_merc_setup(log, rows, bad, shots):
    """SET-UP: a Rogue hired from Kashya (quest fixture of hire_in) and equipped by clicks on the hireling panel (HD coordinates:
    done before the switch to legacy). An existing live mercenary is kept."""
    m, worn = merc_info()
    if m is None:
        m = hire_in(1, 1, 150, "Kashya", 271, log, rows, bad)
        if m is None:
            return None
        worn = []
    if not [i for i in worn if i.get("page") == 255]:
        Hl("packclear", log)
        merc_panel_open(log, shots, "uppass")
        for code, body, allowed, what in MERC_GEAR[271]:
            if allowed:
                on, note = equip_by_click(code, body, log, shots, "uppass")
                rows.append("SET-UP mercenary %s on body %d: %s" % (what, body, note))
        panels_closed()
    m, worn = merc_info()
    rows.append("SET-UP mercenary id %s class %s level %s, worn %s" % (
        m and m.get("id"), m and m.get("class"), m and m.get("level"),
        ",".join(str(i.get("code")) for i in worn if i.get("page") == 255) or "none"))
    return m


def up_fill(n, log, rows):
    """SET-UP (MXL_UP_FILL=n): n more items in the backpack / cube (the player's character was item-heavy)."""
    codes = ("615", "600", "164", "101", "rin", "amu", "jew")
    made = 0
    for k in range(n):
        if H("item %s inv" % codes[k % len(codes)])[0] or H("item %s cube" % codes[k % len(codes)])[0]:
            made += 1
    rows.append("SET-UP: %d of %d items made in the backpack / cube" % (made, n))


def up_click_tile(tile, dest, log):
    """Real left clicks on and round the warp tile (the legacy view is not the HD projection rp_screen_xy computes, so a ring of
    spots round it, as glacial_click_spot). Returns the clicks made."""
    clicks = 0
    for up in (0, 40, 80):
        for ox, oy in UP_CLICK_RING:
            if not up_alive() or hstate()["player"].get("area") == dest:
                return clicks
            fx, fy = rp_screen_xy(tile["x"] + ox, tile["y"] + oy)
            fy -= up / 900
            g.click(min(max(fx, RP_SAFE[0] / 1600), RP_SAFE[2] / 1600), min(max(fy, RP_SAFE[1] / 900), RP_SAFE[3] / 900))
            clicks += 1
            time.sleep(2)
    return clicks


def up_tile_classes(level, dest):
    """Every warp tile class (lvlwarp Id) that leads from `level` to `dest` (levels.txt Vis<i> == dest -> Warp<i>): Stony Field
    and Dark Wood list four cave entrance variants (0-3) for area 10."""
    row = next((r for r in table("levels") if r.get("Id") == str(level)), None) or {}
    out = set()
    for i in range(8):
        w = row.get("Warp%d" % i)
        if row.get("Vis%d" % i) == str(dest) and w and w.lstrip("-").isdigit() and int(w) >= 0:
            out.add(int(w))
    return out


def up_click_through(src, dest, log):
    """In `src`: the nearest loaded warp tile to `dest`, a walk up to it (harness `move`), then real left clicks on it (the
    projection first, then a ring round it for the legacy view). Returns (entered, note)."""
    want = up_tile_classes(src, dest)
    p = hstate()["player"]
    tiles = [t for t in cache_tiles(Hl("tiles", log)[1]) if t["area"] == src and t["class"] in want]
    if not tiles:
        return False, "no loaded tile of class %s in %d" % (sorted(want), src)
    t = min(tiles, key=lambda t: (t["x"] - p["x"]) ** 2 + (t["y"] - p["y"]) ** 2)
    acts_walk(t["x"], t["y"], reach=6, timeout=60)
    in_dest = lambda: up_alive() and hstate()["player"].get("area") == dest  # noqa: E731
    if rp_click_toward(t["x"], t["y"], in_dest, tries=4):
        return True, "tile class %d at %d,%d by clicks" % (t["class"], t["x"], t["y"])
    if not up_alive():
        return False, "game gone during the clicks"
    n = up_click_tile(t, dest, log)
    for _ in range(4):
        if in_dest():
            return True, "tile class %d at %d,%d by ring clicks (%d)" % (t["class"], t["x"], t["y"], n)
        if not up_alive():
            break
        time.sleep(1)
    return False, "tile class %d at %d,%d: %d clicks, still in %s" % (t["class"], t["x"], t["y"], n,
                                                                     hstate()["player"].get("area") if up_alive() else "GONE")


def up_enter(src, dest, log):
    """SET-UP: `src` (harness travel), the server warp into `dest` (`level <dest> warp`: lands at src's entrance of dest), real
    clicks on dest's tile back out into `src` (the exit lands next to the entrance). Then the judged entry: real clicks on src's
    tile into `dest`, with the mercenary along. Returns (entered, how)."""
    if not up_alive():
        return False, "game gone before the try"
    goto(src)
    if hstate()["player"].get("area") != src:
        return False, "SET-UP: not in %d" % src
    Hl("level %d warp" % dest, log)
    time.sleep(6)
    for _ in range(10):
        if not up_alive() or hstate()["player"].get("area") == dest:
            break
        time.sleep(2)
    if not up_alive():
        return False, "game gone after the server warp into %d" % dest
    if hstate()["player"].get("area") != dest:
        return False, "SET-UP: `level %d warp` did not arrive" % dest
    time.sleep(4)  # the mercenary follows
    ok, how_out = up_click_through(dest, src, log)
    if not ok:
        return False, "SET-UP way out %d->%d: %s" % (dest, src, how_out)
    time.sleep(5)
    ok, how = up_click_through(src, dest, log)
    return ok, "out: %s; in: %s" % (how_out, how)


def check_uppass():
    """Lane uppass (bugs #511 / #292): into Underground Passage Level 1 (10) from Stony Field (4) and from Dark Wood (5), and on
    into Level 2 (14), with a live, equipped mercenary, in MXL_UP_GRAPHICS (default legacy), MXL_UP_ROUNDS rounds (default 3) of
    MXL_UP_ROUTES (default 4-10,5-10,10-14). After each entry: game alive, the mercenary with the player, engine asserts and crash
    files since the try. PASS: every route entered every round, the game alive. SET-UP: hire fixture quest, gear by clicks, travel
    to the source area by harness, MXL_UP_FILL items."""
    name = "uppass"
    mark0 = engine_mark()
    if not need_game():
        return add(name, "BLOCKED", "not in a game")
    rows, bad, log, shots = [], [], [], []
    revive_if_dead()
    goto(1)
    m = up_merc_setup(log, rows, bad, shots)
    if m is None:
        return finish(name, False, "no mercenary: " + "; ".join(bad), mark0, shots, rows + log[-300:])
    fill = int(os.environ.get("MXL_UP_FILL", "0"))
    if fill:
        up_fill(fill, log, rows)
    enable_debug()
    cheat("god 1")  # SET-UP: the walks through Stony Field / Dark Wood / the caves are not cut short by deaths
    for s in (7, 6):  # SET-UP: the mercenary lives through them too (maximum, then current life 20,000)
        Hl("stat merc %d set %d" % (s, 20000 << 8), log)
    rows.append("SET-UP: god mode on the player, mercenary life 20,000")
    gfx = os.environ.get("MXL_UP_GRAPHICS", "legacy")
    goto(1)
    ok_gfx = set_graphics(gfx)
    rows.append("graphics %s: %s" % (gfx, "on" if ok_gfx else "NOT SET (%s)" % graphics_mode()))
    shots.append(sh("uppass_gfx_%s" % gfx))
    routes = [tuple(int(v) for v in r.split("-")) for r in os.environ.get("MXL_UP_ROUTES", UP_ROUTES).split(",") if r.strip()]
    rounds = int(os.environ.get("MXL_UP_ROUNDS", "3"))
    tries = entered = 0
    gone = False
    for rnd in range(1, rounds + 1):
        for src, dest in routes:
            guard()
            mark = engine_mark()
            if src != 10:
                revive_if_dead()
                mb, _w = merc_info()
                if mb is None:  # dead or lost: revive it at Kashya (fixture gold), it must be with the player for the try
                    merc_revive(150, "Kashya", 1, log, rows, [])  # its price checks belong to `mercs`
            tries += 1
            t0 = time.time()
            ok, how = up_enter(src, dest, log)
            time.sleep(8)  # the client's room / unit packets of the new level
            alive = up_alive()
            mi = merc_info()[0] if alive else None
            area = hstate()["player"].get("area") if alive else None
            near = alive and mi is not None and any(x.get("id") == mi.get("id") for x in hstate()["mons"])
            asserts = engine_asserts(mark)
            crashes = sorted((set(os.listdir(g.CRASH_DIR)) if os.path.isdir(g.CRASH_DIR) else set()) - mark["crashes"])
            entered += 1 if ok and alive else 0
            rows.append("round %d %d->%d: %s (%s) in %.0f s; game %s, area %s, mercenary %s%s%s%s" % (
                rnd, src, dest, "entered" if ok else "NOT entered", how, time.time() - t0, "alive" if alive else "GONE", area,
                "none" if mi is None else "id %s level %s %s" % (mi.get("id"), mi.get("level"), "near" if near else "not in view"),
                "; asserts: " + "; ".join("%s (%s)" % (a[0][:70], a[1].split("\\")[-1]) for a in asserts) if asserts else "",
                "; CRASH FILES " + ", ".join(crashes) if crashes else "",
                "; graphics " + graphics_mode() if alive and dest != 14 and rnd == 1 else ""))
            g.log("uppass " + rows[-1])
            if alive and rnd == 1:
                shots.append(sh("uppass_r%d_%d_%d" % (rnd, src, dest)))
            if not alive:
                gone = True
                bad.append("game gone after %d->%d round %d" % (src, dest, rnd))
                break
        if gone:
            break
    if not gone:
        # after the travels: back in town, is the mercenary with the player again (server mode, in `state`, on screen)?
        goto(1)
        time.sleep(10)
        mi = merc_info()[0]
        near = mi is not None and any(x.get("id") == mi.get("id") for x in hstate()["mons"])
        rows.append("after the rounds, Rogue Encampment: mercenary %s" % (
            "none" if mi is None else "id %s mode %s life %s %s" % (mi.get("id"), mi.get("mode"), mi.get("life"), "near" if near else "not in view")))
        g.log("uppass " + rows[-1])
        shots.append(sh("uppass_town_after"))
        cheat("god 0")
        rows.extend("plugin: " + ln for ln in mxl_text().splitlines() if ln.startswith("reassign"))  # the guard's counters
    note = "%d of %d entries, graphics %s; %s" % (entered, tries, gfx, "GAME CLOSED" if gone else "game alive throughout")
    finish(name, not gone and entered == tries and not bad, note + ("; " + "; ".join(bad) if bad else ""), mark0, shots,
           rows + log[-400:], partial=None if ok_gfx else "graphics mode not reached")


CHECKS += [("uppass", check_uppass)]

if __name__ == "__main__":
    main()

