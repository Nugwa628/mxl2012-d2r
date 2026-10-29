"""Keeps temporary files inside the project (CLAUDE.md rule 1: nothing is written elsewhere on the PC).

Importing this module (`import projtemp  # noqa: F401`) points Python's `tempfile` at a project-local folder and sets TMPDIR /
TEMP / TMP for this process, so child processes (PowerShell, CMake, MSVC, 7-Zip, git) inherit it. Every unit-test module and
every tool that makes temp files imports it; tools/tests/test_projtemp.py fails when a test module does not, and asserts that
`tempfile.gettempdir()` is inside the repo during the tests. Nobody has to set TMP / TEMP by hand.

Where (first that applies):
  1. env MXL_TMP
  2. TMPDIR / TEMP / TMP when it already points inside this checkout or the runs folder (<runs> = mxl2012-runs, MXL2012_RUNS)
  3. <repo>/work/tmp (git-ignored; on CI the workspace)
The folder is created when missing. If it cannot be created, nothing changes (the system default stays).
"""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VARS = ("TMPDIR", "TEMP", "TMP")


def runs_dir() -> Path:
    import localconfig  # the runs folder beside the main checkout or two levels above a lane worktree
    return localconfig.runs_dir()


def inside(path, folder) -> bool:
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(folder))
        return True
    except ValueError:
        return False


def choose(env=None) -> Path:
    """The folder temp files go to (not created here)."""
    env = os.environ if env is None else env
    if env.get("MXL_TMP"):
        return Path(env["MXL_TMP"])
    for v in VARS:
        cur = env.get(v)
        if cur and (inside(cur, ROOT) or inside(cur, runs_dir())):
            return Path(cur)
    return ROOT / "work" / "tmp"


def apply() -> Path | None:
    target = choose()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    tempfile.tempdir = str(target)
    for v in VARS:
        os.environ[v] = str(target)
    return target


TMP = apply()
