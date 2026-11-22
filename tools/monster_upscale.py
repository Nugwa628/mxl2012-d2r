#!/usr/bin/env python
"""Upscaling a classic monster frame for an HD card (lane hdtools-monster): the pipeline and a method comparison sheet.

A frame is palette art with a hard 1-bit edge. The pipeline keeps colour and coverage apart:

  colour    the opaque pixels' colour is first pushed outward into the transparent ones (bleed), so no method ever mixes the
            sprite with a background colour (no dark or grey halo). Then one of METHODS makes it `scale` times larger.
  alpha     always Lanczos, then a soft threshold (SOFT wide around one half): a clean edge that still has a pixel of
            anti-aliasing, whatever the colour method does.

METHODS: nearest, lanczos, hq4x (the hqx pixel-art scaler; needs the `hqx` package), esrgan:<model> (Real-ESRGAN's ncnn
build, a local exe: the models of its release are realesrgan-x4plus, realesrgan-x4plus-anime, realesr-animevideov3),
and any of them after `dedither+` (a small bilateral filter over the colour first: it takes the 1-pixel palette dither away
before the scaler turns it into texture) or before `+shape` (the silhouette too is drawn by the scaler, see upscale()).

  py -3 tools/monster_upscale.py compare OUT.png --token "~k" --frames NU:0,A1:7,WL:4 --dir 4 --esrgan EXE [--methods ...]
  py -3 tools/monster_upscale.py flicker --token "~k" --mode NU --dir 4 --method esrgan:realesrgan-x4plus --esrgan EXE
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401
import monster_sheet  # noqa: E402

SOFT = 0.15                 # half the width of the alpha threshold's ramp
PAD = 8                     # bled pixels round a frame given to a scaler (its filters need a neighbourhood)
MODEL_SCALE = 4             # what the Real-ESRGAN models make; other scales are a Lanczos resize of that
DEFAULT_METHODS = ("nearest", "lanczos", "hq4x", "esrgan:realesrgan-x4plus", "esrgan:realesrgan-x4plus-anime",
                   "esrgan:realesr-animevideov3", "dedither+esrgan:realesrgan-x4plus")


def bleed(rgba: np.ndarray, steps: int = PAD + 4) -> np.ndarray:
    """(h, w, 3): the colour of the opaque pixels, pushed `steps` pixels outward into the transparent ones."""
    rgb = rgba[..., :3].astype(np.float32)
    known = rgba[..., 3] > 0
    rgb[~known] = 0
    for _ in range(steps):
        if known.all():
            break
        total = np.zeros_like(rgb)
        count = np.zeros(known.shape, np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            k = np.roll(known, (dy, dx), (0, 1))
            c = np.roll(rgb, (dy, dx), (0, 1))
            if dy == 1:
                k[0], c[0] = False, 0
            elif dy == -1:
                k[-1], c[-1] = False, 0
            if dx == 1:
                k[:, 0], c[:, 0] = False, 0
            elif dx == -1:
                k[:, -1], c[:, -1] = False, 0
            total += c * k[..., None]
            count += k
        new = (count > 0) & ~known
        rgb[new] = total[new] / count[new][:, None]
        known = known | new
    return np.clip(rgb + 0.5, 0, 255).astype(np.uint8)


def alpha_up(alpha: np.ndarray, scale: int, soft: float = SOFT) -> np.ndarray:
    """The coverage, `scale` times larger: Lanczos, then a smooth step from 0.5 - soft to 0.5 + soft."""
    from PIL import Image
    h, w = alpha.shape
    if scale == 1:
        return alpha
    big = np.asarray(Image.fromarray(alpha, "L").resize((w * scale, h * scale), Image.LANCZOS)).astype(np.float32) / 255.0
    return _step(big, soft)


def dedither(rgb: np.ndarray) -> np.ndarray:
    """A small edge-keeping blur: the palette's 1-pixel dither goes, outlines stay."""
    src = rgb.astype(np.float32)
    total = np.zeros_like(src)
    weight = np.zeros(src.shape[:2] + (1,), np.float32)
    edge = np.pad(src, ((2, 2), (2, 2), (0, 0)), mode="edge")
    h, w = src.shape[:2]
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            near = edge[2 + dy:2 + dy + h, 2 + dx:2 + dx + w]
            k = np.exp(-(dy * dy + dx * dx) / (2 * 1.6 ** 2) - ((near - src) ** 2).sum(-1, keepdims=True) / (2 * 28.0 ** 2))
            total += near * k
            weight += k
    return np.clip(total / weight + 0.5, 0, 255).astype(np.uint8)


