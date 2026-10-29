# HD icons: skill icon sheets and inventory item pictures (phase 5, 2D sprite part)

Lane `icons`, 2026-10-28. Pure Python, no game run. Source: the pure v005 extraction `mxl2012-runs/extract-mpq` (from the
archive.org D2SE/D2GL repack's `patch_d2.mpq`; re-check against the ModDB zip when it lands). Output is gitignored
(`work/hd`); the sprites travel in the asset pack, not in git.

```
py -3 -I tools/hd_icons.py baseline <extract_dir>                 once: copies what we read of D2R 93847 into work/d2r-baseline
py -3 -I tools/hd_icons.py build                                  skill sheets, item sprites + maps, both checks (about 1 min)
py -3 -I -m unittest discover -s tools/tests -p "test_icons.py"   unit tests on synthetic data (no game files)
py -3 -I -m unittest discover -s tools/tests -p "test_hditems.py" unit tests of the upscaler, the D2R HD reuse and the unused-index fill
py -3 -I tools/item_upscale_sheet.py <out.png> [mxl/<inv> ...]   comparison sheet of the upscaling methods (keep it out of git)
py -3 -I -m unittest discover -s tools/tests -p "test_hdpolish.py" unit tests of the skill sheet / panel upscale and the classic 225-254 fill
```

`MXL2012_EXTRACT` overrides the extraction folder, `MXL2012_HD_OUT` the output folder (default `work/hd`).

## What is read

| From | What |
|---|---|
| extract-mpq `data/global/excel` | `skills.txt` (`charclass`, `skilldesc`), `skilldesc.txt` (`IconCel`, `SkillPage`), `properties.txt` + the item tables (which skills items put on the skill bar), `charstats.txt`, `weapons/armor/misc.txt` (`code`, `invfile`, `uniqueinvfile`, `setinvfile`, `invwidth/invheight`, `type`), `uniqueitems.txt`, `setitems.txt`, `itemtypes.txt` |
| extract-mpq `data/global/ui/spells/*skillicon.dc6`, `data/global/items/*.dc6` | the pictures (units palette) |
| D2R baseline (read-only copy of `extract_dir`, machine-local config) | `filelist.txt`, `pal.dat` (units palette; the mod has no palette of its own), D2R's `weapons/armor/misc/uniqueitems/setitems/itemtypes.txt`, `data/hd/items/{items,uniques,sets}.json`, the classic `data/global/items/*.dc6` |

## Skill icons (`tools/skill_icons.py`)

Median XL 2012 is a 1.13c data mod, so the references are 1.13c's: `skills.txt charclass` picks the sheet (`ama sor nec pal
bar dru ass` -> `<xx>skillicon.dc6`, anything else, including the 449 classless rows, -> `skillicon.dc6`) and `skilldesc.txt
IconCel` is a frame of it. D2R reads the same two fields the same way (`Spells/<Class>/<Xx>Skillicon`,
`Spells/SubMenu/Skillicon`), so the class sheets are **not renumbered**: every frame of a class sheet becomes the same frame of
an HD sprite. The shared sheet is rebuilt in pairs and its cels rewritten (`tools/shared_icons.py`, next section).

- Class sheets hold **two frames per icon** (normal, pressed): `IconCel` is even, 210 tree skills = 7 classes x 30 distinct even
  cels. The **shared sheet holds one frame per icon** (25 frames; Attack is cel 3, Throw 5, ...): its odd cels are icons, not
  pressed frames. No frame number is ever rounded.
- HD: 130 px icons at stride 132, the strip well under D2R's 16384 px limit (the biggest sheet, Sorceress, is 118 frames x 132
  = 15576; a sheet over 124 frames would get a smaller stride, none does). 48x48 frames scaled up bilinearly with
  premultiplied alpha, units palette. `.lowend.sprite` is half size as D2R's own (65 px icons, stride 67; lane hdicons2: it was
  a copy of the HD file, 4 times the pixels).
- Writes `data/hd/global/ui/spells/{amazon/amskillicon, sorceress/soskillicon, necromancer/neskillicon, paladin/paskillicon,
  barbarian/baskillicon, druid/drskillicon, assassin/asskillicon, submenu/skillicon}.sprite` + `.lowend.sprite` and
  `skill_sheets.json`. The classic class `.dc6` files are the mod's own and need no conversion; the classic shared sheet is
  the paired one below.

Result on extract-mpq: 8 sheets, 684 class frames + 50 shared frames -> 734 HD frames, 16 sprite files.

### Shared sheet in pairs (`tools/shared_icons.py`, lane hdicons2)

The game draws `IconCel` as the skill button and `IconCel + 1` as the pressed button. Median's shared sheet has one frame per
icon, so a class-less skill showed the *next* icon while pressed (Attack, cel 3, pressed showed frame 4), and 74 class-less
skills named a cel past its 25 frames. `shared_icons.py tables` (a data step of `tools/build.py`, after `string_gaps.py`)
rebuilds the sheet as pairs (icon, the same icon again as the pressed frame, as Median's class sheets store theirs) and
rewrites the built tables of both banks; `skill_icons.py` writes the HD sheet from the plan, `sheet_dc6()` the classic
`skillicon.dc6` (`work/mod/shared_icons/skillicon.dc6`, shipped by `legacy_art.py` instead of Median's), so HD and classic read
the same frame numbers.

Where each class-less row's picture comes from:

| Rule | Source | Example |
|---|---|---|
| 1. class row: a Median class skill has the row too (Median's source tables) | that class sheet's frame; the class-less users get a copy `<row>~shared` with the new cel and no tree slot (the class skill keeps its row) | `Item Moon Queen` -> Amazon frame 60, `Item Balance` 44, `Item Wings of W` 48, `Item Elfin Arrows` -> Druid 16 |
| 2. a Median row with a cel on the shared sheet | that frame (the 1.13c picture) | Attack 3, Throw 5, the scrolls and books, the 200-odd item oskills on frame 0 ("?") |
| 3. a vanilla row D2R has too / a D2R-only row | D2R's frame (D2R's charclass of the row picks the sheet, its IconCel the frame; HD from D2R's own HD sprite) | `Fire Wall` -> D2R's Sorceress frame 30 |
| 4. none | Median's "?" (frame 0) | `Hard Aura` (cel 56, no sheet has it) |
| 5. a visible row on the "?" (rule 2 with cel 0, or rule 4) | the closest existing icon of `tools/data/item_skill_icons.tsv` (lane procicons, next section) | `Ice Lance` -> D2R's Ice Blast, `Summon Treewarden` -> Median's Druid Treewarden Form |

Only skills the player sees get a picture of their own (tiers tree / start / bar); item procs and monster skills keep theirs
when it is on the sheet anyway, else the "?" pair. All sources would be about 260 frames, more than the 16384-pixel strip
holds at 132 px (124 frames; more would shrink the icons, `MAX_FRAMES` stops the build); the visible ones are **58 icons, 116
frames**. A row is split whenever a class
skill of the built tables uses it (also D2R's Warlock skills, and the hidden class skills txt_migrate points at `attack` in the
classic bank), so no class skill's icon moves. `validate.py` checks that a `~shared` copy holds no tree slot.

Result (build of 2026-10-29, with lane procicons' table): 387 class-less rows, 50 split into `~shared` copies (49 in the
classic bank), 485 class-less skills; player-visible (218): 24 on Median's own shared frames, 4 on a class sheet frame, 1 on
D2R's (Fire Wall), 189 on a closest icon, 0 on the "?". `work/mod/shared_icons.json` holds the plan; a second run on the
rewritten tables recognises them (and the donor table) by hash and changes nothing.

Sizes against D2R's own `submenu/skillicon`: HD 7,962,280 bytes (116 frames; Median's single sheet was 1,716,040, D2R's
2,745,640 for 40 frames, lane hdicons2's 50-frame sheet 3,432,040), lowend 2,020,760 (D2R 696,840); classic DC6 280,462 bytes
(Median 59,755, D2R 58,560). The frames keep their size (130 px, lowend 65 px) and the shared sheet stays smaller than the
biggest sheet the mod already ships (Sorceress, 118 frames: 8,099,560 / 2,055,600 bytes). All 16 skill icon sprites are 68.8
MB (Median's sheets at full size were 97.3 MB, lane hdicons2's 63.2 MB).

### Item skills on the skill bar (lane procicons, `tools/data/item_skill_icons.tsv`)

The skills an item gives with charges (`item_charged_skill`) or as an oskill (`item_singleskill`, `item_nonclassskill`) go on
the skill bar and into the skill pop-ups. `skill_icons.item_skills` finds them in every item table of the build (uniques, sets,
runewords, magic affixes, automagic, cube outputs, gems, quality items; Median's charms and relics are unique items):
**201 skills**. One of them, `Apocalypse`, is renamed `Apocalypse_mxl` by txt_migrate (D2R's Warlock has a skill of that
name), so the plan read it as a monster skill and the check missed it; `shared_icons` and `skill_icon_check` now look a renamed
skill up by its Median name.

- **Already right (12):** Median gives them a frame of their own (Titan Strike, Bloodlust, Summon Edyrem, Jitan's Gate, Boss
  Killer, Mark of the Wild, Summon Quest Skill on the shared sheet; Item Moon Queen, Balance, Wings of W, Elfin Arrows on a class
  frame; Fire Wall on D2R's). They resolve in both banks (checked per bank, below).
- **Fixed (189):** Median's own data has cel 0, the "?" picture, for them (Median showed the "?" too). Each gets the closest
  existing picture, chosen by the skill's element, its missile / summon / aura and its name, preferring the skill's own class
  version or family in Median (Dragon Shot, Phalanx, the totems, the stances, Treewarden, Poison Flash, Holy Trap) and else
  D2R's icon of the same kind (D2R's frame, its own HD art in HD and its classic picture in classic). No new art. 35 donors,
  33 of them new on the sheet (Fire Wall's and the pentagram frame were there already). D2R's Warlock sheet is never a donor:
  its classic `waskillicon.dc6` holds the Druid's pictures. The table also names the row's other class-less users (monster
  skills on the same row), which get the same picture.

| Icon (donor) | Skills (display name, `skills.txt` name where it differs) | Why |
|---|---|---|
| `d2r:fire ball` | Ancients' Hand (`Ancients Hand`), Backfire, Bloodstar, Death Blossom, Disco Inferno (`Dinferno`), Fire Bolt Nova (`Firebolt Nova`), Item Death Blossom, Mon Ancients Hand, Splitfire, Sunburn, Syb, Wrath | fire missile or fire strike |
| `d2r:meteor` | Apocalypse, Cataclysm, Fire Fountain, Immolation Bomb, Meteor Shower, Mon Dynamite, NTSHW, Powder Keg (`Player Dynamite`), Pyroclastic Flow, Rain of Bombs | fire from the sky, fire bombs, eruptions |
| `d2r:fire wall` | Fire Cascade (`Other Fire Cascade`), Path of Flames, Phoenix Wave, Rune of Fire, Seal of Fire | fire on the ground, fire trap (the picture is on the sheet already, Fire Wall) |
| `mxl:brimstone` | Holy Trap, Mon Holy Trap Target | its class version, Paladin Holy Trap Advanced |
| `shared:1` | Pentagram (`Fire Star`) | a pentagram (Median's shared frame 1, on the sheet already) |
| `d2r:ice blast` | Cone of Cold, Cryo Beam, Frozen Soul, Ice Beam (`Mon Ice Beam`), Ice Lance | cold missile or beam |
| `d2r:frost nova` | Avalanche, Churel, Countdown, Frostfire Wave (`Other Pandemonium`), Frozen Crown, Glacial Nova, Hailstorm, Ice Bolt Nova, Ice Whirl (`Doom Serpents`), Mon Rune of Ice Target, NTGN, Rune of Ice, Shackles of Ice (`Other Shackles of Ice`), Shadow Avatar (`Other Avatar`), Super Gn, Winter Avatar (`Shadow Avatar`) | cold nova, ring, storm, trap or cold form |
| `d2r:terror` | Banish (`Other Banish`), Bloodspeaker's Mark (`Bloodspeakers Mark`), Charm, Cold Fear, Dire Charm (`Dire Charm L`), Dominate, Flash Charm, Greater Charm, Merc Possess, Nightmare, Possess (`Other Possess`), Timerless Charm, Untimered CF, Wyrd | curse: fear, banish, charm, mark |
| `d2r:nova` | Blast Wave (`Other Blast Wave`), Mon Longer BW, Msupernova, Nova Bomb, Supernova, Trinity Nova (`Elemental Rain`) | lightning nova or blast wave |
| `d2r:thunder storm` | Lightning Arena, Lightning Shield, Lightning Wall, Mlightning Shield, Static Ward, Stormfront, Vortex | lightning field, wall, storm or shield |
| `d2r:lightning` | Electrobolt (`Electrobolt Spell`), Ion Channel, Lightning Cascade (`Lightning Cascade Old`), Shock Flower, Static Lance (`Ball Lightning`), Static Spike (`New Static Spike`) | lightning bolt, beam or strike |
| `mxl:poisonflash` | Blood Flash, Flash | its family, Druid Poison Flash (the same barflash missiles) |
| `d2r:poison nova` | Amatoxin, Black Lotus Strike, Devouring Cloud (`Devouring Acid`), Diseased Cattle, Emerald Prison, Gamma Field, MercVSpirit, Mon Gamma, Mon Lotus Strike, Mpunisher, Punisher, Razor Spines (`Mon Spike Ripple`), Venomous Spirit | poison cloud, field or strike |
| `mxl:searinglight` | Death Coil, Death Ray (`Disintegrate`), Disintegrate (`DisinUber`), Energy Beam (`Mon Energy Beam`), NTDISUber, OHMAN, Orb of Annihilation (`BFG83K`), Pain Spirit (`Mon Pain Spirit`), Psicrown, Psionic Storm (`Mon Psionic Storm`), Searing Orb, Time Wave | magic beam, orb, spirit or psionic spell (Paladin Searing Light, a burst of light) |
| `d2r:hurricane` | Cyclone (`Typhoon`), Maelstrom, Squall Gust, Squall Wave, Whammy, Whirlpool | vortex, whirlpool, cyclone, squall |
| `mxl:manasweep` | Mana Coil, Rune of Mana | mana element, Sorceress Mana Sweep |
| `d2r:fist of the heavens` | Body of the Savior, Cherub Strike, Conquest, Exorcism, Sunspear | holy spell or holy strike |
| `mxl:dragon shot` | Fragmentation Shot (`Dragonshot2`) | its class version, Necromancer Dragon Shot (the same dragoncannonball missile) |
| `mxl:phalanx_real` | Ambush (`Phalanx`), Mon Bowless Phalanx | its class version, Amazon Phalanx |
| `d2r:multiple shot` | Arrow Swarm, Blindside, SMG, SS Blindside, Scattershot (`Scatter Shot`), Wraith Arrow | arrows or bullets |
| `d2r:blade fury` | Blade Barrier, Death Shards, Guided Chain, Shadow Blade, Silver Dart (`Silver Streak`), Slicer Blade (`Char Slicer Blade`) | blades, darts, chains, shards |
| `mxl:showerofrocks` | Hail of Stones (`Lapidate`), Rock Shock | stones, Barbarian Shower of Rocks |
| `d2r:whirlwind` | Claw Tornado (`Merc Claw Tornado`), Danse Macabre, Harvest, Mon Claw Tornado Effect, Spin to Win (`Spin To Win`), Spiral Dance, Spiral Dance (`Chober Chaber Spiral Dance`), Spiral Dance (`Skill Spiral Dance`), Spiral Proc | spinning melee attack |
| `d2r:berserk` | Cautious Strike, Clobber, Deathstrike, Feral Strike, Gorefest, Hamstring, Item Deathstrikes, Medusa, Merc Thorn Field, Mon Time Strike Target, Overpower, Ravage, Soulshatter, Thorn Field, Time Strike | melee strike |
| `d2r:teleport` | Demonic Speed (`Other Demonic Speed`), Shunpo | teleport or speed |
| `d2r:might` | Blood Fury, Dark Power, Hounfor (`Reward Hounfor`), Munholy Armor, Raven Heart (`Other Raven Heart`), Tantrum, UA2, Unholy Armor, Vanquish | damage or armor aura, shout |
| `d2r:prayer` | Bloody Mary, Inner Fire, Pagan Heart | healing aura |
| `mxl:snakestance` | Crane Stance, Kraken Stance, Sinwar Kraken | its family, the Barbarian stances |
| `mxl:deathsfurytotem` | Dead Wall Totem, Devil's Fang Totem (`Devils Fang Totem`), Elemental Totem, Exploding Totem, Fear Bomb Totem, Liche Totem, Mana Tide Totem, Totembound Guardian | its family, the Necromancer totems |
| `d2r:summon spirit wolf` | Call Scavengers (`Summon Rats`), Golden Calf, Summon Avalanche, Summon Shock Beast, Summon Thunder Bear | summons beasts |
| `mxl:treewardenform` | Call Treewarden (`Summon Treewarden`), Summon Glowing Fungus | its class version, Druid Treewarden Form (also a summoned plant) |
| `d2r:bloodgolem` | Call Blood Golem, Call Necrobot | summons a golem |
| `mxl:summonvoidarchon` | Call Henchman, Call Leprechaun, Call Malthael (`Call Angel King Safe`), Champions of the Sun, Summon Bane Monster, Summon Corpse (`Pet Corpse on Death`), Summon Darklings, Summon Daystar, Summon Fallen, Summon Overlord, Summon Shredder, Summon Sinner, Summon Sirens | summons other monsters (Necromancer Summon Void Archon) |
| `d2r:raven` | Fowl Fight (`Player Chickens`), Hawk Talons, Raven Flight (`Other Raven Flight`) | birds |
| `d2r:lightning sentry` | ATMG Sentry, Guard Tower, Patriot Sentry, TLGT, Typhoon Sentry (`Other Typhoon Sentry`) | sentry or tower |

In game (check `pic_skillbar`, slot 3, 2026-10-29, seen with the harness, docs/testing.md): three charged items and three learnt
oskill skills show their donor pictures in the skill pop-ups, the same in HD and in legacy, no "?".

Choosing again: change the donor in the table and rebuild; `shared_icons.py` fails on a donor that names no frame, on more
icons than the strip holds at full size, and lists table rows it did not need.

**The 3 missing skilldesc rows (`NT Old` -> `necromantictrance`, `MUnholyPrayer` -> `unholyprayer`, `Avenging Dummy` ->
`avenging fury`): accepted, no data fix.** No table of Median's names them (no monster, item, cube recipe, missile or other
skill; only their own skills.txt row), so no player can get or see them; pointing them at an existing row would make up a
connection Median never had. They stay the check's 3 unresolved monster skills.

**Not done:** the 21 item procs (chance to cast on hit / when struck, `ITEM` tier) and the monster skills keep the "?" when
Median gives them none: neither is drawn on the skill bar or in a pop-up.

In game (slot 4, 2026-10-29, background input, a new level-30 Sorceress and Amazon, HD and classic G, the lane's build with main's plugin): Fire Wall on the right button shows D2R's Sorceress fire wall in HD and a fire wall in classic, Attack
on the left button its crossed sword and arrow; the skill pop-up (a click on the button) shows every skill with its own
picture (Fire Wall, Scroll of Townportal, Force Wall, Unsummon, Throw, Attack and the class skills learnt). A button held down
(the left mouse button posted down, captured, then up) shows the same icon as released, in HD and classic, not the next
icon; D2R draws no visible pressed look on these buttons, so this shows only that no wrong frame appears. Item Moon Queen,
Item Balance and Item Wings of W ("Wild and Free") are passives (`passive` 1): the game puts them on no button and lists them
in no pop-up, so their new pictures are only seen with the check, not by a player.

Again in game (lane uicheck, 2026-10-30, slot 4's installed build of 2026-10-29 18:30, new level 1 Sorceress, Fire Wall,
Item Moon Queen and Item Balance learnt by `setskill`; Item Wings of W refused at level 0): Fire Wall on the right button shows
its fire wall in HD and legacy (`uic_sor_hd_bar.png`, `uic_sor_legacy_bar.png` in `mxl2012-runs/uicheck/checks-20261030-012114-s4/`).
The release notes' "no icon on the skill bar" line was written before this lane's sheet and is gone from them.

### Check (`tools/skill_icon_check.py`)

659 skills name a skilldesc (210 tree, 17 start, 201 bar, 21 item, 210 monster). Reference resolution (row exists, numeric
IconCel, frame inside the sheet, class sheets: pressed frame exists) and sprite integrity (frame count, every frame against its
DC6 by opaque fraction and mean colour, lowend at half size). With the plan of `shared_icons.py` the class-less skills are read
with their rewritten row and cel, the shared sheet is checked like a class sheet (even cel, pressed frame present), each of its
frames against its source (a D2R frame against D2R's own HD frame), and a visible skill left on the "?" (frame 0, also Median's
own cel 0: lane procicons) is a sheet problem. Each bank of the built tables (rotw and base) is read too: every class-less skill
of the plan must name the plan's row, and the row the plan's IconCel.

After lane procicons (build of 2026-10-29): 656 of 659 resolve as before, 0 sheet problems (no visible skill on the "?", both
banks as planned), 0 warnings.

Before (Median's tables as they are, lane icons):

| tier | skills | resolve | unresolved |
|---|---|---|---|
| tree (class skill on a tree page) | 210 | 210 | 0 |
| start (basic skills, character start grants) | 17 | 17 | 0 |
| bar (items put them on the skill bar: charges, oskills) | 201 | 197 | **4** |
| item (named by item tables otherwise, e.g. procs) | 21 | 18 | 3 |
| monster / vanilla leftovers | 210 | 143 | 67 |
| **total** | 659 | **585** | **74** |

After `shared_icons.py` (lane hdicons2, build of 2026-10-29): **656 of 659 resolve**, tree 210 / start 17 / bar 201 / item 21
all resolve, 3 monster skills unresolved (the three that name a missing skilldesc row), 0 sheet problems, 0 warnings.

Before, sheet problems 0, class-sheet warnings 0 (every class cel has its pressed frame). The 74 unresolved are all **classless skills
whose IconCel lies beyond the 25-frame shared sheet** (cels 26 to 108; three more name a skilldesc row that does not exist:
`NT Old`, `MUnholyPrayer`, `Avenging Dummy`). Most are vanilla skill rows the mod de-classed (Fire Wall, Lightning, Teleport,
Frozen Orb, ... still carry their vanilla page and a vanilla-sized cel) or monster skills; the mod's own UI never draws them.
The 4 on the skill bar: `Fire Wall` (51, cel 30; leftover vanilla row), and the item skills `Item Moon Queen` (756, cel 60),
`Item Balance` (790, 44), `Item Wings of W` (965, 48), whose skilldesc rows (`moonqueen`, `balance`, `wingsofwrath`) are shared
with the Amazon skills of the same name: the cel is the *Amazon sheet's* frame, so as classless skills they read past the shared
sheet. 46 of the 67 monster ones are shared that way too (fixed by the `~shared` split above). Exit code 1 only for a
tree/start skill or a broken sheet; `--strict` also fails on bar skills.

## Item pictures (`tools/item_art.py`, `tools/item_hd.py`)

D2R's HD inventory sprite: one RGBA frame, 98 px per inventory cell (lowend 49), centred on `invwidth x invheight`. D2R finds
it through three maps: `items.json` (code -> asset), `uniques.json`, `sets.json` (name key -> normal/uber/ultra asset). The mod
has 2429 distinct base item codes (weapons 921, armor 642, misc 866 rows) and **almost none are D2R codes** (18 of 921 weapon
codes), so each item gets its picture by its **invfile**, in this order:

1. **mod**: the invfile's DC6 is in the mod's MPQ -> converted (`mxl/<invfile>`). 100 pictures (99 new + `invrvex`, which
   overrides a vanilla name; the mod's art wins).
2. **same code**: D2R has the code in the same table with the same invfile -> D2R's entry (160 items).
3. **invfile**: a D2R item (or a D2R unique/set item with an own picture) of the same table has the invfile -> its HD asset.
4. **classic**: D2R has the classic DC6 of the invfile but no HD asset maps to it -> D2R's DC6 converted (`classic/<invfile>`,
   15 sprites, 20 items + 17 uniques). Vanilla invfiles otherwise use D2R's HD art, as asked.
5. **fallback** (approximation, listed in `item_hd_report.json`): no picture for the invfile at all.

Unique and set items use their row's `invfile`, else the base item's `uniqueinvfile` / `setinvfile`, else its `invfile`; D2R's
own unique entry of the same name is used only when its picture is the same (`same name`).

Result on extract-mpq: `items.json` 2429, `uniques.json` 808, `sets.json` 181; sprites generated 99 `mxl` + 15 `classic`
(each in HD and lowend = 228 files, 6.0 MB; `invrvex` points at D2R's own Vex rune, see "Picture quality"). Methods: items mod 551 / same code 160 / invfile 1696 / classic 20 / fallback 2;
uniques mod 18 / same name 4 / invfile 767 / classic 17 / a D2R unique's own picture 2; sets invfile 166 / same name 15.

### Picture quality (`tools/item_reuse.py`, `tools/upscale.py`; lane hditems, 2026-10-29)

The 115 converted pictures (100 `mxl`, 15 `classic`) were a 3.5x bilinear upscale, blurry next to D2R's own HD items. Now:

1. **Vanilla art -> D2R's HD picture.** Every converted picture is compared by palette index with each of the 385 D2R
   classic pictures that have an HD sprite (`art_provenance.compare`: silhouette IoU, index equality / mapping
   consistency, brightness and detail correlation). Accepted: `exact`, `recolour` (same silhouette; also a near one,
   IoU >= 0.93 with brightness corr >= 0.90 and detail corr >= 0.80, where Median redrew a few edge pixels of a gem) and
   `rescale` (another size, IoU >= 0.93, corr >= 0.75, detail >= 0.60). The sprite is then D2R's HD (and lowend) sprite,
   recoloured with the index mapping's hue and brightness shift and the saturation as a ratio (D2R's HD art is more
   saturated than its classic art, so an additive shift left Median's obsidian gems green; `colour_shift.shift_pixels`,
   the recolour of the HD effects, moved out of `hd_recolour.py` so no game slot is needed), scaled for a rescale,
   cropped and centred on the item's cells. An exact copy with D2R's folder and size is not written: the map points at
   D2R's asset (`hd_reuse_direct` in the report). **23 pictures**: the 20 Median gem colours `invgs[acot][a-e]` (D2R's
   sapphires / one amethyst, recoloured), `classic/invdss` (Mephisto's soul stone recoloured), `invsbk2` (D2R's Book of
   Skill at 0.49), `invrvex` (exact: D2R's `rune/vex_rune`, direct). Listed in `item_hd_report.json` `hd_reuse`.
2. **New art -> edge-directed upscale.** The other 92 (78 Median, 14 D2R classic) use `upscale.METHOD = "hybrid"`:
   Scale2x (EPX, exact colours) twice on edges and Lanczos-3 in the texture, blended by local contrast (YUV distance
   40..100 to a 4-neighbour; next to transparency = edge), resampled to 3.5x (lowend: Scale2x once, 1.75x) with
   premultiplied alpha, alpha from a bilinear resize (Lanczos rings: it made pictures slightly see-through) and alpha
   under 4 cleared, then a mild unsharp mask (0.5) that never exceeds alpha. Compared on 12 sample pictures (two D2R HD
   items as reference) against bilinear, Lanczos + sharpen, Scale2x x2, Scale3x and Scale2x with a loose colour
   threshold: Scale-only methods give clean outlines but turn the dithered, pre-rendered texture into flat blobs (a
   loose threshold posterizes it); Lanczos keeps the texture but stays soft; the hybrid has Scale2x's outlines and
   Lanczos' texture. The sheet is made by `tools/item_upscale_sheet.py` (game art: kept outside git).
3. **Palette indices 225-254.** D2R's units palette has them black (Diablo II's act palettes give them per-act
   colours), so 34 Median item pictures and the 7 skill icon sheets drew black specks and streaks in HD (1-99 pixels per
   file; the two spell books worst). `dc6.decode_frame(..., fill=True)` gives those pixels the mean colour of their
   opaque non-hazard 8-neighbours (looks the same as Diablo II's act 1 colours, without depending on an act palette).
   Used by `item_art`, `skill_icons` and both checks. Classic mode: `legacy_art.py` gives the same pixels of the shipped DC6
   the palette index nearest to that mean colour (docs/legacy-graphics.md).
4. **Skill icon sheets and HD panels (lane hdpolish, 2026-10-29).** The skill sheets (48 -> 130 px) use the same hybrid
   (`upscale.scale_rows`, dc6.scale's call; `skill_icons.scale` is bound to it, frame layout and IconCel mapping unchanged),
   and so do the inventory / cube panels (`ui_panels.scale_panel`, was Lanczos). Sizes unchanged (raw RGBA of the same
   geometry: 16 skill sheet files 97,332,160 B, 4 panel files 17,509,176 B). Other scaled art left as it is: D2R's own HD
   art resized (`item_reuse`, `skill_tree_art`: painted), the missile flipbook masks (`missile_art.py`, run by hand: a
   brightness mask, not pixel art), the matching thumbnails of `art_provenance`. Comparison sheets:
   `py -3 -I tools/hd_polish_sheet.py <out_dir> --legacy` (game art: keep it out of git).

Size: each sprite keeps its item's cells, so it is the size of D2R's own picture for those cells (98 px per cell, RGBA);
the reused ones are at most D2R's (D2R's chipped gems are 100 x 100, ours 98 x 98). Total item sprites 6,059,720 ->
6,011,620 bytes (230 -> 228 files). Sprites are cached by modification time against their DC6 and the converting tools.

### Check (`tools/item_icon_check.py`)

468 invfiles are referenced (invfile, uniqueinvfile, setinvfile of weapons/armor/misc, invfile of uniques/sets): 100 have a mod DC6,
366 only a D2R classic DC6, **2 have no DC6 anywhere**. Checked: all 228 generated sprites against their DC6 (size = whole cells
holding the picture, opaque fraction, colour; the 22 made from D2R's HD art within the looser `REUSE_*` limits, opaque
fraction 0.15 and colour 25, as D2R's redraw is not the classic picture; 0 problems), every one of the 2429 codes in `items.json` and every unique / set name
in its map with an existing asset (D2R sprite or generated; 0 missing), every item using a mod picture points at it or, for an exact copy, at D2R's asset (0 not used).
Exit 1 on any of those; unresolved invfiles and fallbacks are reported, not failed.

## Gaps (also in `docs/unported.md`)

- **Unresolved item references (2).** `stoneearth` (Mana Pack, `zoh`) and `stonemars` (Life Pack, `zog`): no DC6 in the mod
  or in D2R. They get an approximate picture (`charm/charm_small`); real art needs the base game's file or a new picture.
- **Unresolved skill references**: fixed for every skill the player sees (`shared_icons.py`, above); the 189 item skills that
  Median itself draws as "?" get the closest existing icon (lane procicons, "Item skills on the skill bar"). Item procs and
  monster skills without a frame of their own draw the "?" icon (the sheet's size limit); 3 monster skills name a skilldesc
  row that does not exist (`NT Old`, `MUnholyPrayer`, `Avenging Dummy`): accepted, no table names them.
- **Item skill icons are stand-ins.** 189 skills show an icon of another skill of the same kind (no new art); several share one.
- **Pressed state of shared-sheet skills**: fixed (the sheet is in pairs, HD and classic); in game a held button shows its
  own icon (above).
- **Shared sheet size**: 116 frames against D2R's 40 (+5.24 MB HD, +1.32 MB lowend against D2R's): 58 visible icons need 116
  frames, still under the Sorceress sheet (118).
- **Repeated unique/set names.** The maps are keyed by name; Median reuses one name on many bases (231 unique names on several
  rows, 350 rows `Cornerstone of the Roflworld`, 195 `SkillsdLastSkillEver` placeholders). The first row's picture is used for all
  rows of a name; only 5 names (2 unique, 3 set) have rows with another picture.
- **Art quality.** 92 pictures (78 Median, 14 D2R classic without an HD picture) are still upscales (the hybrid above):
  crisp, but pixel-art detail next to D2R's painted HD items. No new HD redraw. Skill icon sheets use the hybrid too (item 4). Seen in game with the harness (check `hdit_icons`, slot 4,
  2026-10-29, docs/testing.md): 16 items in HD and legacy, drawn as intended.
- **Skill tree backgrounds** (`skltree_*_back.dc6`): done by `skill_tree_art.py`, docs/hd-ui.md ("Skill trees").
- **State icons: nothing to convert.** Median XL 2012 (1.13c) has no buff / state icon art (no DC6 for it in the MPQ, no icon
  column in `states.txt`; a state shows only as its overlay, which the effects tools port), and D2R 3.3 has no state icon bar:
  its only HD "effect icons" are the controller HUD's fixed set (`controller/hud/effecticons`: immunities, desecrated / terror),
  drawn by D2R's own rules, with no table field a mod state could point at.
- **Not done here:** other UI DC6, DCC animations (`dcc.py`, monsters/missiles/overlays: other lanes).
- **Untested in game.** No game run: that D2R accepts these sprites at these paths and
  that D2RLoader serves them from the mod folder is not checked here. The maps replace D2R's
  `data/hd/items/*.json` wholesale (they must not be merged: D2R's own entries name items the mod does not have).

## Files

The tools, what they were built from and what changed:

| Here | From | Change |
|---|---|---|
| `tools/dc6.py` | `skill_icons.py` (read/write DC6, decode, resize, sprite, PNG) + `item_art.py` (scale, item sprite) | split out; `scale` merges both resizers (centred, premultiplied); sprite reader and fingerprint helper added; palette from a file |
| `tools/skill_icons.py` | `skill_icons.py` | rewritten smaller: no renumbering, no skilldesc/skills rewrite, no classic DC6 repack (the mod's sheets are 1.13c's); keeps the tier logic (`item_skills`, priorities) for the report |
| `tools/skill_icon_check.py` | `skill_icon_check.py` | no PIL / D2Sigma comparison: reference resolution + sprite-vs-DC6 fingerprint |
| `tools/item_art.py` | `item_art.py` | mod DC6 vs D2R classic DC6 groups; reads the mod's extraction; no D2R filelist test |
| `tools/item_hd.py` | `item_hd.py` | invfile-first resolution (new codes), effective unique/set invfile, classic fallback, no strings_ns (1.13c index cells are plain names), report JSON, testable `Plan` class |
| `tools/item_icon_check.py`, `tools/hd_icons.py`, `tools/icon_paths.py`, `tools/tests/test_icons.py` | new | check, driver (baseline copy + build), paths, 17 unit tests |
| `tools/upscale.py`, `tools/item_reuse.py`, `tools/colour_shift.py`, `tools/item_upscale_sheet.py`, `tools/tests/test_hditems.py` | new (lane hditems) | upscaler methods, vanilla-art detection + D2R HD render, the recolour (moved from `hd_recolour.py`), comparison sheet, 15 unit tests |
| `tools/shared_icons.py`, `tools/tests/test_shared_icons.py` | new (lane hdicons2) | shared sheet in pairs: plan, table rewrite, classic DC6; 9 unit tests |
| `tools/data/item_skill_icons.tsv`; `shared_icons.py`, `skill_icon_check.py`, `test_shared_icons.py` | new / changed (lane procicons) | closest icon of the item skills on the "?" (donor table, its resolution, the strip limit), renamed `_mxl` skills by their Median name, per-bank table check; 6 more unit tests |
| `tools/hd_polish_sheet.py`, `tools/tests/test_hdpolish.py` | new (lane hdpolish) | comparison sheets (skill icons, panels, classic 225-254), 9 unit tests |

Not copied: `state_icons.py` (no state icon art in 1.13c, see Gaps), `dcc.py`, `hd-effects.md` / `item-tooltips.md` (no state icons in the mod; DCC art and tooltips are
other lanes).
