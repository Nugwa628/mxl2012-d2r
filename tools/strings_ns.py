"""The `mxl2012` string namespace for the table and layout tools (docs/strings-namespace.md).

Group 1 = keys D2R's own string files have (unqualified in table cells = `d2r:`; Median's text for them is a `d2r:<key>`
record in `strings/mxl2012/overrides.json`); group 2 = Median-only keys (namespaced, `mxl2012:<key>` in table cells,
`@mxl2012:<key>` in HD layouts). A key is group 2 when it is not in D2R's string files
(extract/d2r/93847/data/local/lng/{strings,strings-legacy}/*.json). D2R's own files are not part of the mod.

  d2r_keys()             every key of D2R's own string files (the group 1 set)
  load_group2()          group 2 keys: work/mod/strings_namespace.json (tbl2json) when it exists, else computed the same way
  d2r_loaded()           key -> records of D2R's strings/ files (the keys the loader knows as `d2r:<key>`)
  overrides()            the mod's `d2r:<key>` override records, by bare key
  effective_texts(lang)  bare key -> displayed text (D2R's, the override's, or the Median-only key's)
  native_exceptions()    the keys of tools/strings_native.json (must be empty)
  is_localization(t, c)  True if column c of table t holds a string key (LOCALIZATION below)
  qualify(ref, group2)   table / JSON reference as written: `mxl2012:<key>` for group 2, anything else unchanged
  plan_aliases / load_aliases / write_aliases / qualify_reference / is_reference
                         short aliases `mxlname_<n>` for keys that do not fit a fixed-size cell (see below)
  split_key(ref)         ('mxl2012', key) / (None, ref)
  bare(ref)              `mxl2012:<key>` -> `<key>`
  qualify_layout(...)    every `@key` of a layout
  map_colours(text)      Median's colour codes D2R cannot draw -> the colour D2R draws (COLOUR_MAP, docs/strings.md "Colour codes")
  bad_colours(text)      the colour code characters of a text that D2R cannot draw (text_audit kind `colour-code`)
  map_colours also moves a code that ends a line behind the line break (D2R drops it there)
"""
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAMESPACE = "mxl2012"
PREFIX = NAMESPACE + ":"
D2R_LNG = Path(os.environ.get("D2R_LNG") or ROOT / "extract" / "d2r" / "93847" / "data" / "local" / "lng")
NAMESPACE_FILE = ROOT / "work" / "mod" / "strings_namespace.json"
EXCEPTIONS_FILE = ROOT / "tools" / "strings_native.json"
OVERRIDE_FILE = "overrides.json"
D2R_PREFIX = "d2r:"
MOD_STRINGS = ROOT / "work" / "mod" / "data" / "local" / "lng" / "strings"
ALIAS_FILE = ROOT / "work" / "mod" / "strings_alias.json"
ALIAS_PREFIX = "mxlname_"
LNG = ROOT / "work" / "mod" / "data" / "local" / "lng"

NUMERIC = re.compile(r"-?\d+(\.\d+)?")

# Colour codes `ÿc<char>` (ÿ = U+00FF; docs/strings.md "Colour codes", bug #398). 1.13c's text colour is <char> - '0' into a
# table of 13 (PL2 text colours, '0'..'<'); D2R draws the codes below (0-9 : ; are 1.13c's, M and U are D2R's own, used by its
# strings) and prints any other code as text ("*/" in HD, "Ø/" in classic). COLOUR_MAP maps Median's other codes to one D2R
# draws: `ÿc/` (721 times in 710 texts, mostly the first word of a skill's long description and the text after a red / blue
# requirement line) is colour -1 in 1.13c, a read in front of the table (not a colour of its own: in DirectDraw a dark
# brown-red, in other renderers whatever precedes the table); Median uses it as "back to the description's colour", so it
# becomes white `ÿc0`, the colour of an uncoloured description line.
# A colour holds across line breaks in both games, but D2R drops a code that ends a line (the line after "ÿc1requires a
# crossbowÿc/\n" stays red), where 1.14d's drawer 0x501a80 applies it to the next line; map_colours moves such codes behind the
# line breaks that follow (EOL_COLOUR: 139 Median texts, 132 of them `ÿc/`).
COLOUR_CODE = re.compile("ÿc(.)", re.S)
EOL_COLOUR = re.compile("((?:ÿc[^\n])+)(\n+)")
D2R_COLOURS = frozenset("0123456789:;MU")
COLOUR_MAP = {"/": "0"}


