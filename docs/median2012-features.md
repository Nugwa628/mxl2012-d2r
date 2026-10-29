# Median XL 2012 v005: player features and test checklist

This is a research baseline for the port, not a claim that the port already works. The local source is the read-only D2SE/D2GL repack's `documentation/README.rtf` (README) and `documentation/Documentation.txt`; the latter points to the original documentation site and forum. Recheck repack-derived claims against the original v005 release when available. Brother Laz's legacy pages are contemporaneous but may reflect different revisions: exact numbers and individual mechanics require v005 confirmation. Modern Sigma and Ultimative documentation is not a v005 specification.

## Classes and skills

The README says each of the seven classes has 30 new skills: 25 main, three uberskills and two challenge rewards, or 210 in total. These are skill counts, not counts of UI tabs or confirmed individually named trees. [README; [legacy introduction](https://modsbylaz.vn.cz/introduction.html)]

| Class | Documented skill paths or play styles | Source |
| --- | --- | --- |
| Amazon | Bow, spear, javelin and blood trees; summoning. The level-18 devotion skills in those four trees are mutually exclusive. | [Amazon](https://modsbylaz.vn.cz/amazon.html); README |
| Assassin | Melee, throwing knives, mechanical bombs and weapon systems; psionic skills. | [Assassin](https://modsbylaz.vn.cz/assassin.html); [v005 changes](https://www.moddb.com/downloads/median-xl-2012-v005) |
| Barbarian | Melee, throwing and ancestral spirits. | [Barbarian](https://modsbylaz.vn.cz/barbarian.html) |
| Druid | Bow, shapeshifting, nature magic and summons. | [Druid](https://modsbylaz.vn.cz/druid.html); [v005 changes](https://www.moddb.com/downloads/median-xl-2012-v005) |
| Necromancer | Summons, totems, melee and crossbows. | [Necromancer](https://modsbylaz.vn.cz/necromancer.html) |
| Paladin | Holy and unholy paths, melee and spells. | [Paladin](https://modsbylaz.vn.cz/paladin.html) |
| Sorceress | Elemental spells and melee wards; specialization limits study to two elements. | [Sorceress](https://modsbylaz.vn.cz/sorceress.html) |

The full in-game tab names, complete tree names and per-tree skill counts are **unverified**; the play styles above are not asserted to be the exact UI tree labels. Use the class pages and v005 data to resolve them before treating a tree-by-tree inventory as complete.

## Items and progression

- Six tiers of base equipment plus Sacred items, class-specific equipment, new gems and runes, improved magic and rare affixes, unique and set items are described in the README. It advertises 710 uniques, 29 sets and 332 runewords; the older [introduction](https://modsbylaz.vn.cz/introduction.html) says 475, 28 and 310 respectively. The specific [runeword list](https://modsbylaz.vn.cz/runewords.html) says 332. Treat all catalogue totals as provisional rather than acceptance counts. [README]
- Runewords use a nonmagical grey socketed base: fill preceding sockets with jewels and put the single required rune last. For example Dawn uses El in a weapon, with zero to five preceding jewels. [Runewords](https://modsbylaz.vn.cz/runewords.html)
- Cube systems include crafting points, vendor reagents, shrine crafting and blessing, jewelcrafting, Mystic Orbs and honorific equipment. Disenchant a unique or set with Catalyst of Disenchantment for shards while retaining the catalyst; five Arcane Shards make an Arcane Crystal. Two identical gems make the next quality. A non-sacred item plus Oil of Enhancement and two crystals rerolls as a unique. These recipes consume or change items: use expendable test items. [Cube recipes](https://modsbylaz.vn.cz/cube.html); [README]
- Charms grant bonuses while carried. Many Destruction uber bosses have a 2% trophy drop; cube the matching trophy with its charm once for an extra bonus. Kurast 3000 BA has one class charm for each class. The cited 2012-era sources establish trophies, but do not establish a separate player item category called relics; verify before adding one. [Cube recipes](https://modsbylaz.vn.cz/cube.html); [Level Challenge 2](https://modsbylaz.vn.cz/levelchallenge2.html)

## Quests, monsters and rules

- The README advertises 30 uberquests, described as 22 bosses plus eight special levels; the legacy [bestiary](https://modsbylaz.vn.cz/monsters.html) says 25. Counts are unresolved. Examples include Creature of Flame in Ancient Tunnels (Lost City), Azmodan in Forgotten Reliquary (Upper Kurast), and Kurast 3000 BA via Arachnid Lair (Spider Forest). Destruction rewards include unique charms. [README; [dungeons](https://modsbylaz.vn.cz/dungeonubers.html); [uberlevels](https://modsbylaz.vn.cz/levelubers.html)]
- For summoning quests, cube three Sacrifical Hearts and three Meditation Candles to make a reusable Book of Summoning, select its skill and cast at the correct location. The Butcher is summoned in The Hole Level 2, Black Marsh. [Summoning](https://modsbylaz.vn.cz/summoningubers.html)
- Level Challenge 2 requires killing Tal Rasha in Binding of Baal on Terror at level 90 or below, then cubing the class charm with a perfect gem within 30 seconds of the kill. The Black Road challenge has five trials, including a carried-gold requirement of 666,666 for Trial of Greed. [Level Challenge 2](https://modsbylaz.vn.cz/levelchallenge2.html); [Black Road](https://modsbylaz.vn.cz/blackroad.html)
- Monsters have new attacks and behavior, including homing quill rat spikes; elites, veterans and heroic enemies have improved stats and attacks. Uber encounters can have special invulnerability mechanics. [README; [monsters](https://modsbylaz.vn.cz/monsters.html)]
- Difficulties are named Hatred, Terror and Destruction in the legacy quest documentation. The Belladonna Elixir recipe is Oil of Absolution plus a rune; the original documentation says its respec works only with LoD 1.13, so D2R behavior needs separate verification. Gold is used for vendors and the Black Road carried-gold trial; exact caps and death penalties are unverified. [Summoning](https://modsbylaz.vn.cz/summoningubers.html); [cube](https://modsbylaz.vn.cz/cube.html); [Black Road](https://modsbylaz.vn.cz/blackroad.html)
- **Inventory, stash and cube grid dimensions, stash pages and gold limits: unknown for original v005.** The repack may contain third-party additions, so do not use its apparent storage layout as proof of the original. The README says PlugY does not come with Median XL. [README]

## v005 changes relative to v004

Brother Laz calls v005 a small balance and bugfix patch with a new druid bow skill. The [v005 release notes](https://www.moddb.com/downloads/median-xl-2012-v005) are the detailed source for the following representative changes; consult them for the full skill-by-skill list:

- Druid Laughing Ghost replaces Blindside; Cascade starts at nine targets rather than six, and Acid Fiends gain 33% damage avoidance.
- Amazon Ghost Arrow gains an extra arrow every five hard points instead of seven; Ecstatic Frenzy gains flat magic damage and self-synergy; Takedown's life regeneration per kill falls from 5% to 2.5%.
- Assassin Queen of Blades fires every 0.8 seconds instead of one; Maelstrom MkIV changes damage and flechette count. Barbarian Immortal gains five percentage points of avoidance.
- Necromancer Bane gains radius; Paladin Sunstorm is no longer channeled and benefits from cast rate; Sorceress Moonstrike's life bonus becomes linear and capped at 35%.
- Existing Thunder Machine and Athulua's Command items may need to be found again because their old procs no longer work after the Blindside replacement. Act bosses have reduced unique drop bias. [v005 release notes](https://www.moddb.com/downloads/median-xl-2012-v005); [release announcement](https://modsbylaz.vn.cz/latestnews.html)

## Test checklist

Run only when game testing is authorized. Expected behavior follows the cited sources above; original-version caveats apply. Use disposable characters and items, and record build, difficulty, setup and observed outcome.

- [ ] **Seven starts:** Create each class; reach Act I town, open the skill panel, and save/reload successfully. Compare skills and unlocks to v005 data; the README's 30-per-class count includes rewards.
- [ ] **Amazon devotion:** With suitable level and points, learn one level-18 bow/spear/javelin/blood devotion and verify the other three are unavailable. [Amazon](https://modsbylaz.vn.cz/amazon.html)
- [ ] **Druid v005 skill:** Learn and cast Laughing Ghost; verify the projectile travels and explodes, and Blindside is replaced. [v005 notes](https://www.moddb.com/downloads/median-xl-2012-v005)
- [ ] **Monster behavior:** Encounter quill rats and observe their homing spikes; verify a representative elite's distinct attack. [README]
- [ ] **Gem upgrade:** Cube two identical same-quality gems; expect one gem of the next quality. [Cube](https://modsbylaz.vn.cz/cube.html)
- [ ] **Disenchant and crystal:** Cube an expendable unique with the catalyst; verify shards and catalyst returned, then cube five shards into one crystal. [Cube](https://modsbylaz.vn.cz/cube.html)
- [ ] **Dawn runeword:** Insert El last in an eligible grey socketed weapon, filling any preceding sockets with jewels; expect Dawn. [Runewords](https://modsbylaz.vn.cz/runewords.html)
- [ ] **Book and Butcher:** Cube three hearts and three candles, select the Book's skill in The Hole Level 2, summon the Butcher, and verify the book remains. [Summoning](https://modsbylaz.vn.cz/summoningubers.html)
- [ ] **Kurast access and class charm:** Enter Arachnid Lair from Spider Forest and reach Kurast 3000 BA; obtain a matching class charm and check its inventory bonuses. [Uberlevels](https://modsbylaz.vn.cz/levelubers.html); [Level Challenge 2](https://modsbylaz.vn.cz/levelchallenge2.html)
- [ ] **Dungeon and trophy:** Enter Ancient Tunnels for Creature of Flame; separately, with a matching charm and trophy, cube them and confirm the added bonus and one-use restriction. Trophy drops are random. [Dungeons](https://modsbylaz.vn.cz/dungeonubers.html); [cube](https://modsbylaz.vn.cz/cube.html)
- [ ] **Respec:** Make Belladonna Elixir and verify actual D2R refund behavior, including saved points after reload; original LoD version limitation makes this a port-specific check. [Cube](https://modsbylaz.vn.cz/cube.html)
- [ ] **Storage and gold:** Measure grids, page behavior, carried/stashed gold and persistence; compare with original v005 evidence once available. No dimensions or limits are asserted yet.
