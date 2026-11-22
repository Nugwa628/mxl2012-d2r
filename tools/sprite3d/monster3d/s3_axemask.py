"""Stage 3: split the upscaled standing sprites into body and axe by colour (the axe blades are the only large grey area).

  venv python s3_axemask.py <x4 views dir> <out dir>     writes nu_d<N>.png without the axe (alpha 0 there), axe_d<N>.png (axe
                                                         only) and split.png (a check sheet)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

src, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
rows = []
for d in range(8):
    im = np.asarray(Image.open(src / ("nu_d%d.png" % d)).convert("RGBA")).copy()
    rgb = im[..., :3].astype(np.float32)
    mx, mn = rgb.max(2), rgb.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    grey = (sat < 0.2) & (mx > 105) & (im[..., 3] > 100)
    grey = ndi.binary_opening(grey, iterations=2)
    lab, n = ndi.label(grey)
    size = ndi.sum(grey, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s in enumerate(size) if s > 1500])
    axe = ndi.binary_dilation(keep, iterations=7) & (im[..., 3] > 0)
    body = im.copy()
    body[axe, 3] = 0
    only = im.copy()
    only[~axe, 3] = 0
    Image.fromarray(body).save(out / ("nu_d%d.png" % d))
    Image.fromarray(only).save(out / ("axe_d%d.png" % d))
    bg = np.full(im.shape[:2] + (3,), 48, np.uint8)
    tile = [(bg * (1 - x[..., 3:] / 255.0) + x[..., :3] * (x[..., 3:] / 255.0)).astype(np.uint8) for x in (im, body, only)]
    rows.append(np.vstack(tile))
    print(d, "axe px", int(axe.sum()), "of", int((im[..., 3] > 100).sum()))
Image.fromarray(np.hstack(rows)).save(out / "split.png")
