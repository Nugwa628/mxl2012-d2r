"""Weapon share of missiles.txt `SrcDamage`, the way D2R 93847 reads it (same as 1.13c / 1.14d; docs/txt-migrate.md "SrcDamage").

D2R's missiles loader keeps `SrcDamage` as an unsigned byte at record +0x155 (field type 4, as `Red`/`Green`/`Blue`; 1.14d:
+0x12d), so the cell's low 8 bits count: 0-255, and -1 is stored as 255. The missile damage function (D2R `0x3bfa4c`,
1.14d `0x64b860`, same branches) picks the share of the source unit's damage, in 1/128ths:
  - the missile has a `Skill` (or `MissileSkill` set): the skill's skills.txt `SrcDam` (+0x24d); the missile's own SrcDamage
    only matters as 255 (-1), which makes the share 0;
  - otherwise the missile's own byte (-1 = 255 = 199%).
`Half2HSrc` halves it when the source holds a two-handed weapon. The share multiplies the source's weapon min / max damage
(stats 21 / 22, <<8, then >>7) and, through D2R `0x3c12f0` (1.14d `0x64aa60`), the elemental and other damage fields:
linear, no clamp. Median 2012's missiles.bin (what 1.13c ran) holds the same byte for all 2665 rows.

Usage: py -3 tools/srcdamage.py [excel dir] [--min N]   (lists the rows whose share is above N/128, default 128)
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL = 128  # 100% of the source's damage


def _cell(header: list[str], r: list[str], col: str) -> str:
    i = header.index(col) if col in header else -1
    return r[i].strip() if 0 <= i < len(r) else ""


def stored_byte(v: str) -> int | None:
    """The byte D2R keeps for a SrcDamage cell (blank = 0); None for a cell that is not an integer."""
    v = v.strip()
    if not v:
        return 0
    try:
        return int(v) & 0xFF
    except ValueError:
        return None


def weapon_share(srcdamage: str, has_skill: bool, skill_srcdam: str = "") -> int:
    """Share of the source's damage in 1/128ths that D2R gives a missile (before Half2HSrc)."""
    b = stored_byte(srcdamage) or 0
    if has_skill:
        return 0 if b == 0xFF else (stored_byte(skill_srcdam) or 0)
    return b


def rows(excel: Path) -> list[dict]:
    """Every missile row with a SrcDamage cell or a skill: name, cell, skill, share (1/128ths)."""
    def load(name: str) -> tuple[list[str], list[list[str]]]:
        with open(excel / f"{name}.txt", encoding="utf-8", errors="replace", newline="") as f:
            t = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
        return t[0], t[1:]

    mh, mr = load("missiles")
    sh, sr = load("skills")
    skill_src = {_cell(sh, r, "skill"): _cell(sh, r, "SrcDam") for r in sr if r}
    out = []
    for r in mr:
        name = r[0].strip() if r else ""
        if not name or name == "Expansion":
            continue
        cell, skill = _cell(mh, r, "SrcDamage"), _cell(mh, r, "Skill")
        has_skill = bool(skill) or _cell(mh, r, "MissileSkill") == "1"
        if not cell and not has_skill:
            continue
        out.append({"missile": name, "cell": cell, "skill": skill, "has_skill": has_skill,
                    "share": weapon_share(cell, has_skill, skill_src.get(skill, "")), "half2h": _cell(mh, r, "Half2HSrc") == "1"})
    return out


def problems(header: list[str], mrows: list[list[str]]) -> list[tuple[str, str, str, str, str]]:
    """(severity, column, row, problem, value) for validate.py: a SrcDamage cell D2R would not keep as written (outside
    -1..255 or not a number: the byte wraps, 256 = 0)."""
    out = []
    for r in mrows:
        name = r[0].strip() if r else ""
        v = _cell(header, r, "SrcDamage")
        if not name or not v:
            continue
        b = stored_byte(v)
        if b is None or not -1 <= int(v) <= 255:
            out.append(("warn", "SrcDamage", name, "SrcDamage outside -1..255: D2R keeps only the low byte "
                        "(tools/srcdamage.py)", v))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("excel", nargs="?", default=str(ROOT / "work" / "mod" / "data" / "global" / "excel"))
    ap.add_argument("--min", type=int, default=FULL, help="list rows whose share is above this (1/128ths)")
    a = ap.parse_args()
    listed = [r for r in rows(Path(a.excel)) if r["share"] > a.min or (r["cell"] and r["has_skill"]
                                                                       and stored_byte(r["cell"]) not in (0, 0xFF))]
    for r in listed:
        how = f"skill {r['skill'] or '(MissileSkill)'}'s SrcDam" if r["has_skill"] else "own byte"
        note = "; own SrcDamage ignored" if r["has_skill"] and stored_byte(r["cell"]) not in (0, 0xFF) else ""
        print(f"{r['missile']:24} SrcDamage={r['cell']:>4}  share {r['share']:3}/128 = {r['share'] * 100 // FULL:3}% "
              f"({how}{note}){' Half2HSrc' if r['half2h'] else ''}")
    print(f"{len(listed)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
