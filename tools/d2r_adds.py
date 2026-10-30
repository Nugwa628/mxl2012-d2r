"""Remove (or bend to Median XL 2012's rules) what D2R added after 1.14d, on the migrated tables (lane d2radds).

Owner decision 2026-10-28: D2R additions (2.4 .. 3.3 "Reign of the Warlock") that conflict with Median XL 2012 go; the
Warlock stays playable but follows Median's rules (level cap, experience, points per level, difficulty); Akara's respec
stays D2R's. The full list with the decision per addition is docs/d2r-additions.md; this step does the data side.

Steps (each one is idempotent, so the step can run twice):
  terror_zones    D2R's desecratedzones.json with every ladder_enabled / non_ladder_enabled flag false and
                  max_herald_tiers 0 -> <out>/data/hd/global/excel/desecratedzones.json (no zone, no Herald)
  no_terrorize    monstats CannotDesecrate = CannotHerald = 1 on every row and the Desecrated / Herald treasure classes
                  (monstats, superuniques) emptied: a zone that still fires cannot boost or re-loot Median's monsters
  ladder          firstLadderSeason / lastLadderSeason / disallowCraftingIn(Non)Ladder emptied (setitems, uniqueitems,
                  runes, cubemain, treasureclassex): D2R's season gating copied onto Median rows by key (Angelical
                  Raiment got seasons 15-16) must not hide Median items
  sunder          states sunderfull / sunder-res-reduce emptied (D2R 2.6 Sunder charms; 1.13c has no sunder rules)
  merc_classitems hireling equivalentcharclass emptied (D2R lets Rogues / Barbarians wear class items; 1.13c does not)
  dup_codes       gems / books rows that D2R appended with an item code a Median row already has (Median spells
                  "Saphire", D2R "Sapphire": both rows carry gcb..gpb and D2R's vanilla gem mods would shadow Median's;
                  Median names its books "unused", so D2R's three Tome rows were appended after them)
  warlock         Warlock on Median's rules: experience column (curve + MaxLvl 120) and the charstats per-level /
                  movement / regen constants copied from the template class (Amazon, whose D2R values match the
                  Warlock's), Median's common starting kit plus a Median dagger instead of D2R's `dgr` (no such item)
  advanced_stash  keep (default): misc AdvancedStashStackable copied from D2R's misc.txt onto the mod rows with the same
                  code and type (runes, gems, rejuvenation potions, Token; the migration leaves it empty, bug #510);
                  --advanced-stash off empties it (owner question)

Input:  <mod>/data/global/excel/{,base/}<table>.txt   the migrated tables (tables lane: work/mod)
        <d2r>/data/hd/global/excel/desecratedzones.json D2R 93847 baseline (read-only)
Output: <out> (default: <mod>, edited in place); same layout; <out>/d2r_adds_report.md

Usage: py -3 tools/d2r_adds.py [--mod work/mod] [--out DIR] [--d2r EXTRACT] [--advanced-stash keep|off] [--only STEP ...]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402  (.mxl-local.json defaults, D2R extraction)

ROOT = Path(__file__).resolve().parent.parent
D2R_DEFAULT = localconfig.default_d2r_extract()
EXCEL = Path("data") / "global" / "excel"
BANKS = ("", "base")  # RotW bank, Classic/LoD bank
ZONES = Path("data") / "hd" / "global" / "excel" / "desecratedzones.json"

LADDER_COLUMNS = ("firstLadderSeason", "lastLadderSeason", "disallowCraftingInLadder", "disallowCraftingInNonLadder")
LADDER_TABLES = ("setitems", "uniqueitems", "runes", "cubemain", "treasureclassex")
TERROR_TC = {"monstats": ("TreasureClassDesecrated", "TreasureClassDesecratedChamp", "TreasureClassDesecratedUnique",
                          "TreasureClassHerald"),
             "superuniques": ()}  # superuniques: every "... Desecrated" column, found by name
DUP_CODE_COLUMNS = {"gems": ("code",), "books": ("ScrollSpellCode", "BookSpellCode")}
POSITIONAL = ("books",)
STASH_FLAG = "AdvancedStashStackable"

WARLOCK = "Warlock"
TEMPLATE = "Amazon"  # D2R's Warlock per-level values equal D2R's Amazon's (ManaPerMagic 8 vs 6 aside)
# charstats columns that are Median's rules, not class identity (base str/dex/int/vit, skills, strings stay D2R's)
WARLOCK_RULE_COLUMNS = ("hpadd", "ManaRegen", "ToHitFactor", "WalkVelocity", "RunVelocity", "RunDrain",
                        "LifePerLevel", "StaminaPerLevel", "ManaPerLevel", "LifePerVitality", "StaminaPerVitality",
                        "ManaPerMagic", "StatPerLevel", "SkillsPerLevel", "BlockFactor")
# starting kit: Median's kit shared by all seven classes (items 1-5: cube, 8 potions, 10 portal scrolls, statue, body
# armour; '01-' last) with "Dagger (Grade 1)" (code 142) in the right hand in place of the class weapon
WARLOCK_KIT_SHARED = 5
WARLOCK_WEAPON = ("142", "rarm", "1")
WARLOCK_KIT_TAIL = "01-"


# ---------------------------------------------------------------- tables

class Table:
    def __init__(self, path: Path):
        self.path = path
        text = path.read_bytes().decode("utf-8")  # not read_text: it would turn CRLF into LF
        self.crlf = "\r\n" in text
        lines = text.replace("\r\n", "\n").split("\n")
        self.trailing = lines and lines[-1] == ""
        if self.trailing:
            lines = lines[:-1]
        self.header = lines[0].split("\t")
        self.rows = [line.split("\t") for line in lines[1:]]
        self.changed = 0

    def col(self, name: str) -> int | None:
        return self.header.index(name) if name in self.header else None

    def get(self, row: list[str], i: int) -> str:
        return row[i] if i < len(row) else ""

    def set(self, row: list[str], i: int, value: str) -> bool:
        if self.get(row, i) == value:
            return False
        row.extend([""] * (i + 1 - len(row)))
        row[i] = value
        self.changed += 1
        return True

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        nl = "\r\n" if self.crlf else "\n"
        body = nl.join("\t".join(r) for r in [self.header, *self.rows])
        path.write_text(body + (nl if self.trailing else ""), encoding="utf-8", newline="")


class Mod:
    """The migrated tables of both banks, loaded on demand, written to `out` when changed."""

    def __init__(self, mod: Path, out: Path):
        self.mod, self.out = mod, out
        self.cache: dict[tuple[str, str], Table | None] = {}

    def tables(self, name: str) -> list[Table]:
        found = []
        for bank in BANKS:
            key = (bank, name)
            if key not in self.cache:
                p = self.mod / EXCEL / bank / f"{name}.txt"
                self.cache[key] = Table(p) if p.exists() else None
            if self.cache[key] is not None:
                found.append(self.cache[key])
        return found

    def save(self) -> list[str]:
        written = []
        for (bank, name), t in self.cache.items():
            if t is not None and t.changed:
                t.write(self.out / EXCEL / bank / f"{name}.txt")
                if t.changed:
                    written.append(f"{bank + '/' if bank else ''}{name}.txt ({t.changed} cells/rows)")
        return written


# ---------------------------------------------------------------- steps

def clear_flags(node, counts: dict) -> None:
    if isinstance(node, dict):
        for key in ("ladder_enabled", "non_ladder_enabled"):
            if key in node:
                counts[key] = counts.get(key, 0) + bool(node[key])
                node[key] = False
        if node.get("max_herald_tiers"):
            counts["max_herald_tiers"] = counts.get("max_herald_tiers", 0) + 1
            node["max_herald_tiers"] = 0
        for value in node.values():
            clear_flags(value, counts)
    elif isinstance(node, list):
        for value in node:
            clear_flags(value, counts)


def step_terror_zones(mod: Mod, d2r: Path, log: list[str]) -> None:
    src = d2r / ZONES
    if not src.exists():
        raise SystemExit(f"missing {src} (D2R baseline; set --d2r or MXL_D2R_EXTRACT)")
    data = json.loads(src.read_text(encoding="utf-8"))  # the UInt64 seed stays exact (Python ints)
    counts: dict = {}
    clear_flags(data, counts)
    dst = mod.out / ZONES
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.append(f"terror_zones: {counts.get('ladder_enabled', 0)} ladder + {counts.get('non_ladder_enabled', 0)} "
               f"non-ladder flags cleared, {counts.get('max_herald_tiers', 0)} Herald tier limits set to 0 -> {ZONES.as_posix()}")


def step_no_terrorize(mod: Mod, log: list[str]) -> None:
    n = 0
    for t in mod.tables("monstats"):
        flags = [i for i in (t.col("CannotDesecrate"), t.col("CannotHerald")) if i is not None]
        tcs = [i for c in TERROR_TC["monstats"] if (i := t.col(c)) is not None]
        for r in t.rows:
            if not t.get(r, 0) or t.get(r, 0) == "Expansion":
                continue
            n += sum(t.set(r, i, "1") for i in flags) + sum(t.set(r, i, "") for i in tcs)
    for t in mod.tables("superuniques"):
        tcs = [i for i, c in enumerate(t.header) if "Desecrated" in c]
        for r in t.rows:
            n += sum(t.set(r, i, "") for i in tcs)
    log.append(f"no_terrorize: {n} monstats / superuniques cells set (CannotDesecrate/CannotHerald 1, terror TCs empty)")


def step_clear_columns(mod: Mod, log: list[str], name: str, tables, columns) -> None:
    n = 0
    for table in tables:
        for t in mod.tables(table):
            for c in columns:
                i = t.col(c)
                if i is not None:
                    n += sum(t.set(r, i, "") for r in t.rows)
    log.append(f"{name}: {n} cells emptied ({', '.join(columns)} in {', '.join(tables)})")


def step_dup_codes(mod: Mod, d2r: Path, log: list[str]) -> None:
    """Drop rows that are D2R's own rows (identical to a D2R baseline row) and repeat an item code of a mod row."""
    dropped = []
    for table, code_cols in DUP_CODE_COLUMNS.items():
        for bank in BANKS:
            ts = [t for t in mod.tables(table) if t.path.parent.name == ("base" if bank else "excel")]
            src = d2r / EXCEL / bank / f"{table}.txt"
            if not ts or not src.exists():
                continue
            t = ts[0]
            base = Table(src)
            # D2R's rows seen through the mod table's header (the migration may add, drop or reorder columns)
            d2r_keyed = {tuple(dict(zip(base.header, r)).get(c, "") for c in t.header) for r in base.rows}
            idx = [t.col(c) for c in code_cols if t.col(c) is not None]

            def codes(r):
                return tuple(t.get(r, i) for i in idx)

            def from_d2r(r):
                return tuple(t.get(r, j) for j in range(len(t.header))) in d2r_keyed

            mod_rows = [r for r in t.rows if not from_d2r(r)]
            mod_codes = {codes(r) for r in mod_rows if any(codes(r))}
            keep = []
            for n, r in enumerate(t.rows):
                # books is read by row (book type): D2R's rows appended after the mod's own are surplus records
                appended = table in POSITIONAL and mod_rows and n >= len(mod_rows) and from_d2r(r)
                if appended or (from_d2r(r) and any(codes(r)) and codes(r) in mod_codes):
                    dropped.append(f"{bank + '/' if bank else ''}{table}: {t.get(r, 0)} ({'/'.join(codes(r))})")
                    t.changed += 1
                else:
                    keep.append(r)
            t.rows = keep
    log.append(f"dup_codes: {len(dropped)} D2R rows dropped" + (": " + "; ".join(dropped) if dropped else ""))


