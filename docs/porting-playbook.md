# Porting a classic Diablo II mod to D2R: handoff playbook

For an agent starting a new port of a classic (1.13c / 1.10 era) Diablo II mod to Diablo II: Resurrected. Written
from the Median XL port (this repo, 2026-10-05 to 2026-10-14, about 55% done). It assumes the new mod has the same
shape as Median: standard D2 TXT tables (stored as `.bin`), a custom engine DLL (Median's `D2Sigma.dll`) that adds
tables and changes the game, and classic DC6/DCC art. What is generic and what is Median-specific is marked.

Read this first, then `docs/PLAN.md` (phases and status), `docs/txt-migrate.md` (data rules) and
`docs/plugin-plan.md` (engine findings) in this repo for the full detail behind each point.

## 1. Target and setup

| Item | Value used here | Note |
|---|---|---|
| Game | D2R 3.3.0, build **93847** | Every engine address below and in `plugin/src/d2r.h` is for this build only. A new build means new addresses. |
| Loader | **D2RLoader 1.3.1** (PluginSDK 0.3.0, ABI 4) | Mod folder `<game>/mods/<Mod>`, extended save format (wider stat/skill IDs), its own save folder. |
| Tables | D2R's 32,768-row limit per table | Median's largest: cubemain 7,500, missiles 5,609, monstats 3,901, skills 3,018. |
| Toolchain | Python 3.14, CMake + MSVC, git/gh, StormLib + CascLib (submodules), Ghidra 12.1.4 (headless) | Ghidra: `%USERPROFILE%\Desktop\sugma\tools\ghidra_12.1.4_PUBLIC`. Projects in `..\ghidra\` (D2R dump, the mod DLL, 1.13c D2Game). |
| Permission | Ask the mod team first | Median's team approved this port; nothing of theirs or Blizzard's is committed (`.gitignore`: `extract/`, `work/`). |

Machine paths for this port: repo `%USERPROFILE%\Desktop\sugma\mxl2012-d2r`, game `C:\Program Files (x86)\Diablo II
Resurrected`, saves `%USERPROFILE%\Saved Games\Diablo II Resurrected\mods\mxl2012`.

## 2. Phases and how the work split

| Phase | Share of work | What it is |
|---|---|---|
| 0 Setup | 2% | Repo, toolchain, loader installed, game boots |
| 1 Tools | 12% | Extract both games, decode the mod's binary tables, names, formulas, migrate to D2R's layout, strings, validator |
| 2 Data port | 10% | Install the mod folder, first boot, fix load asserts |
| 3 Triage | 8% | Sort every module of the mod's DLL into: (a) data only, (b) loader service, (c) native hook, (d) UI rebuild, (e) cut |
| 4 Plugins | 30% | Re-implement the DLL's engine changes as a D2RLoader plugin |
| 5 Graphics | 28% | HD art and HD UI (the largest open part here) |
| 6 Test and release | 10% | Saves, multiplayer, packaging |

**First milestone:** in game with a new character as early as possible (reached on day 1 here, with placeholder
graphics). Everything after that is driven by what breaks in game.

## 3. The data pipeline (Phase 1-2)

```
python tools/mpq_extract.py      # v005 patch_d2.mpq -> assets/median/ (the asset pack: tools/asset_pack.py build, docs/setup.md step 4)
python tools/casc_extract.py     # D2R baseline    -> extract/d2r/<build>/   (tables in excel/ and excel/base/)
python tools/build.py            # names, formulas, mod tables, strings, migration, art/UI steps, validation -> work/mod/
python tools/install_mod.py      # -> <game>/mods/<Mod> (folder mod, plugin DLL included)
```

`tools/build.py` rebuilds `work/` from scratch and ends with `validate.py`; aim for **0 errors**. Install only while
the game is closed; the user must fully restart D2R after an install.

**Reusable as they are:** `mpq_extract.py`, `casc_extract.py`, `tbl2json.py` (.tbl strings to D2R JSON),
`validate.py` (types every field from D2R's own data guide in `data/global/dataguide/`), `install_mod.py`,
`build.py`, `animdata_merge.py`, `item_art.py` / `ui_panels.py` (DC6 to HD sprite), `ui_layouts.py`, `save/`.
**Median-specific, adapt:** `mxl_names.py` (resolves the decoder's placeholder names), `sigma_tables.py` (D2Sigma's
37 extra tables), `formula.py` (decodes 1.13c formula bytecode; generic in principle, Median's calc codes in the
name list), the rule tables inside `txt_migrate.py`.

### Row merge rules (generic, `docs/txt-migrate.md`)
- **Indexed tables** (read by row number: skills, states, itemstatcost, missiles, monstats(2), overlay, properties,
  levels, objects, ...): row *i* = the mod's row *i*, else D2R's. D2R's own additions keep their IDs; the mod's new
  rows follow them, so **the mod's IDs get renumbered** and every reference must be remapped (`docs/id-mapping.md`).
- **Replace** (item bases, treasure classes, affixes, uniques, sets, runes, cubemain, ...): the mod's rows only.
  Merging D2R's vanilla bases back lets them drop through auto treasure classes.
- **D2R wins** (sounds, skillcalc, misscalc, playerclass, plrtype, storepage): D2R's rows first; the mod's extra
  calc codes are appended.
- **Keyed** (the rest): the mod's rows, then D2R's rows whose key the mod lacks.
- Values with no D2R column go to `work/mod/overflow/<table>.txt`; nothing is dropped silently.

### Data traps that cost real time (check all of these on a new mod)
1. **Mode codes.** 1.13c's plrmode/monmode gives Sequence (18) the code **GH** (same as Get Hit). D2R spells it
   **SQ** and Knockback **KB**. Skills' `anim`/`seqtrans` GH must become SQ (122 skills here), and the plrmode/monmode
   `Code` column must keep D2R's values, or sequence skills play knockback frames and then crash (`0x3b6700` got -1).
2. **overlay `Character`**: empty in 1.13c, but D2R uses it as the HD overlay folder. Without it there are no HD
   auras, cast effects or Whirlwind spin. Fill it from D2R's matching rows.
3. **Signed bytes decoded unsigned**: coldeffect -20 became 236 (chilled monsters ran +236% faster), spawnx/y -2 as
   254, misc spellicon -1 as 255. Compare every numeric column with D2R on shared rows to find these.
4. **32-bit -1 printed as 4294967295** in most tables. Write signed, except real unsigned fields (experience).
5. **Mixed columns**: monstats `Sk1mode..Sk8mode` hold a monmode code *or* a monseq sequence; the decoder wrote
   sequences as placeholders and 1,152 monster skills found no mode.
6. **Stop functions**: D2R pairs some do functions with stop functions (Whirlwind srvdo 76 / cltdo 45 -> stop 1).
   Copy them to mod rows that use the same do function.
7. **Blank-key rows are records** (monsounds, montype start with one); only "Expansion" rows are skipped.
8. **Formula limits**: 255 characters per formula, 32 bytes per quoted name, no bare negative literals (write
   `(0-N)`), bracket ternary branches. Shorten generated names that formulas reference.
9. **Treasure classes**: item display names inside quoted cells must go back to codes; DLL-generated classes don't
   exist in TXT.
10. **missiles**: D2R merged `LevRange` into `Range` (`Range+LevRange*lvl`).
11. **inventory.txt**: D2R has two rows per page (screen resolutions) and extra pages; set grid sizes on all
    matching rows (40 rows here for inventory 15x10, cube 15x10, stash 14x14).
12. **Engine limits D2R keeps**: more states than D2R's own sync handles (Median has 1,014, D2R sends 512 per unit;
    D2RLoader 1.3.1 syncs wide states itself, see 5.3) and
    level types beyond D2R's fixed list (automap needs a plugin).
13. **Banks**: D2R has `excel/` (RotW) and `excel/base/` (Classic/LoD); write both until you know which one the
    mod's characters load.

## 4. Strings, saves, test characters

- Strings: **start with a D2RLoader string namespace** for the mod (`docs/strings.md`, `docs/strings.md`). Split
  the mod's keys into those D2R's own files already have (group 1: the mod's text goes into `d2r:<key>` records without id in one override file, e.g. `lng/strings/<mod>/overrides.json`, one
  record per key and only for keys D2R's `strings/` files have; never copies of D2R's files, an unqualified record of a namespaced
  mod belongs to the mod's namespace; plain keys in table cells) and the rest (group 2: `<mod>:<key>` entries in
  `lng/strings/<mod>/*.json` without ids, `<mod>:<key>` in table cells, `@<mod>:<key>` in layouts). Never append the mod's
  own strings to D2R's files with new numeric ids: D2R has its own ids in the same range and they collide silently
  (bug #7). Fixed-size fields (`LevelWarp` 39, item index 31 characters) must hold the whole `namespace:key`: keep the
  keys that do not fit native with a fixed id. Plugins read text by key through the localization service. Make the
  validator check both the cells and the keys the plugin source uses before anything is booted.
- Saves (`docs/save-format.md`): v105 `.d2s`, checksum at +0xc, plus D2RLoader's `<name>.d2rl` sidecar with two
  SHA-256 hashes. **After any edit update checksum, size, both hashes**, or the character silently disappears.
  Stats ("gf") use 16-bit IDs and CSvBits widths; class skills ("if") are one byte per class skill in ID order.
  Level, stats and skill points edit fine; **never hand-build items** in the extended format (two characters were
  lost that way). Use the debug Item Spawner instead. Always back up to `mxl-manual-backups/` first.

## 5. Engine work: the plugin (Phase 3-4)

### 5.1 Triage the mod's DLL
Group its functions by the source file names in its assert strings (`..\D2Craft.cpp` etc.; Ghidra
`StringXrefs.java`). This repo's table is docs/subsystems/README.md: 109 modules, most of the networking, saves
and launcher code is **n/a** (D2R and D2RLoader do it).

### 5.2 Find the D2R twin of a vanilla function
1. Dump the running D2R image (`tools/dump_image.py`) and analyse it once (`tools/ghidra_analyze.ps1`).
2. Query headless and read-only: `powershell -ExecutionPolicy Bypass -File tools/ghidra_query.ps1 <Script>.java
   [-Project D2R|D2Sigma|D2Game] args`. Scripts in `tools/ghidra_scripts/`: Decompile, Disasm, Refs, NearRefs,
   StringXrefs, FindDisp (field offset users), FindDispRange, FieldDispatch, FindPtrTables (dispatch tables),
   FindSwitch (switch with N cases).
3. **Best lead: D2R's own assert paths.** D2R keeps file names like `D2Common\src\DataTbls\HoradricCube.cpp` and
   `D2Game\src\Player\PlrTrade.cpp`. StringXrefs on a file name, NearRefs on its descriptor, then Refs on the tiny
   assert stub, gives that file's functions. This found the cube recipe search in minutes after days of guessing.
4. Record getters: `<table>Record(index)` functions read `datatables + offset`; FindDisp on that offset lists
   every user. Record sizes differ from 1.13c (cubemain 0x148 -> 0x16c).
5. Dispatch tables (skill do functions, missile hit functions, item spells): FindPtrTables; the mod DLL's own
   table is located by its functions' asserts.
6. Put each confirmed address in `plugin/src/d2r.h` with its signature in a comment.

### 5.3 Writing hooks (D2RLoader PluginSDK)
- `InstallInlineHook` needs the **exact entry bytes**, whole instructions, at least 14 bytes, REX prefixes
  included (`40 53 ...`). Every hook checks its bytes and refuses on mismatch (build safety).
- Hook function pointer types must be `noexcept`.
- **Before patching engine code, check whether D2RLoader already hooks it** (a `jmp [rip+x]` at the function
  entry). Its D2RCore exports cover some things already, e.g. wide state sync (SendChangedWideStateStats etc.).
  Here, a self-written "states fix" fought D2RLoader's and broke monster hover and overlays (bug #22).
- Prefer data over code: many DLL features map to an existing D2R function with different TXT values (e.g.
  Median's 160 -> D2R Armageddon, 167 -> Revive). The plugin adds only what D2R lacks: new skill do functions in
  free slots, calc codes (skill formula variables), missile hit functions, item use functions, stat layers, etc.
- Generated headers (`mxl_*.h`) carry table data from the build into the plugin; check at load that the row count
  matches what D2R loaded.

### 5.4 Debugging in game
- Logs: `<game>\d2rloader\logs\d2rloader.log` (asserts after "startup complete"), `d2rloader\crashes\*.log`,
  the plugin's own log in `mods\<Mod>\d2rloader\logs\`, D2R's `blz-log.txt`. Crash dumps:
  `%LOCALAPPDATA%\CrashDumps\D2RLoader.exe.<pid>.dmp` (parse with `work/dumpstack.py`; no debugger installed).
- **Diagnosis switch**: a text file `mxl2012-core-off.txt` in the plugin folder lists features to leave out (states,
  levels, calc, skills, items, missiles, ...) plus trace words. Bisect regressions with it; build the same into a
  new plugin from day one.
- Hangs: dump the busy thread (MiniDumpWriteDump via PowerShell), map repeated RIPs to functions via `.pdata`.
- You may launch D2RLoader.exe to the menu yourself to read the install lines, then close it.

## 6. Graphics and UI (Phase 5)

- **Classic mode (G key)** reads DC6/DCC from the mod folder: ship the mod's art files D2R lacks (tiles, monsters,
  missiles, overlays, item pictures). Merge `animdata.d2` (D2R base + the mod's records).
- **HD mode** needs `.sprite` files: header `SpA1`, version 31, width, height, RGBA. Items are **98 px per cell**
  (lowend 49). Panels are **1162 x 1507** (classic 512 x 704 panels scale x 2.2695, y 2.1406). Upscaling the mod's
  DC6 bilinearly works (`item_art.py`, `ui_panels.py`). Monsters/missiles: borrow a D2R look-alike HD model
  (`gfx_placeholders.py`, `missile_hd.py`) until real art exists.
- **HD UI layouts** are JSON in `data/global/ui/layouts/*hd.json`; patch D2R's own files (`ui_layouts.py`) rather
  than writing new ones. Grids: `InventoryGridWidget` `cellCount`/`cellSize`. **Items draw at 98 px regardless of
  cellSize**, so to fit a bigger grid set cellSize 98 x 92 and a rect `"scale"` (0.6735 here) instead of shrinking
  cells. Equipment slots: keep D2R's native size, same scale, centred on the mod's slot. Measure positions from the
  mod's classic panel art and scale them.
- Panel art may contain things D2R draws elsewhere (Median's stash gold box sat where D2R's tabs go); cut and move
  them in the sprite build step (`ui_panels.py` `MOVES`).
- **HD player animations for sequence skills**: D2R's HD models pick a clip per skill ID (state machine, modeId 18 +
  skill index). Give each mod sequence skill a copy of the D2R state with the same seqnum (`hd_skill_anims.py`).

## 7. Working with this user

- They test in game in batches. After each installed change add a row to `docs/testing.md` (what, how, expected)
  and keep working; move rows to "Confirmed" when they report back. Don't stop to ask for tests.
- Install only when the game is not running. Commit and push to git as work lands.
- "start next" means continue with the next planned item; they like a short status table with a weighted total.
- They send screenshots for UI work; iterate positions from them.

## 8. Day-one checklist for a new mod

1. Get the team's permission; new private repo with the same layout (`tools/`, `plugin/`, `docs/`, ignored
   `extract/` and `work/`).
2. Install D2R + D2RLoader; note the exact build; boot vanilla through the loader.
3. Extract the mod's MPQs and D2R's CASC; list the mod's tables against D2R's (headers, row counts, limits).
4. Decode the mod's `.bin` tables to TXT; resolve names; decode formulas; list the DLL's extra tables.
5. Migrate with the rules in section 3; run the validator until 0 errors; check every trap in the list.
6. Install, boot, read `d2rloader.log`; fix load asserts; get a new character into Act 1.
7. Triage the DLL by assert file names; start the plugin with byte-checked hooks and a diagnosis switch.
8. Then work from what breaks in game, keeping `docs/bugs.md` and `docs/testing.md` current.

## 9. Where the Median port stands (if continuing it instead)

About 55% overall (PLAN.md table). In progress: **cube recipe conditions** (D2R search `0x529090` handles player
conditions 1-14 only; Median's 32-42, cubemainext's second condition and gold cost are missing; plan in
plugin-spec.md "Cube conditions, D2R side"). Open: trade window size, classic-mode panels, skill tree tab art
(bug #3), quests/ubers (largest DLL module), hirelings, NPC services, HD monster/missile art, the testing.md backlog.
