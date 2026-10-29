"""Unit tests of tools/warlock_legacy_check.py and the classic frame cap of tools/animdata_merge.py (bugs.md #498) on synthetic
data (no game files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_warlock_legacy_check.py" """
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import animdata_merge  # noqa: E402
import dc6  # noqa: E402
import warlock_legacy_check as w  # noqa: E402
from test_legacy_art import animdata, cof, dcc  # noqa: E402

LAYERS = [(1, "hth"), (5, "hth")]  # tr, rh


def put(root: Path, rel: str, data: bytes | str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data.encode() if isinstance(data, str) else data)


def table(rows: list[dict[str, str]]) -> str:
    head = list(dict.fromkeys(k for r in rows for k in r))
    return "\n".join(["\t".join(head)] + ["\t".join(r.get(k, "") for k in head) for r in rows]) + "\n"


class Fixture:
    """A built mod folder (data/) and a D2R extraction (data/ + filelist.txt) in a temp folder."""

    def __init__(self, tmp: str):
        self.root = Path(tmp)
        self.mod = self.root / "mod" / "data"
        self.d2r = self.root / "d2r"
        self.base: list[str] = []

    def d2r_file(self, rel: str, data: bytes | str) -> None:
        put(self.d2r / "data", rel, data)
        self.base.append(rel)

    def view(self) -> w.View:
        (self.d2r / "filelist.txt").write_text("".join(f"data:data/{r}\n" for r in self.base), "utf-8")
        return w.View(self.mod, self.d2r)


class CharTest(unittest.TestCase):
    def test_twins_animdata_and_layer_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Fixture(tmp)
            for cls in ("ne", "wk"):
                f.d2r_file(f"global/chars/{cls}/cof/{cls}a1hth.cof", cof(15, LAYERS, dirs=16))
                f.d2r_file(f"global/chars/{cls}/tr/{cls}trlita1hth.dcc", dcc(16, 15))
            f.d2r_file("global/chars/ne/rh/nerhdgra1hth.dcc", dcc(16, 15))   # no Warlock twin
            f.d2r_file("global/chars/wk/cof/wknuhth.cof", cof(8, LAYERS, dirs=16))
            f.d2r_file("global/chars/wk/tr/wktrlitnuhth.dcc", dcc(16, 4))     # fewer frames than its COF
            rows = w.check_char(f.view(), "wk", "ne", {"WKA1HTH": 16, "WKNUHTH": 8})
            by = {r.file: r for r in rows}
            self.assertEqual(by["global/chars/wk/rh/wkrhdgra1hth.dcc"].found, "MISSING")
            self.assertIn("runs past the art", by["global/chars/wk/cof/wka1hth.cof"].problem)
            self.assertIn("4 frames", by["global/chars/wk/tr/wktrlitnuhth.dcc"].problem)
            self.assertEqual(by["global/chars/wk/cof/wknuhth.cof"].problem, "")
            rows = w.check_char(f.view(), "wk", "ne", {"WKA1HTH": 12, "WKNUHTH": 8})
            r = next(r for r in rows if r.file.endswith("wka1hth.cof"))
            self.assertEqual(r.problem, "")
            self.assertIn("ends early", r.note)   # animdata shorter than the art: drawn, cut short

    def test_no_token(self):
        self.assertEqual(w.check_char(w.View(Path("."), Path(".")), "", "ne", None)[0].found, "MISSING")


class MonsterTest(unittest.TestCase):
    def test_vanilla_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Fixture(tmp)
            f.d2r_file("global/monsters/gm/cof/gmnu2hs.cof", cof(10, [(1, "2hs"), (5, "2hs")]))
            f.d2r_file("global/monsters/gm/tr/gmtrlitnu2hs.dcc", dcc(8, 10))
            f.d2r_file("global/monsters/gm/cof/gmdthth.cof", cof(19, [(1, "hth")]))   # DT only in hth
            f.d2r_file("global/monsters/gm/tr/gmtrlitdthth.dcc", dcc(8, 19))
            f.d2r_file("global/monsters/gm/cof/gmgh2hs.cof", cof(6, [(1, "2hs")]))
            f.d2r_file("global/monsters/gm/tr/gmtrlitgh2hs.dcc", dcc(8, 6))
            r2 = {"basew": "2hs", "mnu": "1", "mdt": "1", "msq": "1", "mkb": "1", "mwl": "1", "tr": "1", "trv": "lit",
                  "rh": "1", "rhv": "axe"}
            rows = w.monster_rows(f.view(), "gm", r2, "summon", {"GMNU2HS": 10, "GMDTHTH": 19, "GMGH2HS": 6})
            by = {(r.file, r.needed_by.split()[-1]): r for r in rows}
            self.assertEqual(by[("global/monsters/gm/cof/gmdthth.cof", "DT")].found, "base")   # hth fallback
            self.assertEqual(by[("global/monsters/gm/cof/gmgh2hs.cof", "KB")].found, "base")   # KB draws GH
            self.assertEqual(by[("global/monsters/gm/cof/gmwl2hs.cof", "WL")].found, "MISSING")
            self.assertFalse(any("sq" in r.file.rsplit("/", 1)[1][2:4] for r in rows))      # SQ: no COF
            rh = [r for r in rows if "/rh/" in r.file]
            self.assertTrue(rh and all(r.found == "not-drawn" and not w.bad(r) for r in rh))


