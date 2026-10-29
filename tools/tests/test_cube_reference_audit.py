import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from cube_reference_audit import audit


class CubeReferences(unittest.TestCase):
    def test_checks_each_input_output_and_operation(self):
        rows = [{"input 1": '"gem,qty=2"', "input 7": "missing",
                 "output": '"useitem,mag"', "output c": "unknown", "op": "29"},
                {"input 1": "gem", "output": "Cow Portal", "op": "28"}]
        self.assertEqual(audit(rows, {"gem"}), [(1, "input 7", "missing"),
                                                (1, "output c", "unknown"), (1, "op", "29")])
