"""Verify a Median XL original archive against a repack without executing it."""
import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROJECT = REPO.parent.parent if REPO.parent.name == "mxl2012-wt" else REPO.parent
RUNS = Path(os.environ.get("MXL2012_RUNS", PROJECT / "mxl2012-runs"))
SEVEN_ZIP = Path(r"C:\Program Files\7-Zip\7z.exe")
EXPECTED_MD5 = "53ae96c95e76062ef67a73845abe41f6"
RELEVANT = {".mpq", ".dll", ".ini"}
ARCHIVES = {".zip", ".7z", ".rar", ".exe"}


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def extract(archive, destination, seven_zip):
    """Extract each nested archive into its own directory; never run its contents."""
    destination.mkdir(parents=True, exist_ok=False)
    def unpack(source, target, depth):
        if depth > 8:
            raise ValueError("Nested archive depth exceeds 8")
        result = subprocess.run([str(seven_zip), "x", "-y", "-o" + str(target), str(source)],
                                capture_output=True, text=True, errors="replace")
        if result.returncode:
            raise RuntimeError("7-Zip failed on {}: {}".format(source, result.stderr or result.stdout))
        for item in sorted(target.rglob("*")):
            if item.is_file() and item.suffix.lower() in ARCHIVES:
                nested = item.with_name(item.name + ".unpacked")
                # An exe may be a game executable rather than an installer.
                probe = subprocess.run([str(seven_zip), "t", str(item)], capture_output=True)
                if probe.returncode == 0:
                    nested.mkdir()
                    unpack(item, nested, depth + 1)
                elif item.suffix.lower() != ".exe":
                    raise RuntimeError("Cannot unpack nested archive: {}".format(item))
    unpack(archive, destination, 0)


def inventory(root, relevant=False):
    """Index distribution files by basename, or MPQ contents by relative path."""
    if not root.is_dir():
        raise ValueError("Directory does not exist: {}".format(root))
    found = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or (relevant and path.suffix.lower() not in RELEVANT):
            continue
        name = path.name if relevant else path.relative_to(root).as_posix()
        key = name.casefold()
        if key in found:
            raise ValueError("Ambiguous duplicate file name: {} and {}".format(found[key][0], path))
        found[key] = (path, name, path.stat().st_size, digest(path))
    return found


def describe(entry):
    return "{} ({} bytes, SHA-256 {})".format(entry[1], entry[2], entry[3])


def differences(original, repack):
    lines = []
    for title, keys, source in (("Repack-only files", repack.keys() - original.keys(), repack),
                                ("Original-only files", original.keys() - repack.keys(), original)):
        lines.extend(["### " + title, ""])
        lines.extend("- " + describe(source[k]) for k in sorted(keys))
        if not keys:
            lines.append("- None")
        lines.append("")
    lines.extend(["### Changed files", ""])
    changed = [k for k in sorted(original.keys() & repack.keys())
               if original[k][2:] != repack[k][2:]]
    for k in changed:
        lines.append("- Original: {}; repack: {}".format(describe(original[k]), describe(repack[k])))
    if not changed:
        lines.append("- None")
    lines.append("")
    lines.extend(["### Identical files", ""])
    same = [k for k in sorted(original.keys() & repack.keys()) if k not in changed]
    lines.extend("- " + describe(original[k]) for k in same)
    if not same:
        lines.append("- None")
    lines.append("")
    return lines


def report(zip_path, original, repack, original_mpq=None, repack_mpq=None):
    md5 = digest(zip_path, "md5")
    lines = ["# Original vs repack", "", "- Archive: {}".format(zip_path),
             "- Size: {} bytes".format(zip_path.stat().st_size),
             "- MD5: {} ({})".format(md5, "matches expected" if md5 == EXPECTED_MD5 else "MISMATCH"),
             "- SHA-256: {}".format(digest(zip_path)), "", "## Distribution files", ""]
    orig = inventory(original, True)
    rep = inventory(repack, True)
    lines.extend(differences(orig, rep))
    key = "patch_d2.mpq"
    identical = key in orig and key in rep and orig[key][3] == rep[key][3]
    verdict = "patch_d2.mpq identical" if identical else "patch_d2.mpq not identical"
    lines.extend(["## Verdict", "", verdict, ""])
    if not identical and key in orig and key in rep:
        if original_mpq is not None and repack_mpq is not None:
            lines.extend(["## Extracted patch_d2.mpq contents", ""])
            lines.extend(differences(inventory(original_mpq), inventory(repack_mpq)))
        else:
            lines.extend(["MPQ content comparison pending: provide both extraction directories.", ""])
    return "\n".join(lines), verdict, md5 == EXPECTED_MD5


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, help="original ModDB zip")
    parser.add_argument("--repack", type=Path, default=RUNS / "src-repack")
    parser.add_argument("--original", type=Path, default=RUNS / "src-original")
    parser.add_argument("--report", type=Path, default=RUNS / "original-vs-repack.md")
    parser.add_argument("--original-mpq-extract", type=Path)
    parser.add_argument("--repack-mpq-extract", type=Path)
    parser.add_argument("--7zip", type=Path, default=SEVEN_ZIP)
    parser.add_argument("--reuse-original", action="store_true", help="reuse a previously extracted original")
    args = parser.parse_args(argv)
    if bool(args.original_mpq_extract) != bool(args.repack_mpq_extract):
        parser.error("provide both MPQ extraction directories")
    try:
        if not args.reuse_original:
            extract(args.zip, args.original, args.__dict__["7zip"])
        output, verdict, valid = report(args.zip, args.original, args.repack,
                                        args.original_mpq_extract, args.repack_mpq_extract)
        args.report.write_text(output, encoding="utf-8")
        print(verdict)
        if not valid:
            print("Original zip MD5 mismatch; see report.", file=sys.stderr)
            return 1
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
