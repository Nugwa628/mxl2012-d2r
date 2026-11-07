"""Player release of the port: the launcher's feed (release-manifest.json) and a .7z for manual / offline install.

From a finished build (tools/build.py -> work/mod) and the release plugin (cmake -DMXL_RELEASE=ON: no test harness, built
here unless --plugin is given) it writes into dist/:

  D2R-XL-2012-<version>.7z      solid LZMA2 7z (-mx7), top folder mxl2012/, the folder tools/install_mod.py writes into
                                 <D2R>\\mods:
                                   mxl2012.mpq/modinfo.json   {"name": "mxl2012", "savepath": "mxl2012/"}
                                   mxl2012.mpq/data/...       install_mod.build_data (work/mod/data + the install-time merges)
                                   d2rloader/plugins/mxl2012-core.dll, d2rloader/config/d2rloader.toml + mxl2012-core.toml, d2rloader/patches/,
                                   d2rloader/metadata.json     (modVersion = <version>, website = the GitHub repo)
                                   d2rloader/plugins/legacy169.dll, d2rloader/config/legacy169.toml (D2R Legacy 16:9 at
                                   the pinned commit, tools/build_legacy169.ps1 unless --legacy169 is given)
                                   d2rloader/plugins/d2rl-buff-panel.dll + .mpq + licences, d2rloader/config/buff-panel.toml
                                   (Buff HUD, our fork of Lukaszpg's plugin at the pinned commit, tools/build_buffhud.ps1
                                   unless --buffhud is given)
                                   d2rloader/plugins/d2rl-auto-belt-refill.dll, d2rloader/config/auto-belt-refill.toml
                                   (Auto Belt Refill by jaycachou-svg at the pinned commit + our patches,
                                   tools/build_beltrefill.ps1 unless --beltrefill is given)
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

  py -3 tools/package_release.py [--version 0.70.0] [--plugin DLL] [--legacy169 DLL] [--buffhud DLL] [--beltrefill DLL] [--data-from DIR] [--game DIR] [--out dist] [--notes MD]
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
import urllib.parse
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
# The pinned D2RLoader (docs/setup.md step 10). The downloader's Install D2RLoader fetches `url` (https on d2rloader.net
# only) when the player asks and installs it only when `size` and `sha256` match (docs/launcher.md "Install D2RLoader").
D2RLOADER = {"version": "1.3.1-beta", "url": "https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip", "size": 47652455,
             "sha256": "9286c6b5bff7f1043658411dbea305faa9698b6a455e6441668fc6d02c22aad7",
             "signerThumbprint": "8001082E968FADAA58BF2F73EFA1810A11D0C28F"}
# What the game folder's own d2rloader/config/d2rloader.toml needs for this mod ([d2rloader] section of D2RLoader's config):
# the mod starts by itself. The player sets it in the game (Default Mod); the downloader does not write that file. No -txt:
# D2RLoader 1.3.1 compiles the mod's .txt tables itself at each start (docs/launcher.md "How the player starts the game").
LAUNCH = {"default_mod": NAME, "launch_arguments": ""}
# Our own D2R Legacy 16:9 plugin (docs/bundled-plugins.md), shipped in the mod folder: built from its source at the commit
# the gitlink third_party/D2R-Legacy169 pins (tools/build_legacy169.ps1), unless --legacy169 is given. Its default config goes
# in too, as a `preserve` file: D2RLoader would write it at the first start, but the downloader removes files the release does
# not list, so a player's `enabled = false` would not survive an update.
LEGACY169 = {"name": "D2R Legacy 16:9", "version": "0.1.1", "repo": "https://github.com/Nugwa628/D2R-Legacy169",
             "dll": "d2rloader/plugins/legacy169.dll", "config": "d2rloader/config/legacy169.toml"}
LEGACY169_BUILD = ROOT / "build" / "legacy169"
# Buff HUD by Lukaszpg (MIT), shipped as our fork (branch mxl2012: the generic fixes offered upstream plus the Median XL 2012
# buff list inside its companion MPQ), docs/bundled-plugins.md. Built from the commit the gitlink third_party/d2rl-buff-hud pins
# (tools/build_buffhud.ps1), unless --buffhud is given. The MPQ sits next to the DLL; the fork's MIT licence (copyright
# Lukaszpg) and the PluginSDK licence it links go next to them. Its default config is a `preserve` file, as legacy169's.
BUFFHUD = {"name": "Buff HUD", "version": "1.1.0", "repo": "https://github.com/Nugwa628/d2rl-buff-hud",
           "upstream": "https://github.com/Lukaszpg/d2rl-buff-hud", "author": "Lukaszpg",
           "dll": "d2rloader/plugins/d2rl-buff-panel.dll", "mpq": "d2rloader/plugins/d2rl-buff-panel.mpq",
           "config": "d2rloader/config/buff-panel.toml",
           "licence": "d2rloader/plugins/d2rl-buff-panel-LICENSE.txt",
           "sdk_licence": "d2rloader/plugins/d2rl-buff-panel-PluginSDK-LICENSE.txt"}
BUFFHUD_BUILD = ROOT / "build" / "buffhud"
BUFFHUD_FILES = ("dll", "mpq", "config", "licence", "sdk_licence")
# Auto Belt Refill by jaycachou-svg, shipped with the author's permission (2026-11-06; the repository has no licence file),
# docs/bundled-plugins.md. Built from the author's source at the commit the gitlink third_party/auto-belt-refill pins, with our
# patches (third_party/auto-belt-refill-mxl2012/*.patch: PluginSDK renames, Median belt rows, first-slot
# matching and belt counts) applied at build time (tools/build_beltrefill.ps1), unless --beltrefill is given. Its config is ours
# (columns follow their first slot, elixirs never refilled, keys unbound) and a
# `preserve` file, as legacy169's. The author's prebuilt DLL is for an older D2RLoader ABI and is refused.
BELTREFILL = {"name": "Auto Belt Refill", "version": "0.35.9", "repo": "https://github.com/jaycachou-svg/auto-belt-refill",
              "author": "jaycachou-svg", "dll": "d2rloader/plugins/d2rl-auto-belt-refill.dll",
              "config": "d2rloader/config/auto-belt-refill.toml"}
BELTREFILL_BUILD = ROOT / "build" / "beltrefill"
BELTREFILL_OURS = ROOT / "third_party" / "auto-belt-refill-mxl2012"  # the patches, our CMakeLists.txt and the config
BELTREFILL_FILES = ("dll", "config")
BELTREFILL_AUTHOR_DLL = "77c7d1b9068c8cacc2fded62ff1120b441001d601ad65a8ee3043e3b61c650db"  # its plugins/ at the pinned commit
# The player's own settings: the downloader writes these only when they are missing (docs/release.md).
PRESERVE = ["d2rloader/config/d2rloader.toml", "d2rloader/config/mxl2012-core.toml"]
SCHEMA = 2  # 2: the 7z ("archive") replaced the zip; the downloader installs from it or from objects (docs/release.md)
STAMP = (2026, 1, 1, 0, 0, 0)  # the staged files' mtime
# 7z: LZMA2, one solid block, multithreaded. No time stamps go in the archive (-mtm/-mtc/-mta off) and the staged files get
# STAMP as mtime anyway; the same input gives the same bytes with the same 7-Zip build (docs/release.md).
SEVENZ_ARGS = ["a", "-t7z", "-m0=lzma2", "-mx=7", "-ms=on", "-mmt=on", "-mtm=off", "-mtc=off", "-mta=off", "-bd", "-y"]
SEVENZ_NAMES = ("7z", "7zz", "7za", "7zr")
NO_7Z = ("no 7-Zip found (Program Files\\7-Zip\\7z.exe, or 7z / 7zz / 7za / 7zr on PATH). A release is a .7z only: install "
         "7-Zip (https://www.7-zip.org; Debian / Ubuntu: apt install 7zip) and run again")

FORBIDDEN = re.compile(r"(^|/)(mxl2012-testharness[^/]*|legacy169-testharness[^/]*|mxl2012-core-off\.txt|input-bindings\.toml|imgui\.ini|debugsettings\.json)$"
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


def pinned_commit(path: str) -> str:
    """The commit a gitlink of this repo pins (index, as HEAD in a clean checkout)."""
    out = subprocess.run(["git", "ls-files", "-s", path], cwd=ROOT, capture_output=True, text=True).stdout.split()
    if len(out) < 2 or out[0] != "160000":
        raise SystemExit(f"{path} is not a pinned submodule of this repo")
    return out[1]


def legacy169_commit() -> str:
    """The D2R-Legacy169 commit this repo pins: the gitlink third_party/D2R-Legacy169."""
    return pinned_commit("third_party/D2R-Legacy169")


def buffhud_commit() -> str:
    """The d2rl-buff-hud fork commit this repo pins: the gitlink third_party/d2rl-buff-hud."""
    return pinned_commit("third_party/d2rl-buff-hud")


def beltrefill_commit() -> str:
    """The auto-belt-refill commit this repo pins: the gitlink third_party/auto-belt-refill."""
    return pinned_commit("third_party/auto-belt-refill")


def beltrefill_patches(ours: Path = BELTREFILL_OURS) -> list:
    """Our patches as tools/build_beltrefill.ps1 records them in PATCHES: "<sha256>  <name>", in name order."""
    return [f"{sha256(p)}  {p.name}" for p in sorted(ours.glob("*.patch"), key=lambda p: p.name)]


def build_legacy169() -> Path:
    """tools/build_legacy169.ps1: legacy169.dll from the pinned commit's source (release options, its unit tests run)."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_legacy169.ps1: build legacy169.dll there and pass --legacy169 DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_legacy169.ps1")], cwd=ROOT)
    return LEGACY169_BUILD / "Release" / "legacy169.dll"


