"""Median XL 2012's classic art for D2R's legacy graphics mode (G / Alt+G): which files D2R 3.3 loads from the mod, and the copy.

Legacy mode draws with the original DC6 / DCC / COF / DT1 / DS1 files, read from the mod's data folder
(mods/<mod>/<mod>.mpq/data/global/...) before D2R's own CASC copy. Median's v005 files are 1.13c's, the same formats D2R
ships, so nothing is converted: the step is a selection + a lower-cased copy, and a check (docs/legacy-graphics.md has the why).

  items/*.dc6, missiles/*.dcc, overlays/**.dcc   copied (Median-only names; a file D2R has too is Median's when it differs)
  monsters/<token>/{cof,<part>}/*                 copied; the tokens D2R shares (fm im iw oy rt) only when Median's COFs agree
                                                  with the merged animdata.d2 (else D2R's stay, as animdata_merge.py decided);
                                                  the files of an own token (tools/own_tokens.py: Slayer e9 -> KS) are renamed
                                                  into it, and its missing modes / parts are filled
  ui/panel/{invchar6,supertransmogrifier}.dc6     copied (what D2R's classic layouts name; tools/ui_layouts.py places the grids)
  ui/spells/*skillicon.dc6, skltree_*_back.dc6    copied (same sheet / tile structure as D2R's); the shared sheet skillicon.dc6
                                                  is tools/shared_icons.py's paired one when the build wrote it
  everything else (menus, local ui, tiles, animdata, strings, tables, sounds)   not here: the reason is in the report

Never written into git: the output is work/mod/data/global/... (and the asset pack / release). The one conversion: a DC6 pixel
on palette index 225-254 (hot pink in D2R's UI palette; none of D2R's 737 item DC6 draws them, 41 of Median's
do) gets the units-palette colour nearest to the mean of its opaque neighbours (as the HD pictures' fill; the plain nearest
colour of those indices is near-black, as D2R's units palette has them black), bytes in place (the file keeps its size).

  py -3 -I tools/legacy_art.py [build]   plan + copy + check -> work/mod/data/global/..., work/mod/legacy_art.md / .json
  py -3 -I tools/legacy_art.py plan      the plan only, nothing written
  py -3 -I tools/legacy_art.py check     structure and completeness of the art that build would ship / has shipped
Options: --median DIR (a folder holding data/global; MXL_EXTRACT, else assets/median, else extract-mpq), --d2r DIR (D2R 93847
extraction with filelist.txt; MXL_D2R_EXTRACT / MXL_D2R_BASE), --out DIR (default work/mod/data), --strict (warnings fail).
"""
import argparse
import csv
import json
import os
import shutil
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
from dc6 import palette as dc6_palette  # noqa: E402
import death_cofs  # noqa: E402
import own_tokens  # noqa: E402

COMPS = ["hd", "tr", "lg", "ra", "la", "rh", "lh", "sh", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]  # COF composite order
MODES = ["DT", "NU", "WL", "GH", "A1", "A2", "BL", "SC", "S1", "S2", "S3", "S4", "DD"]  # monstats2 m<MODE> flags a monster needs art
# for (KB / SQ / RN are flagged on vanilla monsters that have no file for them, so a missing one proves nothing)
UI_SHIP = {
    "global/ui/panel/invchar6.dc6": "character sheet + inventory (D2R's classic expansion layout names PANEL\\invchar6)",
    "global/ui/panel/supertransmogrifier.dc6": "Horadric Cube (horadriccubelayout names PANEL\\supertransmogrifier)",
}
UI_SKIP = {
    "global/ui/panel/tradestash.dc6": "no D2R classic layout names it: the stash is PANEL\\expandedstash (with D2R's tab bar, "
                                      "shared-stash arrows and gold bar), so Median's stash picture would be dead weight",
}
MENU_DIRS = ("global/ui/frontend/", "global/ui/bigmenu/", "global/ui/charselect/")
PAIRED_SHEET = "global/ui/spells/skillicon.dc6"   # replaced by <out>/../shared_icons/skillicon.dc6 (tools/shared_icons.py)
HAZARD = range(225, 255)  # UI palette indices that are hot pink in D2R's UI palette
MAX_REL = 150             # D2R's install path + mods/<mod>/<mod>.mpq/ must stay far under Windows' 260
WARN_LIST = 12


