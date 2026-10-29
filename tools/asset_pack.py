"""The asset pack: assets/ (Median XL's own files, the HD art) as a versioned, downloadable archive.

assets/ is not in git. `assets.lock` (repo root) pins the pack the checkout builds against: version, file name, size,
sha256 of the pack, sha256 of its manifest, and where to download it from. The pack holds the tree of assets/ plus
`assets-manifest.json` (path, size, sha256 of every file); after unpacking, that manifest sits at assets/assets-manifest.json.

  asset_pack.py fetch    [--from SRC] [--dest DIR] [--force] [--link]   put the pinned pack into assets/
  asset_pack.py verify   [--dir DIR] [--full] [--strict]                  compare assets/ with the manifest and assets.lock
  asset_pack.py build    --version V [--format zip|tar.xz] [--out DIR]    make assets-<V>.<ext> + manifest from assets/
                         [--write-lock]
  asset_pack.py adopt    [--dir DIR]                                      an assets/ from before the pack (LFS checkout) that equals the
                                                                          pinned pack: write its manifest, no download
  asset_pack.py scan     [--dir DIR]                                      text files of assets/ against tools/check_public.py's rules (build runs it)
  asset_pack.py check-pack FILE                                           sha256/size of a pack file against assets.lock

Where fetch looks (first hit wins): `--from SRC`, env MXL_ASSETS, the download cache (env MXL_ASSETS_CACHE, default
~/.cache/mxl2012-d2r/assets), the build PC's pack folder <MXL2012_RUNS>/assetpack/pack (where the pack is built, docs/setup.md
step 4), then the URLs of assets.lock. SRC is a pack file, a directory holding the pack (also in a
`<version>/` subfolder), a directory that already is an unpacked tree (median/, hd/, assets-manifest.json: CI cache and the game PC;
with --link assets/ becomes a junction/symlink to it, no copy), or a file:// / http(s):// URL. Every pack is checked against
the sha256 and size in assets.lock before it is unpacked, and every unpacked file against the manifest.
A read token for the private forge release (env MXL_ASSETS_TOKEN: a Forgejo access token with read:repository) is sent as
`Authorization: token ...` to git.werdegames.com URLs only (CI's `assets` job, docs/setup.md "CI asset pack"); a GitHub token
(MXL_ASSETS_TOKEN or GITHUB_TOKEN) as a bearer header to github.com URLs only. Never anywhere else.

Exit codes: 0 ok, 1 mismatch / failure, 2 usage or nothing to fetch from.
"""
from __future__ import annotations

import pathlib as _pl, sys as _sys; _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent)); import projtemp  # noqa: E402,E702,F401  (temp files stay inside the project, tools/projtemp.py)
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
LOCK = ROOT / "assets.lock"
MANIFEST = "assets-manifest.json"
STAMP = ".asset-pack-verified.json"       # inside assets/: stat snapshot of the last full verification (git-ignored with assets/)
RACY_NS = 5_000_000_000                    # files modified less than this long before a check are not trusted by the stat snapshot
FIXED_TIME = (1980, 1, 1, 0, 0, 0)         # zip entries: the pack is byte-identical for the same tree
CHUNK = 1 << 20
LFS_POINTER = b"version https://git-lfs"
REPO = "Nugwa628/mxl2012-d2r"
DOWNLOAD_BASE = "https://dl.werdegames.com/mxl2012/"  # the download host (docs/hosting.md); publish_release.py --assets puts packs in assets/
FORGE = "https://git.werdegames.com/"
# the private release the pack is downloaded from until the owner approves public hosting (docs/setup.md "CI asset pack")
FORGE_RELEASES = FORGE + "WerdeGames/mxl2012-assets/releases/download/"
RUNS = projtemp.runs_dir()
LOCAL_PACKS = RUNS / "assetpack" / "pack"   # the build PC: tools/asset_pack.py build --out here (docs/setup.md step 4)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def read_lock(path: Path | None = None) -> dict:
    path = path or LOCK
    if not path.exists():
        sys.exit(f"{path.name} missing: the pack this checkout builds against is not pinned")
    return json.loads(path.read_text("utf-8"))


