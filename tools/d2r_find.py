"""Query tool for the D2R memory dump (file offset == RVA, base 0x140000000, x64).

  py -3 tools/d2r_find.py str  "Quests" [-i]       # ASCII + UTF-16 string search (substring), prints RVA + text
  py -3 tools/d2r_find.py xref 0x1d3a1c0 [...]     # RIP-relative references to data RVAs (code), with owning function
  py -3 tools/d2r_find.py sxref "BC_ASSERT" [-i]   # string search, then xrefs of every ASCII hit
  py -3 tools/d2r_find.py func 0x529090            # function bounds from .pdata (begin, end)
  py -3 tools/d2r_find.py dis  0x529090 [--max N] [--func]   # disassemble; --func = to the end of the function
  py -3 tools/d2r_find.py callers 0x5da800         # direct E8/E9 callers of a function
  py -3 tools/d2r_find.py around 0x526d55 [before] [after]   # disassemble around an address (resyncs from the function start)
  py -3 tools/d2r_find.py qinit 6|all               # quest init function + event handler slots (descriptor table at 0x239c5c0)
  py -3 tools/d2r_find.py bytes 0x529090 [16]      # raw bytes (entry bytes)
  py -3 tools/d2r_find.py qword 0x238ea00 [n]      # read pointers (shown as RVA when inside the image)
  py -3 tools/d2r_find.py ptrs 0x52aa00            # find 8-byte pointers to an RVA (function tables, vtables)

Dump path: env D2R_DUMP or the default below. dis annotates RIP-relative strings and call targets.
"""
import argparse
import bisect
import os
import re
import struct

import numpy as np

DUMP = os.environ.get("D2R_DUMP", os.path.join(os.path.expanduser("~"), "ghidra", "D2RLoader_6ab3782c_dump.exe"))
BASE = 0x140000000
TEXT = (0x1000, 0x1000 + 0x1caf000)
PDATA = 0x3bff000

_buf = None
_funcs = None
_begins = None


def buf():
    global _buf
    if _buf is None:
        _buf = np.memmap(DUMP, dtype=np.uint8, mode="r")
    return _buf


def raw(rva, n):
    return bytes(buf()[rva:rva + n])


