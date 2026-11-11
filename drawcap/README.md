# drawcap (Draw List Cap)

A standalone D2RLoader plugin for Diablo II: Resurrected (written on 3.3 build 93847; it finds its places by signature and
is not tied to a game build or version). It raises D2R's fixed 3000-entry legacy draw
list cap to 12000 (configurable). Big crowds and heavy on-hit procs need more than 3000 entries, and whatever does not fit is
not drawn. The patch is **on by default**. A read-only probe that measures how full the list gets is **off by default**.

It needs only D2RLoader (PluginSDK ABI 4; the DLL carries the SDK's plugin manifest resource, `src/drawcap.rc`, without
which D2RLoader rejects it as "an old alpha plugin"). It does not depend on D2R-XL 2012, the mxl2012-core plugin or its test harness.
D2R-XL 2012 ships it next to its own plugin, in the mod's `d2rloader\plugins` folder.

## What it measures

D2R still builds the 1.14d wall/unit draw list ("Wall2"): a fixed array of 3000 entries of 32 bytes inside the view struct
(`TVIEWDATA`). Seven inserters compare the index with 3000 and drop the entry when the list is full. The count keeps rising
past 3000, so the count a frame ends with is the real demand. Dropped entries are walls, units, missiles or shadows that are
not drawn that frame, with no assert and no log.

The plugin hooks the start of the list build. With the patch on (section "The cap raise") the hook stores the view's entry
buffer before the build runs. With the probe on it reads, per frame, the count (there it still holds the previous frame's
demand; the build resets it a little later), the view rectangle and the graphics mode. The probe never writes game memory and
never calls game code; every read runs under SEH, so a bad read is counted, not a crash.

## Config and switches

`d2rloader\config\drawcap.toml` (D2RLoader writes the embedded default there when it is missing). A config without a
`patch` key (0.1.0) gets the patch on at 12000:

```toml
[drawcap]
patch = true         # raise the cap to `cap`
cap = 12000          # 3001 to 100000 entries of 32 bytes (12000 = 375 KB per view)
probe = false        # true: write drawcap-stats.csv
interval_ms = 1000   # one stats line per graphics mode per interval, 250 to 60000
```

There are two test switch files. Each takes effect for one launch when it sits next to `drawcap.dll`:
- an empty `drawcap-probe.txt` turns the probe on;
- `drawcap-nopatch.txt` turns the patch off.

D2R-XL 2012's test tools create and remove them, and packaging refuses to ship them.

## Signature guard

drawcap is not tied to a game build, version or image. Nothing is hooked or patched unless every signature below matches in the loaded `.text` of the running game, exactly as
stated. Any miss turns the plugin off with the reason in the log ("signature 'X' did not match ... nothing hooked or
patched") and the game runs as without the plugin. The hook's expected bytes are the 25 bytes read at the found address, so D2RLoader also refuses the hook
when another plugin already changed them.

| Name | Signature (`??` any byte) | Rule | 93847 RVA |
|-|-|-|-|
| draw list build | `48 89 5c 24 18 48 89 74 24 20 55 57 41 54 41 56 41 57 48 8b ec 48 83 ec 60 48 8b 05 ?? ?? ?? ?? 48 33 c4 48 89 45 f8 48 8b d9 44 8b e2 8b 49 0c b8 67 66 66 66 2b 4b 04 f7 e9 8b 4b 10 b8 67 66 66 66 2b 4b 08` | exactly one match; hooked at its start (first 25 bytes) | `0x21bae0` |
| count reset | `0f 10 45 d8 33 ff 89 bb ?? ?? ?? ?? 0f 11 05 ?? ?? ?? ?? 89 7b 48` | exactly one match within 0x400 bytes after the build; its disp32 at +8 is the count offset | `0x21bc08` (count `TVIEWDATA+0x17750`) |
| HD graphics test | `48 8b 05 ?? ?? ?? ?? 48 85 c0 74 08 0f b6 80 b9 00 00 00 c3` | exactly one match; its global must lie inside the image | `0x846210` (global `0x3440170`, flag `+0xb9`) |
| cap sites | `cmp <count>, imm32` reading `[reg+0x17708]` (list-relative) or `[reg+0x17750]` (view-relative), optional REX | at least one within 0x2000 bytes after the build; all caps equal; `0x50 + cap * 32 == count offset` | 7 sites, cap 3000 |

The 93847 cap sites (the `cmp` instruction): `0x21be8f`, `0x21bf90`, `0x21c273` (REX-prefixed), `0x21c578`, `0x21c660`,
`0x21c904`, `0x21c9f5`. The log lists the sites it found and says "(the 93847 places)" when the build and the count offset
are where they are in 93847, "(moved: another build)" otherwise. A build with a bigger array still passes the guard as long
as the struct stays consistent (the cap is read from the code, not assumed).

The graphics mode is the byte the HD test returns: the panel manager's `+0xb9`, 1 in HD and 0 in legacy graphics (checked in
game against the G toggle). A null panel manager counts as `unknown`.

## Output

- **Log**: `d2rloader\logs\drawcap.log`, the plugin's own D2RLoader log (load line with the image stamp, config state, found
  addresses, each cap site, and at most one line per 10 s when a second had frames over the cap).
