"""Base game files read from the game's CASC storage on demand, through a capped, least-recently-used local cache.

A CascRoot is a root of vfs.Layered like a folder: `find(logical)` returns a file on disk or None. It looks in order at
  1. seed folders (read-only copies made earlier, e.g. a research extract; never written, never evicted, not counted),
  2. the cache folder <cache>/<build>/ (files this root fetched before),
  3. the CASC storage of a game folder, opened read-only on the first miss; the file is written into the cache.
The cache holds at most `cap_bytes` (oldest use evicted first, down to 90 % of the cap) and keeps an index
(<cache>/<build>/index.json: logical path -> size, last use). The build key comes from the game folder (`build_of`), so
two game builds never share cached bytes.

Reading the storage. CascLib opens the storage's files read-only but WITHOUT write sharing (FileStream.cpp: share mode
FILE_SHARE_READ only), so a game or launcher that opened a data file for writing would fail while we hold it. A CascRoot
therefore reads only while `lock_free()` says no run holds the game folder (the site's slot lock), waits up to
`wait_s` for it otherwise, and closes the storage whenever it finds the lock held. A missing file is remembered as
missing for the life of the object.

Nothing here knows a game folder, a lock or a library path: `opener(game_dir) -> storage` (with `.read(name) -> bytes`
raising FileNotFoundError, and `.close()`), `lock_free()` and `build_of(game_dir)` come from the caller (the repository's
site adapter wires CascLib, the slot locks and the default places; see `from_site`).
"""
import json
import os
import time
from pathlib import Path

from .vfs import Layered, normalise

DEFAULT_CAP_GB = 4.0


def build_of_folder(game_dir) -> str:
    """The build number from a Battle.net install's `.build.info` (column Version, e.g. 1.6.93847 -> '93847')."""
    try:
        lines = Path(game_dir, ".build.info").read_text(encoding="utf-8", errors="replace").splitlines()
        head = [h.split("!")[0] for h in lines[0].split("|")]
        i = head.index("Version")
        for ln in lines[1:]:
            cols = ln.split("|")
            if len(cols) > i and cols[i]:
                return cols[i].rsplit(".", 1)[-1]
    except (OSError, ValueError, IndexError):
        pass
    return "unknown"


