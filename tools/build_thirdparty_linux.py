"""Builds the bundled third-party plugins on Linux, as the Windows scripts do (docs/bundled-plugins.md "Building on Linux").

  python tools/build_thirdparty_linux.py [PLUGIN ...] [--out DIR] [--repos DIR] [--sdk DIR] [--work DIR]
                                         [--skill-profile FILE] [--no-tests]

PLUGIN: legacy169 buffhud beltrefill controllerqol ehb fd vsr (default: all). Each is the Linux twin of its
tools/build_<name>.ps1 (build_legacy169, build_buffhud, build_beltrefill, build_controllerqol, build_enemyhealthbars,
build_floatingdamage, build_vendorstockrefresh): the same pinned commit exported with `git archive`, the same patches in
name order, the same CMake options and tests, and the same files in the same places. Only the compiler differs: MSVC under
wine (msvc-wine, Ninja, CMAKE_SYSTEM_NAME=Windows) instead of Visual Studio; test executables and D2RLCompiler.exe run under
wine. /Zi does not work under wine (C1902), so every build uses embedded debug info (CMP0141 NEW + Embedded), as
/d2work/toolchains/scripts/build_plugins_linux.sh does for our own plugins.

Output: --out (default /d2work/build/thirdparty-linux) gets the layout of the Windows build\\ folder, so package_release.py
finds every file by the same relative path (point its build/ at it, or pass --legacy169 OUT/legacy169/Release/legacy169.dll
and so on; the -src folders with PINNED_COMMIT / PATCHES / SKILL_PROFILE sit beside them):
  legacy169/Release/legacy169.dll                               legacy169-src/
  buffhud/Release/d2rl-buff-panel.dll + .mpq                    buffhud-src/
  beltrefill/Release/d2rl-auto-belt-refill.dll                  beltrefill-src/
  controllerqol/Release/Controller QOL Updates.dll              controllerqol-src/
  enemyhealthbars/Release/d2rl-enemy-health-bars.dll + notices  enemyhealthbars-src/
  floatingdamage/Release/d2rl-ruffneckk-floating-damage.dll ... floatingdamage-src/, floatingdamage-deps/
  vendorstockrefresh/Release/d2rl-ruffneckk-vendor-stock-refresh.dll ...  vendorstockrefresh-src/, vendorstockrefresh-deps/
CMake build trees go to OUT/_cmake/<plugin>.

Sources: a git repository that has the pinned commit, first of: the MXL_*_DIR variable the .ps1 reads (env or
.mxl-local.json), --repos DIR (<name>.git or <name> inside it), the worktree's submodule, else a bare clone of the public
URL (.gitmodules; graxytv's repo for Enemy Health Bars) into OUT/repos. The pinned commit is checked in every case.
PluginSDK: --sdk DIR, MXL2012_PLUGINSDK_DIR or the submodule when it has sources, else the pinned commit of the PluginSDK
repository exported into OUT/PluginSDK. FetchContent (Floating Damage, Vendor Stock Refresh) needs the network once.
Buff HUD's half-size legacy icon sheets come from a built mod: --work DIR (a checkout with work/mod and work/d2r-baseline),
default this checkout. Controller QOL: --skill-profile FILE embeds the mxl2012 skill seed (package_release.py makes it from
the package's skills.txt) and records its sha256 in controllerqol-src/SKILL_PROFILE.
"""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402,F401  (.mxl-local.json defaults: MXL2012_PLUGINSDK_DIR)

ROOT = Path(__file__).resolve().parent.parent
OUT = Path("/d2work/build/thirdparty-linux")
MSVC = Path(os.environ.get("MXL_MSVC_WINE", "/d2work/toolchains/msvc"))
WINEPREFIX = os.environ.get("WINEPREFIX", "/d2work/prefixes/msvc-build")
PY_BIN = Path(sys.executable).parent  # the venv: cmake, ninja
COMMON = ["-G", "Ninja", "-DCMAKE_SYSTEM_NAME=Windows", "-DCMAKE_SYSTEM_PROCESSOR=AMD64", "-DCMAKE_BUILD_TYPE=Release",
          "-DCMAKE_POLICY_DEFAULT_CMP0141=NEW", "-DCMAKE_MSVC_DEBUG_INFORMATION_FORMAT=Embedded",
          "-DCMAKE_CROSSCOMPILING_EMULATOR=wine"]
