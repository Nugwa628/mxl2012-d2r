# Engine triage: Median XL 2012 v005 on D2R 3.3 (build 93847)

Phase 3 triage (lane triage, 2026-10-28). Question: which behaviours of Median XL 2012 v005 do the tables alone
possibly *not* give in D2R 3.3, and what does each need?

Classes: **data** = data can do it (table edit, remap or merge rule, maybe "verify" in game) · **plugin** = plugin
needed (D2RLoader 1.3.1 plugin code) · **D2R has it** = D2R or D2RLoader already does it · **drop** = not ported
(row in [unported.md](unported.md)). Effort: XS < 1 h, S < 1 day, M a few days, L a week or more.

Sources (all static reading, nothing executed):
- Pure v005 = `mxl2012-runs\extract-mpq\` (patch_d2.mpq only, 2,362 files). Repack-only files from
  `mxl2012-runs\src-repack\` and `extract-merged\` (see EXTRACT_DONE.txt). **All of it is the archive.org repack
  and must be re-checked against the ModDB zip** (md5 53ae96c9…) when it arrives.
- D2R baseline tables: `<extract_dir>\data\global\excel\base\` (read-only; `extract_dir` in the machine-local config, docs/setup.md).
- Tools on this branch: `tools/engine_audit.py` (function-slot audit against the 1.13c view), `tools/vanilla113.py`
  (1.13c view of the tables), `tools/bin_vs_txt.py`, `tools/bindiff.py`, `tools/invgrid.py`, `tools/rtf2txt.py`. Run with
  `py -3 -I -B tools/<tool>.py <path>`; outputs go to the ignored `work/`.

## 1. Does v005 depend on any code? No.

| Evidence | Finding |
|---|---|
| README.rtf (Laz, 27 Dec 2011) | "This mod requires Diablo II LoD 1.10 or later"; install = replace `patch_d2.mpq`; no loader, no DLL. "PlugY does not come with Median XL … I did not create PlugY and therefore I do not support it." A mod that runs unchanged on 1.10, 1.11, 1.12 and 1.13 cannot carry version-specific code patches. |
| patch_d2.mpq content | 2,362 files: dcc/cof/dc6/dt1/ds1/wav art, 93 txt + 91 bin tables, string tables, `.d2` animdata/cof indexes, `plugy/plugyfixed.ini`, `plugy/statsinterface.txt`. No file starts with `MZ` (checked every unnamed `.xxx`; they are tables, ds1s, a string table and a joke text "Nothing to see here. Move along."). |
| D2SE_SETUP.ini (repacker) | `D2Core=1.13c`; `ModUseD2SE=0`, `ModUseD2Mod=0`, `ModUseNefex=0`, `ModUseD2Extra=0`, no `ModDll1-3`; `ModUsePatch_D2=1`. `Modable=1` / `Direct=1` only make the launcher pass `-direct` (loose `data\` overrides the mpq); `Txt=0`, so 1.13c reads the compiled `.bin` tables. |
| `.bin` vs `.txt` in the mpq (`tools/bin_vs_txt.py`) | Every table pair has the same record count (Expansion separator rows excluded), cubemain (11,477) and charstats included, except the classic `treasureclass` (bin 95, txt 751): LoD 1.13c loads `treasureclassex` (1,468 = 1,468), so that pair is a leftover and not used. The shipped `.txt` files are usable sources; 1.13c itself ran the `.bin`. |
| Engine functions used by the tables (`tools/engine_audit.py`, section 2) | Every function number, AI code, calc code and formula function is a 1.13c engine one. |

So v005 is pure data on vanilla 1.13c. Everything below is about 1.13c behaviour the data relies on that D2R 3.3
numbers, implements or limits differently, plus the PlugY settings the mpq itself carries.

## 2. Triage table: mod behaviours (pure v005)

| # | Feature | Evidence | Class | Effort | Notes |
|---|---|---|---|---|---|
| 1 | Skill server do 109 (MonFrenzy, BloodLordFrenzy, Feral Strike) | engine_audit: srvdofunc `109` [moved], 3 rows. D2R reused 109 for "Townportal O Skill" (skills opened town portals) | data | XS | Remap 109 -> 9 (`skill_rules`). Add a `POISON` validate rule. |
| 2 | Skill server start 64 / 37+109 (MonFrenzy, Feral Strike; BloodLordFrenzy) | srvstfunc `64` 2 rows, `37` with do 109 on BloodLordFrenzy. D2R's 64 is Bind Demon's start | data | XS | 64 -> 67; (37, 109) -> 67. Massacre and Ravage are on 37 too but not with do 109: they keep 37 (check their do column during the migration). |
| 3 | Client start 82 (Temp Corpse Explode, Baal Corpse Explode) | cltstfunc `82`; D2R's client start table ends at 55 | data | XS | Blank it (`CLT_START_DROP`). Loses only the client start visual: approx. |
| 4 | Client do 22 (Rock Shock, ParasiteSkill) | cltdofunc `22`; D2R's row is blank (the Lightning Strike client half is gone) | plugin | S | Run it from plugin client slot 113 (`clt_moved`). Without it the server half works and only the client effect is missing. |
| 5 | Client do 83 (Titan Strike, Innate Titans, Soulshatter, Mana Sweep) | cltdofunc `83`: no vanilla 1.13c row uses it, no D2R row uses it either; D2R's client do bound is 130, so the slot exists | data (verify) | S | Same table index in both games is likely the same function, but unverified. Game check: cast each skill, watch the client effect; else port (plugin, M). |
| 6 | Skill progression functions (Batstrike: srvprg 22/119/51, cltprg 25; Blackstorm: cltprg 28) | engine_audit: [new113, d2r-unused] | data (verify) | S | Same as #5: 1.13c slots no vanilla skill uses. Two skills. |
| 7 | Missile client do 11 (16 rows: corpseexplosion, poisoncorpseexplosion, monstercorpseexplode, grimward*stop, …) | pCltDoFunc `11`: D2R split it (corpse explosion -> 69, the others keep 11) | data | XS | Remap the corpse-explosion rows to 69, keep the rest on 11. |
| 8 | Missile client hit 11/12/26 (desertfireball, immolationarrow, barimmospawn, firespawnerfire, bootsabouttoexplode, fistoftheheavensdelay) | pCltHitFunc: D2R blanked these cells; 12 and 26 still exist in D2R's binary, slot 11 is empty | drop | - | Client-only hit visuals (6 rows), as D2R's own desertfireball. Can be re-pointed by a plugin later (XS) if it shows. unported.md row. |
| 9 | **Missile server hit 6: monster spawners**, incl. the summoning uberquests (102 rows: edy1summon, darkbosssummon, master1summon, cow3summon, evil1-4spawner, treewardenspawner, …) | pSrvHitFunc `6`, sHitPar1 = monstats row (e.g. 1107), sHitPar2 = 1. No vanilla row of either game uses 6. D2R's server hit table `0x2391030` has 71 slots, 61-70 empty, so 6 is filled | data (verify) | S | Highest-risk slot: the summoning ubers and many monster skills depend on it. Game check first; if D2R's 6 differs, route the rows to a plugin hit 68 ("spawn monstats row calc1 at the missile"), which does the same thing (M). sHitPar1 must go through the monstats idmap (#13). |
| 10 | Missile server hit 23 (bloodspeakerbolt, leapingjumper) | pSrvHitFunc `23`, sHitPar1 = 119 | data (verify) | XS | Same as #9, 2 rows. |
| 11 | Everything else that names an engine function | engine_audit: srvdo (102 values), srvst (43), cltst (41), cltdo (61), ItemEffect, ItemCltEffect, pSrvDo/pSrvDmg/SrvCalc1/CltCalc1/CollideType, states set/rem/active funcs, objects Operate/Populate/Init/Client fns, levels LevelType/DrlgType, shrines, monstats AI (144 codes), properties func1-7, itemstatcost op/Encode, misc pSpell (1-3, 6-10) | D2R has it | - | Same number, same vanilla function in both. properties func 3 in func5-7 (8 rows) is the vanilla "same as previous" function in a later slot: fine. |
| 12 | Calc codes and formula functions | skillcalc.bin: 73 codes, identical and in the same order as D2R's first 73 (`ln12` … `pets`, `skpt`). Formulas use only `stat()`, `skill()`, `min()`, `max()`, `rand()`, `sklvl()`, `miss()` and vanilla qualifiers (`.accr`, `.blvl`, `.pst1-5`, `.par1-8`, `.ln12`, …) | D2R has it | - | Text formulas compile in D2R; only the names inside `stat('x')` / `skill('y')` must exist after the idmap. |
| 13 | ID space: rows past the 1.13c ranges | Median 2012 rows vs D2R base: itemstatcost 508/368, states 255/232, skills 1038/427, missiles 2665/736, monstats 1823/752, monstats2 1211/624, overlay 525/334, properties 544/285, skilldesc 699/232. D2R appended its own rows right after 1.13c's | data | M | idmap lane: keep vanilla rows at vanilla indexes, move Median's added rows after D2R's. Every table is small enough for D2R (16-bit stat ids in D2RLoader's save, states > 512 supported by D2RLoader 1.3.1). levels: 137 rows, no new level, no collision. |
| 14 | **Numeric IDs hidden in parameters** | cube `op` param = stat id (12 level, 14 gold, 419-425, 428 `var_blackroad`, 471, 472, 507 `var`) on the challenge "decoy" recipes; missile sHitPar1 = monstats row (#9); hit 23 par 119 | data | S | The idmap must rewrite these, not only named columns. Trap for the tables/idmap lanes: a stat id in cubemain `param` left on the 1.13c number silently tests a D2R stat. |
| 15 | Stat tooltips with the 1.13c descfuncs | itemstatcost descfunc 1-4, 6-8, 20 (271 rows), descval 1, dgrpfunc 1-4, 20. D2R's own stats use printf-style descfunc 19 and strings with `%d` | data | M | D2R still implements descfunc 1-29 (Median's non-printf descfuncs draw in D2R). The strings lane must point those stats at strings without `%d` / `%+d`. |
| 16 | Single-rune runewords padded with jewels | runes.txt 3,133 rows, 3,080 complete; 7,180 Rune cells are `jew`: one row per socket count, rune first (`Sur, jew, jew, jew, jew`) | data (verify) | S | Explicit padding, no matcher change: D2R's native matcher counts jewels in an exact row. Check the runeword id still fits D2R's save field (12 bits, 3,133 < 4,096) and that D2R loads 3,133 rows. |
| 17 | Ladder-only content | runes.txt `server` blank on every row; cubemain `ladder` blank on every row | D2R has it | - | Nothing ladder-gated, so D2R's offline ladder rules change nothing. |
| 18 | Cube system: 11,477 recipes, ops, outputs | ops used 3, 6, 10, 15, 16, 17, 18, 28 (D2R: 1-28); outputs `useitem` / `usetype` + quality flags, plus one "Cow Portal" (Wirt's Leg + Tome of Town Portal) | data (verify) | S | Same semantics in D2R. The "decoy" recipes depend on first match in row order with op rejection: check in game once. Check that D2R loads 11,477 rows (> 6,500 known to load). |
| 19 | Inventory 10x6, cube 10x8, stash 10x10 | mpq inventory.txt / .bin: classes 10x6, Transmogrify 10x8, Big Bank 10x10 | data | M | inventory.txt grids + D2R HD/legacy layout JSON (UI lane). Merge by class name: D2R's inventory.txt has no Guild Vault / Trophy Case rows and adds Warlock rows (`tools/vanilla113.py`). |
| 20 | Level cap 120 | experience.txt `MaxLvl` 120 for all 7 classes | data | XS | Replace D2R's `MaxLvl 99` row (keep the Warlock column). |
| 21 | Starting kit, innate skills | charstats.txt: box, hp1, tsc, zen, class charms; `Skill 1-10` = Throw, Kick, scrolls/books, Unsummon, class Innate skill | data | XS | D2R has the same columns. **Not** the repack's loose charstats.bin (it is vanilla 1.13c, section 4). |
| 22 | Uberquests and uberlevels (30) | No new levels: Pandemonium 1-Finale and other vanilla levels are reused. levels.txt gives Pandemonium 1 a Vis/Warp to level 17 and **Pandemonium 2 waypoint index 17, the same as Valley of the Kings**. Summoning ubers spawn through missile hit 6 (#9); clue gems/keys/relics are misc items + cube recipes | data (verify) | S | No PlugY uber quest (Laz's PlugYFixed.ini forces `ActiveUberQuest=0`) and no Pandemonium cube outputs. Verify the shared waypoint index in D2R's waypoint panel (1.13c shares the activation bit; D2R's panel may list only one level per index). |
| 23 | Challenges, honorific items, blessings, crafting | stats `var`, `var_blackroad`, `levelchallenge_kill_check`, `blessings-counter`, `desc-honorific` on cube outputs (3,200+ rows) | data | - | Pure table logic. Depends on #14. |
| 24 | Item use functions | misc pSpell 3 (signets add experience / stat points / gold bank via stat1/calc1), 6 (potions), 9 (elixirs: timed stats), 10 (Apple = +skill point, as Book of Skill); Token of Absolution has **no pSpell** (D2R's is 13) | D2R has it | - | Same vanilla functions. **Corrected (lane rules-chars, bug #240):** vanilla's `toa` row has no pSpell either; 1.13c runs the Token, Book of Skill, Potion of Life and Malah's scroll by item code (1.14d `0x55e3d0`-`0x55e52a`), D2R by pSpell 13 / 10 / 11 / 12. Median makes the Token in the cube ("ToA creation"), so it is Median's respec item; the build gives the four rows D2R's pSpell (`docs/median-rules-audit.md` SK9, QU2). |
| 25 | Elite / veteran / heroic monsters, monster AI | monstats rows, 144 vanilla AI codes, monumod | D2R has it | - | No special name colours in 2012 (that was Sigma's monstats3). |
| 26 | Seven classes vs D2R 3.3's Warlock | Median tables have 7 classes; D2R 3.3 tables carry an 8th (Warlock) column/row in charstats, playerclass, experience, inventory, skills | plugin | S | Merging must keep the Warlock entries or D2R breaks. Whether Warlock stays playable (with D2R's own skills) or is hidden at character creation is an owner question; hiding it needs UI/plugin work. |
| 27 | D2R-only systems switched on by default | terror zones (desecratedzones.json), D2R's Pandemonium cube outputs, D2R 2.4+ vanilla-row rebalances | data | XS | Terror zones off (`tools/d2r_adds.py`). The rest is replaced by Median's tables (replace-style merge, docs/porting-playbook.md). |
| 28 | Hardcoded D2R changes to vanilla rules | e.g. Rite of Passage experience (D2R 1.4M/20M/40M, `0x550c20`) and D2R's bug fixes (str/dex glitch, whirlwind chance-to-cast, shapeshift) | D2R has it | - | 2012 inherits these from D2R. D2R's fixes stay (they fix 1.13c bugs, Median 2012 does not rely on them). Rite of Passage: compare with 1.13c in a game check; a plugin hook if it matters (S). |
| 29 | D2R data asserts that 1.13c tolerated | Engine asserts of D2R's data checks (curse skills without cltmissile, nRadius, …) | data | S | Run validate.py's rules on the merged 2012 tables. |
| 30 | Leftover tables in the mpq | 19 unnamed files: item-base/affix-like tables, a "description enabled min diff …" table, 4 binary tables, 8 dc6 | drop | - | Not loaded by 1.13c under their (unknown) names; not part of the game. Re-check against the ModDB zip. |

## 3. PlugY: what the mod itself sets (mpq `plugy/`)

Laz says PlugY is not part of Median XL, yet the mpq carries two PlugY files. They take effect only if a player adds
PlugY, which then reads them from the mpq:

| Setting (plugy/plugyfixed.ini, "Features disabled by modmaker to prevent bugs (skill reassignment) or cheating") | Value | D2R 3.3 |
|---|---|---|
| ActiveStatsUnassignment | **1 (forced on)** | D2R has no per-point stat unassign; see section 5 |
| ActiveSkillsUnassignment | 0 | D2R: Akara / Token respec reset skills too, as in 1.13c (the Token's blank pSpell is vanilla's: 1.13c runs it by item code, bug #240); Akara's free respec is hardcoded in both games |
| ActiveStatPerLevelUp, ActiveSkillPerLevelUp | 0 | nothing to do |
| SeparateHardcoreStash | 1 | D2R has it (separate softcore / hardcore shared stash) |
| ActiveWorldEvent (Uber Diablo / SoJ) | 0 | D2R has no offline DClone: nothing to do |
| ActiveUberQuest (PlugY's Pandemonium) | 0 | Median's own ubers (#22) |
| ActiveLadderRunewords | 0 | no ladder rows (#17): nothing to do |
| ActiveVersionTextChange | 0 | cosmetic |

`plugy/statsinterface.txt`: Laz's layout for PlugY's extra stat pages, 4 pages, ~85 stats (craft points, MF/GF,
FCR/IAS/FHR/FBR, leech, %attributes, masteries/pierce, crushing/deadly, resist/max resist/absorb, minion stats, …).
In D2R this is the **Advanced Stats panel** (itemstatcost `advdisplay`, `txt_migrate.py advanced_stats`):
**data, S**, using this file as the list. The tables/UI lane decides.

## 4. Repack-only changes (not v005): drop

All under `extract-merged\` / `src-repack\`, which loose-override the mpq with `-direct`:

| File | Finding | Decision |
|---|---|---|
| `data/global/excel/charstats.bin` | **Vanilla 1.13c** charstats (Amazon str 20, `jav`/`buc`, Sorceress `sst`, …), not Median's. With D2SE `Direct=1` repack players got the vanilla starting stats and kit | drop: repack defect. Use the mpq's charstats |
| `data/global/excel/inventory.bin` | inventory 11x9 (mod: 10x6), trade 10x5 (mod: 10x4), other pages as mod | drop: repacker's bigger inventory (with `ui/panel/invchar6.dc6`) |
| `data/global/tiles/act2/maggot/*.ds1` (58 new + magqueen.ds1 changed, 2022) | repacker map edits | drop; re-check against the ModDB zip |
| palettes `ACT1-5/Pal.pl2`, `ui/Orb/*`, `ui/panel/*`, fonts, `A1L4x/A2L4x` | renderer / HD-orb / font cosmetics (2019-2023) | drop: D2R draws its own |
| glide3x.dll + d2gl.mpq/ini (D2GL), SGD2FreeRes.dll/.mpq/.json | renderer and resolution | D2R has it (HD renderer, widescreen) |
| D2SE_SETUP.ini | launcher (1.13c core, -direct, PlugY allowed) | drop |

## 5. Optional extras: the repack's PlugY.ini (owner decides)

PlugY 14.03 with the repacker's PlugY.ini. PlugYFixed.ini in the mpq wins over PlugY.ini where both set a key (rows
marked "fixed"). None of these are part of v005 itself.

| PlugY feature (repack value) | Median 2012? | D2R 3.3 / D2RLoader | Suggestion | Effort |
|---|---|---|---|---|
| Stat unassign, Alt+click (on; also **forced on by Laz's fixed ini**) | modder-endorsed | not in D2R | owner: plugin (per-point unassign, from a stat shift-click hook) or accept D2R's Akara respec | M |
| Skill unassign (off, fixed off) | Laz forbids | Akara respec resets skills | keep D2R's Akara respec or block its skill part (plugin S) — owner | S |
| Shared stash (on), shared gold (on), separate HC stash (fixed on) | tolerated (README: remove non-Median items) | D2R has it (shared tabs, shared gold, separate HC) | D2R has it | - |
| Multi-page stash, personal + shared, unlimited pages | repack extra | D2R: 1 personal + 3 shared tabs (stash 10x10); D2RLoader extra pages | owner; D2RLoader stash pages if wanted | S |
| Extra stat pages (on) | mod-supplied layout (section 3) | Advanced Stats panel | data | S |
| World event, PlugY uber quest (fixed off) | off by Laz | - | drop | - |
| Ladder runewords (fixed off) | off by Laz | - | nothing to do | - |
| Display item level (on) | repack extra | not shown by D2R | drop (or plugin, S) | - |
| Always show life/mana values (on) | repack extra | D2R has it (option) | D2R has it | - |
| Display base stat values (on) | repack extra | Advanced Stats shows totals | drop | - |
| Cow portal after killing the Cow King (on) | repack extra | D2R keeps the vanilla rule | drop | - |
| Don't close Nihlathak's portal (on) | repack extra | vanilla rule | drop | - |
| Move Cain near the Harrogath waypoint (on) | repack extra | vanilla | drop | - |
| /commands, auto backups (20/char), launch many LoDs, version text | repack extras | D2R/D2RLoader own tooling | drop | - |
| D2GL, SGD2FreeRes | repack extras | D2R HD + widescreen | D2R has it | - |

## 6. Summary

Phase 3 closed every row: verdicts in section 7 (same 13, ported 15, unported 2; 2026-10-29: #24's Apple part moved to the plugin plan, bug #499). The static triage below is kept as written.

Section 2 (v005 behaviours, 30 rows): **data 20** (7 of them "verify" in a game check: #5, #6, #9, #10, #16, #18,
#22), **plugin 2** (#4, #26), **D2R has it 6** (#11 and #12 cover the whole remaining function and calc space),
**drop 2** (#8, #30). Repack-only (section 4): 5 drop, 1 D2R has it. PlugY extras (section 5,
15 rows): 3 D2R has it, 1 data, 8 drop / nothing to do, 3 owner decisions (stat unassign, skill-respec rule, stash
pages).

Top plugin / verify work items:
1. **Missile server hit 6** (#9): game-check the 102 spawner rows (summoning ubers); fallback route to a plugin hit 68.
2. **Client do 22** (#4): plugin client slot 113.
3. **Unused-by-vanilla slots** cltdo 83, srvprg 22/119/51, cltprg 25/28, srvhit 23 (#5, #6, #10): one game check.
4. **Warlock** (#26): owner decision; UI/plugin work only if Warlock is hidden.
5. **Stat unassign** (section 5): owner decision; plugin M if kept.
6. **Shared waypoint index 17** (#22): game check of D2R's waypoint panel.

Data traps for the other lanes: stat ids in cubemain `param` and monster rows in missile `sHitPar1` (#14); the 1.13c
slot remaps (#1-#3, #7); descfunc strings (#15); never take charstats.bin / inventory.bin from the repack (section 4).

Open questions for the owner: Warlock playable or hidden; stat unassign (PlugY-style) yes/no; keep D2R's Akara
respec of skills given Laz's "no skill reassignment"; extra stash pages yes/no.

## 7. Closure (lane triage, phase 3, 2026-10-28)

Each row of section 2 ends as **same** (confirmed: same behaviour in D2R 3.3 as 1.13c, by a game check and/or a static
comparison with the 1.14d `Game.exe` in `gamedata/`, the nearest Blizzard build we can read), **ported** (plugin part or
data change, with the check named) or **unported** (row in [unported.md](unported.md) with the reason). Game runs: slot 2,
background mode, plugin 0.1.0 dev of lane/triage, character `Triagebarb`; reports `work/runs/checks-20261028-12*-s2/`,
`checks-20261028-13*-s2/` (not in git), summary in [testing.md](testing.md) "Lane triage". Harness verb added by this lane:
`watch cltdo|srvhit <index>` counts the calls of one function-table slot on the real path (docs/plugin-plan.md 10.1).

| # | Verdict | Evidence |
|---|---|---|
| 1 | ported (data) | `idmap.SLOT_REMAP` srvdo 109 -> 9. `test_idmap.IntegrationTest.test_engine_slot_cells`: MonFrenzy, BloodLordFrenzy, Feral Strike on (67, 9). Check `frenzy` PASS: Feral Strike (dagger oskill) by left clicks, zombie life 62 -> 33; a Thorn Hulk's MonFrenzy and a Blood Lord's BloodLordFrenzy at the player, 3 casts each, player life 29999 -> 29804; 0 town portals (D2R's 109 is "Townportal O Skill") |
| 2 | ported (data) | srvst 64 -> 67, (37, 109) -> 67; same test asserts Massacre stays on (37, 13); same check |
| 3 | same (static) | 1.14d's client start table (`0x727a90`, bound `0x727a8c` = 70, slots 54-69 empty) has no slot 82 either, as D2R (bound 70): the 1.13c-family code never called a function for cltstfunc 82, so blanking it loses nothing. unported.md row rewritten |
| 4 | ported (plugin) | part `cltdo22` (slot 113). Check `rockshock`: real cast, client wall calls +3, monster life -34 (lane plugin / gameplay, testing.md) |
| 5 | same | Static: D2R `0x2b25e0` = 1.14d `0x4f2fe0` (plugin-plan.md 4.1); the dispatchers that call it match too (D2R `0x216d20` / 1.14d `0x4c6680`: skill record, cltdofunc at `+0x14a` / `+0xf4`, bound 130, cltprgfunc when the caller asks; the current-skill caller D2R `0x216c60` = 1.14d `0x4c68f0`). Game, check `cltdo83` PARTIAL: Titan Strike (learnt) by left and right clicks reaches slot 83 6 times (last skill 8) and makes no missile, as the function returns 0 without a cltmissile. The missile branch is not shown in game: Soulshatter starts only on the player's own pet (srvstfunc 3 = Unsummon's start, TargetPet) and Mana Sweep is a sorceress skill; clicked oskills run the client's previously selected skill (a harness limit, see testing.md). Control: client do 19 (Aerials Disaster, learnt) makes its missiles per click (3 + 3). Lane skillsweep (sorceress, player path, docs/skill-sweep.md): Mana Sweep (546, learnt) by left and right clicks on a zombie reaches slot 83 with last skill 546 and makes no client missile either: Mana Sweep has `range none`, and `0x2b25e0` (as 1.14d `0x4f2fe0`) returns 0 without a target unit, so the client branch is never taken for it in 1.13c either. The skill's effect is its server missiles (one sweepcenter 1119 per click; the zombie hit by the right click and gone after the left one): verdict ok, slot 83 same as 1.14d |
| 6 | same | Lane skillsweep, check `skillprog` (slot 4, assassin `SweepAssassin` with a claw worn and re-entered, bug #391): Batstrike charges 1 -> 2 -> 3 by left clicks, Attack clicks release the finisher (`knocknova` 1449 x64), client prg slot 25 reached (1 call, last skill 326), no assert: same. Blackstorm: slot 28 reached 3 times (last 514); the check's FAIL is its old criterion (`blackstorm1` is never seen by the tracker, as in the earlier runs); the sweep shows its state and missiles. Before: Blackstorm cltprg 28: check `skillprog`, the slot is reached by right clicks (runs 1 and 2: 4 and 2 calls, last 514). Batstrike (srvprg 22/119/51, cltprg 25): no assassin could be played in slot 2 (`be_class(6)` failed twice); static only (same numbers in both games, plugin-plan.md 4) |
| 7 | ported (data) | corpseexplosion on pCltDoFunc 69, vine beast death on 70; the other corpse / debris rows stay on 11 as D2R's own rows; `test_engine_slot_cells` |
| 8 | unported | already in unported.md (dropped, nothing lost: 1.14d's client hit 11 is empty too) |
| 9 | ported (data) | sHitPar1 rows remapped; check `srvhit6spawn` PASS (testing.md, Harness lane) |
| 10 | same | Check `srvhit23` PASS (run 3): Bloodspeakers Mark (oskill of a worn spear) by left clicks, right clicks and server casts: hit 23 (`exe+0x4533c0` = 1.14d `0x5acfc0`) called 8 times, last missile 1393 (bloodspeakerbolt); srvdo 119 summons a bloodspeakerpet per hit (8 alive): neither D2R `0x575990` nor 1.14d `0x5c7390` tests petmax (a start-function rule), so 1.13c did the same. leapingjumper (no Median skill fires it) reaches the slot through the harness. New bug #270: D2R asserts on the pet's target-list add where 1.14d skips the same add silently; explained, harmless |
| 11 | same | skill sweep (docs/skill-sweep.md, lane skillsweep on the player path: 168 ok, 1 assert (#54), 0 broken, 41 passive) and monster sweep (1795 of 1839 rows spawn) |
| 12 | same | the build compiles every formula (validate 0 errors); calc codes identical (section 2) |
| 13 | ported (data) | tools/idmap.py + `test_idmap` (lane idmap) |
| 14 | ported (data) | every cubemain `op` param stat id maps by name: 11,477 rows, 0 mismatches; `test_idmap` covers the cube param |
| 15 | ported (data) | descfunc strings without `%d` (lane strings / monitems tooltips, testing.md) |
| 16 | same | check `rprunes` (RP2, lane rulescheck) PASS on the player path: the padded row (jewel, jewel, El) in a 3-socket Broad Sword makes Dawn as El alone in a 1-socket Short Sword does; El first in the wrong order or a magic base makes none; Kyrie (Taha, Taha) made: D2R's exact-row matcher counts the jewels as 1.13c's. 3,133 rows load. unported.md row restored (lane phase3, 2026-10-29) |
| 17 | same | data fact: no ladder gate in runes.txt or cubemain |
| 18 | same | check `cubeclasses` (lanes cube / cube2, median-rules-audit.md "Cube recipe classes in game") on the player path: first match in row order with op rejection, as 1.13c (honorific row 8169 rejected by op 15, so row 8226 makes the Apple of Discord; the honorific row before row 7728; op 3 refusal 565 leaves the cube unchanged; op 18 refuses the second dupe 8397); rows up to 11399 transmute. unported.md row restored (lane phase3, 2026-10-29) |
| 19 | ported (data) | lane integ: inventory 10x6, cube 10x8 drawn in HD and classic (testing.md) |
| 20 | ported (data) | experience.txt MaxLvl 120 (testing.md, Harness lane) |
| 21 | ported (data) | lane qa: starting kit and innate skills (testing.md) |
| 22 | same | check `pandewp` PARTIAL (the panel's look is by eye): Pandemonium 2 (134) reached by the waypoint warp; no class-402 waypoint object there, as 1.13c (its preset loop skips 402 in level 134), so nothing in Pandemonium 2 sets bit 17 by operating; the Valley sets bit 17 = 1 and the panel opens |
| 23 | same | pure table logic on #14's ids |
| 24 | ported (plugin) | lane phase3, check `rpsignets` (slot 3, run `checks-20261029-184343-s3`; items picked up by a click, used by a right click): **pSpell 3 same**: Signets of Gold (+150 gold), Experience (+250), Learning (+1 stat point, potion_stat_cap +1), Bling Bling (+5 / +5), Buyable Signet of Gold (+150 bank) and Signet of Skill (+1 skill point, potion_skill_cap +1) each give misc.txt's calc1 / calc2 at level 1 and are used up. **pSpell 10 differs**: 1.14d's item spell 10 (`0x5bf170`) starts skill 47 (Median: Apple Healing Spell), D2R's runs the Book of Skill, so the Apple is refused (bug #499); moved to the plugin plan (section 25). Lane apple (2026-10-30): plugin part `appleuse` runs 1.14d's entry 10 for every pSpell 10 item but the Book of Skill; `rpsignets` and `apple_use` pass. pSpell 9 (elixirs): lane elixir |
| 25 | same | monster sweep (testing.md, Lane monsweep) |
| 26 | ported (data) | owner decision: Warlock stays playable with D2R's own skills; the merge keeps its entries |
| 27 | ported (data) | check `terrorzones` PASS (testing.md) |
| 28 | same (static) | Rite of Passage: D2R `0x550c20` and 1.14d `0x58c5c0` both give 1,400,000 / 20,000,000 / 40,000,000 per difficulty after the same level-cap test; no plugin hook needed |
| 29 | ported (data) | validate.py rules + plugin guards (`cltnomis`, `cltdostub`, `statelist`); every build ends with validate 0 errors |
| 30 | unported | already in unported.md (dropped) |

Count (30 rows): **same 13** (#3, #5, #6, #10, #11, #12, #16, #17, #18, #22, #23, #25, #28), **ported 15**
(#1, #2, #4, #7, #9, #13, #14, #15, #19, #20, #21, #24, #26, #27, #29; #24's pSpell 10 part is plugin part `appleuse`, bug #499),
**unported 2** (#8, #30 dropped). #6's Batstrike, "verify" before, is same since lane skillsweep; #16 and #18 are same by lane
rulescheck's `rprunes` and lanes cube / cube2's `cubeclasses`; #24 was checked by lane phase3 (2026-10-29). Nothing in section 2 is left
without a verdict.