def list_tree(root: Path) -> list[str]:
    """Posix relative paths of every file under root (not the manifest or the stamp), sorted."""
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for n in filenames:
            rel = (Path(dirpath) / n).relative_to(root).as_posix()
            if rel not in (MANIFEST, STAMP):
                out.append(rel)
    return sorted(out)


def manifest_bytes(version: str, files: list[dict]) -> bytes:
    return (json.dumps({"version": version, "files": files}, indent=0, sort_keys=True) + "\n").encode("utf-8")


def is_link(p: Path) -> bool:
    if p.is_symlink():
        return True
    try:  # NTFS junction
        return bool(os.lstat(p).st_file_attributes & 0x400)
    except (AttributeError, OSError):
        return False


def remove_tree(p: Path) -> None:
    """Delete a tree, or just the link if p is a junction/symlink (never the target)."""
    if is_link(p):
        os.rmdir(p) if os.name == "nt" else p.unlink()
    elif p.exists():
        shutil.rmtree(p)


# ----------------------------------------------------------------------------------------------------------------- scan

NOT_PRIVATE = (  # check_public hits that are Median / Blizzard data: file names with an @ in them, Blizzard's own address
    ("email", re.compile(r"\.(cof|dcc|dc6|dt1|ds1|d2|txt|bin|tbl)$|@blizzard\.com$", re.I)),
)


