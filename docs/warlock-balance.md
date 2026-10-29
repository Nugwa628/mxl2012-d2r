# Warlock balance: D2R's Warlock scaled to Median XL 2012

Round 1: lane `warlock`, owner decision 2026-10-28 (numbers only). Round 2: lane `warlock2`, owner answer 2026-10-28 to the
three open questions: "go with what you think is best to match the scaling; leave anything you can't do for later". Tool
`tools/warlock_scale.py`, data `data/warlock_rules.tsv` (formulas and tooltip lines) and `data/warlock_balance.tsv`
(numbers), build step after `d2r_adds.py` (docs/txt-migrate.md). RotW bank only.

## For the owner: what changed, what needs a playtest

D2R's Warlock (8th class, skills 373-402) keeps all 30 skills, their functions, missiles, states and skill tree. Round 1 moved
257 numbers. Round 2 gives the Warlock Median's own rules where Median applies them to its classes. Every formula is copied
from a Median row, not invented: 366 formula / tooltip cells, and the numbers refitted (305 cells).

### 1. Skill-point gating (Median's `skpoints`)

- All 30 Warlock skills now use Median's class-skill cost, written the way Median's rows write it:
  `((ulvl-T)<((blvl-1-stat('skill_more'.accr))*6))?(stat('newskills'.accr)+1):1`. T is the skill's reqlevel (`ulvl` alone for
  the reqlevel-1 skills, as Median's tier-1 rows). A hard point costs 1 while the skill has at most one hard point per 6
  character levels past its reqlevel (plus Median's `skill_more` stat). Past that it costs more points than the character
  has. A reqlevel-1 Warlock skill now reaches 2 hard points at clvl 1, 3 at clvl 6, 4 at clvl 12, 5 at clvl 21 and 20 at
  clvl 108, as Median's classes do (before: 20 hard points by clvl 21).
- Each skill's tooltip gets Median's line "Base Skill Level (Maximum Level Based on Character Level): x / y" (Median's
  `DescMaxLevel2` line, last free slot of the second block). Its cap is where clvl 120 or the Warlock's maxlvl 20 stops the gate.
- **Not taken:** Median's exclusive-path rules. They are not on all classes: Amazon's devotions and tier-1 picks, the
  Sorceress' and Paladin's tier-1 picks, and the level-90 Ennead / Black Road skills (the Warlock has no level-90 skills).
- maxlvl stays D2R's 20: the gate allows 20 hard points at clvl 108+ for reqlevel 1-6 skills, 22 / 21 on Median's 99-maxlvl rows.

### 2. Character-level scaling (Median's synergy calcs)

- **The 8 spells** (Miasma Bolt, Ring of Fire, Miasma Chains, Blood Boil, Flame Wave, Eldritch Blast, Apocalypse, Abyss) get
  Median's spell synergy, copied from Rain of Fire: `(100 + 20 x clvl) % x (100 + 260 (energy + 10) / (energy + 250)) %`
  (+ Median's hidden `DSK 2` bonus). Blood Boil takes it on both its fire and physical part, as Median's 4 such rows do. They
  also take Median's spell HitShift 4 (the block in 1/16 points: with up to ~5,800 % synergy at clvl 120 whole points are too
  coarse; Median's spells all use 4).
- **The hybrid / weapon skills' own damage** (Hex Bane, Hex Purge, Blade Warp, Echoing Strike, and Mirrored Blades' new
  flat magic part) get Median's `10*ulvl` (+10 % per clvl), the calc of Median's weapon skills' flat part (Ghost Arrow,
  Great Hunt, Barrier Strike, Crucify, ...).
- They replace D2R's per-skill damage synergies (Median's spells have none), and those tooltip lines are gone
  ("+x % Magic Damage per Level"). The spells get Median's two lines instead ("Energy: Adds Fire / Magic Damage
  (Diminishing Returns)", "Current Bonus: x percent"). The Warlock's other synergies stay: damage over time of the miasma
  clouds and Flame Wave, hex duration, echoes, Psychic Ward's absorb, Cleave's damage %. The damage lines (`enma` / `exma`,
  `pnma` / `pxma`) are the game's own synergised values, so they show the new formula.
- The numbers were refitted with `warlock_scale.py fit` on the same reference character (below). Both sides now scale with
  clvl and energy, so a Warlock off the reference curve moves the way a Median class does.

