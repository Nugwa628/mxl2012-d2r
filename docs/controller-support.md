# Controller (gamepad) support

State of the mod's gamepad support and the plan for 0.1.17 (lane padui, 2026-11-07, research; scripted pad input: lane padinput). Evidence:
`mxl2012-runs/padui/` (`REPORT.md`, `run1-panels/`, `run2-native/`, `controller-qol/`), `mxl2012-runs/padinput/`.

## 1. Seeing the gamepad UI without a gamepad

D2R picks its UI by the last input device. No `Settings.json` key or launch argument forces it (the `Controller ...`
keys are cursor speed, rumble, stick swap and weapon-swap bindings only). The switch in D2R 3.3 build 93847:

| What | RVA | Notes |
|-|-|-|
| RequestInputMethod thunk `(int device)` | `0x847630` | `mov edx, ecx; mov rcx, [PanelManager]`, then `0x8a5440`; called from the input paths (`0x13b4ab`, `0x13edd0`, `0x13f470`, `0x6508f0`) |
| PanelManager::RequestInputMethod `(pm, device)` | `0x8a5440` | device 1 = gamepad, 0 = mouse / keys; on a change sets `pm+0xdc` = device and `pm+0xdb` = pending, posts `InputMethodChanged` |
| PanelManager singleton | `0x3440170` | |
| PanelManager update | `0x8a40c0` | pending: `0x8a690(pm+0xdc == 1)`, then reloads every panel (profile table `0x8a15b0`: `Layouts/_profileHD.json` or `Layouts/Controller/_profileHD.json`) |
| SetControllerMode `(bool)` | `0x8a690` | writes the byte via `0x77e40`, resets the cursor state |
| "Gamepad UI on" getter / byte | `0x77e10` / `0x2a23274` | `0x77e10` = console build (`0x2a210a0+0xdc8`, getter `0x77d80`) or the byte; 448 callers |

**Test switch (dev builds only):** harness verb `h padui on | off` (plugin/src/harness_cmds.cpp). It hooks `0x8a5440`
(pass-through until a verb asks) and while forced turns every request into 1, so background keys and the virtual mouse
no longer switch back; `on` also asks for the gamepad UI at once. The release DLL has no harness, so players never get it.
Checks `padui` and `padui2` (tools/padui_checks.py) take the shots.

What it can and cannot show:

- The gamepad HUD, layouts and panels: yes, in HD and in legacy graphics (the gamepad UI stays HD over the legacy world).
- Keys (I, C, T) do nothing while the gamepad UI is on; panels open through D2R's own UI message
  (`stashpage uia PanelManager OpenPanel <name>`), the stash through the stash object. Mouse clicks still land (stash tabs).
- Gamepad navigation (focus moves, LB / RB / LT / RT paging, A / X / Y actions, item tooltips by focus) needs gamepad
  events: the scripted gamepad below (`h pad`) gives them.

## 1a. Scripted gamepad input (`h pad`, dev builds only)

Lane padinput, 2026-11-07. D2R 3.3 build 93847 reads Xbox-style pads only through `XInputGetState` of `XINPUT9_1_0.dll`
(no Windows.Gaming.Input, no GameInput, no DirectInput; PlayStation pads go their own way, `0x1312c20`):

| What | RVA | Notes |
|-|-|-|
| Import `XINPUT9_1_0!XInputGetState` / `XInputSetState` | IAT `0x1cb1258` / `0x1cb1260` | thunks `0x130cbab` / `0x130cbb1`; one caller each |
| OsControllerUpdate | `0x1210940` | slots 0-3 at `0x35620d0` (`0x30` bytes: `+0` connected, `+4` XINPUT_STATE, `+0x18` previous wButtons, `+0x28` last poll); a connected slot is read every update, a free one every 4 s |
| Controller events | `0x1210050` | calls `0x1210940`, then turns wButtons changes into the UI's button down / up events |

