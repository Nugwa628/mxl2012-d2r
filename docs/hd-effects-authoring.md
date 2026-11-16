# Authoring HD effects: editing and layering D2R's particle effects (lane hd587 round 3, 2026-11-15)

D2R-XL 2012 draws Median XL's missiles and overlays in HD with D2R's own effects (docs/hd-effects.md). Where no D2R effect
looks right, the mod makes its own: a new definition built from layers of D2R effects, with edited copies of D2R's particle
files. This page covers the file formats, what can and cannot be changed, the tools, how to test, and the pitfalls.

## 1. Where an effect lives (build 93847)

| Layer | File | What it holds |
|-|-|-|
| name map | `data/hd/missiles/missiles.json` | missile name (normalised, docs/hd-effects.md section 1) -> model name |
| missile | `data/hd/missiles/<model>.json` (`UnitDefinition`) | entities: one `UnitRootComponent` entity, then entities with a `VfxDefinitionComponent` (a particle file) and a `TransformDefinitionComponent` |
| overlay | `data/hd/overlays/<folder>/<name>.json` (`OverlayDefinition`) | the same entities without the root; `overlay.txt` `Character` is the folder |
| particles | `data/hd/vfx/particles/**.particles` | a PopcornFX 2.9 baked effect (section 2) |
| textures | `data/hd/vfx/textures/**.texture` | D2R textures (`tools/d2r_texture.py`): gradients are RGBA8 (`0x1F`), masks and noise BC4 (`0x3F`, one channel), colour maps BC3 |
| meshes, materials | `data/hd/vfx/meshes/*.model`, `vfx/materials/*.pkma` | named by path in the particle file |

