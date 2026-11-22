"""Stage 1: a monster's classic frames (prototype F's decoder, copied) and their 4x upscale.

  python s1_frames.py [--token T] classic               every mode: frame PNGs at 1x on the mode's common canvas + frames.json
  python s1_frames.py up MODE:FRAME [...]     the 8 directions of those frames 4x (de-dither + Real-ESRGAN x4plus, alpha by
                                             Lanczos + threshold: prototype F's pipeline), GPU gate checked first
"""
import json
import sys

import numpy as np
from PIL import Image

import common

sys.path.insert(0, str(common.WT / "tools"))
sys.path.insert(0, str(common.FCOPY))
import monster_sheet  # noqa: E402
import monster_upscale  # noqa: E402

OUT = common.STAGES / "1-frames"
ACT = 1


def classic():
    data = monster_sheet.load(common.TOKEN)
    pal = monster_sheet.act_palette(ACT)
    meta = {}
    for mode, e in data.items():
        box = monster_sheet.mode_box(e)
        cof = e["cof"]
        d = OUT / "classic" / mode
        d.mkdir(parents=True, exist_ok=True)
        for di in range(cof["dirs"]):
            for f in range(cof["frames"]):
                monster_sheet.compose(e, di, f, box, pal).save(d / ("d%d_f%02d.png" % (di, f)))
        meta[mode] = {"box": box, "dirs": cof["dirs"], "frames": cof["frames"], "speed": cof["speed"]}
        print(mode, meta[mode], flush=True)
    (OUT / "classic" / "frames.json").write_text(json.dumps(meta, indent=1))


def up(picks, method="dedither+esrgan:realesrgan-x4plus"):
    if not common.gpu_gate(240):
        return 1
    data = monster_sheet.load(common.TOKEN)
    pal = monster_sheet.act_palette(ACT)
    work = common.EV / "tmp"
    for pick in picks:
        mode, f = pick.split(":")
        e = data[mode.lower()]
        box = monster_sheet.mode_box(e)
        frames = [np.asarray(monster_sheet.compose(e, d, int(f), box, pal)) for d in range(e["cof"]["dirs"])]
        big = monster_upscale.upscale(frames, 4, method, {"exe": str(common.ESRGAN), "work": str(work)})
        d = OUT / "x4" / ("%s%02d" % (mode.lower(), int(f)))
        d.mkdir(parents=True, exist_ok=True)
        for di, b in enumerate(big):
            Image.fromarray(b, "RGBA").save(d / ("nu_d%d.png" % di))
        print(pick, "->", d, big[0].shape, flush=True)
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "classic":
        classic()
    else:
        sys.exit(up(sys.argv[2:]))