def funcs():
    """Sorted (begin, end) RVAs from the .pdata RUNTIME_FUNCTION table."""
    global _funcs, _begins
    if _funcs is None:
        data = raw(PDATA, 0x400000 * 3 // 3 * 3)
        n = len(data) // 12
        a = np.frombuffer(data[:n * 12], dtype="<u4").reshape(n, 3)
        ok = (a[:, 0] >= 0x1000) & (a[:, 0] < a[:, 1]) & (a[:, 1] < 0x2000000)
        cnt = n if ok.all() else int(np.argmin(ok))
        a = a[:cnt]
        _funcs = sorted(set((int(x), int(y)) for x, y, _ in a))
        _begins = [x[0] for x in _funcs]
    return _funcs


def func_of(rva):
    f = funcs()
    i = bisect.bisect_right(_begins, rva) - 1
    if i >= 0 and f[i][0] <= rva < f[i][1]:
        return f[i]
    return None


def read_cstr(rva, maxn=100):
    if not 0 < rva < len(buf()) - maxn:
        return None
    b = raw(rva, maxn)
    e = b.find(b"\0")
    if e < 3:
        return None
    b = b[:e]
    if all(32 <= c < 127 for c in b):
        return b.decode()
    return None


def find_strings(sub, ignore_case=False):
    """[(start rva, kind 'a'|'w', full text)] for ASCII / UTF-16 occurrences of sub."""
    b = buf()
    hits = []
    for kind, pat in (("a", sub.encode()), ("w", sub.encode("utf-16-le"))):
        p = pat.lower() if ignore_case else pat
        step = 1 << 24
        for off in range(0, len(b), step):
            chunk = bytes(b[off:off + step + len(pat)])
            hay = chunk.lower() if ignore_case else chunk
            i = hay.find(p)
            while i >= 0:
                if i < step:
                    hits.append((off + i, kind))
                i = hay.find(p, i + 1)
    res = []
    for rva, kind in sorted(hits):
        s = rva
        if kind == "a":
            while s > 0 and (32 <= b[s - 1] < 127 or b[s - 1] == 9) and rva - s < 200:
                s -= 1
            e = rva
            while e < len(b) and (32 <= b[e] < 127 or b[e] == 9) and e - rva < 300:
                e += 1
            res.append((s, kind, bytes(b[s:e]).decode()))
        else:
            while s > 1 and b[s - 1] == 0 and 32 <= b[s - 2] < 127 and rva - s < 400:
                s -= 2
            e = rva
            while e + 1 < len(b) and b[e + 1] == 0 and 32 <= b[e] < 127 and e - rva < 600:
                e += 2
            res.append((s, kind, bytes(b[s:e]).decode("utf-16-le")))
    return res


def _text_disp():
    lo, hi = TEXT
    seg = np.asarray(buf()[lo - 1:hi + 8]).astype(np.uint32)
    n = hi - lo
    d = (seg[1:n + 1] | (seg[2:n + 2] << 8) | (seg[3:n + 3] << 16) | (seg[4:n + 4] << 24)).astype(np.int64)
    d = np.where(d >= 1 << 31, d - (1 << 32), d)
    modrm = seg[:n]
    return lo, hi, d, modrm


def xrefs(targets):
    """RIP-relative references (modrm mod=00 rm=101) in .text. {target: [(disp position, imm bytes after disp)]}"""
    lo, hi, d, modrm = _text_disp()
    ok = (modrm & 0xC7) == 0x05
    pos = np.arange(lo, hi, dtype=np.int64)
    res = {t: [] for t in targets}
    for extra in (0, 1, 2, 4):
        tgt = pos + 4 + extra + d
        for t in targets:
            for p in pos[ok & (tgt == t)]:
                res[t].append((int(p), extra))
    for t in res:
        res[t].sort()
    return res


def callers(target):
    lo, hi = TEXT
    seg = np.asarray(buf()[lo:hi + 8])
    s = seg.astype(np.uint32)
    res = []
    for op in (0xE8, 0xE9):
        idx = np.nonzero(seg[:hi - lo] == op)[0]
        d = (s[idx + 1] | (s[idx + 2] << 8) | (s[idx + 3] << 16) | (s[idx + 4] << 24)).astype(np.int64)
        d = np.where(d >= 1 << 31, d - (1 << 32), d)
        t = idx + lo + 5 + d
        for p in idx[t == target]:
            res.append((int(p) + lo, "call" if op == 0xE8 else "jmp"))
    return sorted(res)


def ann(ins):
    notes = []
    m = re.search(r"rip ([+-]) (0x[0-9a-f]+)", ins.op_str)
    if m:
        d = int(m.group(2), 16)
        t = ins.address + ins.size + (d if m.group(1) == "+" else -d)
        s = read_cstr(t)
        notes.append(f'data {t:#x} "{s}"' if s else f"data {t:#x}")
    if ins.mnemonic in ("call", "jmp") and ins.op_str.startswith("0x"):
        t = int(ins.op_str, 16)
        f = func_of(t)
        notes.append(f"{ins.mnemonic} {t:#x}" + ("" if f and f[0] == t else " (mid)" if f else " (no func)"))
    return "  ; " + ", ".join(notes) if notes else ""


def dis(rva, n=0x200, whole=False):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    if whole:
        f = func_of(rva)
        if f:
            n = f[1] - rva
    int3run = 0
    for ins in md.disasm(raw(rva, n), rva):
        int3run = int3run + 1 if ins.mnemonic == "int3" else 0
        if whole and int3run >= 3:
            break
        print(f"{ins.address:#09x}  {ins.bytes.hex():<24} {ins.mnemonic} {ins.op_str}{ann(ins)}")


QUEST_CB = 0x270  # D2R quest object: callback for event N at +0x270 + 8*N (1.13c: +0xa0 + 4*N)


QUEST_TABLE = 0x239c5c0  # 36 descriptors of 0x20 bytes: +0 init fn VA, +8 u32 act (0-4), +0x14 u32 ordinal, +0x18 u32 quest id
QUEST_COUNT = 36


def quest_table():
    """[(quest id, act, init function RVA)] from the descriptor table."""
    out = []
    for i in range(QUEST_COUNT):
        init, w1, _w2, w3 = struct.unpack("<QQQQ", raw(QUEST_TABLE + 0x20 * i, 32))
        out.append((w3 & 0xFFFFFFFF, w1 & 0xFFFFFFFF, init - BASE))
    return out


def quest_init(arg):
    """arg = quest id (e.g. 6) or 'all': find the quest's init function in the descriptor table and print which handler
    it stores into quest+0x270+8*event. Quest id N of act 1 is file a1qN; act 2: a2q(N-8); act 3: a3q(N-16);
    act 4: a4q(N-24); act 5: a5q(N-34). Ids 29-33 and 41 are extra objects with no handlers of their own."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for qid, act, init in quest_table():
        if arg != "all" and qid != int(arg, 0):
            continue
        f = func_of(init)
        end = f[1] if f and f[0] == init else init + 0x400  # leaf inits have no .pdata entry of their own
        print(f"quest {qid} (act {act + 1}) init {init:#x}  entry bytes {raw(init, 16).hex(' ')}")
        ins = []
        for x in md.disasm(raw(init, end - init), init):
            ins.append(x)
            if x.mnemonic == "ret":
                break
        for i, x in enumerate(ins):
            m = re.search(r"rip ([+-]) (0x[0-9a-f]+)", x.op_str)
            if x.mnemonic == "lea" and m and i + 1 < len(ins):
                tgt = x.address + x.size + (int(m.group(2), 16) if m.group(1) == "+" else -int(m.group(2), 16))
                n = re.search(r"qword ptr \[r\w+ \+ (0x[0-9a-f]+)\], r", ins[i + 1].op_str)
                if ins[i + 1].mnemonic == "mov" and n:
                    off = int(n.group(1), 16)
                    if QUEST_CB <= off < QUEST_CB + 8 * 20:
                        print(f"    event {(off - QUEST_CB) // 8:2d} (quest+{off:#x}) = {tgt:#x}  {raw(tgt, 16).hex(' ')}")


def around(rva, before=0x60, after=0x80):
    """Disassemble around an address that may be mid-instruction: start from the owning function's
    begin when known (linear sweep, resyncs on the real instruction stream), else try starts below rva."""
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    f = func_of(rva)
    starts = [f[0]] if f else range(rva - before, rva - before + 16)
    for s in starts:
        ins = []
        cur, end = s, rva + after
        while cur < end:
            chunk = list(md.disasm(raw(cur, end - cur), cur))
            ins += chunk
            if not chunk:
                cur += 1
            else:
                cur = chunk[-1].address + chunk[-1].size
                if cur < end:
                    cur += 1  # undecodable byte: skip
        if any(i.address == rva for i in ins):
            for i in ins:
                if i.address >= rva - before:
                    print(f"{i.address:#09x}  {i.bytes.hex():<24} {i.mnemonic} {i.op_str}{ann(i)}")
            return
    print("could not sync")


def main():
    ap =argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd")
    ap.add_argument("args", nargs="*")
    ap.add_argument("--max", type=lambda s: int(s, 0), default=0x200)
    ap.add_argument("--func", action="store_true")
    ap.add_argument("-i", action="store_true", help="ignore case (str, sxref)")
    a = ap.parse_args()
    c = a.cmd

    def iv(s):
        return int(s, 0)

    if c == "str":
        for rva, k, t in find_strings(a.args[0], a.i):
            print(f"{rva:#x} {k} {t!r}")
    elif c in ("xref", "sxref"):
        if c == "sxref":
            hits = [(r, t) for r, k, t in find_strings(a.args[0], a.i) if k == "a"]
            targets = [r for r, _ in hits]
            names = dict(hits)
        else:
            targets = [iv(x) for x in a.args]
            names = {}
        xr = xrefs(targets)
        for t in targets:
            print(f"== {t:#x} {names.get(t, '')!r}")
            for p, extra in xr[t]:
                f = func_of(p)
                where = f"func {f[0]:#x}-{f[1]:#x}" if f else "no func"
                print(f"   insn ~{p - 3:#x} (disp at {p:#x})  {where}")
    elif c == "func":
        f = func_of(iv(a.args[0]))
        print(f"{f[0]:#x} {f[1]:#x} size {f[1] - f[0]:#x}" if f else "none")
    elif c == "dis":
        dis(iv(a.args[0]), a.max, a.func)
    elif c == "callers":
        for p, k in callers(iv(a.args[0])):
            f = func_of(p)
            print(f"{p:#x} {k}  in {f[0]:#x}" if f else f"{p:#x} {k}")
    elif c == "qinit":
        quest_init(a.args[0])
    elif c == "around":
        around(iv(a.args[0]), iv(a.args[1]) if len(a.args) > 1 else 0x60, iv(a.args[2]) if len(a.args) > 2 else 0x80)
    elif c == "ptrs":
        pat = struct.pack("<Q", BASE + iv(a.args[0]))
        b = bytes(buf())
        i = b.find(pat)
        while i >= 0:
            print(f"{i:#x}")
            i = b.find(pat, i + 1)
    elif c == "bytes":
        n = iv(a.args[1]) if len(a.args) > 1 else 16
        print(raw(iv(a.args[0]), n).hex(" "))
    elif c == "qword":
        n = iv(a.args[1]) if len(a.args) > 1 else 1
        for i in range(n):
            v = struct.unpack("<Q", raw(iv(a.args[0]) + 8 * i, 8))[0]
            print(f"{iv(a.args[0]) + 8 * i:#x}: {v:#x}" + (f"  (rva {v - BASE:#x})" if BASE <= v < BASE + 0x6000000 else ""))
    else:
        ap.error("unknown command")


if __name__ == "__main__":
    main()
