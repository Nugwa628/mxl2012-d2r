"""Prepares a worktree so that `tools/build.py` and `tools/build_plugin.ps1` run in it with nothing copied by hand.

  py -3 tools/lane_setup.py [WORKTREE] [--check] [--local-native] [--seed-cache DIR] [--cache-from-slot N]

What a fresh `git worktree add` lacks, and where lane_setup gets it (docs/setup.md, "New worktree"):

  StormLib / CascLib DLLs   Built ONCE for every worktree into <runs>/shared/native/build (tools/build_native.ps1, CMake of
                            Visual Studio), from sources at the commit the repo pins. tools/native.py finds them there when the
                            worktree has no build/ of its own. The submodule sources are used when the worktree has them; an
                            empty submodule (always, in a new worktree) is replaced by a clone of the pinned commit made from a
                            local checkout (the worktree's own, MXL_NATIVE_REF, or the machine's reference checkout, read-only) into
                            <runs>/shared/native/src. Nothing is downloaded. --local-native builds into the worktree's build/.
  PluginSDK                 Same: <runs>/shared/native/src/PluginSDK at the pinned commit; build_plugin.ps1 reads its folder
                            from MXL2012_PLUGINSDK_DIR in .mxl-local.json.
  D2R extraction            MXL_D2R_EXTRACT: this checkout's extract/d2r/93847, else the machine's (read-only). Must have both
                            banks of skills.txt; txt_migrate, validate and build.py refuse to run without one.
  D2R file cache            The few D2R files the extraction lacks (HD state machines ...): ONE cache, <runs>/shared/d2r-cache,
                            used by all worktrees (MXL_D2R_CACHE), never copied. Filled from --seed-cache DIR (a work/d2r-cache
                            of another checkout, same layout) or --cache-from-slot N (reads the CASC of game slot N under its
                            lock; slots 2 to 5 only, never 1; a missing slot is refused). Once it is complete a new worktree needs neither.
  .mxl-local.json           Git-ignored, in the worktree: MXL_D2R_EXTRACT, MXL_D2R_CACHE, MXL_NATIVE_DIR, MXL2012_PLUGINSDK_DIR,
                            MXL_MACHINE
                            (tools/localconfig.py). Environment variables still win.
  machine.json              The machine-local config outside every checkout (tools/localconfig.py: reference checkout,
                            extraction, shared slot lock folder, protected folders); reported, never written here. The
                            game-slot tools refuse to run while its safety keys are missing.

Run again at any time: finished parts are only checked. --check changes nothing and exits 1 when something is missing.
Shared work (clone, build, cache fill) happens under <runs>/shared/.lock so two new lanes do not build at the same time.
Exit codes: 0 ready, 1 something is missing or failed.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import localconfig  # noqa: E402

TOOLS = Path(__file__).resolve().parent
NATIVE_LIBS = ("StormLib", "CascLib")
SDK = "PluginSDK"
LOCK_STALE_SECONDS = 3600


# ---------------------------------------------------------------------------------------------------------- git helpers
def git(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed ({r.returncode}): {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def pinned_commits(root: Path) -> dict[str, str]:
    """submodule name -> the commit the repo pins (the gitlinks of HEAD under third_party/)."""
    out = {}
    for line in git("ls-tree", "HEAD", "third_party/", cwd=root).splitlines():
        meta, _, path = line.partition("\t")
        mode, kind, sha = meta.split()
        if mode == "160000":
            out[Path(path).name] = sha
    return out


def head_of(src: Path) -> str | None:
    """HEAD of a source checkout, or None when it is not one (an empty submodule folder)."""
    if not (src / "CMakeLists.txt").exists():
        return None
    sha = git("rev-parse", "HEAD", cwd=src, check=False)
    return sha or None


def has_commit(repo: Path, sha: str) -> bool:
    return subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"], cwd=repo, capture_output=True).returncode == 0


def reference_repos(root: Path, lib: str) -> list[Path]:
    """Local checkouts the pinned commit of `lib` can be cloned from (read-only use), best first."""
    refs = []
    if os.environ.get("MXL_NATIVE_REF"):
        refs += [Path(p) / lib for p in os.environ["MXL_NATIVE_REF"].split(os.pathsep) if p]
    refs.append(root / "third_party" / lib)
    if localconfig.reference_dir() is not None:
        refs.append(localconfig.reference_dir() / "third_party" / lib)
    return [r for r in refs if (r / ".git").exists()]


# ------------------------------------------------------------------------------------------------------------- the lock
class SharedLock:
    """<runs>/shared/.lock: a directory made with mkdir (atomic), holding owner.txt. Waits, takes over a stale one."""

    def __init__(self, shared: Path, timeout: float = 1800, alive=None, poll: float = 2.0):
        self.path = shared / ".lock"
        self.shared, self.timeout, self.poll = shared, timeout, poll
        self.alive = alive or _pid_alive

    def __enter__(self):
        self.shared.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.path.mkdir()
                (self.path / "owner.txt").write_text(f"pid={os.getpid()} {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                return self
            except FileExistsError:
                if self.stale():
                    shutil.rmtree(self.path, ignore_errors=True)
                    continue
                if time.monotonic() > deadline:
                    raise SystemExit(f"{self.path} is held by {self.owner()} for more than {self.timeout:.0f} s; "
                                     "wait for that lane or delete the folder if it is dead")
                time.sleep(self.poll)

    def __exit__(self, *exc):
        shutil.rmtree(self.path, ignore_errors=True)

    def owner(self) -> str:
        try:
            return (self.path / "owner.txt").read_text().strip()
        except OSError:
            return "someone (no owner.txt)"

    def stale(self) -> bool:
        """Old enough and its owner's process gone (a lock without owner.txt is respected until it is old)."""
        try:
            age = time.time() - self.path.stat().st_mtime
        except OSError:
            return True  # vanished while we looked
        if age < LOCK_STALE_SECONDS:
            return False
        owner = self.owner()
        pid = owner.split("pid=")[1].split()[0] if "pid=" in owner else ""
        return not (pid.isdigit() and self.alive(int(pid)))


