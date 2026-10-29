"""Object ids in Median XL 2012's maps and the automap (lane objstr; data step after txt_migrate.py).

Median 2012 is a 1.13c data mod: its maps name an object as (act, id) and the engine resolves that through ObjPreset to an
Objects row; the automap is drawn from AutoMap rows per level type. Neither table is shipped (no objpreset / automap in
`patch_d2.mpq`), so 1.13c used its own, and D2R's per-act `objpreset.txt` / `automap.txt` are those tables plus D2R's additions.
This step proves that the D2R tables, together with the mod's built tables, give the same result, and writes what the
installer needs (docs/id-mapping.md "Objects and ObjPreset", docs/maps-hd.md):

  1. work/mod/ds1_ids.json    the monster id table of tools/ds1_remap.py (install_mod.py renumbers the maps from it)
  2. objects  every type-2 object (act, id) of the original .ds1 files must be an index of D2R's ObjPreset for that act, its
              ObjectClass must name one Objects row of the built table (case-insensitive, like D2R), that row is the mod's
              row of the same position (same Name), and no Objects row of the mod moved (ObjPreset names rows by D2R's ids)
  3. automap  the mod ships no automap table; every level type of the built lvltypes.txt has the name and position of D2R's
              (so each finds its AutoMap rows by name), the built objects.txt keeps the mod's AutoMap cel of every row
  4. work/mod/objstr_report.md  the result; exit code 1 on a PROBLEM

  py -3 -I tools/objstr.py [--mod EXCEL] [--built EXCEL] [--d2r EXCEL] [--tiles DIR] [--out DIR]
"""
import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds1_remap  # noqa: E402
import idmap  # noqa: E402
import strings_ns  # noqa: E402

MAX_AUTOMAP_CEL = 1498          # D2R's automap atlas has 1499 cels (a known engine limit)


def table(path: Path):
    """(header, records) of a tab file, or None."""
    if not path.exists():
        return None
    h, rows = idmap.read_tsv(path)
    return h, idmap.records(rows)


def objects_by_class(h: list[str], recs: list[list[str]]):
    """lower-cased Class -> record index, and the duplicate classes."""
    ci = h.index("Class")
    by, dup = {}, []
    for i, r in enumerate(recs):
        c = r[ci].strip().lower()
        if not c:
            continue
        if c in by:
            dup.append(c)
        by.setdefault(c, i)
    return by, dup


def preset_classes(h: list[str], recs: list[list[str]]) -> dict:
    """act (1-based) -> {Index: ObjectClass} of D2R's objpreset.txt."""
    ia, ii, ic = h.index("Act"), h.index("Index"), h.index("ObjectClass")
    out: dict = {}
    for r in recs:
        if r[ia].isdigit() and r[ii].lstrip("-").isdigit():
            out.setdefault(int(r[ia]), {})[int(r[ii])] = r[ic]
    return out


def ds1_objects(tiles: Path) -> collections.Counter:
    """(file, act 1-based, id) -> count of the type-2 objects of every .ds1 under `tiles`."""
    n: collections.Counter = collections.Counter()
    for p in sorted(Path(tiles).rglob("*.ds1")):
        ds = ds1_remap.Ds1(p.read_bytes())
        for t, i, *_ in ds.objects:
            if t == 2:
                n[(p.relative_to(tiles).as_posix(), ds.act + 1, i)] += 1
    return n