def step_advanced_stash(mod: Mod, d2r: Path, log: list[str]) -> None:
    """D2R's materials / gems / runes tab (bankexpansionlayouthd.json, one AdvancedStashSlotWidget per item code) takes an
    item only when its misc row has AdvancedStashStackable 1. The migration leaves D2R-only columns empty, so every Median
    row lost it (bug #510: no rune could go into the runes tab). A mod row with D2R's code and item type takes D2R's flag."""
    n, rows = 0, 0
    for bank in BANKS:
        ts = [t for t in mod.tables("misc") if t.path.parent.name == ("base" if bank else "excel")]
        src = d2r / EXCEL / bank / "misc.txt"
        if not ts or not src.exists():
            continue
        t, base = ts[0], Table(src)
        flag, code, typ = t.col(STASH_FLAG), t.col("code"), t.col("type")
        bflag, bcode, btyp = base.col(STASH_FLAG), base.col("code"), base.col("type")
        if None in (flag, code, bflag, bcode):
            continue
        d2r_rows = {base.get(r, bcode): r for r in base.rows if base.get(r, bflag) not in ("", "0")}
        for r in t.rows:
            src_row = d2r_rows.get(t.get(r, code))
            if src_row is None:
                continue
            if typ is not None and btyp is not None and t.get(r, typ) != base.get(src_row, btyp):
                continue  # another item on D2R's code: it has no slot of its own in the tab
            rows += 1
            n += t.set(r, flag, base.get(src_row, bflag))
    log.append(f"advanced_stash: kept (D2R's stack tab; owner question, docs/d2r-additions.md); {STASH_FLAG} of D2R on "
               f"{rows} rows by code and type, {n} cells set")


