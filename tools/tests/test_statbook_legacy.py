"""The Stat Book in legacy graphics (tools/statbook_legacy.py): the classic sheet widened with the book's contract widgets, the
classic side panel, their geometry for the plugin, the fit in D2R's classic fonts and the art (shipped or stock)."""
import json
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
import statbook_legacy as SL  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
D2R = Path(fxpaths.D2R)
SRC = D2R / "data" / sr.LAYOUTS / sr.LEGACY
HAVE_D2R = SRC.is_file()
BOOK = L.read_book(L.full_book_text())
HOST = ROOT / "statbook" / "src" / "sheet_host.cpp"


def widgets(node):
    yield node
    for c in node.get("children", []):
        yield from widgets(c)


def boxes(side=False):
    """Tab boxes from a fixed width per label (the build measures font6)."""
    return SL.tab_boxes([6 * len(t) for t in SL.tab_texts(BOOK, side, lambda s: 6 * len(s))])


def cpp_list(name: str) -> list[str]:
    m = re.search(r"%s\[\]\s*=\s*\{(.*?)\};" % name, HOST.read_text("utf-8"), re.S)
    return re.findall(r'"([^"]+)"', m.group(1))


class Geometry(unittest.TestCase):
    def test_tabs_fill_the_strip(self):
        for side in (False, True):
            b = boxes(side)
            self.assertEqual(b[0][0], 0)
            self.assertEqual(sum(w for _x, w in b), SL.PANEL_W)
            for (x0, w0), (x1, _w1) in zip(b, b[1:]):
                self.assertEqual(x0 + w0, x1)

    def test_side_has_no_character_tab(self):
        g = SL.geometry(BOOK, boxes(True), True)
        self.assertEqual(g["tabs"][0], [0, 0, 0, 0])
        self.assertEqual(len(g["tabs"]), len(L.tabs(BOOK)))
        self.assertEqual(g["origin"], [SL.SIDE_X, 0])
        self.assertEqual(SL.geometry(BOOK, boxes(), False)["origin"], [0, 0])
        self.assertTrue(all(t[3] in (0, SL.TAB_H) for t in g["tabs"]))

    def test_slots_inside_the_body_above_close(self):
        x0, y0, x1, y1 = SL.BODY
        close_top = SL.CLOSE[1]
        g = SL.geometry(BOOK, boxes(), False)
        for x, y, w, h in g["lineRects"] + g["allRowRects"] + [g["search"]]:
            self.assertGreaterEqual(x, x0)
            self.assertLessEqual(x + w, x1)
            self.assertGreaterEqual(y, y0)
            self.assertLessEqual(y + h, close_top)
        self.assertEqual(len(g["lineRects"]), L.LINES)
        self.assertEqual(2 * sum(SL.HALF) + SL.HALF_GAP, SL.LINE_W)
        self.assertGreaterEqual(SL.HALF_GAP, 0)
        self.assertEqual(sum(SL.FULL), SL.LINE_W)

    def test_longest_page_fits(self):
        most = max(len(L.page_lines(recs)) for _p, _t, recs in BOOK["pages"])
        self.assertLessEqual(most, L.LINES)

    def test_inside_the_classic_panel(self):
        # D2R draws a classic left panel only inside its 320 x 432 area: everything of the book is in it
        tx, ty = SL.TOGGLE_XY
        self.assertGreaterEqual(tx, SL.CLASS_BOX[0] + SL.CLASS_BOX[1])     # right of the class box, in the name row
        self.assertLessEqual(tx + SL.TOGGLE, SL.PANEL_W - 4)
        self.assertGreaterEqual(ty, SL.TAB_H)
        self.assertLessEqual(ty + SL.TOGGLE, SL.HEAD_H)
        ax, ay, ah = SL.ADVANCED
        self.assertGreaterEqual(ax, 138)                                  # right of the stat points plate
        self.assertLessEqual(ay + ah, SL.CLOSE[1] + SL.CLOSE[3])
        self.assertGreaterEqual(SL.LINE_Y, SL.HEADER_H)
        self.assertLessEqual(SL.LINE_X + SL.LINE_W, SL.PANEL_W)

    def test_short_labels(self):
        short = SL.short_labels()
        self.assertEqual(short["Minion Resistances"], "Minion Res.")
        self.assertFalse([b for b in short.values() if b.endswith(".s") or "Dmg" in b], "clean short forms")
        self.assertEqual(SL.short_label("Life Stolen per Hit"), "Life Leech")
        self.assertEqual(SL.short_label("Strength"), "Strength")

    def test_host_reads_both(self):
        text = HOST.read_text("utf-8")
        self.assertIn('ParseGeometry(json, "legacy")', text)
        self.assertIn('ParseGeometry(json, "legacyside")', text)
        self.assertIn(SL.MARKER, text)
        self.assertIn(SL.SIDE_FILE, text)


