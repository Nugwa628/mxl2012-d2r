"""Own monster tokens: Median's art under a token of its own, never under a name D2R's art also uses (docs/legacy-graphics.md
section 6, docs/hd-monsters.md section 5).

D2R draws a monster in classic mode from `data/global/monsters/<token>/...` (token = monstats `Code`, two characters) and takes
its timing from `animdata.d2` records named `<TOKEN><MODE><WEAPON CLASS>`. Median XL 2012 and D2R share a few tokens although the
art differs, and Median has rows whose art D2R cannot start with (a mode without a COF); both ended with D2R's art in classic
mode. The data file `tools/data/own_tokens.json` lists what is done about it, one entry per token:

  split     Median's rows `rows` move from the shared token `old` to the unused token `new` (the monstats `Code` is rewritten,
            Median's `old` files are renamed to `new`, D2R's `old` files fill the modes Median ships none for, as 1.13c's vanilla
            files did, and the animdata records get the new names). D2R's own rows keep `old` with D2R's art. First case: the
            Slayer (`e9`), whose NU / S2 COFs have 13 / 14 frames while D2R's animdata says 2 for the Wake of Destruction trap
            that owns the token.
  complete  A token of Median's own that tools/gfx_placeholders.py used to replace with a D2R monster's graphics because a mode
            the row asks for has no COF. Median's art is kept; a missing mode becomes a copy of a neighbouring mode (COF, the DCCs
            it names under the new mode, the animdata record), a part Median shipped no DCC for is dropped from the COFs
            (`drop_missing_layers`, 1.13c drew nothing for it either) or taken from another look (`fill_variants`).
  borrow    Median rows with no art anywhere (Median ships nothing for their token) that borrowed a D2R monster's graphics
            (tools/gfx_placeholders.py) whose modes do not cover the row's skills. The rows get the token `new`: D2R's `old`
            files of the weapon classes `weapons` renamed (the COFs and the DCCs they name, animdata records from D2R's),
            the monstats2 visual columns of D2R's `donor` row with the row's own modes added, and the modes D2R's art lacks
            filled as `complete` does. First case: the six Haunts (AM / DZ / SO, player class codes) as D2R's Corrupt Rogue
            archer (CR bow): their MonBow uses SC, a mode no CR COF has (bug #74).

Everything is derived from Median's files, D2R's files and the built tables; nothing is stored in git but the entry file.

  py -3 -I tools/own_tokens.py tables [--excel DIR]   rewrite the Code of the split rows in work/mod (a build step)
  py -3 -I tools/own_tokens.py plan                    the files and animdata records the plan makes
  py -3 -I tools/own_tokens.py audit                   every place a Median row shares or borrows a D2R token (docs table)
Used by tools/legacy_art.py (files), animdata_merge.py (records), gfx_placeholders.py, hd_monsters.py, hd_donors.py.
"""
import json
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from txt_migrate import read_tsv, write_tsv, is_record  # noqa: E402
import fxpaths  # noqa: E402

DATA = fxpaths.ROOT / "tools" / "data" / "own_tokens.json"
COMPS = ["hd", "tr", "lg", "ra", "la", "rh", "lh", "sh", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]  # COF composite order
MODES = ["DT", "NU", "WL", "GH", "A1", "A2", "BL", "SC", "S1", "S2", "S3", "S4", "DD", "RN"]
# a mode with no COF takes a neighbouring mode's animation, first one found (the monster plays that animation instead)
MODE_SOURCE = {
    "DT": ("DD",), "DD": ("DT",), "NU": ("WL",), "WL": ("NU",), "GH": ("NU",), "BL": ("NU",), "RN": ("WL", "NU"),
    "A1": ("A2", "S1"), "A2": ("A1", "S1"), "SC": ("A1", "A2", "S1"), "S1": ("A1", "SC", "A2"),
    "S2": ("A1", "SC", "A2"), "S3": ("A1", "S1", "A2"), "S4": ("A1", "S1", "A2"),
}
BANKS = ("base", "")


# --- the entry file --------------------------------------------------------------------------------------------------------

def load(path: Path = DATA) -> list[dict]:
    return json.loads(Path(path).read_text("utf-8"))["tokens"] if Path(path).exists() else []


def splits(entries: list[dict] | None = None) -> list[dict]:
    return [e for e in (load() if entries is None else entries) if e["mode"] == "split"]


