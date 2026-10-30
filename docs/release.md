# Player releases

Owner decision 2026-10-27: the supported install path is the **D2R-XL 2012 Downloader** (`D2R-XL-2012-Downloader.exe`,
docs/launcher.md). It puts the mod into `<D2R folder>\mods\mxl2012` of the player's own D2R install and nothing else;
the player installs D2RLoader 1.3.1 from d2rloader.net and starts the game with `D2RLoader.exe` (default mod D2R-XL 2012).
(The 0.1.x launcher's private game copy is gone.) Mod managers (D2RMM and others) and Nexus are not supported. For a
manual / offline install the release has a `.7z`. Owner decision 2026-10-26: **no zip files**, 7z only. The downloader
installs a fresh copy from that 7z and small updates and repairs from single-file objects ("Hosting layout").

## What a release is

`py -3 tools/package_release.py` (on the game PC, after `tools/build.py`) writes into `dist/`:

| File | What |
|---|---|
| `release-manifest.json` | the downloader's feed (format below). `tools/publish_release.py` sends it to the download host ("Hosting layout") |
| `D2R-XL-2012-<version>.7z` | top folder `mxl2012/`, unpacked into `<D2R>\mods\` it is the folder `tools/install_mod.py` writes. One solid LZMA2 7z (`-mx7`, multithreaded): the manual download for players. (This port's size is in its release notes.) Needs 7-Zip (`C:\Program Files\7-Zip\7z.exe`, else `7z` / `7zz` / `7za` / `7zr` on PATH): without it the packager stops with an error before doing anything. `--no-data` (CI) writes `D2R-XL-2012-<version>-nodata.7z` |
| `RELEASE_NOTES-<version>.md` | default: skeleton for a downloader release (requirements, install steps; fill in Changes / Known issues by hand). `--notes TEMPLATE` writes a template's text instead (`tools/data/release_notes_alpha.md`: the hand-copied alpha, "Alpha for hand copying") |
| `SHA256SUMS` | sha256 of the 7z, the manifest and the notes (`sha256sum -c` format) |

`-mx9` is no smaller than `-mx7` on this data and takes longer. The download host builds its own copy of this 7z from
the objects (tools/dl_ingest.py, "Hosting layout"), so the whole 7z never goes over the uploader's line.

Reproducibility: the 7z is written from the sorted staging folder with all three time stamps off (`-mtm=off -mtc=off -mta=off`) and the staged files' mtimes set to
2026-01-01, so the same input gives the same bytes on the same machine with the same 7-Zip version (checked by `tools/test_package_release.py`). It is not byte-reproducible across machines or
7-Zip versions: `-mmt=on` splits the LZMA2 stream by the number of threads (the same data with another thread count: another size and
sha256), and 7-Zip versions may encode differently. The published manifest records the sha256 of the 7z the server
built; `files[]` (the content) does not depend on any of this.

Layout of the mod folder (the 7z's `mxl2012/`, the manifest's paths):

```
mxl2012.mpq/modinfo.json          {"name": "mxl2012", "savepath": "mxl2012/"}
mxl2012.mpq/data/...              install_mod.build_data: work/mod/data + global/dataversionbuild.txt (93847) + Median's
                                   tiles (ds1 ids renumbered) + HD scenes (maps_hd) + Median-only classic art
modinfo.json                       copy at the mod root (D2RLoader guide layout)
d2rloader/metadata.json            schemaVersion 1, namespace "mxl2012", metadata.modVersion = <version>,
                                   metadata.website = https://github.com/Nugwa628/mxl2012-d2r
d2rloader/config/d2rloader.toml    [d2rcore.save_format] mode = "extended" (no extra shared tabs: install_mod.EXTRA_SHARED_TABS = 0)
d2rloader/plugins/mxl2012-core.dll     the RELEASE plugin (cmake -DMXL_RELEASE=ON)
d2rloader/patches/                 empty
```

install_mod.py and package_release.py share the code (`install_mod.build_data`, `install_mod.write_mod_files`); a dev
install and a release differ only in the plugin build, `modVersion` / `description` / `website`, and the save folder of
slots 2 and 3.

What never goes in (package_release refuses or leaves it out):
- the test harness: the release DLL is built with `-DMXL_RELEASE=ON` (plugin/CMakeLists.txt): `testharness.cpp` and
  `harness_cmds.cpp` are not compiled, `testharness_release.cpp` has no-op entry points, so `mxl2012-testharness.txt` does
  nothing. package_release refuses a DLL that contains the string `mxl2012-testharness` or lacks the PluginVersion. The `mxl`
  console command's first line says `mxl2012-core <version> (release)` or `(dev)`.
- `mxl2012-testharness*`, `mxl2012-core-off.txt`, `input-bindings.toml`, `imgui.ini`, `debugsettings.json`, saves and their
  sidecars (`.d2s .d2i .d2x .d2rl .ctc .ctl .key .map .ma0-9`), `.log .dmp .pdb .orig`: the run stops if one is in the staged folder.
- byte copies of Blizzard's files: every staged data file that is identical (same path, same bytes) to
  `extract/d2r/93847/data/...` is removed (D2R reads its own); `dataversionbuild.txt` is written by us, not copied.

The default dev build is unchanged (`tools/build_plugin.ps1` -> `build/plugin/Release`, harness compiled in, off unless
`mxl2012-testharness.txt` exists). The release build goes to `build/plugin-release/Release`.

## Release manifest (schemaVersion 2)

Simple JSON, one object. The downloader must reject a `schemaVersion` it does not know. New fields may be added within
schemaVersion 2 (ignore unknown fields); a change of meaning or a removed field raises schemaVersion. 2 (2026-10-26)
removed `zip` (and with it the launcher's zip fallback) and added `archive` (the 7z) and `emptyDirs`; a schema 1 manifest
is refused by this downloader ("too new for the release"), a schema 3 one by a downloader of today ("too old": it offers the
manifest's `launcher` as a self-update). `package_release.py` writes the fields below except `objectsBase` and `launcher`
(added by `publish_release.py`) and `archive.path` (the server's ingest, which also replaces `archive` by the 7z it built).

```json
{
 "schemaVersion": 2,
 "name": "mxl2012",
 "version": "0.1.0",
 "pluginVersion": "0.1.0",
 "released": "2026-10-26",
 "complete": true,
 "d2r": {"build": "93847", "version": "3.3.0", "imageTimestamp": "0x6ab3782c"},
 "d2rloader": {"version": "1.3.1-beta", "url": "https://d2rloader.net/download/D2RLoader-1.3.1-beta.zip",
               "size": 47652455, "sha256": "9286c6b5bff7f1043658411dbea305faa9698b6a455e6441668fc6d02c22aad7",
               "signerThumbprint": "8001082E968FADAA58BF2F73EFA1810A11D0C28F"},
 "launch": {"default_mod": "mxl2012", "launch_arguments": ""},
 "modFolder": "mxl2012",
 "saveFolder": "mxl2012/",
 "preserve": ["d2rloader/config/d2rloader.toml"],
 "archive": {"format": "7z", "name": "D2R-XL-2012-0.1.0.7z", "size": 372345678, "sha256": "...",
             "path": "releases/0.1.0/D2R-XL-2012-0.1.0.7z"},
 "emptyDirs": ["d2rloader/patches"],
 "objectsBase": "objects/",
 "launcher": {"version": "0.2.5", "path": "launcher/0.2.5/D2R-XL-2012-Downloader.exe", "size": 12345678, "sha256": "..."},
 "fileCount": 8802,
 "totalSize": 791000000,
 "files": [
  {"path": "mxl2012.mpq/data/global/excel/armor.txt", "size": 123456, "sha256": "..."},
  {"path": "d2rloader/plugins/mxl2012-core.dll", "size": 874496, "sha256": "..."}
 ]
}
```

| Field | Meaning for the downloader |
|---|---|
| `version` | the release (tag `v<version>`); `pluginVersion` is the plugin's own PluginVersion (normally equal) |
| `complete` | `false` only for a CI `--no-data` package (no `mxl2012.mpq/data`): never install it for a player |
| `d2r.build` | the D2R build the private copy must be at. `imageTimestamp` is the PE TimeDateStamp of that `D2R.exe` (the plugin checks it, `plugin/src/build_guard_logic.h`) |
| `d2rloader` | the D2RLoader the release needs. The downloader compares `version` with `<D2R folder>\D2RLoader.exe` and, when it is missing or another version, shows "D2R-XL 2012 needs D2RLoader <version>" with a button to https://d2rloader.net/download.html. It never downloads D2RLoader (`url`, `sha256` are informational) |
| `launch` | what the game folder's own `d2rloader/config/d2rloader.toml` (section `[d2rloader]`) needs: `default_mod` = `mxl2012`. The player sets it in the game (gear on the character screen, Default Mod); the downloader does not write that file. `-txt` is not needed: D2RLoader 1.3.1 compiles the mod's `.txt` tables itself at each start (tested 2026-10-27, docs/launcher.md), except on the start that builds its base compiler snapshot (first start after installing or updating D2RLoader or D2R): that start has D2R's own sounds table with or without `-txt`, the plugin says so on screen and the next start is right (docs/bugs.md #46) |
| `modFolder` | every `files[].path` is relative to `<game>/mods/<modFolder>/`, with `/` separators |
| `saveFolder` | characters live in `Saved Games/Diablo II Resurrected/mods/<saveFolder>` (modinfo.json `savepath`); the downloader never writes there |
| `preserve` | files the player may edit: write them only when missing, never overwrite |
| `files` | the complete mod folder, sorted by path. Update = for each entry, download when the local file is missing or its size / sha256 differ; then delete local files under the mod folder that are not listed (except `preserve` entries and their `.retail-backup` copies (bug #512), and `d2rloader/logs/`, which D2RLoader writes) |
| `emptyDirs` | folders of the mod folder that hold no file (`d2rloader/patches`): the downloader creates them, the 7z has them |
| `archive` | the same content as a solid `.7z`: `format` `"7z"`, `name`, `size`, `sha256`; `archive.path` is where the host has it. The downloader uses it when the objects it would fetch add up to more than `size` (a fresh install): download resumable, check sha256, unpack with the built-in decoder, check every file (docs/launcher.md). Manual installs use it too |
| `objectsBase` | (published manifests, required by the downloader) where the file bytes are, relative to the site root: `objects/`. The bytes of `files[i]` are at `<root>/<objectsBase><sha256[0:2]>/<sha256>` |
| `launcher` | (published manifests, optional) the downloader build published with this release: `version`, `path` relative to the site root, `size`, `sha256` |

## Hosting layout (tools/publish_release.py, tools/dl_ingest.py)

Owner decision 2026-10-26: the release files live on our own server, not on GitHub (the forge needs a sign-in for
everything). A static HTTPS host serves one folder; the root URL is `https://dl.werdegames.com/mxl2012/` ("the site root"
below; the downloader takes it as its one setting). Setting it up: docs/hosting.md. Players get the same layout from the DigitalOcean Space
mirror behind Cloudflare, `https://files.werdegames.com/mxl2012/`: the server copies the site there after every ingest,
promote and gc (tools/dl_sync.py, channel files last; docs/hosting.md section 7).

