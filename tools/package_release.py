"""Player release of the port: the launcher's feed (release-manifest.json) and a .7z for manual / offline install.

From a finished build (tools/build.py -> work/mod) and the release plugin (cmake -DMXL_RELEASE=ON: no test harness, built
here unless --plugin is given) it writes into dist/:

  D2R-XL-2012-<version>.7z      solid LZMA2 7z (-mx7), top folder mxl2012/, the folder tools/install_mod.py writes into
                                 <D2R>\\mods:
                                   mxl2012.mpq/modinfo.json   {"name": "mxl2012", "savepath": "mxl2012/"}
                                   mxl2012.mpq/data/...       install_mod.build_data (work/mod/data + the install-time merges)
                                   d2rloader/plugins/mxl2012-core.dll, d2rloader/config/d2rloader.toml, d2rloader/patches/,
                                   d2rloader/metadata.json     (modVersion = <version>, website = the GitHub repo)
                                 The manual download for players, and where tools/publish_release.py reads the file bytes
                                 from. There is no zip (owner decision 2026-10-26). Needs 7-Zip: the run stops without it.
  release-manifest.json          schemaVersion 2: version, required D2R build, required D2RLoader + sha256, every file of
                                 the mod folder with size and sha256, the 7z as "archive" (docs/release.md "Release manifest")
  RELEASE_NOTES-<version>.md     the player's notes: NOTES below (downloader install), or --notes TEMPLATE
                                 (tools/data/release_notes_alpha.md: the hand-copied alpha, manual install only)
  SHA256SUMS                     of the 7z, the manifest and the notes

Nothing else goes in: no test harness files, test configs, saves or logs (checked), and no file that is a byte copy of one in
the D2R baseline (fxpaths.D2R: MXL_D2R_EXTRACT / extract/d2r/93847 / the machine's extract_dir) or the shared D2R cache (Blizzard's own
files: D2R reads those from its own install). Without a baseline that check cannot run, so a package with data stops.
The release plugin is built by tools/build_plugin.ps1 -Release (CMake on PATH or Visual Studio's, the PluginSDK of
.mxl-local.json; nothing is downloaded). tools/verify_package.py checks the finished 7z; tools/cut_alpha.ps1 runs it all.

  py -3 tools/package_release.py [--version 0.70.0] [--plugin DLL] [--data-from DIR] [--game DIR] [--out dist] [--notes MD]
  py -3 tools/package_release.py --no-data --plugin build/mxl2012-core.dll   (CI: no game files there; plugin + config only)
Version: PluginVersion of plugin/src/mxl2012_core.cpp; --version must equal it (only --no-data builds may differ).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import install_mod  # noqa: E402
import fxpaths  # noqa: E402  (the D2R baseline and the shared D2R cache, .mxl-local.json)

ROOT = install_mod.ROOT
NAME = "mxl2012"
REPO_URL = "https://github.com/Nugwa628/mxl2012-d2r"
EXTRACT = fxpaths.D2R  # D2R 93847's extraction (MXL_D2R_EXTRACT > extract/d2r/93847 > the machine's extract_dir, read-only)
RELEASE_BUILD = ROOT / "build" / "plugin-release"
D2R = {"build": install_mod.D2R_BUILD, "version": "3.3.0", "imageTimestamp": "0x6ab3782c"}  # plugin/src/build_guard_logic.h
# The pinned D2RLoader (docs/setup.md step 10)
D2RLOADER = {"version": "1.3.1-beta", "url": "https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip", "size": 47652455,
             "sha256": "9286c6b5bff7f1043658411dbea305faa9698b6a455e6441668fc6d02c22aad7",
             "signerThumbprint": "8001082E968FADAA58BF2F73EFA1810A11D0C28F"}
# What the game folder's own d2rloader/config/d2rloader.toml needs for this mod ([d2rloader] section of D2RLoader's config):
# the mod starts by itself. The player sets it in the game (Default Mod); the downloader does not write that file. No -txt:
# D2RLoader 1.3.1 compiles the mod's .txt tables itself at each start (docs/launcher.md "How the player starts the game").
LAUNCH = {"default_mod": NAME, "launch_arguments": ""}
# The player's own settings: the downloader writes these only when they are missing (docs/release.md).
PRESERVE = ["d2rloader/config/d2rloader.toml"]
SCHEMA = 2  # 2: the 7z ("archive") replaced the zip; the downloader installs from it or from objects (docs/release.md)
STAMP = (2026, 1, 1, 0, 0, 0)  # the staged files' mtime
# 7z: LZMA2, one solid block, multithreaded. No time stamps go in the archive (-mtm/-mtc/-mta off) and the staged files get
# STAMP as mtime anyway; the same input gives the same bytes with the same 7-Zip build (docs/release.md).
SEVENZ_ARGS = ["a", "-t7z", "-m0=lzma2", "-mx=7", "-ms=on", "-mmt=on", "-mtm=off", "-mtc=off", "-mta=off", "-bd", "-y"]
SEVENZ_NAMES = ("7z", "7zz", "7za", "7zr")
NO_7Z = ("no 7-Zip found (Program Files\\7-Zip\\7z.exe, or 7z / 7zz / 7za / 7zr on PATH). A release is a .7z only: install "
         "7-Zip (https://www.7-zip.org; Debian / Ubuntu: apt install 7zip) and run again")

FORBIDDEN = re.compile(r"(^|/)(mxl2012-testharness[^/]*|mxl2012-core-off\.txt|input-bindings\.toml|imgui\.ini|debugsettings\.json)$"
                       r"|\.(d2s|d2i|d2x|d2rl|ctc|ctl|key|map|ma\d|log|dmp|pdb|orig)$", re.I)  # saves: D2R and D2RLoader sidecars


def plugin_version() -> str:
    m = re.search(r'PluginVersion = "([^"]+)"', (ROOT / "plugin" / "src" / "mxl2012_core.cpp").read_text("utf-8"))
    return m.group(1)


def build_release_plugin() -> Path:
    """tools/build_plugin.ps1 -Release: the dev DLL (build/plugin) and the player DLL (-DMXL_RELEASE=ON, build/plugin-release).
    The script finds CMake (PATH or Visual Studio's) and the PluginSDK (.mxl-local.json, else the submodule) and never
    downloads anything (a bare `cmake` is not on PATH on the build PC, and `git submodule update` would need the network)."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_plugin.ps1 -Release: build the plugin there and pass --plugin DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_plugin.ps1"), "-Release"], cwd=ROOT)
    return RELEASE_BUILD / "Release" / "mxl2012-core.dll"