def classify(rel: str) -> tuple[str, str | None]:
    """rel = 'global/...' or 'local/...' lower case -> (kind, why it is not shipped here or None)."""
    ext = rel.rsplit(".", 1)[-1] if "." in rel.rsplit("/", 1)[-1] else ""
    art = ext in ("dc6", "dcc", "cof", "dt1", "ds1")
    if rel.startswith("global/items/") and ext == "dc6":
        return "item", None
    if rel.startswith("global/missiles/") and ext == "dcc":
        return "missile", None
    if rel.startswith("global/overlays/") and ext == "dcc":
        return "overlay", None
    if rel.startswith("global/monsters/") and ext in ("dcc", "cof", "dc6"):
        return "monster", None
    if rel in UI_SHIP:
        return "panel", None
    if rel in UI_SKIP:
        return "panel", UI_SKIP[rel]
    if rel.startswith("global/ui/spells/") and ext == "dc6":
        return ("skilltree" if "/skltree_" in rel else "skillicon"), None
    if rel.startswith(MENU_DIRS):
        return "menu", "D2R draws its own front end; legacy mode only changes the in-game drawing"
    if rel.startswith("local/ui/"):
        return "local-ui", "no D2R layout names data/local/ui/<lang>/act*/ pictures (D2R has only the options-menu ones)"
    if rel.startswith("global/tiles/"):
        return "tile", "tools/maps_hd.py build (DT1 as they are, DS1 with their monster ids renumbered)"
    if rel == "global/animdata.d2":
        return "animdata", "tools/animdata_merge.py (D2R's records + Median's)"
    if ext == "d2":
        return "d2", "classic client's COF caches (cmncof_a*, chars_cof): D2R reads the loose COFs, Median's would shadow D2R's"
    if rel.startswith("local/lng/") or ext == "tbl":
        return "strings", "tools/tbl2json.py (strings lane)"
    if rel.startswith("global/excel/") or ext in ("txt", "bin"):
        return "table", "tools/txt_migrate.py (tables lane)"
    if ext == "wav" or rel.startswith("global/sfx/"):
        return "sound", "not graphics"
    if art:
        return "unclassified", "art at a path this tool has no rule for: decide in tools/legacy_art.py"
    return "other", "not art"


# --- file formats -------------------------------------------------------------------------------------------------------

def parse_cof(b: bytes) -> dict:
    """COF: u8 layers, u8 frames per direction, u8 directions, 25 header bytes, 9-byte layers (composite, shadow, selectable,
    overlay, transparency, weapon class[4]), then the keyframe flags (frames) and the layer priorities (frames x dirs x layers)."""
    if len(b) < 28:
        raise ValueError("short COF")
    n, frames, dirs = b[0], b[1], b[2]
    want = 28 + 9 * n + frames + frames * dirs * n
    if want != len(b):
        raise ValueError(f"COF size {len(b)} != {want} for {n} layers, {frames} frames, {dirs} directions")
    layers = []
    for i in range(n):
        o = 28 + 9 * i
        comp = b[o]
        if comp >= len(COMPS):
            raise ValueError(f"COF layer {i}: composite {comp}")
        layers.append((COMPS[comp], b[o + 5:o + 9].split(b"\0")[0].decode("latin-1").lower()))
    return {"frames": frames, "dirs": dirs, "layers": layers}


def parse_dcc(b: bytes) -> dict:
    """DCC header: 0x74, version 6, directions u8, frames per direction u32."""
    if len(b) < 7 or b[0] != 0x74 or b[1] != 6:
        raise ValueError("not a DCC v6")
    return {"dirs": b[2], "frames": struct.unpack_from("<I", b, 3)[0]}


