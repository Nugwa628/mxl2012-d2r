"""The wiki panel's generated layout header and its geometry (tools/wiki_layout.py, plugin/src/mxl_wiki_layout.h)."""
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401
import devmenu_layout as dev  # noqa: E402
import wiki_layout as lay  # noqa: E402

# the content table's category labels (lane wikipanel-data); "All" is the plugin's own
LABELS = ["All", "Uniques", "Sets", "Runewords", "Gemwords", "Base items", "Cube recipes", "Monsters", "Skills", "Ubers", "Pages"]


def _children():
    return {c["name"]: c for c in lay.layout()["root"]["children"]}


def _overlap(a, b, gap=0):
    return a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap


class Layout(unittest.TestCase):
    def test_header_current(self):
        self.assertEqual(lay.HEADER.read_text("utf-8"), lay.header_text(), "run: py -3 -I tools/wiki_layout.py header")

    def test_header_pieces_join_to_the_layout(self):
        text = lay.header_text()
        body = text[text.index("LayoutHdParts[] = {"):]
        pieces = re.findall(r'^    "(.*)",$', body, re.M)
        joined = "".join(p.replace('\\"', '"').replace("\\\\", "\\") for p in pieces)
        self.assertEqual(json.loads(joined), json.loads(json.dumps(lay.layout()["root"])))
        self.assertLess(max(len(p) for p in pieces), 16000, "one string literal stays under the compiler's limit")

    def test_panel_is_strict_json_with_every_button(self):
        root = json.loads(json.dumps(lay.layout()["root"]))
        self.assertEqual((root["name"], root["type"]), (lay.PANEL, "Panel"))
        kids = _children()
        self.assertIn(lay.INPUT, kids)
        for b in lay.BUTTONS:
            self.assertEqual(kids[f"Btn_{b}"]["fields"]["onClickMessage"], lay.CLICK_MESSAGE, b)
        self.assertEqual(len(lay.BUTTONS), len(set(lay.BUTTONS)))

    def test_no_classic_layout(self):
        self.assertNotIn("LayoutSd", lay.header_text(), "HD only: the plugin does not open the panel in classic graphics")

    def test_one_background_first(self):
        children = lay.layout()["root"]["children"]
        self.assertEqual(children[0]["name"], "Background")
        self.assertEqual(lay.widget_box(children[0]), (0, 0, lay.PANEL_W, lay.PANEL_H))

    def test_text_boxes_are_empty_and_under_the_arrows(self):
        children = lay.layout()["root"]["children"]
        order = [c["name"] for c in children]
        first_arrow = order.index("Btn_row0")
        for c in children:
            if c["type"] == "TextBoxWidget" and c["name"] not in ("Title", "InputLabel"):
                self.assertEqual(c["fields"]["text"], "", c["name"])
                self.assertLess(order.index(c["name"]), first_arrow, "text boxes stay under the arrows")

    def test_every_line_has_one_box_per_table_colour(self):
        kids = _children()
        source = (lay.ROOT / "plugin" / "src" / "wiki_logic.h").read_text("utf-8")
        names = re.search(r"ColourNames\[ColourCount\] = \{([^}]*)\}", source).group(1)
        self.assertEqual([n.strip().strip('"') for n in names.split(",")], [n for n, _rgb in lay.COLOURS], "the table's colours, in wiki_logic.h's order")
        for i in range(lay.LINES):
            boxes = [kids[f"DetailText{i}_{c}"] for c in range(len(lay.COLOURS))]
            self.assertEqual(len({json.dumps(b["fields"]["rect"]) for b in boxes}), 1, f"line {i}: one place")
            colours = [tuple(b["fields"]["style"]["fontColor"][k] for k in "rgb") for b in boxes]
            self.assertEqual(colours, [rgb for _n, rgb in lay.COLOURS])
            self.assertEqual({b["fields"]["style"]["fontFace"] for b in boxes}, {lay.TEXT_FACE})
        for i in range(lay.ROWS):
            self.assertEqual(kids[f"RowText{i}_0"]["fields"]["rect"], kids[f"RowText{i}_1"]["fields"]["rect"])
            self.assertEqual(kids[f"RowSub{i}"]["fields"]["style"]["alignment"]["h"], "right")

    def test_search_box_is_plain(self):
        box = _children()[lay.INPUT]
        self.assertNotIn("alwaysAcceptsKeyInput", box["fields"])
        self.assertFalse(box["fields"].get("focusOnMouseOver"))


