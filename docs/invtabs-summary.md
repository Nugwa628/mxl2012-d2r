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
