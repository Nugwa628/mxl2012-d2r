"""Small extras for the D2R memory dump, on top of d2r_find.py (same dump, RVAs).

  py -3 tools/d2r_scan.py eb 0x4404f0 0x441300 ...        # first 16 entry bytes of each function
  py -3 tools/d2r_scan.py ctx 0x541125 [before] [after]   # instructions before/after a call site (resyncs from the .pdata chunk start)
  py -3 tools/d2r_scan.py pat "c5 90 c6 6a" [min_hits]    # functions (pdata chunks) containing a byte pattern (e.g. an imm32 constant)
  py -3 tools/d2r_scan.py pat2 "e9 a2 8b 2e" "ab aa aa 2a" "67 66 66 66"   # chunks that contain ALL the given patterns

Examples used in docs/d2r-addresses.md: pat2 with the x%11 / x%12 / x%20 magic multipliers finds the game frame
function 0x406550; pat "c5 90 c6 6a" lists every user of the 0x6ac690c5 LCG multiplier.
"""
import re
import sys
from collections import defaultdict

import capstone
import numpy as np

import d2r_find as d


def _text():
    lo, hi = d.TEXT
    return lo, bytes(np.asarray(d.buf()[lo:hi]))


def cmd_eb(args):
    for a in args:
        v = int(a, 16)
        print(a, " ".join("%02x" % x for x in bytes(d.raw(v, 16))))


def cmd_ctx(args):
    a = int(args[0], 16)
    before = int(args[1]) if len(args) > 1 else 14
    after = int(args[2]) if len(args) > 2 else 2
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    f = d.func_of(a)
    s = f[0] if f else a - 200
    ins = list(md.disasm(d.raw(s, a + 64 - s), s))
    addrs = [x.address for x in ins]
    if a not in addrs:
        print("could not sync")
        return
    i = addrs.index(a)
    for x in ins[max(0, i - before):i + 1 + after]:
        print(f"{x.address:#09x} {x.mnemonic} {x.op_str}{d.ann(x)}"[:130])


def _pat(s):
    return bytes(int(x, 16) for x in s.split())


def cmd_pat(args):
    lo, data = _text()
    p = _pat(args[0])
    minhits = int(args[1]) if len(args) > 1 else 1
    res = defaultdict(list)
    for m in re.finditer(re.escape(p), data):
        res[d.func_of(lo + m.start())].append(lo + m.start())
    for f, hits in sorted(res.items(), key=lambda x: x[0] or (0, 0)):
        if f and len(hits) >= minhits:
            print(hex(f[0]), hex(f[1] - f[0]), len(hits), [hex(h) for h in hits[:4]])


def cmd_pat2(args):
    lo, data = _text()
    sets = defaultdict(set)
    for i, s in enumerate(args):
        for m in re.finditer(re.escape(_pat(s)), data):
            sets[d.func_of(lo + m.start())].add(i)
    for f, s in sets.items():
        if f and len(s) == len(args):
            print(hex(f[0]), hex(f[1] - f[0]))


if __name__ == "__main__":
    {"eb": cmd_eb, "ctx": cmd_ctx, "pat": cmd_pat, "pat2": cmd_pat2}[sys.argv[1]](sys.argv[2:])
