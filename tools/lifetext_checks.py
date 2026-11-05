"""Bug #547: the life orb's text ("Life: x / y" when the orb is hovered) against the life the orb draws and the server holds (check
`lifetext` of tools/game_checks.py). A player (Discord, 0.1.12) saw the legacy orb two-thirds empty under "Life: 970 / 970".

D2R's orb widget (D2Client AttributeBallWidget, update 0x14caf10, draw 0x14c9ca0) draws the fill AND the text from one value
object (widget +0x5d0: stat ids 6 / 7 or 8 / 9 of the client's player, eased by time in 0x1514240), so the text can only lag
the fill when the client's own stats do. Each round reads the server's life / mana (`stat player 6 / 7 / 8 / 9`) and the client
copy's (`cstat`) and keeps a screenshot with the orb hovered: life lost to spawned zombies (the game's own melee) and by the
harness stat write (D2R's stat update path), the cursor held on the orb while the life changes, a Median healing / mana potion
drunk by a right click (its state `regenpotion`; D2R's widget eases the text only under `healthpot` / `manapot`), max life
from worn items, and Replenish Life high and negative (the client runs its own regeneration between the server's updates).
HD and legacy. FAIL when client and server differ by more than SLACK points after a settle; the text on the screenshots is
read by hand (REVIEW).
"""
import re
import time

ZOMBIE = 5  # monstats row zombie1
SLACK = 2  # whole points: one regeneration step between the two reads
STATS = {"life": (6, 7), "mana": (8, 9)}
ORB = {"hd": {"life": (0.25, 0.90), "mana": (0.75, 0.90)},  # 1600 x 900 client, orb centres
       "legacy": {"life": (0.19, 0.92), "mana": (0.81, 0.92)}}


def pools(gc, log):
    """{"life": (server cur, server max, client cur, client max), "mana": ...} in whole points (the stats are in 1/256)."""
    out = {}
    for name, (cur, mx) in STATS.items():
        vals = [gc.rd("player", cur), gc.rd("player", mx)]
        for st in (cur, mx):
            vals.append(gc.stat_of(gc.Hl("cstat %d" % st, log)[1]))
        out[name] = tuple(None if v is None else v >> 8 for v in vals)
    log.append("pools: %s" % out)
    return out


def judge(p, tag, bad):
    """Server against client, life and mana, after a settle."""
    for name, (scur, smax, ccur, cmax) in p.items():
        if None in (scur, smax, ccur, cmax) or abs(scur - ccur) > SLACK or smax != cmax:
            bad.append("%s %s: server %s/%s, client %s/%s" % (tag, name, scur, smax, ccur, cmax))


def hover_shot(gc, mode, which, tag, shots):
    gc.hover(*ORB[mode][which])
    time.sleep(0.5)
    shots.append(gc.sh("lifetext_%s_%s_%s" % (mode, which, tag)))
    gc.hover(0.5, 0.3)


def zombies(gc, n, log):
    px, py = gc.player_xy()
    ids = []
    for k in range(n):
        _, sp = gc.Hl("spawn %d 1 %d %d" % (ZOMBIE, px + 2 + k, py + 1), log)
        mid = gc.first(sp, r"id=(\d+)")
        if mid is not None:
            ids.append(mid)
    return ids


def round_(gc, mode, tag, rows, bad, log, shots):
    p = pools(gc, log)
    judge(p, "%s %s" % (mode, tag), bad)
    hover_shot(gc, mode, "life", tag, shots)
    hover_shot(gc, mode, "mana", tag, shots)
    rows.append("%s %s: life server %s/%s client %s/%s, mana server %s/%s client %s/%s" % ((mode, tag) + p["life"] + p["mana"]))
    return p


