"""tools/publish_release.py, tools/dl_ingest.py and tools/serve_dir.py: delta selection, the upload into incoming/ (READY
last, folder rename), resume after a dropped connection, the server's ingest, promote / list / gc, the sftp backend (through
tools/fake_sftp.py) and an end-to-end publish -> ingest -> HTTP -> sha256 check. No game files, no network, no ssh. Uses
7-Zip when the machine has it, else tools/fake_7z.py."""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import dl_ingest
import package_release as pr
import publish_release as pub
import serve_dir

HERE = Path(__file__).resolve().parent
FAKE_SFTP = [sys.executable, str(HERE / "fake_sftp.py")]
REAL_7Z = pr.find_7z()
# What the ingest on the server is told for this product (docs/hosting.md): its own site and incoming folders, names, modFolder.
PRODUCT = dict(site_name="mxl2012", incoming_name="incoming-mxl2012", archive_prefix="D2R-XL-2012",
               launcher_name="D2R-XL-2012-Downloader.exe", mod_folder="mxl2012")
PRODUCT_ARGS = ["--site", "mxl2012", "--incoming", "incoming-mxl2012", "--archive-prefix", "D2R-XL-2012",
                "--launcher-name", "D2R-XL-2012-Downloader.exe", "--mod-folder", "mxl2012"]


def fake_7z_command(folder: Path) -> str:
    """A one-file command that runs tools/fake_7z.py (the tools call 7-Zip as [exe, args...])."""
    if sys.platform == "win32":
        p = folder / "fake7z.cmd"
        p.write_text(f'@"{sys.executable}" "{HERE / "fake_7z.py"}" %*\r\n')
    else:
        p = folder / "fake7z.sh"
        p.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{HERE / "fake_7z.py"}" "$@"\n')
        p.chmod(0o755)
    return str(p)


def tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


class Recorder(pub.DirTarget):
    """A DirTarget that remembers every write (rel paths, in order) and can die at the n-th one."""

    def __init__(self, root, fail_at=0):
        super().__init__(root)
        self.puts, self.fail_at, self.renames = [], fail_at, []

    def put_files(self, items):
        for local, rel in items:
            if self.fail_at and len(self.puts) + 1 == self.fail_at:
                raise pub.PublishError("connection lost (test)")
            self.puts.append(rel)
            super().put_files([(local, rel)])

    def deliver(self, up, final, items, ready, listing):
        super().deliver(up, final, items, ready, listing)
        self.renames.append((up, final))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.seven = REAL_7Z or fake_7z_command(self.tmp)
        p = mock.patch.object(pub, "find_7z", return_value=self.seven)
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(pub, "RETRY_WAIT", 0)
        p.start()
        self.addCleanup(p.stop)
        self.dll = self.tmp / "mxl2012-core.dll"
        self.dll.write_bytes(b"MZ..." + pr.plugin_version().encode() + b"\0...")
        self.srv = self.tmp / "srv"  # /srv/dl on the server
        self.site = self.srv / "mxl2012"
        self.incoming = self.srv / "incoming-mxl2012"
        self.site.mkdir(parents=True)
        self.incoming.mkdir()

    def make_dist(self, version, files=None, complete=True):
        """A real package_release output (stage, 7z, manifest, notes) from a tiny fake data folder."""
        data = self.tmp / f"data-{version}"
        shutil.rmtree(data, ignore_errors=True)
        base = {"global/excel/armor.txt": b"Median armor\n", "global/excel/weapons.txt": b"Median weapons\n",
                "global/excel/copy-of-weapons.txt": b"Median weapons\n"}  # same bytes twice: one object
        for rel, body in (files or base).items():
            (data / rel).parent.mkdir(parents=True, exist_ok=True)
            (data / rel).write_bytes(body)
        out = self.tmp / f"dist-{version}"
        mod = out / "stage" / "mxl2012"
        pr.stage(mod, version, self.dll, self.tmp, data_from=data)
        seven = out / f"D2R-XL-2012-{version}.7z"
        pr.write_7z(mod, seven, self.seven)
        man = pr.manifest(version, pr.file_list(mod), seven, complete, pr.empty_dirs(mod))
        (out / "release-manifest.json").write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
        (out / f"RELEASE_NOTES-{version}.md").write_text(f"notes {version}\n", encoding="utf-8")
        shutil.rmtree(out / "stage")
        return out

    def ingest(self, expect=0):
        with mock.patch("builtins.print"):
            rc = dl_ingest.Ingest(self.srv, sevenzip=self.seven, **PRODUCT).run()
        self.assertEqual(rc, expect)

    def publish(self, version, channel="test", target=None, files=None, ingest=True, dist=None, **kw):
        target = target or pub.DirTarget(self.site)
        info = pub.publish(target, dist or self.make_dist(version, files), version, channel, log=lambda *_: None, **kw)
        if ingest:
            self.ingest()
        return info

    def channel(self, name):
        return json.loads((self.site / "channels" / f"{name}.json").read_text("utf-8"))

    def ready(self, version):
        return json.loads((self.incoming / version / "READY").read_text("utf-8"))