@unittest.skipUnless(HAVE_D2R, "D2R extraction not found")
class Layouts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = sr.legacy(pad_ui.load(SRC.read_text("utf-8-sig")))
        cls.lay = SL.legacy_sheet(json.loads(json.dumps(cls.base)), BOOK, boxes())
        cls.side = SL.side_layout(BOOK, boxes(True))

    def names(self, lay):
        return [w["name"] for w in widgets(lay) if "name" in w]

    def test_contract_names_present(self):
        self.assertEqual(SL.contract_names(BOOK) - set(self.names(self.lay)), set())
        side_names = set(self.names(self.side))
        missing = (SL.contract_names(BOOK) - {"SbTab0", "SbTab0Selected", "SbTab0SelectedLabel", SL.ADVANCED_NAME, SL.MARKER}) - side_names
        self.assertEqual(missing, set())
        self.assertLessEqual({"SbSideBody", "SbSideTitle", "SbSideHeading"}, side_names)

    def test_same_groups_as_hd(self):
        # WidgetService handles are paths: a name sits in the same group in HD and legacy (sheet_host_logic.h ParentOf)
        def parents(lay):
            out = {}

            def walk(ws, parent):
                for w in ws:
                    if "name" in w:
                        out[w["name"]] = parent
                    walk(w.get("children", []), w.get("name", parent))
            walk(lay["children"], "")
            return out
        hd = parents(L.pc_hd(sr.pc_hd(pad_ui.load((D2R / "data" / sr.LAYOUTS / sr.PC_HD).read_text("utf-8-sig"))), BOOK))
        lg = parents(self.lay)
        for n in SL.contract_names(BOOK) & L.contract_names(BOOK):
            if n.endswith("Cell") or n.endswith("HeadingRule") or n.startswith("SbAllScroll"):
                continue                                      # art pieces: groups of two images in legacy, never shown by name
            self.assertEqual(lg.get(n), hd.get(n), n)

    def test_unique_and_valid(self):
        kinds = {"Widget", "ImageWidget", "TextBoxWidget", "ButtonWidget", "InputTextBoxWidget", "ClickCatcherWidget"}
        for lay in (self.lay, self.side):
            sb = [n for n in self.names(lay) if n.startswith(L.STATBOOK_PREFIXES)]
            self.assertEqual(len(sb), len(set(sb)))
            json.loads(json.dumps(lay))
            for w in widgets(lay):
                n = str(w.get("name", ""))
                if not n.startswith(L.STATBOOK_PREFIXES):
                    continue
                self.assertIn(w["type"], kinds, n)
                self.assertIn("rect", w["fields"], n)
                if w["type"] == "ImageWidget":
                    self.assertIn("frame", w["fields"], n)
                if w["type"] == "ButtonWidget":
                    self.assertEqual(w["fields"]["onClickMessage"], L.CLICK, n)
                if w["type"] in ("TextBoxWidget", "InputTextBoxWidget"):
                    self.assertIn(w["fields"]["fontType"], ("6pt", "8pt", "16pt"), n)
                    if w["type"] == "TextBoxWidget":
                        self.assertIsInstance(w["fields"]["style"]["fontColor"], dict, n)   # _profilesd lacks most colours

    def test_sheet_kept_name_row_moved_rebuild_same(self):
        self.assertEqual(self.lay["fields"]["rect"], self.base["fields"]["rect"])
        old = {c.get("name"): c for c in self.base["children"]}
        for c in self.lay["children"]:
            n = c.get("name")
            if n in old and n not in ("CharacterName", "ClassInfo"):
                self.assertEqual(c.get("fields", {}).get("rect"), old[n].get("fields", {}).get("rect"), n)
        top = {c.get("name"): c for c in self.lay["children"]}
        self.assertEqual(top["CharacterName"]["fields"]["rect"]["y"], SL.NAME_Y - 3)
        names = [c.get("name") for c in self.lay["children"]]
        self.assertEqual(names.index("SbHead"), names.index("background") + 1)   # under D2R's texts
        again = SL.legacy_sheet(json.loads(json.dumps(self.lay)), BOOK, boxes())
        self.assertEqual(again, self.lay)

    def test_side_stone_not_in_page_body(self):
        # the side host hides SbPageBody (bare in HD too): the side stone is part of SbSideBody
        top = {c.get("name"): c for c in self.side["children"]}
        self.assertFalse(top["SbPageBody"].get("children"))
        kids = [c.get("name") for c in top["SbSideBody"]["children"]]
        self.assertIn("SbSideStone", kids)

    def test_every_widget_inside_the_panel(self):
        def walk(ws, ox, oy):
            for w in ws:
                rr = w.get("fields", {}).get("rect", {})
                if not all(isinstance(rr.get(k, 0), int) for k in ("x", "y", "width", "height")):
                    continue                                   # D2R's own $Profile sizes
                x, y = ox + rr.get("x", 0), oy + rr.get("y", 0)
                n = str(w.get("name", ""))
                if n.startswith(L.STATBOOK_PREFIXES) and isinstance(rr.get("width"), int):
                    self.assertTrue(0 <= x and x + rr["width"] <= SL.PANEL_W + 2 and 0 <= y and y + rr["height"] <= SL.PANEL_H, n)
                walk(w.get("children", []), x, y)
        for lay in (self.lay, self.side):
            walk(lay["children"], 0, 0)

    def test_advanced_arrow_on_the_sheet(self):
        adv = [c for c in self.lay["children"] if c.get("name") == SL.ADVANCED_NAME]
        self.assertEqual(len(adv), 1)
        self.assertEqual(adv[0]["fields"]["onClickMessage"], L.CLICK)       # found by its rect (geometry "advanced")
        x, y, w, h = SL.geometry(BOOK, boxes(), False)["advanced"]
        self.assertEqual((x, y, h), (adv[0]["fields"]["rect"]["x"], adv[0]["fields"]["rect"]["y"], SL.ADVANCED[2]))
        names = self.names(self.lay)
        self.assertLess(names.index(L.MARKER), names.index("CloseButton"))
        top = [c.get("name") for c in self.lay["children"]]
        for n in ("SbPageBody", "StatBookPage", "StatBookAll"):    # after (over) the hidden page body's ClickCatcher
            self.assertLess(top.index(n), top.index(SL.ADVANCED_NAME))

    def test_normal_build_shows_no_page(self):
        top = {c.get("name"): c for c in self.lay["children"]}
        for n in ("StatBookPage", "StatBookAll", "SbPageBody"):
            self.assertIs(top[n]["fields"].get("visible"), False, n)
        self.assertNotIn("visible", top["StrengthStat"]["fields"])

    def test_host_hides_what_the_pages_cover(self):
        # sheet_host.cpp KeepLegacy / HideByNameLegacy against the classic layout's top level
        hidden = set(SL.hidden_on_pages(self.lay))
        keep = set(cpp_list("KeepLegacy"))
        by_name = set(cpp_list("HideByNameLegacy"))
        self.assertEqual(keep & hidden, set())
        self.assertLessEqual(SL.KEEP_ON_PAGES, keep)
        tops = {c.get("name") for c in self.lay["children"] if c.get("name")}
        self.assertEqual(hidden - by_name - {"MxlSheetLegacy"}, set())          # the marker is an empty widget
        self.assertEqual(by_name - tops, set())
        self.assertIn(SL.ADVANCED_NAME, by_name)                         # the arrow only on the Character tab
        self.assertIn("background", keep)                                 # the header band stays above the page

    def test_every_image_shipped_or_stock(self):
        own = {"Body", "BodyLow", "Band", "Head", "Cells", "Tabs", "TabsSelected", "SideTabs", "SideTabsSelected", "TabsToggle", "Advanced", "Go"}
        side = json.loads(json.dumps(self.side))
        for t in side["children"]:
            if t.get("name") == "StatBookTabs":
                for b in t["children"]:
                    fn = b["fields"].get("filename", "")
                    if fn.endswith(("\\Tabs", "\\TabsSelected")):
                        b["fields"]["filename"] = fn.replace("\\Tabs", "\\SideTabs")
        built = ROOT / "work" / "mod" / "data" / SL.ART_DIR
        for lay in (self.lay, side):
            for w in widgets(lay):
                fn = w.get("fields", {}).get("filename")
                if not isinstance(fn, str) or fn.startswith("$"):
                    continue
                if fn.startswith(SL.ART):
                    art = fn[len(SL.ART):]
                    self.assertIn(art, own, w.get("name"))
                    if built.is_dir():
                        self.assertTrue((built / (art.lower() + ".dc6")).is_file(), art)
                else:                                       # D2R's own classic art (the sheet's buttons, sockets)
                    p = D2R / "data" / "global" / "ui" / (fn.replace("\\", "/").lower() + ".dc6")
                    self.assertTrue(p.is_file() or not (D2R / "data" / "global" / "ui" / "panel").is_dir(), fn)

    def test_built_art_one_height_per_file(self):
        # D2R draws a classic frame bottom-aligned to the DC6's frame 0: every frame of a file is as high as frame 0
        import dc6
        built = ROOT / "work" / "mod" / "data" / SL.ART_DIR
        files = sorted(built.glob("*.dc6")) if built.is_dir() else []
        if not files:
            self.skipTest("no built mod")
        for f in files:
            heights = {fr[1] for fr in dc6.read_dc6(f)}
            self.assertEqual(len(heights), 1, f.name)

    def test_built_files(self):
        data = ROOT / "work" / "mod" / "data"
        geo = data / L.ART_DIR / "statbook-layout.json"
        if not (data / L.ART_DIR / SL.SIDE_FILE).is_file():
            self.skipTest("no built mod")
        g = json.loads(geo.read_text("utf-8"))
        self.assertEqual(set(g) >= {"pc", "pad", "side", "legacy", "legacyside"}, True)
        lay = pad_ui.load((data / L.LAYOUTS / SL.LEGACY).read_text("utf-8-sig"))
        tabs = {w["name"]: w["fields"]["rect"] for w in widgets(lay) if re.fullmatch(r"SbTab\d+", w.get("name", ""))}
        for i, (x, y, w, h) in enumerate(g["legacy"]["tabs"]):
            self.assertEqual((tabs["SbTab%d" % i]["x"], tabs["SbTab%d" % i]["y"]), (x, y))


