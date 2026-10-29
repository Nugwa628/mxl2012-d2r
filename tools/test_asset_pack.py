"""asset_pack.py on small fake trees in a temp folder; the real assets/ and assets.lock are never touched."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import asset_pack  # noqa: E402


def make_tree(root: Path, extra: dict | None = None) -> Path:
    files = {"median/data/global/excel/a.bin": b"\x00\x01" * 1000, "median/2_txt/b.txt": b"hello\n",
             "hd/wereowl/c.npz": os.urandom(5000)}
    files.update(extra or {})
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


class PackCase(unittest.TestCase):
    fmt = "zip"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="asset_pack_test_"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.src = make_tree(self.tmp / "src")
        self.out = self.tmp / "out"
        self.lock = self.tmp / "assets.lock"
        self.assets = self.tmp / "assets"
        for k, v in (("LOCK", self.lock), ("ASSETS", self.assets), ("LOCAL_PACKS", self.tmp / "local-packs")):
            p = patch.object(asset_pack, k, v)
            p.start()
            self.addCleanup(p.stop)
        env = patch.dict(os.environ, {"MXL_ASSETS_CACHE": str(self.tmp / "cache")})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("MXL_ASSETS", None)
        os.environ.pop("MXL_SKIP_ASSET_CHECK", None)

    def run_main(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rc = asset_pack.main(list(argv))
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
                buf.write(str(e.code))
        return rc, buf.getvalue()

    def build_pack(self, version="7"):
        rc, text = self.run_main("build", "--version", version, "--format", self.fmt, "--src", str(self.src),
                                 "--out", str(self.out), "--write-lock", "--level", "1")
        self.assertEqual(rc, 0, text)
        return json.loads(self.lock.read_text())


class BuildFetchVerify(PackCase):
    def test_build_is_deterministic_and_lock_matches(self):
        lock = self.build_pack()
        pack = self.out / lock["file"]
        self.assertEqual(lock["sha256"], asset_pack.sha256_file(pack))
        self.assertEqual(lock["size"], pack.stat().st_size)
        self.assertEqual(lock["files"], 3)
        first = pack.read_bytes()
        self.build_pack()
        self.assertEqual(first, pack.read_bytes())

    def test_manifest_lists_every_file(self):
        lock = self.build_pack()
        mpath = self.out / "assets-7.manifest.json"
        m = json.loads(mpath.read_bytes())
        self.assertEqual([f["path"] for f in m["files"]], sorted(f["path"] for f in m["files"]))
        self.assertEqual({f["path"] for f in m["files"]}, set(asset_pack.list_tree(self.src)))
        f = next(f for f in m["files"] if f["path"] == "median/2_txt/b.txt")
        self.assertEqual((f["size"], f["sha256"]), (6, hashlib.sha256(b"hello\n").hexdigest()))
        self.assertEqual(hashlib.sha256(mpath.read_bytes()).hexdigest(), lock["manifest_sha256"])

    def test_fetch_from_pack_file_folder_and_verify(self):
        lock = self.build_pack()
        pack = self.out / lock["file"]
        for src in (str(pack), str(self.out)):
            with self.subTest(src=src):
                if self.assets.exists():
                    asset_pack.remove_tree(self.assets)
                rc, text = self.run_main("fetch", "--from", src)
                self.assertEqual(rc, 0, text)
                self.assertEqual((self.assets / "median/2_txt/b.txt").read_bytes(), b"hello\n")
                self.assertEqual(self.run_main("verify")[0], 0)
                self.assertTrue(asset_pack.assets_ok()[0])
        rc, text = self.run_main("fetch", "--from", str(pack))
        self.assertIn("already the pinned pack", text)

    def test_env_override_and_unpacked_tree_link(self):
        lock = self.build_pack()
        tree = self.tmp / "cache-tree"
        self.assertEqual(self.run_main("fetch", "--from", str(self.out / lock["file"]), "--dest", str(tree))[0], 0)
        with patch.dict(os.environ, {"MXL_ASSETS": str(tree)}):
            rc, text = self.run_main("fetch", "--link")
        self.assertEqual(rc, 0, text)
        self.assertTrue(asset_pack.is_link(self.assets))
        self.assertTrue(asset_pack.assets_ok()[0])
        asset_pack.remove_tree(self.assets)
        self.assertTrue((tree / "median/2_txt/b.txt").exists(), "removing the link must leave the tree")

    def test_wrong_pack_is_refused(self):
        lock = self.build_pack()
        bad = self.tmp / "bad.pack"
        data = bytearray((self.out / lock["file"]).read_bytes())
        data[len(data) // 2] ^= 0xFF
        bad.write_bytes(bytes(data))
        rc, text = self.run_main("fetch", "--from", str(bad))
        self.assertEqual(rc, 1, text)
        self.assertFalse(self.assets.exists())
        self.assertEqual(self.run_main("check-pack", str(bad))[0], 1)
        self.assertEqual(self.run_main("check-pack", str(self.out))[0], 0)

    def test_missing_source_is_an_error_not_a_download(self):
        self.build_pack()
        rc, text = self.run_main("fetch", "--from", str(self.tmp / "nowhere"))
        self.assertEqual(rc, 2, text)
        self.assertFalse(self.assets.exists())

    def test_fetch_from_the_build_pcs_pack_folder(self):
        lock = self.build_pack()
        local = self.tmp / "local-packs"
        local.mkdir()
        shutil.copy(self.out / lock["file"], local)
        rc, text = self.run_main("fetch")
        self.assertEqual(rc, 0, text)
        self.assertIn("build PC's pack folder", text)
        self.assertTrue(asset_pack.assets_ok()[0])

    def test_forge_token_goes_to_the_forge_only(self):
        lock = self.build_pack()
        data = (self.out / lock["file"]).read_bytes()
        seen = {}

        class Resp(io.BytesIO):
            headers = {"Content-Length": str(len(data))}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                self.close()

        def fake_urlopen(req, timeout=None):
            seen[req.full_url] = req.get_header("Authorization")
            return Resp(data)

        forge = asset_pack.FORGE_RELEASES + f"assets-7/{lock['file']}"
        with patch.object(asset_pack.urllib.request, "urlopen", fake_urlopen), \
                patch.dict(os.environ, {"MXL_ASSETS_TOKEN": "t0k"}), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(asset_pack.download(forge, self.tmp / "dl" / "a.zip", lock))
            self.assertTrue(asset_pack.download("https://example.org/a.zip", self.tmp / "dl" / "b.zip", lock))
        self.assertEqual(seen, {forge: "token t0k", "https://example.org/a.zip": None})
        self.assertTrue(lock["urls"][0].startswith(asset_pack.FORGE_RELEASES))

    def test_verify_changed_missing_extra(self):
        lock = self.build_pack()
        self.run_main("fetch", "--from", str(self.out / lock["file"]))
        (self.assets / "new.txt").write_text("x")
        self.assertEqual(self.run_main("verify", "--full")[0], 0)           # extra files are fine
        self.assertEqual(self.run_main("verify", "--strict")[0], 1)
        (self.assets / "new.txt").unlink()
        (self.assets / "median/2_txt/b.txt").write_bytes(b"HELLO\n")        # same size, other bytes
        rc, text = self.run_main("verify", "--full")
        self.assertEqual(rc, 1, text)
        self.assertIn("changed", text)
        (self.assets / "median/2_txt/b.txt").unlink()
        rc, text = self.run_main("verify")
        self.assertEqual(rc, 1, text)
        self.assertIn("missing", text)

    def test_same_size_edit_with_old_mtime_is_caught_right_after_fetch(self):
        lock = self.build_pack()
        self.run_main("fetch", "--from", str(self.out / lock["file"]))
        f = self.assets / "median/2_txt/b.txt"
        st = f.stat()
        f.write_bytes(b"HELLO\n")
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns))         # same size, same mtime
        self.assertEqual(self.run_main("verify")[0], 1)
        self.assertFalse(asset_pack.assets_ok()[0])

    def test_existing_assets_need_force(self):
        lock = self.build_pack()
        make_tree(self.assets, {"median/other.txt": b"mine"})
        pack = str(self.out / lock["file"])
        rc, text = self.run_main("fetch", "--from", pack)
        self.assertEqual(rc, 1, text)
        self.assertTrue((self.assets / "median/other.txt").exists())
        self.assertEqual(self.run_main("fetch", "--from", pack, "--force")[0], 0)
        self.assertFalse((self.assets / "median/other.txt").exists())

    def test_adopt_only_the_pinned_tree(self):
        self.build_pack()
        shutil.copytree(self.src, self.assets)
        self.assertFalse(asset_pack.assets_ok()[0])                          # no manifest yet
        self.assertEqual(self.run_main("adopt")[0], 0)
        self.assertTrue(asset_pack.assets_ok()[0])
        (self.assets / "median/2_txt/b.txt").write_bytes(b"changed")
        (self.assets / asset_pack.MANIFEST).unlink()
        self.assertEqual(self.run_main("adopt")[0], 1)

    def test_private_details_in_text_files_stop_the_build(self):
        # Plant what the generic rules of check_public flag (user-home path, internal host, address). The machine names of the
        # private-terms file are not used: that file exists only on the owner's PC, never on the CI runner.
        make_tree(self.src, {"median/notes.txt": b"made in C:" + b"\\Users\\jdoe\\work, served by box7." + b"lan at 192.168." + b"1.20\n",
                             "median/list.txt": b"c" + b"@a2hth.cof\n"})   # a file name with an @ is Median data, not an address
        rc, text = self.run_main("build", "--version", "8", "--src", str(self.src), "--out", str(self.out), "--format", self.fmt)
        self.assertEqual(rc, 1, text)
        self.assertIn("notes.txt", text)
        for rule in ("home-path", "host", "ip"):
            self.assertIn(f"[{rule}]", text)
        self.assertNotIn("a2hth", text)
        self.assertEqual(self.run_main("scan", "--dir", str(self.src))[0], 1)

    def test_lfs_pointer_is_not_packed(self):
        make_tree(self.src, {"median/p.dcc": b"version https://git-lfs.github.com/spec/v1\noid sha256:00\nsize 1\n"})
        rc, text = self.run_main("build", "--version", "8", "--src", str(self.src), "--out", str(self.out), "--format", self.fmt)
        self.assertEqual(rc, 1, text)
        self.assertIn("LFS pointer", text)
        self.assertEqual(list(self.out.glob("assets-8*")), [])


class BuildFetchVerifyXz(BuildFetchVerify):
    fmt = "tar.xz"


class ZipSlip(PackCase):
    def test_entry_outside_destination_is_refused(self):
        lock = self.build_pack()
        evil = self.tmp / "evil.zip"
        with zipfile.ZipFile(self.out / lock["file"]) as zf, zipfile.ZipFile(evil, "w") as out:
            for zi in zf.infolist():
                out.writestr(zi, zf.read(zi))
            out.writestr("../escape.txt", b"x")
        lock["size"], lock["sha256"] = evil.stat().st_size, asset_pack.sha256_file(evil)
        self.lock.write_text(json.dumps(lock))
        rc, text = self.run_main("fetch", "--from", str(evil))
        self.assertNotEqual(rc, 0, text)
        self.assertFalse((self.tmp / "escape.txt").exists())


class BuildPyGate(PackCase):
    def setUp(self):
        super().setUp()
        import build
        self.build = build

    def test_build_stops_without_assets(self):
        self.build_pack()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.build.ensure_assets(False), 2)
        self.assertIn("asset_pack.py fetch", out.getvalue())
        self.assertFalse(self.assets.exists())

    def test_build_fetches_a_missing_assets_from_a_local_source(self):
        lock = self.build_pack()
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(os.environ, {"MXL_ASSETS": str(self.out / lock["file"])}):
            self.assertEqual(self.build.ensure_assets(False), 0)
        self.assertTrue(asset_pack.assets_ok()[0])

    def test_build_links_assets_to_the_build_pcs_unpacked_tree(self):
        lock = self.build_pack()
        tree = self.tmp / "local-packs" / lock["version"] / "assets"
        self.assertEqual(self.run_main("fetch", "--from", str(self.out / lock["file"]), "--dest", str(tree))[0], 0)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.build.ensure_assets(False), 0)
        self.assertTrue(asset_pack.is_link(self.assets))
        asset_pack.remove_tree(self.assets)

    def test_build_does_not_replace_modified_assets(self):
        lock = self.build_pack()
        self.run_main("fetch", "--from", str(self.out / lock["file"]))
        (self.assets / "median/2_txt/b.txt").write_bytes(b"edited")
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(os.environ, {"MXL_ASSETS": str(self.out / lock["file"])}):
            self.assertEqual(self.build.ensure_assets(False), 2)
            self.assertEqual((self.assets / "median/2_txt/b.txt").read_bytes(), b"edited")
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(os.environ, {"MXL_SKIP_ASSET_CHECK": "1"}):
            self.assertEqual(self.build.ensure_assets(False), 0)


if __name__ == "__main__":
    unittest.main()
