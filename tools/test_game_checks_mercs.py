"""The `mercs` game check's tables and parsing (lane mercs2); no game is started."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc


class MercCheckTables(unittest.TestCase):
    def test_every_hire_class_has_gear_rows(self):
        for _act, _area, _npc, name, cls in gc.MERC_HIRERS:
            rows = gc.MERC_GEAR[cls]
            weapons = [r for r in rows if r[1] == 4]
            self.assertTrue(any(r[2] for r in weapons), name + ": an allowed weapon")
            self.assertTrue(any(not r[2] for r in weapons), name + ": a refused weapon")
            self.assertTrue(all(r[1] in gc.MERC_SLOT for r in rows), name + ": every body location has a panel slot")

    def test_hirers_and_vendors_are_the_acts_towns(self):
        self.assertEqual([h[0] for h in gc.MERC_HIRERS], [1, 2, 3, 5])  # Act 4 has no hirer
        self.assertEqual(sorted(gc.TOWN_VENDORS), [1, 2, 3, 4, 5])
        towns = {h[0]: h[1] for h in gc.MERC_HIRERS}
        for act, v in gc.TOWN_VENDORS.items():
            if act in towns:
                self.assertEqual(v[0], towns[act])


class MercCheckParsing(unittest.TestCase):
    def test_item_lines(self):
        lines = ["merc id=7 class=271 level=3", "item id=12 code=164 class=5 page=255 x=0 y=0 quality=2 body=4", "merc items 1"]
        its = gc.item_lines(lines)
        self.assertEqual(len(its), 1)
        self.assertEqual((its[0]["id"], its[0]["code"], its[0]["page"], its[0]["body"]), (12, 164, 255, 4))

    def test_menu_lines(self):
        menu = ["menu npc id=3 class=150 row=2 lines=3 (+ Cancel)", "  line 0 string=0xf1 handler=image+0x1", "  line 2 string=0x2 handler=image+0x2"]
        self.assertEqual(gc.menu_lines(menu), [0, 2])
        self.assertEqual(gc.menu_lines(None), [])

    def test_menu_line_by_handler(self):
        halbu = ["menu npc id=35 class=257 row=22 lines=1 (+ Cancel)", "  line 0 string=0xd06 handler=image+0x112f30"]
        gheed = ["  line 0 string=0xd35 handler=image+0x112eb0", "  line 1 string=0xd44 handler=image+0x112f30",
                 "  line 2 string=0xd46 handler=image+0x112c80"]
        self.assertEqual(gc.menu_line_of(halbu, gc.MENU_TRADE), 0)
        self.assertEqual(gc.menu_line_of(gheed, gc.MENU_GAMBLE), 2)
        self.assertIsNone(gc.menu_line_of(halbu, gc.MENU_GAMBLE))

    def test_cells_are_fractions_of_the_client(self):
        for fx, fy in (gc.inv_cell(0, 0), gc.inv_cell(9, 5, 2, 3), gc.shop_cell(0, 0), gc.shop_cell(9, 9, 2, 4)):
            self.assertTrue(0 < fx < 1 and 0 < fy < 1)
        self.assertLess(gc.inv_cell(0, 0)[0], gc.inv_cell(1, 0)[0])


if __name__ == "__main__":
    unittest.main()