def check_release_plugin(dll: Path, version: str) -> list:
    """Problems of a plugin DLL for a release: the test harness must be compiled out, and the version must be the release's."""
    b = dll.read_bytes()
    problems = []
    if b"mxl2012-testharness" in b:
        problems.append(f"{dll} has the test harness (build it with -DMXL_RELEASE=ON)")
    if version.encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry PluginVersion {version}")
    return problems


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage(mod: Path, version: str, plugin: Path, game: Path, data_from: Path = None, no_data: bool = False) -> None:
    if mod.exists():
        shutil.rmtree(mod)
    data = mod / f"{NAME}.mpq" / "data"
    if data_from is not None:
        shutil.copytree(data_from, data)
    elif not no_data:
        install_mod.build_data(data, game)
    install_mod.write_mod_files(mod, NAME, f"{NAME}/", plugin, {
        "modVersion": version, "website": REPO_URL,
        "description": "D2R-XL 2012: Median XL 2012 (v005) for Diablo II: Resurrected (build %s) through D2RLoader." % install_mod.D2R_BUILD})


def baselines(extract: Path = EXTRACT, cache: Path = None) -> list:
    """The folders holding D2R's own data/... files: the baseline extraction and the shared D2R cache (fxpaths.D2R_CACHE:
    the files the extraction lacks, e.g. animdata.d2, missiles.json), those that exist."""
    cache = fxpaths.D2R_CACHE if cache is None else cache
    return [b for b in (extract, cache) if b and (Path(b) / "data").is_dir()]


