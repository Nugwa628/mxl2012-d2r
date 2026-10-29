"""The player-path item plan of game_checks (lane realpath): which representative items rp_items drops, picks up and wears; no game
is started."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc

ITYPES = [
    {"Code": "weap", "Equiv1": "", "Equiv2": "", "Body": "", "BodyLoc1": "", "Class": ""},
    {"Code": "mele", "Equiv1": "weap", "Equiv2": "", "Body": "1", "BodyLoc1": "rarm", "Class": ""},
    {"Code": "axe", "Equiv1": "mele", "Equiv2": "", "Body": "", "BodyLoc1": "", "Class": ""},
    {"Code": "helm", "Equiv1": "", "Equiv2": "", "Body": "1", "BodyLoc1": "head", "Class": ""},
    {"Code": "circ", "Equiv1": "helm", "Equiv2": "", "Body": "", "BodyLoc1": "", "Class": ""},
    {"Code": "barb", "Equiv1": "", "Equiv2": "", "Body": "", "BodyLoc1": "", "Class": "bar"},
    {"Code": "phlm", "Equiv1": "helm", "Equiv2": "barb", "Body": "", "BodyLoc1": "", "Class": ""},
    {"Code": "rune", "Equiv1": "", "Equiv2": "", "Body": "", "BodyLoc1": "", "Class": ""},
]
BASES = [
    {"code": "hax", "type": "axe", "type2": "", "spawnable": "1", "levelreq": "3"},
    {"code": "axe", "type": "axe", "type2": "", "spawnable": "1", "levelreq": "1"},
    {"code": "ci0", "type": "circ", "type2": "", "spawnable": "0", "levelreq": "1"},
    {"code": "ci1", "type": "circ", "type2": "", "spawnable": "1", "levelreq": "20"},
    {"code": "ba1", "type": "phlm", "type2": "", "spawnable": "1", "levelreq": "5"},
    {"code": "r01", "type": "rune", "type2": "", "spawnable": "1", "level": "1"},
    {"code": "cm3", "type": "rune", "type2": "", "spawnable": "1", "level": "9", "invwidth": "0", "invheight": "0"},
]
HD = [{"hax": {"asset": "axe/hand_axe"}}, {"axe": {"asset": "axe/axe"}}, {"ci0": {"asset": "helm/circlet"}}, {"ci1": {"asset": "helm/circlet"}},
      {"zzz": {"asset": "nothing/here"}}]
UNIQ = [{"index": "Bladebone", "code": "hax", "disabled": ""}, {"index": "Second axe", "code": "axe", "disabled": ""},
        {"index": "Off", "code": "ci1", "disabled": "1"}, {"index": "Crown of Ages", "code": "ci1", "disabled": ""}]
SETS = [{"index": "Arctic Horn", "item": "ba1"}]


class ItemPlan(unittest.TestCase):
    def setUp(self):
        self.plan, self.abstract = gc.rp_item_plan(ITYPES, BASES, UNIQ, SETS, HD)
        self.by = {(p["code"], p["args"]): p for p in self.plan}

    def test_one_base_per_type_spawnable_and_lowest_level_first(self):
        types = [p["why"] for p in self.plan if p["why"].startswith("itemtypes")]
        self.assertEqual(types, ["itemtypes axe", "itemtypes circ", "itemtypes phlm", "itemtypes rune"])
        self.assertIn(("axe", "axe"), self.by)  # level 1 before the level 3 hand axe
        self.assertIn(("ci1", "ci1"), self.by)  # the spawnable circlet before the unspawnable one

    def test_abstract_types_have_no_base(self):
        self.assertEqual(sorted(self.abstract), ["barb", "helm", "mele", "weap"])

    def test_hd_assets_not_covered_get_their_own_item(self):
        hd = [p["code"] for p in self.plan if p["why"].startswith("hd asset")]
        self.assertEqual(hd, ["hax"])  # axe/hand_axe; helm/circlet is covered by ci1, codes without a base are skipped

    def test_one_unique_and_set_row_per_base_type(self):
        uniq = [p["args"] for p in self.plan if " unique " in p["args"]]
        self.assertEqual(uniq, ["hax unique 0", "ci1 unique 3"])  # one per type (axe, circ), the disabled row skipped
        self.assertEqual([p["args"] for p in self.plan if " set " in p["args"]], ["ba1 set 0"])

    def test_body_location_and_class_follow_the_type_chain(self):
        self.assertEqual((self.by[("axe", "axe")]["loc"], self.by[("axe", "axe")]["cls"]), ("rarm", ""))
        self.assertEqual((self.by[("ci1", "ci1")]["loc"], self.by[("ci1", "ci1")]["cls"]), ("head", ""))
        self.assertEqual((self.by[("ba1", "ba1")]["loc"], self.by[("ba1", "ba1")]["cls"]), ("head", "barbarian"))
        self.assertEqual(self.by[("r01", "r01")]["loc"], "")

    def test_zero_size_items_are_marked(self):
        """Median's cm1-cm3 have no inventory cells; picked up from the ground the game crashes (bug #393): rp_items skips them."""
        self.assertFalse(self.by[("r01", "r01")]["noinv"])
        cm3 = [p for p in gc.rp_item_plan(ITYPES, [b for b in BASES if b["code"] == "cm3"], [], [], [])[0]]
        self.assertTrue(cm3 and cm3[0]["noinv"])

    def test_little_endian_packet_fields(self):
        self.assertEqual(gc._le(0x19, 1), "19 00 00 00 01 00 00 00")


class PlayerPathRules(unittest.TestCase):
    def test_checks_are_registered(self):
        names = [n for n, _ in gc.CHECKS]
        for n in ("rp_items", "rp_vendors", "rp_death", "rp_areas", "rp_persist", "rp_use"):
            self.assertIn(n, names)

    def test_no_shortcuts_in_player_path_code(self):
        """The player-path checks never use god mode, Tank, a life stat or `item ... inv` (lane realpath, owner 2026-10-28)."""
        import inspect
        for name, fn in gc.CHECKS:
            if not name.startswith("rp_"):
                continue
            src = inspect.getsource(fn)
            for helper in ("rp_item_round", "rp_fight", "rp_vendor_round", "rp_ready", "rp_be", "rp_pickup", "rp_ground_item"):
                src += inspect.getsource(getattr(gc, helper))
            for pat in (r"Tank\(", r"god 1", r"stat player [67]\b", r"setstat\(\"player\", [67]\b", r"\"item [^\"]*\binv\b",
                        r"\"kill (nearest|%)", r"\"spawn "):
                m = re.search(pat, src)
                self.assertIsNone(m, "%s uses a shortcut: %s" % (name, m.group(0) if m else ""))


if __name__ == "__main__":
    unittest.main()
