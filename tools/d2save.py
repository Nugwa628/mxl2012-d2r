"""Save inspector and round-trip codec for D2R 3.3 (v105) saves as D2RLoader's extended mode writes them (docs/save-format.md).

Reads a character `.d2s`, a shared stash `.d2i` and the D2RLoader sidecar `<name>.d2rl`, lists the character's stats, skills
and every item (player, corpse, mercenary, golem; socketed children under their parent), and writes the parsed save back.
The item layout is written once (`_item_layout`) and runs in both directions, so `encode(decode(x)) == x` checks that every
field is read with the width the game wrote it with: a wrong width shifts every later bit and the item list no longer ends
on its section marker. Widths come from the built tables (`work/mod/data/global/excel`: itemstatcost Save Bits / Save Add /
Save Param Bits / CSvBits / CSvParam, item codes and stack flags), so the codec follows the mod, not retail.

  py -3 tools/d2save.py show <file.d2s|file.d2i> [--excel DIR] [--json]
  py -3 tools/d2save.py roundtrip <file> [...]            exit 1 if a file does not re-encode to the same bytes
  py -3 tools/d2save.py diff <before> <after>              items / stats / skills that differ (exit 1 on any difference)
  py -3 tools/d2save.py sidecar <file.d2s>                 checks the .d2rl hashes, checksum and size against the .d2s
  py -3 tools/d2save.py snapshot <file> -o out.json        the comparable view (`diff` also takes two snapshots)

Read-only on the inputs: nothing is ever written next to a save.
"""
import argparse
import csv
import hashlib
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXCEL = os.path.join(ROOT, "work", "mod", "data", "global", "excel")

# ---------------------------------------------------------------------------------------------------------------- bits


class BitReader:
    def __init__(self, data, pos=0):
        self.data, self.pos = data, pos

    def read(self, n):
        v = 0
        for i in range(n):
            byte = self.data[self.pos >> 3]  # IndexError past the end: the caller reports a truncated item
            v |= ((byte >> (self.pos & 7)) & 1) << i
            self.pos += 1
        return v


class BitWriter:
    def __init__(self):
        self.bits = []

    @property
    def pos(self):
        return len(self.bits)

    def write(self, v, n):
        if v < 0 or v >> n:
            raise ValueError(f"value {v} does not fit {n} bits")
        self.bits.extend((v >> i) & 1 for i in range(n))

    def tobytes(self):
        b = self.bits + [0] * (-len(self.bits) % 8)
        return bytes(sum(b[i + j] << j for j in range(8)) for i in range(0, len(b), 8))


# ------------------------------------------------------------------------------------------------------------ huffman
# D2R's item-code tree (unchanged since 1.10). Its one free leaf, path 000101111 (beside `j`), is the escape D2RLoader's
# extended mode uses for a code character the tree lacks (Median's `! $ & + - @ ^` and capitals): the escape is followed by
# that character's path in a second, prefix-free tree (EXT_CODES, 6-8 bits). Solved from game-written items whose codes
# were known (lane savefmt: a cube holding one item per character, docs/save-format.md); every save then parses to its
# section markers and re-encodes byte for byte. `A` is still unknown.
HUFF = {
    " ": "10", "0": "11111011", "1": "1111100", "2": "001100", "3": "1101101", "4": "11111010", "5": "00010110",
    "6": "1101111", "7": "01111", "8": "000100", "9": "01110", "a": "11110", "b": "0101", "c": "01000", "d": "110001",
    "e": "110000", "f": "010011", "g": "11010", "h": "00011", "i": "1111110", "j": "000101110", "k": "010010",
    "l": "11101", "m": "01101", "n": "001101", "o": "1111111", "p": "11001", "q": "11011001", "r": "11100", "s": "0010",
    "t": "01100", "u": "00001", "v": "1101110", "w": "00000", "x": "00111", "y": "0001010", "z": "11011000",
}
HUFF_ESC = "000101111"
EXT_CODES = {  # character -> bits after the escape, in reading order
    "!": "10101100", "$": "10011000", "&": "0000011", "+": "11111011", "-": "11110010", "@": "11000101", "^": "11110100",
    "B": "11001110", "C": "11011001", "D": "10011111", "E": "01111000", "F": "10011100", "G": "10101011", "H": "10111001",
    "I": "10111100", "J": "0000111", "K": "10100100", "L": "10010010", "M": "11011011", "N": "0000010", "O": "11101011",
    "P": "10100111", "Q": "01100100", "R": "11100111", "S": "01101010", "T": "10001010", "A": "01011100",
}
EXT_CHARS = EXT_CODES  # the characters the codec can write (save_audit lists the others)


