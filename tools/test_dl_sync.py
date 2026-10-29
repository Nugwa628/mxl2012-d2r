"""tools/dl_sync.py: the mirror of the download site to the DigitalOcean Space, against tools/fake_rclone.py (a folder
plays the Space; a script named rclone on PATH). The upload order (objects first, release manifests after their 7z,
channels last, deletions after everything and never of an object a release uses), the headers and ACL per prefix, what is
never uploaded (dot files, *.part-*, files outside the layout), re-runs, a failure half-way, the lock, --dry-run, --check,
and the trigger file the ingest, promote and gc write. No network; the real Space is not tested here."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import dl_sync
import publish_release as pub
from test_publish_release import Base, tree

HERE = Path(__file__).resolve().parent
SHA_A = hashlib.sha256(b"object a").hexdigest()
SHA_B = hashlib.sha256(b"object b!").hexdigest()


def fake_rclone_on_path(folder: Path) -> Path:
    """A folder holding `rclone` (rclone.cmd on Windows) that runs tools/fake_rclone.py."""
    bin_dir = folder / "bin"
    bin_dir.mkdir()
    if sys.platform == "win32":
        (bin_dir / "rclone.cmd").write_text(f'@"{sys.executable}" "{HERE / "fake_rclone.py"}" %*\r\n')
    else:
        p = bin_dir / "rclone"
        p.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_rclone.py"}" "$@"\n')
        p.chmod(0o755)
    return bin_dir


class SyncBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.site = self.tmp / "srv" / "mxl2012"
        self.site.mkdir(parents=True)
        self.state = self.tmp / "state"
        self.space = self.tmp / "space"  # fake_rclone's root: spaces:d2r-xl/mxl2012 is space/d2r-xl/mxl2012
        self.space.mkdir()
        self.remote = self.space / "d2r-xl" / "mxl2012"
        self.remote_spec = "spaces:d2r-xl/mxl2012"
        self.log_file = self.tmp / "rclone.log"
        bin_dir = fake_rclone_on_path(self.tmp)
        env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}", "FAKE_RCLONE_ROOT": str(self.space),
               "FAKE_RCLONE_LOG": str(self.log_file)}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("JOURNAL_STREAM", None)
        os.environ.pop("FAKE_RCLONE_FAIL", None)

    def put(self, rel, data: bytes):
        p = self.site.joinpath(*rel.split("/"))
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def make_site(self):
        man = {"schemaVersion": 2, "version": "1.0.0", "files": [{"path": "a.txt", "sha256": SHA_A, "size": 8},
                                                                 {"path": "b.txt", "sha256": SHA_B, "size": 9}]}
        self.put(f"objects/{SHA_A[:2]}/{SHA_A}", b"object a")
        self.put(f"objects/{SHA_B[:2]}/{SHA_B}", b"object b!")
        self.put("releases/1.0.0/release-manifest.json", json.dumps(man).encode())
        self.put("releases/1.0.0/D2R-XL-2012-1.0.0.7z", b"7z..")
        self.put("releases/1.0.0/SHA256SUMS", b"sums\n")
        self.put("releases/1.0.0/RELEASE_NOTES-1.0.0.md", b"notes\n")
        self.put("launcher/0.3.0/D2R-XL-2012-Downloader.exe", b"MZ")
        self.put("launcher/0.3.0/D2R-XL-2012-Downloader.exe.sha256", b"x  D2R-XL-2012-Downloader.exe\n")
        self.put("assets/pack-1.7z", b"assets")
        self.put("channels/stable.json", b'{"version": "1.0.0"}\n')
        self.put("channels/test.json", b'{"version": "1.0.0"}\n')
        # never mirrored
        self.put(".sync/wanted", b"now\n")
        self.put(".sync/status.json", b"{}")
        self.put(f"objects/{SHA_A[:2]}/{SHA_A}.part-1a2b", b"half")
        self.put("releases/.hidden/x", b"x")
        self.put("releases/1.0.0/.notes.swp", b"x")
        self.put("stray.txt", b"x")

    def sync(self, *args, expect=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = dl_sync.main(["--site", str(self.site), "--state", str(self.state), "--config", str(self.tmp / "rclone.conf"),
                               "--remote", self.remote_spec, "--lock-wait", "0", *args])
        self.output = out.getvalue() + err.getvalue()
        self.assertEqual(rc, expect, self.output)
        return self.output

    def calls(self):
        if not self.log_file.is_file():
            return []
        calls = [json.loads(ln) for ln in self.log_file.read_text("utf-8").splitlines()]
        self.log_file.unlink()
        return [(next(a for a in c["argv"] if not a.startswith("-") and a in ("lsjson", "copy", "delete", "cat")), c["files"])
                for c in calls]

    def meta(self):
        return json.loads((self.space / ".meta.json").read_text("utf-8"))

    def status(self):
        return json.loads((self.site / ".sync" / "status.json").read_text("utf-8"))


class SyncTests(SyncBase):
    def expected(self):
        return {r: b for r, b in tree(self.site).items() if dl_sync.mirrored(r)}

    def test_mirror_layout_headers_and_acl(self):
        self.make_site()
        self.sync()
        self.assertEqual(tree(self.remote), self.expected())
        self.assertNotIn("stray.txt", tree(self.remote))
        self.assertFalse(any(".part-" in r or "/." in "/" + r for r in tree(self.remote)), "no temp or dot files")
        meta = self.meta()
        want = {
            f"objects/{SHA_A[:2]}/{SHA_A}": ("public, max-age=31536000, immutable", "application/octet-stream"),
            "channels/stable.json": ("no-cache", "application/json"),
            "releases/1.0.0/release-manifest.json": ("public, max-age=3600", "application/json"),
            "releases/1.0.0/D2R-XL-2012-1.0.0.7z": ("public, max-age=3600", "application/x-7z-compressed"),
            "releases/1.0.0/SHA256SUMS": ("public, max-age=3600", "text/plain; charset=utf-8"),
            "launcher/0.3.0/D2R-XL-2012-Downloader.exe": ("public, max-age=3600", "application/octet-stream"),
            "assets/pack-1.7z": ("public, max-age=3600", "application/x-7z-compressed"),
        }
        for rel, (cc, ct) in want.items():
            m = meta[f"d2r-xl/mxl2012/{rel}"]
            self.assertEqual((m["cache-control"], m["content-type"]), (cc, ct), rel)
        self.assertTrue(all(m["acl"] == "public-read" for m in meta.values()), "public-read on every object")
        st = self.status()
        self.assertEqual((st["result"], st["uploaded"], st["deleted"]), ("ok", len(self.expected()), 0))
        self.assertEqual(st["lastSuccessAt"], st["finishedAt"])

    def test_header_mapping_and_exclusions(self):
        self.assertEqual(dl_sync.headers("channels/test.json"), ("no-cache", "application/json"))
        self.assertEqual(dl_sync.headers(f"objects/ab/{SHA_A}")[0], dl_sync.IMMUTABLE)
        self.assertEqual(dl_sync.headers("releases/1.0.0/RELEASE_NOTES-1.0.0.md")[1], "text/markdown; charset=utf-8")
        for rel in (".sync/wanted", "objects/ab/x.part-0", "releases/1.0.0/.x", "stray.txt", "incoming/1.0.0/READY",
                    "releases//x", "channels"):
            self.assertFalse(dl_sync.mirrored(rel), rel)
        self.assertTrue(dl_sync.mirrored("assets/pack-1.7z"))

    def test_order_objects_first_channels_last(self):
        self.make_site()
        self.sync()
        copies = [files for cmd, files in self.calls() if cmd == "copy"]
        flat = [f for files in copies for f in files]
        self.assertTrue(copies[0] and all(f.startswith("objects/") for f in copies[0]), "objects first")
        chan = [i for i, f in enumerate(flat) if f.startswith("channels/")]
        self.assertEqual(chan, list(range(len(flat) - 2, len(flat))), "channels last")
        self.assertTrue(all(f.startswith("channels/") for f in copies[-1]), "channels in their own, last upload")
        self.assertLess(flat.index("releases/1.0.0/D2R-XL-2012-1.0.0.7z"), flat.index("releases/1.0.0/release-manifest.json"))
        self.assertLess(flat.index("launcher/0.3.0/D2R-XL-2012-Downloader.exe"), flat.index("releases/1.0.0/release-manifest.json"))

    def test_second_run_uploads_nothing_and_a_changed_file_goes_up(self):
        self.make_site()
        self.sync()
        self.calls()
        self.sync()
        self.assertEqual([c for c, _ in self.calls()], ["lsjson"], "nothing to do")
        self.put("channels/test.json", b'{"version": "1.0.1"}\n')  # the same size, other bytes
        self.sync()
        self.assertEqual([f for c, files in self.calls() if c == "copy" for f in files], ["channels/test.json"])
        self.assertEqual((self.remote / "channels" / "test.json").read_bytes(), b'{"version": "1.0.1"}\n')

    def test_resumes_after_a_failure_and_never_publishes_a_channel_first(self):
        self.make_site()
        os.environ["FAKE_RCLONE_FAIL"] = "release-manifest.json"
        self.sync(expect=1)
        calls = self.calls()
        self.assertFalse(any(f.startswith("channels/") for c, files in calls if c == "copy" for f in files))
        self.assertNotIn("delete", [c for c, _ in calls])
        self.assertFalse((self.remote / "channels").exists(), "no channel on the Space")
        self.assertTrue((self.remote / "objects").is_dir(), "the objects went up")
        st = self.status()
        self.assertEqual(st["result"], "failed")
        self.assertIn("rclone copy failed", st["error"])
        self.assertNotIn("lastSuccessAt", st)
        del os.environ["FAKE_RCLONE_FAIL"]
        self.sync()
        again = [f for c, files in self.calls() if c == "copy" for f in files]
        self.assertFalse(any(f.startswith("objects/") for f in again), "objects not sent twice")
        self.assertEqual(tree(self.remote), self.expected())

    def test_deletions_come_last_and_only_unreferenced(self):
        self.make_site()
        self.sync()
        self.calls()
        # gc on the site: release 1.0.0's 7z and object b are gone; a new channel version was written
        (self.site / "releases" / "1.0.0" / "D2R-XL-2012-1.0.0.7z").unlink()
        man = json.loads((self.site / "releases/1.0.0/release-manifest.json").read_text("utf-8"))
        man["files"] = man["files"][:1]
        self.put("releases/1.0.0/release-manifest.json", json.dumps(man).encode())
        (self.site / "objects" / SHA_B[:2] / SHA_B).unlink()
        self.put("channels/stable.json", b'{"version": "1.0.0", "x": 1}\n')
        self.sync()
        calls = self.calls()
        cmds = [c for c, _ in calls]
        self.assertEqual(cmds[-1], "delete")
        self.assertEqual(cmds.count("delete"), 1)
        self.assertEqual(sorted(calls[-1][1]), sorted([f"objects/{SHA_B[:2]}/{SHA_B}", "releases/1.0.0/D2R-XL-2012-1.0.0.7z"]))
        self.assertEqual(tree(self.remote), self.expected())
        self.assertEqual(self.status()["deleted"], 2)

    def test_an_object_a_release_uses_is_never_deleted(self):
        self.make_site()
        self.sync()
        self.calls()
        (self.site / "objects" / SHA_B[:2] / SHA_B).unlink()  # the site lost an object its release still names
        self.sync(expect=1)
        self.assertNotIn("delete", [c for c, _ in self.calls()])
        self.assertTrue((self.remote / "objects" / SHA_B[:2] / SHA_B).is_file())
        self.assertIn("not deleting anything", self.status()["error"])
        self.sync("--no-delete")  # an upload-only run still works
        self.assertTrue((self.remote / "objects" / SHA_B[:2] / SHA_B).is_file())

    def test_mass_deletion_is_refused(self):
        self.make_site()
        for i in range(120):
            self.put(f"assets/extra-{i}.bin", b"x")
        self.sync()
        shutil.rmtree(self.site / "assets")
        self.sync(expect=1)
        self.assertIn("--allow-mass-delete", self.output)
        self.sync("--allow-mass-delete")
        self.assertFalse(any(r.startswith("assets/") for r in tree(self.remote)))

    def test_an_empty_site_is_refused(self):
        self.put("objects/ab/" + "a" * 64, b"x")
        self.sync(expect=1)
        self.assertIn("looks empty", self.output)
        self.assertFalse(self.remote.exists())

    def test_dry_run_changes_nothing(self):
        self.make_site()
        out = self.sync("--dry-run")
        self.assertIn("would upload", out)
        self.assertEqual([c for c, _ in self.calls()], ["lsjson"])
        self.assertFalse(self.remote.exists())
        self.assertEqual((self.site / ".sync" / "status.json").read_bytes(), b"{}", "status untouched")
        self.assertFalse((self.state / "uploaded.json").exists())

    def test_lock_keeps_two_runs_apart(self):
        self.make_site()
        fd = dl_sync.lock(self.state / "lock", 0)
        try:
            self.sync(expect=1)
            self.assertIn("another dl_sync is running", self.output)
            self.assertEqual(self.calls(), [])
        finally:
            os.close(fd)
        self.sync()

    def test_another_pass_when_the_site_changed_during_one(self):
        self.make_site()
        real = dl_sync.Rclone.upload
        hits = []

        def upload(rc, src, rels, cc, ct):
            if not hits:
                hits.append(1)
                self.put("channels/test.json", b'{"version": "2.0.0"}\n')
                self.put(".sync/wanted", b"later, longer\n")
            return real(rc, src, rels, cc, ct)

        with mock.patch.object(dl_sync.Rclone, "upload", upload):
            self.sync()
        self.assertIn("once more", self.output)
        self.assertEqual((self.remote / "channels" / "test.json").read_bytes(), b'{"version": "2.0.0"}\n')

    def test_check(self):
        self.make_site()
        self.sync()
        self.assertIn("the Space matches the site", self.sync("--check", "--full"))
        p = self.remote / "releases" / "1.0.0" / "SHA256SUMS"
        p.write_bytes(b"SUMS\n")  # same size, other bytes
        (self.remote / "assets" / "junk").write_bytes(b"j")
        meta = self.meta()
        meta["d2r-xl/mxl2012/channels/test.json"]["cache-control"] = "public, max-age=3600"
        (self.space / ".meta.json").write_text(json.dumps(meta), encoding="utf-8")
        out = self.sync("--check", "--full", expect=1)
        self.assertIn("content differs (sha256): releases/1.0.0/SHA256SUMS", out)
        self.assertIn("on the Space only: assets/junk", out)
        self.assertIn("headers differ: channels/test.json", out)


class TwoProductsTests(SyncBase):
    """The first product (site /srv/dl/mxl -> Space prefix mxl/) and this product (mxl2012 -> mxl2012/) share one Space bucket, one
    installed dl_sync.py and one rclone.conf; each unit has its own site, remote prefix and state folder."""

    def setUp(self):
        super().setUp()
        self.other_site = self.tmp / "srv" / "mxl"
        self.other_site.mkdir(parents=True)
        self.other_remote = self.space / "d2r-xl" / "mxl"

    def sync_other(self, *args, expect=0):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = dl_sync.main(["--site", str(self.other_site), "--remote", "spaces:d2r-xl/mxl", "--state", str(self.tmp / "state-mxl"),
                               "--config", str(self.tmp / "rclone.conf"), "--lock-wait", "0", *args])
        self.assertEqual(rc, expect, out.getvalue() + err.getvalue())

    def fill_other(self):
        for rel, body in (("channels/stable.json", b'{"version": "0.69.0"}\n'), ("objects/ab/" + "ab" * 32, b"other object"),
                          ("releases/0.69.0/Other-0.69.0.7z", b"7z")):
            p = self.other_site.joinpath(*rel.split("/"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)

    def test_each_product_mirrors_into_its_own_prefix_and_leaves_the_other_alone(self):
        self.fill_other()
        self.sync_other()
        before = tree(self.other_remote)
        self.assertIn("channels/stable.json", before)
        self.make_site()
        self.sync()
        self.assertEqual(tree(self.other_remote), before, "syncing this product changed nothing of the other prefix")
        self.assertTrue(set(tree(self.remote)) >= {"channels/stable.json", "releases/1.0.0/release-manifest.json"})
        self.assertFalse(set(tree(self.remote)) & {"releases/0.69.0/Other-0.69.0.7z"}, "nothing of the other product here")
        self.assertEqual(self.status()["remote"], "spaces:d2r-xl/mxl2012")
        self.assertTrue((self.tmp / "state-mxl" / "uploaded.json").is_file() and (self.state / "uploaded.json").is_file())

    def test_a_cleanup_here_deletes_nothing_of_the_other_product(self):
        self.fill_other()
        self.sync_other()
        self.make_site()
        self.sync()
        other = tree(self.other_remote)
        (self.site / "releases/1.0.0/SHA256SUMS").unlink()
        self.sync()
        self.assertNotIn("releases/1.0.0/SHA256SUMS", tree(self.remote))
        self.assertEqual(tree(self.other_remote), other)
        self.sync_other()  # the other product's own run afterwards: its site did not change, so nothing is uploaded or deleted
        self.assertEqual(tree(self.other_remote), other)


class TriggerTests(Base):
    """The ingest, promote, gc and an asset upload write <site>/.sync/wanted (mxl2012-dl-sync.path); `list` shows the status."""

    def wanted(self):
        p = self.site / ".sync" / "wanted"
        return p.read_text("utf-8") if p.is_file() else None

    def test_ingest_promote_gc_ask_for_a_sync(self):
        self.publish("1.0.0", "test")
        self.assertIn("ingest 1.0.0", self.wanted())
        (self.site / ".sync" / "wanted").unlink()
        pub.promote(pub.DirTarget(self.site), "1.0.0", "stable", log=lambda *_: None)
        self.assertIn("promote 1.0.0 stable", self.wanted())
        (self.site / ".sync" / "wanted").unlink()
        pub.gc(pub.DirTarget(self.site), 1, dry_run=True, log=lambda *_: None)
        self.assertIsNone(self.wanted(), "a dry run asks for nothing")
        pub.gc(pub.DirTarget(self.site), 1, log=lambda *_: None)
        self.assertIn("gc --keep 1", self.wanted())

    def test_list_shows_the_sync_status(self):
        self.publish("1.0.0", "test")
        lines = []
        pub.list_cmd(pub.DirTarget(self.site), log=lines.append)
        self.assertFalse(any("Space sync" in ln for ln in lines))
        (self.site / ".sync" / "status.json").write_text(json.dumps(
            {"result": "failed", "finishedAt": "2026-10-27T10:00:00Z", "error": "rclone copy failed (1): boom",
             "lastSuccessAt": "2026-10-27T09:00:00Z"}), encoding="utf-8")
        lines = []
        pub.list_cmd(pub.DirTarget(self.site), log=lines.append)
        self.assertIn("Space sync: FAILED at 2026-10-27T10:00:00Z: rclone copy failed (1): boom (last ok 2026-10-27T09:00:00Z; "
                      "journalctl -u mxl2012-dl-sync)", lines)


if __name__ == "__main__":
    unittest.main()
