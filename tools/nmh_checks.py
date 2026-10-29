"""Lane nmhell: the first check of Nightmare and Hell progression (checks `nmhsetup`, `nmhnm`, `nmhhell` of tools/game_checks.py).

SET-UP (coordinator ruling "PLAYER PATH vs SET-UP", named in every row): a new Barbarian is levelled by the game's own experience
award (`xp`), its stat points are spent by harness (`stat ... set`: half strength, half vitality) and its skill points by the game's
skill-point function (`setskill`: Blood Hatred as the attack, Aerials Disaster before it, passives); a closed-save edit with our
own code (tools/rc_setup.py) writes the progression byte the game itself writes after Baal (5 = Nightmare open, later 10 = Hell
open) and marks Normal's five act-boss quests done. That is all finishing a difficulty changes for the next one: the difficulty
dialog reads the progression byte, and the quest words, waypoints and act of every difficulty are kept apart in the save.
Travel help (`level`, `move`, `place`) and gear (`equip`, stats in the notes) are named too.

Judged on the player path: the difficulty dialog (clicks), the Cold Plains waypoint (operate) and its panel (a click on the
Rogue Encampment line), NPC talks and menu lines, boss fights with Blood Hatred on the right button and real right clicks on
the boss (the server's cast function is the fallback after clicks that do no damage; both counts are in the note).
Expected numbers come from the built tables: area level levels.txt MonLvlEx / (N) / (H), boss level monstats Level / (N) / (H),
life monstats minHP..maxHP (or MinHP(N) ...) x monlvl.txt L-HP / (N) / (H) of that level / 100.
"""
import os
import re
import time

import rc_setup

DIFFS = {"normal": 0, "nightmare": 1, "hell": 2}
SUFFIX = {0: "", 1: "(N)", 2: "(H)"}
LEVEL = {"nightmare": 80, "hell": 120}  # character level per difficulty (Median 2012 caps at 120; no level gate to enter)
ATTACK = 352  # Blood Hatred (barbarian, melee, mana 26, itypea1 and itypeb1 `mele`: two melee weapons): the attack of the build
SKILLS = ((351, 1), (352, 20), (439, 10), (442, 10))  # Aerials Disaster (its prerequisite), Blood Hatred, passives Ancient Blood,
# Mountain King (built ids)
BOSS_QUESTS_DONE = (6, 14, 23, 26, 40)  # Normal quest words a finished Normal has: Andariel, Duriel, Mephisto, Diablo, Baal
FIELD = 2  # Blood Moor: the monster level / life sample
WP_AREA = 3  # Cold Plains: the first field waypoint
WP_FIRST_LINE = (340 / 1600, 222 / 900)  # waypoint panel tab I first line (Rogue Encampment), lane playtest calibration
AKARA, WARRIV = 148, 155
GEAR_MULT = {1: 10, 2: 30}  # weapon damage factor (help: with x1 / x3 Andariel / Duriel Nightmare lost 3 % of their life before
# 5 deaths, run checks-20261029-011051-s1; Hell life is 500 % of the row at every level)
BELT_VIT = 300  # vitality per character level on the given belt (Belt (Grade 1), code 629), with 75 % poison length reduction
CLICK_MISSES = 4  # right clicks without damage before the cast-function fallback
FIGHT_S = {1: 300, 2: 600}


# ------------------------------------------------------------------ pure helpers (unit tests: tools/tests/test_nmh_checks.py)
def area_level(levels_row, diff):
    """Expansion monster level of a level row in a difficulty (D2R's MonLvlEx columns)."""
    return int(levels_row.get("MonLvlEx" + SUFFIX[diff]) or 0)


def boss_level(mon_row, diff):
    return int(mon_row.get("Level" + SUFFIX[diff]) or 0)


def life_range(mon_row, monlvl_row, diff):
    """(lowest, highest) maximum life in whole points of a normal monster of this row and level row."""
    pct = int(monlvl_row.get("L-HP" + SUFFIX[diff]) or 0)
    lo = int(mon_row.get("minHP" if diff == 0 else "MinHP" + SUFFIX[diff]) or 0)
    hi = int(mon_row.get("maxHP" if diff == 0 else "MaxHP" + SUFFIX[diff]) or 0)
    return lo * pct // 100, hi * pct // 100


def judge_sample(sample, alvl):
    """sample: [(class, level, maxlife, (lo, hi))]. Returns (at area level, in life range of those, other levels)."""
    at = [s for s in sample if s[1] == alvl]
    ok = [s for s in at if s[3][0] - 1 <= s[2] <= s[3][1] + 1]
    return at, ok, [s for s in sample if s[1] != alvl]


def spend_points(statpts, strength, vitality):
    """Half the unspent stat points into strength, the rest into vitality: (strength, vitality)."""
    return strength + statpts // 2, vitality + statpts - statpts // 2


def parse_ground(lines):
    """`ground` lines -> [{id, code, mode, x, y, ...}] (ints where the value is a number)."""
    out = []
    for ln in lines:
        if ln.startswith("ground id="):
            out.append({k: (int(v) if re.fullmatch(r"-?\d+", v) else v) for k, v in re.findall(r"(\w+)=(\S+)", ln)})
    return out


def unlock_edit(difficulty):
    """The save edit of a finished previous difficulty: progression byte (never lowered) and Normal's act-boss quests done."""
    def fn(s):
        s = rc_setup.set_progression(s, difficulty)
        for q in BOSS_QUESTS_DONE:
            s = rc_setup.set_quest_bits(s, 0, q, rc_setup.DONE)
            if difficulty == "hell":
                s = rc_setup.set_quest_bits(s, 1, q, rc_setup.DONE)
        return s
    return fn


# ------------------------------------------------------------------ in-game helpers (gc = the game_checks module)
def mon_row(gc, cls):
    rows = gc.table("monstats")
    r = rows[cls] if 0 <= cls < len(rows) else None
    if r is None or r.get("*hcIdx") != str(cls):
        r = gc.row_of("monstats", "*hcIdx", cls)
    return r


def monlvl_row(gc, level):
    return gc.row_of("monlvl", "Level", level)


def expected_life(gc, cls, level, diff):
    r, m = mon_row(gc, cls), monlvl_row(gc, level)
    return life_range(r, m, diff) if r and m else (0, 0)


def build(gc, level, log):
    """SET-UP: the game's experience award to `level`, stat points into strength / vitality by harness, skills by `setskill`."""
    lvl = gc.acts_level_up(level)
    pts = gc.rd("player", 4) or 0
    s0, v0 = gc.rd("player", 0) or 0, gc.rd("player", 3) or 0
    s1, v1 = spend_points(pts, s0, v0)
    for stat, val in ((0, s1), (3, v1), (4, 0)):
        gc.Hl("stat player %d set %d" % (stat, val), log)
    skp = gc.rd("player", 5) or 0
    got = []
    for sk, lv in SKILLS:
        _ok, lines = gc.Hl("setskill %d %d" % (sk, lv), log)  # Median caps a skill by character level: the level it stopped at
        got.append("%d:%s" % (sk, gc.first(lines, r"base level (\d+)")))
    gc.Hl("stat player 5 set %d" % max(0, skp - sum(lv for _s, lv in SKILLS)), log)
    note = ("SET-UP: level %d by the game's xp award; %d stat points spent by harness (strength %d -> %d, vitality %d -> %d); "
            "skills by setskill %s (%d skill points the engine gave)" % (lvl, pts, s0, s1, v0, v1, ", ".join(got), skp))
    return lvl, note


