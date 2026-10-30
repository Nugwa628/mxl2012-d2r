"""Unit tests of tools/pet_icons.py (bug #514): the HD layout edit, the picture shift inside the frame, which entries a build
takes, the pettype.txt baseicon edit, and the build on a synthetic mod with fake D2R files.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_pet_icons.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import pet_icons as P  # noqa: E402
import ui_art  # noqa: E402
from PIL import Image  # noqa: E402

LAYOUT = '{\n    "fields": {\n        "summonsUseSecondSet": true,\n        "nameAlternationSecondSetY": 0,\n    }\n}\n'
DC6_BYTES = b"DC6 of the class face"


def icon(colour=(200, 40, 40, 255), frame=(150, 120, 60, 255), size=120):
    im = Image.new("RGBA", (size, size), frame)
    f = P.FRAME[size]
    im.paste(Image.new("RGBA", (size - 2 * f, size - 2 * f), colour), (f, f))
    return im


class LayoutTests(unittest.TestCase):
    def test_names_staggered(self):
        out = P.layout_text(LAYOUT)
        self.assertIn(f'"nameAlternationSecondSetY": {P.NAME_STAGGER}', out)
        self.assertIn('"summonsUseSecondSet": true', out)

    def test_missing_field_is_an_error(self):
        with self.assertRaises(ValueError):
            P.layout_text('{"fields": {}}')


class ShiftTests(unittest.TestCase):
    def test_frame_kept_inside_shifted(self):
        src = icon()
        out = P.shift(src, {"hue": 120})
        self.assertEqual(out.size, src.size)
        self.assertEqual(out.getpixel((2, 60)), src.getpixel((2, 60)))   # the gold frame
        r, g, b, a = out.getpixel((60, 60))
        self.assertGreater(g, r)                                         # red turned green
        self.assertEqual(a, 255)

    def test_no_change_without_shift(self):
        src = icon()
        self.assertEqual(list(P.shift(src, {}).tobytes()), list(src.tobytes()))

    def test_value_and_lowend(self):
        out = P.shift(icon(size=60), {"val": 0.5})
        self.assertLess(out.getpixel((30, 30))[0], 120)
        self.assertEqual(out.getpixel((1, 30)), (150, 120, 60, 255))


class ChosenTests(unittest.TestCase):
    SPEC = {"enabled": False, "pets": {"a": {"icon": "x"}, "b": {"icon": "y", "enabled": False}}}

    def test_off_by_default(self):
        self.assertEqual(P.chosen(self.SPEC), {})

    def test_enabled(self):
        self.assertEqual(set(P.chosen(dict(self.SPEC, enabled=True))), {"a"})

    def test_trial(self):
        self.assertEqual(set(P.chosen(self.SPEC, "all")), {"a", "b"})
        self.assertEqual(set(P.chosen(self.SPEC, "b")), {"b"})
        with self.assertRaises(SystemExit):
            P.chosen(self.SPEC, "zz")

    def test_committed_file_is_on(self):
        spec = P.load_spec()
        self.assertTrue(spec["enabled"])  # owner approved the review sheet (2026-10-31)
        self.assertEqual(len(P.chosen(spec)), 15)
        for k, e in spec["pets"].items():
            self.assertTrue(e.get("icon") and e.get("why"), k)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.d2r = self.tmp / "d2r"
        (self.d2r / "data/global/ui/layouts").mkdir(parents=True)
        (self.d2r / P.LAYOUT).write_text(LAYOUT, "utf-8")
        (self.d2r / P.DC6_DIR).mkdir(parents=True)
        (self.d2r / P.DC6_DIR / "necromancericon.dc6").write_bytes(DC6_BYTES)
        for suffix, size in ((".sprite", 120), (".lowend.sprite", 60)):
            ui_art.write_sprite(self.d2r / P.HD_DIR / f"wolf{suffix}", [icon(size=size)])
        self.mod = self.tmp / "mod"
        for bank in ("", "base/"):
            p = self.mod / f"data/global/excel/{bank}pettype.txt"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"pet type\tname\tbaseicon\r\nshadowspet\tShadow\tnecromancericon\r\nlamiaspet\tLamia\tnecromancericon\r\n")
        self.spec = self.tmp / "spec.json"
        self.spec.write_text(json.dumps({"enabled": False, "pets": {"shadowspet": {"icon": "wolf", "hue": 90, "why": "t"}}}))

    def run_build(self, trial=None):
        with mock.patch.object(P.fxpaths, "d2r_file", lambda rel: self.d2r / rel), \
                mock.patch.object(P, "load_spec", lambda path=None: json.loads(self.spec.read_text())), \
                mock.patch.object(P, "median_baseicons", lambda: {"shadowspet": "necromancericon"}):
            return P.build(self.mod, trial)

    def test_off_writes_only_the_layout(self):
        self.assertEqual(self.run_build(), 0)
        self.assertIn(f": {P.NAME_STAGGER}", (self.mod / P.LAYOUT).read_text("utf-8"))
        self.assertFalse((self.mod / P.HD_DIR).exists())
        self.assertIn("\tnecromancericon\r\n", (self.mod / "data/global/excel/pettype.txt").read_bytes().decode())

    def test_trial_writes_icons_and_rows(self):
        self.run_build("all")
        for bank in ("", "base/"):
            text = (self.mod / f"data/global/excel/{bank}pettype.txt").read_bytes().decode()
            self.assertIn("shadowspet\tShadow\tmxl_shadowspet\r\n", text)
            self.assertIn("lamiaspet\tLamia\tnecromancericon\r\n", text)   # no entry: Median's icon stays
        self.assertEqual((self.mod / P.DC6_DIR / "mxl_shadowspet.dc6").read_bytes(), DC6_BYTES)  # legacy unchanged
        hd = ui_art.read_sprite(self.mod / P.HD_DIR / "mxl_shadowspet.sprite")[0]
        low = ui_art.read_sprite(self.mod / P.HD_DIR / "mxl_shadowspet.lowend.sprite")[0]
        self.assertEqual((hd.size, low.size), ((120, 120), (60, 60)))
        self.assertNotEqual(hd.getpixel((60, 60)), (200, 40, 40, 255))
        self.run_build("all")  # again over the edited tables: Median's name is looked up instead of mxl_
        self.assertEqual((self.mod / P.DC6_DIR / "mxl_shadowspet.dc6").read_bytes(), DC6_BYTES)


if __name__ == "__main__":
    unittest.main()
