"""tools/cube_rules_check.py on synthetic data: the 1.13c cubemain.bin decoder and the bin / port / D2R comparisons.

Run: py -3 -I -m unittest discover -s tools/tests -p "test_cube_rules_check.py"
"""
import struct
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import cube_rules_check as crc  # noqa: E402

TABLES = {
    "weapons": [{"code": "axe", "name": "Axe"}, {"code": "msf", "name": "Staff of Kings"}],
    "armor": [{"code": "cap", "name": "Cap"}],
    "misc": [{"code": "r01", "name": "El"}, {"code": "key", "name": "Key"}, {"code": "", "name": "Expansion"},
             {"code": "toa", "name": "Token"}],
    "itemtypes": [{"Code": "weap", "ItemType": "Weapon"}, {"Code": "", "ItemType": "Expansion"}, {"Code": "rune", "ItemType": "Rune"},
                  {"Code": "key", "ItemType": "Key"}],
    "properties": [{"code": "str"}, {"code": "Expansion"}, {"code": "sock"}],
    "uniqueitems": [{"index": "Axe of Test", "code": "axe"}],
    "setitems": [],
}


def record(**f):
    """A 0x148-byte 1.13c cubemain record from fields (inputs: list of (flags, item, uniq, quality, qty); outputs: list of dicts)."""
    r = bytearray(crc.RECORD)
    r[0], r[2], r[3], r[4] = f.get("enabled", 1), f.get("min diff", 0), f.get("class", 0xFF), f.get("op", 0)
    struct.pack_into("<iiBxH", r, 8, f.get("param", 0), f.get("value", 0), f.get("numinputs", 0), f.get("version", 0))
    for k, inp in enumerate(f.get("inputs", [])):
        struct.pack_into("<HHHBB", r, 0x14 + 8 * k, *inp)
    for s in range(crc.OUTPUTS):
        base = 0x4C + 0x54 * s
        o = (f.get("outputs") or [])[s] if s < len(f.get("outputs") or []) else None
        mods = (o or {}).get("mods", [])
        for m in range(crc.MODS):
            if m < len(mods):
                struct.pack_into("<IHhhB", r, base + 0x18 + 12 * m, *mods[m])
            else:
                struct.pack_into("<I", r, base + 0x18 + 12 * m, 0xFFFFFFFF)
        if o:
            struct.pack_into("<HHHBBBBBB", r, base, o.get("flags", 0), o.get("item", 0), o.get("uniq", 0), o.get("quality", 0),
                             o.get("qty", 0), o["type"], o.get("lvl", 0), o.get("plvl", 0), o.get("ilvl", 0))
    return bytes(r)


def table_bin(*records):
    return struct.pack("<I", len(records)) + b"".join(records)


class Decoder(unittest.TestCase):
    def test_fields(self):
        data = table_bin(record(op=28, numinputs=2, inputs=[(1, 1, 0, 0, 0), (2, 1, 0, 0, 2)],
                                outputs=[{"type": 0xFC, "item": 5, "lvl": 99, "mods": [(0, 7, 2, 3, 50)]}]))
        rec = crc.decode_bin(data)[0]
        self.assertEqual((rec["op"], rec["numinputs"], rec["class"]), (28, 2, 0xFF))
        self.assertEqual(rec["inputs"][1], {"flags": 2, "item": 1, "uniq": 0, "quality": 0, "qty": 2})
        self.assertIsNone(rec["inputs"][2])
        self.assertEqual(rec["outputs"][0]["mods"][0], {"prop": 0, "param": 7, "min": 2, "max": 3, "chance": 50})
        self.assertIsNone(rec["outputs"][0]["mods"][1])
        self.assertEqual((rec["outputs"][0]["type"], rec["outputs"][0]["lvl"]), (0xFC, 99))

    def test_size_check(self):
        with self.assertRaises(ValueError):
            crc.decode_bin(struct.pack("<I", 2) + bytes(crc.RECORD))


