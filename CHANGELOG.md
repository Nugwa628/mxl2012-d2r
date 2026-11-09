# Changelog

Release notes of D2R-XL 2012, newest first. `tools/github_release.py` and `tools/package_release.py` read the section of the
version being released (docs/release.md).

## Unreleased

## D2R-XL 2012

### 0.1.18 (2026-11-10)

- New developer menu, single player only: press Ctrl+F12 in a game (rebindable in Options > Controls). Spawn any unique, set item, charm, quest item or base by name, get a runeword kit (the base with sockets and the runes), travel to any area by name, raise your level, unlock every waypoint. See `docs/dev-menu-guide.md`.

- In HD, where Median's own wall art meets a D2R wall, a stone post or pillar now covers the seam, sized to the wall, on
  Tran Athulua (`desertpeak`), Old Bremmtown (`borgir`), Kurast 3000 BA (`excelsior3`), Rathma Square (`moskvich`), Toraja
  (`macumba`), The Proving Grounds (`dungrm6a`) and Khalimgrad (`charismatic`). Median's wall art on those maps is also toned
  to the colours of the D2R walls beside it. Fauztinville (`cypherpunk`) gets the toning but no posts, as the map is already
  at its limit.

- The HD main menu has a larger, centred three-line credit: "Median XL 2012", "By BrotherLaz", "(D2R Fan Port)".

- In HD, about 170 skill and monster effects changed size or picture to sit closer to their classic art. Among them, Miasma no longer throws lightning sparks and Soulshatter's rings are orange instead of bright yellow.

- In HD, more skills now look close to their classic picture: Buckshot's muzzle flash no longer throws a tall pillar of light, Holy Trap shows its flash again when it is laid, Psychic Scream has its wide ring, Moonbeam its long beam, Hypnotoad Prince its blue clouds, Wychwind its knives, and Queen of Blades, Seismic Charge, Phalanx and Egg Trap have bigger blasts (still orange where classic is red).

- In HD, about 150 more skills, monsters' skills included, now show a picture where part or all of their effect was missing: among them Egg Trap,
  Lava Pit, Rising Dawn, Beacon, Moonbeam, Great Hunt, Thunderstone, Holy Trap and Meteor Shower. Effects that stay on the ground no longer vanish right after
  they appear. Colours are only close for now and will be matched later.

- In HD, the walls of Median's own maps now follow the classic walls as whole wall lines built from D2R's own wall pieces, with
  gateways and doors where the classic map has them and walls as tall as in legacy. Duncraig's (`epicwhiners`) monastery front, which was only
  ivy and low stones, now stands as a full wall with its two arched gates.
- In HD, walls that were knee-high or missing on Median's Kurast and docktown maps now stand at full height with Median's
  own wall art where D2R has no matching wall: Tran Athulua (`desertpeak`), Fauztinville (`cypherpunk`), Kurast 3000 BA
  (`excelsior3`), Rathma Square (`moskvich`) and Old Bremmtown (`borgir`). Fauztinville now gets the same whole wall lines as
  the other maps. In The Proving Grounds (`dungrm6a`) the red brick arch is back, and the stairs of Khalimgrad
  (`charismatic`) show as steps instead of flat floor. The HD download grows by about 9 MB.
- In HD, projectiles that used to fly invisibly now draw: Flamefront, Pyroblast, Forked Lightning, Tempest and about 150 others. Blast Wave shows its expanding fire rings instead of a white flash. Forked Lightning and Tempest are white in HD (blue in legacy).

- Every crafting shrine now has one more line in its tooltip, in blue, naming what its Cube recipes give, for example
  "Cube: Strength, Crushing Blow". The name, charges and verse stay as they were.

- HD graphics: your weapon and shield no longer appear on you while you are in Trap Rat, Treewarden, Deathlord or Cow Disguise
  form. Legacy graphics already hid them.

- The five act towns now show their whole map as soon as you arrive, with no key press. Everywhere else, L still reveals the
  current level.

- Elixirs now have a liquid colour of their own in HD and legacy, also those already in your stash: Fire red-orange, Cold ice
  blue, Lightning yellow, Poison green, Experience violet, Greed magenta, Wealth gold, Strength crimson, Dexterity teal, Energy
  deep blue, Vitality orange, Adrenaline hot pink, Concentration grey-blue, Power white, Love pink, and the Greater ones a
  brighter shade: Experience blue-violet, Greed bright purple, Wealth pale gold, Strength bright red, Dexterity mint, Energy
  sky blue, Vitality peach. Names, effects and ground pictures stay the same.
- Crafting shrines now have a colour of their own in HD and legacy inventory/stash views, at every charge count:
  Creepy: dark red; Abandoned: light grey; Quiet: light blue; Eerie: dark purple; Weird: crystal red; Gloomy: dark
  blue; Tainted: dark green; Fascinating: orange; Ornate: light gold; Sacred: crystal blue; Shimmering: white;
  Mysterious: light purple; Spiritual: light green; Magical: crystal green; Enchanted: light yellow; Divine: bright
  white; Hidden: light red; Stone: dark grey; Religious: dark gold; Cryptic: dark yellow. Names, tooltips and
  ground pictures stay the same.

