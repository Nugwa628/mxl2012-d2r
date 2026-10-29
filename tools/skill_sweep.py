#!/usr/bin/env python
"""Skill sweep: every class skill of Median XL 2012 cast in the game, one fresh character per class (docs/skill-sweep.md).

    MXL_RUN=<lane> MXL_SLOT=2 py -3 tools/skill_sweep.py run [--out DIR] [--classes ama,sor,...] [--level N] [--fresh] [--only ID,..] [--redo ID,..]
    py -3 tools/skill_sweep.py report --out DIR [--md docs/skill-sweep.md]

`run` needs the slot lock (`game_slots.py lock N <lane>`), the built mod installed in that slot and game_ctl's background input
(the default; never MXL_INPUT=sendinput). Per class it plays a character `Sweep<Class>` (created when missing; `--fresh` deletes the
slot's old Sweep characters first), raises the character level stat to 120 (with its experience), mana to MANA (5000) and life to
LIFE_MAX (about a level-120 character's; the life is refilled to it before each skill, never above: no god mode), learns every
class skill (prerequisites first) to `--level` and goes to the Blood Moor. Per skill, on each button skills.txt allows (leftskill /
rightskill), the player path only (lane triage: the server-side `cast` reaches no client function):
  - Attack (0) is put on both buttons first, so a click that does not run the skill under test runs Attack, whose signs (melee
    damage, mode A1 / A2) the verdict does not count (lane triage: a click runs the client's previous skill when the client does
    not follow the selection, e.g. an oskill);
  - `skill left|right <id>`: selectable or not (the game's answer names the skill now on the button);
  - `watch cltdo <n>` on the skill's client do slot (skills.txt cltdofunc, else cltprgfunc1, e.g. Batstrike's 25): counts the
    client's calls of that slot and keeps the last skill id, so a call with the skill's id proves the client ran this skill;
  - a vanilla zombie (class 5, life raised so it survives: the target, not the player) is spawned 4 sub-tiles east, and a
    background click with that button on it casts the skill the way a player does (a second click when the first showed
    nothing the skill did, e.g. while an animation ran); a skill that consumes corpses (srvdofunc 82: Pagan Rites) gets a
    zombie killed next to it first, a TargetCorpse skill is clicked at the spot where its zombie died.
Signals of a click: `cltdo` (the watched slot called with the skill's id), mana (spent: Attack costs none), missile (one of the
skill's own missiles, skills.txt srv/cltmissile* and their sub, hit-sub and explosion missiles, two levels deep), other missile
(any other, but not a weapon's own missiletype, which Attack fires), state (a new state on the player), summon (new monsters),
mode (the player in a skill mode other than Attack's A1 / A2 right after), warp (the player 2+ sub-tiles away 0.3 s after the click without
walking: a teleport), corpse (a new state on the corpse laid for a corpse-consuming skill, e.g. redemption) and damage / target gone (counted only with another
signal: Attack does damage too). An aura (skills.txt aura 1) counts when its state comes on with the selection.
Then once without a target, for the record only: the harness `cast <id> <x> <y>` at a point 5 sub-tiles west (server side, prints
the game's usability code; never makes a verdict ok, only explains a blocked one). A skill with skills.txt item type needs (itypea /
itypeb) first gets gear (`gear_for`):
strength and dexterity 1000, the old weapon and off-hand taken off (`unequip`), the lowest-level weapons.txt base of a wanted type
the class may use worn on the right hand (harness `equip`; throwing weapons and quivers with a full stack), the bow's or crossbow's
quiver or the itypeb weapon on the left hand; a `restrict` 2 skill also gets its form first (the class skill whose aurastate /
passivestate is State1-3 is cast at the target, e.g. Trap Rat Form for Quill Storm; a short state that is not a shapeshift, e.g.
the paladin's Evocation from Arcane Strike, is taken again right before each click, `reform`; set-up casts are the harness' server
`cast`, like the pet for TargetPet rows: they set the stage, the verdict comes from the clicks). Engine asserts come from the harness'
`asserttrace` hook (every call, with the message and file), crashes from the slot's process list and crash folder, hangs from a
harness command that no longer answers; a crash or hang restarts the game and the sweep goes on with the next skill. Passives (no
button allowed) are only selected for the record.

Results go to <out>/sweep.json (resumable: done skills are skipped), the D2RLoader / plugin logs and crash files next to it.
`report` writes the markdown table (docs/skill-sweep.md). Evidence stays outside git (mxl2012-runs/skills/).
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.dirname(ROOT)), "mxl2012-runs", "skillsweep", "sweep")

# class id (`h state` class) -> skills.txt charclass, hero select key, character name (letters only: D2R drops digits)
CLASSES = [(0, "ama", "amazon", "SweepAmazon"), (1, "sor", "sorceress", "SweepSorceress"), (2, "nec", "necromancer", "SweepNecro"),
           (3, "pal", "paladin", "SweepPaladin"), (4, "bar", "barbarian", "SweepBarbarian"), (5, "dru", "druid", "SweepDruid"),
           (6, "ass", "assassin", "SweepAssassin")]  # Warlock (war) left out: the slot's account has no Reign of the Warlock
TARGET_CLASS = 5  # zombie1: a vanilla monster at its vanilla id
STAT_STR, STAT_DEX, STAT_QUANTITY = 0, 2, 70  # itemstatcost ids (vanilla rows): requirements for the gear, stack size
LEARN_STATS = (504, 505)  # learn_ennead, learn_blackroad (itemstatcost ids of the build)
EXP_120 = 7022000  # experience.txt row 119: the experience of character level 120
LIFE = 30000  # whole points: the target's life
MANA = 5000  # whole points: the character's mana (regeneration is a share of the maximum: 30000 refilled a small cost before the look)
LIFE_MAX = 3000  # whole points: the character's life, about a level-120 character's (vitality from its stat points), never raised above
CORPSE_DO = {"82"}  # srvdofunc of skills that consume corpses around the caster (Redemption, Pagan Rites): a corpse is laid next to the target
SKILL_MODES = set(range(7, 17)) | {18}  # A1 A2 BL SC TH KK S1-S4 DD SQ (plrmode.txt): the player is using a skill
ATTACK_MODES = {7, 8}  # A1 A2: what Attack (0) shows, so not a sign of the skill under test
MOVE_MODES = {2, 3}  # WL RN: Attack walking to its target
WARP_DIST = 2  # sub-tiles the player moved by the quick look without walking: a teleport (srvdofunc 27, e.g. Spirit Walk)
CLT_BOUND = 130  # D2R's client do table bound (watch cltdo)


def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, p)


# ---------------------------------------------------------------- data (the built tables of work/mod)

def class_skills(gc, charclass):
    """The class's skills.txt rows (skill tree order is irrelevant here: id order)."""
    out = []
    for r in gc.table("skills"):
        if r.get("charclass") == charclass and re.fullmatch(r"\d+", r.get("*Id", "")):
            out.append(r)
    return sorted(out, key=lambda r: int(r["*Id"]))


