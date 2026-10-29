#!/usr/bin/env python
"""Isolation check for the launcher (docs/launcher.md "Testing"): a hash snapshot of folders before an install / play,
and the comparison afterwards. The launcher must leave the player's real D2R folder, other mods' folders (D2RMM's
output mod) and other saves byte for byte as they were.

  py -3 tools/launcher_isolation.py snapshot --out before.json DIR [DIR ...] [--exclude REL_PREFIX ...]
  py -3 tools/launcher_isolation.py compare before.json after.json

Each file is recorded by path, size, mtime and sha256. --exclude takes paths relative to one of the DIRs (prefix match,
case-insensitive), e.g. the launcher's own save folder. compare prints every added, removed or changed file and exits
1 when there is one.
"""
import argparse
import hashlib
import json
import os
import sys
import time


def sha256_file(p, chunk=4 << 20):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                return h.hexdigest()
            h.update(b)


def snapshot(a) -> int:
    excl = [e.replace("\\", "/").strip("/").lower() for e in a.exclude]
    out = {"taken": time.strftime("%Y-%m-%d %H:%M:%S"), "roots": {}}
    for root in a.dirs:
        files = {}
        t0 = time.time()
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if not os.path.islink(os.path.join(dp, d))]
            for fn in fns:
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, root).replace("\\", "/")
                if any(rel.lower() == e or rel.lower().startswith(e + "/") for e in excl):
                    continue
                st = os.stat(p)
                files[rel] = [st.st_size, st.st_mtime_ns, sha256_file(p)]
        out["roots"][os.path.abspath(root)] = files
        print(f"{root}: {len(files)} files, {sum(v[0] for v in files.values()) / 2**30:.1f} GB, {time.time() - t0:.0f} s")
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f)
    return 0


def compare(a) -> int:
    with open(a.before, encoding="utf-8") as f:
        before = json.load(f)
    with open(a.after, encoding="utf-8") as f:
        after = json.load(f)
    bad = 0
    for root, b in before["roots"].items():
        c = after["roots"].get(root)
        if c is None:
            print(f"{root}: missing from the second snapshot")
            bad += 1
            continue
        diffs = [f"  added   {p}" for p in sorted(set(c) - set(b))]
        diffs += [f"  removed {p}" for p in sorted(set(b) - set(c))]
        diffs += [f"  changed {p}" + ("" if b[p][2] != c[p][2] else " (mtime only)")
                  for p in sorted(set(b) & set(c)) if b[p] != c[p]]
        print(f"{root}: {len(b)} files, {'unchanged' if not diffs else f'{len(diffs)} differences'}")
        for d in diffs[:50]:
            print(d)
        bad += len(diffs)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--out", required=True)
    s.add_argument("--exclude", action="append", default=[])
    s.add_argument("dirs", nargs="+")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    a = ap.parse_args()
    return snapshot(a) if a.cmd == "snapshot" else compare(a)


if __name__ == "__main__":
    sys.exit(main())