def completes(entries: list[dict] | None = None) -> list[dict]:
    return [e for e in (load() if entries is None else entries) if e["mode"] == "complete"]


def borrows(entries: list[dict] | None = None) -> list[dict]:
    return [e for e in (load() if entries is None else entries) if e["mode"] == "borrow"]


def row_token(mid: str, code: str, entries: list[dict] | None = None) -> str:
    """The token a monstats row draws with after the split: `code` (what the raw table says) unless the row is listed."""
    for e in splits(entries):
        if mid.lower() in (r.lower() for r in e["rows"]) and code.lower() == e["old"].lower():
            return e["new"]
    for e in borrows(entries):
        if mid.lower() in (r.lower() for r in e["rows"]):
            return e["new"]
    return code


def apply_tables(excel: Path, entries: list[dict] | None = None) -> list[str]:
    """Rewrite the monstats `Code` of the split rows in both banks of `excel`; returns report lines."""
    out = []
    for e in splits(entries):
        want = {r.lower() for r in e["rows"]}
        for bank in BANKS:
            p = excel / bank / "monstats.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            ci = h.index("Code")
            hit = [r for r in rows if is_record(r) and r[0].lower() in want and r[ci].lower() == e["old"].lower()]
            for r in hit:
                r[ci] = e["new"]
            if hit:
                write_tsv(p, h, rows)
            out.append(f"| {bank or 'rotw'} | {e['old']} -> {e['new']} | {', '.join(r[0] for r in hit)} |")
            done = {r[0].lower() for r in rows if is_record(r) and r[ci].lower() == e["new"].lower()}   # a second run
            missing = want - {r[0].lower() for r in hit} - done
            if missing:
                raise SystemExit(f"own_tokens: {sorted(missing)} not in {p} with Code {e['old']}")
    for e in borrows(entries):
        out += _borrow_tables(e, excel)
    return out


def _borrow_tables(e: dict, excel: Path, d2r_excel: Path | None = None) -> list[str]:
    """Code -> `new` and the monstats2 row -> D2R's `donor` row (visual columns) plus the row's own modes, both banks."""
    d2r_excel = fxpaths.D2R_EXCEL if d2r_excel is None else d2r_excel
    want = {r.lower() for r in e["rows"]}
    out = []
    for bank in BANKS:
        p, p2 = excel / bank / "monstats.txt", excel / bank / "monstats2.txt"
        if not p.exists() or not p2.exists():
            continue
        vh2, vrows2 = read_tsv(d2r_excel / bank / "monstats2.txt")
        donor = next((r for r in vrows2 if is_record(r) and r[0].lower() == e["donor"].lower()), None)
        if donor is None:
            raise SystemExit(f"own_tokens: no monstats2 row {e['donor']} in {d2r_excel / bank}")
        h, rows = read_tsv(p)
        h2, rows2 = read_tsv(p2)
        ci, xi = h.index("Code"), h.index("MonStatsEx")
        ms2 = {r[0].lower(): r for r in rows2 if is_record(r)}
        hit = [r for r in rows if is_record(r) and r[0].lower() in want]
        if {r[0].lower() for r in hit} != want:
            raise SystemExit(f"own_tokens: {sorted(want - {r[0].lower() for r in hit})} not in {p}")
        done = set()
        for r in hit:
            r[ci] = e["new"]
            r2 = ms2.get(r[xi].lower())
            if r2 is None or r[xi].lower() in done:
                continue
            done.add(r[xi].lower())
            own_modes = {m for m in MODES if f"m{m}" in h2 and r2[h2.index(f"m{m}")] == "1"}
            for c in h2:
                if c not in ("Id", "*hcIdx", "*eol") and c in vh2:
                    r2[h2.index(c)] = donor[vh2.index(c)]
            for m in own_modes:
                r2[h2.index(f"m{m}")] = "1"
        write_tsv(p, h, rows)
        write_tsv(p2, h2, rows2)
        out.append(f"| {bank or 'rotw'} | borrow {e['old']} ({e['donor']}) -> {e['new']} | {', '.join(r[0] for r in hit)} |")
    return out


# --- COF helpers -----------------------------------------------------------------------------------------------------------