class PublishTests(Base):
    def test_layout_after_the_servers_ingest(self):
        info = self.publish("1.0.0", "stable")
        self.assertEqual(info["state"], "uploaded")
        t = tree(self.site)
        ch = self.channel("stable")
        self.assertEqual(set(ch), {"schemaVersion", "version", "manifest", "manifestSha256", "publishedAt"})
        self.assertEqual((ch["schemaVersion"], ch["version"]), (1, "1.0.0"))
        self.assertEqual(ch["manifest"], "releases/1.0.0/release-manifest.json")
        self.assertEqual(pub.sha256_bytes(t[ch["manifest"]]), ch["manifestSha256"])
        man = json.loads(t[ch["manifest"]])
        self.assertEqual(man["schemaVersion"], 2)
        self.assertEqual(man["objectsBase"], "objects/")
        self.assertNotIn("zip", man)
        body = t["releases/1.0.0/D2R-XL-2012-1.0.0.7z"]
        self.assertEqual(man["archive"], {"format": "7z", "name": "D2R-XL-2012-1.0.0.7z", "size": len(body),
                                          "sha256": pub.sha256_bytes(body), "path": "releases/1.0.0/D2R-XL-2012-1.0.0.7z"})
        for f in man["files"]:
            self.assertEqual(pub.sha256_bytes(t[pub.object_path(f["sha256"])]), f["sha256"])
        sums = t["releases/1.0.0/SHA256SUMS"].decode().splitlines()
        self.assertEqual(sorted(sums), sorted([f"{man['archive']['sha256']}  D2R-XL-2012-1.0.0.7z",
                                               f"{ch['manifestSha256']}  release-manifest.json",
                                               f"{pub.sha256_bytes(b'notes 1.0.0' + os.linesep.encode())}  RELEASE_NOTES-1.0.0.md"]))
        self.assertFalse([k for k in t if k.endswith(".zip")])
        self.assertTrue(all(pub.PART not in k for k in t), "no temp files left")
        self.assertEqual([p.name for p in self.incoming.iterdir() if not p.name.startswith(".")], [], "incoming emptied")

    def test_server_7z_holds_the_release(self):
        self.publish("1.0.0", "stable")
        man = json.loads((self.site / "releases/1.0.0/release-manifest.json").read_text())
        out = self.tmp / "unpacked"
        subprocess.run([self.seven, "x", "-y", f"-o{out}", str(self.site / "releases/1.0.0/D2R-XL-2012-1.0.0.7z")],
                       check=True, capture_output=True)
        got = pr.file_list(out / "mxl2012")
        self.assertEqual([(f["path"], f["size"], f["sha256"]) for f in got],
                         [(f["path"], f["size"], f["sha256"]) for f in man["files"]])
        self.assertTrue((out / "mxl2012" / "d2rloader" / "patches").is_dir(), "emptyDirs")

    def test_delta_selection_packs_only_what_the_host_lacks(self):
        self.publish("1.0.0")
        objs = {p.name for p in self.site.glob("objects/*/*")}
        man1 = json.loads((self.site / "releases/1.0.0/release-manifest.json").read_text())
        self.assertEqual(objs, {f["sha256"] for f in man1["files"]}, "first release: every object, once")
        # 1.1.0 changes one data file; metadata.json (modVersion) differs anyway; everything else is shared
        self.publish("1.1.0", files={"global/excel/armor.txt": b"Median armor v2\n", "global/excel/weapons.txt": b"Median weapons\n"},
                     ingest=False)
        ready = self.ready("1.1.0")
        man2 = json.loads((self.incoming / "1.1.0" / "release-manifest.json").read_text())
        new = {f["sha256"] for f in man2["files"]} - objs
        self.assertEqual(len(new), 2)
        self.assertEqual(ready["objectCount"], 2)
        listing = subprocess.run([self.seven, "l", "-slt", str(self.incoming / "1.1.0" / ready["objectsPack"])],
                                 capture_output=True, text=True).stdout
        entries = {ln[7:] for ln in listing.split("----------", 1)[1].splitlines() if ln.startswith("Path = ")}
        self.assertEqual(entries, new, "the pack holds exactly the missing objects, named by sha256")
        self.ingest()
        self.assertEqual({p.name for p in self.site.glob("objects/*/*")}, objs | new)

    def test_no_missing_objects_no_pack(self):
        self.publish("1.0.0")
        dist = self.make_dist("1.0.0")
        man = json.loads((dist / "release-manifest.json").read_text())
        man["version"] = "1.0.1"
        (dist / "release-manifest.json").write_text(json.dumps(man))
        (dist / "RELEASE_NOTES-1.0.0.md").unlink()
        self.publish("1.0.1", dist=dist, ingest=False)
        ready = self.ready("1.0.1")
        self.assertIsNone(ready["objectsPack"])
        self.assertEqual(sorted(ready["files"]), ["release-manifest.json"])
        self.ingest()
        self.assertTrue((self.site / "releases/1.0.1/D2R-XL-2012-1.0.1.7z").is_file())

    def test_dist_of_another_product_is_refused(self):
        dist = self.make_dist("1.0.0")
        man_path = dist / "release-manifest.json"
        man = json.loads(man_path.read_text("utf-8"))
        man.update(name="OtherMod", modFolder="OtherMod")
        man_path.write_text(json.dumps(man), encoding="utf-8")
        with self.assertRaises(pub.PublishError) as e:
            pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "test", log=lambda *_: None)
        self.assertIn("another product", str(e.exception))
        self.assertEqual(list(self.incoming.iterdir()), [], "nothing was uploaded")

    def test_ready_last_then_folder_rename(self):
        t = Recorder(self.site)
        self.publish("1.0.0", "stable", target=t, ingest=False)
        up, final = "../incoming-mxl2012/1.0.0.uploading", "../incoming-mxl2012/1.0.0"
        inc = [p for p in t.puts if p.startswith(up)]
        self.assertEqual(inc[-1], f"{up}/READY")
        self.assertEqual(t.renames, [(up, final)])
        self.assertFalse(self.site.joinpath("channels").exists(), "the publisher never writes the channel itself")
        self.assertEqual({p.name for p in self.incoming.iterdir()}, {"1.0.0"})
        self.assertEqual(self.ready("1.0.0")["channel"], "stable")

    def test_waiting_upload_is_not_sent_again(self):
        dist = self.make_dist("1.0.0")
        self.publish("1.0.0", dist=dist, ingest=False)
        r = Recorder(self.site)
        info = pub.publish(r, dist, "1.0.0", "test", log=lambda *_: None)
        self.assertEqual(info["state"], "waiting")
        self.assertEqual(r.puts, [])
        with self.assertRaises(pub.PublishError):  # other content under the same version, still waiting
            self.publish("1.0.0", files={"global/excel/armor.txt": b"other\n"}, ingest=False)

    def test_rerun_after_publishing_is_safe(self):
        dist = self.make_dist("1.0.0")
        self.publish("1.0.0", "stable", dist=dist)
        before = tree(self.site)
        r = Recorder(self.site)
        info = pub.publish(r, dist, "1.0.0", "stable", log=lambda *_: None)
        self.assertEqual(info["state"], "published")
        self.assertEqual(r.puts, ["channels/stable.json"])
        after = tree(self.site)
        self.assertEqual(set(before), set(after))
        self.assertLessEqual({k for k in before if before[k] != after[k]}, {"channels/stable.json"}, "only publishedAt moves")

    def test_published_version_never_changes(self):
        self.publish("1.0.0")
        with self.assertRaises(pub.PublishError):
            self.publish("1.0.0", files={"global/excel/armor.txt": b"other\n"}, ingest=False)

    def test_refused_upload_is_reported_and_force_replaces_it(self):
        dist = self.make_dist("1.0.0")
        self.publish("1.0.0", "stable", dist=dist, ingest=False)
        notes = self.incoming / "1.0.0" / "RELEASE_NOTES-1.0.0.md"
        notes.write_bytes(b"damaged on the way\n")
        self.ingest(expect=1)
        self.assertTrue((self.incoming / "1.0.0" / "REFUSED").is_file())
        with self.assertRaises(pub.PublishError) as e:
            pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "stable", log=lambda *_: None)
        self.assertIn("RELEASE_NOTES-1.0.0.md does not match READY", str(e.exception))
        pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "stable", force=True, log=lambda *_: None)
        self.ingest()
        self.assertEqual(self.channel("stable")["version"], "1.0.0")

    def test_object_with_the_wrong_size_is_sent_again(self):
        self.publish("1.0.0")
        victim = self.site / pub.object_path(pub.sha256_bytes(b"Median armor\n"))  # 1.0.1 has it too
        good = victim.read_bytes()
        victim.write_bytes(good[:3])
        dist = self.make_dist("1.0.1")
        self.publish("1.0.1", dist=dist, ingest=False)
        self.assertGreaterEqual(self.ready("1.0.1")["objectCount"], 1)
        self.ingest()
        self.assertEqual(victim.read_bytes(), good)

    def test_7z_content_must_match_the_manifest(self):
        dist = self.make_dist("1.0.0")
        man = json.loads((dist / "release-manifest.json").read_text())
        man["files"][0]["sha256"] = "0" * 64
        (dist / "release-manifest.json").write_text(json.dumps(man))
        with self.assertRaises(pub.PublishError):
            pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "test", log=lambda *_: None)
        seven = dist / "D2R-XL-2012-1.0.0.7z"
        seven.write_bytes(seven.read_bytes() + b"!")
        with self.assertRaises(pub.PublishError):
            pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "test", log=lambda *_: None)
        self.assertEqual(list(self.incoming.iterdir()), [])

    def test_old_schema_is_refused(self):
        dist = self.make_dist("1.0.0")
        man = json.loads((dist / "release-manifest.json").read_text())
        man["schemaVersion"] = 1
        (dist / "release-manifest.json").write_text(json.dumps(man))
        with self.assertRaises(pub.PublishError):
            pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "test", log=lambda *_: None)

    def test_incomplete_package_is_not_for_stable(self):
        dist = self.make_dist("1.0.0", complete=False)
        t = pub.DirTarget(self.site)
        for kw in ({"channel": "stable", "allow_incomplete": True}, {"channel": "test"}):
            with self.assertRaises(pub.PublishError):
                pub.publish(t, dist, "1.0.0", log=lambda *_: None, **kw)
        pub.publish(t, dist, "1.0.0", "test", allow_incomplete=True, log=lambda *_: None)
        self.ingest()
        self.assertEqual(self.channel("test")["version"], "1.0.0")
        self.assertTrue((self.site / "releases/1.0.0/D2R-XL-2012-1.0.0-nodata.7z").is_file())
        with self.assertRaises(pub.PublishError):
            pub.promote(t, "1.0.0", "stable", log=lambda *_: None)

    def test_wrong_version_is_refused(self):
        dist = self.make_dist("1.0.0")
        with self.assertRaises(pub.PublishError):
            pub.publish(pub.DirTarget(self.site), dist, "1.0.1", "test", log=lambda *_: None)

    def test_launcher_and_assets(self):
        exe = self.tmp / "launcher.exe"
        exe.write_bytes(b"MZ launcher")
        assets = self.tmp / "assets"
        assets.mkdir()
        (assets / "pack-1.zip").write_bytes(b"pack")
        self.publish("1.0.0", launcher=exe, launcher_version="0.3.0", assets=assets)
        t = tree(self.site)
        self.assertEqual(t["launcher/0.3.0/D2R-XL-2012-Downloader.exe"], b"MZ launcher")
        self.assertEqual(t["launcher/0.3.0/D2R-XL-2012-Downloader.exe.sha256"].decode().split()[0], pub.sha256_file(exe))
        self.assertEqual(t["assets/pack-1.zip"], b"pack")
        man = json.loads(t["releases/1.0.0/release-manifest.json"])
        self.assertEqual(man["launcher"]["path"], "launcher/0.3.0/D2R-XL-2012-Downloader.exe")
        self.assertEqual(man["launcher"]["sha256"], pub.sha256_file(exe))

    def test_publish_from_a_stage_folder(self):
        dist = self.make_dist("1.0.0")
        stage = self.tmp / "unpacked"
        subprocess.run([self.seven, "x", "-y", f"-o{stage}", str(dist / "D2R-XL-2012-1.0.0.7z")], check=True, capture_output=True)
        pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "test", source=pub.DirSource(stage / "mxl2012"), log=lambda *_: None)
        self.ingest()
        self.assertEqual(self.channel("test")["version"], "1.0.0")

    def test_pack_is_cached_for_a_rerun(self):
        dist = self.make_dist("1.0.0")
        t = Recorder(self.site, fail_at=1)
        with mock.patch.object(pub.DirTarget, "deliver", side_effect=pub.PublishError("down")):
            with self.assertRaises(pub.PublishError):
                pub.publish(t, dist, "1.0.0", "test", retries=1, log=lambda *_: None)
        packs = list((dist / "upload" / "1.0.0").glob("objects-set-*.7z"))
        self.assertEqual(len(packs), 1)
        logs = []
        pub.publish(pub.DirTarget(self.site), dist, "1.0.0", "test", log=logs.append)
        self.assertTrue(any("reused" in ln for ln in logs), logs)