def _pid_alive(pid: int) -> bool:
    import game_slots  # Windows-only inside (kernel32); never os.kill, which terminates on Windows
    try:
        return bool(game_slots.pid_alive(pid))
    except OSError:
        return True  # cannot tell: keep the lock


# --------------------------------------------------------------------------------------------------------------- steps
class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str]] = []

    def add(self, status: str, what: str, detail: str = "") -> None:
        self.rows.append((status, what, detail))
        print(f"[{status:4}] {what}" + (f": {detail}" if detail else ""), flush=True)

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.rows)


def ensure_source(root: Path, lib: str, sha: str, shared_src: Path, report: Report, check_only: bool) -> Path | None:
    """The folder with `lib`'s sources at the pinned commit: the worktree's submodule, else the shared clone (made here)."""
    own = root / "third_party" / lib
    if head_of(own) == sha:
        report.add("ok", f"{lib} source", f"submodule third_party/{lib} at {sha[:9]}")
        return own
    dest = shared_src / lib
    if head_of(dest) == sha:
        report.add("ok", f"{lib} source", f"shared clone at {sha[:9]}")
        return dest
    if check_only:
        report.add("FAIL", f"{lib} source", f"no checkout at {sha[:9]} (run tools/lane_setup.py)")
        return None
    if dest.exists():
        report.add("FAIL", f"{lib} source", f"{dest} exists but is not at {sha[:9]}; fix or delete that folder")
        return None
    for ref in reference_repos(root, lib):
        if not has_commit(ref, sha):
            continue
        shared_src.mkdir(parents=True, exist_ok=True)
        tmp = shared_src / f"{lib}.partial-{os.getpid()}"
        shutil.rmtree(tmp, ignore_errors=True)
        try:
            git("clone", "--quiet", "--no-checkout", "--no-hardlinks", str(ref), str(tmp))
            git("checkout", "--quiet", "--detach", sha, cwd=tmp)
            os.replace(tmp, dest)
        except (RuntimeError, OSError) as e:
            shutil.rmtree(tmp, ignore_errors=True)
            report.add("FAIL", f"{lib} source", f"clone from a local checkout failed: {e}")
            return None
        report.add("ok", f"{lib} source", f"cloned {sha[:9]} from a local checkout into {dest}")
        return dest
    report.add("FAIL", f"{lib} source",
               f"commit {sha[:9]} is in no local checkout (looked at the worktree's submodule, MXL_NATIVE_REF, the reference checkout); "
               f"`git submodule update --init third_party/{lib}` needs the network, or point MXL_NATIVE_REF at a folder that has {lib}/")
    return None


def powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def native_dlls(base: Path) -> dict[str, Path]:
    return {lib: base / lib / "Release" / f"{lib}.dll" for lib in NATIVE_LIBS}


def built_at(base: Path, lib: str) -> str | None:
    stamp = base / lib / ".source-sha"
    dll = base / lib / "Release" / f"{lib}.dll"
    return stamp.read_text().strip() if dll.exists() and stamp.exists() else None


def ensure_native(root: Path, pins: dict[str, str], shared: Path, local: bool, report: Report, check_only: bool) -> Path | None:
    """Makes sure StormLib.dll and CascLib.dll exist; returns the build folder native.py will find them in (None = failed)."""
    base = root / "build" if local else shared / "native" / "build"
    need = []
    for lib in NATIVE_LIBS:
        sha = pins.get(lib)
        if not sha:
            report.add("FAIL", f"{lib} DLL", f"{lib} is not a pinned submodule of this repo")
            return None
        have = built_at(base, lib)
        # a worktree that built its own build/ before this tool existed has no stamp: its DLL is used as it is
        own = native_dlls(root / "build")[lib]
        if not local and own.exists():
            report.add("ok", f"{lib} DLL", f"{own} (this worktree's own build)")
        elif have == sha:
            report.add("ok", f"{lib} DLL", f"{native_dlls(base)[lib]} (source {sha[:9]})")
        else:
            need.append(lib)
    if not need:
        return base
    if check_only:
        for lib in need:
            report.add("FAIL", f"{lib} DLL", f"not built at {base} (run tools/lane_setup.py)")
        return None
    ps = powershell()
    if not ps:
        report.add("FAIL", "native build", "no PowerShell on PATH")
        return None
    src_base = shared / "native" / "src"
    if all(head_of(root / "third_party" / lib) == pins[lib] for lib in NATIVE_LIBS):
        src_dir = root / "third_party"  # this worktree has its submodules at the pinned commits: build from them
        report.add("ok", "native sources", "the worktree's submodules")
    else:
        if any(ensure_source(root, lib, pins[lib], src_base, report, False) is None for lib in NATIVE_LIBS):
            return None
        src_dir = src_base
    cmd = [ps, "-NoProfile", "-File", str(TOOLS / "build_native.ps1"), "-Source", str(src_dir), "-Out", str(base)]
    print("   " + " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=root)
    if r.returncode:
        report.add("FAIL", "native build", f"build_native.ps1 exited {r.returncode}")
        return None
    for lib in need:
        if built_at(base, lib) != pins[lib]:
            report.add("FAIL", f"{lib} DLL", f"build finished but {native_dlls(base)[lib]} / .source-sha is not at {pins[lib][:9]}")
            return None
        report.add("ok", f"{lib} DLL", f"built {native_dlls(base)[lib]}")
    return base


def ensure_sdk(root: Path, pins: dict[str, str], shared: Path, report: Report, check_only: bool) -> Path | None:
    sha = pins.get(SDK)
    if not sha:
        report.add("FAIL", "PluginSDK", "not a pinned submodule of this repo")
        return None
    src = ensure_source(root, SDK, sha, shared / "native" / "src", report, check_only)
    if src is not None and not (src / "include").exists():
        report.add("FAIL", "PluginSDK", f"{src} has no include/ folder")
        return None
    return src


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cache_missing(extract: Path, cache: Path) -> list[str]:
    """D2R files the build reads (fxpaths.CACHED_FILES) that are in neither the extraction nor the cache."""
    import fxpaths
    return [rel for rel in fxpaths.CACHED_FILES if not (extract / rel).exists() and not (cache / rel).exists()]


def write_atomic(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dest)


def casc_reader(slot: int):
    """A function rel -> bytes reading D2R's CASC in game slot `slot` (2 to 5: --cache-from-slot does not offer the owner's slot 1)."""
    import game_slots
    import native
    game = game_slots.slot_dir(game_slots.require_slot(slot))
    if game_slots.slot_of_game_dir(game) is None:
        raise SystemExit(f"{game} is not the folder of game slot {slot}")
    storage = native.open_casc(game)

    def read(rel: str) -> bytes:
        return native.casc_read(storage, "data:" + rel)
    return read


def fill_cache(extract: Path, cache: Path, missing: list[str], seeds: list[Path], slot: int | None, report: Report,
               reader=None) -> None:
    """Fills `missing` from the seed folders (same layout as the cache), then from a slot's CASC. Never overwrites."""
    for rel in list(missing):
        for seed in seeds:
            if (seed / rel).exists():
                write_atomic(cache / rel, (seed / rel).read_bytes())
                report.add("ok", f"cache {rel}", f"copied from {seed}")
                missing.remove(rel)
                break
    if missing and slot is not None:
        import game_slots
        ok, msg = game_slots.acquire(slot, "lane_setup")
        if not ok:
            report.add("FAIL", f"cache from slot {slot}", f"{msg}; try the other slot or wait")
            return
        try:
            read = reader or casc_reader(slot)
            for rel in list(missing):
                write_atomic(cache / rel, read(rel))
                report.add("ok", f"cache {rel}", f"read from the CASC of slot {slot}")
                missing.remove(rel)
        finally:
            game_slots.release(slot, "lane_setup")


def update_manifest(cache: Path) -> dict[str, str]:
    """cache/MANIFEST.json: sha256 of every cached file, first seen = trusted; a later change is reported by check()."""
    mf = cache / "MANIFEST.json"
    known = json.loads(mf.read_text("utf-8")) if mf.exists() else {}
    for p in sorted(cache.rglob("*")):
        rel = p.relative_to(cache).as_posix()
        if p.is_file() and not rel.endswith((".tmp", "MANIFEST.json")) and rel not in known:
            known[rel] = sha256(p)
    if known and cache.exists():
        write_atomic(mf, (json.dumps(known, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    return known


def cache_damaged(cache: Path) -> list[str]:
    mf = cache / "MANIFEST.json"
    if not mf.exists():
        return []
    return [rel for rel, h in json.loads(mf.read_text("utf-8")).items() if not (cache / rel).exists() or sha256(cache / rel) != h]


def check_tools(report: Report) -> None:
    for mod in ("PIL", "numpy", "capstone"):
        try:
            __import__(mod)
            report.add("ok", f"python {mod}")
        except ImportError:
            report.add("FAIL", f"python {mod}", "py -3 -m pip install --user -r tools/requirements.txt")
    ps = powershell()
    report.add("ok" if ps else "FAIL", "powershell", ps or "not on PATH")
    cmake = shutil.which("cmake")
    if not cmake:
        import glob
        found = sorted(glob.glob(r"C:\Program Files\Microsoft Visual Studio\*\*\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"))
        cmake = found[-1] if found else None
    report.add("ok" if cmake else "FAIL", "cmake", cmake or "not on PATH and no Visual Studio CMake found")


def setup(root: Path, args, report: Report) -> dict[str, str]:
    shared = localconfig.shared_dir()
    settings: dict[str, str] = {}
    check_only = args.check
    try:
        pins = pinned_commits(root)
    except RuntimeError as e:
        report.add("FAIL", "pinned submodules", str(e))
        return settings
    report.add("ok", "shared folder", str(shared))

    with (SharedLock(shared) if not check_only else _NoLock()):
        # 1. native DLLs
        base = ensure_native(root, pins, shared, args.local_native, report, check_only)
        if base is not None and base != root / "build":
            settings["MXL_NATIVE_DIR"] = str(base)  # tools/native.py: this worktree's build/ first, then this
        # 2. PluginSDK
        sdk = ensure_sdk(root, pins, shared, report, check_only)
        if sdk is not None:
            settings["MXL2012_PLUGINSDK_DIR"] = str(sdk)
        # 3. D2R extraction
        extract = localconfig.find_d2r_extract()
        if extract is None:
            report.add("FAIL", "D2R extraction", "none usable; looked in " + "; ".join(str(c) for c in localconfig.d2r_extract_candidates()))
        else:
            settings["MXL_D2R_EXTRACT"] = str(extract)
            note = "" if (extract / "filelist.txt").exists() else " (no filelist.txt: art_fix.py / gfx_placeholders.py need one)"
            report.add("ok" if not note else "FAIL", "D2R extraction", f"{extract}{note}")
            # 4. the shared D2R file cache
            cache = shared / "d2r-cache"
            settings["MXL_D2R_CACHE"] = str(cache)
            missing = cache_missing(extract, cache)
            if missing and not check_only:
                fill_cache(extract, cache, missing, [Path(s) for s in args.seed_cache], args.cache_from_slot, report)
            if missing:
                report.add("FAIL", "D2R cache", f"{len(missing)} file(s) missing in {cache}, e.g. {missing[0]}. Seed it once with "
                           "`py -3 tools/lane_setup.py --seed-cache <work/d2r-cache of any checkout>` or read it from a game slot "
                           "with `--cache-from-slot 2|3|4|5`")
            else:
                if not check_only:
                    update_manifest(cache)
                bad = cache_damaged(cache)
                report.add("FAIL" if bad else "ok", "D2R cache", f"{', '.join(bad)} differ from MANIFEST.json" if bad else str(cache))
        # 5. Median's extracted tables
        src = Path(os.environ.get("MXL2012_SRC") or localconfig.runs_dir() / "extract-mpq" / "data" / "global" / "excel")
        report.add("ok" if (src / "skills.txt").exists() else "FAIL", "Median XL 2012 tables", str(src))
        if os.environ.get("MXL2012_SRC"):
            settings["MXL2012_SRC"] = os.environ["MXL2012_SRC"]
    # 6. the machine-local config (read-only here)
    cfg = localconfig.machine()
    lacking = [k for k in localconfig.SLOT_SAFETY_KEYS if not cfg.get(k)]
    report.add("ok" if cfg else "note", "machine config", str(localconfig.machine_path()) if cfg else
               f"{localconfig.machine_path()} missing (only the reference data and the game-slot tools need it)")
    if cfg:
        settings["MXL_MACHINE"] = str(localconfig.machine_path())
    if cfg and lacking:
        report.add("note", "machine config", f"lacks {', '.join(lacking)}: the game-slot tools refuse to run")
    check_tools(report)
    return settings


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("worktree", nargs="?", default=str(localconfig.ROOT), help="the worktree to prepare (default: this one)")
    ap.add_argument("--check", action="store_true", help="only check; change nothing; exit 1 when something is missing")
    ap.add_argument("--local-native", action="store_true", help="build StormLib/CascLib into the worktree's build/ instead of the shared build")
    ap.add_argument("--seed-cache", action="append", default=[], metavar="DIR", help="fill the shared d2r-cache from DIR/data/... (repeatable)")
    ap.add_argument("--cache-from-slot", type=int, choices=(2, 3, 4, 5), metavar="N", help="read missing cache files from the CASC of game slot N (takes its lock)")
    args = ap.parse_args(argv)
    if args.cache_from_slot is not None and not args.check:
        import game_slots
        game_slots.require_present(args.cache_from_slot, "--cache-from-slot")
    root = Path(args.worktree).resolve()
    if not (root / "tools" / "build.py").exists():
        print(f"{root} is not a worktree of this repository (no tools/build.py)")
        return 1
    report = Report()
    settings = setup(root, args, report)
    if not args.check and settings:
        old = localconfig.load(root / ".mxl-local.json")
        old.update(settings)
        localconfig.save(old, root / ".mxl-local.json")
        print(f"wrote {root / '.mxl-local.json'}")
    print("READY: tools/build.py and tools/build_plugin.ps1 can run" if not report.failed else "NOT READY: see the FAIL lines above")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