def check_legacy169(dll: Path) -> list:
    """Problems of a legacy169.dll for a release: no test build (harness or bad-bytes table), the pinned version."""
    b = dll.read_bytes()
    problems = []
    if b"legacy169-testharness" in b or b"-test\0" in b:
        problems.append(f"{dll} is a legacy169 test build (build it with tools/build_legacy169.ps1)")
    if b"legacy169" not in b or LEGACY169["version"].encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry legacy169 version {LEGACY169['version']}")
    return problems


def build_buffhud() -> Path:
    """tools/build_buffhud.ps1: d2rl-buff-panel.dll + .mpq from the pinned commit's source (the fork's release preset and tests)."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_buffhud.ps1: build Buff HUD there and pass --buffhud DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_buffhud.ps1")], cwd=ROOT)
    return BUFFHUD_BUILD / "Release" / "d2rl-buff-panel.dll"


def check_buffhud(dll: Path) -> list:
    """Problems of a Buff HUD build for a release: our fork (its buff-panel.toml switch is embedded), the pinned version, and
    a packed companion MPQ next to the DLL."""
    b = dll.read_bytes()
    problems = []
    if b"buff-panel" not in b or BUFFHUD["version"].encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry Buff HUD version {BUFFHUD['version']}")
    if b"[buff_panel]" not in b:
        problems.append(f"{dll} is not our fork's build (no buff-panel.toml embedded): build it with tools/build_buffhud.ps1")
    mpq = dll.with_suffix(".mpq")
    if not mpq.is_file():
        problems.append(f"no {mpq.name} next to {dll}")
    elif mpq.read_bytes()[:4] != b"MPQ\x1a":
        problems.append(f"{mpq} is not a packed MPQ")
    return problems


def build_beltrefill() -> Path:
    """tools/build_beltrefill.ps1: d2rl-auto-belt-refill.dll from the pinned commit's source with our patches."""
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        raise SystemExit("no PowerShell to run tools/build_beltrefill.ps1: build Auto Belt Refill there and pass --beltrefill DLL")
    subprocess.check_call([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "tools" / "build_beltrefill.ps1")], cwd=ROOT)
    return BELTREFILL_BUILD / "Release" / "d2rl-auto-belt-refill.dll"


