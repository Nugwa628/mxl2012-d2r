# Known D2R crash patterns against Median XL 2012

Why: crashes players hit on this engine and loader often come from paths that shortcut checks miss (death message, item type
ids, sound ids). Same engine, same loader, same 1.13c-era data patterns, so a list of known crash / hang / assert causes of 1.13c
data on D2R 3.3 was checked against this port (lane realpath, 2026-10-28). Rows C1-C21; C12 and C21 are not crashes but share a
cause with one.

Data evidence is from a lane build with this branch's `txt_migrate.py` / `idmap.py` (`mxl2012-wt/integ/work/mod`, 10:57), this
worktree's `work/named` (Median 2012's tables) and D2R 93847's own tables (the extract set up by `tools/lane_setup.py`). Probes:
`mxl2012-runs/realpath-audit/probe*.py`, dry run of the new passes on a copy: `dry.py`.

| row | what | applies to 2012? | evidence | fix | check |
|---|---|---|---|---|---|
| C1 | skill tooltip assert `stringIndex1 != strdummy` (line type without its text A / B) | **yes, fixed here** | 23 lines in both banks lack a string their D2R type needs: type 13 x20 (Valkyrie, Raise Skeleton, golems, Oak Sage, ...), 34 (Raise Skeleton), 41 (Fire Golem), 7 (Lion Stance). 1.13c hard-coded 13 / 34 / 41's text; D2R's own rows use exactly one text per type (13 `StrSkill42` "Life: %d", 34 `StrSkill4`, 41 `StrSkill5`). No type-40 or 74+ line of Median's is short (74 only on D2R's own rows) | `txt_migrate.skilldesc_lines`: 22 lines get D2R's text, 1 dropped (Lion Stance's type 7 with no text) | `tools/tests/test_txt_migrate_crash_rows.py`; probe2 after the pass: 0 short lines. In game: hover the trees of those skills, 0 `strdummy` in d2rloader.log (no check here yet) |
| C2 | crash on death: sysmsg7-9 "was slain by" passed to sprintf with Median's `%s` | already handled | `tbl2json.py` keeps D2R's text when printf placeholders differ (`placeholders`, `main` lines ~203-231); integ `strings_report.md`: 280 keys kept | existing | `tools/test_strings.py` `test_placeholders`; `rp_death` (2026-10-28, slot 3): a level-1 Sorceress killed by natural Stony Field monsters, "slain" message path ran, the game stayed up, Esc respawned |
| C3 | more than 512 states | no | 302 states rows (built base `states.txt`); idmap `STATE_SYNC_LIMIT` 512 | none | idmap limits report |
| C4 | levels above 255 (portal byte) | no | levels max Id 137 (138 rows) | none | - |
| C5 | vendor crash: item codes without an HD `items.json` entry (`[default_unit]`, null +0x12e) | already handled | `tools/item_hd.py`: integ `item_hd_report.json` 2429 items, 808 uniques, 181 sets, `missing_assets` [] (2 Median invfiles fall back to `charm_small`) | existing | `item_hd_report.json`, `tools/item_icon_check.py`; `rp_vendors` (2026-10-28, slot 3): Gheed, Charsi, Halbu, Malah trade panels opened, items bought by right click (and sold back, Gheed gambled), no crash |
| C6 | `BC_VERIFY ... UNIT_STATE_SHAREDSTASH` once per session | no (needs a plugin states fix, which this port does not have) | no states fix in mxl2012-core (302 states, D2R's arrays untouched) | none | - |
| C7 | hang loading a character (a states fix's copy routine patched) | no | same: no states fix, no stat-list copy patches in `plugin/src` | none | - |
| C8 | map memory self-loop: automap cel >= 1499; Layer > 99 indexes a 100-bucket table | no | no automap.txt in Median 2012 or our build (D2R's own, max cel 1498); levels max Layer 99, every Layer equals D2R's for the same Id | none | probe1 |
| C9 | client missile tick calls an empty client do slot (null call, RIP 0) | already handled | our bugs #8 / #14; `plugin/src/missile_stubs.cpp` stubs the empty client do / server hit slots | existing (`cltdostub`) | game check `cltdostub` (`missilescan` 0 / 0 / 0) |
| C10 | `Position 1` on a Median-only maze: empty entry-room table, null read | already handled (data); presets need a game look | `txt_migrate.fix_maze_positions` present, 0 rows: the mazes with Position (54, 74, 135) are D2R's own rows unchanged. Median turned 125-127 (Hell 1-3) into presets (DrlgType 2) and added preset 137 (Colossal Summit), all `Position 1`; D2R has preset rows with Position (1, 38, 40, 73, ...), so not the maze case | existing | `tools/area_audit.py` PROBLEM row; in game: `cheat goto` 125, 126, 127, 137 once |
| C11 | `nDesc >= 0 && nDesc < skillDescTbl.size()` assert (skill without skilldesc named by an item or cast) | **yes, fixed here for items** | 412 of 1110 skills have no skilldesc; 4 are named by item properties (Heal Mana Aura on `NewBookOfKalen`, Item Mega Impact, Item Thunderfury, Weapon Amazing Grace Mod); ~71 more only by monprop (Mon Hit / Kill Monster Effect ...) | `txt_migrate.blank_item_skilldesc`: those 4 point at an empty row `mxl_blank`; monster-only skills left alone (assert once per cast, logged, harmless) | unit test; in game: tooltip of the 4 items, no `nDesc` line |
| C12 | 1.13c srvdofunc 109 / srvstfunc 64 / cltstfunc 82 ran D2R's new functions (town portal) | already handled | `idmap.SLOT_REMAP` (109 -> 9, 64 -> 67, 82 -> none) and `SLOT_REMAP_WITH` | existing | `tools/test_idmap.py`; docs/function-slots.md |
| C13 | item packet empty: function-28 property layer on a stat with no Save Param Bits (`hUnit`, 0x34b891) | no | no property in Median 2012's or the built `properties.txt` uses func 28 | none (if one appears: clear the unsaved layers in data) | probe1 |
| C14 | `D2R.exe+0x7761DC`: stale event in D2R's HD UnitTranslationLayer at a character switch (Druid morph + Save and Exit) | yes, D2R's own; **needs plugin** | no plugin code in the frame there; same D2R image here; mxl2012-core had no guard | ported: plugin part `transguard`; game-checked (lane realpath2, check `crashrows`, run `checks-20261028-195354-s3`): the Druid cast Trap Rat Form (448) and Treewarden Form (463) by right click, then Save and Exit, 3 rounds: guard events 44 -> 48, 0 skipped, no crash | a long run with Druid morphs; the probe payload `0x80000003F0` was not met in game |
| C15 | Raven AI pet dies at once (counter from calc3 in D2R, Param1 in 1.13c) | **yes, fixed here** | Median 2012 monstats AI Raven: `companion` (Skill1 Wolf Companion, Param1 -2, calc3 empty) and `devilcat` (SorcFamiliar, same), both summoned by player skills. `druidhawk` / `midnightfaes` / `dragoncompanion` name skills Median does not have (Skill1 emptied by `clean_references`) and no skill summons them | `txt_migrate.raven_counts` (bug #390): calc3 `ln12` on Wolf Companion and SorcFamiliar | unit test; in game: summon both, alive after 30 s |
| C16 | hit-6 missiles spawn the wrong monster (sHitPar1 not remapped) | already handled | `idmap.NUMERIC_REFS` remaps `sHitPar1` on pSrvHitFunc 6 rows (102 rows); `validate.py hit6_spawns`: 0 errors in the integ build | existing | `validate.py`; game check `srvhit6spawn` (our #6 / #11) |
| C17 | client sound lookup on id -1 (`D2R.exe+0xD8CEA` null+0xC7) | yes, on D2RLoader's snapshot start; **needs plugin** | Every sound name resolves in our `sounds.txt` (12101 rows), but 206 are Median-only, after D2R's rows: 2 monsounds Neutral (`l4dwitchsnd`, `malewitchsnd`), 12 Taunt, 3 Skill1, 1 Death; skills 64, missiles 61, states 20, misc 422. On the start that builds `<D2R>\d2rloader\data\compiler\3.3.0\` D2RLoader 1.3.1 compiles only D2R's sounds, so all of those are -1 for that start | ported: plugin part `soundguard`; game-checked (lane realpath2, check `crashrows`, run `checks-20261028-195354-s3`): `sounds.txt` loaded with 12119 rows (the build's 12119), 0 bad sound ids skipped; the witches 1722 and 1740 (Median Neutral sounds) in view, no crash | the same on a snapshot start (the D2RLoader compile of D2R's sounds only) |
| C18 | player crash after a cube panel close, no fault logged | unknown, needs game | no cause known; no d2rloader log | none | `rp_use` (cube panel opened and closed, 3 recipes, 2026-10-28 slot 1: no crash); check `crashrows` (lane realpath2, run `checks-20261028-195354-s3`): cube opened by right click and closed with Esc 5 times, no crash, no fault |
| C19 | player crash on Steam 94995 after combat, no fault logged | unknown, needs game | as C18 | none | not testable here: the slots run build 93847 only. On 93847 combat runs ended without a crash (lane realpath2: `rp_death` natural deaths in Stony Field, `skillprog` casts, run `checks-20261028-193921-s3` / `195354-s3`) |
| C20 | circlet worn or picked up: D2R's fixed type ids (rune 75 = our circlet), `UnitGetType(hUnit) == UNIT_ITEM` assert | already handled | `idmap.align_item_types` puts D2R's rows at D2R's ids: built itemtypes ids 0-107 equal D2R's (jewl 58, warl 67, h2h 68, pelt 73, rune 75, circ 76, hpot 77, wpot 82, scha 83, mcha 84, lcha 85, gem4 96) | existing | `idmap.check_built` (build fails on a mismatch; integ: 0 errors), `tools/test_idmap.py`; `rp_items` (circlets picked up and worn) |
| C21 | socketed runes add nothing (same type id cause) | already handled | as C20 | existing | as C20; `rp_use` socketed a rune, a gem and a jewel by click |

## Plugin parts

Done (lane realpath, 2026-10-28): `sound_guard.cpp` (C17) and `translation_guard.cpp` (C14), docs/plugin-plan.md section 13.
`ModSoundRows` is 12119 (built expansion `sounds.txt`; base/ 12101), checked by `tools/tests/test_sound_rows.py`. Both follow
the pattern of `mxl2012_core.cpp` (an `Off("<word>")` part, a `mxl2012` status line, build-guarded RVAs).

- **Sound guard** (C17): inline entry hooks on build 93847: `0x107dd0` (unit, sound id) -> null for an id outside the table;
  record readers `0xd8c70` (+0xc7), `0xd9180` (+0xb0), `0xd9030` (path), `0xd9e60` and `0xda360` (variant pick) return their
  empty-table answer; row count `0x3b20c0`, record `0x3b1fd0`. Plus `CheckSoundTable` on D2RLoader's DataTablesLoaded: loaded
  rows below ours -> log and screen notice "close the game and start it again". Off word `soundguard`. Dev test switch
  `MXL_SOUNDGUARD_TEST` needs a monster with a Median Neutral sound (`l4dwitchsnd` / `malewitchsnd` users).
- **Translation guard** (C14): hook on `0x775fc0` (`TranslationEvent(layer, event)`, event type 0x10 of the loop `0x77a3b0`):
  `VirtualQuery` that `*event`, `[*event+0x70]` and `[payload+0x870]` are readable, else skip and count. Off word `transguard`.

Not needed here: a map memory guard (Layer <= 99), a states fix, item type id hooks (ids aligned in data).

## Summary

21 rows: applies 5 (fixed here 3: C1, C11, C15; plugin part ported 2: C14, C17), already handled 8 (C2, C5, C9, C10, C12, C16,
C20, C21), not applicable 6 (C3, C4, C6, C7, C8, C13), needs game 2 (C18, C19). Game looks still worth doing for handled rows:
C10 (levels 125-127, 137), C11 (the 4 item tooltips), C15 (pets alive), C1 (tree hovers).
