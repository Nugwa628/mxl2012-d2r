"""Static audit of Median's areas in the built tables (read-only).

Checks levels / lvlprest / lvltypes / lvlmaze / lvlwarp in work/mod/data/global/excel against each other, against the
map and tile files the mod will have (Median's global/tiles installed over D2R's), against the .ds1 contents, and
against D2R's limits (docs/subsystems/areas-drlg.md). Prints PROBLEM (would break or misplace an area), WARN (suspect)
and INFO lines plus a summary; exit code 1 when there are problems.

  py -3 tools/area_audit.py [--excel DIR] [--verbose]

Scope tags: "median" = ids D2R's levels.txt lacks (>= 138) or Median-only level types (>= 36); "vanilla" = the rest.
The .ds1 id renumbering that tools/install_mod.py applies (tools/ds1_remap.py) is simulated here, so the residue shown
is what is left after the install.
"""
import argparse
import csv
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ds1_remap import Ds1, Maps, remap_bytes  # noqa: E402
import fxpaths  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXCEL = ROOT / "work" / "mod" / "data" / "global" / "excel"
# D2R's own tables and tiles, Median's tiles: tools/fxpaths.py (repo extract / assets, else the environment, the runs folder)
D2R_EXCEL = fxpaths.D2R_EXCEL
MXL_TILES = fxpaths.MXL / "tiles"
D2R_TILES = fxpaths.D2R_DATA / "global" / "tiles"
IDMAP = ROOT / "work" / "named" / "idmap.json"

MAX_LEVEL_ID = 0x10001          # D2R asserts levelDataTbl.size() < MAX_LEVEL_ID (0x330446)
D2R_AUTOMAP_LEVEL_TYPES = 36    # AutoMap.txt names (plugin level_types.cpp)
D2R_WAYPOINTS = 112             # the waypoint record keeps 112 bits (table 0x2389010; the save keeps all of them)
PANEL_BUTTONS = 27             # waypoint panel (plugin waypoints.cpp): up to 27 levels per act tab, each under its levels.txt Act
# Maze.cpp post-generation switch on the level type (0x3e69e0); any other type hits the default arm, which asserts and exits
MAZE_LEVEL_TYPES = {3, 4, 7, 8, 10, 13, 14, 15, 17, 18, 19, 22, 23, 24, 25, 28, 32, 33, 34, 35}
# (level, waypoint number) shared on purpose by Median 2012 (docs/bugs.md)
KNOWN_SHARED_WAYPOINTS = {(134, 17): "bugs.md #13: Pandemonium 2 keeps the Valley of the Kings' number, as 1.13c"}
MAX_PRESET_FILES = 6            # LvlPrest File1..File6
MAX_TYPE_FILES = 32             # LvlTypes File 1..File 32 (Dt1Mask is a 32-bit mask)


_dt1 = {}


def dt1_tiles(path: Path):
    """{(main_index, sub_index)} of a .dt1 (version 7: tile count at 0x10C, tile headers at the offset in 0x110, 96 bytes each)."""
    if path not in _dt1:
        b = path.read_bytes()
        n, ptr = struct.unpack_from("<ii", b, 268)
        _dt1[path] = {struct.unpack_from("<ii", b, ptr + i * 96 + 24) for i in range(n)}
    return _dt1[path]


def maze_position_risk(row, d2r_row):
    """True for a maze level (DrlgType 1) with Position set unless D2R's level of the same id is a maze with Position
    set too (D2R's own mazes 54, 74, 125-127, 135 have entry rooms in their presets; a maze without one has an empty table)."""
    def on(r):
        return r is not None and str(r.get("DrlgType", "")).strip() == "1" and str(r.get("Position", "")).strip() not in ("", "0")
    return on(row) and not on(d2r_row)


def rd(path: Path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]


def num(s, default=None):
    try:
        return int(str(s).strip())
    except ValueError:
        return default


