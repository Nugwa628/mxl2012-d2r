"""Convert Median XL's string tables (.tbl) into D2R string JSON files.

Input:  Median XL 2012 (classic 1.13c): <tbl-dir>/{string,expansionstring,patchstring}.tbl. --tbl-dir can be given several
        times; a later directory replaces a whole file of an earlier one (loose files over patch_d2.mpq). Default:
        assets/mxl2012/data/local/lng/eng.
        D2R baseline: extract/d2r/<build>/data/local/lng/{strings,strings-legacy}/*.json (--d2r-lng or env D2R_LNG)
Output: work/mod/data/local/lng/strings/mxl2012/overrides.json (Median's text for D2R's own keys, records
        {"Key": "d2r:<key>", 13 languages}, no id, one per key) and strings/mxl2012/median.json (Median-only keys,
        namespace "mxl2012", no ids; mirrored to strings-legacy/mxl2012/median.json), work/mod/strings_namespace.json, work/mod/strings_idkeys.json, strings_report.md.
        D2R's own string files are not copied: they load from the game.

String IDs: string.tbl index, patchstring 10000 + index, expansionstring 20000 + index (what D2Sigma's tables
and code use). Rules:
  * Strings Median only looks up by ID share the throwaway key "x" (or none); they get the unique key
    "mxl_<id>". Numeric keys ("115" = "Axe (1)") are unique and used by item namestr cells, so they stay.
    strings_idkeys.json maps every Median ID to its final key.
  * A key in several tables: patchstring wins over expansionstring over string (1.13c lookup order).
  * Group 1: keys D2R already has are overridden by `d2r:<key>` records in mxl2012/overrides.json (once the mod has
    a namespace an unqualified record would define `mxl2012:<key>` instead). Only keys of D2R's strings/ files (the set
    the loader knows) whose text changes are written, unless the two texts' printf placeholders differ: D2R formats some
    strings itself (e.g. sysmsg7-9, the "was slain by" fragments it joins to names and then passes through sprintf), so
    a Median "%s" there reads a missing argument and crashes the game. Those keys keep D2R's text. Skipped keys are
    listed in strings_report.md. Table cells keep plain keys (= d2r:).
  * Group 2: every other key goes to the D2RLoader namespace "mxl2012" (docs/strings-namespace.md): median.json,
    {"Key", 13 languages}, no id, so no numeric ID can collide with D2R's again (bug #7). The full key is
    "mxl2012:<key>"; strings_namespace.json lists them, strings_idkeys.json maps IDs to the full key.
  * No native exceptions: tools/strings_native.json must stay empty (an unqualified record of a namespaced mod is a
    mxl2012: record and its id is ignored); keys too long for a cell get short aliases in txt_migrate.
  * Median ships English only. By default its text fills every language (otherwise other clients would show
    vanilla wording that contradicts Median); --english-only changes enUS alone.

Usage: python tools/tbl2json.py [--english-only]
"""
import argparse
import json
import re
import shutil
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import string_gaps  # noqa: E402
import strings_ns  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TBL_DEFAULT = ROOT / "assets" / "mxl2012" / "data" / "local" / "lng" / "eng"
D2R_LNG = strings_ns.D2R_LNG  # env D2R_LNG overrides (strings_ns.py)
OUT = ROOT / "work" / "mod"
TABLES = (("string", 0), ("patchstring", 10000), ("expansionstring", 20000))
PRECEDENCE = ("patchstring", "expansionstring", "string")  # first wins for duplicate keys
NAMESPACE = "mxl2012"  # install_mod.py writes the same name to d2rloader/metadata.json
NAMESPACE_FILE = "median.json"
OVERRIDE_FILE = "overrides.json"  # `d2r:<key>` records: Median's text for D2R's own keys
D2R_PREFIX = "d2r:"
ALIAS_SUFFIX = "_mxl"  # Median's text for a key whose D2R text was kept (placeholders differ)
ID_PAIRS: tuple = ()  # Median 2013 only (Ethereal wording); nothing for the 2012 mod
NATIVE_EXCEPTIONS: set[str] = set()  # see load_exceptions()
EXCEPTIONS_FILE = ROOT / "tools" / "strings_native.json"
LANGS = ["enUS", "zhTW", "deDE", "esES", "frFR", "itIT", "koKR", "plPL", "esMX", "jaJP", "ptBR", "ruRU", "zhCN"]


FALLBACK: list[bytes] = []  # raw byte strings that were not valid UTF-8 and were read as cp1252 (reported)


