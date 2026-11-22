"""Working copies: a map's .ds1 and HD preset copied into a folder of their own, edited there, rendered from there.
Never the extracts, a build output or a game folder: every write goes below the working copy (checked).

  <work>/workcopy.json                       map, source, where each file was copied from
  <work>/data/global/tiles/<map>.ds1         the .ds1 (renders read it through `--work <work>`)
  <work>/data/hd/env/preset/...<map>.json    the preset, at the logical path it came from (a hdkit root, ahead of the mod
                                             data and CASC, so the HD render reads the edited copy)
  <work>/edits.jsonl                         one line per edit

  python -m hdkit.view map edit init <map> [--work DIR] [--source ...]       default DIR /d2work/runs/mapview/work/<map name>
  python -m hdkit.view map edit tile <work> <x> <y> --layer floor|wall|shadow [--index 0] (--style S --seq Q
                       [--orientation O] [--prop1 P] [--hidden] | --clear)
  python -m hdkit.view map edit obj-add <work> <type> <id> <subtile x> <subtile y> [--flags F]
  python -m hdkit.view map edit obj-move <work> <index> <subtile x> <subtile y>
  python -m hdkit.view map edit obj-remove <work> <index>
  python -m hdkit.view map edit ent-add <work> --model <logical .model> --pos x,y,z [--yaw deg] [--name n]
  python -m hdkit.view map edit ent-move <work> <index> --pos x,y,z [--yaw deg]
  python -m hdkit.view map edit ent-remove <work> <index>
  python -m hdkit.view map edit show <work>                                   the edits and a cell diff against the origin

Entity positions are HD world units (x, y up, z; 10 per cell, cell (cx, cy) spans x 10cx..10cx+10, z 10cy..10cy+10).
"""
from __future__ import annotations

import json
import math
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import ds1 as D

WORK_ROOT = Path(os.environ.get("MAPVIEW_WORK") or "/d2work/runs/mapview/work")
FORBIDDEN = ("/d2work/slots", "/d2work/extract", "/d2work/mxl2012-runs/extract-mpq", "/games", "/d2work/data", "/mnt")


def _guard(path: Path, root: Path):
    p = Path(path).resolve()
    r = Path(root).resolve()
    if r != p and r not in p.parents:
        raise PermissionError("refusing to write %s: outside the working copy %s" % (p, r))
    for f in FORBIDDEN:
        if str(p).startswith(f + "/"):
            raise PermissionError("refusing to write %s: a game / extract folder" % p)