# The .ps1 scripts build with the Visual Studio generator (-A x64), which links every target with /SUBSYSTEM:CONSOLE; Ninja
# leaves a DLL's subsystem to link.exe (GUI). Buff HUD's own preset is Ninja on Windows too, so it does not get this.
VS_LIKE = ["-DCMAKE_SHARED_LINKER_FLAGS_INIT=/SUBSYSTEM:CONSOLE"]
EHB_URL = "https://github.com/graxytv/D2R-Over-the-Head-Health-Bars"
EHB_PIN = "e6b929bfa5c59e79e0cbabf898eb777f6d359132"
EHB_SHARE = ("EnemyHealthBars-0.2.6-Reimagined-Share.zip", "c0ed2aa43205202601ec8075f3043e6dada5f0992ab9423e2a6378ad4eec10f4")
EHB_SOURCE = ("source/EnemyHealthBars-0.2.6-Source.zip", "8e26f4a9164f38d4f0970d1d4cd0e68c416c8df1272b01b1e1682195cd1acfa1")
PLUGINS = ("legacy169", "buffhud", "beltrefill", "controllerqol", "ehb", "fd", "vsr")


def env() -> dict:
    e = dict(os.environ)
    e["PATH"] = os.pathsep.join([str(PY_BIN), str(MSVC / "bin" / "x64"), e.get("PATH", "")])
    e.update(WINEDEBUG="-all", WINEPREFIX=WINEPREFIX, CC="cl", CXX="cl")
    return e


def run(cmd, cwd=None, log=None, extra_env=None):
    """Runs cmd (output to the log file when given); exits with its code when it fails."""
    e = env()
    e.update(extra_env or {})
    print("  $ " + " ".join(str(c) for c in cmd), flush=True)
    if log is None:
        r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=e)
    else:
        with open(log, "a", encoding="utf-8") as f:
            f.write("$ " + " ".join(str(c) for c in cmd) + "\n")
            f.flush()
            r = subprocess.run([str(c) for c in cmd], cwd=cwd, env=e, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        if log is not None:
            tail = Path(log).read_text("utf-8", "replace").splitlines()[-25:]
            print("\n".join("    " + ln for ln in tail))
        raise SystemExit(f"FAILED ({r.returncode}): {' '.join(str(c) for c in cmd)}" + (f" (log {log})" if log else ""))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args, cwd=ROOT) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def pinned(path: str) -> str:
    out = git("ls-files", "-s", path).split()
    if len(out) < 2 or out[0] != "160000":
        raise SystemExit(f"{path} is not a pinned submodule of this repo")
    return out[1]


def has_commit(repo: Path, commit: str) -> bool:
    return subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
                          capture_output=True).returncode == 0


def gitmodule_url(path: str) -> str:
    return git("config", "-f", ".gitmodules", f"submodule.{path}.url").strip()


def local_setting(name: str):
    """As _cmake.ps1's Get-LocalSetting: the environment variable, else that key of the git-ignored .mxl-local.json."""
    if os.environ.get(name):
        return os.environ[name]
    cfg = ROOT / ".mxl-local.json"
    if cfg.is_file():
        v = json.loads(cfg.read_text("utf-8-sig")).get(name)
        return v if isinstance(v, str) and v else None
    return None


def find_repo(a, name: str, commit: str, setting: str = None, submodule: str = None, url: str = None) -> Path:
    """A git repository with `commit`: setting (env / .mxl-local.json), --repos, the submodule, else a clone of url."""
    tries = []
    if setting and local_setting(setting):
        tries.append(Path(local_setting(setting)))
    if a.repos:
        tries += [a.repos / f"{name}.git", a.repos / name]
    if submodule:
        tries.append(ROOT / submodule)
    tries.append(a.out / "repos" / f"{name}.git")
    for t in tries:
        if (t / "HEAD").is_file() or (t / ".git").exists():
            if has_commit(t, commit):
                return t
    url = url or gitmodule_url(submodule)
    dest = a.out / "repos" / f"{name}.git"
    if not dest.exists():
        print(f"  cloning {url} -> {dest} (needs the network once)")
        run(["git", "clone", "--quiet", "--bare", url, dest])
    else:
        run(["git", "-C", dest, "fetch", "--quiet", "origin", "+refs/heads/*:refs/heads/*"])
    if not has_commit(dest, commit):
        raise SystemExit(f"{name}: commit {commit} is in none of {[str(t) for t in tries]} nor in {url}")
    return dest