class BinCompare(unittest.TestCase):
    def setUp(self):
        self.m = crc.Median(TABLES)

    def row(self, **cells):
        base = {"enabled": "1", "numinputs": "2", "input 1": "axe", "input 2": "r01", "output": "useitem"}
        base.update(cells)
        return base

    def test_indexes(self):
        # items: weapons + armor + misc without the Expansion line; types and properties skip theirs; uniques are stored + 1
        self.assertEqual((self.m.items["toa"], self.m.types["rune"], self.m.props["sock"]), (5, 1, 1))
        self.assertEqual(self.m.expect_input("Axe of Test")["uniq"], 1)

    def test_same(self):
        b = record(numinputs=2, inputs=[(1, 0, 0, 0, 0), (1, 3, 0, 0, 0)], outputs=[{"type": 0xFE}])
        self.assertEqual(crc.compare_bin([self.row()], crc.decode_bin(table_bin(b)), self.m), [])

    def test_type_before_item(self):
        """`key` is a type and an item code: 1.13c's compiler took the type."""
        b = record(numinputs=2, inputs=[(1, 0, 0, 0, 0), (2, 2, 0, 0, 0)], outputs=[{"type": 0xFE}])
        self.assertEqual(crc.compare_bin([self.row(**{"input 2": "key"})], crc.decode_bin(table_bin(b)), self.m), [])

    def test_modifiers_and_mods(self):
        b = record(numinputs=3, inputs=[(1 | 0x20, 0, 0, 4, 0), (2, 1, 0, 0, 2)],
                   outputs=[{"type": 0xFF, "quality": 6, "flags": 0x20, "ilvl": 100, "mods": [(1, 0, 6, 6, 0)]}])
        row = self.row(numinputs="3", **{"input 1": "axe,mag,noe", "input 2": "rune,qty=2", "output": "usetype,rar,rem",
                                         "ilvl": "100", "mod 1": "sock", "mod 1 min": "6", "mod 1 max": "6"})
        self.assertEqual(crc.compare_bin([row], crc.decode_bin(table_bin(b)), self.m), [])

    def test_difference_found(self):
        b = record(op=3, param=12, value=80, numinputs=2, inputs=[(1, 0, 0, 0, 0), (1, 3, 0, 0, 0)], outputs=[{"type": 0xFE}])
        found = crc.compare_bin([self.row(op="3", param="12", value="81")], crc.decode_bin(table_bin(b)), self.m)
        self.assertEqual([f[3] for f in found], ["value"])

    def test_dropped_input(self):
        """An input name 1.13c could not resolve is left empty in the record (row 10627's `o^o`)."""
        b = record(numinputs=2, inputs=[(1, 0, 0, 0, 0)], outputs=[{"type": 0xFE}])
        found = crc.compare_bin([self.row(**{"input 2": "zzz"})], crc.decode_bin(table_bin(b)), self.m)
        self.assertEqual([(f[0], f[3]) for f in found], [("note", "input 2")])


def ctx(**over):
    stats = crc.Space([{"Stat": "level"}, {"Stat": "gold"}], "Stat")
    c = {"bank": "RotW", "renames": {}, "kinds": {"att-skill": ("skill", ["item_skillonattack"])},
         "src_stats": stats, "built_stats": crc.Space([{"Stat": "level", "*ID": "12"}, {"Stat": "gold", "*ID": "14"}], "Stat", "*ID"),
         "src_skills": crc.Space([{"skill": "Attack"}, {"skill": "Dire Charm L"}], "skill"),
         "built_skills": crc.Space([{"skill": "Attack", "*Id": "0"}, {"skill": "Dire Charm L", "*Id": "710"}], "skill", "*Id"),
         "src_uniques": ["Sunstone"], "built_uniques": ["mxl2012:Sunstone"], "src_sets": [], "built_sets": [],
         "code_map": lambda c: c.replace("\xb5", "^"),
         "built_props": {"att-skill", "str"}, "built_stat_ids": {12, 14}, "quest_items": {}, "src_quest": {}, "both_codes": set()}
    c.update(over)
    return c


