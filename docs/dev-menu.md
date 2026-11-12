# Developer menu (plugin part `devmenu`)

For players: [dev-menu-guide.md](dev-menu-guide.md). Off word `devmenu`. Code: `plugin/src/devmenu.cpp`, pure rules in `plugin/src/devmenu_logic.h`
(test `devmenu_tests`), the parts it shares with the wiki panel ([wiki-panel.md](wiki-panel.md): layout and button registration, the text setter,
the typing fix, reading the catalog file) in `plugin/src/panel_shared.cpp` and `panel_logic.h` (test `panel_tests`), layouts from `tools/devmenu_layout.py` (`plugin/src/mxl_devmenu_layout.h`, committed, `tools/tests/test_devmenu_layout.py`
checks it is current), catalog from `tools/devmenu_catalog.py`, in-game check `devmenu` (`tools/devmenu_checks.py`).

## What it is

One native D2R panel, `mxl2012-core/DevMenu`, in HD and classic layouts, opened by the Controls action `mxl_dev_menu` ("Developer Menu",
category "D2R-XL 2012", default Ctrl+F12, rebindable in `input-bindings.toml` and the Controls menu). Every player gets it in single player.
No `MXL_DEVMENU` build option: the release build has it too. It does not use the test harness; the harness verb `devmenu`
(`open|close|press <button>|input <text>|state`) exists in dev builds only.

## How the panel is put together