def buttons(row):
    """The buttons skills.txt allows: leftskill 1 -> left, rightskill 1 -> right."""
    return [b for b, col in (("left", "leftskill"), ("right", "rightskill")) if row.get(col) not in ("", "0", None)]


def transform_states(gc):
    return {int(r["*ID"]) for r in gc.table("states") if r.get("transform") == "1" and re.fullmatch(r"\d+", r.get("*ID", ""))}


# ---------------------------------------------------------------- game helpers

class Session:
    def __init__(self, gc, g, out, reenter_gear=False):
        self.gc, self.g, self.out = gc, g, out
        self.reenter_gear = reenter_gear
        self.transform = transform_states(gc)

    def alive(self):
        return bool(self.g.game_pids())

    def responsive(self):
        """The game thread still answers a server-side harness verb (a hang leaves the process alive but silent)."""
        for _ in range(2):
            ok, lines = self.g.hcmd("state", 20)
            if ok:
                return True
        return False

    def plain_missiles(self):
        if not hasattr(self, "_plain"):
            self._plain = weapon_missiles(self.gc.table("weapons"), self.gc.table("missiles"))
        return self._plain

    def asserts(self):
        ok, lines = self.g.hcmd("asserttrace count", 8)
        m = re.search(r"count (\d+)", " ".join(lines))
        return int(m.group(1)) if m else None

    def assert_lines(self, n):
        if n <= 0:
            return []
        ok, lines = self.g.hcmd("asserttrace show %d" % min(n, 32), 10)
        return [ln for ln in lines if ln.startswith("assert #")]

    def states(self, ref="player"):
        ok, lines = self.g.hcmd("states %s" % ref, 15)
        return {int(m.group(1)) for ln in lines for m in [re.match(r"server state (\d+):", ln)] if m}

    def start_and_enter(self, cls):
        """Game to the main menu, then the class's Sweep character (created when missing), in the Blood Moor, ready."""
        gc, g = self.gc, self.g
        if not gc.to_menu():
            raise RuntimeError("game did not reach the main menu")
        cid, _cc, hero, name = cls
        card = gc.card_of(name)
        self._worn = None
        ok = gc.create_character(hero, name) if card is None else gc.enter_game(card)
        if not ok or gc.hstate()["player"].get("class") != cid:
            raise RuntimeError("could not play %s" % name)
        return self.prepare()

    def switch(self, cls):
        cid, _cc, hero, name = cls
        self._worn = None
        if not self.gc.switch_character(name, hero, cid):
            raise RuntimeError("could not switch to %s" % name)
        return self.prepare()

    def prepare(self):
        gc, g = self.gc, self.g
        ok, lines = g.hcmd("asserttrace on", 8)
        if not ok:
            g.log("asserttrace not available: " + " | ".join(lines))
        self.tank()
        gc.goto(2)
        return gc.hstate()["player"].get("area") == 2

    def tank(self):
        """Life refilled (LIFE_MAX), mana raised, character level 120 with its experience (a kill re-reads the level from experience: with 0 the
        character falls back to level 1 and the game refuses skill points)."""
        for s, v in ((7, LIFE_MAX), (6, LIFE_MAX), (9, MANA), (8, MANA)):  # life: refilled to a level-120 value; mana raised
            self.gc.setstat("player", s, v << 8)
        self.gc.setstat("player", 13, EXP_120)
        self.gc.setstat("player", 12, 120)
        for s in LEARN_STATS:  # the Ennead / Black Road skills ask for these in skpoints (Median gives them by quest)
            self.gc.setstat("player", s, 1)

    def clear_monsters(self):
        for _ in range(25):
            ok, _l = self.g.hcmd("kill nearest", 8)
            if not ok:
                break

    def spawn_target(self):
        gc = self.gc
        p = gc.hstate()["player"]
        ok, lines = self.g.hcmd("spawn %d 1 %d %d" % (TARGET_CLASS, p.get("x", 0) + 4, p.get("y", 0)), 10)
        m = re.search(r"id=(\d+)", " ".join(lines))
        if not m:
            return None
        mid = int(m.group(1))
        for s in (7, 6):
            gc.setstat("mon:%d" % mid, s, LIFE << 8)
        return mid

    def ensure_learned(self, row, level):
        """The skill at `level`. Median's skill paths are exclusive: skpoints costs more than any pool while a rival named in the
        formula (`skill('<name>'.blvl)`) has points, so the rivals go to 0 first; prerequisites are learnt again (a rival may
        be one)."""
        gc = self.gc
        sid = int(row["*Id"])
        got = gc._setskill(sid, level)
        if got == level:
            return got
        ids = {r["skill"]: int(r["*Id"]) for r in gc.table("skills") if re.fullmatch(r"\d+", r.get("*Id", ""))}
        for name in re.findall(r"skill\('([^']+)'\.blvl\)", row.get("skpoints", "")):
            if name in ids and ids[name] != sid:
                gc._setskill(ids[name], 0)
        gc.learn(sid, 1)
        return gc._setskill(sid, level)

    def target_for(self, row):
        """The unit a targeted cast goes at: skills.txt TargetCorpse -> the zombie's corpse, TargetPet -> a pet of one of the class's
        own summon skills, else the live zombie. (unit id or None, kind)."""
        gc, g = self.gc, self.g
        if row.get("TargetCorpse") == "1":
            mid = self.spawn_target()
            self._corpse_at = None
            if mid is not None:
                mon = next((m for m in gc.hstate()["mons"] if m.get("id") == mid), None)
                self._corpse_at = (mon["mx"], mon["my"]) if mon and "mx" in mon else None  # `state` lists corpses without a spot
                g.hcmd("kill %d" % mid, 8)
            return mid, "corpse"
        if row.get("TargetPet") == "1":
            summon = next((r for r in class_skills(gc, row.get("charclass", "")) if r.get("summon") and r.get("TargetPet") != "1"
                           and r.get("TargetCorpse") != "1" and buttons(r)), None)
            if summon is None:
                return self.spawn_target(), "monster (the class has no summon skill for a pet)"
            self.ensure_learned(summon, 1)
            p = gc.hstate()["player"]
            g.hcmd("cast %s %d %d" % (summon["*Id"], p.get("x", 0) + 3, p.get("y", 0)), 10)
            time.sleep(1.5)
            pets = sorted((m for m in gc.hstate()["mons"] if m.get("class") != TARGET_CLASS), key=lambda m: m.get("dist", 99))
            if pets:
                return pets[0]["id"], "pet of %s %s" % (summon["*Id"], summon["skill"])
            return self.spawn_target(), "monster (no pet appeared after %s)" % summon["skill"]
        return self.spawn_target(), "monster"

    # -- gear for item type needs (harness `equip` / `unequip`)
    def _types(self):
        if not hasattr(self, "_itypes"):
            self._itypes = {r["Code"]: r for r in self.gc.table("itemtypes") if r.get("Code")}
        return self._itypes

    def ancestors(self, code):
        out, todo = set(), [code]
        while todo:
            c = todo.pop()
            if c and c not in out and c in self._types():
                out.add(c)
                todo += [self._types()[c].get("Equiv1", ""), self._types()[c].get("Equiv2", "")]
        return out

    def base_for(self, want, charclass, exclude=()):
        """(code, stack) of the lowest-level weapons.txt / misc.txt base whose type is (or is equivalent to) `want`, usable by the
        class (no class-only type of another class on its type chain), none of whose types is excluded."""
        best = None
        for table in ("weapons", "misc"):
            for r in self.gc.table(table):
                if not r.get("code") or not r.get("type"):
                    continue
                chain = self.ancestors(r["type"]) | (self.ancestors(r["type2"]) if r.get("type2") else set())
                if want not in chain or chain & set(exclude):
                    continue
                if any(self._types()[c].get("Class") not in ("", charclass) for c in chain):
                    continue
                lvl = int(r.get("levelreq") or 0) if (r.get("levelreq") or "0").lstrip("-").isdigit() else 999
                stack = int(r["maxstack"]) if r.get("stackable") == "1" and (r.get("maxstack") or "").isdigit() else 0
                key = (lvl, r["code"])
                if best is None or key < best[0]:
                    best = (key, r["code"], stack, chain)
        return (best[1], best[2], best[3]) if best else (None, 0, set())

    def equip(self, code, stack, loc, log):
        cmd = "equip %s %s%s" % (code, ("%d=%d " % (STAT_QUANTITY, stack)) if stack else "", loc)
        ok, lines = self.g.hcmd(cmd, 10)
        log.append("%s -> %s" % (cmd, lines[-1] if lines else "-"))
        return ok

    def gear_for(self, row, log):
        """Wear what the row's item types ask for and take on its form state (module docstring). Returns a short note."""
        gc, g = self.gc, self.g
        cc = row.get("charclass", "")
        want = [row[c] for c in ("itypea1", "itypea2", "itypea3") if row.get(c)]
        excl = [row[c] for c in ("etypea1", "etypea2") if row.get(c)]
        second = [row[c] for c in ("itypeb1", "itypeb2", "itypeb3") if row.get(c)]
        note = []
        key = (tuple(want), tuple(excl), tuple(second))
        if want and key == getattr(self, "_worn", None):  # already worn (and loaded by the client): not made again
            note.append(self._worn_note)
            want = []
        if want:
            for s_, v in ((STAT_STR, 1000), (STAT_DEX, 1000)):
                gc.setstat("player", s_, v)
            for loc in ("rhand", "lhand"):
                g.hcmd("unequip %s" % loc, 8)
            for w in want:
                code, stack, chain = self.base_for(w, cc, excl)
                if code is None:
                    continue
                if self.equip(code, stack, "rhand", log):
                    note.append("%s %s" % (w, code))
                    quiver = next((self._types()[c].get("Shoots") for c in chain if self._types()[c].get("Shoots")), "")
                    if quiver:
                        qcode, qstack, _qc = self.base_for(quiver, cc)
                        if qcode and self.equip(qcode, qstack, "lhand", log):
                            note.append("quiver %s" % qcode)
                    break
            else:
                note.append("no base of %s could be worn" % "/".join(want))
            if second and not any(n.startswith("quiver") for n in note):
                for w in second:
                    code, stack, _chain = self.base_for(w, cc, excl)
                    if code and self.equip(code, stack, "lhand", log):
                        note.append("left %s %s" % (w, code))
                        break
            # bug #391 (fixed: the harness `equip` sends D2R's equip update, kind 8): the client wears the gear at once.
            # --reenter-gear keeps the old workaround (Save and Exit + Play loads the gear and stats from the save on both sides)
            if self.reenter_gear:
                gc.leave_and_reenter()
                self.prepare()
                log.append("re-entered so the client loads the gear: %s" % "; ".join(note))
            else:
                log.append("gear worn: %s" % "; ".join(note))
            self._worn, self._worn_note = key, "; ".join(note)
        self._form = None
        if row.get("restrict") == "2":
            names = [row[c] for c in ("State1", "State2", "State3") if row.get(c)]
            ids = {r["state"]: int(r["*ID"]) for r in gc.table("states") if re.fullmatch(r"\d+", r.get("*ID", ""))}
            for name in names:
                giver = next((r for r in class_skills(gc, cc) if name in (r.get("aurastate"), r.get("passivestate"))), None)
                if giver is None or ids.get(name) in self.states():
                    continue
                self.ensure_learned(giver, 1)
                mid = self.spawn_target()
                ok, lines = g.hcmd("cast %s unit %d" % (giver["*Id"], mid) if mid is not None else "cast %s" % giver["*Id"], 10)
                time.sleep(1.5)
                on = ids.get(name) in self.states()
                log.append("form: cast %s %s -> %s, state %s %s" % (giver["*Id"], giver["skill"], lines[-1] if lines else "-", name,
                                                                    "on" if on else "NOT on"))
                note.append("form %s via %s %s" % (name, giver["*Id"], "on" if on else "not on"))
                if ids.get(name) not in self.transform:  # a short state (not a shapeshift): taken again before each cast
                    self._form = (giver, ids.get(name))
                self.clear_monsters()
        return "; ".join(note)

    def reform(self, mid, log):
        """Takes the non-shapeshift form state of the skill under test again when it ran out (gear_for)."""
        form = getattr(self, "_form", None)
        if not form or form[1] in self.states():
            return
        giver, sid = form
        ok, lines = self.g.hcmd("cast %s unit %d" % (giver["*Id"], mid) if mid is not None else "cast %s" % giver["*Id"], 10)
        time.sleep(1.0)
        log.append("reform: cast %s -> state %d %s" % (giver["*Id"], sid, "on" if sid in self.states() else "NOT on"))

    def unshift_if_needed(self):
        """A shapeshift state (states.txt transform) stays on and blocks later spells: Save and Exit + Play clears it."""
        on = self.states() & self.transform
        if on:
            self.g.log("transform state(s) %s on: Save and Exit + Play" % sorted(on))
            self.gc.leave_and_reenter()
            self.prepare()
        return sorted(on)


