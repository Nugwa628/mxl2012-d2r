#!/usr/bin/env python
"""Hunyuan3D-2mv (Tencent, tencent-hunyuan-community licence: no use in the EU, the UK or South Korea) four sprite views ->
shape on local weights. A COMPARISON tool only: nothing it makes may be shipped. No network: the weights folder and the code
checkout are given on the command line, Hugging Face is set offline.

  python run_hunyuan.py --src <Hunyuan3D-2 checkout> --weights <folder that holds Hunyuan3D-2mv/hunyuan3d-dit-v2-mv> --out <dir>
                        --front f.png --left l.png --back b.png --right r.png [--name quad] [--seeds 42,7] [--steps 50]
                        [--guidance 5.0] [--octree 380] [--device cuda]

The four pictures are RGBA sprite views a quarter turn apart (README.md: directions 4, 5, 6, 7 of a Median monster); the
model's own preprocessor centres each on white. Writes <out>/<name>_s<seed>.npz (pos, tris) and .glb; the mesh is in the
model's frame (y up).

Runs in the 3D venv (README.md: transformers < 5, diffusers < 0.36). The checkout imports OpenCV for three resize calls: the
stand-in in cv2_stub/ is put on the path instead of installing it.
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", required=True)
    ap.add_argument("--weights", required=True)
    ap.add_argument("--out", required=True)
    for v in ("front", "left", "back", "right"):
        ap.add_argument("--" + v, required=True)
    ap.add_argument("--name", default="quad")
    ap.add_argument("--seeds", default="42")
    ap.add_argument("--steps", type=int, default=50)
    ap.add_argument("--guidance", type=float, default=5.0)
    ap.add_argument("--octree", type=int, default=380)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    os.environ["HY3DGEN_MODELS"] = str(Path(args.weights).resolve())
    sys.path.insert(0, str(Path(__file__).resolve().parent / "cv2_stub"))
    sys.path.insert(0, args.src)
    import torch
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        "Hunyuan3D-2mv", subfolder="hunyuan3d-dit-v2-mv", variant="fp16", use_safetensors=True, device=args.device,
        dtype=torch.float16 if args.device != "cpu" else torch.float32)
    print("pipeline loaded in %.1f s on %s" % (time.time() - t0, args.device), flush=True)
    for seed in [int(s) for s in args.seeds.split(",")]:
        images = {v: Image.open(getattr(args, v)).convert("RGBA") for v in ("front", "left", "back", "right")}
        t0 = time.time()
        mesh = pipe(image=images, num_inference_steps=args.steps, guidance_scale=args.guidance, octree_resolution=args.octree,
                    num_chunks=20000, generator=torch.manual_seed(seed), output_type="trimesh")[0]
        pos, tris = np.asarray(mesh.vertices, np.float32), np.asarray(mesh.faces, np.int64)
        stem = out / ("%s_s%d" % (args.name, seed))
        np.savez(str(stem) + ".npz", pos=pos, tris=tris)
        mesh.export(str(stem) + ".glb")
        print("%s seed %d: %d vertices, %d triangles, box %s .. %s, %.1f s" % (
            args.name, seed, len(pos), len(tris), pos.min(0).round(2), pos.max(0).round(2), time.time() - t0), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
