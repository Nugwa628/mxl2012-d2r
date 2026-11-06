# Median XL stash tabs: MEDIAN, ORBS and the Materials tab's Median page

Built by lane medtab (2026-11-06) for 0.1.14, on the owner's decisions of 2026-11-05 / 06 (option D below). The design history
(lane medstash, 2026-11-05) follows in "Earlier design".

## What ships

In a **Reign of the Warlock** game the stash has 7 tabs: **PERSONAL / SHARED / GEMS / MATERIALS / RUNES / MEDIAN / ORBS**
(HD: the full names; legacy graphics: PERSON / SHARED / GEMS / MATS / RUNES / MEDIAN / ORBS, drawn into the tab art because the
classic tab bar has room for about 6 capitals of `font6`). Every slot works like D2R's own advanced stash slots: Ctrl-click
from the backpack puts an item in, items of a code stack in their slot (count up to 99 as D2R's), a click takes one out.

| Tab | Items | Slots | Cube |
|-|-|-|-|
| MEDIAN | 23 elixirs and Goodberry, 18 signets / packs / Moon Symbol / Boom! / Signet of Skill / Apple, 14 uberquest trophies, the 20 full-charge shrines (`?0+`, 1 x 2) | 75 (95 of the 100 cells) | no |
| ORBS | the 100 Mystic Orbs (`&01`-`&95`, `&a1`-`&a5`) | 100 | no |
| MATERIALS, Vanilla page | D2R's page unchanged (its 23 codes) | 23 | yes |
| MATERIALS, Median page | 10 oils and catalysts, 6 arcane crystals and shards, 13 cube reagents (5 brains, Sacrificial Heart, Meditation Candle, 5 sigils, "I Am Rich" / Poser!) | 29 | yes |

The Materials tab has a **Vanilla / Median** selector (arrows on the left ornament under the plinth band); Ctrl-click routes by
code, so a D2R material Ctrl-clicked while the Median page shows goes into its Vanilla slot (and the reverse). Not in the tabs
(owner): used shrines (the 180 part-charged codes stay ordinary items in the grid pages), the Buyable Mystic Orbs, the Pearls of
Wisdom, the emblems. The code lists are `tools/median_tabs.py` (`SINGLES`, `SHRINES`, `ORBS`, `MAT_MEDIAN`).

**Classic and expansion games** (no RotW stash): tabs 6 and 7 are hidden as D2R hides Gems / Materials / Runes there, so the stash
is Personal + Shared, as before. With a gamepad the stash stays D2R's (its controller layout has no Median slots; stacks put in
with mouse and keyboard stay in the save). The "Send storable/stackable items to stash" button sends the new codes too.

## How it is built

