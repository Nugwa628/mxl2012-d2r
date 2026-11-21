# Classic animations in HD: a skill drawn by Median's own art (`tools/effects_classic.py`)

D2R-XL 2012 draws most of Median XL's missiles in HD with a D2R effect that looks alike (docs/hd-effects.md). For the
skills listed in `data/hd-effects-classic.json` the mod plays the classic animation itself: the same picture as legacy
graphics, upscaled, with the light the row has in `missiles.txt`. The skills: the Assassin's Bionetic Slam (skill 329)
Phalanx's golden archers (`legiontile`, bug #570; section 7) and the Barbarian stances' feathers (overlays
barb_1..4, bug #578; section 8). Method, measurements and the full research: `mxl2012-runs/hdtools/effects/REPORT.md`.

## 1. What the build makes

| Row | Classic art | In HD |
|-|-|-|
| `bioneticmover` (the flying orb) | `PsiOrb`, 17 frames, loops | `mxl_fx_psiorb`: one layer in the art's own colours, blue point light (reach 21) |
| `bioneticlargeboom` (the burst) | `PsiOrbExplode`, 11 frames, plays once | `mxl_fx_psiorbexplode`: three layers (red, green and blue level) that add up to the picture, blue point light (reach 6) |
| `bioneticdamage` (16 per cast, no picture) | none | `mxl_fx_light_blue2`: the blue point light only (reach 6) |
| `bioneticstar` (16 per cast, the white star and the rings) | `TeethExplode`, 13 frames, plays once | `mxl_fx_bioneticstar`: one layer, brightened so the 16 copies read as classic's one white star |
| `legiontile` (Phalanx's archers, a line of them per cast) | `LegionTile`, loops | `mxl_fx_legiontile`: three layers (red, green and blue level), yellow point light (reach 9) |

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
(`game_checks.py fx_card`). Not built: animations with different pictures per direction, overlays on units. Art that is
not additive (`Trans` other than 1) needs an `"opaque": "<why>"` line in the spec, since HD still draws it additive, and a
row other skills or monsters reach needs `"shared": "<why>"` instead of a private copy; both are checked by the build.

## 6. Known differences from classic (Bionetic Slam)

- The burst starts one frame (at most 50 ms) after the orb disappears; classic has no gap.
- The star's rim is paler than classic's deep blue and its white body rounder.
- HD's flash is equally strong in every cast; classic's varies from cast to cast.
- Measured in one place (the Blood Moor at night); gains may read differently on bright ground.

## 7. Phalanx's archers (`legiontile`, bug #570)

Phalanx New (skill 303), the old Phalanx and the monster skill Mon Bowless Phalanx all make `legionmaker`, which lays
lines of `legiontile`: a golden armoured archer standing on the ground. D2R has no effect that looks like it, so HD drew a
small gold glow and the archers looked missing. The row is marked `shared` (all three draw the same archer in legacy,
so HD gets it for all of them) and `opaque` (legacy draws it with `Trans` 0; in HD it is three additive colour layers,
so it reads as a bright golden spirit archer and the dark armour shows less than in legacy). About 0.92 MB (0.14 MB
compressed). Seen in game in HD and legacy on slot 2 (lane bugs128, `checks-20261121-172927-s2`; before:
`checks-20261121-172912-s5`).

## 8. Overlays: the Barbarian stances' feathers (barb_1..4, bug #578)

The spec's `overlays` (row of overlay.txt -> the same fields as a missile, plus an optional `texture`) are built the same
way, but each is written as the overlay's own HD file, `data/hd/overlays/<Character>/<row>.json` (type
`OverlayDefinition`, the effect entities without a unit root): D2R finds an overlay by its name, so this replaces what
`effects_hd.py` chose for it (the build's facts keep the old particle list as `was`). An overlay is one file for every
state, skill and monster that shows it, so the spec must mark it `shared`; its Filename must be the art.

The stances (Lion, Bear, Snake, Eagle and the other auras on states aura_1..6) show barb_1..4: Median's `vdfeathers`,
26 frames of dark grey feathers swirling round the unit, drawn with Trans 5 (D2's normal draw: opaque pixels, index 0
see-through). D2R's `vulturedemonfeathers` that HD used drew nothing visible on a player (lane bugs127). The parts are
`"blend": "alpha"`: the flipbook's renderer gets Transparent.Type AlphaBlend (2) instead of the template's Additive, the
atlas keeps the art's own colours (BC3) and a second atlas of the drawn pixels (`<texture>_mean_alpha`) is the AlphaMask
with AlphaOnly, as D2R's own raven feathers (`vfx_druidraven_spawn`: colour atlas plus alpha atlas, both alpha-blended).
So the feathers are dark as in classic. HD's exposure lifts an alpha-blended colour a lot: at gain 1.5 they came out pale
pink-grey, at 0.3 down to 0.02 dark grey (calibration run `/d2work/runs/bugs128/runs/checks-20261121-191954-s2`, one gain
per stance); the spec uses about 0.3 with a faint tint of each stance's light colour (barb_1 yellow, barb_2 red, barb_3
green, barb_4 orange) and keeps the small light of the same colour (reach 4). The four share both atlases
(`"texture": "mxl_fx_vdfeathers"`), about 0.25 MB compressed in all. Seen in game in the Rogue Encampment (`/d2work/runs/bugs128/runs/checks-20261121-192138-s2`): dark feathers swirl round the barbarian for the whole stance in HD, as in legacy. Before (lane bugs128's first stand-in, additive):
the feathers were lifted (gain 5) and glowed in the stance's colour, because an additive flipbook cannot draw dark.
