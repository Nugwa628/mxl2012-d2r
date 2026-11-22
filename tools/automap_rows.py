#!/usr/bin/env python
"""Automap rows for Median XL 2012's own wall tiles (lanes hdmaps2, automapall): the minimap draws a tile only when
automap.txt has a row for its (level type, tile code, style, sequence) (tools/automap_render.py). Median 2012 ships no
automap.txt, so its new tile sets in a stock level type find D2R's (= vanilla) rows, which were written for the stock
tiles: most of Median's walls get no row and the minimap of a map like Fauztinville (Act 2 - Tomb) shows almost nothing,
in classic Median as in D2R.

This adds, per level type, one row for every wall key (code, style, sequence) a map of that type draws and no row covers:
  maps     every map Median ships (its 34 .ds1) and every map of a level whose level type lists a tile set D2R's row of
           that type does not (Median appended its own sets to 6 stock types), map_list();
  cells    per level type and wall code the cell its own rows use most (TEMPLATE, derived from D2R's automap.txt by
           templates(); a type missing a code takes a sibling code, a type missing one of the 7 main codes takes GENERIC's
           whole set). For types whose legacy cells read dimmer than their HD ones (ink_ratio() under INK_TARGET: every
           type a Median map changes, the classic lines being thinner) the 8 non-door codes point at
           free cells holding brighter copies (BRIGHT, tools/automap_art.py; at most 8 per type).
  skipped  keys a stock tile set of the type holds (D2R's lvltypes File 1..32 of that type) or one of D2R's own maps of the
           type draws: the stock levels keep their minimap exactly (check_stock() proves it on every D2R map of those
           types, maze rooms included); tree and invisible-wall tile sets
           (NOT_WALLS: stock trees have no row either); keys no tile set of the map has (nothing is drawn there).
Floors, roofs, shadows and lower walls keep no row (the automap draws none of them in stock maps).

  python tools/automap_rows.py OUT_AUTOMAP_TXT [--plan PLAN_JSON] [--map MAP ...] [--base automap.txt] [--d2r DIR]
writes D2R's automap.txt with the new rows appended (a mod's data/global/excel/automap.txt), the plan (maps, per-type
cells, rows, report; read by automap_art.py and automap_void.py) and prints the report.
  python tools/automap_rows.py --list      the map list with each map's level types
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401
import automap_render as ar  # noqa: E402

WALL_CODES = ["wl", "wr", "wtlr", "wtll", "wtr", "wbl", "wbr", "wld", "wrd", "wle", "wre", "co"]
CORE = ["wl", "wr", "wtlr", "wtll", "wtr", "wbl", "wbr"]        # a type without a row for one of these takes GENERIC
DOORS = ("wld", "wrd", "wle", "wre")                           # keep the template cell (no bright copy: max 8 per type)
SIBLING = {"wtlr": ["wtll"], "wtll": ["wtlr"], "co": ["wbr"], "wld": ["wl"], "wrd": ["wr"], "wle": ["wld", "wl"],
           "wre": ["wrd", "wr"]}                                # a code the type has no row for takes the first one it has
GENERIC = "1 Catacombs"     # the plain wall set (cells 20-39) most dungeon types share; every code present
INK_TARGET = 0.8            # legacy reads dimmer than HD when its cells' ink (luma x alpha per screen area, ink_ratio())
                            # is under this share of the HD cells': those types get bright copies with a gain of
GAIN_MAX = 2.4              # INK_TARGET / ratio, at most GAIN_MAX (the Tomb's: ratio 0.21, gain 2.4, as hdmaps2 shipped)
BRIGHT_ORDER = ["wr", "wl", "wbl", "wtr", "wtll", "wtlr", "wbr", "co"]
BRIGHT_MAX = 8
FIRST_BRIGHT = 1176         # free cells are handed out from here up (then the rest from the bottom)
# hdmaps2's cells for the Tomb (Fauztinville, checked in game): kept as they are
PINNED = {"2 Tomb": {"wr": 1176, "wl": 1177, "wbl": 1178, "wtr": 1179, "wtll": 1180, "wtlr": 1180, "wbr": 1181,
                     "co": 1182}}
NOT_WALLS = re.compile(r"(^|/)(tree[^/]*|inv_wall)\.dt1$", re.I)   # trees (as stock) and the invisible collision wall
CEL_MAX = 1498            # D2R's automap atlas ends here (crash audit C8: a cell past it crashes the HD game)
MOD_OBJECTS = None        # Median's objects.txt (AutoMap cells it uses), default: the mod extract's


def automap_rows_all(path: Path) -> list:
    """[(LevelName, TileName, Style, cels)] of a whole automap.txt, in file order."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    head = lines[0].split("\t")
    out = []
    for ln in lines[1:]:
        r = dict(zip(head, ln.split("\t")))
        if not r.get("LevelName"):
            continue
        out.append((r["LevelName"], r.get("TileName", ""), r.get("Style", ""),
                    [int(r["Cel%d" % i]) for i in range(1, 5) if r.get("Cel%d" % i, "").lstrip("-").isdigit()
                     and int(r["Cel%d" % i]) >= 0]))
    return out


