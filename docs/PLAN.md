# Port plan

Target: **Median XL 2012 (v005)** on retail D2R 3.3 build 93847 + D2RLoader 1.3.1 (SDK 0.3.0, ABI 4), extended save format. Display
name "D2R-XL 2012", mod and save folder `mxl2012`, plugin `mxl2012-core`, repo `WerdeGames/mxl2012-d2r`.
The phases follow docs/porting-playbook.md. Median
XL 2012 is plain 1.13c data (no D2Sigma tables, no engine DLL), so phases 1, 3 and 4 are small.
The numbers in the progress column are our own estimate of each phase, not a measurement; the lead agent updates them.

| Phase | What | Progress | Notes |
|---|---|---|---|
| 0 | Setup | 98 % | every item done (toolchain checked by `tools/lane_setup.py` 2026-10-29); left: CI's `assets` job runs only after the owner's asset-pack upload + secret (OWNER-QUESTIONS #28) |
| 1 | Tools | 98 % | full `tools/build.py` runs end to end (lane phase3 rebuild 2026-10-29: 8 min, validate 0 errors); asset pack `assets-1` built and pinned in assets.lock; left: the owner's upload of it (same blocker as phase 0) |
| 2 | Data port | 90 % | all 86 tables migrated, validate 0 errors; boots, all five act towns load; saves round-trip (lane savefmt); D2R additions removed; open bugs left (2026-10-29): #434 (medium, Hratli out of reach) and lows #17, #292, #392, #399, #432, #436, #484, plus the player reports #487-#498 of other lanes |
| 3 | Triage of engine differences | 100 % | every row has an in-game or static verdict (engine-triage.md section 7: same 13, ported 15, unported 2); #16 (`rprunes`), #18 (`cubeclasses`) and #24 (`rpsignets`, lane phase3) confirmed on the player path; #24's Apple needed engine work: plugin part `appleuse` (plugin-plan.md section 25, bug #499, lane apple) |
| 4 | Plugin | 90 % | v0.1 built and in game; first game pass done (all plugin-plan 10.1 checks run, bugs #4 / #5 fixed) and its failures ported (#6 `cltnomis`, #14, #15, #16); later parts (whirlwind, ilvl, runeletter, cubedupe, lvlupui, ...) in. Apple part `appleuse` in (lane apple, bug #499). Left: whirlwind feel by eye (human visual review) |
| 5 | Graphics | 65 % | HD stand-ins (monsters, effects, maps floors, icons, UI) and classic Median art in the build; map walls and custom art open |
| 6 | Test and release | 50 % | game checks in tools/game_checks.py (acts, cube, rules, saves); alpha package tool (tools/cut_alpha.ps1); release scripts and owner server steps ready (docs/hosting.md); 0.1.0 to 0.1.2 published (2026-10-29), downloader with it; public GitHub mirror live; signing and open bugs left |

Overall: roughly 80 % (2026-10-29 evening, lane phase3: phases 0-4 audited; 78 % earlier that day, 72 % on 2026-10-28 evening).

## Phase 0: Setup
- [x] Repo on the forge (private), `.gitignore` forbids game content; public GitHub mirror since 2026-10-29
- [x] Source: Median XL 2012 v005 (provisional: archive.org D2SE/D2GL repack; the ModDB zip to replace it), docs/source-inventory.md, docs/verify-original.md
- [x] Feature list docs/median2012-features.md, engine triage docs/engine-triage.md, plugin plan docs/plugin-plan.md
- [x] Tooling scaffold (tools/, plugin skeleton, downloader, CI, templates), docs/scaffold-notes.md
- [x] Downloader art (owner background; panel and icon from tools/launcher_art/)
- [x] Toolchain on the game PC: CMake, MSVC (VS 18), Python, StormLib / CascLib submodules built (tools/build_native.ps1; since lane
  toolchain one shared build for all worktrees, bug #210, `tools/lane_setup.py`: all parts "ok" on 2026-10-29, lane phase3)
- [x] Game slots 2 and 3 set up for mxl2012 (docs/setup.md; slot 1, the owner's game, usable by name since 2026-10-28)
- [x] CI runner for this repo (`mxl-cross`, own instance on the CI server, 2026-10-28): plugin, launcher, native-tests, tools all pass; the
  `assets` job is written (.forgejo/workflows/ci.yml, tools/ci_assets.sh) and skips until the owner uploads `assets-1` and sets
  `MXL_ASSETS_TOKEN` (OWNER-QUESTIONS #28; docs/setup.md "CI asset pack")

## Phase 1: Tools (Python CLI)
- [x] `tools/mpq_extract.py`, `tools/casc_extract.py` (D2R 93847 baseline), `tools/tbl2json.py`, `tools/validate.py`, `tools/txt_migrate.py` copied
- [x] `tools/tbl2json.py` and the `mxl2012` string namespace (lane strings)
- [x] Original ModDB zip verified (patch_d2.mpq byte-identical to the repack; mxl2012-runs/original-vs-repack.md)
- [x] Extract Median XL 2012's MPQs into the asset pack (`tools/mpq_extract.py`, `tools/asset_pack.py build`): `assets-1`
  from the ModDB original's `patch_d2.mpq`, equal to `extract-mpq`; the build reads `assets/median`. CI `assets` job
  waits for the owner's upload + secret (docs/setup.md, "CI asset pack")
- [x] `tools/txt_migrate.py` adapted to 2012's tables (1.13c layout; specifics of later Median versions removed)
- [x] `tools/build.py` runs end to end (lane boot, 2026-10-28; about 2 min, validate 0 errors both banks). Inputs: MXL_D2R_EXTRACT =
  a D2R 93847 extraction with filelist.txt (machine-local `extract_dir`, read-only), Median's files from MXL_EXTRACT / assets/median /
  mxl2012-runs/extract-mpq (tools/fxpaths.py). `hd_skill_anims.py` needs D2R's player state machines, which that
  extraction lacks: it reads them once from a slot's CASC (MXL_SLOT=2|3, read-only) into work/d2r-cache. `--keep-going`
  reports a failing art step and goes on; every step's output is in work/build-logs/. The plugin builds separately
  (`tools/build_plugin.ps1 -Sdk <PluginSDK> -Release -Tests`).

## Phase 2: Data port
- [x] Migrate the standard tables, merge with D2R's rows, both banks; `tools/install_mod.py` into slot 2 (mods\mxl2012)
- [x] First boot with `-txt`, fix load asserts (lane boot: main menu clean, Act 1 enterable; asserts #6, #7 fixed since)
- [x] Strings: namespace `mxl2012` (docs/strings.md)

## Phase 3: Triage of engine differences
- [x] docs/engine-triage.md (static reading of 1.13c rules against D2R 3.3)
- [x] Confirm each row in game; rows that need engine work go to the plugin plan, the rest to docs/unported.md (engine-triage.md
  section 7; the last three, #16 / #18 / #24, by `rprunes`, `cubeclasses` and `rpsignets`, 2026-10-29; #24's Apple: plugin-plan.md
  section 25, bug #499)

## Phase 4: Plugin (`mxl2012-core`)
- [x] Skeleton: entry, off list, `mxl2012` console command, build guard, other-plugin guard, test harness framework
- [x] v0.1 parts of docs/plugin-plan.md (CltDoWall, empty-slot stubs, dev harness subset)
- [x] First game pass, then per-failure ports (lane boot's partial pass, docs/testing.md "First boot"; harness bugs #4, #5 fixed; full
  pass in docs/testing.md "Harness lane" / "Lane triage" / "Lane pluginplan2"; failures ported: #6 `cltnomis`, #14, #15, #16)
- [x] Apple: 1.13c item spell 10 starts skill 47 (plugin-plan.md section 25, bug #499; found by lane phase3; part `appleuse`,
  lane apple, 2026-10-30)

## Phase 5: Graphics
- [x] Downloader art
- [x] Classic and HD stand-ins for Median-only monsters, missiles, items (tools/gfx_placeholders.py, hd_monsters.py, effects_hd.py)
- [x] Skill tree, inventory and panel art (HD layouts + classic Median art; docs/hd-ui.md, docs/legacy-graphics.md)
- [x] HD walls for the 8 retextured Median maps: D2R's own wall models in Median's layout (tools/walls_hd.py, docs/maps-hd.md; lane walls)
- [ ] Recolour tints and custom art for those maps (Median's retextured look; charismatic's cathedral, downtown's 382 uncovered cells) (last)

## Phase 6: Test and release
- [x] Game checks on slots 2/3 (tools/game_checks.py; lanes boot, harness, datafix, qa)
- [ ] All open bugs in docs/bugs.md triaged/fixed; Warlock in-game check (needs a RotW account)
- [ ] Release package, publish to files.werdegames.com/mxl2012/, downloader signing
- [x] GitHub mirror and issue templates live (2026-10-29: https://github.com/Nugwa628/mxl2012-d2r, public; fresh history, one snapshot commit per mirror run)
