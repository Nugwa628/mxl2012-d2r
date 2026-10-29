"""tools/localconfig.py and tools/lane_setup.py: the setup of a fresh worktree (bugs #210-#219, lane toolchain).

Host-independent (CI runs this on Linux): no DLL, no CMake, no game; the git parts use throw-away repositories in a temp folder.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import fxpaths  # noqa: E402
import lane_setup  # noqa: E402
import localconfig  # noqa: E402

GIT = ["git", "-c", "user.name=t", "-c", "user.email=tester", "-c", "commit.gpgsign=false"]


def fake_extract(root: Path, banks=("base", "")) -> Path:
    for b in banks:
        d = root / "data" / "global" / "excel" / b
        d.mkdir(parents=True, exist_ok=True)
        (d / "skills.txt").write_text("skill\n")
    return root


def run_tool(script: str, env: dict, *args: str) -> subprocess.CompletedProcess:
    """A tool as a lane runs it (py -I), with the machine's MXL_* settings removed and `env` added."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("MXL_", "MXL2012_"))}
    clean.update(env)
    return subprocess.run([sys.executable, "-I", str(TOOLS / script), *args], capture_output=True, text=True, env=clean, timeout=120)


class LocalConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_load_keeps_only_known_string_settings(self):
        f = self.dir / "c.json"
        f.write_text(json.dumps({"_comment": "x", "MXL_D2R_EXTRACT": "/a", "PATH": "/evil", "MXL_D2R_CACHE": 5, "MXL_NATIVE_DIR": ""}))
        self.assertEqual(localconfig.load(f), {"MXL_D2R_EXTRACT": "/a"})

    def test_load_missing_file_is_empty_and_damaged_file_is_an_error(self):
        self.assertEqual(localconfig.load(self.dir / "none.json"), {})
        bad = self.dir / "bad.json"
        bad.write_text("{nope")
        with self.assertRaises(SystemExit) as cm:
            localconfig.load(bad)
        self.assertIn("lane_setup.py", str(cm.exception))
        bad.write_text("[1]")
        with self.assertRaises(SystemExit):
            localconfig.load(bad)

    def test_apply_does_not_override_the_environment(self):
        f = self.dir / "c.json"
        localconfig.save({"MXL_D2R_EXTRACT": "/from-file", "MXL_D2R_CACHE": "/cache-file"}, f)
        env = {"MXL_D2R_EXTRACT": "/from-env"}
        done = localconfig.apply(env, f)
        self.assertEqual(env, {"MXL_D2R_EXTRACT": "/from-env", "MXL_D2R_CACHE": "/cache-file"})
        self.assertEqual(done, {"MXL_D2R_CACHE": "/cache-file"})

    def test_save_writes_only_known_nonempty_keys(self):
        f = self.dir / "c.json"
        localconfig.save({"MXL_D2R_EXTRACT": "/a", "MXL_NATIVE_DIR": "", "OTHER": "x"}, f)
        data = json.loads(f.read_text())
        self.assertEqual({k for k in data if not k.startswith("_")}, {"MXL_D2R_EXTRACT"})

    def test_extract_probe_needs_both_banks(self):
        self.assertEqual(len(localconfig.d2r_extract_ok(self.dir)), 2)
        fake_extract(self.dir, banks=("",))
        self.assertEqual(localconfig.d2r_extract_ok(self.dir), ["data/global/excel/base/skills.txt"])
        fake_extract(self.dir)
        self.assertEqual(localconfig.d2r_extract_ok(self.dir), [])

    def test_require_d2r_extract_fails_loudly(self):
        with self.assertRaises(SystemExit) as cm:
            localconfig.require_d2r_extract(self.dir / "nothing", "txt_migrate")
        msg = str(cm.exception)
        self.assertIn("txt_migrate", msg)
        self.assertIn("MXL_D2R_EXTRACT", msg)
        self.assertIn("lane_setup.py", msg)
        self.assertEqual(localconfig.require_d2r_extract(fake_extract(self.dir / "ok"), "x"), self.dir / "ok")

    def test_default_extract_prefers_the_environment(self):
        with mock.patch.dict(os.environ, {"MXL_D2R_EXTRACT": "/somewhere"}):
            self.assertEqual(localconfig.default_d2r_extract(), Path("/somewhere"))

    def test_default_extract_falls_back_to_the_reference(self):
        ref = self.dir / "reference"
        fake_extract(ref / "extract" / "d2r" / "93847")
        env = {k: v for k, v in os.environ.items() if k != "MXL_D2R_EXTRACT"}
        env["MXL_REFERENCE"] = str(ref)
        env["MXL_MACHINE"] = str(self.dir / "no-machine.json")
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(localconfig, "ROOT", self.dir / "no-repo"):
            self.assertEqual(localconfig.default_d2r_extract(), ref / "extract" / "d2r" / "93847")

    def test_default_extract_uses_the_machine_extract_dir(self):
        ext = fake_extract(self.dir / "machine-extract")
        (self.dir / "machine.json").write_text(json.dumps({"extract_dir": str(ext)}))
        env = {k: v for k, v in os.environ.items() if k not in ("MXL_D2R_EXTRACT", "MXL_REFERENCE")}
        env["MXL_MACHINE"] = str(self.dir / "machine.json")
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(localconfig, "ROOT", self.dir / "no-repo"):
            self.assertEqual(localconfig.default_d2r_extract(), ext)

    def test_require_machine_refuses_without_the_safety_keys(self):
        (self.dir / "machine.json").write_text(json.dumps({"shared_lock_dir": "x", "_comment": "y"}))
        with mock.patch.dict(os.environ, {"MXL_MACHINE": str(self.dir / "machine.json")}):
            with self.assertRaises(SystemExit) as cm:
                localconfig.require_machine(tool="game_slots")
            self.assertIn("protected_mod_folders", str(cm.exception))
            self.assertNotIn("_comment", localconfig.machine())
        with mock.patch.dict(os.environ, {"MXL_MACHINE": str(self.dir / "none.json")}):
            with self.assertRaises(SystemExit):
                localconfig.require_machine(tool="game_slots")

    def test_runs_dir_is_found_beside_the_main_checkout_and_above_a_lane(self):
        r = self.dir / "R"
        (r / "mxl2012-runs").mkdir(parents=True)
        main, lane = r / "MXL2012-D2R", r / "mxl2012-wt" / "lane"
        self.assertEqual(localconfig.default_runs_dir(main), r / "mxl2012-runs")
        self.assertEqual(localconfig.default_runs_dir(lane), r / "mxl2012-runs")
        env = {k: v for k, v in os.environ.items() if k not in ("MXL2012_RUNS", "MXL_MACHINE")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(localconfig, "ROOT", main):
            self.assertEqual(localconfig.runs_dir(), r / "mxl2012-runs")
            self.assertEqual(localconfig.machine_path(), r / "mxl2012-runs" / "machine.json")
        with mock.patch.dict(os.environ, {"MXL2012_RUNS": str(self.dir / "elsewhere")}):
            self.assertEqual(localconfig.runs_dir(), self.dir / "elsewhere")

    def test_native_dll_candidates_local_build_first(self):
        with mock.patch.dict(os.environ, {"MXL_NATIVE_DIR": str(self.dir / "shared")}):
            c = localconfig.native_dll_candidates("StormLib")
        self.assertEqual(c[0], localconfig.ROOT / "build" / "StormLib" / "Release" / "StormLib.dll")
        self.assertEqual(c[1], self.dir / "shared" / "StormLib" / "Release" / "StormLib.dll")

    def test_find_native_dll_prefers_local_then_shared_then_explains(self):
        shared = self.dir / "shared"
        with mock.patch.dict(os.environ, {"MXL_NATIVE_DIR": str(shared)}), mock.patch.object(localconfig, "ROOT", self.dir / "repo"):
            with self.assertRaises(FileNotFoundError) as cm:
                localconfig.find_native_dll("CascLib")
            self.assertIn("lane_setup.py", str(cm.exception))
            (shared / "CascLib" / "Release").mkdir(parents=True)
            (shared / "CascLib" / "Release" / "CascLib.dll").write_bytes(b"x")
            self.assertEqual(localconfig.find_native_dll("CascLib"), shared / "CascLib" / "Release" / "CascLib.dll")
            (self.dir / "repo" / "build" / "CascLib" / "Release").mkdir(parents=True)
            (self.dir / "repo" / "build" / "CascLib" / "Release" / "CascLib.dll").write_bytes(b"y")
            self.assertEqual(localconfig.find_native_dll("CascLib"),
                             self.dir / "repo" / "build" / "CascLib" / "Release" / "CascLib.dll")


class MissingExtractionFailsLoudlyTests(unittest.TestCase):
    """The old behaviour: no extraction -> txt_migrate skipped every table, exited 0 and wrote an empty mod."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.empty = str(Path(self.tmp.name) / "empty")
        Path(self.empty).mkdir()

    def assert_refuses(self, r):
        self.assertEqual(r.returncode, 1, (r.stdout, r.stderr))  # SystemExit(message) -> 1, the message on stderr
        self.assertIn("not a D2R extraction", r.stderr)
        self.assertIn("lane_setup.py", r.stderr)

    def test_txt_migrate(self):
        self.assert_refuses(run_tool("txt_migrate.py", {"MXL_D2R_EXTRACT": self.empty}))

    def test_validate(self):
        self.assert_refuses(run_tool("validate.py", {"MXL_D2R_EXTRACT": self.empty}))

    def test_build_stops_before_it_runs_or_deletes_anything(self):
        r = run_tool("build.py", {"MXL_D2R_EXTRACT": self.empty, "MXL_SKIP_ASSET_CHECK": "1"}, "--data-only")
        self.assert_refuses(r)
        self.assertNotIn("== mxl2012_prep.py", r.stdout)


class D2rFileCacheTests(unittest.TestCase):
    def test_missing_cache_file_without_a_slot_says_what_to_do(self):
        with tempfile.TemporaryDirectory() as tmp:
            ext = fake_extract(Path(tmp) / "ext")
            code = "import sys; sys.path.insert(0, %r); import fxpaths; fxpaths.d2r_file('data/hd/x.json')" % str(TOOLS)
            clean = {k: v for k, v in os.environ.items() if not k.startswith(("MXL_", "MXL2012_"))}
            clean.update(MXL_D2R_EXTRACT=str(ext), MXL_D2R_CACHE=str(Path(tmp) / "cache"))
            r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=clean, timeout=60)
            self.assertEqual(r.returncode, 1)
            self.assertIn("lane_setup.py", r.stderr)
            self.assertIn("data/hd/x.json", r.stderr)

    def test_cache_dir_follows_mxl_d2r_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = "import sys; sys.path.insert(0, %r); import fxpaths; print(fxpaths.D2R_CACHE)" % str(TOOLS)
            clean = {k: v for k, v in os.environ.items() if not k.startswith(("MXL_", "MXL2012_"))}
            clean["MXL_D2R_CACHE"] = tmp
            r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env=clean, timeout=60)
            self.assertEqual(Path(r.stdout.strip()), Path(tmp))


class SharedLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.shared = Path(self.tmp.name) / "shared"
        self.addCleanup(self.tmp.cleanup)

    def test_enter_creates_and_exit_removes(self):
        with lane_setup.SharedLock(self.shared) as lock:
            self.assertTrue((lock.path / "owner.txt").exists())
        self.assertFalse((self.shared / ".lock").exists())

    def test_held_lock_times_out_with_its_owner(self):
        with lane_setup.SharedLock(self.shared):
            with self.assertRaises(SystemExit) as cm:
                with lane_setup.SharedLock(self.shared, timeout=0.05, poll=0.01):
                    pass
            self.assertIn(f"pid={os.getpid()}", str(cm.exception))
        self.assertFalse((self.shared / ".lock").exists())

    def test_old_lock_of_a_dead_process_is_taken_over(self):
        lock = self.shared / ".lock"
        lock.mkdir(parents=True)
        (lock / "owner.txt").write_text("pid=999999 2026-01-01 00:00:00\n")
        old = time.time() - lane_setup.LOCK_STALE_SECONDS - 10
        os.utime(lock, (old, old))
        with lane_setup.SharedLock(self.shared, timeout=1, alive=lambda pid: False):
            self.assertIn(f"pid={os.getpid()}", (lock / "owner.txt").read_text())

    def test_old_lock_of_a_live_process_is_kept(self):
        lock = self.shared / ".lock"
        lock.mkdir(parents=True)
        (lock / "owner.txt").write_text("pid=4242 2026-01-01 00:00:00\n")
        old = time.time() - lane_setup.LOCK_STALE_SECONDS - 10
        os.utime(lock, (old, old))
        with self.assertRaises(SystemExit):
            with lane_setup.SharedLock(self.shared, timeout=0.05, poll=0.01, alive=lambda pid: True):
                pass

    def test_young_lock_is_never_stale(self):
        lock = self.shared / ".lock"
        lock.mkdir(parents=True)
        (lock / "owner.txt").write_text("pid=1 x\n")
        self.assertFalse(lane_setup.SharedLock(self.shared, alive=lambda pid: False).stale())


def git(cwd: Path, *args: str) -> str:
    r = subprocess.run([*GIT, *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


class SourceCloneTests(unittest.TestCase):
    """ensure_source: the pinned commit of an (empty) submodule is cloned from a local checkout, never downloaded."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        # a reference checkout whose third_party/StormLib is a git checkout with two commits
        self.ref = self.dir / "reference"
        lib = self.ref / "third_party" / "StormLib"
        lib.mkdir(parents=True)
        git(lib, "init", "-q")
        (lib / "CMakeLists.txt").write_text("project(x)\n")
        git(lib, "add", ".")
        git(lib, "commit", "-q", "-m", "one")
        self.first = git(lib, "rev-parse", "HEAD")
        (lib / "more.txt").write_text("2\n")
        git(lib, "add", ".")
        git(lib, "commit", "-q", "-m", "two")
        # the repo being set up: StormLib pinned at the first commit, its folder empty (a fresh worktree)
        self.root = self.dir / "wt"
        (self.root / "third_party" / "StormLib").mkdir(parents=True)
        git(self.root, "init", "-q")
        git(self.root, "update-index", "--add", "--cacheinfo", f"160000,{self.first},third_party/StormLib")
        git(self.root, "commit", "-q", "-m", "pin")
        self.shared_src = self.dir / "runs" / "shared" / "native" / "src"
        self.env = mock.patch.dict(os.environ, {"MXL_REFERENCE": str(self.ref)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_pinned_commits_reads_the_gitlinks(self):
        self.assertEqual(lane_setup.pinned_commits(self.root), {"StormLib": self.first})

    def test_empty_submodule_is_not_a_source(self):
        self.assertIsNone(lane_setup.head_of(self.root / "third_party" / "StormLib"))

    def test_clones_the_pinned_commit_not_the_tip(self):
        rep = lane_setup.Report()
        dest = lane_setup.ensure_source(self.root, "StormLib", self.first, self.shared_src, rep, False)
        self.assertEqual(dest, self.shared_src / "StormLib")
        self.assertEqual(lane_setup.head_of(dest), self.first)
        self.assertFalse((dest / "more.txt").exists())
        self.assertEqual(rep.rows[-1][0], "ok")

    def test_second_call_reuses_the_clone(self):
        lane_setup.ensure_source(self.root, "StormLib", self.first, self.shared_src, lane_setup.Report(), False)
        rep = lane_setup.Report()
        with mock.patch.object(lane_setup, "reference_repos", side_effect=AssertionError("must not clone again")):
            dest = lane_setup.ensure_source(self.root, "StormLib", self.first, self.shared_src, rep, False)
        self.assertEqual(dest, self.shared_src / "StormLib")

    def test_check_only_changes_nothing(self):
        rep = lane_setup.Report()
        self.assertIsNone(lane_setup.ensure_source(self.root, "StormLib", self.first, self.shared_src, rep, True))
        self.assertEqual(rep.rows[-1][0], "FAIL")
        self.assertFalse(self.shared_src.exists())

    def test_commit_in_no_local_checkout_is_a_failure_that_names_the_options(self):
        rep = lane_setup.Report()
        missing = "1" * 40
        self.assertIsNone(lane_setup.ensure_source(self.root, "StormLib", missing, self.shared_src, rep, False))
        status, _, detail = rep.rows[-1]
        self.assertEqual(status, "FAIL")
        self.assertIn("MXL_NATIVE_REF", detail)
        self.assertFalse((self.shared_src / "StormLib").exists())

    def test_populated_submodule_at_the_pin_is_used_as_it_is(self):
        sub = self.root / "third_party" / "StormLib"
        git(self.dir, "clone", "-q", str(self.ref / "third_party" / "StormLib"), str(sub / "tmp"))
        # make the submodule folder itself the checkout at the pin
        for item in (sub / "tmp").iterdir():
            item.rename(sub / item.name)
        (sub / "tmp").rmdir()
        git(sub, "checkout", "-q", self.first)
        rep = lane_setup.Report()
        self.assertEqual(lane_setup.ensure_source(self.root, "StormLib", self.first, self.shared_src, rep, False), sub)
        self.assertFalse(self.shared_src.exists())

    def test_native_reference_env_comes_first(self):
        other = self.dir / "other"
        other.mkdir()
        git(other, "clone", "-q", str(self.ref / "third_party" / "StormLib"), "StormLib")
        with mock.patch.dict(os.environ, {"MXL_NATIVE_REF": str(other)}):
            refs = lane_setup.reference_repos(self.root, "StormLib")
        self.assertEqual(refs[0], other / "StormLib")


class DllStateTests(unittest.TestCase):
    def test_built_at_needs_dll_and_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self.assertIsNone(lane_setup.built_at(base, "StormLib"))
            (base / "StormLib" / "Release").mkdir(parents=True)
            (base / "StormLib" / "Release" / "StormLib.dll").write_bytes(b"x")
            self.assertIsNone(lane_setup.built_at(base, "StormLib"))
            (base / "StormLib" / ".source-sha").write_text("abc\n")
            self.assertEqual(lane_setup.built_at(base, "StormLib"), "abc")

    def test_up_to_date_shared_build_needs_no_powershell(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, shared = Path(tmp) / "wt", Path(tmp) / "shared"
            pins = {"StormLib": "a" * 40, "CascLib": "b" * 40}
            for lib, sha in pins.items():
                d = shared / "native" / "build" / lib
                (d / "Release").mkdir(parents=True)
                (d / "Release" / f"{lib}.dll").write_bytes(b"x")
                (d / ".source-sha").write_text(sha)
            rep = lane_setup.Report()
            with mock.patch.object(lane_setup, "powershell", side_effect=AssertionError("no build expected")):
                base = lane_setup.ensure_native(root, pins, shared, False, rep, False)
            self.assertEqual(base, shared / "native" / "build")
            self.assertFalse(rep.failed)

    def test_stale_shared_build_is_reported_in_check_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, shared = Path(tmp) / "wt", Path(tmp) / "shared"
            rep = lane_setup.Report()
            base = lane_setup.ensure_native(root, {"StormLib": "a" * 40, "CascLib": "b" * 40}, shared, False, rep, True)
            self.assertIsNone(base)
            self.assertEqual([s for s, _, _ in rep.rows], ["FAIL", "FAIL"])

    def test_worktree_with_its_own_build_keeps_using_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, shared = Path(tmp) / "wt", Path(tmp) / "shared"
            for lib in lane_setup.NATIVE_LIBS:
                (root / "build" / lib / "Release").mkdir(parents=True)
                (root / "build" / lib / "Release" / f"{lib}.dll").write_bytes(b"x")
            rep = lane_setup.Report()
            base = lane_setup.ensure_native(root, {"StormLib": "a" * 40, "CascLib": "b" * 40}, shared, False, rep, True)
            self.assertIsNotNone(base)
            self.assertFalse(rep.failed)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.ext = fake_extract(self.dir / "ext")
        self.cache = self.dir / "shared" / "d2r-cache"

    def seed_dir(self, content=b"seed") -> Path:
        seed = self.dir / "seed"
        for rel in fxpaths.CACHED_FILES:
            (seed / rel).parent.mkdir(parents=True, exist_ok=True)
            (seed / rel).write_bytes(content + rel.encode())
        return seed

    def test_everything_is_missing_at_first(self):
        self.assertEqual(lane_setup.cache_missing(self.ext, self.cache), list(fxpaths.CACHED_FILES))

    def test_files_in_the_extraction_are_not_needed_in_the_cache(self):
        rel = fxpaths.CACHED_FILES[0]
        (self.ext / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.ext / rel).write_bytes(b"x")
        self.assertNotIn(rel, lane_setup.cache_missing(self.ext, self.cache))

    def test_seed_fills_the_cache_and_the_manifest_detects_changes(self):
        missing = lane_setup.cache_missing(self.ext, self.cache)
        rep = lane_setup.Report()
        lane_setup.fill_cache(self.ext, self.cache, missing, [self.seed_dir()], None, rep)
        self.assertEqual(missing, [])
        self.assertEqual(lane_setup.cache_missing(self.ext, self.cache), [])
        manifest = lane_setup.update_manifest(self.cache)
        self.assertEqual(set(manifest), set(fxpaths.CACHED_FILES))
        self.assertEqual(lane_setup.cache_damaged(self.cache), [])
        (self.cache / fxpaths.CACHED_FILES[0]).write_bytes(b"changed")
        self.assertEqual(lane_setup.cache_damaged(self.cache), [fxpaths.CACHED_FILES[0]])

    def test_fill_never_overwrites_and_leaves_no_temp_files(self):
        rel = fxpaths.CACHED_FILES[0]
        (self.cache / rel).parent.mkdir(parents=True)
        (self.cache / rel).write_bytes(b"mine")
        missing = lane_setup.cache_missing(self.ext, self.cache)
        lane_setup.fill_cache(self.ext, self.cache, missing, [self.seed_dir()], None, lane_setup.Report())
        self.assertEqual((self.cache / rel).read_bytes(), b"mine")
        self.assertEqual(list(self.cache.rglob("*.tmp")), [])

    def test_slot_fill_takes_and_releases_the_slot_lock(self):
        import game_slots
        calls = []
        with mock.patch.object(game_slots, "acquire", lambda n, owner, pid=None: calls.append(("lock", n, owner)) or (True, "ok")), \
                mock.patch.object(game_slots, "release", lambda n, owner=None, manual=False: calls.append(("unlock", n, owner))):
            missing = lane_setup.cache_missing(self.ext, self.cache)
            lane_setup.fill_cache(self.ext, self.cache, missing, [], 2, lane_setup.Report(), reader=lambda rel: b"casc:" + rel.encode())
        self.assertEqual(missing, [])
        self.assertEqual(calls, [("lock", 2, "lane_setup"), ("unlock", 2, "lane_setup")])
        rel = fxpaths.CACHED_FILES[2]
        self.assertEqual((self.cache / rel).read_bytes(), b"casc:" + rel.encode())

    def test_slot_fill_releases_the_lock_when_reading_fails(self):
        import game_slots
        calls = []

        def boom(rel):
            raise OSError("CASC")
        with mock.patch.object(game_slots, "acquire", lambda n, owner, pid=None: (True, "ok")), \
                mock.patch.object(game_slots, "release", lambda n, owner=None, manual=False: calls.append("unlock")):
            with self.assertRaises(OSError):
                lane_setup.fill_cache(self.ext, self.cache, lane_setup.cache_missing(self.ext, self.cache), [], 3, lane_setup.Report(), reader=boom)
        self.assertEqual(calls, ["unlock"])

    def test_slot_held_by_someone_else_is_a_failure_not_a_read(self):
        import game_slots
        rep = lane_setup.Report()
        missing = lane_setup.cache_missing(self.ext, self.cache)
        with mock.patch.object(game_slots, "acquire", lambda n, owner, pid=None: (False, "held by lane x")):
            lane_setup.fill_cache(self.ext, self.cache, missing, [], 2, rep, reader=lambda rel: self.fail("read without the lock"))
        self.assertEqual(rep.rows[-1][0], "FAIL")
        self.assertTrue(missing)


class MainTests(unittest.TestCase):
    def test_refuses_a_folder_that_is_not_a_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(lane_setup.main([tmp, "--check"]), 1)

    def test_build_scripts_read_the_local_config(self):
        ps = (TOOLS / "build_plugin.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-LocalSetting 'MXL2012_PLUGINSDK_DIR'", ps)
        self.assertIn(".mxl-local.json", (TOOLS / "_cmake.ps1").read_text(encoding="utf-8"))
        self.assertIn("-Source", (TOOLS / "build_native.ps1").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
