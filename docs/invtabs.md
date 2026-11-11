# invtabs: inventory tabs on the custom player page

`invtabs/` is a standalone D2RLoader 1.3.1 plugin (`invtabs.dll`, plugin id `invtabs`) for D2R-XL 2012 on D2R 3.3
build 93847. It owns D2RLoader's one custom player page (item page 6 of the .d2s), sets it to 16 x 16 and shows
rectangular parts of it ("areas") as tabs. The first tab is the charm tab. It replaces Dimentio's CharmInv in the package
and takes over the charms that CharmInv 1.0.1 left on page 6.

It is built from wild-healer's two plugins in his public D2R-Tools repository (commit
`6722cc545f52a012460f5e9a825632a7f5e38eb5` of 2026-11-09, kept in `mxl2012-runs\invtabs\upstream\`). The repository has
no licence file, so all rights stay with him until he agrees to this use:

- `plugins/aaa-player-page-host` (Player Page Host 1.0.2): page owner, area grids, Ctrl+click, TCP/IP link.
- `plugins/wild-healers-charm-inventory` (Wild Healer's Charm Inventory): the charm area client.

wild-healer approved the use with credit (2026-11-11); it is the mod's charm inventory since the release after 0.1.19 (`CHARM_INVENTORY`, below). Credit: README, NOTICE.md and the file headers.

Build: `tools/build_plugin.ps1` (with `-Tests` for the unit tests) builds `build\invtabs\Release\invtabs.dll` and
`build\invtabs\tests\Release\invtabs_tests.exe`. The plugin needs only the PluginSDK, nothing of mxl2012-core.

## Interface for the other lanes

This section is the contract the sibling lanes code against. It is copied to `mxl2012-runs\invtabs\INTERFACE.md`
whenever it changes. Anything marked "assumed" is open for the owning lane to change; tell the core lane.

### Names

| thing | value |
|-|-|
| plugin id / DLL | `invtabs` / `invtabs.dll` |
| config | `d2rloader\config\invtabs.toml` (embedded default: `invtabs/invtabs.toml`, owned by the data lane) |
| log lines | D2RLoader plugin log, every line starts with `invtabs:` |
| page logical id | `charms` (D2RLoader keys saved page items by it; never change) |
| tab panels | local id = the tab's config name (`[tabs.<name>]`), full name `invtabs/<name>`; the charm tab is `invtabs/charms`, always slot 0 |
| whole-page view (debug) | local id `All`, full name `invtabs/All` (console `invtabs all`) |
| grid child of every tab panel | `invtabs/Grid` (an `InventoryGridWidget`, `cellCount` 16 x 16, `cellSize` `$ItemCellSize`) |
| grid marker | `chronicleFlourishOffset` = {7400 + N, 7400} (N = slot, 12 for `All`); the core's grid wrappers find their grids by it |
| inventory button child | local id `InventoryButton`, child of `StockPanel::PlayerInventory`, `KeyboardMouseOnly`; click message `PanelManager:TogglePanel:invtabs/Tab0`; rect x 214, y 1375 (HD: right of the stock back-arrow button) |
| console | `invtabs` (status, also logged as `invtabs: status: ...`; then `drawn <tab> hd|classic|none`: the tab whose grid the game drew in the last 300 ms, the checks' visibility assertion, and `pad open|closed|off`: the controller panel), `invtabs open|close|toggle [<tab>]`, `invtabs all`, `invtabs scroll <n>` (summary lines), `invtabs summary` (refreshes, then writes the summary lines to the log) |
| Controls menu action | logical id `toggle-charms`, category `Inventory Tabs`; bound to `open_key` unless that is 0 or 73 (`I`, the stock inventory key, which it would take from the inventory) |
| HD panel layout | generated in memory by the core per tab (`layouts.h`), root name `invtabs/<name>`. Text references in plugin layouts must be namespaced: `@d2r:strClose`, `@invtabs:...`; a bare `@strClose` makes D2RLoader refuse the layout and `openPanel` returns 5 (NotFound) (unit test) |
| classic (legacy) panel layout | assumed `data/global/ui/layouts/invtabs/Tab<N>.json`; the SDK documents only `hd.json` and says legacy inventory layouts are not supported yet: the legacy lane verifies |
| controller layouts | assumed `data/global/ui/layouts/controller/invtabs/...` (SDK: controller-only child layouts); one `ControllerRouteRegistration` globally (pad lane) |
| HD art | `data/hd/global/ui/d2rloader/invtabs/<name>.sprite` + `.lowend.sprite` (SpA1 v31, RGBA), generated at runtime for the tab size |
| custom tables | `data/global/excel/d2rloader/invtabs/<name>.txt` (strict LF TSV; data lane) |

### Config keys the core reads

From `invtabs.toml` (the data lane's schema; the core reads only these keys and ignores the rest):

| key | default | use |
|-|-|-|
| `[invtabs] enabled` | true | false: no panels, button, hooks or drops; the page is still registered (16 x 16, removing items only), so saved page items load and stay |
| `[invtabs] inventory_charms` | true | true: charms count in the stock inventory and in the charm tab (Median rule). false: only in the charm tab |
| `[invtabs] open_button` | true | the inventory button |
| `[invtabs] open_key` | 73 | key of the Controls action; 0 or 73 leave it unbound (see Names) |
| `[tabs.<name>] columns`, `rows`, `label` | charms: 10, 6 | each tab's size (1..16) and title; the charm tab must stay at least 10 x 4 for CharmInv saves (see H) |
| `[tabs.<name>] item_types` or `types` | `types_<name>.txt` | inline type codes, else the tab's table; codes the game does not know are left out and logged |

Notes for the data lane: (1) `open_key = 73` is the stock inventory key `I`; the core does not bind keys itself, the
Controls menu action is unbound by default (as upstream) so it never fights the game's own binding. (2) D2RLoader's inactive
charm tint is an enum (Red, Green, Blue, Yellow, PaleRed), not RGBA: `inactive_charm_tint` should be one of those names.
(3) The charm tab is pinned at page cell 0,0 (see Areas); `Pack` must leave a tab with a preset `x,y` where it is.

### Tabs and areas

A tab is an area: `x, y, w, h` on the 16 x 16 page, plus the item types it accepts. The core holds `Tab` records (name,
label, columns, rows, x, y, accepted type codes). Placement rule:

1. The tab named `charms` is pinned at 0,0, so CharmInv's 10 x 4 items (x 0..9, y 0..3) are inside it.
2. The other tabs are packed around it, largest area first, then taller first, first free row then column, no rotation
   (wild-healer's packing; `tab_config.h::Pack` of the data lane).
3. The packing depends only on the config, so the areas are always the same for the same config. There is no area
   sidecar file (upstream had one). An item belongs to the area that holds its top-left cell.

Type rule: an item fits a tab when one of D2RLoader's `ItemPolicyRequest.matchingItemTypes` (the item's type and its
Equiv parents) is in the tab's type list. Built-in fallback for the charm tab: `char` (every Median charm type reaches it:
`scha mcha lcha csch summ grtz araa`..`arag`). Type lists come from the data lane's tables once they are wired in.

Charm rule: D2RLoader's own charm check (`IsCharmUsable`) with the page's charm policy `StockInventoryAndPlayerPage`
(or `PlayerPageOnly`). Only the charm tab accepts charms, so every charm on the page is in the charm tab and no native
charm hook is needed. The same check runs in the hosting game for every player, which is what G needs.

### What the core calls in the sibling modules (assumed; the owning lane's header wins)

| module | core calls | when |
|-|-|-|
| summary (`invtabs/src/summary*`) | a layout fragment for the top of the charm panel, given x, y, width, height; a refresh with the counting charms | building the charm layout; on tab open and after a page item change |
| pad (`invtabs/src/pad*`) | register the controller route / layouts for panel `invtabs/Tab0` | plugin load, after the panels are registered |
| legacy (`tools/invtabs_legacy*`, `tools/invtabs_art*`) | a classic layout + art for a tab of w x h, registered as resources by the core | plugin load |
| mp (`invtabs/src/mp*`) | start/stop with the page handle; asks the core for the areas and the type rule | plugin load / unload |

The core reserves a summary band of `SummaryHeight` pixels above the charm grid (0 until the summary module is wired in).

## Architecture

One DLL, one translation unit for the page host plus pure logic headers:

- `invtabs/src/invtabs.cpp`: plugin entry, config, page registration, panels, grid wrappers, item policy, button,
  console, Controls action.
- `invtabs/src/invtabs_logic.h`: pure logic, no Windows headers (signature patterns and matcher, area geometry and
  packing with a pinned tab, grid marker, type rule, config reading).
- `invtabs/src/invtabs_natives.h`: the signature table (checked against the dump by `tools/invtabs_sigs.py`).
- `invtabs/tests/invtabs_test.cpp`: unit tests of the logic header.

### What comes from which upstream file

| invtabs part | upstream | change |
|-|-|-|
| page registration 16 x 16, charm policy, item policy | host.cpp `Load`, `OnPagePolicy` | one owner, no lease service; page id `charms`; policy by tab type list |
| panels with a grid each, layout re-registered before open | host.cpp `RegisterPanels`, `SyncLayout`, `DefaultLayout`, `GridWidget` | our names and marker 7400 |
| procedural panel background, SpA1 writer | host.cpp `Background`, `SpriteFile`, `Half` | as is (his own code; used only with his OK) |
| grid vtable wrappers (draw, item rect, valid cell, cell at point, cell rect) | host.cpp `PatchVtable`, `Hook*` | addresses by signature, not fixed RVAs |
| area packing | host.cpp `TryPack` / `PackWaiting` | pinned charm tab; no saved places |
| inventory button, Controls action, console | plugin.cpp `AddButton`, `OnCharmsAction`, `Command` | own button art; `TogglePanel` message |
| charm check wrapper | host.cpp `HookCharm`, plugin.cpp `WrapCharmSlot` | not used (see charm rule) |
| one-copy rule for unique charms | plugin.cpp | not used: H wants a second carry1 copy |
| Ctrl+click into an area, TCP/IP area link | host.cpp | later (stage 2 and G) |
| joiner item requests (`requestCreateFromSave`, `requestSaveItem`, `requestDestroyItem`, `itemsWhere`) | host.cpp | not ported (decision 3) |
| `frame_art.inc`, `mold.inc` (art from Grail On! / Expanded Stash Plus) | plugin.cpp | not taken (decision 6) |

### Coordinator decisions (2026-11-11, after the upstream review)

1. No sidecar files and no packing by arrival order: tab rectangles follow from the config / tab table alone, the charm
   tab is pinned at 0,0. invtabs never moves, returns or deletes an item on its own (no "back to the inventory or stash"
   path). An item outside every tab stays where it is and is reached through the whole-page view (`invtabs/All`).
   A config that shrinks a tab under items is refused (the old size stays, with a log line; stage 2, with the tab table).
2. The page is always registered (16 x 16), also with `enabled = false` or when patterns are missing, so saved page items
   always load.
3. The joiner item requests are not ported. Only item moves; the hosting game decides everything. Lane invtabs-mp designs
   the protocol; the seam is the item policy callback (`OnPagePolicy`) and the area / type query of the core.
4. The first in-game test came before more building (results below).
5. invtabs does not hook 0x36BC50 or 0x3E2ABB0 (mxl2012-core owns them); the grid vtable is found by pattern.
6. Art: no `frame_art.inc` / `mold.inc`; our own plain generated panel art. The game-icons.net icon (CC BY 3.0) may be
   used with its exact attribution (not used yet).
7. mxl2012-core follow-ups (not done here): stash retirement must recognise `invtabs.dll` as a page-6 owner; `charmdup`
   must treat only the charm tab's rectangle as the charm inventory. For that, invtabs exports
   `int __cdecl InvTabsCharmTab(int* x, int* y, int* w, int* h)` (1 and the charm tab's page rectangle, 0 when there is
   no tab); look it up with `GetProcAddress(GetModuleHandleW(L"invtabs.dll"), "InvTabsCharmTab")`.

Median specifics: Median XL 2012's charms are carry1 uniques of type `grtz` (Equiv `char`), 1 x 1 to 2 x 2
(Butcher's Tooth `a60` 1 x 1, Sacred Worldstone Key `a61` 1 x 2, Jolly Roger `yq7` 2 x 2); the base `cm1`..`cm3` rows are
switched off (0 x 0). Charms count in the inventory too. There is no Grail On! button to sit under.

### In-game results (2026-11-11, slot 2, HD, 1600 x 900, background input)

Checks `invtabs_seed` (CharmInv 1.0.1 installed) then `invtabs` (CharmInv removed, `invtabs.dll` + default config),
`tools/game_checks.py`, throwaway character InvTabsC (runs `checks-20261111-131439-s2`, `checks-20261111-131635-s2`;
first pass InvTabsB `checks-20261111-124420-s2` / `-124915-s2`, the same results without the button step):

- CharmInv adoption: YES. Butcher's Tooth (0,0) and the Sacred Worldstone Key (9,2..9,3) that CharmInv saved on page 6
  load into the page invtabs registers (16 x 16, logical id `charms`) at the same cells, in the charm tab. D2RLoader did
  not refuse the character for the missing `d2rl-charm-inv.dll`.
- Second carry1 copy: REFUSED. A second Butcher's Tooth clicked into the charm tab stays on the cursor, although the
  invtabs item policy accepts it (type `grtz` -> `char`; no invtabs refusal line). So D2RLoader's custom-page placement
  (or mxl2012-core) refuses it regardless of our rule; H needs a fix outside invtabs.
- The tab: the Charms button in the inventory opens it (status closed -> open), 10 x 6 at page 0,0; the tooth gives
  +10 Strength (30 -> 40 server and client, 30 while held on the cursor); the Jolly Roger (2 x 2) is taken at 2,2; an El
  rune is refused; Save and Exit and Play keeps all three page items and +10 once. The whole-page view shows the page.
- Plugin log (`mods\mxl2012\d2rloader\logs\invtabs.log`): `page 16x16 owned, charm tab 10x6 at 0,0`, grid vtable entries
  3, 16, 18, 19, 31 wrapped, `character ready: N item(s) on the page, 0 outside every tab`.

### Stage 2 (2026-11-11, slot 2, background input; Itabsdelta, Itabsepsilon)

Runs `checks-20261111-173049-s2` (tabs), `-173751-s2` (tabs) and `-174050-s2` (shrink), notes in
`mxl2012-runs\invtabs\stage2` (`session4.log`, `session5.log`). Config: the repo's `invtabs.toml` plus a test-only potions
tab 4 x 3 (`hpot mpot rpot`); the shipped file has only the charm tab.

- Tabs as data: both tabs register (`charm tab 10x6 at 0,0; tab potions 4x3 at 10,0`), each with its own HD panel and the
  tab row; the potions tab takes a healing potion at 10,0 and refuses a charm; the charm tab refuses an El rune.
- Never lose items: with the charm tab at 10 x 4 while items lie in rows 4 and 5 the config is refused (`config refused
  (tab charms 10x4 at 0,0 would leave items seen in cells 0,0 to 0,5 outside it): the previous tab layout stays`), the
  status still says 10 x 6 and no page item moved. The plugin never moves or deletes items itself. Layout memory:
  `d2rloader\config\invtabs-layout.txt` (each tab's place and the box its items reach); delete it to forget.
- Ctrl+click: backpack -> open tab for charms, a rune stays, the potions tab takes potions only. The click event's item
  handle is stale on the game thread (`executeExistingItemTransaction` 9, StaleHandle); the core finds the item again by
  `runtimeId` in the backpack before the move.
- Summary: totals at level 120 equal the sum of the counting charms (`+18 to Strength` = tooth 10 + the others), the
  level-40 tooth is left out at level 1, the second copy of a carry1 charm counts once, the list scrolls to its end in HD
  (wheel) and classic (PgUp / PgDn, `invtabs scroll`). "left out" also counts the backpack's non-charm items.
- HD art: built from stock D2R sprites only (`tools/invtabs_hdart.py`: panel_bg, closebtn_4x, mkb_tabs_195,
  stashpanel_bg_personal, the side-panel hinge); nothing from CharmInv. Screenshots: `stage2\look\hd_charms_10x6.png`,
  `hd_potions_4x3.png`. Non-stock to the eye: the summary text is small blue item-stat text on the dark pad, and below
  10 columns the grid sits centred in a lot of empty pad (potions 4 x 3).
- Classic: charm tab drawn inside the classic panel, button opens it, X closes it (`sd_charms_top.png`, `sd_charms_end.png`).
  Open: an item of another tab on the same page (the test potion at 10,0) is drawn above the classic charm grid.
- Engine: the harness `item` generator's `wPrefix != 0 || wSuffix != 0` (bug #35) fails the check by the engine rule
  although every sub-check passed; one first-chance report at shutdown, outside D2R.exe (see testing.md, "Crash files
  that are not the crash").
- Mod data: `PluginContext::modDirectory` is the `mods\mxl2012\mxl2012.mpq` folder itself; the core looks for `data`
  there first, then under `<dir><mod>.mpq` and `<dir><mod>\<mod>.mpq`.

### Stage 3 (2026-11-11, slot 2, HD, background input; Itabspad*, Itabstab*)

Runs in `mxl2012-runs\invtabs\stage3\runs` (`session1.log` .. `session4.log`), driver `stage3\scripts\session.py`.

**Controller tab (E), check `invtabs_pad`** (`tools/invtabs_pad_checks.py`; invtabs installed, CharmInv absent, a fresh
character, the scripted pad). Run `checks-20261111-194228-s2`: PARTIAL = every row passed, the looks judged on the shots.

- The gamepad menu reads Quest Log, Character, Inventory, **Charm Inventory**, Skill Tree, Options (`invtabs_pad_menu.png`).
- D2R pages that menu with **RB / LB** (the strip shows the LB / RB marks); with Controller QOL Updates (bundled in
  releases) it is RT / LT, as the pad lane saw with CharmInv. The check takes whichever key opens the tab. RB from
  Inventory opens our panel (status `pad open`, `drawn charms hd`), LB goes back, RB opens it again.
- With our grid focused, D-pad right crosses into the backpack, A picks up a charm, left crosses back, A places it in the
  tab (page 6 9,1); moved to 0,0, menu closed and opened again, the first A picks it up: the focus lands on our grid.
  A in the tab, right, A in the backpack takes it back out of the tab.
- The summary is on the controller panel (new: `SummaryPad`, rows in the panel's summary well, set by the core while the
  pad panel is open; log `summary: on the controller panel, N line(s) of 20 row(s)`), `invtabs_pad_summary.png`. 20
  fixed rows for 10 x 6; longer lists are cut (the pad has no scroll input).
- Send to stash in the gamepad inventory still empties the backpack (tools/cqol_checks.py's route).
- The first attempts failed on the test, not the plugin: the harness `pickup` puts items into the backpack while the
  gamepad UI is on, and a backpack full of Butcher's Tooth (carry1) cannot give the page a second copy (H). The check
  now fills the backpack with plain a55 charms.

**Layout memory (`invtabs-layout.txt`) review.** Result: kept, hardened, tested (`MemoryFile` in invtabs_test.cpp).

- What it holds: per tab its place and the box its items have reached, the union over every character played in this
  install. It is read once at plugin load by `PlanTabs` and only (a) refuses a config that would leave a seen item box
  outside its tab, overlap or not fit, keeping the remembered layout, and (b) keeps a remembered tab at its place when
  the packing would put it elsewhere. Nothing reads it to move, return or delete an item: the plugin moves items only on
  the player's own Ctrl+click.
- Missing file: the config as it is (worst case an item lies outside every tab: saved where it is, reachable with
  `invtabs all`). Stale or another character's reach: at most a refusal. Corrupt: unreadable lines are dropped, values
  outside 0..16 dropped, a layout that overlaps, has too many tabs or no charm tab at 0,0 falls back to the charm tab
  alone; a file over 64 KB is ignored. The unit test plans every combination of 9 broken or stale files and 6 configs and
  checks the plan is always safe (charm tab first at 0,0, at least 10 x 4, all on the page, no overlap).
- Written whole to `invtabs-layout.txt.tmp`, flushed, then one `MoveFileExW(REPLACE_EXISTING | WRITE_THROUGH)`.
- Keying: there is no per-character record to collide. D2RLoader gives a plugin neither the character's name nor its
  save folder, and the tab layout is per install (panels, the controller route and the classic art are fixed at plugin
  load, before any character is chosen). So the reach is one union that only grows: two characters with the same name in
  different save folders can only add to it, never take the other's items out of the protection. Price: a reach never
  shrinks; deleting the file forgets it (safe, see "missing").
- Why not from the live items: the refusal could be decided at character load, but the fallback layout could not be
  applied then (the controller route can be registered only during plugin load, the classic art is per configured size),
  so the decision has to be made at plugin load, before any character is known. The file stays.

**Stage 2 issues.**

- (a) Classic graphics, another tab's item drawn above the charm grid: **open**. The classic grid is 16 x 16 like the HD
  one and goes through our Draw wrapper, but an item-rect wrapper that moved other tabs' items off screen changed nothing
  (run `checks-20261111-190756-s2`, `invtabs_sd_charms_top.png`; reverted), so the classic renderer collects and places
  its items outside the wrapped Draw / item-rect calls. Needs the classic draw path found in the dump.
- (b) "left out" counted every backpack item: **fixed**. The summary walk takes charms only, by the game's own item type
  test (0x373890, `char` with its Equiv children; optional signature from its call in 0x36ae00). In game at level 1 the
  two teeth (level 40) give `2 left out` (stage 2: 23).
- (c) Missing patterns: **tested** (`invtabs_natives_off_tests.exe`, a fake PE image with every pattern). Each of the
  summary's 13 patterns broken: the summary is off (on for its two optional formatter ones) and all 9 core patterns still
  resolve. Each core pattern broken: it does not resolve, so `Locate()` turns the tab areas off (one log line; no
  wrappers, no Ctrl+click, the page and its items untouched; the plugin then keeps the summary off too, its items come
  from the area draw). The optional type pattern broken: only it is missing.
- (d) Bug #35: **separated**. `finish(..., harness=INVTABS_HARNESS)` reports `wPrefix != 0 || wSuffix != 0` as a harness
  note in every invtabs check. `invtabs_tabs` then PASSes (`checks-20261111-193524-s2`, its first full PASS).

## Packaging: the charm inventory switch

One switch: `CHARM_INVENTORY` in `tools/charm_inventory.py` (`"invtabs"`, the default, or `"charminv"`), read by the build, the
package tools and the dev install. `--charm-inventory` on `tools/build.py` and `tools/package_release.py`, or the
environment variable `MXL2012_CHARM_INVENTORY`, choose the other one for one run. The build and the package must agree:
`package_release.py` refuses data built for the other charm inventory, `verify_package.py` checks it in the 7z, and
`install_mod.py` warns in a dev install.

With invtabs the package holds `d2rloader/plugins/invtabs.dll` (from `--invtabs` or `build/invtabs/Release/invtabs.dll`),
`d2rloader/config/invtabs.toml` (a preserve file), invtabs' data in `mxl2012.mpq/data` (`INVTABS_DATA`), the classic
Charms button in both classic inventory layouts, and none of CharmInv's three files or its two tables; the manifest's
`bundledPlugins` entry credits wild-healer with his repository and commit. With CharmInv the package is what main built
before the switch existed (checked in stage 4: every path, size and hash of the 0.1.19 manifest except the two DLLs
rebuilt from this branch). Unit tests: `tools/tests/test_charm_inventory.py`, `test_package_release`,
`test_verify_package`. `install_mod.py --invtabs DLL` installs a dev slot the same way (the data comes from `work/mod`).

| file in mxl2012.mpq/data | made by (build step, invtabs only) |
|-|-|
| `global/excel/d2rloader/invtabs/tabs.txt`, `types_charms.txt` | `invtabs_tables.py build` |
| `hd/global/ui/panel/invtabs/stockgrid.sprite`, `.lowend.sprite` | `invtabs_hdart.py build` |
| `global/ui/panel/invtabs_charms.dc6`, `invtabs_tab_charms.dc6`, `invtabs_button.dc6` | `invtabs_art.py build` |
| the classic Charms button in `playerinventory*layout.json` | `invtabs_legacy.py button` |
| (CharmInv only) `global/excel/d2rloader/charm-inv/*.txt` | `charm_inv.py apply` |

The HD, classic and controller panel layouts and the HD panel, button and controller art are made by the plugin at run
time. The classic Charms button used to be added by `ui_layouts.py` in every build, also while CharmInv shipped (a
button that opened nothing); it now exists only in an invtabs build (`check_buttons`, tests `ClassicButton`).

A player who updates by unpacking the 7z over an older install must delete CharmInv's three files
(`d2rloader\plugins\d2rl-charm-inv.dll`, `d2rl-charm-inv.mpq`, `d2rloader\config\charm-inv.toml`): with both plugins
present the first one takes the custom page and the other has no page. The downloader removes files that left the
manifest by itself.

The packing and the art follow wild-healer's CharmInv design; he approved the use of his code with credit (2026-11-11).

## Address table

Our 93847 code is byte-identical to upstream's 93787 at every native upstream uses, so the RVAs are the same. invtabs
finds them by pattern anyway (`invtabs/src/invtabs_natives.h`, checked by `py -3 tools/invtabs_sigs.py`; each pattern
matches exactly once in .text of the 93847 dump). `??` covers rel32 call targets and RIP displacements.

| his RVA (93787) | what | pattern (start) | our 93847 RVA | status |
|-|-|-|-|-|
| 0x34A360 | InventoryOf(unit, file, line) | `48 89 5C 24 18 56 48 83 EC 20 48 8B F1 48 85` | 0x34A360 | found, used |
| 0x388C10 | FirstItem(inventory) | `40 53 48 83 EC 20 48 8B D9 48 85 C9 74 2E 81` | 0x388C10 | found, used |
| 0x38ABA0 | NextItem(item) | 159 bytes, ends `48 05 A0 00 00 00 74 DC 48 8B 40 10` | 0x38ABA0 | found, used |
| 0x38A930 | NodeMode(item) | 159 bytes, ends `48 05 A0 00 00 00 74 DC 0F BE 40 19` | 0x38A930 | found, used |
| 0x15F100 | CursorItem() | `48 83 EC 28 E8 ?? ?? ?? ?? 8B C8 E8 ?? ?? ?? ?? 48 85 C0 74 21` | 0x15F100 | found, used |
| 0x2A7810 | GridOwner(widget) | `48 83 EC 28 44 8B 81 C4` | 0x2A7810 | found, used |
| 0x2C6300 | PointToCell(widget, out, point) | `48 8B C4 4C 89 40 18 53 55 56 57 41 56` | 0x2C6300 | found, used |
| 0x371850 | ItemSize(item, &w, &h, file, line) | 64 bytes from `48 89 74 24 18 48 89 7C 24 20 41 56` | 0x371850 | found, used |
| 0x1CF3800 | InventoryGridWidget vtable | `48 8D 05 ?? ?? ?? ?? 48 89 03 33 D2` (lea in the constructor 0x2C3400, disp at +3) | 0x1CF3800 | found, used |
| 0x8B2D0 | LocalIndex() | `8B 05 ?? ?? ?? ?? C3` is not unique; only with the next getters | 0x8B2D0 | not used (SDK `getLocalPlayer`) |
| 0x9A480 | PlayerUnit(index) | `48 89 5C 24 08 57 48 83 EC 20 83 F9 08` | 0x9A480 | not used yet (item record) |
| 0x1C3420, 0x1A0780 | item drop sound, PlaySound | 16-byte prologue identical | same | later (Ctrl+click sound) |
| 0x3E2B61C -> slot 0x3E2ACA0 | D2RCore charm check thunk (`jmp [slot]`, 12 callers) | `FF 25` + rel to slot | same | not used (charm rule needs no hook) |
| 0x3E2B6A0, 0x3E2B6AC, 0x43D900, 0x43CD50, 0x48FE80, 0x46EB00, 0x48FAA0 | item from save bytes (TCP/IP item requests) | prologues identical | same | later (G) |
| D2RCore+0x6FFC58, +0x423492 | D2RCore internal slot / call | not checked | ? | later (G); D2RCore-version bound |

Grid vtable entries used: 3 Draw, 16 item rect, 18 valid cell, 19 cell at point, 31 cell rect. Widget fields: page byte
+0x630, marker +0x634. Unit: id +0x08, data +0x10, path +0x38; path x +0x10, y +0x14; item data page byte +0x55.

A feature whose pattern is missing switches itself off with one `invtabs:` log line: without the grid patterns the tab
panels show the whole 16 x 16 page and drops are not limited to the area (the type rule still holds).

## Save format

- Page items are stored by the game in the .d2s item list: stored location 0, serialized page 7 = native page 6, x/y in
  four bits each (hence 16 x 16). D2RLoader restores them through the page owner's registration (logical id) and refuses
  the character when it cannot place a saved item.
- D2RLoader's `.d2rl` sidecar (D2RL v2) beside each .d2s holds the save hashes, the build, the mod and the plugin list
  (with versions). It holds no items. invtabs adds nothing to it beyond D2RLoader's own plugin record.
- invtabs writes no sidecar of its own. Upstream kept two text files in `Saved Games\Diablo II Resurrected\Player Page
  Host\<mod>\`: `aaa-player-page-host-areas.txt` (`plugin/area x y w h`, leased places) and
  `aaa-player-page-host-items.txt` (`<character> x y w h <owner area>|-`, which area each page item was put in). Both are
  rebuildable, and invtabs does not need them: the areas follow from the config alone, and an item's area is the one
  holding its top-left cell.
- Rebuilding lost upstream sidecars (for a player coming from wild-healer's plugins): areas = run the packing on the
  config; items = load the character, walk page-6 items (FirstItem / NextItem, page byte 6), write `x y w h` with the
  area holding the top-left cell as owner. invtabs does this implicitly every time.
- Config changes that move a tab can leave items outside every area. Those items stay saved where they are and are
  reachable in the whole-page view; invtabs never moves them itself. Shrinking a tab under items is refused.

### H: CharmInv saves

CharmInv 1.0.1 registers the same single custom page (10 x 4); its charms are page-6 items at x 0..9, y 0..3. invtabs
registers the page 16 x 16 with the charm tab pinned at 0,0, so those items are inside the charm tab and need no move.
Nothing is copied, so nothing can be duplicated or deleted. Charm tab sizes below 10 x 4 would leave some outside: the
config reader clamps the charm tab to at least 10 x 4.

mxl2012-core's `charmdup` (docs/d2r-addresses.md 22c) treats page 6 as the "CharmInv first" active copy; that stays
true because the page and its byte are the same.

## Risks

- A character saved with CharmInv loads with invtabs instead (checked in game, also as a joined TCP/IP player).
  mxl2012-core's stash retirement knows both page-6 owners (checked in game in stage 4, below).
- A second copy of a carry1 unique is refused by the custom page (checked in game), not by invtabs (H).
- The grid vtable is shared by every inventory grid; the wrappers only act on grids with our marker and call through to
  whatever was there before (another plugin's wrapper or the game).
- Another plugin that registers the custom page first (CharmInv, wild-healer's host) leaves invtabs without a page:
  logged, the tabs stay closed. The package must not ship both.
- The page size can change only before the grid is first used (D2RLoader returns Busy after).
- Joined TCP/IP players (docs/invtabs-mp.md section 6): the hosting game decides every move; a joined player whose
  tab table differs from the host's has take-out-only tabs with a plain notice. Drops by drag are limited to the area
  by each client's own grid wrappers; the hosting game's item policy checks the type only.

## Stage plan

1. Skeleton (this): plugin, page 16 x 16, charm tab 10 x 6 at 0,0, grid wrappers by pattern, type rule with `char`
   fallback, button / console / Controls action, CharmInv adoption, unit tests, address table.
2. A: tab tables from the data lane (`tab_config.h`), several tabs and their buttons, Ctrl+click into the shown area,
   the shrink refusal, the generated charm-tab art for any size (C), the `InvTabsCharmTab` users in mxl2012-core.
3. D: summary module wired into the charm tab (summary lane).
4. E: controller route and layouts (pad lane).
5. F: classic panel (legacy lane) once D2RLoader accepts non-HD layouts, or through the path the legacy lane finds.
6. G: TCP/IP item moves with the hosting game deciding (mp lane's protocol), tested with the mp rig.
7. H: carry1 second copy in the charm tab (find what refuses it: D2RLoader's custom-page carry1 test or mxl2012-core),
   package switch from CharmInv to invtabs, release notes.

Status 2026-11-12 (stage 4): A, C, D, E, the classic part of F and G checked in game; the build and the package are
wired; the classic draw of other tabs' items (F, test configs only) and the carry1 second copy (H, the same refusal as
with CharmInv 1.0.1) stay open.

### Build wiring (applied in stage 4)

`tools/build.py` takes its steps from `steps_for(charm_inventory)`: for `"charminv"` exactly the steps main had
(`charm_inv.py apply` included), for `"invtabs"` without `charm_inv.py apply` and with these four after `legacy_art.py`
(it checks the classic tiles the legacy panel reuses):

    ["invtabs_tables.py", "build", "--out", str(MOD)],                      # types_<tab>.txt from invtabs/invtabs.toml
    ["invtabs_hdart.py", "build", "--out", str(MOD / "data")],              # HD frame, tabs, cells, pad from stock D2R sprites
    ["invtabs_art.py", "build", "--d2r", str(D2R_EXTRACT), "--out", str(MOD / "data")],     # classic charm panel art
    ["invtabs_legacy.py", "button", "--out", str(MOD / "data")],            # the classic Charms button, both classic layouts

`invtabs_legacy.py build` (classic panel layouts as files) is not a build step: the plugin makes those layouts at run
time. A full `tools/build.py` run was not made in this lane (it is the coordinator's hour-long build); the four steps
were run through `build.run` on a copy of main's finished build, twice with the same bytes, followed by
`strings_check.py` and `validate.py` with 0 errors, and that tree went into the test package and the game runs.

### Stage 4 (2026-11-12, slots 2 and 5, HD, background input)

Evidence: `mxl2012-runs\invtabs\stage4\` (docs/testing.md "Lane invtabs stage 4" lists the runs).

- Package: switch off equals main's 0.1.19 package; switch on verified by `verify_package.py`, installed into slot 2 as
  a release and smoke-tested.
- Stash retirement with invtabs as the page owner, in the game: the old-core fixture loses exactly its seven old
  page-2 items at start-up and keeps the other 860; a character saved with invtabs and one saved with CharmInv (core
  record set back to 0.1.18, so only the owner record protects them) are byte-identical after start-up and keep their
  page-6 items in the game.
- Second copy of a carry-once charm: refused into the tab (stays on the cursor), exactly as CharmInv 1.0.1 refuses it
  (D2RCore's own custom-page test, docs/d2r-addresses.md 22c); invtabs is not worse.
- The whole-page view (`invtabs all`) did not open and raised a game assert (`TypeDesc.cpp:197`: its 61 px cell size
  was written as a bare number where the layout wants x / y): fixed in `layouts.h` (`HdPanel`), unit test added.
- TCP/IP: docs/invtabs-mp.md section 6.
