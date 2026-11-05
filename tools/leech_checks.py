"""Lane leech (bug #540): life and mana leech per hit on Normal, Nightmare and Hell (check `leech` of tools/game_checks.py).

Median XL 2012 v005 ships no DLL, so 2012 ran 1.13c's leech step; 1.14d's copy is `DAMAGE_ApplyLifeAndManaLeech` (0x57c420,
SUnitDmg.cpp). For a player attacker it takes the leech percents of the damage block (stats lifedrainmindam 60 / manadrainmindam
62), shifts them left by 6, divides them by difficultylevels LifeStealDivisor / ManaStealDivisor (Median: 4 / 100 / 200, vanilla
1 / 2 / 3), takes that percent of the physical damage dealt (after the clamp to the target's life), then the target's monstats
Drain percent (Median: 100 on every attackable row), and shifts right by 6. All amounts are in 1/256 points.

SET-UP (named in the note): the lane character is raised to level 60 by the game's own experience award, its stats are set by
harness (`stat ... set`: leech 60 / 62, life and mana pools, mana recovery -100 so regeneration does not hide the mana gain, flat
damage reduction so the zombie cannot hurt it, attack rating, strength), the target is a spawned zombie with its life raised and
its regeneration off; the hit is the game's own Attack (`cast 0 unit`, skill 0, the cast-on-unit function: the server's melee or
ranged attack with the damage calculation that fills the leech fields). Nightmare / Hell: the save edit of tools/nmh_checks.py
(progression 10). Judged: the life and mana gained per hit against expected_gain() of the zombie's life loss.
"""
import time

import nmh_checks as nmh

DIVISORS = {"normal": (4, 4), "nightmare": (100, 100), "hell": (200, 200)}  # Median's difficultylevels (life, mana)
EAGLE = 432  # skills.txt Eagle Stance (Barbarian, aurastat3 lifedrainmindam 1 + blvl / 2)
ZOMBIE = 5  # monstats row zombie1 (Drain 100 on all three difficulties)
SAVED = (0, 6, 7, 8, 9, 19, 27, 34, 60, 62)  # strength, life, max life, mana, max mana, attack rating, mana recovery %, flat DR, leech


def expected_gain(phys, pct, divisor, drain=100):
    """1.14d 0x57c420 for a player attacker: the life (or mana) a hit of `phys` physical damage (1/256 points) gives with `pct`
    leech, the difficulty's divisor and the target's monstats Drain. Integer steps as the game does them (C division truncates)."""
    if phys <= 0 or pct == 0 or drain == 0:
        return 0
    v = pct << 6
    if divisor:
        v = int(v / divisor)
    v = phys * v // 100
    if drain != 100:
        v = v * drain // 100
    return v >> 6


def judge(hits, pct, divisor, drain=100):
    """(gained, expected, ok) over the hits that did damage: the sum of the per-hit gains against the sum of expected_gain(); one
    1/256 point per hit of slack (a hit that lands across the two reads)."""
    got = sum(h[1] for h in hits)
    want = sum(expected_gain(h[0], pct, divisor, drain) for h in hits)
    return got, want, abs(got - want) <= len(hits) + want // 50


def bow_code(gc):
    """The built weapons.txt bow with the lowest level requirement (the ranged round)."""
    rows = [r for r in gc.table("weapons") if r.get("type") == "bow" and r.get("code")]
    rows.sort(key=lambda r: int(r.get("levelreq") or 0))
    return rows[0]["code"] if rows else None


def zombie(gc, log, row=ZOMBIE):
    px, py = gc.player_xy()
    _, sp = gc.Hl("spawn %d 1 %d %d" % (row, px + 2, py), log)
    mid = gc.first(sp, r"id=(\d+)")
    if mid is None:
        return None
    ref = "mon:%d" % mid
    for st in (74, 34, 36):  # regeneration, flat and % damage reduction (Median's Nightmare / Hell monprop rows add them)
        gc.setstat(ref, st, 0)
    gc.setstat(ref, 7, 20000 << 8)
    gc.setstat(ref, 6, 20000 << 8)
    return mid


