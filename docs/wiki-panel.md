# Wiki panel (plugin part `wiki`)

For players: [wiki-guide.md](wiki-guide.md). Off word `wiki`. Code: `plugin/src/wiki.cpp`, rules in `plugin/src/wiki_logic.h` (test
`wikilogic_tests`), the parts shared with the developer menu in `plugin/src/panel_shared.cpp` and `panel_logic.h` (test `panel_tests`), layout
from `tools/wiki_layout.py` (`plugin/src/mxl_wiki_layout.h`, committed; `tools/tests/test_wiki_layout.py` checks it is current), content table
from the exporter of lane wikipanel-data (`wikipanel_export.py`), in-game checks `wiki`, `wikilook`, `wikilab` (`tools/wiki_checks.py`).

## What it is

One native D2R panel, `mxl2012-core/Wiki`, HD graphics only, opened by the Controls action `mxl_wiki` ("Wiki", category "D2R-XL 2012",
default **J**, rebindable in the Controls menu). It lists and shows the mod's own reference text: uniques, sets, runewords, gemwords, base
items, cube recipes, monsters, skills, ubers and the prose pages. It reads no game state and changes nothing.

- **No single-player gate.** The part calls no server function, hooks no server frame and looks at no unit: its only game calls are the
  panel, widget, input and thread services, D2R's text setter, and (for the two notices) the client's own chat handler with a client player
  present. So it opens the same way in single player, in a TCP/IP game and in a joined game. Checked by reading the code; a multiplayer run
  was not made.
- **Offline.** All content is the mod's table `wiki.tsv` in its data folder `mxl2012-wiki`, built from the mod's own files (lane wikipanel-data). The
  plugin reads it once at load (`panel_shared::ReadModFile`, as the developer menu reads its catalog): the built table of 2026-11-11
  (6.4 MB, 3,855 entries, 89,254 lines) is read and parsed in 31 to 47 ms at game start and takes about 12 MB of memory. A search over it
  runs when the typed text changes, not every frame (0.5 ms for 10,000 entries in the unit test).
- **A missing or unusable table** leaves the panel closed: the plugin log says why (one line), and the key prints "The wiki text was not
  found in this installation of the mod." in the message log.
- **Classic graphics.** There is no classic layout. The key prints one line in the message log, "The wiki is only available in HD
  graphics.", and nothing opens; a panel that is open when the graphics mode changes is closed with the same line. The line is a client-only
  chat record (the path of the map level action, [d2r-addresses.md](d2r-addresses.md) section 13), not sent while an NPC talks.
- **Welcome page.** With nothing typed in the search box the panel opens on the entry named "Welcome" (the how-to and the credit to
  Brother Laz are that entry's text; the panel has no credit line of its own). A table without that entry opens with an empty text pane.
  A search left in the box is still there on the next opening, with the entry that was shown.

## The panel

2800 x 1660 units of the 3840 x 2160 HD screen (1167 x 692 pixels at 1600 x 900), centred, its bottom above the HUD. It fits 16:9 at any
size and a 4:3 window (2880 units wide). From the top: title and close button; the search box and Back; one row of category buttons ("All"
and one per category of the table, labelled from the table's `C` lines); the result list (22 rows) on the left and the entry's text (27
lines) on the right; under each a foot line ("Uniques: 770 entries. Page 1 of 35", "Lines 1-27 of 108") between two arrows; one status line.

- **Result rows:** the name on the left, the subtitle right-aligned in grey in what the name leaves of the row (60 characters). The arrow
  in front of a row opens the entry; the open entry's row is yellow.
- **Entry text:** the table's lines, wrapped to 80 characters, each in its table colour. Page buttons, the mouse wheel (3 lines a notch;
  over the list it turns the result pages) and Page Up / Page Down scroll it. The wheel and the two keys are taken from the game only while
  the panel is open (the wheel only over the panel).
- **Links:** an entry's `K` lines become its last lines ("See also", then one line per link, links to names the table does not have are
  dropped at load), so they scroll with the text and there is no limit on their number. A link line has an arrow in front of it; it opens
  that entry, and Back returns to where the link was followed, at the old scroll position (16 steps). Choosing a row empties Back.
- **Search hits:** an entry opened from a search starts two lines above the first line that holds every typed word (or, when no line has
  them all, the first that holds any), when that line is not on the first page; every such line has a `>` in front of it
  (`wiki_logic::FirstMatchingLine`). This is what makes a long list entry ("all mystic orbs") usable from a search by effect.
