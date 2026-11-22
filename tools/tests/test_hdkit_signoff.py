"""hdkit.signoff: the pure capture helpers (feet pixel, cut box, frame labels, steady-frame pick), the CLI's defaults,
the overlay layout from a monster3d stage and the art store, and the sheet on synthetic results. No game, no GPU."""
import hashlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.signoff import capture, cli, config  # noqa: E402
from hdkit.view import camera  # noqa: E402


class Capture(unittest.TestCase):
    def test_feet_matches_camera(self):
        f = {"x": 103, "y": 98, "px": 100, "py": 100}
        self.assertEqual(capture.feet_px(f), camera.unit_pixel(3, -2))
        self.assertEqual(capture.FEET, camera.FEET_1600x900)

    def test_box(self):
        b = capture.box_of((800.0, 437.5))
        self.assertEqual((b[2] - b[0], b[3] - b[1]), capture.CUT)
        self.assertEqual((800 - b[0], 438 - b[1]), (capture.CUT_FEET[0], capture.CUT_FEET[1] + 0))

    def test_label_and_pick(self):
        p = lambda m, d=8: {"mode": m, "dir": d, "x": 1, "y": 1, "px": 0, "py": 0}  # noqa: E731
        polls = [(0.0, p(1)), (0.1, p(1)), (0.2, p(1)), (0.3, p(4)), (0.4, p(4)), (0.5, p(4)), (0.6, p(4)), (0.7, p(12))]
        frames = [(t + 0.01, (0, 0, 4, 4), "img%d" % i) for i, t in enumerate([0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7])]
        lab = capture.label(0.0, frames, polls)
        self.assertEqual([fr["steady"] for fr in lab], [True, True, False, False, True, True, False, False])
        a1 = capture.pick(lab, "a1")
        self.assertEqual(a1["poll"]["mode"], 4)
        self.assertAlmostEqual(a1["t_mode"], lab[5]["t"] - 0.3 if a1 is lab[5] else a1["t_mode"])
        self.assertIsNone(capture.pick(lab, "gh"))
        self.assertEqual(capture.MODE_INDEX["dd"], 12)


class Facing(unittest.TestCase):
    def test_dir64_matches_game_polls(self):
        # phase 8 polls (unit -> character vector, polled dir64); the game's own table is within 1 of the exact angle
        for v, d in [((-1, 3), 11), ((-2, -1), 29), ((0, -3), 40), ((3, -1), 52), ((2, -1), 51), ((-2, 1), 19), ((1, 1), 0)]:
            self.assertLessEqual(abs((capture.dir64_of(*v) - d + 32) % 64 - 32), 1, v)
        self.assertEqual([capture.key_of(d) for d in (63, 3, 4, 11, 12, 52, 59, 60)], [0, 0, 1, 1, 2, 7, 7, 0])

    def test_spots_for_every_key(self):
        for key in range(8):
            spots = capture.spots_for((500, 600), key, 3)
            self.assertTrue(spots, key)
            for s in spots:
                self.assertEqual(capture.key_toward((500, 600), s), key)
                d = capture.dir64_of(s[0] - 500, s[1] - 600)
                self.assertLessEqual(abs((d - 8 * key + 32) % 64 - 32), 2)
            fx, fy = capture.FACE[key]
            self.assertEqual(capture.key_toward((500, 600), (500 + 3 * fx, 600 + 3 * fy)), key)

    def test_twin_cut(self):
        poll = {"x": 103, "y": 98, "px": 100, "py": 100}
        b, pb = capture.twin_cut((103, 98), (100, 100))
        self.assertEqual(b, capture.box_of(capture.feet_px(poll)))          # character not moved: the frame's own box
        self.assertEqual(pb, [752 - b[0], 278 - b[1], 848 - b[0], 450 - b[1]])
        b2, _ = capture.twin_cut((103, 98), (101, 100))                    # moved one sub-tile: the ground moved 24, 12
        self.assertEqual((b[0] - b2[0], b[1] - b2[1]), (24, 12))

    def test_pick_by_key(self):
        p = lambda d: {"mode": 4, "dir": d, "x": 1, "y": 1, "px": 0, "py": 0}  # noqa: E731
        polls = [(i * 0.1, p(11 if i < 6 else 16)) for i in range(11)]
        lab = capture.label(0.0, [(i * 0.1 + 0.01, (0, 0, 4, 4), i) for i in range(11)], polls)
        self.assertEqual(capture.key_of(capture.pick(lab, "a1")["poll"]["dir"]), 1)
        self.assertEqual(capture.pick(lab, "a1", 2)["poll"]["dir"], 16)
        self.assertIsNone(capture.pick(lab, "a1", 5))