def hits_round(gc, life_pct, mana_pct, n, log, row=ZOMBIE):
    """Attacks on a monster of monstats row `row` (default a zombie) with the leech stats set until n did damage (at most 2 n):
    [(monster life lost, player life gained, player mana gained)] per Attack."""
    gc.setstat("player", 60, life_pct)
    gc.setstat("player", 62, mana_pct)
    out, mid = [], None
    for _ in range(2 * n):
        if sum(1 for x in out if x[0] > 0) >= n:
            break
        if mid is None or gc.rd("mon:%d" % mid, 6) in (None, 0):
            mid = zombie(gc, log, row)
            if mid is None:
                break
        ref = "mon:%d" % mid
        gc.setstat(ref, 6, 20000 << 8)
        gc.setstat("player", 6, 1000 << 8)
        gc.setstat("player", 8, 100 << 8)
        l0, p0, m0 = gc.rd(ref, 6), gc.rd("player", 6), gc.rd("player", 8)
        gc.Hl("cast 0 unit %d" % mid, log)
        time.sleep(1.5)
        l1, p1, m1 = gc.rd(ref, 6), gc.rd("player", 6), gc.rd("player", 8)
        if None in (l0, p0, m0, p1, m1):
            continue
        out.append(((l0 - (l1 or 0)), p1 - p0, m1 - m0))
        if out[-1][0] <= 0:  # no damage (a miss, or the zombie walked off): the next Attack goes to a fresh one
            gc.Hl("state", log)
            gc.H("kill %d" % mid)
            mid = None
    if mid is not None:
        gc.H("kill %d" % mid)
    log.append("round row %d life %d%% mana %d%%: %s" % (row, life_pct, mana_pct, out))
    return out


def drain_of(gc, row, difficulty):
    """monstats Drain / Drain(N) / Drain(H) of a built row (blank = 0: no leech from it)."""
    r = gc.table("monstats")[row]
    col = {"normal": "Drain", "nightmare": "Drain(N)", "hell": "Drain(H)"}[difficulty]
    return int(r.get(col) or 0), r.get("Id")


def measure(gc, difficulty, rounds, rows, bad, log):
    """Each (life %, mana %, hits[, monstats row]) round in Blood Moor: rows of the numbers, `bad` for a mismatch or a round without
    a landed hit."""
    dl, dm = DIVISORS[difficulty]
    gc.goto(2)
    gc.kill_all_near()
    for life_pct, mana_pct, n, *rest in rounds:
        row = rest[0] if rest else ZOMBIE
        drain, name = drain_of(gc, row, difficulty)
        h = [x for x in hits_round(gc, life_pct, mana_pct, n, log, row) if x[0] > 0]
        if not h:
            bad.append("%s %d/%d: no Attack did damage" % (difficulty, life_pct, mana_pct))
            continue
        lg, lw, lok = judge([(x[0], x[1]) for x in h], life_pct, dl, drain)
        mg, mw, mok = judge([(x[0], x[2]) for x in h], mana_pct, dm, drain)
        dmg = sum(x[0] for x in h)
        rows.append("%s %s (Drain %d) life %d%% mana %d%%: %d hits, damage %.1f, life +%.2f (want %.2f), mana +%.2f (want %.2f)" % (
            difficulty, name, drain, life_pct, mana_pct, len(h), dmg / 256, lg / 256, lw / 256, mg / 256, mw / 256))
        if not lok:
            bad.append("%s life %d%%: +%d/256 want %d/256" % (difficulty, life_pct, lg, lw))
        if not mok:
            bad.append("%s mana %d%%: +%d/256 want %d/256" % (difficulty, mana_pct, mg, mw))


def set_up(gc, log):
    """The stats of the set-up; returns what to put back."""
    saved = [(s, gc.rd("player", s)) for s in SAVED]
    for s, v in ((7, 30000 << 8), (9, 30000 << 8), (27, -100), (34, 30000), (19, 100000), (0, 1000)):
        gc.setstat("player", s, v)
    return saved


def restore(gc, saved):
    """The saved stats back, in town (Blood Moor's own monsters kill a level-1 character whose flat DR is gone), life full."""
    gc.goto(1)
    for s, v in saved:
        if v is not None:
            gc.setstat("player", s, v)
    top = dict(saved).get(7)
    if top:
        gc.setstat("player", 6, top)


