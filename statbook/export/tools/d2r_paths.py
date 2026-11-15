"""Where the tools find Diablo II: Resurrected's own files (fonts, HD sprites, layouts, itemstatcost.txt).

D2R keeps them in its CASC storage; extract the files you need with a CASC tool (for example CascView or Ladik's CascLib)
into a folder that holds `data/...` as in the game (data/global/excel/itemstatcost.txt, data/hd/ui/fonts/...,
data/hd/global/ui/panel/...). Point the tools at it with the environment variable D2R_DATA; several folders may be listed,
separated by os.pathsep (";" on Windows), and are searched in order. Nothing is ever written there.

  set D2R_DATA=C:\\d2r-extract            (cmd)       $env:D2R_DATA = "C:\\d2r-extract"   (PowerShell)
"""
import os
from pathlib import Path

DIRS = [Path(p) for p in os.environ.get("D2R_DATA", "").split(os.pathsep) if p.strip()]
D2R = DIRS[0] if DIRS else Path(__file__).resolve().parent.parent / "d2r-data"


def d2r_file(rel: str) -> Path:
    """A file of D2R's data (rel = 'data/hd/...'), from the first D2R_DATA folder that has it."""
    for d in DIRS or [D2R]:
        p = Path(d) / rel
        if p.exists():
            return p
    raise SystemExit(f"{rel} is not in D2R_DATA ({os.pathsep.join(str(d) for d in DIRS) or 'not set'}): extract it from "
                     "your D2R install (see tools/d2r_paths.py)")