SKILL_MISSILE_COLS = ("srvmissile", "srvmissilea", "srvmissileb", "srvmissilec", "cltmissile", "cltmissilea", "cltmissileb",
                      "cltmissilec", "cltmissiled")
SUB_MISSILE_COLS = ("ExplosionMissile", "SubMissile1", "SubMissile2", "SubMissile3", "HitSubMissile1", "HitSubMissile2",
                    "HitSubMissile3", "HitSubMissile4", "CltSubMissile1", "CltSubMissile2", "CltSubMissile3", "CltHitSubMissile1",
                    "CltHitSubMissile2", "CltHitSubMissile3", "CltHitSubMissile4")


def own_missiles(row, missiles, depth=2):
    """{missile id} of a skills.txt row: its srv/clt missile columns and, `depth` levels deep, their explosion, sub and hit-sub
    missiles (missiles: the missiles.txt rows)."""
    by_name = {r["Missile"]: r for r in missiles if r.get("Missile") and re.fullmatch(r"\d+", r.get("*ID", ""))}
    todo, seen = {row[c] for c in SKILL_MISSILE_COLS if row.get(c)}, set()
    for _ in range(depth + 1):
        nxt = set()
        for n in todo - seen:
            seen.add(n)
            r = by_name.get(n)
            if r:
                nxt |= {r[c] for c in SUB_MISSILE_COLS if r.get(c)}
        todo = nxt
    return {int(by_name[n]["*ID"]) for n in seen if n in by_name}