def map_colours(text: str) -> str:
    text = COLOUR_CODE.sub(lambda m: "ÿc" + COLOUR_MAP.get(m.group(1), m.group(1)), text)
    return EOL_COLOUR.sub(lambda m: m.group(2) + m.group(1), text)


def bad_colours(text: str) -> list[str]:
    """Colour code characters D2R cannot draw, in order. A text that ends in a bare `ÿc` counts as "", except the text `ÿc`
    itself (string 3994 `colorcode`, which the game's code completes with a colour character)."""
    bad = [m.group(1) for m in COLOUR_CODE.finditer(text) if m.group(1) not in D2R_COLOURS]
    return bad + ([""] if text.endswith("ÿc") and text != "ÿc" else [])


# Localization columns per table, lower case. Source: D2R's data guide (global/dataguide/data/files/*.js) fields typed
# `string`, plus the text fields whose description says "string key" (hireling, lowqualityitems, objects, rareprefix,
# raresuffix, runes, setitems, uniqueitems), the affix names (magicprefix/magicsuffix/automagic/unique*, stored in a
# fixed-size field, LOCALIZATION.md) and levels LevelName / LevelWarp / LevelEntry (the guide types them `text`
# but describes them as string fields). armor / weapons / misc share namestr through shareditems. Median's levels
# column EntryFile (leftover bytes of the .bin) is not mapped to LevelEntry, so it never reaches the output.
LOCALIZATION = {
    "armor": {"namestr"},
    "weapons": {"namestr"},
    "misc": {"namestr", "spelldescstr", "spelldescstr2"},
    "automagic": {"name"},
    "magicprefix": {"name"},
    "magicsuffix": {"name"},
    "rareprefix": {"name"},
    "raresuffix": {"name"},
    "uniqueprefix": {"name"},
    "uniquesuffix": {"name"},
    "uniqueappellation": {"name"},
    "uniqueitems": {"index"},
    "setitems": {"index"},
    "sets": {"name"},
    "runes": {"name"},
    "lowqualityitems": {"name"},
    "charstats": {"strallskills", "strskilltab1", "strskilltab2", "strskilltab3", "strclassonly"},
    "hireling": {"hiredesc", "namefirst", "namelast"},
    "itemstatcost": {"descstrpos", "descstrneg", "descstr2", "dgrpstrpos", "dgrpstrneg", "dgrpstr2"},
    "levelgroups": {"namestring"},
    "levels": {"levelname", "levelwarp", "levelentry"},
    "monstats": {"namestr", "descstr"},
    "montype": {"strplur"},
    "objects": {"name"},
    "pettype": {"name", "overridename1", "overridename2", "overridename3", "overridename4"},
    "shrines": {"stringname", "stringphrase"},
    "skilldesc": {"str name", "str short", "str long", "str alt", "item proc text",
                  *(f"{p}{c}{n}" for p, rng in (("desctext", 6), ("dsc2text", 5), ("dsc3text", 7)) for c in "ab"
                    for n in range(1, rng + 1))},
    "superuniques": {"name"},
}
# Columns that name a string key but are read as a numeric range (hireling NameFirst..NameLast: every ID from the first
# to the last is a name). A qualified key gets a loader-assigned number, so the range could not follow it: these stay
# native (group 1); txt_migrate skips them and validate.py fails if one names a group 2 key.
RANGE_COLUMNS = {"hireling": {"namefirst", "namelast"}}


