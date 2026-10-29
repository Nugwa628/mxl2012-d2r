"""Writer (and a small reader) for D2R's HD .texture files, used for the sprite effects of tools/missile_art.py.

Layout (little endian): "<DE(" magic; u32 = format | 2 << 16 | mips << 24; width; height; 1; 0; 0; mips; 4; then per
mip a (size, offset) pair, the offset counted from its own field to the mip's data (so the data follows the table
directly, largest mip first). Formats seen in D2R's own files:
  0x3f (63)  BC4, one 8-bit channel (masks, flipbook frames), 8 bytes per 4x4 block, at least 8 bytes per mip
  0x1f (31)  RGBA8, 4 bytes per pixel (gradients; red, green, blue, alpha)
  0x3e (62)  BC3 / DXT5, sRGB (albedo)
  0x3d (61)  BC3 / DXT5 data read as linear (normal and ORM maps; found 2026-10-23 by decoding D2R's own werebear maps as DXT5:
             the normal map is DXT5nm, red 255, green = normal y, blue 0, alpha = normal x; the ORM map is red = occlusion,
             green = roughness, blue = metal (0), alpha 255. Earlier notes called 61 BC5; BC5 data under 61 decodes as a
             wrong normal (green 16 = a normal tilted by 60 degrees) and drew a whole body black)
The other codes (65: 8 bits per pixel, probably BC7; 58: BC1) are not written here.
"""
import struct

import numpy as np

FMT_BC4 = 0x3F
FMT_RGBA8 = 0x1F
FMT_BC3 = 0x3E  # 62: DXT5 colour maps (albedo), sRGB
FMT_BC3_LIN = 0x3D  # 61: DXT5 data decoded linearly (normal, ORM maps)


