"""Merge Median's animdata.d2 into D2R's (Phase 5: monster animations).

animdata.d2 holds one record per animation (COF name: token + mode + weapon class): frames per direction, speed and
the per-frame event table (attack/missile/sound frames). It is read in HD mode too, for gameplay timing.
Format: 256 buckets (bucket = sum of the upper-case name's characters % 256), each a uint32 count then 160-byte
records: char name[8], uint32 frames, uint32 speed, uint8 events[144].

Merge: D2R's records stay the base (its Warlock and other 3.x additions, 103 records Median lacks). Median's own
animations (its new monster codes and modes, about 2,500) are added. Where both have a record, Median's wins when only
the speed/events differ (Median's attack-speed balance, about 245 records); when the frame count differs, D2R's record
stays, so it keeps matching D2R's COF and HD animation. eanimdata.d2 (D2R's own extra table) is left alone.

Input:  the D2R baseline's data/global/animdata.d2 and Median's (tools/fxpaths.py: MXL_D2R_EXTRACT, MXL_EXTRACT)
Output: work/mod/data/global/animdata.d2, work/mod/animdata_report.md
Usage: python tools/animdata_merge.py
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
import death_cofs  # noqa: E402
import own_tokens  # noqa: E402

ROOT = fxpaths.ROOT
MXL = fxpaths.MXL / "animdata.d2"
OUT = ROOT / "work" / "mod" / "data" / "global" / "animdata.d2"
REPORT = ROOT / "work" / "mod" / "animdata_report.md"
RECORD = 160


def bucket(name: bytes) -> int:
    return sum(name.split(b"\0")[0].upper()) % 256


def parse(data: bytes) -> dict[bytes, bytes]:
    """Upper-case name -> 160-byte record, in file order."""
    recs, o = {}, 0
    for _blk in range(256):
        count = struct.unpack_from("<I", data, o)[0]
        o += 4
        for _ in range(count):
            rec = data[o:o + RECORD]
            recs[rec[:8].split(b"\0")[0].upper()] = rec
            o += RECORD
    if o != len(data):
        raise SystemExit(f"animdata: {len(data) - o} trailing bytes")
    return recs


# Records D2R 93847 ships with more frames than its own classic COF and DCCs of that animation (D2R's Warlock art is the
# Necromancer's, 15 frames for unarmed attacks): in legacy graphics mode the last frame index would run past the art
# (bugs.md #498; tools/warlock_legacy_check.py finds them). Capped to the classic frame count; speed and events stay, they
# lie inside the cap (action frame 9 / 7). The animation is one frame shorter in HD too.
CLASSIC_CAPS = {b"WKA1HTH": 15, b"WKA2HTH": 15}


def cap_classic(merged: dict[bytes, bytes], caps: dict[bytes, int] = CLASSIC_CAPS) -> list[str]:
    """Lower the frame count of the capped records in place; -> 'NAME old->new' per change."""
    done = []
    for name, frames in caps.items():
        rec = merged.get(name)
        if rec is None:
            continue
        have = struct.unpack_from("<I", rec, 8)[0]
        if have <= frames:
            continue
        late = [i for i, e in enumerate(rec[16:]) if e and i >= frames]
        if late:
            raise SystemExit(f"animdata {name.decode()}: events on frames {late} past the classic cap {frames}")
        merged[name] = rec[:8] + struct.pack("<I", frames) + rec[12:]
        done.append(f"{name.decode()} {have}->{frames}")
    return done


def main() -> int:
    D2R = fxpaths.d2r_file("data/global/animdata.d2")
    d2r, mxl = parse(D2R.read_bytes()), parse(MXL.read_bytes())
    merged = dict(d2r)
    added, retimed, kept = [], [], []
    for name, rec in mxl.items():
        if name not in d2r:
            merged[name] = rec
            added.append(name)
        elif rec[8:] != d2r[name][8:]:
            if rec[8:12] == d2r[name][8:12]:  # same frame count: Median's speed and events
                merged[name] = d2r[name][:8] + rec[8:]
                retimed.append(name)
            else:
                kept.append(name)
    own = own_tokens.add_animdata(merged, mxl, d2r)   # records of the own monster tokens (tools/own_tokens.py)
    derived = death_cofs.animdata_records(merged)   # death records for the weapon class of the row (bugs.md #34)
    capped = cap_classic(merged)   # frames past D2R's own classic art (bugs.md #498)
    buckets: list[list[bytes]] = [[] for _ in range(256)]
    for name, rec in merged.items():
        buckets[bucket(rec[:8])].append(rec)
    out = bytearray()
    for b in buckets:
        out += struct.pack("<I", len(b)) + b"".join(b)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(bytes(out))
    report = ["# animdata merge", "",
              f"- D2R records: {len(d2r)}; Median records: {len(mxl)}; merged: {len(merged)}",
              f"- Added from Median: {len(added)}",
              f"- Median timing taken (same frame count): {len(retimed)}",
              f"- D2R kept (frame count differs): {len(kept)}: {', '.join(n.decode() for n in sorted(kept))}",
              f"- D2R-only kept: {sum(1 for n in d2r if n not in mxl)}",
              f"- Own monster token records (tools/own_tokens.py): {', '.join(own) or 'none'}",
              f"- Death records copied from hth (tools/death_cofs.py, bugs.md #34): {', '.join(derived) or 'none'}",
              f"- Capped to the classic art's frames (bugs.md #498): {', '.join(capped) or 'none'}"]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join("   " + line for line in report[2:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
