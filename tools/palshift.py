"""PalShift of Median's missiles (missiles2.bin byte 0, 25 rows): which rows, and what the shift does to their colour.

D2's missiles.txt PalShift (1-111) picks one of the 111 colour-variation tables of the act palette file (Pal.PL2: after
the 32 light levels, 16 tone tables and 5 x 256 blend tables, 111 tables of 256 bytes, row 1328 + n - 1 of the 256-byte
rows behind the 1024-byte palette). Each table maps a palette index to another palette index; Median's classic client
draws the missile's DCC through it. D2R's HD effects are particle programs with their own colours (docs/hd-effects.md
section 6), so the shift cannot be applied there: effects_hd.py scores the missile's art with the shift applied
(apply_shift) and picks the vanilla HD effect whose colour comes closest.

  py -3 tools/palshift.py            list the rows, their shift and the mean colour before / after
"""
from __future__ import annotations

import pathlib as _pl, sys as _sys; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent)); import projtemp  # noqa: E402,E702,F401  (temp files stay inside the project, tools/projtemp.py)
import csv
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MXL_EXCEL = ROOT / "assets" / "median" / "data" / "global" / "excel"
NAMED = ROOT / "work" / "named" / "missiles.txt"
MEDIAN = Path(r"C:\games\median-xl")
BS = chr(92)
PL2_NAME = BS.join(["data", "global", "palette", "ACT1", "Pal.PL2"])
PL2_PALETTE = 1024
FIRST_TABLE_ROW = 1328  # the 111 colour-variation tables
TABLES = 111

_pl2: bytes | None = None


def pl2() -> bytes:
    """The act 1 PL2 of the D2 data archive (the tables are the same in every act's file)."""
    global _pl2
    if _pl2 is None:
        import tempfile

        import native
        h = native.open_mpq(MEDIAN / "d2data.mpq")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "pal.pl2"
            if not native.extract(h, PL2_NAME, dest):
                raise SystemExit(f"{PL2_NAME} not found in {MEDIAN / 'd2data.mpq'}")
            _pl2 = dest.read_bytes()
        native.storm.SFileCloseArchive(h)
    return _pl2


def table(n: int) -> bytes:
    """The 256-byte palette index map of PalShift n (1..111)."""
    if not 1 <= n <= TABLES:
        raise ValueError(f"PalShift {n} is outside 1..{TABLES}")
    off = PL2_PALETTE + (FIRST_TABLE_ROW + n - 1) * 256
    return pl2()[off:off + 256]


def apply_shift(hist, n: int):
    """Colour histogram (256 counts per palette index) of a DCC after PalShift n."""
    t = table(n)
    out = [0] * 256
    for i, c in enumerate(hist):
        out[t[i]] += c
    return out


def shifted_rows(named: Path = NAMED, bin_dir: Path = MXL_EXCEL) -> dict[str, int]:
    """missile name (lowercase) -> PalShift, for the rows whose missiles2 byte is non-zero. The missiles2 table is
    parallel to Median's missiles.txt (work/named/missiles.txt carries the row order and the names)."""
    data = (bin_dir / "missiles2.bin").read_bytes()
    count = struct.unpack_from("<I", data)[0]
    with open(named, encoding="latin1", newline="") as f:
        rows = list(csv.reader(f, delimiter=chr(9), quoting=csv.QUOTE_NONE))[1:]
    if len(rows) != count:
        raise SystemExit(f"missiles2.bin has {count} rows, {named} {len(rows)}")
    return {rows[i][0].lower(): data[4 + i] for i in range(count) if data[4 + i]}


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    rows = shifted_rows()
    print(f"{len(rows)} missiles with a PalShift")
    for name, n in sorted(rows.items(), key=lambda kv: (kv[1], kv[0])):
        t = table(n)
        print(f"{n:4d}  {name}  (table maps {sum(1 for i in range(256) if t[i] != i)} of 256 indices)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
