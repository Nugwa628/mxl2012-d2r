"""The classic side: a monster mode composited from its COF layers and DCC/DC6 parts, coloured through an act PL2.

Reused: tools/dcc.py (`decode`: DCC directions and frames), tools/dc6.py is not needed for monsters with DCC parts,
tools/legacy_art.py (`COMPS`, the COF composite order, and `parse_cof` as the size check), tools/palshift.py (the PL2
row layout: 1024-byte palette, then 256-byte rows: 32 light levels, 16 light tables, 5 x 256 blend rows, 111 colour
shift tables from row 1328).
Layer order and blends after Reimagined D2R Mod Studio (MIT, @ea1a969) `src/ModStudio.Core/Cof.cs`: per direction and
frame the COF lists the composite ids in draw order; a layer is blended only when its transparent byte (offset 3) is
set, DrawEffect 0/1/2 = 25/50/75 % opacity, 3/4 = additive, 5 = normal. Speed is the u32 at offset 24 (256 = one
frame per game frame at 25 fps).

The palette is the PL2's own (RGBA bytes, the same colours as pal.dat's BGR). `light` 0..31 picks a light-level row
(31 = full, 0 = black); it is a parameter, not a fitted night look (calibration).
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_TOOLS = Path(__file__).resolve().parents[2]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
import dcc  # noqa: E402
import legacy_art  # noqa: E402

COMPS = legacy_art.COMPS
PL2_PALETTE = 1024
LIGHT_LEVELS = 32


@dataclass
class Layer:
    comp: str
    shadow: bool
    transparent: bool
    effect: int
    wclass: str


@dataclass
class Cof:
    layers: list
    dirs: int
    frames: int
    speed: int
    events: bytes
    order: list            # [dir][frame] -> [composite codes] in draw order

    @property
    def fps(self) -> float:
        return 25.0 * self.speed / 256.0

    @property
    def seconds(self) -> float:
        return self.frames / self.fps if self.fps > 0 else 0.0

    def layer(self, comp: str) -> Layer | None:
        return next((l for l in self.layers if l.comp == comp), None)


def read_cof(b: bytes) -> Cof:
    legacy_art.parse_cof(b)                       # size and composite checks
    n, frames, dirs = b[0], b[1], b[2]
    speed = struct.unpack_from("<I", b, 24)[0]
    layers = []
    for i in range(n):
        o = 28 + 9 * i
        layers.append(Layer(COMPS[b[o]], b[o + 1] != 0, b[o + 3] != 0, b[o + 4],
                            b[o + 5:o + 9].split(b"\0")[0].decode("latin-1").lower()))
    o = 28 + 9 * n
    events = b[o:o + frames]
    o += frames
    order = [[[COMPS[c] for c in b[o + (d * frames + f) * n:o + (d * frames + f) * n + n]] for f in range(frames)]
             for d in range(dirs)]
    return Cof(layers, dirs, frames, speed if 0 < speed <= 4096 else 256, events, order)


class Pl2:
    def __init__(self, data: bytes):
        self.data = data
        self.palette = np.frombuffer(data[:PL2_PALETTE], np.uint8).reshape(256, 4)[:, :3].copy()

    def row(self, r: int) -> np.ndarray:
        o = PL2_PALETTE + r * 256
        return np.frombuffer(self.data[o:o + 256], np.uint8)

    def rgb(self, idx: np.ndarray, light: int = LIGHT_LEVELS - 1) -> np.ndarray:
        """Palette indices -> RGB through light-level row `light` (0..31)."""
        lut = self.palette[self.row(max(0, min(LIGHT_LEVELS - 1, int(light))))]
        return lut[idx]


def part_path(root: Path, token: str, comp: str, style: str, mode: str, wclass: str) -> Path:
    """data/global/monsters/<tok>/<comp>/<tok><comp><style><mode><wclass>.dcc, as the game names a monster part."""
    return Path(root) / token / comp / ("%s%s%s%s%s.dcc" % (token, comp, style, mode, wclass))


def composite(root: Path, token: str, mode: str, direction: int, frame: int, pl2: Pl2, styles: dict | None = None,
              light: int = LIGHT_LEVELS - 1):
    """RGBA (H, W, 4) uint8 of one classic frame, its origin pixel (x, y) in that image, and notes.
    root: the monsters folder; styles: composite -> style code (default "lit")."""
    root = Path(root)
    cof = read_cof((root / token / "cof" / ("%s%shth.cof" % (token, mode))).read_bytes())
    d, f = direction % cof.dirs, frame % cof.frames
    parts, notes = [], []
    for comp in cof.order[d][f]:
        lay = cof.layer(comp)
        p = part_path(root, token, comp, (styles or {}).get(comp, "lit"), mode, lay.wclass)
        if not p.exists():
            notes.append("missing part %s" % p.name)
            continue
        x0, y0, dw, dh, frames = dcc.decode(p.read_bytes())[d]
        fx, fy, fw, fh, pix = frames[f % len(frames)]
        idx = np.frombuffer(pix, np.uint8).reshape(fh, fw)
        parts.append((fx, fy, idx, lay))
    if not parts:
        return np.zeros((1, 1, 4), np.uint8), (0, 0), notes
    xa = min(p[0] for p in parts)
    ya = min(p[1] for p in parts)
    xb = max(p[0] + p[2].shape[1] for p in parts)
    yb = max(p[1] + p[2].shape[0] for p in parts)
    rgb = np.zeros((yb - ya, xb - xa, 3), float)
    alpha = np.zeros((yb - ya, xb - xa), float)
    for fx, fy, idx, lay in parts:
        sl = (slice(fy - ya, fy - ya + idx.shape[0]), slice(fx - xa, fx - xa + idx.shape[1]))
        m = idx != 0
        col = pl2.rgb(idx, light).astype(float)
        dst = rgb[sl]
        if lay.transparent and lay.effect in (3, 4):
            dst[m] = np.minimum(dst[m] + col[m], 255.0)
            alpha[sl][m] = np.maximum(alpha[sl][m], 1.0)
        else:
            op = {0: 0.25, 1: 0.5, 2: 0.75}.get(lay.effect, 1.0) if lay.transparent else 1.0
            dst[m] = (1 - op) * dst[m] + op * col[m]
            alpha[sl][m] = np.maximum(alpha[sl][m], op)
        if lay.transparent:
            notes.append("layer %s drawn with effect %d" % (lay.comp, lay.effect))
    out = np.dstack([rgb, alpha * 255.0]).round().clip(0, 255).astype(np.uint8)
    return out, (-xa, -ya), notes
