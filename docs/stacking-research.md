# Stackable Median items: research (0.1.12)

Owner question (2026-11-05): can Median's shrines, the new runes, the new potions (experience, greed, ...) and similar
consumables be made stackable? Research only, no change to the mod. Sources: Median's own tables
(`work/named/misc.txt`, `cubemain.txt`, `itemtypes.txt`), D2R 3.3's misc.txt (`work/d2r-baseline`), the save codec
(`tools/d2save.py`, [save-format.md](save-format.md)), a RotW shared stash written on slot 2, and the 1.14d engine
(Redivivus, Game.exe; D2R 3.3 shares this code but was not disassembled for this note). No game run.

**Short answer:** not by data alone. Turning `stackable` on for these rows is a one-cell change, but the engine then
treats a stack as ONE item everywhere that matters for Median: using a stacked elixir eats the whole stack, the cube
counts a stack as one input and consumes all of it, and the save format stores no count for these items today. The
workable routes are the RotW stash tab (storage only, runes / gems style) or a plugin part.

## 1. How D2R 3.3 stacks items

### misc.txt columns

| Column | Effect |
|-|-|
| `stackable` | 1 = the item carries a quantity (the `quantity` stat, 9 bits in the save). Right-click on a stack in hand merges / splits (packets 0x21 / 0x22, `SCMD_0x21_MergeStackables` `0x54b300`) |
| `minstack` / `maxstack` | range of a stack; `maxstack` caps merges (`ITEM_GetMaxStack` `0x6295b0`) |
| `spawnstack` | quantity of a newly dropped / bought item (`ITEM_InitItemBaseStats`) |
| itemtypes `AutoStack` | a picked-up item merges onto a stack of the same code in the inventory (`ITEMMODE_AutoStackItem` `0x55d0d0`); Median sets it on no type |
| `AdvancedStashStackable` (D2R 3.x only) | the item may go into the RotW Gems / Materials / Runes tab, which stacks it there whatever `stackable` says |

What D2R itself makes `stackable` 1: gold, arrows / bolts, keys (`maxstack` 12), tomes (20), throwing weapons and the
unused red / blue "stack" potions `rps` `rpl` `bps` `bpl` (5-10). Runes, gems, rejuvenation potions, Token of
Absolution, keys / organs / essences / shards and the Colossal materials are `stackable` **0** with
`AdvancedStashStackable` **1**: D2R stacks them only inside the RotW tab, and an item taken out of the tab is a single
item again. Median's tables keep `stackable` for tomes (100), arrows / bolts (500), sacred arrows / bolts, keys (50),
gold and the four red / blue stack potions. **No Median-only row is stackable** (868 misc rows).

### The RotW advanced stash tab (bug #510)

- One fixed `AdvancedStashSlotWidget` per item code in D2R's `bankexpansionlayouthd.json` (91 codes: 33 runes, 35 gems
  and skulls, 2 rejuvs, Token, keys, organs, essences, shards, Colossal materials); the slot recesses are painted into
  the page pictures ([legacy-graphics.md](legacy-graphics.md) section 9). A code without a widget cannot go in.
- It takes an item only when its row has `AdvancedStashStackable` 1. Our build copies D2R's flag onto the 71 Median rows
  with D2R's code and type (`tools/d2r_adds.py` `advanced_stash`); Median's runes r34-r56 have no widget and no flag.
- The tab is RotW only (the pages live in `ModernSharedStashSoftCoreV2.d2i`, kind-1 page: [save-format.md](save-format.md)).
  Players without RotW have no tab, so it cannot be the only answer.
- The stack count in the tab: the slot-2 RotW stash (`mxl2012-runs/stashhdr/backup0`) has a kind-1 page with 13 items,
  all with the simple-item flag and ~26 bytes each, in a form `d2save.py` cannot read yet (it misreads from the first
  item; `mxl2012-runs/stackres/rotw_tab_items.txt`). Where D2R keeps the count of a tab stack is **not decoded**. Next
  step if this route is picked: a RotW save with 1 Ith, then 2 Ith, in the tab, and diff the page.

### Use, split, cube (1.14d engine, Redivivus)

