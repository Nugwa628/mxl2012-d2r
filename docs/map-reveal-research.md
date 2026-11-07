# Pity map reveal: research (lane mapreveal, 2026-11-06, for 0.1.14)

Owner idea (2026-11-06): once the player has explored a set share of the current level's automap, they may reveal the rest of
that level with a hotkey or a button near the level-up buttons. Research only. No feature code is committed. The probe verb
lives in `mxl2012-runs\mapreveal\mapprobe.cpp.inc` (not in the repo).

## 1. How a level's automap is revealed (build 93847)

Everything is client side. The server never sends automap data: the client builds its own copy of the act from the map seed
(its own DRLG), and the automap is a set of cells per level (one automap layer per level).

| What | RVA | Notes |
|-|-|-|
| automap "reveal room" callback | `0xd2240` | `(active room)`: adds the room's floor and wall tiles and preset objects to the current layer. D2R stores it in the client DRLG at `+0x838` and calls it for every room that becomes active near the player. That call is the whole "exploration" |
| create active room | `0x3289a0` | `(u8 data context, DRLG room) -> active room`: loads tiles and presets (`0x3f3970`, `0x3de0e0`, `0x328fd0`) and returns `room +0x58` |
| init level | `0x3271c0` | `(u8 context, level)`: builds the level's DRLG rooms when `level +0x10` is still empty |
| path -> room | `0x341c30` | `(unit +0x38 path) -> active room`; active room `+0x18` = DRLG room; DRLG room `+0x90` = level; level `+0x1f8` = level id, `+0x1c8` = DRLG, `+0x10` = first room (next at `+0x48`, tile x/y/w/h at `+0x60/64/68/6c`, active room at `+0x58`) |
| local context / player | `0x8b2d0` / `0x9a480` | `() -> context (0)`, `(context) -> client player` |
| current automap layer | `0x2a2cf68` | cells = the four tree sizes at `+0x28 / +0x50 / +0x78 / +0xa0` |
| debug "Reveal Automap" | `0xd42b0` | D2R's debug menu entry: reveals the whole act (an earlier lane saw the layer list grow 1 -> 25). Act scope, not level scope |
| D2RLoader console `revealmap` | (D2RCore `ExecuteConsoleCommand`) | act reveal as well. MapSense uses it for its "Reveal Act" action |

**MapSense's per-level reveal** (`reveal_engine.cpp` `RevealCurrentZone` -> `RevealLevelUnchecked`): resolve the player's client
level as above, check that `drlg +0x838` is exactly `0xd2240`, then for every DRLG room of the level call
`cb(CreateActiveRoom(ctx, room))`. That is about 30 lines and needs no hook. MapSense's only reason to hook `InitLevel 0x3271c0`
(an inline hook) is to remember the client DRLG and the context byte for its other features (atlas, POIs, GPS). For a single
level, the player's own room gives both.

**Next to mxl2012-core:** no clash. MapSense installs inline hooks at `0x3271c0` (InitLevel) and `0xd76e0` (automap unit
drawing), plus MinHook on D3D12 for its ImGui menu, and registers its own InputService actions. mxl2012-core hooks none of those
addresses (checked by grep of `plugin/src`) and registers no InputService action today. Still, we should not bundle MapSense
for this: our own reveal is ~30 lines.

Other MapSense features (out of scope, no work done): reveal act / reveal-all (every level of each act on entry), monster
markers by rarity with names, immunity letters or halos, missile dots on the automap, POI labels (waypoints, exits, quest
objects) from a map-generation helper exe (a Zig build of libd2), GPS navigation and routing to a chosen level, an ImGui
settings panel (D3D12 overlay), loot-filter and other mod compatibility profiles.

## 2. Measuring "explored percent"

D2R keeps no per-level "explored" counter. It has (a) the automap cells of each layer, which only grow, and (b) the active
rooms (`room +0x58`), which exist only near the player and are freed again behind them. Neither gives a percent by itself:
the cell count has no known total until the level is revealed, and the active set is not history.

Recommended measure: **tile area of the level's DRLG rooms that have been active at least once / total tile area of the
level's rooms.** The plugin keeps one bit per room for the current level (rooms <= 4096) and samples the room list a few times
a second (or every frame: see the timing in section 4). A room becomes active exactly when D2R calls the automap callback for
it, so "visited" matches what the automap shows. Area weighting matters because the rooms of outdoor levels are small uniform
blocks, while dungeon preset rooms differ a lot in size.

- Total: read from the client DRLG without revealing anything (the room list exists as soon as the level is initialised).
- Per level, not per area name: each level id has its own layer and its own room list. A multi-level dungeon (Tower 1-5,
  Catacombs 1-4) counts each floor separately, which fits "the current level".
