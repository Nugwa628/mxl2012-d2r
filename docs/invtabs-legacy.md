# invtabs in legacy graphics (lane invtabs-legacy)

Target F of the invtabs plugin: in legacy (classic, G) graphics a basic panel per tab with the item grid, a title, a close
button, room for the bonus summary and a tab row, opened from a button on the classic inventory. Code:
`tools/invtabs_legacy.py` (layout, geometry, inventory button), `tools/invtabs_art.py` (art), tests
`tools/tests/test_invtabs_legacy.py`, `tools/tests/test_invtabs_art.py`.

## Assumed names and interface (for the core lane)

Nothing here exists in `invtabs/` yet; these are the names the classic layouts use. If the core picks others, change the
constants at the top of `tools/invtabs_legacy.py` (`INVTABS` target, `Tab`) and nothing else.

| what | assumed | where it is used |
|-|-|-|
| panel of a tab | `invtabs/<Tab>` (localId = the tab id with a capital first letter: `invtabs/Charms`) | layout root name, tab buttons' `PanelManager:OpenPanel:<panel>`, close button's `ClosePanel`, the inventory button's `TogglePanel` |
| classic layout file | `data/global/ui/layouts/invtabs/<Tab>.json` next to the HD `.../<Tab>hd.json` | D2R reads the one of the graphics mode |
| grid widget | `invtabs/Grid` (InventoryGridWidget, `cellSize` `$ItemCellSize`, rect x / y from `geometry`) | the core binds it to the page (`bindPlayerPageGrid`, `childName`) |
| other widgets | `invtabs/PanelClickCatcher`, `invtabs/Background`, `invtabs/Summary<i>`, `invtabs/Tab<i>`, `invtabs/Close` | `Summary<i>`: empty TextBoxWidgets, classic `8pt`, for the summary lane |
| inventory button | `InvTabsButton` in `playerinventory{original,expansion}layout.json` (classic only) | `add_button_to_layout`, to be called from `tools/ui_layouts.py` |
| art | `PANEL\invtabs_<tab>` (panel, 4 tiles), `PANEL\invtabs_tab_<tab>` (tab button, 3 frames), `PANEL\invtabs_button` | flat names under `data/global/ui/panel/` |
| tab data | `Tab(id, label, title, icon, cols, rows)`; a JSON list with these keys via `--tabs` | the data lane's table / toml give id, name, picture and grid size |

