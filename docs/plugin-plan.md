# Plugin plan: mxl2012-core (D2RLoader 1.3.1, D2R 3.3)

Design only (lane pluginplan, 2026-10-28). No plugin code here: the skeleton is being copied as `mxl2012-core` by another
lane. This file says, item by item from [engine-triage.md](engine-triage.md), what D2R 3.3 does today, which part of the
existing plugin code (read-only reference) already does it, and whether that part is
copied as-is, changed, or written new.

Sources (static reading only, no game run): reference notes outside this repo (plugin spec, function slots, D2R addresses,
subsystems, stash pages, release, bug list, plan),
`tools/d2r_adds.py`, `plugin/src/*.cpp`; Median 2012 tables from `mxl2012-runs\extract-mpq\` (pure v005, repack source:
re-check against the ModDB zip); D2R baseline tables `<extract_dir>\...\excel\base\` (machine-local config, docs/setup.md).

Owner decisions applied (2026-10-28): **Warlock stays playable** (no "hide Warlock" part) and **Akara's respec stays D2R's**
(no respec part). Both rows are gone from this plan; no existing respec code (`quests_act2_5.cpp` `0x5d9ae0`
hook, `respecbuffs`, `freerespec`) comes over.

Effort: XS < 1 h, S < 1 day, M a few days, L a week or more (same scale as engine-triage.md).

## 0. Summary

| # | Item | D2R 3.3 today | Plan | Existing part | Copy | Effort | In v0.1 |
|---|---|---|---|---|---|---|---|
| A | Client do 22 (Rock Shock, ParasiteSkill) | slot 22 is not 1.13c's function | data remap 22 -> 113 + plugin client function | `sigma_skills.cpp` `CltDoWall`, slot 113 | copy, small cut-out | S | yes |
| B | Missile server hit 6 (102 rows) | D2R's own hit 6 (`0x45ce90`) spawns monstats row sHitPar1: **the same job** | data (idmap of sHitPar1) + game check; plugin only if the check fails | fallback `missile_hits.cpp` `HitSpawnCorpse` (slot 65), **not** hit 68 | none / fallback copy | XS (S fallback) | check only |
| C | Unused-in-vanilla slots: cltdo 83, srvprg 22/119/51, cltprg 25/28, srvhit 23 | D2R has a function in each slot (not verified to be 1.13c's) | one game check; plugin port per slot only if it fails | none | new if needed | S check, M per failed slot | check only |
| D | Empty missile function slots (crash guard) | D2R calls client do / server hit table entries with no null check | stubs in every empty slot | `missile_hits.cpp` empty-slot stubs | copy as-is | XS | yes |
| E | Build guard, wrong-version notice | - | image stamp 0x6ab3782c + build name 93847; player text says "3.3" | `build_guard.cpp`, `build_guard_logic.h`, `mxl2012_core.cpp` | change the text | XS | yes |
| F | Other-plugin guard | another engine plugin and mxl2012-core would write the same table slots | refuse to install next to it | `other_plugins_logic.h`, `mxl2012_core.cpp` `LogOtherPluginsLater` | copy, change ids | XS | yes |
| G | Dev test harness (for the game checks) | - | dev builds only, a small verb set | `testharness.cpp`, part of `harness_cmds.cpp` | copy, cut down | S-M | yes (dev only) |
| H | Pandemonium 2 waypoint index 17 (shared with Valley of the Kings) | D2R's panel lists actinfo levels; a number maps to one level | game check; same as 1.13c expected, nothing to build | fallback `waypoints.cpp` `InstallWaypointPanel` | none / fallback change | XS (M fallback) | check only |
| I | Stat unassign (Laz's PlugY ini forces it) | no per-point unassign in D2R | **optional, owner**: new part | starting point `stat_rules.cpp` `StatClickHook` (`0x4b3c70`) | new | M | no |
| J | Extra stash pages | 1 personal page + 3 shared tabs | **optional, owner**: shared tabs are data (`add_shared_tabs`); personal page 2 is plugin | `stash_pages.cpp`, `mxl_stash_page.h` | change (size 10x10) | XS data / M plugin | no |
| K | D2R additions that conflict with Median | see section 9 | data first (lane d2radds); a hook only if data cannot switch it off | data only (`tools/d2r_adds.py`) | - | XS-S | check only |

**mxl2012-core v0.1 = E + F + A + D (+ G in dev builds).** Effort for v0.1 on top of the skeleton: about 1.5-2 days
(A: S, D/E/F: XS each, G: S-M). B, C, H, K are game checks that may add a part later; I and J wait for the owner.

## 1. Plugin rules

### 1.1 Build guard (image stamp, build 93847)

Every RVA in this file is an address of the dumped D2R.exe of **D2R 3.3.0 build 93847** (PE `TimeDateStamp` **0x6ab3782c**,
D2RLoader 1.3.1). The rule (`plugin/src/build_guard_logic.h` `build_guard::Matches`, unit test
`plugin/tests/build_guard_test.cpp`):

- Hooks and patches go in only when the image stamp is `0x6ab3782c` **and** D2RLoader's `buildName` (when its context has
  the field) is `"93847"`. An empty / missing build name with the right stamp is accepted.
- On any other image the plugin installs **nothing** (no hook, no patch, no table write, no harness), logs one ERROR line,
  draws one line at the top of the screen through D2RLoader's overlay service (`build_guard.cpp` `ShowWrongBuildNotice`,
  registered at load, `Overlay::Phase::AfterGameUi`), and keeps only its console command (`mxl2012`) so a player can read why.
- Each part also checks what it overwrites: table slots are written with `PatchWriteU64` and an expected old value (0 for an
  empty slot, the D2R function for a wrapped slot), inline hooks with `InstallInlineHook` and the expected entry bytes. A
  mismatch turns that part off and its status line says so. This is a second guard under the image stamp, not a substitute.
- Every part has an off word in `mxl2012-core-off.txt` next to the DLL (read by
  `ReadOffList` / `Off()` in `mxl2012_core.cpp`), and a status line in the `mxl2012` console command.

### 1.2 Player-facing requirement: "3.3", never a build number

- Whatever a player reads (release notes, README, downloader/launcher, the plugin's on-screen notice, the `PluginInfo`
  description) names the requirement as **Diablo II: Resurrected 3.3** (and D2RLoader 1.3.1), never "build 93847".
- The build number and image stamp are internal: the guard compares them, and the **log line** may carry them for support
  (`image 0x6ab3782c`, `buildName 93847`) because players send logs, not because they need to understand them.
- So `build_guard::Message` names no build number. The mxl2012 text:

      D2R-XL 2012 <version> needs Diablo II: Resurrected 3.3; this game is a different version. The mod's engine changes are off.

  and the log gets a second line with the stamp and build name found. The unit test asserts the screen text contains
  `"3.3"` and no digit run of 5 (no build number).
- PluginInfo: `id "mxl2012-core"`, `name "D2R-XL 2012 core"`, flags `Shared | ModScopedOnly | NativeHooks`,
  description e.g. "Engine support for D2R-XL 2012, the Median XL 2012 port (D2R 3.3)". `PluginVersion` starts at 0.1.0
  (bumping is the coordinator's call).

### 1.3 Other plugins (F)

Another engine plugin may write the same free table slots (client do 113, the empty-slot stubs). `ModScopedOnly` keeps it out of
the `mxl2012` mod, but a stray DLL in the game-wide `d2rloader\plugins` loads with every mod. Copy
`other_plugins_logic.h` and the module walk (`D2RLoaderGetPluginInfo` id check), changed so that when a
conflicting module (or a second `mxl2012-core`) is in the process, mxl2012-core installs nothing and shows a notice
naming the DLL to remove from d2rloader\plugins. XS.

## 2. A: client do 22 (Rock Shock, ParasiteSkill)

**Median 2012 rows** (skills.txt): `Rock Shock` (row 28) and `ParasiteSkill` (row 408): srvdofunc 14, **cltdofunc 22**,
srvmissilea / cltmissilea / cltmissileb = `rockshock` / `purgestrike`, aurarangecalc `par1`. That is a copy of 1.13c's
Lightning Strike row (srvdofunc 14, cltdofunc 22, aurarangecalc par1).

**D2R today:** D2R's Lightning Strike row is srvdofunc 14 with **cltdofunc blank**: the 1.13c client half is gone from
the data. Earlier notes disagree on what D2R's table slot 22 holds now: function-slots.md says "empty",
plugin-spec.md says "an Amazon chain-lightning client". Either way slot 22 is not 1.13c's function, so the rows must leave it.
Client do table `0x235f7d0` (8-byte pointers, bound 130 at `0x235f7c4`, dispatcher `0x216d20` calling (unit, skill, level));
110-129 are free in D2R.

**Existing part:** `sigma_skills.cpp` `CltDoWall`, installed into client do slot **113** (`ClientFunctions[]`,
`PatchWriteU64(0x235f7d0 + 113*8, expected 0)`). It is D2Sigma's client 22 (`0x100a7fa0`): two `cltmissilea` client missiles
on the skill's target point, the point pulled to within aurarangecalc of the caster, flying out perpendicular to the cast
direction (flags 0x21). It runs the same three rows of later Median versions (rock_shock, parasite_2, parasite_3) that Median 2012 has,
and D2Sigma kept vanilla numbering for vanilla functions, so it is very likely a rebuild of 1.13c's Lightning Strike client
half. **Not proven**: nobody compared it with 1.13c D2Client's function 22. Not ported there: the spot's collision
test and the town check; 2012's `cltmissileb` is not used (as in D2Sigma's).

D2R pieces it needs: data flag `0x34a0e0`, client target point `0x214c80`, client missile `0x1b7760` (&params, 0), skill
record getter + `evalSkillCalc` + `missileCount` from `d2r.h` `api`, record offsets cltmissile `+0x13e` (a/b/c `+0x140/+0x142/
+0x144`), aurarangecalc `d2r::SkAuraRangeCalc`, `d2r::MissileParams`, `d2r::UnitXY`.

**Plan:** copy `CltDoWall` and the client slot loop into a new small file (e.g. `client_skills.cpp`, off word `cltdo22`)
with only the `d2r.h` pieces above; **nothing else of `sigma_skills.cpp`**. Data side (tables lane): cltdofunc 22 -> 113 on
both rows (`clt_moved` in `txt_migrate.py`), plus a validate rule that no Median row is left on cltdofunc 22.
Without the plugin the server half (srvdofunc 14) still works; only the client visual is missing.

Copy: **as-is plus cut-out**. Effort **S** (mostly trimming `d2r.h` and wiring). Game check `rockshock`.

### 2.1 CltDoWall compared with 1.13c's client do 22 (lane plugin, 2026-10-28; static reading, no game run)

Built in v0.1 as `plugin/src/client_skills.cpp` (off word `cltdo22`, slot 113, geometry in `client_skills_logic.h`, unit test
`clientskills_tests`). What is known about the two functions:

| | 1.13c D2Client client do 22 (what Median 2012 ran) | CltDoWall (a port of D2Sigma's 22, now in mxl2012-core) |
|---|---|---|
| Code | vanilla D2Client.dll 1.13c: Median 2012 v005 ships **no DLL** (engine-triage.md: patch_d2.mpq only, D2SE `ModDll` empty), so 2012 ran Blizzard's function | D2Sigma's own code: an audit of D2Sigma's patches (client5) says D2Sigma's cltdofunc table "replaces 11, 15, 22, 31, 93-95", i.e. **D2Sigma's 22 is not the 1.13c pointer** |
| Decompile | none: only a 1.13 D2Game decompile exists; no D2Client one | D2Sigma `0x100a7fa0` (read statically) |
| Vanilla rows on it | Lightning Strike (Amazon, row 34): srvstfunc 10, srvdofunc 14, cltmissilea/b/c `lightningstrike`, aurarangecalc `par1` (20), range h2h | - |
| 2012 rows | Rock Shock 28 (cltmissilea/b/c `rockshock`, missile row 2214), ParasiteSkill 408 (`purgestrike`, row 2156): the same layout as Lightning Strike, no charclass (monster skills) | the same rows after idmap 22 -> 113 |
| What it does | **unknown**: no source. From the data it is the client half of a melee strike whose server half (srvdofunc 14) throws srvmissilea at the hit target | two `cltmissilea` client missiles (flags 0x21) on the skill's client target point, the point pulled to within aurarangecalc (20) of the caster, flying out perpendicular to the cast direction, one to each side |
| Not in the port | - | D2Sigma's collision test of the spot (D2Common 10303, mask 5) and its town check; cltmissileb/c (2012 repeats a there, so no difference) |

What D2R itself does with the same row: D2R kept Lightning Strike's server half (srvstfunc 10, srvdofunc 14, same
missiles) and **blanked its cltdofunc**; Lightning Strike still shows its bolts in D2R because the server's missiles are sent
to the client. So the D2R-native equivalent of "1.13c's Lightning Strike client half" is *no client function at all*, and
earlier notes disagree on what D2R's slot 22 holds now (function-slots.md: empty; plugin-spec.md: an Amazon chain-
lightning client); `h slot cltdo 22` reads it in game.

Differences to expect, and what `rockshock` must settle:

1. **Extra visual.** If 1.13c's 22 only accompanied the server's missiles (as D2R's blank row suggests), CltDoWall adds two
   client-only `rockshock` / `purgestrike` missiles that 2012 never drew. They are client missiles (no damage, no server
   unit), so gameplay is the same either way; the difference is what the player sees.
2. **Placement.** CltDoWall puts its missiles on the skill's target point clamped to 20 sub-tiles from the caster and flies
   them sideways (a short wall). A melee strike's target is adjacent, so the clamp rarely matters.
3. **No town / collision test.** D2Sigma skipped a spot that is blocked or in town; the port does not (no
   report of a problem; the skills are monster skills, rarely cast in town).

Decision rule for the test lane: run `rockshock` twice, with the plugin as installed and with the control "D2R's way":
Rock Shock and ParasiteSkill with a **blank cltdofunc** in the installed skills.txt (exactly D2R's Lightning Strike row).
The `cltdo22` off word is the second control (rows on 113, slot left empty); it is safe only if D2R's skill client
dispatcher `0x216d20` skips an empty slot, which nobody has verified, so run it last and treat a crash there as that
answer, not as a v0.1 bug. If the blank-row run shows the rock/purge bolts from the server and no crash, the faithful
choice for 2012 is the **D2R way** (cltdofunc blank, no plugin slot) and CltDoWall should be dropped (owner call: it is
D2Sigma's look, not 2012's); if it shows nothing at all, keep CltDoWall. Either way the data remap 22 -> 113 is harmless.

## 3. B: missile server hit 6 (102 rows, summoning ubers and spawners)

**Median 2012 rows:** 102 missiles with pSrvHitFunc 6, sHitPar1 = a monstats row (e.g. `treewardenspawner` 1107,
`edy1summon` 1222, `darkonesummon` 1221), sHitPar2 = 1 on 99 rows and 0 on 3. No vanilla row of either game uses 6.

**D2R today:** server hit 6 = `0x45ce90` -> `0x50a050(game,
room, sHitPar1, ...)`, i.e. **D2R's hit 6 spawns sHitPar1 as a monster row at the missile**. Later Median versions ship 406 hit-6 rows
on it; a crash there was a data bug (sHitPar1 left on Median's old monstats numbers), fixed in `txt_migrate.py` (sHitPar1
through the monstats id map, report line `missiles: N hit-6 spawn rows ...`) and caught by `validate.py` rule `hit6_spawns`.
A game check `denboss` saw D2R's hit 6 spawn the right (remapped) monster. Server hit table `0x2391030` (record `+0x2e`,
bound 71 at `0x2391404`, dispatcher `0x464ac0`).

So the triage's worry ("game check first") is mostly answered: **D2R's 6 is a monster spawner, no plugin is needed**. What is
not yet known: how D2R's 6 uses sHitPar2 (2012: 1 = mode NU? or a count?) and whether it spawns in the mode the summoning
ubers expect.

**Plan:** data only: the idmap/tables lane must rewrite sHitPar1 through the monstats map (engine-triage #14) and copy the
`hit6_spawns` validate rule. Game check `srvhit6spawn`.

**Fallback if the check fails** (wrong mode, wrong count): route the 102 rows to a plugin slot running
`missile_hits.cpp` **`HitSpawnCorpse` (slot 65)**, not hit 68: `HitSummon` (68) reads the monster from the *skill's calc1*,
while `HitSpawnCorpse` reads **sHitPar1 as the monster and sHitPar2 as the mode** (0-15, else 1), which is exactly 2012's
layout. Copy it without the `Param4` "last revived class" path and the `ReviveRecording` wrap (Habeas Corpus is D2Sigma's).
D2R pieces: owner `RvaMissileOwner`, room `RvaUnitRoom` / `RvaRoomAt`, spawn `0x492cf0` (game, room, x, y, monster, mode,
-1 then 4 = search, flags). Slot: any server hit slot 61-70 (all free in D2R; mxl2012-core uses none of
61-69). Effort XS for the check, **S** for the fallback.

## 4. C: slots no vanilla skill uses (one game check)

| Column | Slot | Median 2012 rows | D2R | Check |
|---|---|---|---|---|
| cltdofunc | 83 | Titan Strike (row 8), Innate Titans (9), Soulshatter (18), Mana Sweep (474) | client do table `0x235f7d0`, slot below the bound 130, filled; no D2R row uses it | `cltdo83` |
| srvprgfunc1/2/3 | 22 / 119 / 51 | Batstrike (326, srvdofunc 35) | same numbers in both games for every vanilla row (an earlier audit: nothing differs in srvprg / cltprg) | `skillprog` |
| cltprgfunc1 | 25 | Batstrike | as above | `skillprog` |
| cltprgfunc1 | 28 | Blackstorm (442, srvdofunc 29) | as above | `skillprog` |
| pSrvHitFunc | 23 | bloodspeakerbolt (row 1335, sHitPar1 119), leapingjumper (row 2183, sHitPar1 27) | server hit table `0x2391030`, slot 23 filled; no D2R row uses it | `srvhit23` |

**D2R today:** each slot holds a D2R function; that it is 1.13c's function at the same index is likely (D2R kept vanilla
numbering except the slots in function-slots.md) but unverified. No existing part covers any of them (later Median versions do
not use them).

**Plan:** before the game run, a short static step: name the D2R function at each slot from the dump (a Ghidra
project of image 0x6ab3782c, read-only) and the 1.13c one from a decompile of 1.13 D2Game
(server slots only; there is no D2Client decompile, so the client slots rely on the game
check). Then one game check pass. For a slot that does not match: **new** plugin function (a port of the 1.13c function)
into a free slot (client do 114-129, server hit 61-70; prg tables: find their bounds first) plus a data remap, M each.
Effort: S for the check; nothing else expected.

### 4.1 Static step done (lane gameplay, 2026-10-28): both slots are 1.13c's function, no plugin part

Neither a Ghidra project nor a D2Game decompile is readable from this project, so the step compared two images
read statically (capstone, read only): D2R 93847 dumped from a slot-2 game (`tools/dump_image.py`, evidence
`mxl2012-runs/gameplay/d2r93847_dump.exe`, not in git) and the project's own **1.14d `Game.exe`** (`gamedata/`, D2Client + D2Game
merged; its function tables have D2R's sizes: skill client do bound 130, missile client do 91, client hit 81, server hit 71), the
nearest Blizzard build to 1.13c we can read. Table addresses in 1.14d: skill client do `0x727ba8` (bound `0x727db0`, indexed by
the skill record's cltdofunc and cltprgfunc), missile server hit `0x73c840` (bound `0x73c83c`), missile client hit `0x72a508`
(bound `0x72a504`), skill srvdo `0x7322b0` (191), srvst `0x732140` (91).

| Slot | 1.14d function | D2R function | What it does (both) | Verdict |
|---|---|---|---|---|
| cltdofunc 83 | `0x4f2fe0` | `0x2b25e0` | skill record, the skill's client missile (`0x4f21b0` / `0x2b35f0`; none = return 0), the skill's target **unit** (`0x4648f0` / `0x9a570`; none = return 0), a count (`0x4f2260` / `0x2b3490`, else the skill calc at record `+0x64` / `+0x84`), then that many client missiles at the target | same function. The harness `cltdo 8/9/18/546` returns 0 because it has no target unit, as 1.13c would; the look needs a real cast at a monster (`cltdo83` screenshot) |
| pSrvHitFunc 23 | `0x5acfc0` | `0x4533c0` | the missile's skill id and level, owner check (`0x552fd0` / `0x490300`), records the hit target (`0x620c10` / `0x34e0c0`), then runs **skill server do function `sHitPar1`** (bound 190) for the missile with that skill and level (`0x56d810` / `0x435490`, table `0x7322b0` / `0x238ea00`) | same function. bloodspeakerbolt runs srvdo 119, leapingjumper srvdo 27 (Leap); both numbers are vanilla slots D2R did not renumber (function-slots.md), so no data change. sHitPar1 is a srvdo number, not a missile row (why `srvhit23` sees no second missile) |

The prg slots of the table above stay as the earlier audit says (same numbers in both games); cltprgfunc 28 (Blackstorm) is
1.14d's Meteor / Blizzard client do (`0x4e3910`: the skill's client missile at the target), shared by do and prg in the one
table. Blackstorm's client assert (bug #20) is not the slot: it is D2R's cast-id bookkeeping before any client do runs.

### 4.2 Game verdicts (lane triage, 2026-10-28): no plugin part

Slot 2, background mode, real clicks (no god mode: only mana raised for cltdo83 / srvhit23), `watch cltdo|srvhit <index>`
counting the slot's calls (section 10.1). Details: engine-triage.md section 7, testing.md "Lane triage".

| Slot | Game result | Verdict |
|---|---|---|
| pSrvHitFunc 23 | `srvhit23` PASS: Bloodspeakers Mark's bolts (left / right clicks and server casts) reach `exe+0x4533c0` 8 times, last missile 1393; one bloodspeakerpet per hit (srvdo 119 tests no petmax in D2R `0x575990` nor 1.14d `0x5c7390`); leapingjumper reaches it through the harness only | same; D2R's target-list assert after the summon is bug #270 (1.14d `0x5b1900` skips the same add without an assert) |
| cltdofunc 83 | `cltdo83` PARTIAL: Titan Strike (learnt) reaches `exe+0x2b25e0` by left and right clicks (3 + 3), last skill 8, no missile (no cltmissile: returns 0, as 1.14d). Soulshatter needs its own pet as target (srvstfunc 3 = Unsummon's start), Mana Sweep is a sorceress skill: the missile branch stays static | same (dispatchers D2R `0x216d20` / `0x216c60` = 1.14d `0x4c6680` / `0x4c68f0`) |
| cltprgfunc1 28 | `skillprog`: Blackstorm by right clicks reaches slot 28 (4 and 2 calls, last 514) | same |
| srvprg 22/119/51, cltprg 25 | Batstrike: no assassin in slot 2 (`be_class(6)` failed) | same (lane skillsweep `skillprog`: charges, finisher, cltprg 25 reached) |

## 5. D: empty missile slots (crash guard, v0.1)

**D2R today:** the client missile tick `0x1ba040` calls client do `table[record +0x28]` (`0x2358430`) for
any index below its bound with **no null check** (slots 0 and 78-90 empty), and the server hit dispatcher `0x464ac0` does the
same for 1 <= index < 71 (61-70 empty). A missile row pointing at an empty slot crashes the client outside town.

**Median 2012:** 2 missile rows have an empty pCltDoFunc (= slot 0); the server hit values used stop at 59 (no 61-70), but
any later remap into a free slot must not leave a gap.

**Existing part:** `missile_hits.cpp` `InstallMissileHits(..., clientDoStubs)`: fills every empty slot below the bound of both
tables with a do-nothing function (`g_cltDoEmpty[]`, `g_srvHitEmpty[]`) that logs the first missile row per slot; off word
`cltdostub`. **Copy only this part** (plus its report line), as-is. **Not** the 9 server hits, 2 client hits, phalanx or
revive wrap. Order rule: the stubs go in after every real function the plugin installs (else they take the free slots).
Effort XS. Game check `cltdostub` (harness `missilescan` lists rows on an empty slot, `missile <row>` fires one).

## 6. G: dev test harness (dev builds only)

The game checks need a test harness: `testharness.cpp` (console channel, off unless `mxl-testharness.txt` exists,
compiled out with `-DMXL_RELEASE=ON` through `testharness_release.cpp`) and a subset of `harness_cmds.cpp` (5,583 lines,
mostly Sigma-specific). Verbs mxl2012 needs: `spawn`, `mcast` (monster casts a skill), the player cast verb, `missile <row> dx dy
skill level`, `missilescan`, `warp` / `enter`, `h state`, `object` / `operate` / `objmode`, `wp` bit get/set, `dump ground`.
Rename the trigger file to `mxl2012-testharness.txt`. Copy with cuts, **S-M**. The release DLL never contains it.

## 7. H: Pandemonium 2 waypoint index 17

**Median 2012:** levels.txt gives Pandemonium 2 waypoint number 17, the same as Act 2's Valley of the Kings (and Pandemonium 1
a Vis/Warp to level 17). In 1.13c both levels share the activation bit; the 1.13c panel lists levels from a fixed per-act
table, so Pandemonium 2 is never listed and clicking 17 goes to the Valley.

**D2R today:** waypoint number -> bit through the record bit table `0x2389010` (112 entries, saved in "WS"); level -> number
`0x3d6670`; server use test `0x4b6f10`; the panel (WaypointsPanel) has one tab per actinfo.txt row with nine slots, button
table `0x2a969e0` written by the tab fill `0x1ea9b0`. D2R's level -> number lookup with two levels on one number is the open
point (which level does a click on 17 send? does the "the level you stand in" flag grey out the Valley while in Pande 2?).
Waypoint travel `0x5933f0` picks entry kind 13 only for towns, 46/74 and 133-137, so arriving in Pande 2 (one of 133-136) by
waypoint would find the object.

**Plan:** expected same as 1.13c, so **no part**; game check `pandewp`.

**Result (lane gameplay, 2026-10-28, bug #13):** Pandemonium 2 has **no waypoint object, in 1.13c too**. Its map is the Valley's
centre preset (lvlprest 394 `Act2/Outdoors/KingWarp.ds1`, ds1 header act 2: object 134 = `WaypointDesertValley` 402, four id 94
braziers), and the server's room preset loop hard-codes level 134: it skips object class 402 there and one random 3rd-5th
object (1.14d `0x5559a0`, D2R `0x48f2de`, same code; 133 / 135 skip class 397). So Median's `Waypoint 17` on the row is the
Valley row copied; bit 17 is the Valley's and nothing in Pande 2 sets it. A unique number (40) on the row in game: still no
object. `pandewp` now expects no waypoint object there. Fallback if D2R's panel misbehaves:
`waypoints.cpp` `InstallWaypointPanel` (hook of the tab fill `0x1ea9b0`, three `lea` readers at `0x1ea198` / `0x1ec05a` /
`0x1ec582`, count `0x2a969d4`, generated `mxl_waypoints.h` by tools/waypoints_data.py) with a generated list where number 17
lists only the Valley. Change + generator copy, **M**. `InstallWaypointArrival` (added waypoint levels >= 138)
is not needed: 2012 adds no level.

## 8. Optional parts (owner decides; not in v0.1)

### 8.1 I: stat unassign (PlugY-style)

Laz's `plugy/plugyfixed.ini` forces `ActiveStatsUnassignment=1`, but PlugY is not part of v005. **D2R today:** no per-point
unassign; only Akara's full respec (kept as D2R's, owner 2026-10-28). No existing part does it. Closest piece:
`stat_rules.cpp` `StatClickHook`, a hook on the stat-point packet 0x3a handler `0x4b3c70` (game, player, packet, length;
shift-click count 4 -> 24) and the passive refresh `0x33f830(unit, 1)`. **New** part: a client input hook (Alt+click on a
stat button), a server action that takes one point off the stat (not below the charstats start value) and gives one back to
stat 4 (statpts), sent through a D2RLoader network/packet service or an unused 0x3a count value, then the refresh. Also the
multiplayer/anti-cheat question. **M**. Game check `statunassign`.

### 8.2 J: extra stash pages

PlugY's multi-page stash was a repack extra. **D2R today:** 1 personal stash page + 3 shared tabs. Known design:
(1) shared tabs are **data**: `tools/install_mod.py` writes `d2rcore.stash.add_shared_tabs = N` into
the mod's `d2rloader.toml`, no plugin. (2) One extra **personal** page through D2RLoader's single custom player page
(`InventoryService::registerPlayerPage`, logical id `stash2`, item page 6 + `<char>.d2rl`, max 16 x 16), drawn by the plugin
panel `StashPage2` (`stash_pages.cpp`, generated `mxl_stash_page.h`, layout from `tools/ui_layouts.py`). D2RLoader allows
exactly one such page; ten personal pages are not safely possible. Caveat: a character with items on page 2 refuses to load
without the plugin ("protected page"). For 2012: shared tabs = XS (data); personal page 2 = copy `stash_pages.cpp` with the
grid changed from 14 x 14 to Median 2012's 10 x 10, **M**. Game check `stashpage2`.

## 9. K: D2R additions that conflict with Median (data cannot switch off?)

Lane d2radds owns the data side. This section lists the additions, how each is handled, and whether a hook could be
needed. **Finding: every one can be switched off with data; no hook is needed to disable a D2R system.** The only known hooks
on D2R rules change them to D2Sigma's values (e.g. `quests_rewards.cpp` Rite of Passage `0x550c20`), which is later Median
behaviour and must not come over.

| D2R addition | How it is handled | Data enough? | Plugin fallback | Check |
|---|---|---|---|---|
| Terror zones ("desecrated zones": "Corrupted tremors strike ..." messages, hourly boosted zones, Herald monsters) | `tools/d2r_adds.py`: writes D2R's `data/hd/global/excel/desecratedzones.json` into the mod with every `ladder_enabled` / `non_ladder_enabled` flag false, so no zone is ever active (owner 2026-10-21). No hook | yes (no report of a zone so far) | only if a zone or tremor message still appears: none known; finding the scheduler would be new research (M) | `terrorzones` |
| Herald / desecrate monster flags (monstats columns) | defaults in txt_migrate (Median rows have none) | yes | - | part of `terrorzones` |
| D2R's Pandemonium / uber cube outputs, Sunder charms, D2R 2.4+ vanilla row rebalances, ladder runewords | replace-style merge: Median's tables replace D2R's rows (porting-playbook) | yes | - | tables lane validate |
| RotW content (Warlock, Colossal Summit level 137, RotW items/skills) | rows kept where removing breaks D2R (Warlock column/rows), otherwise unused by Median data | yes; **Warlock stays playable** (owner) | - | - |
| D2R hardcoded rule changes (Rite of Passage 1.4M/20M/40M `0x550c20`, str/dex glitch and other bug fixes) | D2R's kept (a hook for **D2Sigma's** 50,000 rule exists, not used); bug fixes kept | not a conflict for 2012: 1.13c's Rite of Passage is the same capped grant, and Median 2012 does not rely on the 1.13c bugs | none (do **not** copy `quests_rewards.cpp`) | optional `riteofpassage` compare |
| D2R options that only show D2R systems ("Show Terror Zones" etc.) | left alone | n/a (cosmetic, empty with zones off) | - | - |

If lane d2radds finds an addition that no table or json can turn off, it goes into this table with its scheduler/handler
address and becomes a small new part with its own off word; none is known today.

## 10. Game checks (for when game runs start)

Named like the `tools/game_checks.py` checks; run with
`py -3 tools/game_checks.py --slot N all <names>` on slot 2 or 3 under the shared locks. Each FAILs on a new crash file or a
new assert in `d2rloader.log`.

| Check | Item | What it verifies |
|---|---|---|
| `mxl2012` | E, F | console `mxl2012`: version line (dev/release), every v0.1 part "on", no FAILED install, `other plugins: none`. `check_mxl` with mxl2012's line list |
| `rockshock` | A | player casts Rock Shock at a monster; a monster casts ParasiteSkill (`mcast`): two client missiles appear at the target point (clamped to aurarangecalc), the server half damages; `cltdo22` off word as control (no client visual, no crash); no row left on cltdofunc 22 (table read) |
| `srvhit6spawn` | B | fire each hit-6 spawner (`missile <row>`) and two summoning ubers' skills (e.g. edy1summon, darkonesummon): the spawned class is the idmapped sHitPar1 row (never the unmapped number), its mode for sHitPar2 1 and 0, count per hit; no stray monster (the trap of section 3) |
| `srvhit23` | C | bloodspeakerbolt (sHitPar1 119) and leapingjumper (sHitPar1 27) hit: the effect matches 1.13c's hit 23 (named in the static step) |
| `cltdo83` | C | Titan Strike, Innate Titans, Soulshatter, Mana Sweep cast: a client effect is drawn and matches the 1.13c function named in the static step; no assert |
| `skillprog` | C | Batstrike (srvprg 22/119/51, cltprg 25) and Blackstorm (cltprg 28) through their progression stages: charges/progress count up, the finisher fires, client progression visual |
| `cltdostub` | D | `missilescan` lists 0 rows on an empty slot after the stubs; firing the 2 rows with blank pCltDoFunc outside town does not crash; `cltdostub` off word as control is NOT run (it crashes by design) |
| `pandewp` | H | in Pandemonium 2 operate the waypoint: bit 17 set; the panel opens; Valley of the Kings listed once and reachable; standing in the Valley, the bit is shared (Pande 2's activation unlocked it, as 1.13c); no crash. Compare with the 1.13c expectation in section 7 |
| `terrorzones` | K | with the mod's desecratedzones.json, no tremor message and no boosted zone over a forced schedule tick (or a long idle); no Herald spawn |
| `wrongbuild` | E | unit test only (`build_guard_test`): stamp/build combinations, screen text has "3.3" and no build number |
| `statunassign` | I (optional) | Alt+click removes one point, refunds statpts, never below the start value, Grit-like passives refresh |
| `stashpage2` | J (optional) | page 2 opens, items saved and restored across a restart, the protected-page refusal without the plugin |

### 10.1 Game-check spec for v0.1 (lane plugin, 2026-10-28)

The checks below are named checks of `tools/game_checks.py` (lane harness, 2026-10-28: `py -3 tools/game_checks.py all [names]`,
plus `cltnomis` for bug #6 and `classes`; results in docs/testing.md "Harness lane"). All need a **dev** build of mxl2012-core with `mxl2012-testharness.txt` next to
the DLL (the release DLL has no harness). Harness verbs (`h help` lists them; `plugin/src/harness_cmds.cpp`):

| Verb | Side | Does |
|---|---|---|
| `state` | server | player (area, x/y, life, mana, active skills), `client wall calls`, missile stub counters, live / seen missiles, monsters within 40, corpses within 40, objects within 30 (portals with their destination) |
| `units` | server | the unit hash tables per type (players 0x446, monsters 0x4c6, objects 0x546, items 0x5c6, missiles 0x646: game + base * 8) |
| `stat player\|mon:<id> <stat> [layer] [set <v>]` | server | a stat through the game's own calls (the checks fill life / mana / level with it) |
| `level <id> [warp [kind]\|npc]` | server | travel to a level (D2R level id after idmap): the waypoint warp `0x488180` inside the act, the NPC travel `0x4f2e40` across acts; kind 13 = at the waypoint spot |
| `spawn <class> [count [x y]]`, `kill <id>\|nearest [class]` | server | monsters by monstats row |
| `setskill <id> <lvl>`, `skill [left\|right <id>]`, `cast <id> [x y\|unit <id>\|nearest [class]\|self]` | server | player skills through the game's own skill-point and cast calls |
| `mcast <skill> <mode> unit <id>\|nearest [class]` | server | a monster uses one of its monstats skills (mode 6 A1, 7 A2, 9 SC, 10 S1) |
| `missile <row> [dx dy [skill lvl [where]]]` | server | one missile of a missiles.txt row from the player; prints its pCltDoFunc / pCltHitFunc / pSrvHitFunc and the new unit (`where`: which hash table holds it) |
| `missiles [reset]` | server | live missiles; after `reset` every missile class seen per server frame |
| `missilescan` | server | rows that point at an empty missile client do / client hit / server hit slot (client hit and server hit 0 = no function; 0 everywhere with the stubs except bug #14) |
| `cltdo <skill> [lvl] [orig]`, `cltst <skill> [orig]` | client | calls the skill's client do / client start function as the client dispatcher does; prints slot, entry (exe+RVA or plugin); `orig` calls D2R's curse / start 18 past the `cltnomis` wrappers (bug #6 control) |
| `slot <cltdo\|srvdo\|mcltdo\|mclthit\|srvhit> [index]` | client | a function-table entry as exe+RVA (the static step of section 4), or the bound and the empty slots |
| `waypoint n <number> [get\|set\|clear]`, `waypoint open` | server | a waypoint bit by levels.txt number; the panel |
| `objects [class]`, `object <class> [dx dy]`, `operate <id> <fn>`, `objmode <id> <mode>`, `enter nearest\|<id>` | server | objects, operate functions, portals |
| `dump mon <class>` | server | the first 0x40 bytes of a monstats record |
| `watch cltdo\|srvhit <index>`, `watch`, `watch off` | client / server | wraps one skill client do or missile server hit table entry (only these two: same three-argument shape) and counts calls, non-zero returns and the last skill id (cltdo) or missile class (srvhit); the real path's proof that a slot runs (lane triage) |

Every check FAILs on a new crash file, a new assert in `d2rloader.log`, an `h: ... FAIL crashed` line, or a
`mxl2012-core: ... FAILED` log line. Row and level numbers below are Median 2012's; use the ids **after** tools/idmap.py
(its report) where they differ.

| Check | Steps | PASS when |
|---|---|---|
| `mxl2012` | console `mxl2012` | line 1 `mxl2012-core 0.1.0 (dev) \| game: Diablo II: Resurrected 3.3, engine changes on`; `pluginguard ok: no conflicting plugin in the game`; `cltdo22 cltdofunc 113 client wall ...` without FAILED; `cltdostub empty slots skipped: missile client do 14 of 91, server hit 10 of 71` (D2R's own empties; other numbers = another table state, investigate); `other plugins: none`; no line shows `0x6ab3782c` or `93847` (those are in the log line `mxl2012-core: D2R ... image ...`) |
| `rockshock` | `h slot cltdo 22`, `h slot cltdo 113` (113 = plugin); outside town `h spawn <class>` a monster; `h setskill 28 1` (Rock Shock has no charclass: if the game refuses the point, skip to `cltdo`), `h missiles reset`, `h cast 28 nearest`, `h missiles`, `h state`; `h cltdo 28` and `h cltdo 408`; a monster owning ParasiteSkill (408, from monstats Skill1-8): `h mcast 408 <its mode> nearest` | `cltdo 28` / `cltdo 408`: `cltdofunc=113 ... entry=plugin`, `wall calls +1`; `state` client wall calls > 0 after the cast; the server half damages (monster life drops); missiles seen include `rockshock` / `purgestrike`; no row on cltdofunc 22 (tables lane validate). Then the two controls of section 2.1 (blank cltdofunc; `cltdo22` off word last) with screenshots of the three visuals for the owner |
| `srvhit6spawn` | outside town: `h missile 1330` (treewardenspawner), `h missile 1610` (edy1summon), `h missile 1613` (darkonesummon), `h missile 1301` (demon seed on ground, sHitPar2 0) one at a time, each followed by `h state` | a new monster of class = the **idmapped** sHitPar1 (1107 / 1222 / 1221 / 1 -> their D2R rows) near the impact; `dump mon <class>` is a real row; no monster of the unmapped number; one spawn per hit; mode for sHitPar2 1 vs 0 noted |
| `srvhit23` | lane triage version: `h slot srvhit 23`; a spear (`137`) with Bloodspeakers Mark (658) as oskill; per way (left clicks, right clicks, `cast 658 unit`) a fresh zombie, `h watch srvhit 23`, 3 uses; then `h missile <leapingjumper> 6 0` under the watch | the slot is `exe+0x4533c0`, it is reached with last missile bloodspeakerbolt, bloodspeakerpets appear (one per hit: no petmax in srvdo 119), no new assert (#270 is tagged known) |
| `cltdo83` | lane triage version: `h slot cltdo 83`, `h cltdo 8/18/546`; the dagger (`142`); Titan Strike, Soulshatter, Mana Sweep learnt with `setskill` where the game gives the point (else oskill), per way a fresh zombie, `h watch cltdo 83`, 3 uses; controls on `watch cltdo 19` (Aerials Disaster learnt, Bloodspeakers Mark oskill) | the slot is `exe+0x2b25e0`, Titan Strike reaches it and makes no missile; PASS also needs a cltmissile skill's missiles (PARTIAL without: Soulshatter needs its own pet, Mana Sweep a sorceress) |
| `frenzy` | lane triage: the dagger's Feral Strike by left clicks on a zombie; a Thorn Hulk's MonFrenzy (215) and a Blood Lord's BloodLordFrenzy (268) at the player (`mcast`, mode from monstats Sk<n>mode), 3 each | the zombie's life drops, the casts are taken, no new town portal (D2R's 109 is "Townportal O Skill"), no assert |
| `skillprog` | assassin character: `h setskill 326 1`, `h cast 326 nearest` x4 (Batstrike: srvprg 22/119/51, cltprg 25) with `h state` between; paladin: `h setskill 442 1`, `h cast 442 nearest` x4 (Blackstorm: cltprg 28) | charges count up per hit, the finisher fires on the last stage (`missiles` shows its missile), no assert |
| `cltdostub` | `h missilescan`; outside town `h missile 83` (stuckarrow) and `h missile 84` (footprint), wait 3 s, `h state` | `missilescan`: 0 rows on an empty client do / client hit / server hit slot; no crash; `state` stub counters show the client do stub ran (`client do` >= 1) and the log has `missile row 83 has client do slot 0 ... skipped`. The `cltdostub` off word control is NOT run (it crashes by design) |
| `pandewp` | reach Pandemonium 2 (level 134 in 2012 numbering: `h level <id>` or the uber portals with `enter`), `h objects` (the waypoint object), `h operate <id> <its OperateFn>`, `h waypoint n 17 get`, `h waypoint open`; `h level 46` (Valley of the Kings), `h waypoint n 17 get` | bit 17 set by Pandemonium 2's waypoint; the panel opens; the Valley is listed once and reachable; standing in the Valley the bit is the same one (1.13c behaviour); no crash |
| `terrorzones` | the mod's desecratedzones.json installed (lane d2radds); idle 10 min in a field level with `h state` every minute; scan the game log and chat capture | no terror-zone / tremor message, no boosted zone, no monster with a Herald / desecrated flag. No harness verb reads the zone scheduler (its address is not known): this check is data + observation only |
| `wrongbuild` | unit test `buildguard_tests` (plugin/tests) | passes: screen text "needs Diablo II: Resurrected 3.3", no 5-digit run, no image stamp; the log line carries both |

## 11. Parts NOT to bring over (later Median / D2Sigma)

Everything below is D2Sigma behaviour or later Median content that Median 2012 (pure 1.13c data) does not have. Copying any of
it would change 2012's rules or write slots 2012's data never uses.

- **Skills:** `sigma_skills.cpp` (all srvdofunc 172-190, the 41/73 wrappers, client 110-112, curse / start-18 / area-aura
  wrappers; keep only `CltDoWall`), `skill_starts.cpp` (srvstfunc 71/72), `calc_codes.cpp` (calc codes 73-110: 2012 uses D2R's
  first 73 only), `auras.cpp`, `area_damage.cpp`, `teleport.cpp`, `pet_scaling.cpp`, `stat_list.cpp`, `mana_costs.cpp`,
  `cooldowns.cpp`, `skill_restrict.cpp`, `skill_damage.cpp`, `heat.cpp`, `whirlwind.cpp`, `skill_tree.cpp` (8 tabs),
  `collide_types.cpp` (types 9/10), `mxl_skill_flags.h`, `mxl_cooldowns.h`.
- **Missiles:** `missile_hits.cpp` server hits 61-69, client hits 6/7, phalanx (srvdo 46 / cltdo 14), revive wrap (keep only
  the empty-slot stubs; `HitSpawnCorpse` only as the section 3 fallback).
- **Items / cube:** `item_spells.cpp`, `item_rules.cpp`, `item_gen.cpp`, `items_ext.cpp` (runeword properties 8-13 and the
  jewel-padding matcher: 2012 pads explicitly in runes.txt, engine-triage #16), `item_events.cpp`, `item_type_ids.cpp`,
  `item_text.cpp`, `tooltip_probe.cpp`, `properties_ext.cpp`, `cube_conditions.cpp` (ops 29-42), `craft_flags.cpp`,
  `unique_limits.cpp`, `unique_carry.cpp`, `gamble.cpp`, `vendor_stock.cpp`, all `mxl_items.h` / `mxl_runewords.h` /
  `mxl_cube*.h` / `mxl_unique_limits.h` tables.
- **World / monsters / quests:** `quests_act1.cpp`, `quests_act2_5.cpp` (incl. the respec bookkeeping hook: Akara stays D2R's),
  `quests_rewards.cpp` (Rite of Passage 50,000), `requirements.cpp`, `requirement_gates.cpp`, `dungeon_lockout.cpp`,
  `goblins.cpp`, `monster_ai.cpp` (andariel_ai 155), `monster_looks.cpp`, `monster_rules.cpp`, `level_types.cpp`,
  `waypoints.cpp` (except as the section 7 fallback), `travel.cpp` (wp auto-activation, map reveal, hotkeys: Median 2.x
  conveniences), `town_rules.cpp`, `no_corpse.cpp`, `death_event.cpp`, `hardcore_death.cpp`, `trophy_timer.cpp`,
  `engine_gaps.cpp` (later Median's hit-20 floor, recast guard, slow floor), `combat.cpp` (D2Sigma caps), `stat_rules.cpp`,
  `stat_columns.cpp`, `game_end.cpp`, `map_memory.cpp`, `npc_actions.cpp`, `npc_services.cpp`, `hirelings.cpp`,
  `required_level.cpp`, `translation_guard.cpp`.
- **UI:** `buff_icons.cpp`, `info_panels.cpp`, `client_messages.cpp`, `stash_pages.cpp` (only if the owner wants J),
  `strings.cpp` / `strings_probe.cpp` (run-time `medianxl:` lookups for text the plugin draws; mxl2012-core draws no Median
  text in v0.1, and the `mxl2012` string namespace is data, docs/strings.md).
- **Diagnostics tied to the above:** `states_fix.cpp` (off by default; D2RLoader 1.3.1's wide states),
  `state_trace.cpp`, `sound_guard.cpp` (fix for a later Median goblin sound; copy later only if 2012 data shows a -1 sound),
  the 5,000 lines of Sigma verbs in `harness_cmds.cpp`.

Generic parts that **do** come over: `build_guard*`, `env_guard_logic.h` (wrong mod folder / stray DLL warning;
optional XS), `other_plugins_logic.h`, the entry/off-list/console skeleton, a trimmed `d2r.h` / `d2r.cpp`,
`CltDoWall`, the missile empty-slot stubs, `testharness.cpp` + a trimmed harness (dev only), `CMakeLists.txt` with
`MXL_RELEASE`, the version resource, and the unit tests of these (`build_guard_test`, `other_plugins_test`, `env_guard_test`,
`harness_cmds_test` trimmed).

Watch-list (copy only if the first game runs show the symptom; each is XS, as-is): `sigma_skills.cpp` `CltDoCurse` (curse rows
without cltmissilea assert in D2R's client curse `0x2b05d0`), `CltStMissileC` (client start 18 asserts without cltmissilec,
`0x2b0df0`), `AreaAuraHook` (`0x4327d0` asserts "nRadius > 0" for auras with a blank aurarangecalc). These are D2R asserts on
vanilla-style data, not D2Sigma rules, so Median 2012 rows may hit them too; validate.py's assert rules (engine-triage #29)
should fix most of them in data first. Lane harness (2026-10-28): the first two showed (bug #6, SkillsNec.cpp:60 / :30) and are
copied as part `cltnomis` (section 13). Lane monitems (2026-10-28): "nRadius > 0" showed too (bug #31, Belial's monprop aura 281 Laz Resist Aura, srvdofunc 65, blank aurarangecalc), so `AreaAuraHook` is copied into part `cltnomis` as well (client_skills.cpp; a radius below 1 skips D2R's applier, which does nothing for it).

## 12. Order of work

1. Skeleton lane: entry, off list, `mxl2012` console, build guard with the "3.3" text, other-plugin guard (E, F).
2. v0.1 parts: `CltDoWall` at 113 + data remap (A), empty-slot stubs (D), dev harness subset (G).
3. Static step for C (name the D2R and 1.13c functions per slot).
4. First game pass: `mxl2012 rockshock srvhit6spawn srvhit23 cltdo83 skillprog cltdostub pandewp terrorzones`.
5. Per failure: B fallback (`HitSpawnCorpse`, S), C ports (M each), H fallback (M), K hooks (none known).
6. Owner answers on I and J (OWNER-QUESTIONS.md #7).

## 13. v0.1 as built (lane plugin, 2026-10-28)

PluginVersion 0.1.0. Build: `cmake -S plugin -B build/plugin -A x64 -DMXL2012_PLUGINSDK_DIR=<PluginSDK checkout>` then
`cmake --build build/plugin --config Release` (+ `--target tests`); `-DMXL_RELEASE=ON` for the player DLL. No game run yet.

| Item | File(s) | Off word | Notes |
|---|---|---|---|
| E build guard | `build_guard_logic.h` (`Message`, `LogDetail`), `mxl2012_core.cpp` | - | screen / `mxl2012`: "needs Diablo II: Resurrected 3.3"; image stamp and build name only in log lines (`wrong game: image ...`, and `mxl2012-core: D2R ... image ...` each time `mxl2012` runs) |
| F plugin guard | `other_plugins_logic.h` (`IsConflictingPlugin`, `ConflictNotice`), `mxl2012_core.cpp` `FindConflictingPlugin` | `pluginguard` | refuses (installs nothing, keeps `mxl2012`) when a loaded module has the PluginInfo id or file name of a conflicting plugin, or that DLL waits in `<game>\d2rloader\plugins` (loads after the mod's plugins) or next to our DLL. A conflicting plugin that appears later under another file name is only reported (error log + notice) by the 15 s check: the parts are in by then |
| A client do 113 | `client_skills.cpp`, `client_skills_logic.h` | `cltdo22` | written only if slot 113 is below the bound and empty; see 2.1 for the open question |
| D empty slot stubs | `missile_stubs.cpp`, `missile_stubs_logic.h` | `cltdostub` | missile client do (bound 91) and server hit (bound 71); installed after A |
| + client no-missile wrappers | `client_skills.cpp` `CltDoCurse` / `CltStMissileC`, `client_skills_logic.h` (`HasClientMissile`) | `cltnomis` | D2R's client curse (cltdofunc 30, `0x2b05d0`) and client start 18 (`0x2b0df0`) wrapped in place: a row without a client missile skips them instead of asserting (bug #6; the section 11 watch-list part, lane harness) |
| + item-event skill guard | `item_effect.cpp`, `item_effect_logic.h` (`SkipsEventSkill`) | `itemeffect` | D2R's item-event skill resolver `0x589930` (D2Game SkillItemEffect.cpp:136; callers `0x5896e0` chance-to-cast, `0x589820`, `0x56b020`) answers 0 for a skill whose row has no ItemEffect instead of logging `BC_ASSERT: ptSkill->nItemEffect != 0` and then returning 0 itself: 1.13c ran nothing there either, the tooltip lines of Median's properties stay (bug #40, lane fixes2). `mxl2012` / `h state` print the calls answered and the last skill |
| + skill-remove guard | `skill_remove.cpp`, `skill_remove_logic.h` (`SkipsRemove`) | `skillremove` | D2R's skill remove `0x3402d0` (D2Common Skills.cpp:904; reached from set-skill-level `0x33efb0` with level 0) returns at once when the unit has no skill list (unit `+0x100`) or no first skill, instead of asserting `ptSkill` and then removing nothing: the level-0 `sumskill`s that summon do 119 gives the pets of Batstrike, Summon Rampagor and Summon Lamia when the caster lacks those skills (pets that own no skill; bug #15, lane states). 1.13c removed nothing either. Inline hook of the 17 entry bytes; `mxl2012` / `h state` print the calls answered and the last skill |
| + dodge list guard | `dodge_list.cpp`, `dodge_list_logic.h` (`JumpBytes`) | `dodgelist` | D2R's damage code (SUnitDmg.cpp, `0x44ad9a`) reads the defender's dodge / avoid / evade state list (65 / 66 / 68, `0x2f5940` at `0x44b148`) for its passive skill; Median gives those chances as plain stats (338-340), so the list is missing and D2R logs `hList`, then leaves at `0x44b27d`. The assert block at `0x44b152` becomes `jmp 0x44b27d` (5 bytes; the 14 block bytes are compared first): the same exit without the log line (bug #53, lane states) |
| + blaze / spider-lay list guard | `state_lists.cpp`, `state_lists_logic.h` (`Blocks`, `JumpBytes`) | `statelist` | D2R's client and server functions of states 13 (blaze: `0x21edc0`, `0x551450`) and 22 (spiderlay: `0x221650`, `0x578680`) read the skill, level and missile from the state's list (stat 350 / 351) and assert when one is out of range; Median keeps shellshock / raptured on those ids as 1.13c did (lane statefaith) and their lists name no skill. 1.14d's functions take the same exits silently. The first instruction of each of the 12 range asserts (3 per function; the null-unit assert stays) becomes a `jmp` to the instruction after its `int3` (each whole block compared first): D2R's flow without the log lines (bugs #50 #52) |
| + state-22 melt trail | `melt_trail.cpp`, `melt_trail_logic.h` (`FixedTrail`, `StepDirection`, `SpotFrom`) | `melttrail` | Inline hooks at the entry of D2R's state-22 functions (client `0x221650`, 15 bytes; server `0x578680`, 16 bytes). When the state's list names no skill (stat 350 <= 0 or past skills.txt: Median's `raptured`, Rapture / NTRAP), the hook makes what 1.14d's `Game.exe` makes for every state-22 unit (client `0x4e2d40`, server `0x5ce4f0`, called from the walk-mode steps `0x4807c0` / `0x5a8490` as D2R's from `0xf9aba` / `0x445d20`): missile 143 at the unit's position + one step (step table `0a 08 16 14 12 10 0e 0c` by the path direction index, `0x341930` -> `0x3aeb30` -> `0x3aeb40`), target + two more steps, velocity 3, level = the unit's skill 173 (`0x33dd40(unit, 173, 0)` = 1.14d `0x643810`, then `0x33d1e0(unit, skill, 1, 0)` = 1.14d `0x6442a0`; 0 without the skill). Client: flags 0x25, skill 0 (1.14d sets none), no missile in a room `0x2f0750` refuses (1.14d `0x61ab00`), D2R's list seed (stat 202, made by `0x8d5d0` and stored when 0), `0x1b7760`, then sound 0x726 (`0x1a0780`). Server: flags 0x21, skill 173, stat 202 of the list as seed, `0x5371a0`. A list with a skill runs D2R's function (trampoline). `mxl2012` prints the trails made (client, server). Bug #52, lane melttrail; game check `melttrail` |
| + D2R-only asserts | `orig_asserts.cpp`, `orig_asserts_logic.h` (`Blocks`, `JumpBytes`, `ContinueOf`) | `animseq`, `monequip`, `aurastate` | Three asserts D2R logs where 1.14d (`Game.exe`, read statically) takes the same path without a word; each block's `lea` becomes a jump to where D2R's own `je` goes after it (bytes compared first). `animseq` (#74, Median's `TH` skill modes of haunt_vasily / haunt_amazon): D2Common's set-sequence `0x34d900` (1.14d `0x621260`) with no sequence record, `ptUnit->hAnimSequence` (Units.cpp:2835), `0x34d935 -> 0x34d948`; `monequip` (#74, flyingscimitar's monequip row with loc1 `6`): the monster equipment code `0x56d200` (1.14d `0x5d6b60`) with no valid location, `count > 0` (SkillAss.cpp:2364), `0x56d38b -> 0x56d47d` (next row); `aurastate` (#181, Mon Pain Spirit): srvdofunc 18 `0x553e60` (1.14d `0x5c9480`) with a blank aurastate, SkillSor.cpp:424, `0x553ef4 -> 0x553f0e` (its own return-0 test). `mxl2012` prints one line per word (lane fixes4) |
| ~~+ carry1 per unique~~ | removed by lane pluginplan2 | ~~`uniquecarry`~~ | Now data: `tools/txt_migrate.py` `carry_numbers` writes the same numbers (record index + 1) into the built uniqueitems.txt, `validate.py` rule `carry_numbers` (section 14.5) |
| + Whirlwind hit rate | `whirlwind.cpp`, `whirlwind_logic.h` (`ClassicDelay`, `D2RSpeed`, `ClassicSpeed`, `HitDelay`) | `whirlwind` | Inline hook of `0x56ac00` (19 entry bytes; only Whirlwind's do function `0x568f40` calls it): D2R 2.4's frames rescaled to 1.13c's speed (100 + stat 68 + IAS, no diminishing returns) and put through 1.13c's table, a hit every 4-16 frames (no weapon 10). Median's srvdofunc 76 rows: Whirlwind, Spin To Win, Danse Macabre, Harvest (bug #281, section 14). `mxl2012` prints the delays answered and the last one; the first six go to the log with stat 68 / IAS / both speeds |
| + second `useitem` cube output | `cube_dupe.cpp`, `cube_dupe_logic.h` (`ExtraCopies`, `Pages`) | `cubedupe` | Inline hook of the recipe executor `0x5269c0` (21 entry bytes; post-hook). When the original returns its first output and the record (slot `i` at `+0x5a + 0x5b*i`, special byte `+0x0d`) has `useitem` (0xfe) in slot 0 and in a later slot, each later `useitem` slot gets a copy of the returned item made by D2R's item duplicate `0x43d660(game, item)` (1.14d `0x55a2a0`: serialise / read back, flags 0x80000 on and 0x2000 off on the copy, 0x8000000 on the source, which the hook clears again when it was clear), placed in the cube (else the backpack) as the executor places its outputs: `0x34a410` / `0x3865b0` / `0x382e10` / `0x471500`, identified flag `0x10`, item packet `0x535f60(game, player, item, 0, 2, loc)`. No room: the copy is freed and counted. `mxl2012` prints copies made / no room / refused. Bug #350, lane cube2; check `cubeclasses` row 8397 |
| + item level above 99 | `item_level.cpp`, `item_level_logic.h` (`PatchBytes`, `Written`, `Read`) | `ilvl` | D2Common's item serializer `0x37d140` clamps the item level to 99 before its 7-bit write; both immediates of the clamp at `0x37d744` become 0x7f (the whole clamp and the 7-bit write compared first), so 100-127 are kept and nothing above 127 is ever written (bug #251, lane ilvl, section 18) |
| + rune letters of Median's Great Runes | `rune_letters.cpp`, `rune_letters_logic.h` (`IsD2RLetterKey`, `UseCell`, `CopyCell`) | `runeletter` | The runeword tooltip looks each rune's gems `letter` cell up as a D2R key (`0x2c29da`, thunk `0x3e2b736`); D2R's own fallback to the cell (`0x2c29fa`, a pointer compare with the lookup of `strMissingString`) never fires under D2RLoader. The thunk's import slot `0x3e2ae18` is replaced (`PatchWriteU64`) by a pass-through that, only for the call returning to `0x2c29df`, answers a cell that is not `r01L`..`r33L` or has no text with the cell itself, as 1.14d. `mxl2012` prints the letters drawn from the cell / D2R keys kept. Bug #334, lane runeletters, section 19; check `runeletters` |
| + skill tooltip labels | `skill_text.cpp`, `skill_text_logic.h` (`Labels`, `ConversionLength`, `KeptPart`, `CutLabel`) | `skilltext` | D2R's skill tooltip line renderer `0x287a50` still appends 1.13c's hard-coded labels (types 9, 10, 11, 14, 22, 25, 27, 28), but D2R rewrote their texts as printf formats (`StrSkill5` "Fire Damage: %d-%d"). Inline hook of `0x287a50` (19 entry bytes; post-hook): in the text the call appended, each raw label (read through the string thunk `0x3e2b730`, so any language matches) is cut to the words before its first conversion, `StrSkill34` to the words after its last (1.13c's " per second"). `mxl2012` prints the labels cut. Bug #396, lane skilltips, section 21 |
| + sound guard | `sound_guard.cpp`, `sound_guard_logic.h` (`Skips`, `CheckTable`, row counts) | `soundguard` | docs/crash-audit.md C17. Inline hooks at the entry of the client unit sound wrapper `0x107dd0` (15 bytes; an id outside the table returns null) and of the five sound record readers `0xd8c70` (+0xc7), `0xd9180` (+0xb0), `0xd9030` (path), `0xd9e60` / `0xda360` (variant pick), which check the id against the row count (`0x3b20c0`) but go on with a null record; a skipped id gets the empty-table answer (0, an empty path, the id). After each table load (D2RLoader's DataTablesLoaded listener) the loaded row count is compared with ours: below it (D2RLoader's table-cache start, D2R's own 11913 rows) a log warning and the screen notice "Close the game and start it again". Ours: `ModSoundRows` 12119 (expansion bank), `ModSoundRowsBase` 12101 (base/); the check takes the smaller. `tools/tests/test_sound_rows.py` compares them to the built tables (skipped without a build). `mxl2012` prints rows and skipped ids. Dev switch `MXL_SOUNDGUARD_TEST=1/2` (Neutral id -1). Not yet game-checked |
| + spirit summon sound | `sound_guard.cpp` (`InstallSpiritSound`), `sound_guard_logic.h` (`SkipsSpiritDeath`, `AncientDeathHd`, `SpiritFirst` / `SpiritLast`) | `spiritsound` | Bug #502. The Barbarian's spirit summons (Guardian / Defender / Protector Spirit, skills 433-435, monsters 1085-1087) are drawn in HD with D2R's Ancients (`monsters.json`: `ancientbarb2` / `ancientbarb1` / `ancientbarb3`); the Ancients' HD death timeline plays `ancient_death_hd` (sounds.txt `*Index` 6754) through the client play `0x1a0780` (sound id, unit, ...; 13 entry bytes) each time a spirit dies or is cast again. An inline hook at `0x1a0780` returns 0 (nothing played) for that id when the unit is a monster (type 1) of class 1085-1087; everything else goes on to D2R. The real Ancients and the quest NPCs on the same units keep the sound. Legacy never played it (only the monsounds death sound `barbarian_death_1`, Median's). `tools/tests/test_sound_rows.py` checks the id and the classes against the built tables. `mxl2012` prints the skipped plays. With `MXL_SOUND_TRACE=<file>` (dev builds) the guard's hooks and this one count every sound id they see into the file (lane sound) |
| + translation guard | `translation_guard.cpp`, `translation_guard_logic.h` (`EventSound`, `InRegion`, `ReadableProtect`) | `transguard` | docs/crash-audit.md C14 (`D2R.exe+0x7761DC` at a character switch after a Druid morph). Inline hook at the entry of the UnitTranslationLayer event type 0x10 handler `0x775fc0` (16 bytes): `*event`, `[*event+0x70]` and its `+0x870` byte must be readable (`VirtualQuery`: committed, no `PAGE_NOACCESS` / `PAGE_GUARD`, inside the region), else the event is skipped, counted and logged (first 8, with the payload words). `mxl2012` prints events seen / skipped; `TranslationGuardProbe` is there for a harness verb (not wired). Not yet game-checked |
| + Baal laugh chat line | `vo_chat.cpp`, `vo_chat_logic.h` (`PathKeyIs`, `LineAllowed`) | `vochat` | Bug #508, section 27. Inline hook at the entry of D2R's voice subtitle `0x1a0da0` (19 bytes): the "Baal says: ..." line of the voice file `baallaugh1` is left out when the last one was printed less than 30 s ago; the sound is not touched |
| G harness (dev) | `harness_cmds.cpp`, `harness_cmds_logic.h` (`ParseSlotTable`, `WatchableTable`), `testharness.cpp` | - | verbs of 10.1 (lane triage: `watch`, a counting wrapper on one cltdo / srvhit entry, written and restored with `PatchWriteU64` and its expected old value); the harness itself hooks the server frame `0x406550` |
| `d2r.h` | trimmed to the v0.1 calls and the five function tables | - | summon / pet / melee / seed helpers of the skeleton removed |

Off words now take letters **and digits** (`cltdo22`); the skeleton's reader kept letters only. Unit tests: `buildguard_tests`
(= check `wrongbuild`), `otherplugins_tests` (plugin guard), `clientskills_tests`, `missilestubs_tests`, `envguard_tests`,
`harness_tests` (`ParseSlotTable` added; lane triage: `WatchableTable`; lane harness: `CallsEmptySlot`, `UseNpcTravel`), `clientskills_tests` (`HasClientMissile`), `itemeffect_tests` (`SkipsEventSkill`, lane fixes2), `skillremove_tests` (`SkipsRemove`, lane states), `dodgelist_tests` (patch bytes, lane states), `statelists_tests` (12 blocks, lane statefaith), `melttrail_tests` (ids, decision, step table, spot, entry bytes; lane melttrail), `cubedupe_tests` (slot layout, `ExtraCopies`, pages; lane cube2). `uniquecarry_tests` (row + 1, rewrite pass, D2R's comparison before / after),
`whirlwind_tests` (1.13c table edges, both speed terms, the whole rule; lane pluginplan), `origasserts_tests` (3 blocks: shape, reporter, where D2R goes on; lane fixes4), `runeletters_tests` (call site bytes, both thunk calls, key test, fallback rule, cell copy; lane runeletters), `itemlevel_tests` (patch bytes, the clamp before / after, write and read back 1-127; lane ilvl), `soundguard_tests`, `transguard_tests` (crash-audit C17 / C14 guards; lane realpath), `skilltext_tests` (conversions, the cut before / after, every occurrence, a formatted line left alone; lane skilltips).

## 14. Phase 4: open plugin items and D2R-side parts (lane pluginplan, 2026-10-28)

Static reading only, no game run (the slots were busy). Scope: plugin items of this file and of [unported.md](unported.md) that do
**not** wait for a game verdict of lane triage, plus existing parts that fix D2R-side problems any 1.13c-data mod meets (lane
realpath audits the crash guards; this lane covers the non-crash rules).

### 14.1 Built

| Part (off word) | Why Median XL 2012 needs it | Evidence | Game check |
|---|---|---|---|
| ~~`uniquecarry`~~ (bug #280; data since lane pluginplan2, section 14.5) | D2R's carry1 is a number compared between records; Median's 45 carry1 uniques all have 1, so one relic / quest charm blocked every other one. 1.13c refuses only a second copy of the same unique | Median 2012 `uniqueitems.txt` (pure v005 and the integ build: 45 rows, all `1`; D2R's own: 1001 / 1002 / 1003); D2R's placement test `0x473960` (loader type 2 at +0x30) | `uniquecarry` |
| `whirlwind` (bug #281) | D2R 2.4 reworked the hit rate of srvdofunc 76; Median 2012 has four skills on 1.13c's function 76 | Median 2012 `skills.txt` srvdofunc 76: Whirlwind, Spin To Win, Danse Macabre, Harvest; D2R `0x568f40` / `0x56ac00`, 1.13c D2Game `0x6fce1470`, D2Common 10564 | `whirlwind` |

### 14.2 Existing parts looked at and not ported

| Part (off word) | Decision | Reason |
|---|---|---|
| `item_type_ids.cpp` (`typeids`) | not ported | Its start-up check compares D2R's 25 fixed type immediates with a header generated from the built itemtypes.txt. Here `idmap.align_item_types` puts every D2R type at D2R's number and `idmap.check_built` fails the build on a mismatch (integ build: jewl 58, warl 67, h2h 68, pelt 73, rune 75, hpot 77, apot 81, wpot 82, scha 83, mcha 84, gem4 96), and the build guard pins the image, so the plugin check would compare constants with constants. The type-id bugs it guards against are covered by data |
| `sound_guard.cpp` (`soundguard`), `translation_guard.cpp` (`transguard`) | lane realpath | Crash guards, ported by lane realpath on its branch; not touched here, to keep the file names apart |
| `unique_limits.cpp` (`uniquelimits`) | not needed | Later Median's `uniqueitems2` (LimitGroup / LimitCount / PickDuplicates, D2Sigma's D2Units check). Median 2012 has no such table; its only carry rule is 1.13c's carry1, which `uniquecarry` restores |
| `whirlwind.cpp` `InstallWhirlwindProcs` (`wwproc`) | not ported | Chance to cast on striking during a spin was a Median 2.x fix of a Diablo II bug; 1.13c (so Median 2012) refuses it as D2R does (state 54 held for the spin) |
| `level_types.cpp`, `map_memory.cpp`, `waypoints.cpp` | not needed | Median 2012 has vanilla's level types (lvltypes.txt: 36 and the Expansion row), levels Layer <= 99, no waypoint number above 38 |
| `items_ext.cpp` (`runewords`) | not needed | 1.13c's runes.txt has 7 property slots, as D2R's record; single-rune padding is explicit (engine-triage #16) |
| `required_level.cpp`, `item_rules.cpp`, `stat_rules.cpp`, `gamble.cpp`, `combat.cpp`, `engine_gaps.cpp`, `town_rules.cpp`, `hardcore_death.cpp`, `travel.cpp` | not ported | D2Sigma / Median 2.x rule changes (section 11), not 1.13c behaviour |

### 14.3 Open plugin items of this plan, unchanged

- I (stat unassign) and J (personal stash page 2): the owner decisions of 2026-10-28 ("QoL: only what D2R itself has, no PlugY
  rebuilds"; "D2R's shared stash as D2R has it", per panel the larger grid) answer both: not built.
- B, C, H, K: game checks; the static steps found the same functions in D2R and 1.14d (DECISIONS.md: srvhit23 / cltdo83 need no
  part, the Pandemonium 2 waypoint is engine behaviour). Nothing to build before a check fails.
- Client start 82 (Baal Corpse Explode, approx) and missile client hit 11 (dropped): no 1.13c function body to port (no D2Client
  decompile; 1.14d has no function for hit 11). Left as unported.md says.
- Warlock demons' pack size / monster level: later, owner call after a playtest.

### 14.4 Checks run (lane pluginplan2, see 14.5)

`py -3 tools/game_checks.py --slot N all mxl2012 uniquecarry whirlwind`, the controls and the B / C / H / K checks ran on slots 1 and 3;
results in section 14.5 and docs/testing.md "Lane pluginplan2".

### 14.5 Round 2 (lane pluginplan2, 2026-10-28): game checks, `uniquecarry` moved into the build

#### 14.5.1 `uniquecarry`: data instead of a plugin part

The round-1 part worked in game (`mxl2012`: `table loads 1, carry1 uniques 90, rewritten 90`: 45 records in each of the two table banks; the
check's expected `45` was wrong, and its row list read the built `*ID` column, which is blank in uniqueitems.txt, so it found no rows). The
same numbers are now written by the build:

- **Why data is the simpler, more robust choice.** D2R's loader reads `carry1` as an int (`0x31f1d0`, type 2, record +0x30) and its own rows
  carry 1001 / 1002 / 1003, so a distinct number per row is the column used as D2R means it. The part needed four image-specific facts
  (table block call `0x300a90`, offsets +0x13c8 / +0x13d0, record size 0x15c, field +0x30), wrote into D2R's loaded records after every table
  load and had to find the two banks' arrays itself; the data fix needs none of that, is visible in the built table, is checked by
  `validate.py` (rule `carry_numbers`: two carry1 rows with one number = error) and is unit tested (`tools/tests/test_txt_migrate_unique.py`).
- **Behaviour identical to 1.13c, and to the part.** Same numbers (record index + 1, the record the placement test reads), so the same
  comparison: a second copy of one unique is refused, two different carry1 uniques are carried together. Nothing else in D2R reads the
  number (the placement test `0x473960` and the record comparison it shares with `0x5269c0`).
- Removed: `unique_carry.cpp` / `.h` / `_logic.h`, `uniquecarry_tests`, the `uniquecarry` status line and off word. Game check `uniquecarry`
  now checks the built numbers, then placement, second copy and a real ground pickup (it clicks the item's own spot).

#### 14.5.2 Verdicts of B, C, H, K (this round plus lane triage's runs of the same day)

| Item | Check(s) | Verdict | Part needed |
|---|---|---|---|
| B hit 6 spawners | `srvhit6spawn` PASS (slot 1): 1388 / 1668 / 1671 spawn the idmapped classes 1195 / 822 / 1296 alive, one per hit; 1359 (sHitPar2 0) one corpse of class 1, as Median (bug #11) | D2R's hit 6 is 1.13c's | none |
| C srvhit 23 | `srvhit23` PASS (slot 3, with lane triage's `watch`): Bloodspeakers Mark by left / right clicks and server casts, hit 23 `exe+0x4533c0` runs 1 / 3 / 3 times, 7-8 bloodspeakerpets; leapingjumper 1 call; known assert #270 | same function as 1.14d (section 4.1) | none |
| C cltdo 83 | `cltdo83` PARTIAL (slot 3): Titan Strike by clicks reaches `exe+0x2b25e0` (2 + 3 calls, 0 client missiles: Titan Strike has no cltmissile, as 1.14d); Soulshatter never starts on a zombie (Unsummon's start: own pet only), Mana Sweep as an oskill does not reach the client do (client follows only skills in its own list) | same function as 1.14d (section 4.1); the missile branch on screen is still open | none |
| C prg slots | `skillprog` (slot 3): **Batstrike PASS** on an assassin (charges 2 -> 3, finisher `knocknova` x128, client prg 25 called twice, last skill 326); Blackstorm's cltprg 28 confirmed by lane triage (this slot had no paladin) | same numbers in both games | none |
| H Pande 2 waypoint | `pandewp` PARTIAL (slot 1): arrived in 134 by the waypoint warp (kind 13), no class-402 object (as 1.13c), Valley reached, bit 17 = 1 there; the panel opens with the Act I tab only (the test character has no later act open, the harness has no act-progress verb) | as 1.13c (bug #13) | none; the Act 2 / Act 5 tab lists by eye on a character with those acts open |
| K terror zones | `terrorzones` PASS (slot 1, 10 min in Blood Moor): no terror / tremor / desecrated / herald line, the mod's desecratedzones.json installed | data switches them off | none |
| + `whirlwind` (#281) | `whirlwind` PARTIAL (slots 1, 3): the hook answers a spin (`stat68 110, IAS 0, D2R speed 110 -> 5 frames; 1.13c speed 110 -> hit every 4`): D2R's stat 68 carries 1.13c's base 100, as the rule assumes; control (`MXL_CONTROL=whirlwind`): `mxl2012` line off, 0 calls | the part works as built | kept. **Owner decision 2026-10-29: keep the plugin's classic (1.13c) hit rate per spin**; the feel stays on the final human visual review list (lane unporteda) |

No check failed for a reason a plugin part would fix, so B, C, H and K add no part.

## 15. Rules audit (lane rules-chars, 2026-10-28)

`docs/median-rules-audit.md` (character sections) compared every character table cell Median changed from vanilla with the
build. Two coded 1.13c rules that D2R holds in data were fixed in the build (bugs #240, #241: data, no part). One candidate
part:

**L: levels.txt `IsInside` (bug #242): dropped, no part.** 1.14d parses the column into its levels record (`+8`) but no code reads it (all levels-array accesses go through `0x61db70` and the byte getters; none reads `+8`); D2R does not load it. Light (Intensity / RGB, day/night only when R/G/B are all 0), rain and mud come from columns D2R reads as 1.13c did, so the four levels look as in Median's engine. Lane isinside, 2026-10-29: accepted, no visible effect.

No part needed (data or D2R native): drop upgrade odds (D2R codes vanilla's values, which Median kept), potion class
percentages (Median's potions are pSpell 6), skill points per level, light radius, resurrect cost.

## 16. Item rules audit (lane rules-items2, 2026-10-28)

`docs/median-rules-audit.md` (items sections: 49 rules) took every item rule to a verdict against Median's own compiled
tables and D2R's code. Two gaps were data and are fixed in the build (bugs #310 misc `auto prefix`, #311 cube input that
names nothing); no new part is needed. D2R code read for the verdicts (all build 93847):

| What | Address | Finding |
|---|---|---|
| Cube player conditions | `0x529230`, jump table `0x52992c` (ops 1-14) | 3-6 total `>=` `<=` `!=` `==`, 7-10 base, 11-14 non-base; value `>>` the stat's ValShift; ops above 14 pass |
| Cube item conditions | `0x52a15b`, jump table `0x52a8e8` (ops 15-27), input 1 only (`0x52a146`) | 15-18 total `>=` `<=` `!=` `==`, 19-26 base / non-base, 27 mod class `!=` |
| Cube op 28 | `0x52a0b5` | base `quest` + `questdiffcheck` (record +0x13a / +0x13b): item stat 356 must equal the game's difficulty |
| Empty input slot | `0x529d96` | flags `& 3` == 0 passes at once; the search's item count check is `0x529223` |
| Item table loads | `0x318290`-`0x318423` | weapons, armor and misc load with the same field list (`[rbp-0x10]`, builder `0x315fd0`, holds `auto prefix` `0x1cfaff0`) |

Contingent (build only if the real-path check fails):

**M: charm flag (IB7, RP5).** Median marks 14 item types `Charm` 1; D2R's itemtypes has no such column. All of Median's charm
types reach `char` through Equiv, so a type test with equivalence treats them as charms. If RP5 shows a Median charm type
(trophy `araa`-`arag`, `summ`, `grtz`) giving no stats from the inventory: find D2R's charm test (the stat list / inventory
check that 1.13c makes with ItemTypes `nCharm`) and answer it from Median's column (kept in `work/mod/overflow/itemtypes.txt`).
**S**, no address yet. RP5 in game (lane rulescheck, 2026-10-28): not decided. The Scroll of Summons (`summ`, unique row 176) picked up
from the ground shows "Required Level: 6" in red and gives a level-1 character nothing (oskill 596 stat 0), which says nothing
about the charm flag; every Median charm and trophy has a level requirement (6 to 90). Needs a character at the requirement
(check `rpcharm`: inventory vs cube vs ground). Item M stays contingent.

## 17. Cube (lane cube, 2026-10-28)

Evidence: `docs/median-rules-audit.md` CU12-CU14 and "Cube recipe classes in game"; static check `tools/cube_rules_check.py`
(build step, 0 errors). The data reaches D2R as 1.13c compiled it; one engine difference is left.

**S: `useitem` in a second output (bug #350, CU14). Done: plugin part `cubedupe` (lane cube2).** 24 dupe rows (8397-8420)
put `useitem` in output a and b with the same mods. 1.14d's `Game.exe` (read for 1.13c: Median 2012 patches no code): the
matcher `0x565010` stores input 1's item in all three output entries of the search context (`0x5656ee..0x565816`, input 1
only), and the executor `0x565ab0` makes a NEW item for each `useitem` slot with the item duplicate `0x55a2a0` (`0x565e8c`;
serialise to 0x400 bytes and read back) before it applies that slot's mods; the inputs are used up afterwards, so two
`useitem` slots give two copies of input 1, both with `item_hasbeenduped` 1 and levelreq + 5. D2R's executor keeps input 1
itself for `useitem` (`0x527104`: its id leaves the list of inputs to consume, no copy) and output b finds the id gone
(`0x527170` -> `0x52788f`), so one item comes out. The post-hook on `0x5269c0` copies output a once per further `useitem`
slot with D2R's same duplicate (`0x43d660`) and puts the copy in the cube (parts table above).

## 18. Item level above 99 (lane ilvl, 2026-10-28; bug #251)

The owner reversed the earlier "stays 99" ruling (2026-10-28): Median's monsters go to level 120 and its cube rerolls / upgrades
read the item level, so items keep 100-127. Static read of the D2R dump (`tools/d2r_find.py`, `mxl2012-runs/gameplay/d2r93847_dump.exe`):

| Place | What it does with the item level | Verdict |
|---|---|---|
| Writer `0x37d140` (D2Common Items.cpp; called by `0x37ffd0`, D2Common's item serializer, which `0x375ee0` calls and which calls itself for socketed children) | `0x37d733`: read item data `+0x38`, `< 1 -> 1`; `0x37d744 cmp ecx,0x63 / jl` (below 99: read again and written as is); `0x37d74d mov eax,0x63` (99 and up: 99); `0x37d770` cap at r15d = 0x7f; `0x37d77d mov r8d,7` + `0xa1b710` (bit write) | **the clamp of bug #251**: patched (part `ilvl`) |
| Reader `0x378860` (load) | `0x378c76` reads 7 bits, `< 1 -> 1` (`0x378cf6`), stores `+0x38` at `0x378d05`; no upper clamp | keeps 1-127, no change |
| Reader `0x37a8ce` | while applying the socket count (stat 194, `0x36e880`) it sets `+0x38` to 99 and restores the saved level right after (`0x37a954`) | temporary, no change |
| Reader `0x37b923` | `cmp r13d,0x63`: r13d is the item format version, not the level | not the level |
| `0x58c940` | affix level: `ilvl > 99 -> 99`, `99 - qlvl/2`, `2*ilvl - 99`, magic level (`+0x150`) | 1.13c's own formula (D2Common affix level), unchanged |
| `0x58ce80` | `min(max(ilvl + 2, 1), 99)` passed on (affix table walk of an item type, `0x3142f0`) | a derived level, as in Diablo II; not changed (not read further) |
| `0x41b3f8` (PlrSave.cpp) | `min(ilvl, 99)` into a debug text line (`itemLevelId = %d`) | text only |
| Generator `0x43d530` / `0x442d60`, drops (`0x43e8a0`), cube executor `0x5269c0` area, vendor / gamble (`0x4f0000`-`0x500000`, `0x53c000`-`0x540000`) | no 0x63 compare on the level (scan of every function there); the generator's own "level above 99" branch is the ethereal roll | no clamp |

Other 0x63 hits on the item paths are not the item level: `0x4fab35` (a byte `+0x9c` summed and capped at 99, PlrMsg.cpp),
`0x4f989d` (a count >= 99), `0x36f230` (player stat 87 capped at 99), `0x3cbf90` / `0x3cecb5` / `0x3d13b3` (`99 - x` in stat
formulas). The 7-bit field cannot hold more than 127, so 128+ (only reachable by the harness) is written as 127.

The part `ilvl` (`item_level.cpp`, off word `ilvl`) compares 84 bytes from `0x37d733` (read, the clamp, the 0x7f cap, the 7-bit
write up to its call) and `mov r15d,0x7f` at `0x37d67d`, then `PatchBytes` the 14 clamp bytes at `0x37d744` with both
immediates 0x7f. On any byte difference it logs `FAILED (bytes differ, left as D2R: 99)` and writes nothing. In-game evidence:
docs/testing.md "Lane ilvl".

## 19. Rune letters of the Great Runes (lane runeletters, 2026-10-28; bug #334)

The second line of a runeword's tooltip, the rune letters between quotes, is built in D2Client InventoryTooltips.cpp
(chunk `0x2c2909`..`0x2c2a4e`, static read of the 93847 dump with `tools/d2r_find.py`):

| Address | What it does |
|---|---|
| `0x2c2920` / `0x2c2a2b` | first / next socketed item (`0x38aab0` / `0x38aba0`); `0x373890(item, 0x4b)` keeps the runes |
| `0x2c297b` | `0x313ce0(data flag, gem index)` -> gems record (0xc0 bytes; the index from `0x349860`, items record `+0xf8`) |
| `0x2c29ae` | `add rbx,0x20`: the record's 5-character `letter` cell, made a string_view `{rbx, strlen}` at `[rsp+0x30]` |
| `0x2c29da` | key lookup through the thunk `0x3e2b736` (`jmp [rip-0x924]`, slot `0x3e2ae18`, into D2RLoader's string table): rcx = string_view*, rax = text |
| `0x2c29f5` | the same lookup of `strMissingString` (length 0x10) |
| `0x2c29fa` | `cmp rdi,rax / jne`: the same pointer -> copy the cell itself (`0x1227840`, 6 bytes); else the lookup's text |
| `0x2c2a23` | append to the line (`0x12276a0`, 0x400) |

So D2R itself means to draw the raw cell when the cell is no key, as 1.14d always does (`0x486670` draws the cell). Under D2RLoader
the failed lookup and the lookup of `strMissingString` are different pointers with the same text, so the cell is never drawn:
"Missing string" for Median's Great Runes r34-r56 (no key in D2R's namespace, D2RLoader rejects a new `d2r:` key, and the field
cannot hold a `mxl2012:` key), and another D2R key's text for No / On / Xar ("NO", "ON", "Ornate Plate"). The build points r01-r33
at D2R's `r01L`..`r33L` (data/string_gaps.tsv, bug #330); those stay on D2R's lookup.

The part `runeletter` (`rune_letters.cpp`, off word `runeletter`) compares the thunk's 6 bytes and the 0x7a bytes `0x2c29ae`..`0x2c2a28`
(both rel32 calls into the thunk included), then writes its own function into the slot with `PatchWriteU64` (the old pointer as the
expected value; a direct VirtualProtect write when the loader refuses the data write, reported as `slot written`). The function
calls the original lookup and returns its answer, except when its return address is `0x2c29df`: there a cell that is not `r01L`..`r33L`
(any case), or whose answer is empty / "Missing string" / the text of `strMissingString`, is returned as itself (thread-local copy,
cut at 15 characters). All of the thunk's 1,217 call sites pass only rcx (string_view*), so the one-argument pass-through keeps their
calls. On any byte difference it logs `off: bytes differ ...` and writes nothing. `mxl2012` line: `runeletter on: ...; letters drawn
from the cell N, D2R keys kept M`. Unit tests `runeletters_tests`; game check `runeletters` (docs/testing.md "Lane runeletters").

## 20. Harness `equip` packet (lane skillsweep, 2026-10-28)

**S: bug #391.** `equip` places the item on the server body slot, then sends it with `SendItem(..., 1, 2, page, ...)`
(`harness_cmds.cpp:1579`), the update kind for an item put in a page. The client keeps its old weapon until the character
is re-entered. Read which kind D2R's own equip path (`0x535f60` callers on the body-location branch) sends and use it
for `bodyLoc > 0`. Then drop the `leave_and_reenter()` after gear in `tools/skill_sweep.py` and check `skillprog`.

**Done (lane equip391, 2026-10-28).** The 5th argument of `0x535f60` is the item's command flag (item data +0x14; the 4th, the item
flags at +0x18). D2R's item-to-body handler (packet 0x1a, `0x4aa450`; entry 0x19 of the client packet table `0x1d2a798`, which starts
at opcode 1) on success (`0x4aa682`): clear item flag 0x4000, `SendItem(game, player, item, 1, 8, body loc)`, `0x34dbe0(player, 1)`.
`harness_cmds.cpp` does the same when `bodyLoc > 0` (`hcmd::PlaceCmdKind`: 8 equip, 2 put in a page). Checked in game on slot 3
(spear skills and Batstrike right after `equip`, no re-entry); `skill_sweep.py --reenter-gear` keeps the old workaround.

## 21. Skill tooltip labels (lane skilltips, 2026-10-29; bug #396)

D2R's skill tooltip line renderer `0x287a50` (jump table `0x289f88`, types 1-79; 1.14d `0x4edea0`, table `0x4eedc8`, types 1-75)
reads the skilldesc record through `0x88850`: type at +0x3e + line, text A at +0x50, text B at +0x74, calc A / B at +0x98 / +0xe0
(18 lines: 6 desc, 5 dsc2, 7 dsc3). Read statically against 1.14d, line type by line type:

- Types 1-73 append as 1.13c did (text, number, unit), except 13, 34, 36, 40 (text A), 53-56, 66, 74 and 75, which D2R formats with
  printf; 76-79 are D2R's own. Data: `strings_ns.SKILLDESC_FORMAT`; a text cell of an appending type whose D2R text is a printf
  format names the mod's own words `<key>_mxl` (`txt_migrate.median_skill_wording`).
- Type 1 (mana cost): 1.13c took the label from skilldesc `str mana` (record +0x10); D2R dropped the column and reads text A, so a
  blank text A is the dummy string 5382. Data: the row's `str mana` key goes into text A.
- Types 9, 10, 11, 14, 22, 25, 27 and 28 append a label named by id in the code (`StrSkill4`-`8`, `13`, `18`, `20`, `34`, `39`),
  whose D2R text is a printf format. No cell changes it: plugin part `skilltext` (table above).
- Type 52 is type 38 with a sign in both games (lane colourcode, 2026-10-29): 1.14d case `0x4ee90e` pushes 1 and joins type 38's
  `0x4e7f40`, D2R case `0x2892fa` sets the byte flag and joins `0x288d57` -> `0x291350`. Both append text A, the range as `"+%d-%d"`
  (flag 1; type 38: `"%d-%d"`; a single number without sign when calc A = calc B), text B and the `newline` string (1.14d id
  0xf9e). 2 Median lines: Widowmaker "Crossbow Base Damage: +2-5 " (`DescWidowBase`, `DescBlank`), Merkabah "Area Attack Magic
  Damage: +5-25 percent of base strength" (`DescMerkabahStr1` / `Str2`, level 1); 3 vanilla rows (Frenzy, Feral Rage, Maul) keep
  D2R's own text. Nothing to change.

The audit kind `skill-desc` (docs/text-audit.md) finds the data cases; `FIXED_LABELS_HANDLED` marks the plugin's types as handled.

## 22. Durability loss on the client (lane durability, 2026-10-29; bug #433)

**Only if the player-path test fails.** First run `ven_vendors` with `MXL_VEN_WEAR=click MXL_VEN_TOWNS=1 MXL_VEN_NPCS=Charsi`
(the Circlet picked up and worn by clicks, not by the harness `equip`). If Repair All then works at the first try, #433 is the
harness set-up and this part is not needed.

What D2R does (static read of the 93847 dump): the wear dispatcher `0x441b10 (game, unit, item)` takes one point off stat 0x48
(`0x2f7940(item, 0x48, value, 0)`) and sends packet 0x3e through `0x47a190(client, item, 1, 0x48, value, 0)` to the client of
`unit` (`0x48fde0`). The client handler (`0x12c8d0`) is protected and cannot be read. In 1.14d (`0x4c1f30`) it sets the stat raw.
If the click-worn item still shows full durability, the client drops or misfiles that update, and a full resend of the item
(what lifting and re-wearing does) is the work-around.

**S: post-hook on `0x441b10`** (off word `dursync`; entry bytes `48 89 6c 24 10 56 57 41 54 41 56 41 57 48 83 ec 30`, 17 bytes,
no rip-relative operand). Before the original, read `0x2f5020(item, 0x48, 0)`. After it, when the value
changed, the unit is a player (type 0) with a client (`0x48fde0` not null) and the item still exists and is worn (item mode 1),
resend it as `IdentifyItem` in `harness_cmds.cpp` does: `0x535f60(game, player, item, 1, 0, mode, page, byte54, position)`
with mode = the item's mode, page = `0x36cfe0(item)`, byte54 = `0x36ca10(item)`, position = `0x34a110(item)`. All of its location arguments
come from the item, so it should fit a worn item too (to be checked in game). A broken item (value 0)
takes D2R's own break path (`0x43eaa0` / `0x43ea10`) and needs no resend. Wear procs run on 4-10 % of hits, so the extra packet is
rare. Pure logic (when to resend) in a `dur_sync_logic.h` with unit tests. Counter on `mxl`: `durability resends N`.

Check: `ven_vendors` with `MXL_VEN_WEAR=click` at Charsi, Fara and Larzuk: the tooltip after the fight shows the server's value,
and Repair All repairs at the first try. Control with `dursync` off: the bug comes back.

**Result (lane dursync, 2026-10-29): not the resend, a 5-byte patch** (`plugin/src/dur_sync.cpp`, `dur_sync_logic.h`, off word
`dursync`, unit test `dursync_tests`). The S design above was built and worked (the resent item showed the server's value),
but the harness verbs `durwatch` / `cistat` (docs/testing.md) found the cause, so the hook was replaced:

- The server does send 0x3e (one per point lost), and the client's 0x3e table handler is entered for each. D2R's own client
  apply `0x1c7710` is never called (D2RLoader's thunk at `0x12c8d0` does the work itself), so its counter says nothing.
- The 6th argument of `0x47a190` is the stat's layer (16 bits). The wear loss branch stores it with
  `mov word ptr [rsp+0x28],si` at `0x441c4b`, which leaves the upper six bytes of the 8-byte slot as they were: seen in game
  as `0x140380000`. `0x47a190` is a D2RLoader `jmp [rip]` thunk (slot `0x3e2a1b8`), and its code reads the slot wider than
  D2R's own body does (`movzx ebx, word [rsp+0xd8]`): the client keeps the old value (`cistat ... scan`: only layer 0, the old
  value, so the update is dropped, not filed under another layer).
- Proof both ways: a watch that re-stores the argument as a clean 16-bit value made the update land (client = server, Repair
  All at the first try, `dursync` off); a watch that passes the raw slot on did not (client 10, server 8, Repair All refused).
- Patch: `66 89 74 24 28` -> `48 89 74 24 28` (`mov qword ptr [rsp+0x28],rsi`; rsi is 0 from the `xor esi,esi` before it).
  The loss branch from its stat set to the jump into the shared send (`0x441c2b`, 46 bytes) and the send (`0x441e62`, 17
  bytes) are compared first. No extra packets: 2 points lost = 2 packets 0x3e, nothing else.
- Not a data problem: Median's durability rows (Save Bits 10 / Save Add 150, max durability 10 / 90) do not enter 0x3e
  (value sent in a 32-bit field, no table read); they stay as they are (save compatibility untouched).
- The other `0x47a190` callers: 11 store the layer as a dword (their client updates are not known to fail), three as a word:
  `0x43eb8e` (inside `0x43eb30`, itself a D2RLoader thunk: probably dead code), `0x4369c9` and `0x46f484` (stat 0xcc, an
  item's charged skill: bug #484, not patched, the width of their source registers is not known).

## 23. Missile without a source (lane hsource394, 2026-10-29; bug #394)

**Optional; log line only.** D2R's server missile create `0x5371a0 (game, &params)` tests `params->owner` (+0x08) first: when
it is null it logs `ptCreate->hSource` (Missiles.cpp:202, descriptor `0x239e3c8`, reporter `0x536b20`) and then takes
`je 0x537325`, which returns 0 (no missile). 1.14d's create (`Game.exe 0x59fa30`, the stand-in for 1.13c) makes the same test
(`mov eax,[esi+4] / test eax,eax / jne`) and returns 0 with no log line. So the result is the same in both games; only the
line differs. The callers that hit it ignore the result (server do 23 `0x45a080` calls `0x463100` next, with nothing read from
the return value), so there is no crash path. What sends a null owner: missile functions that pass the missile owner straight from the owner
getter `0x490300` (null once the casting unit is gone) into the params with no test. Server do 9, 12, 22, 23 / 24, 30 (second
call), 32, 34 and hit 4, 11, 46, 48, 51 do this in D2R (static scan of every do / hit slot that calls `0x5371a0`: do 2, 6, 12
(first), 15, 28, 30 (first), 31, 33, 38, 40, 42 and hit 5, 12, 15, 25, 26, 29, 52, 58 test the owner first).

**L: one more row in `orig_asserts::Blocks`** (off word `hsource`, same mechanism as `animseq` / `monequip` / `aurastate`):

    // 0x5371d1: lea rcx,[rsp+0x50] / mov byte [rsp+0x50],0 / call 0x536b20 / test al,al / je +1 / int3 ; next: cmp qword [r14+8],0
    {0x5371d1, 0x5371e5, {0x48,0x8d,0x4c,0x24,0x50,0xc6,0x44,0x24,0x50,0x00,0xe8,0x40,0xf9,0xff,0xff,0x84,0xc0,0x74,0x01,0xcc}, 20,
     0x536b20, "hsource", "missile without a source (ptCreate->hSource)"},

`0x5371e5` repeats the owner test and goes to the `return 0` at `0x537325`, as 1.14d does. Test: `orig_asserts_test.cpp`
`BlockCount == 4` plus `Blocks[3].rva == 0x5371d1 && next == 0x5371e5 && reporter == 0x536b20`; add `hsource` to the off-word
list in `mxl2012_core.cpp`. Check: the `acts` Mephisto stage (Durance 3 with `firewizard2`, see bugs.md #394) shows no
`ptCreate->hSource` line; with `hsource` off it comes back. The Chaos Sanctuary source (nmhell3) is not known yet. To find it,
the row could become a counted hook that logs `params->missile` (+0x20) once per class before the jump; plain L does not log it.

## 24. Legacy level-up buttons (lane uiplus, 2026-10-29; bug #488)

In legacy graphics a level-up left the classic HUD's StatUp / SkillUp + buttons grey with dead clicks until G was pressed twice.
D2R, not Median: D2Client's `LevelUpButtonWidget` (`UI\Widgets\LevelUpButtonWidget.cpp`, 0xd70 bytes, vtable `0x1fd9ee0`, type
descriptor `0x14d06d0`) recomputes itself in its Update (slot 2):

| What | Address | Notes |
|---|---|---|
| Update | `0x14d1090` | panel offsets, then `+0xd5c` = lit mask from `0x14d0dd0`; mask 0 -> disable `0x86eec0` (byte `+0x67a` = 1, disabled frame), else enable `0x86efb0` |
| lit mask | `0x14d0dd0` | per button type (`+0xb88`, count `+0xb94`): 0 = skill (stat 5, UI var 7), 1 = stat (stat 4, UI var 6), 2 = quest; syncs the UI var (`0xcd7c0` / `0xc7d30`) |
| Draw | `0x14d01a0` | draws frame `+0xd5c` of the 8 at `+0xbf0` (stride 0x28) |
| click | `0x14d0ca0` (slot 24) | per lit bit opens UI 4 (skill tree), 2 (character sheet) or the quest log |
| HUD lookup | `0x846170(name)`, `0x856220(widget, name)` | panel by name (`HUDPanel`), child by name (`StatUp`, `SkillUp`) |
| graphics mode | `0x846210()` | panel manager (`0x3440170`) byte `+0xb9`: 1 HD, 0 legacy |

The widget tree runs Update only on enabled widgets (Draw on all). HD's `HUDPanelHD` keeps its buttons going; in the classic HUD
a button that disabled itself (no points) was never updated again. Harness `lvlbtn` (dev, client side: state, `count` puts counters
into slots 2 / 3, `update` runs Update by hand) showed 0 Updates against 800 Draws after a legacy level-up, and one Update by hand lit
the buttons for good.

**Part `lvlupui`** (`lvlup_ui.cpp`, `lvlup_ui_logic.h`, test `lvlupui_tests`): the Draw slot `0x1fd9ef8` is replaced (PatchWriteU64 with
the old value) by a wrapper that, when `0x846210()` says legacy and the button's `+0x67a` is set, runs the widget's own Update first.
HD and enabled buttons go straight to D2R's Draw. Before the write: both slots hold `0x14d1090` / `0x14d01a0`, their 16 entry bytes,
the disable's `mov byte [rcx+0x67a],1` and the 20 bytes of `0x846210`. `mxl2012` prints the counts. Checked in game (docs/testing.md
"Lane uiplus" round 2): the buttons light at the level-up and open the panels; HD unchanged; no asserts.


## 25. Apple: 1.13c item spell 10 (lane phase3, 2026-10-29; bug #499; built by lane apple, 2026-10-30)

engine-triage #24 sends this here. 1.14d `Game.exe` item-spell table `0x741794` (8 bytes per entry; 1-11 filled: `0x5be230`, `0x5be290`,
`0x5be3f0`, `0x5be7b0`, `0x5beac0`, `0x5bef90`, `0x5bf0c0`, `0x5bf060`, `0x5beda0` (elixirs, tables-status.md), `0x5bf170`, `0x5bf1f0`).
Entry 10, `0x5bf170`: item record by class (`0x6335f0`), then function id 0x2f = skill 47 started on the user: on the unit from
`0x553540` when there is one (`0x5fdca0`), else at the user's x / y (`0x648a10` / `0x648a00`, `0x5fdd60`). Median 2012's skills row
47 is `Apple Healing Spell` (srvdofunc 18, aurastate `mega_apple`, auralencalc 15000, aurastat1-5: hpregen and four synergy stats).
D2R's pSpell 10 is the Book of Skill (bug #240 gives `ass` that number), so a part must tell the two apart by item code.

Proposed part `appleuse` (off word `appleuse`): wrap D2R's item-spell 10 handler; for an item whose code is not `ass ` start the
built skill `Apple Healing Spell` (its id looked up by name at table load, not the number 47: the build may renumber) on the user
with D2R's own skill-start path, then use the item up; `ass ` goes to D2R's handler unchanged. Needs: D2R's item-spell table and its
entry 10 (not in d2r-addresses.md yet), the skill-start function. Check: `rpsignets` (its `dog` row: the Apple used up, skill points
unchanged; by hand: state `mega_apple` on the player, hpregen up). Data stand-in if the part is refused: pSpell 6 with
state `mega_apple`, len 15000, stat1 hpregen (loses the synergy stats; an unported.md "approx" row).

**Built (lane apple, 2026-10-30; owner decision: the plugin part, the full effect).** D2R's item spells, read in the dump
(D2Game SkillItem.cpp):

| What | Address | Notes |
|---|---|---|
| item-spell descriptor | `0x300ae0(dataFlag, item)` -> `0x236fe30 + 12 * pSpell` | `{check index, use index, flag}`, 20 entries; items record `+0x94` = pSpell. pSpell 10 is `{7, 10, 0}` |
| check table | `0x1d3ea30`, 11 entries, `(game, user, item) -> bool` | called by `0x5817f0`. Slot 7 = `0x5806f0`: Radament's book flag (quest 9 bit 5) set, else "I can't" (`0x491960(user, 0x14)`). Only reached through the table |
| use table | `0x1d3ea90`, 16 entries, `(game, user, item) -> bool` | called by `0x581680`, which then uses the item up (`0x46f090`) and logs a SkillItem.cpp verify line on a 0 answer. Slot 10 = `0x580750`: the Book (stat 5 +1, the quest flag, sound 8) |
| item-event casts | `0x5896e0(unit, skill, level, target, flag)`, `0x589820(unit, skill, level, x, y, flag)` | 1.14d `0x5fdca0` / `0x5fdd60`; both go through the resolver `0x589930` (the skill needs ItemEffect: row 47 has 1). Target `0x48fe20(game, unit)`; position words `0x34b8f0` / `0x34b940` as the event handler `0x583b30` passes them |

**Part `appleuse`** (`apple_use.cpp`, `apple_use_logic.h`, test `appleuse_tests`, off word `appleuse`): check slot 7 and use slot 10
get the part's functions (written only while they hold D2R's). For an item whose code is not `ass ` (D2R's Book of Skill keeps its
own two functions) the check passes, as in 1.14d (entry 10 has no check), and the use casts skill 47 at level 1, flag 0, exactly
as 1.14d `0x5bf170`: on the user's target unit when there is one, else at the user's position. The use answers 1, so the item is
used up. The id 47 is a constant: 1.13c rows keep their ids (id-mapping.md), like `melttrail`'s 173. `mxl2012` prints "casts N,
refused N, Books of Skill left to D2R N". Checks `apple_use` (bought from Charsi, state 44, its five stats and 15000 frames, Save and
Exit) and `rpsignets` (`dog`: used up, no skill point, state `mega_apple`); results in docs/testing.md "Lane apple".

Checked in game (lane apple, 2026-10-30, slot 3, new Barbarians): the Apple bought from Charsi and used by a right click is used
up and starts `mega_apple` with 14890 of 15000 frames left when read. Its five stats equal skills row 47's formulas
(hpregen 6 = maxhp / 3000 at item_faster_potions 0, and 7 / 9 / 11 / 1 from the four synergy stats). No skill point is added.
After Save and Exit the Apple stays used up and the state is gone (1.13c saves no states). `rpsignets` passes all seven rows.

## 26. Pets spread round their owner after a warp (lane totems, 2026-10-29; bug #493)

Owner ruling (2026-10-29): Bend the Shadows (486) keeps gathering the totems, but they must not end stacked. Median's pettype
`totemic` has `warp` 1, so D2R brings the totems along whenever the Necromancer is moved, and puts them on the owner's own sub-tile.
The totems cannot walk (monstats2 `barbtotem`: modes DT / NU / A1), so they stay stacked. There are two D2R paths, both read in the dump:

| What | Address | Notes |
|---|---|---|
| owner's pets set on its new spot | `0x500a40(game, owner, x, y)` | called by the unit move `0x491ca0` at `0x491f92` after the owner is placed. Pettypes 1..n (table `+0x12d8`, 0xc8 bytes each): for a type whose flag byte `+4` has the warp bit (mask dword `0x1d996d0` = 1), every pet of the owner's list of that type (`0x5013f0`; node `+0` flags, `+4` unit id, `+0x18` next; unit `0x48fe80(game, 1, id)`) is set **exactly** on (x, y). Types with mask `0x1d996d4` go through `0x501920` instead. This is the Bend the Shadows path: it moves the player with srvdo 27 `0x554c40` -> `0x491ca0`. Entry `48 89 74 24 20 48 89 54 24 10 55 57 41 54 41 55` |
| set a unit on a spot as it is | `0x501df0(game, unit, node or 0, room, x, y)` | no free-spot search; sets the teleported flag `0x34f490(unit, 1)`. Also called by `0x4fe8f0` (a pet's own pets) and the level change. Entry `48 89 5c 24 10 48 89 6c 24 18 56 57 41 56 48 83 ec 40` |
| pet warp to the owner | `0x596d40(game, owner, pet)` | D2Game AiUtil.cpp. It is used for a pet in an inactive room (`0x504b70`) and by AI functions `0x5bc940` / `0x5c1460` / `0x5d6910`. It tries a random spot in the owner's room first, then the owner's position through `0x491ca0`'s free-spot search `0x362f90` (mask 0x1c09: no unit bit), then that position as it is. **Not** used by Bend the Shadows (counter 0 in game). Entry `48 89 5c 24 18 55 56 57 41 54 41 55 41 56 41 57` |

**Part `petspread`** (`pet_spread.cpp`, `pet_spread_logic.h`, test `petspread_tests`, off word `petspread`):
- `0x500a40` is wrapped. During the call, a hook on `0x501df0` only records the units it places (at most 32). It moves nothing
  inside D2R's pet-list loop.
- When `0x500a40` returns, each recorded pet that stands within one sub-tile of its owner is moved to the first spot of a ring
  round the owner that is both:
  - free: `0x350a20(unit, x, y, mask)` with 0x1c09 plus the player, monster and pet bits 0x80 / 0x100 / 0x2000;
  - not within 2 sub-tiles of a pet this gather already placed. D2R's collision test did not see a totem placed a moment
    earlier: in the first build all four ended 1 sub-tile apart.
- The ring is 8 spots at 3 sub-tiles, then 16 at 5 and 16 at 7.
- The move is the unit move `0x491ca0(game, pet, 0, x, y, 0, 0)`. If the pet landed within one sub-tile of the asked spot, it
  is flagged teleported (`0x34f490`).
- A pet that `0x596d40` leaves on the owner's spot gets the same treatment (without the list).
- The gather itself is unchanged, and pets that are already off the owner's spot are left alone.
- **Totems only** (owner ruling 2026-10-29, lane apple): a pet is moved only when its unit id is in its owner's list of pettype
  `totemic` (row 34: the necromancer's five totems and Median's other `totemic` summons). The list is the one the gather walks:
  `0x5013f0(dataFlag, root, 34)`, root = `*(0x34b240(owner) + 0x98)`, for a player owner. Mercenaries and every other warp pet
  (Median 2012 gives players no golem) keep D2R's placement on the owner's spot and walk off by themselves.
- `mxl2012` prints "owner moves with pets N, pet warps N, onto the owner N, spread N, other pets left N (last pet class N)".

Checked in game (docs/testing.md "Lane totems", "Lane apple"): the four totems end on four ring spots (diagonals at 3) round the player, in HD
and legacy. Attack rates and states are unchanged (they were unchanged without the part too). Open: the 1.13c twin of `0x500a40`
was not found in 1.14d `Game.exe`, so whether 1.13c also stacked them is not known. The HD orbs left at the old spot are bug #500,
which the part does not change. Lane apple (totems only, 2026-10-30): `totem_spread` still spreads the four totems, and
`pet_keep` shows a Kashya mercenary and a Summon Shadows pet left to D2R after Bend the Shadows and after a waypoint
(`spread` +0, `other pets left` +2 / +4).

## 27. Baal's laugh in the chat (lane baallol, 2026-10-30; bug #508)

Owner ruling (2026-10-30): Median's skills and missiles that play Baal's laugh (voice file `baallaugh1`) print "Baal says: LOL"
instead of "Baal says: \*Laughing\*", at most once every 30 seconds; the sound keeps playing every time. The text is data: the
`d2r:baallaugh1` record of `data/d2r_string_fixes.json` (D2R's `vo.json` key; `merge_string_overrides.py` folds it into
`overrides.json`, so there is no second copy of the key, bug #1). It also changes Baal's own laugh in the Throne (accepted).

D2R's subtitle, read in the dump:

| What | Address | Notes |
|---|---|---|
| client play | `0x1a0780(sound id, unit, ...)` | starts the sound; then, when `0xd2e490` (subtitles on) and the flag at `rbp+0x7f` is 0, calls the subtitle at `0x1a0bc3` with `(id, 0)`; the return is not used |
| voice subtitle | `0x1a0da0(sound id, flag)` | sounds record `0xd96a0(id, 0, 0)`, path at `+0x32`; `0x1a0210` makes the key (copy of at most 0x9b bytes, no extension, no trailing `_hd`, lower case, file name only); `0x3e2b724` (D2RLoader's key -> id) and `0x3e2b730` (id -> text). With flag 0 and a key that is not `strMissingString` it finds the speaker through a map at `0x2357de0` (the player's class names, `Hireables`, `Cain`, else a speaker string; not read further) and writes `DialogSpeakerFormatString` ("%s says: %s") into the chat (`0x3e2b7f0`). One caller. Entry `4c 8b dc 55 53 49 8d ab 08 ff ff ff 48 81 ec e8 01 00 00` |

**Part `vochat`** (`vo_chat.cpp`, `vo_chat_logic.h`, test `vochat_tests`, off word `vochat`): an inline hook at `0x1a0da0` reads the
sound's path the way the subtitle does. For the key `baallaugh1` (`PathKeyIs`: file name, no extension, no `_hd`, any case) it
returns without printing when the last line went out less than 30 s ago (`LineAllowed`, `GetTickCount64`); otherwise it notes
the time and calls D2R's function. Every other voice line and every sound are unchanged. `mxl2012` prints "Baal laugh lines
printed N, left out N". The same test on another key would extend it to the soldiers' "Over here!" (`sol_overhere`) and "Help
us!" (`sol_helpus`): a list of keys with a time each instead of one key (not done: owner ruling, they stay as they are).

Checked in game (docs/testing.md "Lane baallol", slot 4, HD and legacy): "Baal says: LOL" from Spawn Edyrem right clicks at 0 s, none until 30 s, then once
more at 38 s; a `dark_master1` laughed 29 times in 45 s and printed one line; the sound trace counts every laugh; 0 asserts.
