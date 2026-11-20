# Vendor Stock Refresh 2.1.7 by RuffnecKk (bundled D2RLoader plugin)

Vendor Stock Refresh adds the gamble screen's refresh button to the HD trade screen of every vendor. A click rerolls the
vendor's normal stock on the spot, for free, as often as the player likes. Gambling keeps its own refresh. Docs:
[docs/bundled-plugins.md](../../docs/bundled-plugins.md) "Vendor Stock Refresh".

- **Author:** RuffnecKk, <https://github.com/RuffDood>.
- **Source:** <https://github.com/RuffDood/RuffnecKk-D2RLoader-Suite>, `plugins/vendor-stock-refresh`, at commit
  `514359f7b27fbc1026c17e7e2b440179fefdf9ba`, the gitlink `third_party/RuffnecKk-D2RLoader-Suite` that Floating Damage is
  built from. Built unchanged by `tools/build_vendorstockrefresh.ps1` (no patches).
- **Companion MPQ:** `d2rl-ruffneckk-vendor-stock-refresh.mpq` (the button art) is not in the repository. It is the file
  from the author's hub release 2.1.7 (<https://d2rloader.net/hub/plugins/vendor-stock-refresh>, released 2026-11-03,
  D2R 3.3, D2RLoader 1.3.1).
- **Licence:** MIT, "Copyright (c) 2026 RuffnecKk and contributors" (the suite's LICENSE, shipped next to the DLL as
  `d2rl-ruffneckk-vendor-stock-refresh-license.txt`, with the suite's third-party notices). The hub release has no
  licence file of its own; the MPQ is the author's art from the same suite. Credit: README, NOTICE.md, CHANGELOG and
  docs/bundled-plugins.md.

| File | Size | sha256 |
|-|-|-|
| `d2rl-ruffneckk-vendor-stock-refresh.mpq` | 5,651,640 | `0014c677e24979275307fd2194b4d6c31167a46ab8eb9c0f005b6a8cddedc5f6` |

The source checks the same hash before it loads the MPQ (`src/companion_hash.hpp`). `tools/package_release.py`
(`VSR`) refuses any other bytes. The DLL is reproducible (`/Brepro`): our build of the pinned commit has sha256
`d0f22528ae0f89727f02...` on the build machine of lane plug127.

## Where the MPQ lives

It is not in git (`.gitignore` excludes `*.mpq`). `tools/package_release.py` takes it, checked against the hash above,
from the first of these:

1. `--vsr-mpq DIR`,
2. the environment variable `MXL_VSR_MPQ_DIR`,
3. this folder (`third_party/vendor-stock-refresh/d2rl-ruffneckk-vendor-stock-refresh.mpq`, a local copy, git-ignored),
4. `<MXL2012_RUNS>/shared/vendor-stock-refresh-2.1.7/`.

To get it, download release 2.1.7 from the hub page above and take the MPQ from its `plugins/` folder.

## Our settings

The shipped `ruffneckk-vendor-stock-refresh.toml` is the author's config from the pinned commit: on, diagnostics off.
It is a `preserve` file, so a player's changes survive Update and Repair. `tools/verify_package.py` checks both keys.

## How it decides to work

It hooks the vendor panel set-up and the client refresh send, and on the server the vendor interaction and the entity
action packet (`0x38`, action `VSRF`, rewritten to the game's own trade action). Every hook checks the expected bytes
first, and it checks the D2RCore packet relay; it has no game-version gate of its own. In legacy graphics it finds no
gold anchor on the classic panel and leaves the button out (it logs that once per panel). In game (lane plug127)
mxl2012-core reported no plugin clashes.

To move to a new version, move the gitlink (with Floating Damage), update `VSR` (version, MPQ hash) in
`tools/package_release.py` and this README, and run the in-game check (docs/testing.md "Lane plug127").