def drop_blizzard_copies(mod: Path, extract: Path = EXTRACT, cache: Path = None) -> int:
    """Remove files that are byte copies of D2R's own (same path under <baseline>/data, baselines()): the game has them
    already. dataversionbuild.txt is ours (install_mod writes it). -> number removed."""
    data = mod / f"{NAME}.mpq" / "data"
    n = 0
    roots = baselines(extract, cache)
    if not roots or not data.is_dir():
        return 0
    for p in sorted(data.rglob("*")):
        if not p.is_file() or p.name.lower() == "dataversionbuild.txt":
            continue
        rel = p.relative_to(data)
        size = p.stat().st_size
        for b in roots:
            twin = Path(b) / "data" / rel
            if twin.is_file() and twin.stat().st_size == size and twin.read_bytes() == p.read_bytes():
                p.unlink()
                n += 1
                for d in p.parents:  # a folder emptied this way is not ours either (no emptyDirs entry for it)
                    if d == data or any(d.iterdir()):
                        break
                    d.rmdir()
                break
    return n


def forbidden_files(mod: Path) -> list:
    return [p.relative_to(mod).as_posix() for p in mod.rglob("*") if p.is_file() and FORBIDDEN.search(p.relative_to(mod).as_posix())]


def file_list(mod: Path) -> list:
    return [{"path": p.relative_to(mod).as_posix(), "size": p.stat().st_size, "sha256": sha256(p)}
            for p in sorted(mod.rglob("*"), key=lambda q: q.relative_to(mod).as_posix()) if p.is_file()]


def empty_dirs(mod: Path) -> list:
    """Folders with nothing in them (d2rloader/patches): listed in the manifest, so the server builds the same 7z."""
    return sorted(p.relative_to(mod).as_posix() for p in mod.rglob("*") if p.is_dir() and not any(p.iterdir()))


def find_7z():
    """The 7-Zip command line: 7-Zip\\7z.exe under Program Files, else 7z / 7zz / 7za / 7zr on PATH. None when there is none."""
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(var)
        exe = Path(base) / "7-Zip" / "7z.exe" if base else None
        if exe and exe.is_file():
            return str(exe)
    for name in SEVENZ_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def fix_mtimes(mod: Path) -> None:
    """Every staged file and folder gets STAMP as its mtime."""
    t = time.mktime(STAMP + (0, 0, -1))
    for p in [mod, *mod.rglob("*")]:
        os.utime(p, (t, t))


def write_7z(mod: Path, out: Path, sevenzip=None) -> None:
    """Solid LZMA2 7z of the staged folder, top folder mxl2012/ (empty folders kept). Raises RuntimeError when there is no
    7-Zip or it fails; nothing is left behind then."""
    exe = sevenzip or find_7z()
    if not exe:
        raise RuntimeError(NO_7Z)
    fix_mtimes(mod)
    out.unlink(missing_ok=True)  # `7z a` would add to an existing archive
    r = subprocess.run([exe, *SEVENZ_ARGS, str(out.resolve()), mod.name], cwd=mod.parent, capture_output=True, text=True,
                       errors="replace")
    if r.returncode != 0 or not out.is_file():
        out.unlink(missing_ok=True)
        raise RuntimeError(f"7-Zip failed ({r.returncode}): {(r.stdout + r.stderr).strip()[-600:]}")