def parse_cof(b: bytes) -> dict:
    """{'frames', 'dirs', 'layers': [(composite name, weapon class)]}; raises ValueError for a size that does not fit."""
    if len(b) < 28:
        raise ValueError("short COF")
    n, frames, dirs = b[0], b[1], b[2]
    if 28 + 9 * n + frames + frames * dirs * n != len(b):
        raise ValueError("COF size")
    layers = []
    for i in range(n):
        o = 28 + 9 * i
        if b[o] >= len(COMPS):
            raise ValueError("COF composite")
        layers.append((COMPS[b[o]], b[o + 5:o + 9].split(b"\0")[0].decode("latin-1").lower()))
    return {"frames": frames, "dirs": dirs, "layers": layers}


def drop_layers(b: bytes, drop: set[str]) -> bytes:
    """The COF without the layers whose composite is in `drop` (names such as 'rh'): layer records and the priority bytes
    (one composite id per layer, per frame and direction) of those composites are removed, the keyframes stay."""
    n, frames, dirs = b[0], b[1], b[2]
    ids = {COMPS.index(c) for c in drop}
    layers = [b[28 + 9 * i:28 + 9 * i + 9] for i in range(n)]
    keep = [l for l in layers if l[0] not in ids]
    if len(keep) == n or not keep:
        return b
    keys = b[28 + 9 * n:28 + 9 * n + frames]
    prio = b[28 + 9 * n + frames:]
    new_prio = b"".join(bytes(x for x in prio[i * n:(i + 1) * n] if x not in ids) for i in range(frames * dirs))
    return bytes([len(keep)]) + b[1:28] + b"".join(keep) + keys + new_prio


# --- files -------------------------------------------------------------------------------------------------------------------

@dataclass
class Op:
    """One file below data/global/monsters/ the plan writes: `src` (copied as it is) or `data` (made here)."""
    dest: str                      # lower case, e.g. 'ks/cof/ksnuhth.cof'
    origin: str                    # median | d2r | derived: <what>
    src: Path | None = None
    data: bytes | None = None

    def read(self) -> bytes:
        return self.data if self.data is not None else self.src.read_bytes()


@dataclass
class Anim:
    """An animdata record to add: `name` (upper case) is made from the record `source` of `table` (median | d2r | merged)."""
    name: str
    source: str
    table: str
    frames: int


@dataclass
class Plan:
    ops: dict[str, Op] = field(default_factory=dict)
    anims: list[Anim] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    moved: dict[str, str] = field(default_factory=dict)       # Median file (lower-case rel) that moves -> its new rel


def index(root: Path | None, token: str | None = None) -> dict[str, Path]:
    """Lower-cased path below root -> file, optionally only below one token's folder."""
    if root is None or not Path(root).exists():
        return {}
    out = {}
    for p in Path(root).rglob("*"):
        if p.is_file():
            rel = p.relative_to(root).as_posix().lower()
            if token is None or rel.split("/")[0] == token.lower():
                out[rel] = p
    return out


def renamed(rel: str, old: str, new: str) -> str:
    """'e9/cof/e9nuhth.cof' -> 'ks/cof/ksnuhth.cof' (the folder and the file name's token prefix)."""
    parts = rel.lower().split("/")
    parts[0] = new.lower()
    if parts[-1].startswith(old.lower()):
        parts[-1] = new.lower() + parts[-1][len(old):]
    return "/".join(parts)


def _cof_name(rel: str) -> tuple[str, str, str] | None:
    """('token', 'MODE', 'wc') of a '<tok>/cof/<tok><mode><wc>.cof' path, else None."""
    m = re.fullmatch(r"([^/]+)/cof/(.+)\.cof", rel)
    if not m:
        return None
    tok, stem = m.group(1), m.group(2)
    if not stem.startswith(tok) or len(stem) < len(tok) + 3:
        return None
    return tok, stem[len(tok):len(tok) + 2].upper(), stem[len(tok) + 2:]


def _split_plan(e: dict, plan: Plan, med: dict[str, Path], d2r: dict[str, Path]) -> None:
    old, new = e["old"].lower(), e["new"].lower()
    for where, files in (("Median", med), ("D2R", d2r)):
        if any(r.split("/")[0] == new for r in files):
            raise SystemExit(f"own_tokens: new token {e['new']} already has files in {where}'s monsters folder")
    for rel, p in med.items():
        if rel.split("/")[0] == old:
            dest = renamed(rel, old, new)
            plan.ops[dest] = Op(dest, "median", src=p)
            plan.moved[rel] = dest
    for rel, p in d2r.items():
        if rel.split("/")[0] == old:
            dest = renamed(rel, old, new)
            if dest not in plan.ops:
                plan.ops[dest] = Op(dest, "d2r", src=p)
    for dest, op in list(plan.ops.items()):
        c = _cof_name(dest)
        if c and c[0] == new:
            plan.anims.append(Anim(c[0].upper() + c[1] + c[2].upper(), old.upper() + c[1] + c[2].upper(), "", parse_cof(op.read())["frames"]))


