#!/usr/bin/env python
"""TripoSG (VAST-AI-Research, MIT) image -> shape on local weights. No network: the weights folder and the code checkout are
given on the command line, Hugging Face is set offline.

  python run_triposg.py --src <TripoSG checkout> --weights <weights/TripoSG> --out <dir> [--seeds 42,7] [--steps 50]
                        [--guidance 7.0] [--depth 9] [--faces 0] [--bg 255] [--device cuda] image.png [image.png ...]

Every image is an RGBA sprite view (alpha = the monster). It is cropped to its alpha box, padded by a tenth and squared on
a plain background (what the project's own script does after its background remover, which is not used here), then
<out>/<image stem>_s<seed>.npz (pos, tris) and .glb are written. The mesh is in the model's frame: y up, the input view
looks at +z, the whole shape inside the cube -1 .. 1. A figure the model made small in that cube comes out coarse, and the
pipeline's `bounds` argument does not help: with a box tight around the figure the decoder returned a shapeless lump.

Runs in the 3D venv (torch for the AMD card: tools/sprite3d/README.md; diffusers, transformers, einops, trimesh,
scikit-image, omegaconf, jaxtyping, typeguard, peft). `diso` is CUDA only: the stand-in in diso_stub/ is put on the path and
the mesh comes out of the hierarchical decoder (use_flash_decoder=False).
"""
import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def prepare(path: Path, bg: int = 255, pad: float = 0.1) -> Image.Image:
    im = np.asarray(Image.open(path).convert("RGBA")).astype(np.float32)
    a = im[..., 3:] / 255.0
    ys, xs = np.nonzero(a[..., 0] > 0.02)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb = (im[..., :3] * a + bg * (1 - a))[y0:y1, x0:x1]
    h, w = rgb.shape[:2]
    side = int(max(h, w) * (1 + 2 * pad))
    out = np.full((side, side, 3), float(bg), np.float32)
    oy, ox = (side - h) // 2, (side - w) // 2
    out[oy:oy + h, ox:ox + w] = rgb
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype(np.uint8))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("images", nargs="+")
    ap.add_argument("--src", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", default="42")
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--guidance", type=float, default=7.0)
    ap.add_argument("--depth", type=int, default=9, help="octree depth of the marching cubes grid (9 = 512 cells)")
    ap.add_argument("--faces", type=int, default=0, help="keep the raw surface too, and a copy reduced to this many faces")
    ap.add_argument("--bg", type=int, default=255)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent / "diso_stub"))
    sys.path.insert(0, args.src)
    import torch
    import trimesh
    from triposg.pipelines.pipeline_triposg import TripoSGPipeline

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dtype = torch.float16 if args.device != "cpu" else torch.float32
    t0 = time.time()
    pipe = TripoSGPipeline.from_pretrained(args.weights).to(args.device, dtype)
    print("pipeline loaded in %.1f s on %s" % (time.time() - t0, args.device), flush=True)
    for path in args.images:
        img = prepare(Path(path), args.bg)
        img.save(out / (Path(path).stem + "_input.png"))
        for seed in [int(s) for s in args.seeds.split(",")]:
            t0 = time.time()
            with torch.no_grad():
                res = pipe(image=img, generator=torch.Generator(device=pipe.device).manual_seed(seed),
                           num_inference_steps=args.steps, guidance_scale=args.guidance, use_flash_decoder=False,
                           dense_octree_depth=min(8, args.depth), hierarchical_octree_depth=args.depth).samples[0]
            pos, tris = res[0].astype(np.float32), np.ascontiguousarray(res[1]).astype(np.int64)
            stem = out / ("%s_s%d" % (Path(path).stem, seed))
            np.savez(str(stem) + ".npz", pos=pos, tris=tris)
            trimesh.Trimesh(pos, tris, process=False).export(str(stem) + ".glb")
            print("%s seed %d: %d vertices, %d triangles, %.1f s" % (Path(path).name, seed, len(pos), len(tris), time.time() - t0),
                  flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