def _tree(codes):
    paths = {p: c for c, p in codes.items()}
    return paths, {p[:i] for p in paths for i in range(1, len(p))}


_TREE, _PREFIXES = _tree(dict(HUFF, **{"<esc>": HUFF_ESC}))
_EXT, _EXT_PREFIXES = _tree(EXT_CODES)


def _walk(r, paths, prefixes, what):
    path = ""
    while True:
        path += str(r.read(1))
        if path in paths:
            return paths[path]
        if path not in prefixes:
            raise ValueError(f"bad {what} bits {path}")


def huff_read(r):
    c = _walk(r, _TREE, _PREFIXES, "item code")
    return _walk(r, _EXT, _EXT_PREFIXES, "extended code character (escape)") if c == "<esc>" else c


def huff_write(w, ch):
    if ch in HUFF:
        bits = HUFF[ch]
    elif ch in EXT_CODES:
        bits = HUFF_ESC + EXT_CODES[ch]
    else:
        raise ValueError(f"no extended code known for {ch!r} (EXT_CODES)")
    for b in bits:
        w.write(int(b), 1)


def split_code(code):
    return list(code)


# ------------------------------------------------------------------------------------------------------------- tables


def _rows(path):
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


class Tables:
    """The widths the codec needs. `Tables.from_excel(dir)` reads a built mod; tests build one by hand."""

    # stats saved right after another one, without their own id (D2's fixed pairs)
    PAIRS = {17: [18], 48: [49], 50: [51], 52: [53], 54: [55, 56], 57: [58, 59]}

    def __init__(self, stats, armor=(), weapons=(), stackable=(), tomes=("tbk", "ibk"), char_stats=None):
        self.stats = stats  # id -> dict(name, bits, add, par, csv_bits, csv_par)
        self.armor, self.weapons, self.stackable = set(armor), set(weapons), set(stackable)
        self.tomes = set(tomes)
        self.char_stats = char_stats or {i: s for i, s in stats.items() if s.get("csv_bits")}

    @classmethod
    def from_excel(cls, excel=EXCEL):
        stats = {}
        for r in _rows(os.path.join(excel, "itemstatcost.txt")):
            if (r.get("*ID") or "").strip().isdigit():
                stats[int(r["*ID"])] = dict(name=r["Stat"], bits=_int(r.get("Save Bits")), add=_int(r.get("Save Add")),
                                            par=_int(r.get("Save Param Bits")), csv_bits=_int(r.get("CSvBits")),
                                            csv_par=_int(r.get("CSvParam")), saved=r.get("Saved") == "1")
        armor = {r["code"] for r in _rows(os.path.join(excel, "armor.txt")) if r.get("code")}
        weapons = {r["code"] for r in _rows(os.path.join(excel, "weapons.txt")) if r.get("code")}
        stack = set()
        for f in ("armor.txt", "weapons.txt", "misc.txt"):
            stack |= {r["code"] for r in _rows(os.path.join(excel, f)) if r.get("code") and r.get("stackable") == "1"}
        t = cls(stats, armor, weapons, stack)
        t.char_stats = {i: s for i, s in stats.items() if s["saved"] and s["csv_bits"]}
        return t


# ---------------------------------------------------------------------------------------------------------- item codec
# Extended mode stores an item stat's parameter in 32 bits whenever the stat has one (Save Param Bits > 0); the value keeps
# Save Bits / Save Add. Read from game-written uniques: oskill 712 (Pyroclastic Flow), skill-on-kill 755 << 6 | 5.
PARAM_BITS = 32
# Quality fields in extended mode (all read from game-written items, docs/save-format.md): magic prefix / suffix, set id and
# unique id 16 bits each (retail 11 / 11 / 12 / 12); rare and crafted names 16 bits each and 8 affix slots of flag + 16 bits
# (retail 8-bit names, 6 slots of flag + 11).
RARE_SLOTS = 8


