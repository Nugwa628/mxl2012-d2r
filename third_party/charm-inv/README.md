# CharmInv 1.0.1 by Dimentio (bundled D2RLoader plugin)

CharmInv adds a separate **Charm Inventory** panel to D2R: a button on the player inventory, an input action (Options >
Controls) and a controller inventory tab open it. It keeps its items on D2RLoader's one custom player page (item page 6 of
the `.d2s`). Docs: [docs/bundled-plugins.md](../../docs/bundled-plugins.md) "CharmInv".

- **Author:** Dimentio (also the author of D2RLoader). CharmInv is a direct extension of D2RLoader.
- **Source:** the user-supplied zip `CharmInv-1.0.1`, downloaded from <https://d2rloader.net/hub/plugins/charm-inventory>.
  It holds only `d2rloader/plugins/d2rl-charm-inv.dll` and `d2rloader/plugins/d2rl-charm-inv.mpq` (no readme, no licence).
  No source code is published; we ship the author's binaries unchanged.
- **Licence:** redistributed with D2RLoader by the owner's decision (author: Dimentio, D2RLoader's author), 2026-11-10.
  Credit: README, NOTICE.md, the release notes / CHANGELOG and docs/bundled-plugins.md.

| File | Size | sha256 |
|-|-|-|
| `d2rl-charm-inv.dll` | 68,952 | `b14f6a0bd4c9df0af9c392ea97dc879ad3760592481517dbdb0983595145d88b` |
| `d2rl-charm-inv.mpq` | 9,591,921 | `e01163aac3b0d76c3cbdad56e19350692864b51484d9ad6dfbc41f28023fb0ac` |

The DLL is Authenticode-signed "Dimentio". `tools/package_release.py` (`CHARMINV`) refuses any other bytes.

## Where the two files live

They are not in git (the repository holds no binaries; `.gitignore` excludes `*.dll` / `*.mpq`, and the MPQ's HD panel art is
9.6 MB). `tools/package_release.py` takes them, checked against the hashes above, from the first of:

1. `--charminv DIR` (a folder holding both files),
2. the environment variable `MXL_CHARMINV_DIR`,
3. this folder (`third_party/charm-inv/d2rl-charm-inv.dll` / `.mpq`, a local copy, git-ignored),
4. `<MXL2012_RUNS>/shared/charm-inv-1.0.1/` (the build PC's shared copy).

## What is in the package

`mods\mxl2012\d2rloader\plugins\d2rl-charm-inv.dll` + `d2rl-charm-inv.mpq` (mod-scoped) and our config
`mods\mxl2012\d2rloader\config\charm-inv.toml` (this folder's `charm-inv.toml`, a `preserve` file: a player's changes
survive Update and Repair). Our settings differ from CharmInv's embedded default in one key: `allow_inventory_charms = true`
(Median's charms keep working from the normal inventory; the owner's decision).

The mod's own data overrides two CharmInv files by the same virtual path (mod data wins over a plugin's companion MPQ):

- `data/global/excel/d2rloader/charm-inv/charminvtypes.txt` and `charminv.txt`: Median's charm item types and the 10 x 4
  grid (`tools/charm_inv.py`, a `tools/build.py` data step).
- the strings `d2r:Charmdes` / `d2r:ItemExpcharmdesc` (CharmInv: "Keep in Charm Inventory to Gain Bonus"): ours name both
  places (`data/d2r_string_fixes.json`).

## What the MPQ holds (1.0.1)

```
data/d2rloader/compiler/table-schemas.json                       plugin charm-inv: tables charminv, charminvtypes (RotW bank)
data/global/excel/d2rloader/charm-inv/charminv.txt / .bin        Id gridX gridY: charm-inv 10 4
data/global/excel/d2rloader/charm-inv/charminvtypes.txt / .bin   itemType: char
data/global/ui/layouts/charm-inv/CharmInvPanelhd.json            the panel (HD only: no legacy layout)
data/global/ui/layouts/charm-inv/InventoryButtonhd.json          the button in the player inventory (x 3, y 672)
data/global/ui/layouts/controller/charm-inv/CharmInvControllerPanelhd.json
data/hd/global/ui/d2rloader/charm-inv/*.sprite                   panel / button art (+ .lowend)
data/local/lng/strings/d2rloader/charm-inv/strings.json          CharmInvPanelTitle, d2r:Charmdes, d2r:ItemExpcharmdesc
```

To move to a new version: put the new files where package_release looks, update `CHARMINV` (version, sizes, hashes) in
`tools/package_release.py` and the table above, check the MPQ's tables / layouts / strings again (`py -3 -I
tools/mpq_dump.py d2rl-charm-inv.mpq <out>`), and run the in-game check (docs/testing.md "Lane charminv").