def weapon_missiles(weapons, missiles):
    """{missile id} the weapons.txt bases fire with a plain attack (missiletype: arrows, bolts, thrown weapons)."""
    ids = {int(r["*ID"]) for r in missiles if re.fullmatch(r"\d+", r.get("*ID", ""))}
    return {int(r["missiletype"]) for r in weapons if re.fullmatch(r"\d+", r.get("missiletype") or "")} & ids


def watch_slot(row):
    """The client do slot whose calls prove the client ran the skill: cltdofunc, else cltprgfunc1 (progressive skills, e.g.
    Batstrike's 25, index the same table); None when the row has neither (or one beyond the bound)."""
    for c in ("cltdofunc", "cltprgfunc1"):
        v = row.get(c) or ""
        if re.fullmatch(r"\d+", v) and 0 < int(v) < CLT_BOUND:
            return int(v)
    return None


def parse_watch(lines):
    """(calls, non-zero returns, last skill id) of the harness `watch` answer, None for each when it is missing."""
    for ln in lines:
        m = re.search(r"calls=(\d+) nonzero=(\d+) last=(-?\d+)", ln)
        if m:
            return tuple(int(v) for v in m.groups())
    return None, None, None


def parse_selected(lines, button):
    """The skill id the game's `skill left|right` answer names on that button (`skill left=<id> right=<id>`), else None."""
    m = re.search(r"\b%s=(-?\d+)" % button, " ".join(lines))
    return int(m.group(1)) if m else None


def signals(before, after, mid, own=frozenset(), plain=frozenset()):
    """What changed between two snapshots: the signs that a cast happened. `own`: the skill's missiles; `plain`: missiles a
    plain attack fires (not counted)."""
    sig = []
    if after["mana"] is not None and before["mana"] is not None and after["mana"] < before["mana"]:
        sig.append("mana")
    mis = set(after["missiles"]) - set(plain)
    if mis & set(own):
        sig.append("missile")
    elif mis:
        sig.append("other missile")
    if mid is not None and before["target"] is not None and (after["target"] is None or after["target"] < before["target"]):
        sig.append("damage" if after["target"] is not None else "target gone")
    if after["states"] - before["states"]:
        sig.append("state")
    if after["mode"] in SKILL_MODES - ATTACK_MODES:
        sig.append("mode")
    if after.get("mons", set()) - before.get("mons", set()):
        sig.append("summon")
    return sig


# the signs that tie a click to the skill under test (Attack, primed on both buttons, shows only damage and mode A1 / A2)
OWN_SIGNALS = ("cltdo", "mana", "missile", "other missile", "state", "summon", "mode", "warp", "corpse")


def proven(sig):
    return any(s in OWN_SIGNALS for s in sig)


