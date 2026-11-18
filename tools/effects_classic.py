#!/usr/bin/env python
"""Build step: skills drawn in HD with Median's own classic animations (data/hd-effects-classic.json).

tools/effects_hd.py gives every missile row a D2R effect that looks alike. For the skills listed in the spec the mod plays
the classic animation itself instead: each missile of the skill gets a particle flipbook made from its DCC
(tools/effect_flipbook.py: Lanczos 2x, additive, the art's own colours) and the row's missiles.txt light.

  rows    before effects_hd.py: the spec's `rows` are added to work/mod's missiles.txt (both banks). A row there is a copy
          of a shared row (same art, same numbers: classic draws it exactly as before) that one missile of the skill makes
          instead of the shared one, so its HD picture can differ from the shared row's without touching any other skill.
  build   after missile_release.py: writes the textures, particle files and definitions under work/mod/data/hd and points
          the spec's rows at them in data/hd/missiles/missiles.json. Refuses when anything outside the spec's skills
          reaches one of the rows: nothing else may change its look.
  check   the same refusal and the files, without writing.

Spec: {"enabled": bool, "scale": 2, "method": "lanczos", "skills": [skills.txt names],
       "rows": {"<new row>": {"copy": "<row>", "at": [["<row>", "<column>"], ...]}},
       "missiles": {"<row>": {"name": "<definition>", "art": "missiles/<CelFile>", "mode": "loop"|"once",
                              "light": {"rgb": [r, g, b] (0..1), "range": world units, "power": n},
                              "parts": [{"ramp": "own"|"grey", "level": "mean"|"r"|"g"|"b", "tint": [r, g, b],
                                         "lift": world units (default: from the art's box)}]}}}
A missile without `art` is a light only. `enabled` false: every command does nothing and says so.

Usage: py -3 tools/effects_classic.py rows|build|check [--work DIR] [--spec FILE]
"""
import argparse
import json
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effect_flipbook as ef  # noqa: E402
import effects_hd as fx  # noqa: E402
import fxpaths  # noqa: E402
from missile_release import ITEM_TABLES, MONSTER_MISSILE_COLS  # noqa: E402
from txt_migrate import read_tsv, write_tsv  # noqa: E402

SPEC = fxpaths.ROOT / "data" / "hd-effects-classic.json"
MADE_COLS = fx.HIT_COLS + fx.SUB_COLS
GREY = np.dstack([np.arange(256)] * 3 + [np.full(256, 255)])[0].astype(np.uint8)
LIGHT_LIFT = 1.0  # world units over the missile's anchor: where the prototype's lights sat when they were measured


def load_spec(path: Path = SPEC) -> dict:
    spec = json.loads(Path(path).read_text("utf-8"))
    spec.setdefault("rows", {})
    spec.setdefault("missiles", {})
    spec.setdefault("skills", [])
    return spec


# ---------------------------------------------------------------- the tables
def add_rows(header: list[str], rows: list[list[str]], wanted: dict) -> list[str]:
    """Adds the spec's rows to a missiles.txt (in place). -> what was done, one line per row. A row that is there
    already (a second run) is only checked."""
    low = [h.lower() for h in header]
    name_at = low.index("missile")
    id_at = next((low.index(c) for c in ("*id", "id") if c in low), None)
    by_name = {r[name_at].lower(): r for r in rows if r and r[name_at]}
    done = []
    for new, how in wanted.items():
        src = by_name.get(how["copy"].lower())
        if src is None:
            raise SystemExit(f"effects_classic: no missiles.txt row {how['copy']!r} to copy for {new!r}")
        row = by_name.get(new.lower())
        if row is None:
            row = list(src)
            row[name_at] = new
            if id_at is not None:
                row[id_at] = str(len(rows))
            rows.append(row)
            by_name[new.lower()] = row
            done.append(f"{new}: copy of {how['copy']}")
        else:
            done.append(f"{new}: there already")
        differ = [header[k] for k in range(len(header)) if k not in (name_at, id_at) and row[k] != src[k]]
        if differ:
            raise SystemExit(f"effects_classic: row {new!r} is not a copy of {how['copy']!r}: {', '.join(differ)} differ")
        for owner, column in how["at"]:
            at = low.index(column.lower())
            user = by_name.get(owner.lower())
            if user is None:
                raise SystemExit(f"effects_classic: no missiles.txt row {owner!r}")
            if user[at].lower() not in (how["copy"].lower(), new.lower()):
                raise SystemExit(f"effects_classic: {owner}.{column} is {user[at]!r}, not {how['copy']!r}")
            user[at] = new
    return done


