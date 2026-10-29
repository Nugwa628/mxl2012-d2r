"""Preview composite (not committed): the background with mock text and buttons at the downloader's layout rects
(launcher/src/win/window.cpp: PanelRect, StatusRect, LineRect, BarRect, button rects, HowToPlayRect, FooterRect).
Buttons are drawn the way DrawButton does (Exocet labels); this is only a mock-up, not the real window.

  py -3 tools/launcher_art/make_preview.py <preview.png> [--res launcher/res] [--fonts <folder with the fonts>]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))

from art_common import REPO, font_dir  # noqa: E402

W, H = 960, 640  # CanvasW, CanvasH
PANEL = (230, 262)
STATUS = (270, 284)  # StatusRect, 19 px a line
BAR = (272, 389, 416, 9)
INSTALL = (360, 444, 240, 60)
ROW = [((175, 516, 140, 34), "Repair"), ((325, 516, 140, 34), "Uninstall"), ((475, 516, 150, 34), "D2R folder"),
       ((635, 516, 150, 34), "Mods folder")]
HOW_Y, HOW_WRAP = 570, W - 220  # HowToPlayRect: first line's centre, wrap width
FOOT_Y = 616  # FooterRect's centre
ICON = (918, 602, 28, 28)

GOLD, BODY, DIM = (232, 196, 128), (222, 212, 192), (150, 136, 112)
HOW = ("How to play: start D2RLoader.exe in your D2R folder. The first time, click the gear on the character screen, set "
       "Default Mod to D2R-XL 2012, Apply, and start D2RLoader again.")
LINES = [r"D2R: C:\Program Files (x86)\Diablo II Resurrected (build 93847)", "D2RLoader: 1.3.1-beta (OK)",
         "D2R-XL 2012: 0.9.0 installed (latest)", r"Mod folder: ...\Diablo II Resurrected\mods\mxl2012"]
FOOT = ("Downloader 0.1.0  ·  D2R-XL 2012, a port of Median XL 2012 by Brother Laz. Diablo II by Blizzard Entertainment. "
        "Not affiliated with Blizzard.")
S = 2


def build(res: str, fonts) -> Image.Image:
    base = Image.open(f"{res}/background.png").convert("RGBA")
    assert base.size == (W, H), base.size
    base.alpha_composite(Image.open(f"{res}/popup-window.png").convert("RGBA"), PANEL)
    big = base.resize((W * S, H * S), Image.LANCZOS)
    ov = Image.new("RGBA", big.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    body = lambda sz: ImageFont.truetype(str(fonts / "RobotoCondensed.ttf"), int(sz * S))
    title = lambda sz: ImageFont.truetype(str(fonts / "exocet.ttf"), int(sz * S)) if (fonts / "exocet.ttf").is_file() else body(sz)

    def text(xy, s, font, fill, anchor="la"):
        x, y = xy[0] * S, xy[1] * S
        d.text((x + S, y + S), s, font=font, fill=(0, 0, 0, 170), anchor=anchor)
        d.text((x, y), s, font=font, fill=fill + (255,), anchor=anchor)

    for i, line in enumerate(LINES):
        text((STATUS[0], STATUS[1] + i * 19), line, body(14), BODY)
    bx, by, bw, bh = BAR
    text((bx + bw / 2, by - 16), "Downloading D2R-XL-2012.7z: 41.0 of 96.5 MB, 2 min left", body(14), GOLD, "mm")
    d.rectangle([bx * S, by * S, (bx + bw) * S, (by + bh) * S], fill=(0, 0, 0, 170))
    d.rectangle([bx * S, by * S, (bx + bw * 0.42) * S, (by + bh) * S], fill=(210, 130, 50, 255))
    d.rectangle([bx * S, by * S, (bx + bw) * S, (by + bh) * S], outline=(110, 88, 56, 255))

    def button(r, label, kind="small"):
        x, y, w, h = r
        box = [(x + 1) * S, (y + 1) * S, (x + w - 1) * S, (y + h - 1) * S]
        if kind == "big":
            d.rounded_rectangle(box, radius=7 * S, fill=(96, 30, 12, 230), outline=GOLD + (255,), width=2 * S)
            text((x + w / 2, y + h / 2), label, title(30), GOLD, "mm")
        else:
            d.rounded_rectangle(box, radius=4 * S, fill=(0, 0, 0, 160), outline=(120, 96, 60, 255), width=S)
            text((x + w / 2, y + h / 2), label, title(15), GOLD, "mm")

    button(INSTALL, "Install", "big")
    for r, label in ROW:
        button(r, label)
    words, lines, cur = HOW.split(), [], ""
    f = body(14)
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) > HOW_WRAP * S:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    for i, l in enumerate(lines):
        text((W / 2, HOW_Y + i * 18), l, f, GOLD, "mm")
    text((14, FOOT_Y), FOOT, body(12), DIM, "lm")
    ix, iy, iw, ih = ICON  # issues icon stand-in
    d.ellipse([(ix + 4) * S, (iy + 5) * S, (ix + iw - 4) * S, (iy + ih - 5) * S], fill=GOLD + (255,))
    big.alpha_composite(ov)
    return big.resize((W, H), Image.LANCZOS).convert("RGB")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--res", default=str(REPO / "launcher" / "res"))
    ap.add_argument("--fonts")
    a = ap.parse_args()
    build(a.res, font_dir(a.fonts)).save(a.out)
    print("preview:", a.out)


if __name__ == "__main__":
    main()
