# HD UI: skill trees, inventory and cube panels, layouts (phase 5, 2D UI part)

Lane `ui`, 2026-10-28. Pure Python (Pillow), no game run. Source: the pure v005 extraction `mxl2012-runs/extract-mpq` (from the
archive.org D2SE/D2GL repack's `patch_d2.mpq`; re-check against the ModDB zip when it lands). Output is gitignored
(`work/hd-ui`); the sprites and layouts travel in the asset pack, not in git.
(`tools/skill_tree_art.py`, `ui_panels.py`, `ui_layouts.py` also exist on `main` in versions for
D2Sigma art; the files here are rewritten for 2012's 1.13c data and win in this repo.)

```
py -3 -I tools/hd_ui.py baseline <extract_dir>                 once: copies what we read of D2R 93847 into work/d2r-baseline/ui
py -3 -I tools/hd_ui.py build                                 skill trees, panels, layouts, then the check (a few seconds)
py -3 -I tools/hd_ui.py check                                 only the check
py -3 -I -m unittest discover -s tools/tests -p "test_ui.py"  32 unit tests on synthetic data (no game files)
```

`MXL2012_EXTRACT` overrides the extraction folder, `MXL2012_UI_OUT` the output (default `work/hd-ui`). Needs Pillow
(`tools/requirements.txt`). Each tool has `--preview DIR` where it makes pictures.

## What 1.13c changes against D2R

Median XL 2012 is a 1.13c data mod, so its UI is the classic 640 x 480 UI with the mod's own tables:

| UI part | Mod (v005) | D2R | Result |
|---|---|---|---|
| Skill pages | 3 per class, two chains of 5 in columns 1 and 3, rows 1-5 (210 skills = 7 x 30) | 3 per class, own cells | D2R's tab strip kept, sockets and arrows redrawn for the mod's cells |
| Player inventory | 10 x 6 (`inventory.txt`; same numbers for all 7 classes) | 10 x 4 | new panel art + layout |
| Horadric Cube (`Transmogrify Box`) | 10 x 8 | 3 x 4 | new panel art + layout |
| Stash (`Big Bank`) | 10 x 10, one personal page | 10 x 10 | **D2R's HD stash unchanged** (nothing to generate; the mod's `tradestash.dc6` is vanilla expansion bank art) |
| Trade 10 x 4, vendor 10 x 10, hireling | as D2R | | D2R's, unchanged (checked against the layouts' `cellCount`) |
| Character sheet (`invchar6.dc6` set 0) | vanilla layout | | D2R's HD sheet unchanged |

`ui_check.py` prints the table comparison (grid sizes of every `inventory.txt` row, mod against D2R's baseline copy).

### Panel sizes: the larger grid wins (owner decision 2026-10-28, lane qol)

Per panel the grid with more cells is used, Median 2012's or D2R's (D2R's on a tie, so D2R's panels and behaviour stay where
nothing is gained). `tools/txt_migrate.py` (`inventory_sizes`, `larger_grid`) writes the rule into `inventory.txt` of both
banks (the 800 x 600 "...2" rows the same), Warlock rows take the Assassin's; `ui_check.py` ("built tables") checks every
built row against the rule and that each panel's layout, the mod's or D2R's own, draws the table's size, HD and classic.

| Panel | `inventory.txt` row | Median 2012 | D2R 3.3 | Used | Layouts (HD / classic) |
|---|---|---|---|---|---|
| Player inventory (all 8 classes, Warlock incl.) | Amazon .. Warlock, ...2 | 10 x 6 | 10 x 4 | **10 x 6 (Median)** | mod: `playerinventory{original,expansion}layout{hd,}.json` |
| Horadric Cube (Transmogrify Box) | Transmogrify Box Page 1 / Box2 | 10 x 8 | 3 x 4 | **10 x 8 (Median)** | mod: `horadriccubelayout{hd,}.json` |
| Personal stash | Big Bank Page 1 / Page2 | 10 x 10 (one page) | 10 x 10 | **10 x 10 (D2R)** | D2R's `bankexpansionlayout{hd,}.json` |
| Shared stash tabs | Big Bank Page 1 (each tab) | none (PlugY pages were a repack feature) | 10 x 10 per tab, D2R's tab count | **D2R's, unchanged** (owner: "as D2R has it") | D2R's |
| Materials / gems stack tab (RotW) | - (AdvancedStash slots) | none | D2R's | **D2R's** (owner: keep) | D2R's (a classic layout + art down-rendered from D2R's HD pages is built but kept out of the mod: it crashes D2R without RotW, docs/legacy-graphics.md section 9) |
| Classic bank (non-expansion characters) | Bank Page 1 / Page2 | 6 x 4 | 6 x 4 | 6 x 4 (D2R) | D2R's `bankoriginallayout{hd,}.json` |
| Trade, each side | Trade Page 1 / 2 | 10 x 4 | 10 x 4 | 10 x 4 (D2R) | D2R's |
| Vendor | Monster | 10 x 10 | 10 x 10 | 10 x 10 (D2R) | D2R's |
| Guild Vault, Trophy Case | (1.13c leftover rows) | 10 x 4 | no row | not used (no such panel in either game) | - |

