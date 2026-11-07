# HD vs legacy combat (lane hdcombat, 2026-11-06)

Player report: damage, hits and procs (chance to cast on attack / strike) "don't seem to work as well" in HD graphics but
work in legacy graphics.

## Measured

Check `hdcombat` (tools/game_checks.py), Barbarian `HdCombat`, level 30 stat, tanked, Blood Moor, one zombie with 200000
life (restored after each hit). Per round: 30 background left clicks with a Broad Sword (Grade 1), 30 clicks with a chance
to cast weapon, then the left button held for 20 s. Rounds in the order HD, legacy, HD, legacy. Hits = clicks after which
the zombie lost life; damage = life lost.

| Run | Mode | Plain clicks: hits / damage | CTC weapon clicks: hits / damage | Held 20 s: damage | Server frames per 30 clicks |
|-|-|-|-|-|-|
| run1 (slot 1) | HD | 23 / 27, 29 / 41 | 29 / 37, 28 / 39 | 90, 84 | 2292, 2314 |
| run1 (slot 1) | legacy | 30 / 42, 30 / 38 | 28 / 31, 29 / 39 | 83, 83 | 2439, 2421 |
| run3 (slot 2) | HD | 29 / 35, 28 / 36 | 23 / 35, 28 / 41 | 88, 88 | 2195, 2231 |
| run3 (slot 2) | legacy | 30 / 39, 29 / 31 | 26 / 34, 29 / 48 | 78, 81 | 2333, 2286 |

Totals over the 30-click rounds: HD 217 hits / 291 damage in 240 clicks, legacy 231 hits / 302 damage in 240 clicks.
Held button: HD 350 damage, legacy 325 damage in 80 s each. The server ran 25 frames/s in both modes (held rounds: 507-519
frames in 20 s).

Reading: the server deals the same damage per hit and the same damage per second in both modes. With the button held
(server-paced attacks), HD is not weaker. The few missed clicks in HD (23 and 28 of 30 in the bad rounds) come from the
click: `click_unit` aims with the HD screen projection and the zombie walks. They are not misses decided by the server.

Procs: not measured. No proc fired in either mode (0 missiles in every round), so the harness set-up is the problem, not
the graphics mode:
- `equip <code> rhand 195:<skill<<6|lvl>=<chance>` (raw stats on a harness item): the stats are on the item (`stat 195:2305
  = 50`), but the item events that `itemstatcost` `itemevent1` (domeleeattack) needs are added by the property code, which
  the harness skips.
- Addertongue (`uniqueitems` row 327, 25 % Venomous Spirit 841 on attack), made in the backpack and worn by the client
  packets 0x19 / 0x1a: still 0 missiles. It is not confirmed that the item was worn, or that Venomous Spirit (srvdofunc 101,
  `venomousspider`) shows up in the `missiles` tracker.

## What does not depend on the graphics mode

- Combat rules run in the game server, the same code in both modes. The plugin reads D2R's HD flag (RVA 0x846210,
  panelmgr+0xb9) only in `lvlup_ui.cpp` and `rotw_stash.cpp` (UI). No combat, item-event or missile part of the plugin
  reads it.
- Attack timing comes from `animdata.d2` (merged by tools/animdata_merge.py: Median's speed and events where the frame
  count matches). D2R reads it in HD too. Only 4 monster records keep D2R's timing, and no player record does.
- FPS: the server frame rate is 25/s in both modes (above). Lower client FPS in HD does not slow the server's attacks.

## What differs in HD (looks only)

- Missiles and overlays: Median's missiles are drawn in HD with D2R art picked by tools/effects_hd.py (exact 1550, prior
  266, hand 110, provenance 59, stand-in 40 of 2025). 779 missiles on 272 CelFiles have no HD model of their own
  (missile_hd report). A proc whose missile uses a stand-in or a small recolour can look like a different or weaker skill
  in HD, or be hard to see. Legacy draws Median's own DC6 art. This is the likely reason procs "look" weaker.
- Player swing animations in HD are D2R's models (hd_skill_anims.py gives Median sequence skills an HD state). The hit
  frame is still the server's.

## Proposal

1. Make the proc comparison work: confirm the packet-worn item with `items` (page 255, body 4), then count procs by a
   skill with a plain `srvmissile` (e.g. Gnarled Root row 558, Poison Flash Proc `barflashpoison`, 5 %, or a magic affix
   with Fire Bolt on attack). Use 100+ attacks per mode.
2. If the server proc counts match, list the proc skills of common items whose HD missile is a stand-in or has no art
   (`work/mod/effects_hd.md`) and give them visible HD art.
3. Ask the reporter for one concrete item and skill. "Damage looks weaker" with the same numbers is most likely the HD
   look (smaller or recoloured effects, different hit sounds).

Evidence (outside git): `mxl2012-runs/hdcombat/run1.log`, `run2.log` (script error, no numbers), `run3.log`; reports
`work/runs/checks-20261106-174647-s1`, `checks-20261106-183032-s2`.
