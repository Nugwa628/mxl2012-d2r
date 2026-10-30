# Changelog

Release notes of D2R-XL 2012, newest first. `tools/github_release.py` and `tools/package_release.py` read the section of the
version being released (docs/release.md).

## Unreleased

- "Baal says: *Laughing*" from Median's skills now reads "Baal says: LOL", at most once every 30 seconds.
- Release notes: the line on HD item pictures now says about 90 Median-only ones are upscaled classic pictures.
- HD walls: Hole Level 2 has its stairs at the arrival, and Khalimgrad's cathedral has its Fortress walls in place (they
  floated several tiles off before) with many more of them drawn; downtown and glados get more walls too.

## D2R-XL 2012

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