def read_tbl(path: Path) -> list[tuple[str, str]]:
    """1.13c .tbl: header (crc u16, count u16, hash size u32, version u8, data start u32, max tries u32,
    file size u32), count u16 indices into the hash table, then 17-byte hash nodes
    (used u8, index u16, hash u32, key offset u32, string offset u32, length u16). Median wrote its text as
    UTF-8 ("ÿ" = C3 BF); anything that is not valid UTF-8 is read as cp1252, the classic 8-bit encoding."""
    b = path.read_bytes()
    _crc, count, hash_size = struct.unpack_from("<HHI", b, 0)
    header = 21
    indices = struct.unpack_from(f"<{count}H", b, header)
    nodes_at = header + count * 2

    def cstr(off: int) -> str:
        raw = b[off:b.index(b"\0", off)]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            FALLBACK.append(raw)
            return raw.decode("cp1252", errors="replace")

    out = []
    for i in range(count):
        node = nodes_at + indices[i] * 17
        _used, _idx, _h, key_off, str_off, _len = struct.unpack_from("<BHIIIH", b, node)
        out.append((cstr(key_off), cstr(str_off)))
    return out


PLACEHOLDER = re.compile(r"%(?:\d+\$)?[-+ #0]*(?:\d+|\*)?(?:\.\d+)?(?:hh|h|ll|l|I64|z)?[a-zA-Z%]")


def placeholders(text: str) -> list[str]:
    """printf conversions in order ("%%" is literal), e.g. "%+d%% to %s" -> ["d", "s"]."""
    return [m.group()[-1] for m in PLACEHOLDER.finditer(text or "") if m.group() != "%%"]


def load_median(tbl_dirs: list[Path] | None = None) -> tuple[dict[int, tuple[str, str]], dict[str, int]]:
    """id -> (original key, text); key -> winning id. A later directory replaces a whole file of an earlier one."""
    by_id, rank = {}, {}
    for name, base in TABLES:
        src = [d / f"{name}.tbl" for d in (tbl_dirs or [TBL_DEFAULT]) if (d / f"{name}.tbl").exists()]
        if not src:
            raise SystemExit(f"tbl2json: no {name}.tbl in {tbl_dirs or [TBL_DEFAULT]}")
        for i, (key, text) in enumerate(read_tbl(src[-1])):
            by_id[base + i] = (key, text)
            rank[base + i] = PRECEDENCE.index(name)
    winner: dict[str, int] = {}
    for sid in sorted(by_id, key=lambda s: (rank[s], s)):
        winner.setdefault(by_id[sid][0], sid)
    return by_id, winner


def load_exceptions() -> set[str]:
    extra = json.loads(EXCEPTIONS_FILE.read_text("utf-8"))["keys"] if EXCEPTIONS_FILE.exists() else []
    return NATIVE_EXCEPTIONS | set(extra)


