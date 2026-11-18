# Damage Overflow Fix 2.4.0 by CelestialRayOne (bundled D2RLoader plugin)

Damage Overflow Fix makes D2R's damage math 64-bit where the game multiplies in 32 bits. Without it, a hit whose damage
passes about 8.39 million (2^31 in 1/256ths) wraps and deals 0–2 damage. With it, the hit is capped at 8,388,607 instead.
Below that limit every result is bit-identical to the game's own. Docs: [docs/bundled-plugins.md](../../docs/bundled-plugins.md)
"Damage Overflow Fix".

- **Author:** CelestialRayOne (Bogdan Bulai), <https://github.com/CelestialRayOne>.
- **Source:** <https://github.com/CelestialRayOne/d2rloader_plugins>, `plugins/damage-overflow-fix`, at commit
  `924072545985e0d1bef58c3362c1c1572531aa2e`. We ship the author's release build from that commit unchanged:
  `release/d2rl-celestialrayone-damage-overflow-fix.dll`.
- **Licence:** MIT, "Copyright (c) 2026 Bogdan Bulai" ([LICENSE](LICENSE), shipped next to the DLL as
  `d2rl-celestialrayone-damage-overflow-fix-license.txt`). Credit: README, NOTICE.md, CHANGELOG and docs/bundled-plugins.md.

| File | Size | sha256 |
|-|-|-|
| `d2rl-celestialrayone-damage-overflow-fix.dll` | 111,616 | `cfc95e328230c86d4659f04d223552afd90f3fd4990f3fd62c48e9770f144a58` |

`tools/package_release.py` (`DOF`) refuses any other bytes.

## How it decides to work

It patches about 100 sites in the game and the stat engine in D2RCore.dll. Before patching a site, it checks that the bytes
there are exactly the ones it expects. A site that does not match is skipped and logged, and the game is not touched there.
It has no game-version or build check, so it meets our rule never to tie a plugin to a build. In game (lane plug125) it
logged "104 site(s) active, 1 disabled, 0 failed", and mxl2012-core reported no plugin clashes.

## Where the DLL lives

It is not in git (`.gitignore` excludes `*.dll`). `tools/package_release.py` takes it, checked against the hash above, from the
first of these:

1. `--dof DIR`,
2. the environment variable `MXL_DOF_DIR`,
3. this folder (`third_party/damage-overflow-fix/d2rl-celestialrayone-damage-overflow-fix.dll`, a local copy, git-ignored),
4. `<MXL2012_RUNS>/shared/damage-overflow-fix-2.4.0/`.

To get it, clone the repository above, check out the pinned commit, and copy `release/d2rl-celestialrayone-damage-overflow-fix.dll` here.

## Our settings

`celestialrayone.damage-overflow-fix.toml` is the author's default 2.4.0 config with two changes (owner decision, 2026-11-16):

- `debug_log = false`: the default writes a `.hits.log` with a record for every hit (up to 256 MB).
- `log_each_site = false`: one summary line in the plugin log, instead of one line per patched site.

Everything else is the author's default, including `leech = true`. It is a `preserve` file, so a player's changes survive Update
and Repair. `tools/verify_package.py` checks these three keys in the package.

To move to a new version, put the new DLL here, update `DOF` (version, commit, size, hash) in `tools/package_release.py` and
this README, diff the new default config against ours, and run the in-game check (docs/testing.md "Lane plug125").
