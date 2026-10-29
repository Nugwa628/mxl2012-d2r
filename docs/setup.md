# Setup on a new PC

Done on the game PC, 2026-10-20 (Windows 11, from a fresh clone; about an hour, most of it the two extractions and the
build). Every command runs from the repo root.

## External inputs

Release rule (2026-10-23): the port is for players who own **only D2R**. Everything from Median XL and all custom art is
in the **asset pack** (`assets/` after `tools/asset_pack.py fetch`; not in git, pinned by `assets.lock`); only Blizzard's
base game files are taken from the D2R install and are never committed or packed.

| Input | Where | Notes |
|---|---|---|
| Diablo II: Resurrected 3.3, build 93847 | `C:\Program Files (x86)\Diablo II Resurrected` | read through CascLib; game must be installed (not running) |
| Median XL 2012 v005 | not needed | Median's own files are in the asset pack (`assets/median/`). The ModDB zip `Median_XL_2012_v005.zip` (md5 `53ae96c95e76062ef67a73845abe41f6`, [verify-original.md](verify-original.md)) is only needed to re-extract its `patch_d2.mpq` with `tools/mpq_extract.py` |
| Asset pack | `assets-1.zip`, 151,094,751 bytes (224,050,707 bytes in 2,364 files unpacked), pinned in `assets.lock` | `tools/asset_pack.py fetch` (step 4); no Git LFS needed. Provenance: [source-inventory.md](source-inventory.md), section 0 |
| Python 3.12 | `py -3` | `python` is the Store stub |
| CMake | `C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin` | not on PATH; add it for the build shells |
| MSVC | Visual Studio 18 Community, "Desktop development with C++" | |
| D2RLoader 1.3.1-beta | https://d2rloader.net/download.html | see below |

## Steps

