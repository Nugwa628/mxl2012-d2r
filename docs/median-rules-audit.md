# Median XL 2012 rules audit

## Items: scope and evidence

Item rules of Median XL 2012 v005 (cube, properties, uniques, sets, runewords, affixes, item bases, drops, gambling,
vendors), each taken to a verdict against the build (D2R 3.3, build 93847). Lane rules-items2, 2026-10-28; it replaces the
first pass (lane rules-items: 18 rows, all "partly"). Static work: nothing was run in game.

Method:
- **Median's own compiled tables.** v005 ships a `.bin` next to every `.txt` and 1.13c runs the `.bin`. The ModDB original's
  tables (`assets/median`, asset pack 1) and the repack's (`mxl2012-runs/extract-mpq`) are byte-identical for every item
  table and bin read here (cubemain, uniqueitems, setitems, sets, runes, affixes, bases, itemtypes, treasureclassex, gamble,
  properties, itemstatcost, gems, qualityitems, difficultylevels), so nothing below depends on the repack.
- **Built tables.** `work/mod/data/global/excel/{,base/}` of a full `tools/build.py`, compared with `work/named` (Median's
  tables as the build normalised them) row by row and column by column, both banks.
- **D2R's code.** Disassembly of the 93847 image (`tools/d2r_find.py`, `D2R_DUMP` = `mxl2012-runs/gameplay/d2r93847_dump.exe`)
  where a rule's meaning lives in code: the cube search `0x529090` and input matcher `0x529d50`, the item table loader
  `0x318290`. D2R's data guide (`extract/d2r/93847/data/global/dataguide`) for the rest.
- `py -3 -I tools/item_rules_audit.py` repeats the cube-vs-bin, property, vendor and treasure-class checks;
  `tools/cube_reference_audit.py` the cube references (both after a build).

Verdicts: **verified** = Median's data reaches both banks unchanged (or changed only where the row says why) and the rule
means the same in D2R as in 1.13c, shown statically (code, data guide, or a cell-by-cell compare); rows where the last link
is player behaviour list a real-path check (RPn, below) to confirm, not to establish it. **fixed** = wrong in the build
until this lane (or another lane, cited). **unported** = differs from Median, with the reason (row in `docs/unported.md`).
**open (game)** = static work cannot settle it; RPn decides.

## Items: totals

| Category | verified | fixed | unported | open (game) | total |
|---|---|---|---|---|---|
| Cube | 12 | 1 | 0 | 1 | 14 |
| Item properties | 5 | 0 | 0 | 0 | 5 |
| Uniques | 4 | 1 | 1 | 0 | 6 |
| Sets | 3 | 0 | 0 | 0 | 3 |
| Runewords | 4 | 0 | 0 | 0 | 4 |
| Affixes and quality tables | 4 | 1 | 1 | 0 | 6 |
| Item bases | 7 | 1 | 0 | 1 | 9 |
| Drops, gambling, vendors | 5 | 0 | 0 | 0 | 5 |
| **All** | **44** | **4** | **2** | **2** | **52** |

Fixed by data in this lane (`tools/txt_migrate.py`, tests `tools/tests/test_txt_migrate_items2.py`):
1. **Bug #310 (AF5): automagic on 116 misc items was lost.** Median's misc rows carry `auto prefix` (its compiled `misc.bin`
   holds it at record `+0xf8` on all 116 rows: the Sacred amulet, ring, arrows and bolts `qmu qin qqv qqc` with group 401
   (78 automagic rows), Anya's 15 reward amulets `dr1`-`drf` with 494, 96 more amulets with 491-497, `zen` with 801). D2R's misc.txt has no such column, so the merge sent it to `overflow/`. D2R parses weapons, armor and
   misc with **one** field list (`0x318290`-`0x318423`: three table loads `0x3e2b544` with the same arguments, list at
   `[rbp-0x10]` and `0x1c0`) and that list holds `"auto prefix"` (`0x1cfaff0`, referenced from the builder `0x315fd0`). Now
   `EXTRA_COLUMNS` adds the column to misc.txt (both banks) and Median's values reach the game. Of the groups, 401 (78 rows) and 494 (1 row) exist; 491-493, 495-497 and 801 have no automagic rows in Median either, so
   those 97 items roll nothing in 1.13c too.
2. **Bug #311 (CU10): "upgrade dark ring" (cubemain row 10627) named an input D2R cannot resolve.** The source txt reads
   `oµo` (built `o^o`, the `µ` letter rule of `mxl2012_prep.py`); no item has that code (the ring is `o@o`). Median's
   compiled record has numinputs 6 and **no** third input (the other five, `l@l m@m p@p q@q BossKillerRing`, are there), so
   1.13c ran the recipe as "these five plus any sixth item". D2R does the same with an empty slot: the search compares the
   cube's item count with numinputs (`0x529223`), and the matcher passes a slot whose flags `& 3` are 0 at once
   (`0x529d96`). `cube_unresolved_inputs` empties such cells (only this one) after `clean_references`, so D2R gets 1.13c's
   record instead of a name its parser has to cope with. Round 1's "o^o vs o@o" question is settled: not a port defect, and
   not to be "corrected" to `o@o` (that would forbid the other sixth items 1.13c accepts).

Engine items: none new. Every rule here is data or D2R-native; `docs/plugin-plan.md` section 16 lists the contingent ones.

## Items: cube

