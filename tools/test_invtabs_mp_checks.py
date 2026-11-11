"""Tests for the pure parts of tools/invtabs_mp_checks.py (no game, no slot)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (test temp files stay in the project)
import invtabs_mp_checks as m  # noqa: E402

TOML = """[d2rloader.advanced]

# TCP port used for both hosting and joining TCP/IP games.
game_port = 4000

# Automatically request a temporary matching TCP port mapping from the router.
automatic_port_mapping = true

# Check from outside your network whether the configured game port is reachable.
hosting_check = true   # trailing note
"""


class TomlKeys(unittest.TestCase):
    def test_sets_both_keys_and_keeps_the_rest(self):
        out, missing = m.set_toml_keys(TOML, m.NET_KEYS)
        self.assertEqual(missing, [])
        self.assertEqual(m.toml_value(out, "automatic_port_mapping"), "false")
        self.assertEqual(m.toml_value(out, "hosting_check"), "false")
        self.assertIn("# trailing note", out)
        self.assertEqual(m.toml_value(out, "game_port"), "4000")
        self.assertEqual(out.count("\n"), TOML.count("\n"))

    def test_missing_key_is_reported(self):
        out, missing = m.set_toml_keys("game_port = 4000\n", m.NET_KEYS)
        self.assertEqual(sorted(missing), ["automatic_port_mapping", "hosting_check"])
        self.assertEqual(out, "game_port = 4000\n")

    def test_comment_lines_are_not_keys(self):
        text = "# automatic_port_mapping = true\nautomatic_port_mapping = true\n"
        out, _ = m.set_toml_keys(text, {"automatic_port_mapping": False})
        self.assertEqual(out, "# automatic_port_mapping = true\nautomatic_port_mapping = false\n")


class LoaderLines(unittest.TestCase):
    def test_classify(self):
        lines = ["[INFO] TCP/IP hosting is using TCP port 4000.",
                 "[INFO] Automatic port mapping is disabled for TCP/IP host port 4000.",
                 "[WARN] Plugin charm-inv rejected: Incompatible",
                 "[INFO] nothing here"]
        tags = m.classify_loader_lines(lines)
        self.assertIn("hosting", tags)
        self.assertIn("mapping_off", tags)
        self.assertNotIn("mapping_on", tags)
        self.assertEqual(len(tags["refused"]), 1)


class Verdicts(unittest.TestCase):
    def test_all_pass(self):
        rows = m.charminv_verdict({"base": 20, "bag": 27, "both": 30}, {"joined": 30, "bag_to_page6": 30, "page6_to_bag": 30})
        self.assertTrue(all(ok for _, ok, _ in rows))
        self.assertEqual(len(rows), 5)

    def test_joiner_page6_not_counted(self):
        rows = dict((n, ok) for n, ok, _ in m.charminv_verdict({"base": 20, "bag": 27, "both": 30}, {"joined": 27}))
        self.assertFalse(rows["joiner: both charms count after joining"])
        self.assertTrue(rows["sp: CharmInv charm counts"])

    def test_missing_values_fail(self):
        rows = m.charminv_verdict({}, {})
        self.assertFalse(any(ok for _, ok, _ in rows))


class FullVerdicts(unittest.TestCase):
    SP = {"base": 20, "bag": 27, "page": 40, "uniq_a": 40, "uniq_b": 40}

    def test_all_pass(self):
        mp = {"server": {"joined": {"str": 40, "life": 300 << 8, "maxlife": 300 << 8}, "bag_in": {"str": 40}},
              "host_seen_bag": {"str": 25}}
        sp = dict(self.SP, final={"str": 40, "page6_codes": [("x1x", "6", "0")], "bag_codes": []})
        rows = m.full_verdict(sp, mp, None, [("on the joiner", "button")])
        self.assertTrue(all(ok for _, ok, _ in rows), [x for x in rows if not x[1]])
        names = [n for n, _, _ in rows]
        self.assertIn("server counts the joiner's charms (bag_in)", names)
        self.assertIn("CharmInv panel opens on the joiner", names)

    def test_server_misses_page6_and_skips(self):
        mp = {"server": {"joined": {"str": 37}, "bag_in": {"str": None, "joiner_note": "skipped: no panel"},
                         "page_out": {"str": 37, "joiner_note": "skipped: the CharmInv panel did not open"}}}
        rows = dict((n, ok) for n, ok, _ in m.full_verdict(self.SP, mp, None, [("on the joiner", None)]))
        self.assertFalse(rows["server counts the joiner's charms (joined)"])
        self.assertNotIn("server counts the joiner's charms (bag_in)", rows)
        self.assertNotIn("server counts the joiner's charms (page_out)", rows)
        self.assertFalse(rows["CharmInv panel opens on the joiner"])

    def test_session_owner(self):
        self.assertEqual(m.session_owner("invtabs-mp", 3), "invtabs-mp-s3")
        self.assertIsNone(m.session_owner(None, 3))


class Barriers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [0.0]
        self.b = m.Barrier(self.tmp.name, sleep=lambda s: self.now.__setitem__(0, self.now[0] + s), clock=lambda: self.now[0])

    def tearDown(self):
        self.tmp.cleanup()

    def test_post_and_wait(self):
        self.b.post("hosted", {"port": 4000})
        self.assertEqual(self.b.wait("hosted", 5), {"port": 4000})
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "sync", "hosted.tmp")))

    def test_timeout(self):
        with self.assertRaises(TimeoutError):
            self.b.wait("never", 3)
        self.assertGreaterEqual(self.now[0], 3)

    def test_abort_ends_the_wait(self):
        self.b.abort("join: slot lock")
        self.b.abort("second reason is ignored")
        with self.assertRaises(RuntimeError) as e:
            self.b.wait("hosted", 100)
        self.assertIn("slot lock", str(e.exception))

    def test_bad_names(self):
        for name in ("../x", "A", "a b", ""):
            with self.assertRaises(ValueError):
                self.b.post(name)


class Plugins(unittest.TestCase):
    def test_plugin_set_and_diff(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for root, files in ((a, {"x.dll": 3, "c.mpq": 2, "note.txt": 1}), (b, {"x.dll": 4, "y.dll": 1})):
                d = os.path.join(root, "mods", "mxl2012", "d2rloader", "plugins")
                os.makedirs(d)
                for n, size in files.items():
                    with open(os.path.join(d, n), "wb") as f:
                        f.write(b"0" * size)
            pa, pb = m.plugin_set(a), m.plugin_set(b)
            self.assertEqual(len(pa), 2)  # the .txt is not a plugin file
            only_a, only_b, size = m.plugin_diff(pa, pb)
            self.assertEqual([os.path.basename(n) for n in only_a], ["c.mpq"])
            self.assertEqual([os.path.basename(n) for n in only_b], ["y.dll"])
            self.assertEqual([os.path.basename(n) for n in size], ["x.dll"])


class Checkbox(unittest.TestCase):
    def image(self, tick):
        from PIL import Image, ImageDraw
        im = Image.new("L", (1600, 900), 40)
        cx, cy = int(m.UI["mp_lan_only"][0] * 1600), int(m.UI["mp_lan_only"][1] * 900)
        d = ImageDraw.Draw(im)
        d.rectangle((cx - 12, cy - 12, cx + 12, cy + 12), outline=130, fill=90)  # the grey box, unticked
        if tick:
            d.line((cx - 6, cy, cx - 1, cy + 6, cx + 7, cy - 6), fill=200, width=3)
        return im

    def test_tick_read(self):
        self.assertTrue(m.checkbox_ticked(self.image(True), *m.UI["mp_lan_only"]))
        self.assertFalse(m.checkbox_ticked(self.image(False), *m.UI["mp_lan_only"]))

    def test_registration_line_is_caught(self):
        tags = m.classify_loader_lines(["[2026-11-11 13:26:20.760] [HOSTING] Host registration was rejected with HTTP 422",
                                        "[WARN] TCP/IP environment admission denied: client=1 reason=shared plugin changed"])
        self.assertIn("registration", tags)
        self.assertIn("env_rejected", tags)

    def test_letters_tag(self):
        for t in (0, 1_731_330_000, 1_731_333_600):
            tag = m.letters_tag(t)
            self.assertTrue(tag.isalpha() and len(tag) == 2, tag)
        self.assertNotEqual(m.letters_tag(0), m.letters_tag(60))


class PanelVisible(unittest.TestCase):
    def test_close_box_read(self):
        from PIL import Image
        for red, want in (((170, 63, 25), True), ((42, 38, 34), False), ((199, 179, 119), False)):
            im = Image.new("RGB", (1600, 900), (20, 20, 20))
            im.putpixel((563, 102), red)
            g = type("G", (), {"grab_client": staticmethod(lambda im=im: im)})()
            w = type("W", (), {"g": g})()
            self.assertEqual(m.Worker.panel_visible(w), want, red)


class Report(unittest.TestCase):
    def test_report_has_minimal_table(self):
        md = m.report_md({"run": "r", "host_slot": 4, "join_slot": 3, "scenario": "charminv"},
                         {"steps": [["hosting", True, "port 4000"]]}, None,
                         [("x", True, "1 -> 2")])
        self.assertIn("|-|-|-|", md)
        self.assertIn("no result", md)
        self.assertIn("hosting: ok (port 4000)", md)
        json.dumps(md)

    def test_ui_fractions_in_range(self):
        for k, (x, y) in m.UI.items():
            self.assertTrue(0 < x < 1 and 0 < y < 1, k)
        for c in range(10):
            self.assertTrue(0 < m.inv_cell(c, 7)[0] < 1 and 0 < m.charminv_cell(c, 3)[1] < 1)


def _it(code, page, x, y):
    return {"code": code, "page": str(page), "x": str(x), "y": str(y)}


def _good_run():
    """The results of a scenario `invtabs` run in which everything went right (fresh characters)."""
    bag = [_it("r01", 0, 2, 0)]

    def view(a, b, cursor=None, strength=35, rune=True):
        items = [_it("x1x", *a)] if a else []
        items += [_it("x2x", *b)] + (bag if rune else [])
        return {"str": strength, "cursor": cursor, "items": items}
    views = {
        "joined": view((0, 0, 0), (0, 1, 0)),
        "drag_in": view((6, 2, 1), (0, 1, 0)),
        "ctrl_in": view((6, 2, 1), (6, 0, 0)),
        "drag_out": view((0, 0, 0), (6, 0, 0)),
        "ctrl_out": view((0, 0, 0), (0, 1, 0)),
        "rune_held": view((0, 0, 0), (0, 1, 0), cursor=[40, "r01"], rune=False),
        "rune_back": view((0, 0, 0), (0, 1, 0)),
        "rune_ctrl": view((0, 0, 0), (0, 1, 0)),
        "outside_held": view(None, (0, 1, 0), cursor=[38, "x1x"], strength=28),
        "placed": view((6, 3, 2), (0, 1, 0)),
        "final": view((6, 3, 2), (6, 0, 0)),
        "after_host": view((6, 3, 2), (6, 0, 0)),
        "rejoined": view((6, 3, 2), (6, 0, 0)),
    }
    join = {"sp": {"str": 35}, "mp": {"link": "areas on; drawn none; pad closed; link joined, full", "server": views},
            "invtabs_log": ["multiplayer: the hosting game's answer for item 40: refused: the tab does not take this item"]}
    mine = [_it("x1x", 6, 0, 0), _it("r02", 0, 1, 0)]
    host = {"own": {"link": "pad closed; link local, 1 joined", "after_items": mine, "rejoin_items": mine, "ctrl_out_back": True},
            "invtabs_log": ["multiplayer: a joined player's item 39 (1x1) to page cell 0,0 of tab charms: moved (item result 0)"]}
    diffs = {"join-0-setup-to-1-after": ["LOST items:1/0/0@0,0:x1x", "NEW  items:1/0/6@3,2:x1x"], "join-1-after-to-2-rejoin": []}
    return join, host, diffs


class InvtabsScenario(unittest.TestCase):
    def test_where_and_outside(self):
        items = [_it("x1x", 6, 2, 1), _it("r01", 0, 4, 0), _it("x2x", 6, 10, 0), _it("a60", 6, 0, 6)]
        self.assertEqual(m.it_where(items, "x1x"), (6, 2, 1))
        self.assertIsNone(m.it_where(items, "zzz"))
        self.assertIsNone(m.it_where(None, "x1x"))
        self.assertEqual(m.it_outside(items), [("x2x", "10", "0"), ("a60", "0", "6")])
        self.assertEqual(m.it_outside(items[:2]), [])

    def test_diff_codes_pair_a_moved_item(self):
        lines = ["stat strength: 25 -> 35", "LOST items:1/0/0@0,0:x1x", "NEW  items:1/0/6@3,2:x1x", "CHANGED items:1/0/0@1,1:hp1: dur 1 -> 2"]
        self.assertEqual(m.diff_codes(lines), (["x1x"], ["x1x"]))
        self.assertEqual(m.diff_codes(["LOST items:1/0/0@0,0:x1x"]), (["x1x"], []))

    def test_a_good_run_passes_every_row(self):
        rows = m.invtabs_verdict(*_good_run())
        self.assertGreater(len(rows), 15)
        self.assertEqual([r for r in rows if not r[1]], [])

    def test_a_charm_outside_the_area_fails(self):
        join, host, diffs = _good_run()
        join["mp"]["server"]["ctrl_in"]["items"][1] = _it("x2x", 6, 12, 3)
        failed = [r[0] for r in m.invtabs_verdict(join, host, diffs) if not r[1]]
        self.assertIn("no item of the joiner on the page outside the tab's area, at any step", failed)
        self.assertIn("Ctrl+click into the tab (joiner, by the host): first free cell", failed)

    def test_a_rune_in_the_tab_and_a_lost_item_fail(self):
        join, host, diffs = _good_run()
        join["mp"]["server"]["rune_ctrl"]["items"][-1] = _it("r01", 6, 1, 0)
        diffs["join-0-setup-to-1-after"] = ["LOST items:1/0/0@0,0:x1x"]
        failed = [r[0] for r in m.invtabs_verdict(join, host, diffs) if not r[1]]
        self.assertIn("rune Ctrl+clicked: refused (stays in the backpack)", failed)
        self.assertIn("save diff join-0-setup-to-1-after: items moved, none lost or new", failed)

    def test_a_missing_worker_or_save_fails_without_raising(self):
        rows = m.invtabs_verdict(None, None, {"host-0-setup-to-1-after": None})
        self.assertTrue(rows and not any(r[1] for r in rows))

    def test_read_only_joiner_rows(self):
        views = {
            "joined": {"str": 60, "cursor": None, "items": [_it("a60", 6, 0, 0), _it("key", 6, 9, 2)]},
            "ro_out": {"cursor": None, "items": [_it("a60", 0, 3, 4), _it("key", 6, 9, 2)]},
            "ro_drag_in": {"cursor": [9, "a60"], "items": [_it("key", 6, 9, 2)]},
            "ro_ctrl_in": {"cursor": None, "items": [_it("a60", 0, 3, 4), _it("key", 6, 9, 2)]},
            "after_host": {"cursor": None, "items": [_it("a60", 0, 3, 4), _it("key", 6, 9, 2)]},
            "rejoined": {"cursor": None, "items": [_it("a60", 0, 3, 4), _it("key", 6, 9, 2)]},
        }
        join = {"readonly": True, "adopt": {"tooth": "a60", "key": "key"}, "mp": {"link": "link joined, read-only", "server": views}}
        mine = [_it("x1x", 6, 5, 3), _it("r02", 0, 1, 0)]
        host = {"own": {"after_items": mine, "rejoin_items": mine, "ctrl_out_back": False}}
        rows = m.invtabs_verdict(join, host, {})
        failed = [r[0] for r in rows if not r[1]]
        self.assertEqual(failed, ["host: Ctrl+click on a charm in the tab moves it to the backpack"])
        self.assertIn("read-only: drag into the tab refused (stays on the cursor)", [r[0] for r in rows])


if __name__ == "__main__":
    unittest.main()
