# txt-migrate: Median XL 2012 tables -> D2R layout

Lane `tables`. Source: the pure v005 MPQ (`patch_d2.mpq` alone, `mxl2012-runs/extract-mpq`), which ships 93 real `.txt` tables
(no `.bin` decoder is needed; `tools/bin_check.py` compares the two where they could differ). Target: D2R 3.3 build 93847's
two table banks. Nothing here serves a
D2Sigma DLL (aura / damage / cooldown / pet plugin headers, item spells, proxies, extra calc codes, vendors, stat screen,
`.bin` decoders), because Median XL 2012 has no engine DLL.

```
py -3 -I tools/build.py [--data-only]        # the whole chain; --data-only stops after validate.py
  mxl2012_prep.py                            # extract-mpq tables -> work/named/ (UTF-8, normalised)
  tbl2json.py --excel-dir work/named         # strings -> work/mod/data/local/lng (docs/strings.md)
  txt_migrate.py                             # D2R layout -> work/mod/data/global/excel/{base,}   (this document)
  d2r_adds.py --mod work/mod --d2r <extract> # D2R's own additions off / Warlock follows Median (docs/d2r-additions.md)
  warlock_scale.py apply --mod work/mod      # Warlock skills on Median's rules and power (data/warlock_rules.tsv, data/warlock_balance.tsv, docs/warlock-balance.md)
  string_gaps.py apply                       # keys no .tbl defines: names = their own text, description lines emptied (data/string_gaps.tsv)
  objstr.py                                  # map object ids vs D2R's ObjPreset, automap, work/mod/ds1_ids.json (docs/id-mapping.md)
  strings_check.py --rewritten               # string keys of the migrated tables
  merge_string_overrides.py                  # skill_tab_titles.json (ui lane) into mxl2012/overrides.json
  validate.py                                # D2R schema checks -> work/mod/validate_report.md
```