The pixel columns of the rows (gridLeft .. gridBottom, the slot boxes) stay D2R's numbers in the built table: D2R places
grids and slots from the layout JSON (the mod's layouts take Median's numbers, see below), which also works
for larger grids; lane qa saw the classic 10 x 6 grid line up in game with these tables.

**Seen in game (lane qol, 2026-10-28, slot 2, build of `lane/qol`, Sorceress `QolSorc`).** Server side, filled with 1 x 1 items
through the harness (`item jew inv|cube` until "no room"): the inventory holds 60 cells (an item at x 9 y 5), the cube 80
(max x 9 y 7). Drawn full and lined up in HD and classic: inventory 10 x 6, cube 10 x 8; stash: Personal 10 x 10 and Shared
3 pages of 10 x 10 (D2R's, HD and classic). No assert, no crash file (`logscan`). Screenshots in `mxl2012-runs/qol/`
(`inv_full_hd.png`, `cube_hd.png`, `inv_classic.png`, `cube_classic.png`, `stash_hd.png`, `stash_shared_hd.png`,
`stash_classic.png`). The test account has no Reign of the Warlock, so the materials tab and the Warlock were not seen.

## What is generated

### Skill trees (`tools/skill_tree_art.py`)

- `data/hd/global/ui/spells/skill_trees/{am,so,ne,pa,ba,dr,as}skilltree.sprite` + `.lowend.sprite` (14 files): per class 3 frames
  of 895 x 1169 (stride 897; lowend 447 x 584), frame n = tab n active, D2R's own strip with the active tab lit, below it **the
  mod's own page art** (lane hdicons2): set n + 1 of `skltree_<x>_back.dc6`, its page part (228 x 432, left of the tab column)
  with Median's stone, socket boxes, level boxes and arrows. Same file sizes as D2R's (same dimensions).
- Geometry: scaled by 2.63 (classic row pitch 68 -> D2R's HD row pitch, rows 1-5 land on D2R's `skillRow`, a 48-px box hole
  holds D2R's 130-px icon; classic y 0 lands right under D2R's 96-px tab strip). The page is cut in three: x 0-90 (column 1)
  placed on D2R's HD column 1, x 124-228 (column 3, incl. page 3's passive frame) on D2R's column 3, the empty column-2 stone
  between (x 90-124) stretched sideways to the wider HD gap (2.8x). D2R's layout stays as it is (the Warlock shares it).
- D2R draws the level number in a box right of the icon's upper half (`LEVEL_HD`, measured on D2R's socket art); Median's
  art has its level box at the icon's lower-right corner, so each cell's level box is moved there (10 right, 11 up, classic
  pixels) and the corner it leaves is filled with the icon box's mirrored lower-left corner and the stone above.
- Tab n (0 = leftmost) shows SkillPage 3 - n (`page_of`; the classic tab column lists page 3 at the top), so frame n is drawn
  from set 3 - n of the DC6 and that page's cells. Before this the frames used page n + 1: the art of page 1 sat behind page
  3's skills (seen in game 2026-10-29, fixed the same day; the older socket drawing had the same indexing).
- In game (slot 4, 2026-10-29, Sorceress and Amazon, HD and classic): every tab shows the art of the page whose skills it
  holds, the same as classic (page 3's passive frame on the leftmost tab), icons in Median's boxes, the level number inside
  the moved level box (Moonstrike 7, Flamefront 5, Cold Blood 3; Ghost Arrow 4, Takedown 6).
- The tab column of the classic art (Median's labelled tree icons) has no place in D2R's HD tree: D2R's tab strip with the title
  strings below stays. A class whose skills sit off columns 1 / 3, or without the DC6, falls back to the older drawing (D2R's
  socket art on each skill cell and drawn arrows); none does. Cells come from `skills.txt` (`charclass`, `skilldesc`) and
  `skilldesc.txt` (`SkillPage/Row/Column`).
- `data/local/lng/strings/mxl2012/skill_tab_titles.json`: 21 `d2r:SkillCategory<Am|So|Ne|Pa|Ba|Dr|As><1-3>` override records, the
  tab titles. D2R draws the title as text from those keys (its layout's `textTab0-2`) with its own class names, so the
  right titles are string overrides, not sprite art, and the skill tree layout stays D2R's (Warlock's keys and `waskilltree`
  untouched). **The strings lane/coordinator has to merge this file into `mxl2012/overrides.json`** (same record format as
  `tools/tbl2json.py` writes). A page title is the two labels of its two trees, as the classic art prints them (`TAB_LABELS`,
  read from the pictures by eye, cut words written out): e.g. Barbarian "Special / Rage", "Stances / Spirits", "Throw / Melee".
- Classic mode (G) needs nothing: the 7 `skltree_<x>_back.dc6` are the mod's own (4 sets of four 256/64 x 256/176 tiles, the
  structure D2R's classic layout expects; checked) and ship as they are.

### Skill trees: HD page candidates (`tools/skill_tree_hd.py`, lane skillhd, OFF)

The shipped pages above are Median's page scaled x 2.63 with Lanczos: right place, soft look (a 1 px frame line becomes a
3 px blur, the column-2 stone stretched 2.8x sideways shows streaks). Lane skillhd (2026-10-30) made three sharper candidates
for the owner's review; **none ships**: `tools/data/skill_tree_proposals.json` has `enabled: false` (its `method` names the
one it would ship, today `rebuild-stone`), so a normal build draws `lanczos` as before. The candidates keep median_page's
geometry exactly (the three parts, the cells on D2R's `skillRow` / `skillColumn`, the moved level boxes, D2R's tab strip),
only the picture changes; classic mode (G) is not touched.