@unittest.skipUnless(HAVE_D2R, "D2R extraction not found")
class Fonts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import rotw_stash_legacy as rsl
        d2r = rsl.D2R(D2R, use_cache=True)
        cls.f6, cls.f8 = d2r.font("font6"), d2r.font("font8")
        if cls.f6 is None or cls.f8 is None:
            raise unittest.SkipTest("classic fonts not found")

    def test_every_text_fits(self):
        self.assertEqual(SL.fit_problems(BOOK, self.f6, self.f8), [])

    def test_short_forms_only_where_needed(self):
        # a half row's label keeps its full text when it fits; every short form is for a label that does not
        halves = {row[1] for _p, _t, recs in BOOK["pages"] for ln in L.page_lines(recs) if ln[0] == "pair" for row in ln[1:] if row}
        for full, short in SL.short_labels().items():
            self.assertLessEqual(self.f6.width(short), SL.HALF[0] - 4, short)
            # these fit but take the form of their siblings (Melee / Missile Defense, Life / Mana Leech, the four Spells)
            if full in halves and full not in ("Defense vs. Melee", "Life Stolen per Hit", "Fire Spell Damage", "Cold Spell Damage"):
                self.assertGreater(self.f6.width(full), SL.HALF[0] - 4, full)

    def test_tab_labels_fit_their_tabs(self):
        for side in (False, True):
            texts = SL.tab_texts(BOOK, side, self.f6.width)
            b = SL.tab_boxes([self.f6.width(t) for t in texts])
            for t, (_x, w) in zip(texts, b):
                self.assertLessEqual(self.f6.width(t) + 8, w, t)