def _borrow_plan(e: dict, plan: Plan, med: dict[str, Path], d2r: dict[str, Path], excel: Path) -> None:
    """D2R's `old` COFs of the weapon classes `weapons` (and the DCCs their layers name) under `new`, then the row's other
    modes filled from them (`_complete_plan`)."""
    old, new = e["old"].lower(), e["new"].lower()
    for where, files in (("Median", med), ("D2R", d2r)):
        if any(r.split("/")[0] == new for r in files):
            raise SystemExit(f"own_tokens: new token {e['new']} already has files in {where}'s monsters folder")
    wcs = {w.lower() for w in e["weapons"]}
    used: set[tuple[str, str]] = set()   # (composite, mode + layer weapon class) of the copied COFs' layers
    for rel, p in sorted(d2r.items()):
        c = _cof_name(rel)
        if not c or c[0] != old or c[2] not in wcs:
            continue
        dest = renamed(rel, old, new)
        plan.ops[dest] = Op(dest, "d2r", src=p)
        cof = parse_cof(p.read_bytes())
        plan.anims.append(Anim(new.upper() + c[1] + c[2].upper(), old.upper() + c[1] + c[2].upper(), "", cof["frames"]))
        used |= {(comp, c[1].lower() + lwc) for comp, lwc in cof["layers"]}
    for rel, p in d2r.items():
        parts = rel.split("/")
        if parts[0] != old or len(parts) != 3 or not parts[2].endswith(".dcc") or parts[1] == "cof":
            continue
        comp, stem = parts[1], parts[2][:-4]
        if any(comp == uc and stem.startswith(old + comp) and stem.endswith(ml) for uc, ml in used):
            dest = renamed(rel, old, new)
            plan.ops.setdefault(dest, Op(dest, "d2r", src=p))
    _complete_plan({**e, "token": e["new"]}, plan, med, d2r, excel)


def row_flags(excel: Path, token: str) -> list[dict]:
    """For every monstats row with Code `token` in either bank: {'wc', 'modes', 'parts': {composite: [variants]}}."""
    out = []
    for bank in BANKS:
        d = excel / bank
        if not (d / "monstats.txt").exists() or not (d / "monstats2.txt").exists():
            continue
        h, rows = read_tsv(d / "monstats.txt")
        h2, rows2 = read_tsv(d / "monstats2.txt")
        ms2 = {r[0].lower(): {k.lower(): v for k, v in zip(h2, r)} for r in rows2 if is_record(r)}
        ci, ei = h.index("Code"), h.index("MonStatsEx")
        for r in rows:
            if not is_record(r) or r[ci].lower() != token.lower():
                continue
            row = ms2.get(r[ei].strip().lower())
            if row is None:
                continue
            parts = {}
            for comp in COMPS:
                if row.get(comp, "").strip() == "1":
                    parts[comp] = [v.strip().lower() for v in row.get(comp + "v", "").strip().strip('"').split(",") if v.strip().lower() != "nil"]   # '' = the plain file
            out.append({"wc": (row.get("basew", "").strip().lower() or "hth"),
                        "modes": [m for m in MODES if row.get("m" + m.lower(), "").strip() == "1"], "parts": parts})
    return out


