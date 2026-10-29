"""Baked albedo PNG -> the D2R `.texture` set of a generated unit (3D venv or any python with numpy + Pillow).

    make_textures.py <albedo.png> <out data dir> <game path stem> [--gain 1.0]

Writes `<out>/<stem>_alb.texture` (RGBA8 with mips), `_nrm` (flat normal), `_orm` (occlusion 1, roughness 0.82, metal 0) and
`_sss` (all black: KTINT mask and thickness, nothing tinted, no subsurface). <game path stem> is the game path without the suffix, for
example `data/hd/character/enemy/pig/textures/pig`. The engine only loads texture files at paths D2R already has
(docs/hd-models.md), so the stem must name an existing alb/nrm/orm/sss set of a unit nothing in Median uses (pig).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import d2r_texture as dt  # noqa: E402


def levels(n):
    return int(np.log2(n)) + 1


def main():
    a = sys.argv[1:]
    src, out, stem = Path(a[0]), Path(a[1]), a[2]
    gain = float(a[a.index("--gain") + 1]) if "--gain" in a else 1.0
    im = np.array(Image.open(src).convert("RGB")).astype(np.float32) * gain
    alb = np.dstack([np.clip(im, 0, 255), np.full(im.shape[:2], 255, np.float32)]).astype(np.uint8)
    flat = np.zeros((256, 256, 4), np.uint8)
    nrm, orm, blk = flat.copy(), flat.copy(), flat.copy()
    nrm[...] = (128, 128, 255, 255)
    orm[...] = (255, 209, 0, 255)
    blk[..., 3] = 255
    for suf, arr in (("alb", alb), ("nrm", nrm), ("orm", orm), ("sss", blk)):
        p = out / (stem + "_" + suf + ".texture")
        p.parent.mkdir(parents=True, exist_ok=True)
        dt.write_rgba(p, arr, mips=levels(arr.shape[0]))
        print(p, arr.shape[1], "x", arr.shape[0])


if __name__ == "__main__":
    main()