| Method | What it draws |
|---|---|
| `lanczos` | the shipped page (above) |
| `rebuild` (A) | Median's page; its structure (frames, coloured rims, arrows, box holes, level boxes, the page edge, page 3's passive frame: `structure`, bright / dark / saturated pixels round the cells and the page edge, groups of 40+) rebuilt edge-aware as `rune_hd` does: every colour channel split in 12 tone levels, each level's mask EPX-scaled twice, smoothed and cut with an anti-aliased edge at the HD size, stacked again, the rest between two levels bilinear. Crisp straight edges, Median's colours only. The stone between is Lanczos + unsharp mask (the tone decomposition makes stone look posterised) |
| `rebuild-stone` (B) | A's structure; the stone between is D2R's own HD stone (`panel_skilltreebg`, the picture behind D2R's tree, at the same place) carrying Median's stone tone: Median's stone low-passed (3 classic px) + D2R's stone high-passed (9 HD px) |
| `d2r` (C) | D2R's HD skill tree look with Median's layout: the page left transparent so D2R's own stone shows, every skill cell D2R's engraved socket + level box, every arrow of Median's chains D2R's short arrow (both cut from frame 1 of D2R's `soskilltree`, `D2R_ART`), each tree's colour (the coloured rim of Median's boxes, sampled per cell) as a thin rim round the socket, a column without arrows (page 3's passives) in an engraved frame as Median draws it |

```
py -3 -I tools/skill_tree_review.py <out>                    review sheets: per class legacy | HD now | A | B | C (each tab), 1:1 details, overviews
py -3 -I tools/skill_tree_art.py --try d2r                   a TRIAL build of the tree sprites with one method (owner review only)
MXL2012_SKILLTREE_TRY=rebuild-stone py -3 tools/build.py     the same through the whole build (hd_ui.py build)
```

`hd_ui.py baseline` now also copies `panel_skilltreebg.sprite` (B and the review sheets need it). A trial run of
`skill_tree_art.py` into `work/mod` writes `skill_tab_titles.json` there again: delete it before an install (the build merges
it into `overrides.json`; a stray copy stops D2R's string tables loading: "String tables are unavailable", MonType.txt, no
startup; seen by lane skillhd).

Weak spots: A and B keep Median's stretched column-2 stone tone (A its streaks; B only its low-pass, faint smudges); B's stone
is lighter and flatter than Median's speckled stone; C drops Median's own box art (bright bevelled frames, the arrow shafts
through the boxes) for D2R's engraved style, Amazon / Necromancer / Assassin pages without coloured rims look plain; at
1600 x 900 the page is drawn at about 0.35 x, where the gain of A over the shipped page is small. Review sheets and in-game
shots: docs/testing.md "Lane skillhd".

### Inventory and cube panels (`tools/ui_panels.py`)

- `data/hd/global/ui/panel/mxl/{inventory,cube}.sprite` + `.lowend.sprite` (1162 x 1507 / 581 x 753): the mod's classic 320 x 432
  pictures (`invchar6.dc6` set 1, `supertransmogrifier.dc6`) scaled x 3.631 / x 3.488 (the pixel-art upscaler `upscale.hybrid` + sharpen since lane hdpolish, was Lanczos; premultiplied alpha), referenced
  by the layouts as `PANEL\mxl\inventory` / `PANEL\mxl\cube`.

### Layouts (`tools/ui_layouts.py`, `data/global/ui/layouts/`)

D2R takes grid sizes from `inventory.txt` but places grids, slots and buttons from its layout JSON, so the layouts are D2R's files
with text edits (checked for balanced brackets, existing sprite references, grid sizes equal to the table):

| File | Change |
|---|---|
| `playerinventoryoriginallayouthd.json`, `playerinventoryexpansionlayouthd.json` | background `PANEL\mxl\inventory`; grid 10 x 6 at the table's place; 10 equipment slots at the table's boxes (D2R's widget size scaled to fit); weapon swap tabs on the picture's I / II boxes; gold button and amount on the picture's coin and bar |
| `horadriccubelayouthd.json` | background `PANEL\mxl\cube`; grid 10 x 8; transmute button on the picture's square |
| `playerinventoryoriginallayout.json`, `playerinventoryexpansionlayout.json` (classic) | `PANEL\invchar6` (the mod's file), grid 10 x 6, slots from the table, swap tabs 16 px up (the mod's arms sit 16 px higher) |
| `horadriccubelayout.json` (classic) | grid 10 x 8 (the mod's `supertransmogrifier.dc6` is what D2R names) |

Items draw at D2R's HD size (98 px per cell) whatever `cellSize` says, so the HD grids keep `cellSize` 98 x 94 and get
`scale` 1.0746 (cell 105.3 x 101.2 = 29 classic px scaled), a mechanism verified in game.

## Not generated (and why)

- **Stash, trade, vendor, hireling, character sheet panels**: sizes equal D2R's, so D2R's HD panels stay. The stash is one 10 x 10
  personal page (no extra pages: PlugY's pages were a repack feature), so no stash-page work applies.
- **Warlock keeps D2R's UI**: its skill page (`waskilltree`) and tab strings are untouched. The inventory and cube panels are
  one shared layout for all classes, so Warlock gets the mod's 10 x 6 / 10 x 8 grids too (`inventory.txt` has no `Warlock` /
  `Warlock2` row in the mod, D2R has: the tables lane must add them with the mod's 10 x 6, otherwise the grid the layout draws
  and the server's differ for Warlock). See Gaps.
- **Other DC6**: the remaining UI DC6 in the MPQ (`FrontEnd/` 7, `bigmenu/` 2, `charselect/` 1 = menu screens) are D2R's
  vanilla menu pictures kept for 1.13c compatibility; D2R HD has its own front end, which stays. `ui/spells/*skillicon.dc6` were
  done by the icons lane; `data/local/ui/eng/` (16 quest/act pictures) are not part of any HD panel.
- **Stock panel labels** (string table: `strpanel*`) follow the strings lane.

## Gaps (also in `docs/unported.md`)

- **Soft panel art.** The inventory and cube are 320 x 432 classic art scaled 3.5x; next to D2R's native HD panels they are blurry,
  and the frame, hinges, title and close button are D2R's, laid over the classic frame. A redrawn HD frame would be the proper fix.
- **Seen in game (lane qa, 2026-10-28).** The layouts load; grids, slots, tabs, gold and the transmute square line up; the stash and the character sheet are D2R's. The HD inventory and cube titles drew "Missing string" (bugs.md #30): `ui_layouts.py` now writes the title as a literal (none for the inventory, "Horadric Cube" for the cube). The classic skill trees showed the title text over the art's own labels (bugs.md #33): fixed, `ui_layouts.py` now writes the classic `skillstreepanel.json` with the seven classic classes' tab title keys emptied and its widget texts / tooltips as literals (a `@key` there draws "Missing string", as for #30); HD is unchanged.
- **Not seen in game (older text, written before the check).** No game run: that D2R accepts the layouts' `scale` on 10 x 6 / 10 x 8 grids, that slots, tabs, gold and
  the transmute square line up (the layout math was checked on an overlay of the generated panels, the classic positions only by
  the table), and the strings merge. The cube's D2R "flourish" animation plays over the bigger grid unchanged.
- **Tab titles are my reading of the art.** The classic tab column labels (two small labelled icons per page; Amazon's still read
  "Special / Defen. / Blood / Spear / Javelin / Bow" like a leftover) do not obviously match the skills of those pages (Barbarian's
  pages are Earthquake/Bear Claw, Spirits/Stances, Companions/Nephalem). The owner may want other titles: edit `TAB_LABELS`.
- **Weapon swap tabs, classic mode**: D2R's `invchar6Tab` widgets moved 16 px up by the arithmetic of the arm slots; not measured
  on the picture.
- **Skill tree stone background** (`panel_skilltreebg`) stays D2R's around the page; the page itself is Median's art (above).
- **Skill tree art quality** (lane hdicons2): Median's 320 x 432 classic pages scaled 2.63x are softer than D2R's HD art, the
  stretched column-2 stone shows sideways streaks, and Median's tab column (labelled icons) is not shown in HD (seen in game).
- **Warlock inventory/cube rows**: above.
