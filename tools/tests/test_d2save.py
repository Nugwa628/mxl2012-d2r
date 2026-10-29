"""Tests of tools/d2save.py and tools/save_audit.py (lane savefmt): synthetic items, saves and tables, no game files.

  py -3 -I -m unittest discover -s tools/tests -p "test_d2save.py" -v
"""
import copy
import hashlib
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import d2save  # noqa: E402
import save_audit  # noqa: E402

S = lambda name, bits, add=0, par=0, csv_bits=0: dict(name=name, bits=bits, add=add, par=par, csv_bits=csv_bits,  # noqa: E731
                                                      csv_par=0, saved=bool(csv_bits))
STATS = {
    0: S("strength", 11, 32, csv_bits=12), 5: S("newskills", 8, csv_bits=8), 12: S("level", 7, csv_bits=7),
    13: S("experience", 32, csv_bits=32), 14: S("gold", 25, csv_bits=25),
    17: S("item_maxdamage_percent", 9, 161), 18: S("item_mindamage_percent", 9, 161),
    31: S("armorclass", 16, 500), 72: S("durability", 10), 73: S("maxdurability", 10),
    80: S("item_magicbonus", 10, 75), 89: S("item_lightradius", 8, 5),
    97: S("item_nonclassskill", 6, 1, par=11), 196: S("item_skillonkill", 7, par=17), 204: S("item_charged_skill", 16, par=16),
    300: S("flag_bit", 1), 537: S("high_id_stat", 9),
}
T = d2save.Tables(STATS, armor={"600", "86@"}, weapons={"119", "149"}, stackable={"149", "tsc"})


def item(**kw):
    base = dict(flags=0x00880010, b105=5, version=5, location=0, equip=0, x=0, y=0, page=1, code="119", filled=0,
                id=0x12345678, ilvl=99, quality=2, guid=(1 << 127) | 12345, maxdur=40, dur=33, ts=0, stats=[])
    base.update(kw)
    return base


def prop(sid, value, param=None, lead=True):
    return dict(id=sid, name=STATS[sid]["name"], param=param, value=value, lead=lead)


def roundtrip(it, tables=T):
    data = d2save.write_item(it, tables)
    back, end = d2save.read_item(data, 0, tables)
    return data, back, end


def same(a, b):
    drop = {"_raw", "code_chars", "children"}
    return {k: v for k, v in a.items() if k not in drop} == {k: v for k, v in b.items() if k not in drop}


class Huffman(unittest.TestCase):
    def test_codes_and_escapes(self):
        for code in ("hp1", "zen", "01-", "!08", "86@", "&01", "J0+", "!@A", "!@B", "0o^", "5$a"):
            w = d2save.BitWriter()
            chars = (d2save.split_code(code) + [" "] * 4)[:4]
            for ch in chars:
                d2save.huff_write(w, ch)
            r = d2save.BitReader(w.tobytes())
            got = [d2save.huff_read(r) for _ in range(4)]
            self.assertEqual(got, chars)
            self.assertEqual(r.pos, w.pos)

    def test_escape_values_found_in_game(self):
        # starter item `01-` of every class: after `0`, `1` comes the escape 000101111 and 0x4f
        w = d2save.BitWriter()
        d2save.huff_write(w, "-")
        self.assertEqual("".join(map(str, w.bits)), "000101111" + "11110010")

    def test_unknown_character_refused(self):
        with self.assertRaises(ValueError):
            d2save.huff_write(d2save.BitWriter(), "~")

    def test_extended_tree_read_from_the_game(self):
        """`&`, `J`, `N` are 7 bits after the escape (a `0` follows them in `&01`, `J0+`, `N0+`); the others 8."""
        self.assertEqual(len(d2save.EXT_CODES), 27)  # ! $ & + - @ ^ and A-T
        self.assertEqual({c for c, p in d2save.EXT_CODES.items() if len(p) == 7}, {"&", "J", "N"})
        ext = list(d2save.EXT_CODES.values())
        for a in ext:
            for b in ext:
                if a != b:
                    self.assertFalse(b.startswith(a), (a, b))

    def test_tree_is_prefix_free(self):
        codes = list(d2save.HUFF.values()) + [d2save.HUFF_ESC]
        for a in codes:
            for b in codes:
                if a != b:
                    self.assertFalse(b.startswith(a), (a, b))


