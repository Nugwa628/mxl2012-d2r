# D2R-XL 2012 Downloader

`D2R-XL-2012-Downloader.exe` installs and updates **D2R-XL 2012**, the Median XL 2012 port,
into the player's D2R folder at `<D2R>\mods\mxl2012`. The plugin is `mxl2012-core.dll`.
The downloader version starts at **0.1.0**, independently of the plugin and release versions.

It never starts the game or installs D2RLoader. Install **D2RLoader 1.3.1** from
<https://d2rloader.net/>, run the downloader and press **Install**. To play, start
`D2RLoader.exe`; use its gear menu to select D2R-XL 2012 as Default Mod, Apply, and restart
D2RLoader. The downloader also offers a confirmed **Default mod** action (below).
The release `.7z` is the manual-install fallback.

## Finding D2R and checking prerequisites

- Battle.net discovery reads `InstallLocation` from the Diablo II Resurrected Uninstall
  key under HKLM/HKCU, both registry views. Steam discovery reads `SteamPath`,
  `libraryfolders.vdf`, and app manifests named Diablo II: Resurrected. Default install
  folders are checked too. Discovery is read-only.
- **D2R folder** or `--game-dir` chooses a folder containing `D2R.exe` and `Data`. The
  choice is saved. Official Median XL and classic Diablo II folders are refused.
- D2R **3.3** is required. `.build.info`'s active row is preferred, with the executable's
  FileVersion as fallback (`detect.cpp`). The check compares major/minor versions, not
  individual build numbers; 3.3.93847 is the port's baseline. A mismatch shows a warning
  and the GUI asks before installing anyway. The plugin has its own build guard.
- `<D2R>\D2RLoader.exe`'s version resource must match **1.3.1** (or the release manifest's
  required version). Numeric equivalents `1.3.1`, `1.3.1.0`, and `1.3.1-beta` match.
  A missing or different version shows a warning and **Get D2RLoader** opens its official
  download page (https://d2rloader.net/download.html). Installation remains available; the downloader never downloads the loader.

## Where it writes

- `<D2R>\mods\mxl2012` only for mod installation, repair and uninstall. The target is
  fixed even if saved state names another mod; a manifest naming another `modFolder`
  is refused. In particular, another mod's folder is never an install target.
- `mxl2012-install.json` in that folder records `made_by = "D2R-XL 2012 Downloader"`,
  installation id and release version. An unmarked manual/developer install requires
  confirmation before replacement (`--replace` for CLI). Another downloader id can be
  adopted. Uninstall requires the current installation's marker.
- `mxl2012-download` inside the mod folder holds object `.part` files and `7z` staging.
  Finished files are renamed into place on the same volume. Staging is removed on success.
- `%LOCALAPPDATA%\mxl2012`: `launcher.json`, `launcher.log`, and `download` for release
  archives. `--data-dir` overrides this for tests. The official Median XL's data and save
  folders are protected and separate.
- Next to the downloader: `<exe>.download` and `<exe>.old` during self-update.

The executable uses `asInvoker`; a write failure explains how to grant access or run as
administrator. Install, repair, uninstall and environment fixes refuse while D2R or
D2RLoader is running from the selected game folder. Characters and game settings are
never written. The only optional writes outside the target mod folder are the explicit
Default mod and Move plugin actions below.

There is no private game copy, Play action, loader download, legacy state migration,
old-copy deletion prompt, `remove-old-copy` command, or `--source` alias. This new product
does not migrate or delete other launchers' old copies.

## Install, Update, Repair and Uninstall

The default site is **https://files.werdegames.com/mxl2012/** (backup origin
`https://dl.werdegames.com/mxl2012/`, selectable with `--site`). Each refresh reads
`channels/<channel>.json` then its schema-2 manifest and verifies `manifestSha256`.
Unpublished channels, HTTP failures and connection errors produce separate messages.
A release without game data (`complete: false`, a `--no-data` package) installs only from a
channel other than **stable** (`InstallableFromChannel`); the window then marks it as a test
package. The stable channel never carries one (`publish_release.py`, `dl_ingest.py`).

