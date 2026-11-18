# Charm-tab summary

A scrollable list at the top of the charm tab: the total bonuses of the charms in the tab that count, worded the way
the game words them in an item tooltip ("All Resists +10%", "Adds 5-10 fire damage", "+1 to Sorceress Skill Levels").

Code: `invtabs/src/summary_logic.h` (pure), `invtabs/src/summary.h` / `summary.cpp` (game side),
`invtabs/src/summary_natives.h` (signature patterns). Tests: `invtabs/tests/summary_test.cpp`,
`invtabs/tests/summary_sigs.py`. In-game proof: the TEST ONLY probe `invtabs/tests/summary_probe/`.

## Assumed core interface

The invtabs core (the plugin entry and the charm tab panel) is another lane's work. This module assumes the core does
the following. `summary.h` states the same thing at the top.

1. **Load.** `Summary::Init(gameModuleBase, log)` once. It scans `.text` for the patterns below. If a required one is
   missing, Init returns false, logs the reason, and every later call does nothing.
2. **Item enumeration is the core's job.** On charm tab open, and after every add, remove or move on the charm page,
   the core collects the client item units on that page (any order) and calls `Refresh(items, count)`. Refresh decides
   which items count and formats the totals.
3. **Layout.** When the core builds the charm tab's panel JSON (after Refresh), it reserves a band above the grid (a
   `SummaryHeight` of its choice) and splices `Fragment(mode, area)` into the panel's `children`. `area` is in panel
   coordinates. `mode` is `LayoutMode::Hd` for the HD layout file and `LayoutMode::Classic` for the legacy one.
4. **Re-registration before open.** `NeedsRelayout()` is true when a later Refresh produced more lines than the
   registered layout holds (HD only). The core then registers the layout again before the next open, as upstream
   SyncLayout does: `UnloadPanel` through `dispatchUiAction` if the panel was opened, `unregisterResource`,
   `registerResource`, then `openPanel`.
5. **Texts.** `ApplyTexts(panelName)` on the UI thread after the panel opened and after each Refresh while it is open.
   It finds the panel and its `SummaryLine<i>` rows by name and sets their text.
6. **Classic scrolling.** The legacy layout has a fixed window of rows. On a mouse wheel over the band the core calls
   `ScrollBy(lines)` and then `ApplyTexts`. HD scrolls by itself (ScrollViewWidget).

## What counts

- An item counts if its stats are merged into the player: `Merged(item, nullptr) != null` (0x2f8120, the same test
  the client charm refresh 0x1c9610 uses, docs/d2r-addresses.md 22c). This drops charms whose requirements are not met
  and the inactive copy of a duplicate carry1 charm. In game, the second Butcher's Tooth gave `counts=0`, the first
  `counts=1`.
- Each counting item's own list: `GetStatList(item, 0, 0x40)`, entries `{u16 layer, u16, u32 stat, i32 value, i32}`
  at list+0x30, count at list+0x38 (low 16 bits).
- `Sum` adds the entries per (stat, layer) in 64 bits, clamps the result to int32, and drops totals that come to zero.
  Layers (params) are separate stats: `83:1` (Sorceress skills) and `83:2` do not add up. Negative values add normally
  (+10 and -7 Dexterity show "+3 to Dexterity").

## Wording

The totals go into a fresh stat list (`AllocStatList(0, 0, 4, itemId)`, one `StatListAdd` per total). The tooltip's
own stat block writer `StatListText` (0x2da760) then formats it into a 32 KB buffer, with the first counting item as the
context unit, and the list is freed. That writer:

- groups stats the way tooltips do ("All Resists +10%", "+10 to all Attributes", "Adds 5-10 fire damage");
- leaves out hidden stats (itemstatcost descfunc 0), e.g. stat 82;
- writes lines in ascending `descpriority`. A tooltip shows them reversed, so `TooltipOrder` reverses them.

Colour codes (`ÿcX`, both encodings) are stripped. More than `MaxLines` (160) lines are cut, and the last line says how
many were left out (`... +N`).

If `StatListText` cannot be used, the fallback formats each total on its own with `FormatOne` (0x2d97e0), ordered by
`descpriority` (`OrderForDisplay`, with the row from `StatRecord` 0x2d9730). The fallback does not group stats. Both
are optional; without both, the summary stays off.

## Game functions (build 93847)

Every pattern matches exactly once in `.text` of the 93847 dump. `py -3 invtabs/tests/summary_sigs.py` checks them, and
`--make` rebuilds them. D2RCore (D2RLoader) replaces the entries of several stat functions with `jmp [slot]` thunks, so
most patterns are call sites. `rip` is the offset of the call's rel32 in the match.

