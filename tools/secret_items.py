"""Make Median XL 2012's secret uniques drop (lane secrets, owner request 2026-11-16).

Nine uniques with stats on the community wiki's "Secrets" page are in v005's uniqueitems.txt but never drop: their 1.13c
`enabled` (D2R `spawnable`) is blank. Aerial's Skull and the Token beta ring stay out (owner); the page's 17 names
without stats stay as they are. data/secret_items.tsv lists the rows with:

  rarity       the row's new uniqueitems rarity (its weight when a unique of its base is rolled)
  lvl req      a new required level, blank keeps Median's (Lady of Storms: 555 -> 40, owner)
  peer factor  every other spawnable unique on the same base code has its rarity multiplied by this, so a secret is
               rarer than any of them while their odds against each other stay what Median gave them (x4 on the sacred
               bases, whose uniques already have rarity 1-2; x10 on jewels)

Median's stats and qlvl (`lvl`) are not changed, nor any treasure class: the bases already drop.

The step runs after txt_migrate.py and before chronicle.py (which hides unspawnable rows from D2R's Chronicle). It edits
both banks in place and is idempotent: tables where every secret row already has its new values are left alone.
Report with the drop shares per base: <mod>/secret_items_report.md.

Usage: py -3 tools/secret_items.py apply [--mod work/mod] [--data data/secret_items.tsv]
       py -3 tools/secret_items.py odds  [--mod work/mod]     (the shares only)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from d2r_adds import BANKS, EXCEL, Table  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "secret_items.tsv"
PREFIX = "mxl2012:"  # txt_migrate's namespace on uniqueitems index


def load_secrets(path: Path = DATA) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    out = []
    for line in lines[1:]:
        if line.strip():
            r = dict(zip(head, line.split("\t")))
            r["rarity"], r["peer factor"] = int(r["rarity"]), int(r["peer factor"])
            out.append(r)
    return out


def key(index: str) -> str:
    return index[len(PREFIX):] if index.startswith(PREFIX) else index


def apply_table(t: Table, secrets: list[dict]) -> list[str]:
    ci, cc, cs, cr, cq = (t.col(c) for c in ("index", "code", "spawnable", "rarity", "lvl req"))
    by = {s["index"]: s for s in secrets}
    rows = {key(t.get(r, ci)): r for r in t.rows if key(t.get(r, ci)) in by}
    missing = sorted(set(by) - set(rows))
    if missing:
        raise SystemExit(f"{t.path}: secret rows not found: {', '.join(missing)}")
    done = all(t.get(r, cs) == "1" and t.get(r, cr) == str(by[k]["rarity"])
               and (not by[k]["lvl req"] or t.get(r, cq) == by[k]["lvl req"]) for k, r in rows.items())
    if done:
        return [f"{t.path.name}: already applied"]
    log = []
    factors: dict[str, int] = {}
    for k, r in rows.items():
        code = t.get(r, cc)
        f = by[k]["peer factor"]
        if factors.setdefault(code, f) != f:
            raise SystemExit(f"{k}: peer factor {f} differs from another secret on base {code}")
    secret_rows = {id(r) for r in rows.values()}
    for code, f in factors.items():
        n = 0
        for r in t.rows:
            if id(r) in secret_rows or t.get(r, cc) != code or t.get(r, cs) != "1":
                continue
            t.set(r, cr, str(int(t.get(r, cr) or "0") * f))
            n += 1
        log.append(f"base {code}: {n} spawnable uniques' rarity x{f}")
    for k, r in rows.items():
        s = by[k]
        t.set(r, cs, "1")
        t.set(r, cr, str(s["rarity"]))
        if s["lvl req"]:
            t.set(r, cq, s["lvl req"])
        log.append(f"{s['name']} ({k}): spawnable, rarity {s['rarity']}" + (f", lvl req {s['lvl req']}" if s["lvl req"] else ""))
    return log


def odds(t: Table, secrets: list[dict]) -> list[str]:
    """Share of each secret among the uniques of its base at item level 120 (and at its own qlvl when lower)."""
    ci, cc, cs, cr, cl = (t.col(c) for c in ("index", "code", "spawnable", "rarity", "lvl"))
    by = {s["index"]: s for s in secrets}
    out = ["| item | base | qlvl | ilvl | weight | pool | share | rarest other unique | most common other unique |", "|-|-|-|-|-|-|-|-|-|"]
    for r in t.rows:
        k = key(t.get(r, ci))
        if k not in by:
            continue
        code, q = t.get(r, cc), int(t.get(r, cl) or "0")
        for ilvl in sorted({120, max(q, 1)}):
            if ilvl < q:
                continue
            pool = [x for x in t.rows if t.get(x, cc) == code and t.get(x, cs) == "1" and int(t.get(x, cl) or "0") <= ilvl]
            total = sum(int(t.get(x, cr) or "0") for x in pool)
            others = [int(t.get(x, cr) or "0") for x in pool if key(t.get(x, ci)) not in by]
            w = int(t.get(r, cr))
            rare = f"1 in {total / min(others):,.0f}" if others and min(others) else "-"
            common = f"1 in {total / max(others):,.1f}" if others and max(others) else "-"
            out.append(f"| {by[k]['name']} | {code} | {q} | {ilvl} | {w} | {total} | 1 in {total / w:,.0f} | {rare} | {common} |")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=("apply", "odds"))
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod")
    ap.add_argument("--data", type=Path, default=DATA)
    a = ap.parse_args(argv)
    secrets = load_secrets(a.data)
    report = ["# Secret uniques (tools/secret_items.py)", ""]
    for bank in BANKS:
        p = a.mod / EXCEL / bank / "uniqueitems.txt"
        if not p.exists():
            continue
        t = Table(p)
        if a.action == "apply":
            log = apply_table(t, secrets)
            if t.changed:
                t.write(p)
            report += [f"## {bank or 'expansion'} bank", "", *[f"- {line}" for line in log], ""]
        if not bank:
            report += ["## Drop shares (expansion bank): when an item of the base rolls unique", "", *odds(t, secrets), ""]
    text = "\n".join(report)
    if a.action == "apply":
        (a.mod / "secret_items_report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