- Bits reset on a new game (the automap is per game in D2R; Median's map memory does not change that).
- Exclude: towns (all five: always fully drawn), and levels with no real exploration or a scripted layout, e.g. Arcane
  Sanctuary? (big, but the point of the level), Uber levels (Matron's Den, Forgotten Sands, Furnace of Pain, Uber Tristram),
  the Cow Level?, boss arenas (Durance 3, Chaos Sanctuary, Throne, Worldstone Chamber). The owner decides; the list goes into a
  small table keyed by level id (mxl2012 ids after `tools/idmap.py`).
- Big open levels: the share grows slowly, since the active radius is about one screen. The same threshold feels harder there
  than in a corridor dungeon. That is acceptable for a "pity" button, but see the threshold below.

## 3. UI

| Option | Cost | Notes |
|-|-|-|
| Hotkey via D2RLoader InputService (`registerAction`, as MapSense's actions and the earlier `mxl_map_reveal` / `mxl_transmute` actions) | small | Free keys checked in an earlier lane: L (Median's own reveal key) is unbound in D2R's `.key` file. Rebindable in D2RLoader's input menu, stored in `input-bindings.toml` |
| Chat line when it becomes available ("Map completion available: press L") | small | client-side system line; must wait while an NPC talks (a chat record during an NPC speech freezes it: d2r-addresses.md "Send to stash") |
| Button like the level-up buttons | medium-large | D2R's `LevelUpButtonWidget` (plugin-plan.md section 24) has three fixed types (skill, stat, quest) with fixed click handlers: not reusable as is. Route used by lane sendstash: a D2RLoader widget button on a registered empty panel, with its own layout JSON for HD (`...hd.json`) and legacy, art for both modes, and the hit-test pitfall (hidden widgets still take clicks) |

Hotkey + chat line is the cheapest and works the same in HD and legacy. The button can come later with its own art.

## 4. In-game probe (slot 2, 2026-11-06, background mode, branch build + an uncommitted harness verb)

One run: `mxl2012-runs\mapreveal\probe_scripts\mapprobe_run.py`, evidence `mxl2012-runs\mapreveal\run-20261106-s2\`
(`mapprobe.txt`, `game_ctl.log`, `hd_lvl3_before.png`). Verb `mapprobe [reveal]` (`mxl2012-runs\mapreveal\mapprobe.cpp.inc`).

| Where | Result |
|-|-|
| Rogue Encampment (1) | 35 rooms, area 2240 tiles, all 35 active: 100 % (towns are fully active, so they must be excluded) |
| Cold Plains (3), on arrival | 98 rooms, area 6272, 20 active: **20.4 %** on arrival; automap cells 785 |
| after 9 harness `move` steps | the active set moved (20 -> 16 rooms), explored stayed 20.4 % (the steps were short); cells 785 -> 831 |
| room walk cost | `walkms=0` for 98 rooms (and the 4096-entry seen list): cheap enough every frame |
| `mapprobe reveal` (hook-free per-level reveal: `CreateActiveRoom(0x8b2d0(), room)` + `0xd2240` on all 98 rooms) | **the game process closed** (no answer, no crash dump in the slot, `game_ctl` "not running"). Not retried: one probe run |

What this shows:

- Reading the level (rooms, area, active rooms) from the player's client room works without hooks, and the area measure behaves
  as intended (20 % on arrival in a field level, 100 % in town).
- The per-level reveal needs the exact arguments MapSense uses: the `u8` context byte and the client level as captured by its
  `InitLevel 0x3271c0` hook, re-fetched through `GetLevel 0x3267c0(ctx, drlg, id)`. Using `0x8b2d0()` (0) as the context byte, or
  the player's room's level directly, is wrong for at least one of the two. The feature must hook `InitLevel` the way MapSense
  does (an inline hook, 14 entry bytes `48 89 6c 24 20 56 41 56 41 57 48 83 ec 20`) and call MapSense's sequence unchanged.
  Not proven in game yet.
- Fallback that is known to work (lane gap-travel, 2026-10-22): D2R's debug "Reveal Automap" `0xd42b0`, which reveals
  the whole act, not just the level.
- HD / legacy screenshots after a reveal were not taken (the game closed). Only `hd_lvl3_before.png` exists. MapSense's
  `revealmap` console path was not tried.

## 5. Recommendation and effort

- Rule: when the explored area share of the current (non-excluded) level is >= **70 %** (default), the hotkey reveals the rest of
  that level. Below it, the key prints "Explored N % of this level (70 % needed)". One chat line the first time a level passes
  the threshold.
- Configurable: yes, one value (threshold 0-100, 0 = always, 101 = off) plus the hotkey. Settings live with the plugin's other
  player settings (D2RLoader stores the key binding itself). No per-level table for players.
- Multiplayer: purely client side and per player. Each client measures its own exploration and reveals only its own automap.
  Nothing goes to the server, so it gives no advantage over what D2R's own debug reveal or MapSense already allow. Party members'
  automap sharing (D2R shares nothing here) is unchanged.
- Reveal: the MapSense sequence with an `InitLevel` hook (section 4). First step of the feature lane: prove it in game, HD and
  legacy, and check that walking into revealed rooms later still works (the created active rooms are released by D2R as usual).
  If it cannot be made safe, use the act reveal `0xd42b0` and tell the player it reveals the act.
- Effort: hotkey + measure + reveal + chat line + exclusions + a harness verb and a game check: about 1 lane day (~300 lines with
  tests). The HUD button for HD and legacy, with art and layouts: another 1-2 lane days.

## 6. Result of the feature lane (2026-11-06)

The hook-free per-level reveal works when the context byte is the player's data-table flag `0x34a0e0(player)` (unit `+0x1bd`):
the probe's `0x8b2d0()` is 0, the server's byte, and that is what closed the game. No `InitLevel` hook is needed. Game check
`mapreveal`, run `checks-20261106-172408-s1` (slot 1): HD Cold Plains and Den of Evil, legacy Blood Moor and Cave Level 1,
every room made, the game went on, 0 crash files. The part: docs/plugin-plan.md section 34.