1. `git clone --recurse-submodules` the repo (or `git submodule update --init`).
2. `py -3 -m pip install --user -r tools/requirements.txt` (pillow, capstone).
3. Native libraries: `tools\build_native.ps1` (CMake on PATH, else Visual Studio's bundled one) -> `build\StormLib`, `build\CascLib`
   from the submodule sources; it does not download anything and stops with the way to fill an empty submodule. In a new
   `git worktree` (empty submodules) use `py -3 tools/lane_setup.py` instead: [New worktree](#new-worktree-a-parallel-lane).
4. Median's files and the HD art (`assets/`, the asset pack): `py -3 tools/asset_pack.py fetch`. It downloads the pack that
   `assets.lock` pins (version, sha256, size, URLs), checks the sha256, unpacks into `assets/` and checks every file against
   the pack's manifest; run again, it only says "already the pinned pack". `tools/build.py` does the same check first and
   stops (exit 2) with this instruction when `assets/` is missing or differs; it never builds without it.
   - Offline / local copy: `py -3 tools/asset_pack.py fetch --from <pack file | folder holding it | unpacked tree>`, or set
     `MXL_ASSETS` to that path (then `tools/build.py` fetches a missing `assets/` by itself). With `--link` and an unpacked
     tree, `assets/` becomes a junction/symlink to the tree (no copy; CI and the game PC use this).
   - Download cache: `~/.cache/mxl2012-d2r/assets` (`MXL_ASSETS_CACHE` moves it). The URL in `assets.lock` is a release of the
     private forge repo `WerdeGames/mxl2012-assets` (section "CI asset pack"): it needs a Forgejo token with `read:repository`
     in `MXL_ASSETS_TOKEN`, which is only sent to git.werdegames.com (a GitHub token, `MXL_ASSETS_TOKEN` or `GITHUB_TOKEN`,
     only to github.com).
   - The build PC (lane worktrees under `R\mxl2012-wt\`): the pack is built into `R\mxl2012-runs\assetpack\pack\`
     (`assets-1.zip` and its unpacked tree `1\assets\`). `fetch` looks there after the download cache, and `tools/build.py`
     fetches a missing `assets/` from there by itself, as a junction to the unpacked tree (no copy per worktree).
   - A checkout from before the pack with `assets/` already there (Git LFS): `py -3 tools/asset_pack.py adopt` hashes it and,
     if it equals the pinned pack, writes the manifest (no download). `verify` re-checks (`--full` hashes everything;
     the default trusts an unchanged stat snapshot of the last full check; `--strict` also fails on extra files).
   - Making the pack from the original (what `assets-1` is; untrusted input, so `-I` and the output outside the download):
     ```
     py -3 -I tools/verify_original.py <R>\mxl2012-runs\download\Median_XL_2012_v005.zip      (-> mxl2012-runs\src-original)
     py -3 -I tools/mpq_extract.py --src <R>\mxl2012-runs\src-original --out <R>\mxl2012-runs\assetpack\assets\median
     py -3 -I tools/asset_pack.py build --version 1 --src <R>\mxl2012-runs\assetpack\assets --out <R>\mxl2012-runs\assetpack\pack --write-lock
     py -3 -I tools/asset_pack.py fetch --from <R>\mxl2012-runs\assetpack\pack --dest <R>\mxl2012-runs\assetpack\pack\1\assets
     ```
     `mpq_extract.py` refuses any `patch_d2.mpq` but v005's (sha256 `5a9da6ea...`). Same tree, same bytes (sorted entries,
     fixed timestamps): `assets-1.zip` always comes out as sha256 `7ad1b448d0ed00305a4aa139c20fdf75cbcc05b362c9cc8c9ae21be9e14c2246`.
   - Changing assets: edit `assets/`, then `MXL_SKIP_ASSET_CHECK=1 tools/build.py` builds with a warning. A new pack:
     `py -3 tools/asset_pack.py build --version <N> --write-lock` (writes `build/asset-pack/assets-<N>.zip` + manifest and
     `assets.lock`; `build` first scans the text files with `tools/check_public.py`'s rules and refuses on a hit, `asset_pack.py scan`
     runs only that), then the owner uploads it as in "CI asset pack" (new tag `assets-<N>`) and the coordinator commits
     `assets.lock`. Public hosting (`tools/publish_release.py --assets`, `https://dl.werdegames.com/mxl2012/assets/`,
     docs/hosting.md) only after the owner approves publishing Median's files; then add that URL to `assets.lock`'s `urls`.
5. Extract the D2R baseline, all sets the build reads:
   ```
   py -3 tools/casc_extract.py --set excel --set strings --set layouts --set dataguide --set meta --set legacy-ui --set legacy-art --set legacy-maps --set hd-ui
   ```
   -> `extract/d2r/93847/` (35,124 files). The default sets alone are not enough: `gfx_placeholders.py` (art file lists),
   `missile_hd.py`, `item_hd.py`, `skill_icons.py` (palette), `ui_panels.py` read `legacy-*` and `hd-ui`.
6. (no step: the vanilla 1.13c view comes from the D2R extraction of step 5.) `mxl_names.py` and `func_slots.py` need
   the tables of Median's vanilla rows only as a row count, row order, key names and a few function slots; D2R's own tables
   hold the 1.13c rows as their first rows. `tools/vanilla113.py` cuts the 33 tables the build uses to their 1.13c row counts
   and puts back the few cells D2R changed (`py -3 tools/vanilla113.py` lists them). No classic Diablo II files or
   `..\D2R Modding Tools` folder are read. Against the build that read the classic tables `work/mod` is byte-identical
   except 214 comment cells that carry D2R's wording instead of 1.13c's (misc.txt `name`, 63 rows; cubemain.txt
   `description`, 151 rows; both columns are typed "comment" in D2R's data guide) and the lines of validate_report.md that quote them.
7. Nothing to do: the build reads Median's tables from `assets/median/data/global/excel` (`MXL2012_SRC` overrides) and its
   other files from `assets/median` (tools/fxpaths.py; `MXL_EXTRACT` / `MXL2012_EXTRACT` override; `R\mxl2012-runs\extract-mpq`,
   the same tree made from the repack's identical MPQ, is the fallback).
8. `py -3 tools/build.py` -> `work/mod/`. Result: validate.py **0 errors** (both banks), 3,994 plugin items,
   48 (base) / 89 (rotw) warnings. The 2 errors in `validation.md` were fixed by an earlier commit.
9. Plugin (CMake on PATH, else Visual Studio's): `tools\build_plugin.ps1 [-Release] [-Tests] [-Sdk DIR]` -> `build\plugin\Release\mxl2012-core.dll`, **mxl2012-core 0.36.0**.
   The PluginSDK folder is `-Sdk`, else `MXL2012_PLUGINSDK_DIR` (environment, else `.mxl-local.json`), else `third_party\PluginSDK`.
10. D2RLoader 1.3.1-beta (the pinned version):
    - Download `https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip` (47,652,455 bytes) into an empty folder.
    - SHA-256 must be `9286c6b5bff7f1043658411dbea305faa9698b6a455e6441668fc6d02c22aad7` (the value on the download page).
    - Unzip into a second folder and check `D2RLoader.exe` and `D2RCore.dll` with `Get-AuthenticodeSignature`:
      signer `CN=D2RLoader`, thumbprint `8001082E968FADAA58BF2F73EFA1810A11D0C28F` (the thumbprint the download page
      publishes), file version 1.3.1-beta. Status shows `UnknownError` ("root certificate not trusted"): the
      certificate is self-signed, so the check is the thumbprint plus an intact signature (not HashMismatch).
    - Copy the zip contents into the game folder (`D2RLoader.exe`, `D2RCore.dll`, `d2rloader.mpq`, `d2rloader\`).
      The zip has no `mods\` folder; `install_mod.py` creates it.
11. `py -3 tools/install_mod.py` -> `<game>\mods\mxl2012` (8,802 files, 791 MB, plugin mxl2012-core.dll included).
    It needs `D2RLoader.exe` in the game folder (step 10) and `work/mod` (step 8).

## CI asset pack

CI (`.forgejo/workflows/ci.yml`, job `assets`, `tools/ci_assets.sh`) has no game files and no cache: it downloads the pack
named in `assets.lock` from a private forge release with a read token kept as a CI secret, checks it (size + sha256 of the
pack, every file against its manifest, `--strict`), scans its text files and runs `tools/tests/test_assets_median.py`
(the tree is the v005 original; its tables and strings read without any Blizzard file). Until the secret exists the job
prints a notice and passes. Setting it up is the owner's (it puts Median's files on the forge, privately); nothing in the
repo changes:

1. Create the private repository `WerdeGames/mxl2012-assets` on git.werdegames.com (empty; it only holds releases) with
   the same members as `WerdeGames/mxl2012-d2r`.
2. In it, create a release with tag **`assets-1`** (pre-release; notes e.g. "Median XL 2012 v005 patch_d2.mpq, extracted.
   Median XL 2012 by Brother Laz. Private: not for redistribution.") and attach **`assets-1.zip`** from
   the build PC: `R\mxl2012-runs\assetpack\pack\assets-1.zip`, 151,094,751 bytes, sha256
   `7ad1b448d0ed00305a4aa139c20fdf75cbcc05b362c9cc8c9ae21be9e14c2246` (`py -3 tools/asset_pack.py check-pack
   R\mxl2012-runs\assetpack\pack` checks it). Its download URL is then the one in `assets.lock`:
   `https://git.werdegames.com/WerdeGames/mxl2012-assets/releases/download/assets-1/assets-1.zip`.
3. Make a read token: an account that can read `mxl2012-assets` (best a bot user that is only a read collaborator there),
   Settings -> Applications -> Generate new token, scope **`read:repository`** only.
4. In `WerdeGames/mxl2012-d2r` -> Settings -> Actions -> Secrets, add **`MXL_ASSETS_TOKEN`** with that token. The next
   CI run's `assets` job fetches and checks the pack instead of skipping. The token goes to that one step only, is sent only
   to git.werdegames.com and is unset right after the download.
5. Optional, once it is green: `MXL_ASSETS_REQUIRED: "1"` in the `assets` job's env makes a lost secret fail CI instead of
   skipping.

A new pack version is a new release `assets-<N>` with `assets-<N>.zip` in the same repository (the token keeps working)
plus the commit that bumps `assets.lock`. Every CI run downloads the pack (about 150 MB, from the forge itself); if that
gets too much, a runner-side cache (e.g. `/var/cache/mxl-assets`) needs a host volume on the runner.

## New worktree (a parallel lane)

A fresh `git worktree add` has empty submodules (`third_party\StormLib`, `CascLib`, `PluginSDK`), no `build\`, and none of the
paths the tools need. Two commands make it ready; nothing is copied by hand:

```
git -C <main checkout> worktree add <runs>/../mxl2012-wt/<lane> -b lane/<lane> main
cd <runs>/../mxl2012-wt/<lane>
py -3 tools/lane_setup.py          :: once (about 1 minute the first time on this PC, seconds afterwards)
py -3 tools/build.py               :: full data + art build -> work/mod, validate 0 errors
tools\build_plugin.ps1 -Tests      :: plugin DLL + the native unit tests
```

(`<runs>` is `mxl2012-runs`, two levels above the lane worktrees; `MXL2012_RUNS` moves it.) `lane_setup.py [WORKTREE]` also takes
another worktree's path, `--check` only reports (exit 1 when something is missing), and running it again only re-checks. It
prepares:

| What | Where it ends up | Source |
|---|---|---|
| StormLib / CascLib DLLs | `<runs>/shared/native/build/<lib>/Release` (one build for all worktrees; `tools/native.py` takes a worktree''s own `build/` first, then this) | built by `tools/build_native.ps1 -Source ... -Out ...` from the commit the repo pins, with Visual Studio''s CMake. Sources: the worktree''s submodules when they are filled, else a clone of the pinned commit in `<runs>/shared/native/src`, made from a LOCAL checkout (`MXL_NATIVE_REF`, the worktree''s own, or the `third_party` of the machine-local config''s `reference_checkout`); nothing is downloaded. `--local-native` builds into the worktree''s `build/` instead. A build whose `.source-sha` is the pinned commit is not repeated |
| PluginSDK | `<runs>/shared/native/src/PluginSDK` at the pinned commit | same clone; its folder is `MXL2012_PLUGINSDK_DIR` for `build_plugin.ps1` |
| D2R extraction | `MXL_D2R_EXTRACT` | this checkout''s `extract/d2r/93847`, else the machine-local config''s `extract_dir` (read-only); must hold both banks of `skills.txt` |
| D2R file cache | `<runs>/shared/d2r-cache` (`MXL_D2R_CACHE`), one for all worktrees, never copied | the files the extraction lacks (`fxpaths.CACHED_FILES`: the seven HD player state machines used by `hd_skill_anims.py`, plus animdata / missiles.json when an extraction lacks them). First fill, once per PC: `--seed-cache DIR` (the `work/d2r-cache` of any checkout; same layout) or `--cache-from-slot 2` (reads the CASC of game slot 2 to 5 under its lock; no game is started; slot 1 is refused). A `MANIFEST.json` of sha256 values makes a changed file show up in `--check` |
| `.mxl-local.json` | the worktree root (git-ignored) | the values above as environment-variable defaults: `MXL_D2R_EXTRACT`, `MXL_D2R_CACHE`, `MXL_NATIVE_DIR`, `MXL2012_PLUGINSDK_DIR` (`tools/localconfig.py`; a variable set in the shell wins) |

`tools/build.py` and the tools that read these variables import `tools/localconfig.py`, which applies the file, so no
`$env:` line is needed; `build_plugin.ps1` reads the same file. Missing inputs are errors, not empty output: `txt_migrate.py`,
`validate.py` and `build.py` stop with exit 1 and the list of places they looked when the D2R extraction has no
`data/global/excel/skills.txt` + `base/skills.txt` (bug #211); `fxpaths.d2r_file` says to run `lane_setup.py` when a cache file is
missing and no slot is named; `native.py` names the folders it searched. Shared work (clone, build, cache fill) runs under
`<runs>/shared/.lock`, so two new lanes do not build at once; the lock of a dead process is taken over after an hour.

Temp files stay in the project, too (CLAUDE.md rule 1): every test module and every tool that makes temp files imports `tools/projtemp.py`, which points `tempfile` and TMPDIR / TEMP / TMP (so child processes: CMake, MSVC, 7-Zip, git) at `<repo>/work/tmp` (git-ignored; on CI the workspace), or at `MXL_TMP`, or at a TEMP / TMP you already set inside the checkout or `<runs>`. `build_native.ps1` and `build_plugin.ps1` do the same for their processes. Nobody sets TMP / TEMP by hand; `tools/tests/test_projtemp.py` and `tools/test_temp_inside_repo.py` assert that `tempfile.gettempdir()` is inside the repo in both discovers, and the first fails when a new `test_*.py` forgets the import (add `import projtemp` after its `sys.path` set-up).

What it does not do: install Python packages (`py -3 -m pip install --user -r tools/requirements.txt`, checked by `--check`),
fetch the Median tables (`<runs>/extract-mpq` or `MXL2012_SRC`, checked), or fetch the asset pack (`tools/asset_pack.py fetch`,
once `assets.lock` exists). Verified 2026-10-28 on a new worktree: `lane_setup.py` (native build 1 min), `build.py` (validate 0
errors, text audit 0), `build_plugin.ps1 -Tests` (all native tests passed), with no variable set in the shell.
## By hand

- D2RLoader settings for unattended runs (`<game>\d2rloader\config\d2rloader.toml`):
  `default_mod = "mxl2012"`, `launch_arguments = "-w -txt"`, `skip_title_screen = true`,
  `check_for_updates = false`, `write_crash_dumps = true`, `developer.enable_console = true`,
  and developer logs enabled for `excel_files`, `bin_validation`, `extension_details`, `archive_mounts`.
  The original is kept as `d2rloader.toml.orig`; `check_for_updates = false` keeps the pinned 1.3.1.
- `-txt` compiles all 380 tables at start (about 15 s total), this launch only; no manual `d2rl compile D2R-XL 2012` is needed.
- mxl2012-core 0.37.0 loads (ABI 4). Three startup asserts are expected; see [plugin-spec.md](plugin-plan.md).
- Test characters: none were on this PC (below). Create new ones; read `save-format.md` before editing saves.
## Ghidra

- Ghidra 12.1.4 (Java 21). The scripts expect it at `..\tools\ghidra_12.1.4_PUBLIC`; on the game PC that is a junction to
  the install in Downloads.
- `..\ghidra\sigma` (project `D2Sigma`, `D2Sigma.dll` from the Median install, base 0x10000000) and `..\ghidra\d2game`
  (project `D2Game`, Median's `D2Game.dll` imported as `D2Game_113.dll`, base 0x6fc20000): `analyzeHeadless` import
  with auto-analysis, about 1.5 minutes each.
- `..\ghidra\project` (the D2R image): needs a memory dump of the running game. Start D2RLoader, then
  `py -3 tools/dump_image.py` -> `..\ghidra\D2RLoader_<time>_dump.exe`, then `tools/ghidra_analyze.ps1 -MaxMem 16G` (hours; worked on the 64 GB machine).
- Parallel lanes each query their own copy of a project (`..\ghidra-lanes\<lane>\sigma`): two headless runs can't
  open one project at once.

## Slot copies for parallel test games

Up to five games can run side by side (docs/testing.md, "Parallel slots"). Slot 1 is the Battle.net install; slots 2
to 5 are full copies of the same build 93847 folder (29 GB each) on any drive (D: here; the harness reports C:'s
volume serial so the Battle.net session cookie still decrypts):

```
robocopy "C:\Program Files (x86)\Diablo II Resurrected" D:\D2R-93847     /E /MT:8 /XD logs     :: slot 2 (an older copy was already there)
robocopy "C:\Program Files (x86)\Diablo II Resurrected" D:\D2R-93847-s3  /E /MT:8 /XD logs     :: slot 3 (about 5 minutes)
:: slots 4 and 5 (2026-10-28): copies of slot 2's folder, D:\D2R-93847-s4 / D:\D2R-93847-s5, then `game_slots.py setup 4 5`
py -3 tools/game_slots.py setup          :: modinfo savepath mxl2012-s2 / -s3, toml from slot 1, save folders, D2RLoader-sN.exe
py -3 tools/install_mod.py --slot all    :: mod data + plugin into every slot (built once, copied)
py -3 tools/game_slots.py status
```

Slot 1 is the owner's own install (`C:\Program Files (x86)\Diablo II Resurrected`, approved 2026-10-28): no robocopy, it is
set up only by name, under its lock: `game_slots.py setup 1` (savepath `mxl2012-s1`, no loader copy) and
`install_mod.py --slot 1` (docs/testing.md "Parallel slots" for its extra rules and Program Files writes).
Other folders: env `MXL_SLOT1_DIR` ... `MXL_SLOT5_DIR`. `MXL_D2R_GAME` / `install_mod.py --game`
pointing at a slot folder keeps that slot's save folder. Never run two slots on one folder. A slot needs
`D2R.exe`, `D2RLoader.exe`, `D2RCore.dll`, `d2rloader.mpq`, `.build.info` and the `Data` folder, which the robocopy gives it.

Rename to D2R-XL 2012 (2026-10-26): the mod folder is `mods\mxl2012` and the save folders `mods\mxl2012`, `mxl2012-s2`,
`mxl2012-s3` (were `MedianXL`, `MedianXL-s2`, `-s3`). A slot set up before needs, under its lock,
`py -3 tools/install_mod.py --slot N` (writes `mods\mxl2012`) and `py -3 tools/game_slots.py setup N` (modinfo savepath,
`default_mod = "mxl2012"` in the slot's `d2rloader\config\d2rloader.toml`; since lane slots (2026-10-28) the toml is
no longer edited: runs pass `-mod mxl2012`). The old `mods\MedianXL` folder can then be deleted; the old save folders are moved by hand (characters
are not converted by any tool).

## Old test characters

No `mxl-manual-backups` folder and no `mxl2012` save folder exist on the game PC: not in `Saved Games\Diablo II Resurrected`
(only `Backups`, `mods\RMD-MP`, unrelated), OneDrive (empty), Documents or Desktop. They must come from the PC that
made them, into `Saved Games\Diablo II Resurrected\mods\mxl2012` (the mod's `savepath`).

## CI

CI runs on a private CI server (`<ci-server>`; its address is deliberately not published) with a Forgejo runner scoped to `WerdeGames/mxl2012-d2r`, label `mxl-cross`, a Docker image with clang-cl, lld, xwin and g++, capacity 1, and a cap of 6 CPUs / 8 GB. The runner is not exposed to GitHub: pull requests on GitHub are applied to the forge by maintainers and then run there.

`.forgejo/workflows/ci.yml` runs on every PR and push to `main`. `plugin` cross-builds `mxl2012-core.dll` with clang-cl + lld-link and the xwin MSVC CRT/SDK (`/opt/xwin/xwin`) via `plugin/cmake/xwin-toolchain.cmake` (pass it as an absolute path). `native-tests` builds `plugin/tests` and `launcher/tests` (standalone CMake projects) with g++ and runs the unit test binaries listed in the workflow. `tools` runs the Python unit tests (`unittest discover` over `tools` and `tools/tests`) and `tools/check_public.py` (no private paths, host names, addresses or credentials in tracked text).

The CI image (shared with another project and not changed for this one) has `python3` but neither numpy nor Pillow. The `tools` job therefore makes a venv in the workspace (`python3 -m venv --without-pip .venv-ci`, git-ignored: the image has no ensurepip / `python3-venv`), installs the pinned `tools/requirements-ci.txt` (numpy, Pillow) into it with the image's system pip (`python3 -m pip --python .venv-ci/bin/python install ...`) and runs the tests with `.venv-ci/bin/python -I`. Raise a pin there when the tests need a newer package. Tests that start the game (`test_game_ctl_nofocus`, `subprocess.STARTUPINFO`) are skipped off Windows.

The unit tests have to pass on Linux, where `ctypes.windll` does not exist and the owner's private-terms file (`MXL_PRIVATE_TERMS`) is absent:

- `tools/game_slots.py`, `game_ctl.py` and `game_checks.py` get their Windows DLLs from `tools/winapi.py`, which loads them on first use. They import everywhere, the slot, lock and name logic is testable, `game_slots.processes()` finds no game off Windows, and an actual DLL call raises `OSError: ... only available on Windows`. `tools/test_winapi.py` imports them with `windll` removed from ctypes to keep that true. A new Windows-only call goes through `winapi.Dll`, never `ctypes.windll` at import time.
- A test that plants private details must plant what the *generic* rules of `check_public.py` flag (a user-home path, an internal host, an IP address), not a machine name from the private-terms file: that file does not exist on the runner, so such a test passes at home and fails in CI (this was the `test_asset_pack` failure).
- Tests that need extracted game tables (`test_idmap` integration tests: `MXL2012_MOD_EXCEL`, or `mxl2012-runs/extract-mpq` next to the worktrees) skip when they are not there.
- To try the Linux conditions on Windows: run the discover with `ctypes.windll`/`WinDLL`/`WINFUNCTYPE` deleted and `MXL_PRIVATE_TERMS` pointing at a missing file.

No game files go to the server. The boot check and the in-game smoke run (`py -3 tools/game_ctl.py smoke`) need the game and run on the game PC.

Job logs are not exposed by API v1; reproduce a failing job on the CI server with `docker run` of the CI image.
