"""Rename audit: art / file / sound names the mod ships that D2R renamed or that exist nowhere (lane renamesweep).

Bug #518 was one cell: objects.txt row 194 (UnfoldingStairLeft) kept 1.13c's Token `sl`, D2R renamed that art `9c` and has
no `sl`, so the stair never unfolded. This tool looks for every other cell of that class, in every migrated table that
names art, a file or a sound. Per cell it compares four values of the same row:

  M  Median XL 2012 v005's value (work/named, the prep output)
  V  vanilla's value: the 1.14d `.bin` table of the native install (gamedata/game/Patch_D2.mpq; 1.14d's data is 1.13c's).
     A `.bin` has no column names, so V is read by looking for M and D as NUL-ended strings inside the row's record:
     `M` / `D` = only that one is in the record, `both`, or `?` (neither, or no record)
  D  D2R 93847's value of the matching row (same id for an indexed table, same key for a keyed one)
  B  the built value (work/mod/data/global/excel, what the release ships)

and where the asset that B (and M, D) names exists: `d` D2R's CASC (filelist.txt), `m` the mod's own files (work/mod/data
after a full build, plus Median's classic tiles the install copies), `x` Median's MPQ (extract-mpq listfile), `v` the 1.14d
MPQs (looked up by name, so only for names the tool can spell: tokens by their COF names, files by path).

Verdicts (automatic; docs/txt-migrate.md "Rename audit" has the triage of each hit):
  renamed          M == V (Median kept vanilla's value), D2R's row holds another value whose asset D2R has, and B's asset
                   is in neither D2R nor the mod: the #518 class (fix: txt_migrate.D2R_RENAMED)
  renamed-fixed    the same, but B already is D's value (D2R_RENAMED or another step took it)
  renamed-exists   M == V, D differs, but B's asset exists too (D2R changed the row and kept the old art: harmless)
  missing-vanilla  B's asset is missing in D2R and the mod but 1.14d had it (D2R dropped it, no rename on the row)
  missing          B's asset exists nowhere the tool can see (also not in 1.14d: vanilla's own dead names, Median typos)
  median-missing   Median's own value (M != V or a row of Median's own) whose asset exists nowhere
  renamed-emptied  M == V, D2R renamed it, and the build emptied the cell (a reference cleaned as dangling): D's value fits
  emptied          the build emptied Median's value and its asset exists nowhere (art_fix's "null", a dangling sound key)
Rows whose asset exists are not listed (counted as `ok`), nor rows whose built value is D2R's own and whose asset D2R lacks too
(`d2r-same`: unmodded D2R behaves the same; D2R's sound rows on `none.flac` are such).

  py -3 -I tools/rename_audit.py [--bank rotw|base] [--out DIR] [--table T ...]
Writes DIR/rename_audit.tsv (one line per hit) and DIR/rename_audit.md (counts per table and verdict); default DIR work/mod.
"""
from __future__ import annotations

import argparse
import os
import struct
import tempfile
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import idmap  # noqa: E402

ROOT = fxpaths.ROOT
NAMED = ROOT / "work" / "named"
BUILT = ROOT / "work" / "mod" / "data" / "global" / "excel"
MOD_DATA = ROOT / "work" / "mod" / "data"
D2R_EXCEL = fxpaths.D2R_EXCEL
MXL_LISTFILE = fxpaths.MXL_ROOT / "_listfile.txt"
# the native 1.14d install (CLAUDE.md approved exception: gamedata/ inside the project, read-only here)
VANILLA_DIR = Path(os.environ.get("MXL_VANILLA_114D") or ROOT.parent.parent / "gamedata" / "game")
VANILLA_MPQS = ("Patch_D2.mpq", "d2exp.mpq", "d2data.mpq", "d2char.mpq", "d2sfx.mpq", "d2speech.mpq", "d2xtalk.mpq",
                "d2music.mpq", "d2xmusic.mpq", "d2xvideo.mpq", "d2video.mpq")
