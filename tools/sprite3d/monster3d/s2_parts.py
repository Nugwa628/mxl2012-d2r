"""Stage 2: split the sprite views of a two-part monster (the Glowing Fungus: a bright cap on a dark body) by colour.

  venv python s2_parts.py [--token T] [--views <dir>] [--blue 18] [--check <sheet.png>]

For each nu_d<N>.png of the views dir (default stages/1-frames/x4/nu00) the cap is the largest connected patch of pixels
that are clearly blue (blue above red by --blue) or bright, opened, and its convex hull; the body is the rest. Writes
stages/2-shape/parts/cap/nu_d<N>.png and .../body/nu_d<N>.png (the sprite with the other part's alpha set to 0, same
canvas, so cameras fitted to the whole sprite stay valid) and parts.json (the cap's box and the row where it ends, per
direction). --check writes a sheet: sprite, cap, body per direction.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.morphology import convex_hull_image

import common

a = sys.argv[1:]
views = Path(a[a.index("--views") + 1]) if "--views" in a else common.STAGES / "1-frames" / "x4" / "nu00"
blue = float(a[a.index("--blue") + 1]) if "--blue" in a else 18
OUT = common.STAGES / "2-shape" / "parts"
(OUT / "cap").mkdir(parents=True, exist_ok=True)
(OUT / "body").mkdir(parents=True, exist_ok=True)
(OUT / "in").mkdir(parents=True, exist_ok=True)
meta, tiles = {}, []
for d in common.CLOCKWISE_8:
    im = np.asarray(Image.open(views / ("nu_d%d.png" % d)).convert("RGBA"))
    k = max(1, im.shape[0] // 100)      # 1 for classic frames, 4 for the 4x ones
    rgb, al = im[..., :3].astype(np.float32), im[..., 3] > 100
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    m = al & ((b - r > blue) | (rgb.min(2) > 170))
    m = ndimage.binary_closing(m, iterations=2 * k)
    lab, n = ndimage.label(m)
    if n:
        m = lab == 1 + np.argmax(ndimage.sum(m, lab, range(1, n + 1)))
    # thin blue bits of the body (lit arms) off, then the hull: the cap's dark middle is not blue and, seen from the front,
    # borders the dark body
    m = ndimage.binary_opening(ndimage.binary_fill_holes(m), iterations=2 * k)
    lab, n = ndimage.label(m)
    if n:
        m = lab == 1 + np.argmax(ndimage.sum(m, lab, range(1, n + 1)))
    m = convex_hull_image(m) & al
    rest = al & ~ndimage.binary_dilation(m, iterations=k)      # the cap's rim line stays with the cap
    lab, n = ndimage.label(rest)
    if n:
        sizes = ndimage.sum(rest, lab, range(1, n + 1))
        rest = np.isin(lab, 1 + np.nonzero(sizes >= 0.05 * sizes.max())[0])
    m = al & ~rest
    cap, body = im.copy(), im.copy()
    cap[..., 3] = np.where(m, im[..., 3], 0)
    body[..., 3] = np.where(m, 0, im[..., 3])
    for part, pic in (("cap", cap), ("body", body)):
        Image.fromarray(pic).save(OUT / part / ("nu_d%d.png" % d))
        Image.fromarray(pic).save(OUT / "in" / ("%s_d%d.png" % (part, d)))      # one folder, distinct names: generator input
    ys, xs = np.nonzero(m)
    meta[d] = {"cap_box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], "cap_px": int(m.sum()),
               "body_px": int((al & ~m).sum())}
    bg = np.array([40, 40, 48], np.float32)
    over = lambda t: (t[..., :3] * (t[..., 3:] / 255.0) + bg * (1 - t[..., 3:] / 255.0)).astype(np.uint8)  # noqa: E731
    tiles.append(np.vstack([over(im), over(cap), over(body)]))
(OUT / "parts.json").write_text(json.dumps(meta, indent=1))
print(json.dumps(meta))
if "--check" in a:
    sheet = Image.fromarray(np.hstack(tiles))
    if sheet.height < 600:
        sheet = sheet.resize((sheet.width * 4, sheet.height * 4), Image.NEAREST)
    sheet.save(a[a.index("--check") + 1])
