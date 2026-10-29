"""Static audit: which player skills D2R refuses, and why (lane skilluse).

D2R decides whether a unit may use a skill in `0x33f360(unit, Skill*)` (build 93847, read from the dump): 0 usable, else a
reason code. A refused skill on a mouse button does not start; a click on a monster then swings the plain Attack (mode
7 / 8) instead, which is what a play tester sees. The function, in the order D2R tests:

| Code | Test | skills.txt / states.txt |
|---|---|---|
| 3 | the row's InGame flag is off | `InGame` |
| 6 / 5 | aura / passive (a button refuses them; an aura still runs) | `aura`, `passive` |
| 2 | `0x340a80`: scroll skills need a quantity; ids 2 / 4 / 5 (Throw, Left Hand Throw / Swing) their own item rules | `scroll` |
| 2 | `0x33f1f0`: the weapon test, below | `itypea1-3`, `etypea1-2`, `itypeb1-3`, `etypeb1-2`, `requiresweapon` |
| 1 | `0x340900`: mana and cooldown (runtime) | `mana`, `minmana`, ... |
| 4 | `restrict` 0: refused while the unit has a state flagged `restrict` (D2R's shapeshift list, data +0x358, test `0x336250`); `restrict` 2: needs such a state AND one of State1-3; 1 and 3+ pass | `restrict`, `State1-3`, states `restrict` |
| 1 | minimum mana (`minmana`, with state 12) | |
| 2 | an item skill's charges | |
| 8 | `0x3404a0` (cooldown / delay state) | |
| 4 | finishing moves: progression charges below `prgchargestocast` | `finishing`, `prgchargestocast` |

The weapon test (`0x33f1f0`): nothing to test when itypea1 and etypea1 are empty (the b lists are then not read). Else, with
R / L the items in body locations 4 / 5: `requiresweapon` wants a `weap` in either hand; then the skill passes when
`hand(R, L, a) and hand(L, R, b)` or `hand(L, R, a) and hand(R, L, b)`. `hand(item, other, list)` (`0x3406b0`):
- no item: passes when the list's first itype and first etype are empty; or when itypea1 (always the a list) is `weap`,
  `mele` or `h2h` (item types 45 / 46 / 68), itypeb1 is empty and the other hand holds no weapon;
- an item: refused when it is one of the list's etypes; passes when the list has no itype, or the item is one of them
  (a broken item only for Attack; a bow / crossbow also needs its ammunition (`Shoots`) in the other hand unless `noammo`).
So `itypeb1` asks for a matching item in the second hand: a weapon in the left hand, which D2R allows a barbarian (any
one-handed weapon) and an assassin (claws) only. These are vanilla 1.13c's rules (D2R's own Frenzy, Double Swing, Double
Throw and Dragon Claw rows carry the same columns and need two weapons in D2R as in 1.13c); the audit says which Median
skills they block for which gear.

Run: `py -3 tools/skill_use_audit.py [--excel DIR] [--md FILE]` on the built tables (work/mod/data/global/excel). Exit 1
when a class skill can never be used (finding kind `never`). Unit tests: tools/tests/test_skill_use_audit.py.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILT = os.path.join(ROOT, "work", "mod", "data", "global", "excel")

CLASSES = {"ama": "amazon", "sor": "sorceress", "nec": "necromancer", "pal": "paladin", "bar": "barbarian", "dru": "druid",
           "ass": "assassin", "war": "warlock"}
DUAL_WIELD = {"bar": "weapon", "ass": "h2h"}  # what D2R lets each class hold as a weapon in the left hand
SRV_DO_SLOTS, SRV_ST_SLOTS = 191, 91  # D2R's srvdofunc / srvstfunc table sizes (docs/function-slots.md)
SPECIAL_IDS = {2: "Throw", 4: "Left Hand Throw", 5: "Left Hand Swing"}  # rows `0x340a80` and `0x33f1f0` test by id
EMPTY_HAND_TYPES = ("weap", "mele", "h2h")  # item types 45, 46, 68 in `0x3406b0`'s empty-hand case


def read(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:] if r and any(c.strip() for c in r)]


def on(v):
    return (v or "").strip() not in ("", "0")


class Types:
    """itemtypes.txt: the equivalence chain, class owner and ammunition of each type code."""

    def __init__(self, rows):
        self.rows = {r["Code"]: r for r in rows if r.get("Code")}

    def chain(self, code):
        out, todo = set(), [code]
        while todo:
            c = todo.pop()
            if c and c not in out and c in self.rows:
                out.add(c)
                todo += [self.rows[c].get("Equiv1", ""), self.rows[c].get("Equiv2", "")]
        return out

    def owner(self, code):
        return next((self.rows[c]["Class"] for c in self.chain(code) if self.rows[c].get("Class")), "")

    def shoots(self, code):
        return next((self.rows[c]["Shoots"] for c in self.chain(code) if self.rows[c].get("Shoots")), "")


class Item:
    """A base item reduced to what the weapon test reads: its type set, hands, ammunition."""

    def __init__(self, types, row, kind):
        self.code = row.get("code", "")
        self.name = row.get("name", "") or self.code
        self.type_codes = [t for t in (row.get("type", ""), row.get("type2", "")) if t]
        self.types = set().union(*(types.chain(t) for t in self.type_codes)) if self.type_codes else set()
        self.owner = next((types.owner(t) for t in self.type_codes if types.owner(t)), "")
        self.two_handed = on(row.get("2handed")) and not on(row.get("1or2handed"))
        self.kind = kind  # weapon / shield / quiver
        self.shoots = next((types.shoots(t) for t in self.type_codes if types.shoots(t)), "")

    def key(self):
        return (tuple(sorted(self.types)), self.owner, self.two_handed, self.kind, self.shoots)

    def __repr__(self):
        return self.name


def lists(row, which):
    it = [row.get(f"itype{which}{i}", "") for i in (1, 2, 3)]
    et = [row.get(f"etype{which}{i}", "") for i in (1, 2)]
    return it, et


def hand_ok(row, item, other, which):
    """`0x3406b0(item, other, row, which)`: one hand against the a (`which` "a") or b list."""
    it, et = lists(row, which)
    if item is None:
        if not et[0] and not it[0]:
            return True
        a1, b1 = row.get("itypea1", ""), row.get("itypeb1", "")
        if a1 in EMPTY_HAND_TYPES and not b1:
            if other is None or "weap" not in other.types:
                return True
            return False
        return False
    for e in et:
        if not e:
            break
        if e in item.types:
            return False
    if not it[0]:
        return True
    for t in it:
        if not t:
            break
        if t in item.types:
            if item.shoots and not on(row.get("noammo")):
                return other is not None and item.shoots in other.types
            return True
    return False


def weapon_ok(row, right, left):
    """`0x33f1f0`: the skill against the items in body locations 4 (right) and 5 (left)."""
    if not row.get("itypea1") and not row.get("etypea1"):
        return True
    if on(row.get("requiresweapon")) and not any(i is not None and "weap" in i.types for i in (right, left)):
        return False
    if hand_ok(row, right, left, "a"):
        return hand_ok(row, left, right, "b")
    if hand_ok(row, left, right, "a"):
        return hand_ok(row, right, left, "b")
    return False


def bases(types, weapons, armor, misc=()):
    """Distinct base items (one per type signature): weapons, shields (`shie`, armor.txt) and quivers (`bowq` / `xboq`,
    misc.txt as in vanilla)."""
    seen = {}
    for row in weapons:
        if row.get("code"):
            it = Item(types, row, "weapon")
            seen.setdefault(it.key(), it)
    for row in list(armor) + list(misc):
        if not row.get("code"):
            continue
        it = Item(types, row, "")
        if "shie" in it.types:
            it.kind = "shield"
        elif it.types & {"bowq", "xboq"}:
            it.kind = "quiver"
        else:
            continue
        seen.setdefault(it.key(), it)
    return list(seen.values())


def loadouts(cls, items):
    """(right, left) pairs a class can wear: D2R lets only a barbarian hold a weapon in the left hand (any one-handed
    weapon) and an assassin claws there. Throw-weapon stacks and quivers count as present (quantity > 0)."""
    mine = [i for i in items if not i.owner or i.owner == cls]
    weapons = [i for i in mine if i.kind == "weapon"]
    shields = [i for i in mine if i.kind == "shield"]
    quivers = [i for i in mine if i.kind == "quiver"]
    out = [(None, None)] + [(None, s) for s in shields]
    for w in weapons:
        out.append((w, None))
        if w.shoots:
            out += [(w, q) for q in quivers if w.shoots in q.types]
        if w.two_handed:
            continue
        out += [(w, s) for s in shields]
        dual = DUAL_WIELD.get(cls)
        for w2 in weapons:
            if w2.two_handed or w2.shoots:
                continue
            if dual == "weapon" or (dual == "h2h" and "h2h" in w.types and "h2h" in w2.types):
                out.append((w, w2))
    return out


def tree_skills(skills, skilldesc):
    """Rows of the classes' skill trees: a class and a skilldesc row placed on a skill page."""
    pages = {r["skilldesc"]: r for r in skilldesc if r.get("skilldesc")}
    return [r for r in skills if r.get("charclass") in CLASSES and on(pages.get(r.get("skilldesc", ""), {}).get("SkillPage"))]


