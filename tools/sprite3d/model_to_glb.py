"""D2R .model -> GLB (bind pose, albedo texture), to look at a donor monster in Blender / a viewer.

    <3d venv python> -I tools/sprite3d/model_to_glb.py <unit dir> <out.glb> [model name, default torso_lod0.model ...]
    (the unit dir is a directory extracted like data/hd/character/enemy/<unit>; textures are looked up by file name in
    <unit dir>/textures, then in ../*/textures)

Needs trimesh + numpy + Pillow (the 3D venv). Vertex decode follows docs/hd-models.md: position = int16 / 32767 * VertexScale.
"""
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_model as dm  # noqa: E402
import texture_png  # noqa: E402


def find_texture(unit_dir: Path, ref: str) -> Path | None:
    name = Path(ref).name.lower()
    for base in [unit_dir / "textures", *sorted(unit_dir.parent.glob("*/textures"))]:
        if base.is_dir():
            for p in base.iterdir():
                if p.name.lower() == name:
                    return p
    return None


def meshes_of(path: Path, unit_dir: Path):
    tree = dm.parse_tree(dm.Gr2File.read(path.read_bytes()))
    for mesh in tree["Meshes"]:
        vd = mesh["PrimaryVertexData"]["Vertices"].obj
        if not vd or "Position" not in vd[0].f:
            continue
        scale = float(mesh["ExtendedData"].obj.f.get("VertexScale", 1.0)) if mesh["ExtendedData"] is not None else 1.0
        pos = np.array([v["Position"][:3] for v in vd], np.float64) / 32767.0 * scale
        uv = np.array([v["TextureCoordinates0"] for v in vd], np.float32)
        topo = mesh["PrimaryTopology"]
        if topo["Indices16"]:
            idx = np.array([i["Int16"] for i in topo["Indices16"]], np.int64) & 0xFFFF
        else:
            idx = np.array([i["Int32"] for i in topo["Indices"]], np.int64)
        idx = idx.reshape(-1, 3)
        groups = topo["Groups"] or []
        mats = [b["Material"] for b in mesh["MaterialBindings"]]
        parts = groups or [None]
        for g in parts:
            first, cnt = (g["TriFirst"], g["TriCount"]) if g is not None else (0, len(idx))
            mat = mats[g["MaterialIndex"]] if g is not None and g["MaterialIndex"] < len(mats) else (mats[0] if mats else None)
            tex = None
            if mat is not None:
                for mp in mat["Maps"]:
                    if mp["Usage"] == "AlbedoTexture" and mp["Map"].get("Texture"):
                        tex = mp["Map"]["Texture"]["FromFileName"]
            yield mesh["Name"], pos, uv, idx[first:first + cnt], mat["Name"] if mat else "", tex


def main():
    unit_dir = Path(sys.argv[1])
    out = Path(sys.argv[2])
    names = sys.argv[3:] or ["torso_lod0.model"]
    scene = trimesh.Scene()
    cache: dict = {}
    for n in names:
        for mname, pos, uv, tris, matname, tex in meshes_of(unit_dir / n, unit_dir):
            uv = uv.astype(np.float64).copy()
            uv[:, 1] = 1.0 - uv[:, 1]  # glTF has v down
            vis = None
            if tex:
                tp = find_texture(unit_dir, tex)
                if tp is not None:
                    if tp not in cache:
                        try:
                            cache[tp] = texture_png.to_image(tp).convert("RGB")
                        except Exception:
                            cache[tp] = None
                    if cache[tp] is not None:
                        vis = trimesh.visual.TextureVisuals(uv=uv, material=trimesh.visual.material.PBRMaterial(
                            baseColorTexture=cache[tp], metallicFactor=0.0, roughnessFactor=0.9))
            m = trimesh.Trimesh(pos, tris, process=False)
            if vis is not None:
                m.visual = vis
            scene.add_geometry(m, geom_name=f"{n}:{mname}:{matname}")
    scene.export(out)
    print("wrote", out, "geometries", len(scene.geometry))


if __name__ == "__main__":
    main()
