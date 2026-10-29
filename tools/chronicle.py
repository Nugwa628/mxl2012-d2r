"""D2R's Chronicle (3.x collection log) over Median XL 2012's uniques, sets and runewords (lane qol).

Owner decision 2026-10-28: keep the Chronicle and make it track Median's items. How D2R 93847 builds it (data side; the
panel is code, `ChroniclePanel` in data/global/ui/layouts/chroniclepanelhd.json):

  tabs        three, fixed: Unique / Sets / Runewords (`tabMessages` name native list panels: no data-made tabs)
  entries     uniqueitems.txt and setitems.txt rows (column `disableChronicle` 1 hides a row: D2R sets it on its
              unspawnable uniques and the crafted Sunder charms), runes.txt rows with `complete` 1 (no per-row switch)
  categories  the tree on the left of the Unique / Sets lists is itemuicategories.txt (parent / sub categories, the
              Name is the string key); an item lands in its base's `UICatOverride` (armor / weapons / misc) or else
              its item type's `UICategory` (itemtypes.txt). Runewords group by the item types' `RunewordCategory1/2`.

Median's itemtypes.txt replaces D2R's (only Grimoire and Colossal Jewel, D2R rows kept for the Warlock, carry a category),
so without this step every Median item had no category. This step, idempotent, both banks where the column exists:

  categories       itemtypes `UICategory` / `RunewordCategory1/2` left empty are filled: a Median type with D2R's code
                   takes D2R's value (Median reuses vanilla codes with the vanilla meaning); any other type inherits from
                   the first type up its Equiv1 / Equiv2 chain that has one (Sacred "qtor" -> "tors" -> armor, "2hsd" ->
                   "swor" -> sword, Reward / Challenge charms "grtz" / "ara?" -> "char" -> charm). EXTRA_CATEGORIES
                   names the few types whose chain ends without one (Mega Ring "kill" -> rings; Assassin Naginata / Sorceress
                   Crystal Sword, Equiv "mele" only -> their class weapon category).
  disableChronicle  1 on uniqueitems / setitems rows that are not collectable Median items: no base item (Median's 103
                   vanilla set items whose base Median removed, separators), unspawnable rows (Median's 443 placeholder
                   "SkillsdLastSkillEver" rows and its 14 `enabled` 0 rows), quest items (Median's Viper amulet, Staff
                   of Kings, Horadric Staff, Hell Forge Hammer, Khalim's flails: D2R's Chronicle lists no quest item
                   either) and rows whose base type has no UI category (they would sit in no category). Everything
                   else is 0 (shown). D2R's own uniques / sets / runewords are gone already (replace-rule tables).

Not possible by data: a fourth tab (relics, quest items, ...), hiding single runewords (runes.txt has no switch; `complete`
0 would disable the runeword itself). Median's runes.txt has 3,080 complete rows for 1,420 names (one row per socket
count / base); D2R lists each row.

Usage: py -3 tools/chronicle.py [--mod work/mod] [--d2r EXTRACT]       report: <mod>/chronicle_report.md
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from d2r_adds import BANKS, D2R_DEFAULT, EXCEL, Mod, Table  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CATEGORY_COLUMNS = ("UICategory", "RunewordCategory1", "RunewordCategory2")
# Median item types whose Equiv chain reaches no D2R category (Mega Ring: misc) or only a too general one is set by hand:
# the class melee weapons Assassin Naginata / Sorceress Crystal Sword (Equiv "mele") join their class weapon category
EXTRA_CATEGORIES = {"kill": "rings", "nagi": "assas", "scrd": "sorce"}
BASE_TABLES = ("armor", "weapons", "misc")


def by_code(t: Table, key: str) -> dict[str, list[str]]:
    c = t.col(key)
    return {t.get(r, c): r for r in t.rows if c is not None and t.get(r, c)}


def resolve_categories(types: Table, d2r_types: Table | None) -> dict[str, int]:
    """Fill empty UICategory / RunewordCategory cells of `types` in place; returns counts per column."""
    code = types.col("Code")
    eq = [types.col("Equiv1"), types.col("Equiv2")]
    d2r = by_code(d2r_types, "Code") if d2r_types is not None else {}
    rows = by_code(types, "Code")
    counts = collections.Counter()
    # UICategory alone; the two runeword columns as a pair (D2R's "weap" has r_mis + r_mel, a sword only r_mel)
    for group in (("UICategory",), ("RunewordCategory1", "RunewordCategory2")):
        cis = [types.col(n) for n in group]
        if None in cis:
            continue
        dcis = [d2r_types.col(n) for n in group] if d2r_types is not None else []

        def own(c: str) -> tuple[str, ...]:
            r = rows.get(c)
            if r is not None and any(types.get(r, ci) for ci in cis):
                return tuple(types.get(r, ci) for ci in cis)
            if c in d2r and None not in dcis and any(d2r_types.get(d2r[c], i) for i in dcis):
                return tuple(d2r_types.get(d2r[c], i) for i in dcis)
            if group == ("UICategory",) and c in EXTRA_CATEGORIES:
                return (EXTRA_CATEGORIES[c],)
            return ()

        def find(c: str) -> tuple[str, ...]:
            seen, queue = set(), [c]
            while queue:
                t = queue.pop(0)
                if t in seen or not t:
                    continue
                seen.add(t)
                if own(t):
                    return own(t)
                r = rows.get(t)
                if r is not None:
                    queue += [types.get(r, e) for e in eq if e is not None]
            return ()

        for r in types.rows:
            c = types.get(r, code)
            if not c or any(types.get(r, ci) for ci in cis):
                continue
            for name, ci, v in zip(group, cis, find(c)):
                if v and types.set(r, ci, v):
                    counts[name] += 1
    return counts


def item_category(code: str, bases: dict[str, tuple[Table, list[str]]], types: Table) -> str:
    t, r = bases[code]
    ov = t.col("UICatOverride")
    if ov is not None and t.get(r, ov):
        return t.get(r, ov)
    tr = by_code(types, "Code").get(t.get(r, t.col("type")))
    return types.get(tr, types.col("UICategory")) if tr is not None else ""


def is_quest(t: Table, r: list[str], types: Table) -> bool:
    q = t.col("quest")
    if q is not None and t.get(r, q) not in ("", "0"):
        return True
    return t.get(r, t.col("type")) == "ques"


def chronicle_flags(mod: Mod) -> list[str]:
    """disableChronicle on uniqueitems / setitems of the banks that have the column."""
    out = []
    for bank in BANKS:
        p = lambda n: mod.mod / EXCEL / bank / f"{n}.txt"  # noqa: E731
        if not all(p(n).exists() for n in ("itemtypes", "uniqueitems", "setitems", *BASE_TABLES)):
            continue
        types = next(t for t in mod.tables("itemtypes") if t.path == p("itemtypes"))
        bases: dict[str, tuple[Table, list[str]]] = {}
        for n in BASE_TABLES:
            t = next(t for t in mod.tables(n) if t.path == p(n))
            for c, r in by_code(t, "code").items():
                bases.setdefault(c, (t, r))
        for name, key in (("uniqueitems", "code"), ("setitems", "item")):
            t = next(t for t in mod.tables(name) if t.path == p(name))
            dc, kc, sp = t.col("disableChronicle"), t.col(key), t.col("spawnable")
            if dc is None:
                continue
            why = collections.Counter()
            for r in t.rows:
                if not any(c.strip() for c in r) or r[0] == "Expansion":  # separators are not records
                    continue
                code = t.get(r, kc)
                if code not in bases:
                    reason = "no base item"
                elif sp is not None and t.get(r, sp) != "1":
                    reason = "not spawnable"
                elif is_quest(*bases[code], types):
                    reason = "quest item"
                elif not item_category(code, bases, types):
                    reason = "no UI category"
                else:
                    reason = ""
                t.set(r, dc, "1" if reason else "0")
                why[reason or "shown"] += 1
            out.append(f"{bank or 'rotw'} {name}: " + ", ".join(f"{k} {v}" for k, v in sorted(why.items())))
    return out


def runeword_note(mod: Mod) -> list[str]:
    out = []
    for t in mod.tables("runes")[:1]:
        c, n = t.col("complete"), t.col("Name")
        live = [t.get(r, n) for r in t.rows if t.get(r, c) == "1"]
        out.append(f"runes: {len(live)} complete rows, {len(set(live))} names (each row is one Chronicle entry)")
    return out


def run(mod_dir: Path, d2r: Path) -> list[str]:
    mod = Mod(mod_dir, mod_dir)
    lines = []
    for bank in BANKS:
        p = mod_dir / EXCEL / bank / "itemtypes.txt"
        if not p.exists():
            continue
        types = next(t for t in mod.tables("itemtypes") if t.path == p)
        dp = d2r / EXCEL / bank / "itemtypes.txt"
        counts = resolve_categories(types, Table(dp) if dp.exists() else None)
        lines.append(f"{bank or 'rotw'} itemtypes: " + (", ".join(f"{k} +{v}" for k, v in counts.items()) or "nothing to fill"))
    lines += chronicle_flags(mod)
    lines += runeword_note(mod)
    lines += [f"wrote {w}" for w in mod.save()]
    (mod_dir / "chronicle_report.md").write_text("# Chronicle (tools/chronicle.py)\n\n" + "\n".join(f"- {x}" for x in lines) + "\n",
                                                 encoding="utf-8")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod")
    ap.add_argument("--d2r", type=Path, default=D2R_DEFAULT, help="D2R 93847 extraction (read-only)")
    a = ap.parse_args(argv)
    for line in run(a.mod, a.d2r):
        print(f"   {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
