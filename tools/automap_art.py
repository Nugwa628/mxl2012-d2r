#!/usr/bin/env python
"""Automap cels for the rows tools/automap_rows.py adds (lanes hdmaps2, automapall; art step).

automap_rows.py's plan (automap_plan.json) names, per dim level type, a free cel for each non-door wall code (one no
table uses, `bright`), the type's own cel it stands for (`template`) and the legacy `gain`. Each one gets:
  classic (legacy graphics): the template cel's picture (the plan's `template`) with every pixel moved to the act palette's
           colour nearest to gain x its colour, in global/ui/automap/maximap.dc6 (the big automap) and maximaps.dc6 (the
           minimap), so the legacy minimap reads as clearly as the HD one;
  HD:      the template cel's own HD picture, unchanged, in hd/global/ui/automap/defaultNN/tiles.sprite and
           tiles.lowend.sprite (NN = cel // 100, frame cel % 100).
The stock cels are not touched. Every file is D2R's copy with only those frames replaced, written into the mod.

  python tools/automap_art.py build MOD_DATA --plan PLAN [--d2r D2R_EXTRACT]   (MOD_DATA = work/mod/data)
  python tools/automap_art.py check --plan PLAN [--d2r ...] [--objects objects.txt ...]   the bright cels are free and in
                                                                                         the atlas
"""
import argparse
import csv
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401
import automap_render as ar  # noqa: E402
import automap_rows  # noqa: E402

GAIN = 2.4                       # classic wall cels of the Tomb average (62, 10, 5): about (150, 25, 12) after
PAL_RANGE = range(1, 225)        # indices 0 (transparent) and 225-254 (act-dependent, dc6.UNUSED) are never picked
UI = Path("global") / "ui" / "automap"