BIN_MPQS = ("Patch_D2.mpq", "d2exp.mpq", "d2data.mpq")  # the first that has the table wins

OBJ_MODES = ("NU", "OP", "ON", "S1", "S2", "S3", "S4", "S5")
MON_MODES = ("NU", "WL", "A1", "GH", "DT", "DD", "A2", "BL", "SC", "S1", "S2", "S3", "S4", "RN")
MON_WCLASS = ("HTH", "1HS", "2HS", "1HT", "2HT", "BOW", "XBW", "STF", "1SS", "1JS", "1ST", "1JT", "HT1", "HT2")

SOUND_COLS = {
    "missiles": ("TravelSound", "HitSound", "ProgSound"),
    "overlay": ("StartSound",),
    "states": ("onsound", "offsound"),
    "skills": ("stsound", "dosound", "dosound a", "dosound b", "tgtsound", "prgsound", "ItemCastSound"),
    "weapons": ("dropsound", "usesound"), "armor": ("dropsound", "usesound"), "misc": ("dropsound", "usesound"),
    "uniqueitems": ("dropsound", "usesound"), "setitems": ("dropsound", "usesound"),
    "monsounds": ("Attack1", "Weapon1", "Attack2", "Weapon2", "HitSound", "DeathSound", "Skill1", "Skill2", "Skill3",
                  "Skill4", "Footstep", "FootstepLayer", "Neutral", "Init", "Taunt", "Flee"),
    "soundenviron": ("Song", "Day Ambience", "Night Ambience", "Day Event", "Night Event"),
}
ITEM_FILES = ("invfile", "uniqueinvfile", "setinvfile", "flippyfile")
# table -> {column: asset kind}
ASSETS: dict[str, dict[str, str]] = {
    "objects": {"Token": "objtoken"},
    "monstats": {"Code": "montoken"},
    "missiles": {"CelFile": "missile"},
    "overlay": {"Filename": "overlay"},
    "weapons": {**{c: "item" for c in ITEM_FILES}, "alternategfx": "altgfx"},
    "armor": {**{c: "item" for c in ITEM_FILES}, "alternategfx": "altgfx"},
    "misc": {c: "item" for c in ITEM_FILES},  # misc alternategfx is never drawn on a character
    "uniqueitems": {"invfile": "item", "flippyfile": "item"},
    "setitems": {"invfile": "item", "flippyfile": "item"},
    "itemtypes": {f"InvGfx{i}": "item" for i in range(1, 7)},
    "lvlprest": {f"File{i}": "tile" for i in range(1, 7)},
    "lvltypes": {f"File {i}": "tile" for i in range(1, 33)},
    "sounds": {"FileName": "sfx"},
}
for _t, _cols in SOUND_COLS.items():
    ASSETS.setdefault(_t, {}).update({c: "sound" for c in _cols})
# keyed tables: key column (the others are idmap entities, matched by id)
KEYED = {"weapons": "code", "armor": "code", "misc": "code", "itemtypes": "Code", "uniqueitems": "index",
         "setitems": "index", "sounds": "Sound"}
EMPTY = {"", "0", "none", "null", "xxx", "-1", "none.wav", "none.flac"}  # none.*: D2R's own "no file" sound
# alternategfx is drawn only on these body locations (helm HD layer, shield / weapon hand layers); itemtypes BodyLoc1/2
ALT_BODYLOCS = {"head", "rarm", "larm"}


def norm(v: str) -> str:
    return v.strip().replace("/", "\\").lower()