def finding(row, kind, why, **extra):
    return {"id": int(row["*Id"]), "skill": row["skill"], "class": row.get("charclass", ""), "kind": kind, "why": why, **extra}


def audit(tables):
    """tables: dict of name -> rows (skills, skilldesc, states, itemtypes, weapons, armor). Returns a list of findings.

    kinds: `never` (D2R refuses the skill for every gear and state), `dual_wield` (a weapon in the left hand),
    `gear` (only some bases; which ones in `ok_with`), `form` (restrict 2: a form state), `locked_by` (restrict 0 and the
    class can put a `restrict` state on itself), `unrestricted` (restrict 3+: D2R does not test it, Median did)."""
    types = Types(tables["itemtypes"])
    items = bases(types, tables["weapons"], tables["armor"], tables.get("misc", ()))
    restrict_states = {r["state"] for r in tables["states"] if on(r.get("restrict"))}
    self_states = defaultdict(dict)  # class -> restrict-flagged state -> the skill that puts it on the caster
    for r in tables["skills"]:
        for col in ("aurastate", "passivestate"):
            if r.get(col) in restrict_states and r.get("charclass") in CLASSES:
                self_states[r["charclass"]].setdefault(r[col], r["skill"])
    known = set(types.rows)
    out = []
    by_class = {}
    for row in tree_skills(tables["skills"], tables["skilldesc"]):
        cls = row["charclass"]
        if not on(row.get("InGame")):
            out.append(finding(row, "never", "InGame is off: code 3"))
            continue
        bad = [row[c] for c in ("itypea1", "itypea2", "itypea3", "etypea1", "etypea2", "itypeb1", "itypeb2", "itypeb3",
                                "etypeb1", "etypeb2") if row.get(c) and row[c] not in known]
        if bad:
            out.append(finding(row, "never", "item type(s) not in itemtypes.txt: %s" % ", ".join(bad)))
            continue
        for col, size in (("srvdofunc", SRV_DO_SLOTS), ("srvstfunc", SRV_ST_SLOTS)):
            if row.get(col, "").strip().isdigit() and int(row[col]) >= size:
                out.append(finding(row, "never", "%s %s is past D2R's table (%d slots)" % (col, row[col], size)))
        if on(row.get("passive")) and not on(row.get("aura")):
            continue  # a passive: D2R (code 5) and 1.13c keep it off the buttons by design
        restrict = int(row["restrict"]) if row.get("restrict", "").strip().isdigit() else 0
        if restrict == 2:
            states = [row.get(f"State{i}", "") for i in (1, 2, 3) if row.get(f"State{i}")]
            if not any(s in restrict_states for s in states):
                out.append(finding(row, "never", "restrict 2 needs a `restrict` state and one of State1-3 (%s); none of them "
                                   "is flagged `restrict` in states.txt: code 4" % (", ".join(states) or "none")))
                continue
            out.append(finding(row, "form", "restrict 2: only while in %s (code 4 otherwise)" % ", ".join(states)))
        elif restrict == 0 and self_states.get(cls):
            locks = self_states[cls]
            out.append(finding(row, "locked_by", "restrict 0: refused (code 4) while the caster has %s" %
                               ", ".join("%s (%s)" % (s, k) for s, k in sorted(locks.items())), states=sorted(locks)))
        elif restrict >= 3:
            out.append(finding(row, "unrestricted", "restrict %d: D2R tests only 0-2, so its State1-3 rule is not applied" % restrict))
        if not row.get("itypea1") and not row.get("etypea1"):
            continue
        outfits = by_class.setdefault(cls, loadouts(cls, items))
        good = [(r, l) for r, l in outfits if weapon_ok(row, r, l)]
        if not good:
            out.append(finding(row, "never", "no gear the class can wear passes the weapon test (code 2): itypea %s, itypeb %s" %
                               (_list(row, "a"), _list(row, "b"))))
        elif all(l is not None and l.kind == "weapon" for _, l in good):
            out.append(finding(row, "dual_wield", "needs a weapon in each hand (code 2 with one weapon): itypea %s, itypeb %s" %
                               (_list(row, "a"), _list(row, "b")), ok_with=_names(good)))
        elif len(good) < len(outfits) and row.get("itypea1"):
            out.append(finding(row, "gear", "weapon types %s" % _list(row, "a"), ok_with=_names(good)))
    return sorted(out, key=lambda f: (list(CLASSES).index(f["class"]), f["id"], f["kind"]))


