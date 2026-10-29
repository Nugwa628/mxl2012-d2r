# Skill and missile function slots: 1.13c vs D2R 93847

Median XL's skills.txt and missiles.txt carry D2Sigma's numbering: 1.13c D2Game's function tables plus D2Sigma's
additions. D2R renumbered some vanilla slots and reused freed ones for its own skills. A Median row left on the 1.13c
number runs whatever D2R put there (bug #31: Feral Strike, Flash, MonFrenzy and Bloodlord's skill opened town portals).
`tools/txt_migrate.py` (`skill_rules`) remaps each Median row to the D2R slot that does what the 1.13c slot did;
`tools/validate.py` (`engine_rules`) fails the build when a Median row is still on a slot D2R changed.

The audit is `py -3 tools/func_slots.py` (`D2R_BANK=base|""` picks the bank): the same vanilla skill (missile) is read
in the 1.13c view (`tools/vanilla113.py`: D2R's first rows plus the 22 slot cells D2R changed, kept as the 1.13c numbers) and D2R's, and every column slot that is not the same
number is reported. `tools/func_slots_median.py` lists, per slot, the Median rows that use it against the vanilla users in
both games. The remap constants (`SRV_DO_REMAP`, `SRV_START_REMAP`, `SRV_START_REMAP_WITH_DO`, `CLT_START_DROP`,
`POISON`) are in `tools/func_slots.py`.

D2R's tables (image RVAs of build 93847): srvdofunc `0x238ea00` (191 slots, bound `0xbe`), srvstfunc `0x238e710` (91),
client do `0x235f7d0` (bound 130), missile server hit `0x2391030` (71), client hit `0x2358710` (81).

## Skill columns: slots D2R changed for vanilla skills

| Column | 1.13c slot | 1.13c function | D2R slot of that function | What D2R's old slot holds now | Median rows | Fix |
|---|---|---|---|---|---|---|
| srvdofunc | 109 | MonFrenzy: melee hit plus the frenzy state (D2Game `0x6fcd6790`) | **9** (Frenzy; `0x567e80`, D2R merged 109 into it and added a stack counter) | **Townportal O Skill** (itemless town portal, `0x5822b0`: creates object 0x3b, links it to town) | 4: MonFrenzy, flash, feral_strike, bloodlord1_skill | -> 9 |
| srvstfunc | 64 | MonFrenzy start: target check (`0x6fcd3570`) | **67** (`0x569c30`: frenzy counter reset, no target check) | Bind Demon's start (the slot holds an import thunk, `0x3e2b6f4`) | 2: MonFrenzy, feral_strike | -> 67 |
| srvstfunc | 37 (on a row with do 109) | Zeal / Fury start, used by BloodLordFrenzy together with do 109 | 67 (D2R's BloodLordFrenzy row is 67 + 9) | 37 stays Zeal / Fury's | 1: bloodlord1_skill (impale_3 keeps 37) | -> 67 |
| cltstfunc | 82 | Baal Corpse Explode start | none (D2R's client start table ends at 55; its Baal Corpse Explode row is blank) | past the end of the table | 2: Firestorm, Baal Corpse Explode | -> blank |
| cltdofunc | 22 | Lightning Strike client half | none (D2R's row is blank) | empty | 3 (parasite_2, parasite_3, rock_shock): already moved to plugin 113 by `clt_moved` | unchanged |

Slots D2R added for its own skills (no 1.13c skill used them; a Median row on the same number is a collision):

| Column | Slot | D2R skill |
|---|---|---|
| srvstfunc | 67 | Frenzy; 68 Double Swing; 64-70 are D2R's own |
| cltstfunc | 54 / 55 | Inferno skills / Impale |
| cltdofunc | 97 | Volcano |
| srvdofunc | 153-171 | D2R's newer skills (Warlock, uber skills) |
| pSrvDmgFunc | 15 | holybolt, fistoftheheavensbolt |
| CltCalc1 | 3 | viper_poisjav |

Slots that no vanilla skill uses in either game, and slots both games use for the same vanilla skills, are not listed:
the audit found nothing else that differs for srvprgfunc1-3 and cltprgfunc1-3 (every vanilla row has the same number in
both tables). srvstopfunc / cltstopfunc do not exist in 1.13c's skills.txt (D2R-only; txt_migrate gives Whirlwind-type
rows D2R's stop function 1).

## Already moved before this audit (txt_migrate, D2Sigma's added slots)

| Column | Median slot | Moves to | Where it runs |
|---|---|---|---|
| srvdofunc | 153-171 (D2Sigma's added functions) | +19 = 172-190 | mxl2012-core plugin (docs/plugin-spec.md "Skill server functions"); 175 = D2Sigma 156 since bug #58; free: 181, 182, 183, 186-189 |
| srvdofunc | 155 (town_portal), 160, 161, 167 | 109 (D2R's itemless Town Portal, on purpose), 124, 121, 58 | D2R native; `town_portal` -> 109 stays, it is the one Median row that may use 109 |
| srvstfunc | 30, 66 | 71, 72 | plugin `skill_starts.cpp` |
| cltdofunc | 97, 98, 99; 15, 11, 95, 22 | 110, 111, 112; 19, 15, 111, 113 | plugin client slots / D2R's equivalents |
| srvdofunc | 27 (with aurarangecalc), 18 / 124 (layered) | 179, 174 / 180 | plugin |

## Missile columns

Missile rows are compared the same way. For vanilla missiles D2R changed only a few rows; Median's own rows already
carry their own values (`missile_functions` in txt_migrate remaps D2Sigma's added hit / do slots through
`SRV_HIT_MOVED`, `CLT_HIT_MOVED`, `SRV_DO_MOVED`, `CLT_DO_MOVED`).

| Column | 1.13c slot | Vanilla missile | D2R slot | Note |
|---|---|---|---|---|
| pCltDoFunc | 11 | corpseexplosion | 69 | D2R split it; vine beast death -> 70. Median's `corpseexplosion` row is on the plain function 1, the 14 Median rows on 11 are the ones D2R also keeps on 11 (grimward*, andydebris*, queendeathsplat*, ...) |
| pCltHitFunc | 11, 12, 26 | desertfireball, immolationarrow, fistoftheheavensdelay | blank | D2R dropped the effect for those rows. The functions still exist for 12 (`0x1acda0`) and 26 (`0x1adcb0`); slot 11 is empty. Median's rows on 12 / 26 keep their numbers. 11 (desertfireball) is blanked by `idmap.SLOT_REMAP` as D2R's own row (bug #14); 1.14d's client hit table has no function at 11 either |
| pSrvDmgFunc, CltCalc1 | - | - | 15, 3 | D2R additions only, no Median row collides |
| pSrvDoFunc, pSrvHitFunc, pCltHitFunc (others), SrvCalc1 | - | - | - | same number in both for every vanilla missile |

## Build rules

- `txt_migrate` report line "1.13c slots D2R renumbered": counts per column (`srvdofunc`, `srvstfunc`, `cltstfunc`).
  Current build: srvdofunc 4, srvstfunc 3, cltstfunc 2.
- `validate.py` error "slot N is ..." for every Median skill row on `POISON` (srvdofunc 109 outside `town_portal` and D2R's
  own rows, srvstfunc 64, cltstfunc 82). The error is not downgraded to a warning for a value D2R's vanilla also uses.
- RotW's own Death Mark (D2R srvdofunc 155) was written as 109 by the town_portal conversion (a D2R row mistaken for
  D2Sigma's town_portal); the conversion now skips D2R's own rows.

## Game check

`py -3 tools/game_checks.py --slot N all mxl funcslots townportal` (`funcslots`): the player casts feral_strike and flash
at a monster, monsters cast MonFrenzy (class 127), bloodlord1_skill (class 506) and flash (class 1250) through `mcast`.
No portal object may appear in `h state`; the casts must start and do something. `townportal` runs in the same pass as the
control: town_portal still opens a portal to town and back.
