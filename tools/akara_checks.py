"""Lane akararespec: Akara's "Reset Skills and Stats" without the Den of Evil limit up to level 100 (check `akararespec` of
tools/game_checks.py; plugin part `akararespec`, plugin/src/akara_respec.cpp).

D2R 93847 shows the line (string 0x2ba0) when the client's quest 41 bit 0 is clear and bit 1 set (the Den of Evil reward), and
its packet 0x39 handler respecs only with the server's quest 41 bit 1, which it then spends (bit 0 set, bit 1 cleared). The part
gives a character of level 1-100 the line and the respec every time and leaves the bits alone; above 100 D2R decides.

SET-UP (named in the note): a NEW lane character (MXL_CHAR, never used before: the run raises it past level 100) is raised to
level 30 by the game's own experience award; points are spent the way the character screen and the skill tree spend them
(packets 0x3a / 0x3b); the respec is the packet Akara's Yes sends (0x39 with Akara's unit id: D2R's Yes handler 0x1130d0 sends
exactly that). Nightmare / Hell: the save edit of tools/nmh_checks.py. The Den reward above 100 is set by harness (quest 41
bit 1, as the Den's completion sets it), then Save and Exit and Play so the client gets the record.
Judged per cycle: the line in Akara's menu, then all points back (unspent stat points, Strength and skill points equal to the
values before any point was spent: no point lost, none doubled), and quest 41's bits as they were. Above level 100 (lane
akarahide, owner 2026-11-05) the line shows only while the Den's respec is waiting: none without the reward or after it was
spent (D2R's builder alone would keep it in Hell once Den of Evil is done, 0x114c52; the part hides it), the line and D2R's
respec with it, in HD and legacy. The part's counter of menus with the line must not move above 100.
"""
import re
import time

import nmh_checks as nmh

AKARA = 148
RESPEC_LINE = 0x2ba0  # D2R's "Reset Skills and Stats" menu string
LOW_LEVEL = 30
HIGH_LEVEL = 101
STAT_POINTS, SKILL_POINTS, STRENGTH = 4, 5, 0
SPEND_STATS, SPEND_SKILLS = 3, 2


def respec_packet(unit_id):
    """`pkt` bytes of packet 0x39: u8 0x39, u32 NPC unit id (little-endian)."""
    return "39 " + " ".join("%02x" % ((unit_id >> (8 * i)) & 0xff) for i in range(4))


def skill_packet(skill):
    """Packet 0x3b (skill tree +, D2R 5 bytes): u8 0x3b, u16 skill, u16 0."""
    return "3b %02x %02x 00 00" % (skill & 0xff, skill >> 8)


def has_line(menu):
    """True when a parsed `menu list` (game_checks.parse_menu) holds the respec line."""
    return bool(menu) and any(s == RESPEC_LINE for _i, s, _h in menu["lines"])


def refunded(base, after):
    """base / after: (stat points, Strength, skill points). All points back, none extra."""
    return None not in after and tuple(after) == tuple(base)


def first_skill(rows, cls):
    """A class skill of skills.txt with level requirement 1 and no prerequisite: (id, name)."""
    for i, r in enumerate(rows):
        if r.get("charclass") == cls and str(r.get("reqlevel") or "") == "1" and not r.get("reqskill1"):
            return i, r.get("skill")
    return None, None


def points(gc):
    return gc.rd("player", STAT_POINTS), gc.rd("player", STRENGTH), gc.rd("player", SKILL_POINTS)


def akara_id(gc):
    near = [m for m in gc.hstate()["mons"] if m.get("class") == AKARA]
    near.sort(key=lambda m: m.get("dist", 99))
    return near[0].get("id") if near else None


def quest41(gc, log):
    ok, lines = gc.Hl("quest 41 dump", log)
    q = gc.parse_quest_dump(lines) if ok else None
    return q[1][:2] if q else None


def spend(gc, skill, log):
    """SPEND_STATS points into Strength, SPEND_SKILLS into `skill`; returns the points after."""
    for _ in range(SPEND_STATS):
        gc.Hl("pkt 3a 00 00 00 00", log)  # stat 0, count field 0 = one point
        time.sleep(0.4)
    for _ in range(SPEND_SKILLS):
        gc.Hl("pkt " + skill_packet(skill), log)
        time.sleep(0.4)
    return points(gc)


def menu(gc, log):
    lines = gc.npc_menu_near(AKARA)
    m = gc.parse_menu(lines) if lines else None
    log.append("akara menu: %s" % (m and [(i, hex(s)) for i, s, _h in m["lines"]]))
    return m


