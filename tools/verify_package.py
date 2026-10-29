"""Check a player package (tools/package_release.py's .7z) the way a player gets it: unpacked, next to what install_mod.py installs.

  py -3 tools/verify_package.py <dist>/D2R-XL-2012-<v>.7z [--scratch DIR] [--no-reference] [--keep]

The 7z, release-manifest.json and SHA256SUMS are read from the 7z's folder. Into DIR (default <MXL2012_RUNS>/verify-package;
it must be inside the project root R or the repo, and only its own unpacked/ and reference/ are ever replaced) it:

1. lists the 7z (every path under mxl2012/, no absolute or `..` path) and unpacks it into unpacked/, as a player unpacks it into
   <D2R>\\mods\\;
2. checks the unpacked mxl2012/ against the manifest (the same paths, sizes and sha256, no extra file, emptyDirs, archive size and
   sha256, SHA256SUMS) and as a mod folder: modinfo.json (both copies) {"name": "mxl2012", "savepath": "mxl2012/"},
   d2rloader/metadata.json (namespace, modVersion = the release), d2rloader.toml (extended saves), the release plugin (no test
   harness, the PluginVersion), d2rloader/patches/, dataversionbuild.txt, the Median string files, no test or player file;
3. (unless --no-reference) writes what tools/install_mod.py installs (install_mod.build_data + write_mod_files, save folder
   mxl2012/, as on a player's PC) into reference/ and compares: every file must be the same bytes, except
   d2rloader/plugins/mxl2012-core.dll (the release DLL against the dev DLL) and d2rloader/metadata.json (modVersion,
   description, website); a reference file the package lacks must be a byte copy of D2R's own (the D2R baseline or the shared
   D2R cache, package_release.baselines()); the package has no file the reference lacks.

unpacked/ and reference/ are deleted at the end unless --keep (or a check failed). Exit 0 = the package installs the same game
as install_mod.py. Reads the build (work/mod/data) and the baselines; writes only into DIR.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import install_mod  # noqa: E402
import localconfig  # noqa: E402
import package_release as pr  # noqa: E402

NAME = pr.NAME
DIFFERS_BY_DESIGN = {"d2rloader/plugins/mxl2012-core.dll", "d2rloader/metadata.json"}
STRING_FILES = ("strings/%s/median.json", "strings/%s/overrides.json", "strings-legacy/%s/median.json")


def allowed_scratch(path: Path) -> bool:
    """DIR must sit inside the project root (two levels above a lane worktree) or this checkout."""
    p = path.resolve()
    root = install_mod.ROOT.resolve()
    if p == root or p in root.parents:  # never the checkout itself or a folder holding it
        return False
    for base in (localconfig.runs_dir().resolve().parent, install_mod.ROOT.resolve()):
        if p != base and base in p.parents:
            return True
    return False


def archive_paths(exe: str, archive: Path) -> list:
    """The entries of the 7z (`7z l -slt`), with / separators."""
    r = subprocess.run([exe, "l", "-slt", str(archive)], capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"7-Zip cannot list {archive}: {(r.stdout + r.stderr).strip()[-400:]}")
    paths = [ln[7:].replace("\\", "/") for ln in r.stdout.splitlines() if ln.startswith("Path = ")]
    return [p for p in paths if p != str(archive).replace("\\", "/")]


def bad_archive_paths(paths: list) -> list:
    return [p for p in paths if p.startswith("/") or ":" in p or ".." in p.split("/")
            or not (p == NAME or p.startswith(NAME + "/"))]


def check_mod_folder(mod: Path, version: str) -> list:
    """Problems of an unpacked mod folder as a player install."""
    problems = []
    want = {"name": NAME, "savepath": f"{NAME}/"}
    for rel in (f"{NAME}.mpq/modinfo.json", "modinfo.json"):
        f = mod / rel
        if not f.is_file():
            problems.append(f"{rel} is missing")
        elif json.loads(f.read_text("utf-8")) != want:
            problems.append(f"{rel} is {f.read_text('utf-8').strip()!r}, not {want}")
    meta = mod / "d2rloader" / "metadata.json"
    if meta.is_file():
        m = json.loads(meta.read_text("utf-8"))
        if m.get("namespace") != install_mod.NAMESPACE:
            problems.append(f"metadata.json namespace {m.get('namespace')!r}")
        if m.get("metadata", {}).get("modVersion") != version:
            problems.append(f"metadata.json modVersion {m.get('metadata', {}).get('modVersion')!r}, not {version}")
    else:
        problems.append("d2rloader/metadata.json is missing")
    toml = mod / "d2rloader" / "config" / "d2rloader.toml"
    if not toml.is_file() or 'mode = "extended"' not in toml.read_text("utf-8"):
        problems.append("d2rloader/config/d2rloader.toml lacks [d2rcore.save_format] mode = \"extended\"")
    dll = mod / "d2rloader" / "plugins" / "mxl2012-core.dll"
    if dll.is_file():
        problems += pr.check_release_plugin(dll, pr.plugin_version())
    else:
        problems.append("d2rloader/plugins/mxl2012-core.dll is missing")
    if not (mod / "d2rloader" / "patches").is_dir():
        problems.append("d2rloader/patches/ is missing")
    data = mod / f"{NAME}.mpq" / "data"
    dvb = data / "global" / "dataversionbuild.txt"
    if not dvb.is_file() or dvb.read_text("ascii").strip() != install_mod.D2R_BUILD:
        problems.append(f"global/dataversionbuild.txt is not {install_mod.D2R_BUILD}")
    if not (data / "global" / "excel").is_dir():
        problems.append("no global/excel tables")
    for rel in STRING_FILES:
        if not (data / "local" / "lng" / (rel % install_mod.NAMESPACE)).is_file():
            problems.append(f"local/lng/{rel % install_mod.NAMESPACE} is missing")
    bad = pr.forbidden_files(mod)
    if bad:
        problems.append("test or player files: " + ", ".join(bad[:20]))
    return problems


def check_manifest(mod: Path, man: dict, archive: Path, sums: Path) -> list:
    problems = []
    files = pr.file_list(mod)
    listed = {f["path"]: f for f in man.get("files", [])}
    have = {f["path"]: f for f in files}
    for p in sorted(set(listed) - set(have)):
        problems.append(f"manifest lists {p}, the 7z lacks it")
    for p in sorted(set(have) - set(listed)):
        problems.append(f"the 7z has {p}, the manifest does not list it")
    for p in sorted(set(have) & set(listed)):
        if (have[p]["size"], have[p]["sha256"]) != (listed[p]["size"], listed[p]["sha256"]):
            problems.append(f"{p}: size/sha256 differ from the manifest")
    if man.get("fileCount") != len(files) or man.get("totalSize") != sum(f["size"] for f in files):
        problems.append("manifest fileCount / totalSize do not match the 7z")
    if sorted(man.get("emptyDirs", [])) != pr.empty_dirs(mod):
        problems.append(f"emptyDirs {man.get('emptyDirs')} != {pr.empty_dirs(mod)}")
    arc = man.get("archive", {})
    if (arc.get("name"), arc.get("size"), arc.get("sha256")) != (archive.name, archive.stat().st_size, pr.sha256(archive)):
        problems.append("manifest archive entry does not match the 7z")
    if man.get("complete") is not True:
        problems.append("manifest says complete=false (a --no-data package): not for players")
    if man.get("saveFolder") != f"{NAME}/" or man.get("modFolder") != NAME:
        problems.append("manifest modFolder / saveFolder")
    if sums.is_file():
        for line in sums.read_text("utf-8").splitlines():
            digest, _, name = line.partition("  ")
            f = sums.parent / name
            if not f.is_file() or pr.sha256(f) != digest:
                problems.append(f"SHA256SUMS: {name} does not match")
    else:
        problems.append("SHA256SUMS is missing")
    return problems


def same_bytes(a: Path, b: Path) -> bool:
    if a.stat().st_size != b.stat().st_size:
        return False
    with open(a, "rb") as fa, open(b, "rb") as fb:
        while True:
            x, y = fa.read(1 << 20), fb.read(1 << 20)
            if x != y:
                return False
            if not x:
                return True


def write_reference(ref: Path, game: Path) -> None:
    """What install_mod.py writes into <D2R>\\mods\\mxl2012 on a player's PC (save folder mxl2012/, the dev plugin)."""
    install_mod.build_data(ref / f"{NAME}.mpq" / "data", game)
    install_mod.write_mod_files(ref, NAME, f"{NAME}/")


