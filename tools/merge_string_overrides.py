"""Merge extra `d2r:<key>` override records into work/mod/data/local/lng/strings/mxl2012/overrides.json.

tools/tbl2json.py writes overrides.json (Median's text for D2R's own keys, from the .tbl files). Other tools write override
records of their own next to it, in the same record format ({"Key": "d2r:<key>", 13 languages}); this step folds them in, so
the loader sees one file:

  skill_tab_titles.json    tools/skill_tree_art.py: the 21 `d2r:SkillCategory<Cl><n>` skill tab titles (docs/hd-ui.md)

data/d2r_string_fixes.json (committed; `[{"key": "d2r:<key>", "text": ..., "why": ...}]`) holds hand-made overrides of D2R's own
keys that no table cell can reach (docs/bugs.md #18: D2R names its Uber Tristram monsters by class); each becomes a record
with the text in all 13 languages (the language list of the first record of overrides.json), folded in the same way.

A file that does not exist is skipped (the step that writes it did not run). A key already in overrides.json is replaced by the
extra file's record (the later tool knows the key better than the .tbl text); every record keeps exactly one entry per key.
A merged extra file is then moved out of the namespace folder to <mod>/string_extras/: D2RLoader loads every .json in
strings/mxl2012/, so a second copy of a key there is a "duplicate string" and the whole string table fails to initialise
(docs/bugs.md #1). Run it again after the writer: the merge is idempotent.

Usage: py -3 -I tools/merge_string_overrides.py [--mod work/mod] [--extra skill_tab_titles.json ...]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRA = ["skill_tab_titles.json"]
FIXES = ROOT / "data" / "d2r_string_fixes.json"


def read(path: Path) -> list:
    return json.loads(path.read_text("utf-8-sig"))


def fix_records(path: Path, langs: list[str]) -> list[dict]:
    """The records of a d2r_string_fixes.json: {"Key", <langs>}, the same text in every language."""
    out = []
    for f in read(path):
        if not f["key"].startswith("d2r:"):
            raise SystemExit(f"{path.name}: key {f['key']!r} is not a d2r: override")
        out.append({"Key": f["key"], **{lang: f["text"] for lang in langs}})
    return out


def merge(strings_dir: Path, extra: list[str], park: Path | None = None,
          fixes: Path | None = None) -> tuple[int, int, list[str]]:
    """(records added, records replaced, files merged); rewrites overrides.json only when something changed. park: the folder
    the merged extra files are moved to (None: they stay)."""
    target = strings_dir / "overrides.json"
    if not target.exists():
        raise SystemExit(f"{target} missing (run tools/tbl2json.py first)")
    recs = read(target)
    index = {r["Key"]: i for i, r in enumerate(recs)}
    added = replaced = 0
    merged = []

    def fold(records: list[dict], name: str) -> None:
        nonlocal added, replaced
        for r in records:
            if not r["Key"].startswith("d2r:"):
                raise SystemExit(f"{name}: key {r['Key']!r} is not a d2r: override")
            if r["Key"] in index:
                if recs[index[r["Key"]]] != r:
                    recs[index[r["Key"]]] = r
                    replaced += 1
            else:
                index[r["Key"]] = len(recs)
                recs.append(r)
                added += 1

    for name in extra:
        p = strings_dir / name
        if not p.exists():
            continue
        fold(read(p), name)
        merged.append(name)
    if fixes is not None and fixes.exists():
        fold(fix_records(fixes, [k for k in recs[0] if k != "Key"]), fixes.name)
    for name in merged if park is not None else ():
        park.mkdir(parents=True, exist_ok=True)
        (strings_dir / name).replace(park / name)
    if added or replaced:
        text = json.dumps(recs, ensure_ascii=False, indent=2).replace("\n", "\r\n")  # as tbl2json.write_json
        target.write_text("﻿" + text, encoding="utf-8", newline="")
    return added, replaced, merged


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod")
    ap.add_argument("--extra", nargs="*", default=EXTRA)
    args = ap.parse_args(argv)
    added, replaced, merged = merge(args.mod / "data" / "local" / "lng" / "strings" / "mxl2012", args.extra,
                                    args.mod / "string_extras", FIXES)
    print(f"overrides.json: {added} records added, {replaced} replaced from {', '.join(merged) or 'no extra file (none written yet)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
