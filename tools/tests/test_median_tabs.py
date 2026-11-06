"""The stash's MEDIAN / ORBS tabs and the Materials tab's Median page (tools/median_tabs.py), and the plugin / layout pair check
of tools/install_mod.py."""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import install_mod  # noqa: E402
import median_stash  # noqa: E402
import median_tabs as mt  # noqa: E402
import ui_layouts  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "plugin" / "src" / "medtab_names.h"
BUILT = ROOT / "work" / "mod" / "data"


def fake_layout():
    page = {"type": "Widget", "children": []}
    return {"type": "Widget", "name": "root", "children": [
        {"type": "TabBarWidget", "name": "BankTabs", "fields": {"tabCount": 5, "textStrings": ["a", "b", "c", "d", "e"]}},
        {**page, "name": "advancedstash_gems"}, {**page, "name": "advancedstash_materials", "children": []},
        {**page, "name": "advancedstash_runes", "children": [{"type": "AdvancedStashSlotWidget", "name": "r01",
                                                              "fields": {"itemCode": "r01"}}]}]}


def slots(node, out=None):
    out = [] if out is None else out
    if node.get("type") == "AdvancedStashSlotWidget":
        out.append(node)
    for c in node.get("children", []):
        slots(c, out)
    return out


def overlaps(rects):
    return [(a, b) for i, (a, (ax, ay, aw, ah)) in enumerate(rects) for b, (bx, by, bw, bh) in rects[:i]
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah]


class Codes(unittest.TestCase):
    def test_sets(self):
        self.assertEqual(len(mt.SINGLES), 55)
        self.assertEqual(len(mt.SHRINES), 20)
        self.assertTrue(all(c.endswith("0+") for c in mt.SHRINES))  # full charge only (owner: option D)
        self.assertEqual(len(mt.ORBS), 100)
        self.assertEqual(len(mt.MAT_MEDIAN), 29)
        self.assertEqual(len(mt.CODES), 204)
        self.assertFalse(set(mt.CODES) & set(median_stash.CODES))

    def test_at_codes(self):
        self.assertEqual(mt.AT_CODES, ["b@b", "c@c", "!@B", "l@l", "m@m", "o@o", "p@p", "q@q", "u@v"])
        self.assertFalse([c for c in mt.CODES if mt.PLACEHOLDER in c])
        for c in mt.CODES:
            lc = mt.layout_code(c)
            self.assertNotIn("@", lc)
            self.assertLessEqual(len(lc), 4)
            self.assertEqual(mt.real_code(lc), c)
        self.assertEqual(mt.real_code("r_x"), "r_x")  # only the 9 placeholders map back

    def test_no_item_code_has_the_placeholder(self):
        tables = [BUILT / "global" / "excel" / f"{t}.txt" for t in ("misc", "weapons", "armor")]
        if not all(p.exists() for p in tables):
            self.skipTest("no built mod (tools/build.py)")
        for p in tables:
            lines = p.read_text("latin-1").splitlines()
            ci = lines[0].split("\t").index("code")
            codes = {f[ci] for f in (line.split("\t") for line in lines[1:]) if len(f) > ci}
            self.assertFalse([c for c in codes if mt.PLACEHOLDER in c], p.name)