def step_warlock(mod: Mod, log: list[str]) -> None:
    n = 0
    for t in mod.tables("experience"):
        w, a = t.col(WARLOCK), t.col(TEMPLATE)
        if w is None or a is None:
            continue
        n += sum(t.set(r, w, t.get(r, a)) for r in t.rows)
    for t in mod.tables("charstats"):
        rows = {t.get(r, 0): r for r in t.rows}
        war, tpl = rows.get(WARLOCK), rows.get(TEMPLATE)
        if war is None or tpl is None:
            continue
        for c in WARLOCK_RULE_COLUMNS:
            if (i := t.col(c)) is not None:
                n += t.set(war, i, t.get(tpl, i))
        kit = []
        for k in range(1, WARLOCK_KIT_SHARED + 1):
            kit.append(tuple(t.get(tpl, t.col(f"item{k}{s}")) if t.col(f"item{k}{s}") is not None else ""
                             for s in ("", "loc", "count")))
        kit.append(WARLOCK_WEAPON)
        kit.append((WARLOCK_KIT_TAIL, "", "1"))
        for k in range(1, 11):
            item, loc, count = kit[k - 1] if k <= len(kit) else ("0", "", "0")
            for s, v in (("", item), ("loc", loc), ("count", count)):
                if (i := t.col(f"item{k}{s}")) is not None:
                    n += t.set(war, i, v)
            if (i := t.col(f"item{k}quality")) is not None:
                n += t.set(war, i, "2")
    log.append(f"warlock: {n} cells set (experience column and MaxLvl from {TEMPLATE}; charstats "
               f"{', '.join(WARLOCK_RULE_COLUMNS)}; starting kit)")


