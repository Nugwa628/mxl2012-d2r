"""Renumber the monster ids inside Median XL 2012's .ds1 map files for D2R's tables (adapted from another
port's ds1_remap.py; docs/maps-hd.md).

A .ds1 preset map lists "objects": (type, id, x, y, flags) and the engine resolves the id per act (the act is the .ds1
header's; D2R: PresetFileLoad 0x3dfae0):
  type 1 (monster/NPC): id below the act's MonPreset row count = that row; at or above it = the MonStats row itself (the
    engine keeps the raw id). Median 2012's MonStats has 1,822 rows (1.13c: 410); D2R appended its own rows after the
    1.13c ones, so every mod row from 410 up lands behind D2R's last row (the idmap lane's
    tools/idmap.py). The maps place Median-only monsters by raw MonStats row, so those ids must be renumbered.
  type 2 (object): (act, id) -> the act's ObjPreset table -> Objects row. Median 2012 ships no ObjPreset table (the 1.13c
    engine's own is used), its Objects.txt keeps the 574 vanilla rows in order, so D2R's per-act ObjPreset.txt (the 1.13c
    table plus D2R's additions) already resolves every id: nothing is renumbered, ids D2R's table lacks are only reported.

Ids come from the idmap lane's tools/idmap.py (docs/id-mapping.md): `IdMap.build(MOD_EXCEL, D2R_EXCEL)`, then
  monstats  mod row -> final id (`spaces["monstats"].ids()`), used for every raw type-1 id;
  objects   mod row -> final id: Median keeps D2R's 574 rows in place, so type-2 ids stay (checked, `Maps.moved_objects`);
  superuniques  no .ds1 holds a superunique id: monpreset.txt's Place column names them by key. Median's rows from 43 up sit
    one id above vanilla (kept as Median ran them), so `Maps.superunique_ids` lists the shifted rows for the report.
The built monpreset.txt must keep Median's rows per act (59/61/43/29/59) so the "id below the act's count" rule is unchanged.

The id table is a data-step product (tools/objstr.py writes `work/mod/ds1_ids.json`): remap_tree() without a `Maps` reads it,
so tools/install_mod.py renumbers the installed maps without the extract of the original mod or of D2R (lane objstr:
tools/objstr.py checks that D2R's ObjPreset resolves every object id of the maps, docs/id-mapping.md "Objects and ObjPreset").

  py -3 -I tools/ds1_remap.py --check TILES_DIR [--mod EXCEL] [--d2r EXCEL]   count what would change, write nothing
  py -3 -I tools/ds1_remap.py TILES_DIR [--mod EXCEL] [--d2r EXCEL]           rewrite the .ds1 files under TILES_DIR in place (use a copy)
  py -3 -I tools/ds1_remap.py --ids-file FILE TILES_DIR                       the same with the ids of work/mod/ds1_ids.json
"""
import argparse
import csv
import json
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
IDS_FILE = ROOT / "work" / "mod" / "ds1_ids.json"     # written by tools/objstr.py (the data step)


class Ds1:
    """Header + layers + object list of a .ds1 (version 2..18); offsets so the object block can be rewritten."""

    def __init__(self, data: bytes):
        self.data = data
        o = 0

        def i32():
            nonlocal o
            v = struct.unpack_from("<i", data, o)[0]
            o += 4
            return v

        self.version = i32()
        self.width = i32() + 1
        self.height = i32() + 1
        self.act = i32() if self.version >= 8 else 0
        self.tag_type = i32() if self.version >= 10 else 0
        self.files = []
        if self.version >= 3:
            for _ in range(i32()):
                e = data.index(b"\0", o)
                self.files.append(data[o:e].decode("latin1"))
                o = e + 1
        if 9 <= self.version <= 13:
            o += 8
        walls = i32() if self.version >= 4 else 1
        floors = i32() if self.version >= 16 else 1
        self.walls, self.floors = walls, floors
        self.layers_at = o  # wall1, orient1, wall2, orient2, ..., floor1.., shadow, [tag]: width*height dwords each
        o += (walls * 2 + floors + 1 + (1 if self.tag_type in (1, 2) else 0)) * self.width * self.height * 4
        self.objects = []
        self.count_at = o
        if self.version >= 2:
            n = i32()
            for _ in range(n):
                if o + (20 if self.version >= 5 else 16) > len(data):
                    raise ValueError("object block runs past the end of the file")
                t, i, x, y = struct.unpack_from("<4i", data, o)
                o += 16
                f = 0
                if self.version >= 5:
                    f = i32()
                self.objects.append([t, i, x, y, f])
        self.end_at = o
        if o > len(data):
            raise ValueError("object block runs past the end of the file")

    def cells(self, index: int):
        """Layer `index` of the layer stream as a tuple of width*height dwords."""
        n = self.width * self.height
        return struct.unpack_from(f"<{n}I", self.data, self.layers_at + index * n * 4)

    def wall_layers(self):
        """[(wall cells, orientation cells)] for each wall layer."""
        return [(self.cells(2 * j), self.cells(2 * j + 1)) for j in range(self.walls)]

    def floor_layers(self):
        return [self.cells(self.walls * 2 + j) for j in range(self.floors)]

    def pack(self) -> bytes:
        out = bytearray(self.data[: self.count_at])
        out += struct.pack("<i", len(self.objects))
        for t, i, x, y, f in self.objects:
            out += struct.pack("<4i", t, i, x, y)
            if self.version >= 5:
                out += struct.pack("<i", f)
        return bytes(out) + self.data[self.end_at:]


