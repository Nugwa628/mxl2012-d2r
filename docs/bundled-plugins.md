# Third-party D2RLoader plugins planned to ship with D2R-XL 2012

Planned 2026-11-04. Not shipped yet; add new candidates to the tables below. The compatibility work (which plugins
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
| [item-roll-ranges](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/item-roll-ranges/README.md) | Shows each modifier's possible roll range and source while Ctrl / RT is held | Reads the active game's affixes, uniques and runewords; check against Median's tables and D2RLoader's own Ctrl stat ranges, which the mod turns off (`item_stat_ranges = false`, bug #528): make sure only one draws |
| [inventory-deposit](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/inventory-deposit/README.md) | "Deposit all gems, materials and runes" button by the inventory gold | Needs the HD advanced stash and its item-type rules; Median items with no slot on the open page stay put (bug #535 side note: such an item logged item asserts) |

All five target D2RLoader 1.3.1 and plugin ABI 4 on Windows x64, the same loader the port uses.

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

## Auto Belt Refill by jaycachou-svg

[Auto Belt Refill](https://github.com/jaycachou-svg/auto-belt-refill/tree/main/Auto-belt-refill-v0.35.8-EN) (v0.35.8) by
**jaycachou-svg**: refills the potion belt from the inventory, by hand (a key or the `belt-fill` console command) or
automatically, with a per-column memory of potion codes. Candidate for 0.1.12 (owner, 2026-11-05). The repository states
no licence: ask jaycachou-svg before shipping it.

**Result (lane beltrefill, 2026-11-05): works with a locked Median column config; needs a rebuild for our SDK, and
waits on bug #541 for elixir columns.** Details in docs/testing.md "Lane beltrefill".

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
- **In game (slot 2).** With the column config below, the manual fill (`belt-fill`) filled all 16 slots per column
  (life, mana, life, Elixir of Experience). Auto-refill topped up a drunk slot from the inventory within one poll. Median
  items that no column lists (Elixir of Greed, Greater Elixir of Experience) were never moved.
- **Median-only potions.** Every Median elixir (`ey1`-`ey9`, `eo7`-`eo9`, `et1`, `0g0`-`0g8`) and the Goodberry `b@b`
  is item type `hpot`, like the healing potions. D2R's own belt routing, which the plugin uses, puts them into any life
  column that has room (bug #541). An unlocked column then adds the routed code to its memory ("column memory extended
  to follow the game"). Measured: a life column learned `ey2` and refilled with an Elixir of Experience, and the elixir
  column learned `hp5`. With `locked = true` the plugin refuses such routes, so columns keep their exact lists (checked in game with v0.35.9).
  `rvs` / `rvl` are not spawnable in Median. The #541 fix planned in lane beltstack is data only (each non-classic belt
  potion gets its own item type), and the plugin matches item codes, never item types, so it needs no change for it.
- **Median XL 2012 column config** (`auto-belt-refill.toml`, mod `d2rloader\config\`): columns 1 and 3
  `["hp5","hp4","hp3","hp2","hp1"]`, columns 2 and 4 `["mp5","mp4","mp3","mp2","mp1"]`, all `locked = true`, keys
  unbound (players bind them under Options > Controls), `debug_logs = false`. Elixirs stay out of the lists.

**Shipping needs:** jaycachou-svg's permission (no licence); v0.35.9 built with the SDK renames above (the patch is a
rename script, kept outside the repo); the locked config above; a check after the #541 fix that elixirs no longer reach
life columns; and credit to jaycachou-svg in the release notes and the README.

## Checks before shipping (after 0.1.11)

- Each plugin loads next to mxl2012-core without hook conflicts, in HD and in legacy graphics.
- The mod-specific data (controller skill profile, loot filter, deposit item types) is written for Median XL 2012.
- Item-roll-ranges vs D2RLoader's stat ranges (off in the mod, #528): only one may draw.
- The installer and the Downloader install them into `mods\mxl2012\d2rloader\plugins\`, pinned by checksum like D2RLoader.
- Release notes and README credit PyreFly and Lukaszpg (Buff HUD: done in 0.1.12).