**Install / Update** uses `PlanInstall` to fetch missing or changed release files.
Size/mtime records can skip hashes of unchanged files; **Repair** hashes every file.
Files absent from the release are removed except manifest `preserve` entries,
D2RLoader logs/crashes, the install marker and staging. Empty directories are created.
The marker and state record the completed release.

The downloader chooses the release **7z** when the objects needed are larger than the
archive, otherwise individual **objects**. `--via auto|7z|objects` overrides this choice.
Archive failures fall back to objects in auto mode; forced 7z mode reports the failure.

- Archives resume with Range requests, verify manifest size/SHA-256, and unpack with the
  bundled LZMA SDK decoder. Single LZMA2/LZMA/Copy blocks stream through a dictionary;
  filtered blocks decode in memory (64 MB limit). Only planned files under `mxl2012/`
  are staged, checked by CRC and SHA-256, and moved into place. Archive entries are data;
  nothing from the downloaded mod is executed.
- Objects use `objects/<sha[0:2]>/<sha>`, up to eight workers, resumed `.part` downloads,
  size/SHA-256 checks, and final renames. Identical hashes share one download.
- Downloads retry five times with 2/4/8/16-second pauses; 403/404/410 stop immediately.
  Stop, close or interruption preserves completed work and resumable parts.

**Uninstall** removes only the marked `mods\mxl2012` and clears download/state records.
Saves remain at `Saved Games\Diablo II Resurrected\mods\mxl2012` (or the modinfo savepath).
D2R, D2RLoader, other mods, and the game-wide `default_mod` setting remain.

## What D2RLoader really starts

On refresh the downloader checks `<D2R>\d2rloader\config\d2rloader.toml`, section
`[d2rloader]`, key `default_mod`. Missing/empty values, no config yet, and any name other
than `mxl2012` show a warning. Comparison is case-insensitive; **any other name is another mod**.
The per-mod config cannot select the active mod. **Default mod** asks before setting
only `default_mod = "mxl2012"`, preserving other keys, comments, BOM and line endings.

It also checks game-wide `d2rloader\plugins` and other mods' plugin directories for
`mxl2012-core*.dll` or renamed copies identified by version resources (ProductName
`mxl2012` / `D2R-XL 2012`, or a matching core FileDescription). Other mods' plugins are
not ours. Warnings distinguish copies that load with every mod from those in another mod.
Junctions are not followed while enumerating files.

**Move plugin** asks before moving our stray copies to
`<data>\removed\<date>\<relative path>`; collisions receive numeric suffixes and nothing
is deleted. Copies inside **protected mod folders (`protected_mod_folders`) stay in place** and are reported for manual
handling, even if their metadata identifies our plugin. That folder is never changed.
The warnings remain visible until the player resolves the copies.

## Self-update and version resource

`MXL_LAUNCHER_VERSION` in `launcher/src/win/app.h` is **0.1.0**. CMake uses that one value
for the code and executable FileVersion/ProductVersion resource; the application
manifest is also 0.1.0.0. `-DMXL_LAUNCHER_VERSION=x.y.z` overrides code and version resources
for self-update tests. Release publishing reads the executable version resource and
rejects a contradictory `--launcher-version`.

A manifest's `launcher` entry offers an update only when its version is newer and its
SHA-256 differs from the running executable. This is available even when the release
requires a newer downloader/schema. The replacement downloads beside the executable,
checks size and SHA-256, logs optional signature information, renames the current file
to `.old`, and moves the new file into its place. A failed swap attempts rollback.
The GUI offers a restart; the CLI reports the update for the next run. Old executable
cleanup happens after the previous process exits. Signing is a separate release step
via `tools/sign_launcher.py`; no signing certificate is required by self-update.

The download host's `tools/dl_ingest.py` is told the exe's name by its unit (`--launcher-name D2R-XL-2012-Downloader.exe`,
docs/hosting.md) and refuses any other file name. The host needs this multi-product `dl_ingest.py` (docs/hosting.md,
"Owner steps") before the first release with a downloader is published.

## Command line and build

```text
D2R-XL-2012-Downloader.exe --cli status|detect|install|update|repair|uninstall|self-update|fix-default-mod|remove-stray-plugins
  --game-dir DIR --data-dir DIR --site URL|DIR --channel stable|test
  --replace --via auto|7z|objects
```

