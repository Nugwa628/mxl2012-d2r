# Median XL 2012 maps in D2R 3.3 HD

Lane maps, 2026-10-28. Tools: `tools/maps_hd.py` (plan, report, scenes, docs tables), `tools/ds1_remap.py` (.ds1 reader and id
renumbering), `tools/dt1.py` (.dt1 reader), tests `tools/tests/test_maps.py` (35 tests, synthetic bytes, no game files).
Nothing here ran in the game: every "plan" below is a decision from the tables and the tile data, marked UNVERIFIED until a
game check. Outputs of the tools go to `work/maps_hd/` (gitignored).

Source: the pure v005 mod extract (`mxl2012-runs/extract-mpq`). The original ModDB zip arrives later; the extract comes from the
archive.org D2SE repack. **[re-check]** Anything below that may depend on repack-only files: the repack's 59 Maggot Lair .ds1
(58 new + `magqueen.ds1`, 2022; `docs/unported.md`) are not in the pure mpq and are ignored here; `act2/maggot/magqueen.ds1` in
the tables is the **mpq's** version.

## What Median 2012 changes (34 .ds1, 52 .dt1)

- 34 .ds1: 21 sit at vanilla paths (10 byte-identical to D2R's, 11 edited by Median), 13 are new (`expansion/<set>/<name>.ds1`).
  There are no new levels: all 137 levels and 36 level types are the vanilla ones. Median repurposed level slots (lvlprest
  `File1` points a vanilla level at a new map) and appended its new .dt1 files to vanilla `lvltypes` rows.
- 52 .dt1, all new, under `expansion/<set>/`. Every one is a **retextured copy of a stock tile set**: 51 have exactly the tile
  keys, sizes and walkability flags of a stock .dt1 (Jaccard 1.00, all flags equal); only `expansion/redsquare/inv_wall.dt1`
  differs (0.37: it is the invisible collision wall, no art). So no .ds1 cell needs rewriting for tiles, and a stock .dt1 is a
  drop-in stand-in for collision, walkability and layout. Which stock set each one is: the table below.

## How D2R HD draws a map, and the plan

1. D2R HD builds the scene of a map from `data/hd/env/preset/<ds1 path without .ds1>.json`. A map without one is loaded with a
   default biome and its floors painted from the tile data, but with **no walls and no buildings**. A scene that holds only
   `biomeFilename` (the shape of D2R's own empty presets, e.g. `act3/kurast/chaos08x08_4.json`) gives the right ground and light.
2. A .ds1 does not reference .dt1 files at runtime. Tiles resolve by (style, sequence) across the .dt1 files that lvlprest
   `Dt1Mask` selects from the level type's `lvltypes` `File 1..32`. The .ds1 header's file list is editor metadata. This tool
   reproduces that resolution (`resolve_tiles`) and finds nearly every cell; the few unresolved cells are in the report.
3. Plan per map (`plan` in `tools/maps_hd.py`):
   - **D2R scene**: the map is D2R's own (byte-identical, 10) or Median's edit changes at most 25% of the wall/floor cells at the
     same size (7): keep D2R's baked scene. Walls the edit moved sit in D2R's scene positions until a game check shows what that
     does (a changed wall tile resolves to another stock tile; the baked model does not follow).
   - **minimal scene** (`py -3 -I tools/maps_hd.py build`): the map is new (13), or an edit above the threshold or at another
     size (4: caveroom4, dungrm6a, temple5, temple6). The biome is chosen by a vote of the wall/floor cells through the stock
     stand-in of each .dt1 (shared ground/river sets do not vote); the level type's own biome is shown as the alternative.
     `BIOME_OVERRIDE` fixes `inarius` (a clone of cathy3, whose floors the Barracks tile set shares: the vote alone gives Barracks).
4. **Stand-ins for the 52 new .dt1.** HD textures are keyed by the stock .dt1 path, and the new .dt1 have none. Because each one
   is a copy of a stock set (table below), the plan is a swap at `lvltypes` level: point the type's `File n` at the stock donor.
   Whether D2R HD's tile masks accept the donor path in that slot is UNVERIFIED. All 52 .dt1 still ship (collision and classic
   mode use them), they just carry no HD look.
5. **Art needed.** Walls and buildings of the 13 new maps and 4 edited ones are missing in HD until a scene exists. The last
   column of the first table has three classes: *none (D2R's scene)*; *missing, generatable from stock tiles* (every wall cell is
   a stock tile: inarius, belial, excelsior3, rockisdead, epicwhiners, and the 4 edited maps; a later stage can write a scene
   with stock wall models); *missing, Median's look needs custom art* (the .dt1 stand-in is a stock set, so the map shows
   stock walls: desertpeak, cypherpunk, glados, downtown, moskvich, borgir, macumba, charismatic).

## IDs inside the maps (interface to the idmap lane)

`tools/ds1_remap.py` uses `tools/idmap.py` (`IdMap.build(MOD_EXCEL, D2R_EXCEL)`, `docs/id-mapping.md`) for:

| .ds1 object | Meaning | Source of the new id |
|---|---|---|
| type 1, id below the act's MonPreset rows | a MonPreset row (Median keeps 59/61/43/29/59 per act) | unchanged: the built `monpreset.txt` must keep those counts |
| type 1, id at or above it | a raw MonStats row | `spaces["monstats"].ids()`: rows below 410 stay, Median's own rows move behind D2R's (563 objects change in 12 maps, 39 distinct rows, listed below) |
| type 2 | (act, id) -> D2R's per-act `ObjPreset.txt` -> Objects row | unchanged: Median's `objects.txt` keeps D2R's 574 rows in place, and Median has no ObjPreset table. `Maps.moved_objects()` is checked by `audit` and fails on a move. `tools/objstr.py` (data step) repeats the check against the **built** tables, class by class (docs/id-mapping.md "Objects and ObjPreset") |
| superunique | no .ds1 holds one: `monpreset.txt` Place names them by key | nothing to renumber. Median's superuniques from row 43 up (41) sit one id above vanilla as Median ran them (idmap.md), so D2R's quest code that tests ids (Siege Boss, Ancients, Nihlathak) is a game check |

Negative monster ids are dropped; a raw id with no row in the ID map is an audit PROBLEM. `py -3 -I tools/ds1_remap.py --check
<tiles dir>` counts the changes (34 files, 12 changed, 563 renumbered); without `--check` it rewrites a **copy** in place. The
data step `tools/objstr.py` writes the id table to `work/mod/ds1_ids.json`; `remap_tree(tiles)` (no `Maps` argument) and `--ids-file` read it, so the
installer renumbers the maps without the extracts.

Known risk, `expansion/zakarum/charismatic.ds1`: its header act is 4 (0-based, "act 5") while its level (127) is act 5. D2R
resolves monster rows and objects by the header act. Under the header act, the 7 objects with id 16 are HellLight3 and the 2 with id 53
a ConsolationChest, which fits a lava map; under the level's act they would be a BurningPit and DrehyaInTown. What 1.13c does with
the mismatch is unconfirmed, so this is flagged, not changed.

## Walls of Median's 17 own maps (lanes walls and wallsfix 2026-10-29, hdwalls2 2026-10-30)

`tools/walls_hd.py` (build step after `maps_hd.py build`, tests `tools/tests/test_walls_hd.py`) replaces the minimal scene of
desertpeak, cypherpunk, glados, downtown, moskvich, borgir, macumba and charismatic with a scene that also holds **wall
entities made of D2R's own wall models**:

1. D2R's scenes place walls, cliffs, pillars and roofs as entities (model + transform) at 10 world units per tile
   (x = column * 10, z = row * 10; checked on `act4/mesa/border1a`, the entities sit on the wall cells).
2. **Learn.** Every D2R map that has a scene and whose .ds1 header names a tile file of a folder the 8 maps need (via the
   donor of each new .dt1, table below) is read: its wall cells (all wall layers; key = tile set folder + orientation + style +
   sequence) and the scene entities standing on each cell, with their offset in the cell. Decoration (ivy, ferns, roots,
   rubble, bones, stains, props such as chests, swords and barrels: `DECOR`) is dropped unless it fades with the wall
   (WallTransparencyComponent) or its file names a structural piece (`STRUCTURE`: arches, pillars, walls, fences, the
   jungle treeline). Physics bodies and effects are dropped from the copies (gameplay collision comes from the tiles; HD
   physics only serves corpses).
3. **Pick.** Per cell key the most common variant with models, if D2R gives that key models in at least a third of its cells
   (a wall model spans tiles but stands on one, so its neighbours count as empty), else the empty variant. A key D2R never
   has in that combination takes the variant of one of its tiles (*partial*). **Set pieces** (a model that stands on fewer
   than 3 wall cells in all of D2R: Tyrael's chamber, a tomb's sarcophagus, ...) are left out: copied onto every cell with
   the same key they repeat one unique building piece hundreds of times.
4. **Place.** Every wall cell of the Median map gets its variant at its own position, and every copied entity gets wall
   transparency (D2R gives it only to walls that can hide the player in its own layout; without it desertpeak in HD was
   black at the arrival). The scene keeps maps_hd's biome.

5. **Gaps** (lane wallsfix). A wall tile that no D2R scene has on any cell (downtown's Harrogath walls of style 3: Harrogath's
   own maps resolve those keys to other files) takes D2R's most common single-tile wall of the same orientation in the same
   tile set, else in the same act's sets (`generic`: `Library.generic_pick`; set pieces and variants with props are never
   used: Docktown's commonest orientation-1 piece was a book stack, Harrogath's orientation-7 one a flagpole). Only wall
   orientations 1-9 get one. Downtown's 126 Harrogath cells of orientation 14 (trees, not walls) get D2R's trees since lane
   walls4 (item 13).
