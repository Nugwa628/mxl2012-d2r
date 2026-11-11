# D2R-XL 2012

A fan port of **Median XL 2012 (v005) by Brother Laz** to **Diablo II: Resurrected**, running through
**D2RLoader 1.3.1** (tested on D2R 3.3 and 3.4). Mod folder `mods\mxl2012`.

## Credits

**Median XL 2012 is the work of Brother Laz.** Every skill, item, monster, map, string and piece of art the port carries
over is his; this project only moves it to Diablo II: Resurrected.

- Median XL 2012 and its files (the source of the mod files this port uses): <https://modsbylaz.vn.cz/>
- Brother Laz's mods on Nexus Mods (he also makes great Skyrim mods): <https://www.nexusmods.com/profile/EnaiSiaion/mods>

Shipped with the mod from 0.1.12: **Buff HUD** by **Lukaszpg** (<https://github.com/Lukaszpg/d2rl-buff-hud>, MIT; copyright
and licence notice in `mods\mxl2012\d2rloader\plugins\d2rl-buff-panel-LICENSE.txt`), in our fork for Median XL 2012
(<https://github.com/Nugwa628/d2rl-buff-hud>): a panel of your timed buffs with timers and names. Turn it off with
`enabled = false` in `mods\mxl2012\d2rloader\config\buff-panel.toml`. See [docs/bundled-plugins.md](docs/bundled-plugins.md).

Shipped with the mod from 0.1.17: **Controller QOL Updates** by **PyreFly** (<https://github.com/Pyre-Flies/D2R-Mods>,
`plugins/controller-qol`, shipped and adapted with PyreFly's permission): gamepad shortcuts for items (LB + A / X / Y, Deposit
All with LB + L3, also into the MEDIAN and ORBS stash tabs), direct ground looting with LB, menu and stash paging, and
right-stick aiming with a skill profile made for Median XL 2012's skills. Its belt shortcuts are off (Auto Belt Refill keeps
the belt). Settings: `mods\mxl2012\d2rloader\config\controller-qol-updates.toml`; your skill choices (R3 in the skill tree)
are kept in `controller-qol-skills\` next to it.

Shipped with the mod from 0.1.15: **Auto Belt Refill** by **jaycachou-svg** (<https://github.com/jaycachou-svg/auto-belt-refill>,
shipped and adapted with the author's permission; the repository has no licence file): refills the potion belt from your
inventory, by itself after you drink and on a key you bind (Options > Controls: Refill Belt). Each column refills with
exactly the potion at its bottom, a completely empty column stays empty until you put a potion there, and a small number on
each column shows how many of that potion you have left; elixirs are never moved. Set fixed columns, or turn it off with
`enabled = false`, in `mods\mxl2012\d2rloader\config\auto-belt-refill.toml`.

Shipped with the mod: **Inventory Tabs** (`invtabs`), our charm inventory of 10 x 6 cells with a summary of the charms'
bonuses, a classic-graphics panel and a gamepad tab, built on **wild-healer**'s Player Page Host and Charm Inventory
(<https://github.com/wild-healer/D2R-Tools>, used with his permission). Open it with the Charms button on the inventory
panel or a key you bind under Options > Controls. Median charms work there and, as before, in the normal inventory;
players who join a TCP/IP game can use it too. Settings: `mods\mxl2012\d2rloader\config\invtabs.toml`.

It replaces **CharmInv** by **Dimentio**, D2RLoader's author (<https://d2rloader.net/hub/plugins/charm-inventory>), which
the mod shipped in 0.1.19; charms kept in CharmInv's inventory are in the new one, in the same cells.

Shipped with the mod: our own plugin **D2R Legacy 16:9** (`legacy169.dll`, <https://github.com/Nugwa628/D2R-Legacy169>, MIT), the
classic graphics in 16:9 (1066x600 / 853x480). Turn it off with `enabled = false` in
`mods\mxl2012\d2rloader\config\legacy169.toml`.

Diablo II and Diablo II: Resurrected belong to Blizzard Entertainment. D2RLoader is its own project
(<https://d2rloader.net>). This port is not affiliated with or endorsed by Brother Laz or Blizzard. See [NOTICE.md](NOTICE.md).

## Playing it

You need your own Diablo II: Resurrected and D2RLoader 1.3.1 (tested on D2R 3.3 and 3.4). Each release's notes (on the Releases page)
explain the install step by step; the D2R-XL 2012 Downloader keeps the mod up to date. Characters live in their own save
folder and do not touch your normal D2R characters.

Works with **Reign of the Warlock (RotW)**: with the expansion on your Battle.net account you can also play the Warlock,
its skills rescaled to Median XL 2012's rules (still lightly tested). Legacy graphics (G) work in RotW games too.

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
