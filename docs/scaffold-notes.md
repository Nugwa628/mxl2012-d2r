# Scaffold notes (lane scaffold, 2026-10-28)

What the repository's starting tooling is, what was left out, and what still needed a human look when it was set up.

`MXL_D2R_EXTRACT` overrides the D2R `extract/d2r/93847` baseline (default from the machine-local config, docs/setup.md).
`MXL2012_RUNS` overrides the runs directory used by `verify_original.py`; its default is `mxl2012-runs` adjacent to the main
checkout or worktree directory.

## Names

| Thing | D2R-XL 2012 |
|---|---|
| Display name | D2R-XL 2012 |
| Mod folder / mod id | `mxl2012` (`<D2R>\mods\mxl2012`) |
| Save folder | `...\mods\mxl2012-sN` (slots 2 and 3 only) |
| Repo | `mxl2012-d2r` (forge `WerdeGames/mxl2012-d2r`, private; GitHub mirror later) |
| Plugin | `mxl2012-core` (`mxl2012-core.dll`, `PluginVersion` 0.1.0), console command `mxl2012` |
| Dev switch files | `mxl2012-testharness.txt`, `mxl2012-core-off.txt` |
| Downloader | `D2R-XL-2012-Downloader.exe`, data `%LOCALAPPDATA%\mxl2012`, marker `mxl2012-install.json` |
| Release archive | `D2R-XL-2012-<v>.7z`, top folder `mxl2012/` |
| Download site | `files.werdegames.com/mxl2012/` (backup origin `dl.werdegames.com/mxl2012/`) |
| String namespace | `mxl2012` (docs/strings.md; the strings lane's tools) |
| Test character | `Mxl2Barb` |
| Assets | `assets/` + `assets.lock` (`tools/asset_pack.py`; pack layout `assets/median/`, `assets/hd/`); no pack and no `assets.lock` yet, `assets.lock.example` shows the format |

Unchanged on purpose: the env var names `MXL_*`, the C++ namespace `mxl::` of the downloader, and the official Median XL's own
folder names (`%LOCALAPPDATA%\MedianXL`, `mxl-launcher`) that the downloader refuses to write into. The private-terms file and the
shared lock folder come from the machine-local config (docs/setup.md; key `shared_lock_dir` for the locks).

## Game slots (owner rules, 2026-10-28)

- (Superseded 2026-10-28, lane slot1: the owner approved slot 1 for this project's tests; `require_slot` now takes 1, 2 and 3 and
  slot 1 honours the old single `game.lock` again. docs/testing.md "Parallel slots".)
- Only slots 2 (`D:\D2R-93847`) and 3 (`D:\D2R-93847-s3`). `game_slots.require_slot()` ends every tool with an error for slot 1 or
  any other number; there is no default slot (`--slot N` or `MXL_SLOT=N` each time). `MXL_D2R_GAME` is accepted only when it is the
  folder of the chosen slot. The data tools that read D2R's own tables (CASC) go through `tools/d2r_game.py`, which has the same rule.
- Locks: `game.lock.N` stay in the shared lock folder (`LOCK_ROOT`, machine-local config key `shared_lock_dir`, env `MXL_LOCKS` or
  `MXL_RUNS` overrides) so every user of the slots queues on the same locks; the old single `game.lock` of slot 1 is gone. Run output
  (run folders, logs, screenshots, the release-install state) is `RUNS` = `<repo>/work/runs` (env `MXL_RUNS`), not the lock folder,
  because a lane may write only the lock files there.
- `game_slots.py setup` takes the first `d2rloader.toml` from the folder in `MXL_CONFIG_SRC` (never slot 1), sets `default_mod` to
  `mxl2012` and copies `D2RLoader.exe` to `D2RLoader-sN.exe`. Nothing here touches the other mod folders in the slot
  (`protected_mod_folders`).
  **Superseded (lane slots, 2026-10-28):** `setup` no longer edits the slot's game-wide `d2rloader\config` (it is shared with
  other mods): `MXL_CONFIG_SRC` and `default_mod` are gone, every run names the mod on the loader's command line and restores the
  shared files afterwards (`tools/slot_share.py`, docs/testing.md "Sharing slots").