class Geometry(unittest.TestCase):
    def test_every_widget_inside_the_panel(self):
        for name, child in _children().items():
            if name == "ClickCatcher":
                continue
            x, y, w, h = lay.widget_box(child)
            self.assertTrue(x >= 0 and y >= 0 and x + w <= lay.PANEL_W and y + h <= lay.PANEL_H, f"{name}: {(x, y, w, h)}")

    def test_buttons_do_not_overlap(self):
        # every button sends one message and the plugin finds the button from the click's place (panel_logic.h RectAt)
        kids = _children()
        boxes = [(b, lay.widget_box(kids[f"Btn_{b}"])) for b in lay.BUTTONS]
        for i, (a, ra) in enumerate(boxes):
            for b, rb in boxes[i + 1:]:
                self.assertFalse(_overlap(ra, rb), f"{a} / {b}")

    def test_header_rectangles_are_the_buttons(self):
        kids = _children()
        rects = re.search(r"ButtonRects\[ButtonCount\] = \{(.*)\};", lay.header_text()).group(1)
        got = [tuple(int(v) for v in r.split(",")) for r in re.findall(r"\{([^{}]*)\}", rects)]
        self.assertEqual(got, [lay.widget_box(kids[f"Btn_{b}"]) for b in lay.BUTTONS])

    def test_category_row_is_even_centred_and_labels_fit(self):
        kids = _children()
        boxes = [lay.widget_box(kids[f"Btn_cat{i}"]) for i in range(lay.CATEGORY_SLOTS)]
        self.assertEqual(len({(b[1], b[2], b[3]) for b in boxes}), 1)
        gaps = {boxes[i + 1][0] - (boxes[i][0] + boxes[i][2]) for i in range(len(boxes) - 1)}
        self.assertEqual(len(gaps), 1)
        self.assertGreater(min(gaps), 0)
        self.assertLessEqual(abs(boxes[0][0] - (lay.PANEL_W - boxes[-1][0] - boxes[-1][2])), 1, "centred")
        self.assertEqual(len(LABELS), lay.CATEGORY_SLOTS)
        for i, text in enumerate(LABELS):
            child = kids[f"Btn_cat{i}"]
            self.assertEqual(child["fields"]["textString"], f"@C{i}@", "the plugin puts the table's label here")
            self.assertLessEqual(lay.label_width(child, text), boxes[i][2] * dev.BUTTON_TEXT_SHARE, text)

    def test_sections_do_not_overlap(self):
        kids = _children()
        box = lambda n: lay.widget_box(kids[n])  # noqa: E731
        bottom = lambda n: box(n)[1] + box(n)[3]  # noqa: E731
        self.assertLessEqual(bottom("Title"), box("InputSlot")[1])
        self.assertLess(bottom("InputSlot"), box("Btn_cat0")[1])
        self.assertLess(bottom("Btn_back"), box("Btn_cat0")[1])
        self.assertLess(bottom("Btn_cat0"), box("ListPane")[1])
        self.assertFalse(_overlap(box("ListPane"), box("DetailPane")))
        self.assertLessEqual(bottom("ListPane"), box("Btn_prev")[1])
        self.assertLessEqual(bottom("Btn_prev"), box("StatusText")[1])
        self.assertLessEqual(bottom("StatusText"), lay.PANEL_H - 8)
        self.assertLess(box("Btn_back")[0] + box("Btn_back")[2], box("Btn_close")[0] + box("Btn_close")[2] + 1)
        self.assertLess(box("InputSlot")[0] + box("InputSlot")[2], box("Btn_back")[0])
        self.assertTrue(box("InputSlot")[0] <= box(lay.INPUT)[0] and box(lay.INPUT)[0] + box(lay.INPUT)[2] <= box("InputSlot")[0] + box("InputSlot")[2])

    def test_rows_and_lines_stay_in_their_panes(self):
        kids = _children()
        m = lay.layout()["metrics"]
        lx, ly, lw, lh = lay.widget_box(kids["ListPane"])
        dx, dy, dw, dh = lay.widget_box(kids["DetailPane"])
        self.assertEqual((lx, ly, lw, lh, dx, dy, dw, dh), tuple(m[k] for k in ("listX", "listY", "listW", "listH", "detailX", "detailY", "detailW", "detailH")))
        for name, child in kids.items():
            if name == "ClickCatcher":
                continue
            x, y, w, h = lay.widget_box(child)
            if name.startswith(("RowText", "RowSub", "Btn_row")):
                self.assertTrue(lx <= x and x + w <= lx + lw and ly <= y and y + h <= ly + lh, name)
            if name.startswith(("DetailText", "LineMark", "Btn_line")):
                self.assertTrue(dx <= x and x + w <= dx + dw and dy <= y and y + h <= dy + dh, name)
        # an arrow sits left of its text and in its row
        for i in range(lay.ROWS):
            ax, ay, aw, ah = lay.widget_box(kids[f"Btn_row{i}"])
            tx, ty, _tw, th = lay.widget_box(kids[f"RowText{i}_0"])
            self.assertTrue(ax + aw <= tx and ty <= ay and ay + ah <= ty + th, i)
        for i in range(lay.LINES):
            ax, ay, aw, ah = lay.widget_box(kids[f"Btn_line{i}"])
            tx, ty, _tw, th = lay.widget_box(kids[f"DetailText{i}_0"])
            self.assertTrue(ax + aw <= tx and ty <= ay and ay + ah <= ty + th, i)
            self.assertEqual(lay.widget_box(kids[f"LineMark{i}"])[:2], (lay.layout()["metrics"]["lineX"], ty))

    def test_character_counts_fit_their_boxes(self):
        m = lay.layout()["metrics"]
        self.assertLessEqual(m["rowChars"] * lay.FORMAL_CHAR, m["rowTextW"])
        self.assertLessEqual(m["lineChars"] * lay.FORMAL_CHAR, m["lineTextW"])
        self.assertGreaterEqual(m["lineChars"], 72, "a stat line of the exporter's table fits one line")
        self.assertGreaterEqual(m["rowChars"], 52, "the longest name of the exporter's table (51 characters) fits a row")
        self.assertEqual((m["rows"], m["lines"]), (lay.ROWS, lay.LINES))
        self.assertLessEqual(m["rowY"] + lay.ROWS * lay.ROW_PITCH, m["listY"] + m["listH"])
        self.assertLessEqual(m["lineY"] + lay.LINES * lay.LINE_PITCH, m["detailY"] + m["detailH"])

    def test_panel_fits_the_screen(self):
        # HD UI units: the screen is 2160 high; 16:9 is 3840 wide (1280 x 720 and 1600 x 900), 4:3 is 2880. The side panels end at y 1833.
        m = lay.layout()["metrics"]
        for w, h in ((1280, 720), (1600, 900), (1920, 1080), (1600, 1200)):
            units_w = 2160 * w / h
            left, top = units_w / 2 + m["panelX"], 1080 + m["panelY"]
            self.assertTrue(left >= 0 and left + m["panelW"] <= units_w, (w, h))
            self.assertTrue(top >= 0 and top + m["panelH"] <= 1834, (w, h))

    def test_built_table_categories_fit_the_buttons(self):
        path = lay.ROOT / "work" / "mod" / "data" / "mxl2012-wiki" / "wiki.tsv"
        if not path.exists():
            self.skipTest("no built content table (tools/build.py)")
        labels = [ln.split("\t")[2] for ln in path.read_text("utf-8").split("\n") if ln.startswith("C\t")]
        self.assertLessEqual(len(labels), lay.CATEGORY_SLOTS - 1, "one button per category beside All")
        kids = _children()
        for i, text in enumerate(labels, 1):
            self.assertLessEqual(lay.label_width(kids[f"Btn_cat{i}"], text), lay.CAT_W * dev.BUTTON_TEXT_SHARE, text)


if __name__ == "__main__":
    unittest.main()