def write_json(path: Path, recs: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(recs, ensure_ascii=False, indent=2).replace("\n", "\r\n")
    path.write_text("\ufeff" + text, encoding="utf-8", newline="")


def final_key(sid: int, key: str) -> str:
    return f"mxl_{sid}" if key in ("x", "") else key  # numeric keys stay: item namestr cells use them


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # the report holds non-ASCII characters; the console may be cp932
    ap = argparse.ArgumentParser()
    ap.add_argument("--english-only", action="store_true")
    ap.add_argument("--tbl-dir", action="append", type=Path, help="directory with the three .tbl files (repeatable, later wins per file)")
    ap.add_argument("--d2r-lng", type=Path, default=D2R_LNG, help="D2R data/local/lng folder (default: env D2R_LNG or extract/d2r/93847/...)")
    ap.add_argument("--excel-dir", type=Path, help="the mod's data/global/excel: short aliases are planned only for keys the limited "
                    "columns (uniqueitems / setitems index, levels LevelWarp) really use; without it every long key gets one")
    args = ap.parse_args()
    d2r_lng = args.d2r_lng
    out_dir = OUT

    by_id, winner = load_median(args.tbl_dir)
    idkeys = {sid: final_key(sid, key) for sid, (key, _t) in by_id.items()}
    texts: dict[str, str] = {}
    for sid, (key, text) in by_id.items():
        fk = idkeys[sid]
        if fk.startswith("mxl_") or winner[key] == sid:
            texts[fk] = text
    shadowed = sum(1 for sid, (key, _t) in by_id.items() if not idkeys[sid].startswith("mxl_") and winner[key] != sid)

    # sanity: the .tbl parse must agree with the first extraction (key<TAB>text, newlines written as \n)
    old_dir = ROOT / "assets" / "mxl2012" / "2_txt" / "strings"
    agree = 0
    for name, base in TABLES:
        if not (old_dir / f"{name}.txt").exists():
            continue  # the first extraction sits outside the repo (absent in agent worktrees)
        for i, line in enumerate((old_dir / f"{name}.txt").read_text("utf-8").splitlines()):
            key, _, old = line.partition("\t")
            agree += (key, old.replace("\\n", "\n")) == by_id[base + i]

    report = ["# tbl2json report", "",
              f"- Median strings: {len(by_id)} (string {sum(1 for s in by_id if s < 10000)}, patchstring "
              f"{sum(1 for s in by_id if 10000 <= s < 20000)}, expansionstring {sum(1 for s in by_id if s >= 20000)})",
              f"- Keys given an ID-based name (\"x\" or empty): {sum(1 for k in idkeys.values() if k.startswith('mxl_'))}",
              f"- Duplicate keys resolved (patch > expansion > string): {shadowed} entries shadowed",
              f"- Agreement with the first extraction: " + (f"{agree}/{len(by_id)} strings identical" if agree else "not checked"),
              f"- Languages: {'enUS only' if args.english_only else 'English text in all 13 languages'}"]

    folders = {f: {p.name: json.loads(p.read_text("utf-8-sig")) for p in sorted((d2r_lng / f).glob("*.json"))}
               for f in ("strings", "strings-legacy") if (d2r_lng / f).exists()}
    d2r_keys = {e["Key"] for files in folders.values() for recs in files.values() for e in recs}
    # What the loader knows as `d2r:<key>`: the records of D2R's strings/ files (a few keys exist in strings-legacy/ only).
    # A key may repeat in D2R's own files (126 do); an override has to agree with every record.
    loaded: dict[str, list[dict]] = {}
    for recs in folders["strings"].values():
        for e in recs:
            loaded.setdefault(e["Key"], []).append(e)

    # Group 2 = Median-only keys (not in D2R's files): namespaced, no numeric IDs (docs/strings-namespace.md). A native
    # exception (fixed numeric ID) cannot exist any more: with the mod's namespace on, an unqualified record defines
    # `mxl2012:<key>` and its id is ignored. A key that does not fit a fixed-size cell gets a short alias (txt_migrate).
    exceptions = sorted(load_exceptions())
    if exceptions:
        raise SystemExit(f"tbl2json: native exceptions are not possible with a mod namespace (an unqualified record "
                         f"is a mxl2012: record, its id is ignored): {exceptions}")
    # Keys the tables name that no .tbl defines get the text the text lane wrote for them (a name in words, a tooltip line), and
    # Median's own texts that read like a key are replaced (data/string_gaps.tsv, docs/tables-status.md, docs/text-audit.md)
    raw_keys = {k: t for k, t in string_gaps.texts().items() if k not in texts and k not in d2r_keys}
    texts.update(raw_keys)
    fixed = string_gaps.fixes()
    absent = sorted(k for k in fixed if k not in texts or k in d2r_keys)
    if absent:
        raise SystemExit(f"tbl2json: string_gaps `fix` rows name keys Median's tbl does not define (or D2R owns): {absent}")
    texts.update(fixed)
    # colour codes D2R cannot draw -> the colour it draws (strings_ns.COLOUR_MAP, bug #398: Median's `ÿc/` printed as "*/")
    colour_mapped = Counter(m.group(1) for t in texts.values() for m in strings_ns.COLOUR_CODE.finditer(t)
                            if m.group(1) in strings_ns.COLOUR_MAP)
    colour_texts = sum(1 for t in texts.values() if strings_ns.map_colours(t) != t)
    colour_eol = sum(len(strings_ns.EOL_COLOUR.findall(t)) for t in texts.values())
    texts = {k: strings_ns.map_colours(t) for k, t in texts.items()}
    # misc spelldesc 2 texts without a placeholder: `<key>_val` draws the value after them, as 1.13c (bug #490, strings_ns)
    value_alias = {}
    for k in sorted(strings_ns.spell_value_keys(args.excel_dir)):
        if k in texts and k not in d2r_keys and not placeholders(texts[k]):
            texts[k + strings_ns.VALUE_SUFFIX] = strings_ns.spell_value_text(texts[k])
            value_alias[k] = k + strings_ns.VALUE_SUFFIX
    group2 = [k for k in texts if k not in d2r_keys]

    def lang_rec(k: str) -> dict:
        return {lang: texts[k] if (lang == "enUS" or not args.english_only) else "" for lang in LANGS}

    # Group 1 = Median's text for keys D2R has: one `d2r:<key>` record per key in OVERRIDE_FILE (loader contract:
    # LOCALIZATION.md "Replace existing text"). Not written: keys whose text does not change, keys whose printf
    # placeholders differ from D2R's (bug #12), keys the loader does not know (only in strings-legacy/).
    langs = ["enUS"] if args.english_only else LANGS
    overrides, kept, same, legacy_only = [], {}, 0, []
    for k in texts:
        if k not in d2r_keys:
            continue
        recs = loaded.get(k)
        if recs is None:
            legacy_only.append(k)
            continue
        t = texts[k]
        if any(placeholders(t) != placeholders(e.get("enUS", "")) for e in recs):
            kept[k] = (recs[0].get("enUS", ""), t)
            continue
        if all(e.get(lang, t) == t for e in recs for lang in langs):
            same += 1
            continue
        overrides.append({"Key": f"{D2R_PREFIX}{k}", **{lang: t for lang in langs}})
    # A kept key cannot carry Median's text (the game formats the key itself with D2R's placeholders). The item property
    # lines still need Median's wording, so each kept key also gets a Median-only alias `<key>_mxl` (txt_migrate points the
    # itemstatcost string cells at it).
    for k, (_d, m) in sorted(kept.items()):
        texts[k + ALIAS_SUFFIX] = m
        group2.append(k + ALIAS_SUFFIX)
    for sid, d2r_key, fmt in ID_PAIRS:
        t = fmt.format(by_id[sid][1])
        recs = loaded.get(d2r_key)
        if recs and any(e.get("enUS", "") != t for e in recs) and all(placeholders(t) == placeholders(e.get("enUS", "")) for e in recs):
            overrides.append({"Key": f"{D2R_PREFIX}{d2r_key}", **{lang: t for lang in langs}})
    group1 = len({k for k in texts if k in d2r_keys})
    report.insert(2, f"- {len(raw_keys)} keys the tables name that no .tbl defines, given a text of their own, and {len(fixed)} Median texts replaced (data/string_gaps.tsv)")
    report.insert(2, f"- Groups: {group1} group 1 (D2R keys), {len(group2)} group 2 (`{NAMESPACE}:` namespace)")
    aliases = strings_ns.plan_aliases(strings_ns.overflowing_keys(group2, args.excel_dir))
    for k, a in aliases.items():  # alias records: the long key's texts under `mxlname_<n>` (Median-only, group 2)
        texts[a] = texts[k]
        group2.append(a)
    base = out_dir / "data" / "local" / "lng"
    shutil.rmtree(base / "strings", ignore_errors=True)
    shutil.rmtree(base / "strings-legacy", ignore_errors=True)
    # D2R's own files are not shipped: they load from the game. The mod's folder holds only the override file and the
    # namespace file. strings-legacy/ gets a mirror of the namespace file only, as before (docs/strings.md
    # "strings-legacy"): the overrides are not mirrored, a `d2r:` record there would repeat a key of the other folder.
    write_json(base / "strings" / NAMESPACE / OVERRIDE_FILE, overrides)
    median = [{"Key": k, **lang_rec(k)} for k in group2]
    write_json(base / "strings" / NAMESPACE / NAMESPACE_FILE, median)
    write_json(base / "strings-legacy" / NAMESPACE / NAMESPACE_FILE, median)
    report += [f"- {len(overrides)} D2R keys overridden (`{D2R_PREFIX}<key>` records in {NAMESPACE}/{OVERRIDE_FILE}, one per key, "
               f"{'enUS only' if args.english_only else '13 languages'})",
               f"- {same} D2R keys skipped: Median's text equals D2R's",
               f"- {len(kept)} D2R keys skipped, kept D2R's text (printf placeholders differ, bug #12)",
               f"- {len(legacy_only)} D2R keys skipped: only in strings-legacy/, the loader does not know `d2r:<key>` for them",
               f"- {len(group2)} Median-only keys in {NAMESPACE}/{NAMESPACE_FILE} (group 2)",
               f"- {len(value_alias)} misc spelldesc 2 texts given `<key>{strings_ns.VALUE_SUFFIX}` with the value after them (bug #490): "
               + (", ".join(sorted(value_alias)) or "none")]
    report += [f"  - kept `{k}`: D2R {d!r} / Median {m!r}" for k, (d, m) in sorted(kept.items())]
    report += [f"  - not loaded `{k}`: {texts[k]!r}" for k in sorted(legacy_only)]

    # (planned and added to group 2 above, before the files were written.) Short aliases for keys that do not fit a fixed-size cell (uniqueitems / setitems index 31, levels LevelWarp 39:
    # the whole `mxl2012:<key>` must fit). Alias records carry the long key's texts, the long key stays defined.
    long_keys = sorted(k for k in group2 if len(strings_ns.PREFIX + k) > min(strings_ns.CELL_LIMITS.values()))
    report += [f"- {len(aliases)} short aliases `{strings_ns.ALIAS_PREFIX}<n>` for keys that overflow "
               + ", ".join(f"{c} ({n})" for c, n in strings_ns.CELL_LIMITS.items())
               + (" (planned from --excel-dir usage)" if args.excel_dir else " (no --excel-dir: every key over the smallest limit)"),
               f"- {len(long_keys)} group 2 keys whose `{strings_ns.PREFIX}<key>` is longer than {min(strings_ns.CELL_LIMITS.values())}"]
    report += [f"  - alias `{a}` = {k!r} ({len(strings_ns.PREFIX + k)} chars)" for k, a in sorted(aliases.items(), key=lambda x: x[1])[:60]]
    fold = {}
    for k in d2r_keys:
        fold.setdefault(k.lower(), []).append(k)
    case_clash = sorted(k for k in group2 if k.lower() in fold and k not in d2r_keys)
    report.append(f"- {len(case_clash)} group 2 keys equal a D2R key apart from case (D2R looks keys up case-insensitively; "
                  f"table cells are always qualified, see strings_map.json `case_clash`)")
    report += [f"  - {k!r} ~ {fold[k.lower()]}" for k in case_clash[:30]]
    report.append(f"- Strings read as cp1252 because they are not valid UTF-8: {len(FALLBACK)}"
                  + (f" (e.g. {FALLBACK[0][:60]!r})" if FALLBACK else ""))
    report.append(f"- U+FFFD (undecodable byte) in a text: {sum(1 for t in texts.values() if chr(0xFFFD) in t)}")
    report.append(f"- Colour codes (ÿc<char>) in {sum(1 for t in texts.values() if 'ÿc' in t)} texts; texts starting with a "
                  f"VO number line (digits then LF; D2R's own copy has the number but no line breaks): "
                  f"{sum(1 for t in texts.values() if re.match(r'\d+\n', t))}")
    report.append(f"- Colour codes changed in {colour_texts} texts: codes that end a line moved behind the line break {colour_eol}; "
                  "codes D2R cannot draw mapped (strings_ns.COLOUR_MAP): "
                  + (", ".join(f"`ÿc{c}` -> `ÿc{strings_ns.COLOUR_MAP[c]}` {n}" for c, n in sorted(colour_mapped.items())) or "none")
                  + f"; left that D2R cannot draw: {sum(1 for t in texts.values() if strings_ns.bad_colours(t))} texts")
    report.append(f"- Group 2 keys with leading/trailing space: {[k for k in group2 if k != k.strip()]}")
    nonascii = sorted({c for t in texts.values() for c in t if ord(c) > 127})
    report.append("- Non-ASCII characters in the texts: " + " ".join(f"U+{ord(c):04X}" for c in nonascii))

    # strings_idkeys.json: Median ID -> full key. Group 2 gets the namespace prefix; group 1 stays plain.
    g2 = set(group2)
    idkeys = {sid: (f"{NAMESPACE}:{k}" if k in g2 else k) for sid, k in idkeys.items()}
    (out_dir / "strings_namespace.json").write_text(
        json.dumps({"namespace": NAMESPACE, "keys": group2}, ensure_ascii=False, indent=0), encoding="utf-8")

    (out_dir / "strings_idkeys.json").write_text(json.dumps({str(k): v for k, v in sorted(idkeys.items())}, indent=0),
                                             encoding="utf-8")
    # strings_map.json: what the tables lane reads (docs/strings.md "strings_map.json")
    (out_dir / "strings_map.json").write_text(json.dumps({
        "namespace": NAMESPACE, "prefix": NAMESPACE + ":", "limits": strings_ns.CELL_LIMITS,
        "group2": {k: f"{NAMESPACE}:{k}" for k in sorted(g2)},
        "aliases": aliases, "case_clash": case_clash,
        "kept_alias": {k: k + ALIAS_SUFFIX for k in sorted(kept)},
        "value_alias": value_alias,
        "id_keys": {str(k): v for k, v in sorted(idkeys.items())}}, ensure_ascii=False, indent=0), encoding="utf-8")
    (out_dir / "strings_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
