"""tools/pad_input.py: the scripted gamepad's script words and status line (lane padinput).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_pad_input.py"
"""
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import pad_input as pi  # noqa: E402


class ScriptTest(unittest.TestCase):
    def test_words(self):
        self.assertEqual(pi.parse_script("a lb+A down:300 hold:lb release release:lb wait:1.5 stick:r:-50:100 trigger:L:255"),
                         [("h", "press a 120"), ("h", "press lb+a 120"), ("h", "press down 300"), ("h", "hold lb"),
                          ("h", "release"), ("h", "release lb"), ("wait", 1.5), ("h", "stick R -50 100"), ("h", "trigger L 255")])

    def test_bad_words(self):
        for word in ("q", "a+q", "hold", "stick:l:0:101", "stick:x:0:0", "trigger:r:256", "a:99999", "a:b:c"):
            with self.assertRaises(ValueError, msg=word):
                pi.parse_script(word)

    def test_empty(self):
        self.assertEqual(pi.parse_script("  "), [])


class StatusTest(unittest.TestCase):
    LINE = ("pad on=1 hooked=1 polls=812 packet=14 buttons=0x1200 lt=0 rt=255 l=0,-16383 r=32767,0 held=0x200 "
            "pressed=0x1000 gamepadUi=1 device=1")

    def test_parse(self):
        st = pi.parse_status(["something", self.LINE])
        self.assertEqual(st["polls"], 812)
        self.assertEqual(st["buttons"], 0x1200)
        self.assertEqual((st["lx"], st["ly"], st["rx"], st["ry"]), (0, -16383, 32767, 0))
        self.assertEqual((st["held"], st["pressed"], st["gamepadUi"], st["device"]), (0x200, 0x1000, 1, 1))

    def test_none(self):
        self.assertEqual(pi.parse_status(["pad: usage"]), {})

    def test_run_script_stops_at_refusal(self):
        sent = []

        def H(cmd):
            sent.append(cmd)
            return (cmd != "pad hold lb"), [self.LINE]

        pi.GAP_S, gap = 0.0, pi.GAP_S
        try:
            self.assertFalse(pi.run_script(H, "a:0 hold:lb b", []))
        finally:
            pi.GAP_S = gap
        self.assertEqual(sent, ["pad press a 0", "pad hold lb"])


if __name__ == "__main__":
    unittest.main()
