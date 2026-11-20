"""The Stat Book's HD layouts (tools/statbook_layout.py): the widget-name contract of docs/statbook-layout.md, valid layouts,
every page fitting its slots, and the seam-free art helpers."""
import json
import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import pad_ui  # noqa: E402
import sheet_resists as sr  # noqa: E402
import statbook_layout as L  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "statbook-layout.md"
D2R = Path(fxpaths.D2R)
SRC = D2R / "data" / sr.LAYOUTS
HAVE_D2R = (SRC / sr.PC_HD).is_file() and (SRC / sr.PAD).is_file()
BOOK = L.read_book(L.full_book_text())
TONE_NAMES = "|".join(t for t, _ in L.TONES)


def widgets(node):
    yield node
    for c in node.get("children", []):
        yield from widgets(c)


def pattern(name: str) -> str:
    """A widget name with its indices and tone as placeholders, the way the doc writes them."""
    name = re.sub(f"Value({TONE_NAMES})$", "Value<Tone>", name)
    return re.sub(r"\d+", "#", name)


def doc_patterns() -> set[str]:
    out = set()
    for tok in re.findall(r"`([A-Za-z<>]+)`", DOC.read_text("utf-8")):
        if tok.startswith(("Sb", "StatBook")):
            out.add(re.sub(r"<(i|ii|jj)>", "#", tok))
    return out


class Contract(unittest.TestCase):
    def test_doc_lists_every_name(self):
        made = {pattern(n) for n in L.contract_names(BOOK) | L.contract_names(BOOK, pad_layout=True)}
        self.assertEqual(made, doc_patterns())

    def test_tones_are_book_logic_order(self):
        text = (ROOT / "statbook" / "src" / "book_logic.h").read_text("utf-8")
        enum = re.search(r"enum\s+(?:class\s+)?Tone[^{]*\{([^}]*)\}", text).group(1)
        names = [re.sub(r"\s*=.*", "", s).strip() for s in enum.split(",") if s.strip() and not s.strip().startswith("//")]
        self.assertEqual([t for t, _ in L.TONES], names)



