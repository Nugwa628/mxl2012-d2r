"""Disassemble, edit and reassemble the compiled code of D2R's HD particle files (PopcornFX CBVM bytecode, build 93847).

docs/hd-effects-authoring.md section 7. A `.particles` file (tools/hd_particles.py) keeps each script of an effect
(spawner, particle spawn, particle evolve) as a `CCompilerBlobCache` object compiled for PopcornFX's CPU virtual
machine ("CBVM", backend string `CPU/CPU_VM`). D2R.exe runs it with the interpreter of PopcornFX's
`CompilerBackend_CPU_VM` plugin; the decoder table at `0x2a05a30` (one function per opcode, called from the validator
`0x16d12a0` that prints "corrupt CBVM bytecode") gives every instruction's layout. All 41337 scripts of the 608 particle
files decode with it and this module writes them back byte for byte (`py -3 tools/hd_cbvm.py check <dir>`).

Blob object fields: 0 backend (string), 1 script kind (optional), 2 the program (u32 count + words), 4 descriptors of
the externals (5 u32 each), 5 the externals' names (string indices, -1 = none), 6 the called functions' names.
Program: 9 u32 header (h0 register count, h1 code bytes, h3 constant bytes = 32 * h5, h5 constant count, h6..h8 kept
as found), then the code, then the constants (each 32 bytes: the value repeated to fill 8 lanes), then zero padding.

Registers are u32: index (bits 0-20), class (21-22: 0 constant `c`, 2 uniform `u`, 3 per particle `s`), a flag (23,
written `!`), type (24-29, the VM's type table: float, float3, int, bool ...). Text form: `s1.float4`, `c3.float`.

  py -3 tools/hd_cbvm.py dis <file> [--obj N]          listing of every script (or one)
  py -3 tools/hd_cbvm.py dump <file> <dir>             one editable `obj_<N>.cbvm` per script
  py -3 tools/hd_cbvm.py build <file> <dir> <out>      reassemble the edited scripts into a new particle file
  py -3 tools/hd_cbvm.py tint <file> <out> <stream> R G B [A]   multiply a colour stream by a constant (see `tint`)
  py -3 tools/hd_cbvm.py check <file|dir> ...          decode -> text -> assemble round trip, byte for byte
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hd_particles as hp  # noqa: E402

BLOB = "CCompilerBlobCache"
NONE = 0xFFFFFFFF
# The VM's type table (D2R.exe 0x1d9e640, 32 bytes per entry: components, bytes, name): register bits 24-29.
TYPES = ["class", "void", "bool", "bool2", "bool3", "bool4", "ubyte", "ubyte2", "ubyte3", "ubyte4", "byte", "byte2",
         "byte3", "byte4", "uword", "uword2", "uword3", "uword4", "word", "word2", "word3", "word4", "uint", "uint2",
         "uint3", "uint4", "int", "int2", "int3", "int4", "u64", "i64", "float", "float2", "float3", "float4", "double"]
CLASS = "c?us"  # register class letters (bits 21-22)
# Math functions of opcodes 0x77/0x78 (byte 1): index -> (name, operands in); D2R.exe 0x1dd8d20 -> 0x1da4330.
MATH = ["sqrt", "rsqrt", "cbrt", "length", "normalize", "sin", "cos", "sincos", "tan", "asin", "acos", "atan",
        "atan2", "exp", "exp2", "log", "log2", "rcp", "abs", "sign", "ceil", "floor", "frac", "fracSign", "saturate",
        "step", "discretize", "min", "max", "dot", "cross", "fast_sqrt", "fast_rsqrt", "fast_cbrt", "fast_length",
        "fast_normalize", "fast_sin", "fast_cos", "fast_sincos", "fast_tan", "fast_asin", "fast_acos", "fast_atan",
        "fast_atan2", "fast_exp", "fast_exp2", "fast_log", "fast_log2", "fast_rcp", "all", "any", "isfinite", "isinf"]
BINARY = {"atan2", "step", "discretize", "min", "max", "dot", "cross", "fast_atan2"}
# Opcodes 0x69..0x7d (mnemonics as D2R.exe's CBVM debug table spells them where it has one).
OPS = {0x69: "ld", 0x6A: "st", 0x6B: "stz", 0x6C: "cvt", 0x6D: "vct", 0x6E: "swz", 0x6F: "dup", 0x70: "mop",
       0x71: "add", 0x72: "sub", 0x73: "mul", 0x74: "div", 0x75: "madd", 0x76: "idivmi", 0x77: "mfn1", 0x78: "mfn2",
       0x79: "mfn3", 0x7A: "sel", 0x7B: "call", 0x7C: "prlg", 0x7D: "eplg"}
CODE = {v: k for k, v in OPS.items()}
FIXED_REGS = {0x6C: 2, 0x6F: 2, 0x71: 3, 0x72: 3, 0x73: 3, 0x74: 3, 0x75: 4, 0x7A: 4, 0x76: 5}


# ---------------------------------------------------------------------- registers
def reg_text(r: int) -> str:
    if r == NONE:
        return "_"
    t = (r >> 24) & 0x3F
    s = f"{CLASS[(r >> 21) & 3]}{r & 0x1FFFFF}.{TYPES[t] if t < len(TYPES) else t}"
    if (r >> 23) & 1:
        s += "!"
    if r >> 30:
        s += f"^{r >> 30}"
    return s


REG_RE = re.compile(r"^([c?us])(\d+)\.(\w+)(!)?(?:\^(\d))?$")


def reg_parse(s: str) -> int:
    s = s.strip()
    if s == "_":
        return NONE
    m = REG_RE.match(s)
    if not m:
        raise ValueError(f"bad register {s!r}")
    t = TYPES.index(m.group(3)) if m.group(3) in TYPES else int(m.group(3))
    return (int(m.group(2)) | CLASS.index(m.group(1)) << 21 | (1 << 23 if m.group(4) else 0) | t << 24
            | int(m.group(5) or 0) << 30)


# ---------------------------------------------------------------------- instructions
@dataclass
class Ins:
    op: int
    regs: list[int] = field(default_factory=list)
    imm: list[int] = field(default_factory=list)   # op-specific small values (ext number, sub-op, swizzle bytes ...)
    args: list[tuple[int, int]] = field(default_factory=list)  # call arguments: (kind byte, register)

    @property
    def name(self) -> str:
        return OPS[self.op]


def math_size(fn: int) -> int:
    return 14 if fn < len(MATH) and MATH[fn] in BINARY else 10


def decode(code: bytes) -> list[Ins]:
    """The instructions of a script's code (ValueError on an opcode D2R would refuse)."""
    p, out = 0, []
    u = lambda o: struct.unpack_from("<I", code, o)[0]  # noqa: E731
    try:
        return _decode(code, u)
    except struct.error as e:
        raise ValueError(f"CBVM code ends inside an instruction ({e})") from None


