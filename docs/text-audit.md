# No raw text: the text audit (lane text, 2026-10-28)

Owner decision 2026-10-28: **no raw text anywhere a player sees it** (items first, then monsters, skills, objects, UI): a full
translation / port of Median XL 2012 into D2R. This replaces the earlier default (data/string_gaps.tsv `raw`: a name nobody
defines showed its key, "CouatlInhibitor"). Tools: `tools/string_gaps.py` (the decisions), `tools/text_audit.py` (the check,
tests `tools/tests/test_text_audit.py`, `test_string_gaps.py`), `tools/strings_check.py` (runs the audit in the build).

## What was written

`data/string_gaps.tsv` (columns `table column key action text cells reason`; the reason column says where each text comes from):

| Action | Rows | What |
|---|---|---|
| `text` | 54 rows, 50 keys | the 46 former `raw` names (monsters 13, monster types 4, objects 17, pet 1 (the same key as a monster), super unique 1, level warps 3, the 8 beta-era potions) and 4 description lines that were empty: the three stats and the Dark Nephalem |
| `fix` | 2 | Median's own text reads like a key: `PortalKombat` -> "Portal Kombat" (unique item `New2PortalKombat`), `StataMater` -> "Stata Mater" (runeword name, 6 rows) |
| `cell` | 12 | the four bone prison monsters (`boneprison1-4`) had a blank NameStr; they read D2R's `skillname88` ("Bone Prison"); the four Greater Elixirs get `spelldesc` 0 and `pSpell` 0 (bug #104, below) |
| `empty` | 4 | the description keys of the four Greater Elixirs: the original shows no line (below) |

Names (CamelCase split, Median's typos fixed, Median's own name where it has one): `Couatl Inhibitor` and `Landshark Inhibitor` (Median's
tbl has them under the typo keys `CouatlInhibitr`, `LandsharkInhbitor`), `Crystal Ball`, `Glass Skull` (the super unique is
"Glass Skull the Jagged"), `Crusader Spirit` (monster and pet; the skill is "Summon Crusader Spirit"), `Claw Vipers`, `Vampires`
(was `Vamps`), `Barbarian` for the two Act 5 hireling rows, `Injured Barbarian`, `Funeral Pyre`, `Burning Logs`, `Steam`, `Torch`,
`Barbecue`, the six Desert Shrine spawn markers as "<Armor|Combat|Recharge|Resist|Skill|Stamina> Shrine", `Treasure Chest`,
`Unique Chest`, `Arcane Thingamajig`, `Control Object`. Most of the object names are for spawn markers (token `ss`, not selectable)
that no player meets; they are text for completeness. Names that were already words (`Bunny`, `Pandora`, `Zoo`, `Keeper`, `Humans`,
`Magi`, `Worldstone Effect`, `Ghosthoof the Possessed`, `To The Pandemonium Run 1-3`) keep their wording, now as an explicit row.

Description lines, in Median's wording style (the text is the part after the value, `descfunc` / `descval` decide the order):

| Stat | Line | Why |
|---|---|---|
| `item_elemskill` (`ModitemColdSkills`) | `+N to Fire Skills` | D2R's stat 126 reads "+12 to Fire Skills" (property `fireskill`); Median's key name says Cold, nothing in its tables gives the stat |
| `item_levelreqpct` (`ModitemLevReq`) | `Required Level +N%` | descfunc 4 / descval 2 as Median's `item_req_percent` ("Requirements +10%") |
| `passive_mastery_melee_dmg` (`ModitemPeril`) | `+N% to Melee Damage` | Median's group line was descfunc 3 / descval 0 (the text alone, no value); it is descfunc 4 / descval 1 now (`cells` column), as the ModitemAllsk group ("+N% to Spell Damage") |
| Greater Elixirs `0g3`-`0g6` | (no line) | the lane's first lines ("Fire Spell Damage +100% for 20 seconds" ...) are gone: the original shows none (below) |
| `dark_kid` description | `Divine Apparition, Superbeast, Tremor Attack` | its skills and the Tremor its monprop casts; the style of `mon_icebeam` |

None of the three stats is given by any property, affix, unique, set, runeword or recipe of Median 2012 (greps over the tables): a player
can only see the lines through a harness-made item.

### Greater Elixirs of Strength / Dexterity / Energy / Vitality (`0g3`-`0g6`, bug #104, lane elixir)