Template form for wild-healer's host convention (`--template`): the root name is `@PANEL@`, the close message
`PanelManager:ClosePanel:@PANEL@`, and the grid is the bare token `@GRID@` where the host splices its own grid widget object
(the host's `GridWidget(slot, x, y)`, with the x / y of `geometry`). Written to
`data/global/ui/layouts/invtabs/<tab>.template.json` for the core to embed; not for the mod as it is.

`py -3 -I tools/invtabs_legacy.py geometry --grid 10x6` prints the numbers as JSON. For the default 10 x 6 tab:

| item | classic pixels in the 320 x 432 left panel |
|-|-|
| panel | rect (-320, -240, 320, 432), `$LeftPanelAnchor` (as D2R's classic cube / stash) |
| title | drawn into the art, header's lower name box (75, 49)-(247, 66), D2R classic `font6`, gold |
| summary box | (20, 86)-(302, 164): 5 lines of 12 px, about 42 characters each (8pt, 6.4 px a character) |
| tab row | 12 places of 24 x 24 at x 17 + 24 i, y 168 |
| grid | origin (16, 198), 10 x 6 cells of 29 px; its last row always ends on the stash's own bottom line (y 372) |
| close | (275, 383, 32 x 32), `PANEL\buysellbtn` frames 10 / 11 (D2R's classic close) |

## The premise: does D2R load a plugin panel's classic layout? Yes (2026-11-11)

The unfinished lane charminv-legacy assumed that a plugin panel layout without the `hd` suffix is used in legacy graphics.
Settled in game on slot 3 with today's install (main 1d2719c build, `install_mod.py --charminv`, CharmInv 1.0.1, whose MPQ
ships only `charm-inv/CharmInvPanelhd.json`), the old lane's staged `charm-inv/CharmInvPanel.json`, its art and its
inventory button copied into the run's data only:

- Legacy graphics, `charminv open`: the classic panel draws in the left slot (header look 20.3 against the art, threshold 40;
  CharmInv logged "panel is now open"), no "could not find its panel layout" line, no stray HD title over the backpack.
- The classic inventory button (`TogglePanel:charm-inv/CharmInvPanel`) opens it; the panel's close button
  (`ClosePanel`) closes it; at 1600 x 900 and 1280 x 720.
- Items sit in the cells: a +7 Strength charm moved from the backpack to cell (0, 0) lands on page 6 at (0, 0), Strength
  30 -> 37 (backpack) -> 30 (held) -> 37 (in the grid); two more at (3, 1) and (9, 3); tooltips show.
- G to HD and back to legacy: the game keeps answering, and the button opens the classic panel again after the switch
  (the panel was not open at the switch, so "open across G" is not checked).

So both ways of supplying the classic file work: a loose file in the mod (this run) and a ResourceService registration
(mxl2012-core's own panels: `plugin/src/send_stash.cpp`, `plugin/src/devmenu.cpp` register `<id>hd.json` and `<id>.json`;
the developer menu's classic panel, docs/dev-menu.md).

Evidence: `mxl2012-runs/invtabs/legacy/evidence/premise2/` (`legacy_panel_open.png`, `sheet_1600.png`, `sheet_1280.png`,
`run.txt`), harness run folder in the worktree's `work/runs/checks-20261111-120343-s3`.

## How wild-healer's host registers layouts, and what invtabs must add

`aaa-player-page-host/src/host.cpp` (upstream copy in `mxl2012-runs/invtabs/upstream/`):

- At load it registers a pool of panels (`RegisterPanels`): localId `Area<n>` / `All`, flags `CloseOnEscape |
  GameplayLeftSlot` (overlay slots none), each bound to the page with `bindPlayerPageGrid` (`childName`
  `aaa-player-page-host/Grid`).
- `SyncLayout(slot)` builds the slot's layout text (`WantedLayout`: the client's own layout with `@PANEL@` / `@GRID@`
  replaced, or `DefaultLayout`) and registers it with ResourceService as
  `data/global/ui/layouts/aaa-player-page-host/<Area<n>>hd.json`. When the text changed, it first sends
  `PanelManager:UnloadPanel:<panel>` and unregisters the old handle. It is called at registration and before every open.
- The grid is always 16 x 16 cells (`GridWidget`) with the marker `chronicleFlourishOffset {7300 + slot, 7300}`; the host
  wraps the shared grid vtable (draw, item rect, valid cell, cell at point, cell rect) so a marked grid shows and accepts
  only its area, drawn at the grid's corner.
- Only the `hd.json` name is registered. `DefaultLayout` is HD-only anyway (`PANEL\closebtn_4x`, a `d2rloader\...` sprite
  background, `pointSize 40`). In classic D2R finds no `<Area<n>>.json`, which is CharmInv's situation before this lane: no
  usable classic panel.

What invtabs must do for classic, next to the HD registration (one more handle per slot / tab):

1. Register `data/global/ui/layouts/<plugin>/<id>.json` (no suffix) with the classic layout whenever it registers
   `<id>hd.json`, in the same `SyncLayout` step (unload, unregister the old classic handle, register the new one). The text
   is this lane's template for the tab with `@PANEL@` and `@GRID@` replaced exactly as for HD, the grid origin from
   `geometry` (classic pixels, cells of 29: `$ItemCellSize` is 29 in classic).
2. Skip the classic registration for a tab that `check_size` refuses (more than 10 columns, more than 7 rows) and log the
   reason once; such a tab is HD only and is left off the classic tab row (`classic_tabs`), so no classic button opens a
   panel without a classic layout. (An unregistered classic layout is what made CharmInv's HD title draw over the
   backpack in legacy before this lane.)
3. Keep the panel names fixed per tab (`invtabs/<Tab>`, not `Area<n>` handed out by lease order): the classic inventory
   button is static mod data and names the first tab's panel.
4. The art must exist for the size registered: it is built at mod build time for the size in the toml (see "Grid size"
   below).

Not proven, for the core lane to check in game: the host's vtable wrap in classic. The 16 x 16 marked grid relies on the
wrapped draw / cell functions to show only the area; if classic draws grids through another path, a marked grid would draw
16 x 16 cells of 29 px (464 px, past the panel). The stand-in proof above used CharmInv's own page with a plain 10 x 4 grid.
Check first thing when the core plugin loads: a classic panel with the marked grid, items at the area's corner cells.

## The panel

Built per tab by `tools/invtabs_art.py` from Median's `tradestash.dc6` (the stash Median players know), so header, vine
border and bottom band stay Median's own art. Top to bottom:

- Header: unchanged; the title in the lower name box (font6, gold), the upper box plain (its divider covered).
- Summary box: Median's name box stretched (corners kept, rims drawn longer) inside the stash frame, 2 to 8 lines.
- Tab row: up to 12 buttons of 24 x 24 (rim grey, pressed darker with the picture one pixel down-right, this tab gold),
  the tab's classic item picture scaled into 20 x 20. Only tabs that exist and fit classic are written.
- Grid: the stash's own cells (its last `rows` rows, its first `cols` columns), centred, dark at the sides of a narrow grid.
- Bottom band: the stash's, with D2R's classic close button on its gold-framed square.

Previews (`work/invtabs_art/`, `--mock maps,potions,...` draws review-only extra tabs and sample summary lines):
`mock_<tab>_<cols>x<rows>_x2.png`, `panel_..._x2_grid.png` (cells traced in cyan).

### Grid size

Any size 1..16 on each side for the page. Classic: at most 10 columns (290 px of grid in the 320 px panel; an 11th column
would cover the frame and the right panel) and at most 7 rows (the title, 2 summary lines and the tab row must fit above;
8 rows would leave 1 summary line). Larger is refused with `ClassicSizeError`, message e.g. "grid 10 x 8: the classic panel
(320 x 432, 29-pixel cells) fits at most 7 rows under the title, 2 summary lines and the tab row; this tab has no classic
layout and shows in HD graphics only". The build skips the tab's classic layout and art and logs that line. The default
10 x 6 leaves 5 summary lines, CharmInv's 10 x 4 8 lines.

A grid size changed in the toml after the mod is built has no matching classic art. The core should register a classic
layout only for the size the art was built for (the coordinator decides how the build reads the toml; `--grid` / `--tabs`
take it).

## Commands and build steps

```
py -3 -I tools/invtabs_art.py build --out work/mod/data [--target invtabs|charminv] [--grid 10x6] [--tabs tabs.json]
py -3 -I tools/invtabs_legacy.py build --out work/mod/data [same]      (writes, then checks; exit 1 on problems)
py -3 -I tools/invtabs_legacy.py build --out <dir> --template          (host templates)
py -3 -I tools/invtabs_legacy.py check --out work/mod/data [--no-inventory]
py -3 -I tools/invtabs_legacy.py button --out work/mod/data            (the inventory button; normally ui_layouts.py)
py -3 -I tools/invtabs_legacy.py geometry --grid 10x6
```

For the coordinator (not done here, files of other owners): in `tools/build.py` `ART_STEPS` after `legacy_art.py`, run
`invtabs_art.py build` then `invtabs_legacy.py build`; in `tools/ui_layouts.py` `inventory_original` /
`inventory_expansion`, wrap the classic text in `invtabs_legacy.add_button_to_layout` (after the send-stash buttons, as
the old lane did for CharmInv). The old lane's `charm_inv_*` files are superseded by these; `--target charminv` gives
CharmInv 1.0.1 a classic panel today if the package ships CharmInv before invtabs replaces it.

Nothing of Blizzard's or Median's is in git: the art and the layouts are written into the mod's data folder under the
gitignored `work/`.

## Game proof with CharmInv as the stand-in (2026-11-11, slot 3, background input)

`--target charminv` (10 x 4, one tab), built into a copy of main's finished `work/mod/data`, installed with
`install_mod.py --slot 3 --charminv`, run under `heavy_lock.py game invtabs-legacy` and the slot lock; the slot got main's
developer install back afterwards (without CharmInv, as before) and was unlocked; throwaway character `InvTabsLegacy`.

| check | 1600 x 900 | 1280 x 720 |
|-|-|-|
| inventory button visible, tooltip | PASS | PASS |
| button opens the panel (art, title, summary box, tab, grid) | PASS | PASS |
| charms in the cells: (0, 0), (3, 1), (9, 3) on page 6 at those cells, tooltips | PASS | PASS (same charms) |
| tab button tooltip "Charms", close tooltip "Close" | PASS | PASS |
| close button closes the panel, inventory stays | PASS | PASS |

The first proof run showed specks of the header's ornament on the grid's top line (the stash frame's top line was reused);
fixed by keeping the cell line above the grid's rows; the final run (a fourth charm at (5, 2)) shows the fixed art at both
sizes. Logs: 0 crash files in every run; in the premise and first proof runs one `BC_ASSERT: wPrefix != 0 || wSuffix != 0`
at the moment the harness made the test charm (`item x1x`), not from the panel.

Evidence (outside git): `mxl2012-runs/invtabs/legacy/evidence/final/` (final art: `f1600_*`, `f1280_*`,
`sheet_final.png`, `closeup_1280.png`), `.../evidence/proof/` (first run, `zoom_gridtop.png` shows the specks),
session logs `*-session.log`, scripts in `mxl2012-runs/invtabs/legacy/scripts/` (`session.py`, `live.py`, `lsteps.py`) and
`proof/` (`prep.py`, `steps.py`).

## Open

- The host's area-limited 16 x 16 grid in classic (see above): the core's first classic check.
- Tab switching between two tab panels (one tab exists today); `OpenPanel` of another `GameplayLeftSlot` panel is expected
  to replace the open one.
- Summary lines: empty in the layout; the summary lane fills them through D2R's text setter (as the developer menu does in
  classic, docs/dev-menu.md); 42 characters a line, 2 to 8 lines.
- Tab pictures: `icon` per tab comes from the data lane's table; charms use D2R's small charm (`invchm`).
- Controller (pad) classic layouts are not covered.
