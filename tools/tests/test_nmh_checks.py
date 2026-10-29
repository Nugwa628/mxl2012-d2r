"""Pure helpers of the Nightmare / Hell checks (lane nmhell, tools/nmh_checks.py); no game is started.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_nmh_checks.py" """
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc  # noqa: E402
import nmh_checks as nmh  # noqa: E402
import rc_setup  # noqa: E402

# Median XL 2012 rows (monstats andariel / fallen1, monlvl 61 and 120, levels 2)
ANDARIEL = {"Level": "15", "Level(N)": "61", "Level(H)": "120", "minHP": "2500", "maxHP": "2500", "MinHP(N)": "2000",
            "MaxHP(N)": "2000", "MinHP(H)": "1500", "MaxHP(H)": "1500"}
FALLEN = {"minHP": "40", "maxHP": "60", "MinHP(N)": "40", "MaxHP(N)": "60", "MinHP(H)": "170", "MaxHP(H)": "180"}
LVL61 = {"Level": "61", "L-HP": "6435", "L-HP(N)": "12881", "L-HP(H)": "50000"}
LVL120 = {"Level": "120", "L-HP": "24557", "L-HP(N)": "46750", "L-HP(H)": "50000"}
BLOOD_MOOR = {"Id": "2", "MonLvl": "1", "MonLvl(N)": "55", "MonLvl(H)": "120", "MonLvlEx": "1", "MonLvlEx(N)": "53", "MonLvlEx(H)": "120"}


class Tables(unittest.TestCase):
    def test_area_level_reads_the_expansion_columns(self):
        self.assertEqual([nmh.area_level(BLOOD_MOOR, d) for d in (0, 1, 2)], [1, 53, 120])

    def test_boss_level(self):
        self.assertEqual([nmh.boss_level(ANDARIEL, d) for d in (0, 1, 2)], [15, 61, 120])

    def test_life(self):
        self.assertEqual(nmh.life_range(ANDARIEL, LVL61, 1), (257620, 257620))
        self.assertEqual(nmh.life_range(ANDARIEL, LVL120, 2), (750000, 750000))
        self.assertEqual(nmh.life_range(FALLEN, LVL120, 2), (85000, 90000))

    def test_judge(self):
        s = [(19, 53, 100, (90, 110)), (19, 53, 200, (90, 110)), (19, 55, 300, (90, 110))]
        at, ok, other = nmh.judge_sample(s, 53)
        self.assertEqual((len(at), len(ok), len(other)), (2, 1, 1))


class Setup(unittest.TestCase):
    def test_points(self):
        self.assertEqual(nmh.spend_points(395, 30, 25), (30 + 197, 25 + 198))

    def test_ground(self):
        d = nmh.parse_ground(["ground id=5 code=rin mode=3 x=3 y=4 dist=2.0 flags=0x10", "ground items 1", "ground OK"])
        self.assertEqual(d, [{"id": 5, "code": "rin", "mode": 3, "x": 3, "y": 4, "dist": "2.0", "flags": "0x10"}])

    def test_unlock_edit(self):
        save = bytearray(0x400)
        save[0x100:0x104] = b"Woo!"
        out = nmh.unlock_edit("nightmare")(bytes(save))
        self.assertEqual(out[rc_setup.OFF_PROGRESSION], 5)
        self.assertEqual(rc_setup.get_quest(out, 0, 6), rc_setup.DONE)
        self.assertEqual(rc_setup.get_quest(out, 1, 6), 0)
        out2 = nmh.unlock_edit("hell")(out)
        self.assertEqual(out2[rc_setup.OFF_PROGRESSION], 10)
        self.assertEqual(rc_setup.get_quest(out2, 1, 40), rc_setup.DONE)
        self.assertEqual(rc_setup.get_quest(out2, 2, 40), 0)

    def test_checks_registered(self):
        names = {n for n, _f in gc.CHECKS}
        self.assertTrue({"nmhsetup", "nmhnm", "nmhhell"} <= names)

    def test_path_word(self):
        self.assertEqual(nmh.path_word({"click_dmg": 10, "cast_dmg": 5}), "player path (clicks)")
        self.assertEqual(nmh.path_word({"click_dmg": 0, "cast_dmg": 5}), "cast function (help)")


