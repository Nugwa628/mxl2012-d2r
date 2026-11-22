"""A logical game path resolved over local roots, first root wins, with the root that answered.

D2R names its files by logical paths such as `data/hd/character/enemy/mummy1/skeleton/mummy1.skeleton` (unit JSONs, models
and particles name each other that way). A mod's build output is one root, files already extracted from the game another;
the first root that holds the path answers, as the game itself takes a mod's file before its own. Nothing here opens CASC:
roots are plain folders.

A root is a folder that holds the path's tail after `data/` (a `data` folder or an overlay with `hd/...` directly inside),
given as (name, folder). Lookups ignore case and slash direction (the game's paths are case-insensitive on Windows).
A root may also be an object with `find(logical) -> Path | None` (and optionally `walk(prefix, suffix) -> [(logical,
path)]`), e.g. casc.CascRoot, which fetches base files from the game's CASC into a capped cache on first use. The usual
order is the mod's build output first, then CASC: `--root mod=work/mod/data --root casc`.
"""
import os
from dataclasses import dataclass
from pathlib import Path


def normalise(path: str) -> str:
    """'Data\\HD\\x.json' -> 'hd/x.json': forward slashes, lower case, no leading 'data/' or './'."""
    p = str(path).replace("\\", "/").strip().lstrip("/")
    while p.startswith("./"):
        p = p[2:]
    low = p.lower()
    if low.startswith("data/"):
        low = low[5:]
    return low


@dataclass(frozen=True)
class Hit:
    logical: str     # normalised logical path
    root: str        # name of the root that answered
    path: Path       # the file on disk


class Layered:
    """Roots in order; `resolve` returns the first hit and remembers it in `log` (provenance of every file used)."""

    def __init__(self, roots):
        self.roots = [(str(n), p if hasattr(p, "find") else Path(p)) for n, p in roots]
        self.log: dict[str, Hit] = {}
        self._dirs: dict[Path, dict[str, str]] = {}

    def _listing(self, d: Path) -> dict:
        if d not in self._dirs:
            try:
                self._dirs[d] = {e.lower(): e for e in os.listdir(d)}
            except OSError:
                self._dirs[d] = {}
        return self._dirs[d]

    def _find(self, root, logical: str) -> Path | None:
        if hasattr(root, "find"):
            return root.find(logical)
        cur = root
        for part in logical.split("/"):
            real = self._listing(cur).get(part)
            if real is None:
                return None
            cur = cur / real
        return cur if cur.is_file() else None

    def resolve(self, path: str) -> Hit | None:
        logical = normalise(path)
        if logical in self.log:
            return self.log[logical]
        for name, root in self.roots:
            p = self._find(root, logical)
            if p is not None:
                hit = Hit(logical, name, p)
                self.log[logical] = hit
                return hit
        return None

    def exists(self, path: str) -> bool:
        return self.resolve(path) is not None

    def read(self, path: str) -> bytes:
        hit = self.resolve(path)
        if hit is None:
            raise FileNotFoundError("%s: in none of %s" % (normalise(path), [n for n, _ in self.roots]))
        return hit.path.read_bytes()

    def walk(self, prefix: str = "", suffix: str = "") -> list:
        """[Hit] of every file under the logical folder `prefix` whose logical path ends with `suffix`, first root wins
        per path, sorted by logical path. Not logged in the provenance (nothing is read)."""
        pre = normalise(prefix).rstrip("/")
        suf = suffix.lower()
        seen: dict[str, Hit] = {}
        for name, root in self.roots:
            if hasattr(root, "find"):
                for logical, full in (root.walk(pre, suf) if hasattr(root, "walk") else []):
                    if logical not in seen:
                        seen[logical] = Hit(logical, name, Path(full))
                continue
            base = root
            for part in [p for p in pre.split("/") if p]:
                real = self._listing(base).get(part)
                if real is None:
                    base = None
                    break
                base = base / real
            if base is None or not base.is_dir():
                continue
            for dirpath, _dirs, files in os.walk(base):
                for f in files:
                    full = Path(dirpath) / f
                    logical = normalise(full.relative_to(root).as_posix())
                    if logical.endswith(suf) and logical not in seen:
                        seen[logical] = Hit(logical, name, full)
        return [seen[k] for k in sorted(seen)]

    def provenance(self) -> list:
        """[{logical, root, path}] of every file resolved so far, in order."""
        return [{"logical": h.logical, "root": h.root, "path": str(h.path)} for h in self.log.values()]


def parse_roots(specs) -> list:
    """['mod=work/mod/data', 'base=d2r/data'] (or bare folders, named root1, root2 ...) -> [(name, Path)].
    `casc` (the site's game folder) or `casc=<game folder>` is a casc.CascRoot over that folder's CASC storage."""
    out = []
    for i, s in enumerate(specs, 1):
        name, sep, folder = str(s).partition("=")
        if name == "casc":
            from . import casc
            out.append(("casc", casc.from_site(folder or None)))
            continue
        if not sep:
            name, folder = "root%d" % i, str(s)
        out.append((name, Path(folder)))
    return out