def snapshot(sess, mid, missiles=False):
    gc = sess.gc
    st = gc.hstate()
    p = st["player"]
    mana = None
    m = re.search(r"mana=(-?\d+)", " ".join(st["lines"]))
    if m:
        mana = int(m.group(1))
    target = None
    if mid is not None:
        mon = next((x for x in st["mons"] if x.get("id") == mid), None)
        target = mon.get("life") if mon else None
    seen = {}
    if missiles:
        ok, ml = sess.g.hcmd("missiles", 10)
        seen = gc.missiles_seen(ml)
    return {"mana": mana, "target": target, "mode": p.get("mode"), "states": sess.states(), "missiles": seen,
            "mons": {x.get("id") for x in st["mons"]}}


def quick_look(sess):
    """(mode, x, y, mana) of the player a moment after a click: a skill's animation is over (and a small mana cost
    regenerated) by the time of the full snapshot."""
    st = sess.gc.hstate()
    p = st["player"]
    m = re.search(r"mana=(-?\d+)", " ".join(st["lines"]))
    return p.get("mode"), p.get("x"), p.get("y"), int(m.group(1)) if m else None


def warped(start, look):
    """The player stands WARP_DIST or more sub-tiles from `start` (x, y) at the quick look (mode, x, y) without walking or
    attacking: a teleport (Attack walks to its target, mode WL / RN, or is already hitting, A1 / A2)."""
    mode, x, y = look[:3]
    if None in (x, y) or None in start or mode in MOVE_MODES | ATTACK_MODES:
        return False
    return max(abs(x - start[0]), abs(y - start[1])) >= WARP_DIST


def screen_spot(player, spot):
    """(fx, fy) of a sub-tile spot on the 1600 x 900 HD client, as game_checks.click_unit measures it (the player at (800, 405))."""
    dx, dy = spot[0] - player["x"], spot[1] - player["y"]
    return (800 + (dx - dy) * 27) / 1600, (405 + (dx + dy) * 13.5) / 900


def click_at(sess, spot, button):
    """A background click on a spot (a corpse: `state` lists it without one, so the spot is where its zombie died)."""
    if spot is None:
        return False
    fx, fy = screen_spot(sess.gc.hstate()["player"], spot)
    sess.g.click(fx, fy, button=button)
    return True


def click_once(sess, row, b, slot, own, plain, log):
    """One background click with button `b` at a fresh target; the signals (module docstring) and the watched slot's numbers."""
    gc, g = sess.gc, sess.g
    sid = int(row["*Id"])
    sess.tank()
    sess.clear_monsters()
    if row.get("srvdofunc") in CORPSE_DO:  # a corpse to consume: one more zombie, killed (cleared monsters leave none)
        extra = sess.spawn_target()
        if extra is not None:
            g.hcmd("kill %d" % extra, 8)
    else:
        extra = None
    mid, kind = sess.target_for(row)
    time.sleep(0.8)  # the client shows the new monster (hover needs it on screen)
    sess.reform(mid, log)
    if slot is not None:
        g.hcmd("watch cltdo %d" % slot, 8)
    g.hcmd("missiles reset", 8)
    before = snapshot(sess, mid)
    p0 = gc.hstate()["player"]
    start = (p0.get("x"), p0.get("y"))
    corpse0 = sess.states("mon:%d" % extra) if extra is not None else set()
    if kind == "corpse":
        clicked = click_at(sess, getattr(sess, "_corpse_at", None), b)
    else:
        clicked = gc.click_unit(mid, button=b) if mid is not None else False
    time.sleep(0.3)
    look = quick_look(sess) if sess.alive() else (None, None, None, None)
    mode = look[0]
    time.sleep(1.2)
    t = {"clicked": clicked, "signals": [], "kind": kind}
    if not sess.alive():
        t["crash"] = True
        return t
    after = snapshot(sess, mid, missiles=True)
    sig = signals(before, after, mid, own, plain)
    if mode in SKILL_MODES - ATTACK_MODES and "mode" not in sig:
        sig.append("mode")
    if warped(start, look):
        sig.append("warp")
    if "mana" not in sig and None not in (look[3], before["mana"]) and look[3] < before["mana"]:
        sig.append("mana")
    if extra is not None and sess.states("mon:%d" % extra) - corpse0:
        sig.append("corpse")
    if slot is not None:
        ok, wl = g.hcmd("watch", 8)
        calls, made, last = parse_watch(wl)
        t["watch"] = {"slot": slot, "calls": calls, "made": made, "last": last}
        if calls and last == sid:
            sig.insert(0, "cltdo")
    t["signals"] = sig
    t["missiles"] = {str(k): v for k, v in sorted(after["missiles"].items())}
    return t