def dc6_index_hist(b: bytes) -> Counter:
    """How often each palette index is drawn by a DC6 (every direction and frame), without building the pictures."""
    _v, _f, _e, _t, dirs, fpd = struct.unpack_from("<6I", b, 0)
    hist: Counter = Counter()
    for p in struct.unpack_from(f"<{dirs * fpd}I", b, 24):
        length = struct.unpack_from("<i", b, p + 28)[0]
        blk, i = b[p + 32:p + 32 + length], 0
        while i < len(blk):
            c = blk[i]
            i += 1
            if c & 0x80:
                continue  # 0x80 = end of line, else a skip
            hist.update(blk[i:i + c])
            i += c
    return hist


def nearest_map(pal: list[tuple[int, int, int]]) -> dict[int, int]:
    """Palette index 225-254 -> the nearest colour among indices 1-224 (0 is transparent)."""
    return {i: min(range(1, 225), key=lambda j: sum((a - b) ** 2 for a, b in zip(pal[i], pal[j]))) for i in HAZARD}


def remap_dc6(b: bytes, mapping: dict[int, int], pal: list[tuple[int, int, int]] | None = None) -> bytes:
    """The DC6 with every literal pixel in `mapping` replaced; the run-length structure is untouched. With the units palette
    `pal`, a pixel first takes the index (1-224, not a hazard) nearest to the mean colour of its opaque non-hazard
    8-neighbours (the neighbour fill the HD pictures use, dc6.fill_unused); `mapping` only where no neighbour has a colour
    (D2R's units palette has 225-254 black, so the plain nearest colour is near-black)."""
    out = bytearray(b)
    _v, _f, _e, _t, dirs, fpd = struct.unpack_from("<6I", b, 0)
    for p in struct.unpack_from(f"<{dirs * fpd}I", b, 24):
        w, h = struct.unpack_from("<II", b, p + 4)
        length = struct.unpack_from("<i", b, p + 28)[0]
        i, end = p + 32, p + 32 + length
        x, y, grid, holes = 0, h - 1, {}, {}
        while i < end:
            c = b[i]
            i += 1
            if c == 0x80:
                x, y = 0, y - 1
                continue
            if c & 0x80:
                x += c & 0x7F
                continue
            for k in range(i, min(i + c, end)):
                grid[x, y] = b[k]
                if b[k] in mapping:
                    holes[x, y] = k
                x += 1
            i += c
        fill = _neighbour_fill(grid, holes, mapping, pal) if pal else {}
        for xy, k in holes.items():
            out[k] = fill.get(xy, mapping[b[k]])
    return bytes(out)


def _neighbour_fill(grid: dict, holes: dict, mapping: dict[int, int], pal: list, rounds: int = 4) -> dict:
    """{(x, y): index} for the holes that have coloured neighbours (holes next to filled holes in later rounds)."""
    todo, done, cache = set(holes), {}, {}
    for _ in range(rounds):
        new = {}
        for x, y in todo:
            acc, n = [0, 0, 0], 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    q = (x + dx, y + dy)
                    if not (dx or dy):
                        continue
                    if q in done:
                        idx = done[q]
                    elif q in grid and grid[q] not in mapping:
                        idx = grid[q]
                    else:
                        continue
                    r, g, bl = pal[idx]
                    acc[0], acc[1], acc[2], n = acc[0] + r, acc[1] + g, acc[2] + bl, n + 1
            if n:
                rgb = (acc[0] / n, acc[1] / n, acc[2] / n)
                if rgb not in cache:
                    cache[rgb] = min((j for j in range(1, 225) if j not in mapping),
                                     key=lambda j: sum((a - c) ** 2 for a, c in zip(rgb, pal[j])))
                new[x, y] = cache[rgb]
        if not new:
            break
        done.update(new)
        todo -= set(new)
    return done


def anim_frames(data: bytes) -> dict[str, int]:
    """animdata.d2 -> {COF name upper case: frames per direction} (256 buckets of u32 count + 160-byte records)."""
    out, o = {}, 0
    for _ in range(256):
        count = struct.unpack_from("<I", data, o)[0]
        o += 4
        for _ in range(count):
            out[data[o:o + 8].split(b"\0")[0].decode("latin-1").upper()] = struct.unpack_from("<I", data, o + 8)[0]
            o += 160
    return out