class Pages(unittest.TestCase):
    def test_every_page_has_room(self):
        longest = max(len(L.page_lines(recs)) for _p, _t, recs in BOOK["pages"])
        self.assertLessEqual(longest, L.LINES)
        self.assertEqual(L.LINES, 2 * L.PAD_ROWS)

    def test_tabs(self):
        labels = [t for t, _ in L.tabs(BOOK)]
        self.assertEqual(labels[0], "Character")
        self.assertEqual(labels[-1], "All Stats")
        self.assertEqual(len(labels), len(BOOK["pages"]) + 2)

    def test_texts_fit(self):
        if L.font("Formal", 20) is None:
            self.skipTest("D2R's fonts not available (fxpaths.d2r_file)")
        self.assertEqual(L.fit_problems(BOOK, L.PC) + L.fit_problems(BOOK, L.PADG), [])

    def test_same_measure_on_every_os(self):
        # BASIC layout pinned: with raqm (Linux wheels) "Advanced" is 130.3 px at 18 pt and the side tabs fell to 17 pt
        if L.font("", 18) is None:
            self.skipTest("D2R's fonts not available (fxpaths.d2r_file)")
        from PIL import ImageFont
        self.assertEqual(L.font("", 18).layout_engine, ImageFont.Layout.BASIC)
        self.assertEqual(L.text_w("Advanced", "", 18), 130.0)
        self.assertEqual(L.tab_point_size([t for t, _ in L.tabs(BOOK)], L.SIDE), 18)

    def test_page_lines(self):
        sec, half, full = ["section", "Head"], ["row", "a", "1", "%d", "w", "h"], ["row", "b", "2", "%d", "w", ""]
        lines = L.page_lines([sec, half, half, half, full, sec, half])
        self.assertEqual([ln[0] for ln in lines], ["heading", "pair", "pair", "full", "heading", "pair"])
        self.assertIsNone(lines[2][2])
        self.assertIsNone(lines[5][2])

    def test_slots_inside_the_body(self):
        x0, y0, x1, y1 = L.PC.body
        for i in range(L.LINES):
            x, y = L.line_xy(i, L.PC)
            self.assertTrue(x0 <= x and x + L.full_w(L.PC) <= x1 and y0 <= y and y + L.PC.cell_h <= y1, i)
        for j in range(L.ALL_ROWS):
            x, y = L.all_xy(j, L.PC)
            self.assertTrue(x + L.PC.all_w <= L.PC.track_x and y + L.PC.all_h <= y1, j)
        for i in range(L.LINES):     # the gamepad: inside D2R's plain stone (2738 wide, the bar from 1335)
            x, y = L.line_xy(i, L.PADG)
            self.assertTrue(x + L.full_w(L.PADG) <= 2738 - 40 and y + L.PADG.cell_h <= 1335, i)
        for j in range(L.PAD_ALL_ROWS):
            x, y = L.all_xy(j, L.PADG)
            self.assertTrue(x + L.PADG.all_w <= 2738 - 40 and y + L.PADG.all_h <= 1335, j)

    def test_highlight_layers(self):
        texts = [(True, "Offense"), (False, "Adds 3-5 Fire Damage"), (False, "Cold Resistance")]
        self.assertEqual(L.search(texts, "fire"), [(0, -1), (1, 9)])
        self.assertEqual(L.search(texts, ""), [(0, -1), (1, -1), (2, -1)])

    def test_match_colour_stands_out(self):
        rows = [w for w in L.all_widgets(BOOK, L.PC, True, "fire") if w["name"].startswith("SbAll")]
        hit = next(k for r in rows for k in r.get("children", []) if k["name"].endswith("Hit"))
        self.assertEqual(hit["fields"]["style"]["fontColor"], L.HIT)
        self.assertNotEqual(L.HIT, L.GOLD)

    def test_value_and_label_boxes_match_the_fit_check(self):
        for g in (L.PC, L.PADG):
            cell = L.cell_group("X", 0, 0, "HalfCell", 0, g.half, g, None)
            label = next(k for k in cell["children"] if k["name"] == "XLabel")
            value = next(k for k in cell["children"] if k["name"] == "XValueWhite")
            self.assertEqual(label["fields"]["rect"]["width"], g.half[0] - 14)
            self.assertEqual(value["fields"]["rect"]["width"], g.half[1] - 12)
            self.assertEqual(label["fields"]["style"].get("spacing"), L.LABEL_SPACING)


