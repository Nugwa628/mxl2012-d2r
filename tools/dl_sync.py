#!/usr/bin/env python3
"""Mirror the download site (/srv/dl/mxl) to the DigitalOcean Space that players download from (docs/hosting.md
"DigitalOcean Spaces + Cloudflare"). Runs ON the download host as the upload user (mxlup), started by systemd after every
ingest, promote and gc (a path unit on <site>/.sync/wanted) and by a timer every 30 minutes. Needs python3 (stdlib, 3.9+)
and rclone (Debian package rclone; a remote `spaces` in /etc/mxl-dl/rclone.conf).

  /srv/dl/mxl/<rel>  ->  spaces:d2r-xl/mxl/<rel>  ->  https://files.werdegames.com/mxl/<rel>   (same layout)

One pass, in this order, so a player never sees a channel that points at something the Space does not have yet:

  1. everything but channels/: objects/ first, then releases/ (the 7z, notes, SHA256SUMS), launcher/, assets/, and the
     release manifests last. Only files the Space lacks or that changed are uploaded; nothing is deleted.
  2. channels/*.json.
  3. deletions: files on the Space the site no longer has (what gc removed), never an object a local release still uses,
     and only after 1 and 2 went through.

What is new or changed: an object (named by its sha256) when the Space lacks it or has another size; any other file also
when its sha256 differs from what the last upload recorded (the manifest <state>/uploaded.json). JSON files are copied
into <state>/stage/ when the pass starts and uploaded from there, so a channel file the ingest rewrites during the pass
cannot reach the Space before the objects of its release. Every upload sets Cache-Control and Content-Type (HEADERS) and
the public-read ACL. Never uploaded: dot files and folders (.sync/), temp files (*.part-*), links, anything outside the
known prefixes. When <site>/.sync/wanted changed during a pass, another pass follows.

<site>/.sync/status.json (a dot file: Caddy does not serve it; `publish_release.py list` shows it over SFTP) records the
last run. A lock in the state folder keeps two runs apart. Exit status 0 = the Space matches the site, 1 = failed.

  python3 -I /opt/mxl-dl/dl_sync.py [--site /srv/dl/mxl] [--remote spaces:d2r-xl/mxl] [--dry-run] [--no-delete]
  python3 -I /opt/mxl-dl/dl_sync.py --check [--sample 50 | --full]    compare the Space with the site (size, sha256, headers)
"""
import argparse
import datetime
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SITE = "/srv/dl/mxl"
REMOTE = "spaces:d2r-xl/mxl"
CONFIG = "/etc/mxl-dl/rclone.conf"
STATE = "/var/lib/mxl-dl-sync"
SYNC_DIR = ".sync"  # in the site: `wanted` (the trigger) and `status.json`; a dot folder, so neither served nor mirrored
STATUS_SCHEMA = 1
PREFIXES = ("objects", "releases", "launcher", "assets", "channels")
PART_RE = re.compile(r"\.part-[0-9a-z]+$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_NAME = "release-manifest.json"
MAX_PASSES = 5
LOCK_WAIT = 3 * 3600
IMMUTABLE = "public, max-age=31536000, immutable"
HOUR = "public, max-age=3600"
# every rclone call: no bucket creation (the key may only touch d2r-xl), public objects, quiet unless something goes wrong
RCLONE_COMMON = ["--s3-no-check-bucket", "--s3-acl", "public-read", "--retries", "3", "--low-level-retries", "10",
                 "--stats", "0", "--log-level", "NOTICE"]
RCLONE_COPY = ["--transfers", "8", "--checkers", "16", "--no-traverse", "--ignore-times"]
JOURNAL = bool(os.environ.get("JOURNAL_STREAM"))
CONTENT_TYPES = {".json": "application/json", ".7z": "application/x-7z-compressed", ".exe": "application/octet-stream",
                 ".md": "text/markdown; charset=utf-8", ".sha256": "text/plain; charset=utf-8",
                 ".txt": "text/plain; charset=utf-8", ".xz": "application/x-xz", ".zip": "application/zip"}


class SyncError(Exception):
    pass


def log(msg, error=False):
    print(("<3>" if error and JOURNAL else "") + msg, file=sys.stderr if error and not JOURNAL else sys.stdout, flush=True)


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_atomic(dest: Path, data: bytes):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.part-{os.getpid():x}")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, dest)


# --------------------------------------------------------------------------------------------------------- what goes up
def mirrored(rel: str) -> bool:
    """A site path that belongs on the Space: under a known prefix, no dot segment, not a temp file."""
    parts = rel.split("/")
    return len(parts) >= 2 and parts[0] in PREFIXES and not any(p.startswith(".") or not p for p in parts) \
        and not PART_RE.search(parts[-1])


def headers(rel: str):
    """-> (Cache-Control, Content-Type) for a mirrored path."""
    top, ext = rel.split("/", 1)[0], os.path.splitext(rel)[1].lower()
    if top == "objects":
        return IMMUTABLE, "application/octet-stream"
    if top == "channels":
        return "no-cache", "application/json"
    if rel.rsplit("/", 1)[-1] == "SHA256SUMS":
        return HOUR, "text/plain; charset=utf-8"
    return HOUR, CONTENT_TYPES.get(ext, "application/octet-stream")


def phase(rel: str) -> int:
    """Upload order: 0 objects, 1 the rest, 2 release manifests (they name the 7z), 3 channels. Deletions come after all."""
    top, name = rel.split("/", 1)[0], rel.rsplit("/", 1)[-1]
    if top == "objects":
        return 0
    if top == "channels":
        return 3
    return 2 if top == "releases" and name == MANIFEST_NAME else 1


def scan(site: Path) -> dict:
    """-> {rel: (size, mtime_ns)} of every mirrored file (links and dot folders are not followed)."""
    out, other = {}, []
    for dirpath, dirnames, filenames in os.walk(site):
        d = Path(dirpath)
        dirnames[:] = sorted(n for n in dirnames if not n.startswith(".") and not (d / n).is_symlink())
        for n in filenames:
            p = d / n
            rel = p.relative_to(site).as_posix()
            if p.is_symlink() or not p.is_file():
                continue
            if mirrored(rel):
                st = p.stat()
                out[rel] = (st.st_size, st.st_mtime_ns)
            elif not n.startswith(".") and not PART_RE.search(n):
                other.append(rel)
    if other:
        log(f"not mirrored (outside {', '.join(PREFIXES)}): {', '.join(sorted(other)[:5])}{' ...' if len(other) > 5 else ''}")
    return out


# ---------------------------------------------------------------------------------------------------------------- rclone
class Rclone:
    def __init__(self, remote=REMOTE, config=CONFIG, binary=None, work: Path = None, cache_dir=None):
        self.remote = remote.rstrip("/")
        self.binary = binary or shutil.which("rclone")
        if not self.binary:
            raise SyncError("no rclone (apt install rclone)")
        self.base = [self.binary, "--config", str(config), *RCLONE_COMMON] + (["--cache-dir", str(cache_dir)] if cache_dir else [])
        self.work = work

    def run(self, args, ok=(0,), stdout=subprocess.PIPE):
        r = subprocess.run(self.base + args, stdout=stdout, stderr=subprocess.PIPE, text=stdout is not None, errors="replace")
        if r.returncode not in ok:
            raise SyncError(f"rclone {args[0]} failed ({r.returncode}): {(r.stderr or '').strip()[-500:]}")
        return r

    def list(self) -> dict:
        """{rel: size} of everything under the remote prefix ({} when it does not exist yet)."""
        r = self.run(["lsjson", "-R", "--files-only", "--no-modtime", "--no-mimetype", self.remote], ok=(0, 3))
        if r.returncode == 3:  # directory not found: an empty Space
            return {}
        return {e["Path"]: e["Size"] for e in json.loads(r.stdout or "[]")}

    def _files_from(self, rels) -> str:
        fd, path = tempfile.mkstemp(prefix="files-", suffix=".txt", dir=self.work)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(r + "\n" for r in rels))
        return path

    def upload(self, src: Path, rels, cache_control, content_type):
        lst = self._files_from(rels)
        try:
            self.run(["copy", str(src), self.remote, "--files-from", lst, *RCLONE_COPY,
                      "--header-upload", f"Cache-Control: {cache_control}", "--header-upload", f"Content-Type: {content_type}"])
        finally:
            os.unlink(lst)

    def delete(self, rels):
        lst = self._files_from(rels)
        try:
            self.run(["delete", self.remote, "--files-from", lst])
        finally:
            os.unlink(lst)

    def sha256(self, rel) -> str:
        h = hashlib.sha256()
        with subprocess.Popen(self.base + ["cat", f"{self.remote}/{rel}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
            for chunk in iter(lambda: p.stdout.read(1 << 20), b""):
                h.update(chunk)
            err = p.stderr.read()
        if p.returncode != 0:
            raise SyncError(f"rclone cat {rel} failed ({p.returncode}): {err.decode('utf-8', 'replace').strip()[-300:]}")
        return h.hexdigest()

    def metadata(self, rel) -> dict:
        r = self.run(["lsjson", "-M", "--files-only", f"{self.remote}/{rel}"])
        entries = json.loads(r.stdout or "[]")
        return {k.lower(): v for k, v in (entries[0].get("Metadata") or {}).items()} if entries else {}


# ------------------------------------------------------------------------------------------------------------------ sync
class Sync:
    def __init__(self, site: Path, state: Path, rclone: Rclone, dry_run=False, delete=True, mass_delete=False):
        self.site, self.state, self.rc = Path(site), Path(state), rclone
        self.dry_run, self.delete, self.mass_delete = dry_run, delete, mass_delete
        self.stage = self.state / "stage"
        self.manifest_path = self.state / "uploaded.json"
        self.uploaded = self.deleted = 0
        self.bytes = 0
        if not self.site.is_dir():
            raise SyncError(f"{self.site} is not a folder")

    def load_manifest(self) -> dict:
        try:
            return json.loads(self.manifest_path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def save_manifest(self, man):
        if not self.dry_run:
            write_atomic(self.manifest_path, (json.dumps(man, indent=0, sort_keys=True) + "\n").encode())

    def snapshot(self, local) -> dict:
        """Copy the JSON files (channels, release manifests, asset indexes) into the stage folder: {rel: (bytes, sha256)}.
        A file that vanished since the scan (gc) is dropped from `local`."""
        shutil.rmtree(self.stage, ignore_errors=True)
        snap = {}
        for rel in [r for r in local if r.endswith(".json") and not r.startswith("objects/")]:
            try:
                data = (self.site / rel).read_bytes()
            except FileNotFoundError:
                del local[rel]
                continue
            local[rel] = (len(data), local[rel][1])
            snap[rel] = (data, hashlib.sha256(data).hexdigest())
            if not self.dry_run:
                dest = self.stage.joinpath(*rel.split("/"))
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        return snap

    def plan(self, local, remote, man, snap):
        """-> [(rel, size, mtime_ns, sha256 or None)] to upload, in phase order, and [rel] to delete."""
        ups = []
        for rel in sorted(local, key=lambda r: (phase(r), r)):
            size, mtime = local[rel]
            have = remote.get(rel)
            if rel.startswith("objects/"):
                if have != size:
                    ups.append((rel, size, mtime, None))
                continue
            rec = man.get(rel)
            # the staged JSON files are compared by sha256 always (cheap); the rest by size and mtime first
            if have == size and rec and rec.get("size") == size and rel not in snap and rec.get("mtime_ns") == mtime:
                continue
            sha = snap[rel][1] if rel in snap else sha256_file(self.site / rel)
            if have == size and rec and rec.get("sha256") == sha:
                rec["mtime_ns"] = mtime
                continue
            ups.append((rel, size, mtime, sha))
        dels = sorted(r for r in remote if r not in local and r.split("/", 1)[0] in PREFIXES)
        return ups, dels

    def referenced(self, snap) -> set:
        """Objects the site's release manifests use: never deleted from the Space."""
        refs = set()
        for rel, (data, _) in snap.items():
            if rel.startswith("releases/") and rel.endswith("/" + MANIFEST_NAME):
                try:
                    refs |= {f"objects/{f['sha256'][:2]}/{f['sha256']}" for f in json.loads(data)["files"]}
                except (ValueError, KeyError, TypeError) as e:
                    raise SyncError(f"{rel} is not a readable manifest ({e}): not deleting anything")
        return refs

    def run_pass(self):
        local = scan(self.site)
        if not any(r.startswith("channels/") and r.endswith(".json") for r in local):
            raise SyncError(f"{self.site} has no channels/*.json: the site looks empty or unmounted; nothing done")
        snap = self.snapshot(local)
        remote = self.rc.list()
        man = self.load_manifest()
        ups, dels = self.plan(local, remote, man, snap)
        log(f"site {len(local)} files, Space {len(remote)}: {len(ups)} to upload "
            f"({sum(u[1] for u in ups) / 1e6:.1f} MB), {len(dels)} to delete{' (dry run)' if self.dry_run else ''}")
        groups = {}
        for u in ups:
            src = self.stage if u[0] in snap else self.site
            groups.setdefault((phase(u[0]), str(src), *headers(u[0])), []).append(u)
        for (ph, src, cc, ct), items in sorted(groups.items()):
            what = f"{len(items)} files ({sum(i[1] for i in items) / 1e6:.1f} MB) [{ct}; {cc}]"
            if self.dry_run:
                log(f"would upload {what}: {', '.join(i[0] for i in items[:3])}{' ...' if len(items) > 3 else ''}")
                continue
            log(f"uploading {what}")
            self.rc.upload(Path(src), [i[0] for i in items], cc, ct)
            for rel, size, mtime, sha in items:
                if sha is not None:
                    man[rel] = {"size": size, "mtime_ns": mtime, "sha256": sha}
            self.uploaded += len(items)
            self.bytes += sum(i[1] for i in items)
            self.save_manifest(man)
        if dels:
            self.remove(dels, remote, snap, man)
        for rel in [r for r in man if r not in local]:
            del man[rel]
        self.save_manifest(man)
        if not self.dry_run:
            shutil.rmtree(self.stage, ignore_errors=True)

    def remove(self, dels, remote, snap, man):
        if not self.delete:
            log(f"{len(dels)} files on the Space the site no longer has: kept (--no-delete)")
            return
        live = self.referenced(snap) & set(dels)
        if live:
            raise SyncError(f"{len(live)} objects a release on the site uses are missing from the site, e.g. {sorted(live)[0]}: "
                            "not deleting anything (check the site)")
        if len(dels) > max(100, len(remote) // 2) and not self.mass_delete:
            raise SyncError(f"{len(dels)} of {len(remote)} files on the Space would be deleted: refusing (--allow-mass-delete)")
        if self.dry_run:
            log(f"would delete {len(dels)} files: {', '.join(dels[:3])}{' ...' if len(dels) > 3 else ''}")
            return
        log(f"deleting {len(dels)} files the site no longer has")
        self.rc.delete(dels)
        self.deleted += len(dels)
        for rel in dels:
            man.pop(rel, None)


# ----------------------------------------------------------------------------------------------------------------- check
def check(site: Path, rc: Rclone, sample=50, full=False, seed=None) -> int:
    """Compare the Space with the site: every file there with its size, nothing extra; sha256 (and the headers) of the
    channels, the release manifests and `sample` other files (all with full). -> number of problems."""
    local = scan(site)
    remote = rc.list()
    problems = []
    for rel, (size, _) in sorted(local.items()):
        if rel not in remote:
            problems.append(f"missing on the Space: {rel}")
        elif remote[rel] != size:
            problems.append(f"size differs: {rel} (site {size}, Space {remote[rel]})")
    extra = sorted(r for r in remote if r not in local)
    problems += [f"on the Space only: {r}" for r in extra]
    both = sorted(r for r in local if remote.get(r) == local[r][0])
    always = [r for r in both if r.startswith("channels/") or r.endswith("/" + MANIFEST_NAME)]
    rest = [r for r in both if r not in always]
    picked = always + (rest if full else random.Random(seed).sample(rest, min(sample, len(rest))))
    meta_ok = True
    for rel in picked:
        if rc.sha256(rel) != sha256_file(site / rel):
            problems.append(f"content differs (sha256): {rel}")
        if not meta_ok:
            continue
        try:
            meta = rc.metadata(rel)
        except SyncError as e:
            log(f"headers not checked (rclone 1.59 or newer reads them): {e}")
            meta_ok = False
            continue
        cc, ct = headers(rel)
        if meta.get("cache-control") != cc or meta.get("content-type") != ct:
            problems.append(f"headers differ: {rel} (Cache-Control {meta.get('cache-control')!r}, "
                            f"Content-Type {meta.get('content-type')!r}; expected {cc!r}, {ct!r})")
    for p in problems[:50]:
        log(p, error=True)
    log(f"check: {len(local)} files on the site, {len(remote)} on the Space, {len(picked)} compared by sha256: "
        + (f"{len(problems)} problems" if problems else "the Space matches the site"), error=bool(problems))
    return len(problems)


# ------------------------------------------------------------------------------------------------------ lock and trigger
def lock(path: Path, wait: float):
    """An exclusive lock on `path` (flock; msvcrt on Windows), waiting up to `wait` seconds -> an fd to close."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + wait
    while True:
        try:
            try:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return fd
        except OSError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise SyncError(f"another dl_sync is running (lock {path})")
            time.sleep(min(5.0, max(0.05, deadline - time.monotonic())))


def stamp(site: Path):
    try:
        st = (site / SYNC_DIR / "wanted").stat()
        return st.st_mtime_ns, st.st_size, st.st_ino
    except OSError:
        return None


def write_status(site: Path, status: dict):
    p = site / SYNC_DIR / "status.json"
    try:
        old = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        old = {}
    if status["result"] == "ok":
        status["lastSuccessAt"] = status["finishedAt"]
    elif old.get("lastSuccessAt"):
        status["lastSuccessAt"] = old["lastSuccessAt"]
    try:
        write_atomic(p, (json.dumps(status, indent=1) + "\n").encode())
    except OSError as e:
        log(f"cannot write {p}: {e}", error=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=Path(SITE), help=f"the served folder (default {SITE})")
    ap.add_argument("--remote", default=REMOTE, help=f"rclone remote and prefix (default {REMOTE})")
    ap.add_argument("--config", default=CONFIG, help=f"rclone config (default {CONFIG})")
    ap.add_argument("--state", type=Path, default=Path(os.environ.get("STATE_DIRECTORY", STATE).split(":")[0]),
                    help=f"lock, upload manifest, stage folder (default $STATE_DIRECTORY or {STATE})")
    ap.add_argument("--rclone", help="rclone binary (default: rclone on PATH)")
    ap.add_argument("--dry-run", action="store_true", help="show what would be uploaded and deleted; change nothing")
    ap.add_argument("--no-delete", action="store_true", help="upload only; keep files the site no longer has")
    ap.add_argument("--allow-mass-delete", action="store_true", help="allow deleting more than half of the Space")
    ap.add_argument("--check", action="store_true", help="compare the Space with the site instead of syncing")
    ap.add_argument("--sample", type=int, default=50, help="--check: files besides channels and manifests to hash (default 50)")
    ap.add_argument("--full", action="store_true", help="--check: hash every file")
    ap.add_argument("--lock-wait", type=float, default=LOCK_WAIT, help=f"seconds to wait for a running sync (default {LOCK_WAIT})")
    a = ap.parse_args(argv)
    site = a.site.resolve()
    held = None
    status = {"schemaVersion": STATUS_SCHEMA, "remote": a.remote, "startedAt": now_utc(), "result": "failed"}
    try:
        held = lock(a.state / "lock", a.lock_wait)
        rc = Rclone(a.remote, a.config, a.rclone, a.state, a.state / "cache")
        if a.check:
            return 1 if check(site, rc, a.sample, a.full) else 0
        sync = Sync(site, a.state, rc, a.dry_run, not a.no_delete, a.allow_mass_delete)
        for n in range(1, MAX_PASSES + 1):
            before = stamp(site)
            sync.run_pass()
            if a.dry_run or stamp(site) == before:
                break
            log(f"the site changed during pass {n} ({SYNC_DIR}/wanted): once more")
        status.update(result="ok", uploaded=sync.uploaded, deleted=sync.deleted, uploadedMB=round(sync.bytes / 1e6, 1))
        log(f"done: {sync.uploaded} uploaded ({sync.bytes / 1e6:.1f} MB), {sync.deleted} deleted"
            + (" (dry run: nothing changed)" if a.dry_run else ""))
        return 0
    except SyncError as e:
        status["error"] = str(e)
        log(f"error: {e}", error=True)
        return 1
    finally:
        if not a.dry_run and not a.check and held is not None:
            status["finishedAt"] = now_utc()
            write_status(site, status)
        if held is not None:
            os.close(held)


if __name__ == "__main__":
    sys.exit(main())
