"""Layer a mod's loose data/ files over an MPQ extraction (loose wins, as with D2's -direct) into a new folder.

Usage: py -3 -I tools/merge_loose.py <extract-mpq> <repack-root> <out-dir>

Copies <extract-mpq> (minus its _manifest/_listfile) to <out-dir>, then copies <repack-root>/data/** over it.
Path matching is case-insensitive (MPQ names are). Writes <out-dir>/_merge_manifest.json with, per file,
the source ("mpq", "loose-override" with both hashes, or "loose-new").
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    mpq, repack, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    if out.exists() and any(out.iterdir()):
        print(f"{out} is not empty; refusing to overwrite")
        return 1
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict] = {}
    by_lower: dict[str, str] = {}
    for p in sorted(mpq.rglob("*")):
        if not p.is_file() or p.parent == mpq and p.name.startswith("_"):
            continue
        rel = p.relative_to(mpq).as_posix()
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        files[rel] = {"source": "mpq", "size": p.stat().st_size, "sha256": sha(p)}
        by_lower[rel.lower()] = rel
    loose_root = repack / "data"
    for p in sorted(loose_root.rglob("*")):
        if not p.is_file():
            continue
        rel = "data/" + p.relative_to(loose_root).as_posix()
        h = sha(p)
        prev = by_lower.get(rel.lower())
        if prev:
            entry = {"source": "loose-override", "size": p.stat().st_size, "sha256": h,
                     "mpq_sha256": files[prev]["sha256"], "mpq_size": files[prev]["size"],
                     "identical": files[prev]["sha256"] == h}
            target = out / prev
            del files[prev]
            rel = prev
        else:
            entry = {"source": "loose-new", "size": p.stat().st_size, "sha256": h}
            target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        files[rel] = entry
        by_lower[rel.lower()] = rel
    counts: dict[str, int] = {}
    for e in files.values():
        k = e["source"] + ("-identical" if e.get("identical") else "")
        counts[k] = counts.get(k, 0) + 1
    (out / "_merge_manifest.json").write_text(json.dumps({"mpq": str(mpq), "loose": str(loose_root),
                                                          "counts": counts, "files": dict(sorted(files.items()))},
                                                         indent=1), encoding="utf-8")
    print(f"{len(files)} files -> {out}; {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
