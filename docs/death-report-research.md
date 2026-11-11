# Death report: research and design (lane deathlog, 2026-11-05)

Owner question (2026-11-05): when the player dies, can the mod show what killed them: the damage taken in the last N
seconds or hits, with the monster (name, unique / champion), the skill, missile or attack, the damage type (physical,
fire, cold, lightning, poison, magic), the amount after resistances, the life left and the time.

**Short answer: yes, server side, with one inline hook that D2R's damage code already goes through for melee, missiles,
skills, auras and thorns.** Poison and other damage over time do not pass through it and need a second, cheap source
(a per-frame life sample). Research only: no plugin code was changed, nothing was run in game (no slot).

Confidence words as in [d2r-addresses.md](d2r-addresses.md): *verified* = read in code and matched against 1.14d;
*likely* = the structure matches, one link inferred; *guess* = not read.

## 1. Where the plugin can see it (D2R build 93847)

### 1.1 The damage path

D2R keeps 1.14d's `SUnitDmg.cpp` shape. The 1.14d names come from the redivivus database (Game.exe), the D2R addresses
from `tools/d2r_find.py` on the build 93847 dump plus the earlier lanes' notes.

| 1.14d (redivivus) | D2R 93847 | What | Confidence |
|-|-|-|-|
| `DAMAGE_ApplyDamageToUnit` `0x57c6c0` (game, attacker, victim, bApplyDefenseReduction, damage) | **`0x44ce80`** (same five arguments; the damage block is the 5th, at `[rsp+0x28]`) | the one place that subtracts life. Order: can-attack test, town rule, `StoreLastAttacker`, defensive reduction (`0x44df10`, resist + absorb per type), hit events 5 / 6 / 1 / 2, physical clamped to current life, leech (`0x450c90`), absorb heal (`0x451820` with `+0x130`), **life -= `+0x134`** (`0x2f5020` / `0x2f7d10` stat 6, under 256 -> 0), mana / stamina drain, stun, cold, freeze, poison, burning, then result flag 2 (dead) when life < 1 and the kill events 10 and 9 | verified: entry matches (`0x48e060` can-attack, `test [dmg],0x1000`, `and word [dmg+4],0xfffc`), the life write at `0x44d062`-`0x44d093`, the status calls at `0x44d10f`-`0x44d140` |
| `DAMAGE_ApplyDefensiveReduction` `0x57c1e0` | `0x44df10` (called at `0x44cf93`) | the 12-entry damage table, each entry through the per-type step `0x4523e0` (resist, then absorb `0x450670`) | verified (scaffold lanes hooked `0x4523e0` / `0x450670` in game) |
| `SERVER_GetHitCalculation` `0x57cee0` (game, attacker, victim, damage) | `0x44a9b0` (likely) | the reaction: get-hit / block / knock-back modes, and the kill call for a dead victim | likely (scaffold `combat-stats.md`) |
| `SERVER_KillMonster` `0x57ccb0` (game, victim, killer, flag) | **`0x44db20`** | the unit death function, players too (returns at once for a player in mode 0 / 17); 21 callers | verified (harness `kill` calls it; scaffold `death_event.cpp` hooked it) |
| `RegenAndPsnDecreaser` `0x5a6920` | not located | the per-frame regen / poison tick. 1.14d: when life reaches 0 it finds the poison stat list's owner (type + GUID stored by `DAMAGE_ApplyPoison`) and calls the death function with that owner as the killer | 1.14d verified; D2R twin **guess** |
| `DAMAGE_ApplyPoison` `0x57ac50` | `0x451570` area (the calls after `+0x118` cold / `+0x11c` freeze; which one is poison not read) | state `poison` with stat `hpregen` = -rate for `length` frames, owner = attacker | 1.14d verified |

Callers of `0x44ce80` (36): the melee hit `0x44b2b0`, the thorns / item event handlers `0x582948`, `0x582b99`, `0x582da9`,
`0x582fb9`, `0x583580` (exe handler table 6 = thorns `0x582b20`), the aura code `0x561280` / `0x561480`, skill and
missile functions (`0x55xxxx`, `0x57xxxx`), monster AI. So reflect, auras and missiles all reach it. Not checked: whether
D2RLoader's D2RCore.dll reimplements any damage path without calling `0x44ce80` (it does redirect some `0x4523e0` call
sites, see d2r-addresses.md "D2RCore.dll"); the in-game test in section 4 covers that.

### 1.2 The damage block (D2R, 0x180 bytes)

1.14d's `D2DamageStrc` is 0x70 bytes. D2R's block puts a small list at `+0x40` and keeps the rest of the 1.14d order,
shifted. Offsets read from `0x44df10` (each table entry's field pointer is a `lea r, [block + X]` next to its type
name) and from `0x44ce80`:

