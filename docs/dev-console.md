# D2RLoader developer console (debug mode) for scripted checks

Found 2026-10-21 with `tools/game_checks.py` (build 93847, D2RLoader 1.3.1, `enable_console = true` in
`d2rloader.toml`). Everything below was tried in the game unless marked "from the DLL strings".

## Opening it and enabling cheats

- **Ctrl + ` ** (backtick, scancode 0x29) opens and closes a dockable ImGui console over the top of the window. It works at
  the main menu and in game. Typing goes through SendInput scancodes (`game_ctl.type_text`), Enter runs the line. The
  newest output is the last line; `Console.run()` in `tools/game_checks.py` crops the panel (x 330-1270, y 0-235 of the
  1600x900 client area) for screenshots.
- `help` lists commands; `help cheats [page]` pages through the cheat names (the pages are the "legacy" list, the
  everyday names are not on the first page); `help cheat <name>` shows one cheat's usage.
- **`debug_mode` TOGGLES debug mode. It stays in force for the whole D2R process (across characters and games), and a
  second `debug_mode` switches it off again.** Without it every cheat answers `Cannot execute - Cheats are disabled.`,
  and in the menu `Cannot execute - Operator permission required.` (cheats need a running game). `enable_debug()` in
  game_checks probes with `cheat heal` and toggles only when that fails. `d2rloader.toml` says saved cheat settings apply
  only in debug mode; launching with `-debug_mode` also works (not tried).
- Console output is **not** written to d2rloader.log or mxl2012-core.log. The only way to read it is the screenshot.
  (The `ERR` tag is red: `console_error_seen` looks for red pixels in the newest line.)

## Plugin command

`mxl` prints one line per plugin feature, e.g.
`cube conditions on: 542 recipes (ops 29-42, second condition, gold cost)`,
`dungeon lockout on: 162 levels; tile warps on, portals on (refused 0, clocks started 0)`,
`goblins on: ... (FORCED 1) 0 spawned (last -1 in level -1), 0 rolls, 0 spawn failures`,
`npc actions on: 6 menu lines (Akara respec, Cain crafting materials); 8 stubbed services`. The counters make the
lockout and goblin checks readable without the log.

## Cheats that worked (`cheat <name> <args>`)

| Cheat | Use |
|---|---|
| `god 1` | invincible, infinite stamina/mana, `easykill` (one hit kills anything) |
| `heal` | refill life (harmless probe for debug mode) |
| `level N` | raise the player to level N (class clamped; `level 12` gave 55 unspent stat points) |
| `gold N` | add gold to the inventory |
| `goto <level id>` | warp: 1 Rogue Encampment, 2 Blood Moor, 37 Andariel's lair (Median ids = D2R ids) |
| `mspawn <monster id or name> ` | spawn next to the player (`mspawn fallen1`, `mspawn akara`, `mspawn 156` = Andariel) |
| `spawn <code>[,inv]` | item by Inventory code on the ground near the player (`leg`, `tbk`, `box` = Horadric Cube; `box,inv` puts the cube into the inventory) |
| `pickup` | moves the items on the ground near the player into the inventory (this is how scripts fill the cube) |
| `itemgroundclear` | removes ground items (`clearitems`, `groundclear` named in the help text are unknown) |
| `quests` | completes the quests of the current difficulty (this also unlocks the next one in the difficulty list) |
| `questcontrol a1q1/e4` | raw quest control (from the DLL strings: `aXqY/eN`, `xN` resets quest N); not used yet |
| `cubestuff <recipe>` | spawns recipe inputs on the ground; answered `failed` for recipes 2 and 3 (Khalim / Cow) |
| `skillpoints N`, `resetskills`, `resetstats`, `allskills`, `spawnrand <a|h|l|m|r|s|u>` | listed in the DLL, not run |

Names printed in the help text are not all valid: `cubeinputs`, `recipeitems`, `loc`, `spawnloc`, `clearitems`,
`groundclear` came back `Unknown cheat`. Try the name in game before relying on it.

Spawn cheats put things "near the player" whatever the pointer position; use pixel differences against a screenshot
taken before the cheat to find where (see `find_all_changed` / `clusters` in game_checks.py).

## Other findings that matter for scripts

- Characters on the main menu: cards on the right, 0.095 of the window height apart from y = 0.076 (x 0.87). The play
  button (0.394, 0.897) opens a difficulty dialog (Normal 0.42, Nightmare 0.482, Hell 0.542 at x 0.5) when more than
  one difficulty is available.
- A click on the ground walks (and the town NPCs are out of reach); **Shift + click attacks in place**.
- In the Esc menu Save and Exit is at (0.5, 0.44); the first Esc closes an open panel instead of opening the menu.
- Hell for a test character: `cheat quests` in Normal (and Nightmare) unlocks the next difficulty after Save and Exit.
- `MxlBarb` is level 126 and has finished Hell (card 1 "Champion"), not level 1 as in the lane brief.