def check_beltrefill(dll: Path) -> list:
    """Problems of an Auto Belt Refill build for a release: the pinned version, and not the author's prebuilt DLL (written for
    an older D2RLoader ABI, without the Median belt rows)."""
    b = dll.read_bytes()
    problems = []
    if b"auto-belt-refill\0" not in b or BELTREFILL["version"].encode() + b"\0" not in b:
        problems.append(f"{dll} does not carry Auto Belt Refill version {BELTREFILL['version']}")
    if hashlib.sha256(b).hexdigest() == BELTREFILL_AUTHOR_DLL:
        problems.append(f"{dll} is the author's prebuilt DLL (older D2RLoader ABI): build it with tools/build_beltrefill.ps1")
    return problems


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


def stage(mod: Path, version: str, plugin: Path, game: Path, data_from: Path = None, no_data: bool = False,
          legacy169: Path = None, buffhud: Path = None, beltrefill: Path = None) -> None:
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
    if legacy169 is not None:
        stage_legacy169(mod, legacy169)
    if buffhud is not None:
        stage_buffhud(mod, buffhud)
    if beltrefill is not None:
        stage_beltrefill(mod, beltrefill)


def stage_legacy169(mod: Path, dll: Path, src: Path = ROOT / "build" / "legacy169-src") -> None:
    """legacy169.dll into d2rloader/plugins/ (mod-scoped: only with this mod) and its default legacy169.toml from the pinned
    source (tools/build_legacy169.ps1 exports it to build/legacy169-src) into d2rloader/config/."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else None
    if pinned != legacy169_commit():
        raise SystemExit(f"{src} is not the pinned commit {legacy169_commit()[:9]} (it is {pinned}): run "
                         "tools/build_legacy169.ps1")
    shutil.copy2(dll, mod / LEGACY169["dll"])
    shutil.copy2(src / "legacy169.toml", mod / LEGACY169["config"])


def stage_buffhud(mod: Path, dll: Path, src: Path = ROOT / "build" / "buffhud-src") -> None:
    """d2rl-buff-panel.dll and its companion MPQ (the Median buff list is inside it) into d2rloader/plugins/ (mod-scoped), the
    fork's LICENSE and its PluginSDK's next to them, and the default buff-panel.toml into d2rloader/config/, all from the pinned
    source that tools/build_buffhud.ps1 exports to build/buffhud-src."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else None
    if pinned != buffhud_commit():
        raise SystemExit(f"{src} is not the pinned commit {buffhud_commit()[:9]} (it is {pinned}): run tools/build_buffhud.ps1")
    shutil.copy2(dll, mod / BUFFHUD["dll"])
    shutil.copy2(dll.with_suffix(".mpq"), mod / BUFFHUD["mpq"])
    shutil.copy2(src / "LICENSE", mod / BUFFHUD["licence"])
    shutil.copy2(src / "external" / "PluginSDK" / "LICENSE", mod / BUFFHUD["sdk_licence"])
    shutil.copy2(src / "buff-panel.toml", mod / BUFFHUD["config"])