def manifest(version: str, files: list, archive_path: Path, complete: bool, dirs=()) -> dict:
    """archive_path: the .7z. The launcher installs from the objects (docs/release.md), never from the archive."""
    return {
        "schemaVersion": SCHEMA,
        "name": NAME,
        "version": version,
        "pluginVersion": plugin_version(),
        "released": datetime.date.today().isoformat(),
        "complete": complete,  # false: a --no-data build (no mxl2012.mpq/data); not for players
        "d2r": D2R,
        "d2rloader": D2RLOADER,
        "launch": LAUNCH,
        "modFolder": NAME,  # the paths below are relative to <D2R>/mods/<modFolder>/
        "saveFolder": f"{NAME}/",  # under Saved Games/Diablo II Resurrected/mods/ (modinfo.json savepath)
        "preserve": PRESERVE,
        "archive": {"format": "7z", "name": archive_path.name, "size": archive_path.stat().st_size,
                    "sha256": sha256(archive_path)},  # the manual download
        "emptyDirs": list(dirs),  # folders the 7z holds although no file is in them (d2rloader/patches)
        "fileCount": len(files),
        "totalSize": sum(f["size"] for f in files),
        "files": files,
    }


UNPACK_7Z = ("Unpack `{archive}` into `<D2R folder>\\mods\\` so that `<D2R folder>\\mods\\mxl2012\\mxl2012.mpq\\modinfo.json` exists\n"
             "   (Windows 11 opens .7z files; otherwise use 7-Zip, https://www.7-zip.org).")

