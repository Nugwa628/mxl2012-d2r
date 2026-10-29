"""Regenerate the D2R-XL 2012 downloader's generated art: the status panel and the icon. background.png is the owner's
art (launcher/res/ART.md) and is never written here.

  py -3 tools/launcher_art/make_all.py [--out launcher/res] [--fonts <res folder with the fonts>]
                                       [--icon-png docs/icon.png] [--preview <preview.png>]

Needs Pillow and numpy (a venv is fine). Output is deterministic (fixed seeds). The fonts (only for the preview
mock-up) are read from --fonts, $MXL_LAUNCHER_RES or launcher/res.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_icon, make_panel, make_preview  # noqa: E402
from art_common import REPO, font_dir  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "launcher" / "res"))
    ap.add_argument("--fonts")
    ap.add_argument("--icon-png", default=str(REPO / "docs" / "icon.png"))
    ap.add_argument("--preview")
    ap.add_argument("--only", choices=["panel", "icon"], action="append")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(a.only or ["panel", "icon"])
    if "panel" in only:
        make_panel.main(str(out / "popup-window.png"))
    if "icon" in only:
        Path(a.icon_png).parent.mkdir(parents=True, exist_ok=True)
        make_icon.main(str(out / "icon.ico"), a.icon_png)
    if a.preview:
        make_preview.build(str(out), font_dir(a.fonts)).save(a.preview)
        print("preview:", a.preview)


if __name__ == "__main__":
    main()
