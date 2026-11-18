# Classic animations in HD: a skill drawn by Median's own art (`tools/effects_classic.py`)

D2R-XL 2012 draws most of Median XL's missiles in HD with a D2R effect that looks alike (docs/hd-effects.md). For the
skills listed in `data/hd-effects-classic.json` the mod plays the classic animation itself: the same picture as legacy
graphics, upscaled, with the light the row has in `missiles.txt`. The first and so far only skill is the Assassin's
Bionetic Slam (skill 329). Method, measurements and the full research: `mxl2012-runs/hdtools/effects/REPORT.md`.

## 1. What the build makes

| Row | Classic art | In HD |
|-|-|-|
| `bioneticmover` (the flying orb) | `PsiOrb`, 17 frames, loops | `mxl_fx_psiorb`: one layer in the art's own colours, blue point light (reach 21) |
| `bioneticlargeboom` (the burst) | `PsiOrbExplode`, 11 frames, plays once | `mxl_fx_psiorbexplode`: three layers (red, green and blue level) that add up to the picture, blue point light (reach 6) |
| `bioneticdamage` (16 per cast, no picture) | none | `mxl_fx_light_blue2`: the blue point light only (reach 6) |
| `bioneticstar` (16 per cast, the white star and the rings) | `TeethExplode`, 13 frames, plays once | `mxl_fx_bioneticstar`: one layer, brightened so the 16 copies read as classic's one white star |

- Each layer is one camera-facing additive billboard whose atlas frame comes from the particle's age at 25 frames per
  second (`tools/effect_flipbook.py`). The frames are upscaled 2x with Lanczos: a glow keeps its soft rim, which an AI
  upscaler redraws as a hard outline. No GPU and no model is needed, so every build makes the same bytes.
- Files: `data/hd/vfx/textures/mxl/flipbook/`, `data/hd/vfx/textures/gradient/mxl_fb_*`,
  `data/hd/vfx/particles/mxl/flipbook/`, `data/hd/missiles/mxl_fx_*.json`. 22 files, about 3.96 MB (0.69 MB compressed).
- The particle files are edited copies of two D2R files read from the shared D2R cache
  (`chill_blood_puff.particles` for a flipbook, `vfx_candle_light.particles` for a light). Both are in
  `fxpaths.CACHED_FILES`, so `tools/lane_setup.py` checks them and fetches a missing one (`--cache-from-slot N`).

## 2. No other skill changes

Classic's white star is not the burst: it is 16 `teethexplodeblue` explosions, a row that 45 other Median missiles
make too (Batstrike, Scorpion Blade, Wychwind, Shuriken Flurry, Hunting Banshee, Bladestorm, Enfilade, monsters). In HD
16 dim copies do not add up to a white star the way classic's do, so the star's picture is brightened for the pile; one
such copy would be too bright anywhere else.

So Bionetic Slam gets a row of its own: `effects_classic.py rows` adds `bioneticstar` to `missiles.txt`, a copy of
`teethexplodeblue` in every column but the name and the id, and `bioneticdamage.ExplosionMissile` names it. Classic and
legacy graphics draw exactly what they drew. `teethexplodeblue` itself, its HD effect and every other skill stay as they
were.

The build enforces it: `effects_classic.py build` refuses when a skill outside the spec's `skills`, a missile outside the
spec, a monster, a state or an item reaches one of the spec's rows, and when a private row is no longer a copy of its
source. `py -3 tools/effect_chain.py <skill> --hd work/mod/data/hd/missiles/missiles.json` prints what every row of a
skill draws.

## 3. Build steps

`tools/build.py` runs both by default, with no switch:

1. `effects_classic.py rows` before `effects_hd.py`: the private rows, in both table banks.
2. `effects_classic.py build` after `missile_release.py`: the files, and the rows pointed at them in
   `data/hd/missiles/missiles.json`. `work/mod/effects_classic.json` lists the files and bytes per row and what the row
   drew before (`was`).

`py -3 tools/effects_classic.py check` checks a finished build without writing.

## 4. Turning it off

Set `"enabled": false` in `data/hd-effects-classic.json` and rebuild: both steps do nothing, no row is added, and Bionetic
Slam is drawn by the stand-in effects it had before. An installed mod can be put back the same way without a rebuild by
pointing the four rows of `data/hd/missiles/missiles.json` at their `was` models.

## 5. Adding a skill

Not automatic yet. Per skill: list its chain (`tools/effect_chain.py`), add its rows to the spec, give a shared row a
private copy, and fit the gains (`tint`) and the light power by comparing HD with legacy frames
(`game_checks.py fx_card`). Not built: animations with different pictures per direction, overlays on units, art that is
not additive (`Trans` other than 1).

## 6. Known differences from classic (Bionetic Slam)

- The burst starts one frame (at most 50 ms) after the orb disappears; classic has no gap.
- The star's rim is paler than classic's deep blue and its white body rounder.
- HD's flash is equally strong in every cast; classic's varies from cast to cast.
- Measured in one place (the Blood Moor at night); gains may read differently on bright ground.