def axes(gc, dmg, log):
    """The axe in each hand: Blood Hatred needs two melee weapons (itypeb1 `mele`; with one, D2R refuses it as 1.13c does and
    a click swings Attack: lane skilluse, bug #397)."""
    for hand in ("rhand", "lhand"):
        gc.H("unequip %s" % hand)
        gc.Hl("equip %s 21=%d 22=%d 119=400 60=20 93=60 %s" % (gc.ACTS_WEAPON, dmg, dmg * 2, hand), log)


def gear(gc, level, diff, log):
    """Help (named): game_checks.acts_gear (axe, ring, amulet), the axe's damage x GEAR_MULT and a second such axe in the left
    hand (axes()), an amulet with energy and mana
    regeneration for the skill, a second ring with resistances that make up the difficulty's penalty; life and mana filled."""
    dmg = gc.acts_gear(level) * GEAR_MULT[diff]
    axes(gc, dmg, log)
    gc.H("unequip belt")
    gc.Hl("equip 629 3=%d 110=75 belt" % (level * BELT_VIT), log)
    gc.H("unequip neck")
    gc.Hl("equip amu 39=75 41=75 43=75 45=75 1=500 27=300 neck", log)
    res = 50 * diff
    gc.H("unequip lring")
    if res:
        gc.Hl("equip rin 39=%d 41=%d 43=%d 45=%d lring" % (res, res, res, res), log)
    for cur, top in ((6, 7), (8, 9)):
        t = gc.rd("player", top)
        if t:
            gc.setstat("player", cur, t)
    return dmg


def gear_note(level, dmg, diff):
    return ("help: gear (an axe in each hand, %d-%d damage, 400 %% AR, 60 %% IAS; ring +%d vitality, replenish life, 50 %% DR; belt +%d vitality, 75 %% poison length reduction; amulet "
            "75 resist, +500 energy, 300 %% mana regeneration; second ring +%d resist)" % (dmg, dmg * 2, level * 60, level * BELT_VIT, 50 * diff))


def click_mon(gc, mon_id, button="right", dy_px=-30):
    """A background click on a monster (game_checks.click_unit's geometry, aimed a little above the feet)."""
    st = gc.hstate()
    p = st["player"]
    m = next((m for m in st["mons"] if m.get("id") == mon_id), None)
    if m is None or "mx" not in m:
        return False
    dx, dy = m["mx"] - p["x"], m["my"] - p["y"]
    x, y = 800 + (dx - dy) * 27, 405 + (dx + dy) * 13.5 + dy_px
    if not (40 <= x <= 1560 and 40 <= y <= 780):
        return False
    gc.g.click(x / 1600, y / 900, button=button)
    return True


def close_in(gc, mon_id, reach=7, c=None):
    """Run straight to the boss (`move` legs). When the legs do not move the character (a pack boxes it in: Catacombs 4's arrival,
    runs checks-20261029-013141-s1 and -014324-s1) the nearest monsters in the way are hit with the right-button skill by clicks
    (or the cast function), as a player clears a path. True when the boss is within `reach`."""
    u = gc.parse_moveto(gc.H("moveto %d" % mon_id)[1])
    if u is None:
        return True
    for _ in range(6):
        p = gc.hstate()["player"]
        if gc.player_dead(p):
            return False
        if abs(p.get("x", 0) - u["x"]) <= reach and abs(p.get("y", 0) - u["y"]) <= reach:
            return True
        before = (p.get("x"), p.get("y"))
        gc.acts_walk(u["x"], u["y"], reach=reach, timeout=6)
        p = gc.hstate()["player"]
        if (p.get("x"), p.get("y")) != before:
            continue
        for m in gc.hostiles_near(gc.hstate(), 12, skip=(u["class"],))[:2]:  # boxed in: clear the way
            for _hit in range(4):
                if not (gc.acts_mon_life(m["id"]) or 0) > 0:
                    break
                if not click_mon(gc, m["id"]):
                    gc.H("cast %d unit %d" % (ATTACK, m["id"]))
                if c is not None:
                    c["way"] = c.get("way", 0) + 1
                time.sleep(0.8)
    return False


def fight(gc, mon_id, skill, timeout, log, on_tick=None):
    """Fight one monster with `skill` on the right button: right clicks on it (player path); after CLICK_MISSES clicks without
    damage the server's cast function (the cast packet's call) for 6 casts, then clicks again. Returns (killed, deaths, secs,
    counts) with counts {click, click_dmg, cast, cast_dmg, nomana}. `on_tick(counts)` runs before each swing."""
    gc.H("skill right %d" % skill)
    cost = int((gc.row_of("skills", "*Id", skill) or {}).get("mana") or 0)
    c = {"click": 0, "click_dmg": 0, "cast": 0, "cast_dmg": 0, "nomana": 0}
    t0, last, misses, cast_left = time.time(), None, 0, 0
    area0 = gc.hstate()["player"].get("area")
    d0 = gc.STATE.get("acts_deaths", 0)

    def deaths():  # the walk's own fights (acts_clear) count and revive a death too
        return gc.STATE.get("acts_deaths", 0) - d0
    while time.time() - t0 < timeout:
        p = gc.hstate()["player"]
        if p and gc.player_dead(p):
            gc.STATE["acts_deaths"] = gc.STATE.get("acts_deaths", 0) + 1
            gc.revive_if_dead()
            return False, deaths(), int(time.time() - t0), c
        if p.get("area") != area0 or deaths():
            return False, deaths(), int(time.time() - t0), c
        life = gc.acts_mon_life(mon_id)
        if life is not None and life <= 0:
            return True, 0, int(time.time() - t0), c
        if life is None:
            return (last is not None and last < gc.ACTS_GONE_LOW), 0, int(time.time() - t0), c
        last = life
        if on_tick is not None:  # lane nmhell2: potions from the belt between swings
            on_tick(c)
        if not close_in(gc, mon_id, reach=7, c=c):
            continue
        if ((gc.rd("player", 8) or 0) >> 8) < cost:
            c["nomana"] += 1
            time.sleep(1.5)
            continue
        by_click = cast_left == 0 and click_mon(gc, mon_id)
        if not by_click:
            gc.H("cast %d unit %d" % (skill, mon_id))
            cast_left = max(0, cast_left - 1)
        time.sleep(0.35)
        st = gc.hstate()  # lane nmhell3: player mode 18 = Blood Hatred's sequence, 7 = a plain Attack (bug #397)
        mode = st["player"].get("mode")
        c["modes"] = c.get("modes", {})
        c["modes"][mode] = c["modes"].get(mode, 0) + 1
        bmode = next((m.get("mode") for m in st["mons"] if m.get("id") == mon_id), None)  # the boss: get-hit 4, block 7?
        c["bmodes"] = c.get("bmodes", {})
        c["bmodes"][bmode] = c["bmodes"].get(bmode, 0) + 1
        time.sleep(0.55)
        after = gc.acts_mon_life(mon_id)
        dmg = max(0, (life - after)) >> 8 if after is not None else 0
        key = "click" if by_click else "cast"
        c[key] += 1
        c[key + "_dmg"] += dmg
        if by_click:
            misses = 0 if dmg > 0 else misses + 1
            if misses >= CLICK_MISSES:
                cast_left, misses = 6, 0
    return False, deaths(), int(time.time() - t0), c


def fight_note(c):
    return ("right clicks %d (%d damage), cast-function fallback %d (%d damage), waits for mana %d, hits on monsters in the way %d; "
            "player mode 0.35 s after each swing %s (18 Blood Hatred, 7 Attack), boss mode then %s"
            % (c["click"], c["click_dmg"], c["cast"], c["cast_dmg"], c["nomana"], c.get("way", 0), mode_text(c.get("modes", {})),
               mode_text(c.get("bmodes", {}))))


def mode_text(modes):
    """{mode: count} -> 'mode:count' sorted by count, most first ('none' when empty)."""
    return " ".join("%s:%d" % (m, n) for m, n in sorted(modes.items(), key=lambda kv: (-kv[1], str(kv[0])))) or "none"