def try_skill(sess, row, level, log):
    """One skill: Attack on both buttons, then per allowed button the skill selected and clicked at the target (twice when the
    first click shows nothing of the skill); then the server-side usability check at a point without a target (record only)."""
    gc, g = sess.gc, sess.g
    sid = int(row["*Id"])
    res = {"id": sid, "name": row["skill"], "buttons": buttons(row), "itypes": itypes(row), "select": {}, "target": {}, "notarget": {},
           "asserts": [], "crash": False, "notes": []}
    a0 = sess.asserts()
    sess.tank()
    res["level"] = sess.ensure_learned(row, level)
    if res["level"] != level:
        res["notes"].append("base level %s of %d" % (res["level"], level))
    if res["itypes"]:
        res["gear"] = sess.gear_for(row, log)
        if res["gear"]:
            res["notes"].append("gear: " + res["gear"])
    slot = watch_slot(row)
    res["watch_slot"] = slot
    own = own_missiles(row, gc.table("missiles"))
    plain = sess.plain_missiles()
    aura = row.get("aura") == "1"
    for b in (("left", "right") if not res["buttons"] else res["buttons"]):
        if res["buttons"]:
            g.hcmd("skill %s 0" % b, 10)  # Attack first: a click that ignores the selection shows Attack's signs only
        pre = sess.states() if aura else set()
        ok, lines = g.hcmd("skill %s %d" % (b, sid), 10)
        on = parse_selected(lines, b)
        res["select"][b] = "ok" if ok and on in (None, sid) else ("refused" if not ok else "button shows %s" % on)
        log.append("skill %s %d -> %s" % (b, sid, lines[-1] if lines else "-"))
        if not res["buttons"] or not ok:
            continue
        if aura:  # an aura (skills.txt aura 1, the Stances) works while it sits on the button: its state comes on
            time.sleep(1.5)
            res.setdefault("aura_states", {})[b] = sorted(sess.states() - pre)
        t = click_once(sess, row, b, slot, own, plain, log)
        if not t.get("crash") and not proven(t["signals"]):
            t2 = click_once(sess, row, b, slot, own, plain, log)
            t2["second"] = True
            t2["first"] = t["signals"]
            t = t2
        res["target"][b] = t
        log.append("target %s: %s" % (b, t))
        if t.get("crash"):
            res["crash"] = True
            break
    if slot is not None and not res["crash"]:
        g.hcmd("watch off", 8)
    if res["buttons"] and not res["crash"]:
        sess.tank()
        if getattr(sess, "_form", None):  # the form skill needs a target: one more zombie, gone before the cast without target
            fm = sess.spawn_target()
            sess.reform(fm, log)
            if fm is not None:
                g.hcmd("kill %d" % fm, 8)
        sess.clear_monsters()
        p = gc.hstate()["player"]
        ok, lines = g.hcmd("cast %d %d %d" % (sid, p.get("x", 0) - 5, p.get("y", 0)), 10)
        text = " ".join(lines)
        usable = re.search(r"usable=(-?\d+)", text)
        code = re.search(r"code (-?\d+)", text)
        time.sleep(1.5)
        if not sess.alive():
            res["crash"] = True
            res["notes"].append("crashed on the server-side usability cast")
        else:
            res["notarget"] = {"usable": int(usable.group(1)) if usable else None, "code": int(code.group(1)) if code else None,
                               "answer": text[:200]}
        log.append("notarget: %s" % res["notarget"])
    if not res["crash"]:
        a1 = sess.asserts()
        if a0 is not None and a1 is not None and a1 > a0:
            res["asserts"] = [re.sub(r"^assert #\d+: ", "", ln) for ln in sess.assert_lines(a1 - a0)]
        try:
            shifted = sess.unshift_if_needed()
            if shifted:
                res["notes"].append("left shapeshift state(s) %s (re-entered)" % shifted)
        except Exception as e:  # noqa: BLE001
            res["notes"].append("re-enter after shapeshift failed: %r" % (e,))
    return res


ITYPE_COLS = ("itypea1", "itypea2", "itypea3", "etypea1", "etypea2", "itypeb1", "itypeb2", "itypeb3")


def itypes(row):
    """What skills.txt asks of the caster: weapon / item types (itypea / etypea / itypeb; a fresh character's starting weapon rarely
    fits) and, for `restrict` 2, the form state (State1-3) the skill is only usable in (the druid's form skills)."""
    need = [row[c] for c in ITYPE_COLS if row.get(c)]
    if row.get("restrict") == "2":
        need += ["state " + row[c] for c in ("State1", "State2", "State3") if row.get(c)]
    return need


def verdict(r):
    """ok / assert / broken / blocked / unproven / passive (docs/skill-sweep.md's legend): ok needs a click whose signs tie it to the
    skill (OWN_SIGNALS) or an aura's state; the server-side usability check never makes a skill ok."""
    if r.get("crash") or r.get("hang"):
        return "broken"
    if not r.get("buttons"):
        return "passive" if not r.get("asserts") else "assert"
    if r.get("asserts"):
        return "assert"
    if any(v != "ok" for v in r.get("select", {}).values()):
        return "broken"
    if any(proven((t or {}).get("signals") or []) for t in r.get("target", {}).values()) or any(r.get("aura_states", {}).values()):
        return "ok"
    usable = (r.get("notarget") or {}).get("usable")
    if usable == 5 or (usable in (2, 4) and r.get("itypes")):  # refused for the weapon / form the test character lacks
        return "blocked"
    if any((t or {}).get("signals") for t in r.get("target", {}).values()):
        return "unproven"  # only damage: Attack, primed on the buttons, does that too
    return "broken"


# ---------------------------------------------------------------- run