class _Codec:
    """One pass over an item: `f(name, bits)` reads into `it` or writes from it, so the layout exists once."""

    def __init__(self, tables, it, reader=None, writer=None):
        self.t, self.it, self.r, self.w = tables, it, reader, writer

    def f(self, name, bits):
        if self.r:
            self.it[name] = self.r.read(bits)
        else:
            self.w.write(self.it.get(name, 0), bits)
        return self.it[name] if self.r else self.it.get(name, 0)

    def opt(self, name, bits):
        """1-bit presence flag, then the field."""
        if self.r:
            if self.r.read(1):
                self.it[name] = self.r.read(bits)
        else:
            has = name in self.it
            self.w.write(int(has), 1)
            if has:
                self.w.write(self.it[name], bits)

    def code(self):
        if self.r:
            self.it["code_chars"] = [huff_read(self.r) for _ in range(4)]
            self.it["code"] = "".join(self.it["code_chars"]).rstrip()
        else:
            chars = self.it.get("code_chars") or (split_code(self.it["code"]) + [" "] * 4)[:4]
            for ch in chars:
                huff_write(self.w, ch)

    def string(self, name, bits):
        if self.r:
            s = ""
            while (c := self.r.read(bits)):
                s += chr(c)
            self.it[name] = s
        else:
            for c in self.it.get(name, ""):
                self.w.write(ord(c), bits)
            self.w.write(0, bits)

    def props(self, name):
        stats = self.t.stats
        if self.r:
            out = self.it[name] = []
            while True:
                sid = self.r.read(16)
                if sid == 0xFFFF:
                    break
                group = [sid] + Tables.PAIRS.get(sid, [])
                for k, s in enumerate(group):
                    st = stats.get(s)
                    if st is None or not st["bits"]:
                        raise ValueError(f"stat {s} has no Save Bits (item list misread before this point)")
                    par = self.r.read(PARAM_BITS) if (k == 0 and st["par"]) else None
                    raw = self.r.read(st["bits"])
                    out.append(dict(id=s, name=st["name"], param=par, value=raw - st["add"], lead=k == 0))
        else:
            for p in self.it.get(name, []):
                st = stats[p["id"]]
                if p.get("lead", True):
                    self.w.write(p["id"], 16)
                    if st["par"]:
                        self.w.write(p.get("param") or 0, PARAM_BITS)
                self.w.write(p["value"] + st["add"], st["bits"])
            self.w.write(0xFFFF, 16)


def _item_layout(c):
    """Bit layout of one D2R 3.3 item (docs/save-format.md, "Items"). Children are handled by the list walker."""
    flags = c.f("flags", 32)
    c.f("b105", 8)
    c.f("version", 3)
    c.f("location", 3)
    c.f("equip", 4)
    c.f("x", 4)
    c.f("y", 4)
    c.f("page", 3)
    if flags & 0x10000:  # ear
        c.f("ear_class", 3)
        c.f("ear_level", 7)
        c.string("ear_name", 7)
        return
    c.code()
    it = c.it
    if flags & 0x200000:  # simple
        c.opt("guid", 128)
        c.f("filled", 1)
        return
    c.f("filled", 3)
    c.f("id", 32)
    c.f("ilvl", 7)
    q = c.f("quality", 4)
    c.opt("picture", 3)
    c.opt("autoaffix", 16)
    if q == 1:
        c.f("lowq", 3)
    elif q == 3:
        c.f("superior", 3)
    elif q == 4:
        c.f("prefix", 16)
        c.f("suffix", 16)
    elif q == 5:
        c.f("set_id", 16)
    elif q == 7:
        c.f("unique_id", 16)
    elif q in (6, 8):
        c.f("rare1", 16)
        c.f("rare2", 16)
        for i in range(RARE_SLOTS):  # even slots prefixes, odd slots suffixes
            c.opt(f"affix{i}", 16)
    if flags & 0x4000000:
        c.f("runeword_id", 12)
        c.f("runeword_pad", 4)
    if flags & 0x1000000:
        c.string("personal", 8)
    code = it["code"]
    if code in c.t.tomes:
        c.f("tome", 5)
    c.opt("guid", 128)
    st = c.t.stats
    if code in c.t.armor:
        a = st[31]
        if c.r:
            it["defense"] = c.r.read(a["bits"]) - a["add"]
        else:
            c.w.write(it["defense"] + a["add"], a["bits"])
    if code in c.t.armor or code in c.t.weapons:
        mx, cur = st[73], st[72]
        if c.r:
            it["maxdur"] = c.r.read(mx["bits"]) - mx["add"]
            if it["maxdur"] > 0:
                it["dur"] = c.r.read(cur["bits"]) - cur["add"]
        else:
            c.w.write(it["maxdur"] + mx["add"], mx["bits"])
            if it["maxdur"] > 0:
                c.w.write(it["dur"] + cur["add"], cur["bits"])
    c.f("ts", 1)
    if code in c.t.stackable:
        c.f("quantity", 9)
    if flags & 0x800:
        c.f("sockets", 4)
    if q == 5:
        c.f("set_mask", 5)
    c.props("stats")
    if q == 5:
        for i in range(5):
            if it.get("set_mask", 0) >> i & 1:
                c.props(f"set_stats{i}")
    if flags & 0x4000000:
        c.props("runeword_stats")