# ---------------------------------------------------------------------------------------------------------------- files
class Files:
    """Lower-case data paths ('data/global/...') of D2R's CASC, the mod's built files, Median's MPQ; 1.14d by lookup."""

    def __init__(self, d2r_list: Path, mod_data: Path, mxl_list: Path, vanilla_dir: Path):
        self.d2r = set()
        if d2r_list.exists():
            for line in d2r_list.read_text(encoding="utf-8", errors="replace").splitlines():
                p = line.strip().lower().replace("\\", "/")
                if p.startswith("data:"):
                    p = p[5:]
                self.d2r.add(p)
        self.mod = set()
        if mod_data.exists():
            for p in mod_data.rglob("*"):
                if p.is_file():
                    self.mod.add("data/" + p.relative_to(mod_data).as_posix().lower())
        self.mxl = set()
        if mxl_list.exists():
            self.mxl = {line.strip().lower().replace("\\", "/") for line in mxl_list.read_text(
                encoding="latin-1").splitlines() if line.strip()}
        # the install copies Median's classic tiles (tools/install_mod.py)
        self.mod |= {p for p in self.mxl if p.startswith("data/global/tiles/")}
        self._dirs: dict[str, set[str]] = {}
        self.vanilla = Vanilla(vanilla_dir)

    def dirs(self, which: str) -> set[str]:
        if which not in self._dirs:
            s = set()
            for p in getattr(self, which):
                parts = p.split("/")
                for i in range(1, len(parts)):
                    s.add("/".join(parts[:i]) + "/")
            self._dirs[which] = s
        return self._dirs[which]

    def has(self, which: str, path: str) -> bool:
        return path.lower() in getattr(self, which)

    def has_dir(self, which: str, prefix: str) -> bool:
        return prefix.lower() in self.dirs(which)


class Vanilla:
    """The 1.14d MPQs, opened read-only through tools/native.py's StormLib.

    Names are checked with SFileFindFirstFile over an external listfile of the candidate names: only names in an MPQ's hash
    table come back. (SFileHasFile and SFileOpenFileEx answer TRUE for any name on these archives, so they are not used.)"""

    def __init__(self, folder: Path):
        self.handles = []
        self.folder = folder
        self.found: set[str] = set()
        self.asked: set[str] = set()
        try:
            import native
        except Exception:  # noqa: BLE001  (no StormLib build: the v column stays empty)
            return
        self.native = native
        for name in VANILLA_MPQS:
            p = folder / name
            if not p.exists():
                p = next((q for q in folder.glob("*") if q.name.lower() == name.lower()), p) if folder.exists() else p
            if p.exists():
                try:
                    self.handles.append((p.name.lower(), native.open_mpq(p)))
                except OSError:
                    pass

    @property
    def available(self) -> bool:
        return bool(self.handles)

    def lookup(self, paths, mpqs: tuple[str, ...] | None = None) -> set[str]:
        """The names of `paths` (any separator / case) that exist, in all MPQs or only those of `mpqs`; lower case, '/'."""
        names = sorted({p.replace("/", "\\").lower() for p in paths})
        if not names or not self.handles:
            return set()
        fd, lf = tempfile.mkstemp(suffix=".txt", prefix="rename_audit_")  # projtemp: inside the project
        try:
            os.write(fd, "\r\n".join(names).encode("latin-1", errors="replace"))
            os.close(fd)
            out = set()
            for name, h in self.handles:
                if mpqs is None or name in {m.lower() for m in mpqs}:
                    out |= {n.lower().replace("\\", "/") for n, _ in self.native.mpq_files(h, lf)}
            return out & {n.replace("\\", "/") for n in names}
        finally:
            os.unlink(lf)

    def prefetch(self, paths) -> None:
        new = {p.lower().replace("\\", "/") for p in paths} - self.asked
        self.found |= self.lookup(new)
        self.asked |= new

    def has(self, path: str) -> bool:
        key = path.lower().replace("\\", "/")
        if key not in self.asked:
            self.prefetch([key])
        return key in self.found

    def read(self, path: str, mpqs: tuple[str, ...] = BIN_MPQS) -> bytes | None:
        """The file from the first of `mpqs` that has it."""
        key = path.replace("/", "\\")
        for want in mpqs:
            if not self.lookup([key], (want,)):
                continue
            for name, h in self.handles:
                if name == want.lower():
                    with tempfile.TemporaryDirectory(prefix="rename_audit_") as d:  # projtemp: inside the project
                        out = Path(d) / "f.bin"
                        if self.native.extract(h, key, out) and out.exists():
                            return out.read_bytes()
        return None