class Plain(unittest.TestCase):
    """The standalone plugin's classic panels (statbook_plain_legacy.h) for plain D2R."""
    BOOK = L.plain_book()

    def lay(self):
        return SL.plain_sheet(self.BOOK, SL.tab_boxes([6 * len(t) for t in SL.tab_texts(self.BOOK, False, lambda s: 6 * len(s))]))

    @unittest.skipUnless(HAVE_D2R, "needs D2R's classic fonts")
    def test_header_is_current(self):
        self.assertEqual(SL.PLAIN_HEADER.read_text("utf-8"), SL.plain_header_text(D2R),
                         "statbook/src/statbook_plain_legacy.h is out of date: py -3 -I tools/statbook_legacy.py plain")

    def test_panel_and_contract(self):
        lay = self.lay()
        self.assertEqual(lay["name"], L.PLAIN_NAME)
        self.assertEqual(lay["fields"]["rect"], {"x": -SL.PANEL_W, "y": -240, "width": SL.PANEL_W, "height": SL.PANEL_H})
        names = {w.get("name") for w in widgets(lay)}
        want = {n for n in SL.contract_names(self.BOOK) if not n.startswith("SbSide")}
        self.assertEqual(want - names, set())
        self.assertTrue({SL.PLAIN_NAME_TEXT, SL.PLAIN_CLASS_TEXT, "SbClose", "SbHead"} <= names)

    def test_no_click_catcher_close_on_the_pages(self):
        lay = self.lay()
        self.assertFalse([w for w in widgets(lay) if w.get("type") == "ClickCatcherWidget"])
        body = next(w for w in lay["children"] if w["name"] == "SbPageBody")
        close = next(w for w in body["children"] if w["name"] == "SbClose")
        self.assertEqual(close["fields"]["onClickMessage"], "CharacterStatsPanelMessage:Close")
        order = [w["name"] for w in lay["children"]]
        self.assertGreater(order.index(SL.ADVANCED_NAME), order.index("StatBookAll"))

    def test_art_list_is_every_dc6_named(self):
        side = SL.side_layout(self.BOOK, SL.tab_boxes([6 * len(t) for t in SL.tab_texts(self.BOOK, True, lambda s: 6 * len(s))]))
        names = SL.plain_art_names((self.lay(), side))
        text = SL.PLAIN_HEADER.read_text("utf-8")
        self.assertEqual(re.findall(r'"([a-z]+\.dc6)"', text), names)

    def test_host_registers_and_fills(self):
        host = HOST.read_text("utf-8")
        for s in ("statbook_plain::LayoutLegacy", "statbook_plain::SideLayoutLegacy", "statbook_plain::GeometryLegacy",
                  "statbook_plain::LegacyArt", "statbook_plain::NameText", "statbook_plain::ClassText"):
            self.assertIn(s, host)


if __name__ == "__main__":
    unittest.main()