```
channels/<channel>.json                   what a channel (stable, test) points to; the only file the downloader polls
releases/<v>/release-manifest.json        the packager's manifest + objectsBase, launcher, and the server's archive entry
releases/<v>/D2R-XL-2012-<v>.7z          the manual download for players, built on the server (-nodata.7z for a CI package)
releases/<v>/SHA256SUMS                   sha256 of the 7z, the manifest, the notes (sha256sum -c format)
releases/<v>/RELEASE_NOTES-<v>.md
objects/<sha256[0:2]>/<sha256>            the raw bytes of a file, named by its sha256; shared by every version
launcher/<v>/D2R-XL-2012-Downloader.exe     and D2R-XL-2012-Downloader.exe.sha256 (0.1.x: D2R-XL-2012-Launcher.exe)
assets/<files>                            the asset pack (lane pub-assets)
```

Next to the site root, not served: `incoming-mxl2012/` (on the server `/srv/dl/incoming-mxl2012`, the site is `/srv/dl/mxl2012`), where uploads wait for the server's check.
The host's existing site uses `/srv/dl/mxl` and `/srv/dl/incoming`; the two never share a folder
(docs/hosting.md "Design").

Channel file (`schemaVersion` 1, rules as for the manifest):

```json
{"schemaVersion": 1, "version": "0.1.0", "manifest": "releases/0.1.0/release-manifest.json",
 "manifestSha256": "...", "publishedAt": "2026-10-26T12:00:00Z"}
```

