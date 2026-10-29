"""Clean the projected Wereowl albedo (3D venv: numpy, scipy, cv2, PIL).

    albedo_clean.py <albedo_raw.png> <coverage.png|-> <out albedo.png> [--median 64] [--dark 26] [--denoise 4]

project_texture.py bakes the albedo from the small Median sprites: the sprite outlines and shadow pixels come in as near-black texels
(a quarter of the atlas is below luma 20), the chart patchwork is noisy, and the whole map is dark (median luma 36 against 64 for
the vanilla werebear albedo). This
1. marks texels darker than `--dark` (luma, after a 3x3 median so single texels do not count) and every texel the projection did
   not see (coverage < 255) as unreliable, grows the mask a little and inpaints it from the reliable neighbours (Telea);
2. denoises with a light non-local-means pass (`--denoise` strength) and rounds the chart patches off with a small bilateral filter;
3. scales the map so its median luma is `--median` (the vanilla werebear's), with a soft shoulder so highlights keep their shape.
The result replaces `albedo.png` as the build input (`ALBEDO_GAMMA` = 1.0 in tools/wereowl_models.py); the raw bake is kept as
`source/albedo_raw.png`.
"""
import sys

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage


def luma(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114], np.float32)


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        print(__doc__)
        return 1
    src, cov, dst = a[:3]
    target = float(a[a.index("--median") + 1]) if "--median" in a else 64.0
    dark = float(a[a.index("--dark") + 1]) if "--dark" in a else 26.0
    dn = float(a[a.index("--denoise") + 1]) if "--denoise" in a else 4.0
    im = np.asarray(Image.open(src).convert("RGB"))
    L = luma(cv2.medianBlur(im, 3).astype(np.float32))
    cv = np.asarray(Image.open(cov).convert("L")) if cov != "-" else np.full(L.shape, 255, np.uint8)
    used = cv > 0  # texels some face maps to; the rest of the atlas is gutter / empty and is refilled at the end
    bad = (L < dark) & used
    bad = ndimage.binary_dilation(bad, iterations=2) & used
    bad = ndimage.binary_opening(bad, iterations=1) | ((L < dark * 0.5) & used)  # drop isolated specks, keep the dark cores
    bad |= cv == 128  # mapped but no sprite saw it: its colour is the nearest-texel smear of the bake
    print("unreliable texels: %.1f%% of the mapped ones" % (100 * bad.sum() / used.sum()))
    # inpaint at half size (the bad regions are large and smooth: colour from the surrounding fur), then composite
    small = cv2.resize(im, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    msk = cv2.resize(bad.astype(np.uint8) * 255, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_NEAREST)
    fill = cv2.inpaint(small, msk, 7, cv2.INPAINT_TELEA)
    fill = cv2.resize(fill, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_CUBIC)
    soft = cv2.GaussianBlur(bad.astype(np.float32), (0, 0), 2.0)[..., None]
    out = (im * (1 - soft) + fill * soft).astype(np.uint8)
    if dn > 0:
        out = cv2.fastNlMeansDenoisingColored(out, None, dn, dn, 5, 15)
    out = cv2.bilateralFilter(out, 5, 24, 3)
    f = out.astype(np.float32)
    m = float(np.median(luma(f)[used]))
    gain = target / max(m, 1.0)
    f = f * gain
    # soft shoulder above 200 so the lifted highlights do not clip
    hi = f > 200
    f[hi] = 200 + 55 * np.tanh((f[hi] - 200) / 55)
    out = np.clip(f, 0, 255).astype(np.uint8)
    # gutters and empty atlas: the nearest mapped texel (keeps the bilinear / mip borders of the charts clean)
    _, (iy, ix) = ndimage.distance_transform_edt(~used, return_indices=True)
    out = np.where(used[..., None], out, out[iy, ix])
    Image.fromarray(out).save(dst)
    Lo = luma(out.astype(np.float32))
    print("median luma (mapped) %.1f -> %.1f (gain %.2f), below 20: %.1f%% -> %.1f%%  -> %s" % (
        m, np.median(Lo[used]), gain, 100 * (L < 20)[used].mean(), 100 * (Lo < 20)[used].mean(), dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
