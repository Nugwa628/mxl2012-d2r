"""Read and edit D2R's HD particle files (PopcornFX baked `.particles`, build 93847): docs/hd-effects-authoring.md.

A `.particles` file is a PopcornFX 2.x binary object file. Layout (little endian), found by reading D2R's own files:

    header   u32 magic 0xCA000B11, u32 version 0x01050902, u32 0x1F40, u32 object count, u32 class count,
             u32 offset of the string table, u32 0; then one (class, count) pair of u32 per class
    objects  per object: u32 size, then `size` bytes: 0x20, u32 class (an index into the string table, whose first
             entries are the class names), u16 field count, then per field a u16 field id and its value
    strings  u32 count, then per string a u8 length and the bytes (class names, layer names, property names,
             texture / mesh / material paths, the VM's function names); the table ends the file

Objects refer to each other by number (1 = the first object) and to strings by index. The effect's behaviour (spawn
rate, life, size, colour curves) is compiled bytecode in `CCompilerBlobCache` objects. What a renderer draws with is
plain data: a `CLayerCompileCacheRenderer` lists its `CLayerCompileCacheRendererProperty` objects, each a name (field 0),
a type (field 1: 1 bool, 3 int, 7 float, 12 texture, 14 mesh), a 16-byte value (field 2: a feature switch is
0xFF * 16 on, absent off) and a string (field 3: the texture or mesh path). That is what this module edits:

  - `replace_string` / `set_texture`: any texture or mesh path, of any length (only the string table changes);
  - `set_enabled`: a renderer's `EnableRendering` switch (a layer drawn or not: e.g. the rings of the Salvation aura
    left out so only its rainbow sparkles stay);
  - `set_property`: a float, int or bool property of a renderer (e.g. `Transparent.CameraSortOffset`).

Every edit keeps each object's size, so object offsets and the header stay valid; the string table is rewritten.
`py -3 tools/hd_particles.py info <file>` lists the layers' renderers, their switches and textures.
"""
from __future__ import annotations

import argparse
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

MAGIC = 0xCA000B11
RENDERER = "CLayerCompileCacheRenderer"
PROPERTY = "CLayerCompileCacheRendererProperty"
ON, OFF = b"\xff" * 16, b"\x00" * 16
T_BOOL, T_INT, T_FLOAT, T_TEXTURE, T_MESH = 1, 3, 7, 12, 14
KIND = {0: "billboard", 1: "ribbon", 2: "mesh", 5: "light"}  # renderer field 0 (absent: 0)


@dataclass
class Prop:
    obj: int                 # object number (0-based)
    name: str
    type: int | None = None
    value: bytes | None = None   # the 16-byte value
    value_at: int | None = None  # its offset in the file
    string: int | None = None    # string index (textures, meshes)
    string_at: int | None = None


@dataclass
class Renderer:
    obj: int
    kind: str
    material: str
    props: dict[str, Prop] = field(default_factory=dict)

    @property
    def enabled(self) -> bool:
        p = self.props.get("EnableRendering")
        return bool(p and p.value == ON)


