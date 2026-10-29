import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import item_rules_audit as ira  # noqa: E402


def cube_bin(*records: bytes) -> bytes:
    return struct.pack("<I", len(records)) + b"".join(records)


def record(enabled=1, min_diff=0, cls=255, op=0, param=0, value=0, numinputs=1, version=100, inputs=(), outputs=()):
    r = bytearray(ira.RECORD)
    r[0], r[2], r[3], r[4] = enabled, min_diff, cls, op
    struct.pack_into("<iihH", r, 8, param, value, numinputs, version)
    for k, slot in enumerate(inputs):
        struct.pack_into("<HHHBB", r, 0x14 + 8 * k, *slot)
    for k, slot in enumerate(outputs):
        struct.pack_into("<HHH", r, 0x4c + 0x54 * k, *slot)
    return bytes(r)


class CubeRecordTests(unittest.TestCase):
    def test_decodes_header_inputs_and_outputs(self):
        data = cube_bin(record(), record(op=16, param=219, value=0, numinputs=6, version=10,
                                         inputs=[(1, 2359, 0, 0, 0), (0x41, 2364, 1792, 7, 0)], outputs=[(8, 5, 201)]))
        rec = ira.cube_record(data, 1)
        self.assertEqual((rec["op"], rec["param"], rec["value"], rec["numinputs"], rec["version"]), (16, 219, 0, 6, 10))
        self.assertEqual(rec["inputs"][:3], [(1, 2359, 0, 0, 0), (0x41, 2364, 1792, 7, 0), (0, 0, 0, 0, 0)])
        self.assertEqual(rec["outputs"][0], (8, 5, 201))

    def test_header_diffs_against_the_txt_row(self):
        rec = ira.cube_record(cube_bin(record(cls=4, op=3, param=12, value=121, numinputs=2)), 0)
        row = {"enabled": "1", "class": "bar", "op": "3", "param": "12", "value": "121", "numinputs": "2", "version": "100"}
        self.assertEqual(ira.header_diffs(row, rec), [])
        self.assertEqual(ira.header_diffs({**row, "class": "", "value": "120"}, rec), ["class", "value"])


class TreasureClassReachTests(unittest.TestCase):
    def test_reach_goes_up_through_parent_classes(self):
        tc = [{"Treasure Class": "Leaf", "Item1": "gem"},
              {"Treasure Class": "Mid", "Item1": '"Leaf,mul=2"'},
              {"Treasure Class": "Top", "Item1": "Mid"},
              {"Treasure Class": "Orphan", "Item1": "Leaf"}]
        roots = {"Top": ["monstats.TreasureClass"]}
        self.assertEqual(ira.tc_reach(tc, roots, "Leaf"), ["monstats.TreasureClass"])
        self.assertEqual(ira.tc_reach(tc, roots, "Orphan"), [])


class PropertyColumnTests(unittest.TestCase):
    def test_slot_columns_of_each_table_kind(self):
        header = ["index", "prop1", "par1", "aprop2b", "PCode3a", "FCode8", "T1Code7", "mod1code", "mod 1", "b mod 5",
                  "weaponMod2Code", "helmMod1Param", "itype1"]
        self.assertEqual(ira.property_columns(header), ["prop1", "aprop2b", "PCode3a", "FCode8", "T1Code7", "mod1code",
                                                        "mod 1", "b mod 5", "weaponMod2Code"])


if __name__ == "__main__":
    unittest.main()