def candidates(kind: str, value: str) -> tuple[list[str], list[str]]:
    """(exact file paths, directory prefixes) where an asset of `kind` named `value` would be; all lower case."""
    v = value.strip().replace("\\", "/").lower()
    if kind == "objtoken":
        return [f"data/global/objects/{v}/cof/{v}{m.lower()}hth.cof" for m in OBJ_MODES], [f"data/global/objects/{v}/cof/"]
    if kind == "montoken":
        return ([f"data/global/monsters/{v}/cof/{v}{m.lower()}{w.lower()}.cof" for m in MON_MODES for w in MON_WCLASS],
                [f"data/global/monsters/{v}/cof/"])
    if kind in ("missile", "overlay"):
        folder = "missiles" if kind == "missile" else "overlays"
        base = v[:-4] if v.endswith((".dcc", ".dc6")) else v
        return [f"data/global/{folder}/{base}.dcc", f"data/global/{folder}/{base}.dc6"], []
    if kind == "item":
        base = v[:-4] if v.endswith(".dc6") else v
        return [f"data/global/items/{base}.dc6"], []
    if kind == "tile":
        return [f"data/global/tiles/{v}"], []
    if kind == "sfx":
        stem = v.rsplit(".", 1)[0] if "." in v.rsplit("/", 1)[-1] else v
        return [f"data/{s}/sfx/{stem}.{e}" for s in ("global", "local") for e in ("wav", "flac")], []
    return [], []


class Resolver:
    def __init__(self, files: Files, sounds: dict[str, str], altgfx: dict[str, set[str]]):
        self.f, self.sounds, self.altgfx = files, sounds, altgfx

    def where(self, kind: str, value: str) -> str:
        """Letters of the places the asset exists: d (D2R), m (mod), x (Median's MPQ), v (1.14d); '-' none; '' n/a."""
        if norm(value) in EMPTY:
            return ""
        if kind == "sound":
            fn = self.sounds.get(norm(value))
            if fn is None:
                return "-key"
            return self.where("sfx", fn) if norm(fn) not in EMPTY else ""
        if kind == "altgfx":
            v = norm(value)
            return "".join(c for c in "dmx" if v in self.altgfx.get(c, set())) or "-"
        files, dirs = candidates(kind, value)
        out = ""
        for which, letter in (("d2r", "d"), ("mod", "m"), ("mxl", "x")):
            if any(self.f.has(which, p) for p in files) or any(self.f.has_dir(which, p) for p in dirs):
                out += letter
        if self.f.vanilla.available and any(self.f.vanilla.has(p) for p in files):
            out += "v"
        return out or "-"


def alt_tokens(files: Files) -> dict[str, set[str]]:
    """alternategfx tokens per source: player composite DCCs data/global/chars/<cc>/<pp>/<cc><pp><alt><mode><wc>.dcc."""
    out = {}
    for which, letter in (("d2r", "d"), ("mod", "m"), ("mxl", "x")):
        s = set()
        for p in getattr(files, which):
            if p.startswith("data/global/chars/") and p.endswith(".dcc"):
                name = p.rsplit("/", 1)[-1]
                if len(name) >= 14:
                    s.add(name[4:7])
        out[letter] = s
    return out


# ---------------------------------------------------------------------------------------------------------------- .bin
class BinTable:
    """A 1.14d .bin: u32 count + fixed-size records; values are found as NUL-ended strings inside a record."""

    def __init__(self, data: bytes):
        self.n = struct.unpack_from("<I", data)[0] if len(data) >= 4 else 0
        self.size = (len(data) - 4) // self.n if self.n else 0
        self.data = data
        self.by_key: dict[str, int] | None = None

    def record(self, i: int) -> bytes | None:
        if i is None or not 0 <= i < self.n:
            return None
        return self.data[4 + i * self.size: 4 + (i + 1) * self.size]

    def index_keys(self, first_key: str, keys: list[str]) -> None:
        """Map key text -> record using the key field's offset, found from the first D2R key in record 0."""
        r0 = self.record(0)
        off = find_str(r0, first_key) if r0 else None
        self.by_key = {}
        if off is None:
            return
        for i in range(self.n):
            r = self.record(i)
            end = r.find(b"\0", off)
            k = r[off:end if end >= 0 else None].decode("latin-1").lower()
            self.by_key.setdefault(k, i)