class Plain(unittest.TestCase):
    """The plain D2R panels (statbook_plain_layout.h): current, the mod's layouts with D2R's stock art but the Stat Book's
    own sprites, every name the host fills."""

    def test_header_is_current(self):
        if L.font("Formal", 20) is None:  # the tab point size is measured with D2R's fonts (tab_point_size)
            self.skipTest("D2R's fonts not available (fxpaths.d2r_file)")
        self.assertEqual(L.PLAIN_HEADER.read_text("utf-8"), L.plain_header_text(),
                         "statbook/src/statbook_plain_layout.h is out of date: py -3 -I tools/statbook_layout.py plain")

    def test_stock_art_but_the_own_sprites(self):
        for make in (L.plain_layout, L.plain_side_layout):
            files = {w["fields"]["filename"] for w in widgets(make(L.plain_book())) if "filename" in w.get("fields", {})}
            self.assertLessEqual({f[len(L.ART):] for f in files if f.startswith(L.ART)}, set(L.PLAIN_OWN_ART), make.__name__)
            files = {w["fields"]["filename"] for w in widgets(make(L.plain_book(), stock=True)) if "filename" in w.get("fields", {})}
            self.assertFalse([f for f in files if f.startswith(L.ART)], files)

    def test_fallback_swaps_every_own_sprite(self):
        book = L.plain_book()
        texts = [L._compact(L.plain_layout(book)), L._compact(L.plain_side_layout(book))]
        for _file, own, stock in L.art_fallback(book):
            self.assertEqual(sum(t.count(own) for t in texts), 1)
            texts = [t.replace(own, stock) for t in texts]
        self.assertEqual(json.loads(texts[0]), L.plain_layout(book, stock=True))
        self.assertEqual(json.loads(texts[1]), L.plain_side_layout(book, stock=True))
        files = {f for f, _, _ in L.art_fallback(book)}
        self.assertEqual(files, {a.lower() + ".sprite" for a in L.PLAIN_OWN_ART})

    def test_same_as_the_mods_layouts(self):
        # every widget of the mod's PC and side layouts is in the plain ones, the same but its art (the Stat Book's sprites
        # but its own swapped for D2R's)
        book = L.plain_book()
        pc = {"type": "Panel", "name": "pc", "children": L.statbook_widgets(book, L.PC)}
        L.leaf_visibility(pc["children"])
        for mod, plain in ((pc, L.plain_layout(book)), (L.side_layout(book), L.plain_side_layout(book))):
            got = {w["name"]: w for w in widgets(plain)}
            for w in widgets(mod):
                if w is mod:
                    continue
                f = w.get("fields", {})
                art = f.get("filename", "")[len(L.ART):] if f.get("filename", "").startswith(L.ART) else None
                self.assertTrue(w["name"] in got, w["name"])
                g = got[w["name"]]["fields"]
                if art is None or art in L.PLAIN_OWN_ART:
                    self.assertEqual(g, f, w["name"])
                else:
                    self.assertEqual(g.get("visible", True), f.get("visible", True), w["name"])

    def test_every_image_shipped_or_stock(self):
        # every image the plain layouts use is the Stat Book's own sprite (PLAIN_OWN_ART, shipped with the plugin: written by
        # the art build, which plain installs copy) with a Fallback row for each widget that shows it, or D2R's own sprite
        book = L.plain_book()
        out = ROOT / "work" / "mod" / "data" / "hd" / "global" / "ui" / "panel" / "statbook"
        if out.is_dir():
            for art in L.PLAIN_OWN_ART:
                for ext in (".sprite", ".lowend.sprite"):
                    self.assertTrue((out / (art.lower() + ext)).is_file(), art + ext)
        rows = {own for _, own, _ in L.art_fallback(book)}
        ui = D2R / "data" / "hd" / "global" / "ui"
        for make in (L.plain_layout, L.plain_side_layout):
            for w in widgets(make(book)):
                fn = w.get("fields", {}).get("filename")
                if fn is None:
                    continue
                if fn.startswith(L.ART):
                    art = fn[len(L.ART):]
                    self.assertIn(art, L.PLAIN_OWN_ART, w["name"])
                    self.assertIn(L._compact(w), rows, w["name"])
                elif ui.is_dir():
                    self.assertTrue(fxpaths.ci(ui / (fn.replace("\\", "/") + ".sprite")).is_file(), fn)  # D2R ignores case
        # the cell art is there: plain rows have their boxes as on the mod
        arts = {w["fields"]["filename"][len(L.ART):] for w in widgets(L.plain_side_layout(book)) if w.get("fields", {}).get("filename", "").startswith(L.ART)}
        self.assertLessEqual({"SideHalfCell", "SideFullCell", "SideAllCell", "SideRule", "SideAllRule"}, arts)
        arts = {w["fields"]["filename"][len(L.ART):] for w in widgets(L.plain_layout(book)) if w.get("fields", {}).get("filename", "").startswith(L.ART)}
        self.assertLessEqual({"HalfCell", "FullCell", "AllCell", "Rule", "AllRule"}, arts)

    def test_names_the_host_fills(self):
        book = L.plain_book()
        names = {w.get("name") for w in widgets(L.plain_layout(book))}
        art_leaves = {n for n in L.contract_names(book) if n.endswith(("Cell", "HeadingRule"))}
        self.assertEqual(L.contract_names(book) - art_leaves - names, set())
        side = {w.get("name") for w in widgets(L.plain_side_layout(book))}
        self.assertEqual(L.contract_names(book) - art_leaves - side - {"SbTab0", "SbTab0Selected", "SbTab0SelectedLabel"}, set())
        self.assertEqual(L.plain_layout(book)["name"], "statbook/SbPlainPanel")
        self.assertEqual(L.plain_side_layout(book)["name"], L.SIDE_NAME)

    def test_pieces_fit_msvc(self):
        text = L.plain_header_text()
        for piece in re.findall(r'R"SBJSON\((.*?)\)SBJSON"', text, flags=re.S):
            self.assertLess(len(piece), 16000)

    def test_body_shade_covers_the_body(self):
        book = L.plain_book()
        x0, y0, x1, y1 = L.PC.body
        for body, (x, y, w, h) in ((next(c for c in L.plain_layout(book)["children"] if c["name"] == "SbPageBody"), (x0, y0, x1 - x0, y1 - y0)),
                                   (next(c for c in L.plain_side_layout(book, stock=True)["children"] if c["name"] == "SbSideBody"),
                                    (0, 0, L.SIDE_W, L.SIDE_H))):
            tops = sorted({k["fields"]["rect"]["y"] for k in body["children"]})
            side = round(33 * body["children"][0]["fields"]["rect"]["scale"])
            self.assertEqual((body["fields"]["rect"]["x"], body["fields"]["rect"]["y"]), (x, y))
            self.assertEqual(tops[0], 0)
            self.assertGreaterEqual(tops[-1] + side, h)
            self.assertLessEqual(side, w + 1)


