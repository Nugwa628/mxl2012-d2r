# Wiki name audit

Fourth-round review, 2026-11-11. Game names and descriptions are resolved through
`strings_ns.effective_texts`, including built overrides. An editor label is never
a substitute for a missing game string. This changes no table-format fields.

## Naming paths reviewed

| Source | Finding and exporter treatment |
|---|---|
| `wiki/cube.py`, `Names.base` | Invented qualified Mystic Orb names from misc editor labels. Removed. Base names now require the resolved namestr. Orb descriptions are separately resolved from spelldescstr and stripped of colours. |
| `wiki/cube.py`, `Names.__init__` | Used an unresolved unique/set string key as a name. Removed; unnamed definitions do not enter the name map. |
| `wiki/cube.py`, `Names.thing` | Displayed itemtypes editor labels. Uses generic ingredient wording for common categories, and concrete resolved base names otherwise. The Cow Portal recipe result is already a player-readable special result, rather than a table reference. |
| `wiki/items.py`, `Data` | Used internal skill and monster keys when display strings were absent. Unresolved references now have no display name; item stat lines needing them are omitted rather than displaying the key or a fabricated numbered name. |
| `wiki/items.py`, `uniques` | Fell back from unique/base string keys to editor labels. Removed. Unnamed definitions are omitted and missing base names fail rather than inventing text. |
| `wiki/bases.py`, `bases` | Fell back to the editor base name. Removed. Type/group labels remain diagnostic metadata and never become base-entry titles or subtitles. |
| `wiki/setwords.py`, `shown`, `base_fields`, `rune_name` | Used a bare key or editor base label as fallback. Removed. Set name/index and runeword Name cells are string references, resolved before display. |
| `wiki/setwords.py`, `type_names` | Allowed/excluded runeword and gemword bases came from itemtypes editor labels. They now enumerate resolved, spawnable base-item names through the type inheritance chain, with tiers collapsed. |
| `wiki/monsters.py`, `shown_name`, `Data.area` | Fell back to internal monster/superunique keys, level keys or map labels. Removed. |
| `wiki/monsters.py`, `Data.skill`, `props`, `skills` | Stripped “Mon” from unresolved skill keys, bypassing the player's unknown-name filter. It now retains the intact diagnostic key until that filter translates a known summon to its resolved monster name or records an omission. Resolved names have colours stripped. Abilities require a resolved skill string. |
| `wiki/monsters.py`, category, rank, mods | Inferred Animal/rank words and internal modifier labels are diagnostic metadata. The player renderer omits them. |
| `wiki/skills.py`, `record` | Used a row key for an unnamed skill/prerequisite. Removed. Only named prerequisites are retained. |
| `wiki/skills.py`, `LAZ_ALIASES` | Wiki-page aliases differ from game names. The player renderer already replaces them with the effective skilldesc name and selects skills from an obtainable player source. Formula-reference names are evaluated internally or omitted, never used as display names. |
| `wikipanel_player.py`, area/skill/item labels | Uses effective LevelName and skilldesc strings and base tooltip names. Internal keys remain necessary to trace sources and joins; they are not display fallbacks. |
| Hand-written pages and uber calls | Existing prose filtering replaces known map labels and rejects technical references. These are authored prose, rather than a name-column fallback. No source page was edited. |

## Orb identity and coverage

An orb member is identified by its complete, colour-stripped game description
and the set of all item-kind, honorific-condition and effect tuples from its
recipes, including the required-level cost. A price or internal label never
participates in identity. Every source item code belongs to exactly one member.
The audit records each member's full description and item codes.

There are 140 ordinary orb codes forming 70 exact description/effect pairs, and
30 unique orb codes forming 30 members. In particular, the ordinary minion-life
orb and the Wyrd orb no longer share an invented qualifier. The old 70 internal
qualifiers grouped codes without checking descriptions or effects; their count
happened to match the correct count of 70 player-visible descriptions.
Of those old pairings, 21 combined different descriptions/effects and 49 happened
to match. Every ordinary qualifier was invented rather than a game name.

Five unavailable duplicate definitions have recipes identical to five obtainable
definitions. The coverage audit maps these aliases to the same existing member;
it records the obtainable subset separately. No unavailable definition adds
display content. Thus all 170 recipe-bearing orb definitions have one member
line, without claiming an unsupported vendor or drop source.

The ordinary member line starts with the game's distinguishing description.
Only the common cubing instruction and required-level cost are omitted from its
label because the family states those once. Unique orbs keep their resolved item
name and description. Effects retain the game wording and item-kind differences.
No bought/dropped source claim is made. Trophies use resolved item names and keep
their actual reward targets and recipe effects; no invented trophy qualifier was
found.

The monster-key correction changes 76 entries. Existing unresolved effects are
omitted unless a summon can be traced to a named monster. Even when a stripped
editor label happens to equal a player skill's name, that coincidence does not
establish that the monster uses the same named skill. This remains an accuracy
limit: some real abilities have no resolved display string and cannot be named
from these data without an authored, verified explanation.

## Spot-check method and limits

Seed 20261111 selects three entries per category, in this order: uniques, sets,
runewords, skills and monsters. Each population is sorted by case-insensitive
display name before `random.Random.sample`. The selected names and full source
traces are retained in the lane's external fourth-round evidence. One name and
one stat line per entry are traced through raw built tables and effective strings;
sets use a piece's modifier. This is a bounded source check, not a game run or
proof that every property/skill formula is rendered correctly.

Later wiki cleanup must remove the same invented orb qualifiers on the live wiki,
as well as editor-type labels, unresolved-name fallbacks and page aliases described
above. Earlier cleanup candidates remain: repeated recipe lists, row annotations,
query-only headings and technical instructions mixed into player guides.