The harness verb `pad` (plugin/src/harness_cmds.cpp, pure part plugin/src/pad_input_logic.h) swaps that IAT entry for its
own function on the first verb that changes the pad and puts the original back on `pad off`. Until then nothing is
hooked; slots 1-3 and a real pad's other slots go to XInput unchanged. No driver, no install: only D2R's own import in the
game process. The release DLL (`build_plugin.ps1 -Release`, `MXL_RELEASE`) has no harness, so none of this: its DLL has
none of the verb's strings (`pad on=`, `XINPUT9_1_0`), the dev DLL has them.

```
h pad on                       connect the scripted pad (slot 0); the game sees it within 4 s
h pad press a [ms]             down for ms (default 120) and at least 3 polls; lb+a joins buttons
h pad hold lb / release [lb]   down until released; `release` alone also centres sticks and triggers
h pad stick L|R <x> <y>        percent, -100..100, y up
h pad trigger L|R <0-255>      (lt / rt as buttons = 255)
h pad off                      disconnect, import back
h pad                          status: on hooked polls packet buttons ... gamepadUi device
```

Buttons: `a b x y lb rb lt rt ls rs start back up down left right` (aliases `menu view l3 r3 dup ...`). Scripts for checks:
tools/pad_input.py (`run_script(H, "start wait:1 right a a rb")`, also a command line for a running game). Checks:
`padprobe` (MXL_PAD_PROBE script with `shot:<name>` words) and `padinput` (tools/padinput_checks.py).

What the pad does in D2R's gamepad UI (HD, slot 1, `mxl2012-runs/padinput/run3-final/`):

