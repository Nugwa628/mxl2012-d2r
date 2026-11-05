# Changelog

Release notes of D2R-XL 2012, newest first. `tools/github_release.py` and `tools/package_release.py` read the section of the
version being released (docs/release.md).

## Unreleased

## D2R-XL 2012

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