@unittest.skipUnless(HAVE_D2R, "needs D2R 93847's extraction (fxpaths.D2R)")
class Layouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pc = L.pc_hd(sr.pc_hd(pad_ui.load((SRC / sr.PC_HD).read_text("utf-8-sig"))), BOOK)
        cls.pad = L.pad(sr.pad(pad_ui.load((SRC / sr.PAD).read_text("utf-8-sig"))), BOOK)

    def names(self, lay):
        return [w["name"] for w in widgets(lay) if "name" in w]

    def test_close_button_tells_the_pc_sheet(self):
        # plain D2R: the host opens its panel only over a sheet with a CloseButton (sheet_host.cpp PlainFollow)
        top = lambda p: {c.get("name") for c in pad_ui.load((SRC / p).read_text("utf-8-sig"))["children"]}
        self.assertIn("CloseButton", top(sr.PC_HD))
        self.assertNotIn("CloseButton", top(sr.PAD))

    def test_contract_names_present(self):
        self.assertEqual(L.contract_names(BOOK) - set(self.names(self.pc)), set())
        self.assertEqual(L.contract_names(BOOK, pad_layout=True) - set(self.names(self.pad)), set())

    def test_statbook_names_unique(self):
        for lay in (self.pc, self.pad):
            sb = [n for n in self.names(lay) if n.startswith(L.STATBOOK_PREFIXES)]
            self.assertEqual(len(sb), len(set(sb)))

    def test_valid_widgets(self):
        kinds = {"Widget", "ImageWidget", "TextBoxWidget", "ButtonWidget", "InputTextBoxWidget"}
        for lay in (self.pc, self.pad):
            json.loads(json.dumps(lay))
            for w in widgets(lay):
                if str(w.get("name", "")).startswith(L.STATBOOK_PREFIXES):
                    self.assertIn(w["type"], kinds, w["name"])
                    self.assertIn("rect", w["fields"], w["name"])
                    if w["type"] == "ImageWidget":      # the gamepad file is basedOn the PC one: a missing frame is inherited
                        self.assertIn("frame", w["fields"], w["name"])
                    if w["type"] == "ButtonWidget":
                        self.assertEqual(w["fields"]["onClickMessage"], L.CLICK)

    def test_normal_build_shows_no_page(self):
        top = {c.get("name"): c for c in self.pc["children"]}
        for n in ("StatBookPage", "StatBookAll", "SbPageBody"):
            self.assertIs(top[n]["fields"].get("visible"), False, n)
        self.assertNotIn("visible", top["StrengthStat"]["fields"])
        self.assertEqual(top["StatsPanelTitle"]["fields"]["text"], "")
        names = self.names(self.pc)
        self.assertLess(names.index(L.MARKER), names.index("CloseButton"))

    def test_leaves_carry_their_groups_visibility(self):
        def walk(ws, shown):
            for w in ws:
                own = w["fields"].get("visible", True)
                if w.get("children"):
                    yield from walk(w["children"], shown and own)
                else:
                    yield w["name"], shown, own
        for lay in (self.pc, self.pad):
            sb = [c for c in lay["children"] if c.get("name", "").startswith(L.STATBOOK_PREFIXES)]
            leaves = list(walk(sb, True))
            self.assertTrue(leaves)
            for name, shown, own in leaves:
                self.assertTrue(own is False or shown, name)       # under a hidden group: hidden itself
            shown_leaves = {n for n, s, own in leaves if own}
            self.assertIn("SbTab0", shown_leaves)
            self.assertNotIn("SbAll00Cell", shown_leaves)
            self.assertNotIn("SbSearchSlot", shown_leaves)

    def test_hidden_on_pages(self):
        hidden = L.hidden_on_pages(self.pc)
        self.assertIn("StrengthStat", hidden)
        self.assertIn("MxlMagicText", hidden)
        self.assertNotIn("CloseButton", hidden)
        self.assertNotIn("CharacterName", hidden)
        self.assertFalse([n for n in hidden if n.startswith(L.STATBOOK_PREFIXES)])

    def test_rebuild_is_idempotent(self):
        again = L.pc_hd(json.loads(json.dumps(self.pc)), BOOK)
        self.assertEqual(again, self.pc)
        pad_again = L.pad(json.loads(json.dumps(self.pad)), BOOK)
        self.assertEqual(pad_again, self.pad)

    def test_preview_rebuild_restores(self):
        prev = L.pc_hd(json.loads(json.dumps(self.pc)), BOOK, preview=1)
        self.assertIs({c.get("name"): c for c in prev["children"]}["StrengthStat"]["fields"].get("visible"), False)
        self.assertEqual(L.pc_hd(prev, BOOK), self.pc)

    def test_preview_look_leaves_out_hidden(self):
        prev = L.preview_look(L.pc_hd(json.loads(json.dumps(self.pc)), BOOK, preview=1))
        names = set(self.names(prev))
        self.assertIn("SbLine00Heading", names)
        self.assertNotIn("SbAll00Cell", names)
        self.assertNotIn("SbTab0Selected", names)
        self.assertIn("SbTab1Selected", names)
        top = {c.get("name"): c for c in prev["children"]}
        self.assertEqual(top["StrengthStat"]["fields"]["rect"]["x"], L.OFF_PANEL)
        self.assertNotEqual(top["CharacterName"]["fields"]["rect"]["x"], L.OFF_PANEL)

    def test_preview_base_round_trip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            p = data / L.LAYOUTS / L.PC_HD
            p.parent.mkdir(parents=True)
            normal = json.dumps(self.pc)
            p.write_text(normal, "utf-8")
            self.assertEqual(L.preview_base(data, L.PC_HD, p), normal)
            L.keep_preview_base(data, L.PC_HD, normal, "PREVIEW")
            p.write_text("PREVIEW", "utf-8")
            self.assertEqual(L.preview_base(data, L.PC_HD, p), normal)       # the preview's own text: start from the base
            p.write_text("REBUILT", "utf-8")
            self.assertEqual(L.preview_base(data, L.PC_HD, p), "REBUILT")    # rewritten since: the new file wins
            L.drop_preview_base(data, L.PC_HD)
            self.assertFalse((L._base_dir(data) / L.PC_HD).exists())

    def test_contract_json(self):
        c = L.contract_json(BOOK)
        self.assertEqual(len(c["pc"]["tabs"]), len(L.tabs(BOOK)))
        self.assertEqual(len(c["pad"]["allRowRects"]), L.PAD_ALL_ROWS)
        self.assertEqual(c["pc"]["tones"], [t for t, _ in L.TONES])
        self.assertEqual(c["pc"]["toggle"], [*L.TOGGLE_PC, L.TOGGLE, L.TOGGLE])
        self.assertNotIn("toggle", c["pad"])


