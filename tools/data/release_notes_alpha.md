# D2R-XL 2012 {version} (alpha)

D2R-XL 2012 is Median XL 2012 (v005, by Brother Laz) running in Diablo II: Resurrected through
D2RLoader and the plugin mxl2012-core {plugin}. This is an **alpha**: it is playable, but expect bugs and crashes, and
expect to start new characters for later versions.

The download is `{archive}` ({archive_mb} MB; {file_count} files, {unpacked_mb} MB unpacked). SHA256SUMS holds its checksum.

## What you need

- **Diablo II: Resurrected at build {build}** (D2R {d2rver}) exactly. On any other build the mod's engine part switches
  itself off and shows a red line at the top of the screen: "D2R-XL 2012 {plugin} needs D2R build {build}; this is ...".
  Keeping your D2R at that build is up to you.
- **D2RLoader {loader}** exactly (not an older or newer one), from https://d2rloader.net/download.html.
  The file is `{loader_url}`; its SHA-256 is `{loader_sha}`.
- About {unpacked_mb} MB of free space in the D2R folder.
- 7-Zip (https://www.7-zip.org) if your Windows does not open .7z files (Windows 11 does).

## Install

1. **D2RLoader.** Unzip the D2RLoader {loader} zip and copy everything in it (`D2RLoader.exe`, `D2RCore.dll`,
   `d2rloader.mpq` and the `d2rloader` folder) into your D2R folder, next to `D2R.exe`.
2. **The mod.** {unpack}
   Make the `mods` folder first if your D2R folder has none.
3. **Default Mod.** Start `D2RLoader.exe`. On the character screen click the gear, set Default Mod to **D2R-XL 2012**,
   press Apply, close the game and start `D2RLoader.exe` again. (Or put `default_mod = "mxl2012"` under `[d2rloader]` in
   `<D2R folder>\d2rloader\config\d2rloader.toml`.)
4. Play: always start the game with `D2RLoader.exe`. Starting D2R through Battle.net starts the normal game without the mod.

The first start after installing or updating D2RLoader or D2R takes longer, and the mod may show a message asking you to
close the game and start it again: do that once, the next start is right.

## Your characters

Characters of the mod are saved in `Saved Games\Diablo II Resurrected\mods\{save_folder}` (in your user folder). They are
separate from your normal D2R characters, which the mod does not touch. Back that folder up if you care about them.

## Update to a newer alpha

Close the game, delete `<D2R folder>\mods\mxl2012\mxl2012.mpq\data`, then unpack the new 7z into `<D2R folder>\mods\`
as in step 2. Keep `mods\mxl2012\d2rloader\config\d2rloader.toml` if you edited it. Read the new notes first: a new alpha
may not load characters of an older one.

**Legacy graphics (G) in Reign of the Warlock games** need one line in the mod's own settings. New installs have it. If you update and keep your old `mods\mxl2012\d2rloader\config\d2rloader.toml`, add these two lines to it (or delete that file before unpacking, if you never edited it):

```
[d2rcore.player]
always_enable_rotw_legacy_graphics_keybind = true
```

## Remove

Delete `<D2R folder>\mods\mxl2012`. Your characters stay in `Saved Games` until you delete them yourself.

## Known issues

What we know is wrong or different. Please don't report these again, unless you find a new way to cause them.

**Can end your game**

- **Pandemonium 2 by town portal.** Opening a town portal in the second Pandemonium area and stepping back through it from
  town closes the game. The normal game has no way into that area, so you should not meet this.
- **Colossal Summit.** Entering D2R's own Colossal Summit area (Reign of the Warlock) closes the game. Median XL 2012 has no
  way in; if you find one, please report it.
- **Very long sessions.** After many areas and town visits in one session the game may write an "asset cache" warning to its
  log; it goes on, but if it gets slow or stops after hours of play, restart it and tell us how long you had played.

**Looks or reads different**

- **Stand-in HD art.** Many Median-only monsters, missiles, effects and items show a borrowed or recoloured D2R model or
  picture in HD. Legacy graphics (G) show Median's own classic art where it has one.
- **Median's own maps show D2R's walls in HD.** The 17 maps that Median added or changed have D2R's own walls in Median's
  layout in HD, lit in each map's own colour as in legacy mode; 3 of them show only part of their walls (Hole Level 2, Ancient Tunnels, and
  Khalimgrad's cathedral). Legacy graphics (G) show them as Median drew them.
- **Item pictures in HD:** most are Median's classic pictures scaled up, so they look softer than D2R's own.
- **Skill trees in HD** are Median's classic page art scaled up.
- **A few names** that Median XL 2012 itself never wrote (some potions, monsters and objects) show a name we gave them.
- **Chronicle:** making some runewords (for example Kyrie) names the base item in the chat message; the item itself is right.

**Plays different from Median XL 2012 (on purpose, D2R's features kept)**

- Kashya hires mercenaries from character level 8 even before her quest is done.
- D2R's shared stash tabs, materials tab, Chronicle, loot filter and auto gold pick-up are there; Median had none of them.
  As in D2R, quest items (the Horadric Cube, Wirt's Leg, the Bark Scroll, Khalim's parts and so on) cannot go into the
  shared tabs, also not by Ctrl-click; keep them in the Personal tab.
- The mercenary panel lists the mercenary's skills; some auras there read "Attack".

**Other**

- **Warlock.** It needs the Reign of the Warlock expansion on your Battle.net account. Its skills were rescaled to Median's
  rules but it is **untested in play**.
- **The save format may change.** Characters made with this alpha may not load in a later version.
- **Acts 2 to 5 are only lightly tested.**
- **Glacial Trail exit.** The exit stands on a ledge. From the low pocket below it, clicking the exit does nothing (there is
  no path up from there): walk round through the other rooms to reach the ledge.
- English text only.

## How to report a bug

Tell the person who gave you this copy. Please send:

1. **What happened:** what you did just before, what you saw (a screenshot helps: Print Screen), and whether it happens
   again when you do the same thing.
2. **Where:** your character's class and level, difficulty, act and area (the area name shows at the top right of the
   automap, Tab), and whether you play in HD or legacy graphics (G).
3. **Which version:** {version} (the name of the 7z you unpacked).
4. **The logs, right after it happened** (they are rewritten at every start, so copy them before you start the game again):
   - `<D2R folder>\d2rloader\logs\d2rloader.log` (D2RLoader's log: engine warnings and crashes),
   - `<D2R folder>\mods\mxl2012\d2rloader\logs\mxl2012-core.log` (the mod's own log),
   - after a crash, also the newest files in `<D2R folder>\d2rloader\crashes\`.

Don't send your character files unless asked: they hold your character's name.

## Credits

Median XL 2012 is the work of Brother Laz: every skill, item, monster, map and piece of art in this mod is his.
Median XL 2012 and its files: https://modsbylaz.vn.cz/ . His mods on Nexus Mods (he also makes great Skyrim mods):
https://www.nexusmods.com/profile/EnaiSiaion/mods . Diablo II: Resurrected is Blizzard's; the mod needs your own
copy of the game and does not include it. D2RLoader is by its own authors (https://d2rloader.net).