@dataclass
class WorkCopy:
    root: Path
    meta: dict

    @property
    def map(self):
        return self.meta["map"]

    @property
    def source(self):
        return self.meta["source"]

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def ds1_path(self) -> Path:
        return self.data_dir / "global" / "tiles" / (self.map + ".ds1")

    @property
    def preset_path(self) -> Path | None:
        lg = self.meta.get("preset_logical")
        return self.data_dir / lg if lg else None

    @classmethod
    def open(cls, work) -> "WorkCopy":
        root = Path(work)
        if not (root / "workcopy.json").exists() and (WORK_ROOT / str(work) / "workcopy.json").exists():
            root = WORK_ROOT / str(work)
        meta = json.loads((root / "workcopy.json").read_text("utf-8"))
        return cls(root, meta)

    @classmethod
    def init(cls, name: str, work: str | None = None, source: str = "auto", hd: bool = True, force: bool = False,
             roots=None):
        from . import world
        src = world.MapSource(name, source, roots=roots)
        root = Path(work) if work else WORK_ROOT / src.key.replace("/", "_")
        for f in FORBIDDEN:
            if str(root.resolve()).startswith(f + "/") or str(root.resolve()) == f:
                raise PermissionError("a working copy may not live in %s" % f)
        if (root / "workcopy.json").exists() and not force:
            raise FileExistsError("%s is a working copy already (force=True starts it again)" % root)
        root.mkdir(parents=True, exist_ok=True)
        meta = {"map": src.key, "source": src.source, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "ds1_from": str(src.ds1_path)}
        wc = cls(root, meta)
        wc.ds1_path.parent.mkdir(parents=True, exist_ok=True)
        _guard(wc.ds1_path, root)
        shutil.copyfile(src.ds1_path, wc.ds1_path)
        if hd:
            try:
                from . import hd as H
                specs = H.roots_for(src.source)
                fs = H.fs_for(specs)
                lg = H.find_preset(fs, src.key, src.source)
                if lg:
                    hit = fs.resolve(lg)
                    dest = wc.data_dir / hit.logical
                    _guard(dest, root)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(fs.read(lg))
                    meta["preset_logical"] = hit.logical
                    meta["preset_from"] = "%s:%s" % (hit.root, hit.path)
            except Exception as e:      # no CASC: a classic-only working copy
                meta["preset_error"] = str(e)
        wc.save_meta()
        (root / "edits.jsonl").touch()
        return wc

    def save_meta(self):
        _guard(self.root / "workcopy.json", self.root)
        (self.root / "workcopy.json").write_text(json.dumps(self.meta, indent=1), encoding="utf-8")

    def log(self, op: dict):
        _guard(self.root / "edits.jsonl", self.root)
        op = dict(op, time=time.strftime("%Y-%m-%d %H:%M:%S"))
        with open(self.root / "edits.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(op) + "\n")

    # ---- .ds1 ----------------------------------------------------------------------------------------------------------
    def ds1(self) -> D.Ds1:
        return D.Ds1.read(self.ds1_path)

    def write_ds1(self, ds: D.Ds1):
        _guard(self.ds1_path, self.root)
        ds.write(self.ds1_path)

    def set_tile(self, x: int, y: int, layer: str = "floor", index: int = 0, style: int | None = None,
                 seq: int | None = None, orientation: int | None = None, prop1: int | None = None, hidden: bool = False,
                 clear: bool = False) -> dict:
        ds = self.ds1()
        if not (0 <= x < ds.width and 0 <= y < ds.height):
            raise ValueError("cell %d,%d outside the map" % (x, y))
        key = (layer, index if layer != "shadow" else 0)
        if key not in ds.layers:
            raise ValueError("no layer %s %d (walls %d, floors %d)" % (layer, index, ds.n_walls, ds.n_floors))
        old = int(ds.layers[key][y, x])
        if clear:
            new = 0
        else:
            if style is None or seq is None:
                raise ValueError("style and seq (or clear)")
            new = D.make_cell(style, seq, prop1 if prop1 is not None else ((old & 0xFF) or 1), hidden, old)
        ds.layers[key][y, x] = new
        old_o = None
        if layer == "wall" and orientation is not None:
            ok = ("orient", index)
            old_o = int(ds.layers[ok][y, x])
            if ds.version < 7:
                raise ValueError("orientation edits need a .ds1 of version 7 or later")
            ds.layers[ok][y, x] = (old_o & ~0xFF) | (orientation & 0xFF)
        self.write_ds1(ds)
        op = {"op": "tile", "cell": [x, y], "layer": layer, "index": index, "old": "%08x" % old, "new": "%08x" % new}
        if old_o is not None:
            op["orientation"] = [old_o & 0xFF, orientation]
        self.log(op)
        return op

    def obj_add(self, t: int, ident: int, sx: int, sy: int, flags: int = 0) -> dict:
        ds = self.ds1()
        ds.objects.append(D.Obj(t, ident, sx, sy, flags))
        self.write_ds1(ds)
        op = {"op": "obj-add", "index": len(ds.objects) - 1, "object": [t, ident, sx, sy, flags]}
        self.log(op)
        return op

    def obj_move(self, index: int, sx: int, sy: int) -> dict:
        ds = self.ds1()
        o = ds.objects[index]
        old = [o.x, o.y]
        o.x, o.y = sx, sy
        self.write_ds1(ds)
        op = {"op": "obj-move", "index": index, "old": old, "new": [sx, sy],
              "note": "NPC paths in the .ds1 tail are kept as they are"}
        self.log(op)
        return op

    def obj_remove(self, index: int) -> dict:
        ds = self.ds1()
        o = ds.objects.pop(index)
        self.write_ds1(ds)
        op = {"op": "obj-remove", "index": index, "object": o.as_list(),
              "note": "later objects move up one index; NPC paths are kept as they are"}
        self.log(op)
        return op

    # ---- preset --------------------------------------------------------------------------------------------------------
    def preset(self) -> dict:
        if not self.preset_path or not self.preset_path.exists():
            raise FileNotFoundError("this working copy has no preset (%s)" % self.meta.get("preset_error", "none found"))
        return json.loads(self.preset_path.read_text("utf-8-sig"))

    def write_preset(self, d: dict):
        _guard(self.preset_path, self.root)
        self.preset_path.write_text(json.dumps(d, indent=4), encoding="utf-8")

    def ent_add(self, model: str, pos, yaw: float = 0.0, name: str | None = None) -> dict:
        d = self.preset()
        ents = d.setdefault("entities", [])
        ids = {e.get("id") for e in ents}
        nid = 0x6D760000
        while nid in ids:
            nid += 1
        nm = name or "mapview_%s_%d" % (Path(model).stem, len(ents))
        h = math.radians(yaw) / 2.0
        ent = {"type": "Entity", "name": nm, "id": nid, "components": [
            {"type": "TransformDefinitionComponent", "name": nm + "_TransformDefinitionComponent",
             "position": {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])},
             "orientation": {"x": 0.0, "y": math.sin(h), "z": 0.0, "w": math.cos(h)},
             "scale": {"x": 1.0, "y": 1.0, "z": 1.0}, "inheritOnlyPosition": False},
            {"type": "ModelDefinitionComponent", "name": "model", "filename": model, "visibleLayers": 1, "lightMask": 19,
             "shadowMask": 3, "ghostShadows": False, "floorModel": False, "terrainBlendEnableYUpBlend": False,
             "terrainBlendMode": 1}]}
        ents.append(ent)
        self.write_preset(d)
        op = {"op": "ent-add", "index": len(ents) - 1, "name": nm, "model": model, "pos": list(pos), "yaw": yaw}
        self.log(op)
        return op

    def ent_move(self, index: int, pos, yaw: float | None = None) -> dict:
        d = self.preset()
        ent = d["entities"][index]
        td = next((c for c in ent["components"] if c["type"] == "TransformDefinitionComponent"), None)
        if td is None:
            raise ValueError("entity %d has no transform" % index)
        old = dict(td.get("position") or {})
        td["position"] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])}
        if yaw is not None:
            h = math.radians(yaw) / 2.0
            td["orientation"] = {"x": 0.0, "y": math.sin(h), "z": 0.0, "w": math.cos(h)}
        self.write_preset(d)
        op = {"op": "ent-move", "index": index, "name": ent.get("name"), "old": old, "new": td["position"], "yaw": yaw}
        self.log(op)
        return op

    def ent_remove(self, index: int) -> dict:
        d = self.preset()
        ent = d["entities"].pop(index)
        self.write_preset(d)
        op = {"op": "ent-remove", "index": index, "name": ent.get("name"),
              "note": "later entities move up one index"}
        self.log(op)
        return op

    def show(self) -> dict:
        ds = self.ds1()
        orig = D.Ds1.read(self.meta["ds1_from"])
        changed = []
        for k in ds.stream:
            a, b = ds.layers[k], orig.layers.get(k)
            if b is None or a.shape != b.shape:
                continue
            ys, xs = np.nonzero(a != b)
            for y, x in zip(ys.tolist(), xs.tolist()):
                changed.append({"layer": "%s%d" % k, "cell": [x, y], "old": "%08x" % int(b[y, x]),
                                "new": "%08x" % int(a[y, x])})
        edits = [json.loads(s) for s in (self.root / "edits.jsonl").read_text("utf-8").splitlines() if s.strip()]
        return {"work": str(self.root), "meta": self.meta, "edits": edits, "cells_changed": changed[:500],
                "cells_changed_total": len(changed), "objects": [len(orig.objects), len(ds.objects)],
                "ds1_identical": ds.pack() == orig.pack()}