# Localization columns whose value is never displayed, so a value that is no string key is no finding: automagic affixes
# are applied "regardless of the item's quality ... without changing the item's name" (D2R's data guide, automagic.js);
# Median fills the column with labels ("InnateAreaEffect", "Angelic 1H") that its own string tables lack as well.
LABEL_COLUMNS = {"automagic": {"name"}}
# Placeholder rows (value never shown): objects.Name `dummy_<n>`.
PLACEHOLDER_VALUES = {("objects", "name"): re.compile(r"dummy_\d+")}


# Skill tooltip line types (skilldesc descline / dsc2line / dsc3line) whose text cells D2R's line renderer (0x287a50, jump table
# 0x289f88) uses as a printf format; every other type of 1.13c's 1-73 appends text A / B, the number and a unit as 1.13c did
# (bug #396). D2R's own types 76-79 format both texts.
SKILLDESC_FORMAT = {13: "A", 34: "A", 36: "AB", 40: "A", 53: "A", 54: "A", 55: "A", 56: "A", 66: "A", 74: "A", 75: "A"}
# Types whose label D2R hard-codes and appends, while D2R rewrote the label's text as a printf format ("Fire Damage: %d-%d"
# for 1.13c's "Fire Damage: "): no cell of the row changes it. type -> the labels (keys of D2R's strings).
SKILLDESC_FIXED_LABELS = {9: ("StrSkill4",), 10: ("StrSkill4", "StrSkill5", "StrSkill6", "StrSkill7", "StrSkill8", "StrSkill39"),
                          11: ("StrSkill13",), 14: ("StrSkill5", "StrSkill6", "StrSkill7", "StrSkill8", "StrSkill39", "StrSkill20"),
                          22: ("StrSkill5", "StrSkill6", "StrSkill7", "StrSkill8", "StrSkill39", "StrSkill34"),
                          25: ("StrSkill7", "StrSkill34"),
                          27: ("StrSkill5", "StrSkill34"), 28: ("StrSkill18",)}
SKILLDESC_GROUPS = (("descline", "desc", 6), ("dsc2line", "dsc2", 5), ("dsc3line", "dsc3", 7))


def skilldesc_format(kind: int) -> str:
    """The text slots ("A", "B") that line type `kind` uses as a printf format in D2R."""
    return SKILLDESC_FORMAT.get(kind, "AB" if kind > 75 else "")


def is_label_column(table: str, column: str) -> bool:
    return column.lower() in LABEL_COLUMNS.get(table.lower(), ())


def is_placeholder(table: str, column: str, value: str) -> bool:
    rx = PLACEHOLDER_VALUES.get((table.lower(), column.lower()))
    return bool(rx and rx.fullmatch(value))


def is_localization(table: str, column: str) -> bool:
    return column.lower() in LOCALIZATION.get(table.lower(), ())


def is_range_column(table: str, column: str) -> bool:
    return column.lower() in RANGE_COLUMNS.get(table.lower(), ())


def d2r_keys() -> set[str]:
    """Every key of D2R's string files, both folders (the group 1 set)."""
    return {e["Key"] for f in ("strings", "strings-legacy") if (D2R_LNG / f).exists()
            for p in (D2R_LNG / f).glob("*.json") for e in json.loads(p.read_text("utf-8-sig"))}


def d2r_loaded() -> dict[str, list[dict]]:
    """key -> its records in D2R's strings/ files: what the loader knows as `d2r:<key>` (a key can repeat in D2R's own
    files). Keys that exist only in strings-legacy/ are not in it."""
    out: dict[str, list[dict]] = {}
    for p in sorted((D2R_LNG / "strings").glob("*.json")):
        for e in json.loads(p.read_text("utf-8-sig")):
            out.setdefault(e["Key"], []).append(e)
    return out


