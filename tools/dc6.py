"""DC6 pictures and D2R HD sprites (adapted from another port's skill_icons.py and item_art.py).

DC6: 1 direction, N frames of (w, h, offx, offy, encoded block); a frame is stored bottom-up, 0x80 ends a line, a byte
with the high bit set skips that many transparent pixels, else it is a run of palette indexes.
D2R .sprite, version 31 ('SpA1', as Spells/*Skillicon and the HD inventory items): u16 31, u16 frame width, u32 strip
width, u32 height, u32 0, u32 frames, u32 0, u32 0, u32 data size, u32 4, then the RGBA strip (frames side by side).
Skill icon sheets: frame width = stride - 2 (D2R's 130/132); item pictures: one frame, frame width = width.
Pure Python, no third-party packages.
"""
import struct
import zlib
from pathlib import Path

Rows = list  # list of rows, a row is a list of (r, g, b, a)
HEADER = 40
MAX_STRIP = 16384  # D2R's texture limit for the strip width


def read_dc6(path: Path) -> list[tuple[int, int, int, int, bytes]]:
    """Frames as (width, height, offx, offy, encoded block) of a 1-direction DC6."""
    return parse_dc6(Path(path).read_bytes())


def parse_dc6(d: bytes) -> list[tuple[int, int, int, int, bytes]]:
    _ver, _flags, _enc, _term, dirs, fpd = struct.unpack_from("<6I", d, 0)
    ptrs = struct.unpack_from(f"<{dirs * fpd}I", d, 24)
    frames = []
    for p in ptrs:
        _flip, w, h, ox, oy, _unk, _next, length = struct.unpack_from("<8i", d, p)
        frames.append((w, h, ox, oy, d[p + 32:p + 32 + length]))
    return frames


def build_dc6(frames: list[tuple[int, int, int, int, bytes]]) -> bytes:
    """A DC6 file from frames (used by the tests)."""
    head = struct.pack("<6I", 6, 1, 0, 0xEEEEEEEE, 1, len(frames))
    offset = 24 + 4 * len(frames)
    ptrs, blobs = [], []
    for w, h, ox, oy, block in frames:
        ptrs.append(offset)
        blob = struct.pack("<8i", 0, w, h, ox, oy, 0, 0, len(block)) + block + b"\xee\xee\xee"
        blobs.append(blob)
        offset += len(blob)
    return head + struct.pack(f"<{len(ptrs)}I", *ptrs) + b"".join(blobs)


UNUSED = range(225, 255)  # palette indices D2R's units palette has black (Diablo II's act palettes: per-act colours)


def decode_frame(w: int, h: int, block: bytes, pal: list[tuple[int, int, int]], fill: bool = False) -> Rows:
    """RGBA rows top to bottom (pixels the run-length skips pass over are transparent). `fill`: pixels on palette indices
    225-254 (UNUSED: black in D2R's units palette, act-dependent colours in Diablo II's act palettes; 34 of Median's item
    pictures and 7 skill icon sheets draw a few) take the mean colour of their other opaque 8-neighbours instead
    (fill_unused), so the HD picture has no black specks."""
    rows = [[(0, 0, 0, 0)] * w for _ in range(h)]
    holes = []
    x, y, i = 0, h - 1, 0
    while i < len(block) and y >= 0:
        b = block[i]
        i += 1
        if b == 0x80:
            x, y = 0, y - 1
        elif b & 0x80:
            x += b & 0x7F
        else:
            for c in block[i:i + b]:
                if 0 <= x < w:
                    r, g, bl = pal[c]
                    rows[y][x] = (r, g, bl, 255)
                    if fill and c in UNUSED:
                        holes.append((x, y))
                x += 1
            i += b
    if holes:
        fill_unused(rows, holes)
    return rows


def fill_unused(rows: Rows, holes: list[tuple[int, int]], rounds: int = 4) -> None:
    """Each hole (x, y; opaque) gets the mean colour of its opaque 8-neighbours that are not holes; holes with only hole
    neighbours are filled in later rounds from the filled ones (a hole left after `rounds` keeps its colour)."""
    h, w = len(rows), len(rows[0]) if rows else 0
    todo = set(holes)
    for _ in range(rounds):
        done = {}
        for x, y in todo:
            acc, n = [0, 0, 0], 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx, ny = x + dx, y + dy
                    if (dx or dy) and 0 <= nx < w and 0 <= ny < h and (nx, ny) not in todo and rows[ny][nx][3]:
                        p = rows[ny][nx]
                        acc[0], acc[1], acc[2], n = acc[0] + p[0], acc[1] + p[1], acc[2] + p[2], n + 1
            if n:
                done[x, y] = (round(acc[0] / n), round(acc[1] / n), round(acc[2] / n), 255)
        for (x, y), p in done.items():
            rows[y][x] = p
        todo -= set(done)
        if not todo or not done:
            break


def palette(path: Path) -> list[tuple[int, int, int]]:
    """The units palette (pal.dat, 256 x BGR) as RGB."""
    d = Path(path).read_bytes()
    return [(d[i * 3 + 2], d[i * 3 + 1], d[i * 3]) for i in range(256)]


