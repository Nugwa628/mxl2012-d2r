#!/usr/bin/env python
"""`data/hd/model_lod_desc.bin`: the engine's index of model files (docs/hd-models.md section 3c). Adds entries for NEW model paths.

D2R's model asset cache (D2Render\\src\\model_asset_cache.cpp, loader 0xf75c60, resolver 0xf75fe0) looks every model up by the
FNV-1a hash of its lower-cased game path `data/hd/.../torso.model`. A path that is not in the table is requested as the plain
`torso.model`, loaded and never drawn; a path that is in the table gets its `_lodN.model` files (the entry's LOD mask) and
the bounds / stream sizes it stores. A new model path therefore needs an entry; the entry of a vanilla model with the same
number of LODs is a good template (the vanilla override at the `horse` path draws with the horse's entry).

File layout (little endian): three arrays, header `{count, self-relative offset}` x 3 (the offset is from its own field):
  array 1  count1 x 44 B, sorted by key: u32 key | f32 bbMin[3] | f32 bbMax[3] | u8 lodMask (bit k+1 = lod k) + 3 B | u32 lodCount |
           u32 offset | u32 size (offset / size index the stream records of arrays 2 and 3)
  array 2  count2 x 12 B     array 3  count3 x 32 B  (per mesh / per LOD stream records)
Adding entries only grows array 1 (so the offsets of arrays 2 and 3 grow by 44 B per entry); the new entries share the donor's
records.

  py -3 tools/model_lod_desc.py show data/hd/character/enemy/horse/torso.model [...]
  py -3 tools/model_lod_desc.py add OUT.bin NEW_PATH=DONOR_PATH [...]        (reads the installed game's table)
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ENTRY = 44
GAME_FILE = "data:data/hd/model_lod_desc.bin"


def fnv(path):
    """The key: FNV-1a 32 of the lower-cased path."""
    h = 0x811c9dc5
    for c in path.lower().encode("ascii"):
        h = ((h ^ c) * 0x1000193) & 0xffffffff
    return h


def read_game_table(game):
    import native
    return native.casc_read(native.open_casc(game), GAME_FILE)


def parse(data):
    n1, r1, n2, r2, n3, r3 = struct.unpack_from("<6i", data, 0)
    a1, a2, a3 = 4 + r1, 12 + r2, 20 + r3
    if a1 + n1 * ENTRY != a2 or a2 + n2 * 12 != a3 or a3 + n3 * 32 != len(data):
        raise ValueError("model_lod_desc.bin layout differs from the build the tool was written for")
    entries = [bytes(data[a1 + i * ENTRY:a1 + (i + 1) * ENTRY]) for i in range(n1)]
    return entries, bytes(data[a2:a3]), bytes(data[a3:]), (n2, n3)


def find(entries, path):
    k = struct.pack("<I", fnv(path))
    return next((e for e in entries if e[:4] == k), None)


def describe(e):
    f = struct.unpack("<I6f", e[:28])
    mask, count, off, size = e[28], *struct.unpack_from("<3I", e, 32)
    return "key %08x bb min %s max %s lod mask %02x count %d stream off %d size %d" % (
        f[0], ["%.2f" % x for x in f[1:4]], ["%.2f" % x for x in f[4:7]], mask, count, off, size)


def add(data, new_to_donor, bounds=None):
    """A table with `new_to_donor` ({new path: donor path}) added. `bounds` ({new path: (min xyz, max xyz)}) replaces the
    donor's bounds. Existing entries of a new path are replaced."""
    old, a2, a3, (n2, n3) = parse(data)
    drop = {fnv(p) for p in new_to_donor}
    # the stream offset (u32 at +36) is self-relative like the header's: keep each entry's absolute target (in array 2, old
    # file coordinates) and derive the offset again once the entries have their final places
    absolute = [(e, 24 + i * ENTRY + 36 + struct.unpack_from("<I", e, 36)[0]) for i, e in enumerate(old)]
    items = [it for it in absolute if struct.unpack_from("<I", it[0])[0] not in drop]
    for new, donor in new_to_donor.items():
        d = next((it for it in items if it[0][:4] == struct.pack("<I", fnv(donor))), None)
        if d is None:
            raise KeyError("donor %s is not in the table" % donor)
        e = bytearray(d[0])
        struct.pack_into("<I", e, 0, fnv(new))
        if bounds and new in bounds:
            lo, hi = bounds[new]
            struct.pack_into("<6f", e, 4, *lo, *hi)
        items.append((bytes(e), d[1]))
    items.sort(key=lambda it: struct.unpack_from("<I", it[0])[0])
    a2_old = 24 + len(old) * ENTRY
    n1 = len(items)
    a1 = 24
    a2s = a1 + n1 * ENTRY
    a3s = a2s + len(a2)
    shift = a2s - a2_old  # array 2 moved by this much
    out = []
    for i, (e, t) in enumerate(items):
        e = bytearray(e)
        struct.pack_into("<I", e, 36, t + shift - (a1 + i * ENTRY + 36))
        out.append(bytes(e))
    head = struct.pack("<6i", n1, a1 - 4, n2, a2s - 12, n3, a3s - 20)
    return head + b"".join(out) + a2 + a3


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("show", "add"):
        print(__doc__)
        return 1
    import wereowl_models as wm
    data = read_game_table(wm.GAME)
    if a[0] == "show":
        entries = parse(data)[0]
        for p in a[1:]:
            e = find(entries, p)
            print(p, describe(e) if e else "not in the table")
        return 0
    pairs = dict(x.split("=", 1) for x in a[2:])
    out = add(data, pairs)
    Path(a[1]).parent.mkdir(parents=True, exist_ok=True)
    Path(a[1]).write_bytes(out)
    print(a[1], len(out), "bytes,", len(parse(out)[0]), "entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
