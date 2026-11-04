# Third-party D2RLoader plugins planned to ship with D2R-XL 2012

Planned 2026-11-04. Not shipped yet; add new candidates to the tables below. The compatibility work (which plugins
need changes for Median XL 2012's data)
starts after release 0.1.11. Each plugin keeps its author's credit in the release notes, the README credits and this file.

## PyreFly's plugins

By **PyreFly** (<https://github.com/Pyre-Flies/D2R-Mods>). Shipped with PyreFly's permission (given to the project
owner, 2026-11-04). Their READMEs state no licence, so the permission is the basis for shipping them.

| Plugin | What it does | Likely work for Median XL 2012 |
|-|-|-|
| [controller-qol](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/controller-qol/README.md) | Controller shortcuts for item actions, direct ground looting, menu navigation, optional right-stick skill aiming | Skill behaviour is keyed to numeric skill ids with per-mod profiles: needs an mxl2012 profile for our skills |
| [pyre-lootfilter](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/pyre-lootfilter/README.md) | Ground loot filter from `filter.json`, minimap icons, pickup guard | Reads weapons.txt, armor.txt, itemtypes.txt, item codes and stat ids: needs a filter written for Median's items |
| [pyre-stashsearch](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/pyre-stashsearch/README.md) | Search across the Personal and Shared stash pages, boolean stat filters, highlighted matches, renamable side tabs | Check with the mod's 5 / 7 shared pages (`add_shared_tabs`, bug #535) and Median's stat names |
| [item-roll-ranges](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/item-roll-ranges/README.md) | Shows each modifier's possible roll range and source while Ctrl / RT is held | Reads the active game's affixes, uniques and runewords; check against Median's tables and D2RLoader's own Ctrl stat ranges, which the mod turns off (`item_stat_ranges = false`, bug #528): make sure only one draws |
| [inventory-deposit](https://github.com/Pyre-Flies/D2R-Mods/blob/main/plugins/inventory-deposit/README.md) | "Deposit all gems, materials and runes" button by the inventory gold | Needs the HD advanced stash and its item-type rules; Median items with no slot on the open page stay put (bug #535 side note: such an item logged item asserts) |

All five target D2RLoader 1.3.1 and plugin ABI 4 on Windows x64, the same loader the port uses.

## Checks before shipping (after 0.1.11)

- Each plugin loads next to mxl2012-core without hook conflicts, in HD and in legacy graphics.
- The mod-specific data (controller skill profile, loot filter, deposit item types) is written for Median XL 2012.
- Item-roll-ranges vs D2RLoader's stat ranges (off in the mod, #528): only one may draw.
- The installer and the Downloader install them into `mods\mxl2012\d2rloader\plugins\`, pinned by checksum like D2RLoader.
- Release notes and README credit PyreFly.
