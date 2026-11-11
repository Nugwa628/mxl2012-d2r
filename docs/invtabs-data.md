# Inventory tab data for D2R-XL 2012

## Core integration contract

This lane supplies a pure C++ header, not plugin lifecycle wiring. Include
`src/tab_config.h`. At plugin initialization read `d2rloader/config/invtabs.toml`
using the core's TOML reader. `[invtabs]` controls enabled, inventory_charms,
open_key (Windows virtual key, 0 disables), open_button (mouse inventory button),
controller_button (controller navigation entry) and inactive_charm_tint (four
RGBA integers, 0..255). Defaults are documented beside every key in
`invtabs/invtabs.toml`. Respect inventory_charms on every player's charm rule.

After CustomTableService / DataTablesLoaded makes itemtypes available, read
`data/global/excel/d2rloader/invtabs/tabs.txt`, then each referenced types file.
Call `invtabs::ParseTabs(text, tabs, error)` and `ParseTypes(text, tab, error)`;
then `Validate(tabs, accessor, error)` before leasing any page rectangles.
Accessor signature: `bool(const std::string& code, invtabs::TypeRow& out)`;
return false for missing rows, and copy Code, Equiv1, Equiv2 from itemtypes.
`Matches(tab, itemTypeCode, accessor)` admits an exact listed code or either
parent chain; cycles terminate and unknown rows fail closed. Use the item's
type from game data, never infer dimensions or type from its item code.
Validate again on table reload; publish the new configuration atomically only
after every tab passes. Log an invalid configuration and disable its new leases;
never delete or move saved items because parsing failed.

If the tab list is absent, `CharmFallback()` supplies a 10 x 6 charm tab with
root code `char` (therefore matching all descendants). Missing tables on an
explicitly configured additional tab are errors, not permission to admit all
items. TOML `[tabs.<name>]` order is authoritative when generating tabs.txt;
rebuild after editing sizes, labels or type filenames. The core should apply
user TOML tab overrides by name before Validate, so editing an installed config
also changes the plugin grid without rebuilding mod data. New TOML-only tabs
need their type TSV deployed. Missing `tabs` uses the table list / fallback.

`Pack` is a fresh-layout feasibility check: stable descending cell area, then
descending height, first free cell scanning y then x, no rotation. This mirrors
wild-healer's aaa-player-page-host fresh packing (source in D2R-Tools, credit
wild-healer). It intentionally does not implement his saved-place/item-aware
passes. The core host retains those rules and adopts existing page-6 items;
feasibility coordinates must not overwrite saved lease coordinates.

Core owns CMake. Add these two lines inside its test-enabled block:

```cmake
add_executable(invtabs_tab_config_tests tests/tab_config_test.cpp)
target_compile_features(invtabs_tab_config_tests PRIVATE cxx_std_20)
```

The test executable is standalone,
standard-library-only and uses Check/failure count like drawcap/tests.

## File formats

Every plugin table is printable ASCII strict TSV, LF line ends with final LF;
headers are case-sensitive. No comments or blank rows inside TSV files.
`tabs.txt` header is `name<TAB>label<TAB>columns<TAB>rows<TAB>types`.
Example row: `charms<TAB>Charms<TAB>10<TAB>6<TAB>types_charms.txt`.
Names use ASCII letters, digits, underscore or hyphen. Labels are nonempty
printable ASCII. Type filenames are unique safe basenames
`types_<letters/digits/underscore/hyphen>.txt`, never paths. Names are unique.
There must be 1..12 tabs, each dimension 1..16; rectangles must pack together
on the 16 x 16 custom page (total area alone is insufficient).

Each type file has the single header `itemType`, then one unique itemtypes.txt
`Code` per line (1..4 printable nonblank ASCII characters). All listed codes
must exist. Different tabs may intentionally accept the same type; duplicates
within a type file are rejected. Equiv1/Equiv2 are traversed at runtime, so
listing one root suffices. Generated charm types reuse `charm_inv.charm_types`
unchanged: the Median table produces char scha mcha lcha csch summ grtz and
araa through arag (14 codes). CharmInv's own tool and 10 x 4 output are unchanged.

## Modder workflow

Run `py -3 tools/invtabs_tables.py build --out <mod root>`; `<mod root>` contains
`data/global/excel/itemtypes.txt`. This only writes the invtabs table folder;
it does not run the mod build. `--config <file.toml>` selects another config.
`py -3 tools/invtabs_tables.py check --out <mod root>` validates deployed tables
against that tree's itemtypes and checks dimensions, names, codes and packing.

To add consumables, copy the commented `[tabs.consumables]` section from the
default config and uncomment it. Create `types_consumables.txt` in the invtabs
table folder, header `itemType`, followed by your actual consumable type codes.
Build and check again. The builder regenerates the charm type file but leaves
other tab files owned by the modder. Deploy the config and generated tables
together; restart after edits. No packaging or full-build default enables this.

## Packaging and installation (opt in only)

The default release still ships CharmInv. To stage the replacement explicitly,
pass `--invtabs <invtabs.dll> --no-charminv` to package_release.py. Passing
--invtabs without --no-charminv fails early with
`invtabs and CharmInv cannot be staged together`. stage() and both individual
staging helpers enforce that rule too, before copying conflicting files.
The hook installs `d2rloader/plugins/invtabs.dll` and
`d2rloader/config/invtabs.toml`; config is listed for preservation. The DLL
check currently verifies MZ and plugin id; version/manifest-specific validation
must be tightened when the core lane defines its release identity.

install_mod.py accepts --invtabs DLL (CharmInv is already off by default for
that tool); --charminv conflicts. It removes old CharmInv files before staging
invtabs, preserves an existing invtabs config, and removes invtabs files when
returning to an install without that option. The verifier accepts invtabs in
place of CharmInv only when its DLL/config exist, rejects both owners, and
allows these optional files in reference comparisons. It still checks every
other required bundled plugin. Tables are supplied in --data-from; these hooks
do not generate tables or enable the replacement automatically.

## Validation and limits

Synthetic Python tests cover the 14 codes, Equiv2/cycles, future tabs, unsafe
paths, duplicates, unknown codes and geometric packing. The C++ test covers
parsing, validation, fallback and matching without game files. No game run or
full data build belongs to this lane. The repository and main checkout contain
no CLAUDE.md at the brief's specified location; docs/testing.md was read.

Lane validation: focused Python suite (including installer) passed. Full requested
suite has one unrelated existing failure in test_advanced_stats.py because this
fresh worktree lacks work/named/itemstatcost.txt and the extracted PlugY spelling
is item_healonstrikingmelee while the data list uses skill_healonstrikingmelee.
The standalone C++ test compiles with MSVC /std:c++20 /W4 /WX; runtime validation
was blocked by a suspended process before output, so no runtime pass is claimed.
See the lane notes for logs. Packaging tests use MXL_DRAWCAP pointing to the main
checkout's existing finished DLL; no plugin build or data build is needed.