- `tools/median_tabs.py apply work/mod/data` (a `tools/build.py` step after `rotw_stash_legacy.py`): both stash layouts
  (`bankexpansionlayouthd.json`, classic `bankexpansionlayout.json`) get 7 tabs (HD 139 x 72 each, the 195-pixel tab art
  re-sliced; classic 44 x 24 with the names in `rotwstash_tabs.dc6`), the MEDIAN and ORBS slots as direct children of
  `advancedstash_runes`, the Median Materials slots as direct children of `advancedstash_materials` (D2R takes a page's accepted
  codes from its direct children only), the page pictures and the two selectors as panel siblings (a non-slot child of a page
  crashes the stash init), and the art (stone pages with a recess per slot, made from D2R's Materials page).
- `tools/d2r_adds.py` (`step_advanced_stash`) sets `AdvancedStashStackable` 1 on the 204 codes; `median_tabs.py apply` stops
  when one lacks it.
- The plugin part **medtab** (`plugin/src/median_tabs.cpp`, docs/plugin-plan.md section 33) runs tabs 6 and 7 as the Runes page
  (D2R's panel knows 5 pages), shows the slot group of the active tab and of the selector, hides the cube on MEDIAN / ORBS, and
  hides tabs 6 and 7 outside RotW. `medtab_names.h` (its widget names) is written by `py -3 tools/median_tabs.py header`.

## The 9 codes with "@"

Goodberry `b@b`, Moon Symbol `c@c`, Signet of Skill `!@B`, the five sigils `l@l m@m o@o p@p q@q` and Poser! `u@v` asserted
(`m_itemCode.size() <= 4`, AdvancedStashSlotWidget) in the probe. Cause: D2R's layout loader reads `@key` anywhere in a string as
a string key (D2R's own layouts have `"@minipanelHelp@minipanelspecial"`), so `"b@b"` became "b" plus the key's text, longer
than 4 characters; the code read `0x2ce910` asserts on that. JSON offers no escape for it (`@` is the same character after
parsing). So **no data change**: the layouts write the codes with `_` (`b_b`, `!_B`, ...; no item code of the mod has `_`, a test
checks it), slot names too, and the plugin hooks `0x2ce910` and puts the `@` back into the widget's own string (inline buffer,
3 characters) before D2R reads it. The items keep their codes, so saves, cube recipes, quests and drops are untouched; nothing
has to be converted.

## Plugin and layout

The 7-tab layouts need the medtab part: without it tab 6 asserts (blz array index 5) and the game crashes, and the `_` codes
name no item. So:

- `tools/install_mod.py` (`write_mod_files`, which `tools/package_release.py` uses too) refuses a mod whose stash layouts have
  the Median tabs with no plugin or with a plugin without the part (the DLL must name the layout mark `medtab_sel_vanilla`).
  The plugin is mod-scoped (in `mods\mxl2012\d2rloader\plugins`), so a release always carries the pair.
- The plugin with an older or D2R layout (no `medtab_sel_vanilla` in the panel) leaves the stash as D2R: 5 tabs, nothing shown
  or hidden; the getter cap stays harmless (tabs 0-4 only).
- The off word `medtab` keeps the hooks (the layout needs them) and hides tabs 6 and 7 in every game, with D2R's Materials
  page only.
- On another D2R build (`build_guard`) or different bytes at the hooked sites the part installs nothing; that game is not
  93847, which the mod does not run on anyway.

## Saves

The stacks are kept where D2R keeps all advanced stash stacks: the kind-1 page of `ModernSharedStashSoftCoreV2.d2i` (shared by
the RotW characters). No new page, no new file; the Personal and Shared pages are unchanged, and a 0.1.13 stash loads as it was.
**One-way (#545):** a build whose misc rows lack `AdvancedStashStackable` for a code deletes that code's stacks on load. So
going back to 0.1.13 or older after putting items in the new slots deletes those stacks, and no later build may drop a code
from these lists.

## Earlier design (lane medstash, 2026-11-05)

Kept for the record. What shipped is option A grown into own tabs: lane medtab found how to add tabs 6 and 7 (with the plugin),
which this design had left open ("a 4th advanced page ... unknown"). The mock-ups and probe results are in
`mxl2012-runs/medtab/index.md` (outside git).

Owner request (2026-11-05): Median's runes and gems go into the RotW stash's Runes / Gems pages (done, see
[stacking-research.md](stacking-research.md) section 4); **everything else to collect gets its own "Median XL" stash tab**:
shrines, the other Median potions and elixirs, signets and similar consumables. Design first: how such a tab can exist in
every game type, whether it can stack, shrines, how it is saved, and what happens without the plugin (bug #537's rule: the
character must not load, so nothing is lost). This note is the design; nothing of it is built (section 5).

### 1. What the items are

From [stacking-research.md](stacking-research.md) section 2 (Median's `misc.txt`):

| Group | Codes | Notes |
|-|-|-|
| Shrines | 200 (20 kinds x 10 charge levels, `A0+`-`A9+` ...) | the charge count is the code; 5,600 cube rows turn `B0+` into `B1+` |
| Elixirs, Goodberry | 22 | useable, belt items |
| Signets, packs, icons | 18 `poti` rows | useable |
| Affix crystals | 170 `&01` ... | cube only |
| Oils, catalysts | 10 `0o^`-`9o^` | cube only |
| Arcane crystals | 4 | no cube row |

About 420 codes. Every one is `compactsave` 1 (a simple item, no quantity outside the RotW tab).

### 2. What D2R 3.3 and D2RLoader 1.3.1 offer

| Mechanism | Game types | Stacks | Saved in | Without the plugin | Room |
|-|-|-|-|-|-|
| RotW advanced stash page (`AdvancedStashSlotWidget` + `AdvancedStashStackable`) | RotW only | yes, 8-bit count per code (docs/save-format.md) | `ModernSharedStashSoftCoreV2.d2i`, kind-1 page, shared by all RotW characters | data only: works without the plugin | one slot per code; a page holds at most ~57 slots at D2R's 98-pixel pitch (9 columns is also the classic page's limit) |
| A 4th advanced page (new tab next to Gems / Materials / Runes) | RotW only | as above | as above | as above | **unknown**: the five tabs and their page kinds are D2R code; the layout alone has not been shown to add a page (not tried) |
| D2RLoader custom player page (`registerPlayerPage`) | all | no (a plain grid) | `<char>.d2rl`, item page 6 | the character does not load (D2RCore stops it, the `.d2s` is unchanged): #537's rule holds | **exactly one per mod, already used by personal page 2** (`stash2`, 10 x 10 of a possible 16 x 16) |
| D2RLoader shared tabs (`add_shared_tabs`) | all | no | the shared `.d2i` | data only | 10 x 10 pages; D2R draws them as "Shared" pages, no own name |
| Plugin-held virtual stash (the plugin keeps counts in its own file, items leave the game) | all | yes (counts) | a file of the plugin | **items invisible, and lost if the character is saved meanwhile**: breaks #537's rule unless tied to the `.d2rl` | any |

### 3. Options

| # | Option | Gives | Effort | Risks |
|-|-|-|-|-|
| A | **More RotW slots**: put the stackable groups on the Materials page (its free stone, like the Runes / Gems pages here) or a 4th page if D2R allows one | stacks, no plugin code, old saves unchanged (codes are stored as text) | S-M for the Materials page (this lane's tooling: `tools/median_stash.py`), M-L for a 4th page (find the tab -> page code in D2R.exe first) | RotW only (classic / expansion get nothing: the owner's "every game type" is not met); the Materials page holds D2R's 23 codes (some 1 x 2) and, redrawn like the Runes page, about 30 more, not ~420: elixirs (22) or oils + arcane crystals (14) fit, shrines and affix crystals do not |
| B | **Personal page 2 grows into "Median XL"**: the one D2RLoader page becomes 16 x 16 (its maximum) and is titled for Median's collectibles | a page in every game type; #537's no-plugin rule already holds | S-M (`stash_pages.cpp` grid size, layout and art; lane stashp2fix owns that file now) | no stacking (one cell per item); it is the owner's page 2, not a new tab: the personal stash stays at 2 pages |
| C | **Plugin "Median stash" page on top of page 2's sidecar**: page 2 keeps its grid, and the plugin stores per-code counts for the collectibles inside the same protected page (a hidden 16 x 16 area beyond the 10 x 10 the player sees, one cell per code, count in a stat) | stacks in every game type, #537's rule holds (same `.d2rl` page) | **L**: server-side item create / destroy on deposit / withdraw (D2R 3.3 addresses to find), a new panel, save tests | item loss or duplication bugs in the deposit / withdraw path; 256 cells cannot hold ~420 codes (shrines by kind only); a D2RLoader update that changes the page format breaks it |
| D | **SDK request**: ask D2RLoader for more than one custom player page (or a page with stacks) | a real second tab, drawn and saved by D2RLoader | small for us, depends on D2RLoader | not in our hands; no date |

### 4. Shrines

Keep **one item per charge level**, as Median 2012 does. Each of the 200 codes is its own recipe input and output, so a
stack per code would be correct, but 200 slots fit on no page. Proposal: whichever tab is built takes the 20 full shrines
(charge 10, `?0+`, the ones that drop) as stacks or cells; used shrines stay in the normal stash. Turning charges into a
stack count is the "shrines by charge" redesign of stacking-research.md (a cube hook and a save converter): an owner call,
not part of this tab.

### 5. Recommendation and status

No option is both every-game-type and stacking without a large plugin project (C) or D2RLoader help (D). So this lane
**stops after the design** (the brief's rule: build only if clearly safe and small).

- Quick and safe, RotW only: **A** on the Materials page for elixirs (22) and oils / arcane crystals (14), with the tooling
  of the Runes / Gems pages. Needs the owner's yes to RotW-only.
- Every game type: **D** first (ask D2RLoader for a second player page); until then **B** (page 2 to 16 x 16, no stacks) after
  lane stashp2fix is merged.
- C only if the owner wants stacks in classic / expansion games and accepts an L-sized plugin part with its save risks.

Questions for the owner: (1) RotW-only acceptable for the collectibles (option A)? (2) Page 2 as the "Median XL" page (B),
or keep page 2 as a plain personal page and wait for D? (3) Shrines: only the 20 full ones in the tab, as proposed?
