"""Pixel decoder for .dt1 tiles (palette indices per tile), for tools/map_tint.py.

A tile's pixels sit in blocks of 32 x 32 (header of 20 bytes each at the tile's block pointer): x, y (int16), unused (int16),
grid x / y (uint8), format (int16), length (int32), unused (int16), data offset from the block pointer (int32). Format 1 is an
isometric floor block (15 rows of 4, 8, ... 32 ... 4 pixels, 256 bytes); any other format is run-length: byte pairs (skip,
count) followed by `count` pixels, (0, 0) ends the row. Index 0 is transparent.
"""
import struct

BLOCK_HEADER = 20
ISO_X = (14, 12, 10, 8, 6, 4, 2, 0, 2, 4, 6, 8, 10, 12, 14)
ISO_N = (4, 8, 12, 16, 20, 24, 28, 32, 28, 24, 20, 16, 12, 8, 4)


def block_pixels(fmt: int, data: bytes):
    """-> [(x, y, index)] of one block, positions relative to the block."""
    out = []
    if fmt == 1:
        i = 0
        for y, (x0, n) in enumerate(zip(ISO_X, ISO_N)):
            for x in range(x0, x0 + n):
                if i < len(data):
                    out.append((x, y, data[i]))
                i += 1
        return out
    i = x = y = 0
    while i + 1 < len(data):
        skip, n = data[i], data[i + 1]
        i += 2
        if skip == 0 and n == 0:
            x, y = 0, y + 1
            continue
        x += skip
        for k in range(n):
            if i + k < len(data):
                out.append((x + k, y, data[i + k]))
        x += n
        i += n
    return out


def tiles(data: bytes):
    """-> {(orientation, style, sequence): [(x, y, index)]} for every tile of a .dt1 (the first tile of a key wins; rarity
    variants of one key share their look closely enough for colour statistics). Positions are block offset + pixel."""
    count, ptr = struct.unpack_from("<ii", data, 0x10C)
    out = {}
    for t in range(count):
        o = ptr + t * 96
        orient, main, sub = struct.unpack_from("<iii", data, o + 20)
        bptr, blen, nblocks = struct.unpack_from("<iii", data, o + 72)
        key = (orient, main, sub)
        if key in out:
            continue
        px = []
        for b in range(nblocks):
            h = bptr + b * BLOCK_HEADER
            if h + BLOCK_HEADER > len(data):
                break
            bx, by, _u, _gx, _gy, fmt, length, _u2, off = struct.unpack_from("<hhhBBhihi", data, h)
            start = bptr + off
            for x, y, c in block_pixels(fmt, data[start:start + length]):
                px.append((bx + x, by + y, c))
        out[key] = px
    return out
