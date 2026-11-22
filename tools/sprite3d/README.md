# sprite -> 3D prototype helpers (lane `wereowl-3d`)

Prototype: turn a Median 2D monster sprite into a D2R HD model. Everything heavy (Blender, Real-ESRGAN, the 3D venv, model
weights, meshes) lives outside the repository (the art store and the machine's tool folders, see "Settings" below) and is
never committed.

| Script | Use |
|---|---|
| `dcc_frames.py` | Median/D2R DCC -> RGBA PNG frames (all 16 directions, palette from D2R `pal.dat`) |
| `texture_png.py` | D2R `.texture` (BC1/BC3/RGBA8) -> PNG through Pillow; format 62 is BC3 (not BC7) |
| `model_to_glb.py` | D2R `.model` -> GLB (bind pose + albedo), runs in the 3D venv (needs trimesh) |
| `render_glb.py` | `blender -b -P` 4-angle Workbench render strip of GLBs |
| `donor_info.py`, `extract_anims.py`, `ai/clip_survey.py` | skeleton bone counts and real clip names of the D2R enemy units |
| `rig_fit.py` | Wereowl mesh -> skinned to a D2R skeleton (profiles `wolf`, `goatman1`, `bear`, `hellbovine`): capsule weights, per-role unposing; used by `tools/wereowl_models.py` |
| `owl_hi.py`, `owl_retopo.py`, `owl_bake.py`, `owl_maps.py`, `owl_lods.py`, `owl_pose.py`, `bl_common.py`, `render_npz.py` | lane wereowl-mesh: high-poly clean-up, QuadriFlow retopology, normal / AO bake and albedo re-projection (Blender), maps to PNG, LOD collapse (pymeshlab), fit to the bear skeleton, Blender helpers, static Blender renders; commands in `docs/hd-wereowl-assets.md` |
| `morph_shots.py` | in game: a Druid casts Wereowl (`cast 1364 self`) and the form is screenshot (neutral / walk / run / attack / cast / get hit; `MXL_MORPH_DIRS=1` adds eight walk directions), background input, slot lock held by the caller |
| `ai/run_triposg.py`, `ai/diso_stub/` | TripoSG (MIT) one sprite view -> shape on local weights, offline; `diso` (CUDA only) replaced by a stand-in |
| `ai/run_hunyuan.py`, `ai/cv2_stub/` | Hunyuan3D-2mv front / left / back / right sprite views -> shape on local weights, offline. COMPARISON ONLY, never shipped (its licence excludes the EU, the UK and South Korea); OpenCV replaced by a stand-in |
| `render_soft.py` | software rasteriser (numba): grey or textured views of a mesh, also through a `cam_fit` camera; no Blender or GPU needed |
| `monster3d/` | lane hdtools-monster3d: the stage scripts of the Hardliner 3D test (section below) |

## Settings and Linux (lane m3dlinux, 2026-11-20)

The `monster3d/` scripts name no drive or user path. `monster3d/common.py` reads each setting from its environment variable,
else the git-ignored machine config (`machine.json`, `tools/localconfig.py`), else a default:

| Setting | machine.json key | Default |
|-|-|-|
| `MXL_M3D_DIR` (the lane's working folder EV: stages, shots, logs, `ART-MANIFEST.json`) | `m3d_dir` | `<runs folder>/hdtools/monster3d` |
| `MXL_ART_STORE` (large files, tool and weight trees) | `art_store` | none (an error names the setting when it is needed) |
| `MXL_BLENDER`, `MXL_REALESRGAN` | `blender`, `realesrgan` | Windows: the art store's trees; Linux: `blender` / `realesrgan-ncnn-vulkan` on PATH |
| `MXL_TRIPOSG_SRC`, `MXL_TRIPOSG_WEIGHTS`, `MXL_HUNYUAN_SRC`, `MXL_HUNYUAN_WEIGHTS` | `triposg_src`, ... | the art store's trees (`ART-MANIFEST.json` toolchain) |
| `MXL_M3D_DLL` (dev plugin for `g6_gamerun.py dll=1`) | `m3d_dll` | `<framework>/build/plugin/Release/mxl2012-core.dll` |

On Linux, `. /d2work/tools/env.sh` sets the tool variables (Blender 4.5.9, Real-ESRGAN 0.2.5.0, `$MXL_PY3D` = the ROCm torch
venv); GPU stages run as `sg render -c '...'` until the `render` group is active in the login. The GPU gate (`common.gpu_gate`)
reads the slot locks through `tools/game_slots.py` and, on Linux, the amdgpu load through `hdkit.gpugate.read_linux`
(Windows: the `GPU Engine` counter). `g6_gamerun.py` and its capture steps (`g6_deathcap.py`, `g6_movecap.py`) use the
game-check framework of this checkout (lane hdtools-monster's `mon_card` / `mon_turn` are merged here; `framework=<dir>` or
`MXL_M3D_FRAMEWORK` names another) and the slot backend `tools/game_slots.py` picks at run time: on Linux the game runs on a
private Xvfb display, the whole slot is snapshotted and restored, and the run's logs are read from `<run>/slot-logs-N/`.
A short Linux run (slot 5, 2 facings, HD and legacy) takes about 5 minutes:

```
MXL_M3D_TOKEN='2(' python tools/sprite3d/monster3d/g6_gamerun.py 5 <tag> <stage>/overlay check=mon_moves dll=<dev mxl2012-core.dll> MXL_MONTURN_KEYS=0,2
```

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

## Hardliner 3D test (lane hdtools-monster3d)
One 8-direction Median monster (token `~k`) from classic sprite to a skinned HD unit in game, all local. The working folder
(venv, weights, Blender, stages, shots) is outside the repository: `MXL_M3D_DIR`, default `mxl2012-runs/hdtools/monster3d`
(`monster3d/common.py`). Result and numbers: that folder's `REPORT.md`. GPU jobs go through `common.py`'s gate (no slot
locked, GPU idle).

| Stage script (`monster3d/`) | Does |
|---|---|
| `s1_frames.py` | classic frames of every mode, and the 8 standing directions 4x (Real-ESRGAN x4plus; decoder and upscaler are lane hdtools-monster's, copied into the working folder) |
| `ai/run_triposg.py`, `s2_clean.py`, `s2_candidates.py` | shapes from one view, cleaned; connected pieces listed (a loose axe is its own piece) |
| `s3_axemask.py` | sprites split into body and axe by colour (the blades are the only large grey area) |
| `s3_prep.py`, `cam_fit.py`, `project_texture.py`, `s3_albedo.py` | body upright at height 1 (`--asis` for a mesh that already is), sprite cameras, projected albedo, clean-up without repainting |
| `s3_axe.py` | the axe as its own rigid piece with a local frame (shaft along y, grip at the origin) and its own atlas strip |
| `s3_renderback.py` | render-back sheet: classic, 4x sprite, then each mesh through the fitted cameras with its per-direction IoU |
| `s4_lods.py` | body + axe, 5 LODs (Blender Decimate, UVs kept) |
| `s5_build.py` | skin to the Hell Bovine skeleton (`rig_fit` profile `hellbovine`), axe rigid on `R_hand_bind_jnt`, `.model` x5, textures, unit JSON as an overlay |
| `g6_gamerun.py`, `g6_contact.py`, `g6_strip.py` | overlay on a test slot under its lock with the two index files made from the installed mod, lane hdtools-monster's `mon_card` check, restore; contact sheet; comparison sheet |
| `casc_get.py` | named vanilla D2R files out of a test slot's CASC under its lock |

What the 8-direction case needs that the Wereowl did not:
- `cam_fit.py --ring 4,0,5,1,6,2,7,3 --front 4 --sign 1`: file directions of an 8-direction monster clockwise on screen.
  `--gen` names the directions the mesh was made from, `--yaw0` / `--span` steer the yaw search.
- A mesh from ONE sprite view is in that picture's frame, read as a level view: stretch y by 1/cos(30), turn it to face +z
  (`s3_prep.py`), then fit with `--elev 30 --ky 1.0`.
- `project_texture.py --ztol 0.02` for a mesh of height 1, `--trust P` to weight views by their silhouette IoU.
- The right-hand sprites (directions 2, 7, 3) are exact mirror silhouettes of the left-hand ones (1, 5, 0): a monster that
  holds something in one hand cannot match both sides, the IoU of the mirrored side stays near 0.5 for every mesh.
