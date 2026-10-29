# D2R baseline (build 93847)

Extracted with `tools/casc_extract.py` into `extract/d2r/93847/` (ignored by git).

## What D2R's CASC holds
- 175,823 named files; 24,497 are not downloaded locally (mostly other locales).
- Tables: 184 in `data/global/excel/` (RotW bank) and 177 in `data/global/excel/base/` (Classic/LoD).
- Strings: `data/local/lng/strings/*.json` (plus `strings-legacy/`, per-language folders, subtitles).
- Official data guide: `data/global/dataguide/` (210 html/js files).
- **Legacy 2D assets ship alongside HD**: 20,972 `.dcc`, 3,613 `.cof`, 1,337 `.dc6`, 266 `.dt1`, 2,277 `.ds1`
  under `data/global/`. Median's art uses these same formats, so legacy-graphics mode is the natural first
  target for Phase 5. Still to test: whether D2RLoader serves *modded* legacy files from the mod MPQ.

## Median 1.13c tables vs D2R columns
80 of Median's standard tables have a D2R equivalent; 22 have identical headers.
No D2R table: arena, chartemplate, hiredesc, monitempercent, uniquetitle, weaponclass.

Biggest gaps (columns D2R has that Median's 1.13c layout lacks / the reverse; some are renames):

| Table | +D2R | -MXL | Notes |
|---|---|---|---|
| skills | 74 | 9 | Param9-14 descriptions, new behavior flags |
| monstats | 32 | 14 | TreasureClass split, Desecrate/Herald flags |
| soundenviron | 26 | 13 | HD ambience |
| armor / weapons / misc | 20-24 | 17-18 | Anya rewards, advanced stash, quiver |
| charstats | 16 | 12 | potion %, skills per level |
| difficultylevels | 16 | 5 | mercenary/pet damage rules |
| monlvl | 15 | 0 | AC/DM per difficulty |
| hireling | 14 | 10 | resistances |
| runes | 8 | 27 | Median uses 13 property slots (vanilla 7) |

`txt-migrate` must map renamed columns, fill new D2R columns with safe defaults, and route columns
D2R lacks (e.g. extra rune slots) to custom tables or plugins.
