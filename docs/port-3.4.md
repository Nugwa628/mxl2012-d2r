# Port to D2R 3.4 build 95032: scope and port (lane port34, 2026-11-11 and 2026-11-12)

What it takes to run D2R-XL 2012 on Diablo II: Resurrected 3.4 (build 95032). Sections 1 to 7 are the scope as measured
on 2026-11-11, before anything was changed; section 8 is the port for D2RLoader 1.3.1 that followed on 2026-11-12 and
the rule it was done under. Evidence is outside git in `mxl2012-runs/port34/` (file names below are
relative to it). Slot 1 is the 3.4 install, slot 2 the 3.3 install (docs/testing.md "Game slots").

**Rule (owner, 2026-11-12): plugins are never tied to a game build or version. A part installs when the code it needs is
what it expects (expected bytes or signature), and turns itself off with a log line when it is not.** Where sections 5
and 6 proposed to accept a list of build names, that proposal is withdrawn: the build-name test is removed instead
(section 8.1).

## 1. Summary

- **D2RLoader 1.3.1-beta brings its own game image.** `D2RLoader.exe` is a packed copy of the game program (PE time stamp
  `0x6ab3782c`, a 30 MB `.text`), the same file in the 3.3 and the 3.4 install. The stamp our plugins check is this file's,
  not the stamp of Blizzard's `D2R.exe` (`0x6a6b96a4` for 3.3, `0x6ad81202` for 3.4, both encrypted on disk). On the 3.4
  install the running image is byte for byte the 3.3 one (section 3.3). So **with D2RLoader 1.3.1 every address, hook and
  patch of ours is unchanged on 3.4**; what 3.4 changes is the data the game reads and the build name D2RLoader reports
  (`95032`).
- **Why the loader start stopped:** D2RLoader shows a notice window ("This D2R version hasn't been fully tested yet") and
  waits for OK before it starts the game (section 2).
- **There is no D2RLoader release for 3.4** (section 2.3). When one comes with a new game image, the full address re-port
  is due (section 5); until then it is not.
- **With our mod on 3.4:** the game reaches the main menu, the core plugin loads, sees build name `95032`, installs nothing
  and says so; `drawcap` has no build-name test and patches as on 3.3 (section 3).
- **Data:** 86 of the 91 tables are identical, 5 differ in rows only; no table gained, lost, renamed or moved a column
  (section 4). Built against the 3.4 files, the mod differs from the 3.3 build in 16 small art definition files
  (section 4.4).

## 2. D2RLoader's start on 3.4

### 2.1 Why the boot check stopped

`slot_share.py bootcheck` waits for the `[CASC] ... paths:` line of `d2rloader.log`. On 3.4 the log stops after

```
[WARN] This D2R version hasn't been fully tested yet. You're running Diablo II: Resurrected 3.4. The latest version officially supported by D2RLoader is 3.3.
```

because D2RLoader opens a modal Windows task dialog about 0.5 s after the start, before it starts the game, and waits.
Window enumeration of our own launch (`run1-mxl2012-observe/timeline.json`, picture `run2-mxl2012-ok/window-01-n32770.png`):

| Field | Value |
|-|-|
| Window | class `#32770`, title `D2RLoader`, one child `DirectUIHWND`, one button |
| Heading | This D2R version hasn't been fully tested yet |
| Text | You're running Diablo II: Resurrected 3.4. The latest version officially supported by D2RLoader is 3.3. D2RLoader will still try to launch normally, and everything may work just fine. You could occasionally run into unexpected issues, though. |
| Check box | Don't remind me again for D2R 3.4 |
| Button | OK |

No game window exists while the dialog is open; the 90 s timeout of the boot check is that wait.

### 2.2 Getting past it without a foreground click

- **No configuration key.** `d2rloader\config\d2rloader.toml` has no entry for it, and none of the 74 configuration key
  names in `D2RCore.dll` is about the version notice (`d2rcore-config-keys.txt`). The warning's text is not readable in
  `D2RLoader.exe` (packed), `D2RCore.dll` or `d2rloader.mpq`, so no switch could be read from them either.
- **The supported permanent way is the dialog's own check box** ("Don't remind me again for D2R 3.4"). It is the install
  owner's choice; this lane did not tick it (`d2rloader\data\state.json` is unchanged, copy in `state-backup/`).
