"""Where the UI tools read and write (all of it outside git: extract-mpq is the pure v005 extraction, work/ is ignored).

Mod tables and DC6: <Median tree>/data/global/{excel,ui}; the tree is tools/fxpaths.py's (MXL2012_EXTRACT or MXL_EXTRACT,
else assets/median from the asset pack, else <R>/mxl2012-runs/extract-mpq)
D2R baseline, a read-only copy made by `py -3 tools/hd_ui.py baseline <a D2R 93847 extraction>`:
  work/d2r-baseline/ui/{layouts/*.json, spells/skill_trees/*.sprite, excel/inventory.txt}
  work/d2r-baseline/palette/pal.dat (the icons lane's copy: `py -3 tools/hd_icons.py baseline ...` writes the same file)
Output: work/hd-ui/data/{global/ui/layouts, hd/global/ui/{spells/skill_trees,panel/mxl}, local/lng/strings/mxl2012} and
work/hd-ui/*.json reports; MXL2012_UI_OUT overrides work/hd-ui.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402

EXTRACT = fxpaths.MXL_ROOT
MOD = EXTRACT / "data" / "global"
EXCEL = MOD / "excel"
MOD_UI = MOD / "ui"
MOD_LNG = EXTRACT / "data" / "local" / "lng" / "eng"
BASE = ROOT / "work" / "d2r-baseline"
BASE_UI = BASE / "ui"
PAL = BASE / "palette" / "pal.dat"
OUT = Path(os.environ.get("MXL2012_UI_OUT") or ROOT / "work" / "hd-ui")
OUT_DATA = OUT / "data"
HD_OUT = OUT_DATA / "hd" / "global" / "ui"
LAYOUT_OUT = OUT_DATA / "global" / "ui" / "layouts"
STRINGS_OUT = OUT_DATA / "local" / "lng" / "strings" / "mxl2012"
