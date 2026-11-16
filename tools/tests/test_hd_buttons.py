"""tools/hd_buttons.py: the HD Send to stash and Charms buttons (bug #592), with the drawn stand-in sources (no D2R needed)."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import dc6  # noqa: E402
import hd_buttons as hb  # noqa: E402
import invtabs_hdart as ih  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = hb.Sources.drawn()


class Buttons(unittest.TestCase):
    def test_states_differ_and_fill_the_frame(self):
        for icon, (w, h) in (("sendstash", (104, 100)), ("charms", (56, 56)), ("sendstash", (64, 62))):
            frames = hb.frames(icon, w, h, hb.KINDS, SRC)
            self.assertEqual({f.size for f in frames}, {(w, h)})
            self.assertEqual(len({f.tobytes() for f in frames}), 4, icon)
            for f in frames:
                self.assertEqual(f.getpixel((w // 2, h // 2))[3], 255)  # the inside is opaque
                self.assertLess(f.getpixel((w - 1, 0))[3], 128)        # the top-right corner is margin (the shadow is lower)

    def test_greyed_has_no_colour(self):
        f = hb.button("charms", 56, 56, "greyed", SRC)
        a = np.asarray(f, dtype=int)
        rgb = a[a[..., 3] == 255][:, :3]
        self.assertLessEqual(int((rgb.max(axis=1) - rgb.min(axis=1)).max()), 12)

    def test_icon_has_colour(self):
        f = hb.button("charms", 56, 56, "normal", SRC)
        a = np.asarray(f, dtype=int)
        self.assertTrue(((a[..., 2] > a[..., 0] + 60) & (a[..., 3] == 255)).any())  # the blue stone

    def test_unknown_state(self):
        with self.assertRaises(ValueError):
            hb.button("charms", 56, 56, "disabled", SRC)

    def test_nine_slice_keeps_corners(self):
        src = Image.new("RGBA", (40, 40), (0, 0, 0, 255))
        for x in range(8):
            for y in range(8):
                src.putpixel((x, y), (x * 30, y * 30, 7, 255))
        out = hb.nine_slice(src, 100, 90, 8)
        self.assertEqual(out.size, (100, 90))
        self.assertEqual([out.getpixel((x, y)) for x in range(8) for y in range(8)], [src.getpixel((x, y)) for x in range(8) for y in range(8)])

    def test_rim_scale(self):
        self.assertEqual(hb.rim_scale(96, 90), 1.0)
        self.assertEqual(hb.rim_scale(30, 30), 0.8)

    def test_lowend_is_half(self):
        frames = hb.frames("charms", 56, 56, hb.KINDS, SRC)
        self.assertEqual({f.size for f in hb.lowend(frames)}, {(28, 28)})


class InvtabsButton(unittest.TestCase):
    def test_written_sprites(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            ih.build_button(out, SRC)
            for rel, size in ((ih.BUTTON_REL, ih.BUTTON), (ih.BUTTON_REL.with_name("button.lowend.sprite"), ih.BUTTON // 2)):
                info = dc6.sprite_info(out / rel)
                self.assertEqual((info["version"], info["frame_width"], info["height"], info["frames"]), (31, size, size, 4))

    def test_plugin_agrees(self):
        """invtabs.cpp: the stand-in's size, the mod file it looks for and the filename it then uses match invtabs_hdart."""
        src = (ROOT / "invtabs" / "src" / "invtabs.cpp").read_text(encoding="utf-8")
        self.assertEqual(int(re.search(r"constexpr int\s+ButtonSize\s*=\s*(\d+);", src).group(1)), ih.BUTTON)
        self.assertIn('ButtonArtFile[] = "data/%s";' % ih.BUTTON_REL.as_posix(), src)
        self.assertIn('ButtonArt[]     = "PANEL\\\\invtabs\\\\button";', src)
        # the plugin's frame order: normalFrame 0, pressedFrame 1, disabledFrame 2, hoveredFrame 3
        self.assertIn('"normalFrame": 0, "pressedFrame": 1, "disabledFrame": 2, "hoveredFrame": 3', src)
        self.assertEqual(ih.BUTTON_FRAMES, ("normal", "pressed", "greyed", "hovered"))



class InvtabsListMode(unittest.TestCase):
    def test_glyphs_differ_and_states_differ(self):
        frames = ih.listmode_frames(SRC)
        self.assertEqual(len(frames), 8)
        self.assertEqual({f.size for f in frames}, {(ih.BUTTON, ih.BUTTON)})
        self.assertEqual(len({f.tobytes() for f in frames}), 8)
        # the "by charm" glyph has its blue stones, the sum sign is gold only
        by_charm, total = (np.asarray(frames[k], dtype=int) for k in (0, 4))
        blue = lambda a: int(((a[..., 2] > a[..., 0] + 60) & (a[..., 3] == 255)).sum())  # noqa: E731
        self.assertGreater(blue(by_charm), 10)
        self.assertLess(blue(total), blue(by_charm))

    def test_written_sprites(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            ih.build_listmode(out, SRC)
            for rel, size in ((ih.LISTMODE_REL, ih.BUTTON), (ih.LISTMODE_REL.with_name("listmode.lowend.sprite"), ih.BUTTON // 2)):
                info = dc6.sprite_info(out / rel)
                self.assertEqual((info["version"], info["frame_width"], info["height"], info["frames"]), (31, size, size, 8))

    def test_plugin_agrees(self):
        """invtabs.cpp looks for this file and uses frames 0 / 4 per mode; layouts.h orders a glyph's frames like the art."""
        src = (ROOT / "invtabs" / "src" / "invtabs.cpp").read_text(encoding="utf-8")
        lay = (ROOT / "invtabs" / "src" / "layouts.h").read_text(encoding="utf-8")
        self.assertRegex(src, r'ListArtFile\[\]\s*=\s*"data/%s";' % re.escape(ih.LISTMODE_REL.as_posix()))
        self.assertRegex(src, r'ListArt\[\]\s*=\s*"PANEL\\\\invtabs\\\\listmode";')
        self.assertEqual(ih.LISTMODE_FRAMES, ("normal", "hovered", "pressed", "greyed"))
        self.assertRegex(lay, r'"normalFrame": \)"\s*\+ N\(t\.frame0\) \+ R"\(, "hoveredFrame": \)" \+ N\(t\.frame0 \+ 1\)')


if __name__ == "__main__":
    unittest.main()