| Name | Match at | Target | Where the pattern sits |
|-|-|-|-|
| GetStatList | 0x2DC55F | 0x2F5A00 | tooltip stat block builder 0x2dc4b0 |
| AllocStatList | 0x2DC595 | 0x2F7300 | same |
| DataFlag | 0x2DC5A4 | 0x34A0E0 | same |
| StatListAdd | 0x2F354F | 0x2F3330 | a stat list helper calling it |
| StatListText | 0x2DC7CA | 0x2DA760 | tooltip stat block builder 0x2dc4b0 |
| FreeStatList | 0x2DCC52 | 0x2F4180 | same |
| Merged | 0x1C97F1 | 0x2F8120 | client charm refresh 0x1c9610 |
| FormatOne | 0x14EB2B9 | 0x2D97E0 | Advanced Stats panel 0x14eb280 |
| StatRecord | 0x2DB733 | 0x2D9730 | per-level stat value 0x2db700 |
| UiRoot (data) | 0x83F3AE | 0x3440170 | UI root widget pointer |
| UiFindPanel | 0x843C34 | 0x89F760 | panel lookup by name |
| UiFindChild | 0x855C90 | 0x855C90 | entry pattern |
| TextBoxSetText | 0x86DD50 | 0x86DD50 | entry pattern |

Signatures are in `summary_natives.h`. `StatListText` is
`(u8 dataFlag, char* out, int outSize, Unit* ctx, StatList* list, int newline, int* hasLine, void* chronicle,
ChronicleSpan* span {u64, u8}, u8 bullet)`. The summary passes a zeroed span and no chronicle.

All calls into the game go through SEH-guarded wrappers in `summary.cpp`. A fault logs and returns empty, and does not
crash the game.

## UI

**HD.** A `ScrollViewWidget` "SummaryView" (`clipChildrenDraw`) with one `TextBoxWidget` "SummaryLine<i>" per line
(pitch 32, height 30, `$FontColorBlue`, `$SmallFontSize`, centred). To its right is a `ScrollControllerWidget`
"SummaryScroll" (width 26, gap 10), using the art `FrontEnd/HD/Final/FrontEnd_ScrollUpBtn`, `.../FrontEnd_ScrollDownBtn`
and `PauseMenu/VerticalIndicator`. Art paths use forward slashes: a single backslash breaks the JSON, and a unit test
checks that the fragment has none. The layout holds one row per line (at least a screenful), so the game scrolls it with
the wheel and the arrows.

**Classic (legacy).** A fixed window of rows (pitch 13, height 12, `fontType` 8pt, rgba 110,110,255). The window is
moved with `ScrollBy`, clamped so the last line ends at the bottom row (`ClampFirst`).

## Classic pages: grid, then stats (lane charmstats)

In legacy graphics the charm tab has two pages (owner request 2026-11-16): page 1 is the charm grid, page 2 the stats
list. A one-page panel only had room for 2 to 8 summary lines above the grid; page 2 shows 18 rows at a time in a box
of 282 x 251 (panel pixels (20,115)-(302,366)), scrolled with the wheel or PageUp / PageDown as before.