Environment: `MXL2012_SRC` (the MPQ extraction's `data/global/excel`; default `<R>/mxl2012-runs/extract-mpq/...`),
`MXL_D2R_EXTRACT` (D2R 93847's extraction, read-only; default `extract/d2r/93847` in the repo). Output (git-ignored,
Median-derived): `base/` (Classic/LoD header) and the RotW folder, both written, because which bank a Median character loads
is still to be confirmed in game. Report: `work/mod/migrate_report.md`; values D2R has no column for: `work/mod/overflow/`;
references the clean-up emptied: `work/mod/dangling_refs.tsv`. Per-table result: `docs/tables-status.md`.

## What `mxl2012_prep.py` does

- Bytes are cp1252-ish, not UTF-8. `0xB5` (µ) is a letter of 24 item codes (`µ01`, `6oµ`) in misc / cubemain /
  treasureclassex; D2R item codes are four raw bytes, so it becomes `^` (no other code uses it; the art lane has to map the
  codes). `0xA0` -> space, `0x85` -> `...` (comment cells). CRLF, rows padded / cut to the header.
- Not written (nothing reads them): `treasureclass` (the unused classic pair, engine-triage), `uniqueitems2`, `aiparms`,
  `cubetype`, `monname`, `weaponclass`.
- Formula names of 32+ characters (D2R's parser keeps 31, trap 8) get a compact key `name[:24]_<5 hex>` in the key row, every
  reference (`idmap.NAME_REFS`) and every formula; in v005 that is one stat (`skill_shadows_addcorpseonstriking`).

## Row ids: `tools/idmap.py`

The ID mapping is the idmap lane's (`docs/id-mapping.md`). txt_migrate builds `IdMap` once on `work/named` and runs
`remap_table` on each mod table **before** any D2R row is merged: own-id columns, numeric references (cubemain `param` stat ids,
missiles `sHitPar1` of hit function 6, `missiletype`, states `gfxclass`, item property parameters, ...), renamed keys
(`Sword Mastery` -> `Blade Mastery`, `nehlithak*` -> `nihlathak*`, `Abyss` / `Ring of Fire` / `Apocalypse` -> `_mxl`), formula names and
the function slots (srvdofunc 109 -> 9, srvstfunc 64 / 37+109 -> 67, cltstfunc 82 -> blank, cltdofunc 22 -> the plugin's 113,
missiles pCltDoFunc 11 -> 69 / 70 for the corpse explosions). `idmap.check_built` runs on both built banks at the end and
fails the step on a moved fixed item type id.

A renamed skill takes its `skilldesc` row with it (`abyss` -> `abyss_mxl`): the keyed merge would otherwise give D2R's Warlock
skill Median's description and tree slot.

## Row merge by table kind

| Kind | Tables | Rule |
|---|---|---|
| indexed | `idmap.ENTITIES`: skills, states, itemstatcost, missiles, monstats, monstats2, overlay, properties, levels, objects, superuniques, events, pettype, montype, monumod, monprop, monsounds, monai, lvltypes, lvlprest, lvlmaze, lvlsub, objgroup, shrines, belts, charstats | `m.order(entity)`: output row *i* is the mod row whose new id is *i*, else D2R's row *i* (D2R's added rows keep their ids; the mod's new rows follow D2R's last row). The base bank is shorter than RotW for skills / missiles / overlay / events / levels: it borrows the RotW rows so both banks have the same ids |
| d2r_wins_indexed | soundenviron, playerclass | the same order, but a row that matches D2R's is D2R's |
| itemtypes | itemtypes | `idmap.align_item_types`: every D2R type at its D2R number (`warl` 67, `csch` 108 ...), the mod's own types from 109; the engine tests fixed numbers (h2h 68, pelt 73, rune 75, hpot 77 ...) |
| replace | weapons, armor, misc, uniqueitems, setitems, sets, magicprefix / suffix, automagic, rareprefix / suffix, runes, cubemain, gamble, treasureclassex, hireling, monpreset, qualityitems, lowqualityitems, unique prefix / suffix / appellation | the mod's rows only. Median replaced the vanilla item bases and pools; D2R's own uniques, sets, runewords, recipes, TC entries and mercenary rows are not merged back (`tables-status.md`: output rows = mod rows) |
| d2r_wins | sounds, skillcalc, misscalc, plrtype, storepage | D2R rows, then the mod's rows with keys D2R lacks (sounds: `sound_rows` gives them a vanilla file's D2R audio columns where a vanilla sound is the template) |
| d2r_only | inventory | D2R's file (two rows per page and resolution; it asserts on any other layout) with the mod's grid sizes copied in by class name (player 10x6, transmog box 10x8, big stash 10x10); `Warlock` / `Warlock2` take the Assassin's, so the HD layout shared by all classes works |
| by_row | books, lvlwarp | the mod's row *i* is D2R's row *i* (books: the mod calls its three rows `unused`, D2R names its tomes; lvlwarp: 1.13c names both directions of five Act 5 warps alike where D2R adds " L" / " R", bug #260); an "Expansion" separator stays where D2R has it |
| keyed | the rest | the mod's rows, then D2R's rows whose key the mod lacks. Gems are keyed by item **code** (D2R's `Sapphire` is Median's `Saphire`, same codes); monseq has several rows per key and is merged group by group |

## Columns

- Same name (case-insensitive) copies. Renames (`RENAMES`): `Hralti*` -> `Hratli*`, `Drehya*` -> `Anya*`, monstats
  `TreasureClassN` -> `TreasureClass`/`Champ`/`Unique`/`Quest`, `NoShldBlock` -> `ShieldBlockOverride`, levels `MonLvl1` ->
  `MonLvl`, skills `delay` -> `localdelay`, uniqueitems `enabled` -> `spawnable`, itemtypes `MaxSock1/25/40` -> `MaxSockets1/2/3`, shrines,
  soundenviron `EAX *` -> `SFX EAX *`, ...; hireling `Resist` feeds the four resistance columns; missiles `LevRange` is folded
  into `Range` (`range+levrange*lvl`).
- Dropped on purpose (`OBSOLETE`, 1.13c columns D2R removed): ids, `Beta`, `Expansion`, `eol`, sound reverb / cache columns ...
  Anything else without a D2R column goes to `work/mod/overflow/<table>.txt`.
- **D2R-only columns are neutral (empty) by default**, also on a row that matches a D2R row: ladder seasons, sunder flags, the
  mercenary class-item column, Terror Zone treasure classes, loot-filter categories and the like are D2R features the mod
  never had. The explicit list of columns the game needs (`NEEDED_FROM_D2R`, a matching row takes D2R's value) and constants
  (`CONSTANTS`, all rows):

  | Table | Columns | Why |
  |---|---|---|
  | difficultylevels | all D2R-only | PvP / mercenary / Prime Evil damage percentages, hit-react buffers (0 would be 0 % damage) |
  | charstats | SkillsPerLevel, LightRadius, MinimumCastingDelay, item1-10quality | functional; `HealthPotionPercent` / `ManaPotionPercent` are constants 100 (D2R scales per class, 1.13c does not) |
  | hireling | HiringMaxLevelDifference per Version from D2R's rows (classic 5, expansion 1; `hireling_level_difference`, bug #241); constants resurrectcostmultiplier 15, divisor 2, max 50000 | hire range and resurrection price |
  | levels | PreventTownPortal | the towns and the Pandemonium finale (1.13c: code) |
  | lvlwarp | NoInteract, UniqueId | warp identity, clickable trap doors |
  | objects | Class | the class name D2R's code references an object by |
  | belts | defaultItem* | controller auto-populate |
  | skills | rightskill | 0 keeps passives off the right-button list. D2R reads **blank as 0** (bug #16: Blackstorm could not be selected), so `skill_rules` fills every blank: 0 for a passive or a row with no start / do function, missile or aura, else 1 (1.13c has no such column: any usable skill goes on the right button) |
  | setitems | constant `spawnable` 1 | a set item is a random drop only when 1 (1.13c: all) |
  | armor / weapons | constant `TMogType` xxx | "no transmog" |
  | overlay | Character (when the mod's cell is empty) | the HD overlay folder; without it D2R draws no HD overlay |
  | misc | pSpell of `ass`, `xyz`, `tr2`, `toa` (when the mod's cell is empty; `D2R_WHEN_EMPTY_ROWS`) | 1.13c runs these item uses by item code, D2R by pSpell 10 / 11 / 12 / 13 (bug #240) |
  | misc (via `book_cursors`) | spellicon of the books.txt scroll / tome codes = that row's `SpellIcon` | 1.13c takes a scroll's / tome's cursor from books.txt, D2R from misc `spellicon` (Median: -1 everywhere): `isc` / `ibk` get 0, the identify cursor (bug #485) |
  | skills (via `conversion_calcs`) | calc1 `dm56` / calc2 `par3` of every srvdofunc 51 row whose cell is blank | 1.13c's conversion (Mind Blast, Median's charms, Elvensong's spirit) takes the chance from Param5 / Param6 and the length from Param3 + rand(Param4); D2R evaluates calc1 / calc2 instead (its own Mind Blast row was moved the same way). Blank cells meant a 1 % chance and a 0-frame charm (bug #487); a set cell (Black Sleep's calc1 100) is kept |
  | plrmode / monmode | Code (always D2R's) | 1.13c spells Sequence and Knockback `GH`, D2R `SQ` / `KB` (trap 1) |
  | objects | Token `sl` -> `9c` (`D2R_RENAMED`: only a cell that still holds 1.13c's value, on a row where D2R holds the new one) | UnfoldingStairLeft (row 194): D2R ships this stair's art and animation data as `9c` and has no `sl`; with `sl` the stair never unfolds and blocks the Kurast temple doorway (bug #518). Token `xx` -> `az`: ShrineMagicArcaneSanctuary1 (row 133), D2R and 1.14d have no `xx` art, so the Arcane Sanctuary's magic shrine was invisible in legacy graphics (bug #520); D2R's own HellBridge (row 375) keeps `xx`. Rows whose token D2R changed while the old art is still there (45, 277, 361, ...: "Rename audit" below; 284 differs only in case) stay as Median has them |
  | skills (via `skill_rules`) | srvstopfunc / cltstopfunc | a mod row on a do function D2R pairs with a stop function (Whirlwind) gets D2R's; GH -> SQ in anim / seqtrans |
  | itemtypes | MaxSocketsLevelThreshold1/2 = 25 / 40 | 1.13c's fixed socket thresholds |

- Number cleaning: values above 2^31 become signed (`-1` as 4294967295, trap 4; experience.txt keeps its unsigned values), a few
  raw control characters become numbers, booleans other than 0/1 become 1.
- **missiles `SrcDamage` is copied as is** (lane srcdamage): D2R 93847 reads it the way 1.13c / 1.14d do, so Median's 160-255
  values (47 rows) and its -1 cells need no conversion. It is an unsigned byte (D2R record +0x155, 1.14d +0x12d, field type
  4 like `Red`; -1 is kept as 255), the share of the source's damage in 1/128ths: on a missile with a `Skill` (or
  `MissileSkill`) the skill's `SrcDam` is used instead and the missile's own value only matters as 255 / -1 (= no weapon
  damage); on any other missile its own byte (-1 = 255 = 199%). `Half2HSrc` halves it for a two-handed source. The share
  multiplies weapon min / max and the elemental fields linearly (addresses in d2r-addresses.md, "Missile damage"). A
  `Skill` name Median's skills.txt has no row for (144 rows name vanilla skills Median renamed, e.g. `poisonjavcloud`'s
  "Poison Javelin") is emptied, which is what 1.13c ran (Median's missiles.bin holds -1 there): those rows take their own
  byte. `tools/srcdamage.py` lists each row's share; validate.py warns on a cell outside -1..255 (the byte wraps).

## Fixes for D2R's loader (the mod's own data, `clean_references`)

1.13c's compiler tolerates what D2R's loader refuses. Per bank, over every migrated table:
a reference cell whose value differs from the target key only in case takes the target's spelling; a reference to a row that
does not exist is emptied (listed in `dangling_refs.tsv`; checked against the mod's compiled `missiles.bin`, where those cells are
0xFFFF too); required links (`monstats.MonStatsEx`) fall back to the first row of the target table; an invalid enum value
(`monstats2.BaseW`) becomes `hth`; an invalid property code is emptied. Formulas (`tools/formula_fix.py`): stray quotes and `;`
fixed, `ulvl` in Item scope -> `stat('level'.accr)`, calls naming a missing skill / missile / stat -> `0`, unknown calc codes -> `0`,
missing closing brackets appended, negative literals `-N` -> `(0-N)`, non-trivial ternary branches bracketed (D2R's parser, trap
9). The 255-character formula limit is checked by validate.py (v005 has no formula over it). A missiles function cell that is text (`*12` of royalstrikechainlightning) is emptied.

A state's stat list reaches the client with each stat cut to its itemstatcost `Send Bits`. `modifierlist_skill` (350) has 9 in D2R and 1.13c, too few for Median's skill ids (up to 1109), and D2R's client skill do dispatcher asserts `nSkillCastId` when the caster's `aurastate` list names another skill (bug #20). `stat_send_bits` raises the column to the bits of the highest skill id (11).

A misc item spell whose timed state 1.13c skipped in silence (a state name states.txt lacks, emptied above, or a `len` <= 0)
makes D2R assert `spellState > 0` (SkillItem.cpp:545 / :823) or `len` > 0 (:548 / :826) on the drink (bug #191). After
`clean_references`, `item_spell_states` gives such a pSpell 6 row (cures, then the state step) the empty state `healthpot`
for 1 frame with no stats, so the cures run and nothing else is applied, as in 1.13c (`yps`, `wms`, `ey9`), and such a pSpell
9 row (state only) pSpell 0, so the use is refused and the item kept, as in 1.13c (`hrb`, `eo7`-`eo9`, `ey1`, `ey5`-`ey8`,
`0g3`-`0g6`); listed in `migrate_report.md`.

D2R's client nova (cltdofunc 25) asserts `nMissile >= 0` and draws nothing for a row without cltmissilea; `skill_rules` empties cltdofunc on those 11 rows (bug #51, listed in migrate_report.md).

An item base with `unique` 1 (always created as a unique) needs a `uniqueitems` row: without one D2R saves unique index 4095 and the character asserts when loaded (bug #7, the starting kit's Median Statue `zen`). `clear_unique_flags` sets `unique` to 0 on weapon / armor / misc bases that have no uniqueitems row and that D2R's own tables do not flag (D2R's quest bases keep it).

A `monprop` event property (`hit-skill`, `kill-skill`, `death-skill`, `att-skill`, `gethit-skill`, `levelup-skill`: the properties whose stat is an `item_skillon*` one) on a skill with no `ItemEffect` makes D2R assert `ptSkill->nItemEffect != 0` when the event fires (bug #32). 1.13c ran nothing for it, so `monprop_event_skills` empties those properties (24 cells: hornedgods, elite_goatpriest5 / A, dark_master1 / 2, dark_convert(_old), dragoncompanions; listed in `migrate_report.md`). The same case on items stays (tooltips, bug #40).

From the crash audit ([crash-audit.md](crash-audit.md)): `skilldesc_lines` gives a skilldesc line that lacks a
string its D2R line type needs the text D2R's own rows use for that type (1.13c hard-coded 13 "Life", 34 "Damage", 41 "Fire
Damage"; 22 lines) and drops a line with no such text (Lion Stance's type 7; C1, `stringIndex1 != strdummy`);
`blank_item_skilldesc` points the 4 skills an item property names that have no skilldesc at an empty row `mxl_blank` (C11,
`nDesc` assert); `raven_counts` gives Wolf Companion and SorcFamiliar (Raven AI pets) calc3 `ln12`, the hit counter D2R
reads there instead of 1.13c's Param1 (C15: the pet died on its first think).

Other D2R-engine fixes: treasure classes D2R cannot resolve are cleared (`clean_treasure_classes`), monster
presets / mazes are claimed and maze start positions fixed, set items past 6 move to `<set> (2)`
(`split_large_sets`), skills without a skilldesc use `attack`, hireling `HireDesc` codes map to D2R's string keys (`HIREDESC_KEYS`).
The 44 cleared treasure class entries name nothing in Median's tables either and sit in classes no monster, object or recipe
reaches (`docs/median-rules-audit.md` DR2); no Median 2012 set has more than 6 items, so `split_large_sets` changes nothing here.

A cubemain input that names nothing (row 10627's `o^o`) is emptied by `cube_unresolved_inputs`: 1.13c compiles it to an empty
slot (Median's cubemain.bin) and D2R passes an empty slot the same way (bug #311). Columns D2R's parser reads although D2R's own
file lacks them are added to the header (`EXTRA_COLUMNS`): misc `auto prefix`, which D2R's shared weapons / armor / misc field
list holds (bug #310).

## Localization cells (docs/strings.md)

`namespace_cells` is the last pass: every cell of a localization column that names a Median-only key is written `mxl2012:<key>`
(short alias where the field is too small), references to unique / set item names follow (`strings_ns.qualify_reference`);
cells that name a D2R key stay unqualified. `median_stat_wording` points itemstatcost description cells at the mod's text
(`<key>_mxl`, kept alias) except for the descfuncs where D2R formats a text of its own. `median_skill_wording` does the same for skilldesc text cells of the line types D2R still builds by appending (all of 1.13c's but 13, 34, 36, 40, 53-56, 66, 74, 75: `strings_ns.SKILLDESC_FORMAT`) and gives a blank mana cost label (type 1) the row's `str mana` key, which D2R no longer reads (bugs.md #396). `strings_check.py --rewritten` validates
the result (0 errors, 0 missing keys). v005 named 104 cells per bank that neither its tbl nor D2R define: the 46 `blah` cells of `shrines.txt`
are fixed in `shrine_strings` (rows take D2R's `ShrId<n>` / `ShrMsg<n>`), the other 58 are decided per key in `data/string_gaps.tsv` and
listed in `tables-status.md` (names show their key as in 1.13c, description lines are emptied).

## Warlock balance (`warlock_scale.py apply`, after `d2r_adds.py`)

Owner decisions 2026-10-28: D2R's Warlock skills (ids 373-402) are scaled to Median 2012's power (round 1) and follow Median's
own skill rules (round 2: the skpoints gate, the character-level synergy calcs, Median's summon and weapon-skill patterns and
their tooltip lines). The step writes `data/warlock_rules.tsv` (366 formula / text cells: skills, skilldesc), then
`data/warlock_balance.tsv` (305 number cells: skills, missiles `abysscenter`, monstats `wargoatman` / `warbighead` /
`warputriddefiler`) into the RotW bank and stops on a cell that holds neither the recorded value before nor the new one (refit
with `warlock_scale.py fit`); the Classic/LoD bank's Warlock rows are id placeholders and are not written. Method, comparables and the per-skill table:
`docs/warlock-balance.md`.

## Rename audit (`tools/rename_audit.py`, lane renamesweep)

Bug #518 came from one cell that kept a vanilla value D2R had renamed. `py -3 -I tools/rename_audit.py [--bank rotw|base]`
looks for every other cell of that class. It checks each art / file / code / sound name the built tables carry (objects Token,
monstats Code, missiles CelFile and sounds, overlay Filename, item inv / flippy / alternate graphics, itemtypes InvGfx, lvlprest
File1-6, lvltypes File 1-32, sounds FileName and every sound column). It compares Median's value, 1.14d's (read from the native
install's `.bin` tables), D2R's for the matching row (idmap id, or the key of a keyed table) and the built one. It also notes
where the asset exists (D2R's CASC, the mod, Median's MPQ, 1.14d's MPQs). It writes `work/mod/rename_audit.{tsv,md}`. The
verdicts are in the tool's docstring. Run of 2026-10-31 (rotw; base gives the same hits on other row ids):

| Table | ok | d2r-same | Hits | Triage |
|---|---|---|---|---|
| objects | 556 | 2 | 1 renamed, 2 renamed-fixed, 12 renamed-exists (before the #520 fix: 2 renamed, 1 renamed-fixed) | below |
| misc | 2977 | 1 | 479 median-missing | Median's own sounds (`shrine_boink` etc.), Clue Gem / `ab!` flippy `flpdss` / `flptail` and `zog` / `zoh` inventory art: known gaps (unported.md, legacy-graphics.md) |
| missiles | 3563 | 0 | 1 missing, 30 median-missing, 9 emptied | sounds Median added (silent until the audio port); `emptied` = art_fix's DRAW_NOTHING rows and sound keys Median's own sounds.txt lacks |
| skills | 984 | 0 | 49 median-missing, 5 emptied | Median's own sounds; dangling sound keys Median had |
| sounds | 4556 | 71 | 108 median-missing, 1 emptied | Median's 108 own sounds (`sound_rows`: silent until ported) |
| monsounds | 898 | 1 | 18 median-missing | Median's own sounds |
| states | 230 | 0 | 1 missing, 17 median-missing | Median's own sounds |
| uniqueitems | 14 | 0 | 12 median-missing | Median's own sounds |
| overlay | 512 | 0 | 4 emptied | art_fix's DRAW_NOTHING rows |
| armor, weapons, itemtypes, lvlprest, lvltypes, monstats, soundenviron | all | 3 / 0 / 0 / 0 / 0 / 11 / 50 | none | |

The `missing` sound cells are both Median's own sounds on a row where D2R uses a vanilla one: missiles 678 `trapnova`
TravelSound `forcewavetrap` (D2R `sorceress_nova`) and states 153 `cloak_of_shadows` onsound `darkness_falls` (D2R
`assassin_cloakofdarkness`). They are silent like the other 108, not renames.

Objects:

- `renamed`, real: row 133 ShrineMagicArcaneSanctuary1 `xx` (D2R `az`). It is drawn, can be clicked (OperateFn 2), and is placed at
  random in the Arcane Sanctuary (objgroup 75, levels 59 / 65 / 74). In legacy graphics it was invisible (bug #520; HD draws it, because D2R picks the HD model by row), so
  `D2R_RENAMED` now maps `xx` to `az`.
- `renamed`, left alone: row 78 Town1Ambient `TA` (D2R `SS`). It is Draw 0, size 0 and has no functions, so no art is ever
  drawn for it.
- `renamed-fixed`: row 194 `sl` -> `9c` (#518).
- `renamed-exists`: rows 45, 277, 361, 363, 419, 425, 473, 504, 505, 509, 510, 511. These hold the 1.14d token, which D2R
  changed, but D2R still ships that token's legacy art. D2R's HD model is picked by row (objects.json is in row order), so
  both modes draw them and they stay. In the legacy probe every one of these that has art (not 45 / 78, Draw 0) appeared where it was spawned (testing.md "Lane renamesweep").

## Open items found here (for plugins / later phases)

- **States on ids D2R's code names** (lane states, revised by lane statefaith): the 15 repurposed Median states on
  `D2R_FIXED_STATES` ids are **kept** at their ids, as 1.13c ran them (1.14d's code uses every one of those ids the same way);
  `idmap.map_space(relocate=...)` would move an id marked `move` (none now). D2R's asserts on them are taken by plugin guards
  (`statelist`, `dodgelist`). docs/id-mapping.md; bugs #50 #52 #53. states.txt: 302 rows in both banks.
- **cltdofunc 22 -> 113** (Lightning Strike's client half): Rock Shock and ParasiteSkill sit on the plugin's slot 113.
- **Missiles `pSrvHitFunc` 6**: 102 monster-spawning missiles; D2R's hit 6 spawns the `monstats` row in `sHitPar1` (remapped);
  game check. `cltdofunc 83` and the progression slots in `docs/id-mapping.md`: game check.
- **µ item codes** are `^` in the tables; the art / asset lanes must use the same codes.
- ds1 monster ids are renumbered from `work/mod/ds1_ids.json` (`objstr.py` writes it, `ds1_remap.py` reads it); object ids need no
  change and the automap stays D2R's (`tables-status.md` "Object ids and automap", `id-mapping.md` "Objects and ObjPreset"). The TBL
  strings are the strings lane's.
- Stat description lines: itemstatcost description cells follow the mod's wording (`median_stat_wording`); the line formats still
  need an in-game look for descfuncs where D2R formats the text itself.
- Tables without a D2R twin are skipped: `arena`, `chartemplate`, `hiredesc` (folded into hireling), `monitempercent`, `uniquetitle`.
- hireling is a replace table: RotW's 15 extra mercenary rows are not merged (`tables-status.md`).
- validate.py plugin-class items (170): Falloff, colorshift, seqnum, Trans, cltdofunc 113 are things D2R's schema flags that the
  plugin / game decides.