def check_objects(used, presets: dict, built_objects, mod_objects, moved) -> tuple[list[str], list[str], dict]:
    """-> (problems, notes, stats). used: Counter (file, act, id); presets: act -> {Index: class}; built_objects /
    mod_objects: (header, records) of the built and the original objects.txt."""
    problems, notes = [], []
    if moved:
        problems.append(f"objects rows that change id ({len(moved)}): ObjPreset names rows by D2R's ids, e.g. {moved[:5]}")
    bh, brecs = built_objects
    by_class, dup = objects_by_class(bh, brecs)
    if dup:
        problems.append(f"built objects.txt: Class used by several rows (D2R resolves by name, the first wins): {sorted(set(dup))[:8]}")
    mh, mrecs = mod_objects
    bn, mn = bh.index("Name"), mh.index("Name")
    # (a name no .tbl defines is a mxl2012 string of its own text in the built table: tools/string_gaps.py)
    renamed = [i for i in range(min(len(mrecs), len(brecs)))
               if strings_ns.bare(brecs[i][bn]) != mrecs[i][mn] and not brecs[i][bn].startswith(strings_ns.ALIAS_PREFIX)]
    if renamed:
        problems.append(f"built objects.txt: Name differs from the mod's in rows {renamed[:8]}")
    stats = {"objects": sum(used.values()), "distinct": len({(a, i) for _f, a, i in used}), "missing_slot": 0, "no_class": 0,
             "d2r_only_row": 0}
    seen = set()
    for (f, act, i), n in sorted(used.items()):
        if (act, i) in seen:
            continue
        cls = presets.get(act, {}).get(i)
        if cls is None:
            seen.add((act, i))
            stats["missing_slot"] += 1
            problems.append(f"{f}: object id {i} (act {act}) has no row in D2R's ObjPreset: the object is not placed")
            continue
        row = by_class.get(cls.strip().lower())
        if row is None:
            seen.add((act, i))
            stats["no_class"] += 1
            problems.append(f"{f}: object id {i} (act {act}) -> ObjectClass {cls!r}, no Objects row of the built table has that Class")
        elif row >= len(mrecs):
            stats["d2r_only_row"] += 1
            notes.append(f"act {act} id {i} -> {cls!r} -> row {row}, a row only D2R has")
        seen.add((act, i))
    return problems, notes, stats


def norm_type_name(name: str) -> str:
    """lvltypes 'Act 1 - Town' -> '1 Town' (the form of AutoMap.txt's LevelName; 'Act 5 - Ice Caves' -> '5 Ice Caves')."""
    n = name.strip()
    if n.lower().startswith("act "):
        n = n[4:].replace(" - ", " ")
    return n