class Layout(unittest.TestCase):
    def check(self, lay):
        self.assertEqual(mt.find(lay, "BankTabs")["fields"]["tabCount"], 7)
        self.assertEqual(mt.find(lay, "BankTabs")["fields"]["textStrings"][5:], ["Median", "Orbs"])
        self.assertIsNotNone(mt.find(lay, mt.LAYOUT_MARK))
        codes = [mt.real_code(s["fields"]["itemCode"]) for s in slots(lay)]
        self.assertTrue(set(mt.CODES) <= set(codes))
        for s in slots(lay):
            self.assertNotIn("@", s["fields"]["itemCode"])
            self.assertNotIn("@", s["name"])  # the plugin finds the slots by name
            self.assertLessEqual(len(s["fields"]["itemCode"]), 4)
        runes = [c["name"] for c in mt.find(lay, "advancedstash_runes")["children"]]
        mats = [c["name"] for c in mt.find(lay, "advancedstash_materials")["children"]]
        self.assertTrue({mt.layout_code(c) for c in mt.SINGLES + mt.SHRINES + mt.ORBS} <= set(runes))
        self.assertTrue({mt.layout_code(c) for c in mt.MAT_MEDIAN} <= set(mats))
        # D2R casts every direct child of a page to a slot: pictures and selectors are panel siblings
        for page in ("advancedstash_runes", "advancedstash_materials"):
            self.assertEqual({c["type"] for c in mt.find(lay, page)["children"]} - {"AdvancedStashSlotWidget"}, set(), page)
        for name in ("medtab_median_bg", "medtab_orbs_bg", "medtab_mat_bg", "medtab_sel_vanilla", "medtab_sel_median"):
            w = next((c for c in lay["children"] if c.get("name", "").startswith(name)), None)
            self.assertIsNotNone(w, name)
            self.assertIs(w["fields"]["visible"], False, name)  # the plugin shows them

    def test_fake_layout(self):
        lay = mt.apply_hd(fake_layout())
        self.check(lay)
        self.assertEqual(mt.find(lay, "BankTabs")["fields"]["tabSize"], {"x": mt.HD_TAB_W, "y": 72})
        with self.assertRaises(ValueError):
            mt.apply_hd(lay)  # twice

    def test_d2r_layout(self):
        if not (ui_layouts.BASE_UI / "layouts" / "bankexpansionlayouthd.json").exists():
            self.skipTest("no D2R baseline (py -3 tools/hd_ui.py baseline <extraction>)")
        from rotw_stash_legacy import lenient_json
        lay = mt.apply_hd(median_stash.apply(lenient_json(ui_layouts.baseline("bankexpansionlayouthd.json"))))
        self.check(lay)
        tabs = mt.find(lay, "BankTabs")["fields"]
        self.assertEqual(len(tabs["textStrings"]), 7)
        self.assertEqual(len(tabs["disabledFrames"]), 7)

    def test_pages(self):
        for group in (mt.median_slots(), mt.orbs_slots(), mt.mat_slots()):
            self.assertEqual(overlaps(group), [])
        x0, y0 = mt.GRID
        for _c, (x, y, w, h) in mt.median_slots() + mt.orbs_slots():
            self.assertTrue(x0 <= x and x + w <= x0 + 10 * mt.SLOT and y0 <= y and y + h <= y0 + 10 * mt.SLOT)
        self.assertEqual(sum(h // mt.SLOT for _c, (_x, _y, _w, h) in mt.median_slots()), 95)  # 55 + 20 x 2 cells
        for _c, (x, y, w, h) in mt.mat_slots():
            self.assertLessEqual(y + h, mt.MAT_FIELD[3])  # above the cube plinth: the cube stays

    def test_check_misc(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "global" / "excel" / "misc.txt"
            p.parent.mkdir(parents=True)
            rows = ["name\tcode\tAdvancedStashStackable"] + [f"x\t{c}\t1" for c in mt.CODES]
            p.write_text("\n".join(rows), "latin-1")
            report = []
            mt.check_misc(Path(d), report)
            self.assertIn("204", report[0])
            p.write_text("\n".join(rows[:-1] + [f"x\t{mt.CODES[-1]}\t"]), "latin-1")
            with self.assertRaises(ValueError):
                mt.check_misc(Path(d), [])


class Header(unittest.TestCase):
    def test_header_is_current(self):
        lays = [BUILT / "global" / "ui" / "layouts" / f for f in ("bankexpansionlayouthd.json", "bankexpansionlayout.json")]
        if not all(p.exists() and mt.LAYOUT_MARK in p.read_text("utf-8") for p in lays):
            self.skipTest("no built mod with the Median tabs (tools/build.py)")
        self.assertEqual(HEADER.read_text("utf-8"), mt.header(BUILT), "run `py -3 tools/median_tabs.py header`")

    def test_header_tables(self):
        text = HEADER.read_text("utf-8")
        self.assertIn(f'LayoutMark[] = "{mt.LAYOUT_MARK}"', text)
        self.assertIn(f"Placeholder = '{mt.PLACEHOLDER}'", text)
        at = re.search(r"AtCodes\[\] = \{(.*?)\};", text, re.S).group(1)
        self.assertEqual(json.loads("[" + at.strip().rstrip(",") + "]"), [mt.layout_code(c) for c in mt.AT_CODES])
        self.assertNotIn("@", text)


class Pair(unittest.TestCase):
    def test_pair(self):
        with tempfile.TemporaryDirectory() as d:
            data, dll = Path(d) / "data", Path(d) / "mxl2012-core.dll"
            lay = data / "global" / "ui" / "layouts" / "bankexpansionlayouthd.json"
            lay.parent.mkdir(parents=True)
            self.assertEqual(install_mod.medtab_pair_problem(data, dll), "")  # no stash layout of ours
            lay.write_text(json.dumps(fake_layout()), "utf-8")
            self.assertEqual(install_mod.medtab_pair_problem(data, dll), "")  # 5 tabs: any plugin
            lay.write_text(json.dumps(mt.apply_hd(fake_layout())), "utf-8")
            self.assertIn("no plugin", install_mod.medtab_pair_problem(data, dll))
            dll.write_bytes(b"MZ older plugin")
            self.assertIn("no medtab part", install_mod.medtab_pair_problem(data, dll))
            dll.write_bytes(b"MZ ... " + mt.LAYOUT_MARK.encode() + b"\0")
            self.assertEqual(install_mod.medtab_pair_problem(data, dll), "")
            mod = Path(d) / "mod"
            shutil.copytree(data, mod / "x.mpq" / "data")
            with self.assertRaises(SystemExit):
                install_mod.write_mod_files(mod, "x", "x/", Path(d) / "missing.dll")


if __name__ == "__main__":
    unittest.main()
