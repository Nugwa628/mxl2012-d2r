"""Validator for the mxl2012 string output and for the string keys the tables name (docs/strings.md "strings_check").

Checks, in this order:
  1. the generated string files (work/mod): no `id` anywhere, no key defined twice in the package, every `d2r:<key>` override
     names a key D2R's strings/ files have, 13 languages per record, strings_namespace.json == median.json keys, no key with a
     ':' (it would be read as a namespace), every alias target exists, strings_map.json agrees with the files;
  2. every localization cell of the mod's tables (strings_ns.LOCALIZATION) in --excel-dir:
     * default (raw tables, keys as Median wrote them): a key that neither the mod's strings nor D2R's files define is
       MISSING (the game would show "Missing string" / an empty name); a numeric or text key is looked up case-insensitively,
       like D2R does;
     * --rewritten (tables after the tables lane's rewrite): additionally an unqualified cell naming a group 2 key,
       a `mxl2012:<key>` cell whose key is not in the namespace, a `d2r:<key>` cell D2R does not know, and a cell longer than its
       fixed-size field (strings_ns.CELL_LIMITS) are errors.

  3. with --rewritten: tools/text_audit.py (docs/text-audit.md), the text a player reads: a cell whose text is a key name, a
     placeholder, "Missing string" or empty where the thing has art, and every `@key` in the mod's UI layouts. A hit is an
     error, so a new one fails the build (fix it in data/string_gaps.tsv, or give it a reasoned row in data/text_audit_allow.tsv).

Exit code 1 on an error or a missing key (--warn-missing: missing keys do not fail). Usage:
  py -3 -I tools/strings_check.py [--excel-dir <mod data/global/excel>] [--rewritten] [--warn-missing] [--d2r-lng <dir>]
      [--layouts-dir <mod data/global/ui/layouts>] [--no-text-audit]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import strings_ns as ns  # noqa: E402

LANGS = ["enUS", "zhTW", "deDE", "esES", "frFR", "itIT", "koKR", "plPL", "esMX", "jaJP", "ptBR", "ruRU", "zhCN"]
MOD = ns.ROOT / "work" / "mod"


def load(p: Path):
    return json.loads(p.read_text("utf-8-sig"))


def check_files(errors: list[str], d2r_loaded: dict) -> tuple[set[str], set[str]]:
    """Returns (group 2 keys from median.json, override bare keys)."""
    base = MOD / "data" / "local" / "lng"
    median_p, over_p = base / "strings" / ns.NAMESPACE / "median.json", base / "strings" / ns.NAMESPACE / ns.OVERRIDE_FILE
    for p in (median_p, over_p, MOD / "strings_namespace.json", MOD / "strings_map.json"):
        if not p.exists():
            errors.append(f"missing output file {p} (run tools/tbl2json.py)")
    if errors:
        return set(), set()
    median, over = load(median_p), load(over_p)
    seen: dict[str, str] = {}
    for label, recs in (("median.json", median), ("overrides.json", over)):
        for e in recs:
            k = e["Key"]
            if "id" in e or "Id" in e:
                errors.append(f"{label}: record {k!r} has an id (an unqualified record would define {ns.NAMESPACE}:<key>, ids are ignored)")
            if k in seen:
                errors.append(f"{label}: key {k!r} defined twice (also in {seen[k]}); the loader refuses to start")
            seen[k] = label
            missing = [lang for lang in LANGS if lang not in e]
            if missing:
                errors.append(f"{label}: {k!r} lacks languages {missing}")
    g2 = {e["Key"] for e in median}
    for e in median:
        if ":" in e["Key"]:
            errors.append(f"median.json: key {e['Key']!r} contains ':' (read as a namespace)")
    ov_keys = set()
    for e in over:
        k = e["Key"]
        if not k.startswith(ns.D2R_PREFIX):
            errors.append(f"overrides.json: record {k!r} is not a `d2r:` record")
            continue
        ov_keys.add(k[len(ns.D2R_PREFIX):])
        if k[len(ns.D2R_PREFIX):] not in d2r_loaded:
            errors.append(f"overrides.json: {k!r}: D2R's strings/ files do not have the key (the loader rejects it)")
    if g2 & ov_keys:
        errors.append(f"keys in both files: {sorted(g2 & ov_keys)[:5]}")
    listed = set(load(MOD / "strings_namespace.json")["keys"])
    if listed != g2:
        errors.append(f"strings_namespace.json and median.json differ ({len(listed ^ g2)} keys)")
    m = load(MOD / "strings_map.json")
    for k, a in m["aliases"].items():
        if a not in g2 or k not in g2:
            errors.append(f"alias {a!r} / key {k!r} missing from median.json")
    if set(m["group2"]) | set(m["aliases"].values()) != g2:
        errors.append("strings_map.json group2 + aliases do not equal median.json")
    for sid, full in m["id_keys"].items():
        k = ns.bare(full)
        if full.startswith(ns.PREFIX) and k not in g2:
            errors.append(f"id_keys {sid} -> {full}: not in median.json")
        elif not full.startswith(ns.PREFIX) and k not in d2r_loaded and k not in ns.d2r_keys():
            errors.append(f"id_keys {sid} -> {full}: neither group 2 nor a D2R key")
    return g2, ov_keys


def read_table(path: Path) -> tuple[list[str], list[list[str]]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    lines = text.replace("\r\n", "\n").split("\n")
    head = lines[0].split("\t")
    return head, [ln.split("\t") for ln in lines[1:] if ln]


def check_cells(excel: Path, rewritten: bool, g2: set[str], d2r_all: set[str], d2r_loaded: dict, errors: list[str],
                missing: dict[str, list[str]], stats: dict) -> None:
    g2_fold = {k.lower() for k in g2}
    known_fold = g2_fold | {k.lower() for k in d2r_all}
    d2r_loaded_fold = {k.lower() for k in d2r_loaded}
    for table, cols in sorted(ns.LOCALIZATION.items()):
        path = excel / f"{table}.txt"
        if not path.exists():
            continue
        head, rows = read_table(path)
        lower = [h.strip().lower() for h in head]
        for col in sorted(cols):
            if col not in lower:
                continue
            ci = lower.index(col)
            limit = ns.CELL_LIMITS.get(f"{table}.{col}")
            for n, row in enumerate(rows, 2):
                v = row[ci] if ci < len(row) else ""
                if not v or ns.is_label_column(table, col) or ns.is_placeholder(table, col, v):
                    continue
                stats["cells"] += 1
                where = f"{table}.txt row {n} {head[ci]}={v!r}"
                if limit and len(v) > limit:
                    errors.append(f"{where}: {len(v)} chars, the field holds {limit}")
                space, key = ns.split_key(v)
                if space == ns.NAMESPACE:
                    if not rewritten:
                        errors.append(f"{where}: qualified cell in a raw table")
                    elif key not in g2:
                        errors.append(f"{where}: {ns.NAMESPACE} key not in the namespace")
                elif space == "d2r":
                    if key.lower() not in d2r_loaded_fold:
                        errors.append(f"{where}: D2R has no such key")
                elif rewritten and key in g2:
                    errors.append(f"{where}: unqualified cell names a group 2 key (needs {ns.PREFIX})")
                elif key.lower() not in known_fold:
                    missing[f"{table}.{col}"].append(v)
                    stats["missing_cells"] += 1


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # the report holds non-ASCII characters; the console may be cp932
    ap = argparse.ArgumentParser()
    ap.add_argument("--excel-dir", type=Path)
    ap.add_argument("--rewritten", action="store_true")
    ap.add_argument("--warn-missing", action="store_true")
    ap.add_argument("--d2r-lng", type=Path, help="D2R data/local/lng (default: env D2R_LNG or extract/d2r/...)")
    ap.add_argument("--layouts-dir", type=Path, default=ns.ROOT / "work" / "mod" / "data" / "global" / "ui" / "layouts",
                    help="the mod's UI layouts for the text audit (skipped when the folder does not exist yet)")
    ap.add_argument("--no-text-audit", action="store_true", help="skip tools/text_audit.py")
    args = ap.parse_args()
    if args.d2r_lng:
        ns.D2R_LNG = args.d2r_lng
    errors: list[str] = []
    d2r_loaded, d2r_all = ns.d2r_loaded(), ns.d2r_keys()
    g2, _ov = check_files(errors, d2r_loaded)
    missing: dict[str, list[str]] = defaultdict(list)
    stats = {"cells": 0, "missing_cells": 0}
    if args.excel_dir and g2:
        check_cells(args.excel_dir, args.rewritten, g2, d2r_all, d2r_loaded, errors, missing, stats)
    audit_report: list[str] = []
    if args.excel_dir and args.rewritten and g2 and not args.no_text_audit:
        import text_audit
        found, audit_report = text_audit.audit(args.excel_dir, text_audit.Strings.load(), args.layouts_dir)
        errors += [f"text audit: {f}" for f in found]
    print(f"files: group 2 keys {len(g2)}; cells checked {stats['cells']}")
    for line in audit_report:
        print(line)
    for e in errors[:200]:
        print("ERROR", e)
    if len(errors) > 200:
        print(f"... {len(errors) - 200} more errors")
    for col, vals in sorted(missing.items()):
        uniq = sorted(set(vals))
        print(f"MISSING {col}: {len(vals)} cells, {len(uniq)} keys, e.g. {uniq[:8]}")
    print(f"{len(errors)} errors, {stats['missing_cells']} cells with a missing key")
    return 1 if errors or (stats["missing_cells"] and not args.warn_missing) else 0


if __name__ == "__main__":
    sys.exit(main())