class Items(unittest.TestCase):
    def test_simple_item(self):
        it = dict(flags=0x00A80010, b105=5, version=5, location=2, equip=0, x=3, y=0, page=0, code="tsc", guid=7, filled=0)
        data, back, end = roundtrip(it)
        self.assertTrue(same(it, back))
        self.assertEqual(end, len(data) * 8)

    def test_weapon_armor_stack_fields(self):
        for it in (item(), item(code="600", defense=1234, maxdur=250, dur=0),
                   item(code="149", quantity=511, maxdur=0), item(code="119", maxdur=0)):
            if it["maxdur"] == 0:
                del it["dur"]
            _data, back, _end = roundtrip(it)
            self.assertTrue(same(it, back), (it, back))
            if it["maxdur"] == 0:
                self.assertNotIn("dur", back)

    def test_extended_quality_widths(self):
        """16-bit unique / set / affix / rare fields: values above the retail widths survive."""
        cases = [item(quality=7, unique_id=2478), item(quality=7, unique_id=0xFFFF), item(quality=4, prefix=4000, suffix=60000),
                 item(quality=6, rare1=300, rare2=65535, affix0=747, affix3=959, affix6=528, affix7=65535),
                 item(quality=8, rare1=1, rare2=2, affix1=3)]
        for it in cases:
            _data, back, _end = roundtrip(it)
            self.assertTrue(same(it, back), (it, back))

    def test_set_item_bonus_lists(self):
        it = item(code="86@", quality=5, set_id=299, defense=10, set_mask=0b10101, stats=[prop(0, 5)],
                  set_stats0=[prop(80, 30)], set_stats2=[prop(89, 2)], set_stats4=[prop(0, 7), prop(80, -75)])
        _data, back, _end = roundtrip(it)
        self.assertTrue(same(it, back))
        self.assertNotIn("set_stats1", back)

    def test_runeword_personalized_ethereal(self):
        it = item(flags=0x00880010 | 0x4000000 | 0x1000000 | 0x400000 | 0x800, runeword_id=3132, runeword_pad=5,
                  personal="Nugwa", sockets=6, stats=[prop(17, 300), prop(18, 300, lead=False)],
                  runeword_stats=[prop(97, 25, param=1109)])
        _data, back, _end = roundtrip(it)
        self.assertTrue(same(it, back))

    def test_param_is_32_bits_and_values_use_save_bits(self):
        it = item(stats=[prop(97, 21, param=712), prop(196, 100, param=(1109 << 6) | 63), prop(204, 0xFFFF, param=0xFFFF)])
        data, back, _end = roundtrip(it)
        self.assertEqual([(p["id"], p["param"], p["value"]) for p in back["stats"]], [(97, 712, 21), (196, (1109 << 6) | 63, 100),
                                                                                     (204, 0xFFFF, 0xFFFF)])
        w = d2save.BitWriter()
        w.write(712, 32)
        self.assertIn(w.tobytes(), data)

    def test_paired_stats_have_no_id_of_their_own(self):
        it = item(stats=[prop(17, 51), prop(18, 51, lead=False)])
        _data, back, _end = roundtrip(it)

        def bits(x):
            w = d2save.BitWriter()
            d2save._item_layout(d2save._Codec(T, x, writer=w))
            return w.pos
        self.assertEqual(bits(it) - bits(item(stats=[])), 16 + 9 + 9)  # one id, two values
        self.assertEqual([p["lead"] for p in back["stats"]], [True, False])

    def test_value_out_of_range_refused(self):
        with self.assertRaises(ValueError):
            d2save.write_item(item(stats=[prop(89, -20)]), T)  # light radius -20 with Save Add 5: the trap save_audit reports

    def test_byte_aligned_item_gets_a_padding_byte(self):
        seen = set()
        for n in range(8):
            it = item(stats=[prop(300, 1)] * n)
            w = d2save.BitWriter()
            d2save._item_layout(d2save._Codec(T, it, writer=w))
            data = d2save.write_item(it, T)
            self.assertEqual(len(data), w.pos // 8 + 1)
            back, end = d2save.read_item(data + b"\xff", 0, T)
            self.assertEqual(end, len(data) * 8)
            self.assertTrue(same(it, back))
            seen.add(w.pos % 8)
        self.assertIn(0, seen)

    def test_list_with_socketed_children(self):
        parent = item(flags=0x00880810, sockets=3, filled=2)
        kids = [dict(flags=0x00A80010, b105=5, version=5, location=6, equip=0, x=i, y=0, page=0, code="tsc", guid=i, filled=0)
                for i in range(2)]
        parent["children"] = kids
        lone = item(code="600", defense=3, x=4)
        data = d2save.write_item_list([parent, lone], T)
        items, end = d2save.read_item_list(data + b"jf", 0, T)
        self.assertEqual(end, len(data))
        self.assertEqual(len(items), 2)
        self.assertEqual([k["x"] for k in items[0]["children"]], [0, 1])
        self.assertEqual(d2save.write_item_list(items, T), data)


def synthetic_d2s(items, corpse_items=None, merc=None, golem=None):
    head = bytearray(0x340)
    struct.pack_into("<II", head, 0, d2save.SIG, 0x69)
    head[0x18], head[0x1B] = 4, 120
    head[0x12B:0x12B + 7] = b"Tester\0"
    body = bytes(head)
    body += d2save.write_char_stats([dict(id=0, value=4000), dict(id=12, value=120), dict(id=13, value=666666666),
                                     dict(id=5, value=255), dict(id=14, value=1200000)], T)
    body += b"if" + bytes(range(30))
    body += d2save.write_item_list(items, T)
    if corpse_items is None:
        body += b"JM\0\0"
    else:
        body += b"JM\1\0" + struct.pack("<III", 0, 5652, 5522) + d2save.write_item_list(corpse_items, T)
    body += b"jf" + (d2save.write_item_list(merc, T) if merc is not None else b"")
    body += b"kf" + (b"\1" + d2save.write_item(golem, T) if golem else b"\0")
    return d2save.fix_header(body)


class Saves(unittest.TestCase):
    def test_d2s_roundtrip_all_containers(self):
        data = synthetic_d2s([item(), item(code="600", defense=7, x=2)], corpse_items=[item(x=5)],
                             merc=[item(location=1, equip=4, page=0)], golem=item(code="119"))
        s = d2save.D2S(data, T)
        self.assertEqual((s.name, s.cls, s.level), ("Tester", 4, 120))
        self.assertEqual({x["name"]: x["value"] for x in s.stats}["experience"], 666666666)
        self.assertEqual(s.skills, list(range(30)))
        self.assertEqual(len(s.corpses), 1)
        self.assertEqual(len(s.merc), 1)
        self.assertIsNotNone(s.golem)
        self.assertEqual(s.encode(), data)
        self.assertEqual(d2save.checksum(data), struct.unpack_from("<I", data, 12)[0])
        self.assertEqual([w for w, _ in s.all_items()], ["player", "player", "corpse", "merc", "golem"])

    def test_char_stat_width_saturation_is_visible(self):
        with self.assertRaises(ValueError):
            d2save.write_char_stats([dict(id=5, value=256)], T)  # newskills is 8 bits

    def test_d2i_pages(self):
        pages = b""
        for n, its in enumerate(([item()], [], [item(code="600", defense=1), item(x=3)])):
            body = d2save.write_item_list(its, T)
            hdr = struct.pack("<IIIII", d2save.SIG, 1, 0x69, 1000 * n, 64 + len(body)) + bytes(44)
            pages += hdr + body
        st = d2save.D2I(pages, T)
        self.assertEqual([len(p["items"]) for p in st.pages], [1, 0, 2])
        self.assertEqual([p["gold"] for p in st.pages], [0, 1000, 2000])
        self.assertEqual(st.encode(), pages)

    def test_sidecar(self):
        d2s = synthetic_d2s([item()])
        body = bytearray(0x60)
        struct.pack_into("<II", body, 0x08, struct.unpack_from("<I", d2s, 12)[0], len(d2s))
        body[0x10:0x30] = hashlib.sha256(d2s).digest()
        head = b"D2RL" + struct.pack("<HHI", 2, 0x2C, len(body)) + hashlib.sha256(bytes(body)).digest()
        self.assertEqual(d2save.check_sidecar(d2s, head + bytes(body)), [])
        edited = d2save.fix_header(d2s[:-1] + b"\1")
        problems = d2save.check_sidecar(edited, head + bytes(body))
        self.assertTrue(any("checksum" in p for p in problems) and any("save hash" in p for p in problems))

    def test_diff_reports_lost_and_changed(self):
        a = d2save.D2S(synthetic_d2s([item(), item(code="600", defense=7, x=2), item(x=4, quality=7, unique_id=400)]), T)
        changed = [item(), item(code="600", defense=8, x=2)]
        b = d2save.D2S(synthetic_d2s(changed), T)
        d = d2save.diff_snapshots(d2save.snapshot(a), d2save.snapshot(b))
        self.assertTrue(any(x.startswith("LOST") and ":119" in x for x in d), d)
        self.assertTrue(any(x.startswith("CHANGED") and "defense 7 -> 8" in x for x in d), d)
        self.assertEqual(d2save.diff_snapshots(d2save.snapshot(a), d2save.snapshot(copy.deepcopy(a))), [])

    def test_moved_item_is_not_a_difference_of_content(self):
        a = d2save.D2S(synthetic_d2s([item(x=1, id=1)]), T)
        b = d2save.D2S(synthetic_d2s([item(x=1, id=2, guid=99)]), T)  # the game gives items new ids on load
        self.assertEqual(d2save.diff_snapshots(d2save.snapshot(a), d2save.snapshot(b)), [])


def write_tsv(d, name, header, rows):
    with open(os.path.join(d, name), "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(header) + "\n")
        for r in rows:
            f.write("\t".join(str(c) for c in r) + "\n")


class Audit(unittest.TestCase):
    def tables(self, d, unique_rows, skills_per_class=30, maxstack=500):
        write_tsv(d, "itemstatcost.txt", ["Stat", "*ID", "Saved", "CSvBits", "CSvParam", "Save Bits", "Save Add", "Save Param Bits"], [
            ["strength", 0, 1, 12, "", 11, 32, ""], ["statpts", 4, 1, 11, "", "", "", ""], ["newskills", 5, 1, 8, "", "", "", ""],
            ["level", 12, 1, 7, "", "", "", ""], ["experience", 13, 1, 32, "", "", "", ""], ["gold", 14, 1, 25, "", "", "", ""],
            ["goldbank", 15, 1, 25, "", "", "", ""], ["armorclass", 31, "", "", "", 16, 500, ""],
            ["durability", 72, "", "", "", 10, 0, ""], ["maxdurability", 73, "", "", "", 10, 0, ""],
            ["item_lightradius", 89, "", "", "", 8, 5, ""], ["item_skillonkill", 196, "", "", "", 7, 0, 17],
            ["unsaved_stat", 300, "", "", "", "", "", ""]])
        fh = ["code", "*Id"] + [f"{k}{i}" for i in range(1, 8) for k in ("func", "stat", "set", "val")]
        props = [["light", 1, 1, "item_lightradius"], ["kill-skill", 2, 11, "item_skillonkill"], ["nosave", 3, 1, "unsaved_stat"]]
        write_tsv(d, "properties.txt", fh, [p + [""] * (len(fh) - len(p)) for p in props])
        write_tsv(d, "uniqueitems.txt", ["index", "code", "prop1", "par1", "min1", "max1"], unique_rows)
        write_tsv(d, "skills.txt", ["skill", "*Id", "charclass", "maxlvl"],
                  [[f"s{i}", i, "ama", 20] for i in range(skills_per_class)] + [["Big", 1500, "", 20]])
        for f in ("armor.txt", "weapons.txt"):
            write_tsv(d, f, ["name", "code", "stackable", "maxstack", "gemsockets"], [["x", "600" if f == "armor.txt" else "119", 0, 0, 6]])
        write_tsv(d, "misc.txt", ["name", "code", "stackable", "maxstack", "gemsockets"],
                  [["arrows", "aqv", 1, maxstack, 0], ["gold", "gld", 1, 5000, 0], ["orb", "4~a", 0, 0, 0]])
        write_tsv(d, "inventory.txt", ["class", "gridX", "gridY"], [["Amazon", 10, 6], ["Big Bank Page 1", 10, 10]])
        write_tsv(d, "experience.txt", ["Level", "Amazon"], [["MaxLvl", 120], [0, 0], [119, 7022000], [120, 666666666]])
        write_tsv(d, "charstats.txt", ["class", "StatPerLevel", "SkillsPerLevel"], [["Amazon", 5, 1], ["Expansion", "", ""]])

    def run_audit(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            self.tables(d, **kw)
            return save_audit.audit(d)

    def test_clean_tables(self):
        f = self.run_audit(unique_rows=[["Fine", "119", "light", "", 2, 4]])
        self.assertEqual([x for x in f if x.level == "error"], [])

    def test_value_below_save_add(self):
        f = self.run_audit(unique_rows=[["Dark", "119", "light", "", -20, -20]])
        errors = [x for x in f if x.level == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIn("-20", errors[0].text)

    def test_unsaved_stat_and_layer_overflow(self):
        f = self.run_audit(unique_rows=[["NoSave", "119", "nosave", "", 1, 1], ["Wide", "119", "kill-skill", "Big", 10, 5]])
        self.assertTrue(any(x.level == "warn" and "unsaved_stat" in x.text for x in f))
        self.assertTrue(any(x.level == "error" and "16-bit stat layer" in x.text for x in f))

    def test_skills_stack_and_codes(self):
        f = self.run_audit(unique_rows=[], skills_per_class=31, maxstack=600)
        text = " | ".join(map(repr, f))
        self.assertIn("31 skills", text)
        self.assertIn("aqv maxstack 600", text)
        self.assertNotIn("gld", text)  # gold is a character stat, not an item stack
        self.assertIn("~:1", text)  # a character Median does not use has no escape path


if __name__ == "__main__":
    unittest.main()
