# Inventory / stash auto sort with D2R-XL 2012 (research, lane autosort, 2026-11-05)

Owner question for 0.1.12 (2026-11-05): does auto sort work with the mod, or could it? Short answer: **there is no
sort a mouse and keyboard player can use today.** D2R 3.3 has a sort, but only for controller players. D2RLoader 1.3.1
and the plugins we plan to ship have none. A sort of our own would be a new plugin part, about a week of work.

## 1. What exists

| Source | Sort? | Evidence |
|-|-|-|
| D2R 3.3 (build 93847), mouse and keyboard | **No** | No sort key in `keybinds.json` or the Options key list. No layout in `data/global/ui/layouts` (pc or controller) has a sort button. The string `strSort` ("Sort", ui.json id 5294) is in the tables, but no layout uses it |
| D2R 3.3, controller | **Yes: "Hold to Sort"** (hold R3 on a grid) | String `ControllerPromptHoldToSortInventory` (ui-controller.json id 26031). In the 93847 dump it is read only by the inventory grid widget's controller legend builder `0x2c8cc2` (`D2Client\src\UI\Widgets\InventoryGridWidget.cpp`), next to `ControllerPromptItemCompare` and `OpenCurrentStashLegend`. It is shown when the widget's grid kind byte (`+0x630`) is neither -1 nor 1. Players describe it as a controller-only action (R3); it is not bound for mouse and keyboard |
| D2R 3.3 server | no "sort" packet found | The "Failed to rearrange inventory" log lines in `PlrMsg.cpp` belong to the item move packets: 0x56 (`0x4ab980`, 21 bytes: item, stash, position, target page, target position), 0x5d (`0x4ac160`, belt auto-fill) and 0x5e (`0x4a8c40`). So the controller sort is most likely laid out by the client and sent as single moves. Not proved: the sort routine itself was not found |
| D2RLoader 1.3.1 | **No** | `d2rloader.toml` sections `game_rules`, `automap`, `items`, `player`, `stash` (shared tab count, material stack limit), backups, advanced, developer: no sort option. Its input bindings are only `d2rloader/console` and `d2rloader/cube_transmute`. No sort string in D2RCore.dll, D2R_loader.dll or D2RLoader.exe that is not a library's |
| PyreFly's plugins (all 12 in Pyre-Flies/D2R-Mods) | **No** | controller-qol, pyre-lootfilter, pyre-stashsearch, running-defense, ultrawide, item-roll-ranges, gem-bag-ui, inventory-deposit, floating-damage, always-show-sockets, day-night-cycle, map-assistance. The closest are the deposit actions (inventory-deposit "Deposit All", controller-qol LB + L3): they move gems, runes, materials and rejuvenations into the advanced stash; nothing reorders. controller-qol uses R3 for its own actions (LB + R3 belt fill, skill aim) and does not mention D2R's sort |
| Other bundled candidates (buff HUD, Auto Belt Refill) | No | docs/bundled-plugins.md |
| Median XL 2012 itself (1.13c) | Yes, a stash **Sort** button | D2Sigma's stash panel (`0x113cf0`) has Prev / Next / Sort / Mode buttons (docs/d2r-addresses.md section 18). The port does not have it (testing.md: "personal pages 3-10 and Sort are not built") |

## 2. In-game test

**Not run.** The only sort in the game needs a controller (XInput) in the game window. The slot rules allow
background mouse and keyboard input only. A virtual gamepad needs a driver install (a system change, forbidden here),
and calling the sort through the harness would need new harness code (this lane makes no mod code changes). So the
checks the owner listed (inventory, personal page 1 and 2, shared pages; Median's large items, charms, quest items, HD
and legacy) are open for D2R's controller sort.

What can be said without a run:

- A mouse and keyboard player cannot use it at all. That is most of our players, so it does not answer the request even
  if it works.
- The controller legend is built by the inventory grid widget. Not checked: whether legacy graphics (Ctrl + G) shows
  the legend and allows the sort.
- Personal page 2 is D2RLoader's custom page panel (plugin part `stashpages`), not a D2R grid. D2R's sort will not
  know it.
- Charms would stay in the inventory if the sort only moves items within the grid it runs on. Not proved.

