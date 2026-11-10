"""Traced, content-addressed cache for the walls build; no cached entry is mutable.

The recipe hash covers the transitive tools import closure, Python,
NumPy/Pillow versions and MXL switches. A recipe's manifests record actual file reads,
existence/type probes and directory listings, including absent fallback candidates.
Paths below the checkout are relative so independent lanes can share entries.
"""
import ast
import contextlib
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

VERSION = 1
ROOT = Path(__file__).absolute().parent.parent


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Trace:
    def __init__(self, root=ROOT):
        self.root = Path(root).absolute()
        self.inputs = {}
        self.writes = set()
        self.active = False
        self.busy = False
        self.stat = os.stat
        self.scandir = os.scandir

    def name(self, path):
        p = Path(os.path.abspath(path))
        try:
            return '@/' + p.relative_to(self.root).as_posix()
        except ValueError:
            return str(p)

    def path(self, name):
        return self.root / name[2:] if name.startswith('@/') else Path(name)

    def state(self, kind, path):
        if kind == 'read':
            try:
                return digest(path)
            except FileNotFoundError:
                return None
        if kind == 'list':
            try:
                with self.scandir(path) as entries:
                    return sorted((e.name, e.is_dir()) for e in entries)
            except FileNotFoundError:
                return None
        try:
            import stat
            follow = not (kind == 'lprobe' or kind.startswith('lstat.'))
            info = self.stat(path, follow_symlinks=follow)
            if kind.startswith(('stat.', 'lstat.')):
                field = kind.split('.', 1)[1]
                return list(info) if field == 'tuple' else getattr(info, field)
            return stat.S_IFMT(info.st_mode)
        except (FileNotFoundError, NotADirectoryError):
            return None

    def record(self, kind, path):
        if not self.active or self.busy or isinstance(path, int):
            return
        self.busy = True
        try:
            name = self.name(path)
            # Runtime imports are covered by versions; tools sources by the recipe.
            low = str(path).lower()
            if low.endswith(('.py', '.pyc', '.pyd', '.dll')):
                return
            if name in self.writes:
                return
            token = kind + ':' + name
            if token not in self.inputs:
                self.inputs[token] = self.state(kind, self.path(name))
        finally:
            self.busy = False

    def audit(self, event, args):
        if not self.active or self.busy:
            return
        if event == 'open':
            path, mode, flags = args
            if not isinstance(path, (str, bytes, os.PathLike)):
                return
            if (flags or 0) & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                if (flags or 0) & (os.O_RDWR | os.O_APPEND):
                    self.record('read', path)
                self.writes.add(self.name(path))
            else:
                self.record('read', path)
        elif event == 'os.mkdir':
            self.writes.add(self.name(args[0]))
        elif event in ('os.scandir', 'os.listdir'):
            self.record('list', args[0])
        elif event in ('subprocess.Popen', 'ctypes.dlopen'):
            # External/native reads cannot be observed by Python. Fail closed.
            raise RuntimeError('walls cache cannot trace external/native input: ' + event +
                               '; fill the D2R file cache first, or use MXL_NO_BUILD_CACHE=1')

    @contextlib.contextmanager
    def capture(self):
        trace = self

        class StatView:
            def __init__(self, path, info, prefix):
                self.path, self.info, self.prefix = path, info, prefix

            def __getattr__(self, field):
                if field.startswith('st_'):
                    trace.record(self.prefix + field, self.path)
                return getattr(self.info, field)

            def __getitem__(self, index):
                trace.record(self.prefix + 'tuple', self.path)
                return self.info[index]

            def __iter__(self):
                trace.record(self.prefix + 'tuple', self.path)
                return iter(self.info)

        def traced_stat(path, *args, **kwargs):
            if not trace.active or trace.busy:
                return trace.stat(path, *args, **kwargs)
            if kwargs.get('dir_fd') is not None:
                raise RuntimeError('relative directory-fd stat needs a cache dependency adapter')
            follow = kwargs.get('follow_symlinks', True)
            trace.record('probe' if follow else 'lprobe', path)
            info = trace.stat(path, *args, **kwargs)
            return StatView(path, info, 'stat.' if follow else 'lstat.')
        sys.addaudithook(self.audit)
        os.stat = traced_stat
        self.active = True
        try:
            yield self
        finally:
            self.active = False
            os.stat = self.stat

    def current(self, manifest):
        return {token: self.state(*[token.split(':', 1)[0], self.path(token.split(':', 1)[1])])
                for token in manifest}


