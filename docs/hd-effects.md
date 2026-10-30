# HD effects for Median XL 2012's missiles and overlays (lane `fx`, 2026-10-28)

Goal: every missile and overlay that Median XL 2012 v005 uses gets an HD stand-in in D2R, the closest vanilla HD effect by
element, shape and size, as a build step. Median's own art (the DCCs) stays classic-mode only; custom HD art replaces the
stand-ins later (section 7).

Tools: `tools/build.py` already runs `tools/art_provenance.py` and `tools/effects_hd.py` as steps; `tools/build_effects.py` runs
those two and a check on their own. Mapping table (committed, our own data): `data/hd-effects-map.tsv`, one line per art file.
Everything else goes to the gitignored `work/mod/` (the build's folder).
No game runs: nothing here has been looked at in the game (section 6).

This file holds art file names, D2R effect names and counts. No table content, no art.

## 1. How D2R draws an effect (build 93847)

D2R does not read the DCC. A missile or overlay is drawn from data files:

| Layer | File | Key |
|---|---|---|
| name map | `data/hd/missiles/missiles.json` | missile name, normalised (below) -> model name |
| missile definition | `data/hd/missiles/<model>.json` (`UnitDefinition`) | |
| overlay definition | `data/hd/overlays/<Character>/<overlay name>.json` (`OverlayDefinition`) | overlay.txt `Character` is the folder |
| visuals | `data/hd/vfx/particles/**.particles` (PopcornFX), textures, a few 3D models | |

- The lookup key is the name lowercased, spaces as `_`, and an `_` in front of every digit run after a non-digit
  (`spike1` -> `spike_1`, `cyclonearmor1front` -> `cyclonearmor_1front`). `norm_key()` in `tools/effects_hd.py`.
- A definition carries only the transform scale and position of its entities (used here), one fade-in alpha and one spot
  light. It has **no tint, transparency, speed or animation timing**: where a Median row differs from the D2R row it follows
  in light, Trans, Vel or range, that difference is not shown in HD.
- **Character trap, confirmed in v005.** The 1.13c `overlay.txt` `Character` column is `all` on 328 of 525 rows and a class
  name (`Paladin`, `Druid`, ...) or `Monster` on the rest. D2R reads the column as the HD folder (`common`, `paladin`,
  `sorceress`, ...). Every row needs its value rewritten, not only the new ones. `effects_hd.py` sets `Character` on
  505 rows: in place in both banks of `work/mod/data/global/excel/` once `txt_migrate.py` has made them, otherwise (this lane's
  run, on Median's raw table) as a copy at `work/mod/data/global/excel/overlay.txt`.
  Rows that are D2R's own take D2R's folder; the others take the folder of the effect they use.
- D2R names one model in `missiles.json` that has no file (`engorgecorpseexplode`); not ours, left alone.

## 2. Inputs

| What | Where | Note |
|---|---|---|
| Median v005 tables and DCCs | `assets/median` of the repo, else `R\mxl2012-runs\extract-mpq\` (`MXL_EXTRACT`) | 2,665 missile rows, 525 overlay rows; 145 + 63 DCCs |
| Tables the rows are read from | `work/mod/data/global/excel` once `txt_migrate.py` made it, else Median's own (`MXL_TABLES`) | this lane ran on Median's own |
| D2R baseline: tables, legacy DCCs, `hd/` json, units palette | `extract/d2r/93847` of the repo (`casc_extract.py`), else `extract_dir` of the machine-local config (`MXL_D2R_BASE`; docs/setup.md) | read-only; D2R ships the base game's 392 missile and 406 overlay DCCs, so the base-game art needs no extraction from the 1.13c MPQs |
| Earlier per-art effect decisions (reference set) | the reference set's `effects_hd.md`, `art_fix.md` and Median art, located by the machine-local config | read-only (skipped with `--no-prior`) |
| Python | `py -3` with numpy and Pillow (`tools/requirements-fx.txt`); the lane used `R\mxl2012-runs\venv-art` | |

Paths and environment variables: `tools/fxpaths.py`.

## 3. Rules

Every missile and overlay row that D2R does not already draw in HD gets a class. Rows that are D2R's own (same name, same art
as a D2R row with an HD effect: 644 missile rows, 290 overlay rows) keep D2R's effect and are not in the table.

| Class | When | Effect |
|---|---|---|
| `exact` | the row's art file is a D2R art file that a D2R row draws in HD | that D2R row's effect; among several, the row most like this one (name and skill words, moving / hit / sub / loop role, then Vel, Range, Light, Trans) |
| `hand` | the art has a line in `data/hd-effects-picks.tsv` (lane hdfx2, section 9) and D2R does not draw the art itself | the picked D2R effect, scaled by art size unless the line gives a scale; the reason is in the line |
| `provenance` | `art_provenance.py` found the Median-only DCC to be an exact (or rescaled, or colour-close) copy of a vanilla animation that has an HD effect | that vanilla animation's effect |
| `prior` | the reference set decided the same art, and the file is byte-identical (Median file) or is a base-game file (same D2R file) | the reference set's stand-in; for the row of the same name its choice, otherwise the closest of its choices for that art |
| `stand-in` | anything else | the D2R effect with the lowest cost: 3.0 x colour distance (mean palette colour of the DCC frames) + 1.2 x size ratio + 0.35 x frame-count ratio + role mismatches - 1.7 per shared element word (fire, ice, elec, poison, arcane, holy, bone, blood, dark, wind, earth, nature, blade, trap, buff) - 0.7 per shared shape word (nova, orb, bolt, explode, trail, wall, storm, front/back, small/large, cast) - 0.4 per shared word. Hand-picked look-alikes win for their art. |
| `no-art` | the art file exists nowhere (not in `patch_d2.mpq`, not in the base game) | none: 1.13c draws nothing either |

Order: exact, hand, provenance, prior, stand-in. Confidence: `exact` high unless several D2R models share the art and the rows hardly
differ; `stand-in` and `prior` high when element words agree and the colours are close, medium when one does, else low.
A stand-in is scaled (transform scale and position of every entity, `mxl_<model>_s<percent>.json`) by the ratio of Median's
classic art to the stand-in's art, damped (`ratio^0.7`, 0.6 to 1.8, 0.1 steps, left alone within 15%).

Choices of this port:

- **No PalShift.** The 1.13c `missiles.txt` of v005 has no PalShift column, so
  `palshift.py` is not ported and reference decisions made by "shifted colour" are not reused.
- **Gradient tint (lane tints, 2026-10-29).** A recolour of a vanilla animation (22 missile and 3 overlay DCCs) keeps the vanilla
  effect when its colour is within 0.12 of the original; otherwise `tools/hd_recolour.py` makes a copy of the vanilla effect with
  its colour gradients shifted to Median's colour (section 5a). Where that is not possible (no colour gradient in the effect,
  or the D2R vfx files are not cached) the nearest-colour scoring decides; the scoring gives the original's own effect a 1.5
  credit (shape match) and adds the original's name to the row's words.
- **Missing art: nothing where nothing uses it, a stand-in where a skill does** (owner 2026-10-29). In 1.13c a row whose art exists
  nowhere draws nothing; the port keeps that only for rows no player or monster skill reaches (section 5).
- **Art-level reuse.** The reference set's rows (4,975 missile rows) have few row names in common with v005, so
  its decisions are reused by art file: byte-identical (SHA-1) Median files and base-game files.
- Not ported: `missile_hd.py` (its by-CelFile map is a subset of the per-row `exact` rule; only its two hand-picked look-alikes
  are kept), `missile_art.py` (custom flipbook art, never confirmed in game), `hd_skill_anims.py` (HD
  *body* animation states for sequence skills, not a missile or overlay; a separate step if wanted).

## 4. Results (run of 2026-10-28)

Art files (a missile CelFile, an overlay Filename) needing an effect, and the rows behind them:

| | arts | rows |
|---|---:|---:|
| Missile rows, total | | 2,665 |
| &nbsp;&nbsp;D2R's own (stay) | | 644 |
| &nbsp;&nbsp;logic missiles (no art) | | 802 |
| &nbsp;&nbsp;with art, decided here | 322 | 1,219 |
| &nbsp;&nbsp;&nbsp;&nbsp;exact (D2R art) | 148 | 743 |
| &nbsp;&nbsp;&nbsp;&nbsp;provenance | 2 | 3 |
| &nbsp;&nbsp;&nbsp;&nbsp;prior | 127 | 368 |
| &nbsp;&nbsp;&nbsp;&nbsp;stand-in (new here) | 35 | 91 |
| &nbsp;&nbsp;&nbsp;&nbsp;**no-art (unmapped)** | **10** | **14** |
| Overlay rows, total | | 524 |
| &nbsp;&nbsp;D2R's own (stay) | | 290 |
| &nbsp;&nbsp;with art, decided here | 197 | 234 |
| &nbsp;&nbsp;&nbsp;&nbsp;exact | 72 | 97 |
| &nbsp;&nbsp;&nbsp;&nbsp;prior | 113 | 125 |
| &nbsp;&nbsp;&nbsp;&nbsp;stand-in (new here) | 1 | 1 |
| &nbsp;&nbsp;&nbsp;&nbsp;**no-art (unmapped)** | **11** | **11** |

**Mapped: 312 missile arts and 186 overlay arts (1,205 + 223 rows). Unmapped: 10 + 11 arts (14 + 11 rows), all because the
art file exists nowhere.** Confidence of the mapped rows with art: missiles high 810 / medium 369 / low 26 (`exact` rows: high 586, medium 157),
overlays high 124 / medium 95 / low 4.

Median's own DCCs: 145 missile + 63 overlay = 208. 169 are referenced by a row and mapped (114 missile, 55 overlay: 28 missile
stand-ins chosen here, 84 + 55 through prior decisions, 2 through provenance). 39 are referenced by no row of `missiles.txt` / `overlay.txt` (31
missile, 8 overlay); they are in the table as `unreferenced`. Provenance of the 208: missiles 18 exact copies of a vanilla
animation, 22 recolours, 105 new; overlays 23 exact, 3 recolours, 37 new (some "vanilla" sources are an animation of the other
kind, e.g. overlay `rockon1` is vanilla missile `ceilingchunkvanish01`; D2R's missile and overlay definitions are not
interchangeable, so such a match only feeds the scoring words).

Generated: `work/mod/data/hd/missiles/missiles.json` (D2R's map plus an entry per decided row, logic missiles as `null`), 68 scaled
variants `mxl_<model>_s<percent>.json`, 234 overlay definitions under `work/mod/data/hd/overlays/<folder>/`, the
`overlay.txt` copy, `work/mod/effects_hd.md` (every row: art, effect, scale, class, confidence, why; names of table rows, so not
committed) and `work/mod/art_provenance.json/.md`.

Reading the table (`data/hd-effects-map.tsv`): `art_in` mod / base (base-game file D2R ships) / missing; `provenance` what
`art_provenance.py` found; `rows` rows that use the art; `effects` how many distinct effects those rows got (the line shows the
most common); `prior_file` identical / differs / absent / base against the reference set's Median files, `prior_effect` the reference set's
most common effect for the art.

### Stand-ins chosen here (36 art files)

Lane hdfx2 (section 9) replaced `bonfire`, `focusgreen`, `psiorbexplode`, `sparklez1` and `sparklez2` with hand picks; the
lines below are the scoring's choice of 2026-10-28.

These are the only decisions made by this lane's scoring; the rest follow D2R or the reference set. "Colour dist" is 0 (same) to 1.

| Kind | Art | Rows | HD effect | Scale | Conf | Vanilla source | Why |
|---|---|---:|---|---:|---|---|---|
| missile | `balefire` | 3 | diabwall | 1 | medium | recolour of groundfiremedium | like D2R `diabwall`, colour dist 0.51 |
| missile | `blackfirebig` | 3 | ground_fire_big | 1 | medium | recolour of groundfirebig | like D2R `firewall`, 0.44 |
| missile | `blackfiremedium` | 1 | diabwall | 1 | medium | recolour of groundfiremedium | like D2R `diabwall`, 0.44 |
| missile | `blueshockeffect` | 1 | expansion_shock_field | 1 | medium | | like D2R shock field, 0.25 |
| missile | `bonespiritpurple` | 2 | bone_spirit | 1 | medium | recolour of bonespirit | the original's effect, 0.41 |
| missile | `bonfire` | 1 | expansion_armageddon_fire | 1 | high | | like D2R `armageddontail`, 0.10 |
| missile | `chicken` | 6 | charged_bolt | 1 | medium | | like D2R `chargedbolt`, 0.19 |
| missile | `discoinferno` | 17 | expansion_impmissile_01 | 1 | low | recolour of impmissile01 | the original's effect, 0.32 |
| missile | `dopplezonexplodeblue` | 1 | mxl_teethexplode_s130 | 1.3 | medium | | like D2R `sucshockfieldmissileexp`, 0.15 |
| missile | `dopplezonexplodegreen` | 1 | dopplezon_explode | 1 | low | | like D2R `dopplezonexplode`, 0.37 |
| missile | `dragonbolt` | 6 | mxl_expansion_bladefury_b_s130 | 1.3 | high | | like D2R `bladefragment2`, 0.11 |
| missile | `expansion/pdteleportmissile` | 1 | expansion_impteleport | 1 | high | | like D2R `imp teleport`, 0.15 |
| missile | `expansion/siegrock` | 1 | mxl_expansion_molten_boulder_emerge_s120 | 1.2 | high | | like D2R `moltenboulderemerge`, 0.11 |
| missile | `expansion/steamthick_a` | 1 | expansion_shockwave | 1 | medium | | like D2R `shockwave`, 0.20 |
| missile | `expansion/steamthick_b` | 1 | mxl_expansion_armageddon_fire_s130 | 1.3 | medium | | like D2R `armageddontail`, 0.45 |
| missile | `extra/bighead` | 1 | electric_nova | 1 | high | | like D2R `lightningtowernova`, 0.19 |
| missile | `extra/chillblood02` | 1 | mxl_chill_blood_s80 | 0.8 | high | | like D2R `chillblood`, 0.11 |
| missile | `extra/explodingarrowdebris02` | 1 | ceiling_chunk_vanish_02 | 1 | high | | like D2R `andydebrisexplosion2`, 0.14 |
| missile | `famfadekingsblue` | 1 | bone_cast | 1 | medium | | like D2R `bonecast`, 0.18 |
| missile | `flamepillar` | 1 | ground_fire_small | 1 | high | | like D2R `vampirefirewall`, 0.07 |
| missile | `focusgreen` | 1 | mxl_furylightning_s120 | 1.2 | low | | like D2R `furylightning`, 0.33 |
| missile | `groundfirepurple` | 2 | ground_fire_medium | 1 | medium | recolour of groundfiremedium | like D2R `vampiremeteorfire`, 0.68 |
| missile | `iceberg` | 1 | blizzard | 1 | high | exact copy of a vanilla animation without HD effect | like D2R `blizzard4`, 0.08 |
| missile | `megalith` | 1 | sand_maggot_sand_pile | 1 | high | | like D2R `sand pile`, 0.19 |
| missile | `newfiremissile` | 9 | firebolt | 1 | high | recolour of iceblast | like D2R `firebolt`, 0.06 |
| missile | `psiorbexplode` | 1 | exp_arrow_explode | 1 | low | | like D2R `explodingarrowexp`, 0.50 |
| missile | `purplefrostnova` | 1 | frost_nova | 1 | medium | recolour of frostnova | the original's effect, 0.38 |
| missile | `ratrace` | 2 | mxl_expansion_bladefury_s70 | 0.7 | medium | | like D2R `bladefragment1`, 0.29 |
| missile | `sigil_engaging` | 1 | light_beams | 1 | medium | | like D2R `denofevillight`, 0.08 |
| missile | `somebluething` | 11 | furylightning | 1 | high | recolour of lightningstrike | like D2R `furylightning`, 0.20 |
| missile | `sparklez1` | 1 | mxl_diablo_lightning_s80 | 0.8 | high | exact copy of tiger_strike_a | like D2R `diablight`, 0.21 |
| missile | `sparklez2` | 2 | mxl_lightning_strike_s130 | 1.3 | medium | exact copy of tiger_strike_c | like D2R `lightninghit`, 0.47 |
| missile | `sunfiremedium` | 5 | ground_fire_medium | 1 | high | recolour of groundfiremedium | like D2R `meteorfire`, 0.20 |
| missile | `teethexplodegreen` | 1 | teethexplode | 1 | medium | recolour of teethexplode | the original's effect, 0.36 |
| missile | `whiteorbglowing` | 1 | bone_spirit_explode | 1 | medium | | like D2R `hellfireexa`, 0.18 |
| overlay | `extra/evilaura` | 1 | warlock/healthlink | 1 | high | | like D2R `healthlink`, 0.14 |

## 5. Gaps

**Art that exists nowhere: owner decision 2026-10-29 (lane unporteda).** Median draws nothing for a row whose art file exists
nowhere. The port keeps that **only for rows that no player skill (class or item-given) and no monster skill reaches**; a row a skill
uses points at similar existing art so the skill shows something. `tools/art_fix.py` does both before the HD maps run (`DRAW_NOTHING`:
art `null`, nothing in classic or HD; `REDIRECT`: the stand-in, which `missile_hd.py` / `effects_hd.py` then map like any D2R art).
Reach was traced through skills.txt (srv / clt missile and overlay columns), the missiles.txt sub / hit / explosion chains, states'
overlays, monstats Skill1-8 and Miss*, and item properties naming the skill by name or id (uniques, sets, runewords, affixes).
Typos and conversion slips of an existing file (`expansion|baaldeathghostie01`, `extra\lifedrain.dcc`) are repairs, not missing art.

| Kind | Row | Median's art | Who uses the row | Now |
|---|---|---|---|---|
| missile | `combatshotarrow` | `TeethExplodeYellow` | nothing | draws nothing |
| missile | `whyaretherealways` | `XXXXX` | only `snakeshieldspawner`'s chain, which no skill fires | draws nothing |
| missile | `twinklesmash` | `LazBloodMissile` | nothing | draws nothing |
| missile | `mythalexplode` | `DopplezonExplodeX` | nothing | draws nothing |
| missile | `cherubcenter` | `cherub` | Mon Cherub Avatar, which no monster, item or skill has | draws nothing |
| overlay | `laststandhit` | `DopplezonExplodeBlue` | nothing | draws nothing |
| overlay | `mortalstrikehit` | `DopplezonExplodeLilac` | nothing | draws nothing |
| overlay | `cc_dust` | `CeilingChunkVanish01` | nothing | draws nothing |
| overlay | `gorecarpet` | `gore20` | nothing | draws nothing |
| missile | `searingorb` | `GreenFlare` | Searing Orb (unique The Sentinel's Sorrow, Cornerstone; Supernature, Blades of Light) | `fireball` (orange orb, 16 directions) |
| missile | `sunspear2` | `TeethExplodeYellow` | Sunspear (runeword Dragonfly, Cornerstone) | `teethexplode` (the vanilla burst Median recoloured) |
| missile | `seismicfieldexplode` | `DopplezonExplodeX` | Seismic Field (Assassin), Enemy Singularity (`l_slayer`) | `dopplezonexplode` |
| missile | `silverstreak`, `silversecondary` | `extra\SpikeFiendMamaMissile` | Silver Streak (runeword Araboth, set Testament of the Apes, Cornerstone) | `extra\spikefiendmamamissle` (the file Median misspelt) |
| missile | `freezestormboomexplode` | `Extra\IceStormImpactVar3` | Hailstorm (Izual) | `extra\icestormimpactvar03` (the file Median misspelt) |
| missile | `nephalemweapons` | `AndarielFlameDeath2` | Nephalem Weapons (Barbarian) | `andarielflamedeath` (D2R has the first variant only) |
| overlay | `paganheartcast` | `extra\AuraResistColdCast` | state `purifyingspring` of Pagan Heart (runeword Endor, unique Eko Eko, Cornerstone) | `auraresistcoldcast` (the file, without Median's wrong folder) |
| overlay | `bloodwytch` | `Pentacle` | Lava Pit (Amazon) | `blackpentacle` (Median's own pentacle) |
| overlay | `splat2` | `extra\GenericSplash` | Angel of Death (Necromancer; `ancientbarb3`) | `extra\generic_splash` (the file Median misspelt) |
| overlay | `lazblood` | `LazBlood` | Offensive 2 Blink (`l_slayer`) | `bloodripple` (red blood ripple) |
| overlay | `whiteblinding` | `WhiteBlinding` | Summon Veil King, Summon Void Archon (Necromancer), Summon Overlord (runeword Leviathan, set Satanic Mantra) | `extra\whiteflash` |
| overlay | `threeflames` | `ThreeFlames` | Seal of Fire (uniques Demonsong, Dragon Tail, Demonlure, set item Warmage's Fireblade, Cornerstone) | `firecast_for_sorceress` |

`mephistooverlay` (overlay rows `mephisto`, `godcloud`) is a D2R classic file with no HD effect: D2R's own business, unchanged.

(`greatermummybreath` and `soulforgenova` are base-game files whose frames are empty; they are mapped.)

**Mapped but weak (low confidence)**: missile stand-ins `discoinferno` (17 rows), `dopplezonexplodegreen`, `focusgreen`,
`psiorbexplode`; reused choices `discoball`, `swarmhovers`, `vulturebolt`; overlays `expansion/oak_sage_overlay`,
`expansion/steamthick_a`, `extra/frogsplash`, `extra/necromindrecieve`. These want custom art or an owner look.

**Colour: gradient tint where the effect has a gradient (section 5a).** HD definitions have no tint field. Of the 20
recoloured missile DCCs that rows use, 11 have rows that draw a tinted copy of their vanilla effect (56 rows) and
`lightningcircles` draws the vanilla effect (colour close); the other 8 and the 3 overlay DCCs keep the prior or
nearest-colour effect.

**Row differences not shown.** `exact` and `prior` rows share an effect with a D2R row but may differ in Light, Trans, Vel,
Range or animation timing; an HD definition has no field for these.

**Not done.** Custom HD art (a `missile_art.py` flipbook; its in-game test was inconclusive). HD body animation states for
sequence skills (`hd_skill_anims.py`). Cross-kind use of a vanilla source (an overlay that is a vanilla missile animation).

## 5a. Gradient tints (`tools/hd_recolour.py`, lane tints 2026-10-29)

D2R draws an effect with PopcornFX `.particles` programs. Some take their colour from RGBA8 gradient textures
(`data/hd/vfx/textures/gradient/T_FX_*.texture`, 256 x 16), stored in the program as a length-prefixed path. For a provenance
row whose art is a recolour (`art_provenance.py` gives the hue / saturation / value shift), `effects_hd.py` asks `hd_recolour.py`:

- the vanilla effect's particle programs are read and their colourful gradients found (mean saturation 0.18 or more; grey and
  alpha ramps stay);
- a shifted copy of each gradient is written under a path of the same length (`..._<tag>.texture`, the tag hashes the shift and
  the source path), the program is copied with the paths swapped (`data/hd/vfx/particles/mxl/<name>_<tag>.particles`), and
  the definition is copied with its `VfxDefinitionComponent`s pointing at the copies (a missile under a name as long as the
  original's, an overlay under the row's own name);
- per-effect rules (`TINT_OVERRIDES`, keyed by the D2R definition and Median's art, lane hdlook2): a ramp named by the
  rule is recoloured even under the saturation floor, by mapping its brightness (darkest to brightest) onto explicit colour
  stops (`ramp_pixels`, alpha kept) instead of the hue shift; the effect's other gradients get the shift as before. One rule:
  `ice_blast` / `newfiremissile` maps `T_FX_IceBolt_gradient` (light blue to white, saturation 0.126) onto a fire ramp
  (deep orange, orange, warm yellow), bug #403;
- no file is larger than the D2R file it copies (same texture format and mip count, same program size, the definition's name
  length kept; `hd_recolour.fits` refuses a definition that would grow).

The particles and gradients are not in the baseline extraction: they are read through `fxpaths.d2r_file` (the shared D2R
cache; `tools/lane_setup.py` fills it from the committed list `tools/data/d2r_vfx_files.txt`, 60 files, or a run with
`MXL_SLOT=2|3|4` reads them read-only from that slot's CASC). Without them the build still runs and the rows fall back to the
nearest-colour scoring (`effects_hd.md` says how many files were missing). `py -3 tools/hd_recolour.py list` rewrites the list
after a run that read new files. `effects_hd.py --no-tint` switches the tint off.

Result of the build (2026-10-29): **15 tinted effects for 56 missile rows** (82 rows fell back to the nearest colour before,
26 now), 72 files, **8,737,907 bytes** (57 copies of particle programs and gradients, 15 definitions; none larger than its
D2R source). The particle programs are most of it (120-370 KB each): a shift of a ground-fire family copies its five
programs. Per effect and the rows that draw it: `work/mod/effects_hd.md` section "Gradient tints" and `work/mod/hd_recolour.json`.

| Median art | Rows | Now |
|---|---:|---|
| `blackfiresmall`, `blackfirebig`, `blackfiremedium`, `balefire`, `groundfirepurple`, `sunfiremedium` | 13, 3, 1, 3, 2, 5 | tinted copy of the vanilla ground fire / Diablo fire wall (`blackfiresmall`: 11 of its 13 rows; `templesmall`, `totemicpandafire` keep the prior choice) |
| `discoinferno` | 17 | tinted copy of the imp missile (was a low-confidence stand-in) |
| `newfiremissile` | 9 | tinted copy of `ice_blast` (the art is a recoloured Ice Blast) |
| `bonespiritpurple`, `purplefrostnova` | 2, 1 | tinted Bone Spirit, Frost Nova |
| `lightningcircles` | 1 | vanilla Hand of God (colour close, no tint needed) |
| `somebluething` | 11 | 2 rows tinted (`chainlightningBolt`); the other 9 keep the scored `furylightning` / `lightning_strike` |
| `teethexplodegreen`, `teethexplodered` | 1, 5 | no colour gradient in Teeth's programs: stand-in / prior |
| `boneghosttrail`, `greenexplode`, `greenflash`, `greenquake`, `lightandshadowstrike`, `lorenado` | 4, 1, 1, 2, 1, 1 | prior choice (source without a gradient or without an HD effect) |
| overlays `suncast`, `sunlight` (`sunburned` has no row) | 1, 1 | `necromindcast` has no colour gradient, `horadriclightbeam` no HD effect: prior choice |

Seen in game: not yet. The harness `missile` verb drew no effect on screen in four runs (docs/testing.md "Lane
tints"); offline the shifted gradients are in `mxl2012-runs/tints/offline/gradients_before_after.png`.

Seen in game (lane hdlook, player casts, docs/testing.md "Lane hdlook"): Balefire (green), Better Bloodstorm (purple), Ring
of Light and Holy Trap Advanced (pale gold) look as in classic; the fire bolt effect `mxl_ice_blast_cb8e0f3` stays pale blue-white
(bug #403: its main ramp `T_FX_IceBolt_gradient` is under `MIN_SAT` and is not shifted). Lane hdlook2: the rule above makes
the effect `mxl_ice_blast_c913a3d` (one more file, the fire ramp; 73 files, 8,754,335 bytes); the other 14 effects' files
are byte-identical to a build without the rule (SHA-1 list of every file `hd_recolour.json` names, and of the whole
`work/mod/data/hd` tree: only `missiles.json` and the fire bolt's own five files differ). In game: docs/testing.md "Lane hdlook2".
Lane hdlook3 (bug #404): a second rule, `frost_nova` + `purplefrostnova` (Dark Power's nova, `darkpowernova`), maps Frost
Nova's only colour ramp `T_FX_Bluelightning_Gradient` (pale light blue) onto a violet ramp (`VIOLET_RAMP`: deep violet to
lavender); the hue turn alone gave a pale indigo. New effect `fro_470248` (was `fro_c7ee0d`). Proof as for #403: the whole
`work/mod/data/hd` tree (846 files) built with and without the new rule differs only in `missiles.json` and Frost Nova's own
three files (definition, particles, ramp); the build without it is identical to main's (SHA-1 of every `hd_recolour.json` file).
In game: docs/testing.md "Lane hdlook3".

## 6. Not verified in the game

Nothing was run. Open for this port: whether stand-in definitions load and draw without new errors, the look of single
stand-ins, whether D2RLoader serves the generated `hd/` files from the mod folder, and whether the rewritten `overlay.txt` `Character`
column makes the overlays appear.

## 7. Files

| File | From | Change |
|---|---|---|
| `tools/dcc.py` | scaffold | none: main's scaffold copy is used as is |
| `tools/art_provenance.py` | adapted | paths through `fxpaths`; output to `work/mod/` (as in the build) |
| `tools/effects_hd.py` | adapted | paths through `fxpaths`; no PalShift; gradient tint through `hd_recolour` (lane tints; `--no-tint`); own `read_tsv` and `check_inputs` (no CASC); `LOOKALIKE` from `missile_hd.py`; art-level reuse (`Prior`); `no-art` class; provenance words and original-effect credit; whole `overlay.txt` `Character` rewrite as a copy; art -> effect table |
| `tools/hd_recolour.py`, `tools/d2r_texture.py` | adapted (lane tints) | D2R vfx through `fxpaths.d2r_file` (shared cache, `tools/data/d2r_vfx_files.txt`) instead of an open CASC at import; dry run (`out=None`); same-length definition names; texture tags per source; size check; `list` and `clean`. Tests `tools/tests/test_hd_recolour.py` |
| `tools/fxpaths.py`, `tools/build_effects.py`, `tools/test_effects_hd.py`, `tools/requirements-fx.txt` | new | |
| `data/hd-effects-map.tsv` | new | the committed mapping table (558 art files) |
| `data/hd-effects-picks.tsv` | new (lane hdfx2) | hand-picked stand-ins, an input of `effects_hd.py` (section 9) |

Not ported: `missile_hd.py`, `missile_art.py`, `hd_skill_anims.py`, `palshift.py`, `art_fix.py`
(reasons in section 3).

Tests: `py -3 -I tools/test_effects_hd.py` (28 unit tests: key normalisation, word tags, scoring, scaling, definitions, table
reading, `overlay.txt` rewrite, reuse rules, hand picks, and a check of a finished run); `tools/art_provenance.py --selftest`
(passes); `tools/build_effects.py --check-only` (every row has an existing effect, every DCC is in the table, every in-use
missile and overlay art is D2R's own or in the table, every hand pick shows in the table).

## 8. Open questions for the owner

1. ~~Missing art (section 5)~~ owner 2026-10-29: draws nothing only on rows no player or monster skill uses, a stand-in elsewhere (section 5).
2. Gradient tints (section 5a) add 8.7 MB of copied particle programs: keep all 15, or only the ones that show (the owner's
   look at `mxl2012-runs/tints/`)?
3. The 39 DCCs no row references: dead art, or used by a path the tables do not show (skills or monsters by code)?
4. Hand picks (section 9) where only the colour is off (Judgement gold -> blue-white, Hammerstrike red -> pale, Lorenado green
   -> grey): good enough until custom art, or a gradient tint where the effect has one?

## 9. Early skills checked by eye, hand picks (lane hdfx2, 2026-10-29)

**Method.** Every class skill with a required level up to 24 (Normal Act 1-2 and the main trees: 112 skills) was walked from
`skills.txt` to the missiles it fires (with their sub, hit and explosion missiles), its overlays and the overlays of its
states. For each art that is not D2R's own, Median's classic frames were rendered next to the classic art the HD effect stands
for (same scale per pair, 5 frames each): 142 pairs, then 96 candidate effects for the bad ones. The renders are scratch
(not committed). A pick goes into `data/hd-effects-picks.tsv` (kind, art, effect, scale, confidence, reason), which
`effects_hd.py` applies as class `hand` after `exact` and before the other classes. The table is rewritten each build, so the
picks live in that input file, not in the table. An `exact` art (D2R draws it itself) is never picked.
`tools/build_effects.py` checks that every pick shows in the table.

**Changes: 37 art files** (31 missile, 6 overlay; 94 missile rows and 7 overlay rows). Early skills affected per class:
Amazon 8, Assassin 2, Barbarian 6, Druid 14, Necromancer 5, Paladin 10, Sorceress 5 (50; a skill counts once per class).
"Old" is the table's effect before (the most common one when the rows differed); a scale shows in the `mxl_<model>_s<pct>`
name and is left out here.

| Class | Skills (req. level) | Kind | Art | Old | New | Why |
|---|---|---|---|---|---|---|
| Amazon | Ghost Arrow (1), Barrage (6), Phalanx New (12), Great Hunt (24), Wyrmshot (24); Druid: Quill Storm (6), Spore Shot (12), Nova Shot (24) | missile | `boneghosttrail` | exp_arrow_explode | yellow_ball_glow_2 | small pulsing golden glow; the old effect is a fiery burst |
| Amazon | Magic Missiles (1); Druid: Trap Rat Form, Treewarden Form (1), Pummel, Quill Storm (6), Egg Trap (12), Wildfire (18), Thorn Wall, Summon Acid Devils (24); Necromancer: Summon Shadows (1), Summon Rampagor (6), Summon Lamia (12); Paladin: Mind Flay (6), Dark King (24) | overlay | `mooncast` | warlock/warlock_fire_cast_1 | necro/cast_familiar | white sparkle cast flash; the old one is an orange fire cast |
| Amazon | Fairy Ring (24) | missile | `expansion/deathsentrymissile` | skull_left | expansion_throwing_star_missile | a small spinning shuriken, not a flying skull |
| Amazon | Hyena Strike (6); Necromancer: ParasiteSkill (18) | missile | `littleredball` | expansion_imp_fireball | expansion_imp_fireball | one of two rows had a meteor rock: every row now takes the imp fireball |
| Assassin | Bionetic Slam (12) | missile | `psiorb` | expansion_dethsentry_02 | ice_orb | blue glowing sphere; the old one is a scatter of sparkles |
| Assassin | Bionetic Slam (12) | missile | `psiorbexplode` | exp_arrow_explode | bighead_lightning_explosion | blue sphere bursting with lightning; weak stand-in, see below |
| Assassin | PsionicSkill (18) | missile | `biglightning` | lightningbolt_big | bighead_lightning_missile | a tangled ball of lightning, not a vertical column |
| Barbarian | Bear Claw (1), Stampede (6), Rebound (12) | missile | `extra/cursemissle` | skull_poison | firebolt | bright star with an orange flame tail, not a green poison skull |
| Barbarian | Aerials Disaster (1) | missile | `expansion/moltenfragmentd` | expansion_rock_lava_pool | meteor | small glowing rock chunk, the size of the meteor's rock; not a lava puddle |
| Barbarian | Shower of Rocks (18) | missile | `extra/explodingarrowdebris01` | bone_cast | ceiling_chunk_vanish_02 | faint grey rock dust on the ground, as already chosen for `debris02`; not a blue spark |
| Barbarian | Stormblast (24) | missile | `lightningexplosion` | lightningbolt_big | bighead_lightning_explosion | lightning spreading from a centre, not a column |
| Druid | Elemental (1) | missile | `elemental` | expansion_molten_boulder_roll | ground_fire_medium | an upright fire figure, not a rolling boulder |
| Druid | Laughing Ghost (1) | missile | `laughingghost` | rock_small | expansion_baaldeathghostie_01 | a flying ghost, not a thrown rock |
| Druid | Pummel (6) | missile | `extra/explodingarrowdebris03` | exp_arrow_explode | ceiling_chunk_vanish_02 | grey rock dust, not a fiery burst |
| Druid | Quill Storm (6) | missile | `extra/spikefiendmamamissle` | arrow | spike_fiend_missle | a flying quill; D2R's spike fiend quill is the same kind of art |
| Druid | Wildfire (18) | missile | `doomsmoke` | meteor_tail | fire_smoke | grey smoke wisps, not a fire trail |
| Druid | Mythal (18) | missile | `sparklez1` | diablo_lightning | dopplezon_explode | scattered red sparkles, not Diablo's red lightning |
| Druid | Idol2Scosglen (24) | missile | `sparklez2` | lightning_strike | expansion_impmissile_01 | red star burst, not a blue lightning strike |
| Necromancer | Deathlord (24); Paladin: Scourge (24) | overlay | `extra/frogsplash` | common/surge_hex_explode | monster/vulturedemonfeathers | grey splash of small bits, not an orange fire burst; weak stand-in |
| Paladin | Judgement (1) | missile | `lightandshadowstrike` | skull_poison | lightning_strike | the same jagged bolt in shape and size; was a green poison skull. Colour stays blue-white (gold in classic) |
| Paladin | Searing Light (1) | missile | `greenflash` | exp_arrow_explode | teethexplode | a white flash opening into a ring |
| Paladin | Hammerstrike (6) | missile | `extra/cursehit` | meteor_tail | teethexplode | small star flash; colour stays pale (red in classic) |
| Paladin | Holy Trap Advanced (12) | missile | `extra/shamanhealmissile01` | grim_ward_medium_start | yellow_ball_glow_2 | golden glow ball, not a skeleton rising from blood |
| Paladin | Pillar of Faith (18) | missile | `extra/missileflamesword` | fire_arrow | fire_arrow | a small flaming blade; one row had the Fire Nova burst |
| Paladin | Slayer (18), Dark King (24) | overlay | `slayercloud` | common/druid_fire_cast_1 | monster/fetishdeath_2 | grey smoke cloud, not an orange fire cast |
| Paladin | Colosseum (24) | missile | `tinyflame` | expansion_rock_lava_pool | ground_fire_small | a small flame on the ground, not a lava puddle |
| Sorceress | Lorenado (1) | missile | `lorenado` | expansion_overseer_missile | expansion_tornado | the art is Tornado's frames in green; was a green orb. Tornado has no colour gradient: it stays grey |
| Sorceress | Lorenado (1) | missile | `flipbook` | lightningbolt_big | expansion_hurricane_rocks | a few small flying bits (low confidence) |
| Sorceress | Miasma (12) | missile | `gore20` | exp_arrow_explode | sand_maggot_dirt_pile | a flat brown patch on the ground; D2R has no ground-gore effect (low) |
| Sorceress | Miasma (12) | overlay | `poisondark` | common/curseconfuse | common/poisonhit | green-yellow poison cloud, not the Confuse curse's sparkles |
| Sorceress | Firedance (24) | missile | `bonfire` | expansion_armageddon_fire | ground_fire_small | a burning pile on the ground, not a falling meteor |
| Sorceress | Bladestorm (24) | missile | `scimitar6` | lightningbolt_big | expansion_bladefury | a small spinning blade, not a lightning column |
| Sorceress | Swarm (24) | missile | `swarmhovers` | blue_nova_b | poison_sparks | faint specks hovering over an area (a poison skill); weak stand-in (low) |
| (none early) | | missile | `discoball` | skull_left | yellow_ball_glow_2 | a small glowing orb whose colour cycles in classic; weak stand-in |
| (none early) | | missile | `focusgreen` | furylightning | expansion_catapultpoisonbomb | green star burst with sparkles; weak stand-in |
| (none early) | | overlay | `expansion/steamthick_a` | common/psychic_hammer_hit | common/ice_explode | a pale cyan cloud; weak stand-in (low) |
| (none early) | | overlay | `extra/necromindrecieve` | common/lightning | common/shrine_mana_regen | a soft blue glow over the target; weak stand-in |

Skill names are the game's strings; `PsionicSkill`, `ParasiteSkill` and `Idol2Scosglen` have none (the row name is shown).

**Seen in game (lane hdlook3, player casts, docs/testing.md "Lane hdlook3").** Firedance (`bonfire`), Hammerstrike
(`extra/cursehit`) and Swarm (`swarmhovers`) look right; Miasma's `poisondark` overlay glows green on the target. Judgement
(`lightandshadowstrike`) draws its bolt below the target (bug #481) and Lorenado's `flipbook` pick draws next to nothing where
classic has a cloud of green orbs, its tornado stays grey (bug #482). Not seen: Bear Claw (no `bearbolt` made), `gore20`
(no `newhexgraphical` made), the Magic Missiles cast flash (covered by the missiles) and `expansion/steamthick_a` (the
Skeletons' Nightmare curse not told apart). No colour fix was cheap: hand picks are not tinted, `lightning_strike` has only
grey mask gradients and `teethexplode` none.

**Weak stand-ins (the 11 low-confidence arts of section 4 and `data/hd-effects-map.tsv`).** Re-picked (above): `focusgreen`,
`psiorbexplode`, `discoball`, `swarmhovers`, `expansion/steamthick_a`, `extra/frogsplash`, `extra/necromindrecieve`. Kept:

- `discoinferno` (17 rows) -> expansion_impmissile_01: the art is a recolour of the imp missile, so the effect has the same
  shape; only the colour differs (the effect has no colour gradient to tint).
- `dopplezonexplodegreen` -> dopplezon_explode: the same explosion in green; same shape family, colour differs.
- `vulturebolt` -> its prior choice: D2R has no flying-bird missile; it needs custom art.
- `expansion/oak_sage_overlay` -> common/oak_sage: the same role (Oak Sage's spirit); D2R has no greener look-alike.

**Checked and kept** (the HD effect is fine): `teethexplodered` (same shape, colour differs), `suncast`, the `balefire` and
`sunfiremedium` tints, `somebluething`, `violetlightning`, `extra/familiarfade`, and the other `exact` and `provenance` arts of
these skills.

**No D2R look-alike, custom art needed** (kept at their current choice): Avatar, Boiling, Broadsider, `demiphantom`,
`egg_alive` / `egg_dead`, the tower and turret arts (`towerstanding`, `towerdestroyed`, `turret*`), `legiontile`,
`littlespider`, `nehlthak_hole_light`, `blackholeexplode`, `ghostlights`, `blackpentacle`, `heatwave`, `bigbass`,
`baaldeathhead01`.

**Not seen in game yet.** All four game slots were busy during this lane, so the picks are judged from the offline renders
only. Open: whether the picks where only the colour differs (question 4) read well enough, and the five low-confidence picks.


## 9a. Tinted hand picks (lane picktint, 2026-10-29)

`data/hd-effects-picks.tsv` has two optional columns after the reason:

- `tint`: a ramp of `hd_recolour.RAMPS` (`fire`, `violet`, `gold`, `green`, `red`), optionally with `:` and the gradient stems
  to recolour joined by `+` (`gold:T_FX_LightBlue_Gradient_02+T_FX_Max_Grad_01`). Without stems the effect's colourful gradients
  (saturation `MIN_SAT` or more) are mapped; with stems exactly those, grey ones too. `hd_recolour.pick_spec` makes the same kind
  of spec as `TINT_OVERRIDES` (`ramp_pixels`, alpha kept, nothing else of the effect changed, same-length paths, size check), and
  `effects_hd.py` writes the copy as for a provenance tint; the reason in `effects_hd.md` says "gradient tint ..." or "tint ... not
  made (why)". `effects_hd.py --no-tint` switches these off too.
- `rows`: missile rows, comma-separated, that the line applies to (a row-scoped line wins over the art's own line and over the
  `exact` class, so rows of an art D2R draws itself can be given another effect).

`build_effects.py` checks that every pick, scaled or tinted copy shows for its rows, and that an asked tint was made when no
D2R file was missing.

| Art (rows) | Skill | Pick | Tint | Bug |
|---|---|---|---|---|
| `lightandshadowstrike` (`zomgpewpewmallet`) | Judgement | `lightningstrike` (was `lightning_strike`) | `gold` on its blue ramp and its two flat white core gradients | #481 |
| `lorenado` | Lorenado | expansion_tornado | `green` on `T_FX_Brown_Dust_Gradient_03` | #482 |
| `flipbook` (`lorenadobookflip`) | Lorenado | `yellow_ball_glow_2`, size 2 (was expansion_hurricane_rocks) | `green` | #482 |
| `teethexplodered` | Magic Missiles and others | `yellow_ball_glow_2` | `red` | #483 |
| `teethexplode` (rows `magicmissile`, `magicbolt`, `monmagicmissile`, `monmagicbolt`, `mon2magicmissile`, `mon2magicbolt`, `nerfedmagicmissile`, `nerfedmagicbolt`, `newmmwave`, `newmmhit`) | Magic Missiles | `yellow_ball_glow_2`, size 1 | `red` | #483 |

`GOLD_RAMP`, `GREEN_RAMP` and `RED_RAMP` are new. A flat (one-colour) gradient maps to the ramp's top stop, so the gold ramp
ends in a saturated gold, not a pale one.

**Byte check.** `work/mod` built with main's picks file and the new code is identical to main's build (SHA-1 of every file; only
two stale scaled copies from earlier runs differ). With the new picks the existing files that change are `missiles.json` (20 keys:
the rows above and `deathcoil`, `deathmetal`, `queenidolcast`, `seismicchargeblink`, which also draw `teethexplodered`),
`effects_hd.md` and `hd_recolour.json`; the rest are new files of the five tinted effects. Tint totals: 19 tinted effects, 87
files, 9,875,908 bytes, none larger than its D2R source. The final gold step changed only the Judgement effect's own files.

**In game** (docs/testing.md "Lane picktint"): Magic Missiles red-orange, Lorenado's tornado and orbs green. Judgement's glow is
gold, its bolt core stays white: the core's colour is a constant in the particle program, not a gradient, so no texture tint
reaches it. The bolt drawn below the target is the missile's own path (classic draws the missile's light on the same spot).
