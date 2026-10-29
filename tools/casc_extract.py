"""Extract vanilla D2R files from CASC into extract/d2r/<build>/ as the baseline for the port.

Usage:
  python tools/casc_extract.py                      # default sets: excel, strings, layouts, dataguide
  python tools/casc_extract.py --set legacy-ui      # add more sets (repeatable), see SETS
  python tools/casc_extract.py --prefix data\\global\\monsters\\   # any raw prefix(es)

Paths are written without the "data:" storage prefix, e.g. extract/d2r/93847/data/global/excel/skills.txt.
"""
import d2r_game  # noqa: E402
import argparse
import json
import sys
from pathlib import Path

import native

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GAME = d2r_game.read_game_dir()

SETS = {
    "excel": ["data\\global\\excel\\"],
    "strings": ["data\\local\\lng\\"],
    "layouts": ["data\\global\\ui\\layouts\\"],
    "dataguide": ["data\\global\\dataguide\\"],
    "meta": ["data\\global\\dataversionbuild.txt", "data\\hd\\global\\excel\\desecratedzones.json"],
    "legacy-ui": ["data\\global\\ui\\"],
    "legacy-art": ["data\\global\\chars\\", "data\\global\\monsters\\", "data\\global\\missiles\\",
                   "data\\global\\items\\", "data\\global\\objects\\", "data\\global\\overlays\\"],
    "legacy-maps": ["data\\global\\tiles\\"],
    "hd-ui": ["data\\hd\\global\\ui\\"],
}
DEFAULT_SETS = ["excel", "strings", "layouts", "dataguide", "meta"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--set", action="append", choices=sorted(SETS), help="file set (repeatable)")
    ap.add_argument("--prefix", action="append", default=[], help="raw path prefix (repeatable)")
    ap.add_argument("--out", help="default: extract/d2r/<build>")
    args = ap.parse_args()

    prefixes = [p.lower() for s in (args.set or DEFAULT_SETS) for p in SETS[s]]
    prefixes += [p.lower().replace("/", "\\") for p in args.prefix]

    storage = native.open_casc(args.game)
    try:
        build = native.casc_read(storage, "data:data/global/dataversionbuild.txt").decode().strip()
        out = Path(args.out) if args.out else ROOT / "extract" / "d2r" / build
        wanted = []
        missing_locally = []
        for name, size, available in native.casc_files(storage):
            if not name.startswith("data:"):
                continue
            rel = name[len("data:"):]
            if not any(rel.lower().startswith(p) for p in prefixes):
                continue
            (wanted if available else missing_locally).append((name, rel, size))

        print(f"build {build}: {len(wanted)} files to extract, {len(missing_locally)} not downloaded locally", flush=True)
        failed = []
        for i, (name, rel, _) in enumerate(wanted, 1):
            dest = out / rel.replace("\\", "/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                dest.write_bytes(native.casc_read(storage, name))
            except OSError as e:
                failed.append(f"{rel}: {e}")
            if i % 500 == 0:
                print(f"  {i}/{len(wanted)}", flush=True)
    finally:
        native.casc.CascCloseStorage(storage)

    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {"files": {}}
    manifest.update({"game": args.game, "build": build})
    manifest["files"].update({rel.replace("\\", "/"): size for _, rel, size in wanted})
    manifest["not_local"] = sorted(set(manifest.get("not_local", [])) | {r for _, r, _ in missing_locally})
    manifest["failed"] = failed
    manifest_path.write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{len(wanted) - len(failed)} extracted, {len(failed)} failed -> {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