class PromoteListGcTests(Base):
    def setUp(self):
        super().setUp()
        self.t = pub.DirTarget(self.site)
        # 1.0.0 stable, 1.1.0 test, 1.2.0 and 1.3.0 no channel; each version has data of its own plus shared files
        for v in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
            files = {"global/excel/armor.txt": b"shared\n", f"global/excel/only-{v}.txt": f"only {v}\n".encode()}
            self.publish(v, {"1.0.0": "stable", "1.1.0": "test"}.get(v), files=files)

    def refs(self, v):
        return {f["sha256"] for f in json.loads((self.site / f"releases/{v}/release-manifest.json").read_text())["files"]}

    def objects(self):
        return {p.name for p in self.site.glob("objects/*/*")}

    def test_promote(self):
        pub.promote(self.t, "1.2.0", "stable", log=lambda *_: None)
        ch = self.channel("stable")
        self.assertEqual(ch["version"], "1.2.0")
        self.assertEqual(ch["manifestSha256"], pub.sha256_file(self.site / "releases/1.2.0/release-manifest.json"))
        with self.assertRaises(pub.PublishError):
            pub.promote(self.t, "9.9.9", "stable", log=lambda *_: None)
        victim = next(iter(self.refs("1.3.0") - self.refs("1.2.0")))
        (self.site / pub.object_path(victim)).unlink()
        with self.assertRaises(pub.PublishError):
            pub.promote(self.t, "1.3.0", "stable", log=lambda *_: None)
        self.assertEqual(self.channel("stable")["version"], "1.2.0", "a refused promote leaves the channel alone")

    def test_list(self):
        out = []
        versions, chans = pub.list_cmd(self.t, out.append)
        self.assertEqual(versions, ["1.0.0", "1.1.0", "1.2.0", "1.3.0"])
        self.assertEqual({k: v["version"] for k, v in chans.items()}, {"stable": "1.0.0", "test": "1.1.0"})
        self.assertTrue(any("1.0.0" in ln and "stable" in ln and "7z" in ln for ln in out))

    def test_gc_never_touches_channel_versions(self):
        expect = self.refs("1.2.0") - self.refs("1.0.0") - self.refs("1.1.0") - self.refs("1.3.0")
        doomed, orphans = pub.gc(self.t, 1, log=lambda *_: None)
        self.assertEqual(doomed, ["1.2.0"])  # kept: newest 1.3.0 + stable 1.0.0 + test 1.1.0
        self.assertEqual(pub.release_versions(self.t), ["1.0.0", "1.1.0", "1.3.0"])
        for v in ("1.0.0", "1.1.0", "1.3.0"):
            self.assertTrue(self.refs(v) <= self.objects(), f"every object of {v} is still there")
        self.assertEqual(self.objects(), self.refs("1.0.0") | self.refs("1.1.0") | self.refs("1.3.0"))
        self.assertEqual({Path(rel).name for rel, _ in orphans}, expect)
        self.assertTrue(len(expect) >= 1)
        self.assertEqual(self.channel("stable")["version"], "1.0.0")

    def test_gc_keep_two(self):
        pub.gc(self.t, 2, log=lambda *_: None)
        self.assertEqual(pub.release_versions(self.t), ["1.0.0", "1.1.0", "1.2.0", "1.3.0"])  # 1.2.0 + 1.3.0 newest two
        pub.promote(self.t, "1.3.0", "stable", log=lambda *_: None)
        pub.promote(self.t, "1.3.0", "test", log=lambda *_: None)
        pub.gc(self.t, 1, log=lambda *_: None)
        self.assertEqual(pub.release_versions(self.t), ["1.3.0"])
        self.assertEqual(self.objects(), self.refs("1.3.0"))

    def test_gc_dry_run_deletes_nothing(self):
        before = tree(self.site)
        pub.gc(self.t, 1, dry_run=True, log=lambda *_: None)
        self.assertEqual(tree(self.site), before)

    def test_gc_refuses_when_a_channel_points_nowhere(self):
        shutil.rmtree(self.site / "releases/1.0.0")
        before = tree(self.site)
        with self.assertRaises(pub.PublishError):
            pub.gc(self.t, 1, log=lambda *_: None)
        self.assertEqual(tree(self.site), before)

    def test_gc_sees_every_channel_file(self):
        extra = dict(self.channel("stable"), version="1.2.0", manifest="releases/1.2.0/release-manifest.json")
        (self.site / "channels/beta.json").write_text(json.dumps(extra))
        pub.gc(self.t, 1, log=lambda *_: None)
        self.assertIn("1.2.0", pub.release_versions(self.t))

    def test_gc_removes_unfinished_releases_and_temp_files(self):
        (self.site / "releases/1.4.0").mkdir()
        (self.site / "releases/1.4.0/D2R-XL-2012-1.4.0.7z").write_bytes(b"half")  # an ingest that died before its manifest
        stale = self.site / "objects/ab" / ("c" * 64 + pub.PART + "1234")
        stale.parent.mkdir(exist_ok=True)
        stale.write_bytes(b"x")
        pub.gc(self.t, 1, log=lambda *_: None)
        self.assertFalse((self.site / "releases/1.4.0").exists())
        self.assertFalse(stale.exists())
        self.assertIn("1.3.0", pub.release_versions(self.t))

    def test_gc_keeps_a_launcher_still_in_use(self):
        exe = self.tmp / "l.exe"
        exe.write_bytes(b"L")
        self.publish("1.4.0", files={"global/excel/armor.txt": b"x\n"}, launcher=exe, launcher_version="0.9.0")
        self.publish("1.5.0", files={"global/excel/armor.txt": b"y\n"}, launcher=exe, launcher_version="0.9.0")
        pub.gc(self.t, 1, log=lambda *_: None)
        self.assertTrue((self.site / "launcher/0.9.0/D2R-XL-2012-Downloader.exe").exists())


