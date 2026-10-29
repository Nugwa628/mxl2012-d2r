"""Cube recipe rules: Median XL 2012's cubemain as 1.13c ran it against the port as D2R reads it (lane cube).

Three comparisons over every recipe row (docs/median-rules-audit.md, "Cube recipes: static check"):

  bin   Median's compiled cubemain.bin (the table 1.13c loaded, 0x148-byte records) against its cubemain.txt (the port's
        source): enabled, ladder, min diff, class, op / param / value, numinputs, version, every input (item / type /
        unique, quality, quantity, nos / sock / noe), every output (item / useitem / usetype / Cow Portal, quality, lvl /
        plvl / ilvl, mod / uns / rem) and its five mods (property, param, min, max, chance).
  port  the source row against the built row of each bank, by meaning: same row order (first match decides decoys), a stat
        parameter names the same stat, a mod's skill / state / monster parameter the same row, a reference the same item,
        type or unique / set row (renamed codes, `mxl2012:` names), every other cell unchanged.
  d2r   what D2R reads differently (its data guide, data/global/dataguide/data/files/cubemain.js): field sizes (lvl / plvl /
        ilvl and mod chance 8 bits, mod param / min / max 16 bits), the op groups (1-14 player, 15-27 each input item,
        28 quest item), modifier words D2R's parser knows, stats / properties the build lacks, numinputs against the
        inputs' quantities, op 28 inputs without D2R's quest flags, version values the guide does not describe.

Levels: `error` (the port reads a row differently from 1.13c), `note` (both engines do the same odd thing, or a D2R
reading only a game check can settle; listed in the report). Exit 1 on an error.

  py -3 tools/cube_rules_check.py [--src <Median excel>] [--built <work/mod excel>] [--report <md>]

The source is untrusted downloaded data: run the tool with `py -3 -I`. Unit tests: tools/tests/test_cube_rules_check.py.
"""
import argparse
import csv
import re
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
import idmap  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUILT = ROOT / "work" / "mod" / "data" / "global" / "excel"
RECORD = 0x148            # 1.13c cubemain.bin record (D2R's is 0x16c)
INPUTS, OUTPUTS, MODS = 7, 3, 5
OUT_COLS = ("output", "output b", "output c")
OUT_PREFIX = ("", "b ", "c ")
QUALITY = {"low": 1, "nor": 2, "hiq": 3, "mag": 4, "set": 5, "rar": 6, "uni": 7, "crf": 8, "tmp": 9}
CLASSES = ("ama", "sor", "nec", "pal", "bar", "dru", "ass")
IN_FLAG = {"item": 0x1, "type": 0x2, "nos": 0x4, "sock": 0x8, "noe": 0x20, "named": 0x40}
OUT_FLAG = {"mod": 0x1, "named": 0x8, "uns": 0x10, "rem": 0x20}
OUT_TYPE = {"useitem": 0xFE, "usetype": 0xFF, "Cow Portal": 0x01}
OUT_ITEM = 0xFC
# D2R's data guide (cubemain.js "input #" / "output" tables); "sock" is also written without "=" (D2R's own rows).
D2R_INPUT_WORDS = {"any", "qty", "low", "nor", "hiq", "mag", "set", "rar", "uni", "crf", "tmp", "nos", "sock", "noe", "eth",
                   "upg", "bas", "exc", "eli", "nru", "id"}
D2R_OUTPUT_WORDS = {"qty", "pre", "suf", "low", "nor", "hiq", "mag", "set", "rar", "uni", "crf", "tmp", "eth", "sock", "mod",
                    "uns", "rem", "reg", "exc", "eli", "rep", "rch", "lvl"}
D2R_SPECIAL_OUTPUTS = {"useitem", "usetype", "Cow Portal", "Pandemonium Portal", "Pandemonium Finale Portal", "Red Portal"}
PLAYER_OPS, ITEM_OPS, QUEST_OP = range(1, 15), range(15, 28), 28
STAT_OPS = set(range(3, 27))      # param = an itemstatcost id
D2R_BITS = {"lvl": (0, 255), "plvl": (0, 255), "ilvl": (0, 255), "chance": (0, 255), "mod": (-32768, 32767),
            "op": (0, 255), "numinputs": (0, 255)}