- **For scripted runs: answer the dialog of our own launch by message.** A task dialog takes `TDM_CLICK_BUTTON`
  (`WM_USER + 102`, `wParam` = `IDOK`) posted to its window. `loader_run.py --ok-dialog` does that for the `#32770` window
  titled `D2RLoader` that belongs to the process it started and whose only button is OK. No focus, no key or mouse input,
  no hook: the dialog and the game window were sent to the bottom of the window order without activation and were never
  the foreground window in the samples. The game then starts normally.
- **In the tools since 2026-11-12:** `slot_share.py bootcheck` and `game_ctl.py start` do this step
  (`tools/loader_notice.py`, section 8.2).

### 2.3 Is there a D2RLoader release for 3.4?

No. The public download page (d2rloader.net, read 2026-11-11, copies in `web/`) lists **1.3.1-beta** as the latest
version; the changelog's last entry is 1.3.1-beta (September 24, 2026): "Added official support for D2R 3.3". The archive
on the server was last changed 2026-10-19 (the page carries two checksums for 1.3.1-beta, so it was re-issued once under
the same version). Nothing mentions 3.4 or build 95032. Nothing was downloaded into a game install.

## 3. What runs on 3.4

All runs: slot 1 under its lock (owner `port34`), background only, shared files restored and verified after each run.

### 3.1 With `-mod mxl2012` (`run2-mxl2012-ok/`)

- The game reaches the main menu with the mod's menu and character list (`shot-04-t40.png` to `shot-08-t135.png`);
  `D2R startup complete.` 14 s after the launch. It closed on `WM_CLOSE`. No crash, no new crash report.
- D2RLoader reports `build-name 95032`, `version 3.4.0`; these come from the install's data (its build configuration),
  not from a program file.
- It loads both plugins of the installed mod: `Draw List Cap 0.2.0` and `D2R-XL 2012 core 0.1.19`.
- **Core plugin** (`mxl2012-core.log`): loaded, engine hooks off, as designed:
  ```
  mxl2012-core 0.1.19 loaded (mod mxl2012, D2R 3.4.0, image 0x6ab3782c; not the expected image, engine hooks stay off)
  [ERROR] D2R-XL 2012 0.1.19 needs Diablo II: Resurrected 3.3; this game is a different version. The mod's engine changes are off.
  [ERROR] mxl2012-core: wrong game: image 0x6ab3782c, buildName 95032 (another build); expected image 0x6ab3782c, buildName 93847
  ```
  The image **is** the expected one; only the build name differs. The words "not the expected image" in the first line
  are wrong for this case.
- **`drawcap` is not held back.** It tests the image stamp only, found its 7 places at the 3.3 addresses and applied all
  14 edits (`drawcap.log`: "patch on: cap 12000 (was 3000) at 7 sites"). That is correct for this image, and it shows that
  the two plugins do not follow the same rule.
- The plugin's on-screen notice line is not in the five main menu pictures. It is drawn through D2RLoader's overlay
  service; whether it only shows in a game was not checked (no game was entered: without the engine parts the mod is not
  playable, and a character must not be saved in that state).