class Report:
    def __init__(self, verbose):
        self.items = []
        self.verbose = verbose

    def add(self, sev, kind, msg, scope="median"):
        self.items.append((sev, kind, msg, scope))

    def show(self):
        counts = Counter()
        for sev in ("PROBLEM", "WARN", "INFO"):
            kinds = defaultdict(list)
            for s, k, m, sc in self.items:
                if s == sev:
                    kinds[k].append((m, sc))
            for k, lst in sorted(kinds.items()):
                counts[sev] += len(lst)
                by_scope = Counter(sc for _, sc in lst)
                print(f"\n[{sev}] {k}: {len(lst)}  (median {by_scope['median']}, vanilla {by_scope['vanilla']})")
                for m, sc in lst[: (10**9 if self.verbose else 10)]:
                    print(f"   [{sc[0]}] {m}")
                if len(lst) > 10 and not self.verbose:
                    print(f"   ... {len(lst) - 10} more (--verbose)")
        return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel", default=str(EXCEL))
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    ex = Path(args.excel)
    rep = Report(args.verbose)

    _, levels = rd(ex / "levels.txt")
    _, prest = rd(ex / "lvlprest.txt")
    _, types = rd(ex / "lvltypes.txt")
    _, mazes = rd(ex / "lvlmaze.txt")
    _, warps = rd(ex / "lvlwarp.txt")
    _, monstats = rd(ex / "monstats.txt")
    _, objgroup = rd(ex / "objgroup.txt")
    # Median 2012 has no automap table of its own: D2R's AutoMap.txt stays (docs/tables-status.md)
    am_path = ex / "automap.txt" if (ex / "automap.txt").exists() else D2R_EXCEL / "automap.txt"
    automap = rd(am_path)[1] if am_path.exists() else []
    d2r_lv_path = D2R_EXCEL / "base" / "levels.txt" if (D2R_EXCEL / "base" / "levels.txt").exists() else D2R_EXCEL / "levels.txt"
    d2r_levels = {num(r.get("Id")): r for r in rd(d2r_lv_path)[1]} if d2r_lv_path.exists() else {}
    d2r_ids = [i for i in d2r_levels if i is not None] or [137]
    vanilla_ids = max(i for i in d2r_ids if i is not None) + 1  # D2R ids 0..137

    # file universe: Median's tiles are copied over D2R's under the mod (install_mod.py)
    mxl_files, d2r_files = {}, {}
    for root, store in ((MXL_TILES, mxl_files), (D2R_TILES, d2r_files)):
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file():
                    store[p.relative_to(root).as_posix().lower()] = p

    def tile(rel):
        """-> (Path, 'mxl'|'d2r') of the file the game will load, or (None, None)."""
        k = str(rel).replace("\\", "/").lower().lstrip("/")
        if k in mxl_files:
            return mxl_files[k], "mxl"
        if k in d2r_files:
            return d2r_files[k], "d2r"
        return None, None

    # ---- levels
    lv = {}
    for r in levels:
        i = num(r.get("Id"))
        if i is None:
            rep.add("PROBLEM", "levels: row without Id", r.get("Name", "?"))
            continue
        if i in lv:
            rep.add("PROBLEM", "levels: duplicate Id", f"{i} {r['Name']} / {lv[i]['Name']}")
        lv[i] = r
    ids = sorted(lv)
    if ids != list(range(len(ids))):
        rep.add("PROBLEM", "levels: Ids not contiguous from 0", f"{len(ids)} rows, max {ids[-1]}")
    if len(ids) >= MAX_LEVEL_ID:
        rep.add("PROBLEM", "levels: too many rows", f"{len(ids)} >= {MAX_LEVEL_ID}")

    mon_ids = {r.get("Id", "").lower() for r in monstats}
    objgroup_n = len(objgroup)
    type_ids = {}
    for j, t in enumerate(types):
        tid = num(t.get("Id"))
        type_ids[tid if tid is not None else j] = t
    if sorted(type_ids) != list(range(len(types))):
        rep.add("PROBLEM", "lvltypes: Ids not contiguous", f"{len(types)} rows")

    # waypoint panel: the plugin lists every waypoint level under its own act (tab = Act + 1), up to PANEL_BUTTONS per tab
    wp_numbers = {}
    act_waypoints = defaultdict(int)
    for r in lv.values():
        if num(r.get("Waypoint"), 0) != 255:
            act_waypoints[num(r.get("Act"), 0) or 0] += 1

    prest_by_level = defaultdict(list)
    for p in prest:
        lid = num(p.get("LevelId"), 0)
        if lid:
            prest_by_level[lid].append(p)
    maze_by_level = defaultdict(list)
    for m in mazes:
        maze_by_level[num(m.get("Level"), 0)].append(m)
    warp_ids = {num(w.get("Id")) for w in warps}

    def scope(i):
        return "median" if i >= vanilla_ids else "vanilla"

    used_types = Counter()
    n_by_drlg = Counter()
    for i in ids:
        r = lv[i]
        name = r["Name"]
        sc = scope(i)
        tag = f"{i} {name}"
        drlg = num(r.get("DrlgType"))
        ltype = num(r.get("LevelType"))
        if i == 0 or name.startswith("levels_"):
            rep.add("INFO", "levels: empty placeholder rows (never generated)", tag, sc)
            continue
        n_by_drlg[drlg] += 1
        act = num(r.get("Act"), 0)
        if not 0 <= act <= 4:
            rep.add("PROBLEM", "levels: Act outside 0..4", f"{tag} Act={r.get('Act')}", sc)
        if drlg not in (1, 2, 3):
            rep.add("PROBLEM", "levels: DrlgType not 1/2/3", f"{tag} DrlgType={r.get('DrlgType')}", sc)
        if ltype is None or ltype not in type_ids or ltype == 0:
            rep.add("PROBLEM", "levels: LevelType missing or out of lvltypes", f"{tag} LevelType={r.get('LevelType')}", sc)
        else:
            used_types[ltype] += 1
        if drlg == 3 and i >= vanilla_ids:
            rep.add("PROBLEM", "levels: outdoor (DrlgType 3) generator on a Median-only level "
                    "(D2R picks the outdoor generator by level id)", tag, sc)
        if drlg == 2:
            rows = prest_by_level.get(i, [])
            if not rows:
                rep.add("PROBLEM", "levels: preset level with no lvlprest row", tag, sc)
            elif not any(p.get(f"File{k}", "0").strip() not in ("", "0") for p in rows for k in range(1, MAX_PRESET_FILES + 1)):
                rep.add("PROBLEM", "levels: preset level whose lvlprest rows list no map file", tag, sc)
        if drlg == 1:
            if i not in maze_by_level:
                rep.add("PROBLEM", "levels: maze level with no lvlmaze row", tag, sc)
            if ltype not in MAZE_LEVEL_TYPES:
                rep.add("PROBLEM", "levels: maze level whose LevelType is not in D2R's maze switch (generation asserts and exits)",
                        f"{tag} LevelType={ltype}", sc)
            if maze_position_risk(r, d2r_levels.get(i)):
                rep.add("PROBLEM", "levels: maze level with Position set that D2R does not have as such a maze (no entry room: "
                        "the arrival spot is (0, 0), the room is null and the game dies)", tag, sc)
        if drlg == 2 and r.get("Position", "").strip() not in ("", "0") and d2r_levels.get(i) is not None                 and num(d2r_levels[i].get("DrlgType")) != 2:
            rep.add("WARN", "levels: preset level with Position set where D2R's level is not a preset (arrival spot of "
                    "the new map; checked in game by tools/level_sweep.py)", tag, sc)
        for k in range(8):
            vis = num(r.get(f"Vis{k}"))
            if vis is not None and vis <= 0:
                vis = None
            wp = num(r.get(f"Warp{k}"), -1)
            if vis is not None and vis not in lv:
                rep.add("PROBLEM", "levels: Vis points at a missing level", f"{tag} Vis{k}={vis}", sc)
            if wp not in (-1, None) and wp not in warp_ids:
                rep.add("PROBLEM", "levels: Warp points at a missing lvlwarp row", f"{tag} Warp{k}={wp}", sc)
            if vis is not None and vis in lv and not any((num(lv[vis].get(f"Vis{q}"), 0) or 0) == i for q in range(8)):
                rep.add("WARN", "levels: one-way Vis link", f"{tag} Vis{k}={vis} ({lv[vis]['Name']}) does not link back", sc)
        wpn = num(r.get("Waypoint"), 0)   # blank = 0
        if wpn != 255:
            if wpn >= D2R_WAYPOINTS:
                rep.add("PROBLEM", f"levels: Waypoint number >= {D2R_WAYPOINTS} (past the waypoint record)", f"{tag} Waypoint={wpn}", sc)
            if wpn in wp_numbers:
                if (i, wpn) in KNOWN_SHARED_WAYPOINTS:
                    rep.add("WARN", "levels: Waypoint number used twice, as in Median 2012's own table",
                            f"{tag} Waypoint={wpn} (also {wp_numbers[wpn]}): {KNOWN_SHARED_WAYPOINTS[(i, wpn)]}", sc)
                else:
                    rep.add("PROBLEM", "levels: Waypoint number used twice", f"{tag} Waypoint={wpn} (also {wp_numbers[wpn]})", sc)
            wp_numbers[wpn] = r["Name"]
            act = num(r.get("Act"), 0) or 0
            if not 0 <= act <= 4 or act_waypoints[act] > PANEL_BUTTONS:
                rep.add("WARN", f"levels: waypoint level with no button in the waypoint panel (acts 1-5, {PANEL_BUTTONS} per act)", f"{tag} Waypoint={wpn}", sc)
        for col in [f"{p}mon{k}" for p in ("", "n", "u") for k in range(1, 26)] + [f"cmon{k}" for k in range(1, 5)]:
            v = r.get(col, "").strip()
            if v and v.lower() not in mon_ids:
                rep.add("PROBLEM", "levels: monster column names a monster that is not in monstats", f"{tag} {col}={v}", sc)
        for k in range(8):
            g = num(r.get(f"ObjGrp{k}"))
            if g is not None and g >= objgroup_n:
                rep.add("PROBLEM", "levels: ObjGrp past objgroup rows", f"{tag} ObjGrp{k}={g}", sc)

    # ---- lvlprest
    seen_def = set()
    per_level = Counter()
    maps_used = {}   # path -> (origin, Ds1 or None)
    for n, p in enumerate(prest):
        d = num(p.get("Def"))
        if d != n:
            rep.add("PROBLEM", "lvlprest: Def is not the row index", f"row {n} Def={p.get('Def')} ({p['Name']})")
        if d in seen_def:
            rep.add("PROBLEM", "lvlprest: duplicate Def", str(d))
        seen_def.add(d)
        lid = num(p.get("LevelId"), 0)
        if lid and lid not in lv:
            rep.add("PROBLEM", "lvlprest: LevelId is not a level", f"{p['Name']} LevelId={lid}")
        nfiles = num(p.get("Files"), 0)
        if nfiles > MAX_PRESET_FILES:
            rep.add("PROBLEM", f"lvlprest: Files > {MAX_PRESET_FILES}", f"{p['Name']} Files={nfiles}")
        if lid:
            per_level[lid] += 1
        sc = scope(lid)
        for k in range(1, MAX_PRESET_FILES + 1):
            f = p.get(f"File{k}", "").strip()
            if f in ("", "0"):
                continue
            path, origin = tile(f)
            if path is None:
                rep.add("PROBLEM", "lvlprest: map file missing from the mod and D2R", f"{p['Name']} (level {lid}) {f}", sc)
            elif path not in maps_used:
                try:
                    maps_used[path] = (origin, Ds1(path.read_bytes()))
                except Exception as e:  # noqa: BLE001
                    maps_used[path] = (origin, None)
                    rep.add("PROBLEM", "lvlprest: map file does not parse as .ds1", f"{f}: {e}", sc)
        mask = num(p.get("Dt1Mask"), 0) or 0
        if mask < 0 or mask >= 1 << MAX_TYPE_FILES:
            rep.add("PROBLEM", "lvlprest: Dt1Mask outside 32 bits", f"{p['Name']} {mask}")
        elif lid and lid in lv and mask:  # LevelId 0: shared pieces (outdoor transitions) of whatever level uses them
            lt = type_ids.get(num(lv[lid].get("LevelType")))
            if lt is not None:
                avail = set()
                for b in range(MAX_TYPE_FILES):
                    if not mask >> b & 1:
                        continue
                    f = lt.get(f"File {b + 1}", "0")
                    if f in ("", "0"):
                        rep.add("WARN", "lvlprest: Dt1Mask selects an empty lvltypes slot",
                                f"{p['Name']} bit {b} (type {lt['Name']})", sc)
                        continue
                    dp, _ = tile(f)
                    if dp is not None:
                        avail |= dt1_tiles(dp)
                # tile coverage: share of the map's floor/wall cells whose (style, sequence) no selected .dt1 has
                for k in range(1, MAX_PRESET_FILES + 1):
                    ent = maps_used.get(tile(p.get(f"File{k}", "0"))[0])
                    if not ent or ent[1] is None or not avail:
                        continue
                    d = ent[1]
                    tot = miss = 0
                    stream = [d.cells(j * 2) for j in range(d.walls)] + [d.cells(d.walls * 2 + j) for j in range(d.floors)]
                    for li, lay in enumerate(stream):
                        for c in lay:
                            main, sub = (c >> 20) & 0x3F, (c >> 8) & 0x3F
                            if c & 0xFF == 0 and main == 0 and sub == 0:
                                continue
                            tot += 1
                            miss += (main, sub) not in avail
                    if tot and miss / tot > 0.2:
                        rep.add("WARN", "tiles: over 20% of a map's cells name a tile none of its selected .dt1 files has "
                                "(heuristic: style/sequence only)", f"{p['Name']} {p.get(f'File{k}')}: {miss}/{tot}", sc)

    # ---- lvlmaze
    for n, m in enumerate(mazes):
        lid = num(m.get("Level"), 0)
        if lid == 0:
            rep.add("INFO", "lvlmaze: rows with a blank Level (never matched)", m["Name"], "vanilla")
        elif lid not in lv:
            rep.add("PROBLEM", "lvlmaze: Level is not a level", f"row {n} {m['Name']} Level={m.get('Level')}")
        elif num(lv[lid].get("DrlgType")) != 1:
            rep.add("WARN", "lvlmaze: row for a level that is not DrlgType 1", f"{m['Name']} -> {lid} {lv[lid]['Name']}", scope(lid))
        for c in ("Rooms", "SizeX", "SizeY"):
            if (num(m.get(c), 0) or 0) <= 0:
                rep.add("PROBLEM", "lvlmaze: non-positive Rooms/SizeX/SizeY", f"{m['Name']} {c}={m.get(c)}", scope(lid or 0))

    # ---- lvltypes
    for j, t in sorted(type_ids.items()):
        if j == 0:
            continue
        sc = "median" if j >= D2R_AUTOMAP_LEVEL_TYPES else "vanilla"
        nonempty = 0
        for k in range(1, MAX_TYPE_FILES + 1):
            f = t.get(f"File {k}", "").strip()
            if f in ("", "0"):
                continue
            nonempty += 1
            if tile(f)[0] is None:
                rep.add("PROBLEM", "lvltypes: tile file missing from the mod and D2R", f"type {j} {t['Name']} File {k}: {f}", sc)
        if not nonempty:
            rep.add("WARN", "lvltypes: type lists no tile files", f"type {j} {t['Name']}", sc)
        if j not in used_types:
            rep.add("INFO", "lvltypes: type used by no level", f"type {j} {t['Name']}", sc)
    names = [t["Name"] for _, t in sorted(type_ids.items())]
    am_by_type = Counter(a.get("LevelName", "") for a in automap)
    for j in range(D2R_AUTOMAP_LEVEL_TYPES, len(names)):
        if used_types.get(j) and not am_by_type.get(f"mxl_lvltype_{j}") and not am_by_type.get(names[j]):
            rep.add("INFO", "automap: Median level type used by levels but with no AutoMap.txt rows (no automap tiles there)",
                    f"type {j} {names[j]} used by {used_types[j]} level(s)")

    # ---- lvlwarp
    used_warps = Counter()
    for r in levels:
        for k in range(8):
            w = num(r.get(f"Warp{k}"), -1)
            if w not in (-1, None):
                used_warps[w] += 1
    # D2R's own lvlwarp has two rows (directions l / r) for some Ids: the warp lookup is by Id and Direction, so a pair twice
    # is ambiguous (D2R-XL 2012 bug #260: a keyed merge appended D2R's Act 5 rows a second time)
    pairs = Counter((num(w.get("Id")), w.get("Direction", "").strip().lower()) for w in warps if num(w.get("Id")) is not None)
    for (wid, dirn), c in sorted(pairs.items()):
        if c > 1:
            rep.add("PROBLEM", "lvlwarp: (Id, Direction) on more than one row", f"Id {wid} Direction {dirn or '-'} x{c}")
    rep.add("INFO", "lvlwarp: rows no level uses", f"{sum(1 for n in range(len(warps)) if n not in used_warps)} of {len(warps)}",
            "vanilla")

    # ---- ds1 contents (Median's own copies only; D2R's maps use D2R's ids)
    if IDMAP.exists() and (ex / "monpreset.txt").exists():
        maps = Maps(IDMAP, ex)
        op_path = ex / "objpreset.txt"
        if not op_path.exists():
            op_path = D2R_EXCEL / "objpreset.txt"
        have = set()
        if op_path.exists():
            have = {(num(r.get("Act")), num(r.get("Index"))) for r in rd(op_path)[1]}
        files = Counter()
        missing_idx = Counter()
        for path, (origin, d) in maps_used.items():
            if d is None or origin != "mxl":
                continue
            files["maps"] += 1
            if not 0 <= d.act <= 4:
                rep.add("PROBLEM", "ds1: act field outside 0..4", f"{path.name} act {d.act}")
            before = Counter()
            new = remap_bytes(path.read_bytes(), maps, before)
            for k, v in before.items():
                files[k] += v
            if before:
                files["maps changed"] += 1
            if before["type1_dropped"]:
                rep.add("WARN", "ds1: monster id past monstats / unresolvable negative id (dropped by the remap)",
                        f"{path.name} x{before['type1_dropped']}")
            if before["type2_dropped"]:
                rep.add("WARN", "ds1: object id naming no slot of Median's ObjPreset table (dropped by the remap)",
                        f"{path.name} x{before['type2_dropped']}")
            d2 = Ds1(new)
            for t, i, *_ in d2.objects:
                if t == 2 and (d2.act + 1, i) not in have:
                    missing_idx[(d2.act + 1, i)] += 1
        if missing_idx:
            rep.add("PROBLEM", "objpreset: remapped object index missing from the built ObjPreset.txt (rebuild with "
                    "tools/txt_migrate.py; the built mod lacks Median's table)",
                    f"{sum(missing_idx.values())} placements, {len(missing_idx)} (act, index) pairs, e.g. "
                    f"{sorted(missing_idx)[:3]}")
        rep.add("INFO", "ds1 remap (tools/ds1_remap.py, applied by install_mod.py)",
                f"{files['maps']} Median maps used, {files['maps changed']} changed: monsters {files['type1_renumbered']} "
                f"renumbered / {files['type1_dropped']} dropped, objects {files['type2_renumbered']} renumbered / "
                f"{files['type2_dropped']} dropped")

    # ---- tile shadowing
    shadow = diff = 0
    for k, p in mxl_files.items():
        q = d2r_files.get(k)
        if q is not None:
            shadow += 1
            if p.read_bytes() != q.read_bytes():
                diff += 1
    rep.add("INFO", "tiles", f"Median ships {len(mxl_files)} tile files; {shadow} share a path with D2R's and {diff} of "
            f"those differ (Median's copy wins in the mod)", "vanilla")
    top = per_level.most_common(1)[0] if per_level else (0, 0)
    rep.add("INFO", "counts", f"levels {len(ids)} ({len(ids) - vanilla_ids} beyond D2R's {vanilla_ids}; DrlgType "
            f"{dict(sorted((k or 0, v) for k, v in n_by_drlg.items()))}), lvlprest {len(prest)} (max {top[1]} rows per level), "
            f"lvltypes {len(types)} (D2R automap names {D2R_AUTOMAP_LEVEL_TYPES}; types beyond used by "
            f"{sum(c for j, c in used_types.items() if j >= D2R_AUTOMAP_LEVEL_TYPES)} levels), lvlmaze {len(mazes)}, "
            f"lvlwarp {len(warps)}, {len(maps_used)} distinct maps resolved", "vanilla")

    counts = rep.show()
    print(f"\nSUMMARY: {counts['PROBLEM']} problems, {counts['WARN']} warnings, {counts['INFO']} info")
    return 1 if counts["PROBLEM"] else 0


if __name__ == "__main__":
    sys.exit(main())