def stances(gc, rows, bad, log):
    """Median's leech skills on the Barbarian: Eagle Stance (aurastat3 lifedrainmindam 1 + blvl / 2), asked for at level 10. Its
    reqlevel formula gates each level (ulvl - 18 >= (blvl - 1) * 6), so the base level reached is what is judged. Returns
    (stat 60 read, want)."""
    gc.setstat("player", 60, 0)
    blvl = gc.learn(EAGLE, 10) or 0
    gc.setstat("player", 8, 30000 << 8)  # the stance's mana
    gc.Hl("cast %d self" % EAGLE, log)
    time.sleep(1.5)
    got = gc.rd("player", 60)
    want = 1 + blvl // 2
    rows.append("Eagle Stance level %d cast: stat 60 reads %s (want %d from the aura)" % (blvl, got, want))
    return got, want


def level_up(gc, level, log):
    """Experience through the game's own award up to `level`: the level stat set by Level() alone does not hold (state read 3 inside
    it), and the to-hit level factor and Eagle Stance's reqlevel 18 read the real one."""
    lvl, amount = gc.hstate()["player"].get("level", 0), 50000
    for _ in range(60):
        if lvl >= level:
            break
        lvl = gc.parse_xp(gc.Hl("xp %d" % amount, log)[1]).get("level", lvl)
        amount = min(amount * 2, 2000000000)
    return lvl


def run(gc):
    mark = gc.engine_mark()
    log, rows, bad, shots = [], [], [], []
    if not gc.need_game():
        return gc.add("leech", "BLOCKED", "not in a game")
    gc.Hl("setskill %d 0" % EAGLE, log)  # a stance left on by an earlier run
    lvl = level_up(gc, 60, log)
    rows.append("character level %s (experience award)" % lvl)
    saved = None
    try:
        with gc.Level(60):
            saved = set_up(gc, log)
            gc.Hl("unequip rhand", log)
            gc.Hl("unequip lhand", log)
            gc.Hl("equip 142 21=150 22=150 rhand", log)
            skel = next((i for i, r in enumerate(gc.table("monstats")) if r.get("Id") == "skeleton2"), None)
            rounds = [(0, 0, 3), (100, 0, 4), (0, 100, 4), (10, 10, 4)] + ([(100, 100, 3, skel)] if skel is not None else [])
            measure(gc, "normal", rounds, rows, bad, log)
            bow = bow_code(gc)
            if bow:
                gc.Hl("unequip rhand", log)
                gc.Hl("equip %s 21=150 22=150 rhand" % bow, log)
                gc.Hl("equip aqv lhand", log)
                before = len(rows)
                measure(gc, "normal", ((100, 100, 4),), rows, bad, log)
                if len(rows) > before:
                    rows[-1] = "bow %s: " % bow + rows[-1]
                gc.Hl("unequip lhand", log)
                gc.Hl("unequip rhand", log)
                gc.Hl("equip 142 21=150 22=150 rhand", log)
            shots.append(gc.sh("leech_normal"))
            restore(gc, saved)
            saved = None
        gc.goto(1)
        if not nmh.closed_edit_and_enter(gc, nmh.unlock_edit("hell"), "nightmare", log, shots):
            bad.append("Nightmare not entered")
        for diff in ("nightmare", "hell"):
            if diff == "hell" and not nmh.ensure(gc, "hell", log, shots):
                bad.append("Hell not entered")
                continue
            if gc.hstate()["player"].get("difficulty") != nmh.DIFFS[diff]:
                bad.append("%s: the game is not in it" % diff)
                continue
            with gc.Level(60):
                saved = set_up(gc, log)
                gc.Hl("unequip rhand", log)
                gc.Hl("equip 142 21=150 22=150 rhand", log)
                measure(gc, diff, ((0, 0, 3), (100, 100, 10)), rows, bad, log)
                shots.append(gc.sh("leech_%s" % diff))
                restore(gc, saved)
                saved = None
            gc.goto(1)
        # last: the stance stays on (its life regeneration and mana recovery would hide the leech of later rounds)
        saved = set_up(gc, log)
        gc.goto(2)
        got, want = stances(gc, rows, bad, log)
        if got != want or want < 2:
            bad.append("Eagle Stance gave stat 60 = %s (want %d)" % (got, want))
        restore(gc, saved)
        saved = None
    finally:
        gc.Hl("setskill %d 0" % EAGLE, log)
        if saved:
            restore(gc, saved)
    gc.finish("leech", not bad, "SET-UP: experience award to level 60, harness stats (leech 60 / 62, pools, mana recovery -100, flat DR, attack rating, "
              "strength), a 150-damage dagger, spawned zombies; the game's own Attack. " + "; ".join(rows)
              + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log)
