# invtabs: inventory tabs for D2R-XL 2012

A standalone D2RLoader 1.3.1 plugin (`invtabs.dll`) for D2R-XL 2012 on D2R 3.3 build 93847. It owns D2RLoader's custom
player page (item page 6), sets it to 16 x 16 and shows parts of it as tabs. The first tab is the charm tab (10 x 6 by
default), opened with the Charms button in the inventory, the console command `invtabs open` or the Controls action
"Inventory Tabs / toggle-charms". Charms saved by CharmInv 1.0.1 are in the charm tab as they are.

Design, interface for the other modules, address table and test results: [docs/invtabs.md](../docs/invtabs.md).

## Credit

invtabs is built from **wild-healer**'s Player Page Host 1.0.2 and Wild Healer's Charm Inventory
(<https://github.com/wild-healer/D2R-Tools>, commit `6722cc5`, `plugins/aaa-player-page-host` and
`plugins/wild-healers-charm-inventory`). The page registration and policies, the panel and grid layout, the procedural panel
background and sprite writer, the grid widget wrappers and the area packing are adapted from his code. His repository has
no licence file: all rights stay with wild-healer, and invtabs ships with the mod only after he agrees.

## Build and test

```
powershell tools\build_plugin.ps1 -Tests
py -3 tools\invtabs_sigs.py
```

The first builds `build\invtabs\Release\invtabs.dll` and runs `invtabs_tests`; the second checks every signature pattern
in `src/invtabs_natives.h` against the 93847 dump (`--make` derives them again). In game: `tools/game_checks.py` checks
`invtabs_seed` (with CharmInv) and `invtabs` (with `invtabs.dll` instead), see docs/invtabs.md.

## Config

`d2rloader\config\invtabs.toml` of the mod (embedded default: `invtabs.toml`, else `src/invtabs_default.toml`):

```toml
[invtabs]
enabled = true            # false: no tabs; the page is still registered so saved items load
inventory_charms = true   # charms count in the inventory too (Median rule)
open_button = true        # the Charms button in the inventory

[tabs.charms]
columns = 10              # 10..16
rows = 6                  # 4..16
```
