"""ObjPreset.txt for Median's maps.

A .ds1 map names an object by (act, id): D2R looks the id up in the act's ObjPreset table (Index -> ObjectClass; ids
past the table or negative are skipped). Median's own table (objpreset.bin, 750 rows of Objects.txt row numbers) is
flat: row = 150 * act + id, and its maps lean on that (negative ids reach another act's slots; slots Median changed
differ from D2R's). D2R's per-act tables cannot be edited without breaking D2R's own maps (about 1,600 of the maps the
levels use are D2R's), so Median's whole table is *added*: every non-empty flat slot g becomes row Index 1000 + g in
every act, and tools/ds1_remap.py rewrites Median's maps to those indexes. D2R's own rows stay as they are.

ObjectClass references Objects.txt `Class`; Median's added objects (rows 573-588, ids 587+ in the mod) have no class in
the decoded table, so objects.txt gets Class = Name for them (unique: dummy_2.., megaportal, rainbowportal, ...).
"""
import struct
from pathlib import Path

INDEX_BASE = 1000  # Median flat slot g -> Index 1000 + g
SLOT = 150         # Median's slots per act in its flat table
ACTS = 5


def load_flat(bin_path: Path) -> list[int]:
    """Median's objpreset.bin: u32 count, then count i32 Objects.txt rows (Median numbering)."""
    b = Path(bin_path).read_bytes()
    n = struct.unpack_from("<I", b, 0)[0]
    return list(struct.unpack_from(f"<{n}i", b, 4))


def flat_slot(act0: int, ds1_id: int, flat: list[int]):
    """Flat slot of a map object id (act from the .ds1 header, 0-based), or None if it names no object."""
    g = SLOT * act0 + ds1_id
    if 0 <= g < len(flat) and flat[g] != 0:
        return g
    return None


def fill_classes(header: list[str], rows: list[list[str]]) -> int:
    """Objects.txt: give rows with a blank Class their Name as Class (Median's added objects). Returns rows changed."""
    ci, ni = header.index("Class"), header.index("Name")
    n = 0
    for r in rows:
        if not r[ci].strip() and r[ni].strip():
            r[ci] = r[ni].strip()
            n += 1
    return n


def build(d2r_header: list[str], d2r_rows: list[list[str]], flat: list[int], row_to_id: dict[int, int],
          classes: list[str]) -> tuple[list[list[str]], dict]:
    """D2R's rows plus Median's flat table. row_to_id: Median Objects row -> mod row (idmap); classes: mod Class by row."""
    hi = {h: i for i, h in enumerate(d2r_header)}
    out = [list(r) for r in d2r_rows]
    stats = {"added": 0, "slots": 0, "class_not_first": 0}
    first = {}
    for i, c in enumerate(classes):
        if c:
            first.setdefault(c, i)
    for g, med_row in enumerate(flat):
        if med_row == 0:
            continue
        new_row = row_to_id.get(med_row)
        if new_row is None or not classes[new_row]:
            continue
        stats["slots"] += 1
        if first[classes[new_row]] != new_row:
            stats["class_not_first"] += 1  # the class names an earlier row with the same Class: D2R resolves by name
        for act in range(1, ACTS + 1):
            r = [""] * len(d2r_header)
            r[hi["Index"]], r[hi["Act"]], r[hi["ObjectClass"]] = str(INDEX_BASE + g), str(act), classes[new_row]
            if "*eol" in hi:
                r[hi["*eol"]] = "0"
            out.append(r)
            stats["added"] += 1
    return out, stats