def _complete_plan(e: dict, plan: Plan, med: dict[str, Path], d2r: dict[str, Path], excel: Path) -> None:
    t = e["token"].lower()
    avail: dict[str, Path] = {r: p for r, p in d2r.items() if r.split("/")[0] == t}
    avail.update({r: p for r, p in med.items() if r.split("/")[0] == t})
    flags = row_flags(excel, t)
    wcs = {(m, f["wc"]) for f in flags for m in f["modes"]}

    def has(rel: str) -> bool:
        return rel in avail or rel in plan.ops

    def cof_bytes(rel: str) -> bytes | None:
        if rel in plan.ops:
            return plan.ops[rel].read()
        return avail[rel].read_bytes() if rel in avail else None

    def source(rel: str) -> Path:
        return avail[rel] if rel in avail else plan.ops[rel].src

    def dcc(comp: str, var: str, mode: str, wc: str) -> str:
        return f"{t}/{comp}/{t}{comp}{var}{mode.lower()}{wc}.dcc"

    for mode, wc in sorted(wcs):
        rel = f"{t}/cof/{t}{mode.lower()}{wc}.cof"
        if has(rel):
            continue
        for sm in MODE_SOURCE.get(mode, ()):
            srel = f"{t}/cof/{t}{sm.lower()}{wc}.cof"
            if not has(srel):
                continue
            data = cof_bytes(srel)
            plan.ops[rel] = Op(rel, f"derived: {sm} COF", data=data)
            plan.anims.append(Anim((t + mode + wc).upper(), (t + sm + wc).upper(), "merged", parse_cof(data)["frames"]))
            plan.notes.append(f"{t}{mode.lower()}{wc}.cof <- {sm}")
            for comp, lwc in parse_cof(data)["layers"]:
                for f in (f for f in flags if f["wc"] == wc):
                    for var in f["parts"].get(comp, []):
                        s, d = dcc(comp, var, sm, lwc), dcc(comp, var, mode, lwc)
                        if has(s) and not has(d):
                            plan.ops[d] = Op(d, f"derived: {sm} DCC", src=source(s))
            break
    # parts the token has no DCC for
    for mode, wc in sorted(wcs):
        rel = f"{t}/cof/{t}{mode.lower()}{wc}.cof"
        data = cof_bytes(rel)
        if data is None:
            continue
        drop = set()
        for comp, lwc in parse_cof(data)["layers"]:
            vars_ = sorted({v for f in flags if f["wc"] == wc for v in f["parts"].get(comp, [])})
            if comp not in {c for f in flags if f["wc"] == wc for c in f["parts"]}:
                continue
            have = [v for v in vars_ if has(dcc(comp, v, mode, lwc))]
            if vars_ and not have:
                if e.get("drop_missing_layers"):
                    drop.add(comp)
                    plan.notes.append(f"{t}{mode.lower()}{wc}.cof: layer {comp} dropped (no {comp} DCC in any look)")
            elif have:
                for v in vars_:
                    if v not in have and e.get("fill_variants"):
                        s, d = dcc(comp, have[0], mode, lwc), dcc(comp, v, mode, lwc)
                        plan.ops[d] = Op(d, f"derived: look {have[0]}", src=source(s))
        if drop:
            plan.ops[rel] = Op(rel, "derived: layers dropped", data=drop_layers(data, drop))


def make_plan(entries: list[dict] | None = None, med_mon: Path | None = None, d2r_mon: Path | None = None,
              excel: Path | None = None) -> Plan:
    entries = load() if entries is None else entries
    med_mon = fxpaths.MXL / "monsters" if med_mon is None else med_mon
    d2r_mon = fxpaths.D2R_DATA / "global" / "monsters" if d2r_mon is None else d2r_mon
    excel = fxpaths.OUT / "global" / "excel" if excel is None else excel
    plan = Plan()
    med, d2r = index(med_mon), index(d2r_mon)
    for e in entries:
        if e["mode"] == "split":
            _split_plan(e, plan, med, d2r)
        elif e["mode"] == "complete":
            _complete_plan(e, plan, med, d2r, excel)
        elif e["mode"] == "borrow":
            _borrow_plan(e, plan, med, d2r, excel)
    return plan


_cache: dict[tuple, Plan] = {}


def default_plan() -> Plan:
    key = (str(fxpaths.MXL), str(fxpaths.D2R), str(fxpaths.OUT))
    if key not in _cache:
        _cache[key] = make_plan()
    return _cache[key]


def cof_stems(plan: Plan | None = None) -> set[str]:
    """Lower-case COF stems the plan adds (gfx_placeholders.py counts them as Median's files)."""
    plan = default_plan() if plan is None else plan
    return {Path(r).stem for r in plan.ops if r.endswith(".cof")}


def virtual_index(plan: Plan | None = None) -> dict[str, Path]:
    """rel -> source file for the plan's files that are copies (hd_monsters.py reads the art of a new token through this)."""
    plan = default_plan() if plan is None else plan
    return {r: o.src for r, o in plan.ops.items() if o.src is not None}