- **Typing, Esc, the key:** as in the developer menu, from the same code: a click on the box gives it the keyboard until the next click
  elsewhere; bound keys then type instead of running their commands; Esc and the panel's key close it, also from the box.

## How it is built

- **Shared with the developer menu** (`panel_shared.cpp`, `panel_logic.h`; the developer menu's unit tests and its game checks are
  unchanged): layout resources, the UI message listener for button clicks, D2R's text setter with change tracking (`SetLine`: only a text
  that changed is sent, every text when the panel opens), the search box typing fix (one subclass of the game window for both panels), the
  mouse wheel and extra keys for an open panel, reading a table file from the mod, and the pure rules (tab-separated lines, word search,
  pages, cutting and wrapping, which keys type, pixel to panel units).
- **Buttons.** D2R hands a button's `PanelManager:OpenPanel:<name>` message to plugins only when `<name>` is a registered panel, and the
  loader allows a plugin **64 registered panels** (seen in game: the 65th registration fails). The developer menu uses one name per button
  (31); this panel has 66 buttons, so all of them send one name, `mxl2012-core/WikiB_0`, and the plugin finds the button from where the
  left button went up (`panel_shared::LastClick`, `panel_logic::RectAt` over `ButtonRects` of the generated header; the rectangles do not
  overlap, a geometry test). The game still decides whether a click was on a button at all.
- **Colours** (answer by experiment, check `wikilab`): D2R's text setter draws colour codes inside a text as written (`ÿc4`, also with the
  style option `pipeCharacterBehavior: handle`, and `|c` forms), and a text box has one colour, set by its style in the layout. So every
  detail line is ten text boxes at the same place, one per table colour (`DetailText<line>_<colour>`); the plugin fills the box of the
  line's colour and empties the one that held the line before. A row's name is two boxes (white, yellow for the open entry).
- **One box per line, not one tall box.** A tall text box with `newlineHandling: standard` and `lineWrap: true` does show several lines and
  wraps by the real glyph widths (seen in game), but it has one colour, the plugin cannot know where D2R broke the lines (so it cannot
  scroll by lines or put a link arrow beside a line), and the game does not cut what does not fit. With one box per line the plugin wraps
  by character count and sends only the lines that changed: a scroll by 3 lines sends up to 27 texts (plus one empty text for each line
  whose colour changed), opening the panel sends all 372 once, and a tick with no change sends nothing. The panel is ticked every 100 ms
  while open and not at all while closed.
- **Fonts and widths.** Rows and entry lines use D2R's `Formal` face (mixed case); the default face draws capitals only and is kept for
  the title, labels and foot lines. Measured at 1600 x 900 on `wikilab` screenshots: Formal at `$SmallFontSize` takes 15.7 panel units a
  character for prose, 16.8 for digits, 18.6 for capitals; the layout counts 18 (80 characters in the 1440-unit text line, 60 in a row),
  so an all-capitals line of 80 characters would run 18 pixels past the pane.
- **Category labels** come from the table, so the layout holds placeholders (`@C<n>@`) that the plugin replaces before it registers the
  layout; slots without a category are hidden.

## Content table and rules

Format and exporter: lane wikipanel-data (`wikipanel_export.py` and its own document). Parser, search ranking (name starts with the query, name holds
every word, the rest), pages, wrapping, scrolling, links, history and the view state: `wiki_logic.h` (lane wikipanel-logic). The panel adds
to it `FirstMatchingLine` / `HasAnyWord` (search hits), uses `internal::Show` for the Welcome page, and takes `SplitTabs` and `ToInt` from
`panel_logic.h` like the developer menu.

## Checks

`MXL_RUN=<lock> MXL_SLOT=2 MXL_CHAR=<letters> py -3 tools/game_checks.py --slot 2 all wiki` (also `wikilook`, `wikilab`). The checks read
the installed table (`work/mod/data/mxl2012-wiki/wiki.tsv`) and pick their entries from it; before the exporter is part of the build,
`py -3 tools/wiki_checks.py use-table <wiki.tsv>` puts a table there for `tools/install_mod.py`. Harness verb (dev builds): `wiki [state] |
open | close | press <button> | input <text> | box | raw <widget> <text>`. Results: [testing.md](testing.md) "Lane wikipanel".

## Limits

- Mouse only: the buttons are found from the pointer, so a controller cannot press them.
- The category row's labels are small (20 units high: eleven buttons in one row). The open category is named in the list's foot line.
- Text is wrapped by character count, so prose lines end at about 85 % of the pane's width.