def confined(spec: dict, skills: list[dict], missiles: list[dict], monstats: list[dict], items: list[dict],
             states: list[dict]) -> list[str]:
    """Everything outside the spec's skills that reaches one of the spec's rows (empty: only those skills show them)."""
    ours = {m.lower() for m in spec["missiles"]}
    allowed = {s.lower() for s in spec["skills"]}
    bad = []
    for s in skills:
        if (s.get("skill") or "").lower() in allowed:
            continue
        bad += [f"skill {s.get('skill')}.{c} -> {s[c]}" for c in fx.SKILL_MISSILE_COLS if (s.get(c) or "").lower() in ours]
    for m in missiles:
        if m["Missile"].lower() in ours:
            continue
        bad += [f"missile {m['Missile']}.{c} -> {m[c]}" for c in MADE_COLS if (m.get(c) or "").lower() in ours]
    for m in monstats:
        bad += [f"monster {m.get('Id')}.{c} -> {m[c]}" for c in MONSTER_MISSILE_COLS if (m.get(c) or "").lower() in ours]
    for st in states:
        if (st.get("missile") or "").lower() in ours:
            bad.append(f"state {st.get('state')}.missile -> {st['missile']}")
    ids = {r.get("*ID") or str(i): r["Missile"].lower() for i, r in enumerate(missiles)}
    for it in items:
        mt = it.get("missiletype", "")
        if mt and mt != "0" and ids.get(mt) in ours:
            bad.append(f"item {it.get('code')}.missiletype -> {ids[mt]}")
    return bad


def problems(spec: dict, excel: Path) -> list[str]:
    """Why the spec cannot be built over the tables in `excel` (empty: it can)."""
    opt = lambda t: fx.table(excel / t)[1] if (excel / t).exists() else []  # noqa: E731
    missiles = fx.table(excel / "missiles.txt")[1]
    by_name = {r["Missile"].lower(): r for r in missiles}
    bad = [f"no missiles.txt row {m}" for m in spec["missiles"] if m.lower() not in by_name]
    for m, how in spec["missiles"].items():
        row = by_name.get(m.lower())
        if row and how.get("art"):
            cel = (row.get("CelFile") or "").lower()
            if cel != how["art"].split("/")[-1].lower():
                bad.append(f"{m}: the row's CelFile is {cel!r}, the spec draws {how['art']!r}")
            if row.get("Trans") != "1":
                bad.append(f"{m}: Trans is {row.get('Trans')!r}; a flipbook is additive (Trans 1)")
    skills = opt("skills.txt")
    known = {(s.get("skill") or "").lower() for s in skills}
    bad += [f"no skills.txt row {s!r}" for s in spec["skills"] if s.lower() not in known]
    items = [r for t in ITEM_TABLES for r in opt(f"{t}.txt")]
    return bad + confined(spec, skills, missiles, opt("monstats.txt"), items, opt("states.txt"))