class VersionTests(unittest.TestCase):
    def test_order_and_validation(self):
        vs = ["0.70.0", "0.9.0", "0.70.1", "1.0.0-rc1", "1.0.0", "0.100.0"]
        self.assertEqual(sorted(vs, key=pub.version_key), ["0.9.0", "0.70.0", "0.70.1", "0.100.0", "1.0.0-rc1", "1.0.0"])
        self.assertEqual(sorted(vs, key=dl_ingest.version_key), sorted(vs, key=pub.version_key))
        self.assertEqual(pub.check_version("v0.70.0"), "0.70.0")
        for bad in ("../x", "1.2", "1.2.3/../../x", "latest", ""):
            with self.assertRaises(SystemExit):
                pub.check_version(bad)

    def test_exe_version(self):
        import struct
        key = "VS_VERSION_INFO".encode("utf-16-le") + b"\0\0"
        fixed = bytes.fromhex("bd04effe") + struct.pack("<III", 0x10000, (0 << 16) | 1, (2 << 16) | 0)
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "x.exe"
            # the signature bytes once in "code" before the resource, then the real VS_FIXEDFILEINFO
            exe.write_bytes(b"MZ" + bytes.fromhex("bd04effe") + b"\x07" * 12 + key + fixed)
            self.assertEqual(pub.exe_version(exe), "0.1.2")
            exe.write_bytes(b"MZ no resource")
            self.assertEqual(pub.exe_version(exe), "")

    def test_sftp_target_parse(self):
        t = pub.SftpTarget.parse("sftp://upload@dlhost:2222/mxl2012/")
        self.assertEqual((t.user, t.host, t.port, t.path), ("upload", "dlhost", 2222, "/mxl2012"))
        self.assertEqual(t._abs(pub.INCOMING + "/1.0.0"), "/mxl2012/../incoming-mxl2012/1.0.0")
        t = pub.SftpTarget.parse("sftp://u@h/~/site")
        self.assertEqual((t.port, t.path), (None, "site"))
        self.assertEqual(t._abs("objects/ab"), "site/objects/ab")
        with self.assertRaises(SystemExit):
            pub.SftpTarget.parse("ftp://x/y")

    def test_ls_parse(self):
        lines = ["-rw-r--r--    1 1000     1000       123456 Oct 26 10:00 abc",
                 "drwxr-xr-x    2 0        0            4096 Oct 26 2025 a dir",
                 "-rw-r--r--    1 0        0               0 Jan  1 00:00 ."]
        self.assertEqual(pub.parse_sftp_ls(lines), {"abc": (123456, False), "a dir": (4096, True)})

    def test_ls_parse_openssh_forms(self):
        """What OpenSSH's sftp prints for `ls -ln "/mxl2012/releases"`: the listed path + '/' + name, numeric ids, both
        date forms; Windows' client prints the permissions as '*********' (the cause of an empty `list` on the real host)."""
        d = "/mxl2012/releases"
        lines = ["drwxr-xr-x    0 1001     1001         4096 Oct 29 00:05 /mxl2012/releases/0.1.0",
                 "drwxr-xr-x    2 0        0            4096 Oct 29  2025 /mxl2012/releases/0.0.1",
                 "-rw-r--r--    1 1001     1001          321 Jan  1 09:15 /mxl2012/releases/notes with spaces.txt",
                 "d*********    0 1001     1001         4096 Oct 29 00:05 /mxl2012/releases/0.2.0",
                 "-*********    0 1001     1001           17 Oct  9  2025 /mxl2012/releases/a  b",
                 "?*********    0 0        0               5 Oct 29 00:05 /mxl2012/releases/odd",
                 "drwxr-xr-x+   1 1001     1001         4096 29 Oct 00:05 /mxl2012/releases/0.3.0/",
                 "-rw-r--r--    1 1001     1001            9  /mxl2012/releases/nodate",
                 "-rw-r--r--    1 1001     1001            0 Oct 29 00:05 /mxl2012/releases/.",
                 ""]
        got = pub.parse_sftp_ls(lines, d)
        self.assertEqual(got, {"0.1.0": (4096, True), "0.0.1": (4096, True), "notes with spaces.txt": (321, False), "0.2.0": (4096, True),
                               "a  b": (17, False), "odd": (5, False), "0.3.0": (4096, True), "nodate": (9, False)})
        # a relative target path ("sftp://u@h/~/site") lists "site/channels/<name>"
        self.assertEqual(pub.parse_sftp_ls(["-*********    0 1001  1001  250 Oct 29 00:05 site/channels/test.json"],
                                           "site/channels"), {"test.json": (250, False)})
        # the real host through a Windows sftp client (2026-10-29): partly masked modes and '?' as the link count
        self.assertEqual(pub.parse_sftp_ls(["-rw-******    ? 1003     1003          225 Oct 29 09:05 /mxl2012/channels/test.json",
                                            "drwx******    ? 1003     1003         4096 Oct 29 09:05 /mxl2012/channels/old"],
                                           "/mxl2012/channels"), {"test.json": (225, False), "old": (4096, True)})
        self.assertEqual(pub.parse_sftp_ls([], d), {}, "an empty folder")

    def test_ls_parse_refuses_what_it_does_not_understand(self):
        for ln in ("total 8", "Couldn't stat remote file: No such file or directory",
                   "-rw-r--r-- 1 1001 1001 big Oct 29 00:05 /mxl2012/channels/x",
                   "-rw-r--r--    1 1001     1001   9 Oct 29 00:05 /mxl2012/channels/sub/x"):
            with self.assertRaises(pub.PublishError, msg=ln):
                pub.parse_sftp_ls([ln], "/mxl2012/channels")

    def test_snapshot_splits_the_batch_output_per_folder(self):
        t = pub.SftpTarget("mxlup", "example.invalid", None, "/mxl2012")
        out = ['sftp> -ls -ln "/mxl2012/channels"',
               "-*********    0 1001     1001          250 Oct 29 00:05 /mxl2012/channels/test.json",
               'sftp> -ls -ln "/mxl2012/releases"',
               "d*********    0 1001     1001            0 Oct 29 00:05 /mxl2012/releases/0.0.1",
               "d*********    0 1001     1001            0 Oct 29  2025 /mxl2012/releases/0.1.0",
               'sftp> -ls -ln "/mxl2012/objects/ab"',
               'sftp> -ls -ln "/mxl2012/objects/cd"',
               'sftp> -get "/mxl2012/.sync/status.json" "C:/x/f0"',
               "Fetching /mxl2012/.sync/status.json to C:/x/f0"]
        err = 'Can\'t ls: "/mxl2012/objects/cd" not found\n'
        dirs = ["channels", "releases", "objects/ab", "objects/cd"]
        with mock.patch.object(pub.SftpTarget, "_run", return_value=(out, err)):
            got, _ = t.snapshot(dirs, [".sync/status.json"])
        self.assertEqual(got, {"channels": {"test.json": (250, False)},
                               "releases": {"0.0.1": (0, True), "0.1.0": (0, True)}, "objects/ab": {}, "objects/cd": None})
        # an sftp that does not echo the commands: lines go to the folder they name
        quiet = [ln for ln in out if not ln.startswith(pub.ECHO)]
        with mock.patch.object(pub.SftpTarget, "_run", return_value=(quiet, err)):
            got2, _ = t.snapshot(dirs, [".sync/status.json"])
        self.assertEqual(got2, got)