def export(repo: Path, commit: str, dest: Path, paths=()) -> None:
    """git archive of `commit` (files as committed, LF) into dest, which is made empty first."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    data = subprocess.run(["git", "-C", str(repo), "-c", "core.autocrlf=false", "-c", "core.eol=lf", "archive",
                           "--format=zip", commit, *paths], capture_output=True, check=True).stdout
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        z.extractall(dest)
    # zip drops the exec bits git keeps; nothing here needs them except scripts we never run directly


def apply_patches(ours: Path, directory: Path, extra=()) -> list:
    """Our patches in name order, applied as the .ps1 does (git apply --directory=<the exported tree>): here from inside the
    tree, which is outside every repository, so git apply works on plain files."""
    patches = sorted(ours.glob("*.patch"), key=lambda p: p.name)
    for p in patches:
        r = subprocess.run(["git", "-c", "core.autocrlf=false", "apply", "--whitespace=nowarn", *extra, str(p)],
                           cwd=directory)
        if r.returncode:
            raise SystemExit(f"{p.name} does not apply to {directory}")
    return patches


def write_patches(patches: list, dest: Path) -> None:
    dest.write_text("".join(f"{sha256(p)}  {p.name}\r\n" for p in patches), "ascii")


def write_ascii(dest: Path, *lines: str) -> None:
    """As PowerShell's Set-Content -Encoding ascii: CRLF after every line (package_release.py strips it)."""
    dest.write_text("".join(f"{ln}\r\n" for ln in lines), "ascii", newline="")


def sdk_dir(a) -> Path:
    """The PluginSDK of tools/build_plugin.ps1 (its pinned commit)."""
    for d in (a.sdk, Path(local_setting("MXL2012_PLUGINSDK_DIR")) if local_setting("MXL2012_PLUGINSDK_DIR") else None,
              ROOT / "third_party" / "PluginSDK"):
        if d is not None and (d / "CMakeLists.txt").is_file():
            return d
    commit = pinned("third_party/PluginSDK")
    dest = a.out / "PluginSDK"
    if (dest / "PINNED_COMMIT").is_file() and (dest / "PINNED_COMMIT").read_text().strip() == commit:
        return dest
    export(find_repo(a, "PluginSDK", commit, None, "third_party/PluginSDK"), commit, dest)
    (dest / "PINNED_COMMIT").write_text(commit + "\n")
    return dest


def winpath(p: Path) -> str:
    return subprocess.run(["winepath", "-w", str(p)], capture_output=True, text=True, env=env()).stdout.strip()


def wine(exe: Path, *args, log=None):
    run(["wine", exe, *args], log=log)