class Side(unittest.TestCase):
    """The side panel (option B) and the top / side toggle."""

    def setUp(self):
        self.lay = L.side_layout(BOOK)
        self.names = [w.get("name") for w in widgets(self.lay)]

    def test_panel(self):
        f = self.lay["fields"]
        self.assertEqual(self.lay["name"], "statbook/SbSidePanel")
        self.assertFalse(L.SIDE_LOCAL_ID.startswith("StatBook"))
        self.assertEqual((f["rect"]["x"], f["rect"]["width"], f["rect"]["height"]), (L.SIDE_X, L.SIDE_W, L.SIDE_H))
        self.assertEqual(L.SIDE_X, 236 + 1162)   # right of the sheet

    def test_names(self):
        need = L.contract_names(BOOK) - {"SbTab0", "SbTab0Selected", "SbTab0SelectedLabel"}
        self.assertEqual(need - set(self.names), set())
        self.assertNotIn("SbTab0", self.names)            # no Character tab
        named = [n for n in self.names if n]
        self.assertEqual(len(named), len(set(named)))

    def test_contract(self):
        c = L.contract_json(BOOK)["side"]
        self.assertEqual(c["tabs"][0], [0, 0, 0, 0])
        self.assertEqual(len(c["tabs"]), len(L.tabs(BOOK)))
        self.assertEqual(c["toggle"], [*L.TOGGLE_SIDE, L.TOGGLE, L.TOGGLE])

    def test_toggle_clear_of_everything(self):
        """The toggle in the page's top-right corner touches no tab, no search box, no All Stats row, on both hosts."""
        def hit(a, b):
            return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]
        for key in ("pc", "side"):
            c = L.contract_json(BOOK)[key]
            t = c["toggle"]
            for r in c["tabs"] + c["allRowRects"] + [c["search"]]:
                self.assertFalse(hit(t, r), (key, r))
            for r in c["lineRects"][0 if key == "side" else 1:]:   # on the sheet over line 0's heading rule only
                self.assertFalse(hit(t, r), (key, r))
        x, y, w, _h = L.contract_json(BOOK)["pc"]["toggle"]
        self.assertLessEqual(x + w, L.PC.body[2])                 # inside the sheet frame's inner bevel

    def test_first_line_of_every_page_is_a_heading(self):
        """On the sheet the toggle sits over the right end of line 0, which must be a heading (its rule fades there)."""
        for pid, _t, recs in BOOK["pages"]:
            self.assertEqual(L.page_lines(recs)[0][0], "heading", pid)

    def test_tabs_and_lines_inside_the_page(self):
        c = L.contract_json(BOOK)["side"]
        for x, y, w, h in c["tabs"][1:] + c["lineRects"] + c["allRowRects"]:
            self.assertLessEqual(y + h, L.SIDE_PAGE_BOTTOM)
            self.assertLessEqual(x + w, L.SIDE_W - L.SIDE_INNER[2])

    def test_texts_fit(self):
        self.assertEqual(L.fit_problems(BOOK, L.SIDE), [])