def path_word(c):
    """'player path' when the clicks did most of the damage, else 'cast function' (harness help)."""
    return "player path (clicks)" if c["click_dmg"] >= c["cast_dmg"] else "cast function (help)"


def enter(gc, difficulty, log, shots):
    """From the main menu: the lane character's card, Play, a screenshot of the difficulty dialog, the difficulty's button."""
    g = gc.g
    card = gc.card_of(g.CHAR_NAME)
    y = gc.card_y(card or 0)
    if y is None:
        log.append("%s is not on the visible character list (card %s)" % (g.CHAR_NAME, card))
        return False
    g.click(0.87, y)
    time.sleep(0.8)
    g.click(*g.UI["menu_play"])
    time.sleep(3)
    shots.append(gc.sh("nmh_dialog_%s" % difficulty))
    ok = False
    for _attempt in range(2):
        g.click(0.5, gc.DIFF_Y[difficulty])
        ok = gc.wait_in_game(45)
        if ok:
            break
        g.click(*g.UI["menu_play"])
        time.sleep(3)
    gc.STATE["in_game"] = ok
    if ok and gc.hstate()["player"].get("class") != gc.save_class(g.CHAR_NAME):
        gc.STATE["in_game"] = False
        log.append("another character is in the game: stopped")
        return False
    return ok


def closed_edit_and_enter(gc, fn, difficulty, log, shots):
    """Save and Exit, close the game, the save edit, start the game, Play in `difficulty` (dialog screenshot)."""
    if not gc.rc2_save_exit():
        raise RuntimeError("Save and Exit did not leave the game")
    gc.g.stop()
    time.sleep(2)
    rc_setup.edit(gc.SAVES, gc.g.CHAR_NAME, fn)
    if not gc.to_menu():
        raise RuntimeError("the game did not come back to the menu after the save edit")
    return enter(gc, difficulty, log, shots)


def ensure(gc, difficulty, log, shots):
    """In `difficulty` (Save and Exit and Play there when the game is in another one)."""
    if gc.STATE.get("in_game") and gc.hstate()["player"].get("difficulty") == DIFFS[difficulty]:
        return True
    if gc.STATE.get("in_game") and not gc.rc2_save_exit():
        return False
    return enter(gc, difficulty, log, shots)


# ------------------------------------------------------------------ steps
def step_enter(gc, difficulty, shots, log):
    diff = DIFFS[difficulty]
    mark = gc.engine_mark()
    p = gc.hstate()["player"]
    qs = {q: gc.quest_bits(q) for q in (1, 6)}
    ok = p.get("difficulty") == diff and p.get("area") == 1
    gc.finish("nmh %s: enter (difficulty dialog, Rogue Encampment)" % difficulty, ok and all(v == "0" * 16 for v in qs.values()),
              "difficulty %s (want %d), area %s (want 1), level %s; this difficulty's quest words start empty: quest 1 %s, quest 6 %s "
              "(Normal's are done in the save); the difficulty dialog's screenshot is in the set-up row" % (
                  p.get("difficulty"), diff, p.get("area"), p.get("level"), qs[1], qs[6]),
              mark, list(shots) + [gc.sh("nmh_%s_town" % difficulty)], log)


def step_hellgate(gc, log):
    """With progression 5 (Normal done, Nightmare not) the dialog's Hell button is clicked: 1.13c and D2R refuse Hell then (the
    button is disabled). The character goes back to Nightmare afterwards."""
    mark = gc.engine_mark()
    shots = []
    prog = None
    if not gc.rc2_save_exit():
        return gc.add("nmh nightmare: Hell refused before Nightmare is done", "BLOCKED", "Save and Exit did not leave the game")
    try:
        with open(os.path.join(gc.SAVES, gc.g.CHAR_NAME + ".d2s"), "rb") as f:
            prog = f.read(0x16)[rc_setup.OFF_PROGRESSION]
    except OSError:
        pass
    got = enter(gc, "hell", log, shots)
    diff = gc.hstate()["player"].get("difficulty") if got else None
    if got:
        shots.append(gc.sh("nmh_hellgate_ingame"))
    else:  # still on the menu / dialog: close it
        gc.g.press("esc")
        time.sleep(1)
    back = ensure(gc, "nightmare", log, shots)
    gc.finish("nmh nightmare: Hell refused before Nightmare is done", prog == 5 and diff != 2 and back,
              "save progression byte %s (5 = Normal done); Hell button clicked: in game %s, difficulty %s (2 = Hell entered); back in "
              "Nightmare %s" % (prog, got, diff, back), mark, shots, log)


def step_monsters(gc, difficulty, log):
    """Blood Moor's own monsters: monster level (stat 12) against the area level, maximum life against the table range."""
    diff = DIFFS[difficulty]
    mark = gc.engine_mark()
    st = gc.goto(FIELD)
    alvl = area_level(gc.row_of("levels", "Id", FIELD), diff)
    sample, seen = [], set()
    p0 = st["player"]
    for dx, dy in ((0, 0),) + gc.EXPLORE_LEGS:
        if dx or dy:
            gc.acts_walk(p0.get("x", 0) + dx, p0.get("y", 0) + dy, reach=15, timeout=40)
        for m in gc.hostiles_near(gc.hstate(), 40):
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            lvl = gc.rd("mon:%d" % m["id"], 12)
            top = gc.rd("mon:%d" % m["id"], 7)
            if lvl is None or top is None:
                continue
            sample.append((m.get("class"), lvl, top >> 8, expected_life(gc, m.get("class"), lvl, diff)))
        if len(sample) >= 15:
            break
    at, ok, other = judge_sample(sample, alvl)
    log.append("sample (class, level, max life, table range): %s" % sample)
    shot = gc.sh("nmh_%s_bloodmoor" % difficulty)
    gc.goto(1)
    gc.finish("nmh %s: Blood Moor monster level and life" % difficulty, bool(at) and len(ok) == len(at),
              "area level %d (levels MonLvlEx%s); %d monsters read, %d at the area level, %d of those with life in the table range; "
              "other levels (champions / uniques +2 / +3, minions): %s; first rows %s" % (
                  alvl, SUFFIX[diff], len(sample), len(at), len(ok), sorted({s[1] for s in other}), sample[:6]),
              mark, [shot], log)


def step_waypoint(gc, difficulty, log):
    """Cold Plains' waypoint: the bit of this difficulty is 0, the operate (the click's OperateFn 23) sets it and opens the panel,
    a click on the Rogue Encampment line takes the character to town."""
    mark = gc.engine_mark()
    gc.goto(1)
    gc.Hl("level %d warp 13" % WP_AREA, log)  # travel help: the waypoint warp's arrival
    time.sleep(8)
    area = gc.hstate()["player"].get("area")
    num = int(gc.row_of("levels", "Id", WP_AREA)["Waypoint"])
    _ok, ln = gc.Hl("waypoint n %d get" % num, log)
    before = gc.first(ln, r"= (\d)")
    wp = gc.find_waypoint_object()
    shots = []
    if wp:
        objs = [o for o in gc.parse_objects(gc.Hl("objects %d" % wp[1], log)[1]) if o["id"] == wp[0]]
        if objs:
            gc.acts_walk(objs[0]["x"] + 2, objs[0]["y"] + 2, reach=4, timeout=40)
        gc.Hl("operate %d 23" % wp[0], log)
        time.sleep(3)
    _ok, ln = gc.Hl("waypoint n %d get" % num, log)
    after = gc.first(ln, r"= (\d)")
    shots.append(gc.sh("nmh_%s_wp_panel" % difficulty))
    gc.g.click(*WP_FIRST_LINE)
    for _ in range(8):
        time.sleep(2)
        if gc.hstate()["player"].get("area") == 1:
            break
    town = gc.hstate()["player"].get("area")
    if town != 1:
        gc.g.press("esc")
        time.sleep(1)
    gc.finish("nmh %s: Cold Plains waypoint and the panel's travel" % difficulty, area == WP_AREA and before == 0 and after == 1 and town == 1,
              "arrived in %s (want %d, travel help `level %d warp 13`); waypoint object %s; waypoint number %d: bit before %s, after the operate %s; "
              "after the click on the panel's first line: area %s (want 1)" % (area, WP_AREA, WP_AREA, wp, num, before, after, town),
              mark, shots, log)