`--snapshot FILE` renders the window to PNG. The GUI-subsystem executable should be
waited for with `Start-Process -NoNewWindow -Wait` when used from PowerShell.

```text
cmake -S launcher -B build/launcher -A x64
cmake --build build/launcher --config Release
build/launcher/tests/Release/launcher_tests.exe
```

The existing Visual Studio CMake location is documented in `docs/setup.md`. This builds
one static-runtime C++20 Win32/GDI+/WinHTTP executable plus the portable core tests.
The unsigned executable and its `.sha256` are under `build/launcher/Release`.
Tests can also be configured separately with `cmake -S launcher/tests -B build/launcher-tests -A x64`.
CI cross-builds with the existing xwin toolchain and runs portable tests on Linux.

Tests cover detection, manifest/installation plans, hashes, marker/path protection,
7z decoding and corruption, coexistence, TOML preservation, plugin identification,
other-mod warnings, and protection of other mods from automatic cleanup. No downloader or
in-game integration run is required for this cleanup; unit tests do not access a real
D2R installation. Previous copied documentation's release/game test results are not
validation of this new port.

Validation for lane `dlclean` (2026-10-28): CMake / Visual Studio 18 2026, MSVC
19.51.36260.0, x64 Release build passed. `launcher_tests.exe`: **208 checks, 0 failures**.
The unsigned downloader is **2,859,008 bytes**; FileVersion and ProductVersion both read
**0.1.0**. Only the unit-test executable was run; the downloader executable was not run
against any D2R folder. No downloaded mod executable, DLL or script was executed.

## Testing

Never against a real D2R folder: give every run its own `--data-dir` and a fake `--game-dir`
(a folder with `D2R.exe` (any bytes), an empty `Data` folder and a `.build.info` whose active
row is `3.3.93847`; a `D2RLoader.exe` with FileVersion `1.3.1-beta` for the loader check).
Relative `--game-dir` / `--data-dir` are made absolute. `tools/launcher_isolation.py snapshot`
before and `compare` after (with `--exclude mods/mxl2012`) shows that nothing else changed.

- **Download host:** `--channel test` against the default site installs the published test
  package; a second `update` reports "installed and up to date"; a `<name>.7z.part` in
  `<data>\download` (or an object `.part` in `mods\mxl2012\mxl2012-download`) resumes with a
  Range request.
- **Local update test:** build a release (`tools/package_release.py`, or `package_release.stage`
  + `write_7z` + `manifest` on a small data folder), `tools/launcher_testsite.py derive` the next
  version with `--put` (added), `--append` (changed, also on a `preserve` file) and `--remove`,
  `publish_release.publish` both into `dir:<x>/mxl2012` with `<x>/incoming-mxl2012` next to it,
  run `dl_ingest.Ingest(<x>, ...)`, `promote` the first to `test` and serve `<x>/mxl2012` with
  `tools/serve_dir.py`. Install, edit the preserved `d2rloader/config/d2rloader.toml`, add a
  `d2rloader/logs` file, `promote` the second, `update`: added/changed files arrive as objects,
  removed ones go, the player's toml and the log stay, unchanged files are not rewritten.
- **Window:** `--snapshot FILE` renders the start-up state. Install / Stop can be driven with
  `WM_COMMAND` messages to the button ids (`window.cpp`), no input injection; after Stop the
  panel says "Stopped. Install again to continue ..." without a message box.

Validation for lane `launcher` (2026-10-29), MSVC x64 Release, 2,205,184 bytes, `launcher_tests.exe`
**210 checks, 0 failures**. Live host (`files.werdegames.com`, channel `test` = 0.0.1, a no-data
package, read-only GETs): status, install (7z), second run up to date, resume from a partial 7z,
uninstall, window install by message, fake folder unchanged. Local site (0.0.2-lt1 -> 0.0.3-lt2,
42 MB 7z served at 4 MB/s): 7z download killed after 4 s and resumed, object download killed and
resumed, Stop in the window and Install again resumed, update with changed/added/removed files and
a preserved toml, second update up to date, Repair; every installed file matched the manifest.
