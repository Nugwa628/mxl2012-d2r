# Map viewer (classic and HD)

A map-editor-like viewer for D2R-XL 2012's maps, for agents (CLI, MCP) and for the owner (a local web page): the whole
map or a cell range, classic (the `.ds1` drawn with its `.dt1` tiles and the act palette) and HD (the D2R or mod preset
drawn with hdkit's wgpu renderer in the game camera) on the same pixels, cell inspection, edits on working copies, and
screenshots. Viewer only: it never runs the game and never writes game files or extracts.

Code: `tools/hdkit/view/mapview/` (ds1.py, dt1.py, world.py, frame.py, classic.py, hd.py, edit.py, api.py, cli.py,
webmap.py), the page `tools/hdkit/view/web/map.html` + `map.js`, the MCP tools in `tools/hdkit/view/mcp_server.py`, tests
`tools/tests/test_mapview.py` (synthetic `.ds1` / `.dt1` only). Outputs: `/d2work/runs/mapview/<map>/` (`MAPVIEW_OUT`).

## Commands

Run from `tools/` with the project venv (`/d2work/venv/mxl2012/bin/python`):

    python -m hdkit.view map ls [--source mod|d2r] [--pattern p]
    python -m hdkit.view map info <map>
    python -m hdkit.view map classic <map> [--cells x0,y0,x1,y1] [--scale s] [--layers ...] [--isolate]
    python -m hdkit.view map hd <map> [--cells ...] [--scale s] [--layers ...] [--el 50 --az 20] [--grid]
    python -m hdkit.view map sheet <map> [--cells ...] [--scale s]           classic | HD | 50% blend
    python -m hdkit.view map cell <map> <x> <y> [--near 1]
    python -m hdkit.view map edit init|tile|obj-add|obj-move|obj-remove|ent-add|ent-move|ent-remove|show ...
    python -m hdkit.view map serve [<map>] [--port 8766]                     the page, 127.0.0.1 only; Ctrl+C stops it

`<map>` is the path below `data/global/tiles` without `.ds1` (`act1/cathedrl/cathy3`, `expansion/ghetto/cypherpunk`).
`--source auto` (default) takes the mod's map when the mod has one, else D2R's; `--source d2r` forces D2R's own.
Scale: output px per native classic px (default 0.5 for a whole map, 1 for a region). Every PNG has a JSON beside it
(frame, layers, missing tiles, notes, timings).

Classic layers: `floor shadow wall lower roof special objects labels grid coords walk`; the defaults are
`floor shadow wall lower roof objects labels`; `-roof,+grid,+walk` edits them (write `--layers=-roof,...` when the list starts with `-`), a plain list replaces
them, `all` = every one.
HD layers: `terrain decals walls props prefabs lights fx units objects grid` (default all but objects and grid; `objects`
are the classic overlay's markers, `units` the HD object models). `--rig vis` (default) lights the map with its biome's own
vis file and lights (below); `game` / `default` are hdkit's generic rigs.

MCP (hdkit-view server, `python -m hdkit.view.mcp_server`): `map_list`, `map_info`, `map_render` (kind classic / hd /
sheet), `map_cell`, `map_edit_init`, `map_edit`. HD renders pass the GPU gate first like the other render tools.

## Data

* Classic: the `.ds1` and tables from the mod's MPQ extract (`tools/maps_hd.default_extract()`) or D2R's extract
  (`default_d2r()`); tile files: the lvlprest rows naming the map -> their level's LevelType -> lvltypes `File 1..32`
  selected by `Dt1Mask` (the game's rule, as `tools/maps_hd.py`); maps no level uses fall back to the ds1edit file list
  stored in the `.ds1`. The first file that has a key wins. The act palette (`data/global/palette/actN/pal.dat`) is not
  in the extracts: it is read through hdkit's CASC root (slot 5's game folder, read-only, cached).
* HD: the preset `hd/env/preset/mxl2012/<map>.json` (Median's own maps after the build, `tools/ds1_paths.py`) or
  `hd/env/preset/<map>.json`, over the roots: a working copy, the built mod data (`MAPVIEW_MOD_DATA`, default the newest
  `/d2work/runs/relpkg/*/mxl2012/mxl2012.mpq/data`), CASC.
* Object names: type 1 through the act's MonPreset rows, else MonStats rows; type 2 through ObjPreset (D2R's, Median ships
  none) and Objects. Monster ids of Median maps are shown as Median numbered them (the extract is before the remap).

## How it draws

Classic (`classic.py`, after OpenDiablo2's d2maprenderer and ds1edit):

* cell (x, y)'s floor diamond has its top corner at native ((x - y) * 80, (x + y) * 40); a floor tile's blocks are drawn
  from 80 px left of that corner; any other tile's blocks are given from the tile's bottom and drawn 80 px lower; a roof is
  lifted by its roof height;
* pass 1 cell by cell (rows, then columns): lower walls (orientations 16-19), floors (each floor layer), shadows (13,
  darken 50 %); pass 2 cell by cell: walls of orientations 1-9, 12, 14, each wall layer, a north corner's right part (3)
  also draws its left part (4); pass 3: roofs (15). Special tiles 10/11 only with the `special` layer (faded);
* a dword whose prop1 byte is 0 or whose hidden bit (31) is set draws nothing;
* rarity variants of one key: one picked per cell by a hash of (x, y) weighted by rarity (the game picks at random per
  seed, so variant choice differs from a given game, the layout does not);
* big maps render in strips of 2048 native rows, each scaled down on its own (downtown, 251 x 251 cells: 38,797 tiles
  in 23 s at scale 0.125, 1.2 GB peak memory).

HD (`hd.py`, lane hdmaps2 for ground, decals, materials, lights and units): `preset.build_scene` (model entities, one
level of prefabs), placements whose origin is more than 3 cells outside the range skipped, the renderer at the game camera
(elevation 30, azimuth 45) with k = 16.97 x scale x 2/3 px per unit and the world origin on the frame's pixel of cell
corner (0, 0): one cell is 10 world units, so a cell step is (120, 60) px at HD scale 1 = (80, 40) at classic scale 1. The
test `test_hd_camera_lines_up` checks the maths; on cathy3 the altar and pillars sit on the same pixels in both renders.
Orbit angles (`--el/--az`) fit the range into the image instead (pixels then do not line up with classic; overlays are
skipped).

* **Ground** (`ground.py`): a splat of up to 16 terrain layers in one shader (`fs_terrain`). The biome is the one the
  terrain entity's `terrain.model` material names (cathy3: `act1_catacombs`, while the preset says `act1_cathedral`: the
  game shows catacomb stone, which is how this was settled), else the preset's `biomeFilename` on a ground plane under the
  map's floor cells. Per floor cell the base layer (0) of its biome (`perTileBiomeOverrides` per tileX / tileY, else the
  ground biome); cells without a floor tile get no ground. Terrain stamps paint their R / G / B channels x stomp into layers
  layerIndexR / G / B of `biomeName` over scale.x x scale.z units at the transform's yaw. Layers blend by weight x (albedo
  alpha + 0.5)^4 (the albedo alpha is the layer's height), tile edges soften over 3 texels of 16 per cell, one layer texture
  repeat per 20 world units.
* **Decals**: terrain decals (`TerrainDecalDefinitionComponent`) and floor decals (`DecalDefinitionComponent` whose
  projection axis is within 45 degrees of vertical) as alpha-blended quads 0.03 units above the ground, scale.x x scale.z,
  alpha = albedo alpha x stomp (or weight). Decals on walls are counted, not drawn.
* **Materials** (`gr2.material_params`): `AlphaThreshold` (or an enabled `PrimaryAlphaThreshold`) cuts, `AlphaIntensity`
  blends (premultiplied, drawn after the opaque pass back to front), `EmissiveIntensity` adds albedo x MaskTexture x the
  intensity. Before this the blood, grunge and carpet overlays drew as opaque grey or red squares and sprite trees as
  rectangles.
* **Light** (`--rig vis`): the biome's vis file (`day` when the biome has several) through `rig.from_vis` with the
  environment's light mask (1): its key light and exposure (indoor biomes have a key of power 0); ambient 0.004 x
  `iblIntensity`; every preset point light (colour x power x 0.01) and spot light (as a point half way along its axis);
  per draw the 32 lights that reach it, nearest first (the shader's limit; a scene may hold any number). `maps_calib.py`
  adds the player's light (playerUnitLightPower x characterBrightnessFactor x 0.15, radius 10 sub-tiles x
  playerUnitLightDistanceScaler) for comparisons with captures.
* **Effects and units** (`units.py`): particle effects are not simulated; fire-like ones (candle, torch, brazier, fire,
  flame, ember, lava in the file or entity name) are an emissive flame card facing the camera plus a warm point light,
  the rest is counted. `.ds1` objects (type 2) are drawn as their D2R HD unit in its rest pose: (act, id) -> ObjPreset ->
  the objects.txt row (D2R's table: Median's has no Class column and keeps D2R's rows) -> `data/hd/objects/objects.json`
  (keys in row order) -> `<asset_path>/<key>.json`; a unit whose effects are fire gets a flame card and light too.
  Monsters are not drawn in HD.

Calibration (`tools/maps_calib.py pair`): in-game captures at 3840x2160 (profile `visual4k`, `MXL_CLIENT=3840x2160`, run
`/d2work/runs/hdmaps2/runs/checks-20261121-105757-s5`, cathy3 and Fauztinville in HD and classic) against the viewer at
classic scale 3.6 (= the game's 4K camera), aligned on the player's spot. The constants above were fitted on cathy3
(three gains on a grid, error = mean squared log luminance over a 3 x 3 grid of the screen): mean luminance of the
playfield 0.060 viewer against 0.041 game at the altar, 0.079 against 0.040 in the nave. The viewer is still up to 2x
too bright, mostly where the game fades the walls in front of the player (the viewer draws them) and in the player's
pool. Fauztinville's captures are crowded by Median's unkillable turrets and their missiles, so they serve for the mood
(classic and HD alike dark and blue at the arrival) and not for numbers.

Frame (`frame.py`): a cell range's ground diamonds' bounding box plus `rise` native px above (default: the tallest wall
tile the map uses) and 40 below; `origin_px` + `cell_step_px` in each JSON give the pixel of any cell corner.

## Inspect and edit

`map cell` (`map_cell`, the page's click): each floor / wall / shadow dword with style, sequence, orientation, prop1,
hidden; the tile it resolves to (dt1 file, index, variants and rarities, size, roof height, 5 x 5 sub-tile flags as hex
rows); the cell's combined walk flags; the `.ds1` objects on it; the preset entities whose origin is on it (or within
`--near` cells): index, name, components, model, prefab, transform, light.

Working copies (`edit.py`): `map edit init <map>` copies the `.ds1` and the preset to
`/d2work/runs/mapview/work/<map>/data/...` (same logical paths); `tile`, `obj-add/move/remove` (sub-tile coordinates),
`ent-add/move/remove` (world units) edit the copy and log to `edits.jsonl`; `show` lists the edits and the changed
cells. Renders and `cell` take `--work <folder>`. Writes are checked to stay inside the copy and never land in
`/d2work/slots`, the extracts or `/games`. The `.ds1` writer copies everything but the layer stream and the object block,
so an unchanged map writes the same bytes: all 2,311 `.ds1` of both extracts round-trip byte-identically (checked once by
hand; the test does it on synthetic maps of versions 3 to 18). Preset JSON is rewritten with `json.dumps(indent=4)`
(same content, not the same bytes).

## Web page

`python -m hdkit.view map serve [<map>]`, open `http://127.0.0.1:8766/`. The page loads the whole map at a base scale
(0.5, halved until the longest side is at most 8192 px), pans (drag) and zooms (wheel), switches classic / HD / overlay
(HD opacity slider), draws the grid, shows a clicked cell's info (and its raw JSON), and for a shift-dragged region
saves the view as shown (PNG download) or opens a fresh render of the region (classic, HD or sheet, any scale). The first
HD image of a map takes from a few seconds to a minute (models and textures read from CASC on first use). Renders are
cached under `<map>/web/`. No CDN or network URL: everything comes from the local server. Stop it with Ctrl+C.

### Memory

The PC is shared: keep a job under about 10 GB. A whole-map HD render below 1:1 skips the top mips of every texture
(`scene.MIP_DROP`, set by `hd.render` from the frame's scale: floor(log2(1 / scale)) levels), the renderer's texture cache
empties itself past 1.5 GB (`gpu.TEX_CACHE_BYTES`), and `tools/maps_audit.py run` with several maps runs each map in its
own process under `tools/memwatch.py --gb 9` (a map that grows past it is stopped and reported, the others go on; the 4x
Fauztinville audit peaks at 2.4 GB). Wrap other long jobs the same way: `python tools/memwatch.py --gb 9 -- COMMAND`. An
address-space cap (`ulimit -v`, `prlimit --as`) does not work for the GPU tools: the Vulkan driver reserves several GB of
address space.

### Rounds page (showing results)

`http://127.0.0.1:8766/rounds` on the same server shows prepared pictures, read-only: a round folder
(`$MXL_ROUNDS`, default `/d2work/runs/hdmaps2/rounds/<round>/<map or crop>/`) holds `<n>_<label>.png` pictures of one
frame (classic, shipped HD, new builds) and an optional `note.txt`. The page shows them side by side with one pan/zoom,
as a flicker (keys 1-9, space) or as a wipe (the split follows the mouse); `1:1` is the 4K screen size when the
pictures were rendered at scale 3.6. `[` / `]` step through the maps. `tools/maps_rounds.py crop|whole` renders such a
folder (`--hd LABEL=ROOTS` per HD build). Only picture files below the rounds folder are served.

## Not drawn / approximate

* HD: tile mask path masks (`data/hd/env/tilemasks`, town and outdoor path edges), grass and clutter, the layers' noise
  textures and parallax; particles (only fire, as cards); wall fading in front of the player; shadows; spot light cones;
  monsters. Light is calibrated on one D2R map (above); outdoor biomes with a sun were not checked against the game.
* Classic: animated tiles show their first frame; rarity variants are a stand-in (see above); light is the palette at
  full brightness (no light map, no day/night); shadows are a plain 50 % darken; units (monsters, NPCs, object sprites)
  are markers, not their DCC/DC6 art; lower walls are drawn before the floor of the same cell (OpenDiablo2's order, not
  checked against the game); the sub-tile flag order (OpenDiablo2's `(4 - y) * 5 + x`) is not checked against the game.
* Version 3 and older `.ds1` layer streams follow ds1edit's layout (one D2R file); groups and NPC paths are kept as raw
  bytes (an object move does not move its path).
* The page shows pre-rendered images (canvas 2D), not a live WebGPU scene; editing is CLI / MCP only.
