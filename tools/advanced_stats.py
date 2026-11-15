"""The Advanced Stats panel's groups (bugs #581 / #582): data/advanced_stats.tsv -> the plugin part `advstats`'s table
(statbook/src/advstats_table.h) and its strings (work/mod/.../strings/mxl2012/advanced_stats.json, written by txt_migrate).

data/advanced_stats.tsv, one row per panel row in display order inside its group:
  stat    itemstatcost row name; several joined by "," for a row of several stats
  show    always / nonzero (txt_migrate.read_advanced_stats: the advdisplay value when the plugin part is off)
  group   one of GROUPS
  row     empty = D2R's own row text (the item tooltip line, needs a descfunc); else the plugin's own row:
          range:<Key>  min and max stat, text "Adds %d-%d ..."     value:<Key>  one percent stat based on 100, text with value - 100
          avoid        passive_dodge, passive_avoid, passive_evade: one line when equal, else one line each
  source  where the row came from

  py -3 tools/advanced_stats.py header [--named work/named/itemstatcost.txt]   writes statbook/src/advstats_table.h
  py -3 tools/advanced_stats.py check  [--named ...]                           fails when the header is out of date
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tbl2json import LANGS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TSV = ROOT / "data" / "advanced_stats.tsv"
HEADER = ROOT / "statbook" / "src" / "advstats_table.h"
NAMED = ROOT / "work" / "named" / "itemstatcost.txt"
STRING_FILES = ("strings/mxl2012/advanced_stats.json", "strings-legacy/mxl2012/advanced_stats.json")

# group id -> (string key, English heading), in display order
GROUPS = {
    "offense": ("AdvStatsGroupOffense", "Offense"),
    "spell": ("AdvStatsGroupSpell", "Spell Damage"),
    "defense": ("AdvStatsGroupDefense", "Defense"),
    "resist": ("AdvStatsGroupResist", "Resistances"),
    "speed": ("AdvStatsGroupSpeed", "Speed"),
    "lifemana": ("AdvStatsGroupLifeMana", "Life & Mana"),
    "attributes": ("AdvStatsGroupAttributes", "Attributes"),
    "skills": ("AdvStatsGroupSkills", "Skills"),
    "summons": ("AdvStatsGroupSummons", "Summons"),
    "other": ("AdvStatsGroupOther", "Other"),
}
# The own rows' texts (English in every language, as the mod's other strings)
TEXTS = {
    "AdvStatsAddsFire": "Adds %d-%d Fire Damage",
    "AdvStatsAddsLightning": "Adds %d-%d Lightning Damage",
    "AdvStatsAddsCold": "Adds %d-%d Cold Damage",
    "AdvStatsAddsMagic": "Adds %d-%d Magic Damage",
    "AdvStatsSkillAttackSpeed": "%+d%% Attack Speed from Skills",
    "AdvStatsSkillMoveSpeed": "%+d%% Movement Speed from Skills",
}
# statbook/src/advstats_logic.h AvoidTexts
AVOID_TEXTS = {
    "AdvStatsAvoidAll": "%d%% Chance to Avoid Damage",
    "AdvStatsDodge": "%d%% Chance to Dodge Melee Attacks",
    "AdvStatsAvoidMissile": "%d%% Chance to Avoid Missiles",
    "AdvStatsEvade": "%d%% Chance to Evade Attacks while Moving",
}
AVOID_STATS = ["passive_dodge", "passive_avoid", "passive_evade"]
KINDS = {"": ("Stat", 1), "range": ("Range", 2), "value": ("Value", 1), "avoid": ("Avoid", 3)}


def read_rows(path: Path = TSV) -> list[dict]:
    """The rows in display order (GROUPS order, file order inside a group), checked."""
    lines = [line.split("\t") for line in path.read_text("utf-8").splitlines() if line.strip()]
    h = lines[0]
    rows, seen = [], set()
    for n, r in enumerate(lines[1:], 2):
        d = dict(zip(h, r))
        stats = d["stat"].split(",")
        kind, _, key = d.get("row", "").partition(":")
        where = f"{path.name}:{n} {d['stat']}"
        if d["group"] not in GROUPS:
            raise ValueError(f"{where}: group {d['group']!r} is not one of {list(GROUPS)}")
        if kind not in KINDS:
            raise ValueError(f"{where}: row {d['row']!r}: kind must be empty, range:<Key>, value:<Key> or avoid")
        if len(stats) != KINDS[kind][1]:
            raise ValueError(f"{where}: a {kind or 'stat'} row has {KINDS[kind][1]} stat(s)")
        if kind in ("range", "value") and key not in TEXTS:
            raise ValueError(f"{where}: text key {key!r} is not in TEXTS")
        if kind == "avoid" and stats != AVOID_STATS:
            raise ValueError(f"{where}: an avoid row lists {','.join(AVOID_STATS)}")
        if d["show"] not in ("always", "nonzero"):
            raise ValueError(f"{where}: show must be always or nonzero")
        for s in stats:
            if s in seen:
                raise ValueError(f"{where}: {s} listed twice")
            seen.add(s)
        rows.append({"stats": stats, "always": d["show"] == "always", "group": d["group"], "kind": kind, "key": key})
    order = list(GROUPS)
    return sorted(rows, key=lambda r: order.index(r["group"]))


def stat_ids(named: Path) -> dict[str, int]:
    """itemstatcost row name -> stat id in the built mod: the row number in Median's table, renumbered by tools/idmap.py
    (vanilla rows keep their ids; Median's own rows move after D2R's, e.g. game_craftpoints 183 -> 368)."""
    import fxpaths
    import idmap
    lines = named.read_text("utf-8-sig", errors="replace").splitlines()[1:]
    m = idmap.IdMap.build(named.parent, Path(fxpaths.D2R) / "data" / "global" / "excel")
    return {line.split("\t")[0]: m.new_id("itemstatcost", i) for i, line in enumerate(lines)}


def cstr(s: str | None) -> str:
    return "nullptr" if s is None else json.dumps(s)


def header_text(rows: list[dict], ids: dict[str, int]) -> str:
    missing = [s for r in rows for s in r["stats"] if s not in ids]
    if missing:
        raise ValueError(f"not in itemstatcost: {missing}")
    out = ["// Generated by tools/advanced_stats.py from data/advanced_stats.tsv; do not edit (py -3 tools/advanced_stats.py header).",
           "#pragma once", "", '#include "advstats_logic.h"', "", "namespace advstats {", "",
           "inline constexpr Group Groups[] = {"]
    out += [f"    {{{cstr(k)}, {cstr(e)}}}," for k, e in GROUPS.values()]
    out += ["};", "", "inline constexpr Row Rows[] = {"]
    order = list(GROUPS)
    for r in rows:
        kind = KINDS[r["kind"]][0]
        st = [ids[s] for s in r["stats"]] + [0] * (3 - len(r["stats"]))
        key = r["key"] or None
        out.append(f"    {{{order.index(r['group'])}, Kind::{kind}, {'true' if r['always'] else 'false'}, {{{st[0]}, {st[1]}, {st[2]}}}, "
                   f"{cstr(key)}, {cstr(TEXTS.get(key) if key else None)}, {cstr(','.join(r['stats']))}}},")
    out += ["};", "", "}  // namespace advstats", ""]
    return "\n".join(out)


def strings() -> list[dict]:
    """The strings file of the headings and own rows: English in every language."""
    texts = {k: e for k, e in GROUPS.values()} | TEXTS | AVOID_TEXTS
    return [{"Key": k, **dict.fromkeys(LANGS, v)} for k, v in texts.items()]


def write_strings(data: Path) -> list[Path]:
    """Writes the strings file under `data` (the mod's data folder); returns the paths."""
    text = json.dumps(strings(), indent=2, ensure_ascii=False) + "\n"
    out = []
    for rel in STRING_FILES:
        p = data / "local" / "lng" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        out.append(p)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["header", "check"])
    ap.add_argument("--named", type=Path, default=NAMED, help="the named itemstatcost (stat ids)")
    a = ap.parse_args(argv)
    text = header_text(read_rows(), stat_ids(a.named))
    if a.cmd == "header":
        HEADER.write_bytes(text.encode("utf-8"))
        print(f"wrote {HEADER}")
        return 0
    if not HEADER.exists() or HEADER.read_bytes().decode("utf-8") != text:
        print(f"{HEADER} is out of date: py -3 tools/advanced_stats.py header", file=sys.stderr)
        return 1
    print("advstats_table.h is up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
