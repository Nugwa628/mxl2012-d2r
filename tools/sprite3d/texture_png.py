"""Decode a D2R .texture (mip 0) to PNG through Pillow's DDS reader (BC1 / BC3 / BC7 are all Pillow-native).

    py -I tools/sprite3d/texture_png.py <in.texture> <out.png>

The wrapper's format code is the low byte of the version word. 62 = BC3 (DXT5, 8 bits per pixel, colour; confirmed by
viewing a decoded albedo, BC7 gives noise); 58 = BC1 (as noted in d2r_texture.py); 61 (normals, flow, hair maps) is read as BC5
and 65 as BC7, both unverified; use this for albedo (62) only.
"""
import io
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import d2r_texture  # noqa: E402
from PIL import Image  # noqa: E402

DXGI = {58: 71, 62: 77, 61: 83, 65: 98}  # BC1_UNORM, BC3_UNORM, BC5_UNORM, BC7_UNORM


def to_image(path) -> Image.Image:
    fmt, w, h, mips = d2r_texture.read_texture(path)
    if fmt == d2r_texture.FMT_RGBA8:
        return Image.frombytes("RGBA", (w, h), mips[0])
    dxgi = DXGI.get(fmt, 98)
    hdr = bytearray(128 + 20)
    hdr[0:4] = b"DDS "
    struct.pack_into("<7I", hdr, 4, 124, 0x1007, h, w, len(mips[0]), 0, 1)
    struct.pack_into("<I", hdr, 76, 32)          # pixel format size
    struct.pack_into("<I", hdr, 80, 4)           # DDPF_FOURCC
    hdr[84:88] = b"DX10"
    struct.pack_into("<I", hdr, 108, 0x1000)
    struct.pack_into("<5I", hdr, 128, dxgi, 3, 0, 1, 0)
    return Image.open(io.BytesIO(bytes(hdr) + mips[0])).convert("RGBA")


if __name__ == "__main__":
    to_image(sys.argv[1]).save(sys.argv[2])
