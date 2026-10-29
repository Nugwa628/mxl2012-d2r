# Graphics and maps inventory: Median XL 2012 v005 (phase 5 planning)

Lane `gfxsurvey`, 2026-10-28. Tools: `tools/gfx_survey.py` (inventory) and `tools/gfx_monster_cmp.py` (monster sets against
the reference monster set). Both read-only, run as `py -3 -I`. Scratch output, not committed: `R\mxl2012-runs\gfxsurvey-out\`.

This document holds file paths, counts, frame numbers and item codes only. No art, table content or item display names.

## 1. Scope and sources

- **The port is pure v005.** Primary tree: `R\mxl2012-runs\extract-mpq\` (`patch_d2.mpq` alone, 2,362 files; `EXTRACT_DONE.txt`).
  Every count below is for this tree unless marked **repack-only**.
- **Repack-only extras (not ported).** `R\mxl2012-runs\extract-merged\` is the MPQ plus the D2SE/D2GL repack's loose `data/`.
  It adds 107 art files and replaces 9 MPQ art files. Section 6 lists them. They are not ported.
- **D2R baseline.** `<extract_dir>\filelist.txt` (150,886 `data/` paths; `extract_dir`: machine-local config, docs/setup.md) and its `manifest.json`
  (sizes). Read-only.
- **Reference monster set.** A later Median release's monster folders and an `hd_monsters.md` with HD stand-in donors
  keyed by monster Code (paths from the machine-local config). Read-only.
- **1.13c base game.** The mod overlays 1.13c; patch_d2.mpq holds only what Median overrides or adds. A vanilla file the mod
  does not override (e.g. item icon `invaar.dc6`) comes from the base game, not from the mod tree. So "not in the mod tree"
  is not a gap. A gap is a file in neither the mod tree nor D2R.
- **Classes** by extension: DC6, DCC, COF, DT1, DS1, palettes, `.tbl`. Names the extractor could not resolve
  (`FileNNNNNNNN.ext`) form their own class.
- **Path status.** *Same path in D2R*: the lower-cased `data/...` path is in the D2R filelist. *Same size* / *size differs*:
  against D2R's manifest. *NEW*: no D2R path. A same-path file can still be Median's own art.

## 2. Totals, pure v005 (`extract-mpq`)

| class | files | same path in D2R | same size | size differs | NEW to D2R |
|---|---:|---:|---:|---:|---:|
| DC6 (UI, item icons, skill sheets) | 151 | 30 | 12 | 18 | 121 |
| DCC (monsters, missiles, overlays) | 1,046 | 13 | 0 | 13 | 1,033 |
| COF (monster animations) | 753 | 5 | 3 | 2 | 748 |
| DT1 (tilesets) | 52 | 0 | - | - | 52 |
| DS1 (maps) | 34 | 21 | 10 | 11 | 13 |
| Text tables (`.tbl`: string tables) | 10 | 10 | 0 | 10 | 0 |
| Unresolved names (`FileNNNNNNNN`) | 19 | 0 | - | - | 19 |
| **Total** | **2,065** | **79** | **25** | **54** | **1,986** |

Not art, skipped: WAV 102, TXT 94, BIN 91, `.d2` 9, and a few INI/JSON. Palettes and fonts are not in pure v005 at all
(repack-only).

## 3. Findings (pure v005)

- 1,986 of 2,065 art files (96%) are at paths D2R does not have. 79 share a D2R path; 54 of those differ in size, so Median
  changed them.
- **Monsters.** 108 monster art sets (1,592 files). 93 have a folder of the same token in the reference set; 86 of those have
  identical DCC/COF file names. 15 sets (203 files) have no reference folder. Section 4 marks each set.
- **Item icons.** 467 `invfile` codes in the armor, weapon and misc tables (incl. unique and set columns). 113 are not in
  D2R's tables (new codes): 99 have art in the mod, 12 use the base-game icon at the same D2R path, and **2 have no art
  anywhere** (`stoneearth`, `stonemars`).
- **Skill icon sheets.** 8 sheets, all in the mod and in D2R; **no new sheet**. Median changed them. Five of D2R's six
  class sheets are exactly 60 frames (2 frames per icon x 30 skills) and the sixth is 156. The mod's class sheets are 76 to
  118 frames and its basic sheet is 78. Class skills step their icon cels by 2 (cel n and n+1 make one icon).
- **Maps.** 13 new DS1 and 52 new DT1. The DT1s are all in new `expansion/` tilesets: neonmile 16, dystopic 9, redsquare 7,
  voodoo 7, terror 6, zakarum 4, magma 3. 11 of the 21 vanilla-path DS1 differ in size from D2R.
- **Missiles and overlays.** 145 missile DCCs and 63 overlay DCCs, all new. No D2R counterparts.
- **UI.** 13 DC6 in `ui/`, all at D2R paths. 16 local string/quest DC6s (`data/local/ui/eng/`) are new to D2R.
- **Unresolved.** 19 files at the root of the MPQ extraction are unnamed: 11 `.xxx` and 8 `.dc6`. Their content is not identified.

## 4. Monster sets against the reference set

The reference set's monster folders are the same tokens (monstats Code) as the 2012 folders. Its `hd_monsters.md`
gives an HD donor for every reference monster Code (71 high, 16 medium, 3 other, 3 low confidence).

- **93 of 108 sets are in the reference set**, so its HD stand-in choice applies to them (the donor's confidence is in the
  table). **86 have identical DCC/COF file names**; 7 differ (`!1`, `!h`, `!k`, `&d`, `0n`, `9x`, `~z`).
- **15 sets are not in the reference set** (203 files): `!e`, `!z`, `&6`, `7$`, `8@`, `9$`, `@d`, `^t`, `ie`, `k+`, `m+`, `oy`, `t^`,
  `x+`, `~5`. No reference stand-in exists for them; they need custom art or a donor chosen here.
- **Caveat.** The reference donors are for D2R's **HD** client (models, unit JSON), not the legacy DCC/COF this mod uses. They
  say which monster looks are covered in principle, not that a legacy DCC exists for them.

## 5. What needs custom art or a stand-in (pure v005)

Stand-in = a D2R file at the same path (the legacy 2D file D2R ships). See section 7, item 3, on whether D2RLoader serves it.
"Custom" = nothing at the path in the mod or in D2R.

| group | files | D2R path | needs | notes |
|---|---:|---|---|---|
| Item icons (`data/global/items/`) | 106 (+12 base-game) | 1 same path; 12 base-game icons have D2R art | **custom for 2 codes** (`stoneearth`, `stonemars`) | 99 new codes have mod art |
| Skill icon sheets (`ui/spells/`) | 15 | all at the same path | none (no new sheets) | class sheets differ in frame count from D2R |
| UI (`ui/`) | 13 | all at the same path | none | |
| Local UI (`data/local/ui/eng/`) | 16 (pure v005) | new | custom or D2R has none | 8 more are repack-only (section 6) |
| Text tables (`data/local/lng/`) | 10 | all at the same path; 10 differ in size | none | not art; listed for completeness |
| Maps (DS1), vanilla path | 21 | same path; 11 differ in size | D2R's DS1 is a stand-in for the 11 changed; the other 10 are the same file | |
| Maps (DS1), new | 13 | none | stand-in biome or custom | `expansion/*`, `act1/cathedrl`, `act2/arcane`, `act3/kurast` |
| Tilesets (DT1), new | 52 | none | stand-in or custom | 7 `expansion/` tilesets |
| Monsters (DCC + COF), 93 sets in reference | 1,389 | (19 monster files in total share a D2R path) | reference HD donor exists (HD only); legacy DCC still needed | section 4 |
| Monsters, 15 sets not in reference | 203 | none | custom or a chosen donor | section 4 |
| Missiles (DCC) | 145 | none | custom, or drop | |
| Overlays (DCC) | 63 | none | custom, or drop | |
| Unresolved names | 19 | - | identify first | |

## 6. Repack-only extras (not ported)

From `extract-merged` minus `extract-mpq`. Not in pure v005; a repack-only file is ported only if the owner rules otherwise.

| group | added | replaced (MPQ file) | D2R path | notes |
|---|---:|---:|---|---|
| Maggot Lair DS1 (`data/global/tiles/act2/maggot/`) | 57 | 1 (`magqueen.ds1`, content differs) | all at D2R paths | repack's 2022 edits |
| UI DC6 (`ui/FrontEnd/` 5, `ui/panel/` 3) | 0 | 8 (7 byte-identical to the MPQ; `ui/panel/invchar6.dc6` differs) | all at D2R paths | |
| UI DC6 panels (`ui/panel/Hlthmana`, `npcinv`, `overlap`) | 3 | 0 | all at D2R paths | |
| Orb DC6 (`ui/Orb/`) | 11 | 0 | new | repack's 2022 orbs |
| Local UI DC6 (`data/local/UI/ENG/act1`, `act2`) | 8 | 0 | new | 2019 |
| Palettes (`data/global/palette/ACT1-5`) | 6 (5 `Pal.pl2`, `ACT5/Pal.pl2.b`) | 0 | 5 at D2R paths; `ACT5/Pal.pl2.b` new | 2018 |
| Fonts (`data/local/font/latin/`) | 22 (11 DC6, 11 backup `.tbl`) | 0 | 10 DC6 at D2R paths; `fontformal8.dc6` and the `.tbl` new | 2023 |
| **Total** | **107** | **9** | | |

Note: the repack's loose `data/` also contains three zip files (font, LNG and local bundles); not unpacked, not counted.

## 7. Open items

1. **Permission.** Owner question 5 (is shipping Median 2012 art OK) gates every row in section 5 that would ship Median art.
2. **ModDB zip.** Re-check the pure v005 numbers against `Median_XL_2012_v005.zip` when it lands (`EXTRACT_DONE.txt` says the
   MPQ is from the repack; the zip is the check).
3. **Untested stand-in path.** D2R ships legacy DC6/DCC/DT1/DS1 next to its HD assets, but whether
   D2RLoader serves *modded* legacy files from the mod MPQ is still untested. Every stand-in above is a plan until that is.
4. **Shared skill sheet.** 446 classless named skill rows point at cels 0 to 49 of `skillicon.dc6`, which has 25 frames (D2R:
   24). That mapping is unresolved, so those rows are not counted as class icons.
5. **Unresolved files.** The 19 unnamed files need identification before they are classed.
6. **No legacy donor mapping.** The reference donors are for the HD client only. A donor for legacy DCC/COF
   (for the 15 sets not in the reference set, or the 103 new token folders) is not built.

## Appendix A. Folders, pure v005 (generated by `tools/gfx_survey.py`)

Files per folder in `extract-mpq`. "in D2R": same path in the D2R filelist. NEW: no D2R path.

| folder | area | dc6 | dcc | cof | dt1 | ds1 | palette | font tbl | unresolved | total | in D2R | NEW | status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| (root, unresolved names) | outside data/ | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 19 | 19 | 0 | 19 | NEW |
| data/global/items | item icons | 106 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 106 | 1 | 105 | mixed |
| data/global/missiles | missiles | 0 | 145 | 0 | 0 | 0 | 0 | 0 | 0 | 145 | 0 | 145 | NEW |
| data/global/monsters/!! | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/!1 | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/!2 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!3 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!4 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!5 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!6 | monsters | 0 | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 18 | 0 | 18 | NEW |
| data/global/monsters/!7 | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/!8 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!9 | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/!a | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!d | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/!e | monsters | 0 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 20 | 0 | 20 | NEW |
| data/global/monsters/!h | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!i | monsters | 0 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 12 | NEW |
| data/global/monsters/!k | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/!s | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/!z | monsters | 0 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 12 | NEW |
| data/global/monsters/#0 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#5 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#6 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#i | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#l | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#m | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#q | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#r | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#w | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/#y | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/$a | monsters | 0 | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 18 | 0 | 18 | NEW |
| data/global/monsters/$f | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/$g | monsters | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 4 | NEW |
| data/global/monsters/$h | monsters | 0 | 7 | 8 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 15 | NEW |
| data/global/monsters/%4 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/%9 | monsters | 0 | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 18 | 0 | 18 | NEW |
| data/global/monsters/&6 | monsters | 0 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 12 | NEW |
| data/global/monsters/&b | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/&d | monsters | 0 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 12 | 0 | 12 | NEW |
| data/global/monsters/&g | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(0 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(1 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(2 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(a | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(c | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(g | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/(i | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(l | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(m | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/(n | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/(o | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(r | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/(s | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/(x | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/0! | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/0( | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/08 | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/0k | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/0n | monsters | 0 | 10 | 10 | 0 | 0 | 0 | 0 | 0 | 20 | 0 | 20 | NEW |
| data/global/monsters/1! | monsters | 0 | 8 | 7 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 15 | NEW |
| data/global/monsters/1c | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/2! | monsters | 0 | 8 | 7 | 0 | 0 | 0 | 0 | 0 | 15 | 0 | 15 | NEW |
| data/global/monsters/2# | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/2( | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/3# | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/5$ | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/5( | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/7# | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/7$ | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/8# | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/8$ | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/8@ | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/9! | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/9$ | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/9( | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/9x | monsters | 0 | 91 | 8 | 0 | 0 | 0 | 0 | 0 | 99 | 0 | 99 | NEW |
| data/global/monsters/@1 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/@3 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/@5 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/@6 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/@c | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/@d | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/@e | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/@f | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/^3 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/^t | monsters | 0 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 7 | 0 | 7 | NEW |
| data/global/monsters/b# | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/c# | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/c@ | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/e9 | monsters | 0 | 5 | 2 | 0 | 0 | 0 | 0 | 0 | 7 | 7 | 0 | vanilla |
| data/global/monsters/fm | monsters | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 3 | 1 | 2 | mixed |
| data/global/monsters/g7 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/ie | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/im | monsters | 0 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | 3 | 1 | 2 | mixed |
| data/global/monsters/iw | monsters | 0 | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 8 | 8 | 0 | vanilla |
| data/global/monsters/ji | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/k+ | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/m+ | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/n# | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/oy | monsters | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 2 | 0 | vanilla |
| data/global/monsters/rt | monsters | 0 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 4 | NEW |
| data/global/monsters/t^ | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/x+ | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/~2 | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/~3 | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/~5 | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/monsters/~b | monsters | 0 | 9 | 9 | 0 | 0 | 0 | 0 | 0 | 18 | 0 | 18 | NEW |
| data/global/monsters/~k | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/~m | monsters | 0 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 14 | 0 | 14 | NEW |
| data/global/monsters/~z | monsters | 0 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |
| data/global/overlays | overlays | 0 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 60 | 0 | 60 | NEW |
| data/global/overlays/expansion | overlays | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 3 | NEW |
| data/global/tiles/act1 | maps (ds1/dt1) | 0 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 5 | 4 | 1 | mixed |
| data/global/tiles/act2 | maps (ds1/dt1) | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 4 | 3 | 1 | mixed |
| data/global/tiles/act3 | maps (ds1/dt1) | 0 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 4 | 3 | 1 | mixed |
| data/global/tiles/act4 | maps (ds1/dt1) | 0 | 0 | 0 | 0 | 10 | 0 | 0 | 0 | 10 | 10 | 0 | vanilla |
| data/global/tiles/expansion | maps (ds1/dt1) | 0 | 0 | 0 | 52 | 11 | 0 | 0 | 0 | 63 | 1 | 62 | mixed |
| data/global/ui/FrontEnd | ui | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 7 | 7 | 0 | vanilla |
| data/global/ui/bigmenu | ui | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 2 | 0 | vanilla |
| data/global/ui/charselect | ui | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 0 | vanilla |
| data/global/ui/panel | ui | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 3 | 0 | vanilla |
| data/global/ui/spells | skill/spell icons | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 15 | 15 | 0 | vanilla |
| data/local/lng/chi | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | vanilla |
| data/local/lng/deu | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | vanilla |
| data/local/lng/eng | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 0 | 3 | 3 | 0 | vanilla |
| data/local/lng/esp | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | vanilla |
| data/local/lng/fra | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | vanilla |
| data/local/lng/ita | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | vanilla |
| data/local/lng/kor | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | vanilla |
| data/local/lng/pol | ui-local (strings/quest art) | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 1 | 0 | vanilla |
| data/local/ui/eng | ui-local (strings/quest art) | 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 16 | 0 | 16 | NEW |

## Appendix B. Monster sets against the reference set (generated by `tools/gfx_monster_cmp.py`)

"in reference": the reference set has a monster folder of that token. "same file names": its DCC/COF names match the reference set's. "reference HD donor": the reference `hd_monsters.md` donor for that Code and its confidence (for the HD client only).

| token | files | in reference | same file names | reference HD donor (confidence) |
|---|---:|---|---|---|
| `!!` | 16 | yes | yes | brute2, eagle (high) |
| `!1` | 16 | yes | no | gorgon1 (high) |
| `!2` | 14 | yes | yes | councilmember1, doomknight2 (high) |
| `!3` | 14 | yes | yes | clawviper1, nihlathakboss (high) |
| `!4` | 14 | yes | yes | colbarbwhirl (medium) |
| `!5` | 14 | yes | yes | councilmember1, fetishblow1 (high) |
| `!6` | 18 | yes | yes | bear, firegolem (high) |
| `!7` | 16 | yes | yes | fetishblow1, irongolem (high) |
| `!8` | 14 | yes | yes | brute2, deathmauler1 (high) |
| `!9` | 16 | yes | yes | sk_archer1, trappedsoul1 (high) |
| `!a` | 14 | yes | yes | baalminion1, irongolem (high) |
| `!d` | 16 | yes | yes | willowisp1 (high) |
| `!e` | 20 | no | - | - |
| `!h` | 14 | yes | no | suicideminion1, vilemother1 (high) |
| `!i` | 12 | yes | yes | willowisp1 (high) |
| `!k` | 16 | yes | no | putriddefiler1 (high) |
| `!s` | 14 | yes | yes | cantor1, willowisp1 (high) |
| `!z` | 12 | no | - | - |
| `#0` | 14 | yes | yes | irongolem (high) |
| `#5` | 14 | yes | yes | clawviper1, sandleaper1 (high) |
| `#6` | 14 | yes | yes | snowyeti1 (medium) |
| `#i` | 14 | yes | yes | act5pow, doomknight3 (high) |
| `#l` | 14 | yes | yes | bonefetish1 (medium) |
| `#m` | 14 | yes | yes | colbarbwhirl (high) |
| `#q` | 14 | yes | yes | hydra1 (high) |
| `#r` | 14 | yes | yes | scarab1 (high) |
| `#w` | 14 | yes | yes | darkwanderer (high) |
| `#y` | 14 | yes | yes | wraith1 (high) |
| `$a` | 18 | yes | yes | wraith1 (high) |
| `$f` | 16 | yes | yes | warputriddefiler (medium) |
| `$g` | 4 | yes | yes | barricadewall2 (medium) |
| `$h` | 15 | yes | yes | bonefetish1 (medium) |
| `%4` | 14 | yes | yes | scarab1, warbighead (high) |
| `%9` | 18 | yes | yes | baalminion1 (medium) |
| `&6` | 12 | no | - | - |
| `&b` | 14 | yes | yes | eagle, scarab1 (high) |
| `&d` | 12 | yes | no | mummy1 (medium) |
| `&g` | 14 | yes | yes | colbarbwhirl (high) |
| `(0` | 14 | yes | yes | hephasto (high) |
| `(1` | 14 | yes | yes | darkwanderer, doomknight2 (high) |
| `(2` | 14 | yes | yes | doomknight2 (high) |
| `(a` | 14 | yes | yes | quillrat1 (high) |
| `(c` | 14 | yes | yes | clawviper1 (high) |
| `(g` | 16 | yes | yes | bonefetish1, druidhawk (high) |
| `(i` | 14 | yes | yes | mummy1, scarab1 (high) |
| `(l` | 14 | yes | yes | deathmauler1 (high) |
| `(m` | 16 | yes | yes | irongolem, wraith1 (high) |
| `(n` | 16 | yes | yes | arach1 (high) |
| `(o` | 14 | yes | yes | brute2, doomknight1 (high) |
| `(r` | 16 | yes | yes | hephasto (medium) |
| `(s` | 14 | yes | yes | duriel, fingermage1 (high) |
| `(x` | 14 | yes | yes | doomknight2, frogdemon1 (high) |
| `0!` | 16 | yes | yes | councilmember1, summoner (high) |
| `0(` | 14 | yes | yes | wolf (high) |
| `08` | 16 | yes | yes | warputriddefiler (high) |
| `0k` | 16 | yes | yes | painworm1, scarab1 (high) |
| `0n` | 20 | yes | no | ancientbarb1, sandraider1 (high) |
| `1!` | 15 | yes | yes | eagle (medium) |
| `1c` | 14 | yes | yes | barricadedoor2, hephasto (high) |
| `2!` | 15 | yes | yes | boneprison3, warputriddefiler (medium) |
| `2#` | 14 | yes | yes | summoner (high) |
| `2(` | 14 | yes | yes | bear, boneprison3 (high) |
| `3#` | 14 | yes | yes | quillbear1 (high) |
| `5$` | 14 | yes | yes | siegebeast1 (high) |
| `5(` | 14 | yes | yes | deathmauler1, doomknight2 (high) |
| `7#` | 14 | yes | yes | councilmember1 (high) |
| `7$` | 16 | no | - | - |
| `8#` | 14 | yes | yes | regurgitator1 (high) |
| `8$` | 16 | yes | yes | sk_archer1 (high) |
| `8@` | 16 | no | - | - |
| `9!` | 14 | yes | yes | baboon1, quillbear1 (high) |
| `9$` | 14 | no | - | - |
| `9(` | 16 | yes | yes | councilmember1, foulcrow1 (high) |
| `9x` | 99 | yes | no | , cain1 (medium) |
| `@1` | 14 | yes | yes | colbarbwhirl, wraith1 (high) |
| `@3` | 14 | yes | yes | wraith1 (high) |
| `@5` | 14 | yes | yes | bighead1, warputriddefiler (high) |
| `@6` | 14 | yes | yes | doomknight3, firegolem (high) |
| `@c` | 14 | yes | yes | councilmember1, darkwanderer (high) |
| `@d` | 14 | no | - | - |
| `@e` | 14 | yes | yes | darkwanderer, summoner (high) |
| `@f` | 14 | yes | yes | brute2, thornhulk1 (high) |
| `^3` | 14 | yes | yes | wolf (high) |
| `^t` | 7 | no | - | - |
| `b#` | 14 | yes | yes | cantor1, doomknight1 (high) |
| `c#` | 14 | yes | yes | firegolem (high) |
| `c@` | 14 | yes | yes | wraith1 (high) |
| `e9` | 7 | yes | yes | infernosentry, wakeofdestruction (-) |
| `fm` | 3 | yes | yes | , claygolem (low) |
| `g7` | 14 | yes | yes | brute2, councilmember1 (high) |
| `ie` | 14 | no | - | - |
| `im` | 3 | yes | yes | , batdemon1 (low) |
| `iw` | 8 | yes | yes | act3hire (-) |
| `ji` | 14 | yes | yes | darkwanderer, warputriddefiler (high) |
| `k+` | 14 | no | - | - |
| `m+` | 14 | no | - | - |
| `n#` | 14 | yes | yes | act5pow (low) |
| `oy` | 2 | no | - | - |
| `rt` | 4 | yes | yes | rat (-) |
| `t^` | 16 | no | - | - |
| `x+` | 16 | no | - | - |
| `~2` | 16 | yes | yes | brute2, painworm1 (high) |
| `~3` | 14 | yes | yes | cantor1, fetishshaman1 (high) |
| `~5` | 16 | no | - | - |
| `~b` | 18 | yes | yes | bear, hephasto (medium) |
| `~k` | 14 | yes | yes | bonefetish1 (medium) |
| `~m` | 14 | yes | yes | bonefetish1, quillrat1 (medium) |
| `~z` | 16 | yes | no | baalminion1 (medium) |

## Appendix C. Item codes not in D2R's armor, weapon or misc tables (codes only)

"dc6 in mod": the item icon is in the mod tree. "dc6 in D2R": a D2R file at that path (the stand-in). Two codes have neither.

| invfile | dc6 in mod | dc6 in D2R | item rows |
|---|---|---|---:|
| apple | yes | **no** | 14 |
| bird4 | yes | **no** | 1 |
| catal1 | yes | **no** | 1 |
| catal2 | yes | **no** | 1 |
| catal3 | yes | **no** | 1 |
| cherries | yes | **no** | 1 |
| evileye | yes | **no** | 5 |
| gemcontainer | yes | **no** | 1 |
| hardmode | yes | **no** | 1 |
| invbla | no | yes | 1 |
| invbonr3 | no | yes | 1 |
| invcndl | no | yes | 1 |
| invdss | no | yes | 1 |
| invfary3 | no | yes | 1 |
| invfary4 | no | yes | 1 |
| invgldm | no | yes | 1 |
| invgmb | no | yes | 1 |
| invgmr | no | yes | 1 |
| invgmv | no | yes | 1 |
| invgmw | no | yes | 1 |
| invgmy | no | yes | 7 |
| invgsaa | yes | **no** | 1 |
| invgsab | yes | **no** | 1 |
| invgsac | yes | **no** | 1 |
| invgsad | yes | **no** | 1 |
| invgsae | yes | **no** | 1 |
| invgsca | yes | **no** | 1 |
| invgscb | yes | **no** | 1 |
| invgscc | yes | **no** | 1 |
| invgscd | yes | **no** | 1 |
| invgsce | yes | **no** | 1 |
| invgsoa | yes | **no** | 1 |
| invgsob | yes | **no** | 1 |
| invgsoc | yes | **no** | 1 |
| invgsod | yes | **no** | 1 |
| invgsoe | yes | **no** | 1 |
| invgsta | yes | **no** | 1 |
| invgstb | yes | **no** | 1 |
| invgstc | yes | **no** | 1 |
| invgstd | yes | **no** | 1 |
| invgste | yes | **no** | 1 |
| invhscr2 | yes | **no** | 4 |
| invsbk2 | yes | **no** | 3 |
| invscb2 | yes | **no** | 1 |
| jbscross | yes | **no** | 200 |
| moon1 | yes | **no** | 1 |
| og1 | yes | **no** | 1 |
| og2 | yes | **no** | 1 |
| og3 | yes | **no** | 1 |
| og4 | yes | **no** | 1 |
| og5 | yes | **no** | 1 |
| pearl1 | yes | **no** | 50 |
| pearl2 | yes | **no** | 50 |
| pearl3 | yes | **no** | 30 |
| pearl4 | yes | **no** | 44 |
| pot04 | yes | **no** | 1 |
| r-a-01 | yes | **no** | 1 |
| r-a-02 | yes | **no** | 1 |
| r-a-03 | yes | **no** | 1 |
| r-a-05 | yes | **no** | 1 |
| r-a-06 | yes | **no** | 1 |
| r-a-07 | yes | **no** | 1 |
| r-a-08 | yes | **no** | 1 |
| r-a-09 | yes | **no** | 1 |
| r-a-10 | yes | **no** | 1 |
| r-a-11 | yes | **no** | 1 |
| r-a-12 | yes | **no** | 1 |
| r-a-13 | yes | **no** | 1 |
| r-a-14 | yes | **no** | 1 |
| r-a-15 | yes | **no** | 1 |
| r-a-16 | yes | **no** | 1 |
| r-a-17 | yes | **no** | 1 |
| r-a-18 | yes | **no** | 1 |
| r-d-02 | yes | **no** | 1 |
| r-d-04 | yes | **no** | 1 |
| r-d-05 | yes | **no** | 1 |
| r-d-07 | yes | **no** | 1 |
| r-d-11 | yes | **no** | 1 |
| r-d-12 | yes | **no** | 1 |
| realapple | yes | **no** | 1 |
| redgem | yes | **no** | 2 |
| ring01 | yes | **no** | 1 |
| ring03 | yes | **no** | 1 |
| ring06 | yes | **no** | 1 |
| ring07 | yes | **no** | 1 |
| ring08 | yes | **no** | 2 |
| ring09 | yes | **no** | 1 |
| s1 | yes | **no** | 1 |
| scroll11 | yes | **no** | 5 |
| shinieblue | yes | **no** | 6 |
| shiniegreen | yes | **no** | 8 |
| shiniepurple | yes | **no** | 8 |
| shiniered | yes | **no** | 7 |
| shiniewhite | yes | **no** | 18 |
| shinieyellow | yes | **no** | 7 |
| sigil1b | yes | **no** | 2 |
| sigil2b | yes | **no** | 2 |
| sigil3b | yes | **no** | 2 |
| sigil4b | yes | **no** | 1 |
| sigil5b | yes | **no** | 2 |
| sigil6b | yes | **no** | 2 |
| sigilxl | yes | **no** | 2 |
| skullstar | yes | **no** | 1 |
| stoneearth | no | **no** | 1 |
| stonemars | no | **no** | 1 |
| summbook | yes | **no** | 1 |
| zelixir1 | yes | **no** | 1 |
| zelixir2 | yes | **no** | 1 |
| zelixir4 | yes | **no** | 1 |
| zelixir5 | yes | **no** | 1 |
| zelixir6 | yes | **no** | 1 |
| zelixir7 | yes | **no** | 1 |
| zelixir8 | yes | **no** | 1 |

## Appendix D. Maps, missiles, overlays, unresolved names

**New DT1 (52), by tileset:**

- `expansion/dystopic`: docks.dt1, floors.dt1, interior.dt1, pyramid.dt1, ruinflr.dt1, ruinwall.dt1, terraces.dt1, treegrp.dt1, trees.dt1
- `expansion/magma`: floor.dt1, rocks.dt1, walls.dt1
- `expansion/neonmile`: bridge.dt1, buildings.dt1, buildingses.dt1, floors.dt1, gate.dt1, ground.dt1, keepwall.dt1, maingate.dt1, otherwalls.dt1, rkwall.dt1, terraces.dt1, townwalls.dt1, trees.dt1, wallrocks.dt1, walls.dt1, walls2.dt1
- `expansion/redsquare`: arch_walls.dt1, brick_walls.dt1, chain_walls.dt1, dist_wall.dt1, floor.dt1, inv_wall.dt1, weird.dt1
- `expansion/terror`: basewall.dt1, column.dt1, floor.dt1, frescoes.dt1, graveyrd.dt1, stained.dt1
- `expansion/voodoo`: floors.dt1, pygmy.dt1, ruin.dt1, terraces.dt1, treegrp.dt1, trees.dt1, walls.dt1
- `expansion/zakarum`: exterior.dt1, foregate.dt1, interior.dt1, plaza.dt1

**New DS1 (13):** `act1/cathedrl/inarius.ds1`, `act2/arcane/belial.ds1`, `act3/kurast/excelsior3.ds1`, `expansion/dystopic/desertpeak.ds1`, `expansion/ghetto/cypherpunk.ds1`, `expansion/glados/glados.ds1`, `expansion/icecave/rockisdead.ds1`, `expansion/morework/epicwhiners.ds1`, `expansion/neonmile/downtown.ds1`, `expansion/redsquare/moskvich.ds1`, `expansion/terror/borgir.ds1`, `expansion/voodoo/macumba.ds1`, `expansion/zakarum/charismatic.ds1`

**New missile DCCs (145):** adance, auraresistallfront, avatar, balefire, barrellol, biglightning, blackbolt, blackexplodecenter, blackfirebig, blackfiremedium, blackfiresmall, blackholeexplode, blackpentacle, blamf, bloodboom, bloodspear, bloodtrail, bloom, bluediabinferno, blueshockeffect, bluewizcast, boiling, bombchest, boneghost, boneghosttrail, bonespiritpurple, bonespiritred, bonespirityellow, bonfire, boombarrel, broadsider, carrionhawk, chicken, chickenlickin, chillbloodinitialpoof, coldfuse, cougarbolt, cow_eating, cowmoo, cross_statue, crystalbash, darkpurpleimpmissile, deathrock, demiphantom, discoball, discocrash, discoflare2, discohover, discoinferno, discotripbolt, doomsmoke, dopplezonexplodeblue, dopplezonexplodegreen, dopplezonexplodelilac, dragonbolt, duh, eaglebolt, eaglescream, earthslam, egg_alive, egg_dead, elemental, famfadekingsblue, fistofhell, flamepillar, flipbook, focusgreen, friendtrappy, frogsplash, frostghost, golddiabinferno, gore20, greathunt, greenexplode, greenflash, greenquake, greenshockeffect, groundfirepurple, hoamissileexplode, holyboltdeepblue, holyboltgreen, holyboltnew, iceberg, izual20, laughingghost, legiontile, lightandshadowstrike, lightningcircles, lightningexplosion, littlebirdie, littleredball, littlespider, livingearth, lorenado, megafire, megalith, newfiremissile, nuclear, onaplane, psiorb, psiorbexplode, psndeath1, psndeath2, purplefrostnova, radfield, radfieldaura, ratrace, receive_cold_spell, redscare, redscatter, redshockhit, redwizcast, runev, runex, scimitar6, shocker, shockhit, sigil_active, sigil_engaging, singleblueflame, snakie, somebluething, sparklez1, sparklez2, spinna, spinner, spinner2, summonah, summonahfrozen, sunfiremedium, swarmhovers, teethexplodegreen, teethexplodepurple, teethexplodered, teethexplodeviolet, tinyflame, tinylittleflame, towerdestroyed, towerstanding, turretdeath, turretstandingthere, violetlightning, vulturebolt, watersnake, whiteorbglowing

**New overlay DCCs (63):** angeldeath, apocmushroom2, aura130, aura230, baaldeathhead01, baaldeathmushroom, bigbass, bigblam, blackpentacle, bloodflashback, bloodflashfront, brsmokedt, brsmokenu, brsmokes1, circleofpower16, cleansingredback, cleansingredfront, doomportal, dustcloud01, elswarm, enragedz, baalteleport, icecavequest_magic, nehlithakglow, firecracker, firecrown, flashback, flashfront, focusgreen, fohpurple, ghostlights, ghostrising, goldaurafog, greenamp, greenaurafog, greenspell, heatwave, holymagik, manabubbles, massiveorange, massivestarter, mininova, mooncast, poisondark, poisonflashback, poisonflashfront, redaurafog, redring, redspell, rockon1, rockon2, rockon3, rockon4, slayercloud, sunburned, suncast, sunlight, treeaura, trinity15, whitering, wispybloodcast, yellowbigball, yellowskullpulse

**Unresolved (19):** File00000064.xxx, File00000082.xxx, File00000083.xxx, File00000098.xxx, File00000100.xxx, File00000105.xxx, File00000167.xxx, File00000169.xxx, File00000170.xxx, File00000171.dc6, File00000172.dc6, File00000173.dc6, File00000174.dc6, File00000175.dc6, File00000176.dc6, File00000177.dc6, File00000178.dc6, File00000192.xxx, File00000193.xxx