class PortCompare(unittest.TestCase):
    def test_meaning_kept(self):
        src = [{"description": "x", "op": "6", "param": "1", "input 1": "Sunstone", "input 2": "9o\xb5", "mod 1": "att-skill",
                "mod 1 param": "1"}]
        built = [{"description": "x", "op": "6", "param": "14", "input 1": "mxl2012:Sunstone", "input 2": "9o^",
                  "mod 1": "att-skill", "mod 1 param": "710"}]
        self.assertEqual(crc.compare_port(src, built, ctx()), [])

    def test_wrong_stat_and_skill(self):
        src = [{"description": "x", "op": "6", "param": "1", "mod 1": "att-skill", "mod 1 param": "1"}]
        built = [{"description": "x", "op": "6", "param": "12", "mod 1": "att-skill", "mod 1 param": "0"}]
        fields = [f[3] for f in crc.compare_port(src, built, ctx())]
        self.assertEqual(fields, ["RotW: param", "RotW: mod 1 param"])

    def test_unresolved_input_emptied(self):
        """Bug #311: an input naming nothing is emptied by the build, as 1.13c compiled it (an empty slot)."""
        src = [{"description": "x", "input 1": "axe", "input 2": "zzz"}]
        built = [{"description": "x", "input 1": "axe", "input 2": ""}]
        self.assertEqual(crc.compare_port(src, built, ctx(median=crc.Median(TABLES))), [])
        self.assertEqual(len(crc.compare_port(src, [{"description": "x", "input 1": "axe", "input 2": "r01"}],
                                              ctx(median=crc.Median(TABLES)))), 1)

    def test_order_lost(self):
        self.assertEqual(crc.compare_port([{"description": "a"}], [], ctx())[0][0], "error")
        found = crc.compare_port([{"description": "a"}, {"description": "b"}], [{"description": "b"}, {"description": "a"}], ctx())
        self.assertTrue(all("description" in f[3] for f in found) and len(found) == 2)


class D2RReading(unittest.TestCase):
    def row(self, **cells):
        base = {"enabled": "1", "numinputs": "1", "input 1": "axe", "output": "useitem"}
        base.update(cells)
        return base

    def test_clean(self):
        self.assertEqual(crc.check_d2r([self.row()], ctx()), [])

    def test_field_sizes(self):
        found = crc.check_d2r([self.row(lvl="300", **{"mod 1": "str", "mod 1 max": "40000"})], ctx())
        self.assertEqual(sorted(f[3] for f in found), ["RotW: lvl", "RotW: mod 1 max"])

    def test_unknown_words_props_stats(self):
        found = crc.check_d2r([self.row(op="3", param="99", **{"input 1": "axe,foo", "output": "useitem,bar", "mod 1": "nope"})], ctx())
        self.assertEqual(sorted(f[3] for f in found), ["RotW: input 1", "RotW: mod 1", "RotW: output", "RotW: param"])

    def test_numinputs_destruction_note(self):
        found = crc.check_d2r([self.row(numinputs="3")], ctx())
        self.assertEqual([(f[0], "unlisted" in f[4]) for f in found], [("note", True)])

    def test_useitem_second_output(self):
        found = crc.check_d2r([self.row(**{"output b": "useitem,uns"})], ctx())
        self.assertEqual([(f[0], f[3]) for f in found], [("note", "RotW: output b")])

    def test_version_and_ops(self):
        found = crc.check_d2r([self.row(version="10"), self.row(op="29")], ctx())
        self.assertEqual([(f[0], f[2]) for f in found], [("note", 1), ("error", 2)])

    def test_quest_flags(self):
        c = ctx(quest_items={"msf": ("", "")}, src_quest={"msf": ("10", "1")})
        found = crc.check_d2r([self.row(op="28", **{"input 1": "msf"})], c)
        self.assertEqual([f[0] for f in found], ["error"])
        self.assertEqual(crc.check_d2r([self.row(op="28", **{"input 1": "msf"})], ctx(quest_items={"msf": ("10", "1")},
                                                                                         src_quest={"msf": ("10", "1")})), [])


class Helpers(unittest.TestCase):
    def test_split(self):
        self.assertEqual(crc.split_cell('"weap,mag,qty=2"'), ("weap", [("mag", ""), ("qty", "2")]))
        self.assertEqual(crc.s16(0xFFFF), -1)

    def test_report(self):
        text = crc.report([("error", "bin", 3, "op", "txt 3, bin 4"), ("note", "d2r", 5, "RotW: version", "version 10")],
                          {"rows": 2, "ops": crc.op_groups([{"op": "3"}, {"op": ""}])})
        self.assertIn("| error | bin | 1 | 3 | op |", text)
        self.assertIn("player 1-14", text)


if __name__ == "__main__":
    unittest.main()