| Field | 1.14d | D2R | Source |
|-|-|-|-|
| hit flags | `+0x00` | `+0x00` | verified (`test [rdi],0x1000`) |
| result flags (u16; bit 1 hit, 2 dead, 0x20 no events) | `+0x04` | `+0x04` | verified |
| physical | `+0x08` | `+0x18` | verified ("Phys") |
| fire | `+0x10` | `+0x20` | verified ("Fire") |
| burning rate / length | `+0x14` / `+0x18` | `+0x24` / `+0x28` | guess (gap between Fire and Ligt) |
| lightning | `+0x1c` | `+0x2c` | verified ("Ligt") |
| magic | `+0x20` | `+0x30` | verified ("Magc") |
| cold | `+0x24` | `+0x34` | verified ("Cold") |
| poison rate / length | `+0x28` / `+0x2c` | `+0x38` / `+0x3c` | verified ("Pois", "PLen") |
| cold / freeze length | `+0x30` / `+0x34` | `+0x118` / `+0x11c` | verified ("CLen", "FLen"; read again by the apply) |
| life / mana / stamina leech | `+0x38`..`+0x40` | `+0x120` / `+0x124` / `+0x128` | verified |
| stun length | `+0x44` | `+0x12c` | verified |
| absorbed life (heals the victim) | `+0x48` | `+0x130` | verified |
| **total damage subtracted from life** | `+0x4c` | **`+0x134`** | verified (`0x44d062`) |
| hit class | `+0x60` | `+0x144` | verified earlier (plugin-spec, scaffold) |

All amounts are in 1/256 of a life point, like stat 6. After the original `0x44ce80` returns, the per-type fields hold
the values **after** resistances and absorb (the table ran inside it when the 4th argument is 1); with argument 0 the
caller passed an already reduced block. `+0x134` is the total actually taken in both cases.

### 1.3 Who and what

- **Attacker**: the 2nd argument (null for a few environmental hits). For a missile it is the missile's owner, for a
  pet the pet (owner via `0x4a53c0`).
- **Monster name / class**: class id `unit+4`; monstats row via `0x976e0(dataFlag, class)`; the string id of the name and
  its lookup are not mapped on D2R yet (guess: monstats `NameStr` -> the string table the plugin already uses for
  `skill_text`). Superunique row and its name: monster data (`unit+0x10`), offset **guess**. Unique / champion /
  superunique: monster data `+0x1a` bits 0x8 / 0x4 / 0x2 (verified, d2r-addresses.md section 15). Random unique names
  (prefix + suffix seeds) are a guess; the first version can print "unique Fallen".
- **Skill or missile**: the block has no skill id (1.14d struct read in full; the D2R `+0x40` list holds hit-skill
  entries, contents not read). Two sources: (a) a pre-hook on the server missile hit (`0x45bc40`, likely) that puts the
  missile class in a per-thread "current hit" slot read by the `0x44ce80` hook; (b) the attacker's current skill and
  mode (unit mode `+0xc` is verified; the used-skill pointer offset is a guess). Melee without a skill reads as
  "attack" by mode (A1 / A2). Thorns: the call comes from the item event handlers, so the attacker is the reflecting
  unit; mark it with the same per-thread slot from a hook on `0x582b20`, or read hit flags (not mapped).
- **Life left**: stat 6 of the victim after the original returns (`0x2f5020`, a D2RCore thunk; safe on the server
  thread). Max life stat 7 for a percent.
- **Time**: server frame `game+0x170` (25 per second, verified) plus a wall clock for the file.
- **The death**: result flag 2 after the original, for a player victim; and a hook on `0x44db20` for deaths that do not
  come from a hit (poison, burning, harness `kill`, scripted). The death function's killer argument names the poison owner.

### 1.4 Existing mxl2012-core code nearby

