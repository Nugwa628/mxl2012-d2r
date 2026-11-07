# HD text in legacy graphics: feasibility

Lane `hdtext`, 2026-11-06, for 0.1.14. Owner request (2026-11-06): "a toggle in settings somewhere for HD text in legacy
mode, using the fonts from the HD version of the game". This is a time-boxed probe, not the feature. Evidence and the
probe code (not committed): `mxl2012-runs/hdtext/` (`probe.patch`, `run_slot.ps1`, `decomp/`, `shots/`,
`crash-*.log`). Addresses are RVAs in the 93847 dump (`D2RLoader_6ab3782c_dump.exe`, docs/d2r-addresses.md).

## 1. How D2R picks the font

- **No single switch.** The panel manager's HD flag (`0x846210`, `panelmgr+0xb9`) is asked at 197 call sites, one per
  feature.
- **Layouts:** the classic layouts name a classic DC6 font with `fontType` (`TextBoxWidget`, `ButtonWidget`; parser
  `0x8bb540`: `8pt` font8, `16pt` font16, `30pt`, `42pt`, `10ptF` fontformal10, `12ptF` fontformal12, `6pt`, `24pt`,
  `11ptF`, `10ptE` fontexocet10, `8ptE` fontexocet8, `BNet` ReallyTheLastSucker, `Chat` fontingamechat; ids 0-13, name
  table `0x1d84a00`, loader `0x90eae0` / `0x90f070`: `data/local/font/<lang>/<name>.dc6` + `.tbl`). The HD layouts use
  `style` (`fontFace` BlizzardGlobal / Exocet / Formal, `pointSize` from `_profilehd.json`; fonts in `data/hd/ui/fonts/*.ttf`,
  face names parsed at `0x8ba570`). The classic tab bar already showed that classic widgets ignore `textStyle`
  (docs/legacy-graphics.md). **Nothing in `data/` can switch classic text to a TTF font.**
- **Text facade:** `0x902990`-`0x9040a0`, 11 functions that each ask the HD flag and then pass the same arguments (text,
  rect, classic font id, flags) either to the DC6 code (`0x90dc10` layout, `0x90cea0` draw, `0x90d400`, `0x90e4b0`) or to
  the HD TrueType code (`0x907b70` draw, `0x909560` measure, `0x908890`). Draw `0x902e20`, measure `0x903cd0` /
  `0x903dd0`. So D2R already maps a classic font id to an HD style, and measuring goes through the same facade.
- The HD glyph code `0x90b370` gets its font face from a D2RCore thunk (`0x3e2b250(fontId)`, D2RLoader's own module)
  and sizes it from the style's size times a UI scale (`DAT_141d84934`).

## 2. Probe in game (slot 1, 4:3, 2026-11-06)

Harness verb `hdtext on [mask]` (probe only): the facade's HD checks return true (`mov al,1`) while legacy is on.

| Run | Sites forced | Result |
|-|-|-|
| `checks-20261106-150314-s1` | all 11 | crash on the first frame after `hdtext on`: `BC_ASSERT: result == FT_Err_Ok`, then an access violation at `0x90b627` (face pointer null, `[face+0x80]`) |
| `checks-20261106-150831-s1` | draw + 2 measures (`0x308`) | same assert, same crash address |

HD and legacy shots before the switch: `shots/hdt_43_npcname_hd.png`, `hdt_43_npcname_legacy.png`, `hdt_43_chat_*.png`.
No legacy-with-HD-text shot exists: the game crashes before a frame is drawn.
**Not run:** the 16:9 pass with the Legacy 16:9 plugin (built in this worktree, `build/legacy169`). The crash happens at the
first HD text draw, before any layout is involved, so it would only repeat the same crash.

**What this settles:** taking D2R's HD branch is not enough. In legacy, the HD text state (font faces, or their
size: UI scale) is not set up, so FreeType fails and the face is null. Coordinates/size and clipping in fixed classic
boxes could not be judged, because no frame was drawn. They stay open risks (section 4).

## 3. Where the toggle can live

- **D2R's Options menu:** no plugin API to add an entry. It would mean adding a widget to `gameplayoptionspanel*.json`
  and hooking how settings are saved. Not worth it.
- **D2RLoader input actions** (`input.h` `ActionRegistration`): the action shows up in D2R's own Controls / key-binding
  menu (category "Extensions"), and players can rebind it. Recommended for the switch: like G, a key that
  flips it in a game.
- **D2RLoader TOML config** (`ensureConfig` / `readConfig` / `writeConfig`; `mods\mxl2012\d2rloader\config\`, editable in
  D2RLoader's in-game plugin settings as legacy169 / buff-panel are): stores the choice across starts.
- **Recommendation:** a TOML value `hd_text_in_legacy` (default off), plus a rebindable action that flips it and
  writes the TOML back.

## 4. Effort and risks for the full feature

Two ways in, both in `mxl2012-core`:

- **A. Make D2R's own HD text work in legacy** (preferred: real D2R fonts, colour codes and measuring for free). First find
  what the G switch sets up for the HD text code (face cache behind `0x3e2b250`, the UI scale `DAT_141d84934`,
  `_profilehd` sizes). Keep that alive in legacy, or set it up when legacy is entered, then route the 11 facade
  checks through our own `TextIsHd()`. Also map the classic 800x600 coordinates to the HD text's coordinate space
  (unknown yet), and handle classic boxes sized for DC6 glyphs. Estimate: 3-6 lane days (RE 1-2, hook + scale 1-2,
  the surface sweep with 4:3 / 16:9 shots, tests, docs 1-2). The RE part may also show it is not possible without
  D2RLoader changes (D2RCore owns the face cache).
- **B. Draw the text ourselves:** hook the classic DC6 draw/measure (`0x90cea0` / `0x90dc10`) and draw TTF glyphs
  ourselves. D2RLoader's OverlayService draws text, but in its own font and on top of the frame (no layering
  under panels or cursor), so it does not meet "D2R's HD fonts". Using our own FreeType with D2R's `.ttf` files is a
  new text renderer (glyph atlas, `ÿc` colours, widths for wrapping): 6-10 lane days.

Risks: classic panels and tooltips sized for DC6 widths (HD glyphs are wider: clipping, overflow on Median's long item
lines); position and scale under the Legacy 16:9 plugin; `ÿc` colour codes and Median's own strings; per-frame cost of
TTF layout on busy screens (item labels); D2RLoader updates (the D2RCore thunk); any crash here hits every legacy frame,
so the switch must default off and fail safe (hook refused -> classic text).

**Recommendation:** one more RE lane (1-2 days) for A's first step: find and keep alive the HD font state in legacy, with
the probe re-run. Go or no-go after that. Only fall back to B if A is blocked.