def mip_chain(a: np.ndarray, levels: int) -> list[np.ndarray]:
    """Box-filtered mip levels of an (h, w) or (h, w, c) uint8 image with even sides (down to 1 pixel)."""
    out = [a]
    for _ in range(levels - 1):
        h, w = a.shape[:2]
        if h < 2 or w < 2:
            break
        f = a.astype(np.float32).reshape(h // 2, 2, w // 2, 2, *a.shape[2:]).mean(axis=(1, 3))
        a = np.clip(np.rint(f), 0, 255).astype(np.uint8)
        out.append(a)
    return out


def bc4_encode(a: np.ndarray) -> bytes:
    """BC4 (one channel) from an (h, w) uint8 image; h and w are padded up to a multiple of 4 by edge replication."""
    h, w = a.shape
    ph, pw = -h % 4, -w % 4
    if ph or pw:
        a = np.pad(a, ((0, ph), (0, pw)), mode="edge")
    bh, bw = a.shape[0] // 4, a.shape[1] // 4
    blocks = a.reshape(bh, 4, bw, 4).transpose(0, 2, 1, 3).reshape(bh * bw, 16).astype(np.int32)
    hi = blocks.max(axis=1)
    lo = blocks.min(axis=1)
    # 8-value mode (endpoint 0 > endpoint 1): palette = r0, r1, then 6 steps between them
    pal = np.empty((len(hi), 8), np.int32)
    pal[:, 0], pal[:, 1] = hi, lo
    for i in range(1, 7):
        pal[:, i + 1] = ((7 - i) * hi + i * lo) // 7
    idx = np.abs(blocks[:, :, None] - pal[:, None, :]).argmin(axis=2).astype(np.uint64)
    bits = np.zeros(len(hi), np.uint64)
    for i in range(16):
        bits |= idx[:, i] << np.uint64(3 * i)
    out = np.empty((len(hi), 8), np.uint8)
    out[:, 0], out[:, 1] = hi, lo
    for j in range(6):
        out[:, 2 + j] = ((bits >> np.uint64(8 * j)) & np.uint64(0xFF)).astype(np.uint8)
    return out.tobytes()


def bc4_decode(data: bytes, w: int, h: int) -> np.ndarray:
    bw, bh = -(-w // 4), -(-h // 4)
    a = np.frombuffer(data, np.uint8)[:bw * bh * 8].reshape(bh * bw, 8)
    r0, r1 = a[:, 0].astype(np.int32), a[:, 1].astype(np.int32)
    pal = np.zeros((len(a), 8), np.int32)
    pal[:, 0], pal[:, 1] = r0, r1
    for i in range(1, 7):
        pal[:, i + 1] = (((7 - i) * r0 + i * r1) // 7)
    six = r0 <= r1  # 6-value mode: 4 steps, then 0 and 255
    for i in range(1, 5):
        pal[six, i + 1] = (((5 - i) * r0 + i * r1) // 5)[six]
    pal[six, 6], pal[six, 7] = 0, 255
    bits = np.zeros(len(a), np.uint64)
    for j in range(6):
        bits |= a[:, 2 + j].astype(np.uint64) << np.uint64(8 * j)
    px = np.empty((len(a), 16), np.uint8)
    for i in range(16):
        sel = ((bits >> np.uint64(3 * i)) & np.uint64(7)).astype(np.int64)
        px[:, i] = np.take_along_axis(pal, sel[:, None], 1)[:, 0]
    return px.reshape(bh, bw, 4, 4).transpose(0, 2, 1, 3).reshape(bh * 4, bw * 4)[:h, :w]


def write_texture(path, fmt: int, w: int, h: int, levels: list[bytes]) -> None:
    n = len(levels)
    head = b"<DE(" + struct.pack("<IIIIIIII", fmt | (2 << 16) | (n << 24), w, h, 1, 0, 0, n, 4)
    table = b""
    pos = 0  # data offset from the end of the table
    for i, lv in enumerate(levels):
        field = 0x28 + 8 * i
        data_pos = 0x24 + 8 * n + pos
        table += struct.pack("<II", len(lv), data_pos - field)
        pos += len(lv)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(head + table + b"".join(levels))


def write_bc4(path, a: np.ndarray, mips: int = 1) -> None:
    h, w = a.shape
    levels = []
    for m in mip_chain(a, mips):
        data = bc4_encode(m)
        levels.append(data.ljust(8, b"\0"))
    write_texture(path, FMT_BC4, w, h, levels)


def write_rgba(path, a: np.ndarray, mips: int = 1) -> None:
    h, w = a.shape[:2]
    write_texture(path, FMT_RGBA8, w, h, [m.tobytes() for m in mip_chain(a, mips)])


def _dds_levels(a: np.ndarray, mips: int, pixel_format: str, mode: str) -> list[bytes]:
    import io
    from PIL import Image
    levels = []
    for m in mip_chain(a, mips):
        bio = io.BytesIO()
        Image.fromarray(np.ascontiguousarray(m[..., :len(mode)]), mode).save(bio, format="DDS", pixel_format=pixel_format)
        d = bio.getvalue()
        levels.append(d[148:] if d[84:88] == b"DX10" else d[128:])
    return levels


def write_bc3(path, a: np.ndarray, mips: int = 1, linear: bool = False) -> None:
    """BC3 / DXT5 from (h, w, 4) uint8 pixels, encoded by Pillow's DDS writer: format 62 (sRGB colour: albedo) or, with
    `linear`, format 61 (the engine's linear maps). Normal map: (255, y, 0, x) with 128 = flat; ORM map: (occlusion, roughness,
    metal, 255)."""
    write_texture(path, FMT_BC3_LIN if linear else FMT_BC3, a.shape[1], a.shape[0], _dds_levels(a, mips, "DXT5", "RGBA"))


def read_texture(path):
    """(format, width, height, [mip data]) of a .texture file."""
    d = open(path, "rb").read()
    _m, v, w, h = struct.unpack_from("<4I", d, 0)
    n = (v >> 24) & 0xFF
    mips = []
    for i in range(n):
        size, off = struct.unpack_from("<II", d, 0x24 + 8 * i)
        pos = 0x28 + 8 * i + off
        mips.append(d[pos:pos + size])
    return v & 0xFF, w, h, mips
