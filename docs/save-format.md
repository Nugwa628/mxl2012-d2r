# Save format of D2R-XL 2012 (D2R 3.3 v105, D2RLoader extended mode)

What a Median XL 2012 character is saved as, where the fields come from and what was checked (lane savefmt, 2026-10-28). The mod
runs D2RLoader's **extended** save mode (`[d2rcore.save_format] mode = "extended"`, written by tools/install_mod.py), which takes
the stat widths from the mod's itemstatcost.txt and widens several item fields beyond retail 3.3. The item layout below was read
from game-written saves (35 characters of slots 2 and 3, the shared stash and the 5 characters of the lane's game batches) and is implemented by `tools/d2save.py`; every one of
those saves re-encodes byte for byte.

Tools:

| Tool | What it does |
|---|---|
| `py -3 tools/d2save.py show <file.d2s\|.d2i>` | header, character stats, skills, every item (player, corpse, mercenary, golem; socketed items under their parent) with its stats |
| `py -3 tools/d2save.py roundtrip <files>` | parse and re-encode; exit 1 when a file does not come back byte-identical (a wrong field width shifts all later bits) |
| `py -3 tools/d2save.py diff <before> <after>` | lost / new / changed items, stats, skills between two saves (or two `snapshot` JSON files); item ids and positions are not content |
| `py -3 tools/d2save.py sidecar <file.d2s>` | the D2RLoader sidecar against the save (body hash, checksum, size, save hash) |
| `py -3 tools/save_audit.py` | static check of the built tables against the save widths (below); exit 1 on an error |

Unit tests: `tools/tests/test_d2save.py` (synthetic items, saves, stash pages, sidecars and tables). The older `tools/save/d2item.py`
and `d2s_stats.py` read retail widths and 9-bit character stat ids; they do not parse this port's saves.

Always back up a save before touching it and never edit one while the game runs. Hand-built items are still not recommended
(characters can be lost that way); with the widths below a hand-built item can at least be checked with `d2save.py roundtrip`
before the game sees it.

## Files

| File | Content |
|---|---|
| `<name>.d2s` | the character (below) |
| `<name>.d2rl` | D2RLoader sidecar: `D2RL`, u16 version 2, u16 header size 0x2c, u32 body length at +0x08, SHA-256 of the body at +0x0c. The body (from +0x2c) holds the save's checksum at +0x34, its size at +0x38, a SHA-256 of the whole `.d2s` at +0x3c, then the game build (`3.3.0`, `93847`), the mod (`mxl2012`, its description and version) and the plugin list (`mxl2012-core`). After an edit all four values must follow, or the character disappears from character select. Items are not in the sidecar. |
| `SharedStashSoftCoreV2.d2i` | shared stash: pages of a 64-byte header (0xaa55aa55, u32 flags, u32 version 0x69, u32 gold, u32 page size, 44 bytes) followed by a `JM` item list; D2RLoader's extra shared tabs (`add_shared_tabs`) are more pages of the same shape |
| `.key`, `.ctl`, `.ma*`, `.map` | key bindings, controller layout, automap: no character data |

## Character file (`.d2s`)

Header: signature 0xaa55aa55, version field at +4 (`05 00 52 44`, i.e. 5 and `RD`, in every extended save seen; retail writes 0x69), file size at +8, checksum at +0xc (rotate left by one, add each byte, with the
checksum field zeroed), class at +0x18, level at +0x1b, name at +0x12b. Then the sections, in this order:

| Section | Layout | Median XL 2012 needs | Fits |
|---|---|---|---|
| `Woo!` quests | D2R's record, 3 difficulties | the vanilla quest records (Median's uberquests are items and states, not quest slots) | yes |
| `WS` waypoints | 3 x 24 bytes, 112 bits used per difficulty | levels.txt `Waypoint` up to 38 (vanilla numbers) | yes |
| `w4` NPC flags | unchanged | unchanged | yes |
| `gf` character stats | 16-bit stat id, CSvParam bits, CSvBits value, ... 0xffff | see "Character stats" | yes |
| `if` skills | one byte (hard points) per class skill, in skill-id order | 30 skills per class (all eight classes), skills.txt `maxlvl` up to 99 | yes (30 bytes, values up to 255) |
| `JM` items | u16 count, then the items (socketed items follow their parent and are not counted) | below | yes, with the extended widths |
| `JM` corpse | u16 count (0 or 1); a corpse is 12 bytes (u32 0, u32 x, u32 y) and its own `JM` list | as D2 | yes (FixBarb / FixAma hold one and round-trip) |
| `jf` mercenary | `JM` list of the mercenary's items when one is hired, nothing otherwise | mercenary gear uses the item layout | see the game check |
| `kf` golem | one byte (1 = an Iron Golem item follows) and the item | as D2 | yes |

