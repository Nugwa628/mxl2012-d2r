"""Extract Median XL 2012 v005's patch_d2.mpq (the ModDB original) into assets/median/ and write its manifest.

Usage: py -3 -I tools/mpq_extract.py [--src PATH] [--out assets/median] [--any-mpq]

  --src   patch_d2.mpq, or a folder holding it (default: <MXL2012_RUNS>/src-original, where tools/verify_original.py unpacks the
          ModDB zip Median_XL_2012_v005.zip; docs/verify-original.md)
  --out   a new or empty folder (default assets/median, the median/ part of the asset pack: tools/asset_pack.py build)
  --any-mpq  extract an MPQ whose sha256 is not the v005 original's (a test archive); the manifest says so

Median XL 2012 ships one archive: its patch_d2.mpq REPLACES Blizzard's (docs/source-inventory.md), so the tree holds the
vanilla 1.13c patch files next to Median's own. Names come from the archive's internal (listfile) plus
tools/data/patch_d2-v005.names.txt: the 49 names the internal list lacks (the excel .bin twins, a few maps, sounds, art and
the non-English patchstring.tbl), found by the inventory lane with a 45,140-name candidate list (tools/make_listfile.py) and
kept here so the extraction needs nothing but the MPQ. The 19 entries no name is known for are extracted as
FileNNNNNNNN.xxx (StormLib's name: the hash-table index, the same for the same archive) at the root of the tree.

Writes <out>/_manifest.json (source file name + sha256, counts, unnamed list, size + sha256 per file; no local paths, the tree
is packed) and <out>/_listfile.txt (the archive's own listfile, for reference). Reads the archive only.
Exit codes: 0 ok, 1 extraction failure or wrong archive, 2 usage.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I leaves the script's folder off sys.path

ROOT = Path(__file__).resolve().parent.parent
import localconfig  # noqa: E402
RUNS = localconfig.runs_dir()
NAMES = ROOT / "tools" / "data" / "patch_d2-v005.names.txt"
# patch_d2.mpq of Median_XL_2012_v005.zip (md5 53ae96c95e76062ef67a73845abe41f6); the archive.org repack's copy is identical
ORIGINAL_SHA256 = "5a9da6ea9aa0cf229a011407a1ece89f56652fb7079c4328ffb4e6b7696b1f9b"
ORIGINAL_SIZE = 168_375_551
SPECIAL = {"(listfile)", "(attributes)", "(signature)"}
UNNAMED = re.compile(r"^File\d{8}\.\w+$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def find_mpq(src: Path) -> Path | None:
    if src.is_file():
        return src
    if src.is_dir():
        hits = sorted(p for p in src.rglob("*") if p.is_file() and p.name.lower() == "patch_d2.mpq")
        return hits[0] if len(hits) == 1 else None
    return None


def extract(mpq: Path, out: Path, any_mpq: bool = False) -> int:
    size, sha = mpq.stat().st_size, sha256_file(mpq)
    original = size == ORIGINAL_SIZE and sha == ORIGINAL_SHA256
    if not original and not any_mpq:
        print(f"{mpq}: not Median XL 2012 v005's patch_d2.mpq (size {size:,}, sha256 {sha[:16]}...); --any-mpq extracts it anyway")
        return 1
    if out.exists() and any(out.iterdir()):
        print(f"{out} is not empty: extract into a new folder")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    import native  # StormLib (build/StormLib, tools/build_native.ps1): Windows only, loaded when needed
    h = native.open_mpq(mpq)
    try:
        total = native.mpq_file_count(h)
        names: dict[str, int] = {}
        for n, s in native.mpq_files(h, str(NAMES)):
            names.setdefault(n, s)
        files, failed, unnamed = {}, [], []
        for name in sorted(names):
            if name in SPECIAL:
                if name == "(listfile)":
                    native.extract(h, name, out / "_listfile.txt")
                continue
            rel = name.replace("\\", "/")
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not native.extract(h, name, dest):
                failed.append(rel)
                continue
            files[rel] = {"size": dest.stat().st_size, "sha256": sha256_file(dest)}
            if UNNAMED.match(Path(rel).name):
                unnamed.append(rel)
    finally:
        native.storm.SFileCloseArchive(h)
    manifest = {"source": {"file": mpq.name, "size": size, "sha256": sha, "original_v005": original},
                "names": NAMES.relative_to(ROOT).as_posix(), "hash_table_entries": total,
                "extracted": len(files), "unnamed": unnamed, "failed": failed, "files": files}
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{mpq.name}: archive reports {total} entries; extracted {len(files)}, unnamed {len(unnamed)}, failed {len(failed)} -> {out}")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--src", default=str(RUNS / "src-original"))
    ap.add_argument("--out", default=str(ROOT / "assets" / "median"))
    ap.add_argument("--any-mpq", action="store_true")
    args = ap.parse_args()
    mpq = find_mpq(Path(args.src))
    if mpq is None:
        print(f"{args.src}: no (single) patch_d2.mpq there")
        return 2
    return extract(mpq, Path(args.out), args.any_mpq)


if __name__ == "__main__":
    sys.exit(main())
