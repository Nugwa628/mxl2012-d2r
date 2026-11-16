# Auto Belt Refill for D2R-XL 2012

**Auto Belt Refill** is by **jaycachou-svg**: <https://github.com/jaycachou-svg/auto-belt-refill>. D2R-XL 2012 ships it from
0.1.15 with the author's permission (2026-11-06: use and customise it). The author's repository has no licence file, so this
permission is the only basis for shipping it.

The author's source is the submodule `third_party/auto-belt-refill`, pinned at commit `a3b6805` ("Add
Auto-belt-refill-v0.35.9"), folder `Auto-belt-refill-v0.35.9-EN`. It is never changed and never forked: `tools/build_beltrefill.ps1`
exports that commit and applies the files here at build time.

| File | What it is |
|-|-|
| `0001-pluginsdk-1.3.1.patch` | API renames for the PluginSDK of D2RLoader 1.3.1 (ABI 4): `abiVersion`, `InventoryService`, `ThreadService`, `InputService`, `LifecycleService`, the one-argument `QueryService`. No behaviour change |
| `0002-mxl2012-belt-rows.patch` | Rows per belt column for Median XL 2012's own belt codes (below) |
| `0003-mxl2012-match-first-slot.patch` | Our additions, each off unless the config turns it on: `match_first_slot` (each column refills with exactly the code in its first slot; a completely empty column refills nothing), `never_refill` (codes never learned or refilled: Median's elixirs and the Goodberry), `belt_counts` (a count on each column; how it is shown: 0006), console `belt-counts`. Pure logic in the new `belt_match_logic.h` |
| `0004-mxl2012-count-signatures.patch` | `belt_counts` finds its game data (the HD / legacy test and the classic screen size) by byte signatures at load, with the repo's scan (`invtabs/src/invtabs_logic.h`), instead of D2R 93847's fixed addresses; a signature that does not match exactly once turns the counts off with a log line (refilling is not affected) |
| `0005-refill-natives-by-signature.patch` | The refill's twelve game routines (`GetLocalPlayer` ... `BeltTransfer`, `Pickup` for `belt-verify` only) found at load by byte signatures (new `belt_natives.h`, with the repo's scan) instead of the author's fixed RVAs; each must match once and pass its cross-checks, else the refill is off with a log line and nothing is hooked or called. Kept separate so it can go to the author (the scan header, `invtabs_logic.h`, is standard C++ only) |
| `0006-mxl2012-counts-as-hud-text.patch` | `belt_counts` puts the counts in D2R's own HUD text boxes (`MxlBeltCount0`-`3`, `MxlBeltCountZero0`-`3`, which the mod's HUD layouts add on the belt's bottom-row cells) through D2R's UI root, panel / child lookup and text setter, found by the repo's signatures (`invtabs/src/summary_natives.h`), on the UI thread, only the texts that changed. Replaces the loader overlay drawing of 0003 / 0004, which never reached the screen (D2R-XL 2012 bug #613). Without those layout boxes nothing shows (a log line says so) |
| `0007-mxl2012-column-counts-and-reserve.patch` | The count on each column is the items in that belt column (red at 1 or 0, `BeltMatch::LowCount`), no longer the column's potion in the inventory and the belt together; that potion in the inventory (the refill's reserve) goes to a third box per column, `MxlBeltReserve0`-`3` ("+N"). The red boxes are renamed `MxlBeltCountLow0`-`3`. `belt-counts` logs both numbers |
| `tests/belt_match_tests.cpp` | Unit tests of `belt_match_logic.h` (`BeltMatchTests`, run by `tools/build_beltrefill.ps1`); with env `D2R_DUMP` (a 93847 dump, `tools/dump_image.py`) also the signatures in the real image |
| `CMakeLists.txt` | Release build against the project's PluginSDK (the author's CMakeLists.txt lists the sources next to it, the repo keeps them in `src/`) |
| `auto-belt-refill.toml` | The shipped config: `match_first_slot`, `belt_counts`, the elixirs and the Goodberry in `never_refill`, no fixed columns, no hotkeys bound |

## Note for the author: belt rows in Median XL 2012

The plugin takes the rows per column from the worn belt's item code (`RowsForBeltCode`), with D2R's codes (`lbl`, `vbl`, `mbl`,
`tbl`, `hbl`) and 4 rows for any other code. Median XL 2012 keeps D2R's `belts.txt`, but none of its 35 belts uses a D2R code:
they are `627`-`631`, `673`-`677`, `719`-`723`, `765`-`769`, `811`-`815`, `857`-`861` and `@28`-`@32` (Sash, Light Belt,
Belt, Heavy Belt and Plated Belt in grades 1-6 and Sacred), and the size goes by grade, not by name (`armor.txt` column
`belt`): grades 1-3 = 8 slots (2 rows), grades 4-5 = 12 slots (3 rows), grade 6 and Sacred = 16 slots (4 rows). So every
Median belt read as 4 rows. `0002` adds the 2- and 3-row codes to the switch; the 4-row ones already get the default.

A mod-independent fix would read the size from the game tables instead: the worn item's `belt` column (Items table) as an
index into `belts.txt` (`numboxes` / 4). (In D2R itself the default is right for the codes the switch leaves out: the
exceptional and elite belts `zlb` ... `uhc` are all `belts.txt` row 6, 16 slots.)
