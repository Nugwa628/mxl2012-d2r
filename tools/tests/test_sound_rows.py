"""Sound guard row counts (plugin/src/sound_guard_logic.h ModSoundRows / ModSoundRowsBase) equal the built sounds.txt
(work/mod/data/global/excel and its base/ bank). Skipped when there is no build (CI, a fresh checkout)."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGIC = ROOT / "plugin" / "src" / "sound_guard_logic.h"
EXCEL = ROOT / "work" / "mod" / "data" / "global" / "excel"


def constant(name):
    m = re.search(r"\b%s = (\d+);" % name, LOGIC.read_text(encoding="utf-8"))
    if not m:
        raise AssertionError("%s not found in %s" % (name, LOGIC))
    return int(m.group(1))


def data_rows(path):
    """Rows after the header, blank lines left out (as the game's loaded count does)."""
    with open(path, encoding="latin-1") as f:
        lines = [ln.rstrip("\r\n") for ln in f]
    return sum(1 for ln in lines[1:] if ln.strip())


class SoundRowsTests(unittest.TestCase):
    def check(self, name, path):
        if not path.is_file():
            self.skipTest("no built %s" % path.relative_to(ROOT))
        self.assertEqual(constant(name), data_rows(path),
                         "%s differs from the built %s: update sound_guard_logic.h" % (name, path.relative_to(ROOT)))

    def test_expansion_bank(self):
        self.check("ModSoundRows", EXCEL / "sounds.txt")

    def test_base_bank(self):
        self.check("ModSoundRowsBase", EXCEL / "base" / "sounds.txt")

    def test_above_d2r(self):
        self.assertLess(constant("D2RSoundRows"), min(constant("ModSoundRows"), constant("ModSoundRowsBase")))


if __name__ == "__main__":
    unittest.main()
