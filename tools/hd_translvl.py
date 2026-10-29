#!/usr/bin/env python
"""Per-TransLvl recolours of HD monsters: the classic palette shift of a monster level, as an entry of its HD variant table.

Classic Diablo II recolours the monsters of one art token per level: the token's `palshift.dat`
(data/global/monsters/<token>/cof/palshift.dat) holds 8 tables of 256 palette indices, and a monster of TransLvl t draws
through table t + 2 (tables 0 and 1 are the cold and poison tints; seen in game: Median's quillbear4, TransLvl 3, draws
black = table 5, quillbear5 purple = table 6). D2R's HD renderer has the same layout in the unit's VariantTransformTable
(data/hd/character/enemy/<unit>/<unit>_variant.json): 8 entries `cold`, `poison`, `level0` .. `level4`, `misc`, entry t + 2
for TransLvl t (fallen1..fallen5 share the unit fallen1 and differ only there). Each entry holds 3 ColorTransforms (the red, green and blue mask regions of the model) with
colorAdjustment (hue turn, saturation, value, 1) and colorTint (r, g, b, amount), the fields tools/hd_donors.py tint_of
fills for the stand-in units.

D2R authored the entries only for the levels its own monsters use. Median XL 2012 puts monsters on other levels of the same
tokens; an entry D2R left as identity then draws the level-0 colours in HD while the classic client shifts them. This step:

  - takes every monstats Id of the build (both banks) that draws a D2R HD unit (work/mod/data/hd/character/monsters.json,
    not one of hd_monsters.py's mxl_* stand-ins) with TransLvl 1..5,
  - keeps the (unit, level) pairs whose entry is identity and whose classic token has a palshift.dat,
  - measures the classic art (frame 0 of mode NU of the monster's looks, the build's monstats2 row) without and with the
    level's palette shift, and turns the difference into a colour transform (hd_donors.tint_of, quantised),
  - writes the unit's variant table with those entries filled to work/mod/data/hd/character/enemy/<unit>/<unit>_variant.json
    (the mod's copy shadows D2R's), never larger than D2R's file.

Levels D2R itself uses and left identity (Quill Rats, Wisps, Zakarum clerics ...: D2R draws all their levels alike in HD,
classic does not) are filled as well, Median's classic look first; --keep-d2r-levels leaves them as D2R has them. A shift
below hd_donors.tint_of's threshold is no recolour. Stand-in units (mxl_*) draw Median's own
tokens, which ship no palshift.dat: classic draws them in one colour, as the stand-in does (docs/hd-monsters.md).

  py -3 -I tools/hd_translvl.py plan     report only (work/mod/hd_translvl.md)
  py -3 -I tools/hd_translvl.py build    report + the variant tables (tools/build.py runs this after hd_monsters.py build)
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402  (D2R baseline, Median's extracted MPQ, work/mod)
import hd_donors as hd  # noqa: E402

LEVEL0 = 2      # entry index of TransLvl 0 (after cold, poison)
ENTRIES = 8
MAX_LEVEL = ENTRIES - 1 - LEVEL0   # TransLvl 5 -> entry 7 (`misc`); 6 and 7 have no entry
ZERO4 = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0}


# ------------------------------------------------------------------ tables
def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="latin-1", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return [dict(zip(rows[0], r)) for r in rows[1:] if r and r[0] and r[0] != "Expansion"]


def enabled(r: dict) -> bool:
    """A row the game spawns (monstats `enabled` 1; a table without the column counts as enabled)."""
    return r.get("enabled", "1") == "1"


def bank_dirs(excel: Path) -> list[Path]:
    return [d for d in (excel, excel / "base") if (d / "monstats.txt").exists()]


# ------------------------------------------------------------------ variant tables
def is_identity(t: dict) -> bool:
    adj, tint = t.get("colorAdjustment", {}), t.get("colorTint", {})
    if any(abs(adj.get(k, 0.0) - (1.0 if k == "w" else 0.0)) > 1e-6 for k in "xyzw"):
        return False
    if any(abs(t.get(f, ZERO4).get(k, 0.0)) > 1e-6 for f in ("hueAdjustment0", "hueAdjustment1", "satAdjustment0",
                                                              "satAdjustment1") for k in "xyzw"):
        return False
    return abs(tint.get("w", 0.0)) <= 1e-6


def entry_identity(e: dict) -> bool:
    return all(is_identity(t) for t in e.get("transforms", []))


def fill_entry(e: dict, base: dict, adj: list, tint: list) -> dict:
    """Entry e with every transform set to the shift (adj, tint) on top of the level-0 entry's transform `base` of the
    same mask (hue turns add, saturation and value add and clip, the shift's tint wins when it has one). Values are
    rounded to 2 decimals, the copied level-0 ones too (keeps the table within D2R's file size)."""
    out = json.loads(json.dumps(e))
    for i, t in enumerate(out["transforms"]):
        b = base["transforms"][i] if i < len(base.get("transforms", [])) else t
        ba, bt = b["colorAdjustment"], b["colorTint"]
        t["colorAdjustment"] = {"x": rnd((ba["x"] + adj[0]) % 1.0), "y": rnd(clip(ba["y"] + adj[1])),
                                "z": rnd(clip(ba["z"] + adj[2])), "w": rnd(ba["w"])}
        t["colorTint"] = dict(zip("xyzw", map(rnd, tint if tint[3] else [bt[k] for k in "xyzw"])))
        for f in ("hueAdjustment0", "hueAdjustment1", "satAdjustment0", "satAdjustment1"):
            t[f] = {k: rnd(v) for k, v in b.get(f, ZERO4).items()}
    return out


def clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


def rnd(x: float) -> float:
    return round(float(x), 2) + 0.0


def dump(d: dict) -> bytes:
    return json.dumps(d, separators=(",", ":")).encode("utf-8")


def fit(table: dict, filled: list[int], limit: int) -> bytes | None:
    """The table as compact json no larger than `limit` bytes: as it is, else with short names on the filled entries'
    transforms (the engine finds a table by its file path; our own stand-in tables use free names too), else also with
    their values rounded to 1 decimal, else None."""
    data = dump(table)
    if len(data) <= limit:
        return data
    for i in filled:
        for j, t in enumerate(table["entries"][i]["transforms"]):
            t["name"] = f"L{i - LEVEL0}{'RGB'[j] if j < 3 else j}"
    data = dump(table)
    if len(data) <= limit:
        return data
    for i in filled:
        for t in table["entries"][i]["transforms"]:
            for f, v in t.items():
                if isinstance(v, dict):
                    t[f] = {k: round(x, 1) + 0.0 for k, x in v.items()}
    data = dump(table)
    return data if len(data) <= limit else None


# ------------------------------------------------------------------ classic art
class ClassicArt(hd.Art):
    """hd_donors.Art reading the build's classic monster art: Median's file when it ships one, else D2R's."""

    def __init__(self, roots: list[Path]):
        super().__init__()
        self.roots = [r for r in roots if r and r.exists()]
        self._idx: dict[tuple[int, str], dict[str, Path]] = {}

    def read(self, side: str, rel: str) -> bytes | None:
        d, _, f = rel.rpartition("/")
        for n, root in enumerate(self.roots):
            key = (n, d.lower())
            if key not in self._idx:
                base = root / d
                self._idx[key] = {x.name.lower(): x for x in base.iterdir()} if base.is_dir() else {}
            p = self._idx[key].get(f.lower())
            if p:
                return p.read_bytes()
        return None


def palshift_of(d2r_monsters: Path, token: str) -> list[list[int]] | None:
    p = d2r_monsters / token / "cof" / "palshift.dat"
    if not p.exists():
        return None
    b = p.read_bytes()
    return [list(b[i * 256:(i + 1) * 256]) for i in range(8)] if len(b) >= 2048 else None


def level_shift(hist: list[int], pal, shift: list[int], base_shift: list[int] | None = None) -> tuple[list, list, str]:
    """(colorAdjustment, colorTint, label) turning the classic colour of level 0 (palette through `base_shift`, palshift
    table 2) into the level's (through `shift`); label 'none' when the change is below hd_donors.tint_of's threshold."""
    base = hd.colour_stats(hist, pal, base_shift)
    shifted = hd.colour_stats(hist, pal, shift)
    adj, tint, label = hd.tint_of(shifted, base)
    if label == "none":
        return [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0], "none"
    adj = [hd.q(adj[0], 0.02) % 1.0, hd.q(adj[1], 0.05), hd.q(adj[2], 0.05), 1.0]
    tint = [hd.q(t, 0.1) for t in tint[:3]] + [hd.q(tint[3], 0.05)]
    return adj, tint, label


# ------------------------------------------------------------------ plan
def plan(excel: Path, mj: dict, d2r: Path, keep_d2r_levels: bool = False) -> dict:
    """{unit: {level: {...}}} of the (unit, TransLvl) pairs the build's monsters use, with what is done about each."""
    d2r_excel = d2r / "data" / "global" / "excel"
    dmj = json.loads((d2r / "data" / "hd" / "character" / "monsters.json").read_text("utf-8-sig"))
    d2r_levels: dict[str, set[int]] = defaultdict(set)
    for r in read_rows(d2r_excel / "monstats.txt"):
        if r["Id"] in dmj:
            d2r_levels[dmj[r["Id"]]].add(int(r.get("TransLvl") or 0))
    uses: dict[tuple[str, int], dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for bank in bank_dirs(excel):
        for r in read_rows(bank / "monstats.txt"):
            u, tl = mj.get(r["Id"], ""), int(r.get("TransLvl") or 0)
            if not u or u.startswith("mxl_") or not tl or not r.get("Code") or not enabled(r):
                continue
            ids = uses[(u, tl)][r["Code"].lower()]
            if (r["Id"], r.get("MonStatsEx", "")) not in ids:
                ids.append((r["Id"], r.get("MonStatsEx", "")))
    out: dict[str, dict] = defaultdict(dict)
    for (u, tl), toks in sorted(uses.items()):
        vp = d2r / "data" / "hd" / "character" / "enemy" / u / f"{u}_variant.json"
        tok = max(toks, key=lambda t: (len(toks[t]), t))
        e = {"token": tok, "ids": [i for i, _ in toks[tok]], "rows2": [x for _, x in toks[tok]],
             "other_tokens": sorted(t for t in toks if t != tok), "d2r_uses": tl in d2r_levels.get(u, set())}
        if tl > MAX_LEVEL:
            e["state"] = "no entry"       # TransLvl 6, 7: the table has 8 entries
        elif not vp.exists():
            e["state"] = "no variant table"
        else:
            v = json.loads(vp.read_text("utf-8-sig"))
            if len(v.get("entries", [])) != ENTRIES:
                e["state"] = "table layout"
            elif not entry_identity(v["entries"][tl + LEVEL0]):
                e["state"] = "D2R colour"   # D2R authored the level
            elif not (d2r / "data" / "global" / "monsters" / tok / "cof" / "palshift.dat").exists():
                e["state"] = "no palshift"  # classic draws the level unshifted too
            elif e["d2r_uses"] and keep_d2r_levels:
                e["state"] = "D2R identity"  # D2R's own monster of that level: D2R's HD look
            else:
                e["state"] = "fill"
        out[u][tl] = e
    return out


def measure(p: dict, excel: Path, d2r: Path, mxl_monsters: Path | None) -> None:
    """Adds adj / tint / label to every `fill` entry of the plan (its state becomes `below threshold` when the shift
    is too small, `no art` when the classic art is missing)."""
    rows2: dict[str, dict] = {}
    for bank in bank_dirs(excel):
        for r in read_rows(bank / "monstats2.txt"):
            rows2.setdefault(r["Id"], r)
    d2r_mon = d2r / "data" / "global" / "monsters"
    art = ClassicArt([mxl_monsters, d2r_mon])
    for u, levels in p.items():
        for tl, e in levels.items():
            if e["state"] != "fill":
                continue
            hist = [0] * 256
            for r2id in dict.fromkeys(e["rows2"]):
                r2 = rows2.get(r2id)
                st = art.stats("d2r", e["token"], r2, r2.get("BaseW") or "hth") if r2 else None
                if st:
                    hist = [a + b for a, b in zip(hist, st["hist"])]
            shifts = palshift_of(d2r_mon, e["token"])
            if not sum(hist) or not shifts:
                e["state"] = "no art"
                continue
            adj, tint, label = level_shift(hist, art.pal, shifts[tl + LEVEL0], shifts[LEVEL0])
            e.update(adj=adj, tint=tint, label=label)
            if label == "none":
                e["state"] = "below threshold"


def build_tables(p: dict, d2r: Path, out: Path) -> dict[str, tuple[int, int, list[int]]]:
    """Writes the filled variant tables; {unit: (D2R size, our size, filled levels)}. A table that cannot be kept within
    D2R's size is not written and its levels become `too large`. The tables of an earlier run are deleted first (only this
    step writes <unit>/<unit>_variant.json; hd_monsters.py writes under enemy/mxl/)."""
    enemy = out / "hd" / "character" / "enemy"
    for d in (enemy.iterdir() if enemy.is_dir() else ()):
        if d.is_dir() and d.name != "mxl" and (d / f"{d.name}_variant.json").is_file():
            (d / f"{d.name}_variant.json").unlink()
    done = {}
    for u, levels in sorted(p.items()):
        todo = {tl: e for tl, e in levels.items() if e["state"] == "fill"}
        if not todo:
            continue
        rel = Path("hd") / "character" / "enemy" / u / f"{u}_variant.json"
        src = d2r / "data" / rel
        v = json.loads(src.read_text("utf-8-sig"))
        base = v["entries"][LEVEL0]
        for tl, e in todo.items():
            v["entries"][tl + LEVEL0] = fill_entry(v["entries"][tl + LEVEL0], base, e["adj"], e["tint"])
        limit = src.stat().st_size
        data = fit(v, [tl + LEVEL0 for tl in todo], limit)
        if data is None:
            for e in todo.values():
                e["state"] = "too large"
            continue
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(data)
        for e in todo.values():
            e["state"] = "filled"
        done[u] = (limit, len(data), sorted(todo))
    return done


def report(p: dict, done: dict) -> str:
    states = Counter(e["state"] for lv in p.values() for e in lv.values())
    ids = Counter()
    for lv in p.values():
        for e in lv.values():
            ids[e["state"]] += len(e["ids"])
    size = sum(b for _, b, _ in done.values())
    lines = ["# Per-TransLvl recolours of HD monsters (tools/hd_translvl.py)", "",
             "(unit, TransLvl) pairs of the build's monsters on D2R HD units, TransLvl 1 and up. States: `filled` = the level's "
             "classic palette shift written into the unit's variant table; `D2R colour` = D2R authored the level; `D2R identity` = "
             "D2R's own monsters of that level draw the level-0 colours in HD too (kept with --keep-d2r-levels); `no palshift` = the token has no "
             "palshift.dat, classic draws the level unshifted; `below threshold` = the shift is too small to show; `no entry` = "
             "TransLvl 6 / 7 (the table has 8 entries); `no variant table`, `no art`, `too large` (would exceed D2R's file).", "",
             "| State | Pairs | Ids |", "|---|---:|---:|"]
    lines += [f"| {s} | {n} | {ids[s]} |" for s, n in sorted(states.items())]
    lines += ["", f"{len(done)} variant tables written, {size} bytes (each no larger than D2R's file of the same path).", "",
              "| Unit | TransLvl | Token | State | Shift | Ids |", "|---|---:|---|---|---|---|"]
    for u, lv in sorted(p.items()):
        for tl, e in sorted(lv.items()):
            if e["state"] in ("D2R colour", "no palshift"):
                continue
            ids_ = ", ".join(e["ids"][:6]) + (f" (+{len(e['ids']) - 6})" if len(e["ids"]) > 6 else "")
            lines.append(f"| {u} | {tl} | `{e['token']}` | {e['state']} | {e.get('label', '')} | {ids_} |")
    return "\n".join(lines) + "\n"


def summary(p: dict, excel: Path, mj: dict) -> dict:
    """work/mod/hd_translvl.json: per unit with a filled level, a TransLvl-0 Id of the unit (for a side-by-side look) and
    the filled levels with their Ids and shifts (read by tools/game_checks.py check tint_hd)."""
    level0: dict[str, str] = {}
    for bank in bank_dirs(excel):
        for r in read_rows(bank / "monstats.txt"):
            u = mj.get(r["Id"], "")
            if u and not int(r.get("TransLvl") or 0) and enabled(r):
                level0.setdefault(u, r["Id"])
    out = {}
    for u, lv in sorted(p.items()):
        filled = {str(tl): {"ids": e["ids"], "token": e["token"], "shift": e.get("label", "")}
                  for tl, e in sorted(lv.items()) if e["state"] == "filled"}
        if filled:
            out[u] = {"level0": level0.get(u), "levels": filled}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["plan", "build"])
    ap.add_argument("--mod", default=str(fxpaths.MOD), help="work/mod (data/global/excel, data/hd/character/monsters.json)")
    ap.add_argument("--d2r", default=str(fxpaths.D2R), help="D2R 93847 baseline extract")
    ap.add_argument("--median-monsters", default=str(fxpaths.MXL / "monsters"))
    ap.add_argument("--keep-d2r-levels", action="store_true", help="leave the levels D2R uses and left identity as they are")
    a = ap.parse_args()
    mod, d2r = Path(a.mod), Path(a.d2r)
    excel = mod / "data" / "global" / "excel"
    mjp = mod / "data" / "hd" / "character" / "monsters.json"
    if not mjp.exists():
        print(f"{mjp} missing: run tools/hd_monsters.py build first")
        return 1
    hd.configure(Path(a.median_monsters), d2r)
    p = plan(excel, json.loads(mjp.read_text("utf-8")), d2r, a.keep_d2r_levels)
    measure(p, excel, d2r, Path(a.median_monsters))
    done = build_tables(p, d2r, mod / "data") if a.cmd == "build" else {}
    (mod / "hd_translvl.md").write_text(report(p, done), encoding="utf-8")
    (mod / "hd_translvl.json").write_text(json.dumps(summary(p, excel, json.loads(mjp.read_text("utf-8"))), indent=1),
                                          encoding="utf-8")
    st = Counter(e["state"] for lv in p.values() for e in lv.values())
    print(f"{dict(st)}; {len(done)} variant tables, {sum(b for _, b, _ in done.values())} bytes -> {mod / 'hd_translvl.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