| Input | Result | Shot |
|-|-|-|
| A pad button (Start), no `padui` | the UI switches to the gamepad UI by itself (`gamepadUi` 0 -> 1, device 1); the left stick alone does not switch it | `padin_start_menu.png` |
| Start | opens the panel menu on Inventory (Quest Log, Character, Inventory, Skill Tree, Options; LB / RB legends); B closes it | `padin_inv_open.png` |
| D-pad | moves the focus; the focused item shows its tooltip (Minor Healing Potion on the belt) | `padin_inv_right2.png` |
| A, A | picks the focused item up (legend "A Place X Drop") and puts it back | `padin_inv_a_pick.png`, `padin_inv_a_put.png` |
| RB / LB | next / previous panel of the menu (Skill Tree with Median's tab names, Character) | `padin_inv_rb1.png`, `padin_inv_lb2.png` |
| RT / LT (stash open) | next / previous stash tab: Personal, Shared, Gems, Materials, Runes (no MEDIAN / ORBS, #557) | `padin_stash_rt1.png` ... `padin_stash_lt3.png` |
| RB / LB (Shared tab) | shared page 1/7 -> 2/7 -> 1/7 | `padin_stash_rb1.png` |
| D-pad down (stash open) | focus into the backpack: Horadric Cube tooltip | `padin_stash_down1.png` |

The first RT onto the gamepad stash's Gems tab gave #548's assert burst (no crash), see docs/bugs.md.

## 2. The mod's panels in the gamepad UI (HD, `MedStashA`, slot 2)

The mod overrides 2 of D2R's 83 gamepad layout files (`controller/horadriccubelayouthd.json`, `controller/bankexpansionlayouthd.json`).
The character sheet and skill tree layouts are `basedOn` the PC files and follow the mod; the inventory is D2R's own.
The table is lane padui's state; #556 and #557 are fixed since (section 5).

| Screen | Result | Shot |
|-|-|-|
| HUD | gamepad HUD, life / mana orbs, belt; skill buttons A / X / B / Y / RB / RT empty ("?") for a character with no bindings | `run1-panels/padui_hd_pad_town.png` |
| Inventory | **broken (#556, fixed: section 5)**: D2R's 4-row gamepad frame, Median's last two rows and right column drawn outside it over the gold field; no Send to stash button | `run2-native/padui2_playerinventoryexpansionlayout.png` |
| Stash | **incomplete (#557, fixed: section 5)**: Personal, Shared, Gems, Materials, Runes; no MEDIAN / ORBS; the backpack beside it is partly hidden under the stash panel; the stash cube (10 x 8) is right | `run1-panels/padui_hd_pad_stash*.png` |
| Cube | right: Median's 10 x 8 grid, transmute button, "Y Transmute" legend; the inventory beside it has the #556 overflow | `run2-native/padui2_horadriccubelayout.png` |
| Character sheet | draws (D2R's gamepad sheet with the mod's values) | `run2-native/padui2_characterstatspanel.png` |
| Skill tree | draws, Median's tab names (Special / Rage, Stances / Spirits, Throw / Melee, General Skills), **but on D2R's vanilla tree art** (empty sockets, arrows to nothing): fixed by lane wltree, section 8 | `run2-native/padui2_skillstreepanel.png` |
| Tooltips | a mouse hover does not show them in the gamepad UI; gamepad focus (`h pad`, section 1a) does: belt potion, Horadric Cube | `run2-native/padui2_tooltip_hp1.png`; padinput `run3-final/padin_inv_right2.png` |
| Plugin parts | medtab: tabs missing (#557); stashtip / tabflash: work on the MEDIAN / ORBS slots, so nothing to show; send_stash: no button (#556); buff HUD, legacy 16:9: not seen in the gamepad UI shots | |

## 3. PyreFly's controller-qol

Source: github.com/Pyre-Flies/D2R-Mods `plugins/controller-qol`, commit `df44457e5cfddf9149bc2f623ea5ab1b251e75bf`
(2026-10-30, version 1.3.1+rev.79-beta.2), kept read-only in `mxl2012-runs/padui/controller-qol`.

- **Version gate passes.** Its only file check is D2RCore.dll's SHA-256 `2A868D01...FDEB5A2`, which is ours (slots 1 and 2).
  "D2R 3.3.93787" in COMPATIBILITY.txt is a stale label: its byte checks are 93847 addresses (`0x846210`, cube
  Transmute `0x2cd720`, pickup `0x471950`, `0x4fdb40`, `0x15f8b0` match this repo's notes). A failed byte check turns
  that feature off and logs "declined"; nothing crashes. A second Core hash gates only its ControllerManager bridge.
- **Input:** D2R's own controller events (hooks `0x13edd0`, `0x13def0`), XInput as fallback; only the modifier can be
  a key. None of it is testable with background keys.
- **Conflicts with our plugin** (as found by lane padui; both resolved in lane cqol, section 7):
  - medtab's patch at `0x23af9f` lay inside controller-qol's 128-byte check of the tab getter `0x23af50`, so its
    shared-stash paging, shared-page route and native identify turned off. Its materials code checks only 32 bytes, stayed
    on, and read MEDIAN / ORBS as Runes (tab 4). medtab now leaves the getter as D2R has it.
  - Our Auto Belt Refill build hooks `0x15f660`; controller-qol accepts that only from the upstream DLL's hash, so its
    belt actions turn off. We ship them off by a config switch (`belt_actions = false`).
  - Found in lane cqol: spiritsound's hook of `0x1a0780` (D2R's client sound play) failed controller-qol's 33-byte check, so
    every Deposit All was refused; patch 0003 checks the bytes after the hooked prologue. tabflash's hook of `0x15ef70`
    makes controller-qol's own tab-flash feedback after Deposit All turn off (one warning line a session; the deposit is
    unaffected and tabflash flashes Ctrl-click deposits as before).
  - Same paths without byte overlap: pickup redirects, cube_dupe.
  - No overlap: rotwstash, stashtip, lvlup_ui, send_stash, whirlwind, legacy16:9, buff HUD.
- **Mod data:** skill profiles are keyed by numeric skill id per mod folder (`<scope>.overrides.toml`, ids read from
  the mod's skills.txt). The shipped defaults use vanilla ids and would land on the wrong Median skills; caps of 1024
  skills and 64 KB per profile file. Item codes hard-coded: runes r01-r33, gems g*, potions hp* / mp* / rvs / rvl,
  tomes and scrolls, cube `box`. Stash: tabs 2 / 3 / 4 = Gems / Materials / Runes by stock widget names.
- **Build:** CMake 3.29, C++20, two MASM files; expects a monorepo (`third_party/D2RLoader-PluginSDK`, `../inventory-deposit`);
  last SDK pin noted `bb0b48e`, ours `717f727` (needs a compile check).

## 4. Plan for 0.1.17

| Order | Lane | Work | State |
|-|-|-|-|
| 1 | padlayout | Mod gamepad inventory layouts (expansion + original) sized for Median's backpack, the Send to stash button (#556); MEDIAN / ORBS in the gamepad stash (#557, medtab for the controller layout) | done (section 6); the focus graph and LT / RT into MEDIAN / ORBS tested with `h pad` in lane cqol (section 7) |
| 2 | padinput | Test-only `XInputGetState` hook in the dev plugin: scripted pad buttons, sticks and triggers | done (section 1a) |
| 3 | cqvendor | Vendor controller-qol (PyreFly's source pinned, built by our tools, packaged and pinned like the other bundled plugins; credit PyreFly) | done (section 7) |
| 4 | cqcompat | medtab coexistence (our patch moved out of the tab getter's checked 128 bytes), tabs 5 / 6 known as MEDIAN / ORBS, belt shortcuts shipped off | done (section 7) |
| 5 | cqprofile | mxl2012 skill profile from Median's skills (lane padskills' generator, section 5), seeded at build time | done (section 7); the item-code ranking changes of section 5's table are still open |
| 6 | cqlive | Live test with a real gamepad by a person (slot rules: background input only, so the owner or a player) | open: what scripted input cannot show is listed in section 7 |

## 5. Lane padskills: generated skill seed (2026-11-07, static)

`tools/controller_skill_profile.py` reads the **final built** `skills.txt` and `skilldesc.txt`.
Run after `tools/build.py` (or `--data-only` for static work):

```powershell
py -3 tools/controller_skill_profile.py --out work/controller-skills
```

It stages `mxl2012.overrides.toml` and `mxl2012.skills.json` (IDs, internal labels, inferred kind,
settings, override reasons and source SHA-256). The latter is an audit catalog, not plugin input.
This lane's data-only build produces **818 entries, 32,873 bytes**, within upstream's 1024-entry
union and 65,535-byte read limit. Maximum numeric ID is not the capacity limit.
No game was started; these are suggestions awaiting controller validation.

### Profile grammar and loading (upstream df44457)

Source authority: `src/aim/skill_settings.h`, `skill_catalog.h`, `skill_discovery_policy.h`,
`skill_discovery.cpp`, `skill_profile_policy.h`, and release `skill-defaults.toml` in the padui reference.
Shared aim controls (stick deadzone, reticle, cursor speed, colors, logging) stay in the main TOML;
only the following skill sections belong in the overrides file:

| Section / value | Meaning |
|-|-|
| `[aim.amazon]`, `.sorceress`, `.necromancer`, `.barbarian`, `.paladin`, `.druid`, `.assassin`, `.warlock` | Numeric IDs from the compiled vanilla catalog; class labels organize IDs, they do not restrict the character using the skill. Use the catalog section even if Median assigns another class. |
| `[aim.custom]` | Numeric IDs 1..65534 absent from the compiled catalog. Cannot put a vanilla catalog ID here. |
| `true` | Enable right-stick routing using the entry's targeting mode. |
| `false` | Native behavior, but R3 may toggle aim. |
| `"disabled"` | Native behavior, locked against R3. Used for passives/inactive/absent rows. |
| `"ground"` / `"snap"` in `.custom` | Also enables aim and chooses targeting; class sections accept only bool or `"disabled"`. Generator uses bool plus `.targeting` for both. |
| `[aim.targeting]` | Per-ID `"ground"` = point at stick reticle, no monster snap; `"snap"` = snap selection/retention around the reticle and coordinate routing. Refines an existing ID, does not enable it. |
| `[aim.leading]` | Per-ID predicted target motion, milliseconds per tile, integer 0..200; 0 disables prediction. |
| `[aim.leading_max_ms]` | Per-ID prediction cap, integer 100..1500; default 600. |
| `[aim.leading_max_tiles]` | Per-ID spatial prediction cap, integer 1..8; default 3. |
| `[aim.whirlwind]` `whirlwind_pass_through_enabled` | Boolean for upstream vanilla Whirlwind routing. Seed sets false to avoid unintended behavior on replacement IDs. |
| `whirlwind_pass_through_distance` | Distance past target, finite number 0..15; default 1.5. |

Leading is explicitly set to 0 for every entry, canceling inherited vanilla tuning; the shipped
ID 39/45 limit exceptions are reset to 600 ms / 3 tiles. This is deliberate: server missile travel speed is insufficient to infer delay for
multi-stage, accelerating and spawned Median missiles. Duplicate IDs, unknown aim sections and invalid
values reject the profile; tuning an absent entry also fails. Reference defaults seed missing values;
R3 writes the active overrides file, manual edits require restart (or the plugin's reload facility).

**Installation scope:** the actual file is `d2rloader/config/controller-qol-skills/<scope>.overrides.toml`,
where scope is 64-bit FNV-1a over UTF-8 `lowercase(canonical_mod_root_with_forward_slashes + "|mxl2012")`
(ASCII lowercasing, basis 14695981039346656037). It is **not** named after the mod. Pass
`--mod-root <installation_mod_directory>` to stage the correctly named file, or use the file whose
`# Mod:` line identifies mxl2012 after first launch. Do not install to a scope calculated from the
worktree. Seed only missing profiles; never replace a player's R3 choices on update/repair.
Packaging/scope discovery remains work for the vendor lane; no live configuration was changed here.

### Inference and hand corrections

Precedence: passive/inactive -> aura -> explicit corpse/item/pet/ally target -> melee -> movement
(`warp`, srvdofunc 27/76) -> summon/pettype -> self nova (22/68) -> known self-buff functions with
aurastate -> ground-placed area/trap functions (28/31/80) or lob -> server missile/ranged weapon ->
skilldesc missile -> target-state area -> native pending review. Melee and explicit unit targeting
keep native selection; summons and movement use ground; projectile/hostile area use snap.
A state or missile column by itself does not establish semantics: melee procs must not become aimed spells.

`tools/data/controller_skill_overrides.json` keys eight corrections by unique **internal skill name**,
so renumbering follows the built table and missing/ambiguous names stop generation. Moonbeam, Balefire
and Wychwind have offensive missiles despite buff states; Broadside and Fortress are automatic buffs;
Nova Shot and Supernova are self-centered despite missile columns; Spin To Win is movement at ID 27.
`tools/data/controller_qol_catalog.json` records only the pinned upstream ID-to-section mapping (240
entries); refresh it against `skill_catalog.h` if the vendored plugin changes. Every catalog entry is
explicitly replaced, including hidden/absent skills, so enabled vanilla defaults cannot leak through.
Every described built skill above ID 5 is covered, including oskills, monster descriptions and shared-icon
copies. IDs 0..5 retain native engine semantics. This intentionally favors complete data coverage over
pretending every described row is player-castable. The JSON catalog exposes all uncertain/native rows.

Upstream still has special numeric policies: Telekinesis 43 is a native-unit route (this build's row is
hidden and locked off); Whirlwind 151 has special pass-through logic (off here); discovery/general
selection excludes engine actions 357..364 and 370 (Interact, Loot, TownPortal, EmoteWheel, SwapWeapons,
Map, ShowItems, RunToggle, CubeLoot, all kept native here). New automatic IDs need runtime table/UI
confirmation. A TOML file cannot change those policies; the compatibility lane must review them if IDs
or meanings change. No claim of gamepad playability follows from this static classification.

### Hard-coded item rules: actual behavior and required fork changes

Audited `src/plugin_main.cpp` (`GetPotionType`, `GetItemCodeRank`), `belt_policy.h`,
`materials_policy.h`, `materials_actions.cpp`, `identify_action.h`, `identify_bulk.h`,
`vendor_policy.h`, `client_transfer.cpp`, `cube_controls.cpp`, `cube_shortcut_policy.h`,
`client_loot_policy.h`. These are code rules, separate from skill TOML.

| Codes / rule | Median result | Change needed in our copy |
|-|-|-|
| hp*, mp*, rv*; exact rvs/rvl in belt/materials | **Already accepts** Median hpo/mpo/hpf/mpf as well as hp1..5/mp1..5. Prefix matching is not limited to vanilla tiers. rvs/rvl remain correct. | Keep families; use built misc belt/use eligibility for any added consumables. Do not blindly add every elixir to auto-refill. |
| vps/wms/yps, tsc/isc | Utility potions and scrolls retain codes. GetPotionType compares four-byte space-padded strings, belt policy uses MakeItemCode. | Normalize padding consistently; retain utility/scroll handling. Potion effect fixes are separate (#191/#104). |
| Missing belt items | hrb, eo7..9, ey1..9, et1, 0g0..8, b@b (Goodberry), c@c (Moon Icon), dog (Apple) have belt=1 but fail BeltCandidate. Several have pSpell=0 deliberately, others have use restrictions. | Table-derived allowlist, native can-use/can-belt as final authority; preserve no-op/refused items and special uses. Never treat these all as health/mana. |
| Rune ranking: r[0-3][0-9] | Comment says r01..r33 but code actually includes r00..r39; Sha through Nas (r34..39) rank as high runes, Ath through Sha'ad (r40..56) fall back to gear. | Rank via rune itemtype + full built rune list r01..56, not first digits. |
| Gem ranking: g + s/p/f/c, sk* | Omits flawless gl* even in vanilla; misses Rainbow yo1..5, Bloodstone 9$a..e, Turquoise 7$a..e, Amber 5$a..e. | Derive from gems.txt/code and itemtypes ancestry, including Median Onyx and all tiers; do not use a broad g* prefix. |
| cm*, jew; rin/amu | Vanilla charm/jewel and jewelry rankings apply; Median special charm codes outside cm* fall back to gear. cm1..3 rows even have Median type hpot, so code/name assumptions are unsafe. | Use itemtypes ancestry and explicit Median charm intent rather than cm prefix. Keep jewelry codes where unchanged. |
| pk*, tes | Keys/token rank; source comment mentions ceh/bet/fed but the code does not check them. Median respec token is toa, so it gets gear rank. | Explicit built quest/material/token categories; include toa deliberately rather than copying stale comments. |
| tsc/isc -> tbk/ibk; ibk/isc identify | Same books/scrolls in Median; native quantity/identify checks still needed. | No code remap. Keep quantity limits and native admission, review stack sizes from tables. |
| box | Correct Horadric Cube identity for open/transfer. Recipes include oils, signets, shrines, trophies, Mystic Orbs and reagents under arbitrary codes. | Keep box; use native transmute/transfer checks, never infer cube ingredients from vanilla material prefixes. |
| key, aqv, cqv, gld | Skeleton Key, arrows, bolts, gold retain codes; gold also has numeric padded/NUL checks. | Keep code identities; normalize encoding. These rankings do not describe all Median ingredients. |
| Advanced tabs 2/3/4, widget names advancedstash_gems/materials/runes | MEDIAN/ORBS are tabs 5/6 and share rune widget children. Wrong page routing/visibility risks moving the wrong stack. WidgetName only permits lowercase ASCII/digits. | Route by medtab group + visible page, honor Materials selector. Use median_tabs.py's 204-code set: 55 singles + 20 shrines + 100 orbs + 29 materials. Accept exact three-byte codes including &, $, ^, +, uppercase and @; resolve layout placeholders through medtab's real_code mapping. No unrestricted string sanitization. |

The 204-code set includes elixirs/signets/trophies, full shrines A0+..T0+, oils 0o^..9o^,
arcane qus/qut/qux/quy/qul/qum, reagents, Mystic Orbs (&01 etc.) and nine @ codes. Exact lists and
placeholder policy already live in `tools/median_tabs.py`; reuse them rather than maintaining another
partial list. These fork changes are recommendations for cqcompat, not modifications to the read-only source.

## 6. The mod's gamepad inventory and stash (lane padlayout, #556 / #557)

`tools/pad_ui.py build` (a step of tools/build.py after tools/median_tabs.py) writes three gamepad layouts from D2R's own
files and the mod's finished PC layouts, plus their art in `hd/global/ui/panel/mxl/`:

- `controller/playerinventoryoriginallayouthd.json`, `controller/playerinventoryexpansionlayouthd.json`: the cause of #556
  was inheritance. D2R's gamepad files are `basedOn` the PC files and took the mod's PC grid scale (1.0745) and cell size
  (98 x 94). They now set their own grid: 10 x 6, cell 98, scale 0.921. It sits on D2R's gamepad art with the grid grown
  from 4 to 6 rows (`padinventory`, `padinventory_classic`), so the backpack ends inside the 1411-high frame that the stash
  and cube draw round it. D2R's gold plate is dropped. The gold button sits in the stone right of the belt row, and the three
  Send to stash buttons (tools/send_stash.py, `sendstash_pad`) sit left of it. The plugin part `send_stash` finds them by
  name, as in the PC layouts. Focus links: gloves, then send, then grid; boots, then gold, then grid. A derived layout draws
  only the children it names, so the expansion file names the send buttons too.
- `controller/bankexpansionlayouthd.json`: the cause of #557 was that medtab changed only the PC layout. The gamepad stash
  now has the PC layout's seven tabs (`medtab_tabs_pad`, 153 wide in D2R's 1075 row, text 22 pt). Every slot, picture and
  the Median materials selector of the PC Gems / Materials / Runes pages is moved by (+66, -72); D2R's gamepad pages are
  its PC pages without the outer frame. The page backgrounds (`padstash_gems`, `_consumables`, `_runes`) are D2R's gamepad
  pages with the PC page's inside pasted at (+68, -172). The plugin part `medtab` finds its widgets by name, so it drives
  this panel without a change.

Tested in game (slot 2, `MedStashA`, harness `padui on`, panels opened by `OpenPanel`, tabs by mouse clicks; shots in
`mxl2012-runs/padlayout/evidence/shots/`):

| Screen | HD | Legacy 4:3 | Legacy 16:9 (legacy169) |
|-|-|-|-|
| Inventory | 10 x 6 inside the frame, send and gold buttons drawn | no frame art on the standalone panel; the same with D2R's own art (D2R draws no gamepad inventory background in legacy) | as 4:3 |
| Stash, 7 tabs | every tab opens by a click and shows its page (Median elixirs / signets / trophies / shrines, Orbs, Gems, Mats with the selector, Runes); full backpack beside it | same | same |
| Cube | right, full backpack beside it | not shot | not shot |
| PC UI (gamepad off) | unchanged | unchanged | unchanged |

Still to test with pad input (harness `pad` verb from lane padinput, not on main yet):

- the focus graph: the stick from the gloves to the send buttons, from the boots to gold, and from both into the grid;
  focus on the greyed (`MxlSendStashNoSlots`) and hidden button states;
- LT / RT paging through all seven tabs, especially into MEDIAN (5) and ORBS (6) and back;
- A on the send button (moves the backpack to the stash), and tooltips by focus on the MEDIAN / ORBS slots;
- the stick moving from the stash page to the backpack and back with the shifted page slots.

## 7. Lane cqol: controller-qol shipped with the mod (2026-11-08, slot 2, background input)

What ships (docs/bundled-plugins.md has the packaging): PyreFly's controller-qol at `df44457` (still the newest commit on
2026-11-08) with three patches (`third_party/controller-qol-mxl2012/`): `belt_actions` (shipped false), tabs 5 / 6 as
MEDIAN / ORBS, and the check of `0x1a0780` past spiritsound's hook. medtab no longer patches the tab getter `0x23af50`: a
14-byte stub at `0x23afd2` caps its 21 direct callers at Runes, so controller-qol's 128-byte check passes and it reads the
real tab. The skill seed of section 5 is embedded as the plugin's skill defaults, so each install writes its own profile on
the first start and only adds missing keys afterwards (a player edit survived a restart, run C).

In game with the dev harness `pad` verb, check `cqol` (tools/cqol_checks.py), `MedStashA`, HD and legacy:

| What | Result |
|-|-|
| Load | all features admitted, none declined (shared paging, native identify, native input); "Potion shortcuts off"; profile seeded |
| Ground loot | hold LB shows the labels, LB + A picks the item up |
| Stash paging | RT through all seven tabs incl. MEDIAN (5) and ORBS (6), LT back and past Personal to ORBS; the same in legacy |
| Deposit All (LB + L3) | Gems, Materials, MEDIAN, ORBS: every made item stashed (HD; ORBS also legacy); Runes: 1 of 2 in each run ("Batch partially unconfirmed; no retry", upstream's 1 s check), a second press moves the rest |
| Inventory focus | gloves to Send to stash to the grid, boots to gold to the grid (shots); A on Send to stash empties the backpack |
| LB + X / A / Y on a backpack item | not shown: the scripted D-pad left the focus on the gloves slot (the plugin logs "Advanced focus unresolved") |
| Mouse and keyboard | unchanged: the mouse-driven checks (medtab, stashtip, tabflash, mxl2012) gave the same results with the plugin as without |

Found on the way:

- **Same-poll combos.** D2R sends each pad button as its own event, so LB + L3 pressed in one poll can reach the game with
  L3 first: D2R's own L3 (Open Cube) ran and the deposit was dropped. Players hold LB first; the check does too.
- **tabflash vs. controller-qol's stash feedback:** our hook of `0x15ef70` makes controller-qol turn its tab flash after
  Deposit All off (one warning a session); the deposit is unaffected.
- **#558:** `Inventory.cpp:2035` / `2036` asserts when the stash is opened by a click with controller-qol loaded (open).
- #548's burst at RT onto Gems shows with or without controller-qol (known).

Needs a real gamepad (lane cqlive): LB + X / A / Y on focused items, right-stick aiming on Median skills (R3 toggles in the
skill tree), the Runes deposit with real timing, and whether #558 shows outside the harness.

## 8. Lane wltree: the gamepad UI's skill trees (2026-11-10)

D2R's gamepad skill tree draws each tab from `Controller/Panel/Spells/V2/<xx>SkillTree` (3 frames, transparent but for the tab
strip and the engraved socket + level box of every vanilla cell, with vanilla's arrows) over the shared stone
`CenterPanelBG_SkillTrees`. The mod shipped none, so for all seven Median classes the icons (columns 1 and 3, rows 1-5) sat on
vanilla's sockets: 12-14 empty sockets per class (column 2 and row 6), arrows into empty sockets, some icons on cells vanilla
has none (seen in game on slot 2, Sorceress, and lane padui's Barbarian shot). The Warlock is right: its cells are D2R's own.

`tools/pad_skill_trees.py` (an `hd_ui.py build` step) writes `data/hd/global/ui/controller/panel/spells/v2/<xx>skilltree.sprite`
and `.lowend.sprite` for am so ne pa ba dr as: D2R's tab strip of each frame, D2R's own socket (cut from its Sorceress art) on
every cell of the page that holds a skill, at the offset D2R's art uses round a button, and D2R's arrow head on every chain link
(`skill_tree_art.page_arrows`, the links the HD and classic pages draw). No layout change: the controller layout already names
these files. Its check (sockets on skills only and placed like D2R's, an arrow on every link and on no other gap) reports 357
problems on D2R's own files and none on the built ones. Tests: `tools/tests/test_warlock_tree.py` (`PadSkillTreeTests`).