def templates(automap: Path) -> dict:
    """{LevelName: {code: cel}}: each type's most-used cell per wall code (ties: the one its rows name first), missing codes
    from SIBLING, a type without one of CORE all from GENERIC."""
    use = defaultdict(lambda: defaultdict(Counter))
    first = {}
    for i, (lt, code, _st, cels) in enumerate(automap_rows_all(automap)):
        for c in cels:
            use[lt][code][c] += 1
            first.setdefault((lt, code, c), i)
    raw = {}
    for lt, codes in use.items():
        raw[lt] = {code: min(cnt, key=lambda c: (-cnt[c], first[(lt, code, c)]))
                   for code, cnt in codes.items() if code in WALL_CODES}

    def fill(t):
        out = dict(t)
        for code in WALL_CODES:
            if code not in out:
                out[code] = next((out[s] for s in SIBLING.get(code, []) if s in out), None)
        return out

    generic = fill(raw[GENERIC])
    assert all(generic[c] for c in WALL_CODES), "automap_rows: %s lacks a wall code" % GENERIC
    out = {}
    for lt, t in raw.items():
        f = fill(t)
        out[lt] = dict(generic) if any(f[c] is None for c in CORE) else {c: f[c] or generic[c] for c in WALL_CODES}
    return out


def act_of(lt: str) -> int:
    """'2 Tomb' -> 2 (the act palette its automap is drawn with)."""
    return int(lt.split()[0])


def luma(cels, act: int) -> float:
    """Mean luma of the classic pictures of these cells (opaque pixels, the act palette)."""
    import numpy as np
    art = ar.Art(act)
    px = np.concatenate([art.classic(c)[art.classic(c)[..., 3] > 0][:, :3] for c in cels]).astype(np.float64)
    return float((px @ np.array([0.299, 0.587, 0.114])).mean())


def ink_ratio(cels, act: int) -> float:
    """Legacy / HD ink of these cells: mean luma x alpha per screen area, the classic cell (16 x 32) against its HD cell
    (64 x 128, the same screen area at 4x). The classic lines are thinner, so it is about 0.5 even where the pixels are
    as bright."""
    import numpy as np
    art, w = ar.Art(act), np.array([0.299, 0.587, 0.114])

    def ink(im, area):
        im = im.astype(np.float64)
        return float((im[..., :3] @ w * im[..., 3] / 255.0).sum() / area)
    return sum(ink(art.classic(c), 16 * 32) for c in cels) / max(1e-9, sum(ink(art.hd(c), 64 * 128) for c in cels))


def gain_of(ratio: float) -> float:
    """The legacy gain for a type whose ink ratio is this (1.0 = none), in steps of 0.05."""
    return round(min(GAIN_MAX, max(1.0, INK_TARGET / ratio)) * 20) / 20.0


