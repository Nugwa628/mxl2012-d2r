"""hdkit.view.casc: the on-demand CASC root with its capped LRU cache. A fake storage stands in for CascLib, so no game
folder is needed: seed precedence, cache hits, missing names (including CascLib's empty answer), LRU eviction, the
index rebuild, the lock wait that closes the storage, and the vfs wiring."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.view import casc, vfs  # noqa: E402


class FakeStorage:
    def __init__(self, files, log):
        self.files, self.log, self.closed = files, log, False

    def read(self, name):
        self.log.append(name)
        if name not in self.files:
            raise FileNotFoundError(name)
        return self.files[name]

    def close(self):
        self.closed = True


class CascRootTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.cache, self.seed = base / "cache", base / "seed"
        (self.seed / "hd" / "env").mkdir(parents=True)
        (self.seed / "hd" / "env" / "seeded.json").write_bytes(b"seed")
        self.files = {"data:data/hd/a.json": b"A" * 100, "data:data/hd/b.json": b"B" * 100,
                      "data:data/hd/c.json": b"C" * 100, "data:data/hd/env/seeded.json": b"casc",
                      "data:data/hd/empty.json": b""}
        self.reads, self.opened = [], []

    def tearDown(self):
        self.tmp.cleanup()

    def root(self, cap=250, lock_free=None, **kw):
        def opener(game):
            s = FakeStorage(self.files, self.reads)
            self.opened.append(s)
            return s
        return casc.CascRoot("G", self.cache, cap, [self.seed], opener, lock_free, build_of=lambda g: "b1", **kw)

    def test_seed_first_then_casc_then_cache(self):
        r = self.root()
        self.assertEqual(r.find("Hd/Env/Seeded.json").read_bytes(), b"seed")
        p = r.find("hd/a.json")
        self.assertEqual(p, self.cache / "b1" / "hd" / "a.json")
        self.assertEqual(p.read_bytes(), b"A" * 100)
        self.assertEqual(r.find("hd/a.json"), p)
        self.assertEqual(self.reads, ["data:data/hd/a.json"])
        self.assertEqual((r.stats["seed"], r.stats["casc"], r.stats["cache"]), (1, 1, 1))

    def test_missing_and_empty_are_not_cached(self):
        r = self.root()
        self.assertIsNone(r.find("hd/nope.json"))
        self.assertIsNone(r.find("hd/empty.json"))
        self.assertIsNone(r.find("hd/nope.json"))           # remembered: no second read
        self.assertEqual(len(self.reads), 2)
        self.assertFalse((self.cache / "b1" / "hd" / "empty.json").exists())
        self.assertEqual(r.index, {})

    def test_lru_eviction_and_index(self):
        r = self.root(cap=250)
        r.find("hd/a.json")
        r.find("hd/b.json")
        r.index["hd/a.json"]["last"] = 1.0                  # a is the oldest use
        r.find("hd/c.json")                                 # 300 > 250: evict down to 225 - 100
        self.assertNotIn("hd/a.json", r.index)
        self.assertFalse((self.cache / "b1" / "hd" / "a.json").exists())
        self.assertEqual(sorted(r.index), ["hd/b.json", "hd/c.json"])
        self.assertLessEqual(r.used_bytes(), 250)
        r.close()
        saved = json.loads((self.cache / "b1" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(saved["files"]), ["hd/b.json", "hd/c.json"])
        self.assertTrue(self.opened[0].closed)

    def test_index_rebuilt_from_disk(self):
        r = self.root()
        r.find("hd/a.json")
        r.close()
        (self.cache / "b1" / "index.json").unlink()
        r2 = self.root()
        self.assertEqual(list(r2.index), ["hd/a.json"])
        self.assertEqual(r2.find("hd/a.json").read_bytes(), b"A" * 100)
        self.assertEqual(len(self.reads), 1)

    def test_larger_than_cap(self):
        self.files["data:data/hd/big.bin"] = b"x" * 1000
        with self.assertRaises(ValueError):
            self.root(cap=500).find("hd/big.bin")

    def test_lock_wait_closes_storage(self):
        state = {"free": True, "polls": 0}

        def lock_free():
            if not state["free"]:
                state["polls"] += 1
                if state["polls"] >= 2:
                    state["free"] = True
                return False
            return True
        r = self.root(lock_free=lock_free, poll_s=0.0)
        r.find("hd/a.json")
        state["free"] = False
        r.find("hd/b.json")
        self.assertTrue(self.opened[0].closed)              # closed while the run held the folder
        self.assertEqual(len(self.opened), 2)               # reopened afterwards

    def test_lock_timeout(self):
        r = self.root(lock_free=lambda: False, wait_s=0.0, poll_s=0.0)
        with self.assertRaises(TimeoutError):
            r.find("hd/a.json")
        self.assertEqual(self.opened, [])

    def test_vfs_layers_folder_before_casc(self):
        mod = Path(self.tmp.name) / "mod"
        (mod / "hd").mkdir(parents=True)
        (mod / "hd" / "a.json").write_bytes(b"mod")
        r = self.root()
        L = vfs.Layered([("mod", mod), ("casc", r)])
        self.assertEqual(L.resolve("hd/a.json").path.read_bytes(), b"mod")
        self.assertEqual(L.resolve("hd/b.json").path.read_bytes(), b"B" * 100)
        self.assertIsNone(L.resolve("hd/nope.json"))
        self.assertIn("hd/env/seeded.json", [lg for lg, _p in r.walk("hd/env")])

    def test_build_of_folder(self):
        g = Path(self.tmp.name) / "game"
        g.mkdir()
        (g / ".build.info").write_text("Branch!STRING:0|Active!DEC:1|Version!STRING:0\nus|1|1.6.93847\n",
                                       encoding="utf-8")
        self.assertEqual(casc.build_of_folder(g), "93847")
        self.assertEqual(casc.build_of_folder(Path(self.tmp.name) / "none"), "unknown")


if __name__ == "__main__":
    unittest.main()