# --- inputs -------------------------------------------------------------------------------------------------------------

class D2R:
    """D2R 93847's legacy files: names from filelist.txt (data:data/... lines), contents from the extraction where it has them."""

    def __init__(self, root: Path | None, filelist: Path | None = None):
        self.data = Path(root) / "data" if root else None
        self.files: set[str] = set()
        self.has_list = bool(filelist and Path(filelist).exists())
        if self.has_list:
            for line in Path(filelist).read_text("utf-8").splitlines():
                if line.startswith("data:data/"):
                    self.files.add(line[len("data:data/"):].lower())
        elif self.data and self.data.exists():
            self.files = {p.relative_to(self.data).as_posix().lower() for p in self.data.rglob("*") if p.is_file()}

    def has(self, rel: str) -> bool:
        return rel in self.files

    def read(self, rel: str) -> bytes | None:
        p = self.data / rel if self.data else None
        return p.read_bytes() if p and p.is_file() else None


def read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="latin-1", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    return rows[0], rows[1:]


# --- plan ---------------------------------------------------------------------------------------------------------------

@dataclass
class Entry:
    rel: str
    src: Path
    kind: str
    action: str          # copy | skip
    why: str             # new | median-wins | same-as-d2r | kept-d2r | <reason it is not this tool's>
    size: int = 0
    pink: int = 0        # pixels of a DC6 on palette indices 225-254 (remapped when written)


@dataclass
class Plan:
    entries: list[Entry] = field(default_factory=list)
    tokens: dict[str, dict] = field(default_factory=dict)  # shared monster tokens: decision + why

    def shipped(self) -> list[Entry]:
        return [e for e in self.entries if e.action == "copy"]


def merged_frames(median_data: Path, d2r: D2R, out: Path | None) -> dict[str, int] | None:
    """Frames per direction animdata_merge.py's result has: the built file when it exists, else D2R's records with Median's
    added where D2R has none (its rule: a shared record with another frame count stays D2R's). None = no animdata at all."""
    if out and (out / "global" / "animdata.d2").exists():
        return anim_frames((out / "global" / "animdata.d2").read_bytes())
    mxl = median_data / "global" / "animdata.d2"
    if not mxl.exists():
        return None
    frames = anim_frames(mxl.read_bytes())
    base = d2r.read("global/animdata.d2")
    return {**frames, **anim_frames(base)} if base else frames