class ParticleFile:
    """A parsed `.particles` file; edits are made on a copy of the bytes and returned by `data()`."""

    def __init__(self, data: bytes):
        self.raw = bytearray(data)
        magic, _ver, _x, nobj, ncls, stro = struct.unpack_from("<6I", data, 0)
        if magic != MAGIC:
            raise ValueError(f"not a D2R particle file (magic {magic:#x})")
        self.str_at = stro
        n = struct.unpack_from("<I", data, stro)[0]
        p, self.strings = stro + 4, []
        for _ in range(n):
            ln = data[p]
            self.strings.append(data[p + 1:p + 1 + ln].decode("latin-1"))
            p += 1 + ln
        if p != len(data):
            raise ValueError(f"string table ends at {p:#x}, file at {len(data):#x}")
        pos = 0x1C + 8 * ncls
        self.objects: list[tuple[int, int, int]] = []  # (class string, payload offset, payload size)
        for _ in range(nobj):
            size = struct.unpack_from("<I", data, pos)[0]
            if data[pos + 4] != 0x20:
                raise ValueError(f"object at {pos:#x} does not start with 0x20")
            self.objects.append((struct.unpack_from("<I", data, pos + 5)[0], pos + 4, size))
            pos += 4 + size
        if pos != stro:
            raise ValueError(f"objects end at {pos:#x}, string table at {stro:#x}")

    # ------------------------------------------------------------------ reading
    def cls(self, i: int) -> str:
        return self.strings[self.objects[i][0]]

    def fields(self, i: int):
        """(field id, value offset) of object i, for the classes whose layout is known (renderers, properties)."""
        _c, off, size = self.objects[i]
        b = self.raw
        n = struct.unpack_from("<H", b, off + 5)[0]
        q, out = off + 7, []
        kind = self.cls(i)
        for _ in range(n):
            fid = struct.unpack_from("<H", b, q)[0]
            q += 2
            out.append((fid, q))
            if kind == PROPERTY:
                q += {0: 4, 1: 4, 2: 16, 3: 4}[fid]
            elif kind == RENDERER:
                if fid in (1, 2):
                    q += 4 + 4 * struct.unpack_from("<I", b, q)[0]
                else:
                    q += 4
            else:
                raise ValueError(f"no field layout for {kind}")
        if q != off + size:
            raise ValueError(f"object {i} ({kind}): fields end at {q:#x}, object at {off + size:#x}")
        return out

    def prop(self, i: int) -> Prop:
        b, p = self.raw, Prop(i, "")
        for fid, at in self.fields(i):
            if fid == 0:
                p.name = self.strings[struct.unpack_from("<I", b, at)[0]]
            elif fid == 1:
                p.type = struct.unpack_from("<I", b, at)[0]
            elif fid == 2:
                p.value, p.value_at = bytes(b[at:at + 16]), at
            elif fid == 3:
                p.string, p.string_at = struct.unpack_from("<I", b, at)[0], at
        return p

    def renderers(self) -> list[Renderer]:
        out = []
        for i in range(len(self.objects)):
            if self.cls(i) != RENDERER:
                continue
            kind, refs, mat = 0, [], ""
            for fid, at in self.fields(i):
                if fid == 0:
                    kind = struct.unpack_from("<I", self.raw, at)[0]
                elif fid == 2:
                    n = struct.unpack_from("<I", self.raw, at)[0]
                    refs = list(struct.unpack_from(f"<{n}I", self.raw, at + 4))
                elif fid == 4:
                    mat = self.strings[struct.unpack_from("<I", self.raw, at)[0]]
            r = Renderer(i, KIND.get(kind, str(kind)), mat)
            for ref in refs:
                p = self.prop(ref - 1)
                r.props[p.name] = p
            out.append(r)
        return out

    def textures(self) -> list[str]:
        return [s for s in self.strings if s.startswith("data/hd/") and s.endswith((".texture", ".model"))]

    def prop_string(self, p: Prop) -> str | None:
        return None if p.string is None else self.strings[p.string]

    # ------------------------------------------------------------------ editing
    def replace_string(self, old: str, new: str) -> int:
        """Every string `old` becomes `new` (any length). Returns how many entries changed."""
        n = 0
        for k, s in enumerate(self.strings):
            if s == old:
                self.strings[k] = new
                n += 1
        return n

    def add_string(self, s: str) -> int:
        if s in self.strings:
            return self.strings.index(s)
        self.strings.append(s)
        return len(self.strings) - 1

    def set_texture(self, r: Renderer, prop: str, path: str) -> None:
        """One renderer's texture or mesh property points at `path` (the others that share the old path keep it)."""
        p = r.props[prop]
        if p.string_at is None:
            raise ValueError(f"{prop} of renderer {r.obj} names no file")
        k = self.add_string(path)
        struct.pack_into("<I", self.raw, p.string_at, k)
        p.string = k

    def set_enabled(self, r: Renderer, on: bool) -> None:
        """A renderer's EnableRendering switch: off, the layer simulates but draws nothing."""
        p = r.props.get("EnableRendering")
        if p is None or p.value_at is None:
            raise ValueError(f"renderer {r.obj} has no EnableRendering value")
        self.raw[p.value_at:p.value_at + 16] = ON if on else OFF
        p.value = ON if on else OFF

    def set_property(self, r: Renderer, prop: str, value) -> None:
        """A bool, int or float property with a stored value (the same value in all four lanes)."""
        p = r.props[prop]
        if p.value_at is None:
            raise ValueError(f"{prop} of renderer {r.obj} has no stored value (it takes the material's default)")
        if p.type == T_FLOAT:
            v = struct.pack("<4f", *([float(value)] * 4))
        elif p.type == T_INT:
            v = struct.pack("<4i", *([int(value)] * 4))
        elif p.type in (T_BOOL, None):
            v = ON if value else OFF
        else:
            raise ValueError(f"{prop} has type {p.type}: set_texture for files")
        self.raw[p.value_at:p.value_at + 16] = v
        p.value = v

    def data(self) -> bytes:
        """The edited file: the objects as edited, then the string table rebuilt."""
        out = bytearray(self.raw[:self.str_at])
        out += struct.pack("<I", len(self.strings))
        for s in self.strings:
            b = s.encode("latin-1")
            if len(b) > 255:
                raise ValueError(f"string longer than 255 bytes: {s[:60]}...")
            out += bytes([len(b)]) + b
        return bytes(out)