What the downloader does (all URLs are `<root>/` + the relative path):

1. `GET channels/<channel>.json` (the host sends `Cache-Control: no-cache`); reject an unknown `schemaVersion`.
2. `GET <manifest>`; its sha256 must equal `manifestSha256` (this also detects a half-updated host or a stale cache);
   `schemaVersion` must be 2.
3. When the objects to fetch add up to more than `archive.size` (a fresh install): `GET <archive.path>` resumable into
   `%LOCALAPPDATA%\mxl2012\download`, check its sha256, unpack the files it still needs into staging inside the mod
   folder, check each file's size and sha256 and move it into place. Whatever is still missing after that (or when the
   7z fails) comes from the objects. Then
   for each entry of `files` that is missing locally or differs in size / sha256: `GET <objectsBase><sha[0:2]>/<sha>`, check
   size and sha256 of what arrived, then move it into place. Objects never change, so a partial download is resumed
   with a `Range` request and a cache may keep them forever. Several entries with the same sha256 are one download. Each
   object is tried 5 times (resumed, with a growing pause); then the install stops with "Download failed ... try again",
   and what was installed so far stays (the next Update continues from there). There is no other source.
4. Files under the mod folder that the release does not list are removed (except `preserve` and D2RLoader's logs);
   `emptyDirs` are created; the state file records the release.
5. Downloader self-update: `launcher.version` / `.path` / `.sha256` of the channel's manifest.

### Publishing: a delta upload, checked and finished on the server

The uploader's line is slow (about 160 KB/s up) and every SSH login costs seconds, so `publish` sends only what the host
lacks, packed, in as few logins as possible, and the server does everything else:

1. One login lists `objects/` (only the prefix folders the release uses), the release folder and `incoming-mxl2012/`.
2. The objects the host lacks (or has with another size) go into one solid 7z (`-mx7`), entries named by their sha256:
   `objects-<sha256 of the 7z, 16 hex>.7z`. It is kept in `dist/upload/<v>/` so a re-run sends the same bytes.
3. One login uploads, into `incoming-mxl2012/<v>.uploading/`: that 7z, the manifest (without `archive`, plus `objectsBase` and
   `launcher`), the notes and the downloader exe. Each under a temp name and renamed; the 7z under the fixed name
   `<name>.part-0`, continued with `reput` when a dropped connection left part of it. Then `READY` (JSON: version, channel,
   size and sha256 of every file, the 7z's name, `force`), **last**, and the folder is renamed to `incoming-mxl2012/<v>/`. When the
   connection drops, the upload is retried (5 times, a growing pause), each time resuming the 7z; when all fail, running
   the same command again resumes.
4. On the server, a systemd path unit sees the rename and runs `tools/dl_ingest.py` as the upload user. It checks every
   file against `READY`, the manifest (schema 2, safe paths, sizes), lists the objects 7z before unpacking it (plain files
   named by a sha256 the manifest uses, with that size; no folders, links or other names), unpacks it into
   `incoming-mxl2012/<v>/.work/`, checks every object's sha256 against its name and moves them into `objects/`. Every object the
   manifest names must then be on the host. It links the player's `mxl2012/` folder together from the objects (each one
   hashed again) and packs `releases/<v>/D2R-XL-2012-<v>.7z` with the packager's switches, writes the notes, the manifest
   (with `archive` of that 7z), `SHA256SUMS`, `launcher/<lv>/`, and the channel file **last**. Then it deletes
   `incoming-mxl2012/<v>/` and `*.part-*` files older than an hour anywhere in the site (leftovers of dead uploads).
5. Anything that fails a check is refused: nothing is published, the reason goes to the journal and to
   `incoming-mxl2012/<v>/REFUSED`, the folder stays for a look, and the next `publish` of that version says why
   (`publish --force` deletes it and uploads again). `dl_ingest.py --retry <v>` tries a refused upload again.

Rules the downloader can rely on:

- The channel file is written last, after the objects, the 7z and the manifest are in place; a half-finished publish is
  never visible. Every file is written under a temp name and renamed.
- A published version never changes (`releases/<v>/` and the objects it names): the ingest refuses another manifest under
  a published version unless the upload says `force` (`publish --force`). A new build is a new version.
- Objects are only added by the ingest; `gc --keep N` removes releases older than the newest N and the objects only they
  used, and never a version a channel points to.

```
py -3 tools/publish_release.py publish --version 0.1.0 --channel test --target sftp://user@host/mxl2012 [--launcher EXE] [--assets DIR]
py -3 tools/publish_release.py promote 0.1.0 --channel stable --target ...
py -3 tools/publish_release.py list | gc --keep 3 [--dry-run] --target ...
py -3 tools/publish_release.py verify --url https://dl.werdegames.com/mxl2012/ --channel stable   # fetch + sha256 over HTTPS
py -3 tools/serve_dir.py <folder>                                                              # local Range-capable test host
python3 tools/dl_ingest.py --root <folder that holds incoming-mxl2012/ and mxl2012/> --site mxl2012 --incoming incoming-mxl2012 \
    --archive-prefix D2R-XL-2012 --launcher-name D2R-XL-2012-Downloader.exe --mod-folder mxl2012 [--retry VERSION]   # what the server runs
```

`publish` reads the file bytes from the packager's 7z (the staging folder is deleted after packaging; it unpacks it once
into `dist/upload/<v>/`), checks every object against the manifest while packing, and refuses a `complete: false` package
for the stable channel (`--allow-incomplete` lets one onto `test`). It answers with one of: uploaded (the server takes it
from there, usually within a minute plus the time to build the 7z), waiting (an upload of this version is already in
`incoming-mxl2012/`), or published already (then it only sets the channel). `promote` and `gc` write the site directly
(the channel file, deletes). Targets: `dir:<path>` (a local folder: tests, or a run on the server; `<path>/../incoming-mxl2012`
is the incoming folder) and `sftp://user@host[:port]/<path>` (OpenSSH `sftp`, key login, no shell needed on the server).
`verify` downloads the channel, the manifest, every object (or `--sample N` of them) and the 7z and checks every sha256.

