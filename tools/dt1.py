"""Reader for .dt1 tile sets (version 7.6): tile keys, geometry and a content hash per tile.

A .dt1 holds tiles with a header of 96 bytes each (file offset in the dword at 0x110, count at 0x10C). A map (.ds1) names a
tile by (orientation, main index = "style", sub index = "sequence"); the game loads the .dt1 files the level type lists
(lvltypes File 1..32, selected by lvlprest Dt1Mask) and looks the key up in all of them.

Used by tools/maps_hd.py to tell which of a map's tiles come from stock tile sets and which from Median's own, and which
stock tile set a Median tile set was copied from (identical tile data).
"""
import hashlib
import struct
from pathlib import Path

HEADER_COUNT_AT = 0x10C
TILE_HEADER = 96


class Tile:
    __slots__ = ("orientation", "main", "sub", "width", "height", "digest", "meta")

    def __init__(self, orientation, main, sub, width, height, digest, meta=b""):
        self.orientation, self.main, self.sub = orientation, main, sub
        self.width, self.height, self.digest, self.meta = width, height, digest, meta

    @property
    def key(self):
        return (self.orientation, self.main, self.sub)


def parse(data: bytes) -> list[Tile]:
    """Tiles of a .dt1. Raises ValueError for a file that is not version 7.x or runs past its end."""
    if len(data) < HEADER_COUNT_AT + 8:
        raise ValueError("dt1 too short")
    v1, v2 = struct.unpack_from("<ii", data, 0)
    if v1 != 7:
        raise ValueError("dt1 version %d.%d, expected 7.x" % (v1, v2))
    count, ptr = struct.unpack_from("<ii", data, HEADER_COUNT_AT)
    if count < 0 or ptr < 0 or ptr + count * TILE_HEADER > len(data):
        raise ValueError("dt1 tile table runs past the end of the file")
    tiles = []
    for i in range(count):
        o = ptr + i * TILE_HEADER
        height, width = struct.unpack_from("<ii", data, o + 8)
        orient, main, sub = struct.unpack_from("<iii", data, o + 20)
        bptr, blen = struct.unpack_from("<ii", data, o + 72)
        if bptr < 0 or blen < 0 or bptr + blen > len(data):
            raise ValueError("dt1 tile %d data runs past the end of the file" % i)
        h = hashlib.sha1(struct.pack("<iiii", width, height, main, sub))
        h.update(data[bptr:bptr + blen])
        # header without the unused bytes 65-71 and 84-95 (editors leave junk there) and the data pointer / length / block
        # count (72-83): direction, roof height, sound, animation, size, key, rarity and the 25 sub-tile flags (walkability
        # at 40-64), i.e. what the game logic reads besides the pixels
        meta = data[o:o + 65]
        tiles.append(Tile(orient, main, sub, width, height, h.digest(), meta))
    return tiles


def parse_file(path: Path) -> list[Tile]:
    return parse(Path(path).read_bytes())
