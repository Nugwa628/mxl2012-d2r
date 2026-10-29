# Source inventory: Median XL 2012 v005

Inventory lane, 2026-10-28. Static, read-only analysis. Nothing from the download was run.

**Source used:** the archive.org D2SE/D2GL repack `D2SE_Median XL 2012-005 D2GL.7z` (md5
`6eb55e9b583d1a66eef5bcc091a30182`, verified). The original ModDB zip (`Median_XL_2012_v005.zip`, md5
`53ae96c95e76062ef67a73845abe41f6`) arrived later and is verified: its `patch_d2.mpq` is byte-identical to the repack's
(section 0), so every finding about the MPQ holds for the original. The **[re-check]** marks below concern only what the
repack added around the MPQ (loose `data\` files, PlugY/D2GL/SGD2FreeRes); the original ships none of it.

## 0. Provenance of the asset pack

`assets/median/` (the asset pack, `assets.lock`) is made from the ModDB original only:

| Step | Input | Output (all outside git) | Check |
|---|---|---|---|
| download | ModDB `Median_XL_2012_v005.zip`, 168,387,701 bytes | `R\mxl2012-runs\download\` | md5 `53ae96c95e76062ef67a73845abe41f6`, sha256 `7be4c2b46124bfbf7212de3e8cc12e76f4710820fcda01276c993b917133b7b3` |
| `tools/verify_original.py` | the zip (7-Zip, nothing run) | `src-original\` (`patch_d2.mpq` + 3 documentation files), `original-vs-repack.md` | `patch_d2.mpq` 168,375,551 bytes, sha256 `5a9da6ea9aa0cf229a011407a1ece89f56652fb7079c4328ffb4e6b7696b1f9b` = the repack's ([verify-original.md](verify-original.md)) |
| `tools/mpq_extract.py` | `src-original\patch_d2.mpq` (refuses any other sha256) | `assetpack\assets\median\`: 2,362 files + `_manifest.json` + `_listfile.txt` | 2,363 hash-table entries, 0 failed; names from the internal listfile + `tools/data/patch_d2-v005.names.txt` (49), 19 unnamed |
| `tools/asset_pack.py build --version 1` | `assetpack\assets\` | `assetpack\pack\assets-1.zip` + `assets-1.manifest.json`, `assets.lock` | 151,094,751 bytes, sha256 `7ad1b448d0ed00305a4aa139c20fdf75cbcc05b362c9cc8c9ae21be9e14c2246`, manifest sha256 `63618be9...`, 2,364 files / 224,050,707 bytes; rebuilt: same bytes |

Equal to what the build read before (2026-10-28): the pack, unpacked by `asset_pack.py fetch`, against `extract-mpq\`
(the inventory lane's `mpq_dump.py` of the repack's MPQ with the 45,140-name candidate list): 2,363 files on each side, same
paths (case included), same sha256 for every file; only `_manifest.json` differs (it now records the source by name and
sha256 instead of a local path, and the names list used). The 49 names beyond the internal listfile are kept in the repo
so the extraction needs only the MPQ. `tools/build.py`, `mxl2012_prep.py`, `fxpaths.py` (and through it `icon_paths.py`,
`ui_paths.py`), `maps_hd.py` and `test_idmap.py` read `assets/median` first now; `extract-mpq` stays as the fallback.
`tools/tests/test_assets_median.py` checks a fetched tree (manifest = v005 original, counts, tables and strings read);
CI's `assets` job runs it after downloading the pack (docs/setup.md, "CI asset pack").

| Artifact (all in `R\mxl2012-runs\`, not in git) | What |
|---|---|
| `src-repack\` | the unpacked repack (149 files, 187.9 MB) |
| `src-repack-manifest.tsv` | path, size, sha256, mtime of every unpacked file |
| `extract-mpq\` | full extraction of `patch_d2.mpq` (2,362 files + `_manifest.json` with sha256, `_listfile.txt`) |
| `extract-merged\` | `extract-mpq` with the repack's loose `data\` over it (2,472 files, `_merge_manifest.json`) |
| `EXTRACT_DONE.txt` | the handoff note for other lanes (counts, unnamed files, tool) |
| `inventory-pe.txt`, `inventory-tables.tsv`, `inventory-funcs.tsv` | raw output of the tools below |

Tools (in this branch, `tools/`; run as `py -3 -I tools/<x>.py ...`): `src_manifest.py`, `pe_info.py` (PE parser that
does not need pefile), `mpq_dump.py` (StormLib, adapted from an `mpq_extract.py` and `native.py`),
`make_listfile.py`, `merge_loose.py`, `table_inventory.py`, `func_ranges.py`, `rtf2txt.py`. StormLib/CascLib DLLs are
copied into the ignored `build\`.

## 1. Headline findings

| Question | Answer | Confidence |
|---|---|---|
| Classic version targeted | **1.13c in practice; the mod is written for "1.10 or later"** (README). Built and tested on 1.13 (the README, dated 2011-12-27, calls 1.13 the latest); D2SE runs it on 1.13c | High (see 3) |
| Where the engine changes live | **Nowhere: there is no Median code.** Median XL 2012 is a softcoded `patch_d2.mpq` mod (tables, strings, art) on top of the vanilla DLLs. The README's only install step is "replace `patch_d2.mpq`", with Mac instructions too (a Mac build cannot load Windows DLLs). PlugY is an optional extra the mod supports (it ships a `PlugYFixed.ini` inside its MPQ). | High; **[re-check]** the ModDB zip ships nothing else |
| Function / dispatch ids in the tables | All inside vanilla 1.13c ranges. The few that D2R renumbered are exactly the ones `tools/func_slots.py` remaps (section 5) | High |
| TXT sources | **Shipped.** `data\global\excel` has 93 `.txt` and 91 `.bin`, so no `.bin` decoder / name-resolution / formula-bytecode work is needed | High |
| Size of the data | 2,362 MPQ files: 1,046 DCC, 753 COF, 159 DC6, 102 WAV, 86 maps (52 DT1, 34 DS1), 93 TXT + 91 BIN tables, 10 TBL, 9 `.d2` | Exact |

## 2. What is v005 and what the repack added

Top-level files of the repack:

| File | Size | sha256 (first 16) | Origin | Notes |
|---|---:|---|---|---|
| `patch_d2.mpq` | 168,375,551 | `5a9da6ea9aa0cf22` | **Median XL 2012 v005** | mtime 2012-02-25. The whole mod. |
| `documentation\README.rtf` | 89,218 | `f0c941260a279d77` | Median (Laz), dated 2011-12-27 | feature list; points to modsbylaz.hugelaser.com |
| `documentation\Other useful mods you may like.rtf`, `Documentation.txt` | 39,042 / 263 | | Median | |
| `medianXL.bmp` | 4,512 | `78134651d8eac75b` | Median D2SE banner (2009) | D2SE mod-select button |
| `D2SE_SETUP.ini` | 4,688 | `19565b93ffdeb146` | D2SE mod config; edited 2023 by the repacker | `D2Core=1.13c`, `ModMajorVersion=2012`, `ModMinorVersion=_v005`, `Direct=1`, all mod systems (D2Mod, NEFEX, D2Extra, D2SE dll, ModDll1-3) **off** |
| `PlugY.dll` + `PlugY.ini` + `PlugY\*` | 321,024 | `54ea41826fe58f13` | **repack** (PlugY 14.03, 2021) | Median 2012 predates 14.03; the MPQ carries its own `plugy\plugyfixed.ini` / `statsinterface.txt` |
| `glide3x.dll`, `d2gl.mpq`, `d2gl.ini` | 1,235,968 | `dfbb4b755b11fd97` | **repack** (D2GL 1.0.4, 2023) | Glide-to-OpenGL renderer, HD cursor/text/orbs |
| `SGD2FreeRes.dll`, `.mpq`, `.json`, licence files | 317,440 | `e765cba0140f1a35` | **repack** (SGD2FreeRes 3.0.3.1, 2023) | free resolution |
| loose `data\...` (122 files) | | | **repack** (2018-2023 dates) | see below |
| `save\` | empty | | repack | |

Loose `data\` files (D2SE runs with `-direct`, so they win over the MPQ):

| Group | Count | Effect |
|---|---:|---|
| `excel\charstats.bin`, `excel\inventory.bin` | 2 | **change** Median's tables (same size, different bytes). Probably the repacker's layout / start-item tweaks for PlugY / FreeRes. **[re-check]** |
| `tiles\act2\maggot\magqueen.ds1` + 58 other Maggot Lair `.ds1` | 59 | `magqueen.ds1` changes Median's (2,259 vs 2,778 bytes); the other 58 are new (2022 edits of vanilla maps). **[re-check]**: whose fix is this? |
| `ui\panel\invchar6.dc6` | 1 | **changes** Median's inventory panel (335,192 vs 282,000 bytes) |
| `ui\Orb\*.dc6` (11), `ui\panel\Hlthmana/npcinv/overlap.dc6` | 14 | new; D2GL HD-orb era (2022) |
| `palette\ACT1-5\Pal.pl2` (+ `.b`) | 6 | new (2018); palette lookup tables |
| `local\font\latin\*` (2023), `local\UI\ENG\act1-2\*.dc6` (2019) | 30 | new fonts and quest-log art |
| `ui\FrontEnd\*` (5), `ui\panel\supertransmogrifier/tradestash.dc6`, `local\use` | 8 | byte-identical to the MPQ copy |
| `local.zip`, `local\font.zip`, `local\LNG\ENG.zip` | 3 | inert (the game does not read zips): font backups and a 2019 ENG `string/expansionstring/patchstring.tbl` set that differs from the MPQ's |

**Confidence:** high that `patch_d2.mpq` is Median's own (2012 mtime, 168 MB, Median banner/readme next to it, all its
contents fit the mod). Medium that the MPQ is untouched: the repacker could have rebuilt it, and two oddities need the
original to explain them: the 19 unnamed entries (section 4.1) and the PlugY files inside the MPQ. **For the port use
`extract-mpq\` as the baseline and ignore the repack's loose files** unless the owner wants the repack's fixes.

## 3. Target version: 1.13c

The README (section 2, dated 2011-12-27) says: "This mod requires Diablo II Lord of Destruction version 1.10 or
later", install = back up and replace `patch_d2.mpq` (Windows and Mac), and "Diablo II Lord of Destruction 1.13 is the
latest version". So the data is version-neutral within 1.10-1.13c, and 1.13c is the version it was built and tested on.
The port should treat **1.13c** as the reference engine. Further evidence:

1. `D2SE_SETUP.ini` `[Protected]` `D2Core=1.13c`: D2SE runs the mod on its own vanilla 1.13c core. The repack contains
   no `Game.exe` and no Blizzard DLL, so the mod ran on unmodified 1.13c DLLs.
2. 82 of the 83 compared `.bin` tables use **the same record size as 1.13c bins** (cubemain
   0x148, skills 0x23c, monstats 0x1a8 by size/count). The one exception, runes (0x120 vs 0x180), is an
   extended runes record. The `.bin` files fit a 1.13c-layout engine (this does not rule out 1.10, whose layouts are
   largely the same).
3. The MPQ ships `plugy\plugyfixed.ini` with `[STAT ON LEVEL UP]` / `[SKILL ON LEVEL UP]` sections, which belong to
   newer PlugY releases (the repack's 14.03 line); with the MPQ dated 2012 that is odd. **[re-check]** whether the
   original MPQ has these files or the repacker added them.
4. Table column sets are those of 1.13c (no D2R-only columns), and `events` has 13 rows as in 1.13c (D2R has 17).

No PE in the source can be version-checked: the only binaries are third-party (below).

## 4. Binaries

| File | Size | sha256 | PE timestamp (UTC) | Version resource | Exports | Imports (summary) | Notable strings |
|---|---:|---|---|---|---|---|---|
| `PlugY.dll` | 321,024 | `54ea41826fe58f13df050b5a988b97f77c6de3c8ac2534193aa12a6106c63539` | 2021-10-07 12:04:24, MSVC 9.0 | PlugY 14.0.3.0, Yohann Nicolas | `_Init@4`, `_Release@0` | KERNEL32 (97, incl. VirtualProtect, LoadLibraryA), USER32 (11), VERSION | PlugY's own; no Median names |
| `SGD2FreeRes.dll` | 317,440 | `e765cba0140f1a35c512163ddd66bfd6708889aa54c77537b39e846bd992ad6c` | 2023-02-22 13:28:59, MSVC 14.34 | 3.0.3.1, SlashGaming (Mir Drualga) | `PrintLicenseNotice` | KERNEL32 (43, WriteProcessMemory), ADVAPI32 (registry, crypto hash), MSVCP140/UCRT | |
| `glide3x.dll` | 1,235,968 | `dfbb4b755b11fd97d5fb07b84af39675208102a5d2ad7eb35fa299cbe95b7c2f` | 2023-03-10 17:28:59, MSVC 14.29 | D2GL 1.0.4.0 | 95 Glide3 entry points (`_grDrawTriangle@12`, ...) | OPENGL32, GDI32, WINMM, IMM32; Detours sections | |

None of these carries Median code; none has Median assert paths (`..\Foo.cpp`). There is **no Median DLL, no D2Mod /
NEFEX / D2Extra config, and no patched Blizzard DLL** in the repack, and the README's install steps (replace
`patch_d2.mpq` only, Mac included) rule one out for the original too. The MPQ contains no `.dll` or code-like files and
no table mentions a DLL. So the "engine changes" of Median 2012 are whatever vanilla 1.13c does with Median's table
values (plus the optional PlugY features). **[re-check]**: if the ModDB zip ships a launcher, installer or patched DLL,
this whole section changes.

## 5. MPQ contents

### 5.1 Extraction
Because the mod installs by *replacing* Blizzard's `patch_d2.mpq`, the MPQ must also carry the vanilla patch files the
game needs (that is why it holds vanilla-named maps, sounds and `animdata.d2`). Not every file in it is Median's own;
a Blizzard 1.13c `patch_d2.mpq` (not on this PC) would be needed to separate them.

`patch_d2.mpq`: hash table 2,363 entries = 2,362 files + `(listfile)`. With the internal listfile 68 entries had no
name; a candidate listfile (45,140 names from earlier Median manifests, D2R 93847's tree, the repack and the
standard table names) named 49 more. **19 remain unnamed** (kept as `FileNNNNNNNN.ext` at the root of `extract-mpq\`):

| Entry | Size | Content |
|---|---:|---|
| `File00000064.xxx` | 56,995 | string table, same header as the other `patchstring.tbl` (another language? `jpn` did not match) |
| `File00000082/083.xxx` | 1,526 ×2 | identical binary, magic `WS%` |
| `File00000098.xxx` | 7,580 | TXT, cubemain-like header (`description enabled min diff version start day ...`) |
| `File00000100.xxx` | 124,550 | TXT, item-base header (`name type code alternateGfx ...`) |
| `File00000105.xxx` | 56,898 | TXT, affix header (`Name version spawnable rare level ...`) |
| `File00000167.xxx` | 32 | "Nothing to see here. Move along." |
| `File00000169/170/192/193.xxx` | 13-15 KB | binary, `00 00 01 00` header (BIN-like) |
| `File00000171-178.dc6` | 0.5-3 KB | 8 small DC6 |

They look like leftovers or old copies; the named tables all exist. Not used by any lane until the original confirms.

### 5.2 Tables (`data\global\excel`)
Full numbers in `inventory-tables.tsv`. Rows exclude "Expansion" separators. 1.13c = vanilla row count
(`vanilla113.py`), D2R = 93847 `excel\`.

| Table | 2012 rows | 1.13c | D2R | Note |
|---|---:|---:|---:|---|
| cubemain | 11,477 | 151 | 227 | largest table; under D2R's 32,768 limit |
| runes | 3,133 | | 181 | runewords |
| missiles | 2,665 | 684 | 742 | |
| uniqueitems | 2,479 | | 438 | rows incl. blank / placeholder rows |
| sounds | 4,900 | | 11,913 | fewer than D2R: D2R's own sounds must be kept ("D2R wins" rule) |
| monstats / monstats2 | 1,822 / 1,210 | 735 / 610 | 751 / 623 | |
| treasureclassex | 1,468 | | 1,358 | (`treasureclass.txt` 751 rows is a pre-1.10 leftover, not loaded by 1.13c) |
| monseq | 1,402 | 1,010 | 1,030 | |
| lvlprest | 1,101 | 1,092 | 1,092 | |
| skills / skilldesc | 1,038 / 699 | 357 / 221 | 429 / 263 | 30 class skills per class (the 210 vanilla class slots, replaced in place) + monster / item skills |
| magicprefix / magicsuffix | 747 / 959 | | 721 / 785 | |
| weapons / armor / misc | 921 / 642 / 866 | | 306 / 217 / 169 | |
| properties | 543 | 269 | 284 | |
| itemstatcost | 508 | 359 | 368 | at the classic 9-bit stat-id ceiling (511) |
| states | 255 | 185 | 232 | exactly the 1.13c byte-id ceiling; under D2R's 512 |
| levels / lvltypes / lvlwarp / lvlmaze | 137 / 36 / 88 / 81 | 138 / 37 / ... | 138 / 36 / 88 / 81 | **vanilla count**: uber levels reuse vanilla slots |
| setitems / sets | 299 / 67 | | 140 / 35 | |
| gamble | 1,322 | | 121 | |
| monprop | 376 | 13 | 13 | |
| overlay | 524 | 294 | 334 | |
| pettype | 66 | 20 | 22 | |
| hireling | 120 | | 135 | |
| inventory | 32 | 33 | 30 | player grid 10×6, cube 10×8, big stash 10×10 (vanilla 10×4, 3×4, 6×8) |

Tables 2012 has that D2R does not: `arena`, `chartemplate`, `hiredesc`, `monitempercent`, `uniquetitle` (1.13c
leftovers D2R dropped), plus reference-only TXT without a `.bin` (`aiparms`, `cubetype`, `monname`, `weaponclass`,
`uniqueitems2`, `soundenviron`). **No Median-only engine tables**. `.bin`-only:
`itemscode`, `misscode`, `skillscode`, `skilldesccode`, `leveldefs` (compiled by the game, as in vanilla).

TXT vs BIN: row counts match everywhere except `objects` (574 txt / 573 bin) and `objgroup` (133 / 134) and the unused
`treasureclass`. The game reads the `.bin` (D2SE `Txt=0`), so a data lane must confirm the TXT matches the BIN before
building from TXT (decode the BIN of the tables that differ).

### 5.3 Dispatch ids (`inventory-funcs.tsv`)
Every function column (skills srv/clt start/do/prg, missiles do/hit/dmg, itemstatcost descfunc/dgrpfunc/op, properties
func, states set/rem/active, objects Operate/Populate/Init/Client, misc pSpell, levels DrlgType) stays within the
vanilla maximum. The only ids outside D2R's own rows are **srvdofunc 109, srvstfunc 64, cltstfunc 82, cltdofunc 22,
pCltHitFunc 11/12/26**: exactly the 1.13c slots D2R renumbered or dropped, already handled by
`func_slots.py` / `txt_migrate.py` `skill_rules` and the validator (`docs/function-slots.md` there). Skill formulas
are plain text in the TXT (e.g. `par1+(blvl*par2)`, `stat('skill_minion_hp_percent'.accr)`); they need
formula limits check (255 chars, 32-byte names), not a bytecode decoder.

### 5.4 Strings
| File | Entries |
|---|---:|
| `lng\eng\string.tbl` | 8,811 |
| `lng\eng\expansionstring.tbl` | 9,841 |
| `lng\eng\patchstring.tbl` | 4,325 |
| `lng\{chi,deu,esp,fra,ita,kor,pol}\patchstring.tbl` | 1,143 each |

English is the only real language (all three tables replaced). The other seven are just `patchstring` and are probably
vanilla (1,143 entries each, same size range); the mod's text would show in English or as missing keys there.

### 5.5 Art, maps, sound
| Folder | Files | Note |
|---|---:|---|
| `monsters` | 1,592 (DCC + COF) in **108 tokens** | 94 tokens with non-alphanumeric names (Median-only), 14 alphanumeric. 93 of the 108 have an existing HD placeholder mapping that can be reused |
| `missiles` | 145 DCC | |
| `overlays` | 63 DCC | |
| `items` | 106 DC6 | inventory pictures |
| `ui` | 28 DC6 | panels (invchar6, supertransmogrifier, tradestash), skill icons ×8, skill-tree backgrounds ×7, front-end / char select |
| `local\ui\eng` | 16 DC6 | quest-log pictures |
| `tiles` | 52 DT1 + 34 DS1 in 23 folders | edits of vanilla areas (act 1-5 incl. expansion); no new level types |
| `sfx` | 102 WAV | |
| `data\global\*.d2` | 9 | `animdata.d2`, `chars_cof.d2`, `cmncof_a1-a7.d2` |

No player-character art (`data\global\chars`): Median 2012 uses vanilla player models.

## 6. Port problems that apply to 2012

| Problem | Applies to 2012? | Why |
|---|---|---|
| D2Sigma triage (109 modules), patch audit (300+ rows), own-code audit, 46 Sigma tables | **No** | no DLL. The engine work is just "what 1.13c does with these values vs what D2R does" |
| `.bin` decoder, `mxl_names.py` placeholder names, formula bytecode `formula.py` | **No** (mostly) | TXT is shipped; only the TXT-vs-BIN check for 2-3 tables |
| GH/SQ trap 1 | **Half** | skills `anim` already says `SQ` (113 rows, 0 `GH`); plrmode/monmode `Code` must still keep D2R's values |
| Signed-byte / 4294967295 traps 3-4 | **Mostly no** | TXT holds the original signed values; still compare numeric columns on shared rows |
| Function slots D2R renumbered | **Yes** | same slots (5.3); reuse `func_slots.py` rules |
| Merge rules (indexed / replace / D2R wins / keyed), ID remap, validator | **Yes** | same table set |
| overlay `Character`, missiles `LevRange`, inventory two rows per page, stop functions, blank-key rows, `excel\` vs `excel\base\` banks | **Yes** | generic D2R traps |
| Treasure classes with display names | **Check** | read the TXT |
| Wide states (967 > 512) | **No** | 255 states |
| New levels / level types / automap plugin | **No** | 137 levels, 36 level types: vanilla counts |
| Strings namespace, `tbl2json.py` | **Yes** | 3 ENG tables, 22,977 entries |
| Saves (D2RLoader extended format) | **Yes** | itemstatcost 508 and skills 1,038 exceed vanilla; new characters only |
| HD art: item / UI upscale, monster / missile placeholders | **Yes, smaller** | 108 monster tokens (93 with an existing mapping), 145 missiles, 106 items |
| HD UI layouts (grids) | **Yes, smaller** | inventory 10×6, cube 10×8, stash 10×10 |
| Cube conditions beyond D2R's (Sigma's 32-42, cubemainext) | **Probably no** | 1.13c cube only; 11,477 recipes but vanilla columns |
| Sigma UI (loot filter, dungeon widget, options, notifications) | **No** | |
| PlugY features | **New** | shared/multi-page stash, stat unassignment (`PlugYFixed.ini` in the MPQ forces stat unassign on, world event / uber quest / ladder runewords off); D2R has shared stash tabs, D2RLoader has stash pages |

## 7. What this means for the port

**Data-only vs plugin.** Median 2012 is a data mod on vanilla 1.13c. Rough split of the engine-side work:
**about 85-90% data** (migrate the TXT with the existing migration rules, function-slot remaps, strings, validator) and **10-15%
plugin**: the behaviour 1.13c had and D2R changed (the renumbered slots that have no D2R twin, e.g. cltstfunc 82 and
pCltHitFunc 11; any 1.13c hardcoded mechanic D2R altered that the data relies on), plus PlugY-parity features (stat
unassign, stash pages) if wanted. The plugin share drops to
something like 5% of the whole. Graphics stays the largest open part (HD placeholders for 108 monster tokens, 145
missile and 63 overlay DCCs, 106 item and ~45 UI DC6), but an existing pipeline and much of its mapping (93 shared
tokens) carry over.

**Recommended next lanes**
1. **original-check** (when the ModDB zip lands): diff it against `src-repack` / `extract-mpq` (MPQ sha256, presence
   of any exe/dll/launcher, the 19 unnamed entries, PlugY files in the MPQ). Gate for everything below.
2. **txt-check**: decode the `.bin` of `objects`, `objgroup` (and spot-check skills, itemstatcost, cubemain) and
   confirm the TXT is what the game used.
3. **data-migrate**: adapt `txt_migrate.py` / `validate.py` / `func_slots.py` / `vanilla113.py`, drop the
   Sigma parts, run on `extract-mpq` TXT, reach 0 validator errors.
4. **strings**: `tbl2json.py` + D2RLoader namespace `mxl2012` for the 3 ENG tables.
5. **install-boot** (needs the coordinator's go for game runs): first boot, new character in Act 1.
6. **gfx-placeholders**: reuse the existing monster/missile HD mapping for the 93 shared tokens, map the other 15;
   upscale items / panels; grid layouts for 10×6 / 10×8 / 10×10.
7. **engine-audit**: list 1.13c hardcoded behaviours the 2012 data depends on that D2R changed (slots above, states at
   255, stat ids up to 507, 1,038 skills in saves), and decide plugin work.

## 8. Open questions for the owner

1. Is the ModDB zip coming soon? Until then every finding is from the repack. The README says the install is only
   "replace `patch_d2.mpq`", so no DLL is expected, but the zip settles whether the repacker changed the MPQ (PlugY
   files inside it, 19 unnamed entries).
2. Which classic version is the reference? The README says "1.10 or later" and was tested on 1.13; this inventory
   assumes 1.13c. The project has a 1.14d install approved for native runs (CLAUDE.md); 1.13c vs 1.14d
   differences could matter if it is used for side-by-side behaviour checks.
3. Do you want the repack's fixes (the changed `charstats.bin` / `inventory.bin`, the Maggot Lair maps, `invchar6.dc6`,
   fonts), or pure v005? This inventory recommends pure v005.
4. PlugY: the MPQ's `PlugYFixed.ini` (if original) forces stat unassignment on. Should the port provide PlugY-like features (stat
   unassign, multi-page / shared stash) or only what D2R does natively?
5. Languages: only English is complete. English only for the port?
6. May Median XL 2012 data ship as an asset pack (open question from the lane rules)? Who holds the rights
   to Median 2012 today, and has the team been asked?