If the owner wants it checked, the test is about 15 minutes by hand with a real controller on slot 2. Back up the save
first, then hold R3 on each grid listed above and look at the result in HD and in legacy.

## 3. A sort of our own (plugin part `autosort`)

A mxl2012-core part, the same way as `stashpages` and the harness item verbs. It works with mouse and keyboard and covers
every page, the custom page too.

### Behaviour

- Trigger: an InputService action `mxl_sort` (free key, rebindable as `mxl_pickup_toggle` is), and later a small button
  on the inventory and stash panels (HD layout json; legacy needs a classic button, see docs/legacy-graphics.md).
- Scope: the grid under the cursor, or the open page. One grid per press; no moves between grids or pages.
- Never moved: the Horadric Cube; **charms** (Median's charms only work in the inventory, so the inventory sort leaves
  them where they are, or packs them into a block the player picks, and never sends them to the stash); quest items
  (Median's quest items and the Token, by itemtypes/quest flag); the belt; the RotW materials tab (it is a stack tab, not
  a grid); locked cells from an optional config (a column or a block kept free).
- Order (first try, owner to confirm): by size, largest first (Median's large items first, so they fit), then by
  type group (weapons, armour, jewellery, charms when the stash is sorted, runes / gems / materials, potions, other), then
  quality (unique, set, rare, magic, normal), then item code, then item level. Pack column by column, top to bottom, like
  Median's own Sort.
- The layout: compute the full target layout first. If it does not fit (it can happen with large items, a full stash
  and a fixed cube), do nothing and say so in chat.

### How the moves are done

- Single player and the game's host: run on the server side in one game tick: take every item to move off the grid,
  place each one at its target, check that the item count and ids are the same before and after; on any failed place,
  put everything back at its old cell. The harness already moves items on the server side (`place`, `move`,
  `packclear`, `stashprobe`), so the calls are known.
- A client that is not the host (TCP/IP, D2RLoader's online modes): only the move packets (0x56 and its neighbours)
  are possible, one item at a time through the cursor. That needs a free cell to swap through, and an interrupted sort
  leaves a half-sorted page (no loss, but a mess). First version: host only; elsewhere the action says "not
  available".
- Personal page 2 lives in D2RLoader's custom page storage: read and write it through the `stashpages` part's own
  functions (the same ones the harness verb `move <page>` uses), never through D2R's grid.
- Shared pages (3 normal + 7 added): D2R grids; same path as personal page 1.

### Effort and risks

| Work | Estimate |
|-|-|
| Layout code (packing, order, exclusions) with unit tests (pure C++, like `cooldowns_logic.h`) | 1.5 days |
| Server-side move with roll-back, per grid (inventory, personal 1, shared pages) | 1.5 days |
| Custom page 2 through `stashpages` | 0.5 day |
| Key binding, chat messages, config; button on the HD panels | 1 day (+1 for a legacy button) |
| In-game checks on slot 2 (HD and legacy; inventory, personal 1 / 2, shared; large items, charms, quest items, full grid, save + reload) | 1 day |

About 5 to 6 days in all.

Risks:

- **Item loss or copies** if a move fails half way. Mitigation: target layout first, count and id check, roll-back,
  and a save backup in the first test rounds. This is the main risk.
- **Grid asserts**: D2R asserts on bad cells (bug #393: `x >= 0 && x < pPage->bWidth`, a 0 x 0 item). Skip items with
  no size and check every target cell against the page size before any move.
- **The custom page**: page 2 is D2RLoader's storage. A sort there must go through the provider, or D2RCore refuses the
  load (testing.md "Stash pages: personal page 2").
- **Charms**: a bug that sends a charm to the stash makes the player lose its bonus, and nothing tells them. Keep charms
  out of the stash sort's input.
- **Multiplayer**: the packet path is slower and can be left half done. Leave it out of the first version.
- **Conflicts**: inventory-deposit and controller-qol (both on the ship list) move items too. Make sure a sort and a
  deposit cannot run in the same tick. D2R's own controller sort stays as it is.

## Open questions for the owner

1. Is it enough that controller players can sort today? If yes, someone with a real controller should run the test in
   section 2.
2. Should we build our own sort (section 3)? If yes: which sort order, should the inventory sort move charms at all,
   and is host only acceptable for the first version?
3. Should it work like Median 2012's Sort button (stash only), or should the inventory sort too?
