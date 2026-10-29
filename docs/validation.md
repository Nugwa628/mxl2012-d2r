# Validation

Tools: `tools/validate.py` (checks), `tools/build.py` (whole pipeline: names, formulas, Sigma tables, strings,
migration, validation; rebuilds `work/named` and `work/mod` from scratch).

## Schema source
D2R's own data guide (`extract/d2r/<build>/data/global/dataguide/data/files/*.js`) types every field:
`reference` with its target table/column, `string` (string key), `text` with a maximum length and sometimes an
allowed-value list, `int`, `boolean`, `parse` (BBE formulas by scope, or property codes / parameters), and enum
validations (`enums.js`). armor/weapons/misc share fields through `SharedItems`, the affix tables through
`SharedItemMods`. The BBE reference (docs/bbe-calc.html) gives the formula scopes: skill (skillcalc codes),
missile (misscalc), monster (moncalc); item and treasure-class formulas take no identifiers. D2R added a
`cond('Name', param)` function (IsType, IsClass, Desecrated, Difficulty, MonsterTestElite, ItemIsType,
ItemIsModType, MonsterHasMod); none checks a state, so `mxl_hasstate` still needs a plugin.

## Severities
- **error**: rejected value or a reference to something that does not exist.
- **plugin**: valid once a D2RLoader plugin provides it.
- **warn**: D2R's own data has the same value, or the string key is missing from Median's own tables too.
- Plugin string keys (`tools/plugin_keys.py`) and the localization-cell rules are described in [strings.md](strings.md); a
  missing plugin key is an **error**.

## Current result (both banks)
2026-10-20 rebuild on the game PC (docs/setup.md): **0 errors**, 3,994 plugin items (base), 48/89 warnings (base/rotw).
Not yet checked why this differs from the numbers below (fixes since then, or the restored Median data).

Earlier result:
**2 errors**: `stat('strength'.320)` in two skills' `prgcalc1` (broken bytecode in Median's own data; the 4
such cells are listed in work/formulas/report.md and need a manual decision).

**Plugin work (base bank, 4,667):**
| Kind | Uses | Notes |
|---|---|---|
| Median calc codes | 2,844 | `mlvl`/`skcp`/`skcn` in every skill's `skpoints` (~540 each), `syn1`-`syn6` (~580), `wdm` 141, `skcd` 129, `aura` 90, `bl12..` , `area` 58, `mnhp`, `mnar`, `pass`, `maxe`, missile `blvl`/`msyn` |
| Median level types | 975 | automap rows for level types 36-44, 51; D2R: "level types are static defined values that cannot be added" |
| Engine values outside D2R's lists | 702 | item use functions (`misc.pSpell`), missile hit functions, stat description functions (`descfunc`), cube ops, property functions, quest flags, state colour shifts, sound falloff, ... each a D2Sigma feature |
| Median formula functions | 140 | `mxl_statlayer` 76, `mxl_hasstate` 54, `mxl_itemstat` 8, `mxl_skilllevel` 1, `mxl_tabpoints` 1 |
| Median `stat()` modes | 6 | modes 5, 6 (and 86 in a broken formula) |

## Fixes the validator drove (all in the pipeline now)

- Missile chains (bug #395, `tools/missile_chains.py`, check `missile_chains`): a missile that can make itself again through SubMissile / HitSubMissile / Clt* / ExplosionMissile is an **error** (the client trail copy of client do 15 and the rows in `LOOP_ALLOW` excepted); a monster attack missile (monstats Miss*) making more than 250 server missiles per launch is a **warning**. `py -3 tools/missile_chains.py` lists the heaviest rows per side.
- Generated names respect D2R key lengths (31 for missiles/objects, 39 lvlwarp, 47 others): ~2,400 errors.
- **Blank-key rows are records.** D2R's ID columns confirm: only "Expansion" rows are skipped. monsounds and
  montype start with a blank record; skipping it had shifted every monster-sound name by one.
- automap decoded straight from `automap.bin` (the first decoder's text did not line up with the records).
- D2R-only columns pointing into tables Median replaces (Terror Zone "Desecrated" treasure classes) are left
  empty; rows kept from D2R (RotW Colossal monsters) get such dangling references emptied.
- hireling `HireDesc` is a string key in D2R (`rs1` -> `strhirespecial1` via the Sigma table hiredescext);
  hireling is Median-only (D2R repeats the key per level, so key-merging re-added D2R's mercenaries).
- monseq keeps D2R's own sequence groups after Median's.
- Numeric string keys stay numeric (`115` = "Axe (1)"; item `namestr` cells use them; they are unique).
- Single-row formula columns are converted too; booleans normalised to 0/1; a stray control byte fixed.
- `sigma_tables.py` wrote `\r\r\n` line endings; fixed.

## First boot (2026-10-05): what the game asserted, and the fixes
The first launch crashed (black screen) loading `data\global	iles\mxl\quest\yshariasewall.dt1`: Median's level
types use Median's own tiles, which the mod did not ship. The log also listed load assertions. Fixed:
- **Tiles:** `install_mod.py` now ships Median's `data/global/tiles` (129 .dt1, 574 .ds1).
- **Formula limits:** D2R keeps 255 characters per formula and 32 bytes per quoted name. Generated names
  lost the `mxl_` prefix, names formulas can reference are capped at 31, and rows named in formulas still over
  255 get compact names (`sk1820`) through `work/shorten.json` (build.py repeats naming until stable).
- **Formula syntax:** D2R's parser rejects bare negative literals and unbracketed ternary branches: negatives are
  written `(0-N)`, non-trivial branches are bracketed.
- **Median formula functions** (`mxl_*`) are written as `0` until a plugin provides them (`formula.py convert
  --keep-mxl` writes the real calls). The 2 broken `stat('strength'.320)` cells are `0` as well.
- **Treasure classes:** item display names inside quoted cells with modifiers (`"Gold (gld),mul=2560"`) are
  mapped back to codes; D2R allows unique/set item names in TCs; Median's D2Sigma-generated classes
  (`sarm93`, `swea93`) and missing names are cleared and reported; a case-only mismatch is fixed.
- **MonStatsEx** blank means monstats2 row 0 (the first decoder wrote 0 as blank).
- **Monster AI** must be one of the first 155 monai rows (the engine's AI table has 155 entries; a later row runs "None" and the monster stands still), except Median's `andariel_ai` at exactly id 155, which the plugin serves natively. Median's
  `andariel_ai` (47 monsters) keeps its row (tools/monster_ai_data.py checks the id; docs/subsystems/monsters-ai.md); the validator errors if any other AI lands past the table.
- **Sets:** "Orphan's Call" has 9 items (D2R: 6); items 7+ go to "Orphan's Call (2)" until a plugin exists.
- **Inventory:** D2R's own rows for now (2 per page, one per screen resolution).
- The validator now checks all of these (formula/name lengths, TC entries, set sizes, MonStatsEx, mercenary
  name ranges, inventory rows).

Still expected at load (engine limits, not data errors): **more states than D2R allows** (Median 1,014; D2RLoader
advertises 32,768, possibly only for tables built by its own compiler) and **level types beyond D2R's fixed list**.