- Tests: `tools/test_game_slots.py`. No game was started and no lock taken while making this scaffold.

## Tooling in the scaffold (game-generic)

- `tools/`: mpq/casc extraction, `txt_migrate.py` framework, `validate.py`, `formula.py`, `build.py` (a skeleton),
  `install_mod.py`, `release_install.py`, `game_slots.py`, `game_ctl.py`, `game_checks.py` (framework + one `status` check),
  `package_release.py`, `publish_release.py`, `dl_ingest.py`, `dl_sync.py`, `github_release.py`, `sign_launcher.py`, `check_public.py`,
  `dcc.py`, `d2r_model.py` / `d2r_mesh.py` / `d2r_texture.py`, `animdata_merge.py`, `ds1_remap.py`, `objpreset.py`, `save/`, the Ghidra
  scripts, `fake_*` test doubles, `launcher_*`, `sprite3d/`, the HD/graphics pipeline scripts and their tests. Main's versions are
  kept for `tbl2json.py`, `strings_*`, `native.py`, `vanilla113.py` and the inventory / audit tools.
- `plugin/`: `mxl2012_core.cpp` (entry/off-list/console skeleton), `d2r.h` / `d2r.cpp`, `build_guard*`,
  `env_guard_logic.h`, `other_plugins_logic.h`, `testharness*` (+ a `harness_cmds.cpp` with an empty verb table and `help`, `echo`,
  `frames`), `harness_cmds_logic.h`, version resource, CMake with `MXL_RELEASE`, unit tests of these. The PluginSDK path is the cache
  variable `MXL2012_PLUGINSDK_DIR` (default `third_party/PluginSDK`).
- `launcher/`: the downloader, complete (C++ Win32, LZMA SDK decoder). Art is main's (lane dlart).
- `.forgejo/workflows`, `.github` templates, `.gitmodules` (+ gitlinks), `LICENSE`, `NOTICE.md`.
- `docs/`: porting-playbook (reference), testing, release, launcher, hosting, txt-migrate, validation, save-format, dev-console,
  setup, d2r-addresses, d2r-baseline, function-slots (see "Review" below).

## Left out (D2Sigma specific)

`sigma_*` tools, name lists, plugin-header data generators (items, item specials, item types, unique limits, stat names, NPC
actions and services, monster AI, waypoints, cube effects and tables, state icons, orb tips, infographics, stat screen),
strings-namespace experiments, plugin feature parts, harness verbs and game checks beyond the framework, `assets/` and
`assets.lock` (replaced by `assets.lock.example`), and the sigma / subsystem / realm docs. Per docs/plugin-plan.md section 11 the
plugin also leaves out `strings`, `client_messages`, `translation_guard`, `game_end`, `sound_guard` (they were in an earlier cut of
this scaffold and were removed before the commit).

## Review: maybe not 2012-ready (kept because unsure)

