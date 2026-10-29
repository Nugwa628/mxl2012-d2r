"""A stand-in for rclone for tools/test_dl_sync.py: remotes are folders. `<remote>:<path>` is $FAKE_RCLONE_ROOT/<path>;
the headers of every upload go to $FAKE_RCLONE_ROOT/.meta.json ({path: {"cache-control", "content-type", "acl"}}), so
`lsjson -M` can show them. Only what tools/dl_sync.py uses:

  lsjson -R --files-only ... REMOTE:PATH        [{"Path", "Name", "Size", "IsDir"}]; exit 3 when PATH does not exist
  lsjson -M --files-only REMOTE:PATH/FILE      one entry with "Metadata"
  copy SRC REMOTE:PATH --files-from LIST --header-upload "K: V" ... [--s3-acl X]
  delete REMOTE:PATH --files-from LIST
  cat REMOTE:PATH/FILE

FAKE_RCLONE_LOG=FILE appends one JSON line per call: {"argv": [...], "files": [the --files-from list]}.
FAKE_RCLONE_FAIL=TEXT: a copy whose file list holds a path containing TEXT uploads nothing and exits 1.
"""
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ["FAKE_RCLONE_ROOT"])
META = ROOT / ".meta.json"
VALUED = {"--config", "--files-from", "--header-upload", "--s3-acl", "--retries", "--low-level-retries", "--stats",
          "--log-level", "--transfers", "--checkers", "--cache-dir"}


def local(spec: str) -> Path:
    remote, _, path = spec.partition(":")
    return ROOT.joinpath(*[p for p in path.split("/") if p])


def main(argv):
    opts, args, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a in VALUED:
            opts.setdefault(a, []).append(argv[i + 1])
            i += 2
        else:
            (opts.setdefault(a, []).append(True) if a.startswith("-") else args.append(a))
            i += 1
    cmd = args[0]
    files = []
    if "--files-from" in opts:
        files = [ln for ln in Path(opts["--files-from"][0]).read_text("utf-8").splitlines() if ln]
    log = os.environ.get("FAKE_RCLONE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"argv": argv, "files": files}) + "\n")
    meta = json.loads(META.read_text("utf-8")) if META.is_file() else {}
    if cmd == "lsjson":
        base = local(args[1])
        if "-M" in opts:
            if not base.is_file():
                return 3
            key = base.relative_to(ROOT).as_posix()
            print(json.dumps([{"Path": base.name, "Name": base.name, "Size": base.stat().st_size, "IsDir": False,
                               "Metadata": meta.get(key, {})}]))
            return 0
        if not base.is_dir():
            print("directory not found", file=sys.stderr)
            return 3
        out = [{"Path": p.relative_to(base).as_posix(), "Name": p.name, "Size": p.stat().st_size, "IsDir": False}
               for p in sorted(base.rglob("*")) if p.is_file()]
        print(json.dumps(out))
        return 0
    if cmd == "copy":
        src, dest = Path(args[1]), local(args[2])
        fail = os.environ.get("FAKE_RCLONE_FAIL")
        if fail and any(fail in f for f in files):
            print(f"failed to copy: {fail}", file=sys.stderr)
            return 1
        hdr = {}
        for h in opts.get("--header-upload", []):
            k, _, v = h.partition(":")
            hdr[k.strip().lower()] = v.strip()
        hdr["acl"] = (opts.get("--s3-acl") or ["private"])[-1]
        for rel in files:
            d = dest.joinpath(*rel.split("/"))
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src.joinpath(*rel.split("/")), d)
            meta[d.relative_to(ROOT).as_posix()] = hdr
        META.write_text(json.dumps(meta), encoding="utf-8")
        return 0
    if cmd == "delete":
        dest = local(args[1])
        for rel in files:
            p = dest.joinpath(*rel.split("/"))
            p.unlink(missing_ok=True)
            meta.pop(p.relative_to(ROOT).as_posix(), None)
        META.write_text(json.dumps(meta), encoding="utf-8")
        return 0
    if cmd == "cat":
        p = local(args[1])
        if not p.is_file():
            return 3
        sys.stdout.buffer.write(p.read_bytes())
        return 0
    print(f"fake_rclone: unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
