"""A .dt1 tile set decoded to palette-index images, with every header field the map viewer shows.

Tile header (96 bytes, table at the dword 0x110, count at 0x10C): direction i32, roof height i16, sound u8, animated u8,
height i32, width i32, unused i32, orientation i32, main index ("style") i32, sub index ("sequence") i32, rarity / frame
i32, unknown 4 bytes, 25 sub-tile flags (40..64), unused, block table pointer i32 (72), block data length i32, block count
i32. Blocks (20 bytes): x i16, y i16, unused i16, grid x u8, grid y u8, format i16 (1 = isometric 32x15 floor block, else
run-length), length i32, unused i16, data offset i32 (from the block table). Index 0 is transparent (tools/dt1_pixels.py
decodes the same blocks to pixel lists).

Image frame. A floor tile's blocks lie at y 0..80 below the top corner of its diamond; any other tile's blocks are given
from the tile's bottom (y negative upwards), so they are drawn 80 px lower: the map renderer puts a tile's block (x, y) at
(cell top corner x - 80 + x, cell top corner y + y + (0 if floor else 80)); a roof is lifted by its roof height instead.
(OpenDiablo2 d2maprenderer: YAdjust = min block y + 80, roofs -RoofHeight.)

Sub-tile flags (one byte per sub-tile, 5 x 5 per tile): bit 0 blocks walking, 1 blocks light and line of sight, 2 blocks
jumping/teleport, 3 blocks players but not mercenaries, 5 blocks light only; others unknown. Byte index of sub-tile
(sx, sy) of the cell = (4 - sy) * 5 + sx (OpenDiablo2's subtileLookup).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

ISO_X = (14, 12, 10, 8, 6, 4, 2, 0, 2, 4, 6, 8, 10, 12, 14)
ISO_N = (4, 8, 12, 16, 20, 24, 28, 32, 28, 24, 20, 16, 12, 8, 4)
_ISO_YS = np.concatenate([np.full(n, y) for y, n in enumerate(ISO_N)])
_ISO_XS = np.concatenate([np.arange(x, x + n) for x, n in zip(ISO_X, ISO_N)])

FLOOR, LEFT, RIGHT, NC_RIGHT, NC_LEFT, LEFT_END, RIGHT_END, SOUTH, LEFT_DOOR, RIGHT_DOOR = range(10)
SPECIAL1, SPECIAL2, PILLAR, SHADOW, TREE, ROOF = 10, 11, 12, 13, 14, 15
LOWER = (16, 17, 18, 19)
UPPER = (1, 2, 3, 4, 5, 6, 7, 8, 9, 12, 14)
ORIENT_NAMES = {0: "floor", 1: "left wall", 2: "right wall", 3: "north corner, right part", 4: "north corner, left part",
                5: "left end wall", 6: "right end wall", 7: "south corner", 8: "left wall with door",
                9: "right wall with door", 10: "special 1", 11: "special 2", 12: "pillar / standalone", 13: "shadow",
                14: "tree", 15: "roof", 16: "lower left wall", 17: "lower right wall", 18: "lower north corner",
                19: "lower south corner"}
FLAG_NAMES = {0: "block_walk", 1: "block_light_los", 2: "block_jump", 3: "block_player", 5: "block_light"}


def subtile_index(sx: int, sy: int) -> int:
    return (4 - sy) * 5 + sx


@dataclass
class Tile:
    index: int
    orientation: int
    main: int
    sub: int
    rarity: int
    roof_height: int
    height: int
    width: int
    direction: int
    animated: int
    flags: bytes
    blocks: list = field(default_factory=list)     # (x, y, format, bytes)
    _img: tuple | None = None

    @property
    def key(self):
        return (self.orientation, self.main, self.sub)

    def image(self):
        """(index image uint8 HxW, x0, y0): the tile's pixels, (x0, y0) the block offset of the image's top-left."""
        if self._img is None:
            self._img = decode(self.blocks, self.orientation == FLOOR)
        return self._img

    def flag_grid(self) -> np.ndarray:
        """5x5 [sy, sx] sub-tile flags in cell order."""
        g = np.zeros((5, 5), np.uint8)
        for sy in range(5):
            for sx in range(5):
                g[sy, sx] = self.flags[subtile_index(sx, sy)] if len(self.flags) == 25 else 0
        return g


def decode(blocks, floor: bool):
    if not blocks:
        return np.zeros((1, 1), np.uint8), 0, 0
    boxes = []
    for x, y, fmt, _d in blocks:
        h = 15 if fmt == 1 else 32
        boxes.append((x, y, x + 32, y + h))
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    img = np.zeros((y1 - y0 + 32, x1 - x0), np.uint8)
    for x, y, fmt, d in blocks:
        bx, by = x - x0, y - y0
        if fmt == 1:
            n = min(len(d), 256)
            if n:
                img[by + _ISO_YS[:n], bx + _ISO_XS[:n]] = np.frombuffer(d[:n], np.uint8)
            continue
        i = cx = cy = 0
        L = len(d)
        while i + 1 < L:
            skip, n = d[i], d[i + 1]
            i += 2
            if skip == 0 and n == 0:
                cx, cy = 0, cy + 1
                continue
            cx += skip
            if n:
                seg = d[i:i + n]
                yy, xx = by + cy, bx + cx
                if 0 <= yy < img.shape[0] and xx + len(seg) <= img.shape[1]:
                    img[yy, xx:xx + len(seg)] = np.frombuffer(seg, np.uint8)
                cx += n
                i += n
    rows = np.nonzero(img.any(1))[0]
    img = img[:rows.max() + 1] if len(rows) else img[:1]
    return img, x0, y0


def parse(data: bytes, with_blocks: bool = True) -> list:
    if len(data) < 0x114:
        raise ValueError("dt1 too short")
    v1, _v2 = struct.unpack_from("<ii", data, 0)
    if v1 != 7:
        raise ValueError("dt1 version %d" % v1)
    count, ptr = struct.unpack_from("<ii", data, 0x10C)
    if count < 0 or ptr < 0 or ptr + count * 96 > len(data):
        raise ValueError("dt1 tile table runs past the end of the file")
    out = []
    for t in range(count):
        o = ptr + t * 96
        direction, roof_h, _snd, anim, height, width, _u = struct.unpack_from("<ihBBiii", data, o)
        orient, main, sub, rarity = struct.unpack_from("<iiii", data, o + 20)
        flags = data[o + 40:o + 65]
        bptr, blen, nblocks = struct.unpack_from("<iii", data, o + 72)
        tile = Tile(t, orient, main, sub, rarity, roof_h, height, width, direction, anim, flags)
        if with_blocks and 0 <= bptr and nblocks > 0 and bptr + nblocks * 20 <= len(data):
            for b in range(nblocks):
                h = bptr + b * 20
                bx, by, _u0, _gx, _gy, fmt, length, _u2, off = struct.unpack_from("<hhhBBhihi", data, h)
                s = bptr + off
                if 0 <= s and s + length <= len(data) and length >= 0:
                    tile.blocks.append((bx, by, fmt, data[s:s + length]))
        out.append(tile)
    return out


def synthetic(tiles) -> bytes:
    """A .dt1 for tests. tiles: dicts orientation, main, sub, [rarity, roof_height, flags (25 bytes)], blocks:
    [(x, y, format, bytes)]."""
    head = bytearray(struct.pack("<ii", 7, 6)) + b"\0" * (0x10C - 8)
    n = len(tiles)
    ptr = 0x114
    head += struct.pack("<ii", n, ptr)
    table = bytearray()
    blob = bytearray()
    blocks_at = ptr + 96 * n
    hdrs = []
    for t in tiles:
        bl = t.get("blocks", [])
        hdr_part = bytearray()
        data_part = bytearray()
        for (x, y, fmt, d) in bl:
            hdr_part += struct.pack("<hhhBBhihi", x, y, 0, 0, 0, fmt, len(d), 0, 20 * len(bl) + len(data_part))
            data_part += d
        hdrs.append((blocks_at + len(blob), len(hdr_part) + len(data_part), len(bl)))
        blob += hdr_part + data_part
    for t, (bp, blen, nb) in zip(tiles, hdrs):
        rec = bytearray(96)
        struct.pack_into("<ihBBiii", rec, 0, 0, t.get("roof_height", 0), 0, 0, t.get("height", -80), t.get("width", 160), 0)
        struct.pack_into("<iiii", rec, 20, t["orientation"], t["main"], t["sub"], t.get("rarity", 0))
        fl = t.get("flags", b"\0" * 25)
        rec[40:65] = fl
        struct.pack_into("<iii", rec, 72, bp, blen, nb)
        table += rec
    return bytes(head + table + blob)


def rle_block(rows) -> bytes:
    """Run-length block bytes for rows of (skip, [indices]) lists: [[(skip, [i, ...]), ...], ...]."""
    out = bytearray()
    for row in rows:
        for skip, px in row:
            out += bytes((skip, len(px))) + bytes(px)
        out += b"\0\0"
    return bytes(out)
