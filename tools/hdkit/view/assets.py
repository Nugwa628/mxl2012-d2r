"""What the roots hold: units, models and a unit's clips, listed over a `vfs.Layered` (nothing outside the roots is read).

  units    unit JSONs as D2R lays them out: `hd/character/<kind>/<name>.json` (one folder below `hd/character`)
  models   every `.model` under `hd/` (LOD files included; `scene.load_unit` picks `_lod<N>` itself)
  clips    the clips of one unit or model (`combined.animations` next to its model): name, duration, decodable

`resolve(fs, path)` says which root answers a logical path. Results are plain dicts, so the CLI prints them as JSON and the
MCP server returns them as they are.
"""
import fnmatch

from . import scene, vfs

KINDS = ("units", "models", "clips")


def _match(logical: str, pattern: str | None) -> bool:
    if not pattern:
        return True
    pat = pattern.lower()
    return fnmatch.fnmatchcase(logical, pat) if any(c in pat for c in "*?[") else pat in logical


def units(fs: vfs.Layered, pattern: str | None = None) -> list:
    out = []
    for h in fs.walk("hd/character", ".json"):
        parts = h.logical.split("/")
        if len(parts) == 4 and _match(h.logical, pattern):
            out.append({"logical": h.logical, "root": h.root, "name": parts[-1][:-5]})
    return out


def models(fs: vfs.Layered, pattern: str | None = None) -> list:
    return [{"logical": h.logical, "root": h.root} for h in fs.walk("hd", ".model") if _match(h.logical, pattern)]


def clips(fs: vfs.Layered, asset: str, lod: int = 0) -> dict:
    u = scene.load_unit(fs, asset, lod)
    return {"asset": vfs.normalise(asset), "unit": u.name, "kind": u.kind, "root_scale": u.root_scale,
            "parts": [{"name": p.name, "model": p.model, "meshes": len(p.meshes), "skeleton": p.skeleton is not None,
                       "layers": [ly.name for ly in p.layers]} for p in u.parts],
            "clips": [{"name": n, "duration": round(float(c.duration), 4), "decodable": bool(c.decodable())}
                      for n, c in sorted(u.clips.items())],
            "modes": {m: c for m, c in scene.MODE_CLIP.items() if c in u.clips},
            "notes": u.notes, "files": fs.provenance()}


def listing(fs: vfs.Layered, kind: str = "units", pattern: str | None = None, asset: str | None = None,
            limit: int | None = 200, lod: int = 0) -> dict:
    """One call for the three kinds; `limit` cuts long lists (the total is kept)."""
    if kind not in KINDS:
        raise ValueError("kind: one of %s" % (KINDS,))
    if kind == "clips":
        if not asset:
            raise ValueError("clips: name the unit or model (asset)")
        return clips(fs, asset, lod)
    items = units(fs, pattern) if kind == "units" else models(fs, pattern)
    n = len(items)
    if limit is not None and n > limit:
        items = items[:limit]
    return {"kind": kind, "pattern": pattern, "total": n, "shown": len(items), "items": items,
            "roots": [{"name": nm, "folder": str(p)} for nm, p in fs.roots]}


def resolve(fs: vfs.Layered, path: str) -> dict:
    h = fs.resolve(path)
    shadowed = [nm for nm, root in fs.roots if h is not None and nm != h.root and fs._find(root, h.logical) is not None]
    return {"logical": vfs.normalise(path), "found": h is not None, "root": h.root if h else None,
            "path": str(h.path) if h else None, "size": h.path.stat().st_size if h else None, "also_in": shadowed}
