"""Extract every file of one MPQ (read-only on the archive) and write a manifest.

Usage: py -3 -I tools/mpq_dump.py <archive.mpq> <out-dir> [--listfile <file>]...

Adapted from another port's mpq_extract.py (same StormLib build through tools/native.py). Names come from the
archive's internal (listfile) plus any external listfiles given. Entries StormLib cannot name come back as
FileNNNNNNNN.xxx; they are extracted under those names and counted as unnamed in the manifest.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native  # noqa: E402

SPECIAL = {"(listfile)", "(attributes)", "(signature)"}
UNNAMED = re.compile(r"^File\d{8}\.\w+$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mpq")
    ap.add_argument("out")
    ap.add_argument("--listfile", action="append", default=[])
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    h = native.open_mpq(args.mpq)
    try:
        total = native.mpq_file_count(h)
        names: dict[str, int] = {}
        # One listing pass: StormLib merges the internal (listfile) with the external one, so a single pass gives
        # every resolvable name once (the last listfile given wins; pass a merged file for several sources).
        lf = args.listfile[-1] if args.listfile else None
        for n, s in native.mpq_files(h, lf):
            names.setdefault(n, s)
        files, failed, unnamed = {}, [], []
        for name, size in sorted(names.items()):
            if name in SPECIAL:
                # keep the internal listfile itself for reference
                if name == "(listfile)":
                    native.extract(h, name, out / "_listfile.txt")
                continue
            rel = name.replace("\\", "/")
            dest = out / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not native.extract(h, name, dest):
                failed.append(name)
                continue
            sha = hashlib.sha256(dest.read_bytes()).hexdigest()
            files[rel] = {"size": dest.stat().st_size, "sha256": sha}
            if UNNAMED.match(Path(rel).name):
                unnamed.append(rel)
    finally:
        native.storm.SFileCloseArchive(h)
    manifest = {"source": str(args.mpq), "hash_table_entries": total, "listfiles": args.listfile,
                "extracted": len(files), "unnamed": unnamed, "failed": failed, "files": files}
    (out / "_manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"archive reports {total} entries; extracted {len(files)}, unnamed {len(unnamed)}, failed {len(failed)} -> {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