def find_str(rec: bytes | None, value: str) -> int | None:
    if not rec or not value:
        return None
    b = value.encode("latin-1", errors="replace")
    start = 0
    while True:
        i = rec.find(b + b"\0", start)
        if i < 0:
            return None
        if i == 0 or rec[i - 1] == 0:
            return i
        start = i + 1


def find_ci(rec: bytes | None, value: str) -> bool:
    if not rec or not value:
        return False
    return find_str(rec.lower(), value.lower()) is not None


def vanilla_value(rec: bytes | None, m: str, d: str) -> str:
    if rec is None:
        return "?"
    fm, fd = find_ci(rec, m), find_ci(rec, d)
    if norm(m) == norm(d):
        return "M" if fm else "?"
    return {(True, False): "M", (False, True): "D", (True, True): "both"}.get((fm, fd), "?")


def vanilla_candidates(built_dir: Path, d2r_dir: Path, sounds: dict[str, str], tables: list[str] | None) -> set[str]:
    """Every file name the audit may ask the 1.14d MPQs for (one batched lookup instead of one per cell)."""
    out = set()
    for fn in sounds.values():
        out.update(candidates("sfx", fn)[0])
    for table, cols in ASSETS.items():
        if tables and table not in tables:
            continue
        for folder in (built_dir, d2r_dir, NAMED):
            if not (folder / f"{table}.txt").exists():
                continue
            h, rows = read(folder / f"{table}.txt")
            for col, kind in cols.items():
                if col in h and kind not in ("sound", "altgfx"):
                    for r in rows:
                        v = cell(h, r, col)
                        if norm(v) not in EMPTY:
                            out.update(candidates(kind, v)[0])
    return out


def item_types(path: Path) -> dict[str, tuple[set[str], list[str]]]:
    """itemtypes Code (lower) -> (BodyLoc1/2, Equiv1/2)."""
    if not path.exists():
        return {}
    h, rows = read(path)
    return {cell(h, r, "Code").lower(): ({cell(h, r, "BodyLoc1").lower(), cell(h, r, "BodyLoc2").lower()} - {""},
                                         [cell(h, r, "Equiv1").lower(), cell(h, r, "Equiv2").lower()]) for r in rows}


def alt_drawn(code: str, types: dict, seen: set | None = None) -> bool:
    """True when an item of type `code` (or a type it is equivalent to) is worn where alternategfx is drawn."""
    seen = seen if seen is not None else set()
    code = code.lower()
    if not code or code in seen or code not in types:
        return False
    seen.add(code)
    locs, equiv = types[code]
    return bool(locs & ALT_BODYLOCS) or any(alt_drawn(e, types, seen) for e in equiv)


# ---------------------------------------------------------------------------------------------------------------- audit
def read(path: Path) -> tuple[list[str], list[list[str]]]:
    h, rows = idmap.read_tsv(path)
    return h, idmap.records(rows)


def cell(h: list[str], r: list[str] | None, c: str) -> str:
    if r is None or c not in h:
        return ""
    i = h.index(c)
    return r[i].strip() if i < len(r) else ""


