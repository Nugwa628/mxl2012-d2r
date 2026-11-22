"""The art store for the monster3d scripts: find, fetch and check files moved out of EV (see common.py).

  python store.py where <logical path> [...]             where each file is now (local copy or store object)
  python store.py list <pattern> [...]                   logical paths in ART-MANIFEST.json that match (fnmatch, / separators)
  python store.py fetch <dest dir> <pattern> [...]       copy matching files to <dest dir>/<logical path>, hash checked
  python store.py fetch --in-place <pattern> [...]       the same into EV itself (puts files back where they were)
  python store.py tools                                  the tool and weights trees and where they resolve
  python store.py check [<pattern>]                      re-hash the store objects of matching entries
  python store.py put [--min-kib N] [--delete] [--dry] <file or dir under EV> [...]
                                                        copy local files (dirs: every file of at least N KiB, default
                                                        256) into the store and add them to ART-MANIFEST.json; with
                                                        --delete the local file goes only after its object re-hashes
                                                        equal. Each object is written to tmp/, hash checked, then moved
                                                        into objects/; the manifest copy in the store is refreshed.

A pattern is a logical path (the file's old path relative to EV, e.g. fungus/round5/stages/3-tone-f/albedo.png) or an
fnmatch pattern on it (fungus/round5/stages/3-tone-f/*). A file name list can be given as @list.txt (one per line).
The store is MXL_ART_STORE or machine.json art_store (common.py); MXL_M3D_DIR or m3d_dir moves EV. Stdlib only.
"""
import fnmatch
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import common


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def patterns(args):
    out = []
    for a in args:
        if a.startswith("@"):
            out += [line.strip().replace("\\", "/") for line in open(a[1:], encoding="utf-8") if line.strip()]
        else:
            out.append(a.replace("\\", "/"))
    return out


def select(pats):
    files = common.manifest()["files"]
    hit = []
    for pat in pats:
        if any(c in pat for c in "*?["):
            got = [f for f in files if fnmatch.fnmatchcase(f["path"], pat)]
        else:
            got = [f for f in files if f["path"] == pat or f["path"].startswith(pat.rstrip("/") + "/")]
        if not got:
            raise SystemExit("no manifest entry matches %s" % pat)
        hit += got
    seen = set()
    return [f for f in hit if not (f["path"] in seen or seen.add(f["path"]))]


def fetch(dest: Path, entries):
    n = skipped = 0
    for f in entries:
        out = dest / f["path"]
        if out.is_file() and out.stat().st_size == f["size"] and sha256(out) == f["sha256"]:
            skipped += 1
            continue
        src = common.object_path(f["sha256"])
        if not src.is_file():
            raise SystemExit("store object missing for %s: %s" % (f["path"], src))
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".fetch")
        shutil.copyfile(src, tmp)
        if sha256(tmp) != f["sha256"]:
            tmp.unlink()
            raise SystemExit("hash mismatch fetching %s" % f["path"])
        os.replace(tmp, out)
        n += 1
    print("fetched %d files to %s (%d already there)" % (n, dest, skipped))


def save_manifest(m):
    out = {k: v for k, v in m.items() if k != "by_path"}
    out["files"] = sorted(out["files"], key=lambda f: f["path"])
    tmp = common.MANIFEST.with_name(common.MANIFEST.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    os.replace(tmp, common.MANIFEST)
    copy = common.STORE / "manifests" / "monster3d" / "ART-MANIFEST.json"
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(common.MANIFEST, copy)


def put_object(src: Path, digest: str):
    obj = common.object_path(digest)
    if obj.is_file() and obj.stat().st_size == src.stat().st_size and sha256(obj) == digest:
        return False
    tmpd = common.STORE / "tmp"
    tmpd.mkdir(parents=True, exist_ok=True)
    tmp = tmpd / (digest + ".put")
    shutil.copyfile(src, tmp)
    if sha256(tmp) != digest:
        tmp.unlink()
        raise SystemExit("hash mismatch copying %s to the store" % src)
    obj.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, obj)
    return True


def put(args):
    min_kib, delete, dry, roots = 256, False, False, []
    i = 0
    while i < len(args):
        if args[i] == "--min-kib":
            min_kib = float(args[i + 1]); i += 2; continue
        if args[i] == "--delete":
            delete = True
        elif args[i] == "--dry":
            dry = True
        else:
            roots.append(Path(args[i]).resolve())
        i += 1
    ev = common.EV.resolve()
    files = []
    for r in roots:
        if r.is_dir():
            files += sorted(q for q in r.rglob("*") if q.is_file() and q.stat().st_size >= min_kib * 1024)
        elif r.is_file():
            files.append(r)
        else:
            raise SystemExit("not found: %s" % r)
    m = common.manifest()
    new = copied = deleted = total = 0
    for q in files:
        try:
            logical = q.relative_to(ev).as_posix()
        except ValueError:
            raise SystemExit("%s is not under %s" % (q, ev))
        if q.name.endswith((".fetch", ".tmp", ".put")):
            continue
        total += q.stat().st_size
        if dry:
            print("would put %s (%d)" % (logical, q.stat().st_size))
            continue
        digest, size = sha256(q), q.stat().st_size
        copied += put_object(q, digest)
        ent = {"path": logical, "sha256": digest, "size": size}
        old = m["by_path"].get(logical)
        if old is None:
            m["files"].append(ent); new += 1
        elif old["sha256"] != digest:
            old.update(ent)
        m["by_path"][logical] = m["by_path"].get(logical) or ent
        save_manifest(m)
        if delete:
            obj = common.object_path(digest)
            if obj.stat().st_size == size and sha256(obj) == digest:
                q.unlink(); deleted += 1
            else:
                raise SystemExit("store object of %s did not verify; local file kept" % logical)
    print("%s %d files (%.1f MiB): %d objects copied, %d new manifest entries, %d local files deleted"
          % ("would put" if dry else "put", len(files), total / 2**20, copied, new, deleted))


def main(a):
    if not a:
        raise SystemExit(__doc__)
    cmd, rest = a[0], a[1:]
    if cmd == "where":
        for p in patterns(rest):
            print(common.art(p))
    elif cmd == "list":
        for f in select(patterns(rest)):
            print("%s  %d  %s" % (f["sha256"][:12], f["size"], f["path"]))
    elif cmd == "fetch":
        if rest and rest[0] == "--in-place":
            dest, pats = common.EV, rest[1:]
        else:
            dest, pats = Path(rest[0]), rest[1:]
        fetch(dest, select(patterns(pats)))
    elif cmd == "tools":
        for old, t in sorted(common.manifest()["toolchain"].items()):
            print("%-22s %s" % (old, common.tool(old)))
        print("BLENDER", common.BLENDER, common.BLENDER.is_file())
        print("ESRGAN ", common.ESRGAN, common.ESRGAN.is_file())
    elif cmd == "put":
        put(rest)
    elif cmd == "check":
        ents = select(patterns(rest)) if rest else common.manifest()["files"]
        bad = [f["path"] for f in {f["sha256"]: f for f in ents}.values()
               if not common.object_path(f["sha256"]).is_file() or sha256(common.object_path(f["sha256"])) != f["sha256"]]
        print("checked %d objects, %d bad" % (len({f["sha256"] for f in ents}), len(bad)))
        for b in bad:
            print("  BAD", b)
        sys.exit(1 if bad else 0)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
