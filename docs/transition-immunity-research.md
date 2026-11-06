# Transition immunity: research (lane transimm, 2026-11-06)

Owner (2026-11-06) about the D2RLoader plugin Transition Immunity in the owner's own repo
([Nugwa628/D2R-Tools `plugins/transition-immunity`](https://github.com/Nugwa628/D2R-Tools/tree/main/plugins/transition-immunity)):
"we will have to see if it works, and maybe just implement it directly without the plugin itself in some form".

**Short answer.** The plugin loads and runs on our build (D2R 3.3.93847, D2RLoader 1.3.1-beta, next to mxl2012-core
0.1.13) without a hook clash or crash, and its window works as described (starts on every new level, ends on a step or
after 60 s, shield over the head). **But it does not stop damage.** Its hit hook is on `0x44a9b0`, the get-hit reaction,
which every damage caller runs *after* `0x44ce80`, where life is taken and poison, cold, freeze and stun are applied.
In game the character lost life and got poisoned while the plugin logged "104 hits blocked". Curses are blocked
(`0x55a7e0` works). Recommendation: **(b) port the logic into mxl2012-core**, server side, with the damage check on
`0x44ce80` and a stricter window (Median 2012 balance), behind a config toggle. Research only: no feature code.

Evidence and scratch (outside git): `mxl2012-runs/transimm/`: the download (`src/`, upstream commit `fb0c8425`), the
MSVC build (`buildcfg/`, `build/Release/d2rl-transition-immunity.dll`, PluginSDK `03a5af9` as upstream pins), the run
script `run_transimm.py`, `run1.out`, `run2.out` and the two run folders.

## 1. What the plugin does (version 1.0.1, source read in full)

| Point | Plugin 1.0.1 |
|-|-|
| Which transitions | Any time the **client** sees the local player in a new level id: waypoint, town portal, cave or dungeon entrance, stairs, act change, joining a game. Also a level change by teleporting across a level border (any level id change counts). Detection: a 50 ms timer queues a tick on the UI thread; local player `0x9a480(0x8b2d0())`, level `0x2efc10(0x34b440(unit))` |
| Loading screen | Covered as well: while the server unit's level differs from the level the client last showed, the player counts as protected (`IsProtected`, the "loading" case) |
| What is blocked (claimed) | Every landed hit (melee, missiles, spells, traps, damaging auras), curses. Not blocked by design: non-damage aura effects (Holy Freeze slow, Conviction), poison already ticking |
| What is blocked (real, section 2) | The **get-hit reaction** of a hit (`0x44a9b0`: hit recovery / block / knock-back modes, the state checks after it) and **curses** (`0x55a7e0` returns 0 for the player). **Not** blocked: life, mana and stamina loss, poison, cold, freeze, burning (all in `0x44ce80`, before `0x44a9b0`) |
| Targeting / aggro | Not touched. Monsters see, target and attack the player as usual; only the outcome of the hit is filtered |
| How long | Until the player moves or `duration_seconds` (default 60, 1 to 3600) have passed. A 0.6 s grace after arrival in which position changes are ignored |
| What ends it | Player mode walk / run / town walk (2 / 3 / 6), or a position change of more than 2 sub-tiles (teleport included), or time up, or leaving the game, or `enabled = false`. **Attacking or casting in place does not end it** |
| Server / client | Hooks run on the server thread (inline hooks on `0x44a9b0` and `0x55a7e0`), window logic on the client UI thread; the two share the player's unit id and two atomics |
| Single player only? | Single player and a TCP/IP game you **host**, and then only for the host's own character (it compares with the local client's player id). Joiners get nothing, in either direction |
| Indicator | Overlay `ShrineArmor` (overlay.txt row found by Filename at table load) put on the client's player with `0x150280` / removed with `0x152090`; choosable in I Hate TOMLs |
| Build check | First 16 bytes of each function compared at load (Steam 3.3.93787 / 94995 named); on a mismatch it stays inactive. All seven checks match on 93847 (same RVAs as our own code: `0x8b2d0`, `0x9a480`, `0x34b440`, `0x2efc10` are used by mxl2012-core too, [d2r-addresses.md](d2r-addresses.md)) |
| Config | `d2rloader/config/transition-immunity.toml` (written on first launch from the embedded default), live through the I Hate TOMLs menu |

### Vanilla Diablo II

No load-in invulnerability was found in 1.14d (redivivus database, time-boxed). Monster targeting
(`MONSTERAI_CanTargetUnit` `0x5dc970`) only refuses a dead target, a target in a town room, a target without
`UNITFLAG_CANBEATTACKED` and (partly) an invisible one; the hit itself only asks `UNITS_CheckIfCanAttackTarget`
`0x554200` (hostility). The join path (`NET_D2GS_SERVER_SrvJoinAct` `0x530190` -> `CLIENT_PlacePlayerInRoom` `0x5394a0`)
sets no protection. The only vanilla "safety" on arrival is that town rooms cannot be targeted. Not checked: whether
D2R added anything of its own (the run below shows none: unprotected life loss right after arrival without the plugin's
window is the same as with it).

## 2. Does it work on our build (in game, slot 1, 2026-11-06)

Slot 1 (D2R 3.3.93847 Battle.net install, D2RLoader 1.3.1-beta), mod of this branch (`tools/build.py`, main 038116d,
`install_mod.py --slot 1`), the plugin DLL placed in `mods\mxl2012\d2rloader\plugins\` for the run and removed after
(with its config and log). Character `TransImm` (Barbarian, new), life raised to 30000 (`Tank`). Per arrival: five
zombies (class 5) and a doomknight3 (class 312, owns Decrepify, skill 87) spawned at the player, the doomknight casts
Decrepify at the player (`mcast 87 11`); life and states read before and 8 s later while standing; then one `move`
step and the same again.

| Check | Run | Result |
|-|-|-|
| load, clashes | `checks-20261106-105039-s1`, `-110630-s1` | PASS: "Transition Immunity 1.0.1: active" (both hooks installed, no "hits only"), D2RLoader lists it, no hook refusal, mxl2012-core loads as usual, **0 crash files**, plugin files removed (`left: []`). mxl2012-core hooks neither `0x44a9b0` nor `0x55a7e0` nor the overlay functions |
| window and indicator | both | PASS: one "protected" line per new level (load-in level 1, waypoint level 3, town portal 1 and back 3, cave 9); ends "you moved" on the `move` step, "time up" after 60.0 s standing (run 1), "left the game" on exit; the shield floats over the head (`ti_waypoint_standing.png`) |
| waypoint (town -> Cold Plains by the panel) | `-105039-s1`, `-110630-s1` | **FAIL**: life 30000 -> 28827 and poisoned (state 2) while protected, plugin log "34 hits blocked" |
| town portal (scroll in Cold Plains, through to town, back through the portal) | `-110630-s1` | **FAIL** for damage: life 16873 -> 12175 standing, log "104 hits and 5 curses blocked"; curse PASS (no curse state standing; state 298 after the step) |
| cave entrance (Cold Plains -> Cave Level 1, the entrance's own warp) | `-110630-s1` | **FAIL** for damage: life 2325 -> 921 standing (poisoned), log "45 hits and 9 curses blocked"; after the step the character died |
| curse ends with the window | `-110630-s1` waypoint | PASS: Decrepify (state 60) only after the step |
| loading-screen part | both | not seen: "0 of them while loading" each time (a single-player load is too short for the spawned monsters; needs a slow load or a joiner) |

Why: D2R's damage callers (36 of them, e.g. the melee hit `0x44b2b0`: `0x44ce80` at `0x44b3fa`, then `0x44a9b0` at
`0x44b4f4`; the aura pulses `0x561280` / `0x561480` likewise) call `0x44ce80` first. `0x44ce80` is the one place that
subtracts life and applies poison, cold, freeze, burning and stun ([death-report-research.md](death-report-research.md)
1.1, verified there). `0x44a9b0` (size 0xaf) is the reaction afterwards: can-attack test `0x48e060`, then the get-hit
mode `0x34c2c0` and the knock-back / state calls `0x451e50`, `0x451fb0`, `0x3351b0`, `0x3354c0`. Skipping it removes hit
recovery and knock-back only. Nothing in our mod changes that order (mxl2012-core has no hook on either function), so the
plugin behaves the same in plain D2R on these builds. This is a bug in the plugin (its README says "the hit does
nothing"); the owner may want to fix it upstream: skip `0x44ce80` for the protected defender (the `hit` row of the old
harness table in [testing.md](testing.md) repeats the same wrong reading of `0x44a9b0` as "life").

## 3. How to put it in the mod

| Way | What | Effort | Verdict |
|-|-|-|-|
| (a) ship the plugin as a bundled plugin (like Buff HUD, [bundled-plugins.md](bundled-plugins.md)) | package the DLL, its licence, a default TOML | 0.5 day packaging, **plus** an upstream fix first (it does not stop damage today) and a release cadence tied to D2R-Tools | No: does not work as is; window rules too loose for Median (below); host-only; a second set of build checks and a second log to support |
| (b) port the logic into mxl2012-core as a part with a config toggle | see the design below | about 2 days: server window per player and hooks (1), state row and indicator (0.25), config and unit tests of the window logic (0.25), a game check in `game_checks.py` and a run (0.5) | **Pick** |
| (c) data only | a state given on level entry by existing mod mechanics | none possible | No: no table has a level-entry trigger (levels.txt, states.txt, skills.txt, monstats have no "on arrival" event), and no stat makes a player immune (Median caps damage reduction and resistances). Data is only the indicator half of (b) |

### Design for (b) (for the implementation lane)

- **Server side only, every player.** A callback of mxl2012-core's shared per-game server frame hook
  (`plugin/src/server_frame.cpp`, `0x406550`, 25 Hz; the harness and `spiritwarp` use it), keep per player unit: last level id (`0x2efc10(0x34b440(unit))`), window start frame,
  start position. A new level id (or the first frame of a player in the game) starts a window. Protects joiners in a
  hosted TCP/IP game too, and covers the loading time from the server's side (the server moves the unit before the
  client has loaded), with no client-server split.
- **Damage:** an inline hook on `0x44ce80` (game, attacker, defender, bApplyDefenseReduction, damage): protected
  defender = return without applying (as the can-attack test's refusal does). Keep a hook on `0x44a9b0` too or not:
  `0x44a9b0` repeats the can-attack test, the reaction does nothing harmful once life is not taken; measure in game.
  Only monster (and monster-owned) attackers: PvP hostility stays the engine's.
- **Curses:** the `0x55a7e0` per-target step, as the plugin does (it works).
- **Indicator and flag in one:** a new states.txt row (overlay `ShrineArmor`-like, no stats) set and cleared with D2R's
  set-state `0x3355a0` (the harness `setstate` call); states go to every client by themselves, so joiners see it and the buff bar / Buff HUD can show it.
  The damage hook then tests that state, nothing shared between threads.
- **Ends:** any position change past 2 sub-tiles, walk / run, **any attack or skill use** (player modes 7, 8 and 10-18:
  attack, cast, throw, kick, skill; not 9, block), item use, or a cap after arrival (proposal: 3 s once the client has loaded; while the server still
  waits for the client the window stays). Towns: no window (already safe).
- **Config:** `[transition_immunity] enabled = true` in mxl2012-core's own config (as the other parts' toggles), the cap
  in seconds; log one line per window as the plugin does (hits / curses blocked).
- Check names for `game_checks.py`: `transimm` = the run of this lane with the expected results inverted where the plugin
  failed (life unchanged and no poison while standing, after the step life drops and Decrepify lands, attack in place
  ends the window, cap ends it).

### Balance and multiplayer

- The plugin's rules invite abuse in a hard mod: **casting or attacking in place does not end it**, for up to 60 s.
  A Sorceress / Necromancer / trap Assassin can town portal or walk into an uber or boss room and kill from where she
  stands, immune (once damage is really blocked). In Median XL 2012, whose endgame is about surviving bosses and
  uber levels, that is a real exploit. Hence: end on any action and keep the cap to a few seconds; consider no window
  on the uber / boss arenas (levels.txt ids, a config list) if the owner wants it stricter still.
- Summons and the mercenary are not protected (nor should they be). The "loading screen" part is the real value: a slow
  load (or a joiner's) is the classic death in Hardcore.
- Multiplayer: the plugin protects only the host's own character; a joiner with the plugin gets nothing and a joiner
  without it is unprotected in the host's game. The server-side port protects every player of a game hosted with the
  mod (all players run the mod anyway, since the data must match). D2R online play is not a concern (the mod is offline /
  TCP/IP only).