Tests: `tools/test_publish_release.py` (delta selection, READY last and the folder rename, two sftp logins for a
publish, resume after a dropped connection, a refused upload and `--force`, gc safety, the sftp backend against
`tools/fake_sftp.py`, publish -> ingest -> `serve_dir.py` -> `verify`) and `tools/test_dl_ingest.py` (every refusal: a
damaged file, an object with a wrong sha256, a missing object, an entry that is no object, a link, a file READY does not
list, bad paths, old schema; the channel written last; re-runs; temp-file cleanup; the 7z it builds equals the packager's).
Both use 7-Zip when it is installed, else `tools/fake_7z.py`.

## Wrong game build

The plugin (plugin/src/mxl2012_core.cpp, `build_guard_logic.h`, unit test
`plugin/tests/build_guard_test.cpp`): the plugin goes on only when the `D2R.exe` PE timestamp is `0x6ab3782c` and
D2RLoader's build name (when it gives one) is `93847`. Otherwise it installs nothing (no hook, patch or harness), writes
an ERROR line to `d2rloader.log`, draws the line at the top of the screen through D2RLoader's overlay service, and `mxl`
prints it:

    D2R-XL 2012 0.1.0 needs D2R build 93847; this is 94100. The mod's engine changes are off.

(For a different `D2R.exe` with the same build number: `this is 93847 with another D2R.exe (image 0x...)`.)
D2RLoader 1.3.1 itself checks the game build at start (`D2RCore.dll build compatibility verified`, `Loaded build
configuration for <hash>` in `d2rloader.log`); a build it has no configuration for may not start at all. Not tested in
game: no other D2R build is installed here; the decision is covered by the unit test.

## Making a release

1. `py -3 tools/build.py` (needs the D2R baseline and the native libs: `tools/lane_setup.py`, docs/setup.md), D2R build 93847 installed for
   `maps_hd` (`--game`, default `MXL_D2R_GAME` or the slot 1 folder; only read).
2. `py -3 tools/package_release.py [--version X]`: builds the release plugin (`tools/build_plugin.ps1 -Release`: CMake on PATH or Visual Studio's, the PluginSDK of `.mxl-local.json`; nothing is downloaded), stages, leaves out byte copies of D2R's files (the baseline extraction and the shared D2R cache; without a baseline the run stops), checks, writes
   `dist/`. `--plugin DLL` uses a release DLL built elsewhere (it is checked); `--data-from <mods\mxl2012\mxl2012.mpq\data>`
   copies a finished data folder instead of rebuilding it.

   **One version number.** The release version is `PluginVersion` in `plugin/src/mxl2012_core.cpp`. That number appears in:
   - the release name;
   - the d2rloader metadata;
   - the plugin's `mxl` line;
   - the build-guard message.

   Raise it for every player release, even a repackage with the same code.
   - `--version` must equal it. Otherwise the packager stops; only `--no-data` builds may differ.
   - Publishing a version that is already on the host is refused (without `--force`).

   The downloader has its own version (`MXL_LAUNCHER_VERSION` in `launcher/src/win/app.h`), because it updates separately.
3. Fill in `RELEASE_NOTES-<version>.md`, tag `v<version>`.

   **Or run all of it at once:** `bash tools/release.sh <version>` (Git Bash on the game PC, from `main` at the release
   commit) checks the clean tree, `PluginVersion == <version>` and the `### <version>` CHANGELOG section, runs the pipeline's
   unit tests, then (steps 1, 2 and 4 below) packages, publishes, waits until the channel shows the version on
   `files.werdegames.com/mxl2012/`, and runs `verify`; with `--with-github` it also does step 5. `--check-only` stops after
   the checks; `--channel test` is for a first run; settings (`MXL_PUBLISH_TARGET`, `MXL_PUBLISH_IDENTITY`) are environment
   variables, listed in the script's header. Publish output is never piped through `tail`: the upload takes minutes and a
   pipe would hide its exit status.
4. `py -3 tools/publish_release.py publish --version <version> --channel test --target sftp://...` (when a downloader or asset
   pack goes along: `--launcher`, `--assets`), look at it with the downloader on the test channel, then
   `promote <version> --channel stable`. "Hosting layout" above; server setup in docs/hosting.md.
5. **Changelog and GitHub release.**
   1. Add a `### <version>` section to `CHANGELOG.md`, written for players. Downloader versions get their own section
      under "D2R-XL 2012 Downloader".
   2. Mirror main to GitHub with the scrub script (outside the repo).
   3. Run `py -3 tools/github_release.py <version> --commit <full sha of that commit on GitHub main> --latest`, plus
      `--downloader <exe>` when a new downloader ships. The release notes are the CHANGELOG section and the download
      links. The 7z stays on files.werdegames.com and is not attached.
   4. Make the **forge** release the same way: `py -3 tools/github_release.py <version>
      --forge --commit <full sha of the forge's own commit> [--downloader <exe>]` (token: ~/.mxl2012-d2r/forge_token or MXL_FORGE_TOKEN). The forge's history is not scrubbed,
      so its commit ids differ from GitHub's.

CI (`.forgejo/workflows/release.yml`, runner `mxl-cross`, manual dispatch or tag `v*`): no game files on the
server, so it cannot run tools/build.py. It cross-builds the release DLL, runs the packager's unit tests and
`package_release.py --no-data`, and keeps `dist/` as the artifact `mxl2012-d2r-release` (`D2R-XL-2012-<v>-nodata.7z`,
manifest with `"complete": false`; the runner needs 7-Zip, the job checks for it first). It checks that the release plugin
builds and packs; the player release comes from the game PC.
No GitHub workflow uses a self-hosted runner.

## Alpha for hand copying

Owner request 2026-10-28: an alpha the owner copies by hand (USB stick, own cloud) to another PC; no upload, no channel, no
downloader. One command on the build PC, from a lane worktree or the main checkout:

```
pwsh -NoProfile -File tools\cut_alpha.ps1 [-SkipBuild] [-Tests] [-Out DIR] [-Scratch DIR] [-NoReference]
```

1. `py -3 tools/build.py` (full build; stops on validate errors; `-SkipBuild` takes `work/mod` as it is);
2. `tools\build_plugin.ps1 -Release` (`-Tests` also runs the plugin's unit tests);
3. `py -3 tools/package_release.py --plugin build\plugin-release\Release\mxl2012-core.dll --out <Out> --notes tools/data/release_notes_alpha.md`;
4. `py -3 tools/verify_package.py <Out>\D2R-XL-2012-<v>.7z --scratch <Scratch>`: lists the 7z (nothing outside `mxl2012/`),
   unpacks it as a player would, checks it against the manifest and SHA256SUMS and as a mod folder (modinfo.json savepath
   `mxl2012/`, metadata, extended saves, release DLL without the harness, no test or player files), then writes what
   `install_mod.py` installs (save folder `mxl2012/`) next to it and compares every file: the same bytes except the plugin
   (release against dev DLL) and `d2rloader/metadata.json`; what the package lacks must be a byte copy of D2R's own.
   `verify-report.json` in the scratch folder keeps the numbers.

`<Out>` defaults to `<runs>\dist-alpha` (never inside the checkout), `<Scratch>` to `<runs>\alpha-verify`. The version is
PluginVersion (no bump for the alpha; "alpha" is in the notes' title only). What the owner copies: the 7z and
`RELEASE_NOTES-<v>.md` (SHA256SUMS to check the copy). The notes are written for a player on a fresh PC: D2R build 93847,
D2RLoader 1.3.1-beta from d2rloader.net, unpack into `<D2R>\mods\`, Default Mod, where saves go, the alpha's limits, what to
send with a bug report.

## Manual install (fallback)

Into a D2R folder at build 93847 that has D2RLoader 1.3.1-beta (docs/setup.md step 10):

1. Unpack `D2R-XL-2012-<version>.7z` into `<D2R folder>\mods\` (Windows 11 opens .7z files; otherwise use
   [7-Zip](https://www.7-zip.org)): `<D2R folder>\mods\mxl2012\mxl2012.mpq\modinfo.json` must exist.
2. Start `D2RLoader.exe`, click the gear on the character screen, set Default Mod to D2R-XL 2012, Apply, and start
   D2RLoader again (or set `default_mod = "mxl2012"` in `<D2R folder>\d2rloader\config\d2rloader.toml`). `-txt` is
   not needed. The very first start of a new D2RLoader (or after a D2R / D2RLoader update) builds its table cache and
   loads D2R's own sounds table; the plugin then says "Close the game and start it again" (docs/bugs.md #46).
3. Start `D2RLoader.exe`. Saves: `Saved Games\Diablo II Resurrected\mods\mxl2012\`.
4. Update: delete `mods\mxl2012\mxl2012.mpq\data`, unpack the new release over the folder (keep your own
   `mods\mxl2012\d2rloader\config\d2rloader.toml` if you edited it).

## Tested

- Scripts (2026-10-28, lane hosting): `tools/test_package_release.py`, `test_publish_release.py`, `test_dl_ingest.py`,
  `test_dl_sync.py`, `test_github_release.py` (no network): a publish into a local site folder with its own
  `incoming-mxl2012/` next to a second product's `mxl/` + `incoming/`, the ingest with this product's flags, the sync into a
  `mxl2012/` prefix of a Space that already holds an `mxl/` prefix (its files, state and deletions untouched).
  The earlier `test_dl_ingest.py`, `test_publish_release.py` and `test_dl_sync.py` also pass against this `dl_ingest.py`
  with its defaults, which is what lets one installed copy serve both products.
- First real package (2026-10-28, lane alpha, `tools/cut_alpha.ps1 -SkipBuild` after a fresh full `tools/build.py`,
  validate 0 errors, text audit 0): `D2R-XL-2012-0.1.0.7z` 131,965,879 bytes (132 MB), 3,258 files, 469 MB unpacked;
  45 files left out as byte copies of D2R's own (34 `global/excel/{,base/}` tables such as armtype, composit, monmode,
  objmode, plrmode, skillcalc, soundenviron, the unique-name tables; 10 act 4 / town `.ds1`; `hd/overlays/common/lightning.json`);
  `verify_package.py`: every file equals install_mod.py's except the plugin and metadata.json. Not installed into a game
  from the 7z yet (all slots busy; no tool installs a local 7z into a slot).
- Not done yet: a publish to the real host, the real Space and Worker.
