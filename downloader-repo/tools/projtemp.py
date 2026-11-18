"""Temp files of the tests stay inside the repository: <repo>/build/tmp (git-ignored), or $MXL_TMP.

The downloader repository's stand-in for the D2R-XL 2012 repository's tools/projtemp.py, which also knows that
repository's lane and runs folders (exported by its tools/downloader_repo.py).
"""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VARS = ("TMPDIR", "TEMP", "TMP")


def apply() -> Path | None:
    target = Path(os.environ.get("MXL_TMP") or ROOT / "build" / "tmp")
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    tempfile.tempdir = str(target)
    for v in VARS:
        os.environ[v] = str(target)
    return target


TMP = apply()
