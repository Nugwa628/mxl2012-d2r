"""A .ds1 preset map read into editable layers and objects, and written back byte for byte.

Layout (versions 3..18, after ds1edit by Paul Siramy and OpenDiablo2's d2ds1; tools/ds1_remap.py reads the same header):

  version, width-1, height-1, [act (v>=8)], [tag type (v>=10)], [file list (v>=3): count + zero-ended names],
  [2 dwords (v 9..13)], [wall layers (v>=4)], [floor layers (v>=16)], then the layer stream of width*height dwords each:
    v>=4:  wall1, orientation1, wall2, orientation2, ..., floor1, floor2, ..., shadow, [tag (tag type 1 or 2)]
    v<4:   wall1, orientation1, floor1, tag, shadow
  then objects (v>=2): count + (type, id, x, y[, flags v>=5]) int32 each; then groups and NPC paths (kept as raw bytes).

A wall / floor / shadow dword: byte 0 "prop1" (0 = no tile), bits 8-13 sequence (sub index), bits 20-25 style (main
index), bit 31 hidden. An orientation dword's low byte is the wall's tile orientation (versions below 7 store an older
code, mapped through ORIENT_V6). Object x, y are sub-tiles (5 per cell).

Writing replaces only the layer stream and the object block; everything else (file list, groups, paths, unknown dwords)
is copied, so an unchanged map writes the same bytes.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

ORIENT_V6 = (0x00, 0x01, 0x02, 0x01, 0x02, 0x03, 0x03, 0x05, 0x05, 0x06, 0x06, 0x07, 0x07, 0x08, 0x09, 0x0A, 0x0B,
             0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x14)
SUBTILES = 5


def cell_fields(c: int) -> dict:
    c = int(c)
    return {"dword": c, "prop1": c & 0xFF, "sequence": (c >> 8) & 0x3F, "style": (c >> 20) & 0x3F,
            "unknown": (c >> 14) & 0x3F, "hidden": bool(c >> 31 & 1), "raw_hex": "%08x" % c}


def make_cell(style: int, sequence: int, prop1: int = 1, hidden: bool = False, keep: int = 0) -> int:
    """A wall/floor dword: `keep`'s other bits kept, style / sequence / prop1 / hidden set."""
    c = int(keep) & ~(0xFF | (0x3F << 8) | (0x3F << 20) | (1 << 31))
    c |= (prop1 & 0xFF) | ((sequence & 0x3F) << 8) | ((style & 0x3F) << 20) | ((1 << 31) if hidden else 0)
    return c & 0xFFFFFFFF


@dataclass
class Obj:
    type: int
    id: int
    x: int
    y: int
    flags: int = 0

    def as_list(self):
        return [self.type, self.id, self.x, self.y, self.flags]


