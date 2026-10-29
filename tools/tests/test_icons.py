"""Unit tests of the HD icon tools on synthetic data (no game files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_icons.py" """
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import dc6  # noqa: E402
import item_art  # noqa: E402
import item_hd  # noqa: E402
import item_icon_check  # noqa: E402
import skill_icon_check  # noqa: E402
import skill_icons  # noqa: E402

PAL = [(i, 255 - i, i // 2) for i in range(256)]


def block(rows_bottom_up: list[list[int | None]]) -> bytes:
    """Encoded DC6 block: lines bottom-up, None = transparent pixel."""
    out = bytearray()
    for line in rows_bottom_up:
        i = 0
        while i < len(line):
            j = i
            if line[i] is None:
                while j < len(line) and line[j] is None and j - i < 127:
                    j += 1
                out.append(0x80 | (j - i))
            else:
                while j < len(line) and line[j] is not None and j - i < 127:
                    j += 1
                out.append(j - i)
                out += bytes(line[i:j])
            i = j
        out.append(0x80)
    return bytes(out)


def solid(w: int, h: int, c: int) -> tuple:
    return (w, h, 0, 0, block([[c] * w for _ in range(h)]))


def write_tsv(path: Path, head: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("\t".join(r) for r in [head] + rows) + "\n", encoding="latin-1")


class Dc6Tests(unittest.TestCase):
    def test_roundtrip_and_decode(self):
        frames = [(3, 2, 1, 2, block([[5, None, 7], [9, 9, 9]])), solid(2, 2, 100)]
        got = dc6.parse_dc6(dc6.build_dc6(frames))
        self.assertEqual(got, frames)
        rows = dc6.decode_frame(*got[0][:2], got[0][4], PAL)
        # lines are stored bottom-up: the first stored line is the bottom row
        self.assertEqual(rows[1], [PAL[5] + (255,), (0, 0, 0, 0), PAL[7] + (255,)])
        self.assertEqual(rows[0], [PAL[9] + (255,)] * 3)

    def test_scale_keeps_colour_and_centres(self):
        rows = [[(200, 100, 50, 255)] * 4 for _ in range(4)]
        out = dc6.scale(rows, 20, 20, 2.0)  # 8x8 picture on a 20x20 canvas: 6 pixels margin each side
        self.assertEqual(out[0][0], (0, 0, 0, 0))
        self.assertEqual(out[6][6], (200, 100, 50, 255))
        self.assertEqual(out[13][13], (200, 100, 50, 255))
        self.assertEqual(out[14][14], (0, 0, 0, 0))

    def test_scale_premultiplied_edge(self):
        rows = [[(255, 0, 0, 255), (0, 0, 0, 0)]]
        out = dc6.scale(rows, 4, 2, 2.0)
        for p in out[0]:  # transparent neighbours must not darken the red
            self.assertTrue(p[3] == 0 or p[0] == 255)

    def test_sheet_sprite_roundtrip(self):
        a = [[(10, 20, 30, 255)] * 3 for _ in range(3)]
        b = [[(40, 50, 60, 128)] * 3 for _ in range(3)]
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "s.sprite"
            dc6.write_sheet_sprite(p, [a, b], 5, 3)
            info = dc6.sprite_info(p)
            self.assertEqual((info["version"], info["frame_width"], info["strip_width"], info["height"], info["frames"]),
                             (31, 3, 10, 3, 2))
            self.assertEqual(info["data_size"], 10 * 3 * 4)
            self.assertEqual(dc6.read_sprite(p), [a, b])

    def test_png_signature(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "a.png"
            dc6.write_png(p, 1, 1, b"\1\2\3\4")
            self.assertEqual(p.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


class SkillTests(unittest.TestCase):
    def test_strip_geometry(self):
        self.assertEqual(skill_icons.strip_geometry(118), (132, 130))
        self.assertEqual(skill_icons.strip_geometry(124), (132, 130))
        self.assertEqual(skill_icons.strip_geometry(200), (81, 79))  # more than fits at full size: smaller frames

    def make_excel(self, root: Path) -> Path:
        ex = root / "excel"
        write_tsv(ex / "skills.txt", ["skill", "Id", "charclass", "skilldesc"],
                  [["Attack", "0", "", "attack"], ["Kick", "1", "", "kick"], ["Fire Bolt", "5", "", "firebolt"],
                   ["Ice Blast", "7", "sor", "iceblast"], ["Bad Cel", "8", "sor", "badcel"], ["Beyond", "9", "ama", "beyond"],
                   ["No Row", "10", "", "ghost"], ["Monster", "11", "", "mon"], ["Charged", "12", "", "chg"],
                   ["NoDesc", "13", "", ""]])
        write_tsv(ex / "skilldesc.txt", ["skilldesc", "SkillPage", "IconCel"],
                  [["attack", "0", "3"], ["kick", "0", "5"], ["firebolt", "0", "2"], ["iceblast", "1", "4"],
                   ["badcel", "1", "x"], ["beyond", "1", "6"], ["mon", "0", "40"], ["chg", "0", "8"]])
        write_tsv(ex / "properties.txt", ["code", "stat1"], [["charged", "item_charged_skill"], ["dmg", "damage"]])
        write_tsv(ex / "uniqueitems.txt", ["index", "prop1", "par1"], [["Staff", "charged", "Charged"]])
        write_tsv(ex / "charstats.txt", ["class", "Skill 1"], [["Sorceress", "Fire Bolt"]])
        return ex

    def test_load_skills_tiers(self):
        with tempfile.TemporaryDirectory() as t:
            skills = {s["name"]: s for s in skill_icons.load_skills(self.make_excel(Path(t)))}
        self.assertEqual(skills["Ice Blast"]["tier"], skill_icons.TREE)
        self.assertEqual(skills["Attack"]["tier"], skill_icons.START)
        self.assertEqual(skills["Fire Bolt"]["tier"], skill_icons.START)  # id < 6 / the character start grant
        self.assertEqual(skills["Charged"]["tier"], skill_icons.BAR)       # an item charges it
        self.assertEqual(skills["Monster"]["tier"], skill_icons.MONSTER)
        self.assertNotIn("NoDesc", skills)
        self.assertIsNone(skills["Bad Cel"]["cel"])
        self.assertFalse(skills["No Row"]["has_desc"])

    def test_check_resolution_without_rounding(self):
        with tempfile.TemporaryDirectory() as t:
            skills = skill_icons.load_skills(self.make_excel(Path(t)))
        frames = {"": 10, "sor": 8, "ama": 6}
        problems, counts = skill_icon_check.check_skills(skills, frames)
        why = {p["name"]: p["why"] for p in problems}
        self.assertIn("No Row", why)
        self.assertEqual(why["No Row"], "no skilldesc row")
        self.assertEqual(why["Bad Cel"], "no IconCel")
        self.assertIn("beyond the sheet", why["Beyond"])        # frame 6 of 6
        self.assertIn("beyond the sheet", why["Monster"])       # frame 40 of 10
        self.assertNotIn("Attack", why)                         # odd frame 3 on the shared sheet resolves as is (not rounded to 2)
        self.assertNotIn("Kick", why)
        self.assertNotIn("Ice Blast", why)
        # Attack, Kick, Fire Bolt, Ice Blast, Charged resolve; the shared sheet's pressed frame is the next icon
        self.assertEqual(counts["resolved"], 5)
        self.assertEqual(counts["shared sheet: pressed frame is the next icon"], 4)

    def test_class_sheet_warnings(self):
        s = [{"name": "A", "id": "1", "sheet": "sor", "desc": "a", "has_desc": True, "cel": 7, "tier": 0},
             {"name": "B", "id": "2", "sheet": "sor", "desc": "b", "has_desc": True, "cel": 3, "tier": 0}]
        problems, _ = skill_icon_check.check_skills(s, {"sor": 8, "": 1})
        self.assertEqual([p["kind"] for p in problems], ["warning", "warning"])
        self.assertIn("no pressed frame", problems[0]["why"])
        self.assertIn("odd IconCel", problems[1]["why"])

    def test_convert_sheet_keeps_frames(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            spells, hd = root / "spells", root / "hd"
            frames = [solid(48, 48, 10 * (i + 1)) for i in range(5)]
            for sheet, _t in skill_icons.TARGETS.values():
                (spells).mkdir(exist_ok=True)
                (spells / f"{sheet}.dc6").write_bytes(dc6.build_dc6(frames))
            report = skill_icons.convert(PAL, None, spells, hd)
            self.assertEqual(report["sor"]["frames"], 5)
            self.assertEqual(report["sor"]["hd_size"], 130)
            sp = hd / "global" / "ui" / "spells" / "sorceress" / "soskillicon.sprite"
            info = dc6.sprite_info(sp)
            self.assertEqual((info["frames"], info["frame_width"], info["strip_width"], info["height"]), (5, 130, 660, 130))
            self.assertTrue((hd / "global" / "ui" / "spells" / "submenu" / "skillicon.lowend.sprite").exists())
            for i, f in enumerate(dc6.read_sprite(sp)):  # frame i of the sprite is frame i of the DC6, scaled up
                self.assertEqual(f[65][65], PAL[10 * (i + 1)] + (255,))


class ItemTests(unittest.TestCase):
    def tables(self):
        mod = {
            "weapons": [{"name": "A", "code": "aaa", "invfile": "invown", "type": "swor", "invwidth": "1", "invheight": "3"},
                        {"name": "B", "code": "hax", "invfile": "invhax", "type": "axe", "invwidth": "1", "invheight": "3"},
                        {"name": "C", "code": "ccc", "invfile": "invhax", "type": "axe", "invwidth": "1", "invheight": "3"},
                        {"name": "D", "code": "ddd", "invfile": "invonly", "type": "axe", "invwidth": "1", "invheight": "3"},
                        {"name": "E", "code": "eee", "invfile": "invnone", "type": "axe", "invwidth": "1", "invheight": "3"},
                        {"name": "F", "code": "fff", "invfile": "", "type": "swor", "invwidth": "1", "invheight": "3"}],
            "armor": [], "misc": [],
            "uniqueitems": [{"index": "Own Unique", "code": "ccc", "invfile": "invown"},
                            {"index": "Hax Unique", "code": "ccc", "invfile": ""},
                            {"index": "Old Name", "code": "ddd", "invfile": ""},
                            {"index": "Old Name", "code": "aaa", "invfile": ""}],
            "setitems": [{"index": "Set Thing", "item": "ccc", "invfile": "invsetpic"}],
        }
        d2r = {
            "weapons": [{"code": "hax", "invfile": "invhax", "type": "axe"}, {"code": "wnd", "invfile": "invwnd", "type": "swor"}],
            "armor": [], "misc": [],
            "uniqueitems": [{"index": "Old Name", "code": "hax", "invfile": "invhax"},
                            {"index": "Gnasher", "code": "hax", "invfile": "invsetpic"}],
            "setitems": [],
        }
        maps = {"items": {"hax": {"asset": "axe/hand_axe"}, "wnd": {"asset": "sword/wand"}},
                "uniques": {"old_name": {"normal": "axe/old", "uber": "axe/old", "ultra": "axe/old"},
                            "gnasher": {"normal": "axe/gnasher", "uber": "axe/gnasher", "ultra": "axe/gnasher"}},
                "sets": {}}
        have = {"weapon/axe/hand_axe", "weapon/sword/wand", "weapon/axe/old", "weapon/axe/gnasher"}
        types = [{"Code": "axe", "Equiv1": "mele"}, {"Code": "swor", "Equiv1": "mele"}]
        return mod, d2r, maps, have, types

    def plan(self, mod_dc6=("invown", "invonly"), d2r_dc6=("invhax", "invwnd", "invsetpic", "invonly2")):
        mod, d2r, maps, have, types = self.tables()
        p = item_hd.Plan(mod, d2r, maps, have, set(mod_dc6), set(d2r_dc6), types)
        return p, p.run()

    def test_base_item_order(self):
        p, (items, uniques, sets) = self.plan()
        a = {c: v["asset"] for e in items for c, v in e.items()}
        self.assertEqual(a["aaa"], "mxl/invown")            # the mod ships the picture
        self.assertEqual(a["hax"], "axe/hand_axe")           # same code, same invfile
        self.assertEqual(a["ccc"], "axe/hand_axe")           # new code, vanilla invfile: D2R's HD asset
        self.assertEqual(a["ddd"], "mxl/invonly")            # mod picture wins
        self.assertEqual(a["eee"], "axe/hand_axe")           # no DC6 anywhere: fallback of the same item type
        self.assertEqual(a["fff"], "sword/wand")             # blank invfile: same item type
        self.assertEqual(p.how["items: mod"], 2)
        self.assertEqual(len(p.report["fallback"]), 2)
        self.assertEqual(p.report["no_dc6"], ["weapons eee 'E': invfile 'invnone'"])
        self.assertEqual(set(p.needs), {("weapon", "mxl", "invown"), ("weapon", "mxl", "invonly")})

    def test_classic_fallback_when_d2r_has_no_hd_for_invfile(self):
        mod, d2r, maps, have, types = self.tables()
        mod["weapons"].append({"name": "G", "code": "ggg", "invfile": "invonly2", "type": "axe", "invwidth": "2", "invheight": "2"})
        p = item_hd.Plan(mod, d2r, maps, have, {"invown"}, {"invhax", "invwnd", "invonly2"}, types)
        items, _u, _s = p.run()
        self.assertEqual({c: v["asset"] for e in items for c, v in e.items()}["ggg"], "classic/invonly2")
        self.assertIn(("weapon", "classic", "invonly2"), p.needs)
        self.assertEqual(p.needs["weapon", "classic", "invonly2"], (2, 2))

    def test_uniques_and_sets(self):
        p, (items, uniques, sets) = self.plan()
        u = {k: v["normal"] for e in uniques for k, v in e.items()}
        self.assertEqual(u["own_unique"], "mxl/invown")
        self.assertEqual(u["hax_unique"], "axe/hand_axe")      # blank invfile: the base item's picture
        self.assertEqual(u["old_name"], "mxl/invonly")         # first row of the repeated name decides (its base ddd has the mod's picture)
        self.assertEqual(len(uniques), 3)
        self.assertEqual({k: v["normal"] for e in sets for k, v in e.items()}["set_thing"], "axe/gnasher")  # D2R unique with that invfile
        self.assertEqual(p.report["repeated_names_uniqueitems"][0][:24], "1 names repeat on severa")

    def test_same_name_needs_same_invfile(self):
        mod, d2r, maps, have, types = self.tables()
        mod["uniqueitems"] = [{"index": "Old Name", "code": "ccc", "invfile": "invhax"}]  # D2R's Old Name has invhax too
        p = item_hd.Plan(mod, d2r, maps, have, set(), {"invhax", "invwnd", "invsetpic"}, types)
        _i, uniques, _s = p.run()
        self.assertEqual(uniques[0]["old_name"]["normal"], "axe/old")  # D2R's Old Name has this invfile: its own entry
        mod["uniqueitems"] = [{"index": "Gnasher", "code": "ccc", "invfile": "invwnd"}]  # same name, other invfile than D2R's
        p = item_hd.Plan(mod, d2r, maps, have, set(), {"invhax", "invwnd", "invsetpic"}, types)
        self.assertEqual(p.run()[1][0]["gnasher"]["normal"], "sword/wand")  # not D2R's gnasher art: the invfile decides

    def test_key(self):
        self.assertEqual(item_hd.key("Buriza-Do Kyanon"), "buriza_do_kyanon")
        self.assertEqual(item_hd.key("Civerb's Ward"), "civerbs_ward")

    def test_item_art_sizes_and_assets(self):
        self.assertEqual(item_art.asset_size(28, 84, 1, 3), (1, 3))
        self.assertEqual(item_art.asset_size(56, 56, 1, 1), (2, 2))  # the picture decides when the table's cells are too small
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            src = root / "mod"
            src.mkdir()
            (src / "pic.dc6").write_bytes(dc6.build_dc6([solid(28, 56, 77)]))
            out = root / "hd"
            name = item_art.make_asset("mxl", "pic", "misc", 1, 2, PAL, out, {"mxl": src})
            self.assertEqual(name, "mxl/pic")
            info = dc6.sprite_info(out / "global/ui/items/misc/mxl/pic.sprite")
            self.assertEqual((info["strip_width"], info["height"], info["frame_width"], info["frames"]), (98, 196, 98, 1))
            low = dc6.sprite_info(out / "global/ui/items/misc/mxl/pic.lowend.sprite")
            self.assertEqual((low["strip_width"], low["height"]), (49, 98))
            self.assertIsNone(item_art.make_asset("mxl", "nope", "misc", 1, 1, PAL, out, {"mxl": src}))
            self.assertEqual(item_icon_check.check_sprite(out / "global/ui/items/misc/mxl/pic.sprite", src / "pic.dc6", PAL, 98), [])
            self.assertEqual(item_icon_check.check_sprite(out / "global/ui/items/misc/mxl/pic.lowend.sprite", src / "pic.dc6", PAL, 49), [])
            self.assertTrue(item_icon_check.check_sprite(out / "global/ui/items/misc/mxl/none.sprite", src / "pic.dc6", PAL, 98))

    def test_reference_check(self):
        mod, d2r, maps, have, types = self.tables()
        p = item_hd.Plan(mod, d2r, maps, have, {"invown", "invonly"}, {"invhax", "invwnd", "invsetpic"}, types)
        items, uniques, sets = p.run()
        flat = lambda lst: {k: v for e in lst for k, v in e.items()}  # noqa: E731
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            rep = item_icon_check.check_items(mod, flat(items), flat(uniques), flat(sets), have, {"invown", "invonly"},
                                              {"invhax", "invwnd", "invsetpic"}, out)
            self.assertEqual(rep["kinds"], {"mod": 2, "d2r classic": 2, "none": 1})  # invsetpic is not referenced by the mod base rows
            self.assertEqual(list(rep["unresolved"]), ["invnone"])
            self.assertEqual(rep["unmapped_codes"], [])
            # the mod's sprites were not generated here: the assets are missing
            self.assertTrue(rep["bad_assets"])
            self.assertEqual(rep["mod_art_not_used"], [])
            self.assertEqual(rep["repeated_names"], ["uniqueitems 'Old Name'"])


if __name__ == "__main__":
    unittest.main()
