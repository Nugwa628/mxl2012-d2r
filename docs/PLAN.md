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
| 2 | Data port | 99 % | all 86 tables migrated, validate 0 errors; boots, all five act towns load; saves round-trip (lane savefmt); D2R additions removed; RotW stash tabs take runes / gems (#510, 0.1.4); saves no longer cancelled by a retail save format (#512: plugin part savemode + downloader 0.1.1, 0.1.5). Old unreproduced lows #17, #392, #432 closed (owner). Left: whatever Acts 2-5 play turns up |
| 3 | Triage of engine differences | 100 % | every row has an in-game or static verdict (engine-triage.md section 7: same 13, ported 15, unported 2); #16 (`rprunes`), #18 (`cubeclasses`) and #24 (`rpsignets`, lane phase3) confirmed on the player path; #24's Apple needed engine work: plugin part `appleuse` (plugin-plan.md section 25, bug #499, lane apple) |
| 4 | Plugin | 90 % | v0.1 built and in game; first game pass done (all plugin-plan 10.1 checks run, bugs #4 / #5 fixed) and its failures ported (#6 `cltnomis`, #14, #15, #16); later parts (whirlwind, ilvl, runeletter, cubedupe, lvlupui, ...) in. Apple part `appleuse` in (lane apple, bug #499). Left: whirlwind feel by eye (human visual review) |
| 5 | Graphics | 95 % | HD stand-ins (monsters, effects, map floors, icons, UI), classic Median art, HD walls on all 17 Median maps, map light colours, Rainbow Stones in D2R HD art (0.1.4); 0.1.5: Khalimgrad cathedral's arches and Fortress huts, downtown's trees, 43 more item pictures, 8 better monster stand-ins; 0.1.6: 4 more stand-ins, Rathma as the Oblivion Knight; 0.1.7: own HD pet icons (#514), skill-tree pages in D2R HD style. Left: Median's runes (redrawn signs held back by the owner), ~45 upscaled item pictures (21 redrawn, held back), the cathedral's tall pointed arch and long roofed walls (no D2R model), Ancient Tunnels void (drawn as floor), Judgement's white core (#481), RotW stash pages in classic mode (#516, built, off: crashes without RotW) |
| 6 | Test and release | 91 % | game checks in tools/game_checks.py; alpha package and release scripts; 0.1.0 to 0.1.7 published (stable 0.1.7, 2026-10-31), downloader 0.1.1, public GitHub mirror and releases; #511 / #292 (area change with a mercenary) and #509 fixed; Acts 2-5 Normal sweep with a mercenary done (lane acts25: no crash in play, 33 of 37 entries by click; #517 one failed start). Left: Nightmare / Hell sweep, the two Kurast temple entries (81->97, 82->99), #481 decision, Warlock in play and RotW stash test (need RotW), downloader signing |

Overall: roughly 96 % (2026-11-01, after 0.1.10 and 0.1.9; 95 % after 0.1.8 and 0.1.7, 94 % after 0.1.5, 92 % after 0.1.4, 80 % on 2026-10-29 evening, 72 % on 2026-10-28 evening).

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
- [x] Median's look for those maps: no recolour needed (the retextures keep the donors' colours); each map gets its own coloured key light like legacy mode (tools/map_tint.py, docs/maps-hd.md "Median's look"; lane maptint)
- [ ] Custom art for those maps: charismatic's cathedral arches and roofs, downtown's 126 Harrogath cells (orientation 14) without an HD wall (last)

## Phase 6: Test and release
- [x] Game checks on slots 2/3 (tools/game_checks.py; lanes boot, harness, datafix, qa)
- [ ] All open bugs in docs/bugs.md triaged/fixed; Warlock in-game check (needs a RotW account)
- [x] Release package, publish to files.werdegames.com/mxl2012/ (0.1.0 to 0.1.4)
- [ ] Downloader signing
- [ ] Ship PyreFly's plugins with the mod (controller-qol, pyre-lootfilter, pyre-stashsearch, item-roll-ranges,
  inventory-deposit),
  adapted to Median XL 2012 where needed: docs/bundled-plugins.md (after 0.1.11)
- [x] Release 0.1.12 (2026-11-05, owner list of 2026-11-05):
  - [x] Barbarian spirits: stricter fight rule (target within 25 of the owner, at most 4 s; lane spiritfight, #534)
  - [x] Ship the D2R Legacy 16:9 plugin (lane legacy169ship)
  - [x] Ship Buff HUD by Lukaszpg (our fork, branch `mxl2012`: Median buffs, legacy, elixir pictures, hover names; lane
    buffship)
  - [x] Median XL potions (experience, greed, ...) no longer stack onto life / mana potions in the belt (#541, lane beltstack)
  - [x] Does life / mana leech work? (#540, lane leech: yes, as Median)
  - [x] Act 4 Heretics: an HD model that can be seen (#542, lane heretic)
  - [x] Research: stackable shrines, new runes, new potions (lane stackres): [stacking-research.md](stacking-research.md)
  - [x] Median's runes r34-r56 and its 25 gems stack in the RotW stash's Runes / Gems pages, HD and classic (owner
    2026-11-05, lane medstash; stacking-research.md section 4)
  - [x] Research: does D2R's inventory auto sort work with the mod, or could it (lane autosort):
    [docs/autosort-research.md](autosort-research.md). Controller only ("Hold to Sort"); nothing for mouse and keyboard;
    our own plugin part would take about 5-6 days
  - [x] Research: a death report (who hit the player for how much, up to the death) (lane deathlog; design in
    [death-report-research.md](death-report-research.md), feasible: one read-only hook on D2R's apply-damage `0x44ce80`)
- [x] Release 0.1.13 (2026-11-06):
  - [x] "Send to stash" button in the empty cell under the inventory (owner's answers 2026-11-05; lane sendstash, plugin part
    `sendstash`, docs/testing.md "Lane sendstash"): backpack items with a RotW stash slot go into it, full slots stay, one chat
    line; greyed in classic / expansion games and for joiners (joiners stay off until a two-instance test)
  - [x] Akara's respec unlimited up to level 100, D2R's one per difficulty above (owner 2026-11-05, lane akararespec;
    plugin part `akararespec`, plugin-plan.md section 31)
  - [x] use D2RLoader's Transmute Horadric Cube (documented)
  - [x] The RotW stash cube window shows the cube's items again on a matching 10 x 8 grid (owner 2026-11-05, lane cubewindow, #515)
  - [x] Legacy graphics dim the RotW-only stash slots (#546); Buff HUD hides behind open panels; five new buff icons
- [ ] Later: death report panel on the death screen (last 30 s, Copy button, nothing saved; owner 2026-11-05,
  [death-report-research.md](death-report-research.md) section 6)
- [ ] Release 0.1.14, to look into (owner 2026-11-06; no work yet):
  - [ ] Ship jaycachou-svg's Auto Belt Refill plugin if its author agrees (docs/bundled-plugins.md; lane beltrefill)
  - [ ] A "Median XL" stash tab for shrines, elixirs, signets, crystals, oils: designed and probed
    (option D, MEDIAN and ORBS tabs, Vanilla/Median selector in Materials), not built; waits for the owner's go
    ([median-stash-tab.md](median-stash-tab.md))
  - [ ] Transition immunity
    ([D2R-Tools/plugins/transition-immunity](https://github.com/Nugwa628/D2R-Tools/tree/main/plugins/transition-immunity)):
    check that it works first, then maybe build it into the mod in some form instead of shipping the plugin
  - [ ] MapSense
    ([RuffnecKk-D2RLoader-Suite/plugins/mapsense](https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite/tree/main/plugins/mapsense)):
    probably not all of its features; decide which ones we want
- [x] GitHub mirror and issue templates live (2026-10-29: https://github.com/Nugwa628/mxl2012-d2r, public; fresh history, one snapshot commit per mirror run)
