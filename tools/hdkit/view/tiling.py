"""Images larger than one GPU texture: tile plans, a streamed PNG writer, seam windows.

An orthographic camera cuts into tiles exactly (camera.OrthoCamera.matrix of each pixel rectangle), so an image of any size
is a grid of tiles of at most `tile` px. Rows of tiles are written to the PNG as they finish, so memory holds one row of
tiles, not the image. `seam_windows` lists small windows across every inner tile edge; rendering such a window in one
pass and comparing it with the stitched image measures the seam numerically.
"""
import struct
import zlib

import numpy as np


def plan(width: int, height: int, tile: int) -> list:
    """[(x0, y0, w, h)] covering width x height in row-major order, each at most tile x tile."""
    if width <= 0 or height <= 0 or tile <= 0:
        raise ValueError("width, height and tile must be positive")
    out = []
    for y0 in range(0, height, tile):
        for x0 in range(0, width, tile):
            out.append((x0, y0, min(tile, width - x0), min(tile, height - y0)))
    return out


def rows(tiles) -> list:
    """The plan grouped by tile row: [[(x0, y0, w, h), ...], ...]."""
    out, cur, y = [], [], None
    for t in tiles:
        if t[1] != y and cur:
            out.append(cur)
            cur = []
        y = t[1]
        cur.append(t)
    if cur:
        out.append(cur)
    return out


def seam_windows(width: int, height: int, tile: int, half: int = 8, every: int | None = None) -> list:
    """Windows (x0, y0, w, h) of 2*half px across each inner tile edge, clipped to the image: one at the middle of each
    tile's edge, or with `every` one each `every` px along every edge."""
    out = []

    def along(n0, length):
        if every:
            return list(range(n0 + every // 2, n0 + length, every))
        return [n0 + length // 2]
    for x in range(tile, width, tile):
        for y0 in range(0, height, tile):
            for cy in along(y0, min(tile, height - y0)):
                out.append((x - half, max(0, cy - half), 2 * half, min(2 * half, height - max(0, cy - half))))
    for y in range(tile, height, tile):
        for x0 in range(0, width, tile):
            for cx in along(x0, min(tile, width - x0)):
                out.append((max(0, cx - half), y - half, min(2 * half, width - max(0, cx - half)), 2 * half))
    return out


def stitch(tiles_and_pixels, width: int, height: int, channels: int = 4, dtype=np.uint8) -> np.ndarray:
    """One array from [((x0, y0, w, h), pixels)] (small images only: tests and seam checks)."""
    out = np.zeros((height, width, channels), dtype)
    for (x0, y0, w, h), px in tiles_and_pixels:
        out[y0:y0 + h, x0:x0 + w] = px
    return out


class PngStream:
    """Write an 8-bit RGBA (or RGB) PNG row by row: header now, rows as they come, `close()` ends it."""

    def __init__(self, path, width: int, height: int, channels: int = 4, level: int = 6):
        if channels not in (3, 4):
            raise ValueError("channels must be 3 or 4")
        self.f = open(path, "wb")
        self.w, self.h, self.c = width, height, channels
        self.done = 0
        self.z = zlib.compressobj(level)
        self.f.write(b"\x89PNG\r\n\x1a\n")
        self._chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6 if channels == 4 else 2, 0, 0, 0))

    def _chunk(self, kind: bytes, data: bytes):
        self.f.write(struct.pack(">I", len(data)) + kind + data)
        self.f.write(struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    def write(self, block: np.ndarray):
        """block: (n, width, channels) uint8, the next n rows."""
        block = np.ascontiguousarray(block, np.uint8)
        if block.ndim != 3 or block.shape[1] != self.w or block.shape[2] != self.c:
            raise ValueError("block must be (n, %d, %d), got %s" % (self.w, self.c, block.shape))
        if self.done + block.shape[0] > self.h:
            raise ValueError("more rows than the image has")
        raw = np.zeros((block.shape[0], 1 + self.w * self.c), np.uint8)
        raw[:, 1:] = block.reshape(block.shape[0], -1)       # filter type 0 per row
        data = self.z.compress(raw.tobytes())
        if data:
            self._chunk(b"IDAT", data)
        self.done += block.shape[0]

    def close(self):
        if self.done != self.h:
            raise ValueError("PNG closed after %d of %d rows" % (self.done, self.h))
        self._chunk(b"IDAT", self.z.flush())
        self._chunk(b"IEND", b"")
        self.f.close()
