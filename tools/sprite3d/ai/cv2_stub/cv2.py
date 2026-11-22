"""Stand-in for OpenCV: the one function Hunyuan3D-2's image preprocessor calls on in-memory pictures (resize), done with PIL.
Put on sys.path by run_hunyuan.py so the 3D venv needs no opencv wheel. Pictures are passed as PIL images, never as paths."""
import numpy as np
from PIL import Image

INTER_NEAREST, INTER_LINEAR, INTER_CUBIC, INTER_AREA = 0, 1, 2, 3
IMREAD_UNCHANGED, COLOR_BGR2RGB = -1, 4


def resize(src, dsize, interpolation=INTER_LINEAR):
    w, h = dsize
    a = np.asarray(src)
    if interpolation == INTER_AREA:      # area averaging when shrinking, linear when enlarging (what OpenCV does)
        mode = Image.BOX if (w < a.shape[1] or h < a.shape[0]) else Image.BILINEAR
    else:
        mode = {INTER_NEAREST: Image.NEAREST, INTER_LINEAR: Image.BILINEAR, INTER_CUBIC: Image.BICUBIC}[interpolation]
    if a.ndim == 3 and a.shape[2] == 1:  # OpenCV gives a one-channel picture back as h x w
        a = a[..., 0]
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a).resize((w, h), mode))
    return np.dstack([np.asarray(Image.fromarray(np.ascontiguousarray(a[..., c])).resize((w, h), mode))
                      for c in range(a.shape[2])])


def imread(*_a, **_k):
    raise NotImplementedError("cv2 stand-in: pass PIL images")


def cvtColor(*_a, **_k):
    raise NotImplementedError("cv2 stand-in: pass PIL images")
