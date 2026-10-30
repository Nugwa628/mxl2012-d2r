# D2R additions since 1.14d and what the port does with them (lane d2radds, 2026-10-28)

Owner decision (2026-10-28): what D2R added (2.4 .. 3.3 "Reign of the Warlock", build 93847) and **conflicts** with Median
XL 2012 is removed. The **Warlock stays playable** but follows Median's rules (level cap, experience, points per level,
difficulty). **Akara's respec stays D2R's.**

Sources: the D2R 93847 baseline (`extract_dir` in the machine-local config, docs/setup.md: `excel/`, `excel/base/`,
`data/hd/global/excel/desecratedzones.json`, `data/local/lng/strings/*.json`), the tables lane's migrated tables
(`mxl2012-wt/tables/work/mod`, built by its `tools/txt_migrate.py`) and `docs/plugin-plan.md` section 9.

How the list was made: every row of the migrated tables (both banks) whose key is not Median's and that is D2R's (not in
the 1.13c view `vanilla113.ROW_COUNTS`), plus every D2R-only column with its values on the migrated rows, plus D2R's
strings for features without table rows (loot filter, Chronicle, stash, ladder, Diablo Clone, auto gold).

## The data step: `tools/d2r_adds.py`

Standalone; input = a migrated mod folder (`--mod`, default `work/mod`), output = `--out` (default: the same folder, in
place), D2R baseline = `--d2r` (default the machine-local config's `extract_dir`, or `MXL_D2R_EXTRACT`). Writes `d2r_adds_report.md` next
to the tables. Every step is idempotent. For `tools/build.py`: one step `["d2r_adds.py"]` after `txt_migrate.py` (and
after anything else that writes charstats / experience / gems / books), before `validate.py`. It **replaces** the
`terror_zones.py` step that the tables lane's draft `build.py` lists (that file is not in the tables lane, and
this step writes the same json plus `max_herald_tiers` 0). Run on the tables lane's current `work/mod` (copy in
`mxl2012-runs/d2radds/out3`): 15 tables + the json changed, nothing else. Tests: `py -3 -m unittest tools.tests.test_d2r_adds`.

