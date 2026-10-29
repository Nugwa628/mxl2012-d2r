"""Shared helpers for the D2R-XL 2012 downloader art generators (Python 3 + Pillow + numpy).

The panel and the icon are procedural: noise and gradients made here, no source images. The background is the
owner's art (launcher/res/ART.md) and has no generator. The fonts the downloader ships
(launcher/res/RobotoCondensed.ttf, exocet.ttf) are used only by the mock-up preview.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO = Path(__file__).resolve().parents[2]


def font_dir(arg: str | None = None) -> Path:
    """Folder with RobotoCondensed.ttf / exocet.ttf: --fonts, $MXL_LAUNCHER_RES, else <repo>/launcher/res."""
    for cand in (arg, os.environ.get("MXL_LAUNCHER_RES"), str(REPO / "launcher" / "res")):
        if cand and (Path(cand) / "RobotoCondensed.ttf").is_file():
            return Path(cand)
    sys.exit("RobotoCondensed.ttf not found: pass --fonts <folder with the launcher's res fonts>")


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def fbm(w: int, h: int, seed: int, base: int = 4, octaves: int = 5, persistence: float = 0.5) -> np.ndarray:
    """Fractal value noise in 0..1, shape (h, w), made by summing bicubic-upscaled random grids."""
    r = rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gw, gh = max(2, base * 2**o), max(2, int(base * 2**o * h / w) + 1)
        g = Image.fromarray(r.random((gh, gw)).astype(np.float32), "F")
        out += amp * np.asarray(g.resize((w, h), Image.BICUBIC), np.float32)
        tot += amp
        amp *= persistence
    out /= tot
    lo, hi = out.min(), out.max()
    return (out - lo) / (hi - lo + 1e-9)



def blur(a: np.ndarray, radius: float) -> np.ndarray:
    """Gaussian blur of a float 2D array in 0..1 (via an 8-bit L image: plenty for masks and glows)."""
    im = Image.fromarray(np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(im, np.float32) / 255.0


def over(dst: np.ndarray, color, alpha: np.ndarray) -> np.ndarray:
    """dst (h,w,3 float 0..255) <- color over dst with per-pixel alpha (h,w). Color is a tuple or an (h,w,3) array."""
    a = alpha[..., None]
    c = np.asarray(color, np.float32)
    return dst * (1 - a) + c * a


def add(dst: np.ndarray, color, intensity: np.ndarray) -> np.ndarray:
    """Additive light: dst + color * intensity."""
    return dst + np.asarray(color, np.float32) * intensity[..., None]