- **Stats**: `d2rloader\logs\drawcap-stats.csv`, new at each game start, shared for reading while the game runs. Lines
  starting with `#` are comments (the first names the version, image stamp, addresses and cap). Then:

```
t_ms,mode,frames,max,mean,over,dropped,cap,view_w,view_h,grid
```

  One line per graphics mode that drew in the interval: `t_ms` (GetTickCount64 at the flush), `frames`, the largest and the
  mean count, `over` (frames with count > cap), `dropped` (sum of count - cap over those frames: entries not drawn), the cap,
  the view size in pixels and the grid side the game derives from it (`w/160 + h/80 + 22`).
- **Console**: `drawcap` prints the status and the totals per mode.

`tools/drawcap_stats.py` in the D2R-XL 2012 repo sums a stats file up per mode.

## Install without D2R-XL 2012

1. Copy `drawcap.dll` into `<D2R>\d2rloader\plugins` (all games) or into a mod's `mods\<mod>\d2rloader\plugins`.
2. Start the game through D2RLoader. It writes `d2rloader\config\drawcap.toml` (patch on at 12000, probe off), and the cap is
   raised from that start on. `drawcap.log` lists the 14 edits, and the console command `drawcap` shows the state.
3. To measure the list, set `probe = true` (or put an empty `drawcap-probe.txt` next to the DLL) and start again. To go back
   to the game's own cap, set `patch = false`; with both off the plugin hooks nothing.

Build: `cmake -S drawcap -B build/drawcap -A x64 -DDRAWCAP_PLUGINSDK_DIR=<PluginSDK>` then
`cmake --build build/drawcap --config Release --target drawcap` (`tools/build_plugin.ps1` does it in this repo). Unit tests of
the pure part (`src/drawcap_logic.h`): target `drawcap_tests`, or `cmake -S drawcap/tests` on its own; with env `D2R_DUMP`
set to a 93847 memory dump the tests also run the scan on it.

## The cap raise

Every inserter computes its entry as `base + index * 32`, where the base is one
`lea r64, [TVIEWDATA + 0x50]` (or `[list + 8]`) a few instructions after its cap compare. The patch changes two
instructions per site, 14 in all:

- The compare's imm32 becomes the new cap (`81 fa b8 0b 00 00` becomes `81 fa e0 2e 00 00` at 12000).
- The base `lea` (`48 8d /r disp8`) becomes a `mov` with the same operands (`48 8b /r disp8`). The base is then the qword
  stored at `TVIEWDATA + 0x50`, the first 8 bytes of the old entry 0.

The build hook stores the view's own buffer (cap × 32 bytes, made once per view and kept) at `TVIEWDATA + 0x50` before each
build.

No code is added to the game, so there are no stubs and nothing has to be placed within 2 GB of the image. The rest of the
game reaches entries only through the grid cells' linked pointers (cell `+0x10`, entry `+0x18`), never by index, so entries
in the buffer are drawn exactly like entries in the struct. The code reading behind that is in the run notes (PATCH.md).

Safety:

- **Signatures.** Each site's compare comes from the scan above. Its base `lea` must follow the `jae` within 0x30 bytes,
  with the right displacement (8 for list-relative, 0x50 for view-relative) and a destination other than `rax`. A
  `shl rax, 5` must sit between the compare and the `add <dest>, rax` that uses it.
- **No partial patch.** If any site misses, nothing is patched and the log names the site. The probe can still run.
- **One transaction.** The hook and the 14 edits go into one D2RLoader `MutationService` transaction. Each edit's expected
  bytes are the bytes read at the found address, so another plugin's change there makes D2RLoader refuse the transaction.
  If the commit fails, the game code is restored.
- **Logged.** The log lists every edit (address, old bytes, new bytes).

| Site | Compare | Base lea | 93847 edit |
|-|-|-|-|
| A | `0x21be8f` | `0x21bea5` | `48 8d 59 08` to `48 8b 59 08` |
| B | `0x21bf90` | `0x21bfb3` | `48 8d 7e 08` to `48 8b 7e 08` |
| C | `0x21c273` (REX) | `0x21c293` | `48 8d 79 08` to `48 8b 79 08` |
| D | `0x21c578` | `0x21c586` | `48 8d 77 50` to `48 8b 77 50` |
| E | `0x21c660` | `0x21c66e` | same as D |
| F | `0x21c904` | `0x21c912` | same as D |
| G | `0x21c9f5` | `0x21ca03` | same as D |

The patch was tested on 2026-11-10/11 in 93847, slot 1, legacy 800x600:
- A Chaos Sanctuary crowd of Siege Beasts and zombies, on two layers of their corpses, needed up to 3,553 entries.
- With the patch off, that scene dropped up to 374 entries a frame (353,020 in one launch).
- With the patch on, it drew all of them (0 frames over the 12000 cap). A 630 s legacy soak at about 3,000 to 3,420
  entries ran without a crash or a plugin error.
- At equal entry counts, fps is the same with and without the patch.
- The patch changes nothing below 3000 entries, and nothing in HD (HD crowd fps 10.8 with it, 11.4 without; the patch does
  not change what HD draws).
