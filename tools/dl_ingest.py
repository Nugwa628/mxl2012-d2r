#!/usr/bin/env python3
"""Server side of a release upload (docs/hosting.md, docs/release.md "Hosting layout"). Runs ON the download host as the
upload user (mxlup), started by the systemd path unit that watches <root>/incoming; needs only python3 (stdlib, 3.9+) and
7-Zip (`7zz` from Debian's package 7zip, or `7z` from 7zip / p7zip-full).

tools/publish_release.py uploads into <root>/<incoming>/<version>.uploading/ and, last, renames that folder to
<root>/<incoming>/<version>/ with a READY file inside:

  READY                        JSON: version, channel, files {name: {size, sha256}}, objectsPack, launcher, force
  release-manifest.json        the release manifest (schemaVersion 2) without "archive": this script builds the 7z
  objects-<sha16>.7z           the objects the host lacked, entries named by their sha256 (absent when it lacked none)
  RELEASE_NOTES-<v>.md         optional
  <launcher-name>              optional (the manifest's "launcher" names it; an older name from 0.1.x publishers too when
                               the defaults file lists one)

For every such folder, in version order:

  1. READY and every file it lists are checked (size, sha256); a file it does not list is refused.
  2. The manifest is checked: schemaVersion 2, the folder's version, safe paths, sha256 / size of every file.
  3. The objects 7z is listed first (only plain files named by a sha256 the manifest uses), unpacked into the scratch folder
     incoming/<v>/.work/, and every file's sha256 must equal its name; then they are moved into <site>/objects/<sha[0:2]>/.
  4. Every object the manifest needs must be on the host. Its bytes are read again (sha256) while the player's folder
     <modFolder>/ is linked together from them, and that folder becomes releases/<v>/<archive-prefix>-<v>.7z (solid LZMA2,
     -mx7, no time stamps), so the big archive never has to come over the uploader's slow line. The manifest gets
     "archive" (name, size, sha256, path).
  5. releases/<v>/ gets the 7z, the notes, release-manifest.json, SHA256SUMS; launcher/<lv>/ the exe and its .sha256.
  6. channels/<channel>.json is written LAST (when READY names a channel).
  7. The incoming folder and the work folder are deleted; *.part-* leftovers older than an hour under the site go too.
  8. When anything was published: <site>/.sync/wanted is rewritten, which starts the mirror to the DigitalOcean Space
     (tools/dl_sync.py, a systemd path unit; this script itself has no network).

One installed copy serves several products (D2R-XL 2012 and others): each runs this script with its own flags, from its own
systemd units, on its own folders. The defaults are the host's first product's, from dl_ingest.defaults.json next to the
installed script (or $DL_INGEST_DEFAULTS): {"site", "incoming", "archive_prefix", "launcher_name",
"legacy_launcher_names": {launcher name: its 0.1.x name}}, so a unit that passes only --root keeps working unchanged.
Without that file --site / --incoming default to `mxl` / `incoming` and --archive-prefix and --launcher-name must be
given. Another product passes --site, --incoming, --archive-prefix and --launcher-name (and --mod-folder, which refuses a
manifest of another product):

  python3 -I /opt/mxl-dl/dl_ingest.py --root /srv/dl --site mxl2012 --incoming incoming-mxl2012 \
      --archive-prefix D2R-XL-2012 --launcher-name D2R-XL-2012-Downloader.exe --mod-folder mxl2012

Every file is written under a temp name and renamed. A failed check writes the reason to incoming/<v>/REFUSED, leaves
the folder for inspection and skips it from then on (exit status 1); `--retry <v>` removes REFUSED and tries again.
Running it again is safe: a version whose published manifest is the same is not built again; a different one is refused
(a published version never changes) unless READY says force. Nothing outside <root> is written.

  python3 -I /opt/mxl-dl/dl_ingest.py [--root /srv/dl] [--site mxl] [--incoming incoming] [--archive-prefix PREFIX]
      [--launcher-name NAME.exe] [--mod-folder NAME] [--7z PATH] [--retry VERSION]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

MANIFEST_SCHEMA = 2
READY_SCHEMA = 1
CHANNEL_SCHEMA = 1
CHANNELS = ("stable", "test")
OBJECTS_BASE = "objects/"
# The defaults of --launcher-name, --archive-prefix, --site and --incoming are the host's first product's (an installed unit
# that passes none of them must go on doing what it did); they live on the host, in DEFAULTS_FILE, not in this repository.
DEFAULTS_FILE = Path(os.environ.get("DL_INGEST_DEFAULTS") or Path(__file__).with_name("dl_ingest.defaults.json"))
LAUNCHER_NAME = ARCHIVE_PREFIX = None
SITE_NAME, INCOMING_NAME = "mxl", "incoming"
# Publishers before the downloader (launcher 0.1.x) uploaded the launcher under an older name: still accepted, under its
# own name, for the launcher names the defaults file maps to one.
LEGACY_LAUNCHER_NAMES: dict = {}
LAUNCHER_NAMES: tuple = ()


def apply_defaults(d: dict) -> None:
    """Sets the module defaults from a defaults file's object (keys missing: the built-in ones / none)."""
    global LAUNCHER_NAME, ARCHIVE_PREFIX, SITE_NAME, INCOMING_NAME, LEGACY_LAUNCHER_NAMES, LAUNCHER_NAMES
    LAUNCHER_NAME, ARCHIVE_PREFIX = d.get("launcher_name"), d.get("archive_prefix")
    SITE_NAME, INCOMING_NAME = d.get("site") or "mxl", d.get("incoming") or "incoming"
    LEGACY_LAUNCHER_NAMES = dict(d.get("legacy_launcher_names") or {})
    LAUNCHER_NAMES = tuple(n for n in (LAUNCHER_NAME, LEGACY_LAUNCHER_NAMES.get(LAUNCHER_NAME)) if n)


