#!/usr/bin/env python
"""Approved 3D monsters (lane monster3d / fungus14) into the mod build: the stage overlay of s5_build.py, from the art store.

A stage is what tools/sprite3d/monster3d/g6_gamerun.py laid over a test slot for the owner's in-game sign-off: the unit's
files under hd/ (unit JSON, models with LODs, skeleton, clips, textures, glow particles) and its build.json. This tool
gives the built mod exactly that, with the same two index edits g6_gamerun made from the installed mod's own files:

- hd/character/monsters.json: each monstats Id of the entry -> the new unit (every Id that draws the classic monster);
- hd/model_lod_desc.bin: the new model path with the donor's entry and the stage's bounds times its unit scale u
  (model_lod_desc.add).

  python tools/m3d_ship.py store STAGE_DIR --id MONSTATS_ID [--id ...] [--manifest tools/data/m3d_ship.json]
      copies STAGE_DIR/overlay/** into the art store (objects/sha256/..) and writes the monster's manifest entry
  python tools/m3d_ship.py build MOD_DATA [--manifest tools/data/m3d_ship.json]
      lays every listed monster into MOD_DATA (a mod's .../data folder), checking each file's sha256

The build step (tools/build.py, after every writer of monsters.json and model_lod_desc.bin) needs the art store:
MXL_ART_STORE, else machine.json `art_store` (hdkit_site.store_root). MXL2012_M3D=0 leaves the 3D monsters out (the old
build); without a store the step stops instead of shipping a release without them.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tools" / "data" / "m3d_ship.json"
MONSTERS = "hd/character/monsters.json"
LOD_DESC = "hd/model_lod_desc.bin"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def store_root() -> Path:
    sys.path.insert(0, str(ROOT / "tools"))
    import hdkit_site
    root = Path(os.environ.get("MXL_ART_STORE") or hdkit_site.store_root())
    if not (root / "README.md").is_file():
        raise SystemExit("m3d_ship: no art store at %s (set MXL_ART_STORE, e.g. /d2work/mxl2012-art; MXL2012_M3D=0 builds "
                         "without the 3D monsters)" % root)
    return root


def _object(root: Path, sha: str) -> Path:
    return root / "objects" / "sha256" / sha[:2] / sha


def entry_of(stage: Path, ids: list, files: list) -> dict:
    """The manifest entry of a stage: its build.json's unit, model, donor and bounds (times u, as g6_gamerun lays them)."""
    build = json.loads((stage / "build.json").read_text(encoding="utf-8"))
    u = build["u"]
    lo, hi = build["bounds"]
    return {"ids": list(ids), "unit": build["unit"], "model": build["model"], "donor_model": build["donor_model"],
            "bounds": [[v * u for v in lo], [v * u for v in hi]], "stage": str(stage), "files": files}


def store(stage: Path, ids: list, manifest: Path = MANIFEST, root: Path = None, log=print) -> dict:
    """Copies the stage's overlay into the store (by hash, through tmp/) and puts its entry into the manifest."""
    root = root or store_root()
    over = stage / "overlay"
    files = []
    for f in sorted(p for p in over.rglob("*") if p.is_file()):
        h = _sha(f)
        obj = _object(root, h)
        if not obj.exists():
            tmp = root / "tmp" / h
            tmp.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, tmp)
            if _sha(tmp) != h:
                raise SystemExit("m3d_ship: %s changed while it was copied" % f)
            obj.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, obj)
        files.append({"path": f.relative_to(over).as_posix(), "sha256": h, "size": f.stat().st_size})
    for f in files:
        if f["path"] in (MONSTERS, LOD_DESC):
            raise SystemExit("m3d_ship: the overlay holds %s; the build makes it from the mod's own" % f["path"])
    doc = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {
        "about": "3D monsters that tools/build.py ships (tools/m3d_ship.py): files in the art store by sha256, the "
                 "monsters.json and model_lod_desc.bin edits from each entry", "monsters": []}
    doc["monsters"] = [m for m in doc["monsters"] if m["unit"] != entry_of(stage, ids, [])["unit"]] + [entry_of(stage, ids, files)]
    text = json.dumps(doc, indent=1) + "\n"
    manifest.write_text(text, encoding="utf-8")
    copy = root / "manifests" / "m3d" / manifest.name
    copy.parent.mkdir(parents=True, exist_ok=True)
    copy.write_text(text, encoding="utf-8")
    log("stored %s: %d files (%d MB)" % (", ".join(ids), len(files), sum(f["size"] for f in files) >> 20))
    return doc


def build(data: Path, manifest: Path = MANIFEST, root: Path = None, log=print) -> int:
    """Lays every monster of the manifest into the mod data folder `data`. -> the number of files written."""
    sys.path.insert(0, str(ROOT / "tools"))
    import model_lod_desc
    doc = json.loads(manifest.read_text(encoding="utf-8"))
    if not doc["monsters"]:
        return 0
    root = root or store_root()
    table_file, lod_file = data / MONSTERS, data / LOD_DESC
    for f in (table_file, lod_file):
        if not f.is_file():
            raise SystemExit("m3d_ship: the mod has no %s (run after the steps that write it)" % f.relative_to(data))
    table = json.loads(table_file.read_text(encoding="utf-8"))
    lod = lod_file.read_bytes()
    n = 0
    for m in doc["monsters"]:
        missing = [i for i in m["ids"] if i not in table]
        if missing:
            raise SystemExit("m3d_ship: %s not in %s" % (", ".join(missing), MONSTERS))
        for f in m["files"]:
            obj = _object(root, f["sha256"])
            if not obj.is_file() or obj.stat().st_size != f["size"] or _sha(obj) != f["sha256"]:
                raise SystemExit("m3d_ship: %s of %s is missing or changed in the art store (%s)" % (f["path"], m["unit"], obj))
            dest = data / f["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(obj, dest)
            n += 1
        for i in m["ids"]:
            log("%s: %s -> %s" % (i, table[i], m["unit"]))
            table[i] = m["unit"]
        log("%s: %d files" % (m["unit"], len(m["files"])))
        lod = model_lod_desc.add(lod, {m["model"]: m["donor_model"]}, {m["model"]: tuple(map(tuple, m["bounds"]))})
    table_file.write_text(json.dumps(table, indent=2), encoding="utf-8")   # hd_monsters.py writes it the same way
    lod_file.write_bytes(lod)
    return n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("store")
    s.add_argument("stage", type=Path)
    s.add_argument("--id", required=True, action="append", help="a monstats Id (a key of hd/character/monsters.json); repeat it for every Id that draws the monster")
    s.add_argument("--manifest", type=Path, default=MANIFEST)
    b = sub.add_parser("build")
    b.add_argument("data", type=Path)
    b.add_argument("--manifest", type=Path, default=MANIFEST)
    a = ap.parse_args(argv)
    if a.cmd == "store":
        store(a.stage, a.id, a.manifest)
        return 0
    if os.environ.get("MXL2012_M3D", "1") == "0":
        print("m3d_ship: MXL2012_M3D=0, no 3D monsters")
        return 0
    print("m3d_ship: %d files" % build(a.data, a.manifest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
