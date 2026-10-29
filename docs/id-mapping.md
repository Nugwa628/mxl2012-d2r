# ID mapping: Median XL 2012 (1.13c) -> D2R 3.3 build 93847

Tool: `tools/idmap.py` (tests: `tools/test_idmap.py`). Source data: the pure v005 tables in
`mxl2012-runs/extract-mpq/data/global/excel` (93 `.txt` tables shipped in `patch_d2.mpq`). Baseline: D2R 93847's
extracted `data/global/excel` (`base/` = Classic/LoD bank, top level = RotW bank). Based on the
`docs/id-mapping.md`, `docs/function-slots.md`, tools/item_type_ids.py, `tools/func_slots.py` and `tools/vanilla113.py`.
Median 2012 is a plain txt mod (no engine DLL; `docs/engine-triage.md`), so there are no placeholder
names to resolve: every reference in the txt tables is either a **key name** or a **row number**.

## Why ids move

The engine addresses skills, states, stats, missiles, monsters, overlays, levels, objects ... by **row index**. D2R
appended its own rows directly after 1.13c's, and D2R's code depends on them (cooldown states, Interact/Loot skills,
the Warlock class and its 30 skills, `skill_cooldown` stats, ...). Median 2012 also appended its rows after 1.13c's,
so both use the same ids for different rows.

## Rules

| Case | Rule |
|---|---|
| Mod row below the 1.13c count | keeps its id (it is the vanilla row, possibly repurposed by the mod) |
| ... in a slot 1.13c left unused (`unused183`) that D2R filled | the mod row moves to the new range; D2R keeps the slot (itemstatcost: 22 rows) |
| ... a repurposed vanilla **state** whose id D2R's code names by number (`D2R_FIXED_STATES`) | per-id decision (lane statefaith): **kept** where 1.14d's code uses the id the same way (all 15 now; D2R's asserts on them taken by plugin guards), **moved** (relocated: new id, D2R's row back) only for D2R-only code; mod references to D2R's key at those ids (the mod had no row of that name) are emptied, as 1.13c resolved them to nothing |
| ... whose 1.13c key D2R renamed (`nehlithak*` -> `nihlathak*`) | keeps its id and takes D2R's key; every name reference is renamed with it |
| Mod row past the 1.13c count | new id = D2R's row count (larger bank) + running number |
| ... whose key equals one of D2R's added keys (`Abyss`, `Ring of Fire`, `Apocalypse`) | renamed `<key>_mxl` (+ its references) |
| ... named by an item parameter with few saved bits | numbered **first** in the new range (charged skills: 10 bits, `state` property: 8 bits) |
| D2R's own added rows (incl. the Warlock: playerclass/charstats row 7, skills 373-402) | stay at D2R's ids; `IdMap.order()` returns them as `("d2r", id)` |
| Item types | every D2R row at its D2R number (`warl` 67 ..., RotW's `csch` 108), the mod's own types from 109 in both banks; types are referenced by code, so only the order changes |
| Tables without a known 1.13c count (lvlwarp, belts, playerclass, charstats, soundenviron, objgroup) | D2R's count stands in; mod rows keep their positions |

Record counting: every row is a record except an "Expansion" separator **in the first column** and empty lines.
Blank-key rows are records. Checked against each table's compiled `.bin` header (`bin_records`): all 86 tables that
ship a `.bin` match, except the unused classic `treasureclass` (LoD loads `treasureclassex`; engine-triage).
Median's `objects.txt` row 250 has a line break inside a cell; `read_tsv` rejoins it.

D2R banks: ids come from the larger bank (RotW). Where the base bank is shorter (skills 427 vs 429, missiles 736 vs
742, overlay 333 vs 334, events 16 vs 17, levels 137 vs 138), the base-bank table must be padded with the RotW rows
so the mod's rows land on the same ids in both banks.

## States D2R's code names by number (lane states, then lane statefaith, 2026-10-28; bugs #50 #52 #53)

D2R.exe 93847 tests, sets or reads the stat list of vanilla states by immediate id. Lane states' scan of the dump (immediate ids in
`edx` before calls to the state test `0x3351b0`, the state set `0x3354c0`, `0x2d11d0`, `0x48e820`, `0x46d8f0` and the state stat list
getter `0x2f5940`; `mxl2012-runs/states/scratch/statescan.*`) found 63 such ids plus 65 / 66 / 68, which the damage code `0x44b100`
picks from the hit's result flags. Median 2012 repurposed 15 of them. Lane states moved all 15 to new ids; that stopped the asserts
but also changed what 1.13c did, because **1.13c's own engine used the same ids the same way**. Lane statefaith compared every D2R
call site with 1.14d's `Game.exe` (the project's install in `gamedata/`, read statically with capstone; 1.14d is the nearest
Blizzard build to 1.13c we can read): state test `0x639df0`, state set `0x639db0` and state stat list `0x6256b0` were found by the
id histogram of their callers, then every one of the 15 ids was looked up there (scripts `mxl2012-runs/statefaith/scratch/g114.py`,
`sites.py`, `d2rlist.py`, `d2rlea.py`). Rule (owner: match Median XL 2012 as it played on 1.13c): where 1.14d tests / sets / reads
the id in the same situation, Median's row at that id WAS the 1.13c behaviour and is **kept**; where D2R's code asserts on it, a
plugin guard keeps 1.14d's flow; only an id that D2R names in D2R-only code, or that cannot be kept, is **moved**.
`idmap.D2R_FIXED_STATES` holds the table below (decision and reason per id); `RELOCATE` is derived from it (empty now), and
`map_space(..., relocate=...)` still moves any id marked `move`.