# ---------------------------------------------------------------------- recipes
def select(pf: ParticleFile, which) -> list[Renderer]:
    """Renderers by kind ('mesh', 'billboard', 'ribbon', 'light'), '*', a texture/mesh path fragment, several of those
    joined by commas, or a list of indexes into `renderers()`."""
    rs = pf.renderers()
    if isinstance(which, str) and "," in which:
        return [r for r in rs if any(r in select(pf, w.strip()) for w in which.split(","))]
    if which == "*":
        return rs
    if isinstance(which, list):
        return [rs[k] for k in which]
    if which in KIND.values():
        return [r for r in rs if r.kind == which]
    return [r for r in rs if any(which in (pf.prop_string(p) or "") for p in r.props.values())]


def apply(data: bytes, edits: dict, textures: dict[str, str] | None = None) -> bytes:
    """A recipe on a particle file. Keys (all optional):
        hide: renderers to switch off (see `select`)
        show: renderers to switch on
        textures: {old path: new path} for every renderer (`replace_string`)
        props: [{"renderers": <select>, "name": <property>, "value": <number or bool>}]
    `textures` (argument) is merged into the recipe's (derived textures made by the caller)."""
    pf = ParticleFile(data)
    for r in select(pf, edits["hide"]) if "hide" in edits else []:
        pf.set_enabled(r, False)
    for r in select(pf, edits["show"]) if "show" in edits else []:
        pf.set_enabled(r, True)
    for old, new in {**edits.get("textures", {}), **(textures or {})}.items():
        if not pf.replace_string(old, new):
            raise ValueError(f"the file names no {old}")
    for pr in edits.get("props", []):
        for r in select(pf, pr.get("renderers", "*")):
            if pr["name"] in r.props:
                pf.set_property(r, pr["name"], pr["value"])
    return pf.data()


def describe(pf: ParticleFile) -> list[str]:
    lines = [f"{len(pf.objects)} objects, {len(pf.strings)} strings"]
    for k, r in enumerate(pf.renderers()):
        files = sorted({pf.prop_string(p) for p in r.props.values() if p.string is not None} - {None})
        lines.append(f"renderer {k} (object {r.obj}): {r.kind}, {r.material}, {'on' if r.enabled else 'OFF'}")
        lines += [f"    {f}" for f in files]
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("info", help="renderers, switches and files of a .particles file")
    a.add_argument("file")
    a = sub.add_parser("hide", help="write a copy with renderers switched off")
    a.add_argument("file")
    a.add_argument("out")
    a.add_argument("which", help="mesh, billboard, ribbon, *, a path fragment, or comma-separated renderer numbers")
    args = ap.parse_args(argv)
    data = Path(args.file).read_bytes()
    if args.cmd == "info":
        print("\n".join(describe(ParticleFile(data))))
    else:
        w = args.which
        which = [int(x) for x in w.split(",")] if w.replace(",", "").isdigit() else w
        Path(args.out).write_bytes(apply(data, {"hide": which}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
