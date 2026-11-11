"""Signature patterns for the invtabs plugin, made from the 93847 memory dump.

  py -3 tools/invtabs_sigs.py            # check every pattern in invtabs/src/invtabs_natives.h
  py -3 tools/invtabs_sigs.py --make     # derive the shortest unique pattern for each target

A pattern is hex bytes with ?? wildcards. Relative call/jump targets and RIP-relative
displacements are wildcards, so the pattern survives code moving between builds. Every
pattern must match exactly once in .text. For a data target (the grid vtable) the pattern
covers the instruction that loads it, and `rip` names the offset of its disp32.

Dump path: env D2R_DUMP or tools/d2r_find.py's default.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import d2r_find  # noqa: E402

import capstone  # noqa: E402

NATIVES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "invtabs", "src", "invtabs_natives.h")

# name -> (start RVA of the pattern, RVA it resolves to, how it resolves)
TARGETS = {
    "InventoryOf": (0x34A360, 0x34A360, "entry"),
    "FirstItem": (0x388C10, 0x388C10, "entry"),
    "NextItem": (0x38ABA0, 0x38ABA0, "entry"),
    "NodeMode": (0x38A930, 0x38A930, "entry"),
    "CursorItem": (0x15F100, 0x15F100, "entry"),
    "GridOwner": (0x2A7810, 0x2A7810, "entry"),
    "PointToCell": (0x2C6300, 0x2C6300, "entry"),
    "ItemSize": (0x371850, 0x371850, "entry"),
    "LocalIndex": (0x8B2D0, 0x8B2D0, "entry"),
    "PlayerUnit": (0x9A480, 0x9A480, "entry"),
    "GridVtable": (0x2C3467, 0x1CF3800, "rip"),
}


def text_bytes():
    b = d2r_find.buf()
    lo, hi = d2r_find.TEXT
    return bytes(b[lo:hi]), lo


def masked(start, length):
    """Bytes from start with relative operands wildcarded (None)."""
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = True
    raw = bytes(d2r_find.buf()[start:start + length + 32])
    out = []
    for insn in md.disasm(raw, start):
        b = list(insn.bytes)
        if insn.mnemonic in ("call", "jmp") or insn.mnemonic.startswith("j"):
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


def make():
    text, lo = text_bytes()
    for name, (start, target, kind) in TARGETS.items():
        for length in range(8, 200):
            p = masked(start, length)
            if len(p) < length:
                continue
            if p[-1] is None:
                continue
            h = hits(p, text, lo)
            if h == [start]:
                rip = ""
                if kind == "rip":
                    m = masked(start, 16)
                    rip = f" rip={next(i for i, v in enumerate(m) if v is None)}"
                print(f"{name:12} start=0x{start:X} target=0x{target:X}{rip}  {fmt(p)}")
                break
        else:
            print(f"{name:12} NO UNIQUE PATTERN within 200 bytes")


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
        print(f"{'ok  ' if ok else 'FAIL'} {name:12} at 0x{at:X} -> 0x{got:X} (expected 0x{expect:X})")
    return 1 if bad else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make", action="store_true")
    a = ap.parse_args()
    if a.make:
        make()
    else:
        sys.exit(check())
