"""A content-addressed store for large outputs: `objects/sha256/<2 hex>/<sha256>`, written through `tmp/`, hash checked.

The layout of the art store README (one file per content hash, no extension, never changed once written; a copy goes to
`tmp/` first, its hash is checked, then it moves into `objects/`). The store folder is `HDKIT_STORE`, else `store_root()`
of the optional site adapter `hdkit_site`, else none (outputs then stay where they were written).

  put(path)               move one file into the store; returns {sha256, size, object}
  offload(paths, min_bytes, manifest)   every listed file of at least min_bytes goes in; a manifest JSON (logical name,
                          sha256, size, object, source) is written next to the outputs and copied to
                          `manifests/hdkit-view/` in the store
"""
import hashlib
import importlib
import json
import os
import shutil
import time
from pathlib import Path


def root() -> Path | None:
    env = os.environ.get("HDKIT_STORE")
    if env:
        return Path(env)
    try:
        site = importlib.import_module("hdkit_site")
    except ImportError:
        return None
    fn = getattr(site, "store_root", None)
    r = fn() if fn else None
    return Path(r) if r else None


def sha256(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8 << 20), b""):
            h.update(b)
    return h.hexdigest()


def put(path, store=None, keep: bool = False) -> dict:
    store = Path(store) if store else root()
    if store is None:
        raise RuntimeError("no store: set HDKIT_STORE")
    p = Path(path)
    dg = sha256(p)
    obj = store / "objects" / "sha256" / dg[:2] / dg
    if not (obj.exists() and obj.stat().st_size == p.stat().st_size and sha256(obj) == dg):
        tmp = store / "tmp" / ("%s.%d.part" % (dg, os.getpid()))
        tmp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, tmp)
        if sha256(tmp) != dg:
            tmp.unlink()
            raise RuntimeError("store copy of %s does not hash equal" % p)
        obj.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp, obj)
    size = p.stat().st_size
    if not keep:
        p.unlink()
    return {"sha256": dg, "size": size, "object": str(obj)}


def offload(paths, min_bytes: int, manifest, source: dict | None = None, store=None) -> dict:
    """Move each existing file of at least min_bytes into the store. Returns {local path: entry}; writes `manifest`."""
    store = Path(store) if store else root()
    moved = {}
    if store is None:
        return moved
    for p in paths:
        p = Path(p)
        if p.is_file() and p.stat().st_size >= min_bytes:
            e = put(p, store)
            e["path"] = p.name
            moved[str(p)] = e
    if moved:
        man = {"tool": "hdkit.view", "written": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": source or {},
               "files": list(moved.values())}
        mp = Path(manifest)
        mp.write_text(json.dumps(man, indent=1) + "\n", encoding="utf-8")
        cp = store / "manifests" / "hdkit-view" / ("%s_%s.json" % (mp.parent.name, mp.stem))
        cp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(mp, cp)
    return moved