| Code | Relation |
|-|-|
| `server_frame.cpp` (`0x406550`, 4 callback slots, 2 used: harness, spiritwarp) | the per-frame life sample for DoT (section 3.2) takes the third slot |
| `dodge_list.cpp` | a byte patch inside `0x44ad9a` (SUnitDmg), no hook on `0x44ce80`; no conflict |
| `harness_cmds.cpp` | `kill` calls `0x44db20`; has `RvaGetStat` / `RvaMonStats` / mode helpers to reuse; `watch srvhit` already counts missile server hits |
| `image_guard.cpp` | already draws text over the game with the Overlay service (`AfterGameUi`), the model for an in-game panel |
| lane leech (#540) | reads the same function (`0x450c90` is called from `0x44d038`); coordinate if both add hooks on `0x44ce80` |
| scaffold `death_event.cpp` / `combat.cpp` (mxl2012-runs/scaffold-src, not in this plugin) | hooked `0x44db20`, `0x4523e0`, `0x450670`, `0x44ef70` in game with the same entry-byte checks; proves the hooks install |

No current mxl2012-core part hooks `0x44ce80` or `0x44db20` (grep of plugin/src). D2RLoader refuses a second inline hook
on one address (server_frame.cpp), so the death report must own those hooks and give other parts a callback list, as
server_frame.cpp does. Another D2RLoader plugin that hooks `0x44ce80` would make ours fail to install (reported in the
`mxl2012` line, nothing breaks).

The PluginSDK's lifecycle service has a **monster** death listener only (`lifecycle_events.h`, killer included); there
is no player death or damage event, so the hooks above are needed.

## 2. How to show it

| Option | Who sees it | Cost | Verdict |
|-|-|-|-|
| Console: `mxl2012 deathlog [n]` (the brief's `mxl deathlog`) | anyone with the D2RLoader console (`enable_console`, debug builds and testers) | small: `Say()` lines from the ring buffer; also lands in `mxl2012-testharness-console.txt` with the harness on | first stage; players normally do not have the console open |
| File: one block per death appended to `deaths.txt` next to `mxl2012-core.log` (D2RLoader's log folder), or in the mod's save folder (`mods\mxl2012\...` save path) | anyone, after the session; bug reports can attach it | small; write on the death (server thread, a few hundred bytes), rotate at ~1 MB | first stage; the most useful for bug reports and Hardcore |
| Overlay panel: the Overlay service (`registerFrameCallback`, `drawText`, `drawFilledRectangle`, `measureText`, clip) on the death screen, the last 8-10 hits, closed by the respawn | the local player | medium: text layout, scale with `Metrics`, colour per type; draw thread reads a copy taken under a lock | second stage, the owner's "report" proper |
| Native D2R panel (`Panels` / `Widgets` services, as d2rl-buff-hud does) | the local player, looks like the game | larger: panel JSON, open / close, localisation | only if the overlay looks out of place |
| Chat line ("Killed by Fallen Shaman (unique): Fire Bolt 1234 fire") | every player in the game, also joined ones if sent as a server message | small for the host; the send path for a server chat message is not mapped | optional one-liner at stage 2 |

Data flow: hooks fill a per-player ring buffer on the server thread; at the death the buffer is frozen into a "last
death" record; the console, the file and the overlay read that record. The draw callback runs on the render thread, so
it copies the record under a lock (or a sequence counter) and never touches units.

## 3. Costs and hard cases

### 3.1 Per-hit overhead

`0x44ce80` runs for every hit on every unit: with Median's area skills, auras and many monsters, hundreds per second.
The hook calls the original, then returns at once unless the victim is a player (`unit+0`, one compare). For a player:
copy about 15 ints from the block, read stat 6, the attacker's class and flags, write one 64-byte ring entry (64 entries
per player, no allocation). Names are looked up only when the report is built. Expected cost: well under a microsecond
per player hit; nothing measurable for monster hits. The per-frame sampler (3.2) is one stat read per player per frame.

### 3.2 Poison, burning and other life loss without a hit

Poison is a stat list with negative `hpregen`; its ticks run in the regen event, not in `0x44ce80`. The hit that
applied it is logged ("poisoned: 120/s for 4 s by Fallen Shaman"), but the life it takes later is not. A per-frame
sample of each player's life (server frame hook) gives the gap: life lost in a frame without a logged hit becomes a
"poison / over time" entry, with the source taken from the poison state's owner when it is still set (the 1.14d stat
list stores the attacker's type and GUID; D2R offset guess). The same sample catches anything else that writes stat 6
directly (Median skills or scripts that set life). The final "killed by" for a poison death comes from the `0x44db20`
hook's killer argument.

### 3.3 Multiplayer

All of this is server code. It runs in the process that hosts the game: single player, and the host of a TCP/IP or
lobby game. A joined player's own plugin never sees these calls; their client only gets life updates. So:

- host / single player: full report for the local player; the host also has reports for every other player (file);
- joined players: no report unless the host sends it (chat message or a custom packet). Stage 3 at most; not designed
  here.

### 3.4 Median's own damage

| Source | Path | Seen by the hook? |
|-|-|-|
| D2Sigma-style item spells (chance to cast on striking / when struck, oskills) | ordinary skills and missiles through D2R's skill code | yes, attributed to the caster; the skill name comes from the missile / skill slot (1.3) |
| Auras (monster auras, Median's aura stats) | aura apply `0x561280` / `0x561480` -> `0x44ce80` | yes; the aura owner as attacker, no missile; label from the aura state (guess) |
| Reflect / thorns, Median's "attacker takes damage" | item event handlers `0x582xxx` -> `0x44ce80` | yes; mark as reflected (1.3) |
| Corpse explosion, death novas (stat 271 cast on death, monprop rows) | skills of a dying monster: the attacker can be in mode 0 / 12 | yes; the attacker pointer is still valid in the hook (the unit is freed later), but the report must copy the name at once |
| Plugin-made damage blocks (scaffold ported 161 / 171 via `0x44ce80` / `0x44a9b0`) | none in mxl2012-core today | n/a now; any future one is covered if it calls `0x44ce80` |
| Life set directly, bleeding / open wounds (event 5 / 6) | open wounds is a regen-style state; event handlers | open wounds: as poison (3.2); others yes |

### 3.5 Risks

- `0x44ce80` is long and hot; a hook bug crashes every fight. Mitigation: post-hook only reads, never writes the block;
  entry bytes checked (`40 55 53 56 57 41 56 41 57 48 8d ac 24 e8 fe ff ff 48 81 ec 18 02 00 00`, 24 bytes, no
  rip-relative operand; the next instruction loads the stack cookie rip-relative and must stay out of the copied bytes);
  off word `deathlog`.
- Field offsets marked guess (burning, superunique name, used skill, poison owner) must be checked in game before they
  are printed; until then print only verified fields.
- Unit pointers in the ring buffer go stale: store ids and names, never pointers.
- D2RCore redirects: if a damage path bypasses `0x44ce80`, the per-frame sampler still shows the life loss as "unknown".
- Another plugin hooking `0x44ce80` or `0x44db20` blocks ours (only the report is lost).

## 4. Staged plan

| Stage | Content | Effort | Risk |
|-|-|-|-|
| 0 (done) | this research | - | - |
| 1 | part `deathlog`: post-hook `0x44ce80` (player victims only), hook `0x44db20` (player deaths), ring buffer 64 per player, last-death record; `mxl2012 deathlog [n]` console lines; `deaths.txt` append; unit tests for the ring buffer and the line format (`deathlog_logic.h`, like the other `_logic.h` tests); harness verb `deathlog` | 1-2 days | low (read-only hook) |
| 2 | per-frame life sampler (DoT / unknown), poison owner, monster and superunique names, unique / champion tags, missile class via a missile-hit pre-hook, thorns mark; overlay panel on the death screen | 2-3 days | medium (offsets to verify, overlay layout) |
| 3 | optional: chat line for every player, report to joined players, a toggle in the launcher settings | 1-2 days | medium (server chat send not mapped) |

In-game test (slot 2, `game_checks.py` check `deathlog`, mortal character, god mode off):

1. Fresh character, fire resist set by `stat` to 0 and then 75; spawn a fire caster (Fallen Shaman); let it kill the
   player. The report's last entries must name the shaman, fire, an amount that falls by about 4x between the two
   resist settings, and life left falling to 0 at the death entry; the sum of logged damage in the last 5 s must match
   the life lost (stat 6 samples by `h state`) within 1 point.
2. A champion and a unique of the same class: the tags must read champion / unique.
3. Poison: a poison monster or `hit player poison`; the death must read as poison over time with the source.
4. Thorns: a monster with thorns, the player attacking until death: entries marked reflected.
5. Aura: a monster with a damage aura (Holy Fire class row) next to the player: entries with no missile, the aura owner.
6. Load: 30 monsters in melee for 60 s, frame time with and without the part (log per-frame times from the harness),
   no new asserts, no crash file.
7. `mxl2012-core-off.txt` word `deathlog`: hooks absent, nothing reported.

## 5. Open questions for the owner

- Last N seconds or last N hits by default? Proposal: the last 10 s, at most 64 hits, the overlay shows the last 10.
- File in the save folder (travels with the character) or the log folder (with the other logs)? Proposal: log folder.
- Should other players in the game see a one-line "killed by" in chat?
- Hardcore: keep every death report of a character (file), or only the last one?

## 6. Owner decisions (2026-11-05)

Planned for a later release, not scheduled yet:

- Window: the last 30 seconds before the death (at most about 64 hits).
- Nothing is saved: no `deaths.txt`, no file in the save folder. The report is a panel on the death screen that closes
  with the respawn, the killing blow highlighted at the bottom, and a Copy button that puts the text on the clipboard
  (for Discord or a bug report); players can also take a screenshot.
- So stage 1's file and the questions about the file place and Hardcore history fall away; the console lines stay as a
  tester tool. Single player and the host only (3.3).

Evidence and scratch: `mxl2012-runs/deathlog/notes.md`.
