# Legacy maps to HD: what works, what does not, and the way on (lane hdmaps, 2026-11-11)

Goal (owner): convert a legacy Median XL map into an HD map a player could not tell from a hand-built D2R map.

**Result in one paragraph.** The proof map, Fauztinville (`cypherpunk`, level 59), does **not** meet the goal. The method
below was run on it end to end and the result is better than the shipped scene in one respect (the ground is stone paving
where legacy has roads and pavements, no longer dirt), but a player sees at once that it is not legacy's city: legacy shows
wide stairs and terraces at several heights, lit red and blue, in a black void; HD shows flat paving with low wall pieces
and short stair flights standing on it. The cause is not a tuning problem. Fauztinville is hand-built: no part of it is a
copy of a D2R map, so there is no D2R scene to take, and its look is made of height, which the engine's flat ground plane
cannot show. What it would take is in [What Fauztinville needs](#what-fauztinville-needs). For the maps that *are* built
from D2R maps the method does reach the goal: Azmodan's Reliquary (`temple5`) is D2R's own scene, whole.

Working notes, scenes and captures: `mxl2012-runs/hdmaps/` (paths below are relative to it unless they start with
`tools/` or `docs/`).

## Diagnosis

### What a hand-made D2R map has

D2R draws a map in HD from `data/hd/env/preset/<ds1 path>.json`; the .ds1 and its .dt1 tiles keep doing the gameplay
(walkable area, line of sight). A stock preset is far more than walls. `act1/cathedrl/cathy3`: 1,377 entities, of which
953 models, 444 wall-transparency volumes, 440 physics bodies, 142 effects, 97 prefab placements, 89 decals, 34 terrain
decals, 7 terrain stamps, plus lights, fade targets and visual-data boxes (`study/preset_stats.py`). And one more thing no
entity list shows: **a terrain mesh modelled by hand for that preset** (`preset/<path>/terrain.model`, painted by a biome,
with its own floor physics). Travincal's is 877 vertices with ground from 7.5 below to 14.7 above zero: the causeways,
pits and stairs are the terrain, the entities stand on it.

Relation to the .ds1: floors are not entities (the terrain mesh, or the engine's ground plane painted per cell by a biome's
texture layers); a wall tile is usually one model on its cell, often with a transparency volume; props, lights, decals and
effects have no tile at all; collision stays in the .dt1 sub-tile flags, the scene's physics is for the camera, for fading
and for the height units stand at. The camera is orthographic, 30 degrees above the ground along the tile
diagonal, so its axis is (-s, -1, -s) with s = sqrt(1.5) = 1.2247: a piece on ground raised by g stands at
(x + s·g, y + g, z + s·g) to show over its tile, and one unit of height is 14.7 px on the screen where one unit along x
or z is (12, 6) px. D2R's terrace step of 4.899 is a slide of 6 units. (An earlier version of this page said (-1, -1, -1);
measured wrong, a piece raised by 18.2 stood 50 px too high.)

### What our conversion has

The shipped pipeline (`tools/walls_hd.py`, `tools/walls_scene.py`) learns "this wall tile -> this model" cell by cell from
D2R's maps and places one piece per wall cell on the flat ground plane. So a converted map has walls (and flat
sprites of the legacy art where no model fits) and little else: no terrain, no dressing, no lights, a biome voted by tile
folder with at most two more as per-tile overrides. The pictures (current HD left, legacy right):
`diagnosis/desertpeak_walljoins.jpg`, `diagnosis/cypherpunk_0.jpg`, `diagnosis/temple5_0.jpg`,
`diagnosis/excelsior3_0.jpg`, `diagnosis/epicwhiners_0.jpg`, `diagnosis/downtown_0.jpg`.

Three findings explain most of the gap:

