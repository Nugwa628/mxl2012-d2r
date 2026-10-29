# D2R-XL 2012

A fan port of **Median XL 2012 (v005) by Brother Laz** to **Diablo II: Resurrected 3.3**, running through
**D2RLoader 1.3.1**. Mod folder `mods\mxl2012`.

## Credits

**Median XL 2012 is the work of Brother Laz.** Every skill, item, monster, map, string and piece of art the port carries
over is his; this project only moves it to Diablo II: Resurrected.

- Median XL 2012 and its files (the source of the mod files this port uses): <https://modsbylaz.vn.cz/>
- Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods): <https://www.nexusmods.com/profile/EnaiSiaion/mods>

Diablo II and Diablo II: Resurrected belong to Blizzard Entertainment. D2RLoader is its own project
(<https://d2rloader.net>). This port is not affiliated with or endorsed by Brother Laz or Blizzard. See [NOTICE.md](NOTICE.md).

## Playing it

You need your own Diablo II: Resurrected 3.3 and D2RLoader 1.3.1. Each release's notes (on the Releases page)
explain the install step by step; the D2R-XL 2012 Downloader keeps the mod up to date. Characters live in their own save
folder and do not touch your normal D2R characters.

This is an **alpha**: playable, but expect bugs. Known issues are listed in each release's notes and in
[docs/bugs.md](docs/bugs.md). Report bugs with the issue templates (include `d2rloader.log` after a crash).

## What is in this repository

- `plugin/`: the D2RLoader plugin `mxl2012-core` (C++), the engine parts Median XL needs that D2R lacks.
- `tools/`: the build that turns Median XL 2012's files into a D2R mod (tables, strings, maps, HD art), the test harness
  and game checks, and the release tools.
- `launcher/`: the D2R-XL 2012 Downloader.
- `docs/`: how everything works and what is left. Start with [docs/PLAN.md](docs/PLAN.md), [docs/setup.md](docs/setup.md)
  and [docs/porting-playbook.md](docs/porting-playbook.md).

No Median XL or Blizzard game files are in git. Building the mod yourself needs your own D2R install and Median XL 2012's
files (docs/setup.md).

## License

The project's own code and docs are MIT ([LICENSE](LICENSE)). Median XL 2012's content stays Brother Laz's; Diablo II's
stays Blizzard's ([NOTICE.md](NOTICE.md)).
