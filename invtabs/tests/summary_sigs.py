"""Signature patterns for the charm-tab summary (invtabs/src/summary_natives.h), from the 93847 dump.

  py -3 invtabs/tests/summary_sigs.py            # check every pattern in summary_natives.h
  py -3 invtabs/tests/summary_sigs.py --make     # derive the shortest unique pattern for each target

A pattern is hex bytes with ?? wildcards. Relative call/jump targets and RIP-relative
displacements are wildcards, so a pattern survives code moving between builds. Every pattern
must match exactly once in .text.

Most targets are reached through a call site, not their entry bytes: D2RCore (D2RLoader)
replaces the entry of several stat functions with `jmp [slot]`, and entry bytes of small
helpers are rarely unique. For a call site, `rip` is the offset of the call's rel32 inside the
pattern and the target is the call destination. For a data target `rip` is the offset of the
loading instruction's disp32. For an entry pattern `rip` is -1 and `adjust` is added to the hit.

Dump path: env D2R_DUMP or tools/d2r_find.py's default.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools"))
import projtemp  # noqa: E402,F401
import d2r_find  # noqa: E402

import capstone  # noqa: E402

MIN_LEN = 16  # shorter patterns are unique today but likely to collide in a later build
NATIVES = os.path.join(HERE, "..", "src", "summary_natives.h")

# name -> (kind, earliest address the pattern may start at, anchor instruction, expected target)
# kind "call": the anchor is a call rel32; "rip": the anchor loads a RIP-relative address;
# "entry": the pattern starts at the function entry (anchor unused).
TARGETS = {
    # SKILLDESC_BuildStatBuffDesc analogue 0x2dc4b0 (the item tooltip's stat block)
    "GetStatList": ("call", 0x2DC540, 0x2DC55F, 0x2F5A00),
    "AllocStatList": ("call", 0x2DC586, 0x2DC595, 0x2F7300),
    "DataFlag": ("call", 0x2DC595, 0x2DC5A4, 0x34A0E0),
    "StatListText": ("call", 0x2DC7A6, 0x2DC7D3, 0x2DA760),
    "FreeStatList": ("call", 0x2DCC4B, 0x2DCC52, 0x2F4180),
    # StatListAdd (D2RCore thunk) from 0x2f3528
    "StatListAdd": ("call", 0x2F3528, 0x2F354F, 0x2F3330),
    # stats of the item are merged into its owner (client refresh 0x1c9686)
    "Merged": ("call", 0x1C97C0, 0x1C97F1, 0x2F8120),
    # one stat with the local player's context (Advanced Stats panel 0x14eb280)
    "FormatOne": ("call", 0x14EB290, 0x14EB2C3, 0x2D97E0),
    "StatRecord": ("call", 0x2DB700, 0x2DB73A, 0x2D9730),
    # UI text setters (devmenu.cpp uses the same functions)
    "UiRoot": ("rip", 0x83F3A0, 0x83F3AE, 0x3440170),
    "UiFindPanel": ("call", 0x843C2F, 0x843C34, 0x89F760),
    "UiFindChild": ("entry", 0x855C90, 0, 0x855C90),
    "TextBoxSetText": ("entry", 0x86DD50, 0, 0x86DD50),
}


def text_bytes():
    b = d2r_find.buf()
    lo, hi = d2r_find.TEXT
    return bytes(b[lo:hi]), lo


def md():
    m = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    m.detail = True
    return m


def insns(start, end):
    """Instructions from start (an instruction boundary) up to and including the one at end."""
    out = []
    raw = bytes(d2r_find.buf()[start:end + 16])
    for i in md().disasm(raw, start):
        out.append(i)
        if i.address >= end:
            break
    return out


def masked(start, length):
    """Bytes from start with relative operands wildcarded (None)."""
    raw = bytes(d2r_find.buf()[start:start + length + 32])
    out = []
    for insn in md().disasm(raw, start):
        b = list(insn.bytes)
        if insn.bytes[0] in (0xE8, 0xE9) or (insn.bytes[0] == 0x0F and 0x80 <= insn.bytes[1] <= 0x8F):
            for i in range(len(b) - 4, len(b)):
                b[i] = None
        if insn.disp_offset and any(op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP for op in insn.operands):
            for i in range(insn.disp_offset, insn.disp_offset + 4):
                b[i] = None
        out.extend(b)
        if len(out) >= length:
            break
    return out[:length]


def to_regex(pattern):
    return re.compile(b"".join(b"." if v is None else re.escape(bytes([v])) for v in pattern), re.DOTALL)


def hits(pattern, text, lo, limit=3):
    found = []
    for m in to_regex(pattern).finditer(text):
        found.append(lo + m.start())
        if len(found) >= limit:
            break
    return found


def fmt(pattern):
    return " ".join("??" if v is None else f"{v:02X}" for v in pattern)


def parse(text):
    return [None if t == "??" else int(t, 16) for t in text.split()]


def best(kind, first, anchor, text, lo):
    """Shortest unique pattern: (start, pattern, rip) or None."""
    if kind == "entry":
        starts = [(first, 0)]
    else:
        begin = d2r_find.func_of(anchor)[0]
        seq = [i for i in insns(begin, anchor) if i.address >= min(first, anchor - 64)]
        if not seq or seq[-1].address != anchor:
            raise SystemExit(f"0x{anchor:X} is not an instruction boundary from 0x{first:X}")
        a = seq[-1]
        if kind == "call":
            if a.bytes[0] != 0xE8:
                raise SystemExit(f"0x{anchor:X} is not a call rel32")
            off_in_anchor, need_end = 1, anchor + 5
        else:
            off_in_anchor, need_end = a.disp_offset, anchor + a.size
        starts = [(i.address, anchor - i.address + off_in_anchor) for i in reversed(seq)]
        starts = [(s, r, need_end) for s, r in starts]
    found = None
    for item in starts:
        s, r = item[0], item[1]
        min_len = (item[2] - s) if kind != "entry" else 8
        for length in range(max(min_len, MIN_LEN), min_len + 96):
            p = masked(s, length)
            if len(p) < length or p[-1] is None:
                continue
            if hits(p, text, lo) == [s]:
                if found is None or len(p) < len(found[1]):
                    found = (s, p, r if kind != "entry" else -1)
                break
    return found


def make():
    text, lo = text_bytes()
    for name, (kind, first, anchor, target) in TARGETS.items():
        f = best(kind, first, anchor, text, lo)
        if f is None:
            print(f"{name:14} NO UNIQUE PATTERN")
            continue
        s, p, rip = f
        adjust = 0
        print(f'    {{"{name}", "{fmt(p)}", {rip}, {adjust}, 0x{target:X}}},  // at 0x{s:X}')


def check():
    text, lo = text_bytes()
    src = open(NATIVES, encoding="utf-8").read()
    rows = re.findall(r'\{\s*"(\w+)",\s*"([0-9A-F? ]+)",\s*(-?\d+),\s*(-?\d+),\s*0x([0-9A-Fa-f]+)\s*\}', src)
    if not rows:
        print("no patterns found in", NATIVES)
        return 1
    bad = 0
    for name, pat, rip, adjust, expect in rows:
        rip, adjust, expect = int(rip), int(adjust), int(expect, 16)
        h = hits(parse(pat), text, lo)
        if len(h) != 1:
            print(f"FAIL {name}: {len(h)} match(es)")
            bad += 1
            continue
        at = h[0]
        if rip >= 0:
            disp = int.from_bytes(bytes(d2r_find.buf()[at + rip:at + rip + 4]), "little", signed=True)
            got = at + rip + 4 + disp
        else:
            got = at + adjust
        ok = got == expect
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {name:14} at 0x{at:X} -> 0x{got:X} (expected 0x{expect:X})")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make", action="store_true")
    a = ap.parse_args()
    if a.make:
        make()
    else:
        sys.exit(check())
