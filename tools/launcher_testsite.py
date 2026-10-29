#!/usr/bin/env python
"""Test releases for the launcher's end-to-end test (docs/launcher.md "Testing"): a new dist/ folder derived from a real
tools/package_release.py output, with a few files changed, added or removed. tools/publish_release.py then publishes it
into a local site folder in the download host's layout, and tools/serve_dir.py serves that folder with Range.

  py -3 tools/launcher_testsite.py derive --from dist --out dist-lt2 --version 0.70.0-lt2
        [--savepath mxl2012-lt/] [--put REL=FILE ...] [--append REL=TEXT ...] [--remove REL ...]

  --savepath  mxl2012.mpq/modinfo.json "savepath" and the manifest's saveFolder: a test release must never use a real
              save folder (package_release writes mxl2012/, the player's)
  --put       replace or add a file (e.g. the dev mxl2012-core.dll, so the game checks can drive the game)
  --append    add a line to a text file (a changed file)
  --remove    drop a file

Everything else in the manifest (d2r, d2rloader, launch, preserve, ...) is the source's. The 7z is written the way
package_release writes it (tools/package_release.py write_7z, top folder mxl2012/); needs 7-Zip.
"""
import argparse
import datetime
import json
import shutil
import sys
import subprocess
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import package_release as pr  # noqa: E402


def derive(a) -> int:
    src = Path(a.src)
    man = json.loads((src / "release-manifest.json").read_text("utf-8"))
    archives = list(src.glob("D2R-XL-2012-*.7z"))
    if len(archives) != 1:
        print(f"{src}: expected one D2R-XL-2012-*.7z, found {len(archives)}")
        return 1
    sevenzip = pr.find_7z()
    if not sevenzip:
        print(pr.NO_7Z)
        return 1
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        subprocess.run([sevenzip, "x", "-y", "-bd", f"-o{tmp}", str(archives[0])], check=True, capture_output=True)
        mod = Path(tmp) / pr.NAME
        if a.savepath:
            info = mod / "mxl2012.mpq" / "modinfo.json"
            mi = json.loads(info.read_text("utf-8"))
            mi["savepath"] = a.savepath
            info.write_text(json.dumps(mi, indent=2) + "\n", encoding="utf-8")
            man["saveFolder"] = a.savepath
        for spec in a.put:
            rel, file = spec.split("=", 1)
            (mod / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, mod / rel)
        for spec in a.append:
            rel, text = spec.split("=", 1)
            with open(mod / rel, "a", encoding="utf-8", newline="") as f:
                f.write(text + "\n")
        for rel in a.remove:
            (mod / rel).unlink()
        archive = out / f"D2R-XL-2012-{a.version}.7z"
        pr.write_7z(mod, archive, sevenzip)
        files, dirs = pr.file_list(mod), pr.empty_dirs(mod)
    man.update({
        "version": a.version,
        "released": datetime.date.today().isoformat(),
        "archive": {"format": "7z", "name": archive.name, "size": archive.stat().st_size, "sha256": pr.sha256(archive)},
        "emptyDirs": dirs,
        "fileCount": len(files),
        "totalSize": sum(f["size"] for f in files),
        "files": files,
    })
    man_path = out / "release-manifest.json"
    man_path.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
    notes = out / f"RELEASE_NOTES-{a.version}.md"
    notes.write_text(f"# D2R-XL 2012 {a.version}\n\nTest release derived from {man.get('version')} for the launcher tests.\n",
                     encoding="utf-8")
    (out / "SHA256SUMS").write_text("".join(f"{pr.sha256(p)}  {p.name}\n" for p in (archive, man_path, notes)), encoding="utf-8")
    print(f"{out}: {a.version}, {len(files)} files ({len(a.put)} put, {len(a.append)} changed, {len(a.remove)} removed)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("derive")
    d.add_argument("--from", dest="src", required=True, help="a package_release.py output folder")
    d.add_argument("--out", required=True)
    d.add_argument("--version", required=True)
    d.add_argument("--savepath")
    d.add_argument("--put", action="append", default=[])
    d.add_argument("--append", action="append", default=[])
    d.add_argument("--remove", action="append", default=[])
    a = ap.parse_args()
    return derive(a)


if __name__ == "__main__":
    sys.exit(main())