6. **Cap** (bug #360 open, asset cache overflow). No generated scene goes above D2R's largest map scene, `act3/docktown/
   docktown3` (4,989 entities, 4,423 of them with a model, 679 distinct models, 4,651,080 bytes): `cap()` keeps at most 4,423
   placed models and 4,651,080 bytes. It drops props first, then details on walls (buttresses, pillars, arches, beams,
   gargoyles: `DETAIL`), then the walls, cliffs and fences that close rooms (`SIGHT`), stairs (`STAIRS`, lane elevwalls)
   last; inside a tier every model loses the same share, thinned evenly over the map (`spread`), not cut by region. The
   cap is our own policy, not a measured engine limit: bug #360's overflow was the monster variant table cache, and no
   entity or byte limit of D2R's scenes is known (lane reimref read the Reimagined level editor: none there either). Only cypherpunk reaches it (5,825 placed:
   1,402 dropped, all 1,802 elevation walls kept). Since lane stairs cypherpunk has its own larger budget (`MAP_LIMITS`, measured in game:
   [below](#stairs-at-fauztinville-lane-stairs-2026-11-07)); since lane hdscene2 that budget is its composed scene (8,620 placed,
   7,999,943 bytes; [Model cache](#model-cache-lane-hdscene2-2026-11-09)); the other 16 maps keep the cap.

Size: the 8 scenes are 10.2 MB of JSON together (before wallsfix 10.9 MB); the largest is cypherpunk, 4,423 placed models,
3.29 MB, 33 distinct models (before: 5,820, 4.31 MB, 42). They name only D2R's own models, no new textures.

**The other 9 maps** (lane hdwalls2). `walls_hd.MAPS` is now all 17 maps maps_hd gives a minimal scene: the 8 above
(`RETEXTURED`) and the 9 on stock tiles (`STOCK`: inarius, belial, excelsior3, rockisdead, epicwhiners and the edits caveroom4,
dungrm6a, temple5, temple6, whose layout is too far from D2R's scene to keep it). Their tiles are D2R's own, so no donor is
needed; the method is the same. Two gaps of the method showed on them and are fixed for all 17:

7. **Model variations.** 87k of D2R's 393k model entities carry no `ModelDefinitionComponent` but a
   `ModelVariationDefinitionComponent` (weighted list of models, the engine picks one): all fences of the Flayer Dungeon, most
   of the ice caves', Mesa, Travincal, the Arcane Sanctuary. walls_hd skipped them, so dungrm6a got 87 models for 475 wall
   cells. They are learnt now (`model_of` takes the first entry, `models_of` lists all for the scene's `dependencies`; the
   component is copied).
8. **Walls on floor tiles** (`floor_cells`). D2R draws some walls on floor tiles: in the Act 1 caves 82% of the wall models
   stand on cells with a floor and no wall tile (5% on wall cells; caveroom4 has 3 wall cells and 87 floor cells), the ice cave
   ledges, Kurast stairs, the Arcane platforms' trims, Travincal's trench. Cells with a floor and no wall are keyed by their
   floor tiles and learnt the same way; `choose()` keeps a floor bare unless D2R gives that floor tile models in a third of its
   cells, and a floor tile D2R never has stays bare (never *uncovered*, never a generic wall).

With both, the self-check on D2R's own maps went from 43% to 55% of their wall entities. The 8 earlier maps change too
(cypherpunk 5,825 -> 10,166 placed pieces, still capped at 4,423; glados 850 -> 3,698, mostly Travincal trench and Kurast
stairs on floor tiles). The 17 scenes are 21.9 MB together; none is above the cap.

**The three partial maps** (lane walls3, 2026-10-30). Why caveroom4, belial and charismatic showed only part of their walls,
the three changes that fix what data could fix (for all 17 maps), and one that did not work:

9. **Raised D2R maps** (`Ground`, `d2r_ground`). D2R's HD camera is orthographic at the true isometric angle, so a piece that
   stands on terrain raised by g is drawn at (x + g, y + g, z + g) to stay over its tile. Most D2R maps are flat, but the
   Fortress interior stands about 35 units up (Travincal, Kurast, the Arcane and the caves a few units): learnt as they were,
   the Fortress walls sat 3-4 tiles off the wall cells they belong to and floated 35 units over Median's flat maps. The
   tool now reads each D2R map's baked terrain mesh (the preset's `terrain` entity, `terrain_lod0.model`: world-space
   positions, `terrain_mesh`) and moves every learnt piece to (x - g, y - g, z - g), the same spot on screen at ground level.
   charismatic (Fortress tiles) went from 366 wall cells without a model to 213, 424 -> 646 placed pieces.
10. **Bare partial walls** (`Library.pick`). charismatic's Fortress walls of style 4 (41 cells of one pair alone) are on no
   learnt cell in D2R; they shared a tile with a key that D2R draws bare and so got nothing. A wall key whose only match is
   such a bare key now gets the tile set's generic wall (`generic_pick`; a key D2R itself draws bare stays bare). charismatic
   213 -> 81 wall cells without a model, 646 -> 887 placed pieces (Fortress walls, gargoyle pillars, columns). The same rule
   fills 170 more downtown cells with Harrogath walls and 114 glados cells with Travincal/Mesa walls.
11. **Pieces on no cell** (`Library.anchor`). D2R's artists place a model where it looks right, not on the tile it belongs
   to. The Act 1 caves' stairs (`back_stairs01`) stand on the void cell beside the stairs tiles (style 3, sequences 8-17) in
   all 21 cave maps that have them, so they were never learnt: caveroom4's arrival (and epicwhiners') had no stairs. A piece
   on no learnt cell is now counted on the rarest learnt key within 2 cells at its offset from it, and placed with that key
   when it is there in at least a third of the key's cells and in 3 or more. Learnt: 135 such pieces on 55 keys; caveroom4 and
   epicwhiners get the stairs, belial 22 Arcane edge pieces (straight walls, corners, trims, gargoyles under the platform
   edge, hidden under the HD floor as long as the void is floor: item 12), dungrm6a 54 broken arches, glados 33 Travincal
   fades. (Hanging also the pieces a cell's own pick leaves out raised
   the self-check from 55% to 71%, but pushed glados, desertpeak and epicwhiners past the cap with props: not done.)
12. **A terrain mesh for the Arcane: tried, no effect** (`TERRAIN_MAPS`, `terrain_model`, left empty). belial's starry void is
   floor in HD, and that floor hides the arches that hang under the platform edges. D2R's own Arcane maps have a terrain
   mesh over their platforms only (sancte: 482 flat triangles at y = 0), while maps_hd's minimal scene has `"terrain": {}`.
   The tool can now write a `terrain_lod0.model` from sancte's (its mesh replaced by flat quads over the map's floor cells,
   positions and UV as D2R's) and give the scene D2R's `terrain` entity naming it. In game (slot 2, run
   `checks-20261030-120504-s2`, and again with sancte's physics body added) belial loaded with no assert, but HD still drew
   floor over the whole void, the same as before. So the HD floor there does not come from the preset's terrain entity
   (perhaps the level's own ground, Ancient Tunnels being a larger level than the 48x48 preset); open, not shipped.
   **Lane tunnels (2026-10-30): closed, cannot be done with the scene.** walls3's mesh was never drawn: the engine finds
   a model only through `data/hd/model_lod_desc.bin` (docs/d2r-addresses.md section 23) and the new path was not in it.
   The tool now can add it (`lod_entry`, `write_lod_desc`: the mod's copy of the index with the path added, the template's
   entry as donor, the mesh padded to the template's vertex and index counts, `terrain_model(pad=True)`; template
   `act3/jungle/pygn2`, whose box 0-330 holds belial's platform at 110-220 x 60-320; texture on the `act2_arcane` biome).
   In game (slot 1, run `checks-20261030-223110-s1`, `wall_belial_hd_*.png` against `wall_belial_classic_*.png`) the
   indexed mesh loaded with no assert and no engine error, and HD still drew the same stone floor over the whole void.
   So the HD floor is not the scene's terrain at all; with a terrain indexed or not, the engine draws it. D2R's own void
   cannot be borrowed from the scene either: belial already names the `act2_arcane` biome, and D2R's Arcane Sanctuary
   (level 74) shares its LevelType 19. What is left that differs is the level itself: level 65 is a maze level
   (DrlgType 2, 47x47, one lvlprest room 1092 with FillBlanks) where level 74 is a preset level (DrlgType 1). Making
   level 65 a preset level changes how the game builds the level, a gameplay-data change for the owner to rule on; it is
   not tried. `TERRAIN_MAPS` stays empty, so the build writes neither a terrain nor an index of its own (the index tool and
   its tests stay for a later map that needs a new model path).
   **Lane tunnels65 (2026-10-31, owner: "try making it a fixed pre made map"): already one; the terrain tried again, no effect.**
   In levels.txt `DrlgType` 1 is a maze, 2 a preset, 3 outdoors (Rogue Encampment 2, Blood Moor 3, Den of Evil 1). So Median's
   level 65 (`DrlgType` 2, 47x47, lvlprest 1091 -> `act2/arcane/belial.ds1` only) **is** a fixed pre-made map, and the Arcane
   Sanctuary (74, `DrlgType` 1) is the maze, built from D2R's 12x12 Sanct rooms; the note above had the two the wrong way round.
   There is nothing to switch on the level side. The .ds1 is not the difference either: belial and D2R's `sanctnsew.ds1` both
   leave the void cells without a floor tile, and both lvlprest rows have `FillBlanks` 1. One untried difference was left in
   the scene: every one of D2R's 2,026 scenes with a terrain names the terrain model in `dependencies.models`, the earlier try
   named it in `dependencies.other`. `add_terrain` now uses `models`, and the build adds the belial terrain (pygn2 template,
   indexed in model_lod_desc.bin) only with `MXL2012_BELIAL_TERRAIN=1` (`walls_hd.terrain_maps`, default off). In game (slot 2,
   check `tunnels65`, in and out by clicks on the warp tiles, HD and classic; runs `checks-20261031-144449-s2` with the switch,
   `checks-20261031-151341-s2` without, sheet `mxl2012-runs/tunnels65/t65_before_after.png`): HD draws the same stone floor over
   the void at the arrival and at both spots with and without the terrain, classic the black void; no assert, no crash file
   either way. **Left off**; the HD floor comes from neither the level type nor the .ds1 nor the scene's terrain. What remains
   untried needs engine work (where HD fills a preset's empty cells) or a different map (one of D2R's Sanct layouts, which
   changes Median's level), so it stays a known issue.
   **Lane voidengine (2026-10-31, owner: "dig into the engine. find what's wrong"): found, a level-74 hard-code in D2R.exe;
   not fixable without new floor geometry.** The stone is D2R's ground plane `data/hd/env/model/global/terrain/outdoor_lod0.model`:
   a routine (D2R 93847 `0x6b4a30`, called from `0x6b3fe8`; per-room loop at `0x6b4b76`) places one plane per room,
   scaled to the room's size, on every level **except level id 74** (`0x6b4b80` `cmp dword ptr [level+0x1f8], 0x4a` / `je`;
   room activation `0x6a1f44` places the same plane for room type 1). That plane is where HD draws a room's floor tiles, so it
   covers the whole room, void cells included. D2R's Arcane Sanctuary skips it and gets its platform floor from its Sanct
   scenes instead; Median's level 65 has no such floor, so it gets the plane. Classic has the same level-74 special case
   (1.14d `DRLGROOMTILE_ProcessTile` `0x0066e9b0`, D2R `0x3f357b`: blank tile flags `0x1e00100` for 74, `0x1e00000` otherwise),
   but in classic both values draw black. Data-side tests in game (slot 1) changed nothing: no terrain in D2R's 53 Sanct/summ
   scenes (74 unchanged), sancte's terrain entity in belial (65 unchanged), the void cells of belial.ds1 filled with 74's blank
   value (both unchanged). Engine test: the immediate at `0x6b4b86` patched in memory from 0x4a to 0x41 (65), run
   `checks-20261031-183526-s1`: **65 in HD shows D2R's starry void** (no assert, no crash file, classic unchanged, 74
   unchanged), **but the platform floor goes with it**: only the edge trims, arches and stairs are left in the void. A belial
   terrain mesh (`MXL2012_BELIAL_TERRAIN=1`) or sancte's own terrain, also moved under the arrival, is not drawn there either. So
   skipping the plane needs a floor model for belial's platform, and the owner rule allows no new 3D models: **no fix shipped,
   no plugin part.** Testing and shots: docs/testing.md "Lane voidengine".
   **Lane tunnelfloor (2026-11-01, owner: "option 1", review sheet first; approved: "this is good for now put it in"): fixed,
   both halves on by default since 0.1.9.**
   (a) Plugin part `void65` (off word `void65` in `mxl2012-core-off.txt`): the compare at `0x6b4b80`
   jumps to a stub that skips the plane for level 74 **or** 65 (docs/d2r-addresses.md section 25); room activation
   (`0x6a1958`) is left as D2R's, its plane being for room type 1 only. (b) the walkways (`MXL2012_BELIAL_WALKWAY=0` leaves them out; `walls_hd.walkway_maps`,
   `walkway_pieces`, `walkway_cover`, `add_walkway`): the floor of D2R's own Arcane Sanctuary is the mesh of each Sanct
   scene's `terrain` entity (`act2/arcane/sanctXX/terrain_lod0.model`); the 29 flat ones are the pieces. A greedy cover places
   them whole, turned in 90 degree steps and moved by whole cells, over belial's 170 platform cells (`terrain_cells`), as plain
   model entities `mxk_<n>` (D2R's terrain entity's model component, without the terrain component and the physics body,
   which drew nothing in the earlier tries). No new model: D2R's meshes as they are. Result: 14 pieces cover all 170 cells
   and draw 15 cells over the void (the inside of the top ring by the north bar, cells 14-16 x 8-9, and four other spots);
   with no overhang allowed, 45 cells stay bare. In game (slot 2, runs `checks-20261101-044700-s2` now,
   `-045013-s2` void65 only, `-044226-s2` both; sheet `mxl2012-runs/tunnelfloor/review.png`) with both on, HD shows D2R's
   starry void round a Sanct stone platform, legacy is unchanged, walking is unchanged (the same 10 legs to the north bar in
   every build and mode: the bar is reachable on foot), no assert, no crash file. The owner approved row 3 of the sheet; the 15 overhang cells stay (known). Testing,
   including level 74, Hell and a save and reload with the default build: docs/testing.md "Lane tunnelfloor".

**Arches, roofs and trees** (lane walls4, 2026-10-30). Owner rule: no new 3D models; only D2R's own wall, arch and roof
models (any act's tile sets), placed with this pipeline; a cell with no fitting D2R model stays as it is and is listed.

13. **Trees** (`Library.tree_pick`, `TREE`, `TRUNK_BASE`). Orientation 14 holds trees drawn over several cells: one trunk
   tile and crown pieces on the cells next to it. downtown's 126 "uncovered" cells were the crown pieces (14/14/16-17) of
   Harrogath's trees. A trunk tile is one whose lowest opaque pixel is within 50 pixels of its cell's ground (decoded from
   the .dt1 by `tile_pixels`); it gets the tree D2R puts on that tile's cells (Harrogath townwest: `expansion_tree_dead05` /
   `06`), or, for a trunk D2R never puts in a scene (`trees.dt1` 14/15/3), the tree learnt most for another trunk of the
   same tile set. Crown cells get nothing (the trunk's model is the whole tree) and count as *tree cells*, not uncovered.
   A cell with tree tiles only draws its tree and nothing else (D2R's 14/15/3 cells also carried a neighbour's
   `wall_segment_short`, a wall block beside the tree that classic does not have). A tree on fewer than a third of
   the tile's D2R cells is not the tile's (the jungle's tree tiles: 3 of 322), so the jungle maps keep their look.
   downtown: 412 tree cells, 286 trees, 0 uncovered (126 before); macumba gets one Act 1 oak.
14. **Look-alike tiles** (`Library.lookalike`, `compose`, `LOOKALIKE_IOU`). A wall tile D2R never has borrows the variant
   of the learnt tile of the same set and orientation whose silhouette (opaque pixels in 4x4 blocks) overlaps it by at
   least 0.75 (intersection over union). charismatic's Fortress arcade tiles (exterior 1/4/2-4, 1/3/0 and 1/3/11) look
   like D2R's foregate arch tile 1/3/1 (0.80-0.99) and now get its `arch01` with the gargoyle columns, where the generic
   pick gave a plain wall; a cell with a wall and an arcade in two layers draws both. charismatic 177 cells, glados 78,
   cypherpunk 83, borgir 34, moskvich 27, epicwhiners 19, macumba 18, downtown 4, desertpeak 2.
15. **Set pieces by layout** (`Library.learn_pieces`, `fit`, `footprint`, `model_box`). A model D2R uses on fewer than 3
   wall cells is a set piece and is left out (item 4), but some match a Median map by the wall tiles under them. Each set
   piece's footprint is the wall keys under its bounding box (bbMin / bbMax of its LOD-0 model, turned by its yaw); a Median
   map that repeats at least 4 of those cells with 4 distinct keys, and 60% of the footprint, gets the piece at the same
   offset. D2R's Fortress huts are walls and slate roof in one model: `hut_blacksmith01` matches charismatic 5 times and
   `hut_merchant01` twice, the roofed buildings of the classic map. No other map gets one.
16. **Sunk walls** (lane tawalls, 2026-11-06, `Library.lift`, `SUNK_BASE`, `SUNK_TOP`). D2R puts Kurast's dock walls
   (`act3_docktown_walls_lower/wall_*`, `walls_upper/stone_ruin01/02`: the pieces of `ruinwall.dt1` style 4) and its
   `wall_elevation_stone01` at the foot of a terrace; `Ground` measures the terrace top on their cell (highest triangle), so
   they were learnt 4-5 units under the floor with their top at floor level. On Median's flat maps they were drawn inside
   the floor: Tran Athulua (desertpeak, level 60) had 1,016 of its 2,926 pieces sunk and showed floor only in its corridors
   (player report, docs/bugs.md "tawalls"). A wall piece (cap tier 2, not a `DETAIL`) whose y is under -0.5 and whose top
   (model box) ends under 1.0 now stands on the floor (y 0, same tile). Lifted: desertpeak 1,016, excelsior3 22,
   cypherpunk 7, moskvich 1 placed pieces; no generated scene keeps a sunk wall. Details (cliff supports, stairs,
   gargoyles under belial's platform, hanging roots) stay as learnt.
17. **Hollow wall cells** (lane tawalls2, 2026-11-07, `HOLLOW_MAPS`, `Library.fill`, `Library.cover`). Tran Athulua's
   corridors west of the arrival are Median's copy of the Act 3 jungle walls of style 10. D2R draws those in its terrain
   mesh (66 keys, models on 4% of their D2R cells), so the library learns them empty; Median's scenes have no D2R terrain,
   so HD had floor there. Of the 994 empty cells, 496 are tree tiles (orientation 14, no wall) and 556 hold a jungle wall
   tile. Those now get the wall of their orientation that the same map uses most (desertpeak: the Docktown ruin walls;
   a wall end takes its side's wall), with props left out. A cell is skipped when a wall piece of another cell already runs
   5 units through it (model box turned by the yaw), so D2R's long walls are not doubled; cells are filled from the far
   end, because D2R's wall models run back from their cell. Result: 480 cells filled, 76 skipped as spanned, 1,082 more
   pieces (4,008, under the cap). Only desertpeak and only its `act3/jungle` cells: the Act 2 tomb cells at the arrival are
   Tyrael's cliff tiles (the platform edge), where a wall would stand on the floor. The 16 other scenes are byte-equal to
   before. In game (slot 2, `checks-20261107-015409-s2` before, `checks-20261107-014406-s2` after, sheets
   `mxl2012-runs/tawalls2/pairs/`, before HD / after HD / classic): the west wall line at cell 8,30 has its wall pieces
   where it had gaps; at 12,52 one more segment closes the corridor end; the arrival is unchanged. Still not like classic:
   classic's corridors are tall walls overgrown with jungle trees, HD has low Docktown ruin walls and no trees (the tree
   tiles have no D2R tree on most of their cells, `Library.tree_pick`). Checked for the reimref notes on .ds1 decoding:
   desertpeak has no cell with sequence bits 14-15 set and no flags-only dword, so neither explains the empty keys.

**Left as is** (no fitting D2R model, by the owner rule): charismatic's tall pointed arch (foregate 8/3/0-1, 16 cells each;
D2R draws it with `gate01`, whose footprint matches 1 cell only), the long roofed building walls (1/2/6-13, 2/2/7-9) and
D2R's one-piece Fortress roof `ext_roof01` (no layout match), and the 81 cells D2R itself draws without a model. belial's
void (item 12) is not part of this lane.

**Floors** (lane wallsfix, `tools/maps_hd.py`). HD paints a floor tile from the biome's terrain layers through the biome's
tile mask (`data/hd/env/tilemasks/*.json`), keyed by .dt1 path; a tile no mask names gets the base layer. Median's new .dt1
are in no mask, so before this lane every Median floor got its biome's base layer: Kurast's, chosen for cypherpunk by its
Kurast walls, read as grass over the Docktown bridge floor that classic shows as dark stone, and charismatic's Fortress plaza
had the darker base stone instead of the grey marble D2R's mask gives the stock plaza. Two changes:

- the biome is voted by **floor cells first** (`vote_biome`; walls only when no floor names a biome): cypherpunk
  act3_kurast -> act3_docktown (the biome desertpeak already has: the same bridge floor, dark stone in HD), moskvich
  act3_kurast -> act4_mesa (Median's Mesa floor is most of its ground). The other 15 minimal scenes keep their biome.
- **generated floor biomes** (`floor_biomes`): for a biome whose maps use new floor .dt1 with a donor of that biome, the build
  writes `data/hd/env/biome/mxl2012_<biome>.json` (D2R's biome, tile mask renamed) and `data/hd/env/tilemasks/
  mxl2012_<biome>_masks.json` (D2R's mask plus each new .dt1 with its donor's entries). Built: `mxl2012_act4_fort`
  (borgir, macumba, charismatic: zakarum plaza/interior as the Fortress's) and `mxl2012_act4_mesa` (glados, downtown,
  moskvich: redsquare floor as the Mesa's). A donor of another biome keeps the base layer (its mask types name that
  biome's layers). Docktown's bridge has no mask entry in D2R, so cypherpunk and desertpeak use stock act3_docktown.
  D2R's biome and mask come from the D2R extraction or the shared cache (`fxpaths.CACHED_FILES`).

In game (lane wallsfix, slot 3, `wall_maps`, docs/testing.md "Lane wallsfix"): cypherpunk's and moskvich's HD floors are dark
stone now (grass before); charismatic's floor shows no visible change from the generated Fortress mask, so whether D2R's HD
reads a tile mask entry for a mod .dt1 path is **unconfirmed** (the copies are harmless: the same layers and lighting as the
stock biome). If it does not, the way left is per-tile terrain stamps like D2R's own Kurast stone tiles (entities with a
TerrainStampDefinitionComponent), not done here. The run's only assert was the session-long #360 one in classic downtown
(12th area), none with downtown alone. In game (lane walls, slot 3, 2026-10-29,
`wall_maps`): all 8 maps entered in HD and classic in one launch, no assert and no crash file in the last run. One earlier run
had `BC_ASSERT: 0 (AssetCache.h:187)` in classic downtown, the 12th area of the launch; the same route **with the old minimal
scenes (no walls)** had the same assert at the same place, and downtown alone in a fresh launch had none, so it is the
session-long cache filling of bug #360, not the walls.

What the player sees is D2R's stock walls of the donor tile sets in Median's layout, not Median's retextured colours (custom
art, docs/unported.md). The tool reads D2R's scenes from the D2R extraction or the shared cache (`d2r-cache`); a run with
`MXL_SLOT=2..5` fills the cache once from that slot's CASC (read-only; about 290 MB of scene JSON for the 1063 maps).
`py -3 -I tools/walls_hd.py report` writes `work/maps_hd/walls_report.md`; `docs` refreshes the table below.

<!-- walls_hd:begin (generated: py -3 -I tools/walls_hd.py docs) -->

| map | biome | wall cells | exact | partial | look-alike | generic | no D2R model | uncovered | tree cells (trees) | floor cells (with models) | set pieces left out (placed by layout) | placed | capped | models in scene | distinct models | scene size | full height (low / none) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| expansion/dystopic/desertpeak.ds1 | mxl2012_tint_desertpeak | 2171 | 2040 | 115 | 2 | 14 | 589 | 0 | 0 (0) | 13435 (46) | 17 (0) | 3743 | 0 | 3743 | 73 | 3905 KB | 97% (3% / 0%) |
| expansion/ghetto/cypherpunk.ds1 | mxl2012_tint_cypherpunk | 3996 | 2661 | 843 | 5 | 11 | 791 | 0 | 0 (0) | 8563 (546) | 0 (0) | 8620 | 0 | 8620 | 126 | 7812 KB | 100% (0% / 0%) |
| expansion/glados/glados.ds1 | mxl2012_tint_glados | 639 | 450 | 186 | 2 | 0 | 320 | 1 | 0 (0) | 6911 (1322) | 20 (0) | 4215 | 0 | 4215 | 55 | 4055 KB | 100% (0% / 0%) |
| expansion/neonmile/downtown.ds1 | mxl2012_tint_downtown | 1419 | 718 | 218 | 0 | 68 | 340 | 0 | 412 (286) | 32292 (0) | 0 (0) | 1528 | 0 | 1528 | 23 | 2115 KB | 100% (0% / 0%) |
| expansion/redsquare/moskvich.ds1 | mxl2012_tint_moskvich | 202 | 72 | 101 | 26 | 1 | 39 | 2 | 0 (0) | 308 (59) | 14 (0) | 632 | 0 | 632 | 153 | 571 KB | 100% (0% / 0%) |
| expansion/terror/borgir.ds1 | mxl2012_tint_borgir | 733 | 417 | 278 | 34 | 3 | 18 | 1 | 0 (0) | 774 (57) | 1 (0) | 1666 | 0 | 1666 | 96 | 1238 KB | 100% (0% / 0%) |
| expansion/voodoo/macumba.ds1 | mxl2012_tint_macumba | 207 | 198 | 5 | 0 | 1 | 3 | 2 | 1 (1) | 1128 (0) | 14 (0) | 561 | 0 | 561 | 24 | 453 KB | 100% (0% / 0%) |
| expansion/zakarum/charismatic.ds1 | mxl2012_tint_charismatic | 242 | 68 | 73 | 75 | 25 | 54 | 1 | 0 (0) | 1173 (21) | 32 (1) | 1412 | 0 | 1412 | 40 | 1000 KB | 100% (0% / 0%) |
| act3/jungle/dungrm6a.ds1 | act3_jungle | 75 | 74 | 0 | 0 | 0 | 25 | 1 | 0 (0) | 572 (87) | 0 (0) | 786 | 0 | 786 | 86 | 1050 KB | 100% (0% / 0%) |
| act3/temple/temple5.ds1 | act3_kurast | 38 | 8 | 30 | 0 | 0 | 0 | 0 | 0 (0) | 181 (0) | 0 (0) | 347 | 0 | 347 | 29 | 302 KB | 100% (0% / 0%) |
| act3/temple/temple6.ds1 | act3_kurast | 38 | 8 | 30 | 0 | 0 | 0 | 0 | 0 (0) | 181 (0) | 0 (0) | 347 | 0 | 347 | 29 | 302 KB | 100% (0% / 0%) |
| act1/caves/caveroom4.ds1 | act1_caves | 3 | 2 | 0 | 0 | 0 | 0 | 1 | 0 (0) | 84 (17) | 0 (0) | 20 | 0 | 20 | 15 | 17 KB | |
| act3/kurast/excelsior3.ds1 | act3_kurast | 884 | 798 | 13 | 0 | 0 | 333 | 73 | 0 (0) | 1709 (112) | 5 (2) | 1621 | 0 | 1621 | 111 | 1235 KB | 100% (0% / 0%) |
| act2/arcane/belial.ds1 | act2_arcane | 75 | 70 | 2 | 0 | 0 | 0 | 3 | 0 (0) | 96 (96) | 0 (0) | 673 | 0 | 673 | 18 | 563 KB | 100% (0% / 0%) |
| expansion/morework/epicwhiners.ds1 | act1_caves | 315 | 86 | 16 | 4 | 208 | 18 | 1 | 0 (0) | 4412 (189) | 58 (0) | 1384 | 0 | 1384 | 47 | 1214 KB | 99% (0% / 1%) |
| act1/cathedrl/inarius.ds1 | act1_cathedral | 6 | 6 | 0 | 0 | 0 | 4 | 0 | 0 (0) | 145 (0) | 1 (0) | 124 | 0 | 124 | 10 | 118 KB | 100% (0% / 0%) |
| expansion/icecave/rockisdead.ds1 | expansion_icecave | 23 | 23 | 0 | 0 | 0 | 1 | 0 | 0 (0) | 3556 (481) | 0 (0) | 531 | 0 | 531 | 33 | 751 KB | 100% (0% / 0%) |
| all | | 11066 | 7699 | 1910 | 148 | 331 | 2535 | 86 | 413 (287) | 75520 (3033) | 162 (3) | 28210 | 0 | 28210 | | 26700 KB | |

Learnt from 1490 D2R maps (485135 wall and floor cells, 10493 distinct cell keys, 44288 variants). *exact*: the cell's wall tiles were seen together in a D2R map; *partial*: the variant of a learnt key that shares a tile; *generic*: a wall tile D2R never has in a scene gets D2R's most common wall of the same orientation in the same tile set or act (Library.generic_pick); *look-alike*: a wall tile D2R never has borrows the variant of the learnt tile of its set and orientation that has the same silhouette (Library.lookalike); *no D2R model*: D2R draws that tile without an entity (part of a map's baked terrain or nothing); *uncovered*: no wall drawn in HD (not a wall orientation, or no learnt wall of that orientation); *tree cells*: cells with only tree pieces (orientation 14), in brackets the trees placed on trunk tiles (Library.tree_pick); *floor cells*: cells with a floor and no wall, in brackets those that get the models D2R puts on that floor tile (cave walls, ledges, stairs, trims; floor_cells); *set pieces*: models D2R places on fewer than 3 wall cells (Library.set_piece), in brackets those placed where the map repeats the wall tiles under them (Library.fit); *capped*: pieces cap() dropped to stay within D2R's largest scene (docktown3: 4423 placed models, 4.44 MB); *full height*: the wall cells whose models (within one cell or under their footprint) reach 0.028 HD units per pixel of the classic wall tile, half of what D2R's own maps give (wall_heights; *low*: models under that, *none*: no model; D2R's own maps: 76-81% at full height, the build fails a map under 70% that HEIGHT_KNOWN_LOW does not list).

Self-check (D2R's own maps, `self_check`): the scenes this method makes for 40 of the learnt D2R maps have 3477 of their 6363 wall entities (55%; same model within 1.5 units).

<!-- walls_hd:end -->

### Status per map (lane hdwalls2, 2026-10-30, slot 1, check `wall_maps`)

Every map entered by harness travel in HD and then in classic in one launch per group, three shots each; HD judged against
legacy graphics (G) by eye. Runs `checks-20261030-005953-s1` (the 9 maps on stock tiles) and `checks-20261030-010654-s1`
(the 8 retextured maps, again after this lane's changes): all 16 levels reached in both modes, **no engine assert and no
crash file in either run**, VariantTransformTable peak 107 and 105 of 128 (bug #360). Walkability: the scenes are drawing only
(no physics bodies, no tile or .ds1 change), so collision is the classic map's. Order: most visited first.

| map | level | HD walls | seen in game (HD against classic) |
|---|---|---|---|
| act3/jungle/dungrm6a | 90 Flayer Dungeon 3 | yes | stone walls, arches and the iron gate follow the classic layout |
| act3/temple/temple5, temple6 | 96 Forgotten Reliquary (one of the two, identical in Median) | yes | temple walls and pillars as in classic; the HD floor is the Kurast biome's grass where classic has temple stone (biome, not walls) |
| act1/caves/caveroom4 | 15 Hole Level 2 | yes (walls3) | cave rock walls where classic has walls, and the stairs at the arrival as in classic (lane walls3: D2R's `back_stairs01`, item 11). The room is small: 3 wall cells, 84 floor cells, 20 pieces |
| act3/kurast/excelsior3 | 84 Spider Cave | yes | Kurast walls, stairs and the courtyard as in classic; 68 wall cells stay without (43 tiles no file of the level type has, 25 Kurast corner halves) |
| act2/arcane/belial | 65 Ancient Tunnels | yes | trims, arches and gargoyles round the platform; since 0.1.9 (lane tunnelfloor, item 12) the platform floats over D2R's starry void on D2R's Sanct walkways (15 cells of walkway over the void by the north bar). Before: the void was drawn as floor in HD, and classic's arches under the platform edge stayed hidden under it (lane walls3: 22 edge pieces are placed there now; lane tunnels: a terrain mesh over the platform, indexed in model_lod_desc.bin, did not change the floor either, so it is not the scene's; closed as a known issue, item 12; lane tunnels65: the level already is a preset level, and the terrain named as D2R names its own did not change it either) |
| expansion/morework/epicwhiners | 13 Cave Level 2 | yes | cave walls, stalagmites and rock mounds roughly where classic has them |
| act1/cathedrl/inarius | 14 Underground Passage Level 2 | yes | cathedral walls, arches and windows as in classic |
| expansion/icecave/rockisdead | 116 Drifter Cavern | yes | ice cave walls and ledges where classic has walls (classic is Median's brown cave colour) |
| the 8 retextured maps | 60, 59, 95, 18, 98, 126, 125, 127 | yes | as in lanes walls / wallsfix; glados and cypherpunk now also show Kurast stairs and Travincal trench pieces on floor tiles; charismatic (lane walls3, items 9-10): the Fortress walls, gargoyle pillars and columns now stand along classic's walls (before they floated 3-4 tiles off) and 81 wall cells are left without a model (was 366); lane walls4 (items 13-15): charismatic's arcades have D2R's arches and gargoyle columns and its 7 roofed buildings D2R's Fortress huts; the tall pointed arch and the long roofed walls stay without; downtown has Harrogath's dead trees where classic has trees |

Known-issue count in the alpha release notes: 17 maps without walls in HD before, 0 now; 2 showed only part of them (belial:
the void drawn as floor, fixed in 0.1.9 by lane tunnelfloor; charismatic: arches and hut roofs since lane walls4, but not
the tall pointed arch and the long roofed walls) and all 17 show D2R's stock walls, not Median's colours. Lane
walls3 (2026-10-30, slot 2, runs `checks-20261030-120504-s2` and `checks-20261030-121747-s2`, docs/testing.md "Lane walls3")
re-checked caveroom4, belial, charismatic, glados and downtown in HD and classic. Lane walls4 (slot 3, run
`checks-20261030-175423-s3`, docs/testing.md "Lane walls4") re-checked charismatic, downtown and macumba.

## HD wall scan 2026-11-06 (lane wallscan)

Owner request after lane tawalls (item 16): look at the other 16 Median maps for HD wall problems. Static pass: the scenes of
main's `walls_hd.py` (with `Library.lift`) per cell category, the cap, and wall pieces left far over the floor
(scripts and output in `mxl2012-runs/wallscan/static/`). In game: slot 2, check `wall_maps` with `MXL_WALL_SPOTS` (the map
cells of the static pass; the harness hops there), the slot's 17:40 install with main's lifted scenes of desertpeak,
cypherpunk, moskvich and excelsior3 copied over for the run and restored byte-equal after. Run
`checks-20261106-224456-s2`, all 9 levels reached in both modes, no assert in the visits. Shots
`mxl2012-runs/wallscan/shots2/`, HD left / classic right in `mxl2012-runs/wallscan/pairs/wall_<map>_pair_<n>.jpg`
(0 = arrival, 1-2 = the spots).

All 17 maps have their scene in the install. dungrm6a, temple5, temple6 and caveroom4 are not missing: since lane hole2
they sit at `hd/env/preset/mxl2012/<path>.json` (ds1_paths). The other 17 .ds1 of the mod use D2R's own scene.

| map / area | problem | seen | severity | suggested fix |
|-|-|-|-|-|
| desertpeak (60 Tran Athulua), corridors west of the arrival (cell 12,52) | 994 wall cells take a D2R variant with no model (D2R draws them in its terrain); HD shows open floor and short ruin stubs where classic has a closed corridor | yes, `wall_desertpeak_pair_1` | high | done (lane tawalls2, item 17): the map's own wall of the cell's orientation on its jungle wall cells, not where a neighbour's wall spans the cell |
| desertpeak, arrival | the short back wall takes the tomb pillars (tawalls note); a low ruin wall stands on the floor south of the player where classic has the platform edge | yes, `pair_0` | low | left (lane tawalls2): classic also has tall carved pillars behind the braziers, HD's tomb pillars stand there without the wall between them; the platform edge needs a terrain step (item 12), a wall is the nearest D2R piece |
| cypherpunk (59 Fauztinville) | cap: 11,083 pieces placed, 6,660 dropped: all 363 props and 6,297 of 7,142 details (stairs, buttresses, gargoyles, caps) | arrival: HD flat floor with slab walls where classic has a wide stair (`pair_0`); spots: walls roughly as classic (`pair_1`, `pair_2`) | medium | keep `stair`/`step` pieces in the walls tier of `cap()`, or a per-map cap once bug #360's cache limit is measured |
| cypherpunk, excelsior3 | `wall_elevation_stone01` learnt at y 3 (cypherpunk 884, excelsior3 54, plus 38 at 5-10): retaining walls of D2R's terraces stand as free walls on the flat floor | excelsior3 arrival: classic's sunken courtyard with stairs is a flat yard fenced by slabs in HD (`wall_excelsior3_pair_0`) | medium | the mirror of item 16 (pieces above a terrace); a terrain mesh is not possible (item 12), so at most drop the raised ones or stand them at y 0 |

| desertpeak (60 Tran Athulua), corridors west of the arrival (cell 12,52) | 994 wall cells take a D2R variant with no model (D2R draws them in its terrain); HD shows open floor and short ruin stubs where classic has a closed corridor | yes, `wall_desertpeak_pair_1` | high | for wall cells whose learnt variant is empty, place `generic_pick` (needs a check that it does not double D2R's own terrain walls on the stock maps) |
| desertpeak, arrival | the short back wall takes the tomb pillars (tawalls note); a low ruin wall stands on the floor south of the player where classic has the platform edge | yes, `pair_0` | low | prefer the variant of the cell's main tile set on mixed cells |
| cypherpunk (59 Fauztinville) | cap: 11,083 pieces placed, 6,660 dropped: all 363 props and 6,297 of 7,142 details (stairs, buttresses, gargoyles, caps) | arrival: HD flat floor with slab walls where classic has a wide stair (`pair_0`); spots: walls roughly as classic (`pair_1`, `pair_2`) | medium | stairs kept since lane elevwalls (cap tier 3, all 1,406); the arrival stair: done (lane stairs, [below](#stairs-at-fauztinville-lane-stairs-2026-11-07)) |
| cypherpunk, excelsior3 | `wall_elevation_stone01` learnt at y 3 (cypherpunk 884, excelsior3 54, plus 38 at 5-10): retaining walls of D2R's terraces stand as free walls on the flat floor | excelsior3 arrival: classic's sunken courtyard with stairs is a flat yard fenced by slabs in HD (`wall_excelsior3_pair_0`) | medium | done (lane elevwalls): walls facing away from the camera left out, facing ones moved onto the floor ([below](#retaining-walls-and-stairs-lane-elevwalls-2026-11-07)) |
| downtown (18), arrival and Harrogath walls | 422 generic cells: low crenellated `wall_segment_short` (288) where classic has a tall skull wall; shelf-like pieces stand where classic has a stone arch; 71 wrought-iron fences learnt at y 9 | yes, `pair_0`, `pair_2` | medium (look only, layout right) | needs art or a taller D2R wall as the generic pick for style 3; fences: drop or stand at y 0 |
| glados (95) | 42 generic and 78 look-alike cells: walls and gargoyle pillars match; classic's big trees are missing in HD | yes, `pair_1`, `pair_2` | low | trees: object or tile layer not in the scene (not walls) |
| Khalimgrad (`charismatic`, 127) | 177 look-alike, 54 generic | walls, arches, huts follow classic (`pair_1`, `pair_2`) | low (known: item 10, tall pointed arch) | none |
| excelsior3 (84), cell 36,12 | 68 uncovered cells (known, 43 tiles without a file of the level type, 25 corner halves) | ruins as classic (`pair_2`) | low | none |
| The Proving Grounds (`dungrm6a`, 90) | 209 cells with no D2R model | walls and arches follow the classic layout, a few near-side walls thinner (`pair_1`) | low | none |
| epicwhiners (13) | 423 no-model cells, 546 set pieces left out | arrival as classic (`pair_0`); the hop stopped short of both spots | low | look again by walking |
| rockisdead (116) | 153 ledge corners at y 8 | HD dark where classic shows the lower ledges (`pair_1`); not conclusive | low | none now |
| moskvich, borgir, macumba, inarius, belial, temple5/6, caveroom4 | nothing beyond the known items in the static pass (a few ornate walls at y 12-17 in moskvich and borgir: upper floors) | not visited (tawalls and hdwalls2 shots) | OK | none |

The `downtown` origin (10000, 5000) is given in `MXL_WALL_SPOTS` because `presets rooms` lists 400 rooms at most.

### downtown (the Crypt, level 18): hand picks (lane downtownhd, 2026-11-07)

The wall scan's downtown row, read again from the tiles (Median's neonmile files are Harrogath's with the same keys and
shapes, other colours): the tall skull wall of classic is Harrogath's `walls.dt1` style 1 (416 px tiles), which D2R itself
draws with `wall_segment_short` and `wall_crenelation` (exact cells; kept). What did not match was the generic pick for the
tiles D2R never draws: `walls2.dt1` style 3 is a **low** rock barricade (124 px tiles) and got the tall town wall (orientation
1-3) or an iron fence learnt at y 9 on Harrogath's terraces (5/3/0, 61 cells; 5/1/0, the tall wall's end, 6 more); the keep
wall (`keepwall.dt1` 2/16) a bookshelf and fence set; the free-standing crypt arch at the arrival (crypt corner 7/0/0 at both
ends, the passage tiles 10/1/0-1 between, cells 6,11-13) the crypt corner's pillar and a wall turned across the arch.

`walls_hd.STAND_INS` (per map; only downtown has one, other maps' scenes are unchanged) gives those tiles fixed pieces:
style 3 the low ruin wall and rubble of D2R's Harrogath ruins (`expansion/ruins` 1/22/2, 6/22/2, 3/22/2, 1/22/23: wall_low02,
rubble_wall01), 5/1 the tall wall, 2/16 the tall wall along x, crypt 7/0 the end pillar only and 10/1/0 the crypt's doorway
arch (`doorway01`, turned 90 degrees as on D2R's left-wall door cells). 267 cells take a stand-in; generic cells 422 -> 162
(the building walls 2/14 and the main gate 8/3 stay generic). Generic picks now stand a wall piece learnt over 3 units
(`FLOAT_Y`) on the floor (`Library._ground`): a tile D2R never draws has no terrace to measure, and that left the fences at y 9.
Tests `tools/tests/test_walls_hd.py` `StandInTest`. Evidence `mxl2012-runs/downtownhd/` (tile renders `tiles/`, `sheet*.png`,
static scripts and the scene in `static/`, in-game pairs in `pairs/`).

### Retaining walls and stairs (lane elevwalls, 2026-11-07)

Fixes for the cypherpunk and excelsior3 rows above, in `walls_hd.py` (`Library.seat`, `facing`, `tier`; tests
`SeatTest`, `CapTest`):

- **Retaining walls.** D2R's terrace walls (`wall_elevation_*` with their `wall_stone_buttress_*` pieces) have one face, on
  the low side of the step (local +x, corners also +z; measured on D2R's Kurast scenes: the terrain is 4.9 lower on that
  side), and their body sits inside the upper terrace. In D2R's own maps the four turns are equally common. D2R's camera
  looks along (-1, -1, -1), so a face turned away from it (normal nx + nz <= 0) is hidden by the terrace in D2R and classic
  draws only the terrace edge there. On Median's flat floor (no terrain, item 12) these stood as free walls showing their
  backs: cypherpunk's walkways had 2,780 of them (of 2,800 elevation walls), excelsior3's courtyard 212. `seat` leaves them
  out. A facing one learnt over the floor (the ground measured on a sloped triangle at the terrace edge: 918 at y 3.27 in
  cypherpunk) is moved along the view axis to y 0: same place on screen, standing on the floor. Retaining pieces learnt
  under the floor (under `SUNK_BASE`) stay `lift()`'s.
- **Stairs** are the last cap tier (3), so cypherpunk keeps all its 1,406 stair pieces (before: 169;
  the arrival's wide stair was gone). Stairs learnt under the floor (y < `SUNK_BASE`: glados' 312
  Kurast stairs at -1.3, excelsior3's sewer stair at -7.7) are moved up the view axis to y 0; D2R's cave stairs at y 0 that
  reach under the floor by design are not touched.
- **Props**: cypherpunk now places 5,611 pieces (was 11,083); the cap still drops 1,188: all props and part of the
  details. The budget does not allow props there; raising it needs a game test of a larger scene first.

- **Cypherpunk's arrival stair is not fixed** here. (Lane stairs: the stair is not sequences 12-15, which are kerbed
  flagstone walkway floor; it is sequences 23 and 26, fixed [below](#stairs-at-fauztinville-lane-stairs-2026-11-07).)

In game (slot 2, run `checks-20261107-022822-s2`, this lane's scenes of excelsior3, cypherpunk, desertpeak, glados and
moskvich copied over the slot's for the run and restored byte-equal after; all 5 levels reached in both modes, 0 asserts,
no crash file): cypherpunk's walkways show their near faces and no slabs on the far side, as classic (`pair_1`;
wallscan's had slabs on both sides); the arrival's slabs are gone, the stair is still floor (`pair_0`). excelsior3's
courtyard: the front slabs are gone, the back walls (faces toward the camera), torches and stairs stay where classic has
them; the floor stays flat (`pair_0`). desertpeak, glados and moskvich: nothing missing or floating at the spots.
Evidence `mxl2012-runs/elevwalls/` (`pairs/`, `shots/`, `run1.log`, scripts).

Scene changes against main (all 17 rebuilt): cypherpunk (2,681 elevation walls out, stairs and details in), excelsior3
(-382 pieces), desertpeak (-36: 15 away-facing elevation walls with their buttresses, Kurast donor pieces on its corridors),
moskvich (-28), borgir (-22), macumba (-6), glados (-3, 373 stairs moved up); the other 10 maps unchanged (caveroom4's and
epicwhiners' stairs included).

### Stairs at Fauztinville (lane stairs, 2026-11-07)

Cypherpunk's (59 Fauztinville) wide stairs, at the arrival and at every walkway crossing, were flat floor in HD.

- **Which tiles.** A colour render of Median's `expansion/dystopic/terraces.dt1` (a retexture of D2R's
  `act3/kurast/terraces.dt1`, style 31, all 28 sequences; sheet `mxl2012-runs/stairs/tiles_all31.png`) shows that
  sequences 12-15 (1,838 cells) are flagstone floor with a kerb on one edge, the walkways themselves: bare floor is right
  for them. The steps are sequences 7, 10, 23 and 26 (6, 11, 22 and 27 are steps with a terrace edge): cypherpunk has 476
  such cells (23: 186, 26: 272, 10: 12, 6: 3, 7: 3), 2 by 3 cells at the ends of each walkway and 5 by 2 or 3 across each
  corridor. D2R draws these with its terrain mesh and puts `act3_kurast_stairs/stairs_a01` (and b01, b02) on a third of
  their cells at most, so `choose()` learnt them bare (23) or with a trim (26).
- **Fix** (`KURAST_STAIR`, `KURAST_STAIR_TILES`, `KURAST_STAIRS`, a `STAND_INS` table for cypherpunk; a stand-in piece
  may now carry a scale). Every such cell gets one `stairs_a01`, turned as D2R turns it on these tiles (yaw 270 on 6/7/22/23,
  0 on 10/11/26/27), stretched to span the cell (x 2.4, z 1.39: the piece is 4 deep and 7.2 long) and flattened to 1.8
  units (y 0.35). D2R's own layout (2 by 2 pieces per cell, each a 5-unit flight up a terrace) would add about 1,900 pieces
  and stand as rows of blocks on Median's flat floor; two pieces per cell at full height looked like a saw in game (run
  `checks-20261107-150324-s2`); one flat flight per cell reads like classic's stair (`pairs/stairs_cypherpunk_pair_0`).
  The flights stop at each cell's edge, so a 2 by 3 stair shows six small flights, not one.
- **Budget** (`MAP_LIMITS`). With the stairs cypherpunk places 5,779 pieces (5.05 MB, 99 models); under the common cap
  1,356 of them (all props and details) would go, against 1,188 before. Measured in game, slot 2, `wall_maps` of level
  59 at the arrival and two busy spots (cells 70,49 and 38,57), HD and classic, each scene swapped into the slot for the
  run and restored byte-equal: a 6,255-piece scene (5,417,732 bytes, two pieces per cell) and the 5,779-piece one both
  loaded with no assert while in the map (only the usual pool asserts at game exit) and no crash file; load screen
  2.65-3.1 s against 2.6-3.0 s; private memory 9.70-9.83 GB against 9.54-9.77 GB with main's scene; frame rate at arrival / spot 1 / spot 2
  59.9 / 59.9 / 53.7 against 60.0 / 59.9 / 58.8 (spot 2 has monster packs fighting; one run of each was slower while
  another game ran on the GPU). cypherpunk's budget is therefore that tested scene, 6,255 pieces and 5,417,732 bytes; the
  other 16 maps keep the common cap. D2R's largest scene has 679 distinct models, cypherpunk 99.
- The other 16 scenes are byte-equal to main's (full builds of both). Not done: the walkways' kerb edges (sequences
  12-15) have no model; the stairs' rise is drawn, not walked (the floor stays flat). Testing: docs/testing.md
  "Lane stairs".

### Wall heights against legacy (lane duncraig, bug #561, 2026-11-08)

A scene can place models on every wall cell and still read as bare floor next to legacy. Tran Athulua's Kurast ruin walls
became knee-high ruins (D2R uses those tiles at the foot of its dock terraces, models 4.6-7.8 units tall). Duncraig's
Monastery facade (level 13, `expansion/morework/epicwhiners`) got only ivy and low wall bits: D2R builds the facade from
4-tile models (`act1/monastry/facade1`), which stand on 1 cell of the 4 they cover, so `choose` learns those keys as empty.
`walls_hd.wall_heights` measures it per wall cell: the top of the models within one cell against the classic wall tile's
pixel height. **Full height** is at least `HEIGHT_PER_PX` = 0.028 HD units per pixel, half of what D2R's own maps give
(docktown3 0.048, cathy3 0.066). On D2R's own maps 76-81% of the wall cells reach it. The column "full height (low / none)"
of the generated table below shows it per map. `report`, `build` and `docs` exit 1 when a map is under `HEIGHT_MIN_OK` (70%)
and not in `HEIGHT_KNOWN_LOW`. Known low: epicwhiners (39%, 27% with no model) and desertpeak (43%). Lowest of the others:
excelsior3 (76%, 22% with no model) and dungrm6a (77%). The release ships these scenes byte for byte (0.1.16 package
checked), so what players see is the generator's result, not a packaging fault. Why the lanes judged TA "fixed": the
`wall_maps` shots were judged by position ("walls where classic has them"), not by height. Full analysis and options:
`mxl2012-runs/duncraig/HD-PIPELINE-FINDINGS.md`.

### Walls composed from the classic layout (lane hdscene, 2026-11-09)

`tools/walls_scene.py` (tests `tools/tests/test_walls_scene.py`), called by `walls_hd.build` for every map not in `SCENE_OFF`.
Instead of one guess per cell, it rebuilds the classic map's wall structures with D2R's own multi-tile pieces:

1. **Classic structures.** `find_runs`: wall runs along a cell edge (orientations 2/3/6/9 on the cell's top edge along x,
   1/4/5/8 on its left edge along z), split at gaps and where the tile set changes; `find_posts`: the posts (orientation 7).
2. **D2R's kit, learnt from D2R's scenes over D2R's own tiles** (`Kit`, fed by `Library.learn` for all 1490 D2R maps): the
   models standing on a run are grouped by pivot and yaw into a *piece* (footprint, length in tiles, height, pivot across
   the run, details riding on top such as spikes), recorded once per tile set together with the tile sequences it stands on
   (`slots`). Left walls use the piece mirrored across the x = z diagonal. Posts within 3 units of a piece end are the
   tile set's *joint*.
3. **Composition** (`compose`): each run is cut into *opening* spans (tiles D2R draws with a gate, door, entrance or arch
   piece: one piece per classic opening, at the same place, its length fitted to the classic span within 0.8-1.25) and
   *plain* spans (the tile set's most used non-opening piece, end to end with no gap, height scaled by the classic tile's
   pixel height against the tiles the piece was learnt on, 0.6-1.6). A joint goes on every piece boundary. A span whose
   piece stays under full height (`FULL_PER_PX` = 0.028 units per classic pixel; D2R's footings and trims) is left to the
   per-tile walls, so is every cell the kit has nothing for. A cell whose wall tiles were composed gets nothing more from the
   per-tile pick when only floor or post tiles are left in it (the run's joints stand there): no floor rubble and no post
   stones under a composed wall.
4. **Floors.** `biome_overrides` writes D2R's `perTileBiomeOverrides` for floor cells whose tile set has another D2R biome
   than the scene's (byte budget kept), for the `OVERRIDE_BIOMES` (2) biomes with the most cells only: with 3 or 4 override
   biomes Fauztinville's arrival asserts `visibleTileBiomes.size() < BiomeVisibleCountMax` (terrain.cpp:664; lane hdscene2).

The height gate (`wall_heights`) now also counts the cells under a model's footprint (up to `FOOT_MAX` = 12 cells each way),
not only the cells around its pivot: a 4-tile wall stands on 1 cell of the 4 it covers.

Result (build of 2026-11-09; kit: 150 pieces in 35 tile sets, learnt from the 1490 D2R maps). Wall cells at full height,
release 0.1.16 -> now, both counted with footprints: Duncraig (epicwhiners) 53% -> 99% (1,213 of its 1,223 wall cells
composed; its gate run at y 34 gets two `gateway01` arches at x 55-59 and 60-64, each fitted to the classic 5-tile span,
then `wall01` to x 72, and `basic_wall01` down the side walls at x 55 and x 73), downtown 82% -> 100%, inarius 83% -> 100%,
charismatic 96% -> 100%, desertpeak 43% -> 47% (Tran Athulua's ruins, known low), the others equal or higher.
Composed / left per tile:

- Composed in full or mostly: epicwhiners, downtown, dungrm6a, inarius, rockisdead, belial (4 cells), macumba, charismatic,
  glados (210 cells; 274 left per tile).
- Mostly per tile, because the kit's pieces for the tile set are footings or trims under full height: excelsior3, temple5,
  temple6, borgir, moskvich, desertpeak (Kurast and docktown tile sets).
- Per tile by `SCENE_OFF`: none since lane hdscene2 (Fauztinville (`cypherpunk`) was, at its model cap: the added pieces
  pushed per-tile walls out, 61% vs 79%; it is now composed within its own budget,
  [below](#sprite-walls-in-the-gaps-lane-hdscene2-2026-11-09)).
- Nothing to compose: caveroom4 (its cave walls are floor tiles).

The 8 retextured maps (lane maptint) take the kit of the D2R tile set their tiles stand in for: Duncraig the Monastery facade
(`act1/monastry`), downtown and the Kurast-set maps D2R's own pieces of those sets, tinted by the map's biome. Where a span
kept low per-tile walls (above), lane hdscene2 draws Median's own wall art instead
([below](#sprite-walls-in-the-gaps-lane-hdscene2-2026-11-09)). The 17 scenes are 0.15 MB smaller in the download than release 0.1.16 (deflated 1.01 -> 0.86 MB; raw
23.2 -> 27.2 MB, mostly `perTileBiomeOverrides`), no new models or textures.

### Sprite walls in the gaps (lane hdscene2, 2026-11-09)

Where D2R's kit has no full-height piece for a tile set (Kurast and docktown runs: their D2R pieces are footings and trims),
`walls_scene.compose` leaves the span to the per-tile pick, and that pick stays low too. Those cells now get Median's own wall
tiles as cut-out models (`tools/walls_sprite.py`, `MapSprites`; `walls_hd.SpriteFill`, `build_scene` `sprites`; tests
`tools/tests/test_walls_sprite.py`, `test_walls_hd.py`):

- **Which cells.** A gap cell (`compose` `gaps`) whose per-tile pick does not reach full height (`HEIGHT_PER_PX` of the cell's
  classic tile, `SpriteFill.tall`) draws its wall layers as sprites instead of the pick. A cell whose pick reaches full height
  keeps D2R's pieces. `SPRITE_OFF` lists maps that keep the pick everywhere (none).
- **One model per classic tile** a map uses (orientation, main index, sub index): a vertical curtain over the cell's back
  edges with the tile's sprite (the prototype of lane hdwallart), file names `wallsprite/<map>/wall_<o>_<s>_<q>.model` (tier 2
  in `cap()`, a wall). Each map has one atlas at the classic size (BC3, 5 mips; the art has no more detail), and all maps share
  one flat normal map and one ORM map (64 x 64, 5 mips). The models take the vertex and index counts of the prototype's
  donor (`wood_burning06`, `DONOR`), padded, since `model_lod_desc.bin` stores the donor's.
- **Joins.** A sprite cell meets the neighbouring D2R piece edge to edge, with a post of the tile set at the join and the
  atlas toned toward its D2R neighbours (see "Joints and colour at sprite joins" below). Light: the flat normal map, so the
  walls are lit like the floor (as lane hdwallart's second run).
- **The Proving Grounds' arch** (`dungrm6a`, `ARCH_TILES`): the classic arch and its wall at x 1-4 draw as sprites whatever the pick (D2R had ruin
  walls there). **Khalimgrad's steps** (`charismatic`, `STEP_TILES`): the 12 step tiles of the Fortress floor draw as floor sprites (flat
  quads `FLOOR_LIFT` above the floor, `step_<o>_<s>_<q>.model`, tier 3) over their 250 cells, so the stairs read as steps.

Two things learnt in game (slot 1): a 25-vertex donor (docktown `thatch03`) gives "Failed to create index buffer" for every
model made from it, and 16 x 16 normal / ORM maps with one level lose the GPU device ("Present failed", 0x887A0005) as soon
as a map that draws them loads; with the prototype's donor and 64 x 64 maps with mips, level 60 loads with no assert.

Wall cells at full height (footprint count), lane hdscene's build -> this lane:

| Map | Before | After | Sprite walls (models) |
|-|-|-|-|
| Tran Athulua (`desertpeak`, 60) | 48% (2,776 capped) | 97% (0 capped) | 1,143 (24) |
| Fauztinville (`cypherpunk`, 59) | 79% (per tile, `SCENE_OFF`) | 100% (composed, 8,620 placed, 0 capped) | 1,897 (31) |
| Kurast 3000 BA (`excelsior3`, 84) | 77% | 100% | 184 (14) |
| Old Bremmtown (`borgir`, 126) | 82% | 100% | 699 (47) |
| Rathma Square (`moskvich`, 98) | 89% | 100% | 137 (57) |
| The Proving Grounds (`dungrm6a`, 90) | 100% (227 capped) | 100% (0 capped; 1,050 KB, was 4,539 KB) | 56 arch (14) |
| Khalimgrad (`charismatic`, 127) | 100% | 100% | 26 walls, 250 floor steps |
| Azmodan's Reliquary (`temple5`, `temple6`, 96) | 100% | 100% | 0 |

Five more maps get a few sprite walls in their gap cells (Dimensional Sanctum (`belial`), Ureh (`downtown`), Duncraig (`epicwhiners`), Vizjun
(`glados`), Toraja (`macumba`): 1 to 6 models each); the other maps are unchanged. Download: the sprite models add 6.4 MB deflated (1,115 files, 223 models x 5 LODs, 47 MB raw:
the donor's counts are padding), the 12 atlases and 2 flat maps 2.1 MB (19 MB raw), the 17 scenes 0.2 MB (deflated 0.86 ->
1.05 MB); about 8.7 MB together.

### Joints and colour at sprite joins (lane walljoins, 2026-11-09)

Where a sprite wall meets a D2R wall piece, `build_scene` now puts a post at the join, and each map's sprite atlas is toned
toward the D2R pieces round it (`tools/walls_scene.py` `join_points`, `Kit.join_fit`, `place_joins`; `tools/walls_hd.py`
`budget_joins`, `sprite_neighbours`; `tools/walls_sprite.py` `match_colour`, `albedo_stats`; tests
`tools/tests/test_walls_joins.py`):

- **Join points.** A grid point that ends both a sprite wall edge and a D2R wall edge (in line or at a corner). The joint's
  height is the sprite wall's top there.
- **Which joint.** The joints the kit learnt for the tile set (posts near piece ends in D2R's own maps), the D2R side's tile
  set first, the most used first. A joint is used only when it is a post (`JOIN_FOOT`, footprint at most 7 units each way:
  no ruin corners, fences or wall slabs) and its height scales to the sprite top within `JOIN_SCALE` (0.6 to 2). When the
  tile set has none, the post of another tile set of the same act that needs the least scaling ("similar"). Else the join
  is left as it was and listed (`joins_left_at`). A point that already has a joint from `compose` is skipped (`joins_taken`).
- **Budget.** Joints are tier 2 but only take the room left under `cap()` / `MAP_LIMITS` after the map's own entities;
  over it, whole joints are kept spread over the map (`budget_joins`). Entities `mxj_<i>_<k>`, ids from `JOIN_ID_BASE`.
- **Colour.** The albedo (`_ALB.texture`, a small mip) of each D2R wall piece within one cell of a sprite wall is pooled per
  map, weighted by count; the atlas's opaque pixels move per channel toward that mean and spread (`match_colour`: spread
  ratio clamped to `SPREAD_RANGE` 0.5 to 2, applied `COLOUR_STRENGTH` 0.75 of the way). Maps with fewer than `COLOUR_MIN`
  (10) neighbouring pieces keep Median's colours. Deterministic, at build time; `d2r_texture` decodes BC1 / BC3 / BC7.

Per map (all 17 rebuilt, height gate clear, `validate` exit 0):

| Map | Joints placed | Own / similar | Left | Colour target (RGB) |
|-|-|-|-|-|
| Tran Athulua (`desertpeak`, 60) | 197 | 186 / 11 | 5: (8,26) (8,81) (9,17) (9,26) (9,31) | 93 / 91 / 58 |
| Old Bremmtown (`borgir`, 126) | 195 | 195 / 0 | 0 | 101 / 96 / 83 |
| Rathma Square (`moskvich`, 98) | 40 | 40 / 0 | 0 | 94 / 88 / 78 |
| Kurast 3000 BA (`excelsior3`, 84) | 33 | 33 / 0 | 0 | 104 / 97 / 83 |
| The Proving Grounds (`dungrm6a`, 90) | 23 | 10 / 13 | 0 | 93 / 95 / 47 |
| Toraja (`macumba`) | 23 | 23 / 0 | 0 | 106 / 97 / 88 |
| Khalimgrad (`charismatic`, 127) | 11 | 11 / 0 | 3: (7,19) (7,20) (8,45) | 78 / 73 / 70 |
| Vizjun (`glados`) | 3 | 3 / 0 | 0 | none (too few pieces) |
| Dimensional Sanctum (`belial`) | 2 | 0 / 2 | 0 | none |
| Duncraig (`epicwhiners`) | 1 | 0 / 1 | 0 | 95 / 85 / 74 |
| Fauztinville (`cypherpunk`, 59) | 0 (329 over budget) | 329 / 0 | 0 | 98 / 95 / 65 |

Joint counts are per join point (a joint can have several members). The posts used: Kurast's `vine_pillar02`, Travincal's
round pillars and Kurast's `pillar_corner01` / `pillar_thin02` at Tran Athulua; Kurast's `wall_stone_buttress01` and
`pillar01` at Kurast 3000 BA and Old Bremmtown. Fauztinville is at its entity limit (8,620 placed), so its joins stay edge
to edge; the left points at Tran Athulua and Khalimgrad have no post in reach of their sprite height.
Before/after HD sheets with legacy: `mxl2012-runs/walljoins/sheets/` (outside the repo).

### Model cache (lane hdscene2, 2026-11-09)

D2R keeps every HD model it has loaded in the render asset manager's ModelAsset cache (capacity 2,750). A full cache raises
`BC_ASSERT: 0` (Fog AssetCache.h:187) and grows by half. Sprite walls add one model per classic tile a map uses (up to 57 per map, 223 over the 17 maps), so a session through
several maps comes closer to the limit. The plugin
(`plugin/src/model_cache.cpp`, `model_cache_logic.h`, test `plugin/tests/model_cache_test.cpp`, off word `modelcache`) starts
the cache at 8,250 (three times D2R's) before the renderer starts: the asset manager's constructor sets the capacity
(0xdfb5b9) and reserves the entry pool (0xdfb61d), and the ModelAssetCache init (0xf75c60, called from the renderer start)
sets the capacity again (0xf75cc1). All three immediates are patched after their bytes are compared; with only the first two
the live capacity read 2,750. `tools/cache_probe.py` accepts 8,250 as a ModelAsset capacity (`PLUGIN_CAPACITIES`).
In game (slot 1, `checks-20261109-120054-s1`, 8 maps in HD and legacy): the live capacity reads 8,250, peak 1,531 models.

The scene budget (`cap()`, `MAP_LIMITS`) is our own policy, not this cache: Fauztinville's (`cypherpunk`) composed scene is 8,620 placed pieces
and 7,999,943 bytes. In game it loads with no crash: 59-59.5 fps, private memory 9.7-9.8 GB at Fauztinville in HD (lane
stairs measured 9.54-9.77 GB with the 5,779-piece scene).

## Edited D2R maps (lane hole2, bug #525, 2026-11-03)

D2R builds a preset from the .ds1 in its own CASC whenever the CASC has that path, not from the mod's copy at the same path
(D2RLoader 1.3.1-beta, both graphics modes). Median's edits of D2R's own maps were therefore never used: Hole Level 2 (15,
lvlprest `Act1/Caves/CaveRoom4.ds1`) was D2R's large caveroom4 with D2R's units, while the mod's HD scene for that path (made
by walls_hd for Median's small room) was loaded on it, so HD drew no walls near the player. Maps at paths only the mod has
(Median's own `expansion/...` maps: 13, 14, 116 and the rest) were never affected.

`tools/ds1_paths.py build` (build step after legacy_art, tests `tools/tests/test_ds1_paths.py`) moves every .ds1 of the mod
whose path D2R has with other bytes to `data/global/tiles/mxl2012/<path>`, prefixes the lvlprest File cells naming it (excel
and excel/base) with `mxl2012/`, and moves its HD scene along: the mod's own scene, or a copy of D2R's scene, whose terrain
(`preset/<path>/terrain.model`) is named by its full D2R path and still loads. 11 of the 21 mod .ds1 files at a D2R path differ:

| Map | lvlprest row (Def) | HD scene |
|-|-|-|
| act1/caves/caveroom4 | Act 1 - Cave Treasure 4 (106): Hole Level 2 (15) | the mod's (walls_hd) |
| act1/caves/caveroom5 | Act 1 - Cave Treasure 5 (107) | D2R's copied |
| act1/cathedrl/cathy3 | Act 1 - Cathedral (257) | D2R's copied |
| act1/outdoors/bivouac | Act 1 - Bivouac (50) | D2R's copied |
| act2/maggot/magqueen | Act 2 - Lair Tight Spot S (509) | D2R's copied |
| act2/palace/harem2 | Act 2 - Harem (353) | D2R's copied |
| act2/tomb/duriel | Act 2 - Duriel's Lair (481) | D2R's copied |
| act3/jungle/dungrm6a | Act 3 - Dungeon Treasure 1 (703): Swampy Pit 3 (90) | the mod's (walls_hd) |
| act3/temple/temple5 | Act 3 - Temple 3 (750): 96 | the mod's (walls_hd) |
| act3/temple/temple6 | Act 3 - Temple 3 (750): 96 | the mod's (walls_hd) |
| act4/diab/heart | Act 4 - Diablo Heart (862) | D2R's copied |

So Median's object and unit edits of these maps (Duriel's lair, the Chaos heart, the cathedral, the harem, ...) take
effect now; before they were D2R's in both modes. Check `hole2_room` (tools/game_checks.py) reads the preset unit spots of
levels 15, 90 and 96 (`presets`) and names the .ds1 they belong to (mod or D2R), with HD screenshots also of 73, 33 and 50.

### Result per map in HD (lane maps10, 2026-11-04, slot 2, check `maps10`)

Check `maps10` (tools/game_checks.py) visits each level in HD and then classic. It tells which .ds1 the level was built from
by the preset spots that only Median's map or only D2R's has (`edit_source`), walks to the spot of Median's edit and takes
shots at the arrival and at that spot (`m10_<level>_<mode>_*.png`). Collision comes from the tiles on the server, so it is the
same in both modes. The HD look is D2R's copied scene or the walls_hd one. "Tiles" compares the tile layers of the two .ds1
files:

| Map | Level | Tiles against D2R's | Median's edit | Built from | HD scene | Result |
|-|-|-|-|-|-|-|
| caveroom5 | 16 (Cave Treasure 5) | same | Winged Death (act1 47) and fires; D2R's fallen shamans and unique pack gone | mod (2 Median-only spots) | cave as classic | OK |
| cathy3 | 33 | same | 8 gargoyle traps, LargeChestL (65,60), ConsolationChest | mod (6) | cathedral altar as classic | OK |
| bivouac | none (random Act 1 outdoor piece) | same | D2R's "The Cow King" preset (1,45) gone | judged from the files | D2R's copied: same tiles | OK (not seen in game) |
| magqueen | 64 (Maggot Lair 3) | same | 26 objects: fires 49-51, corpses, HellLight1, ConsolationChest; Staff of Kings chest kept | not told: `presets` lists nothing in a maze level and the walk (`magqueen_seek`) did not reach the room | D2R's copied: same tiles | OK (judged from the files) |
| harem2 | 50 | same | Sharp Tooth Sayer (act2 59) at (35,44) | mod (1) | arch and stairs as classic | OK |
| duriel | 73 | same walls, 1 floor cell | 4 firetowers, Flamespike the Crawler; D2R's 6 Brazier3 gone | mod (no D2R braziers) | lair as classic | OK |
| dungrm6a | 90 | differ | Riftwraith / Death Projector, raw monstats 970 | mod (3) | the mod's (walls_hd) | OK |
| temple5 / temple6 | 96 | differ | many object changes | mod (temple6, 35) | the mod's (walls_hd); grass floor as known (biome) | OK |
| heart | 108 | same walls, 84 floor cells | 2 champions, Anodized Elite (act4 28), SkeletonSpawnHell | mod (5) | D2R's copied: D2R's pentagram on Median's floor cells | OK |

No holes, missing walls or invisible walls were seen in the HD shots, so nothing needed a fix. In 16, 33, 50, 90 and 96 the
harness walk (`move`) stopped 23-100 sub-tiles short of the spot. It stopped by about as much in classic, so this is the
harness's path search on long paths and not a map defect. The check notes these walks rather than failing on them.

Duriel (73): his preset spot (135,218) and the arrival tile (orientation 10 at sub-tile (135,190)) are the same bytes in
Median's and D2R's duriel.ds1. At the first frame in the lair he stands at his preset, 20-25 sub-tiles from the player, in
both modes. He then walks or charges to the player (1.14d `AITHINK_Fn1_Duriel` 0x5f67b0: when not engaged, a charge with
chance aip5, otherwise a walk to the target), usually within 1.3-1.5 s. Classic Median 1.13c uses the same map and AI, so it
does the same and nothing was changed. Lane hole2's "Duriel stands at the arrival" was this rush, seen after it had ended.

## Median's look on the 8 retextured maps (lane maptint, 2026-10-30)

`tools/map_tint.py` (build step inside `walls_hd.py build`, tests `tools/tests/test_map_tint.py`; pixel reader
`tools/dt1_pixels.py`).

**Median's 51 retextured .dt1 are not recoloured.** `py -3 -I tools/map_tint.py measure` compares every tile of a new .dt1
pixel by pixel with the same tile of its stock donor (the donor under its own act's palette, Median's under Act 5's): the mean
RGB distance is 0.4 - 5.9 of 441, and only 0 - 1% of the pixels are more than 24 off (table below). Hue moves by at most 0.03 of
a turn and brightness by under 0.01. Only saturation drops, in the darkest pixels: Kurast's and the jungle's greens lose
0.05 - 0.11, the jungle trees 0.45 (dark green to dark grey-green). What Median changed is the palette **index**. The five act
palettes share 226 of their 256 entries, and Median moved every pixel onto those shared entries (the donors draw up to 46% of
their pixels with act-only entries), so a tile set looks the same whatever act's level uses it. D2R's wall models, placed by
`walls_hd.py`, already have the donors' colours; recoloured copies of the donor textures would change nothing worth the size.

**What makes the maps look like Median in legacy mode is their light.** Median places invisible light monsters
(`idleredlight`, `idlegreenlight`, `idlebluelight`, `idleyellowlight`: monstats2 Light 4-7 in red, green, blue, yellow) and
coloured lit objects in these maps. Classic (G) shows cypherpunk in indigo neon, glados in teal, charismatic as cool lavender
marble, macumba and borgir as dark with a few lit spots, and downtown, moskvich and desertpeak in warm red to gold (lane
hdwalls2's classic shots). D2R HD lights every map of a biome with that biome's directional key light (`global_key_light` of
`data/hd/env/vis/<biome>_<time>.json`: white for the Fortress, warm grey for the Mesa and Docktown), so all 8 looked like the
same warm grey stone.

**What the build does.** `map_tint.apply` gives each of the 8 maps its own biome, `mxl2012_tint_<map>`. It is a copy of the
biome its scene uses (D2R's, or maps_hd's generated floor biome, so the floor masks stay), and every time-of-day slot names
one visual data file, `data/hd/env/vis/mxl2012_tint_<map>.json`. That file is a copy of the base biome's day file with the
key light in the map's colour and power (`TINTS`). This is the same lever D2R itself uses for its time of day (Docktown's
night key light is blue). Only the key light changes (lightMask 9: scene and ground); the player, monster and item lights,
the grading LUT, IBL and fog stay D2R's. Cost: 8 biomes (about 70 KB each: a biome holds its terrain layers) and 8 visual data files (7 KB each), 0.6 MB, no
textures or models. maps_hd's floor biomes `mxl2012_act4_fort` and `mxl2012_act4_mesa` are still written, but no scene
names them now: their six maps use tinted copies of them, which keep their tile masks.

Also looked at and not used: the grading LUT (`gradingLutFile`, a .dds per visual data file) would recolour the player and
monsters too; `VisualDataBoxDefinitionComponent` (a visual data file per box of a scene) does the same as a whole-map biome
for a whole map; material or texture overrides of the placed models (`OverrideModelDefinitionComponent` swaps the whole
model) and recoloured texture copies would only repeat the donor colours (see the measurement above).

**In game** (slot 4, 2026-10-30, HD and classic, check `wall_maps`; docs/testing.md "Lane maptint"). All 8 maps were seen in HD
with their tint, no assert, load screens as before (0.1 - 2.9 s). Sheets: `mxl2012-runs/maptint/sheets/sheet_<map>.png`
(before = main's build, after = this build, legacy).

| Map | HD before | HD after | Legacy (G) | Left |
|---|---|---|---|---|
| desertpeak | grey stone | warm gold, saturation 0.22 -> 0.54 | gold, 0.66 | - |
| cypherpunk | warm grey | indigo / violet, hue 0.83 | 0.85 | - |
| glados | warm grey | cyan-teal | teal | - |
| downtown | warm grey | warm red-orange, saturation 0.37 -> 0.48 | 0.44 - (trees since lane walls4) |
| moskvich | warm | warmer gold, 0.47 -> 0.61 | 0.63 | - |
| borgir | grey, bright | dark teal-green | dark, teal floor, yellow torches | darker overall than before; torches keep their own light |
| macumba | grey, bright | dark warm | very dark warm | - |
| charismatic | white-grey | cool lavender-grey, hue 0.84 | lavender, hue 0.70, a bit more saturated | the tall pointed arch and long roofed walls (no fitting D2R model; arches and huts since lane walls4) |

The tint lights the scene and ground only. Median's coloured light spots (the light monsters) are not ported: D2R draws them
with the monsters' own HD light, as before.

<!-- map_tint:begin (generated: py -3 -I tools/map_tint.py docs) -->

| map | cells on new .dt1 (of all) | mean RGB distance | pixels > 24 off | hue shift | saturation | brightness | classic light (TINTS) | HD key light |
|---|---|---|---|---|---|---|---|---|
| expansion/dystopic/desertpeak.ds1 | 19084 (19122) | 2.2 | 0.00% | -0.010 | -0.080 | -0.0013 | dark gold, green glow on the floor rings | rgb 1.00 0.80 0.45, power x0.8 |
| expansion/ghetto/cypherpunk.ds1 | 15813 (17142) | 2.2 | 0.07% | -0.011 | -0.080 | -0.0010 | indigo with magenta neon | rgb 0.65 0.42 1.00, power x0.9 |
| expansion/glados/glados.ds1 | 3630 (8723) | 2.5 | 0.07% | -0.010 | +0.004 | +0.0032 | teal / cyan | rgb 0.45 0.85 1.00, power x1.0 |
| expansion/neonmile/downtown.ds1 | 38190 (38792) | 2.1 | 0.00% | -0.008 | +0.005 | +0.0022 | red-orange brick, green neon near the crowds | rgb 1.00 0.58 0.42, power x0.9 |
| expansion/redsquare/moskvich.ds1 | 331 (871) | 2.5 | 0.27% | -0.012 | -0.006 | +0.0027 | warm orange | rgb 1.00 0.72 0.42, power x1.0 |
| expansion/terror/borgir.ds1 | 2544 (2545) | 2.1 | 0.00% | -0.016 | -0.081 | -0.0007 | dark, teal floor lattice, yellow torches | rgb 0.62 1.00 0.97, power x0.5 |
| expansion/voodoo/macumba.ds1 | 1648 (1876) | 1.4 | 0.00% | -0.027 | -0.004 | +0.0011 | dim sepia | rgb 1.00 0.72 0.48, power x0.6 |
| expansion/zakarum/charismatic.ds1 | 2476 (2478) | 1.4 | 0.19% | -0.017 | -0.019 | +0.0013 | bright cool lavender-grey marble and slate | rgb 0.70 0.68 1.00, power x2.0 |

Per new .dt1 (all 51 copies; pixel pairs at the same place of the same tile key, new against donor):

| new .dt1 | donor | pixels | mean RGB distance | > 24 off | hue shift | saturation | brightness | on shared palette entries |
|---|---|---|---|---|---|---|---|---|
| expansion/dystopic/docks.dt1 | act3/docktown/docks.dt1 | 409592 | 1.5 | 0.00% | -0.005 | -0.101 | -0.0008 | 100% |
| expansion/dystopic/floors.dt1 | act3/kurast/floors.dt1 | 128680 | 1.7 | 0.00% | -0.006 | -0.077 | -0.0015 | 100% |
| expansion/dystopic/interior.dt1 | act3/kurast/interior.dt1 | 590864 | 1.2 | 0.00% | -0.004 | -0.053 | -0.0006 | 100% |
| expansion/dystopic/pyramid.dt1 | act3/docktown/pyramid.dt1 | 219875 | 2.8 | 0.26% | -0.010 | -0.048 | -0.0022 | 99% |
| expansion/dystopic/ruinflr.dt1 | act3/docktown/ruinflr.dt1 | 912840 | 2.6 | 0.00% | -0.008 | -0.082 | +0.0003 | 100% |
| expansion/dystopic/ruinwall.dt1 | act3/docktown/ruinwall.dt1 | 228005 | 2.3 | 0.00% | -0.010 | -0.035 | -0.0019 | 100% |
| expansion/dystopic/terraces.dt1 | act3/kurast/terraces.dt1 | 393165 | 2.9 | 0.00% | -0.016 | -0.109 | -0.0023 | 100% |
| expansion/dystopic/treegrp.dt1 | act3/jungle/treegrp.dt1 | 617230 | 5.9 | 0.00% | -0.032 | -0.474 | -0.0065 | 100% |
| expansion/dystopic/trees.dt1 | act3/jungle/trees.dt1 | 829387 | 4.9 | 0.00% | -0.027 | -0.445 | -0.0020 | 100% |
| expansion/magma/floor.dt1 | act4/lava/floor.dt1 | 2214807 | 2.4 | 0.97% | -0.014 | -0.102 | -0.0023 | 100% |
| expansion/magma/rocks.dt1 | act4/lava/rocks.dt1 | 77734 | 1.1 | 0.00% | -0.011 | -0.013 | +0.0012 | 100% |
| expansion/magma/walls.dt1 | act4/diab/walls.dt1 | 735612 | 2.2 | 0.00% | -0.002 | -0.180 | +0.0019 | 100% |
| expansion/neonmile/bridge.dt1 | act3/docktown/bridge.dt1 | 369291 | 2.0 | 0.00% | -0.009 | -0.054 | -0.0008 | 100% |
| expansion/neonmile/buildings.dt1 | expansion/town/buildings.dt1 | 1847801 | 0.4 | 0.00% | -0.002 | +0.001 | -0.0005 | 100% |
| expansion/neonmile/buildingses.dt1 | expansion/town/buildingses.dt1 | 1888837 | 0.4 | 0.00% | -0.002 | +0.001 | -0.0005 | 100% |
| expansion/neonmile/floors.dt1 | act3/travincal/floors.dt1 | 183693 | 1.7 | 0.00% | -0.006 | -0.092 | -0.0003 | 100% |
| expansion/neonmile/gate.dt1 | act3/travincal/gate.dt1 | 297339 | 1.6 | 0.00% | -0.004 | -0.035 | -0.0010 | 100% |
| expansion/neonmile/ground.dt1 | expansion/town/ground.dt1 | 1172883 | 0.7 | 0.00% | -0.004 | +0.002 | -0.0009 | 100% |
| expansion/neonmile/keepwall.dt1 | expansion/town/keepwall.dt1 | 1580786 | 0.3 | 0.00% | -0.001 | +0.009 | -0.0001 | 100% |
| expansion/neonmile/maingate.dt1 | expansion/town/maingate.dt1 | 220409 | 0.9 | 0.00% | -0.001 | +0.006 | -0.0007 | 100% |
| expansion/neonmile/otherwalls.dt1 | expansion/town/otherwalls.dt1 | 47794 | 0.4 | 0.00% | -0.002 | +0.002 | -0.0004 | 100% |
| expansion/neonmile/rkwall.dt1 | expansion/town/rkwall.dt1 | 1010187 | 0.9 | 0.00% | -0.003 | +0.002 | -0.0010 | 100% |
| expansion/neonmile/terraces.dt1 | act3/travincal/terraces.dt1 | 607902 | 1.8 | 0.00% | -0.005 | -0.089 | -0.0009 | 100% |
| expansion/neonmile/townwalls.dt1 | expansion/town/walls.dt1 | 342437 | 1.5 | 0.00% | -0.002 | -0.013 | -0.0017 | 100% |
| expansion/neonmile/trees.dt1 | expansion/town/trees.dt1 | 41035 | 0.3 | 0.00% | -0.002 | +0.001 | -0.0003 | 100% |
| expansion/neonmile/wallrocks.dt1 | act3/kurast/terraces.dt1 | 393165 | 2.9 | 0.00% | -0.016 | -0.109 | -0.0023 | 100% |
| expansion/neonmile/walls.dt1 | act3/travincal/walls.dt1 | 620663 | 1.7 | 0.00% | +0.001 | -0.122 | +0.0002 | 100% |
| expansion/neonmile/walls2.dt1 | expansion/town/walls2.dt1 | 360210 | 0.5 | 0.00% | -0.003 | -0.000 | -0.0007 | 100% |
| expansion/redsquare/arch_walls.dt1 | act4/mesa/arch_walls.dt1 | 135771 | 2.0 | 0.00% | -0.020 | -0.162 | +0.0001 | 100% |
| expansion/redsquare/brick_walls.dt1 | act4/mesa/brick_walls.dt1 | 136601 | 2.4 | 0.00% | -0.026 | -0.100 | +0.0016 | 100% |
| expansion/redsquare/chain_walls.dt1 | act4/mesa/chain_walls.dt1 | 202336 | 2.0 | 0.00% | -0.021 | -0.176 | +0.0001 | 100% |
| expansion/redsquare/dist_wall.dt1 | act4/mesa/dist_wall.dt1 | 346850 | 2.3 | 0.00% | -0.017 | -0.256 | +0.0002 | 100% |
| expansion/redsquare/floor.dt1 | act4/mesa/floor.dt1 | 686866 | 2.5 | 0.00% | -0.010 | +0.007 | +0.0034 | 100% |
| expansion/redsquare/weird.dt1 | act4/mesa/weird.dt1 | 10024 | 1.1 | 0.00% | +0.012 | -0.043 | -0.0007 | 100% |
| expansion/terror/basewall.dt1 | act1/crypt/basewall.dt1 | 236761 | 3.3 | 0.00% | -0.036 | +0.010 | +0.0007 | 100% |
| expansion/terror/column.dt1 | act1/cathedrl/column.dt1 | 21339 | 2.9 | 0.00% | -0.025 | -0.005 | -0.0013 | 100% |
| expansion/terror/floor.dt1 | act1/crypt/floor.dt1 | 19200 | 2.9 | 0.00% | -0.034 | +0.014 | +0.0014 | 100% |
| expansion/terror/frescoes.dt1 | act1/cathedrl/frescoes.dt1 | 253386 | 2.9 | 0.00% | -0.017 | +0.002 | -0.0012 | 100% |
| expansion/terror/graveyrd.dt1 | act1/graveyard/graveyrd.dt1 | 526383 | 2.4 | 0.00% | -0.051 | -0.004 | +0.0005 | 100% |
| expansion/terror/stained.dt1 | act1/cathedrl/stained.dt1 | 140982 | 2.6 | 0.00% | -0.028 | +0.000 | -0.0003 | 100% |
| expansion/voodoo/floors.dt1 | act3/travincal/floors.dt1 | 183693 | 1.7 | 0.00% | -0.006 | -0.092 | -0.0003 | 100% |
| expansion/voodoo/pygmy.dt1 | act3/jungle/pygmy.dt1 | 154968 | 3.1 | 0.00% | -0.021 | -0.124 | +0.0021 | 100% |
| expansion/voodoo/ruin.dt1 | act3/jungle/ruin.dt1 | 386131 | 4.5 | 0.00% | -0.028 | -0.118 | -0.0003 | 100% |
| expansion/voodoo/terraces.dt1 | act3/kurast/terraces.dt1 | 393165 | 2.9 | 0.00% | -0.016 | -0.109 | -0.0023 | 100% |
| expansion/voodoo/treegrp.dt1 | act3/jungle/treegrp.dt1 | 617230 | 5.9 | 0.00% | -0.032 | -0.474 | -0.0065 | 100% |
| expansion/voodoo/trees.dt1 | act3/jungle/trees.dt1 | 829387 | 4.9 | 0.00% | -0.027 | -0.445 | -0.0020 | 100% |
| expansion/voodoo/walls.dt1 | act3/kurast/walls.dt1 | 1013715 | 2.9 | 0.00% | -0.014 | -0.151 | -0.0023 | 100% |
| expansion/zakarum/exterior.dt1 | act4/fort/exterior.dt1 | 512595 | 2.4 | 1.25% | -0.024 | -0.043 | +0.0004 | 100% |
| expansion/zakarum/foregate.dt1 | act4/fort/foregate.dt1 | 706270 | 2.1 | 0.00% | -0.016 | -0.039 | +0.0021 | 100% |
| expansion/zakarum/interior.dt1 | act4/fort/interior.dt1 | 310773 | 1.7 | 0.00% | -0.000 | -0.091 | +0.0008 | 100% |
| expansion/zakarum/plaza.dt1 | act4/fort/plaza.dt1 | 476737 | 1.0 | 0.00% | -0.016 | -0.004 | +0.0014 | 100% |

Distances are in RGB units (0-441): Median's tile under the Act 5 palette against the donor under its own act's. Hue in turns (1 = 360 degrees), only over pixels coloured on both sides; saturation and brightness on the HSV 0-1 scale. Map rows weight each file by the map's wall and floor cells drawn from it.

<!-- map_tint:end -->

## Files

| File | State |
|---|---|
| `tools/ds1_remap.py` | adapted: no `objpreset`, monster ids from `tools/idmap.py`, `Ds1` reader keeps the layers (tile checks), object block checked against truncation |
| `tools/maps_hd.py` | adapted: Median's inputs (34 maps, vanilla levels), tile-set stand-ins from `.dt1` content, biome vote, audit folded in |
| `tools/dt1.py` | new: .dt1 v7 reader (keys, sizes, pixel digest, walkability header) |
| `tools/tests/test_maps.py` | new |
| `docs/maps-hd.md` | this file (the tables between the markers are generated) |
| `tools/objpreset.py` | not copied: Median has no ObjPreset table and D2R's resolves every object id |
| `tools/area_audit.py` | not copied: the checks that matter for 34 maps are `maps_hd.audit` |

Median's own textures for the retextured maps: none needed (the retextures keep the donors' colours, section "Median's look"); the
maps' coloured light is `tools/map_tint.py`. Gaps are in `docs/unported.md` (section Maps).

## Generated tables

Refresh: `py -3 -I tools/maps_hd.py docs`. Needs the extract and the D2R 93847 baseline extract (`filelist.txt`, tables, tiles).

<!-- maps_hd:begin (generated: py -3 -I tools/maps_hd.py docs) -->

### Maps (34 .ds1)

| map | levels (lvlprest -> levels.txt) | size | kind | plan | scene / biome | conf. | art needed for walls/buildings |
|---|---|---|---|---|---|---|---|
| act1/cathedrl/cathy3.ds1 | 33 Act 1 - Cathedral | 29x35 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act1/cathedrl/inarius.ds1 | 14 Act 1 - Cave 3 Treasure | 29x35 | Median map | minimal scene | act1_cathedral | medium | D2R's stock walls in HD (tools/walls_hd.py): all 110 wall cells are stock tiles |
| act1/caves/caveroom4.ds1 | 15 Act 1 - Cave 4 Treasure | 25x25 | D2R map, edited by Median | minimal scene | act1_caves | medium | D2R's stock walls in HD (tools/walls_hd.py; D2R's scene dropped: layout changed) |
| act1/caves/caveroom5.ds1 | 16 Act 1 - Cave 5 Treasure | 25x25 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act1/outdoors/bivouac.ds1 | preset rows: Act 1 - Bivouac | 17x17 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act2/arcane/belial.ds1 | 65 Act 2 - Sewer 2 A | 48x48 | Median map | minimal scene | act2_arcane | medium | D2R's stock walls in HD (tools/walls_hd.py): all 81 wall cells are stock tiles |
| act2/maggot/magqueen.ds1 | preset rows: Act 2 - Lair Tight Spot S | 11x11 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act2/palace/harem2.ds1 | 50 Act 2 - Harem | 17x20 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act2/tomb/duriel.ds1 | 73 Act 2 - Duriel's Lair | 33x48 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act3/jungle/dungrm6a.ds1 | 90 Act 3 - Dungeon 1 Treasure | 41x41 | D2R map, edited by Median | minimal scene | act3_jungle (level type: act3_jungle_dungeon) | medium | D2R's stock walls in HD (tools/walls_hd.py; D2R's scene dropped: layout changed) |
| act3/kurast/excelsior3.ds1 | 84 Act 3 - Spider 1 | 51x51 | Median map | minimal scene | act3_kurast | medium | D2R's stock walls in HD (tools/walls_hd.py): all 1199 wall cells are stock tiles |
| act3/temple/temple5.ds1 | 96 Act 3 - Temple 3 | 25x25 | D2R map, edited by Median | minimal scene | act3_kurast | medium | D2R's stock walls in HD (tools/walls_hd.py; D2R's scene dropped: layout changed) |
| act3/temple/temple6.ds1 | 96 Act 3 - Temple 3 | 25x25 | D2R map, edited by Median | minimal scene | act3_kurast | medium | D2R's stock walls in HD (tools/walls_hd.py; D2R's scene dropped: layout changed) |
| act4/diab/entry1.ds1 | preset rows: Act 4 - Diablo Entry | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/heart.ds1 | preset rows: Act 4 - Diablo Heart | 25x25 | D2R map, edited by Median | D2R scene | D2R scene | medium | none (D2R's scene) |
| act4/diab/winge1.ds1 | preset rows: Act 4 - Diablo Arm E | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/winge2.ds1 | preset rows: Act 4 - Diablo Arm E | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/wingn1.ds1 | preset rows: Act 4 - Diablo Arm N | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/wingn2.ds1 | preset rows: Act 4 - Diablo Arm N | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/wings1.ds1 | preset rows: Act 4 - Diablo Arm S | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/wings2.ds1 | preset rows: Act 4 - Diablo Arm S | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/wingw1.ds1 | preset rows: Act 4 - Diablo Arm W | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| act4/diab/wingw2.ds1 | preset rows: Act 4 - Diablo Arm W | 25x25 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| expansion/dystopic/desertpeak.ds1 | 60 Act 2 - Tomb 2 Treasure | 128x128 | Median map | minimal scene | act3_docktown (level type: act2_tomb) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act3/docktown, act3/jungle, act3/kurast, act4/fort; Median's re-textured look needs custom art (2697 of 2992 wall cells on new .dt1) |
| expansion/ghetto/cypherpunk.ds1 | 59 Act 2 - Tomb 1 Treasure | 128x128 | Median map | minimal scene | act3_docktown (level type: act2_tomb) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act3/docktown, act3/jungle, act3/kurast, act4/fort; Median's re-textured look needs custom art (4691 of 5228 wall cells on new .dt1) |
| expansion/glados/glados.ds1 | 95 Act 3 - Temple 2 | 120x120 | Median map | minimal scene | act4_mesa (level type: act3_kurast) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act4/fort, act4/mesa; Median's re-textured look needs custom art (200 of 1038 wall cells on new .dt1) |
| expansion/icecave/rockisdead.ds1 | 116 Act 5 - Ice Cave 2A | 65x65 | Median map | minimal scene | expansion_icecave | medium | D2R's stock walls in HD (tools/walls_hd.py): all 52 wall cells are stock tiles |
| expansion/morework/epicwhiners.ds1 | 13 Act 1 - Cave 2 Treasure | 120x120 | Median map | minimal scene | act1_caves (level type: act1_cathedral) | medium | D2R's stock walls in HD (tools/walls_hd.py): all 1735 wall cells are stock tiles |
| expansion/neonmile/downtown.ds1 | 18 Act 1 - Crypt 1 A | 251x251 | Median map | minimal scene | act4_mesa (level type: act1_crypt) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act3/travincal, act4/fort, act4/mesa, expansion/town; Median's re-textured look needs custom art (2002 of 3493 wall cells on new .dt1) |
| expansion/redsquare/moskvich.ds1 | 98 Act 3 - Temple 5 | 25x25 | Median map | minimal scene | act4_mesa (level type: act3_kurast) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act4/fort, act4/mesa; Median's re-textured look needs custom art (82 of 393 wall cells on new .dt1) |
| expansion/terror/borgir.ds1 | 126 Act 5 - Hell 2 | 100x100 | Median map | minimal scene | act4_fort (level type: expansion_icecave) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act3/jungle, act3/kurast, act4/fort; Median's re-textured look needs custom art (1306 of 1315 wall cells on new .dt1) |
| expansion/town/townwest.ds1 | 109 Act 5 - Town | 41x41 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| expansion/voodoo/macumba.ds1 | 125 Act 5 - Hell 1 | 64x64 | Median map | minimal scene | act4_fort (level type: expansion_icecave) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act1/graveyard, act3/kurast, act4/fort; Median's re-textured look needs custom art (421 of 429 wall cells on new .dt1) |
| expansion/zakarum/charismatic.ds1 | 127 Act 5 - Hell 3 | 96x96 | Median map | minimal scene | act4_fort (level type: act4_lava) | medium | D2R's stock walls in HD (tools/walls_hd.py): stand-in tiles are stock act4/fort; Median's re-textured look needs custom art (870 of 871 wall cells on new .dt1) |

Notes per map: diff against D2R, tile resolution through lvlprest Dt1Mask + lvltypes, ids the remap / ID map must see:

| map | note | floor / wall cells (on new .dt1) | monsters: preset rows / raw MonStats rows | objects (unresolved in D2R's table) |
|---|---|---|---|---|
| act1/cathedrl/cathy3.ds1 | Median's layout on D2R's scene: 0.0% of wall/floor cells differ; 10 objects added, 0 removed | 602 (0) / 226 (0) | 9 / 0 | 31 (0) |
| act1/cathedrl/inarius.ds1 | biome by override: clone of cathy3 (same size and tile-file list; the vote only sees the shared Barracks floor) | 216 (0) / 110 (0) | 4 / 18: quest_overlord, quest_rogue1h, quest_rogue2h | 15 (0) |
| act1/caves/caveroom4.ds1 | layout differs too much for D2R's baked scene (tiles changed, 33% of wall/floor cells); biome by floor cells: act1/caves 87 | 87 (0) / 3 (0); 1 unresolved | 1 / 0 | 5 (0) |
| act1/caves/caveroom5.ds1 | Median's layout on D2R's scene: 0.0% of wall/floor cells differ; 3 objects added, 5 removed | 306 (0) / 6 (0); 1 unresolved | 1 / 0 | 14 (0) |
| act1/outdoors/bivouac.ds1 | Median's layout on D2R's scene: 0.0% of wall/floor cells differ; 0 objects added, 1 removed | 289 (0) / 39 (0); no level, tiles not resolved | 0 / 0 | 5 (0) |
| act2/arcane/belial.ds1 | biome by floor cells: act2/arcane 173 | 173 (0) / 81 (0); 1 unresolved | 0 / 2: quest_fleshdoom, quest_subordinate | 4 (0) |
| act2/maggot/magqueen.ds1 | Median's layout on D2R's scene: 0.0% of wall/floor cells differ; 26 objects added, 0 removed | 36 (0) / 28 (0); no level, tiles not resolved | 1 / 0 | 27 (0) |
| act2/palace/harem2.ds1 | Median's layout on D2R's scene: 0.0% of wall/floor cells differ; 1 objects added, 0 removed | 201 (0) / 116 (0); 2 unresolved | 1 / 0 | 13 (0) |
| act2/tomb/duriel.ds1 | Median's layout on D2R's scene: 0.0% of wall/floor cells differ; 5 objects added, 6 removed | 765 (0) / 225 (0); 3 unresolved | 7 / 0 | 38 (0) |
| act3/jungle/dungrm6a.ds1 | layout differs too much for D2R's baked scene (tiles changed, 32% of wall/floor cells); biome by floor cells: act3/jungle 859 | 859 (0) / 475 (0) | 3 / 8: quest_laser | 51 (0) |
| act3/kurast/excelsior3.ds1 | biome by floor cells: act3/ground 1827, act3/kurast 758, act3/jungle 16 | 2737 (0) / 1199 (0); 185 unresolved | 0 / 15: spawn_cast3, super_cast3 | 47 (0) |
| act3/temple/temple5.ds1 | layout differs too much for D2R's baked scene (tiles changed, 34% of wall/floor cells); biome by floor cells: act3/kurast 246, act3/travincal 21 | 267 (0) / 170 (0) | 1 / 0 | 35 (0) |
| act3/temple/temple6.ds1 | layout differs too much for D2R's baked scene (tiles changed, 32% of wall/floor cells); biome by floor cells: act3/kurast 246, act3/travincal 21 | 267 (0) / 170 (0) | 1 / 0 | 35 (0) |
| act4/diab/entry1.ds1 | byte-identical to D2R's map | 636 (0) / 71 (0); no level, tiles not resolved | 0 / 0 | 16 (0) |
| act4/diab/heart.ds1 | Median's layout on D2R's scene: 4.5% of wall/floor cells differ; 5 objects added, 0 removed | 717 (0) / 58 (0); no level, tiles not resolved | 3 / 0 | 25 (0) |
| act4/diab/winge1.ds1 | byte-identical to D2R's map | 652 (0) / 75 (0); no level, tiles not resolved | 0 / 0 | 22 (0) |
| act4/diab/winge2.ds1 | byte-identical to D2R's map | 660 (0) / 44 (0); no level, tiles not resolved | 0 / 0 | 22 (0) |
| act4/diab/wingn1.ds1 | byte-identical to D2R's map | 662 (0) / 68 (0); no level, tiles not resolved | 0 / 0 | 22 (0) |
| act4/diab/wingn2.ds1 | byte-identical to D2R's map | 662 (0) / 59 (0); no level, tiles not resolved | 0 / 0 | 21 (0) |
| act4/diab/wings1.ds1 | byte-identical to D2R's map | 673 (0) / 101 (0); no level, tiles not resolved | 0 / 0 | 13 (0) |
| act4/diab/wings2.ds1 | byte-identical to D2R's map | 673 (0) / 96 (0); no level, tiles not resolved | 0 / 0 | 19 (0) |
| act4/diab/wingw1.ds1 | byte-identical to D2R's map | 654 (0) / 54 (0); no level, tiles not resolved | 0 / 0 | 23 (0) |
| act4/diab/wingw2.ds1 | byte-identical to D2R's map | 646 (0) / 76 (0); no level, tiles not resolved | 0 / 0 | 24 (0) |
| expansion/dystopic/desertpeak.ds1 | biome by floor cells: act3/docktown 13114, act3/kurast 3012, act2/tomb 3 | 16130 (16127) / 2992 (2697) | 0 / 94: goldencalf, hefaetruspriestess, hefaetrusturret, idleredlight, karcheushimself... | 21 (0) |
| expansion/ghetto/cypherpunk.ds1 | biome by floor cells: act3/docktown 5095, act3/kurast 3199, act4/fort 2464 | 11917 (10830) / 5228 (4691); 3 unresolved | 0 / 206: hefaetrusturret, idlegreenlight, neonfiend, r_alpha, r_beta... | 0 (0) |
| expansion/glados/glados.ds1 | biome by floor cells: act4/mesa 3419, act3/kurast 2959, act3/travincal 1307 | 7685 (3419) / 1038 (200) | 0 / 200: combatdrone2, mcsboss, sentinelchain, sentinelcore, sentinelcube1... | 165 (0) |
| expansion/icecave/rockisdead.ds1 | biome by floor cells: expansion/icecave 3586 | 3586 (0) / 52 (0) | 2 / 1: quest_malic | 210 (0) |
| expansion/morework/epicwhiners.ds1 | biome by floor cells: act1/caves 4122, act1/cathedrl 1044 | 5166 (0) / 1735 (0); 1 unresolved | 5 / 1: orkshaman | 607 (0) |
| expansion/neonmile/downtown.ds1 | biome by floor cells: act4/mesa 27300, expansion/town 7939, act3/travincal 58 | 35299 (35297) / 3493 (2002) | 1 / 0 | 986 (0) |
| expansion/redsquare/moskvich.ds1 | biome by floor cells: act4/mesa 242, act3/kurast 231, act3/travincal 5 | 478 (242) / 393 (82) | 1 / 0 | 0 (0) |
| expansion/terror/borgir.ds1 | biome by floor cells: act4/fort 1230, expansion/icecave 1 | 1231 (1230) / 1315 (1306); 1 unresolved | 0 / 2: darkstardragon, empty_undeadmage4 | 212 (0) |
| expansion/town/townwest.ds1 | byte-identical to D2R's map | 1321 (0) / 731 (0) | 13 / 0 | 38 (0) |
| expansion/voodoo/macumba.ds1 | biome by floor cells: act4/fort 1227, expansion/icecave 226 | 1453 (1227) / 429 (421); 6 unresolved | 0 / 9: toraja_celebrant, toraja_morlufiend | 28 (0) |
| expansion/zakarum/charismatic.ds1 | biome by floor cells: act4/fort 1606, act4/lava 1, act4/expansion 1 | 1608 (1606) / 871 (870); 1 unresolved | 0 / 7: quest_lightwells | 9 (0) |

### Tile sets (52 new .dt1) and their stock stand-ins

Match = same set of (orientation, style, sequence, width, height) as a stock .dt1 (J = Jaccard of the multisets); walkability = tiles whose header (sub-tile flags, roof, sound, animation) equals the stand-in's. Level types are the lvltypes rows that list the file.

| new .dt1 | tiles | stock stand-in | match | walkability same | stock biome | maps using it | level types |
|---|---|---|---|---|---|---|---|
| expansion/dystopic/docks.dt1 | 64 | act3/docktown/docks.dt1 | copy (J 1.00) | 64/64 | act3_docktown | none | Act 2 - Tomb |
| expansion/dystopic/floors.dt1 | 61 | act3/kurast/floors.dt1 | copy (J 1.00) | 61/61 | act3_kurast | expansion/dystopic/desertpeak, expansion/ghetto/cypherpunk | Act 2 - Tomb |
| expansion/dystopic/interior.dt1 | 73 | act3/kurast/interior.dt1 | copy (J 1.00) | 73/73 | act3_kurast | expansion/ghetto/cypherpunk | Act 2 - Tomb |
| expansion/dystopic/pyramid.dt1 | 18 | act3/docktown/pyramid.dt1 | copy (J 1.00) | 18/18 | act3_docktown | none | Act 2 - Tomb |
| expansion/dystopic/ruinflr.dt1 | 179 | act3/docktown/ruinflr.dt1 | copy (J 1.00) | 179/179 | act3_docktown | none | Act 2 - Tomb |
| expansion/dystopic/ruinwall.dt1 | 46 | act3/docktown/ruinwall.dt1 | copy (J 1.00) | 46/46 | act3_docktown | expansion/dystopic/desertpeak | Act 2 - Tomb |
| expansion/dystopic/terraces.dt1 | 105 | act3/kurast/terraces.dt1 | copy (J 1.00) | 105/105 | act3_kurast | expansion/dystopic/desertpeak, expansion/ghetto/cypherpunk | Act 2 - Tomb |
| expansion/dystopic/treegrp.dt1 | 24 | act3/jungle/treegrp.dt1 | copy (J 1.00) | 24/24 | act3_jungle | expansion/dystopic/desertpeak | Act 2 - Tomb |
| expansion/dystopic/trees.dt1 | 189 | act3/jungle/trees.dt1 | copy (J 1.00) | 189/189 | act3_jungle | expansion/dystopic/desertpeak, expansion/ghetto/cypherpunk | Act 2 - Tomb |
| expansion/magma/floor.dt1 | 494 | act4/lava/floor.dt1 | copy (J 1.00) | 494/494 | act4_lava | none | - |
| expansion/magma/rocks.dt1 | 22 | act4/lava/rocks.dt1 | copy (J 1.00) | 22/22 | act4_lava | none | - |
| expansion/magma/walls.dt1 | 48 | act4/diab/walls.dt1 | copy (J 1.00) | 48/48 | act4_diab | none | - |
| expansion/neonmile/bridge.dt1 | 59 | act3/docktown/bridge.dt1 | copy (J 1.00) | 59/59 | act3_docktown | expansion/dystopic/desertpeak, expansion/ghetto/cypherpunk | Act 1 - Crypt, Act 2 - Tomb |
| expansion/neonmile/buildings.dt1 | 222 | expansion/town/buildings.dt1 | copy (J 1.00) | 222/222 | expansion_town | expansion/neonmile/downtown | Act 1 - Crypt |
| expansion/neonmile/buildingses.dt1 | 229 | expansion/town/buildingses.dt1 | copy (J 1.00) | 229/229 | expansion_town | none | Act 1 - Crypt |
| expansion/neonmile/floors.dt1 | 55 | act3/travincal/floors.dt1 | copy (J 1.00) | 55/55 | act3_travincal | none | Act 1 - Crypt |
| expansion/neonmile/gate.dt1 | 23 | act3/travincal/gate.dt1 | copy (J 1.00) | 23/23 | act3_travincal | none | Act 1 - Crypt |
| expansion/neonmile/ground.dt1 | 199 | expansion/town/ground.dt1 | copy (J 1.00) | 199/199 | expansion_town | expansion/neonmile/downtown | Act 1 - Crypt |
| expansion/neonmile/keepwall.dt1 | 54 | expansion/town/keepwall.dt1 | copy (J 1.00) | 54/54 | expansion_town | expansion/neonmile/downtown | Act 1 - Crypt |
| expansion/neonmile/maingate.dt1 | 28 | expansion/town/maingate.dt1 | copy (J 1.00) | 28/28 | expansion_town | expansion/neonmile/downtown | Act 1 - Crypt |
| expansion/neonmile/otherwalls.dt1 | 13 | expansion/town/otherwalls.dt1 | copy (J 1.00) | 13/13 | expansion_town | none | Act 1 - Crypt |
| expansion/neonmile/rkwall.dt1 | 22 | expansion/town/rkwall.dt1 | copy (J 1.00) | 22/22 | expansion_town | none | Act 1 - Crypt |
| expansion/neonmile/terraces.dt1 | 120 | act3/travincal/terraces.dt1 | copy (J 1.00) | 120/120 | act3_travincal | expansion/neonmile/downtown | Act 1 - Crypt |
| expansion/neonmile/townwalls.dt1 | 15 | expansion/town/walls.dt1 | copy (J 1.00) | 15/15 | expansion_town | none | Act 1 - Crypt |
| expansion/neonmile/trees.dt1 | 25 | expansion/town/trees.dt1 | copy (J 1.00) | 25/25 | expansion_town | none | Act 1 - Crypt |
| expansion/neonmile/wallrocks.dt1 | 105 | act3/kurast/terraces.dt1 | copy (J 1.00) | 105/105 | act3_kurast | none | Act 1 - Crypt |
| expansion/neonmile/walls.dt1 | 45 | act3/travincal/walls.dt1 | copy (J 1.00) | 45/45 | act3_travincal | expansion/neonmile/downtown | Act 1 - Crypt |
| expansion/neonmile/walls2.dt1 | 47 | expansion/town/walls2.dt1 | copy (J 1.00) | 47/47 | expansion_town | none | Act 1 - Crypt |
| expansion/redsquare/arch_walls.dt1 | 12 | act4/mesa/arch_walls.dt1 | copy (J 1.00) | 12/12 | act4_mesa | none | Act 1 - Crypt, Act 3 - Kurast |
| expansion/redsquare/brick_walls.dt1 | 31 | act4/mesa/brick_walls.dt1 | copy (J 1.00) | 31/31 | act4_mesa | expansion/redsquare/moskvich | Act 1 - Crypt, Act 3 - Kurast |
| expansion/redsquare/chain_walls.dt1 | 26 | act4/mesa/chain_walls.dt1 | copy (J 1.00) | 26/26 | act4_mesa | expansion/neonmile/downtown | Act 1 - Crypt, Act 3 - Kurast |
| expansion/redsquare/dist_wall.dt1 | 23 | act4/mesa/dist_wall.dt1 | copy (J 1.00) | 23/23 | act4_mesa | none | Act 1 - Crypt, Act 3 - Kurast |
| expansion/redsquare/floor.dt1 | 215 | act4/mesa/floor.dt1 | copy (J 1.00) | 215/215 | act4_mesa | expansion/dystopic/desertpeak, expansion/ghetto/cypherpunk, expansion/glados/glados, expansion/neonmile/downtown, expansion/redsquare/moskvich | Act 1 - Crypt, Act 2 - Tomb, Act 3 - Kurast |
| expansion/redsquare/inv_wall.dt1 | 24 | act4/mesa/inv_wall.dt1 | none (J 0.37) | 13/24 | act4_mesa | expansion/neonmile/downtown | Act 1 - Crypt, Act 3 - Kurast |
| expansion/redsquare/weird.dt1 | 1 | act4/mesa/weird.dt1 | copy (J 1.00) | 1/1 | act4_mesa | none | Act 3 - Kurast |
| expansion/terror/basewall.dt1 | 26 | act1/crypt/basewall.dt1 | copy (J 1.00) | 26/26 | act1_crypt | none | Act 5 - Ice Caves |
| expansion/terror/column.dt1 | 1 | act1/cathedrl/column.dt1 | copy (J 1.00) | 1/1 | act1_cathedral | none | Act 5 - Ice Caves |
| expansion/terror/floor.dt1 | 30 | act1/crypt/floor.dt1 | copy (J 1.00) | 30/30 | act1_crypt | none | Act 5 - Ice Caves |
| expansion/terror/frescoes.dt1 | 20 | act1/cathedrl/frescoes.dt1 | copy (J 1.00) | 20/20 | act1_cathedral | none | Act 5 - Ice Caves |
| expansion/terror/graveyrd.dt1 | 104 | act1/graveyard/graveyrd.dt1 | copy (J 1.00) | 104/104 | act1_outdoors | expansion/voodoo/macumba | Act 5 - Ice Caves |
| expansion/terror/stained.dt1 | 17 | act1/cathedrl/stained.dt1 | copy (J 1.00) | 17/17 | act1_cathedral | none | Act 5 - Ice Caves |
| expansion/voodoo/floors.dt1 | 55 | act3/travincal/floors.dt1 | copy (J 1.00) | 55/55 | act3_travincal | none | Act 5 - Ice Caves |
| expansion/voodoo/pygmy.dt1 | 29 | act3/jungle/pygmy.dt1 | copy (J 1.00) | 29/29 | act3_jungle | none | Act 5 - Ice Caves |
| expansion/voodoo/ruin.dt1 | 75 | act3/jungle/ruin.dt1 | copy (J 1.00) | 75/75 | act3_jungle | none | Act 5 - Ice Caves |
| expansion/voodoo/terraces.dt1 | 105 | act3/kurast/terraces.dt1 | copy (J 1.00) | 105/105 | act3_kurast | expansion/terror/borgir, expansion/voodoo/macumba | Act 5 - Ice Caves |
| expansion/voodoo/treegrp.dt1 | 24 | act3/jungle/treegrp.dt1 | copy (J 1.00) | 24/24 | act3_jungle | expansion/terror/borgir | Act 5 - Ice Caves |
| expansion/voodoo/trees.dt1 | 189 | act3/jungle/trees.dt1 | copy (J 1.00) | 189/189 | act3_jungle | expansion/terror/borgir | Act 5 - Ice Caves |
| expansion/voodoo/walls.dt1 | 112 | act3/kurast/walls.dt1 | copy (J 1.00) | 112/112 | act3_kurast | expansion/terror/borgir | Act 5 - Ice Caves |
| expansion/zakarum/exterior.dt1 | 55 | act4/fort/exterior.dt1 | copy (J 1.00) | 55/55 | act4_fort | expansion/dystopic/desertpeak, expansion/ghetto/cypherpunk, expansion/glados/glados, expansion/neonmile/downtown, expansion/redsquare/moskvich, expansion/zakarum/charismatic | Act 1 - Crypt, Act 2 - Tomb, Act 3 - Kurast, Act 5 - Lava |
| expansion/zakarum/foregate.dt1 | 64 | act4/fort/foregate.dt1 | copy (J 1.00) | 64/64 | act4_fort | expansion/redsquare/moskvich, expansion/zakarum/charismatic | Act 3 - Kurast, Act 5 - Lava |
| expansion/zakarum/interior.dt1 | 30 | act4/fort/interior.dt1 | copy (J 1.00) | 30/30 | act4_fort | expansion/ghetto/cypherpunk, expansion/zakarum/charismatic | Act 2 - Tomb, Act 3 - Kurast, Act 5 - Lava |
| expansion/zakarum/plaza.dt1 | 78 | act4/fort/plaza.dt1 | copy (J 1.00) | 78/78 | act4_fort | expansion/ghetto/cypherpunk, expansion/terror/borgir, expansion/voodoo/macumba, expansion/zakarum/charismatic | Act 1 - Crypt, Act 2 - Tomb, Act 3 - Kurast, Act 5 - Ice Caves, Act 5 - Lava |

### Levels whose map set or key columns differ from D2R's

| level | Median maps (lvlprest) | D2R maps | levels.txt change (D2R -> mod) |
|---|---|---|---|
| 13 Act 1 - Cave 2 Treasure | expansion/morework/epicwhiners | act1/caves/caveroom2 | SizeX 24->119, SizeY 24->119, LevelType 3->9 |
| 14 Act 1 - Cave 3 Treasure | act1/cathedrl/inarius | act1/caves/caveroom3 | SizeX 24->28, SizeY 24->34, LevelType 3->9 |
| 18 Act 1 - Crypt 1 A | expansion/neonmile/downtown | - | SizeX 200->250, SizeY 200->250, DrlgType 1->2 |
| 59 Act 2 - Tomb 1 Treasure | expansion/ghetto/cypherpunk | - | SizeX 200->127, SizeY 200->127, DrlgType 1->2 |
| 60 Act 2 - Tomb 2 Treasure | expansion/dystopic/desertpeak | - | SizeX 200->127, SizeY 200->127, DrlgType 1->2 |
| 65 Act 2 - Sewer 2 A | act2/arcane/belial | - | SizeX 200->47, SizeY 200->47, DrlgType 1->2, LevelType 13->19 |
| 84 Act 3 - Spider 1 | act3/kurast/excelsior3 | - | SizeX 200->50, SizeY 200->50, DrlgType 1->2, LevelType 23->22 |
| 90 Act 3 - Dungeon 1 Treasure | act3/jungle/dungrm6a | act3/jungle/dungrm1a, act3/jungle/dungrm2a, act3/jungle/dungrm3a, act3/jungle/dungrm4a, act3/jungle/dungrm5a, act3/jungle/dungrm6a | - |
| 95 Act 3 - Temple 2 | expansion/glados/glados | act3/temple/temple3, act3/temple/temple4 | SizeX 24->119, SizeY 24->119 |
| 98 Act 3 - Temple 5 | expansion/redsquare/moskvich | act3/temple/temple10, act3/temple/temple9 | - |
| 99 Act 3 - Temple 6 | act3/temple/temple10, act3/temple/temple11, act3/temple/temple12, act3/temple/temple9 | act3/temple/temple11, act3/temple/temple12 | - |
| 116 Act 5 - Ice Cave 2A | expansion/icecave/rockisdead | - | SizeX 32->64, SizeY 32->64, DrlgType 1->2 |
| 122 Act 5 - Temple 1 | - | - | SizeX 120->80, SizeY 120->80 |
| 123 Act 5 - Temple 2 | - | - | SizeX 120->80, SizeY 120->80 |
| 125 Act 5 - Hell 1 | expansion/voodoo/macumba | - | SizeX 200->63, SizeY 200->63, DrlgType 1->2, LevelType 35->33 |
| 126 Act 5 - Hell 2 | expansion/terror/borgir | - | SizeX 200->99, SizeY 200->99, DrlgType 1->2, LevelType 35->33 |
| 127 Act 5 - Hell 3 | expansion/zakarum/charismatic | - | SizeX 200->95, SizeY 200->95, DrlgType 1->2 |

### Raw MonStats rows the maps place (renumbered by tools/idmap.py)

| mod row | Id | D2R id (tools/idmap.py) | maps |
|---|---|---|---|
| 970 | quest_laser | 1067 | act3/jungle/dungrm6a |
| 998 | quest_overlord | 1095 | act1/cathedrl/inarius |
| 999 | quest_rogue1h | 1096 | act1/cathedrl/inarius |
| 1000 | quest_rogue2h | 1097 | act1/cathedrl/inarius |
| 1004 | quest_subordinate | 1101 | act2/arcane/belial |
| 1005 | quest_fleshdoom | 1102 | act2/arcane/belial |
| 1015 | super_cast3 | 1112 | act3/kurast/excelsior3 |
| 1025 | spawn_cast3 | 1122 | act3/kurast/excelsior3 |
| 1031 | quest_malic | 1128 | expansion/icecave/rockisdead |
| 1038 | quest_lightwells | 1135 | expansion/zakarum/charismatic |
| 1083 | goldencalf | 805 | expansion/dystopic/desertpeak |
| 1084 | karcheuspriestess | 806 | expansion/dystopic/desertpeak |
| 1085 | hefaetruspriestess | 807 | expansion/dystopic/desertpeak |
| 1088 | karcheushimself | 1177 | expansion/dystopic/desertpeak |
| 1089 | hefaetrusturret | 1178 | expansion/dystopic/desertpeak, expansion/ghetto/cypherpunk |
| 1090 | idleredlight | 1179 | expansion/dystopic/desertpeak |
| 1091 | idlegreenlight | 1180 | expansion/ghetto/cypherpunk |
| 1095 | neonfiend | 1183 | expansion/ghetto/cypherpunk |
| 1096 | r_alpha | 1184 | expansion/ghetto/cypherpunk |
| 1097 | r_beta | 1185 | expansion/ghetto/cypherpunk |
| 1098 | r_gamma | 1186 | expansion/ghetto/cypherpunk |
| 1099 | r_delta | 1187 | expansion/ghetto/cypherpunk |
| 1100 | r_epsilon | 1188 | expansion/dystopic/desertpeak |
| 1226 | toraja_celebrant | 1300 | expansion/voodoo/macumba |
| 1227 | toraja_morlufiend | 1301 | expansion/voodoo/macumba |
| 1246 | empty_undeadmage4 | 1314 | expansion/terror/borgir |
| 1247 | darkstardragon | 1315 | expansion/terror/borgir |
| 1612 | orkshaman | 1640 | expansion/morework/epicwhiners |
| 1629 | combatdrone2 | 1655 | expansion/glados/glados |
| 1630 | mcsboss | 1656 | expansion/glados/glados |
| 1631 | sentinelchain | 1657 | expansion/glados/glados |
| 1632 | sentineldrone1 | 1658 | expansion/glados/glados |
| 1633 | sentineldrone2 | 1659 | expansion/glados/glados |
| 1634 | sentinelcube1 | 1660 | expansion/glados/glados |
| 1635 | sentinelcube2 | 1661 | expansion/glados/glados |
| 1636 | sentinelmines | 1662 | expansion/glados/glados |
| 1637 | sentinelmirv | 1663 | expansion/glados/glados |
| 1640 | sentinelwelcome | 1666 | expansion/glados/glados |
| 1641 | sentinelcore | 1667 | expansion/glados/glados |

### Audit

| severity | finding |
|---|---|
| WARN | expansion/zakarum/charismatic.ds1: header act 4, but its levels are act 5 (D2R resolves objects/monster rows by the header act; 9 object ids resolve to another class in the level's act) |
| INFO | superuniques from row 43 up (41 rows) sit one id above vanilla as Median ran them; no .ds1 holds a superunique id (monpreset Place names them by key), D2R quest code that tests ids must be game-checked |

<!-- maps_hd:end -->