def row_pairs(table: str, m: "idmap.IdMap | None", named: tuple, d2r: tuple, built: tuple):
    """(built index, built row, named row or None, d2r row or None, own) for every built row that is the mod's."""
    bh, brows = built
    nh, nrows = named
    dh, drows = d2r
    if table in KEYED:
        key = KEYED[table]
        dk = {cell(dh, r, key).lower(): r for r in drows}
        nk = {}
        for r in nrows:
            nk.setdefault(cell(nh, r, key).lower(), r)
        dset = {cell(dh, r, key).lower() for r in drows} if table == "sounds" else None
        for i, r in enumerate(brows):
            k = cell(bh, r, key).lower()
            if table == "sounds" and k in dset and k not in nk:
                continue  # D2R's own sound row
            yield i, r, nk.get(k), dk.get(k), k not in dk
        return
    space = m.spaces.get(table) if m else None
    if space is None:
        return
    for row in space.rows:
        if row.id >= len(brows):
            continue
        vanilla = row.kind == "vanilla"
        yield (row.id, brows[row.id], nrows[row.row] if row.row < len(nrows) else None,
               drows[row.id] if vanilla and row.id < len(drows) else None, not vanilla)


def audit(bank: str = "rotw", tables: list[str] | None = None, files: Files | None = None,
          vanilla_bins: dict[str, BinTable] | None = None) -> tuple[list[dict], Counter]:
    built_dir = BUILT if bank == "rotw" else BUILT / "base"
    d2r_dir = D2R_EXCEL if bank == "rotw" else D2R_EXCEL / "base"
    files = files or Files(fxpaths.D2R_FILELIST, MOD_DATA, MXL_LISTFILE, VANILLA_DIR)
    m = idmap.IdMap.build(NAMED, D2R_EXCEL)
    sh, srows = read(built_dir / "sounds.txt")
    sounds = {norm(cell(sh, r, "Sound")): cell(sh, r, "FileName") for r in srows}
    res = Resolver(files, sounds, alt_tokens(files))
    types = item_types(built_dir / "itemtypes.txt")
    if files.vanilla.available:
        files.vanilla.prefetch(vanilla_candidates(built_dir, d2r_dir, sounds, tables))
    hits, counts = [], Counter()
    for table, cols in ASSETS.items():
        if tables and table not in tables:
            continue
        if not (built_dir / f"{table}.txt").exists() or not (NAMED / f"{table}.txt").exists():
            continue
        built, named = read(built_dir / f"{table}.txt"), read(NAMED / f"{table}.txt")
        d2r = read(d2r_dir / f"{table}.txt") if (d2r_dir / f"{table}.txt").exists() else ([], [])
        vb = None
        if vanilla_bins is not None:
            vb = vanilla_bins.get(table)
        elif files.vanilla.available:
            data = files.vanilla.read(f"data/global/excel/{table}.bin")
            vb = BinTable(data) if data else None
        if vb is not None and table in KEYED and d2r[1]:
            vb.index_keys(cell(d2r[0], d2r[1][0], KEYED[table]), [])
        for i, brow, nrow, drow, own in row_pairs(table, m, named, d2r, built):
            if table in KEYED:
                key = cell(built[0], brow, KEYED[table]).lower()
                rec = vb.record(vb.by_key.get(key)) if vb is not None and vb.by_key is not None and key in vb.by_key else None
            else:
                rec = vb.record(i) if vb is not None and not own else None
            name = cell(built[0], brow, KEYED.get(table) or idmap.ENTITIES[table].key)
            for col, kind in cols.items():
                if col not in built[0]:
                    continue
                b = cell(built[0], brow, col)
                mv = cell(named[0], nrow, col) if nrow is not None else ""
                dv = cell(d2r[0], drow, col) if drow is not None else ""
                if norm(b) in EMPTY and norm(mv) in EMPTY:
                    continue
                v = vanilla_value(rec, mv, dv) if not own else "own"
                wb = res.where(kind, b)
                wd = res.where(kind, dv) if drow is not None and norm(dv) != norm(b) else ""
                wm = res.where(kind, mv) if norm(mv) != norm(b) else ""
                exists_b = wb and any(c in wb for c in "dm")
                kept = v == "M" and drow is not None and norm(mv) != norm(dv) and norm(dv) not in EMPTY
                if norm(b) in EMPTY and norm(mv) not in EMPTY:
                    # the build emptied Median's value (a dangling reference, art_fix's "null", ...)
                    if kept and "d" in wd:
                        verdict = "renamed-emptied"
                    elif wm and any(c in wm for c in "dm"):
                        counts[(table, "ok")] += 1
                        continue
                    else:
                        verdict = "emptied"
                elif kept and norm(b) == norm(dv) and norm(b) != norm(mv):
                    verdict = "renamed-fixed"
                elif kept and not exists_b and "d" in wd:
                    verdict = "renamed"
                elif kept and exists_b:
                    verdict = "renamed-exists"
                elif wb == "" or exists_b:
                    counts[(table, "ok")] += 1
                    continue
                elif drow is not None and norm(b) == norm(dv):
                    counts[(table, "d2r-same")] += 1  # D2R's own row has the same missing asset: D2R's behaviour
                    continue
                elif kind == "altgfx" and not alt_drawn(cell(built[0], brow, "type"), types):
                    counts[(table, "ok")] += 1  # gloves, boots, belts, body armour: not drawn from alternategfx
                    continue
                elif own or v not in ("M", "both"):
                    verdict = "missing-vanilla" if "v" in wb else ("median-missing" if own or v == "D" else "missing")
                else:
                    verdict = "missing-vanilla" if "v" in wb else "missing"
                counts[(table, verdict)] += 1
                hits.append({"table": table, "bank": bank, "id": i, "name": name, "column": col, "kind": kind,
                             "verdict": verdict, "median": mv, "vanilla": v, "d2r": dv, "built": b,
                             "where_built": wb, "where_d2r": wd, "where_median": wm})
    return hits, counts


