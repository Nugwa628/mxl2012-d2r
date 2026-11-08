# Controller QOL Updates for D2R-XL 2012: our patches

PyreFly's controller-qol (<https://github.com/Pyre-Flies/D2R-Mods>, `plugins/controller-qol`, version 1.3.1+rev.95) is shipped
with the mod by PyreFly's permission (given to the project owner on 2026-11-04; the repository's LICENSE reserves all rights).
The gitlink `third_party/D2R-Mods` pins PyreFly's commit `df44457` (2026-10-30, the newest on 2026-11-08). PyreFly's
repository is never changed: `tools/build_controllerqol.ps1` exports `plugins/controller-qol`, `plugins/inventory-deposit/src`
and `/tests` and `LICENSE` of that commit, applies the patches here in name order, builds the plugin and its 63 unit tests
against the project's PluginSDK (`717f727`; PyreFly pins `bb0b48e`, the one commit between them changes comments and the
README only) and embeds the mxl2012 skill seed (docs/controller-support.md section 5) as its skill defaults. docs/bundled-plugins.md
has the rest.

PyreFly's sources are CRLF: the patches keep their CR bytes (`.gitattributes`: `-text`). To change a patch, edit the exported
copy in `build/controllerqol-src` and diff it against a fresh export with `git -c core.autocrlf=false diff --no-index`.

- `0001-mxl2012-belt-actions-switch.patch`: a `[qol]` key `belt_actions` (default true, as upstream; restart). False skips the
  belt module (LB + A on a potion, LB + R3 refills, merchant refills) and logs "Potion shortcuts off (belt_actions = false)".
  The embedded and shipped `controller-qol-updates.toml` set it false, so Auto Belt Refill keeps the belt.
- `0002-mxl2012-median-orbs-tabs.patch`: the stash's tabs 5 (MEDIAN) and 6 (ORBS) are advanced tabs. The tab getter answers
  the real tab to this plugin (our medtab part caps it for D2R's own callers only), so without the patch the plugin refused
  every advanced action there. With it: Deposit All (LB + L3), LB + X and the embedded-Cube routes accept 5 and 6, their slots
  are looked up under `advancedstash_runes` (where tools/median_tabs.py puts them), and slot names accept Median's code
  characters (A-Z, `! $ & + ^`; `@` as the layouts' `_`). Three upstream tests that used 5 as the "unknown tab" use 7 now,
  with new checks for 5 and 6.
- `0003-mxl2012-hooked-sound-entry.patch`: mxl2012-core's part `spiritsound` (bug #502) inline-hooks `0x1a0780`, D2R's client
  sound play, which controller-qol calls after a transfer and checks 0x21 bytes of. Deposit All checked them in raw memory, so
  every LB + L3 was refused ("Native deposit contract unavailable") and D2R's own L3 (Open Cube) ran instead. The new
  `hooked_entry_policy.h` checks only the bytes after the hooked 13-byte prologue (a check of the prologue would fail and log
  an error on every poll); Deposit All, the advanced LB + X route and the Materials withdrawals use it.

Not changed (docs/controller-support.md section 5 lists them): the ground-loot ranking of runes and gems (vanilla code
prefixes), the belt candidate list (off anyway), charm / jewel ranks.
