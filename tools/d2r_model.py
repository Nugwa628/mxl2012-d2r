"""Reader (and first writer) for D2R's HD model files: .model, .skeleton and .animations are all RAD Granny 2 (GR2) containers.

What is here (see docs/hd-models.md for the findings):
  * BitKnit2 decompressor (pure Python; port of the algorithm documented in eiz/pybg3 + libbg3, MIT; cross-checked
    against the file CRCs),
  * GR2 container reader: header, sections, relocations, mixed-marshalling blocks, the type-definition tables and the
    object graph (a plain Python tree: dict per struct, list per array, tuples of floats for vectors),
  * GR2 container writer: serialises such a tree again (sections uncompressed, new relocations, CRC) -- a Granny
    reader accepts a section stored with compression type 0,
  * `roundtrip()`: decode -> tree -> encode -> decode -> compare, and a container-level repack check.

Usage:
  py tools/d2r_model.py info  <file>              header, sections, root type, summary of the tree
  py tools/d2r_model.py dump  <file> [--depth N]  the tree as text
  py tools/d2r_model.py check <file|dir> ...      round-trip every .model/.skeleton/.animations found
  py tools/d2r_model.py repack <in> <out>         write the file again with uncompressed sections

Files are read from the extract (never committed); this tool only writes what you tell it to.
"""
import argparse
import bisect
import struct
import sys
import zlib
from array import array
from pathlib import Path

GR2_MAGIC_LE64 = bytes.fromhex("e59b495e6f631f141e13eba990beedc4")
GR2_MAGICS = {
    bytes.fromhex("b80d6b1ea1ba4e5e2e1d8b11fd41e3a6"): ("le", 32),  # little endian, 32-bit pointers (value from opengr2; unused here)
    GR2_MAGIC_LE64: ("le", 64),
}

COMPRESSION = {0: "none", 1: "oodle0", 2: "oodle1", 3: "bitknit1", 4: "bitknit2"}

# ---------------------------------------------------------------------------------------------------------------------
# BitKnit2 (compression type 4)
# ---------------------------------------------------------------------------------------------------------------------

BITKNIT2_MAGIC = 0x75B1


