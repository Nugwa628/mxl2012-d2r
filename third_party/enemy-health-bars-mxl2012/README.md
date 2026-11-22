# Enemy Health Bars for D2R-XL 2012

**Enemy Health Bars** 0.2.6 is by **Graxy_TV** (graxytv): <https://github.com/graxytv/D2R-Over-the-Head-Health-Bars>, also on
the d2rloader.net hub. It draws compact health bars above hostile monsters in HD graphics. The owner has the author's
permission to ship it. Its licence is **GPL-3.0-only** (the `LICENSE` in the author's package). It builds on
SirCabby/D2RCabbyCodes (GPL-3.0; signatures and layout research), D2RLoader's PluginSDK (MIT), Dear ImGui 1.91.5 (MIT), and
the MapSense OverlayHost API from RuffDood/RuffnecKk-D2RLoader-Suite (MIT); see the package's `THIRD_PARTY.md` and `licenses/`.

## Source

The author's repository holds the release as one zip. Commit `e6b929bfa5c59e79e0cbabf898eb777f6d359132` ("Add files via
upload") adds `EnemyHealthBars-0.2.6-Reimagined-Share.zip` (sha256
`c0ed2aa43205202601ec8075f3043e6dada5f0992ab9423e2a6378ad4eec10f4`); the next commit (`9a18bd4`) deletes it. Inside it,
`source/EnemyHealthBars-0.2.6-Source.zip` (sha256 `8e26f4a9164f38d4f0970d1d4cd0e68c416c8df1272b01b1e1682195cd1acfa1`) is
the plugin's complete source with its build dependencies. That source matches the hub's 0.2.6 source file for file, except
for the README, the launcher add-on's `plugininfo.json`, and the plugin's author field ("Custom" in the repository's copy,
"Graxy_TV" on the hub).

`tools/build_enemyhealthbars.ps1` takes that zip from the pinned commit (`-Src`, `MXL_EHB_DIR`, or a clone into
`build/enemyhealthbars-repo`), checks both sha256 values, extracts the source into `build/enemyhealthbars-src`, applies the
patches here in name order, and builds it with the source's own CMakeLists.txt and its bundled PluginSDK. It also runs the
author's `policy_tests`. The output goes to `build/enemyhealthbars/`:

- `Release/d2rl-enemy-health-bars.dll`
- the author's `LICENSE`, `THIRD_PARTY.md` and `licenses/`
- `enemy-health-bars.toml`: the patched config (our defaults)
- `d2rl-enemy-health-bars-source.zip`: the patched source as built, with these patches and a `SOURCE.txt` that names the refs
  above. Under the GPL, a release that ships the DLL also ships this zip.

The author's repository is never changed. The patches keep their bytes (`.gitattributes`: `-text`), because the source mixes
CRLF and LF files.

