"""Where the icon tools read and write (all of it outside git: extract-mpq is the pure v005 extraction, work/ is ignored).

Mod tables and DC6: <Median tree>/data/global/{excel,items,ui/spells}; the tree is tools/fxpaths.py's (MXL2012_EXTRACT or MXL_EXTRACT,
else assets/median from the asset pack, else <R>/mxl2012-runs/extract-mpq)
D2R baseline, a read-only copy made by `py -3 tools/hd_icons.py baseline <a D2R 93847 extraction>`:
  work/d2r-baseline/{filelist.txt, excel/*.txt, hd-items/*.json, items/*.dc6, palette/pal.dat}
Output: work/hd/data/hd/... (sprites and the JSON item maps), work/hd/*.json (reports); MXL2012_HD_OUT overrides work/hd.
"""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402

EXTRACT = fxpaths.MXL_ROOT
MOD = EXTRACT / "data" / "global"
EXCEL = MOD / "excel"
BASE = ROOT / "work" / "d2r-baseline"
OUT = Path(os.environ.get("MXL2012_HD_OUT") or ROOT / "work" / "hd")
HD_OUT = OUT / "data" / "hd"


def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Header and rows of a tab table (cp1252 text; short rows padded, empty lines dropped). The 0xB5 letter (µ) of the 24
    µ item codes becomes `^`, as tools/mxl2012_prep.py writes them into the built tables (the HD item maps are keyed by code)."""
    with Path(path).open(encoding="latin-1", newline="") as f:
        rows = list(csv.reader((line.replace("\xb5", "^") for line in f), delimiter="\t"))
    head = rows[0]
    body = [r + [""] * (len(head) - len(r)) for r in rows[1:] if any(c for c in r)]
    return head, body


def col(head: list[str], name: str) -> int | None:
    """Index of the column `name` (case-insensitive), None when the table lacks it."""
    low = [h.lower() for h in head]
    return low.index(name.lower()) if name.lower() in low else None
