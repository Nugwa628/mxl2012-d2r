# Stat Book: how it works

The Stat Book turns D2R's character sheet into a book with tabs: tab 1 is D2R's own sheet, then the themed pages Offense,
Spells, Defense, Resistances, Skills & Procs and Utility, and last All Stats (every stat the character has, in groups, with
a search box). The tabs sit on top of the sheet (folder tabs, the default) or down the side of a panel beside the sheet; a
button on the book and a Controls action switch between the two. HD graphics only; legacy graphics keep D2R's own sheet.

It is one D2RLoader plugin (`statbook.dll`, plugin id `statbook`) with its own config and art. It runs on plain D2R (in an
empty mod, see the README) and inside the D2R-XL 2012 mod, which ships the same plugin with its own book and layouts.

## Data

`data/statbook_pages.tsv` (columns kind, page, text, stat, format, colour, cap, base) lists the pages, their section
headings and rows. A row names itemstatcost stats (two for a range, `name:class` for the player's class as param), a
format (`%d`, `%+d`, `%%` only, or `yesno` / `block`), a colour (w r b y p m gold blue green), an optional cap (`N` or
`N+stat<=M`: gold at or over it) and an optional base per value (`0,75` for a resistance and its maximum, shown as
"max 75%" plus the maximum resistance stat).

`tools/statbook.py` resolves the names against one game's itemstatcost (by row number, as D2R reads it) and writes the
book: rows whose stats that game lacks are left out, with their section or page when nothing is left, so one data file makes
the plain D2R book and a mod's book. The All Stats list comes from `data/advanced_stats.tsv` into the same book.

- `py -3 tools/statbook.py default` writes the plain D2R book compiled into the plugin (`src/default_book.inc`) from D2R's
  itemstatcost.txt; `check` fails when it is out of date.
- `py -3 tools/statbook.py book --isc <a mod's itemstatcost.txt> --out <mod>.mpq/data/statbook/statbook.txt` writes a mod's
  book. The plugin reads `data/statbook/statbook.txt` from the mod's data and uses the compiled-in book without it.

Row tones: zero grey, below zero red, at or over the cap gold, else the row's colour. Chance to Block is the `block`
format: the plugin asks D2R's own block rate function (the number D2R itself uses), not a sum of stats.

The book file is plain text, one record per line, fields split by tabs (`src/book_logic.h` ParseBook reads it; the format
is described at the top of `tools/statbook.py`).

## Plugin parts and settings

`statbook.toml` (D2RLoader writes the default into `d2rloader\config\` on the first start; changes apply at the next game
start, except `tabs`, which the game switches and writes back):

| Key | Default | Meaning |
|-|-|-|
| `sheet_rows` | true | the Magic / Physical Resistance rows on page 1 (needs a sheet layout with those rows: D2R-XL 2012's) |
| `advanced_stats` | true | D2R's Advanced Stats panel sorted into groups (with D2R-XL 2012's book only; plain D2R keeps D2R's panel) |
| `book` | true | the themed pages and All Stats |
| `tabs` | "top" | "top": folder tabs on the sheet; "side": the book as a panel beside the sheet, its tabs down its side |
| `pad_tabs` | "auto" | gamepad tab buttons: "auto" (LB / RB with the Controller QOL plugin, else LT / RT), "bumpers", "triggers", "off" |
| `pad_bumper_left` ... `pad_trigger_right` | 19, 20, 7, 8 | D2R's controller action ids of LB, RB, LT, RT (-1 turns one off) |
| `pad_log` | false | log every controller action the gamepad menu gets (page and id) to statbook.log |

Console (D2RLoader's console):

- `statbook`: the plugin's status, one line per part (game image, sheet rows, Advanced Stats, book, block, gamepad).
- `statbook page <n>`: page n's lines with the player's values.
- `statbook host`, `statbook tab <n>`, `statbook find <text>`: the sheet host's state, open a tab, search All Stats.
- `statbook tabs [top|side|toggle]`: switch the tabs (written back to statbook.toml).

All game addresses are of one D2R image (the one D2RLoader 1.3.1 runs, image stamp 0x6ab3782c). On another image the plugin
loads, says so in its log and status line, and hooks or calls nothing.

## Hosts

`src/book_logic.h` knows no widgets: `PageLines` fills a page into N lines (a heading, a full row, or two half rows),
`Search` picks the All Stats lines for a query with the match position for the highlight, `Tabs` holds the tab state.
A host maps those onto widgets. The folder tabs on the sheet are the first host, the side panel the second, over the same
calls and the same tab state.

### Sheet host

`src/sheet_host.cpp` binds the widget names of [statbook-layout.md](statbook-layout.md) on the HD sheet. A 50 ms UI-thread
tick does the work:

- Visibility: D2R shows every widget of the sheet when it opens, whatever its layout says. On each opening and each tab
  change the host sets every Stat Book group through D2RLoader's WidgetService (hiding a group hides its children, so leaves
  need no handle; WidgetService gives a plugin about 256 handles and the host uses about 165). D2R's own page-1 widgets are
  hidden by name on the other tabs and shown again on the Character tab.
- Open / closed: the byte of a widget's visible flag is found once by hiding two Stat Book widgets and comparing; the
  sheet's own flag then tells an opening. Nothing is shown or hidden while the sheet is closed.
- Clicks: every Stat Book button sends the same panel message (`PanelManager:OpenPanel:statbook/StatBook`); the click's
  position in the sheet's layout units picks the tab or the All Stats row. A row's arrow opens the page that has the row's
  stat.
- The Advanced Stats arrow opens All Stats when the mod's layouts are there; on plain D2R it keeps opening D2R's own panel.
- Search: the search box types through `src/shared/panel_shared.cpp`'s typing fix (D2R's text boxes do not get typed keys in
  a plugin panel otherwise); the count shows "shown/total" rows; the mouse wheel over the list scrolls it. Rows are D2R's
  own item lines for the stat or the book's own texts. The match is drawn in orange over the row's colour.
- Values are 22 pt in wide boxes; labels use D2R's reduced spacing. `tools/statbook_layout.py` checks that every label and
  value of the book fits its box with D2R's own fonts.

### Side host

With `tabs = "side"` the book is the plugin's own panel `statbook/SbSidePanel` right of the HD PC sheet, where D2R puts its
Advanced Stats panel (1342 x 1507 layout units, the sheet's height). The sheet then shows D2R's own page 1.

- Frame: D2R's Advanced Stats frame widened by whole knotwork periods, so the border runs on unbroken; the title band and
  the inner page are rebuilt as one stone picture each, with no seam. Title "Stat Book", a header row with the page title.
- Tabs down the left: Offense ... All Stats (no Character tab: the sheet is beside it). The gamepad tab buttons step round
  the side tabs.
- Pages, All Stats, the search box, the row arrows and the Advanced Stats arrow work as on the sheet.
- Its widgets are shown and hidden with D2R's own widget functions, only while it is open (the WidgetService handles are
  taken by the sheet host).
- Not on the gamepad sheet (it keeps its top tabs) and not in legacy graphics.
- At 16:9 the side panel overlaps the inventory or stash panel when both are open, as D2R's own Advanced Stats panel does.

Switching (live, with the sheet open or closed):

- The toggle on the book: a 69 x 69 icon button (tooltip "Tabs: Top / Side", D2R's gold button frame with a glyph of the
  mode a click switches to) in the top-right corner of the page. A click flips the setting and writes `tabs` back to
  statbook.toml (the rest of the file is kept).
- The Controls action "Stat Book: Top/Side Tabs" (unbound by default: bind it in Options > Controls; it is listed in the
  category "Advanced Stats").
- Console: `statbook tabs [top|side|toggle]`.
- D2R's Options menu has no plugin API, so the setting has no entry there.

### Plain D2R panel

Without a mod's Stat Book layouts there is no Stat Book widget in D2R's sheet, so the plugin registers panels of its own
from `src/statbook_plain_layout.h` (HD; legacy graphics below), which `py -3 -I tools/statbook_layout.py plain` writes from the plain book:
`statbook/SbPlainPanel` over the sheet (D2R's left panel rect) and the side panel `statbook/SbSidePanel`.

- The Stat Book's own sprites (the tabs, the row cells and heading rules, the side panel's frame and tabs, the toggle) ship
  in the mod's data (`<mod>.mpq/data/hd/global/ui/panel/statbook/`, in `data/hd/...` of this repository). For each one the
  install does not hold, the plugin swaps its widgets for one of D2R's stock sprites (the stash tab, a darkened body, the
  level-up button, a bare row), so it still works without them, just plainer. The `statbook` status line says which art is
  in use.
- The panel follows D2R's sheet: it opens with it and closes with it.
- D2R's title text ("Character") sits under the tab strip and is hidden while the panel is shown.
- Gamepad sheet: plain D2R keeps D2R's own sheet. The panel is opened only over the PC sheet.
- Legacy graphics: `src/statbook_plain_legacy.h` holds classic layouts of both panels (registered as `SbPlainPanel.json` and
  `SbSidePanel.json`, which D2R picks in legacy graphics, beside the HD `...hd.json`): the book over D2R's classic sheet
  (320 x 432) with a tab strip along its top, the pages and All Stats in D2R's classic fonts, a classic Advanced Stats
  arrow that opens All Stats, and the classic side panel. Their art is DC6 (`<mod>.mpq/data/global/ui/panel/statbook/`,
  in `data/global/...` of this repository); without all of it legacy graphics keep D2R's own sheet. The panel's head
  picture covers D2R's name and class texts, so the plugin draws the character's name and class itself; on the pages the
  panel draws its own close button (D2R's, the same message). The header and the DC6 files are made by D2R-XL 2012's
  classic sheet tools (its `tools/statbook_legacy.py plain` and `plain-art`), from D2R's classic sheet and these HD sprites.

## Gamepad

On D2R's gamepad menu (Quest Log, Character, Inventory, ...) the controller actions go to the menu, not to the page
panels. The plugin chains the menu's input handler (vtable slot 4 of D2R's UISwitcher) and takes two buttons on the
Character page only, once the sheet host is bound: LT / RT on plain D2R (LB / RB page the menu), LB / RB with the
Controller QOL plugin (which turns LT / RT into menu paging). Everything else goes on to D2R, D2RLoader and other plugins
unchanged. Controller QOL is found by its file name or its plugin id (`controller-qol-updates`), whatever the load order.

The gamepad sheet's tabs need the mod's gamepad layout (D2R-XL 2012); plain D2R keeps D2R's own gamepad sheet.

## Art and layouts

`tools/statbook_layout.py` builds the Stat Book's layouts and its art from D2R's own HD sprites (the character sheet's
stone and resistance wells, the stash tab, the Advanced Stats frame and scroll bar, the level-up button):

- `py -3 -I tools/statbook_layout.py art --data data` rebuilds the sprites a plain install ships into
  `data/hd/global/ui/panel/statbook/` (the same bytes as the ones in this repository).
- `py -3 -I tools/statbook_layout.py plain` rewrites `src/statbook_plain_layout.h`.
- `build` adds the Stat Book to a mod's own sheet layouts (it expects the D2R-XL 2012 build's sheet layouts in `--mod`).

All three read D2R's files from `D2R_DATA` (see `tools/d2r_paths.py`) and need Pillow and NumPy.
`py -3 -m unittest discover -s tools/tests` checks that the committed book, header and art are current.
