"""tools/dl_ingest.py: what the server does with an upload in incoming/. Every check that must refuse an upload (a damaged
file, a bad object, a missing object, an entry that is not an object, a file READY does not list), the order of the writes
(channel last), re-runs, --retry, the leftover-temp-file cleanup and the 7z it builds. Uses 7-Zip when the machine has it,
else tools/fake_7z.py. No network."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import dl_ingest as ing
import publish_release as pub
from test_publish_release import PRODUCT, PRODUCT_ARGS, REAL_7Z, Base, fake_7z_command, tree

# The host's first product, as its dl_ingest.defaults.json would describe it (the real file lives on the host only).
FIRST = {"archive_prefix": "Other", "launcher_name": "Other-Downloader.exe",
         "legacy_launcher_names": {"Other-Downloader.exe": "Other-Launcher.exe"}}


def setUpModule():
    ing.apply_defaults(FIRST)


def tearDownModule():
    ing.apply_defaults(ing.load_defaults())


class IngestTests(Base):
    def upload(self, version="1.0.0", channel="stable", files=None, **kw):
        """A publish into incoming/ (no ingest yet) -> the incoming folder."""
        self.publish(version, channel, files=files, ingest=False, **kw)
        return self.incoming / version

    def refused(self, inc):
        return (inc / "REFUSED").read_text("utf-8") if (inc / "REFUSED").is_file() else None

    def rewrite_ready(self, inc, edit):
        ready = json.loads((inc / "READY").read_text("utf-8"))
        edit(ready)
        (inc / "READY").write_text(json.dumps(ready), encoding="utf-8")

    def reseal(self, inc, name):
        """A file changed on purpose (the test plays the uploader): READY gets its new size and sha256."""
        p = inc / name
        self.rewrite_ready(inc, lambda r: r["files"].__setitem__(name, {"size": p.stat().st_size, "sha256": pub.sha256_file(p)}))

    def assert_refused(self, inc, words):
        self.ingest(expect=1)
        self.assertIn(words, self.refused(inc) or "")
        self.assertTrue(inc.is_dir(), "a refused upload stays for a look")
        self.assertFalse((self.site / "channels").exists(), "nothing published")
        self.assertFalse((inc / ing.WORK).exists(), "no work folder left")

    def repack(self, inc, entries, link=None):
        """Replace the upload's objects 7z by one holding `entries` {name: bytes}; READY follows."""
        ready = json.loads((inc / "READY").read_text("utf-8"))
        old = ready["objectsPack"]
        src = self.tmp / "repack"
        shutil.rmtree(src, ignore_errors=True)
        src.mkdir()
        for n, b in entries.items():
            (src / n).write_bytes(b)
        out = self.tmp / "repack.7z"
        out.unlink(missing_ok=True)
        env = dict(os.environ, FAKE_7Z_LINK=link) if link else None
        subprocess.run([self.seven, "a", "-t7z", str(out), *entries], cwd=src, check=True, capture_output=True, env=env)
        (inc / old).unlink()
        new = f"objects-{pub.sha256_file(out)[:16]}.7z"
        shutil.move(out, inc / new)
        ready["files"].pop(old)
        ready["files"][new] = {"size": (inc / new).stat().st_size, "sha256": pub.sha256_file(inc / new)}
        ready["objectsPack"] = new
        (inc / "READY").write_text(json.dumps(ready), encoding="utf-8")

    def pack_entries(self, inc):
        out = self.tmp / "unpack"
        shutil.rmtree(out, ignore_errors=True)
        pack = json.loads((inc / "READY").read_text("utf-8"))["objectsPack"]
        subprocess.run([self.seven, "x", "-y", f"-o{out}", str(inc / pack)], check=True, capture_output=True)
        return {p.name: p.read_bytes() for p in out.iterdir()}

    # ---------------------------------------------------------------------------------------------------------- checks
    def test_damaged_file_is_refused(self):
        inc = self.upload()
        p = inc / "release-manifest.json"
        p.write_bytes(p.read_bytes().replace(b'"fileCount"', b'"fileCounT"'))
        self.assert_refused(inc, "release-manifest.json does not match READY")

    def test_object_with_a_bad_sha256_is_refused(self):
        inc = self.upload()
        entries = self.pack_entries(inc)
        sha = sorted(entries)[0]
        body = entries[sha]
        entries[sha] = bytes([body[0] ^ 1]) + body[1:]  # same size, other bytes
        self.repack(inc, entries)
        self.assert_refused(inc, f"{sha} has sha256")
        self.assertFalse((self.site / pub.object_path(sha)).exists())

    def test_missing_object_is_refused(self):
        inc = self.upload()
        entries = self.pack_entries(inc)
        gone = sorted(entries)[0]
        del entries[gone]
        self.repack(inc, entries)
        self.assert_refused(inc, "objects the host does not have")
        self.assertFalse((self.site / "releases" / "1.0.0" / "release-manifest.json").exists())

    def test_object_damaged_on_the_host_is_refused(self):
        self.publish("1.0.0", None)
        victim = self.site / pub.object_path(pub.sha256_bytes(b"Median weapons\n"))
        victim.write_bytes(b"Median weaponZ\n")  # same size: the publisher believes it, the server checks the bytes
        inc = self.upload("1.0.1")
        self.assert_refused(inc, "on the host is damaged")

    def test_entry_that_is_not_an_object_is_refused(self):
        inc = self.upload()
        entries = self.pack_entries(inc)
        entries["notes.txt"] = b"hello"
        self.repack(inc, entries)
        self.assert_refused(inc, "'notes.txt', which is not an object")

    def test_unused_object_is_refused(self):
        inc = self.upload()
        entries = self.pack_entries(inc)
        stray = b"not in this release\n"
        entries[pub.sha256_bytes(stray)] = stray
        self.repack(inc, entries)
        self.assert_refused(inc, "which the manifest does not use")

    @unittest.skipIf(REAL_7Z, "the symbolic-link entry is made with tools/fake_7z.py")
    def test_symlink_entry_is_refused(self):
        inc = self.upload()
        entries = self.pack_entries(inc)
        self.repack(inc, entries, link="a" * 64)
        self.assert_refused(inc, "which is not an object")

    def test_symlink_entry_is_refused_by_the_listing(self):
        listing = ("Path = x.7z\nType = 7z\n\n----------\nPath = " + "a" * 64 + "\nFolder = -\nSize = 3\n"
                   "Attributes = A_ -rwxrwxrwx\n\nPath = " + "b" * 64 + "\nFolder = -\nSize = 9\nAttributes = A lrwxrwxrwx\n\n")
        r = subprocess.CompletedProcess([], 0, listing, "")
        with mock.patch.object(ing.subprocess, "run", return_value=r):
            with self.assertRaises(ing.Refused) as e:
                ing.list_pack("7z", Path("x.7z"), {"a" * 64: 3, "b" * 64: 9})
        self.assertIn("b" * 64, str(e.exception))
        r = subprocess.CompletedProcess([], 0, "----------\nPath = ../../mxl/channels/stable.json\nFolder = -\nSize = 2\n\n", "")
        with mock.patch.object(ing.subprocess, "run", return_value=r):
            with self.assertRaises(ing.Refused):  # a path out of the work folder: never unpacked
                ing.list_pack("7z", Path("x.7z"), {"a" * 64: 3})
        with mock.patch.object(ing.subprocess, "run", return_value=r):
            with self.assertRaises(ing.Refused):  # the wrong size
                ing.list_pack("7z", Path("x.7z"), {"a" * 64: 4, "b" * 64: 9})

    def test_file_that_ready_does_not_list_is_refused(self):
        inc = self.upload()
        (inc / "evil.sh").write_text("rm -rf /\n")
        self.assert_refused(inc, "files that READY does not list: evil.sh")

    def test_ready_that_names_other_files_is_refused(self):
        inc = self.upload()
        (inc / "index.html").write_text("<html>")
        self.reseal(inc, "index.html")
        self.assert_refused(inc, "READY lists a file it may not: 'index.html'")

    def test_bad_manifest_paths_are_refused(self):
        for path, words in (("../escape.txt", "bad manifest entry"), ("mxl2012/../../x", "bad manifest entry"),
                            ("C:/x", "bad manifest entry"), (None, "duplicate path")):
            with self.subTest(path=path):
                shutil.rmtree(self.incoming / "1.0.0", ignore_errors=True)
                inc = self.upload()
                p = inc / "release-manifest.json"
                man = json.loads(p.read_text("utf-8"))
                man["files"][1]["path"] = path or man["files"][0]["path"]
                p.write_text(json.dumps(man), encoding="utf-8")
                self.reseal(inc, "release-manifest.json")
                self.assert_refused(inc, words)

    def test_old_manifest_schema_is_refused(self):
        inc = self.upload()
        p = inc / "release-manifest.json"
        man = json.loads(p.read_text("utf-8"))
        man["schemaVersion"] = 1
        p.write_text(json.dumps(man), encoding="utf-8")
        self.reseal(inc, "release-manifest.json")
        self.assert_refused(inc, "manifest schemaVersion 1")

    def test_folder_and_ready_versions_must_agree(self):
        inc = self.upload()
        self.rewrite_ready(inc, lambda r: r.__setitem__("version", "9.9.9"))
        self.assert_refused(inc, "READY is for version '9.9.9'")

    def test_incomplete_for_stable_is_refused(self):
        dist = self.make_dist("1.0.0", complete=False)
        pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "test", allow_incomplete=True, log=lambda *_: None)
        inc = self.incoming / "1.0.0"
        self.rewrite_ready(inc, lambda r: r.__setitem__("channel", "stable"))
        self.assert_refused(inc, "not for the stable channel")

    def test_launcher_must_match_the_manifest(self):
        exe = self.tmp / "l.exe"
        exe.write_bytes(b"MZ one")
        inc = self.upload(launcher=exe, launcher_version="0.3.0")
        (inc / "D2R-XL-2012-Downloader.exe").write_bytes(b"MZ two")
        self.reseal(inc, "D2R-XL-2012-Downloader.exe")
        self.assert_refused(inc, "the uploaded launcher does not match")

    def test_old_launcher_name_is_only_for_the_first_product(self):
        """The first product's 0.1.x publishers uploaded Other-Launcher.exe: the default names still accept it. D2R-XL 2012
        never had such a publisher: its ingest refuses the name."""
        folder = self.tmp / "old-launcher"
        folder.mkdir()
        (folder / "release-manifest.json").write_bytes(b"{}")
        (folder / "Other-Launcher.exe").write_bytes(b"MZ")
        meta = {"size": 2, "sha256": pub.sha256_file(folder / "Other-Launcher.exe")}
        ready = {"schemaVersion": 1, "version": "1.0.0", "channel": None, "launcher": "Other-Launcher.exe",
                 "files": {"release-manifest.json": {"size": 2, "sha256": pub.sha256_file(folder / "release-manifest.json")},
                           "Other-Launcher.exe": meta}}
        (folder / "READY").write_text(json.dumps(ready), encoding="utf-8")
        self.assertEqual(ing.check_ready(folder, "1.0.0")["launcher"], "Other-Launcher.exe")
        with self.assertRaises(ing.Refused) as e:
            ing.check_ready(folder, "1.0.0", ("D2R-XL-2012-Downloader.exe",))
        self.assertIn("may not", str(e.exception))
        self.assertEqual(ing.Ingest(self.srv, sevenzip=self.seven, **PRODUCT).launcher_names, ("D2R-XL-2012-Downloader.exe",))
        self.assertEqual(ing.Ingest(self.srv, "mxl2012", self.seven, "incoming-mxl2012").launcher_names, ing.LAUNCHER_NAMES)

    def test_without_a_defaults_file_the_names_are_needed(self):
        try:
            ing.apply_defaults({})
            with self.assertRaises(SystemExit) as e:
                ing.Ingest(self.srv, "mxl2012", self.seven, "incoming-mxl2012")
            self.assertIn("--archive-prefix", str(e.exception))
            self.assertEqual(ing.Ingest(self.srv, sevenzip=self.seven, **PRODUCT).archive_prefix, "D2R-XL-2012")
            path = self.tmp / "defaults.json"
            path.write_text(json.dumps(FIRST), encoding="utf-8")
            ing.apply_defaults(ing.load_defaults(path))
            self.assertEqual(ing.LAUNCHER_NAMES, ("Other-Downloader.exe", "Other-Launcher.exe"))
            self.assertEqual(ing.load_defaults(self.tmp / "none.json"), {})
        finally:
            ing.apply_defaults(FIRST)

    def test_old_launcher_name_is_refused(self):
        inc = self.upload(launcher=self.make_exe(), launcher_version="0.3.0")
        old = "D2R-XL-2012-Launcher.exe"
        (inc / "D2R-XL-2012-Downloader.exe").rename(inc / old)
        man = inc / "release-manifest.json"
        m = json.loads(man.read_text("utf-8"))
        m["launcher"]["path"] = f"launcher/0.3.0/{old}"
        man.write_text(json.dumps(m), encoding="utf-8")

        def edit(r):
            r["files"][old] = r["files"].pop("D2R-XL-2012-Downloader.exe")
            r["launcher"] = old
        self.rewrite_ready(inc, edit)
        self.reseal(inc, "release-manifest.json")
        self.assert_refused(inc, "READY lists a file it may not")

    def test_two_launchers_are_refused(self):
        inc = self.upload(launcher=self.make_exe(), launcher_version="0.3.0")
        (inc / "D2R-XL-2012-Launcher.exe").write_bytes(b"MZ other")
        self.reseal(inc, "D2R-XL-2012-Launcher.exe")
        self.assert_refused(inc, "READY lists a file it may not")

    def test_published_version_never_changes_without_force(self):
        self.publish("1.0.0", "stable")
        before = tree(self.site)
        inc = self.upload("1.0.0", "stable", files={"global/excel/armor.txt": b"other\n"}, force=True)
        self.rewrite_ready(inc, lambda r: r.__setitem__("force", False))
        self.assert_refused_keeping(inc, "already published with other contents", before)
        self.rewrite_ready(inc, lambda r: r.__setitem__("force", True))
        (inc / "REFUSED").unlink()
        self.ingest()
        man = json.loads((self.site / "releases/1.0.0/release-manifest.json").read_text())
        self.assertIn(pub.sha256_bytes(b"other\n"), {f["sha256"] for f in man["files"]})
        self.assertEqual(self.channel("stable")["manifestSha256"],
                         pub.sha256_file(self.site / "releases/1.0.0/release-manifest.json"))

    def assert_refused_keeping(self, inc, words, before):
        self.ingest(expect=1)
        self.assertIn(words, self.refused(inc))
        self.assertEqual(tree(self.site), before)

    # ------------------------------------------------------------------------------------------------- order and re-runs
    def test_channel_is_written_last(self):
        inc = self.upload(launcher=self.make_exe(), launcher_version="0.3.0")
        writes = []
        real = ing.write_atomic

        def spy(dest, *a, **kw):
            writes.append(Path(dest).relative_to(self.site).as_posix())
            return real(dest, *a, **kw)

        with mock.patch.object(ing, "write_atomic", side_effect=spy):
            self.ingest()
        self.assertEqual(writes[-1], ".sync/wanted", "after everything: the trigger of the Space mirror (dl_sync.py)")
        writes.pop()
        self.assertEqual(writes[-1], "channels/stable.json")
        objects = [w for w in writes if w.startswith("objects/")]
        self.assertEqual(writes[:len(objects)], objects, "objects first")
        rest = writes[len(objects):]
        self.assertLess(rest.index("releases/1.0.0/D2R-XL-2012-1.0.0.7z"), rest.index("releases/1.0.0/release-manifest.json"))
        self.assertLess(rest.index("releases/1.0.0/release-manifest.json"), rest.index("channels/stable.json"))
        self.assertIn("launcher/0.3.0/D2R-XL-2012-Downloader.exe", rest)
        self.assertFalse(inc.exists())

    def make_exe(self):
        exe = self.tmp / "launcher.exe"
        exe.write_bytes(b"MZ launcher")
        return exe

    def test_rerun_is_idempotent(self):
        self.publish("1.0.0", "stable")
        before = tree(self.site)
        self.ingest()  # nothing pending
        self.assertEqual(tree(self.site), before)
        # the same release uploaded again (e.g. a lost answer): accepted, the 7z kept, only the channel's date may move
        inc = self.upload("1.0.0", "stable", force=True)
        self.ingest()
        after = tree(self.site)
        self.assertEqual(set(before), set(after))
        self.assertLessEqual({k for k in before if before[k] != after[k]}, {"channels/stable.json", ".sync/wanted"})  # both hold a time stamp
        self.assertFalse(inc.exists())

    def test_refused_upload_is_skipped_until_retry(self):
        inc = self.upload()
        (inc / "evil.sh").write_text("x")
        self.ingest(expect=1)
        first = self.refused(inc)
        self.ingest(expect=0)  # skipped: nothing pending
        self.assertEqual(self.refused(inc), first)
        (inc / "evil.sh").unlink()
        with mock.patch("builtins.print"):
            self.assertEqual(ing.main(["--root", str(self.srv), "--7z", self.seven, *PRODUCT_ARGS, "--retry", "1.0.0"]), 0)
        self.assertEqual(self.channel("stable")["version"], "1.0.0")

    def test_uploads_in_progress_are_left_alone(self):
        dist = self.make_dist("1.0.0")
        t = pub.DirTarget(self.site)
        with mock.patch.object(pub.DirTarget, "deliver", lambda self, up, final, items, ready, listing:
                               self.put_files([(local, f"{up}/{n}") for local, n in items])):
            pub.publish(t, dist, "1.0.0", "stable", log=lambda *_: None)
        self.assertTrue((self.incoming / "1.0.0.uploading").is_dir())
        (self.incoming / "1.0.0").mkdir()  # a folder without READY: its rename has not happened
        self.ingest()
        self.assertTrue((self.incoming / "1.0.0.uploading").is_dir())
        self.assertFalse((self.site / "channels").exists())
        # a pre-release name: "1.0.0-rc1.uploading" matches the version pattern, READY is in it before the rename
        up = self.incoming / "1.0.0-rc1.uploading"
        up.mkdir()
        (up / "READY").write_text("{}")
        self.ingest()
        self.assertFalse((up / "REFUSED").exists(), "an upload in progress is never judged")

    def test_versions_go_in_order(self):
        self.upload("1.0.0", "stable", files={"global/excel/armor.txt": b"a\n"})
        self.upload("1.0.10", "stable", files={"global/excel/armor.txt": b"b\n"})
        self.upload("1.0.9", "stable", files={"global/excel/armor.txt": b"c\n"})
        self.ingest()
        self.assertEqual(self.channel("stable")["version"], "1.0.10")
        self.assertEqual(sorted(p.name for p in (self.site / "releases").iterdir()), ["1.0.0", "1.0.10", "1.0.9"])

    def test_old_temp_files_are_cleaned(self):
        self.publish("1.0.0")
        old = self.site / "objects" / "ab" / ("c" * 64 + ".part-0")
        new = self.site / "objects" / "ab" / ("d" * 64 + ".part-1a2b")
        keep = self.site / "objects" / "ab" / ("e" * 64)
        old.parent.mkdir(exist_ok=True)
        for p in (old, new, keep):
            p.write_bytes(b"x")
        stale = time.time() - 2 * ing.PART_AGE
        os.utime(old, (stale, stale))
        os.utime(keep, (stale, stale))
        self.ingest()
        self.assertFalse(old.exists())
        self.assertTrue(new.exists(), "young: an upload may still be writing it")
        self.assertTrue(keep.exists())

    def test_built_7z_matches_the_manifest(self):
        inc = self.upload()
        self.ingest()
        man = json.loads((self.site / "releases/1.0.0/release-manifest.json").read_text())
        self.assertEqual(man["emptyDirs"], ["d2rloader/patches"])
        arch = self.site / man["archive"]["path"]
        self.assertEqual((arch.stat().st_size, pub.sha256_file(arch)), (man["archive"]["size"], man["archive"]["sha256"]))
        out = self.tmp / "x"
        subprocess.run([self.seven, "x", "-y", f"-o{out}", str(arch)], check=True, capture_output=True)
        got = sorted(p.relative_to(out / "mxl2012").as_posix() for p in (out / "mxl2012").rglob("*") if p.is_file())
        self.assertEqual(got, sorted(f["path"] for f in man["files"]))
        self.assertTrue((out / "mxl2012/d2rloader/patches").is_dir())
        self.assertFalse(inc.exists())

    @unittest.skipUnless(REAL_7Z, "reproducibility of the real 7z")
    def test_server_7z_is_the_packagers_7z(self):
        """Same files, same switches, no time stamps: the 7z built from the objects is the one package_release.py made."""
        dist = self.make_dist("1.0.0")
        self.publish("1.0.0", "stable", dist=dist)
        local = json.loads((dist / "release-manifest.json").read_text())["archive"]
        server = json.loads((self.site / "releases/1.0.0/release-manifest.json").read_text())["archive"]
        self.assertEqual((server["size"], server["sha256"]), (local["size"], local["sha256"]))

    def test_no_7zip(self):
        inc = self.upload()
        with mock.patch("builtins.print"):
            rc = ing.Ingest(self.srv, sevenzip=None, **PRODUCT).run()
        self.assertEqual(rc, 1)
        self.assertIn("no 7-Zip", self.refused(inc))

    def test_root_layout_is_checked(self):
        with self.assertRaises(SystemExit):
            ing.Ingest(self.tmp / "nothing", sevenzip=self.seven, **PRODUCT)

    def test_site_and_incoming_names_are_checked(self):
        for kw in ({"incoming_name": "mxl2012"}, {"incoming_name": "../incoming"}, {"incoming_name": ".sync"},
                   {"site_name": "a/b"}, {"site_name": ""}, {"archive_prefix": "../x"}, {"launcher_name": "a/b.exe"}):
            with self.assertRaises(SystemExit, msg=str(kw)):
                ing.Ingest(self.srv, **{**PRODUCT, **kw}, sevenzip=self.seven)

    def test_two_products_share_one_script_and_one_root(self):
        """The first product's unit (the script's defaults) and this product's unit (flags) run side by side on one /srv/dl: each
        sees only its own incoming folder and writes only its own site."""
        (self.srv / "mxl").mkdir()
        (self.srv / "incoming").mkdir()
        inc = self.upload()
        with mock.patch("builtins.print"):
            self.assertEqual(ing.main(["--root", str(self.srv), "--7z", self.seven]), 0)  # the first product's unit: nothing for it
        self.assertTrue(inc.is_dir(), "the other product's ingest leaves this upload alone")
        self.assertEqual(list((self.srv / "mxl").iterdir()), [], "and writes nothing into its own site")
        self.ingest()
        self.assertEqual(self.channel("stable")["version"], "1.0.0")
        self.assertEqual(list((self.srv / "mxl").iterdir()), [])
        self.assertEqual(list((self.srv / "incoming").iterdir()), [])
        self.assertTrue((self.site / "releases/1.0.0/D2R-XL-2012-1.0.0.7z").is_file())
        self.assertTrue((self.site / ".sync/wanted").is_file(), "the trigger of this product's sync unit")

    def test_upload_for_another_products_site_is_refused(self):
        inc = self.upload()
        with mock.patch("builtins.print"):
            rc = ing.Ingest(self.srv, sevenzip=self.seven, **{**PRODUCT, "mod_folder": "OtherMod"}).run()
        self.assertEqual(rc, 1)
        self.assertIn("modFolder 'mxl2012', this site is for 'OtherMod'", self.refused(inc))
        self.assertFalse((self.site / "channels").exists())

    def test_journal_priority(self):
        with mock.patch.object(ing, "JOURNAL", True), mock.patch("builtins.print") as p:
            ing.log("bad", error=True)
            ing.log("fine")
        self.assertEqual([c.args[0] for c in p.call_args_list], ["<3>bad", "fine"])

    def test_find_7z_prefers_7zz(self):
        with mock.patch.object(ing.shutil, "which", side_effect=lambda n: f"/usr/bin/{n}" if n in ("7zz", "7z") else None):
            self.assertEqual(ing.find_7z(), "/usr/bin/7zz")
        with mock.patch.object(ing.shutil, "which", side_effect=lambda n: "/usr/bin/7z" if n == "7z" else None):
            self.assertEqual(ing.find_7z(), "/usr/bin/7z")
        self.assertEqual(ing.find_7z("/opt/7zz"), "/opt/7zz")


class SafeRelTests(unittest.TestCase):
    def test_paths(self):
        for ok in ("a", "global/excel/armor.txt", "d2rloader/patches"):
            self.assertTrue(ing.safe_rel(ok), ok)
        for bad in ("", "/a", "a/", "../a", "a/../b", "a//b", "a\\b", "C:/x", "a/./b", "a. ", "x\x00", "aux:"):
            self.assertFalse(ing.safe_rel(bad), repr(bad))


if __name__ == "__main__":
    unittest.main()
