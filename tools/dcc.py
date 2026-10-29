"""DCC decoder (Diablo II's cell-compressed 8-bit animation format), used by tools/missile_art.py.

decode(data) -> list of directions; each direction is (x_min, y_min, width, height, frames) with
frames = list of (x_min, y_min, width, height, bytes of palette indices, 0 = transparent), the boxes in
direction space (y grows downwards, the origin is the animation's anchor).

Layout (per direction, LSB-first bit stream): header with the frame boxes, then the equal-cell, pixel-mask,
encoding-type and raw-pixel streams, then the pixel-code-and-displacement stream. Stage 1 decodes the four colours
of every 4x4 cell, stage 2 draws each frame's cells from them (the cell grid is aligned to the direction box).
"""
import struct

SIGNATURE = 0x74
BITS = (0, 1, 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, 26, 28, 30, 32)


class Bits:
    def __init__(self, data: bytes, pos: int = 0, end: int | None = None):
        self.data, self.pos = data, pos
        self.end = len(data) * 8 if end is None else end

    def take(self, n: int) -> "Bits":
        if self.pos + n > self.end:
            raise ValueError("DCC stream extends past the data")
        sub = Bits(self.data, self.pos, self.pos + n)
        self.pos += n
        return sub

    def read(self, n: int) -> int:
        if n == 0:
            return 0
        if self.pos + n > self.end:
            raise ValueError("DCC bit stream ended early")
        byte, shift = divmod(self.pos, 8)
        v = int.from_bytes(self.data[byte:byte + (shift + n + 7) // 8], "little")
        self.pos += n
        return (v >> shift) & ((1 << n) - 1)

    def read_signed(self, n: int) -> int:
        v = self.read(n)
        if n in (0, 32):
            return v - (1 << 32) if n == 32 and v >> 31 else v
        return (v ^ (1 << (n - 1))) - (1 << (n - 1))

    def remaining(self) -> int:
        return self.end - self.pos


def axis_cells(offset: int, length: int) -> list[int]:
    """Cell sizes along one axis for a span of `length` starting `offset` pixels into the direction box."""
    first = 4 - offset % 4
    if length <= first + 1:
        return [length]
    rem = length - first
    r = rem % 4
    if r == 0:
        return [first] + [4] * (rem // 4)
    if r == 1:
        return [first] + [4] * (rem // 4 - 1) + [5]
    return [first] + [4] * (rem // 4) + [r]


def decode_direction(data: bytes, frame_count: int):
    b = Bits(data)
    b.read(32)  # outsize_coded
    flags = b.read(2)
    code = [BITS[b.read(4)] for _ in range(7)]
    heads = []
    for _ in range(frame_count):
        heads.append(dict(
            var0=b.read(code[0]), w=b.read(code[1]), h=b.read(code[2]),
            x=b.read_signed(code[3]), y=b.read_signed(code[4]),
            optional=b.read(code[5]), coded=b.read(code[6]), bottom_up=b.read(1)))
    if any(h["optional"] for h in heads):
        b.pos = (b.pos + 7) // 8 * 8
        b.pos += 8 * sum(h["optional"] for h in heads)
    equal_size = b.read(20) if flags & 2 else 0
    mask_size = b.read(20)
    enc_size = raw_size = 0
    if flags & 1:
        enc_size, raw_size = b.read(20), b.read(20)
    values = [i for i in range(256) if b.read(1)]
    equal, mask, enc, raw = b.take(equal_size), b.take(mask_size), b.take(enc_size), b.take(raw_size)
    pcd = b.take(b.remaining())

    boxes = []
    for h in heads:
        if h["w"] == 0 or h["h"] == 0:
            raise ValueError("DCC frame without size")
        y = h["y"] if h["bottom_up"] else h["y"] - h["h"] + 1
        boxes.append((h["x"], y, h["w"], h["h"]))
    dx0 = min(x for x, _y, _w, _h in boxes)
    dy0 = min(y for _x, y, _w, _h in boxes)
    dw = max(x + w for x, _y, w, _h in boxes) - dx0
    dh = max(y + h for _x, y, _w, h in boxes) - dy0
    cw = -(-dw // 4)
    ch = -(-dh // 4)

    layouts = []
    for x, y, w, h in boxes:
        fx, fy = x - dx0, y - dy0
        cells, cy = [], fy
        for j, hh in enumerate(axis_cells(fy, h)):
            cx = fx
            for i, ww in enumerate(axis_cells(fx, w)):
                cells.append((cx, cy, ww, hh, (fy // 4 + j) * cw + fx // 4 + i))
                cx += ww
            cy += hh
        layouts.append(cells)

    popcount = [bin(i).count("1") for i in range(16)]
    latest = [None] * (cw * ch)
    queue = {}
    for f, cells in enumerate(layouts):
        for ci, (_x, _y, _w, _h, dcell) in enumerate(cells):
            prev = latest[dcell]
            if prev is not None:
                if equal_size and equal.read(1):
                    continue
                pm = mask.read(4)
            else:
                pm = 0xF
            n = popcount[pm]
            is_raw = n > 0 and enc_size > 0 and enc.read(1) == 1
            stack, last = [], 0
            for _ in range(n):
                if is_raw:
                    c = raw.read(8)
                else:
                    c = last
                    while True:
                        d = pcd.read(4)
                        c += d
                        if d != 15:
                            break
                    c &= 0xFF
                if c == last:
                    break
                stack.append(c)
                last = c
            old = prev or (0, 0, 0, 0)
            v = []
            for i in range(4):
                if pm & (1 << i):
                    v.append(stack.pop() if stack else 0)
                else:
                    v.append(old[i])
            latest[dcell] = tuple(v)
            queue[(f, ci)] = tuple(v)

    buf = bytearray(dw * dh)
    last_rect = [None] * (cw * ch)
    frames = []
    for f, cells in enumerate(layouts):
        bx, by, bw, bh = boxes[f]
        fx0, fy0 = bx - dx0, by - dy0
        out = bytearray(bw * bh)
        for ci, (cx, cy, w, h, dcell) in enumerate(cells):
            v = queue.get((f, ci))
            if v is not None:
                if v[0] == v[1]:
                    for y in range(cy, cy + h):
                        buf[y * dw + cx:y * dw + cx + w] = bytes([v[0]]) * w
                else:
                    nb = 1 if v[1] == v[2] else 2
                    for y in range(cy, cy + h):
                        for x in range(cx, cx + w):
                            buf[y * dw + x] = v[pcd.read(nb)]
            else:
                lr = last_rect[dcell]
                if lr is not None and lr[2] == w and lr[3] == h:
                    lx, ly = lr[0], lr[1]
                    tmp = [bytes(buf[y * dw + lx:y * dw + lx + w]) for y in range(ly, ly + h)]
                    for row, y in enumerate(range(cy, cy + h)):
                        buf[y * dw + cx:y * dw + cx + w] = tmp[row]
                else:
                    for y in range(cy, cy + h):
                        buf[y * dw + cx:y * dw + cx + w] = bytes(w)
            last_rect[dcell] = (cx, cy, w, h)
            for row in range(cy, cy + h):
                out[(row - fy0) * bw + (cx - fx0):(row - fy0) * bw + (cx - fx0) + w] = buf[row * dw + cx:row * dw + cx + w]
        pix = bytes(values[c] if c < len(values) else 0 for c in out)
        frames.append((bx, by, bw, bh, pix))
    return dx0, dy0, dw, dh, frames


def decode(data: bytes):
    if data[0] != SIGNATURE:
        raise ValueError("not a DCC file")
    dirs = data[2]
    fpd = struct.unpack_from("<I", data, 3)[0]
    offs = list(struct.unpack_from(f"<{dirs}I", data, 15)) + [len(data)]
    return [decode_direction(data[offs[d]:offs[d + 1]], fpd) for d in range(dirs)]
