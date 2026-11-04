# D2R-XL 2012 Downloader

`D2R-XL-2012-Downloader.exe` installs and updates **D2R-XL 2012**, the Median XL 2012 port,
into the player's D2R folder at `<D2R>\mods\mxl2012`. The plugin is `mxl2012-core.dll`.
The downloader version starts at **0.1.0**, independently of the plugin and release versions.

It needs **D2RLoader 1.3.1** in the D2R folder: when it is missing,
**Install D2RLoader** downloads it from <https://d2rloader.net/> after asking (below); it can also be
installed by hand. Then press **Install**, then **Play** (below), which starts `D2RLoader.exe -mod mxl2012`.
Without the downloader, start `D2RLoader.exe` by hand; use its gear menu to select D2R-XL 2012 as Default Mod,
Apply, and restart D2RLoader. The downloader also offers a confirmed **Default mod** action (below).
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
  A missing or different version shows a warning and **Install D2RLoader** in Uninstall's place
  (below). **Get D2RLoader**, which opens the official download page
  (https://d2rloader.net/download.html), takes that place when the release manifest has no usable
  `d2rloader` package or an install of it failed. Installing D2R-XL 2012 stays available either way.

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
- Install D2RLoader only, after the player confirms: D2RLoader's files in the D2R folder (below). The ZIP
  downloads to `<data>\download`, is unpacked into `<data>\loader-staging`, and both are removed afterwards.

The executable uses `asInvoker`; a write failure explains how to grant access or run as
administrator. Install, repair, uninstall and environment fixes refuse while D2R or
D2RLoader is running from the selected game folder. Characters and game settings are
never written. The only optional writes outside the target mod folder are the explicit
Install D2RLoader, Default mod and Move plugin actions below.

There is no private game copy, bundled D2RLoader, legacy state migration,
old-copy deletion prompt, `remove-old-copy` command, or `--source` alias. This new product
does not migrate or delete other launchers' old copies.

## Play

**Play** (owner decision 2026-11-04) sits next to Install / Update. It starts `<D2R>\D2RLoader.exe -mod mxl2012` with the D2R
folder as working folder, with the downloader's own rights (it runs `asInvoker`, so never elevated), and does not wait for
the game. **How the mod is chosen:** D2RLoader passes its own command line on to D2R after the game-wide `launch_arguments`,
and a `-mod` there wins over the game-wide `default_mod` (checked on slot 2, where `default_mod` names another mod:
`tools/slot_share.py`, and with Play itself: docs/testing.md "Lane playbtn"). So Play starts D2R-XL 2012 whatever `default_mod` says and never
writes D2RLoader's config; the Default mod warning and action stay for players who start D2RLoader by hand. (D2RLoader 1.3.1
refuses `-mod` only inside `launch_arguments` of its config, not on its command line.)