| Action | What the engine does with a stack |
|-|-|
| Right-click use (`SERVER_UseItemAtCoords` `0x562390`) | runs the item spell once, then `ITEMMODE_ConsumeItemAndRemove` (`0x561e70`) **deletes the whole item**: no quantity decrement. Tomes have their own path (`ITEMMODE_UpdateBookSkillQuantity`); keys are not used through this function |
| Cube input (`CUBE_MatchInputDescriptorToCubeItems` `0x565010`) | counts **items, not quantity**: a stack of 40 El is one match. With a stackable item present the test becomes "matched >= qty" instead of "== qty", and every matched item (the whole stack) is consumed on transmute |
| Show | the tooltip shows the quantity (`INV_FormatQuantityText`); how D2R HD draws it on a Median item is not checked |
| Belt | a belt cell holds one item; nothing in the belt code decrements a quantity |
| Vendors | price scales with quantity / `maxstack` (`ITEMS_CalcTransactionCost`); buying merges onto an existing stack (`SUNITNPC_FindExistingStackInInventory`) |

### The save format

- The 9-bit `quantity` is written only in the **extended** part of an item, and only when the code's row is `stackable`
  1 at load time (`tools/d2save.py` `_item_layout`: `if code in c.t.stackable`).
- Every candidate row is `compactsave` 1 (shrines, runes, gems, elixirs, signets, crystals, oils, arcane crystals: 563
  rows). Compact items are saved as **simple items** (flag 0x200000): code, guid, one socket bit, nothing else. A
  simple item has no quantity field, so a stack of a compact code cannot be saved; the count is lost on Save and Exit.
