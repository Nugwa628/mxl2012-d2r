"""Mesh .npz (pos, nrm, uv, tris) + albedo PNG -> textured GLB for a quick look (3D venv, trimesh).

    npz_glb.py <mesh.npz> <albedo.png> <out.glb> [--suffix _1]

uv runs down the image (v = row / height), as D2R textures do.
"""
import sys

import numpy as np
import trimesh
from PIL import Image

a = sys.argv[1:]
sfx = a[a.index("--suffix") + 1] if "--suffix" in a else ""
d = np.load(a[0])
uv = np.array(d["uv" + sfx], float)
uv[:, 1] = 1 - uv[:, 1]  # trimesh flips v on export (glTF v runs down, trimesh's runs up)
mat = trimesh.visual.material.PBRMaterial(baseColorTexture=Image.open(a[1]).convert("RGB"), metallicFactor=0.0, roughnessFactor=0.9)
m = trimesh.Trimesh(d["pos" + sfx], d["tris" + sfx], vertex_normals=d["nrm" + sfx], process=False,
                    visual=trimesh.visual.TextureVisuals(uv=uv, material=mat))
m.export(a[2])
print(a[2], len(m.vertices), "verts")
