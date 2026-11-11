# invtabs: the controller tab of the charm inventory

The gamepad side of invtabs (D2R-XL 2012's own charm inventory, docs/invtabs.md): a "Charm Inventory" entry in D2R's gamepad
menu that works like the one in Dimentio's CharmInv 1.0.1 (bundled today, docs/bundled-plugins.md). Files:

| File | What |
|-|-|
| `tools/invtabs_pad.py` | the panel layout's reference generator (grid size a parameter, default 10 x 6), art spec, golden data |
| `tools/tests/test_invtabs_pad.py` | its tests |
| `invtabs/src/pad_layout.h` | the same layout at run time (no SDK), the panel art |
| `invtabs/src/pad_route.h`, `pad_route.cpp` | registration with D2RLoader: art, label string, layout, panel, grid binding, controller route |
| `invtabs/src/pad_tests.cpp`, `pad_golden.inc` | C++ test: layouts byte for byte against the generator, registration against fake services |

## Names and interfaces assumed

From the core's draft (docs/invtabs.md, lane invtabs). If the core changes one of them, change it here and in both generators.

| Name | Value |
|-|-|
| plugin id | `invtabs` |
| custom page | the core's `Inventory::PageRegistrationHandle` (logical id `charms`, page 6 of the player) |
| tab slot N, marker | grid widget `chronicleFlourishOffset {7400 + N, 7400}`; the core's grid wrappers find a grid by it (charm tab: N = 0) |
| grid child name | `invtabs/Grid` (the binding's `childName`) |
| summary area | a child `invtabs/Summary` (plain `Widget`) at the top of the panel: the summary lane fills it (rect: `geometry()["summary"]`) |
| our panel | `invtabs/Pad<N>`, layout `data/global/ui/layouts/invtabs/Pad<N>hd.json` (registered in memory) |
| our art | sprite `d2rloader\invtabs\pad_<cols>x<rows>` (registered through the core's `RegisterSprite`, 1305 x 1421) |
| route label | `@invtabs:PadRouteLabel`, enUS "Charm Inventory" (strings file `data/local/lng/strings/d2rloader/invtabs/pad.json`) |
| tab size | the core's `[tabs.charms] columns, rows` (default 10 x 6) |

What the core calls and when: the header of `invtabs/src/pad_route.h`. In short: `invtabs::pad::Register(...)` at plugin
load after the page and the keyboard tab panels, `invtabs::pad::Unregister(...)` at unload. The core also adds
`invtabs/src/pad_route.cpp` to the plugin and `pad_tests.cpp` + `pad_route.cpp` as a test executable (the pad lane does not
edit CMake).

## How CharmInv 1.0.1's controller tab works (observed)

Release-style install (0.1.19 package, CharmInv + Controller QOL Updates bundled, dev core DLL for the harness), scripted pad
(`h pad`, tools/pad_input.py), runs `mxl2012-runs/invtabs/pad/game/checks-20261111-*-s4`, contact sheets in
`mxl2012-runs/invtabs/pad/smoke/` (r2_*, r3_*, r4_*). Driver: `mxl2012-runs/invtabs/pad/scripts/pad_observe.py`.

Files (MPQ JSON and the DLL's string table only; no code read):

- one controller layout, `data/global/ui/layouts/controller/charm-inv/CharmInvControllerPanelhd.json`: root `Panel`
  `charm-inv/CharmInvControllerPanel`, priority 10, rect `$ConsoleLeftPanelRect`, anchor `$LeftPanelAnchor`, **no
  `defaultWidget`**; children: a `ClickCatcherWidget` (fitToParent), an `ImageWidget` (1305 x 1409 art,
  `d2rloader/charm-inv/charminv_controller_bg`), an `InventoryGridWidget` `charm-inv/InventoryGrid` at x 163, y 893,
  cellCount 10 x 4, cellSize `$ItemCellSize`, navigation `right: {panelBoundary: true}`;
- the art: dark stone, a large charm-bundle illustration in the upper half (decoration only, no text, no bonus summary),
  the 10 x 4 cell frame at the bottom;
- the DLL registers that panel and one controller route with the label `@charm-inv:CharmInvPanelTitle` ("Charm Inventory").

Behaviour:

| What | Observed |
|-|-|
| menu | Start opens D2R's menu; the tab strip reads Quest Log, Character, Inventory, **Charm Inventory**, Skill Tree, Options |
| tab switching | RT / LT step through the tabs (RT from Inventory opens Charm Inventory); RB / LB do nothing there. D-pad up from the paperdoll's top or a grid's top row reaches the tab strip; left / right move along it, A opens the tab |
| screen | his panel on the left, D2R's player inventory on the right (the route's PairWithPlayerInventory), like the Cube or hireling inventory |
| focus at open | stays in the inventory (his panel has no `defaultWidget`); the first D-pad press moves inside the inventory |
| crossing | left from the backpack's left column enters his grid at its right side (top row); right from his grid's last column goes back to the inventory (his layout's `panelBoundary`; not pressed in the runs) |
| edges | down stops at his last row (no wrap); up from his top row goes to the tab strip |
| buttons on his grid | A places the cursor item (legend "A Place"; page 6 0 -> 1 in run `checks-20261111-125414-s4`); on an item the legends read "A Pick Up", "X Drop"; a charm's tooltip adds his line "Keep in Inventory or Charm Inventory to Gain Bonus / [LB + X] Transfer" |
| legends | D2R's own: Open Cube, Hold to Sort (on a grid), Show Ranges, Close Menu (B) |
| legacy graphics | the gamepad menu stays HD; the same panel |
| `charminv open` (console) with the gamepad UI on | opens his keyboard panel on the right without pad focus: the pad then acts on the world (A opened the stash nearby). Not the way in |

A first run once ended the game process (no crash file) at Start right after B from a menu whose focus was on the tab strip;
the same sequence in the next run worked (row "Start after B with the tab strip focused" ok). Not reproduced; noted only.

## How D2R builds the controller menu and its focus graph

D2R 3.3's controller layouts (extract `data/global/ui/layouts/controller/`):

- `uiswitcherhd.json` lists the menu's panels: party, quest_log, character, inventory, skills_tree, hireling_inventory,
  pause; the interruptable ones (stash, horadric_cube, vendor, imbue, trade, waypoints, scroll_of_inifuss) replace the
  left side. The tab strip and RT / LT paging belong to that switcher.
- `_profilehd.json`: `$ConsoleLeftPanelRect` (x -1366, y -582, 1305 x 1421) for the left panel,
  `$ConsoleRightPanelRect` (x -8, y -608, 1408 x 1486) for the inventory, `$LeftPanelAnchor` (0.5, 0.397).
- Focus: every focusable widget has a `navigation` object (`up`/`down`/`left`/`right`: a widget name, or
  `{"panelBoundary": true}`). A panel's `defaultWidget` gets the focus when it opens. Left panels (Cube, hireling, stash) put
  `right: panelBoundary` on their rightmost widgets; the inventory puts `left: panelBoundary` on its left edge (right weapon
  slot, gloves, the backpack grid, gold). A boundary press moves to the nearest focusable widget of the other panel. Grid
  widgets navigate cell by cell inside `cellCount` and use their `navigation` at the edges.
- Our mod's controller inventory (tools/pad_ui.py) keeps those edges and adds the Send to stash buttons between gloves and
  grid (gloves down to send, send down to grid, send left = panelBoundary).

What a plugin needs for a controller tab bound to page 6 (SDK `panels.h`, pin 717f727):

1. a panel layout rooted at `<plugin-id>/<localId>` with `$ConsoleLeftPanelRect` and an `InventoryGridWidget` whose
   rightmost cells (`navigation.right`) are `panelBoundary`; registered as a resource at
   `data/global/ui/layouts/<plugin-id>/<localId>hd.json` (or shipped in the MPQ);
2. `registerPanel` (local id), then `bindPlayerPageGrid` (panel, page handle, the grid's child name);
3. `registerControllerRoute` with `PairWithPlayerInventory`, `AfterPlayerInventory`, the panel and a label key starting
   with `@` (a string in the plugin's namespace). All during plugin load; **one route globally**: a second plugin gets
   `Conflict`.

## Our tab

Layout (`py -3 -I tools/invtabs_pad.py layout 10 6`):

| Part | Where (panel pixels, 1305 x 1421) |
|-|-|
| art `pad_<c>x<r>` | 0, 0, full panel; drawn at load by `pad_layout.h` (stone, gold rim, sunken summary well, cells) |
| summary `invtabs/Summary` | x 60, y 60, width 1185, down to 30 above the grid (10 x 6: 693 high; never under 240) |
| grid `invtabs/Grid` | bottom edge at y 1371, centred (10 x 6: x 163, y 783, scale 1); wider than 12 columns or too tall for a 240 summary: `rect.scale` (16 x 16: 0.663) |

Differences from CharmInv, on purpose:

- `defaultWidget` is our grid: RT into the tab puts the focus on the charms, not in the inventory;
- cellCount is the tab's size (CharmInv: 10 x 4 fixed); the grid carries the core's marker for tab N, so the core's grid
  wrappers map its cells onto the tab's area of the 16 x 16 page;
- the upper part is the summary area, not decoration.

Same as CharmInv: route after Inventory paired with the inventory, `right: panelBoundary` from the grid, A / X / Y / sticks are
D2R's own grid controls. A charm moves between the backpack and the tab with A (pick up) and A (place) across the boundary.
An LB + X transfer like CharmInv's is not part of this module (open below).

## The Send to stash regression (0.1.19 smoke, row "A on Send to stash")

The button is reachable; the check's route moved. With CharmInv's route registered, the right weapon slot's
`left: panelBoundary` on the Inventory tab no longer does nothing: it jumps into the backpack grid's top-left cell. cqol's
`INV_NAV` pressed left twice (head, then the boundary), so the following downs walked the grid and A hit an empty cell.
Fix (separate commit, tools/cqol_checks.py): one `left` only; `up up up left down` reaches the gloves, `down` the Send to stash
button, `down` the grid, `up` back to the button. Verified in game on the 0.1.19 package with CharmInv
(`checks-20261111-124328-s4`: rows "inventory focus walk" ok, "A on Send to stash" ok, backpack 4 -> 3).

Our tab keeps it reachable: the inventory's own graph is untouched (the route only adds a left panel on its own tab), the
boundary from the inventory lands in our grid only on the Charm Inventory tab, and the gloves / send / grid links stay
D2R's and pad_ui.py's.

## Art spec

`py -3 -I tools/invtabs_pad.py art 10 6` prints the sprite path, panel size, summary well, grid rect, scale and every cell
rectangle. The art lane may replace the drawn art with a painted one of the same size per tab size; the cells must stay at
those rectangles (the grid widget draws items there).

## Tests

- `py -3 -I -m unittest discover -s tools/tests -p test_invtabs_pad.py`: 9 tests (geometry for every size, scale text,
  names, golden file current).
- `pad_tests.exe` (built from `pad_tests.cpp` + `pad_route.cpp` with the SDK include path, /W4 /WX): the six golden layouts,
  geometry of all 256 sizes, registration order and rollback (route taken, bad size, old SDK). Passes.
- In game (stage 3, check `invtabs_pad`, tools/invtabs_pad_checks.py, run `checks-20261111-194228-s2`): the menu entry
  after Inventory, RB / LB paging in a dev install (RT / LT with Controller QOL Updates), focus on our grid at open, a
  charm moved both ways across the panel boundary with A, the summary on the panel (the core fills `invtabs/Summary`'s
  area), Send to stash still working. docs/invtabs.md "Stage 3".

## Open

- **Core grid wrappers and cellCount**: the Pad grid has cellCount = tab size, the keyboard grids 16 x 16. The core must
  check that its wrappers (valid cell, cell rect, point to cell) take a grid's own cellCount, and that cell (0, 0) maps to
  the area's top-left.
- **More than one tab on the pad**: one route, one panel. Paging between tabs inside the panel (e.g. LB / RB while the grid has
  focus) needs input the SDK does not offer to layouts yet; until then the pad shows the charm tab only.
- **Summary focus**: the summary is not focusable; a long summary needs a scroll (right stick?) the summary lane decides.
- **Label string at run time**: the strings resource is registered at load; if D2RLoader reads string files only at launch,
  the core ships `pad.json` in its MPQ instead (`Options.labelText = nullptr`).
- **LB + X transfer** (CharmInv's): backpack <-> charm tab with one press; needs an item move the core owns.