def read(path: Path) -> list[dict]:
    """A tab table as dicts; Median's files are Latin-1, the built ones UTF-8."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return list(csv.DictReader(text.splitlines(), delimiter="\t"))


def num(cell) -> int:
    cell = (cell or "").strip()
    return int(cell) if re.fullmatch(r"-?\d+", cell) else 0


def s16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def split_cell(cell: str) -> tuple[str, list[tuple[str, str]]]:
    """'"weap,mag,qty=2"' -> ('weap', [('mag', ''), ('qty', '2')])."""
    parts = (cell or "").strip().strip('"').split(",")
    words = []
    for p in parts[1:]:
        k, _, v = p.strip().partition("=")
        if k:
            words.append((k, v))
    return parts[0].strip(), words


# --- 1.13c side ---------------------------------------------------------------------------------------------------------

def decode_bin(data: bytes) -> list[dict]:
    """cubemain.bin -> one dict per record (the fields the comparison uses; layout found against the txt, see module doc)."""
    count = struct.unpack_from("<I", data, 0)[0]
    if 4 + count * RECORD != len(data):
        raise ValueError(f"cubemain.bin: {len(data)} bytes is not 4 + {count} x 0x{RECORD:x}")
    out = []
    for i in range(count):
        r = data[4 + i * RECORD: 4 + (i + 1) * RECORD]
        rec = {"enabled": r[0], "ladder": r[1], "min diff": r[2], "class": r[3], "op": r[4],
               "param": struct.unpack_from("<i", r, 8)[0], "value": struct.unpack_from("<i", r, 12)[0],
               "numinputs": r[0x10], "version": struct.unpack_from("<H", r, 0x12)[0], "inputs": [], "outputs": []}
        for k in range(INPUTS):
            flags, item, uniq, quality, qty = struct.unpack_from("<HHHBB", r, 0x14 + 8 * k)
            rec["inputs"].append(None if flags == 0 else {"flags": flags, "item": item, "uniq": uniq, "quality": quality, "qty": qty})
        for s in range(OUTPUTS):
            o = r[0x4C + 0x54 * s: 0x4C + 0x54 * (s + 1)]
            flags, item, uniq, quality, qty, kind, lvl, plvl, ilvl = struct.unpack_from("<HHHBBBBBB", o, 0)
            mods = []
            for m in range(MODS):
                prop, par, lo, hi, chance = struct.unpack_from("<IHhhB", o, 0x18 + 12 * m)
                mods.append(None if prop == 0xFFFFFFFF else {"prop": prop, "param": s16(par), "min": lo, "max": hi, "chance": chance})
            rec["outputs"].append({"flags": flags, "item": item, "uniq": uniq, "quality": quality, "qty": qty, "type": kind,
                                   "lvl": lvl, "plvl": plvl, "ilvl": ilvl, "mods": mods})
        out.append(rec)
    return out


class Median:
    """Median's own tables in 1.13c's numbering (the .bin record indexes)."""

    def __init__(self, tables: dict[str, list[dict]]):
        self.items = {}
        for t in ("weapons", "armor", "misc"):
            for r in tables[t]:
                if r.get("code") and r.get("name") != "Expansion":
                    self.items.setdefault(r["code"], len(self.items))
        self.types = {r["Code"]: i for i, r in enumerate(x for x in tables["itemtypes"] if x.get("ItemType") != "Expansion") if r.get("Code")}
        self.props = {r["code"]: i for i, r in enumerate(x for x in tables["properties"] if x.get("code") != "Expansion") if r.get("code")}
        self.uniques, self.unique_code = {}, {}
        for i, r in enumerate(tables["uniqueitems"]):
            self.uniques.setdefault(r["index"], i)
            self.unique_code.setdefault(r["index"], r.get("code", ""))
        self.sets = {r["index"]: i for i, r in enumerate(tables["setitems"])}
        self.set_code = {r["index"]: r.get("item", "") for r in tables["setitems"]}

    def expect_input(self, cell: str) -> dict | None:
        name, words = split_cell(cell)
        if not name:
            return None
        e = {"flags": 0, "item": 0, "uniq": 0, "quality": 0, "qty": 0}
        if name in self.uniques:
            e.update(flags=IN_FLAG["named"] | IN_FLAG["item"], item=self.items.get(self.unique_code[name], -1),
                     uniq=self.uniques[name] + 1, quality=7)
        elif name in self.sets:
            e.update(flags=IN_FLAG["named"] | IN_FLAG["item"], item=self.items.get(self.set_code[name], -1),
                     uniq=self.sets[name] + 1, quality=5)
        elif name in self.types:  # a code that is both a type and an item (`key`): 1.13c's compiler took the type
            e.update(flags=IN_FLAG["type"], item=self.types[name])
        elif name in self.items:
            e.update(flags=IN_FLAG["item"], item=self.items[name])
        else:
            e.update(flags=-1)
        for k, v in words:
            if k in QUALITY:
                e["quality"] = QUALITY[k]
            elif k == "qty":
                e["qty"] = num(v)
            elif k in IN_FLAG:
                e["flags"] |= IN_FLAG[k]
        return e

    def expect_output(self, cell: str) -> dict | None:
        name, words = split_cell(cell)
        if not name:
            return None
        e = {"flags": 0, "item": 0, "uniq": 0, "quality": 0, "qty": 0}
        if name in OUT_TYPE:
            e["type"] = OUT_TYPE[name]
        elif name in self.uniques:
            e.update(type=OUT_ITEM, flags=OUT_FLAG["named"], item=self.items.get(self.unique_code[name], -1),
                     uniq=self.uniques[name] + 1, quality=7)
        elif name in self.sets:
            e.update(type=OUT_ITEM, flags=OUT_FLAG["named"], item=self.items.get(self.set_code[name], -1),
                     uniq=self.sets[name] + 1, quality=5)
        elif name in self.items:
            e.update(type=OUT_ITEM, item=self.items[name])
        else:
            e.update(type=-1)
        for k, v in words:
            if k in QUALITY:
                e["quality"] = QUALITY[k]
            elif k == "qty":
                e["qty"] = num(v)
            elif k in OUT_FLAG:
                e["flags"] |= OUT_FLAG[k]
        return e


def compare_bin(txt_rows: list[dict], bin_rows: list[dict], median: Median) -> list[tuple]:
    """(level, 'bin', row, field, message) for every field where the compiled record says something else than the txt."""
    found = []
    if len(txt_rows) != len(bin_rows):
        return [("error", "bin", 0, "rows", f"txt {len(txt_rows)} rows, bin {len(bin_rows)}")]

    def diff(n, field, want, got):
        if want != got:
            found.append(("error", "bin", n, field, f"txt {want!r}, bin {got!r}"))

    for n, (t, b) in enumerate(zip(txt_rows, bin_rows), 1):
        diff(n, "enabled", num(t.get("enabled")), b["enabled"])
        diff(n, "min diff", num(t.get("min diff")), b["min diff"])
        diff(n, "class", CLASSES.index(t["class"]) if t.get("class") in CLASSES else 0xFF, b["class"])
        diff(n, "op", num(t.get("op")), b["op"])
        diff(n, "param", num(t.get("param")), b["param"])
        diff(n, "value", num(t.get("value")), b["value"])
        diff(n, "numinputs", num(t.get("numinputs")), b["numinputs"])
        diff(n, "version", num(t.get("version")), b["version"])
        for k in range(INPUTS):
            want, got = median.expect_input(t.get(f"input {k + 1}", "")), b["inputs"][k]
            if want and want["flags"] == -1 and got is None:  # a name 1.13c's compiler could not resolve: it left the input out
                found.append(("note", "bin", n, f"input {k + 1}", f"{t.get(f'input {k + 1}')!r} names nothing: 1.13c compiled the "
                              f"row without this input (numinputs still counts it, so one more item of any kind)"))
                continue
            diff(n, f"input {k + 1}", want, got)
        for s, col in enumerate(OUT_COLS):
            e, o, p = median.expect_output(t.get(col, "")), b["outputs"][s], OUT_PREFIX[s]
            if e is None:
                if o["type"] != 0:
                    found.append(("error", "bin", n, col, f"txt empty, bin output type 0x{o['type']:02x}"))
                continue
            diff(n, col, e, {k: o[k] for k in e})
            for f in ("lvl", "plvl", "ilvl"):
                diff(n, p + f, num(t.get(p + f)), o[f])
            for m in range(MODS):
                code = (t.get(f"{p}mod {m + 1}") or "").strip()
                want = None if not code else {"prop": median.props.get(code, -1), "param": s16(num(t.get(f"{p}mod {m + 1} param"))),
                                              "min": s16(num(t.get(f"{p}mod {m + 1} min"))), "max": s16(num(t.get(f"{p}mod {m + 1} max"))),
                                              "chance": num(t.get(f"{p}mod {m + 1} chance")) & 0xFF}
                diff(n, f"{p}mod {m + 1}", want, o["mods"][m])
    return found


# --- port side ----------------------------------------------------------------------------------------------------------

class Space:
    """Row number <-> key of an id space in one table set (Median: row order; built: the *ID / *Id column)."""

    def __init__(self, rows: list[dict], key: str, id_col: str | None = None, skip: str | None = None):
        self.by_id = {}
        rows = [r for r in rows if not skip or r.get(key) != skip]
        for i, r in enumerate(rows):
            rid = num(r.get(id_col)) if id_col and (r.get(id_col) or "").strip() else i
            self.by_id.setdefault(rid, (r.get(key) or "").strip().lower())

    def name(self, rid: int) -> str | None:
        return self.by_id.get(rid)


def same_name(a: str | None, b: str | None, renames: dict[str, str]) -> bool:
    """Keys of the same row: equal, renamed by prep (prep_renames.json) or given `_mxl` (a key D2R also adds)."""
    if a is None or b is None:
        return False
    a, b = a.lower(), b.lower()
    return a == b or renames.get(a, "").lower() == b or b in (a + "_mxl",) or idmap_rename(a) == b


def idmap_rename(key: str) -> str:
    """1.13c keys D2R spells differently (idmap: nehlithak -> nihlathak)."""
    return key.replace("nehlithak", "nihlathak")


def unique_ref(cell: str, index_rows: list[str]) -> int | None:
    """Row of a unique / set index the reference names (exact index cell; Median's tables are in row order in the build)."""
    name, _ = split_cell(cell)
    return index_rows.index(name) if name in index_rows else None


def compare_port(src: list[dict], built: list[dict], ctx: dict) -> list[tuple]:
    """(level, 'port', row, field, message) where a built row means something else than its source row."""
    found = []
    bank = ctx["bank"]
    if len(src) != len(built):
        return [("error", "port", 0, bank, f"source {len(src)} rows, built {len(built)}: the row order (first match) is lost")]
    renames = ctx.get("renames", {})
    code_map = ctx.get("code_map", lambda c: c)
    kinds = ctx.get("kinds", {})

    def bad(n, field, msg):
        found.append(("error", "port", n, f"{bank}: {field}", msg))

    for n, (s, b) in enumerate(zip(src, built), 1):
        if (s.get("description") or "").strip() != (b.get("description") or "").strip():
            bad(n, "description", f"{s.get('description')!r} became {b.get('description')!r} (rows out of order?)")
        for c in ("enabled", "min diff", "version", "op", "value", "class", "numinputs"):
            if (s.get(c) or "").strip() != (b.get(c) or "").strip():
                bad(n, c, f"{s.get(c)!r} -> {b.get(c)!r}")
        if (s.get("ladder") or "").strip() not in ("", "0") or (b.get("firstLadderSeason") or "").strip() not in ("", "0"):
            bad(n, "ladder", f"ladder {s.get('ladder')!r} -> firstLadderSeason {b.get('firstLadderSeason')!r}")
        op = num(s.get("op"))
        sp, bp = (s.get("param") or "").strip(), (b.get("param") or "").strip()
        if op in STAT_OPS and sp:
            a, z = ctx["src_stats"].name(num(sp)), ctx["built_stats"].name(num(bp))
            if not same_name(a, z, renames):
                bad(n, "param", f"stat {sp} ({a}) -> {bp} ({z})")
        elif sp != bp:
            bad(n, "param", f"{sp!r} -> {bp!r}")
        for col in [f"input {k}" for k in range(1, INPUTS + 1)] + list(OUT_COLS):
            sc, bc = (s.get(col) or "").strip(), (b.get(col) or "").strip()
            if sc == bc:
                continue
            median = ctx.get("median")
            if bc == "" and col.startswith("input") and median is not None and median.expect_input(sc)["flags"] == -1:
                continue  # a name 1.13c could not resolve: compiled as an empty slot, the build empties it too (bug #311)
            sn, sw = split_cell(sc)
            bn, bw = split_cell(bc)
            if sw != bw:
                bad(n, col, f"modifiers {sc!r} -> {bc!r}")
                continue
            su, bu = unique_ref(sn, ctx["src_uniques"]), unique_ref(bn, ctx["built_uniques"])
            ss, bs = unique_ref(sn, ctx["src_sets"]), unique_ref(bn, ctx["built_sets"])
            if su is not None or ss is not None:
                if (su, ss) != (bu, bs):
                    bad(n, col, f"{sc!r} -> {bc!r}: unique row {su} -> {bu}, set row {ss} -> {bs}")
            elif code_map(sn) != bn:
                bad(n, col, f"{sc!r} -> {bc!r}")
        for p in OUT_PREFIX:
            for f in ("lvl", "plvl", "ilvl"):
                if (s.get(p + f) or "").strip() != (b.get(p + f) or "").strip():
                    bad(n, p + f, f"{s.get(p + f)!r} -> {b.get(p + f)!r}")
            for m in range(1, MODS + 1):
                k = f"{p}mod {m}"
                code, bcode = (s.get(k) or "").strip(), (b.get(k) or "").strip()
                if code.lower() != bcode.lower() and not same_name(code, bcode, renames):
                    bad(n, k, f"{code!r} -> {bcode!r}")
                for f in ("chance", "min", "max"):
                    if (s.get(f"{k} {f}") or "").strip() != (b.get(f"{k} {f}") or "").strip():
                        bad(n, f"{k} {f}", f"{s.get(f'{k} {f}')!r} -> {b.get(f'{k} {f}')!r}")
                spar, bpar = (s.get(f"{k} param") or "").strip(), (b.get(f"{k} param") or "").strip()
                kind = kinds.get(code.lower(), ("", []))[0]
                space = {"skill": "skills", "skill-range": "skills", "state": "states", "monster": "monstats"}.get(kind)
                if space and re.fullmatch(r"\d+", spar):
                    a, z = ctx["src_" + space].name(num(spar)), ctx["built_" + space].name(num(bpar))
                    if not same_name(a, z, renames):
                        bad(n, f"{k} param", f"{kind} {spar} ({a}) -> {bpar} ({z})")
                elif spar != bpar:
                    bad(n, f"{k} param", f"{spar!r} -> {bpar!r}")
    return found


# --- what D2R reads differently -----------------------------------------------------------------------------------------

def check_d2r(built: list[dict], ctx: dict) -> list[tuple]:
    """(level, 'd2r', row, field, message): cells D2R's cubemain reader takes otherwise than 1.13c's, or cannot hold."""
    found = []
    bank = ctx["bank"]
    props, stats = ctx["built_props"], ctx["built_stat_ids"]
    quest = ctx.get("quest_items", {})

    def add(level, n, field, msg):
        found.append((level, "d2r", n, f"{bank}: {field}", msg))

    for n, r in enumerate(built, 1):
        enabled = (r.get("enabled") or "").strip() == "1"
        op = num(r.get("op"))
        for f, lim in (("op", D2R_BITS["op"]), ("numinputs", D2R_BITS["numinputs"])):
            if not lim[0] <= num(r.get(f)) <= lim[1]:
                add("error", n, f, f"{r.get(f)} does not fit D2R's 8-bit field")
        if op and op not in PLAYER_OPS and op not in ITEM_OPS and op != QUEST_OP:
            add("error", n, "op", f"op {op}: D2R knows 1-28 (any other op counts as passed)")
        if op in STAT_OPS and num(r.get("param")) not in stats:
            add("error", n, "param", f"op {op} names stat {r.get('param')}, which the built itemstatcost lacks")
        version = (r.get("version") or "").strip()
        if version not in ("", "0", "100") and enabled:
            add("note", n, "version", f"version {version}: D2R's guide describes 0 and 100 only (1.13c: usable when <= 100)")
        qty = 0
        for k in range(1, INPUTS + 1):
            cell = (r.get(f"input {k}") or "").strip()
            if not cell:
                continue
            name, words = split_cell(cell)
            for w, v in words:
                if w not in D2R_INPUT_WORDS:
                    add("error", n, f"input {k}", f"modifier {w!r} is not one D2R's parser knows")
            qty += max(1, num(dict(words).get("qty")))
            if op == QUEST_OP and enabled and quest.get(name) != ctx.get("src_quest", {}).get(ctx.get("code_map", str)(name), quest.get(name)):
                add("error", n, f"input {k}", f"op 28 (D2R: an input with quest + questdiffcheck must have a quest difficulty above "
                                              f"the game's): {name}'s flags {quest.get(name)} differ from Median's")
            if enabled and name in ctx.get("both_codes", ()):
                add("note", n, f"input {k}", f"{name!r} is an item type and an item code: 1.13c took the type; D2R's order unproven")
        if enabled and qty != num(r.get("numinputs")):
            extra = num(r.get("numinputs")) - qty
            add("note", n, "numinputs", f"numinputs {r.get('numinputs')}, inputs {qty}: " + (
                f"{extra} unlisted items more (Median's destruction recipes: the engine checks the count only and eats the "
                f"rest; game check `cubeclasses`)" if extra > 0 else "fewer items than inputs: never matches (1.13c the same)"))
        for s, col in enumerate(OUT_COLS):
            cell, p = (r.get(col) or "").strip(), OUT_PREFIX[s]
            if cell:
                name, words = split_cell(cell)
                if s > 0 and name == "useitem" and enabled:
                    add("note", n, col, "useitem in a second output: Median's dupe recipes mean a copy of input 1; D2R makes "
                                        "none (game check cubeclasses, row 8397; plugin-plan.md 16)")
                for w, v in words:
                    if w not in D2R_OUTPUT_WORDS:
                        add("error", n, col, f"modifier {w!r} is not one D2R's parser knows")
            for f in ("lvl", "plvl", "ilvl"):
                v = num(r.get(p + f))
                if not D2R_BITS[f][0] <= v <= D2R_BITS[f][1]:
                    add("error", n, p + f, f"{v} does not fit D2R's 8-bit field")
            for m in range(1, MODS + 1):
                k = f"{p}mod {m}"
                code = (r.get(k) or "").strip()
                if not code:
                    continue
                if code.lower() not in props:
                    add("error", n, k, f"property {code!r} is not in the built properties.txt")
                if not 0 <= num(r.get(f"{k} chance")) <= 255:
                    add("error", n, f"{k} chance", f"{r.get(f'{k} chance')} does not fit 8 bits")
                for f in ("param", "min", "max"):
                    v = num(r.get(f"{k} {f}"))
                    if not D2R_BITS["mod"][0] <= v <= D2R_BITS["mod"][1]:
                        add("error", n, f"{k} {f}", f"{v} does not fit D2R's 16-bit field (1.13c's is 16-bit too: check the bin)")
    return found


def op_groups(rows: list[dict]) -> Counter:
    c = Counter()
    for r in rows:
        op = num(r.get("op"))
        c["none" if not op else "player 1-14" if op in PLAYER_OPS else "item 15-27" if op in ITEM_OPS else "quest 28" if op == 28 else "other"] += 1
    return c


# --- driver -------------------------------------------------------------------------------------------------------------

def load_context(src_dir: Path, built_dir: Path) -> dict:
    t = {name: read(src_dir / f"{name}.txt") for name in ("weapons", "armor", "misc", "itemtypes", "properties", "uniqueitems",
                                                          "setitems", "itemstatcost", "skills", "states", "monstats")}
    renames = {}
    rpath = ROOT / "work" / "prep_renames.json"
    if rpath.exists():
        import json
        for table in json.loads(rpath.read_text("utf-8")).values():
            renames.update({k.lower(): v for k, v in table.items()})
    props = idmap.param_kinds(tsv(src_dir / "properties.txt"), tsv(src_dir / "itemstatcost.txt"))
    return {"tables": t, "median": Median(t), "renames": renames, "kinds": props,
            "src_stats": Space(t["itemstatcost"], "Stat", skip="Expansion"), "src_skills": Space(t["skills"], "skill", skip="Expansion"),
            "src_states": Space(t["states"], "state", skip="Expansion"), "src_monstats": Space(t["monstats"], "Id", skip="Expansion"),
            "src_quest": quest_flags(t), "both_codes": set(Median(t).types) & set(Median(t).items),
            "src_uniques": [r["index"] for r in t["uniqueitems"]], "src_sets": [r["index"] for r in t["setitems"]],
            "code_map": lambda c: c.replace("\xb5", "^")}


def tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    rows = read(path)
    header = list(rows[0].keys()) if rows else []
    return header, [[r.get(h) or "" for h in header] for r in rows]


def quest_flags(tables: dict) -> dict[str, tuple[str, str]]:
    """item code -> (quest, questdiffcheck) of the item tables."""
    out = {}
    for t in ("weapons", "armor", "misc"):
        for r in tables[t]:
            if r.get("code"):
                out.setdefault(r["code"], ((r.get("quest") or "").strip(), (r.get("questdiffcheck") or "").strip()))
    return out


def bank_context(base: dict, bank_dir: Path, bank: str) -> dict:
    b = {name: read(bank_dir / f"{name}.txt") for name in ("itemstatcost", "skills", "states", "monstats", "properties",
                                                           "uniqueitems", "setitems", "weapons", "armor", "misc")}
    quest = quest_flags(b)
    ctx = dict(base)
    ctx.update(bank=bank, built_stats=Space(b["itemstatcost"], "Stat", "*ID"), built_skills=Space(b["skills"], "skill", "*Id"),
               built_states=Space(b["states"], "state", "*ID" if b["states"] and "*ID" in b["states"][0] else None),
               built_monstats=Space(b["monstats"], "Id", "*hcIdx" if b["monstats"] and "*hcIdx" in b["monstats"][0] else None),
               built_uniques=[r["index"] for r in b["uniqueitems"]], built_sets=[r["index"] for r in b["setitems"]],
               built_props={(r.get("code") or "").strip().lower() for r in b["properties"]},
               built_stat_ids={num(r.get("*ID")) for r in b["itemstatcost"] if (r.get("*ID") or "").strip()},
               quest_items=quest)
    return ctx


def run(src_dir: Path, built_dir: Path) -> tuple[list[tuple], dict]:
    base = load_context(src_dir, built_dir)
    src = read(src_dir / "cubemain.txt")
    found, stats = [], {"rows": len(src), "ops": op_groups(src)}
    bin_path = src_dir / "cubemain.bin"
    if bin_path.exists():
        found += compare_bin(src, decode_bin(bin_path.read_bytes()), base["median"])
    else:
        found.append(("note", "bin", 0, "cubemain.bin", "not in the source: the 1.13c comparison was skipped"))
    for bank, d in (("RotW", built_dir), ("base", built_dir / "base")):
        ctx = bank_context(base, d, bank)
        built = read(d / "cubemain.txt")
        found += compare_port(src, built, ctx)
        found += check_d2r(built, ctx)
    return found, stats


def report(found: list[tuple], stats: dict) -> str:
    by = Counter((lv, kind) for lv, kind, *_ in found)
    lines = ["# cube_rules_check", "", f"{stats['rows']} source rows; op groups {dict(stats['ops'])}; findings "
             + ", ".join(f"{k[1]} {k[0]} {v}" for k, v in sorted(by.items())) or "none", ""]
    groups = Counter((lv, kind, re.sub(r"\d+", "#", field), re.sub(r"\d+", "#", msg)) for lv, kind, _n, field, msg in found)
    first = {}
    for lv, kind, n, field, msg in found:
        first.setdefault((lv, kind, re.sub(r"\d+", "#", field), re.sub(r"\d+", "#", msg)), (n, field, msg))
    lines += ["| level | check | rows | first row | field | example |", "|---|---|---|---|---|---|"]
    for key, cnt in sorted(groups.items(), key=lambda kv: (kv[0][0] != "error", kv[0][1], -kv[1])):
        n, field, msg = first[key]
        lines.append(f"| {key[0]} | {key[1]} | {cnt} | {n} | {field} | {msg.replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", type=Path, default=fxpaths.MXL_ROOT / "data" / "global" / "excel")
    ap.add_argument("--built", type=Path, default=BUILT)
    ap.add_argument("--report", type=Path, default=ROOT / "work" / "mod" / "cube_rules_report.md")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Median's names hold Latin-1 letters (0xB5)
    except (AttributeError, ValueError):
        pass
    found, stats = run(a.src, a.built)
    text = report(found, stats)
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(text, encoding="utf-8")
    errors = [f for f in found if f[0] == "error"]
    print(text if len(text) < 6000 else text[:6000] + "\n...")
    print(f"{len(errors)} errors, {len(found) - len(errors)} notes -> {a.report}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