- A definition may hold **several entities**, each with its own particle file and transform: that is how layered effects
  work (D2R's own Gleam has a second entity for Shiver Armor).
- A transform has `position` (y is up: Fire Bolt's head sits at y 4), `orientation`, `scale` and `inheritOnlyPosition`.
- An entity with a `UnitSourceSkillFilterComponent` whose `sourceSkill` is set draws only for that D2R skill; the
  authoring tool leaves such entities out.
- The mod ships its files under `work/mod/data/hd/...` like D2R's paths: a file there replaces D2R's, a new path adds one.
  Edited copies never overwrite D2R's files: they go under `data/hd/vfx/particles/mxl/authored/<effect>/` and
  `data/hd/vfx/textures/mxl/authored/`, and the new definition points at them.

## 2. The particle file (`tools/hd_particles.py`)

Found by reading D2R's files: all 608 particle files of build 93847 that slot 3 holds parse, list their renderers and round-trip byte for byte.

- Header: seven u32 (magic `0xCA000B11`, version `0x01050902`, `0x1F40`, object count, class count, offset of the string
  table, 0), then a (class, count) u32 pair per class.
- Objects: u32 size, then the payload: `0x20`, u32 class (a string index), u16 field count, then per field a u16 id and
  its value. Objects refer to each other by number (1 = the first object).
- String table at the end: u32 count, then u8 length + bytes per string. It names the classes, the layers, the renderer
  properties, every texture, mesh and material path, and the bytecode's functions (`effect.isTeleporting_pCtxI`, ...).

What each part controls:

| What | Where | Editable |
|-|-|-|
| which texture, mesh, gradient | renderer property, type 12 (texture) or 14 (mesh), field 3 = string index | yes, any path and length (`replace_string`, `set_texture`) |
| colour from a gradient | `GradientRemap.GradientMap` texture (RGBA8 strip) | yes: a recoloured copy of the strip (`ramps` below) |
| a layer drawn or not | renderer property `EnableRendering`, 16 bytes `FF` on / `00` off | yes (`set_enabled`, recipe `hide` / `show`); confirmed in game |
| sort offset, softness, other plain floats | renderer property, type 7 (float, lane 0), 3 (int), 1 (bool) | yes (`set_property`) |
| layer kind | renderer field 0: absent billboard, 1 ribbon, 2 mesh, 5 light | read only |
| spawn rate, life, size, speed, colour over life, randomness | compiled scripts in `CCompilerBlobCache` objects: PopcornFX CPU VM bytecode (section 7) | yes: disassemble, edit the text, assemble (`tools/hd_cbvm.py`); `tint` colours a computed colour; confirmed in game (section 9) |
| world space or attached | the scripts (`xform_l2w`, `effect.isTeleporting`) | in principle (section 7), not tried |

Colour therefore has two sources: a gradient texture (`ramps`) or values a script computes (`tint`, or an edit of the
script). Salvation's sparkles pick a random hue in their script (`rgb2hsv` / `hsv2rgb` with a random float4), which is why
they are rainbow whatever the gradient. Masks and noise are BC4, a single channel, so recolouring them does nothing.

`py -3 tools/hd_particles.py info <file>` lists the renderers, their switch and their files;
`py -3 tools/hd_particles.py hide <file> <out> <which>` writes a copy with layers switched off (`which`: a kind, `*`, a path
fragment, several joined by commas).

## 3. Authored effects (`data/hd-effects-authored.json`, `tools/hd_authored.py`)

```json
{"name": "mxl_thunderstone_b", "kind": "missile", "base": "rock_large", "why": "...",
 "layers": [
   {"from": "missile:rock_large", "scale": 1.5},
   {"from": "missile:charged_bolt", "scale": 0.8},
   {"particles": "data/hd/vfx/particles/...", "offset": [0, 0.3, 0],
    "edit": {"hide": "mesh,light", "ramps": {"<gradient>": "blue"}, "textures": {"<old>": "<new>"},
             "props": [{"renderers": "billboard", "name": "Transparent.CameraSortOffset", "value": 2}]}}]}
```

- `from` copies the drawing entities of a D2R missile or overlay (`missile:<model>`, `overlay:<folder>/<name>`) with
  their dependencies; `particles` makes one entity for a particle file.
- `scale` multiplies the layer's transforms (one is added only where needed), `offset` moves it (y up).
- `edit` runs `hd_particles.apply` on every particle file of the layer; `ramps` maps a gradient onto a colour ramp of
  `tools/hd_recolour.py` `RAMPS` (`blue`, `rainbow`, `violet`, ...) as a new RGBA8 texture.
- `base` is the D2R effect a hand pick's scale counts from; an overlay goes to its base's folder.
- A hand pick (`data/hd-effects-picks.tsv`) names the effect in its `effect` column like a D2R one (no `tint` column:
  edits go in the recipe). Unpicked candidates stay in the file so a pick can switch to them.
- `tools/effects_hd.py` builds the picked ones (`--authored` names another file). Every candidate's edited D2R files are
  in `tools/data/d2r_vfx_files.txt` (`py -3 tools/hd_recolour.py list`), so lanes build them from the shared cache.

## 4. Testing

1. `py -3 tools/hd_particles.py info <file>` on the D2R file (from the shared cache, or `MXL_SLOT=3` reads slot 3's CASC).
2. Add or change the entry and the pick; rerun the effect steps (`missile_hd`, `effects_hd`, `missile_looks`, `skill_looks`,
   `missile_release`, `build_effects --check-only`) under `heavy_lock.py build`.
3. Check the built definition in `work/mod/data/hd/missiles|overlays/` (scales, the edited file paths).
4. Run the skill in a game slot (3 or 4, slot lock and `heavy_lock.py game`, in the foreground) with a lab plan that shows
   the effect where it happens: a lob in flight (throw far), monsters in range, walking legs long enough to see a trail.
5. Put candidates side by side on a sheet with HD before and legacy (`mxl2012-runs/hd587/round3/sheet3.py`).
6. `py -3 -m unittest discover -s tools/tests -p "test_hd_*.py"` for the tools.

## 5. Pitfalls

- **About 200 live effects drop every particle for a frame.** D2R then skips all particle effects of the scene, torches
  included (docs/hd-effects.md section 12). A layer on a missile that comes in dozens (Faerie Fire's sparkles, a field)
  multiplies the count: keep layers few and lean on such rows.
- **Overlays move their effects with the unit.** Trails made for missiles (Fire Bolt, Fire Ball: their spawners read
  `effect.isTeleporting`) leave nothing behind on an overlay. The tower mist trail does leave mist behind; its colour is
  computed in its script, which `tint` now changes (section 7). Rapture's own ground trail is a missile the plugin leaves
  (row 143 `spidergoolay`, plugin part `melttrail`), so it can take any missile look (section 9).
- **`auto` pick scale applies to added transforms.** An authored overlay picked with `auto` was scaled by 1.8; picks of
  authored effects use 1 and put the size in the layers.
- **Gradients only in RGBA8.** `ramps` refuses a texture that is not an RGBA8 strip under `textures/gradient/`.
- **Property edits keep object sizes.** Only the string table grows; a property without a stored value (it takes the
  material's default) cannot be set. Script edits (`tools/hd_cbvm.py`) may change object sizes: objects refer to each other
  by number, so only the string-table offset in the header moves.
- **A gradient may be shared.** `ramps` and `textures` change every renderer of the file that names the path; use
  `set_texture` on one renderer for a narrower edit.

## 6. Results of round 3 (#594, #597, #600)

Sheet: `mxl2012-runs/hd587/round3/shots/overview.png` (HD before / A / B / C / legacy).

| Skill | Pick | Others |
|-|-|-|
| Thunderstone (#600) | B: the stone inside Charged Bolt's spark ball | A: Assassin charge-up arcs (faint); C: lightning-hit crackle (barely seen) |
| Faerie Fire (#597) | B: Salvation front with its rings switched off: rainbow sparkles only | A: the whole Salvation front at half size; C: Charge flash in a rainbow ramp (reads yellow-green) |
| Rapture (#594) | C: blue ring plus the tower mist trail: pale mist along the path | A, B: blue Fire Bolt and Fire Ball trails: nothing left behind |

## 7. The compiled scripts: PopcornFX CPU VM bytecode (`tools/hd_cbvm.py`, lane fxlab, 2026-11-16)

What the "compiled bytecode" is, found in the 93847 dump (`d2r93847_dump.exe`, RVA = file offset, read only):

- Every `CCompilerBlobCache` object is one compiled script (spawn, evolve, renderer feed ...) for PopcornFX's CPU virtual
  machine: its backend string is `CPU/CPU_VM` (`CompilerBackend_CPU_VM`). D2R runs it on the CPU; there is no GPU or native
  code in the file.
- The loader checks each script with a validator at `0x16d12a0` that walks the code through a decoder table at `0x2a05a30`
  (opcodes `0x69`..`0x7d`, one decoder each) and fails with `corrupt CBVM bytecode @%05X ! (could not decode instruction %02X)`
  (`0x200e0e0`) or `(illegal instruction %02X)` (`0x200e128`). The mnemonics are in the binary (`0x200df08`: `stz cvt vct
  swz dup mop madd idivmi mfn1 mfn2 mfn3 call prlg eplg`), the register type names in the VM type table at `0x1d9e640`, and
  the math function names at `0x1dd8d20` / `0x1da4330`.

Object fields (u16 id, value): 0 backend (string), 1 kind (absent, 1 to 5; kinds 4 and 5 hold identical copies, `tint`
edits all), 2 program (u32 word count, words), 4 external descriptors (5 u32 per external), 5 external names (string
indices, `-1` = none), 6 function names (the `call` targets: `effect.isTeleporting_pCtxI`, ...).

Program: nine u32 (h0 register count, h1 code bytes, h3 constant bytes = 32 x h5, h5 constant count; the others are kept),
the code at byte 36, the constants right after the code (unaligned, 32 bytes each: a value repeated over 8 SIMD lanes; a
float3 is packed and repeated), then 0 to 3 pad bytes.

Registers are u32: bits 0-20 index, 21-22 class (`c` constant, `u` uniform, `s` per-particle stream), bit 23 a flag (`!`),
24-29 the type (`float`, `float4`, `int`, `bool`, ... the VM table's order); `0xFFFFFFFF` = none.

| Opcode | Text | Bytes | Operands |
|-|-|-|-|
| `69` `6A` | `ld` `st` | 7 | register, i16 external (a stream or input by name) |
| `6B` | `stz` | 3 | i16 external |
| `6C` `6F` | `cvt` `dup` | 9 | dst, src |
| `6D` | `vct` | 6 + 4n | count byte, dst, n components |
| `6E` | `swz` | 12 | three swizzle bytes, dst, src |
| `70` | `mop.N` | 14 | sub-op byte (logic and compare; kept as a number), 3 registers |
| `71`..`74` | `add` `sub` `mul` `div` | 13 | dst, a, b |
| `75` `7A` | `madd` `sel` | 17 | dst, a, b, c |
| `76` | `idivmi` | 21 | 5 registers |
| `77` `78` | `mfn1.<fn>` `mfn2.<fn>` | 10 or 14 | function byte, dst, 1 or 2 sources (14 for the binary functions: `atan2`, `min`, `max`, `dot`, `cross` ...) |
| `79` | `mfn3.N` | 18 | function byte, 4 registers |
| `7B` | `call` | 11 + 5n | flags, i16, u16 function index (field 6), n, dst, then n x (kind byte, register) |
| `7C` | `prlg` | 2 + 4k | k words |
| `7D` | `eplg` | 1 | end |

How a colour reaches the screen: the renderer's `CLayerCompileCacheRendererParticleInput` maps an input (`Color.Color`)
to a field of the layer (`CLayerCompileCacheField`) whose name is the stream's external name in the evolve script (decimal
names: `'15'`, `'11'` ...). D2R's tower mist computes one grey float and broadcasts it to the float4 colour with `swz`
before the `st`: that is why it is grey whatever its textures.

Tools:

- `py -3 tools/hd_cbvm.py dis <file> [--obj N]`: the scripts as text (directives `.order .backend .kind .head .ext .fns
  .const .pad`, then one instruction per line, e.g. `mul s1.float4, s1.float4, c15.float4`).
- `dump <file> <dir>` writes one `obj_<N>.cbvm` per script; edit them (a constant, an instruction, new constants with
  `.const`); `build <file> <dir> <out>` assembles them back into the particle file.
- `streams <file>`: the colour streams computed as a grey level (candidates for `tint`).
- `tint <file> <out> <stream> R G B [A]`: a `mul` by a new float4 constant before every store of the stream. In an
  authored layer: `"edit": {"tint": [r, g, b, a]}` (every grey colour stream) or `{"tint": {"<stream>": [r, g, b, a]}}`.
- `check <files or folders>`: text round trip of every script. All 610 particle files of the shared cache (41,337
  scripts) come back byte for byte.

Limits: the `mop` sub-ops and the `mfn3` functions are kept as numbers (their meaning is not mapped yet); a new
instruction must keep the register count h0 (new registers need h0 raised); D2R refuses the whole file on a bad
instruction (the validator above), so test a change in game; which kind (4, 5 or none) the PC build runs is not known,
which is why `tint` edits every copy.

## 8. Models: Granny GR2 `.model` to glTF and back (`tools/hd_gltf.py`, lane fxlab)

D2R's HD models (`.model`, also `.skeleton`, `.animations`) are RAD Granny 3D GR2 files: a section container (BitKnit2
compressed; `tools/d2r_model.py` reads and writes it, a port of the MIT eiz/pybg3 decoder) holding a typed object tree
(Textures, Materials, Skeletons, VertexDatas, TriTopologies, Meshes, Models). A `<name>.model` path is resolved to
`<name>_lod0.model` ... through `data/hd/model_lod_desc.bin` (docs/d2r-addresses.md section 23); the `_lodN` files hold the
meshes, the plain path is often an empty file. The open GR2 readers are made for other games (Norbyte's LSLib and eiz's
pybg3 for Larian's games; the BitKnit2 decoder here is a port of pybg3) and were not tried on D2R's files; the repo's own
reader is the converter, glTF 2.0 the open side that Blender edits.

Vertex formats seen (277 env models sampled): static `Position` BinormalInt16[4], `Normal` / `Tangent` BinormalInt8[4],
optional `DiffuseColor0` NormalUInt8[4] (vertex colour), `TextureCoordinates0` Real16[2]; skinned parts add
`BoneWeights` NormalUInt8[4] (sum 255) and `BoneIndices` UInt8[4] (into the mesh's BoneBindings). Position = int16 / 32767
x the mesh's `ExtendedData.VertexScale`; the 16-bit indices are a signed Int16 member (values above 32767 read negative).

Round trip:

1. Get the D2R file: env models are in the shared cache (`mxl2012-runs/shared/d2r-cache/data/hd/env/model`); others come
   from a game slot's CASC (read only, under the slot lock: `tools/lane_setup.py`'s `casc_reader`).
2. `py -3 tools/hd_gltf.py export <x_lod0.model> <x.glb>`: one glTF mesh per D2R mesh, one primitive per triangle group,
   POSITION / NORMAL / TANGENT / TEXCOORD_0 (+ COLOR_0), the skin as `_JOINTS` / `_WEIGHTS` with the bone names in
   `extras.d2r.bones`, each material's texture game paths as image URIs and `extras.d2r.maps`.
3. Edit in Blender (File > Import > glTF 2.0; export glTF Binary with the same mesh names, "Custom Attributes" on for a
   skinned part) or with `hd_gltf.py edit <in.glb> <out.glb> --scale S --offset X Y Z --map AlbedoTexture=<path>`.
4. `py -3 tools/hd_gltf.py import <x_lod0.model> <edited.glb> <out_lod0.model>`: meshes matched by name, vertex and triangle
   counts may change (more than 65,535 vertices do not fit 16-bit indices), bounds, VertexScale and bone boxes recomputed,
   new vertices take the skin of the nearest original one, texture paths from the material.
5. Ship it at D2R's path (`work/mod/data/hd/<same path>`) to replace D2R's model, or at a new path with a
   `model_lod_desc.bin` entry (`tools/model_lod_desc.py`); a new texture path needs a `texture_desc_cache.json` entry.
6. `py -3 tools/hd_gltf.py check <files or folders>`: export then import of unchanged geometry must give the same tree.

Limits: the skeleton, animations and the Model placement are kept from the donor (not in the `.glb`); only
`TextureCoordinates0` is carried; materials are referenced by game path (the texture pixels are `tools/d2r_texture.py`'s);
a mesh the donor does not have is refused; the bounds in `model_lod_desc.bin` stay D2R's for an override (a much larger
model may be culled early near the screen edge).

## 9. Results of lane fxlab (2026-11-16)

Sheet: `mxl2012-runs/fxlab/shots/overview.png` (HD before / A / B / D / old C / legacy; the model round trip). Runs on
slot 3 (`mxl2012-runs/fxlab/lab/`: `runlab.sh`, `lab.py`, `plan.json`, `sheet.py`).

- **Script edit in game.** The tower mist (`vfx_mist_towerMistTrail.particles`) with its grey colour multiplied by a blue
  constant (`tint`: a `mul` and a constant added before each colour store, object sizes changed) loads and draws blue.
- **Rapture's melt trail (#594).** In HD the trail pieces (missile 143 `spidergoolay`, art `IceBreakSmallMelt`) drew
  D2R's `ice_break_small_melt`, which has no renderers: nothing showed. A row pick now draws them as the tower mist, which
  stays on the ground where it was made, turned blue in its script:

| Candidate | Look | Note |
|-|-|-|
| `rapture_melt_a` (built as the pick) | deep blue mist along the path | closest in colour to legacy's trail |
| `rapture_melt_b` | larger, paler ice-blue mist | softer; reads more like frost |
| `rapture_trail_d` (overlay, ring pick) | the blue ring plus a blue mist cloud on the paladin | the overlay moves with him: a cloud, not a trail |

  Legacy's trail is a bright, dense light-blue smear; the mist is softer and fainter. Brighter would need a stronger
  constant or the alpha raised in the same script (a value in `tint`'s fourth component, or an edit of the opacity
  constants with `dump` / `build`).
- **Model round trip.** Thunderstone's stone (`data/hd/vfx/meshes/fx_mesh_andarial_chunk03_lod0.model`, read from slot 3's
  CASC) exported to glTF, scaled 3x and given the ice cave platform albedo (`hd_gltf.py edit`), imported back and put at
  D2R's path in the mod for one run: the stone flies three times bigger with the ice texture (sheet, last row). The file
  was only in that run's install, not in the build. `hd_gltf.py check`: 1,194 env and vfx models, 0 differ.