def step_town(gc, difficulty, log):
    """Akara's first talk starts the Den of Evil (quest 1) in this difficulty; Warriv shows no travel line before Andariel."""
    mark = gc.engine_mark()
    gc.goto(1)
    q0 = gc.quest_bits(1)
    ak = gc.acts_menu(AKARA)
    time.sleep(3)
    gc.close_menu()
    q1 = gc.quest_bits(1)
    wv = gc.acts_menu(WARRIV)
    gc.close_menu()
    if wv:
        gc.STATE.setdefault("menus", {})[WARRIV] = wv
    gc.finish("nmh %s: Akara starts the Den of Evil, Warriv before Andariel" % difficulty, bool(ak) and q1 != q0 and bool(wv),
              "Akara menu %s; quest 1 bits %s -> %s; Warriv menu lines %s (kept: the travel line must be new after Andariel)" % (
                  [("%x" % s) for _i, s, _h in (ak or {"lines": []})["lines"]], q0, q1,
                  [("%x" % s) for _i, s, _h in (wv or {"lines": []})["lines"]]), mark, [gc.sh("nmh_%s_town_talks" % difficulty)], log)


def step_boss(gc, difficulty, stage, level, setup_note, log):
    diff = DIFFS[difficulty]
    _act, area, cls, _lvl, quest = gc.ACT_BOSSES[stage]
    mark = gc.engine_mark()
    dmg = gear(gc, level, diff, log)
    q0 = gc.quest_bits(quest)
    st = gc.goto(area)
    name = "nmh %s: %s" % (difficulty, stage)
    if st["player"].get("area") != area:
        return gc.finish(name, False, "did not reach level %d (area %s)" % (area, st["player"].get("area")), mark, log=log)
    mon = gc.acts_find(cls, log)
    if mon is None:
        return gc.finish(name, False, "no unit of class %d in level %d" % (cls, area), mark, [gc.sh("nmh_%s_%s_nofind" % (difficulty, stage))], log)
    want_lvl = boss_level(mon_row(gc, cls), diff)
    blvl = gc.rd("mon:%d" % mon["id"], 12)
    top = (gc.rd("mon:%d" % mon["id"], 7) or 0) >> 8
    lo, hi = expected_life(gc, cls, want_lvl, diff)
    shot0 = gc.sh("nmh_%s_%s_found" % (difficulty, stage))
    killed, deaths, secs, c = fight(gc, mon["id"], ATTACK, FIGHT_S[diff], log)
    while not killed and 0 < deaths <= gc.ACTS_BOSS_RETRIES:  # back after a death, as a player does (gear given again)
        gear(gc, level, diff, log)
        gc.goto(area)
        mon2 = gc.acts_find(cls, log)
        if not mon2:
            break
        log.append("retry %d: boss life %s" % (deaths, mon2.get("life")))
        k2, d2, s2, c2 = fight(gc, mon2["id"], ATTACK, FIGHT_S[diff], log)
        killed, deaths, secs = k2, deaths + d2, secs + s2
        for k in c:
            c[k] += c2[k]
        if not d2:
            break
    time.sleep(4)
    q1 = gc.quest_bits(quest)
    drops = parse_ground(gc.Hl("ground", log)[1]) if killed else []
    for d in drops[:6]:  # the item's tooltip lines (name, quality colour removed) for the log: read by hand
        gc.Hl("tip %s" % d.get("code"), log)
    drop_txt = ", ".join(str(d.get("code")) for d in drops[:20]) or "none listed"
    stats_ok = blvl == want_lvl and lo <= top <= hi + 1
    note = ("%s; %s; boss class %d level %s (monstats Level%s %d), max life %d (table %d-%d); Blood Hatred: %s after %d s, %d deaths; "
            "%s -> %s; quest %d bits %s -> %s; ground after the kill: %s"
            % (setup_note, gear_note(level, dmg, diff), cls, blvl, SUFFIX[diff], want_lvl, top, lo, hi,
               "killed it" if killed else "did not kill it", secs, deaths, fight_note(c), path_word(c), quest, q0, q1, drop_txt))
    if killed:
        gc.STATE.setdefault("acts_killed", set()).add(stage)
    gc.finish(name, killed and q1 != q0 and stats_ok, note, mark, [shot0, gc.sh("nmh_%s_%s_after" % (difficulty, stage))], log)
    return killed


def run(gc, difficulty, steps=None):
    """All steps of one difficulty (MXL_NMH_STEPS=enter,monsters,waypoint,town,andariel,travel12,duriel picks some;
    MXL_NMH_STEPS_NIGHTMARE / MXL_NMH_STEPS_HELL for one difficulty only)."""
    env = os.environ.get("MXL_NMH_STEPS_" + difficulty.upper(), os.environ.get("MXL_NMH_STEPS", ""))
    want = [s.strip() for s in (steps or env).split(",") if s.strip()]
    order = (["enter"] + (["hellgate"] if difficulty == "nightmare" else []) + ["monsters", "waypoint", "town", "andariel", "travel12"]
             + (["duriel"] if difficulty == "nightmare" else []))
    log, shots = [], []
    gc.STATE["menus"] = {}
    if not ensure(gc, difficulty, log, shots):
        return gc.add("nmh %s" % difficulty, "BLOCKED", "not in %s: %s" % (difficulty, "; ".join(log)), shots, log)
    level = LEVEL[difficulty]
    note = gc.STATE.get("nmh_setup_note", "SET-UP: see nmhsetup")
    if (gc.hstate()["player"].get("level") or 0) < level:
        _lvl, note = build(gc, level, log)
    for stage in order:
        if want and stage not in want:
            continue
        try:
            gc.guard()
            gc.clean_start_state("nmh " + stage)
            slog = []
            if stage == "enter":
                step_enter(gc, difficulty, shots, slog)
            elif stage == "hellgate":
                step_hellgate(gc, slog)
            elif stage == "monsters":
                step_monsters(gc, difficulty, slog)
            elif stage == "waypoint":
                step_waypoint(gc, difficulty, slog)
            elif stage == "town":
                step_town(gc, difficulty, slog)
            elif stage in ("andariel", "duriel"):
                step_boss(gc, difficulty, stage, level, note, slog)
            elif stage == "travel12":
                if "andariel" not in gc.STATE.get("acts_killed", set()):
                    gc.add("nmh %s: travel12" % difficulty, "BLOCKED", "Andariel was not killed in this run")
                    continue
                gc.acts_travel("travel12")
        except Exception as e:
            gc.add("nmh %s %s" % (difficulty, stage), "BLOCKED", "script error: %r" % (e,))
            if gc.WD.abort:
                break


def setup(gc):
    """nmhsetup: Normal character -> level, points, skills; save edit progression 5 (Nightmare open), Normal bosses done; Play in
    Nightmare (the dialog's screenshot shows Hell greyed)."""
    log, shots = [], []
    gc.goto(1)
    _lvl, note = build(gc, LEVEL["nightmare"], log)
    ok = closed_edit_and_enter(gc, unlock_edit("nightmare"), "nightmare", log, shots)
    note += "; save edit: progression 5, Normal quests %s done" % (BOSS_QUESTS_DONE,)
    gc.STATE["nmh_setup_note"] = note
    p = gc.hstate()["player"] if ok else {}
    gc.add("nmhsetup", "INFO" if ok and p.get("difficulty") == 1 else "BLOCKED",
           "%s; in game %s, difficulty %s, area %s" % (note, ok, p.get("difficulty"), p.get("area")), shots, log)