def scan_text(root: Path) -> list[str]:
    """Private details (CI server, user-home paths, machine names, internal hosts, credentials) in the text files of root."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import check_public as cp
    hits = {}
    for rel in list_tree(root):
        p = root / rel
        if p.stat().st_size > 60_000_000:
            continue
        data = p.read_bytes()
        if b"\0" in data[:8192]:
            continue
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for rule, m in cp.scan_line(line):
                if any(rule == r and rx.search(m) for r, rx in NOT_PRIVATE):
                    continue
                hits.setdefault((rel, rule, m), n)
    return [f"{rel}:{n}: [{rule}] {m}" for (rel, rule, m), n in sorted(hits.items())]


def cmd_scan(args) -> int:
    hits = scan_text(Path(args.dir))
    print("\n".join(hits) if hits else f"{args.dir}: no private details in its text files")
    return 1 if hits else 0


# ---------------------------------------------------------------------------------------------------------------- build

def build(args) -> int:
    src = Path(args.src)
    if not (src / "median").is_dir():
        print(f"{src} has no median/ folder: nothing to pack")
        return 1
    rels = list_tree(src)
    if not args.no_scan:
        hits = scan_text(src)
        if hits:
            print("\n".join(hits[:30]))
            print(f"{len(hits)} private detail(s) in the text files of {src}: scrub them (or --no-scan) before building a public pack")
            return 1
    ext = {"zip": ".zip", "tar.xz": ".tar.xz"}[args.format]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pack = out_dir / f"assets-{args.version}{ext}"
    tmp = pack.with_name(pack.name + ".part")
    t0 = time.time()
    files, total = [], 0
    if args.format == "zip":
        zf = zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=args.level)
        add = lambda rel, size, fh: _zip_add(zf, rel, size, fh)
        put_bytes = lambda rel, data: _zip_add(zf, rel, len(data), io.BytesIO(data))
        close = zf.close
    else:
        import lzma
        raw = open(tmp, "wb")
        xz = lzma.LZMAFile(raw, "wb", format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=args.level)
        tf = tarfile.open(fileobj=xz, mode="w", format=tarfile.PAX_FORMAT)
        add = lambda rel, size, fh: _tar_add(tf, rel, size, fh)
        put_bytes = lambda rel, data: _tar_add(tf, rel, len(data), io.BytesIO(data))
        close = lambda: (tf.close(), xz.close(), raw.close())
    ok = False
    try:
        for rel in rels:
            p = src / rel
            size = p.stat().st_size
            with open(p, "rb") as fh:
                if fh.read(40).startswith(LFS_POINTER):
                    print(f"{rel} is a Git LFS pointer, not the file: run `git lfs pull` in a checkout that still has assets in LFS")
                    return 1
                fh.seek(0)
                h = hashlib.sha256()
                add(rel, size, _Hashing(fh, h))
            files.append({"path": rel, "size": size, "sha256": h.hexdigest()})
            total += size
        data = manifest_bytes(args.version, files)
        put_bytes(MANIFEST, data)
        ok = True
    finally:
        close()
        if not ok:
            tmp.unlink(missing_ok=True)
    os.replace(tmp, pack)
    (out_dir / f"assets-{args.version}.manifest.json").write_bytes(data)
    lock = {
        "version": args.version,
        "tag": f"assets-{args.version}",
        "file": pack.name,
        "format": args.format,
        "size": pack.stat().st_size,
        "sha256": sha256_file(pack),
        "manifest_sha256": hashlib.sha256(data).hexdigest(),
        "files": len(files),
        "bytes": total,
        "urls": [f"{FORGE_RELEASES}assets-{args.version}/{pack.name}"],
    }
    print(f"{pack}: {lock['size']:,} bytes from {total:,} bytes in {len(files)} files ({time.time() - t0:.0f} s)")
    print(f"  sha256 {lock['sha256']}")
    if args.write_lock:
        old = json.loads(LOCK.read_text("utf-8")) if LOCK.exists() else {}
        lock["urls"] = old.get("urls") if old.get("version") == args.version and old.get("urls") else lock["urls"]
        LOCK.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {LOCK.name}")
    else:
        print(json.dumps(lock, indent=2))
    return 0


class _Hashing:
    def __init__(self, fh, h):
        self.fh, self.h = fh, h

    def read(self, n=-1):
        b = self.fh.read(n)
        self.h.update(b)
        return b


def _zip_add(zf: zipfile.ZipFile, rel: str, size: int, fh) -> None:
    zi = zipfile.ZipInfo(rel, FIXED_TIME)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.external_attr = 0o644 << 16
    with zf.open(zi, "w", force_zip64=size >= 1 << 31) as dst:
        shutil.copyfileobj(fh, dst, CHUNK)


def _tar_add(tf: tarfile.TarFile, rel: str, size: int, fh) -> None:
    ti = tarfile.TarInfo(rel)
    ti.size, ti.mtime, ti.mode = size, 0, 0o644
    tf.addfile(ti, fh)


# --------------------------------------------------------------------------------------------------------------- verify

def stat_digest(root: Path, rels: list[str]) -> str:
    h = hashlib.sha256()
    for rel in rels:
        st = (root / rel).stat()
        h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def verify_tree(root: Path, lock: dict | None, full: bool = False, strict: bool = False, quiet: bool = False) -> tuple[bool, str]:
    """(ok, reason). Missing or changed files fail; extra files only with strict."""
    mpath = root / MANIFEST
    if not mpath.exists():
        return False, f"{root} has no {MANIFEST}"
    mbytes = mpath.read_bytes()
    if lock and hashlib.sha256(mbytes).hexdigest() != lock["manifest_sha256"]:
        return False, f"{root} is not the pinned pack (manifest sha256 differs from assets.lock version {lock['version']})"
    manifest = json.loads(mbytes)
    files = manifest["files"]
    rels = list_tree(root)
    extra = sorted(set(rels) - {f["path"] for f in files})
    stamp_path = root / STAMP
    # quick path: nothing but the files of the manifest, same stat snapshot as the last full verification
    if not full and not extra and stamp_path.exists():
        try:
            stamp = json.loads(stamp_path.read_text("utf-8"))
            if stamp.get("manifest_sha256") == hashlib.sha256(mbytes).hexdigest() \
                    and all((root / f["path"]).exists() for f in files) \
                    and stamp.get("stat") == stat_digest(root, rels):
                return True, "ok (stat snapshot of the last full check unchanged)"
        except (OSError, ValueError):
            pass
    missing, bad = [], []
    done = 0
    for f in files:
        p = root / f["path"]
        if not p.is_file():
            missing.append(f["path"])
        elif p.stat().st_size != f["size"] or sha256_file(p) != f["sha256"]:
            bad.append(f["path"])
        done += 1
        if not quiet and done % 2000 == 0:
            print(f"  verified {done}/{len(files)}", flush=True)
    if missing or bad or (strict and extra):
        parts = []
        for label, lst in (("missing", missing), ("changed", bad), ("extra", extra if strict else [])):
            if lst:
                parts.append(f"{len(lst)} {label} (e.g. {', '.join(lst[:3])})")
        return False, "; ".join(parts)
    # No stamp while any file is younger than RACY_NS: a same-size edit within the file system's timestamp granularity
    # would keep the same (size, mtime) (git's "racy" case), so a build right after a fetch just hashes again.
    try:
        newest = max((root / rel).stat().st_mtime_ns for rel in rels)
        if time.time_ns() - newest > RACY_NS:
            stamp_path.write_text(json.dumps({"manifest_sha256": hashlib.sha256(mbytes).hexdigest(),
                                              "stat": stat_digest(root, rels)}), encoding="utf-8")
        else:
            stamp_path.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass
    note = f" ({len(extra)} extra files not in the pack)" if extra else ""
    return True, f"ok, {len(files)} files{note}"


def cmd_adopt(args) -> int:
    lock = read_lock()
    root = Path(args.dir)
    if not (root / "median").is_dir():
        print(f"{root} has no median/ folder")
        return 1
    files = []
    for rel in list_tree(root):
        p = root / rel
        files.append({"path": rel, "size": p.stat().st_size, "sha256": sha256_file(p)})
    data = manifest_bytes(lock["version"], files)
    if hashlib.sha256(data).hexdigest() != lock["manifest_sha256"]:
        print(f"{root} is not the pinned pack {lock['version']} (its file list / hashes differ): use `fetch --force` for a clean copy")
        return 1
    (root / MANIFEST).write_bytes(data)
    print(f"{root}: equals pack {lock['version']} ({len(files)} files); {MANIFEST} written")
    verify_tree(root, lock, full=True, quiet=True)   # writes the stat snapshot
    return 0


def cmd_verify(args) -> int:
    lock = None if args.no_lock else read_lock()
    root = Path(args.dir)
    ok, why = verify_tree(root, lock, full=args.full, strict=args.strict)
    print(("assets OK: " if ok else "assets DO NOT MATCH: ") + why)
    return 0 if ok else 1


def assets_ok(root: Path | None = None) -> tuple[bool, str]:
    """For tools/build.py: does root (default assets/) match assets.lock? (stat-snapshot fast path)"""
    root = root or ASSETS
    if not root.is_dir():
        return False, f"{root} does not exist"
    return verify_tree(root, read_lock(), quiet=True)


# ----------------------------------------------------------------------------------------------------------------- fetch

def cache_dir() -> Path:
    return Path(os.environ.get("MXL_ASSETS_CACHE") or Path.home() / ".cache" / "mxl2012-d2r" / "assets")


def pack_matches(path: Path, lock: dict) -> bool:
    return path.is_file() and path.stat().st_size == lock["size"] and sha256_file(path) == lock["sha256"]


def find_local(src: str, lock: dict, prefer_tree: bool = False) -> tuple[str, Path] | None:
    """('pack', file) or ('tree', dir) for a local SRC, None when it holds nothing usable."""
    p = Path(src[7:] if src.startswith("file://") else src)
    if p.is_file():
        return "pack", p
    if not p.is_dir():
        return None
    packs = [("pack", c) for c in (p / lock["file"], p / lock["version"] / lock["file"]) if c.is_file()]
    trees = [("tree", c) for c in (p, p / "assets", p / lock["version"], p / lock["version"] / "assets") if (c / MANIFEST).is_file()]
    found = trees + packs if prefer_tree else packs + trees
    return found[0] if found else None


def download(url: str, dest: Path, lock: dict) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "mxl2012-d2r-asset-pack", "Accept": "application/octet-stream"})
    token = os.environ.get("MXL_ASSETS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://github.com/"):
        req.add_header("Authorization", f"Bearer {token}")
    elif os.environ.get("MXL_ASSETS_TOKEN") and url.startswith(FORGE):
        req.add_header("Authorization", f"token {os.environ['MXL_ASSETS_TOKEN']}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    print(f"downloading {url}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(part, "wb") as out:
            total = int(r.headers.get("Content-Length") or lock["size"])
            got, last = 0, time.time()
            while chunk := r.read(CHUNK):
                out.write(chunk)
                got += len(chunk)
                if time.time() - last > 5:
                    print(f"  {got / 1e6:,.0f} / {total / 1e6:,.0f} MB", flush=True)
                    last = time.time()
    except Exception as e:  # noqa: BLE001 - any network failure moves on to the next URL
        print(f"  failed: {e}")
        part.unlink(missing_ok=True)
        return False
    if not pack_matches(part, lock):
        print(f"  downloaded file does not match assets.lock (size {part.stat().st_size:,}, sha256 differs): discarded")
        part.unlink(missing_ok=True)
        return False
    os.replace(part, dest)
    return True


def unpack(pack: Path, dest: Path, fmt: str) -> None:
    dest.mkdir(parents=True)
    if fmt == "zip":
        with zipfile.ZipFile(pack) as zf:
            for zi in zf.infolist():
                _safe(zi.filename)
            zf.extractall(dest)
    else:
        with tarfile.open(pack, "r:xz") as tf:
            for ti in tf.getmembers():
                _safe(ti.name)
            tf.extractall(dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        now = time.time()                  # the tar's mtimes are 0: make them the unpack time (see RACY_NS)
        for rel in list_tree(dest):
            os.utime(dest / rel, (now, now))


def _safe(name: str) -> None:
    parts = Path(name).parts
    if name.startswith(("/", "\\")) or ".." in parts or (parts and ":" in parts[0]):
        sys.exit(f"pack entry {name!r} would leave the destination: pack refused")


def install_tree(staging: Path, dest: Path, force: bool) -> int:
    if dest.exists() or is_link(dest):
        if not force:
            print(f"{dest} exists and does not match assets.lock; --force replaces it (changes in it are lost)")
            return 1
        remove_tree(dest)
    os.replace(staging, dest)
    return 0


def make_link(target: Path, link: Path) -> None:
    if os.name == "nt":
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"mklink /J failed: {r.stdout}{r.stderr}")
    else:
        link.symlink_to(target, target_is_directory=True)


def cmd_fetch(args) -> int:
    lock = read_lock()
    dest = Path(args.dest)
    if dest.is_dir() and not args.force:
        ok, why = verify_tree(dest, lock, quiet=True)
        if ok:
            print(f"{dest} is already the pinned pack {lock['version']}: {why}")
            return 0
    sources = [s for s in (args.src, os.environ.get("MXL_ASSETS")) if s]
    pack = tree = None
    for s in sources:
        if "://" in s and not s.startswith("file://"):
            local = None
        else:
            local = find_local(s, lock, prefer_tree=args.link)
            if local is None:
                print(f"{s}: no {lock['file']} and no unpacked tree there")
                return 2   # a source named by the user must work; do not fall through to a download
        if local:
            kind, p = local
            if kind == "pack":
                pack = p
            else:
                tree = p
            break
        cached = cache_dir() / lock["file"]
        if not download(s, cached, lock):
            return 1   # a source named by the user must work; do not fall through to the lock's URLs
        pack = cached
        break
    if pack is None and tree is None:
        cached = cache_dir() / lock["file"]
        local = local_source(lock, prefer_tree=args.link)
        if pack_matches(cached, lock):
            pack = cached
        elif local:
            kind, p = local
            pack, tree = (p, None) if kind == "pack" else (None, p)
            print(f"from the build PC's pack folder: {p}")
        else:
            for url in lock.get("urls", []):
                if download(url, cached, lock):
                    pack = cached
                    break
    if pack is None and tree is None:
        print("no pack found. Give one with `--from PATH` / MXL_ASSETS (a pack file, a folder holding it, or an unpacked tree),\n"
              f"or download {lock['file']} from {', '.join(lock.get('urls', [])) or '(no url in assets.lock)'}\n"
              f"into {cache_dir()}")
        return 2
    t0 = time.time()
    if tree is not None:
        ok, why = verify_tree(tree, lock, full=True)
        if not ok:
            print(f"{tree}: {why}")
            return 1
        if args.link:
            staging_ok = (dest.exists() or is_link(dest)) and not args.force
            if staging_ok:
                print(f"{dest} exists; --force replaces it")
                return 1
            if dest.exists() or is_link(dest):
                remove_tree(dest)
            make_link(tree.resolve(), dest)
            print(f"{dest} -> {tree.resolve()} ({why}, {time.time() - t0:.0f} s)")
            return 0
        staging = dest.with_name(dest.name + f".tmp{os.getpid()}")
        shutil.copytree(tree, staging)
    else:
        if not pack_matches(pack, lock):
            print(f"{pack} does not match assets.lock (size {pack.stat().st_size:,} vs {lock['size']:,}, or sha256): refused")
            return 1
        print(f"unpacking {pack} ({pack.stat().st_size / 1e6:,.0f} MB)")
        staging = dest.with_name(dest.name + f".tmp{os.getpid()}")
        shutil.rmtree(staging, ignore_errors=True)
        try:
            unpack(pack, staging, lock["format"])
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    ok, why = verify_tree(staging, lock, full=True)
    if not ok:
        shutil.rmtree(staging, ignore_errors=True)
        print(f"unpacked tree failed verification: {why}")
        return 1
    rc = install_tree(staging, dest, args.force)
    if rc:
        shutil.rmtree(staging, ignore_errors=True)
        return rc
    print(f"{dest}: {why} ({time.time() - t0:.0f} s)")
    return 0


def local_source(lock: dict, prefer_tree: bool = False) -> tuple[str, Path] | None:
    """The pinned pack (or its unpacked tree) in LOCAL_PACKS, if the build PC has it there."""
    if not LOCAL_PACKS.is_dir():
        return None
    found = find_local(str(LOCAL_PACKS), lock, prefer_tree)
    if found and found[0] == "pack" and not pack_matches(found[1], lock):
        return None
    return found


def cmd_check_pack(args) -> int:
    lock = read_lock()
    p = Path(args.file)
    if p.is_dir():
        p = p / lock["file"]
    if pack_matches(p, lock):
        print(f"{p}: matches assets.lock {lock['version']} ({p.stat().st_size:,} bytes)")
        return 0
    print(f"{p}: missing or differs from assets.lock {lock['version']} (size {lock['size']:,}, sha256 {lock['sha256'][:16]}...)")
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="put the pinned pack into assets/")
    f.add_argument("--from", dest="src", help="pack file, folder with the pack, unpacked tree, or URL (default: env MXL_ASSETS, cache, assets.lock urls)")
    f.add_argument("--dest", default=str(ASSETS))
    f.add_argument("--force", action="store_true", help="replace an existing destination that does not match")
    f.add_argument("--link", action="store_true", help="from an unpacked tree: junction/symlink instead of a copy")
    v = sub.add_parser("verify", help="check a local assets/ against its manifest and assets.lock")
    v.add_argument("--dir", default=str(ASSETS))
    v.add_argument("--full", action="store_true", help="hash every file even if the stat snapshot is unchanged")
    v.add_argument("--strict", action="store_true", help="files that are not in the manifest also fail")
    v.add_argument("--no-lock", action="store_true", help="only check against the tree's own manifest")
    b = sub.add_parser("build", help="make assets-<version>.zip|.tar.xz and its manifest from assets/")
    b.add_argument("--version", required=True)
    b.add_argument("--format", choices=("zip", "tar.xz"), default="zip")
    b.add_argument("--level", type=int, default=None, help="deflate level (default 9) or xz preset (default 6)")
    b.add_argument("--src", default=str(ASSETS))
    b.add_argument("--out", default=str(ROOT / "build" / "asset-pack"))
    b.add_argument("--no-scan", action="store_true", help="skip the check_public scan of the text files")
    b.add_argument("--write-lock", action="store_true", help="write assets.lock for this pack")
    a = sub.add_parser("adopt", help="an assets/ from an LFS checkout that equals the pinned pack: write its manifest")
    a.add_argument("--dir", default=str(ASSETS))
    sc = sub.add_parser("scan", help="text files of assets/ against tools/check_public.py's rules")
    sc.add_argument("--dir", default=str(ASSETS))
    c = sub.add_parser("check-pack", help="a pack file (or folder holding it) against assets.lock")
    c.add_argument("file")
    args = ap.parse_args(argv)
    if args.cmd == "build" and args.level is None:
        args.level = 9 if args.format == "zip" else 6
    return {"fetch": cmd_fetch, "verify": cmd_verify, "build": build, "adopt": cmd_adopt, "scan": cmd_scan, "check-pack": cmd_check_pack}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