class SftpTests(Base):
    """The chroot as the sftp user sees it: / = srv (holds mxl2012/ and incoming-mxl2012/; the real chroot also holds the first product's mxl/ and incoming/)."""

    def target(self):
        return pub.SftpTarget("mxlup", "example.invalid", 2222, "/mxl2012", sftp_cmd=FAKE_SFTP)

    def setUp(self):
        super().setUp()
        self.log = self.tmp / "sftp.log"
        p = mock.patch.dict(os.environ, {"FAKE_SFTP_ROOT": str(self.srv), "FAKE_SFTP_LOG": str(self.log)})
        p.start()
        self.addCleanup(p.stop)

    def commands(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_same_result_as_a_dir_target_in_two_logins(self):
        dist = self.make_dist("1.0.0")
        ref = self.tmp / "ref"
        (ref / "mxl2012").mkdir(parents=True)
        (ref / "incoming-mxl2012").mkdir()
        pub.publish(pub.DirTarget(ref / "mxl2012"), dist, "1.0.0", "stable", log=lambda *_: None)
        with mock.patch("builtins.print"):
            dl_ingest.Ingest(ref, sevenzip=self.seven, **PRODUCT).run()
        t = self.target()
        self.publish("1.0.0", "stable", target=t, dist=dist, ingest=False)
        self.assertEqual(t.logins, 2, "one login for the state, one for the upload")
        cmds = [c for c in self.commands() if c != "LOGIN"]
        self.assertTrue(cmds[-2].startswith('rename "/mxl2012/../incoming-mxl2012/1.0.0.uploading/READY.part-0"'), cmds[-3:])
        self.assertEqual(cmds[-1], 'rename "/mxl2012/../incoming-mxl2012/1.0.0.uploading" "/mxl2012/../incoming-mxl2012/1.0.0"')
        self.ingest()
        a, b = tree(ref / "mxl2012"), tree(self.site)
        self.assertEqual(set(a), set(b))
        for k in a:
            if k not in ("channels/stable.json", ".sync/wanted"):  # both hold a time stamp
                self.assertEqual(a[k], b[k], k)

    def test_resume_after_connection_reset(self):
        dist = self.make_dist("1.0.0", files={f"global/excel/t{i}.txt": os.urandom(3000) for i in range(20)})
        cut = self.tmp / "cut"
        cut.write_text("2 4000")  # the first two logins that send more than 4000 bytes die after 4000
        with mock.patch.dict(os.environ, {"FAKE_SFTP_CUT": str(cut)}):
            info = self.publish("1.0.0", "stable", target=self.target(), dist=dist, ingest=False)
        self.assertEqual(info["state"], "uploaded")
        cmds = self.commands()
        self.assertEqual(sum(1 for c in cmds if c.startswith("reput ")), 2, "the objects 7z was resumed, twice")
        pack = self.ready("1.0.0")["objectsPack"]
        self.assertEqual(pub.sha256_file(self.incoming / "1.0.0" / pack), self.ready("1.0.0")["files"][pack]["sha256"])
        self.ingest()
        self.assertEqual(self.channel("stable")["version"], "1.0.0")

    def test_gives_up_after_the_retries(self):
        dist = self.make_dist("1.0.0")
        cut = self.tmp / "cut"
        cut.write_text("99 10")
        with mock.patch.dict(os.environ, {"FAKE_SFTP_CUT": str(cut)}):
            with self.assertRaises(pub.PublishError) as e:
                self.publish("1.0.0", "stable", target=self.target(), dist=dist, ingest=False, retries=2)
        self.assertIn("Run the same command again", str(e.exception))
        self.assertFalse((self.incoming / "1.0.0").exists(), "no READY folder after a failed upload")
        self.assertFalse(self.site.joinpath("channels").exists())

    def test_existing_objects_are_listed_in_one_login(self):
        self.publish("1.0.0", target=self.target())
        self.log.unlink()
        t = self.target()
        info = self.publish("1.1.0", target=t, files={"global/excel/armor.txt": b"v2\n"}, ingest=False)
        self.assertEqual(t.logins, 2)
        self.assertEqual(info["objects"], 2)

    def test_list_and_gc_over_sftp(self):
        for v, ch in (("1.0.0", "stable"), ("1.1.0", None), ("1.2.0", None)):
            self.publish(v, ch, target=self.target(), files={"global/excel/armor.txt": v.encode()})
        t = self.target()
        out = []
        versions, chans = pub.list_cmd(t, out.append)
        self.assertEqual(versions, ["1.0.0", "1.1.0", "1.2.0"])
        self.assertEqual(chans["stable"]["version"], "1.0.0")
        pub.gc(t, 1, log=lambda *_: None)
        self.assertEqual(pub.release_versions(t), ["1.0.0", "1.2.0"])
        self.assertIsNone(t.list_dir("releases/1.1.0"))
        self.assertEqual(t.read("channels/nothing.json"), None)

    def test_list_and_gc_with_the_windows_client_listing(self):
        with mock.patch.dict(os.environ, {"FAKE_SFTP_WINDOWS": "1"}):
            for v, ch in (("1.0.0", "stable"), ("1.1.0", None), ("1.2.0", "test")):
                self.publish(v, ch, target=self.target(), files={"global/excel/armor.txt": v.encode()})
            t = self.target()
            out = []
            versions, chans = pub.list_cmd(t, out.append)
            self.assertEqual(versions, ["1.0.0", "1.1.0", "1.2.0"])
            self.assertEqual((chans["stable"]["version"], chans["test"]["version"]), ("1.0.0", "1.2.0"))
            self.assertTrue(any(ln.startswith("channel test    1.2.0") for ln in out), out)
            pub.gc(t, 1, log=lambda *_: None)
            self.assertEqual(pub.release_versions(t), ["1.0.0", "1.2.0"])

    def test_gc_refuses_when_the_listing_hides_the_channel_files(self):
        for v, ch in (("1.0.0", "stable"), ("1.1.0", None), ("1.2.0", None)):
            self.publish(v, ch, target=self.target(), files={"global/excel/armor.txt": v.encode()})
        before = tree(self.site)
        real = pub.SftpTarget.snapshot

        def blind(self_, dirs, files):  # a listing that comes back empty although the files are there
            listings, contents = real(self_, dirs, files)
            return {d: ({} if d == "channels" else v) for d, v in listings.items()}, contents
        with mock.patch.object(pub.SftpTarget, "snapshot", blind):
            with self.assertRaises(pub.PublishError) as e:
                pub.gc(self.target(), 1, log=lambda *_: None)
            self.assertIn("channels/stable.json", str(e.exception))
            with self.assertRaises(pub.PublishError):
                pub.list_cmd(self.target(), lambda *_: None)
        self.assertEqual(tree(self.site), before, "nothing deleted")

    def test_listing_error_is_not_mistaken_for_an_empty_folder(self):
        t = self.target()
        with mock.patch.object(pub.SftpTarget, "_run", return_value=([], "Couldn't read directory: Permission denied")):
            with self.assertRaises(pub.PublishError):
                t.list_dir("objects/ab")


class ServeAndVerifyTests(Base):
    def get(self, url, headers=None, method="GET"):
        req = urllib.request.Request(url, headers=headers or {}, method=method)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_range_server(self):
        (self.site / "f.bin").write_bytes(bytes(range(100)))
        (self.site / "objects").mkdir()
        (self.site / "objects" / "o").write_bytes(b"x")
        with serve_dir.running(self.site) as base:
            st, h, body = self.get(base + "f.bin")
            self.assertEqual((st, len(body), h["Accept-Ranges"]), (200, 100, "bytes"))
            self.assertEqual(h["Cache-Control"], "no-cache")
            st, h, body = self.get(base + "f.bin", {"Range": "bytes=10-19"})
            self.assertEqual((st, body, h["Content-Range"]), (206, bytes(range(10, 20)), "bytes 10-19/100"))
            st, h, body = self.get(base + "f.bin", {"Range": "bytes=90-"})
            self.assertEqual((st, body), (206, bytes(range(90, 100))))
            st, h, body = self.get(base + "f.bin", {"Range": "bytes=-5"})
            self.assertEqual((st, body, h["Content-Range"]), (206, bytes(range(95, 100)), "bytes 95-99/100"))
            st, h, body = self.get(base + "f.bin", {"Range": "bytes=50-500"})
            self.assertEqual((st, len(body), h["Content-Range"]), (206, 50, "bytes 50-99/100"))
            self.assertEqual(self.get(base + "f.bin", {"Range": "bytes=100-"})[0], 416)
            st, h, body = self.get(base + "f.bin", method="HEAD")
            self.assertEqual((st, body, h["Content-Length"]), (200, b"", "100"))
            self.assertEqual(self.get(base + "missing")[0], 404)
            self.assertEqual(self.get(base + "objects/")[0], 404, "no directory listing")
            self.assertIn("immutable", self.get(base + "objects/o")[1]["Cache-Control"])
            st, h, _ = self.get(base + "f.bin")
            self.assertEqual(self.get(base + "f.bin", {"If-None-Match": h["ETag"]})[0], 304)
            self.assertEqual(self.get(base + "..%2f..%2fetc/passwd")[0], 404)
            self.assertEqual(self.get(base + "%2e%2e/x")[0], 404)

    def test_end_to_end_publish_ingest_serve_verify(self):
        """publish -> ingest -> HTTP (Range capable) -> channel, manifest, every object and the 7z checked, as the launcher will."""
        self.publish("1.0.0", "stable")
        self.publish("1.1.0", "test", files={"global/excel/armor.txt": b"new\n"})
        with serve_dir.running(self.site) as base:
            n = pub.verify_url(base, "stable", log=lambda *_: None)
            self.assertGreaterEqual(n, 4)
            pub.verify_url(base, "test", log=lambda *_: None)
            pub.verify_url(base, "stable", sample=1, log=lambda *_: None)
            ch = json.loads(urllib.request.urlopen(base + "channels/stable.json").read())
            man = json.loads(urllib.request.urlopen(base + ch["manifest"]).read())
            seven = self.site / man["archive"]["path"]
            good = seven.read_bytes()
            seven.write_bytes(good[:-1] + bytes([good[-1] ^ 1]))  # same size, other bytes: only the hash notices
            with self.assertRaises(pub.PublishError):
                pub.verify_url(base, "stable", log=lambda *_: None)
            seven.write_bytes(good)
            obj = self.site / pub.object_path(man["files"][0]["sha256"])  # a corrupted object is caught
            obj.write_bytes(obj.read_bytes() + b"!")
            with self.assertRaises(pub.PublishError):
                pub.verify_url(base, "stable", log=lambda *_: None)

    @unittest.skipUnless(REAL_7Z, "package_release.py needs 7-Zip")
    def test_end_to_end_with_a_real_package_release_run(self):
        """package_release.py --no-data (what CI does) -> publish --allow-incomplete -> ingest -> serve -> verify."""
        out = self.tmp / "dist"
        r = subprocess.run([sys.executable, "-I", str(HERE / "package_release.py"), "--no-data", "--plugin", str(self.dll),
                            "--version", "0.0.1", "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        argv = ["publish", "--version", "0.0.1", "--channel", "test", "--dist", str(out), "--allow-incomplete",
                "--target", f"dir:{self.site}"]
        with mock.patch("builtins.print"):
            self.assertEqual(pub.main(argv), 0)
            self.assertEqual(pub.main(argv), 0, "second run: waiting for the server")
            self.assertEqual(dl_ingest.main(["--root", str(self.srv), "--7z", self.seven, *PRODUCT_ARGS]), 0)
            self.assertEqual(pub.main(argv), 0, "third run: published already")
            self.assertEqual(pub.main(["list", "--target", f"dir:{self.site}"]), 0)
            with serve_dir.running(self.site) as base:
                self.assertEqual(pub.main(["verify", "--url", base, "--channel", "test"]), 0)
            self.assertEqual(pub.main(["promote", "0.0.1", "--channel", "stable", "--target", f"dir:{self.site}"]), 1,
                             "incomplete -> not stable")
            self.assertEqual(pub.main(["gc", "--keep", "1", "--target", f"dir:{self.site}"]), 0)


if __name__ == "__main__":
    unittest.main()