def overrides() -> dict[str, dict]:
    """bare key -> record of the mod's `d2r:<key>` overrides (work/mod/.../strings/mxl2012/overrides.json)."""
    p = MOD_STRINGS / NAMESPACE / OVERRIDE_FILE
    if not p.exists():
        return {}
    return {e["Key"][len(D2R_PREFIX):]: e for e in json.loads(p.read_text("utf-8-sig")) if e["Key"].startswith(D2R_PREFIX)}


def effective_texts(lang: str = "enUS") -> dict[str, str]:
    """bare key -> the text the player reads: D2R's strings/ text, replaced by the mod's override, plus the
    Median-only keys of mxl2012/median.json (a key has one text; D2R and Median-only key sets do not overlap)."""
    out = {k: recs[0].get(lang, "") for k, recs in d2r_loaded().items()}
    out.update({k: e[lang] for k, e in overrides().items() if lang in e})
    p = MOD_STRINGS / NAMESPACE / "median.json"
    if p.exists():
        out.update({e["Key"]: e.get(lang, "") for e in json.loads(p.read_text("utf-8-sig"))})
    return out


def native_exceptions() -> set[str]:
    """tools/strings_native.json. Must stay empty: with a mod namespace an unqualified record is a `mxl2012:` record
    and its id is ignored, so no string can be native with a fixed id (validate.py fails otherwise)."""
    return set(json.loads(EXCEPTIONS_FILE.read_text("utf-8"))["keys"]) if EXCEPTIONS_FILE.exists() else set()


def load_group2() -> set[str]:
    """Median-only keys that need the `mxl2012:` prefix."""
    if NAMESPACE_FILE.exists():
        return set(json.loads(NAMESPACE_FILE.read_text("utf-8"))["keys"])
    # Not written yet (tbl2json has not run): the keys of the namespace file
    p = MOD_STRINGS / NAMESPACE / "median.json"
    return {e["Key"] for e in json.loads(p.read_text("utf-8-sig"))} if p.exists() else set()


def qualify(ref: str, group2: set[str], aliases: dict[str, str] | None = None) -> str:
    """Table / JSON reference to a key: `mxl2012:<key>` for group 2 (`mxl2012:<alias>` for a key with a short alias,
    see load_aliases); empty cells, group 1 keys, native exceptions and already qualified references stay as they
    are. A number is a key like any other: Median's item names are keys such as `704` (group 2), and an unqualified
    `704` would name `d2r:704`, which does not exist (the item shows "an evil force")."""
    if not ref or ref.startswith(PREFIX) or ref not in group2:
        return ref
    return PREFIX + (aliases if aliases is not None else load_aliases()).get(ref, ref)


# ---- short aliases for keys that do not fit a fixed-size field ----------------------------------------------------
# uniqueitems.index and setitems.index (31 characters) and levels.LevelWarp (39) store the key in the cell itself, so
# the whole `mxl2012:<key>` must fit. A Median-only key that does not ("Sunstone of the Twin Seas") gets a short
# alias `mxlname_<n>`: txt_migrate decides which keys (plan_aliases), writes the alias map (work/mod/strings_alias.json),
# adds an alias record with the same 13 texts to the namespace files (write_aliases) and writes the alias in every
# cell that names the key (localization and reference cells alike, as `mxl2012:<alias>`). The long key stays defined as well (the plugin and idkeys use it).

# Fixed-size cells that hold the whole `mxl2012:<key>`: table.column (lower case) -> characters (D2R's dataLength).
CELL_LIMITS = {"uniqueitems.index": 31, "setitems.index": 31, "levels.levelwarp": 39}


def cell_value(table: str, column: str, key: str, group2, aliases: dict[str, str]) -> str:
    """The cell text for a key in table.column: qualified (`mxl2012:<key>`) for group 2, the short alias when the
    qualified key is longer than the column's limit (KeyError when the alias map lacks it), anything else (group 1) unchanged."""
    if key not in group2 or key.startswith(PREFIX):
        return key
    limit = CELL_LIMITS.get(f"{table.lower()}.{column.lower()}")
    full = PREFIX + key
    if limit and len(full) > limit:
        if key not in aliases:
            raise KeyError(f"{full!r} is {len(full)} chars, {table}.{column} holds {limit}, and the key has no alias")
        return PREFIX + aliases[key]
    return full


