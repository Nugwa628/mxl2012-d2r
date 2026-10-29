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

## Walls of the 8 retextured maps (lane walls, 2026-10-29)

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
   orientations 1-9 get one; downtown's 126 Harrogath cells of orientation 14 (a tree/object slot, not a wall) stay without.
6. **Cap** (bug #360 open, asset cache overflow). No generated scene goes above D2R's largest map scene, `act3/docktown/
   docktown3` (4,989 entities, 4,423 of them with a model, 679 distinct models, 4,651,080 bytes): `cap()` keeps at most 4,423
   placed models and 4,651,080 bytes. It drops props first, then details on walls (buttresses, pillars, arches, beams,
   stairs, gargoyles: `DETAIL`), the walls, cliffs and fences that close rooms (`SIGHT`) last; inside a tier every model
   loses the same share, thinned evenly over the map (`spread`), not cut by region. Only cypherpunk reaches it (5,825 placed:
   1,402 dropped, all 1,802 elevation walls kept).

Size: the 8 scenes are 10.2 MB of JSON together (before wallsfix 10.9 MB); the largest is cypherpunk, 4,423 placed models,
3.29 MB, 33 distinct models (before: 5,820, 4.31 MB, 42). They name only D2R's own models, no new textures.

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

| map | biome | wall cells | exact | partial | generic | no D2R model | uncovered | set pieces left out | placed | capped | models in scene | distinct models | scene size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| expansion/dystopic/desertpeak.ds1 | act3_docktown | 2692 | 2384 | 306 | 2 | 1016 | 0 | 22 | 2790 | 0 | 2790 | 24 | 2153 KB |
| expansion/ghetto/cypherpunk.ds1 | act3_docktown | 3983 | 3218 | 760 | 5 | 1121 | 0 | 19 | 5825 | 1402 | 4423 | 33 | 3370 KB |
| expansion/glados/glados.ds1 | mxl2012_act4_mesa | 832 | 436 | 395 | 0 | 445 | 1 | 53 | 850 | 0 | 850 | 22 | 656 KB |
| expansion/neonmile/downtown.ds1 | mxl2012_act4_mesa | 3278 | 2203 | 693 | 256 | 797 | 126 | 4 | 2362 | 0 | 2362 | 12 | 1760 KB |
| expansion/redsquare/moskvich.ds1 | mxl2012_act4_mesa | 212 | 74 | 126 | 11 | 50 | 1 | 2 | 364 | 0 | 364 | 52 | 277 KB |
| expansion/terror/borgir.ds1 | mxl2012_act4_fort | 734 | 418 | 312 | 3 | 37 | 1 | 1 | 2074 | 0 | 2074 | 43 | 1605 KB |
| expansion/voodoo/macumba.ds1 | mxl2012_act4_fort | 405 | 356 | 20 | 28 | 18 | 1 | 38 | 561 | 0 | 561 | 15 | 431 KB |
| expansion/zakarum/charismatic.ds1 | mxl2012_act4_fort | 568 | 143 | 402 | 22 | 366 | 1 | 87 | 228 | 0 | 228 | 9 | 171 KB |
| all | | 12704 | 9232 | 3014 | 327 | 3850 | 131 | 226 | 15054 | 1402 | 13652 | | 10423 KB |

Learnt from 1063 D2R maps (92406 wall cells, 3455 distinct cell keys, 12437 variants). *exact*: the cell's wall tiles were seen together in a D2R map; *partial*: the variant of a learnt key that shares a tile; *generic*: a wall tile D2R never has in a scene gets D2R's most common wall of the same orientation in the same tile set or act (Library.generic_pick); *no D2R model*: D2R draws that tile without an entity (part of a map's baked terrain or nothing); *uncovered*: no wall drawn in HD (not a wall orientation, or no learnt wall of that orientation); *set pieces*: models D2R places on fewer than 3 wall cells (Library.set_piece); *capped*: pieces cap() dropped to stay within D2R's largest scene (docktown3: 4423 placed models, 4.44 MB).

Self-check (D2R's own maps, `self_check`): the scenes this method makes for 40 of the learnt D2R maps have 945 of their 2203 wall entities (43%; same model within 1.5 units).

<!-- walls_hd:end -->

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

Not done: building a scene for a generated or custom-art map beyond the minimal one, any game run, the HD textures. Gaps are in
`docs/unported.md` (section Maps).

## Generated tables

Refresh: `py -3 -I tools/maps_hd.py docs`. Needs the extract and the D2R 93847 baseline extract (`filelist.txt`, tables, tiles).

<!-- maps_hd:begin (generated: py -3 -I tools/maps_hd.py docs) -->

### Maps (34 .ds1)

| map | levels (lvlprest -> levels.txt) | size | kind | plan | scene / biome | conf. | art needed for walls/buildings |
|---|---|---|---|---|---|---|---|
| act1/cathedrl/cathy3.ds1 | 33 Act 1 - Cathedral | 29x35 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act1/cathedrl/inarius.ds1 | 14 Act 1 - Cave 3 Treasure | 29x35 | Median map | minimal scene | act1_cathedral | medium | missing in HD: all 110 wall cells are stock tiles, a generated scene (stage 2) can use stock wall models |
| act1/caves/caveroom4.ds1 | 15 Act 1 - Cave 4 Treasure | 25x25 | D2R map, edited by Median | minimal scene | act1_caves | medium | missing in HD (D2R scene dropped: layout changed); stock tiles, generatable |
| act1/caves/caveroom5.ds1 | 16 Act 1 - Cave 5 Treasure | 25x25 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act1/outdoors/bivouac.ds1 | preset rows: Act 1 - Bivouac | 17x17 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act2/arcane/belial.ds1 | 65 Act 2 - Sewer 2 A | 48x48 | Median map | minimal scene | act2_arcane | medium | missing in HD: all 81 wall cells are stock tiles, a generated scene (stage 2) can use stock wall models |
| act2/maggot/magqueen.ds1 | preset rows: Act 2 - Lair Tight Spot S | 11x11 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act2/palace/harem2.ds1 | 50 Act 2 - Harem | 17x20 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act2/tomb/duriel.ds1 | 73 Act 2 - Duriel's Lair | 33x48 | D2R map, edited by Median | D2R scene | D2R scene | high | none (D2R's scene) |
| act3/jungle/dungrm6a.ds1 | 90 Act 3 - Dungeon 1 Treasure | 41x41 | D2R map, edited by Median | minimal scene | act3_jungle (level type: act3_jungle_dungeon) | medium | missing in HD (D2R scene dropped: layout changed); stock tiles, generatable |
| act3/kurast/excelsior3.ds1 | 84 Act 3 - Spider 1 | 51x51 | Median map | minimal scene | act3_kurast | medium | missing in HD: all 1199 wall cells are stock tiles, a generated scene (stage 2) can use stock wall models |
| act3/temple/temple5.ds1 | 96 Act 3 - Temple 3 | 25x25 | D2R map, edited by Median | minimal scene | act3_kurast | medium | missing in HD (D2R scene dropped: layout changed); stock tiles, generatable |
| act3/temple/temple6.ds1 | 96 Act 3 - Temple 3 | 25x25 | D2R map, edited by Median | minimal scene | act3_kurast | medium | missing in HD (D2R scene dropped: layout changed); stock tiles, generatable |
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
| expansion/dystopic/desertpeak.ds1 | 60 Act 2 - Tomb 2 Treasure | 128x128 | Median map | minimal scene | act3_docktown (level type: act2_tomb) | medium | missing in HD: stand-in tiles are stock act3/docktown, act3/jungle, act3/kurast, act4/fort; Median's re-textured look needs custom art (2697 of 2992 wall cells on new .dt1) |
| expansion/ghetto/cypherpunk.ds1 | 59 Act 2 - Tomb 1 Treasure | 128x128 | Median map | minimal scene | act3_docktown (level type: act2_tomb) | medium | missing in HD: stand-in tiles are stock act3/docktown, act3/jungle, act3/kurast, act4/fort; Median's re-textured look needs custom art (4691 of 5228 wall cells on new .dt1) |
| expansion/glados/glados.ds1 | 95 Act 3 - Temple 2 | 120x120 | Median map | minimal scene | act4_mesa (level type: act3_kurast) | medium | missing in HD: stand-in tiles are stock act4/fort, act4/mesa; Median's re-textured look needs custom art (200 of 1038 wall cells on new .dt1) |
| expansion/icecave/rockisdead.ds1 | 116 Act 5 - Ice Cave 2A | 65x65 | Median map | minimal scene | expansion_icecave | medium | missing in HD: all 52 wall cells are stock tiles, a generated scene (stage 2) can use stock wall models |
| expansion/morework/epicwhiners.ds1 | 13 Act 1 - Cave 2 Treasure | 120x120 | Median map | minimal scene | act1_caves (level type: act1_cathedral) | medium | missing in HD: all 1735 wall cells are stock tiles, a generated scene (stage 2) can use stock wall models |
| expansion/neonmile/downtown.ds1 | 18 Act 1 - Crypt 1 A | 251x251 | Median map | minimal scene | act4_mesa (level type: act1_crypt) | medium | missing in HD: stand-in tiles are stock act3/travincal, act4/fort, act4/mesa, expansion/town; Median's re-textured look needs custom art (2002 of 3493 wall cells on new .dt1) |
| expansion/redsquare/moskvich.ds1 | 98 Act 3 - Temple 5 | 25x25 | Median map | minimal scene | act4_mesa (level type: act3_kurast) | medium | missing in HD: stand-in tiles are stock act4/fort, act4/mesa; Median's re-textured look needs custom art (82 of 393 wall cells on new .dt1) |
| expansion/terror/borgir.ds1 | 126 Act 5 - Hell 2 | 100x100 | Median map | minimal scene | act4_fort (level type: expansion_icecave) | medium | missing in HD: stand-in tiles are stock act3/jungle, act3/kurast, act4/fort; Median's re-textured look needs custom art (1306 of 1315 wall cells on new .dt1) |
| expansion/town/townwest.ds1 | 109 Act 5 - Town | 41x41 | D2R map, unchanged | D2R scene | D2R scene | exact | none (D2R's scene) |
| expansion/voodoo/macumba.ds1 | 125 Act 5 - Hell 1 | 64x64 | Median map | minimal scene | act4_fort (level type: expansion_icecave) | medium | missing in HD: stand-in tiles are stock act1/graveyard, act3/kurast, act4/fort; Median's re-textured look needs custom art (421 of 429 wall cells on new .dt1) |
| expansion/zakarum/charismatic.ds1 | 127 Act 5 - Hell 3 | 96x96 | Median map | minimal scene | act4_fort (level type: act4_lava) | medium | missing in HD: stand-in tiles are stock act4/fort; Median's re-textured look needs custom art (870 of 871 wall cells on new .dt1) |

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