class SkillTest(unittest.TestCase):
    def test_closure_follows_missiles_states_and_summons(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Fixture(tmp)
            ex = f.mod / "global" / "excel"
            put(ex.parent.parent, "global/excel/skills.txt", table([
                {"skill": "Blast", "*Id": "1", "charclass": "war", "srvmissilea": "boom", "aurastate": "glow",
                 "summon": "pet", "castoverlay": "nothere"},
                {"skill": "Pet Bite", "*Id": "2", "charclass": "", "cltmissile": "bite"}]))
            put(ex.parent.parent, "global/excel/missiles.txt", table([
                {"Missile": "boom", "CelFile": "boom", "NumDirections": "16", "SubMissile1": "boomexp"},
                {"Missile": "boomexp", "CelFile": "expansion\\boomexp"}, {"Missile": "bite", "CelFile": ""}]))
            put(ex.parent.parent, "global/excel/overlay.txt", table([{"overlay": "glowfx", "Filename": "GlowFx"}]))
            put(ex.parent.parent, "global/excel/states.txt", table([{"state": "glow", "overlay1": "glowfx"}]))
            put(ex.parent.parent, "global/excel/monstats.txt", table([{"Id": "pet", "Code": "pt", "Skill1": "Pet Bite"}]))
            put(ex.parent.parent, "global/excel/monstats2.txt", table([{"Id": "pet", "BaseW": "hth", "mNU": "1"}]))
            f.d2r_file("global/missiles/boom.dcc", dcc(1, 4))
            f.d2r_file("global/overlays/glowfx.dcc", dcc(1, 4))
            put(f.mod, "global/monsters/pt/cof/ptnuhth.cof", cof(4, []))
            rows = w.check_skills(f.view(), w.Tables(ex), {"PTNUHTH": 4})
            by = {r.file: r for r in rows}
            self.assertIn("NumDirections 16", by["global/missiles/boom.dcc"].note)   # a note, as in vanilla rows
            self.assertFalse(w.bad(by["global/missiles/boom.dcc"]))
            self.assertEqual(by["global/missiles/expansion/boomexp.dcc"].found, "MISSING")
            self.assertEqual(by["global/overlays/glowfx.dcc"].found, "base")
            self.assertEqual(by["global/monsters/pt/cof/ptnuhth.cof"].found, "mod")
            self.assertEqual(by["excel/overlay.txt:nothere"].found, "MISSING")
            self.assertNotIn("global/missiles/.dcc", by)   # a blank CelFile draws nothing


class UiTest(unittest.TestCase):
    LAYOUT = ('{ "fields": { "skillRow": [ 1, 2, 3, 4, 5, 6 ], "skillColumn": [ 1, 2, 3 ],\n'
              ' "skillButtonFile": [ ' + ", ".join(f'"Spells\\\\C{i}"' for i in range(8)) + ' ],\n'
              ' "skillBackgroundFile": [ ' + ", ".join(f'"Spells\\\\T{i}"' for i in range(8)) + ' ],\n'
              ' "textTab0": [ 0,1,2,3,4,5,6,7 ], "textTab1": [ 0,1,2,3,4,5,6,7 ], "textTab2": [ 0,1,2,3,4,5,6,7 ],\n'
              ' // seven classes\n "cancelPositionCode": [ 321, 113, 131, 121, 313, 333, 231 ], } }')

    def test_layout_sheet_and_inventory(self):
        frame = (48, 48, 0, 0, bytes([0x80]) * 48)
        with tempfile.TemporaryDirectory() as tmp:
            f = Fixture(tmp)
            f.d2r_file("global/ui/layouts/skillstreepanel.json", self.LAYOUT)
            f.d2r_file("global/ui/spells/c7.dc6", dc6.build_dc6([frame] * 6))
            f.d2r_file("global/ui/spells/t7.dc6", dc6.build_dc6([frame] * 16))
            ex = f.root / "excel"
            put(ex, "skills.txt", table([{"skill": "A", "charclass": "war", "skilldesc": "a"},
                                         {"skill": "B", "charclass": "war", "skilldesc": "b"}]))
            put(ex, "skilldesc.txt", table([{"skilldesc": "a", "SkillPage": "1", "SkillRow": "1", "SkillColumn": "1",
                                             "IconCel": "4"},
                                            {"skilldesc": "b", "SkillPage": "2", "SkillRow": "7", "SkillColumn": "1",
                                             "IconCel": "5"}]))
            put(ex, "inventory.txt", table([{"class": "Amazon", "gridX": "10"}, {"class": "Warlock", "gridX": "10"}]))
            rows = w.check_ui(f.view(), w.Tables(ex))
            by = {r.file: r for r in rows}
            self.assertIn("no index 7", by["global/ui/layouts/skillstreepanel.json:cancelPositionCode"].problem)
            self.assertEqual(by["global/ui/layouts/skillstreepanel.json:textTab0"].problem, "")
            self.assertEqual(by["global/ui/spells/c7.dc6"].found, "base")
            self.assertEqual(by["excel/skilldesc.txt:a"].problem, "")                 # 4 and 5 inside 6 frames
            self.assertIn("IconCel 5", by["excel/skilldesc.txt:b"].problem)           # its pressed frame 6 is not
            self.assertIn("row 7", by["excel/skilldesc.txt:b"].problem)
            self.assertEqual(by["excel/inventory.txt:Warlock2"].found, "MISSING")
            self.assertEqual(by["excel/inventory.txt:Warlock"].problem, "")


class KitTest(unittest.TestCase):
    def test_kit_pictures_and_hand(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Fixture(tmp)
            ex = f.root / "excel"
            put(ex, "charstats.txt", table([{"class": "Amazon", "item1": "gem", "item2": "jav"},
                                            {"class": "Warlock", "item1": "gem", "item2": "dag"}]))
            put(ex, "weapons.txt", table([{"code": "dag", "alternategfx": "dgr", "invfile": "invdgr",
                                           "flippyfile": "flpdgr", "wclass": "1ht", "2handedwclass": "1ht"}]))
            put(ex, "misc.txt", table([{"code": "gem", "invfile": "invgem", "flippyfile": "flpgone"}]))
            f.d2r_file("global/items/invdgr.dc6", b"x")
            put(f.mod, "global/items/invgem.dc6", b"x")
            f.d2r_file("global/chars/wk/cof/wka11ht.cof", cof(19, [(5, "1ht")]))
            rows = w.check_kit(f.view(), w.Tables(ex), "wk")
            by = {r.file: r for r in rows}
            self.assertEqual(by["global/items/invdgr.dc6"].found, "base")
            self.assertEqual(by["global/items/flpdgr.dc6"].found, "MISSING")
            self.assertEqual(by["global/items/invgem.dc6"].found, "mod")
            self.assertEqual(by["global/items/flpgone.dc6"].found, "all-classes")   # every class starts with it
            self.assertEqual(by["global/chars/wk/rh/wkrhdgra11ht.dcc"].found, "MISSING")


class CapTest(unittest.TestCase):
    @staticmethod
    def rec(name: bytes, frames: int, event_at: int) -> bytes:
        ev = bytearray(144)
        ev[event_at] = 1
        return name.ljust(8, b"\0") + struct.pack("<II", frames, 256) + bytes(ev)

    def test_cap_keeps_speed_and_events(self):
        merged = {b"WKA1HTH": self.rec(b"WKA1HTH", 16, 9), b"WKA2HTH": self.rec(b"WKA2HTH", 15, 7)}
        before = dict(merged)
        self.assertEqual(animdata_merge.cap_classic(merged), ["WKA1HTH 16->15"])
        self.assertEqual(struct.unpack_from("<I", merged[b"WKA1HTH"], 8)[0], 15)
        self.assertEqual(merged[b"WKA1HTH"][12:], before[b"WKA1HTH"][12:])
        self.assertEqual(merged[b"WKA2HTH"], before[b"WKA2HTH"])   # already inside the cap
        self.assertEqual(animdata_merge.cap_classic({}), [])

    def test_cap_refuses_an_event_past_it(self):
        with self.assertRaises(SystemExit):
            animdata_merge.cap_classic({b"WKA1HTH": self.rec(b"WKA1HTH", 16, 15)})

    def test_checker_reads_animdata(self):
        self.assertEqual(w.anim_frames(animdata({"WKA1HTH": 15}))["WKA1HTH"], 15)


if __name__ == "__main__":
    unittest.main()
