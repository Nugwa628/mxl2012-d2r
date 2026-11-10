import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: F401
import walls_cache as c


class CacheTests(unittest.TestCase):
    def test_traced_content_and_absence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / 'input.bin'
            f.write_bytes(b'a')
            t = c.Trace(root)
            with t.capture():
                f.read_bytes()
                (root / 'optional').exists()
                list(root.iterdir())
            baseline = c.key(t.inputs)
            self.assertEqual(baseline, c.key(t.current(t.inputs)))
            f.write_bytes(b'b')
            self.assertNotEqual(baseline, c.key(t.current(t.inputs)))
            f.write_bytes(b'a')
            (root / 'optional').write_bytes(b'new')
            self.assertNotEqual(baseline, c.key(t.current(t.inputs)))

    def test_size_gate_for_unread_input(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); f = root / 'table.bin'; f.write_bytes(b'')
            t = c.Trace(root)
            with t.capture():
                if f.exists() and f.stat().st_size >= 4:
                    f.read_bytes()
            self.assertNotIn('read:@/table.bin', t.inputs)
            before = c.key(t.inputs)
            f.write_bytes(b'1234')
            self.assertNotEqual(before, c.key(t.current(t.inputs)))

    def test_exists_ignores_unread_content_and_size(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); f = root / 'skills.txt'; f.write_bytes(b'a')
            t = c.Trace(root)
            with t.capture():
                self.assertTrue(f.exists())
            before = c.key(t.inputs)
            f.write_bytes(b'unrelated skill data, still present')
            self.assertEqual(before, c.key(t.current(t.inputs)))

    def test_unrelated_not_read(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); f = root / 'input'; f.write_bytes(b'a')
            t = c.Trace(root)
            with t.capture():
                f.read_bytes()
            (root / 'unrelated').write_bytes(b'anything')
            self.assertEqual(c.key(t.inputs), c.key(t.current(t.inputs)))

    def test_prior_input_and_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); f = root / 'combined'; f.write_bytes(b'before')
            t = c.Trace(root)
            with t.capture():
                f.read_bytes()
                f.write_bytes(b'after')
                f.read_bytes()
            self.assertEqual(t.inputs['read:@/combined'], __import__('hashlib').sha256(b'before').hexdigest())
            self.assertIn('@/combined', t.writes)

    def test_atomic_store_restore_and_corruption(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / 'product'; src.write_bytes(b'result')
            cache = root / 'cache'; trace = c.Trace(root)
            c.store(cache, 'key', {}, {'@/product': src})
            c.store(cache, 'key', {}, {'@/product': src})
            self.assertEqual([p.name for p in cache.iterdir()], ['key'])
            src.unlink()
            c.restore(cache / 'key', trace)
            self.assertEqual(src.read_bytes(), b'result')
            (cache / 'key' / 'files' / '@' / 'product').write_bytes(b'corrupt')
            src.write_bytes(b'untouched')
            with self.assertRaises(ValueError):
                c.restore(cache / 'key', trace)
            self.assertEqual(src.read_bytes(), b'untouched')

    def test_recipe_source_switch_and_unrelated(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root / 'tools').mkdir()
            src = root / 'tools' / 'walls_hd.py'; src.write_text('VERSION = 1')
            before = c.key(c.recipe(root))
            (root / 'notes.md').write_text('unrelated')
            (root / 'tools' / 'unrelated.py').write_text('UNRELATED = 1')
            self.assertEqual(before, c.key(c.recipe(root)))
            src.write_text('VERSION = 2')
            self.assertNotEqual(before, c.key(c.recipe(root)))
            before = c.key(c.recipe(root))
            with patch.dict(c.os.environ, {'MXL2012_BELIAL_TERRAIN': 'changed'}):
                self.assertNotEqual(before, c.key(c.recipe(root)))
            with patch.dict(c.os.environ, {'MXL_CONTROL': 'walls'}):
                self.assertNotEqual(before, c.key(c.recipe(root)))

    def test_transitive_conditional_import_closure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); tools = root / 'tools'; tools.mkdir()
            (tools / 'walls_hd.py').write_text('if False: import helper')
            (tools / 'helper.py').write_text('from leaf import VERSION')
            leaf = tools / 'leaf.py'; leaf.write_text('VERSION = 1')
            before = c.key(c.tools_sources(root))
            self.assertEqual(len(c.tools_sources(root)), 3)
            leaf.write_text('VERSION = 2')
            self.assertNotEqual(before, c.key(c.tools_sources(root)))
            (tools / 'helper.py').write_text("__import__('dynamic')")
            with self.assertRaises(RuntimeError):
                c.tools_sources(root)

    def test_concurrent_publication(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); src = root / 'source'; src.write_bytes(b'complete')
            cache = root / 'cache'
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = [pool.submit(c.store, cache, 'key', {}, {'@/dest': src}) for _ in range(8)]
                for f in futures:
                    f.result()
            c.restore(cache / 'key', c.Trace(root))
            self.assertEqual((root / 'dest').read_bytes(), b'complete')
            self.assertEqual([p.name for p in cache.iterdir()], ['key'])

    def test_end_to_end_cross_checkout_and_input_miss(self):
        import os
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            env = dict(os.environ, MXL_BUILD_CACHE=str(base / 'shared-cache'))
            env.pop('MXL_NO_BUILD_CACHE', None)
            env.pop('MXL_VERIFY_BUILD_CACHE', None)
            env.pop('MXL_BUILD_CACHE_PROBE', None)
            lanes = []
            for lane in ('one', 'two'):
                root = base / lane; (root / 'tools').mkdir(parents=True)
                shutil.copyfile(c.__file__, root / 'tools' / 'walls_cache.py')
                (root / 'tools' / 'localconfig.py').write_text(
                    "from pathlib import Path\ndef apply(): pass\ndef runs_dir(): return Path('.')\n")
                (root / 'tools' / 'walls_hd.py').write_text(
                    "from pathlib import Path\nimport sys\n"
                    "def main():\n"
                    "    src = Path('source.bin')\n"
                    "    optional = Path('optional').exists()\n"
                    "    data = src.read_bytes() + str(optional).encode()\n"
                    "    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)\n"
                    "    (out / 'product').write_bytes(data)\n"
                    "    return 0\n")
                (root / 'source.bin').write_bytes(b'input')
                lanes.append(root)
            def run(root, expected=0):
                result = subprocess.run([sys.executable, str(root / 'tools' / 'walls_cache.py'),
                    'build', str(root / 'out')], cwd=root, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                return result.stdout
            self.assertIn('cache miss', run(lanes[0]))
            self.assertIn('cache hit', run(lanes[1]))
            self.assertEqual((lanes[0] / 'out' / 'product').read_bytes(),
                             (lanes[1] / 'out' / 'product').read_bytes())
            (lanes[1] / 'source.bin').write_bytes(b'changed')
            env['MXL_BUILD_CACHE_PROBE'] = '1'
            self.assertIn('cache miss', run(lanes[1], expected=2))
            self.assertEqual((lanes[1] / 'out' / 'product').read_bytes(), b'inputFalse')
            env.pop('MXL_BUILD_CACHE_PROBE')
            self.assertIn('cache miss', run(lanes[1]))
            self.assertEqual((lanes[1] / 'out' / 'product').read_bytes(), b'changedFalse')
            env['MXL_VERIFY_BUILD_CACHE'] = '1'
            env['MXL_BUILD_CACHE_PROBE'] = '1'
            self.assertIn('cache hit', run(lanes[1]))
            env.pop('MXL_BUILD_CACHE_PROBE')
            self.assertIn('cache verified', run(lanes[1]))
            env['MXL_NO_BUILD_CACHE'] = '1'
            self.assertNotIn('cache ', run(lanes[1]))

    def test_prune_only_recognized_entries(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); cache = root / 'cache'; src = root / 'source'
            src.write_bytes(b'payload')
            unrelated = cache / 'other' / 'valuable'
            unrelated.mkdir(parents=True)
            (unrelated / 'keep').write_bytes(b'keep')
            c.store(cache / ('a' * 64), 'b' * 64, {}, {'@/product': src})
            c.prune(cache, limit=0)
            self.assertFalse((cache / ('a' * 64) / ('b' * 64)).exists())
            self.assertEqual((unrelated / 'keep').read_bytes(), b'keep')

    def test_failed_store_does_not_publish(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); cache = root / 'cache'
            with self.assertRaises(FileNotFoundError):
                c.store(cache, 'key', {}, {'@/missing': root / 'missing'})
            self.assertEqual(list(cache.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