STEPS = ("terror_zones", "no_terrorize", "ladder", "sunder", "merc_classitems", "dup_codes", "warlock", "advanced_stash")


def run(mod_dir: Path, out_dir: Path, d2r: Path, advanced_stash: str = "keep", only=None) -> list[str]:
    mod_dir, out_dir = mod_dir.resolve(), out_dir.resolve()
    if not (mod_dir / EXCEL).is_dir():
        raise SystemExit(f"no migrated tables in {mod_dir / EXCEL} (run the tables lane's build first)")
    if out_dir != mod_dir:  # standalone: copy the whole mod folder, then edit the copy
        shutil.copytree(mod_dir, out_dir, dirs_exist_ok=True)
        mod_dir = out_dir
    mod = Mod(mod_dir, out_dir)
    log: list[str] = []
    want = set(only or STEPS)
    if "terror_zones" in want:
        step_terror_zones(mod, d2r, log)
    if "no_terrorize" in want:
        step_no_terrorize(mod, log)
    if "ladder" in want:
        step_clear_columns(mod, log, "ladder", LADDER_TABLES, LADDER_COLUMNS)
    if "sunder" in want:
        step_clear_columns(mod, log, "sunder", ("states",), ("sunderfull", "sunder-res-reduce"))
    if "merc_classitems" in want:
        step_clear_columns(mod, log, "merc_classitems", ("hireling",), ("equivalentcharclass",))
    if "dup_codes" in want:
        step_dup_codes(mod, d2r, log)
    if "warlock" in want:
        step_warlock(mod, log)
    if "advanced_stash" in want:
        if advanced_stash == "off":
            step_clear_columns(mod, log, "advanced_stash", ("misc",), (STASH_FLAG,))
        else:
            step_advanced_stash(mod, d2r, log)
    written = mod.save()
    report = ["# D2R additions step (tools/d2r_adds.py)", "", *[f"- {line}" for line in log], "",
              "Written: " + (", ".join(written) if written else "nothing changed")]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "d2r_adds_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod", help="migrated mod folder (input)")
    ap.add_argument("--out", type=Path, help="output folder (default: --mod, in place)")
    ap.add_argument("--d2r", type=Path, default=D2R_DEFAULT, help="D2R 93847 extraction (read-only)")
    ap.add_argument("--advanced-stash", choices=("keep", "off"), default="keep")
    ap.add_argument("--only", nargs="+", choices=STEPS)
    a = ap.parse_args(argv)
    for line in run(a.mod, a.out or a.mod, a.d2r, a.advanced_stash, a.only):
        print(f"   {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