def overflowing_keys(group2, excel_dir) -> set[str]:
    """Group 2 keys whose `mxl2012:<key>` does not fit a limited cell. With the mod's excel folder: only keys the limited
    columns really hold (and, as references, cubemain / treasureclassex cells name them; those follow the index cell, so
    the index decides). Without it: every key longer than its smallest limit."""
    if excel_dir is None:
        small = min(CELL_LIMITS.values())
        return {k for k in group2 if len(PREFIX + k) > small}
    out = set()
    for tc, limit in CELL_LIMITS.items():
        table, col = tc.split(".")
        path = Path(excel_dir) / f"{table}.txt"
        if not path.exists():
            continue
        lines = path.read_text("cp1252", errors="replace").splitlines()
        head = [h.strip().lower() for h in lines[0].split("	")]
        ci = head.index(col)
        for ln in lines[1:]:
            cells = ln.split("	")
            if ci < len(cells) and cells[ci] in group2 and len(PREFIX + cells[ci]) > limit:
                out.add(cells[ci])
    return out


# misc.txt spelldesc 2 (bug #490): 1.13c drew spelldescstr, a space (string 3995) and the spelldesccalc value (1.14d Game.exe
# 0x486411: append the text, "%ld" of the value, append string 3995, the number, newline 3998); D2R formats spelldescstr with
# the value as printf (its own ItemStats1q is "Points: %d"), so a Median text without a placeholder ("Right-click: Gold in Bank:")
# shows no number. Such a key gets a Median-only text `<key>_val` = the text, " %d" (tbl2json), and the cells name it (txt_migrate).
SPELLDESC_VALUE_KINDS = ("2",)
VALUE_SUFFIX = "_val"


def spell_value_text(text: str) -> str:
    """The printf format that draws what 1.13c drew for a spelldesc 2 text: the text (a literal "%" doubled), a space, the value."""
    return text.replace("%", "%%") + " %d"


def spell_value_keys(excel_dir) -> set[str]:
    """spelldescstr keys of the misc.txt rows whose spelldesc appends the value in 1.13c (SPELLDESC_VALUE_KINDS)."""
    path = Path(excel_dir) / "misc.txt" if excel_dir is not None else None
    if path is None or not path.exists():
        return set()
    lines = path.read_text("cp1252", errors="replace").splitlines()
    head = [h.strip().lower() for h in lines[0].split("\t")]
    kind, key = head.index("spelldesc"), head.index("spelldescstr")
    out = set()
    for ln in lines[1:]:
        cells = ln.split("\t")
        if max(kind, key) < len(cells) and cells[kind].strip() in SPELLDESC_VALUE_KINDS and cells[key]:
            out.add(cells[key])
    return out


def plan_aliases(keys) -> dict[str, str]:
    """key -> alias for the given keys, numbered 1.. in key order (deterministic for the same set)."""
    return {k: f"{ALIAS_PREFIX}{n}" for n, k in enumerate(sorted(set(keys)), 1)}


def load_aliases() -> dict[str, str]:
    """key -> alias, as written by txt_migrate (empty when the file does not exist)."""
    return json.loads(ALIAS_FILE.read_text("utf-8"))["aliases"] if ALIAS_FILE.exists() else {}


# Columns that name a unique / set item by its index (cubemain input / output, treasureclassex Item#). The engine
# matches the name against the item's index cell, which reads `mxl2012:<key>` for a Median-only name, so the
# reference must read the same (an unqualified `HotTJ` names no unique item: the recipe's input matches anything and
# the wrong recipe fires, a treasure class entry drops nothing).
REFERENCE_COLUMNS = {"cubemain": re.compile(r"input \d|output( [bc])?"), "treasureclassex": re.compile(r"Item\d+")}