def compare_reference(mod: Path, ref: Path, extract: Path = pr.EXTRACT, cache: Path = None) -> tuple:
    """-> (problems, stats) of the package's mod folder against install_mod's."""
    pkg = {p.relative_to(mod).as_posix() for p in mod.rglob("*") if p.is_file()}
    rf = {p.relative_to(ref).as_posix() for p in ref.rglob("*") if p.is_file()}
    roots = pr.baselines(extract, cache)
    problems, blizzard = [], 0
    for rel in sorted(pkg - rf):
        problems.append(f"the package has {rel}, install_mod.py does not install it")
    data = f"{NAME}.mpq/data/"
    for rel in sorted(rf - pkg):
        twins = [Path(b) / "data" / rel[len(data):] for b in roots] if rel.startswith(data) else []
        if any(t.is_file() and same_bytes(t, ref / rel) for t in twins):
            blizzard += 1
        else:
            problems.append(f"install_mod.py installs {rel}, the package lacks it (and it is no copy of D2R's own file)")
    differ = 0
    for rel in sorted(pkg & rf):
        if rel in DIFFERS_BY_DESIGN:
            continue
        if not same_bytes(mod / rel, ref / rel):
            differ += 1
            if differ <= 20:
                problems.append(f"{rel} differs from install_mod.py's")
    if differ > 20:
        problems.append(f"... {differ} files differ in all")
    return problems, {"common": len(pkg & rf), "blizzardCopiesLeftOut": blizzard, "differByDesign": sorted(DIFFERS_BY_DESIGN & pkg)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archive", type=Path)
    ap.add_argument("--scratch", type=Path, default=localconfig.runs_dir() / "verify-package")
    ap.add_argument("--no-reference", action="store_true", help="skip the comparison with install_mod.py's folder")
    ap.add_argument("--game", type=Path, default=Path(install_mod.DEFAULT_GAME or "."),
                    help="D2R folder read for maps_hd (only when work/mod/data has no global/tiles)")
    ap.add_argument("--keep", action="store_true", help="keep unpacked/ and reference/")
    a = ap.parse_args()

    archive = a.archive.resolve()
    if not archive.is_file():
        print(f"no package at {archive}")
        return 1
    if not allowed_scratch(a.scratch):
        print(f"--scratch {a.scratch} is not inside the project (R or this checkout)")
        return 1
    exe = pr.find_7z()
    if not exe:
        print(f"error: {pr.NO_7Z}")
        return 1
    man_path = archive.parent / "release-manifest.json"
    if not man_path.is_file():
        print(f"no release-manifest.json next to {archive.name}")
        return 1
    man = json.loads(man_path.read_text("utf-8"))
    version = man.get("version", "")

    problems = []
    paths = archive_paths(exe, archive)
    bad = bad_archive_paths(paths)
    if bad:
        print("the 7z has entries outside mxl2012/ (not unpacked): " + ", ".join(bad[:10]))
        return 1
    unpacked, ref = a.scratch / "unpacked", a.scratch / "reference"
    for d in (unpacked, ref):
        if d.exists():
            shutil.rmtree(d)
    unpacked.mkdir(parents=True)
    r = subprocess.run([exe, "x", "-y", "-bd", f"-o{unpacked}", str(archive)], capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        print(f"7-Zip failed to unpack: {(r.stdout + r.stderr).strip()[-400:]}")
        return 1
    top = sorted(p.name for p in unpacked.iterdir())
    if top != [NAME]:
        problems.append(f"top level of the 7z is {top}, not ['{NAME}']")
    mod = unpacked / NAME
    problems += check_mod_folder(mod, version)
    problems += check_manifest(mod, man, archive, archive.parent / "SHA256SUMS")
    files = pr.file_list(mod)
    stats = {"archive": archive.name, "archiveSize": archive.stat().st_size, "archiveSha256": pr.sha256(archive),
             "version": version, "files": len(files), "unpackedSize": sum(f["size"] for f in files)}
    if not a.no_reference:
        if not (install_mod.SRC / "global" / "excel").exists():
            problems.append("work/mod/data is missing: no reference to compare with (run tools/build.py, or --no-reference)")
        else:
            write_reference(ref, a.game)
            p, s = compare_reference(mod, ref)
            problems += p
            stats["reference"] = s

    (a.scratch / "verify-report.json").write_text(json.dumps({**stats, "problems": problems}, indent=1) + "\n", "utf-8")
    if problems:
        print(f"FAIL: {len(problems)} problems (kept {a.scratch} for a look):")
        print("\n".join("  " + p for p in problems[:60]))
        return 1
    if not a.keep:
        for d in (unpacked, ref):
            shutil.rmtree(d, ignore_errors=True)
    ref_note = (f"; same as install_mod.py's folder ({stats['reference']['common']} files, "
                f"{stats['reference']['blizzardCopiesLeftOut']} D2R files left out, plugin + metadata differ by design)"
                if "reference" in stats else "")
    print(f"OK {archive.name}: {stats['files']} files, {stats['unpackedSize'] / 1e6:.0f} MB unpacked, "
          f"{stats['archiveSize'] / 1e6:.0f} MB, sha256 {stats['archiveSha256']}{ref_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
