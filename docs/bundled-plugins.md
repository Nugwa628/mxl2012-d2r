# Third-party D2RLoader plugins planned to ship with D2R-XL 2012

Planned 2026-11-04. Shipped so far: D2R Legacy 16:9 and Buff HUD (0.1.12), Auto Belt Refill (0.1.15), PyreFly's Controller QOL
Updates (0.1.17), CharmInv by Dimentio (0.1.19), Damage Overflow Fix by CelestialRayOne, Enemy Health Bars by Graxy_TV and
Floating Damage by RuffnecKk (0.1.25), and Monster Display by CelestialRayOne and Vendor Stock Refresh by RuffnecKk (0.1.27); add new candidates to
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
  embedded in the DLL), but the downloader removes our files the release does not list, so the package lists it as a `preserve`
  file: written when missing, never overwritten, and a player's `enabled = false` survives Update and Repair. The manifest's
  `bundledPlugins` names the plugin, version, repository and commit.
- **Reproducible build:** the gitlink `third_party/D2R-Legacy169` pins the commit (v0.1.2, `c1ec651`: v0.1.1 plus the game-build tie removed, D2R 3.4).
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
`buff-panel status` names the label under the cursor. Lane buffship, docs/testing.md "Lane buffship". From fork 1.2.0 the
name is the panel's own `HoverName` text widget, drawn by the game: 1.1.0 drew it in D2RLoader's overlay layer, which
players did not see over the game (and which a screenshot of the window does not hold either).

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
- **Harmful effects, moving the icons, legacy size (fork 1.2.0, lane buffhud):** `display_type = debuff` rows of
  `buff-hud.txt` (22 rows: curses such as Amplify Damage, Decrepify, Lower Resist, Blood Mana, Terror, Nightmare, Dazzle,
  Doom; poison, burning, freeze, chill, stun, slow and others, each pointed at a fitting existing icon in
  `buff-hud-display.txt`) read the state's own stat list on the player and show in a second group of 14 slots by the
  mana globe, with a red frame (`debuffframe`), a timer when the list carries an end frame, and the name on hover. Buffs
  keep 21 slots by the life globe. Left Ctrl + left drag on an icon moves its group (the game window is subclassed; the
  grabbing click and the moves while dragging never reach the game, a click without Ctrl still walks). Each group's
  top-left corner is saved in `buff-panel.toml` as a share of the UI screen (`hd_buffs_x` / `_y`, `hd_debuffs_x` / `_y`,
  `legacy_buffs_x` ... ; `-1` = the default spot), clamped to the screen, so it survives a restart and a resolution
  change. `reset_buffs` / `reset_debuffs = true` put a group back at the next start (the plugin writes them back as
  `false`); the console command `buff-panel reset [buffs | debuffs]` does it at once. Legacy icons are 24 px (half size,
  `small/` sheets in the companion MPQ, made from this mod's built pictures by the fork's `scripts/make_companion_art.py`,
  which `tools/build_buffhud.ps1` runs before packing; they are not in the fork's git) with a smaller timer and name
  font; HD is unchanged. The panel moves through D2R's own widget setters (fingerprinted; on a mismatch the debuff
  group, the hover name and moving stay off and the log says so). docs/testing.md "Lane buffhud".
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
  `0002-mxl2012-belt-rows.patch`, the Median belt sizes (next point). `0004-mxl2012-count-signatures.patch`, the counts' game
  data found by signature (`belt_counts` below). `0006-mxl2012-counts-as-hud-text.patch`, the counts as D2R's own HUD
  text in boxes of the mod's HUD layouts instead of the loader's overlay (`belt_counts` below, bug #613).
  `0007-mxl2012-column-counts-and-reserve.patch`, the count of each belt column itself and the inventory reserve beside it
  (`belt_counts` below). `0005-refill-natives-by-signature.patch` (written so it can go to the author):
  the twelve game routines the refill drives (`GetLocalPlayer`, `GetLocalDataContext`, `GetUnitInventory`, `GetUnitType`,
  `GetItemData`, `GetFirstItem`, `GetNextItem`, `GetItemCode`, `GetFreeBeltSlot`, `CanPutInBelt`, `BeltTransfer`, and
  `Pickup`, which only `belt-verify` reports) are found at load by byte signatures in `.text` (new `belt_natives.h`, the
  repo's scan in `invtabs/src/invtabs_logic.h`) instead of the author's fixed RVAs. Each must match exactly once, its target
  must lie in `.text` and be distinct, and it is cross-checked: getters taken from a caller site must have their own entry
  bytes, and the calls inside the match must reach routines already found (`GetLocalDataContext`'s caller hands it to
  `GetLocalPlayer`, `CanPutInBelt` starts with both, `GetNextItem`'s loop starts with `GetFirstItem`). A missing required
  routine logs `natives: OFF - pattern ...`: nothing is hooked or called and fill / auto / place report "natives not
  resolved". The two inline hooks take the routine's own first 32 bytes once its signature matched. The load log lists every
  address (`natives: patterns resolved: ...`); `belt-verify` prints them. `BeltMatchTests` with `D2R_DUMP` checks all twelve
  against the 93847 addresses. `0003-mxl2012-match-first-slot.patch`, our behaviour
  for D2R-XL 2012 (lane beltmatch, owner request 2026-11-06), each part off unless the config turns it on:
  - `match_first_slot`: each column refills with exactly the item code in its first (bottom) slot; no families, no
    `prefer_large`, and no "follow the game" extension of a column's list. Upstream has no such mode: an unlocked column learns
    the whole family of its first-row potion (hp5 > hp4 > ... with `prefer_large`), and the fill adds any code the game routes
    into a non-empty column. A **completely empty column refills nothing** until the player puts a potion there (owner decision
    2026-11-06; no remembered type). An empty first slot under items still in the column keeps the code.
  - `never_refill`: codes never learned or refilled, also from a column's bottom: Median's elixirs (`ey1`-`ey9`, `eo7`-`eo9`,
    `et1`, `0g0`-`0g8`) and the Goodberry `b@b` (#541).
  - `belt_counts`: two numbers per column, as D2R's own HUD text (nothing on an empty or elixir column). How many items that
    belt column holds (`0007-mxl2012-column-counts-and-reserve.patch`; 0006 showed the code's inventory and belt total), on
    the column's bottom-row cell, right-aligned on the hotkey letter's line: white, red at 1 or 0 (`BeltMatch::LowCount`;
    with the refill on a column only drops below full once the inventory has none of its potion left). The bottom row is the
    one that stays in place when the belt opens (the others pop up above it), so the counts show with the belt closed and
    open. And the reserve, "+N" = the column's code in the inventory (what the refill takes from; two columns of one code
    show the same reserve): in HD a row just above the belt's rim, centred on each column, pale gold, before the belt in the
    panel so an opened belt covers it; in legacy at the top right of the bottom-row cell, since the classic mini panel sits
    above the belt's first two columns and the right skill button right of the belt (there is no room for one line beside
    the fourth slot in either HUD). Since `0006-mxl2012-counts-as-hud-text.patch` (bug #613): the mod's HUD layouts carry
    twelve empty text boxes, `MxlBeltCount0`-`3` (white), `MxlBeltCountLow0`-`3` (red) and `MxlBeltReserve0`-`3`, by the
    belt (`tools/ui_layouts.py` `hud_hd` / `hud_controller` / `hud_classic`: `hudpanelhd.json` 34 pt on the 98-pixel cell
    and 30 pt above it, the gamepad `controller/hudpanelhd.json` at its own belt, the legacy `hudpanel.json` in its "Middle"
    part with the classic font). The plugin finds D2R's UI root, panel lookup, child lookup and text setter by the repo's signatures
    (`invtabs/src/summary_natives.h`, the same functions as the dev menu and the charm summary: 93847 `0x3440170`,
    `0x89f760`, `0x855c90`, `0x86dd50`), and the watcher queues a UI-thread pass after each refresh that sets only the texts
    that changed (all of them once a second and for a new HUD: G between HD and legacy rebuilds it). A fault in that pass
    turns the counts off (`counts: off (a fault in the UI pass)`), the refill goes on. Before 0006 the counts were drawn with
    D2RLoader's `OverlayService`: the plugin's draw calls all succeeded but nothing reached the screen (as for the dev menu's
    overlay text, bug #567), so players saw no count (#613). HD or legacy and the classic screen size are still found by
    signature (`0004-mxl2012-count-signatures.patch`, D2R's HD test `0x846210`, the screen-size function `0x7f4d0`), now
    only for `belt-counts`' report. A signature that does not match exactly once logs `belt_counts: OFF - pattern ...` and
    the counts stay off; refilling is not affected. `BeltMatchTests` with env `D2R_DUMP` resolves all of them in the 93847
    dump. The watcher refreshes the counts every `auto_poll_frames`; out of a game the boxes are emptied. Console
    `belt-counts` logs the counts, whether the HUD panel and its boxes were found and how many texts were set.
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

## CharmInv by Dimentio (shipped in 0.1.19, replaced by Inventory Tabs in 0.1.20)

Shipped in 0.1.19. From the release after it the package carries our own charm inventory, invtabs, in its place
(docs/invtabs.md "Packaging: the charm inventory switch"); `--charm-inventory charminv` still builds and packages
CharmInv as described here.

[CharmInv](https://d2rloader.net/hub/plugins/charm-inventory) 1.0.1 by **Dimentio**, D2RLoader's author: a separate
charm inventory, a 10 x 4 grid on the left panel, opened by a button on the left edge of the inventory panel, a key
(Options > Controls > Charm Inventory: Open Charm Inventory; no key by default), the console command
`charminv open|close|toggle` or a controller tab. Charms in it grant
their bonus. **Licence:** no source and no licence file are published (the zip holds the signed DLL and its MPQ); CharmInv
is redistributed with D2RLoader by the owner's decision (author: Dimentio, D2RLoader's author), 2026-11-10. Credit: README,
CHANGELOG / release notes, NOTICE.md, `third_party/charm-inv/README.md` and this file (lane charminv).

- **In the package:** `mods\mxl2012\d2rloader\plugins\d2rl-charm-inv.dll` and its companion `d2rl-charm-inv.mpq` (both
  unchanged, mod-scoped), and our config `mods\mxl2012\d2rloader\config\charm-inv.toml`, a `preserve` file. The manifest's
  `bundledPlugins` names it with version, source, author and both SHA-256.
- **No binaries in git.** The author's two files are pinned by size and SHA-256 in `tools/package_release.py` (`CHARMINV`)
  and looked up by `--charminv DIR`, `MXL_CHARMINV_DIR`, a git-ignored copy in `third_party/charm-inv/` or
  `<runs>/shared/charm-inv-1.0.1/`; other bytes are refused (`third_party/charm-inv/README.md` has the update steps).
- **Config** (`third_party/charm-inv/charm-inv.toml`): `allow_inventory_charms = true` (owner decision 2026-11-10: a charm
  works in the normal inventory as in Median XL, and in CharmInv; the plugin's own default is `false`),
  `inactive_charm_tint = "yellow"` (only drawn when a charm does not count), `inject_inventory_button = true` (our mod
  has no other way in with the mouse).
- **Median charm types** (`tools/charm_inv.py`, build step after `warlock_scale`): the plugin reads which item types it
  takes from its table `charminvtypes.txt` (stock: `char`). The build writes the mod's override
  `data/global/excel/d2rloader/charm-inv/charminvtypes.txt` with every Median type whose `Equiv` chain reaches `char`:
  `char scha mcha lcha csch summ grtz araa`-`arag` (14; trophies, Sunstones and quest charms are `grtz`, the class
  challenge charms `ara*`, the Scroll of Summoning `summ`). Jewels are socket fillers in Median and stay out. The grid table
  `charminv.txt` stays 10 x 4 (the panel art has 10 x 4 cells).
- **The custom player page.** D2RLoader gives a mod one custom player page (item page 6 of the `.d2s`). It belonged to
  mxl2012-core's second personal stash page (`stash2`, `plugin/src/stash_pages.cpp`); that page is no longer registered
  and its arrows are gone from the HD and legacy stash layouts (`tools/ui_layouts.py`, `tools/rotw_stash_legacy.py`).
  **Old alpha items on stash page 2 are deleted before character select**, rather than imported into CharmInv.
  mxl2012-core 0.1.19 performs the cleanup and preserves characters already saved with CharmInv;
  see [stash retirement](stash-page-retirement.md).
- **Strings.** CharmInv's MPQ sets the charm line to "Keep in Charm Inventory to Gain Bonus"; the mod's string fixes win
  and say "Keep in Inventory or Charm Inventory to Gain Bonus" (`data/d2r_string_fixes.json`).
- **Legacy graphics: not usable yet.** The MPQ has HD layouts only (panel, inventory button, controller panel). In legacy
  no button is drawn and `charminv open` or the key only reserves an empty left panel; the charms in it still count
  (docs/testing.md "Lane charminv"). A legacy layout of our own (`data/global/ui/layouts/charm-inv/CharmInvPanel.json`,
  `InventoryButton.json` with classic art) is open.
- **Duplicate carry1 uniques** (mxl2012-core part `charmdup`, `plugin/src/charm_dup.cpp`, docs/d2r-addresses.md section 22c):
  Median's 45 carry1 uniques (unique charms, relics, quest charms) give their bonus once per character. A player may carry
  more copies of one of them (to trade) in the backpack: D2R's carry test no longer refuses the second copy (the unique
  half of `0x473960` is left out and the carry1 comparison slot `0x3e2abb0` answers "not the same"; the build's own carry1
  numbers stay). **CharmInv still takes one copy of each:** D2RLoader's custom page placement has its own carry1 test, so a
  second copy stays on the cursor when one is already carried (open item for D2RLoader; docs/testing.md "Lane charmdup"). Only the active copy gives its stats: the copy in CharmInv, else the
  top-left copy of the backpack (top row first, then the left column); the choice depends only on where the copies lie, so
  client, server and a reload agree. The other copies answer D2R's requirement check `0x36bc50` with "not met": D2R draws
  them red and never merges their stats. When a copy arrives that outranks the active one, the refresh first takes the
  old copy's stat list out (`0x2f8290`, on the server and in the client's own copy of the stats), then D2R merges the new
  one. Moving, dropping, picking up, trading and loading all go through D2R's refresh. The items themselves are
  never changed. The tooltip of an inactive copy has no line of its own (D2R has no native text for it); its requirement
  lines stay white. `MXL_CONTROL=charmdup` turns the part off (then the second copy is refused, as before). Game check
  `charmdup`; `uniquecarry` expects the second copy placed while the part is on.
- **Turn it off:** `inject_inventory_button = false` hides the button; delete the DLL and MPQ to remove it (the items in it
  stay on page 6 of the save).
- **Test runs:** a dev install (`tools/install_mod.py`) removes it; `--charminv` installs it as a release does.

## Damage Overflow Fix by CelestialRayOne (shipped from 0.1.25)

[Damage Overflow Fix](https://github.com/CelestialRayOne/d2rloader_plugins) 2.4.0 by **CelestialRayOne (Bogdan Bulai)**,
`plugins/damage-overflow-fix`, commit `9240725`. D2R does most of its damage math in 32 bits, in 1/256ths of a point, so a hit
or a damage stat above about 8.39 million wraps negative and then deals 0–2 damage. The plugin does that math in 64 bits and
caps it at 8,388,607 instead. Below the limit, every result is bit-identical to the game's own. **Licence:** MIT, "Copyright
(c) 2026 Bogdan Bulai". The licence text ships next to the DLL. Credit: README, CHANGELOG / release notes, NOTICE.md,
`third_party/damage-overflow-fix/README.md` and this file (lane plug125).

- **In the package:** `mods\mxl2012\d2rloader\plugins\d2rl-celestialrayone-damage-overflow-fix.dll` (the author's release
  build from the pinned commit, unchanged, mod-scoped), `d2rl-celestialrayone-damage-overflow-fix-license.txt`, and our
  config `mods\mxl2012\d2rloader\config\celestialrayone.damage-overflow-fix.toml`, a `preserve` file. The manifest's
  `bundledPlugins` lists it with its repository, commit, author and SHA-256.
- **No binaries in git.** The DLL is pinned by size and SHA-256 in `tools/package_release.py` (`DOF`). It is looked up by
  `--dof DIR`, `MXL_DOF_DIR`, a git-ignored copy in `third_party/damage-overflow-fix/` or
  `<runs>/shared/damage-overflow-fix-2.4.0/`, and other bytes are refused.
- **Config** (owner decision 2026-11-16): the author's default with `debug_log = false` (no per-hit `.hits.log`, up to
  256 MB) and `log_each_site = false`. `leech = true` stays on. `tools/verify_package.py` checks the three keys.
- **How it decides to work:** it patches about 100 sites, in Game.exe and in D2RCore.dll's stat engine. It checks each site
  against its expected bytes first and skips any that differ, with a log line. It has no build or version check. In game:
  "104 site(s) active, 1 disabled, 0 failed", and mxl2012-core reports no plugin clashes (none of its sites are ours).
- **Median data:** realistic Median damage (a few 100k per hit) never reaches the limit, so for normal play nothing changes.
  Monster life fits: Uber Izual has about 1.96M. An extreme build gets a capped hit instead of a hit for 1. Tested in
  lane plug125: 30,000 damage × 30,000% ED dealt 1–2 without the plugin and killed a 7.81M-life monster in one hit with it.
  Resist and leech results are identical with and without it.
- **Console:** `dmgoverflow` lists the sites, and `dmgoverflow hit` shows the last hit's damage types before and after resistances.
- **Turn it off:** delete the DLL, or set `dry_run = true` (it checks every site and patches none).

## Enemy Health Bars by Graxy_TV (shipped from 0.1.25)

[Enemy Health Bars](https://github.com/graxytv/D2R-Over-the-Head-Health-Bars) 0.2.6 by **Graxy_TV** (graxytv, also on the
[d2rloader.net hub](https://d2rloader.net/hub/plugins/enemy-health-bars)) draws compact health bars over hostile monsters in
HD and (with our patch) legacy graphics. Champions get blue outlines, and uniques and bosses orange. It is used with the author's permission (owner,
2026-11-16). **Licence:** GPL-3.0-only. It builds on SirCabby's D2RCabbyCodes (GPL-3.0), D2RLoader's PluginSDK (MIT), Dear
ImGui (MIT) and RuffnecKk's MapSense OverlayHost API (MIT). Credit: README, CHANGELOG / release notes, NOTICE.md,
`third_party/enemy-health-bars-mxl2012/README.md` and this file (lane plug125).

- **Built from source** by `tools/build_enemyhealthbars.ps1`, from the author's source zip in commit `e6b929b` (both zips
  checked by sha256), with our three patches in `third_party/enemy-health-bars-mxl2012/`:
  - `0001-no-build-fingerprint`: removes the check of Game.exe's time stamp and size, which refused every build but one (owner
    rule: never tie a plugin to a build). Its nine byte signatures stay, so on code it does not know it turns itself off
    with its own log line. This also sets the version to `0.2.6+mxl2012`.
  - `0002-dev-keep-visible-unfocused`: a test-only key, `dev_keep_visible_unfocused` (default `false`, not in any shipped
    config). It keeps the overlay drawn while the game is in the background, so test runs can capture it without taking focus.
  - `0003-legacy-placement-damaged-only`: **bars in legacy graphics**, with and without Legacy 16:9, placed the way our
    Floating Damage patch places its numbers: the unit's classic pixel position minus D2R's view offset, raised by the
    monster type's classic height (`pixHeight` in `monstats2`, 56 when it has none), then the classic screen (800x600, or
    1066x600 with Legacy 16:9) fitted to the window height and centred. Everything it reads is found at load by expected
    bytes; if they don't match, legacy stays without bars (log line) and HD is unchanged. It also makes **bars only on
    damaged monsters** the default (owner, 2026-11-16): `show_full_health` now defaults to `false` in the plugin and its config.
- **Setting, bars on all monsters:** `show_full_health = true` under `[bars]` in
  `mods\mxl2012\d2rloader\config\enemy-health-bars.toml` (the plugin's own key) also shows bars on monsters at full life;
  `false` (shipped) shows them only once a monster is below full life. `enemybars reload` in the D2RLoader console applies it
  without a restart.
- **In the package (GPL: the binary comes with its source):** `mods\mxl2012\d2rloader\plugins\d2rl-enemy-health-bars.dll`,
  `d2rl-enemy-health-bars-license.txt` (GPL-3.0), `-third-party.txt` with the ImGui, MapSense API and PluginSDK licences
  (`-imgui-license.txt`, `-mapsense-api-license.txt`, `-pluginsdk-license.txt`), and `d2rl-enemy-health-bars-source.zip`.
  The zip holds the patched source as built, our patches and a `SOURCE.txt` with the exact refs. The manifest's
  `bundledPlugins` names the repository, commit, licence and patch hashes. Its config
  `mods\mxl2012\d2rloader\config\enemy-health-bars.toml` (the patched source's, `show_full_health = false`) is a `preserve`
  file, so a player's choice survives Update and Repair. `tools/package_release.py` and `tools/verify_package.py` refuse a
  config that is not on, shows full-life monsters, or has the test-only key on.
- **How it works:** it reads game memory only, with no hooks or byte patches. Life comes from the client's normalized life
  stat, so Median's huge monster life (Uber Izual about 1.96M) cannot overflow it. The boss outline comes from MonStats
  flags. Head heights come from the mod's `monstats` / `monstats2` (1839 monster types). It draws in its own transparent
  window over the game, which hides while the game is not focused.
- **Tests:** the author's `policy_tests` plus ours (damaged-only visibility, the legacy placement maths for 800x600,
  1066x600 and 640x480) run in the build script; the packaging tests check the shipped config.
- **Screenshots** (lane plug125, background mode, overlay captured and laid over the game capture, docs/testing.md "Lane
  plug125"): HD, legacy, and legacy with Legacy 16:9; a Fallen at full life without a bar next to Fallen at 70/25% and a
  Median normal at 50% with bars, and the same with `show_full_health = true`; Andariel and Uber Izual with boss outlines.
- **On by default; turn it off:** `enabled = false` under `[bars]` in `enemy-health-bars.toml` (the plugin's own key; shipped
  `true`), then start the game again. Or delete the DLL. The README and the 0.1.27 notes tell players
  how, together with Floating Damage's switch.

## Floating Damage by RuffnecKk (shipped from 0.1.25)

[Floating Damage](https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite/tree/main/plugins/floating-damage) 1.5.6 by
**RuffnecKk** shows the damage of each hit as a number rising over the monster, plus a small DPS counter. It is based on locbones'
D2RHUD and the design of Fr4nsson's D2RDamageNumbers. **Licence:** MIT, "Copyright (c) 2026 RuffnecKk and contributors".
Credit: README, CHANGELOG / release notes, NOTICE.md, `third_party/floating-damage-mxl2012/README.md` and this file
(lane plug125).

- **Built from source** by `tools/build_floatingdamage.ps1`, from the submodule `third_party/RuffnecKk-D2RLoader-Suite`
  (commit `514359f`), with our patches in `third_party/floating-damage-mxl2012/`. The plugin's CMake fetches MinHook and
  Dear ImGui at the commits it pins.
  - `0001-mxl2012-legacy-projection`: **numbers over the target in legacy graphics**, with and without Legacy 16:9. The
    author's projection is HD only, so in legacy the numbers landed off the target or not at all. In legacy the plugin now
    places a number where the classic engine draws the unit: the unit's pixel position minus D2R's view offset, raised
    56 classic pixels to the head. The classic screen (800x600, or 1066x600 with Legacy 16:9) is then scaled to the window
    height and centred, as D2R does. Everything it reads is found at load by expected bytes. If they don't match, the legacy
    path turns off with a log line and HD keeps working. HD is unchanged.
  - `0002-mxl2012-bundled-font`: the default font is Exocet, which a plugin cannot read from D2R's CASC, so it fell back to
    Segoe UI. It now uses the bundled **Cinzel Bold** (Natanael Gama / The Cinzel Project Authors, SIL Open Font License 1.1,
    unmodified), a classical capital face close to Exocet.
  - `0003-mxl2012-legacy-dps-counter`: in legacy graphics the **DPS counter sits inside the game picture**. The author
    places it by percent of the whole window, so a 4:3 picture in a wide window had it in the black side bar. It now uses the
    same percents inside the classic picture and moves up when it would cover the classic HUD (globes and control panel).
    With Legacy 16:9 the bottom left corner is free, so it stays there. HD is unchanged.
  - `0004-mxl2012-legacy-text-scale`: **bigger numbers in legacy graphics** (owner, 2026-11-17). The author's sizes are
    reference pixels scaled to the window height, the same in HD and legacy, which looked small next to the classic
    sprites. The new key `legacy_text_scale` under `[appearance]` (shipped `2.5`, valid 0.25 to 8) multiplies the numbers'
    size (`text_size`, `critical_hit_size`) while legacy graphics are drawn, with or without Legacy 16:9. HD and the DPS
    counter keep their size. The packaging checks refuse a shipped config without `legacy_text_scale = 2.5`.
  - `0005-mxl2012-missing-system-font`: **no crash when a Windows font is missing** (lane fdproton, 2026-11-21). The
    renderer loads 12 fonts from `%WINDIR%\Fonts` before its first frame. Dear ImGui 1.91.5 reports a file it cannot open
    with an error tooltip, and opening that window outside a frame, with no font yet, crashed the game on the first
    Present. Proton prefixes have no Segoe UI (the default index 0), so every start under Proton crashed. Missing,
    unreadable and non-font files now go to the author's fallback (ImGui's built-in font) without that report, and a font
    that cannot be built leaves the built-in font for every index. With every font present, as on Windows, nothing changes.
- **In the package:** `mods\mxl2012\d2rloader\plugins\d2rl-ruffneckk-floating-damage.dll`,
  `d2rl-ruffneckk-floating-damage-license.txt` (MIT), `d2rl-ruffneckk-floating-damage-third-party.txt` (the suite's
  third-party notices and every licence text they keep: PluginSDK, Dear ImGui, MinHook, D2R Damage Numbers ...),
  `ruffneckk-floating-damage-font.ttf` with `ruffneckk-floating-damage-font-license.txt` (OFL), and the config
  `mods\mxl2012\d2rloader\config\ruffneckk-floating-damage.toml` (the author's, with a comment on the font), a `preserve`
  file.
- **How it works:** inline hooks where the game commits monster life (two call sites) and on the camera update, each
  checked against its expected bytes. It also hooks DXGI Present for its own D3D12 ImGui renderer, which draws into the game's
  frame. It has no build check. The amount shown is int32 visible life, so one number can show up to about 8.39M (the same
  limit as Damage Overflow Fix's cap).
- **Console:** `floating-damage status` (HD and legacy projection lines), `floating-damage preview`.
- **Tests:** the author's config tests and our legacy projection and font loading tests run in the build script. In game (lane plug125):
  numbers over a Fallen and over Andariel in HD, in legacy and in legacy with Legacy 16:9, and DPS 910 / 2.4K / 4.6K in
  legacy; the numbers 2.5 times bigger in legacy 4:3 and Legacy 16:9 with the shipped `legacy_text_scale`.
- **Bigger or smaller numbers:** `legacy_text_scale` (legacy only) or `text_size` / `critical_hit_size` (both modes) in
  `ruffneckk-floating-damage.toml`.
- **On by default; turn it off:** `enabled = false` under `[general]` in `ruffneckk-floating-damage.toml` (the author's
  master switch; shipped `true`), then start the game again: no renderer or combat hook is loaded. The packaging checks
  refuse a shipped config without `[general] enabled = true`. Or delete the DLL.

## Monster Display by CelestialRayOne (shipped from 0.1.27)

[Monster Display](https://github.com/CelestialRayOne/d2rloader_plugins) 1.0.18 by **CelestialRayOne (Bogdan Bulai)**,
`plugins/monster-display`, commit `9240725` (the commit Damage Overflow Fix comes from). It redraws D2R's HD hover panel over a
monster: a wider life bar with exact life and percent, level and type, the unique affixes in the game's own words, a
resistance row, and the immunity line. Prime evils get a bar twice as wide. **Licence:** MIT, "Copyright (c) 2026 Bogdan
Bulai". Credit: README, CHANGELOG / release notes, NOTICE.md, `third_party/monster-display/README.md` and this file (lane
plug127).

- **Which build:** the author's repository is the source; Lukaszpg's fork is the same commit, and the other forks (hclhdj,
  Songyx090818, eoakt) are behind or diverged. The plugin is not on the D2RLoader hub. The release DLL at the commit is
  1.0.18; the source there is 1.0.19, which only adds a lookup for the author's Summon Enhancements plugin. We ship the
  tested 1.0.18 DLL unchanged.
- **In the package:** `mods\mxl2012\d2rloader\plugins\d2rl-celestialrayone-monster-display.dll`,
  `d2rl-celestialrayone-monster-display-license.txt`, the config `mods\mxl2012\d2rloader\config\celestialrayone.monster-display.toml`
  (the author's default plus Median's 36–39 in `minion_hidden_affixes`, a `preserve` file), and its HD files in `mxl2012.mpq\data`: the three
  `hudmonsterhealthhd.json` layouts (mouse, controller, controller on PC) and 28 frame sprites in
  `hd\global\ui\panel\monsterdisplayframes\`. Our data has no hover panel layout of its own; the packager refuses to stage over
  one.
- **No binaries in git.** The DLL and the HD files are pinned in `tools/package_release.py` (`MD`: the DLL's size and SHA-256
  and one SHA-256 over the 31 HD files). They are looked up by `--md DIR` (the author's `release/` folder), `MXL_MD_DIR` or
  `<runs>/shared/monster-display-1.0.18/`, and other bytes are refused.
- **How it decides to work:** inline hooks on the hover panel builder (`0x0CEA50`) and the panel update (`0x1F84E0`), each
  checked against its expected bytes; no build or version check. It reads only the hovered monster (client copy, then
  the server's values). In legacy graphics it changes nothing.
- **Median data:** names, levels, types and affix names come from the game's own builders, so Median's strings show as they
  are. Median's monumod 36 Ghostly, 37 Fanatic, 38 Possessed and 39 Berserk (xfer 1, so minions carry them) are the
  game's champion types; its affix name builder gives them no name, so they show on neither a boss nor a minion. Our
  config still adds 36–39 to `minion_hidden_affixes` (a setting of the 1.0.18 DLL, no code change), so minions stay
  without them if a later build names them, like the author's own list (fire, lightning and cold enchanted,
  teleportation, spectral hit, stone skin). Resistances: in `effective` mode it applies the hovering player's
  sunder (`item_pierce_*_immunity`) and −enemy resistance the way D2R's damage code does; our port keeps D2R's resist step
  and moves Median's own stats off ids 187–193 (docs/id-mapping.md), so it reads the right stats. In game: a Median normal
  with fire 50 showed 25 with −25 % enemy fire; a fire 100 Fallen kept 100 and "Immune to Fire", as the damage code does.
  Uber classes 704–709 get no immunity line (the game's own rule; Median's ubers use the same ids). Life goes to 1,958,490
  (Uber Izual) without trouble.
- **Next to our plugins:** no clash (mxl2012-core `plugin clashes: none`). Enemy Health Bars and Floating Damage draw in
  their own layers; Monster Display only changes the hover panel.
- **Console:** `monsterdisplay` shows the hovered monster's data.
- **Turn it off:** `enabled = false` in `celestialrayone.monster-display.toml`, or delete the DLL (the layouts then show the
  game's own panel without the extras).

## Vendor Stock Refresh by RuffnecKk (shipped from 0.1.27)

[Vendor Stock Refresh](https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite/tree/main/plugins/vendor-stock-refresh) 2.1.7 by
**RuffnecKk**. It adds the gamble screen's refresh button to every vendor's HD trade screen; a click rerolls the vendor's
normal stock, free and as often as the player likes. Gambling keeps its own refresh. **Licence:** MIT, "Copyright (c) 2026
RuffnecKk and contributors". Credit: README, CHANGELOG / release notes, NOTICE.md, `third_party/vendor-stock-refresh/README.md`
and this file (lane plug127).

- **Which build:** the author's suite (`RuffDood/RuffnecKk-D2RLoader-Suite`), the same commit `514359f` our submodule pins
  for Floating Damage; 2.1.7's last change is in it. Lukaszpg's fork and the others are behind with nothing of their own.
  RuffDood's archived D2RLoader-Community-Pack is not used. The hub's 2.1.7 (2026-11-03, D2R 3.3, D2RLoader 1.3.1) is the
  same version.
- **Built from source** by `tools/build_vendorstockrefresh.ps1`, unchanged, from the submodule with the suite's own CMake
  (MinHook and nlohmann/json fetched at its pins). It runs the author's policy, panel layout and compact layout tests. The
  build is reproducible: the same bytes on every build of the commit.
- **Companion MPQ:** the button art is not in the repository; it is the hub release's MPQ, pinned by SHA-256 in
  `tools/package_release.py` (`VSR`), the same hash the plugin checks before it loads it. It is looked up by `--vsr-mpq DIR`,
  `MXL_VSR_MPQ_DIR`, a git-ignored copy in `third_party/vendor-stock-refresh/` or `<runs>/shared/vendor-stock-refresh-2.1.7/`.
- **In the package:** `mods\mxl2012\d2rloader\plugins\d2rl-ruffneckk-vendor-stock-refresh.dll` and `.mpq`,
  `d2rl-ruffneckk-vendor-stock-refresh-license.txt` (MIT), `d2rl-ruffneckk-vendor-stock-refresh-third-party.txt` (the suite's
  notices), and the config `mods\mxl2012\d2rloader\config\ruffneckk-vendor-stock-refresh.toml` (the author's: on, diagnostics
  off; a `preserve` file).
- **How it works:** client hooks on the vendor panel set-up (`0x2411E0`) and the refresh send (`0x10F520`); server hooks on
  the vendor interaction (`0x502F60`) and the entity action packet (`0x4B0470`, packet `0x38`, action `VSRF`, rewritten to
  the game's own trade action with the vendor's refresh flag set, so the game rebuilds the stock itself). Every hook checks
  its expected bytes, and it checks D2RCore's packet relay. No game-version gate of its own.
- **Median vendors:** the new stock is the game's own (Median's vendor tables, levels and shop rules), only made again. In
  game: Charsi 33 items → 36 with 16 kept after one refresh. Gambling (Gheed) is left alone. Legacy graphics (from 0.1.28):
  the mod's classic trade panel layout gives the plugin the named rects of its "legacy-frame" route (`tools/ui_layouts.py`
  `vendor_classic`), so the button shows on the stone left of Buy; gambling keeps D2R's own refresh on the repair square.
  Before, the classic panel had no gold anchor the plugin could find and it showed no button.
- **First trade with a vendor:** a trade picked while the vendor's first-meeting greeting plays used to close when the
  greeting ended (D2R reopens the NPC menu; the same without the plugin). mxl2012-core's part `npcgreet` keeps it open
  (docs/bugs.md #621). A click during the greeting only ends the greeting; the next one refreshes.
- **Next to our plugins:** no clash (mxl2012-core `plugin clashes: none`).
- **Console:** `vendor-stock-refresh` shows its state.
- **Turn it off:** `enabled = false` under `[plugin]` in `ruffneckk-vendor-stock-refresh.toml`, or delete the DLL.

## Building on Linux

`tools/build_thirdparty_linux.py` is the Linux equivalent of the `tools/build_<plugin>.ps1` scripts above (lane
thirdparty-linux, 2026-11-20). It builds `legacy169`, `buffhud`, `beltrefill`, `controllerqol`, `ehb` (Enemy Health Bars),
`fd` (Floating Damage) and `vsr` (Vendor Stock Refresh, once its .ps1 is on the branch), all of them by default:

```
/d2work/venv/mxl2012/bin/python tools/build_thirdparty_linux.py [PLUGIN ...] [--out DIR] [--repos DIR] \
    [--work CHECKOUT] [--skill-profile FILE] [--no-tests]
```

- **Same inputs as the .ps1:** the pinned commit of each gitlink (EHB: the pinned commit and both zip hashes), exported
  with `git archive`, our patches in name order, the same CMake options and targets, the same tests, and `PINNED_COMMIT`,
  `PATCHES` and `SKILL_PROFILE` written as package_release.py reads them. Sources come from the same `MXL_*_DIR` settings,
  `--repos` (a folder of clones), the submodule, or else a bare clone of the public repository (network once).
- **Compiler:** MSVC under wine (msvc-wine in `/d2work/toolchains/msvc`, `WINEPREFIX=/d2work/prefixes/msvc-build`), Ninja,
  `CMAKE_SYSTEM_NAME=Windows`, embedded debug info (`/Zi` fails under wine, C1902), and `/SUBSYSTEM:CONSOLE` for the DLLs
  that Windows builds with the Visual Studio generator (Buff HUD's preset is Ninja on Windows too). Tests and
  Buff HUD's `D2RLCompiler.exe` run under wine. The RuffnecKk suite's CMake requires PowerShell for ctest-only policy
  scripts the .ps1 never runs; on Linux that variable points at a stub that fails if anything runs it.
- **Output:** `--out` (default `/d2work/build/thirdparty-linux`) has the layout of the Windows `build\` folder:
  `legacy169/Release/legacy169.dll` with `legacy169-src/` beside it, and the same for `buffhud`, `beltrefill`,
  `controllerqol`, `enemyhealthbars` and `floatingdamage`, plus `vendorstockrefresh`. Hand the DLLs to
  `package_release.py` (`--legacy169`, `--buffhud`, ...) with the `-src` folders in its `build/`.
- **Inputs from the release build:** Buff HUD's half-size legacy icon sheets come from a built `work/` (`--work`, default
  this checkout). Controller QOL embeds the skill seed from `--skill-profile` (what `package_release.controllerqol_profile()`
  writes from the package's skills.txt; the packager refuses another seed).
- **Compared with the Windows builds (0.1.26 / plug127 bundle):** exports, imports, section names and text strings are the
  same. The Buff HUD MPQ is byte for byte the same. The code differs slightly, because msvc-wine has MSVC 19.52 and the
  build PC had 19.51 (sizes differ by up to about 3 %; the newer static CRT also imports `IsProcessorFeaturePresent`). Floating Damage
  and Vendor Stock Refresh are reproducible (`/Brepro`); the others carry a link time stamp, as on Windows. On the build PC
  `core.autocrlf=true` made `git archive` / `git apply` write CRLF into legacy169's, Controller QOL's and Enemy Health Bars'
  configs (in the DLL and as shipped). On Linux they keep the committed bytes. Both parse the same.
- **Tests under wine:** all pass, except three Controller QOL tests that check its memory guards against the real Windows
  memory APIs (`qol-guarded-local-read`, `qol-image-header-work`, `qol-current-page-query`). Wine 9 does not answer those
  APIs as Windows does. The script runs them and reports the result, and they do not stop the build. They pass on Windows.

## Checks before shipping (after 0.1.11)

- Each plugin loads next to mxl2012-core without hook conflicts, in HD and in legacy graphics.
- The mod-specific data (controller skill profile, loot filter, deposit item types) is written for Median XL 2012.
- Item-roll-ranges vs D2RLoader's stat ranges (on in the mod, #528; some automagic range lines repeat): only one may draw.
- The installer and the Downloader install them into `mods\mxl2012\d2rloader\plugins\`, pinned by checksum like D2RLoader.
- Release notes and README credit PyreFly, Lukaszpg (Buff HUD: done in 0.1.12) and jaycachou-svg (Auto Belt Refill: done for 0.1.15).