- So pure data needs `stackable` 1 **and** `compactsave` 0. The simple flag is stored per item, so items saved before
  the change still load as simple items (the reader follows the item's own flag, not the table). They would come back
  without a quantity stat: whether D2R then gives them 0, `minstack` or 1 is **not verified** (a quantity-0 item is
  the risk: some code paths delete or refuse it). New items would be extended items with the quantity.
- The other direction is the breaking one: making a stackable row non-stackable later misreads every saved item of that
  code and every item after it (the 9 bits are still in the file), the same failure as #536's `BadHeader`. A stacking
  change is therefore one-way; once shipped it cannot be removed without a save converter.

## 2. The candidate groups

| Group | Rows | Type, use | Median behaviour that depends on single items | Data-only stacking |
|-|-|-|-|-|
| Shrines | 200: 20 kinds (Creepy, Abandoned, Quiet, ... Divine) x 10 codes (`A0+`-`A9+`, `B0+`-`B9+`, ...), one code per charge count (10 .. 1) | `thng`, not useable, cube only | 5,600 cube rows: shrine + item -> item modified, **output b = the same shrine with one charge less** (`B0+` -> `B1+`). The charge count IS the code | Breaks the recipe: a stack of `B0+` is one input, the whole stack is consumed and one `B1+` comes back. Stacking only works for codes with the same charges, and the cube must take one from the stack |
| New runes | 23: `r34`-`r56` (Sha .. Sha'ad). Median 2012 has **no Great Runes** (those are Median XL Sigma) | `rune`, socketable | 69 cube rows, 46 with `qty=2` / `qty=4` (upgrades r34 x2 -> r35 ...) | Breaks upgrades (a stack = 1 input, all consumed) and socketing a stacked rune is undefined (the socket code expects one unit) |
| Classic runes, gems | 33 + 60 | `rune`, `gem*` | 197 + 125 cube rows, most with `qty=2` / `qty=4` | Same as new runes; already stack in the RotW tab |
| Elixirs | 22: `ey2`-`ey9`, `et1`, `eo7`-`ey1`, `0g0`-`0g8`, Goodberry `b@b` | `hpot`, useable, `belt` 1 / `autobelt` 1, item spells 9 / 6 | no cube use | Right-click eats the whole stack (one effect). Belt: one cell, one item. Also #541 (elixirs auto-belting onto potions) |
| Signets, packs | 18 `poti` rows: Signets of Gold / Experience / Learning / Skill (and Greater / Buyable), Life / Mana Pack, Moon Icon, Apple, Bling Bling | useable, item spell 3 / 10 | `c@c` has one cube row | Same as elixirs: whole stack used at once |
| Affix crystals | 170 `asaa` (`&01` ...) | not useable, cube only | 1,055 cube rows (`useitem` + crystal) | Whole stack consumed per recipe |
| Oils, catalysts | 10 (`0o^`-`9o^`) | not useable, cube only | 795 cube rows | Whole stack consumed per recipe |
| Arcane crystals | 4 (`qus` `qut` `qux` `quy`) | not useable | no cube row in the named table | Safe in the cube sense; still the compact-save problem |

D2Sigma: Median XL 2012 v005 does not use D2Sigma (that is Sigma's engine). The 2012 consumables use vanilla item
spells (misc `pSpell` 3, 6, 9, 10) and cube rows, and our own plugin; nothing in a Median DLL expects single items
beyond what the cube and use paths above already do.

## 3. Options, ranked

| # | Option | What it gives | Risks | Effort |
|-|-|-|-|-|
| 1 | **RotW tab for Median's runes (and maybe crystals / oils)**: `AdvancedStashStackable` 1 on `r34`-`r56` plus 23 new slot widgets in `bankexpansionlayouthd.json` (and the classic layout), new page art for the slots | runes stack in storage like D2R's; taken out they are single items, so cube, sockets and saves stay as they are | RotW players only; page art for 23 more slots (the Runes page has 33 painted recesses, no room: a second page or a redrawn page); whether D2R reads widget codes it does not know from the layout alone is untested; the tab's count format is not decoded | medium: layout + art, then a RotW game check on slot 2 |
| 2 | **Plugin part "stack consumables"**: keep the rows `compactsave` 0 / `stackable` 1 for chosen groups, and hook the two paths: use (decrement by one instead of deleting, `SERVER_UseItemAtCoords` -> `ITEMMODE_ConsumeItemAndRemove`) and cube (count quantity per input, take only `qty` from a stack and give the rest back) | real stacks in inventory and stash for elixirs, signets, crystals, oils; works without RotW | the largest change: server-side item code in D2R 3.3 (addresses to find; 1.14d gives the shape), trade / vendor / belt paths to check, old saves (simple items of those codes, see section 1) need a test, and the change is one-way | high: plugin work + save tests + game checks |
| 3 | **Pure data** (`stackable` 1, `compactsave` 0, `maxstack`) | stacks in the inventory | each use eats the whole stack, the cube consumes whole stacks and miscounts, shrines lose their charge chain; one-way save change | low effort, **not shippable** for any group that is used or cubed (all of them except arcane crystals) |
| - | **Shrines by charge** (redesign: one code per shrine kind, the quantity as its charges) | 20 codes instead of 200 | needs option 2's cube hook (take a charge, not the item) and a converter for the 200 saved shrine codes | high; a Median design change, owner call |

Recommendation: for 0.1.12 none of this is a quick data change. If storage is the goal, option 1 for the new runes is
the safe one (no save or recipe change), RotW only. If the goal is fewer inventory cells for elixirs / signets /
crystals / oils on every account, it is option 2, a plugin project of its own; shrines stay single items unless the
owner wants the charge redesign.

## 4. Follow-up: Median's runes and gems in the RotW tab (owner 2026-11-05, lane medstash)

The owner picked option 1 for Median's new runes **and** gems; the rest gets a "Median XL" tab of its own, designed in
[median-stash-tab.md](median-stash-tab.md). Answered on slot 2 (docs/testing.md "Lane medstash"):

- **The tab's count:** a tab stack is a simple item whose bit after the guid is 1, followed by an **8-bit count** (LSB first;
  1, 2, 4 Ith diffed; the padding of 16 records rules out 7 bits). An item withdrawn from the tab keeps the bit with count 0.
  `tools/d2save.py` reads and writes it (`stack`); docs/save-format.md. The item code is stored as text, so new codes need
  no save change, and old saves (Median runes / gems as plain items) load unchanged.
- **New codes from the layout alone:** yes. A widget with a code D2R does not know plus the misc flag is enough: Ctrl-click
  deposit, stacking and the count work like D2R's own codes. No plugin code.
- **Built:** `tools/median_stash.py`: `AdvancedStashStackable` 1 on the 48 codes (r34-r56; Rainbow Stone `yo1`-`yo5`, Onyx
  `g$`, Bloodstone `9$`, Turquoise `7$`, Amber `5$`), the Runes page with 56 slots and the Gems page with 12 families
  (60 slots), both pages redrawn from D2R's Materials page, HD and classic. The gamepad layout keeps D2R's console art and
  slots (no Median codes with a gamepad).

## Open questions for the owner

1. Is the goal storage (the stash tab is enough) or carrying stacks in the inventory (plugin)?
2. RotW-only for the runes tab acceptable?
3. Shrines: keep one item per charge (as Median 2012), or redesign as stacks of charges?

## Not verified (needs a game run on slot 2)

- How D2R 3.3 loads an old simple item whose row became `stackable` 1 / `compactsave` 0 (quantity 0, 1 or `minstack`).
- That D2R 3.3's use and cube paths match 1.14d's (`0x562390`, `0x565010`); D2R's binary was not read for this note.
