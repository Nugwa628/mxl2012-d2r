"""tools/slot_share.py on fake slot folders: a mxl2012 run snapshots the slot's shared D2RLoader files, picks its mod on the
command line and puts everything back byte for byte; another mod's folder and settings are never changed. No game runs and
no real lock or slot is touched (slot folders, lock folder and run folder are temp folders)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import game_slots  # noqa: E402
import install_mod  # noqa: E402
import slot_share  # noqa: E402

OTHER_TOML = '[d2rcore.stash]\nadd_shared_tabs = 0\n\n[d2rloader]\ndefault_mod = "OtherMod"\nlaunch_arguments = "-w -txt"\n'


def tree(root):
    """{rel: (bytes, mtime_ns)} of every file under root."""
    out = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            p = os.path.join(dirpath, f)
            out[os.path.relpath(p, root)] = (Path(p).read_bytes(), os.stat(p).st_mtime_ns)
    return out


class LockRoot(unittest.TestCase):
    def test_runs_does_not_change_shared_lock_root_and_override_is_reported(self):
        tmp = tempfile.mkdtemp(prefix="machine-")
        self.addCleanup(shutil.rmtree, tmp, True)
        machine = os.path.join(tmp, "machine.json")
        with open(machine, "w", encoding="utf-8") as f:
            json.dump({"shared_lock_dir": os.path.join(tmp, "shared-locks")}, f)
        env = os.environ.copy()
        env.pop("MXL_LOCKS", None)
        env["MXL_RUNS"] = "independent-run-folder"
        env["MXL_MACHINE"] = machine
        code = "import game_slots; print(game_slots.LOCK_ROOT)"
        result = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(game_slots.__file__),
                                env=env, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), os.path.join(tmp, "shared-locks"))  # machine.json's folder
        self.assertEqual(result.stderr, "")
        env["MXL_LOCKS"] = "explicit-lock-folder"
        result = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(game_slots.__file__),
                                env=env, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), env["MXL_LOCKS"])
        self.assertIn("MXL_LOCKS override: explicit-lock-folder", result.stderr)
        env.pop("MXL_LOCKS")
        env["MXL_MACHINE"] = os.path.join(tmp, "missing.json")
        result = subprocess.run([sys.executable, "slot_share.py", "status", "2"], cwd=os.path.dirname(game_slots.__file__),
                                env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to run", result.stderr)


class FakeSlot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="slotshare-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.game = os.path.join(self.tmp, "D2R-93847")
        g = Path(self.game)
        (g / "d2rloader" / "config").mkdir(parents=True)
        (g / "d2rloader" / "plugins").mkdir()
        (g / "d2rloader" / "patches").mkdir()
        (g / "d2rloader" / "config" / "d2rloader.toml").write_bytes(OTHER_TOML.encode("utf-8-sig").replace(b"\n", b"\r\n"))
        (g / "d2rloader" / "config" / "debugsettings.json").write_text('{"drawGrid": false}')
        (g / "d2rloader" / "config" / "input-bindings.toml").write_text('[bindings."other-core/x"]\nprimary_key = 76\n')
        (g / "d2rloader" / "config" / "imgui.ini").write_text("[Window][Debug]\n")
        for f in ("D2R.exe", "D2RLoader.exe"):
            (g / f).write_bytes(b"MZ")
        sis = g / "mods" / "OtherMod"
        (sis / "OtherMod.mpq").mkdir(parents=True)
        (sis / "OtherMod.mpq" / "modinfo.json").write_text('{"name": "OtherMod", "savepath": "OtherMod-s2/"}')
        (sis / "d2rloader" / "plugins").mkdir(parents=True)
        (sis / "d2rloader" / "plugins" / "other-core.dll").write_bytes(b"MZ other")
        (sis / "d2rloader" / "config").mkdir()
        (sis / "d2rloader" / "config" / "d2rloader.toml").write_text("[d2rcore.stash]\nadd_shared_tabs = 7\n")
        old = time.time() - 3600  # the files are an hour old: a rewrite with the same bytes shows in the mtime
        for dirpath, _, files in os.walk(self.game):
            for f in files:
                os.utime(os.path.join(dirpath, f), (old, old))
        self.locks = os.path.join(self.tmp, "locks")
        self.runs = os.path.join(self.tmp, "runs")
        for p in (patch.dict(os.environ, {"MXL_SLOT2_DIR": self.game}),
                  patch.object(game_slots, "LOCK_ROOT", self.locks), patch.object(game_slots, "RUNS", self.runs),
                  patch.object(game_slots, "SAVE_ROOT", os.path.join(self.tmp, "saves"))):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("MXL_LAUNCH_ARGS", None)
        self.before = tree(self.game)

    def lock(self, owner="slots"):
        ok, _ = game_slots.acquire(2, owner, pid=0)
        self.assertTrue(ok)

    def cfg(self, name):
        return Path(self.game, "d2rloader", "config", name)

    def run_changes(self):
        """What a D2RLoader start does to the shared folder (seen on slot 2): the toml rewritten, files touched, created."""
        self.cfg("d2rloader.toml").write_text(OTHER_TOML.replace('"OtherMod"', '"mxl2012"'))
        self.cfg("input-bindings.toml").write_text('[bindings."other-core/x"]\nprimary_key = 76\n[bindings."mxl2012-core/y"]\nprimary_key = 75\n')
        self.cfg("debugsettings.json").write_text('{"drawGrid": false}')  # same bytes, new mtime
        self.cfg("imgui.ini").unlink()
        (self.cfg("sub")).mkdir()
        (self.cfg("sub") / "new.toml").write_text("x")
        self.cfg("new.json").write_text("{}")


class Snapshot(FakeSlot):
    def test_begin_needs_our_lock(self):
        with self.assertRaises(SystemExit):
            slot_share.begin(2, "slots")
        self.lock("other-lane")
        with self.assertRaises(SystemExit):
            slot_share.begin(2, "slots")
        self.assertIsNone(slot_share.pending(2))

    def test_run_is_restored_byte_for_byte(self):
        self.lock()
        slot_share.begin(2, "slots")
        self.assertIsNotNone(slot_share.pending(2))
        self.run_changes()
        got = dict(slot_share.diff(2))
        self.assertEqual(got["d2rloader/config/d2rloader.toml"], "changed")
        self.assertEqual(got["d2rloader/config/imgui.ini"], "deleted")
        self.assertEqual(got["d2rloader/config/new.json"], "created")
        self.assertTrue(got["d2rloader/config/debugsettings.json"].startswith("touched"))
        msg = slot_share.end(2, "slots", running=[])
        self.assertIn("restored and verified", msg)
        self.assertEqual(tree(self.game), self.before)  # bytes and mtimes of every file, created ones gone
        self.assertFalse(self.cfg("sub").exists())
        self.assertIsNone(slot_share.pending(2))
        rep = json.load(open(os.path.join(slot_share.state_dir(2), "last-restore.json")))
        self.assertIn(["d2rloader/config/d2rloader.toml", "changed"], rep["changed_by_run"])

    def test_restore_refused_while_game_runs_and_snapshot_kept(self):
        self.lock()
        slot_share.begin(2, "slots")
        self.run_changes()
        with self.assertRaises(SystemExit):
            slot_share.end(2, "slots", running=[(1234, "D2RLoader-s2.exe")])
        self.assertIsNotNone(slot_share.pending(2))
        slot_share.end(2, "slots", running=[])
        self.assertEqual(tree(self.game), self.before)

    def test_restore_only_by_lock_owner(self):
        self.lock()
        slot_share.begin(2, "slots")
        with self.assertRaises(SystemExit):
            slot_share.end(2, "someone-else", running=[])
        self.assertIsNotNone(slot_share.pending(2))

    def test_killed_run_is_restored_by_next_begin(self):
        self.lock()
        slot_share.begin(2, "slots")
        self.run_changes()  # the tool died here: no end()
        with patch.object(game_slots, "slot_processes", return_value=[]):
            msg = slot_share.begin(2, "slots")
        self.assertIn("pending snapshot of an earlier run restored first", msg)
        slot_share.end(2, "slots", running=[])
        self.assertEqual(tree(self.game), self.before)

    def test_unlock_restores_first(self):
        self.lock()
        slot_share.begin(2, "slots")
        self.run_changes()
        with patch.object(game_slots, "slot_processes", return_value=[(1, "D2R.exe")]):
            self.assertFalse(game_slots.release(2, "slots", manual=True))  # game still up: lock and snapshot stay
        self.assertIsNotNone(game_slots.lock_info(2))
        with patch.object(game_slots, "slot_processes", return_value=[]):
            self.assertTrue(game_slots.release(2, "slots", manual=True))
        self.assertIsNone(game_slots.lock_info(2))
        self.assertEqual(tree(self.game), self.before)

    def test_other_mod_is_never_touched(self):
        self.lock()
        slot_share.begin(2, "slots")
        self.run_changes()
        slot_share.end(2, "slots", running=[])
        other = {k: v for k, v in tree(self.game).items() if k.startswith(os.path.join("mods", "OtherMod"))}
        self.assertEqual(other, {k: v for k, v in self.before.items() if k.startswith(os.path.join("mods", "OtherMod"))})
        self.assertEqual(len(other), 3)


class Extensions(FakeSlot):
    def test_global_plugin_refuses_the_run(self):
        self.lock()
        Path(self.game, "d2rloader", "plugins", "other-core.dll").write_bytes(b"MZ")
        with self.assertRaises(SystemExit) as e:
            slot_share.begin(2, "slots")
        self.assertIn("loads with every mod", str(e.exception))
        self.assertIsNone(slot_share.pending(2))

    def test_our_plugin_in_the_other_mod_refuses_the_run(self):
        self.lock()
        Path(self.game, "mods", "OtherMod", "d2rloader", "plugins", "mxl2012-core.dll").write_bytes(b"MZ")
        with self.assertRaises(SystemExit):
            slot_share.begin(2, "slots")

    def test_other_plugin_in_its_own_mod_is_fine(self):
        self.assertEqual(slot_share.foreign_extensions(self.game), [])


class LaunchArgs(FakeSlot):
    def test_toml_words_are_not_repeated(self):
        # the other mod's toml already adds "-w -txt": only the mod goes on the command line
        self.assertEqual(slot_share.launch_args(2), ["-mod", "mxl2012"])
        with patch.dict(os.environ, {"MXL_LAUNCH_ARGS": "-w -txt -debug_mode"}):
            self.assertEqual(slot_share.launch_args(2), ["-debug_mode", "-mod", "mxl2012"])

    def test_toml_value_reads_bom_and_crlf(self):
        text = self.cfg("d2rloader.toml").read_bytes().decode("utf-8-sig")
        self.assertEqual(slot_share.toml_value(text, "d2rloader", "launch_arguments"), "-w -txt")
        self.assertIsNone(slot_share.toml_value('[d2rloader]\n# launch_arguments = "x"\n', "d2rloader", "launch_arguments"))

    def test_release_run_without_txt_sets_launch_arguments_inside_the_snapshot(self):
        st = os.path.join(self.runs, "release-install-s2")
        os.makedirs(st)
        Path(st, "release-install.json").write_text(json.dumps({"launch_arguments": "-w"}))
        with self.assertRaises(SystemExit):
            slot_share.launch_args(2)  # no snapshot: the shared toml is not edited
        self.assertEqual(tree(self.game), self.before)
        self.lock()
        slot_share.begin(2, "slots")
        self.assertEqual(slot_share.launch_args(2), ["-mod", "mxl2012"])
        text = self.cfg("d2rloader.toml").read_bytes().decode("utf-8-sig")
        self.assertEqual(slot_share.toml_value(text, "d2rloader", "launch_arguments"), "-w")
        self.assertEqual(slot_share.toml_value(text, "d2rloader", "default_mod"), "OtherMod")  # never ours
        slot_share.end(2, "slots", running=[])
        self.assertEqual(tree(self.game), self.before)

    def test_another_mod_is_refused(self):
        with patch.dict(os.environ, {"MXL_LAUNCH_ARGS": "-w -mod OtherMod"}):
            with self.assertRaises(SystemExit):
                slot_share.launch_args(2)


class SetupAndInstall(FakeSlot):
    def shared_and_other(self):
        return {k: v for k, v in tree(self.game).items() if not k.startswith(os.path.join("mods", "mxl2012"))
                and k != "D2RLoader-s2.exe"}

    def test_setup_leaves_the_shared_config_alone(self):
        game_slots.setup(2)
        self.assertEqual(self.shared_and_other(), self.before)
        self.assertTrue(Path(self.game, "D2RLoader-s2.exe").exists())

    def test_placeholder_install(self):
        self.lock()
        with patch.dict(os.environ, {"MXL_RUN": "slots"}):
            self.assertEqual(install_mod.install_one(Path(self.game), "mxl2012", "mxl2012-s2/", placeholder=True), 0)
        mod = Path(self.game, "mods", "mxl2012")
        self.assertEqual(sorted(p.relative_to(mod).as_posix() for p in mod.rglob("*") if p.is_file()),
                         ["modinfo.json", "mxl2012.mpq/modinfo.json"])
        self.assertEqual(json.loads((mod / "mxl2012.mpq" / "modinfo.json").read_text())["savepath"], "mxl2012-s2/")
        self.assertEqual(self.shared_and_other(), self.before)

    def test_install_refused_without_our_lock_or_for_the_other_mod(self):
        with patch.dict(os.environ, {"MXL_RUN": "slots"}):
            self.assertEqual(install_mod.install_one(Path(self.game), "mxl2012", "mxl2012-s2/", placeholder=True), 1)
            self.lock()
            self.assertEqual(install_mod.install_one(Path(self.game), "OtherMod", "x/", placeholder=True), 1)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MXL_RUN", None)
            self.assertEqual(install_mod.install_one(Path(self.game), "mxl2012", "mxl2012-s2/", placeholder=True), 1)
        self.assertEqual(tree(self.game), self.before)


def denied_writes(*names):
    """builtins.open that refuses writing (as a Program Files folder may without administrator rights) to files whose name
    is in `names` or, with no names, to every file."""
    real_open = open

    def fake(p, mode="r", *a, **k):
        if any(c in mode for c in "wax+") and (not names or os.path.basename(str(p)) in names):
            raise PermissionError(13, "Access is denied", str(p))
        return real_open(p, mode, *a, **k)
    return patch("builtins.open", side_effect=fake)


class OwnerSlot(FakeSlot):
    """The fake folder as slot 1 (the owner's game in Program Files): same snapshot and restore as slots 2 and 3, both locks,
    and a write the folder refuses ends the run or the install cleanly before anything changed."""

    def setUp(self):
        super().setUp()
        p = patch.dict(os.environ, {"MXL_SLOT1_DIR": self.game})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("MXL_SLOT2_DIR", None)
        self.assertEqual(game_slots.slot_of_game_dir(self.game), 1)

    def lock(self, owner="slots"):
        ok, _ = game_slots.acquire(1, owner, pid=0)
        self.assertTrue(ok)

    def test_slot_one_run_is_restored_byte_for_byte(self):
        self.lock()
        self.assertTrue(os.path.isdir(os.path.join(self.locks, "game.lock")), "the old lock is taken too")
        slot_share.begin(1, "slots")
        self.assertTrue(slot_share.state_dir(1).endswith("slot-share-s1"))
        self.run_changes()
        self.assertIn("restored and verified", slot_share.end(1, "slots", running=[]))
        self.assertEqual(tree(self.game), self.before)
        self.assertEqual(slot_share.launch_args(1), ["-mod", "mxl2012"])

    def test_other_legacy_lock_blocks_the_run(self):
        os.makedirs(os.path.join(self.locks, "game.lock"))
        Path(self.locks, "game.lock", "owner.txt").write_text("other pid=0 x", encoding="utf-8")
        with self.assertRaises(SystemExit):
            slot_share.begin(1, "slots")
        self.assertIsNone(slot_share.pending(1))

    def test_run_refused_when_the_shared_files_cannot_be_written(self):
        self.lock()
        with denied_writes("input-bindings.toml"), self.assertRaises(SystemExit) as cm:
            slot_share.begin(1, "slots")
        self.assertIn("refusing the run: no write access to", str(cm.exception))
        self.assertIn("input-bindings.toml", str(cm.exception))
        self.assertIsNone(slot_share.pending(1))
        self.assertEqual(tree(self.game), self.before)

    def test_refused_restore_keeps_snapshot_and_lock(self):
        self.lock()
        slot_share.begin(1, "slots")
        self.run_changes()
        with patch.object(slot_share.shutil, "copy2", side_effect=PermissionError(13, "Access is denied", "x.toml")):
            with self.assertRaises(SystemExit) as cm:
                slot_share.end(1, "slots", running=[])
        self.assertIn("restore refused, no write access", str(cm.exception))
        self.assertIsNotNone(slot_share.pending(1))
        with patch.object(slot_share.shutil, "copy2", side_effect=PermissionError(13, "Access is denied", "x.toml")):
            self.assertFalse(game_slots.release(1, "slots", manual=True))  # unlock keeps the lock while not restored
        self.assertIsNotNone(game_slots.lock_info(1))
        slot_share.end(1, "slots", running=[])
        self.assertEqual(tree(self.game), self.before)

    def test_install_refused_cleanly_when_the_folder_cannot_be_written(self):
        self.lock()
        with patch.dict(os.environ, {"MXL_RUN": "slots"}), denied_writes():
            self.assertEqual(install_mod.install_one(Path(self.game), "mxl2012", "mxl2012-s1/", placeholder=True), 1)
        self.assertEqual(tree(self.game), self.before)
        with patch.dict(os.environ, {"MXL_RUN": "slots"}):
            self.assertEqual(install_mod.install_one(Path(self.game), "mxl2012", "mxl2012-s1/", placeholder=True), 0)
        mod = Path(self.game, "mods", "mxl2012")
        self.assertEqual(json.loads((mod / "mxl2012.mpq" / "modinfo.json").read_text())["savepath"], "mxl2012-s1/")
        self.assertTrue(Path(self.game, "mods", "OtherMod", "d2rloader", "plugins", "other-core.dll").exists())

    def test_setup_makes_no_loader_copy_in_the_owner_folder(self):
        game_slots.setup(1)
        self.assertFalse(Path(self.game, "D2RLoader-s1.exe").exists())
        self.assertEqual(tree(self.game), self.before)


if __name__ == "__main__":
    unittest.main()