def part_line(gc):
    txt = gc.mxl_text() or ""
    return next((ln.strip() for ln in txt.splitlines() if "Akara's respec" in ln), "no akararespec line in `mxl2012`")


def shown_count(line):
    """Akara menus the part showed the line in, from its `mxl2012` line; None when not there."""
    m = re.search(r"Akara menus with the line (\d+)", line or "")
    return int(m.group(1)) if m else None


def hidden_count(line):
    """Akara menus the part built without the line above 100, from its `mxl2012` line; None when not there."""
    m = re.search(r"menus without the line above 100 (\d+)", line or "")
    return int(m.group(1)) if m else None


def cycle(gc, tag, base, skill, expect, rows, bad, log, shots, want_line=None):
    """One round at Akara: spend points, the menu (line wanted when `expect`, or as `want_line` says when given), the packet,
    then the points. Returns True when the respec happened. `menu list` reads the opener's lines, which still hold the line the
    builder drops (D2R's own "used" case too): with `want_line` given (above 100) the line counts as drawn when the part's
    hidden-line counter did not move for this menu; the screenshot shows the drawn menu."""
    q0 = quest41(gc, log)
    spent = spend(gc, skill, log)
    if spent[0] is None or spent[0] != base[0] - SPEND_STATS or spent[2] != base[2] - SPEND_SKILLS:
        bad.append("%s: points not spent as asked (%s -> %s)" % (tag, base, spent))
    hidden0 = hidden_count(part_line(gc))
    m = menu(gc, log)
    shots.append(gc.sh("akara_%s_menu" % tag))
    after_menu = part_line(gc)
    log.append("%s: %s" % (tag, after_menu))
    if want_line is None:
        line = has_line(m)
    else:
        hidden1 = hidden_count(after_menu)
        line = hidden0 is not None and hidden1 == hidden0
        if hidden0 is None or hidden1 is None:
            bad.append("%s: no hidden-line counter in `mxl2012`" % tag)
    gc.close_menu()
    aid = akara_id(gc)
    if aid is None:
        bad.append("%s: Akara not found next to the character" % tag)
        return False
    gc.Hl("pkt " + respec_packet(aid), log)
    time.sleep(1.0)
    after = points(gc)
    q1 = quest41(gc, log)
    done = refunded(base, after)
    rows.append("%s: line %s, respec %s (stat points / Strength / skill points %s -> spent %s -> %s; quest 41 bits 0-1 %s -> %s)" % (
        tag, "yes" if line else "no", "yes" if done else "no", base, spent, after, q0, q1))
    if want_line is None:
        want_line = True if expect else None
    if want_line is not None and line != want_line:
        bad.append("%s: %s" % (tag, "no respec line in Akara's menu" if want_line else "the respec line shows without a respec waiting"))
    if expect:
        if not done:
            bad.append("%s: points not given back exactly (%s, want %s)" % (tag, after, base))
    return done


def restore_spent(gc, base, skill, log):
    """After a refused respec the spent points stay spent: put the base back by harness for the next round."""
    gc.Hl("setskill %d 0" % skill, log)
    gc.setstat("player", STAT_POINTS, base[0])
    gc.setstat("player", STRENGTH, base[1])
    gc.setstat("player", SKILL_POINTS, base[2])


def level_up(gc, level, log):
    """The game's own experience award up to exactly `level`: the experience left to its start (experience.txt), in awards of at
    most 2e9."""
    lvl = gc.hstate()["player"].get("level", 0)
    for _ in range(8):
        need = gc.exp_start(level) - (gc.rd("player", 13) or 0)
        if lvl >= level or need <= 0:
            break
        lvl = gc.parse_xp(gc.Hl("xp %d" % min(need, 2000000000), log)[1]).get("level", lvl)
    return lvl


def intro(gc, tag, log, shots):
    """The first talk to Akara in a difficulty plays her Den of Evil speech instead of the menu (the harness's `menu list` then
    reads the menu lines left from before): talk once, past the speech, before the rounds."""
    menu(gc, log)
    shots.append(gc.sh("akara_%s_intro" % tag))
    gc.close_menu()


def low_rounds(gc, diff, skill, rows, bad, log, shots, graphics):
    gc.goto(1)
    if not gc.set_graphics(graphics):
        bad.append("%s: graphics %s not set" % (diff, graphics))
    intro(gc, diff, log, shots)
    base = points(gc)
    for n in range(1, 4):
        cycle(gc, "%s%d_%s" % (diff, n, graphics), base, skill, True, rows, bad, log, shots)


