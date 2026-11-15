# D2R Advanced Stats

A D2RLoader plugin for Diablo II: Resurrected that turns the character sheet into a stat book: pages of the stats the
game normally hides, with tabs on top of the sheet or down the side of a panel beside it.

![The Offense page with the tabs on top of the sheet (plain D2R)](docs/images/top-tabs-offense.png)

- **Pages with tabs.** Character (D2R's own sheet), Offense, Spells, Defense, Resistances, Skills & Procs, Utility and All
  Stats. Every value is the character's current one; zero is grey, negative red, capped gold. Chance to Block is D2R's own
  block rate, not a sum of stats.
- **Top or side tabs.** Folder tabs on the sheet (default), or the book as a panel beside the sheet with its tabs down its
  side, where D2R's Advanced Stats panel sits. A button in the corner of the book switches between the two, live, and so
  does a rebindable Controls action.
- **All Stats with search.** Every stat the character has, sorted into groups (Offense, Spell Damage, Defense,
  Resistances, Speed, Life & Mana, ...), filtered as you type. The arrow on a row opens the page that has it.
- **Magic and Physical Resistance and Chance to Block** on the pages; with the D2R-XL 2012 mod also as rows on the sheet
  itself.
- **Grouped Advanced Stats.** With the D2R-XL 2012 mod, D2R's Advanced Stats panel is sorted into the same groups.
- **Gamepad.** With the D2R-XL 2012 mod the gamepad sheet gets the tabs too, stepped with LT / RT (LB / RB with the
  Controller QOL plugin).

Side tabs, with the Offense page:

![The book beside the sheet with its tabs down the side (plain D2R)](docs/images/side-tabs-offense.png)

All Stats, searching for "speed":

![All Stats with a search (plain D2R)](docs/images/all-stats-search.png)

With D2R-XL 2012: Magic and Physical Resistance on the sheet, the Defense page, and the Resistances page on the side:

![The character sheet with Magic and Physical Resistance rows (D2R-XL 2012)](docs/images/sheet-magic-physical-resistance.png)
![The Defense page (D2R-XL 2012)](docs/images/top-tabs-defense.png)
![The Resistances page beside the sheet (D2R-XL 2012)](docs/images/side-tabs-resistances.png)

## Requirements

- Diablo II: Resurrected with **D2RLoader 1.3.1**. The plugin checks the game code it runs on: under another D2RLoader
  version it loads, says so in its log and changes nothing.
- HD graphics. Legacy (classic) graphics keep D2R's own sheet.
- Offline / single player (D2RLoader).

## Install on plain D2R

The Stat Book's own art (tabs, row cells, the side panel frame, the toggle button) is game data, and D2R reads game data
only from a mod, so the release is a small, otherwise empty mod called `AdvancedStats`:

1. Install D2RLoader 1.3.1 and start the game through it once.
2. Unpack `d2r-advanced-stats-<version>.zip` into the game folder (the folder with `D2R.exe`). It adds
   `mods\AdvancedStats\` and nothing else:
   ```
   mods\AdvancedStats\modinfo.json
   mods\AdvancedStats\AdvancedStats.mpq\modinfo.json
   mods\AdvancedStats\AdvancedStats.mpq\data\hd\global\ui\panel\statbook\*.sprite
   mods\AdvancedStats\d2rloader\plugins\statbook.dll
   mods\AdvancedStats\d2rloader\config\statbook.toml
   ```
3. Start the mod: `D2RLoader.exe -mod AdvancedStats` (for example in a shortcut), or pick AdvancedStats as the Default
   Mod in D2RLoader's settings.
4. In game, open the character sheet (C).

The mod keeps its own save folder (`Saved Games\Diablo II Resurrected\mods\AdvancedStats\`), as D2R does for every mod
with a `savepath`. To play an existing character there, copy its files into that folder (keep a backup).

If the sprites are missing from the mod, the book still works and uses D2R's stock sprites instead (the stash tab for the
tabs, plain rows); the `statbook` console command says which art is in use.

To remove it, delete `mods\AdvancedStats\`.

## With D2R-XL 2012

D2R-XL 2012 (the Diablo II: Resurrected port of Median XL 2012) bundles this plugin, with its own book (Median's
stats, caps and pages), its sheet layouts (the resistance rows, the gamepad tabs) and the grouped Advanced Stats panel.
Nothing to install there; its settings are in `mods\mxl2012\d2rloader\config\statbook.toml`.

## Settings

D2RLoader writes the default `statbook.toml` into the matching `d2rloader\config\` folder on the first start (the same file
is in this repository). Changes apply at the next game start, except `tabs`, which the toggle switches in game and writes
back.

```toml
[statbook]
sheet_rows = true       # the Magic / Physical Resistance rows on page 1 (in sheet layouts that have them: D2R-XL 2012)
advanced_stats = true   # D2R's Advanced Stats panel sorted into groups (with D2R-XL 2012's book)
book = true             # the themed pages and All Stats
tabs = "top"            # "top": folder tabs on the sheet; "side": the book as a panel beside the sheet
pad_tabs = "auto"       # gamepad tab buttons: auto (LB / RB with Controller QOL, else LT / RT), bumpers, triggers or off
pad_bumper_left = 19    # D2R's controller action ids of LB, RB, LT, RT (-1: off)
pad_bumper_right = 20
pad_trigger_left = 7
pad_trigger_right = 8
pad_log = false         # log every controller action the gamepad menu gets to statbook.log
```

**Controls:** the action "Stat Book: Top/Side Tabs" switches the tabs. It is unbound by default; bind a key in
Options > Controls (it is listed in the category "Advanced Stats").

The plugin writes its log to `statbook.log` in `d2rloader\logs\`. D2RLoader's console has the command `statbook` (status),
`statbook page <n>` (a page's lines with your values) and `statbook tabs top|side|toggle`.

## Building from source

Windows x64, CMake 3.29 or newer, Visual Studio with the C++ workload (built and tested with Visual Studio 2026):

```powershell
cmake -S . -B build -A x64
cmake --build build --config Release --target statbook statbook_all_tests
ctest --test-dir build -C Release
py -3 tools/package.py --dll build/Release/statbook.dll     # dist/d2r-advanced-stats-<version>.zip
```

The configure step fetches the [D2RLoader PluginSDK](https://github.com/D2RLoader/PluginSDK) (MIT) at the commit pinned in
`CMakeLists.txt`. To build without network access, point it at a local checkout of that commit:
`cmake -S . -B build -A x64 -DSTATBOOK_PLUGINSDK_DIR=<PluginSDK folder>`.

Output: `build\Release\statbook.dll` (no VC++ runtime needed). The unit tests cover the book, the config, the resistance
rows, the grouped Advanced Stats and the sheet host's page logic; they need no game.

Pages and rows are data: edit `data/statbook_pages.tsv` (and `data/advanced_stats.tsv` for All Stats) and regenerate the
compiled-in book with `py -3 tools/statbook.py default`. That and the art and layout tools need files from your own D2R
install; see [docs/statbook.md](docs/statbook.md) ("Data", "Art and layouts") and `tools/d2r_paths.py`.

Layout:

| Path | What |
|-|-|
| `src/` | the plugin: `statbook.cpp` (entry, settings, console, gamepad), `sheet_host.cpp` (tabs, pages, All Stats), `sheet_resist.cpp`, `advstats.cpp`; the pure logic in `*_logic.h` |
| `src/shared/` | native panel helpers shared with D2R-XL 2012's core plugin (typing into a text box, layout registration, D2R's block rate) |
| `tests/` | unit tests of the pure parts |
| `data/` | the page and All Stats tables, and the plain install's sprites (`data/hd/...`) |
| `tools/` | the book, layout and art generators, the release packer |
| `docs/` | [how it works](docs/statbook.md), [the widget names](docs/statbook-layout.md) |

## Credits and thanks

- Built for **D2R-XL 2012**, the Diablo II: Resurrected port of Median XL 2012 (Median XL 2012 by Brother Laz), and
  released on its own for plain D2R.
- **D2RLoader** and its PluginSDK: plugin loading, widgets, panels, hooks, config, console and logs.
- **Controller QOL Updates** by PyreFly: the gamepad tab buttons follow its button layout when it is loaded.
- **Blizzard Entertainment** for Diablo II and Diablo II: Resurrected.

## License

MIT ([LICENSE](LICENSE)) for the code, tools and docs. The sprites in `data/hd/` are built from Diablo II: Resurrected's
own HD interface art (the character sheet, the stash tab, the Advanced Stats frame, the level-up button) and are included
for use with the game; that art belongs to Blizzard Entertainment. Diablo II and Diablo II: Resurrected belong to Blizzard
Entertainment; this project is not affiliated with or endorsed by Blizzard Entertainment or the D2RLoader project.