class CascRoot:
    def __init__(self, game_dir, cache_dir, cap_bytes: int = int(DEFAULT_CAP_GB * (1 << 30)), seeds=(), opener=None,
                 lock_free=None, build_of=build_of_folder, wait_s: float = 600.0, poll_s: float = 5.0, log=None):
        self.game_dir = str(game_dir) if game_dir else None
        self.build = build_of(game_dir) if game_dir else "unknown"
        self.dir = Path(cache_dir) / self.build
        self.cap = int(cap_bytes)
        self.seeds = Layered([("seed%d" % i, Path(s)) for i, s in enumerate(seeds) if s])
        self.opener, self.lock_free = opener, lock_free or (lambda: True)
        self.wait_s, self.poll_s, self.log = wait_s, poll_s, log or (lambda *_: None)
        self.storage = None
        self.missing: set = set()
        self.stats = {"seed": 0, "cache": 0, "casc": 0, "missing": 0, "evicted": 0, "waited_s": 0.0}
        self._index = None
        self._dirty = 0

    # ---- index ---------------------------------------------------------------------------------------------------------------
    @property
    def index(self) -> dict:
        if self._index is None:
            p = self.dir / "index.json"
            try:
                self._index = json.loads(p.read_text(encoding="utf-8"))["files"]
            except (OSError, ValueError, KeyError):
                self._index = {}
                if self.dir.is_dir():            # rebuild from what is on disk
                    for f in self.dir.rglob("*"):
                        if f.is_file() and f.name != "index.json" and not f.name.endswith(".part"):
                            self._index[f.relative_to(self.dir).as_posix().lower()] = {"size": f.stat().st_size,
                                                                                       "last": f.stat().st_mtime}
        return self._index

    def flush(self):
        if self._index is None or not self._dirty:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / "index.json.part"
        tmp.write_text(json.dumps({"build": self.build, "game": self.game_dir, "cap_bytes": self.cap,
                                   "files": self._index}, indent=0), encoding="utf-8")
        os.replace(tmp, self.dir / "index.json")
        self._dirty = 0

    def used_bytes(self) -> int:
        return sum(int(v["size"]) for v in self.index.values())

    def _touch(self, logical):
        e = self.index.get(logical)
        if e is not None:
            e["last"] = time.time()
            self._dirty += 1
            if self._dirty >= 200:
                self.flush()

    def evict(self, need: int = 0) -> int:
        """Drop the least recently used files until used + need <= 90 % of the cap. -> bytes freed."""
        used = self.used_bytes()
        if used + need <= self.cap:
            return 0
        target = int(self.cap * 0.9) - need
        freed = 0
        for logical, e in sorted(self.index.items(), key=lambda kv: kv[1]["last"]):
            if used - freed <= target:
                break
            try:
                (self.dir / logical).unlink()
            except OSError:
                pass
            freed += int(e["size"])
            del self.index[logical]
            self.stats["evicted"] += 1
        self._dirty += 1
        self.flush()
        return freed

    # ---- storage -------------------------------------------------------------------------------------------------------------
    def close(self):
        if self.storage is not None:
            try:
                self.storage.close()
            finally:
                self.storage = None
        self.flush()

    def _wait_lock(self):
        t0 = time.time()
        while not self.lock_free():
            if self.storage is not None:
                self.log("casc: the game folder is in use by a run; storage closed")
                self.close()
            if time.time() - t0 > self.wait_s:
                raise TimeoutError("casc: the game folder %s stayed locked for %.0f s" % (self.game_dir, self.wait_s))
            time.sleep(self.poll_s)
        self.stats["waited_s"] += round(time.time() - t0, 1)

    def _read_casc(self, logical) -> bytes | None:
        if self.opener is None or not self.game_dir:
            return None
        self._wait_lock()
        if self.storage is None:
            self.log("casc: opening %s (read-only)" % self.game_dir)
            self.storage = self.opener(self.game_dir)
        try:
            data = self.storage.read("data:data/" + logical)
        except FileNotFoundError:
            return None
        # CascLib answers a name it does not hold with no bytes rather than an error; no game file we read is empty.
        return data or None

    # ---- the root interface ----------------------------------------------------------------------------------------------------
    def find(self, path) -> Path | None:
        logical = normalise(path)
        hit = self.seeds.resolve(logical)
        if hit is not None:
            self.stats["seed"] += 1
            return hit.path
        p = self.dir / logical
        if logical in self.index and p.is_file():
            self.stats["cache"] += 1
            self._touch(logical)
            return p
        if logical in self.missing:
            return None
        data = self._read_casc(logical)
        if data is None:
            self.missing.add(logical)
            self.stats["missing"] += 1
            return None
        if len(data) > self.cap:
            raise ValueError("casc: %s (%d bytes) is larger than the cache cap" % (logical, len(data)))
        self.evict(len(data))
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        self.index[logical] = {"size": len(data), "last": time.time()}
        self._dirty += 1
        self.stats["casc"] += 1
        return p

    def walk(self, prefix: str = "", suffix: str = "") -> list:
        """(logical, path) of the files under `prefix` that are already local (seeds and cache); CASC is not listed."""
        out = {h.logical: h.path for h in self.seeds.walk(prefix, suffix)}
        pre, suf = normalise(prefix).rstrip("/"), suffix.lower()
        for logical in self.index:
            if logical.startswith(pre) and logical.endswith(suf) and logical not in out:
                out[logical] = self.dir / logical
        return sorted(out.items())

    def describe(self) -> dict:
        return {"game": self.game_dir, "build": self.build, "cache": str(self.dir), "cap_bytes": self.cap,
                "used_bytes": self.used_bytes(), "files": len(self.index),
                "seeds": [str(r) for _n, r in self.seeds.roots], "stats": dict(self.stats)}


def from_site(game_dir=None, log=None) -> CascRoot:
    """A CascRoot with this repository's defaults (tools/hdkit_site.py): game folder, cache place and cap, seeds, CascLib,
    the slot lock of that folder. Environment: HDKIT_CASC_GAME, HDKIT_CASC_CACHE, HDKIT_CASC_CACHE_GB."""
    import hdkit_site as site
    g = game_dir or site.casc_game_dir()
    gb = float(os.environ.get("HDKIT_CASC_CACHE_GB") or site.casc_cache_gb())
    return CascRoot(g, os.environ.get("HDKIT_CASC_CACHE") or site.casc_cache_dir(), int(gb * (1 << 30)),
                    site.casc_seeds(), site.casc_opener, (lambda: site.game_dir_free(g)), log=log)