def is_reference(table: str, column: str) -> bool:
    rx = REFERENCE_COLUMNS.get(table.lower())
    return bool(rx and rx.fullmatch(column))


def qualify_reference(cell: str, names: set[str], aliases: dict[str, str]) -> str:
    """A cell that names a unique / set item by index (cubemain input / output, treasure class item, with optional
    quotes and a `,qty=2` suffix): `mxl2012:<key>` (`mxl2012:<alias>` for a key with a short alias) when the name is
    one of `names` (the Median-only indexes of uniqueitems / setitems), else unchanged."""
    quoted = len(cell) > 1 and cell[0] == cell[-1] == '"'
    name, sep, rest = (cell[1:-1] if quoted else cell).partition(",")
    if name not in names:
        return cell
    body = PREFIX + aliases.get(name, name) + sep + rest
    return f'"{body}"' if quoted else body


def reference_name(cell: str) -> str:
    """The item name of a reference cell (quotes and `,modifier` suffix removed)."""
    return cell.strip().strip('"').partition(",")[0]


def write_aliases(aliases: dict[str, str], group2=None) -> None:
    """Write the alias map and the alias records (same texts as the long key) into median.json of both string
    folders and strings_namespace.json. Idempotent: earlier alias records are replaced."""
    ALIAS_FILE.write_text(json.dumps({"namespace": NAMESPACE, "aliases": aliases}, ensure_ascii=False, indent=0),
                          encoding="utf-8")
    for folder in ("strings", "strings-legacy"):
        path = LNG / folder / NAMESPACE / "median.json"
        if not path.exists():
            continue
        recs = [e for e in json.loads(path.read_text("utf-8-sig")) if not e["Key"].startswith(ALIAS_PREFIX)]
        by_key = {e["Key"]: e for e in recs}
        recs += [{**by_key[k], "Key": a} for k, a in aliases.items()]
        path.write_text("﻿" + json.dumps(recs, ensure_ascii=False, indent=2).replace("\n", "\r\n"),
                        encoding="utf-8", newline="")
    ns = json.loads(NAMESPACE_FILE.read_text("utf-8"))
    ns["keys"] = [k for k in ns["keys"] if not k.startswith(ALIAS_PREFIX)] + list(aliases.values())
    NAMESPACE_FILE.write_text(json.dumps(ns, ensure_ascii=False, indent=0), encoding="utf-8")


def split_key(ref: str) -> tuple[str | None, str]:
    """('mxl2012', 'Key') for 'mxl2012:Key', (None, ref) for an unqualified cell. Other namespaces (d2r:,
    d2rloader:) are returned as written."""
    if ":" in ref:
        ns, key = ref.split(":", 1)
        if ns and re.fullmatch(r"[A-Za-z0-9_.-]+", ns):
            return ns, key
    return None, ref


def bare(ref: str) -> str:
    """`mxl2012:<key>` -> `<key>` (lookups in median.json); other values unchanged."""
    return ref[len(PREFIX):] if ref.startswith(PREFIX) else ref


_REF = re.compile(r"@(?![A-Za-z0-9_]+:[A-Za-z0-9_])([A-Za-z0-9_]+)")


def qualify_layout(text: str, group2: set[str], native: set[str]) -> str:
    """Qualify every `@key` of a layout (JSON text): `@mxl2012:<key>` for group 2, `@d2r:<key>` for D2R's own keys.
    With the mod's namespace active an unqualified `@key` means the mod's own strings (LOCALIZATION.md: copied native
    layouts must qualify the native text they retain with `d2r:`). Already qualified references and unknown keys stay."""
    def sub(m: re.Match) -> str:
        k = m.group(1)
        if k in group2:
            return f"@{PREFIX}{k}"
        return f"@d2r:{k}" if k in native else m.group(0)
    return _REF.sub(sub, text)
