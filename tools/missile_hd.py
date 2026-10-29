"""HD looks for Median's missiles: work/mod/data/hd/missiles/missiles.json.

D2R draws a missile in HD by looking up its missiles.txt name (lowercased) in data/hd/missiles/missiles.json, which
names a model under data/hd/missiles/. The CelFile column is only used by the classic (legacy) renderer. Median's
5,000+ new missiles are not in D2R's map, so in HD they draw nothing.

Each Median missile gets the model D2R uses for a vanilla missile with the same CelFile (the most common one when
several do). Vanilla names whose CelFile Median changed are remapped the same way. CelFiles no vanilla missile
uses (old D2 art D2R never converted) take a hand-picked look-alike from LOOKALIKE, chosen from Median's
missiles.txt values (movement, size, colour). The rest stay unmapped until the art port; they are listed in the
report.

Usage: python tools/missile_hd.py
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from txt_migrate import read_tsv  # noqa: E402
import fxpaths  # noqa: E402

ROOT = fxpaths.ROOT
D2R = fxpaths.D2R_DATA
OUT = ROOT / "work" / "mod" / "data"

# CelFile (lowercase) -> D2R HD model, for classic art no vanilla D2R missile uses
LOOKALIKE = {
    # Whirlpool's body (whirlpool_missile, _2, _3): stationary looping blue swirl, size 3
    "coldfuse": "expansion_tornado",
    # Whirlpool's outward pieces (whirlpool_missile_submissil_2, _3_submiss_4, missiles_534x/536x): one-frame
    # cold bolts, velocity 14; Frozen Orb's bolts are the same kind
    "extra\\frostnova2": "ice_bolt",
}


def cel(row: list[str], h: list[str]) -> str:
    return row[h.index("CelFile")].lower().replace("/", "\\")


def main() -> int:
    hd = json.loads(fxpaths.d2r_file("data/hd/missiles/missiles.json").read_text("utf-8-sig"))
    vh, vrows = read_tsv(D2R / "global" / "excel" / "missiles.txt")
    mh, mrows = read_tsv(OUT / "global" / "excel" / "missiles.txt")
    by_cel: dict[str, Counter] = defaultdict(Counter)
    vanilla_cel = {}
    for r in vrows:
        if not r or not r[0]:
            continue
        name = r[0].lower()
        vanilla_cel[name] = cel(r, vh)
        if name in hd:
            by_cel[cel(r, vh)][hd[name]] += 1
    added = remapped = lookalike = 0
    unmapped: Counter = Counter()
    for r in mrows:
        if not r or not r[0]:
            continue
        name, c = r[0].lower(), cel(r, mh)
        if name in hd and vanilla_cel.get(name, c) == c:
            continue  # vanilla missile, same art
        if c in ("", "null"):
            model = "null"
        elif c in by_cel:
            model = by_cel[c].most_common(1)[0][0]
        elif c in LOOKALIKE:
            model = LOOKALIKE[c]
            lookalike += 1
        else:
            unmapped[c] += 1
            continue
        remapped += name in hd
        added += name not in hd
        hd[name] = model
    target = OUT / "hd" / "missiles" / "missiles.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(hd, separators=(",", ":")), encoding="utf-8")
    print(f"missiles.json: {added} Median missiles added ({lookalike} by look-alike), {remapped} vanilla names "
          f"remapped to Median's art; {sum(unmapped.values())} missiles on {len(unmapped)} CelFiles without an HD "
          f"model (art port)")
    (ROOT / "work" / "mod" / "missile_hd_report.md").write_text(
        "# Missiles without an HD model\n\n| CelFile | Missiles |\n|---|---|\n"
        + "".join(f"| {c} | {n} |\n" for c, n in unmapped.most_common()), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