def load_defaults(path: Path = None) -> dict:
    path = DEFAULTS_FILE if path is None else Path(path)
    if not path.is_file():
        return {}
    d = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise SystemExit(f"{path}: a JSON object expected")
    return d


apply_defaults(load_defaults())
MANIFEST_NAME = "release-manifest.json"
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PACK_RE = re.compile(r"^objects-[0-9a-f]{16}\.7z$")
NOTES_RE = re.compile(r"^RELEASE_NOTES-[0-9A-Za-z.+-]+\.md$")
PART_RE = re.compile(r"\.part-[0-9a-z]+$")
SYNC_DIR = ".sync"  # in the site, not served: `wanted` starts tools/dl_sync.py (the Space mirror)
WORK = ".work"  # the ingest's scratch folder inside incoming/<v>/
PART_AGE = 3600  # a temp file younger than this may belong to an upload that is still running
# the player 7z: the same switches as tools/package_release.py
SEVENZ_ARGS = ["a", "-t7z", "-m0=lzma2", "-mx=7", "-ms=on", "-mmt=on", "-mtm=off", "-mtc=off", "-mta=off", "-bd", "-y"]
SEVENZ_NAMES = ("7zz", "7z", "7za")
JOURNAL = bool(os.environ.get("JOURNAL_STREAM"))  # systemd: "<3>" in front of a line makes it an error in the journal


class Refused(Exception):
    pass


def log(msg, error=False):
    print(("<3>" if error and JOURNAL else "") + msg, file=sys.stderr if error and not JOURNAL else sys.stdout, flush=True)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def dumps(obj) -> bytes:
    return (json.dumps(obj, indent=1) + "\n").encode("utf-8")


def version_key(v: str):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-+](.*))?$", v)
    nums = tuple(int(x) for x in m.groups()[:3])
    return nums + (0, m.group(4)) if m.group(4) else nums + (1, "")


def now_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_7z(given=None):
    if given:
        return given
    for name in SEVENZ_NAMES:
        found = shutil.which(name)
        if found:
            return found
    for var in ("ProgramFiles", "ProgramFiles(x86)"):  # a test run on Windows
        base = os.environ.get(var)
        if base and (Path(base) / "7-Zip" / "7z.exe").is_file():
            return str(Path(base) / "7-Zip" / "7z.exe")
    return None