def tools_sources(root):
    """Walk imports, including lazy/conditional ones, without executing the generator.

    This generator's closure uses ordinary imports. Refuse future dynamic imports
    rather than silently leave a dependency out of the recipe.
    """
    pending = ['walls_hd', 'walls_cache', 'localconfig']
    sources = {}
    while pending:
        name = pending.pop()
        path = root / 'tools' / (name + '.py')
        rel = path.relative_to(root).as_posix()
        if rel in sources or not path.is_file():
            continue
        sources[rel] = digest(path)
        for node in ast.walk(ast.parse(path.read_text('utf-8-sig'))):
            if isinstance(node, ast.Import):
                pending.extend(a.name.split('.')[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                pending.append(node.module.split('.')[0])
            elif isinstance(node, ast.Call):
                fn = node.func
                if (isinstance(fn, ast.Name) and fn.id == '__import__') or (
                        isinstance(fn, ast.Attribute) and fn.attr == 'import_module'):
                    raise RuntimeError('dynamic tools import requires an explicit cache dependency: ' + rel)
    return sources


def recipe(root=ROOT):
    versions = {p: importlib.metadata.version(p) for p in ('numpy', 'Pillow')}
    sources = tools_sources(root)
    env = {k: v for k, v in os.environ.items() if k.startswith('MXL') and k not in
           ('MXL_NO_BUILD_CACHE', 'MXL_BUILD_CACHE', 'MXL_VERIFY_BUILD_CACHE', 'MXL_BUILD_CACHE_PROBE', 'MXL_RUN', 'MXL_SLOT')}
    # Local paths are represented by traced files, not lane-specific path strings.
    for k in list(env):
        if Path(env[k]).is_absolute():
            env[k] = Trace(root).name(env[k])
    return {'version': VERSION, 'sources': sources, 'env': env, 'python': sys.version,
            'versions': versions}


def store(cache, cache_key, manifest, outputs):
    """Publish an entry only after all payload files and their checksums exist."""
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.tmp-', dir=cache))
    try:
        hashes = {}
        for name, src in outputs.items():
            dest = temp / 'files' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            hashes[name] = digest(dest)
        (temp / 'entry.json').write_text(json.dumps({'inputs': manifest, 'outputs': hashes}, sort_keys=True), 'utf-8')
        try:
            temp.rename(cache / cache_key)
        except FileExistsError:
            pass  # Another build published the same complete entry.
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def restore(entry, trace, verify=False):
    """Stage and validate the complete payload before touching any build file.

    A concurrent prune may remove an entry while it is copied. Staging keeps that
    failure from changing the inputs the subsequent cache miss will read.
    """
    meta = json.loads((entry / 'entry.json').read_text('utf-8'))
    scratch = trace.root / 'work' / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='walls-restore-', dir=scratch) as td:
        staged = Path(td)
        for name, expected in meta['outputs'].items():
            if not name.startswith('@/') or '..' in Path(name).parts:
                raise ValueError('invalid output path')
            dest = trace.path(name)
            if verify:
                if not dest.is_file() or digest(dest) != expected:
                    raise ValueError('generated output differs from cache: ' + name)
            else:
                copy = staged / name
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(entry / 'files' / name, copy)
                if digest(copy) != expected:
                    raise ValueError('cache payload checksum mismatch: ' + name)
        if not verify:
            for name in meta['outputs']:
                dest = trace.path(name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + '.' + str(os.getpid()) + '.cachetmp')
                try:
                    shutil.copyfile(staged / name, tmp)
                    os.replace(tmp, dest)
                except OSError as exc:
                    raise RuntimeError('wall cache restore could not replace ' + name) from exc
    return meta


def prune(cache, limit=8 * 1024**3):
    entries = []
    cache = Path(cache).resolve()
    for p in cache.glob('*/*'):
        is_key = lambda name: len(name) == 64 and all(c in '0123456789abcdef' for c in name)
        if not is_key(p.parent.name) or not is_key(p.name) or not p.is_dir():
            continue
        if not p.resolve().is_relative_to(cache) or not (p / 'entry.json').is_file():
            continue
        try:
            size = sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
            entries.append((p.stat().st_mtime, p, size))
        except OSError:
            pass  # A concurrent pruner already removed it.
    total = 0
    for _when, p, size in sorted(entries, reverse=True):
        total += size
        if total > limit:
            try:
                shutil.rmtree(p)
            except OSError:
                pass  # Concurrent reader/pruner; retry on the next publication.


def main():
    import localconfig
    localconfig.apply()
    import walls_hd
    # Third-party runtime initialization is identified by recipe versions.
    import numpy  # noqa: F401
    from PIL import Image  # noqa: F401
    if os.environ.get('MXL_NO_BUILD_CACHE') == '1' or len(sys.argv) < 2 or sys.argv[1] != 'build':
        return walls_hd.main()
    cache = Path(os.environ.get('MXL_BUILD_CACHE') or localconfig.runs_dir() / 'buildcache' / 'walls_hd')
    trace = Trace()
    r = recipe()
    r['args'] = [trace.name(a) if Path(a).is_absolute() else a for a in sys.argv[1:]]
    bucket = cache / key(r)
    bucket.mkdir(parents=True, exist_ok=True)
    found = None
    for entry in sorted(bucket.iterdir()):
        if entry.name.startswith('.') or not entry.is_dir():
            continue
        try:
            meta = json.loads((entry / 'entry.json').read_text('utf-8'))
            if entry.name != key({'recipe': r, 'inputs': meta['inputs']}):
                continue
            current = trace.current(meta['inputs'])
            if key(current) == key(meta['inputs']):
                if os.environ.get('MXL_BUILD_CACHE_PROBE') == '1' or os.environ.get('MXL_VERIFY_BUILD_CACHE') != '1':
                    if os.environ.get('MXL_BUILD_CACHE_PROBE') != '1':
                        restore(entry, trace)
                    print('walls_hd: cache hit ' + entry.name, flush=True)
                    return 0
                found = entry
                break
        except (OSError, ValueError, KeyError, TypeError):
            continue
    print('walls_hd: cache miss' if found is None else 'walls_hd: verifying ' + found.name, flush=True)
    if os.environ.get('MXL_BUILD_CACHE_PROBE') == '1':
        return 2  # Lookup only: no generation or product changes.
    # Import-time reads matter too. Re-execute the tools imports inside the trace.
    for name, module in list(sys.modules.items()):
        file = getattr(module, '__file__', None)
        if file and Path(file).absolute().parent == ROOT / 'tools' and name != '__main__':
            del sys.modules[name]
    with trace.capture():
        import walls_hd
        rc = walls_hd.main()
    if rc:
        return rc
    outputs = {name: trace.path(name) for name in trace.writes if name.startswith('@/') and trace.path(name).is_file()}
    # Runtime/import scratch files are never build products.
    outputs = {n: p for n, p in outputs.items() if '/__pycache__/' not in n and not n.endswith('.pyc')}
    if found:
        expected_outputs = json.loads((found / 'entry.json').read_text('utf-8'))['outputs']
        if set(outputs) != set(expected_outputs):
            raise ValueError('generated output file set differs from cache')
        restore(found, trace, verify=True)
        print('walls_hd: cache verified ' + found.name, flush=True)
    else:
        # Never publish a mixture if a source is edited during generation.
        changed = [token for token, value in trace.inputs.items()
                   if token.split(':', 1)[1] not in trace.writes
                   and trace.state(token.split(':', 1)[0], trace.path(token.split(':', 1)[1])) != value]
        if changed or recipe() != {k: v for k, v in r.items() if k != 'args'}:
            print('walls_hd: inputs changed during generation; result not cached', flush=True)
            return 0
        cache_key = key({'recipe': r, 'inputs': trace.inputs})
        store(bucket, cache_key, trace.inputs, outputs)
        print('walls_hd: cache stored ' + cache_key, flush=True)
        prune(cache)
    return 0


if __name__ == '__main__':
    sys.exit(main())