- **Fallen Wolf Riders and Wyrdwolves no longer stay standing after they die in HD** (bug #560). They looked like werewolves in HD and
  stood on after their death (Kurast Bazaar, Travincal, the Act 3 dungeons and the Act 5 temples). They now look like a grey wolf
  that dies and fades as the Druid's spirit wolf does. Legacy graphics were not affected.
- Map: **L** ("Reveal Level Map" in Options > Controls) now reveals the current level's map whenever you press it, right
  from the start of the level, in every level including the towns. The explored percentage and the 70% you had to explore
  first are gone: they did not match the map, in the sewers and catacombs and in small levels (bug #559). An old
  `threshold` line in `d2rloader/config/mxl2012-core.toml` is ignored; `exclude = [...]` there still turns the key off for
  the levels you list.
- HD walls: the wall-scene build now measures how tall the generated HD walls are against the legacy walls on every map and stops when a map falls below the range of D2R's own maps. Duncraig and Tran Athulua are known to be below it (their HD walls are missing or much lower than in legacy, bug #561) and are listed as known issues until they are fixed. No change in game.

### 0.1.17 (2026-11-08)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

- **Controller support: PyreFly's Controller QOL Updates now ships with the mod** (by **PyreFly**,
  <https://github.com/Pyre-Flies/D2R-Mods>, shipped and adapted with PyreFly's permission). With a gamepad: hold LB near
  items on the ground to see their buttons and pick one up with LB + that button; LB + A / X / Y act on the item in focus
  (identify, move between inventory, stash and Cube); with the stash open, hold LB and click L3 to put your gems, runes, materials and
  Median's elixirs, signets, trophies, shrines and Mystic Orbs into their stash tabs, including MEDIAN and ORBS; LT / RT page
  through the stash tabs and LB + LT / RT through the shared pages. The right stick aims skills, with a skill list made for
  Median XL 2012 (R3 on a skill in the skill tree turns its aiming on or off; your choices are kept across updates). Its
  belt shortcuts are off, so Auto Belt Refill keeps your belt. Settings: `mods\mxl2012\d2rloader\config\controller-qol-updates.toml`.
  Mouse and keyboard play is unchanged.
- Gamepad UI: the inventory now fits Median's 10 x 6 backpack inside its frame (the last rows and the right column no
  longer spill out) and has the Send to stash button next to the gloves; gold sits next to the boots (bug #556).
- Gamepad UI: the stash has all seven tabs, including MEDIAN and ORBS, with Median's Gems, Materials and Runes pages,
  and the backpack beside it shows in full (bug #557). Moving between the tabs with LT / RT has not been tested with a
  real gamepad yet.
- Stash: the Materials tab's Vanilla page no longer raises engine errors on every frame while it is open.
  Its empty slots for D2R-only items (keys, organs, essences, Worldstone shards and the like, none of which exist in Median)
  are gone; the three slots for items Median has stay (bug #548).

**Known issues:**

- With Controller QOL Updates loaded, opening the stash by clicking the chest can log engine warnings (bug #558). It does
  not crash the game.
- The LB + X / A / Y item shortcuts and right-stick aiming are new: feedback is welcome.

### 0.1.16 (2026-11-07)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

- Clearer text in legacy graphics: **press Ctrl+F in legacy graphics** to turn on the clear fonts (thinner, sharper
  digits and letters in panels, item text and titles); press it again to turn them off. The key is under Options >
  Controls > "Clear Legacy Fonts". It applies at once and is saved in `mxl2012-core.toml` (`[fonts] legacy_clear_fonts`,
  off by default). Dialogue, quest and chat text keep the original fonts to avoid the reported crash. Thanks to GeorgiaBoy
  for finding and testing the fix.

**Fixed:**

- Ctrl-clicking an item from the inventory into the stash now flashes the tab it went to (HD graphics). Orbs flash the ORBS tab and elixirs,
  signets, trophies and shrines the MEDIAN tab, where before every one of them flashed RUNES.

- "Send storable/stackable items to stash": in a classic or expansion game the button is greyed (those games have no
  Gems / Materials / Runes / Median / Orbs stash pages to send to), but clicking it only clicked and its tooltip never
  showed, so it looked broken. Now its tooltip shows, and a click says in the chat why it cannot send. In a Reign of the
  Warlock game the button works with the stash open or closed, on any tab, in HD and legacy graphics (also 16:9), and
  sends Mystic Orbs and Elixirs into their Median / Orbs slots (#554).

- HD graphics, Fauztinville: the wide stone stairs at the arrival and at the walkway crossings are drawn as stairs again
  instead of flat floor, and more of the small wall details (buttresses, gargoyles, caps) are back.

### 0.1.15 (2026-11-07)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

- Ctrl stat ranges are back. On some items with automagic mods a few range lines show twice (a D2RLoader issue).
- The downloader updates itself to 0.1.3 first. It turns the Ctrl stat ranges back on once (older downloaders turned
  them off); after that, your own `item_stat_ranges` setting is kept.

**New:**

- The mod now comes with **Auto Belt Refill** by **jaycachou-svg** (<https://github.com/jaycachou-svg/auto-belt-refill>,
  v0.35.9, shipped and adapted with the author's permission). It refills your potion belt from the inventory: by itself a
  moment after you drink, and in one go on a key you bind under Options > Controls (Refill Belt; no key is set by default).
  Each belt column refills with exactly the potion in its bottom slot (a Healing Potion column gets Healing Potions, a
  Greater Mana column Greater Mana Potions); to change a column, put another potion at its bottom. A completely empty column
  gets nothing until you put a potion there yourself. A small number on each column shows how many of its potion you have
  left (inventory and belt), red at 0, in HD and legacy graphics. Elixirs and the Goodberry are never moved.
  It knows the belt sizes of Median XL 2012's own belts (2, 3 or 4 rows by grade). Set fixed columns, or turn it off with
  `enabled = false`, in `mods\mxl2012\d2rloader\config\auto-belt-refill.toml`; updates keep your changes. Thanks to
  jaycachou-svg for the plugin and the permission.

- Map: once you have explored 70% of a level, press **L** (Options > Controls: "Reveal Level Map") to reveal the rest of
  that level's map. A chat line tells you when it is available. Not in towns. The share is set in
  `d2rloader/config/mxl2012-core.toml` (0 = always, 101 = off).

- The automap (Tab) shows the area level, e.g. "Area Level 75", under the area name at the top right: the
  monster level of the current area in the current difficulty (HD and legacy graphics).

**Fixed:**

- HD graphics, the Crypt: the low rock barricades are low rubble walls again instead of tall town walls, the stone arch
  near the entrance is an arch instead of two shelf-like walls, and the iron fences no longer float above the floor.

- Stash: hovering an item on the Gems, Materials, Runes, Median and Orbs tabs now shows its whole description, as in
  the inventory. Each Mystic Orb shows what it adds, so the orbs can be told apart.

- Fixed multiline skill descriptions and flavor text reading backwards (including Batstrike, Dark Summoning and Bloodbath), keeping each line’s color.

- HD graphics: Celerity no longer draws fiery streaks across the screen, and Mephisto's Lightning Arena, Mythal and
  Countdown use lighter effects (no white screen flash, far fewer explosions).

- HD: Tran Athulua's walls are back. Its ruin walls were drawn sunk into the floor, so the area showed floor only; the
  same fix brings up a few sunk walls in Kurast 3000 BA, Fauztinville and Rathma Square. The corridors west of the Tran
  Athulua arrival, which still showed open floor with a few broken wall stubs, are now closed by walls as in legacy. The
  short wall behind the braziers at the arrival still shows as pillars.

- HD: Fauztinville's walkways no longer have walls standing on both sides: the back sides of terrace walls are gone, as in
  classic, and many of its stairs are back. Kurast 3000 BA's sunken courtyard at the arrival is no longer fenced by those
  walls either. Still open: the wide staircase at the Fauztinville arrival is drawn as flat floor.

### 0.1.14 (2026-11-06)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**New:**

- Reign of the Warlock games: the stash has two more tabs, **MEDIAN** and **ORBS** (legacy graphics: PERSON / SHARED / GEMS /
  MATS / RUNES / MEDIAN / ORBS). MEDIAN holds the elixirs and Goodberry, the signets and packs (Moon Symbol, Boom!, Signet of
  Skill, Apple), the uberquest trophies and the 20 full shrines; ORBS holds the 100 Mystic Orbs. The Materials tab gets a
  Vanilla / Median selector: the Median page holds the oils and catalysts, arcane crystals and shards and the cube reagents
  (brains, Sacrificial Heart, Meditation Candle, sigils, Poser!), and D2R's own page stays as it was. Each item stacks in its
  slot like the runes and gems do; Ctrl-click puts it into its slot, and the "Send storable/stackable items to stash" button
  sends these items too. The Horadric Cube stays on both Materials pages. Used shrines stay ordinary items. Classic and
  expansion games keep Personal and Shared only; with a gamepad the stash stays D2R's. Your stash from 0.1.13 loads unchanged.
  **Do not go back to 0.1.13 or older after putting items into the new slots:** older versions delete those stacks when the
  character loads (#545).
- Buff HUD: Lightning Enchant, Cold Enchant, Shadowform, Lifeblood and Cow Disguise use fitting icons from Median's sheets
  instead of the question mark; the two enchants have distinct hover names.
- Legacy graphics: the small Horadric Cube window on the stash's Gems, Materials and Runes pages shows the cube's items, as
  HD does, scaled down on the cube's own 10 x 8 cells (it showed only the cube's cover). Hover for the tooltip, click to take
  an item, drop it on another cell, or Ctrl-click it into your backpack (#515).

**Changed:**

- Akara's "Reset Skills and Stats" is back to the usual rule: one respec per difficulty, the Den of Evil's reward. The
  unlimited respec up to level 100 from 0.1.13 is gone; Median's own respec item does the same at any level: the Token of
  Absolution (Belladonna), made in the cube from an Oil of Absolution and a rune.

**Known:** the life orb text staying at full (#547) is still not reproduced; please tell us if you see it. The gamepad
stash is not tested with the cube window. The first stash open can log a burst of item asserts in
d2rloader.log (#548, no crash, nothing lost, seen since 0.1.3). Life and mana leech on Nightmare and Hell is very small, as in
Median XL 2012 (#540). In HD, Median's runes still show their classic pictures scaled up and the HD pet row shows at most 9
icons (D2R's own limit).

### 0.1.13 (2026-11-06)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**New:**

- A "Send storable/stackable items to stash" button on the inventory (HD: the empty square at the bottom left; legacy
  graphics: next to the close button). One click puts every gem, rune and material in your backpack that has a slot on the
  stash's Gems, Materials or Runes pages into that slot, from anywhere, with the stash closed. A full slot (99) keeps its item
  in the backpack, and one line in the chat says what happened, for example "Sent 14 items. 3 stayed: stack full (El Rune,
  Chipped Ruby x2)." The button is greyed in classic and expansion games (no such stash pages) and, for now, when you joined
  another player's game.
- Akara's "Reset Skills and Stats" is unlimited up to character level 100: a character of level 1 to 100 can use it any number
  of times, on every difficulty, without the Den of Evil first. From level 101 the usual rule is back: one respec per
  difficulty, the Den of Evil's reward (a reward you have not used yet is still there). In multiplayer the host's game decides.
- The small Horadric Cube window on the stash's Gems, Materials and Runes pages (HD) shows the cube's items again, scaled down
  on the cube's own 10 x 8 cells: you can take an item out, drop it on another cell, or Ctrl-click it into your backpack.
  Legacy graphics still shows the cube's cover there (#515).
- Legacy graphics: empty slots on the stash's Gems, Materials and Runes pages are dimmed as in HD, so the slots that hold
  items stand out (#546).
- Buff HUD: the buff icons hide while the stash or the Horadric Cube is open, and while another panel (character, quests,
  waypoints, a vendor, inventory, skill tree) covers one of them; they come back when it closes. In legacy graphics that
  is every left-side panel, and the inventory or skill tree once six or seven buffs show; in HD the inventory stays clear.
  `hide_with_panels = false` in `mods\mxl2012\d2rloader\config\buff-panel.toml` keeps them shown.
- Buff HUD: Arcane (Elemental) Fury, Blades Of Light, Superbeast Neutral, Mark of the Bear and Mark of the Wolf show a real icon
  instead of "?" (their skills have none in Median XL 2012, so they borrow one from the mod's own icons: Elemental, Bladestorm,
  Superbeast, a bear and a wolf).
- Transmute with a key: bind D2RLoader's "Transmute Horadric Cube" in Options > Controls (group "D2RLoader"; no key by
  default). It works while the Horadric Cube is open, or a stash page with the cube window is open.

**Known:** a player saw the life orb's text stay at full ("Life: 970 / 970") while the orb was a third full (#547). We could not
reproduce it; if you see it, please tell us what you were doing and which plugins you use. The gamepad stash is not tested with
the new cube window. Life and mana leech on Nightmare and Hell is very small, as in Median XL 2012 (#540). In HD, Median's runes
still show their classic pictures scaled up and the HD pet row shows at most 9 icons (D2R's own limit).

### 0.1.12 (2026-11-05)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.12:**

- Legacy graphics on a 16:10 screen: the merc and summon portraits, the `/fps` text, the clock and the area name are no longer cut
  off at the screen edges. The classic picture is now widened to the shape of your screen (960x600 on 16:10, 1066x600 on
  16:9); a game in a window of another shape can set `aspect` in `legacy169.toml` (#544).
- The belt sorts Median's potions as in classic: the Experience and Greed elixirs, the Goodberry and Median's other belt
  potions no longer join the life (or mana) potion column. Each takes its own column and stacks only with itself; with no free
  column it goes to the backpack (#541).
- The Heretics of Act 4 (and the Heresiarch, Viletouch and the Cultists, which share their art) can be seen in HD: pale robed
  casters instead of a dark figure that disappeared on the ground. Classic graphics are unchanged (#542).
- Personal stash page 2 keeps the stash's tabs and gold box: it now opens inside the stash instead of replacing it. You can
  click Shared, Gems, Materials or Runes on page 2 again. Going back to page 1 no longer removes the large frame next to the
  stash. HD and legacy (#543).
- The Barbarian's spirits come back sooner: a spirit more than 20 sub-tiles away now stays behind only while the monster it
  hits is within 25 of you, and then for at most 4 seconds. In 0.1.11 a fight up to 40 away could keep one there for half
  a minute (#534).

**New:**

- Buff HUD: the mod now comes with **Buff HUD** by **Lukaszpg** (<https://github.com/Lukaszpg/d2rl-buff-hud>, MIT), in our
  fork for Median XL 2012 (<https://github.com/Nugwa628/d2rl-buff-hud>, branch `mxl2012`). A panel above the skill bar shows
  your timed buffs with a countdown: Median's skill buffs (Holy Armor, Judgement, Superbeast, Merkabah and the others),
  shrines, and the elixirs (Experience, Greed, Wealth, Power, Love, Concentration) with the elixir's picture. Hover an icon
  for the buff's name. It works in HD and in legacy graphics. To turn it off, set `enabled = false` in
  `mods\mxl2012\d2rloader\config\buff-panel.toml` and start the game again (the downloader keeps your copy of that file on
  updates). Thanks to Lukaszpg for the plugin and for the hover names (his pull request #6).
- Legacy graphics in 16:9: the mod now comes with our own D2RLoader plugin **D2R Legacy 16:9** (`legacy169.dll`,
  <https://github.com/Nugwa628/D2R-Legacy169>, MIT). The classic picture fills a 16:9 window: 800x600 shows as 1066x600, 640x480
  as 853x480; the side panels sit at the window edges and the bottom control panel stays 4:3 in the middle. HD is not changed.
  To turn it off, set `enabled = false` in `mods\mxl2012\d2rloader\config\legacy169.toml` and start the game again (the
  downloader keeps your copy of that file on updates).
- Reign of the Warlock games: Median's own runes (Sha to Sha'ad) and gems (Rainbow Stone, Onyx, Bloodstone, Turquoise, Amber)
  go into the stash's Runes and Gems pages and stack there like D2R's own, in HD and legacy graphics. Ctrl-click puts them
  in. Both pages are redrawn with room for them. With a gamepad the pages stay D2R's, without the new slots (stacks you
  already put there stay). **Do not go back to 0.1.11 or older after putting Median runes or gems in these pages:** older
  versions delete those stacks when the character loads (#545).

**Known:** life and mana leech on Nightmare and Hell is very small, as in Median XL 2012 (it divides leech by 100 and 200;
#540, checked against the original). The gamepad stash has no page arrows and no slots for Median's runes and gems. In
HD, Median's runes still show their classic pictures scaled up and the HD pet row shows at most 9 icons (D2R's own limit).

### 0.1.11 (2026-11-05)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.11:**

- The Barbarian's Guardian, Defender and Protector Spirit come back to you: a spirit more than 20 sub-tiles away teleports next to
  you, unless it is fighting a monster near you. After a fight they used to stay behind, 30 to 90 sub-tiles away (#534). Other summons and mercenaries are unchanged.
- Mercenaries use D2R's own AI settings: the Act 2 mercenary runs in to fight in melee and stays with you after a fight
  (it could lose you before). All mercenaries and summons were checked in game, in HD and legacy: they attack and follow
  (#534).
- The Fell Fiends' classic art has a new token (`FZ`, was `08`): a legacy game could ask for its files without the 0 and exit
  (#532). The crash was not seen here with the mod as shipped; the player's mod folder had another mod's D2RLoader files in it, so
  the mod's plugin did not load. Install D2R-XL 2012 into its own folder and do not copy another mod's `d2rloader` files over it.
- Legacy graphics (G) in Reign of the Warlock games: you no longer have to add `always_enable_rotw_legacy_graphics_keybind = true`
  to the mod's `d2rloader.toml` by hand. The downloader sets it on every install, update and repair, also in a file kept from
  an older install. A `false` there (set by hand or left by D2RLoader's template) becomes `true`, as the stat ranges
  setting is kept off. D2RLoader's own game-wide settings are not touched (#498).
- Cogs are yellow in HD as in classic, and so are the Cog shamans (#529). The other monsters with a classic colour of their own
  (Shadows, Lamias, Darklings, Daystars, the Thunder Bear, the Golden Calf and others, 60 in all) get that colour from a monster
  level now, so HD can draw it too. Cogs still cannot be healed. In Hell, Cogs and Cog shamans are still red in HD.
- The Horadric Cube window in HD matches classic Median XL's frame: its close button sits in the bottom right square as in classic (it was on the grid's top right corner, over a cell), and the side hinge no longer covers the grid's left frame and bottom left cells (#531).
- Hole Level 2 shows its cave walls in HD, and Median XL's edits of ten more original maps (Duriel's Lair, the
  Chaos Sanctuary heart, the Cathedral, the Harem, the Act 3 temples and dungeons, ...) are used: the game had loaded its own
  versions of those maps instead (#525). All ten were checked in HD against classic, and Duriel greets the player in his
  lair as in classic: he starts at the far end and rushes in.
- Batstrike and Bloodbath play their strike animations in HD, and Batstrike's nova spreads over its full radius in HD
  (it uses a stand-in look: green, not classic's orange-red, until custom art is made). Batstrike now spends its charges
  on the first Attack that lands, as all finishing moves do in classic, and its charm part converts monsters again (#526,
  #527).
- Batstrike's charm lasts 10 seconds at every level, as in classic; it lasted only as many frames as the character's
  level (2.4 s at level 60) (#527).
- Not bugs, the same as in classic Median XL 2012: Batstrike works without a weapon (an empty hand passes its claw
  requirement); swapping weapons releases the charges once with any weapon; Open Wounds comes only from the gnat family
  (Death Gnat, Blood Stinger, Soul Sucker, Razor Sting, Buzzsaw, ShockSting: 100 % per hit), not from other monsters
  (#527, #530).
- Holding Ctrl over an item no longer adds D2RLoader's "Possible base rolls" block: it printed the same line twice (or
  more) for many D2R-XL 2012 items, so D2RLoader's stat ranges are off for this mod for now (#528). The downloader also turns
  them off in a `d2rloader.toml` kept from an older release (`[d2rcore.items] item_stat_ranges = false`; nothing else in the
  file changes).

**New:**

- The downloader's log (`launcher.log`) now says how the downloader ended: closed by you, after Play, for its own update, by Windows signing out, or a crash, then its exit code. Its first line names the program that started it. If the window ever disappears, that log shows why (#539).
- The downloader keeps a copy of your shared stashes and characters before every install, update and repair, in
  `save-copies` in its data folder (the 10 newest stay). Your save folder is only read. If a shared stash ever shows a "bad
  header" error after an update, close the game and copy the files back from there (or from D2RLoader's own backups in
  `Saved Games\Diablo II Resurrected\D2RLoader Backups`), and please send us `d2rloader\logs\d2rloader.log` and the stash file
  (#536).
- The downloader has a **Play** button: it starts `D2RLoader.exe -mod mxl2012` from your D2R folder, so D2R-XL 2012 starts
  whatever D2RLoader's Default Mod is. It is on when D2RLoader 1.3.1 is there and D2R-XL 2012 is installed and up to date; the
  line under the panel says why when it is off. The downloader closes when the game starts (a check box turns that off).
  Starting `D2RLoader.exe` yourself still works.
- The personal stash has a second page. Open the stash and click the arrows under the grid to switch (page 2 shows
  "2 / 2"); Ctrl-click moves items between your backpack and the open page. Page 2 is D2RLoader's custom player page: its items are
  saved in `<character>.d2rl` next to the `.d2s`. **Keep the mod's plugin with your characters:** a character with items on
  page 2 does not load without it (D2RLoader stops the load, so nothing is lost). Move the items to page 1 first if you
  want to play that character without the plugin. The gamepad stash has no page arrows. On the Shared
  tab the arrows turn D2R's shared pages, as before.
- The shared stash has 2 more pages: 5 in a classic or expansion game, as a Reign of the Warlock game has (D2R gives those 3).
  Install, update and repair set `[d2rcore.stash] add_shared_tabs = 2` in the mod's `d2rloader.toml`; a higher number you set
  yourself is kept, so no page with items on it goes away (#535). The Gems, Materials and Runes pages of a RotW game are shared
  between your RotW characters, as in D2R.
- The downloader can install D2RLoader for you: when D2RLoader is missing or the wrong version, **Install D2RLoader**
  asks first, downloads it from its official site (d2rloader.net), checks it against the version pinned in the release,
  and puts it into your D2R folder. Your D2RLoader settings are kept. If that fails, **Get D2RLoader** opens the download
  page as before.

**Known:** the gamepad stash has no page arrows, and a character with items on personal page 2 needs the mod's plugin to
load. What caused one player's "bad header" shared stash error after an update is not known yet: if you see it, please
send us `d2rloader\logs\d2rloader.log` and the stash file (#536). In HD, Median's runes still show their classic pictures
scaled up and the HD pet row shows at most 9 icons (D2R's own limit).

### 0.1.10 (2026-11-01)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.10:**

- Reign of the Warlock stash pages (Gems, Materials, Runes): the small Horadric Cube window under the pages no longer
  draws the cube's items far past its frame. As in classic Median XL it shows the cube's lid; open the cube itself to see
  and use its items. The gem, rune and material slots are the same as in the unmodded game (#515).
- With a gamepad (D2R's controller UI) the Horadric Cube now uses Median XL's 10 x 8 cube and picture, not D2R's
  small 3 x 4 picture with the items spilling out of it (#523).
- Your own D2RLoader plugins in the game's `d2rloader\plugins` folder load next to D2R-XL 2012, as before. If one of them
  hooks game code that D2R-XL 2012 also changes, D2RLoader turns that hook down (that one feature of the plugin then does
  nothing). The `mxl2012` console command now names such a plugin and the D2R-XL 2012 part in the way
  (`plugin clashes: ...`), and the Downloader no longer deletes your `mxl2012-core-off.txt` (where that part's word turns it
  off) when it updates or repairs (#522).

**New in HD:**

- Witches (the sleeping witches of Terror's outdoor areas and the Witch Queen's tower) are now visible in HD, as a
  whole glowing Wraith; before, only one arm and a few blue wisps were drawn. A few other ghostly monsters with the same
  HD look (the Shadows among them) get their full body too. Classic graphics are unchanged (#524).

**Known:** in HD, Median's runes still show their classic pictures scaled up, Khalimgrad's cathedral has no tall
pointed arch and long roofed walls yet, and the HD pet row shows at most 9 icons (D2R's own limit). The stash's small
cube window shows only the cube's lid: items can't be dropped on it there.

### 0.1.9 (2026-11-01)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.9:**

- Median XL's own sounds (the witch's taunt, Singing Sun, skill shouts, item and monster sounds) are now heard
  every time, in HD and classic. In 0.1.8 the game only found them for a moment after switching graphics, so most
  of them stayed silent (#521).

**New in HD:**

- The Ancient Tunnels now float over the starry void like the Arcane Sanctuary, on walkways of the Sanctuary's own
  stone, where HD used to draw plain stone floor over the whole void.

**Known:** in HD, Median's runes still show their classic pictures scaled up, Khalimgrad's cathedral has no tall
pointed arch and long roofed walls yet, and the HD pet row shows at most 9 icons (D2R's own limit).

### 0.1.8 (2026-11-01)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.8:**

- Kurast: the Forgotten Temple (Upper Kurast) and the Disused Reliquary (Kurast Causeway) can be entered again; the
  unfolding stair in their doorway stayed shut and blocked the way (#518).
- Travincal (Act 3): fights with Glowing Ones no longer log an engine error when one dies; in HD they are now drawn as
  hunched green undead casters with a pale glowing head (#519).
- Classic graphics (G): the Arcane Sanctuary's magic shrine is drawn again, where it was invisible (#520).
- Classic graphics (G): pressing G with the stash open no longer risks a crash, and the stash tab names fit their tabs
  in full (#516).

**New:**

- Classic graphics (G): the Reign of the Warlock stash pages (Gems, Materials, Runes) now have a classic look, drawn down
  from D2R's HD pages (#516). Without Reign of the Warlock only Personal and Shared show.
- Median XL's own sounds now play: skill shouts and item and monster sounds Median added (102 of its 108; the other 6
  had no audio in Median XL either), in HD and classic, and boss taunts go out on D2R's boss-speech channel. Median's
  own versions of the class-select sounds, the gem sound and the werebear bites replace D2R's, in HD and classic.

**Known:** in HD, Median's runes still show their classic pictures scaled up, the Ancient Tunnels void around the
platform is drawn as floor, Khalimgrad's cathedral has no tall pointed arch and long roofed walls yet, and the HD pet
row shows at most 9 icons (D2R's own limit). Two of Median's sounds (the witch's taunt and Singing Sun) are not heard
yet (#521).

### 0.1.7 (2026-10-31)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.7:**

- HD: the Boss Killer Ring and the Upgraded Boss Killer Ring show their picture again (they showed an empty cell) (#513).
- HD: the names under the pet icons by the portrait no longer run into each other (#514).

**New in HD:**

- The Necromancer's summons (and the Overlord, Blood and Ice Elementals, Thunder Bear and Wolf Companion) have their own
  pet icons instead of all sharing the Necromancer's face (#514).
- New skill tree pages for all seven classes in D2R's own HD style: D2R's stone and carved sockets on Median's layout,
  each tree's colour as a rim round its sockets.

**Known:** in HD, Median's runes still show their classic pictures scaled up, the Ancient Tunnels void around the
platform is drawn as floor, Khalimgrad's cathedral has no tall pointed arch and long roofed walls yet, and the HD pet
row shows at most 9 icons (D2R's own limit).

### 0.1.6 (2026-10-30)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**New in HD:**

- Better D2R stand-ins for four more Median monsters: Dark Fey and Crystal (the Dark Spearwoman, teal / bright),
  Magma Demon (the Clay Golem) and Fungus (a smaller, blue Thorned Hulk).
- Rathma Primus is drawn as D2R's Oblivion Knight, a skeletal caster, instead of the Vampire.

**Known:** in HD, Median's runes still show their classic pictures scaled up (sharper versions are made and wait for
a review), the Ancient Tunnels void around the platform is drawn as floor, and Khalimgrad's cathedral has no tall pointed
arch and long roofed walls yet.

### 0.1.5 (2026-10-30)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.5:**

- Saves: the mod now checks at start that D2RLoader writes the extended save format. If your `mods\mxl2012\d2rloader\config\d2rloader.toml`
  lacks `[d2rcore.save_format] mode = "extended"`, it adds that key (the old file is kept as `d2rloader.toml.retail-backup`)
  and asks you to restart once; a failed save now shows a red line. The downloader (0.1.1) sets the same key when it keeps your own
  file. Without the key, every save failed while you carried many Median uniques, set items or runewords (#512).
- No more game close when walking through an area entrance with a mercenary ("Could not get act!", for example into the
  Underground Passage): the game now waits for the mercenary's new spot to load instead of closing (#511).
- Totems no longer stay on the player after Bend the Shadows next to rocks: when the free-spot test refuses the ring
  round the player, the totem is placed where the game's own move finds room (#509).
- Chat: the Act 5 soldiers' "Over here!" and "Help us!", which Median plays on some summons and spells, show at most once
  every 5 s each (Baal's laugh: once every 30 s) (#508).

**New in HD:**

- 43 more Median item pictures now use D2R's HD art of the same kind in Median's colours instead of a scaled-up classic
  picture: the Horadric Malus, scepters, Jolly Roger, scrolls, Token of Absolution, Sunless Crystal Bird, the Sunstones (the
  Sunstone of Thunder in yellow) and Class Rewards, Shadowfang, the Ingredient Rings, the oils (the Oil of Jewelcraft in pink),
  the clue gems, Fool's Gold and more, and the seven signets are a gold seal with their sign engraved. Median's runes keep
  their classic pictures for now (new ones are being worked on).
- Khalimgrad's cathedral (Hell 3) shows D2R's arches, gargoyle columns and Fortress huts with their roofs, and the
  downtown map its Harrogath trees, all from D2R's own models (the tall pointed arch and the long roofed walls stay without).
- Better D2R stand-ins for eight Median monsters: Centaur (Goatman), Deathwing (Desert Wing), Onyx Knight (Doom Knight),
  Fell Fiend (Venom Lord), Porkchop (Overseer), Pest (Fallen), and Belial and the Enforcer in their own colours.

**Known:** in HD, Median's runes still show their classic pictures scaled up (new ones are being worked on), the
Ancient Tunnels void around the platform is drawn as floor, and Khalimgrad's cathedral has no tall pointed arch and
long roofed walls yet.

### 0.1.4 (2026-10-30)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.4:**

- Reign of the Warlock stash: runes (Ith and all others), gems (Chipped Topaz and all others), skulls, rejuvenation
  potions and the Token of Absolution can now be put into the runes / gems tabs.
- "Baal says: *Laughing*" from Median's skills now reads "Baal says: LOL", at most once every 30 seconds.
- HD: the Rainbow Stones use D2R's crisp HD gem pictures in Median's colours.
- HD walls: Hole Level 2 has its stairs at the arrival, and Khalimgrad's cathedral has its Fortress walls in place (they
  floated several tiles off before) with many more of them drawn; downtown and glados get more walls too.
- Release notes: the line on HD item pictures now says about 90 Median-only ones are upscaled classic pictures.

**Known:** now and then one totem stays on your own spot after Bend the Shadows (often next to rocks); cast again or step
aside. In HD, the Ancient Tunnels void around the platform is drawn as floor, and Khalimgrad's cathedral has no arches and
roofs yet.

### 0.1.3 (2026-10-30)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.3:**

- Barbarian spirit summons (Guardian, Defender, Protector Spirit) no longer play the Ancients' HD death roar over and over.
- Totems: Bend the Shadows still brings them to you, but they no longer stack on you or slow down; in HD a moved totem no
  longer leaves its glass orb behind. Other pets keep D2R's placement.
- The Apple works again (heals as in Median XL 2012).
- No more "<name> says: Goodbye." and similar class voice lines in the chat.
- HD: the Veil King has pale swirling bands for his cloud; 16 Median effects that drew nothing in HD now show (Holy Armor,
  Pagan Heart, Thundergod, Amazing Grace, War Spirit, Firedance, Poison Flash and more); 48 states draw their colour shift.
- HD: Median's 8 retextured maps are lit in their own colours; all 17 Median maps show walls.
- Legacy graphics (G): Fire Wall's skill icon and the skill tab titles are right.

**Known:** now and then one totem stays on your own spot after Bend the Shadows (often next to rocks); cast again or step
aside. The Glacial Trail exit stands on a ledge; from the low pocket below it, clicking does nothing: walk round through the
other rooms.

### 0.1.2 (2026-10-29)

D2R-XL 2012 is a fan port of **Median XL 2012 (v005) by Brother Laz** to Diablo II: Resurrected. Median XL 2012 and its
files: <https://modsbylaz.vn.cz/>. Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods):
<https://www.nexusmods.com/profile/EnaiSiaion/mods>.

**Fixed in 0.1.2:**

- Legacy graphics (G): the red + buttons light up again after a level-up.
- Signet of Gold shows its gold value ("Gold in Bank: ...").
- Bane Hunter no longer flickers in HD.
- The Veil King has an HD look close to his legacy one (a gold-bronze crowned skeleton knight) and no neon green glow;
  Belial and a few other monsters lost the same green.
- Elvensong converts monsters again, as in the original.
- The inventory trophy names Median XL 2012 v005 (it said v004).
- Warlock: classic (legacy) art in Reign of the Warlock games, and the G toggle works there. **Updating from an older
  version** and keeping your `mods\mxl2012\d2rloader\config\d2rloader.toml`: add `always_enable_rotw_legacy_graphics_keybind = true`
  under `[d2rcore.player]` in it (new installs have it).

**Known:** the Glacial Trail exit stands on a ledge; from the low pocket below it, clicking does nothing. Walk round
through the other rooms.

**Also in this alpha (since 0.1.0):**

- Sacred amulets, rings, arrows and bolts and Anya's reward amulets get their automatic magic properties again, as in the
  original. The "upgrade dark ring" recipe takes its five items plus any sixth item, as it does in the original.
  docs/median-rules-audit.md (items)
- Greater Elixirs of Strength / Dexterity / Energy / Vitality now behave as in the original Median XL 2012: the red name only, no description line, and using one does nothing (the elixir stays). Median's data names states and text that do not exist, which 1.13c turned into exactly that. docs/bugs.md #104
- Warlock: its 30 skills scaled to Median XL 2012's power (damage, summons, mana anchored to Median's class skills of the
  same tier and role; only numbers changed). docs/warlock-balance.md
- Warlock, round 2 (owner answer: match Median's scaling): its skills follow Median's own rules. Skill points are gated as on
  Median's classes (one hard point per 6 character levels past the skill's level, with Median's "maximum level" tooltip line);
  the spells scale with character level and energy like Median's spells, the hexes, Blade Warp and Echoing Strike gain 10 %
  per character level like Median's weapon skills; Cleave and Mirrored Blades get a flat damage part that grows with
  character level; the demons take their life and damage from the skill as Median's summons do. D2R's per-skill damage
  synergies are gone from those skills and their tooltips, the spells show Median's energy bonus lines. Numbers refitted to
  Median's curve; the demons' pack size and a few missile synergies are left for later. docs/warlock-balance.md
- No raw text anywhere a player sees it: 46 names that showed their key (monsters, objects, potions, plurals) and 8 empty description lines now
  have text in words; Median's `PortalKombat` / `StataMater` read "Portal Kombat" / "Stata Mater"; the four bone prison monsters have a name;
  the inventory / cube / skill tree tooltips and the Warlock tab titles are written out instead of `@keys`. The build checks it (text audit).
