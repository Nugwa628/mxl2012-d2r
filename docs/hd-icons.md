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

### Picture review (`tools/item_art_review.py`, `tools/item_art_sheets.py`; lane itemart, 2026-10-30)

Of the 2429 item codes, about 1,700 already use D2R's own HD art by invfile and 23 pictures are D2R HD sprites recoloured
(`hd_reuse` above); the 92 upscales are what looks soft. **Owner rule (2026-10-30): the owner sees new item pictures
before any goes into the build.** The candidates are written down in `tools/data/item_art_proposals.json`, each with its
own `enabled` switch under the file's `enabled`; `item_hd` uses only the entries switched on
(`item_art_review.enabled_proposals`) and lists every entry in `item_hd_report.json` `picture_proposals` ("ON" or "off:
owner review").

**Switched on (owner, 2026-10-30, lane itemart2): the five Rainbow Stones `og1`..`og5`** ("they look really nice"): D2R's
HD sapphire of the same cut and grade in Median's colours by position, as on sheets 1, 2 and 4. The other 23 entries (the
arcane crystals, the runes, the signet, the apple) stay off: they are only a smoother or crisper upscale.

How the build uses an entry switched on (`item_hd.generate` -> `item_art.make_asset(proposal=...)` -> `item_art.convert`):
the picture is made by the review sheets' own code, `item_art_sheets.candidate`, instead of the upscale or the `hd_reuse`
render: a `reuse` entry crops D2R's HD sprite, scales it to the area of Median's picture at 98 px per cell, recolours it
(`colour_by_position`, or the entry's hue / sat / val) and centres it on the item's cells; the `.lowend` sprite does the same
from D2R's lowend sprite at 49 px per cell; a `method` entry is that upscale setting. The cells, the centring and the size
rule (`asset_size`) are the upscale's, and the sprite is written at the same path (`mxl/<inv>.sprite`), so the item maps do
not change. The report lists the pictures made so as `proposal_on` (a switched-on entry the build has no picture for: under
`proposal_unused`); `generate` counts them as "mxl from proposal". A change of the proposals file remakes the sprites of its
entries (it is a dependency of their cache). The check (`item_icon_check.py`) holds them to the looser `REUSE_*` limits,
as D2R's art. The built og1..og5 sprites are pixel for pixel the candidates on lane itemart's sheets (max difference 0;
`test_itemart.Og4AgainstTheReviewSheetTests` for og4); in game: docs/testing.md "Lane itemart2".

**Ranking** (`py -3 -I tools/item_art_review.py rank --top 0`): how often players see a picture, summed over the items that
show it: expected drops per kill over every enabled monster row and the three difficulties through the treasureclassex tree
(a rough count, no area densities), sold by a vendor, cubemain outputs, kept in the inventory (charm, crystal, rune, gem,
signet, Mega Ring types) and level <= 30; score = log10(1 + 1e4 drop) + 2 sold + log2(1 + cube) + 2 kept + 1 low. Top 25:
`jbscross` (200 shrine items), the four arcane crystals `pearl1-4` (174 items: Arcane Crystals and the Crystal of ... affix
items), `catal3`, `sigil1b`, `realapple`, `shiniewhite` (clue gems), the Rainbow Stones `og3-5`, then 13 of Median's runes
(`r-a-05` .. `r-a-17`, Sha .. Rha). The other runes, `og1`, `og2` and the rest follow.

**Candidates**, tried in this order per picture (judged by eye on the sheets):

1. *A D2R HD sprite of the same kind of object* (`item_art_sheets.loose_candidates`: mask IoU of the two tight crops
   stretched to one box, times exp(-2 |log aspect ratio|); all 444 D2R HD inventory sprites; then scaled to the area of
   Median's picture and recoloured). Accepted only for the **Rainbow Stones** (`og1-5`, type `gemx`, Median's art is a D2R
   gem cut in many colours): D2R's sapphire of the same cut and grade with Median's colours *by position*
   (`colour_by_position`: Median's hue and saturation, smoothed and stretched over the D2R picture, D2R's brightness scaled to
   Median's mean; a single hue shift cannot give a rainbow). `og2`'s flawed cut is wider than Median's upright oval.
   Rejected: faceted D2R gems for the arcane crystals (they are smooth glowing orbs and would read as gems, which Median also
   has); D2R's sorceress orbs (each sits in a claw or on a stick); skulls for the clue gems (silhouette only); D2R runes for
   Median's runes (another glyph names another rune).
2. *Another upscale setting* (`item_art_sheets.VARIANTS`, run on the same hybrid code with other module settings):
   `hybrid-smooth` (Scale2x on the outline only, edge contrast 150..250, sharpen 0.3) for the four **arcane crystals**: the
   hybrid's Scale2x stepped their round shading; `hybrid-crisp` (edge contrast 20..60, sharpen 0.8) for the 17 **Median runes**
   (`r-a-01..03`, `05..18`: the glyph reads clearer), `sigil1b` (Signet of Learning) and `realapple` (Apple).
3. *Keep*: `jbscross`, `catal3`, `shiniewhite` (no D2R object of their kind; the variants were no better).

Would only look right with new art: Median's runes (D2R's HD stones carry D2R's glyphs), the arcane crystals (no plain D2R
sphere), the shrine cross, the catalysts, the signets, the clue gems and the apple.

**Review sheets** (`py -3 -I tools/item_art_review.py sheets <out_dir> --top 25`): one row per picture, Median classic
(legacy look: nearest x3.5) | current HD upscale | candidate, at D2R's HD size (98 px per cell) on an inventory-like cell
grid, the picture key, item names and codes under the row; at most 8 rows per sheet, each also at 2x (`_2x.png`). Pictures
with a proposal first (sheets 1-4), then the top-25 pictures kept as they are (sheet 5). Game art: written outside git
(`mxl2012-runs/itemart/review/`). In game: check `itemart_pics` (docs/testing.md "Lane itemart").

### D2R HD art of the same kind (lane itemart3, 2026-10-30; all 66 ON)

The owner liked the Rainbow Stones and wants as much HD as possible, with D2R's own HD art only (no new 3D models, no new
drawing: D2R's 2D pictures recoloured or recomposed). For each of the 87 upscaled pictures (`rank --top 0`, all but og1..og5)
a D2R HD item picture of the same kind and shape was looked for by eye over all 444 D2R HD inventory sprites, with
`silhouette_score` as a hint, and rendered both ways (`colour_by_position` and the mean shift of `colour_match`); the better
one by eye is the entry's `colour` (or its `hue` / `sat` / `val`). **66 matched, 21 not.** The 66 went into
`tools/data/item_art_proposals.json` with `"lane": "itemart3"` and `"pick"` (1 = best); they replace lane itemart's off upscale
entries of the same pictures (the 17 `hybrid-crisp` runes and `sigil1b`).

**Switched on (owner, 2026-10-30, round 2): 59 of them**, every one but the seven signets ("they look too much like jewels and
they are signets / emblems"). `item_hd` makes them with `candidate` at HD and lowend size, as og1..og5: the build now makes
64 pictures from proposals (54 `mxl`, 10 `classic`), 24 `mxl` and 4 `classic` pictures stay upscales (the 21 unmatched and the
7 signets). In game: docs/testing.md "Lane itemart3".

**Round 3 (owner, 2026-10-30): the 23 runes off again** ("they aren't sharp, Qor is supposed to be a skull, everything is too
blobby / muddled, they should look like chiselled runes but still be legible"; the same for the signets' signs). The build
makes **41 pictures from proposals** (31 `mxl`, 10 `classic`: og1..og5 and 36 of lane itemart3); 47 `mxl` and 4 `classic`
stay upscales. Two owner colour notes are on: the Sunstone of Thunder `invgmw` retinted clear yellow and the Oil of Jewelcraft
`zelixir7` clear pink (reuse key `tint`, `item_art_sheets.tint`: the pixels of a hue range take the new hue and at least a
saturation, the brightest highlights stay near white).

**Redrawn signs (round 3; on since round 4):** every rune and signet sign is redrawn by hand as clean strokes in
`tools/item_glyphs.py` (`RUNES`, `SIGNETS`: polylines, rings, drilled dots, sunk polygons over the classic picture's pixel grid,
following Median's glyph pixel for pixel where it is clear and its intended shape where 23 px are too few: Thur is a 3, Ix an X
over a stem, Sha'ad a lightning bolt, Qor a skull and crossbones, the Gold signet Saturn's sign). `item_glyphs.chisel` cuts
a sign in at the output size, supersampled 4 x 4 and never blurred: a V cut whose wall facing the light (top left, as D2R's
runes) is lit, the near wall in shadow, a dark floor and a thin lit lip outside the far edge. Runes: reuse `"glyph": "chisel"`
(`engrave_rune` on D2R's blank Ist stone); signets: `"seal": "chisel"` (the seal above, the sign engraved on the enamel); both
with `"sign"` = the picture key. Review sheets: `py -3 -I tools/item_art_review.py sheets <dir> --round3`
(`item_art_sheets.write_round3`: Median classic | round 2 | round 3 | round 3 at 1920 x 1080; and `overview_2x.png`, classic |
round 3 for all 32), in `mxl2012-runs/itemart3/review-r3/`.

**Round 4 (owner, 2026-10-30: "the new ones look great, ship em"): the 23 runes and the 7 signets on**, with the redrawn,
chiselled signs (runes on D2R's stone, signets engraved on the gold seal); the yellow Sunstone of Thunder and the pink Oil of
Jewelcraft stay on. The build makes **71 pictures from proposals** (61 `mxl`, 10 `classic`: og1..og5 and all 66 of lane
itemart3); 17 `mxl` and 4 `classic` pictures stay upscales (the 21 unmatched). In game: docs/testing.md "Lane itemart3".

**Signets, second try (off, lane `itemart3-signets`):** a seal instead of a jewel: D2R's flat gold Crown Shield disc
(`armor/shield/crown_shield`) as the stamped metal, its centre (half the radius) enamelled in the colours of Median's centre disc
(the sign filled out from around it, smoothed, D2R's shading kept faintly) and Median's own sign stamped in (its dark strokes
against their surroundings, stretched, cut in as a dark groove with a light lip): `item_art_sheets.seal`, reuse key
`"seal": "median"`. Sheet: `py -3 -I tools/item_art_review.py sheets <dir> --lane itemart3-signets`
(`mxl2012-runs/itemart3/review-signets/sheet_01.png`). On since round 4 with the engraved sign (`"seal": "chisel"`).

| picks | pictures | D2R picture | colour |
|---|---|---|---|
| 1-15 (best) | Horadric Malus `invhmr`, scepter `invscp`, Jolly Roger `hardmode`, scroll pair `invhscr2`, Token of Absolution `pot04`, Sunless Crystal Bird `bird4`, the four Sunstones `invgm[rbwv]` and the Class Rewards `invgmy`, Shadowfang `invbla`, New2LilithsBelt `invblt`, I Am Rich `redgem`, Multi Shards `gemcontainer` | D2R's Horadric Malus, scepter, skull, Horadric scroll pair, green flask (self-resurrect scroll), golden bird, flawless ruby / sapphire / diamond / amethyst / emerald (round cut), Shadowfang, light belt, flawed ruby, soul stone | by position or mean |
| 16-27 | Ingredient Rings 1-5 `ring01/03/06/07/09`; the seven oils `zelixir1,2,4-8` | D2R's rings `ring2` / `ring`; D2R's round potion flask (`full_rejuv_potion`; the oils' skull stopper is lost) | by position |
| 28-50 | the 23 Median runes `r-a-01..03, 05..18`, `r-d-02, 04, 05, 07, 11, 12` | **recomposed**: D2R's Ist rune stone with its glyph taken out (`blank_stone`) and Median's glyph cut in (round 2: `glyph_mask`, `carve`, reuse key `"glyph": "median"`, too blobby; round 3: the redrawn sign chiselled, `"glyph": "chisel"`, on in round 4, off for 0.1.5; since lane runehd: Median's own pictures upscaled again, "Runes" below) | D2R's stone |
| 51-57 | the seven signets `sigil1b-6b`, `sigilxl` | round 1: D2R's gem in a gold setting (`perfect_diamond6`), rejected by the owner (reads as a jewel); then the seal above (round 3: the redrawn sign engraved), on since round 4 | by position |
| 58-63 | the six clue gem colours `shinie*` | D2R's flawed gem of the colour (rough stone); they may read as D2R flawed gems | by position |
| 64-66 (weakest) | Boss Junket `scroll11`, Scroll of Kings `invscb2`, Fool's Gold `invgldm` | D2R's parchments; D2R's gold coins (Median draws lumps, not coins) | mean |

The round-2 rune glyph (kept for the comparison sheets, not used): Median's stroke pixels by hysteresis (darker than 0.70 x the stone's median brightness, grown into the
connected ones darker than 0.86 x, 3 px inside the rim), stretched over D2R's stone with a bicubic resize, a blur and a soft
threshold (`GLYPH_EDGE`), cut in as a dark groove with a lighter lower-right lip. Median's glyphs are 2-3 px strokes in a 23 px
picture, so the bold ones (Thur, Nas, Kra, Yul, Rha, Vith, the `r-d` signs) come out clean and the fine ones (Lah, Kur, Lai,
Ath's lower lines) simplified; the owner judges each on the sheets.

**Not matched (21, stay upscaled):** the shrine cross `jbscross`, the arcane crystals `pearl1-4` (no plain D2R sphere), the
catalysts `catal1-3`, `realapple`, the goblet `apple`, `cherries`, `moon1` (crescent), `evileye` (D2R's eye is an eyeball with
its nerve, Median's a slit-pupil eye), `skullstar` (a skull under a star), `ring08` (a skull ring; D2R has none), the bag `s1`,
the open book `summbook` (D2R's books are closed), the Bling Bling piles `invfary3/4`, the bones `invbonr3`, the candles
`invcndl`.

**Review sheets:** `py -3 -I tools/item_art_review.py sheets <out_dir> --lane itemart3` (`item_art_sheets.write_lane`):
the lane's entries by `pick`, four columns: Median classic (legacy look) | current HD upscale | proposal | the proposal at
1920 x 1080 (49 px per cell, the HD sprite at half size). Written to `mxl2012-runs/itemart3/review/sheet_01..09.png` (+ `_2x`).

### Runes: Median's own pictures upscaled again (lane runehd, 2026-10-30; all 23 off)

Round 4's chiselled runes were held back from 0.1.5 ("we need to work on those more"); the owner's ruling (2026-10-30):
*"just upscale the runes again, try to make them look more like HD versions of the original without losing the symbol feel
too much"*. So the D2R stone is dropped: the 23 rune proposals (`r-a-01..03, 05..18`, `r-d-02, 04, 05, 07, 11, 12`) are now
`"method"` entries of lane `runehd` (picks 1-23, all **off**), made from Median's classic picture by `tools/rune_hd.py`
(also `upscale.METHODS`, so `item_art_sheets.candidate` and the build use them like any other method). No new art, no 3D:
every colour comes from the original.

Why not the plain upscalers: a Median rune is a 23 px stone with 1-3 px strokes and a speckled face. Scale2x / the hybrid
keep the staircase and the speckle, Lanczos smears the sign into the face (the shipped picture: blurry, blobby). `rune_hd`
takes the picture apart at the classic size, scales each layer the way that suits it and puts it back together at 98 px
(49 for lowend):

- **silhouette**: the convex hull of the opaque pixels (the stones are convex), supersampled 4 x 4, corners rounded: straight
  anti-aliased sides; a dark rim band 0.7 classic px wide in the colour of the original's outer ring.
- **face**: the stone's colour without the sign and the speckle (a normalised Gaussian over the face pixels), scaled bicubic
  (the original's light-left / dark-lower-right shading kept as smooth gradients); the speckle comes back weaker, Lanczos-scaled.
- **sign**: each pixel's darkness against the stone around it, kept on the groups of connected dark pixels that hold a clearly
  dark pixel (or form a faint line of 6+ px well inside); single dark speckles and the stone's own darker edge are no sign.
  It is scaled by **threshold decomposition**: every darkness level (0.08 .. 0.50) is a mask, EPX-scaled twice (staircases
  become 45 degree edges), lightly blurred and cut with an anti-aliased edge, and the levels are stacked. So every contour is
  crisp, the original's tones stay (a faint stroke stays faint, a dark core dark), and a 1 px gap (Nih's hole, Thai's bars)
  stays open; binary masks (tried first) melted the signs into blobs, a plain bicubic cut lost faint strokes.

Three methods (sheet `methods_NN.png` shows all three per rune):

| method | what | picked for |
|---|---|---|
| `rune-flat` | the layers only: the closest to the original | Auhe `r-d-04` (its thin-rayed star: the cut-in shading makes it a splash) |
| `rune-hd` | + a light shading pass: the stone's edge bevelled (lit top left), a fine grain on the face, the sign cut in (shadowed upper-left wall, thin lit lower-right lip) | the other 20 |
| `rune-crisp` | `rune-hd` with the sign 1.25 x darker | On `r-a-03`, Qor `r-d-11` (their signs are faint in the original) |

Still weak (the source has too few pixels): Auhe's star loses its fine rays, Qor's skull keeps its shape but not its eye
sockets, On's lower bars and Sha's faint side marks are thin, Kur and Rha are as tangled as the original. The round-4 chisel
code (`item_glyphs`, `engrave_rune`, `item_art_sheets.round4_rune`) stays for the comparison sheets; nothing uses it for
the runes.

**Review sheets:** `py -3 -I tools/item_art_review.py sheets <out_dir> --runehd` (`item_art_sheets.write_runehd`):
`sheet_01..03.png` (+ `_2x`), per rune: Median classic (nearest) | the shipped HD picture (the plain upscale) | round 4
(chiselled) | the new one, at HD size and again at 1920 x 1080 (49 px per cell); `methods_01..03.png` (classic | `rune-flat` |
`rune-hd` | `rune-crisp`); `overview_2x.png` (all 23 new runes at 2x). In `mxl2012-runs/runehd/review/`. In game:
docs/testing.md "Lane runehd".

### Rebuilt pictures: the 21 without D2R art of their kind (lane itemart5, 2026-10-30; all 21 off)

The 21 pictures lane itemart3 found no D2R HD item for (its "Not matched" list: the shrine cross, the four arcane crystals,
the three catalysts, both apples, the goblet, the berry, the moon, the eye, the skull star, the skull ring, the bag, the open
book, the two Bling Bling piles, the bones, the candles) are lane `itemart5` `"method"` entries (picks 1-21, all **off**),
Median's own picture rebuilt crisp by `tools/item_rebuild.py` (also `upscale.METHODS`, so `candidate` and the build use them
like any other method). It is lane runehd's idea (`rune_hd`, owner: "HD versions of the original without losing the ...
feel") for any picture, not only a convex stone with a sign; no new art, every colour from the original:

- **silhouette**: the opaque pixels EPX-scaled twice (staircases become 45 degree edges), blurred 0.45 classic px, cut with an
  anti-aliased edge at the HD size: a clean outline, thin parts (a cherry stem, the cross's bars) kept.
- **tones**: threshold decomposition of the brightness at every distinct tone of the original (midpoints between its tones;
  each step a mask scaled and cut as the silhouette, the steps stacked), then a bilateral smoothing (range 12): the small
  steps of soft shading even out, outlines and highlights stay sharp, and every tone stays where the original has it.
- **colour**: joint bilateral upsampling: an HD pixel takes the colour of the classic pixels near it whose brightness is close
  to its own (a red cherry does not bleed into its green stem), set to the rebuilt brightness.

| method | what | picked for |
|---|---|---|
| `item-hd` | as above | the catalysts, the goblet, the berry, the skull star, the skull ring, the book, Bling Bling, the bones, the candles (their detail is in the tones) |
| `item-soft` | the original's low-contrast dither evened out first (a pixel within 14 of the median of its opaque neighbours takes it) | the arcane crystals, the shrine cross, the Apple, the moon, the eye, the bag (smooth surfaces) |

D2R art was looked at again for each (all 444 HD inventory sprites, and D2R 3.3's new ones: the Warlock's grimoires, the
essences, the fragment busts): the orb heads of D2R's sorceress orbs are the only spheres and each sits in a claw or wire
band (Dragon Stone's claw crosses the ball's front), the grimoires are closed books, D2R's eye is an eyeball. For the arcane
crystals the sheets also show **D2R's round-cut flawless diamond in Median's colours** (`alt`, as lane itemart's rejected
gem idea: it reads as a gem; the owner picks) and the other method; an entry's `alt` list is shown on the sheets and never
built.

Still weak (the source has too few pixels): the catalysts' 1 px bars come out a little thicker (the dark outline pixels
around them are part of the shape), the candles merge into one waxy block, the bone pile and Bling Bling stay as busy as the
original, the skull ring's band is faint (as in the original).

**Review sheets:** `py -3 -I tools/item_art_review.py sheets <out_dir> --rebuild` (`item_art_sheets.write_rebuild`):
`sheet_01..03.png` (+ `_2x`), per picture: Median classic (nearest) | HD now (the plain upscale) | proposal | the alternatives,
at HD size, then classic, now and proposal at 1920 x 1080 (49 px per cell); `overview_2x.png` (classic | new for all 21 at
2x). In `mxl2012-runs/itemart5/review/`. In game (trial build with the 21 on, slot 3): all 21 drawn in HD, docs/testing.md
"Lane itemart5". That run found bug #513: an item type with random pictures (`VarInvGfx`) makes D2R ask for
`<asset><n>`; `item_hd` now also writes those copies (only Median's Boss Killer Rings `ring08` need it).

### Check (`tools/item_icon_check.py`)

468 invfiles are referenced (invfile, uniqueinvfile, setinvfile of weapons/armor/misc, invfile of uniques/sets): 100 have a mod DC6,
366 only a D2R classic DC6, **2 have no DC6 anywhere**. Checked: all 228 generated sprites against their DC6 (size = whole cells
holding the picture, opaque fraction, colour; the 22 made from D2R's HD art within the looser `REUSE_*` limits, opaque
fraction 0.15 and colour 25, as D2R's redraw is not the classic picture; the 142 made from a picture proposal switched on
(71 pictures, HD and lowend) must be the approved candidate pixel for pixel, a VarInvGfx variant copy (#513) its picture byte for byte, `check_proposal_sprite`, since several approved
D2R pictures have another outline than Median's, e.g. coins for Fool's Gold; 0 problems), every one of the 2429 codes in `items.json` and every unique / set name
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
- **Art quality.** 21 pictures (17 Median, 4 D2R classic without an HD picture) are still upscales (the hybrid above;
  the five Rainbow Stones are D2R's HD gems since lane itemart2; lane itemart3 found D2R HD art of the same kind for 66 of
  them, on since 2026-10-30 but the 23 runes (off for 0.1.5; lane runehd proposes Median's own rune pictures upscaled
  again, "Runes: Median's own pictures upscaled again"), the signets with redrawn, chiselled signs: "D2R HD art of
  the same kind"; so 21 remain upscales, plus the 23 runes while off; lane itemart5 proposes all 21 rebuilt crisp from
  Median's own pictures, off, "Rebuilt pictures"):
  crisp, but pixel-art detail next to D2R's painted HD items. No new HD redraw. Skill icon sheets use the hybrid too (item 4). Seen in game with the harness (check `hdit_icons`, slot 4,
  2026-10-29, docs/testing.md): 16 items in HD and legacy, drawn as intended.
- **Skill tree backgrounds** (`skltree_*_back.dc6`): done by `skill_tree_art.py`, docs/hd-ui.md ("Skill trees"); sharper candidates (lane skillhd, off): `skill_tree_hd.py`, docs/hd-ui.md ("Skill trees: HD page candidates").
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
| `tools/item_art_review.py`, `tools/item_art_sheets.py`, `tools/data/item_art_proposals.json`, `tools/tests/test_itemart.py` | new (lane itemart) | visibility ranking of the upscaled pictures, loose silhouette / colour-by-position candidates, upscale variants, review sheets, the proposal list (off), 20 unit tests; `item_hd.py` lists the proposals in its report |
| `tools/item_hd.py`, `tools/item_art.py`, `tools/item_art_sheets.py`, `tools/item_icon_check.py`, `tools/data/item_art_proposals.json`, `tools/tests/test_itemart.py` | changed (lane itemart2) | the build makes the pictures of the proposals switched on (`candidate` at HD and lowend cell size), report `proposal_on`, the check's reuse limits for them; og1..og5 on; 3 more unit tests |
| `tools/item_art_sheets.py`, `tools/item_art_review.py`, `tools/data/item_art_proposals.json`, `tools/tests/test_itemart.py` | changed (lane itemart3) | rune stone recomposition (`blank_stone`, `glyph_mask`, `carve`, reuse key `glyph`), lane sheets with an in-game size column (`write_lane`, `sheets --lane`), 66 proposals; round 2: 59 on, the signet seal (`seal`, reuse key `seal`, off), `item_icon_check.check_proposal_sprite`, `game_checks` sets `itemart3a` / `itemart3b`; round 3: the runes off, the signs redrawn (`tools/item_glyphs.py`, `chisel`, `engrave_rune`, reuse keys `"chisel"` + `sign`), `tint`, `sheets --round3`; round 4: the runes and signets on, `game_checks` sets `itemart4a` / `itemart4b`; 7 more unit tests |
| `tools/rune_hd.py`, `tools/upscale.py`, `tools/item_art.py`, `tools/item_art_sheets.py`, `tools/item_art_review.py`, `tools/data/item_art_proposals.json`, `tools/tests/test_itemart.py` | new / changed (lane runehd) | the rune upscale (`rune_hd`: hull silhouette, face, threshold-decomposed sign; methods `rune-flat` / `rune-hd` / `rune-crisp` in `upscale.METHODS`), the 23 rune proposals as lane `runehd` method entries (off), `write_runehd` / `sheets --runehd`, `round4_rune`; 6 more unit tests (`RuneHdTests` x5, the lane's entries) |
| `tools/item_rebuild.py`, `tools/upscale.py`, `tools/item_art.py`, `tools/item_art_sheets.py`, `tools/item_art_review.py`, `tools/item_hd.py`, `tools/item_icon_check.py`, `tools/data/item_art_proposals.json`, `tools/game_checks.py`, `tools/tests/test_itemart.py` | new / changed (lane itemart5) | the picture rebuild (`item_rebuild`: EPX-cut silhouette, threshold-decomposed tones, bilateral smoothing, joint bilateral colour; methods `item-hd` / `item-soft` in `upscale.METHODS`), the 21 proposals as lane `itemart5` method entries with `alt` (off), `write_rebuild` / `sheets --rebuild`, `game_checks` set `itemart5`; `item_hd` / `item_icon_check`: VarInvGfx variant copies (#513); 6 more unit tests (`ItemRebuildTests` x5, the copies) |

Not copied: `state_icons.py` (no state icon art in 1.13c, see Gaps), `dcc.py`, `hd-effects.md` / `item-tooltips.md` (no state icons in the mod; DCC art and tooltips are
other lanes).