- **The installed `mods\mxl2012` of slot 1 is a lane's test install, not a release build**: installed 2026-11-11 15:54,
  plugin 0.1.19 as a test-harness build, 5,139 data files against 5,122 in the main checkout's build, 42 of them different
  (item pictures, one monster's animation files) and 17 extra (`diff/slot1-installed-vs-main33.txt`). It was good enough
  for the start test and was not reinstalled.

### 3.2 Plain D2RLoader (`run3-plain/`, mod `legacy169-plain`, no plugin files)

Main menu reached (`shot-05-t35.png` to `shot-07-t80.png`), no plugin loaded, no crash, closed on `WM_CLOSE`.

### 3.3 The running image on 3.4 is the 3.3 image

`loader_run.py --textdiff` read the main module of our own launch (plain run) and compared it with the project's 3.3
memory dump (`run3-plain/image-diff-ranges.txt`):

| Section | Different bytes | What they are |
|-|-|-|
| `.text` (30 MB) | 35, in 7 runs of 5 | the 7 inline hooks of our own plugin that the dump contains (it was taken with the plugin loaded: `0x56ac00` is the Whirlwind hook, and the dump's bytes after the jump equal the hook's expected entry bytes) |
| `.rdata` | 1,200, all inside the first 0x1330 bytes | the start of the section, where the resolved import addresses lie (they differ per start) |
| `.pdata` | 0 | |

Time stamp of the running image: `0x6ab3782c`. `D2RLoader.exe`, `D2RCore.dll` and `d2rloader.mpq` have the same SHA-256
in slot 1 and slot 2. So 3.4 under D2RLoader 1.3.1 is: **3.3's game code, 3.4's data**. What 3.4 added in code (if
anything) is not there, and what its data expects of new code is read by 3.3 code.

### 3.4 Side effects of the three runs on the install

Whole-install scan before and after, `Data\` excluded (`scan-before.json`, `scan-after-run3.json`): changed are only
`blz-log.txt`, `d2rloader\logs\d2rloader.log`, `dxdiag.txt` and our mod's two plugin logs; D2RLoader replaced its own
cache `d2rloader\data\compiler\3.3.0\` (368 files) by `compiler\3.4.0\` (368 files) on the first start ("Preparing base
compiler snapshot 3.4.0"). The loader log also shows the game's own storage layer fetching a configuration; `Data\` was
not scanned.

## 4. Data: 3.3 build 93847 against 3.4 build 95032

`extract_95032.py` reads slot 1's storage with CascLib, read only (`tools/lane_setup.py --cache-from-slot` still refuses
slot 1; it was not used or changed): every file under the folders the project's 3.3 extraction holds, 54,071 files, 0
failed, into `extract-95032/`. `diff_extracts.py` compares it with the 3.3 extraction (`MXL_D2R_EXTRACT`); results in
`diff/` (`summary.json`, `tables.md`, `files-changed.txt`, `tables/<table>.diff.txt`).

- Names in the storage: 175,823 in both builds, none added, none removed.
- Of the 36,644 files of the 3.3 extraction: **36,227 identical, 417 changed**.

### 4.1 Tables

The claim "86 of 91 data tables identical" is **confirmed**: of the 91 `data/global/excel/*.txt`, 86 are identical and 5
changed. All 91 tables of `data/global/excel/base/` are identical.

| Table | Rows 3.3 -> 3.4 | Rows changed (cells) | Columns | Added | Removed | Renamed | Reordered |
|-|-|-|-|-|-|-|-|
| `propertygroups.txt` | 33 -> 34 | 0 (one new row at the end) | 57 -> 57 | - | - | - | no |
| `runes.txt` | 181 -> 181 | 1 (9) | 53 -> 53 | - | - | - | no |
| `setitems.txt` | 141 -> 141 | 8 (32) | 102 -> 102 | - | - | - | no |
| `sets.txt` | 36 -> 36 | 1 (5) | 69 -> 69 | - | - | - | no |
| `uniqueitems.txt` | 439 -> 439 | 18 (164) | 75 -> 75 | - | - | - | no |

What the rows are (the patch notes' item changes):

- `propertygroups.txt`: new group `eternity-update` (id 33: `swing1` 30, `dmg/lvl` 24, `indestruct`).
- `runes.txt`: `Runeword36` (Eternity) takes `itype2` = `miss` (missile weapons), 300-390 damage, the new group in place of
  `indestruct`, an `oskill` in place of the charges; ladder season 16.
- `sets.txt` / `setitems.txt`: Isenhart's set reworked (4 items and the full set bonus), Angelic set items' last ladder
  season 16 -> 15.
- `uniqueitems.txt`: 18 uniques reworked (Griswold's Edge, The Tannr Gorerod, Dimoak's Hew, The Grim Reaper, Serpent Lord,
  The Salamander, Victor's Silk, Coldkill, Earthshaker, The Atlantian, Swordguard, The Impaler, Grim's Burning Dead,
  Lavagout, Veil of Steel, Executioner's Justice, Ethereal Edge, Demonhorn's Edge), all with ladder season 16.

The five matching `.bin` files and `dataversionbuild.txt` (`93847` -> `95032`) changed with them; no other `.bin` did.

**What the table migration needs: nothing.** `tools/txt_migrate.py` maps columns by name (`column_map`: D2R's header is
read from the extraction, a mod column is matched by name, case-insensitively, then by the rename and split lists), and
no header changed. The approach without `.bin` files is not touched either: the mod ships `.txt` only, and the five
changed tables are ones where the mod's rows replace D2R's. The built tables are identical for both extractions (4.4).

### 4.2 Other files of the extraction that changed (412)

| Files | What changed | Matters for us |
|-|-|-|
| 367 `.sprite` under `data/hd/global/ui` (item pictures, controller art, panels) | one header byte (offset 31) in each; same size, same pixels | no |
| 13 `data/hd/global/ui/vo_durations/*.json` | same size; the English one is equal as JSON | no |
| 13 `data/hd/character/enemy/*.json` (act5barb2, act5barb3, blunderbore1, bonefetish1, brute2, cantor1, colbarbthrow, corruptrogue1, councilmember1, maggotbaby1, regurgitator1, sandmaggot1, scarab1) | only the `dependencies` lists (textures to preload) | yes, small: our monster variants copy these lists (4.4) |
| 4 overlays (`common/steallife`, `monster/mephisto`, `necro/bonearmor_front`, `paladin/redemptionback`), 1 missile (`skull_poison`) | only `dependencies` paths | one overlay is copied into the mod (4.4) |
| `data/hd/vfx/particles/env/ui/vfx_character_create_fire.particles` | effect of the character creation screen | no |
| `strings/ui-controller.json` | 15 new keys (controller rumble option texts) | no (the mod's strings are separate files) |
| `strings/item-names, levels, skills, ui, vo, ui-controller` | 14 entries changed in translations only; no English text, no id | no |
| `next_string_id.txt` | 28106 -> 28139 | no: the mod's string files carry no ids |

No file under `data/global/ui` (the 329 layout files and the classic art) changed, so every layout we patch is the same.

### 4.3 Files of the shared cache (`MXL_D2R_CACHE`)

The cache holds 7,476 D2R files the extraction lacks. By content key against 3.4 (`diff/cache-changed.txt`): 7,392
identical, **84 changed**: `data/hd/model_lod_desc.bin` (same 14,310 entries and keys; only padding bytes differ), 46 HD
scene presets `data/hd/env/preset/...` (collision boxes and dependency lists; same number of entities), 37 `.particles`
files. A 3.4 cache therefore has to be filled once from the 3.4 install (`--cache-from-slot` refuses slot 1 today; that
refusal is the owner's rule, so the fill needs a decision).

### 4.4 Does our build still work against 3.4 files?

Yes. `tools/build.py` ran in this lane's own worktree with `MXL_D2R_EXTRACT` pointed at a 3.4 tree holding exactly the
file set of the 3.3 extraction (`extract-95032-sameset/`, hard links). Every step passed (exit 0), `validate.py` 0 errors (171 plugin notes, 13 warnings: the
numbers of the 3.3 build), strings check 0 errors (`build-34.log`). Compared with the main checkout's 3.3 build,
file by file (`diff/build-main33-vs-34.txt`):

- 5,193 files, same paths; **17 differ**: 15 `data/hd/character/enemy/mxl_*.json` (our variants of blunderbore1,
  bonefetish1, brute2, cantor1, councilmember1, maggotbaby1, regurgitator1, scarab1: they carry D2R's new dependency
  lists), `data/hd/overlays/common/redemptionback.json`, and one count line of `migrate_report.md`.
- Every table, string file, layout, map, sound and picture is byte-identical.

A second build with the 84 changed cache files in their 3.4 version as well (`build-34-cache34.log`, exit 0, `validate.py`
0 errors) changes 41 more files (`diff/build-34-vs-34cache34.txt`): 38 of our recoloured `.particles` effects, one scene
preset of ours (`harem2.json`), `model_lod_desc.bin` (padding bytes) and the recolour report.

So one mod package can serve both game versions: the differing files are art definitions copied from D2R's own with
small changes on D2R's side.

## 5. Address work

### 5.1 What our plugins hold

Counted from the sources (`count_addresses.py`, `address-counts.md`): an address is a distinct image offset in code.
`docs/d2r-addresses.md` documents 1,081 distinct offsets in all (analysis included).

| Plugin | Parts with addresses | Code addresses | Data addresses | Inline hooks | Byte patches | Found by pattern | Build test |
|-|-|-|-|-|-|-|-|
| `mxl2012-core` | 41 of 54 | 321 | 47 | 40 | 27 | none: all fixed | image stamp and build name |
| `drawcap` | 1 | 3 (cross-check only) | 0 | 0 | 14 edits at 7 places | all 7 places | image stamp only |
| `invtabs` (branch `lane/invtabs`) | 3 | 24 (log hints only) | 1 | 0; it wraps 5 entries of one vtable | 0 | all: 23 signatures | none: it runs where the signatures match once |
| D2R-Legacy169 (pinned submodule, `d6fe85d`) | 1 patch table | 54 | 4 | 2 | 36 | none: all fixed | image stamp and build name |

The largest parts of the core: the test harness commands (123 addresses; they serve the automated checks), the
Median stash tabs (29), the state lists (24), the classic fonts (23), the shared image interface `d2r.h` (22), the dev
menu (18), the melt trail (18), Send to stash (17), the tab flash (16), the charm copy rule (14). Every inline hook and
every byte patch carries the bytes it expects, so a wrong address turns its part off; it does not corrupt the game.

### 5.2 The pattern sample

It cannot be done as asked: both `D2R.exe` files are encrypted on disk (`.text` entropy 8.00), and our addresses are not
`D2R.exe`'s but D2RLoader 1.3.1's image. The stronger check replaces it: the whole running `.text` on 3.4 equals the 3.3
dump except our own 7 hook jumps in the dump (3.3). All sampled functions, and every other one, sit at the same address:
**offset 0**. `drawcap`'s 7 patterns confirm it from the plugin side (found at the 3.3 places).

### 5.3 Estimate

- **3.4 with D2RLoader 1.3.1 (today):** no address work. The guard must stop comparing the build name (core and
  D2R-Legacy169; done, section 8.1), nothing else in the plugins.
- **A later D2RLoader with its own 3.4 image:** every fixed address moves: 368 in the core over 41 parts, 58 in
  D2R-Legacy169. `drawcap` and `invtabs` look their places up and need a check of their logs only. If the code itself
  barely changed (3.4 is an item balance patch by its data), most functions can be found again by byte signature from the
  3.3 dump; a tool that derives one signature per used address and proves it unique in the 3.3 dump can be written and
  tested today, before any new image exists.

## 6. Proposed order of work (proposals; nothing here was started)

| Step | What | Size |
|-|-|-|
| 1 | Tools: answer D2RLoader's notice in `slot_share.py bootcheck` and `game_ctl.py start` (or the owner ticks the check box once). **Done, section 8.2** | half a day |
| 2 | Guard: no build-name or version test at all; one check of the running image (stamp `0x6ab3782c` and code probes) in front of the fixed addresses, in the core and in D2R-Legacy169; unit tests. **Done, section 8.1** (the first proposal here, a list of accepted build names, is withdrawn) | half a day |
| 3 | Launcher and release manifest: never block for the game's version; the manifest's `d2r` block is information. **Done, section 8.3** (the first proposal, a list of game versions, is withdrawn) | one day |
| 4 | Fill a 3.4 file cache; optionally build against 3.4 (16 files differ). Not needed now: one package serves both versions (section 4.4) | hours |
| 5 | Full test pass of the mod on 3.4 in slot 1 (the check suites, HD and classic, a save made on 3.3 loaded on 3.4 and back) | 2 to 3 days of runs |
| 6 | Signature tool for all used addresses, proven on the 3.3 dump, as preparation for a new D2RLoader image | 3 to 5 days |
| 7 | When D2RLoader ships a 3.4 image: re-port (signature tool, then the parts whose code changed by hand), full test pass | 1 to 2 weeks with the tool, 3 to 4 without |

**Both versions at once.** With D2RLoader 1.3.1 it is practical and close to free: same image, same addresses, same mod
package; nothing in the plugins or the launcher knows a game version, only the test matrix has two. Across two different D2RLoader images it is
not practical with fixed addresses (two address sets in 41 parts, every part tested twice); it becomes practical only
if addresses are looked up by signature at load (step 6), and then each image still needs its own test pass.

## 7. Not checked

- Anything in a game on 3.4: no game was entered. Whether 3.3 code plays correctly on 3.4 data is unknown; the owner
  reports that players run this build with D2RLoader. (Since then: the short smoke of section 8.4.)
- The on-screen wrong-version line of the core plugin (not in the main menu pictures).
- The content of the storage's other 131,700 files (models, textures, sounds, video): the names are the same in both
  builds, the content was compared only for the 36,644 extracted files and the 7,476 cache files, because the 3.3
  storage (slot 2) is not this lane's to open.
- The pattern sample on Blizzard's `D2R.exe` (encrypted).
- How D2RLoader reports the build name on other 3.3 or 3.4 builds of the game (another platform's build number). It no
  longer matters: since section 8.1 nothing compares the name.
- `Data\` of slot 1 after the runs (the game's own storage layer may fetch files).

## 8. The port for D2RLoader 1.3.1 (2026-11-12)

### 8.1 No tie to a game build: the image guard

Rule and design: docs/plugin-plan.md 1.1. Every place where a build number or a game version was compared, and what it
is now:

| Where | Before | Now |
|-|-|-|
| Core plugin, `build_guard::Matches` (the former `build_guard_logic.h`) | image stamp `0x6ab3782c` and D2RLoader's build name `93847` | `image_guard::Decide` (`plugin/src/image_guard_logic.h`): the stamp and 12 expected bytes in each of five called functions; the version and build name are logged only |
| Core plugin, the log line of the refusal | kinds by build name ("another build") | kinds by image ("another image", "the known stamp, other code at ..."), the version and build name follow as "for information, not compared" |
| Core plugin, `mxl2012` status line | "3.3" derived from the build name | D2RLoader's own version string, shown only |
| Core plugin, screen text | "needs D2R build 93847; this is ..." | "this D2RLoader version is not supported by the mod yet. The mod's engine changes are off." |
| D2R-Legacy169, `BuildMatches(stamp, buildName)` (`src/patch_table.h`) | stamp and build name `93847` | `ImageSupported(stamp)`; the build name is logged only (own repository, branch `lane/port34`) |
| drawcap | none: all places are found by signature | unchanged; the stamp only words one log line (`LoaderImage131`) |
| invtabs plugin | none | unchanged |
| Downloader, `CheckBuild` / `RequiredGameVersion` (`launcher/src/core/detect.*`) | required D2R 3.3: warned at Install, blocked Play on a known other version, sorted installs by it | `DescribeGame`: one information line with the version found; installs are sorted by "version readable" only |
| Downloader, `PlayInputs.buildMismatch` (`core/paths.*`) | blocked Play | removed; `PlayBlocked` has no version input that blocks |
| Downloader, manifest check (`core/manifest.cpp`) | a manifest without `d2r.build` and `d2r.version` was invalid; `d2r.version` was the required version | the `d2r` block is optional and information |
| `tools/game_checks.py` check `mxl2012` | status line must say "Resurrected 3.3" | any version |

Not comparisons of the running game, unchanged: `tools/install_mod.py` `D2R_BUILD` and the package's
`global/dataversionbuild.txt` (a data file the game reads; `tools/verify_package.py` checks the package holds it), and the
`d2r` block `tools/package_release.py` writes into the manifest (kept so that older downloaders still read it).

Unit tests (`plugin/tests/image_guard_test.cpp`, `imageguard_tests`): the image installs with build name 93847, 95032,
none and a made-up one; another stamp, no image, or one changed probe byte does not; a jump written over a probed
function's entry does not trip the gate; the screen text names no version, build or stamp. With `D2R_DUMP` set the test
also checks stamp and probes against the project's memory dump of the image.

### 8.2 D2RLoader's notice

- **Tools.** `tools/loader_notice.py` answers the notice of our own launch: a visible `#32770` window titled `D2RLoader`
  with exactly one button, OK, owned by one of the launch's processes, and only when `d2rloader.log` holds the
  "hasn't been fully tested yet" warning with a time stamp of this launch. It posts `TDM_CLICK_BUTTON` with `IDOK` to
  that window once per launch: no focus, no key or mouse input, no hook, and the check box stays unticked, so nothing of
  the install's `d2rloader\data\state.json` changes. `slot_share.py bootcheck` and `game_ctl.py start` poll it every
  0.5 s while they wait for the game. Unit test `tools/tests/test_loader_notice.py`. On slot 1 (3.4):
  `bootcheck-34.txt`, BOOTCHECK PASS with the line "D2RLoader's notice ... answered with OK in the background", shared
  files restored.
- **What a player sees on 3.4:** D2RLoader 1.3.1 shows its notice "This D2R version hasn't been fully tested yet" at each
  start; the player clicks OK, or ticks "Don't remind me again for D2R 3.4" once and never sees it again.

### 8.3 Downloader and release manifest

The downloader never refuses, warns or asks because of the game's version (docs/launcher.md). Its status line shows
what it found, for example `D2R: <folder> (3.4, build 95032)`; a version that cannot be read shows as such and does not
block either. The D2RLoader requirement (1.3.1) stays. The manifest keeps its `d2r` block as information
(docs/release.md); a manifest without it is valid. `launcher/tests/core_tests.cpp` covers it (Play is not blocked for
3.2, 3.3, 3.4, 3.10, 9.9 and an unreadable version); a run of the built downloader against a copy of the folder layout
with 3.4 version data showed the neutral line and no warning (`launcher-fake/status34.txt`).

**Downloaders already released** still hold the old test: they read `d2r.version` (`3.3.0`) from the manifest and block
Play on a 3.4 install until they have updated themselves to a downloader built from this change.

### 8.4 Smoke in a game (2026-11-12, HD, dev build of the branch, background only)

One package, built against the 3.3 files, installed with `install_mod.py` into slot 1 (3.4) and slot 2 (3.3). Runs with
`tools/game_checks.py all <checks>`; folders under `smoke/`.

| Run | Slot, game | Checks | Result |
|-|-|-|-|
| `a-mxl2012-devmenu-s1` | 1, D2R 3.4 | `mxl2012`, `devmenu`, new Amazon | PASS, PASS. Status line `game: Diablo II: Resurrected 3.4.0, engine changes on`, 50 lines, no part off or FAILED. The developer menu opens with Ctrl+F12; all 19 rows pass (spawns, travel, raise to 50, waypoints, quests; the panel in HD and in classic graphics) |
| `b-apple-save-reload-s1` | 1, D2R 3.4 | `apple_use`, new Barbarian | PASS, PASS (`apple_save`): Apple bought and used, state and stats as in the table; Save and Exit and back in: entered, the Apple stays used |
| `c-char-from-33-s1` | 1, D2R 3.4 | `mxl2012` with `DmFourH`, a character saved on 3.3 on 2026-11-10 (copied from slot 2's save folder into slot 1's) | PASS: the character enters a game; the game wrote its save again at exit |
| `d-mxl2012-devmenu-s2-33` | 2, D2R 3.3 | `mxl2012`, `devmenu`, new Amazon | PASS, PASS (`3.3.0, engine changes on`; Ctrl+F12 opens the menu, 19 rows pass): nothing lost on 3.3 |

In every 3.4 start `game_ctl.log` holds "D2RLoader's notice ... answered with OK in the background". The shared files
were restored after each run (`slot_share.py status`: no pending snapshot) and the locks released.

Two things seen, not looked into further:

- Run b left one D2RLoader last-resort record (`smoke/d2r-lastresort-crash-report (...).log`): a first-chance access
  violation in a module outside the game image, written at 01:50:39 when the game was closed after both checks had
  passed. The folder holds four records of the same size from earlier days. Runs a, c and d left none.
- The watchdog counted "foreground window changed 2 times" in each 3.4 run and 0 in the 3.3 run, with no cursor change.
  Most likely D2RLoader's notice takes the foreground when it opens, for under a second until it is answered. No input
  of ours goes to the foreground, but the window itself is not kept out of it.

### 8.5 Not done

- The full check suites on 3.4, and play in classic graphics beyond the developer menu panel (section 6, step 5).
- A save written on 3.4 loaded back on 3.3.
- D2R-Legacy169 in a game on 3.4: the mod bundles the pinned build, which still refuses build name 95032 and patches
  nothing there, until its branch `lane/port34` is pushed and the pin moved.
- The other-image case in a game (no other D2RLoader image is installed); it is covered by the unit test.
- The 3.4 file cache and a build against 3.4 files (step 4), the signature tool (step 6): not started.
