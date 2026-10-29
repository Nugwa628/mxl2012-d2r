"""Parsers and verdict rules of the lane rulescheck checks in game_checks.py (no game is started)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class ParseItems(unittest.TestCase):
    def test_items_lines(self):
        lines = ["item id=12 code=ass class=548 page=0 x=3 y=1 quality=2 index=0 identified=1 ilvl=1 sockets=0 flags=0x10",
                 "items: 1", "h: items OK"]
        self.assertEqual(gc.parse_items(lines), [{"id": 12, "code": "ass", "class": 548, "page": 0, "x": 3, "y": 1, "quality": 2,
                                                   "index": 0, "identified": 1, "ilvl": 1, "sockets": 0, "flags": 0x10}])

    def test_codes_with_symbols_stay_text(self):
        it = gc.parse_items(["item id=7 code=8o^ class=900 page=3 x=0 y=0 quality=2 index=0 identified=1 ilvl=5 sockets=0 flags=0x0"])[0]
        self.assertEqual(it["code"], "8o^")
        self.assertEqual(it["page"], gc.RC_PAGE_CUBE)

    def test_numeric_codes_stay_text(self):  # Median's weapon codes `100`, `142`
        it = gc.parse_items(["item id=66 code=100 class=600 page=0 x=6 y=1 quality=2 index=0 identified=1 ilvl=1 sockets=1 flags=0x4082810"])[0]
        self.assertEqual(it["code"], "100")
        self.assertTrue(it["flags"] & gc.ITEM_FLAG_RUNEWORD)

    def test_ground_item_keeps_world_position(self):  # `item <code> ground`: page 255, x / y are world coordinates
        it = gc.parse_items(["item id=29 code=r01 class=1665 page=255 x=4368 y=5601 quality=2 index=0 identified=1 ilvl=1 sockets=0 flags=0x82010"])[0]
        self.assertEqual((it["page"], it["x"], it["y"]), (255, 4368, 5601))

    def test_other_lines_ignored(self):
        self.assertEqual(gc.parse_items(["item: unknown code", "items: 0"]), [])


class InventoryGrid(unittest.TestCase):
    def test_free_block_skips_taken_cells(self):
        items = [{"code": "box", "page": 0, "x": 0, "y": 0}, {"code": "zen", "page": 0, "x": 2, "y": 0}]
        with patch.object(gc, "item_size", side_effect=lambda c: {"box": (2, 2), "zen": (1, 2)}.get(c, (1, 1))):
            self.assertEqual(gc.free_inv_cell(items, 1, 1), (3, 0))
            self.assertEqual(gc.free_inv_cell(items, 2, 4), (3, 0))  # row by row: right of the statue

    def test_full_grid(self):
        items = [{"code": "x", "page": 0, "x": x, "y": y} for x in range(10) for y in range(6)]
        with patch.object(gc, "item_size", return_value=(1, 1)):
            self.assertIsNone(gc.free_inv_cell(items, 1, 1))

    def test_other_pages_do_not_take_cells(self):
        with patch.object(gc, "item_size", return_value=(10, 6)):
            self.assertEqual(gc.free_inv_cell([{"code": "box", "page": 3, "x": 0, "y": 0}], 1, 1), (0, 0))

    def test_cell_centres(self):
        self.assertEqual(gc.inv_px(0, 0), (1049 + 22, 393 + 21))
        self.assertEqual(gc.cube_px(9, 7), (121 + 9.5 * 44, 107 + 7.5 * 42))


class Verdicts(unittest.TestCase):
    def test_delay_rule_of_113c(self):
        self.assertTrue(gc.delay_verdict(True, False, True))   # refused inside the delay, works later
        self.assertFalse(gc.delay_verdict(True, True, True))   # D2R's independent cooldowns
        self.assertFalse(gc.delay_verdict(True, False, False))  # never works again: not the rule either
        self.assertIsNone(gc.delay_verdict(False, False, False))

    def test_charm_only_in_inventory(self):
        self.assertTrue(gc.charm_verdict(1, 0, 0))
        self.assertFalse(gc.charm_verdict(1, 1, 0))  # working from the cube is not 1.13c
        self.assertFalse(gc.charm_verdict(0, 0, 0))

    def test_shortcut_makes_partial(self):
        gc.RESULTS.clear()
        mark = {"loader": 0, "mxl": 0, "crashes": set()}
        with patch.object(gc, "engine_issues", return_value=([], [])), patch.object(gc.g, "log"):
            gc.rc_finish("x", True, "note", mark, [], [], ["travel by the harness"])
            gc.rc_finish("y", True, "note", mark, [], [], [])
            gc.rc_finish("z", False, "note", mark, [], [], ["travel by the harness"])
        self.assertEqual([r.status for r in gc.RESULTS], ["PARTIAL", "PASS", "FAIL"])
        self.assertIn("shortcut only", gc.RESULTS[0].note)
        self.assertIn("no shortcut", gc.RESULTS[1].note)
        gc.RESULTS.clear()

    def test_runeword_rounds(self):
        rounds = gc.runeword_rounds()
        self.assertEqual([r[4] for r in rounds], [True, True, False, False, True])
        for label, base, args, fillers, want in rounds:  # sockets asked = fillers given
            self.assertIn("194=%d" % len(fillers), args, label)

    def test_dark_ring_inputs(self):
        rings, (bkr, _row), (up, _up), sixth = gc.DARK_RING
        self.assertNotIn("o@o", rings + [sixth])  # bug #311: any sixth item that is not Ingredient Ring 3
        self.assertEqual(len(rings) + 2, 6)
        self.assertEqual((bkr, up), ("r@r", "s@s"))

    def test_checks_registered(self):
        names = [n for n, _ in gc.CHECKS]
        for n in ("rcbook", "rcdelay", "rctoken", "rclife", "rcscroll", "rchire", "rcdeath", "rclevels",
                  "rprunes", "rpdarkring", "rpcharm", "rpnames", "rpequip"):
            self.assertIn(n, names)
        self.assertEqual(gc.unknown_checks(names), [])


class Signets(unittest.TestCase):  # engine-triage #24
    def test_exact_gains_pass(self):
        self.assertTrue(gc.signet_verdict({"statpts": 1, "potion_stat_cap": 1}, {"statpts": 0, "potion_stat_cap": 0},
                                          {"statpts": 1, "potion_stat_cap": 1}))

    def test_missing_or_wrong_gain_fails(self):
        self.assertFalse(gc.signet_verdict({"gold": 150}, {"gold": 0}, {"gold": 0}))
        self.assertFalse(gc.signet_verdict({"newskills": 1}, {"newskills": None}, {"newskills": 2}))

    def test_every_stat_is_read_and_registered(self):
        self.assertIn("rpsignets", [n for n, _ in gc.CHECKS])
        for code, _what, gains in gc.RP_SIGNETS:
            for stat in gains:
                self.assertIn(stat, gc.RC_STATS, code)


if __name__ == "__main__":
    unittest.main()