def read_item(data, bitpos, tables):
    it = {}
    r = BitReader(data, bitpos)
    try:
        _item_layout(_Codec(tables, it, reader=r))
    except (IndexError, KeyError, ValueError) as e:
        raise ValueError(f"item at byte {bitpos // 8:#x} (code {it.get('code', '?')!r}): {e}") from None
    # padding to the next byte; a non-simple item that ends exactly on a byte boundary gets a whole zero byte (simple items
    # do not: docs/save-format.md)
    end = (r.pos + 7) // 8 * 8 + (8 if r.pos % 8 == 0 and not it["flags"] & 0x200000 else 0)
    it["_raw"] = data[bitpos // 8:end // 8]
    return it, end


def write_item(it, tables):
    w = BitWriter()
    _item_layout(_Codec(tables, it, writer=w))
    return w.tobytes() + (bytes(1) if w.pos % 8 == 0 and not it["flags"] & 0x200000 else b"")


def read_item_list(data, off, tables):
    """`JM` + u16 count + items (each followed by its socketed children). Returns (items, end offset)."""
    if data[off:off + 2] != b"JM":
        raise ValueError(f"no JM at {off:#x}")
    n = struct.unpack_from("<H", data, off + 2)[0]
    pos, items = (off + 4) * 8, []
    for _ in range(n):
        it, pos = read_item(data, pos, tables)
        kids = []
        for _k in range(it.get("filled", 0) if not it["flags"] & 0x200000 else 0):
            kid, pos = read_item(data, pos, tables)
            kids.append(kid)
        it["children"] = kids
        items.append(it)
    return items, pos // 8


def write_item_list(items, tables):
    out = b"JM" + struct.pack("<H", len(items))
    for it in items:
        out += write_item(it, tables)
        for kid in it.get("children", []):
            out += write_item(kid, tables)
    return out


# ------------------------------------------------------------------------------------------------------------- .d2s

SIG = 0xAA55AA55


def checksum(data):
    d = bytearray(data)
    d[12:16] = b"\0\0\0\0"
    c = 0
    for b in d:
        c = (((c << 1) | (c >> 31)) + b) & 0xFFFFFFFF
    return c


def fix_header(data):
    d = bytearray(data)
    d[8:12] = struct.pack("<I", len(d))
    d[12:16] = struct.pack("<I", checksum(d))
    return bytes(d)


def read_char_stats(data, off, tables):
    """`gf` + (16-bit id, CSvParam bits, CSvBits value) ... 0xffff. Returns (stats, end offset)."""
    if data[off:off + 2] != b"gf":
        raise ValueError(f"no gf at {off:#x}")
    r = BitReader(data, (off + 2) * 8)
    out = []
    while True:
        sid = r.read(16)
        if sid == 0xFFFF:
            break
        st = tables.char_stats.get(sid)
        if st is None:
            raise ValueError(f"character stat {sid} has no CSvBits")
        par = r.read(st["csv_par"]) if st["csv_par"] else None
        out.append(dict(id=sid, name=st["name"], param=par, value=r.read(st["csv_bits"])))
    return out, (r.pos + 7) // 8


def write_char_stats(stats, tables):
    w = BitWriter()
    for s in stats:
        st = tables.char_stats[s["id"]]
        w.write(s["id"], 16)
        if st["csv_par"]:
            w.write(s.get("param") or 0, st["csv_par"])
        w.write(s["value"], st["csv_bits"])
    w.write(0xFFFF, 16)
    return b"gf" + w.tobytes()


class D2S:
    """A parsed character. Unparsed regions (header, quests, waypoints, NPC flags) are kept as bytes."""

    def __init__(self, data, tables):
        self.t = tables
        self.data = data
        if struct.unpack_from("<I", data, 0)[0] != SIG:
            raise ValueError("not a .d2s (signature)")
        self.version, self.size, self.checksum = struct.unpack_from("<III", data, 4)
        self.cls = data[0x18]
        self.level = data[0x1B]
        self.name = data[0x12B:0x12B + 48].split(b"\0")[0].decode("utf-8", "replace")
        gf = data.index(b"gf", 0x300)
        self.head = data[:gf]
        self.stats, i = read_char_stats(data, gf, tables)
        if data[i:i + 2] != b"if":
            raise ValueError(f"no if after the stats ({i:#x})")
        jm = data.index(b"JM", i)
        self.skills = list(data[i + 2:jm])
        self.items, i = read_item_list(data, jm, tables)
        # corpse list: JM + count, each corpse 12 bytes then its own item list
        if data[i:i + 2] != b"JM":
            raise ValueError(f"no corpse JM at {i:#x}")
        ncorpse = struct.unpack_from("<H", data, i + 2)[0]
        i += 4
        self.corpses = []
        for _ in range(ncorpse):
            hdr = data[i:i + 12]
            items, i = read_item_list(data, i + 12, tables)
            self.corpses.append(dict(header=hdr, items=items))
        if data[i:i + 2] != b"jf":
            raise ValueError(f"no jf at {i:#x}")
        i += 2
        self.merc = None
        if data[i:i + 2] == b"JM":
            self.merc, i = read_item_list(data, i, tables)
        if data[i:i + 2] != b"kf":
            raise ValueError(f"no kf at {i:#x}")
        i += 2
        self.golem = None
        has_golem = data[i] if i < len(data) else 0
        i += 1
        if has_golem:
            self.golem, i = read_item(data, i * 8, tables)
            i //= 8
        self.tail = data[i:]

    def encode(self):
        body = self.head + write_char_stats(self.stats, self.t) + b"if" + bytes(self.skills)
        body += write_item_list(self.items, self.t)
        body += b"JM" + struct.pack("<H", len(self.corpses))
        for c in self.corpses:
            body += c["header"] + write_item_list(c["items"], self.t)
        body += b"jf"
        if self.merc is not None:
            body += write_item_list(self.merc, self.t)
        body += b"kf" + bytes([1 if self.golem else 0])
        if self.golem:
            body += write_item(self.golem, self.t)
        return fix_header(body + self.tail)

    def all_items(self):
        """(container, item) for every item incl. socketed children; container = player / corpse / merc / golem."""
        def walk(where, items):
            for it in items:
                yield where, it
                for kid in it.get("children", []):
                    yield where + "/socket", kid
        yield from walk("player", self.items)
        for c in self.corpses:
            yield from walk("corpse", c["items"])
        if self.merc:
            yield from walk("merc", self.merc)
        if self.golem:
            yield "golem", self.golem


# ------------------------------------------------------------------------------------------------------------- .d2i


class D2I:
    """Shared stash: pages of a 64-byte header (0xaa55aa55, u32 flags, u32 version, u32 gold, u32 page size, 44 bytes)
    and a JM list; D2RLoader's extra tabs are more pages of the same shape."""

    def __init__(self, data, tables):
        self.t, self.pages, off = tables, [], 0
        while off < len(data):
            sig, flags, ver, gold, size = struct.unpack_from("<IIIII", data, off)
            if sig != SIG:
                raise ValueError(f"no stash page signature at {off:#x}")
            hdr = data[off:off + 64]
            items, end = read_item_list(data, off + 64, tables) if data[off + 64:off + 66] == b"JM" else ([], off + 64)
            page = dict(header=hdr, gold=gold, version=ver, items=items, extra=data[end:off + size])
            self.pages.append(page)
            off += size

    def encode(self):
        out = b""
        for p in self.pages:
            body = write_item_list(p["items"], self.t) if p["items"] or p["header"] != p.get("_empty") else b""
            body += p["extra"]
            hdr = bytearray(p["header"])
            hdr[16:20] = struct.pack("<I", 64 + len(body))
            out += bytes(hdr) + body
        return out

    def all_items(self):
        for n, p in enumerate(self.pages):
            for it in p["items"]:
                yield f"stash{n}", it
                for kid in it.get("children", []):
                    yield f"stash{n}/socket", kid


# ------------------------------------------------------------------------------------------------------------ sidecar


def check_sidecar(d2s_bytes, d2rl_bytes):
    """Problems (empty = consistent) between a .d2s and its D2RLoader sidecar: the four values that must follow an edit."""
    p = []
    if d2rl_bytes[:4] != b"D2RL":
        return ["sidecar magic is not D2RL"]
    ver, hsize, blen = struct.unpack_from("<HHI", d2rl_bytes, 4)
    body = d2rl_bytes[hsize:]
    if len(body) != blen:
        p.append(f"sidecar body length {len(body)} != header {blen}")
    if hashlib.sha256(body).digest() != d2rl_bytes[0x0C:0x2C]:
        p.append("sidecar body hash differs")
    ck, size = struct.unpack_from("<II", d2rl_bytes, 0x34)
    if ck != struct.unpack_from("<I", d2s_bytes, 12)[0]:
        p.append(f"sidecar checksum {ck:#x} != save's")
    if size != len(d2s_bytes):
        p.append(f"sidecar size {size} != save size {len(d2s_bytes)}")
    if hashlib.sha256(d2s_bytes).digest() != d2rl_bytes[0x3C:0x5C]:
        p.append("sidecar save hash differs")
    if checksum(d2s_bytes) != struct.unpack_from("<I", d2s_bytes, 12)[0]:
        p.append("save checksum wrong")
    return p


# --------------------------------------------------------------------------------------------------------- views/diff

QUALITY = {1: "low", 2: "normal", 3: "superior", 4: "magic", 5: "set", 6: "rare", 7: "unique", 8: "crafted"}
_VOLATILE = {"_raw", "children", "code_chars", "location", "equip", "x", "y", "page", "id", "guid", "b105"}


def item_key(where, it):
    return f"{where}:{it.get('location')}/{it.get('equip')}/{it.get('page')}@{it.get('x')},{it.get('y')}:{it.get('code')}"


def item_view(it):
    v = {k: val for k, val in it.items() if k not in _VOLATILE and not k.startswith("_")}
    for k in list(v):
        if k == "stats" or k.endswith("_stats") or k.startswith("set_stats"):
            v[k] = sorted((p["id"], p["param"], p["value"]) for p in v[k])
    v["children"] = [item_view(k) for k in it.get("children", [])]
    return v


def snapshot(save):
    snap = {"items": {}}
    if isinstance(save, D2S):
        snap.update(name=save.name, cls=save.cls, level=save.level,
                    stats={s["name"]: s["value"] for s in save.stats}, skills=save.skills,
                    merc=save.merc is not None, corpses=len(save.corpses))
    for where, it in save.all_items():
        if "/socket" in where:
            continue  # inside the parent's view
        key = item_key(where, it)
        n = 2
        while key in snap["items"]:
            key = f"{item_key(where, it)}#{n}"
            n += 1
        snap["items"][key] = item_view(it)
    return snap


def diff_snapshots(a, b):
    out = []
    for k in ("name", "cls", "level", "merc", "corpses"):
        if a.get(k) != b.get(k):
            out.append(f"{k}: {a.get(k)} -> {b.get(k)}")
    for k in sorted(set(a.get("stats", {})) | set(b.get("stats", {}))):
        if a.get("stats", {}).get(k) != b.get("stats", {}).get(k):
            out.append(f"stat {k}: {a['stats'].get(k)} -> {b['stats'].get(k)}")
    if a.get("skills") != b.get("skills"):
        out.append(f"skills: {a.get('skills')} -> {b.get('skills')}")
    ia, ib = a["items"], b["items"]
    for k in sorted(set(ia) - set(ib)):
        out.append(f"LOST {k}")
    for k in sorted(set(ib) - set(ia)):
        out.append(f"NEW  {k}")
    for k in sorted(set(ia) & set(ib)):
        if ia[k] != ib[k]:
            fields = sorted(f for f in set(ia[k]) | set(ib[k]) if ia[k].get(f) != ib[k].get(f))
            out.append(f"CHANGED {k}: " + ", ".join(f"{f} {ia[k].get(f)} -> {ib[k].get(f)}" for f in fields))
    return out


def load(path, tables):
    data = open(path, "rb").read()
    if path.lower().endswith(".d2i"):
        return D2I(data, tables)
    return D2S(data, tables)


def describe(it, indent=""):
    q = QUALITY.get(it.get("quality"), "simple" if it["flags"] & 0x200000 else "?")
    extra = []
    for k in ("ilvl", "unique_id", "set_id", "prefix", "suffix", "runeword_id", "defense", "maxdur", "dur", "quantity",
              "sockets", "filled"):
        if k in it:
            extra.append(f"{k}={it[k]}")
    if it["flags"] & 0x400000:
        extra.append("ethereal")
    lines = [f"{indent}{it.get('code')!s:5} {q:8} loc={it['location']} eq={it['equip']} page={it['page']} "
             f"@{it['x']},{it['y']} " + " ".join(extra)]
    for k in sorted(k for k in it if k == "stats" or k.endswith("_stats") or k.startswith("set_stats")):
        for p in it[k]:
            par = f"[{p['param']}]" if p["param"] is not None else ""
            lines.append(f"{indent}    {k}: {p['id']} {p['name']}{par} = {p['value']}")
    for kid in it.get("children", []):
        lines += describe(kid, indent + "  > ")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["show", "roundtrip", "diff", "sidecar", "snapshot"])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--excel", default=os.environ.get("MXL2012_EXCEL", EXCEL))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    if a.cmd == "sidecar":
        bad = 0
        for f in a.files:
            p = check_sidecar(open(f, "rb").read(), open(os.path.splitext(f)[0] + ".d2rl", "rb").read())
            print(f"{os.path.basename(f)}: {'OK' if not p else '; '.join(p)}")
            bad += bool(p)
        return 1 if bad else 0
    t = Tables.from_excel(a.excel)
    if a.cmd == "show":
        for f in a.files:
            s = load(f, t)
            if a.json:
                print(json.dumps(snapshot(s), indent=1, default=str))
                continue
            if isinstance(s, D2S):
                print(f"{s.name}: class {s.cls}, level {s.level}, version field {s.data[4:8].hex(' ')}, {len(s.data)} bytes")
                print("stats:", ", ".join(f"{x['name']}={x['value']}" for x in s.stats))
                print("skills:", s.skills)
                print(f"corpses {len(s.corpses)}, merc {'yes' if s.merc is not None else 'no'}, golem {'yes' if s.golem else 'no'}")
            for where, it in s.all_items():
                if "/socket" not in where:
                    print(f"[{where}] " + "\n".join(describe(it)))
        return 0
    if a.cmd == "roundtrip":
        bad = 0
        for f in a.files:
            data = open(f, "rb").read()
            try:
                s = load(f, t)
                ok = s.encode() == data
                n = sum(1 for _ in s.all_items())
                print(f"{os.path.basename(f)}: {'OK' if ok else 'DIFFERS'} ({n} items)")
            except ValueError as e:
                ok = False
                print(f"{os.path.basename(f)}: PARSE ERROR {e}")
            bad += not ok
        return 1 if bad else 0
    if a.cmd == "snapshot":
        snap = snapshot(load(a.files[0], t))
        text = json.dumps(snap, indent=1, sort_keys=True, default=str)
        if a.out:
            with open(a.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        else:
            print(text)
        return 0
    if a.cmd == "diff":
        if len(a.files) != 2:
            ap.error("diff takes two files")
        snaps = [json.load(open(f, encoding="utf-8")) if f.endswith(".json") else
                 json.loads(json.dumps(snapshot(load(f, t)), default=str)) for f in a.files]
        d = diff_snapshots(*snaps)
        print("\n".join(d) if d else "no differences")
        return 1 if d else 0


if __name__ == "__main__":
    sys.exit(main())