def _list(row, which):
    it, et = lists(row, which)
    s = "/".join(t for t in it if t) or "-"
    ex = "/".join(t for t in et if t)
    return s + (" not " + ex if ex else "")


def _names(good, limit=4):
    pairs = sorted({"%s + %s" % (r or "nothing", l or "nothing") for r, l in good})
    return pairs[:limit] + (["... %d more" % (len(pairs) - limit)] if len(pairs) > limit else [])


def load(excel):
    names = ("skills", "skilldesc", "states", "itemtypes", "weapons", "armor", "misc")
    return {n: read(os.path.join(excel, n + ".txt")) for n in names}


def markdown(found):
    lines = ["| Class | Id | Skill | Kind | Why |", "|---|---|---|---|---|"]
    for f in found:
        if f["kind"] == "gear":
            continue
        why = f["why"] + ("; passes with e.g. " + ", ".join(f["ok_with"]) if f.get("ok_with") else "")
        lines.append("| %s | %d | %s | %s | %s |" % (CLASSES[f["class"]], f["id"], f["skill"], f["kind"], why.replace("|", "/")))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--excel", default=BUILT)
    ap.add_argument("--md", help="write the table of findings (all but `gear`) to this file")
    a = ap.parse_args(argv)
    found = audit(load(a.excel))
    counts = defaultdict(int)
    locks = defaultdict(list)
    for f in found:
        counts[f["kind"]] += 1
        if f["kind"] == "locked_by":
            locks[(f["class"], f["why"])].append(str(f["id"]))
        elif f["kind"] != "gear":
            print("%-11s %-4d %-28s %-12s %s" % (CLASSES[f["class"]], f["id"], f["skill"], f["kind"], f["why"]))
    for (cls, why), ids in locks.items():
        print("%-11s %-33s %-12s %s: %s" % (CLASSES[cls], "%d skills" % len(ids), "locked_by", why, " ".join(ids)))
    print("totals:", ", ".join("%s %d" % kv for kv in sorted(counts.items())))
    if a.md:
        with open(a.md, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(markdown(found))
    return 1 if counts["never"] else 0


if __name__ == "__main__":
    sys.exit(main())