ORDER = ("renamed", "renamed-emptied", "renamed-fixed", "renamed-exists", "missing-vanilla", "missing", "median-missing",
         "emptied")
COLUMNS = ("verdict", "table", "bank", "id", "name", "column", "kind", "median", "vanilla", "d2r", "built", "where_built",
           "where_d2r", "where_median")


def write(out: Path, hits: list[dict], counts: Counter) -> None:
    out.mkdir(parents=True, exist_ok=True)
    order = ORDER
    hits = sorted(hits, key=lambda h: (ORDER.index(h["verdict"]), h["table"], h["id"], h["column"]))
    with open(out / "rename_audit.tsv", "w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(COLUMNS) + "\n")
        for h in hits:
            f.write("\t".join(str(h[c]) for c in COLUMNS) + "\n")
    tables = sorted({t for t, _ in counts})
    lines = ["# Rename audit (tools/rename_audit.py)", "",
             "Where: d D2R CASC, m mod files, x Median MPQ, v 1.14d MPQs, - nowhere, -key sound key missing.", "",
             "| Table | " + " | ".join(("ok", "d2r-same", *order)) + " |", "|---|" + "---|" * (len(order) + 2)]
    for t in tables:
        lines.append(f"| {t} | " + " | ".join(str(counts.get((t, v), 0)) for v in ("ok", "d2r-same", *order)) + " |")
    lines += ["", "## Hits other than missing sounds", "", "| Verdict | Table | Id | Name | Column | M | V | D | B | where B / D / M |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for h in hits:
        lines.append(f"| {h['verdict']} | {h['table']} | {h['id']} | {h['name']} | {h['column']} | {h['median']} | "
                     f"{h['vanilla']} | {h['d2r']} | {h['built']} | {h['where_built']} / {h['where_d2r']} / {h['where_median']} |")
    (out / "rename_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bank", choices=("rotw", "base"), default="rotw")
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "mod")
    ap.add_argument("--table", action="append")
    a = ap.parse_args(argv)
    hits, counts = audit(a.bank, a.table)
    write(a.out, hits, counts)
    by_v = Counter(h["verdict"] for h in hits)
    print(f"rename audit ({a.bank}): {sum(counts.values())} cells, " + ", ".join(f"{k} {v}" for k, v in sorted(by_v.items()))
          + f" -> {a.out / 'rename_audit.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
