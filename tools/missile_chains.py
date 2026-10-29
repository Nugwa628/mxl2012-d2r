"""Missile creation chains of missiles.txt: self-feeding loops and the missiles one launch makes (bug #395).

A missile row makes other missiles through its columns: SubMissile1-3 (server do function), HitSubMissile1-4 (server hit
function), CltSubMissile1-3 / CltHitSubMissile1-4 (the client's own copies) and ExplosionMissile. The tool builds that graph
per side (server, client) and reports
  - loops: a missile that can make itself again through any chain (unbounded in principle: an error), and
  - the load: how many missiles one launch of a row makes on that side, children included (a warning above the budget).

Fan-out per edge, from the functions read in D2R 93847 and 1.14d (same parameters in both, docs/bugs.md #395):
  server do 15 / client do 19 (Frozen Orb's): one SubMissile every Param1 (CltParam1) frames while the missile lives,
      so ceil(Range / Param1) of them;
  server hit 20 / client hit 25 (Lightning Fury's): one HitSubMissile per target, up to sHitPar2 (cHitPar2) targets;
      0 = the skill's number, counted as 1 here;
  server do 1 / client do 1 (and blank): the plain flight, makes no SubMissile (a SubMissile cell there is dead data);
  any other function: 1 per named missile (a lower bound for novas and the like).
  client do 15 naming the row itself: the engine's trail copies (vanilla fingermagespider), not counted.
ExplosionMissile counts 1 on both sides. Range ignores LevRange (the level-1 lifetime).

Usage: py -3 tools/missile_chains.py [missiles.txt] [--top N] [--budget N]
Default table: work/mod/data/global/excel/missiles.txt.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import idmap  # noqa: E402

BUDGET = 300  # missiles per launch on one side (CLI listing)
# A monster's attack missile (monstats Miss* columns) is fired by packs at the AI's attack rate: above this many server
# missiles per launch validate.py warns. The Heretics' skull swarm made about 425 (bug #395), 225 after txt_migrate's
# MISSILE_LOAD; the next heaviest monster attack makes under 100.
MONSTER_ATTACK_BUDGET = 250
MONSTER_MISSILE_COLUMNS = ("MissA1", "MissA2", "MissS1", "MissS2", "MissS3", "MissS4", "MissC", "MissSQ")
# Loops known to be harmless, name -> why. A row here that starts to be used needs a new look.
LOOP_ALLOW = {"barpaincloud": "Median 2012 row named by no skill, monster or other missile (dead data): its hit 29 nova "
                              "would make itself again"}

SIDES = {
    "server": {"do": "pSrvDoFunc", "hit": "pSrvHitFunc", "sub": ["SubMissile1", "SubMissile2", "SubMissile3"],
               "hitsub": ["HitSubMissile1", "HitSubMissile2", "HitSubMissile3", "HitSubMissile4"],
               "freq": "Param1", "max": "sHitPar2", "periodic": {"15"}, "fury": {"20"}},
    "client": {"do": "pCltDoFunc", "hit": "pCltHitFunc", "sub": ["CltSubMissile1", "CltSubMissile2", "CltSubMissile3"],
               "hitsub": ["CltHitSubMissile1", "CltHitSubMissile2", "CltHitSubMissile3", "CltHitSubMissile4"],
               "freq": "CltParam1", "max": "cHitPar2", "periodic": {"19"}, "fury": {"25"}},
}
NO_SPAWN_DO = {"", "0", "1"}


def _int(v: str, default: int = 0) -> int:
    try:
        return int(v.strip())
    except (ValueError, AttributeError):
        return default


def edges(header: list[str], rows: list[list[str]], side: str) -> dict[str, list[tuple[str, int, str]]]:
    """Missile name -> [(child name, count per launch, via column)] for one side."""
    s = SIDES[side]
    col = {c: i for i, c in enumerate(header)}

    def cell(r: list[str], c: str) -> str:
        i = col.get(c)
        return r[i].strip() if i is not None and i < len(r) else ""

    out: dict[str, list[tuple[str, int, str]]] = {}
    for r in rows:
        name = r[0].strip() if r else ""
        if not name or name == "Expansion":
            continue
        e: list[tuple[str, int, str]] = []
        do, hit = cell(r, s["do"]), cell(r, s["hit"])
        if do not in NO_SPAWN_DO:
            n = math.ceil(_int(cell(r, "Range")) / max(_int(cell(r, s["freq"]), 1), 1)) if do in s["periodic"] else 1
            e += [(cell(r, c), max(n, 1), c) for c in s["sub"] if cell(r, c)
                  # client do 15 copies the missile as its own short-lived trail (vanilla fingermagespider): no loop
                  and not (side == "client" and do == "15" and cell(r, c) == name)]
        if hit:
            n = max(_int(cell(r, s["max"])), 1) if hit in s["fury"] else 1
            e += [(cell(r, c), n, c) for c in s["hitsub"] if cell(r, c)]
        if cell(r, "ExplosionMissile"):
            e.append((cell(r, "ExplosionMissile"), 1, "ExplosionMissile"))
        out.setdefault(name, e)  # first row of a name wins, as the game's name lookup
    return out


def analyse(graph: dict[str, list[tuple[str, int, str]]]) -> tuple[dict[str, int], list[list[str]]]:
    """(missiles one launch of each row makes, itself included; loops as name paths). A row on a loop counts as -1."""
    total: dict[str, int] = {}
    loops: list[list[str]] = []
    state: dict[str, int] = {}  # 1 = on the stack, 2 = done

    def visit(root: str) -> None:
        stack: list[tuple[str, int]] = [(root, 0)]
        path: list[str] = []
        while stack:
            name, i = stack.pop()
            if i == 0:
                if state.get(name) == 2:
                    continue
                state[name] = 1
                path.append(name)
            kids = graph.get(name, [])
            if i < len(kids):
                stack.append((name, i + 1))
                kid = kids[i][0]
                if state.get(kid) == 1:
                    loops.append(path[path.index(kid):] + [kid])
                elif state.get(kid) != 2 and kid in graph:
                    stack.append((kid, 0))
                continue
            n = 1
            for kid, cnt, _c in kids:
                t = total.get(kid, 1) if kid in graph else 1
                if t < 0 or state.get(kid) == 1:
                    n = -1
                    break
                n += cnt * t
            total[name] = n
            state[name] = 2
            path.pop()

    for name in graph:
        if state.get(name) != 2:
            visit(name)
    return total, loops


def check(header: list[str], rows: list[list[str]], budget: int = BUDGET) -> dict[str, object]:
    """Both sides: {'server': (totals, loops), 'client': ..., 'over': [(side, name, total)]} for validate.py and the CLI."""
    res: dict[str, object] = {"over": []}
    for side in SIDES:
        total, loops = analyse(edges(header, rows, side))
        res[side] = (total, loops)
        res["over"] += [(side, n, t) for n, t in total.items() if t > budget]
    return res


def problems(header: list[str], rows: list[list[str]], mon: tuple[list[str], list[list[str]]] | None = None,
             budget: int = MONSTER_ATTACK_BUDGET) -> list[tuple[str, str, str, str, str]]:
    """(severity, column, row, problem, value) for validate.py: every loop not in LOOP_ALLOW is an error; a monster attack missile
    (monstats Miss* columns of `mon`) making more than `budget` server missiles per launch is a warning."""
    res = check(header, rows)
    out: list[tuple[str, str, str, str, str]] = []
    seen: set[tuple[str, ...]] = set()
    for side in SIDES:
        for lp in res[side][1]:
            key = tuple(sorted(set(lp)))
            if key in seen or all(n in LOOP_ALLOW for n in key):
                continue
            seen.add(key)
            out.append(("error", "Missile", lp[0], f"self-feeding missile loop ({side} side)", " -> ".join(lp)))
    if mon:
        mh, mrows = mon
        total = res["server"][0]
        for r in mrows:
            for c in MONSTER_MISSILE_COLUMNS:
                v = r[mh.index(c)].strip() if c in mh and mh.index(c) < len(r) else ""
                if v and total.get(v, 0) > budget:
                    out.append(("warn", c, r[0], f"monster attack missile makes more than {budget} server missiles per "
                                "launch (bug #395, tools/missile_chains.py)", f"{v} {total[v]}"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("table", nargs="?", default=str(ROOT / "work" / "mod" / "data" / "global" / "excel" / "missiles.txt"))
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--budget", type=int, default=BUDGET)
    a = ap.parse_args()
    header, rows = idmap.read_tsv(Path(a.table))
    header = header[0] if header and isinstance(header[0], list) else header
    res = check(header, rows, a.budget)
    bad = 0
    for side in SIDES:
        total, loops = res[side]
        print(f"== {side}: {len(total)} rows, {len(loops)} loops")
        for lp in loops:
            allowed = all(n in LOOP_ALLOW for n in lp)
            bad += not allowed
            print("  LOOP " + " -> ".join(lp) + (f"  (allowed: {LOOP_ALLOW[lp[0]]})" if allowed else ""))
        for name, t in sorted(total.items(), key=lambda kv: -kv[1])[: a.top]:
            print(f"  {t:6d}  {name}{'  OVER BUDGET' if t > a.budget else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