### 3. The outliers

Round 1 counted five and named four: Summon Goatman, Summon Defiler, Cleave, Mirrored Blades. **The fifth is Summon
Tainted** (the open question named "weapon skills and summons", 5 skills: 3 summons, 2 weapon skills; the Tainted's damage fit,
its life was 2-2.5x Median's).

- **Cleave**: D2R's own "Flat Damage" calc (`calc2`, which D2R's function 164 adds to the hit, like Bash's) now holds Median's
  weapon-skill flat part: `(Param13 + (lvl-1) Param14) x (100 + 10 x clvl) %`, tooltip line "Damage: +x". The weapon damage %
  (Param1 / 2) and its synergy % (Param9) were fitted to the comparables' weapon share. Time to kill: 0.55-1.56 -> 0.59-1.17.
- **Mirrored Blades**: Median's pattern of Great Hunt / Bladestorm: flat magic damage (EType `mag`, a block seeded with
  Bladestorm's 4s) x `10*ulvl`. D2R's function 166 adds the skill's elemental block (Blade Warp's whole damage is that block on
  the same function). Tooltip line "Magic Damage: x-y". The damage % per duplicate (dm12) is fitted to the weapon share.
  0.47-1.88 -> 0.94-1.17.
- **The demons**: Median's summon pattern. Life and damage come from the skill, not from the monster:
  - base life 1 and attack 1-6 on every difficulty (as `shadows_new`, `lamias`, `veilkings`); D2R's life % per level
    (Param1) 0;
  - life: a `maxhp` passive `((Param15 + (lvl-1) Param16) x 256) x (100 + clvl / 2) %`: Median's Summon Shadows / Lamia /
    Veil King formula. Tooltip: Median's "Life: x hit points" `((1 + passive / 256) x (100 + clc1)) / 100`;
  - flat damage: Median's `min(edmx,2000)` (Goatman, replacing D2R's linear `ln34`) / `min(edmx,4000)` (Defiler, new
    `item_normaldamage` passive) on a typeless block of the skill row, seeded with Guardian Spirit's / Veil King's. The
    Defiler's tooltip gets "Damage: x-y" (Median's `(1-6 + flat) x damage %`);
  - Blood Oath's demon life % (Param5 / 6, read only by the demons' life calc) fitted on all three demons at once: 50 + 35 %
    per level -> 189 + 19 %;
  - the Tainted's damage is its Tainted Fire Ball (refitted as in round 1).
  - Result: the demons no longer depend on their monster level for life and damage (see "later"). Goatman 0.73-2.19 ->
    0.73-1.65, Defiler 0.55-2.87 -> 0.80-1.83, Tainted 0.82-1.23 (unchanged, in range).
- **Abyss**' damage-over-time centre missile (`abysscenter`) keeps D2R's synergy calc (missile calcs have no `ulvl` or energy).
  Its block is now fitted on its own, to the skill row's new damage, instead of copying the row's block.

### Left for later (docs/unported.md)

1. **The demons' pack size** steps with Demonic Mastery (1 / 2 / 3 demons at its blvl 1 / 5 / 10), a D2R mechanic; Median's
   summons grow their count with their own level. Where the pack is one demon and Median's single Veil King keeps growing
   (Defiler slvl 5-8, clvl 30-40) the Warlock kills 1.5-1.8x slower. Goatman slvl 7 (clvl 20) 1.65x slower. Fixing it means changing Demonic
   Mastery's petmax rule; the owner can decide that after a playtest.
2. **The demons' monster level** is set by D2R's summon function 56, hard-coded (Median's summons use function 119 with
   `calc2 = ulvl`). With Median's base 1 life / 1-6 attack it now moves only the demons' defence, attack rating and the small
   base part. Not portable with data.