def resolve(rel: str) -> Path | None:
    return virtual_index().get(rel.lower())


def write(out: Path, plan: Plan | None = None) -> list[str]:
    """Write the plan's files below out (= data; files go to global/monsters/); returns report rows."""
    plan = default_plan() if plan is None else plan
    rows = []
    for rel, op in sorted(plan.ops.items()):
        dest = out / "global" / "monsters" / rel
        data = op.read()
        if not (dest.exists() and dest.read_bytes() == data):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        rows.append(f"| {rel} | {op.origin} |")
    return rows


def add_animdata(merged: dict[bytes, bytes], mxl: dict[bytes, bytes], d2r: dict[bytes, bytes], plan: Plan | None = None) -> list[str]:
    """Add the plan's animdata records to `merged` (name -> 160-byte record): the record of the old name (Median's, else D2R's;
    its frame count must equal the COF's) or of the source mode of a derived one. Returns the names added."""
    plan = default_plan() if plan is None else plan
    added = []
    for a in plan.anims:
        new, src = a.name.encode(), a.source.encode()
        if a.table == "merged":
            rec = merged.get(src)
        else:
            rec = next((t[src] for t in (mxl, d2r) if src in t and struct.unpack_from("<I", t[src], 8)[0] == a.frames), None)
        if rec is None:
            plan.notes.append(f"animdata {a.name}: no record {a.source} with {a.frames} frames")
            continue
        merged[new] = new.ljust(8, b"\0") + rec[8:]
        added.append(a.name)
    return added


# --- the audit: where does a Median row share or borrow a D2R token --------------------------------------------------------

def audit(median_data: Path, d2r_data: Path, excel_raw: Path, excel_built: Path) -> dict:
    """What the survey of docs/legacy-graphics.md section 6 found, from the files: shared tokens (with the file counts),
    classic files of missiles / overlays / items that exist in both with other contents, animdata records whose frame count
    differs from the COF of the same name, and the rows whose Code the placeholder step replaced."""
    res: dict = {}
    for kind in ("missiles", "overlays", "items"):
        m, d = index(median_data / "global" / kind), index(d2r_data / "global" / kind)
        both = [k for k in m if k in d]
        res[kind] = {"median": len(m), "both": len(both), "differ": sorted(k for k in both if m[k].read_bytes() != d[k].read_bytes())}
    m, d = index(median_data / "global" / "monsters"), index(d2r_data / "global" / "monsters")
    toks = {}
    for t in sorted({k.split("/")[0] for k in m} & {k.split("/")[0] for k in d}):
        mt = [k for k in m if k.split("/")[0] == t]
        both = [k for k in mt if k in d]
        toks[t] = {"median": len(mt), "same_path": len(both), "differ": sorted(k for k in both if m[k].read_bytes() != d[k].read_bytes())}
    res["shared_tokens"] = toks
    res["borrowed"] = []
    if (excel_raw / "monstats.txt").exists() and (excel_built / "monstats.txt").exists():
        rh, rrows = read_tsv(excel_raw / "monstats.txt")
        bh, brows = read_tsv(excel_built / "monstats.txt")
        raw = {r[0]: r[rh.index("Code")] for r in rrows if is_record(r)}
        for r in brows:
            if is_record(r) and r[0] in raw and raw[r[0]].lower() != r[bh.index("Code")].lower():
                res["borrowed"].append((r[0], raw[r[0]], r[bh.index("Code")]))
    return res


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["tables", "plan", "audit"])
    ap.add_argument("--excel", help="tables: the folder holding base/ and rotw (default work/mod/data/global/excel)")
    a = ap.parse_args(argv)
    if a.cmd == "tables":
        excel = Path(a.excel) if a.excel else fxpaths.OUT / "global" / "excel"
        lines = apply_tables(excel)
        print("\n".join(lines) or "no split / borrow entries")
        return 0
    if a.cmd == "plan":
        plan = make_plan()
        for rel, op in sorted(plan.ops.items()):
            print(f"{rel}\t{op.origin}")
        print(f"{len(plan.ops)} files, {len(plan.anims)} animdata records, {len(plan.moved)} Median files moved")
        for n in plan.notes:
            print("note:", n)
        return 0
    res = audit(fxpaths.MXL_ROOT / "data", fxpaths.D2R_DATA, fxpaths.WORK / "named", fxpaths.OUT / "global" / "excel" / "base")
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
