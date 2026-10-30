"""Lane unporteda: the `ua_look` check (registration, stages) and the owner's missing-art rule in art_fix.py (no game is started)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import art_fix  # noqa: E402
import game_checks as gc  # noqa: E402


class UaLook(unittest.TestCase):
    def test_registered(self):
        self.assertIn("ua_look", [n for n, _ in gc.CHECKS])
        self.assertEqual(gc.unknown_checks(["ua_look"]), [])

    def test_stages(self):
        self.assertEqual(gc.ua_stages({}), list(gc.UA_STAGES))
        self.assertEqual(gc.ua_stages({"MXL_UA": "maps, ui"}), ["ui", "maps"])  # the check's own order
        self.assertEqual(gc.ua_stages({"MXL_UA": "nothing"}), [])

    def test_disabled_rows_not_spawned(self):
        # bugs.md #70: D2R's disabled helper rows assert on a spawn; they are judged statically, not spawned
        ids = {m for _, m, _ in gc.UA_MONSTERS}
        self.assertFalse(ids & {"chaoshorde1", "suckernest1", "familiar", "poisonorb", "firebeast", "iceglobe", "cougar"})

    def test_hornedgods_has_its_own_stage(self):
        # bugs.md #41: alone it dies at its first tick (a Trap-Poison ally needs an enemy), so it is not in the plain spawn list
        self.assertNotIn("hornedgods", {m for _, m, _ in gc.UA_MONSTERS})
        self.assertIn("horned", gc.UA_STAGES)

    def test_item_rolls(self):
        # group 401 rolls one of two rows per pattern (with the socket or without): both are Median's
        for code, _why, want in gc.UA_ITEMS:
            self.assertEqual(want.get("item_numsockets"), (0, 1), code)
            for name in want:
                self.assertIsNotNone(gc.stat_id(name), name)


class DrawNothing(unittest.TestCase):
    """Owner 2026-10-29: missing art draws nothing on rows no player or monster skill uses, a stand-in on rows a skill uses."""

    def resolve(self, table, name, row, have=()):
        with patch.object(art_fix, "art_exists", side_effect=lambda t, n: "d2r" if n.lower() in have else None):
            return art_fix.resolve(table, name, row)

    def test_unused_row_draws_nothing(self):
        self.assertEqual(self.resolve("missiles", "TeethExplodeYellow", "combatshotarrow", {"teethexplode"}), ("null", "draws nothing"))
        self.assertEqual(self.resolve("overlay", "gore20", "gorecarpet", {"bloodripple"}), ("null", "draws nothing"))

    def test_used_row_keeps_its_stand_in(self):
        self.assertEqual(self.resolve("missiles", "TeethExplodeYellow", "sunspear2", {"teethexplode"}), ("teethexplode", "redirected"))
        self.assertEqual(self.resolve("overlay", "Pentacle", "bloodwytch", {"blackpentacle"}), ("blackpentacle", "redirected"))

    def test_repairs_come_first(self):
        # a stray extension is Median's spelling of an existing file: not missing art, whatever the row
        self.assertEqual(self.resolve("overlay", "extra\\lifedrain.dcc", "rageongoing", {"extra\\lifedrain"}),
                         ("extra\\lifedrain", "repaired"))

    def test_lists_do_not_overlap(self):
        for table, rows in art_fix.DRAW_NOTHING.items():
            self.assertEqual(rows.keys(), {r.lower() for r in rows}, table)
        # every art a draw-nothing row named and no used row needs has no redirect left
        for gone in ("xxxxx", "cherub", "lazbloodmissile"):
            self.assertNotIn(gone, art_fix.REDIRECT["missiles"])
        for gone in ("dopplezonexplodeblue", "dopplezonexplodelilac", "ceilingchunkvanish01", "gore20"):
            self.assertNotIn(gone, art_fix.REDIRECT["overlay"])


if __name__ == "__main__":
    unittest.main()
