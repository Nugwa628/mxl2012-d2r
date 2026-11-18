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

## Behaviour notes

- The bars are drawn in HD (the author's projection) and, with patch 0003, in legacy graphics, with or without Legacy 16:9.
- Shipped config: the patched source's `enemy-health-bars.toml` (`show_full_health = false`), copied next to the build by
  `tools/build_enemyhealthbars.ps1` and shipped as `mods\mxl2012\d2rloader\config\enemy-health-bars.toml` (a `preserve` file).
- It reads game memory only: no hooks and no byte patches. The life value comes from the client's normalized life
  stat, so Median XL's large monster life cannot overflow it. Boss outlines come from MonStats flags.
- Head offsets come from the mod's loose `monstats.txt` / `monstats2.txt` (1839 monster types in D2R-XL 2012).
- It draws into its own transparent window over the game (the "standalone" renderer), or into MapSense's renderer when
  MapSense is installed.
