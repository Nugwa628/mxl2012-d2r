#!/usr/bin/env python
"""Upscaled atlases for the classic-art HD maps (lane hdmaps2): Median's own .dt1 art made 4x for 4K screens.

The classic maps (tools/data/sprite_classic.json, docs/maps-hd.md "Classic maps") draw every tile from an atlas per tile
file (`<group>_atlas.png`) and one floor atlas per map (`<map>_floor_atlas.png`), at 1x: one classic pixel is about 2.4
screen pixels at 3840x2160 (blurry). `sprite_scene.py build --export DIR` writes those atlases and their tile tables
(`<name>_atlas.json`: atlas_xy and sprite_rect per tile); this tool makes a 4x picture of each, tile by tile, and
`sprite_scene.py build --albedo OUT` builds the map from them (any whole multiple of the atlas is accepted).

Per tile (the atlas's own padding is not trusted: each tile is cut out with its rectangle):
  colour  Real-ESRGAN x4 (realesrgan-x4plus, ncnn-vulkan build; MIT, models BSD-3-Clause) after the opaque colour is
          bled outward (tools/monster_upscale.py's pipeline, no dark halo). `dedither+` first was compared and smears the
          stone grain into flat patches, so it is not the default;
  floor   a floor tile (160 x 80 diamond) is upscaled inside a 3 x 3 lattice of itself (neighbours at (+-80, +-40)), so
          its edges are drawn as they continue into the next cell, not as an image border: no seam ring;
  alpha   Lanczos and a soft threshold (monster_upscale.alpha_up): crisp edges, one pixel of anti-aliasing. A floor
          tile whose alpha is the classic diamond gets the exact diamond at 4x instead (straight edges, half a classic
          pixel wider so neighbouring cells overlap and no gap shows), not the classic stair steps.
A whole atlas is then pasted at 4x; pixels outside every tile stay transparent (bled).
  colour  back-projected last (`backproject`): the 4x picture is corrected until its 4 x 4 averages give the classic
          pixels again, so the colours and the light painted into the tiles are Median's own and only the detail is the
          upscaler's (without it the floors' colour drifted, dE 1.7 -> 2.5 against classic over the 12 maps).

  python tools/maps_upscale.py atlas EXPORT_DIR OUT_DIR [--names a,b] [--method dedither+esrgan:realesrgan-x4plus]
                                                         [--esrgan EXE] [--scale 4]
  python tools/maps_upscale.py tile IN.png OUT.png [--floor] ...      one picture (tests, comparisons)
  python tools/maps_upscale.py backproject EXPORT_DIR UP_DIR OUT_DIR   back-projection on existing 4x atlases
  python tools/maps_upscale.py store DIR [--manifest tools/data/maps_classic_4x.json]   DIR's files into the art store
  python tools/maps_upscale.py fetch OUT [--manifest ...]              the manifest's files from the art store into OUT
                                                                       (then MXL2012_SPRITE_ALBEDO=OUT for the build)
The art store (/d2work/mxl2012-art, README.md there): one object per sha256 under objects/sha256/<2 hex>/, the manifest
lists name, sha256, size and origin; the repo's manifest is the one that counts, a copy goes to manifests/maps-classic-4x/.

EXE: env MXL_ESRGAN, else /d2work/tools/realesrgan-ncnn-vulkan-0.2.5.0/realesrgan-ncnn-vulkan.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401
import monster_upscale as mu  # noqa: E402

MANIFEST = Path(__file__).resolve().parent / "data" / "maps_classic_4x.json"
DEFAULT_EXE = "/d2work/tools/realesrgan-ncnn-vulkan-0.2.5.0/realesrgan-ncnn-vulkan"
DEFAULT_METHOD = "esrgan:realesrgan-x4plus"   # compared with dedither+ (smears the grain) and Lanczos: scratch/upcmp
FLOOR_W, FLOOR_H = 160, 80


def esrgan_cfg(exe=None, work=None):
    exe = exe or os.environ.get("MXL_ESRGAN") or DEFAULT_EXE
    if not Path(exe).is_file():
        raise SystemExit("maps_upscale: Real-ESRGAN exe not found: %s (env MXL_ESRGAN)" % exe)
    return {"exe": exe, "work": str(work or Path(projtemp.__file__).resolve().parent.parent / "work" / "tmp")}


def is_floor_tile(px: np.ndarray) -> bool:
    h, w = px.shape[:2]
    return abs(w - FLOOR_W) <= 1 and abs(h - FLOOR_H) <= 1


def diamond_alpha(h: int, w: int, scale: int, grow: float = 1.5) -> np.ndarray:
    """(h*scale, w*scale) uint8: the floor diamond inscribed in the tile's rectangle, edge anti-aliased over one pixel,
    `grow` classic pixels wider."""
    H, W = h * scale, w * scale
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2.0, H / 2.0
    d = np.abs(xx + 0.5 - cx) / (W / 2.0 + grow * scale) + np.abs(yy + 0.5 - cy) / (H / 2.0 + grow * scale / 2.0)
    edge = (1.0 - d) * (H / 2.0)            # distance inside, in output pixels (along y)
    return (np.clip(edge + 0.5, 0, 1) * 255).astype(np.uint8)


def is_diamond(px: np.ndarray) -> bool:
    """The tile's alpha is (nearly) the full floor diamond."""
    h, w = px.shape[:2]
    ideal = diamond_alpha(h, w, 1, 2.0) > 127      # classic diamonds are 4 px wider per row than the inscribed one
    got = px[..., 3] > 0
    return (got & ideal).sum() / max((got | ideal).sum(), 1) > 0.93