### Character stats

CSvBits are Median's own (the build does not change them; only `modifierlist_skill`'s Send Bits differ from Median). The widths
against what a character can reach (`py -3 tools/save_audit.py`):

| Stat | CSvBits | Holds | Needed |
|---|---|---|---|
| strength / energy / dexterity / vitality | 12 | 4,095 | base + 5 per level up to level 120 |
| statpts (unused) | 11 | 2,047 | 610 (5 x 119 + 15 from quests) |
| newskills (unused) | 8 | 255 | 131 (119 + 12 from quests) |
| hitpoints / mana / stamina (and max) | 21 (value << 8) | 8,191 points | base life of a level 120 Barbarian with all points in vitality is about 5,500 |
| level | 7 | 127 | MaxLvl 120 |
| experience | 32 | 4,294,967,295 | 666,666,666 (level 120) |
| gold / goldbank | 25 | 33,554,431 | 1,200,000 carried (10,000 per level) / 2,500,000 (D2R stash) |
| potion_stat_cap / potion_skill_cap (Median's elixir caps, ids 370 / 371) | 12 / 8 | 4,095 / 255 | |

A value above CSvBits is saturated by D2RLoader on Save and Exit (measured for statpts / newskills); none of the
reachable totals comes near.

## Items

Bit-packed, least significant bit first. Fields marked **ext** differ from retail D2R 3.3 and were read from game-written items.

| Field | Bits | Notes |
|---|---|---|
| flags | 32 | 0x10 identified, 0x800 socketed, 0x2000 new, 0x10000 ear, 0x20000 starter, 0x200000 simple, 0x400000 ethereal, 0x1000000 personalized, 0x4000000 runeword; saved items carry 0x80000 and 0x800000 |
| (3.3) | 8 | 5 on every item |
| version, location, equip slot, x, y, page | 3, 3, 4, 4, 4, 3 | location 0 stored, 1 equipped, 2 belt, 4 cursor, 6 socket; page 1 inventory, 4 cube, 5 stash. x / y are 4 bits: the 10 x 6 inventory, 10 x 8 cube and 10 x 10 stash fit |
| code | Huffman, 4 characters | D2R's tree; **ext**: a character the tree lacks is the free leaf `000101111` (the escape) followed by its path in a second prefix-free tree, `d2save.EXT_CODES`, solved from a cube holding one item per character (each path is pinned by what follows it: a known character, or the space and the next field). Paths in reading order: `!` 10101100, `$` 10011000, `&` 0000011, `+` 11111011, `-` 11110010, `@` 11000101, `^` 11110100, `A` 01011100, `B` 11001110, `C` 11011001, `D` 10011111, `E` 01111000, `F` 10011100, `G` 10101011, `H` 10111001, `I` 10111100, `J` 0000111, `K` 10100100, `L` 10010010, `M` 11011011, `N` 0000010, `O` 11101011, `P` 10100111, `Q` 01100100, `R` 11100111, `S` 01101010, `T` 10001010. These are all the characters Median's 2,430 codes use |
| simple item | 1 + 128, 1 | unique-id flag + id, one socket bit; ends the item |
| sockets filled | 3 | |
| item id, item level, quality | 32, 7, 4 | quality 1 low, 2 normal, 3 superior, 4 magic, 5 set, 6 rare, 7 unique, 8 crafted. D2R's own writer clamps the item level to 99 (bug #251); with the plugin part `ilvl` (lane ilvl) the field keeps 1-127 and nothing above 127 is written. D2R's reader takes the whole 7-bit range, so saves of either kind load |
| picture | 1 + 3 | |
| class-specific affix | 1 + 16 | |
| low / superior | 3 | |
| magic | **ext** 16 + 16 | prefix, suffix (retail 11 + 11); Median 747 / 959 rows |
| set | **ext** 16 | setitems row (retail 12); Median 300 rows |
| unique | **ext** 16 | uniqueitems row (retail 12); Median 2,479 rows. Read: Fateweaver 400, Dubhdroiacht 800, Buriza-Do Tsuru 1440, Athulua's Command 1348 |
| rare / crafted | **ext** 16 + 16, then **8** x (1 + 16) | two name ids, then eight affix slots (even prefix, odd suffix; retail 8 + 8 and 6 x (1 + 11)). Read on a rare ring: names 198 / 246, prefixes 478 (mana), 439 (magic find), 528 (regeneration), suffix 416 (lightning resistance) in slots 2, 4, 6 and 3 |
| runeword | 12 + 4 | runes.txt row; Median 3,133 rows (fits 12 bits). Not yet seen in a game-written save |
| personalized name | 8 per character, 0-terminated | |
| tome | 5 | `tbk` / `ibk` only |
| unique-id flag + id | 1 + 128 | |
| defense | itemstatcost `armorclass` Save Bits / Add (16, +500 in Median) | armor only |
| max durability, durability | Save Bits / Add of `maxdurability` / `durability` (10 / 10) | armor and weapons; durability only when the maximum is above 0 |
| (3.3) | 1 | |
| quantity | 9 | stackable items (Median's largest stack is 500, arrows; gold `gld` is a character stat) |
| total sockets | 4 | socketed items (Median up to 6) |
| set bonus mask | 5 | set items |
| stats | 16-bit id, **ext** 32-bit parameter when Save Param Bits > 0, value in Save Bits after Save Add; 0xffff ends | paired stats (17/18, 48/49, 50/51, 52/53, 54/55/56, 57/58/59) are written without their own id. The parameter is 32 bits whatever the table says (oskill 712 = Pyroclastic Flow; skill-on-kill 755 << 6 \| 5) |
| set bonus lists | one stat list per bit of the mask | |
| runeword list | one stat list | |
| padding | to the next byte; **ext**: a non-simple item that ends exactly on a byte boundary gets one more zero byte (simple items do not) | seen on starter weapons and on `&01` (simple, no extra byte); without it every later item is misread |

### What the widths mean for Median's items (`tools/save_audit.py`, built tables of main 90e4ed2)

All 40,000+ property stats of uniqueitems, setitems, sets, runes, the magic and rare affixes, automagic, qualityitems and gems
were checked against Save Bits / Save Add (and each unique / set / runeword row's own properties summed per stat):

| Finding | Effect |
|---|---|
| Three level-120 uniques carry values below `-Save Add`: **mxlname_12** (`56!`, light radius -20), **Skin of Kabraxis** (`@10`, light radius -10) with item_lightradius Save Add 5, and **Angelhost** (`@61`, +life -250) with maxhp Save Add 150 | value + Add is negative and cannot be stored in the field. **Fixed in the build** (`txt_migrate.stat_save_add`, from `save_audit.stat_ranges`): item_lightradius Save Add 5 -> 20, maxhp Save Add 150 -> 250 (widths unchanged: values -20..15 and -250..1500 fit). Items saved before this change read those two stats 15 / 100 higher (test characters only) |
| Every other property fits; no item stat used by an item property has Save Bits 0 | |
| Skill parameters: oskill / single-skill stats name skills up to 1109 in a 32-bit field; skill-event and charged stats (skill << 6 \| level) stay below 1024, so the engine's 16-bit stat layer holds them (id-mapping numbers those skills first) | fits |
| Item ids: uniques 2,479, sets 300, prefixes 747, suffixes 959, rare names 77 / 183 (16-bit fields); runewords 3,133 (12 bits) | fits |
| Stacks: largest 500 (9 bits); sockets: at most 6 (4 bits); grids 10 x 6 / 10 x 8 / 10 x 10 (4-bit x / y) | fits |

## Game check

Lane savefmt, 2026-10-28 (details in [testing.md](testing.md) "Lane savefmt"): five new characters (Amazon, Sorceress, Necromancer, Paladin, and an Amazon at the level-120 maxima) with every item quality, the three uniques of bug #250, socketed / event-skill / charged-skill items and a cube of 80 items covering every code character; Save and Exit, reload, Save and Exit. Nothing lost or added, every item's content equal before and after (the only change is the 0x2000 "new item" flag, cleared on load), character stats at the maxima equal, sidecars consistent, all saves re-encode byte for byte. Two findings: bug #250 (fixed, verified) and #251 (item level clamped to 99; fixed by the plugin part `ilvl`, lane ilvl).