| ID | Rule (Median v005) | Source | Status | Evidence |
|---|---|---|---|---|
| CU1 | 11,477 recipes (833 disabled) in both banks | cubemain | verified | Built rows 1:1 with Median's; every header field (enabled, min diff, class, op, param, value, numinputs, version) of the txt equals the compiled bin on all 11,477 rows; the build changes only `param` (357 rows, stat ids remapped, below) and the namespace of 834 unique names |
| CU2 | Inputs resolve to the item / type / unique 1.13c compiled | cubemain inputs | verified | Built inputs against `cubemain.bin`: 16,930 item codes, 9,622 item types, 829 uniques (the record holds row + 1) the same; 0 set items used. One input 1.13c compiled to nothing: CU10 |
| CU3 | Outputs resolve | cubemain output / b / c | verified | 7 unique outputs = the bin's; codes and types resolve (`cube_reference_audit.py`, 0 findings after the build); the only special output is the Cow Portal (1 row, D2R native, act 1 as in 1.13c) |
| CU4 | Player conditions: op 3 (stat >= value: level 67 rows, `game_craftpoints` 20, others 16), op 6 (== : `levelchallenge_kill_check` 97, others 7), op 10 (base ==, `level` 254) | cubemain op/param/value | verified | D2R's search switch (`0x529230`, table `0x52992c`, ops 1-14): 3 fails on total `<` value (`0x5292ed`), 6 on `!=` (`0x52985d`), 7-10 the same on the base value (`0x2f48c0`), value shifted right by the stat's ValShift (`0x5292e1`) as in 1.13c (1.13c's checker: 3 `>=`, 4 `<=`, 5 `!=`, 6 `==`). D2R's guide words them "greater / less than"; the code is inclusive. Every param names the same stat in Median's and the built itemstatcost (0 of the 4,479 op rows differ, both banks; 357 params remapped where D2R's stat ids moved) |
| CU5 | Item conditions on input 1: op 15 (>= : `item_is_honorific` 371, signets 315), op 16 (<= : `blessings_counter` <= 0, 3,221 shrine / blessing recipes), op 17 (!=, 7), op 18 (==, 100) | cubemain op/param/value | verified | D2R's matcher switch (`0x52a15b`, table `0x52a8e8`, ops 15-27): 15 fails on `<`, 16 on `>`, 17 on `==`, 18 on `!=`, 19-26 base / non-base, 27 the mod class; applied only when the input index is 0 (`0x52a146`), i.e. input 1, the item Median's rows put the condition on (weapons, armour, jewellery, the trophy items). Stat names equal in both banks (as CU4) |
| CU6 | Op 28: quest item difficulty (Horadric Staff, Khalim's Flail, Wirt's Leg rows) | cubemain op 28 | verified | D2R `0x52a0b5`: an input whose base has `quest` and `questdiffcheck` must carry stat 356 = the game's difficulty; 3 vanilla rows, unchanged |
| CU7 | Input modifiers `noe uni rar set crf tmp mag qty any sock nos nor low hiq` | cubemain inputs | verified | All in D2R's input list (data guide), same meanings; no `upg`/`bas`/`exc`/`eli`/`nru`/`id` used |
| CU8 | Output modifiers `crf` (3,215), `uni`, `mod`, `mag`, `rem`, `rar`, `uns`, `nor`, `hiq`, `low`, `tmp`, `set`; `qty`, `lvl`, `plvl`, `ilvl` | cubemain outputs | verified | All in D2R's output list. No `pre=` / `suf=`, so the affix row numbers (prefix 747, suffix 959 rows, unchanged) cannot shift a recipe |
| CU9 | Recipe property mods (mod 1-5, b/c mods) | cubemain mod columns | verified | 25,453 cells, every code in properties.txt (none inert); 115 skill / monster / state params remapped and resolving to the same names (the only name changes are `_mxl` renames, e.g. `apocalypse` -> `apocalypse_mxl`, where D2R's Warlock took the name) |
| CU10 | Upgrade dark ring (row 10627): five items plus any sixth | cubemain row 10627 | fixed (#311) | See "Fixed" 2 above |
| CU11 | Classic / expansion and ladder recipes | version, ladder | verified | version 0 / 10 / 100 as Median's (D2R's version gate `0x5291bd`-`0x5291cb` skips version >= 100 when the game's data flag is 1, the classic / expansion split 1.13c makes); no ladder rows (`firstLadderSeason`/`lastLadderSeason` blank) |

| CU12 | Every cube row means in the build what it meant to 1.13c (build step) | cubemain.bin, cubemain.txt, both built banks | verified | `tools/cube_rules_check.py` (build step after objstr; tests `tools/tests/test_cube_rules_check.py`; report `work/mod/cube_rules_report.md`): decodes Median's `cubemain.bin` (0x148-byte records: header, 7 inputs, 3 outputs with 5 mods each) and matches all 11,477 txt rows field by field incl. every mod's property / param / min / max / chance; then the source against each built bank by meaning (row order, stat / skill / state / monster params by name, unique rows, renamed codes, #311's emptied input); then D2R's reading (8-bit lvl / plvl / ilvl / chance, 16-bit mod values, op groups, modifier words, properties and stats present, op 28 quest flags). 0 errors on the ModDB original (`assets/median`); notes: 1,100 `version 10` rows (CU11), 626 rows with more items than inputs (CU13), 24 `useitem` second outputs (CU14) |
| CU13 | "Destruction": catalyst + up to 79 unlisted items, the extras are eaten (rows 10846-11477, 626 rows) | numinputs > listed inputs | verified in game | 1.13c and D2R check the item count only; `cubeclasses` row 11399: Catalyst of Destruction + a potion -> the catalyst alone |
| CU14 | Oil of Duplication: `useitem` in output b makes a copy of input 1 (rows 8397-8420, 24 rows) | cubemain output b | verified (fixed, #350) | 1.13c (1.14d `Game.exe` `0x565ab0`) makes a new item per `useitem` slot with its item duplicate `0x55a2a0`, so two copies of input 1 with the slot mods (both slots carry the same: levelreq + 5, `item-duped` 1); D2R keeps input 1 and makes nothing for b. Plugin part `cubedupe` copies output a (D2R's `0x43d660`). `cubeclasses` row 8397 (lane cube2, `checks-20261028-162149-s2`): two weapons in the cube, `item_hasbeenduped` 1; a copy put back with crystal and oil is refused (op 18) |

### Cube recipe classes in game (lane cube, `game_checks.py all cubeclasses`)

Player path: every input dropped by the item generator next to the character, picked up onto the cursor (0x16) and clicked
into a cube cell (0x18 page 3), the cube opened by a right click, the panel's Transmute button clicked; the cube read with
`h items`, the output's stats with `h istat`, the tooltip shot. Rulescheck's classes (RP3: blessings, op 28, dark ring;
gem upgrade, disenchant, shards, unique reroll) are not repeated. Run `checks-20261028-141125-s2` (slot 2, character
CubeLane, Barbarian level 1, Normal); cases and expectations in `tools/cube_game.py`.

| Class | Row | Recipe | Verdict |
|---|---|---|---|
| Rune upgrades | 290 / 435 | El x2 -> Eld; Eld -> El | PASS |
| Socketing | 490 | magic socketed weapon + Oil of Disjunction -> `useitem,rem` | PASS (weapon kept, oil used) |
| Socketing | 845 | normal weapon without sockets + jewel -> `sock 1` | PASS (lane cube2, socket-free roll: `item_numsockets` 1) |
| Rerolls | 541 / 839 / 881 | `usetype,low` / `usetype,rar` / `usetype,uni` (shard shatter) | PASS (qualities 1 / 6 / 7) |
| Op 3 (player stat >= value) | 565 | jewelcrafting with 0 craft points | PASS: refused, cube unchanged |
| Op 10 (base level ==) | 580 | zomghelp at level 1 | PASS by the tooltip (lane cube2, new level-1 character, `checks-20261028-163101-s2`): new magic Angel Star with "+25% Enhanced Damage" and damage 20-31 (base 16-25 x 1.25). The harness's `istat` reads stats 17 and 18 as 0 on every layer: a gap of that read (it sees D2R's total stat, which does not hold the ED of this item), not of the game |
| Op 15 on input 1 only | 8394 + 7581 | full honorifics, then honorific weapon + Mystic Orb | PASS: tempered, honorific, `sock 6` capped at the base's 1 (Median's weapons.txt: 1.13c's cap too); then Strength 2 (the honorific row, not row 7728's 1) |
| Op 18 (item stat ==) | 8397 | dupe: weapon + Arcane Crystal + Oil of Duplication, then a copy again | PASS with plugin `cubedupe` (lane cube2): two weapons, `item_hasbeenduped` 1; the copy's second dupe refused (#350 fixed) |
| Mystic Orbs, skill params | 8226 | Apple of Discord | PASS: honorific row 8169 rejected (op 15), levelreq 10, +20 life / mana, chance-to-cast skill 710 = Dire Charm L (Median's 763) |
| Uptier | 9521 | Aerin Shield (1) + Arcane Crystal -> (2), `mod` | PASS |
| Uptier, version 10 | 8421 | unique Catechumen (1) + crystal + rune | PASS (lane cube2, item level 99 input: unique Catechumen (2), quality 7) |
| Disenchanting | 869 | unique weapon + Catalyst of Learning -> signet + catalyst | PASS (lane cube2: Signet of Learning `zkq` and the catalyst back) |
| Item mods, catalysts | 10621 | RIP | PASS (`item_restinpeace` 1, catalyst back) |
| Destruction | 11399 | catalyst + one other item | PASS (CU13) |
| Quest / uber keys | 8282 / 29 | clue gem cycle; summoning scroll (unique `s0m`) | PASS |
| Token of Absolution | 28 | Oil of Absolution + rune -> `toa`, then used | PASS (lane cube2, `checks-20261028-163101-s2`): made, lifted out of the cube by clicks, a Signet of Learning used and its point put into Strength (packet 0x3a), then the Token used by a right click: used up, Strength 31 -> 30, the point unspent again (#240, SK9) |

## Items: properties

| ID | Rule | Source | Status | Evidence |
|---|---|---|---|---|
| PR1 | Every property an item uses exists | uniques, sets, set items, runes, affixes, gems, quality items, cube | verified | 64,013 cells; 0 missing, 0 inert (`item_rules_audit.py properties`) |
| PR2 | Property functions mean the same | properties func1-7 | verified | Median uses funcs 1-3, 5-8, 10-24; D2R has 1-25 and 36 with 1.13c's names (`ItemModsSetValueRegular` ... `ItemModsSetParamAndValue`, data guide); on the 285 codes D2R shares, Median's func columns equal D2R's (0 differ). Func 10 (skill tab) keeps 1.13c's tab ids 0-20 (Warlock's tabs come after) |
| PR3 | 57 properties whose stat Median deleted (the `*/time` and `*/lvl` families, `dex-add-fake`, `upgrades-left`, ...) | properties stat1 | verified | The stats are not in Median's own itemstatcost (Median reused those ids), so 1.13c resolves them to no stat and the property sets nothing; the build empties the cell (`dangling_refs.tsv`), same effect. No item table uses any of the 57 (PR1) |
| PR4 | Skill, monster and state parameters | prop params | verified | Every param of a skill / monster / state property (`idmap.param_kinds`) resolves to the same row name in Median's and the built table: uniques 2,434 skill, 269 monster, 15 state, 20 skill ranges; runes 2,251 / 258 / 30; sets 79 / 11 / 41; set items 45 / 8; 0 mismatches except the `_mxl` renames |
| PR5 | `MRSacredCircle` prop8 `hp%-mana%` | setitems | verified | No such property in Median's properties.txt: inert in 1.13c, emptied in the build (same effect) |

## Items: uniques

| ID | Rule | Source | Status | Evidence |
|---|---|---|---|---|
| UN1 | 2,479 uniques with Median's bases, levels, rarity, costs, colours | uniqueitems | verified | code, lvl, lvl req, rarity, nolimit, carry1, cost mult/add, chrtransform, invtransform, flippy/inv files: 0 cells differ; one `dropsound` `4` (not a sound name) emptied |
| UN2 | Only enabled uniques generate | enabled -> spawnable | verified | `enabled` 1 / blank / 0 (2,022 / 443 / 14) becomes `spawnable` 1 / blank / 0, `disabled` stays blank. The 457 non-enabled rows are placeholders (`SkillsdLastSkillEver` jewels, `DescBlank`, ...); none is a cube output; 3 are cube inputs (`Lady of Storms2`, `Bardslore`, `Xepera Xeper Xeperu`), which no generator makes in 1.13c either |
| UN3 | Duplicate and over-long names | index | verified | 359 rows renamed `mxlname_N` (D2R's key length / duplicates); every cube reference still points at the row 1.13c's compiler chose (CU2) |
| UN4 | One copy of each carry-1 unique (relics, quest charms) | carry1 | fixed (#280, lane pluginplan) | D2R reads carry1 as a group number; the build gives each row its own (`txt_migrate.carry_numbers`, lane pluginplan2; game check `uniquecarry` PASS) |
| UN5 | Median Statue `zen` is always unique | misc `unique` | unported | Bug #7: D2R asserts on load for an always-unique base without a matching unique row; cleared (name colour differs). Listed |
| UN6 | Unique-only stats and +skill lines read as Median's | itemstatcost text | verified | Bug #140 (lane fixes3) restored 1.13c's hard-coded `+%d to %s` formats D2R reads from data; text audit kinds `stat-format`, `skill-name` |

## Items: sets

| ID | Rule | Source | Status | Evidence |
|---|---|---|---|---|
| SE1 | 67 sets, at most 6 items each | sets, setitems | verified | 40 sets of 5, 14 of 4, 9 of 3, 2 of 2, 2 of 6: none exceeds D2R's six, so `split_large_sets` changes nothing (round 1 assumed a split) |
| SE2 | Partial (2-5 items: PCode2a-5b) and full-set (FCode1-8) bonuses; item bonuses by count (`add func` 2, 82 items) or by piece (1, 1 item) | sets, setitems aprop | verified | Columns unchanged; D2R's guide gives `add func` 0 / 1 / 2 1.13c's meanings; params remapped by name (PR4). sets.txt `level` has no D2R field (it is no bonus rule) |
| SE3 | Every set item can drop | setitems spawnable | verified | 1.13c rolls every set item; D2R needs `spawnable` 1, set on all 299 (`CONSTANTS`) |

## Items: runewords

| ID | Rule | Source | Status | Evidence |
|---|---|---|---|---|
| RW1 | Grey socketed base, jewels first, one rune last; 2-rune words; jewelwords; gem words | runes Rune1-6 | verified | Median spells every socket count out as its own row: 334 rune words in 2,021 rows (`jew`.. then the rune), 5 two-rune words (25 rows), 1 six-rune word, 6 jewelwords, 1,080 gem words (12 gem types x 90 rows); total 3,133. No padding logic, so D2R's exact matcher (`0x372260`: all sockets filled, rune class ids in socket order, quality 4-9 rejected, = 1.13c's rules) reads them as 1.13c does |
| RW2 | Allowed and excluded item types; runes exist | itype1-6, etype1-3, Rune1-6 | verified | All type codes and rune codes resolve; 3,080 of 3,133 rows `complete` as in Median |
| RW3 | Seven properties per runeword | T1Code1-7 | verified | D2R's record holds 7, Median uses at most 7 (no overflow) |
| RW4 | Runeword id saved with the item | runes row | verified | 3,133 rows < 4,096 (D2R's 12-bit field) |

## Items: affixes and quality tables

| ID | Rule | Source | Status | Evidence |
|---|---|---|---|---|
| AF1 | Magic affix pools: spawnable, rare, level, maxlevel, levelreq, frequency, group, itype / etype | magicprefix 747, magicsuffix 959, rareprefix 77, raresuffix 183 | verified | 0 cells differ besides the names' namespace; all item types resolve. Price / transform columns D2R lacks (`transform`, `divide`, rare `add/multiply/divide`) are 0 or blank on every Median row |
| AF2 | No class-specific affixes | class, classspecific, classlevelreq | verified | Blank on every Median row (D2R's own class affixes are not merged: replace table) |
| AF3 | Magic items show no affix names (Median's design) | Name = `NoDesc` | verified | All 1,706 prefixes and suffixes name `NoDesc`, built `mxl2012:NoDesc` = "" (median.json). Display: RP6 |
| AF4 | Automagic on weapons, armour and class items | weapons/armor `auto prefix`, automagic 470 | verified | Columns and the 470 rows unchanged (D2R's automagic adds `classspecific`, `etype4-5`, left blank) |
| AF5 | Automagic on misc items (amulets, quest / trophy items) | misc `auto prefix` | fixed (#310) | See "Fixed" 1 above |
| AF6 | Superior (qualityitems) and low quality | qualityitems 8, lowqualityitems 9 | unported (minor) | Mods and item-type flags unchanged. Median's `level`, `multiply`, `add` (price) and `nummods`, `effect1-2`, `ToHit/Dam%/AC%/Dur%` columns have no D2R field; `thrown` 1 = `weapon` 1 on the same 6 rows, so throwing weapons stay eligible. Whether 1.13c's superior price used `multiply/add` was not read; at most a vendor price difference on superior items. Listed |

## Items: item bases

| ID | Rule | Source | Status | Evidence |
|---|---|---|---|---|
| IB1 | Item type ids D2R's code hard-codes | itemtypes | verified | All 105 (RotW) / 104 (base) D2R type codes keep D2R's row ids (`idmap.check_item_type_ids`: 0 problems); all 222 Median types present |
| IB2 | Item type rules: Equiv chains, Body / BodyLoc, Throwable, Reload, ReEquip, AutoStack, Magic / Rare / Normal, Beltable, Shoots / Quiver, StaffMods, Class, StorePage, VarInvGfx | itemtypes | verified | 0 cells differ per type code |
| IB3 | Socket limits by item level (1 / 25 / 40) | MaxSock1/25/40 | verified | -> MaxSockets1-3 with thresholds 25 / 40 on all 222 types (`CONSTANTS`) |
| IB4 | Stacks, throwing weapons, quivers | stackable, minstack, maxstack, spawnstack, wclass, missiletype | verified | 0 cells differ (missiletype remapped by name, 70 rows). Weapons `quivered` and armor/misc `throwable` have no D2R field; the bow-quiver pairing is itemtypes Shoots / Quiver (IB2). RP1 |
| IB5 | Requirements and class items | levelreq, reqstr, reqdex, itemtypes Class | verified | 0 cells differ in weapons, armor, misc. RP1 |
| IB6 | Durability and repair | durability, nodurability | verified | 0 cells differ (Median keeps durability) |
| IB7 | Charms work from the inventory | itemtypes `Charm` | open (game) | Median marks 14 types `Charm` 1 (`char`, `scha`, `mcha`, `lcha`, `summ`, `grtz`, `araa`-`arag`, `play`). D2R has no Charm column; all of Median's charm types reach `char` through Equiv, so D2R treats them as charms if its test is the type check (not read in D2R's code). `play` (ears) has no stats. RP5. Plugin only if RP5 fails (plugin-plan 16) |
| IB8 | Gem / rune / jewel socket fillers | itemtypes `Gem`, gems keyed by code | verified | D2R has no `Gem` column; fillers are the `sock` Equiv (all 20 `Gem` types reach it) plus gems.txt rows, keyed by item code (txt-migrate.md) |
| IB9 | Greater Elixirs `0g3`-`0g6` | misc pSpell | fixed (#104, lane elixir) | Owner: match the original |

## Items: drops, gambling, vendors

| ID | Rule | Source | Status | Evidence |
|---|---|---|---|---|
| DR1 | 1,468 treasure classes | treasureclassex | verified | Rows 1:1; item names as codes |
| DR2 | 44 entries cleared: `TorajaMacumbaStone`, `BloodRedScryingStone` and 42 `Act N Robot Equip X` | treasureclassex Item1-10 | verified | The names exist in no table of Median's (no item, type, class, unique or set item), so 1.13c's loader (names in the bin, resolved at load) had nothing to drop either. The 44 classes holding them are reached by no monster, superunique, object, level, NPC or recipe (`item_rules_audit.py tc-reach`: 44 of 44 unreachable), so clearing them (with their Prob) changes no drop |
| GA1 | Gamble list and prices | gamble 1,322, base `gamble cost` | verified | All 1,322 codes resolve; costs unchanged |
| GA2 | Gamble quality chances: rare 25,000, set 1,000, unique 1,000 (D2R default 10,000 / 100 / 50) | difficultylevels Gamble* | verified | Median's values in both banks (D2R reads them) |
| VE1 | Vendor stock per NPC, act and difficulty | weapons/armor/misc `<NPC>Min/Max/MagicMin/MagicMax/MagicLvl` | verified | 204,987 cells, 0 differ (Hralti -> Hratli, Drehya -> Anya renamed); 934 base / vendor pairs stock something. Refresh and per-difficulty levels are D2R's 1.13c code: RP4 |

## Items: real-path checks (verdicts: "In-game verdicts" below, lane rulescheck)

Real pickups, click-to-equip and the real cube UI; record character, difficulty, inputs and result; save and reload.

1. **RP1 bases** (IB4, IB5): equip tiered, Sacred and class items with requirements met and unmet; throw a stack and
   reload it; equip a bow with and without its quiver.
2. **RP2 runewords** (RW1): Dawn = El in a grey 1-socket weapon, and jewel, jewel, El in a 3-socket one; El first in the
   3-socket one and a magic base must not make it. A two-rune word (Kyrie: r51 r51 in a staff) and a jewelword.
3. **RP3 cube** (CU4-CU6, CU10): a shrine blessing on a fresh item (op 16 `blessings_counter` <= 0), then the same item again
   (refused once the counter is 1); an honorific recipe (op 15); a level-gated recipe one level below and at the level
   (op 3 / 10); upgrade dark ring with the five items plus a sixth that is not `o@o`.
4. **RP4 vendors and gambling** (VE1, GA1, GA2): Charsi / Hratli / Anya stock in Normal and Hell; refresh by leaving town;
   gamble 20 amulets at Gheed and count rares / uniques against 25,000 / 1,000.
5. **RP5 charms** (IB7): carry a small charm and a Median trophy charm (`arab`); the stats apply only in the inventory.
6. **RP6 names and automagic** (AF3, AF5): a magic ring shows its base name only (no double space); a Sacred amulet or
   Sacred arrows (group 401) and Anya's reward amulet (494) show their automagic line.

## Characters: scope and evidence

Character-side rules of Median XL 2012 v005 (classes and stats, skills and respec, experience, difficulty, mercenaries,
monsters, quests, NPCs, shrines, waypoints, level rules), each checked against the port (D2R 3.3, build 93847). Lane
rules-chars, 2026-10-28. Static work only: nothing was run in game.

Method:
- **Three-way table comparison.** v005 is pure data on 1.13c (`docs/engine-triage.md` section 1), so a Median rule that
  differs from vanilla is a table cell that differs from vanilla. Every character table was compared cell by cell: vanilla
  LoD (the 1.14d install's own `patch_d2.mpq` tables, `gamedata/game/extracted`), Median (`mxl2012-runs/extract-mpq`) and
  the built mod (`work/mod/data/global/excel/{base,}` of a full `tools/build.py`, MXL_D2R_EXTRACT = the machine-local
  config's `extract_dir`). A row "ported" here means every cell Median changed reaches both built banks. Scratch scripts in the ignored
  `work/rc/`.
- **Engine rules** (what 1.13c does in code) come from the docs (`engine-triage.md`, `plugin-plan.md`, `d2r-additions.md`) and a static read of 1.14d `Game.exe` (item-code compares, field-name strings).
- The source is the archive.org repack's MPQ; recheck against the ModDB zip (`docs/verify-original.md`).
- Item, cube, drop and vendor-stock rules are in the items sections (lane rules-items); rows here point there.

Status key: **ported** = data or code present and cited ("unverified" until seen in game; "D2R native"
when D2R's engine already does what 1.13c does), **partly**, **missing**, **deviation** (knowingly different, row in
`docs/unported.md`), **unknown** (needs an in-game test). Fixed in this lane: bugs #240 and #241 (`docs/bugs.md`).

## Characters: totals

| Category | ported | partly | missing | deviation | unknown | total |
|---|---|---|---|---|---|---|
| 1. Classes and stats | 13 | 0 | 0 | 1 | 2 | 16 |
| 2. Skills, skill points and respec | 10 | 1 | 0 | 1 | 0 | 12 |
| 3. Experience and level cap | 7 | 0 | 0 | 0 | 0 | 7 |
| 4. Difficulty rules | 11 | 0 | 0 | 0 | 2 | 13 |
| 5. Mercenaries | 7 | 0 | 0 | 0 | 2 | 9 |
| 6. Monsters and special areas | 10 | 1 | 0 | 0 | 0 | 11 |
| 7. Quests and rewards | 5 | 2 | 0 | 0 | 0 | 7 |
| 8. NPCs and town services | 4 | 0 | 0 | 1 | 0 | 5 |
| 9. Shrines | 3 | 0 | 0 | 0 | 0 | 3 |
| 10. Waypoints | 2 | 0 | 0 | 0 | 0 | 2 |
| 11. Level rules (levels.txt) | 6 | 0 | 1 | 0 | 0 | 7 |
| **All** | **78** | **4** | **1** | **3** | **6** | **92** |

Fixed by data in this lane (both in `tools/txt_migrate.py`, unit tests `tools/tests/test_txt_migrate_item_uses.py`,
`test_txt_migrate_hireling.py`):
1. **Bug #240 (SK9, QU2): Book of Skill, Potion of Life, Malah's scroll and the Token of Absolution did nothing.** 1.13c runs
   these four uses by item code (1.14d `Game.exe` item-use code compares `ass ` at `0x55e3d0`, `xyz ` `0x55e44e`, `tr2 `
   `0x55e4b4`, `toa ` `0x55e52a`; the misc rows have no pSpell in vanilla and in Median). D2R runs them by misc `pSpell`
   (10, 11, 12, 13 on its own rows); the replace merge kept Median's blank. Now `D2R_WHEN_EMPTY_ROWS` gives the four rows
   D2R's pSpell (only that cell: 1.13c shows no use line). The Token is Median's respec item (Oil of Absolution + rune,
   cubemain "ToA creation"), so this was Median's only respec besides Akara. `bkd` (deciphered Bark Scroll) is left: not
   usable in 1.13c (useable 0), D2R made it usable.
2. **Bug #241 (ME4): expansion mercenaries offered up to 5 levels off the player's level instead of 1.** D2R's
   `HiringMaxLevelDifference` carries 1.13c's coded rule by Version (classic rows 5, expansion rows 1). The column was both a
   constant 1 and a "needed from D2R" column; the key match took the first D2R "Rogue Scout" row (classic, 5) for all 120
   Median rows. A post pass (`hireling_level_difference`) now sets each row from D2R's value for its Version (60 x 5, 60 x 1).

Plugin item found, then closed: **LV4, levels.txt `IsInside`** (bug #242, accepted: no visible effect; 1.14d loads the column but no code reads it): 1.14d parses the column (field name `IsInside` in `Game.exe`),
D2R's levels.txt has it as the comment column `*IsInside`. Median changed it on four levels (Kurast 3000 BA in the Arachnid
Lair slot is outdoors with rain and mud; levels 125-127, vanilla's Act 5 "Hell 1-3" uber areas, are indoors). See `docs/plugin-plan.md` section 15.

## 1. Classes and stats

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| CH1 | Starting attributes per class differ from vanilla (Amazon str 25, Druid str 25 / int 25 / vit 15, Assassin dex 35 / int 15, Barbarian int 5 / vit 30, Sorceress vit 15, Necromancer vit 20) | charstats str/dex/int/vit | ported (unverified) | Both banks carry Median's values (0 lost). The repack's loose `charstats.bin` is vanilla and is not used (engine-triage section 4) |
| CH2 | 5 stat points per level | charstats StatPerLevel | ported | Same as vanilla |
| CH3 | Life, mana and stamina per level and per point (in fourths): life/level 80-120 (20-30 life), mana/level 20-60, stamina/level 40-60; LifePerVitality 4-12, ManaPerMagic 12-24, StaminaPerVitality 8 | charstats | ported (unverified) | All 7 classes, both banks. Check: level a character up once, compare life/mana gain with the table |
| CH4 | Base life bonus 50 (vanilla 30) | charstats hpadd | ported | |
| CH5 | Mana regenerates a full bar in 20 seconds (vanilla 120) | charstats ManaRegen | ported (seen in game) | Built = Median (20 for all classes, both banks). Lane manacost `su_mana` (slot 1): a 200 pool regains 0.4 a frame (200 / (20 x 25)) with no regeneration bonus; lane acts3's 2,187 pool with a +300 % `manarecoverybonus` ring refilled in ~140 frames, which hid every cast cost in its logs |
| CH6 | To-hit factor 10 for every class (vanilla -15 to 20) | charstats ToHitFactor | ported | |
| CH7 | Faster movement: walk 10-11, run 12-14 (vanilla 6 / 9); Assassin run drain 20 | charstats WalkVelocity, RunVelocity, RunDrain | ported (unverified) | Check: run speed and animation in HD (D2R draws the same velocity) |
| CH8 | Class block bonus nearly removed: BlockFactor 0-3 (vanilla 20-30). Block cap 75 % | charstats BlockFactor | ported | The 75 % cap is code in 1.13c and D2R alike |
| CH9 | Starting kit: Horadric Cube, 8 Lesser Healing Potions, 10 Town Portal scrolls, Median Statue (`zen`), gold, class weapon / armour, class charms | charstats item1-10 | ported (unverified) | `zen` loses its always-unique flag (bug #7, items lane) |
| CH10 | Innate skills: Throw, Kick, scroll/book skills, Unsummon, then the class innate (Innate Bloodlust, Innate Force Wall, Innate Pain Wall, Vindicate, Left Hand Swing + Innate Titans, Innate MOTW, Left Hand Swing + Innate Bloodbath); no StartSkill | charstats Skill 1-10, StartSkill | ported | |
| CH11 | Potions are timed regeneration (pSpell 6: `hpregen` from max life, `manarecoverybonus`), no class potion multiplier | misc hp1-5 / mp1-5 / rvs / rvl | ported (unverified) | charstats HealthPotionPercent / ManaPotionPercent are 100 for all classes (txt_migrate CONSTANTS). Check: a Barbarian and a Sorceress drink the same potion and gain the same share |
| CH12 | Resistances: 75 % base cap, difficulty penalty (DF1), -100 floor | engine; difficultylevels | ported (D2R native) | D2R's `ResistFloor` -100 (RotW bank) is 1.13c's coded floor; base bank blank as in D2R's own base table |
| CH13 | Breakpoints (cast, hit recovery, block, attack speed) follow 1.13c's formulas over Median's animation frames | animdata, plrmode; engine | unknown | `animdata_merge.py` merges Median's animdata. D2R adds charstats `MinimumCastingDelay` (12, taken from D2R) with no 1.13c column: if it is a cast-rate floor it may cut Median's top cast-rate breakpoints. Check: cast at a high FCR value and count frames |
| CH14 | Light radius | engine (1.13c) / charstats LightRadius (D2R) | ported (D2R native) | 13 from D2R |
| CH15 | Seven classes | charstats, playerclass | deviation | D2R 3.3's Warlock stays playable on Median rules (owner, `docs/warlock-balance.md`) |
| CH16 | Class-specific equipment and class charms | itemtypes, item tables | unknown | Items lane (equip restrictions need real equip tests) |

## 2. Skills, skill points and respec

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| SK1 | 1 skill point per level | 1.13c code; D2R charstats SkillsPerLevel | ported (D2R native) | 1 taken from D2R |
| SK2 | 30 skills per class (25 + 3 uberskills + 2 challenge rewards), three tabs | skills, skilldesc | partly | Skill rows, tree positions (SkillPage/Row/Column) and tab titles migrated; HD tree pages by `hd_ui.py`. Skill sweep: 122 ok, 10 assert, 37 blocked (`docs/skill-sweep.md`, open bugs there) |
| SK3 | Exclusive paths by skill-point cost: `skpoints` = `stat('newskills')+1` while a rival skill has points (Amazon level-18 devotions, Sorceress two elements) | skills skpoints, reqlevel, maxlvl | ported (verified for the cost rule by the skills lane sweep) | Built = Median on all 1,035 Median-owned rows; only the three Warlock-renamed rows differ (Ring of Fire, Apocalypse, Abyss -> `_mxl`, idmap), and Mon Super Lifeblood's `skill('Lifeblood')` (no such skill in v005) reads 0 as in 1.13c. Lane acts3's `setskill` caps at clvl 80 follow it: one rank per 6 levels above reqlevel, rank b+1 costs 1 point while ulvl - reqlevel >= (b - 1) x 6 (Living Flame / Frigid Sphere req 6 -> 14, Tempest req 12 -> 13, Warp Armor req 18 -> 12); Forked Lightning (a root) is refused once two other roots (Flamefront, Cold Blood) have points |
| SK4 | Prerequisites | skills reqskill1-3 | ported | 19 cells name skills v005 does not define (Telekinesis, Blaze, Blizzard, Bone Spear, IronGolem, Concentrate, ...); 1.13c found nothing there either, the build empties them |
| SK5 | Synergies in the skill formulas (`skill('X'.blvl)`) | skills calc columns, skilldesc | ported (unverified) | Carried; formulas naming a skill or stat v005 lacks (Skeleton Mastery, Battle Orders, Battle Command, Fire Trauma, `tora_tora_tora`) become 0, as 1.13c compiled them |
| SK6 | Cooldowns | skills delay | ported | Renamed to D2R's `localdelay` |
| SK7 | Apple: 10 minutes of life regeneration (2.5 % of life per second) and class synergy stats (1.13c item spell 10 = skill 47 `Apple Healing Spell`; not a skill point) | misc `dog` pSpell 10, skills row 47 | fixed (bug #499, plugin part `appleuse`, lane apple) | D2R's pSpell 10 is the Book of Skill: the Apple is refused in game (check `rpsignets`, lane phase3). Plugin part needed (plugin-plan.md section 25). Lane apple, 2026-10-30: `apple_use` (state, duration, the five stats) and `rpsignets` pass |
| SK8 | Book of Skill (Radament): +1 skill point | 1.13c code by item code `ass ` | ported (fixed, bug #240) | pSpell 10 from D2R. Check: read a Book of Skill, skill points +1 |
| SK9 | Respec item: Token of Absolution (Median: "Belladonna", Oil of Absolution + rune) resets stats and skills | 1.13c code by item code `toa `; cubemain "ToA creation" | verified (fixed, bug #240) | pSpell 13 from D2R. engine-triage #24 called the blank pSpell "disabled by Laz": vanilla's row is blank too. Check: cube the token, use it, all points back. In game (lane cube2, `cubeclasses` row 28, `checks-20261028-163101-s2`): the Token is used up by a right click and gives a spent stat point back (Strength 31 -> 30, stat points + 1) |
| SK10 | Akara's free respec once per difficulty | 1.13c and D2R code | ported (D2R native) | Kept as D2R's (owner 2026-10-28) |
| SK11 | Stat unassign (PlugY, forced on in Laz's `plugyfixed.ini`) | not part of v005 | deviation | Optional plugin part I (`docs/plugin-plan.md` 8.1), owner decides |
| SK12 | Monster and mercenary skill rows, slot remaps | skills | ported | engine-triage #1-#3, `docs/function-slots.md` |

## 3. Experience and level cap

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| XP1 | Level cap 120 | experience MaxLvl | ported | 120 for all 7 classes and the Warlock (`d2r_adds.py`) |
| XP2 | Experience curve: 1,000 per level at the start, 7,022,000 at level 119, 666,666,666 sentinel for 120 | experience | ported | 123 rows, both banks |
| XP3 | High-level experience reduction from level 3 on | experience ExpRatio | ported | |
| XP4 | Level-difference penalty, party sharing | 1.13c code | ported (D2R native, unverified) | Same code in D2R |
| XP5 | Death costs 1 % experience on Nightmare and Hell, none on Normal (vanilla 5 / 10) | difficultylevels DeathExpPenalty 0/1/1 | ported (unverified) | Check: die on Nightmare, compare stat 13 |
| XP6 | Quest experience (Rite of Passage) grants up to the next level on Median's curve | 1.13c code | ported (D2R native) | D2R caps at 1.4M / 20M / 40M like 1.13c; no 50,000 hook (`plugin-plan.md` 9) |
| XP7 | Monster experience per level | monlvl XP columns | ported | 123 rows (vanilla 111), Hell flat 500 |

## 4. Difficulty rules

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| DF1 | Resistance penalty 0 / -50 / -100 (vanilla Nightmare -40) | difficultylevels ResistPenalty | ported | |
| DF2 | Monster skill bonus 0 / 4 / 7 | MonsterSkillBonus | ported | |
| DF3 | Freeze and cold length not divided on Nightmare / Hell (1 / 1 / 1) | MonsterFreezeDivisor, MonsterColdDivisor | ported | |
| DF4 | Monster curse length divisor 1 / 2 / 3 | AiCurseDivisor | ported | |
| DF5 | Life and mana leech divided by 4 / 100 / 200 | LifeStealDivisor, ManaStealDivisor | ported (unverified) | Check: leech on Hell |
| DF6 | Unique and champion damage bonus 25 % on all difficulties (vanilla 90 / 75 / 66) | UniqueDamageBonus, ChampionDamageBonus | ported | |
| DF7 | Mercenaries deal full damage to bosses (vanilla 50 / 35 / 25 %) | HireableBossDamagePercent | ported | Renamed to D2R's MercenaryDamagePercentVSBoss |
| DF8 | Corpse Explosion monster damage 3 / 4 / 5 %, no Static Field floor | MonsterCEDamagePercent, StaticFieldMin | ported | |
| DF9 | Gamble odds: rare 25,000, set 1,000, unique 1,000 | GambleRare/Set/Unique | ported | |
| DF10 | Drop upgrade odds (exceptional / elite) | UberCodeOdds*, UltraCodeOdds* | unknown | Median's values equal vanilla's (0/10/20, 0/20/40, 0/0/30, 0/0/40). D2R has no column (the values go to `work/mod/overflow/difficultylevels.txt`), so D2R uses its own coded numbers. Static check of D2R's item drop code, or a drop count |
| DF11 | D2R-only constants: PvP 17 %, Prime Evil vs mercenary 200 % / vs pet 400 %, Fire Enchanted explosion 75 / 50 / 13 %, mercenary stun 13, hit-react buffers | difficultylevels D2R-only columns (taken from D2R) | unknown | 1.13c keeps these in code; listed `docs/d2r-additions.md` (verify). The Fire Enchanted explosion is the likeliest to differ |
| DF12 | Monster level per area and difficulty (Hell areas 120) | levels MonLvl*/MonLvlEx* | ported | Renamed `MonLvl1..3` -> `MonLvl`, `(N)`, `(H)` |
| DF13 | Difficulty names Hatred / Terror / Destruction | strings | ported | `mxl2012/overrides.json` |

## 5. Mercenaries

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| ME1 | 120 hire rows: Median's stats and per-level growth, cost, `Exp/Lvl` 1, levels up to 90 | hireling | ported | Replace merge (RotW's extra mercenaries not merged) |
| ME2 | Six skills per mercenary (vanilla at most two), incl. hidden aura skills (`Act N Exp Aura`, chance 1000) | hireling Skill1-6 | ported | Median's header `LvlPerLvl8` is a typo for `LvlPerLvl3`; the 1.13c `.bin` has 0 there on all 120 rows (decoded, `work/rc/hirebin.py`), the build leaves the column empty: same |
| ME3 | Resistances (one 1.13c column) | hireling Resist, Resist/Lvl | ported | Split into D2R's four resist columns |
| ME4 | Hire list levels within 1 of the player (expansion rows) | 1.13c code; D2R hireling HiringMaxLevelDifference | ported (fixed, bug #241) | 60 classic rows 5, 60 expansion rows 1, as D2R |
| ME5 | Equipment: weapon types per class (bow, polearm/spear, sword + shield, sword) | hireling WType1/2, Head/Torso/Weapon/Shield | ported (D2R native) | Median kept vanilla's values; D2R keeps the rule in code |
| ME6 | Hire descriptions | hireling HireDesc | ported | hiredesc codes -> D2R string keys (`HIREDESC_KEYS`) |
| ME7 | Resurrect cost | 1.13c code; D2R resurrectcost* | ported (D2R native, unverified) | D2R's 15 / 2 / 50,000 on every row |
| ME8 | D2R's mercenary panel shows Median's six skills (hidden auras included?) | D2R UI | unknown | Check: hire each act's mercenary, open the panel, note icons and names |
| ME9 | Mercenary level follows the player past 99 (`Exp/Lvl` 1), to 119: the engine stops a mercenary one below MaxLvl (1.13c: 98 under 99) | hireling, engine | verified | Check `ml_merc` (lane unported): 100, 110, 119 by kill experience, the player's own level reached, nothing past 119, kept over Save and Exit (docs/testing.md "Lane unported") |

## 6. Monsters and special areas

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| MO1 | Monster stats per level to 122 (Hell flat: defence 1200, life 50,000 %, damage 515 %) | monlvl | ported | 123 rows, all Median cells kept |
| MO2 | Area monster lists (mon/nmon/umon 1-10), ranged spawns, critters | levels | ported | One cell (Ice Cave 2A `sunlesscleric`) names a monster v005 lacks; 1.13c skipped it, the build empties it |
| MO3 | Density 600 (vanilla 520) | levels MonDen | ported | |
| MO4 | No random unique / champion packs: MonUMin / MonUMax blank in 122 areas (vanilla 1-9). Elites, veterans and heroic monsters are monstats rows | levels MonU* | ported (unverified) | Check: clear an area, count unique packs (expect only superuniques) |
| MO5 | Unique monster modifiers: pick weights and constants changed, `thief` enabled | monumod | ported | |
| MO6 | 84 superuniques (18 new), new names, classes, modifiers, group sizes, drops | superuniques | ported | Bug #2 (blank "Expansion" record kept as id 42); names in the mxl2012 namespace |
| MO7 | Act bosses and monster AI | monstats, monai | ported (unverified) | Monster lanes: `docs/monster-sweep.md` |
| MO8 | Summoning uberquests and spawners (102 missile rows, server hit 6) | missiles | partly | `docs/plugin-plan.md` 3 (B) |
| MO9 | Kurast 3000 BA through the Arachnid Lair (level 84 re-linked to Spider Forest, layout and level type changed), Pandemonium 1 warp to level 17 | levels Vis/Warp, LevelType, DrlgType, lvlprest | ported | Maps: `docs/maps-hd.md`; outdoors flag LV4 |
| MO10 | Monster corpses, sounds, overlays of Median's own monsters | monstats2, monsounds | ported | Graphics lanes |
| MO11 | No Terror Zones | D2R addition | ported | `d2r_adds.py` |

## 7. Quests and rewards

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| QU1 | Acts 1-5 quests as vanilla (Median changed no quest code: pure data) | 1.13c code | ported (D2R native) | |
| QU2 | Coded quest-item uses: Book of Skill (+1 skill point), Potion of Life (+20 life), Malah's scroll (+10 all resistances), Token of Absolution | 1.13c code by item code | ported (fixed, bug #240) | Check: use each item once |
| QU3 | Socket quest, imbue, personalize, Cain's identify | 1.13c code | ported (D2R native) | |
| QU4 | Median's uberquests (30): summoning books, clue items, challenge decoys | cubemain, misc, missiles | partly | Cube: items sections; spawners: MO8 |
| QU5 | Level Challenges, Black Road trials, trophies (cube ops on stats `var`, `var_blackroad`, gold 666,666) | cubemain op/param | partly | Items sections (cube) |
| QU6 | Cow Level portal: Wirt's Leg + Tome of Town Portal | cubemain "Cow Portal" | ported (unverified) | The only portal recipe; D2R's Pandemonium portal recipes are replaced |
| QU7 | Pandemonium levels reused for ubers | levels 133-136 | ported | |

## 8. NPCs and town services

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| NP1 | Vendors buy for a quarter of vanilla (buy mult 128), sell mult 1024, quest sell mult 768 in Act 5, max buy price 1,000-3,000 / 10,000-15,000 / 20,000-25,000 | npc | ported | All 17 rows |
| NP2 | Vendor stock, gambling bases | item tables, gamble | ported | Items sections |
| NP3 | Repair, resurrect, identify, hire | 1.13c code | ported (D2R native) | |
| NP4 | Inventory 10x6, cube 10x8, stash 10x10 | inventory | deviation | Stash / trade / vendor grids are D2R's (owner 2026-10-28, `docs/tables-status.md`) |
| NP5 | Free respec at Akara | code | ported (D2R native) | SK10 |

## 9. Shrines

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| SH1 | Shrine strengths changed (row 7 to-hit / damage 200 -> 150 %, row 13 400 -> 100) | shrines Arg0/Arg1 | ported | |
| SH2 | Shrines 18, 21 and 22 never appear (LevelMin 125, above the level cap) | shrines LevelMin | ported | |
| SH3 | Shrine names and messages | tbl `ShrId<n>` / `ShrMsg<n>` | ported | `string_gaps.py` / D2R_ALWAYS (`docs/text-audit.md`) |

## 10. Waypoints

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| WP1 | Pandemonium 2 carries waypoint number 17 (the Valley's), no waypoint object | levels Waypoint | ported | Bug #13, `docs/plugin-plan.md` 7 (H), check `pandewp` |
| WP2 | Other waypoints as vanilla | levels Waypoint | ported (D2R native) | |

## 11. Level rules (levels.txt)

| ID | Rule (Median v005) | Source | Status | Port evidence / check idea |
|---|---|---|---|---|
| LV1 | Sizes, DRLG and level types of re-made areas (13, 14, 18, 59, 60, 65, 84, 95, 116, 125-127) | levels SizeX/Y, DrlgType, LevelType | ported | |
| LV2 | Lighting colour and intensity on 132 levels | levels Intensity, Red, Green, Blue | ported (unverified) | Check the HD look in a few areas |
| LV3 | Weather: rain and mud in level 84, no rain in Act 5 levels 109-112 | levels Rain, Mud | ported (unverified) | Rain / Mud alone decide it (no inside flag in either engine, bug #242) |
| LV4 | Indoors / outdoors: level 84 outdoors, levels 125-127 (Act 5 "Hell 1-3") indoors | levels IsInside | ported (no effect) | Dead data in Median's own engine: 1.14d loads `IsInside` (`+8`) and never reads it; D2R does not load it. Light, day/night, rain and mud come from Intensity/RGB and Rain/Mud in both engines (bug #242, accepted: no visible effect) |
| LV5 | Saved monsters, wandering monsters, NoPer, LOSDraw, DrawEdges | levels | ported | |
| LV6 | Object groups and chances, warp distance 4500 | levels ObjGrp/ObjPrb, WarpDist | ported | |
| LV7 | No town portal in towns and the Pandemonium finale | 1.13c code; D2R levels PreventTownPortal | ported (D2R native) | Taken from D2R |

## Characters: in-game checks (verdicts: "In-game verdicts" below, lane rulescheck)

Disposable characters, real UI paths where possible. Record class, difficulty, the value before and after.

1. **#240**: read a Book of Skill (skill points +1), drink a Potion of Life (+20 max life), read Malah's scroll (+10 all
   resistances), cube Oil of Absolution + a rune and use the token (all stat and skill points back). Also check the token's
   tooltip (1.13c shows no use line).
2. **#241**: hire screens in each act on Normal and Hell: offered levels within 1 of the player.
3. **CH3 / CH5 / CH7**: one level-up per class (life, mana, stamina gain), mana refill time (about 20 s), run speed.
4. **CH11**: same potion on a Barbarian and a Sorceress: same share healed.
5. **CH13**: cast rate breakpoints near the top; what `MinimumCastingDelay` 12 does.
6. **XP5**: death on Nightmare costs 1 % experience; none on Normal.
7. **DF5 / DF10 / DF11**: leech on Hell; drop upgrade counts; Fire Enchanted explosion damage on Hell.
8. **ME8 / ME9**: mercenary panel (six skills, hidden auras), mercenary level over 99.
9. **MO4**: clear an area: no random unique / champion packs.
10. **LV2-LV4**: Kurast 3000 BA (level 84): daylight, rain and mud; levels 125-127 lighting.

## In-game verdicts (lane rulescheck, 2026-10-28)

Both check lists above, run on the player path as the owner requires: no god mode, no stats or levels set by the harness, a
normal mortal character, items picked up from the ground by a left click (the harness drops them next to the character as a
monster would), used by a right click in the inventory, the real cube (items clicked onto the cube, Transmute button) and real
NPC clicks. Where only a harness shortcut reaches a rule the verdict says "shortcut only" and the rule stays open. Slot 3,
background input, fresh Druids `Rcdruid` / `Rcdruidb`, build of this branch. New checks in `tools/game_checks.py` (rc* for the
characters, rp* for the items; unit tests `tools/test_game_checks_rulescheck.py`); results in `docs/testing.md` ("Lane
rulescheck"). Evidence (not in git): `mxl2012-runs/rulescheck/` (`cal/` session 1, `batch2.log`, run folders).

What decided most verdicts: **a level-1 character cannot reach most rules on the player path.** The quest items are refused,
Kashya does not hire before her quest, Median's charms and trophies carry level requirements, and the starting Druid kills
nothing in Blood Moor (it died to a Flit with 0 experience). Levelling a character to these points by hand is not something a
lane run can do; these rows say "can't test" and name what they need.

| Check | Verdict | Evidence / why |
|---|---|---|
| **#240 Book of Skill, Potion of Life, Malah's scroll** | can't test | The click on `ass` on the ground is answered "I can't" (`rcbook_refused.png`); `xyz` and `tr2` the same; `h item ass inv` fails with "placing failed". `bks` (also a quest item) and every non-quest item pick up normally. The three have `quest` 15 / 19 / 32 and `questdiffcheck` 1, the same cells as D2R's own rows and Median's misc.txt; stat 356 set to 0 or 1 on the item does not change it. D2R gives these items only to a character inside the quest (bug #332). Needs a character at Radament / Anya / Malah |
| **#240 Token of Absolution** | pass (use); refund open | Twice (slot 3 session, then check `rctoken` on slot 2): Oil of Absolution and an El rune picked up, clicked onto the cube, Transmute: the token (`toa`, ilvl 99) appears in the cube, is lifted into the inventory and used by a right click: used up (before the fix the click did nothing). Tooltip: Median's own "Belladonna Extract / Right-click to reset Stat/Skill Points". The refund (all points back) needs spent points; a level-1 character has none |
| **#241 hire level range** | can't test | Kashya's menu for a fresh character: Talk, Cancel (`hire_menu.png`); as in 1.13c she hires after the Burial Grounds quest (Blood Raven). The expected list for a level-1 player (every Rogue level 3; 3-6 would be the bug) is written into check `rchire` |
| CH3 / CH5 / CH7 level-up gain, mana refill, run speed | not run | CH3 needs a level-up (out of reach, see above); CH5 / CH7 had no check written in this lane |
| CH11 potion share | not run | Needs damage taken and a measured heal on two classes; no check written |
| **CH13 cast delay** | can't test; data question open | Trap Rat Form / Treewarden Form (the only two Druid skills with a delay at required level 1) learnt by `h setskill` (shortcut) and right-clicked in town and in Blood Moor: "Impossible." both times, mana unchanged, so the rule was not reached. Static: 1.13c's `delay` puts every skill with a delay on hold (one unit-wide delay); D2R split it into `localdelay` (the skill's own cooldown) and `globaldelay` (the hold on the other delay skills), and charstats `MinimumCastingDelay` 12 is D2R's global floor after a delay skill. The build maps Median's `delay` to `localdelay` only (`globaldelay` empty on all 111 rows), so Median's delay skills likely do not hold each other in the port. Copying `delay` into `globaldelay` too would be the data fix; not made without a game confirmation (check `rcdelay` is ready for two castable delay skills) |
| XP5 death penalty | can't test | A real death on Normal (slain by a Flit in Blood Moor, no god mode; `hunt1.png`) with 0 experience: nothing to lose. Median's own rule (1 % on Nightmare / Hell) needs a character there |
| DF5 / DF10 / DF11 | can't test | Hell |
| ME8 / ME9 merc panel, level above 99 | can't test | No hire (see #241); level 99+ is far out of reach |
| MO4 no random packs | not run | Needs an area cleared by a character that survives it |
| **LV2-LV4 levels 84, 125-127** | shortcut only; #242 accepted: no visible effect (lane isinside: 1.14d never reads IsInside) | Travel by `h level` (shortcut). Kurast 3000 BA (84) is drawn dark with no rain (`level_84.png`); Median makes it outdoors with rain and mud. Levels 125-127 dark like indoor areas. Consistent with D2R reading no `IsInside` (bug #242, plugin-plan section 15) |
| **RP1 bases** | pass for requirements; rest not run | Check `rpequip` (slot 2, `checks-20261028-151714-s2`): a Short Sword (no requirement) picked up and clicked onto the weapon slot is worn; a Broad Sword (Strength 48, the Druid has less) is refused and stays off. Sacred / class items, throwing stacks, bow + quiver: not run |
| **RP2 runewords** | pass | Check `rprunes`, every base and filler picked up, fillers clicked onto the base in order: Dawn from El in a grey 1-socket Short Sword; Dawn from jewel, jewel, El in a 3-socket Broad Sword; no runeword with El first; no runeword in a magic base; Kyrie from Taha, Taha in a 2-socket Long Staff (runeword flag 0x04000000, names in `rw_*.png`). Two text defects seen: the rune-letter line reads `'Missing string'` (bug #330) and making Kyrie printed "Chronicle Item Discovered: [Gemmed Horadric Staff]" (bug #331) |
| **RP3 cube** | dark ring pass; rest not run | Check `rpdarkring` on a fresh Druid (slot 2, `checks-20261028-151714-s2`): Ingredient Rings 1, 2, 4, 5 and the Boss Killer Ring clicked into the cube, Transmute: nothing (cube unchanged, the count is 6); plus an El rune (not `o@o`): the Upgraded Boss Killer Ring (`s@s`) alone in the cube. The first run (`Rcdruid`) was void, its cube held items from an earlier session. Static side: Median's compiled cubemain.bin record 10627 has numinputs 6 and input 3 empty (bytes 0x24-0x2b zero), the five others resolved, so any sixth item completes it, as bug #311 found. Blessing, honorific and level-gated recipes: not run |
| RP4 vendors and gambling | not run | Gambling 20 amulets needs gold a fresh character does not have; vendor stock not run |
| **RP5 charms** | can't test | Median's charms carry level requirements: the Scroll of Summons shows "Required Level: 6" in red (`charm_tip2.png`), trophies 60-90; a level-1 character gets no bonus from the inventory either way (oskill 596 stat 0 with the charm carried). The contingent plugin item M (plugin-plan section 16) stays contingent |
| **RP6 names and automagic** | name pass; automagic open | A magic ring reads "Ring" (base name only, no double space; `name_rin.png`). The Sacred amulet (`qmu`) and Anya's amulet (`dr1`) came out magic; their tooltips do not tell an automagic line from a rolled affix. Median's automagic group 401 has no amulet row (item types `armo` / `misl` / weapons), group 494's one row is for type `scrd`, so neither amulet may show one in v005 either: needs a compare against Median's own game |

Totals: 17 checks (10 character, 6 item, plus item check 7 settled statically by lane rules-items2 and confirmed above): pass 2
(#240 token use, RP2), pass in part 3 (RP1 requirements, RP3 dark ring, RP6 names), shortcut only 1 (LV2-LV4, a known fail),
can't test 7, not run 4. No data fix came out of the runs; new bugs #330-#333.

## In-game verdicts with a set-up character (lane rulescheck2, 2026-10-28)

Coordinator ruling (lane_rules "PLAYER PATH vs SET-UP"): the character may be SET UP by the harness or by a save edit with our
own code, named in each note; the judged action stays on the player path. Set-up here: a new Paladin `Rcpalb` on slot 4, level 30
with experience half-way through the level and seven skills by the harness (`rc2setup`), and by a save edit of the closed
character (`tools/rc_setup.py`: checksum and D2RLoader's `.d2rl` made again) progression 10 (Nightmare and Hell unlocked), the
Burial Grounds quest (Blood Raven) done on all three difficulties and the three quest-item flags of bug #332 on Normal. New checks
`rc2setup`, `rc2quest`, `rc2refund`, `rc2delay`, `rc2death` in `tools/game_checks.py`; evidence (not in git):
`mxl2012-runs/rulescheck2/` (step files, `s*.out`) and the run folder `work/runs/rulescheck2` of the worktree.

| Check | Verdict | Evidence / why |
|---|---|---|
| **#332 quest-item pickup** | same as 1.13c (not a bug) | 1.14d `0x55cc90` and D2R `0x4734f0` are the same gate: `ass` needs quest word 9 bit 5, `xyz` word 20 bit 5, `tr2` word 37 bit 8 (bit 7 clear) on the item's difficulty |
| **#240 Book, Potion of Life, Malah's scroll** | pass | With the #332 flags set: each picked up by a click and used by a right click; skill points +1, maximum life +20, all four resistances +10; each used up (`rc2quest`) |
| **#240 Token refund** | pass | Strength +20 "spent" and no unspent points (harness); the token made in the cube and used: strength 45 -> 25, stat points 0 -> 20, skill points 0 -> 7, the seven skills cleared (`rc2refund`) |
| **#241 hire level range** | pass (expansion rows) | Kashya after the Burial Grounds flag: Hire offered; ten Rogues all level 29 for a level-30 player, 490 / 735 gold (`hire_list.png`). Classic rows need a classic character: not run |
| **CH13 cast delay** | fail before the fix; fixed (bug #335), PASS after the fix (lane skillsweep, slot 4: both Holy Armor casts refused inside Mythal's delay, state `skilldelay` on; control: Holy Armor casts after the delay) | Mythal (delay 245 frames; the game's skill-point function gives it to the Paladin) then Holy Armor by right clicks: Holy Armor was cast 110 frames into Mythal's delay, no `skilldelay` state; 1.13c holds it. A cast is read from D2R's own cooldown stat 359 at the skill's layer (Holy Armor's mana use does not show in stat 8, which made the first attempts look refused). The build now fills `globaldelay` too |
| **XP5 death penalty** | pass | Nightmare and Hell, level 30 with 421,500 experience (span 407,000-436,000): killed by placed zombies, no god mode; both lose exactly 290 (1 % of the span), vanilla would be 1,450 / 2,900 (`rc2death`) |
| DF5 leech divisors | not run | Built data 4 / 100 / 200 is Median's; D2R reads the same columns. No in-game measurement (needs a fixed hit damage) |
| **DF10 upgrade odds** | same (no effect in either game) | 1.14d's only reader of UberCodeOdds / UltraCodeOdds (`0x55fb80`) is not called; D2R has no upgrade roll |
| **DF11 D2R-only constants** | Fire Enchanted fixed (bug #336); rest same or not found | Fire Enchanted explosion: 1.14d 3/4, 2/3, 1/8 (`0x5a2725`..`0x5a2766`), D2R's rows 75 / 50 / 13 -> the build sets 75 / 67 / 13. MonsterCEDamagePercent 3 / 4 / 5 and StaticFieldMin 0 match 1.14d. PvP 17 %, mercenary stun, Prime Evil 200 / 400 %: no 1.14d counterpart found, D2R's values kept |
| ME8 / ME9 merc panel, level above 99 | can't test yet | Hiring not reached: the harness's gold (stat 14) does not reach the client's hire panel (0 gold shown). Needs gold in the save (save edit) or lane mercs2's hire verbs; `rc_setup.set_merc_experience` is ready for ME9 |
| **RP5 charms** | pass; plugin item M not needed | Level 30, Scroll of Summons (level 6): oskill 596 is 1 in the inventory, 0 inside the cube, 1 back in the inventory, 0 on the ground (`rpcharm`) |
| **#330 rune letters** | fixed for runes 1-33; 34-56 bug #334 | The tooltip looks the gems `letter` cell up as a D2R key; r01-r33 now name D2R's `r01L`..`r33L`. D2RLoader rejects new `d2r:` keys, so Median's Great Runes need a plugin fallback |
| **#331 Chronicle name** | explained (cosmetic) | D2R's Chronicle names a dummy of the runes row's itype1 base (`staf` -> Horadric Staff), not the runeword |

Totals: 13 rows: pass 5 (#240 x2, #241, XP5, RP5), same as 1.13c 2 (#332, DF10), fixed by data 3 (CH13, DF11 Fire Enchanted, #330
for runes 1-33), explained 1 (#331), not run / can't test 2 (DF5, ME8 / ME9). New bugs #334-#336.