Play is on only when all of these hold (`PlayBlocked`, paths.h; the line under the panel says `Play: <reason>.` otherwise):
the D2R folder is known, its version is not a known other one (a D2R version that cannot be read does not block), D2RLoader
is there at the required version, `mods\mxl2012` is our install (marker), no update is waiting on the channel, the last install,
update or repair finished (the state's `mod_pending`, set when the folder starts to change and cleared when it ends well),
and no D2R / D2RLoader runs from the D2R folder. A 3-second timer notices when the game ends and turns Play on again. When the
channel cannot be read (offline), an installed release still plays.

A missing `D2RLoader.exe`, a start Windows refuses (with "it asks for administrator rights" for `ERROR_ELEVATION_REQUIRED`)
or a loader that ends within 3 s is shown in red in that line (no message box) and logged with the command line and PID.
**Close the downloader when the game starts** (a check box under the how-to-play line; `close_after_play` in `launcher.json`,
default on) closes the window after a good start. `--cli play` does the same as the button (after reading the channel).

## Install D2RLoader

D2RLoader is never shipped in the release or downloader. The release manifest's `d2rloader` block
(`tools/package_release.py` `D2RLOADER`: version, url, size, sha256, signerThumbprint) names the official ZIP,
`https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip`, sha256 `9286c6b5...2aad7` as published on its
download page. D2RLoader's site sets no licence or terms against downloading it; the downloader fetches
it only from that site, only when the player asks.

- Offered (in Uninstall's place) when D2RLoader is missing or another version, and the manifest's block
  is usable (`LoaderPackageUsable`, loaderpkg.h): a version, an `https://` url on d2rloader.net (or a
  subdomain) naming a `.zip`, a size up to 512 MB, a 64-digit sha256. `package_release.loader_problems`
  checks the same before a manifest is written.
- A question names the version, the source URL and the target D2R folder. `--cli install-loader` does the same
  without asking.
- Refused while D2R or D2RLoader runs from that folder (checked before the download and again before
  anything is moved). No elevation: a write failure explains how to grant access.
- The download resumes with Range requests and retries like the 7z (403/404/410 stop). More bytes than
  `size`, or another sha256, deletes the file; nothing is installed. Then the window offers the download page.
- The ZIP is read by the downloader's own ZIP reader (`zip.cpp`: Stored and Deflate, CRC-32 checked; no ZIP64,
  no encryption). `PlanLoaderInstall` accepts only top-level `D2RLoader*` / `D2RCore*` files, anything under
  `d2rloader/`, and empty folders (`mods/`). Any other entry (D2R's own files, `Data/`, a file in `mods/`, an
  unsafe path, a duplicate) refuses the whole package.
- Files are unpacked into staging first. Files under `d2rloader/config/` that already exist are kept: they
  hold the player's D2RLoader settings and the game-wide `default_mod`. Existing loader files move to
  `<staging>\old` before the new ones go in. A failed move puts them back.
- The Authenticode signer of the new `D2RLoader.exe` is logged and compared with `signerThumbprint`.
  It is information only: the sha256 is the check.

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
Files absent from the release are removed except manifest `preserve` entries (and their
`.retail-backup` copies, below), D2RLoader logs/crashes, the install marker and staging. Empty
directories are created. The marker and state record the completed release.

**Save format of a kept config** (bug #512, owner decision 2026-10-30). The mod's
`d2rloader/config/d2rloader.toml` is a `preserve` file, so a player's copy (an old install, or
another mod's settings) stays. Without `[d2rcore.save_format] mode = "extended"`, D2RLoader writes
retail saves, and every save fails while a Median item with stat ids 511+ is carried. After each
install, update and repair, `EnsureExtendedSaves` reads that file. If it is missing or already
extended, nothing happens; fresh installs ship the key (`tools/install_mod.py`, checked by
`tools/verify_package.py`). Otherwise the file is copied once to `d2rloader.toml.retail-backup`
(never over an older one; the plugin part `savemode` of lane savecap uses the same name). Then only
that key is set (`SetExtendedSaveFormat`, paths.h): a `mode` line, or the top-level dotted
`d2rcore.save_format.mode`, gets the new value in place with its indent and comment; else the
line goes right under an existing header; else the table is appended. Every other line, a BOM,
and the CRLF/LF endings are unchanged. The panel/log line says what the old value was and where
the backup is. If the backup or the write fails, the install stops with an error that names the key.

**Ctrl stat ranges off in a kept config** (bug #528, owner decision 2026-11-03). D2RLoader's
Ctrl "Possible base rolls" block repeats lines for Median's automagic rows (upstream:
D2RLoader/PluginSDK issue 6), so the release ships `[d2rcore.items] item_stat_ranges = false`.
After `EnsureExtendedSaves`, `EnsureModConfigKeys` reads the same kept file and applies the other
`ModConfigKeys` (paths.h). If `item_stat_ranges` is not `false` (missing, `true`, a commented
template), only that key is set (`SetItemStatRangesOff`): an existing line in place with its indent
and comment, a commented template line, else under the header, else the table is appended; BOM and
line endings stay. No backup (one key), and a failed write is only reported: the game runs either way.
A player who sets it back to `true` gets `false` again at the next update or repair while this owner
decision stands.

**Legacy graphics (G) in a RotW game** (bug #498). D2RLoader blocks G in a Reign of the Warlock game
unless `[d2rcore.player] always_enable_rotw_legacy_graphics_keybind = true`. Its game-wide
`d2rloader\config\d2rloader.toml` ships `false`, and the mod's own file overrides it, so the release ships
`true` (`tools/install_mod.py` `TOML_KEYS`). A kept file from an older install may hold only D2RLoader's
commented template line (`# always_enable_rotw_legacy_graphics_keybind = true`). Then the game-wide
false applied. The key is forced like `item_stat_ranges` (owner decision 2026-11-04):
`EnsureModConfigKeys` uses `ForceTomlKey`, the rules of `install_mod.ensure_toml_key` with
`force` (each `TOML_KEYS` entry has a forced flag; the save format, this key and `item_stat_ranges`
are forced). An uncommented value in `[d2rcore.player]`, or the dotted key before the first table,
gets `true` in place with its indent and comment, so a `false` set by hand or left by D2RLoader's
1.3.1 template becomes `true`. Else a commented line (any `#` and spaces) becomes `... = true`. Else
the key goes under the header, or the table is appended. Fresh installs, updates and repairs all
end with `true`; the game-wide file is never written.

**Shared stash pages as in RotW** (bug #535, owner 2026-11-04). D2R 3.3 gives a classic / expansion game 3 shared
stash pages and a Reign of the Warlock game 5. The release ships `[d2rcore.stash] add_shared_tabs = 2` (D2RLoader adds
that many pages after D2R's own). The key is a minimum (`ModConfigKey::atLeast`; `install_mod.ensure_toml_min`, the
`TOML_KEYS` mode `"min"`): a missing key or D2RLoader's commented template line becomes `2`, a smaller value or one that is
not an integer becomes `2` in place (indent and comment kept), a value of 2 or more stays, since lowering it would hide the
items on the pages past the new count.

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
D2R-XL-2012-Downloader.exe --cli status|detect|install|update|repair|uninstall|self-update|fix-default-mod|remove-stray-plugins|install-loader|play
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
7z decoding and corruption, the ZIP reader and the D2RLoader package (`TestZip`, `TestLoaderPackage`), coexistence, TOML preservation, the save format key (`TestSaveFormat`), the stat ranges key (`TestStatRangesOff`), the RotW G key (`TestModConfigKeys`), Play's enable rules and command line (`TestPlay`), plugin identification,
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
