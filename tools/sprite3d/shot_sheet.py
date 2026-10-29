#!/usr/bin/env python
"""Side-by-side contact sheet of morph_shots.py runs: one row per run, one column per animation phase, cropped on the character.

  py -3 tools/sprite3d/shot_sheet.py out.png <run folder>:<tag> [<run folder>:<tag> ...] [--frames neutral_1,walk_3,...] [--box x0,y0,x1,y1] [--zoom 2]

The shots are local test evidence (screenshots of the game are never committed). `morph_shots.py --tag T` writes `<T>_<phase>_<n>.png`
into its run folder; a frame name here is `<phase>_<n>` (default: one or two per phase). The crop is centred on the player, who
the game camera keeps near the middle of the 1600 x 900 client.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

DEFAULT = ["neutral_1", "walk_3", "run_3", "attack1_0_2", "attack1_0_4", "attack_basic_2", "cast_0_2", "gethit_0_2"]


def main():
    a = sys.argv[1:]
    if len(a) < 2:
        print(__doc__)
        return 1
    out, runs = a[0], [x for x in a[1:] if ":" in x and not x.startswith("--")]
    frames = a[a.index("--frames") + 1].split(",") if "--frames" in a else DEFAULT
    box = tuple(int(v) for v in a[a.index("--box") + 1].split(",")) if "--box" in a else (620, 200, 980, 520)
    zoom = float(a[a.index("--zoom") + 1]) if "--zoom" in a else 1.5
    w, h = int((box[2] - box[0]) * zoom), int((box[3] - box[1]) * zoom)
    sheet = Image.new("RGB", (w * len(frames), (h + 16) * len(runs)), (20, 20, 20))
    dr = ImageDraw.Draw(sheet)
    for r, spec in enumerate(runs):
        folder, tag = spec.rsplit(":", 1)
        for c, f in enumerate(frames):
            p = Path(folder) / ("%s_%s.png" % (tag, f))
            if not p.exists():
                continue
            im = Image.open(p).convert("RGB").crop(box).resize((w, h), Image.LANCZOS)
            sheet.paste(im, (c * w, r * (h + 16) + 16))
            dr.text((c * w + 4, r * (h + 16) + 2), "%s %s" % (tag, f), fill=(255, 255, 0))
    sheet.save(out)
    print(out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