**Wrapping.** A classic text box does not wrap, so a long line ("1% Chance to cast level 20 Death Spiral when Struck")
ran over the box's sides. The classic rows now get the lines wrapped (`summary_logic.h` WrapLines): at most
`width / 7` characters a row (7 px is the 8pt font's widest average per character on game screenshots; 38 on the stats
page's 272 px of text), broken at a space, a word longer than a row cut. The continuation rows start with two spaces
and keep the line's colour (the list by charm). Wrapped rows count as rows: the 18 visible rows and the scrolling use
the wrapped list. HD keeps its lines unwrapped. The one-page panel wraps the same way. The rows are centred, so the
indent shows only as a small shift. `invtabs summary` also logs the classic rows (`summary classic: <n> line(s) in <r>
row(s), wrapped at <w> character(s)`, then `summary classic line <i>: ...`); the check `charmstats` asserts that every
row fits, each long line was split, and the words are the HD lines' words in order.

- **Switch:** two 24 x 24 buttons in the tab row (x 230 grid, x 254 stats, y 87), in the tab buttons' style: a grid
  glyph and a list glyph, the shown page's button with a gold rim and no click. Tooltips "Charm grid" / "Charm stats".
  Art: `data/global/ui/panel/invtabs_page.dc6`, 6 frames (grid normal, pressed, shown; stats normal, pressed, shown).
  The "all stats / by charm" button (x 282) shows on page 2 only.
- **Panels:** `invtabs_<tab>_grid.dc6` (the stash grid, no summary box) and `invtabs_<tab>_stats.dc6` (the big box, no
  grid), both built by `tools/invtabs_art.py` next to the one-page `invtabs_<tab>.dc6`.
- **Page 1 is tight** (owner, 2026-11-17): the grid's top line sits right under the tab row, and the stash's bottom band
  with the close button follows right under the grid. A 10 x 6 grid moves up 81 px (cell (0, 0) at y 117 instead of 198, close at
  y 302). The art ends there and the panel below it is transparent (`invtabs_legacy.paged_grid_shift`,
  `Lay::ClassicPagedGridShift`). The panel's click catcher still covers the full 320 x 432, so a click in that
  transparent strip does nothing, as on the other classic panels. Page 2 keeps the full height with its stats box. Its hidden grid
  stays at y 198.
- **Page 2 has no grid.** The layout keeps a hidden grid widget (marker 7402) so the plugin still reads the tab's items
  and the list stays current, but it is not drawn and takes no clicks or tooltips.
- **Also:** the console `invtabs page grid|stats|toggle` and the Controls action "Charm tab page: grid / stats
  (classic graphics)" (logical id `charm-page`, unbound by default). The legacy panel has no controller support, so a
  pad has no way to the page; the gamepad layout keeps its own list.
- The page is not saved; each game starts on page 1. Closing and reopening the tab keeps the page.
- **Falls back to one page** (log "charm tab in legacy graphics: one page: <reason>") when the summary is off, the tab
  has no classic layout, the page art is missing, more than 8 tabs share the row, or the click listener did not
  register. Otherwise the log says "charm tab in legacy graphics: two pages (grid, stats)".
- HD is unchanged: its band above the grid scrolls and has no such shortage of room.

## All stats or by charm

The list has two modes, switched by a button at the top right of the list (lane charmpage):

- **All stats** (the default): the sum above.
- **By charm**: each charm under its own name, in grid order. The charm tab comes first, row by row and left to right.
  The backpack's charms follow under a grey "In the inventory" heading when `inventory_charms` is on. A charm's name
  is gold (unique) or white. Its lines are its own stats, worded by the same stat block writer as the sum. A charm that
  does not count (level too low, or the second copy of a carry1 charm) is grey, with "(inactive)" after its name.
  Identical charms are not grouped: each copy is listed where it lies, so the second copy shows as inactive.
  A text box draws in the one colour of its style (colour codes print as text, docs/d2r-addresses.md "Text boxes"), so in
  this mode each row has four boxes at the same place (`SummaryLine<n>` blue, `...Gold`, `...Grey`, `...White`). The
  plugin fills the box of the line's colour and empties the other three (`summary_logic.h` SplitColour).

The names come from the mod's tables: a unique's `uniqueitems.txt` `index` cell (row = the item's unique index, item
data +0x34), any other charm's `namestr` (weapons, armor and misc in class order, "Expansion" rows left out). The
plugin reads these with D2RLoader's localization service (`mxl2012:Key`, then `Key`, then `d2r:Key`). If no string
is found, the key is split into words. Only the last line of a name is used, without colour codes.

The button's glyph shows the mode that a click switches to: a list of charms while the list shows the sum, a sum sign
while it shows each charm. Its tooltip says the same. A click (or the console `invtabs list all|charm|toggle`, or the
Controls action "Charm list: all stats / by charm", unbound by default) sets the mode. It then writes
`summary_list = "all"|"by_charm"` into `invtabs.toml`, replacing the value in place and keeping the comment and the
rest of the file (`invtabs_logic.h` SetConfigKey). Finally it builds the tab's layouts again with the other glyph,
closing and reopening the tab if it was open, as the summary's own relayout does. The choice is read at the next game
start.

- **HD:** `invtabs/ListMode`, a `ButtonWidget` of 56 x 56 in the summary band's top-right corner. The scroll bar
  starts 64 units lower, and the rows end where the button begins. Art: the mod's
  `data/hd/global/ui/panel/invtabs/listmode.sprite`, 8 frames: 0-3 the "by charm" glyph and 4-7 the "all stats"
  glyph, each normal, hovered, pressed and disabled. It is built by `tools/invtabs_hdart.py` in the style of
  `tools/hd_buttons.py`: D2R's stone rim and the stash cell well. Without it, the core draws a plain stand-in.
- **Classic:** a 24 x 24 button at the right end of the tab row (x 282). It is shown only when there are 10 tabs or
  fewer and the mod has `data/global/ui/panel/invtabs_listmode.dc6`: 4 frames, normal and pressed for each glyph, in
  the tab buttons' style (`tools/invtabs_art.py`). With the two pages (above) it shows on page 2 only.
- **Gamepad:** the controller panel keeps the sum. Its 20 rows are fixed and it has no scrolling, so a long list by
  charm would be cut off.
- The click reaches the plugin through an empty panel name of its own (`invtabs/ListMode`, no panel), which a shared
  event UI message listener consumes. This is the same way as `plugin/src/panel_shared.cpp`.

## Tests

- `invtabs/tests/summary_test.cpp`: a plain assert program with no framework, for sums, the inactive copy, params,
  negatives and clamping, ordering, line splitting and tooltip order, colour stripping, long lists and the classic
  window, layout (balanced brackets, no backslash, row counts), and the pattern parser and scanner. Build it with any
  C++20 compiler; it only includes `summary_logic.h` and `summary_natives.h` (relative paths):
  `cl /std:c++20 /EHsc invtabs/tests/summary_test.cpp`, or add it as a target to the invtabs tests CMake.
  Result: `summary_tests: all checks passed`.
- `py -3 invtabs/tests/summary_sigs.py`: all 13 patterns are unique and resolve to the expected RVA (list above).

## In-game proof

The probe (`invtabs/tests/summary_probe`, plugin id `invtabs-summary-probe`, TEST ONLY) uses `Summary` exactly as the
core would. Its console verbs are `summary-probe refresh | open [classic] | apply | scroll n | close`. It walks the
player's charms itself (fixed 93847 RVAs, test only) and shows the summary in a panel of its own. Both runs used slot 4
with a dev core build (harness, charmdup), a throwaway sorceress, and background input only. Evidence is in
`mxl2012-runs/invtabs/summary/live1` and `live2`.

Charms used (raw values; item stats below the valshift do not reach the client, so +20 life is `7=5120`):

| Item | Stats |
|-|-|
| a55 | 0=5 1=5 39=10 41=10 107:36=1 |
| a56 | 0=3 43=10 45=10 2=-7 82=50 83:1=1 |
| a57 | 1=-5 48=5 49=10 |
| a58 | 7=5120 9=2560 16=30 19=50 20=10 31=100 74=5 60=3 |
| a59 | 80=10 85=5 89=1 93=10 96=10 99=10 105=10 127=1 |
| a60 x2 | Butcher's Tooth (unique 183), one active, one inactive |

Results:

- Run 1 (`checks-20261111-134922-s4`): the inactive Butcher's Tooth was skipped. Summed lines match the charms'
  tooltips word for word (`tip_c1_a55.png`, `tip_c2_a56.png`, `tip_c3_a57.png`, `tip_bt_*.png`): "All Resists +10%",
  "Adds 5-10 fire damage", "+1 to Sorceress Skill Levels", "+3 to Dexterity". Stat 82 (hidden) has no line. 107:36
  has no line, and the charm's own tooltip shows none either.
- Run 2 (`checks-20261111-140734-s4`): 7 charms, 6 counted, 1 skipped, 31 totals, 25 lines (`probe.log`).
  - HD: `probe_hd_top.png` shows the first rows in tooltip order. Mouse wheel notches over the view (3, then 20 more,
    `probe_hd_wheel3.png`) scrolled it to the end ("+1 to Light Radius"), with the indicator at the bottom (`probe_hd_wheel_end.png`).
  - Legacy graphics (G): `probe_sd_top.png`, `probe_sd_scroll5.png` (window from line 5), `probe_sd_end.png`
    (clamped at the last line).
  - Graphics were set back to HD before exit.
- Both runs: no crash file, an empty `mxl2012-core.log`, and only the engine's exit-only pool asserts
  (`s_StatsPool.IsEmpty()` and its followers; docs/testing.md lists them as ignored). The slot's core DLL was restored
  (byte compare), the probe was removed, and the config folders were restored.

## Open issues

- **Classic spacing.** In legacy graphics the rows came out about 48 px apart on a 900 px screen, much more than the
  pitch of 13 suggests. A 10-row window is too tall for a band above the grid. `ClassicRowPitch` and the row count need
  tuning against the core's real legacy charm tab layout. The probe's classic background colour box did not draw
  (probe only).
- **Multi-line stats.** `TooltipOrder` reverses line by line. A stat whose text spans two lines would come out with its
  lines swapped. None of the tested stats do this.
- **Per-level stats** are summed raw and formatted once. A tooltip rounds each charm on its own, so the total can
  differ by rounding from the sum of the tooltips.
- **Context unit.** `StatListText` gets the first counting item as its context. Stats whose text depends on the item
  rather than the owner may word differently. None seen.
- **Refresh on change** was tested by calling refresh by hand. Hooking it to the charm page's item change event is the
  core's part.
- **HD band height.** In the probe's frame, the last visible row slightly overlaps the frame border. The core picks the
  band and its height.