def free_cels(d2r_data: Path, objects=()) -> list:
    """Cells no table uses that both automap pictures (maximap.dc6, maximaps.dc6) and both HD sheets hold, ascending."""
    import struct
    import automap_art
    import dc6
    used = automap_art.used_cels(d2r_data, objects)
    ui = d2r_data / "global" / "ui" / "automap"
    n = min(len(dc6.parse_dc6((ui / f).read_bytes())) for f in ("maximap.dc6", "maximaps.dc6"))
    sheets = {}
    for k in range(CEL_MAX // 100 + 1):
        for f in ("tiles.sprite", "tiles.lowend.sprite"):
            p = d2r_data / "hd" / "global" / "ui" / "automap" / ("default%02d" % k) / f
            sheets[(k, f)] = struct.unpack_from("<I", p.read_bytes(), 0x14)[0] if p.is_file() else 0
    return [c for c in range(1, min(n, CEL_MAX + 1)) if c not in used
            and all(sheets[(c // 100, f)] > c % 100 for f in ("tiles.sprite", "tiles.lowend.sprite"))]


def bright_cels(types: list, tpl: dict, free: list, gains: dict = None) -> dict:
    """{LevelName: {code: free cel}} for the dim types: one cell per distinct template cell of BRIGHT_ORDER's codes. A
    copy is the template cell in the type's act palette at its gain, so types of one act with the same template cell and
    gain share it (1 Crypt and 1 Cathedral)."""
    gains = gains or {}
    out, taken, shared = {}, set(), {}
    for lt in types:
        if lt in PINNED:
            assert all(PINNED[lt][c] in free for c in PINNED[lt]), "automap_rows: a pinned cel of %s is used" % lt
            out[lt] = dict(PINNED[lt])
            taken |= set(PINNED[lt].values())
            for code, c in PINNED[lt].items():
                shared[(act_of(lt), tpl[lt][code], gains.get(lt, GAIN_MAX))] = c
    pool = [c for c in free if c >= FIRST_BRIGHT] + [c for c in free if c < FIRST_BRIGHT]
    for lt in types:
        if lt in out:
            continue
        cels = {}
        for code in BRIGHT_ORDER:
            k = (act_of(lt), tpl[lt][code], gains.get(lt, GAIN_MAX))
            if k not in shared:
                c = next((c for c in pool if c not in taken), None)
                if c is None:
                    raise SystemExit("automap_rows: no free automap cel left for %s" % lt)
                shared[k] = c
                taken.add(c)
            cels[code] = shared[k]
        assert len(set(cels.values())) <= BRIGHT_MAX
        out[lt] = cels
    return out


@lru_cache(maxsize=None)
def _d2r_types() -> dict:
    from hdkit.view.mapview import world
    return {r["Name"]: r for r in world.read_table(ar.D2R / "global" / "excel" / "lvltypes.txt")}


@lru_cache(maxsize=None)
def _d2r_tiles() -> dict:
    """D2R's tile sets by lower-case path below global/tiles."""
    base = ar.D2R / "global" / "tiles"
    return {p.relative_to(base).as_posix().lower(): p for p in base.rglob("*") if p.suffix.lower() == ".dt1"}


def stock_files(lvltype: str) -> list:
    r = _d2r_types().get(lvltype) or {}
    return [f.strip().lower() for f in (r.get("File %d" % i) or "" for i in range(1, 33)) if f.strip() not in ("", "0")]


@lru_cache(maxsize=None)
def stock_keys(lvltype: str) -> frozenset:
    """(code, style, sequence) of every tile in the level type's tile sets in D2R's lvltypes.txt."""
    import dt1
    out = set()
    for f in stock_files(lvltype):
        p = _d2r_tiles().get(f)
        if p is None:
            raise SystemExit("automap_rows: stock tile set %s not found under %s" % (f, ar.D2R))
        for t in dt1.parse_file(p):
            if 0 <= t.orientation < len(ar.CODES):
                out.add((ar.CODES[t.orientation], t.main, t.sub))
    return frozenset(out)


def median_types(roots=None) -> list:
    """Level types (lvltypes Name) whose mod row lists a tile set D2R's row of that type does not."""
    from hdkit.view.mapview import world
    roots = roots or world.Roots()
    out = []
    for r in world.read_table(roots.mod / "excel" / "lvltypes.txt"):
        stock = set(stock_files(r.get("Name", "")))
        files = [(r.get("File %d" % i) or "").strip().lower() for i in range(1, 33)]
        if any(f not in ("", "0") and f not in stock for f in files):
            out.append(r["Name"])
    return out


def map_list(roots=None) -> list:
    """The mod's own maps plus every map a level of a median_types() type uses (lvlprest File1..6), sorted."""
    from hdkit.view.mapview import world
    roots = roots or world.Roots()
    t = world.Tables(roots, "mod")
    med = set(median_types(roots))
    names = {world.num(r.get("Id"), j): r.get("Name") for j, r in enumerate(world.read_table(roots.mod / "excel" /
                                                                                             "lvltypes.txt"))}
    out = set(roots.maps("mod"))
    for r in t.prest:
        lid = world.num(r.get("LevelId"), -1)
        lv = t.levels.get(lid) if lid else None
        lt = names.get(world.num(lv.get("LevelType"), -1)) if lv else prest_type(r.get("Name"), names.values())
        if lt in med:
            out |= {world.norm(f)[:-4] for f in (r.get("File%d" % k, "").strip() for k in range(1, 7)) if f and f != "0"}
    return sorted(out)


@lru_cache(maxsize=None)
def _mod_tables():
    from hdkit.view.mapview import world
    roots = world.Roots(casc=False)          # no palette from the game's CASC: the rows need none
    return roots, world.Tables(roots, "mod")


def open_map(key: str):
    """The map with the mod's tables (a D2R map a Median level uses keeps D2R's .ds1)."""
    from hdkit.view.mapview import world
    roots, t = _mod_tables()
    return world.MapSource(key, "mod", roots=roots, tables=t)


# sub-presets (lvlprest rows of level 0, type None) are laid into a level of their folder's type by the level's own code
SUBPRESET_TYPE = {"act1/outdoors/": "Act 1 - Wilderness", "act2/maggot/": "Act 2 - Lair", "act4/diab/": "Act 4 - Lava"}


def prest_type(name: str, types) -> str:
    """The level type of a lvlprest row of level 0 (a maze room, "Act 2 - Tomb NSEW"): the lvltypes Name (or its automap
    name, "Act 5 - Ice") its Name starts with, the longest; else None."""
    hits = []
    for t in types:
        if not t or t == "None":
            continue
        short = ar.level_type_name(t)          # "Act 5 - Ice Caves" rooms are named "Act 5 - Ice ..." (automap's "5 Ice")
        for pre in {t, "Act %s - %s" % tuple(short.split(" ", 1))} if " " in short else {t}:
            if (name or "").startswith(pre + " "):
                hits.append((len(pre), t))
    return max(hits)[1] if hits else None


def level_types(src) -> list:
    """lvltypes Names the map is drawn under: its levels' types, a maze room's by its lvlprest Name (prest_type), a
    sub-preset by its folder (SUBPRESET_TYPE)."""
    names = [r.get("Name") for r in src.tables.types.values()]
    out = {lv["level_type"] for lv in src.levels if lv.get("level_type") and lv["level_type"] != "None"}
    out |= {t for r, lid, _m in src.tables.usage(src.key) if not lid for t in [prest_type(r.get("Name"), names)] if t}
    if not out:
        out = {t for pre, t in SUBPRESET_TYPE.items() if src.key.startswith(pre)}
    return sorted(out)


def map_needs(src) -> dict:
    """{(automap LevelName, lvltypes Name): Counter{(code, style, seq): tiles}} of the map's drawn wall tiles whose key its
    tile sets hold, for each level type the map is used under. Includes keys that have a row or are stock (filtered later)."""
    types = level_types(src)
    walls = Counter()
    for _x, _y, o, st, sq in ar.tiles(src.ds):
        code = ar.CODES[o] if o < len(ar.CODES) else None
        if code in WALL_CODES and src.lib.variants(o, st, sq):
            walls[(code, st, sq)] += 1
    return {(ar.level_type_name(t), t): walls for t in types}


def not_wall_keys(src) -> set:
    """Keys first found in a NOT_WALLS tile set of the map."""
    return {(ar.CODES[k[0]], k[1], k[2]) for k, rel in src.lib.file_of.items()
            if NOT_WALLS.search(rel) and 0 <= k[0] < len(ar.CODES)}


def new_rows(maps: list, base: Path, objects=None) -> tuple:
    """([(level, code, style, seq, cel)], plan) for the maps' wall keys without a row."""
    tpl = templates(base)
    rows_by_level, need, trees, per_map = {}, defaultdict(Counter), defaultdict(set), {}
    lvt_of = {}
    for key in maps:
        src = open_map(key)
        nw = not_wall_keys(src)
        per_map[key] = {"level_types": level_types(src),
                        "levels": sorted({lv["level_name"] for lv in src.levels if lv.get("level_name")})}
        for (lt, lvt), walls in map_needs(src).items():
            if lt not in tpl:           # a type D2R draws no tile of (5 Town): nothing to copy from, left as it is
                per_map[key].setdefault("no_automap_type", []).append(lt)
                continue
            lvt_of[lt] = lvt
            rows = rows_by_level.setdefault(lt, ar.read_rows(base, lt))
            stock = stock_keys(lvt) | stock_map_keys(lt)
            mine = Counter({k: n for k, n in walls.items() if not ar.lookup(rows, *k) and k not in stock})
            trees[lt] |= {k for k in mine if k in nw}
            for k, n in mine.items():
                need[lt][k] += n
            per_map[key].setdefault("keys", {})[lt] = sorted("%s %d %d" % k for k in mine if k not in nw)
    types = [lt for lt in tpl if need.get(lt) and set(need[lt]) - trees[lt]]       # automap.txt order
    dim = {lt: luma(sorted({tpl[lt][c] for c in CORE}), act_of(lt)) for lt in types}
    ratio = {lt: ink_ratio(sorted({tpl[lt][c] for c in CORE}), act_of(lt)) for lt in types}
    dark = [lt for lt in types if ratio[lt] < INK_TARGET]
    gains = {lt: gain_of(ratio[lt]) for lt in dark}
    for lt in PINNED:
        assert lt not in gains or gains[lt] == GAIN_MAX, "automap_rows: %s's pinned cels were made at %s" % (lt, GAIN_MAX)
    objects = objects if objects is not None else ([MOD_OBJECTS] if MOD_OBJECTS else [_mod_objects()])
    bright = bright_cels(dark, tpl, free_cels(ar.D2R, [o for o in objects if o]), gains)
    out = []
    for lt in types:
        for code, st, sq in sorted(k for k in need[lt] if k not in trees[lt]):
            cel = bright.get(lt, {}).get(code) or tpl[lt][code]
            assert 0 < cel <= CEL_MAX
            out.append((lt, code, st, sq, cel))
    report = {lt: {"level_type": lvt_of[lt], "keys": len(need[lt]), "tiles": sum(need[lt].values()),
                   "added": sum(1 for r in out if r[0] == lt), "skipped_not_walls": ["%s %d %d" % k for k in
                                                                                     sorted(trees[lt])]}
              for lt in need}
    for key, m in per_map.items():
        m["rows_added"] = sum(len(v) for v in m.get("keys", {}).values())
    plan = {"maps": per_map, "types": {lt: {"level_type": lvt_of[lt], "act": act_of(lt), "template": tpl[lt],
                                            "classic_luma": round(dim[lt], 1), "ink_ratio": round(ratio[lt], 3),
                                            "gain": gains.get(lt, 1.0), "bright": bright.get(lt, {})}
                                       for lt in types},
            "rows": [list(r) for r in out], "report": report}
    return out, plan


def _mod_objects():
    from hdkit.view.mapview import world
    p = world.Roots().mod / "excel" / "objects.txt"
    return str(p) if p.is_file() else None


def write(base: Path, rows: list, out: Path):
    text = base.read_bytes().decode("utf-8", errors="replace")      # bytes: keep the table's own line ends (CRLF)
    head = text.splitlines()[0].split("\t")
    nl = "\r\n" if text.splitlines(True)[0].endswith("\r\n") else "\n"
    lines = [ln.rstrip("\r") for ln in text.rstrip("\r\n").split("\n")]
    for lt, code, st, sq, cel in rows:
        v = {"LevelName": lt, "TileName": code, "Style": str(st), "StartSequence": str(sq), "EndSequence": str(sq),
             "*Type1": "mxl %s" % code, "Cel1": str(cel), "Cel2": "-1", "Cel3": "-1", "Cel4": "-1"}
        lines.append("\t".join(v.get(h, "") for h in head))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes((nl.join(lines) + nl).encode("utf-8"))


@lru_cache(maxsize=None)
def d2r_maps() -> dict:
    """{D2R map: {automap LevelName}} of every D2R .ds1 a D2R level (or maze room, prest_type) of a type uses."""
    from hdkit.view.mapview import world
    roots = world.Roots()
    t = world.Tables(roots, "d2r")
    names = {world.num(r.get("Id"), j): r.get("Name") for j, r in enumerate(world.read_table(roots.d2r / "excel" /
                                                                                             "lvltypes.txt"))}
    maps = defaultdict(set)
    for r in t.prest:
        lid = world.num(r.get("LevelId"), -1)
        lv = t.levels.get(lid) if lid else None
        lt = names.get(world.num(lv.get("LevelType"), -1)) if lv else prest_type(r.get("Name"), names.values())
        if lt and lt != "None":
            for f in (r.get("File%d" % k, "").strip() for k in range(1, 7)):
                if f and f != "0":
                    maps[world.norm(f)[:-4]].add(ar.level_type_name(lt))
    return dict(maps)


@lru_cache(maxsize=None)
def _d2r_map_keys(key: str) -> frozenset:
    from hdkit.view.mapview import ds1, world
    p = world.Roots().tile_file(key + ".ds1", "d2r")
    if p is None:
        return frozenset()
    return frozenset((ar.CODES[o], st, sq) for _x, _y, o, st, sq in ar.tiles(ds1.Ds1.read(p)) if o < len(ar.CODES))


def stock_map_keys(lt: str) -> frozenset:
    """Every (code, style, sequence) D2R's own maps of automap type lt draw (D2R's .ds1): never given a row, even where
    the key is not in a stock tile set (D2R's Act 5 lava rooms hold a key only Median's added sets have)."""
    return frozenset().union(*[_d2r_map_keys(k) for k, lts in d2r_maps().items() if lt in lts])


def check_stock(base: Path, built: Path, types: list) -> tuple:
    """(problems, maps, keys): a wall tile of a D2R map (D2R's .ds1) of one of these level types whose automap cells
    differ between the base and the built automap.txt. No problem = every stock level of those types keeps its minimap."""
    problems, maps, n = [], 0, 0
    for key, lts in sorted(d2r_maps().items()):
        keys = _d2r_map_keys(key)
        mine = [lt for lt in lts if lt in types]
        maps += bool(keys and mine)
        for lt in mine:
            a, b = ar.read_rows(base, lt), ar.read_rows(built, lt)
            for k in keys:
                n += 1
                if ar.lookup(a, *k) != ar.lookup(b, *k):
                    problems.append("%s (%s): %s %d %d changes" % (key, lt, *k))
    return problems, maps, n


def main(argv=None) -> int:
    global MOD_OBJECTS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", nargs="?")
    ap.add_argument("--plan", default=None, help="where to write the plan (default: OUT's mod folder/automap_plan.json)")
    ap.add_argument("--map", action="append", default=None)
    ap.add_argument("--base", default=None, help="the automap.txt to add to (default: D2R's)")
    ap.add_argument("--d2r", default=None, help="D2R's extract (the folder holding data/)")
    ap.add_argument("--objects", default=None, help="Median's objects.txt (default: the mod extract's)")
    ap.add_argument("--list", action="store_true", help="print the map list and stop")
    a = ap.parse_args(argv)
    if a.d2r:
        ar.D2R = Path(a.d2r) / "data"
    MOD_OBJECTS = a.objects
    if a.list:
        for m in map_list():
            print(m, ", ".join(level_types(open_map(m))) or "(no level)")
        return 0
    if not a.out:
        ap.error("OUT is needed")
    a.base = Path(a.base or ar.D2R / "global" / "excel" / "automap.txt")
    rows, plan = new_rows(a.map or map_list(), a.base)
    out = Path(a.out)
    write(a.base, rows, out)
    problems, nmaps, ntiles = check_stock(a.base, out, list(plan["report"]))
    plan["stock_check"] = {"maps": nmaps, "keys": ntiles, "problems": problems}
    pp = Path(a.plan) if a.plan else (out.parents[3] / "automap_plan.json" if len(out.parents) > 3 else
                                      out.with_suffix(".plan.json"))
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(json.dumps(plan, indent=1), encoding="utf-8")
    print(json.dumps(plan["report"], indent=1))
    print("automap_rows: %d rows added for %d maps -> %s (plan %s); stock check: %d D2R maps, %d keys, %d changed" % (
        len(rows), sum(1 for m in plan["maps"].values() if m["rows_added"]), out, pp, nmaps, ntiles, len(problems)))
    for p in problems[:20]:
        print("automap_rows: STOCK CHANGED " + p, file=sys.stderr)
    return 1 if problems else 0


def load_plan(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.exit(main())
