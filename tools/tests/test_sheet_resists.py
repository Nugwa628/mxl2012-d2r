"""Magic / Physical Resistance rows on the character sheet (tools/sheet_resists.py, plugin part sheetres): the widget names
the plugin fills, the rows' places in the three layouts, the spliced HD background and the classic boxes."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import pad_ui  # noqa: E402
import sheet_resists as sr  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D2R = Path(fxpaths.D2R)
SRC = D2R / "data" / sr.LAYOUTS
HAVE_D2R = (SRC / sr.PC_HD).is_file() and (SRC / sr.PAD).is_file()
MEDIAN_INVCHAR = Path(fxpaths.MXL_ROOT) / "data" / sr.INVCHAR


def plugin_names() -> set[str]:
    """The value box names statbook/src/sheet_resist_logic.h fills."""
    text = (ROOT / "statbook" / "src" / "sheet_resist_logic.h").read_text("utf-8")
    return set(re.findall(r'"(Mxl\w+)"', text)) - {"MxlSheetLegacy"}


def widgets(node):
    yield node
    for c in node.get("children", []):
        yield from widgets(c)


def by_name(lay: dict) -> dict[str, dict]:
    return {w["name"]: w for w in widgets(lay) if "name" in w}


def box(w: dict) -> tuple[int, int, int, int]:
    r = w["fields"]["rect"]
    return r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]


class Names(unittest.TestCase):
    def test_value_boxes_are_the_plugins(self):
        made = {base + suffix for _t, base, _tip in sr.ROWS for suffix, _c in sr.COLOURS}
        self.assertEqual(made, plugin_names())

    def test_one_box_per_colour(self):
        self.assertEqual([c for _s, c in sr.COLOURS], ["$FontColorWhite", "$FontColorGold", "$FontColorRed"])


class Literals(unittest.TestCase):
    def test_keys_written_out(self):
        lay = {"children": [{"fields": {"text": "@a\n@b", "tooltipString": "@c", "x": "plain @a"}}]}
        used = set()
        sr.literalize(lay, {"a": "A", "b": "B", "c": "C"}, used)
        f = lay["children"][0]["fields"]
        self.assertEqual((f["text"], f["tooltipString"], f["x"]), ("A\nB", "C", "plain @a"))
        self.assertEqual(used, {"a", "b", "c"})

    def test_unknown_key_is_an_error(self):
        with self.assertRaises(ValueError):
            sr.literalize({"text": "@nope"}, {}, set())


class Geometry(unittest.TestCase):
    def test_hd_splice_keeps_the_frame_height(self):
        self.assertEqual(sr.SPLICE_END, sr.LEDGE[0] + (sr.SEPARATOR[1] - sr.SEPARATOR[0]) + (sr.ROW2[1] - sr.ROW2[0]) + sr.LEDGE_H)
        self.assertLess(sr.SPLICE_END, 1445)           # the stat points bar's bottom
        r = sr.points_rect({"x": 91, "y": 1388, "width": 972, "height": 60})
        self.assertGreaterEqual(r["y"], sr.SPLICE_END)
        self.assertLessEqual(r["y"] + r["height"], 1445 + 2)

    def test_legacy_boxes_fit_between_plate_and_close_button(self):
        w = sr.legacy_box_width()
        self.assertLess(sr.LEGACY_X + w, sr.LEGACY_CLOSE_X)
        self.assertGreater(min(sr.LEGACY_ROWS), sr.LEGACY_PLATE_BOTTOM)
        h = sr.FIRE_BOX[3] - sr.FIRE_BOX[1]
        self.assertLessEqual(sr.LEGACY_ROWS[0] + h, sr.LEGACY_ROWS[1])
        self.assertLessEqual(sr.LEGACY_ROWS[1] + h, 432)

    def test_legacy_art_copies_the_fire_box(self):
        import numpy as np
        idx = np.arange(432 * 320, dtype=np.int32).reshape(432, 320) % 200 + 1
        out = sr.legacy_art(idx)
        x0, y0, x1, y1 = sr.FIRE_BOX
        top = sr.LEGACY_ROWS[1]
        self.assertTrue((out[top:top + y1 - y0, sr.LEGACY_X:sr.LEGACY_X + sr.LEGACY_CUT[0] - x0] == idx[y0:y1, x0:sr.LEGACY_CUT[0]]).all())
        self.assertTrue((out[top:top + y1 - y0, sr.legacy_x(sr.LEGACY_CUT[1]):sr.legacy_x(x1)] == idx[y0:y1, sr.LEGACY_CUT[1]:x1]).all())
        self.assertTrue((out[:sr.LEGACY_ROWS[0]] == idx[:sr.LEGACY_ROWS[0]]).all())


@unittest.skipUnless(HAVE_D2R, "needs D2R 93847's extraction (fxpaths.D2R)")
class Layouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = sr.strings(D2R)
        cls.lays = {}
        for name, edit in ((sr.PC_HD, sr.pc_hd), (sr.LEGACY, sr.legacy), (sr.PAD, sr.pad)):
            lay = edit(pad_ui.load((SRC / name).read_text("utf-8-sig")))
            sr.literalize(lay, cls.table, set())
            cls.lays[name] = lay

    def test_no_key_left(self):
        for name, lay in self.lays.items():
            self.assertNotIn('"@', json.dumps(lay), name)

    def test_every_layout_has_the_plugin_boxes(self):
        for name, lay in self.lays.items():
            self.assertLessEqual(plugin_names(), set(by_name(lay)), name)

    def test_hd_rows_under_the_elements(self):
        n = by_name(self.lays[sr.PC_HD])
        for new, old in (("MxlMagicText", "ColdText"), ("MxlPhysicalText", "PoisonText"),
                         ("MxlMagicResistanceTitle", "ColdResistanceTitle")):
            a, b = box(n[new]), box(n[old])
            self.assertEqual((a[0], a[2]), (b[0], b[2]), new)
            self.assertGreaterEqual(a[1], b[3], new)
        self.assertEqual(n["MxlMagicResistanceTitle"]["fields"]["text"], "Magic Resistance")
        self.assertGreaterEqual(box(n["CombinedPointsInfo"])[1], box(n["MxlMagicText"])[3])

    def test_legacy_rows_beside_the_stack(self):
        n = by_name(self.lays[sr.LEGACY])
        self.assertEqual(box(n["MxlMagicText"])[1], box(n["LightningText"])[1])
        self.assertEqual(box(n["MxlPhysicalText"])[1], box(n["PoisonText"])[1])
        self.assertLess(box(n["MxlMagicText"])[2], sr.LEGACY_CLOSE_X)
        self.assertEqual(n["MxlPhysicalResistanceTitle"]["fields"]["text"], "Physical\nResistance")

    def test_only_legacy_has_the_marker(self):
        logic = (ROOT / "statbook" / "src" / "sheet_resist_logic.h").read_text("utf-8")
        self.assertIn('LegacyMarker = "%s"' % sr.LEGACY_MARKER, logic)
        for name, lay in self.lays.items():
            self.assertEqual(sr.LEGACY_MARKER in by_name(lay), name == sr.LEGACY, name)

    def test_pad_rows_under_poison(self):
        n = by_name(self.lays[sr.PAD])
        self.assertGreater(box(n["MxlMagicText"])[1], box(n["PoisonText"])[3])
        self.assertGreater(box(n["MxlPhysicalText"])[1], box(n["MxlMagicText"])[3])
        self.assertLess(box(n["MxlPhysicalText"])[3], box(n["CombinedPointsInfo"])[1])
        self.assertIn("MxlMagicResistanceBG", n)


@unittest.skipUnless(HAVE_D2R and MEDIAN_INVCHAR.is_file(), "needs D2R's extraction and Median's invchar6.dc6")
class HdArt(unittest.TestCase):
    """The third row is not a pixel copy of the Cold / Poison row, and the ledge is cut, not scaled."""

    def art(self):
        from PIL import Image
        import random
        rnd = random.Random(7)
        im = Image.new("RGB", (1162, 1507))
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(1162 * 1507)])
        return im

    def test_new_row_is_not_the_row_above(self):
        src = self.art()
        out = sr.hd_art(src)
        x0, x1 = sr.INTERIOR
        y = sr.NEW_ROW_Y
        h = sr.ROW2[1] - sr.ROW2[0]
        new = out.crop((x0, y, x1, y + h)).tobytes()
        self.assertNotEqual(new, src.crop((x0, sr.ROW2[0], x1, sr.ROW2[1])).tobytes())
        self.assertEqual(new, src.crop((x0, sr.ROW1[0], x1, sr.ROW1[0] + h)).tobytes())

    def test_ledge_rows_are_source_rows(self):
        src = self.art()
        out = sr.hd_art(src)
        x0, x1 = sr.INTERIOR
        ly = sr.NEW_ROW_Y + sr.ROW2[1] - sr.ROW2[0]
        skip = sr.LEDGE[1] - sr.LEDGE[0] - sr.LEDGE_H
        cuts = sr.ledge_cuts(x1 - x0)
        self.assertTrue(all(sr.LEDGE_TOP - 2 <= c <= sr.LEDGE_TOP + 2 for c in cuts))
        self.assertGreater(len(set(cuts)), 1)          # ragged, not one straight cut
        for x in range(0, x1 - x0, 37):
            c = cuts[x]
            for y in range(sr.LEDGE_H):
                got = out.getpixel((x0 + x, ly + y))
                if y < c - sr.BLEND // 2:              # unscaled top rows
                    self.assertEqual(got, src.getpixel((x0 + x, sr.LEDGE[0] + y)))
                elif y >= c + sr.BLEND // 2:           # unscaled bottom rows
                    self.assertEqual(got, src.getpixel((x0 + x, sr.LEDGE[0] + y + skip)))
        self.assertEqual(out.crop((0, sr.SPLICE_END, 1162, 1507)).tobytes(), src.crop((0, sr.SPLICE_END, 1162, 1507)).tobytes())


class Build(unittest.TestCase):
    def test_build_writes_everything(self):
        import shutil
        import ui_art
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp)
            (data / sr.INVCHAR).parent.mkdir(parents=True)
            shutil.copy(MEDIAN_INVCHAR, data / sr.INVCHAR)
            sr.build(D2R, data)
            for name in (sr.PC_HD, sr.LEGACY, sr.PAD):
                self.assertTrue((data / sr.LAYOUTS / name).is_file(), name)
            hd = data / "hd" / "global" / "ui" / f"{sr.BACKGROUND}.sprite"
            art, low = ui_art.read_sprite(hd)[0], ui_art.read_sprite(hd.with_name(hd.stem + ".lowend.sprite"))[0]
            self.assertEqual(art.size, (1162, 1507))
            self.assertEqual(low.size, (581, 753))
            import dc6
            frames = dc6.read_dc6(data / sr.INVCHAR)
            orig = dc6.read_dc6(MEDIAN_INVCHAR)
            self.assertEqual(len(frames), 8)
            self.assertEqual([f[4] for i, f in enumerate(frames) if i != 2], [f[4] for i, f in enumerate(orig) if i != 2])
            self.assertNotEqual(frames[2][4], orig[2][4])
            before = (data / sr.INVCHAR).read_bytes()
            sr.edit_invchar(data / sr.INVCHAR, dc6.palette(D2R / "data" / "global" / "palette" / "units" / "pal.dat"))
            self.assertEqual((data / sr.INVCHAR).read_bytes(), before)   # a second run changes nothing


if __name__ == "__main__":
    unittest.main()