def scale(rows: Rows, out_w: int, out_h: int, factor: float) -> Rows:
    """Bilinear scale by `factor` (premultiplied alpha so edges do not go dark), centred on a transparent
    out_w x out_h canvas (cropped when it does not fit)."""
    h, w = len(rows), (len(rows[0]) if rows else 0)
    sw, sh = round(w * factor), round(h * factor)
    ox, oy = (out_w - sw) // 2, (out_h - sh) // 2
    blank = (0, 0, 0, 0)
    out = [[blank] * out_w for _ in range(out_h)]
    if not w or not h:
        return out
    xs = []  # per output column: (x0, x1, fx)
    for x in range(sw):
        sx = min(max((x + 0.5) / factor - 0.5, 0), w - 1)
        x0 = int(sx)
        xs.append((x0, min(x0 + 1, w - 1), sx - x0))
    for y in range(sh):
        ty = y + oy
        if not 0 <= ty < out_h:
            continue
        sy = min(max((y + 0.5) / factor - 0.5, 0), h - 1)
        y0 = int(sy)
        fy = sy - y0
        r0, r1 = rows[y0], rows[min(y0 + 1, h - 1)]
        line = out[ty]
        for x, (x0, x1, fx) in enumerate(xs):
            tx = x + ox
            if not 0 <= tx < out_w:
                continue
            r = g = b = a = 0.0
            for p, wt in ((r0[x0], (1 - fx) * (1 - fy)), (r0[x1], fx * (1 - fy)), (r1[x0], (1 - fx) * fy),
                          (r1[x1], fx * fy)):
                if p[3]:
                    k = wt * p[3] / 255
                    r += p[0] * k
                    g += p[1] * k
                    b += p[2] * k
                    a += k
            if a > 0:
                line[tx] = (round(r / a), round(g / a), round(b / a), min(255, round(a * 255)))
    return out


def strip(images: list[Rows], stride: int, height: int) -> bytes:
    """Frames side by side, each in a stride-wide cell, RGBA bytes row by row."""
    out = bytearray()
    for y in range(height):
        for img in images:
            line = img[y] if y < len(img) else []
            for x in range(stride):
                out += bytes(line[x]) if x < len(line) else b"\0\0\0\0"
    return bytes(out)


def sprite_bytes(frame_width: int, strip_width: int, height: int, frames: int, rgba: bytes) -> bytes:
    return b"SpA1" + struct.pack("<HHIIIIIIII", 31, frame_width, strip_width, height, 0, frames, 0, 0,
                                 len(rgba), 4) + rgba


def write_sheet_sprite(path: Path, images: list[Rows], stride: int, height: int) -> None:
    """Skill icon sheet: frame width is stride - 2, like D2R's 130 (stride 132)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sprite_bytes(stride - 2, stride * len(images), height, len(images),
                                  strip(images, stride, height)))


def write_item_sprite(path: Path, width: int, height: int, rgba: bytes) -> None:
    """One frame, frame width = width."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sprite_bytes(width, width, height, 1, rgba))


def sprite_info(path: Path) -> dict:
    d = Path(path).read_bytes()
    if d[:4] != b"SpA1" or len(d) < HEADER:
        raise ValueError(f"{path}: not a sprite")
    ver, fw, sw, h, _z, frames = struct.unpack_from("<HHIIII", d, 4)
    size = struct.unpack_from("<I", d, 32)[0]
    return {"version": ver, "frame_width": fw, "strip_width": sw, "height": h, "frames": frames,
            "data_size": size, "file_size": len(d)}


def read_sprite(path: Path) -> list[Rows]:
    """Frames of a version-31 RGBA .sprite as written here (each frame_width wide, the sheet stride is the strip
    width / frames)."""
    d = Path(path).read_bytes()
    info = sprite_info(path)
    sw, h, frames, fw = info["strip_width"], info["height"], info["frames"], info["frame_width"]
    if len(d) < HEADER + sw * h * 4:
        raise ValueError(f"{path}: truncated")
    data = d[HEADER:HEADER + sw * h * 4]
    stride = sw // frames
    out = []
    for i in range(frames):
        rows = []
        for y in range(h):
            base = (y * sw + i * stride) * 4
            rows.append([tuple(data[base + x * 4:base + x * 4 + 4]) for x in range(fw)])
        out.append(rows)
    return out


def write_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    raw = b"".join(b"\0" + rgba[y * width * 4:(y + 1) * width * 4] for y in range(height))

    def chunk(t: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body) & 0xFFFFFFFF)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def stats(rows: Rows) -> tuple[float, float, float, float]:
    """(opaque fraction, mean premultiplied R, G, B) over all pixels: a cheap fingerprint that scaling keeps."""
    n = sum(len(r) for r in rows) or 1
    a = r = g = b = 0
    for row in rows:
        for p in row:
            a += p[3]
            r += p[0] * p[3]
            g += p[1] * p[3]
            b += p[2] * p[3]
    return a / 255 / n, r / 255 / n, g / 255 / n, b / 255 / n