| Id | D2R row | Median row | Decision | D2R code | 1.14d `Game.exe` | Why / 1.13c effect kept | Verified in game |
|---|---|---|---|---|---|---|---|
| 13 | blaze | shellshock (Force Shout) | keep | client trail `0x21edc0`, server `0x551450`: state list, stat 350 / 351 as skill / level, the skill's missile; walk tests `0xf9aac` `0x445d38` `0x429a67` | client `0x4e3ab0`, server `0x5c9d90`: the same code; tests `0x4807cb` `0x5a8499` `0x580c38` | shellshocked units ran it in 1.13c; with no skill in the list both leave, D2R after an assert (#50): plugin `statelist` skips the 6 range asserts | see testing.md, lane statefaith |
| 22 | spiderlay | raptured (Rapture, NTRAP) | keep | client `0x221650`, server `0x578680`: as 13; walk tests `0xf9aca` `0x445d54`, test `0x5b4b9d` | client `0x4e2d40`, server `0x5ce4f0`: **fixed** missile 143 with skill 173 (no list); tests `0x4807de` `0x5a84ae` `0x5f46ef` | 1.13c ran its state-22 code on raptured units; D2R's asserts (#52): `statelist`. 1.14d's trail (Median's `spidergoolay`, a light-blue melt) is not made by D2R's list-driven code: plugin `melttrail` makes it for a list without a skill (lane melttrail; docs/unported.md) | as 13; trail: game check `melttrail` pending |
| 47 | sanctuary | aura_2 (Bear Stance) | keep | damage test `0x452508` | damage test `0x57beea` | the Sanctuary rule met Bear Stance in 1.13c | static only |
| 57 | attract | unholynova (Black Mass) | keep | monster target pick `0x433fd0` | `0x56ea43` | monsters treated Black Mass targets as Attract targets in 1.13c | static only |
| 65 | dodge | shamanstrance (Shamanic Trance, Item Trance S) | keep | damage code `0x44b100` reads the defender's list on a dodge (stat 350 as the skill of the dodge reaction) | `0x57d186` (list `0x6256b0`), the same flow | a dodge sets or clears no state in either game (it only reads the list); no list: plugin `dodgelist` (#53) | yes |
| 66 | avoid | broadsided (Broadside's lockout) | keep | as 65 (avoid) | `0x57d19c` | as 65 | yes |
| 68 | evade | necroshadowspirit | keep | damage list `0x44b148`, client `0x106444` | `0x57d210`, client `0x4cbe6e` | as 65; the 57 monprop `state` cells naming 68 keep it | static + #53 |
| 78 | throwingmastery | phasebombcurse | keep | client tests `0x27fef9` `0x281470` `0x28e3e9` | `0x4e91c5` `0x4ea6eb` `0x4ea8ce` | same three tests | static only |
| 84 | fingermagecurse | abolishcurse | keep | monster AI `0x5afb1d` | `0x5fa628` | same test | static only |
| 87 | slowmissiles | ongoing_thunderdome (Lightning Arena) | keep | missile creation `0x5374d7` (stat 161 of the list), client `0x1b7a5d` | `0x59fb51`, client `0x4cd69d`, same reads | Lightning Arena slowed missiles in 1.13c; no assert in that code | static only |
| 93 | valkyrie | pantherstaunt | keep | set by srvdofunc 16 `0x558218` | set `0x5dc32f`, test `0x5722b1` | same set (no Median skill uses srvdofunc 16) | static only |
| 101 | holyshield | snakepoison | keep | block code `0x347bad` (list `0x347bc2`, no assert), 5 more tests incl. the HD stats panel `0x14e601c` | block code `0x5ceabc` / `0x62243b` with lists, 7 more tests (classic panel) | same code; the HD panel is D2R-only UI showing what the classic panel shows | static only |
| 138 | fenris_rage | totemicvoodoo | keep | monster AI `0x5c9e26` | `0x5ed572` | same test | static only |
| 143 | attached | resonance (Ring of Light) | keep | set by srvdofunc 129 (Imp Teleport) `0x586a6e` `0x586c6e`, 9 tests | set `0x5d1955` `0x5d1a43`, 8 tests | attaching Act 5 imps got Median's Ring of Light state in 1.13c | see testing.md |
| 184 | uberminion | porkulator | keep | Uber AIs set it on their minions `0x5a95b2` `0x5aba53` `0x5ae5ef`, client test `0x1a49c1` | Uber AIs `0x5f8002` `0x5fb555` `0x5fd1f1`, client `0x4afc2f` | the ubers' minions got Median's Porkulator form in 1.13c | see testing.md |

No id met the "move" rule: every D2R site found has a 1.14d counterpart (D2R's few extra tests are the same checks in new places,
e.g. the HD stats panel for 101). Lane states' notes on what relocation changed ("a dodge no longer sets / clears Shamanic Trance")
were partly wrong: in both games the dodge / avoid / evade code only reads the defender's list. States.txt is back to 302 rows
(255 Median + D2R's 47 added rows from 255); the 8-bit `state` property still fits (the rows it names are 68, 78, 87 and the new
ones numbered first from 255). Name references to D2R's keys at the 15 ids (`blaze`, `spiderlay`, `fenris_rage`, `attached`,
`fingermagecurse` ...: 7 cells, Median had no row of those names, so 1.13c resolved them to nothing) are still emptied by
`remap_table` (`SpaceMap.restored_keys` covers kept fixed ids too).

## Function slots

| Kind | Columns / slots | Action |
|---|---|---|
| 1.13c slot D2R renumbered | srvdofunc 109 -> 9, srvstfunc 64 -> 67, srvstfunc 37 with srvdofunc 109 -> 67, cltstfunc 82 -> blank | rewritten for every mod row |
| 1.13c function D2R dropped | cltdofunc 22 (Lightning Strike client half) | -> free plugin slot 113 (free in D2R) |
| Vanilla row cell D2R changed (`CELLS_113C`) | missiles corpseexplosion pCltDoFunc 11 -> 69, vine beast death 11 -> 70; D2R's additions to vanilla rows (Double Swing srvstfunc 68, FetishInferno cltstfunc 54, holybolt/fistoftheheavensbolt pSrvDmgFunc 15, viper_poisjav CltCalc1 3) | the mod's vanilla row follows D2R when it still has the 1.13c value; mod-new rows named `*corpse*explo*` on pCltDoFunc 11 -> 69 |
| Client hit kept / blanked | pCltHitFunc 11, 12, 26 | 12 / 26 kept (the functions still exist in D2R); 11 blanked (`SLOT_REMAP`, bug #14: empty in D2R and in 1.14d, `docs/unported.md`) |
| D2R's own slots (verified) | srvdofunc 153-171, srvstfunc 68-70, cltstfunc 54/55, cltdofunc 97-99, pSrvDmgFunc 15, CltCalc1 3 | -> free slots (srvdofunc 172-190, srvstfunc 71-90, cltdofunc 113/110-112, missile srv hit 61-70, clt hit 6/7/20) for the plugin |
| Slot only D2R's own rows use (inferred from data) | missiles pSrvHitFunc 23 | warning only, game-check |
| Slot no 1.13c vanilla row uses | pSrvHitFunc 6 (102 monster spawners), cltdofunc 83, srvprg 22/119/51, cltprg 25/28 | warning only, game-check (engine-triage #5/#6/#9) |

**Median 2012 uses none of D2R's srvdofunc 153-171** (its highest srvdofunc is 152): nothing has to move into the
plugin's free do slots for that reason.

## Reference columns

`py -3 tools/idmap.py refs` prints the registry; `refs --guide <D2R dataguide/data/files>` diffs it against every
reference field in D2R's data guide (0 missing). `report.md` from `build` lists every column present in the mod's tables.

**Row numbers** (`NUMERIC_REFS`, rewritten by `remap_table`):

| Table.column | Id space | Condition |
|---|---|---|
| levels.Vis0-7, levels.Depend, lvlprest.LevelId, lvlmaze.Level, shrines.LevelMin | levels | |
| levels.LevelType / ObjGrp0-7 / SoundEnv | lvltypes / objgroup / soundenviron | |
| objgroup.ID0-7 | objects | |
| hireling.Class, hireling.Seller, pettype.mclass1-4 | monstats | |
| states.gfxclass | monstats | gfxtype = 1 (2 = player class) |
| **missiles.sHitPar1** | monstats | pSrvHitFunc = 6 (monster-spawning missiles: 100 cells change) |
| superuniques.Mod1-3, skills.sumumod | monumod | |
| weapons/armor/misc.missiletype | missiles | |
| weapons/armor/misc.belt | belts | |
| **cubemain.param** | itemstatcost | op set (stat ids, incl. Median-only 419-507: 357 cells change) |
| item property parameters (uniqueitems, setitems, sets, runes, affixes, automagic, qualityitems, gems, cubemain, monprop) | skills / monstats / states | by the property's func1 and stat (charges, oskills, procs, auras: skill; reanimate descfunc 23: monster; stat `state`: state). Numbers are remapped, names renamed |
| own-id columns: skills.Id, states.id, itemstatcost.ID, missiles.Id, monstats.hcIdx, levels.Id, objects.Id, superuniques.hcIdx, pettype.idx, monumod.id, lvltypes.Id, lvlprest.Def | itself | set to the new id |

**Key names** (`NAME_REFS`; renumbering does not touch them, renames do): skills (books, charstats Skill N /
StartSkill, hireling Skill1-6, missiles.Skill, monsounds CvtSk, monstats Skill1-8 / SkillDamage, monstats2
ResurrectSkill, skills sumskill/reqskill, states.skill), missiles (missiles Explosion/Sub/HitSub/CltSub/CltHitSub,
monstats MissA1..MissSQ, skilldesc descmissile, skills srv/cltmissile*, states.missile), states (misc state/cstate,
skills aurastate/auratargetstate/passivestate/State1-3), itemstatcost (op base/op stat, maxstat, misc stat1-3,
properties stat1-7, skills aurastat/passivestat, states.stat, monpet), monstats (levels mon/nmon/umon/cmon, monequip,
monstats BaseId/NextInClass/spawn/minion, npc, skills.summon, superuniques.Class, monpreset.Place, wanderingmon),
monstats2 (monstats.MonStatsEx), overlay (missiles.ProgOverlay, skills *overlay*, states overlay1-4 / pgsv / cast /
removerlay), events, monai, monprop, monsounds, montype, monumod, pettype, skilldesc, objects (objpreset.ObjectClass),
levels (actinfo), playerclass (charclass and class columns). Formulas: `skill('x'.)`, `miss('x'.)`, `stat('x'.)`.

Not txt (outside this layer): saves, the plugin's own tables. The ds1 maps (monster / object presets by number) are below.

## Objects and ObjPreset (lane objstr, 2026-10-28)

A `.ds1` names an object as (act from the header, id); D2R looks the id up in the act's `objpreset.txt` (`Index` -> `ObjectClass`) and the
class in `objects.txt` (`Class`, one row per class). Median 2012 ships no `objpreset` (1.13c's own table was used), and D2R's per-act table is
that table plus D2R's additions, so **no object id of the maps changes**; `tools/objstr.py` proves it on every build
(`work/mod/objstr_report.md`, details and numbers in `tables-status.md`):

| Check | Result |
|---|---|
| every (act, id) of the 2,803 type-2 objects is a row of D2R's ObjPreset for that act | yes (no negative ids, none missing) |
| its `ObjectClass` names one Objects row of the built table (case-insensitive) and no `Class` is shared by two rows | yes |
| that row is the mod's row of the same position (`Name` equal for the 573 rows), no Objects row moves (`Maps.moved_objects()`) | yes |
| objects.txt keeps the mod's `AutoMap` cel in all 573 shared rows | yes (highest cel 1468) |

So `idmap` needs nothing for objects beyond keeping the first 573 rows in place. Monster ids still change (1,088 of the 1,822 monstats rows);
the data step writes that table to `work/mod/ds1_ids.json` and `tools/ds1_remap.py` / `install_mod.py` renumber the maps from it.
Automap: see `tables-status.md` ("Object ids and automap"): D2R's `automap.txt` stays, the level types are D2R's 36.

## Using it from the tables lane

```python
import idmap
m = idmap.IdMap.build(MOD_EXCEL, D2R_EXCEL)        # once
for table in mod_tables:                            # 1. rewrite each MOD table before merging
    m.remap_table(table, header, rows)              #    numeric refs, own ids, renames, formulas, params, slots
for entity in idmap.ENTITIES:                       # 2. assemble indexed tables in final id order
    for src, i in m.order(entity):                  #    ("mod", mod_row) | ("d2r", d2r_id)
        ...                                         #    d2r ids missing in the base bank: take the RotW row
rows, rep = idmap.align_item_types(mod_h, mod_rows, d2r_h, d2r_rows)   # 3. itemtypes
errors = idmap.check_built(OUT / "base", D2R_EXCEL)                    # 4. after migration: fail on any error
```

CLI: `py -3 -I tools/idmap.py build --mod <dir> [--d2r <dir>] [--out work/idmap]` writes `idmap.json` (per id space:
mod row, key, final id, kind, final name; renames; slot moves; cell moves; low-id rows) and `report.md`, exit 1 on an
error. `py -3 -I tools/idmap.py check --built work/mod/data/global/excel/base` fails (exit 1) when an item type that
D2R.exe tests by a fixed number (h2h 68, pelt 73, rune 75, hpot 77, apot 81, wpot 82, scha 83, mcha 84, gem4 96; 25
call sites of 0x373890) or any other D2R type has another id in the built table. The D2R baseline is found via `--d2r`,
`MXL2012_D2R_EXCEL`, `extract/d2r/93847/...` in this repo, or `extract_dir` from the machine-local config (docs/setup.md).

## Conflicts found in Median XL 2012 v005 (2026-10-28)

`build` result: **0 errors, 33 warnings** (the warnings are the moves, game checks and save-format notes below). Before the rules:

| Area | Finding | Resolution |
|---|---|---|
| Item types | Median lacks `warl`: h2h 67, pelt 72, rune 74, hpot 76, apot 80, wpot 81, scha 82, mcha 83, gem4 95, each one below D2R's fixed id (runes would apply no gem mods, circlets would pass the rune test). Median also lacks blde/sppl/grim/cjwl and has blank `None`/`Not Used` rows at 0/1/14/17/23 | `align_item_types`: D2R's 109 rows (RotW bank) at D2R numbers, Median's 124 own types from 109, 233 types in all (160 Median types change id); `check_built` fails the build otherwise |
| Skill slots | srvdofunc 109 (MonFrenzy, BloodLordFrenzy, Feral Strike: would open town portals), srvstfunc 64 (MonFrenzy, Feral Strike), 37+109 (BloodLordFrenzy), cltstfunc 82 (Temp/Baal Corpse Explode), cltdofunc 22 (Rock Shock, ParasiteSkill) | remapped / plugin slot 113 |
| srvdofunc 153-171 | 0 Median rows (max 152) | nothing to move |
| Missile slots | corpseexplosion / vine beast death pCltDoFunc 11 (D2R: 69 / 70); poisoncorpseexplosion, monstercorpseexplode stay on 11 unless renamed rule matches (`*corpse*explo*` -> 69); pCltHitFunc 11/12/26 (6 rows) | follow D2R / kept |
| Unverified slots | pSrvHitFunc 6 (102 monster spawners incl. the uber summons), pSrvHitFunc 23 (bloodspeakerbolt, leapingjumper; D2R uses 23 only for its own rows), cltdofunc 83, Batstrike/Blackstorm progression slots | game check (engine-triage) |
| Stat ids | 508 Median stats; 22 sit in 1.13c-unused slots 183-213 that D2R filled (game_craftpoints, x_signet01-09, potion caps, ...) -> moved to 368-389; final table 539 rows, top id 538 | 22 saved stats get ids 511-538: beyond the 9-bit save id (511 ends the list) -> need D2RLoader's 16-bit extended save |
| Charged-skill parameters | `charged` (item_charged_skill, skill << 6 \| level in 16 bits = 10 bits of skill) names Venomous Spirit 1002, Inner Fire 1003, Charm 1018 -> 1074/1075/1090 after the +72 shift: overflow | those (and all 443 param-referenced new skills) are numbered first: fits |
| State parameters | property `state` (8 param bits, max 255) names 7 states 211-254 -> 258-301 after the shift: overflow | numbered first (232-239): fits |
| States | 255 Median -> 302 merged (the 15 on ids D2R's code names kept as 1.13c ran them, lane statefaith) | under D2R's 512 per-unit sync |
| Skills per class | 30 each | fits the classic 30-byte class section |
| monai | 144 rows | all on D2R's 155 AI rows |
| Name collisions | skills Abyss, Ring of Fire, Apocalypse; missile apocalypse (equal to D2R's RotW keys) | renamed `_mxl` |
| Repurposed vanilla rows | skills 243, states 100 (15 of them on ids D2R's code names: kept, see "States D2R's code names by number"), itemstatcost 80, properties 121, montype 51, superuniques 23, monstats 24, monprop 13, monstats2 5 (ubers), missiles 3 | kept at their ids as 1.13c ran them; D2R code that names one of these ids by number now meets Median's row. Superuniques: Median's "Expansion" separator is under `Name`, which made it a record and moved every superunique from 43 on one id above vanilla; the prep step puts the label back into the first column (bug #362), so Siege Boss is 42, the Ancients 43-45, Nihlathak 60 and Baal's subjects 61-65 as D2R's quest code expects |
| Duplicate keys | objects (many), objgroup, lvlprest, lvlmaze, lvlsub, belts `uber belt` | name references hit the first row (as in 1.13c) |
| Table sizes | largest cubemain 11,477, sounds 4,900 | under 32,768 |
| Hidden numeric ids rewritten (dry run) | cubemain param 357, missiles sHitPar1 100, weapons missiletype 70, states gfxclass 6, property params ~7,200 (skills/monsters/states), own-id columns | `remap_table` |