def _decode(code: bytes, u) -> list[Ins]:
    p, out = 0, []
    while p < len(code):
        op = code[p]
        if op in (0x69, 0x6A):
            i, n = Ins(op, [u(p + 1)], [struct.unpack_from("<h", code, p + 5)[0]]), 7
        elif op == 0x6B:
            i, n = Ins(op, [], [struct.unpack_from("<h", code, p + 1)[0]]), 3
        elif op in FIXED_REGS:
            k = FIXED_REGS[op]
            i, n = Ins(op, [u(p + 1 + 4 * j) for j in range(k)]), 1 + 4 * k
        elif op == 0x6D:
            k = code[p + 1] + 1
            i, n = Ins(op, [u(p + 2 + 4 * j) for j in range(k + 1)]), 6 + 4 * k
        elif op == 0x6E:
            i, n = Ins(op, [u(p + 4), u(p + 8)], list(code[p + 1:p + 4])), 12
        elif op == 0x70:
            i, n = Ins(op, [u(p + 2 + 4 * j) for j in range(3)], [code[p + 1]]), 14
        elif op in (0x77, 0x78):
            n = math_size(code[p + 1])
            i = Ins(op, [u(p + 2 + 4 * j) for j in range((n - 2) // 4)], [code[p + 1]])
        elif op == 0x79:
            i, n = Ins(op, [u(p + 2 + 4 * j) for j in range(4)], [code[p + 1]]), 18
        elif op == 0x7B:
            na = code[p + 6]
            i = Ins(op, [u(p + 7)], [code[p + 1], struct.unpack_from("<h", code, p + 2)[0],
                                     struct.unpack_from("<H", code, p + 4)[0]],
                    [(code[p + 11 + 5 * j], u(p + 12 + 5 * j)) for j in range(na)])
            n = 11 + 5 * na
        elif op == 0x7C:
            k = code[p + 1]
            i, n = Ins(op, [], [u(p + 2 + 4 * j) for j in range(k)]), 2 + 4 * k
        elif op == 0x7D:
            i, n = Ins(op), 1
        else:
            raise ValueError(f"corrupt CBVM bytecode @{p:05X}: illegal instruction {op:02X}")
        if p + n > len(code):
            raise ValueError(f"CBVM instruction {op:02X} @{p:05X} runs past the code")
        out.append(i)
        p += n
    return out


def encode(ins: list[Ins]) -> bytes:
    out = bytearray()
    R = lambda rs: b"".join(struct.pack("<I", r) for r in rs)  # noqa: E731
    for i in ins:
        op = i.op
        if op in (0x69, 0x6A):
            out += bytes([op]) + R(i.regs) + struct.pack("<h", i.imm[0])
        elif op == 0x6B:
            out += bytes([op]) + struct.pack("<h", i.imm[0])
        elif op in FIXED_REGS:
            if len(i.regs) != FIXED_REGS[op]:
                raise ValueError(f"{i.name} takes {FIXED_REGS[op]} registers")
            out += bytes([op]) + R(i.regs)
        elif op == 0x6D:
            if not 2 <= len(i.regs) <= 5:
                raise ValueError("vct takes a destination and 1-4 components")
            out += bytes([op, len(i.regs) - 2]) + R(i.regs)
        elif op == 0x6E:
            out += bytes([op] + i.imm) + R(i.regs)
        elif op in (0x70, 0x79):
            out += bytes([op, i.imm[0]]) + R(i.regs)
        elif op in (0x77, 0x78):
            if 2 + 4 * len(i.regs) != math_size(i.imm[0]):
                raise ValueError(f"{MATH[i.imm[0]]} takes {(math_size(i.imm[0]) - 2) // 4} registers")
            out += bytes([op, i.imm[0]]) + R(i.regs)
        elif op == 0x7B:
            out += bytes([op, i.imm[0]]) + struct.pack("<hHB", i.imm[1], i.imm[2], len(i.args)) + R(i.regs)
            out += b"".join(bytes([k]) + struct.pack("<I", r) for k, r in i.args)
        elif op == 0x7C:
            out += bytes([op, len(i.imm)]) + R(i.imm)
        elif op == 0x7D:
            out += bytes([op])
    return bytes(out)


# ---------------------------------------------------------------------- scripts
@dataclass
class Script:
    """One CCompilerBlobCache object, decoded."""
    obj: int                      # object number (0-based)
    order: list[int]              # field ids in file order
    backend: str
    kind: int | None
    head: list[int]               # the 9 header words (h1, h3, h5 are recomputed on writing)
    code: list[Ins]
    consts: list[bytes]           # 32 bytes each
    pad: bytes                    # bytes after the constants (alignment)
    ext_desc: list[list[int]]     # per external: its descriptor words
    ext_names: list[str | None]
    fn_names: list[str] | None

    def ext(self, name: str) -> int:
        return self.ext_names.index(name)

    def add_const(self, values, kind: str = "f") -> int:
        """A new constant (1-8 values, repeated to fill 32 bytes); returns its index."""
        vals = list(values)
        lanes = (vals * 8)[:8]
        self.consts.append(struct.pack("<8f" if kind == "f" else "<8i", *lanes))
        return len(self.consts) - 1


def _fields(pf: hp.ParticleFile, i: int) -> list[tuple[int, object]]:
    _c, off, size = pf.objects[i]
    b = pf.raw
    n = struct.unpack_from("<H", b, off + 5)[0]
    q, out = off + 7, []
    for _ in range(n):
        fid = struct.unpack_from("<H", b, q)[0]
        q += 2
        if fid in (2, 4, 5, 6):
            cnt = struct.unpack_from("<I", b, q)[0]
            out.append((fid, bytes(b[q + 4:q + 4 + 4 * cnt])))
            q += 4 + 4 * cnt
        elif fid in (0, 1):
            out.append((fid, struct.unpack_from("<I", b, q)[0]))
            q += 4
        else:
            raise ValueError(f"object {i}: unknown {BLOB} field {fid}")
    if q != off + size:
        raise ValueError(f"object {i}: fields end at {q:#x}, object at {off + size:#x}")
    return out


def scripts(pf: hp.ParticleFile) -> list[Script]:
    out = []
    for i in range(len(pf.objects)):
        if pf.cls(i) != BLOB:
            continue
        f = dict(_fields(pf, i))
        prog = f[2]
        head = list(struct.unpack_from("<9I", prog, 0))
        clen, cbytes = head[1], head[3]
        code = prog[36:36 + clen]
        cst = prog[36 + clen:36 + clen + cbytes]
        if cbytes != 32 * head[5] or len(cst) != cbytes:
            raise ValueError(f"object {i}: constants {cbytes} bytes for {head[5]}")
        names = [None if s == NONE else pf.strings[s] for s in struct.unpack_from(f"<{len(f[5]) // 4}I", f[5])]
        words = struct.unpack_from(f"<{len(f[4]) // 4}I", f[4])
        k = len(words) // len(names) if names else 0
        if names and k * len(names) != len(words):
            raise ValueError(f"object {i}: {len(words)} descriptor words for {len(names)} externals")
        fns = None
        if 6 in f:
            fns = [pf.strings[s] for s in struct.unpack_from(f"<{len(f[6]) // 4}I", f[6])]
        out.append(Script(i, [fid for fid, _ in _fields(pf, i)], pf.strings[f[0]], f.get(1), head, decode(code),
                          [cst[32 * j:32 * j + 32] for j in range(head[5])], prog[36 + clen + cbytes:],
                          [list(words[j * k:(j + 1) * k]) for j in range(len(names))], names, fns))
    return out


def payload(pf: hp.ParticleFile, s: Script) -> bytes:
    """The object's bytes (from 0x20) for a script; strings it names are added to `pf`'s table."""
    code = encode(s.code)
    head = list(s.head)
    head[1], head[3], head[5] = len(code), 32 * len(s.consts), len(s.consts)
    prog = struct.pack("<9I", *head) + code + b"".join(s.consts)
    pad = s.pad if (len(prog) + len(s.pad)) % 4 == 0 else b"\0" * (-len(prog) % 4)
    prog += pad
    sid = lambda x: NONE if x is None else pf.add_string(x)  # noqa: E731
    vals = {0: struct.pack("<I", pf.add_string(s.backend)),
            1: struct.pack("<I", s.kind or 0),
            2: struct.pack("<I", len(prog) // 4) + prog,
            4: struct.pack("<I", sum(map(len, s.ext_desc))) + b"".join(struct.pack(f"<{len(d)}I", *d) for d in s.ext_desc),
            5: struct.pack("<I", len(s.ext_names)) + b"".join(struct.pack("<I", sid(n)) for n in s.ext_names),
            6: struct.pack("<I", len(s.fn_names or [])) + b"".join(struct.pack("<I", sid(n)) for n in s.fn_names or [])}
    order = [f for f in s.order if f != 6 or s.fn_names is not None]
    if s.fn_names is not None and 6 not in order:
        order.append(6)
    cls = struct.unpack_from("<I", pf.raw, pf.objects[s.obj][1] + 1)[0]
    return b"\x20" + struct.pack("<IH", cls, len(order)) + b"".join(struct.pack("<H", f) + vals[f] for f in order)


def rebuild(pf: hp.ParticleFile, new: dict[int, bytes]) -> bytes:
    """The particle file with some objects' payloads replaced ({object number: bytes from 0x20}); object sizes may
    change (objects refer to each other by number, so only the header's string-table offset moves)."""
    hdr_len = 0x1C + 8 * struct.unpack_from("<I", pf.raw, 16)[0]
    body = bytearray()
    for i, (_c, off, size) in enumerate(pf.objects):
        p = new.get(i, bytes(pf.raw[off:off + size]))
        body += struct.pack("<I", len(p)) + p
    head = bytearray(pf.raw[:hdr_len])
    struct.pack_into("<I", head, 20, hdr_len + len(body))
    tail = hp.ParticleFile.data(pf)[pf.str_at:]   # the (possibly grown) string table
    return bytes(head + body + tail)


def write_scripts(pf: hp.ParticleFile, ss: list[Script]) -> bytes:
    return rebuild(pf, {s.obj: payload(pf, s) for s in ss})


# ---------------------------------------------------------------------- text form
def _const_text(c: bytes) -> str:
    w = struct.unpack("<8I", c)
    if all(x == 0 or 0x00800000 <= (x & 0x7FFFFFFF) < 0x7F800000 for x in w):
        fl = struct.unpack("<8f", c)
        if all(struct.pack("<f", float(repr(v))) == struct.pack("<f", v) for v in fl):
            return "f " + " ".join(repr(v) for v in fl)
    if all(x < 0x00800000 or x >= 0xFF800000 for x in w):
        return "i " + " ".join(str(v) for v in struct.unpack("<8i", c))
    return "x " + c.hex()


def _const_parse(s: str) -> bytes:
    kind, *vals = s.split()
    if kind == "x":
        b = bytes.fromhex(vals[0])
    elif kind == "f":
        b = struct.pack("<8f", *((list(map(float, vals)) * 8)[:8]))
    elif kind == "i":
        b = struct.pack("<8i", *((list(map(int, vals)) * 8)[:8]))
    else:
        raise ValueError(f"bad constant {s!r}")
    if len(b) != 32:
        raise ValueError(f"a constant is 32 bytes: {s!r}")
    return b


def ins_text(i: Ins, s: Script | None = None) -> str:
    rs = [reg_text(r) for r in i.regs]
    note = ""
    if i.op in (0x69, 0x6A, 0x6B):
        a = f"{i.name} " + (rs[0] + ", " if rs else "") + f"@{i.imm[0]}"
        if s and 0 <= i.imm[0] < len(s.ext_names):
            note = s.ext_names[i.imm[0]] or "-"
    elif i.op == 0x6E:
        a = "swz.{:02x}.{:02x}.{:02x} ".format(*i.imm) + ", ".join(rs)
    elif i.op == 0x70:
        a = f"mop.{i.imm[0]} " + ", ".join(rs)
    elif i.op in (0x77, 0x78):
        fn = i.imm[0]
        a = f"{i.name}.{MATH[fn] if fn < len(MATH) else fn} " + ", ".join(rs)
    elif i.op == 0x79:
        a = f"mfn3.{i.imm[0]} " + ", ".join(rs)
    elif i.op == 0x7B:
        a = f"call.{i.imm[0]:x}.{i.imm[1]} #{i.imm[2]} {rs[0]} <- " + ", ".join(f"{k:x}:{reg_text(r)}" for k, r in i.args)
        if s and s.fn_names and i.imm[2] < len(s.fn_names):
            note = s.fn_names[i.imm[2]]
    elif i.op == 0x7C:
        a = "prlg" + "".join(f" {v:#x}" for v in i.imm)
    else:
        a = f"{i.name} " + ", ".join(rs) if rs else i.name
    if s:
        cs = [r & 0x1FFFFF for r in i.regs + [r for _k, r in i.args] if r != NONE and not (r >> 21) & 3]
        vals = [f"c{c}={_const_text(s.consts[c])[2:].split()[0]}" for c in cs if c < len(s.consts)]
        note = "  ".join(x for x in [note] + vals if x)
    return a + (f"    ; {note}" if note else "")


def ins_parse(line: str) -> Ins:
    line = line.split(";")[0].strip()
    mn, _, rest = line.partition(" ")
    base, *sub = mn.split(".")
    if base not in CODE:
        raise ValueError(f"unknown instruction {mn!r}")
    op = CODE[base]
    rest = rest.strip()
    if op in (0x69, 0x6A, 0x6B):
        parts = [x.strip() for x in rest.split(",")]
        ext = int(parts[-1].lstrip("@"))
        return Ins(op, [reg_parse(p) for p in parts[:-1]], [ext])
    if op == 0x7C:
        return Ins(op, [], [int(x, 0) for x in rest.split()])
    if op == 0x7D:
        return Ins(op)
    if op == 0x7B:
        m = re.match(r"#(\d+)\s+(\S+)\s*<-\s*(.*)$", rest)
        if not m or len(sub) != 2:
            raise ValueError(f"bad call {line!r}")
        args = []
        for a in filter(None, (x.strip() for x in m.group(3).split(","))):
            k, _, r = a.partition(":")
            args.append((int(k, 16), reg_parse(r)))
        return Ins(op, [reg_parse(m.group(2))], [int(sub[0], 16), int(sub[1]), int(m.group(1))], args)
    regs = [reg_parse(x) for x in rest.split(",")] if rest else []
    if op == 0x6E:
        return Ins(op, regs, [int(x, 16) for x in sub])
    if op in (0x70, 0x79):
        return Ins(op, regs, [int(sub[0])])
    if op in (0x77, 0x78):
        return Ins(op, regs, [MATH.index(sub[0]) if sub[0] in MATH else int(sub[0])])
    return Ins(op, regs)


def script_text(s: Script) -> str:
    h = s.head
    lines = [f"; D2R CBVM script (tools/hd_cbvm.py): object {s.obj + 1}",
             f".order {' '.join(map(str, s.order))}",
             f".backend {s.backend}"]
    if s.kind is not None:
        lines.append(f".kind {s.kind}")
    lines.append(f".head {h[0]} {h[2]} {h[4]} {h[6]} {h[7]} {h[8]}")
    for k, (n, d) in enumerate(zip(s.ext_names, s.ext_desc)):
        lines.append(f".ext {k} {' '.join(map(str, d))} {'-' if n is None else '=' + n}")
    if s.fn_names is not None:
        lines.append(".fns" if not s.fn_names else "")
        lines += [f".fn {k} {n}" for k, n in enumerate(s.fn_names)]   # the name runs to the end of the line
    for k, c in enumerate(s.consts):
        lines.append(f".const {k} {_const_text(c)}")
    if s.pad.strip(b"\0"):
        lines.append(f".pad {s.pad.hex()}")
    lines.append("")
    lines += [ins_text(i, s) for i in s.code]
    return "\n".join(x for x in lines if x is not None) + "\n"


def script_parse(text: str, obj: int) -> Script:
    s = Script(obj, [], "", None, [0] * 9, [], [], b"", [], [], None)
    for raw in text.splitlines():
        line = raw.strip() if raw.lstrip().startswith(".") else raw.split(";")[0].strip()
        if not line:
            continue
        if line.startswith("."):
            key, _, rest = line.partition(" ")
            v = rest.split()
            if key == ".order":
                s.order = list(map(int, v))
            elif key == ".backend":
                s.backend = rest.strip()
            elif key == ".kind":
                s.kind = int(v[0])
            elif key == ".head":
                h = list(map(int, v))
                s.head = [h[0], 0, h[1], 0, h[2], 0, h[3], h[4], h[5]]
            elif key == ".ext":   # .ext <k> <descriptor words> =<name> (the name runs to the end of the line) or -
                words, eq, name = rest.partition(" =")
                if not eq:
                    words, name = rest.rsplit(" ", 1)[0], None
                s.ext_names.append(name)
                s.ext_desc.append(list(map(int, words.split()[1:])))
            elif key == ".fns":
                s.fn_names = []
            elif key == ".fn":
                s.fn_names = (s.fn_names or []) + [rest.split(" ", 1)[1]]
            elif key == ".const":
                if int(v[0]) != len(s.consts):
                    raise ValueError(f"constants out of order at {line!r}")
                s.consts.append(_const_parse(" ".join(v[1:])))
            elif key == ".pad":
                s.pad = bytes.fromhex(v[0])
            else:
                raise ValueError(f"unknown directive {key}")
        else:
            s.code.append(ins_parse(line))
    if 6 in s.order and s.fn_names is None:
        s.fn_names = []
    return s


# ---------------------------------------------------------------------- recipes
def tint(data: bytes, stream: str, rgba) -> tuple[bytes, int]:
    """Every script that stores the per-particle float4 stream `stream` (a colour: the external of that name) gets
    `mul R, R, c<new>` before the store, with a new constant `rgba`: the colour the effect computes, tinted. Returns the
    new file and how many stores were tinted. An effect that computes its colour as a grey level (D2R's tower mist:
    one float broadcast to all four channels) becomes that colour."""
    pf = hp.ParticleFile(data)
    ss, n = scripts(pf), 0
    rgba = list(rgba) + [1.0] * (4 - len(rgba))
    changed = []
    for s in ss:
        if stream not in s.ext_names:
            continue
        k = s.ext(stream)
        out, c = [], None
        for i in s.code:
            if i.op == 0x6A and i.imm[0] == k:
                r = i.regs[0]
                if TYPES[(r >> 24) & 0x3F] != "float4":  # stream names are per layer: another layer's `11` may be a float
                    out.append(i)
                    continue
                if c is None:
                    c = s.add_const(rgba)
                out.append(Ins(0x73, [r, r, TYPES.index("float4") << 24 | c]))
                n += 1
            out.append(i)
        if c is not None:
            s.code = out
            changed.append(s)
    if not n:
        raise ValueError(f"no script stores a float4 stream named {stream!r}")
    return write_scripts(pf, changed), n


def colour_streams(data: bytes) -> list[str]:
    """Float4 per-particle streams the scripts write from one broadcast float (`swz` of a float into a float4 just
    before the store): grey-level colours, the candidates for `tint`."""
    pf = hp.ParticleFile(data)
    out = []
    for s in scripts(pf):
        for a, b in zip(s.code, s.code[1:]):
            if a.op == 0x6E and b.op == 0x6A and b.regs[0] == a.regs[0] and TYPES[(a.regs[1] >> 24) & 0x3F] == "float":
                n = s.ext_names[b.imm[0]]
                if n not in out:
                    out.append(n)
    return out


# ---------------------------------------------------------------------- CLI
def roundtrip(data: bytes) -> tuple[int, bool]:
    """(scripts, identical): every script to text and back, the file rebuilt."""
    pf = hp.ParticleFile(data)
    ss = [script_parse(script_text(s), s.obj) for s in scripts(pf)]
    return len(ss), write_scripts(hp.ParticleFile(data), ss) == data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("dis")
    a.add_argument("file")
    a.add_argument("--obj", type=int, help="object number (1-based, as the listing prints)")
    a = sub.add_parser("dump")
    a.add_argument("file")
    a.add_argument("dir")
    a = sub.add_parser("build")
    a.add_argument("file")
    a.add_argument("dir")
    a.add_argument("out")
    a = sub.add_parser("tint")
    a.add_argument("file")
    a.add_argument("out")
    a.add_argument("stream")
    a.add_argument("rgba", type=float, nargs="+")
    a = sub.add_parser("streams")
    a.add_argument("file")
    a = sub.add_parser("check")
    a.add_argument("paths", nargs="+")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        files = [f for p in map(Path, args.paths) for f in (sorted(p.rglob("*.particles")) if p.is_dir() else [p])]
        total = bad = empty = 0
        for f in files:
            data = f.read_bytes()
            if not data:
                empty += 1
                continue
            n, ok = roundtrip(data)
            total += n
            if not ok:
                bad += 1
                print(f"DIFFERS {f}")
        print(f"{len(files)} files ({empty} empty), {total} scripts, {bad} files differ")
        return 1 if bad else 0
    data = Path(args.file).read_bytes()
    if args.cmd == "dis":
        for s in scripts(hp.ParticleFile(data)):
            if args.obj is None or s.obj + 1 == args.obj:
                print(script_text(s))
    elif args.cmd == "dump":
        d = Path(args.dir)
        d.mkdir(parents=True, exist_ok=True)
        for s in scripts(hp.ParticleFile(data)):
            (d / f"obj_{s.obj + 1}.cbvm").write_text(script_text(s), encoding="utf-8")
    elif args.cmd == "build":
        pf = hp.ParticleFile(data)
        ss = [script_parse(f.read_text(encoding="utf-8"), int(f.stem.split("_")[1]) - 1)
              for f in sorted(Path(args.dir).glob("obj_*.cbvm"))]
        Path(args.out).write_bytes(write_scripts(pf, ss))
    elif args.cmd == "tint":
        out, n = tint(data, args.stream, args.rgba)
        Path(args.out).write_bytes(out)
        print(f"{n} stores of {args.stream} tinted")
    elif args.cmd == "streams":
        print("\n".join(colour_streams(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
