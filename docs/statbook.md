# Stat Book

The Stat Book turns D2R's character sheet into a book with folder tabs (owner decision, option C): tab 1 is D2R's own
sheet (with the Magic / Physical Resistance rows), then the themed pages Offense, Spells, Defense, Resistances,
Skills & Procs and Utility, and last All Stats (the grouped Advanced Stats list with a search box). The old Advanced Stats
arrow opens All Stats. HD graphics only for the themed pages and All Stats; legacy graphics keep page 1 without tabs.

It is one standalone D2RLoader plugin (`statbook`, its own DLL, layouts and config) that also works on plain D2R; D2R-XL 2012
ships the same plugin with Median's book (stat list, caps, page contents).

## Status

| Part | State |
|-|-|
| Page data `data/statbook_pages.tsv`, generator `tools/statbook.py` | done, tested (`tools/tests/test_statbook.py`) |
| Book file in the mod (`data/statbook/statbook.txt`, a `tools/build.py` step) | done |
| Plain D2R book compiled in (`statbook/src/default_book.inc`, `statbook.py default` / `check`) | done |
| Pure core `statbook/src/book_logic.h`: parse, row values and tones, page lines, search, tabs | done, tested (`statbook/tests`) |
| Plugin DLL `statbook/` (`build/statbook/Release/statbook.dll`, `statbook.toml`), the parts sheetres and advstats moved in from mxl2012-core | done, seen in game (check `statbook`, `advgroups`) |
| Chance to Block from D2R's GetBlockRate | done, seen in game (book 12% = GetBlockRate 12) |
| Console command `statbook` / `statbook page <n>` (status, page lines with the player's values) | done, seen in game |
| Gamepad tab hook (the gamepad menu's input slot) | done, seen in game: LT / RT step the book's tab on plain D2R-XL 2012, LB / RB with Controller QOL, D2R's own paging intact (see Gamepad); the buttons are taken only while the sheet host is bound, and step the host's tab (check `statbook_host_pad`) |
| Plain D2R: the plugin loads in an empty mod, uses its built-in book, leaves D2R's Advanced Stats panel alone | seen in game (slot 1, `mods\statbook-plain`, test DLL: an Amazon made, 6 pages, Chance to Block 75% with the starting buckler, shot `statbook_plain_sheet`) |
| Test DLL `build/statbook-test` (`-DSTATBOOK_TEST_HARNESS=ON`): D2R-Legacy169's cut-down harness, switch file `statbook-testharness.txt`; never packaged, the player DLL is checked not to carry it | done |
| Layouts registered under the plugin's own folder (`data/global/ui/layouts/<plugin id>/`, `panel_shared.cpp` RegisterLayout) | done |
| Packaging: `install_mod.py`, `package_release.py`, `verify_package.py` (DLL, config, the book file in the data) | done, tested |
| Sheet host `statbook/src/sheet_host.cpp` (tabs, pages, All Stats with search and row arrows, the Advanced Stats arrow, visibility on every opening), pure part `sheet_host_logic.h` | done, tested (`statbook_sheethost_tests`, `tools/tests/test_statbook_checks.py`), seen in game on the HD PC sheet at 900p / 1080p / 1440p (check `statbook_host`, also with mxl2012-core's developer menu opened first) and on the gamepad sheet with both pad setups (check `statbook_host_pad`) |
| Plain D2R panel over the sheet (`statbook/SbPlainPanel`, `statbook/src/statbook_plain_layout.h`, `statbook_layout.py plain`) | done, seen in game on the HD PC sheet (slot 1, `mods\statbook-plain`): opens and closes with the sheet, all 8 tabs, All Stats search, the Stat Book's own tab strip (D2R's stash tab when its art is not installed), D2R's title hidden; shots `statbook_plain_*`. The side panel and its toggle too (`statbook/SbSidePanel`, own side art and HD toggle). The gamepad sheet and legacy graphics keep D2R's own sheet (see Plain D2R panel) |
| Layouts and art (tab strip, page stone, cells, All Stats, gamepad), `tools/statbook_layout.py` (a `tools/build.py` step), widget names in [statbook-layout.md](statbook-layout.md) | done, tested (`tools/tests/test_statbook_layout.py`); looked at in game with static previews (slot 4, 2026-11-15) |

## Data

`data/statbook_pages.tsv` (columns kind, page, text, stat, format, colour, cap, base) lists the pages, their section
headings and rows. A row names itemstatcost stats (two for a range, `name:class` for the player's class as param), a
format (`%d`, `%+d`, `%%` only, or `yesno` / `block`), a colour (w r b y p m gold blue green), an optional cap (`N` or
`N+stat<=M`: gold at or over it) and an optional base per value (`0,75` for a resistance and its maximum, shown as
"max 75%" plus the maximum resistance stat).

`tools/statbook.py book` resolves the names against one game's itemstatcost (by row number, as D2R reads it) and writes
the book file; rows whose stats that game lacks are left out, with their section or page when nothing is left, so one
data file makes the D2R-XL 2012 book and the plain D2R book. The All Stats list comes from `data/advanced_stats.tsv` (the
advstats groups) into the same file. Page contents change without code: edit the TSV and rebuild the mod.

Row tones: zero grey, below zero red, at or over the cap gold, else the row's colour. Chance to Block is the `block`
format: `FillRow` asks the host for the pseudo stat `BlockRateStat`, and the plugin answers with D2R's own GetBlockRate (RVA 0x347da0, `int32(Unit*, int32 expansion)`, see
`mxl2012-runs/sbresearch/findings.md`, `plugin/src/block_rate_logic.h` on lane/sbresearch).

## Plugin

`statbook.dll` loads per mod (D2R-XL 2012 ships it next to mxl2012-core) or in any other mod folder. It reads the book from
the mod's `data/statbook/statbook.txt` (the mod's MPQ folder); without it, the plain D2R book compiled in. The grouped
Advanced Stats list (part advstats) holds D2R-XL 2012's stat ids, so it only runs with the mod's book; plain D2R keeps its
own panel. The parts have their switches in `statbook.toml`:

| Key | Default | Meaning |
|-|-|-|
| `sheet_rows` | true | the Magic / Physical Resistance rows on page 1 (part sheetres; needs the mod's sheet layout) |
| `advanced_stats` | true | the Advanced Stats panel in groups (part advstats; with the mod's book only) |
| `book` | true | the themed pages and All Stats |
| `pad_tabs` | "auto" | the tab buttons: "auto" (bumpers with Controller QOL, else triggers), "bumpers", "triggers", "off" |
| `pad_bumper_left` ... `pad_trigger_right` | 19, 20, 7, 8 | D2R's controller action ids of LB, RB, LT, RT (-1 turns one off) |
| `pad_log` | false | log every controller action the gamepad menu gets (page and id) to statbook.log |
| `tabs` | "top" | "top": folder tabs on the sheet (option C); "side": the book as a panel beside the sheet, its tabs down its side (option B, "Side host"). Switched in game and written back here |

Console: `statbook` prints one line per part (image, sheetres, advstats, book, block, pad) in the old `mxl2012` line form,
so `tools/game_checks.py statbook_text()` reads them; `statbook page <n>` prints a page's lines with the client player's
values (`sbline <i> heading | ...` or `sbline <i> full|pair | label = value (tone)`). With the mod's test harness on
(`mxl2012-testharness.txt` beside the DLL) the lines also go to `mxl2012-testharness-console.txt`.

Two DLLs compile `plugin/src/panel_shared.cpp`: each has its own copy of its state (typing client, taken key). Only
mxl2012-core's devmenu and wiki call `HookGameWindow`; statbook uses `NativePanel` / `SetLine` / `ReadModFile` only and
subclasses nothing. When the search box arrives it will chain a second window proc: each proc swaps typed keys for F24 only
for its own focused box and passes everything else on, so the two do not take each other's keys (to be seen in game then).
`RegisterLayout` in panel_shared still writes under `layouts/mxl2012-core/`: statbook needs its own folder before it uses it.

## Hosts

`book_logic.h` knows no widgets: `PageLines` fills a page into N `Line`s (a heading, a full row, or two half rows),
`Search` picks the All Stats lines for a query with the match position for the highlight, `Tabs` holds the tab state.
A host maps those onto its widgets. The sheet's folder tabs (option C, the default) are the first host. The side panel
with its tabs down its side (option B, `tabs = "side"`) is the second, over the same calls and the same tab state: nothing
of the page content, filling or search differs.

### Sheet host

`statbook/src/sheet_host.cpp` binds the contract of [statbook-layout.md](statbook-layout.md) on the HD sheet
(`CharacterStatsPanel` with `StatBookMarker`; legacy and D2R's own layout have no marker and are left alone). A 50 ms
UI-thread tick does all the work:

- Visibility: D2R shows every widget of the sheet when it opens. On each opening and each tab change the host sets every Stat
  Book group (tabs' selected marks, `SbPageBody`, `StatBookPage`, `StatBookAll`, the line groups `SbLine<ii>Heading/Full/Left/Right`,
  the All Stats `SbAll<jj>Heading/Row`, `SbPreviewQuery`, the gamepad glyphs) through WidgetService. Hiding a group hides its
  children (seen in game, shot `statbook_vis_group_hidden`), so leaves get no handle (WidgetService gives a plugin about 256;
  the host uses ~165). A value box of another tone holds "". D2R's own page-1 widgets are hidden by name on the other tabs and
  shown again (as they were) on the Character tab.
- Open / closed: the byte of a widget's visible flag is found by hiding `SbPageBody` and `StatBookAll` once and comparing
  their bytes (in game: +0x51 bit 0x01); the sheet's own flag then tells an opening. Nothing is shown while the sheet is closed:
  a first version that showed and hid widgets of the closed sheet with their vfuncs kept the sheet from opening at all.
- Clicks: every Stat Book button sends `PanelManager:OpenPanel:statbook/StatBook` (one registered name); the last click's
  position in the sheet's layout units (16:9: panel at 236, 208.4 of a 2160-unit-high screen) picks the tab or the All
  Stats row in `statbook-layout.json`. A row's arrow opens the page that has the row's stat.
- The Advanced Stats arrow (`CharacterStatsPanelMessage:ToggleAdvancedStats`) is taken on the HD PC sheet and opens All
  Stats; D2R's own Advanced Stats panel does not open there any more (legacy keeps it).
- Search: `SbSearchInput` types through panel_shared's typing fix (as the developer menu's box); the host reads the text with
  WidgetService `getInputText` while the box is clicked. The count shows "shown/total" rows. The mouse wheel over the list
  scrolls it. Rows are D2R's own item lines (0x14eb250 with a stand-in panel) or the book's own patterns, colour codes removed.
- Two copies of panel_shared (mxl2012-core's and statbook's) each subclass the game window once. They chain: the outer one
  turns a key typed into its focused box into F24 and the inner one passes F24 on, and each copy only acts for its own
  clients' boxes (from reading the code). Seen in game: typing in the Stat Book's box with mxl2012-core loaded (check
  `statbook_host`), also after mxl2012-core's developer menu has been opened and closed (both subclasses at once): the query
  typed came through once per key.
- Values are 22 pt (PC) / 26 pt (gamepad) in wider boxes; labels use D2R's
  `$ReducedSpacing` (kerning 0.94) and sit centred on the value's line. `statbook_layout.py` checks every label and value of
  the book fits its real box width (`fit_problems`).
- The search match is drawn in `$FontColorOrange` (255, 168, 0) over the row's own colour: gold, white and the blue magic
  colour of the rows all differ from it clearly (the earlier gold-yellow match was hard to see on gold rows).
- Console: `statbook host` (status), `statbook tab <n>`, `statbook find <text>`, `statbook vis <widget> 0|1|-1` (hold one
  widget's visibility; -1 lets it go). `SheetHostBound()` / `SheetHostStep()` are for the gamepad tab buttons.

### Side host

With `tabs = "side"` the book is the plugin's own panel `statbook/SbSidePanel` right of the HD PC sheet, where D2R puts its
Advanced Stats panel (x 1398 of the left panel anchor, 1342 x 1507, the sheet's height). Its layout is the mod's
`hd/global/ui/panel/statbook/sidepanelhd.json` (built by `statbook_layout.py`), registered at load as the panel's layout;
its click rectangles are `side` in `statbook-layout.json`. The sheet then shows D2R's own page 1 under its own title ("Character",
D2R's string), with the top tabs, pages and toggle hidden.

- Frame: D2R's Advanced Stats frame widened by whole knotwork periods (233 px, two motifs), so the border runs on unbroken;
  the title band, the band under it and the inner page are rebuilt as one stone picture each (patches, no strip, no
  period): no vertical seam anywhere. Title "Stat Book"; a header row with the page's title.
- Tabs down the left: Offense ... All Stats (no Character tab: the sheet is beside it), labels in D2R's grey-gold
  (`$FontColorDarkGrayGold`) at up to 18 points. The art is the stash tab fitted
  upright like the top tabs, its stone rebuilt, then turned so its gem points at the page. The tab is never 0 in side mode
  (`SideTab`); the pad tab buttons step round tabs 1 to 7 (`SideStep`).
- Pages, All Stats, the search box and its highlight, the row arrows and the Advanced Stats arrow (opens All Stats) work as
  on the sheet, with the side panel's rectangles and origin (1398, 208.4).
- Opening: once per sheet opening (as the plain panel), closed with the sheet; reopening keeps the tab.
- Widgets: WidgetService gives a plugin about 256 handles and the sheet's book uses ~165, so the side panel's widgets are
  shown and hidden with D2R's own vfuncs (+0x50, +0x48), only while it is open (it is filled only then); only its search box
  has a handle (the typed text). The fill code is the sheet's, run over the side panel's caches (`SideView`).
- Not on the gamepad sheet (it keeps its top tabs and pad host whatever the setting) and not in legacy graphics.
- Plain D2R has it too: the plugin registers the same side panel from `statbook_plain_layout.h` (`SideLayoutHd`, written by
  `statbook_layout.py plain` from the mod's side layout with its art, see "Plain D2R panel"); the toggle, the
  Controls action, `statbook tabs` and the write-back to statbook.toml work the same. On plain D2R the Advanced Stats arrow
  opens D2R's own panel with top tabs and All Stats in side mode (D2R's panel would sit under the side panel), and D2R's
  "Character" title, hidden under the top tab strip, shows in side mode.
- At 16:9 the side panel (to x 2740) overlaps the inventory or stash panel (from x 2446) by about 294 units when both are
  open; D2R's own Advanced Stats panel sits in the same place.

Switching (live, with the sheet open or closed; the next tick hides one host's widgets and shows the other's):

- The toggle on the book: `SbTabsToggle`, an icon-only button (69 x 69, tooltip "Tabs: Top / Side"; D2R's gold button frame with a glyph of the mode a click
  switches to: tabs down the side on the sheet, tabs on top on the side panel) in the top-right
  corner of the page on both hosts. On the sheet it is at the frame's inner bevel, right of the All Stats count (the count and the
  search row end left of it), over the faded right end of line 0 and above line 1 (line 0 a heading on every page; `test_toggle_clear_of_everything` checks it touches no tab, search box or row), shown on the
  pages and All Stats. On the side panel it is at the right of the header row, between the title and the search row. A click flips the setting and writes
  `tabs` back to statbook.toml (`WithTabs` keeps the rest of the file).
- The Controls action "Stat Book: Top/Side Tabs" (`mxl_statbook_tabs`, category Advanced Stats, unbound by default:
  rebind it in Options > Controls). Registered only when the side panel is (the mod's, or plain D2R's compiled-in one).
- Console: `statbook tabs [top|side|toggle]`.
- D2R's own Options menu has no plugin API (docs/legacy-hd-text-research.md section 3), so the setting has no entry
  there; the gameplay options layout is not patched for it.

### Plain D2R panel

Without the mod there is no `statbook-layout.json` and no Stat Book widget in D2R's sheet, so the host registers panels of
its own from `statbook_plain_layout.h` (HD layouts only; MSVC's string limit splits them into pieces joined at load), which
`statbook_layout.py plain` writes from the plain book and the mod's own layouts, so they cannot drift from them
(`test_same_as_the_mods_layouts`: every widget of the mod's PC and side layouts is in the plain ones, the same but its art;
`test_header_is_current`): `statbook/SbPlainPanel` with the same widget names at the sheet's rect (`$LeftPanelRect`, anchor
0 / 0.397, priority 5), and the side panel `statbook/SbSidePanel` (`SideLayoutHd`, the side host). The Stat Book's own
sprites (`PLAIN_OWN_ART`: `tab`, `tabselected`, the row cells and heading rules `halfcell`, `fullcell`, `allcell`, `rule`,
`allrule` and their `side*` ones, `sidebody`, `sidetab`, `sidetabselected`, `tabstoggleside`, `tabstoggletop`, each `.sprite`
and `.lowend.sprite`) ship with the plugin in the install's data
(`<mod>.mpq/data/hd/global/ui/panel/statbook/`, as the mod's art). For each one the install does not hold, the host swaps its
widgets for D2R's stock sprite (`Fallback` rows in the header: the stash tab `MKB_Tabs_195_TGA` scaled to the tab, a
darkened body for the side frame, the level-up button for the toggle, a bare widget for a cell or rule: the row is then text on the dark body;
`test_every_image_shipped_or_stock` checks every image the plain layouts use is an own sprite with its Fallback rows or
D2R's own); the status line says `tab art own` or `tab art D2R's stash tab`, `cell art own` or `none`, `side art own` or `D2R's stock`, `toggle art own` or `D2R's level-up button`. The rest is D2R's own sprites: a
body darkened with the Advanced Stats cell's translucent centre, the Advanced Stats scroll bar, the modal input slot and the
stash arrow.

- The panel follows D2R's sheet: the sheet's visible flag (+0x51 bit 0x01, as calibrated on the mod's sheet) opens it, and it
  closes with the sheet. One open per sheet opening: a refused open waits for the next opening.
- The Stat Book widgets are the panel's; D2R's widgets hidden on the other tabs are the sheet's, by name.
- The panel's name must not start with the click panel's (`statbook/StatBook`): as `statbook/StatBookPlain` D2RLoader
  never opened it ("Plugin panel open failed ... fallback-resource=found"); the same layout under another name opened.
- D2R's title text (`StatsPanelTitle`, "Character") sits under the tab strip: the host hides it while the panel is bound
  (D2R shows it again on each opening; the mod's layout empties it instead).
- The Advanced Stats arrow keeps opening D2R's own panel there.
- Gamepad sheet and legacy graphics: plain D2R keeps D2R's own sheet. A gamepad variant would need a second panel at the
  gamepad menu's rect, the pad geometry and its own art, registered and focused inside D2R's gamepad menu: not cheap, left
  out. The host opens its panel only over a sheet with a `CloseButton` (D2R's PC sheet has one, the gamepad sheet none,
  `test_close_button_tells_the_pc_sheet`) and only in HD; on the gamepad sheet it stays unbound, so LT / RT / LB / RB stay
  D2R's there. Not run in game: plain D2R with the gamepad UI (the scripted pad needs mxl2012-core's harness, which the
  plain test mod does not hold) and legacy on slot 1 (G would change the owner's graphics setting).
- Run `work/plain_panel.py` (lane scratch, slot 1, 2026-11-15): sheet open binds, each tab click selects its tab, a typed
  All Stats search, closed with the sheet and opened again, no failed open in the loader log; with the tab art installed
  (shots `statbook_plain_*`, `statbook_plain_tabs_vs_mod`: the mod's strip above, the plain one below) and without it
  (`SB_TABART=0`, shots `statbook_stocktabs_plain_*`).

## Gamepad

On D2R's gamepad menu (the UISwitcher of `layouts/controller/uiswitcherhd.json`: Quest Log, Character, Inventory, ...) the
controller actions go to the menu, not to the page panels: CharacterStatsPanel's own handler (slot 4, 0x14eed10) gets none
of them. The plugin chains the menu's input slot (lane sbresearch, `mxl2012-runs/sbresearch/findings.md` "Gamepad routing"):

| What | Value |
|-|-|
| slot | UISwitcher vtable slot 4, RVA 0x1cef450; D2R's handler 0x27e620 (entry `4C 8B DC 55 56 41 56 49 8D 6B A1 48 81 EC E0 00 00 00`, checked), which calls 0x27df80 |
| call | `void(UISwitcher* rcx, InputMessage* rdx)`, Microsoft x64; returning without calling on takes the button |
| message | `[msg]` InputMessage type, `[msg+0x88]` ControllerActionBegin type (D2R's TypeId), `[msg+0x110]` payload: action id +0x10, repeat byte +0x18 |
| current page | `[menu+0x1b8]` index, `[menu+0x188]` count, `[menu+0x168+i*4]` panel id, `0x846190(id)` the panel, its name (`const char*` at +8) `CharacterStatsPanel` on the Character page |
| action ids | LB 19, RB 20, LT 7, RT 8, X 1, Y 2, B 23, D-pad up 12 + 15, down 13 + 16 |

D2R's 0x27df80 pages the menu on 19 / 20 and closes it on 9 / 23. D2RLoader routes the slot through D2RCore (plugin
controller routes) and Controller QOL Updates wraps it (LT / RT become 19 / 20, LB / RB dropped); the plugin keeps whatever
the slot holds and calls it for everything it does not take, so it sees the raw buttons first. Free on the Character page:
LT / RT on plain D2R (LB / RB page the menu), LB / RB with Controller QOL (LT / RT page it). Only those two buttons, only on
the Character page, and only once the sheet host exists (test installs with the harness switch: always) are taken; a held
button's repeats are taken without a further step.

Run `checks-20261115-014623-s3` (plain) and `checks-20261115-014858-s3` (Controller QOL), probe
`mxl2012-runs/sbresearch/padprobe.py`: RT, RT, LT (QOL: RB, RB, LB) stepped the tab 0, 1, 2, 1 with the menu staying on
Character; then LB (QOL: LT) paged to Quest Log and RB (QOL: RT) back. The status line counts `menu messages`, `actions`,
`tab buttons` and `tab steps`. With the sheet host bound (check `statbook_host_pad`, runs `checks-20261115-042217-s3` plain and
`checks-20261115-042449-s3` with Controller QOL) the same buttons step the host's own tab (0, 1, 2, 1, the page shown
follows) and the paging buttons still page the menu.

Load order: D2RLoader loads a mod's plugins in file-name order, so `Controller QOL Updates.dll` loads before `statbook.dll`.
With QOL loaded after the Stat Book (`zz Controller QOL Updates.dll`, `SB_PAD_SETUP=cqol-after`) the first run failed: the
pad choice looked for QOL by its file name only, so the tabs stayed on LT / RT, which QOL turns into menu paging. The choice
now also finds QOL by its plugin id (`controller-qol-updates`, through the loaded modules' `D2RLoaderGetPluginInfo`, at most
every 2 s until seen). Runs `checks-20261115-055601-s3` (QOL after) and `checks-20261115-055831-s3` (QOL before): LB / RB
step the tabs 0, 1, 2, 1, LT / RT page the menu away and back, LB / RB glyphs; `checks-20261115-060024-s3` (no QOL): LT / RT.

## Proven in game

| What | Where | Run, shots |
|-|-|-|
| Book data, values (Chance to Block = GetBlockRate), `statbook` console, sheetres / advstats | slot 3, D2R-XL 2012 | `checks-20261115-002522-s3` (checks `statbook`, `advgroups`) |
| Sheet host, HD PC sheet: tabs, pages, All Stats search with orange match, row arrows, Advanced Stats arrow, reopen, 900p / 1080p / 1440p, legacy unbound | slot 3, D2R-XL 2012 | `checks-20261115-041533-s3`, cp5 `statbook_*` |
| Typing with mxl2012-core's developer menu opened first (both window subclasses) | slot 3 | `checks-20261115-041533-s3`, `statbook_devmenu_open` |
| Pad tabs on the gamepad sheet, D2R's paging intact: no QOL (LT / RT), QOL before and after the Stat Book (LB / RB) | slot 3, D2R-XL 2012 | `checks-20261115-060024-s3`, `-055831-s3`, `-055601-s3`, cp6 `statbook_pad_*` |
| Plain D2R: built-in book, own panel over the HD PC sheet, tabs, search, reopen, own tab art and the stash-tab fallback, title hidden | slot 1, `mods\statbook-plain` | `work/plain_panel.py`, cp6 `statbook_plain_*`, `statbook_stocktabs_plain_*` |
| Plain D2R side host (`statbook/SbSidePanel`): the book toggle both ways with its tooltip, live and with the sheet closed, statbook.toml written back, every side page, the Advanced Stats arrow to All Stats, search and a row arrow, reopen keeps the tab, top tabs right after switching back, own tab, cell, side and toggle art (0 stock swaps; rows in their boxes as on the mod), Controls action registered | slot 1, `mods\statbook-plain` | `work/plain_side.py` (19 rows), `statbook_plain_*` in `shots/plain`, `shots/plain2` (69 px toggle, row cells) |
| Side host (`tabs = "side"`), HD PC sheet at 900p: the book toggle both ways with its tooltip, live with the sheet open, statbook.toml written back, every side page, the Advanced Stats arrow, All Stats search and a row arrow, reopen keeps the tab, `statbook tabs` with the sheet closed, top tabs right after switching back, Controls action registered | slot 1, D2R-XL 2012 | `checks-20261115-100552-s1`, `-114857-s1` (check `statbook_side`; v2: grey-gold side labels, HD toggle), `-134014-s1` and `-134905-s1` (`statbook_side`, `statbook_host`: the 69 px toggle), `statbook_side_*` |
| Not run in game | | the Controls action pressed on a key (registered only, unbound by default), the side host at other resolutions, plain D2R with the gamepad UI or in legacy (D2R's own sheet by design), a real controller (only the scripted pad), Controller QOL on plain D2R |

Shots: `mxl2012-runs/statbook/shots/cp5/` and `cp6/`; side host `mxl2012-runs/sbside/shots/`.

## Notes

- `data/statbook_pages.tsv`: the skill speed rows (attackrate, velocitypercent) have base -100 (D2R stores 100 + bonus).
- The resistance page shows the stats as items and skills give them, before the difficulty penalty (its heading says so).
- `tools/advanced_stats.py` now maps Median's stat ids through `tools/idmap.py`: the table had Median's 1.13c row numbers
  for its own stats (e.g. game_craftpoints 183), the built mod has them after D2R's rows (368).