class Ds1:
    def __init__(self, data: bytes):
        self.data = bytes(data)
        o = 0

        def i32():
            nonlocal o
            if o + 4 > len(data):
                raise ValueError("ds1 header runs past the end of the file")
            v = struct.unpack_from("<i", data, o)[0]
            o += 4
            return v

        self.version = i32()
        if not 1 <= self.version <= 30:
            raise ValueError("ds1 version %d" % self.version)
        self.width = i32() + 1
        self.height = i32() + 1
        if not (0 < self.width <= 4096 and 0 < self.height <= 4096):
            raise ValueError("ds1 size %dx%d" % (self.width, self.height))
        self.act = i32() if self.version >= 8 else 0
        self.tag_type = i32() if self.version >= 10 else 0
        self.files = []
        if self.version >= 3:
            for _ in range(i32()):
                e = data.index(b"\0", o)
                self.files.append(data[o:e].decode("latin1"))
                o = e + 1
        if 9 <= self.version <= 13:
            o += 8
        self.n_walls = i32() if self.version >= 4 else 1
        self.n_floors = i32() if self.version >= 16 else 1
        self.layers_at = o
        if self.version >= 4:
            stream = []
            for j in range(self.n_walls):
                stream += [("wall", j), ("orient", j)]
            stream += [("floor", j) for j in range(self.n_floors)]
            stream.append(("shadow", 0))
            if self.tag_type in (1, 2):
                stream.append(("tag", 0))
        else:
            stream = [("wall", 0), ("orient", 0), ("floor", 0), ("tag", 0), ("shadow", 0)]
        self.stream = stream
        n = self.width * self.height
        need = len(stream) * n * 4
        if o + need > len(data):
            raise ValueError("ds1 layers run past the end of the file")
        arr = np.frombuffer(data, "<u4", len(stream) * n, o).reshape(len(stream), self.height, self.width)
        self.layers = {k: arr[i].copy() for i, k in enumerate(stream)}
        o += need
        self.objects_at = o
        self.objects = []
        if self.version >= 2:
            cnt = i32()
            rec = 20 if self.version >= 5 else 16
            if cnt < 0 or o + cnt * rec > len(data):
                raise ValueError("object block runs past the end of the file")
            for _ in range(cnt):
                t, i, x, y = struct.unpack_from("<4i", data, o)
                o += 16
                f = i32() if self.version >= 5 else 0
                self.objects.append(Obj(t, i, x, y, f))
        self.tail_at = o            # groups, NPC paths: copied as they are

    # ---- access ------------------------------------------------------------------------------------------------------
    @classmethod
    def read(cls, path) -> "Ds1":
        from pathlib import Path
        return cls(Path(path).read_bytes())

    def walls(self):
        return [self.layers[("wall", j)] for j in range(self.n_walls)]

    def floors(self):
        return [self.layers[("floor", j)] for j in range(self.n_floors)]

    def orientation(self, j: int) -> np.ndarray:
        """Orientation codes (0..19) of wall layer j (versions below 7 mapped to the current codes)."""
        o = (self.layers[("orient", j)] & 0xFF).astype(np.int32)
        if self.version < 7:
            lut = np.array(ORIENT_V6 + (0,) * (256 - len(ORIENT_V6)), np.int32)
            o = lut[o]
        return o

    @property
    def shadow(self):
        return self.layers[("shadow", 0)]

    def cell_info(self, x: int, y: int) -> dict:
        out = {"floors": [], "walls": [], "shadow": None}
        for j, f in enumerate(self.floors()):
            out["floors"].append(dict(cell_fields(f[y, x]), layer=j))
        for j, w in enumerate(self.walls()):
            out["walls"].append(dict(cell_fields(w[y, x]), layer=j, orientation=int(self.orientation(j)[y, x]),
                                     orient_dword="%08x" % int(self.layers[("orient", j)][y, x])))
        out["shadow"] = cell_fields(self.shadow[y, x])
        if ("tag", 0) in self.layers:
            out["tag"] = int(self.layers[("tag", 0)][y, x])
        return out

    def objects_in_cell(self, x: int, y: int):
        return [(i, o) for i, o in enumerate(self.objects)
                if x * SUBTILES <= o.x < (x + 1) * SUBTILES and y * SUBTILES <= o.y < (y + 1) * SUBTILES]

    # ---- write -------------------------------------------------------------------------------------------------------
    def pack(self) -> bytes:
        out = bytearray(self.data[:self.layers_at])
        for k in self.stream:
            a = self.layers[k]
            if a.shape != (self.height, self.width):
                raise ValueError("layer %s has shape %s" % (k, a.shape))
            out += np.ascontiguousarray(a, "<u4").tobytes()
        if self.version >= 2:
            out += struct.pack("<i", len(self.objects))
            for ob in self.objects:
                out += struct.pack("<4i", ob.type, ob.id, ob.x, ob.y)
                if self.version >= 5:
                    out += struct.pack("<i", ob.flags)
        out += self.data[self.tail_at:]
        return bytes(out)

    def write(self, path):
        from pathlib import Path
        Path(path).write_bytes(self.pack())


def synthetic(width: int, height: int, version: int = 18, walls: int = 1, floors: int = 1, act: int = 0,
              files=("\\d2\\data\\global\\tiles\\test\\floor.tg1",), objects=(), tail: bytes = b"") -> bytes:
    """A small .ds1 for tests (all layers empty)."""
    b = bytearray(struct.pack("<3i", version, width - 1, height - 1))
    if version >= 8:
        b += struct.pack("<i", act)
    if version >= 10:
        b += struct.pack("<i", 0)
    if version >= 3:
        b += struct.pack("<i", len(files))
        for f in files:
            b += f.encode("latin1") + b"\0"
    if 9 <= version <= 13:
        b += b"\0" * 8
    if version >= 4:
        b += struct.pack("<i", walls)
    if version >= 16:
        b += struct.pack("<i", floors)
    nl = (walls * 2 + floors + 1) if version >= 4 else 5
    b += b"\0" * (nl * width * height * 4)
    if version >= 2:
        b += struct.pack("<i", len(objects))
        for o in objects:
            b += struct.pack("<4i", *o[:4])
            if version >= 5:
                b += struct.pack("<i", o[4] if len(o) > 4 else 0)
    return bytes(b + tail)