| File | What it does |
|-|-|
| `0001-no-build-fingerprint.patch` | Removes the check of the game executable's TimeDateStamp / SizeOfImage, which refused every build but 3.3.93847 (owner rule: never tie a plugin to a build). The nine byte signatures it checks before reading anything stay, so a game whose code differs turns the bars off with the plugin's own "native signature mismatch" log line. The plugin info's author is set back to Graxy_TV, the version to `0.2.6+mxl2012`, and the build number is removed from the description |
| `0002-dev-keep-visible-unfocused.patch` | Adds the dev-only config key `dev_keep_visible_unfocused` (default `false`, not in the shipped config). When it is on, the standalone overlay keeps drawing while the game window is not the foreground window. Its window is then not topmost: it stays just above the game window (its owner) and below other programs. Background-mode test runs need this to capture the bars without ever focusing the game. With the key off, the plugin behaves as the author's (the overlay is hidden while the game is not focused) |
| `0003-legacy-placement-damaged-only.patch` | Bars in legacy graphics, with and without D2R Legacy 16:9: a monster's bar sits where the classic engine draws it (its client pixel position minus the view offset, raised by the monster type's classic `pixHeight` from monstats2, 56 when it has none), and the classic screen is fitted to the window height and centred, as D2R composes it (new `src/legacy_projection.h`, the same placement as our Floating Damage patch). The five game helpers it uses are found by expected bytes at load; a mismatch leaves legacy without bars (log line) and HD unchanged. It also makes bars only on damaged monsters the default (owner, 2026-11-16): `show_full_health` defaults to `false` in the plugin and its config, and the plugin's own key `show_full_health = true` shows them on every monster. Tests for both are added to the author's `policy_tests` |
| `0004-dirty-rect-idle-hidden.patch` | Makes the standalone renderer cheap (lanes fpstown and rel0130, 2026-11-22). The author's renderer sent its whole window (the game's size, 33 MB at 3840x2160) through `UpdateLayeredWindow` on every pass, even with no bar on screen and with the bars off; under Wine/X11 at 4K that held the game to about 36 instead of 85 FPS. Now: the window is made only when the first bar is drawn; with no bar it is hidden and nothing is sent; while bars show only the changed area is sent (`UpdateLayeredWindowIndirect` with `prcDirty`: where the bars were last time plus where they are now), and a window that was hidden gets one whole send before it shows again, so no old bar can stay behind. With the bars off (`enabled = false` or `enemybars off`) the renderer sends nothing and asks the game for no snapshots. The first 32 shows and hides go to the plugin's log with the number of sends. The send logic is a header without Windows calls (`src/present_plan.h`), tested in `policy_tests` (steps, and a simulated window that must always hold exactly the current bars) |
| `0005-mxl2012-uniques-filter-mode-keys.patch` | Bars only on uniques and bosses, and the mode for D2R-XL 2012's Controls action (lane rel0130b, 2026-11-23). New key `uniques_bosses_only` under `[bars]` (default and shipped `false`): `true` draws bars only on the monsters the plugin classes as unique (`Rarity::Unique`, the orange outline): unique and super unique monsters and bosses (the MonStats boss flag: act bosses, Median's ubers); champions (blue outline) and a unique's minions get none. With `show_full_health` this gives four visible modes. Two exports for mxl2012-core's action "Enemy Health Bars Mode" (`plugin/src/overlay_keys.cpp`): `Mxl2012EnemyBarsModeV1()` returns the mode bits (`0x80000000` valid, 1 `enabled`, 2 `show_full_health`, 4 `uniques_bosses_only`; 0 = not running) and `Mxl2012EnemyBarsSetModeV1(bits)` applies them at once (as `enemybars on/off`) and saves the three keys in the player's `enemy-health-bars.toml`, keeping the rest of the file (new `src/mode_config.h`; a file without `uniques_bosses_only` gets the line after `[bars]`); it returns 1 saved, 0 applied but not saved, -1 refused. The rarity is now read before the visibility test. `enemybars` status names the mode. Tests in `policy_tests` (the filter for each rarity, the key rewrite with CRLF and LF files, comments, other tables and a missing key) |

## Behaviour notes

- The bars are drawn in HD (the author's projection) and, with patch 0003, in legacy graphics, with or without Legacy 16:9.
- Shipped config: the patched source's `enemy-health-bars.toml` (`show_full_health = false`, `uniques_bosses_only = false`), copied next to the build by
  `tools/build_enemyhealthbars.ps1` and shipped as `mods\mxl2012\d2rloader\config\enemy-health-bars.toml` (a `preserve` file).
- It reads game memory only: no hooks and no byte patches. The life value comes from the client's normalized life
  stat, so Median XL's large monster life cannot overflow it. Boss outlines come from MonStats flags.
- Head offsets come from the mod's loose `monstats.txt` / `monstats2.txt` (1839 monster types in D2R-XL 2012).
- It draws into its own transparent window over the game (the "standalone" renderer), or into MapSense's renderer when
  MapSense is installed. With patch 0004 that window exists only once a bar has been drawn, is hidden while no bar shows,
  and gets only the changed area of each frame.
