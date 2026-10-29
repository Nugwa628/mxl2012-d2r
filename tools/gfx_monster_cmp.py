"""Compare the Median XL 2012 monster art sets with the prior art sets of the reference checkout (read-only).

    py -3 -I tools/gfx_monster_cmp.py --mpq <extract-mpq dir> --reference <reference assets/median/data/global/monsters>
        --hd-report <reference work/mod/hd_monsters.md> --out <dir>

A monster art set is a folder under data/global/monsters/ named by its token (the monstats Code).
Marks each 2012 set: in the prior sets (same token folder), same DCC/COF file names as the prior set, and the prior
HD stand-in donor for that token (from the reference hd_monsters.md; that report is keyed by Code).
Writes monster-compare.md and monster-compare.json to --out.
"""
import argparse
import json
import os
import sys
from collections import defaultdict


def dirs_of(path):
    if not os.path.isdir(path):
        return []
    return sorted(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))


def files_under(root):
    out = set()
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith((".dcc", ".cof", ".dc6")):
                out.add(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/").lower())
    return out


def hd_donors(path):
    """code -> list of (median id, donor, confidence) from the reference hd_monsters.md table."""
    by_code = defaultdict(list)
    if not os.path.isfile(path):
        return by_code
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 7 or cells[0] in ("Median Id", "---") or set(cells[0]) <= {"-", ":"}:
                continue
            mid, _name, code, donor, _scale, _colour, conf = cells[:7]
            by_code[code].append((mid, donor, conf))
    return by_code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mpq", required=True)
    ap.add_argument("--reference", required=True)
    ap.add_argument("--hd-report", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    mpq_root = os.path.join(a.mpq, "data", "global", "monsters")
    tokens = dirs_of(mpq_root)
    prior_tokens = set(dirs_of(a.reference))
    prior_lower = {t.lower(): t for t in prior_tokens}
    donors = hd_donors(a.hd_report)

    rows = []
    for t in tokens:
        mroot = os.path.join(mpq_root, t)
        mfiles = files_under(mroot)
        st = t if t in prior_tokens else prior_lower.get(t.lower())
        in_s = st is not None
        same_names = None
        if in_s:
            sfiles = files_under(os.path.join(a.reference, st))
            rel_m = {os.path.relpath(p, t) for p in mfiles}
            rel_s = {os.path.relpath(p, st) for p in sfiles}
            # compare by file name relative to the token folder (case-folded)
            same_names = "yes" if rel_m == rel_s else ("no" if rel_m and rel_s else "-")
        d = donors.get(t) or donors.get(t.upper()) or []
        best = ""
        for conf in ("high", "medium", "low"):
            if any(c == conf for _m, _d, c in d):
                best = conf
                break
        rows.append({
            "token": t,
            "files": len(mfiles),
            "in_prior": in_s,
            "same_file_names": same_names or "-",
            "hd_donors": len(d),
            "hd_best_confidence": best or "-",
            "hd_donor_units": sorted({u for _m, u, _c in d}),
        })

    n_in = sum(1 for r in rows if r["in_prior"])
    n_same = sum(1 for r in rows if r["same_file_names"] == "yes")
    n_hd = sum(1 for r in rows if r["hd_donors"])
    summary = {"mpq_monster_sets": len(rows), "in_prior": n_in, "same_file_names": n_same,
               "with_prior_hd_donor": n_hd,
               "not_in_prior": [r["token"] for r in rows if not r["in_prior"]]}

    with open(os.path.join(a.out, "monster-compare.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": rows}, f, indent=1, ensure_ascii=False)

    lines = ["| token | files | in reference | same file names | reference HD donor (confidence) |", "|---|---:|---|---|---|"]
    for r in rows:
        don = ", ".join(r["hd_donor_units"][:2]) if r["hd_donor_units"] else "-"
        if r["hd_donors"]:
            don = "%s (%s)" % (don, r["hd_best_confidence"])
        lines.append("| `%s` | %d | %s | %s | %s |" % (r["token"], r["files"],
                                                      "yes" if r["in_prior"] else "no",
                                                      r["same_file_names"], don))
    with open(os.path.join(a.out, "monster-compare.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "not_in_prior"}, indent=1))
    print("not in prior: " + ", ".join(summary["not_in_prior"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