def mode_rounds(gc, mode, rows, bad, log, shots):
    gc.goto(1)
    if not gc.set_graphics(mode):
        bad.append("graphics %s not set" % mode)
        return
    round_(gc, mode, "town", rows, bad, log, shots)
    gc.goto(2)
    gc.kill_all_near()
    gc.setstat("player", 74, 0)  # no life regeneration while the zombies hit
    ids = zombies(gc, 3, log)
    time.sleep(6)
    round_(gc, mode, "zombies", rows, bad, log, shots)
    for mid in ids:
        gc.H("kill %d" % mid)
    mx = gc.rd("player", 7)
    if mx:
        gc.setstat("player", 6, mx // 3)
        time.sleep(1.5)
        round_(gc, mode, "set_third", rows, bad, log, shots)
    if mx:  # the cursor stays on the orb while the life changes
        gc.hover(*ORB[mode]["life"])
        gc.setstat("player", 6, mx)
        time.sleep(1.5)
        shots.append(gc.sh("lifetext_%s_life_held_full" % mode))
        gc.setstat("player", 6, mx // 4)
        time.sleep(1.5)
        p = pools(gc, log)
        judge(p, "%s held" % mode, bad)
        shots.append(gc.sh("lifetext_%s_life_held_quarter" % mode))
        gc.hover(0.5, 0.3)
        rows.append("%s held: life server %s/%s client %s/%s" % ((mode,) + p["life"]))
    mm = gc.rd("player", 9)
    if mm:
        gc.setstat("player", 8, mm // 3)
        time.sleep(1.5)
        round_(gc, mode, "mana_third", rows, bad, log, shots)


def drift_rounds(gc, mode, rows, bad, log, shots):
    """Life left at a third for a while with Replenish Life (stat 74) at its own value, high and negative: the client runs its own
    regeneration between the server's updates."""
    gc.goto(2)
    gc.kill_all_near()
    regen0 = gc.rd("player", 74) or 0
    mx = gc.rd("player", 7)
    for regen in (regen0, 300, -40):
        gc.setstat("player", 74, regen)
        gc.setstat("player", 6, mx // 3)
        for t in (2, 8):
            time.sleep(t if t == 2 else 6)
            p = pools(gc, log)
            rows.append("%s drift regen %d +%ds: life server %s/%s client %s/%s" % ((mode, regen, t) + p["life"]))
        regen_step = max(abs(regen) * 25 >> 8, SLACK)  # the client's regeneration runs ahead by up to a second of it
        if abs(p["life"][0] - p["life"][2]) > regen_step:
            bad.append("%s drift regen %d: server %s, client %s" % (mode, regen, p["life"][0], p["life"][2]))
        shots.append(gc.sh("lifetext_%s_drift_%d" % (mode, regen)))
    gc.setstat("player", 74, regen0)


ITEMS = [("rring", "76:0=200"), ("lring", "7:0=%d" % (500 << 8)), ("neck", "3:0=150")]  # +% life, +life, +vitality


def item_rounds(gc, mode, rows, bad, log, shots):
    """Max life from worn items (+% life, +life, +vitality), then the life at the new max and at a third of it."""
    gc.goto(2)
    gc.kill_all_near()
    for loc, stat in ITEMS:
        code = "amu" if loc == "neck" else "rin"
        gc.Hl("equip %s magic %s %s" % (code, stat, loc), log)
        time.sleep(1.5)
        p = pools(gc, log)
        judge(p, "%s worn %s" % (mode, stat), bad)
        rows.append("%s worn %s: life server %s/%s client %s/%s" % ((mode, stat) + p["life"]))
        hover_shot(gc, mode, "life", "worn_%s" % loc, shots)
    mx = gc.rd("player", 7)
    for tag, v in (("full", mx), ("third", mx // 3)):
        gc.setstat("player", 6, v)
        time.sleep(1.5)
        p = pools(gc, log)
        judge(p, "%s items %s" % (mode, tag), bad)
        rows.append("%s items life %s: life server %s/%s client %s/%s" % ((mode, tag) + p["life"]))
        hover_shot(gc, mode, "life", "items_%s" % tag, shots)
    for loc, _stat in ITEMS:
        gc.Hl("unequip %s" % loc, log)
    time.sleep(1.5)
    p = pools(gc, log)
    rows.append("%s items off: life server %s/%s client %s/%s" % ((mode,) + p["life"]))
    hover_shot(gc, mode, "life", "items_off", shots)


def state_on(gc, verb, state, log):
    """1 / 0 for the player's state bit on the server (`states`) or the client (`cstates`); None when not read."""
    _ok, lines = gc.Hl("%s player %d" % (verb, state), log)
    for ln in lines:
        m = re.search(r"state %d: bit=(\d)" % state, ln)
        if m:
            return int(m.group(1))
    return 0 if any("states: 0 set" in ln for ln in lines) else None


def drink(gc, code, log):
    """Right click on a new `code` in the backpack (HD inventory open), as a player drinks it. True when it was used up."""
    gc.rp_packclear(log)
    ok, lines = gc.Hl("item %s inv" % code, log)
    iid = gc.first(lines, r"item id=(\d+)")
    it = gc.rp_item_line(iid) if iid is not None else None
    if it is None:
        return False
    if not gc.right_panel_open():
        gc.g.press("i")
        time.sleep(1.0)
    gc.g.click(*gc.rp_inv_xy(it["x"], it["y"]), button="right")
    time.sleep(1.5)
    gc.g.press("i")
    time.sleep(1.0)
    return gc.rp_item_line(iid) is None


def potion_round(gc, code, rows, bad, log, shots):
    gc.goto(1)
    gc.set_graphics("hd")
    mx, mm = gc.rd("player", 7), gc.rd("player", 9)
    gc.setstat("player", 6, mx // 2)
    gc.setstat("player", 8, mm // 2)
    time.sleep(1.5)
    used = drink(gc, code, log)
    time.sleep(2)
    if not used:
        bad.append("%s not drunk" % code)
    for st in (100, 106, 245):  # healthpot, manapot, regenpotion
        srv, clt = state_on(gc, "states", st, log), state_on(gc, "cstates", st, log)
        rows.append("%s used %s: state %d server %s client %s" % (code, used, st, srv, clt))
        if srv != clt:
            bad.append("%s: state %d server %s, client %s" % (code, st, srv, clt))
    for mode in ("hd", "legacy"):
        gc.set_graphics(mode)
        for tag, part in (("quarter", 4), ("full", 1), ("third", 3)):
            gc.setstat("player", 6, mx // part)
            gc.setstat("player", 8, mm // part)
            time.sleep(1.5)
            p = pools(gc, log)
            judge(p, "%s %s %s" % (mode, code, tag), bad)
            rows.append("%s after %s %s: life server %s/%s client %s/%s, mana server %s/%s client %s/%s" % (
                (mode, code, tag) + p["life"] + p["mana"]))
            shots.append(gc.sh("lifetext_%s_%s_%s" % (mode, code, tag)))


def run(gc):
    mark = gc.engine_mark()
    log, rows, bad, shots = [], [], [], []
    if not gc.need_game():
        return gc.add("lifetext", "BLOCKED", "not in a game")
    try:
        for mode in ("hd", "legacy"):
            mode_rounds(gc, mode, rows, bad, log, shots)
        potion_round(gc, "hp3", rows, bad, log, shots)
        potion_round(gc, "mp3", rows, bad, log, shots)
        gc.goto(1)
        gc.set_graphics("legacy")
        item_rounds(gc, "legacy", rows, bad, log, shots)
        drift_rounds(gc, "legacy", rows, bad, log, shots)
    finally:
        gc.goto(1)
        gc.set_graphics("hd")
    gc.finish("lifetext", not bad, "REVIEW the orb text on the screenshots. SET-UP: life / mana and Replenish Life by harness stat writes, "
              "zombies spawned, worn items made by the harness, potions drunk by a right click. " + "; ".join(rows)
              + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log)
