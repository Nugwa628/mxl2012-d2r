# Stat Book layouts: the widget-name contract

The HD layouts and art of the Stat Book (docs/statbook.md, option C: folder tabs on D2R's character sheet) are built by
`tools/statbook_layout.py` in the D2R-XL 2012 build, after `sheet_resists.py` and `statbook.py book`. This page lists every
widget name the statbook plugin fills, shows or hides. The names are stable: renaming one breaks the plugin.
`tools/tests/test_statbook_layout.py` checks that this page, `contract_names()` in the tool and both built layouts agree.

Layouts that get the widgets:

- `global/ui/layouts/characterstatspanelhd.json` (PC, HD graphics), inserted before D2R's `CloseButton`.
- `global/ui/layouts/controller/characterstatspanelhd.json` (gamepad UI), appended at the end. This file is `basedOn` the
  PC file, so every name is repeated with gamepad rects.
- `global/ui/layouts/characterstatspanel.json` (legacy graphics), built by `tools/statbook_legacy.py` after this tool:
  the same names in the same groups (WidgetService handles are paths, so the plugin keeps them across a G switch), classic
  rects, classic fonts (6pt labels, 8pt values and headings) and explicit RGB colours. It keeps D2R's 320 x 432 rect: D2R
  draws a classic left panel only inside the classic panel area, whatever the layout's rect says (a sheet widened by 80 x 24
  was cut there in game, 2026-11-15). The tab strip (18 high) lies over the sheet's frame top; D2R's name and class texts
  move to the row below it, on the SbHead picture. Extra names: SbLegacyMarker (the plugin binds the legacy sheet only when
  it is there), SbAdvanced (a classic Advanced Stats arrow: All Stats; a Stat Book click found by its rect) and SbHead. 21 All Stats
  rows. A half row's label too long for its cell is drawn in a clean short form by the plugin (sheet_host_logic.h ShortLabels,
  whole labels: Minion Resistances to Minion Res. and the like). Values: classic 6pt, right-aligned inside their bars, bright
  tones (HD's grey for a zero value is near white).
- `hd/global/ui/panel/statbook/sidepanel.json`: the classic side panel, registered beside the HD one on the same panel, at
  D2R's right panel anchor (the classic right panel area), its tabs along its top. Its stone is part of SbSideBody (group
  SbSideStone); its SbPageBody is bare, as in HD (the side host hides it).
- `statbook-layout.json` keys `legacy` and `legacyside`: the click rects in classic pixels and `origin`, the panel's corner
  from D2R's classic left panel corner (80, 60 of 800 x 600); the plugin maps a click with D2R's classic screen size.