3. **Missile calcs have no character level / energy** (D2R's misscalc codes): the damage-over-time missiles (miasma clouds,
   Flame Wave's ground fire, `abysscenter`) keep D2R's skill-level synergies. Their numbers follow the reference character.
4. **Mirrored Blades' and Cleave's flat part rides on D2R's functions 166 / 164.** Function 166 adds the elemental block
   (Blade Warp). Function 164's `calc2` is D2R's own "Flat Damage" (as Bash's). Neither is seen in game: playtest check 1.
5. Kept from round 1 (no same-stat Median skill): Psychic Ward's absorb, Sigil Lethargy's -50 % attack speed, Hex Siphon's
   -33 % enemy damage, Sigil Rancor / Death percentages.

### Playtest checks once an account with Reign of the Warlock exists

No game run was possible here (the game accounts don't own Reign of the Warlock).

1. **Flat damage on the weapon skills:** Cleave's tooltip "Damage: +x" and Mirrored Blades' "Magic Damage: x-y". Does a hit
   deal them (Cleave: compare a hit with the skill against a normal attack; Mirrored Blades: magic damage numbers on the
   duplicates)? The flat part is most of Cleave's damage (316 of 428 per hit at slvl 20, 1,274 of 1,423 at slvl 40): if D2R's
   function 164 ignores `calc2`, Cleave is 4x too weak at slvl 20 and 10x at slvl 40. Report it; the fallback is to put the
   flat part into the weapon damage % (numbers only).
2. **Skill-point gate:** a new Warlock at clvl 1-12. A reqlevel-1 skill takes its 2nd hard point at clvl 1, refuses the 3rd
   before clvl 6 and the 4th before clvl 12 (the + button gives no point). The "Base Skill Level (Maximum ...)" line reads x / y with the right y. A `+skill_more` item
   (Median's) raises it by 1.
3. **Spell tooltips:** Miasma Bolt, Ring of Fire, Abyss at a few clvls and energy values: the damage line grows with clvl and
   energy. The "Energy: Adds Magic Damage" / "Current Bonus: x percent" lines read in words. No "+x % per level" line names a
   skill that no longer gives it.
4. **Demons:** Summon Goatman / Tainted / Defiler at clvl 20 / 60 / 100. The tooltip "Life: x hit points" against the demon's
   real life (the monster's life bar / hover). Life spawns full (D2R's function 56 adds the `maxhp` passive). The Defiler's
   "Damage: x-y" against its hits. Blood Oath's "Demon Life +x %" line.
5. **Time to kill** against the table below at two or three area levels, for one spell, one hex, one weapon skill and a demon pack.
6. From round 1, still open: mana (sigils 130-170 per cast), Psychic Ward's absorb, Sigil Lethargy / Hex Siphon percentages.

## Method

1. **Classification.** The 30 rows of D2R 93847's skills.txt / skilldesc.txt (`tools/warlock_scale.py` `SPECS`): tier = reqlevel
   (1 / 6 / 12 / 18 / 24 as in Median; the Warlock's 30 maps to Median's top regular tier 24 for the comparison, while its
   skpoints gate counts from 30), role (damage, weapon, summon, buff, curse, passive, utility) and element.
2. **Rules** (`rule_cells`, round 2): on D2R's rows the fit first writes Median's formulas listed above, copied from Median's
   own rows read in the same tables (Rain of Fire's synergy, HitShift and energy lines; Median's max-level line). The cells
   are listed in `data/warlock_rules.tsv`.
3. **Comparables.** 2-3 Median 2012 class skills of the same tier and role, the same element first (the per-skill table).
   Buffs and curses are compared stat by stat with Median skills granting the same stat, any tier.
4. **Measures** (`warlock_scale.py`, its own D2 calc evaluator over the migrated tables): average damage per hit of the
   skill's damage source (the skill row, or the first missile with damage: Median keeps many skills' damage on missiles),
   with the EMin / EMax level brackets (2-8, 9-16, 17-22, 23-28, 29+), HitShift, poison length and the synergy calc
   (EDmgSymPerCalc / DmgSymPerCalc); weapon share (SrcDam) of a reference weapon, with a Warlock weapon skill's damage %
   on the whole hit (weapon, flat calc, own block); mana cost per level (manashift); the casting delay; summons: one minion's
   life ((monstats life x monlvl L-HP + flat maxhp passive) x (100 + clc1) %, Median's own tooltip formula) and pack damage
   (A1 x L-DM or the demon's spell, + flat damage passive, x damage % passives, x petmax); buffs / curses: the stat's value
   from aurastatcalc / passivecalc.
5. **Fit**, slvl 1-40, on the log ratio to the median of the comparables (x casting delay / 13 frames for delayed skills):
   - elemental / physical blocks: the six bracket positions are scaled (min and max alike, D2R's min / max shape kept) by
     least squares with a smoothness term, then rounded; a missile copy of a block (`abysscenter`) is fitted on its own to the
     row's damage;
   - weapon skills: first the weapon damage % Params to the comparables' weapon share, then the flat part (Cleave's Params
     13 / 14, Mirrored Blades' block) to the rest;
   - Params (weapon / summon damage %, summon life, flat damage, Death Mark, Engorge): only Params a calc reads (the tool
     refuses any other: D2R's do functions read some Params directly as radius, count or timing, and those are mechanics);
   - summon flat damage blocks (six positions, min and max together) with the damage % Params, by pattern search;
     Blood Oath's demon life % on the three demons' life curves at once, then each demon's life Params again (two rounds);
   - mana / lvlmana: linear least squares on the comparables' cost (Median's own buffs or curses for buffs, sigils and
     hexes).
6. **Sanity check** (`warlock_scale.py ttk`): per area level 10-120, the time to kill an average Median monster (median base
   life of the regular monsters x monlvl L-HP, normal / nightmare / hell), Warlock vs the median comparable; ratios beyond
   +-25 % are flagged (below).
7. validate.py: 0 errors in both banks (plugin 170, warnings 13: unchanged); text audit 0 findings; unit tests
   `tools/tests/test_warlock_scale.py` (round 1) and `tools/tests/test_warlock_rules.py` (round 2).

### Reference character (the same for the Warlock and Median's classes)

| Item | Model |
|---|---|
| Character level at slvl s, tier T | u = min(120, T + 3 (s - 1)): half the skill levels from hard points (Median's gate: one per 6 levels, which the Warlock now has too), half from +skills |
| Hard points | h = 1 + (s - 1) // 2; every synergy source skill at blvl h (same class only) |
| Energy | 20 + 2 (u - 1) (2 of 5 stat points per level); strength / dexterity 20 + 1.5 (u - 1); no item stats |
| Weapon | 75th percentile of Median's weapon bases' average damage (best of one / two hands) a level-u character can use |
| Cast rate | one cast per 13 frames, or the casting delay when longer; one target, no resistances |
| Summons | monster level u (Median's summons: `calc2 = ulvl`; with base life 1 / attack 1-6 it matters little now) |

## Per-skill table (slvl 1 / 20 / 40)

Damage = average per hit or cast incl. synergy for the reference character; "(flat part)" = the flat elemental damage a hex
adds to the attack, against the comparables' flat part (the weapon share is the same on both sides). D2R = D2R's own
Warlock (before both rounds). Median target = median of the comparables (x the casting delay factor). Stat rows: absolute
values. Cells = number cells changed for the skill (the rule cells are in `data/warlock_rules.tsv`). The full curves
(slvl 1 / 10 / 20 / 30 / 40) and each comparable's own values: `py -3 -I tools/warlock_scale.py fit` ->
`work/warlock/fit_report.md`.

| Skill | Tier | Role | Comparables | Measure | D2R | Median target | New | Cells |
|---|---|---|---|---|---|---|---|---|
| Summon Goatman | 1 | summon phys | Summon Shadows, Guardian Spirit, Wolf Companion | minion life | 63 / 86254 / 683971 | 11 / 633 / 2624 | 24 / 605 / 3216 | 31 |
| | | | | pack damage | 1.2 / 669 / 2516 | 4.0 / 445 / 1025 | 4.5 / 523 / 1347 |  |
| | | | | mana | 15 / 24 / 34 | 10 / 74 / 144 | 7.5 / 74 / 144 |  |
| Demonic Mastery | 1 | passive | - | - | | | kept | 0 |
| Death Mark | 6 | curse | Doom; mana: Median's curses | normal_damage_reduction | 5.0 / 43 / 83 | 15 / 300 / 600 | 15 / 300 / 600 | 4 |
| | | | | mana | 2.2 / 7.0 / 12 | 120 / 160 / 160 | 134 / 152 / 172 |  |
| Summon Tainted | 12 | summon fire | Summon Lamia, Protector Spirit, Summon Rampagor | minion life | 869 / 154202 / 898197 | 102 / 1488 / 3524 | 218 / 1282 / 4276 | 23 |
| | | | | pack damage | 7.2 / 1220 / 9532 | 8.9 / 617 / 2006 | 10 / 742 / 2242 |  |
| | | | | mana | 25 / 34 / 44 | 40 / 230 / 430 | 40 / 230 / 430 |  |
| Summon Defiler | 18 | summon phys | Summon Veil King, Summon Lamia, Summon Void Archon | minion life | 1457 / 200425 / 990138 | 224 / 1671 / 3684 | 297 / 1582 / 4622 | 30 |
| | | | | pack damage | 26 / 1633 / 5245 | 240 / 1387 / 2653 | 252 / 1736 / 2968 |  |
| | | | | mana | 35 / 44 / 54 | 200 / 675 / 1175 | 200 / 675 / 1175 |  |
| Blood Oath | 6 | passive | - | - | | | demon life % fitted with the demons | 2 |
| Engorge | 24 | buff | Eagle Stance, FamineX, Rapture, Wolf Stance, Ancient Blood; mana: Median's buffs | lifedrainmindam | 15 / 53 / 93 | 3.5 / 15 / 28 | 2.0 / 21 / 41 | 4 |
| | | | | attackrate (kept) | 15 / 34 / 35 | 10 / 34 / 48 | 15 / 34 / 35 |  |
| | | | | mana | 3.0 / 7.8 / 13 | 60 / 60 / 102 | 50 / 69 / 89 |  |
| Blood Boil | 18 | damage fire | Rain of Fire, Blood Thorns, Fireball Sentry | damage | 36 / 1356 / 6820 | 38 / 643 / 1763 | 33 / 640 / 1766 | 22 |
| | | | | mana | 3.8 / 8.5 / 14 | 32 / 108 / 188 | 32 / 108 / 188 |  |
| Consume | 24 | utility | Bacchanalia, Ancient Blood, Embalming, Ice Queen; mana: Median's buffs | item_maxhp_percent (kept) | 5.0 / 24 / 44 | 10 / 30 / 50 | 5.0 / 24 / 44 | 1 |
| | | | | mana | 25 / 44 / 64 | 60 / 60 / 102 | 50 / 69 / 89 |  |
| Bind Demon | 24 | utility | - | - | | | kept | 0 |
| Levitate | 1 | passive | Elfin Arrows | passive_mastery_melee_dmg (kept) | 25 / 101 / 181 | 45 / 270 / 520 | 25 / 101 / 181 | 0 |
| Eldritch Blast | 24 | damage mag | Rising Dawn, Freezing Gale, Lava Pit | damage | 8.0 / 1199 / 8841 | 92 / 1136 / 2792 | 79 / 1157 / 2892 | 14 |
| | | | | mana | 5.5 / 15 / 25 | 30 / 125 / 225 | 30 / 125 / 225 |  |
| Hex Bane | 1 | damage mag | Ghost Arrow, Moonbeam, Laughing Ghost | damage (flat part) | 13 / 877 / 5638 | 6.6 / 816 / 3072 | 8.2 / 818 / 3114 | 12 |
| | | | | skill_armor_percent (kept) | 30 / 49 / 50 | 100 / 100 / 100 | 30 / 49 / 50 |  |
| | | | | item_tohit_percent (kept) | 25 / 25 / 25 | 62 / 62 / 62 | 25 / 25 / 25 |  |
| | | | | mana | 6.0 / 16 / 26 | 5.0 / 5.0 / 5.0 | 5.0 / 5.0 / 5.0 |  |
| Hex Siphon | 24 | utility | Miasma, Colosseum, Screaming Eagle; mana: Median's curses | damagepercent (kept) | 33 / 33 / 33 | 10 / 25 / 25 | 33 / 33 / 33 | 2 |
| | | | | mana | 12 / 22 / 32 | 120 / 160 / 160 | 134 / 152 / 172 |  |
| Psychic Ward | 18 | buff | -; mana: Median's buffs | mana | 20 / 58 / 98 | 60 / 60 / 102 | 50 / 69 / 89 | 2 |
| Echoing Strike | 12 | weapon phys | Enfilade, Rebound, Spore Shot | damage | 40 / 284 / 842 | 49 / 846 / 2656 | 49 / 865 / 2707 | 10 |
| | | | | mana | 7.0 / 16 / 26 | 30 / 21 / 20 | 30 / 21 / 11 |  |
| Hex Purge | 12 | damage mag | Rebound, Spore Shot, Egg Trap | damage (flat part) | 15 / 490 / 2518 | 11 / 790 / 2600 | 13 / 786 / 2658 | 13 |
| | | | | mana | 25 / 44 / 64 | 40 / 30 / 30 | 35 / 35 / 35 |  |
| Blade Warp | 18 | damage mag | Barrier Strike, Dragon Shot, ParasiteSkill | damage | 13 / 592 / 2777 | 82 / 1422 / 4115 | 83 / 1475 / 4102 | 11 |
| | | | | mana | 15 / 15 / 15 | 20 / 20 / 20 | 20 / 20 / 20 |  |
| Cleave | 6 | weapon phys | Stampede, Hyena Strike, Crucify | damage | 34 / 384 / 682 | 34 / 487 / 1609 | 40 / 428 / 1423 | 6 |
| | | | | mana | 3.0 / 3.0 / 3.0 | 20 / 25 / 25 | 21 / 21 / 21 |  |
| Mirrored Blades | 24 | weapon phys | Great Hunt, Bladestorm, Stormblast | damage | 60 / 406 / 432 | 43 / 765 / 2117 | 45 / 744 / 2110 | 16 |
| | | | | mana | 5.0 / 14 / 24 | 50 / 30 / 30 | 34 / 34 / 34 |  |
| Sigil Lethargy | 6 | curse | Miasma, Colosseum, Screaming Eagle, Shower of Rocks; mana: Median's curses | velocitypercent (kept) | 50 / 50 / 50 | 45 / 50 / 56 | 50 / 50 / 50 | 2 |
| | | | | attackrate (kept) | 50 / 50 / 50 | 18 / 18 / 18 | 50 / 50 / 50 |  |
| | | | | item_armor_percent (kept) | 33 / 52 / 72 | 100 / 100 / 100 | 33 / 52 / 72 |  |
| | | | | mana | 4.0 / 4.0 / 4.0 | 120 / 160 / 160 | 133 / 152 / 172 |  |
| Ring of Fire | 6 | damage fire | Hunting Banshee, Thunderstone, Frigid Sphere | damage | 9.6 / 490 / 2092 | 10 / 492 / 1733 | 9.2 / 504 / 1748 | 14 |
| | | | | mana | 8.0 / 18 / 28 | 12 / 88 / 168 | 12 / 88 / 168 |  |
| Miasma Bolt | 1 | damage mag | Magic Missiles, Searing Light, Forked Lightning Sor | damage | 1.8 / 70 / 338 | 5.0 / 605 / 2358 | 4.9 / 605 / 2405 | 14 |
| | | | | mana | 2.0 / 12 / 22 | 5.0 / 52 / 102 | 5.0 / 52 / 102 |  |
| Sigil Rancor | 12 | curse | -; mana: Median's curses | mana | 12 / 12 / 12 | 120 / 160 / 160 | 133 / 152 / 172 | 2 |
| Enhanced Entropy | 24 | passive | - | - | | | kept | 0 |
| Flame Wave | 18 | damage fire | Rain of Fire, Blood Thorns, Fireball Sentry | damage | 20 / 994 / 4630 | 43 / 741 / 2034 | 39 / 770 / 2068 | 14 |
| | | | | mana | 7.0 / 16 / 26 | 32 / 108 / 188 | 32 / 108 / 188 |  |
| Miasma Chains | 12 | damage mag | Tempest, Flamestrike, Better Bloodstorm | damage | 9.0 / 172 / 678 | 17 / 453 / 1400 | 18 / 462 / 1416 | 14 |
| | | | | mana | 4.5 / 14 / 24 | 20 / 115 / 215 | 20 / 115 / 215 |  |
| Sigil Death | 24 | curse fire | -; mana: Median's curses | mana | 10 / 20 / 30 | 120 / 160 / 160 | 134 / 152 / 172 | 2 |
| Apocalypse | 24 | damage fire | Lava Pit, Rising Dawn, Freezing Gale | damage | 108 / 2790 / 14220 | 317 / 3933 / 9665 | 319 / 4026 / 9941 | 14 |
| | | | | mana | 32 / 51 / 71 | 30 / 125 / 225 | 30 / 125 / 225 |  |
| Abyss | 24 | damage mag | Rising Dawn, Lava Pit, Freezing Gale | damage | 36 / 458 / 2338 | 211 / 2622 / 6443 | 241 / 2640 / 6666 | 26 |
| | | | | mana | 23 / 42 / 62 | 30 / 125 / 225 | 30 / 125 / 225 |  |

### Why these comparables

| Skill | Reason |
|---|---|
| Summon Goatman | tier 1 melee summons (Necromancer Shadows, Barbarian Guardian Spirit and Wolf Companion) |
| Summon Tainted | tier 12 summons (Lamia, Protector Spirit); Median has two, so tier 6 Rampagor is the third |
| Summon Defiler | tier 18 Veil King, with the tier 12 / 24 summons (Lamia, Void Archon) around it |
| Death Mark | the mark makes the target take flat extra physical / magic damage (negative damage reduction); Doom is Median's skill with that stat |
| Engorge | demon buff: life steal against Median's life-steal skills (Eagle Stance, FamineX), attack speed against Median's attack-speed buffs |
| Blood Boil, Flame Wave | tier 18 fire area spells (Rain of Fire, Blood Thorns, Fireball Sentry) |
| Consume | life % against Median's life % passives / buffs |
| Eldritch Blast, Apocalypse, Abyss | tier 24 area spells (Rising Dawn magic, Lava Pit fire, Freezing Gale cold); the Warlock's reqlevel 30 is Median's top regular tier |
| Hex Bane | tier 1 skills that put flat magic damage on the attack (Ghost Arrow, Moonbeam, Laughing Ghost: their flat part) |
| Hex Purge | tier 12 skills with a flat magic / fire part (Rebound, Spore Shot, Egg Trap), like the hex's explosion |
| Hex Siphon, Sigil Lethargy | enemy debuffs against Median's debuffs with the same stats (Miasma, Colosseum, Screaming Eagle, Shower of Rocks) |
| Echoing Strike | tier 12 weapon projectiles with flat damage on top (Enfilade, Rebound, Spore Shot) |
| Blade Warp | tier 18 magic weapon skills (Barrier Strike, Dragon Shot, ParasiteSkill); the Warlock's is magic only, no weapon share |
| Cleave | tier 6 melee / weapon skills (Stampede, Hyena Strike, Crucify) |
| Mirrored Blades | tier 24 weapon skills (Great Hunt, Bladestorm, Stormblast) |
| Ring of Fire | tier 6 area spells (Hunting Banshee, Thunderstone, Frigid Sphere); Ring of Light, the fire one, hits many small ticks and has no per-hit match |
| Miasma Bolt | tier 1 bolt spells (Magic Missiles, Searing Light, Forked Lightning) |
| Miasma Chains | tier 12 spells (Tempest's chain lightning first, Flamestrike, Better Bloodstorm) |
| Levitate | Median's only mastery with the same stat (Elfin Arrows) is tier 18: compared, kept |
| Sigil Rancor, Sigil Death, Psychic Ward | no Median skill enrages monsters, executes by life % or absorbs a damage amount: numbers kept, mana from Median's curses / buffs |
| Demonic Mastery, Blood Oath, Enhanced Entropy | passives whose numbers feed the summons / miasma calcs: kept, judged through the skills they feed; Blood Oath's demon life % (read only by the demons' life calc) is fitted with the three demons' life (round 2) |
| Bind Demon | channel skill (mana per frame): kept |

## Time to kill (round 2; ratio Warlock / median comparable, area levels 10-120)

`py -3 -I tools/warlock_scale.py ttk` -> `work/warlock/ttk_report.md` (per area level and difficulty). Ratio > 1: the Warlock
kills slower. Hell TTK in seconds (Warlock / median comparable) of an average Median monster, one target, one skill, no items,
at area level 30 / 60 / 90 / 120 (slvl from the reference character).

| Skill | Ratio range (round 1) | Ratio range (round 2) | Flagged | Flagged areas (ratio) | Hell TTK s at 30 / 60 / 90 / 120 |
|---|---|---|---|---|---|
| Summon Goatman | 0.73 - 2.19 | 0.73 - 1.65 | 4 / 12 | 20 (1.65), 40 (1.27), 50 (1.28), 110 (0.73) | 321/271, 107/126, 63/80, 42/55 |
| Summon Tainted | 0.82 - 1.23 | 0.82 - 1.23 | 0 / 11 | - | 807/654, 143/130, 45/44, 28/29 |
| Summon Defiler | 0.55 - 2.87 | 0.80 - 1.83 | 2 / 11 | 30 (1.52), 40 (1.83) | 177/116, 57/52, 27/33, 21/24 |
| Cleave | 0.55 - 1.56 | 0.59 - 1.17 | 1 / 12 | 10 (0.59) | 308/355, 139/125, 71/61, 40/36 |
| Mirrored Blades | 0.47 - 1.88 | 0.94 - 1.17 | 0 / 10 | - | 691/656, 153/139, 58/58, 32/32 |
| Blood Boil | 0.92 - 1.13 | 1.00 - 1.13 | 0 / 11 | - | 514/494, 131/131, 62/61, 35/35 |
| Eldritch Blast | | 0.97 - 1.11 | 0 / 10 | - | 402/364, 86/86, 39/40, 22/23 |
| Hex Bane | | 0.99 - 1.08 | 0 / 12 | - | 257/245, 68/69, 32/32, 18/18 |
| Echoing Strike | | 0.97 - 1.03 | 0 / 11 | - | 280/273, 86/86, 39/40, 22/23 |
| Hex Purge | | 0.98 - 1.06 | 0 / 11 | - | 424/399, 93/94, 42/41, 23/23 |
| Blade Warp | | 0.96 - 1.08 | 0 / 11 | - | 350/323, 91/93, 41/42, 24/24 |
| Ring of Fire | | 0.98 - 1.07 | 0 / 12 | - | 408/400, 121/124, 57/58, 33/33 |
| Miasma Bolt | | 0.98 - 1.03 | 0 / 12 | - | 322/312, 92/92, 42/42, 23/24 |
| Flame Wave | | 0.96 - 1.11 | 0 / 11 | - | 518/494, 128/131, 59/61, 34/35 |
| Miasma Chains | | 0.98 - 1.07 | 0 / 11 | - | 579/540, 156/159, 73/75, 42/42 |
| Apocalypse | | 0.97 - 1.07 | 0 / 10 | - | 375/364, 87/86, 39/40, 22/23 |
| Abyss | | 0.97 - 1.10 | 0 / 10 | - | 354/364, 89/86, 40/40, 22/23 |

Round 1's 12 damage skills were 0.92 - 1.13 together. Round 2: 7 flagged areas in all (round 1: 31), all on the demons
(pack size, "Left for later" 1) and Cleave at area 10 (slvl 2: the Warlock kills faster; the flat part's smallest
step, 1 point per level, is already a large share at that level).

## Assumptions and limits

- Comparisons are per hit / cast for one target. Area, projectile count, pierce, chain count and DoT ticks are each skill's
  mechanics and were not weighed (Ring of Light, Median's tier 6 fire ring, was left out as a comparable for that reason).
- The pack size uses the skill's petmax (Warlock: 3 demons from Demonic Mastery 10; Median: up to 15 Shadows).
- Elemental masteries, item stats (+% damage, +skills beyond the model) and resistances are 0 on both sides; Median's
  hidden helper skill `DSK 2` (in the spell synergy and its "Current Bonus" line) counts 0.
- `stat('energy')` and the other stats come from the reference character.
- D2R's Warlock rows are D2R's own (ids 373-402) and keep D2R's maxlvl 20 (Median's are 99 but gated to about 20 hard points
  by clvl 120; the Warlock now has the same gate).
- A Warlock weapon skill's damage % multiplies the flat part too (as D2's skill damage % does for a skill's own flat damage);
  not seen in game.

## Data step

`tools/build.py` runs `warlock_scale.py apply --mod work/mod` after `d2r_adds.py`. It writes `data/warlock_rules.tsv`
(formulas / tooltip lines: skills `skpoints`, synergy calcs, HitShift, `calc2`, EType, passives; skilldesc lines), then
`data/warlock_balance.tsv` (numbers: skills, missiles `abysscenter`, monstats `wargoatman` / `warbighead` /
`warputriddefiler`). Both files have the same columns: skill, table, row, column, value before (D2R's, or empty for a new
cell), new value. The RotW bank only: a cell there that holds neither the value before nor the new one stops the step (D2R
or the migration changed the row: refit). The Classic / LoD bank's Warlock rows are id placeholders and are not written. To
refit after a change to Median's or D2R's tables: `py -3 -I tools/warlock_scale.py fit` (it reverts both files' cells, so it
can run on a built work/mod and gives the same files again), review `git diff data/warlock_*.tsv` and
`work/warlock/fit_report.md`, then `ttk`.