def cell_key(c: int):
    """(style, sequence) of a wall/floor cell dword: bits 20-25 and 8-13 (ds1edit layout)."""
    return (c >> 20) & 0x3F, (c >> 8) & 0x3F


def rd_tsv(path: Path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        return list(csv.reader(f, delimiter="\t"))


class Maps:
    """What the remap needs from the built tables and the ID map."""

    def __init__(self, monster, preset_counts: dict, object_slots: dict | None = None, object_ids: dict | None = None,
                 superunique_ids: dict | None = None):
        """monster: callable mod monstats row -> final id (None = unknown); preset_counts: act (1-based) -> MonPreset rows;
        object_slots: act (1-based) -> set of ObjPreset indexes D2R has (None = do not check); object_ids / superunique_ids:
        mod row -> final id of the objects / superuniques spaces (None = not known)."""
        self.monster = monster
        self.presets = dict(preset_counts)
        self.object_slots = object_slots
        self.object_ids = object_ids
        self.superunique_ids = superunique_ids
        self.monster_rows = 0       # rows of the mod's monstats (to_json), set by from_idmap

    @classmethod
    def from_idmap(cls, m, preset_counts: dict, object_slots: dict | None = None):
        """m: an idmap.IdMap (or anything with .spaces[entity].ids())."""
        ids = lambda e: m.spaces[e].ids() if e in m.spaces else None   # noqa: E731
        mon = ids("monstats")
        maps = cls(mon.get if mon is not None else (lambda r: None), preset_counts, object_slots, ids("objects"),
                   ids("superuniques"))
        maps.monster_rows = max(mon) + 1 if mon else 0
        return maps

    @classmethod
    def build(cls, mod_excel: Path, d2r_excel: Path | None = None, built_excel: Path | None = None):
        """Run tools/idmap.py on the mod's tables. preset counts come from `built_excel` (the built tables; default the
        mod's: Median's rows per act are kept)."""
        import idmap
        d2r = idmap.find_d2r(str(d2r_excel) if d2r_excel else None)
        if d2r is None:
            raise SystemExit("no D2R excel folder with base/skills.txt (--d2r or MXL2012_D2R_EXCEL)")
        m = idmap.IdMap.build(Path(mod_excel), d2r)
        return cls.from_idmap(m, preset_counts_of(Path(built_excel or mod_excel)), object_slots_of(d2r))

    @classmethod
    def load(cls, idmap_json: Path, excel: Path, d2r_excel: Path | None = None):
        """From the idmap.json that `tools/idmap.py build` wrote ({"spaces": {entity: {"rows": [{"row", "id"}]}}})."""
        sp = json.loads(Path(idmap_json).read_text("utf-8"))["spaces"]
        ids = lambda e: {r["row"]: r["id"] for r in sp[e]["rows"]} if e in sp else None   # noqa: E731
        mon = ids("monstats")
        return cls(mon.get if mon is not None else (lambda r: None), preset_counts_of(Path(excel)),
                   object_slots_of(Path(d2r_excel)) if d2r_excel else None, ids("objects"), ids("superuniques"))

    def to_json(self, monster_rows: int | None = None) -> dict:
        """What remap_bytes needs, for work/mod/ds1_ids.json: the final id of every mod monstats row (rows without one are
        left out: their objects are dropped) and the MonPreset rows per act."""
        mon = {}
        for r in range(self.monster_rows if monster_rows is None else monster_rows):
            n = self.monster(r)
            if n is not None:
                mon[str(r)] = n
        return {"monster": mon, "presets": {str(a): n for a, n in sorted(self.presets.items())}}

    @classmethod
    def from_json(cls, data: dict | Path | str):
        """The inverse of to_json (a path reads the file). Object slots are not known: type-2 ids are kept as they are."""
        if not isinstance(data, dict):
            data = json.loads(Path(data).read_text("utf-8"))
        mon = {int(r): n for r, n in data["monster"].items()}
        return cls(mon.get, {int(a): n for a, n in data["presets"].items()})

    @classmethod
    def default(cls):
        """The ids of the last data step (work/mod/ds1_ids.json) when it exists, else built from the extracts."""
        if IDS_FILE.exists():
            return cls.from_json(IDS_FILE)
        import maps_hd
        return cls.build(maps_hd.default_extract() / "data" / "global" / "excel")

    def monster_new(self, act0: int, i: int):
        """New id for a type-1 id, or None to drop (negative ids read outside D2R's table; rows past the map)."""
        if 0 <= i < self.presets.get(act0 + 1, 0):
            return i                    # a MonPreset row of the act: same table in the mod
        if i < 0:
            return None
        return self.monster(i)

    def object_valid(self, act0: int, i: int) -> bool:
        return self.object_slots is None or i in self.object_slots.get(act0 + 1, ())

    def moved_objects(self) -> list:
        """[(mod row, final id)] of Objects rows that change id. A type-2 id is an ObjPreset index (D2R's table, which names
        Objects rows by D2R's ids), so any move here would need ObjPreset's ObjectClass rewritten; Median has none."""
        return [(r, n) for r, n in sorted((self.object_ids or {}).items()) if r != n]

    def shifted_superuniques(self, since: int = 43) -> list:
        """Mod superunique rows from `since` up (the separator row of Median's table shifts them one above vanilla)."""
        return [(r, n) for r, n in sorted((self.superunique_ids or {}).items()) if r >= since]


def preset_counts_of(excel: Path) -> Counter:
    presets = Counter()
    for r in rd_tsv(Path(excel) / "monpreset.txt")[1:]:
        if r and r[0].isdigit():
            presets[int(r[0])] += 1
    return presets


def object_slots_of(d2r_excel: Path):
    """act (1-based) -> set of ObjPreset indexes in D2R's table, or None without the table."""
    d2r_excel = Path(d2r_excel)
    f = d2r_excel / "objpreset.txt"
    if not f.exists():
        f = d2r_excel / "base" / "objpreset.txt"
    if not f.exists():
        return None
    h, *rows = rd_tsv(f)
    ia, ii = h.index("Act"), h.index("Index")
    slots = {}
    for r in rows:
        if len(r) > max(ia, ii) and r[ia].isdigit() and r[ii].lstrip("-").isdigit():
            slots.setdefault(int(r[ia]), set()).add(int(r[ii]))
    return slots


def remap_bytes(data: bytes, maps: Maps, stats: Counter):
    """-> new bytes (the same object if nothing changed). Counts type1_renumbered / type1_dropped / type2_unresolved."""
    ds = Ds1(data)
    changed = False
    kept = []
    for obj in ds.objects:
        t, i = obj[0], obj[1]
        if t == 1:
            new = maps.monster_new(ds.act, i)
            if new is None:
                stats["type1_dropped"] += 1
                changed = True
                continue
            if new != i:
                stats["type1_renumbered"] += 1
                obj[1] = new
                changed = True
        elif t == 2 and not maps.object_valid(ds.act, i):
            stats["type2_unresolved"] += 1      # the engine skips it too; kept as is
        kept.append(obj)
    if not changed:
        return data
    ds.objects = kept
    return ds.pack()


def remap_tree(tiles: Path, maps: Maps | None = None, write: bool = True):
    """Renumber every .ds1 under `tiles` (in place unless write is False). maps=None: Maps.default()."""
    maps = maps or Maps.default()
    stats = Counter()
    files = changed = 0
    for p in sorted(Path(tiles).rglob("*.ds1")):
        files += 1
        data = p.read_bytes()
        new = remap_bytes(data, maps, stats)
        if new is not data and new != data:
            changed += 1
            if write:
                p.write_bytes(new)
    stats["files"] = files
    stats["files_changed"] = changed
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tiles", help="the tiles folder to read (and rewrite unless --check)")
    ap.add_argument("--mod", help="the mod's excel folder (default: the extract's data/global/excel)")
    ap.add_argument("--d2r", help="D2R's excel folder (with base/); default as tools/idmap.py finds it")
    ap.add_argument("--built", help="the built excel folder with monpreset.txt (default: the mod's)")
    ap.add_argument("--check", action="store_true", help="count only, write nothing")
    ap.add_argument("--ids-file", help="the id table of the data step (default: work/mod/ds1_ids.json when --mod is not given)")
    a = ap.parse_args()
    import maps_hd
    if a.ids_file or (not a.mod and IDS_FILE.exists()):
        maps = Maps.from_json(a.ids_file or IDS_FILE)
    else:
        mod = Path(a.mod) if a.mod else maps_hd.default_extract() / "data" / "global" / "excel"
        maps = Maps.build(mod, Path(a.d2r) if a.d2r else None, Path(a.built) if a.built else None)
    s = remap_tree(Path(a.tiles), maps, write=not a.check)
    print(("would change " if a.check else "changed ") + ", ".join(f"{k}={v}" for k, v in sorted(s.items())))


if __name__ == "__main__":
    main()