def check_automap(src_dir: Path, built_dir: Path, d2r_dir: Path, mod_objects, built_objects) -> tuple[list[str], list[str]]:
    """-> (problems, notes)."""
    problems, notes = [], []
    shipped = [p.name for n in ("automap", "objpreset") for p in src_dir.glob(f"{n}.*")]
    if shipped:
        problems.append(f"the mod ships {shipped}: Median's own table has to be merged into D2R's, not replaced by it")
    else:
        notes.append("the mod ships no automap and no objpreset table (patch_d2.mpq): 1.13c used its own, D2R's are those plus "
                     "D2R's additions, so D2R's stay")
    for n in ("automap", "objpreset"):
        if (built_dir / f"{n}.txt").exists():
            problems.append(f"the built excel folder has a {n}.txt: it would replace D2R's table")
    lt_mod, lt_d2r = table(built_dir / "lvltypes.txt"), table(d2r_dir / "lvltypes.txt")
    am = table(d2r_dir / "automap.txt")
    if lt_mod and lt_d2r and am:
        mn, dn = [r[0] for r in lt_mod[1]], [r[0] for r in lt_d2r[1]]
        if mn[:len(dn)] != dn or len(mn) > len(dn):
            problems.append(f"built lvltypes.txt names differ from D2R's (level types are static in D2R, AutoMap finds its rows "
                            f"by name): {[(a, b) for a, b in zip(mn, dn) if a != b][:5]}, {len(mn)} vs {len(dn)} rows")
        names = {r[0] for r in am[1]}
        lone = [n for n in dn if n not in ("None", "Expansion")
                and not any(norm_type_name(n).startswith(x) for x in names)]
        if lone:
            notes.append(f"level types with no AutoMap row in D2R's table (nothing for the port to merge): {lone}")
        notes.append(f"{len(mn)} level types, the same names and order as D2R's; AutoMap.txt has {len(am[1])} rows for "
                     f"{len(names)} level names")
    mh, mrecs = mod_objects
    bh, brecs = built_objects
    if "AutoMap" in mh and "AutoMap" in bh:
        ma, ba = mh.index("AutoMap"), bh.index("AutoMap")
        diff = [i for i in range(min(len(mrecs), len(brecs))) if mrecs[i][ma] != brecs[i][ba]]
        if diff:
            problems.append(f"built objects.txt AutoMap differs from the mod's in rows {diff[:8]}")
        cels = [int(r[ba]) for r in brecs if r[ba].lstrip("-").isdigit()]
        if cels and max(cels) > MAX_AUTOMAP_CEL:
            problems.append(f"objects.txt AutoMap cel {max(cels)} is above D2R's atlas ({MAX_AUTOMAP_CEL})")
        else:
            notes.append(f"objects.txt AutoMap: the mod's cel in all {min(len(mrecs), len(brecs))} shared rows, highest cel {max(cels or [0])}")
    return problems, notes


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mod", help="the original mod's data/global/excel (default: the MPQ extract)")
    ap.add_argument("--built", help="the built data/global/excel (default: work/mod)")
    ap.add_argument("--d2r", help="D2R's excel folder with base/ (default as tools/idmap.py finds it)")
    ap.add_argument("--tiles", help="the original mod's data/global/tiles (default: the MPQ extract)")
    ap.add_argument("--out", help="folder for ds1_ids.json and objstr_report.md (default: work/mod)")
    a = ap.parse_args(argv)
    import maps_hd
    extract = maps_hd.default_extract()
    mod = Path(a.mod) if a.mod else extract / "data" / "global" / "excel"
    built = Path(a.built) if a.built else ROOT / "work" / "mod" / "data" / "global" / "excel"
    out = Path(a.out) if a.out else ROOT / "work" / "mod"
    d2r = idmap.find_d2r(a.d2r)
    if d2r is None:
        raise SystemExit("no D2R excel folder with base/skills.txt (--d2r or MXL2012_D2R_EXCEL)")
    tiles = Path(a.tiles) if a.tiles else extract / "data" / "global" / "tiles"

    maps = ds1_remap.Maps.build(mod, d2r, built / "base")
    ids = maps.to_json()
    out.mkdir(parents=True, exist_ok=True)
    (out / "ds1_ids.json").write_text(json.dumps(ids, indent=0), encoding="utf-8")

    problems: list[str] = []
    notes: list[str] = []
    lines = ["# objstr report (objects and automap of the maps, tools/objstr.py)", ""]
    mod_objects = table(mod / "objects.txt")
    for bank, bdir, ddir in (("base", built / "base", d2r / "base"), ("rotw", built, d2r)):
        bobj, op = table(bdir / "objects.txt"), table(ddir / "objpreset.txt")
        if bobj is None or op is None or mod_objects is None:
            problems.append(f"{bank}: objects.txt / objpreset.txt missing (built {bdir}, D2R {ddir})")
            continue
        lines.append(f"## {bank} bank")
        if tiles.exists() and any(tiles.rglob("*.ds1")):
            used = ds1_objects(tiles)
            p, n, st = check_objects(used, preset_classes(*op), bobj, mod_objects, maps.moved_objects())
            problems += [f"{bank}: {x}" for x in p]
            notes += [f"{bank}: {x}" for x in n]
            lines.append(f"- {st['objects']} type-2 objects in {len({f for f, _a, _i in used})} maps, {st['distinct']} distinct "
                         f"(act, id): {st['missing_slot']} without an ObjPreset row, {st['no_class']} with a class no Objects row "
                         f"has, {st['d2r_only_row']} on a row only D2R has")
        else:
            notes.append(f"{bank}: no .ds1 files under {tiles}: object ids not checked against the maps")
        p, n = check_automap(mod, bdir, ddir, mod_objects, bobj)
        problems += [f"{bank}: {x}" for x in p]
        notes += [f"{bank}: {x}" for x in n]
    sup = maps.shifted_superuniques()
    lines += ["", "## ids written for the installer", "",
              f"- ds1_ids.json: {len(ids['monster'])} monstats rows, {sum(1 for r, n in ids['monster'].items() if int(r) != n)} "
              f"change id; MonPreset rows per act {ids['presets']}; objects that move: {len(maps.moved_objects())}",
              f"- superuniques from row 43 up sit one id above vanilla ({len(sup)} rows): no .ds1 holds a superunique id"]
    lines += ["", "## Notes", ""] + [f"- {n}" for n in dict.fromkeys(notes)]
    lines += ["", "## Problems", ""] + ([f"- PROBLEM {p}" for p in problems] or ["- none"])
    (out / "objstr_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-(len(notes) + len(problems) + 8):]))
    print(f"objstr: {len(problems)} problems, ids in {out / 'ds1_ids.json'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
