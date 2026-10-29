"""Death COFs for weapon classes Median ships no death files for (docs/bugs.md #34).

A monster dies in the modes DT (death) and DD (dead). Median ships one death COF per token, for weapon class `hth` (`9xdthth.cof`,
`9xddhth.cof`), while the monstats2 rows of those tokens have another BaseW (the Amazonites of token `9x` use `bow`). 1.13c found
the hth file whatever the weapon class; D2R draws the HD stand-in's death only from files of the row's own weapon class: the 12
Amazonites killed in level 60 stood in the bind pose (bugs.md #34), although D2R's own goatmen (`gm`, 2hs) and fetishes (`fe`, `fk`,
1hs), which also have hth death COFs only, lie down: their state machines bind the death animation to hth, while the stand-in of
the Amazonites (cr_archer1) only binds it to bow.

This module derives the missing files from the hth ones:

  plan()           [(token, mode, weapon class)] for every monstats row (both banks) whose DT / DD mode is on, whose
                   `<token><mode><BaseW>` COF exists neither in D2R nor in Median's files, and whose `<token><mode>hth` COF is Median's;
  apply_cofs(out)  writes the hth COF under the missing name (data/global/monsters/<token>/cof) with an added `lh` layer in the row's
                   weapon class (the body layers stay hth, so they still name Median's DCCs);
  animdata_records(records)  the matching animdata records: the hth record of the same token and mode under the new name.

Run by legacy_art.py (COF files) and animdata_merge.py (records) in the build; `py -3 -I tools/death_cofs.py` prints the plan.
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from txt_migrate import read_tsv, is_record  # noqa: E402
import fxpaths  # noqa: E402

MODES = ("DT", "DD")
COMPS = ["hd", "tr", "lg", "ra", "la", "rh", "lh", "sh", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]  # COF composite order (legacy_art.py)
EXCEL = fxpaths.OUT / "global" / "excel"


def d2r_cofs() -> set[str]:
    out = set()
    for line in fxpaths.D2R_FILELIST.read_text("utf-8").splitlines():
        m = re.search(r"data/global/monsters/[^/]+/cof/([^/]+)\.cof$", line)
        if m:
            out.add(m.group(1))
    return out


def median_cofs() -> dict[str, Path]:
    """Lower-case stem -> Median's COF file."""
    root = fxpaths.MXL / "monsters"
    return {p.stem.lower(): p for p in root.rglob("*.cof")} if root.exists() else {}


def plan(excel: Path = EXCEL, d2r: set[str] | None = None, mxl: dict[str, Path] | None = None) -> list[tuple[str, str, str]]:
    """(token, mode, weapon class) rows that need a derived death COF, sorted, one per name."""
    d2r = d2r_cofs() if d2r is None else d2r
    mxl = median_cofs() if mxl is None else mxl
    out = set()
    for bank in ("base", ""):
        d = excel / bank
        if not (d / "monstats.txt").exists():
            continue
        h, rows = read_tsv(d / "monstats.txt")
        h2, rows2 = read_tsv(d / "monstats2.txt")
        ms2 = {r[0]: r for r in rows2 if is_record(r)}
        for r in rows:
            row2 = ms2.get(r[h.index("MonStatsEx")]) if is_record(r) else None
            code = r[h.index("Code")].lower() if row2 is not None else ""
            w = (row2[h2.index("BaseW")] or "hth").lower() if row2 is not None else "hth"
            if not code or w == "hth":
                continue
            for mode in MODES:
                have = f"{code}{mode.lower()}"
                if (row2[h2.index("m" + mode)] == "1" and f"{have}{w}" not in d2r and f"{have}{w}" not in mxl
                        and f"{have}hth" in mxl):
                    out.add((code, mode, w))
    return sorted(out)


def add_weapon_layer(data: bytes, weapon: str) -> bytes:
    """The COF with one more layer: the left hand (`lh`, composite 6) in weapon class `weapon`, drawn last in every frame and
    direction. Layers are 9 bytes from offset 28 (composite, shadow, selectable, overlay, transparency, class[4]); after the
    layers come one keyframe byte per frame and, per frame and direction, one composite id per layer in draw order.
    D2R's own death COFs of a bow row (`crdtbow.cof`, `skdtbow.cof`) are built the same way: every body layer in hth plus `lh` in
    the row's class, and that one layer is what the HD state machine reads its weapon class from."""
    n, frames, dirs = data[0], data[1], data[2]
    head, layers = data[:28], data[28:28 + 9 * n]
    keys = data[28 + 9 * n:28 + 9 * n + frames]
    prio = data[28 + 9 * n + frames:]
    assert len(prio) == frames * dirs * n, "COF size"
    new_layer = bytes([COMPS.index("lh"), 1, 1, 0, 0]) + weapon.encode("latin-1")[:3].ljust(4, b"\0")
    new_prio = b"".join(prio[i * n:(i + 1) * n] + bytes([COMPS.index("lh")]) for i in range(frames * dirs))
    return bytes([n + 1]) + head[1:] + layers + new_layer + keys + new_prio


def apply_cofs(out: Path, rows=None) -> list[str]:
    """Write the derived death COFs under `out` (data/global/monsters/...): Median's hth COF plus an `lh` layer in the row's weapon
    class. D2R's HD state machines bind their animations by weapon class (`animationBindings`: the Death / Dead states of the
    cr_archer1 stand-in only have `bow`), and a death COF without a bow layer leaves the stand-in in its bind pose: the Amazonites'
    T-pose (bugs.md #34). The body layers stay hth, so the classic client still finds Median's hth DCCs. Returns report lines."""
    rows = plan() if rows is None else rows
    mxl = median_cofs()
    lines = []
    for code, mode, w in rows:
        src = mxl[f"{code}{mode.lower()}hth"]
        dst = out / "global" / "monsters" / code / "cof" / f"{code}{mode.lower()}{w}.cof"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(add_weapon_layer(src.read_bytes(), w))
        lines.append(f"| {code} | {mode} | {w} | {src.name} |")
    return lines


def animdata_records(records: dict[bytes, bytes], rows=None) -> list[str]:
    """Add the hth animdata record of the token and mode under the new name (keys: upper-case names, values: 160-byte records).
    Returns the names added."""
    rows = plan() if rows is None else rows
    added = []
    for code, mode, w in rows:
        new = f"{code}{mode}{w}".upper().encode()
        old = f"{code}{mode}hth".upper().encode()
        if new not in records and old in records:
            records[new] = new.ljust(8, b"\0") + records[old][8:]
            added.append(new.decode())
    return added


def main() -> int:
    rows = plan()
    for code, mode, w in rows:
        print(f"{code}{mode.lower()}{w}  <- {code}{mode.lower()}hth")
    print(f"{len(rows)} derived death COFs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