def lattice(px: np.ndarray) -> tuple:
    """A floor diamond inside a 3 x 3 lattice of itself -> (canvas rgba, (x, y) of the centre copy)."""
    h, w = px.shape[:2]
    H, W = h * 3, w * 3
    can = np.zeros((H, W, 4), np.uint8)
    cx, cy = w, h
    for a in (-2, -1, 0, 1, 2):
        for b in (-2, -1, 0, 1, 2):
            ox, oy = cx + (a + b) * (w // 2), cy + (a - b) * (h // 2)
            x0, y0, x1, y1 = max(ox, 0), max(oy, 0), min(ox + w, W), min(oy + h, H)
            if x0 >= x1 or y0 >= y1:
                continue
            src = px[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
            dst = can[y0:y1, x0:x1]
            m = (src[..., 3] > 0) & (dst[..., 3] == 0)
            dst[m] = src[m]
    return can, (cx, cy)


def up_tiles(tiles: list, scale: int, method: str, esrgan, floors: list) -> list:
    """[(h, w, 4)] -> each `scale` times larger; floors[i]: the lattice treatment for tile i."""
    jobs, crops = [], []
    for px, fl in zip(tiles, floors):
        if fl:
            can, (cx, cy) = lattice(px)
            jobs.append(can)
            crops.append((cx, cy, px.shape[1], px.shape[0]))
        else:
            jobs.append(px)
            crops.append(None)
    big = mu.upscale(jobs, scale, method, esrgan)
    out = []
    for b, c, px in zip(big, crops, tiles):
        if c is None:
            out.append(b)
            continue
        cx, cy, w, h = c
        col = b[cy * scale:(cy + h) * scale, cx * scale:(cx + w) * scale, :3]
        a = diamond_alpha(h, w, scale) if is_diamond(px) else mu.alpha_up(px[..., 3], scale)
        out.append(np.dstack([col, a]))
    return out


def _box_down(rgb: np.ndarray, w: np.ndarray, f: int) -> np.ndarray:
    """Alpha-weighted f x f averages of (H, W, 3) with weights (H, W)."""
    H, W = w.shape
    h, wd = H // f, W // f
    ws_ = w[:h * f, :wd * f].reshape(h, f, wd, f).sum((1, 3))
    acc = (rgb[:h * f, :wd * f] * w[:h * f, :wd * f, None]).reshape(h, f, wd, f, 3).sum((1, 3))
    plain = rgb[:h * f, :wd * f].reshape(h, f, wd, f, 3).mean((1, 3))
    return np.where(ws_[..., None] > 0, acc / np.maximum(ws_[..., None], 1e-6), plain)


def _up(err: np.ndarray, f: int) -> np.ndarray:
    from PIL import Image
    h, w = err.shape[:2]
    return np.dstack([np.asarray(Image.fromarray(err[..., c].astype(np.float32), "F").resize((w * f, h * f), Image.BICUBIC))
                      for c in range(err.shape[2])])


def backproject(big: np.ndarray, small: np.ndarray, iters: int = 3) -> np.ndarray:
    """big (H*f, W*f, 4) uint8, small (H, W, 4) uint8 -> big with its colour corrected so that its alpha-weighted f x f
    averages over small's opaque pixels equal small's colour; alpha unchanged."""
    f = big.shape[0] // small.shape[0]
    if f <= 1 or big.shape[1] // small.shape[1] != f:
        return big
    src = small[..., :3].astype(np.float32)
    known = (small[..., 3] > 0)[..., None]
    w = big[..., 3].astype(np.float32) / 255.0
    rgb = big[..., :3].astype(np.float32)
    for _ in range(iters):
        err = np.where(known, src - _box_down(rgb, w, f), 0.0)
        rgb += _up(err, f)
    return np.dstack([np.clip(rgb + 0.5, 0, 255).astype(np.uint8), big[..., 3]])


def upscale_atlas(png: Path, table: dict, scale: int, method: str, esrgan, log=print, batch: int = 64,
                  back: bool = True) -> np.ndarray:
    from PIL import Image
    atlas = np.array(Image.open(png).convert("RGBA"))
    H, W = atlas.shape[:2]
    out = np.zeros((H * scale, W * scale, 4), np.uint8)
    names = sorted(table["tiles"])
    t0 = time.time()
    for i in range(0, len(names), batch):
        chunk = names[i:i + batch]
        tiles, places = [], []
        for n in chunk:
            (ax, ay), r = table["tiles"][n]["atlas_xy"], table["tiles"][n]["sprite_rect"]
            w, h = r[2] - r[0], r[3] - r[1]
            px = atlas[ay:ay + h, ax:ax + w].copy()
            tiles.append(px)
            places.append((ax, ay))
        big = up_tiles(tiles, scale, method, esrgan, [is_floor_tile(p) for p in tiles])
        for (ax, ay), b in zip(places, big):
            out[ay * scale:ay * scale + b.shape[0], ax * scale:ax * scale + b.shape[1]] = b
        log("%s: %d/%d tiles (%.0f s)" % (png.name, min(i + batch, len(names)), len(names), time.time() - t0))
    rgb = mu.bleed(out, 8)                     # colour outside the tiles, for the mips (the material thresholds alpha)
    big = np.dstack([rgb, out[..., 3]]).astype(np.uint8)
    return backproject(big, atlas) if back else big


def store_root() -> Path:
    import hdkit_site
    root = os.environ.get("MXL_ART_STORE") or hdkit_site.store_root()
    if not Path(root, "README.md").is_file():
        raise SystemExit("maps_upscale: no art store at %s (set MXL_ART_STORE, e.g. /d2work/mxl2012-art)" % root)
    return Path(root)


def _sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def store(src: Path, manifest: Path, origin: dict, root: Path = None, log=print) -> dict:
    """Moves every file of `src` into the store (objects/sha256/xx/<hash>, checked by hash; a file already stored is removed
    from src once the stored copy's hash matches) and writes the manifest (repo) and its copy (store manifests/)."""
    import shutil
    root = root or store_root()
    files = []
    for f in sorted(p for p in Path(src).iterdir() if p.is_file()):
        h = _sha(f)
        obj = root / "objects" / "sha256" / h[:2] / h
        size = f.stat().st_size
        if not obj.exists():
            obj.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(f), str(obj))
            if _sha(obj) != h:
                raise SystemExit("maps_upscale: %s changed while it was stored" % obj)
        elif _sha(obj) == h:
            f.unlink()                     # already stored, its copy checked by hash (the store's rule): the duplicate goes
        files.append({"path": f.name, "sha256": h, "size": size})
    doc = {"about": "4x atlases of the classic-art maps (tools/maps_upscale.py, docs/maps-hd.md 'Classic maps at 4K'); "
                    "objects in the art store, `maps_upscale.py fetch OUT` puts them back", "origin": origin,
           "files": files}
    text = json.dumps(doc, indent=1) + "\n"
    Path(manifest).write_text(text, encoding="utf-8")
    copy = root / "manifests" / "maps-classic-4x" / Path(manifest).name
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(text, encoding="utf-8")
    log("stored %d files (%d MB)" % (len(files), sum(f["size"] for f in files) >> 20))
    return doc


def fetch(out: Path, manifest: Path, root: Path = None) -> int:
    import shutil
    root = root or store_root()
    out.mkdir(parents=True, exist_ok=True)
    doc = json.loads(Path(manifest).read_text(encoding="utf-8"))
    for f in doc["files"]:
        obj = root / "objects" / "sha256" / f["sha256"][:2] / f["sha256"]
        dest = out / f["path"]
        if not (dest.exists() and dest.stat().st_size == f["size"] and _sha(dest) == f["sha256"]):
            shutil.copyfile(obj, dest)
    return len(doc["files"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("atlas")
    a1.add_argument("export")
    a1.add_argument("out")
    a1.add_argument("--names", default="")
    for p in (a1,):
        p.add_argument("--method", default=DEFAULT_METHOD)
        p.add_argument("--esrgan", default=None)
        p.add_argument("--scale", type=int, default=4)
    a2 = sub.add_parser("tile")
    a2.add_argument("inp")
    a2.add_argument("out")
    a2.add_argument("--floor", action="store_true")
    a2.add_argument("--method", default=DEFAULT_METHOD)
    a2.add_argument("--esrgan", default=None)
    a2.add_argument("--scale", type=int, default=4)
    a3 = sub.add_parser("store")
    a3.add_argument("dir")
    a3.add_argument("--manifest", default=str(MANIFEST))
    a3.add_argument("--origin", default="{}", help="JSON: what made the files (tool, method, inputs)")
    a1.add_argument("--no-backproject", action="store_true")
    a5 = sub.add_parser("backproject")
    a5.add_argument("export")
    a5.add_argument("up")
    a5.add_argument("out")
    a4 = sub.add_parser("fetch")
    a4.add_argument("out")
    a4.add_argument("--manifest", default=str(MANIFEST))
    a = ap.parse_args(argv)
    if a.cmd == "store":
        store(Path(a.dir), Path(a.manifest), json.loads(a.origin))
        return 0
    if a.cmd == "backproject":
        from PIL import Image
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        for png in sorted(Path(a.up).glob("*_atlas.png")):
            small = np.array(Image.open(Path(a.export) / png.name).convert("RGBA"))
            big = np.array(Image.open(png).convert("RGBA"))
            Image.fromarray(backproject(big, small), "RGBA").save(out / png.name)
            print(png.name, flush=True)
        return 0
    if a.cmd == "fetch":
        print("fetched %d files to %s" % (fetch(Path(a.out), Path(a.manifest)), a.out))
        return 0
    from PIL import Image
    esr = esrgan_cfg(a.esrgan) if "esrgan" in a.method else None
    if esr:
        Path(esr["work"]).mkdir(parents=True, exist_ok=True)
    if a.cmd == "tile":
        px = np.array(Image.open(a.inp).convert("RGBA"))
        b = up_tiles([px], a.scale, a.method, esr, [a.floor])[0]
        Image.fromarray(b, "RGBA").save(a.out)
        return 0
    exp, out = Path(a.export), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    want = {n for n in a.names.split(",") if n}
    done = {}
    for js in sorted(exp.glob("*_atlas.json")):
        name = js.name[:-len("_atlas.json")]
        if want and name not in want:
            continue
        png = exp / (name + "_atlas.png")
        if not png.is_file():
            continue
        t0 = time.time()
        big = upscale_atlas(png, json.loads(js.read_text(encoding="utf-8")), a.scale, a.method, esr,
                            back=not a.no_backproject)
        Image.fromarray(big, "RGBA").save(out / png.name)
        done[name] = {"size": [big.shape[1], big.shape[0]], "seconds": round(time.time() - t0, 1)}
    (out / "upscale.json").write_text(json.dumps({"method": a.method, "scale": a.scale, "atlases": done}, indent=1),
                                      encoding="utf-8")
    print(json.dumps(done, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