def used_cels(d2r_data: Path, objects=()) -> set:
    """Cels any table names: D2R's automap.txt and the objects.txt AutoMap of D2R and of each file given."""
    used = set()
    lines = (d2r_data / "global" / "excel" / "automap.txt").read_text("utf-8", errors="replace").splitlines()
    head = lines[0].split("\t")
    for ln in lines[1:]:
        r = dict(zip(head, ln.split("\t")))
        used |= {int(r["Cel%d" % i]) for i in range(1, 5) if r.get("Cel%d" % i, "").lstrip("-").isdigit()}
    for p in [d2r_data / "global" / "excel" / "objects.txt", *map(Path, objects)]:
        with open(p, encoding="latin-1", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                v = (r.get("AutoMap") or "").strip()
                if v.lstrip("-").isdigit():
                    used.add(int(v))
    return used


def bright_of(plan: dict) -> dict:
    """{LevelName: {code: (bright cel, template cel)}} of a plan."""
    return {lt: {code: (cel, t["template"][code]) for code, cel in t["bright"].items()}
            for lt, t in plan["types"].items() if t.get("bright")}


def gain_of(plan: dict, lt: str) -> float:
    return float(plan["types"][lt].get("gain") or GAIN)


def check(d2r_data: Path, plan: dict, objects=()) -> list:
    """Problems with the plan's bright cels: a cel some table uses, past the atlas, or one cel standing for two
    different templates."""
    used = used_cels(d2r_data, objects) - {-1, 0}
    out, src = [], {}
    for lt, cels in bright_of(plan).items():
        for code, (cel, tpl) in cels.items():
            if cel in used:
                out.append("%s %s: cel %d is used by a table" % (lt, code, cel))
            if not 0 < cel <= automap_rows.CEL_MAX:
                out.append("%s %s: cel %d is outside D2R's atlas" % (lt, code, cel))
            want = (plan["types"][lt]["act"], tpl, gain_of(plan, lt))
            if src.setdefault(cel, want) != want:
                out.append("%s: cel %d copies two different templates" % (lt, cel))
    return out


def _indices(w: int, h: int, block: bytes) -> np.ndarray:
    """Palette indices of a DC6 frame, top to bottom (0 = transparent)."""
    idx = np.zeros((h, w), np.uint8)
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
                    idx[y, x] = c
                x += 1
            i += b
    return idx


def brighten(idx: np.ndarray, pal, gain: float = GAIN) -> np.ndarray:
    """Each opaque pixel -> the palette index (in PAL_RANGE) nearest to gain x its colour."""
    p = np.array(pal, np.float32)
    cand = np.array(list(PAL_RANGE))
    out = idx.copy()
    for v in np.unique(idx[idx > 0]):
        want = np.clip(p[v] * gain, 0, 255)
        out[idx == v] = cand[int(np.argmin(((p[cand] - want) ** 2).sum(1)))]
    return out


def patch_dc6(data: bytes, new: dict) -> bytes:
    """D2R's DC6 bytes with frames {index: (w, h, ox, oy, block)} replaced; header, the other frames and each frame's
    trailing bytes kept as they are."""
    import struct
    _v, _f, _e, _t, dirs, fpd = struct.unpack_from("<6I", data, 0)
    n = dirs * fpd
    ptrs = list(struct.unpack_from("<%dI" % n, data, 24))
    ends = ptrs[1:] + [len(data)]
    blobs = []
    for i, (p, e) in enumerate(zip(ptrs, ends)):
        head = list(struct.unpack_from("<8i", data, p))
        tail = data[p + 32 + head[7]:e]
        if i in new:
            w, h, ox, oy, block = new[i]
            head[1:5], head[7] = [w, h, ox, oy], len(block)
            blobs.append(struct.pack("<8i", *head) + block + tail)
        else:
            blobs.append(data[p:e])
    out, off = [], 24 + 4 * n
    for b in blobs:
        out.append(off)
        off += len(b)
    return data[:24] + struct.pack("<%dI" % n, *out) + b"".join(blobs)


def patch_sprite(data: bytes, new: dict) -> bytes:
    """D2R's .sprite bytes with frames {frame: RGBA array (h, frame width, 4)} written over their place in the strip; every
    other byte (header, other frames, the gutters between frames) kept."""
    import dc6
    import struct
    _sig, _ver, fw, sw, h = struct.unpack_from("<4sHHII", data, 0)[:5]
    n = struct.unpack_from("<I", data, 0x14)[0]
    stride = sw // n
    strip = np.frombuffer(data, np.uint8, sw * h * 4, dc6.HEADER).reshape(h, sw, 4).copy()
    for i, im in new.items():
        strip[:, i * stride:i * stride + fw] = im
    return data[:dc6.HEADER] + strip.tobytes() + data[dc6.HEADER + sw * h * 4:]


def sprite_frame(data: bytes, i: int) -> np.ndarray:
    import dc6
    import struct
    _sig, _ver, fw, sw, h = struct.unpack_from("<4sHHII", data, 0)[:5]
    n = struct.unpack_from("<I", data, 0x14)[0]
    strip = np.frombuffer(data, np.uint8, sw * h * 4, dc6.HEADER).reshape(h, sw, 4)
    return strip[:, i * (sw // n):i * (sw // n) + fw].copy()


def build(mod_data: Path, d2r_data: Path, plan: dict, log=print) -> dict:
    import dc6
    import map_tint
    from rotw_stash_legacy import encode_frame
    jobs = sorted({(plan["types"][lt]["act"], cel, tpl, gain_of(plan, lt)) for lt, cels in bright_of(plan).items()
                   for _code, (cel, tpl) in cels.items()})
    if not jobs:
        log("automap_art: no bright cels in the plan")
        return {"cels": [], "sheets": 0}
    for name in ("maximap.dc6", "maximaps.dc6"):
        data = (d2r_data / UI / name).read_bytes()
        frames = dc6.parse_dc6(data)
        new = {}
        for act, cel, tpl, gain in jobs:
            pal = [tuple(int(v) for v in c) for c in map_tint.act_palette(act)]
            w, h, ox, oy, block = frames[tpl]
            new[cel] = (w, h, ox, oy, encode_frame(brighten(_indices(w, h, block), pal, gain)))
        out = mod_data / UI / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(patch_dc6(data, new))
    n = 0
    for fname in ("tiles.sprite", "tiles.lowend.sprite"):
        sheets = {}
        for _act, cel, tpl, _gain in jobs:
            sheets.setdefault(cel // 100, {})[cel % 100] = tpl
        for k, pairs in sorted(sheets.items()):
            rel = Path("hd") / UI / ("default%02d" % k) / fname
            if not (d2r_data / rel).is_file():
                continue
            new = {i: sprite_frame((d2r_data / "hd" / UI / ("default%02d" % (tpl // 100)) / fname).read_bytes(), tpl % 100)
                   for i, tpl in pairs.items()}
            (mod_data / rel).parent.mkdir(parents=True, exist_ok=True)
            (mod_data / rel).write_bytes(patch_sprite((d2r_data / rel).read_bytes(), new))
            n += 1
    log("automap_art: %d cels (%s) into maximap.dc6, maximaps.dc6 and %d HD sheets" % (
        len(jobs), ", ".join(str(j[1]) for j in jobs), n))
    return {"cels": [j[1] for j in jobs], "sheets": n}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "check"])
    ap.add_argument("mod_data", nargs="?")
    ap.add_argument("--plan", required=True, help="automap_rows.py's automap_plan.json")
    ap.add_argument("--d2r", default=None, help="D2R's extract (the folder holding data/)")
    ap.add_argument("--objects", action="append", default=[], help="another objects.txt whose AutoMap cels are taken")
    a = ap.parse_args(argv)
    d2r = Path(a.d2r) / "data" if a.d2r else ar.D2R
    plan = automap_rows.load_plan(a.plan)
    problems = check(d2r, plan, a.objects)
    for p in problems:
        print("automap_art: " + p, file=sys.stderr)
    if problems:
        return 1
    if a.cmd == "build":
        if not a.mod_data:
            ap.error("build needs MOD_DATA")
        build(Path(a.mod_data), d2r, plan)
    else:
        print("automap_art: the %d bright cels are free" % sum(len(v) for v in bright_of(plan).values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