def hell(gc):
    """nmhhell: level 120 (xp award), points again, save edit progression 10 (Hell open: Nightmare's bosses done), Play in Hell."""
    log, shots = [], []
    if gc.STATE.get("in_game"):
        gc.goto(1)
        _lvl, note = build(gc, LEVEL["hell"], log)
        ok = closed_edit_and_enter(gc, unlock_edit("hell"), "hell", log, shots)
        note += "; save edit: progression 10, Normal and Nightmare quests %s done" % (BOSS_QUESTS_DONE,)
        gc.STATE["nmh_setup_note"] = note
        p = gc.hstate()["player"] if ok else {}
        gc.add("nmhhell setup", "INFO" if ok and p.get("difficulty") == 2 else "BLOCKED",
               "%s; in game %s, difficulty %s" % (note, ok, p.get("difficulty")), shots, log)
        if not ok:
            return
    run(gc, "hell")


# ------------------------------------------------------------------ lane nmhell2: hit log (why Duriel takes less per click)
# Read on the boss: Median's monprop `mon-avall` gives dodge / avoid / evade (338-340), monstats ToBlock / AC block (20) and
# defense (31); 36 / 37 damage / magic resist; 171 the defense % of Duriel's Idol2Scosglen state (290 galioami).
BOSS_STATS = ((338, "dodge"), (339, "avoid"), (340, "evade"), (20, "block"), (31, "defense"), (36, "damage resist"),
              (37, "magic resist"), (171, "skill defense %"), (16, "defense %"))
PLAYER_STATS = ((25, "damage %"), (68, "attack rate"), (19, "attack rating"), (93, "IAS"))
ST_STUNNED, ST_WARPFIELD = 21, 237  # states.txt rows: stunned; the target state of Duriel's Void Archon Amp Aura
PMODE_ATTACK = (7, 8, 18)  # player modes A1, A2, SQ (Blood Hatred plays the sequence)
MMODE_GETHIT, MMODE_BLOCK = 3, 6
HITLOG_CLICKS = 16
HITLOG_POLLS = 5  # reads of life and modes after each click, 0.25 s apart
AVOID_STATS = (338, 339, 340, 20)  # zeroed on Duriel in the second phase


def parse_state_ids(lines):
    """`states` answer -> the set of state ids (`server state N: bit=1 ...`)."""
    return {int(m.group(1)) for ln in lines for m in [re.search(r"state (\d+): bit=1", ln)] if m}


