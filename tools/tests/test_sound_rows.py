"""Sound guard row counts (plugin/src/sound_guard_logic.h ModSoundRows / ModSoundRowsBase) equal the built sounds.txt
(work/mod/data/global/excel and its base/ bank), and part spiritsound's constants (bug #502) match the built tables: the
*Index of ancient_death_hd and the monsters drawn with D2R's HD Ancients that are not the Ancients. Skipped when there is no
build (CI, a fresh checkout)."""
import csv
import json
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

    def test_ancient_death_hd(self):
        for path in (EXCEL / "sounds.txt", EXCEL / "base" / "sounds.txt"):
            if not path.is_file():
                self.skipTest("no built %s" % path.relative_to(ROOT))
            with open(path, encoding="latin-1", newline="") as f:
                rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
            index = rows[0].index("*Index")
            ids = {r[0]: r[index] for r in rows[1:] if r and r[0]}
            self.assertEqual(str(constant("AncientDeathHd")), ids.get("ancient_death_hd"), path.relative_to(ROOT))

    def test_spirit_classes(self):
        """Exactly the monsters SpiritFirst..SpiritLast are drawn with D2R's ancientbarb1-3 without being them (the quest
        NPCs quest_koth / quest_shaman share a unit too and keep the sound)."""
        hd = ROOT / "work" / "mod" / "data" / "hd" / "character" / "monsters.json"
        stats = EXCEL / "monstats.txt"
        if not hd.is_file() or not stats.is_file():
            self.skipTest("no built monsters.json / monstats.txt")
        units = json.loads(hd.read_text(encoding="utf-8-sig"))
        with open(stats, encoding="latin-1", newline="") as f:
            rows = [r for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)][1:]
        hcls = {r[0]: int(r[1]) for r in rows if r and r[0] and r[1].isdigit()}
        spirits = sorted(hcls[m] for m, u in units.items() if m in hcls and u in ("ancientbarb1", "ancientbarb2", "ancientbarb3")
                         and not m.startswith("ancientbarb") and not m.startswith("quest_"))
        self.assertEqual(list(range(constant("SpiritFirst"), constant("SpiritLast") + 1)), spirits)

    def test_above_d2r(self):
        self.assertLess(constant("D2RSoundRows"), min(constant("ModSoundRows"), constant("ModSoundRowsBase")))


if __name__ == "__main__":
    unittest.main()