class _Model:
    """Adaptive frequency model: 15-bit cumulative table, updated every 1024 symbols (deferred_adaptive_model)."""
    __slots__ = ("vocab", "sums", "acc", "counter", "incr", "last_incr")

    def __init__(self, vocab: int, min_probable: int):
        total = 1 << 15
        eq = vocab - min_probable
        self.vocab = vocab
        self.sums = [(total - min_probable) * i // eq for i in range(eq)] + [total - vocab + i for i in range(eq, vocab + 1)]
        self.acc = [1] * vocab
        self.counter = 0
        self.incr = (total - vocab) // 1024
        self.last_incr = 1 + total - vocab - self.incr * 1024

    def observe(self, sym: int) -> None:
        self.acc[sym] += self.incr
        self.counter = (self.counter + 1) & 1023
        if self.counter == 0:
            acc, sums = self.acc, self.sums
            acc[sym] += self.last_incr
            s = 0
            for i in range(1, self.vocab + 1):
                s += acc[i - 1]
                sums[i] = (sums[i] + (((s - sums[i]) & 0xFFFFFFFF) >> 1)) & 0xFFFF
                acc[i - 1] = 1


class BitKnitError(ValueError):
    pass


def bitknit2_decompress(src: bytes, out_size: int) -> bytes:
    """Decompress one GR2 section (or any BitKnit2 stream with the 0x75B1 magic word first)."""
    words = array("H")
    words.frombytes(src[:len(src) & ~1])
    if sys.byteorder != "little":
        words.byteswap()
    nwords = len(words)
    if not nwords or words[0] != BITKNIT2_MAGIC:
        raise BitKnitError("missing BitKnit2 magic")
    pos = 1
    out = bytearray(out_size)
    cmd_models = [_Model(300, 36) for _ in range(4)]
    ref_models = [_Model(40, 0) for _ in range(4)]
    off_model = _Model(21, 0)
    cache = [1] * 8            # entries
    order = list(range(8))     # order[i] = slot of the i-th most recent entry
    delta = 1
    dst = 0
    while dst < out_size:
        if pos >= nwords:
            raise BitKnitError("unexpected end of stream")
        qend = min(out_size, (dst & ~0xFFFF) + 0x10000)
        if words[pos] == 0:                       # stored quantum
            pos += 1
            n = min((nwords - pos) * 2, qend - dst)
            out[dst:dst + n] = words[pos:pos + (n + 1) // 2].tobytes()[:n]
            dst += n
            pos += n // 2
            continue
        # tying the knot: two rANS states from 3 words
        init0, init1 = words[pos], words[pos + 1]
        pos += 2
        m = (init0 << 16) | init1
        split = m & 15
        m >>= 4
        if m < 0x10000:
            m = (m << 16) | words[pos]
            pos += 1
        b1 = m >> split
        if b1 < 0x10000:
            b1 = (b1 << 16) | words[pos]
            pos += 1
        b2 = ((m << 16) | words[pos]) & ((1 << (16 + split)) - 1)
        pos += 1
        b2 |= 1 << (16 + split)
        if dst == 0:
            out[0] = b1 & 0xFF                    # pop_bits(8)
            b1 >>= 8
            if b1 < 0x10000:
                b1 = (b1 << 16) | words[pos]
                pos += 1
            b1, b2 = b2, b1
            dst = 1
        while dst < qend:
            mi = dst & 3
            mdl = cmd_models[mi]
            sums = mdl.sums
            code = b1 & 0x7FFF
            sym = bisect.bisect_right(sums, code) - 1
            b1 = (b1 >> 15) * (sums[sym + 1] - sums[sym]) + code - sums[sym]
            if b1 < 0x10000:
                b1 = (b1 << 16) | words[pos]
                pos += 1
            mdl.observe(sym)
            b1, b2 = b2, b1
            if sym < 256:
                out[dst] = (sym + out[dst - delta]) & 0xFF
                dst += 1
                continue
            if sym < 288:
                length = sym - 254
            else:
                nb = sym - 287
                bits = b1 & ((1 << nb) - 1)
                b1 >>= nb
                if b1 < 0x10000:
                    b1 = (b1 << 16) | words[pos]
                    pos += 1
                b1, b2 = b2, b1
                length = (1 << nb) + bits + 32
            mdl = ref_models[mi]
            sums = mdl.sums
            code = b1 & 0x7FFF
            ref = bisect.bisect_right(sums, code) - 1
            b1 = (b1 >> 15) * (sums[ref + 1] - sums[ref]) + code - sums[ref]
            if b1 < 0x10000:
                b1 = (b1 << 16) | words[pos]
                pos += 1
            mdl.observe(ref)
            b1, b2 = b2, b1
            if ref < 8:
                slot = order[ref]
                dist = cache[slot]
                del order[ref]
                order.insert(0, slot)
            else:
                mdl = off_model
                sums = mdl.sums
                code = b1 & 0x7FFF
                nbits = bisect.bisect_right(sums, code) - 1
                b1 = (b1 >> 15) * (sums[nbits + 1] - sums[nbits]) + code - sums[nbits]
                if b1 < 0x10000:
                    b1 = (b1 << 16) | words[pos]
                    pos += 1
                mdl.observe(nbits)
                b1, b2 = b2, b1
                k = nbits & 15
                bits = b1 & ((1 << k) - 1)
                b1 >>= k
                if b1 < 0x10000:
                    b1 = (b1 << 16) | words[pos]
                    pos += 1
                b1, b2 = b2, b1
                if nbits >= 16:
                    bits = (bits << 16) | words[pos]
                    pos += 1
                dist = (32 << nbits) + (bits << 5) - 32 + (ref - 7)
                s6, s7 = order[6], order[7]       # insert(): value goes to recency index 6, old 6 moves to 7
                cache[s7] = cache[s6]
                cache[s6] = dist
            if dist > dst or length > qend - dst and length > out_size - dst:
                raise BitKnitError("bad copy")
            delta = dist
            if dist >= length:
                out[dst:dst + length] = out[dst - dist:dst - dist + length]
            else:
                for i in range(length):
                    out[dst + i] = out[dst + i - dist]
            dst += length
        if b1 != 0x10000 or b2 != 0x10000:
            raise BitKnitError("rANS stream corrupted")
    return bytes(out)


# ---------------------------------------------------------------------------------------------------------------------
# GR2 container
# ---------------------------------------------------------------------------------------------------------------------

class Section:
    def __init__(self):
        self.compression = 0
        self.offset = 0
        self.compressed_size = 0
        self.size = 0                 # uncompressed size
        self.alignment = 4
        self.first16 = 0
        self.first8 = 0
        self.relocations = []         # (offset_in_section, target_section, target_offset)
        self.marshalling = b""        # raw mixed-marshalling block (little endian files: kept as is)
        self.num_marshalling = 0
        self.data = b""               # decompressed


class Gr2File:
    """Container level view. `tree` is filled by `parse_tree()`."""
    def __init__(self):
        self.version = 7
        self.format = 0
        self.tag = 0
        self.extra_tags = [0, 0, 0, 0]
        self.string_crc = 0
        self.reserved = [0, 0, 0]
        self.root_type = (0, 0)
        self.root_node = (0, 0)
        self.sections: list[Section] = []
        self.crc_ok = None

    # -- reading ---------------------------------------------------------------------------------------------------
    @classmethod
    def read(cls, data: bytes) -> "Gr2File":
        if data[:16] != GR2_MAGIC_LE64:
            raise ValueError("not a little-endian 64-bit GR2 file")
        f = cls()
        header_size, f.format, _r1, _r2 = struct.unpack_from("<4I", data, 16)
        (f.version, file_size, crc, sec_off, nsec, rt_s, rt_o, rn_s, rn_o, f.tag) = struct.unpack_from("<10I", data, 0x20)
        f.extra_tags = list(struct.unpack_from("<4I", data, 0x48))
        f.string_crc = struct.unpack_from("<I", data, 0x58)[0]
        f.reserved = list(struct.unpack_from("<3I", data, 0x5C))
        f.root_type, f.root_node = (rt_s, rt_o), (rn_s, rn_o)
        f.file_size, f.crc, f.header_size = file_size, crc, header_size
        f.crc_ok = (zlib.crc32(data[0x20 + sec_off:file_size]) & 0xFFFFFFFF) == crc
        for i in range(nsec):
            s = Section()
            (s.compression, s.offset, s.compressed_size, s.size, s.alignment, s.first16, s.first8,
             reloc_off, nreloc, marsh_off, s.num_marshalling) = struct.unpack_from("<11I", data, 0x20 + sec_off + 44 * i)
            raw = data[s.offset:s.offset + s.compressed_size]
            if s.compression == 0 or s.size == 0:
                s.data = bytes(raw) if s.compression == 0 else b""
            elif s.compression == 4:
                s.data = bitknit2_decompress(raw, s.size)
            else:
                raise NotImplementedError(f"section {i}: compression {COMPRESSION.get(s.compression, s.compression)}")
            if nreloc:
                if s.compression == 0:
                    rb = data[reloc_off:reloc_off + 12 * nreloc]
                else:
                    csize = struct.unpack_from("<I", data, reloc_off)[0]
                    rb = bitknit2_decompress(data[reloc_off + 4:reloc_off + 4 + csize], 12 * nreloc)
                s.relocations = [struct.unpack_from("<3I", rb, 12 * k) for k in range(nreloc)]
            if s.num_marshalling:
                # entries: (count, offset in this section, type section, type offset), 16 bytes each
                if s.compression == 0:
                    s.marshalling = data[marsh_off:marsh_off + 16 * s.num_marshalling]
                else:
                    csize = struct.unpack_from("<I", data, marsh_off)[0]
                    s.marshalling = bitknit2_decompress(data[marsh_off + 4:marsh_off + 4 + csize], 16 * s.num_marshalling)
            s.reloc_info = (reloc_off, nreloc, marsh_off)
            f.sections.append(s)
        return f

    # -- writing ---------------------------------------------------------------------------------------------------
    def write(self) -> bytes:
        """Container with all sections stored uncompressed (compression 0). Relocations are raw 12-byte records."""
        nsec = len(self.sections)
        header_size = 0x20 + 0x48 + 44 * nsec
        pos = header_size
        blobs = []
        entries = []
        for s in self.sections:
            data = s.data
            reloc = b"".join(struct.pack("<3I", *r) for r in s.relocations)
            off = pos
            blobs.append(data)
            pos += len(data)
            r_off = pos
            blobs.append(reloc)
            pos += len(reloc)
            m_off = pos
            blobs.append(s.marshalling)
            pos += len(s.marshalling)
            entries.append(struct.pack("<11I", 0, off, len(data), len(data), s.alignment, s.first16, s.first8,
                                       r_off, len(s.relocations), m_off, s.num_marshalling))
        body = b"".join(entries) + b"".join(blobs)
        hdr = struct.pack("<10I", self.version, pos, 0, 0x48, nsec, *self.root_type, *self.root_node, self.tag)
        hdr += struct.pack("<4I", *self.extra_tags) + struct.pack("<I", self.string_crc) + struct.pack("<3I", *self.reserved)
        crc = zlib.crc32(body) & 0xFFFFFFFF
        hdr = hdr[:8] + struct.pack("<I", crc) + hdr[12:]
        return GR2_MAGIC_LE64 + struct.pack("<4I", header_size, 0, 0, 0) + hdr + body


# ---------------------------------------------------------------------------------------------------------------------
# Granny type system and object graph
# ---------------------------------------------------------------------------------------------------------------------

M_END, M_INLINE, M_REF, M_REFARRAY, M_ARRAYREFS, M_VARIANT, M_UNSUPPORTED, M_VARARRAY, M_STRING, M_TRANSFORM, \
    M_REAL32, M_INT8, M_UINT8, M_BINORMAL8, M_NORMAL8, M_INT16, M_UINT16, M_BINORMAL16, M_NORMAL16, M_INT32, M_UINT32, \
    M_REAL16, M_EMPTYREF = range(23)
MEMBER_NAMES = ["End", "Inline", "Reference", "ReferenceToArray", "ArrayOfReferences", "VariantReference", "Unsupported",
                "ReferenceToVariantArray", "String", "Transform", "Real32", "Int8", "UInt8", "BinormalInt8", "NormalUInt8",
                "Int16", "UInt16", "BinormalInt16", "NormalUInt16", "Int32", "UInt32", "Real16", "EmptyReference"]
# (struct format, size) of the scalar member types
SCALAR = {M_REAL32: ("f", 4), M_INT8: ("b", 1), M_UINT8: ("B", 1), M_BINORMAL8: ("b", 1), M_NORMAL8: ("B", 1),
          M_INT16: ("h", 2), M_UINT16: ("H", 2), M_BINORMAL16: ("h", 2), M_NORMAL16: ("H", 2), M_INT32: ("i", 4),
          M_UINT32: ("I", 4), M_REAL16: ("H", 2)}  # Real16 is kept as its raw 16 bits
PTR = 8  # 64-bit files; the records are packed (no alignment padding)
MEMBER_RECORD = 44  # type u32, name ptr, definition ptr, array_size u32, extra[3] i32, ignored ptr


class Member:
    __slots__ = ("type", "name", "defn", "array_size", "extra", "ignored")

    def __init__(self, type, name, defn=None, array_size=0, extra=(0, 0, 0), ignored=0):
        self.type, self.name, self.defn, self.array_size, self.extra, self.ignored = type, name, defn, array_size, tuple(extra), ignored

    def __repr__(self):
        return f"<{MEMBER_NAMES[self.type]} {self.name}[{self.array_size}]>"


class TypeDef:
    """A Granny data_type_definition: the ordered member list of a struct."""
    def __init__(self, members=None):
        self.members: list[Member] = members or []
        self._size = None
        self.end_ignored = 0

    def size(self) -> int:
        if self._size is None:
            self._size = sum(member_size(m) for m in self.members)
        return self._size

    def __repr__(self):
        ms = ", ".join(f"{m.name}:{MEMBER_NAMES[m.type]}" for m in self.members[:8])
        return f"TypeDef({len(self.members)}: {ms}{', ...' if len(self.members) > 8 else ''})"


def member_size(m: Member) -> int:
    t = m.type
    n = m.array_size or 1
    if t == M_INLINE:
        return m.defn.size() * n
    if t in SCALAR:
        return SCALAR[t][1] * n
    if t == M_TRANSFORM:
        return 68 * n
    if t in (M_REF, M_STRING, M_EMPTYREF):
        return PTR * n
    if t in (M_REFARRAY, M_ARRAYREFS):
        return 4 + PTR
    if t == M_VARIANT:
        return 2 * PTR
    if t == M_VARARRAY:
        return PTR + 4 + PTR
    raise ValueError(f"member type {t}")


class Obj:
    """One struct instance of the tree: `td` (TypeDef) and the member values in `f` (name -> value)."""
    __slots__ = ("td", "f")

    def __init__(self, td, f=None):
        self.td, self.f = td, f if f is not None else {}

    def __getitem__(self, k):
        return self.f[k]

    def __setitem__(self, k, v):
        self.f[k] = v

    def get(self, k, d=None):
        return self.f.get(k, d)

    def __repr__(self):
        return "Obj(" + ", ".join(self.f) + ")"


class Variant:
    """VariantReference value: the type of the pointed-to struct (or array of structs) and the data itself."""
    __slots__ = ("td", "obj")

    def __init__(self, td, obj):
        self.td, self.obj = td, obj


class Transform:
    __slots__ = ("flags", "position", "orientation", "scale_shear")

    def __init__(self, flags, position, orientation, scale_shear):
        self.flags, self.position, self.orientation, self.scale_shear = flags, tuple(position), tuple(orientation), tuple(scale_shear)

    def __eq__(self, o):
        return isinstance(o, Transform) and (self.flags, self.position, self.orientation, self.scale_shear) == (o.flags, o.position, o.orientation, o.scale_shear)


class Reader:
    def __init__(self, gr2: Gr2File):
        self.g = gr2
        self.rel = [{o: (ts, to) for (o, ts, to) in s.relocations} for s in gr2.sections]
        self.types: dict[tuple, TypeDef] = {}
        self.objs: dict[tuple, Obj] = {}
        self.strings: dict[tuple, str] = {}

    def ptr(self, sec, off):
        return self.rel[sec].get(off)

    def cstr(self, addr):
        if addr is None:
            return None
        if addr not in self.strings:
            d = self.g.sections[addr[0]].data
            e = d.index(b"\0", addr[1])
            self.strings[addr] = d[addr[1]:e].decode("utf-8", "surrogateescape")
        return self.strings[addr]

    def typedef(self, addr):
        if addr is None:
            return None
        td = self.types.get(addr)
        if td is not None:
            return td
        td = TypeDef()
        self.types[addr] = td
        sec, off = addr
        d = self.g.sections[sec].data
        while True:
            t = struct.unpack_from("<I", d, off)[0]
            if t == M_END:
                td.end_ignored = struct.unpack_from("<Q", d, off + 36)[0]
                break
            name = self.cstr(self.ptr(sec, off + 4))
            dfn = self.typedef(self.ptr(sec, off + 12))
            asz, = struct.unpack_from("<I", d, off + 20)
            extra = struct.unpack_from("<3i", d, off + 24)
            ign, = struct.unpack_from("<Q", d, off + 36)
            td.members.append(Member(t, name, dfn, asz, extra, ign))
            off += MEMBER_RECORD
        return td

    def struct_at(self, sec, off, td):
        """Inline struct value of type td at (sec, off)."""
        o = Obj(td)
        d = self.g.sections[sec].data
        for m in td.members:
            o.f[m.name] = self.member(sec, off, d, m)
            off += member_size(m)
        return o

    def ref_obj(self, addr, td):
        if addr is None:
            return None
        key = (addr, id(td))
        o = self.objs.get(key)
        if o is None:
            o = self.struct_at(addr[0], addr[1], td)
            self.objs[key] = o
        return o

    def member(self, sec, off, d, m):
        t = m.type
        n = m.array_size or 1
        if t in SCALAR:
            fmt = SCALAR[t][0]
            vals = list(struct.unpack_from(f"<{n}{fmt}", d, off))
            return vals if m.array_size else vals[0]
        if t == M_TRANSFORM:
            def one(o):
                v = struct.unpack_from("<I3f4f9f", d, o)
                return Transform(v[0], v[1:4], v[4:8], v[8:17])
            vals = [one(off + 68 * i) for i in range(n)]
            return vals if m.array_size else vals[0]
        if t == M_INLINE:
            sz = m.defn.size()
            vals = [self.struct_at(sec, off + sz * i, m.defn) for i in range(n)]
            return vals if m.array_size else vals[0]
        if t == M_STRING:
            vals = [self.cstr(self.ptr(sec, off + PTR * i)) for i in range(n)]
            return vals if m.array_size else vals[0]
        if t == M_REF:
            vals = [self.ref_obj(self.ptr(sec, off + PTR * i), m.defn) for i in range(n)]
            return vals if m.array_size else vals[0]
        if t == M_EMPTYREF:
            return None
        if t in (M_REFARRAY, M_ARRAYREFS):
            count, = struct.unpack_from("<I", d, off)
            addr = self.ptr(sec, off + 4)
            if not count or addr is None:
                return []
            if t == M_REFARRAY:
                sz = m.defn.size()
                return [self.struct_at(addr[0], addr[1] + sz * i, m.defn) for i in range(count)]
            return [self.ref_obj(self.ptr(addr[0], addr[1] + PTR * i), m.defn) for i in range(count)]
        if t == M_VARIANT:
            td = self.typedef(self.ptr(sec, off))
            addr = self.ptr(sec, off + PTR)
            if td is None or addr is None:
                return None
            return Variant(td, self.ref_obj(addr, td))
        if t == M_VARARRAY:
            td = self.typedef(self.ptr(sec, off))
            count, = struct.unpack_from("<I", d, off + PTR)
            addr = self.ptr(sec, off + PTR + 4)
            if td is None or addr is None or not count:
                return Variant(td, [])
            sz = td.size()
            return Variant(td, [self.struct_at(addr[0], addr[1] + sz * i, td) for i in range(count)])
        raise NotImplementedError(f"member type {MEMBER_NAMES[t]}")


def parse_tree(g: Gr2File):
    """Root object (the granny_file_info struct) of a container."""
    r = Reader(g)
    td = r.typedef(g.root_type)
    return r.struct_at(g.root_node[0], g.root_node[1], td)


def dump(o, depth=3, indent=0, name=""):
    pad = "  " * indent
    if isinstance(o, Obj):
        print(f"{pad}{name}{{")
        if depth <= 0:
            print(f"{pad}  ...")
        else:
            for k, v in o.f.items():
                dump(v, depth - 1, indent + 1, k + ": ")
        print(f"{pad}}}")
    elif isinstance(o, list):
        if o and isinstance(o[0], (int, float)):
            print(f"{pad}{name}[{len(o)}] {o[:12]}{' ...' if len(o) > 12 else ''}")
        else:
            print(f"{pad}{name}[{len(o)}]")
            if depth > 0:
                for i, v in enumerate(o[:6]):
                    dump(v, depth - 1, indent + 1, f"#{i} ")
                if len(o) > 6:
                    print(f"{pad}  ... {len(o) - 6} more")
    elif isinstance(o, Variant):
        print(f"{pad}{name}variant {o.td}")
        if depth > 0:
            dump(o.obj, depth - 1, indent + 1)
    elif isinstance(o, Transform):
        print(f"{pad}{name}T pos={tuple(round(x, 4) for x in o.position)} rot={tuple(round(x, 4) for x in o.orientation)} ss={tuple(round(x, 3) for x in o.scale_shear)}")
    else:
        print(f"{pad}{name}{o!r}")


# ---------------------------------------------------------------------------------------------------------------------
# Writer: object graph -> GR2 container
# ---------------------------------------------------------------------------------------------------------------------

SEC_MAIN, SEC_TYPES = 0, 6  # D2R files only use these two of Granny's eight sections


class Writer:
    """Serialises a tree (as produced by parse_tree, or built by hand from the same TypeDefs) into a Gr2File.

    Layout: the root struct at (0, 0); every other struct, array, string in section 0 in discovery order; the type
    definitions in section 6. Pointers are 8 bytes, records are packed (as in the vanilla files)."""

    def __init__(self, template: Gr2File | None = None):
        self.secs = [bytearray() for _ in range(8)]
        self.relocs: list[list[tuple]] = [[] for _ in range(8)]
        self.template = template
        self.strings: dict[str, tuple] = {}
        self.typedefs: dict[int, tuple] = {}
        self.objs: dict[int, tuple] = {}

    def alloc(self, sec: int, size: int, align: int = 4) -> int:
        b = self.secs[sec]
        pad = -len(b) % align
        b.extend(b"\0" * (pad + size))
        return len(b) - size

    def ptr(self, sec: int, off: int, target: tuple | None) -> None:
        if target is not None:
            self.relocs[sec].append((off, target[0], target[1]))

    def string(self, s: str | None):
        if s is None:
            return None
        a = self.strings.get(s)
        if a is None:
            raw = s.encode("utf-8", "surrogateescape") + b"\0"
            off = self.alloc(SEC_MAIN, len(raw), 1)
            self.secs[SEC_MAIN][off:off + len(raw)] = raw
            a = self.strings[s] = (SEC_MAIN, off)
        return a

    def typedef(self, td: TypeDef | None):
        if td is None:
            return None
        a = self.typedefs.get(id(td))
        if a is not None:
            return a
        off = self.alloc(SEC_TYPES, MEMBER_RECORD * (len(td.members) + 1))
        a = self.typedefs[id(td)] = (SEC_TYPES, off)
        b = self.secs[SEC_TYPES]
        for i, m in enumerate(td.members):
            o = off + MEMBER_RECORD * i
            struct.pack_into("<I", b, o, m.type)
            self.ptr(SEC_TYPES, o + 4, self.string(m.name))
            self.ptr(SEC_TYPES, o + 12, self.typedef(m.defn))
            struct.pack_into("<I3iQ", b, o + 20, m.array_size, *m.extra, m.ignored)
        struct.pack_into("<Q", b, off + MEMBER_RECORD * len(td.members) + 36, td.end_ignored)
        return a

    def struct_into(self, sec: int, off: int, td: TypeDef, obj: Obj) -> None:
        for m in td.members:
            self.member(sec, off, m, obj.f[m.name])
            off += member_size(m)

    def ref(self, obj: Obj | None, td: TypeDef):
        if obj is None:
            return None
        a = self.objs.get(id(obj))
        if a is None:
            off = self.alloc(SEC_MAIN, td.size())
            a = self.objs[id(obj)] = (SEC_MAIN, off)
            self.struct_into(SEC_MAIN, off, td, obj)
        return a

    def array(self, items: list, td: TypeDef):
        off = self.alloc(SEC_MAIN, td.size() * len(items))
        for i, it in enumerate(items):
            self.struct_into(SEC_MAIN, off + td.size() * i, td, it)
        return (SEC_MAIN, off)

    def member(self, sec: int, off: int, m: Member, v) -> None:
        b = self.secs[sec]
        t = m.type
        n = m.array_size or 1
        vals = v if m.array_size else [v]
        if t in SCALAR:
            struct.pack_into(f"<{n}{SCALAR[t][0]}", b, off, *vals)
        elif t == M_TRANSFORM:
            for i, tr in enumerate(vals):
                struct.pack_into("<I3f4f9f", b, off + 68 * i, tr.flags, *tr.position, *tr.orientation, *tr.scale_shear)
        elif t == M_INLINE:
            sz = m.defn.size()
            for i, it in enumerate(vals):
                self.struct_into(sec, off + sz * i, m.defn, it)
        elif t == M_STRING:
            for i, s in enumerate(vals):
                self.ptr(sec, off + PTR * i, self.string(s))
        elif t == M_REF:
            for i, o in enumerate(vals):
                self.ptr(sec, off + PTR * i, self.ref(o, m.defn))
        elif t == M_EMPTYREF:
            pass
        elif t == M_REFARRAY:
            struct.pack_into("<I", b, off, len(v))
            if v:
                self.ptr(sec, off + 4, self.array(v, m.defn))
        elif t == M_ARRAYREFS:
            struct.pack_into("<I", b, off, len(v))
            if v:
                poff = self.alloc(SEC_MAIN, PTR * len(v))
                self.ptr(sec, off + 4, (SEC_MAIN, poff))
                for i, o in enumerate(v):
                    self.ptr(SEC_MAIN, poff + PTR * i, self.ref(o, m.defn))
        elif t == M_VARIANT:
            if v is not None:
                self.ptr(sec, off, self.typedef(v.td))
                self.ptr(sec, off + PTR, self.ref(v.obj, v.td))
        elif t == M_VARARRAY:
            if v.td is not None:
                self.ptr(sec, off, self.typedef(v.td))
            struct.pack_into("<I", b, off + PTR, len(v.obj))
            if v.obj:
                self.ptr(sec, off + PTR + 4, self.array(v.obj, v.td))
        else:
            raise NotImplementedError(MEMBER_NAMES[t])

    def build(self, root: Obj) -> Gr2File:
        td = root.td
        root_off = self.alloc(SEC_MAIN, td.size())
        assert root_off == 0
        self.objs[id(root)] = (SEC_MAIN, 0)
        root_type = self.typedef(td)
        self.struct_into(SEC_MAIN, 0, td, root)
        g = Gr2File()
        if self.template is not None:
            t = self.template
            g.version, g.tag, g.extra_tags, g.string_crc, g.reserved = t.version, t.tag, list(t.extra_tags), t.string_crc, list(t.reserved)
        g.root_type, g.root_node = root_type, (SEC_MAIN, 0)
        for i in range(8):
            s = Section()
            s.data = bytes(self.secs[i])
            s.size = s.first16 = s.first8 = len(s.data)
            s.alignment = 32 if i in (1, 3) else 4
            s.relocations = sorted(self.relocs[i])
            g.sections.append(s)
        return g


def schema(td: TypeDef, indent=0, seen=None, name="") -> str:
    """Readable type schema (nested structs expanded once per file)."""
    seen = seen if seen is not None else set()
    pad = "  " * indent
    lines = []
    for m in td.members:
        a = f"[{m.array_size}]" if m.array_size else ""
        line = f"{pad}{m.name}: {MEMBER_NAMES[m.type]}{a}"
        if m.extra != (0, 0, 0):
            line += f" extra={m.extra}"
        if m.ignored:
            line += f" ignored={m.ignored:#x}"
        if m.defn is not None:
            if id(m.defn) in seen:
                line += " -> (struct above)"
            else:
                seen.add(id(m.defn))
                line += " ->"
                lines.append(line)
                lines.append(schema(m.defn, indent + 1, seen))
                continue
        lines.append(line)
    return chr(10).join(lines)


def collect_variant_types(o, out, seen=None):
    """All (struct type) of VariantReference members found in a tree, keyed by the first member names."""
    seen = seen if seen is not None else set()
    if id(o) in seen:
        return
    seen.add(id(o))
    if isinstance(o, Obj):
        for v in o.f.values():
            collect_variant_types(v, out, seen)
    elif isinstance(o, list):
        for v in o:
            collect_variant_types(v, out, seen)
    elif isinstance(o, Variant):
        if o.td is not None:
            out.setdefault(td_sig_short(o.td), o.td)
        collect_variant_types(o.obj, out, seen)


def td_sig_short(td):
    return ",".join(m.name for m in td.members[:6]) + f"/{len(td.members)}"


# ---------------------------------------------------------------------------------------------------------------------
# Comparison, round trip, command line
# ---------------------------------------------------------------------------------------------------------------------

def td_sig(td: TypeDef, seen=None) -> tuple:
    seen = seen if seen is not None else {}
    if id(td) in seen:
        return ("rec", seen[id(td)])
    seen[id(td)] = len(seen)
    return tuple((m.type, m.name, m.array_size, m.extra, m.ignored, td_sig(m.defn, seen) if m.defn else None) for m in td.members) + (td.end_ignored,)


def tree_equal(a, b, memo=None, path="") -> str | None:
    """None if both trees hold the same data (sharing is compared too), else a description of the first difference."""
    memo = memo if memo is not None else {}
    if isinstance(a, Obj):
        if not isinstance(b, Obj):
            return f"{path}: {type(a).__name__} vs {type(b).__name__}"
        key = (id(a), id(b))
        if key in memo:
            return None
        memo[key] = True
        if td_sig(a.td) != td_sig(b.td):
            return f"{path}: type differs"
        for k in a.f:
            r = tree_equal(a.f[k], b.f.get(k), memo, f"{path}.{k}")
            if r:
                return r
        return None
    if isinstance(a, Variant):
        if not isinstance(b, Variant) or td_sig(a.td) != td_sig(b.td):
            return f"{path}: variant type differs"
        return tree_equal(a.obj, b.obj, memo, path + "<v>")
    if isinstance(a, list):
        if not isinstance(b, list) or len(a) != len(b):
            return f"{path}: list length {len(a)} vs {len(b) if isinstance(b, list) else b!r}"
        for i, (x, y) in enumerate(zip(a, b)):
            r = tree_equal(x, y, memo, f"{path}[{i}]")
            if r:
                return r
        return None
    if isinstance(a, float):
        if isinstance(b, float) and (a == b or (a != a and b != b)):
            return None
        return f"{path}: {a!r} vs {b!r}"
    if a != b:
        return f"{path}: {a!r} vs {b!r}"
    return None


def roundtrip(data: bytes) -> dict:
    """Checks on one file: container decode, CRC, tree -> rewrite (uncompressed) -> re-read -> equal tree, and a pure
    container repack. Returns a dict of findings."""
    r = {}
    g = Gr2File.read(data)
    r["crc_ok"] = g.crc_ok
    r["compression"] = sorted({s.compression for s in g.sections})
    tree = parse_tree(g)
    # 1. container repack: same decompressed sections, relocations, marshalling blocks
    rp = g.write()
    g2 = Gr2File.read(rp)
    r["repack_ok"] = g2.crc_ok and all(
        a.data == b.data and sorted(a.relocations) == sorted(b.relocations) and a.marshalling == b.marshalling
        for a, b in zip(g.sections, g2.sections)) and g2.root_type == g.root_type and g2.root_node == g.root_node
    r["repack_size"] = (len(data), len(rp))
    # 2. object graph rewrite
    g3 = Writer(g).build(tree)
    wb = g3.write()
    g4 = Gr2File.read(wb)
    tree2 = parse_tree(g4)
    diff = tree_equal(tree, tree2)
    r["tree_equal"] = diff is None
    if diff:
        r["tree_diff"] = diff
    r["sections_equal"] = [a.data == b.data for a, b in zip(g.sections, g3.sections)]
    r["rewrite_size"] = len(wb)
    return r


def _summary(tree: Obj) -> str:
    parts = []
    for k, v in tree.f.items():
        if isinstance(v, list) and v:
            parts.append(f"{k}={len(v)}")
    return " ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info")
    p.add_argument("file")
    p = sub.add_parser("dump")
    p.add_argument("file")
    p.add_argument("--depth", type=int, default=3)
    p = sub.add_parser("types")
    p.add_argument("file")
    p = sub.add_parser("check")
    p.add_argument("paths", nargs="+")
    p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("repack")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--rewrite", action="store_true", help="re-serialise the object graph instead of copying sections")
    a = ap.parse_args()
    if a.cmd == "info":
        data = Path(a.file).read_bytes()
        g = Gr2File.read(data)
        print(f"{a.file}: {len(data)} bytes, version {g.version}, tag {g.tag:#x}, crc {'ok' if g.crc_ok else 'BAD'}, "
              f"root type {g.root_type}, root node {g.root_node}")
        for i, s in enumerate(g.sections):
            print(f"  section {i}: {COMPRESSION.get(s.compression)} {s.compressed_size} -> {s.size} bytes, align {s.alignment}, "
                  f"relocations {len(s.relocations)}, marshalling blocks {s.num_marshalling}")
        print("  tree:", _summary(parse_tree(g)))
    elif a.cmd == "dump":
        dump(parse_tree(Gr2File.read(Path(a.file).read_bytes())), a.depth)
    elif a.cmd == "types":
        g = Gr2File.read(Path(a.file).read_bytes())
        tree = parse_tree(g)
        print("root:" + chr(10) + schema(tree.td))
        found = {}
        collect_variant_types(tree, found)
        for k, td in found.items():
            print(f"{chr(10)}variant type {k}:{chr(10)}" + schema(td))
    elif a.cmd == "check":
        files = []
        for p_ in a.paths:
            pp = Path(p_)
            files += [pp] if pp.is_file() else sorted(f for e in ("model", "skeleton", "animations") for f in pp.rglob("*." + e))
        if a.limit:
            files = files[:a.limit]
        bad = 0
        for f in files:
            try:
                r = roundtrip(f.read_bytes())
            except Exception as e:  # noqa: BLE001 - report and go on
                print(f"FAIL {f}: {e!r}")
                bad += 1
                continue
            ok = r["crc_ok"] and r["repack_ok"] and r["tree_equal"]
            bad += not ok
            print(("ok   " if ok else "FAIL ") + f"{f.name} sections_equal={sum(r['sections_equal'])}/8 size {r['repack_size'][0]} -> {r['rewrite_size']}"
                  + ("" if ok else f" {r}"))
        print(f"{len(files) - bad}/{len(files)} ok")
        return 1 if bad else 0
    elif a.cmd == "repack":
        g = Gr2File.read(Path(a.src).read_bytes())
        if a.rewrite:
            g = Writer(g).build(parse_tree(g))
        Path(a.dst).write_bytes(g.write())
    return 0


if __name__ == "__main__":
    sys.exit(main())