def stage_beltrefill(mod: Path, dll: Path, src: Path = ROOT / "build" / "beltrefill-src", ours: Path = BELTREFILL_OURS) -> None:
    """d2rl-auto-belt-refill.dll into d2rloader/plugins/ (mod-scoped) and our auto-belt-refill.toml (the locked Median columns)
    into d2rloader/config/. The build must come from the pinned commit with this repo's patches (tools/build_beltrefill.ps1
    records both in build/beltrefill-src)."""
    pinned = (src / "PINNED_COMMIT").read_text("ascii").strip() if (src / "PINNED_COMMIT").is_file() else None
    if pinned != beltrefill_commit():
        raise SystemExit(f"{src} is not the pinned commit {beltrefill_commit()[:9]} (it is {pinned}): run tools/build_beltrefill.ps1")
    applied = (src / "PATCHES").read_text("ascii").splitlines() if (src / "PATCHES").is_file() else []
    if [ln.strip() for ln in applied if ln.strip()] != beltrefill_patches(ours):
        raise SystemExit(f"{src} was not built with the patches in {ours}: run tools/build_beltrefill.ps1")
    shutil.copy2(dll, mod / BELTREFILL["dll"])
    shutil.copy2(ours / "auto-belt-refill.toml", mod / BELTREFILL["config"])


def preserve_list(mod: Path) -> list:
    """PRESERVE plus the bundled plugins' configs the package holds."""
    return PRESERVE + [c for c in (LEGACY169["config"], BUFFHUD["config"], BELTREFILL["config"]) if (mod / c).is_file()]


def bundled_plugins(legacy169: bool, buffhud: bool, beltrefill: bool = False) -> list:
    """The manifest's bundledPlugins: name, version, repository, source commit and files of each plugin the package holds."""
    out = []
    if legacy169:
        out.append({"name": LEGACY169["name"], "version": LEGACY169["version"], "repo": LEGACY169["repo"],
                    "commit": legacy169_commit(), "files": [LEGACY169["dll"], LEGACY169["config"]]})
    if buffhud:
        out.append({"name": BUFFHUD["name"], "version": BUFFHUD["version"], "repo": BUFFHUD["repo"],
                    "upstream": BUFFHUD["upstream"], "author": BUFFHUD["author"], "commit": buffhud_commit(),
                    "files": [BUFFHUD[k] for k in BUFFHUD_FILES]})
    if beltrefill:
        out.append({"name": BELTREFILL["name"], "version": BELTREFILL["version"], "repo": BELTREFILL["repo"],
                    "author": BELTREFILL["author"], "commit": beltrefill_commit(), "patches": beltrefill_patches(),
                    "files": [BELTREFILL[k] for k in BELTREFILL_FILES]})
    return out


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


