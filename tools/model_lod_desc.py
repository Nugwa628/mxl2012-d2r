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
records, unless they are given records of their own (`own`, lane hdtools-spritewall).

What the records hold (read from the table and D2R's own files, 14,310 entries; no record is shared by two of D2R's entries):
  entry +36  u32 self-relative offset to the model's array 2 records, one per LOD (lodCount of them)
  entry +40  u32, a power of two (32 for 7,104 entries); copied from the donor
  array 2    u8 isMeshFlipbook + 3 B unused | u32 meshCount | u32 self-relative offset (from +8) to the LOD's array 3 records
  array 3    f32 bbMin[3] | f32 bbMax[3] | u32 (1 for 94%) | u16 (1 for 90%) | u16 vertex format (32: position, normal,
             tangent, uv; 48: the same with a colour; 4, 33, 49 on skinned or other meshes)
No vertex or index count is stored anywhere, so a model need not be padded to its donor's counts.

  py -3 tools/model_lod_desc.py show data/hd/character/enemy/horse/torso.model [...]
  py -3 tools/model_lod_desc.py add OUT.bin NEW_PATH=DONOR_PATH [...]        (reads D2R's table: extraction or shared cache)
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


def lods_of(data, path):
    """[[(bbMin, bbMax, (u32, u16, vertex format)) per mesh] per LOD] of a path's records, or None when it has no entry."""
    n1 = struct.unpack_from("<i", data, 0)[0]
    key = struct.pack("<I", fnv(path))
    for i in range(n1):
        at = 24 + i * ENTRY
        if data[at:at + 4] == key:
            count, rel = struct.unpack_from("<2I", data, at + 32)
            out = []
            for k in range(count):
                p = at + 36 + rel + k * 12
                meshes, rel3 = struct.unpack_from("<2I", data, p + 4)
                recs = [struct.unpack_from("<6fIHH", data, p + 8 + rel3 + j * 32) for j in range(meshes)]
                out.append([(r[0:3], r[3:6], r[6:9]) for r in recs])
            return out
    return None


def add(data, new_to_donor, bounds=None, own=None):
    """A table with `new_to_donor` ({new path: donor path}) added. `bounds` ({new path: (min xyz, max xyz)}) replaces the
    donor's bounds. Existing entries of a new path are replaced. `own` ({new path: [[(bbMin, bbMax) per mesh] per LOD]}):
    those paths get stream records of their own instead of the donor's: as many LODs as listed (LOD 0 first; the mask and
    the count follow), each mesh with its own bounds; the flipbook byte and a mesh record's last three fields are those of
    the donor's first LOD and mesh."""
    old, a2, a3, (n2, n3) = parse(data)
    own = {p: lods for p, lods in (own or {}).items() if p in new_to_donor}
    a2_old_at = 24 + len(old) * ENTRY
    new2, new3, own_at = bytearray(), bytearray(), {}     # own_at: new path -> offset of its first record within new2
    first = {}                                             # key bytes -> the first entry with that key
    for i, e in enumerate(old):
        first.setdefault(e[:4], i)
    for p in sorted(own):
        i = first.get(struct.pack("<I", fnv(new_to_donor[p])))
        if i is None:
            raise KeyError("donor %s is not in the table" % new_to_donor[p])
        first2 = 24 + i * ENTRY + 36 + struct.unpack_from("<I", old[i], 36)[0] - a2_old_at   # the donor's LOD 0, within array 2
        first3 = first2 + 8 + struct.unpack_from("<I", a2, first2 + 8)[0] - len(a2)          # its first mesh, within array 3
        own_at[p] = len(new2)
        for meshes in own[p]:
            new2 += a2[first2:first2 + 4] + struct.pack("<2I", len(meshes), len(new3))   # the offset is fixed up below
            for lo, hi in meshes:
                new3 += struct.pack("<6f", *lo, *hi) + a3[first3 + 24:first3 + 32]
    if new2:    # array 3 moves back by the new array 2 records, so every old array 2 record points that much further
        a2 = bytearray(a2)
        for k in range(n2):
            struct.pack_into("<I", a2, k * 12 + 8, struct.unpack_from("<I", a2, k * 12 + 8)[0] + len(new2))
        for j in range(len(new2) // 12):   # new record j: from its +8 to the end of array 2, over the old array 3, to its meshes
            off3 = struct.unpack_from("<I", new2, j * 12 + 8)[0]
            struct.pack_into("<I", new2, j * 12 + 8, len(new2) - (j * 12 + 8) + len(a3) + off3)
        own_at = {p: len(a2) + at for p, at in own_at.items()}    # within the grown array 2
        a2, a3 = bytes(a2) + bytes(new2), a3 + bytes(new3)
        n2, n3 = n2 + len(new2) // 12, n3 + len(new3) // 32
    drop = {fnv(p) for p in new_to_donor}
    # the stream offset (u32 at +36) is self-relative like the header's: keep each entry's absolute target (in array 2, old
    # file coordinates) and derive the offset again once the entries have their final places
    absolute = [(e, 24 + i * ENTRY + 36 + struct.unpack_from("<I", e, 36)[0]) for i, e in enumerate(old)]
    items = [it for it in absolute if struct.unpack_from("<I", it[0])[0] not in drop]
    by_key = {}                                            # key bytes -> the first item with that key, new ones included
    for it in items:
        by_key.setdefault(it[0][:4], it)
    for new, donor in new_to_donor.items():
        d = by_key.get(struct.pack("<I", fnv(donor)))
        if d is None:
            raise KeyError("donor %s is not in the table" % donor)
        e = bytearray(d[0])
        struct.pack_into("<I", e, 0, fnv(new))
        if bounds and new in bounds:
            lo, hi = bounds[new]
            struct.pack_into("<6f", e, 4, *lo, *hi)
        target = d[1]
        if new in own:     # its own records, behind the old array 2 (old file coordinates, like every target here)
            e[28] = (2 << len(own[new])) - 2
            struct.pack_into("<I", e, 32, len(own[new]))
            target = a2_old_at + own_at[new]
        items.append((bytes(e), target))
        by_key.setdefault(bytes(e[:4]), items[-1])
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
    out = head + b"".join(out) + a2 + a3
    return compact(out) if own else out    # a replaced path's own records are dropped, so adding the same paths twice changes nothing


def compact(data):
    """The table without the stream records no entry points to, the others in their old order."""
    entries, a2, a3, (n2, n3) = parse(data)
    a2_at = 24 + len(entries) * ENTRY
    a3_at = a2_at + len(a2)
    used2, used3, first = set(), set(), []
    for i, e in enumerate(entries):
        count, rel = struct.unpack_from("<2I", e, 32)
        k0 = (24 + i * ENTRY + 36 + rel - a2_at) // 12
        first.append(k0)
        for k in range(k0, k0 + count):
            used2.add(k)
            meshes, rel3 = struct.unpack_from("<2I", a2, k * 12 + 4)
            j0 = (a2_at + k * 12 + 8 + rel3 - a3_at) // 32
            used3.update(range(j0, j0 + meshes))
    if len(used2) == n2 and len(used3) == n3:
        return data
    new2 = {k: n for n, k in enumerate(sorted(used2))}     # old record number -> new
    new3 = {j: n for n, j in enumerate(sorted(used3))}
    a2n_at, a3n_at = a2_at, a2_at + len(new2) * 12
    out2 = bytearray()
    for k in sorted(used2):
        meshes, rel3 = struct.unpack_from("<2I", a2, k * 12 + 4)
        j0 = (a2_at + k * 12 + 8 + rel3 - a3_at) // 32
        target = a3n_at + new3[j0] * 32 if meshes else a3n_at
        out2 += a2[k * 12:k * 12 + 4] + struct.pack("<2I", meshes, target - (a2n_at + new2[k] * 12 + 8))
    out3 = b"".join(a3[j * 32:j * 32 + 32] for j in sorted(used3))
    out1 = []
    for i, e in enumerate(entries):
        e = bytearray(e)
        if struct.unpack_from("<I", e, 32)[0]:
            struct.pack_into("<I", e, 36, a2n_at + new2[first[i]] * 12 - (24 + i * ENTRY + 36))
        out1.append(bytes(e))
    head = struct.pack("<6i", len(entries), 20, len(new2), a2n_at - 12, len(new3), a3n_at - 20)
    return head + b"".join(out1) + bytes(out2) + out3


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("show", "add"):
        print(__doc__)
        return 1
    import fxpaths
    data = fxpaths.d2r_file("data/hd/model_lod_desc.bin").read_bytes()   # D2R's table: the extraction, else the shared cache
    if a[0] == "show":
        entries = parse(data)[0]
        for p in a[1:]:
            e = find(entries, p)
            print(p, describe(e) if e else "not in the table")
            for n, meshes in enumerate(lods_of(data, p) or ()):
                print("  lod %d: %s" % (n, "; ".join("bb %s .. %s, tail %s" % (["%.2f" % v for v in lo], ["%.2f" % v for v in hi], tail)
                                                      for lo, hi, tail in meshes)))
        return 0
    pairs = dict(x.split("=", 1) for x in a[2:])
    out = add(data, pairs)
    Path(a[1]).parent.mkdir(parents=True, exist_ok=True)
    Path(a[1]).write_bytes(out)
    print(a[1], len(out), "bytes,", len(parse(out)[0]), "entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