Tools (kept; check each against 2012's data before first use):
- `txt_migrate.py` (171 KB; about 90 Sigma-specific mentions: Sigma-table columns, `SIGMA_KEPT_SPELLS`, item and skill special
  cases), `formula.py` (decodes Fog calc bytecode; 2012's cells may already be text), `validate.py` (rule "Median value outside D2R's
  list (engine feature in D2Sigma)"), `func_slots.py` / `func_slots_median.py`, `disasm.py` (written for `D2Sigma.dll`; 2012 has none).
- Art / HD pipeline: `art_fix.py`, `art_provenance.py`, `gfx_placeholders.py`, `hd_monsters.py`, `hd_skill_anims.py`, `hd_recolour.py`,
  `effects_hd.py`, `missile_art.py`, `missile_hd.py`, `item_art.py`, `item_hd.py`, `maps_hd.py`, `skill_icons.py`, `skill_icon_check.py`,
  `skill_tree_art.py`, `ui_layouts.py` (8-tab skill tree, 15x10 inventory), `ui_panels.py`, `palshift.py`, `area_audit.py`,
  `item_skill_audit.py`, `tooltip_audit.py`, `plugin_keys.py` (string keys the plugin uses; the plugin has none yet).
- `install_mod.py`: `OLD_HOTKEY_DEFAULTS` (old plugin hotkeys) and `DEV_METADATA`; `package_release.py` writes `launch_arguments`
  `-txt`: these need the 2012 answer. Extra shared stash tabs default to zero pending the PlugY decision.
- `game_ctl.py smoke`: the scenario creates the test character and walks the UI at fixed coordinates (1600x900 client); the
  class, the skill-tab coordinates and the expected log lines still need 2012's values. `game_checks.py` helpers
  (`clean_start_state`, `hstate`, `switch_character`, ...) call harness verbs (`state`, `cursor`, `stat`, `difficulty`, ...) that
  the new `harness_cmds.cpp` does not have yet; they come with the plugin lane's verbs.
- `ghidra_*`: paths in the PowerShell helpers assume a Ghidra project layout that has to be set up for this repo.
- `check_public.py` / `.allow`: the allow list still names docs/hd-models.md and launcher entries; run it in the final tree.

Plugin: `d2r.h` / `d2r.cpp` hold RVAs for many functions (skill, missile, pet) that no part here uses yet; the plugin lane trims
them to what it uses. `mxl2012_stat_names.h` is an empty placeholder (the harness takes stat ids only).
`HarnessGameFrame` / `HarnessCommand` exist but nothing calls `HarnessGameFrame` until a part registers a server frame.

Launcher: the private-copy state migration, removal command and UI prompt have been removed.
The D2R-XL 2012 Downloader starts at 0.1.0 and only targets `mods\mxl2012`. `DefaultSite` points at `files.werdegames.com/mxl2012/` and `IssuesUrl` at the future GitHub
mirror `github.com/Nugwa628/mxl2012-d2r` (does not exist yet; the `.github` templates link there too).

Docs that needed a pass by the lane owning the area: `porting-playbook.md` (reference), `testing.md`, `release.md`, `launcher.md`,
`hosting.md`, `setup.md`, `txt-migrate.md`, `validation.md`, `d2r-addresses.md`, `function-slots.md`, `d2r-baseline.md`,
`save-format.md`, `dev-console.md`.

## Checks run (2026-10-28, VS 18 / MSVC 14.51, Python 3.12)

- `py -3 -m py_compile` on every file in `tools/`: no errors.
- Python unit tests (`cd tools && py -3 -m unittest ...`, TEMP in the scratch folder): `test_game_slots` 7, `test_game_checks_names` 4,
  `test_asset_pack` 28, `test_install_mod` 4, `test_package_release` 13, `test_publish_release` 39, `test_dl_ingest` 31 (1 skipped),
  `test_dl_sync` 15, `test_sign_launcher` 6: all OK.
- Downloader unit tests (`cmake -S launcher/tests`, MSVC): 202 checks, 0 failures. The full downloader exe
  (`cmake -S launcher`) builds as `D2R-XL-2012-Downloader.exe`.
- Plugin unit tests (`cmake -S plugin/tests`): buildguard, otherplugins, envguard, harness all pass. `mxl2012-core.dll` builds
  (`cmake -S plugin -DMXL2012_PLUGINSDK_DIR=<PluginSDK checkout>`), Release; not loaded in a game.
- Not run: any game (no slot lock was taken).

## Left for the next lanes

- `plugin/` is frozen at the skeleton commit for the plugin lane. What it still has to do from this scaffold: trim `d2r.h` / `d2r.cpp`
  to the RVAs it uses, give `harness_cmds.cpp` its verbs (the checks in `game_checks.py` expect `state`, `cursor`, `stat`,
  `difficulty`, `gold`, ... verbs), and call `HarnessGameFrame` from a server-frame hook.
- Pass over the docs and the kept tools (lists above) as the data port reaches them.
- `tools/check_public.py` on the merged tree reports hits only in files of other lanes (absolute home paths in
  `docs/verify-original.md`, `docs/source-inventory.md`, `docs/graphics-inventory.md`, `docs/plugin-plan.md`,
  `docs/engine-triage.md`, `docs/d2r-additions.md`, `docs/hd-icons.md`, `tools/vanilla113.py`, `tools/idmap.py`, `tools/d2r_adds.py`,
  `tools/verify_original.py`); they need `%USERPROFILE%` or an env variable before the repo goes public.
