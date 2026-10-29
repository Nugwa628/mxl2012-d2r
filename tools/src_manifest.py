"""Write a TSV manifest (path, size, sha256, mtime) of an unpacked source tree. Read-only on the source.

Usage: py -3 -I tools/src_manifest.py <src-dir> <out.tsv>
"""
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    rows = []
    for p in sorted(src.rglob("*")):
        if not p.is_file():
            continue
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        st = p.stat()
        mt = datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        rows.append(f"{p.relative_to(src).as_posix()}\t{st.st_size}\t{h.hexdigest()}\t{mt}")
    out.write_text("path\tsize\tsha256\tmtime_utc\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"{len(rows)} files -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
