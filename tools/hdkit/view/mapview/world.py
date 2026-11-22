"""Where a map's pieces come from: the .ds1, the .dt1 files the game loads for it, the act palette, and names for its
objects. Read-only over two extracts:

  mod   Median XL 2012's MPQ extract (tools/maps_hd.default_extract(): data/global/tiles, data/global/excel)
  d2r   D2R's own extract (tools/maps_hd.default_d2r(); tiles, excel, palette)

A map is named by its path below data/global/tiles without .ds1 ("act1/cathedrl/cathy3"). `source` "mod" reads the .ds1 and
the tables of the mod (falling back to D2R's tile files a mod tile set does not replace), "d2r" D2R's only; "auto" = mod when
the mod has the map. A working copy (mapview.edit) names its own .ds1 file with `ds1_path`.

Tile files (the game's rule, tools/maps_hd.py): the lvlprest rows whose File1..6 name the map -> their level's LevelType ->
the lvltypes row's File 1..32 selected by the row's Dt1Mask. A map no level uses (maze pieces, unused maps) falls back to
the file list ds1edit stored in the .ds1 (.tg1 read as .dt1). A key (orientation, style, sequence) resolves to the first
file in that order that has it; tiles of one key are rarity variants (picked per cell by a hash, see TileLib.pick).
"""
from __future__ import annotations

import collections
import csv
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

_TOOLS = Path(__file__).resolve().parents[3]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from . import ds1 as ds1mod  # noqa: E402
from . import dt1 as dt1mod  # noqa: E402


def norm(rel: str) -> str:
    p = str(rel).replace("\\", "/").strip().lower().lstrip("/")
    for pre in ("d2/data/global/tiles/", "data/global/tiles/"):
        if p.startswith(pre):
            p = p[len(pre):]
    return p


def read_table(path: Path) -> list:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return [dict(zip(rows[0], r)) for r in rows[1:]] if rows else []


def num(s, default=0):
    try:
        return int(str(s).strip())
    except ValueError:
        return default


def default_roots():
    import maps_hd
    return Path(maps_hd.default_extract()) / "data" / "global", Path(maps_hd.default_d2r()) / "data" / "global"


@lru_cache(maxsize=256)
def _listing(d: Path) -> dict:
    try:
        return {p.name.lower(): p for p in d.iterdir()}
    except OSError:
        return {}


def _ci_find(root: Path, rel: str) -> Path | None:
    cur = root
    for part in rel.split("/"):
        nxt = _listing(cur).get(part.lower())
        if nxt is None:
            return None
        cur = nxt
    return cur if cur.is_file() else None


_CASC = []


def casc_file(logical: str) -> bytes | None:
    """A base-game file the extracts lack (the act palettes), read through hdkit's CASC root (cached on disk after the first
    read; waits while a run holds the game folder). None when CASC cannot be opened."""
    try:
        if not _CASC:
            from .. import casc
            _CASC.append(casc.from_site())
        p = _CASC[0].find(logical)
        return Path(p).read_bytes() if p else None
    except Exception:       # no CascLib, no game folder, lock timeout: the caller falls back
        return None


@lru_cache(maxsize=256)
def _parse_dt1(path: str):
    return dt1mod.parse(Path(path).read_bytes())


class Roots:
    """The two extracts' data/global folders (either may be missing)."""

    def __init__(self, mod: Path | None = None, d2r: Path | None = None, casc: bool = True):
        self.casc = casc
        if mod is None or d2r is None:
            dm, dd = default_roots()
            mod = mod or dm
            d2r = d2r or dd
        self.mod, self.d2r = Path(mod), Path(d2r)

    def tables(self, source: str):
        return self.mod / "excel" if source == "mod" else self.d2r / "excel"

    def tile_file(self, rel: str, source: str) -> Path | None:
        order = (self.mod, self.d2r) if source == "mod" else (self.d2r,)
        for r in order:
            p = r / "tiles" / rel
            if p.exists():
                return p
            hit = _ci_find(r / "tiles", rel)          # the extracts keep the MPQ's case
            if hit:
                return hit
        return None

    def palette(self, act: int) -> np.ndarray:
        """256 x 3 uint8 RGB of act 1..5 (pal.dat is BGR)."""
        data = None
        for r in (self.d2r, self.mod):
            p = r / "palette" / ("act%d" % act) / "pal.dat"
            if p.exists():
                data = p.read_bytes()
                break
        if data is None and self.casc:
            data = casc_file("global/palette/act%d/pal.dat" % act)
        if data is None:
            self.palette_note = "no act palette found: grey ramp"
            g = np.arange(256, dtype=np.uint8)
            return np.stack([g, g, g], 1)
        d = np.frombuffer(data[:768], np.uint8).reshape(256, 3)
        return d[:, ::-1].copy()

    def maps(self, source: str = "mod") -> list:
        base = (self.mod if source == "mod" else self.d2r) / "tiles"
        if not base.exists():
            return []
        return sorted(p.relative_to(base).as_posix()[:-4].lower() for p in base.rglob("*.ds1"))


