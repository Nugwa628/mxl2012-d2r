"""Per-checkout local settings, read by the tools: the git-ignored `.mxl-local.json` at the repo root.

`py -3 tools/lane_setup.py` writes it (docs/setup.md, "New worktree"). It is a flat JSON object of environment variable
names -> values (a key starting with `_` is a comment); only the names in ENV_KEYS are honoured. Importing this module
applies the file as *defaults*: a variable that is already set in the environment wins, so a one-off
`$env:MXL_D2R_EXTRACT = ...` still overrides it. Tools that read one of these variables import it first
(`import localconfig  # noqa: F401`), build.py passes the result on to every step it starts, and tools/build_plugin.ps1 reads
the same file for the PluginSDK folder.

  MXL_D2R_EXTRACT        D2R 93847's extraction (tools/casc_extract.py output: data/global/excel/{,base/}*.txt, filelist.txt)
  MXL_D2R_CACHE          the shared read-only cache of D2R files the extraction lacks (fxpaths.d2r_file)
  MXL_NATIVE_DIR         folder holding StormLib/Release/StormLib.dll and CascLib/Release/CascLib.dll (tools/native.py)
  MXL2012_PLUGINSDK_DIR  the D2RLoader PluginSDK source (tools/build_plugin.ps1)
  MXL2012_SRC            Median XL 2012's extracted data/global/excel (tools/build.py)
  MXL2012_RUNS           the runs folder (default: mxl2012-runs beside the main checkout / two levels above a lane worktree)
  MXL_MACHINE            the machine-local config (default: machine.json in the runs folder), see below

The machine-local config (`machine.json`, outside every checkout; tools/lane_setup.py reports it) holds what this machine
has and the repo must not spell out: another checkout read for reference data, the shared slot lock folder and the other
mod's folders the slot tools must never touch. Keys (all optional for the build, see `machine()`):

  reference_checkout     a read-only checkout the data tools read reference results from (extract/, work/, assets/,
                         third_party/); env MXL_REFERENCE overrides
  extract_dir            a read-only D2R 93847 extraction, tried after this checkout's extract/d2r/93847
  shared_lock_dir        the folder of the game slots' run locks (game.lock.N), shared with other tools on this machine
  protected_mod_folders  mod folder names inside a slot's mods folder that no tool may write (list)
  protected_save_folders save folder names (fnmatch patterns) inside Saved Games/.../mods that no tool may write (list)
  conflicting_plugins    D2RLoader plugin ids / DLL names that must not run beside ours (list)
  public_check_patterns  extra regexes tools/check_public.py refuses (list)
The slot tools refuse to run while a SLOT_SAFETY_KEYS key is missing (require_machine).
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / ".mxl-local.json"
ENV_KEYS = ("MXL_D2R_EXTRACT", "MXL_D2R_CACHE", "MXL_NATIVE_DIR", "MXL2012_PLUGINSDK_DIR", "MXL2012_SRC", "MXL2012_RUNS",
            "MXL_MACHINE")
SLOT_SAFETY_KEYS = ("shared_lock_dir", "protected_mod_folders", "protected_save_folders")
SETUP_HINT = "run `py -3 tools/lane_setup.py` in this worktree (docs/setup.md, \"New worktree\")"
# a D2R extraction is usable when both table banks of skills.txt are in it (txt_migrate merges into both)
D2R_PROBES = ("data/global/excel/skills.txt", "data/global/excel/base/skills.txt")


def load(path: Path | None = None) -> dict[str, str]:
    """The settings of the file (only ENV_KEYS, string values); {} when there is none. A damaged file is an error."""
    path = CONFIG if path is None else path
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8-sig"))
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON ({e}); delete it and {SETUP_HINT}")
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must hold a JSON object; delete it and {SETUP_HINT}")
    return {k: v for k, v in data.items() if k in ENV_KEYS and isinstance(v, str) and v}


def apply(env=None, path: Path | None = None) -> dict[str, str]:
    """Sets every setting the environment does not have yet; returns what was set."""
    env = os.environ if env is None else env
    done = {}
    for k, v in load(path).items():
        if not env.get(k):
            env[k] = v
            done[k] = v
    return done


def save(settings: dict[str, str], path: Path | None = None) -> None:
    path = CONFIG if path is None else path
    data = {"_comment": "written by tools/lane_setup.py; git-ignored; environment variables win over these (tools/localconfig.py)"}
    data.update({k: str(settings[k]) for k in ENV_KEYS if settings.get(k)})
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def default_runs_dir(root: Path | None = None) -> Path:
    """The runs folder next to the checkout: R/mxl2012-runs, where R is the folder holding the main checkout (R/MXL2012-D2R)
    or two levels above a lane worktree (R/mxl2012-wt/<lane>). The first that exists; else the lane form."""
    root = ROOT if root is None else Path(root)
    for base in (root.parent, root.parent.parent):
        if (base / "mxl2012-runs").is_dir():
            return base / "mxl2012-runs"
    return root.parent.parent / "mxl2012-runs"


def runs_dir() -> Path:
    """mxl2012-runs: scratch, extractions and the shared tool inputs (MXL2012_RUNS, else default_runs_dir())."""
    return Path(os.environ.get("MXL2012_RUNS") or default_runs_dir())


def machine_path() -> Path:
    """machine.json: MXL_MACHINE (environment or .mxl-local.json), else machine.json in the runs folder."""
    return Path(os.environ.get("MXL_MACHINE") or runs_dir() / "machine.json")


def machine(path: Path | None = None) -> dict:
    """The machine-local config ({} when there is none: a CI runner, another PC). A damaged file is an error."""
    path = machine_path() if path is None else Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8-sig"))
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON ({e})")
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must hold a JSON object")
    return {k: v for k, v in data.items() if not k.startswith("_")}


def require_machine(keys=SLOT_SAFETY_KEYS, tool: str = "tool") -> dict:
    """The machine config; exits with a clear message when one of `keys` is missing or empty (the slot tools: without
    the protected folders and the shared lock folder they could touch another mod's files or miss its locks)."""
    cfg = machine()
    missing = [k for k in keys if not cfg.get(k)]
    if missing:
        raise SystemExit(f"{tool}: refusing to run: {machine_path()} lacks {', '.join(missing)} (the machine-local safety "
                         "settings; see tools/localconfig.py). Nothing was touched.")
    return cfg


def machine_list(key: str) -> list[str]:
    """A list setting of the machine config ([] when unset)."""
    v = machine().get(key) or []
    return [str(x) for x in ([v] if isinstance(v, str) else v) if x]


def reference_dir() -> Path | None:
    """The read-only reference checkout (MXL_REFERENCE, else machine.json reference_checkout), None when not configured."""
    v = os.environ.get("MXL_REFERENCE") or machine().get("reference_checkout")
    return Path(v) if v else None


def shared_dir() -> Path:
    """What every worktree shares (built/fetched once by lane_setup.py): native/, d2r-cache/."""
    return runs_dir() / "shared"


def d2r_extract_ok(path: Path) -> list[str]:
    """The probe files an extraction at `path` lacks ([] = usable)."""
    return [p for p in D2R_PROBES if not (Path(path) / p).exists()]


def d2r_extract_candidates() -> list[Path]:
    """Where an extraction is looked for, in order: environment/config, this checkout, the machine config's extract_dir
    and reference checkout (read-only)."""
    out = []
    if os.environ.get("MXL_D2R_EXTRACT"):
        out.append(Path(os.environ["MXL_D2R_EXTRACT"]))
    out.append(ROOT / "extract" / "d2r" / "93847")
    if machine().get("extract_dir"):
        out.append(Path(machine()["extract_dir"]))
    if reference_dir() is not None:
        out.append(reference_dir() / "extract" / "d2r" / "93847")
    return out


def find_d2r_extract() -> Path | None:
    for c in d2r_extract_candidates():
        if not d2r_extract_ok(c):
            return c
    return None


def default_d2r_extract() -> Path:
    """D2R's extraction for a tool that reads the tables: MXL_D2R_EXTRACT (environment or config), else the first usable
    default, else this checkout's extract/d2r/93847 (which then fails in require_d2r_extract, never silently)."""
    if os.environ.get("MXL_D2R_EXTRACT"):
        return Path(os.environ["MXL_D2R_EXTRACT"])
    return find_d2r_extract() or ROOT / "extract" / "d2r" / "93847"


def require_d2r_extract(path: Path, tool: str = "tool") -> Path:
    """Exits (2) with a message when `path` is not a D2R extraction. A tool that runs without one used to skip every table and
    write an empty mod (txt_migrate), which looks like success."""
    missing = d2r_extract_ok(path)
    if missing:
        tried = "\n  ".join(str(c) for c in d2r_extract_candidates())
        raise SystemExit(f"{tool}: {path} is not a D2R extraction (missing {', '.join(missing)}).\n"
                         f"Looked in:\n  {tried}\nSet MXL_D2R_EXTRACT or {SETUP_HINT}")
    return Path(path)

def native_dll_candidates(name: str) -> list[Path]:
    """Where tools/native.py looks for <name>.dll (StormLib, CascLib): this checkout's build/, then the shared build."""
    shared = Path(os.environ["MXL_NATIVE_DIR"]) if os.environ.get("MXL_NATIVE_DIR") else shared_dir() / "native" / "build"
    return [ROOT / "build" / name / "Release" / f"{name}.dll", shared / name / "Release" / f"{name}.dll"]


def find_native_dll(name: str) -> Path:
    for p in native_dll_candidates(name):
        if p.exists():
            return p
    looked = "; ".join(str(p) for p in native_dll_candidates(name))
    raise FileNotFoundError(f"{name}.dll not found (looked in {looked}); {SETUP_HINT}")

apply()
