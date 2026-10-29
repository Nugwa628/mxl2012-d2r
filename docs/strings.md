# Strings: tbl2json (Median XL 2012 -> D2R 3.3)

Tools: `tools/tbl2json.py` (reads the mod's `.tbl` files, writes `work/mod/`, gitignored), `tools/strings_ns.py` (shared
helpers), `tools/strings_check.py` (validator), `tools/test_strings.py`. Namespace `mxl2012`; the changes are listed at the end. The design: D2RLoader string
namespace, group 1 / group 2.

```
py -3 -I tools/tbl2json.py --tbl-dir <extract-merged>/data/local/lng/eng --excel-dir <extract-merged>/data/global/excel
py -3 -I tools/strings_check.py --excel-dir <...>/data/global/excel            # raw tables: missing keys
py -3 -I tools/strings_check.py --excel-dir <rewritten tables> --rewritten    # after the tables lane's rewrite
py -3 -I tools/test_strings.py
```
`--d2r-lng` / env `D2R_LNG` = D2R 93847's `data/local/lng` (`extract/d2r/93847/data/local/lng` by default).

## Source

Median XL 2012 v005 is classic 1.13c. Its strings are the three tables of `patch_d2.mpq` (`data\local\lng\eng\`): 22,977 strings
(string 8,811, patchstring 4,325, expansionstring 9,841). The ids are what the game uses (string index, patchstring +10000,
expansionstring +20000). Text is UTF-8 in the `.tbl` files; all of it decodes as UTF-8 (0 cp1252 fallbacks, 0 U+FFFD). The only
non-ASCII character is `ÿ` (U+00FF), the colour code lead (`ÿc4`), in 4,948 texts; D2R's JSON uses the same `ÿc` form, so it is
written unchanged, except the colour codes D2R cannot draw (next section).

## Colour codes

`ÿc<char>` sets the text colour. 1.13c / 1.14d take the colour as `<char> - '0'` (1.14d's text drawer `0x501a80`: kept when
below 13, signed, else 0) and index the 13 text colours of the act palette (`pal.pl2`: white, red, green, blue, gold, grey,
black, tan, orange, yellow, dark green, purple, bright green = `0`-`9`, `:`, `;`, `<`). D2R draws `0`-`9`, `:`, `;` and letters of
its own (its strings use `ÿcM` and `ÿcU`); any other code is printed as text ("*/" in HD, "Ø/" in classic, bug #398).

Median's tables use `0`-`5`, `7`-`9`, `:`, `;` and `/`. `ÿc/` (721 times in 710 texts: the first word of almost every skill's long
description, the text after a red / blue requirement line, a few item lines) is colour -1: not one of the 13, the drawer reads the
256 bytes in front of the palette's text colour shifts (with DirectDraw a dark brown-red, average glyph colour RGB 74, 34, 21 on
vanilla act 1; other renderers read whatever precedes their table). Median uses it as "back to the description's colour", so
`tbl2json.py` writes it as `ÿc0` (white, the colour of an uncoloured description line). The map is `strings_ns.COLOUR_MAP`
(`/` -> `0`), the codes D2R draws `strings_ns.D2R_COLOURS`; strings_report.md counts the mapped codes, and text_audit kind
`colour-code` fails the build on any text of the mod (Median-only key or `d2r:` override) with a code D2R cannot draw
(docs/text-audit.md). Before: 706 findings; after: 0.

A colour holds across line breaks in both games (1.14d's drawer keeps it at a line feed), but D2R drops a code that ends a
line: in "`ÿc1requires a crossbowÿc/` + line break + `targets a minion, ...`" (Voodoo Shot) the second line stayed red in D2R,
where 1.14d draws it in the code's colour. `strings_ns.map_colours` therefore also moves codes that end a line behind the line
break (`EOL_COLOUR`: 146 codes in 139 texts, 132 of them `ÿc/`, 13 `ÿc0`, 1 `ÿc2`); a code at the very end of a text stays. The
audit kind `colour-code` reports such a code too ("ÿc<char> before a line break").

Not converted: `data\local\LNG\ENG.zip` of the D2SE repack holds three other `.tbl` files (2019, vanilla-style text without
Median's colour codes: "Io Rune" where the MPQ says `ÿc;Io Rune`); it is a zip the game never reads, and `extract-merged`
(loose files over the MPQ) has the MPQ's eng tables unchanged. `--tbl-dir` can be given several times (a later directory
replaces a whole file) should that change. The seven `lng/<lang>/patchstring.tbl` (chi deu esp fra ita kor pol, 1,143 vanilla
patch strings each) are vanilla translations, not Median text; Median is English only, so the English text fills
all 13 languages (`--english-only` writes enUS alone).

## Output (work/mod)

| File | Content |
|---|---|
| `data/local/lng/strings/mxl2012/overrides.json` | group 1: `{"Key": "d2r:<key>", <13 languages>}` without `id`, one per key D2R's `strings/` files have and whose text changes (8,072) |
| `data/local/lng/strings/mxl2012/median.json` (+ mirror in `strings-legacy/mxl2012/`) | group 2: `{"Key", <13 languages>}`, no `id`, full key `mxl2012:<key>` (14,203 incl. 14 aliases and 280 `_mxl` keys) |
| `strings_namespace.json` | `{"namespace", "keys"}` = the group 2 keys |
| `strings_idkeys.json` | Median string id -> final key (`mxl2012:<key>` for group 2, plain key for group 1) |
| `strings_map.json` | what the tables lane reads, below |
| `strings_report.md` | counts, kept keys, aliases, case clashes, encoding facts |

Rules that carry over unchanged: 342 strings with the key `x` or none get `mxl_<id>`; a key in several tables resolves patchstring >
expansionstring > string (669 shadowed); 47 keys whose text equals D2R's get no record; 280 keys whose printf placeholders differ from
D2R's keep D2R's text and Median's wording is under `<key>_mxl` (group 2); `d2r:` keys that exist only in `strings-legacy/` are
skipped (none here).

## `strings_map.json` (for the tables lane)

```json
{
  "namespace": "mxl2012", "prefix": "mxl2012:",
  "limits": {"uniqueitems.index": 31, "setitems.index": 31, "levels.levelwarp": 39},
  "group2":  {"<Median key>": "mxl2012:<Median key>"},
  "aliases": {"<long Median key>": "mxlname_<n>"},
  "case_clash": ["<group 2 keys equal to a D2R key apart from case>"],
  "kept_alias": {"<D2R key kept with D2R's text>": "<key>_mxl"},
  "id_keys": {"<Median string id>": "<final key, qualified for group 2>"}
}
```
Rewriting a table cell that holds a string key (`strings_ns.LOCALIZATION`: namestr, name, index, LevelName, LevelWarp, str name...):

* key not in `group2` (group 1, D2R has it): leave the cell; an unqualified cell means `d2r:`;
* key in `group2`: write `group2[key]` (`mxl2012:<key>`), **except** in a column of `limits` (fixed-size field that must hold the
  whole `namespace:key`) where that is longer than the limit: then write `mxl2012:<aliases[key]>`. The alias record has the same
  texts. `strings_ns.cell_value(table, column, key, group2, aliases)` does all of this and raises `KeyError` for an overflow
  without an alias;
* references to unique / set items by their index (cubemain `input N` / `output`, treasureclassex `Item N`) must read exactly like
  the item's index cell (alias included): `strings_ns.qualify_reference`;
* `kept_alias`: a stat whose description should read Median's wording names `<key>_mxl` (`mxl2012:<key>_mxl`), not the D2R key.

Aliases are planned from the mod's own tables when `--excel-dir` is given (14 keys today, all `uniqueitems` / `setitems` names such
as "MRAchilios' Sledgehammer" or "Cornerstone of the Roflworld"; no `LevelWarp` overflows). Without `--excel-dir` every key whose
qualified form is over 31 characters gets one (897). Re-run tbl2json when the tables change.

## Validator: `strings_check.py`

1. **Output files**: no `id`, no key defined twice (the loader refuses to start), every `d2r:` override names a key D2R's `strings/`
   files have, 13 languages per record, no `:` inside a key, `strings_namespace.json` = `median.json`, aliases defined, `id_keys` resolve.
2. **Missing keys**: every localization cell of every table in `--excel-dir`; a key neither the mod nor D2R defines is `MISSING`
   (exit 1, `--warn-missing` to only report). Case-insensitive like D2R's lookup. With `--rewritten` also errors: an unqualified
   cell naming a group 2 key, an unknown `mxl2012:` / `d2r:` key, a cell longer than its field.

3. **Text audit** (with `--rewritten`; `tools/text_audit.py`, docs/text-audit.md): what the player reads. A cell whose text is a key name, a
   placeholder, "Missing string" or empty on something with art, and any `@key` left in the mod's layouts, is an error, so a new hit fails the
   build. Names no .tbl defines have text in words (`data/string_gaps.tsv`: `text`, `fix` and `cell` rows with a reason; owner decision 2026-10-28).

Result on the MPQ's raw tables: 23,764 cells, **108 cells with a missing key** (data gaps of the mod, not conversion bugs):
`hireling.hiredesc` `carw comb def farw ltng` (60 cells), `monstats.namestr` 13 (`Bunny`, `CrusaderSpirit`, `Injured Barbarian 1`, ...),
`misc.namestr` 8 (`bpl bps hpf hpo mpf mpo rpl rps`), `objects.name` 7, `misc.spelldescstr` 4, `montype.strplur` 4, `levels.levelwarp` 3
(`To The Pandemonium Run 1-3`, a vanilla quirk), itemstatcost 6 (`ModitemColdSkills`, `ModitemLevReq`, `ModitemPeril`), and one each in
`monstats.descstr`, `pettype.name`, `superuniques.name`.

## Known problems

* **VO lines**: 867 dialogue texts start with a number line (`45\nGreetings, ...`) and are hard-wrapped with `\n`; D2R's own copy keeps
  the number but has no line breaks (`45Greetings, stranger...`). Written as Median has them; check in game whether
  the number is read as the sound id and whether hard wraps look wrong in D2R's dialogue window.
* **Keys with a trailing space**: `Palace Cellar Level 1 `, `To The Palace Cellar Level 1 `, `druidstr `, `Immortal King's Soul Cage `.
  Tools that strip cells would not find them.
* **Case**: 23 group 2 keys equal a D2R key apart from case (`Chain`/`chain`, `Space`/`space`, ...; the report lists them); table cells
  are always qualified so they cannot hit D2R's. `Zen`/`zen` are two group 2 records (D2R has such pairs too).
* The loose zip tables and the 7 foreign `patchstring.tbl` are not converted (above).

## Tool changes

* `tbl2json.py`: namespace `mxl2012`; `--tbl-dir` (repeatable), `--d2r-lng`, `--excel-dir`; default `assets/mxl2012/...`; Median 2013's
  ID_PAIRS (Ethereal wording) dropped; short aliases are planned and written by tbl2json itself (not in txt_migrate);
  writes `strings_map.json`; the report gains encoding / colour code / VO / space / case-clash lines; UTF-8 stdout.
* `strings_ns.py`: namespace `mxl2012`; `D2R_LNG` from the environment; new `CELL_LIMITS`, `cell_value`, `overflowing_keys`;
  `write_aliases` takes an unused optional argument (kept for the table tools).
* new: `strings_check.py` (the string part of validation), `test_strings.py`.
* `strings_native.json` unchanged (empty).
