r"""Audit: which skill/missile function slots changed meaning between 1.13c and D2R 93847 (docs/function-slots.md).

  py -3 tools/func_slots.py            print, per function column, the vanilla skills/missiles whose slot differs

A slot "moved" when the same vanilla skill (missile) uses number A in 1.13c's table and B in D2R's. The mapping
(A -> B) is read out of the rows; a column slot that maps to more than one D2R slot is reported as ambiguous.
"""
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402  (.mxl-local.json defaults, D2R extraction)
import vanilla113  # noqa: E402  (the 1.13c view built from D2R's own tables)

ROOT = Path(__file__).resolve().parent.parent
D2R = (localconfig.default_d2r_extract() / "data" / "global" / "excel"
       / os.environ.get("D2R_BANK", "base"))

SKILL_COLS = ["srvstfunc", "srvdofunc", "srvstopfunc", "srvprgfunc1", "srvprgfunc2", "srvprgfunc3",
              "cltstfunc", "cltdofunc", "cltstopfunc", "cltprgfunc1", "cltprgfunc2", "cltprgfunc3"]
MISSILE_COLS = ["pSrvDoFunc", "pSrvHitFunc", "pCltDoFunc", "pCltHitFunc", "pCltSrcTownFunc", "pCltTgtTownFunc",
                "pSrvDmgFunc", "pCltDmgFunc", "SrvCalc1", "CltCalc1"]
KEY = {"skills.txt": "skill", "missiles.txt": "Missile"}

# Median's skills.txt carries 1.13c / D2Sigma numbers. Where D2R renumbered or reused a vanilla slot, a Median row on the
# old number runs another D2R function (docs/function-slots.md). Slots below are the old (1.13c) numbers and their D2R home.
SRV_DO_REMAP = {"109": "9"}  # 1.13c MonFrenzy melee + frenzy state; D2R merged it into Frenzy's 9, reused 109 for Townportal O Skill
SRV_START_REMAP = {"64": "67"}  # 1.13c MonFrenzy start (target check); D2R's 64 is Bind Demon's, the frenzy counter reset is 67
SRV_START_REMAP_WITH_DO = {("37", "109"): "67"}  # BloodLordFrenzy: 37 (Zeal's start) + frenzy do; D2R's own row is 67 + 9
CLT_START_DROP = {"82"}  # 1.13c Baal Corpse Explode start; D2R's table ends at 55 and runs nothing for a slot past it
TOWN_PORTAL = "town_portal"  # the one Median skill that runs D2R's srvdofunc 109 on purpose (D2Sigma 155)
# slots whose D2R function differs from 1.13c's for a Median row (value -> what D2R runs); Townportal O Skill must only
# be reached by town_portal (migrated D2Sigma 155 -> 109), never by a Median row's own number
POISON = {("srvdofunc", "109"): "D2R Townportal O Skill (itemless town portal, 0x5822b0)",
          ("srvstfunc", "64"): "D2R Bind Demon start (import thunk), not 1.13c's MonFrenzy start",
          ("cltstfunc", "82"): "past the end of D2R's client start table (55)"}


def read(p: Path):
    lines = p.read_text("utf-8", errors="replace").split("\n")
    h = lines[0].rstrip("\r").split("\t")
    return h, [l.rstrip("\r").split("\t") for l in lines[1:] if l.strip()]


def vanilla(table: str):
    """(header, rows) of skills.txt / missiles.txt as 1.13c has them (tools/vanilla113.py)."""
    return vanilla113.load(table.removesuffix(".txt"), read)


def moves(table: str, cols: list[str]) -> dict[str, dict[str, Counter]]:
    """column -> 1.13c slot -> Counter of D2R slot (as 'slot:skills')"""
    vh, vr = vanilla(table)
    dh, dr = read(D2R / table)
    k = KEY[table]
    d = {r[dh.index(k)]: r for r in dr}
    out: dict[str, dict[str, Counter]] = {}
    names: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for c in cols:
        if c not in vh or c not in dh:
            continue
        m: dict[str, Counter] = defaultdict(Counter)
        for r in vr:
            n = r[vh.index(k)]
            if n not in d or not n:
                continue
            a, b = r[vh.index(c)] or "", d[n][dh.index(c)] or ""
            m[a][b] += 1
            names[(c, a, b)].append(n)
        out[c] = m
    moves.names = names  # type: ignore[attr-defined]
    return out


def main() -> None:
    for table, cols in (("skills.txt", SKILL_COLS), ("missiles.txt", MISSILE_COLS)):
        print(f"== {table}")
        res = moves(table, cols)
        for c, m in res.items():
            diff = {a: dict(b) for a, b in m.items() if set(b) != {a}}
            print(c, "->", diff)
            for a, b in diff.items():
                for bb in b:
                    if bb != a:
                        print(f"    {a} -> {bb}: {', '.join(moves.names[(c, a, bb)][:8])}")  # type: ignore[attr-defined]


if __name__ == "__main__":
    main()
