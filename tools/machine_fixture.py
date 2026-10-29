"""A neutral machine.json for unit tests of the slot tools.

The slot tools refuse to run without the machine-local safety settings (localconfig.require_machine). A CI runner or
another PC has no machine.json, so a test that drives one of these tools writes its own: `use_neutral_machine(self)` in
setUp writes one with made-up folder names into a temp folder (work/tmp, tools/projtemp.py) and points MXL_MACHINE at it
for the test. The real machine.json is never read or changed.
"""
import json
import os
import shutil
import tempfile
from unittest import mock

import projtemp  # noqa: F401  (temp files stay inside the project)

NEUTRAL = {"_comment": "unit-test machine config (tools/machine_fixture.py)",
           "protected_mod_folders": ["OtherMod"], "protected_save_folders": ["OtherMod", "OtherMod-s*"]}


def use_neutral_machine(test, **extra) -> str:
    """Writes a neutral machine.json (shared_lock_dir in its own temp folder) and sets MXL_MACHINE to it until the test
    ends. Returns the file's path."""
    folder = tempfile.mkdtemp(prefix="machine-")
    test.addCleanup(shutil.rmtree, folder, True)
    path = os.path.join(folder, "machine.json")
    data = {**NEUTRAL, "shared_lock_dir": os.path.join(folder, "locks"), **extra}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    p = mock.patch.dict(os.environ, {"MXL_MACHINE": path})
    p.start()
    test.addCleanup(p.stop)
    return path
