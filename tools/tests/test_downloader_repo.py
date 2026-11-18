"""tools/downloader_repo.py: the downloader's own repository gets only allow-listed, scanned files, and a sync commit names
the source commit. Temporary git repositories stand in for this repository and the downloader repository's clone."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import downloader_repo as dr  # noqa: E402

IDENTITY = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t3code@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t3code@users.noreply.github.com"}

LAUNCHER_MD = """# D2R-XL 2012 Downloader

Intro, see [the plan](plugin-plan.md#top) and [the policy](code-signing-policy.md).

## Play

Play text.

Validation for lane `x` (2026-10-28): numbers
more numbers.

## Testing

Only for this repository.

## After

Kept.
"""

BASE = {
    "LICENSE": "MIT\n",
    "tools/sign_launcher.py": "print('sign')\n",
    "tools/test_sign_launcher.py": "import projtemp\n",
    "docs/launcher.md": LAUNCHER_MD,
    "docs/code-signing-policy.md": "# Policy\n\nSee [the downloader](launcher.md) and [NOTICE](../NOTICE.md).\n",
    "docs/other.md": "# not exported\n",
    "launcher/CMakeLists.txt": "project(x)\n",
    "launcher/src/core/a.cpp": "int a;\n",
    "downloader-repo/README.md": "# Downloader\n",
    "downloader-repo/NOTICE.md": "# Notice\n",
    "downloader-repo/.github/workflows/sign-launcher.yml": "name: x\n",
    "data/private.txt": "not exported\n",
}


def run(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def make_repo(root: Path, files: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    run(root, "init", "-q", "-b", "main")
    run(root, "config", "core.autocrlf", "false")
    write(root, files)
    return root


def write(root: Path, files: dict):
    for rel, text in files.items():
        f = root / rel
        if text is None:
            f.unlink()
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8", newline="\n")
    run(root, "add", "-A")
    run(root, "commit", "-q", "-m", "change files")


class Base(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.get(k) for k in IDENTITY}
        os.environ.update(IDENTITY)
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.src_repo = make_repo(self.tmp / "src", BASE)

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()


class AllowListTest(Base):
    def test_star_does_not_cross_folders(self):
        self.assertTrue(dr.match("launcher/src/core/a.cpp", "launcher/src/core/*.cpp"))
        self.assertFalse(dr.match("launcher/src/core/x/a.cpp", "launcher/src/core/*.cpp"))
        self.assertFalse(dr.allowed("launcher/res/secret.txt"))
        self.assertTrue(dr.allowed("downloader-repo/.github/workflows/sign-launcher.yml"))

    def test_plan_maps_curated_files_to_the_root_and_skips_the_rest(self):
        p = dr.plan(dr.Source(self.src_repo))
        self.assertEqual(p["README.md"], "downloader-repo/README.md")
        self.assertEqual(p[".github/workflows/sign-launcher.yml"], "downloader-repo/.github/workflows/sign-launcher.yml")
        self.assertIn("launcher/src/core/a.cpp", p)
        self.assertNotIn("data/private.txt", p)
        self.assertNotIn("docs/other.md", p)

    def test_unlisted_file_under_launcher_is_refused(self):
        write(self.src_repo, {"launcher/res/notes.txt": "hello\n"})
        with self.assertRaisesRegex(dr.ExportError, "allow-list.*launcher/res/notes.txt"):
            dr.plan(dr.Source(self.src_repo))

    def test_missing_extra_file_is_refused(self):
        write(self.src_repo, {"LICENSE": None})
        with self.assertRaisesRegex(dr.ExportError, "missing: LICENSE"):
            dr.plan(dr.Source(self.src_repo))

    def test_rev_reads_the_commit_not_the_working_tree(self):
        (self.src_repo / "launcher/src/core/a.cpp").write_bytes(b"int changed;\n")
        self.assertEqual(dr.Source(self.src_repo).read("launcher/src/core/a.cpp"), b"int a;\n")
        self.assertEqual(dr.Source(self.src_repo, None).read("launcher/src/core/a.cpp"), b"int changed;\n")


class ScanTest(Base):
    def assert_refused(self, text, rule):
        write(self.src_repo, {"launcher/src/core/a.cpp": text})
        with self.assertRaises(dr.ExportError) as e:
            dr.build(dr.Source(self.src_repo))
        self.assertIn(f"[{rule}]", str(e.exception))
        self.assertIn("launcher/src/core/a.cpp:1", str(e.exception))

    def test_retired_domain(self):
        self.assert_refused("// files." + "werde" + "games.com\n", "retired")

    def test_deny_list(self):
        self.assert_refused("// see wild" + "-healer's tools\n", "wild-healer")
        self.assert_refused("// ask on Dis" + "cord\n", "discord")
        self.assert_refused("// mods" + "bylaz.com\n", "laz-site")
        self.assert_refused("// evidence in mxl2012" + "-runs/x\n", "runs-folder")

    def test_token_home_path_and_email(self):
        self.assert_refused("token = '" + "A" * 24 + "'\n", "secret")
        self.assert_refused("// C:\\Users\\" + "somebody\\x\n", "home-path")
        self.assert_refused("// mail someone" + "@example.org\n", "email")

    def test_deny_file(self):
        write(self.src_repo, {"launcher/src/core/a.cpp": "// codename bluefish\n"})
        deny = self.tmp / "deny.txt"
        deny.write_text("# names\nbluefish\n", encoding="utf-8")
        dr.build(dr.Source(self.src_repo))
        with self.assertRaisesRegex(dr.ExportError, "deny-file"):
            dr.build(dr.Source(self.src_repo), dr.load_deny_file(deny))

    def test_export_allow_is_path_bound(self):
        version = "1.3.1" + ".0"  # looks like an IP address to the scan
        write(self.src_repo, {"launcher/src/core/a.cpp": f"// D2RLoader {version}\n"})
        dr.build(dr.Source(self.src_repo))  # allowed in launcher/*
        write(self.src_repo, {"downloader-repo/README.md": f"D2RLoader {version}\n"})
        with self.assertRaisesRegex(dr.ExportError, r"README\.md:1  \[ip\]"):
            dr.build(dr.Source(self.src_repo))

    def test_unsafe_subject_is_not_used_in_the_message(self):
        run(self.src_repo, "commit", "-q", "--allow-empty", "-m", "Fix for player report on Dis" + "cord")
        msg = dr.commit_message(dr.Source(self.src_repo))
        self.assertIn(": downloader update", msg)


class TransformTest(Base):
    def test_launcher_md_is_trimmed_and_links_point_at_the_mod_repository(self):
        tree = dr.build(dr.Source(self.src_repo))
        md = tree["docs/launcher.md"].decode()
        self.assertNotIn("## Testing", md)
        self.assertNotIn("Only for this repository", md)
        self.assertNotIn("Validation for lane", md)
        self.assertIn("## After\n\nKept.", md)
        self.assertIn("## Play\n\nPlay text.\n\n## After", md)
        self.assertTrue(md.startswith("# D2R-XL 2012 Downloader\n\n> This page comes from"))
        self.assertIn(f"]({dr.MOD_BLOB}docs/plugin-plan.md#top)", md)
        self.assertIn("](code-signing-policy.md)", md)
        policy = tree["docs/code-signing-policy.md"].decode()
        self.assertIn("](launcher.md)", policy)
        self.assertIn("](../NOTICE.md)", policy)  # the downloader repository's own NOTICE.md
        self.assertEqual(tree["LICENSE"], b"MIT\n")


class ExportTest(Base):
    def test_export_and_re_export_removes_dropped_files(self):
        out = self.tmp / "out"
        written, removed = dr.export_dir(dr.Source(self.src_repo), out)
        self.assertEqual(removed, [])
        self.assertTrue((out / ".github/workflows/sign-launcher.yml").is_file())
        self.assertFalse((out / "downloader-repo").exists())
        self.assertFalse((out / "data").exists())
        write(self.src_repo, {"launcher/src/core/a.cpp": None, "launcher/src/core/b.cpp": "int b;\n"})
        written, removed = dr.export_dir(dr.Source(self.src_repo), out)
        self.assertEqual(written, ["launcher/src/core/b.cpp"])
        self.assertEqual(removed, ["launcher/src/core/a.cpp"])
        self.assertFalse((out / "launcher/src/core/a.cpp").exists())

    def test_refuses_a_folder_that_is_not_an_export(self):
        out = self.tmp / "busy"
        out.mkdir()
        (out / "mine.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(dr.ExportError, "not empty"):
            dr.export_dir(dr.Source(self.src_repo), out)

    def test_nothing_is_written_when_the_scan_fails(self):
        write(self.src_repo, {"launcher/src/core/a.cpp": "// Dis" + "cord\n"})
        out = self.tmp / "out"
        with self.assertRaises(dr.ExportError):
            dr.export_dir(dr.Source(self.src_repo), out)
        self.assertFalse(out.exists())


class CommitTest(Base):
    def setUp(self):
        super().setUp()
        self.clone = make_repo(self.tmp / "clone", {"README.md": "# made on GitHub\n"})

    def test_incremental_commits(self):
        src = dr.Source(self.src_repo)
        first = dr.commit_clone(src, self.clone)
        self.assertIsNotNone(first)
        msg = run(self.clone, "log", "-1", "--format=%B")
        self.assertTrue(msg.startswith(f"Sync from MXL2012-D2R {src.sha[:10]}: change files"), msg)
        self.assertIn(f"commit {src.sha}.", msg)
        self.assertEqual((self.clone / "README.md").read_text(encoding="utf-8"), "# Downloader\n")
        self.assertIsNone(dr.commit_clone(dr.Source(self.src_repo), self.clone))  # nothing changed: no commit
        self.assertEqual(run(self.clone, "rev-parse", "HEAD"), first)
        write(self.src_repo, {"launcher/src/core/a.cpp": None, "launcher/src/core/b.cpp": "int b;\n"})
        second = dr.commit_clone(dr.Source(self.src_repo), self.clone)
        changed = run(self.clone, "diff", "--name-status", first, second).splitlines()
        self.assertEqual(sorted(changed), ["A\tlauncher/src/core/b.cpp", "D\tlauncher/src/core/a.cpp"])
        self.assertEqual(run(self.clone, "status", "--porcelain"), "")
        self.assertEqual(run(self.clone, "remote"), "")  # never pushes (no remote even needed)

    def test_refuses_a_dirty_clone_and_the_working_tree(self):
        (self.clone / "local.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(dr.ExportError, "uncommitted"):
            dr.commit_clone(dr.Source(self.src_repo), self.clone)
        with self.assertRaisesRegex(dr.ExportError, "working tree"):
            dr.commit_clone(dr.Source(self.src_repo, None), self.clone)


class RealTreeTest(unittest.TestCase):
    def test_this_repository_exports_cleanly(self):
        tree = dr.build(dr.Source(dr.ROOT, None))
        tops = {d.split("/")[0] for d in tree}
        self.assertEqual(tops, {".github", ".gitignore", "LICENSE", "NOTICE.md", "README.md", "docs", "launcher", "tools"})
        for need in ("launcher/CMakeLists.txt", "launcher/tests/CMakeLists.txt", "launcher/signpath-artifact-configuration.xml",
                     ".github/workflows/sign-launcher.yml", "tools/sign_launcher.py", "tools/test_sign_launcher.py",
                     "tools/projtemp.py", "docs/code-signing-policy.md"):
            self.assertIn(need, tree)
        self.assertEqual(sorted(d for d in tree if d.startswith("docs/")),
                         ["docs/code-signing-policy.md", "docs/launcher.md"])
        self.assertNotIn(b"## Testing", tree["docs/launcher.md"])


if __name__ == "__main__":
    unittest.main()
