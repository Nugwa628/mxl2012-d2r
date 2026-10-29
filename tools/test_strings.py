"""Unit tests for tbl2json / strings_ns (py -3 -I tools/test_strings.py)."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import strings_check  # noqa: E402
import strings_ns as ns  # noqa: E402
import tbl2json  # noqa: E402


def make_tbl(entries: list[tuple[bytes, bytes]]) -> bytes:
    """Smallest valid 1.13c .tbl: header, count indices, hash nodes (one per entry), then key/text data."""
    n = len(entries)
    nodes_at = 21 + 2 * n
    data_at = nodes_at + 17 * n
    data, offs = b"", []
    for k, v in entries:
        offs.append((data_at + len(data), data_at + len(data) + len(k) + 1))
        data += k + b"\0" + v + b"\0"
    nodes = b"".join(struct.pack("<BHIIIH", 1, i, 0, ko, so, len(v) + 1) for i, ((ko, so), (_k, v)) in enumerate(zip(offs, entries)))
    head = struct.pack("<HHIBIII", 0, n, n, 0, data_at, 0, data_at + len(data))
    return head + struct.pack(f"<{n}H", *range(n)) + nodes + data


class ReadTbl(unittest.TestCase):
    def test_utf8_cp1252_and_colour_code(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.tbl"
            p.write_bytes(make_tbl([(b"a", "ÿc4Rune".encode("utf-8")), (b"b", b"\xffc1Old"), (b"c", b"plain")]))
            tbl2json.FALLBACK.clear()
            self.assertEqual(tbl2json.read_tbl(p), [("a", "ÿc4Rune"), ("b", "ÿc1Old"), ("c", "plain")])
            self.assertEqual(len(tbl2json.FALLBACK), 1)  # only the raw 0xFF string used the cp1252 path

    def test_placeholders(self):
        self.assertEqual(tbl2json.placeholders("%+d%% to %s"), ["d", "s"])


class Cells(unittest.TestCase):
    G2 = {"Short", "Armor of the Old Religion", "To The Island of the Sunless Sea", "115"}

    def test_qualify_and_aliases(self):
        al = ns.plan_aliases(["Armor of the Old Religion"])
        self.assertEqual(al, {"Armor of the Old Religion": "mxlname_1"})
        self.assertEqual(ns.cell_value("uniqueitems", "index", "Short", self.G2, al), "mxl2012:Short")
        self.assertEqual(ns.cell_value("uniqueitems", "index", "Armor of the Old Religion", self.G2, al), "mxl2012:mxlname_1")
        self.assertEqual(ns.cell_value("armor", "namestr", "Armor of the Old Religion", self.G2, al),
                         "mxl2012:Armor of the Old Religion")  # no fixed limit: the long key stays
        key = "To The Island of the Sunless Sea"  # 32 chars + 8 > 39
        with self.assertRaises(KeyError):
            ns.cell_value("levels", "LevelWarp", key, self.G2, {})
        self.assertEqual(ns.cell_value("levels", "LevelWarp", key, self.G2, ns.plan_aliases([key])), "mxl2012:mxlname_1")
        self.assertEqual(ns.cell_value("misc", "namestr", "115", self.G2, {}), "mxl2012:115")
        self.assertEqual(ns.cell_value("misc", "namestr", "strethereal", self.G2, {}), "strethereal")

    def test_overflowing_keys_from_excel(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "uniqueitems.txt").write_text("index\tcode\nArmor of the Old Religion\tx\nShort\ty\n", "utf-8")
            self.assertEqual(ns.overflowing_keys(self.G2, Path(d)), {"Armor of the Old Religion"})


class CheckCells(unittest.TestCase):
    def run_check(self, rows: str, rewritten: bool):
        from collections import defaultdict
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "armor.txt").write_text("name\tnamestr\n" + rows, "utf-8")
            errors, missing, stats = [], defaultdict(list), {"cells": 0, "missing_cells": 0}
            strings_check.check_cells(Path(d), rewritten, {"Mine"}, {"Theirs"}, {"Theirs": []}, errors, missing, stats)
            return errors, dict(missing)

    def test_raw_missing(self):
        errors, missing = self.run_check("a\tMine\nb\ttheirs\nc\tNope\n", False)
        self.assertEqual(errors, [])
        self.assertEqual(missing, {"armor.namestr": ["Nope"]})

    def test_rewritten_errors(self):
        errors, missing = self.run_check("a\tMine\nb\tmxl2012:Mine\nc\tmxl2012:Gone\nd\td2r:Theirs\ne\td2r:Gone\n", True)
        self.assertEqual(len(errors), 3)  # unqualified Mine, mxl2012:Gone, d2r:Gone
        self.assertEqual(missing, {})


if __name__ == "__main__":
    unittest.main()