def _hq4x(rgb: np.ndarray) -> np.ndarray:
    import types
    import PIL
    from PIL import Image
    if "PIL.PyAccess" not in sys.modules:           # hqx 1.0 imports a module newer Pillows no longer have (a type only)
        shim = types.ModuleType("PIL.PyAccess")
        shim.PyAccess = object
        sys.modules["PIL.PyAccess"] = PIL.PyAccess = shim
    import hqx
    return np.asarray(hqx.hq4x(Image.fromarray(rgb, "RGB")).convert("RGB"))


def _esrgan(rgbs: list, model: str, esrgan: dict) -> list:
    """Every image through the Real-ESRGAN exe in one call (4 times larger). esrgan: {"exe": path, "work": folder}."""
    from PIL import Image
    exe = Path(esrgan["exe"])
    with tempfile.TemporaryDirectory(dir=str(esrgan.get("work") or exe.parent)) as tmp:
        src, dst = Path(tmp) / "in", Path(tmp) / "out"
        src.mkdir()
        dst.mkdir()
        for i, rgb in enumerate(rgbs):
            Image.fromarray(rgb, "RGB").save(src / ("%04d.png" % i))
        subprocess.run([str(exe), "-i", str(src), "-o", str(dst), "-n", model, "-s", str(MODEL_SCALE), "-f", "png"], check=True,
                       cwd=str(exe.parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        out = []
        for i in range(len(rgbs)):
            with Image.open(dst / ("%04d.png" % i)) as im:
                out.append(np.asarray(im.convert("RGB")))
        return out


def colour_up(rgbs: list, scale: int, method: str, esrgan=None) -> list:
    """Opaque colour images, each `scale` times larger by `method`."""
    from PIL import Image
    if method.startswith("dedither+"):
        return colour_up([dedither(r) for r in rgbs], scale, method[len("dedither+"):], esrgan)
    if scale == 1:
        return list(rgbs)
    if method in ("nearest", "lanczos"):
        flt = Image.NEAREST if method == "nearest" else Image.LANCZOS
        return [np.asarray(Image.fromarray(r, "RGB").resize((r.shape[1] * scale, r.shape[0] * scale), flt)) for r in rgbs]
    if method == "hq4x":
        big = [_hq4x(r) for r in rgbs]
    elif method.startswith("esrgan:"):
        if not esrgan:
            raise ValueError("%s needs the Real-ESRGAN exe" % method)
        big = _esrgan(rgbs, method.split(":", 1)[1], esrgan)
    else:
        raise ValueError("no method %r" % method)
    if scale == MODEL_SCALE:
        return big
    return [np.asarray(Image.fromarray(b, "RGB").resize((r.shape[1] * scale, r.shape[0] * scale), Image.LANCZOS))
            for b, r in zip(big, rgbs)]


def _step(x: np.ndarray, soft: float = SOFT) -> np.ndarray:
    t = np.clip((x - (0.5 - soft)) / (2 * soft), 0.0, 1.0)
    return np.clip(t * t * (3 - 2 * t) * 255 + 0.5, 0, 255).astype(np.uint8)


def upscale(frames: list, scale: int, method: str, esrgan=None, shape: bool = False) -> list:
    """(h, w, 4) frames -> (h * scale, w * scale, 4): bled colour by `method`, alpha by alpha_up. `shape`: the alpha too
    goes through the method (as a white-on-black picture) before the threshold: a scaler that redraws outlines then also
    rounds the classic stair steps of the silhouette."""
    if scale == 1:
        return list(frames)
    method, shape = (method[:-len("+shape")], True) if method.endswith("+shape") else (method, shape)
    padded = [np.pad(f, ((PAD, PAD), (PAD, PAD), (0, 0))) for f in frames]
    colours = colour_up([bleed(p) for p in padded], scale, method, esrgan)
    cut = PAD * scale
    if shape and method not in ("nearest", "lanczos"):
        masks = colour_up([np.repeat(p[..., 3:4], 3, 2) for p in padded], scale, method.replace("dedither+", ""), esrgan)
        alphas = [_step(m[cut:-cut, cut:-cut].astype(np.float32).mean(-1) / 255.0) for m in masks]
    else:
        alphas = [alpha_up(f[..., 3], scale) for f in frames]
    return [np.dstack([c[cut:-cut, cut:-cut], a]) for c, a in zip(colours, alphas)]


def over(rgba: np.ndarray, grey: int) -> np.ndarray:
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    return np.clip(rgba[..., :3] * a + grey * (1 - a) + 0.5, 0, 255).astype(np.uint8)


def clip_frames(token: str, mode: str, d: int, act: int = 1) -> list:
    """Every frame of one mode and direction on the mode's common box (the frames stay in register)."""
    entry = monster_sheet.load(token, [mode.lower()])[mode.lower()]
    box = monster_sheet.mode_box(entry)
    pal = monster_sheet.act_palette(act)
    return [np.asarray(monster_sheet.compose(entry, d, f, box, pal)) for f in range(entry["cof"]["frames"])]


def trimmed(rgba: np.ndarray, margin: int = 2) -> np.ndarray:
    ys, xs = np.nonzero(rgba[..., 3])
    y0, y1 = max(ys.min() - margin, 0), min(ys.max() + 1 + margin, rgba.shape[0])
    x0, x1 = max(xs.min() - margin, 0), min(xs.max() + 1 + margin, rgba.shape[1])
    return rgba[y0:y1, x0:x1]


def compare(out: Path, token: str, picks, d: int, methods, esrgan=None, act: int = 1, scale: int = 4, greys=(128, 24)) -> dict:
    """The sheet: one row per picked frame and background, one column per method, all at the same final size."""
    from PIL import Image, ImageDraw, ImageFont
    frames = [trimmed(clip_frames(token, mode, d, act)[f]) for mode, f in picks]
    cols, times = [], {}
    for m in methods:
        t0 = time.time()
        if m == "nearest":
            cols.append([np.repeat(np.repeat(f, scale, 0), scale, 1) for f in frames])      # the classic picture itself
        else:
            cols.append(upscale(frames, scale, m, esrgan))
        times[m] = round((time.time() - t0) / len(frames), 3)
    gap, head = 10, 34
    cw = max(f.shape[1] for f in frames) * scale
    rows = [(f.shape[0] * scale, g) for g in greys for f in frames]
    sheet = Image.new("RGB", (gap + len(methods) * (cw + gap), head + sum(h + gap for h, _ in rows)), (12, 12, 12))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    labels = {"nearest": "classic 1x (nearest)", "lanczos": "Lanczos 4x", "hq4x": "hq4x (pixel-art scaler)"}
    for c, m in enumerate(methods):
        text = labels.get(m, m.replace("esrgan:", "Real-ESRGAN ").replace("dedither+", "de-dither + ").replace("+shape", " + shape"))
        draw.text((gap + c * (cw + gap), 8), text, fill=(235, 235, 235), font=font)
    y = head
    for r, (h, g) in enumerate(rows):
        for c in range(len(methods)):
            tile = cols[c][r % len(frames)]
            box = Image.new("RGB", (cw, h), (g, g, g))
            box.paste(Image.fromarray(over(tile, g)), ((cw - tile.shape[1]) // 2, 0))
            sheet.paste(box, (gap + c * (cw + gap), y))
        y += h + gap
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return {"sheet": str(out), "size": sheet.size, "seconds_per_frame": times,
            "frames": ["%s:%d" % p for p in picks], "frame_px": [list(f.shape[1::-1]) for f in frames]}


def flicker(token: str, mode: str, d: int, method: str, esrgan=None, act: int = 1, scale: int = 4, strip: Path = None) -> dict:
    """How much a whole clip shimmers after `method`, against the same clip by Lanczos (which invents nothing).
    change: mean |frame - previous| over a mid-grey background (0-255); invented: mean | (method - Lanczos) -
    the same of the previous frame |, the part of the change the method adds; still: that over the pixels whose classic
    source did not change within 3 pixels between the two frames (a still part of the monster that flickers)."""
    from PIL import Image
    frames = clip_frames(token, mode, d, act)
    t0 = time.time()
    mine = [over(f, 128).astype(np.float32) for f in upscale(frames, scale, method, esrgan)]
    seconds = (time.time() - t0) / len(frames)
    plain = [over(f, 128).astype(np.float32) for f in upscale(frames, scale, "lanczos")]
    change, base, invented, still = [], [], [], []
    for i in range(1, len(frames)):
        change.append(np.abs(mine[i] - mine[i - 1]).mean())
        base.append(np.abs(plain[i] - plain[i - 1]).mean())
        extra = np.abs((mine[i] - plain[i]) - (mine[i - 1] - plain[i - 1]))
        invented.append(extra.mean())
        moved = (frames[i].astype(np.int16) != frames[i - 1].astype(np.int16)).any(-1)
        wide = moved.copy()
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                wide |= np.roll(moved, (dy, dx), (0, 1))
        quiet = np.repeat(np.repeat(~wide & (frames[i][..., 3] > 0), scale, 0), scale, 1)
        if quiet.any():
            still.append(extra[quiet].mean())
    if strip:
        Image.fromarray(np.hstack([m.astype(np.uint8) for m in mine])).save(strip)
    return {"mode": mode, "dir": d, "frames": len(frames), "method": method, "seconds_per_frame": round(seconds, 3),
            "change": round(float(np.mean(change)), 3), "change_lanczos": round(float(np.mean(base)), 3),
            "invented": round(float(np.mean(invented)), 3), "still": round(float(np.mean(still)), 3) if still else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("out")
    c.add_argument("--frames", default="NU:0,A1:7,WL:4")
    c.add_argument("--methods", default=",".join(DEFAULT_METHODS))
    f = sub.add_parser("flicker")
    f.add_argument("--mode", default="NU")
    f.add_argument("--method", default="esrgan:realesrgan-x4plus")
    f.add_argument("--strip")
    for p in (c, f):
        p.add_argument("--token", required=True)
        p.add_argument("--dir", type=int, default=4)
        p.add_argument("--act", type=int, default=1)
        p.add_argument("--esrgan", help="realesrgan-ncnn-vulkan.exe")
        p.add_argument("--work", help="folder for the exe's temporary files")
    a = ap.parse_args(argv)
    esrgan = {"exe": a.esrgan, "work": a.work} if a.esrgan else None
    if a.cmd == "compare":
        picks = [(m, int(n)) for m, n in (x.split(":") for x in a.frames.split(","))]
        methods = [m for m in a.methods.split(",") if esrgan or "esrgan" not in m]
        rep = compare(Path(a.out), a.token, picks, a.dir, methods, esrgan, a.act)
    else:
        rep = flicker(a.token, a.mode, a.dir, a.method, esrgan, a.act, strip=Path(a.strip) if a.strip else None)
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
