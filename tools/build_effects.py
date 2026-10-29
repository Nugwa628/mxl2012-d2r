"""Build step: HD stand-ins for Median XL 2012's missiles and overlays (work/mod/, data/hd-effects-map.tsv).

  1. tools/art_provenance.py   which Median DCCs are vanilla animations (work/mod/art_provenance.json; cached)
  2. tools/effects_hd.py       every missile / overlay row -> a D2R HD effect; writes work/mod/data/hd/**, the report
                               work/mod/effects_hd.md and the committed table data/hd-effects-map.tsv
  3. check()                   every row has an effect that exists, every art file of the mod is in the table, every
                               in-use missile / overlay art is decided (or drawn by D2R's own row), every hand pick
                               (data/hd-effects-picks.tsv) took effect

Needs numpy and Pillow (tools/requirements-fx.txt) and the read-only inputs of tools/fxpaths.py. No game runs, no network.
tools/build.py runs steps 1 and 2 itself (art_provenance.py, effects_hd.py); this wrapper is for running the lot, or only the
check, outside it.
Usage: py -3 tools/build_effects.py [--groups effects,monsters] [--no-provenance] [--no-prior] [--check-only]
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402

CLASSES = {"exact", "hand", "provenance", "prior", "variant", "stand-in", "no-art", "unreferenced"}
DECIDED = ("exact", "hand", "provenance", "prior", "variant", "stand-in")


def read_map(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))


def check(work: Path, map_path: Path) -> list[str]:
    """Problems of a finished run (empty = fine)."""
    import effects_hd as e
    bad: list[str] = []
    rows = read_map(map_path)
    seen = set()
    for r in rows:
        key = (r["kind"], r["art"])
        if key in seen:
            bad.append(f"duplicate table line {key}")
        seen.add(key)
        if r["class"] not in CLASSES:
            bad.append(f"{key}: unknown class {r['class']!r}")
        if r["class"] in DECIDED and not r["effect"]:
            bad.append(f"{key}: class {r['class']} without an effect")
        if r["class"] in DECIDED and r["confidence"] not in ("high", "medium", "low"):
            bad.append(f"{key}: no confidence")
        if r["class"] in ("stand-in", "prior", "provenance", "hand") and not r["reason"]:
            bad.append(f"{key}: no reason")
    # every DCC of the mod is in the table (referenced or listed as unreferenced)
    for folder, kind in (("missiles", "missile"), ("overlays", "overlay")):
        for p in (fxpaths.MXL / folder).rglob("*.dcc"):
            art = p.relative_to(fxpaths.MXL / folder).with_suffix("").as_posix().lower()
            if (kind, art) not in seen:
                bad.append(f"{kind} DCC {art} is not in the table")
    by_key = {(r["kind"], r["art"]): r for r in rows}
    bad += check_picks(by_key, e.load_picks(fxpaths.PICKS_TSV), work)
    bad += check_in_use(by_key, work)
    # every effect exists: ours (work/mod/data) or D2R's own
    mj = json.loads((work / "data" / "hd" / "missiles" / "missiles.json").read_text("utf-8"))
    mj.pop("dependencies", None)
    for r in rows:
        if not r["effect"]:
            continue
        if r["kind"] == "missile":
            model = r["effect"]
            if not ((work / "data" / "hd" / "missiles" / f"{model}.json").exists() or (e.HDM / f"{model}.json").exists()):
                bad.append(f"missile {r['art']}: model {model} has no definition")
        elif not (e.HDO / f"{r['effect']}.json").exists():
            bad.append(f"overlay {r['art']}: D2R has no {r['effect']}")
    # every decided row is keyed in missiles.json / has its overlay file
    for p in (work / "data" / "hd" / "overlays").rglob("*.json"):
        d = json.loads(p.read_text("utf-8"))
        if d.get("name") != p.stem:
            bad.append(f"{p}: name {d.get('name')!r} differs from the file")
    d2r = json.loads((e.HDM / "missiles.json").read_text("utf-8-sig"))
    ours = {v for k, v in mj.items() if d2r.get(k) != v}  # D2R's own map has a dangling entry or two; only ours count
    for model in ours:
        if model != "null" and not ((work / "data" / "hd" / "missiles" / f"{model}.json").exists() or (e.HDM / f"{model}.json").exists()):
            bad.append(f"missiles.json names model {model}, which has no definition")
    return bad


def check_picks(by_key: dict[tuple[str, str], dict], picks: dict, work: Path | None = None) -> list[str]:
    """Every hand pick shows in the table: its art is there as class hand with the picked effect (or a scaled or tinted
    copy). A pick for named rows shows in the written missiles.json (overlays: the row's definition file). With `work`, a
    pick's tint must have been made unless the run lacked D2R vfx files (hd_recolour.json `missing`)."""
    import re
    import effects_hd as e
    rep = {}
    if work is not None and (work / "hd_recolour.json").exists():
        rep = json.loads((work / "hd_recolour.json").read_text("utf-8"))
    tints = {r["to"]: r["from"] for r in rep.get("recolours", []) if r["kind"] == "missile"}
    mj = {}
    if work is not None and (work / "data" / "hd" / "missiles" / "missiles.json").exists():
        mj = json.loads((work / "data" / "hd" / "missiles" / "missiles.json").read_text("utf-8"))

    def base_of(effect: str) -> str:
        m = re.fullmatch(r"mxl_(.+)_s\d+", effect)
        return m.group(1) if m else effect

    def is_pick(kind: str, effect: str, hp: dict) -> bool:
        b = base_of(effect) if kind == "missile" else effect
        if b == hp["effect"]:
            return not (hp["tint"] and kind == "missile" and rep and not rep.get("missing"))  # asked tint not made
        return kind == "missile" and tints.get(b) == hp["effect"]

    bad = []
    for key, hp in picks.items():
        kind, art = key[0], key[1].replace(e.BS, "/")
        where = f"data/hd-effects-picks.tsv line {hp['line']} ({kind} {art}{' row ' + key[2] if len(key) > 2 else ''})"
        if len(key) > 2:
            if work is None:
                continue
            if kind == "missile":
                got = mj.get(e.norm_key(key[2]))
                if got is None:
                    bad.append(f"{where}: missiles.json has no row {key[2]}")
                elif not is_pick(kind, got, hp):
                    bad.append(f"{where}: missiles.json has {got}, not the pick {hp['effect']}")
            elif not list((work / "data" / "hd" / "overlays").glob(f"*/{e.norm_key(key[2])}.json")):
                bad.append(f"{where}: no overlay definition for the row")
            continue
        r = by_key.get((kind, art))
        if r is None or r["class"] in ("unreferenced", "no-art"):
            bad.append(f"{where}: no row draws this art")
        elif r["class"] == "exact":
            bad.append(f"{where}: D2R draws this art itself (exact); the pick is never used")
        elif r["class"] != "hand" or not is_pick(kind, r["effect"], hp):
            bad.append(f"{where}: table has {r['class']} {r['effect']}, not the pick {hp['effect']}"
                       + (f" tinted {hp['tint']}" if hp["tint"] else ""))
    return bad


def check_in_use(by_key: dict[tuple[str, str], dict], work: Path) -> list[str]:
    """Every missile / overlay row of the mod with an art file is D2R's own (same name and art) or its
    art is in the table with a decision; every decided missile row is keyed in the written missiles.json."""
    import effects_hd as e
    bad = []
    mj = json.loads((work / "data" / "hd" / "missiles" / "missiles.json").read_text("utf-8"))
    d2r_m = json.loads((e.HDM / "missiles.json").read_text("utf-8-sig"))
    for kind, table, namecol, artcol in (("missile", "missiles.txt", "Missile", "CelFile"),
                                         ("overlay", "overlay.txt", "overlay", "Filename")):
        _, d2r = e.table(fxpaths.D2R_EXCEL / table)
        d2r_art = {r[namecol].lower(): e.norm_art(r[artcol]) for r in d2r}
        _, mod = e.table(fxpaths.TABLES / table)
        for r in mod:
            name, art = r[namecol], e.norm_art(r[artcol])
            if not name or art in ("", "null"):
                continue
            # as effects_hd: D2R's own row (same name and art; a missile also needs D2R's HD model) keeps D2R's effect
            own = d2r_art.get(name.lower()) == art and (kind == "overlay" or e.norm_key(name) in d2r_m)
            if own:
                continue
            t = by_key.get((kind, art.replace(e.BS, "/")))
            if t is None:
                bad.append(f"{kind} row {name}: art {art} is in use but not in the table")
            elif t["class"] in DECIDED and kind == "missile" and e.norm_key(name) not in mj:
                bad.append(f"missile row {name}: art {art} is decided ({t['class']}) but missiles.json has no {e.norm_key(name)}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--no-provenance", action="store_true")
    ap.add_argument("--no-prior", action="store_true")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--groups", default="effects,monsters", help="art_provenance.py groups (effects is enough for this step)")
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    work = fxpaths.MOD
    if not args.check_only:
        if not args.no_provenance:
            subprocess.run([sys.executable, "-I", str(here / "art_provenance.py"), "--groups", args.groups], check=True)
        cmd = [sys.executable, "-I", str(here / "effects_hd.py")] + \
            (["--no-provenance"] if args.no_provenance else []) + (["--no-prior"] if args.no_prior else [])
        subprocess.run(cmd, check=True)
    bad = check(work, fxpaths.MAP_TSV)
    for b in bad:
        print("PROBLEM:", b)
    print(f"{len(bad)} problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