# ---- CLI ---------------------------------------------------------------------------------------------------------------------
def _xyz(s):
    v = [float(t) for t in s.split(",")]
    if len(v) != 3:
        raise ValueError("--pos x,y,z")
    return v


def add_parser(sub):
    e = sub.add_parser("edit", help="working-copy edits (see map edit -h)")
    es = e.add_subparsers(dest="op", required=True)
    i = es.add_parser("init")
    i.add_argument("map")
    i.add_argument("--work", default=None)
    i.add_argument("--source", default="auto", choices=("auto", "mod", "d2r"))
    i.add_argument("--no-hd", action="store_true")
    i.add_argument("--force", action="store_true")
    t = es.add_parser("tile")
    t.add_argument("work")
    t.add_argument("x", type=int)
    t.add_argument("y", type=int)
    t.add_argument("--layer", default="floor", choices=("floor", "wall", "shadow"))
    t.add_argument("--index", type=int, default=0)
    t.add_argument("--style", type=int)
    t.add_argument("--seq", type=int)
    t.add_argument("--orientation", type=int)
    t.add_argument("--prop1", type=int)
    t.add_argument("--hidden", action="store_true")
    t.add_argument("--clear", action="store_true")
    oa = es.add_parser("obj-add")
    for n in ("work", "type", "id", "sx", "sy"):
        oa.add_argument(n, type=(str if n == "work" else int))
    oa.add_argument("--flags", type=int, default=0)
    om = es.add_parser("obj-move")
    for n in ("work", "index", "sx", "sy"):
        om.add_argument(n, type=(str if n == "work" else int))
    orm = es.add_parser("obj-remove")
    orm.add_argument("work")
    orm.add_argument("index", type=int)
    ea = es.add_parser("ent-add")
    ea.add_argument("work")
    ea.add_argument("--model", required=True)
    ea.add_argument("--pos", required=True)
    ea.add_argument("--yaw", type=float, default=0.0)
    ea.add_argument("--name", default=None)
    em = es.add_parser("ent-move")
    em.add_argument("work")
    em.add_argument("index", type=int)
    em.add_argument("--pos", required=True)
    em.add_argument("--yaw", type=float, default=None)
    er = es.add_parser("ent-remove")
    er.add_argument("work")
    er.add_argument("index", type=int)
    sh = es.add_parser("show")
    sh.add_argument("work")


def run(a, log=print) -> dict:
    if a.op == "init":
        wc = WorkCopy.init(a.map, a.work, a.source, not a.no_hd, a.force)
        return {"work": str(wc.root), "meta": wc.meta}
    wc = WorkCopy.open(a.work)
    if a.op == "tile":
        return wc.set_tile(a.x, a.y, a.layer, a.index, a.style, a.seq, a.orientation, a.prop1, a.hidden, a.clear)
    if a.op == "obj-add":
        return wc.obj_add(a.type, a.id, a.sx, a.sy, a.flags)
    if a.op == "obj-move":
        return wc.obj_move(a.index, a.sx, a.sy)
    if a.op == "obj-remove":
        return wc.obj_remove(a.index)
    if a.op == "ent-add":
        return wc.ent_add(a.model, _xyz(a.pos), a.yaw, a.name)
    if a.op == "ent-move":
        return wc.ent_move(a.index, _xyz(a.pos), a.yaw)
    if a.op == "ent-remove":
        return wc.ent_remove(a.index)
    if a.op == "show":
        return wc.show()
    raise SystemExit("unknown edit op")
