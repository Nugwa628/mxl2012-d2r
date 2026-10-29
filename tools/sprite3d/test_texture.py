"""Step-2 texture test: a trivially recoloured copy of a D2R albedo as our own `.texture` (RGBA8, d2r_texture.write_rgba).

  <3d venv python> tools/sprite3d/test_texture.py <donor .texture> <out .texture> [r g b]   (channel gains, default 0.35 0.45 1.6)
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_texture as dt  # noqa: E402
import texture_png  # noqa: E402

src, out = sys.argv[1], sys.argv[2]
gain = [float(x) for x in sys.argv[3:6]] if len(sys.argv) >= 6 else [0.35, 0.45, 1.6]
im = texture_png.to_image(Path(src)).convert("RGBA")
a = np.array(im).astype(np.float32)
a[..., :3] = np.clip(a[..., :3] * np.array(gain), 0, 255)
print(src, im.size, "->", out)
Path(out).parent.mkdir(parents=True, exist_ok=True)
dt.write_rgba(Path(out), a.astype(np.uint8), mips=int(np.log2(min(im.size))) + 1)
