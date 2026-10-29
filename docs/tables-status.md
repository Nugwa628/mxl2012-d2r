# Tables status (lane tables)

Generated from `work/mod/migrate_report.md` of `py -3 tools/build.py --data-only` on the pure v005 MPQ (`extract-mpq`) and D2R 93847.
**validate.py: 0 errors in both banks** (170 plugin-class items, 13 warnings: `work/mod/validate_report.md`); `idmap.check_built` 0 errors;
`strings_check.py --rewritten` 0 errors, 0 cells that name a key neither the mod nor D2R defines (there were 104: section "Unresolved string keys" below). Rules: `docs/txt-migrate.md`.

| Table | Merge rule | Source rows (v005) | D2R rows | Built rows | Columns | Status / notes |
|---|---|---|---|---|---|---|
| arena | - | 1 | - | - | - | skipped: no D2R table (custom table / plugin) |
| armor | replace | 642 | 217 | 642 | 156 mapped, 11 D2R-only | done |
| armtype | keyed | 3 | 3 | 3 | 2 mapped, 0 D2R-only | done |
| automagic | replace | 470 | 44 | 470 | 36 mapped, 3 D2R-only | done |
| belts | indexed | 14 | 14 | 14 | 66 mapped, 8 D2R-only | done |
| bodylocs | keyed | 11 | 11 | 11 | 2 mapped, 0 D2R-only | done |
| books | by_row | 3 | 3 | 3 | 9 mapped, 0 D2R-only | done; by row (D2R names its tomes, the mod calls its rows `unused`) |
| charstats | indexed | 7 | 8 | 8 | 67 mapped, 15 D2R-only | done; D2R rows by class; Warlock row by d2r_adds (Median rules) |
| chartemplate | - | 30 | - | - | - | skipped: no D2R table (custom table / plugin) |
| colors | keyed | 21 | 21 | 21 | 2 mapped, 0 D2R-only | done |
| compcode | keyed | 115 | 115 | 115 | 2 mapped, 0 D2R-only | done |
| composit | keyed | 16 | 16 | 16 | 2 mapped, 0 D2R-only | done |
| cubemain | replace | 11477 | 155 | 11477 | 104 mapped, 2 D2R-only | done |
| cubemod | keyed | 13 | 12 | 13 | 2 mapped, 0 D2R-only | done |
| difficultylevels | keyed | 3 | 3 | 3 | 19 mapped, 15 D2R-only | done |
| elemtypes | keyed | 13 | 13 | 13 | 2 mapped, 0 D2R-only | done |
| events | indexed | 13 | 16 | 17 | 2 mapped, 0 D2R-only | done |
| experience | keyed | 123 | 101 | 123 | 9 mapped, 1 D2R-only | done; Median curve / MaxLvl 120; Warlock column filled by d2r_adds |
| gamble | replace | 1322 | 125 | 1322 | 2 mapped, 0 D2R-only | done |
| gems | keyed | 116 | 68 | 117 | 40 mapped, 0 D2R-only | done; keyed by item code (Sapphire = Saphire) |
| hiredesc | - | 9 | - | - | - | skipped: no D2R table (custom table / plugin) |
| hireling | replace | 120 | 135 | 120 | 70 mapped, 6 D2R-only | done; replace: RotW's extra mercenaries not merged; HireDesc codes -> D2R string keys |
| hitclass | keyed | 14 | 14 | 14 | 2 mapped, 0 D2R-only | done |
| inventory | d2r_only | 32 | 30 | 31 | 73 mapped, 0 D2R-only | done; D2R layout, per panel the larger grid (owner 2026-10-28): inventory 10x6 and cube 10x8 Median, stash / trade / vendor D2R (equal); Warlock rows = Assassin's; docs/hd-ui.md |
| itemratio | keyed | 6 | 6 | 6 | 20 mapped, 0 D2R-only | done |
| itemstatcost | indexed | 508 | 368 | 539 | 50 mapped, 1 D2R-only | done; 22 stats moved to 368-389; top id 538 (D2RLoader extended save); wording `_mxl` |
| itemtypes | itemtypes | 227 | 108 | 233 | 34 mapped, 6 D2R-only | done; D2R numbers kept (`warl` 67 ...), mod types from 109; check_built 0 errors |
| levels | indexed | 137 | 137 | 138 | 167 mapped, 18 D2R-only | done |
| lowqualityitems | replace | 9 | 4 | 9 | 1 mapped, 0 D2R-only | done |
| lvlmaze | indexed | 81 | 81 | 81 | 8 mapped, 0 D2R-only | done |
| lvlprest | indexed | 1101 | 1092 | 1102 | 23 mapped, 0 D2R-only | done |
| lvlsub | indexed | 34 | 34 | 34 | 22 mapped, 0 D2R-only | done |
| lvltypes | indexed | 36 | 36 | 36 | 35 mapped, 0 D2R-only | done |
| lvlwarp | by_row | 88 | 88 | 88 | 13 mapped, 2 D2R-only | done; by row (bug #260: keyed by Name, ten Act 5 rows were added twice); NoInteract / UniqueId from D2R |
| magicprefix | replace | 747 | 721 | 747 | 39 mapped, 0 D2R-only | done |
| magicsuffix | replace | 959 | 785 | 959 | 39 mapped, 0 D2R-only | done |
| misc | replace | 866 | 168 | 867 | 161 mapped, 10 D2R-only | done |
| misscalc | d2r_wins | 43 | 47 | 47 | 2 mapped, 0 D2R-only | done |
| missiles | indexed | 2665 | 736 | 2723 | 165 mapped, 5 D2R-only | done; ids remapped; sHitPar1 (hit 6) -> monstats ids; LevRange folded into Range; base bank padded with RotW rows |
| monai | indexed | 144 | 155 | 155 | 10 mapped, 0 D2R-only | done |
| monequip | keyed | 43 | 45 | 45 | 12 mapped, 0 D2R-only | done |
| monitempercent | - | 2 | - | - | - | skipped: no D2R table (custom table / plugin) |
| monlvl | keyed | 123 | 111 | 123 | 31 mapped, 0 D2R-only | done |
| monmode | keyed | 16 | 16 | 16 | 3 mapped, 0 D2R-only | done |
| monplace | keyed | 37 | 37 | 37 | 1 mapped, 0 D2R-only | done |
| monpreset | replace | 251 | 230 | 251 | 2 mapped, 0 D2R-only | done |
| monprop | indexed | 376 | 13 | 376 | 92 mapped, 0 D2R-only | done |
| monseq | keyed | 1402 | 1030 | 1422 | 5 mapped, 0 D2R-only | done |
| monsounds | indexed | 159 | 150 | 168 | 41 mapped, 0 D2R-only | done |
| monstats | indexed | 1822 | 751 | 1839 | 254 mapped, 18 D2R-only | done; 1088 own ids; D2R-only desecrate columns neutral |
| monstats2 | indexed | 1210 | 623 | 1224 | 120 mapped, 5 D2R-only | done; ids; BaseW enum fix |
| montype | indexed | 64 | 59 | 64 | 6 mapped, 1 D2R-only | done |
| monumod | indexed | 43 | 45 | 45 | 18 mapped, 0 D2R-only | done |
| npc | keyed | 17 | 17 | 17 | 19 mapped, 0 D2R-only | done |
| objects | indexed | 573 | 587 | 587 | 144 mapped, 1 D2R-only | done; 3 own ids; txt 574 vs bin 573 is the "Expansion" separator row (bin_check.py: no difference) |
| objgroup | indexed | 134 | 133 | 134 | 25 mapped, 0 D2R-only | done; txt 133 vs bin 134: same content (bin_check.py) |
| objmode | keyed | 8 | 8 | 8 | 2 mapped, 0 D2R-only | done |
| objtype | keyed | 573 | 573 | 577 | 2 mapped, 0 D2R-only | done |
| overlay | indexed | 524 | 333 | 565 | 22 mapped, 3 D2R-only | done |
| pettype | indexed | 66 | 22 | 68 | 20 mapped, 1 D2R-only | done |
| playerclass | d2r_wins_indexed | 7 | 8 | 8 | 2 mapped, 0 D2R-only | done |
| plrmode | keyed | 20 | 20 | 20 | 3 mapped, 0 D2R-only | done |
| plrtype | d2r_wins | 7 | 8 | 8 | 2 mapped, 0 D2R-only | done |
| properties | indexed | 543 | 284 | 559 | 30 mapped, 0 D2R-only | done |
| qualityitems | replace | 8 | 8 | 8 | 18 mapped, 0 D2R-only | done |
| rareprefix | replace | 77 | 46 | 77 | 13 mapped, 0 D2R-only | done |
| raresuffix | replace | 183 | 155 | 183 | 13 mapped, 0 D2R-only | done |
| runes | replace | 3133 | 181 | 3133 | 45 mapped, 4 D2R-only | done |
| setitems | replace | 299 | 140 | 300 | 93 mapped, 6 D2R-only | done; `spawnable` 1; items past 6 per set split |
| sets | replace | 67 | 35 | 68 | 68 mapped, 1 D2R-only | done |
| shrines | indexed | 23 | 23 | 23 | 13 mapped, 0 D2R-only | done |
| skillcalc | d2r_wins | 73 | 121 | 121 | 2 mapped, 0 D2R-only | done |
| skilldesc | keyed | 699 | 232 | 711 | 111 mapped, 8 D2R-only | done |
| skills | indexed | 1038 | 427 | 1110 | 247 mapped, 53 D2R-only | done; idmap ids (Warlock 373-402 stay D2R's); slots remapped; GH->SQ, stop functions; rightskill; Abyss / Ring of Fire / Apocalypse -> `_mxl` |
| soundenviron | d2r_wins_indexed | 50 | 76 | 76 | 20 mapped, 17 D2R-only | done |
| sounds | d2r_wins | 4900 | 11895 | 12101 | 19 mapped, 18 D2R-only | done; D2R wins; 206 mod-only rows (98 on a vanilla file's audio columns, 108 silent until ported) |
| states | indexed | 255 | 232 | 302 | 68 mapped, 5 D2R-only | done; 255 -> 302 rows (D2R's added states keep their ids); gfxclass remapped |
| storepage | d2r_wins | 4 | 4 | 8 | 2 mapped, 0 D2R-only | done |
| superuniques | indexed | 84 | 66 | 83 | 20 mapped, 3 D2R-only | done; Median's "Expansion" separator restored, ids are vanilla's (bug #362, id-mapping.md) |
| treasureclassex | replace | 1468 | 1138 | 1468 | 29 mapped, 6 D2R-only | done; 44 entries D2R cannot resolve cleared |
| uniqueappellation | replace | 25 | 25 | 25 | 1 mapped, 0 D2R-only | done |
| uniqueitems | replace | 2479 | 426 | 2479 | 67 mapped, 5 D2R-only | done |
| uniqueprefix | replace | 53 | 53 | 53 | 1 mapped, 0 D2R-only | done |
| uniquesuffix | replace | 69 | 69 | 69 | 1 mapped, 0 D2R-only | done |
| uniquetitle | - | 16 | - | - | - | skipped: no D2R table (custom table / plugin) |
| weapons | replace | 921 | 306 | 921 | 160 mapped, 8 D2R-only | done |

## Object ids and automap (lane objstr)

`tools/objstr.py` (data step; `work/mod/objstr_report.md`, tests `tools/tests/test_objstr.py`) checks the maps' object ids against the built
tables and writes `work/mod/ds1_ids.json` for the installer (`tools/ds1_remap.py`). Result on v005: **0 problems**.

| Question | Answer |
|---|---|
| Do the maps' object ids (`.ds1` type 2) need remapping? | **No.** The 34 maps hold 2,803 type-2 objects (157 distinct (act, id)); all of them are indexes of D2R's per-act `objpreset.txt`, whose `ObjectClass` names exactly one row of the built `objects.txt` (case-insensitive: D2R's own table spells `GuarDonaStick`, `EfLG`, `CHAn`), the row of the same position as the mod's (same `Name` for all 573), and `Maps.moved_objects()` is empty: Median's Objects rows keep D2R's ids |
| Why no ObjPreset of the mod? | `patch_d2.mpq` ships none: 1.13c resolved the ids with its own table, and D2R's per-act table is that table plus D2R's additions (act 5 has 154 rows in D2R, the maps use ids up to 149) |
| `ds1_remap.py` | monster ids as before (563 objects in 12 maps); new: the id table is a data-step product (`ds1_ids.json`: 1,822 monstats rows, 1,088 change; MonPreset rows per act 59/61/43/29/59) and `remap_tree()` works without the original extract. `tools/install_mod.py` calls `remap_tree(tiles)` with one argument: it works again |
| Automap rows (`automap.txt`) | **D2R's stay.** v005 has no `automap` table (not in `patch_d2.mpq`), no new level type (36 as D2R) and the built `lvltypes.txt` has D2R's names in D2R's order, so `AutoMap.txt`'s `LevelName`s find their level types as for the vanilla game. The 52 retextured `.dt1` carry the stock tile keys (maps-hd.md), so their tiles hit D2R's rows. No `automap.txt` / `objpreset.txt` is built (the merge rule would be "D2R's file"); `objects.txt` keeps the mod's `AutoMap` cel in all 573 shared rows (highest cel 1468, D2R's atlas ends at 1498) |
| Level types without an AutoMap row | `Act 5 - Town` (D2R has none either; nothing to merge) |

## Unresolved string keys (lane objstr, rewritten by lane text 2026-10-28; docs/text-audit.md)

`strings_check.py` reported 104 cells (both banks give the same list) that name keys neither Median's three `.tbl` nor D2R define. Median's
`patch_d2.mpq` ships all three tbl files, so 1.13c met the same miss for every one of them except the shrines, which 1.13c never read.
The decisions are rows of `data/string_gaps.tsv` (action `text`, `fix`, `cell`, `empty`; a reason column), applied by `tbl2json.py` (the texts),
`txt_migrate.py` (`shrine_strings`) and `tools/string_gaps.py` (data step: cells; it fails the build if a cell still names an unknown key).
Owner decision 2026-10-28 (no raw text anywhere a player sees it): the 46 names that showed their key and the description lines that were
emptied now have text in words; `tools/text_audit.py` (run by `strings_check.py`) fails the build on a new key-shaped name, placeholder,
"Missing string", empty name or `@key` in a layout. Now: **0 missing, 0 audit findings**, 50 more group 2 keys (the 46 names + 4 lines); the four Greater Elixirs' description keys stay undefined and their cells are emptied, as the original shows no line (bugs.md #104).

| Table.column | Key | Text it reads | Why |
|---|---|---|---|
| shrines.StringName / StringPhrase | `blah` (23 + 23 cells) | D2R's `ShrId<n>` / `ShrMsg<n>`, Median's wording | **port bug, fixed**: 1.13c never read the columns (Median's tbl has `ShrId0-22` / `ShrMsg0-22`, the d2r: overrides carry its wording) |
| misc.pSpell / spelldesc | `code=0g3` | cell set to `0` | Greater Elixir of Strength (0g3): the original's use does nothing. Its misc loader gives the unknown state name (`strpot` ... is not in states.txt) the value -1 and the item-spell handler for pSpell 9 (1.14d Game.exe 0x5beda0) returns 0 on a state <= 0, so the item stays and nothing is applied. D2R asserts there (SkillItem.cpp:823 spellState > 0) and then uses the elixir up; no item spell (pSpell 0) is the same to the player: it stays and nothing happens (bug #104) |
| misc.pSpell / spelldesc | `code=0g4` | cell set to `0` | Greater Elixir of Dexterity (0g4): the original's use does nothing. Its misc loader gives the unknown state name (`strpot` ... is not in states.txt) the value -1 and the item-spell handler for pSpell 9 (1.14d Game.exe 0x5beda0) returns 0 on a state <= 0, so the item stays and nothing is applied. D2R asserts there (SkillItem.cpp:823 spellState > 0) and then uses the elixir up; no item spell (pSpell 0) is the same to the player: it stays and nothing happens (bug #104) |
| misc.pSpell / spelldesc | `code=0g5` | cell set to `0` | Greater Elixir of Energy (0g5): the original's use does nothing. Its misc loader gives the unknown state name (`strpot` ... is not in states.txt) the value -1 and the item-spell handler for pSpell 9 (1.14d Game.exe 0x5beda0) returns 0 on a state <= 0, so the item stays and nothing is applied. D2R asserts there (SkillItem.cpp:823 spellState > 0) and then uses the elixir up; no item spell (pSpell 0) is the same to the player: it stays and nothing happens (bug #104) |
| misc.pSpell / spelldesc | `code=0g6` | cell set to `0` | Greater Elixir of Vitality (0g6): the original's use does nothing. Its misc loader gives the unknown state name (`strpot` ... is not in states.txt) the value -1 and the item-spell handler for pSpell 9 (1.14d Game.exe 0x5beda0) returns 0 on a state <= 0, so the item stays and nothing is applied. D2R asserts there (SkillItem.cpp:823 spellState > 0) and then uses the elixir up; no item spell (pSpell 0) is the same to the player: it stays and nothing happens (bug #104) |
| monstats.NameStr | `Id=boneprison1` | cell set to `skillname88` | Median's row has no name (D2R's own bone prison rows read d2r:skillname88, Median's text 'Bone Prison'); a hoverable monster with a token drew an empty label |
| monstats.NameStr | `Id=boneprison2` | cell set to `skillname88` | Median's row has no name (D2R's own bone prison rows read d2r:skillname88, Median's text 'Bone Prison'); a hoverable monster with a token drew an empty label |
| monstats.NameStr | `Id=boneprison3` | cell set to `skillname88` | Median's row has no name (D2R's own bone prison rows read d2r:skillname88, Median's text 'Bone Prison'); a hoverable monster with a token drew an empty label |
| monstats.NameStr | `Id=boneprison4` | cell set to `skillname88` | Median's row has no name (D2R's own bone prison rows read d2r:skillname88, Median's text 'Bone Prison'); a hoverable monster with a token drew an empty label |
| misc.spelldescstr | `PotColdReloadedDex` | (no line) | Greater Elixir of Dexterity (0g4) names a description key that no .tbl defines (Median's tbl has the unused PotOfDexReloadedDesc). The original shows NO line: its misc loader turns the unknown key into string 5382 and the tooltip builder skips a spell description of 5382 (1.14d Game.exe 0x4863a8, standing in for 1.13c). Bug #104, owner 2026-10-28 'match the original' |
| misc.spelldescstr | `PotFireReloadedDesc` | (no line) | Greater Elixir of Strength (0g3) names a description key that no .tbl defines (Median's tbl has the unused PotOfStrReloadedDesc). The original shows NO line: its misc loader turns the unknown key into string 5382 and the tooltip builder skips a spell description of 5382 (1.14d Game.exe 0x4863a8, standing in for 1.13c). Bug #104, owner 2026-10-28 'match the original' |
| misc.spelldescstr | `PotLtngReloadedDesc` | (no line) | Greater Elixir of Energy (0g5) names a description key that no .tbl defines (Median's tbl has the unused PotOfEneReloadedDesc). The original shows NO line: its misc loader turns the unknown key into string 5382 and the tooltip builder skips a spell description of 5382 (1.14d Game.exe 0x4863a8, standing in for 1.13c). Bug #104, owner 2026-10-28 'match the original' |
| misc.spelldescstr | `PotPoisReloadedDesc` | (no line) | Greater Elixir of Vitality (0g6) names a description key that no .tbl defines (Median's tbl has the unused PotOfVitReloadedDesc). The original shows NO line: its misc loader turns the unknown key into string 5382 and the tooltip builder skips a spell description of 5382 (1.14d Game.exe 0x4863a8, standing in for 1.13c). Bug #104, owner 2026-10-28 'match the original' |
| (Median's own text) | `New2PortalKombat` | Portal Kombat | unique item New2PortalKombat: Median's own text 'PortalKombat' has no space (a pun on Mortal Kombat); split like a CamelCase key |
| (Median's own text) | `StataMater` | Stata Mater | runeword name StataMater (runes.name, 6 rows): Median's own text 'StataMater' has no space; split like a CamelCase key (the spelling is Median's) |
| itemstatcost.descstrneg / descstrpos | `ModitemColdSkills` | to Fire Skills | item_elemskill is D2R's 'to Fire Skills' stat (126, property fireskill; D2R prints '+12 to Fire Skills', Median's own ModStr3i text is 'to Fire Skills'); Median's key name says Cold but nothing in its tables gives the stat. descfunc 1 descval 1 = '+N <text>' |
| itemstatcost.descstrneg / descstrpos | `ModitemLevReq` | Required Level | item_levelreqpct (94) changes the item's Required Level by a percentage (op 1 on item_levelreq); Median's wording for the related stat item_req_percent is 'Requirements +10%'. descfunc 4 descval 2 = '<text> +N%' -> 'Required Level +10%'. No property or item of Median gives the stat |
| itemstatcost.dgrpstrneg / dgrpstrpos | `ModitemPeril` | to Melee Damage | passive_mastery_melee_dmg (343) is the weapon mastery's melee damage percent (skills Elfin Arrows / Item Elfin Arrows set it); Median's group line was descfunc 3 descval 0 = the text alone, which cannot show the value, so the group line becomes descfunc 4 descval 1 = '+N% <text>' like the ModitemAllsk group ('+N% to Spell Damage'). No property or item of Median gives the stat |
| levels.levelwarp | `To The Pandemonium Run 1` | To The Pandemonium Run 1 | the key is already the wording; Median's other warps read 'To The <level>' (e.g. 'To The Pandemonium Fortress') |
| levels.levelwarp | `To The Pandemonium Run 2` | To The Pandemonium Run 2 | the key is already the wording; Median's other warps read 'To The <level>' (e.g. 'To The Pandemonium Fortress') |
| levels.levelwarp | `To The Pandemonium Run 3` | To The Pandemonium Run 3 | the key is already the wording; Median's other warps read 'To The <level>' (e.g. 'To The Pandemonium Fortress') |
| misc.namestr | `bpl` | Large Blue Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| misc.namestr | `bps` | Small Blue Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| misc.namestr | `hpf` | Full Healing Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| misc.namestr | `hpo` | Healing Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| misc.namestr | `mpf` | Full Mana Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| misc.namestr | `mpo` | Mana Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| misc.namestr | `rpl` | Large Red Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| misc.namestr | `rps` | Small Red Potion | beta-era potion row kept by Median (spawnable 0, in no treasure class, recipe or shop); the row's own name column says so |
| monstats.descstr | `mon_dark_ones` | Divine Apparition, Superbeast, Tremor Attack | description of dark_kid (Median's Dark Nephalem, level 90): its skills Enemy Divine App and N Superbeast and the Tremor its monprop casts on attack; same style as mon_icebeam 'Cold Hit Ice Beam Attack' |
| monstats.namestr | `Act 5 Hireling 1hs` | Barbarian | act5hire1: the Act 5 hireling (AI Hireable; hireling.txt names the class 'Barbarian'); the player sees the mercenary's own name, this is the class name |
| monstats.namestr | `Act 5 Hireling 2hs` | Barbarian | act5hire2: as act5hire1 (two-handed variant) |
| monstats.namestr | `Bunny` | Bunny | bunny: the critter (token 48); the key is already the word |
| monstats.namestr | `CouatlInhibitor` | Couatl Inhibitor | Median's own tbl has this monster as 'CouatlInhibitr' = 'Couatl Inhibitor' (a typo in the monstats key) |
| monstats.namestr | `CrusaderSpirit` | Crusader Spirit | crusaders (Paladin summon, AI NecroPet); Median's skill reads 'Summon Crusader Spirit' |
| monstats.namestr | `CrystalBall` | Crystal Ball | quest_crystal; Median's tbl has 'Crystal Ball' (key with a space) and mon_shieldfull 'Kill Crystal Ball to Remove Immunity' |
| monstats.namestr | `GlassSkull` | Glass Skull | quest_icedemon; Median's superunique reads 'Glass Skull the Jagged' |
| monstats.namestr | `Injured Barbarian 1` | Injured Barbarian | injuredbarb1, a wounded Barbarian of the Act 5 story; the three variants read alike |
| monstats.namestr | `Injured Barbarian 2` | Injured Barbarian | injuredbarb2, a wounded Barbarian of the Act 5 story; the three variants read alike |
| monstats.namestr | `Injured Barbarian 3` | Injured Barbarian | injuredbarb3, a wounded Barbarian of the Act 5 story; the three variants read alike |
| monstats.namestr | `LandsharkInhibitor` | Landshark Inhibitor | Median's own tbl has 'LandsharkInhbitor' = 'Landshark Inhibitor' (a typo in the monstats key) |
| monstats.namestr | `Pandora` | Pandora | uberandariel (bug #18): the hover label comes from the d2r:Lilith override; the key is already the word |
| monstats.namestr | `Worldstone Effect` | Worldstone Effect | worldstoneeffect (token K9, AI Idle, level 0): an effect carrier the player never meets; the key is already words |
| montype.strplur | `ClawVipers` | Claw Vipers | viper monster type; Median's tbl has 'ClawViper' only as a line key |
| montype.strplur | `Humans` | Humans | human monster type; the key is already the word |
| montype.strplur | `Magi` | Magi | mage monster type; the key is already the word |
| montype.strplur | `Vamps` | Vampires | vamp monster type (Vampiress, Vampire Priest...); the plural is spelled out |
| objects.name | `BBQB` | Barbecue | object BBQ (token 29, not selectable); spelled out |
| objects.name | `ControlObject` | Control Object | placeholder object (token ss, Selectable 0, not drawn): a spawn marker the player never sees; text for completeness |
| objects.name | `DesertShrineArmor` | Armor Shrine | Desert Shrine Armor spawn marker (token ss, not drawn, not selectable): the shrine that spawns reads D2R's name for it |
| objects.name | `DesertShrineCombat` | Combat Shrine | Desert Shrine Combat spawn marker (token ss, not drawn, not selectable): the shrine that spawns reads D2R's name for it |
| objects.name | `DesertShrineRecharge` | Recharge Shrine | Desert Shrine Recharge spawn marker (token ss, not drawn, not selectable): the shrine that spawns reads D2R's name for it |
| objects.name | `DesertShrineResist` | Resist Shrine | Desert Shrine Resist spawn marker (token ss, not drawn, not selectable): the shrine that spawns reads D2R's name for it |
| objects.name | `DesertShrineSkill` | Skill Shrine | Desert Shrine Skill spawn marker (token ss, not drawn, not selectable): the shrine that spawns reads D2R's name for it |
| objects.name | `DesertShrineStamina` | Stamina Shrine | Desert Shrine Stamina spawn marker (token ss, not drawn, not selectable): the shrine that spawns reads D2R's name for it |
| objects.name | `Keeper` | Keeper | DummyEx107 (token 7z, drawn, not selectable); the key is already the word |
| objects.name | `PlaceArcaneThingamajig` | Arcane Thingamajig | spawn marker ('Places a thingamjig' in the row's description) |
| objects.name | `PlaceRandomTreasureChest` | Treasure Chest | spawn marker ('Places a random treasure chest') |
| objects.name | `PlaceUniqueChest` | Unique Chest | spawn marker ('Places a Unique Chest') |
| objects.name | `Zoo` | Zoo | DummyEx106 spawn marker (token ss); the key is already the word |
| objects.name | `btor` | Torch | BaalTorch (token 25, not selectable); D2R's torches read 'Torch' |
| objects.name | `burninglogs` | Burning Logs | BurningLogs (token 9i, not selectable); spelled out |
| objects.name | `funeralpire` | Funeral Pyre | FuneralPyre (token 9h, not selectable); the key is Median's misspelling of 'pyre' |
| objects.name | `stma` | Steam | IceCaveSteam (token 2o, not selectable) |
| pettype.name | `CrusaderSpirit` | Crusader Spirit | pet type crusaderspet (monster crusaders): same name as the monster |
| superuniques.name | `Ghosthoof the Possessed` | Ghosthoof the Possessed | the key is already the name |

Near-miss keys (`CouatlInhibitor` / `CouatlInhibitr`, `CrystalBall` / `Crystal Ball`, `ClawVipers` / `ClawViper`) are Median's own typos in
the monstats / montype key; they stay separate keys but read Median's text. What 1.13c shows for an unknown key was never verified
(a name field most likely shows the key); the port no longer does.
