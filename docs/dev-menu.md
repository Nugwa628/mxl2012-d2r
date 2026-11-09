# Developer menu (plugin part `devmenu`)

For players: [dev-menu-guide.md](dev-menu-guide.md). Off word `devmenu`. Code: `plugin/src/devmenu.cpp`, pure rules in `plugin/src/devmenu_logic.h`
(test `devmenu_tests`), layouts from `tools/devmenu_layout.py` (`plugin/src/mxl_devmenu_layout.h`, committed, `tools/tests/test_devmenu_layout.py`
checks it is current), catalog from `tools/devmenu_catalog.py`, in-game check `devmenu` (`tools/devmenu_checks.py`).

## What it is

One native D2R panel, `mxl2012-core/DevMenu`, in HD and classic layouts, opened by the Controls action `mxl_dev_menu` ("Developer Menu",
category "D2R-XL 2012", default Ctrl+F12, rebindable in `input-bindings.toml` and the Controls menu). Every player gets it in single player.
No `MXL_DEVMENU` build option: the release build has it too. It does not use the test harness; the harness verb `devmenu`
(`open|close|press <button>|input <text>|state`) exists in dev builds only.

## How the panel is put together

- Buttons, tabs, the search box and (HD only) the artwork are native widgets. Classic graphics have no plain panel art
  (`MENU\dialogbackground` has input boxes painted in), so that panel floats over the game.
- Button clicks send
  `PanelManager:OpenPanel:mxl2012-core/DevMenuB_<n>`; each `n` is a registered (empty) panel name, because D2R hands PanelManager messages to UI
  listeners only for known panels. `n` indexes `BUTTONS` in the layout tool. The listener consumes the message; the button work runs on the next UI
  tick.
- Result names, the page line and the status are native `TextBoxWidget`s (`RowText<n>`, `HeaderText`, `StatusText<n>`, empty in the layout). WidgetService has no
  "set text", so the plugin calls D2R's own setter on the UI thread (`ApplyTexts` in `devmenu.cpp`, addresses in [d2r-addresses.md](d2r-addresses.md)), only for a line that
  changed and for every line when the panel opens or the graphics mode changes. Lines are cut to the character counts of `Metrics` (`Ellipsize`); the status wraps to three
  lines (`WrapText`, unit tested).
- These lines used to be drawn by D2RLoader's OverlayService. The calls returned Success, but nothing appeared on the owner's screen (2026-11-10, HD, window in front), so
  the menu no longer draws overlay text. Native text is in background screenshots, so the in-game check shows it.
- The search box text comes from `getInputText`. It is only ever used to filter the catalog or as a level number: nothing typed reaches a
  console or a game function.

## The catalog

`tools/devmenu_catalog.py` is a `tools/build.py` step (after the string merge). It writes
`work/mod/data/mxl2012-devmenu/catalog.tsv`, which installs as `<mod>.mpq/data/mxl2012-devmenu/catalog.tsv`. The plugin reads that file at load,
so a table change needs no plugin rebuild and no Median text is in git.

Line kinds and the native row rules are in the tool's docstring: names are in-game names (`strings_ns.effective_texts`, `d2r:<key>` overrides
included, the last line of a multi-line name). Uniques and set rows are record numbers with the `Expansion` lines not counted. Charms are the
uniques whose base type reaches `char`; the 46 include retired rows (tagged). Runeword kits take the compatible armour or weapon with the
smallest area and enough sockets, else the one with the most.

A missing or unreadable catalog leaves the menu off ("Catalog file not found in the mod").

## The gate: single player only

`devmenu_logic.h` `Gate()` runs when an action is queued and again on the game thread when it runs. All must hold:

- the catalog loaded;
- a client player exists;
- a **server frame of this process** found that player (`g_hostPlayer == g_clientPlayer`): false on a joiner's client, where this process has no
  server for the game;
- the local server game has **exactly one client** (walk of `game+0x138`, next at `client+0x628`);
- this process has **no TCP listener on the game port 4000** (`GetExtendedTcpTable`, IPv4 and IPv6, by owning process id). A TCP host listens there
  while hosting, so this also covers an empty hosted game. Only that port counts: single player itself listens on 30001 (loopback game server). When
  the table cannot be read, the gate says "listening": it fails closed.

D2RLoader's SDK has no single-player query (a successful `runOnGameThread` does not separate a TCP host from single player, `threads.h`). The
socket test is the extra check for that case. Its limits: it answers for this process only, so a third-party proxy that accepts connections for
the game would pass.

## Mutations

All in a loader game-thread callback (`runOnGameThread`), one at a time (`g_busy`), the row re-read from the catalog there:

- **Items:** `ItemService::createItem`, backpack then Cube then personal stash; set or unique by forced row (`AllowDuplicateUnique` for uniques),
  identified, item level 127 (the serializer keeps 100-127; many Median rows are above 99). The row of the result is compared with the wanted row.
  The service answers `Unsupported` for many tries of a forced set amulet row and creates it on a later one, so a forced row gets up to 64 tries per
  container. Nothing goes to the ground: `Ground` placement crashed this build in the item service (`BC_ASSERT hRoom`), with `Automatic` and with
  `Exact` at the player's feet. An item that fits nowhere is not made, and the status says so.
- **Kits:** the base with its sockets, then each rune, each by the same placement. `executeTransaction` with no inputs returns `InvalidArgument`, so
  a kit is not all-or-nothing: a full character gets what fits and the status counts it.
- **Travel:** the harness's route: D2R's warp `0x488180` inside an act; across acts the NPC travel `0x4f2e40` to the act's town, a 2 s settle, then the
  warp. The server frame watches for the level to change (15 s limit per hop) and reports arrival. Uber arenas (125-127, 133-137) are labelled
  "map only, the fight needs its normal summon"; Tristram and the Cow Level "portal area".
- **Raise:** the catalog's experience table and D2R's award `0x44f2e0`; refused unless the target is above the current level.
- **Unlocks:** the waypoint setter `0x3d6890` on the records of all three difficulties, for every waypoint number of levels.txt, and the quest
  bits 0 and 12 of words 7, 15, 23, 26 and 28 (the act tabs). Word 26 is Terror's End, so that quest reads as done on each difficulty.
- **Quests:** the loader's `cheat quests` through the `ExecuteConsoleCommand` export, only after the warning and Confirm. Debug mode is switched on
  around it if it was off and back off after. Rewards are not guaranteed; the per-quest reward work is separate.

No per-character marker: the SDK offers no per-character plugin data, and the research's fallback (a side file) would not follow the character;
actions are only in the plugin log.
