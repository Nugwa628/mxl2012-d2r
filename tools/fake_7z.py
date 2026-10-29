"""A stand-in for the 7-Zip command line for the unit tests on machines without 7-Zip (tools/test_publish_release.py,
tools/test_dl_ingest.py). The archive is really a zip; only what the tools use is there:

  a [-switches] ARCHIVE PATH|@LISTFILE ...    add files and folders (recursively, names relative to the current folder)
  x [-switches] -oDIR ARCHIVE                 unpack everything
  l -slt [-switches] ARCHIVE                  technical listing: Path / Folder / Size / Attributes blocks after "----------"

FAKE_7Z_LINK=NAME makes `a` also store an entry NAME marked as a symbolic link (to test the ingest's listing check).
"""
import os
import sys
import zipfile
from pathlib import Path


def main(argv):
    cmd, rest = argv[0], argv[1:]
    opts = [a for a in rest if a.startswith("-")]
    args = [a for a in rest if not a.startswith("-")]
    if cmd == "a":
        out, inputs = Path(args[0]), args[1:]
        names = []
        for i in inputs:
            if i.startswith("@"):
                names += [ln for ln in Path(i[1:]).read_text("utf-8").splitlines() if ln]
            else:
                names.append(i)
        with zipfile.ZipFile(out, "a" if out.exists() else "w", zipfile.ZIP_DEFLATED) as z:
            for n in names:
                p = Path(n)
                if p.is_dir():
                    z.writestr(p.as_posix() + "/", b"")
                    for q in sorted(p.rglob("*")):
                        if q.is_dir():
                            z.writestr(q.as_posix() + "/", b"")
                        else:
                            z.write(q, q.as_posix())
                elif p.is_file():
                    z.write(p, p.as_posix())
                else:
                    print(f"WARNING: cannot find {n}", file=sys.stderr)
                    return 1
            link = os.environ.get("FAKE_7Z_LINK")
            if link:
                info = zipfile.ZipInfo(link)
                info.external_attr = 0o120777 << 16
                z.writestr(info, b"/etc/passwd")
        return 0
    if cmd == "x":
        dest = next(o[2:] for o in opts if o.startswith("-o"))
        with zipfile.ZipFile(args[0]) as z:
            z.extractall(dest)
        return 0
    if cmd == "l":
        print(f"Path = {args[0]}\nType = 7z\n\n----------")
        with zipfile.ZipFile(args[0]) as z:
            for info in z.infolist():
                mode = info.external_attr >> 16
                attrs = "A_ lrwxrwxrwx" if (mode & 0o170000) == 0o120000 else "A"
                print(f"Path = {info.filename.rstrip('/')}\nFolder = {'+' if info.is_dir() else '-'}\nSize = {info.file_size}\n"
                      f"Attributes = {attrs}\n")
        return 0
    print(f"unsupported command {cmd}", file=sys.stderr)
    return 7


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