LOADER_HOST = "d2rloader.net"


def loader_problems(block: dict) -> list:
    """What keeps the downloader from installing the manifest's d2rloader block (the same rules as
    launcher/src/core/loaderpkg.cpp LoaderPackageUsable): a version, an https url on d2rloader.net ending in a .zip name,
    a size, a 64-digit sha256."""
    out = []
    if not block.get("version"):
        out.append("d2rloader.version is missing")
    url = urllib.parse.urlsplit(block.get("url") or "")
    host = (url.hostname or "").lower()
    if url.scheme != "https":
        out.append("d2rloader.url is not https://")
    elif host != LOADER_HOST and not host.endswith("." + LOADER_HOST):
        out.append(f"d2rloader.url is not on {LOADER_HOST}")
    elif not url.path.lower().endswith(".zip") or url.path.endswith("/.zip"):
        out.append("d2rloader.url does not name a .zip")
    size = block.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= 512 << 20:
        out.append("d2rloader.size is missing or out of range")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", block.get("sha256") or ""):
        out.append("d2rloader.sha256 is not 64 hex digits")
    return out


def manifest(version: str, files: list, archive_path: Path, complete: bool, dirs=(), preserve=None, bundled=()) -> dict:
    """archive_path: the .7z. The launcher installs from the objects (docs/release.md), never from the archive."""
    problems = loader_problems(D2RLOADER)
    if problems:
        raise ValueError("D2RLOADER: " + "; ".join(problems))
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
        "preserve": PRESERVE if preserve is None else preserve,
        "bundledPlugins": list(bundled),  # our other plugins in the mod folder: name, version, repo, commit, files
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
3. How to play: press **Play** in the downloader (it starts `D2RLoader.exe -mod mxl2012` in your D2R folder). Or start
   `D2RLoader.exe` yourself: the first time, click the gear on the character screen, set Default Mod to D2R-XL 2012, Apply,
   and start D2RLoader again.

By hand (offline), into a D2R folder at build {build} that has D2RLoader {loader}:

1. {unpack}
2. Set the default mod as in step 3 above, the D2RLoader.exe way (or `default_mod = "mxl2012"` in
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
    ap.add_argument("--legacy169", type=Path, help="a release legacy169.dll of the pinned commit (default: build it with "
                    "tools/build_legacy169.ps1; --no-data builds leave it out unless given)")
    ap.add_argument("--buffhud", type=Path, help="a release d2rl-buff-panel.dll of the pinned fork commit, its .mpq next to it "
                    "(default: build both with tools/build_buffhud.ps1; --no-data builds leave it out unless given)")
    ap.add_argument("--beltrefill", type=Path, help="a release d2rl-auto-belt-refill.dll of the pinned commit with our patches "
                    "(default: build it with tools/build_beltrefill.ps1; --no-data builds leave it out unless given)")
    ap.add_argument("--no-bundled", action="store_true", help="leave out legacy169, Buff HUD and Auto Belt Refill unless given "
                    "(unit tests; "
                    "tools/verify_package.py refuses such a package)")
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
    legacy169 = a.legacy169 or (None if a.no_data or a.no_bundled else build_legacy169())
    if legacy169 is not None:
        problems += check_legacy169(legacy169) if legacy169.is_file() else [f"no legacy169.dll at {legacy169}"]
    buffhud = a.buffhud or (None if a.no_data or a.no_bundled else build_buffhud())
    if buffhud is not None:
        problems += check_buffhud(buffhud) if buffhud.is_file() else [f"no d2rl-buff-panel.dll at {buffhud}"]
    beltrefill = a.beltrefill or (None if a.no_data or a.no_bundled else build_beltrefill())
    if beltrefill is not None:
        problems += check_beltrefill(beltrefill) if beltrefill.is_file() else [f"no d2rl-auto-belt-refill.dll at {beltrefill}"]
    if problems:
        print("\n".join(problems))
        return 1

    a.out.mkdir(parents=True, exist_ok=True)
    mod = a.out / "stage" / NAME
    stage(mod, version, plugin, a.game, a.data_from, a.no_data, legacy169, buffhud, beltrefill)
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
    bundled = bundled_plugins(legacy169 is not None, buffhud is not None, beltrefill is not None)
    man_path.write_text(json.dumps(manifest(version, files, seven_path, not a.no_data, empty_dirs(mod), preserve_list(mod),
                                            bundled), indent=1) + "\n", encoding="utf-8")
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