1. **The pipeline never asked where a Median map came from.** Many are D2R maps, edited. `tools/maps_transplant.py survey`
   finds the regions of a Median map that are tile-for-tile copies of a D2R map at an offset. Two maps are a D2R map whole,
   six more are 33-74% copies by wall cells, nine have nothing (table in [The 17 maps](#the-17-maps)).
2. **Floor paint follows the tile's folder, not the tile.** Fauztinville's biome was voted "Kurast docks dirt" by its 5,095
   most common floor cells, which are black tiles: the void. Its roads were painted with Kurast's biome because their tiles
   sit in Kurast's folder, while D2R itself paints those terrace tiles with Travincal's paving. The legacy floor per cell:
   `study/floor_cypherpunk.png` (dark roads, light pavements, black void: a street grid).
3. **Height is drawn as wall pieces on flat ground.** Legacy fakes height in the tile art; D2R models it in the terrain.
   We have neither, so stairs and terraces come out as pieces lying on a plane.

## Options

| option | reach | cost | risk |
|-|-|-|-|
| A. D2R's scene whole, where the Median map is a D2R map | 2 maps (`temple5`, `temple6`) | none, tool done | none seen; proven in game |
| B. Region transplant: every entity D2R placed on a copied region, moved to the Median map; D2R's terrain mesh as a piece where the region is most of its map | 33-74% of the wall cells of 6 maps | tool done; per map a game check | seams between regions; a sunken or raised region needs its terrain piece |
| C. Floor paint from the legacy tile (black = void, else the biome D2R paints that tile with) | every floor cell of every map | tool done | at most 2 override biomes in view (engine assert); the void is dark ground, not black |
| D. Layout transplant: regions matched on walls alone, floors the mapper's own | Fauztinville: 11% of wall cells | tool done | D2R dressing on a floor it was not made for |
| E. Generated terrain from the legacy heights, ground plane skipped on the level, stairs and walls standing on it | the 9 hand-built maps | terrain generator, a plugin part per level, model index entries; days per map family, then automatic | needs the owner's rule "no new 3D models" lifted for terrain; a generated terrain was never drawn so far (see open questions) |
| F. Per-cell learnt walls on flat ground (shipped) | all 17 | none | known result: not close to hand-built |
| G. Authoring each map by hand in an editor | all | weeks per map | not a conversion method |

**Recommended:** A and B wherever a map has D2R provenance, C on every map, D where it finds something, F only as the
filler for cells nothing else covers. E is the only option that can bring a hand-built map such as Fauztinville to the
goal; it is engine work and an owner decision, not a tuning step. C and D as built cost frame rate on Fauztinville
(below), so neither ships there before the cause is known (open question 5).

## Proof on Fauztinville

### What was built

`py -3 -I tools/maps_transplant.py build cypherpunk --layout 8 --paint --fallback <shipped scene> --out fz/f1`
(with `MXL_SLOT=2` so D2R files missing from the extract are read from the slot's CASC into the shared cache).

| step | result |
|-|-|
| copied regions (walls and floors equal) | 0 of 3,983 wall cells: nothing in Fauztinville is a copy of a D2R map |
| layout regions (walls equal, floors ignored, 8+ wall cells, void cells left out) | 34 regions, all from Travincal (`travs`, `travse`, `travn`, `travne`): 1,685 cells, 428 wall cells (11%), 2,771 D2R entities taken |
| floor paint | 5,095 black cells = void; 4,530 cells Travincal paving (legacy brightness 31: the roads), 2,678 cells Fortress stone (legacy brightness 106: the pavements), 389 of them under walls |
| void | the scene's biome with D2R's darkest ground (`act4_lava_volcanic_dirt01`, mean colour 11, 10, 10) as base layer |
| everything else | the shipped composed scene's pieces (7,561 of its 8,620 kept) |
| scene | 10,332 entities, 9,349 with a model, 606 distinct models, 11.2 MB (shipped: 8,620 entities, 126 distinct models, 8.0 MB) |

Scene and biome: `fz/f1/`. Run `checks-20261111-161039-s2` (slot 2, `wall_maps`, slot restored byte-equal): the scene
loads, no crash file, and the only asserts are the five memory-pool asserts this check logs at game exit (the same five
as in this lane's earlier runs, `run-r3.log`).

### HD beside legacy

| spot | pair | what HD shows against legacy |
|-|-|-|
| arrival stair | `pairs/cypherpunk_0_f1.jpg` | legacy: one wide stair down to a lit landing, black around. HD: stone paving with several short stair flights standing apart on it, a low wall line; no descent |
| walkway crossing (cell 70, 49) | `pairs/cypherpunk_1_f1.jpg` | legacy: a ribbed platform edged with skull trim, in the void. HD: flat paving, low wall stubs in a ring, Travincal's flower decals; the platform does not read as raised |
| pavement (38, 57) | `pairs/cypherpunk_2_f1.jpg` | legacy: light pavement slabs, red and blue light, void below. HD: dark stone, low walls, no coloured light; pavement and road are hard to tell apart |
| inside the largest Travincal region (42, 55) | `pairs/cypherpunk_3_f1.jpg` | HD shows Travincal's own wall and trim along the road edge; the road itself is flat paving. Closest of the five, still not legacy's stepped street |
| south crossing (26, 100) | `pairs/cypherpunk_4_f1.jpg` | legacy: road crossing with lit pavement corners and red and blue walls. HD: paving, a low wall, dark |

Before and after at the same spots (HD shipped | HD converted | legacy): `pairs/three_cypherpunk_*.jpg`.

### Judgement

Not met. A player would not mistake any of the five views for a hand-built map, and three of the five would not be
recognised as the same place as legacy.

What gives it away, in order of weight:

1. **No height.** Stairs, terraces and platforms are flat paving with pieces on it. This is most of Fauztinville.
2. **No light.** Legacy's look is red and blue light on stone; the HD scene has no light entity of its own, so it is evenly
   dim. Only the 34 Travincal regions bring D2R lights and effects.
3. **Walls.** 89% of the wall cells are still per-cell learnt pieces: low, repeated, not joined into buildings.
4. **The void is ground.** It is D2R's darkest ground texture, so it reads as dark rock near the player, not as nothing.
5. **Paint is two textures.** Roads and pavements differ in legacy by a strong brightness step; in HD both are dark stone
   under the map's tint. The engine allows two override biomes in view, so courtyards share the road's paving.
6. **Dressing only where Travincal's layout was found** (21% of the cells that are not void).

What got better against the shipped scene is small: stone instead of dirt and grass at the arrival and wherever the old
vote had left the scene's dirt biome, the void no longer voted as the map's ground, and D2R's own trims, decals and
effects in the Travincal regions. At the walkway crossing the two HD scenes are nearly the same picture
(`pairs/three_cypherpunk_1.jpg`).

### The piece budget

The method does not lower Fauztinville's piece count, it raises it: 10,332 entities against 8,620, and 606 distinct models
against 126 (D2R's model cache holds 2,750, the plugin raises it to 8,250). The shipped budget (`walls_hd.MAP_LIMITS`,
8,620 pieces and 7,999,943 bytes) is the project's own policy, not an engine limit, and this run confirms it once more: a
scene of 11.2 MB loads. Frame rate at the five spots, read from the captures (monsters crowd the player in every shot, so
the numbers compare runs only roughly; strip of the overlays: `pairs/fps_f0_f1.png`, shipped left):

| scene | arrival | 70, 49 | 38, 57 | 42, 55 | 26, 100 |
|-|-|-|-|-|-|
| converted, HD | 51.9 | 43.5 | 32.9 | 23.5 | 36.8 |
| shipped, HD (run `checks-20261111-162254-s2`) | 60.0 | 60.0 | 43.1 | 37.1 | 49.3 |
| legacy (same run as converted) | 56.4 | 51.0 | 43.5 | 38.4 | 47.8 |

The converted scene costs 8 to 17 frames per second at every spot (14-37%), so as built it is not shippable on this
map even before the look is judged. Memory was not measured in this run. The figure of 17,700 wanted pieces in the lane brief is not in `docs/maps-hd.md`
(which lists the shipped scene as 8,620 placed, 0 capped) and was not re-measured here; props stay as they are in the
shipped scene. A real answer to the budget is option E: D2R's own Travincal carries its look in one terrain mesh of 877
vertices plus about 2,300 entities per 33 x 33 cells, where we spend up to two wall pieces per cell to fake height.

### What Fauztinville needs

1. A terrain for the map: floor polygons at the heights legacy implies (`walls_hd.median_heights` already derives them from
   the wall tiles), stairs as ramps under D2R's stair models, painted by the biomes of the floor paint. This is a generated
   .model, which the owner's rule against new 3D models excludes today; the mod already generates sprite models
   (`tools/walls_sprite.py`), so the rule would need the same exception for terrain.
2. The engine's ground plane skipped on level 59, as plugin part `void65` does for levels 74 and 65
   (`docs/maps-hd.md`, lane tunnelfloor): that makes the void black and lets the terrain be the floor.
3. Lights: one D2R light entity per legacy light source, coloured from the legacy tile art around it.
4. Walls placed as runs, not cells: where Travincal's layout was found D2R's own run is used; the same matching on shorter
   runs (4+ wall cells reaches 19% of the wall cells) with the joints closed by the existing join pieces.

Items 1 and 2 were then tried as a pair on one terrace (the owner allowed generated models for terrain only): next section.

## Generated terrain: one terrace

**Superseded by the owner's ruling of 2026-11-12** (classic Median maps are flat; stairs are floor art; see
[Flat maps](#flat-maps-owner-ruling-2026-11-12)). Raised terrain is not the direction and is not extended; the tool
(`tools/maps_terrain.py`) and this record stay.

A small trial, on top of the conversion above: Fauztinville's arrival (cells x 44..77, rows up to 46) as generated ground.
Nothing of it ships; the files are in the notes folder (`terrace/build_terrace.py`, runs `d4`, `d6`, `d7`).

### The route that draws

A generated mesh with D2R's terrain material draws and is painted when it is a **plain entity**:

- The model is one of D2R's own `terrain_lod0.model` files with its mesh replaced (`tools/maps_terrain.py`, the smallest
  donor the mesh fits in, padded to the donor's vertex and index counts), stored as
  `hd/env/model/mxl/terrain/<name>_lod0.model`, with a `hd/model_lod_desc.bin` entry copied from the donor (+44 bytes).
- The entity has a transform and a model component (visible layer 1, terrain blend mode 1) and no terrain component;
  model and floor body are named in the scene's dependencies.
- It is painted by the biomes of the floor tiles under it (the per-tile overrides apply, blood decals lie on it), lit by
  its normals, receives shadows and hides what is behind it.
- With a generated `.physics` floor body, player, minions and monsters stand on it. Without one a raised quad hides the
  player under it (control quad in run `d1`).
- The engine's ground plane must be off on the level, or it shows through beside the terrain: a test build of the plugin
  with level 59 in `void65`'s skip list was used (`terrace/mxl2012-core-skip59.dll`, not committed). With it the void is
  black and all ground is generated: one flat model for the 6,222 floor cells outside the terrace, one for the terrace.

### What the terrace shows

Sheets of (a) legacy, (b) shipped scene, (c) conversion, (d) terrace at three spots: `terrace/terrace_spot0..2.png`, the
same with dark levels raised `..._bright.png`, the walk legs `terrace/terrace_walks.png`.

- The rows north of row 43 stand 19.6 units (4 terrace steps) above the road; the fine stair (legacy tile 31.23, 2 cells
  wide) is 16 real steps with treads and risers where (b) and (c) show rows of slab pieces lying on flat ground.
- Walls, column, gate and props of the upper level stand on it at the pixels (c) has them: all 1,668 pieces of the
  terrace were raised by the height under them, the 25 stair pieces on the band left out.
- Walkable area: collision is the .ds1's and is untouched. On foot the player goes up the stair (cell 67,47 to 67,42) and
  down again, and is stopped at the wall when sent from cell 74,45 toward the void; the same in legacy
  (`checks-20261111-194113-s3`). He is drawn on the steps and on the upper level, not under them.
- No assert in any run.

### What still gives it away

1. **The stair lies in shadow.** The level's sun stands in the north at 45 degrees (`keyLightShadowPitchDeg`, the vis file
   is a copy of D2R's act 3 docks). A stair at the height legacy implies (one terrace step per cell) is a 51 degree slope
   that is high in the north: the walls on top throw their shadow down all of it and the risers face away from the sun.
   At half the height (`d5`; `terrace/terrace_full_half.png`, full height left, half right) the sun reaches the treads and
   the stair reads clearly, but the upper level is then half as high as legacy draws it.
   A light of its own per map (need 3 of the list above) or a sun turned for the level would be the cure; not tried.
2. **Beside the fine stair the band is a bare slope.** Legacy draws stair art on all of the band; only the two cells of
   tile 31.23 were made steps, the road cells are a 51 degree ramp shaded as flat ground.
3. **Legacy's heights do not agree with each other.** The band's road tiles (31.14, 31.15) are stair art that is high in
   the south, next to the fine stair that is high in the north. The upper level was taken as north because the fine
   stair's risers face the camera. A whole map needs such a ruling per stair run, by rule or by hand.
4. Everything outside the terrace is still (c): flat, slab pieces as stairs (the field at cells 69..74, 48..50 is in the
   same views), per-cell walls, no lights.

### Cost

Frame rate (10 s average of the game's overlay) at the three spots, slot 3, other lanes' clients running:

| scene | arrival | below the terrace | top of the stair |
|-|-|-|-|
| (b) shipped | 59.8 | 60.0 | 60.0 |
| (c) conversion | 54.3 | 52.1 | 50.7 |
| (d) terrace, run `d4` | 53.6 | 50.0 | 47.8 |
| (d) terrace, run `d6` | 53.7 | 51.0 | 49.4 |

So 0 to 3 fps for the generated ground on top of the 6 to 10 the conversion costs. Private memory per view is within
the spread between runs ((c) 9,915 / 9,572 / 9,577 MB, (d) 9,935 / 9,620 / 9,623 MB). Files: floor model 351,380 B
(6,889 vertices), terrace model 235,504 B (1,309 vertices, in a 6,561-vertex donor), floor body 113,328 B, model index
+88 B, scene 11.20 MB against (c)'s 11.22 MB.

### What the whole map and the other eight hand-built maps would take

Not started; the owner decides after the images.

- A height per cell for each map. `walls_hd.median_heights` gives heights from wall tiles; stairs give a direction per
  tile (31.23, 31.20, 31.4 high in the north; 31.26, 31.21 west; 31.12 east; 31.14, 31.15 south; 31.13 unknown), and
  Median uses them as decoration as well, so every map needs rulings (item 3 above) and a person to look at each area.
- Ground models per map, split to fit the donors (largest D2R donor: 20,716 vertices, 114,051 indices; Fauztinville's flat
  floor alone is 6,889 vertices), floor bodies for raised parts, every piece raised by the same height function, stair
  pieces removed where the terrain is the stair.
- The plugin's `void65` skip list extended by each map's level (a plugin build and its own checks).
- Lighting per level, or north-high stairs stay dark (item 1).
- Checks per map: `MXL_WALL_WALK` legs over every stair and toward the void, frame rate at the arrival, no new assert.
- It does not touch what else separates (c) from D2R's own maps: walls as runs, lights, paint (judgement above).

## Flat maps (owner ruling 2026-11-12)

The owner's ruling: the classic map has no real stairs. The whole level looks flat, and its stairs only serve to look like
walkways and streets. The protrusions in the HD conversion (pillars, benches and the like) are not supposed to exist.
Every classic Median map is almost entirely 2D except for its walls.

### The rule

Every classic tile kind of a map gets a verdict: **wall** (stands up) or **flat** (painted on the floor). Kinds that are
in doubt get **unsure**, which is built as flat. The verdict comes from the tile itself (`tools/maps_flat.py`, `rule`):

- Floor tiles are always flat. Stair, kerb and step art (Kurast styles 30 and 31) and floor tiles that block all 25
  sub-tiles are painted with their classic picture. The void tile is painted black. Every other floor keeps the HD
  biome paint the conversion already has.
- A wall-layer tile is a wall when its picture reaches 120 px or more above its cell's centre (a classic wall is about
  one cell high). Under 70 px it is flat art; this covers the low kerbs and edge ridges of style 31, which reach 51 to 66 px.
  From 70 to 119 px it is a wall when it is a wall piece proper (orientation 1 to 9) and blocks at least one sub-tile
  (ruined docktown walls at 115 px, graveyard fences, fort and monastery hedges), and unsure when it blocks nothing (the
  see-through tomb railings). Props and trees (orientation 12 and 14) in that band stand when they block a sub-tile and are
  flat art when they block nothing (ferns, spikes); from 120 px they stand like any wall, so trees stay walls.
  Wall-layer pieces of the Kurast step sets (30, 31) are flat art at any height, and a wall-layer
  key with no tile in the map's sets is not drawn. Roofs count as wall. Lower walls (the cliff faces into the void) are flat with no
  picture, so the void edge is only the black floor. Special tiles (orientation 10 and 11, doorways) with a picture are
  painted on the floor at their classic pixels, like stair art; without a picture they are unsure and not drawn.
- Single kinds that the rule gets wrong are corrected in the table: for example desertpeak's low stubs 1.4.10 and 4.4.1
  are walls because they block sub-tiles.
- Shadow tiles are flat and not drawn.
- Cave tile sets (`CAVE_SETS`, today `act1/caves`) draw their rock walls in the **floor** tiles: a cave floor that blocks
  sub-tiles is a **wall** (paint biome, or void when its picture is black), so the shipped scene's cave wall, fence and rock
  models on those cells stay. Without this Duncraig (`epicwhiners`) lost every cave wall: the floor verdicts made none of
  those cells a wall cell, and 243 of its pieces were dropped as clutter.
- Maps in `WHOLE_STRUCTURES` (today Duncraig) keep `walls_scene`'s composed structure pieces (`mxs_<n>`: gateways, wall
  junctions, facade runs) within `STRUCTURE_REACH` (2) cells of a wall cell, since their pivots lie up to 1.5 cells off the
  wall line; elsewhere the one-unit slack stands. On the other maps this would bring back pieces next to flat kinds, so it
  is per map.

The verdicts are a data file, `tools/data/flat_tiles.tsv`: one line per tile kind (map, orientation, main, sub, folder,
cells, rise in px, blocked sub-tiles, verdict, paint, reason). Correcting a kind is a one-line change; the next build reads
it. `py -3 -I tools/maps_flat.py table <map>` adds lines for new kinds only and keeps every line already there.

Fauztinville (`cypherpunk`): 148 kinds, **wall 75, flat 66, unsure 7**. The unsure kinds are the six railings
(1.16.0 to 1.16.5, about 100 px) and one special tile (11.0.4). Contact sheet (every kind's classic picture, its verdict
frame and the numbers behind it): `flat/tile-verdicts.png` and `flat/tile-verdicts.md` in the notes folder.

### What was built

`py -3 -I tools/maps_flat.py build cypherpunk <scene> <out> --lod-base <the mod's model_lod_desc.bin>` starts from the
slot's shipped 0.1.19 scene, not from the conversion (c). The shipped scene uses Kurast's own biome, keeps its tint and
holds fewer distinct models (84 against 190), and building from it ran faster in game (see Cost). The build:

- keeps solid entities (model, prefab, physics) only within one cell of a wall cell, so every pillar, bench, slab and
  stair piece standing on a street is gone (4,204 of 8,620 entities kept). Upright wall sprites of a kind whose verdict is
  flat (the shipped scene draws kerbs and edge ridges as standing sprites) are dropped as well, even next to a wall,
  because that kind is painted on the floor instead (`flat_sprite`);
- paints flat art as ground-level quads that land on the same screen pixels as in classic. Only the terrace floors that
  block sub-tiles (the kerbs and step edges of styles 30 and 31) and the low wall-layer kerbs keep their classic picture.
  The other stair and step floors of styles 30 and 31 (0.31.7, 10, 12 to 15, 23, 26 and 0.30.12, 15) now take the
  biome's HD street paving, like every other floor. The classic pictures are colour-matched to Kurast's HD stone path
  texture, their edges bled and upscaled 2x (Lanczos) into one 2.8 MB atlas, so they read as worn floor paint rather
  than faint diagonal stripes. That is 2,572 pictures;
- puts the painted quads into 16 x 16 cell chunks of at most 38 quads, one model per chunk (the donor model's smallest
  level of detail holds 38 quads), with the lift along the camera's axis baked into the vertices: 104 painted models
  in all, one entity each, instead of one entity per quad;
- covers the void with opaque black quads (107 rectangles over 5,010 void cells), each 0.02 units wider than its cells
  so no seam shows. The material is pure black albedo with no roughness or metal response, so the player's light does
  not lift it. A void cell is one whose floors are all void and that holds no wall; kerb art on the void edge is still
  painted over the black. Biome overrides, decals and effects on void cells are removed;
- removes fog everywhere. Leaves stay off the void, other effects only near walls;
- leaves walls as the shipped scene has them and keeps the walkable area exactly as classic. Collision is the .ds1's,
  and no physics body remains.

When the input is the conversion scene, the build also swaps its biome `act3_travincal_outdoors` for `act3_kurast`
(`FLAT_BIOMES`), the cause of most of the darkness below.

Nothing is raised. Painted pieces sit at most 0.27 units above the floor (a wall is about 5 units high), and each one is
moved along the camera's axis so it stays on its pixels. No terrain model is generated, and the engine's own ground
plane stays as the floor under the paint, so the ground-plane test plugin (`terrace/mxl2012-core-skip59.dll`) is **not
needed** for flat maps.

Unit tests (`tools/tests/test_maps_flat.py`, 28): the rule (terrace floors that block sub-tiles are art, the others
biome), the table round trip, the scene (only walls stand, no geometry above the floor except walls, fog dropped and
leaves kept, the biome swap, one entity per painted model, physics only on walls), upright sprites of flat kinds dropped,
the void cells (a kerb on the void is still painted, a wall excludes its cell), the chunk limits, chunked art landing on
its classic pixels, void quads covering their cells, and the atlas colour and scale.

Checks on the real build (`flat/diag.py`): 0 solid pieces further than one cell from a wall cell, 0 painted pieces above
the paint height, 0 physics bodies.

### Why the earlier flat scene was darker

Three things made the first flat scene darker and muddier than the shipped one:

- the conversion's biome (`act3_travincal_outdoors`) and its tint paint the ground with darker layers: its first layer
  averages RGB 66,63,51 against 83,76,61 for Kurast's stone path, and its base layer is volcanic dirt (shipped: docktown
  dirt);
- the painted classic stair art covered large areas of the ground with the dim 8-bit picture instead of HD paint;
- the conversion's fog effects lay over the whole level.

With the shipped biome and tint, the stair floors back on HD paving and the fog removed, the mean brightness of the game
view (luminance 0 to 255, below the overlay) now matches the shipped scene where nothing moves: 11.7 against 11.6 at
68,44 and 10.7 against 10.6 at 67,42 (last round: 8.8 and 9.1). Where it is lower (72,68 and 40,53) the difference is the
sorceress's spell light in the shipped shots; at 81,57 it is the black void replacing the dark ground.

### What it looks like and what still gives it away

Seen in game on slot 5 (2026-11-12): before is the slot's shipped 0.1.19 scene (run
`checks-20261112-222045-s5`), after is the flat build with its models, atlas, void textures, model index and scene swapped in (run
`checks-20261112-230536-s5`); the slot was restored after each run. Every spot was cleared of monsters within 30 cells
and held for 11 s before the shot, with a fresh sorceress and no summons. Pairs at the same spots and camera, with last
round's flat scene as a third column: `flat/pairs-20261112-2319/` in the notes folder (`overview.png` stacks all of them).

- **Arrival (70,49 and 68,44).** The slab field and stair blocks are gone; the ground is HD Kurast paving and grass with
  the same brightness as the shipped scene. The kerb lines lie flat as worn paint. Nothing stands on the road.
- **Former stair (67,42).** The pillar and the walls behind it stay; the stair is HD paving, no stripes.
- **Streets (72,68 and 40,53).** No benches, slabs or kerb blocks. Street lamps still stand at 72,68 (walls by the rule).
  The building that classic shows to the upper left of 72,68 is not drawn: the roofs (609 wall cells without a piece) are
  out of scope for this round.
- **Void edge (81,57).** The road ends at the painted kerb and then pure black. A few small grass and debris specks still
  show on the black (not checked yet whether they are biome scatter or remaining decals).

Walk legs (identical in every run, shipped and flat): over the former stair 67,47 to 67,42 the player gets there; across
the former slab field 69,49 to 74,49 the player gets there; toward the void 81,56 to 81,60 the player stops at cell 80,57,
on the road's visible edge, as in classic. Nowhere was the player stopped where nothing looks solid.

Still to judge (owner): roofs not drawn, and whether the flat kerb paint reads well enough.

### Cost

Files: scene 4.75 MB (the shipped one is 8.00 MB), 104 painted models (5 levels of detail each, 22.0 MB), one 2.8 MB
atlas and two void textures: 24.8 MB of new files (last round 10.7 MB), while the scene shrinks by 3.25 MB. The painted models are padded to the donor model's size, about 32 KB per
level of detail. The model index gains 104 entries.

Frame rate (10 s mean of the game's overlay), slot 5, no monsters within 30 cells. Other clients were running on the
machine, so a run differs from the next by up to about 3 fps:

| spot | shipped 0.1.19 | flat, from the shipped scene | flat, from the conversion | last round |
|-|-|-|-|-|
| landing 68,44 | 60.0 | 60.0 | 59.4 | 51.6 |
| arrival 70,49 | 59.9 | 54.0 | 56.3 | 45.0 |
| former stair 67,42 | 60.0 | 57.6 | 57.3 | 49.1 |
| street 72,68 | 53.9 | 48.5 | 49.4 | 40.5 |
| street 40,53 | 46.8 | 49.4 | 39.8 | 36.5 |
| void edge 81,57 | 60.0 | 59.8 | 57.5 | 52.3 |
| slab field 74,49 (end of walk) | 60.0 | 59.8 | 51.2 | 49.4 |
| mean | 57.2 | 55.6 | 53.0 | 46.3 |

The frame is CPU-bound (at 74,49: CPU 14.9 ms shipped, 20.7 ms for the build from the conversion, 15.1 ms for the build
from the shipped scene; GPU under 7 ms). Chunking the painted quads into 104 models removed most of last round's cost.
The flat scene from the shipped scene is at the shipped rate at four spots, above it at 40,53 and 5 to 6 fps below it at
70,49 and 72,68. A build from the conversion without effects and decals was mixed (lower at four spots, higher at three), so
effects are not the main cost.

Harness options added to `tools/game_checks.py` for these runs: `MXL_WALL_CLEAR=1` kills monsters near each spot before
its shot (`MXL_WALL_KILL_RADIUS`, default 30 cells; `MXL_WALL_KILLS`, default 150), `MXL_WALL_SETTLE` holds the view
(default 11 s in HD) so the overlay's 10 s mean covers a still scene, and `MXL_WALL_MODES=hd` skips the classic visit
(the check then reports "reached in both: none", as expected).

### The other hand-built maps

The tool is map-agnostic. Each map needs:

- `table <map>`, then a person to look at its contact sheet and correct the doubtful kinds (on Fauztinville: 7 of 148);
- `build <map>` on its shipped scene (or its conversion scene where none is shipped);
- the in-game check per map: pairs at the arrival and at protrusion-rich spots, walk legs over former stairs and toward
  the void, frame rate at the arrival.

There are no per-stair height rulings, no generated terrain, no plugin change and no light per level. That removes most of
the cost listed for the terrace. The eight other hand-built maps (`epicwhiners`, `desertpeak`, `glados`, `downtown`,
`moskvich`, `borgir`, `macumba`, `charismatic`) use other tile sets, so the thresholds (120 / 70 px) and the art sets
(Kurast 30 and 31) must be checked on each one's sheet.

### Merge

Not merged and not shipped; the owner decides after the in-game pairs. Merging would change, for Fauztinville only:

- the scene `hd/env/preset/expansion/ghetto/cypherpunk.json` (replaced by the flat one);
- new files `hd/env/model/mxl/flat/cypherpunk/*` (104 models, 5 levels of detail each), `hd/env/texture/mxl/flat/cypherpunk_alb.texture`
  and the two void textures;
- 104 new entries in `hd/model_lod_desc.bin`;
- the build: `maps_flat.py build` on the shipped scene, reading `tools/data/flat_tiles.tsv`.

Collision, the .ds1, the plugin and the legacy graphics stay as they are. Whether the flat map is better than the shipped
0.1.19 scene can only be judged from the pairs. On paper it removes what made (b) and (c) wrong: pieces standing on
the roads, stair slabs as obstacles and cliff faces into the void. It also keeps everything that matches classic.

## What the other maps taught (short)

- **Azmodan's Reliquary (`temple5`, `temple6`)** is D2R's `act3/temple/temple3` with 2 cells changed. With D2R's scene taken
  whole it looks like a D2R temple: stone floor, stairs, walls, props, lights. `pairs/three_temple5_0.jpg` (shipped | whole
  scene | legacy), run `checks-20261111-141151-s2`. This is the goal met, by provenance.
- **Kurast 3000 BA (`excelsior3`)**, 67% copied from 15 D2R maps: flat regions read as stock Kurast, roof fading included.
  A sunken court is wrong when flattened; with D2R's terrain mesh placed as a plain entity (terrain component removed,
  model and floor physics kept, moved by the region's offset) it is drawn, painted by its own biome, and units stand on it,
  also when raised (`checks-20261111-143510-s2`, `pairs/excelsior3_*_r2.jpg`). Ground below zero shows when a terrain piece
  covers it. The owner judged this map a poor test; nothing more was done on it.

## The 17 maps

`py -3 -I tools/maps_transplant.py survey` (copied regions of 20+ cells or 6+ wall cells):

| map | wall cells | in copied regions | source | way |
|-|-|-|-|-|
| `temple5`, `temple6` | 134 | 100% | `act3/temple/temple3` whole | A: D2R's scene |
| `inarius` | 110 | 74% | 1 D2R map | B + C |
| `excelsior3` | 892 | 67% | 15 D2R maps | B + C |
| `rockisdead` | 51 | 65% | 4 D2R maps | B + C |
| `dungrm6a` | 475 | 50% | 2 D2R maps | B + C |
| `belial` | 78 | 35% | 3 D2R maps | B + C, rest as shipped |
| `caveroom4` | 3 | 33% (47% of all cells) | 1 D2R map | B + C |
| `epicwhiners` | 1,261 | 1% | 13 D2R maps | hand-built: C, D; E to reach the goal |
| `desertpeak`, `cypherpunk`, `glados`, `downtown`, `moskvich`, `borgir`, `macumba`, `charismatic` | 212 to 3,983 | 0% | none | hand-built: C, D; E to reach the goal |

Order of work: A and B maps first (each can be finished and judged on its own); C on all maps in the same build; the
hand-built maps wait for the owner's decision on E after the one Fauztinville terrace (next to the proof above).

What stays manual: the judgement of each map in game (HD beside legacy at the arrival and at spots chosen per map); the
choice per region when a mapper redrew part of a D2R pit (the tool refuses the terrain piece, a person decides whether the
flat result is acceptable); light colours where the tile art is ambiguous; any map a mapper built from nothing if E is
not approved.

## Tooling and checks

- `tools/maps_transplant.py`: `survey`; `build <map>` (whole scene, copied regions, `--layout N`, `--paint`, `--flat`);
  `walk <map> [scene]`; `calibrate`. Tests: `tools/tests/test_maps_transplant.py` (16).
- `tools/maps_floor.py`: legacy floor colour per cell, the biome D2R paints a tile with, the per-tile paint, the void
  biome. Tests: `tools/tests/test_maps_floor.py` (7).
- **Walkable area against drawn geometry** (`walk`): the .dt1 sub-tile flags give the walkable sub-tiles; every model's
  bounding box that is tall and thin enough to be a wall is rastered onto sub-tiles. Two numbers: *walk-through*, the share
  of walkable sub-tiles under a drawn wall (you walk through something solid), and *unseen*, the share of blocked wall
  sub-tiles with nothing drawn (you are stopped by nothing). `calibrate` runs the same on D2R's own maps for the scale:
  walk-through 0.9-4.3% there. Fauztinville: shipped scene 6.2% walk-through and 44% unseen, converted 7.0% and 29%, both
  outside D2R's range for walk-through, which fits what the pictures show (pieces standing on the roads). *Unseen* is not
  yet a gate: model boxes are missing for models whose `_lod0.model` is not in the extract or cache (D2R's own maps score
  1.6-52%), so read it only as a comparison between two scenes of one map.
- `tools/maps_terrain.py`: ground lifted along the camera's axis, stairs as treads and risers, the terrain model written
  into one of D2R's terrain models, the floor body file, the scene entity, pieces raised onto the ground, the model index
  entries. Tests: `tools/tests/test_maps_terrain.py` (8). Superseded by flat maps.
- `tools/maps_flat.py`: `table <map>` (verdict per tile kind into `tools/data/flat_tiles.tsv`), `sheet <map> OUT.png`
  (contact sheet), `build <map> SCENE OUT` (the flat scene, painted pieces, atlas, model index). Tests:
  `tools/tests/test_maps_flat.py` (28).
- Game check: `wall_maps` with `MXL_WALL_LEVELS` and `MXL_WALL_SPOTS`, HD and legacy at the same cells; with
  `MXL_WALL_WALK="59:67,47>67,42;74,45>80,45"` the player is put on the first cell of each leg and walks toward the
  second (monsters near him are killed first, a hit stops a walk). The scripts that swap a scene into a slot and restore
  it are `gamerun.sh`, `gamerun2.sh` and `terrace/gamerun3.sh` (also swaps the plugin) in the notes folder.
- Gates to add before any of this ships: walk-through within D2R's range per map; scene loads with no new assert; frame
  rate at the arrival not below the shipped scene's.

## Open engine questions

1. Answered: a generated terrain-material model draws and is painted when placed as a plain entity ("Generated terrain:
   one terrace"). A generated one declared as the scene's `terrain` never replaced the floor (belial); not tried again.
2. Units (player, minions, monsters) stand on a generated floor body; a raised terrain without one hides them. Still
   open for .ds1 objects: on a plate raised by 15 units only 2 of 5 legacy torches were visible, and the terrace run did
   not look at objects one by one.
3. Is a tile mask entry for a mod .dt1 path read? If yes, one biome could carry all of a map's ground textures and the
   two-biome limit would not matter.
4. Is a mod-shipped black ground texture safe? Every D2R terrain albedo is the same format and size (1024 x 1024, 11
   levels), which suggests a texture array; 16 x 16 normal and ORM maps lost the GPU device before (`docs/maps-hd.md`, sprite walls).
5. How much of the frame-rate drop in the converted Fauztinville scene (8-17 fps) is the 480 extra distinct models, how
   much the 1,700 extra entities and how much the 7,208 biome overrides.