class HitLog(unittest.TestCase):
    """Lane nmhell2: the hit log's state parser and summary."""
    def test_parse_state_ids(self):
        lines = ["h: server state 21: bit=1 list=none", "h: server state 237: bit=1 list flags=00000000 state=237 end=0 stats(0)",
                 "h: server state 290: bit=0 list=none", "h: server states: 2 set (ids below 400)"]
        self.assertEqual(nmh.parse_state_ids(lines), {21, 237})

    def test_summary(self):
        rows = [{"clicked": True, "stunned": False, "pmodes": [18, 1], "bmodes": [1, 3], "dmg": 12000},
                {"clicked": True, "stunned": True, "pmodes": [1, 1], "bmodes": [1, 1], "dmg": 0},
                {"clicked": False, "stunned": False, "pmodes": [7], "bmodes": [6], "dmg": 0},
                {"clicked": True, "stunned": False, "pmodes": [18], "bmodes": [1], "dmg": 8000}]
        s = nmh.summarize_hits(rows)
        self.assertEqual((s["clicks"], s["clicked"], s["stunned"], s["swung"], s["blocked"], s["gethit"]), (4, 3, 1, 3, 1, 1))
        self.assertEqual((s["hits"], s["total"], s["per_hit"], s["per_click"]), (2, 20000, 10000, 5000))
        self.assertIn("2 did damage", nmh.summary_text(s))

    def test_empty_summary(self):
        s = nmh.summarize_hits([])
        self.assertEqual((s["per_hit"], s["per_click"]), (0, 0))

    def test_new_checks_registered(self):
        names = {n for n, _f in gc.CHECKS}
        self.assertTrue({"nmhhitlog", "nmhdialog", "nmhkill"} <= names)

    def test_drink_due(self):
        self.assertTrue(nmh.drink_due(40, 100, 1))
        self.assertFalse(nmh.drink_due(50, 100, 1))
        self.assertFalse(nmh.drink_due(10, 100, 0))
        self.assertFalse(nmh.drink_due(0, 0, 3))

    def test_kill_stages_parse(self):
        self.assertEqual([s.split(":") for s in nmh.KILL_STAGES.split(",")][0], ["nightmare", "andariel"])

    def test_kill_targets(self):
        self.assertEqual(nmh.kill_targets("hell:mephisto, nightmare:travel34,"), [("hell", "mephisto"), ("nightmare", "travel34")])
        with self.assertRaises(ValueError):
            nmh.kill_targets("inferno:baal")

    def test_every_kill_boss_has_a_town(self):
        self.assertEqual(set(nmh.ACT_TOWN), set(gc.ACT_BOSSES))

    def test_split_drops(self):
        rows = nmh.parse_ground(["ground id=5 code=gld mode=3 x=1 y=2 dist=4.0 flags=0x0",
                                 "ground id=6 code=rin mode=3 x=1 y=2 dist=12.5 flags=0x0",
                                 "ground id=7 code=amu mode=3 x=1 y=2 dist=45.0 flags=0x0"])
        gold, items = nmh.split_drops(rows)
        self.assertEqual(([d["id"] for d in gold], [d["id"] for d in items]), ([5], [6]))

    def test_with_kill_gear_stands_in_without_recursion(self):
        calls = []
        fake = type("G", (), {})()
        fake.acts_gear = lambda lvl: calls.append(("acts", lvl)) or 7
        real_kill_gear = nmh.kill_gear
        nmh.kill_gear = lambda g, level, diff, log: g.acts_gear(level)  # as gear() does
        try:
            got = nmh.with_kill_gear(fake, 120, 1, [], lambda: fake.acts_gear(85))
        finally:
            nmh.kill_gear = real_kill_gear
        self.assertEqual((got, calls), (7, [("acts", 120)]))
        self.assertEqual(fake.acts_gear(1), 7)  # the original is back

    def test_mode_text_and_merge(self):
        self.assertEqual(nmh.mode_text({18: 5, 7: 1, None: 1}), "18:5 7:1 None:1")
        self.assertEqual(nmh.mode_text({}), "none")
        c = nmh.merge_counts({"click": 2, "modes": {18: 1}}, {"click": 3, "cast": 1, "modes": {18: 2, 7: 1}})
        self.assertEqual((c["click"], c["cast"], c["modes"]), (5, 1, {18: 3, 7: 1}))
        self.assertEqual(nmh.merge_counts({"click": 1}, {"modes": {18: 2}})["modes"], {18: 2})  # first fight without a swing


if __name__ == "__main__":
    unittest.main()