| Step | What |
|---|---|
| `terror_zones` | D2R's `desecratedzones.json` with all 12 `ladder_enabled` / `non_ladder_enabled` flags false and `max_herald_tiers` 0 (RotW Hell had 5) -> `data/hd/global/excel/desecratedzones.json` |
| `no_terrorize` | monstats `CannotDesecrate` = `CannotHerald` = 1 on every row; `TreasureClassDesecrated*`, `TreasureClassHerald`, superuniques `TC* Desecrated` emptied (second line of defence if a zone still fires) |
| `ladder` | `firstLadderSeason` / `lastLadderSeason` / `disallowCraftingIn(Non)Ladder` emptied in setitems, uniqueitems, runes, cubemain, treasureclassex (found: Median's 4 Angelical Raiment rows had D2R's seasons 15-16 copied by key) |
| `sunder` | states `sunderfull` / `sunder-res-reduce` emptied (8 cells: D2R's flags on Amplify Damage, Terror, Decrepify, passive_3 rows) |
| `merc_classitems` | hireling `equivalentcharclass` emptied (96 cells: Rogues as Amazon, Barbarians as Barbarian for class items) |
| `dup_codes` | D2R rows appended to keyed tables that repeat a Median item code: gems `Chipped..Perfect Sapphire` (Median spells "Saphire"; both carried gcb..gpb, D2R's vanilla gem mods next to Median's) and books' three Tome rows (Median names its books "unused") - both banks, 16 rows |
| `warlock` | experience: Warlock column = Amazon's (Median curve, MaxLvl 120 instead of 99). charstats Warlock: hpadd, ManaRegen, ToHitFactor, Walk/RunVelocity, RunDrain, Life/Stamina/ManaPerLevel, LifePerVitality, StaminaPerVitality, ManaPerMagic, StatPerLevel, SkillsPerLevel, BlockFactor = Amazon's Median values (D2R's Warlock numbers are D2R's Amazon numbers, so Amazon is the template). Base stats, skills, strings stay D2R's. Starting kit = Median's common kit (cube, 8 hp1, 10 tsc, zen, 600 body armour, 01-) with Median's "Dagger (Grade 1)" `142` in the right hand: D2R's `dgr` is not an item in Median's tables |
| `advanced_stash` | default keep: misc `AdvancedStashStackable` copied from D2R onto the 71 Median rows with D2R's code and type (the migration left it empty, bug #510); `--advanced-stash off` empties it (owner question 2) |

## Feature table

Status: **done** (the step does it), **auto** (gone because Median's tables replace D2R's), **kept** (no conflict, left as
D2R has it), **plugin** (needs plugin work, another lane), **owner** (decision needed), **verify** (in game, later).

| Feature | Where | Conflict with Median 2012 | Decision | How | Status |
|---|---|---|---|---|---|
| Terror Zones (2.5): hourly terrorized zones, +levels/exp/drops, "Corrupted tremors" messages | `data/hd/global/excel/desecratedzones.json` (34 zones, level ids are D2R's and point at Median's re-used levels) | yes: changes monster level, exp, loot | remove | json flags false (`terror_zones`) | done; in-game check `terrorzones` (plugin-plan 10) |
| Terrorized monsters / Herald monsters (3.x, Herald tiers, `heraldtier` stat, `heraldspawner` missiles) | json `max_herald_tiers`, monstats `CannotDesecrate` / `CannotHerald` / TC columns, superuniques TC Desecrated | yes | remove | `terror_zones` + `no_terrorize` | done |
| Terror tokens ("Right Click to terrorize Act N", `terrt`) and manual zones | misc (D2R rows), json `manual_zones` | yes | remove | misc is replaced by Median's (no token item exists); json flags off | auto + done |
| Terror Zone options and /terrorized command, automap "Show Terror Zones" | D2R UI / commands | no (show an empty list with zones off) | keep | - | kept (cosmetic; plugin-plan 9) |
| 2.4 runewords, 2.6 runewords, ladder runewords | runes.txt | yes | remove | runes is a replace table (Median's 3,133 rows only) | auto |
| Ladder-only toggles / season gating | `*LadderSeason*`, `disallowCrafting*` in runes, uniques, sets, cubemain, TC | yes when copied onto Median rows (Angelical Raiment 15-16) | remove | `ladder` | done |
| Ladder seasons / ladder shared stash / previous-season tabs | Battle.net online | no (offline/TCP has no season) | keep | - | kept |
| Sunder Charms (2.6) | uniqueitems, itemtypes `csch` (Crafted Sunder Charm), properties `pierce-immunity-*`, states `sunder*` | yes | remove | uniqueitems replaced (no charm); `csch` itemtype row kept at D2R's type number (no item of that type, indexes stay stable); state flags `sunder` | auto + done |
| New uniques / sets since 1.14d (2.4-3.3, incl. Warlock items) | uniqueitems, setitems, sets | yes | remove | replace tables | auto |
| D2R item rebalances (2.4 set/unique/base changes) | armor, weapons, misc, uniques, sets, affixes, gems | yes | remove | replace tables (Median rows only); gems: D2R's Sapphire rows dropped (`dup_codes`) | auto + done |
| D2R cube recipes (2.4 rune upgrades, socket/reroll recipes, 3.x recipes) | cubemain | yes | remove | replace table (11,477 Median rows) | auto |
| 2.4 class skill balance | skills / skilldesc / missiles rows 0-356 | yes | remove | Median's rows overwrite D2R's at every vanilla skill id | auto |
| 2.4 mercenary changes (A1/A2/A5 skills, auras, stats) | hireling.txt | yes | remove | hireling is replaced (Median's 120 rows) | auto |
| Mercenaries wear class items (Rogue: Amazon, Barbarian: Barbarian) | hireling `equivalentcharclass` | yes (1.13c: no class items on mercs) | remove | `merc_classitems` | done |
| Mercenary resistance columns (`Resist*`, `Resist*/Lvl`) | hireling D2R-only columns, filled by the migration | maybe: D2R moved 1.13c's hardcoded merc resists to the table; values must equal 1.13c | keep if equal | tables lane fills them; compare with 1.13c | verify |
| Difficulty constants moved to the table (PvP %, merc/prime evil %, `MonsterFireEnchantExplosionDamagePercent` 75/50/13, `ResistFloor` -100, ...) | difficultylevels D2R-only columns | maybe (same as 1.13c hardcodes, except possibly FE explosion) | keep, owner may tune | - | verify |
| Warlock class (3.0) | charstats, playerclass, plrtype, experience column, D2R's Warlock skill rows, skilldesc, missiles, overlays, states, pettype `demon`/`binddemon`, monstats goatman / bighead / putrid defiler, itemtypes `warl` `blde` `sppl` `grim` | owner: keep playable | keep, Median rules | rows kept at D2R ids; `warlock` step: level cap 120, Median exp curve, Median per-level / regen / speed constants, Median starting kit | done (data); in-game check later |
| Warlock class items (grimoires, Warlock uniques/sets) | armor/weapons/uniques | yes | remove | replace tables: no `grim` item exists (Warlock off-hand rule `TwoHandedOffHandRestrictItemType grim` has nothing to match) | auto |
| Warlock skill power vs Median monsters | skills.txt (D2R's own numbers), monstats demons | balance: D2R-tuned skills meet Median's 120-level monsters | owner: scale to Median (2026-10-28) | `warlock_scale.py apply` (data/warlock_balance.tsv): damage, summons, mana anchored to Median's skills of the same tier and role; round 2 (`data/warlock_rules.tsv`): Median's skpoints gate, character-level synergy calcs and summon / weapon-skill patterns (docs/warlock-balance.md) | done (data); playtest needs a RotW account |
| Colossal Summit area + Colossal Ancients (RotW, level 137, monstats colossal1-3, colbarb*, objects ColossalAltar / colossal_statue_*, monai Colossal*) | levels row 137, monstats/monstats2/monai/objects rows | yes as content, but unreachable: no level links to 137, entry needs "Uber Ancient Summon Material" (misc rows replaced by Median's, so no material exists) | keep rows (indexed tables, D2R ids hardcoded), unreachable | - | auto (verify no portal opens) |
| Terror token / uber materials stack item types (`terrt`, `uberm`) | itemtypes/misc | yes | remove | not in the migrated tables | auto |
| Colossal Jewel (`cjwl`, Restricted) | itemtypes | yes | remove | no item of the type; type row kept for stable type ids | auto |
| Advanced stash "Materials" stack tab (3.0) | misc `AdvancedStashStackable` (71 Median rows by code and type: runes, gems, rejuvs, Token; bug #510) | storage QoL; Median 2012 has 1 stash page | owner | `--advanced-stash off` | owner (question 2) |
| Shared stash tabs (D2R 1.0) | D2R / D2RLoader `add_shared_tabs` | no (plugin-plan J) | keep | - | kept |
| Loot filter (3.x) | D2R UI | no (display only) | keep | - | kept |
| Chronicle (3.x collection log, cosmetic rewards: portal / footsteps / backlight) | uniques/sets `disableChronicle`, itemtypes `UICategory` / `RunewordCategory1-2`, states chronicle* | no gameplay effect | keep, tracks Median's items (owner 2026-10-28) | `tools/chronicle.py`, see "Chronicle" below | done (data); game check below |
| Auto gold pickup option | D2R option | small QoL; Median 2012 had none | keep | hiding the option = plugin | owner (question 4) |
| Akara respec (Reset Stat/Skill Points once per difficulty) and Token of Absolution | D2R engine, misc `toa` | owner: D2R's | keep | Median's cube rows decide whether a Token can be made | kept |
| Diablo Clone world event (2.x online "Terror gazes upon Sanctuary") | Battle.net | no (online only; `diablocloneweight` empty on every Median row) | keep | - | kept |
| Rite of Passage / D2R hardcoded fixes | engine | no (plugin-plan 9: 1.13c's grant is the same; no hook needed) | keep | - | kept |
| Potion % per class (`HealthPotionPercent`, `ManaPotionPercent`) | charstats | no (1.13c hardcodes, same values) | keep | - | kept |
| Controller skills (Interact, Loot, TownPortal, EmoteWheel, SwapWeapons, Map, ShowItems, RunToggle, CubeLoot "Loot to Cube") | skills / skilldesc D2R ids | no (UI actions) | keep | - | kept |
| D2R-only monsters (horse, pig, seagull, cowking, darkelder, suicideminion9-11) and objects (desert shrines, PlaceUniqueChest, PlaceRandomTreasureChest, PlaceArcaneThingamajig, ControlObject) | monstats / objects rows | no unless placed; Median's levels/presets do not place them | keep rows | - | verify (none seen in game) |
| `EventItem` flag (keys, organs, essences, Token) | misc D2R column, copied by code | no (D2R item handling flag) | keep | - | kept |
| Halls of Vaught `CompletionTotalRoomsOverride` 70 | levels D2R column | no (map completion %) | keep | - | kept |
| Sounds, sound environments, HD ambience | sounds / soundenviron (d2r_wins) | no | keep | - | kept |

## Chronicle (lane qol, `tools/chronicle.py`)

Owner decision 2026-10-28: keep the Chronicle, track Median's uniques, sets, runewords and whatever else fits.

How D2R 93847 builds it. The panel is code (`ChroniclePanel`, `data/global/ui/layouts/chronicle*.json`) with three fixed
tabs, Unique / Sets / Runewords: `tabMessages` name native list panels, so data cannot add a tab. The entries are rows of
`uniqueitems.txt` and `setitems.txt` (`disableChronicle` 1 hides a row; D2R sets it on its unspawnable uniques and the
crafted Sunder charms) and the `complete` rows of `runes.txt` (no per-row switch). The tree on the left is
`itemuicategories.txt` (parent / sub categories; the Name is a string key); an item goes to its base's `UICatOverride`
(armor / weapons / misc) or else its item type's `UICategory`; runewords group by the item types' `RunewordCategory1/2`.
The same categories feed D2R's loot filter (RotW only, not ours to change). There is no other Chronicle json or table in the
CASC data (the json are the six layouts, the rest is sprites, strings and the `chronicle*` states / overlay).

What was wrong. Median's `itemtypes.txt` replaces D2R's and has no category columns, so every Median item type had none (only
D2R's Grimoire and Colossal Jewel rows did), and `disableChronicle` was empty on all 2,479 uniques and 300 set items,
including Median's 443 placeholder rows and its set items whose base item does not exist.

The step (data, after `d2r_adds.py`, both banks where the columns exist, idempotent; report `work/mod/chronicle_report.md`):

| Part | Result (build of 2026-10-28) |
|---|---|
| itemtypes `UICategory` | 177 types filled: D2R's value for D2R's code, else inherited up the Equiv chain (Sacred "Armor (Sacred)" -> Armor, "2h sword" -> Sword, Reward / Challenge charms -> Charm, quivers -> Ammo); by hand: Mega Ring -> Rings, Assassin Naginata -> Assassin, Sorceress Crystal Sword -> Sorceress |
| itemtypes `RunewordCategory1/2` | 147 types, the pair taken from the same type (a sword gets `r_mel` only, not "Weapon"'s `r_mis` + `r_mel`) |
| uniqueitems `disableChronicle` | 2,016 shown; 463 hidden: 457 not spawnable (443 "SkillsdLastSkillEver" placeholders, 14 `enabled` 0), 6 quest items (Viper amulet, Staff of Kings, Horadric Staff, Hell Forge Hammer, Khalim's two flails; D2R lists no quest item either); 0 without a category |
| setitems `disableChronicle` | 196 shown; 103 hidden: vanilla set items whose base Median removed (they never drop); the "Expansion" separator row is left alone |
| runes.txt | 3,080 complete rows for 1,420 names (Median has one row per socket count / base); each row is an entry, nothing to switch |

D2R-only entries: none left, the uniques / sets / runes tables hold only Median's rows (replace rule).

Game check (lane qol, 2026-10-28, slot 2): the data loads (no assert at start, `validate.py` 0 errors) and the harness makes
Median uniques of rows 236 (Queen of Glass), 500 (Snakehair) and 1,500 (Narlant Dream) with no assert or crash file. **The
Chronicle itself could not be opened**: the game slots' Battle.net account does not own Reign of the Warlock, and without it
the Esc menu has no Chronicle (nor Loot Filter) button (D2R uses its non-RotW pause layout; `pause.png` in
`mxl2012-runs/qol/`). Making the button appear by layout would get around a paid-feature gate and was not tried. Still to check
on a RotW account: the Unique tab lists Median's items by category, a found Median unique is recorded (unique rows above
511 included: whether D2R's Chronicle store takes 2,479 unique rows is the open risk), runewords show one entry per row.

Not possible by data: a fourth tab (relics, quest items, trophies), new reward tiers, hiding single runeword rows (`complete`
0 would switch the runeword off). New `itemuicategories.txt` rows (a "Median" sub-category) look possible (a table, Name =
string key) but were not needed: every Median unique and set item fits an existing category.

## Owner questions

1. **Warlock balance**: the Warlock now has Median's level cap, curve, stat/skill points and per-level life/mana, but its
   skills keep D2R's numbers (tuned for 99 levels and vanilla monsters). Keep as is, or scale its skills (another lane)?
   **Decided 2026-10-28: scale** (lane warlock, docs/warlock-balance.md, which has the follow-up questions: skill point gating,
   character-level scaling, the five outliers). **Answered 2026-10-28: "go with what you think is best to match the scaling"**
   (lane warlock2: Median's skpoints gate, synergy calcs and summon / weapon-skill patterns; docs/warlock-balance.md).
   Also: template Amazon (life 25 / mana 15 per level) or a caster template (Necromancer: 20 / 20)?
2. **Materials stack tab** (D2R 3.0): keep (runes/gems stack in a tab, saves stash space) or switch off
   (`--advanced-stash off`)?
3. **Chronicle**: answered 2026-10-28, keep and track Median's items (section "Chronicle").
4. **Auto gold pickup** option: keep (QoL) or hide (plugin)?
5. Starting weapon for the Warlock: Median's "Dagger (Grade 1)" (`142`, in place of D2R's dagger) is the default; any
   other Median weapon?

## For the tables lane

- The keyed merge appends D2R rows whose key differs only in spelling (gems "Sapphire" vs Median's "Saphire", books
  "Tome of ..." vs Median's "unused"). `dup_codes` drops them here; matching gems by `code` and books by row in
  `txt_migrate.py` would avoid them at the source.
- D2R-only columns filled from D2R rows by key on Median rows (setitems ladder seasons, states sunder flags, hireling
  `equivalentcharclass`) are cleared here; the same fill may need a look for other D2R-only columns.

No plugin part is needed: every conflicting addition found is switched off by data (plugin-plan 9 stays "none known").
