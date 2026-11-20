# Monster Display 1.0.18 by CelestialRayOne (bundled D2RLoader plugin)

Monster Display redraws the HD hover panel over a monster: a wider life bar with exact life and percent, level and type,
unique affixes in the game's own words, a resistance row (fire, lightning, cold, poison, magic, physical), and the
immunity line. Prime evils get a bar twice as wide with their own frame. Docs:
[docs/bundled-plugins.md](../../docs/bundled-plugins.md) "Monster Display".

- **Author:** CelestialRayOne (Bogdan Bulai), <https://github.com/CelestialRayOne>.
- **Source:** <https://github.com/CelestialRayOne/d2rloader_plugins>, `plugins/monster-display`, at commit
  `924072545985e0d1bef58c3362c1c1572531aa2e` (the commit Damage Overflow Fix comes from). We ship the author's release
  build from that commit unchanged: `release/d2rl-celestialrayone-monster-display.dll` (version 1.0.18) and
  `release/MonsterDisplay/` (three HD layouts and the frame sprites).
- **Licence:** MIT, "Copyright (c) 2026 Bogdan Bulai" ([LICENSE](LICENSE), shipped next to the DLL as
  `d2rl-celestialrayone-monster-display-license.txt`). Credit: README, NOTICE.md, CHANGELOG and docs/bundled-plugins.md.

| File | Size | sha256 |
|-|-|-|
| `d2rl-celestialrayone-monster-display.dll` | 119,296 | `bc5fa7d7ed6468981f8c165b8c3bdde49e475f68a8371d93e2f2eba3b566eaed` |
| `MonsterDisplay/` .json and .sprite files (31) | 133,027 | `afcf2de29d6edb09667efa59f36a0acfc3769715a481079bc3d09bea37f5a264` |

The second hash is the sha256 of the lines `<sha256>  <path>` (one per file, sorted, LF) of those 31 files.
`tools/package_release.py` (`MD`, `md_data_digest`) refuses any other bytes.

The source at that commit is 1.0.19. It only adds a lookup for another CelestialRayOne plugin (Summon Enhancements,
bound demons), which we do not ship. The release DLL at the commit is still 1.0.18, and that is the one tested.

## Where its files go

| From `release/` | In the package |
|-|-|
| `d2rl-celestialrayone-monster-display.dll` | `d2rloader/plugins/` |
| `MonsterDisplay/hudmonsterhealthhd_pc.json` | `mxl2012.mpq/data/global/ui/layouts/hudmonsterhealthhd.json` |
| `MonsterDisplay/hudmonsterhealthhd_controller.json` | `mxl2012.mpq/data/global/ui/layouts/controller/hudmonsterhealthhd.json` |
| `MonsterDisplay/hudmonsterhealthhd_controller_pc.json` | `mxl2012.mpq/data/global/ui/layouts/controller/pc/hudmonsterhealthhd.json` |
| `MonsterDisplay/monsterdisplayframes/*.sprite` | `mxl2012.mpq/data/hd/global/ui/panel/monsterdisplayframes/` |

The layouts replace the game's whole hover panel layout. Our own data has no `hudmonsterhealthhd.json`; `stage_md`
refuses to stage over one if a later change adds it.

## Where the files live

They are not in git (`.gitignore` excludes `*.dll` and `*.sprite`). `tools/package_release.py` takes the author's
`release/` folder (the DLL and `MonsterDisplay/` next to it), checked against the hashes above, from the first of these:

1. `--md DIR`,
2. the environment variable `MXL_MD_DIR`,
3. `<MXL2012_RUNS>/shared/monster-display-1.0.18/`.

To get them, clone the repository above, check out the pinned commit, and point `--md` at its `release/` folder.

## Our settings

`celestialrayone.monster-display.toml` is the author's default config (resistances `effective`: what the hovering
player's hits meet) with one change: `minion_hidden_affixes` also lists Median's 36 Ghostly, 37 Fanatic, 38 Possessed
and 39 Berserk. Median's monumod.txt passes those to minions (xfer 1), and the owner wants them hidden there like the
author's own list. This is a setting of the 1.0.18 DLL (ids 1 to 44), so no code change is needed. In the game today
the setting changes nothing you can see: these four are the game's champion types, and its affix name builder
(`0x1DFAE0`, which Monster Display calls) gives them no name, so they show on neither a boss nor a minion (tested on a
superunique given 36-39 for the test, docs/testing.md "Lane plug127"). The setting keeps them off minions if a later
build names them. It is a `preserve` file, so a player's changes survive Update and Repair. `tools/verify_package.py` checks that it
is on, in `effective` mode, and hides 36-39 on minions (`MD_MINION_HIDDEN`).

## How it decides to work

It hooks the hover panel builder (`0x0CEA50`) and the panel update (`0x1F84E0`). Both hooks check the expected bytes
first; it has no game-version or build check. In legacy graphics it changes nothing: the classic hover text stays as it
is. In game (lane plug127) mxl2012-core reported no plugin clashes.

To move to a new version, update `MD` (version, commit, size, hashes) in `tools/package_release.py` and this README,
diff the new default config against ours, and run the in-game check (docs/testing.md "Lane plug127").