def run(gc):
    mark = gc.engine_mark()
    log, rows, bad, shots = [], [], [], []
    if not gc.need_game():
        return gc.add("akararespec", "BLOCKED", "not in a game")
    p = gc.hstate()["player"]
    if (p.get("level") or 0) > LOW_LEVEL or gc.rd("player", 13):
        return gc.add("akararespec", "BLOCKED", "the character is not new (level %s): run with a new MXL_CHAR" % p.get("level"))
    cls = {0: "ama", 1: "sor", 2: "nec", 3: "pal", 4: "bar", 5: "dru", 6: "ass"}.get(p.get("class"))
    skill, sname = first_skill(gc.table("skills"), cls)
    if skill is None:
        return gc.add("akararespec", "BLOCKED", "no level-1 skill of class %s" % cls)
    lvl = level_up(gc, LOW_LEVEL, log)
    rows.append("level %s (experience award), skill %d %s" % (lvl, skill, sname))
    try:
        low_rounds(gc, "normal", skill, rows, bad, log, shots, "hd")
        if gc.set_graphics("legacy"):
            cycle(gc, "normal4_legacy", points(gc), skill, True, rows, bad, log, shots)
        else:
            bad.append("legacy graphics not set")
        gc.goto(1)
        if not nmh.closed_edit_and_enter(gc, nmh.unlock_edit("hell"), "nightmare", log, shots):
            bad.append("Nightmare not entered")
        else:
            low_rounds(gc, "nightmare", skill, rows, bad, log, shots, "legacy")
        if not nmh.ensure(gc, "hell", log, shots):
            bad.append("Hell not entered")
        else:
            low_rounds(gc, "hell", skill, rows, bad, log, shots, "hd")
            lvl = level_up(gc, HIGH_LEVEL, log)
            rows.append("level %s (experience award)" % lvl)
            if lvl < HIGH_LEVEL:
                bad.append("level %d not reached (%s)" % (HIGH_LEVEL, lvl))
            gc.goto(1)
            base = points(gc)
            shown0 = shown_count(part_line(gc))
            for graphics in ("hd", "legacy"):  # D2R alone keeps the line here (Hell, Den done, 0x114c52): the part hides it
                if not gc.set_graphics(graphics):
                    bad.append("level %s: graphics %s not set" % (lvl, graphics))
                if cycle(gc, "hell_l%d_noden_%s" % (lvl, graphics), base, skill, False, rows, bad, log, shots, want_line=False):
                    bad.append("level %s without the Den reward: Akara respecced" % lvl)
                restore_spent(gc, base, skill, log)
            if shown_count(part_line(gc)) != shown0:
                bad.append("level %s without the Den reward: the part showed the line" % lvl)
            gc.set_graphics("hd")
            gc.Hl("quest 41 1 set", log)  # the Den of Evil's reward, as its completion sets it
            gc.Hl("quest 41 0 clear", log)
            if not (gc.rc2_save_exit() and nmh.enter(gc, "hell", log, shots)):
                bad.append("Hell not entered again after the Den reward")
            else:
                gc.goto(1)
                intro(gc, "hell_l%d_den" % lvl, log, shots)
                base = points(gc)
                shown0 = shown_count(part_line(gc))
                if not cycle(gc, "hell_l%d_den1_hd" % lvl, base, skill, True, rows, bad, log, shots, want_line=True):
                    bad.append("level %s with the Den reward: no respec" % lvl)
                if quest41(gc, log) != "10":
                    bad.append("level %s: the Den reward was not spent (quest 41 bits 0-1 %s, want 10)" % (lvl, quest41(gc, log)))
                for graphics in ("legacy", "hd"):
                    if not gc.set_graphics(graphics):
                        bad.append("level %s: graphics %s not set" % (lvl, graphics))
                    if cycle(gc, "hell_l%d_den2_%s" % (lvl, graphics), base, skill, False, rows, bad, log, shots, want_line=False):
                        bad.append("level %s: a second respec after the Den's one" % lvl)
                    restore_spent(gc, base, skill, log)
                if shown_count(part_line(gc)) != shown0:
                    bad.append("level %s: the part showed the line above 100" % lvl)
    finally:
        gc.close_menu()
    rows.append(part_line(gc))
    gc.finish("akararespec", not bad, "SET-UP: a new character, experience award to %d then %d, points spent by packets 0x3a / 0x3b, the "
              "respec by Akara's packet 0x39, Nightmare / Hell by save edit, the Den reward above 100 by harness. " % (LOW_LEVEL, HIGH_LEVEL)
              + "; ".join(rows) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log)