def summarize_hits(rows):
    """rows: [{clicked, stunned, pmodes, bmodes, dmg}] -> counts and the mean damage of the clicks that did damage."""
    hit = [r["dmg"] for r in rows if r["dmg"] > 0]
    return {"clicks": len(rows), "clicked": sum(1 for r in rows if r["clicked"]),
            "stunned": sum(1 for r in rows if r["stunned"]),
            "swung": sum(1 for r in rows if set(r["pmodes"]) & set(PMODE_ATTACK)),
            "blocked": sum(1 for r in rows if MMODE_BLOCK in r["bmodes"]),
            "gethit": sum(1 for r in rows if MMODE_GETHIT in r["bmodes"]),
            "hits": len(hit), "total": sum(hit), "per_hit": (sum(hit) // len(hit)) if hit else 0,
            "per_click": (sum(hit) // len(rows)) if rows else 0}


def summary_text(s):
    return ("%d clicks (%d reached the client), %d with the player stunned, %d with an attack mode seen, boss block mode %d, "
            "boss get-hit mode %d; %d did damage: total %d, %d per damaging hit, %d per click"
            % (s["clicks"], s["clicked"], s["stunned"], s["swung"], s["blocked"], s["gethit"], s["hits"], s["total"],
               s["per_hit"], s["per_click"]))


def read_stats(gc, ref, stats):
    return {name: gc.rd(ref, sid) for sid, name in stats}


def hit_log(gc, mon_id, n, log, c):
    """n right clicks on the boss (Blood Hatred on the right button), each followed by HITLOG_POLLS reads of its life and of
    both modes. Diagnostic help (named in the note): the player's life is filled by harness before a click when below 70 %."""
    rows = []
    for _ in range(n):
        p = gc.hstate()["player"]
        if gc.player_dead(p):
            gc.STATE["acts_deaths"] = gc.STATE.get("acts_deaths", 0) + 1
            c["dead"] = c.get("dead", 0) + 1
            break
        top = gc.rd("player", 7) or 0
        if top and (gc.rd("player", 6) or 0) < top * 7 // 10:
            gc.setstat("player", 6, top)
            c["refill"] = c.get("refill", 0) + 1
        if not close_in(gc, mon_id, reach=5, c=c):
            continue
        pst = parse_state_ids(gc.H("states player")[1])
        life0 = gc.acts_mon_life(mon_id)
        if life0 is None:
            break
        dist = next((m.get("dist") for m in gc.hstate()["mons"] if m.get("id") == mon_id), None)
        clicked = click_mon(gc, mon_id)
        pm, bm, low = [], [], life0
        for _p in range(HITLOG_POLLS):
            time.sleep(0.25)
            st = gc.hstate()
            pm.append(st["player"].get("mode"))
            bm.append(next((m.get("mode") for m in st["mons"] if m.get("id") == mon_id), None))
            life = gc.acts_mon_life(mon_id)
            if life is not None:
                low = min(low, life)
        row = {"clicked": clicked, "stunned": ST_STUNNED in pst, "warp": ST_WARPFIELD in pst, "dist": dist,
               "pmodes": pm, "bmodes": bm, "dmg": max(0, life0 - low) >> 8}
        rows.append(row)
        log.append("hit %d: %s" % (len(rows), row))
    return rows


def step_hitlog(gc, difficulty, stage, level, log):
    """Hit log on one boss with nmhell's help gear: boss stats and states, the player's stats and states in the fight, then
    HITLOG_CLICKS right clicks; on Duriel a second phase with dodge / avoid / evade / block zeroed on him (harness)."""
    diff = DIFFS[difficulty]
    _act, area, cls, _lvl, _q = gc.ACT_BOSSES[stage]
    mark = gc.engine_mark()
    name = "nmh %s: hit log %s" % (difficulty, stage)
    strong = os.environ.get("MXL_NMH_HITLOG_GEAR") == "kill"  # the kill build (run3): Andariel's walk through Catacombs 4 survives
    dmg = kill_gear(gc, level, diff, log) if strong else gear(gc, level, diff, log)
    st = gc.goto(area)
    if st["player"].get("area") != area:
        return gc.finish(name, False, "did not reach level %d" % area, mark, log=log)
    mon = gc.acts_find(cls, log)
    if mon is None:
        return gc.finish(name, False, "no unit of class %d" % cls, mark, [gc.sh("nmh_hitlog_%s_nofind" % stage)], log)
    mid = mon["id"]
    gc.H("skill right %d" % ATTACK)
    c = {}
    close_in(gc, mid, reach=5, c=c)
    bstats = read_stats(gc, "mon:%d" % mid, BOSS_STATS)
    bstates = sorted(parse_state_ids(gc.H("states mon:%d" % mid)[1]))
    rows = hit_log(gc, mid, HITLOG_CLICKS, log, c)
    pstats = read_stats(gc, "player", PLAYER_STATS)
    pstates = sorted(parse_state_ids(gc.H("states player")[1]))
    s1 = summarize_hits(rows)
    note = ("%s; help: player life filled by harness before %d clicks (diagnostic, not a fight verdict), deaths %d; boss id %d "
            "stats %s, states %s; player in the fight: stats %s, states %s (237 = Void Archon Amp Aura's target state, 21 "
            "stunned); base phase: %s" % ((kill_gear_note if strong else gear_note)(level, dmg, diff), c.get("refill", 0), c.get("dead", 0), mid, bstats,
                                          bstates, pstats, pstates, summary_text(s1)))
    shots = [gc.sh("nmh_hitlog_%s_base" % stage)]
    s2 = None
    if stage == "duriel" and gc.acts_mon_life(mid):
        for sid in AVOID_STATS:
            gc.setstat("mon:%d" % mid, sid, 0)
        after = read_stats(gc, "mon:%d" % mid, [(s, n) for s, n in BOSS_STATS if s in AVOID_STATS])
        s2 = summarize_hits(hit_log(gc, mid, HITLOG_CLICKS, log, c))
        note += "; second phase (harness: stats %s set to 0 on him, read back %s): %s" % (AVOID_STATS, after, summary_text(s2))
        shots.append(gc.sh("nmh_hitlog_%s_noavoid" % stage))
    gc.STATE.setdefault("nmh_hitlog", {})[stage] = (s1, s2)
    gc.finish(name, s1["clicks"] >= HITLOG_CLICKS // 2, note, mark, shots, log)


def save_progression(gc, name):
    """Progression (title) byte of a closed save in the slot's folder, None when unreadable."""
    try:
        with open(os.path.join(gc.SAVES, name + ".d2s"), "rb") as f:
            return f.read(0x16)[rc_setup.OFF_PROGRESSION]
    except (OSError, IndexError):
        return None


def dialog(gc):
    """nmhdialog: from the main menu, for each character of MXL_NMH_DIALOG (names, default the lane character): its card, Play,
    a screenshot of the difficulty dialog, Esc (no game is entered, nothing is saved); with the save's progression byte."""
    names = [s.strip() for s in os.environ.get("MXL_NMH_DIALOG", gc.g.CHAR_NAME).split(",") if s.strip()]
    if gc.STATE.get("in_game") and not gc.rc2_save_exit():
        return gc.add("nmhdialog", "BLOCKED", "Save and Exit did not leave the game")
    gc.STATE["in_game"] = False
    rows, shots = [], []
    for name in names:
        prog, card = save_progression(gc, name), gc.card_of(name)
        y = gc.card_y(card or 0)
        if y is None:
            rows.append("%s: card %s not on the visible list" % (name, card))
            continue
        if prog is None or prog < rc_setup.PROGRESSION["nightmare"]:  # Play starts Normal at once: no dialog (run
            rows.append("%s: progression %s, not played (no dialog: Play enters Normal)" % (name, prog))  # checks-20261029-023811-s1)
            continue
        gc.g.click(0.87, y)
        time.sleep(0.8)
        gc.g.click(*gc.g.UI["menu_play"])
        time.sleep(3)
        shots.append(gc.sh("nmh_dialog_card_%s" % name))
        rows.append("%s: card %d, progression byte %s, dialog in nmh_dialog_card_%s.png" % (name, card, prog, name))
        gc.g.press("esc")
        time.sleep(1.5)
    gc.add("nmhdialog", "INFO", "; ".join(rows) + " (read the screenshots: which buttons are drawn greyed)", shots)


def hitlog(gc):
    """nmhhitlog: hit logs on Andariel and Duriel in Nightmare with the same gear (MXL_NMH_HITLOG=andariel,duriel)."""
    log, shots = [], []
    if not ensure(gc, "nightmare", log, shots):
        return gc.add("nmh hitlog", "BLOCKED", "not in Nightmare: %s" % "; ".join(log), shots, log)
    level = gc.hstate()["player"].get("level") or LEVEL["nightmare"]
    for stage in [s.strip() for s in os.environ.get("MXL_NMH_HITLOG", "andariel,duriel").split(",") if s.strip()]:
        try:
            gc.guard()
            gc.clean_start_state("nmh hitlog " + stage)
            step_hitlog(gc, "nightmare", stage, level, [])
        except Exception as e:
            gc.add("nmh hitlog %s" % stage, "BLOCKED", "script error: %r" % (e,))
            if gc.WD.abort:
                break


# ------------------------------------------------------------------ lane nmhell2: boss kills with a stronger build
KASHYA, ROGUE_MERC = 150, 271
HIRE_GOLD = 200000
KILL_GEAR_MULT = {1: 20, 2: 60}  # weapon damage factor on acts_gear's base (nmhell's GEAR_MULT doubled)
POTIONS = ("rvl", 4)  # Full Rejuvenation Potions picked up from the ground into the belt (Median: life over time, hpregen)
DRINK_BELOW = 45  # % of maximum life
KILL_STAGES = "nightmare:andariel,nightmare:travel12,nightmare:duriel,hell:andariel"


def drink_due(life, top, drinks_left):
    """A belt key press is due: life below DRINK_BELOW % and a potion left."""
    return drinks_left > 0 and top > 0 and life * 100 < top * DRINK_BELOW


def kill_gear(gc, level, diff, log):
    """gear() (nmhell's help gear: acts_gear's ring with 200 % faster hit recovery and 50 % damage reduction, belt, amulet,
    resist ring) with the weapon's damage at KILL_GEAR_MULT and a body armour (+300 % defense, 30 % damage reduction, 100 %
    faster hit recovery). Life filled."""
    gear(gc, level, diff, log)
    dmg = (40 + level * 12) * KILL_GEAR_MULT[diff]
    axes(gc, dmg, log)
    gc.H("unequip torso")
    gc.Hl("equip 600 16=300 36=30 99=100 torso", log)
    for cur, top in ((6, 7), (8, 9)):
        t = gc.rd("player", top)
        if t:
            gc.setstat("player", cur, t)
    return dmg


def kill_gear_note(level, dmg, diff):
    return ("help: gear (an axe in each hand, %d-%d damage, 400 %% AR, 60 %% IAS; body armour +300 %% defense, 30 %% DR, 100 %% FHR; ring 200 %% "
            "FHR, 50 %% DR, +%d vitality; belt +%d vitality; amulet 75 resist, +500 energy; second ring +%d resist)"
            % (dmg, dmg * 2, level * gc_vit(), level * BELT_VIT, 50 * diff))


def gc_vit():
    import game_checks
    return game_checks.ACTS_VIT


def belt_potions(gc, log):
    """Fixture: POTIONS made on the ground; judged: the click pick-up (the game puts a potion into the belt). Returns how many
    left the ground."""
    code, n = POTIONS
    got = 0
    for _ in range(n):
        iid = gc.rp_ground_item(code, log)
        if iid is not None and gc.rp_pickup(iid, log, to_inv=True):
            got += 1
        gc.release_held_item()
    return got


def merc_ready(gc, log):
    """A Rogue hired from Kashya on the player path (NPC click, the Hire line's list, the hire button; fixtures gold and the
    Burial Grounds gate bit, game_checks.hire_in). Keeps one already hired."""
    m, _w = gc.merc_info()
    if m is not None and m.get("life", 1) > 0:
        return "mercenary kept: class %s level %s" % (m.get("class"), m.get("level"))
    rows, bad = [], []
    gc.set_gold(HIRE_GOLD)  # fixture: hire_in tops gold up to 30,000 only; Kashya asks 66,875-80,700 at level 120 (run2)
    m = gc.hire_in(1, 1, KASHYA, "Kashya", ROGUE_MERC, log, rows, bad)
    rows.insert(0, "fixture gold %d" % HIRE_GOLD)
    return "; ".join(rows + bad) if m is not None else "no mercenary: %s" % "; ".join(bad or rows)


ACT_TOWN = {"andariel": 1, "duriel": 40, "mephisto": 75, "diablo": 103, "baal": 109}  # the act's town (gear, potions, mercenary)
DROP_RADIUS = 30  # ground items within this of the character after a kill are the kill's drops
DROP_ITEMS = 8  # items picked up (click), identified and hovered per kill
FAR_TICKS = 2  # swings in a row with the boss out of reach before the travel help
PLACE_MAX = 3  # `place` helps per boss


def kill_targets(spec):
    """MXL_NMH_KILL text -> [(difficulty, stage)]; unknown difficulties are refused."""
    out = []
    for item in [s.strip() for s in spec.split(",") if s.strip()]:
        difficulty, stage = item.split(":")
        if difficulty not in DIFFS:
            raise ValueError("unknown difficulty %r" % difficulty)
        out.append((difficulty, stage))
    return out


def split_drops(ground, radius=DROP_RADIUS):
    """parse_ground rows -> (gold piles, items) within `radius`."""
    near = [d for d in ground if float(d.get("dist", 0) or 0) <= radius]
    return [d for d in near if d.get("code") == "gld"], [d for d in near if d.get("code") != "gld"]


def pick(gc, d, log):
    """Walk next to a ground item (the walk packet), then the click pick-up (game_checks.rp_pickup)."""
    if float(d.get("dist", 0) or 0) > 2.5:
        gc.acts_walk(d["x"], d["y"], reach=2, timeout=15)
    return gc.rp_pickup(d["id"], log, to_inv=True)


def drops_check(gc, difficulty, stage, log):
    """After a kill: the gold piles picked up by click (gold stat before / after), up to DROP_ITEMS items picked up into the
    emptied backpack (click), identified (harness `identify`, help: Cain's line is a separate check), hovered in the backpack
    (screenshots: the tooltips and ERROR strings are judged by eye). Returns (note, shots)."""
    time.sleep(3)
    gold_piles, items = split_drops(parse_ground(gc.Hl("ground", log)[1]))
    g0 = gc.rd("player", 14) or 0
    got_gold = sum(1 for d in gold_piles if pick(gc, d, log))
    time.sleep(1)
    g1 = gc.rd("player", 14) or 0
    gc.H("packclear")
    picked = []
    for d in items[:DROP_ITEMS]:
        if pick(gc, d, log):
            picked.append(d)
        gc.release_held_item()
    _ok, idl = gc.Hl("identify all", log)
    shots = []
    gc.STATE["rp_panel"] = False
    for d in picked:
        gc.rp_tooltip_shot(d["id"], "nmh_drop_%s_%s_%s_%d" % (difficulty, stage, d.get("code"), d["id"]), shots, True)
    if gc.STATE.get("rp_panel"):
        gc.g.press("i")
        gc.STATE["rp_panel"] = False
    note = ("drops within %d: %d gold piles (picked up %d, gold %d -> %d), %d items %s; picked up %d into the backpack, %s; "
            "tooltips: %d screenshots" % (DROP_RADIUS, len(gold_piles), got_gold, g0, g1, len(items),
                                          [d.get("code") for d in items[:20]], len(picked),
                                          gc.first(idl, r"(identify: .*)", cast=str) or "-", len(shots)))
    return note, shots


def place_at_preset(gc, stage, cls, log):
    """Travel help (named) for the stages in MXL_NMH_PLACE: `place` next to the boss's map preset, past the level's packs
    (Catacombs 4 killed the character on the walk in lanes nmhell, nmhell2, nmhell3). Returns the spot or None."""
    if stage not in [x.strip() for x in os.environ.get("MXL_NMH_PLACE", "").split(",")]:
        return None
    pres = [q for q in gc.parse_presets(gc.Hl("presets 1", log)[1]) if q["class"] == cls]
    if pres and gc.acts_place_near(pres[0]["x"], pres[0]["y"] + 6, log):
        return pres[0]["x"], pres[0]["y"] + 6
    return None


def with_kill_gear(gc, level, diff, log, fn):
    """Runs fn() with the kill gear standing in for game_checks.acts_gear (the acts lane's routines give it again after a
    death: 4,722 life at level 120, the Chaos Sanctuary walk died in seconds in run checks-20261029-055258-s1). Help, named."""
    acts_gear = gc.acts_gear

    def stand_in(_lvl, *_a):
        gc.acts_gear = acts_gear  # kill_gear builds on acts_gear itself (gear())
        try:
            return kill_gear(gc, level, diff, log)
        finally:
            gc.acts_gear = stand_in
    gc.acts_gear = stand_in
    try:
        return fn()
    finally:
        gc.acts_gear = acts_gear


def diag_boss(gc, cls, mid, log):
    """Diagnostic (harness, not the player path; MXL_NMH_DIAG names the stages): the units of the boss's class in view, and
    whether the boss's life comes back after the harness takes half of it (reads 0.2 / 1 / 3 s later; then set to full again
    so the fight starts as before). Explains 'get-hit mode but no life lost' (Mephisto Nightmare, run -070312-s1)."""
    same = sorted((m.get("id"), m.get("x"), m.get("y")) for m in gc.hstate()["mons"] if m.get("class") == cls)
    ref = "mon:%d" % mid
    top = gc.rd(ref, 7) or 0
    gc.Hl("stat %s 6 set %d" % (ref, top // 2), log)
    reads = []
    for wait in (0.2, 0.8, 2.0):
        time.sleep(wait)
        reads.append((gc.rd(ref, 6) or 0) >> 8)
    gc.Hl("stat %s 6 set %d" % (ref, top), log)
    return "diagnostic: class %d units in view %s; life set to %d by harness, read after 0.2 / 1 / 3 s: %s (restored to %d)" % (
        cls, same, (top // 2) >> 8, reads, top >> 8)


def reach_help(gc, mon_id, log):
    """Travel help (named): `place` next to a boss the walk does not reach (Mephisto across the moat). True when placed."""
    u = gc.parse_moveto(gc.H("moveto %d" % mon_id)[1])
    return bool(u) and gc.acts_place_near(u["x"] + 3, u["y"] + 3, log)


def merge_counts(c, c2):
    """Adds a retry's fight counts (numbers and the mode table) into the first fight's."""
    for k, v in c2.items():
        if isinstance(v, int):
            c[k] = c.get(k, 0) + v
    for key in ("modes", "bmodes"):
        modes = c.setdefault(key, {})
        for m, n in c2.get(key, {}).items():
            modes[m] = modes.get(m, 0) + n
    return c


def step_kill(gc, difficulty, stage, level, log):
    diff = DIFFS[difficulty]
    _act, area, cls, _lvl, quest = gc.ACT_BOSSES[stage]
    mark = gc.engine_mark()
    name = "nmh %s: %s kill (stronger build)" % (difficulty, stage)
    gc.goto(ACT_TOWN[stage])
    cut = gc.skip_cinematic()  # an act's cut scene left playing after a travel takes the clicks (Mephisto, run -055258-s1)
    merc = merc_ready(gc, log) if stage == "andariel" else merc_ready_any(gc)
    dmg = kill_gear(gc, level, diff, log)
    pots = belt_potions(gc, log)
    q0 = gc.quest_bits(quest)
    st = gc.goto(area)
    if st["player"].get("area") != area:
        return gc.finish(name, False, "did not reach level %d; %s" % (area, merc), mark, log=log)
    seals = None
    if stage == "diablo":  # the seals call him (the walk fights with acts' Attack and the kill gear)
        seals = with_kill_gear(gc, level, diff, log, lambda: gc.acts_open_seals(log))
        kill_gear(gc, level, diff, log)
    placed_at = place_at_preset(gc, stage, cls, log)
    mon = gc.acts_find(cls, log)
    if mon is None and seals and seals.get("centre"):
        gc.acts_walk(seals["centre"][0], seals["centre"][1], reach=20, timeout=180, fight=True, skip=(cls,))
        kill_gear(gc, level, diff, log)
        mon = gc.acts_find(cls, log, tries=1)
    seal_txt = "; seals %s" % {k: v for k, v in seals.items() if k != "centre"} if seals else ""
    if mon is None:
        return gc.finish(name, False, "no unit of class %d in level %d; %s%s" % (cls, area, merc, seal_txt), mark,
                         [gc.sh("nmh_kill_%s_%s_nofind" % (difficulty, stage))], log)
    walk_txt = ""
    if stage == "baal":  # the chamber's arrival is far from him with a pack in the corridor: walk up, fighting the way
        p0 = gc.hstate()["player"]
        ok = with_kill_gear(gc, level, diff, log, lambda: gc.acts_walk(mon["x"], mon["y"], reach=8, timeout=180, fight=True,
                                                                         skip=(cls,)))
        p1 = gc.hstate()["player"]
        walk_txt = "; walk to him with fighting (Attack): %s, from %s,%s to %s,%s (he is at %s,%s)" % (
            "arrived" if ok else "did not arrive", p0.get("x"), p0.get("y"), p1.get("x"), p1.get("y"), mon["x"], mon["y"])
    life0 = (gc.rd("mon:%d" % mon["id"], 6) or 0) >> 8
    top0 = (gc.rd("mon:%d" % mon["id"], 7) or 0) >> 8
    cut += gc.skip_cinematic()
    shot0 = gc.sh("nmh_kill_%s_%s_found" % (difficulty, stage))
    bstates = sorted(parse_state_ids(gc.Hl("states mon:%d" % mon["id"], log)[1]))
    bstats = read_stats(gc, "mon:%d" % mon["id"], BOSS_STATS)
    diag = diag_boss(gc, cls, mon["id"], log) if stage in os.environ.get("MXL_NMH_DIAG", "").split(",") else ""
    left = {"pots": pots, "drinks": 0, "placed": 0}

    def tick(c, mid):
        top, life = gc.rd("player", 7) or 0, gc.rd("player", 6) or 0
        if drink_due(life, top, left["pots"]):
            gc.g.press(str(1 + left["drinks"] % 4))  # the belt key of a column (D2R's default 1-4)
            left["pots"] -= 1
            left["drinks"] += 1
        u = gc.parse_moveto(gc.H("moveto %d" % mid)[1])
        p = gc.hstate()["player"]
        far = u is not None and max(abs(p.get("x", 0) - u["x"]), abs(p.get("y", 0) - u["y"])) > 7
        left["far"] = left.get("far", 0) + 1 if far else 0
        if left["far"] >= FAR_TICKS and left["placed"] < PLACE_MAX and reach_help(gc, mid, log):
            left["placed"] += 1
            left["far"] = 0

    def fight_one(mid):
        left["far"] = 0
        return fight(gc, mid, ATTACK, FIGHT_S[diff], log, on_tick=lambda c: tick(c, mid))
    t_start = time.time()
    killed, deaths, secs, c = fight_one(mon["id"])
    while not killed and 0 < deaths <= gc.ACTS_BOSS_RETRIES:
        kill_gear(gc, level, diff, log)
        left["pots"] += belt_potions(gc, log)
        gc.goto(area)
        mon2 = gc.acts_find(cls, log)
        if not mon2:
            break
        k2, d2, s2, c2 = fight_one(mon2["id"])
        killed, deaths, secs = k2, deaths + d2, secs + s2
        merge_counts(c, c2)
        if not d2:
            break
    wall = int(time.time() - t_start)
    time.sleep(4)
    q1 = gc.quest_bits(quest)
    m, _w = gc.merc_info()
    drop_note, drop_shots = drops_check(gc, difficulty, stage, log) if killed else ("no drops (not killed)", [])
    note = ("%s; %s; %d potions picked up into the belt (click), belt keys pressed %d (Median potions heal over time and not at "
            "all under Duriel's aura: nightmare_no_regen); mercenary at the end %s; boss class %d life %d / %d at the start, "
            "states %s, stats %s; "
            "Blood Hatred: %s after %d s of fighting (%d s with the retries' walks), %d deaths; %s; travel help `place` next to "
            "the boss %d, at the boss's preset %s; cut scenes skipped (Esc held) %d; %s; quest %d bits %s -> %s; %s%s"
            % (merc, kill_gear_note(level, dmg, diff), pots, left["drinks"],
               m and "class %s life %s" % (m.get("class"), m.get("life")), cls, life0, top0, bstates, bstats,
               "killed it" if killed else "did not kill it", secs, wall, deaths, fight_note(c), left["placed"], placed_at, cut, path_word(c),
               quest, q0, q1, drop_note, seal_txt + walk_txt + ("; " + diag if diag else "")))
    if killed:
        gc.STATE.setdefault("acts_killed", set()).add(stage)
    done_before = q0[:1] == "1"  # the save edit already marked it done (Nmhbarb: Nightmare at progression 10)
    if done_before and q1 == q0:
        note += " (the quest was already done in the save: no bit to move)"
    gc.finish(name, killed and (q1 != q0 or done_before), note, mark, [shot0, gc.sh("nmh_kill_%s_%s_after" % (difficulty, stage))] + drop_shots, log)
    return killed


def merc_ready_any(gc):
    m, _w = gc.merc_info()
    return "mercenary %s" % ("class %s level %s" % (m.get("class"), m.get("level")) if m else "none")


def kill(gc):
    """nmhkill: MXL_NMH_KILL=<difficulty>:<stage>,... (default KILL_STAGES): andariel / duriel / mephisto / diablo / baal with the
    stronger build, travel12 / travel23 / travel45 (game_checks.acts_travel: the NPC menu line), travel34 (Mephisto's portal),
    ancients (the Arreat Summit altar, game_checks.acts_ancients). A travel step follows the boss that opens it in this run."""
    opener = {"travel12": "andariel", "travel23": "duriel", "travel34": "mephisto", "travel45": "diablo"}
    for difficulty, stage in kill_targets(os.environ.get("MXL_NMH_KILL", KILL_STAGES)):
        log, shots = [], []
        try:
            gc.guard()
            if not ensure(gc, difficulty, log, shots):
                gc.add("nmh %s %s" % (difficulty, stage), "BLOCKED", "not in %s: %s" % (difficulty, "; ".join(log)), shots, log)
                continue
            gc.clean_start_state("nmh kill " + stage)
            level = gc.hstate()["player"].get("level") or LEVEL[difficulty]
            if stage in opener:
                if opener[stage] not in gc.STATE.get("acts_killed", set()):
                    gc.add("nmh %s: %s" % (difficulty, stage), "BLOCKED", "%s was not killed in this run" % opener[stage].title())
                    continue
                gc.acts_portal_a4() if stage == "travel34" else gc.acts_travel(stage)
                gc.skip_cinematic()
                continue
            if stage == "ancients":  # the acts lane's altar, fights with Attack and the kill gear
                with_kill_gear(gc, level, DIFFS[difficulty], log, gc.acts_ancients)
                continue
            if stage == "andariel":
                gc.goto(1)
                wv = gc.acts_menu(WARRIV)  # Warriv's lines before the kill: the travel line must be new afterwards
                gc.close_menu()
                if wv:
                    gc.STATE.setdefault("menus", {})[WARRIV] = wv
            gc.STATE.setdefault("acts_killed", set()).discard(stage)
            step_kill(gc, difficulty, stage, level, log)
        except Exception as e:
            gc.add("nmh %s %s" % (difficulty, stage), "BLOCKED", "script error: %r" % (e,))
            if gc.WD.abort:
                break
