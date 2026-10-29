"""Unit tests of tools/shared_icons.py (the shared skill icon sheet in pairs) and the parts of skill_icons.py /
skill_icon_check.py that use its plan, on synthetic data (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_shared_icons.py" """
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import dc6  # noqa: E402
import shared_icons as si  # noqa: E402
import skill_icon_check  # noqa: E402
import skill_icons  # noqa: E402
from txt_migrate import write_tsv  # noqa: E402

PAL = [(i, 255 - i, i // 2) for i in range(256)]
DH = ["skilldesc", "SkillPage", "SkillRow", "SkillColumn", "ListRow", "IconCel", "str name"]
SH = ["skill", "*Id", "charclass", "skilldesc"]


def tsv(*lines: str) -> str:
    """Donor table text: fields split by '|' (the header line by spaces)."""
    return "".join(("\t".join(ln.split()) if ln.startswith("skilldesc ") else ln.replace("|", "\t")) + "\n" for ln in lines)


def solid(w: int, h: int, index: int) -> tuple:
    blk = bytearray()
    for _ in range(h):
        blk += bytes([w]) + bytes([index]) * w + b"\x80"
    return (w, h, 0, 0, bytes(blk))


def bank():
    """Built-table style rows: Median's shared rows, a class row an item skill shares, a vanilla row past the sheet,
    a D2R-only row, a row without IconCel, an unresolved monster row."""
    d = [["attack", "0", "0", "0", "0", "3", "sAttack"],
         ["throw", "0", "0", "0", "0", "5", "sThrow"],
         ["moonqueen", "2", "1", "3", "2", "60", "sMoon"],
         ["fire wall", "1", "2", "1", "1", "30", "sFW"],
         ["interact", "0", "0", "0", "0", "2", "sInt"],
         ["mxl_blank", "", "", "", "", "", ""],
         ["hard_aura", "0", "0", "0", "0", "56", "sHard"]]
    s = [["Attack", "0", "", "attack"], ["Throw", "1", "", "throw"], ["Moon Queen", "2", "ama", "moonqueen"],
         ["Item Moon Queen", "3", "", "moonqueen"], ["Fire Wall", "4", "", "fire wall"], ["Interact", "5", "", "interact"],
         ["Blank", "6", "", "mxl_blank"], ["Hard Aura", "7", "", "hard_aura"], ["Hidden", "8", "war", "attack"]]
    return [DH, [list(r) for r in d], SH, [list(r) for r in s]]


MEDIAN = {"attack": set(), "throw": set(), "moonqueen": {"ama"}, "fire wall": set(), "mxl_blank": set(), "hard_aura": set()}
D2R = {"fire wall": ("sor", 30, 60), "interact": ("", 2, 40), "attack": ("", 2, 40)}
TIERS = {"Attack": 1, "Throw": 1, "Item Moon Queen": 2, "Fire Wall": 2, "Hard Aura": 4}
CELS = {"attack": 3, "throw": 5, "moonqueen": 60, "fire wall": 30, "mxl_blank": None, "hard_aura": 56}


class PlanTests(unittest.TestCase):
    def plan(self):
        dh, d, sh, s = bank()
        return si.make_plan({"": (dh, d, sh, s)}, MEDIAN, 25, D2R, TIERS)

    def test_sources(self):
        p = self.plan()
        icons = [(i.origin, i.sheet, i.cel) for i in p.icons]
        # Median's shared frames first (fallback "?" 0, attack 3, throw 5), then the class and D2R frames
        self.assertEqual(icons, [("mxl", "", 0), ("mxl", "", 3), ("mxl", "", 5), ("d2r", "sor", 30), ("mxl", "ama", 60)])
        self.assertEqual(p.skills["Attack"]["cel"], 2)          # icon 1 -> frames 2, 3 (pressed = the same picture)
        self.assertEqual(p.skills["Throw"]["cel"], 4)
        self.assertEqual(p.skills["Fire Wall"], {"row": "fire wall", "cel": 6, "method": "vanilla row", "tier": 2})
        self.assertEqual(p.skills["Item Moon Queen"]["row"], "moonqueen~shared")
        self.assertEqual(p.skills["Item Moon Queen"]["cel"], 8)
        self.assertEqual(p.skills["Hard Aura"]["cel"], 0)        # unresolved -> the "?" pair
        self.assertTrue(p.skills["Hard Aura"]["method"].startswith("unresolved"))
        self.assertEqual(p.skills["Interact"]["cel"], 0)         # D2R row, not visible: no picture of its own
        self.assertNotIn("Blank", p.skills)                      # no IconCel on purpose: left alone
        self.assertNotIn("Moon Queen", p.skills)                 # class skills keep their sheet

    def test_split_rows_follow_the_built_tables(self):
        p = self.plan()
        self.assertTrue(p.rows["moonqueen"]["split"])
        self.assertTrue(p.rows["attack"]["split"])               # a class skill (here a hidden Warlock one) is on it too
        self.assertEqual(p.skills["Attack"]["method"], "shared sheet")   # ... but the picture stays the shared frame
        self.assertFalse(p.rows["throw"]["split"])

    def test_apply_is_idempotent_and_keeps_class_rows(self):
        p = self.plan()
        dh, d, sh, s = bank()
        si.apply(p, dh, d, sh, s)
        rows = {r[0]: r for r in d}
        skills = {r[0]: r for r in s}
        ic = dh.index("IconCel")
        self.assertEqual(rows["moonqueen"][ic], "60")            # the Amazon skill keeps cel 60 and its tree slot
        self.assertEqual(rows["moonqueen"][1:4], ["2", "1", "3"])
        self.assertEqual(rows["moonqueen~shared"][ic], "8")
        self.assertEqual(rows["moonqueen~shared"][1:4], ["0", "0", "0"])   # no tree slot (validate.py)
        self.assertEqual(rows["moonqueen~shared"][6], "sMoon")   # name and texts copied
        self.assertEqual(skills["Item Moon Queen"][3], "moonqueen~shared")
        self.assertEqual(skills["Moon Queen"][3], "moonqueen")
        self.assertEqual(skills["Hidden"][3], "attack")
        self.assertEqual(rows["attack"][ic], "3")                # the class user's row is untouched
        self.assertEqual(rows["throw"][ic], "4")
        self.assertEqual(rows["fire wall"][ic], "6")
        self.assertEqual(rows["mxl_blank"][ic], "")
        before = [list(r) for r in d], [list(r) for r in s]
        _d, _s, n = si.apply(p, dh, d, sh, s)
        self.assertEqual(([list(r) for r in d], [list(r) for r in s]), before)
        self.assertEqual(sum(n.values()), 0)

    def test_plan_json_roundtrip(self):
        p = self.plan()
        self.assertEqual(si.Plan.from_json(p.to_json()).to_json(), p.to_json())

    def test_tables_second_run_keeps_the_plan(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            ex = root / "excel"
            dh, d, sh, s = bank()
            write_tsv(ex / "skilldesc.txt", dh, d)
            write_tsv(ex / "skills.txt", sh, s)
            orig_inputs, orig_d2r = si.median_inputs, si.d2r_rows
            si.median_inputs = lambda: (MEDIAN, 25, TIERS, CELS)
            si.d2r_rows = lambda _p: D2R
            donors = root / "donors.tsv"
            donors.write_text(tsv("# comment", "skilldesc donor skills reason", "hard_aura|d2r:fire wall|Hard Aura|fire"), "utf-8")
            try:
                first = si.tables(ex, root / "plan.json", root, donors)
                text = (ex / "skilldesc.txt").read_text("utf-8")
                second = si.tables(ex, root / "plan.json", root, donors)
            finally:
                si.median_inputs, si.d2r_rows = orig_inputs, orig_d2r
            self.assertEqual(second.to_json(), first.to_json())
            self.assertEqual((ex / "skilldesc.txt").read_text("utf-8"), text)
            self.assertIn("moonqueen~shared", text)


class DonorTests(unittest.TestCase):
    """The closest icon for a visible skill that would show the "?" (tools/data/item_skill_icons.tsv)."""

    def bank(self):
        dh, d, sh, s = bank()
        d += [["oskill", "0", "0", "0", "0", "0", "sOs"], ["proc", "0", "0", "0", "0", "0", "sPr"],
              ["apocalypse_mxl", "0", "0", "0", "0", "0", "sApo"]]
        s += [["Item Oskill", "9", "", "oskill"], ["Item Proc", "10", "", "proc"], ["Apocalypse_mxl", "11", "", "apocalypse_mxl"]]
        return {"": (dh, d, sh, s)}

    TIERS = {**TIERS, "Item Oskill": 2, "Item Proc": 3, "Apocalypse": 2}
    MEDIAN = {**MEDIAN, "oskill": set(), "proc": set(), "apocalypse": set()}

    def donors(self, table):
        return si.donor_icons(table, self.MEDIAN, CELS, 25, D2R)

    def test_donor_icons(self):
        mk = lambda d: si.donor_icon(d, self.MEDIAN, CELS, 25, {**D2R, "raven": ("war", 0, 60)})
        self.assertEqual(mk("d2r:fire wall"), si.Icon("d2r", "sor", 30))
        self.assertEqual(mk("mxl:moonqueen"), si.Icon("mxl", "ama", 60))
        self.assertEqual(mk("shared:1"), si.Icon("mxl", "", 1))
        for bad in ("d2r:raven",        # the Warlock's classic sheet holds Druid pictures
                    "d2r:interact",     # D2R's shared sheet: not a class skill's row
                    "mxl:attack",       # not a class skill's row
                    "shared:0", "shared:25", "d2r:nothing", "fire wall"):
            with self.assertRaises(ValueError, msg=bad):
                mk(bad)

    def test_visible_question_mark_rows_get_the_donor(self):
        table = {"oskill": ("d2r:fire wall", "fire"), "proc": ("mxl:moonqueen", "x"), "apocalypse": ("shared:1", "x"),
                 "throw": ("mxl:moonqueen", "x")}
        p = si.make_plan(self.bank(), self.MEDIAN, 25, D2R, self.TIERS, self.donors(table))
        self.assertEqual(p.skills["Item Oskill"]["cel"], p.skills["Fire Wall"]["cel"])    # shares Fire Wall's icon
        self.assertEqual(p.skills["Item Oskill"]["method"], "closest icon (d2r:fire wall)")
        self.assertEqual(p.skills["Item Proc"]["cel"], 0)              # a proc is not on the bar: stays on the "?"
        self.assertEqual(p.skills["Apocalypse_mxl"]["tier"], 2)        # renamed by txt_migrate: Median's tier, its donor
        self.assertEqual(p.icons[p.skills["Apocalypse_mxl"]["cel"] // 2], si.Icon("mxl", "", 1))
        self.assertEqual(p.skills["Throw"]["method"], "shared sheet")  # a picture of its own wins over a donor
        self.assertEqual(si.unused_donors(p, table), ["proc", "throw"])
        self.assertEqual(len(p.icons), 6)                             # + shared 1; Fire Wall's frame is reused

    def test_too_many_icons(self):
        dh, d, sh, s = bank()
        table = {}
        for i in range(si.MAX_FRAMES // 2):
            d.append([f"r{i}", "0", "0", "0", "0", "0", "s"])
            s.append([f"S{i}", str(100 + i), "", f"r{i}"])
            table[f"r{i}"] = (si.Icon("d2r", "sor", i), f"d2r:{i}")
        tiers = {**TIERS, **{f"S{i}": 2 for i in range(si.MAX_FRAMES // 2)}}
        with self.assertRaises(ValueError):
            si.make_plan({"": (dh, d, sh, s)}, MEDIAN, 25, D2R, tiers, table)

    def test_read_donors(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "d.tsv"
            f.write_text(tsv("# x", "skilldesc donor skills reason", "", "wrath|d2r:fire ball|Wrath|fire missile"), "utf-8")
            self.assertEqual(si.read_donors(f), {"wrath": ("d2r:fire ball", "fire missile")})
            f.write_text(tsv("wrath|d2r:fire ball|Wrath|x", "wrath|d2r:meteor|Wrath|x"), "utf-8")
            with self.assertRaises(ValueError):
                si.read_donors(f)
            self.assertEqual(si.read_donors(Path(t) / "none.tsv"), {})

    def test_the_shipped_table_parses(self):
        table = si.read_donors()
        self.assertGreater(len(table), 100)
        self.assertTrue(all(d.partition(":")[0] in ("d2r", "mxl", "shared") and why for d, why in table.values()))

    def test_check_flags_visible_question_mark_and_banks(self):
        banks = self.bank()
        p = si.make_plan(banks, self.MEDIAN, 25, D2R, self.TIERS, {})
        self.assertEqual(p.skills["Item Oskill"]["cel"], 0)
        dh, d, sh, s = banks[""]
        self.assertTrue(skill_icon_check.bank_problems(p, banks))      # tables not rewritten yet
        si.apply(p, dh, d, sh, s)
        self.assertEqual(skill_icon_check.bank_problems(p, banks), [])


class SheetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.spells = root / "median"
        self.d2r = root / "d2r"
        self.spells.mkdir()
        (self.spells / "skillicon.dc6").write_bytes(dc6.build_dc6([solid(48, 48, 10 + i) for i in range(25)]))
        (self.spells / "amskillicon.dc6").write_bytes(dc6.build_dc6([solid(48, 48, 100 + i) for i in range(76)]))
        for name in ("amskillicon", "soskillicon", "neskillicon", "paskillicon", "baskillicon", "drskillicon", "asskillicon"):
            if not (self.spells / f"{name}.dc6").exists():
                (self.spells / f"{name}.dc6").write_bytes(dc6.build_dc6([solid(48, 48, 7)] * 2))
        cl = self.d2r / "data" / "global" / "ui" / "spells"
        cl.mkdir(parents=True)
        (cl / "soskillicon.dc6").write_bytes(dc6.build_dc6([solid(48, 48, 150 + i) for i in range(60)]))
        hd = self.d2r / "data" / "hd" / "global" / "ui" / "spells" / "sorceress"
        hd.mkdir(parents=True)
        frames = [[[(i, 1, 2, 255)] * 130 for _ in range(130)] for i in range(60)]
        dc6.write_sheet_sprite(hd / "soskillicon.sprite", frames, 132, 130)
        lows = [[[(i, 1, 2, 255)] * 65 for _ in range(65)] for i in range(60)]
        dc6.write_sheet_sprite(hd / "soskillicon.lowend.sprite", lows, 67, 65)
        self.plan = si.Plan([si.Icon("mxl", "", 0), si.Icon("mxl", "", 3), si.Icon("d2r", "sor", 30),
                             si.Icon("mxl", "ama", 60)], {}, {"Fire Wall": {"row": "fire wall", "cel": 4, "method": "vanilla row",
                                                                           "tier": 2}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_classic_sheet_in_pairs(self):
        out = si.sheet_dc6(self.plan, self.spells, self.d2r, Path(self.tmp.name) / "out" / "skillicon.dc6")
        frames = dc6.read_dc6(out)
        self.assertEqual(len(frames), 8)
        idx = [dc6.decode_frame(*f[:2], f[4], PAL)[10][10] for f in frames]
        self.assertEqual(idx, [PAL[10] + (255,)] * 2 + [PAL[13] + (255,)] * 2 + [PAL[180] + (255,)] * 2 + [PAL[160] + (255,)] * 2)

    def test_hd_and_lowend_sheet(self):
        hd = Path(self.tmp.name) / "hd"
        report = skill_icons.convert(PAL, None, self.spells, hd, plan=self.plan, d2r=self.d2r)
        self.assertEqual(report[""]["frames"], 8)
        self.assertTrue(report[""]["paired"])
        sp = hd / "global" / "ui" / "spells" / "submenu" / "skillicon.sprite"
        low = hd / "global" / "ui" / "spells" / "submenu" / "skillicon.lowend.sprite"
        info, linfo = dc6.sprite_info(sp), dc6.sprite_info(low)
        self.assertEqual((info["frames"], info["frame_width"], info["strip_width"]), (8, 130, 8 * 132))
        self.assertEqual((linfo["frames"], linfo["frame_width"], linfo["strip_width"], linfo["height"]), (8, 65, 8 * 67, 65))
        f = dc6.read_sprite(sp)
        self.assertEqual(f[0][65][65], f[1][65][65])              # pressed = the same picture
        self.assertEqual(f[2][65][65], PAL[13] + (255,))
        self.assertEqual(f[4][65][65], (30, 1, 2, 255))           # D2R's own HD frame 30 as it is
        self.assertEqual(f[6][65][65], PAL[160] + (255,))         # Amazon frame 60
        self.assertEqual(dc6.read_sprite(low)[5][30][30], (30, 1, 2, 255))
        # a class sheet: lowend at half size too
        ci = dc6.sprite_info(hd / "global" / "ui" / "spells" / "amazon" / "amskillicon.lowend.sprite")
        self.assertEqual((ci["frames"], ci["frame_width"]), (76, 65))

    def test_check_reads_the_plan(self):
        skills = [{"name": "Fire Wall", "id": "4", "sheet": "", "desc": "fire wall", "has_desc": True, "cel": 30, "tier": 2},
                  {"name": "Odd", "id": "5", "sheet": "", "desc": "odd", "has_desc": True, "cel": 3, "tier": 4}]
        problems, counts = skill_icon_check.check_skills(skill_icon_check.planned(skills, self.plan), {"": 8}, paired=True)
        self.assertEqual(counts["resolved"], 2)
        self.assertEqual([p["name"] for p in problems], ["Odd"])  # an odd cel on the paired sheet is a pressed frame
        self.assertIn("odd IconCel", problems[0]["why"])

    def test_lowend_geometry(self):
        self.assertEqual(skill_icons.lowend_geometry(50), (67, 65))
        self.assertEqual(skill_icons.lowend_geometry(200), (41, 39))


if __name__ == "__main__":
    unittest.main()