# ---------------------------------------------------------------- the effects
def build_missile(out: Path, how: dict, scale: int, method: str, templates: dict | None = None) -> dict:
    """One row's effect under `out` (laid out like the mod's data folder): a layer per part, the light, ONE definition.
    -> {'name', 'files' ('data/...' paths), 'bytes', 'deflated'}."""
    templates = templates or {}
    name = how["name"]
    parts, files = [], []
    layers = how.get("parts", [])
    for k, p in enumerate(layers):
        layer = name if len(layers) == 1 else "%s_%s" % (name, p.get("level", str(k)))
        ramp = GREY if p.get("ramp") == "grey" else p.get("ramp", "own")
        f = ef.build(out, layer, how["art"], how["mode"], scale, method, size=ef.SIZE_FIT, lift=p.get("lift"),
                     template=templates.get("flipbook"), kind="index", ramp=ramp, level=p.get("level", "mean"),
                     tint=tuple(p.get("tint", (1.0, 1.0, 1.0))), write_definition=False)
        parts.append({"particle": f["files"][1], "texture": f["files"][0], "pos": (0.0, f["lift_world"], 0.0)})
        files += f["files"]
    if how.get("light"):
        lamp = how["light"]
        path = ef.PARTICLE_DIR + name.lower() + "_light.particles"
        dest = out / path[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        template = templates.get("light") or fxpaths.d2r_file(ef.LIGHT_TEMPLATE).read_bytes()
        dest.write_bytes(ef.point_light(template, lamp["rgb"], lamp["range"], lamp.get("power", 250.0)))
        parts.append({"particle": path, "texture": None, "pos": (0.0, LIGHT_LIFT, 0.0), "hard_kill": True})
        files.append(path)
    if not parts:
        raise SystemExit(f"effects_classic: {name} has neither a picture nor a light")
    fx.write_json(out / "hd" / "missiles" / (name + ".json"), ef.definition(name, parts, how.get("mode") == "loop"))
    files.append("data/hd/missiles/%s.json" % name)
    raw = [(out / f[len("data/"):]).read_bytes() for f in files]
    return {"name": name, "files": files, "bytes": sum(map(len, raw)), "deflated": sum(len(zlib.compress(r, 9)) for r in raw)}


def build(spec: dict, out: Path, templates: dict | None = None) -> dict:
    """Every effect of the spec under `out` and the rows pointed at them in out/hd/missiles/missiles.json. -> facts."""
    mj = out / "hd" / "missiles" / "missiles.json"
    table = fx.load_json(mj)
    facts = {}
    for row, how in spec["missiles"].items():
        facts[row] = build_missile(out, how, spec.get("scale", 2), spec.get("method", "lanczos"), templates)
        facts[row]["was"] = table.get(row.lower())          # what the steps before chose: the row's look with this switched off
        table[fx.norm_key(row)] = how["name"]
        table[row.lower()] = how["name"]
    fx.write_json(mj, table)
    return facts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("rows", "build", "check"))
    ap.add_argument("--work", default=str(fxpaths.MOD))
    ap.add_argument("--spec", default=str(SPEC))
    args = ap.parse_args(argv)
    spec, work = load_spec(Path(args.spec)), Path(args.work)
    excel = work / "data" / "global" / "excel"
    if not spec.get("enabled", True):
        print("effects_classic: switched off in %s, nothing to do" % Path(args.spec).name)
        return 0
    if args.cmd == "rows":
        for bank in ("base", ""):
            p = excel / bank / "missiles.txt"
            if not p.exists():
                continue
            header, rows = read_tsv(p)
            done = add_rows(header, rows, spec["rows"])
            write_tsv(p, header, rows)
            print("effects_classic rows (%s): %s" % (bank or "top", "; ".join(done) or "none"))
        return 0
    bad = problems(spec, excel)
    if bad:
        print("effects_classic: the spec does not fit the tables:\n  " + "\n  ".join(bad))
        return 1
    out = work / "data"
    if args.cmd == "check":
        table = fx.load_json(out / "hd" / "missiles" / "missiles.json")
        for row, how in spec["missiles"].items():
            if table.get(fx.norm_key(row)) != how["name"] or table.get(row.lower()) != how["name"]:
                bad.append(f"{row} is drawn by {table.get(row.lower())!r}, not {how['name']!r}")
            d = out / "hd" / "missiles" / (how["name"] + ".json")
            if not d.exists():
                bad.append(f"{d} is missing")
                continue
            deps = fx.load_json(d)["dependencies"]
            bad += [f"{how['name']}: {q['path']} is missing" for kind in ("particles", "textures") for q in deps[kind]
                    if not (out / q["path"][len("data/"):]).exists()]
        print("effects_classic check: " + ("\n  ".join(bad) if bad else "%d rows drawn by their classic animation" % len(spec["missiles"])))
        return 1 if bad else 0
    facts = build(spec, out)
    (work / "effects_classic.json").write_text(json.dumps(facts, indent=1), "utf-8")
    total, packed = sum(f["bytes"] for f in facts.values()), sum(f["deflated"] for f in facts.values())
    print("effects_classic: %d rows of %s drawn by their classic animation, %d files, %d bytes (%d deflated)"
          % (len(facts), ", ".join(spec["skills"]), sum(len(f["files"]) for f in facts.values()), total, packed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