- `hd/global/ui/panel/statbook/sidepanelhd.json`: the side panel (tabs = "side", docs/statbook.md "Side host"), the plugin's
  own panel `statbook/SbSidePanel` (rect x 1398, y -651, 1342 x 1507 at D2R's left panel anchor: right of the sheet, where
  D2R puts its Advanced Stats panel). The plugin registers it as its layout. It has the same names as the PC sheet
  (contract below) except the Character tab (no tab 0: the sheet is beside it), with the tabs down its left side, plus three
  of its own: SbSideBody (the frame), SbSideTitle ("Stat Book" in the title band) and SbSideHeading (the page title row, filled
  with the tab's title). Its widgets are shown and hidden with D2R's own vfuncs (only while it is open), not WidgetService.

Placeholders: `<i>` is the tab index (0 = Character, then the book's pages in order, last = All Stats; 8 tabs with the
D2R-XL 2012 book). `<ii>` is the line slot, two digits, `00`-`21` (22 slots; the longest page, offense, has 21 lines).
`<jj>` is the All Stats row, two digits, `00`-`21` on PC and `00`-`19` on the gamepad (two columns of 10).
`<Tone>` is one of the tones below.

## Showing and hiding

In game the layout's `"visible": false` does not hold on this panel (slot 4, 2026-11-15, without the statbook plugin): every
Stat Book widget was drawn when the sheet opened, the hidden All Stats page over the sheet, groups and leaves alike. D2R's own
`CombinedPointsInfo` also showed with `visible: false`. So:

- The plugin sets the visibility of every Stat Book widget each time the sheet opens (and keeps it while open), not only the
  ones that change. Without the plugin the Character tab is covered by the All Stats page.
- Whether `setWidgetVisible` on a group hides its children is not known yet. To be safe, "show a group" in the tables below
  means: set the group and every leaf under it; "hide" the same. A leaf is drawn only when its groups and the leaf itself are
  shown (for example `SbLine<ii>RightValue<Tone>` needs `StatBookPage`, `SbLine<ii>Right` and the row's tone).
- The layouts still write `visible` on every widget, each leaf's flag combined with its groups': it states the start state
  (Character tab) and tests read it.

## Top level

| Name | Kind | Plugin use |
|-|-|-|
| `StatBookMarker` | Widget | Present means the layouts are the Stat Book's (the plugin's check before binding). |
| `StatBookTabs` | Widget | The tab strip group. Always visible. |
| `SbPageBody` | ImageWidget | The seamless stone page body. Show on the themed pages and All Stats, hide on Character. Gamepad: unused (always hidden; D2R's own gamepad stone is plain). |
| `StatBookPage` | Widget | The themed page's line slots. Show on a themed page only. |
| `StatBookAll` | Widget | The All Stats page. Show on All Stats only. |
| `SbTabsToggle` | ButtonWidget | PC only: the top / side tabs toggle, icon only (tooltip "Tabs: Top / Side"), in the page's top-right corner. On the sheet: shown on the themed pages and All Stats (right of the All Stats count, over the faded right end of line 0, which is a heading on every page). On the side panel: always shown, at the right of its header row. |

## Tabs (inside `StatBookTabs`)

| Name | Kind | Plugin use |
|-|-|-|
| `SbTab<i>` | ButtonWidget | The tab, with its short label as text and the page's full title as tooltip. Always visible. |
| `SbTab<i>Selected` | ImageWidget | The selected-tab overlay (gem). Show only on the current tab. |
| `SbTab<i>SelectedLabel` | TextBoxWidget | The label in the selected colour. Show only on the current tab. |

Gamepad only:

| Name | Kind | Plugin use |
|-|-|-|
| `SbPadPrevLB` | ImageWidget | The LB glyph left of the strip. Shown by default. |
| `SbPadNextRB` | ImageWidget | The RB glyph right of the strip. Shown by default. |
| `SbPadPrevLT` | ImageWidget | The LT glyph. Hidden by default. Show it (and hide the LB glyph) when the page keys are LT / RT. |
| `SbPadNextRT` | ImageWidget | The RT glyph. Hidden by default. Show it with `SbPadPrevLT`. |
| `SbPadAllHint` | Widget | The "All Stats" hint with the View button glyph at the bottom right. Show on the themed pages and All Stats. |
| `SbPadAllHintGlyph` | ImageWidget | The glyph inside the hint. |
| `SbPadAllHintText` | TextBoxWidget | The hint's text. |

LB / RB is the default because Controller QOL in D2R-XL 2012 releases frees them on the sheet. On plain D2R the plugin swaps
to LT / RT (docs/statbook.md "Gamepad").

## Themed page lines (inside `StatBookPage`)

Each line slot holds one line of book_logic.h PageLines: a heading, a full row, or a pair of half rows. Show the group of the
line's kind and hide the other three; hide all four on unused slots.

| Name | Kind | Plugin use |
|-|-|-|
| `SbLine<ii>Heading` | Widget | A section heading line. |
| `SbLine<ii>HeadingText` | TextBoxWidget | The heading text (gold). |
| `SbLine<ii>HeadingRule` | ImageWidget | The gold rule behind the text. Static. |
| `SbLine<ii>Full` | Widget | A full-width row (label box 600, value box 435 on PC). |
| `SbLine<ii>Left` | Widget | The left half row (label 380, value 132 on PC). |
| `SbLine<ii>Right` | Widget | The right half row. Hide it when the pair has no second row. |
| `SbLine<ii>FullCell`, `SbLine<ii>LeftCell`, `SbLine<ii>RightCell` | ImageWidget | The cell art. Static. |
| `SbLine<ii>FullLabel`, `SbLine<ii>LeftLabel`, `SbLine<ii>RightLabel` | TextBoxWidget | The row's label. |
| `SbLine<ii>FullValue<Tone>`, `SbLine<ii>LeftValue<Tone>`, `SbLine<ii>RightValue<Tone>` | TextBoxWidget | The value. One box per tone, already in its colour: fill the box of the row's tone and empty the other nine. |

Tones, in book_logic.h order, with their font colours:

| Tone | Colour |
|-|-|
| White | `$FontColorWhite` |
| Grey | `$FontColorGray` |
| Red | `$FontColorRed` |
| Blue | `$FontColorBlue` |
| Yellow | `$FontColorYellow` |
| Purple | RGB 60, 220, 60 |
| Magic | `$FontColorOrange` |
| Gold | `$FontColorGoldYellow` |
| ItemBlue | `$FontColorBlue` |
| Green | `$FontColorGreen` |

The colours are `TONES` in `tools/statbook_layout.py`. The plugin only picks the box by tone name.

## All Stats (inside `StatBookAll`)

| Name | Kind | Plugin use |
|-|-|-|
| `SbSearchLabel` | TextBoxWidget | The "Search" label. Static. |
| `SbSearchSlot` | ImageWidget | The text box frame (the developer menu's `PANEL\Modals\InputSlot` pattern). Static. |
| `SbSearchInput` | InputTextBoxWidget | The search text (max 32 characters). The plugin reads it each frame. |
| `SbSearchCount` | TextBoxWidget | "shown/total" rows, for example `12/124`. |
| `SbAll<jj>Heading` | Widget | A list row that is a group heading. |
| `SbAll<jj>HeadingText` | TextBoxWidget | The group heading text (gold). |
| `SbAll<jj>HeadingRule` | ImageWidget | The rule behind it. Static. |
| `SbAll<jj>Row` | Widget | A list row that is a stat line. Show it or `SbAll<jj>Heading` (or neither past the end of the list). |
| `SbAll<jj>Cell` | ImageWidget | The row's cell art. Static. |
| `SbAll<jj>Text` | TextBoxWidget | The whole line, white. |
| `SbAll<jj>Hit` | TextBoxWidget | Highlight layer 2: the line up to the end of the match, orange (`$FontColorOrange`). Empty without a match. |
| `SbAll<jj>Pre` | TextBoxWidget | Highlight layer 3: the line before the match, white. Empty without a match or when the match starts the line. |
| `SbAll<jj>Go` | ButtonWidget | The arrow that opens the row's page. |

PC only:

| Name | Kind | Plugin use |
|-|-|-|
| `SbAllScrollTrack` | ImageWidget | The scroll track. Static. |
| `SbAllScrollThumb` | ImageWidget | The thumb. The plugin moves it with the scroll position. |

The highlight needs no text measuring. The three left-aligned boxes sit at the same place and draw in order: the whole line
in white, then the line up to the match's end in orange over it, then the line before the match in white over that. What shows
is before (white), match (orange), after (white). Orange (255, 168, 0), not D2R's gold: the gold (199, 179, 119) in the Formal
font was hard to tell from white in game (checkpoint 4 shot `statbook_allstats_search`).

The PC list scrolls with the mouse wheel over the list rect. The gamepad list fills column 1 (`SbAll00`-`SbAll09`), then
column 2 (`SbAll10`-`SbAll19`).

A normal build also has the preview-only query box (SbPreviewQuery, always hidden). The plugin does not use it.

## D2R's widgets the plugin hides on the themed pages and All Stats

Everything at the top level of the sheet except `Background`, `ClickCatcher` / `click_catcher`, `LeftHinge`,
`StatsPanelTitle`, `CharacterName`, `FullClassInfo`, `XpProgress`, `CombinedXP`, `CloseButton`, `LevelUpInfo`,
`CombinedPointsInfo` and the Stat Book's own widgets (`hidden_on_pages()` in the tool). That covers the attributes, damage
and rating, defense, stamina, life, mana, the six resistance rows (including sheetres' `Mxl*`), `AdvancedStats`, and on the
gamepad the row backgrounds and dividers. Show them again on the Character tab. `LeftSkillStats` and `RightSkillStats` are
groups: hide their leaves too.

The stat points line (`CombinedPointsInfo`, `LevelUpInfo`) stays on every page. D2R's code shows it every frame, so a layout's
`visible: false` does not hold (seen in game), and the remaining points are useful on every page anyway.

The PC layout has three top-level widgets named `separator` (between the current and maximum stamina, life and mana). A
lookup by name finds only one, so the plugin walks the top-level children and hides by name, every match.

D2R's title text (`StatsPanelTitle`) is emptied in the PC layout; the tab strip is the title.

## Clicks and the mouse wheel

Every button (`SbTab<i>`, `SbAll<jj>Go`, `SbTabsToggle`) sends the same message, `PanelManager:OpenPanel:statbook/StatBook`. The plugin
picks the tab or row from the cursor position. The rects, in the panel units of each layout, are written next to the art:
`hd/global/ui/panel/statbook/statbook-layout.json`.

| Key | Contents |
|-|-|
| `pc`, `pad`, `side` | One object per layout (`side`: the side panel, in its own panel units). |
| `tabs` | `[x, y, w, h]` of each tab (`side`: tab 0 is `[0, 0, 0, 0]`, never hit). |
| `toggle` | `[x, y, w, h]` of the top / side toggle (`pc` and `side` only). |
| `lineRects` | `[x, y, w, h]` of each line slot (full width). |
| `allRowRects` | `[x, y, w, h]` of each All Stats row. |
| `search` | `[x, y, w, h]` of the search box. |
| `lines`, `allRows`, `allColumns` | Slot counts. |
| `tones` | The tone names in book_logic.h order. |

## Art

Under `hd/global/ui/panel/statbook/` (with `.lowend.sprite` copies), all built from D2R's own HD sprites at build time:

- `PageBody` (seamless stone, PC)
- `HalfCell`, `FullCell`, `AllCell`, and the `Pad` versions (frames vary the cell inside so stacked cells do not repeat)
- `Tab`, `TabSelected`, `PadTab`, `PadTabSelected` (frames: normal, hovered, pressed, disabled)
- `Rule`, `AllRule`, `PadRule`, `PadAllRule`
- `ScrollTrack`, `Empty`
- `SideBody` (the side panel's frame: D2R's Advanced Stats frame widened by whole knotwork periods, its title band and
  inner page rebuilt as seamless stone), `SideTab`, `SideTabSelected` (the stash tab fitted upright, its stone rebuilt, turned
  to point at the page), `SideHalfCell`, `SideFullCell`, `SideAllCell`, `SideRule`, `SideAllRule`
- `TabsToggleSide` / `TabsToggleTop` (69 x 69: D2R's level-up button, its gold frame and its four frames normal, hovered,
  pressed, disabled, the red inside replaced by the sheet's stone, with a gold glyph of the mode a click switches to: a page
  with its tabs down its left (on the sheet) or along its top (on the side panel); the glyph drawn at 8x, the button made
  at the level-up button's 83 x 84 and brought down once)

The tool's docstring has the method. Nothing of Blizzard's art goes into git.

## Dev previews

`py -3 -I tools/statbook_layout.py build --preview TAB [--query TEXT] [--pad-buttons triggers]` shows one tab with
placeholder values for screenshots before the plugin fills anything. Since the layout's hiding does not hold in game, a
preview leaves out the Stat Book's hidden widgets and moves D2R's hidden widgets off the panel. The layout it started from is
kept in `work/mod/statbook-preview-base/`, and the next build (preview or not) starts from it again. `render --out DIR` draws
the built layouts with PIL and D2R's fonts. A normal build (no `--preview`) writes every widget with tab 0 selected; rebuild
without `--preview` before packaging.
