"""The v005 hireling table's third skill growth header is mislabeled."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import txt_migrate


class HirelingMigrationTests(unittest.TestCase):
    def test_third_skill_growth_is_mapped(self):
        migrator = txt_migrate.Migrator.__new__(txt_migrate.Migrator)
        source = ["Skill3", "Level3", "LvlPerLvl8", "Skill4"]
        target = ["Skill3", "Level3", "LvlPerLvl3", "Skill4"]
        columns = migrator.column_map("hireling", source, target)
        row = ["Merc Glacial Nova", "6", "8", "another skill"]
        self.assertEqual([row[source.index(columns[c])] for c in target], row)

    def test_hireling_skill_description_source(self):
        desc = {"Vanquish": "vanquish", "Glacial Nova": "glacialnova", "Tremor": "tremor", "Mon Gift of Inner Fire": "giftofinnerfire",
                "Merc Werebear": ""}
        src = txt_migrate.hireling_desc_source
        self.assertEqual(src("Female Vanquish", desc), "vanquish")
        self.assertEqual(src("Merc Glacial Nova", desc), "glacialnova")
        self.assertEqual(src("Mon Hireling Tremor", desc), "tremor")
        self.assertEqual(src("Mon Super Gift of Inner Fire", desc), "giftofinnerfire")
        self.assertEqual(src("Merc Werebear", desc), "attack")  # no Werebear row with a description
        self.assertEqual(src("Act 1 Exp Aura", desc), "attack")


if __name__ == "__main__":
    unittest.main()