Owner decision 2026-10-28: match the original exactly. Median's rows are *named* for attributes but set `passive_fire / cold / ltng / pois_mastery` 100 for 500 ticks, name states `strpot`, `dexpot`, `enrpot`, `vitpot` that Median's states.txt lacks, and description keys no .tbl defines (`PotFireReloadedDesc`, `PotColdReloadedDex`, `PotLtngReloadedDesc`, `PotPoisReloadedDesc`; the tbl's `PotOfStrReloadedDesc` ... are used by no row). What 1.13c did with that, read in 1.14d's `Game.exe` (the stand-in): an unknown state name loads as -1, an unknown description key loads as string 5382 ("FLYING POLAR BUFFALO ERROR"), the tooltip builder skips a spell description of 5382, and the pSpell 9 handler returns 0 on a state <= 0. So the original item is the red name ("Elixir of Greater Strength", the tbl's `0g3` text), no description line, and **drinking does nothing: the elixir stays**. The addresses and the chain are in bugs.md #104. D2R would assert (`SkillItem.cpp:823`) and use the elixir up on the same data, so the port sets `spelldescstr` empty, `spelldesc` 0 and `pSpell` 0 for the four rows (`data/string_gaps.tsv`: four `empty` and eight `cell` rows); the other cells stay Median's. No "missing string", no raw key, no invented line is shown. Checked in game (below).

## The audit

`py -3 -I tools/text_audit.py [--excel-dir DIR] [--layouts-dir DIR] [--report FILE]` (exit 1 on a finding). It reads the built tables
of both banks (`excel/` and `excel/base/`), resolves every localization cell the way the game does (`mxl2012:<key>` or D2R's key, case
insensitive, the mod's `d2r:` overrides over D2R's text, English) and reports:

| Kind | Meaning |
|---|---|
| `missing-key` | the cell names a key nobody defines |
| `missing-string` | the text is or contains "Missing string" |
| `placeholder` | a placeholder word as the whole text (`blah`, `x`, `tbd`, `Not used`, `???`, ...). Not "Do Not Use Ethereal Items Idiot" (Median's joke item `abu`) |
| `key-text` | one token that looks like a key: snake_case, CamelCase, a lower-case echo of its own key (`btor`), a qualified key |
| `empty-name` | a blank name on an item with an inventory picture, an enabled monster with a token, a skill with an icon or a clickable object |
| `blank-key` | a blank cell D2R looks up anyway (`BLANK_LOOKUP`): `levels` `LevelEntry` of a level with a `LevelName` is the red "Entering ..." banner on arrival and reads "Missing string" when blank (bugs.md #120, the Rogue Encampment on game start) |
| `layout-at-key` / `layout-key-missing` | a `@Key` left in a layout file of the mod (bugs.md #30, #33: such a key draws "Missing string" in a layout the mod serves) |
| `stat-format` | an itemstatcost row with a tooltip function whose format D2R reads from `descstrpos` / `descstrneg` (every descfunc but 11, 13, 14, 30, 31: D2R's formatter `0x2d6520`) and a blank cell: D2R prints the dummy string 5382, "FLYING POLAR BUFFALO ERROR", as the line (bugs.md #140: 1.13c hard-codes the text of descfuncs 27 / 28) |
| `skill-name` | an item property (uniques, sets, runewords, affixes, gems, recipe outputs) whose line names a skill (+skill, aura, chance to cast, charges: descfuncs 15, 16, 24, 27, 28) that has no readable name: no skills row, no skilldesc, a blank or unknown `str name`; D2R's name lookup `0x28bcf0` falls back to the same dummy string. The parameter is read as both games' loaders read it (1.14d `0x6336a0`, D2R `0x320310`, the same code): a cell starting with `-` or a digit is a number, else a skills.txt name, else a montype or states name (its index), else 0; so a name no table has, or a blank cell, is skill 0 (Attack) and reads "+N to Attack" in both games (bugs.md #180) |
| `skill-desc` | a skill tooltip line (skilldesc `descline` / `dsc2line` / `dsc3line` of a row a skills row names, class or not: Fire Wall has no class in Median 2012) that D2R's line renderer `0x287a50` (jump table `0x289f88`) draws wrong. D2R still builds 1.13c's types 1-73 by appending text A / B, the number and a unit; only types 13, 34, 36, 40, 53-56, 66, 74, 75 and D2R's own 76-79 use the text as a printf format (`strings_ns.SKILLDESC_FORMAT`). Found: a mana cost line (type 1) with a blank text A on a skill with a mana cost (1.13c read skilldesc's `str mana`, D2R reads text A: the dummy string + the cost, "FLYING POLAR BUFFALO ERROR44"); a text with a printf conversion in an appending type (D2R's `StrSkill82` "Fire Duration: %d seconds" shows its raw `%d`); a type-36 format without a number; and, while `FIXED_LABELS_HANDLED` is off, the types whose label D2R hard-codes as a printf format (9, 10, 11, 14, 22, 25, 27, 28: `SKILLDESC_FIXED_LABELS`, cut back in game by the plugin part `skilltext`) (bugs.md #396) |
| `colour-code` | a text of the mod's own (a Median-only key or a `d2r:` override, used by a table or not) with a colour code `ÿc<char>` D2R cannot draw (`strings_ns.D2R_COLOURS`: `0`-`9`, `:`, `;`, D2R's `M`, `U`): D2R prints it as text. Median's `ÿc/` read "*/" in HD and "Ø/" in classic on 706 texts; tbl2json maps it to `ÿc0` (`strings_ns.COLOUR_MAP`, docs/strings.md "Colour codes", bugs.md #398); also a code that ends a line ("ÿc<char> before a line break"): D2R drops it, 1.14d colours the next line, tbl2json moves it behind the break |

Only text the mod provides is checked: a D2R key whose text the mod does not change (D2R's own lowercase `fissure` / `orifice`, the
guild stones D2R blanks) is D2R's business. `data/text_audit_allow.tsv` (kind, table, column, key, reason) exempts a hit with a reason; a stale
row fails. Allowed now: nothing (the three unknown skill names of Trang-Oul's Avatar left the list when the check learnt the loaders' reading, bugs.md #180). `strings_check.py --rewritten` runs the audit, `build.py` calls that twice (after the data steps and again
after the UI step wrote the layouts), so a new hit fails the build; verified by a table with an empty monster name (exit 1).

### What it found on the v005 build

91 hits on the previous data: 40 cells per bank (8 potion names, 4 blank bone prison names, 5 monster names, 1 monster type, 14 object names, 1 pet, 6 rune-word cells, 1 unique) and 11 `@key`s in 7 layouts (tooltips Close / Drop Gold / Transmute of the inventory and cube, the Warlock tab titles of the classic skill tree). Fixed: 0 findings now, 0 allowed. (The first version of the audit also hit D2R's own lowercase `fissure` / `orifice` and the blanked guild stones: skipped since, they are D2R's texts.)
The layouts' `@key`s are now D2R's English text written into the layout (`ui_layouts.LITERALS`, `literalize` over every file written; Median
is English only), as #30 and #33 did for the titles.

### Magic affixes with an empty name: Median's design

Every magic prefix and suffix name of the build (747 prefixes + 959 suffixes per bank) is the one key `NoDesc`, which Median's tbl defines
with an empty text (not a missing key: the tbl has it as a real record). Median 2012 shows a magic item with its base name only, so the
affix names stay empty as Median made them; the audit counts them (`designed empty`) and does not report them. Median's strings show nothing
otherwise: no other key in the tbl is used for an affix name in these tables. (The rare / unique prefix and suffix tables have real names.)

## In game (slot 2, `py -3 tools/game_checks.py all textnames`, evidence `mxl2012-runs/text/`)

Character `TextBarb` (deleted afterwards), Rogue Encampment, god mode; monsters spawned one by one and hovered; items spawned into the
inventory (`h item <code> inv`) and hovered. Seen: **Crystal Ball**, **Glass Skull**, **Couatl Inhibitor** and **Landshark Inhibitor** (with the
line "Nearby Monsters are Weakened"), **Bone Prison** (the four blank bone prisons); tooltips **Healing Potion** (`hpo`), **Small Red Potion**
(`rps`), **Elixir of Greater Strength** (`0g3`) and **Elixir of Greater Vitality** (`0g6`) with the lane's first invented lines (replaced by lane elixir: the
name only, see above). 0 engine asserts in the final run (the first run's `ptUnit->eType == UNIT_PLAYER` was the harness spawn of the NecroPet
`crusaders`, bug #19; the check leaves it out). Not seen: Bunny, Injured Barbarian (the hover landed on a Flit next to them), the Dark Nephalem line
(no label for `dark_kid`, probably not selectable: `killable` blank), the Close / Drop Gold tooltips (hover spots guessed), the Warlock tab titles; the
three stat lines cannot be seen on an item because no Median property gives them.

## In game: the Greater Elixirs (lane elixir, slot 2, `py -3 tools/game_checks.py all elixirs`, evidence `mxl2012-runs/elixir/evidence/run3`)

Character `ElixBarb` (stays in `mxl2012-s2`: deleting saves is not allowed to the lane), Rogue Encampment, god mode; each elixir put into the inventory (`h item <code> inv`), hovered (screenshot), right-clicked (the player's own use path), then the item count, the elixir's stat (`passive_*_mastery`) and `states player` compared. `0g3` Strength, `0g4` Dexterity, `0g5` Energy, `0g6` Vitality: the tooltip is the red name and the drop hint only; the use leaves the item (3 -> 3), the stat 0 -> 0, no new state, 0 engine asserts. Control `0g1` Greater Elixir of Greed (state `magpot` exists): tooltip with "+350% Magic Find for 20 seconds", drunk and used up, stat 80 0 -> 350, state 276. Before the `pSpell` 0 cells (first run, `run1-before-fix`) the same four rows asserted `spellState > 0` (`SkillItem.cpp:823`) and were used up. The check is PARTIAL by design: the tooltips are read by hand.

## Not covered

* The other 12 languages read the English text, as the whole port does (Median is English only).
* Text inside strings (a tooltip that names `ModitemXxx` in its own words) is Median's wording and is not parsed.
* In game: the audit proves what the tables ask for, not what D2R draws; the final check list is in docs/testing.md.
