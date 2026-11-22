"""Stage 3: clean a projected albedo without repainting it (numpy + scipy only).

  venv python s3_albedo.py <albedo.png> <coverage.png> <out.png> [--dark 26]

Texels the projection did not sample (coverage < 255) and near-black texels (sprite outline and shadow pixels, luma under
--dark after a 3x3 median) are replaced by the nearest reliable texel; a 3x3 median then takes the single-texel noise of the
chart patchwork out. No brightness change: the colours stay the sprite colours.
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

a = sys.argv[1:]
dark = float(a[a.index("--dark") + 1]) if "--dark" in a else 26
alb = np.asarray(Image.open(a[0]).convert("RGB")).astype(np.float32)
cov = np.asarray(Image.open(a[1]).convert("L"))
luma = ndi.median_filter(alb @ np.array([0.299, 0.587, 0.114], np.float32), 3)
bad = ndi.binary_dilation((luma < dark) | (cov < 255), iterations=1)
idx = ndi.distance_transform_edt(bad, return_distances=False, return_indices=True)
out = alb[idx[0], idx[1]]
out = np.dstack([ndi.median_filter(out[..., c], 3) for c in range(3)])
Image.fromarray(out.astype(np.uint8)).save(a[2])
print(a[2], "replaced %.1f %% of the texels; median luma %.0f -> %.0f"
      % (100 * bad.mean(), np.median(alb @ [0.299, 0.587, 0.114]), np.median(out @ [0.299, 0.587, 0.114])))