def run(args):
    sys.path.insert(0, TOOLS)
    import game_checks as gc  # noqa: E402  (game_ctl reads MXL_SLOT / MXL_RUN at import)
    g = gc.g
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    g.current_run = lambda create=False: out
    data_p = os.path.join(out, "sweep.json")
    data = load_json(data_p, {"started": datetime.datetime.now().isoformat(timespec="seconds"), "classes": {}})
    if not gc.lock():
        print("slot lock not available")
        return 2
    gc.WD = gc.Watchdog()
    gc.WD.start()
    want = [c for c in CLASSES if not args.classes or c[1] in args.classes.split(",")]
    if args.fresh:
        for _cid, cc, _hero, name in want:
            if cc in data["classes"]:  # a resumed sweep keeps the character it started with
                continue
            for f in glob.glob(os.path.join(g.SAVES, name + ".*")):
                os.remove(f)
                g.log("deleted old sweep character file %s" % f)
    marks = {"loader": g._size(g.LOADER_LOG), "mxl": g._size(g.MXL_LOG),
             "crashes": set(os.listdir(g.CRASH_DIR)) if os.path.isdir(g.CRASH_DIR) else set()}
    sess = Session(gc, g, out, reenter_gear=args.reenter_gear)
    started = False
    try:
        for cls in want:
            cid, cc, hero, name = cls
            rec = data["classes"].setdefault(cc, {"char": name, "skills": {}})
            rows = class_skills(gc, cc)
            redo = set(args.redo.split(",")) if args.redo else set()
            todo = [r for r in rows if (r["*Id"] not in rec["skills"] or r["*Id"] in redo) and
                    (not args.only or r["*Id"] in args.only.split(",")) and (not redo or r["*Id"] in redo)]
            if not todo:
                continue
            restarts = 0
            hung = False
            while todo:
                gc.guard()
                if not started or hung or not sess.alive():
                    hung = False
                    if started:
                        g.stop()
                        time.sleep(3)
                    sess.start_and_enter(cls)
                    started = True
                    rec["learned"] = learn_all(gc, rows, args.level)
                elif gc.hstate()["player"].get("class") != cid:
                    sess.switch(cls)
                    rec["learned"] = learn_all(gc, rows, args.level)
                row = todo.pop(0)
                log = []
                try:
                    r = try_skill(sess, row, args.level, log)
                except Exception as e:  # noqa: BLE001
                    r = {"id": int(row["*Id"]), "name": row["skill"], "buttons": buttons(row), "crash": not sess.alive(),
                         "notes": ["driver error: %r" % (e,)], "asserts": [], "select": {}, "target": {}, "notarget": {}}
                if not r["crash"] and not sess.responsive():  # alive but silent: a hang (the game is restarted)
                    r["hang"] = hung = True
                    r["notes"].append("the game stopped answering harness commands (hang); restarted")
                if r["crash"] or r.get("hang"):
                    restarts += 1
                    crash_files = sorted(set(os.listdir(g.CRASH_DIR)) - marks["crashes"]) if os.path.isdir(g.CRASH_DIR) else []
                    r["notes"].append("game process gone; new crash files: %s" % (crash_files or "none"))
                    for c in crash_files:
                        src = os.path.join(g.CRASH_DIR, c)
                        if os.path.isfile(src):
                            shutil.copy2(src, out)
                    marks["crashes"] |= set(crash_files)
                r["log"] = log
                r["verdict"] = verdict(r)
                rec["skills"][row["*Id"]] = r
                save_json(data_p, data)
                g.log("SWEEP %s %s %s: %s %s" % (cc, row["*Id"], row["skill"], r["verdict"], "; ".join(r["asserts"])[:200]))
                if restarts > 6:
                    rec["notes"] = "stopped after %d crashes" % restarts
                    break
    finally:
        gc.WD.stop_flag = True
        try:
            if started:
                g.stop()
        finally:
            for src, dst in ((g.LOADER_LOG, "d2rloader-tail.log"), (g.MXL_LOG, "mxl2012-core-tail.log")):
                try:
                    with open(os.path.join(out, dst), "a", encoding="utf-8") as f:
                        f.write(g._read_from(src, marks["loader" if "d2rloader" in dst else "mxl"]) or "")
                except OSError:
                    pass
            data["watchdog"] = gc.WD.summary()
            data["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
            save_json(data_p, data)
            print(gc.WD.summary())
    return 0


def learn_all(gc, rows, level):
    """Every class skill to `level`: first all at level 1 with their prerequisites (game_checks.learn, which sets a prerequisite to
    1 and so would lower one raised before), then each one raised; {id: base level reached}."""
    for r in rows:
        gc.learn(int(r["*Id"]), 1)
    return {r["*Id"]: gc._setskill(int(r["*Id"]), level) for r in rows}


# ---------------------------------------------------------------- report

VERDICTS = ("ok", "assert", "broken", "blocked", "unproven", "passive")
# assert cluster (message, file) -> docs/bugs.md row
CLUSTER_BUGS = [("hList", "SUnitDmg.cpp", "#53"), ("ptSkill", "Skills.cpp", "#15"), ("nSkill > 0", "SkillsSor.cpp", "#50"),
                ("nSkill > 0", "SkillsMon.cpp", "#52"), ("nDirectionIndex", "MissMode.cpp", "#54"), ("nMissile >= 0", "SkillsSor.cpp", "#51"),
                ("nSkillCastId", "Skills.cpp", "#20")]


def bug_of(cluster):
    return next((b for m, f, b in CLUSTER_BUGS if m in cluster and f in cluster), "-")


def short_assert(a):
    msg, _, rest = a.partition(" | ")
    f = rest.split(" | ")[0].split("\\")[-1]
    return "`%s` (%s)" % (msg.strip(), f.strip())


def target_text(t):
    """One button's click result for the table: its signals (or none / no click), the watched slot when it did not show the
    skill, and a note when the second click was the one recorded."""
    if t.get("crash"):
        return "CRASH"
    txt = "+".join(t.get("signals") or []) or ("none" if t.get("clicked") else "no click")
    w = t.get("watch")
    if w and "cltdo" not in (t.get("signals") or []):
        txt += " (cltdo %s: %s calls, last %s)" % (w.get("slot"), w.get("calls"), w.get("last"))
    if t.get("second"):
        txt += " (2nd click)"
    return txt


def render(data, rows):
    """The markdown of docs/skill-sweep.md from a sweep.json (`data`) and the built skills.txt rows by id (`rows`)."""
    names = {c[1]: c[2] for c in CLASSES}
    order = [c[1] for c in CLASSES]  # class order, whatever order a resumed sweep.json holds them in
    data = dict(data, classes=dict(sorted(data["classes"].items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else 99)))
    for rec in data["classes"].values():
        for sid, r in rec["skills"].items():
            if sid in rows:
                r["itypes"] = itypes(rows[sid])
            r["verdict"] = verdict(r)
    lines = ["# Skill sweep", "",
             "Generated by `py -3 tools/skill_sweep.py report` from the sweep run's `sweep.json` (evidence outside git: "
             "`mxl2012-runs/skillsweep/`). How the sweep casts and what the columns mean: the docstring of `tools/skill_sweep.py`. "
             "Every verdict comes from the player path: the skill learnt with `setskill`, selected with `skill left|right` and used "
             "by background clicks on a live zombie (Attack put on both buttons before each skill); no god mode (life refilled to "
             "about a level-120 character's, mana raised, character level 120).", "",
             "Verdicts: **ok** a click whose signs tie it to the skill (cltdo, mana, missile, other missile, state, summon, mode, warp, corpse) or "
             "an aura's state, with no engine assert and no crash; **assert** an engine assert during the skill's tests (non-fatal); "
             "**broken** a crash, a hang, a button skills.txt allows that the game refuses, or no sign at all; **blocked** no sign of "
             "the skill and the game's usability code says the test character lacks something (5 no weapon, or 2 / 4 on a skill with "
             "item type needs or a `restrict` 2 form, after the sweep wore a base of a wanted type and took on the form: the gear "
             "note says what); **unproven** the click only did damage (Attack does that too); **passive** no button allowed (only "
             "the selection was tried).", "",
             "Signals: **cltdo** the client called the skill's client do slot (skills.txt cltdofunc, else cltprgfunc1) with the "
             "skill's id (harness `watch`); **mana** spent; **missile** one of the skill's own missiles (its srv/clt missile columns "
             "and their sub missiles) seen by the server; **other missile** another one (not a weapon's plain attack missile); "
             "**damage** / **target gone**; **state** a new state on the player; **summon** new monsters; **mode** the player in a "
             "skill mode other than Attack's A1 / A2; **warp** the player 2 or more sub-tiles away 0.3 s after the click without walking "
             "(a teleport); **corpse** a new state on the corpse laid next to a corpse-consuming skill (Pagan Rites). A watched slot that the click did not reach shows its calls and last skill id.",
             "", "Run: started %s, last skill run finished %s. Real input watchdog of the last run: %s" % (
                 data.get("started"), data.get("finished", "-"), data.get("watchdog", "-")), ""]
    lines += ([data["history"], ""] if data.get("history") else []) + [
        "## Summary", "", "| Class | Skills | " + " | ".join(VERDICTS) + " | client do reached |",
        "|---|---|" + "---|" * len(VERDICTS) + "---|"]
    tot = {v: 0 for v in VERDICTS}
    tot_slot = [0, 0]
    for cc, rec in data["classes"].items():
        cnt = {v: 0 for v in VERDICTS}
        slot = [0, 0]
        for r in rec["skills"].values():
            cnt[r["verdict"]] = cnt.get(r["verdict"], 0) + 1
            if r.get("watch_slot"):
                slot[1] += 1
                slot[0] += any("cltdo" in ((t or {}).get("signals") or []) for t in r.get("target", {}).values())
        for v in VERDICTS:
            tot[v] += cnt[v]
        tot_slot = [tot_slot[0] + slot[0], tot_slot[1] + slot[1]]
        lines.append("| %s | %d | %s | %d of %d |" % (names.get(cc, cc), len(rec["skills"]), " | ".join(str(cnt[v]) for v in VERDICTS),
                                                   slot[0], slot[1]))
    lines.append("| **all** | %d | %s | %d of %d |" % (sum(tot.values()), " | ".join(str(tot[v]) for v in VERDICTS), tot_slot[0], tot_slot[1]))
    clusters = {}
    for cc, rec in data["classes"].items():
        for r in rec["skills"].values():
            for a in sorted({short_assert(a) for a in r.get("asserts", [])}):
                clusters.setdefault(a, []).append("%s %s" % (r["id"], r["name"]))
            for kind in ("crash", "hang"):
                if r.get(kind):
                    clusters.setdefault(kind, []).append("%s %s" % (r["id"], r["name"]))
    lines += ["", "## Assert, crash and hang clusters", "", "| Assert | Bug | Skills |", "|---|---|---|"]
    for k, v in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
        lines.append("| %s | %s | %d: %s |" % (k, bug_of(k), len(v), ", ".join(v)))
    if not clusters:
        lines.append("| none | - | 0 |")
    for cc, rec in data["classes"].items():
        lines += ["", "## %s (`%s`)" % (names.get(cc, cc).capitalize(), rec.get("char", "")), "",
                  "| Id | Skill | Buttons | Selectable | Click at the target | Server usability | Asserts | Verdict |",
                  "|---|---|---|---|---|---|---|---|"]
        for sid in sorted(rec["skills"], key=int):
            r = rec["skills"][sid]
            sel = ", ".join("%s %s" % (b, v) for b, v in r.get("select", {}).items()) or "-"
            tgt = "; ".join("%s: %s" % (b, target_text(t or {})) for b, t in r.get("target", {}).items()) or "-"
            if any(r.get("aura_states", {}).values()):
                tgt += "; aura states %s" % sorted({s for v in r["aura_states"].values() for s in v})
            nt = r.get("notarget") or {}
            ntxt = ("usable %s, code %s" % (nt.get("usable"), nt.get("code"))) if nt else "-"
            asserts = "; ".join(sorted({short_assert(a) for a in r.get("asserts", [])})) or (
                "CRASH" if r.get("crash") else ("HANG" if r.get("hang") else "-"))
            notes = r.get("notes") or []
            lines.append("| %s | %s | %s | %s | %s | %s | %s | %s%s |" % (
                r["id"], r["name"], "/".join(r.get("buttons") or []) or "passive", sel, tgt.replace("|", "/"), ntxt,
                asserts.replace("|", "/"), r["verdict"], (" (" + "; ".join(notes).replace("|", "/") + ")") if notes else ""))
    if data.get("extra"):
        lines += ["", data["extra"]]
    return "\n".join(lines) + "\n"


def report(args):
    data = load_json(os.path.join(os.path.abspath(args.out), "sweep.json"), None)
    if data is None:
        print("no sweep.json in %s" % args.out)
        return 2
    rows = {}
    try:
        import csv
        with open(os.path.join(ROOT, "work", "mod", "data", "global", "excel", "skills.txt"), encoding="latin-1", newline="") as f:
            rows = {r["*Id"]: r for r in csv.DictReader(f, delimiter="\t")}
    except OSError:
        pass
    text = render(data, rows)
    if args.md:
        with open(args.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %s" % args.md)
    else:
        print(text)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", default=DEFAULT_OUT)
    r.add_argument("--classes", default="")
    r.add_argument("--level", type=int, default=20)
    r.add_argument("--fresh", action="store_true")
    r.add_argument("--only", default="", help="comma-separated skill ids (a trial run)")
    r.add_argument("--redo", default="", help="comma-separated skill ids to run again (their old results are replaced)")
    r.add_argument("--reenter-gear", action="store_true",
                   help="Save and Exit + Play after gear (the workaround of bug #391, before the harness `equip` fix)")
    p = sub.add_parser("report")
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--md", default="")
    a = ap.parse_args()
    return run(a) if a.cmd == "run" else report(a)


if __name__ == "__main__":
    sys.exit(main())
