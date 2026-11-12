# Wiki panel data

`tools/wikipanel_export.py` runs immediately after `devmenu_catalog.py` in both
full and data-only `tools/build.py` builds. It writes UTF-8/LF format 1 to
`work/mod/data/mxl2012-wiki/wiki.tsv`. The V/C/E/L/K contract and category order
are unchanged. Install and package copy the whole data tree, including this file,
through `install_mod.build_data` and `package_release.stage`.

The exporter regenerates wiki JSON from this checkout's built tables and resolves
names with `strings_ns.effective_texts`, including D2R overrides. It imports no
live-wiki helper and never fetches or uploads anything. The seven modules in
`tools/wiki/` are a separate snapshot commit dated 2026-11-11. The coordinator can
drop that commit when the wiki thread's sources land. Player selection and grouping
are in `tools/wikipanel_player.py`. A separate fourth-round correction commit
removes editor-label and unresolved-key display fallbacks from the snapshot;
the main checkout's original generators remain untouched.

The default prose inputs are committed in `tools/wiki/pages/` and the eight cached
class/skill HTML files in `tools/wiki/class-texts/`. A checkout needs no other wiki
folder or network access. Brother Laz's writing is used with Brother Laz's
permission and credited, as recorded in [NOTICE](../NOTICE.md). The separate
2026-11-11 prose snapshot contains 662,401 bytes. [Wiki prose sources](wiki-prose-sources.md)
lists every page, its apparent authorship and the evidence for that attribution.
`MXL_WIKI_PAGES` and `MXL_WIKI_LAZ` optionally override these defaults through
environment variables or the git-ignored `.mxl-local.json`. Missing inputs stop
the exporter. Generated JSON and the content table remain outside git.

## Player selection

The developer catalog's spawnable/disabled and item-type inheritance rules apply,
but retired charms are omitted rather than tagged. Equipment uniques also need
an obtainable base and an eligible level. Charm/reward definitions need an explicit
named drop or a recipe reachable from drops, shops or quest objects. Upgrades that
require an otherwise unavailable charm cannot seed that charm's availability.
The trace expands live monsters' treasure classes, placed superuniques' reward
classes, map placements, minions, summon skills and monster-spawning missiles.
It is a static source trace, not proof that every engine-driven encounter works.

The original Crystalline Flame Medallion definition has no source; the second,
identical definition has the Imperius reward drop and is retained. Hard Mode Charm
has no starting source: its upgrades and downgrades cannot make it obtainable.
I Am Rich's level-zero requirement does not mean retired: an enabled trophy recipe
produces it. Cornerstone's 149 enabled skill variants share one entry, with grants
listed by class; the other 201 definitions are unspawnable.

Each category has at most one entry per case-insensitive name. Tiered unique
variants keep their complete tooltip blocks, including requirements and adjusted
base damage/defense, under variant headings. Item subtitles use the tooltip base
name or Charm, never the internal charm type. Sets retain pieces and partial/full
bonuses. Runewords retain ordered socket sequences (including filler jewels);
gemwords retain each socket count. Bases retain requirements and maximum sockets.

Cube entries describe methods rather than individual ingredients. Mystic Orbs,
Unique Mystic Orbs and Trophies each state their method once and list all members
and effects. Creating an honorific item remains separate. Effects retain the game
wording; different item kinds and honorific-only variants remain explicit. Common
required-level costs and honorific scaling are stated once. Orb identities use
the complete resolved game description and recipe effects, including item kinds,
conditions and costs. Ordinary members start with their distinguishing item
description, since all are named Mystic Orb in the game. The 140 ordinary item
definitions form 70 members; 30 unique orbs form 30 members. Five unavailable
duplicate definitions map to existing, obtainable members without adding display
content or making a source claim. The naming review and its limits are recorded
in [Wiki name audit](wiki-name-audit.md).

Gem upgrades share one entry listing all 12 kinds and five grades. Runes share
one entry with upgrade and downgrade results. Two-for-one, four-for-one and mixed
grade methods are validated against the input/output chains. Alchemy, renewal,
quality enhancement and disenchanting also use shared methods. Jewelcrafting,
shrine bonuses and lucky upgrades list compact effects; their differing conditions
remain beside each member. Specific summons, quest items and challenge methods
remain separate. The variable enhanced-damage reroll states the level rule once.
Internal counter conditions become player wording and links to the corresponding
challenge guides; unknown conditions fail rather than silently lose a restriction.
The family renderer is in `tools/wikipanel_families.py`; neither it nor the other
exporter modules store generated game prose.

Skills are class-tree/innate skills, plus grants from obtainable uniques, sets,
runewords, gemwords and spawnable affixes. Item procs and charges count as grants.
A name on the old item-only prose list alone does not qualify. Subtitles identify
class, tree and required level, or say Item skill. Warlock uses the effective game
tab names. Unresolved numeric formulas and evaluation assumptions are omitted;
character-dependent values are reference samples, not a live character tooltip.
The wiki renderer still has unsupported skill-description and damage functions.

Monsters must have a placement, population or summon source. NPCs, unkillable
dummies and unlocated definitions are excluded. Entries merge variants by visible
name, retaining complete area/difficulty blocks, levels, resistances, immunities
and named abilities. The wiki's inferred rank/Animal labels are not displayed.
Area names come from levels' effective LevelName strings, never map filenames.
Ubers retain template difficulty, location, summon, reward and following strategy
prose. These hand-written instructions are not mechanically verified by a game run.

## Prose and reports

Headings become gold lines, lists use a dash, tables use cell separators and links
keep their label with a K target only when an entry exists. Images and website
queries/templates are omitted. Main Page, MediaWiki/Template/Module infrastructure,
software installation, loader/plugin setup and port-history pages are skipped.
Technical sentences, filenames, internal identifiers and unavailable-item mentions
are removed without editing source pages. This conservative filter can remove
useful context from a mixed technical paragraph; omissions are recorded for review.

Horadric Cube, Base items, Runewords, Set items, Unique items and Monsters retain
their explanatory prose and native credits, but omit generated member lists,
recipe/item tables, website queries and empty list headings. Each ends with a
direction to the corresponding category. The cube guide keeps crafting-point,
reagent and input/output explanations rather than repeating the recipe category.

`work/wiki/panel-report.json` records counts, size and skipped pages.
`work/wiki/player-audit.json` records removed sentences and reasons, selected
unique keys, reachable recipe count and Cornerstone variants. These reports
contain game prose and stay outside git. Welcome is the only exporter-authored
credit location; credits already in a source page's prose remain there.

The table describes the build it ships in. The coordinator's Unreleased note
remains: CHANGELOG entries under Unreleased print a note and do not fail a build.
The exporter cannot separate unreleased data edits or override prose from a
release without a released input snapshot; packaging must use the intended tree.

Run `py -3 -m unittest discover -s tools/tests -p test_wikipanel_export.py` after a
data build. Tests cover converters, contract, raw-source/selected counts, source
provenance, grouping, forbidden display/search patterns, all-category name
uniqueness, skill metadata, areas, Welcome, install/package copy and determinism.