- One window: a single frame and background behind everything (first child `Background`). HD uses D2R's wide panel art
  `PANEL\Options\FrontEndOptionsBG` (1950 x 1635, the Chronicle panel's), scaled 0.92 to 1794 x 1504: as tall as the side panels, so it sits where
  the 0.1.18 panel (`PANEL\panel_bg`, 1162 x 1507) did, and 632 units wider; the close button is D2R's `PANEL\closebtn_4x` where the Chronicle
  panel has it. Classic graphics have no plain panel art (`MENU\dialogbackground` has input boxes painted in), so there it is one
  `RectangleWidget` (dark fill, gold border), 760 x 502 at the top of the 800 x 600 picture (20 units free at each side). Until 0.1.18 HD stacked
  three modal backgrounds, with seams between them.
- Buttons, tabs and the search box are native widgets. The tab row and the category row are centred, each of one button size with equal gaps; the
  search label and its box are one centred group, the label right-aligned against the box. HD buttons are `ModalButton` scaled so each label
  fits one line (tabs 308, categories 224, actions 690 units wide). Classic button art is drawn at its own size whatever the layout's `scale`
  (only the text moves with it: 0.1.18's classic action buttons drew their label beside a small button), so classic rows use art of the
  right width instead, labels in the `8pt` font (8ptE read poorly on the stone): tabs `FrontEnd\MediumButtonBlank` (128), categories
  `FrontEnd\OkCancelButtonBlank` (96), actions `FrontEnd\WideButtonBlank` (272; a two-piece art that needs the rect's width and height, or
  its label wraps after every letter), close `PANEL\buysellbtn` frames 10 / 11 as the classic inventory's. One tab shows one action, at the
  same place; Confirm sits under the Quests button. The Quests action reads "Advanced: complete quests" (until 0.1.18 with "(rewards not
  guaranteed)" on a second line): the warning is the tab's page line right under it, and Confirm's. Classic graphics list 8 rows a page
  (9 before), HD 12.
- Button clicks send
  `PanelManager:OpenPanel:mxl2012-core/DevMenuB_<n>`; each `n` is a registered (empty) panel name, because D2R hands PanelManager messages to UI
  listeners only for known panels. `n` indexes `BUTTONS` in the layout tool. The listener consumes the message; the button work runs on the next UI
  tick.
- Result names, the page line and the status are native `TextBoxWidget`s (`RowText<n>`, `HeaderText<n>`, `StatusText<n>`, empty in the layout). WidgetService has no
  "set text", so the plugin calls D2R's own setter on the UI thread (`ApplyTexts` in `devmenu.cpp`, addresses in [d2r-addresses.md](d2r-addresses.md)), only for a line that
  changed and for every line when the panel opens or the graphics mode changes. Rows are cut to the character counts of `Metrics` (`Ellipsize`); the page line wraps to two
  lines and the status to four (`WrapText`, unit tested), so the Quests warning is no longer cut ("...Rewa...", 0.1.18). The counts allow 18.5 panel units per
  character in HD (rows 84, page line 80, status 88; measured about 17 on the owner's 0.1.18 screenshot) and 6.4 in classic (rows 108, page line 102,
  status 115; measured 6.0 to 6.2). The longest catalog row, "Welcome to Old Bremmtown  (Act 5)  [map only, the fight needs its normal summon]", is
  80 characters; uber rows ("Cathedral of Vanity (Underground Passage Level 1)") and Cornerstone rows ("Cornerstone of the World: APF-10 'Maelstrom'
  MkIV (Assassin)", 60) fit whole. `tools/tests/test_devmenu_layout.py` (class `Geometry`) checks label widths, centred rows, sections that do not
  overlap, every widget inside the panel, the built catalog's longest row, and the panel inside the screen at 1280 x 720 and 1600 x 900.
- These lines used to be drawn by D2RLoader's OverlayService. The calls returned Success, but nothing appeared on the owner's screen (2026-11-10, HD, window in front), so
  the menu no longer draws overlay text. Native text is in background screenshots, so the in-game check shows it.
- The search box text comes from `getInputText`. It is only ever used to filter the catalog or as a level number: nothing typed reaches a
  console or a game function.
- **Typing.** A click on the box gives it the keyboard until the next click elsewhere (a button, a row, the game) or the menu closes. While it
  has the keyboard, a printable key (letters, digits, space, punctuation, numpad digits; no Ctrl or Alt) reaches D2R as the unbound key F24 (a
  subclass of the game's own window swaps the key of its WM_KEYDOWN / WM_KEYUP; no system hook), so no binding runs and D2R types the key's
  character as for any unbound key; Backspace, Enter, the arrows, Home, End and Delete edit in the box with their bindings marked handled. Esc
  and Ctrl+F12 still close the menu; with the menu closed or the box without the keyboard every key is the game's. In 0.1.18 a key with a
  binding (`A`, the digits, `I`) ran its command and never reached the box. Why and the addresses: [d2r-addresses.md](d2r-addresses.md)
  "Text boxes and key bindings".

## The catalog

`tools/devmenu_catalog.py` is a `tools/build.py` step (after the string merge). It writes
`work/mod/data/mxl2012-devmenu/catalog.tsv`, which installs as `<mod>.mpq/data/mxl2012-devmenu/catalog.tsv`. The plugin reads that file at load,
so a table change needs no plugin rebuild and no Median text is in git.

Line kinds and the native row rules are in the tool's docstring: names are in-game names (`strings_ns.effective_texts`, `d2r:<key>` overrides
included, the last line of a multi-line name). Uniques and set rows are record numbers with the `Expansion` lines not counted. Charms are the
uniques whose base type reaches `char`; the 46 include retired rows (tagged). Runeword kits take the compatible armour or weapon with the
smallest area and enough sockets, else the one with the most.

Unique rows that share one name and give exactly one `oskill` are labelled with that skill: `<name>: <skill> (<class>)` (no class part for a
skill of no class). That is Cornerstone of the World (`mxl2012:mxlname_2`, base `jew`): Median 2012 v005 has 350 rows of it, one per skill,
`oskill <skill id>` 1 and `levelreq` 10, of which 149 are spawnable (`enabled` 1 in Median's table) and listed; the other 201 never drop in the
mod and are left out like any unspawnable unique. The skill is the row, not a roll, so a row's arrow makes that exact jewel through the forced
row like every unique, and the jewel keeps its row (and so its skill) in the save like any unique. A search finds the jewel by its name, the skill,
or the class, in any order ("cornerstone", "ghost arrow", "cornerstone amazon"). Skill names come from skilldesc `str name`, the class from
skills.txt `charclass`.

**Uber levels** (format 3, line `U`): the levels whose entrance label (levels.txt `LevelWarp`) reads "DANGER - Uberquest Area", 16 in
Median 2012 v005, each with its entry level: the `Vis` link (the area holding its entrance) or, for the three without one (the Hell1-3 slots),
the level the game puts their red portal in (`hellwrpN` / `hellwrpW` presets): Frigid Highlands, Arreat Plateau, Frozen Tundra.

| Uber level (map) | id | Arrow goes to (id) |
|-|-|-|
| Duncraig (`epicwhiners`) | 13 | Cave Level 1 (9) |
| Cathedral of Vanity (`Inarius`) | 14 | Underground Passage Level 1 (10) |
| Infernal Cave (`CaveRoom5`) | 16 | Pit Level 1 (12) |
| Ureh (`downtown`) | 18 | Burial Grounds (17) |
| Fauztinville (`cypherpunk`) | 59 | Stony Tomb Level 1 (55) |
| Tran Athulua (`desertpeak`) | 60 | Halls of the Dead Level 2 (57) |
| Dimensional Sanctum (`belial`) | 65 | Lost City (44) |
| Kurast 3000 BA (`excelsior3`) | 84 | Spider Forest (76) |
| The Proving Grounds (`DungRm6A`) | 90 | Swampy Pit Level 2 (87) |
| Vizjun (`glados`) | 95 | Kurast Bazaar (80) |
| Azmodan's Reliquary (`Temple5` / `Temple6`) | 96 | Upper Kurast (81) |
| Rathma Square (`moskvich`) | 98 | Kurast Causeway (82) |
| Island of the Sunless Sea (`rockisdead`) | 116 | Glacial Trail (115) |
| Welcome to Toraja (`macumba`) | 125 | Frigid Highlands (111), red portal |
| Welcome to Old Bremmtown (`borgir`) | 126 | Arreat Plateau (112), red portal |
| Welcome to Khalimgrad (`charismatic`) | 127 | Frozen Tundra (117), red portal |

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
- **Sockets:** a normal base or misc item is made with its maximum number of empty sockets, worked out by the catalog (`max_sockets`, unit
  tested) the way 1.13c and D2R limit sockets: the item type's `MaxSockets1/2/3` (Median's `MaxSock1/25/40`) by item level against the thresholds
  25 / 40, never more than the base's `gemsockets`, at the spawn item level 99 (so the third column). Median's weapon and armour types allow 6 at
  every level, so a base gets its `gemsockets`; rings, amulets, jewels, charms, potions and quest items (types with 0) get none. Uniques and set
  items ask for no sockets: their sockets are the row's fixed `sock` property (1,828 unique and 170 set rows have one) or none, as Median drops
  them, and Median's socket recipe (845) only takes normal items. The status says "with n of m sockets". Catalog format 2 adds the column.
  Every spawned item is created identified (`SpawnIdentified`). Until lane devmenu4 normal items were made unidentified (`stateFlags` 0), and
  D2R's tooltip shows an unidentified item's sockets as "Max Sockets: N"; the item service had set both the count (stat 194) and the socketed
  flag (0x800, flag word 0x82800) all along. Identified, the tooltip reads "Socketed (N)" and a gem clicked onto the item goes in (check
  `devmenutype`: an Amethyst into the Balanced Axe, "Gemmed Balanced Axe", +30% attack rating). After creation the native item is read back
  (`CheckSockets`: count, socketed, identified; harness `devmenu state` `sockfails`, `lastitemflags`).
- **Kits:** the base with exactly the sockets its runes need (not the maximum: a runeword needs the exact count), then each rune, each by the same placement. `executeTransaction` with no inputs returns `InvalidArgument`, so
  a kit is not all-or-nothing: a full character gets what fits and the status counts it.
- **Travel:** the harness's route: D2R's warp `0x488180` inside an act; across acts the NPC travel `0x4f2e40` to the act's town, a 2 s settle, then the
  warp. The server frame watches for the level to change (15 s limit per hop) and reports arrival. Uber arenas (125-127, 133-137) are labelled
  "map only, the fight needs its normal summon"; Tristram and the Cow Level "portal area". A search that matches an uber level (by its name,
  or "uber" for all) lists it first under the heading "Uber levels" as `<name> (<entry area>)`; its arrow travels to the entry area, never into
  the uber level, and the arrival says "right before <name>: its entrance / red portal is in this area". The player lands where the warp puts
  anyone arriving in that area (its waypoint or default entry), not at the entrance tile itself: the warp's entry search (`0x3dac20`) picks
  spots by tile kind, not by destination. The areas follow under "Areas" as before, the uber level included (its arrow goes inside).
- **Raise:** the catalog's experience table and D2R's award `0x44f2e0`; refused unless the target is above the current level.
- **Unlocks:** the waypoint setter `0x3d6890` on the records of all three difficulties, for every waypoint number of levels.txt, and the quest
  bits 0 and 12 of words 7, 15, 23, 26 and 28 (the act tabs). Word 26 is Terror's End, so that quest reads as done on each difficulty.
- **Quests:** the loader's `cheat quests` through the `ExecuteConsoleCommand` export, only after the warning and Confirm. Debug mode is switched on
  around it if it was off and back off after. Rewards are not guaranteed; the per-quest reward work is separate.

No per-character marker: the SDK offers no per-character plugin data, and the research's fallback (a side file) would not follow the character;
actions are only in the plugin log.