def plan_art(median_data: Path, d2r: D2R, out: Path | None = None, own: "own_tokens.Plan | None" = None) -> Plan:
    plan = Plan()
    moved = own.moved if own else {}
    shared: dict[str, list[Entry]] = defaultdict(list)  # monster token -> its entries at a path D2R has and that differs
    token_cofs: dict[str, list[Path]] = defaultdict(list)
    for p in sorted(median_data.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(median_data).as_posix().lower()
        kind, why = classify(rel)
        e = Entry(rel, p, kind, "skip", why or "", p.stat().st_size)
        plan.entries.append(e)
        if why:
            continue
        if rel.startswith("global/monsters/") and rel[len("global/monsters/"):] in moved:
            e.why = "moved to " + moved[rel[len("global/monsters/"):]].split("/")[0]   # an own token (tools/own_tokens.py)
            continue
        if not d2r.has(rel):
            e.action, e.why = "copy", "new"
        else:
            theirs = d2r.read(rel)
            if theirs is not None and theirs == p.read_bytes():
                e.why = "same-as-d2r"
            elif kind == "monster":
                e.why = "kept-d2r"  # decided per token below
                shared[rel.split("/")[2]].append(e)
            else:
                e.action, e.why = "copy", "median-wins"
        if kind == "monster" and rel.endswith(".cof") and not e.why.startswith("moved to"):
            token_cofs[rel.split("/")[2]].append(p)
    frames = merged_frames(median_data, d2r, out)
    for tok, entries in sorted(shared.items()):
        bad = []
        for cof in token_cofs[tok]:
            f = parse_cof(cof.read_bytes())["frames"] if _cof_ok(cof) else None
            want = None if frames is None else frames.get(cof.stem.upper())
            if f is not None and want is not None and f != want:
                bad.append(f"{cof.stem.upper()}: COF {f} frames, animdata {want}")
        plan.tokens[tok] = {"files": len(entries), "median_wins": not bad, "mismatch": bad}
        if not bad:
            for e in entries:
                e.action, e.why = "copy", "median-wins"
    paired = Path(out).parent / "shared_icons" / "skillicon.dc6" if out else None
    if paired and paired.exists():   # the shared sheet in pairs, matching the rewritten skilldesc cels (classic mode reads them too)
        for e in plan.entries:
            if e.rel == PAIRED_SHEET:
                e.src, e.action, e.why, e.size = paired, "copy", "paired", paired.stat().st_size
    for e in plan.shipped():
        if e.rel.endswith(".dc6"):
            e.pink = sum(v for k, v in dc6_index_hist(e.src.read_bytes()).items() if k in HAZARD)
    return plan


def _cof_ok(p: Path) -> bool:
    try:
        parse_cof(p.read_bytes())
        return True
    except ValueError:
        return False


# --- check --------------------------------------------------------------------------------------------------------------

def monster_completeness(median_data: Path, view: set[str], reader, token_of=None,
                         rows2: dict[str, dict] | None = None) -> tuple[Counter, list[str]]:
    """Every Median monstats row against the files its monstats2 row asks for: COF per mode, a DCC/DC6 per COF layer.
    view = names that exist after the build (D2R's + shipped); reader(rel) -> bytes | None; token_of(Id, Code) -> the token the
    built table gives the row (own tokens, tools/own_tokens.py); rows2 = monstats2 rows (lower-case Id -> lower-case column ->
    value) that replace Median's (the built rows of the `borrow` own tokens: D2R's donor row). -> counts, problems."""
    ex = median_data / "global" / "excel"
    if not (ex / "monstats.txt").exists() or not (ex / "monstats2.txt").exists():
        return Counter(), []
    h1, r1 = read_table(ex / "monstats.txt")
    h2, r2 = read_table(ex / "monstats2.txt")
    ms2 = {r[0].lower(): {k.lower(): v for k, v in zip(h2, r)} for r in r2 if r}  # the part columns are HD.. but Rav / Lav
    ms2.update(rows2 or {})
    ci, ii, ei = h1.index("Code"), h1.index("Id"), h1.index("MonStatsEx")
    n, problems = Counter(), []
    seen = set()
    for r in r1:
        if len(r) <= ci or not r[ci].strip() or r[ci].strip() == "*":
            continue
        tok = r[ci].strip().lower()
        if token_of:
            tok = token_of(r[ii].strip(), tok).lower()
        row = ms2.get(r[ei].strip().lower() or r[ii].strip().lower())
        if row is None or (tok, row["id"]) in seen:
            continue
        seen.add((tok, row["id"]))
        if not any(f.startswith(f"global/monsters/{tok}/") for f in view):
            n["no art anywhere"] += 1
            continue
        miss = []
        for mode in MODES:
            if row.get("m" + mode.lower(), "").strip() != "1":
                continue
            wc = row.get("basew", "hth").strip().lower() or "hth"
            cof = f"global/monsters/{tok}/cof/{tok}{mode.lower()}{wc}.cof"
            if cof not in view:
                miss.append(cof.rsplit("/", 1)[1])
                continue
            data = reader(cof)
            try:
                layers = parse_cof(data)["layers"] if data else []
            except ValueError:
                layers = []
            for comp, lwc in layers:
                if row.get(comp, "").strip() != "1":
                    continue  # the monstats2 row does not use this part
                for var in (v.strip().lower() for v in row.get(comp + "v", "").split(",")):  # a list: one per look
                    if var == "nil":
                        continue  # "nil" = this look has no such part
                    name = f"{tok}{comp}{var}{mode.lower()}{lwc}"
                    if not any(f"global/monsters/{tok}/{comp}/{name}.{x}" in view for x in ("dcc", "dc6")):
                        miss.append(name + ".dcc")
        if miss:
            n["incomplete"] += 1
            problems.append(f"{tok}|{row['id']} ({tok}): missing {', '.join(sorted(set(miss))[:4])}{' ...' if len(set(miss)) > 4 else ''}")
        else:
            n["complete"] += 1
    return n, problems


def check_art(plan: Plan, median_data: Path, d2r: D2R, out: Path | None, remap: dict | None = None,
              own: "own_tokens.Plan | None" = None) -> dict:
    """-> {'errors': [...], 'warnings': [...], 'stats': {...}}; reads the sources, never the output except for the tiles note.
    remap = the palette-index map build applies (None: no units palette, pink pixels would ship as they are)."""
    errors, warnings, stats = [], [], {}
    shipped = plan.shipped()
    # structure of what ships
    hazards = [(e.rel, e.pink) for e in shipped if e.pink]
    long_rel = [e.rel for e in shipped if len("data/" + e.rel) > MAX_REL]
    frames = merged_frames(median_data, d2r, out)
    mism = []
    for e in shipped:
        b = e.src.read_bytes()
        try:
            if e.rel.endswith(".cof"):
                c = parse_cof(b)
                want = None if frames is None else frames.get(e.src.stem.upper())
                if want is not None and want != c["frames"]:
                    mism.append(f"{e.src.stem.upper()} (COF {c['frames']}, animdata {want})")
            elif e.rel.endswith(".dcc"):
                parse_dcc(b)
        except (ValueError, struct.error) as ex:
            warnings.append(f"{e.rel}: {ex}")
    if mism:
        warnings.append(f"{len(mism)} shipped COF(s) whose frames differ from animdata: {', '.join(mism[:WARN_LIST])}")
    if hazards and not remap:
        warnings.append(f"{len(hazards)} shipped DC6 with pixels on palette indices 225-254 (hot pink in D2R's UI palette) and no "
                        "units palette to remap them with: " + ", ".join(f"{r.rsplit('/', 1)[1]} ({n})" for r, n in hazards[:WARN_LIST]))
    if long_rel:
        warnings.append(f"{len(long_rel)} paths longer than {MAX_REL} characters, e.g. {long_rel[0]}")
    for t, d in plan.tokens.items():
        if not d["median_wins"]:
            warnings.append(f"monster token {t}: D2R's files stay ({'; '.join(d['mismatch'][:3])})")
    # completeness
    view = set(d2r.files) | {e.rel for e in shipped}
    token_of = None
    if own:
        view |= {"global/monsters/" + r for r in own.ops}
        token_of = lambda mid, code: own_tokens.row_token(mid, code)  # noqa: E731
    rows2 = {}
    built = (out if out is not None else fxpaths.OUT) / "global" / "excel" / "monstats2.txt"
    want = {r.lower() for e in own_tokens.borrows() for r in e["rows"]} if own else set()
    if want and built.exists():
        bh, brows = read_table(built)
        rows2 = {r[0].lower(): {k.lower(): v.strip().strip('"') for k, v in zip(bh, r)} for r in brows if r and r[0].lower() in want}
    comp, found = monster_completeness(median_data, view, lambda rel: _read_view(rel, shipped, d2r, own), token_of, rows2)
    stats["monsters"] = dict(comp)
    brings = {e.rel.split("/")[2] for e in shipped if e.kind == "monster"}  # tokens Median brings files for
    brings |= {r.split("/")[0] for r in own.ops} if own else set()
    problems = [t.split("|", 1)[1] for t in found if t.split("|", 1)[0] in brings]
    vanilla = [t.split("|", 1)[1] for t in found if t.split("|", 1)[0] not in brings]
    stats["vanilla_gaps"] = vanilla
    if problems:
        warnings.append(f"{len(problems)} Median monster rows (tokens Median ships art for) lack classic art parts: "
                        + "; ".join(problems[:WARN_LIST]) + " (tools/gfx_placeholders.py lets those borrow a donor)")
    if vanilla:
        warnings.append(f"{len(vanilla)} monster rows use D2R's own tokens and lack parts D2R's classic art never had either "
                        "(listed in legacy_art.md; the classic client only has D2R's files for them)")
    if out is not None and not any((out / "global" / "tiles").rglob("*.dt1")):
        warnings.append("work/mod has no tiles yet: tools/maps_hd.py build must run before the install (legacy mode needs the DT1/DS1)")
    stats.update(shipped=len(shipped), bytes=sum(e.size for e in shipped), remapped=len(hazards) if remap else 0, incomplete=problems)
    return {"errors": errors, "warnings": warnings, "stats": stats}


def _read_view(rel: str, shipped: list[Entry], d2r: D2R, own: "own_tokens.Plan | None" = None) -> bytes | None:
    if own and rel.startswith("global/monsters/") and rel[len("global/monsters/"):] in own.ops:
        return own.ops[rel[len("global/monsters/"):]].read()
    for e in shipped:
        if e.rel == rel:
            return e.src.read_bytes()
    return d2r.read(rel)


# --- build + report -----------------------------------------------------------------------------------------------------

def copy_plan(plan: Plan, out: Path, remap: dict | None = None, pal: list | None = None) -> int:
    """Writes the shipped files below out (lower-case names), DC6 with their pink pixels remapped (neighbour fill with the
    units palette `pal`, remap_dc6); -> files written."""
    n = 0
    for e in plan.shipped():
        dest = out / e.rel
        data = e.src.read_bytes()
        if e.pink and remap:
            data = remap_dc6(data, remap, pal)
        if dest.exists() and dest.read_bytes() == data:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        n += 1
    return n


def report(plan: Plan, res: dict) -> str:
    kinds = defaultdict(Counter)
    for e in plan.entries:
        why = e.why if e.why in ("same-as-d2r", "kept-d2r") else "moved" if e.why.startswith("moved to") else "excluded"
        kinds[e.kind][e.action if e.action == "copy" else "skip:" + why] += 1
    lines = ["# legacy_art: Median's classic art in the build", "",
             "| kind | copied | same as D2R | kept D2R's | moved to an own token | not this tool's |", "|---|---:|---:|---:|---:|---:|"]
    for k in sorted(kinds):
        c = kinds[k]
        lines.append(f"| {k} | {c['copy']} | {c['skip:same-as-d2r']} | {c['skip:kept-d2r']} | {c['skip:moved']} | {c['skip:excluded']} |")
    lines += ["", f"Shipped {res['stats']['shipped']} files, {res['stats']['bytes'] / 1e6:.1f} MB; {res['stats']['remapped']} DC6 had "
              "pixels on palette indices 225-254 and were remapped to the units-palette colour nearest to their neighbours' mean.", ""]
    if plan.tokens:
        lines += ["## Monster tokens D2R has too", ""]
        for t, d in sorted(plan.tokens.items()):
            lines.append(f"- `{t}`: {d['files']} differing file(s), " + ("Median's" if d["median_wins"] else "D2R's stay: " + "; ".join(d["mismatch"][:4])))
        lines.append("")
    reasons = sorted({(e.kind, e.why) for e in plan.entries if e.action == "skip" and e.why not in ("same-as-d2r", "kept-d2r")
                      and not e.why.startswith("moved to")})
    lines += ["## Not copied here", ""] + [f"- {k}: {w}" for k, w in reasons] + [""]
    m = res["stats"].get("monsters")
    if m:
        lines += ["## Monster rows against their files", "", ", ".join(f"{k} {v}" for k, v in sorted(m.items())), ""]
        lines += [f"- {p}" for p in res["stats"]["incomplete"][:200]]
        lines += ["", "Rows on D2R's own tokens (D2R's files are all there is):", ""]
        lines += [f"- {p}" for p in res["stats"]["vanilla_gaps"][:300]] + [""]
    lines += ["## Warnings", ""] + [f"- {w}" for w in res["warnings"]] + [""]
    return "\n".join(lines)


def resolve_inputs(args) -> tuple[Path, D2R, Path]:
    med = Path(args.median) if args.median else fxpaths.MXL_ROOT
    root = args.d2r or os.environ.get("MXL_D2R_EXTRACT") or os.environ.get("MXL_D2R_BASE") or fxpaths.D2R
    lst = getattr(fxpaths, "D2R_FILELIST", None)
    for c in (Path(root) / "filelist.txt", lst, fxpaths.WORK / "d2r-filelist.txt"):
        if c and Path(c).exists():
            lst = c
            break
    d2r = D2R(root, lst)
    return med / "data", d2r, Path(args.out) if args.out else fxpaths.OUT


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", nargs="?", default="build", choices=["build", "plan", "check"])
    ap.add_argument("--median")
    ap.add_argument("--d2r")
    ap.add_argument("--out")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args(argv)
    median_data, d2r, out = resolve_inputs(args)
    if not (median_data / "global").exists():
        print(f"Median's files not found at {median_data} (MXL_EXTRACT / --median)")
        return 2
    if not d2r.files:
        print("no D2R baseline (filelist.txt / extraction): every Median file counts as new")
    elif not d2r.has_list:
        print("WARNING: no filelist.txt, only the files of the extraction count as D2R's")
    own = own_tokens.make_plan(med_mon=median_data / "global" / "monsters", d2r_mon=d2r.data / "global" / "monsters" if d2r.data else None,
                               excel=out / "global" / "excel")
    plan = plan_art(median_data, d2r, out, own)
    pal = next((p for p in (d2r.data / "global/palette/units/pal.dat" if d2r.data else None, fxpaths.PALETTE) if p and Path(p).exists()), None)
    units = dc6_palette(pal) if pal else None
    remap = nearest_map(units) if units else None
    res = check_art(plan, median_data, d2r, out, remap, own)
    n = 0
    if args.cmd == "build":
        n = copy_plan(plan, out, remap, units)
        derived = death_cofs.apply_cofs(out)   # hth death COFs under the weapon class name of the row (bugs.md #34)
        n += len(derived)
        own_rows = own_tokens.write(out, own)
        n += len(own_rows)
        section = ["", "## Derived death COFs (bugs.md #34)", "",
                   "Median ships death COFs for weapon class hth only; these copies carry the name of the row's own weapon class and an "
                   "added left-hand layer in it, as D2R's own bow death COFs do (the body layers still name the hth DCCs). Their "
                   "animdata records come from tools/animdata_merge.py.", "",
                   "| Token | Mode | Weapon class | Copied from |", "|---|---|---|---|", *derived, ""]
        section += ["## Own monster tokens (tools/own_tokens.py, docs/legacy-graphics.md section 6)", "",
                    "Files written for the tokens Median's art got of its own (Median's files renamed, D2R's files for the modes Median "
                    "ships none for, copies of a neighbouring mode for a missing one):", "",
                    "| File below data/global/monsters/ | Origin |", "|---|---|", *own_rows, ""]
        section += [f"- note: {x}" for x in own.notes] + [""]
        (out.parent / "legacy_art.md").write_text(report(plan, res) + "\n".join(section), encoding="utf-8")
        (out.parent / "legacy_art.json").write_text(json.dumps(
            {"files": [[e.rel, e.kind, e.action, e.why] for e in plan.entries], "tokens": plan.tokens, **res}, indent=1), encoding="utf-8")
    c = Counter(e.action for e in plan.entries)
    print(f"legacy art: {c['copy']} files to ship ({res['stats']['bytes'] / 1e6:.0f} MB), {c['skip']} not; {n} written to {out}")
    print(f"monster rows: {res['stats'].get('monsters')}")
    for w in res["warnings"]:
        print(f"WARNING: {w}"[:400])
    for e in res["errors"]:
        print(f"ERROR: {e}")
    return 1 if res["errors"] or (args.strict and res["warnings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