NOTES = """# D2R-XL 2012 {version}

D2R-XL 2012 is Median XL 2012 (v005, by Brother Laz) ported to Diablo II: Resurrected through the D2RLoader plugin mxl2012-core {plugin}.

## Requirements

- Diablo II: Resurrected **build {build}** (D2R {d2rver}). On any other build the plugin installs nothing and shows
  "D2R-XL 2012 {plugin} needs D2R build {build}; this is <n>".
- D2RLoader **{loader}** ({loader_url}, sha256 `{loader_sha}`).

## Install

1. Install D2RLoader {loader} from https://d2rloader.net/ into your D2R folder (build {build}).
2. Run `D2R-XL-2012-Downloader.exe` (downloads from https://files.werdegames.com/mxl2012/) and press **Install** (or **Update**). It puts the mod
   in `<D2R folder>\\mods\\mxl2012` and changes nothing else.
3. How to play: start `D2RLoader.exe` in your D2R folder. The first time, click the gear on the character screen, set
   Default Mod to D2R-XL 2012, Apply, and start D2RLoader again.

By hand (offline), into a D2R folder at build {build} that has D2RLoader {loader}:

1. {unpack}
2. Set the default mod as in step 3 above (or `default_mod = "mxl2012"` in
   `<D2R folder>\\d2rloader\\config\\d2rloader.toml`).
3. Start `D2RLoader.exe`. Characters are saved in `Saved Games\\Diablo II Resurrected\\mods\\mxl2012\\`.
   To update, delete `mods\\mxl2012\\mxl2012.mpq\\data` and unpack the new release; keep your
   `mods\\mxl2012\\d2rloader\\config\\d2rloader.toml` if you changed it.

## Changes

- TODO

## Known issues

- TODO (docs/unported.md lists what is not ported yet)

## Checksums

See SHA256SUMS.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="release version (default: PluginVersion)")
    ap.add_argument("--plugin", type=Path, help="a release mxl2012-core.dll (default: build it with -DMXL_RELEASE=ON)")
    ap.add_argument("--data-from", type=Path, help="copy this finished mxl2012.mpq/data instead of building it")
    ap.add_argument("--no-data", action="store_true", help="no mxl2012.mpq/data (CI): manifest says complete=false")
    ap.add_argument("--game", type=Path, default=Path(install_mod.DEFAULT_GAME), help="D2R folder read for maps_hd (CASC)")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    ap.add_argument("--notes", type=Path, help="release notes template (str.format fields as NOTES; default NOTES)")
    a = ap.parse_args()

    version = (a.version or plugin_version()).lstrip("v")
    if version != plugin_version():
        # One number for the release and the plugin inside it (the build guard and `mxl` show PluginVersion): a player
        # release must raise PluginVersion in plugin/src/mxl2012_core.cpp, even for a repackage. --no-data builds (CI, tests)
        # are not player releases and may differ.
        if not a.no_data:
            print(f"error: release {version} but PluginVersion is {plugin_version()}: set PluginVersion in "
                  f"plugin/src/mxl2012_core.cpp to {version} (or leave out --version)")
            return 1
        print(f"note: release {version}, plugin PluginVersion {plugin_version()} (--no-data: allowed)")
    sevenzip = find_7z()
    if not sevenzip:  # before the long part of the run
        print(f"error: {NO_7Z}")
        return 1
    if not a.no_data and a.data_from is None and not (install_mod.SRC / "global" / "excel").exists():
        print("work/mod/data is missing: run tools/build.py first")
        return 1
    if not a.no_data and not (EXTRACT / "data").is_dir():
        print(f"error: no D2R {install_mod.D2R_BUILD} baseline at {EXTRACT}, so Blizzard's own files cannot be left out: "
              f"{fxpaths.localconfig.SETUP_HINT} (or set MXL_D2R_EXTRACT)")
        return 1
    template = NOTES
    if a.notes:
        if not a.notes.is_file():
            print(f"no notes template at {a.notes}")
            return 1
        template = a.notes.read_text("utf-8")
    plugin = a.plugin or build_release_plugin()
    if not plugin.is_file():
        print(f"no plugin at {plugin}")
        return 1
    problems = check_release_plugin(plugin, plugin_version())
    if problems:
        print("\n".join(problems))
        return 1

    a.out.mkdir(parents=True, exist_ok=True)
    mod = a.out / "stage" / NAME
    stage(mod, version, plugin, a.game, a.data_from, a.no_data)
    dropped = drop_blizzard_copies(mod)
    if dropped:
        print(f"left out {dropped} files that are byte copies of D2R's own (extract/d2r/{install_mod.D2R_BUILD})")
    bad = forbidden_files(mod)
    if bad:
        print("refusing to package test or player files: " + ", ".join(bad[:20]))
        return 1

    for old in a.out.glob("D2R-XL-2012-*.zip"):  # an earlier packager's zip must not sit next to this release
        old.unlink()
    seven_path = a.out / f"D2R-XL-2012-{version}{'-nodata' if a.no_data else ''}.7z"
    t7 = time.time()
    try:
        write_7z(mod, seven_path, sevenzip)
    except RuntimeError as e:
        print(f"error: {e}")
        return 1
    t7 = time.time() - t7
    files = file_list(mod)
    man_path = a.out / "release-manifest.json"
    man_path.write_text(json.dumps(manifest(version, files, seven_path, not a.no_data, empty_dirs(mod)), indent=1) + "\n",
                        encoding="utf-8")
    notes = a.out / f"RELEASE_NOTES-{version}.md"
    notes.write_text(template.format(version=version, plugin=plugin_version(), build=D2R["build"], d2rver=D2R["version"],
                                  loader=D2RLOADER["version"], loader_url=D2RLOADER["url"], loader_sha=D2RLOADER["sha256"],
                                  unpack=UNPACK_7Z.format(archive=seven_path.name), archive=seven_path.name,
                                  archive_mb=round(seven_path.stat().st_size / 1e6), unpacked_mb=round(sum(f["size"] for f in files) / 1e6),
                                  file_count=len(files), save_folder=f"{NAME}/"), encoding="utf-8")
    (a.out / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in (seven_path, man_path, notes)), encoding="utf-8")
    shutil.rmtree(a.out / "stage")
    print(f"{seven_path.name}: {len(files)} files, {sum(f['size'] for f in files) / 1e6:.0f} MB unpacked, "
          f"{seven_path.stat().st_size / 1e6:.0f} MB as 7z ({t7:.0f} s); {man_path.name}, {notes.name}, SHA256SUMS in {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