class Art(unittest.TestCase):
    def strip(self, w, h, seed):
        from PIL import Image
        rnd = random.Random(seed)
        im = Image.new("RGBA", (w, h))
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256), 255) for _ in range(w * h)])
        return im

    def test_join_keeps_width(self):
        a, b = self.strip(60, 20, 1), self.strip(50, 20, 2)
        j = L.join_h(a, b, random.Random(0))
        self.assertEqual(j.size, (60 + 50 - L.OV, 20))

    def test_fit_width_and_height(self):
        src = self.strip(120, 30, 3)
        for w in (40, 119, 300, 997):
            self.assertEqual(L.fit_width(src, w, 14, 22, random.Random(1)).size, (w, 30))
        self.assertEqual(L.fit_width(src, 500, 14, 22, random.Random(1), centre=True).size[0], 500)
        self.assertEqual(L.fit_height(src, 77, 5, 5, random.Random(1)).size, (120, 77))

    def test_fit_width_keeps_caps(self):
        src = self.strip(120, 30, 4)
        out = L.fit_width(src, 400, 14, 22, random.Random(2))
        self.assertEqual(out.crop((0, 0, 14 - 2, 30)).tobytes(), src.crop((0, 0, 14 - 2, 30)).tobytes())
        self.assertEqual(out.crop((400 - 22 + 2, 0, 400, 30)).tobytes(), src.crop((120 - 22 + 2, 0, 120, 30)).tobytes())


if __name__ == "__main__":
    unittest.main()