SITE = {"runs_root": "/runs", "units": {"t(": {"id": "unit1", "name": "unit", "stage": "unit/r1/stages/5-x"}},
        "area": 2, "slot": 2, "slots": [2, 5], "lock_holder": "holder"}


def settings(extra=None):
    with mock.patch.object(config, "site_settings", return_value=config.merge(SITE, extra or {})), \
            mock.patch.dict("os.environ", {"HDKIT_SIGNOFF_CONFIG": ""}):
        return config.settings()


class Cli(unittest.TestCase):
    def test_parser_defaults(self):
        s = settings()
        a = cli.build_parser(s).parse_args(["views", "t("])
        self.assertEqual((a.modes, a.facings, a.slot, a.reach, a.rig, a.glow, a.area), ("nu,a1,gh,dt,dd", "0,2,4,6", 2, 3, "game",
                                                                                         True, 2))
        self.assertEqual(a.ev, Path("/runs/hdkit/signoff"))
        with self.assertRaises(SystemExit):
            cli.build_parser(s).parse_args(["run", "t(", "--slot", "1"])
        with mock.patch.object(cli.config, "settings", return_value=s):
            with self.assertRaises(SystemExit):
                cli.main(["views", "zz"])          # unknown token without --id/--stage

    def test_prep(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            m3d, store, ev = d / "m3d", d / "store", d / "ev"
            stage = "mon/round1/stages/5-x"
            (m3d / stage / "overlay" / "hd").mkdir(parents=True)
            (m3d / stage / "overlay" / "hd" / "small.json").write_text("{}")
            (m3d / stage / "build.json").write_text(json.dumps({"unit": "u"}))
            big = b"big file"
            h = hashlib.sha256(big).hexdigest()
            (store / "objects" / "sha256" / h[:2]).mkdir(parents=True)
            (store / "objects" / "sha256" / h[:2] / h).write_bytes(big)
            (m3d / "ART-MANIFEST.json").write_text(json.dumps({"files": [
                {"path": stage + "/overlay/hd/big.model", "sha256": h}]}))
            s = settings({"m3d_ev": str(m3d), "art_store": str(store)})
            over = cli.prep(stage, ev, log=lambda *a: None, s=s)
            self.assertEqual((over / "hd" / "big.model").read_bytes(), big)
            self.assertTrue((over / "hd" / "small.json").is_file())
            self.assertTrue((over.parent / "build.json").is_file())
            self.assertEqual(over.parent.name, "5-x")
            self.assertEqual(cli.build_name(stage, True), "5-x-glowoff")


class Config(unittest.TestCase):
    def test_layers(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "c.json"
            f.write_text(json.dumps({"area": 7, "linux": {"dev_plugin": "/x.dll"}, "capture": {"client": [1920, 1080]}}))
            with mock.patch.object(config, "site_settings", return_value=SITE), \
                    mock.patch.dict("os.environ", {"HDKIT_SIGNOFF_CONFIG": str(f)}):
                s = config.settings()
        self.assertEqual((s["area"], s["slot"], s["lock_holder"]), (7, 2, "holder"))      # file over site over defaults
        self.assertEqual(s["linux"]["dev_plugin"], "/x.dll")
        self.assertEqual(s["linux"]["cpu_max"], 60)                                      # dicts merge key by key
        self.assertEqual(s["capture"]["player_box"], [752, 278, 848, 450])
        self.assertEqual(s["capture"]["client"], [1920, 1080])
        self.assertEqual(s["ev"], str(Path("/runs") / "hdkit" / "signoff"))

    def test_neutral_defaults(self):
        with mock.patch.object(config, "site_settings", return_value={}), \
                mock.patch.dict("os.environ", {"HDKIT_SIGNOFF_CONFIG": "", "HDKIT_STORE": ""}):
            s = config.settings()
        self.assertEqual((s["units"], s["slots"], s["slot"], s["ev"]), ({}, [], None, None))
        with self.assertRaisesRegex(SystemExit, "m3d_ev"):
            config.need(s, "m3d_ev")
        with self.assertRaisesRegex(SystemExit, "linux.framework_tools"):
            config.need(s, "linux", "framework_tools")

    def test_backend_at_run_time(self):
        self.assertEqual(config.backend({"backend": "auto"}, "linux"), "linux")
        self.assertEqual(config.backend({"backend": "auto"}, "win32"), "windows")
        self.assertEqual(config.backend({"backend": "windows"}, "linux"), "windows")

    def test_site_adapter_of_this_repo(self):
        import hdkit_site
        s = hdkit_site.signoff_settings()
        self.assertEqual(s["units"]["2("]["id"], "fungus1")
        self.assertEqual(s["slots"], [2, 5])
        self.assertTrue(Path(s["linux"]["framework_tools"], "game_checks.py").is_file())
        self.assertFalse(s["runs_root"].startswith("D:"))
        # the merged monster lanes live in this checkout: the Windows run uses its own scripts, not sibling worktrees
        self.assertTrue(Path(s["windows"]["gamerun"]).is_file())
        self.assertTrue(Path(s["windows"]["framework_tools"], "game_checks.py").is_file())
        self.assertTrue(Path(s["windows"]["gamerun"]).with_name(s["windows"]["runner"]).is_file())

    def test_site_m3d_ev_follows_the_monster3d_setting(self):
        import hdkit_site
        with mock.patch.dict("os.environ", {"MXL_M3D_DIR": "/x/m3d"}), \
                mock.patch.object(hdkit_site, "_machine", return_value={"m3d_dir": "/y/m3d"}):
            self.assertEqual(hdkit_site.signoff_settings()["m3d_ev"], "/x/m3d")
        with mock.patch.dict("os.environ", {"MXL_M3D_DIR": ""}), \
                mock.patch.object(hdkit_site, "_machine", return_value={"m3d_dir": "/y/m3d"}):
            self.assertEqual(hdkit_site.signoff_settings()["m3d_ev"], "/y/m3d")
        with mock.patch.dict("os.environ", {"MXL_M3D_DIR": ""}), mock.patch.object(
                hdkit_site, "_machine", return_value={"m3d_dir": "/y/m3d", "hdkit_signoff": {"m3d_ev": "/z"}}):
            self.assertEqual(hdkit_site.signoff_settings()["m3d_ev"], "/z")

    def test_facing_constants_match_the_framework(self):
        """capture.py keeps its own copy (signoff/ needs no game_checks): it must stay equal to game_checks mon_turn's."""
        import ast
        tree = ast.parse((TOOLS / "game_checks.py").read_text(encoding="utf-8"))   # no import: game_ctl needs a slot
        got = {t.id: ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               for t in n.targets if isinstance(t, ast.Name) and t.id in ("MON_TURN_FACE", "MON_TURN_SPOTS")}
        self.assertEqual(capture.FACE, got["MON_TURN_FACE"])
        self.assertEqual(capture.SPOTS, got["MON_TURN_SPOTS"])

    def test_no_project_items_in_signoff(self):
        """signoff/ stays mod-neutral: the project's names, places and units come from the settings (p8b portability list)."""
        import re
        pat = re.compile(r"MXL|mxl2012|fungus|hdtools|D:\\\\|py -3 .*heavy|Blood Moor|[\"'](?:mon_moves|g6_\w+\.py)[\"']", re.I)
        for f in sorted((TOOLS / "hdkit" / "signoff").glob("*.py")):
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                code = line.split("#")[0]
                self.assertIsNone(pat.search(code), "%s:%d %s" % (f.name, n, line))


class LinuxRun(unittest.TestCase):
    def test_overlay_plan(self):
        from hdkit.signoff import run as R
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            over, data = d / "over", d / "mod" / "data"
            (over / "hd" / "character" / "enemy").mkdir(parents=True)
            (over / "hd" / "character" / "enemy" / "u.json").write_text("{}")
            (data / "hd" / "character").mkdir(parents=True)
            (data / "hd" / "character" / "monsters.json").write_text(json.dumps({"other": "x", "unit1": "old"}))
            (data / "hd" / "model_lod_desc.bin").write_bytes(b"LOD")
            lod = mock.Mock()
            lod.add.return_value = b"LOD+"
            build = {"unit": "u", "bounds": [[0, 0, 0], [1, 2, 3]], "u": 2.0, "model": "m", "donor_model": "dm"}
            plan = R.overlay_plan(over, build, "unit1", data, d / "work", lod)
            dests = sorted(str(p.relative_to(data)) for p, _ in plan)
            self.assertEqual(dests, ["hd/character/enemy/u.json", "hd/character/monsters.json", "hd/model_lod_desc.bin"])
            table = json.loads((d / "work" / "hd" / "character" / "monsters.json").read_text())
            self.assertEqual(table, {"other": "x", "unit1": "u"})
            lod.add.assert_called_once_with(b"LOD", {"m": "dm"}, {"m": ([0, 0, 0], [2.0, 4.0, 6.0])})
            self.assertEqual(json.loads((data / "hd" / "character" / "monsters.json").read_text())["unit1"], "old")
            with self.assertRaisesRegex(SystemExit, "used before"):
                R.overlay_plan(over, build, "unit1", data, d / "work", lod)

    def _fw(self, d, lock=None, pending=False):
        (d / "wctl").mkdir(exist_ok=True)
        (d / "wctl" / "wctl.exe").write_bytes(b"MZ")
        fw = types.SimpleNamespace()
        fw.game_slots = types.SimpleNamespace(RUNS="/parent/runs", lock_info=lambda n: lock, mod_dir=lambda n: str(d / "slot" / "mods" / "m"),
                                              slot_dir=lambda n: str(d / "slot"))
        fw.slot_share = types.SimpleNamespace(pending=lambda n: pending, state_dir=lambda n: str(d / "state"))
        fw.model_lod_desc = types.SimpleNamespace(add=lambda data, a, b: data + b"+")
        return fw

    def test_run_linux_busy_and_locked(self):
        from hdkit.signoff import run as R
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            s = settings({"linux": {"framework_tools": str(d)}})
            fw = self._fw(d)
            with mock.patch.dict(sys.modules, vars(fw)), mock.patch.object(R, "cpu_load", return_value=95):
                self.assertEqual(R.run_linux(s, "t1", 2, "t(", "unit1", d, d / "ev", {}, log=lambda *a: None), 2)
            fw = self._fw(d, lock=("/locks/game.lock.2", "other pid=1"))
            with mock.patch.dict(sys.modules, vars(fw)), mock.patch.object(R, "cpu_load", return_value=5):
                self.assertEqual(R.run_linux(s, "t2", 2, "t(", "unit1", d, d / "ev", {}, log=lambda *a: None), 3)

    def test_run_linux_plan_env_and_copy(self):
        from hdkit.signoff import run as R
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            data = d / "slot" / "mods" / "m" / "data"
            (data / "hd" / "character").mkdir(parents=True)
            (data / "hd" / "character" / "monsters.json").write_text("{}")
            (data / "hd" / "model_lod_desc.bin").write_bytes(b"LOD")
            over = d / "build" / "overlay"
            (over / "hd").mkdir(parents=True)
            (over / "hd" / "a.json").write_text("{}")
            (d / "build" / "build.json").write_text(json.dumps({"unit": "u", "bounds": [[0], [1]], "u": 1, "model": "m",
                                                                "donor_model": "dm"}))
            dll = d / "dev.dll"
            dll.write_bytes(b"MZ")
            (d / "state").mkdir()
            s = settings({"linux": {"framework_tools": str(d), "mod_data": "data", "plugin_dest": "plugins/core.dll",
                                    "env": {"MXL_CHAR": "Tester"}},
                          "framework_env": {"run": "X_RUN", "slot": "X_SLOT", "runs": "X_RUNS"}})
            seen = {}

            def fake_run(cmd, cwd=None, env=None, stdout=None, stderr=None):
                seen.update(cmd=cmd, env=env)
                run = Path(env["X_RUNS"]) / "checks-1-s5"
                run.mkdir(parents=True)
                (run / "signoff_index.json").write_text("[]")
                (run / "big.bin").write_bytes(b"x")
                (d / "state" / "last-restore.json").write_text(json.dumps({"verified": "all", "changed_by_run": [1, 2]}))
                return types.SimpleNamespace(returncode=0)
            fw = self._fw(d)
            with mock.patch.dict(sys.modules, vars(fw)), mock.patch.object(R, "cpu_load", return_value=5), \
                    mock.patch.object(R.subprocess, "run", side_effect=fake_run):
                rc = R.run_linux(s, "t3", 5, "t(", "unit1", over, d / "ev", {"HDKIT_SIGNOFF_AREA": "2"}, dll=str(dll),
                                 log=lambda *a: None)
            self.assertEqual(rc, 0)
            self.assertEqual(seen["cmd"][2:], ["--slot", "5", "all", "signoff"])
            e = seen["env"]
            self.assertEqual((e["X_RUN"], e["X_SLOT"], e["MXL_CHAR"], e["HDKIT_SIGNOFF_ID"], e["HDKIT_SIGNOFF_AREA"]),
                             ("holder", "5", "Tester", "unit1", "2"))
            plan = json.loads(Path(e["HDKIT_SIGNOFF_PLAN"]).read_text())
            self.assertEqual(plan["game"], str(d / "slot"))
            dests = sorted(Path(x).relative_to(d / "slot" / "mods" / "m").as_posix() for x, _ in plan["files"])
            self.assertEqual(dests, ["data/hd/a.json", "data/hd/character/monsters.json", "data/hd/model_lod_desc.bin",
                                     "plugins/core.dll"])
            shots = d / "ev" / "unit" / "shots" / "t3"
            self.assertTrue((shots / "signoff_index.json").is_file())
            self.assertFalse((shots / "big.bin").exists())
            self.assertTrue((shots / "slot-restore.json").is_file())
            self.assertFalse((data / "hd" / "a.json").exists())      # nothing is laid before the snapshot (the hook does)
            self.assertEqual(fw.game_slots.RUNS, "/parent/runs")       # the check's runs folder only while it ran

    def test_run_linux_needs_the_window_helper(self):
        from hdkit.signoff import run as R
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fw = self._fw(d)
            (d / "wctl" / "wctl.exe").unlink()
            s = settings({"linux": {"framework_tools": str(d)}})
            with mock.patch.dict(sys.modules, vars(fw)):
                self.assertEqual(R.run_linux(s, "t4", 2, "t(", "unit1", d, d / "ev", {}, log=lambda *a: None), 4)


class LayPlan(unittest.TestCase):
    def test_lay_plan_inside_the_game_folder_only(self):
        sys.path.insert(0, str(TOOLS / "hdkit" / "signoff"))
        import os
        os.environ.setdefault("MXL_SLOT", "2")   # importing the framework's game_ctl needs a slot; nothing starts a game
        with mock.patch.dict("os.environ", {"HDKIT_SIGNOFF_FWT": str(TOOLS)}):
            import gamecheck
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            game, run = d / "game", d / "run"
            game.mkdir()
            run.mkdir()
            src = d / "a.bin"
            src.write_bytes(b"abc")
            plan = d / "plan.json"
            plan.write_text(json.dumps({"game": str(game), "files": [[str(game / "mods" / "x" / "a.bin"), str(src)]]}))
            with mock.patch.object(gamecheck.g, "GAME_DIR", str(game)), \
                    mock.patch.object(gamecheck.g, "current_run", return_value=str(run)):
                self.assertEqual(gamecheck.lay_plan(str(plan)), "1 files laid into the slot")
                self.assertEqual((game / "mods" / "x" / "a.bin").read_bytes(), b"abc")
                laid = json.loads((run / "signoff_plan.json").read_text())
                self.assertEqual(laid[0]["sha256"], hashlib.sha256(b"abc").hexdigest())
                plan.write_text(json.dumps({"game": str(game), "files": [[str(d / "elsewhere.bin"), str(src)]]}))
                with self.assertRaisesRegex(RuntimeError, "outside the game folder"):
                    gamecheck.lay_plan(str(plan))
                plan.write_text(json.dumps({"game": str(d), "files": []}))
                with self.assertRaisesRegex(RuntimeError, "this run's game folder"):
                    gamecheck.lay_plan(str(plan))
            self.assertFalse((d / "elsewhere.bin").exists())

    def test_capture_configure(self):
        old = (capture.CLIENT, capture.FEET, capture.PLAYER_BOX)
        try:
            capture.configure(client=[1920, 1080], feet_px=[960, 525], player_box=[1, 2, 3, 4])
            self.assertEqual(capture.feet_px({"x": 1, "y": 0, "px": 0, "py": 0}), (984.0, 537.0))
            self.assertEqual(capture.twin_cut((0, 0), (0, 0))[1], [1 - 760, 2 - 225, 3 - 760, 4 - 225])
        finally:
            capture.CLIENT, capture.FEET, capture.PLAYER_BOX = old


class Sheet(unittest.TestCase):
    def test_sheet(self):
        from PIL import Image
        from hdkit.signoff import views
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            g = np.full((400, 400, 3), 60, np.uint8)
            r = np.zeros((400, 400, 4), np.uint8)
            r[220:300, 170:230] = (200, 200, 255, 255)
            Image.fromarray(g).save(d / "g.png")
            Image.fromarray(g).save(d / "t.png")
            Image.fromarray(r).save(d / "r.png")
            Image.fromarray(np.concatenate([g, np.zeros((400, 4, 3), np.uint8), g], 1)).save(d / "p.png")
            res = [{"mode": "nu", "key": 0, "dir64": 3, "t_mode": 0.2, "game": str(d / "g.png"), "twin": str(d / "t.png"),
                    "render": str(d / "r.png"), "panel": str(d / "p.png"), "shot_feet": [200, 300],
                    "render_feet": [200, 300], "iou_at_feet": 0.5, "iou_best": 0.6, "shift": [1, 0], "luma_game": 50.0,
                    "luma_render": 40.0, "luma_ratio": 0.8, "cap_game": [1, 2, 3], "cap_render": None, "cap_distance": None}]
            p = views.sheet(res, d / "s.png", "t", ["nu", "dd"], [0, 2])
            with Image.open(p) as im:
                self.assertGreaterEqual(im.size[0], 1100)


if __name__ == "__main__":
    unittest.main()