def safe_rel(path: str) -> bool:
    """A '/'-separated relative path that cannot leave its folder (the launcher's SafeRelativePath, roughly)."""
    if not isinstance(path, str) or not path or len(path) > 400 or path.startswith("/") or path.endswith("/"):
        return False
    for seg in path.split("/"):
        if seg in ("", ".", "..") or seg[-1] in ". " or any(ord(c) < 0x20 or c in '\\:<>"|?*' for c in seg):
            return False
    return True


def write_atomic(dest: Path, data: bytes = None, src: Path = None, move=False):
    """Write `data` (or copy / move `src`) to dest through <dest>.part-<pid> and a rename: readers never see half a file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(f"{dest.name}.part-{os.getpid():x}")
    if data is not None:
        tmp.write_bytes(data)
    elif move:
        os.replace(src, tmp)
    else:
        shutil.copyfile(src, tmp)
    os.chmod(tmp, 0o644)
    os.replace(tmp, dest)


def strip(man: dict) -> dict:
    """What makes two manifests of one version the same release: everything but the packaging date and the server's 7z."""
    return {k: v for k, v in man.items() if k not in ("released", "archive")}


# ------------------------------------------------------------------------------------------------------------- checks
def check_ready(inc: Path, version: str, launcher_names=None) -> dict:
    launcher_names = LAUNCHER_NAMES if launcher_names is None else launcher_names
    try:
        ready = json.loads((inc / "READY").read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise Refused(f"READY is not readable JSON: {e}")
    if ready.get("schemaVersion") != READY_SCHEMA:
        raise Refused(f"READY schemaVersion {ready.get('schemaVersion')} (this ingest knows {READY_SCHEMA}): update dl_ingest.py")
    if ready.get("version") != version:
        raise Refused(f"READY is for version {ready.get('version')!r}, the folder is {version}")
    if ready.get("channel") not in (None, *CHANNELS):
        raise Refused(f"unknown channel {ready.get('channel')!r}")
    files = ready.get("files")
    if not isinstance(files, dict) or MANIFEST_NAME not in files:
        raise Refused(f"READY lists no {MANIFEST_NAME}")
    pack, launcher = ready.get("objectsPack"), ready.get("launcher")
    for name, meta in files.items():
        ok = name == MANIFEST_NAME or NOTES_RE.match(name) or PACK_RE.match(name) or name in launcher_names
        if not ok or not isinstance(meta, dict) or not SHA_RE.match(str(meta.get("sha256"))) or not isinstance(meta.get("size"), int):
            raise Refused(f"READY lists a file it may not: {name!r}")
    if pack is not None and (pack not in files or not PACK_RE.match(pack)):
        raise Refused(f"READY names objectsPack {pack!r}, which it does not list")
    uploaded = [n for n in launcher_names if n in files]
    if (launcher is not None and launcher not in launcher_names) or uploaded != ([launcher] if launcher else []):
        raise Refused("READY's launcher entry and its file list disagree")
    if any(PACK_RE.match(n) for n in files if n != pack):
        raise Refused("READY lists an objects 7z that is not its objectsPack")
    present = {p.name for p in inc.iterdir()} - {"READY", WORK}
    extra = sorted(present - set(files))
    if extra:
        raise Refused(f"files that READY does not list: {', '.join(extra[:5])}")
    for name, meta in sorted(files.items()):
        p = inc / name
        if name not in present or p.is_symlink() or not p.is_file():
            raise Refused(f"{name} is missing (or not a plain file)")
        if p.stat().st_size != meta["size"] or sha256_file(p) != meta["sha256"]:
            raise Refused(f"{name} does not match READY (size or sha256): the upload is damaged; publish it again")
    return ready


def check_manifest(raw: bytes, version: str, ready: dict, mod_folder=None) -> dict:
    try:
        man = json.loads(raw)
    except ValueError as e:
        raise Refused(f"{MANIFEST_NAME} is not JSON: {e}")
    if man.get("schemaVersion") != MANIFEST_SCHEMA:
        raise Refused(f"manifest schemaVersion {man.get('schemaVersion')} (this ingest knows {MANIFEST_SCHEMA})")
    if man.get("version") != version:
        raise Refused(f"the manifest is version {man.get('version')!r}, the folder is {version}")
    if man.get("objectsBase") != OBJECTS_BASE:
        raise Refused(f"objectsBase must be {OBJECTS_BASE!r}")
    mod = man.get("modFolder")
    if not safe_rel(mod) or "/" in mod:
        raise Refused(f"bad modFolder {mod!r}")
    if mod_folder is not None and mod != mod_folder:  # an upload meant for another product's site
        raise Refused(f"the manifest is for modFolder {mod!r}, this site is for {mod_folder!r}")
    if ready.get("channel") == "stable" and not man.get("complete", False):
        raise Refused("the manifest says complete=false: not for the stable channel")
    files = man.get("files")
    if not isinstance(files, list) or not files:
        raise Refused("the manifest lists no files")
    seen, sizes, total = set(), {}, 0
    for f in files:
        path, sha, size = f.get("path"), f.get("sha256"), f.get("size")
        if not safe_rel(path) or not SHA_RE.match(str(sha)) or not isinstance(size, int) or size < 0:
            raise Refused(f"bad manifest entry {f!r:.200}")
        if path.lower() in seen:
            raise Refused(f"duplicate path {path}")
        seen.add(path.lower())
        if sizes.setdefault(sha, size) != size:
            raise Refused(f"{path}: the same sha256 with two sizes")
        total += size
    if man.get("fileCount", len(files)) != len(files) or man.get("totalSize", total) != total:
        raise Refused("fileCount / totalSize do not match the file list")
    for d in man.get("emptyDirs", []):
        if not safe_rel(d):
            raise Refused(f"bad emptyDirs entry {d!r}")
    lr = man.get("launcher")
    if ready.get("launcher"):
        if not isinstance(lr, dict) or not VERSION_RE.match(str(lr.get("version"))) or \
                lr.get("path") != f"launcher/{lr.get('version')}/{ready['launcher']}":
            raise Refused("the manifest's launcher entry is missing or malformed")
        meta = ready["files"][ready["launcher"]]
        if lr.get("sha256") != meta["sha256"] or lr.get("size") != meta["size"]:
            raise Refused("the uploaded launcher does not match the manifest's launcher entry")
    elif lr is not None:
        raise Refused("the manifest names a launcher, but none was uploaded")
    return man


def list_pack(sevenzip, pack: Path, wanted: dict) -> dict:
    """`7z l -slt`: every entry must be a plain file named by a sha256 the manifest uses, with that object's size.
    -> {sha: size}. Checked before anything is unpacked (no folders, links or paths in it)."""
    r = subprocess.run([sevenzip, "l", "-slt", "-bd", str(pack)], capture_output=True, text=True,
                       errors="replace")
    if r.returncode != 0:
        raise Refused(f"7-Zip cannot list {pack.name} ({r.returncode}): {(r.stdout + r.stderr).strip()[-300:]}")
    body = r.stdout.split("\n----------\n", 1)
    if len(body) != 2:
        raise Refused(f"unexpected 7-Zip listing of {pack.name}")
    entries, cur = {}, {}
    for ln in body[1].splitlines() + [""]:
        if not ln.strip():
            if cur:
                path = cur.get("Path", "")
                if not SHA_RE.match(path) or cur.get("Folder", "-") != "-" or re.search(r"\bl[-r][-w][-xsS]", cur.get("Attributes", "")):
                    raise Refused(f"{pack.name} holds {path!r}, which is not an object (a plain file named by its sha256)")
                if path not in wanted:
                    raise Refused(f"{pack.name} holds {path}, which the manifest does not use")
                if int(cur.get("Size", "-1") or -1) != wanted[path] or path in entries:
                    raise Refused(f"{pack.name}: entry {path} has the wrong size (or is there twice)")
                entries[path] = wanted[path]
                cur = {}
            continue
        k, sep, v = ln.partition(" = ")
        if sep:
            cur[k.strip()] = v
    return entries


# ------------------------------------------------------------------------------------------------------------- ingest
class Ingest:
    def __init__(self, root: Path, site_name=None, sevenzip=None, incoming_name=None,
                 archive_prefix=None, launcher_name=None, mod_folder=None):
        site_name, incoming_name = site_name or SITE_NAME, incoming_name or INCOMING_NAME
        archive_prefix, launcher_name = archive_prefix or ARCHIVE_PREFIX, launcher_name or LAUNCHER_NAME
        if not archive_prefix or not launcher_name:
            raise SystemExit(f"--archive-prefix and --launcher-name are needed: no defaults in {DEFAULTS_FILE}")
        self.root = Path(root).resolve()
        self.site = self.root / site_name
        self.incoming = self.root / incoming_name
        self.sevenzip = sevenzip
        self.archive_prefix = archive_prefix
        self.launcher_names = tuple(n for n in (launcher_name, LEGACY_LAUNCHER_NAMES.get(launcher_name)) if n)
        self.mod_folder = mod_folder
        if site_name == incoming_name:
            raise SystemExit("--site and --incoming must be different folders")
        for what, name in (("--site", site_name), ("--incoming", incoming_name), ("--archive-prefix", archive_prefix),
                           ("--launcher-name", launcher_name)):
            if not safe_rel(name) or "/" in name or name.startswith("."):
                raise SystemExit(f"bad {what} {name!r}: a plain name, no folders")
        for p in (self.site, self.incoming):
            if p.is_symlink() or not p.is_dir() or p.resolve().parent != self.root:
                raise SystemExit(f"{p} must be a real folder directly in {self.root}")

    def obj(self, sha) -> Path:
        return self.site / "objects" / sha[:2] / sha

    def pending(self):
        out = []
        for p in self.incoming.iterdir():
            # <v>.uploading is still being written (and "1.0.0-rc1.uploading" would pass VERSION_RE)
            if VERSION_RE.match(p.name) and not p.name.endswith(".uploading") and p.is_dir() and not p.is_symlink() \
                    and (p / "READY").is_file() and not (p / "REFUSED").exists():
                out.append(p.name)
        return sorted(out, key=version_key)

    def run(self) -> int:
        failed, done, published = 0, set(), []
        while True:  # again after each pass: an upload may have finished while the last one ran
            todo = [v for v in self.pending() if v not in done]
            if not todo:
                break
            for v in todo:
                done.add(v)
                try:
                    self.ingest(v)
                    published.append(v)
                except Refused as e:
                    failed += 1
                    log(f"{v}: REFUSED: {e}", error=True)
                    try:
                        (self.incoming / v / "REFUSED").write_text(f"{now_utc()} {e}\n", encoding="utf-8")
                    except OSError:
                        pass
                    shutil.rmtree(self.incoming / v / WORK, ignore_errors=True)
        self.clean_parts()
        if published:
            self.request_sync(f"ingest {', '.join(published)}")
        return 1 if failed else 0

    def request_sync(self, reason):
        """<site>/.sync/wanted: the trigger of mxl-dl-sync.path (the mirror to the Space, tools/dl_sync.py)."""
        try:
            write_atomic(self.site / SYNC_DIR / "wanted", data=f"{now_utc()} {reason}\n".encode())
        except OSError as e:
            log(f"cannot write {SYNC_DIR}/wanted ({e}); the Space sync timer picks the release up", error=True)

    def ingest(self, v: str):
        inc = self.incoming / v
        log(f"{v}: checking the upload in {inc}")
        if not self.sevenzip:
            raise Refused("no 7-Zip on the server (apt install 7zip)")
        ready = check_ready(inc, v, self.launcher_names)
        man_raw = (inc / MANIFEST_NAME).read_bytes()
        man = check_manifest(man_raw, v, ready, self.mod_folder)
        sizes = {f["sha256"]: f["size"] for f in man["files"]}
        rel_dir = self.site / "releases" / v
        published = rel_dir / MANIFEST_NAME
        old = None
        if published.is_file():
            old = json.loads(published.read_bytes())
            if strip(old) != strip(man) and not ready.get("force"):
                raise Refused(f"releases/{v} is already published with other contents; a published version never changes "
                              "(publish a new version, or publish --force)")
        work = inc / WORK  # inside the upload: the path unit watches incoming/ only, so this is no new trigger
        if work.is_symlink() or work.is_file():  # an upload cannot plant a link here to make the ingest write elsewhere
            work.unlink()
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir()

        pack = ready.get("objectsPack")
        if pack:
            entries = list_pack(self.sevenzip, inc / pack, sizes)
            unpacked = work / "objects"
            r = subprocess.run([self.sevenzip, "x", "-y", "-bd", f"-o{unpacked}", str(inc / pack)], capture_output=True,
                               text=True, errors="replace")
            if r.returncode != 0:
                raise Refused(f"7-Zip cannot unpack {pack} ({r.returncode}): {(r.stdout + r.stderr).strip()[-300:]}")
            found = {}
            for dirpath, dirnames, filenames in os.walk(unpacked):
                if dirnames or Path(dirpath) != unpacked:
                    raise Refused(f"{pack} unpacked into folders")
                for n in filenames:
                    p = unpacked / n
                    if p.is_symlink() or not p.is_file() or n not in entries:
                        raise Refused(f"{pack} unpacked {n!r}, which its listing did not show")
                    got = sha256_file(p)
                    if got != n or p.stat().st_size != sizes[n]:
                        raise Refused(f"{pack}: {n} has sha256 {got}: the object is damaged; publish it again")
                    found[n] = p
            if set(found) != set(entries):
                raise Refused(f"{pack}: {len(set(entries) - set(found))} listed objects were not unpacked")
            moved = 0
            for sha, p in sorted(found.items()):
                dest = self.obj(sha)
                if dest.is_file() and dest.stat().st_size == sizes[sha]:
                    continue
                write_atomic(dest, src=p, move=True)
                moved += 1
            log(f"{v}: {len(found)} objects in {pack}, {moved} new on the host")

        missing = [s for s in sizes if not self.obj(s).is_file() or self.obj(s).stat().st_size != sizes[s]]
        if missing:
            raise Refused(f"the release needs {len(missing)} objects the host does not have, e.g. {missing[0]}; "
                          "publish it again (it uploads what is missing)")

        arch_name = f"{self.archive_prefix}-{v}{'' if man.get('complete', False) else '-nodata'}.7z"
        arch_path = rel_dir / arch_name
        reuse = old is not None and strip(old) == strip(man) and old.get("archive", {}).get("name") == arch_name and \
            arch_path.is_file() and arch_path.stat().st_size == old["archive"]["size"] and \
            sha256_file(arch_path) == old["archive"]["sha256"]
        if reuse:
            log(f"{v}: already published with the same content; {arch_name} kept")
            man_bytes = published.read_bytes()
        else:
            built = self.build_archive(man, work, arch_name)
            pub = dict(man)
            pub["archive"] = {"format": "7z", "name": arch_name, "size": built.stat().st_size, "sha256": sha256_file(built),
                              "path": f"releases/{v}/{arch_name}"}
            man_bytes = dumps(pub)
            write_atomic(arch_path, src=built, move=True)
            log(f"{v}: {arch_name} built ({pub['archive']['size'] / 1e6:.0f} MB from {man['totalSize'] / 1e6:.0f} MB)")
        notes = [n for n in ready["files"] if NOTES_RE.match(n)]
        sums = [(arch_name, json.loads(man_bytes)["archive"]["sha256"])]
        for n in notes:
            write_atomic(rel_dir / n, src=inc / n)
        write_atomic(published, data=man_bytes)  # the release is complete from here on (gc: a folder without it is not)
        sums.append((MANIFEST_NAME, sha256_bytes(man_bytes)))
        sums += [(n, ready["files"][n]["sha256"]) for n in notes]
        write_atomic(rel_dir / "SHA256SUMS", data="".join(f"{s}  {n}\n" for n, s in sums).encode())
        if ready.get("launcher"):
            lr = man["launcher"]
            ldir = self.site / "launcher" / lr["version"]
            name = ready["launcher"]
            exe = ldir / name
            if not (exe.is_file() and sha256_file(exe) == lr["sha256"]):
                write_atomic(exe, src=inc / name)
            write_atomic(ldir / f"{name}.sha256", data=f"{lr['sha256']}  {name}\n".encode())
            log(f"{v}: downloader {lr['version']} in launcher/{lr['version']}/{name}")
        if ready.get("channel"):  # LAST
            ch = {"schemaVersion": CHANNEL_SCHEMA, "version": v, "manifest": f"releases/{v}/{MANIFEST_NAME}",
                  "manifestSha256": sha256_bytes(man_bytes), "publishedAt": now_utc()}
            write_atomic(self.site / "channels" / f"{ready['channel']}.json", data=dumps(ch))
            log(f"{v}: channel {ready['channel']} -> {v}")
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(inc)
        log(f"{v}: published ({man['fileCount']} files); {self.incoming.name}/{v} removed")

    def build_archive(self, man: dict, work: Path, name: str) -> Path:
        """The player's <modFolder>/ folder linked (or copied) together from the objects, each read again for its sha256, then
        7-Zipped with the packager's switches."""
        tree = work / "tree"
        top = tree / man["modFolder"]
        for f in man["files"]:
            src, dst = self.obj(f["sha256"]), top.joinpath(*f["path"].split("/"))
            if sha256_file(src) != f["sha256"]:
                raise Refused(f"object {f['sha256']} on the host is damaged (sha256); delete it and publish again")
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(src, dst)
            except OSError:
                shutil.copyfile(src, dst)
        for d in man.get("emptyDirs", []):
            top.joinpath(*d.split("/")).mkdir(parents=True, exist_ok=True)
        out = work / name
        r = subprocess.run([self.sevenzip, *SEVENZ_ARGS, str(out), man["modFolder"]], cwd=tree, capture_output=True, text=True,
                           errors="replace")
        if r.returncode != 0 or not out.is_file():
            raise Refused(f"7-Zip failed building {name} ({r.returncode}): {(r.stdout + r.stderr).strip()[-300:]}")
        return out

    def clean_parts(self):
        """Temp files (*.part-<hex>) of uploads or writes that died, older than an hour, anywhere in the site."""
        cutoff, n = time.time() - PART_AGE, 0
        for dirpath, _, filenames in os.walk(self.site):
            for name in filenames:
                p = Path(dirpath) / name
                if PART_RE.search(name) and not p.is_symlink() and p.stat().st_mtime < cutoff:
                    p.unlink()
                    n += 1
        if n:
            log(f"removed {n} leftover temp files (*.part-*) from {self.site}")


def lock(incoming: Path):
    """One run at a time (the path unit and the timer may start it together): flock on the incoming folder itself. A lock
    file in it would be a write there, which the path unit sees and answers with another run, forever. -> an fd to close,
    or None where fcntl does not exist (Windows tests)."""
    try:
        import fcntl
    except ImportError:
        return None
    fd = os.open(incoming, os.O_RDONLY)
    fcntl.flock(fd, fcntl.LOCK_EX)
    return fd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path("/srv/dl"), help="holds incoming/ and the site folder (default /srv/dl)")
    ap.add_argument("--site", default=SITE_NAME, help=f"the site folder's name under --root (default {SITE_NAME})")
    ap.add_argument("--incoming", default=INCOMING_NAME, help=f"the uploads folder's name under --root (default {INCOMING_NAME})")
    ap.add_argument("--archive-prefix", default=ARCHIVE_PREFIX,
                    help=f"releases/<v>/<prefix>-<v>.7z, the player 7z the server builds (default {ARCHIVE_PREFIX or 'none: needed'})")
    ap.add_argument("--launcher-name", default=LAUNCHER_NAME,
                    help=f"the downloader exe's file name (default {LAUNCHER_NAME or 'none: needed'})")
    ap.add_argument("--mod-folder", help="refuse a manifest whose modFolder is another (default: any); a product's unit sets it")
    ap.add_argument("--7z", dest="sevenzip", help="7-Zip binary (default: 7zz, 7z or 7za on PATH)")
    ap.add_argument("--retry", metavar="VERSION", help="remove incoming/VERSION/REFUSED and try that upload again")
    a = ap.parse_args(argv)
    ing = Ingest(a.root, a.site, find_7z(a.sevenzip), a.incoming, a.archive_prefix, a.launcher_name, a.mod_folder)
    held = lock(ing.incoming)
    try:
        if a.retry:
            if not VERSION_RE.match(a.retry):
                raise SystemExit(f"bad version {a.retry!r}")
            (ing.incoming / a.retry / "REFUSED").unlink(missing_ok=True)
        return ing.run()
    finally:
        if held is not None:
            os.close(held)


if __name__ == "__main__":
    sys.exit(main())