def fresh(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def cmake_configure(src: Path, build: Path, log: Path, *defs, vs_like=True):
    if build.exists():
        shutil.rmtree(build)
    run(["cmake", "-S", src, "-B", build, *COMMON, *(VS_LIKE if vs_like else []), *defs], log=log)


def cmake_build(build: Path, log: Path, *targets):
    run(["cmake", "--build", build, *([a for t in targets for a in ("--target", t)])], log=log)


# ---------------------------------------------------------------------------------------------------------------- plugins

def build_legacy169(a, log):
    pin = pinned("third_party/D2R-Legacy169")
    repo = find_repo(a, "D2R-Legacy169", pin, "MXL_LEGACY169_DIR", "third_party/D2R-Legacy169")
    src = a.out / "legacy169-src"
    export(repo, pin, src)
    write_ascii(src / "PINNED_COMMIT", pin)
    b = a.out / "_cmake" / "legacy169"
    cmake_configure(src, b, log, f"-DLEGACY169_PLUGINSDK_DIR={sdk_dir(a)}", "-DLEGACY169_TEST_HARNESS=OFF",
                    "-DLEGACY169_TEST_BAD_BYTES=OFF")
    cmake_build(b, log)
    if not a.no_tests:
        wine(b / "tests" / "legacy169_tests.exe", log=log)
    rel = fresh(a.out / "legacy169" / "Release")
    shutil.copy2(b / "legacy169.dll", rel)
    return [rel / "legacy169.dll"]


def compiler_wrapper(a, exe: Path) -> Path:
    """D2RLCompiler.exe under wine: a script CMake can run (it passes Linux paths; wine maps them on Z:)."""
    w = a.out / "_cmake" / "d2rlcompiler-wine.sh"
    w.parent.mkdir(parents=True, exist_ok=True)
    w.write_text("#!/bin/sh\n# D2RLCompiler.exe under wine (tools/build_thirdparty_linux.py)\n"
                 f'exec wine "{exe}" "$@"\n')
    w.chmod(0o755)
    return w


def no_powershell(a, *names) -> list:
    """The RuffnecKk suite's CMake requires PowerShell (find_program REQUIRED) for ctest-only policy scripts that the .ps1
    never runs (it runs the test executables by name, as here). Linux has none: the cache variables point at a stub that
    fails loudly if anything does run it."""
    stub = a.out / "_cmake" / "no-powershell.sh"
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text("#!/bin/sh\necho 'no PowerShell on this Linux build (tools/build_thirdparty_linux.py)' >&2\nexit 1\n")
    stub.chmod(0o755)
    return [f"-D{n}={stub}" for n in names]


def build_buffhud(a, log):
    pin = pinned("third_party/d2rl-buff-hud")
    repo = find_repo(a, "d2rl-buff-hud", pin, "MXL_BUFFHUD_DIR", "third_party/d2rl-buff-hud")
    sdk_pin = git("-C", str(repo), "ls-tree", pin, "external/PluginSDK").split()[2]
    sdk_repo = a.sdk if a.sdk and has_commit(a.sdk, sdk_pin) else find_repo(a, "PluginSDK", sdk_pin, "MXL2012_PLUGINSDK_DIR",
                                                                            "third_party/PluginSDK")
    src = a.out / "buffhud-src"
    export(repo, pin, src)
    export(sdk_repo, sdk_pin, src / "external" / "PluginSDK")
    write_ascii(src / "PINNED_COMMIT", pin)
    # the fork's scripts/build.ps1: the release preset (Ninja, cl), build, ctest; then the companion art and MPQ
    b = a.out / "_cmake" / "buffhud"
    compiler = compiler_wrapper(a, src / "external" / "D2RLCompiler" / "D2RLCompiler.exe")
    cmake_configure(src, b, log, f"-DD2RL_COMPILER={compiler}", f"-DPython3_EXECUTABLE={sys.executable}",
                    vs_like=False)
    cmake_build(b, log)
    if not a.no_tests:
        run(["ctest", "--test-dir", b, "--output-on-failure"], log=log)
    work = a.work or ROOT
    if not (work / "work" / "mod" / "data" / "global").is_dir():
        raise SystemExit(f"Buff HUD legacy icon sheets: no built mod in {work}/work. Run tools/build.py first, or pass --work")
    run([sys.executable, src / "scripts" / "make_companion_art.py", work], log=log)
    cmake_build(b, log, "buff_panel_companion")
    built = b / "stage" / "Release" / "d2rloader" / "plugins"
    rel = fresh(a.out / "buffhud" / "Release")
    for f in ("d2rl-buff-panel.dll", "d2rl-buff-panel.mpq"):
        shutil.copy2(built / f, rel / f)
    return [rel / "d2rl-buff-panel.dll", rel / "d2rl-buff-panel.mpq"]


def build_beltrefill(a, log):
    folder = "Auto-belt-refill-v0.35.9-EN"
    pin = pinned("third_party/auto-belt-refill")
    repo = find_repo(a, "auto-belt-refill", pin, "MXL_BELTREFILL_DIR", "third_party/auto-belt-refill")
    src = a.out / "beltrefill-src"
    export(repo, pin, src, [folder])
    ours = ROOT / "third_party" / "auto-belt-refill-mxl2012"
    patches = apply_patches(ours, src)
    write_ascii(src / "PINNED_COMMIT", pin)
    write_patches(patches, src / "PATCHES")
    b = a.out / "_cmake" / "beltrefill"
    cmake_configure(ours, b, log, f"-DABR_SRC={src / folder / 'src'}", f"-DABR_SDK={sdk_dir(a)}")
    cmake_build(b, log, "AutoBeltRefill", "BeltMatchTests")
    if not a.no_tests:
        wine(b / "BeltMatchTests.exe", log=log)
    rel = fresh(a.out / "beltrefill" / "Release")
    shutil.copy2(b / "d2rl-auto-belt-refill.dll", rel)
    return [rel / "d2rl-auto-belt-refill.dll"]


def build_controllerqol(a, log):
    paths = ["plugins/controller-qol", "plugins/inventory-deposit/src", "plugins/inventory-deposit/tests", "LICENSE"]
    pin = pinned("third_party/D2R-Mods")
    repo = find_repo(a, "D2R-Mods", pin, "MXL_CONTROLLERQOL_DIR", "third_party/D2R-Mods")
    src = a.out / "controllerqol-src"
    export(repo, pin, src, paths)
    patches = apply_patches(ROOT / "third_party" / "controller-qol-mxl2012", src)
    write_ascii(src / "PINNED_COMMIT", pin)
    write_patches(patches, src / "PATCHES")
    sdk = sdk_dir(a)
    shutil.copy2(sdk / "LICENSE", src / "PluginSDK-LICENSE")
    b = a.out / "_cmake" / "controllerqol"
    tests = "OFF" if a.no_tests else "ON"
    cmake_configure(src / "plugins" / "controller-qol", b, log, f"-DPLUGIN_SDK={sdk}", f"-DCONTROLLER_QOL_BUILD_TESTS={tests}")
    # the .ps1 sets CL=/utf-8 (code page 932 on the build PC); the same here
    extra = {"CL": "/utf-8"}
    run(["cmake", "--build", b, *(["--target", "controller-qol"] if a.no_tests else [])], log=log, extra_env=extra)
    if not a.no_tests:
        # Three tests check the plugin's memory guards against the real Windows memory APIs (QueryVirtualMemoryInformation,
        # QueryWorkingSetEx, page protections of the test process); wine 9 does not give Windows' answers, so they fail here
        # and pass on Windows. They are run, and their result reported, but do not stop the build.
        wine_only = "^(qol-guarded-local-read|qol-image-header-work|qol-current-page-query)$"
        run(["ctest", "--test-dir", b, "--output-on-failure", "-E", wine_only], log=log)
        r = subprocess.run(["ctest", "--test-dir", str(b), "--output-on-failure", "-R", wine_only], env=env(),
                           capture_output=True, text=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write(r.stdout + r.stderr)
        print(f"  controller-qol: the 3 Windows-memory-API tests under wine: {'passed' if r.returncode == 0 else 'failed (known, wine)'}")
    if a.skill_profile:
        defaults = src / "plugins" / "controller-qol" / "skill-defaults.toml"
        shutil.copyfile(a.skill_profile, defaults)
        os.utime(defaults)  # newer than the configure: CMake copies it again
        run(["cmake", "--build", b, "--target", "controller-qol"], log=log, extra_env=extra)
        write_ascii(src / "SKILL_PROFILE", sha256(a.skill_profile))
    rel = fresh(a.out / "controllerqol" / "Release")
    dll = next(b.rglob("Controller QOL Updates.dll"))
    shutil.copy2(dll, rel)
    return [rel / dll.name]


def build_ehb(a, log):
    repo = find_repo(a, "D2R-Over-the-Head-Health-Bars", EHB_PIN, "MXL_EHB_DIR", url=EHB_URL)
    work = fresh(a.out / "enemyhealthbars-work")
    share = work / "share.zip"
    share.write_bytes(subprocess.run(["git", "-C", str(repo), "show", f"{EHB_PIN}:{EHB_SHARE[0]}"],
                                     capture_output=True, check=True).stdout)
    if sha256(share) != EHB_SHARE[1]:
        raise SystemExit(f"enemy-health-bars: {EHB_SHARE[0]} sha256 differs")
    with zipfile.ZipFile(share) as z:
        z.extractall(work / "share")
    inner = work / "share" / EHB_SOURCE[0]
    if sha256(inner) != EHB_SOURCE[1]:
        raise SystemExit(f"enemy-health-bars: {EHB_SOURCE[0]} sha256 differs")
    out = fresh(a.out / "enemyhealthbars-src")
    with zipfile.ZipFile(inner) as z:
        z.extractall(out)
    tree = out / "EnemyHealthBars"
    patches = apply_patches(ROOT / "third_party" / "enemy-health-bars-mxl2012", tree, ["--ignore-whitespace"])
    write_patches(patches, tree / "PATCHES")
    write_ascii(tree / "SOURCE.txt",
                "Enemy Health Bars 0.2.6 by Graxy_TV, GPL-3.0-only (LICENSE), as built for D2R-XL 2012.",
                f"Upstream: {EHB_URL} commit {EHB_PIN}, {EHB_SHARE[0]} (sha256 {EHB_SHARE[1]}),",
                f"  inside it {EHB_SOURCE[0]} (sha256 {EHB_SOURCE[1]}).",
                "This tree is that source with the patches in mxl2012-patches/ applied (in name order; their sha256 in PATCHES).")
    outdir = fresh(a.out / "enemyhealthbars")
    b = a.out / "_cmake" / "enemyhealthbars"
    cmake_configure(tree, b, log)
    cmake_build(b, log, "EnemyHealthBars", "policy_tests")
    if not a.no_tests:
        wine(next(b.rglob("policy_tests.exe")), log=log)
    rel = outdir / "Release"
    rel.mkdir()
    shutil.copy2(next(b.rglob("d2rl-enemy-health-bars.dll")), rel)
    for f in ("LICENSE", "THIRD_PARTY.md", "enemy-health-bars.toml"):
        shutil.copy2(tree / f, outdir)
    shutil.copytree(work / "share" / "licenses", outdir / "licenses")
    stage = work / "source" / "EnemyHealthBars"
    shutil.copytree(tree, stage)
    (stage / "mxl2012-patches").mkdir()
    for p in patches:
        shutil.copy2(p, stage / "mxl2012-patches")
    with zipfile.ZipFile(outdir / "d2rl-enemy-health-bars-source.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(stage.rglob("*")):
            z.write(f, f.relative_to(stage.parent).as_posix())
    shutil.rmtree(work)
    return [rel / "d2rl-enemy-health-bars.dll", outdir / "d2rl-enemy-health-bars-source.zip"]


def build_fd(a, log):
    ours = ROOT / "third_party" / "floating-damage-mxl2012"
    paths = ["plugins/floating-damage", "common", "third_party/PluginSDK", "third_party/notices", "scripts", "LICENSE",
             "THIRD_PARTY_NOTICES.md"]
    pin = pinned("third_party/RuffnecKk-D2RLoader-Suite")
    repo = find_repo(a, "RuffnecKk-D2RLoader-Suite", pin, "MXL_FLOATINGDAMAGE_DIR", "third_party/RuffnecKk-D2RLoader-Suite")
    src = a.out / "floatingdamage-src"
    export(repo, pin, src, paths)
    patches = apply_patches(ours, src)
    for t in (ours / "tests").glob("*.cpp"):
        shutil.copy2(t, src / "plugins" / "floating-damage" / "tests")
    write_ascii(src / "PINNED_COMMIT", pin)
    write_patches(patches, src / "PATCHES")
    b = a.out / "_cmake" / "floatingdamage"
    testing = "OFF" if a.no_tests else "ON"
    cmake_configure(src / "plugins" / "floating-damage", b, log, f"-DFETCHCONTENT_BASE_DIR={a.out / 'floatingdamage-deps'}",
                    f"-DBUILD_TESTING={testing}", *no_powershell(a, "FLOATING_DAMAGE_POWERSHELL_EXECUTABLE"))
    targets = ["ruffneckk_floating_damage"] + ([] if a.no_tests else ["ruffneckk_floating_damage_tests",
                                                                       "floating_damage_mxl_tests"])
    cmake_build(b, log, *targets)
    config = src / "plugins" / "floating-damage" / "config" / "ruffneckk-floating-damage.toml"
    if not a.no_tests:
        wine(next(b.rglob("ruffneckk_floating_damage_tests.exe")), winpath(config), log=log)
        wine(next(b.rglob("floating_damage_mxl_tests.exe")), log=log)
    rel = fresh(a.out / "floatingdamage" / "Release")
    shutil.copy2(next(b.rglob("d2rl-ruffneckk-floating-damage.dll")), rel)
    shutil.copy2(config, rel)
    shutil.copy2(src / "LICENSE", rel / "LICENSE-floating-damage.txt")
    shutil.copy2(ours / "fonts" / "Cinzel-Bold.ttf", rel / "ruffneckk-floating-damage-font.ttf")
    shutil.copy2(ours / "fonts" / "OFL.txt", rel / "LICENSE-floating-damage-font.txt")
    return [rel / "d2rl-ruffneckk-floating-damage.dll"]


def build_vsr(a, log):
    pin = pinned("third_party/RuffnecKk-D2RLoader-Suite")
    repo = find_repo(a, "RuffnecKk-D2RLoader-Suite", pin, "MXL_FLOATINGDAMAGE_DIR", "third_party/RuffnecKk-D2RLoader-Suite")
    src = a.out / "vendorstockrefresh-src"
    export(repo, pin, src)
    write_ascii(src / "PINNED_COMMIT", pin)
    b = a.out / "_cmake" / "vendorstockrefresh"
    testing = "OFF" if a.no_tests else "ON"
    cmake_configure(src, b, log, f"-DFETCHCONTENT_BASE_DIR={a.out / 'vendorstockrefresh-deps'}", f"-DBUILD_TESTING={testing}",
                    *no_powershell(a, "RUFFNECKK_POWERSHELL_EXECUTABLE", "REMOTE_STASH_POWERSHELL",
                                   "FLOATING_DAMAGE_POWERSHELL_EXECUTABLE"))
    tests = ["ruffneckk_vendor_stock_refresh_tests", "ruffneckk_vendor_stock_refresh_panel_tests",
             "ruffneckk_vendor_stock_refresh_layout_tests"]
    cmake_build(b, log, "ruffneckk_vendor_stock_refresh", *([] if a.no_tests else tests))
    plugin = "plugins/vendor-stock-refresh"
    config = src / plugin / "config" / "ruffneckk-vendor-stock-refresh.toml"
    if not a.no_tests:
        for t in tests:
            exe = next(b.rglob(f"{t}.exe"))
            wine(exe, *([winpath(config)] if t == "ruffneckk_vendor_stock_refresh_tests" else []), log=log)
    rel = fresh(a.out / "vendorstockrefresh" / "Release")
    shutil.copy2(next(b.rglob("d2rl-ruffneckk-vendor-stock-refresh.dll")), rel)
    shutil.copy2(config, rel)
    shutil.copy2(src / "LICENSE", rel / "LICENSE-vendor-stock-refresh.txt")
    return [rel / "d2rl-ruffneckk-vendor-stock-refresh.dll"]


BUILDERS = {"legacy169": build_legacy169, "buffhud": build_buffhud, "beltrefill": build_beltrefill,
            "controllerqol": build_controllerqol, "ehb": build_ehb, "fd": build_fd, "vsr": build_vsr}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("plugins", nargs="*", metavar="PLUGIN", help=f"{' '.join(PLUGINS)} (default: all)")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--repos", type=Path, help="folder of clones (<name>.git or <name>) that have the pinned commits")
    ap.add_argument("--sdk", type=Path, help="PluginSDK source at the pinned commit (default: MXL2012_PLUGINSDK_DIR, the "
                                             "submodule, else exported from the PluginSDK repository)")
    ap.add_argument("--work", type=Path, help="checkout with a built work/ folder for Buff HUD's icon sheets (default: this one)")
    ap.add_argument("--skill-profile", type=Path, help="Controller QOL: the mxl2012 skill seed to embed")
    ap.add_argument("--no-tests", action="store_true")
    a = ap.parse_args(argv)
    a.out = a.out.resolve()
    unknown = [p for p in a.plugins if p not in PLUGINS]
    if unknown:
        ap.error(f"unknown plugin {', '.join(unknown)} (choose from {' '.join(PLUGINS)})")
    if not (MSVC / "bin" / "x64" / "cl").exists():
        raise SystemExit(f"no msvc-wine at {MSVC} (MXL_MSVC_WINE)")
    if shutil.which("cmake", path=str(PY_BIN)) is None and shutil.which("cmake") is None:
        raise SystemExit("cmake not found (run with the project venv's python)")
    a.out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MXL_TMP", str(a.out / "tmp"))
    os.environ["TMPDIR"] = os.environ["MXL_TMP"]
    Path(os.environ["MXL_TMP"]).mkdir(parents=True, exist_ok=True)
    (a.out / "logs").mkdir(exist_ok=True)
    failed = []
    for name in a.plugins or PLUGINS:
        print(f"== {name}", flush=True)
        log = a.out / "logs" / f"{name}.log"
        log.write_text("")
        try:
            for f in BUILDERS[name](a, log):
                print(f"  {f}  {f.stat().st_size} bytes  sha256 {sha256(f)}")
        except SystemExit as e:
            print(f"  {name}: {e}")
            failed.append(name)
    print("all built" if not failed else "FAILED: " + ", ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
