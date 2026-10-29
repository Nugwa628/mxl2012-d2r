"""Disassemble a D2Sigma.dll function by address, annotating game-function pointers and strings.

Usage: python tools/disasm.py 0x100a6aa0 [0x...]   (stops at int3 padding or --max bytes)
"""
import argparse
import json
from pathlib import Path

import capstone

from sigma_imports import PE

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("addr", nargs="+", type=lambda s: int(s, 16))
    ap.add_argument("--dll", default=r"C:\Games\median-xl\D2Sigma.dll")
    ap.add_argument("--max", type=int, default=0x400)
    a = ap.parse_args()
    pe = PE(Path(a.dll).read_bytes())
    imports = json.loads((ROOT / "research" / "sigma_imports.json").read_text("utf-8"))
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    for va in a.addr:
        off = pe.va_to_off(va)
        print(f"===== {va:#x}")
        for ins in md.disasm(pe.b[off:off + a.max], va):
            if ins.mnemonic == "int3":
                break
            notes = []
            for tok in ins.op_str.replace("[", " ").replace("]", " ").replace(",", " ").split():
                if not tok.startswith("0x"):
                    continue
                if tok in imports:
                    e = imports[tok]
                    notes.append(f"{e['module']}+{e.get('offset', e.get('ordinal'))} {e.get('function', '')}")
                else:
                    v = int(tok, 16)
                    if 0x10167000 <= v < 0x101d4000:
                        s = pe.cstr(v)
                        if len(s) >= 3 and s.isprintable():
                            notes.append(repr(s[:60]))
            print(f"  {ins.address:#x} {ins.mnemonic:6} {ins.op_str}" + (f"   ; {'; '.join(notes)}" if notes else ""))


if __name__ == "__main__":
    main()