class Tables:
    """levels / lvlprest / lvltypes / monstats / monpreset / objects of one source, objpreset from D2R's when the source
    has none (Median ships none: the engine's own resolves its ids, tools/ds1_remap.py)."""

    def __init__(self, roots: Roots, source: str):
        ex = roots.tables(source)
        self.levels = {num(r.get("Id"), -1): r for r in read_table(ex / "levels.txt")}
        self.prest = read_table(ex / "lvlprest.txt")
        self.types = {}
        for j, r in enumerate(read_table(ex / "lvltypes.txt")):
            self.types[num(r.get("Id"), j)] = r
        self.monstats = [r.get("Id", "") for r in read_table(ex / "monstats.txt")]
        self.monpreset = collections.defaultdict(list)
        for r in read_table(ex / "monpreset.txt"):
            if r.get("Act", "").strip().isdigit():
                self.monpreset[int(r["Act"])].append(r.get("Place", ""))
        self.objects = [(r.get("Class", ""), r.get("Name", "")) for r in read_table(ex / "objects.txt")]
        self.object_row = {}
        for i, (cls, _n) in enumerate(self.objects):
            self.object_row.setdefault(cls.strip().lower(), i)
        self.objpreset = {}
        op = ex / "objpreset.txt"
        if not op.exists():
            op = roots.d2r / "excel" / "objpreset.txt"
        for r in read_table(op):
            if r.get("Act", "").isdigit() and r.get("Index", "").lstrip("-").isdigit():
                self.objpreset[(int(r["Act"]), int(r["Index"]))] = r.get("ObjectClass", "")

    def usage(self, key: str) -> list:
        """[(lvlprest row, level id, mask)] of the rows that name map `key`."""
        out = []
        for r in self.prest:
            for k in range(1, 7):
                f = r.get("File%d" % k, "").strip()
                if f and f != "0" and norm(f)[:-4] == key:
                    out.append((r, num(r.get("LevelId")), num(r.get("Dt1Mask"))))
        return out

    def object_name(self, act: int, t: int, ident: int) -> str:
        """act 1..5."""
        if t == 1:
            pre = self.monpreset.get(act, [])
            if 0 <= ident < len(pre):
                return "monpreset:%s" % pre[ident]
            if 0 <= ident < len(self.monstats):
                return "monstats:%s" % self.monstats[ident]
            return "monster #%d" % ident
        if t == 2:
            cls = self.objpreset.get((act, ident))
            if cls is None:
                return "object #%d (no objpreset)" % ident
            row = self.object_row.get(cls.strip().lower())
            nm = self.objects[row][1] if row is not None else ""
            return "%s%s" % (cls, (" (%s)" % nm) if nm and nm.lower() != cls.lower() else "")
        return "type %d #%d" % (t, ident)


