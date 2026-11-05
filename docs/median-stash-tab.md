# A "Median XL" stash tab: design (lane medstash, 2026-11-05)

Owner request (2026-11-05): Median's runes and gems go into the RotW stash's Runes / Gems pages (done, see
[stacking-research.md](stacking-research.md) section 4); **everything else to collect gets its own "Median XL" stash tab**:
shrines, the other Median potions and elixirs, signets and similar consumables. Design first: how such a tab can exist in
every game type, whether it can stack, shrines, how it is saved, and what happens without the plugin (bug #537's rule: the
character must not load, so nothing is lost). This note is the design; nothing of it is built (section 5).

## 1. What the items are

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

## 2. What D2R 3.3 and D2RLoader 1.3.1 offer

| Mechanism | Game types | Stacks | Saved in | Without the plugin | Room |
|-|-|-|-|-|-|
| RotW advanced stash page (`AdvancedStashSlotWidget` + `AdvancedStashStackable`) | RotW only | yes, 8-bit count per code (docs/save-format.md) | `ModernSharedStashSoftCoreV2.d2i`, kind-1 page, shared by all RotW characters | data only: works without the plugin | one slot per code; a page holds at most ~57 slots at D2R's 98-pixel pitch (9 columns is also the classic page's limit) |
| A 4th advanced page (new tab next to Gems / Materials / Runes) | RotW only | as above | as above | as above | **unknown**: the five tabs and their page kinds are D2R code; the layout alone has not been shown to add a page (not tried) |
| D2RLoader custom player page (`registerPlayerPage`) | all | no (a plain grid) | `<char>.d2rl`, item page 6 | the character does not load (D2RCore stops it, the `.d2s` is unchanged): #537's rule holds | **exactly one per mod, already used by personal page 2** (`stash2`, 10 x 10 of a possible 16 x 16) |
| D2RLoader shared tabs (`add_shared_tabs`) | all | no | the shared `.d2i` | data only | 10 x 10 pages; D2R draws them as "Shared" pages, no own name |
| Plugin-held virtual stash (the plugin keeps counts in its own file, items leave the game) | all | yes (counts) | a file of the plugin | **items invisible, and lost if the character is saved meanwhile**: breaks #537's rule unless tied to the `.d2rl` | any |

## 3. Options

| # | Option | Gives | Effort | Risks |
|-|-|-|-|-|
| A | **More RotW slots**: put the stackable groups on the Materials page (its free stone, like the Runes / Gems pages here) or a 4th page if D2R allows one | stacks, no plugin code, old saves unchanged (codes are stored as text) | S-M for the Materials page (this lane's tooling: `tools/median_stash.py`), M-L for a 4th page (find the tab -> page code in D2R.exe first) | RotW only (classic / expansion get nothing: the owner's "every game type" is not met); the Materials page holds D2R's 23 codes (some 1 x 2) and, redrawn like the Runes page, about 30 more, not ~420: elixirs (22) or oils + arcane crystals (14) fit, shrines and affix crystals do not |
| B | **Personal page 2 grows into "Median XL"**: the one D2RLoader page becomes 16 x 16 (its maximum) and is titled for Median's collectibles | a page in every game type; #537's no-plugin rule already holds | S-M (`stash_pages.cpp` grid size, layout and art; lane stashp2fix owns that file now) | no stacking (one cell per item); it is the owner's page 2, not a new tab: the personal stash stays at 2 pages |
| C | **Plugin "Median stash" page on top of page 2's sidecar**: page 2 keeps its grid, and the plugin stores per-code counts for the collectibles inside the same protected page (a hidden 16 x 16 area beyond the 10 x 10 the player sees, one cell per code, count in a stat) | stacks in every game type, #537's rule holds (same `.d2rl` page) | **L**: server-side item create / destroy on deposit / withdraw (D2R 3.3 addresses to find), a new panel, save tests | item loss or duplication bugs in the deposit / withdraw path; 256 cells cannot hold ~420 codes (shrines by kind only); a D2RLoader update that changes the page format breaks it |
| D | **SDK request**: ask D2RLoader for more than one custom player page (or a page with stacks) | a real second tab, drawn and saved by D2RLoader | small for us, depends on D2RLoader | not in our hands; no date |

## 4. Shrines

Keep **one item per charge level**, as Median 2012 does. Each of the 200 codes is its own recipe input and output, so a
stack per code would be correct, but 200 slots fit on no page. Proposal: whichever tab is built takes the 20 full shrines
(charge 10, `?0+`, the ones that drop) as stacks or cells; used shrines stay in the normal stash. Turning charges into a
stack count is the "shrines by charge" redesign of stacking-research.md (a cube hook and a save converter): an owner call,
not part of this tab.

## 5. Recommendation and status

No option is both every-game-type and stacking without a large plugin project (C) or D2RLoader help (D). So this lane
**stops after the design** (the brief's rule: build only if clearly safe and small).

- Quick and safe, RotW only: **A** on the Materials page for elixirs (22) and oils / arcane crystals (14), with the tooling
  of the Runes / Gems pages. Needs the owner's yes to RotW-only.
- Every game type: **D** first (ask D2RLoader for a second player page); until then **B** (page 2 to 16 x 16, no stacks) after
  lane stashp2fix is merged.
- C only if the owner wants stacks in classic / expansion games and accepts an L-sized plugin part with its save risks.

Questions for the owner: (1) RotW-only acceptable for the collectibles (option A)? (2) Page 2 as the "Median XL" page (B),
or keep page 2 as a plain personal page and wait for D? (3) Shrines: only the 20 full ones in the tab, as proposed?
