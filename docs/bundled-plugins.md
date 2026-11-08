# Third-party D2RLoader plugins planned to ship with D2R-XL 2012

Planned 2026-11-04. Shipped so far: D2R Legacy 16:9 and Buff HUD (0.1.12), Auto Belt Refill (0.1.15), PyreFly's Controller QOL
Updates (0.1.17); add new candidates to
the tables below. The compatibility work (which plugins
need changes for Median XL 2012's data)
starts after release 0.1.11. Each plugin keeps its author's credit in the release notes, the README credits and this file.

## D2R Legacy 16:9 (our own, shipped from 0.1.12)

[D2R Legacy 16:9](https://github.com/Nugwa628/D2R-Legacy169) (`legacy169.dll`, MIT) is this project's own D2RLoader plugin: the
classic (legacy) graphics widened to the screen: 800x600 shows as 1066x600 and 640x480 as 853x480 on 16:9 (960x600 / 768x480 on 16:10), the side panels sit at the window edges,
the bottom control panel stays 4:3 in the middle. HD is not changed. Owner decision 2026-11-05 (tested by hand on the owner's
PC); lane legacy169ship, docs/testing.md "Lane legacy169ship".

- **In the package:** `mods\mxl2012\d2rloader\plugins\legacy169.dll` (mod-scoped: it loads only with this mod) and its default
  `mods\mxl2012\d2rloader\config\legacy169.toml`. D2RLoader would write that file itself at the first start (the config is
  embedded in the DLL), but the downloader removes files the release does not list, so the package lists it as a `preserve`
  file: written when missing, never overwritten, and a player's `enabled = false` survives Update and Repair. The manifest's
  `bundledPlugins` names the plugin, version, repository and commit.
- **Reproducible build:** the gitlink `third_party/D2R-Legacy169` pins the commit (v0.1.1, `d6fe85d`: v0.1.0 plus #544's fix).
  `tools/build_legacy169.ps1` exports exactly that commit (`git archive`) from the submodule, or from `MXL_LEGACY169_DIR`
  (a local clone, `.mxl-local.json`), builds it with release options (no test harness, no bad-bytes table) against the
  PluginSDK of `tools/build_plugin.ps1` and runs its unit tests. `tools/package_release.py` runs it (or takes `--legacy169
  DLL`) and refuses a test build or another version; `tools/verify_package.py` checks both files are in a player package.
  `--no-data` (CI) packages leave it out unless `--legacy169` is given. To move to a new legacy169 version: update the
  gitlink (`git -C third_party/D2R-Legacy169 checkout <tag>` then `git add third_party/D2R-Legacy169`) and
  `package_release.LEGACY169["version"]`.
- **Turn it off:** `enabled = false` under `[legacy169]` in `legacy169.toml`, then start the game again: the plugin loads
  and patches nothing (the stock 4:3 classic view). Delete `legacy169.dll` to remove it (the downloader puts it back on
  Repair).
- **Next to mxl2012-core:** no shared hook or patched byte (checked in game, docs/testing.md "Lane legacy169ship"). If
  another plugin already changed one of its bytes, legacy169 patches nothing and says so in `d2rloader\logs\legacy169.log`.
  Not checked: a player who also has a game-wide copy (`<game>\d2rloader\plugins\legacy169.dll`, the same plugin id).
- **Test runs:** a dev install (`tools/install_mod.py`) does not install it, so the calibrated legacy click places of
  `tools/game_checks.py` (4:3 with side bars) stay valid. A run on a release install (`tools/release_install.py`) has it:
  legacy-graphics checks there need its `enabled = false`, or the 16:9 places. `graphics_mode()` reads the panel manager's
  HD flag (harness `lvlbtn`) in a game, so G works with it on.

## PyreFly's plugins

By **PyreFly** (<https://github.com/Pyre-Flies/D2R-Mods>). Shipped with PyreFly's permission (given to the project
owner, 2026-11-04). Their READMEs state no licence, so the permission is the basis for shipping them.

| Plugin | What it does | Likely work for Median XL 2012 |
|-|-|-|
| [controller-qol](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/controller-qol/README.md) | Controller shortcuts for item actions, direct ground looting, menu navigation, optional right-stick skill aiming | Skill behaviour is keyed to numeric skill ids with per-mod profiles: needs an mxl2012 profile for our skills |
| [pyre-lootfilter](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/pyre-lootfilter/README.md) | Ground loot filter from `filter.json`, minimap icons, pickup guard | Reads weapons.txt, armor.txt, itemtypes.txt, item codes and stat ids: needs a filter written for Median's items |
| [pyre-stashsearch](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/pyre-stashsearch/README.md) | Search across the Personal and Shared stash pages, boolean stat filters, highlighted matches, renamable side tabs | Check with the mod's 5 / 7 shared pages (`add_shared_tabs`, bug #535) and Median's stat names |
| [item-roll-ranges](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/item-roll-ranges/README.md) | Shows each modifier's possible roll range and source while Ctrl / RT is held | Reads the active game's affixes, uniques and runewords; check against Median's tables and D2RLoader's own Ctrl stat ranges, which the mod enables (`item_stat_ranges = true`, bug #528; some automagic range lines repeat): make sure only one draws |
| [inventory-deposit](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/inventory-deposit/README.md) | "Deposit all gems, materials and runes" button by the inventory gold | Needs the HD advanced stash and its item-type rules; Median items with no slot on the open page stay put (bug #535 side note: such an item logged item asserts) |

All five target D2RLoader 1.3.1 and plugin ABI 4 on Windows x64, the same loader the port uses.

controller-qol audit for this build (version gate, hook conflicts with medtab and Auto Belt Refill, skill profile, plan):
[controller-support.md](controller-support.md) section 3. controller-qol ships from 0.1.17 (next section).

## Controller QOL Updates by PyreFly (shipped from 0.1.17)

[controller-qol](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/controller-qol/README.md) (`Controller QOL
Updates.dll`, version 1.3.1+rev.95) by **PyreFly**: gamepad shortcuts for items (LB + A / X / Y, Deposit All with LB + L3),
direct ground looting (hold LB, LB + a face button), menu, stash-tab and shared-page paging, and right-stick skill aiming with
per-mod skill profiles. **Licence:** PyreFly's repository reserves all rights (its LICENSE); PyreFly gave the project owner
permission to ship and adapt it on 2026-11-04. Credit: README, CHANGELOG / release notes, NOTICE.md and this file (lane
cqol, docs/testing.md "Lane cqol"; research lanes padui and padskills, docs/controller-support.md sections 3 to 7).

- **In the package:** `mods\mxl2012\d2rloader\plugins\Controller QOL Updates.dll` (mod-scoped) with PyreFly's LICENSE
  (`Controller QOL Updates-LICENSE.txt`) and the PluginSDK's (`Controller QOL Updates-PluginSDK-LICENSE.txt`), and the config
  `mods\mxl2012\d2rloader\config\controller-qol-updates.toml` as a `preserve` file (a player's changes survive Update and
  Repair). The manifest's `bundledPlugins` names it with version, repository, path, author, commit and the patch checksums.
- **Reproducible build, no fork:** the gitlink `third_party/D2R-Mods` pins PyreFly's repository at `df44457` (2026-10-30, still
  the newest commit on 2026-11-08). `tools/build_controllerqol.ps1` exports `plugins/controller-qol`,
  `plugins/inventory-deposit/src` and `/tests` (its build reuses the stash feedback from there) and `LICENSE` of that commit
  (`git archive`, from the submodule or `MXL_CONTROLLERQOL_DIR`), applies `third_party/controller-qol-mxl2012/*.patch` in name
  order, builds it with PyreFly's own CMakeLists.txt against the PluginSDK of `tools/build_plugin.ps1` and runs its 63 unit tests.
  **SDK pin:** PyreFly pins `bb0b48e`, ours is `717f727`, one commit later, which changes only comments and the README; the plugin
  builds against ours with no change. A system code page other than UTF-8 (932 on the build PC) needs `/utf-8` (set by the script). `tools/package_release.py`
  generates the skill seed from the package's `skills.txt`, runs the script with `-SkillProfile` (or takes `--controllerqol
  DLL`) and refuses a build of another commit, patch set or seed, another version, or PyreFly's own DLL (no `belt_actions`
  switch); `tools/verify_package.py` checks all four files in a player package. `--no-data` and `--no-bundled` packages leave
  it out (the seed needs the data). To move to a new upstream commit: update the gitlink, refresh the patches
  (`third_party/controller-qol-mxl2012/README.md`), refresh `tools/data/controller_qol_catalog.json` against its
  `skill_catalog.h`, run the in-game check `cqol`.
- **Patches** (`third_party/controller-qol-mxl2012/`): `0001-mxl2012-belt-actions-switch.patch`, a `belt_actions` key (default
  true as upstream; our config false): its belt module stays off, so **Auto Belt Refill keeps the belt** (owner ruling
  2026-11-07). `0002-mxl2012-median-orbs-tabs.patch`: the stash's tabs 5 / 6 are MEDIAN / ORBS (advanced tabs whose slots sit
  under the Runes page; Median's code characters in slot names), so Deposit All and LB + X work there instead of being refused or
  treated as Runes. `0003-mxl2012-hooked-sound-entry.patch`: our `spiritsound` part (bug #502) hooks the entry of D2R's client
  sound play `0x1a0780`, which controller-qol checks before Deposit All, advanced LB + X and Materials withdrawals; the check now
  admits the hooked entry when the bytes after the 13 the hook replaces match (without it every LB + L3 was refused and fell
  through to D2R's own L3, Open Cube).
- **Next to mxl2012-core:** medtab no longer patches inside the tab getter `0x23af50` (its 21 callers go through a stub in the
  pad after it), so controller-qol's check of the getter's first 128 bytes passes and none of its features is declined
  (`controller-qol-updates.log`); `spiritsound`'s hook at `0x1a0780` is admitted by patch 0003; tabflash's hook of `0x15ef70`
  turns off only controller-qol's own tab flash after Deposit All (one warning a session, the deposit works); pickup and
  cube_dupe share code paths with it but no bytes. Open: #558 (engine asserts when the stash is clicked open with it loaded); `mxl2012`: "plugin clashes: none". Our harness `pad` (dev builds) feeds D2R's XInput import; controller-qol
  reads the pad from D2R's own controller events, so the scripted pad reaches it.
- **Skill profile:** `tools/controller_skill_profile.py` (lane padskills, docs/controller-support.md section 5) makes the
  mxl2012 seed (818 skills, about 33 KB) from the final `skills.txt` / `skilldesc.txt`; the build embeds it in place of
  PyreFly's vanilla `skill-defaults.toml`. At the first start the plugin writes the player's profile
  `d2rloader\config\controller-qol-skills\<scope>.overrides.toml` (the scope is a hash of the install's mod folder) from it,
  and later only adds keys that are missing: R3 choices and hand edits are never replaced, by Update and Repair neither (the
  downloader does not list that folder).
- **Turn it off:** `enabled = false` under `[qol]` and under `[aim]` in `controller-qol-updates.toml`; delete the DLL to remove it
  (the downloader puts it back on Repair).
- **Test runs:** a dev install (`tools/install_mod.py`) does not install it; the run's driver places the DLL and config for a
  run (docs/testing.md "Lane cqol"); a release install has it.

## Buff HUD by Lukaszpg (shipped from 0.1.12)

[d2rl-buff-hud](https://github.com/Lukaszpg/d2rl-buff-hud) by **Lukaszpg** (MIT licence, copyright Lukaszpg): a 3x7 panel
of the player's timed buffs above the skill bar, with a countdown and the buff's name on hover. Version 1.1.0 loads with the
mod but shows "?" icons and no names on Median's tables and breaks in legacy graphics (tested 2026-11-04). We ship our fork
[Nugwa628/d2rl-buff-hud](https://github.com/Nugwa628/d2rl-buff-hud), branch `mxl2012`: the four generic fixes offered back to
Lukaszpg (pull requests #10 widget rebuild after G, #11 icon / name overrides per row, #12 legacy layout, #13 item pictures),
Lukaszpg's own hover-name pull request #6 merged with his commits kept, and on that branch only (owner rule: nothing about
Median XL 2012 goes upstream) the buff list for Median's states (`buff-hud.txt`, `buff-hud-display.txt` inside the
companion MPQ), the elixir pictures, a `buff-panel.toml` on / off switch, and hover names that work under D2RLoader 1.3.1
(it returns the authored, unresolved rects of the panel, so the fork takes the UI screen from the game: 2160 units high in
HD, `ScreenSizeX` x `ScreenSizeY` in legacy), also while the game window is in the background, without D2's colour codes.
`buff-panel status` names the label under the cursor. Lane buffship, docs/testing.md "Lane buffship".

- **In the package:** `mods\mxl2012\d2rloader\plugins\d2rl-buff-panel.dll` (mod-scoped) with its companion
  `d2rl-buff-panel.mpq` (layouts and the Median buff list), the fork's MIT licence with Lukaszpg's copyright
  (`d2rl-buff-panel-LICENSE.txt`) and the licence of the PluginSDK it links (`d2rl-buff-panel-PluginSDK-LICENSE.txt`), and the
  default `mods\mxl2012\d2rloader\config\buff-panel.toml` as a `preserve` file (as `legacy169.toml`: a player's
  `enabled = false` survives Update and Repair). The manifest's `bundledPlugins` names it with version, fork, upstream,
  author and commit.
- **Reproducible build:** the gitlink `third_party/d2rl-buff-hud` pins the fork commit (branch `mxl2012`).
  `tools/build_buffhud.ps1` exports exactly that commit (`git archive`, files as committed, so the MPQ has the same bytes on
  any machine) from the submodule or from `MXL_BUFFHUD_DIR` (a local clone, `.mxl-local.json`), exports the PluginSDK commit the
  fork pins from the PluginSDK of `tools/build_plugin.ps1`, and runs the fork's own `scripts\build.ps1` (release preset, its
  16 tests) and companion pack. `tools/package_release.py` runs it (or takes `--buffhud DLL`, the MPQ next to it) and refuses
  a build that is not our fork (no embedded `buff-panel.toml`), another version or a missing / unpacked MPQ;
  `tools/verify_package.py` checks all five files are in a player package. `--no-data` (CI) and `--no-bundled` (unit tests)
  packages leave it out. To move to a new fork commit: push it to the fork, `git -C third_party/d2rl-buff-hud checkout
  <commit>` then `git add third_party/d2rl-buff-hud` (and `package_release.BUFFHUD["version"]` for a new version).
- **Turn it off:** `enabled = false` under `[buff_panel]` in `buff-panel.toml`, then start the game again: the plugin loads,
  logs it and starts nothing (no panel, no hook). Delete the DLL to remove it (the downloader puts it back on Repair).
- **Next to mxl2012-core (and legacy169):** no hook refused (`mxl2012`: `plugin clashes: none`), checked in game in HD and
  legacy (docs/testing.md "Lane buffship").
- **Hides with big panels (fork, lane buffhide):** `hide_with_panels = true` (the default; a `buff-panel.toml` without the
  key keeps it) hides the icons while the stash or the Horadric Cube is open, in HD and legacy (owner decision 2026-11-05:
  in legacy they covered the stash's corner and close button), and shows them again when it closes. A side panel
  (character, quests, waypoints, vendor / trade, mercenary, party on the left; inventory and skill tree on the right) hides
  them only while it covers an occupied icon slot, so a player can still fight with the inventory open: in legacy (also
  with legacy169 at 16:9 and 16:10) every left panel covers the first icon and a right panel the sixth (16:10) or seventh
  (16:9) one; in HD the panels end above the grid and only the top row's seventh icon reaches a right panel.
  `hide_with_panels = false` keeps them shown always. `buff-panel status` reports `hiddenBy=<panel>`, `buff-panel panels`
  which native panels are open. docs/testing.md "Lane buffhide".
- **Icons for buffs without one (fork, lane bufficons):** Median XL 2012 gives some buff skills no icon (skilldesc
  `IconCel` 0 of the shared sheet, the "?" picture). `buff-hud-display.txt` points those rows at a frame of the mod's own
  skill icon sheets (Median's art, built from the game data into the mod, never in git): Elemental Fury (state 31) druid
  frame 20 (Elemental), Blades Of Light (81) sorceress 56 (Bladestorm), Superbeast Neutral (178) paladin 54 (Superbeast),
  Mark Of The Bear (190) druid 50 (an unused bear frame) and Mark Of The Wolf (191) druid 6 (an unused wolf-head frame).
  Class sheets have the same frames in HD and legacy, so one row serves both. The two Marks are D2R's own item-effect
  rows that no Median skill or item grants, so only the other three were seen in game. Rows that still use global frame 0: Lightning
  Enchant (222), Cold Enchant (223), Shadowform (232), Lifeblood (240), Elixir of Power (241, shows its item picture),
  Stamina Potion (271, item picture) and Cow Disguise (301). docs/testing.md "Lane bufficons".
- **Test runs:** a dev install (`tools/install_mod.py`) does not install it; a release install does.

## Auto Belt Refill by jaycachou-svg (shipped from 0.1.15)

[Auto Belt Refill](https://github.com/jaycachou-svg/auto-belt-refill) (v0.35.9) by **jaycachou-svg**: refills the potion belt
from the inventory, automatically after a drink and in one go on a key (`belt-fill` console command), with a per-column list
of potion codes. **Licence:** the repository has no licence file; jaycachou-svg gave permission on 2026-11-06 to use and
customise it. Credit: README, CHANGELOG / release notes, NOTICE.md and this file (lane beltship, docs/testing.md
"Lane beltship"; the research was lane beltrefill).

- **In the package:** `mods\mxl2012\d2rloader\plugins\d2rl-auto-belt-refill.dll` (mod-scoped) and our config
  `mods\mxl2012\d2rloader\config\auto-belt-refill.toml`, a `preserve` file like legacy169's (a player's changes survive Update
  and Repair). The manifest's `bundledPlugins` names it with version, repository, author, commit and the patch checksums.
- **Reproducible build, no fork:** the gitlink `third_party/auto-belt-refill` pins the author's repository at `a3b6805` ("Add
  Auto-belt-refill-v0.35.9"). `tools/build_beltrefill.ps1` exports folder `Auto-belt-refill-v0.35.9-EN` of that commit (`git
  archive`, from the submodule or `MXL_BELTREFILL_DIR`), applies `third_party/auto-belt-refill-mxl2012/*.patch` in name order and
  builds it with our `CMakeLists.txt` there (the author's lists the sources next to it, the repo keeps them in `src/`) against
  the PluginSDK of `tools/build_plugin.ps1`. It records `PINNED_COMMIT` and `PATCHES` (sha256 + name) in `build/beltrefill-src`;
  `tools/package_release.py` runs it (or takes `--beltrefill DLL`), refuses a build of another commit or patch set, another
  version and the author's prebuilt DLL (older D2RLoader ABI); `tools/verify_package.py` checks both files in a player package.
  The upstream plugin has no unit tests; our additions' pure logic (`belt_match_logic.h`) has `BeltMatchTests`
  (`third_party/auto-belt-refill-mxl2012/tests/`), built and run by `tools/build_beltrefill.ps1`. To move to a new upstream version: update the gitlink, refresh the patches, run the in-game
  check below.
- **Patches:** `0001-pluginsdk-1.3.1.patch`, API renames for D2RLoader 1.3.1 / ABI 4 (`abiVersion`, `InventoryService`,
  `ThreadService`, `InputService`, `LifecycleService`, the one-argument `QueryService`), no behaviour change.
  `0002-mxl2012-belt-rows.patch`, the Median belt sizes (next point). `0003-mxl2012-match-first-slot.patch`, our behaviour
  for D2R-XL 2012 (lane beltmatch, owner request 2026-11-06), each part off unless the config turns it on:
  - `match_first_slot`: each column refills with exactly the item code in its first (bottom) slot; no families, no
    `prefer_large`, and no "follow the game" extension of a column's list. Upstream has no such mode: an unlocked column learns
    the whole family of its first-row potion (hp5 > hp4 > ... with `prefer_large`), and the fill adds any code the game routes
    into a non-empty column. A **completely empty column refills nothing** until the player puts a potion there (owner decision
    2026-11-06; no remembered type). An empty first slot under items still in the column keeps the code.
  - `never_refill`: codes never learned or refilled, also from a column's bottom: Median's elixirs (`ey1`-`ey9`, `eo7`-`eo9`,
    `et1`, `0g0`-`0g8`) and the Goodberry `b@b` (#541).
  - `belt_counts`: a count on the top right of each column's first cell, how many items of that column's code the inventory and
    the belt hold together (white, red at 0; none on an empty or elixir column), drawn with D2RLoader's `OverlayService`.
    The cells come from D2R's own layouts (`hudpanelhd.json`: HUD anchored bottom centre in a 2160-high UI space, belt cell 98,
    pitch 125; `hudpanel.json`: the classic screen letterboxed, belt at the centred middle part, cell 29, pitch 31); HD or legacy
    from D2R's getter `0x846210` (bytes checked), the classic screen size from `0x22a0d68` / `0x22a0d6c`. The watcher refreshes
    the counts every `auto_poll_frames`; out of a game they are hidden. Console `belt-counts` logs them, the cells and the
    overlay's frame / draw counters.
  - **Known limit (D2R):** the game routes a potion by item type, not by code. Two columns of one kind (say `hp3` and `hp5`)
    both short: the game offers the first of them to either code; the plugin never puts the wrong potion there, so while that
    column has room and no potion of its own is left, the other column waits (in game: `hp5` in the inventory, `hp3` column
    short and no `hp3` left, the `hp5` column stayed one short).
- **Belt rows (the author's caveat).** The plugin takes the rows per column from the worn belt's code (`RowsForBeltCode`: D2R's
  `lbl` / `vbl` 2, `mbl` / `tbl` 3, anything else 4). Median XL 2012 keeps D2R's `belts.txt` (same 14 rows and box counts), but
  none of its 35 belts uses a D2R code, and the size goes by grade, not by name (`armor.txt` `belt`): grades 1-3 (`627`-`631`,
  `673`-`677`, `719`-`723`) belts.txt sash / light belt, 8 slots; grades 4-5 (`765`-`769`, `811`-`815`) belt / heavy belt, 12;
  grade 6 (`857`-`861`) and Sacred (`@28`-`@32`) girdle / uber belt, 16. Uniques and sets use these bases. Unpatched, every
  Median belt read as 4 rows (in game with `627`: "rows per column = 4"); the moves still came out right only because the
  game refuses slots the belt lacks. `0002` lists the 2- and 3-row codes. The note for the author (and a mod-independent
  fix: the worn item's `belt` column into `belts.txt` `numboxes`) is in `third_party/auto-belt-refill-mxl2012/README.md`.
- **Config:** `match_first_slot = true`, `belt_counts = true`, the elixirs and the Goodberry in `never_refill`, no
  `[columnN]` sections (fixed columns are still possible with `match_first_slot = false`, as the file's comment shows),
  `fill_key` / `snapshot_key` unbound (players bind Refill Belt / Snapshot Belt Columns under Options > Controls),
  `debug_logs = false`. Lane beltship's locked life / mana columns are gone (owner, 2026-11-06).
- **In game (lane beltship, slot 2, HD and legacy):** belts `627` (2 rows), `767` (3), `859` (4) and none (1): `belt-fill`
  filled exactly the belt's slots (life in columns 1 / 3, mana in 2 / 4), auto-refill topped up after drinking keys 1 and 2,
  the plugin reported the right rows, `ey2` / `b@b` / `0g1` never left the inventory, and the game's own slot search refused an
  `ey2` for a life column with a free slot (#541 fixed). No hook refused, no new engine assert, no crash file.
- **In game (lane beltmatch, slot 2, HD and legacy, docs/testing.md "Lane beltmatch"):** columns `hp3` / `mp5` / `hp5` / `mp3`
  refilled with exactly their codes, `hp4` / `mp4` / `hp1` / `ey2` / `b@b` never moved, an emptied column stayed empty with its
  potion back in the inventory, an `hp4` put there made it an `hp4` column, an `ey2` at a column's bottom was not refilled;
  counts 7 / 7 / 6 / 6 and 6 / 6 / 5 / 5 after drinking. The counts are drawn (overlay counters) at cells that match the
  belt in the screenshots, but **no capture of a background window shows the loader's overlay** (PrintWindow and Windows
  Graphics Capture; a full-width test bar was missing too), so the look is still to be checked by hand.

Research of lane beltrefill (2026-11-05, v0.35.8 / v0.35.9):

- **Addresses.** v0.35.8 inline-hooks GetFreeBeltSlot `0x3862d0`, CanPutInBelt `0x15a110`, BeltTransfer `0x15f660` and
  Pickup `0x471950`, each behind a 32-byte entry check, and calls eight more game functions directly (`0x8b2d0`,
  `0x9a480`, `0x34a360`, `0x34a500`, `0x34b9d0`, `0x388c10`, `0x38aba0`, `0x36ef50`). All twelve sit at the same addresses in
  93847: the four entry patterns match the 93847 dump byte for byte, and the game loaded all four hooks in game. The
  console command `belt-verify` reports "bytes differ" for all four. That is a false alarm: it compares the bytes after
  the plugin's own hooks have patched them.
- **Next to mxl2012-core.** mxl2012-core hooks none of these entries (its 28 inline hooks are elsewhere) and its plugin
  guard does not list this plugin. No hook was refused and there was no new crash or engine assert (only the exit-only pool
  checks). v0.35.9 (same repository) drops the hooks on `0x3862d0` and `0x471950` and calls them directly. That version
  is the one to ship: a later hook of ours (for example a #541 fix on the belt routing) would then not clash with it.
- **SDK.** The source is written for an older PluginSDK (`apiVersion`, `*ServiceV1`). The project's SDK (D2RLoader
  1.3.1, ABI 4) needs renames only: `abiVersion` / `D2RL_PLUGIN_ABI_VERSION`, `InventoryService`, `ThreadService`,
  `InputService`, `LifecycleService` and the one-argument `QueryService`. With them both versions build with no warning.
  We tested our build, not the author's DLL.
- **In game (slot 2).** With a test column config (columns 1-3 as shipped, column 4 `ey2`), the manual fill (`belt-fill`) filled all 16 slots per column
  (life, mana, life, Elixir of Experience). Auto-refill topped up a drunk slot from the inventory within one poll. Median
  items that no column lists (Elixir of Greed, Greater Elixir of Experience) were never moved.
- **Median-only potions.** Every Median elixir (`ey1`-`ey9`, `eo7`-`eo9`, `et1`, `0g0`-`0g8`) and the Goodberry `b@b`
  is item type `hpot`, like the healing potions. D2R's own belt routing, which the plugin uses, puts them into any life
  column that has room (bug #541). An unlocked column then adds the routed code to its memory ("column memory extended
  to follow the game"). Measured: a life column learned `ey2` and refilled with an Elixir of Experience, and the elixir
  column learned `hp5`. With `locked = true` the plugin refuses such routes, so columns keep their exact lists (checked in game with v0.35.9).
  `rvs` / `rvl` are not spawnable in Median. The #541 fix planned in lane beltstack is data only (each non-classic belt
  potion gets its own item type), and the plugin matches item codes, never item types, so it needs no change for it.

## Checks before shipping (after 0.1.11)

- Each plugin loads next to mxl2012-core without hook conflicts, in HD and in legacy graphics.
- The mod-specific data (controller skill profile, loot filter, deposit item types) is written for Median XL 2012.
- Item-roll-ranges vs D2RLoader's stat ranges (on in the mod, #528; some automagic range lines repeat): only one may draw.
- The installer and the Downloader install them into `mods\mxl2012\d2rloader\plugins\`, pinned by checksum like D2RLoader.
- Release notes and README credit PyreFly, Lukaszpg (Buff HUD: done in 0.1.12) and jaycachou-svg (Auto Belt Refill: done for 0.1.15).