class TileLib:
    """Key -> rarity variants, over the ordered tile files of one map."""

    def __init__(self, files: list, parse=None):
        """files: [(rel path, Path or bytes)] in the game's order."""
        self.files = files
        self.by_key = {}
        self.file_of = {}
        for rel, p in files:
            try:
                tiles = dt1mod.parse(p) if isinstance(p, (bytes, bytearray)) else _parse_dt1(str(p))
            except (OSError, ValueError):
                continue
            mine = set()
            for tl in tiles:
                k = (tl.orientation, tl.main, tl.sub)
                if k in self.by_key and k not in mine:
                    continue            # an earlier file has the key: it wins
                mine.add(k)
                self.by_key.setdefault(k, []).append(tl)
                self.file_of.setdefault(k, rel)

    def variants(self, orientation: int, style: int, seq: int):
        return self.by_key.get((orientation, style, seq), [])

    def pick(self, orientation: int, style: int, seq: int, x: int, y: int):
        """One variant for a cell: weighted by rarity (all 0: the first). The game draws one at random per level seed;
        this is a stand-in that hashes (x, y), so renders are stable."""
        v = self.variants(orientation, style, seq)
        if not v:
            return None
        if len(v) == 1:
            return v[0]
        w = [max(tl.rarity, 0) for tl in v]
        tot = sum(w)
        if tot <= 0:
            return v[0]
        h = ((x * 73856093) ^ (y * 19349663) ^ (orientation * 83492791)) & 0x7FFFFFFF
        r = h % tot
        for tl, wi in zip(v, w):
            if r < wi:
                return tl
            r -= wi
        return v[-1]


class MapSource:
    def __init__(self, key: str, source: str = "auto", roots: Roots | None = None, ds1_path=None, tables=None):
        self.roots = roots or Roots()
        key = norm(key)
        if key.endswith(".ds1"):
            key = key[:-4]
        self.key = key
        if source == "auto":
            source = "mod" if self.roots.tile_file(key + ".ds1", "mod") else "d2r"
        self.source = source
        if ds1_path is None:
            ds1_path = self.roots.tile_file(key + ".ds1", source)
            if ds1_path is None:
                raise FileNotFoundError("no map %s.ds1 in the %s extract" % (key, source))
        self.ds1_path = Path(ds1_path)
        self.ds = ds1mod.Ds1.read(self.ds1_path)
        self.tables = tables or Tables(self.roots, source)
        self.notes = []
        self.levels = []
        self.files = self._files()
        self.lib = TileLib([(rel, p) for rel, p in self.files if p is not None])
        self.act = self._act()
        self.palette = self.roots.palette(self.act)

    def reload_ds1(self):
        self.ds = ds1mod.Ds1.read(self.ds1_path)

    def _files(self):
        out, seen = [], set()
        for r, lid, mask in self.tables.usage(self.key):
            lv = self.tables.levels.get(lid)
            lt = self.tables.types.get(num(lv.get("LevelType"), -1)) if lv else None
            if lt is None:
                continue
            self.levels.append({"lvlprest": r.get("Name"), "level": lid, "level_name": lv.get("Name") if lv else None,
                                "level_type": lt.get("Name"), "dt1_mask": mask})
            for b in range(32):
                if mask >> b & 1:
                    f = (lt.get("File %d" % (b + 1)) or "0").strip()
                    if f not in ("", "0"):
                        rel = norm(f)
                        if rel not in seen:
                            seen.add(rel)
                            out.append((rel, self.roots.tile_file(rel, self.source)))
        if not out:
            self.notes.append("no level uses this map: tile files from the .ds1's own (ds1edit) file list")
            for f in self.ds.files:
                rel = norm(f)
                if not rel.endswith((".tg1", ".dt1")):
                    continue
                rel = rel[:-4] + ".dt1"
                if rel not in seen:
                    seen.add(rel)
                    out.append((rel, self.roots.tile_file(rel, self.source)))
        missing = [rel for rel, p in out if p is None]
        if missing:
            self.notes.append("tile files not found: %s" % ", ".join(missing))
        return out

    def _act(self) -> int:
        acts = [num(self.tables.levels[lv["level"]].get("Act")) + 1 for lv in self.levels
                if lv["level"] in self.tables.levels]
        a = acts[0] if acts else self.ds.act + 1
        return max(1, min(5, a))

    def object_name(self, t: int, ident: int) -> str:
        return self.tables.object_name(self.ds.act + 1, t, ident)

    def describe(self) -> dict:
        d = self.ds
        return {"map": self.key, "source": self.source, "ds1": str(self.ds1_path), "version": d.version,
                "size_cells": [d.width, d.height], "act": self.act, "act_header": d.act + 1, "wall_layers": d.n_walls,
                "floor_layers": d.n_floors, "objects": len(d.objects), "levels": self.levels,
                "dt1_files": [{"file": rel, "path": str(p) if p else None} for rel, p in self.files], "notes": self.notes}
