# sprite -> 3D prototype helpers (lane `wereowl-3d`)

Prototype: turn a Median 2D monster sprite into a D2R HD model. Everything heavy (Blender, Real-ESRGAN, the 3D venv, model
weights, meshes) lives under `D:\mxl-3d\` and is never committed.

| Script | Use |
|---|---|
| `dcc_frames.py` | Median/D2R DCC -> RGBA PNG frames (all 16 directions, palette from D2R `pal.dat`) |
| `texture_png.py` | D2R `.texture` (BC1/BC3/RGBA8) -> PNG through Pillow; format 62 is BC3 (not BC7) |
| `model_to_glb.py` | D2R `.model` -> GLB (bind pose + albedo), runs in the 3D venv (needs trimesh) |
| `render_glb.py` | `blender -b -P` 4-angle Workbench render strip of GLBs |
| `donor_info.py`, `extract_anims.py`, `ai/clip_survey.py` | skeleton bone counts and real clip names of the D2R enemy units |
| `rig_fit.py` | Wereowl mesh -> skinned to a D2R skeleton (profiles `wolf`, `goatman1`): capsule weights, per-role unposing; used by `tools/wereowl_models.py` |
| `owl_hi.py`, `owl_retopo.py`, `owl_bake.py`, `owl_maps.py`, `owl_lods.py`, `owl_pose.py`, `bl_common.py`, `render_npz.py` | lane wereowl-mesh: high-poly clean-up, QuadriFlow retopology, normal / AO bake and albedo re-projection (Blender), maps to PNG, LOD collapse (pymeshlab), fit to the bear skeleton, Blender helpers, static Blender renders; commands in `docs/hd-wereowl-assets.md` |
| `morph_shots.py` | in game: a Druid casts Wereowl (`cast 1364 self`) and the form is screenshot (neutral / walk / run / attack / cast / get hit; `MXL_MORPH_DIRS=1` adds eight walk directions), background input, slot lock held by the caller |
| `ai/run_hunyuan.py`, `ai/run_triposg.py`, `ai/diso_stub.py` | Hunyuan3D-2 (mv / mini) and TripoSG shape generation on local weights (copies of what ran from `D:\mxl-3d\scripts`) |

Environment notes (RX 9070 XT, Windows, build of 2026-10-22):
- Python 3.12 venv, AMD wheels from `repo.radeon.com/rocm/windows/rocm-rel-7.2.1/` (torch 2.9.1+rocm7.2.1); works with the installed
  driver 32.0.31041.1004, `torch.cuda.is_available()` is True.
- Hunyuan3D-2 needs `transformers<5` (5.x renamed the DINOv2 attention weights and the checkpoint no longer loads) and
  `diffusers<0.36`.
- TripoSG imports `diso` (CUDA extension). `ai/diso_stub.py` is a stand-in; run with `use_flash_decoder=False` (skimage marching cubes).
- Not installed: the Hunyuan texture stage (CUDA rasterizer), `diso`, `rembg`, `gradio`.

## Sprite direction ring (Median 16-direction DCCs)
Found by sprite-to-sprite similarity (`ai/ring.py`): angular order is `0 9 5 10 1 11 6 12 2 13 7 14 3 15 4 8`, 22.5 degrees per step.
Four steps = 90 degrees, so Hunyuan2mv's (front, left, back, right) quads are `4,5,6,7` (best), `8,10,12,14`, `0,1,2,3`, `9,11,13,15`.
Experiment (lane wereowl-3d): the rotated quads, extra seeds, voxel-voting ensembles and a vertical 1/cos(30) stretch of the inputs
did not beat `4,5,6,7`; the other 12 directions are for texturing and checking, not for more shape passes.

## Texture bake (step 3): 16 sprite directions -> albedo
Run in the 3D venv (numpy, scipy, PIL, trimesh, pymeshlab, numba, xatlas; the last two are `pip install`s, not committed).
```
cam_fit.py        mesh.npz  views_x4/  cameras.json --elev 30 --ky 1.0     # silhouette fit of the 16 sprite cameras
project_texture.py mesh.npz cameras.json views_x4/ out/                    # atlas + bake: out/albedo.png, out/mesh_uv.npz
obj_npz.py to_obj out/mesh_uv.npz lod0.obj --uv; blender -b -P unwrap.py -- lod0.obj out/lodset --keep-uv; obj_npz.py to_npz out/mesh_lods.npz out/lodset_lod{0..4}.obj
make_textures.py  out/albedo.png  <data dir>  data/hd/character/enemy/pig/textures/pig   # .texture set over unused vanilla paths
npz_glb.py out/mesh_uv.npz out/albedo.png out/tex.glb; blender -b -P render_tex.py -- out/tex.glb showcase/tex_iso --n 8 --elev 30
```
Method: sprite directions sit on the ring (above) 22.5 degrees apart with 4 = front, so the camera azimuths are known; cam_fit
refines them with a shared yaw offset (the generated mesh is turned about 10 degrees), one scale and offset per sprite, by
silhouette overlap (mean IoU 0.79 at 30 degrees elevation, 0.80 at 20: the mesh was made from eye-level views, the fit does not
distinguish them). Camera model: orthographic, `px = tx + s p.r`, `py = ty - s ky p.u`. Sign of the ring direction: +1 (IoU 0.79
against 0.63).
Atlas: every face takes the camera that sees it best (facing x visibility from a depth buffer of the mesh in that camera, probes
kept 6 px inside the sprite), the labels are smoothed over face adjacency and pieces below 40 faces merged, so a chart is the surface
one camera sees and its UVs are that camera's screen coordinates; xatlas only packs (194 charts, 2048 px). Texels are sampled
bilinearly from the sprite (next best cameras where the first does not see the texel); the rest is filled from the nearest sampled
texel. Blender's Smart UV Project shatters the bumpy generated mesh into thousands of islands (unwrap.py keeps that path for other
meshes); xatlas's own charting gives ~1200, so charts come from the cameras instead.
