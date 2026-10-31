# In-game tests waiting to be run

Changes that are built and installed but not yet confirmed in the game. Restart D2R after an install. Move an item to
"Confirmed" (or into docs/bugs.md) once tested. Console command `mxl` shows the plugin version and how many skill
functions it installed.

## Waiting

Lane skills5 (2026-10-29, slot 3, background input, dev DLL): player bugs #490-#493, #496 (docs/bugs.md). Seen with the harness:
Signet of Gold text (#490) in HD; Bane Hunter's HD overlay (#492) calm after the `firecrown` pick. Still to check: the #490 line in
legacy (hover the signet in the classic inventory) and on the other 15 rows (Life / Mana packs, the other signets); the
`firecrown` glow by a player's eye (x0.6 is faint); #491 (leap skills) needs the player's `d2rloader.log`; #496 waits on
the owner and the player (#493: section "Lane totems"). Scripts and evidence: `mxl2012-runs/skills5/` (`leapstress.py`, `lab.py`, `signet.py`).

Lane hditems (2026-10-29): **HD item picture quality** (docs/hd-icons.md "Picture quality"; graphics check, seen with the harness,
not a player-path verification). `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all mxl2012 hdit_icons`:
16 Median items (`item <code> inv`: D2R HD reused / recoloured / rescaled gems, Vex rune, book, soul stone; upscaled runes, signet,
rings, crystals, elixir; palette 225-254 pictures) in the backpack, screenshots `hdit_inv_hd.png` / `hdit_inv_legacy.png`, judged
by hand. Run `checks-20261029-024504-s4` (slot 4, new level 1 Barbarian HdItems, build of lane/hditems with the main checkout's
plugin DLL): all 16 made and drawn in their cells in HD and legacy; in HD the reused ones show D2R's own art (Onyx grey, Amber
orange, Vex rune), the upscales are crisp, no black specks on the palette-fill pictures; no crash file. The check reads FAIL
only on `wPrefix != 0 || wSuffix != 0` (Items.cpp:906), raised by the harness `item` generator (bug #35, harness artifact; the
first run, `checks-20261029-024240-s4`, also had it with the `yq9` charm, now replaced). Still to look at by hand: vendors and the
stash in HD (more pictures), the 7 skill icon sheets' palette-fill pixels.

Lane procicons (2026-10-29): **icons of the skills items give** (docs/hd-icons.md "Item skills on the skill bar"; graphics
check, seen with the harness, not a player-path verification). `MXL_RUN=<lock> MXL_SLOT=N py -3 tools/game_checks.py all
pic_skillbar`: two rings and an amulet worn by `equip` with 20 charges of Apocalypse (`Apocalypse_mxl`), Summon Fallen and
Lightning Shield, and the oskill skills Ice Lance, Spin To Win and Summon Treewarden learnt by `setskill` (an oskill added by
`equip` never reaches the game: it sets the stats after the item is worn, also after Save and Exit; the harness' own weapons are
refused by a click, "I can't use this yet"); the left and right skill pop-ups shot in HD and legacy. Run
`checks-20261029-045215-s3` (slot 3, the test Barbarian, level 1; build of lane/procicons with its own plugin DLL; shots in
`mxl2012-runs/procicons/game-20261029`, never in git): PARTIAL (judged by hand), 0 asserts, no crash file. **Seen**: each charge
on its donor picture with its count (Summon Fallen on Median's Void Archon summon, Apocalypse on D2R's Meteor, Lightning Shield on
D2R's Thunder Storm), Ice Lance on D2R's Ice Blast, Spin To Win on D2R's Whirlwind (drawn red: the Barbarian cannot use it yet), the
same pictures in HD and in legacy, no "?" left. Summon Treewarden is learnt but the game lists it in neither pop-up (its row has
`reqlevel` -10; not an icon question). Still to see: the oskills on real Median items worn by a player (a uniques run).

Lane tints (2026-10-29): **per-TransLvl colours and gradient-tinted effects in HD** (`tools/hd_translvl.py`, docs/hd-monsters.md
section 8; `tools/hd_recolour.py`, docs/hd-effects.md section 5a). Check `tint_hd` (tools/game_checks.py, seen with the
harness, not a player path): `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all tint_hd` after
`tools/build.py` and `install_mod.py`. Per filled level it spawns a level-0 monster (screen right) and one of the level (left)
in an Act 1 area of its own, shoots them alive in HD, kills them and shoots the corpses in HD and legacy (`tint_mon_*`); then
it fires each tinted missile (right) beside the untinted source (left) with a 5-shot burst per mode (`tint_fx*`). Runs
(TintLane, background input, shared files restored after each; screenshots and side-by-side crops in `mxl2012-runs/tints/run1`
.. `run4`, never in git):
- `checks-20261029-023258-s4`: first version; one disabled row (`darkguard1`) asserted `MONFLAG_ENABLED` on spawn (the check
  and `hd_translvl.py` now skip disabled rows).
- `checks-20261029-023840-s4` (town) and `checks-20261029-030506-s3` (corpses per area): PARTIAL, 0 asserts, no crash. **Seen**:
  the mod's variant table is loaded in HD (`minion1` level 3 corpse darker and greyer than level 0, where D2R's entry is
  identity), and classic draws TransLvl t through palshift table t + 2 (Quill Rat level 3 black, level 4 purple), which
  corrected `hd_translvl.py` (it read table t). Harness-killed Quill Rats leave no HD corpse.
- `checks-20261029-032744-s2`: casting monster skills via `setskill` on the player asserted `nDesc < skillDescTbl.size()` and
  crashed after the HD round (the check no longer does that; not a mod problem).
**Not seen**: no harness-fired missile (`missile` verb, nor `cast`) showed on screen in any run, so the gradient tints have
no in-game evidence yet (offline: `mxl2012-runs/tints/offline/gradients_before_after.png`). The corrected level colours (10
levels) have not been looked at in game. Next: a player-path look (a character with the skills: e.g. a Median Fire Bolt
row `barfirebolt` / `magefirebolt1`, the purple Frost Nova `darkpowernova`) and the Quill Rat / Wisp levels alive in HD.

Lane cube2 (2026-10-28): **cube recipe classes, second round, and plugin part `cubedupe` (#350)** on slot 2 (`MXL_RUN=cube2 MXL_SLOT=2 MXL_CHAR=CubeLane py -3 tools/game_checks.py all mxl2012 cubeclasses`, run `checks-20261028-162149-s2`): `mxl2012` PASS (line `cubedupe on: ...`); every cubeclasses case PASS except zomghelp (skipped: CubeLane on slot 2 is level 40 now) and the Token (not lifted out of the cube by packet), among them the dupe (two weapons in the cube, `item_hasbeenduped` 1; the copy's second dupe refused), socket creation 845 (socket-free roll, 1 socket), unique uptier 8421 with an item level 99 input, the signet disenchant 869. Rows 580 / 28 on a new level-1 Barbarian (`MXL_CHAR=CubeTwo MXL_CUBE_ONLY=580,28`, runs `checks-20261028-162741-s2`, `checks-20261028-163101-s2`): zomghelp PASS by the tooltip ("+25% Enhanced Damage", damage 20-31 on a 16-25 base; `istat` reads stats 17 / 18 as 0 on every layer, so the case now reports them and the shot judges); Token of Absolution PASS: lifted out of the cube by clicks (the packet 0x19 forms asserted `len == sizeof(command)` or did nothing), a Signet of Learning used and the point spent on Strength (packet 0x3a, 5 bytes in D2R: the 3-byte form asserted `sizeof(cmd) == len`), then the Token used by a right click: used up, Strength back, the point unspent again (#240). Shutdown pool asserts (`s_StatsPool.IsEmpty()`, `m_allocated == 0`, `m_sortedBlockCount == 0`, `_bcObjectPoolBlockListIsEmpty(m_usableBlocks)`, `m_freed == 0`): at every game exit of these runs and of other lanes' logs that reach the exit (rulescheck), also after a data-load abort before any game was entered (datafix `v1-d2rloader.log`: the pool family without `s_StatsPool`), and in 434 run folders of another mod (there too: exit-only, ignored); no crash file. Engine leak checks at exit, not caused by this mod: no bug filed. An exit of an unmodded D2R was not logged on this machine.
Lane runeletters (2026-10-28): **Rune letters of Median's Great Runes in runeword tooltips** (bug #334; plugin part `runeletter`, `plugin/src/rune_letters.cpp`, off word `runeletter`; docs/plugin-plan.md section 19). Built and unit-tested (`runeletters_tests`, `tools/test_game_checks_runeletters.py`), not yet run in game (coordinator: no slot for this lane; the coordinator runs it). Check: `MXL_RUN=<run> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all mxl2012 runeletters` (background input). `mxl2012` must have `runeletter on: rune letters without a D2R key drawn from the gems cell ...`; `runeletters` makes Dawn (El in a 1-socket `100`), Gehenna (Xar `r47` in a 1-socket `100`) and Kyrie (Taha Taha `r51` in a 2-socket `152`) on the player path (harness drop, click pick-up, click insert), hovers each, screenshots `rl_0..2.png` and reads the counters. Expected: all three runewords made, both counters grown (drawn from the cell for Xar / Taha, D2R key kept for El), no assert / crash file; by hand: the quoted letter line reads 'El', 'Xar' (not 'Ornate Plate') and 'TahaTaha' (not 'Missing stringMissing string'). Control: `MXL_CONTROL=runeletter` gives back the old texts

Lane cube (2026-10-28): **Horadric Cube recipe classes on the player path** (`tools/cube_game.py`, check `cubeclasses`; harness verbs `pkt pickup cursor ground move packclear remove` copied from lane realpath, new read-only `istat <item id> <stat> [layer|scan]`). Run `checks-20261028-141125-s2` (slot 2, new level 1 Barbarian CubeLane): 16 of 22 cases PASS (rune up / down, unsocket `rem`, `usetype` rerolls low / rare / unique, op 3 refusal, full honorifics, op 15 honorific + Mystic Orb on input 1 only, Apple of Discord's skill parameter, uptier `mod`, RIP, destruction, clue gem, summoning scroll, Token made); results and open cases in `docs/median-rules-audit.md` "Cube recipe classes in game". Still to run (no slot was free for an hour after the input fixes): `MXL_RUN=<lock> MXL_SLOT=<n> MXL_CHAR=CubeLane py -3 tools/game_checks.py all cubeclasses` for socket creation (845, socket-free roll), zomghelp's damage (580: stats 17 / 18 and the tooltip), unique uptier with version 10 (8421) and the signet disenchant (869) with item level 99 inputs, the dupe refusal (8397 second try); bug #350 (no copy from the Oil of Duplication) stays open. Engine log of that run: BC_ASSERT pool lines (`s_StatsPool.IsEmpty()`, `m_allocated == 0`) only in the last seconds while the game was shut down after the check, no crash file; not looked into further. By hand: use a Token of Absolution made in the cube (the check could not move it out of the cube by packet)
Lane acts (2026-10-28): **Acts 2-5 and the difficulties on the player path** (check `acts`, tools/game_checks.py; harness verbs
`interact`, `menu`, `msg`, `quest`, `xp`, `moveto`, `move`, `presets`, `place`, see "Harness commands" below). Run:
`MXL_SLOT=N MXL_RUN=acts MXL_CHAR=<throwaway> MXL_ACTS=<stages> py -3 tools/game_checks.py all acts`, stages in order
`towns andariel travel12 duriel travel23 mephisto travel34 diablo travel45 ancients baal nightmare` (default all). Owner rule: no god
mode, no invulnerability, no easykill. Help the check gives and names in every row: travel (`level`, `place`), character level (`xp`,
the game's own award) and gear (`equip`: a weapon with damage, a ring with vitality, 75 resistances and 50 % damage reduction). The
boss is the level's own unit (found through the level's preset list, walked to with `move`), fought with the Attack skill through the
cast path; the NPCs are talked to with the server's talk packet and their menu lines run through the line's own handler. A step done
only with a shortcut is "shortcut only" and stays open. Runs (slot 2, character `ActsBarb`, Barbarian, background input,
watchdog clean, 0 crash files; harness help in every row: travel with `level`, level with `xp`, the gear of `acts_gear`):

| Run | Stages | Result |
|---|---|---|
| `checks-20261028-133014-s2` | towns, andariel, travel12 | towns: menus read for Gheed d35/d44/d46, Kashya, Warriv, Warriv (Act 2) d35/d37, Jerhyn, Hratli d35/d06, Meshif (Act 3) d35/d39, Cain (Act 4), Tyrael (Act 4), Malah d35/d44; the other NPCs stood out of the talk range (the script now walks up and looks around). Waypoint panel opens (`acts_town4_waypoint.png`). **`BC_ASSERT: 0 (AssetCache.h:187)`** on entering Catacombs 4 after the five towns (bug #360) |
| `checks-20261028-134603-s2` | andariel (stopped) | the walk did not fight back and the character died to the chamber's archers; walks now fight what is in reach and stop on a death |
| `checks-20261028-170422-s2` | andariel, travel12 | **Andariel PASS**: level 62, killed with Attack in 19 s, 0 deaths, quest 6 `0000100000000000` -> `0100100000000100`. **travel12 PASS**: Warriv's menu gained line d36 after her death, its handler took the character to Lut Gholein (40) |
| `checks-20261028-171213-s2` | duriel .. nightmare | **Duriel PASS**: killed in 61 s, 0 deaths, quest 14 `0010000000000000` -> `0010010000000000`. Mephisto, Diablo, the altar and Baal were not found from the arrival (the search now walks to the level's presets with `moveto` / `presets`) |
| `checks-20261028-174532-s2` | ancients (before #362) | the altar summoned 540, 541 and 935 (goatpriest4, Median's Siege Boss) with 771 minions, no 542; quest 39 stayed `0001...`; the gateway refused: bug #362 |
| `checks-20261028-180749-s2` | ancients, throne, baal, nightmare | **Ancients PASS (after #362)**: summoned 540, 541, 542, all killed, 0 deaths, quest 39 `0001000000000000` -> `1001000000000100`; the first gateway operate only opened it (mode 1). Throne: one death to a burst of about 9000 near (15079, 5158). Baal not reached |
| `checks-20261028-191050-s2` | travel23, mephisto, travel34, ancients, throne | travel23: Meshif in Lut Gholein shows Talk only (d35) after Duriel, Tyrael and Jerhyn were talked to: open. Mephisto found (life 56,440) but not hurt in 240 s: the character stays hit-locked (mode 1) among the Durance's council, 0 deaths. **Gateway PASS**: the repeated operate took the character to the Worldstone Keep (128) (the quest was done in the run before, so the stage's own quest test said FAIL). Throne: walked in with 0 deaths, see the Act 5 monsters below |
| `checks-20261028-193920-s2` | towns (stopped in Act 2) | Act 1: menus for Gheed d35/d44/d46, Akara d35/d44, Kashya d35/d45, Charsi d35/d06, Warriv d35/d36; Cain is not in town (he waits in Tristram until rescued: expected); waypoint panel opens. Act 2: Fara menu d35/d06 (Drognan answered the talk from 34 sub-tiles, too far for a menu; Greiz not loaded). Stopped after 60 min: every NPC not loaded costs up to 12 walks of 90 s (open: a faster search). No `BC_ASSERT`, 0 crash files (bug #360 not repeated) |
| `checks-20261028-210149-s2` (lane acts2) | travel23 (stopped) | Duriel is back at the lair's arrival in a new game and killed the character (no gear in the stage) before Tyrael; Jerhyn talked to in town: Talk only, quest 14 unchanged |
| `checks-20261028-215641-s2` (lane acts2) | travel23, mephisto | Tyrael talked to after the lair's Duriel (quest 14 bit 3); Jerhyn not reached. Mephisto -26,000 life then a death; the retry's "killed" was a unit out of reach (fixed). **Crash**: `enter nearest` with a dead character took the town portal (`BC_ASSERT hnd->IsValid()`, access violation `+0x3e15b0`): harness misuse, travel34 now runs only after Mephisto's death, alive, on his portal (342) |
| `checks-20261028-221201-s2` (lane acts2) | travel23 .. diablo | **travel23 PASS** (Tyrael, Jerhyn in the palace, Meshif line `0xd38` -> Kurast Docks). Mephisto: 5 deaths across the moat, no damage |
| `checks-20261028-223926-s2`, `checks-20261028-224757-s2` (lane acts2) | mephisto .. throne | Mephisto with a bow: no shots land; Chaos Sanctuary and throne: deaths on the walk in (now counted); see the per-act rows |

Per act (verdicts; "help" is the harness help above, never god mode or easykill):

| Act | Step | Verdict | Evidence |
|---|---|---|---|
| 1 | Andariel (Median: AI `Vampire`) killed with Attack, quest 6 reward bits | PASS (help: level 62, gear, travel) | `checks-20261028-170422-s2` |
| 1 | Rogue Encampment: Gheed, Akara, Kashya, Charsi, Warriv menus, waypoint panel (Cain only after Tristram) | PASS | `checks-20261028-193920-s2` |
| 1 | Warriv: Talk only before Andariel, travel line d36 after her death, travel to Lut Gholein | PASS | `checks-20261028-133014-s2`, `checks-20261028-170422-s2` |
| 2 | Lut Gholein loads, Warriv and Jerhyn menus | PASS | run 1 |
| 2 | Duriel (AI `Duriel`) killed, quest 14 bits | PASS (help: level 62, gear, travel) | `checks-20261028-171213-s2` |
| 2 | Horadric Staff cube recipe (`msf` + `vip` -> `hst`) | open; static: the recipe and items exist | tables |
| 2 | Tyrael (lair) and Jerhyn talks, Meshif's travel line to Act 3 | **PASS** (lane acts2; help: level, gear, travel): Duriel killed again in the lair (he is back in every new game), Tyrael talked to (quest 14 `0010010000000000` -> `0011010000000000`), Jerhyn talked to inside the palace (-> `0010110000000000`), then Meshif's menu gained line `0xd38` and took the character to Kurast Docks (75). Not a port bug: run `checks-20261028-191050-s2` had talked to neither (Tyrael was never found, Jerhyn was looked for outside the palace); Jerhyn alone does not move the quest (`checks-20261028-210149-s2`) | `checks-20261028-221201-s2` |
| 3 | Kurast Docks loads, Hratli and Meshif menus | PASS | run 1 |
| 3 | Khalim's Will recipe | open; static: recipe and items exist | tables |
| 3 | Mephisto (AI `Vampire`, life 56,440 at level 93's Normal) | **PASS on the player path** (lane acts4, `checks-20261029-072606-s1`: help level 80, stat and skill points, rings, travel; right clicks; quest 22 changed; with #395's fix, 25 frames/s through the fight). Earlier, **killed on the player path, row not yet PASS** (lane acts3, `checks-20261029-021145-s2`: Sorceress, 30 Frigid Sphere right clicks, 56,440 -> 0 in 89 s, 0 deaths; help: level 80, stat and skill points, rings; quest 22 bits set, seen at the next start; the row read quest 23 and had bug #394; the next try hung, bug #395). Lane acts2: never a hit-lock. The character stood idle (mode 1) at the Durance 3 arrival 50 from him: the cast path does not walk a melee attacker that far. With the walk up first the council (1208) was killed and Mephisto lost 26,000 of his 56,440 life (no healing back) before a death (`checks-20261028-215641-s2`); in the other runs he stays across the lava moat 6 from the character and no swing lands (5 deaths, `checks-20261028-221201-s2`). A bow through the same cast path mostly does not shoot ("mode now 1" at 17, 15 life taken, `checks-20261028-224757-s2`). Next: a ranged / spell character or the attack by click | `checks-20261028-215641-s2`, `checks-20261028-221201-s2`, `checks-20261028-224757-s2` |
| 3 | Mephisto's portal to Act 4 | **PASS once, not repeatable yet** (lane acts4): a background mouse click on the open portal took the character to the Pandemonium Fortress in `checks-20261029-055612-s4` (quest 22 done from the game before, Mephisto killed again); refused ("I can't", character in the portal) right after the first kill in `checks-20261029-053521-s4`, and the walk did not reach the portal in `checks-20261029-072606-s1` (bridge object 341 stayed in mode 0 in both). Open: whether Median's Mephisto (AI `Vampire`, not D2's Mephisto AI) raises the bridge in the game of his first death; compare with Median 2012 on 1.13c. Earlier, lane acts3: Mephisto killed by Frigid Sphere clicks (`checks-20261029-021145-s2`, help: level, stat and skill points, rings), no object 342 in the 12 s after; the stage now waits 30 s | `checks-20261029-021145-s2` |
| 4 | Pandemonium Fortress loads, Tyrael and Cain menus, waypoint panel | PASS | run 1 |
| 4 | Hellforge, seals, Diablo, Tyrael's travel to Act 5 | open (lane acts4): the seals were never open at first sight (lane acts3's reading was the mode after the click); every seal opens 0 -> 2 by a mouse click; the Grand Vizier's pack and Lord De Seis come from their seals; Diablo needs the three seal bosses dead, not reached yet (De Seis is cold immune and outlived the hunt, the Infector wing was skipped by the time budget: `checks-20261029-081719-s1`). Tyrael's Act 5 line needs quest 26 (Diablo) done: Talk only so far, as D2. Earlier, lane acts3 reached all five seals from the sanctuary's map spots and opened 395 and 396 by mouse click (0 -> 2, `checks-20261029-002644-s2`, `checks-20261029-021145-s2`); in `checks-20261029-025925-s2` all five were in mode 2 when first seen and Diablo (243) never came; Tyrael 367 shows d35 only. Earlier: the seals (objects 392-396) are in no room's preset list from the arrival (225 rooms, 23 entrance objects listed: the far rooms list theirs only once loaded). New stage step `acts_open_seals` walks inwards (new harness mode `presets rooms`), clicks each seal (packet 0x13) and fights its boss; not yet run to a seal: the character died 15 s after arriving with 9,815 life (`checks-20261028-223926-s2`), and with 19,580 the room-box middle came out at the arrival itself (`level 108` puts the character in the middle: `checks-20261028-224757-s2`). Next: walk outwards to the seal spots of the sanctuary's maps | `checks-20261028-223926-s2`, `checks-20261028-224757-s2` |
| 5 | Harrogath loads, Malah's menu, waypoint object | PASS | run 1 |
| 5 | Larzuk sockets, Anya's reward: all 111 class-item codes are "anya reward ammy" amulets (automagic 494) | open (static only) | misc.txt |
| 5 | Ancients altar: the three Ancients (540-542), quest 39 | PASS after bug #362 (help: level 92, gear, travel) | `checks-20261028-180749-s2` |
| 5 | Arreat Summit gateway to the Worldstone Keep | PASS (the first operate opens it, the next moves the character) | `checks-20261028-191050-s2` |
| 5 | Throne of Destruction waves, Baal (`baalcrab`, AI `Andariel`) | **open**: no wave yet. The "teleport to Harrogath" of `checks-20261028-191050-s2` was a death the stage did not count (19:33:11: life 0, mode 0 -> 17, revived in town; it was hitting a monster's Bone Wall, class 344, which Attack cannot hurt): the stage then waited 420 s in Harrogath. Now deaths count, walls are skipped, the stage clears the room (radius 45: D2's waves start when the throne room is empty) and passes only when a wave boss (1289, 1148, 803, 1290, 1281) shows. Lane acts2's runs died on the walk in (`checks-20261028-223926-s2`, `checks-20261028-224757-s2`, 19,580 life) | `checks-20261028-224757-s2` |
| all | Nightmare / Hell after Baal | open: not offered while Baal lives (correct), Baal not killed yet | `checks-20261028-180749-s2` |

Act 5 monsters seen (the coordinator's offset question, after bug #362): the altar summons exactly monstats 540, 541, 542 (the
three Ancients); in the Throne of Destruction the walk met 344 (bonewall), 994 (succubusclan5), 1211 (elite_undeadmage4),
1237 (elite_lightning4), 1607 (dragonknight3), 1623 (magmademonE): Median's own throne population. The wave superuniques are
built as 61-65 = classes 1289 (wimp_succubusclan), 1148 (hell_bane), 803 (hell_evilpriest), 1290 (wimp_killermoo), 1281
(crazy_tower), Nihlathak 60; not seen in game yet because the waves did not start. At the end of the throne stage the character
stood in Harrogath (Malah 513, injured barbarians 567-569 in reach): a death in the throne room the stage did not count (lane
acts2, see the Act 5 row).

Static checks of the same steps (built tables): every quest item of Acts 1-5 is there with its quest number and `questdiffcheck`; the
Horadric Staff, Khalim's Will and Cow portal recipes are enabled; the boss treasure classes `Andariel (D)` .. `Baal (D)` exist for all
three difficulties; the five towns carry waypoint numbers 0 / 9 / 18 / 27 / 30 as vanilla.

Lane acts2 (2026-10-28, slot 2, `ActsBarb`, background input, MXL_RUN=acts2): check `acts` changes (tools/game_checks.py,
unit tests tools/tests/test_game_checks_acts_walks.py): the Act 2 end talks (Tyrael 57 west / 130 north of Duriel's preset in
Median's duriel.ds1, after killing the lair's Duriel; Jerhyn at his palace placeholder, object 122, or where `moveto` sees him),
Meshif's map spot (5213, 5078), stuck walks turn through eight detour legs, melee bosses are walked up to (14), a unit that
vanishes with life left is no kill, up to 4 goes at a boss after deaths, deaths are counted in every stage, Bone Walls are not
fought, travel34 only after Mephisto's death (click packet 0x13 on portal 342, harness `enter` as the named fallback), the
seals step for Diablo, the throne stage clears the room and needs a wave boss. Towns: one sweep per town records every NPC
the walk passes (`state` mx / my) and each NPC is walked to straight (`place` when a town wall stops the walk), no exploring
per NPC (not yet timed in game). Harness: `presets rooms` (each DRLG room's origin, read-only). Help named in the rows:
level, travel, gear; the given ring now has 60 vitality and 5 replenish life per level.

Lane acts3 (2026-10-29, slot 2, new character `ActsSorc`, `MXL_CHAR_CLASS=sorceress`, background input, MXL_RUN=acts3): a real
spell build instead of more gear. Set-up help named in every row: level by `xp` (the game's award), the level's stat points spent
by the stat packet 0x3a (Energy to 250, the rest Vitality), skill points by `setskill` (Frigid Sphere 530 and Tempest 535 at the
top with their prerequisites; the game refused levels above 524:14, 530:14, 535:13, 536:12, 17 points stay unspent), the ring of
`acts_gear` and a ring with 300 % mana regeneration, no weapon. Damage comes only from right clicks with the build's skills on the
monster's spot (background mouse, `click_unit`). New: stage `build` (asked only), boss focus (walk up without stopping for
minions, clear the monster in the way when a walk is refused), the Chaos Sanctuary seal walk from the sanctuary's map
(`SEAL_ROUTES`, `SEAL_WINGS`: star 7793, 5293; seals 392/393 east, 394 north, 395/396 west), seal clicks at the foot and higher,
back along the route after each wing, `fight_all` skips a monster it cannot reach. Runs:

| Run | Stages | Result |
|---|---|---|
| `checks-20261028-232048-s2` | build (level 80) | INFO: 395 stat points (Energy +215, Vitality +180), 62 skill points; Frigid Sphere about 5,573 life a click on a zombie, Tempest 587; mana stayed 2,187 (owner question), max life 12,721 |
| `checks-20261028-232449-s2` | mephisto .. travel45 | Mephisto 56,440 -> 47,635 (the walk with fighting spent the time on the council). Diablo: no unit. travel45: Tyrael 367 shows d35 only |
| `checks-20261028-233533-s2`, `checks-20261029-002644-s2`, `checks-20261029-010614-s2`, `checks-20261029-013841-s2` | mephisto .. travel45 | Mephisto: 0 clicks, the character never left the Durance 3 arrival (every walk refused, a monster next to it: fixed by clearing it). Seals: 392, 393, 395, 396 to mode 2 (396 and 395 by the mouse click on the seal, 0 -> 2), the walk out of the Vizier wing stuck (fixed: back along the route) |
| `checks-20261029-021145-s2` | mephisto, travel34, diablo | **Mephisto killed by the player path**: 30 Frigid Sphere right clicks, 56,440 -> 0 in 89 s, 0 deaths (help: level 80, stat and skill points, rings). The row said FAIL: it read quest 23 (now 22, see below) and bug #394 came in the fight. travel34: no object 342 in the 29 loaded objects 12 s after the kill (the stage now waits 30 s). Seal 395 0 -> 2 by click |
| `checks-20261029-023803-s2` | mephisto | quest 22 at the start `1000000000010000` (set by the kill of the run before). Mephisto 56,440 -> 16,305, 2 deaths, then bug #395 (game hung, 11 GB). Stopped |
| `checks-20261029-025925-s2` | diablo, travel45 | all five seals reached (395, 396 west, 394 north at 7773, 5155, 392, 393 east) and the walk back between wings worked, but all five were in mode 2 the first time they were seen: nothing to click, Diablo (243) never came. travel45: Tyrael d35 only |
| `checks-20261029-035647-s4` | towns (stopped after Act 1) | **towns timed once**: the Act 1 town alone took 16 min 14 s (03:57:30 -> 04:13:44) and said FAIL: no NPC menu at all (cain1, gheed, akara, kashya, charsi, warriv1; 15 `interact`, 135 `menu list` "no NPC menu is open", 35 `moveto` refused); the new level 1 character walked out into the Blood Moor and died there once. Stopped to free the slot. The stage gives no level, so a fresh character is at risk outside the town |
| `checks-20261029-041546-s4` | throne, baal, nightmare | throne FAIL: the walk did not reach the throne (no throne preset), 1 death, classes 811, 994, 1013, 1211, 1238, 1607, 1742, 1743 met; no wave boss. Baal (544, life 124,600): 71 Frigid Sphere clicks but no life taken in 712 s, 1 death; the character stayed about 38 from him. nightmare FAIL (Baal alive, quest 40 `0000000000000000`) |

Lane acts4 (2026-10-29, background input, MXL_RUN=acts4, new Sorceresses `ActsSorcD` (slot 4) and `ActsSorcE` (slot 1), each set up
by stage `build` at level 80 as lane acts3's (SET-UP named in every row: level by `xp`, stat points by packet 0x3a, skill points by
`setskill`, the two given rings and amulet, no weapon; travel to each level by `level`); the judged actions are right clicks with the
build's skills and left clicks on objects). Findings: (1) lane acts3's "all five seals open at first sight" (`checks-20261029-025925-s2`)
was a misreading: its first `objects` lists show every seal in mode 0, and the row's mode 2 is the mode after the click (395, 396:
`mouse click (0 px above its foot)`). What kept Diablo away: the pack fight after each seal skipped the Infector of Souls' unit 107
(class 1763) that took no damage; D2 calls Diablo only when the three seal bosses are dead too. The stage now hunts each wing's boss
class (superuniques by name: Grand Vizier of Chaos 1698, Lord De Seis 1699, Infector of Souls 1763; boss and pack share the class)
before leaving the wing and waits up to 60 s at the pentagram. (2) Mephisto's portal (object 342) is a map object in mode 2 next to
the bridge object 341; in run 1 the click packet 0x13 alone got "I can't" and the harness `enter` on it ran a level change to dest 0
(`BC_VERIFY ptDrlgLevel->ptRoomFirst`, Drlg.cpp:882, the same second: harness misuse, `enter` removed); in run 2 a background
mouse click on it took the character to Act 4 with no quest set-up. Why the first try was refused is not known (packet only, or the
first game after the kill). (3) Tyrael's Act 5 line: Tyrael (367) shows Talk (d35) only while quest 26 is not done (as D2: his
travel line comes with Diablo's death); every earlier travel45 try had no Diablo kill.

| Run | Stages | Result |
|---|---|---|
| `checks-20261029-053521-s4` (slot 4, ActsSorcD) | build, mephisto, travel34 | build INFO as lane acts3. **Mephisto killed on the player path**: 52 Frigid Sphere + 31 Tempest right clicks, 56,440 -> 0 in 326 s, 1 death, quest 22 `0000000000000000` -> `1000000001010100`; row FAIL only for `BC_ASSERT: ptCreate->hSource` (Missiles.cpp:202) at 05:40:55 in the fight: bug #394 seen a second time. travel34 FAIL: portal 342 found open (mode 2), the click packet got "I can't" (`acts_travel34.png`), then the harness `enter` assert above |
| `checks-20261029-055612-s4` (slot 4, ActsSorcD) | mephisto, travel34 (diablo cut) | Mephisto killed again in 115 s, 45 Frigid Sphere clicks, 0 deaths, no assert; row FAIL only because quest 22 was already done (`1000000001010000` both). **travel34 PASS**: a background left click on the open portal took the character to the Pandemonium Fortress (103); the screenshot is the act's entry cinematic. The diablo stage was cut by the lane's own shell timeout |
| `checks-20261029-060640-s4` (slot 4, ActsSorcD) | diablo (stopped) | Vizier wing: seals 395 and 396 0 -> 2 by mouse click, the Grand Vizier and his pack (class 1698, units 29-34+) hunted to none; then the walk to the north wing pinned the character against the cathedral wall west of the heart (7724, 5267, `acts4_stuck.png`) for 19 minutes, every `place` to the east wing refused (rooms not loaded). Stopped by the lane. Now: a leg that fails is placed back at the pentagram first, and the seal walk has a 30 minute budget |
| `checks-20261029-072606-s1` (slot 1, new ActsSorcE, same set-up, build of main 086b021 with the #395 fix) | build, mephisto, travel34, diablo, travel45 | **Mephisto PASS on the player path**: 79 Frigid Sphere + 2 Tempest right clicks, 56,440 -> 0 in 321 s, 1 death, quest 22 `0000000000000000` -> `1000000001010100`, 0 engine asserts. #395 load over the 327 s fight: 25.0 frames/s median (min 23.7), missile ids 418/s median (max 1,081), live server missiles 230 median (max 696), private 9,553 -> 9,745 MB (max 9,890), no hang. travel34 FAIL: the walk stopped on a pillar away from the open portal (its glow at the screen's bottom edge, `acts_travel34.png`), no click landed, the quest set-ups (6 / 14, then 7 / 15, then 23 bit 0) changed nothing; bridge object 341 in mode 0. diablo FAIL: the pentagram fallback got the walk to all three wings; seals 396, 395, 393, 392 0 -> 2; seal 394 was counted "opened" because it was not listed after the click packet (no mode read as a change: fixed, seals are now read by class and spot, the unit id changes when a room reloads) and De Seis (1699) never came. travel45 FAIL: Tyrael d35 only, quest 26 `0000000000000000` |
| `checks-20261029-081719-s1` (slot 1, ActsSorcE) | mephisto, travel34, diablo, travel45 | Mephisto not killed in 604 s (75 Frigid Sphere + 13 Tempest clicks, 0 deaths; quest 22 already done). #395 load over 589 s: 24.9 frames/s median (min 22.8), missile ids 349/s median (max 826), live server missiles 229 median (max 1,038), private 9,139 -> 10,474 MB (grew 1.3 GB in the fight), no hang. travel34 BLOCKED (no kill). diablo FAIL: seals 396, 395 and 394 0 -> 2 by mouse click; the Grand Vizier's pack (1698) killed; **Lord De Seis (1699) came for the first time** but stayed alive (cold immune: Tempest only, about 500 a click); the 30 minute walk budget then skipped the Infector wing (392 / 393), so Diablo's condition was not met. Now: 60 minute budget, 10 minutes per seal boss. travel45 FAIL (quest 26 not done). 0 asserts, 0 crash files |

Lane acts5 (2026-10-29, slot 2, background input, MXL_RUN=acts5, Sorceress `ActsSorcF` set up by stage `build` at level 80 as
lane acts4's: level by `xp`, stat points by packet 0x3a, skill points by `setskill`, two rings and an amulet, no weapon; travel to
each level by `level`). Lord De Seis needs no extra help: the build's Arcane Torrent (right clicks, the
build's pick for his class) killed him in `checks-20261029-124850-s2`. Findings: (1) the Chaos Sanctum still gives no Diablo on this path. In
`checks-20261029-124850-s2` all five seals were opened by mouse clicks, the Grand Vizier and Lord De Seis were killed and five
Infector-of-Souls-class units died, but the walk back to the pentagram stuck at about 7812,5201 (north wing) and no class 243
appeared; later runs lost the Infector's wing to walks pinned at 7804-7819,5223-5260 (`checks-20261029-135438-s2`) and in a pocket
west of the heart at 7716-7739,5255-5320 (`checks-20261029-150343-s2`). The route through wingn1's west opening and a search walk
over the walked links were added for this; no Diablo kill, so quest 26 stayed `0001000000000000` and travel45 kept Tyrael (367) on
Talk (d35) only. (2) Glacial Trail (bugs #494, #495): new check `glacial` (warps found by the IceCaveTorch1 pair beside each warp,
`presets 2`, because `tiles` reads nothing in this build, bug #399). (3) Harness: `place` now reads the position back (bug #438);
`tiles` skips unreadable units; new verb `hashscan`. Bug #394's assert (`ptCreate->hSource`, Missiles.cpp:202) was seen in
`checks-20261029-093507-s2`, `checks-20261029-124850-s2` and `checks-20261029-135438-s2`, not after main's fix was merged
(`checks-20261029-150343-s2`). Not run in this lane: throne/baal (routes written, `THRONE_ROUTE`, `BAAL_ROUTE`) and Mephisto's
bridge with `acts_raise_bridge`. Lane endgame: the cause was the walk (Diablo spawns when the star's room is loaded, 1.13c's
rule); Diablo killed, Act 5 by Tyrael's red portal (section "Lane endgame").

| Run | Stages | Result |
|---|---|---|
| `checks-20261029-124850-s2` | diablo, travel45 | diablo FAIL: seals 392-396 0 -> 2 by mouse click, Vizier and De Seis killed, 0 deaths, 5 legs by `place`; no Diablo (the walk back stuck); #394 assert. travel45 FAIL (d35 only) |
| `checks-20261029-135438-s2` | diablo, travel45 | diablo FAIL: 395, 396, 394 opened by click on the new north route (walked, no `place`); 392 not reached; #394 assert. travel45 FAIL |
| `checks-20261029-150343-s2` (main's #394 fix merged) | diablo, travel45 | diablo FAIL: only 395, 396 opened, the Vizier's pack killed, then 50 min pinned west of the heart; no #394 assert. travel45 FAIL |
| `checks-20261029-173931-s2` | glacial (HD) | **115 -> 117 entered by a real left click** after a walk up (screenshot "Entering The Frozen Tundra"); 115 -> 116 by click too; 113 -> 115 not found in 25 min of walking (control) |
| `checks-20261029-183847-s2` | glacial (HD, legacy) | HD FAIL: the walk ended in a pocket below the exit's ledge, clicks from there do nothing. Legacy: 117 entered twice by clicks (first entry, round 1), round 2 the pocket again |
| `checks-20261029-194645-s2` | glacial (HD, legacy) | HD: 117 entered by 4 clicks, round 1 the pocket (`place` refused, its room not active). **Legacy PASS**: first entry and 3 of 3 rounds (waypoint, fight walk, walk up, 1-4 clicks). No crash or error line in any glacial run |

Lane mercs (2026-10-28): the v005 hireling table labels its third skill growth field `LvlPerLvl8`; migration now maps it to D2R's `LvlPerLvl3` in both banks. The 24 Desert Mercenary rows with growth 8 must retain it. Player-path checks remain pending: with a mortal character, hire in acts 1, 2, 3 and 5, equip helm, armor and permitted weapons by click, fight, observe a death, revive and level; exercise buying, selling and gambling in each act, repair and quest services, identify and stash. Inspect both HD and classic mercenary panels and test permitted and refused equipment types. No game result is claimed by this entry.

Slot 2 startup smoke (lane mercs, 2026-10-28, `checks-20261028-122430-s2`): `game_checks.py all mxl2012` PASS with a new level 1 Barbarian, no new crash or engine assert, background input only. This checks startup and plugin loading, not mercenaries or town services. Shared slot files restored and verified after the run.

### Check `mercs` (lane mercs2, 2026-10-28)

`MXL_RUN=mercs2 MXL_SLOT=N MXL_CHAR=Mercsbarb py -3 tools/game_checks.py all mercs`; `MXL_MERCS_PARTS` (hire, equip, fight, death,
revive, reload, vendors) and `MXL_MERCS_ACTS` split it into launches of under ten minutes. Mortal character, no god mode; the
judged actions are the player's: the NPC click (`interact`, packet 0x2f), the menu line's own client handler, the hire list's
button (packet 0x36), real background clicks on the backpack, the hireling panel and the vendor grid. Fixtures, named in the
verdict: gold set before each payment, the Kashya (quest 2) and Qual-Kehk (quest 36) hire gates set as quest bits, the backpack
cleared and the test items made in it, spawned monsters, harness kills of the spawned monsters after each step, an NPC copy
spawned next to the player when the real NPC cannot be reached.

| Part | Run | Result |
|---|---|---|
| Hire in Acts 1, 2, 3, 5 | slot 3 `checks-20261028-180755-s3`, `-181204-s3` | PASS: Rogue 271 (262 gold), Desert Mercenary 338 (350), Iron Wolf 359 (1000), Barbarian 561 (9000); paid = the price shown |
| Equip by click, allowed and refused | same | PASS, 1.13c's types (bug #290): every class wore Cap and Quilted Armor; Rogue bow yes, sword / crossbow no; Desert polearm / spear yes, bow / sword no; Iron Wolf sword / shield yes, bow / spear no; Barbarian sword yes, axe / shield / Barbarian helm no |
| Fight, level-up | `-180755-s3` | PASS: 4 zombies killed by the Rogue in 4 s; mercenary 8 -> 9 from the player's kills in Black Marsh |
| Death, revive and pay | `-180755-s3` | PASS: killed by the spawned monsters in 7 s; revived at Kashya's menu, paid 600 at level 9 = 1.13c (level² / 2 × 15) |
| Save and Exit + Play | `-181204-s3` | PASS: Barbarian level 9 with Scimitar, Quilted Armor, Cap before and after |
| Vendors | slot 4 `checks-20261028-183503-s4`, `-184504-s4`, `-184741-s4` | Buy by right click and sell back PASS at Charsi, Fara, Hratli, Halbu, Larzuk; gamble PASS at Gheed, Alkor, Jamella. Not covered: Elzix (not reachable from the arrival point, no copy could be placed) and Anya (in town only after her quest; at a spawned copy the gamble clicks buy nothing, as at the copies of Alkor and Elzix in earlier runs) |

Engine asserts: none in the runs above; a vendor run on slot 3 (`checks-20261028-181830-s3`) had the known AssetCache.h:187 (bug
#72). Two earlier runs died after the harness travel to Bloody Foothills with a live mercenary (bug #292). Check fixes found on
the way: the vendor grid is 41 px cells from y 183 at 1600 × 900; `kill nearest` without a class also kills the mercenary.

No raw text (lane text, data + tools, no version change; rebuild with `tools/build.py` and install): names in words, the stat lines, the inventory, cube and classic skill tree layouts without `@key`s (docs/text-audit.md). `py -3 tools/game_checks.py all textnames` (slot lock first; the screenshots are read by hand) already showed, on slot 2: Crystal Ball, Glass Skull, Couatl Inhibitor, Landshark Inhibitor, Bone Prison, Healing Potion, Small Red Potion and the two Greater Elixir lines. Still to look at: hover a Bunny and an Injured Barbarian (Act 5), the Crusader Spirit pet (a Paladin with Summon Crusader Spirit), the inventory's Close and Drop Gold buttons, the cube's Close and Transmute buttons, the Warlock tab titles in the classic skill tree (G, Warlock). Expected: "Close", "Drop Gold", "Transmute", tab titles Demon / Eldritch / Chaos, no "Missing string" anywhere.

Damage / IED audit: `game_checks.py all ied iedtip --slot 3`, and the same
with `MXL_CONTROL=innate`. Set `MXL_CHAR` to the lane's own throwaway; an
explicit name is entered or created, never replaced by the selected card.
`ied` grants the hidden passive using equipped stat=value pairs, checks
the data formula, spends a real Dexterity point, and applies native weapon
hits to a zero-resistance monster at SrcDam 128 and 64. `iedtip` checks the
client formatter with explicitly set and restored client inputs. Harness verbs `passiverefresh` and
`weaponhit mon:<id> [SrcDam]` expose the native passive refresh and weapon
build/hit/apply pipeline; `passivestate [arr|dump|watch|awatch]` reads the state list of the innate passive (skill 2072) and
`passivetrace on|clear|show [n]` records every passive apply / refresh with its inputs and call chain (lane ied-vanish); `weaponhit` reports raw damage fields (1/256 life)
and whole life lost. See damage-ied-audit.md.

Use test-sessions.md to run these checks by character.

| Since | What | How to test | Expected |
|---|---|---|---|
| 0.69.15 (lane equip-crash) | **Circlet crash on pickup / wear, bugs #49 (Tiara) and #55 (Coronet)**: D2R's fixed item type ids moved to Median's (plugin/src/item_type_ids.cpp, off word `typeids`; tools/item_type_ids.py) | `MXL_SLOT=<n> MXL_RUN=<lock> MXL_CHAR=<throwaway> py -3 tools/game_checks.py all mxl typeids equipall` with `MXL_EQUIP_MODE=ground MXL_EQUIP_ONLY=<circlet codes> MXL_EQUIP_QUALS=3,4` (pick up from the ground to the cursor and wear; and with the inventory flag, which puts the item on at once when the head is empty) or `MXL_EQUIP_MODE=packet` (every head base and unique by 0x19 / 0x1a); `MXL_GRAPHICS=legacy`, `MXL_CHAR_CLASS=<class>` for a new character of another class. By hand: pick up and wear a Tiara / Coronet; socket a rune into a circlet; drink a mana potion from the belt | `mxl`: `item type ids on: 25 of 25 ...`; `typeids` PASS (a Thul rune goes into a circlet's socket, the circlet is worn); `equipall` PASS, the game survives every item (another class's helms are refused as expected). Control (`typeids` in mxl2012-core-off.txt): wearing or picking up a circlet asserts `UnitGetType(hUnit) == UNIT_ITEM` (ItemMode.cpp:676) and the game dies or hangs. Run on slot 2 with the dev and the release install (Barbarian HD, Sorceress legacy). |
| 0.69.9 (lane goblin-crash) | **Den boss / goblin sound crash, bugs #42 / #46** (plugin/src/sound_guard.cpp, off word `soundguard`; tools/txt_migrate.py hit-6 spawns; tools/validate.py `hit6_spawns`; check `denboss` now mortal) | `MXL_SLOT=3 MXL_RUN=<lock> MXL_CHAR=<throwaway> py -3 tools/game_checks.py all mxl goblincrash denboss` (`MXL_DENBOSS_GOD=1` adds god-mode soak rounds; `MXL_SOUNDGUARD_TEST=1` on a dev DLL feeds the goblins' Neutral sound as -1, =2 reproduces the crash) | PASS: `goblincrash` shows `sound guard: 0 bad sound ids skipped`; `denboss` fights the boss mortal in HD and legacy (cold resist as is, 0, -100), the bone spear spawns 2835 (never 2818), the player lives, no crash file. Tell me: whether Median monster sounds play (goblin chatter) and your d2rloader.log `Loading sound data tables` lines |
| 0.69.9 (lane goblin-crash) | **Treasure goblin crash, bug #46** (check `goblincrash`, tools/game_checks.py; plugin/src/goblins.cpp: monstats row check before the spawn, `goblin <id> rolled ... spawning` log line before the spawn call) | `MXL_SLOT=3 MXL_RUN=<lock> MXL_GOBLINS_FORCE=1 py -3 tools/game_checks.py all mxl goblincrash` on a developer install and on a release install (downloader `--cli install`, `launch_arguments` without `-txt`, save folder `mxl2012-sN/`, dev DLL swapped in) | PASS: in HD and legacy six goblin types spawn, run 20 s, cast their curse (2580) and Submerge (2582), die, and the plugin roll spawns one; no crash file, no new assert, `0 without a monstats row`. Tell me: on your install, the last mxl2012-core.log lines before any goblin crash |
| 0.69.8 (lane env-guard) | **Which build runs, bug #53** (plugin/src/env_guard_logic.h, off word `envguard`; check `envguard`), and the mod toml's `[d2rloader.advanced] suppress_global_extensions = true` (tools/install_mod.py) | `MXL_SLOT=<n> MXL_RUN=<lock> MXL_CHAR=<throwaway> py -3 tools/game_checks.py all mxl envguard otherplugins`; to see the warning: copy the dev mxl2012-core.dll into `<slot D2R>\d2rloader\plugins` (with and without suppress_global_extensions), start, run `mxl` | normal slot: first `mxl` line ends `| mod D2R-XL 2012 | file <slot>\mods\mxl2012\d2rloader\plugins\mxl2012-core.dll`, `environment ok`. With the global copy and suppress on: d2rloader.log loads no global plugin, `environment ok`. With suppress off: about 15 s after the start mxl2012-core.log has `environment WARNING: ... a second copy ...` and the red line shows at the top. **Not run yet** (slots 2 and 3 were busy). |
| 0.69.6 (lane den-crash) | **Den of Evil boss, bug #42** (check `denboss`, tools/game_checks.py) and the **other plugins line** (bug #44; plugin/src/other_plugins_logic.h, off word `otherplugins`) | `MXL_SLOT=3 MXL_RUN=<lock> MXL_CHAR=<throwaway> py -3 tools/game_checks.py all denboss otherplugins` (`MXL_DENBOSS_SECS` fight seconds per graphics mode, default 30; `MXL_DENBOSS_SEARCH` seconds of crawling for the Den's own superunique, default 30) | `denboss`: HD round and legacy round (G pressed in the town), boss class 2833 with its party fights, casts SkeletonRaise, is killed; no crash file, no new assert. PASS `checks-20261027-122930-s3`, `checks-20261027-123712-s3`, `checks-20261027-125047-s3`. `otherplugins`: `mxl` has `other plugins: none` on a test slot; mxl2012-core.log has the line ~15 s after the start |
| lane pub-release (version not bumped; `mxl` first line now ends the version with `(dev)` or `(release)`) | **Player release package and wrong-build guard** (tools/package_release.py, docs/release.md; cmake `-DMXL_RELEASE=ON` compiles the test harness out; plugin/src/build_guard_logic.h) | `py -3 tools/package_release.py` after tools/build.py: dist/ gets the 7z (no zip since 2026-10-26), release-manifest.json, notes and SHA256SUMS. The release DLL cannot run on slots 2/3 (no harness, no `volserial`): test its folder with the dev DLL swapped in (`game_checks.py --slot 3 all mxl`). Wrong build: unit test `buildguard_tests` (no other D2R build installed) | Zip without harness / off / save files; `mxl` PASS on the release folder. On another D2R build the log has `D2R-XL 2012 <v> needs D2R build 93847; this is <n>`, the same line is drawn at the top of the screen and no hook goes in |
| lane p4-ww-morph (plugin 0.63.0; run `mxl` and read the `whirlwind procs` line, `on: chance to cast on striking / on attack works during a spin (0x5896e0 hooked) (N casts let through during a spin, M refused)`; off word `wwproc`) | **Whirlwind chance-to-cast, real shapeshift death** (`whirlwind.cpp`, `tools/game_checks.py`) | Barbarian: wear a ring with chance to cast Fire Bolt on striking or on attack and spin through a pack with Median's Whirlwind (skill 1306): Fire Bolts appear, as with normal attacks. Druid: wear an axe, cast Werebear (1375), let a monster kill you: you die, the form ends, Esc respawns you in town. | No automatic checks needed: `py -3 tools/game_checks.py --slot N all wwproc morphdeath` is PASS (see "Lane p4-ww-morph" below) |
| lane p4-quests-verify (plugin 0.62.0; run `mxl` and read the dungeon lockout line, `... Worldstone / Throne objects both ways, ... Worldstone / Throne warps N`; off word `worldstone`) | **Quest and object verification, Worldstone / Throne object function 70** (`dungeon_lockout.cpp` `ThroneHook`; harness verbs `objmode`, `questobj <id> poke <offset> <byte>`, `missile <row> dx dy skill level`, `dump ground nogold`) | `py -3 tools/game_checks.py --slot N all towerkill lockwarp tyraelwalk worldstone hitfloor strdex itemevents` (background mode; controls: `MXL_CONTROL=quests` towerkill, `lockout` lockwarp, `worldstone` worldstone, `hitfloor` hitfloor). By hand: `h object 569`, `h objmode <id> 2`, `h operate <id> 70` in area 131 with `h questobj 36 poke 166 1` | PASS, run `checks-20261023-234713-s3`; see the rows of docs/unported.md (quest 5 guard, lockout quest condition, Tyrael, item events, quest rewards, D2 bugfix leftovers, hit 20 floor, Gidbinn / Worldstone) |
| lane p4-leftovers (plugin 0.61.0; run `mxl` and read the `soulstealer` line, `on: 34 Soulstealer monsters heal 1/10 of max life when they kill a player ..., heals N, player deaths N (last killer: ...)`; off word `soulstealer`) | **Soulstealer heal, drop item level reader, hire robustness** (`no_corpse.cpp`, `harness_cmds.cpp`, `item_gen.cpp`, `tools/game_checks.py`) | Let a Soulstealer boss (Zagraal, Kabraxis) kill your character in the field: the boss gains a tenth of its max life, an ordinary monster gains nothing. Drops of monsters take the level of the area. | No automatic checks needed: `py -3 tools/game_checks.py --slot N all soulstealer dropilvl classlock` is PASS (see "Lane p4-leftovers" below) |
| lane p4-verify-a (version not bumped; run `mxl` and read the `act 2-5 quests`, `stat rules` and `craft flags` lines; off words `respecbuffs statclick`) | **Phase 4 verification: reset removes buffs (DC7), stat point shift-click (XP6), Cow portal in any town (CR6), Grit follows Strength (XP9)** (plugin/src/quests_act2_5.cpp `ClearTimedBuffs`, stat_rules.cpp `StatClickHook`, item_spells.cpp `CubeCowPortal`, craft_flags.cpp `PortalHook` and the act compare patch `0x432dd5`, dungeon_lockout.cpp cross-act portals by travel `0x4f2e40`; new harness verb `gameflag`, `enter` prints the refusal reasons; docs/unported.md) | `py -3 tools/game_checks.py --slot N all respecbuffs signet dropilvl cubehotkey cowtowns freerespec grit statclick mapreveal` (background mode). `mxl`: `act 2-5 quests ... respec clears buffs`, `shift-click on (25 points...)`, `craft flags ... portals cross acts | Cow portals outside act 1: N opened, M refused`, `dungeon lockout ... portals taken across acts N`. By hand: buff yourself, reset at Akara (the buffs go); shift-click a stat (25 points); put Wirt's Leg in the cube in Lut Gholein (a red portal to the Cow Level appears, once per game) | buffs off after the reset; 25 points per shift-click, 1 per click; the Cow portal opens in every town, can be walked into (Hell, character level 110, Median's table) and its own portal leads back to that town; Grit grows with Strength when the class passive is applied and when a Strength point is spent. The harness verb `gameflag <word> <bit> [get\|set\|clear]` reads and writes D2R's own game flags (the Cow portal's once-per-game flag is word 4 bit 11). Results and run folders: docs/unported.md rows DC7, GS10, CR5, XP6, XP7, MU2 |
| lane new-asset-paths (data only, no version change; rebuild with tools/build.py and install) | **Assets at new paths: the Wereowl units' models and textures at `data/hd/character/mxl/`** (tools/wereowl_models.py `place` / `index_new_paths`, tools/model_lod_desc.py: entries added to `data/hd/model_lod_desc.bin` and `texture_desc_cache.json` in the mod folder; docs/hd-models.md section 3c; `MXL_OLD_PATHS=1` builds the old override of the vanilla `horse` / `wargoatman` paths) | `py -3 tools/game_checks.py --slot N all assetpaths` (background mode; verified on slot 1; with the original `model_lod_desc.bin` the check fails: the unit is not drawn). By hand: `cheat mspawn wereowl`, `cheat mspawn corrupted_wereowl`, or cast the Druid's Wereowl skill | The Druid's Wereowl form and the Corrupted Wereowl are drawn (textured, animated with the werebear / goatman animations); `d2rloader.log` has no `model_asset.cpp` assertion. Not tested: other Median monsters at new paths (the recipe is the same), a new path for a unit with fewer than 5 LODs |
| lane p4-engine-b (version not bumped; run `mxl` and read the `vendorstock` line, `on: no extra magic copies above item level 24 (0x53cd2b patched), Nightmare item level cap (0x53cfa0 hooked)`; off word `vendorstock`) | **Vendor stock rules** (docs/vendors.md; `txt_migrate.py` MagicLvl 0, `waypoints_data.py` actinfo `maxnpcitemlevel`, plugin `vendor_stock.cpp`), the curse client function wrapper (no nMissile assert), the area aura radius guard (no nRadius assert), srvdofunc 41 / 73 wrappers, the cherry (item spell 17) with its lockout clock, the waypoint-open sound (message 0x70) | Game checks `vendorstock` (Charsi in all three difficulties at levels 10 / 40 / 90: builder item level 20 / 68 / none, at most 3 magic copies, magic stock at level 10), `cursemissile`, `asserttrace`, `replacedskills`, `cherry`, `warprevisit`, `wpauto` (step D) | Run folders in docs/unported.md rows 34, 62, 211, 212, 220; the vendor control is the same check before the changes (Normal cap 12, Nightmare 95 uncapped, 5 copies of one magic item, no magic stock at level 10) |
| lane carry1-fix (plugin 0.66.0; run `mxl` and read the `unique carry` line, `on: each carry1 unique gets its own carry number (row + 1) after the table load (loads 1, carry1 uniques 178, rewritten 178)`; off word `uniquecarry`) | **Different carry1 uniques (the 40 charm uniques, Butcher's Tooth to Elder Vial) can be carried together; a second copy of the same one is still refused** (plugin/src/unique_carry.cpp, unique_carry_logic.h) | `py -3 tools/game_checks.py --slot N all mxl charmlimit uniquelimits` (background mode; `MXL_CONTROL=uniquecarry` for the control). By hand: `h item a60 uniq=18 inv`, `h item a59 uniq=19 inv`, `h item a55 uniq=21 inv` (three different carry1 uniques in one backpack), then a second `h item a60 uniq=18 inv` (refused) | The three different uniques are placed, the second Butcher's Tooth is refused (`item: placing failed`); with `uniquecarry` in mxl2012-core-off.txt the second different one is refused again | Cause: D2R 3.3 reads carry1 as a number (unique record +0x30) and refuses a unique when a carried one has the same non-zero number; Median has 1 in all 89 carry1 rows (docs/d2r-addresses.md section 22b) |
| lane unique-limits (version not bumped; run `mxl` and read the `unique limits` line, `on, 334 limited uniques; moves into the backpack N (limited L, refused R)`; off word `uniquelimits`) | **Median's unique carry limits: at most 3 relics of a group, single-copy uniques, no second copy of the same unique in a group** (plugin/src/unique_limits.cpp: hooks the item move `0x471e90` and the ground pickup `0x471950`; data tools/unique_limits_data.py -> mxl_unique_limits.h; text: Median string 12109) | `py -3 tools/game_checks.py --slot N all uniquelimits` (background mode; verified on slot 2, see docs/unported.md). By hand: carry three relics of one kind (e.g. three Cotw uniques of the limit group 1), walk over a fourth lying on the ground, take a fourth out of the Horadric Cube or the stash onto the cursor and drop it into the backpack; pick up a single-copy item (e.g. the Sunstone of the Twin Seas) twice; put an item of the group in the stash first and check it can be taken back only while the count allows | The fourth relic stays on the ground / cursor and a system line says "You can only carry one Relic" (Median's one text for every limit); uniques without a limit and items in the stash / cube / belt / worn are not counted; a pickup to the cursor is not blocked, only the drop into the backpack. Not seen by hand: a real walk-over pickup, a cube recipe output landing in a full backpack, the message in the log |
| lane orb-tooltips (data only, no version change; rebuild with tools/build.py and install) | **Mystic orb tooltips** (tools/orb_tips.py, txt_migrate `orb_tooltips`: each of the 101 orbs has its own spelldescstr `mxl2012:mxlorb_<row>`) | Spawn orbs (`h item <code> inv`, e.g. `46+`, `63+`, `&68`, `mo01`) or buy some, open the inventory, hover them | Each tooltip lists the old text, "Limit per item: N", "+N Required Level", the orb's properties and the target type, e.g. Heart of Frost: Ring, Amulet or Quiver Only / Weapon Physical Damage +9% / +5% to Cold Skill Damage / 2% Chance to cast level 40 Ice Bolt Nova on Melee Attack / +10 Required Level / Limit per item: 2 / Right-Click to Apply. Game check `orbtips` ran on slot 2 (REVIEW: screenshots read by hand) |
| lane pa2-stats (version not bumped; run `mxl` and read the `stat rules` line, `ok: potion amounts on (...), stamina on (0x42e850)`; off words `potionamounts stamina manaregen`) | **Potion of Life +50 life, Lam Esen's Tome 10 stat points, Median's stamina and mana recovery, get-hit durability** (plugin/src/stat_rules.cpp, stat_rules_logic.h, heat.cpp; audit items 11, 12, 15) | `py -3 tools/game_checks.py --slot N all potionamounts manarules nodurability heat townmana sprint` (background mode). By hand: drink a Potion of Life (max life +50, was +20), read Lam Esen's Tome (10 free stat points, was 5); walk with the stamina bar empty (it refills 3/4 as fast as standing); stand next to a Stamina Shrine's effect or use `h setstate player 136 1` (the bar fills at once); get hit by monsters with worn armour (durability stays) | Potion +50 life, Tome +10 points; stamina standing max / 256 raw per frame, walking 75% of that, running 0; state 136 fills the bar; a mana pool smaller than the regeneration frame count does not refill; a run in a town costs no stamina; armour and weapon keep their durability when hit. Not seen by hand: the real item use, a real shrine |
| lane tooltip-verify (version not bumped; run `mxl` and read the `item text` and `tooltip probe` lines; off words `itemtext tooltipprobe`) | **Item property text** (descfunc 32-38, class lock stat 492, `_mxl` string aliases; plugin/src/item_text.cpp; docs/item-tooltips.md) | Hover a unique with honorific / cooldown / innate damage / reanimate / life regeneration lines (e.g. unique relic `cotw` for the class line), a rare ring and a rare amulet | `+12% Enhanced Defense` style lines with the number once and no `%d` / `%+d%%` / `%0`; `Jitan's Gate Cooldown Reduced by 1`; `Innate <Element> Damage: N (P% of <Attribute>)`; `(Assassin Only)` on the class-locked relic; `Orb Effects Applied to this Item are Doubled`. Report any raw printf text, empty line or a skill name that reads like a placeholder |
| lane pa-quests (version not bumped; `mxl` shows the lines `merc revive price`, `quest experience`, `quest rewards`; off words `mercrevive questxp questrewards`) | **Median mercenary revive price, Act 5 quest experience, removed vanilla quest rewards** (plugin/src/quests_rewards.cpp, hirelings.cpp): kill your mercenary at level 126 and read Kashya's revive price; finish an Act 5 quest below level 130; finish Qual-Kehk's, Akara's, Andariel's, Anya's quests, smash the Hellforge soulstone, kill the Countess | the revive line costs level x 100 up to 105, `250 x (level - 90)^1.5` above (54,000 at level 126); each Act 5 quest gives exactly 50,000 experience (none from level 130); Qual-Kehk gives r08 r09 r10 only (Normal), Akara no ring, Andariel no two chipped gems, Anya's reward is an amulet, the Hellforge and the Countess drop their own classes. Game checks `mercrevive`, `questxp`, `questrewards` run the paths; the natural Hellforge smash and Countess kill are not covered by them |
| lane gap-classres (version not bumped; run `mxl` and read the `skill restrict`, `heat` and `trophy timer` lines, each `on: ...`) | **Hunter Steady Aim gate, Fire Sorceress Heat, trophy challenge windows** (plugin/src/skill_restrict.cpp: detour of the skill usability check `0x33f360`, modes 3-7; heat.cpp: detour of the mana regeneration `0x42e350`; trophy_timer.cpp: no hook, rides the goblins frame hook and the cube condition; off words `restrict`, `heat`, `trophy`) | (1) Druid with a bow (Hunter): look at Heartseeker and Cascade in the skill bar before any Steady Shot, then fire 4 Steady Shots and watch the Steady Aim counter. (2) Fire Sorceress with Molten Core: stand in the field with a full mana bar and wait; then cast Flamefront or Emberstep; walk into town. (3) Kill a trophy boss (e.g. Azmodan) and cube the heart: at once; after 15 s; after taking a town portal; after dying | (1) Heartseeker and Cascade cannot be used with no Steady Aim; the counter reads 1, 2, 3, 4; Heartseeker takes one charge per use. (2) The mana bar drains while Molten Core is active, fills while casting fire skills, holds in town. (3) The recipe works at once and not after 15 s, the zone change or death (a red chat line says the challenge is void). Tell me: whether the boss kill gives the challenge at all (nothing in the data says which skill a kill casts), the real time limit of each trophy, and whether the mana bar should say Heat |
| lane no-corpse-2 (version not bumped; run `mxl` and read the `corpse pickup` line: `on: stored corpses are picked up when a character enters a level (0x485350): picked N, kept N, faults N`; off word `corpsepickup`) | **No corpse ever: a corpse already stored in a save is picked up at load** (plugin/src/no_corpse.cpp hook on the level-entry function `0x485350` + D2R's own pickup `0x42b220`; docs/subsystems/death.md sections 8-9) | `py -3 tools/game_checks.py all nocorpse corpsepickup --slot N` (background mode; harness `state` lines `bodies other=.. stored=..`, client verb `ccorpses`). By hand: a character that died with the part off (`mxl2012-core-off.txt` = `nocorpse`) and is loaded with the part on | The body is not on screen, not after a respawn and not in town; the gear is back where it was; the next save has corpse count 0; a new death makes no body (server, client, saved list), the death spot is empty, gear / gold / xp unchanged, respawn after 5 s. Controls: with `nocorpse` off a body appears and follows to town; with `corpsepickup` off a stored body is loaded visibly |
| lane ns-plugin (version not bumped; needs the namespaced mod from ns-strings / ns-tables / ns-ui; `mxl` shows a `strings` line) | **Median text by key at run time** (plugin/src/strings.cpp: localization service, the plugin's own string ids for the NPC menu through a hook of D2R's numeric lookup `0x143e2b730`; docs/strings-namespace.md "Plugin uses") | Slot run: `mxl` must say `strings localization service on; string ids on`. Harness `mstr mxl2012:AkaraMenu1b` (client): `service=ok text="Reset Stat/Skill Points"`, an id near 65000 and the same text via the D2R lookup. `game_checks.py all cain cainsub respec trophy lockout`: Akara's and Cain's lines show Median's text (not `mxl2012:...`), the respec page header is the respec text, the trophy right click prints the challenge, a sealed dungeon prints its lines | Text of the lines equals Median's string; if a line shows `mxl2012:<key>` the service could not find the key (namespace file not installed, or the loader refuses another package's key from a plugin) |
| lane median-ai (version not bumped; run `mxl` and read the `monster ai` line: `on: andariel_ai (AI 155), Summoner roll < aip3, MosquitoNest init`) | **Median monster AI: andariel_ai as AI id 155, Summoner first-branch rule, MosquitoNest init** (plugin/src/monster_ai.cpp; detours the AI table getter `0x4a36c0`, patches `0x5b4e49` / `0x5b4fed`, writes entry 83's init). Not yet seen in game: all slots were busy | Rebuild with tools/build.py, install, restart. `debug_mode`, then `mspawn` (or harness `h spawn 156` for Andariel) Andariel, Maghda and Radament near you; screenshots over ~30 s, `h state`. Then `mxl`: the `monster ai` line shows the counters. Also with `medianai` in mxl2012-core-off.txt (the line says `fallback`) | The monster must not stand still (the engine takes a 156-row monai.txt). Close: melee, with occasional skill 1 / 4. Far (aip3 distance or more): walks in, waits 15 frames after it has engaged. Mid range: skills 2 and 3 on an 11-frame cooldown. Counters for wait / attack / charge / walk / skills must all rise. Summoner (Act 2): first spell chosen by the aip3 roll, not by your resistances. A MosquitoNest (if enabled in the level) spawns its first mosquito after its init delay |
| lane waypoint-panel (version not bumped; `py -3 tools/ui_layouts.py` then install with the plugin, restart the game; run `mxl` and read the `waypoints` line) | **Waypoint panel lists every Median waypoint under its own act, more than 9 per tab** (plugin/src/waypoints.cpp: hook of the tab fill `0x1ea9b0`, relocated button table, 3 readers patched; HD layout `waypointspaneloriginalhd.json` with `buttonOffset` 100; data tools/waypoints_data.py) | (1) `mxl`: the `waypoints` line ends with `panel list has a button for 47` (or the plugin's own on-line). (2) With a debug character: `waypoint all set`, `waypoint tabs`, `waypoint open` (harness) and look at every tab. (3) Touch a real waypoint, click Duncraig, Tran Athulua, Skartara, Caldeum, Torajan Jungles, Vizjun, Silver City and the Act 5 button (level 242): each must travel there. (4) Setting `waypoints` in `mxl2012-core-off.txt` returns the old 9-per-tab panel (rollback). | Tab I 10 buttons (Rogue Encampment ... Duncraig last), II 11 (Tran Athulua, Skartara last), III 12 (Caldeum, Torajan Jungles, Vizjun last), IV 4 (Pandemonium Fortress ... Silver City), V 10 (Tur Dulra last), none cut off or overlapping the panel frame in HD. Seen in game (slot run, screenshots of all 5 tabs): the lists above. **Not yet seen: step (3), a travel click from a real waypoint object** (a click from the harness-opened panel reached the server and was refused with "Impossible") |
| lane waypoints (data + plugin check, no version change; rebuild with tools/build.py, install and restart) | **Median waypoints with numbers 50-90** (tools/waypoints_data.py writes actinfo.txt: Act 4's six free slots list silver_city, duncraig, tran_athulua, island_of_skartara, caldeum, torajan_jungles; plugin/src/waypoints.cpp read-only check, Off word `waypoints`) | (1) `mxl`: the `waypoints` line must say `47 waypoint levels, numbers up to 90 of 112 bits; panel has a button for 45, none for levels 155, 242`. (2) Open a waypoint panel with a character past Act 3 (tab IV is locked until D2R's act 4 intro quest): five tabs as before; tab IV lists the three Act 4 waypoints and then the six Median names. If the game fails to start or the panel is empty or broken, delete `data/global/excel/actinfo.txt` and `base/actinfo.txt` from the installed mod and report the errors.log line. (3) Touch the waypoints of Duncraig (153), Tran Athulua (147), Skartara (169), Caldeum (138), Torajan Jungles (141) and Silver City (139): the panel opens, the current level is marked, and from another waypoint the button for it is enabled and travels there. (4) Save and exit, reload: those waypoints stay activated; check normal and nightmare separately (bits are per difficulty). (5) Touch Vizjun (155) and the Act 5 waypoint (242): the touch must not crash; they have no button (expected, docs/subsystems/areas-drlg.md 3b). | Numbers above 38 are saved and travelled to without a crash; 6 of the 8 are listed in tab IV, 2 are not |
| next build after 0.46.0 (run `mxl`, read `act 2-5 quests`) | **Acts 2-5 quest rewards, Median's catalysts and the respec flag** (plugin/src/quests_act2_5.cpp; hooks a2q5 `0x5a5490` / `0x5a5360`, a2q6 `0x5a66b0`, a3q3 `0x5ef040`, a3q5 `0x5f0df0`, a4q1 `0x5e67c0` / `0x5e6660`, a5q2 `0x54c810`, a5q6 `0x54fa70`, respec bookkeeping `0x5d9ae0`; details docs/subsystems/quests-requirements.md section 5c) | `mxl` must say `act 2-5 quests on: ...` (10 hooks; `partial: N of 10` names a hook that failed). Use debug-friendly characters: (1) Act 2, **Nightmare**: kill the Summoner with quest 13 active; look in the inventory and on the floor; leave and re-enter the game, drop the catalyst, click any Act 2 NPC (Drognan, Atma). (2) Act 2 Normal: kill Duriel, talk to Jerhyn (his Duriel line). (3) Act 3 Normal: bring the Blade of the Old Religion (Gidbinn) to Ormus; repeat the same conversation. Also try Nightmare (3 items) and Hell (5). (4) Act 3: finish Khalim's Will (smash the Compelling Orb path) and talk to Cain in Kurast. (5) Act 4 **Nightmare**: kill Izual; drop the catalyst, click Tyrael in town. (6) Act 5: free the barbarians (Rescue on Mount Arreat) and talk to Qual-Kehk, per difficulty. (7) Act 5 **Hell**: with a level 110+ character kill Baal and stay in the Worldstone Chamber (also test with a second player in the chamber and one in town). (8) Akara respec: use Akara's reset line below level 51 (Den of Evil done) and again at level 51+; click it twice in a row at 51+ | (1) a catalyst of learning (`0o[ `) in the killer's inventory when the Summoner dies, once; the same game or a new game: clicking an Act 2 NPC hands out a replacement only while it is missing; Normal and Hell: nothing. (2) one Arcane Crystal (`qum `) with the vanilla reward, once. (3) 1 / 3 / 5 shrine consumables (`*_shrine_10`, random each) in Normal / Nightmare / Hell, once (a second conversation gives nothing). (4) one Arcane Crystal at Cain's line, once. (5) a catalyst of jewelcraft (`jcat`) in the killer's inventory, Nightmare only, once; Tyrael hands out a replacement while it is missing (and not at Izual's ghost). (6) runes on top of D2R's own three: Normal r08 r09 r10, Nightmare r15 r16 r17, Hell r22 r23 r24 (two or one fewer when quest bits 6 / 7 are set; expect the count 3 in a normal run). (7) a relic orb (`qrel`) for every player in the chamber at level 110+, once per character and difficulty; nothing in other areas. (8) **to check Median's intent**: D2Sigma replaces the respec bookkeeping so the respec token is never used up (at 51+ it is re-armed explicitly); if the line vanishes after the first use below level 51, the replacement did not take. Tell me, per step, what dropped and any difference from the above. Known gaps: no client notices (D2Sigma messages 0x5f-0x61), the drops go to the killer only (D2Sigma drops one per player on the ground). mxl2012-core-off.txt word `quests2` leaves it out |
| lane areas (data only, no version change; rebuild with tools/build.py and install) | **Median's own areas: map objects and monsters** (txt_migrate adds Median's table to ObjPreset.txt, rows Index 1000+; install_mod.py runs tools/ds1_remap.py on the installed tiles and prints `ds1 ids: ... type1_renumbered=4095, type2_renumbered=27526, type2_dropped=30`; audit with `py -3 tools/area_audit.py`, expect 0 problems) | Enter Median's areas through their portals / waypoints / quests (no warp command exists): Ruins of Ureh, Caldeum, Silver City, Trials of the Dimensional Labyrinth (a maze: level types 4, 17, 32-34), Heart of Darkness, Duncraig. Look for: the level generating at all (no crash, no assert dialog; the log `d2rloader.log` may show one-time ASSERTION blocks, send them), the exit portals / waypoints / doors / chests where expected, bosses present (e.g. the Duncraig arenas, Void traps) | Each area loads and has its objects and its boss; if an area is empty or full of wrong monsters/objects, tell me which area and what you saw. mxl2012-core-off.txt has no word for this (data) |
| next build after 0.43.0 (run `mxl`, read the `npc actions` line) | **D2R-native NPC services: Imbue (Charsi), Add sockets (Larzuk), Personalize (Anya), and the travel packages with their waypoint grants** (plugin/src/npc_services.cpp, read-only check of the NPC table `0x237ea60` and the client fix table `0x22a70e0`; no hook, no line of ours: D2R's own lines and server code do the work, docs/subsystems/npc-hirelings.md 1.6) | `mxl` must say `npc actions on: 6 menu lines (Akara, Cain); 8 slots are D2R's own, 8 of 8 D2R-native services match Median's rows; travel gates moved 1` (Tyrael's gate byte is moved from quest 26 to Median's quest 28 at load; `py -3 tools/game_checks.py all tyrael` reads his menu with the quest bits in each state). In game, Normal: (1) finish Tools of the Trade (hand Charsi the Horadric Malus), talk to Charsi, click **Imbue**, pick a normal-quality weapon or armor, confirm. Try a magic item, a socketed item and an item Median should accept. Open Charsi again. (2) Same with Larzuk after Siege on Harrogath (**Socket**: pick a socketable normal or magic item) and Anya after Prison of Ice (**Personalize**, type a name). (3) Reload the character after each and open the menu again. (4) Kill Andariel, then click Warriv: **go east** to Lut Gholein; do not touch the waypoint there, open the waypoint panel at any waypoint. (5) After Duriel, click Meshif in act 2 (sail east) and open a waypoint panel in Kurast Docks; after Diablo go through Tyrael's portal and open the panel in Harrogath. (6) Warriv act 2 (go west) and Meshif act 3 (sail west) | (1) The line shows only while the reward is pending, the panel opens, the chosen item is imbued (becomes rare) and the line is gone afterwards (reward spent, not repeatable; Median does the same). (2) Same for sockets (item gets its sockets) and personalize (name in the item). (3) The change persists in the save and the line does not return. (4)-(5) The arrival town's waypoint is already active (Lut Gholein 40, Kurast Docks 75, Harrogath 109) without touching it. (6) The west trips work and grant nothing. Tell me: whether each line shows at the right time, which items the panel accepts or refuses (Median's new bases and uniques), whether the log line count differs (`7 of 8` expected, Tyrael is known to differ: D2R gates on quest 26, Median on 28), and whether Tyrael offers a travel line at all. mxl2012-core-off.txt word `npc` leaves the npc actions out |
| next build after 0.42.0 (run `mxl` and read the `hirelings` line) | **Mercenary class bonuses and Kashya's hire gate** (plugin/src/hirelings.cpp; hook on D2R's mercenary stat setup `0x544f60`, which the hire, the save load and every level-up run; data: `equivalentcharclass` pal / sor for the act 2 and 3 hirelings) | `mxl` must say `hirelings on: class bonuses on 0x544f60 hooked, Kashya level gate cleared`; the log gets up to 8 lines `hirelings: class C id I level L str S dex D: N stats set`. In game, Normal: (1) hire a Rogue Scout (Kashya), a Desert Mercenary, an Iron Wolf and (act 5) a Barbarian; open the hireling screen (stats): resistances, damage, life regeneration and speed should be well above a plain D2R mercenary (Rogue: movement +100%, dodge; Desert: skill armor, crushing blow, damage resist; Iron Wolf: large energy and armor; Barbarian: strength / dexterity bonus). (2) Level the mercenary or save and reload: the bonuses are still there. (3) A level 8+ character who has not killed Blood Raven talks to Kashya: no Hire entry works. (4) Equip a Paladin-only item (shield or aura item) on the Desert Mercenary and a Sorceress-only item on the Iron Wolf; an Amazon-only item on the Rogue and a Barbarian-only item on the Barbarian | (1) numbers clearly higher than vanilla; the Fighter Mage type (Desert, third) also has fire / cold mastery. (2) unchanged after level-up and reload. (3) hire refused until the quest is done. (4) the class items equip (D2R's `equivalentcharclass`); if the Desert / Iron Wolf refuse them, `equivalentcharclass` for acts 2 and 3 is not honoured and the column should go back to blank. Tell me the `mxl` line, the stat values you see and what (3) and (4) did. mxl2012-core-off.txt word `hirelings` leaves the plugin part out |
| next build after 0.42.0 (run `mxl` and read the `requirement gates` line) | **Requirement gates on D2R's NPC service table** (plugin/src/requirement_gates.cpp; checks Median's npcext shop / gamble / hire flags and requirement rows against the static NPC table `0x237ea60`, writes only where they differ; data tools/npc_services_data.py -> mxl_npc_services.h) | `mxl` must say `requirement gates on: NPC table 43 entries vs 25 Sigma service rows: N services agree, 0 cleared, 0 hire gates set, M Sigma-only, 0 dynamic`. In game, Normal: (1) open Atma, Geglash (act 2 Harem), Cain in Lut Gholein and in Harrogath: Talk only, no Trade button. (2) Open Gheed, Elzix, Alkor, Jamella, Drehya, Nihlathak: Trade and Gamble (Nihlathak: Gamble only) work. (3) Kashya and Qual-Kehk before their quests (Blood Raven; Rescue on Mount Arreat): no hire; Greiz and Asheara: hire works. (4) Finish Blood Raven, talk to Kashya | (1) no shop (matches always-false row 32). (2) as listed. (3) the hire entry is refused before the quest and the log has no `requirement gates` write. (4) Kashya hires. Tell me the `mxl` line (the counts), and any NPC whose Trade, Gamble or Hire differs from the above. mxl2012-core-off.txt word `reqgates` leaves it out |
| next build after 0.48.0 (run `mxl` and read the `item generation` and `game end` lines) | **Mercenary equip lists, bonus drops per player, game-end reset** (plugin/src/item_gen.cpp `MercRequirement`, game_end.cpp, quests_common.h `DropBonusPerPlayer`; data tools/txt_migrate.py -> mxl_hirelings.h `MercClasses`) | Normal: (1) hire a Rogue, a Desert Mercenary, an Iron Wolf and a Barbarian and try to put on them: Rogue bows only (no crossbows or melee weapons, no shields); Desert Mercenary spears and polearms (no swords, no auric shields of other types); Iron Wolf swords and scepters; Barbarian swords and two-hand swords as Median's hireclasses. (2) Kill Andariel in a TCP/IP game with two players: each player gets one catalyst of disenchantment on the ground; kill her again: none. (3) Same for the Summoner (Nightmare) and Izual. (4) Leave a game and make a new one with the same character: the cube crafts that are once per game (dungeon key) work again | (1) refused items give the 'cannot use' reaction; the `item generation` line counts `mercenary equip refused`. (2)-(3) one item per player per kill, lying where the boss died. (4) the key recipe works again; the `game end` line counts the games left. Tell me which class accepts or refuses what differs from the lists. mxl2012-core-off.txt words `gameend` and `classlock` leave the parts out |
| lane pa-damagered (version not bumped; run `mxl`: the `combat` line must end `hooks 0x44ef70 ok, 0x450670 ok, 0x4523e0 ok`) | **Damage reduction stats 184/189/417 on the incoming damage** (plugin/src/combat.cpp `HitStepHook`, combat_logic.h `ReduceField`; off word `damagered`) | `py -3 tools/game_checks.py all damagered` passed on 2026-10-22. By hand: `stat player 39 set 200`, `stat player 40 set 0`, `stat player 373 set 4`, `hit player fire 100000`: the line ends `field=6250` (25000 without the stat) | Not run in game: a monster as the defender (monprop `time` / `stam` rows carry 189 / 417), poison and leech entries |
| lane caps-events (version not bumped; run `mxl` and read the `combat` line) | **Max resistance 90, absorb credit stats, mercenary avoid caps** (plugin/src/combat.cpp; patches the `0x5f` clamps at `0x4524dd` / `0x14e7294` / `0x14f4686`, hook on the absorb step `0x450670`, `0x44ef70` accepts hirelings via `0x3af240`) | `mxl` must say `combat on: ... resist cap 75+max (max 90, 3/3 clamps), absorb credit stats 184/189/417; hooks 0x44ef70 ok, 0x450670 ok`. Background mode (harness): `h stat player 39 set 300`, `h stat player 40 set 20` (max fire), `h stat player 7 set 512000` / `6` (life), `goto 2` on the console, `h spawn 383 1` (Skeleton Mage, fire), read `h state` life every 30 s: fire resist 0 loses X per 30 s; 300 with max 0 / +10 / +20 should lose about 25% / 15% / 10% of X (95 would show 5%). Absorb: `h stat player 142 set 40`, `h stat player 446 1 set 50`: the net loss rises (credit halved), the log has `combat: absorb of N healed M (layer 1)`. Mercenary: hire one in act 1 and give it 100%+ dodge or avoid (a ring with the stat): its hit chance stays under the 60+max cap | Resist caps as above (CAN be seen on the character sheet too: Fire Resist capped at 90 with +20 max). Absorb: 446 / 184 / 189 lower the healing only, never the damage cut. Mercenary resist 90 cap and avoid cap: not exercised yet - tell me what the hireling panel shows with stacked resistances. mxl2012-core-off.txt word `combat` leaves all of it out |
| 0.41.0 (run `mxl` and read the `npc actions` line) | **NPC menu actions: Akara respec and Cain's crafting materials** (plugin/src/npc_actions.cpp; hooks the NPC menu builder `0x1147a0` and the menu packet handler `0x4b0470`; table tools/npc_actions_data.py -> mxl_npc_actions.h) | `mxl` must say `npc actions on: 6 menu lines (...); N stubbed services`. (1) Normal: finish Den of Evil (this sets the respec flag, quest 41 bit 1) with a character that has spent some stat and skill points, then click Akara: the menu must list Talk, Trade, **Reset Stat/Skill Points**; click it. Open Akara again. (2) Before rescuing Cain: click Cain in town (any act): his menu shows Talk, **crafting materials**, Identify (Identify only with unidentified items); click crafting materials. Then finish the Search for Cain (talk to Akara) and click it again; click it a third time; drop the cube and click again. (3) Kill Andariel (Normal) so the Andariel quest is done, click Cain's crafting materials; drop the catalyst and click again. (4) Read the log's `npc actions:` lines. (5) Open and close the Akara and Cain menus several times; open the Larzuk, Charsi, Anya, Warriv, Meshif and Tyrael menus | (1) Stats and skills are reset as D2R's own respec does (points back in the unspent pool, equipment that no longer fits is unequipped); the line then does nothing more (the vanilla respec quest is used up). (2) Before the rescue nothing happens (log `requirement not met`); after it a Horadric Cube lands in the inventory once; a second click gives nothing while you hold one, and the cube again after dropping it. (3) A catalyst of disenchantment (`3o[ `), not twice; Nightmare adds the catalysts of learning and jewelcraft after their Nightmare quests (rows 20, 21). The menu closes after every click. (4) Log lines `done` / `requirement not met` / `nothing to do` with the kind (0x10 + npcRow*16 + slot) and NPC class. (5) No crash, no duplicate lines, other menus unchanged (Larzuk, Charsi, Anya and the travel lines are stubs and are not drawn). Tell me: whether the lines show and look right (text, order), whether the respec really resets skills and stats, whether a line stays visible while its requirement fails (known), anything odd around Identify. mxl2012-core-off.txt word `npc` leaves it out |
| 0.40.0 (run `mxl` and read the `goblins` line) | **Treasure goblins** (plugin/src/goblins.cpp; hooks the server game frame `0x406550` and the kill wrapper `0x515640`, spawns with `0x4929e0`) | `mxl` must say `goblins on: tick on game frame, ...`. To provoke one quickly, set the environment variable `MXL_GOBLINS_FORCE=1` before launching D2RLoader (every roll passes; `=2` also skips the 'killed something in the last 15 s' test). Barbarian in Normal, leave town to the Blood Moor, kill one monster, then wait: the roll runs on game-frame multiples of 375 (every 15 s of game time), so within 15 s a goblin should appear 8 sub-tiles right/down of you. Run `mxl` again: the goblins line shows `N spawned (last <monster id> in level 2)`. Without the variable (real odds): fight continuously in the Blood Moor for several minutes: the Blood Moor chance is only 4/1024 per roll (one per ~250 rolls, about an hour), caves and most later areas 10/1024 (one per ~100 rolls, about 25 minutes), the Mirror Temple 16/1024; each extra player lowers it by 10% | A goblin (`treasure_goblin` id 2791 at most levels, also `shiny_hoarder` 2792, `arcane_collector` 2796, `glowing_baron` 2798) stands next to you; it runs away (AI OblivionKnight, speed 7) and drops gold, runes, jewelry and rare/Sacred gear from the `Goblin` treasure class when killed. Standing in town, being dead, or not fighting for 15 s gives none. The log has `mxl2012-core: goblin <id> spawned in level <n> near player <id> (frame <f>)` for the first 20. Tell me: whether the goblin shows up, where (inside a wall/off-screen?), whether it has the right name, whether it drops, and whether anything in the game misbehaves (a crash on game exit, kills not counted). mxl2012-core-off.txt word `goblins` leaves it out |
| 0.39.0 (run `mxl` and read the `act 1 quests` line) | **Act 1 quests: Griswold's Heart, Andariel catalyst, catalyst re-issue** (plugin/src/quests_act1.cpp; hooks a1q4 event 11 `0x5e0830`, a1q6 events 8 and 0 `0x5e1f00` / `0x5e1d30`, item generator `0x43cd50`) | `mxl` must say `act 1 quests on`. (1) Barbarian, Normal: finish Search for Cain (rescue Cain in Tristram, talk to him), then talk to Akara. (2) Normal: kill Andariel with quest 6 active; look in the inventory and on the floor. (3) Drop the catalyst (or sell it), then click Warriv in town. (4) Reload the character, join a new game in Normal and repeat 3. (5) Nightmare: kill Andariel again; click Warriv | (1) Griswold's Heart (Normal base, code 600) appears in the inventory at Akara's reward, together with the ring, once; Nightmare and Hell give the (N) / (H) versions. (2) A catalyst of disenchantment (`3o[ `) lands in the killer's inventory when Andariel dies (Normal only); no second one on a second kill. (3) Warriv hands it out again while it is missing, not while you hold one. (4) Same in a new game (the flag is a quest-record bit, quest 47 bit 0, so it is saved). (5) Nightmare gives no catalyst. Tell me: whether the Heart is the right unique (name and stats from uniqueitems rows 69-71), whether the log has a line `quests: Griswold's Heart ...`, whether Andariel and the quest still complete normally, and whether anything odd happens with the save. mxl2012-core-off.txt word `quests` leaves it out |
| 0.37.0 / 0.38.0 (hooks switched on in 0.38.0; run `mxl` and read the cube line; 0.38.0 also gives op 30 the +skills) | **Cube recipe conditions** (cubemain ops 29-42, cubemainext second condition and gold cost; stat ids in cubemain remapped) | Rebuild the data (python tools/build.py) and install. `mxl` must say `cube conditions on: 542 recipes`. In the Horadric Cube: (1) Wirt's Leg + Tome of Town Portal in town opens the Cow portal, in the field the cube makes nothing (op 36, recipe 2); (2) a recipe with a chance (ssgl + scum, recipes 5236-5238, op 37) works only some of the time; (3) the Boss Killer Ring recipes (op 33 state 893, e.g. ssgl + f700) work normally and stop while that state is active; (4) cubemain rows 6327-6329 (ext op 3: stat 532 at least 132 / 135 / 138, cost 50,000 / 100,000 / 200,000 gold) are offered only with that stat and the gold; (5) any of the 65 recipes with a gold cost (5,000 to 1,000,000 gold) is not offered when carried + banked gold is short (paying the gold: next row); (6) the 19 op-38 'useitem' recipes (6350-6368) are offered only after the craft that sets their flag (next row); (7) recipes with a stat condition on an item (amulets/rings/charms upgrades) now compare the right stat | The conditions hold: recipes show up in the cube only when they should (the Cow portal only in town). Tell me anything that becomes craftable that should not, or a recipe that no longer works; the log lists a line if the record pointer check fails. mxl2012-core-off.txt word `cube` leaves it out |
| 0.39.0 | **Cube craft flags and gold payment** (craft_flags.cpp; hook on the recipe executor 0x5269c0; `mxl` must say `craft flags on: 256 output effects`) | (1) Player flag: as an assassin with `RathmasSupremacy2`, craft recipe row 6369 (the upgrade of that quest item, sets player flag 1); then the op-38 recipe 6350 (same input item, output `useitem`) must be offered in the cube; before the craft it must not be. (2) Game flag: craft a dungeon key, recipe row 7100 (`UpgradedBossKillerRing` + `erun` + `f700`, sets game flag 50); a second try in the same game is refused, after leaving and creating a new game it works again. (3) Gold: recipe rows 6327-6329 (stat 532 at least 132 / 135 / 138; 50,000 / 100,000 / 200,000 gold), or any recipe with a gold cost: carried plus banked gold is reduced by the cost after the craft, carried gold first, then the bank | Flags unlock and guard as described and are gone in a new game; gold drops by the cost (read it on the inventory screen and the stash; if the carried gold only updates after reopening the inventory, say so, a stat packet is then needed). mxl2012-core-off.txt word `craftflags` leaves it out |
| lane sigma-behaviours-a (version not bumped; run `mxl` and read the `npc actions` line, it ends `respec confirm on`) | **Akara's respec confirmation and the trophy hover text** (plugin/src/npc_actions.cpp `OpenConfirm`, item_spells.cpp `RevealTrophy`; data tools/npc_actions_data.py, tools/txt_migrate.py `item_spells` / `item_level_line`; harness `menu confirm|yes|no`) | (1) `py -3 tools/game_checks.py all respec`: Akara's respec line opens D2R's Yes / No page (header: the respec text), `menu no` leaves strength unchanged, the line again then `menu yes` resets the stats. By hand: click Akara's Reset Stat/Skill Points line, answer No, then Yes. (2) `py -3 tools/game_checks.py all trophy`: `item a56 inv` (Heart of Azmodan), hover it in the inventory, then `use a56` (right click). (3) Types with `NoShowILvl` (runes, trophies, ...) never show an item level line, also with `display_item_levels = true` in d2rloader.toml | (1) The click shows the page and sends nothing; No closes the menu with the stats as they were; Yes respecs once. (2) The tooltip says "Right click to reveal trophy challenge" (not the challenge); the right click prints the challenge in the message log, title gold, and the item stays; the check reports `sent` +10 per use. (3) No "Item Level" line on those types. Seen in game (slot 3): (1) and (2) (`respec_confirm.png`, `trophy_revealed.png`); not seen: (3) |
| lane approx-items (version not bumped; run `mxl` and read the `npc actions`, `dungeon lockout`, `client messages` and `items` lines) | **Cain submenu, dungeon countdown, party experience** (plugin/src/npc_actions.cpp, dungeon_lockout.cpp, client_messages.cpp, items_ext.cpp; off words `clientmsg`, `lockout`, `npc`, `partyxp`) | (0) `cainsub` check passes (first talk with a Cain takes ~30 s before the list appears; the line is read from the record after the speech). (1) Talk to any Cain, click "crafting materials": the list is replaced by the entries whose requirement holds (horadric cube after the rescue, catalysts after their quest while you lack them); click one: the item is created; ESC / talk again shows the normal menu. (2) Enter a Median dungeon with a lock time (e.g. via `b62X` on Hell, level 253): orange "Closing in: mm:ss" + "ONCE YOU EXIT YOU CANNOT GO BACK" at the top of the screen counts down; leaving the level hides it. (3) Party of two near a monster: each gets the monster's whole experience, range about 179 units (two-player game not run yet) | Submenu entries show and give the item; the countdown runs and matches the sealing time; both party members gain the full experience |
| lane dungeon-lockout (version not bumped; run `mxl` and read the `dungeon lockout` line) | **Dungeon lockout and level entry requirements** (plugin/src/dungeon_lockout.cpp; hooks the warp action `0x491ff0` and the portal object operate function `0x58f680`; rules from D2Sigma `0x5d810` / `0x5cee0` / `0x5d9d0`) | `mxl` must say `dungeon lockout on: 162 levels; tile warps on, portals on`. Hell character of class Amazon, level about 100, Act 5 town. (1) Entry requirements: use a key or scroll that opens a level with a Hell level requirement above your level (e.g. a level 125 area) and step into the portal; Normal / Nightmare character with a Hell-only portal (level 138 and up); a non-Druid in a Mirror Temple (256-262). (2) Clock: open a portal to a level with a short lock time (157 Butcher's Lair, 20 s; 159 Proving Grounds, 20 s; or 251 with Scroll of Summoning, 60 s), step in, leave by the town portal inside the lock time and re-enter by the same portal: allowed. Wait out the lock time (inside or outside) and try again. (3) Stairs: a level with a lock time reached by stairs or a tile (132 World Stone Keep from the Throne of Destruction, 1200 s; 268 / 269 Heroic Library 6 / 7 share one clock) starts the clock too. (4) New game: leave the game, make a new one, repeat (2) | (1) The portal does not take you: the character stays where he is and plays the generic "can't do that" reaction; log line `lockout: entry requirements not met, refused (src -> dst)`. Meeting the level and difficulty enters normally. (2) First entry logs `lockout: clock started (src -> dst)`; entering again inside the lock time works; after the time has run out the portal / stairs no longer take you in (log `level sealed, entry refused`), the town portal out of the level still works. (3) Same for stairs. (4) The new game has no seals. Tell me: whether a refusal shows or says anything on screen (Median shows a text and a timer widget that D2R does not have), whether the portal / warp clicks leave the character in a stuck state, whether the one-way portals (objects 600) are refused too (if not, they use another operate function), and whether the lock time feels right against the table (docs/plugin-spec.md, dungeon lockout). mxl2012-core-off.txt word `lockout` leaves it out |
| data + plugin | **Skill tree look and pages: Median's tab titles, stone, arrows, all pages (8, Sorceress 9)** (bug #3; tools/skill_tree_art.py + ui_layouts.py; 9 tab pictures per class; plugin skill_tree.cpp makes pages 4-9 selectable and fills them: `mxl` shows `skill tree on: 13 sites + tab setter hook`; tools/skill_icons.py gives every skill its own icon) | Open the skill tree (T) in HD as a few classes (Barbarian, Sorceress, Paladin...) and click every tab; then press G and do the same in classic mode | HD: a row of 8 tabs with Median's titles (e.g. Barbarian: Nomad, Earthshaker, Windcarver, Elementalist, Warmonger, Shaman, Mastery, Reward), the clicked tab lit, a dark brown Median stone, sockets under every skill icon and Median's arrows between them (they should point the way the skills depend on each other); icons sit in the sockets. Classic: Median's stone with a column of 8 titled tabs on the right and sockets/arrows behind the icons. Every tab shows its skills on its sockets (Barbarian tab 7 Mastery: 9 icons, tab 8 Reward: 7). Report if only 3 tabs show art or tabs 5-8 act like tab 4, a socket stays empty, a tab shows the wrong class's picture, icons are off their sockets, or the panel is blank (screenshot). Sorceress: 9 tabs (Arcane, Fire, Lightning, Cold, Poison, Melee, Mastery, Coven, Reward); the other classes show 8 tabs and a blank 9th cell, and a click on it changes nothing (checked 2026-10-22, HD and G) |
| data | **Median stash size: 14 x 14** (personal and shared pages; inventory.txt Big Bank, HD stash panel with Median's art) | Open the stash: personal tab and the shared tabs. Put items in the far corners (column 14, row 14), switch tabs, leave and reload; check the shared stash still loads for another character | Median's stash art, 14 x 14 grid lined up with it (grid, tabs and gold box confirmed 2026-10-14), items scaled like the inventory; Personal/Shared tabs centred above the grid where Median's gold box was; Median's gold box now at the bottom with D2R's gold button and amount on it; shared-stash arrows and gold withdraw work; items stay put after reload. D2R's Gems/Materials/Runes tabs unchanged. Backup: mxl-manual-backups/all-before-14x14-stash. Also note: since this build the game logs a 'leaked Stats' check when it closes; tell me if anything misbehaves around quitting |
| data | **Median inventory and cube sizes: 15 x 10** (inventory.txt gridX/gridY; HD panels with Median's own art, tools/ui_panels.py + ui_layouts.py) | Open the inventory (I) and the Horadric Cube in HD. Move items into the new rows/columns, equip items in every slot, swap weapons (W), transmute something; save and reload; press G for classic | Inventory: Median's panel, 15 x 10 grid lined up with the art, equipment slots where Median has them, gold box bottom left. Cube: Median's crafting panel, 15 x 10 grid, transmute button under it. Items stay where they were after reload. Report anything misplaced (a screenshot helps). Press G: classic mode now has Median's art for inventory and cube (15 x 10 on scaled grids; items are smaller than in HD), check I / cube / C / stash (both tabs and shared pages) / a vendor: items on the grid cells, nothing overlapping (screenshot). Backup of all characters: mxl-manual-backups/all-before-15x10-inventory |
| data | **Median character sheet** (statsheet page 0 as the HD background, D2R stat widgets moved into its boxes; tools/ui_panels.py 'charsheet', tools/ui_layouts.py char_sheet()) | In HD press C; check with points to spend and with a weapon equipped; hover the stat labels | Median's panel with: name and Level / Class in the top bar, Life / Mana / Stamina and experience in the four bars around the circle, Strength / Dexterity / Vitality / Energy (value box left of the label) with the +1 buttons right of the rows, Fire / Cold / Lightning / Poison and Defense in the boxes, damage and attack rating of the left and right skill beside the weapon portraits, stat points remaining at the bottom. Report text outside its box, missing numbers or buttons off the rows (screenshot). Known: pages 2 and 3 of Median's sheet (extra stats) are not built |
| data | **Median stat pages as Advanced Stats rows** (itemstatcost advdisplay: 96 stats of Median's sheet pages 2-3, descfunc 19 for D2R's printf texts; tools/stat_screen.py, txt_migrate.py advanced_stats; docs/subsystems/stat-screen.md) | In HD press C, click the arrow on the sheet's right edge; scroll the list; equip items with speed / absorb / resist / damage mods | The list starts with thirteen rows shown even at 0 (attack rating, block, five speeds, six resistances), then only the stats the character has, texts like "+30 to Strength" / "+20% Faster Cast Rate" (no raw %d / %+d, no doubled value). Report garbled lines, a row for a stat Median's sheet does not show, or a stat that is missing. Item tooltips of those stats should read the same way |
| data | **Median trade window, NPC store and in-stash cube sizes** (inventory.txt Trade Page 1/2 = 7 x 15 each, Monster = 15 x 15; HD panels tradelayouthd / vendorpanellayouthd / bankexpansionlayouthd with Median's trade.dc6 and store.dc6 art; materials tab cube view 15 x 10; tools/txt_migrate.py, ui_panels.py, ui_layouts.py) | In HD: (1) trade with a second player (TCP/IP test): open the trade window, move items into both columns, accept; (2) open Gheed, Charsi, Akara and a gambler: all four tabs, buy and sell, repair (Charsi), refresh (gambler); (3) open the stash, Materials tab, put items into the cube view and transmute | (1) Two 7 x 15 grids side by side on Median's trade art, names and accept buttons in the header bars, gold under each grid; check which side is yours (left is 'them', right is 'us' in the layout, swap TRADE_GRIDS/TRADE_BARS in ui_layouts.py if wrong). (2) 15 x 15 store grid on Median's store art, D2R's tabs lined up over the four tab slots (none drawn pressed in the art), gold text in Median's gold bar at the top, repair/refresh buttons under the grid not overlapping it. (3) The cube view is a 15 x 10 grid on pasted art over the old recess (side stubs of D2R's art may show), items match the Horadric Cube panel; transmute button below. Classic (G): the trade window has Median's art and two 7 x 15 grids, untested (needs two players): check names, accept buttons and gold under the grids. Report where the item cells and art disagree (screenshot) |
| data | **Cold effect on monsters** (coldeffect -20, was read as 236) | Chill monsters (any cold skill or cold damage item) | Chilled monsters slow down (Median: -20%) instead of speeding up |
| data | **Monster sequence skills** (monstats Sk*mode `mqN` -> sequence names, 1,152 slots) | Fight monsters that raise or revive (Fallen Shamans, Greater Mummies, skeleton-raising casters), charging monsters, Sand Maggots | Shamans revive Fallen, mummies raise, maggots burrow and lay eggs, chargers charge; no monster stands still where it should use a skill |
| data | **HD item pictures: Median's own art** (tools/item_art.py, 987 base items + 45 uniques + 22 set items) | In HD, open a vendor (Gheed, Charsi, Akara) and the stash; look at Median-only items (charms, crafting items, Median armors, quest items); compare with G | They show Median's real picture (upscaled from classic: crisp edges, docs/hd-icons.md "Picture quality"; Median's extra gem colours use D2R's HD gems recoloured) instead of a D2R look-alike; nothing missing or misplaced in the grid |
| 0.36.0 | **Whirlwind hit rate as in classic Median** (1.13c table: a hit every 4-16 frames by weapon speed) | barby: Whirlwind through a pack with the axe; if you have one, try a faster weapon or an IAS item | Noticeably more hits per spin than before (D2R's own timing hit about half as often). Tell me how it feels against classic Median; the log records the speeds of the first hits |
| data | **HD body animations for sequence skills** (tools/hd_skill_anims.py) | barby (level 10): cast Whirlwind outside town; also leap_2 if learnable. Other classes: Assassin smg (Blade Fury look), any class with hurricane_2 / virulence items | The HD Barbarian model spins during Whirlwind like D2R's own Whirlwind; check classic mode (G) too; leap_2 uses Leap's animation |
| 0.35.0 | **States fix off by default** (bug #22: D2RLoader syncs Median's states itself) | Load barby (now level 10, 50 energy, 9 skill points), go to the Blood Moor: hover and attack monsters; cast Whirlwind; play a while with buffs/auras | Monsters highlight and can be attacked; Whirlwind shows its spin; buffs show their effects; no random states, no crash |
| data | **Whirlwind and every other sequence skill** (2026-10-14: moves and hits now; spin effect still not drawn, server sets state 174, testing client state sync with 0.34.4 and the states fix off; anim GH -> SQ: they played the knockback and never started; plus D2R's stop functions and the overlay Character column) | barby: walk out of town (Whirlwind does not work in town), cast Whirlwind at the ground across monsters 3-4 times, let go once mid-spin. Any class: other multi-hit / sequence skills (Zeal-like strikes, Strafe-like volleys, Fend) | The character spins with D2R's whirlwind effect, moves to the clicked spot, hits monsters on the way and stops cleanly; the other sequence skills play their attack sequence instead of a knockback. Tooltip as before; G for classic |
| data (deferred by the user, 2026-10-07) | **Whirlpool, final pass** on a new Paladin (`paladin`): HD looks (missile_hd.py), sounds (Median's sound rows) | New Paladin; get Whirlpool (axe/item written into the save, or Leather of Aut), any melee weapon, hit a monster; also press G for classic graphics | HD: a blue tornado-style swirl on the target (placeholder for Median's ColdFuse), cold bolts flying out (Frozen Orb's), a bone-spirit burst when each swirl ends; the sewer-water sound plays with the swirl. Classic mode: the bolts and burst show, the swirl itself is invisible (ColdFuse art not ported yet). Tooltip: Whirlpool, % weapon damage, "item granted skill"; no crash |
| data (art and Median areas deferred by the user, 2026-10-07; hovering is bug #22) | **Median monsters (Phase 5 step 2)**: own animations + timing (animdata), HD look-alike model | Leave town in Act 1 and fight; press G now and then. Also try a Median-only area (e.g. a Trial) | HD: monsters look like D2R monsters as before, but attack/move with Median's timing; they can be hovered and targeted. Classic (G): Median's own monster art. Note any monster that is invisible, stuck, untargetable, or crashes the game (name + area). Player attack speeds now follow Median's animdata (e.g. Sorceress staff attack) |
| data | **Classic graphics (Phase 5 step 1)**: Median's item pictures (542 .dc6), missile and overlay animations now in the mod | In game press G (classic graphics). Open the inventory and a vendor (Gheed, Charsi): look at Median-only items (charms, runes, uniques). Cast Whirlpool on the Paladin; cast a few Median skills with missiles | Items show Median's own pictures in classic mode (in HD they keep the look-alikes). Whirlpool's swirl (coldfuse) is visible in classic mode. If classic mode shows nothing for these or crashes, D2R does not read classic art from mods: note which |
| 0.33.0 (deferred by the user, 2026-10-07) | **Automap in Median-only areas** (bug #15) | Enter an area on Median's own level types: Caldeum or Caldeum Library (Act 2 town area), Ruins of Ureh, Silver City, Corrupted Abbey, a Trial (Vasily, Bul-Kathos), a Dimensional Labyrinth. Open the map (Tab) and walk around | Walls and floors appear on the automap as you explore (before: an empty map there). Map pieces may look slightly off (Median art vs D2R's automap sprite); no crash when opening the map or changing area. Heart of Darkness / End of Time (type 50) have no Median automap rows, so they stay empty |
| 0.32.0 | **Phalanx** (Amazon phalanx_2; missile do 4 -> 46 / client 69 -> 14) and the **nova fix** (missile hit 66 never fired before) | Amazon: cast Phalanx at a pack. Any class: retest the 0.26.0 nova skills (frigid_nova, coronation, hammertime) | Phalanx: an invisible line walks out and leaves arrow-shooting tiles every few steps (the tiles may show only on the server side if their look is missing). Nova: a ring of sub-missiles when the missile ends. No crash |
| 0.31.0 | Formula functions itemstat / tabpoints (hidden passives: helmet/shield armour bonuses, skills_2062-2069 and 3001; Amazon skills_1473) | Character sheet with and without a helmet / shield equipped; compare Defense and the related bonuses before and after equipping | Bonuses that depend on the helmet or shield's own stats now change when you swap them (before: they acted as if nothing was equipped). No crash when equipping, swapping weapons (W) or dropping items |
| data | **Skill tree rules** (devotion locks, "up to three masteries"; in the skpoints formulas, bug #4) | Amazon: put a point in one devotion (e.g. Bow Devotion), then try another devotion. Any class with mastery unlocks: learn three masteries, then try a fourth | The second devotion and the fourth mastery refuse the point (the + button does nothing / shows no cost) |
| 0.30.0 | **Habeas Corpus** (Paladin; missile hit 73 -> slot 65) and **Resurrect** remembering what it raised | Paladin with Resurrect and Habeas Corpus (Item Spawner / skill points): kill a monster, Resurrect its corpse, then cast Habeas Corpus elsewhere. Also cast Habeas Corpus before ever resurrecting | After a Resurrect, Habeas Corpus leaves corpses of that monster type where it lands (D2Sigma spawns them in the "dead" mode; if D2R shows live monsters or nothing, note which). Before any Resurrect it does nothing. Resurrect itself still works as before; no crash |
| 0.29.0 | **Mana costs from the plugin**: summon costs that grow with petmax (16 summons, calc7) and Median's mana cost % (stat 228) | Cast a summon such as Blood Skeleton or Summon Sinner a few times and watch the mana it takes; equip an item with "+/-% mana cost" (stat 228) and cast any skill with and without it | Summons cost a share of max mana (D2Sigma's formula); with the item the drain changes by that %. Tooltip Mana Cost lines still show the plain table value for these (tooltips are not hooked). No crash on casting. If a skill suddenly costs nothing or everything, note which |
| data | **Mana costs** (D2Sigma's skills2 formulas -> skills.txt mana/lvlmana; tooltip type 77) | Any class skill: hover it in the skill tree, then cast it repeatedly | The tooltip shows a Mana Cost line; casting drains that much mana (e.g. Whirlpool about 75 at level 1, Fire Arrow about 3) and stops when mana runs out. Before this, skills cost only their minimum mana |
| data | **Bug #7**: string IDs below 65536 | New character; talk to Gheed (and Akara, Kashya, Charsi, Warriv) the first time; read a few item and skill tooltips | Gheed greets with his own line ("Good day to you partner! ..."), not "Arcane Ape"; no other text looks out of place |
| 0.28.0 | Missile hits: level portal (srvhit 69, D2Sigma 30), heal ally (67, D2Sigma 34), missile at owner's target (62 + client 6), client nova (client 7) | Portal: skills ancient_gate / judgementwander (a red portal where the missile lands; the one-way kind opens once per game). Heal: monster skills (sinew_shaper and others) heal their allies: hurt a pack, watch the healer's missiles top them up. Nova: frigid_nova, coronation, hammertime (the ring of bolts is now drawn on your screen too) | Portal opens and leads to its level; the hurt monsters' life goes up; nova ring visible; no crash |
| data | **Bug #18 stopgap**: HD pictures for all Median items (tools/item_hd.py) | Open a vendor (Charsi, Gheed, Akara) and browse every tab; buy a quiver; open the debug-mode Item Spawner and scroll its lists | Every item shows a picture (vanilla look-alikes: Median items share D2R art for now); no crash, no freeze at the vendor |
| 0.27.0 | Missile hit owner state (srvhit 63, D2Sigma 71) and summon (srvhit 68, D2Sigma 41) | State: skills Fire Ball (Median's), vanquish, brace_for_impact, inoculation; Summon: monsters corrupted_necromancer, councillor_ormac, sinew_shaper | State: after the missile lands the CASTER gets the buff (its stats show; the state's visual may be missing). Summon: a minion appears where the boss's missile lands; no crash |
| 0.26.0 (fix 0.32.0) | Missile hit nova (srvhit 66, D2Sigma 77) and explosion (D2Sigma 69 -> D2R hit 1) | Nova: skills frigid_nova, frigid_domain, coronation, hammertime, hurricane_2. Explosion: skills gorefest, wychwind, flamestrike, earthquake_2, mana_pulse, batstrike, warp_crash | Nova: when the missile ends, a ring of sub-missiles flies out (frigid nova: a ring of cold bolts); no crash. Explosion: the hit damages every monster in a small radius around the impact, not just the one hit |
| 0.12.0 | Mystic orbs (bug #11) | Buy an orb from Gheed (e.g. a stat orb), right-click it, click an armour or weapon in the inventory | Cursor changes like Identify; the item gains the orb's bonus and +4 level requirement; the orb is used up. Applying the same orb beyond its maximum (5 for normal orbs), or to an item it doesn't fit, does nothing and keeps the orb. Also try one on an equipped item |
| 0.12.0 | Dyes (bug #11) | Right-click a mystic dye, click an armour | Dye used up, no crash (the colour won't show: D2R draws items without Median's dye) |
| 0.14.0 | Arcane shard help | Hover an arcane shard, Arcane Crystal, Oil of Craft, a catalyst | The recipe help text shows in the tooltip (check the line order); right-click does nothing and the item stays |
| 0.14.0 | Containers (gem/rune clusters) | Cube Oil of Craft + a perfect gem -> gem cluster; carry 2-3 more of that perfect gem (inventory and cube; stash too while in town); right-click the cluster | The gems disappear, the cluster's count goes up by one each (up to 50), the cluster stays. No duplicates or ghost items after moving things around / relogging |
| 0.13.0 | Keys open portals | In Harrogath (Act V): right-click dimensional_link (`ktox`) or mind_warp (`kfau`). In Act IV town: key_of_lies (`kbel`) or key_of_sin (`kazm`). Riftstones `cr01` (Act I), `cr02` (Act II), Hell only | A red portal opens next to you, leads to the level and back. A second use of the same key in that game does nothing. `ktox`, `ksco`, `ktpx` and riftstones are used up; `kbel`/`kazm`/`kfau`/`tbr` stay (0.14.0) |
| 0.13.0 | Key in the wrong act | Right-click key_of_lies in Act I town | "Can't do that" message, key kept |
| 0.13.0 | One-way portals | charged_riftstone_16 (`cr21`, Act V) or scroll_of_summoning (`b60X`, Act I) | A portal (Median's one-way portal object) opens; check it can be entered |
| data | Item skill procs/oskills (bug #16) | A unique with "+N to <Median skill>" or "chance to cast", e.g. Book of Triune (Mind Control) | Tooltip and proc name the right skill |
| 0.8.0 | Synergies (syn1-syn6) | An item with "+X% to <skill>"-style synergy bonuses; compare the skill's damage/tooltip with and without it | Damage/tooltip changes with the item |
| 0.8.0 | Item max-level bonus (skcp) | An item with "+N to maximum level of <skill>" | That skill can take N more points |
| 0.9.0 | Base-level skill values (bl12/bd12...) and weapon damage % (wdm) | Skill tooltips that show per-level values or "% weapon damage"; raise the skill by a point and check the value moves | Non-zero values that grow with points spent (not with +skill items) |
| 0.11.0 | State-dependent formulas (hasstate) | Fire Ball's poison interaction, or any skill that changes while a buff/curse is on (e.g. Meditation, shrine effects) | Values change when the state is active |
| 0.11.0 | Layered stat formulas (statlayer) | Holy Shock tooltip with "activation frequency" items | Values include the per-skill item bonus |
| 0.10.0 | Missile formulas (msyn, blvl) | A skill whose missile damage/size scales with the skill's points or synergy items (32 missiles use blvl) | Missile effect grows with points spent |
| 0.9.0 | "Maxed skill" effects (bmax/maxe) | Skills whose tooltip/bonus changes when maxed (e.g. "max this skill ... to remove cooldown") | The bonus appears once the skill reaches its current cap |
| 0.9.0 | Cooldown in skill tooltips (skcd) | Tooltip of a skill with a cooldown | Shows the cooldown (not 0) |
| 0.54.x | Cooldown reduction and shared groups (`cooldowns`) | Item with stat 309 (reduces cooldown of a skill); cast a skill of a group (Deep Freeze, Thunderstorm, Purifying Flame) | The wait is shorter by the stat; the other skills of the group are on cooldown until the same moment (game check `cooldowns`) |
| lane skill-leftovers (version not bumped; `mxl` cooldowns line gains `non-player starts skipped N`) | Monsters have no cooldowns; restrict modes 3-7 do not apply to item procs (as Median) | `py -3 tools/game_checks.py all cooldowns restrictitems` passed on 2026-10-22: a spawned Andariel casts skill 812 (delay 125) twice in a row via `mcast 812 7 unit <id>` and holds no stat 359 / state 0xb9 / 0x79; Heartseeker is refused on the cast path without Steady Aim (code 4) and an item's cast on kill (stat 376, `evtrace fire 9`) fires both without and with it | The monster `monsters` counter stays 0: D2R's own monster skill finish does not reach `0x439500` here (same result with the part off), so the rule is a guard. Not run in game: a hireling or pet casting a delay skill |
| 0.69.16 (lane rune-stack; data: itemtypes ids, `typeids` a self-check) | **Socketed runes apply their gems.txt mods and stack (bug #50)**: D2R's hardcoded item type numbers (58 jewl, 68 h2h, 75 rune, 77 hpot, 82 wpot, 84 mcha, 96 gem4) match our itemtypes.txt (tools/txt_migrate.py `align_item_types`) | `py -3 tools/game_checks.py --slot N all mxl typeids runestack potions hiregates classlock equipall` (equipall as in the 0.69.15 row; run 2026-10-27 on slot 2, HD and legacy, also with the release launch keys `-w` without `-txt`); `mxl`: `item type ids ok: 25 of 25 ...`. `equipall` ground mode now walks to the item before the pickup to the cursor too (a drop ~4 subtiles away was not picked up: k11 / k19 superior). By hand: socket 1, 2, 3 Eld into a socketed helm or armour and read Maximum Damage | Each Eld adds +3 Maximum Damage in armour / helm / shield, each Ral +30 Fire Resist in a weapon; with the Runemaster bonus each rune adds its Defense %; gems and jewels as before |
| lane pa2-skills (version not bumped; `mxl` gains the lines `collide types` and `skill starts`; off words `collidetypes`, `skillstarts`) | Missile CollideType 9 / 10 in the collision tables, D2Sigma's start functions 30 / 66, activation frequency (stat 427) | `py -3 tools/game_checks.py all collidetypes skillstarts activationfreq` passed on 2026-10-23 (evidence `checks-20261023-015713-s3`): server / client rows 0-8 as D2R's, 9 = mask 0x180 with type 3's function, 10 = 0x2080 with type 1's, row 255 empty; the 15 missiles.txt rows with 9 load as 9 (they load as 8 without the record fix); a row-0 arrow fired as types 3, 8, 9 stops at a monster, as type 6 passes it, and every type ends at a wall at the same place; Flash gets state 182 for 19 frames, Move Only is refused, sk851 level 3 lasts 75 frames and is refused while on, a real Flash cast reaches slot 71; Sentence fires 6 missiles in 6 s with stat 427 = 0 and = 200 | A plain arrow cannot show the missing wall bit of type 9: D2R's movement ends every missile at a wall. A real cast of sk851 is not possible (no left / right skill flag); Flash's do function 109 is D2R's Town Portal. Harness verbs added: `collide`, `collidetable`, `wallscan`, `hasstate`, `startfn`, `startstats` |
| 0.9.0 | Area-dependent skills (area) | The class "slow missiles" passives (paragon_of_sanc...) in their level range | Active only in the areas their Param7..Param8 range covers |
| data | Formulas with other Median codes (aura, area, bl12...) | Skills whose tooltips previously showed odd or zero values | Values show (codes not yet implemented count as 0) |
| 0.6.0 | States fix (bug #14) | Play a while with buffs, auras, curses, summons; enter/leave towns and areas | No crashes; buffs show and expire normally |
| 0.6.0 | High-numbered Median states | A Median buff skill late in the list (e.g. a class aura/shout) and its icon/overlay | Effect applies and ends; no crash |
| data | Skill caps (Median's real rules) | Spend points in one tab | Each skill stops at its own cap (e.g. 20 or 25; Molten Core 1); a point in the tab's Specialization raises the caps; locked pairs (e.g. Molten Core vs Entanglement) can't both be taken |
| data | Town Portal (bug #6) | Put Town Portal on the right mouse button, cast outside town | Blue portal opens, leads to town and back |
| data | Death no longer crashes (bug #12) | Die to anything | "... was slain by ..." message, no crash |
| data | Tooltip number lines (296 strings kept from D2R) | Hover items and skills | "Durability: x of y", "Required Strength: n" etc. show their numbers |
| 0.15.0 | Minion scaling (Median's rules) | Necromancer blood_skeleton or Barbarian guardian_spirit at two different character levels / skill levels; hover the pet | Pet level = your level; life grows with skill level and your level (and "+% summon life" items); attack rating grows with skill level; "+summon resist" items raise its resists. Compare with the skill tooltip's life/AR lines (mnhp/mnar, now non-zero) |
| data | hyena_strike / exorcism (D2Sigma 161 -> D2R Rabies) | Amazon hyena_strike on a monster | Melee hit with poison damage, the hyena state on the target, hyena_strike_missile appears |
| 0.25.0 | Missile hit "cast skill" (srvhit 64) | Druid **Egg Trap**: let an egg hatch/hit; Sorceress wintertide, phoenix_wave | When the missile lands, the follow-up skill fires (e.g. Egg Trap's hatch effect) on the target or spot; no crash |
| 0.24.0 | Replaced client functions | vampiric_strike / deathgaze (fan of missiles on the target), parasite_2/3 or rock_shock (two missiles forming a wall at the target), Raise Skeleton (corpse effect), flamefront_15 | Missiles appear as described, no Amazon chain-lightning visuals on parasite/rock_shock, no crash |
| 0.23.0 | Client missile row / missile at target (client 110/112) | Druid Egg Trap, Sorceress flamefront (missile row); havoc or heaven_s_fury_2 (missile at target) | Missile-row skills show their row of missiles (server-drawn) with no Volcano effects; havoc / heaven_s_fury_2 show their missiles at the target; no crash |
| 0.22.0 | **Whirlpool** (server slot 178 + client slot 111) | Wear Leather of Aut (low-level unique; also Black Ice, Waterwalk) which grants Whirlpool; put it on a mouse button with a melee weapon and hit a monster | The hit lands, then a spinning blue whirlpool appears on the target and throws out growing rings of bolts (magic damage); no Warlock/sigil effects, no crash. Also try torment / crucify_2 / ravage (same functions) |
| 0.21.0 | Level portal skill (slot 173) | Whatever grants mysterious_companion_skill / judgementwander_2_skill (item or NPC skill) | A red portal opens next to you to that level; nothing when the level is in another act |
| data | resurrect_2 (-> D2R Revive) | Paladin level-90 resurrect_2 on a corpse | Monster revives as a pet; note its life (Median set it outright, D2R treats the value as a bonus) |
| 0.20.0 | Pets inherit the owner's procs | Wear an item with "X% chance to cast level Y <skill> when you kill an enemy" (or on attack), then cast a multi-summon (blood_skeleton, Druid Harvesters/Bear Companion) | The pets cast that skill on kill (chance divided by the pet type's divisor); no crash on summoning. If nothing ever procs, note it (the stat array may not have been found) |
| 0.19.0 | Levels above 255 (bug #17) | A summoning scroll to the Heroic Library / Heroic Duncraig / an arena (Act matching the scroll), or a Mirror Temple key | Portal opens and leads into the area (not a wrong low-numbered level); area loads with no crash; cast town portal there and come back through it |
| data | Cow Portal (bug #19) | Wirt's Leg + Tome of Town Portal in the cube in Act 1 town | Red portal to the Moo Moo Farm |
| data | Skill tooltips (bug #9) | Hover skills in every tree tab (and with synergies) | No assert/crash; synergy block starts "<Skill> Receives Bonuses From:" with the skill's name; values show. Note any skill whose tooltip looks empty or wrong |
| 0.21.0 | Median teleport range (slot 179; was on 173, which mysterious_companion_skill also used) | Druid harbinger (or Sorceress Teleport, Assassin blink): click far away, then close by | Lands at most the skill's range away along the line to the click (harbinger ~25); close clicks land on the spot; no teleport where Median forbids it; monsters with teleport skills still blink |
| 0.18.0 | Layered self buffs (slot 174) | Druid Steady Shot (sk1296), frigid_nova, lionheart_2, brace_for_impact, lunar_assault_2 | Buff state and its bonuses show; Steady Shot's stacking counter grows per cast and its proc state turns on at the cap; no crash |
| 0.21.0 | land_of_the_dead (slot 180) | The skill (or an item granting it) | Timed effect around the caster keeps firing; its bonuses apply |
| 0.17.0 | queen_of_blades (slot 190) | Assassin: queen_of_blades (level 25) near a pack of monsters | Buff state on; every few frames all enemies within range take lightning plus weapon damage; damage numbers grow with the weapon; buff and pulses end when the state runs out; no crash |
| 0.16.0 | Median item auras (slot 184) | Equip Majesty, Penumbra, Clockwork Slippers or The Pathless | Their aura's state icon shows; its bonuses apply (character sheet); no crash when equipping/unequipping or changing areas |
| 0.3.0 | Multi-summon, slot 172 | Necromancer: blood_skeleton (or Barbarian guardian_spirit) | Several pets per cast, up to the cap; at the cursor when in range |
| 0.2.0 | Barrage, slot 176 | Necromancer: catapult_shot | Missiles land at random spots around the target |
| 0.2.0 | Missile row, slot 177 | Necromancer: death_ripple_2 (or Assassin CountessFirewall) | A row of missiles across the aim line |
| 0.4.0 | Strike burst, slot 178 | Necromancer: torment (or Assassin crucify_2, Barbarian earthquake_2) | Target is hit, then missiles burst from it and fly past |
| 0.5.0 | Missile at target, slot 185 | A flamestrike skill | One missile appears on the cursor spot |
| data | Storm skills -> D2R Armageddon | Druid frigid_domain, Sorceress overheat, Barbarian thundergod | Timed effect around the caster that keeps firing |
| next | Item generation hooks installed | Start the game, run `mxl` | A line `item generation on: class lock (0x36bc50) hooked, ethereal (0x442d60, 0x3d3510) hooked, sockets (0x441fc0) hooked, dyes (0x3710d0) hooked` with the counters; a mismatch names the entry that differed |
| next | Class lock (items-xp.md section 5) | Make one of the 14 class-conversion recipes (cube recipe with `properties_422`) so a unique is locked to one class (stat 492 = class + 1, look at the `mxl` counter `class lock denied`); try to wear it on that class and on another | Own class: equips. Other class: the item shows as unusable (red) and cannot be equipped; `class lock denied` counts up. Add `classlock` to `mxl2012-core-off.txt`: every class can wear it |
| next | Ethereal rate (item level 100+) | Kill bosses in a high area (ilvl 100+) and watch `mxl` `ethereal N of M at item level 100+`; read a dropped ethereal item | Roughly 1 in 2 of the items D2R lets through (M) become ethereal: N/M about 0.5; ethereal items have +25% defence or damage (not +50%) and 75% of the base maximum durability (not half + 1); items that were not accepted keep full durability. Off word `ethereal` restores D2R's 5% / +50% / half |
| lane pa-sockets (version not bumped; run `mxl`, the `item generation` line ends `all qualities (0x44356a socket guard, 0x44364c automagic table) patched`) | **Sockets and automagic for every quality** (Median `qualities.txt` MaxSock / Automagics: magic items roll `rand % 7` sockets, set / rare / unique / crafted / tempered items get the base's maximum, set and unique items get their automagic mod; plugin/src/item_gen.cpp) | Collect rare, unique and magic drops at item level 100+ on socketable bases (`mxl` prints `sockets given N of M rolls (magic ..., set / rare / unique / crafted / tempered ...)`); read a unique's tooltip for the automagic line. Off word `allquals` restores D2R (no sockets from magic up, no automagic on set / unique) | Rare, unique, set and crafted items on a base that can hold 6 sockets arrive with 6; magic items with 0-6 evenly; uniques and sets show an innate automagic mod. Seen by check only (harness generator, not a real drop); a set item was never produced by the harness |
| next | Socket roll (quality 1-3 items) | Collect 40+ white, low and superior drops (`mxl`: `sockets given N of M rolls`) | About 6 of 7 socketable bases are socketed (1-6 sockets, clipped to what the base holds) instead of D2R's 1 in 3. Off word `sockets` restores D2R's |
| next | Dye paint in HD (bug #11) | Use a mystic dye on a body armour, a weapon and a shield; look at the inventory, the ground and the character; also dyes 16-21 (the stat is 5 bits signed) | The item sprite and the worn item change colour (`dyed colours drawn` grows). If dyes 16-21 do nothing or show colour 0 widen the stat's Send Bits to 6. Off word `dyes` restores the uncoloured look |
| later | Multiplayer (TCP/IP through D2RLoader) | Host + join with the same mod and plugin version | Both in game; new skills work for the joiner |

### Level sweep (lane levels, 2026-10-28)

`tools/level_sweep.py` reaches and walks every levels.txt row (docstring: how; result: [level-sweep.md](level-sweep.md), generated).
One batch per slot lock, e.g. `MXL_RUN=levels MXL_SLOT=N MXL_RUNS=<R>\mxl2012-runs py -3 tools/level_sweep.py run --act 1 --out <dir>`,
then `report --out <dir1>,<dir2>,... --md docs/level-sweep.md` (batches merge in `--out` order: a later batch's row replaces an
earlier one's). Done (lane levels): Normal, all 137 rows (acts 1-5, slot 3).

Lane levels2 (2026-10-28, slots 3 and 4, evidence `mxl2012-runs/levels2/`; batches `n-redo`, `n-routes` (the route phases, several
launches into one folder), `h-act1`-`h-act5`, `nm-act2`/`nm-act3`/`nm-act5`). The report is made from lane levels' `n-act1`-`n-act5`, then
`n-redo`, `n-routes`, the Hell and the Nightmare batches.

| Part | Result |
|---|---|
| Normal again for 14, 18, 55, 95, 98 (`--redo`) | All reached, 0 asserts, 0 crashes. The character (level 120 Barbarian, no gear) dies about 7 times in each. 95 Disused Fane and 98 kill it at the entry (28 and 14 monsters there): a level with walked 0 and 2+ deaths is **killed on arrival** (`K` in the report) and is judged on the level load only (no walk, no automap check). An automap taken on a death screen is now "?" (not judged), and every visit saves an arrival screenshot first |
| Waypoints (`--phases waypoints`) | 40 / 40 ok. Each waypoint level's waypoint object is found (within 150 subtiles: the object hash still holds other acts' objects), walked up to and used; a town is reached by the waypoint travel inside its act. Pandemonium 2 (134) has no waypoint object, as Median 2012 on 1.13c (bugs.md #13) |
| Town-portal scrolls (`--phases tp`) | The scroll is right-clicked in the backpack, the portal entered to town, the town end entered back. Ok: 2, 13, 14, 41, 59, 60, 76, 84, 104, 110, 125, 126, 127, 133, 135; 136 Pandemonium Finale opens no portal, as it must (levels.txt `PreventTownPortal`). Not judged (the character died before the scroll or respawned away from the portal): 18, 65, 95, 116. **134: the portal in town back into Pandemonium 2 ends the game, 3 of 3 runs (bugs.md #392)** |
| Red portals (`--phases portals`) | 117 Frozen Tundra -> 127 Infernal Pit ok. 111 -> 125 and 112 -> 126: no class-60 portal object in 120 s of walking (the portal is not a preset: objpreset.txt has no row for class 60, so it exists only once its room is loaded). Redo with `--portal-search 480`: still none, but the character died 14 times (111) and 35 times (112) and explored only 5-6 cells, so both are **not judged** (a search cut short by 2+ deaths); they need a stronger or geared character. Lane levels' Normal visits of 111 / 112 saw no portal either |
| Cow Portal (`--phases cow`, cubemain row 2: Wirt's Leg + Tome of Town Portal, op 28) | Ok in Normal and Hell: in the Rogue Encampment the two items are picked up and put into the opened cube, Transmute is clicked, a class-60 portal to 39 appears and entering it arrives in the Moo Moo Farm. Set-up (harness): Baal killed in that difficulty (`quest 40 0 set`, the condition of the 1.13c and D2R handler), a cube in the backpack |
| Hell, 30 levels (`--difficulty hell`) | 30 / 30 reached, 0 asserts, 0 crashes, 0 hangs. 47 Sewer 1 A, 60 and 131 Throne of Destruction kill the character on arrival |
| Nightmare, 11 levels (`--difficulty nightmare`) | 11 / 11 reached, 0 asserts, 0 crashes, 0 hangs. 55 and 60 kill the character on arrival |

How players reach Pandemonium 1, 2, 3 and the Finale (133-136) in Median 2012: **no route in its data.** No levels.txt `Vis` points to them
(133's `Vis0` 17 is its exit to the Burial Grounds); the vanilla Uber cube rows (`pk1`+`pk2`+`pk3`, `dhn`+`bey`+`mbr`) are absent and those
item codes appear in no Median file; no portal object, skill or missile leads there; no ds1 preset portal. 134's `Waypoint` 17 is the
Canyon of the Magi's (46) number copied. The repack's PlugY.ini turns on PlugY's Uber quest, but the cube rows it needs are not in the mod. The sweep reaches
them only by harness (`level <id>`): the plan lists no entry route for 133-137, and nothing was invented. Question for the owner.

Harness and tool fixes found by these runs: `enter` read the portal after its use handler had freed it (garbage id and destination, an
`eType == UNIT_OBJECT` assert): it now reads them first. A `move` to a far stale object (another act's waypoint 17,600 subtiles away)
hung the game: objects farther than 150 subtiles are ignored. `set_progression` wrote the 1.x header offset 0x25 (another field in a v105
save), so Hell batches played Normal: it now uses `rc_setup` (byte 0x15). A dead character entering a portal ended the game: the sweep
revives first (`ensure_alive`).

## Confirmed

| What | Notes |
|---|---|
| Bug #251: item levels 100-127 survive Save and Exit and a reload (plugin part `ilvl`) | 2026-10-28, slots 4 and 3, background mode; see "Lane ilvl: item levels 100-127" below |
| Sprint (audit SK7), game check `sprint` | 2026-10-22, Barbarian on slot 2. Median's sprint is its charstats stamina, not code: the check (rewritten by lane checks-robust, 2026-10-23, after the pa2-stats stamina step) asserts Median's rules exactly, per frame, from `state` replies that carry the server frame and the raw stamina: a run from full stamina (50 points = 12800 raw) loses exactly 120 raw per frame (RunDrain 60 x2) and regenerates nothing, 107 frames = 4.3 s, then is forced back to walking; walking from empty gains exactly 37 raw per frame (75% of max / 256 = 50; D2R's own step is 25); standing gains exactly 50 raw per frame and refills 0 to 50 in 253 to 261 frames (10.1 to 10.4 s); the run is about 1.3 times the walk speed (data 1.40, 15% allowed); a run starts again at 2 points of stamina (no cooldown timer); state 136 fills the bar; the R key gives one run and one walk (the toggle is the character's own setting and is put back). Rule: D2Sigma `0x100a1f90`, see the pa2-stats section |
| Bug #21 fix (0.33.3): barby loads; Akara, buying, moving items, potions, shared stash tabs work on barby and dewid | 2026-10-07. The stash-link check (bug #20) still fails once at the first join of a session |
| Plugin 0.33.0 loads; every engine change installs (Phase 4 verification, 2026-10-06 20:22, launched to the menu) | mxl2012-core.log: states fix on (73 sites), level types/automap on (10 Median row ranges), calc codes on (incl. itemstat, tabpoints), 15/15 skill functions, item spells on, 13/13 missile hits (no FAILED), mana costs on. d2rloader.log: only the known startup checks (state count, level-type names, both handled by the plugin); clean shutdown, no crash report |
| Vendors stock Median's items (bug #8) | |
| Skill points can be spent; 8-tab skill tree; skill icons | |
| Potions (bug #10) | |
| Flamefront needs Molten Core first (bug #13) | Median's rule, not a bug |

## Automated smoke run (tools/game_ctl.py)

`py -3 tools/game_ctl.py smoke` launches D2RLoader (windowed, resized to a 1600x900 client area), clears the
calibration screens and intro, plays the selected character (difficulty dialog: Normal), takes window-only screenshots
(never the desktop) of town, the character sheet (C), the skill tree (T) and its tabs, the inventory (I), runs the
console command `mxl`, then Save and Exit and re-enter (save/reload check), stops the game and scans the logs. Output
goes to `<runs>\<run>\` (`report.md`, PNGs, `logscan.txt`, `game_ctl.log`); look at the PNGs
yourself. Single steps: `start`, `shot NAME`, `key KEY..`, `click FX FY`, `console CMD`, `logscan`, `stop`.
`MXL_RUN=<name>` pins the run folder (instead of the shared `runs\current.txt`), so two lanes do not mix.

Covers: startup log (known asserts only), the skill tree look row, inventory and character-sheet panels, the plugin
status line, and the save/reload basics. Does not cover combat, vendors, stash, cube or anything needing a walk.

Slot locks live in the machine-local `shared_lock_dir` (docs/setup.md) independently of `MXL_RUNS`. `MXL_LOCKS` explicitly overrides the lock folder and is printed when set; use the shared folder for coordinated game runs.

### Background mode (default): the user's mouse, keyboard and focus stay free

Unattended runs must not steal the real cursor, send global keys or take the foreground. Background mode is the
default; `--foreground` (anywhere on the command line) or env `MXL_INPUT=sendinput` selects the old SendInput +
SetCursorPos + SetForegroundWindow path (it needs the window in front and the user's hands off the PC).

**Lanes and unattended runs must never use `MXL_INPUT=sendinput` / `--foreground`.** The default background path of
`game_ctl.py` (and so `game_checks.py` and `parallel_smoke.py`) calls none of `SetForegroundWindow`, `SetActiveWindow`,
`SetCursorPos`, `keybd_event`, `mouse_event` or `SendInput`: the loader is started with `SW_SHOWNOACTIVATE`, and the game window is sent to the bottom of the z-order without activation. Background mode never restores a minimized window: resize and capture fail explicitly if it is minimized, because D2R can activate itself on restore. `tools/test_game_ctl_nofocus.py` checks these paths and the forbidden calls. Focus still depends on the plugin harness (`WS_EX_NOACTIVATE`, below); the loader may discard the startup show flag. This change has not yet been verified in a game run.

It needs the plugin test harness (plugin/src/testharness.cpp, off in normal play): create an empty
`mxl2012-testharness.txt` next to `mxl2012-core.dll` (`...\mods\mxl2012\d2rloader\plugins\`) before the game starts and
delete it afterwards. With it on, D2R takes no mouse, modifier state or focus from the real devices at all. Without
it the background mouse and console are unavailable (keys and screenshots still work).

What was measured (D2R 3.3.0 build 93847, D2RLoader 1.3.1, game window behind the user's windows on another monitor):

| Input | By window messages alone | How it works in background mode |
|---|---|---|
| Keys: Esc, Enter, letters (I, C, T), digits, F-keys, arrows | works (`PostMessage` WM_KEYDOWN/WM_KEYUP with scancode lParam) | same, no harness needed |
| Text typing (names) | WM_KEYDOWN + WM_CHAR, same path as keys | same (typing a character name is untested in game) |
| Mouse move / click / right click | does NOT work: D2R reads the position with GetCursorPos and the buttons with GetKeyState and ignores WM_MOUSEMOVE / WM_xBUTTON lParam, with or without focus | plugin harness: game_ctl writes a virtual cursor and button state into a shared block, the plugin answers GetCursorPos / GetKeyState from it, and the WM_ messages are posted as well; hover and ImGui menus work |
| Ctrl+` (developer console panel) | does NOT work (the console is a D2R input action; modifiers from posted messages are ignored, also with real focus) | plugin harness runs the line through D2RCore's `ExecuteConsoleCommand` on the UI thread; the panel stays closed |
| Modifier state (Shift/Ctrl/Alt) | not seen by D2R | virtual state in the shared block (GetKeyState: the win32u syscall and, since lane uifix, the game exe's `GetKeyState` import, which mostly answers from the thread's cached key state without the syscall; before that a Ctrl-click was a plain click). `click(..., mods=("ctrl",))` |

Other things the harness keeps off the user's desktop: D2R's own `SetCursorPos` (called once at start in a normal run)
and `ClipCursor` calls become no-ops (otherwise the real cursor jumps and is confined to the game window),
`SetForegroundWindow` and `SetActiveWindow` from the game do nothing, and top-level windows get WS_EX_NOACTIVATE so the
game window is never made the foreground window at launch (without it D2R sits in front for about a second, whatever
the STARTUPINFO show flag says: D2RLoader relaunches itself and the flag is lost).

Capture: `PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT)` of the game window, cropped to the client area. It returns the
D2R DX12 window live (animations move) while it is behind other windows or on another monitor, and never touches the
desktop. (`PW_CLIENTONLY` returns black.) A minimized window cannot be captured: the script refuses, so the window must
stay un-minimized. D2R keeps rendering at 60 FPS when not in front; no D2R option had to be changed.

Found 2026-10-21 (cain-menu lane): the game starts in legacy (2D, 4:3 pillarbox) graphics here; `G` (`press_bg("g", hold=0.1)`, a few
seconds after the game is loaded) switches to HD. In both modes a background click on an NPC (hover works and shows the name) walks the
character next to it but the NPC menu does not open (the menu builder `0x1147a0` is never called; calling the opener `0x1141d0`
from the plugin does call it but draws nothing, and `0x10e6e0` crashed the game), so NPC menu checks still need `--foreground`.
Also: `stop()` returns early when no game is running and then leaves `mxl2012-testharness.txt` in place.

Limits: the output of D2R / D2RLoader commands (cheats, `help`) goes only to the console panel, so it cannot be read in
background mode (the effect of a cheat shows in game; the plugin's own `mxl` output is written to
`mxl2012-testharness-console.txt` and returned by `console_text()`). While the harness is on the game ignores the real
mouse and modifiers (no manual play). `mxl2012-testharness-trace.log` (rewritten every 3 s) lists the Windows input calls D2R
makes and who calls them, for finding what else needs faking.

Status 2026-10-21: the full smoke passes in background mode while the user worked on the same PC: the real cursor
never entered the game window, the game window was never the foreground window (sampled every 25 ms), and D2R's
`SetCursorPos` never reached the system.

### Parallel slots: up to five games at once (tools/game_slots.py, tools/parallel_smoke.py)

A slot is a full copy of D2R 3.3 build 93847 with D2RLoader and the mod, its own save folder and its own run lock.
Every `game_ctl.py` command takes `--slot N` (or env `MXL_SLOT=N`; there is no default slot, `game_slots.require_slot`
refuses anything but 1 to 5) and then only ever touches that slot's process and window.

| Slot | Game folder | Saves (`Saved Games\Diablo II Resurrected\mods\...`) | Loader | Lock | Harness words |
|---|---|---|---|---|---|
| 1 | `C:\Program Files (x86)\Diablo II Resurrected` (the owner's Battle.net install, D2R 3.3.93847 with D2RLoader; `MXL_SLOT1_DIR`) | `mxl2012-s1` | `D2RLoader.exe` | `game.lock.1` and the legacy single `game.lock` | `tag=s1` |
| 2 | `D:\D2R-93847` | `mxl2012-s2` | `D2RLoader-s2.exe` | `game.lock.2` | `volserial tag=s2` |
| 3 | `D:\D2R-93847-s3` | `mxl2012-s3` | `D2RLoader-s3.exe` | `game.lock.3` | `volserial tag=s3` |
| 4 | `D:\D2R-93847-s4` (`MXL_SLOT4_DIR`) | `mxl2012-s4` | `D2RLoader-s4.exe` | `game.lock.4` | `volserial tag=s4` |
| 5 | `D:\D2R-93847-s5` (`MXL_SLOT5_DIR`) | `mxl2012-s5` | `D2RLoader-s5.exe` | `game.lock.5` | `volserial tag=s5` |

**Slots 4 and 5** (owner-approved 2026-10-28, GPU permitting) are copies of slot 2's folder made by the coordinator and
work exactly like slot 3: own save folder, own renamed loader (made by `setup`), own lock `game.lock.4` / `.5` in the shared
lock folder (other users of the lock folder do not know these slots and never take those locks: harmless),
the same harness words. The harness words per slot: `tag=sN` is the only per-slot value (window title
`Diablo II: Resurrected [sN]`, so each slot's window is told apart); `volserial` has no value: the plugin reports the
volume serial of `C:` (where the Battle.net session cookie was made) for every slot off `C:`, so slots 2 to 5 all send
the same serial and need nothing distinct. Both words are made by `game_ctl` from the slot number, so 4 and 5 need no
change in the plugin. **A slot whose folder (or its `D2RLoader.exe`) is missing** is shown as
`slot N: MISSING (... does not exist)` by `game_slots.py status`; `setup` reports it (exit 1 when named), and `lock`,
`install`, `install_mod.py`, `game_ctl.py`, `game_checks.py`, `slot_share.begin`, `d2r_game.py`, `parallel_smoke.py`,
`lane_setup.py --cache-from-slot` and `release_install.py install` refuse it with `game slot N is missing: ...` before
anything is locked or written (`game_slots.require_present`). The defaults (`setup` / `install`, `install_mod.py --slot
all`, `parallel_smoke.py`) take the slots of 2 to 5 that exist. After copying, the coordinator runs
`py -3 tools/game_slots.py setup 4 5` (or just `setup 4`), then `status`.

**Slot 1 is the PC owner's own game** (approved by the owner on 2026-10-28 for this project's tests; another mod uses it
too, with folders listed in `protected_mod_folders` / `protected_save_folders`, which we never touch). It has exactly the safety of slots 2 to 5 (lock held
by `MXL_RUN`, our `mods\mxl2012` and `mxl2012-s1` only, `d2rloader\config` snapshotted and restored by
`slot_share.py`, background input only) plus:

- **The owner's own game is never touched.** `game_ctl start` refuses while any game process runs in the slot folder that
  this run did not start (the owner playing, by Battle.net or D2RLoader, or another mod's run), and for such a game
  `game_pids()` is empty, so no command attaches to it, sends it input, captures it, closes or kills it
  (`game_slots.foreign_game`; ours is recognised by `<RUNS>\slot-share-s1\launched.json`, written right after our
  launch with the loader's PID and removed by `stop`; it counts only while that loader is still running, so a marker of a
  crashed run never claims a later game). Limit: a game the owner starts *while* our run holds the slot is not told apart from ours
  (both are processes in the same folder); the owner should not start the game while `game.lock.1` is held
  (`game_slots.py status` shows it).
- **No loader copy.** Runs use the plain `D2RLoader.exe`; `setup 1` writes no `D2RLoader-s1.exe`
  into the owner's folder. No `volserial` harness word (the game runs from the drive its Battle.net session was made on).
- **Program Files and writes.** The folder may refuse writes to a user without administrator rights. Nothing here ever
  elevates or retries another way: `game_slots.need_write` checks the target first (an existing file is opened for
  writing and closed, no byte or time stamp changes; a folder gets a probe file removed at once; never above the slot
  folder) and the tool ends with `no write access to <path> ... ask the PC owner to give this user write access to that
  folder, or use slot 2, 3, 4 or 5`. `install_mod.py` checks `mods\mxl2012` before it changes anything; `slot_share.begin`
  checks `d2rloader\config` (folder and every file) and `mods\mxl2012` before the snapshot, so a run that could not be
  restored never starts; a write refused later (install half way, restore) ends with the same message (restore: the
  snapshot and the lock stay). Python has a manifest, so Windows does not redirect its writes to the VirtualStore.
  Not checked yet on the game PC which of these writes the folder allows (the ACL was not read from this lane).
- **Only by name.** `game_slots.py setup` / `install` and `install_mod.py --slot all` mean slots 2 to 5, those that exist
  (`game_slots.DEFAULT_SET`, `present_set`); `parallel_smoke.py` defaults to the same. Slot 1 runs only with `--slot 1` /
  `MXL_SLOT=1`. `release_install.py` keeps refusing slot 1 (it would make
  `C:\Program Files (x86)\Diablo II Resurrected.release-backup` next to the owner's game, and a player install there is
  the owner's to make). `lane_setup.py --cache-from-slot` takes 2 to 5, never 1. `d2r_game.py` (read-only CASC reads) accepts slot 1.

Set up (setup.md has the robocopy): `py -3 tools/game_slots.py setup` writes each slot's `modinfo.json` savepath (both
copies, inside `mods\mxl2012` only), makes the save folder and the renamed loader copy when it is missing (it never
edits the slot's `d2rloader\config`: see "Sharing slots with another mod" below); `status` shows folders, running processes and locks; `install` / `install_mod.py --slot all`
installs the built mod into those of slots 2 to 5 that exist (the data is built once and copied; `--slot N`, `--savepath` for one; slot 1
only with `--slot 1`). The plugin DLL comes along with the install.

Locks are directories in the machine-local `shared_lock_dir` (shared with another mod's tools): `game.lock.N`. Slot 1 also honours the
legacy single `game.lock`: either folder held means the slot is held (a hand-made
one without `owner.txt` too), and taking slot 1 makes both (if the second appears in between, ours is removed again);
releasing removes both. `game_ctl start` takes the lock of its slot (owner file `owner.txt` with the run name
and PID; a lock whose owner PID is gone is replaced) and `stop` releases it. A lock made by hand (no `owner.txt`) is
taken to mean "the caller holds it" and is never removed by `game_ctl`. `game_slots.py lock N [OWNER]` / `unlock N [OWNER]`
by hand.

**Sharing slots between lanes (2026-10-27).** A lane holds a slot for its whole session with
`game_slots.py lock N <lane>` (a manual lock, pid 0), then runs `game_checks.py` / `game_ctl.py` / `release_install.py`
with `MXL_RUN=<lane>` as often as it needs, then restores the slot and runs `game_slots.py unlock N <lane>`. The runs
inside the session see the lock as theirs and do **not** release it at their end (`release()` keeps a manual lock; only
`unlock N` removes it), so no other lane can move in while a special install (e.g. `release_install.py`) is on the slot.
Before this, each run's end removed the lane's lock and another lane took the slot mid-session (slot 3, lanes sounds-bin
and quick-cast). Hold the lock only as long as needed: others are waiting.

### Sharing slots with another mod (tools/slot_share.py, lane slots, 2026-10-28)

Slots 1 (`C:\Program Files (x86)\Diablo II Resurrected`, the owner's game), 2 (`D:\D2R-93847`) and 3 (`D:\D2R-93847-s3`) are shared with another mod: its runs may come
at any time, on the same `game.lock.N` (`shared_lock_dir`). The two mods sit side by side in the slot
and must not see each other.

**Rules**

1. Only with the slot lock held (`game_slots.py lock N <lane>`, every command with `MXL_RUN=<lane> MXL_SLOT=N`).
2. Ours: `<slot>\mods\mxl2012\` and `Saved Games\Diablo II Resurrected\mods\mxl2012-sN\`. Never written: the `protected_mod_folders`,
   `mods\MedianXL\`, the `protected_save_folders`, the game files. `install_mod.py` refuses any mod name but `mxl2012`, a slot
   not locked by `MXL_RUN` and a running game.
3. Shared, restored after every run: the game-wide `<slot>\d2rloader\config\` (all files). No tool of ours edits it
   outside a run; a run changes it only between snapshot and restore.
4. The mod is picked per run on the loader's command line (`D2RLoader-sN.exe -mod mxl2012`). `default_mod` stays
   as it is.
5. Plugins load only from the active mod's folder: ours from `mods\mxl2012\d2rloader\plugins\`, the other mod's
   from its own folder. The global `<slot>\d2rloader\plugins\` and `patches\` (they load with *every*
   mod, `allow_global_extensions = true`) must stay empty: a run refuses to start when they hold anything, or when a
   `mxl2012-core*` sits in another mod's folder.

**What a run touches in the slot** (found by reading the tools and D2RLoader 1.3.1's config and log on slot 2):

| Shared state | Who changes it | How a mxl2012 run handles it |
|---|---|---|
| `d2rloader\config\d2rloader.toml` `[d2rloader] default_mod` | the old `game_slots.setup` (set `mxl2012` for good); D2RLoader's own options (gear, Default Mod) | not edited at all: `-mod mxl2012` on the command line |
| same file, `launch_arguments` (`"-w -txt"`, the other mod's) | the old `release_install.py` (set the release's) | D2RLoader puts them **in front of** our command line words, so words already there are not passed again; a run that must not have one (release run without `-txt`) sets the line for that run only, inside the snapshot |
| same file, as a whole | D2RLoader rewrites it at every start ("Configuration synchronized"; same bytes, new mtime) | snapshot + restore (bytes and mtime) |
| same file, `[d2rcore.stash] add_shared_tabs`, `[d2rloader.developer] enable_console` | nobody of ours | `add_shared_tabs = 7` is in **our mod's** `mods\mxl2012\d2rloader\config\d2rloader.toml` ("Active mods can override these"; the log shows `mod.toml.d2rcore.stash.add_shared_tabs`); the console setting is game-wide and left as it is |
| `d2rloader\config\input-bindings.toml` | every plugin stores its hotkeys there on registration (`mxl2012-core/...` next to other plugins' entries); `install_mod.py` migrated our old hotkeys in it | snapshot + restore; `install_mod.py` no longer edits it on a slot |
| `d2rloader\config\debugsettings.json`, `imgui.ini` | the game / D2RLoader's ImGui while running | snapshot + restore |
| `d2rloader\plugins\`, `d2rloader\patches\` (global extensions) | nobody (empty) | run refused if not empty |
| `mods\mxl2012\...\mxl2012-testharness.txt` (harness words `volserial tag=sN`: the Battle.net cookie fix and the window tag) | `game_ctl` start/stop | ours, inside our mod folder; the volserial fix lives in our plugin, so a run of ours without our plugin has none (below) |
| `d2rloader\logs\d2rloader.log`, `<slot>\blz-log.txt` | rewritten by every start (both projects) | not restored: run output, read by each run for its own start only |
| `<slot>\dxdiag.txt` | rewritten by a dxdiag process D2R starts in the background (about 12 s after launch) | not restored (same for the other mod's runs) |
| `d2rloader\data\compiler\` (base compiler snapshot of D2R's own tables) | D2RLoader, only when missing or after an update | not touched by us; shared cache of game data only |
| `d2rloader\crashes\` | a crashing game | new reports stay (they are evidence) |

**How (tools/slot_share.py)**

- `game_ctl.py start` (so also `game_checks.py` and `parallel_smoke.py`): after the lock, `slot_share.begin()` copies
  `d2rloader\config\` to `<RUNS>\slot-share-sN\snapshot\` with `snapshot.json` (sha256, size, mtime per file); a
  snapshot still pending from a killed run is restored first. Then the loader starts with `launch_args()`.
- `game_ctl.py stop`: once the slot's processes are gone, `slot_share.end()` writes every changed file back from the
  snapshot (bytes and mtime), deletes files and folders the run created there, compares again and only then drops the
  pending snapshot (`last-restore.json` lists what the run had changed). Only then is the lock released; when the
  restore fails the lock stays.
- Failure and kill: a failed launch restores at once; `game_slots.py unlock N` restores a pending snapshot before it
  removes the lock (and keeps the lock while a game still runs); `slot_share.py restore N` does it by hand.
  `game_slots.py status` / `slot_share.py status N` show a pending snapshot.
- `MXL_RUN=<lane> py -3 tools/slot_share.py bootcheck N`: starts the loader minimized with no window, focus or input
  calls, waits for the log's mod mount, kills that launch, restores and verifies. `scan N OUT.json` and
  `compare A B` list every file of the slot (size, mtime) for a before/after report.
- Tests: `tools/test_slot_share.py` (fake slot folders: restore byte for byte, refusal without the lock or while the game
  runs, restore after a killed run and on unlock, plugin refusals, launch arguments, `setup` and the placeholder install
  leave the shared files and the protected mod folders alone).

**Live check (slot 2, 2026-10-28).** Placeholder mod `mods\mxl2012` (modinfo.json only: no tables, no plugin) installed
with `install_mod.py --slot 2 --placeholder`, then `slot_share.py bootcheck 2` three times (the first still passed
`-w -txt` itself). d2rloader.log:

```
D2RLoader command line: D:\D2R-93847\D2RLoader-s2.exe -mod mxl2012
Active mod:
  | name                                             | mxl2012                          |
  | modinfo.savepath                                 | mxl2012-s2/                      |
  | d2rloader.default_mod                            | <other mod>                      |
  | d2rloader.launch_arguments                       | -w -txt                          |
D2R command line: D:\D2R-93847\D2RLoader-s2.exe -w -txt -mod mxl2012
  [SCAN]       mod plugins: D:\D2R-93847\mods\mxl2012\d2rloader\plugins
  [SCAN]       global plugins: D:\D2R-93847\d2rloader\plugins
  [CASC]         paths: data="<default>" mod="mxl2012" locale="<default>"
```

No `[PLUGIN]` line: the other mod's plugin did not load. The first run (passing `-w -txt` itself) logged
`D2R command line: ... -w -txt -w -txt -mod mxl2012`, which is how we know D2RLoader puts the toml's words in front.
With `MXL_LAUNCH_ARGS=-w` the run set `launch_arguments = "-w"` for itself (`D2R command line: ... -w -mod mxl2012`)
and the restore put the line back. Each launch was killed right after the mod mount, about 0.6 s after the start,
before D2R's Battle.net cookie step (a placeholder has no plugin, so no `volserial` fix). After each run:
`d2rloader.toml` "touched (same bytes, other mtime)" or "changed" and restored; sha256 and mtime of all five
`d2rloader\config` files equal the snapshot. Whole slot before vs after (without `Data\`): only
`d2rloader\logs\d2rloader.log`, `blz-log.txt` and `dxdiag.txt` differ. The placeholder and the empty save folder were
removed afterwards. No crash report.

**There is no single-instance check.** The string `DiabloII Check For Other Instances` is in D2R.exe, but no mutex,
event, window or named pipe with that name exists in a running D2RLoader (handles listed with
NtQuerySystemInformation, windows with EnumWindows / HWND_MESSAGE; the harness `diag` mode also logs every named
object, FindWindow and NtTerminateProcess), and a second D2RLoader in another folder starts fine next to the first.
What killed a copy of the game on another drive was something else, found with the harness `diag` mode:

- D2RLoader reads `%LOCALAPPDATA%\Blizzard Entertainment\ClientSdk\cookie.bin` (the Battle.net session record that
  proves the 30-day online check) at the "frontend launch" startup step and decrypts it (Botan CryptoBox) with a key
  that is `base64(SHA-1(...))` of data including the **volume serial number of the drive the loader runs from**
  (`FUN_1419ed830`: `GetModuleFileNameW` + `GetVolumeInformationW`). The cookie was written by the install on `C:`;
  from `D:` the key is another one, the integrity check fails, `Botan::Decoding_Error` is thrown and nothing catches
  it: the process dies with an `APPCRASH` (exception 0xe06d7363) about 8 s after the launch, no crash report. Without
  the cookie D2R shows the "not been online in the last 30 days" dialog (OK quits), so hiding it is no way out.
- The harness word `volserial` makes `NtQueryVolumeInformationFile(FileFsVolumeInformation)` report the serial of
  `C:` (read at load), so the key matches and the cookie decrypts. It also refuses every write open of `cookie.bin`
  (the user's real session file is never rewritten by a test instance). Slots on `C:` need no word.
- Tools that look for "the" game by name would still find a test instance. The old `game_ctl.stop` closes the first
  window titled `Diablo II: Resurrected` and then kills every `D2RLoader.exe`: a lane on the old tools closed or
  killed the other lane's game (seen: slot 2 and 3 games ended cleanly or silently at the moment the slot 1 lane
  stopped; with the renamed loader and the tagged title the same two games ran through while the other lane's game
kept running). So slots 2 and 3 run a renamed copy of the loader (`D2RLoader-sN.exe`, made by `game_slots.py setup`) and
  the harness word `tag=s2` renames the window to `Diablo II: Resurrected [s2]`; `game_ctl` finds its window by process
  and accepts the tagged title. Slot 1 is the plain `D2RLoader.exe` / `Diablo II: Resurrected` as before.

The harness block is per process: `Local\mxl2012-testharness-input-<game PID>` (plugin 0.46.0 as released uses the one
shared name `Local\mxl2012-testharness-input`, which `game_ctl` still falls back to, fine for a single instance such as
slot 1). The console output file `mxl2012-testharness-console.txt` and the trace log live in the slot's own plugin folder.
`mxl2012-testharness.txt` is a list of words written by `game_ctl start` (env `MXL_HARNESS_WORDS` overrides it): `volserial`,
`tag=NAME`, `nocookie` (hide cookie.bin: only for experiments), `diag` (log named objects, file opens, C++ exceptions
and process exit to `mxl2012-testharness-diag-<pid>.log`, plus the cookie record and CryptoBox input of D2RLoader 1.3.1).

`py -3 tools/parallel_smoke.py [--slots 1,2,3,4,5] [--name N]` takes the locks (a slot whose lock is held is skipped),
runs `game_ctl.py smoke --slot N` for each with `MXL_RUN=<N>-sN`, staggered by 4 s, samples the real cursor and the
foreground window every 25 ms (`tools/input_watch.py`: stops all games when a test instance becomes the foreground
window or the cursor teleports into a game window and stays), samples CPU / RAM / GPU every 3 s
(`tools/resource_sample.ps1`, per process, GPU through the Windows GPU Engine counters) and writes
`parallel-summary.md` into the run folder. Windows cascade (`100 + 60 (N-1)`, `60 + 40 (N-1)` on the primary monitor,
client 1600 x 900) and are sent to the bottom of the z-order at launch.

Results 2026-10-21 (RX 9070 XT, 32 logical cores, 64 GB; the user worked on the PC meanwhile):

| Run (run folder in `<runs>`) | Slots | Steps passed | Wall time |
|---|---|---|---|
| `par-3way-2` | 1, 2, 3 at once | 18/18, 18/18, 18/18 | 212 s (per slot 203 / 206 / 211 s) |
| `par-3way-1` | 1, 2, 3 | 18/18, 18/18, 0/1 (slot 3's files were being replaced by an install at that moment: that run's own fault) | 207 s |
| `par-2way-9`, `par-2way-8`, `par-2way-7` | 2, 3 | 18/18 each, all three runs | 206 s, 209 s, 209 s |

The 18 steps per slot are the whole smoke: start, menu, create or enter the character, the plugin `mxl` command, the
character sheet, the skill tree and its 8 tabs, the inventory, Save and Exit, reload (`report.md` and the PNGs of each
slot are in `<run>-sN\`; the three games show their own town and panels).

Real mouse and focus (25 ms samples, `input-watch.json`): in the 3-way run the cursor stayed at (2215, 466) for the
whole 212 s (before = after, range x 2215..2215, y 466..466, the user was away), 0 teleports into a game window, a
game window was the foreground window in 0 samples. In the runs where the user kept working (par-2way-7, 1,594 moves,
x 10..3781, y -945..1439) the same: 0 teleports, 0 foreground samples. The plugin trace of every game: D2R called
`SetCursorPos` 6 times, `ClipCursor` 9-11 times, `SetActiveWindow` once, `SetForegroundWindow` never, all answered by
the harness (none reached the system). With the windows on the primary monitor a resting cursor can lie under a game
window rectangle (counted separately, not a violation); an early version of the watcher aborted on that and on a hand
sweeping through a window, hence the "teleport" rule.

Load, 3 games at once (par-3way-2): machine CPU 26% mean, 57% peak of 32 logical cores; free RAM down to 18.0 GB (about
33-38 GB with no game); GPU engines (all processes, summed) 53% mean, 99% peak. Per game (par-2way-9, two games): about
1.5 cores on average and 6.6 cores at the startup peak (the txt compile), 6.6-7.2 GB RAM, 4.1-4.5 GB VRAM, GPU 17-21%
mean (28-57% peak). The RX 9070 XT (16 GB) has room for three; RAM is the thing to watch (about 7 GB per game).

### Test what players get: a release install (tools/release_install.py)

A slot set up by `tools/install_mod.py` is a **developer install**: data from work/mod, the dev plugin, and runs with
`-w -txt` (the slot's shared `launch_arguments`). Players get the **release install**: the D2R-XL 2012 Downloader unpacks the release 7z into
`mods\mxl2012` and the release launch keys have no `-txt` (`launch_arguments = ""` since 0.69.2). A bug a player sees and
a developer install does not (bugs #38 and #45) is checked on a release install:

```
py -3 tools/game_slots.py lock 2 <name>
MXL_SLOT=2 MXL_RUN=<name> py -3 tools/release_install.py install --slot 2     # live stable release, by its own downloader
MXL_SLOT=2 MXL_RUN=<name> py -3 tools/game_checks.py all mxl orbtips allattrtip tooltiptext specialtext --slot 2
py -3 tools/game_slots.py lock 2 <name>                                         # game_checks released it
MXL_SLOT=2 MXL_RUN=<name> py -3 tools/release_install.py restore --slot 2      # the developer install comes back
```

A release candidate that is not published yet (the hand-copied alpha of `tools/cut_alpha.ps1`) goes in with
`install --slot 2 --package <Out>\D2R-XL-2012-<v>.7z`: its 7z unpacked with 7-Zip into the slot's `mods\` folder (the alpha
notes' Install step 2), launch arguments from the `release-manifest.json` next to it, nothing downloaded; the rest as below.
Its Act 1 smoke on the player path: `game_checks.py all playthrough relp_town` with `MXL_PT_CLASSES=1,4` (`relp_town`: fresh
characters of `MXL_RELP_CLASSES`, default sorceress and barbarian; the character / inventory / skill tree panels, talk to Akara
and Charsi and open their Trade windows, walk out of the camp into the Blood Moor and back, Save and Exit + reload, all by left
clicks; `tools/test_relprep.py` greps it for harness moves).

Release candidate rc1 (lane rc1, 2026-10-29):

| Step | Result | Path | Evidence |
|---|---|---|---|
| Cut, `cut_alpha.ps1 -Tests` from main 04cff24 | PASS (superseded) | build | 131,973,879 bytes, sha256 `6f4d94f2…a48b`, `verify_package.py` OK; kept as `<runs>\rc1\dist-rc1-04cff24`, log `<runs>\rc1\cut-04cff24.log` |
| Cut again from main 5f9e9d9 (HD item pictures of lane hditems, `pot_use` callable by name) | PASS | build | `<runs>\dist-rc1\D2R-XL-2012-0.1.0.7z`, 132,194,351 bytes, sha256 `990d523c11411239eb46fefb6109d04c35f5cf50851ce93731dc9df4ba05b676`; validate 0 errors, 16 plugin unit test suites pass, 3,256 files (469 MB unpacked), 45 D2R byte copies left out; `verify_package.py` OK (same as install_mod.py's folder except plugin and metadata); log `<runs>\rc1\cut.log` |
| `release_install.py install --slot 3 --package …` | NOT RUN | player install | slots 2 and 3 held by other lanes (walls, realpath2; acts3) for the whole wait, 02:21-03:23 |
| `playthrough relp_town`, `MXL_PT_CLASSES=1,4` | NOT RUN | player path | as above |
| `pot_use` (bug #191) | NOT RUN | harness set-up, player drink | as above; on a `--package` install it runs with the dev DLL that `install` puts in (the harness verbs `spawn`, `mcast`, `asserttrace` need it), the data is the package's |

Release candidate rc1 smoke, lane rc3 (2026-10-29, slot 2 locked as `rc2` 03:34-05:08, worktree lane/rc2 at main 08af800, the
checks' code as committed by this lane). Package `<runs>\dist-rc1\D2R-XL-2012-0.1.0.7z` (cut from main 5f9e9d9): sha256 matches
`SHA256SUMS` (`990d523c…b676`). Dev DLL built from lane/rc2 (same PluginVersion as the release, `install` says so). The package is
older than main's HD walls, skill icon and item art merges: those are newer on main and not judged here. Run folders are under
`work/runs/` of the worktree, logs under `<runs>\rc3\`.

| Step | Result | Path | Evidence |
|---|---|---|---|
| sha256 against `SHA256SUMS` | PASS | build | `990d523c11411239eb46fefb6109d04c35f5cf50851ce93731dc9df4ba05b676` both |
| `release_install.py install --slot 2 --package …` | PASS | player install | 7z unpacked into `mods\mxl2012`, launch keys `default_mod mxl2012`, `launch_arguments ""` (+ `-w` for the run), dev DLL same PluginVersion; log `<runs>\rc3\install.log` |
| `playthrough`, sorceress | PARTIAL | player path (field reached by harness `level 2`) | create, kit, kill (6 kills, 570 xp), cube, waypoint, reload, vendor (Charsi sell / buy) PASS; pickup SKIP (no drop), equip SKIP; death PARTIAL (died, then died again on the way to the corpse); `checks-20261029-034651-s2` |
| `playthrough`, barbarian | PARTIAL | player path (field by harness `level 2`) | create, kit, kill (4 kills), pickup (`r04`), cube, death (corpse picked up), waypoint, reload, vendor PASS; equip SKIP (no wearable drop); same run folder |
| `relp_town` first run | PASS (sorceress) / FAIL (barbarian), both overstated or harness | player path | `checks-20261029-034651-s2`: Akara not found and walk out BLOCKED on both; BLOCKED counted as PASS (fixed: now PARTIAL); the character panel shot caught the Loading screen (fixed: waits for the game's bottom bar); barbarian's Save and Exit did not leave the game once (not seen again) |
| `relp_town` rerun with the fixes | PARTIAL, both classes | player path | `checks-20261029-044218-s2`: create, panels c / i / t, Charsi's menu and Trade window, Save and Exit + reload PASS; Akara BLOCKED (`presets 1` answer of a fresh game has no Akara row, the 8-direction search does not reach her); walk out BLOCKED (448-535 s: the click walk stops ~40 units inside the camp's rooms at the palisade, the gate is not found) |
| `relp_npcs` (new, diagnostic) | PASS | harness (`moveto nearest`) | `checks-20261029-050645-s2`: Akara (148) preset, found by the server and in view; Charsi (154) found. Akara is in the town: the BLOCKED above is the check's search, not the game |
| `pot_use` (bug #191), all 10 codes | FAIL (set-up only) | harness set-up, player drink | `checks-20261029-043520-s2`: every drink 0 engine asserts; `yps wms ey9 elx vps hp1 mp1 rvs` used up, `hrb eo7` kept, all as expected. The cure set-up never ran: `spawn gnat1` answered "usage" (fixed: `spawn` takes the monstats row) |
| `pot_use` rerun `MXL_POT_ONLY=yps,wms` | FAIL (set-up only) | harness set-up, player drink | `checks-20261029-043945-s2`: spawn 765 / 417 OK, `mcast` Poison Flash / Ice Lance returned 1 but put no poison / cold state, so the cure is not judged; drinks 0 asserts, used up. One `ptUnit->eType == UNIT_PLAYER` (Units.cpp:4666) during the `mcast` set-up: bug #19's harness spawn assert, not a drink |
| `release_install.py restore --slot 2`, `unlock 2 rc2` | PASS | | "developer install back", lock free |

Screenshots (judged by hand): town, character / inventory / skill tree panels, Charsi's menu and trade window, waypoint panel and
the field show no ERROR strings and no missing text; panel labels, stats and resistances read right. The skill tree shows the
package's older grey skill icons (newer on main). Engine: only the known exit-only pool asserts at Save and Exit
(`s_StatsPool.IsEmpty()` and its followers); no crash files.

Verdict: the package installs and plays the Act 1 start on the player path (create, panels, vendor, fight, cube, waypoint, death,
Save and Exit + reload) for sorceress and barbarian, and bug #191's drinks assert no more. Not covered by this smoke: walking out of
the camp by clicks and Akara's menu (check limits, both shown present otherwise), the antidote / thawing cures.

`install` (slots 2 to 5 only, lock and no running game required) moves `mods\mxl2012` to `<slot>.release-backup` (same
volume), downloads the manifest's downloader (sha256-checked) and runs `--cli install` into the
empty folder like a player's first install. Then it changes only what background checks need, and writes each change to
`<RUNS>\release-install-sN\release-install.json`: the dev build of `mxl2012-core.dll` (the release DLL
has no test harness; it is kept in that folder, `--release-dll` keeps it in for a log-only launch), the slot's own
savepath, and the run's launch arguments (the manifest's `launch_arguments` plus `-w`; the shared toml is not edited:
each run sets them for itself inside the snapshot, "Sharing slots with another mod"). Build the dev DLL of the same
version first (`tools/build_plugin.ps1`); `install` says when its PluginVersion differs from the release's. The checks
read the expected data from work/mod and assets/median as usual. `MXL_GRAPHICS=legacy` runs a whole game_checks run in
legacy graphics (G in town first; `inv_cell` / `shop_cell` give the legacy grid positions, the shop ones are not yet
right: the hover misses on Gheed's shelf).

First run (lane release-install, 2026-10-27, slot 2): releases 0.69.5 and 0.69.6 without `-txt`: `mxl`, `allattrtip`,
`tooltiptext`, `specialtext` PASS, `orbtips` REVIEW with complete tooltips (Gheed's shelf and inventory), also in legacy
graphics (inventory). D2RLoader logs "Compiled 188 tables from TXT ... 38 game, 150 mod" without `-txt` too. The
release DLL alone (`--release-dll`) installs every part including "item text on". Bugs #38 / #45 did not reproduce.

`releasetables` (bugs #42 / #46, lane sounds-bin): the sounds table the game loaded (`mxl` sound guard line `sounds.txt N
rows (D2R-XL 2012 12449)`) has the installed mod's row count, the Median-only `treasuregoblin_neutral_1` (row 12214) is inside
it, d2rloader.log's sound step of this start compiled the mod's `sounds.txt` with that many rows, and the installed
`objtype.txt` files equal work/mod's (D2RLoader compiles objtype in neither mode). To see a player's first start, move
`<slot>\d2rloader\data\compiler` aside before the run (D2RLoader then builds its base snapshot and loads D2R's 11913
sound rows: `releasetables` FAILs and names it; `goblincrash` crashed before 0.69.15 and now passes with the skipped ids
listed, because the `mxl` line says `NOT D2R-XL 2012's table`) and put it back afterwards. Runs 2026-10-27 on
the live release 0.69.8 with this lane's dev DLL (then labelled 0.69.10, 0.69.15 after the merge), no `-txt`: first start (snapshot moved aside) `releasetables` FAIL
"loaded sounds table 11913 rows ... base snapshot built in this start" and the plugin's warning in mxl2012-core.log
(checks-20261027-164906-s3); normal start `mxl releasetables goblincrash denboss` all PASS (checks-20261027-165028-s3). With every sound record
lookup guarded (0.69.15 follow-up, release 0.69.10, slot 3): first start `mxl goblincrash denboss` PASS and no crash,
`releasetables` FAIL by design (checks-20261027-171557-s3); normal start all PASS (`denboss` on the rerun,
checks-20261027-172425-s3 / checks-20261027-173418-s3).

## Harness commands (gameplay without input; plugin/src/harness_cmds.cpp)

World clicks do not register in background mode, so the plugin's test harness (only active while `mxl2012-testharness.txt`
sits next to `mxl2012-core.dll`; never in normal play) has gameplay commands that call the game's own functions. They use
the console mailbox that already carries `mxl`: `py -3 tools/game_ctl.py` / `game_ctl.hcmd("kill nearest 156")` writes
`h kill nearest 156`; the answer lines (`h: ...`, ending in `h: <verb> OK` or `h: <verb> FAIL <reason>`) are appended to
`mxl2012-testharness-console.txt`, and `hcmd` returns `(ok, lines)`. Server-side verbs are queued and run on the game thread
inside the server frame (a hook in `goblins.cpp` calls `HarnessGameFrame` after `0x406550`); the UI thread must not wait
for them (the server frames are driven from it). `menu` runs on the UI thread. A bad pointer inside a verb is caught
(`FAIL crashed`), it does not take the game down.

| Command | What it does |
|---|---|
| `state` | player (id, class, level, life, area, x, y, gold, bank, difficulty, frame), every inventory / cube / equipped item (`code`, `page` 0 backpack 3 cube 4 stash 255 equipped, position, quality, unique index), monsters within 40 (class, mode, distance, NPC flag), objects within 30 (portals are class 59 / 60 / 600 and print `dest=<D2R level id>`), plugin counters (goblins, lockout, tower skips), NPC menu globals |
| `kill <unit id>` / `kill nearest [class]` | the unit-death function `0x44db20(game, victim, player, 1)`, the player is the killer, so the quest kill hooks (`0x515640`) fire |
| `spawn <class> [n]` | `0x4929e0` next to the player (monsters and NPCs, e.g. 156 Andariel, 148 Akara) |
| `interact nearest` / `interact <npc class>` | stands next to the NPC (move `0x491ca0`) and sends the server packet 0x2f (start talking) through the packet handler table `0x1d2a790`: the NPC speaks, quest event 0 runs, the server answers 0x27 and the client opens the menu through its builder `0x1147a0` when the speech is over (up to ~30 s for a first talk) |
| `msg nearest\|<npc class> <message id>` | packet 0x31 (a dialog line ended): quest event 11 (Akara `0x76` = Griswold's Heart) |
| `menu list` / `menu <line>` / `menu cancel` | client side: the open NPC menu's record (`0x2a48830`, 48 x 0x48), line string ids and handler (`plugin@` = a plugin line); `menu <line>` calls that line's click handler |
| `quest <id> <bit> set\|clear\|get`, `quest <id> dump` | quest bits (`0x325c00` / `0x325990` / `0x325c50`) of the game's difficulty |
| `players <n>` | D2R's players setting (`0xe19e0()` then `0xd2f020(setting, n)`): monsters spawned afterwards carry players count `n` (stat 100) and the scaling record of that count; not persistent |
| `tctrace [reset]` | the class lookups of the treasure-class executor (`0x397290`): `calls leveled lastclass lastlevel` (level above 0 only when the monster's level steps the class up) |
| `leash [d]` | the mercenary against its owner: with `d` moves the mercenary `d` sub-tiles from the player (unit move `0x491ca0`); prints both positions, `0x596720`'s owner distance, the Euclidean distance and the mercenary's mode |
| `waypoint <level id>\|n <number>\|all [get\|set\|clear]`, `waypoint open\|tabs\|panel` | the server's waypoint record of the player's difficulty (`0x3d6890` set, `0x3d6930` test): one level, one number, or all 112; `open` sends packet 0x63 (`0x4812c0`) so the panel opens as in play; `tabs` sets the client's quests 7, 15, 23, 26 (bit 0) so tabs II-V are enabled; `panel` prints the plugin's button table (level, listed flag) |
| `item <code> [stat=value ...] [q=n] [ilvl=n] [uniq=n] [inv\|cube\|ground]` | creates the item in the backpack, the Horadric Cube or on the ground (port of `0x517530` with the page chosen and the stats set before the client is told); a stat is `<id>[:layer]=<value>` or `<name>[:layer]=<value>` with the `Stat` names of the build's itemstatcost.txt, Median's included (`fireresist=155`, `lightresist`, `coldresist`, `poisonresist`, `item_numsockets`; `plugin/src/mxl2012_stat_names.h`, made by tools/stat_names_data.py; an unknown name is an error), set as the item's total on its magic stat list (0.65.0: the list D2R saves, so the stats survive Save and Exit; before that they sat on the base list and the item came back with none). Charms are always made at quality 2 (the generator ignores `q=`), which keeps the stats; `uniq=<row>` makes a named unique (the generator hook of quests_act1.cpp picks it; unique index = `uniqueitems.txt` line - 2); answers with the item's id, page, position, quality, unique index |
| `cubecraft` / `cubeclear` / `cuberec <n>` | the transmute on the cube contents (`0x529090` search, then `0x5269c0`), prints the recipe row (`FAIL no recipe matches` when none does; portal outputs return no item, look at `state`); empties the cube; hex dump of a cubemain record |
| `cubeslots <first> <count>` | which of the three output slots (D2R record `+0x5a + 0x5b * i`) of recipes first..first+count-1 hold anything: a digit 0-7 per recipe (bit i = slot i filled: its first 0x0e bytes are not all zero, the tail holds -1 defaults even when empty), 50 recipes a line; the empty-output audit of `cowportals` compares it with the built cubemain.txt (reads the lines by their labels and asks again for a chunk with a missing line). Until lane cube-outputs the plugin lost about 7% of such replies' lines (`HarnessEcho` opened the console file with `fopen_s` while `hcmd` polled it, a failed open dropped the line silently): the release suite run `checks-20261022-212141-s1` lost the line of recipes 4950-4999, which shifted every later recipe by 50 and showed as "differences" at rows 4950-4962 / 5083-5100 / 5133-5141 (reproduced offline: delete that line from the built masks and the report's list comes out exactly). `HarnessEcho` now appends each line with one `WriteFile`, full sharing and a retry: 0 of 300 incomplete replies (was 20 of 300). Any harness verb with long output was exposed to the same loss |
| `cubeout <recipe> [slot]` | the executor's output dispatch (`0x526d3c`, handler table `0x1d3bfc0`) for the portal-output slots (special byte 1-4 at slot `+0x0d`) of a recipe, without inputs or conditions; look at `state` for the portal it opened |
| `flag player\|game <n> get\|set\|clear` | the craft flags (craft_flags.cpp) |
| `gameflag <word> <bit 0-15> [get\|set\|clear]` | D2R's own per-game flag bits (game +0x21d8 -> +0x10; get `0x325c50`, set `0x325c00`, clear is the byte of the record with that bit masked off): word 4 bit 11 is the Cow portal's once per game |
| `gold get` / `gold set <carried> <bank>` | gold stats 14 / 15 |
| `stat <ref> <stat> scan [max layer]` | every layer of the stat that reads non-zero (up to 40 lines `scan <ref> <stat>:<layer> = <value>` and a count; default max layer 262143): which skill an item's oskill / aura / proc property really carries (the layer is the skill, or skill << 6 \| level for encode 2 / 3 stats) |
| `stat player\|<item id>\|<item code> <stat> [layer] [set <value>]` | read or set any unit stat (`0x2f5020` / `0x2f7d10`) |
| `level <id>` | the NPC travel `0x4f2e40`: works across acts; inside an act it only opens a portal, use D2R's `cheat goto <id>` there. Do not send further commands for about 5 s (a second travel while one loads can hang the game) |
| `use <item code>` | the item-use check and use functions (`0x5817f0` / `0x581680`), the item is removed unless the item spell keeps it (keys and scrolls) |
| `remove <code> [n]` | takes items out of the inventory |
| `enter nearest\|<object id>` | walks into a portal object (`0x58f680`, as the click does, so the dungeon lockout hook sees it); the first call right after `use` can fail, repeat it |
| `missile <row> [dx dy]` | a missile of missiles.txt row <row> from the player towards (+dx, +dy) (default 12, 0), `0x5371a0` as the skills call it. In a town the client does not tick missiles; fire it in a dungeon (bug #24b: row 5507 crashed the client there before 0.48.0's empty-slot functions) |
| `missilescan [row]` | the rows whose client do / client hit index lands on an empty slot of D2R's tables (counts and the first rows); with a row number: the first 0x60 bytes of that missile record |
| `tile` | uses the nearest warp tile (`0x491ff0`) |
| `towerprobe` | whether the quest 5 kill hook would skip the vanilla handler for the nearest Countess (spawn 45 first): `skip=1` when quest 5 bit 0, 0xe or 0xf is set |
| `lockcheck <level>` | the dungeon warp test's verdict for the player entering the level (`allow`, `requirements`, `quest`, `sealed`, `none` when the table has no row), without moving anybody or counting (dungeon_lockout.cpp `DungeonLockoutProbe`) |
| `difficulty <0-2>` | writes the running game's difficulty byte (checks that need Hell rules without a Hell character; quest records are per difficulty) |
| `class <0-6>` | sets the player's class field (class bound recipes; set it back, the save keeps it) |
| `pkt <hex bytes>` | any client packet into the server handler table (fixed-size packets only: the walk / run packets 1 and 3 are 210 bytes with the client's path, a short one is read as garbage; use `move`) |
| `equip <code> [stat=value ...] [q=n] [ilvl=n] <bodyloc>` / `unequip <bodyloc>` | creates the item (stats as for `item`) and wears it (the game's place function `0x471500` with the location from `0x382df0`, so the owner gets the item's stats: a +77 strength ring raises stat 0 by 77 and `unequip` takes it back); body locations `head neck torso rhand lhand rring lring belt feet gloves altr altl` or 1-12; `state` prints `body=<n>` on worn items |
| `move <x> <y> [walk] [packet]` / `moveto <unit id>\|nearest [class]` | the player walks / runs to a position (state's x / y units) through `0x42d2c0(game, player, 0, 3, x, y, 0, 0)`, the call the walk packet ends in (the server finds the path); poll `state` for the arrival. `packet` sends the 210 byte walk packet through the handler table instead and prints the checks it makes (dead, position, distance <= 15) |
| `skill [left\|right <id>]` | selects the active left / right skill (packet 0x3c); no argument: the skills on both buttons. This plugin has no `skills` list verb (lane skilluse): the game's usability code (`0x33f360`, bug #397: 0 usable, 1 mana / cooldown, 2 item types, scroll quantity or item charges, 3 no InGame, 4 `restrict` / state, 5 passive, 6 aura, 8 delay) is printed only by `cast` |
| `xp <amount>` | D2R's award function `0x44f2e0(game, player, level, amount)`: adds the experience and runs the level-ups (stat / skill points, the class level cap); prints `level`, `experience`, `statpoints`, `skillpoints` |
| `setskill <id> <level>` | gives a skill levels with the game's own `0x438670` (stat 5 refilled each step, restored after); Median skills with prerequisites work, the prerequisite check is skipped |
| `skilldmg <skill> [level] [nomastery]` | the skill's damage at that level for the player through the damage hooks and through D2R's own functions (elemental and physical, min and max), with the inputs of Median's formula: flags (1 BaseSynergy, 2 StaticDamage), character level, energy, stat 514, the synergy percent columns, the BaseSynergy percent, the mastery stats (`docs/plugin-plan.md` "Skill damage scaling") |
| `collide <row> <dx> <dy> [type]` | a missile of missiles.txt row `row` from the player towards (dx, dy) like `missile`, optionally with its collision type (the unit's mode, read by the tick `0x463100`) set to `type`, followed every server frame; prints the record's CollideType and the mode on creation. `collide result`: frames alive, start / last position, distance |
| `collidetable [rows\|row <n>]` | the rows of the collide tables the server and client read now (types 0-10 and 255: check function RVA / mask), `rows`: missiles by CollideType, `row n`: one record's CollideType and the data-table-loaded counters |
| `wallscan [max]` | for the eight directions from the player, the distance to the first wall cell of the missile tick's test (`0x364d50` flag 4) with room cells beyond it; the last line is the best direction |
| `hasstate <state>` | the player's state bit, its stat list and end frame (float at list +0x24), and the game frame |
| `startfn <slot> <skill> [level]` / `startstats` | calls a server start-function table entry (`0x238e710`) the way the cast path does and prints its answer / the plugin's counters for slots 71 and 72 |
| `mcast <skill id> <mode 0-15> unit <id>\|nearest [class] [at <monster id>]` | a monster uses one of its own skills on the player (with `at`: on that monster; lane statefaith, Imp Teleport onto a Siege Beast) through the AI's skill use `0x4a7bc0` (mode as monstats `Sk<n>mode`: 6 = A1, 7 = A2, 9 = SC, 10 = S1); prints the answer, the monster's mode before / after, its stat 359 at layer = skill (the end frame of D2R's cooldown timer) and its states `0xb9` / `0x79`. The skill finish (and with it the cooldown start) comes a few frames later |
| `cast <id> [x y\|unit <id>\|nearest [class]\|self]` | selects the skill as the left skill, then uses it the way the cast packets do (`0x4fdb40` at a position, `0x4f8de0` at a unit: a melee skill walks up to the monster first and the cast starts when it is in reach, so repeat it for a wandering target); prints the usability code, mode and mana at the call |
| `missiles [reset]` | live missile units (type 3, hash base `0x646`) and the distinct missiles seen by any server frame since `reset` (class ids; short-lived ones are counted); `state` ends with the same line |
| `dump player` / `dump client` / `dump mon <class>` / `dump ground` | hex dumps for the RE work behind plugin offsets: the player's data block (`0x34b240`: the character name at +0), the client record of the player in the game, a monstats record (`0x976e0`; the treasure class words are u16 at +0xc0 + difficulty * 0x10 + (n - 1) * 2, n = 1..4; the quest class is n = 4), the items on the ground |
| `merc` | the player's mercenary unit (`0x4ff1a0(game, player, 7, 0)`): id, class, level, mode, life, and every item in its inventory (equipped ones have page 255) |
| `hire [npc class] [n] [reopen]` | hires the n-th free mercenary of the nearest hirer (or of the given NPC class) as the client's hire button does (`reopen`: makes the NPC's list again first; the answer lists the NPC's distance, the player's mode and the gold): lists the entries of the NPC's mercenary list (`0x502b70`), prices it (`0x3c17b0`) and sends packet 0x36 into the server handler; then `merc` shows what the new hire carries |
| `stat player\|merc\|mon:<id>\|<item id>\|<code> <stat> [layer] [set <value>]` | reads (or writes the base of) a stat; `merc` and `mon:<id>` are the mercenary and any monster by unit id (the verify checks set resists, avoid stats, life, strength, level on them) |
| `hit <player\|merc\|mon:id> phys\|fire\|ltng\|magic\|cold\|pois\|life\|mana\|stam\|clen\|flen\|plen <amount> [attacker ref] [stagger]` | one hit through the game's own damage path: a damage block with the elemental field set (result flags bit 0), `0x44ce80` (resist, absorb) then `0x44a9b0` (life); the amount is in 1/256 life points. Prints life before -> after, the absorbed total (block `+0x130`), the result flags and `field=` (the element's field after the step; for `clen` / `flen` / `plen` the cold / freeze / poison length). The player cannot hurt its own mercenary: give an attacker (`mon:<id>` of a spawned monster). `stagger` (last word) sets the result flag 4 (hit recovery) between the two steps: the target enters GetHit even when it has no hit recovery (bosses), and its last-mode field (monster data +0x68) reads 3 when it leaves it, which is the gate of `andariel_ai`'s controlled branch. Nothing happens in town |
| `avoid <ref> melee\|missile\|evade [n]` | runs the game's avoid check `0x44ef70` n times (default 200, the hooked one with Median's caps; its first argument is the attacker unit, the player here) against the unit and tallies none / avoid (2) / dodge (4) / evade (8) / block (0x10); `evade` puts the unit into walk mode for the loop |
| `wear <attacker ref> <defender ref> [n]` | n melee wear steps (`0x4526c0`, the function every hit runs; it calls the wear dispatcher `0x441b10`) and the summed durability of the player's worn items before and after |
| `iflags <item unit id> [unid]` | flag word (0x10 identified), mode, quantity (stat 0x46), durability (0x48) and maximum (0x49) and position of any item unit, on the ground too; `unid` clears the identified flag first |
| `itemdesc <item unit id> [eth]` | the text of the item's description as the inventory tooltip builds it: D2R's own builder `0x2be560` (out string, item, flags, flag, text, options) called on the client's copy of the item; one line `h: itemdesc id=<id> line <n>: <text>` per description line (colour codes removed) and `itemdesc id=<id> lines <n>`; `eth` makes the client's copy read as ethereal for that one call (the item itself is not changed). The `Durability: x of y` line is the output of `0x2c1640` (plugin part `durabilitytip`) |
| `cursor` | the item on the player's cursor (id, code) or `empty`; a held item makes `0x4249f0` report "busy" and refuses every skill use (drop it with the client packet `17 <id u32>`) |
| `manamin [reset]` | the lowest and highest mana of the player on any server frame since `manamin reset` (a skill's mana is charged a frame or more after `cast` returns and regenerates within a few frames, so one read afterwards sees nothing) |
| `manacharge` | what the mana cost hook decided at the last charge site: calls, room, town test, cost, charge, site (1 server, 2 client, 3 the loader's server copy), and the return address of the last other caller |
| `rewardstep potion\|tome` | runs D2R's own grant step of the Potion of Life (`0x580680`, max life stat 7) or of Lam Esen's Tome (`0x5ed6d0`, unspent stat points stat 4; grants only while `quest 17 1` is set) on the player and prints the stat before and after, the difference and the points (life in whole points). The amounts are Median's +50 life and 10 points with the plugin part `potionamounts` (vanilla 20 and 5) |
| `setstate <ref> <state> <0\|1>` | D2R's set-state call (`0x3355a0`) on a unit; prints whether the unit has the state afterwards. Gives the player the Stamina Shrine's state 136 without a shrine |
| `itemroll <code> <n> [q=] [ilvl=]` | makes n items through the generator the way `item` does (quality default 2, item level default 110), reads sockets, the ethereal flag, defence and maximum durability, frees them; prints the socket histogram, the ethereal count, the defence sums and the durability ranges of normal and ethereal ones |
| `colour <item id\|code>` | the item colour function `0x3710d0` (hooked for stat 368) on an item of the player: the colour byte, the item's colour kind and whether a palette entry came back |
| `req <ref> [as <class>]` | the item requirement check `0x36bc50` (class lock stat 492, mercenary weapon / shield lists) of every backpack item against the player or the mercenary; `as` swaps the unit's class for the call (character class 0-6, or a hire monster class 271 / 338 / 359 / 561). Prints id, code, usable, lock, weapon / shield flags and the hireclasses list item types the item belongs to |
| `panelrow <stat>` | the Advanced Stats panel's row functions (`0x14eb1b0` value, `0x14eb250` text, hooked by `stat_columns.cpp`) on a stand-in panel of the player unit for a D2R stat id: prints `panelrow <stat> value=<displayed value> text=[...]` (colour codes removed) and `panelrow weapon strbonus=N dexbonus=N` (or `none`) |
| `cstat <stat> [layer] [set <value>]` | (client side, UI thread) the stat of the client's copy of the player: what the screen shows, to compare with `stat player` after an update packet; `set` writes the client's copy only (a stat set on the server's unit does not reach it) |
| `statorder [open\|adv\|close]` | (client side) `statorder` prints the list the Advanced Stats panel built (`ordered`, rebuild count, rows: `[Label]` / stat id); `open` / `close` the character sheet, `adv` presses its Advanced Stats button (WidgetService panel messages) |
| `bufficons [hover <x> <y> \| hover state <n> \| hover off \| probe [off] \| cstate <state> <0\|1>]` | (client side) counters of the buff icon bar (`on`, frames, icons per group, refused draw requests, rectangles per frame, tooltip state and lines) and one line per drawn icon (`state side slot row secs hover x y size`); `hover` overrides the cursor, `probe` draws a magenta test rectangle, `cstate` sets a state bit on the client's copy of the player |
| `infopanel [close <n>]` | (client side) the presentation state of Median's help panels (2 = open) and how many opens the plugin message `I` asked for / the UI thread did / failed |
| `tip [id\|code]`, `tiplog [n\|reset]`, `tipfmt <stat> <value> [layer [mode [flag]]]` | (client side, off words `itemtext`, `tooltipprobe`) `tipfmt` calls D2R's property formatter `0x2d6520` with the given stat, value and layer and prints `ret` and the text (flag 1 = the group line); `tip` prints the lines of an item (client id or a code on the ground) as the item text builder `0x2dc4b0` made them, with `tip build` arguments only after one hover (the check hovers a ring once); `tiplog` lists the last formatter calls of the hovered item (`reset` right before `tip`, the ring floods every frame) |
| `rewardsnd`, `rewardmsg`, `goblinsay` | the quest reward sound the client hook last played (0x5f-0x61); a reward unit message to the player; the goblin "<name> appears!" line for a monster class |
| `sysmsg <type> <colour> <text...>` | one chat packet 0x26 to the player (docs/d2r-addresses.md section 13): type 4 = message-log line, 5 = overhead bubble; colour byte 0-11 |
| `automap` | (client side) the automap's cell count (sum of the four element counts of every layer), current layer, layer count and the debug flag byte `0x2a2add4` |
| `reveal` | (client side) the R hotkey's work without the key: D2R's debug Reveal Automap `0xd42b0`, flag byte restored; fails when the part is off or no local player exists |
| `wpobj` | every waypoint object of the game (class, position, distance, level, whether it is within 36 sub-tiles) and the player's level and waypoint number |
| `travel` | (client side) the hotkey bindings (key and modifier as D2RLoader reports them), counters (waypoints activated, scans, reveals, key presses, transmutes, cube open / closed) and the distinct UI messages seen (`uimsgs`) |
| `stashprobe <tab>` / `stashprobe result` | queues, on the game thread, a rune created by ItemService in shared stash tab `<tab>` and destroyed again; `result` answers `1 page=<n> create=0 ...` when the tab took the item, `0` when it refused |
| `stashpage state\|open\|close\|toggle\|msgs\|uia <target> <command> [text]\|widget <panel> [child]\|vis <panel> <child> <0\|1>\|put <code> [x y]\|fill <1\|2>\|drop <code>\|list\|move <id> <1\|2> [x y]\|result` | (client side; put / fill / drop / list / move queue work on the game thread, `result` has the answer) the personal stash page 2: panel state (1 closed, 2 open), a native UI message through WidgetService (`uia PanelManager OpenPanel BankExpansionLayout`), a widget rect, items created / listed / moved between page 1 and page 2 in one ItemService transaction |

mxl2012 additions (lane skills, 2026-10-28) to the list above:

| Command | What it does |
|---|---|
| `interact nearest\|<npc class>` | (lane acts) stands the player next to the NPC (`0x491ca0`, within 5 sub-tiles; from farther away the spot is often refused: walk up with `moveto` / `move` first) and sends the talk packet 0x2f: the NPC speaks, quest event 0 runs, the client opens the menu when the speech ends |
| `menu list\|<line>\|cancel` | (client, lane acts) the open NPC menu's lines (`string=` id, handler) or one line's own click handler (Trade, Talk, the act travel line) |
| `msg nearest\|<npc class> <message>` | (lane acts) packet 0x31, a dialog line played to its end (quest event 11) |
| `quest <id> dump\|<bit> [get\|set\|clear]` | (lane acts) the quest bits of the game's difficulty; `set` / `clear` are shortcuts a verdict must name |
| `xp <amount>` | (lane acts) D2R's experience award `0x44f2e0` (level-ups, stat and skill points are the engine's) |
| `moveto <id>\|nearest [class]`, `move <x> <y>` | (lane acts) the player runs to a unit / a position through `0x42d2c0` (what the walk packet ends in; the server paths it). `code 1` = refused (dead, or no path) |
| `presets [type\|rooms]` | (lane acts) the preset units of the player's level that are still in the rooms' lists (type 1 monsters / NPCs, 2 objects, 5 warps), in `state` units: where the map puts its boss, NPCs and waypoint. Units already placed drop out (town NPCs, Tyrael), and far rooms of a big level list nothing yet (Chaos Sanctuary: 23 objects from 225 rooms, lane acts2). `presets rooms` (lane acts2): every room's origin. DRLG walk of `0x3dad90` (offsets in `harness_cmds_logic.h`) |
| `place <x> <y>` | (lane acts) puts the player on a free spot near (x, y) with `0x491ca0`; only in loaded rooms (a travel shortcut) |
| `states player\|mon:<id> [state]` / `cstates ...` | every state the unit has (bit `0x3351b0`) with its stat list (`0x2f5940`: flags, end frame, `stat:layer=value` of the list's own stats); `states` reads the server's unit, `cstates` (UI thread) the client's copy. Ids are bounded by the states.txt row count (`0x300a90(dataFlag) + 0x298`): an id at or past it asserts `nShift`, state 0 asserts `dwState` |
| `cistat <item id> <stat> [layer]` | (lane dursync) the stat of the client's copy of the item (`0x9a5d0(id, 4)`, then `0x2f5020`); `istat` reads the server's. The two differ while a durability update has not reached the client (bug #433) |
| `durwatch on\|show\|off` | (lane dursync) counts packet 0x3e on its way: the server sender `0x47a190` (D2RLoader's jump slot `0x3e2a1b8`, wrapped), the client packet table's 0x3e handler (entry `0x22bc210`, wrapped) and the client's stat apply `0x1c7710` (inline hook), with the last durability value of each and the client item's stat 0x48 after the apply. `off` puts both entries back |
| `asserttrace on\|count\|show [n]\|clear` | hooks the engine's assert report `0x75ff0`; every assert (D2RLoader's log names only the first of a kind per launch) is counted, kept in a ring of 32 with message, file and a stack-scanned call chain, and written to `mxl2012-core.log` (`assert trace #n`). `count` is what `tools/skill_sweep.py` reads before and after each skill |

Where the answers cannot come from a call they come from the screenshot: the NPC popup text (`cain_menu.png`) and
D2R's own cheat output.

### Player actions (lane harness-cast, 2026-10-22, background mode, slot 2, plugin 0.48.0 + harness)

The `pkt` verb could not make the player act: the walk and run packets (1 / 3) are 210 bytes with the client's own path, and the
cast packets run through the character's active skill. `move`, `skill`, `setskill`, `cast`, `equip` and the missile counter now
drive the player server side with the game's own functions (no input of any kind; `py -3 tools/game_checks.py casts itemevents`).

| Row | Result | Evidence |
|---|---|---|
| `move` | PASS | `move 4725 5440` from 4704,5424: mode 3 (run), arrived at 4725,5440 within ~5 s |
| `cast` earthquake_2 (Median 1271, Barbarian) | PASS | melee: walks to the monster, mode 7, mana spent at the call (1000 -> 989 at level 5), 4-6 distinct missiles (earthquake missile classes 4164-4167, 5535-5537) |
| `cast` Bash (126) | PASS | mode 7, mana 1005 -> 996, no missile (a melee hit) |
| `cast` Fire Bolt (36, a Sorceress spell cast by the Barbarian) | PASS | mode 10, missile class 58; the game does not check the class here. The only character in the slot is a Barbarian, and Median's Sorceress skills with a missile and no prerequisite are rare (frigid_nova 485 answers usability 2 and does not run) |
| `equip` + `unequip` | PASS | worn item `body=4` / `body=7`; a +77 strength ring: stat 0 30 -> 107, back to 30 |
| Stat columns (rows 299 / 300, % bonus / base suffix) | PASS (`py -3 tools/game_checks.py all statcols`, slot 2) | `panelrow` with no weapon: 0 / 0; weapon `hfh` (StrBonus 16) at Str 50 / 123 / 300: 8 / 19 / 48; `hst` (DexBonus 6): Dex x 6 / 100; a ring `388=25 389=-10`: " (+25% bonus, N base)" / " (-10% bonus, M base)" on the Strength / Dexterity rows. The weapon bonuses come from the built weapons.txt. Not opened on screen |
| Level cap 150 (experience.txt `MaxLvl`) | PASS (`py -3 tools/game_checks.py all levelcap`, slot 1, 2026-10-22) | Barbarian, 5 stat / 1 skill points per level (charstats): `xp` from the start of level 98 / 99 / 119 / 148 / 149 reaches 99 / 100 / 120 / 149 / 150 with exactly +5 / +1 per level; one award of the whole table from level 99 gives level 150 and +255 / +51; more experience at 150 changes nothing (level 150, experience stays 12353407); the client copy (`cstat 12`) says 150, the character sheet shows `Level 150`; Save and Exit and Play: level 150, same experience and points, `.d2s` header byte 0x1b = 150. Before the fix (main's old `experience.txt`, `MaxLvl 99` last) the same check failed on every step: no award levelled the character at all (98 stayed 98, 149 stayed 149), the client level read 99, the saved character was level 99 |
| Item events (stat 397 / 265 / 376 / 135 / 136) | PASS (`py -3 tools/game_checks.py all itemevents`, slot 3) | ring `397=50`: the monster loses 50 points on `evtrace fire 3 player m<id>`; ring `265=50`: +50 life on `evtrace fire 9`; ring `376:2309=100`: a class-58 missile (Fire Bolt 5, skill not owned); ring `135=100 136=100`: a plain monster loses life on events 5 / 6, one with stat 373 does not. A weapon `115` in `rhand` does not apply its stats in the harness, use a ring. See docs/subsystems/items-xp.md section 5b |

Notes for whoever extends this: `cast` needs the skill to be the active left skill (the unit cast uses the player's active skill), the
harness selects it; a melee skill cast at a unit makes the player run to it first and the class 18 monsters wander off, so the check
repeats the cast; the mana cost cannot be read from `state` after the fact (regeneration refills in a few frames), only at the call.

### Item rules and free mana in town (lane gap-items, 2026-10-22, background mode, slot 1, plugin 0.54.0 + item rules)

`py -3 tools/game_checks.py all nodurability autoid townmana`, the plugin with and without the off words
`durability quantity autoid townmana` in `mxl2012-core-off.txt`.

| Check | With the parts | Off words | Evidence |
|---|---|---|---|
| `nodurability` (audit IT1, IT2) | PASS | FAIL | hfh weapon 110 -> 110 and fld armour 48 -> 48 after 600 `wear` steps (off: 110 -> 101, 48 -> 16); a tax stack, 4 accepted Throws (`cast 2 nearest`), quantity 58 -> 58 (off: 110 -> 109) |
| `autoid` (audit IT3) | PASS | FAIL | 14 Andariel kills (`spawn 156`, `kill nearest 156`), `dump ground` (now prints `quality=` and `identified=`, ground items only): 6 magic / set / rare / unique drops, 6 identified (off word: 0 of 6); the low / normal / superior drops are identified either way (D2R sets the flag on non-magic items itself). `itemroll` and `item` cannot show it: `MakeItem` `0x43d530` sets 0x10 at its end |
| `townmana` (audit SK3) | PASS | FAIL | skill 1558 (`sk1486`, InTown, level 5) cast at the player: Rogue Encampment, lowest mana 5000 of 5000 (cost 16 by the plugin, charged 0, `manacharge` site 3); Blood Moor, lowest 4993 (off: 4993 in town too) |

What the checks needed to learn (so the next check does not lose time on it):

- Mana is charged when the cast's action starts and refills in a few frames, so `cast`'s own "mana A -> B" and a read two
  seconds later both show nothing; `manamin` samples every server frame. The drop it sees (7) is smaller than the charge the
  plugin decides (16): regeneration refills in the same frames.
- `0x4249f0` ("busy") is also true while an item is on the cursor. `unequip` and a pick-up leave the item there, and the next
  cast is refused with code 1 although the usability code says 0. `cursor` shows it, packet `17 <id>` drops it.
- D2RLoader runs a re-assembled copy of the server's skill charge function (`0x436830`), so the return address of the mana
  cost call is a heap address: see docs/plugin-spec.md, Mana costs.
- A skill must be selectable (left or right skill); `cast` refuses the passives and the ones the game will not select
  ("would not select"). The check tries the InTown skills of the built `skills.txt` by required level until one is accepted
  (`usable=0`).
- Median's Throw (skill 2) needs strength 600 / dexterity 600 / level 60 for tax; the check sets the stats and restores them.

### Client messages (lane client-ui, 2026-10-22, background mode, slot 2, plugin 0.48.0, window-only screenshots)

| Row | Result | What the screenshot shows |
|---|---|---|
| `sysmsg 4 <colour>` / `sysmsg 5` | PASS | message-log lines in the colour of the byte (1 red, 2 green, 3 blue, 8 orange, 9 yellow); type 5 a bubble above the player |
| Lockout refusal, requirements | PASS | Normal, `h use b60X` + `h enter nearest` (level 125 char, level 251 needs Hell): red "Requires Hell difficulty" then D2R's "Impossible." |
| Lockout clock | PASS | Hell rules, key `b62X` into level 253: orange "Closing in: 01:00" and "ONCE YOU EXIT YOU CANNOT GO BACK" |
| Lockout sealed | PASS | 68 s after the first entry: red "This area is locked" / "Join another game to enter again" |
| Heart notice | PASS | `h quest 4 1 set`, `h msg 148 0x76`: "You have received: Griswold's Heart" |
| Arcane Crystal notice | PASS | in Lut Gholein (area 40), `h quest 14 3 set`, `h msg 201 0x1ba`: "You have received: Arcane Crystal" (the same message with Jerhyn spawned in Act 1 does nothing: the vanilla handler is not reached) |
| Goblin notice | PASS | `MXL_GOBLINS_FORCE=1`, Blood Moor: yellow "A treasure goblin has been sighted nearby!" |

Ormus' shrines and Cain's crystal use the same call as Jerhyn's and were not run. The game-start helper `clear_intro` (tools/game_ctl.py) looped on the Continue button when the main menu scene was bright; the runs here clicked the three calibration screens by hand. **Fixed 2026-10-22 (lane bug24b):** `clear_intro` now ends when `menu_visible()` sees the main menu (a 12 x 16 grey signature of the left button panel, `MENU_SIG`: mean difference 0 on the menu, about 27 with a dialog dimming it), clicks Continue at most 6 times and holds Esc at most 4 times (never once the menu is up: Esc on the menu opens the exit dialog); checked with synthetic frames (bright menu, three calibration screens, endless calibration, dimmed menu) and on slot 3's live menu, the real calibration screens did not come up on that slot.

### Results with the harness commands (2026-10-21, background mode, slot 2, plugin 0.47.0 + harness)

`py -3 tools/game_checks.py all` (MXL_SLOT=2), evidence in `<runs>\checks-20261021-210224\` (all rows
except the lockout clock) and `checks-20261021-211130\` (lockout clock, sealed). Real-input watchdog (cursor and foreground
window every 25 ms): no abort in any run, the game window was never the foreground window, the cursor never moved into it.

| Row | Result | Evidence |
|---|---|---|
| `mxl` command | PASS | 14 feature lines |
| Goblins (FORCE=1) | PASS | `h kill nearest` x2 in the Blood Moor: `h state` goblins 0 -> 1 spawned, log `goblin 2796 spawned in level 2` |
| Akara respec | PASS | `h interact 148`, menu list shows Talk, Trade, vanilla respec (`0x2ba0`) and the plugin line (`handler=plugin@`); `h menu 3`: strength 90 -> 30, 60 stat points refunded, log `npc actions: done (48, 148)` |
| Cain crafting materials line (bug #23) | PASS | menu opens, no `menu record is full` log line, `cain_menu.png` shows TALK / CRAFTING MATERIALS / CANCEL |
| Griswold's Heart | PASS | `h msg 148 0x76` with quest 4 bit 1: new item base `600`, unique index 69, plus the vanilla ring |
| Andariel catalyst, Warriv re-issue | PASS | `h spawn 156` + `h kill nearest 156`: 1 catalyst `3o[`; second kill: still 1; removed, `h interact 155`: re-issued. (Quest 6 must be active when the game is created and the flag, quest 47 bit 0, clear: game_checks patches the closed save first) |
| Median `andariel_ai` users (AI 155) | PASS 46 of 47 (`py -3 tools/game_checks.py all medianai`, slot 3, `MXL_AI_CHUNK=a:b` for a slice) | Every monstats row with AI `andariel_ai` is spawned beside the god-mode player and watched 3 s: the `monster ai` counters rise (thinks, attack, skills) and the monster changes mode; no crash. Diablo clone (333) cannot be spawned by the harness (nothing spawned). Malthael 10-13 and later users are judged on the counters only: Malthael's unkillable dark nephalems (class 1239) fill the `state` list; each monster is killed by id afterwards |
| `andariel_ai` controlled branch | PASS (`py -3 tools/game_checks.py all medianai_ctl`, slot 3) | Maghda hit with `hit mon:<id> phys 1280 stagger`: `controlled thinks` stays 0 before the first hit and rises after it |
| Tyrael travel line follows quest 28 | PASS (`py -3 tools/game_checks.py all tyrael`, slot 3) | `mxl`: `travel gates moved 1`; the line with handler 0x1162f0 is in his menu only with quest 28 bit 0 set, whatever quest 26 says |
| Dungeon lockout: refusal | PASS | Normal, `h use b60X` + `h enter nearest`: refused 0 -> 1, still in town |
| Dungeon lockout: clock, re-entry, sealed | PASS | Hell rules (`h difficulty 2`, level 125), key `b62X` (level 253): entry, clocks 0 -> 1; re-entry after 18 s allowed; after 68 s the entry is refused (refused counter +2, stays in town) |
| Cow portal recipe | PASS | leg in the cube: Normal town no recipe; Hell town recipe 2 runs and a class-60 portal object appears (the handler needs Baal killed in that difficulty: `h quest 40 0 set`); Hell field no recipe |
| Cube gold payment | PASS | row 6327 (50,000): 400000 -> 350000; row 6328 (100,000) with 20,000 carried: carried 0, bank 100000 -> 20000 |
| Craft flags | PASS | player flag: row 6369 (assassin) sets flag 1, then row 6350 is offered; game flag: key row 7102 sets game flag 50, a second try is refused |

Notes: the cube conditions of Median rows are partly on the player (`stat player 378`, `536`, `532`) and partly on the item
(op 18: item stat 532 == 1), see `game_checks.check_goldcraft` / `check_craftflags`. `h cubecraft` returns no item for
portal recipes; look at `h state`. Observed, not fixed (docs/bugs.md #24): entering a Median dungeon level through a portal
can crash the client after a few area changes in one game (assert `asset cache exceeded`, null call), so the lockout clock
check runs first and the full run ends with a crash on some runs.

### Regression hunt 0.49.0 (2026-10-22, lane regress049, slot 3)

Two checks of `game_checks.py all` failed on 0.49.0 and passed on 0.48.0.

| Check | Before (0.49.0) | Cause | After |
|---|---|---|---|
| `respec` | FAIL: Akara's menu had Talk and Trade only, no plugin line | Not the menu code, not quest 41. The Heart notice added in 0.49.0 (client messages, PR #55) is sent from the quest handler of Akara's speech, in the middle of the speech, and a chat line (types 1, 4, 5) during an NPC speech freezes it: the NPC menu never opens, the menu builder `0x1147a0` is never called (so the plugin's lines are never added). `mxl2012-core-off.txt` word `clientmsg` made the check pass; `h sysmsg 4/1/5` during the speech reproduced it, type 0 and a line after the menu is open do not. Details docs/d2r-addresses.md section 13 | PASS: notices of quest dialog handlers are held until the client's menu is open (`SendClientNotice`); the screenshot shows the menu and "You have received: Griswold's Heart" |
| `casts` | FAIL: Bash showed no cast animation / mana drop | The check, not the plugin: `cast` at a monster 5-8 sub-tiles away only walks to it (mode 3); the Fallen wander, so the same cast failed for Bash in one run and for earthquake_2 in the next (three runs on the same build, a different case each time). Bash's mana cost and animation are as before (mana 15 -> 12, mode 7) | PASS: `cast_and_watch(approach=True)` moves next to the monster before every try of a melee cast (10 tries) |

`py -3 tools/game_checks.py all mxl respec casts --slot 3` after the fix: all three PASS (`checks-20261022-033532-s3`). The
`respec` check now puts the unused stat points back (each run had raised them by the refunded 60 in the saved test character).

### Verify rows of unported.md (2026-10-22, lane verify-checks, background mode, slot 3, plugin 0.50.0)

Twelve new checks in `tools/game_checks.py` (`py -3 tools/game_checks.py --slot N all resistcap absorb avoidcaps classlock hiregates itemrolls dye goldclient bonusdrops summoner tooltiptext gameend craftflags`), built on the harness verbs `hit`, `avoid`, `itemroll`, `colour`, `req`, `cstat` and `stat player|merc|mon:<id>`. A check needs a merc: it hires Kashya (`quest 2 0 set` first, Blood Raven) and waits for the mercenary to follow into the field. Notes for writing checks: damage and avoidance run only outside the town; `fight_ready` kills everything near, the mercenary too, so call it before `ensure_merc`; a hit on a unit just arrived in an area can return result 0 (ignored), the `hit` helper retries; a walking mercenary cannot avoid or dodge.

| Row | Check | Result |
|---|---|---|
| Max resistance cap 90 (player, mercenary) | `resistcap` | PASS: resist 200 and max-resist +0 / +10 / +50 took 25 / 15 / 10% of a 100000 hit, fire / lightning / cold / magic, 24 of 24 |
| Absorb stats 184 / 189 / 417 | `absorb` | PASS: 8 probes, the healed amount equals the formula to the unit (e.g. 30% of 100000 with 7% stat 184: 27900; with 184 = 57%: 12900; divisor 4: 6975; 417 layer 1 at 50%: 13950) |
| Mercenary avoid / dodge / evade caps; player | `avoidcaps` | PASS: 2000 rolls each of the hooked `0x44ef70`: stat 100 with stat 380 = 0 / 10 / 30 gives 60 / 70 / 75%, stat 50 gives 50%, player and Rogue |
| Class-locked items (stat 492), players and mercenaries | `classlock` | PASS: locks 1-8 against 7 player classes and 3 merc types |
| Hireling equip gates by class | `hiregates` | PASS: 4 hire classes, allowed / refused weapon and shield types as the lists |
| Socket roll | `itemrolls` | PASS: 4000 items, 1/7 per socket count below the base maximum |
| Sockets and automagic for every quality | `allqualsockets` | PASS (slot 3, 2026-10-22, lane pa-sockets): 3000 items per quality at item level 101 on a 6-socket base (`60@`): low / normal / superior / magic 0..6 sockets, about 1/7 each; rare / unique / crafted / tempered 6 on all 3000; automagic mod on all 3000 including unique. With `allquals` off: magic 0, rare / unique / crafted / tempered 0 sockets, unique automagic 0 of 3000 (check FAIL as expected). Set (5) not generated by the harness: not judged |
| Ethereal roll + 25% | `itemrolls` | PASS (0.51.0, lane ethereal-avoid): the harness had passed generator bit 2 (no ethereal); fixed. 4000 tower shields at item level 101: 102 ethereal (2.55%, Median 2.6%), defence x1.24, maximum durability 60 -> 45; quality 1 (low): 94 ethereal, 19 -> 14. Rate required within 4 sigma. docs/bugs.md #25 |
| Dye colour (stat 368) | `dye` | PASS: bytes 0x00..0x14 for stat 1..21, undyed for 0 and negative |
| Socketed runes stack (bug #50) | `runestack` | PASS: player stat after 0-3 sockets filled (packet 0x28): Eld max damage 0/3/6/9 in armour, helm, shield; Ral fire res 0/30/60/90; gem gpv AR% 0/50/100/150; jewel fire res 0/30/60/90; Runemaster 20: Defense % 0/20/40/60 |
| Craft player flags by name | `craftflags` | PASS |
| Craft per-game flags reset on game end | `gameend` | PASS: flag 50 set by recipe 7102, 0 in the next game, `games ended` 0 -> 1 |
| Gold payment client update | `goldclient` | PASS: client gold stats equal the server's after rows 6327 / 6328 |
| Summoner AI / MosquitoNest | `summoner` | PASS: spawned, acted (cast and moved), summoned |
| Bonus drops (Summoner / Izual catalysts) | `bonusdrops` | PASS: one on the ground after each of two kills, quest bits set. Per-player count in multiplayer: manual |
| Item tooltip text (65 stats) | `tooltiptext` | PASS: 313 property lines read through D2R's formatter (294 equal Median's text, 19 read on real items, 0 wrong) plus 5 unique items and 12 rare / magic items read as real items; the table is docs/item-tooltips.md |
| Trade window | none | manual: needs two players (TCP/IP), not scriptable here |

Also found: the avoid hook's first parameter is the attacker unit, not the game (docs/bugs.md #26).

### Potion amounts, stamina and mana rules, get-hit durability (lane pa2-stats, 2026-10-23, background mode, slot 1, plugin 0.54.0 + this branch)

`py -3 tools/game_checks.py --slot 1 all manarules sprint`, then with `potionamounts stamina manaregen durability` in `mxl2012-core-off.txt`
`all manarules potionamounts nodurability sprint`. The first pass on slot 3 (`potionamounts manarules nodurability heat townmana sprint`)
gave PASS for `potionamounts`, `nodurability`, `heat` and `townmana`; its `manarules` failed only in the state 136 leg (the first
`setstate` made no state list) and in a 6% tolerance on the walking rate (39.7 against 37 raw per frame). Both were fixed in the check (the
`setstate` verb now builds the state list the way D2R's self buffs do; tolerance 15%).

| Check | With the parts | Off words | Evidence |
|---|---|---|---|
| `potionamounts` (audit item 11) | PASS | FAIL | harness `rewardstep potion` / `tome` (D2R's own grant steps `0x580680` / `0x5ed6d0`): +50 max life and +10 stat points (off: +20 and +5) |
| `manarules` (audit item 15) | PASS | FAIL | standing 49.5 raw per frame (off 50.6; max 50 / 256, both builds); walking 37.1 (off 25.8); state 136 set with `setstate`: stamina 0 -> 50 of 50 in 1 s (off: 6 of 50); a 40 raw mana pool with bonuses off: 0 after 2.5 s (off: 40, D2R's floor of 1 per frame); a run in the Rogue Encampment from full: 6 samples running, lowest 50 of 50 (off: 5 samples, 50 of 50, so the town rule is vanilla's) |
| `nodurability` (audit IT1, item 12) | PASS | FAIL | weapon 70 -> 70 and armour 48 -> 48 after 600 `wear` steps in both directions (off: 70 -> 63 and 48 -> 20); 25 s of real monster hits (850 life lost): armour 48 -> 48. With the part off the armour did not wear down in the real hits either (613 life lost), so that leg only shows that nothing breaks; the `wear` step is the SUnitDmg call `0x4526c0` itself |
| `heat`, `townmana` | PASS | not run | unchanged by the new mana step (heat: 25496 -> 18840 -> 11768 -> 0, Flamefront builds up, a town holds; townmana: cost 957 in the field, none in town) |
| `sprint` (audit SK7) | FAIL | FAIL | the check of that day measured the stamina with a second console read after the state read (a different frame) and judged medians, so its walking, timing and toggle results varied from run to run with every part of this lane off. It now reads frame, mode and stamina from one `state` reply and asserts the exact per-frame rules above (lane checks-robust) |

New harness verbs: `rewardstep potion|tome` and `setstate <ref> <state> <0|1>` (table above).

### Hunter Steady Aim, Fire Sorceress Heat, trophy windows (2026-10-22, lane gap-classres, background mode, slot 3, plugin 0.54.0 + the lane's parts)

`py -3 tools/game_checks.py --slot 3 all steadyaim heat trophytimer` (evidence `checks-20261022-215233-s3`, data and DLL installed together with `install_mod.py --slot 3`; the merge of main had changed the data, a run with the old data under the new DLL read the counter 6, 6, 6, 6). All three drive the plugin through the harness (no input).

| Check | Result |
|---|---|
| `steadyaim` | PASS: 4 Steady Shots read the counter (stat 220 layer 5) 1, 2, 3, 4; Heartseeker is refused (4, restricted) with no counter and usable with it; one Heartseeker leaves 3, the spend runs the counter to 0 and the skill is refused again |
| `heat` | PASS: Molten Core gives stat 297 = 107 at level 21; mana x256 from full 25284 -> 20228 (2.5 s) -> 15093 (5 s) -> 0 (floor 0); Flamefront at empty: peak 1106 and stat 297 goes negative; in the Rogue Encampment a set 12800 is still 12800 3 s later |
| `trophytimer` | PASS: Heart of Sin (stat 378 = 167166, assassin recipe 6377): in time the recipe matches; 12 s later, after Blood Moor and back, and after dying (spawned attacker, 2e9 hit) it does not, with the stat still 167166 each time |

How they work and what is not tested: `docs/plugin-plan.md` "Skill restrictions", "Steady Aim", "Heat", "Trophy timer". The trophy check
sets stat 378 to the Heart of Sin code (167166) with the harness: nothing in the data names the skill a boss kill casts, so the
kill itself is not exercised. Findings on the way: `tools/formula.py` turned a missile `stat(x, n)` with a layer into a plain stat
read (wrong layer), and `txt_migrate.py formula_proxies` read the `ParamN` columns by position; both fixed.

### Skill damage scaling (2026-10-22, lane pa-skills, background mode, slot 1, plugin 0.54.0 + the lane's part)

`py -3 tools/game_checks.py --slot 1 all skillscaling` (evidence `checks-20261022-223626-s1`; data and DLL installed together with `install_mod.py --slot 1`; the plugin reports `skill damage on: elemental + physical min/max, 164 BaseSynergy and 423 StaticDamage skills`). Nothing but the harness: `skilldmg` prints the damage through the hooks and through D2R's own functions, and the inputs the formula needs (character level, energy, stat 514, the synergy percent columns, the mastery stats); the check computes Median's formula in Python from the built `skills.txt` columns and `skills2.bin` flags and compares.

| Check | Result |
|---|---|
| `skillscaling` | PASS: 572 samples (7 groups of skills x skill levels 1, 2, 8, 9, 16, 17, 22, 23, 28, 29, 45 x 4 character setups: level 1 / energy 0, level 40 / 150, level 100 / 300 with stat 514 = 600, level 150 / 1000 with stat 514 = 5000, each with 0-60% mastery stats) equal the formula. BaseSynergy is -42% at level 1 and 1626% at level 100 / 300 energy / stat 514 600. Nova and Meteor (BaseSynergy elemental), blast_wave (BaseSynergy physical), Magic Arrow (StaticDamage elemental: mastery 40 changes nothing), immersion (StaticDamage physical), Fire Bolt, Telekinesis, DiabRun, PoisonBallTrap (plain; stat 357 raises the physical ones). 18 samples of skills with no flag and no mastery equal D2R's own functions to the digit (elemental, physical, and skills with a weapon share: Sanctuary, MonLeapAttack). Synergy: raising Fire Arrow 1 -> 12 raises Poison Javelin's percent column 12 -> 144 and its damage (8744-9891 -> 19051-21550) as the formula says; Charged Bolt from Lightning likewise |

Not tested in the game: the weapon share of the four BaseSynergy skills that have one (scorpion_blade, thunder_hammer, thunder_wave, angel_of_death; the unit tests cover the arithmetic, and the weapon share of plain skills equals D2R's), skills whose `passive` flag keeps D2R's physical function. A first run on slot 3 gave the same results but lost two samples to harness time-outs (`no answer in 15 s`); `_sd_query` now retries.

## Scripted checks (tools/game_checks.py, 2026-10-21, foreground input)

Console commands and measured coordinates: [dev-console.md](dev-console.md). Results of the partial run (the run was
stopped before the full set finished because the foreground input took the user's mouse; the checks are to be re-run
in background mode once `lane/bg-input` is on main). Evidence is in `<runs>\checks-20261021-140330`
(interactive exploration) and `checks-20261021-163305` (scripted run).

| Row | Result 2026-10-21 | Evidence / note |
|---|---|---|
| `mxl` command | PASS: prints all 15 feature lines (plugin 0.42.0) | `checks-20261021-161134\mxl_cmd.png` |
| Goblins (MXL_GOBLINS_FORCE=1) | PASS: after killing a Fallen in the Blood Moor a goblin spawned (log `goblin 2798 spawned in level 2 near player 1 (frame 5250)`, a second run `goblin 2791 ... frame 1500`); drop and name not looked at | `checks-20261021-140330\after18s.png`, `checks-20261021-163305\goblin_scene.png`, `goblin_mxl.png` |
| Akara respec | PASS by hand: with a level-12 character and the Den of Evil bit set (quest 41 word 2), Akara's menu shows Talk, Trade and two "Reset Stat/Skill Points"; the second one logs `npc actions: done (kind, npc class) (48, 148)` and the character sheet then shows 55 stat points remaining (reset). The scripted version clicked the wrong line (vanilla one) and is fixed but not re-run | `checks-20261021-140330\akara_menu1.png`, `respec_char_after_line2.png`, `checks-20261021-163305\respec_3_menu.png` |
| Cain crafting materials | FAIL (bug #23): the line does not show, log `menu record is full` | `checks-20261021-140330\cain_menu1.png` |
| Griswold's Heart | PASS (script): patched save with quest 4 bit 1, talked to Akara twice, one new item in the inventory; the unique's name/stats were not read | `checks-20261021-161134\heart_inventory.png` |
| Andariel catalyst, Warriv re-issue | BLOCKED: no cheat kills Andariel (`god`'s easykill does not one-shot her; 14 axe hits did not), and the quest state for event 8 was not set up | `checks-20261021-163305\catalyst_after_kill1.png` |
| Cow portal recipe, town vs field | PASS for Normal town (recipe 3 has min difficulty 2: nothing happens), earlier manual try; Hell town/field BLOCKED: `spawn leg` plus `spawn tbk` could not be picked up by the script in the later run | `checks-20261021-140330\cow_after.png`; script run `cow_hell_*_pickup_failed.png` |
| Cube gold payment, craft flags (6327-6329, 7100, 6369 -> 6350) | BLOCKED: the recipes need items with Median stats (stat 532, `UpgradedBossKillerRing`, `RathmasSupremacy2`) and no console cheat sets an item's stat or spawns these as upgraded; also `cubeinputs`/`cubestuff` failed for recipes 2, 3 | dev-console.md |
| Dungeon lockout (refusal, clock, seal) | BLOCKED: `spawn b61X` did not yield a usable scroll/portal in the script; not seen manually. The `mxl` command shows counters `refused N, clocks started N` that the check should read | `checks-20261021-163305\lock_normal_portal.png`, `lock_mxl.png` |
| Warriv re-issue | BLOCKED with the catalyst check | - |

### Background-mode run (2026-10-21 18:42, `py -3 tools/game_checks.py all ...`, plugin 0.46.0)

Run folder `<runs>\checks-20261021-184217\` (report.md, screenshots). Real-input watchdog (cursor
and foreground sampled every 25 ms for 10 minutes, 23,303 samples): the game window was never the foreground window and
the run never moved the real cursor into it (the cursor values in the report are the user's own mouse, x 0..5819,
y -1417..2159); no abort. Console lines go through the plugin harness; D2R's cheat output is not readable in this mode, so
cheats are verified by their effect in the screenshots.

| Row | Result | Note |
|---|---|---|
| `mxl` command | PASS | 14 feature lines read through `console_text` (`mxl_town.png`); the whirlwind line no longer exists in 0.46.0 |
| Goblins, Akara respec, Griswold's Heart, Andariel catalyst | FAIL / BLOCKED in this run: **clicks on the game world do not register in background mode** (a left click on a monster does not attack it, a click on Akara does not open her menu, the character does not walk; UI clicks on menus, the inventory and the cube panel do work). `goblin_scene.png` shows 14 spawned Fallen around the character, none hurt; `respec_3_menu.png` shows no menu after the click on Akara. The earlier foreground results above stand. Not yet verified why (hypothesis: world clicks need the button state to be held across several game frames or a hovered-unit update the virtual cursor does not provide); `lane/bg-input` needs to make `click()` work in the world, or the harness needs `interact <unit>` / `attack <unit>` / `move x y` commands |
| Cow portal recipe, lockout (refusal, clock, seal) | BLOCKED: after `cheat itemgridclear` the `cheat spawn box,inv` / `leg,inv` / `tbk,inv` lines through the harness put nothing into the inventory (`cow_normal_town_spawn_failed.png`); the same lines typed in the console panel in the foreground run did. The lockout needs the scroll in the inventory, the counters (`refused N, clocks started N` in `mxl`) are readable already |
| Cube gold payment, craft flags | BLOCKED: needs harness commands `item <code> [stat=value ...]` (item with stats in the inventory), `flag player\|game N get\|set\|clear`, `gold get` |
| Andariel kill (catalyst, Warriv) | BLOCKED: needs a harness command `kill <monster>` or world clicks that work, plus `quest <id> <state>` to put quest 6 in progress |

### Monster looks (lane sigma-behaviours-b, 2026-10-22, slot 3, background mode)

Run folder `<runs>\checks-20261022-101244-s3\` (not committed). `h spawn 2791 1` (treasure goblin) in the Blood Moor.

| Row | Result | Note |
|---|---|---|
| `mxl` monster looks line | PASS | "monster looks on: name colours on, automap on, spawn overlays on (1803 monsters in the table)" with counters |
| Automap marker and name | PASS | `goblin_automap.png`: Tab shows the blue NPC marker and "Treasure Goblin" under it; counter 124 markers / 124 names |
| Spawn overlay | PARTIAL | counter "1 spawn overlays (last 53 on monster 2791)" and the game stays up; the effect itself was not seen in the 0.4 s captures. The first build read the creation function's result without a check (callers that return 1) and ended the game on `cheat goto 2` (crash reports of `d2rloader\crashes`: read at address 1); fixed by only reading pointers |
| Name colour | BLOCKED | the hover needs the cursor over the monster; background mode cannot place it. Rules and data are unit tested (`monster_looks_test.cpp`), the hooks install ("name colours on") |
| PalShift stand-ins | PASS (tool) | `work/mod/effects_hd.md` paragraph PalShift: 21 shifted rows scored, 13 custom art; not looked at in game |

### Backlog B: the old "fix to test" rows of bugs.md (lane bug-backlog-b, 2026-10-22, slot 2, background mode, plugin 0.53.0 + this branch)

Run folders `<runs>\checks-20261022-*-s2\` (not committed). One check per bug, all PASS; run them with `py -3 tools/game_checks.py --slot N all <check>...` (at most three checks per call: a call stays under 10 minutes).

| Bug | Check | Result | What it does / what stays manual |
|---|---|---|---|
| #3 skill tabs | `skilltree` | PASS | clicks the 8 tabs; harness `skilltab` reads the page of each click ([0..7]) and 8 / 8 panel pictures differ. Titles and stone art: look at `skilltab1-8.png` |
| #9 skill tooltip assert | `skilltree` | PASS | hovers all 144 icon cells: no `stringIndex1 != strdummy` box in d2rloader.log. **Root cause of the old "hover does not work in background mode": WM_MOUSELEAVE.** The harness hook of `TrackMouseEvent` (testharness.cpp) now makes it a no-op, so the hover and its tooltip stay up |
| #5 keybinds | `keybinds` | PASS | Options > Controls: Skill 9 = F9, Apply; `<char>.key` md5 cd37237f -> 57e96a28; Save and Exit, restart: same md5 and Skill 9 still F9; F6 skill hotkey selects the same skill before and after. The layout is restored (Default key list) |
| #7 NPC text | `strings` | PASS | the client's string function (harness `str <id>`) for 592 NPC intro / Median strings: 0 wrong, no Median key shares a 16-bit id with a D2R string (D2R ships 27956/28082 shared itself). The subtitle on screen: manual look |
| #15 automap | `automap` | PASS | one area per level type 36-51; harness `automap [type]` lists rows, how many resolve to an atlas cel, the game's own lookups and hits, and (single type) the first missed tile/style pairs. Type 37 has only wall rows, the game asks for styles 2/7/30, so 0 hits there is Median's own table; types 45-50 have no rows (unported.md) |
| #17 levels > 255 | `scrollportals` | PASS | each summoning scroll in its act's town, `enter <portal id>`: areas 251-253, 263-268, 274-276 reached. Entry needs Hell (difficulty 2) and level 150 (mxl_dungeons.h levelReq 120-147); the check restores level 5 and difficulty 0 |
| #18 vendor crash | `vendors` | PASS | Akara, Charsi, Gheed: interact, Trade, tabs (Akara has no Armor tab: a click on that spot closes his panel), right click buys one Misc item each (gold 40000 -> 39999): game alive, 0 `[default_unit]`, 0 `File not found`. One skillDescTbl assert box per run (bugs.md #29). The vendor pictures: look at `shop_*.png` |
| #22 monsters | `monhover` | PASS | spawns a zombie, the virtual mouse goes over its projected position (harness `hover` names the unit), left clicks kill it in ~16 hits. Same WM_MOUSELEAVE root cause as #9 |

New harness verbs (client side unless noted): `skilltab [n]` (selected tab, or select tab n), `str <id>..`, `hover`, `automap [type]`, `shop [npc class]` (server: the vendor's stock; buy through the panel), `levelact <id>..` (server: act of a level). `state` monster lines carry `mx= my=` (world position).

Slot procedure used: `py -3 tools/game_slots.py lock 2 lane-backlog-b`, `py -3 tools/install_mod.py --slot 2`, `MXL_RUN=lane-backlog-b py -3 tools/game_checks.py --slot 2 all <checks>` (the run keeps the lock and releases it at its end). A full install is needed after another lane has used the slot: a partial data set from a foreign install made `strings` fail once (253 wrong, "Missing string"), and a re-install fixed it.
Noticed and not fixed: the Wolf Stance tooltip shows a literal `%+d%%` (bugs.md #30).

### Travel: map reveal, waypoint auto-activation, hotkeys, stash pages (lane gap-travel, 2026-10-22, slot 1, background mode)

Run folder `<runs>\checks-20261022-224210-s1\` (not committed; the run is `py -3 tools/game_checks.py --slot 1 all mapreveal wpauto hotkeys stashpages`). Plugin verbs: `mapcells`, `reveal`, `wpobj`, `travel`, `stashprobe` ([Harness commands](#harness-commands-gameplay-without-input-pluginsrcharness_cmdscpp)).

| Row | Result | Note |
|---|---|---|
| Map reveal (R, MU2) | PARTIAL | the harness `reveal` (the R hotkey's call of D2R's debug Reveal Automap) returns, the automap layer list grows 1 -> 25, a second reveal adds nothing, the debug flag byte is kept. The picture did not change: `cheat goto` and the town arrive with the map drawn whole (`mapreveal_before.png` = `mapreveal.png`), and the cell count stays 8878. A fresh field level reached by walking was not tested. A first pixel-difference criterion passed on a moving NPC only and was removed |
| Waypoint auto-activation (WP2, WP3) | PASS | Cold Plains waypoint (number 1): bit set within 1.5 s at distance 3, still clear at distance 47 (negative control), set at distance 24 while walking up. Two players in one game were not run |
| Hotkeys X / R / C (UI4, CR5) | PASS (first port; the defaults are now X / L / K, see "Checks that no longer depend on the test character's history" below) | window-message presses reach InputService: X toggles (0->1->2 presses, pickup on/off/on), R reveals (+1), C with the cube closed is counted and ignored (transmutes 0, blocked 1), C with the cube open calls Transmute (transmutes 1). The cube-open state comes from the UI message `PanelManager:OpenPanel(<cube panel>)` and `ClosePanel` / `UnloadPanel`. The default keys can overlap D2R's own R and C bindings; not checked |
| Stash pages (GS5) | PASS | `add_shared_tabs = 7` in `d2rloader.toml`: an item created through ItemService lands in shared tabs 0-9, tabs 10 and 12 are refused. The personal stash stays one page; no Prev / Next / Sort / Mode buttons |

### Monster level, players scaling, Normal drops, leash (lane pa2-monsters, 2026-10-23, slot 1, background mode, plugin 0.54.0 + the lane's parts)

Run folders `<runs>\checks-20261023-010539-s1\` (parts on) and `checks-20261023-010836-s1\` (negative control, `mxl2012-core-off.txt` words `monlevel playersx normaltc leash`; not committed): `py -3 tools/game_checks.py all monlevel normaltc leash --slot 1`. The plugin's real-input watchdog saw 0 cursor changes and 0 focus changes.

| Row | Result | Note |
|---|---|---|
| Monster level (DF3, item 17) | PASS | stat 12 of spawned monsters equals the area's `MonLvlEx` in areas 2 / 76 / 111 in Normal, Nightmare and Hell, for a living class (18) and a lUndead class (0). Off: Normal monsters keep their own monstats level (28 and 2 in area 2, where the area level is 1): FAIL |
| Players scaling (DF7, MP3) | PASS | 8 monsters in Hell at `players 1` and `players 8`: mean life x4.49 (Median 4.50), experience 450 / 450, level 100 / 100, players stat 1 / 8. Off: the `mxl` line says off and the checks fail on the line |
| Normal-difficulty drops (item 18) | PASS | a Normal kill of a level 6 monster hands the class getter level 6; a Nightmare kill of a level 52 monster level 52. Off: no lookups traced (the trace hook is only installed with the part) |
| Leash (item 19) | PASS | the mercenary moved 20 / 30 / 36 sub-tiles from the player walks back; at 44 / 47 / 60 it warps (distance drops 25 / 32 / 39 within one sample). Off: it walks back at 44 / 47 / 60 |

Not run: summons and the AI 112 / 107 followers (only the mercenary is checked), a second real player, the Baal throne delay, the items rolled by the stepped Normal class. Moving the player to make the distance pulls the mercenary along at once (that is how the first probe misled); the harness moves the mercenary instead.

### Gamble window and small engine rules (lane pa2-gamble, 2026-10-23, slot 3, background mode)

Run folder `<runs>\checks-20261023-003647-s3\` (not committed; `MXL_RUN=lane-pa2gamble py -3 tools/game_checks.py --slot 3 all mxl gamble enginegaps`). New harness verbs (server side): `gamble` (the player's gamble offers, player data `+0x108`, the same item lines as `shop`, then `gamble offers N`) and `gaps` (the bytes at the hit-20 floor and the recast guard, and the player slow floor through the hooked entry `0x449f40`).

| Row | Result | Note |
|---|---|---|
| Gamble offers (audit item 16, IT10) | PASS | Gheed opened through `interact 147` and the Gamble line of his menu (handler `0x112c80`), then the same request twelve more times through `pkt 38 02 ...` (packet `0x38` kind 2 with Gheed's id): every window has 32 offers (13 x 32 = 416) in 32 distinct cells of page 0, a ring (`rin`) and an amulet (`amu`) in each, 311 magic, 101 rare (242 per mille; Median's chance is 25000 per 100000), 4 unique, no set item, and no window equals the one before. Negative control (`mxl2012-core-off.txt` with `gamble`): 14 offers per window and the check fails, so 14 is D2R's own count |
| Hit 20 floor, recast guard (audit item 21) | PASS (bytes) | `gaps`: `0x45edce` reads `31 db 85 c0 0f 4f d8` and `0x56f859` is 13 x `90`; with the off word `recast` the guard keeps `e8 52 59 dc ff 85 c0 0f 85 b9 02 00 00`. The effect is not tried in play: it needs a skill whose calc comes out 0 or less (hit 20) and a srvdofunc 47 skill cast twice |
| Player slow floor (audit item 21) | PASS | `gaps` at difficulty 0 / 1 / 2 (`h difficulty n`): -12 / -25 / -50 through the hooked entry |

Off words are letters only (digits are dropped when `mxl2012-core-off.txt` is read): the hit-20 floor is `hitfloor`, the Worldstone / Throne object hook is `worldstone`.

### Checks that no longer depend on the test character's history (lane checks-robust, 2026-10-23, slots 1 and 3, background mode)

The release suite (0.54.0, runs `checks-20261022-212141-s1`, `-212441-s3`, `-2256*-s3`) failed checks that pass on a fresh character. The causes were in the checks, the state the earlier checks leave, or the stored settings of the install; none in the game rules the checks test, except the stored hotkeys (below). Run: `py -3 tools/game_checks.py --slot N all respec itemevents medianai medianai_ctl tyrael resistcap avoidcaps classlock bonusdrops summoner vendors itemskills nocorpse deathcrash sprint hotkeys manarules`, once on slot 3 (character `MxlBarb`, level 27 after the `respec` / `xp` checks) and once on slot 1 (level 150, different gear, stash and merc history).

| Check | Cause of the failure | Fix |
|---|---|---|
| respec | the check compared the unused stat points with a fixed number; a character that has spent points (strength 90 / 150) refunds more | `before` / `after` base stats 0-3 are read; the refund is the sum of the differences, and `unused after = unused before + refund`; the stats and stat 4 are put back afterwards |
| tyrael, vendors (Gheed "no menu") | the character was dead or the NPC click was lost; a dead character cannot talk | `npc_menu` revives first, then retries (close menu, interact, spawn a copy of the NPC, wait 30 s then 15 s) up to four times |
| avoidcaps, resistcap, classlock ("no mercenary could be hired") | (1) `itemevents` set life to 100 for its measurement and then wrote the life stat of a character that had died: the server unit stayed in mode 17 while the client believed it alive, so hits, menus and hires did nothing and Esc only paused the game (zombie death); (2) `medianai` leaves 30 unkillable dark nephalems (class 1239) in Blood Moor, which killed a level 150 character within two seconds of `cheat goto 2` | `revive_if_dead` (life 0: Esc every 3 s; zombie: Save and Exit + Play puts the character in town alive); `itemevents` puts life back; `ensure_merc` revives, sets gold and quest 2, tries `hire 150 n` for the free entries and spawns Kashya when missing; `clean_area` (used by `fight_ready`, `medianai`, `medianai_ctl`) kills what can be killed and starts a new game when something survives |
| bonusdrops | quest 13 / 25 and the flags (quest 47 bits 1 / 2) were already set by an earlier run, so the kill handler never ran or the catalyst was not re-issued | `clear_quest_bits` resets quests 13 / 25 and the bits before the first kill and the quest before the second |
| sprint | the character's stamina stats (max, recovery 28, drain 154, skill percents 162 / 163, per-level and by-time gains 241 / 242 / 294 / 295) changed the run time; the run toggle R is the character's own setting and survives a restart; the samples of stamina and of the frame were two replies apart | the wrapper zeroes the bonuses, sets Median's 50 points and restores everything; `state` reports `frame`, `stamina`, `maxstamina` in one reply, and the check asserts Median's rules (pa2-stats, audit item 15 / SK7) per frame and exactly: running -120 raw per frame (107 frames from full), walking +37, standing +50 (refill in 253-261 frames), a run starts with 2 points, state 136 fills, R gives one run and one walk. Nothing was loosened; the R-toggle step needs open ground and a `state` reply takes 0.6 s, so it goes to the Rogue Encampment, clicks the far points first (a click 8 units away is over before the first sample), accepts mode 6 (town walk) as walking, and goes back to Blood Moor; run/walk speed is the fastest unbroken stretch of samples (whole-unit positions a few frames apart are 25% off per pair); the 2-point run start also tries shorter paths |
| resistcap | slot 3's character wears an item with Median stat 184 (damage taken -25% after resistance, stat 369 here) that cut the 90% cap's share to 75% | the check zeroes stat 369 of player and merc and puts it back, and judges `_reduce(want, stat 184)` of what the gear still gives |
| (all checks) | `leave_and_reenter` left `in_game` False when the Save and Exit click did not leave the game, so every later check was BLOCKED "not in a game" | it restores the flag and returns False; `clean_area` then goes on in the same game |
| itemskills (table half) | `mxl2012:` prefixes on the skill name cells: 3844 of ~6000 parameters compared, "mismatches 0" but FAIL on the count | `item_skill_audit.py` matches rows by `strings_ns.bare`; the criterion is mismatches plus "every table with skill parameters contributed" (6054 parameters, 10 of 10 tables) |
| summoner | `medianai` left class 1239 in Blood Moor: "Summoner 250: modes [1]" | `clean_area` (above) |
| deathcrash | a merge had put the `nocorpse` body inside it, and it ran in town (a player cannot be hurt there: `result=0`) | `nocorpse` is its own check, `deathcrash` revives, goes to Blood Moor, hits up to five times and judges by the player's mode, not by the hit's result line |
| nocorpse | the ground gold piles were compared between Blood Moor (before) and the town (after the respawn) | compared only inside the same area |
| itemevents | (1) the life-on-kill gain was read before the heal landed; (2) after the merge of pa2-monsters (monster level by area) a spawned monster has 3-7 points of life, so the 50-point thorns event killed it (life 0 is not `a - 50`), and a monster next to the character may fire the event a second time | (1) polls for up to 1.6 s; (2) the monster is given 2734 points of life before the event, and the loss is judged as a whole multiple (one or more) of 50 points |
| manarules (pa2-stats) | `standing` counted only mode 1, but a character that has just arrived in an area (`cheat goto`) stays in mode 5 (town neutral) until it moves: 0 frames, "recovery None" | standing = modes 1 and 5 (the rule is the same, audit item 15) |
| hotkeys | see below | see below |

Hotkey defaults. travel.cpp (PR #113) registered `mxl_pickup_toggle` X, `mxl_map_reveal` R, `mxl_transmute` C. In D2R, R is the run / walk toggle and C the Character screen (the character's `<name>.key` file: R = action 35, C = action 1, V = action 45), so one press did two things; the Median install on the test machine keeps its keys in `preferences.json` (nopickup 0x58 = X, revealmap 0x4c = L, transmute 0x56 = V) and V is a D2R action too. New defaults: **X** auto pickup (Median's), **L** map reveal (Median's), **K** transmute (the free key next to Median's V). The check reads the registered bindings from `h travel`, requires them to be the defaults, requires that none is in the D2R key file (57 bound keys), presses each key and requires that only its own counters move, presses R and C and requires that no plugin counter moves (with a Character screen screenshot), and drives the transmute key with the cube closed (counted, blocked) and open (transmutes 0 -> 1).

Stored bindings. D2RLoader writes every registered action's key into `<game>/d2rloader/config/input-bindings.toml` the first time the plugin registers it (`primary_key = 82` for R, `67` for C), and keeps it: changing a default in the plugin does not reach a player who already ran an older build. Slot 3 still had R and C stored, so the first run after the change failed with `mxl_map_reveal is bound to R` and the plugin's reveal swallowed the run toggle (sprint saw the first R press give no run). `tools/install_mod.py` now drops the two stored entries of the first port's defaults (only when the stored key is still the old default) so the next start registers the new keys. Players who rebound an action by hand keep their key.

Results of the final full run on both slots (the code of this commit, merged with main after PR #124):

| Check | Slot 1 (level 150, stash and merc history) | Slot 3 (level 27 after `respec` / `xp`) |
|---|---|---|
| respec | PASS | PASS |
| itemevents | PASS | PASS |
| medianai (all users act) | PASS | PASS |
| medianai_ctl (controlled branch) | PASS | PASS |
| tyrael | PASS | PASS |
| resistcap | PASS | PASS |
| avoidcaps | PASS | PASS |
| classlock | PASS | PASS |
| bonusdrops | PASS | PASS |
| summoner | PASS | PASS |
| vendors | PASS | PASS |
| itemskills (every table has parameters) | PASS | PASS |
| itemskills (unique parameters) | PASS | PASS |
| deathcrash | PASS | PASS |
| nocorpse | PASS | PASS |
| sprint | PASS | PASS |
| hotkeys | PASS | PASS |
| manarules | PASS | PASS |
| **Total** | **18 / 18 PASS** | **18 / 18 PASS** |

Run folders `checks-20261023-044022-s1` and `checks-20261023-044022-s3` (both 0 new crash files). Before the fix of bug #33, four of the long chains on slot 3 ended in the goblin crash; afterwards 120 goblin kills in a row on slot 1 and both final chains ran through.

Fixed: the intermittent client crash after a goblin kill, docs/bugs.md #33.

### Release 0.55.0 suite: the 9 FAIL and 4 BLOCKED rows (lane release-055-fixes, 2026-10-23, slots 1 and 3, background mode)

Cause of every non-pass of the first 0.55.0 run (88 checks; 94 PASS / 9 FAIL / 4 BLOCKED):

| Check | Cause | Kind | Fix |
|---|---|---|---|
| damagered, steadyaim, trophytimer, restrictitems, funcslots, nodurability (slot 1) | One shared cause: the emptied field leaves a **town NPC as the nearest monster**. `hit`'s default attacker and `kill` / `cast ... nearest` took the NPC (Warriv, Gheed), so no hit landed; a full backpack made the equips fail; the Steady Aim counter leaked from steadyaim into restrictitems; feral_strike needs an axe or a sword in hand and the melee target wandered off between cast and hit frame; Normal-difficulty level 1 monsters almost never hit a level 150 character (0 - 1 life points in 20 s, 13,000 in Hell) | game harness (the hit verb) and checks | plugin `h hit` default attacker is now the nearest live monster that is neither the mercenary nor an NPC (`NearestFighter`); the checks clear the pack first, clean the Steady Aim counter and state (`aim_clean`), use `tough_target`, wield an axe or sword, freeze the melee target (state 1) and spawn the get-hit attackers under `h difficulty 2` |
| levelcap | Not a game bug. The check piled up 2327 stat / 567 skill points of earlier checks; Median's own save fields are 11 bits (2047) and 9 bits (511) and D2RLoader's extended mode follows CSvBits and saturates | check | realistic totals (a level 150 character earns 745 / 149); the check reads and reports the widths ([save-format.md](save-format.md), [unported.md](unported.md)) |
| itemrolls, allqualsockets (BLOCKED) | `itemroll` gained `identified=`, `qualities=`, `automagic=` fields; the regexes did not allow them | check | regexes accept extra `name=value` fields |
| restrictitems | Behaviour is Median's (cast refused without Steady Aim code 4, allowed with counter 1 code 0, item cast on kill fires both times); the pass condition compared the wrong counters | check | pass condition |
| absorb | The first probe read 0 healed before the damage reduction settled | check | probe retries up to 5 times like `hit()` |
| craftflags (slot 3) | The check switched the character to an assassin (`class 6`); with any class other than its own the harness cannot place an item in the cube ("placing failed"), so no recipe matched | check | the setter row of the character's own class is used (6369 + 19 per class: ass, pal, dru, nec, sor, bar, ama) |
| gamble, vendors ("Gheed's menu did not open") | NPC interaction depended on the arrival position | check | `npc_menu_near`: walk next to the NPC, retry, then spawn a copy, three rounds |
| heat, sprint (slot 1, found in the full run) | heat: the drain per tick is a share of the **maximum** mana, so a fixed 100-point bar was gone in one tick on the 6300-mana character; sprint: the slowest walk leg read 0.52 against 0.62 units per frame | check | heat sets the full bar; sprint repeats a walk leg that does not give the expected ratio |

Final runs (same code, the two check edits for heat and sprint re-run on both slots afterwards): slot 1 (level 150) 106 PASS / 0 FAIL, slot 3 (level 34) 108 PASS / 0 FAIL of 111 rows each; the other rows are the standing REVIEW (short aliases, tooltip: screenshots to read by hand) and PARTIAL (map reveal: the level is already drawn whole on arrival) rows. Run folders `checks-20261023-062317-s1`, `-064559-s1`, `-071122-s1` and `checks-20261023-062317-s3`, `-064419-s3`, `-070748-s3`.

### Stash pages: personal page 2 (lane stash-pages, 2026-10-23, slot 3, background mode, plugin of this branch)

Throwaway character `StashPg` (`MXL_CHAR=StashPg`), saves backed up before each step; design in docs/stash-pages.md.

| Step | Result |
|---|---|
| `game_checks --slot 3 all stashpage2 stashpages` (final DLL) | `stashpages` PASS (shared tabs 0-9 accept an item, 10 and 12 refuse); `stashpage2` PASS (2 items on page 2, the stock stash has the "1 / 2" strip, right arrow opens the page 2 panel, the arrow on page 2 returns to the stock stash, an item moves 2 -> 1 -> 2, clean-up). Engine `BC_ASSERT` lines in d2rloader.log also appear in other lanes' runs (startup / shutdown) |
| Persistence | page 2 filled with 1x1 runes (392 items), Save and Exit, reloaded: 392 present, nothing lost |
| Load without the provider | `mxl2012-core-off.txt` = `stashpages` with items on page 6: the load stops with D2RCore's two ERROR lines, the `.d2s` hash is unchanged afterwards |
| Strip with the part off | `stashpages` off: the stock stash opens without the "1 / 2" strip (screenshot checked) |
| X / Esc / arrows | switching 1 -> 2 -> 1, X on either panel closes the stash, Esc on page 2 returns to page 1: as designed |

Not tested: TCP/IP with two clients (page replication is D2RLoader's); personal pages 3-10 and Sort are not built (`docs/unported.md`).

### No durability in the UI (lane no-durability, 2026-10-23, slot 2, background mode, plugin 0.55.0 + durabilitytip / repairui)

`py -3 tools/game_checks.py --slot 2 all nodurabilityui nodurability itemrolls vendors potions`: the new check and the four checks
that touch what it changes. Control run: `mxl2012-core-off.txt` with `durabilitytip repairui` (the tbl2json ethereal text is data and stays).

| Check | With the parts | Off words | Evidence |
|---|---|---|---|
| `nodurabilityui` (audit IT1, UI half) | PASS | FAIL | stats 72 / 73 > 0 on a Field Plate, a Battle Sword, a magic and an ethereal Field Plate; their descriptions (`itemdesc`, D2R's own builder) have no durability / repair / indestructible text; the ethereal one reads `Ethereal`, not `Ethereal (Cannot be Repaired)`; Charsi's menu ids are 0xd35, 0xd44 (no 0xd06), Gheed's 0xd35, 0xd44, 0xd46; the panel strip below the item grid, Charsi vs Gheed, differs by 0.12 (off words: `Durability: 48 of 48`, 0xd06 in Charsi's menu, strip diff 5.97) |
| `nodurability`, `itemrolls` (ethereal keeps +25% and the 75% durability), `vendors`, `potions` (2 rows) | PASS | | unchanged behaviour |

Screenshots (run folder `checks-20261023-093545-s2`): `nodur_tooltip_armour.png` and `nodur_tooltip_weapon.png` (the inventory
tooltip of a Field Plate: Defense, Required Strength, Socketed, no Durability line), `nodur_charsi_menu.png` and `nodur_charsi_panel.png`
(the plain trade panel, no Repair buttons), `nodur_gheed_menu.png` / `nodur_gheed_panel.png` for comparison.

### Buff / debuff icon bar (lane buff-icons, 2026-10-23, slot 3, background mode, plugin 0.55.0 + the lane's part)

`MXL_RUN=lane-bufficons py -3 tools/game_checks.py all bufficons --slot 3` (evidence `checks-20261023-093022-s3`, 0 new crash files, 0 cursor changes, foreground changed 0 times).

| Check | Result |
|---|---|
| `bufficons` | **PASS** (counters): states 32, 101, 26 in the left group and 89, 19 in the right group, slots 0..n-1 in table order; first icon at x = 460, y = 780, 32 px (1600 x 900); timers {32: 597, 101: 598, 26: 598, 89: 598, 19: 598} s -> {592, 592, 592, 593, 593} after 5 s; hover on state 32 (`mxl2012:SkillnameMaenadFrenzy`): 1 tooltip line; 0 refused overlay requests, 2702 rectangles per frame; the icons go when the states are cleared; all five states reached the client through D2R's own packets (no `cstate` needed) |

**Not seen on screen.** The loader's overlay is not part of the PrintWindow capture of a background window (the dungeon lockout timer had the
same result), so the screenshots `bufficons_bar.png`, `bufficons_probe.png` and `bufficons_hover.png` in the run folder
(`<runs>\checks-20261023-093022-s3\`) show the HUD without the bar; the magenta probe rectangle, whose overlay calls all return
Success, is not in the picture either. The check therefore asserts counters only. **By hand** (normal window, foreground): enter a game, press `~` for
the console, `mxl` should say `buff icons on`; cast a self buff or run `h setstate player 32 1`; the icon bar sits just above the belt next to the orbs
(left group beside the health orb, curses on the right), a countdown under each icon, a tooltip box when the cursor is on an icon. Tell me: the
placement at your resolution, whether the art and tints look like Median's, and the frame rate in a fight with many states.

### Town rules, charms, area levels, D2 bugfixes, minimized window (lane p4-verify-b, 2026-10-23, slots 1 and 3, background mode, plugin 0.56.0)

`py -3 tools/game_checks.py --slot N all cain scrollportals towncast npcheal tplock charmlimit arealevel bugfixes`, run folder `<runs>\checks-20261023-195127-s1` (slot 1). Two earlier runs (`checks-20261023-194007-s1`, `checks-20261023-194334-s3`) aborted in `scrollportals` on the focus watchdog until the minimized-window give-back below worked. Control run with `mxl2012-core-off.txt` = `npcheal tplock` (slot 3): `checks-20261023-200935-s3`.

| Check | Result |
|---|---|
| `cain` (bug #23) | **PASS**: `menu list` has the 3 lines of Cain's popup, no `menu record is full` log line. The picture of the popup is `cain_menu_page.png` of `checks-20261023-190644-s1` (check `cainsub`): TALK / CRAFTING MATERIALS / CANCEL, read by eye |
| `scrollportals` (#17) | Historical result before bug #10 fix: **PASS** with the window minimized: the check minimizes the window (`SW_SHOWMINNOACTIVE`) before its first screenshot and `game_ctl.restore_noactivate` brings it back with `SW_SHOWNOACTIVATE` and sends it to the bottom of the z-order. D2R activates its own window about a second after it is restored. The foreground goes back to the window that had it (`game_ctl.RESTORES`, log line `focus handed back`). A plain `SetForegroundWindow` is refused for this process (returns 0), so the give-back attaches the thread's input queue to the two windows' threads for the call (no input is sent), and the watchdog of game_checks lets those milliseconds pass (`FG_GRACE_UNTIL`). The old BLOCKED "game window minimized or has no size" is gone |
| `towncast` (SK4) | **PASS**: 3 class-free InTown skills start in the Rogue Encampment, 12 skills without InTown are refused there (the unit stays in its town-neutral mode 5; the usability code `0x33f360` does not look at the town) and all 12 start in the Blood Moor. The 8 other InTown skills are Warlock skills (`usable=3` for the test character), not judged |
| `npcheal` (NPC1) | **PASS**: 42 of the 43 NPC classes heal on talk (251 could not be spawned). Control (word `npcheal` off): 6 heal, 37 do not |
| `tplock` (UQ5) | **PASS**: levels 61, 73, 171 refuse (refusals 0 -> 3), the Blood Moor opens a portal. Control (word `tplock` off): level 61 opens a portal |
| `charmlimit` (IC5) | **PASS**: carry1 unique 106 and the limited uniques 7, 8, 9: the second copy is refused; unique 1773 without a rule takes two (unique 82 now refuses a second copy too, also with the part off; not analysed further, see docs/d2r-addresses.md section 22b). Lane carry1-fix (0.66.0) adds: uniques 7, 8, 9 (three different carry1 uniques) are all placed with `item inv`, a second copy of unique 7 is refused with `item inv` and with a ground pickup (packet 0x16, to-inventory flag), unique 8 picked up from the ground next to the carried 7 lands, unique 106 (only D2R's own rule) is placed next to unique 7 and its second copy refused. Runs: `checks-20261025-175642-s1` (fix on: `mxl`, `charmlimit`, `uniquelimits` all PASS), control `checks-20261025-175526-s1` (`MXL_CONTROL=uniquecarry`): the control places only the first and refuses the different ones on both paths |
| `arealevel` (MU3, data part) | **PASS**: monster levels of areas 216, 205, 204, 137, 3 in Normal and Hell equal levels.txt MonLvlEx |
| `bugfixes` (OT4) | **PASS** in the control run (in the first run my own assertion failed: the max resist caps every value from 75 up at the same damage): life / mana 60000 hold, resist 286 / 300 / 1000 / 65586 / 2^31-1 give the damage of 255, hits of 1e9 / 1.5e9 / 2^31-1 take exactly that much, death in the wolf / bear / might states leaves no state, alive after the respawn |

TCP/IP with two clients (slots 1 + 3, background input, LAN-only unlisted host): the session runs and both clients show the stash pages ready, but the harness cannot run stash verbs on the joiner (game-thread runner refuses), so the shared stash row stays `verify` (docs/unported.md "Shared stash in TCP/IP"). Not tested: the str / dex glitch and whirlwind chance-to-cast (OT4).
### Release suite on main (eccc3ad): slot 1 cluster, uniquelimits, engine asserts (lane suite-regressions, 2026-10-23, slots 1 and 2, background mode)

**The slot 1 cluster was the character, not the code.** The 13:45 run had Akara / Cain / Tyrael menus not opening, every harness cast doing nothing, zombie clicks
not hurting, and Griswold's Heart missing, on slot 1 only; both slots had the same plugin and data (hashes equal, same `d2rloader.toml` and off words).
`h state` showed `item id=62 code=143` in the player's state line: **an item held on the cursor** (a unique charm, left by an earlier `uniquelimits` run and
saved in the character). The engine's busy test (`0x4249f0`, nonzero with an item on the cursor or a trade open) refuses every skill use and every NPC
menu while the cursor is full, which is the whole cluster (the casts printed OK because the harness only calls the cast function). Dropping the item
(client packet 0x17 + item id) cured all of it; the check list then passed on slot 1 (65 PASS of 67). The character was backed up first
(`<runs>\save-backup-20261023-144201-s1`); no other character was touched.

`game_checks` now refuses and repairs that state (`clean_start_state`): before the first check and again before every check it revives a dead
character, ends the shapeshift states (140, 236, 278, 300), and drops an item held on the cursor (`release_held_item`, 3 tries, raises when the item stays);
a character that **started** dead / shapeshifted / holding something gets a REVIEW row ("Start state before the first check"), one left in that
state by the check before gets a REVIEW row naming that check, and a state that cannot be repaired gives BLOCKED rows instead of a wall of FAILs.

**uniquelimits "second copy of a single-copy unique should be refused (refused 2 -> 2, in pack 1)" was the check.** The ground-pickup part dropped the
first copy and then removed *its own carried copy* (`remove <code> 1` takes the first item of that code anywhere), so the second pickup found an empty
pack and nothing was there to refuse. The check now leaves the carried copy alone (a far drop stays; `reset()` clears leftovers), and reads back `iflags` of
the picked-up item (mode 3 or 5) and the pack count instead of the counter alone. The plugin rule was fine: the check passes on slot 2 after the change (`refused` moves on the second copy).

**Engine asserts** (`d2rloader.log`; "Continuing because assertion dialogs are disabled"; found by time stamp against the `hcmd` lines of the run log,
each one then reproduced alone with a probe where noted):

| Assert | Trigger (check / action) | Cause | Status |
|---|---|---|---|
| `nDesc >= 0 && nDesc < skillDescTbl.size()`, then `false` | tooltips of an item whose property names skill 2001 / 2004 / 669 / 2073 / 2076 / 741 (`tooltiptext`); a cast of skill 36 (Fire Bolt) or 126 (Bash) by `casts` | those skills have no `skilldesc` row in Median; the client reads the row of a skill when it is cast or named | **fixed** for the 8 skills: `txt_migrate.py blank_skilldesc` gives them a `blank` row (no name, Median's own shape of `avoid`); the other 1049 skills with ItemEffect 1 and no skilldesc assert once per cast in the same way (not changed: a row each changes the skill menus' lists) |
| `nMissile >= 0 && nMissile < NumMissileStats` (x2) | `kill` of class 2054 (unformed phantasm, the Summoner check), `monlevel` | Median's curse skills have `cltdofunc 30` but no `cltmissilea` / `cltmissilec` (52 of the 75 curse rows; vanilla Amplify Damage has `curseamplifydamage` / `cursecast`), D2R's curse client function (0x2b05d0) reads both | **fixed** (p4-engine-b): `sigma_skills.cpp CltDoCurse` wraps the slot in place; a row without a client missile draws nothing (as D2Sigma's function does: Median's look is the state overlay) and returns 1, a row with one runs D2R's function. Check `cursemissile` (run `checks-20261023-182147-s1`): 0 asserts through all 52 bare rows, control (harness `cltdo <skill> orig`) asserts once with the chain `2b0670` ... |
| `nMissile >= 0 && nMissile < NumMissileStats` (x2, second source) | the kill of class 2054 on 0.63.0 (`checks-20261024-105541-s1`), and the spawn of the treasure goblin (class 2791, `leash`, `charmlimit`, `medianai`) | **not a curse and not the Summoner:** `asserttrace` (run `checks-20261024-141208-s3`) gave the chain `2b0e86 21854e 341740 217759 1a56e7` (the trace label `skill 2583 class 2791` is only the harness' last cast skill): the client skill start function `0x218030` calls the start table slot of a skill (`0x235f590`, slot 18 = `0x2b0df0`, which draws the skill's `cltmissilec`); 52 Median rows with cltstfunc 18 have no client missile, so the function reads `cltmissilec` = -1 and asserts twice per start, then returns 1 (the Summoner kill only had a goblin spawned in the same game) | **fixed** (p4-stability, plugin 0.64.0): `sigma_skills.cpp CltStMissileC` wraps slot 18 in place, a row without a client missile draws nothing (Median's look, no D2R visual) and returns 1 as D2R's function does, a row with one runs D2R's function; the `mxl` line says `cltstfunc 18 start without client missile`. Check `asserttrace` calls the slot for skill 66 (D2R's own function asserts, the table entry does not) and fails when the treasure goblin spawn raises an nMissile assert (run `checks-20261024-195658-s3`: PASS, no assert) |
| `nRadius > 0` | spawn of class 2791 (treasure goblin; `goblins`, `medianai`) | the goblin's skill is `skills_2511` (srvdofunc 65, a monster property aura: dmg% = aura), not 2580 as first written. D2R's area applier of the aura functions (0x4327d0 -> 0x4398b0) asserts when `aurarangecalc` (skill +0x84) gives 0; Median leaves it blank on its self-only auras, D2Sigma applies the state to the caster and then to nobody. The assert fired every aura tick (about 400 ms per monster) | **fixed** (p4-engine-b): `sigma_skills.cpp AreaAuraHook` skips the call for a radius below 1 (the applier does nothing for it anyway), the state on the caster stays. Evidence: harness `asserttrace` probe, run `checks-20261023-190745-s3` (treasure goblin spawn: no assert) |
| `nSkillCastId && nSkillCastId != 0xFFFFFFFF` | `medianai` / `medianai_ctl` (andariel_ai users 1693 Maghda, 1899) after a hit; also the pulse of skill 2583 | traced to the client `FUN_140216920` (0x216920): at each aura pulse it looks up the caster's aura-state stat list (state of skill +0xa0) and reads stats 0x15e / 0x15f / 0xca; when the caster has no list for that state it gets cast id -1 / 0 and the engine asserts. Data-driven noise of the aura states Median defines without the stat triple D2R keeps; no wrong behaviour | **traced, not fixed**: log noise only; a fix would have to add the stat list that D2R's own aura skills get, which changes the stat lists of Median's states |
| `nDirectionIndex < nDirections`, `MONFLAG_ENABLED` | `medianai` spawning every andariel_ai user (class 990; class 971 after the not spawnable 333); tagged to skill 2583 / classes 2798, 2791 in the server `MissMode.cpp` | the check spawns disabled / odd monstats rows; the missile-mode assert is a direction count of a missile with no directions on those classes; not reproduced by a plain spawn and not traced further | harness artifact / open |
| `i != warpDefs.end()`, `BC_VERIFY: ptWarp`, `BC_ASSERT: 0` | `cheat goto 16` (Median's level 16 has no Vis / Warp rows, vanilla has Warp1 4 / Vis1 12), goto 191 / 250 / area 134 (`areacycle`, `automap`, `mapmem`) | Median-only levels entered by `goto`: the DS1 warp tile of the level looks up a warp id that Median's `levels.txt` row does not carry (16, 134, 191, 250). Not a port defect: a real walk never gets there, only `goto` into the DS1 of such a level (control: `asserttrace` probe, same levels, `warprevisit`) | **explained**, harness-only (`goto`); no change |
| `nParamIndex < 8` | `enter` into a class 600 portal of a Median dungeon (`lockout`, `scrollportals`, area 251 / 253) | the portal's level parameter; not reproduced in this lane (the earlier lead, andariel_ai Maghda 1693 / class 1899, is the `nSkillCastId` family) | open, not reproduced |
| `wPrefix != 0 \|\| wSuffix != 0` | harness `item <code> q=4` / `q=6` (`tooltiptext`, `trophy`) | the harness builds magic / rare items without affixes | harness artifact |
| `activeUnit` | start of `assetpaths` | not traced | open |
| `nDesc >= 0 && nDesc < skillDescTbl.size()`, then `false` (same pair as the first row) | `enginegaps`: `cast 463 self` (drakemaw, a monster skill, to prove the recast guard) | skill 463 has no `skilldesc` row; the client reads the row of a cast skill. A harness cast of a monster skill, not reachable by play | harness artifact, new trigger (suite-main-060, plugin 0.63.0) |
| `nStat >= 0 && nStat < statsTbl.size()` (`CmdAccess.h:1609`) | `signet`: the refused use of a Signet of Learning at the 400 cap (`use 01^` with stat 370 = 400, "the game refuses to use it") | the refusal path of the Median signet use reads a stat id outside D2R's stats table; the use is refused as wanted and nothing else is lost | open, new (suite-main-060), harmless so far |
| `input->IsValid()` (Domino `world.cpp:3251`, `dynamic_tree.h:257`) | `scrollportals`: `enter` into the class 600 portal of a summoning scroll level above 255 (seen once in two 0.63.0 runs, with the `nParamIndex < 8` family) | physics world of the client given an invalid body while the level changes | open, new (suite-main-060) |
| `BC_ASSERT: 0`, `ii < NUM_LEVEL_TYPES`, `sub.nCelNum`, `eLevelId > 0`, 2 x `statesTbl` | once per launch, on the way into the game | D2R reading Median's tables (states, level types) | open, constant |
| `s_StatsPool.IsEmpty()`, `m_allocated == 0`, `m_freed == 0`, ... | when the game exits or restarts (keybinds, Save and Exit) | pool leak checks of the engine | exit-only, ignored |

Other check fixes of this lane: the window capture puts a minimized game window back with SW_SHOWNOACTIVATE (the scrollportals run was BLOCKED once by
a minimized window: "game window minimized or has no size"; focus is not taken), and `assetpaths` waits up to 10 s for the spawned Corrupted Wereowl
(in two long suite sessions it was not in the unit list 2.5 s after the cheat and the check failed on "did not spawn"; alone it passes, and with the wait it passed in the final run).

Final runs on the fixed build (`py -3 tools/game_checks.py all <group> --slot N`, `group1.txt` on slot 1, `group2.txt` on slot 2, in parallel; folders
`<runs>\checks-20261023-171353-s1` / `-s2`): slot 1 **65 PASS**, 1 REVIEW (short aliases), 1 BLOCKED (`classlock`: `ensure_merc` was refused by the server for all 6
list entries in one of three full runs; it passes alone and in the other two runs, and in the rerun of `classlock casts medianai_ctl` on a fresh game: 3 of 3
PASS, with no `nDesc` / `false` assert at the cast); slot 2 **48 PASS**, 1 REVIEW (mystic orb tooltips), 1 PARTIAL (map reveal: the level was already drawn
whole). The first full runs of the day (before the fixes) were slot 1 with the cursor item and slot 2 with `uniquelimits` FAIL.

## Lane p4-engine-a: engine rules (plugin 0.57.0)

New checks (`tools/game_checks.py`, in `group1.txt` / `group2.txt`): `teleportgold`, `skillafford`, `hcdeath`, `meleenotarget`, `reqlevel`, `cubedrop`;
`enginegaps` now also casts Howl of the Spirits twice (recast guard). Harness verbs: `afford <id>`, `hc [on|off]`, `tpgold`, `modewatch start|stop|read`,
`peek`; `req player` prints level / str / dex; `gaps` prints `reqlevel_sites=`.

Control runs: `MXL_CONTROL="teleportgold afford reqlevel recast"` makes `game_ctl.harness_switch` write those words into `mxl2012-core-off.txt` for the launch;
the checks read the same variable and expect the old behaviour for their own word (`hcdeath` is controlled in a run of its own, because the control leaves a
Hardcore character dead and its saves are restored afterwards). Do not run `hcdeath` with `hc on` followed by Save and Exit and Play: the character is then a
dead Hardcore one that cannot join a game.

When saves are touched from a shell, always pass `--slot N` / `MXL_SLOT=N`: without it the default is slot 1's save folder.

Runs of the lane on plugin 0.57.0 (slot 2): `<runs>/checks-20261023-211144-s2` (normal: mxl, enginegaps, teleportgold, skillafford, meleenotarget, reqlevel, cubedrop: 7 PASS),
`checks-20261023-211416-s2` (control `teleportgold afford reqlevel recast`: 4 PASS with the old behaviour), `checks-20261023-210132-s2` (hcdeath) and
`checks-20261023-210509-s2` (control `hcdeath`). The two hcdeath runs are from the build before the last `afford`-verb fix (the Hardcore code is unchanged by it).

## Lane p4-leftovers (plugin 0.61.0): Soulstealer heal, drop item level reader, hire robustness

Slot procedure: `py -3 tools/game_slots.py lock 2 p4-leftovers`, `py -3 tools/install_mod.py --slot 2`, `MXL_RUN=p4-leftovers py -3 tools/game_checks.py --slot 2 all <checks>` (the run
releases the lock at its end, so the lock is taken again before each install).

| Item | Check | Result |
|---|---|---|
| Drop item level (audit IT16, DF10) | `dropilvl` (rewritten: reader test with `ilvl=` 1 / 33 / 77 / 100 / 150 / 255, then drops in areas 2 and 76 in Normal and Hell, with and without a town trip; item level must equal the area level and the monster level) | PASS, run `checks-20261023-221828-s2`. The old PARTIAL came from the harness's reader (`0x3730d0`, a field that stays 101); `0x36ccf0` reads the real level. Median's rule (area level) was already what D2R's `0x43e8a0` does, so no hook |
| Soulstealer (audit DC5) | `soulstealer` (new): a boss at 30% life kills the harness player (1 life point, so life leech cannot refill the boss), boss life must rise by 10% of max and the plugin counter by one; an ordinary monster must gain nothing | PASS, run `checks-20261023-221828-s2` (Zagraal +10.0%, Kabraxis +10.0%, control monster +0%); control with the part off (`mxl2012-core-off.txt`: `soulstealer`, or `MXL_CONTROL="soulstealer"`) PASS, run `checks-20261023-221613-s2` (bosses +0.0%). The Leoric (class 2907) refills to full life on its own before the death call, so it is left out of the check; the 40% heals are not ported (`docs/unported.md`) |
| `classlock` BLOCKED once ("no mercenary could be hired") | `classlock`, `hiregates`, `resistcap`, `avoidcaps` (all use `ensure_merc`) | PASS, run `checks-20261023-222736-s2`. The cause of the one refusal (run `checks-20261023-171353-s1`, all 6 list entries refused) was not reproduced; the hire verb now logs the NPC distance, the player mode, the gold and the current mercenary id, can remake the NPC's list (`reopen`, used by `ensure_merc` for every hire), and `ensure_merc` tries a hirer copy next to the character and another area before the next try |

## Lane p4-ww-morph (plugin 0.63.0): whirlwind chance-to-cast, real shapeshift death

Slot procedure: `py -3 tools/game_slots.py lock 3 p4-ww-morph`, `py -3 tools/install_mod.py --slot 3`, `MXL_RUN=p4-ww-morph py -3 tools/game_checks.py --slot 3 all <checks>` (the run
releases the lock at its end, so the lock is taken again before each install). `MXL_CONTROL=wwproc` makes the control run (off word written to `mxl2012-core-off.txt`).

| Item | Check | Result |
|---|---|---|
| Wrong skill ids in lane p4-quests-verify (1234 / 1303) | none (`strdex`, `bugfixes` docstrings) | Not a lookup bug: 1234 / 1303 are the `*Id` values of Median's original `skills.txt` (Whirlwind, Werebear Morph); the build renumbers those rows by +72, so the built ids are Barbarian `whirlwind_2` 1306, Druid `werebear_morph` 1375, `werewolf_form` 1380, `wereowl_form` 1364. `_skill_ids_by_name()` reads the built table and is right. |
| Whirlwind chance-to-cast (audit OT4) | `wwproc` (new): Barbarian `MxlBarb`, ring `stat 198` / `stat 195` = Fire Bolt level 5, 100 %; 4 spins of 1306 through 5 monsters vs 8 normal attacks, Fire Bolt missiles (class 58) counted; `mxl` line and counter checked | PASS, run `checks-20261024-012847-s3` (11 / 13 Fire Bolts in the spins, 4 / 6 from the attacks; 24 casts let through, 0 refused). Control `wwproc` off, run `checks-20261024-013722-s3`: line `off`, spins 0, attacks 5 / 6. Cause: D2R's `0x5896e0` refuses the cast while the caster has state 54 and a spin holds it; the plugin clears the bit around the cast when state 174 is on. |
| Real shapeshift immortality (audit OT4) | `morphdeath` (new): Druid `MxlDru` (created in the slot when missing), real `cast <id> self` of the three Median morph skills (weapon of type axe / sword / knife in hand, outside town), lethal hit, and Andariel as killer of the bear | PASS, run `checks-20261024-012847-s3`: death (mode 0 then 17), form state ends, Esc respawn gives a living character in area 1 without the form, for all three forms and the monster kill. D2R's code, nothing ported. |

## Lane suite-main-060: full suite on main (plugin 0.63.0)

Test-only lane. Runs on plugin 0.60.0 (slot 1 `checks-20261023-220521-s1` and `checks-20261023-224514-s1`), 0.61.0 (`checks-20261024-002546-s1/-s2`) and, as asked by the coordinator after #153 / #154,
on **0.63.0** (c2d85b0) with `group1.txt` on slot 1 and `group2.txt` on slot 2 in parallel. The run `checks-20261024-000518-s1` is void from about 00:11 (lane p4-ww-morph ran commands on slot 1 without `MXL_SLOT`). **Final pair on 0.63.0: `checks-20261024-120836-s1` PASS 82, FAIL 0, BLOCKED 0, PARTIAL 0, REVIEW 5; `checks-20261024-120837-s2` PASS 67, FAIL 0, BLOCKED 1 (`mapreveal`, by design after debug mode), PARTIAL 1 (`meleenotarget`), REVIEW 11** (the REVIEW rows are the start-state notes and two screenshot checks).

Fixes of the checks (all in `tools/game_checks.py`, no plugin change):

| Check | Problem | Fix |
|---|---|---|
| start state of every check | the inventory panel left open by a check covers the right half of the client: `monhover` and `levelcap` failed on projected clicks, `statorder` crashed the game (access violation and `m_listWidget` assert) | `clean_start_state` closes the panel (`i`, then Esc) and says so as a REVIEW row; it also notes when the worn items changed since the check before |
| `collidetypes` | the nearest unit was Deckard Cain (unkillable) or the monster moved | uses the spawned monster by id, 14 tries per type |
| `bugfixes` | `hit player` without an attacker is a hit of the player on the player (ignored) | spawns an attacker; saves and restores the pools; the bounds only exclude a rollover (the mana of a long session may start a regen apart) |
| `teleportgold` | the purse-full case hard-coded 160000 gold (a level 16 character); a stray pile of an earlier check was taken too | the cap is 10000 x level (D2R's gold limit, `0x34b320`); strays are tolerated |
| `meleenotarget` | mana regenerates at 8191 pools: the cost hid in the sample | starts from the maximum, waits 3 s after each click, takes every worn item off |
| `tplock` | one run: the first cast was refused by the verb (character still busy), refusal counter 2 instead of 3 | the cast is repeated once; diagnostics (usable code) in the log |
| `npcheal` | life 8190/8191 after the heal counted as "not healed" (and a talk that does not start) | full life within 1 %, one retry with a fresh NPC |
| `strdex` | needs the armor's level (a level 19 character): the stats stayed inactive; the rare ring has random affixes | sets the level 90 for the check; the ring may add resistance |
| `mapreveal` | FAIL when the level is already drawn whole on arrival; left the character in Lut Gholein (`skillafford` then read the column value, formula cost 256) | PARTIAL for that case; goes back to Act 1; `skillafford` starts in a field level |
| `morphdeath` | Andariel hit a level 2 bear for ~16 and stopped; Save and Exit took longer than 9 s after a long session | life 12 for the monster kill; `switch_character` waits up to 42 s |
| start state of every check (stances) | a Way of the Phoenix / Spider / Gryphon / Raven cast of an earlier check stays on the character: Phoenix adds fire damage, mastery and max mana (`meleenotarget`, `bugfixes`, `skillscaling` failed in the full `group2.txt`) | `clear_stance_states()` takes states 308 / 309 / 332 / 783 off and notes it. State 105 (alignment) is left alone: the test character carries it from the start and with it off the casts of `replacedskills` did not start and the 2e9 hit of `playerdeath` did not land (run `checks-20261024-085517-s2`) |
| `hitfloor` | the missile's damage at skill level 0 is the character's flat damage: the earlier runs had it from a Phoenix left on by another check; with the stance taken off (or in a fresh game) all five level 0 shots did nothing | sets flat damage (stats 21 / 22, 48 / 49, 50 / 51) for the shots and puts the values back |
| `mercrevive` | `kill nearest` killed a leftover class 2796 next to the mercenary, the mercenary stayed at 1 life | kills the mercenary by its unit id |
| `meleenotarget` (pool) | in the full `group2.txt` the pool falls by itself (idle dip 740-864 points in 1.2 s, no click), which hides the cost of a click; the usable code was read at a low pool (code 1 = not enough mana) | mana to the maximum before the usable code; an idle baseline: with an idle dip above 100 points the mana judgement is dropped and the status is PARTIAL (the attack modes are still judged) |
| `assetpaths` | the cheat line `mspawn corrupted_wereowl` is lost now and then (none in 11 s) | the cheat is sent once more |

Not regressions (start state, the check or the order of the group): `tplock` (one FAIL on 0.61.0, passed in later runs), `itemevents` (thorns 686816 vs 687200 once, passed alone), `statorder` (panel), `bugfixes` / `strdex` /
`skillafford` / `mapreveal` / `hitfloor` / `mercrevive` (order or start state, see the table), `npcheal` and `soulstealer` (a different NPC class or the boss 2049 fails in some runs, never the same set; 2049 fails with "heals counter 0 -> 0" while 1852 heals 10 %;
`npcheal` passed in the last pair).

Open, not fixed (the lane is test-only):

- **(solved by lane p4-stability: the `heat` check left Molten Core's stat 297 on the character, see "Lane p4-stability")** **The mana pool of the test character falls by itself in the full `group2.txt` on slot 2** (idle dip 740-864 points in 1.2 s, `meleenotarget` PARTIAL; in the earlier pair the plain click "paid" about 1540 mana and `bugfixes` read 58575 mana). `meleenotarget` passes alone and after `uniquelimits charmlimit arealevel bugfixes`; the stance states, the worn items and the player states (only 105) are not the cause, so some check in the middle of the group leaves something else (a stat list, a monster that drains) - not bisected.
- **(analysed by lane p4-stability: D2R's own, docs/bugs.md #34)** **An engine crash at the end of `group1.txt` on slot 1** (`checks-20261024-105541-s1`: `d2r-lastresort-crash-report (2026_10_24 01_55_42 UTC pid-31948).log`, access violation at `D2R.exe+0x7761DC`, generated 11:56:27 during `morphdeath`'s character switch to the Druid; the stack slots hold the string `data/hd/chicken/chicken_state_machine.js`, i.e. the game was loading an HD asset). The run ended without a `morphdeath` row; `wwproc morphdeath` alone (`checks-20261024-115748-s1`) and the full `group1.txt` again (`checks-20261024-120836-s1`) pass. One crash in three runs, not reproduced, not traced to a commit.
- Asserts (the `nMissile` one is fixed in plugin 0.64.0, see the table row for the start function): every assert of the final runs is a row of the table above. `nMissile >= 0 && nMissile < NumMissileStats` still fires once at the Summoner kill (class 2054) on 0.63.0 (`checks-20261024-105541-s1`, 11:08:52) although the table row says fixed by `cursemissile` (`cursemissile` itself has 0 asserts); the fix covers the curse client function, not whatever the kill of class 2054 reaches. `activeUnit` was not seen in these runs.
- `morphdeath` was BLOCKED inside the full `group1.txt` in the first runs of the lane (cut scene after `tyraelwalk` swallowing Esc and Save and Exit); `switch_character` now skips the cut scene and retries, and it passed in the last two full runs.

## Lane p4-stability: engine crash, nMissile assert, flaky checks (plugin 0.64.0)

Slots 1, 2 and 3, background mode. Plugin 0.64.0 = 0.63.0 + `sigma_skills.cpp CltStMissileC` + `translation_guard.cpp`; the harness gained `cltst` and `transguard`;
everything else is `tools/game_checks.py` and the docs. `tools/build.py` does not build the plugin (cmake does: `cmake -S plugin -B build\plugin -A x64`, `cmake --build build\plugin --config Release`);
a run of this lane that used an installed DLL older than the source was thrown away, every number below is from the 0.64.0 DLL (the `mxl` line of each run says `mxl2012-core 0.64.0`).

**1. Engine crash at `D2R.exe+0x7761DC` (`checks-20261024-105541-s1`, again `checks-20261024-183807-s1`).** The function is the handler of event type 0x10 of D2R's `UnitTranslationLayer`
event loop (`0x775fc0`); it reads `[[*event+0x70]+0x870]`, and the payload pointer was `0x8000003F0` (first crash) and `0x46B000003FD` (second): two small integers glued into a qword, i.e. memory that D2R reused
after the event was queued. No plugin code is in the frame; the details are in `docs/bugs.md` #34. It came back in 2 of about 7 full `group1.txt` runs (at the Druid switch of `morphdeath` or just after it), so it
cannot be left in the suite: `translation_guard.cpp` hooks `0x775fc0` and skips an event whose pointer chain is not readable (`VirtualQuery`), otherwise D2R's handler runs unchanged. Off word `transguard`, `mxl` line
`translation guard on (N events, M skipped)`, harness `transguard [probe]`, check `transguard` (PASS in `checks-20261024-195240-s3`: the probe event is skipped, the counters move). `morphstress` (env `MXL_STRESS_CYCLES`)
casts the three forms 30 times each per cycle with a character switch between the cycles: PASS 12 and 9 cycles (`checks-20261024-134134-s3`, `-143419-s3`), no crash: the crash is not triggered by the casts. In the four final runs
below `morphdeath` switched to the Druid in both group1 runs without a crash file. **What is not shown:** the guard skipped no real event in those runs, so it is proven only by the synthetic probe; if the crash comes back with the guard on, the
`mxl2012-core.log` has the three pointers (up to 8 warnings) and the next step is to find who queues the event.

**2. `nMissile >= 0 && nMissile < NumMissileStats`.** Not the Summoner kill and not a curse. `asserttrace` (`checks-20261024-141208-s3`, plugin 0.63.0) gave the chain `2b0e86 21854e 341740 217759 1a56e7` while the
treasure goblin (class 2791) was in the game: the client's skill start function `0x218030` calls slot 18 of the start table (`0x235f590`, `0x2b0df0`), which reads `cltmissilec` (-1) and asserts twice (it then returns 1). 52 Median
rows (curses such as Amplify Damage 66, Terror 77, Lower Resist 91 and many monster skills) have cltstfunc 18 and no `cltmissilec`. Median has no client missile for them and no D2R visual is wanted, so `CltStMissileC` wraps the slot in
place (like `CltDoCurse` for the curses): a row without a client missile returns 1 silently, a row with one runs D2R's function. `mxl` line `cltstfunc 18 start without client missile`; off word `skills`.
Check `asserttrace` now has control 2: harness `cltst 66 orig` (D2R's own function, past the wrapper) raises the assert and `cltst 66` (the table entry) raises none and returns 1; it also FAILs when the treasure goblin spawn raises an
nMissile assert. PASS in `checks-20261024-195658-s3`: control 1 assert, table 0, `treasure goblin spawn: no assert`; also PASS in both group2 runs below. (The trace label "skill 2583" of the old run is the harness' last cast skill, not the
asserting skill, and 2583's own cltstfunc is 0: the first version of the control used it and found an empty slot, so the control uses 66.)

**3. Flaky checks: the mana drain was the `heat` check.** The instrumented `group2.txt` run (`checks-20261024-134106-s2`; `clean_start_state` now measures the idle mana dip and names states, stat 297,
monsters and worn items) shows the first dip note (908 points in 1.2 s) at the start of `mapreveal`, the check after `heat`, and none before. `heat` casts Molten Core (1682, a passive, `stat 297` =
the heat loss rate) on the character for a Sorceress and restored only the class: the harness' `setskill <id> 0` only writes the base level, the passive stat 297 stays until the next recalculation, and
plugin/src/heat.cpp then drains the mana of a Barbarian (740-864 points in 1.2 s) in every later field check. Fixes: `heat` reads the levels of 482 / 1682 first, puts them back and clears what is left of stat 297
(`clear_heat_stat()`: stat set to 0, the remainder cancelled by a negative value); the start state clears a stat 297 above 0 on a character that is not a Sorceress and says so. `npcheal`, `soulstealer` and `meleenotarget` PASS in every
final run below. The old `townmana` PASS had counted that drain as the cost of the field cast ("cost 1008"); the real cost of skill 1558 at level 5 is 2-7 points, the field leg now needs a fall of at least 1 (the town leg stays exact: no fall).

Other flakes found in the repeated full runs and fixed in the checks: `npcheal` (hostile zombies of the Blood Moor at 2-3 yards kept the character in hit recovery, class 177 never opened its menu, and Tyrael 251 was
"not alive" for the interact: the field is cleared before every try, one more try after a `no heal` / `interact failed`); `hcdeath` (the client word `client+0x5658` of a freshly joined game holds garbage, e.g.
`0x5f8ae86f`, `0xe83d1d8d`, so its 0x800 bit read "Hardcore" in two of three full `group1.txt` runs: `_hc_hard()` judges by the character's info word and the save, the client word only when it looks like flags);
`skillscaling` (a random amulet that `skillstarts` leaves worn carried +6 lightning mastery: the check takes the worn items off); `soulstealer` (the player died before the hit once: the trial repeats up to three times
and names the last killer); `cainsub` (the plugin message that rebuilds Cain's list arrived after the 2.5 s the check waited, once: it waits up to 12 s and clicks a second time) and `leave_and_reenter` (a Save and Exit
click the game did not take failed `levelcap` once: three tries, the last with a new Esc).

**4. Final runs** (plugin 0.64.0, `group1.txt` on slot 1 and `group2.txt` on slot 2 in parallel; an earlier pair that ran `game_checks.py all` without the group list because of a wrapper mistake is not counted):

| Run | Result |
|---|---|
| `checks-20261024-221246-s1` (group1) | PASS 78, FAIL 2 (`cainsub`, `levelcap`: UI flakes, both PASS alone and in the next run; the checks were hardened afterwards), REVIEW 5; 0 crash files |
| `checks-20261024-231804-s1` (group1) | PASS 81, FAIL 0, BLOCKED 0, PARTIAL 0, REVIEW 5; 0 crash files; `morphdeath` PASS |
| `checks-20261024-221246-s2` (group2) | PASS 67, FAIL 0, BLOCKED 1 (`mapreveal`, by design after debug mode), PARTIAL 0, REVIEW 10; 0 crash files |
| `checks-20261024-231804-s2` (group2) | PASS 67, FAIL 0, BLOCKED 1 (`mapreveal`), PARTIAL 0, REVIEW 10; 0 crash files |

The hardened `cainsub` / `levelcap` were run once alone after the change (`checks-20261025-002747-s3`: PASS both); group1 was not run a third time on the final check code. The REVIEW rows are the start-state notes
(worn items changed, stance 309, inventory panel).

## Lane p4-soak: soak of the translation event guard (plugin 0.64.0, 2026-10-25)

Test only (plus fixes to `tools/game_checks.py`). Plugin 0.64.0 built from main 79bbf15 (`tools/build_plugin.ps1`, cmake from the Visual Studio install), data from `tools/build.py`, installed into slots 1-3 with
`install_mod.py --slot N`; the `mxl` check of every run reads `mxl2012-core 0.64.0` and `translation guard on: the unit translation event handler 0x775fc0 skips an event with an unreadable payload`.
Every full run is `py -3 tools/game_checks.py all $(cat group1.txt) --slot N` (or `group2.txt`), run folders `<runs>\checks-20261025-*` (not committed), three slots in parallel.
`run_all` now also reads `transguard` (no probe) before it stops the game and writes the counters into the report (`Translation event guard counters at the end of the run`, INFO): the groups never call the
probe, so every skipped event counted is a real one, and the three pointers of the first eight skips are in `mxl2012-core.log` (`translation event skipped: event ..., payload ..., payload+0x70 ...`).

| Run | List | Slot | Result | Crash files | Guard (events / real skips) |
|---|---|---|---|---|---|
| `checks-20261025-010224-s1` | group1 | 1 | PASS 81, FAIL 1 (`morphdeath`: Andariel did not kill the bear, see below), REVIEW 4 | 0 | 321 / 0 |
| `checks-20261025-010229-s2` | group1 | 2 | PASS 82, REVIEW 5 | 1 first-chance report at exit (below) | 314 / 0 |
| `checks-20261025-010235-s3` | group1 | 3 | PASS 82, REVIEW 5 | 1 first-chance report at exit | 299 / 0 |
| `checks-20261025-021629-s1` | group1 | 1 | PASS 80, FAIL 2 (`dropilvl`, `wwproc`), REVIEW 4 | 0 | 319 / 0 |
| `checks-20261025-021635-s2` | group1 | 2 | PASS 82, REVIEW 4 | 1 at exit | 319 / 0 |
| `checks-20261025-021640-s3` | group1 | 3 | PASS 81, FAIL 1 (`monhover`), REVIEW 4 | 1 at exit | 321 / **1** |
| `checks-20261025-032834-s2`, `-032839-s3` | group2 | 2, 3 | aborted after 13 / 14 checks (all PASS): the game died, `Present failed` (`DXGI_ERROR_DEVICE_REMOVED` 0x887A0005) in both processes in the same second (03:43:56), `d2r-crash-report` | 2 each (`.log` + `.dmp`) | not read |
| `checks-20261025-034503-s2`, `-034508-s3` | group2 | 2, 3 | aborted after 13 checks (all PASS): slot 2 `Present failed` again (04:02:17); slots 3 and 1 hung at the same moment (not responding, killed) | slot 2: 2 | not read |
| `checks-20261025-034025-s1` (killed) | group1 | 1 | hung at the same moment (04:02:30, check 29 of 88) | 0 | not read |

**The guard did skip a real event.** In `checks-20261025-021640-s3` the guard logged, at 03:17:25, during the character switch of `morphdeath` (`a cut scene plays: Esc held`, the Druid is loading):
`translation event skipped: event 00000001DD1AFCF8, payload 00000000a90f0d90, payload+0x70 0000000000002035 (not readable memory)`; the end-of-run counter says `events=321 skipped=1`. The payload pointer
read from the event (`+0x70`) is `0x2035`, a small integer and no pointer: the same kind of value as `0x8000003F0` and `0x46B000003FD` of the two crash reports, at the same place in the sequence. D2R would have read
`byte [0x2035 + 0x870]` there (the instruction of the crash at `D2R.exe+0x7761DC`). The run went on: the Druid loaded, `morphdeath` and all later checks PASS, no crash file besides the exit-time report below. The other five
complete group1 runs saw about 300 events each and no unreadable one. **Outcome (a): no crash at `D2R.exe+0x7761DC` in six full group1 runs with the guard on, and the guard skipped a real event at the point where the crash
happened before.** (One real skip in six runs; before the guard the crash came in 2 of about 7 runs.)

**Crash files that are not the crash.** The runs of slots 2 and 3 above each leave one `d2r-lastresort-crash-report (... pid-N).log` (reports with this address since 2026-10-22: 6 on slot 1, 17 on slot 2, 7 on slot 3):
`Record: 1 of at most 2`, a first-chance access violation at `Allocation Base 00007FFA3FFD0000 + 0x163644` (not `D2R.exe`), written within a second of the report `game_ctl.stop`, i.e. when the game exits
(`Generated` = the end of the run). It is a handled first-chance exception of a driver / system module at shutdown, not a death of the game: the run had finished and written its report. A real crash is the report whose
module is `D2R.exe` (`+0x7761DC` for bug #34) or a `d2r-crash-report` before the end of the run.

**The `Present failed` deaths and the hangs are the machine, not the mod.** `d2r-crash-report`: `D2Prism\src\D2Prism.cpp:2112 BC_ASSERT: result.Succeeded(), "Present failed"`, `systemCode 0x887A0005`
(`DXGI_ERROR_DEVICE_REMOVED`). Slots 2 and 3 died in the same second (03:43:56); at 04:02:17 slot 2 died again and the games of slots 1 and 3 hung. After that every new
D2R start of the session hung 10-20 s after the window opened (not responding, CPU idle; the main thread waits in `D2RLoader.exe+0x10e7d50` <- `dxgi.dll+0x62be4`, the window thread is in `win32u`): a DXGI wait that is
not answered, with `dwm.exe` showing 21 GB of GPU memory in the process counters and `Virtual Desktop Monitor` in status Error in `Win32_VideoController` (the PC has a remote-desktop / streaming host running). The single
start at 04:37 worked; the following ones (single or in parallel) did not, over more than an hour, so the group2 pair could not be finished in this session (see "Left").

**Flaky checks found in the full runs and fixed** (`tools/game_checks.py`; each passes alone):

- `morphdeath` (bear killed by Andariel, `checks-20261025-010224-s1`): Andariel's one hit took 7 of the 12 life left and no second hit came in 40 s. The life is put back to 1 point every second while she is at it and a second
  Andariel comes after 15 s.
- `monhover` (`checks-20261025-021640-s3`): `scrollportals` ran before it and left the Barbarian at **1 life point** (`life=1/8191` in the `state` before the zombie spawn); the zombie killed the character and the 24 clicks went to
  a corpse ("You have died" in `monster_fight.png`). `clean_start_state` now sets the life to full when it is under half of the maximum and says so in the row of the check (a REVIEW note).
- `wwproc` (`checks-20261025-021629-s1`): 3 of the 4 spins hurt a monster (the check wanted 4), the procs came anyway (6 Fire Bolts for 6 hits). The spins must hurt 2 monsters; the proof stays the Fire Bolts.
- `dropilvl` (`checks-20261025-021629-s1`): after the town trip in Hell, area 2, 7 drops of item level 1 were counted: they are items of the Normal visit that reach the client as new units a moment after the arrival (the
  area is the same game level), not drops of the kills. The check waits 3 s after the arrival before it records the ground items it must ignore.
- `cainsub` and `levelcap` (hardened by p4-stability, not yet re-run in a full group): PASS in all six full group1 runs above.

`checks-20261025-032845-s1` (`cainsub levelcap dropilvl wwproc monhover` alone, before these fixes): 6 PASS.
**Left:** `group2.txt` in full twice (both pairs died with the machine's GPU, above; the first 13-14 checks PASS on both slots each time, no `transguard` skip read because the counters are only written at the end of a run); the three
check fixes (`morphdeath`, `monhover`, `wwproc`, `dropilvl`) and the start-state life repair are compiled and read, but were not run in a full group after the edit (a game could not be started for more than an hour).

## Lane town-monsters: Median towns

Use a character created only for this check, with its explicit name so the harness never selects another lane's character:
`MXL_SLOT=2 MXL_RUN=town-monsters MXL_CHAR=TwnCodexOct py -3 tools/game_checks.py --slot 2 all mxl townmonsters`.
Take slot 2's lock as `town-monsters`, check it is still held immediately before installing with `tools/install_mod.py`,
and re-lock before every later install (game_checks releases it at the end). Never start if another lane's game is running.
The `MXL_CHAR` path now selects that exact character or creates it, and backs up only that character's files.

Repeat with `MXL_CONTROL=mediantowns` to leave D2R's five-town classifier intact. Both runs use the game's own level
thunk and room check, walk the player through the open Tur Dulra / Scosglen border and observe a native Scytheclaw's
room. The control must show the monster entering level 242; enabled must keep it in 271. Missing borders, inability
to walk to the setup or a monster that never acts cannot pass. All four added towns' room checks are read too.
No monster/path/collision flags are overridden by the harness. `h town [level]`, `h town x y`, `h town edges`,
monster `area=` in `h state` and optional `h spawn class count x y` provide the observations. Off word `mediantowns`;
console line `median towns`; version unchanged.

Final evidence (slot 2, throwaway `TwnCodexOct`, plugin 0.66.0):
- Control `checks-20261025-190752-s2`: `mxl` PASS, `townmonsters` PASS (bug reproduced: active Scytheclaw 30 enters 242).
- Enabled `checks-20261025-191034-s2`: `mxl` PASS, `townmonsters` PASS (active Scytheclaw 30 stays outside 242).
- All nine town ids, adjacent/invalid controls, and room checks in all four added towns match the expected classifier.
- Both runs: zero new crash files, no cursor or foreground changes, transguard skips 0. Enabled loader scan reports
  50 ERROR/ASSERT lines (startup level-type/automap, debug skill-description and exit pool assertions); it is not a clean assertion log.
  No mxl2012-core error/fail/assert lines. Earlier control setup attempts were BLOCKED/FAIL, including one enabled attempt
  that exposed an SDK patch-length refusal; the final equal-length guarded patch installs successfully.
- The fixture streams the outdoor approach using actual Teleport casts before spawning; it can blink past an approach
  obstruction. After spawn it uses walking only. No monster position, collision or path flags are overridden.
- The manual slot lock was retained between install/test iterations by a local runner, then released only after the
  last game stopped. Only the lane-created character was selected/backed up/patched. No slot/save incidents.
- Left: dedicated missile/skill aggression scenarios (shared classifier corrected), documented in `unported.md`.

### Layered special item text (special-text, 2026-10-25, background, slot 3)

`tooltiptext specialtext`: **PASS**, `checks-20261025-185239-s3`. The corrected audit reads 313 property lines
(294 OK / 19 ITEM); the new check sends all 812 referenced Median string IDs through the real property formatter,
checks 64 colour probes (four stats x 16 values), and reads Azure Wrath, Staff of Herding, unique 30 and Optical Detector
through the item builder. All 778 short paragraphs match fully; 34 long paragraphs match bounded prefixes, with their
precise IDs and remaining tail limitation in [unported.md](unported.md). `special-text-readback.txt` in the run folder
keeps the complete text answers. The harness adds `tipcolour` after the existing plain `tipfmt` answer.

Control: `MXL_CONTROL=itemtext`, off word `itemtext`, `specialtext` **PASS**, `checks-20261025-184439-s3`:
no Median special paragraphs; Azure's missing hidden-passive name returns; descfunc 31 prints the native Random Class
line. The final and control runs have zero crash files, zero cursor / foreground changes and no watchdog abort.
The lane's wrapper selected/created only `SpTextThree`; the earlier baseline used only `SpecialTxt` in slot 2
(`checks-20261025-182658-s2`). It did not use the default most-recent-character selection or back up other saves.
The earlier failed long-colour-boundary probe and intermediate build/startup problem are recorded in
item-tooltips.md. Existing startup, magic-item harness and exit pool assertions are unchanged.

## Waypoint arrival and HD panel regression (lane waypoints)

Use an owned slot lock, background input and an explicitly named throwaway character
(`MXL_SLOT=3`, `MXL_RUN=waypoints`, `MXL_CHAR=WpLane`, `MXL_INPUT=background`).
`game_checks` creates the named character if absent; with `MXL_CHAR` set, its save
backup includes only that character's files and it selects that character by name.

Run `py -3 tools/game_checks.py all wparrival wppanel` with
`MXL_CONTROL=wpauto` for the enabled case, then with
`MXL_CONTROL="wpauto wparrival"` for the control. `wpauto` is disabled in both:
the check clears each destination's server bit, operates its real object with
function 23, and verifies that the bit becomes set. `waypoint approach` loads the
waypoint room for setup; the object coordinates come independently from `wpobj`.
Travel uses the normal server packet 0x4b from Cold Plains (town for the vanilla
Cold Plains destination). A source-position check and animation wait prevent a
refused travel request from being counted as an entry fallback. Every arrival
must reach the requested level; the enabled check requires a stand position within
12 sub-tiles of the object, while the control requires the seven added preset areas to
reproduce their old fallback and the maze levels Cold Plains / Duncraig to remain correct.

`wppanel` unlocks the test character's client act-tab quests, opens the native HD
panel and clicks all five tabs using background input. It checks the actual button
table against all 47 destinations (10/11/12/4/10) and saves five screenshots.
Classic graphics (G) remains deferred in `unported.md`.

The installer now honors `MXL_SLOT` by default. With `MXL_RUN` set it refuses a
foreign/missing lock or a running game, before changing mod files or slot config.
`py -3 tools/test_install_mod.py` runs four refusal/selection regression tests
without writing game files. Reacquire the slot before every install; the default
harness shutdown releases its lock.

Final evidence under `<runs>`:

| Run | Arrival | HD panel | Log/input safety |
|---|---|---|---|
| `checks-20261025-191716-s3` (enabled) | PASS: all nine destinations one subtile from their object | PASS: 47 entries | No new errors/asserts/crashes; zero cursor/focus changes |
| `checks-20261025-192243-s3` (off control) | PASS: seven preset fallbacks, Cold Plains and Duncraig correct | PASS: 47 entries | No new errors/asserts/crashes; zero cursor/focus changes |
### Maximum resistance is capped at 90 by design (lane maxres-cap, 2026-10-25)

Median's rule is `min(75 + maximum-resistance stat, 90)`, not an uncapped maximum. See
subsystems/combat-stats.md
for the bundled data and D2Sigma patch evidence. The gameplay code and plugin version are unchanged.

Slot 2, background harness, freshly created lane-owned character **MaxresCodex**. Initial runs used plugin
**0.66.0** built from `ffd829032912c980ee97466921df447a648e3093`. Installed through `tools/install_mod.py::finish_install` after checking
the owned slot lock; existing installed data was retained (no data change).

- Existing check **resistcap: PASS**, run `checks-20261025-182129-s2`: 24/24 probes, player and Rogue hireling,
  fire / lightning / cold / magic. With resistance 200, maximum-resistance +0 / +10 / +50 left exactly
  25,000 / 15,000 / 10,000 of each 100,000-unit incoming hit: effective caps **75 / 85 / 90%**.
- The first item-gear probe in that folder is **invalid / FAIL**: it supplied ten `stat=value` pairs to an
  eight-pair harness command, which refused item creation. Its zero-resistance hits and screenshots are not
  cap measurements. This was a probe error, not a gameplay failure.

All run evidence stays outside git under `<runs>`. No game files or screenshots are committed.

Corrected item probe (local driver `<runs>/maxres-cap-check.py`, built on `game_checks.run_all`, retained outside
git to honour the docs-only direction) uses a `cm2` inventory charm with eight stat pairs, e.g.
`h item cm2 fireresist=150 maxfireresist=10 lightresist=150 maxlightresist=10 coldresist=150 maxcoldresist=10 magicresist=150 maxmagicresist=10 inv`.
It reads server `stat` and client `cstat`, calls the real damage step via `hit` outside town, then captures the character
panel in town. It never substitutes its own cap into the game. The expected cap is only an assertion in the driver.

**Confirmed display bug, separate from the correct gameplay ceiling:** with maximum-resistance **+16**, the character
panel shows **91%**, while the incoming 100,000-unit hit leaves **9,300** (90% resistance, then a separate 7% damage reduction). The server and client
raw stats both read resistance 150, maximum 16. Screenshots `maxresgear_0.png`, `_10.png`, `_15.png`, `_16.png` in
`checks-20261025-182510-s2` show **75 / 85 / 90 / 91%** for fire / cold / lightning. The character panel's unpatched
`cmp ecx,95` (`0x14e728f`) skips the patched `mov ecx,90` for computed maxima 91..94; the damage clamp and hireling
panel use the patched register for their comparison. This display issue is recorded in `unported.md`; it is not a
reason to raise the gameplay cap. No code change under the coordinator's docs-only direction.

The corrected eight-pair run `checks-20261025-182510-s2` initially marked the damage probe FAIL because its
expectation omitted that additional 7% damage reduction (for example 23,250 rather than 25,000 at the 75% cap).
Its gear and client-stat reads and panel captures are valid. A subsequent normal / control pair accounts for
stat 369 in the same way as the existing `resistcap` check. This run also logged a continuing `m_freed == 0`
engine assertion and no crash; it is not presented as an assertion-free run.

Final normal gear check **PASS (24/24)**: `checks-20261025-183121-s2`. With maximum resistance
**+0 / +10 / +15 / +16 / +20 / +50**, effective caps were **75 / 85 / 90 / 90 / 90 / 90%** for fire,
lightning, cold and magic. The loaded character supplied stat 369 = 7 despite a base-stat reset: damage fields
were **23,250 / 13,950 / 9,300 / 9,300 / 9,300 / 9,300** after that additional reduction. Server and client
raw resistance / maximum values matched the charm's 150 / requested maximum in every case. The panel screenshots
show 75 / 85 / 90 / 91 / 90 / 90 for the three visible elemental rows.

The final pair used the slot-installed 0.66.0 DLL, SHA-256
`44048202f7ccd3dc7d609dda40e9cd349fad33c146250bc16045aa661d5dc18d` (another lane installed its build while
this lane had released the lock). Initial source-build DLL SHA-256:
`01f5f1bdadb813cc61deafe91887d0399c98f9bf0b9e32cb218e87c865edf340`.
The `mxl` combat report confirms all three ceiling patches; the control uses the same DLL with **combat** disabled.

Control gear check **PASS (24/24)**: `checks-20261025-183640-s2`, `MXL_CONTROL=combat`, same DLL and character.
The `mxl` line says `combat off: left out by mxl2012-core-off.txt`. Maximum-resistance **+0 / +10 / +15 / +16 / +20 / +50**
leaves **25,000 / 15,000 / 10,000 / 9,000 / 5,000 / 5,000** of a 100,000-unit hit, i.e. native effective caps
**75 / 85 / 90 / 91 / 95 / 95%**. The character panel confirms 95% at +20 (screenshot `maxresgear_20.png`).
The control also disables combat's post-resistance damage reduction, so stat 369 is intentionally excluded from
that run's expected damage. Its report includes the preceding normal rows because the driver reuses the in-memory
results list; the rows marked `control=True` are the control measurements.

Final normal / control runs: **zero new engine assertion lines, zero crash files, watchdog abort None**.
Both games stopped before returning; the driver retained the lock between them and released it afterwards,
and the control off-file was removed. Only this lane's `MaxresCodex` save was modified. No slot/save incidents.
Left: correct the character panel's +16..+19 display comparison in a separately authorized code change.

Control log caveat: the slot-installed build logs an unrelated `median towns FAILED` safety-size mismatch at
`0x327850`. The combat part is deliberately off in that run; cap probes and the native character panel still
match the expected control values. This lane does not modify the towns part.

## Lane suite-067: targeted run of PRs #162-#166 and the character sheet resistance display (plugin 0.68.0, 2026-10-25)

Slot 2, background mode, one game at a time, character `MxlBarb` of the slot. A full `group1.txt` run (68 checks, `suite067-g1`) was
stopped by the owner after about 52 minutes (`game_ctl stop` of the slot, lock released); its results are not a verdict (one FAIL seen,
`itemevents`: thorns 50 took 52 points of monster life instead of 50; the 396 / 128 variants and the other rows of that check were
exact; the check is outside the five PRs; rerun in lane ied-vanish (section below): not reproduced). Targeted list (names as in the CHECKS list; `tooltip` and
`travel` are not check names: `tooltiptext` is the tooltip audit, `iedtip` is #164's tooltip check, `wparrival` / `wppanel` are #166's
travel checks): `mxl tooltiptext specialtext orbtips itemstatsave ied iedtip statclick grit townmonsters towncast npcheal tplock goblins
wparrival wppanel wpauto resistcap`. Also: `py -3 tools/validate.py` (0 errors, base 61 / rotw 102 warnings as before), the nine C++ test
executables (all pass), `tools/build.py` (needs `extract/` and `build/StormLib`, `build/CascLib`: a junction to the shared `extract` and
`tools/build_native.ps1`).

| Check (0.67.0, `checks-20261025-223505-s2`) | Result |
|---|---|
| mxl, goblins, tooltiptext, specialtext, itemstatsave, wparrival, wppanel, wpauto, towncast, npcheal, tplock, grit, statclick, iedtip | PASS |
| orbtips | REVIEW (screenshot review, as in every suite) |
| resistcap | FAIL: the new sheet read found the 91% display bug (+16 differs from +15 by 2.27); the damage rows 24/24 PASS |
| townmonsters | FAIL "inconclusive pursuit setup" (classifier part PASS); rerun alone PASS; see below |
| ied | FAIL (formula rows, IED, marker rows PASS; see below) |

**resistcap (fixed, 0.68.0):** `combat.cpp` now also patches the immediate of the character sheet's compare (`0x14e728f`: `cmp ecx,0x5f; jl +5;
mov ecx,0x5f`, bytes read with `peek`). `check_resistcap` reads the sheet: charm-free, with the client's copy of the stats (`cstat set`
resistance 150, maximum 0 / 10 / 15 / 16 / 20 / 50), `statorder open`, a screenshot, the crop of the Fire / Cold / Lightning rows
(`RESIST_PANEL_BOX`); +15, +16, +20 and +50 must be the same picture (mean pixel difference < 0.3) and +0 / +10 / +15 must differ. 0.67.0: +16 differs by
2.27 (FAIL); 0.68.0 (`checks-20261025-232904-s2`): +16 / +20 / +50 differ by 0.00, PASS, `4/4 clamps` in the `mxl` line. The
control (`MXL_CONTROL=combat`) expects +16 to differ from +15.

**townmonsters (flake of the check's fixture):** the field Scytheclaw sometimes stays idle during the pursuit ("monster acted=False"); that was 2 of 3 runs
before the change, the town classifier rows and "monster entered town=False" were the same in all three. `check_townmonsters` now respawns the monster up
to three times before it calls the setup inconclusive. After the change PASS (`suite067-t5`). With the `mediantowns` off word the check fails its control
expectation as designed.

**ied (open in this run, fixed in plugin 0.69.0, see "Lane ied-vanish" below):** the passive's data formula, IED, marker and explicit-refresh rows are exact,
`iedtip` PASS. What failed differed from run to run: the innate fire (stat 48) was 0 a second after a refresh, or after the live refresh of an attribute
packet. This was not caused by the five PRs: the engine's own equipment recheck took the stat away (details below). `check_ied` had been given a retry of the refresh (up to four times) and a 2 s poll in that run; the retry was removed again in 0.69.0, because it hid the loss.

## Lane ied-vanish: the innate fire that vanishes, `itemevents` thorns 52, check names (plugin 0.69.0, 2026-10-26)

Slot 2, background mode, one game at a time, throwaway character `IedVan`. The drivers are throwaway and not committed (in `<runs>`:
`iedvan_probe.py`, `iedvan_repeat.py`, `iedvan_load.py`, logs `iedvan-*.log`). New harness verbs (kept as diagnostics): `passivestate` (state list of skill 2072:
list pointer, stat array, inputs oskill / synergy / Dexterity / IED, fire), `passivetrace on|clear|show` (every call of the passive apply `0x337890` and refresh
`0x33f830` with the inputs at that moment and a call chain); the write-watch chain of `evtrace watch` now scans the stack for return addresses.

**1. Innate damage vanishing: root cause.** The state list of the passive (skill 2072, state 626) is never lost (`has=1`, same list pointer); its stat
array is rebuilt without the fire / min / max entries (4 entries -> 2). `passivetrace` shows who does it: D2R's own **equipment recheck** runs the apply
with flag 0 three times in a row and then does nothing more:
(a) the item is taken off: oskill 97:2072 = 0, Dexterity without the item's bonus -> level 0 -> fire 307 -> 0;
(b) the same once more;
(c) the item is put back through the equip step `0x475140`, but the apply runs while the list is half back (oskill and Dexterity are in, the synergy
stat 412:2072 is not yet: `osk=1 syn=0 dex=205`) -> fire stays 0. Nothing applies the passive again once the list is complete.
The recheck is not specific to the harness: it runs at once in the handler of every attribute packet (clean game, `iedvan-clean-trace.log`: fire 310 -> 0
inside the packet), D2R runs it again 0.4 - 2 s later (the one that took the stat "a second after a refresh"), and it runs when a character is loaded.
Load control (`iedvan_load.py`, character saved with the cap worn, then a game restart): **fire 0** from the first frame with the part off (`iedvan-load-off.log`),
205 with the fix (`iedvan-load.log`). So a real player loses the innate damage on every login with such gear, after spending points (the plugin's refresh
of 0.67.0 covered the immediate run only, not the second one), and after a gear change that goes through the equip step.
**Why only after other checks:** bisect (part `innate` off, 10 refreshes per run): nothing run before 0/10, `statclick` 0/10, `townmonsters` 3/10 -> `townmonsters`
is the earlier check that sets it up. The deferred second recheck is the part that needs the state it leaves; which single leftover does it is **not isolated**:
the god cheat on/off, cross-act travel (areas 271 / 242), the Teleport skill and mana stats, a move, a spawned monster, stat 328 (pierce index 35, the only stat
difference in the stat / state dump) and a socketed helm, each set alone in a clean game, gave 0 losses. The immediate recheck in the packet handler does not
depend on it.
**Before #164:** the pre-#164 plugin (0.66.0 + probe verbs, `iedvan-old-run.log`) loses the fire the same way (2 of 10 refreshes after `townmonsters`
`statclick`): the loss is the engine's, not a regression of #164, #165 or the other PRs.
**Fix (Median way: the passives are worked out once the item's stat list is complete):** `stat_rules.cpp` hooks `0x475140` under part `innate` and calls
`0x33f830(owner, 1)` after the original returns, for players only. `mxl` line: `innate damage on: attribute and equip refresh on`. No other behaviour changes.
**Results:** probe with the hook (`townmonsters statclick`, `iedvan-run7.log`): refresh 0 of 12 lost, packets 0 of 10 lost (without it 5/12 and 7/10).
`check_ied` is strict now (no retry of the refresh, a 3 s hold after each packet, and a row that reads the fire right after the equip without a refresh); with the
checks that set it up first (`townmonsters`, `statclick`), the same game: **5 of 5 PASS** (`checks-20261026-012834-s2`). Targeted set on the 0.69.0 build
`mxl statclick grit ied iedtip itemstatsave itemevents classlock`: all PASS (`checks-20261026-020458-s2`). `MXL_CONTROL=innate` with `innate` in
`mxl2012-core-off.txt`: `ied`, `iedtip` PASS their control expectations (`checks-20261026-021018-s2`).

**2. `itemevents` thorns 52: not reproduced.** Alone, three times in one game (`checks-20261026-013557-s2`): thorns 50 each time (one run had the 128 variant at
-100 points = two events, which the check allows: the monster's own hit fires the event too). After the group1 predecessors `mxl respec heart lockout cow areacycle`
(`checks-20261026-013854-s2`): 50 / 50 / 50. Again on the 0.69.0 build in the targeted set: PASS. A spawned class 18 monster at 700000 raw life lost nothing in
six 0.3 s readings in ten spawns (`iedvan-drain.log`), so there is no slow drain. The earlier 52 (and the 686816 vs 687200 of the 0.61.0 notes) stay unexplained
and rare; no leftover state was found, so the check is unchanged. (`respec` failed once in the predecessor run with "no plugin line in Akara's menu", and passed
alone with the hook on and off and again after `mxl`: a one-off outside this lane.)

**3. `group2.txt` / unknown names.** `group2.txt` (outside git) listed `tooltip`; removed (`tooltiptext` is the tooltip audit and is in the list). `game_checks.run_all`
now refuses a check list with a name that is not in `CHECKS` (prints the names, returns 2 before the lock, the game and the run folder), and
`tools/test_game_checks_names.py` covers it (`py -3 tools/test_game_checks_names.py`). The three group files have no unknown name.

Also run: `py -3 tools/validate.py` (errors 0, rotw warnings 102 as before), the nine C++ test executables (all pass), `git diff --check`.

### Lane player-bugs-1 (2026-10-27): player reports #35-#39 and #45 (docs/bugs.md)

Data only (tools/txt_migrate.py `raven_counts`), no plugin change, no version bump. Slot 2, character PlrBugsA.

| Check | What | Result |
|---|---|---|
| summonlife (new) | Barbarian: wolf_companion and guardian_spirit (control) summoned in the Blood Moor and in town, life sampled every 2 s for 30 s (one empty sample is a listing gap, two in a row or empty at the end is a death) | **PASS** (`checks-20261027-123822-s2`); before the fix the wolf died about 2 s after the cast in both areas (#36) |
| vendororbs (new) | Akara, Charsi and Gheed at Hell level 90: the mystic orbs on their shelves against Median's npcstores.bin | **PASS** (`checks-20261027-122117-s2`): Gheed 34 orbs, all in Median's list; Akara and Charsi none (#37 cancelled, as Median) |
| orbtips (extended) | also hovers up to 3 orbs on Gheed's Misc tab (Hell, level 90), screenshots `orbtips_shop_<key>` | REVIEW (`checks-20261027-124427-s2`): shop and inventory tooltips show every line of the orb's record (#38 not reproduced) |
| allattrtip (new) | a magic amulet with +5 to Strength / Energy / Dexterity / Vitality and the suffix counter, plus rolled magic amulets until one has the all-attributes suffix: "+N to all Attributes", "Suffixes: 1", no printf placeholder; capture `allattrtip_amulet.png` | **PASS** (`checks-20261027-123822-s2`, #45 not reproduced) |
| nodurabilityui | no repair button at Charsi, no durability line | **PASS** (`checks-20261027-122117-s2`; #39 as Median) |

Also run: `py -3 tools/validate.py` (errors 0, rotw warnings 102 as before), `py -3 tools/test_game_checks_names.py`.

### Lane abyss-knight (2026-10-27): bug #59, Abyss Knights melee (plugin 0.69.13)

Necromancer AbyssKnt, Abyss Knight level 20, monsters spawned 9 yards away, the knights' modes sampled for 25 s.

| Check | What | Result |
|---|---|---|
| abyssknight (new) | knights in skill1 (8, the void blast) more often than attack1 (4), `abyss_knight_skill_missile` made; with `MXL_CONTROL=rangedpets` melee only | before the fix (0.69.10 code, dev): modes {1: 58, 2: 81, 4: 101}, 0 missiles; a forced `mcast` in S1 made the missile (the skill works, the AI never picked it). Dev slot 2: **PASS** `checks-20261027-180606-s2` {1: 101, 2: 38, 8: 93}, 65 missiles; control **PASS** `checks-20261027-180946-s2` {1: 65, 2: 78, 4: 89}, 0 missiles. Release install (tools/release_install.py, slot 2, dev DLL): **PASS** `checks-20261027-181233-s2` {1: 95, 2: 14, 8: 115}, 71 missiles; control **PASS** `checks-20261027-181404-s2` {4: 108}, 0 missiles |
| mxl | `ranged pets on (marked N)` line | **PASS** (all four runs) |

Also run: `py -3 tools/validate.py` (errors 0), the twelve C++ test executables (all pass), `compileall`, `check_public.py`.
Each launch leaves a first-chance access violation report in `d2rloader\crashes` (3733 bytes). It came with the pre-fix plugin too and the game kept running.

## First boot (lane boot, 2026-10-28, slot 2, background mode, plugin 0.1.0 dev)

Full `tools/build.py` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`) + `install_mod.py --slot 2`, `game_ctl` background
launches (`-mod mxl2012`, SW_SHOWMINNOACTIVE), harness verbs through a scratch driver (game_ctl / game_checks helpers; the 10.1
checks are not in `game_checks.py` yet). Evidence (not in git): `mxl2012-runs/boot/` (`captures/`, `checks-*.txt`, the logs of
each session, `crash1/`). Ids are the built tables' (after idmap): Rock Shock 28, ParasiteSkill 480, Titan Strike 8, Innate
Titans 9, Soulshatter 18, Mana Sweep 546, Batstrike 326, Blackstorm 514; missiles treewardenspawner 1388, edy1summon 1668,
darkonesummon 1671, demon seed on ground 1359, bloodspeakerbolt 1393, leapingjumper 2241; Pandemonium 2 = level 134.

| What | Result | Evidence / note |
|---|---|---|
| Startup to the main menu, mod + plugin loaded | PASS (after bugs #1, #2) | 188 tables compiled from TXT (20 game, 168 mod), `D2R startup complete`, 0 assertions; `[PLUGIN] D2R-XL 2012 core 0.1.0`; `captures/menu_main.png` |
| Enter Act 1 with a new character | PASS (after the interim fix of bug #3) | Barbarian, Amazon: town in HD (`town_barb.png`); one assertion on entering (bug #7) |
| `mxl2012` | PASS | `check-mxl2012-console.txt`: version line `0.1.0 (dev) \| game: Diablo II: Resurrected 3.3, engine changes on`, `pluginguard ok`, `cltdo22 cltdofunc 113 client wall`, `cltdostub ... 14 of 91, server hit 10 of 71`, `other plugins: none`. Line 1 also prints the DLL path, which holds the slot folder name `D2R-93847` (not the build): fine for a test slot, worth a look for players |
| `rockshock` | PARTIAL | client: `cltdo 28` / `cltdo 480` -> cltdofunc 113, entry plugin, wall calls +1; `slot cltdo 22` exe+0x2aed10, `slot cltdo 113` plugin; real cast: monster dies, no missile / wall call seen (bug #4); no monster owns ParasiteSkill in monstats, so no `mcast` |
| `srvhit6spawn` | PASS for 3 of 4 | 1388 -> class 1195 (summon_kingkong), 1668 -> 822 (dark_kid), 1671 -> 1296 (edyrems): the idmapped sHitPar1 rows, one per hit; 1359 (sHitPar2 0) spawns nothing (bug #11); SkillsNec assert with those monsters (bug #6) |
| `srvhit23` | NOT JUDGED | `slot srvhit 23` exe+0x4533c0; `missile 1393` / `missile 2241` created, no crash; effect not observable without the missile tracker (bug #4) |
| `cltdo83` | PARTIAL | `slot cltdo 83` exe+0x2b25e0; `cltdo 8/9/18/546` return without crash (returned 0, no client missile); cast of Titan Strike: A1 played, no assert |
| `skillprog` | NOT JUDGED | Batstrike (326) learnt and cast 4x on an Amazon: sequence mode 18, no assert; charges / finisher not visible (bug #4). Blackstorm (514) refused (paladin skill) |
| `cltdostub` | PASS (stub counters not exercised) | `missilescan`: 0 rows on an empty client do / server hit slot (client hit: bug #8); `missile 83` / `84` have pCltDoFunc 0 (no function, not an empty slot), no crash |
| `pandewp` | NOT RUN | no cross-act travel (`h level` does nothing, bug #5) |
| `terrorzones` | PASS (short) | ~3 min in Blood Moor + the whole session: no terror-zone / desecrated / herald line in either log; `hd/global/excel/desecratedzones.json` of the mod installed |
| Level cap 120 (data) | PASS | built experience.txt: MaxLvl 120 in all 8 class columns (Warlock filled by d2r_adds), level 120 = 666666666, 121 = 0 |
| One character per class | 2 of 8 | Barbarian, Amazon entered. Warlock: "Class requires owning Reign of the Warlock" on this install (account entitlement, not the mod). The other five were not created: the driver's Save and Exit did not return to the menu |
| Alt+G (legacy) | PASS | town (`s5_town_legacy.png`, Median tiles / D2R town), inventory with Median's classic panel and 10x6 grid and starting kit (`s5_inv_legacy.png`), 4 toggles back to HD without a crash |
| Shrine message, Pandora name (string_gaps) | NOT RUN | no shrine near the Blood Moor entrance; a monster name needs a hover at a world position |
| Focus | 1 violation | bug #10 |

## Harness lane (2026-10-28, slot 2, background mode, plugin 0.1.0 dev + lane/harness)

Fresh full `tools/build.py` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`; validate errors 0) and plugin, `install_mod.py --slot 2`,
then `py -3 tools/game_checks.py all` (`MXL_CHAR=BootBarb`) twice and `all skillprog` twice more. The 10.1 checks are named checks of
`tools/game_checks.py` now (plus `cltnomis` for bug #6 and `classes`); each FAILs on a new engine assert (bug #7's is reported, not
failed), a crash file, `FAIL crashed` or a `FAILED` log line. Evidence (not in git): `mxl2012-runs/harness/` (`checks-run*.log`, the
run folders `checks-2026*` with `report.md`, screenshots and logs, `session*-*` for the two driver sessions).

| Check | Result (run 2; skillprog run 4) | Evidence / note |
|---|---|---|
| `mxl2012` | PASS | 9 lines, every v0.1 part on including `cltnomis cltdofunc 30 curse without client missile; cltstfunc 18 start without client missile`, `cltdostub ... 14 of 91, server hit 10 of 71`, `other plugins: none`; no build number or stamp outside the DLL path |
| `cltdostub` | FAIL (bug #14) | `missilescan`: client do 0, server hit 0, client hit **1** (row 283 `desertfireball`, client hit 11 = an empty D2R slot); rows 83 / 84 fired without a crash. The stubs' client do counter stays 0 (the client did not run those rows; the spec's `client do >= 1` was not reached) |
| `rockshock` | PARTIAL | `slot cltdo 113` plugin, `cltdo 28` / `cltdo 480` -> CltDoWall, wall calls +1 each; a real cast (left click on a zombie with Rock Shock on the left button): missile `rockshock` (2272) x3, client wall calls +3, zombie life -34. Not judged: `mcast` of ParasiteSkill (no monster owns it), the look of the wall (owner) |
| `cltdo83` | PARTIAL | `slot cltdo 83` exe+0x2b25e0; `cltdo 8 / 9 / 18 / 546` return 0, no assert; Titan Strike cast taken. Not judged: which 1.13c function slot 83 was |
| `srvhit23` | PARTIAL | `slot srvhit 23` exe+0x4533c0; bloodspeakerbolt / leapingjumper are created towards a zombie 8 east, no crash, no further missile seen (their sHitPar1 119 / 27 are not fired as missiles). Not judged: the 1.13c hit 23 to compare with (plan section 4 static step) |
| `cltnomis` (bug #6) | PASS | controls: `cltst 551 orig` asserts at SkillsNec.cpp:30, `cltdo 551 1 orig` at SkillsNec.cpp:60 (bug #6's line); through the table: none; dark_kid + edyrems (hit-6 spawns) with 3 zombies for 25 s: 0 asserts, 273 calls skipped by the wrappers |
| `srvhit6spawn` | PASS | 1388 -> 1195 (Median 1107), 1668 -> 822 (1222), 1671 -> 1296 (1221): one live monster of the idmapped class each, none of the unmapped one; 1359 (sHitPar2 0) -> one `skeleton2` corpse (bug #11: as Median); `kill` leaves dark_kid alive (Median's `killable` is blank) |
| `terrorzones` | PASS | 3 min in Blood Moor, `state` every minute; no terror / tremor / desecrated / herald line in either log; the mod's `desecratedzones.json` installed |
| `pandewp` | FAIL (bug #13) | `level 109` (NPC travel) then `level 134 warp 13` reaches Pandemonium 2 on its waypoint pad; no waypoint object there (16 objects, none OperateFn 23). `level 46` reaches the Valley; bit 17 reads 1 there; the panel opens (only the Act 1 tab on a fresh character) |
| `skillprog` | FAIL (bugs #15, #16) | Batstrike (assassin): 4 casts taken, progressive_fire (321) 2 -> 3 (cap), Attack clicks release the finisher: `knocknova` (1449) x64-128; but the first Attack click raises `ptSkill` (Skills.cpp:904, bug #15). Blackstorm (paladin): learnt with Tainted Blood / Mind Flay at level 30, the game selects it on no button and refuses the cast (bug #16). Not judged: the client progression visuals |
| `classes` | PASS | one character per class on slot 2: Amazon `BootWarlBootAma`, Sorceress `HarnSor`, Necromancer `HarnNec`, Paladin `HarnPal`, Barbarian `BootBarb`, Druid `HarnDru`, Assassin `HarnAsn` (five created by this lane with Save and Exit between); Warlock skipped (account without Reign of the Warlock) |
| Save and Exit | PASS | Esc -> Save and Exit (0.50, 0.44) is back at the main menu in 9 s on every try (6 times in the driver session, every `switch_character` of the runs); boot's failure did not come back |
| Focus / input | PASS | watchdog of each run: 13,000-14,000 samples, foreground window changed 0 times, the real cursor never moved into the game window; the game no longer starts minimized (toolfix bde0af6) and nothing in the checks behaved differently |

Harness findings for later checks: a harness `cast` is a server-side cast and the game runs no client function of the local player for
it (Rock Shock: `rockshock` missile on the server, `client wall calls` +0); a background left click on the monster (`click_unit` in
game_checks: player at (800, 405) of the 1600 x 900 HD client, about 27 px per subtile along x - y and 13.5 px along x + y) is the
real path. A level-1 test character dies in a second to the summoned ubers and to Pandemonium's Duriel: the checks raise life and
mana with `stat` (`Tank`) and the level stat for skill requirements (`Level`), and put the base values back.

## Lane datafix (2026-10-28, slot 3, background mode, plugin of this branch)

Full `tools/build.py` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`) + `install_mod.py --slot 3`; scratch drivers over `game_ctl` (`start`, `clear_intro`, `play_selected`, `hcmd`, `click_bg` hover) in `work/` (not in git). Evidence (not in git): `mxl2012-runs/datafix/` (`datafix/*.png`, `*-d2rloader.log`, `build-*.log`). Character names have no digits (D2R drops them: `Mxl2Barb` became `MxlBarb`, so `MXL_CHAR` must be a letters-only name or the driver tries to create it again).

| What | Result | Evidence / note |
|---|---|---|
| #7 unique index assertion | FIXED, verified | fires on loading a saved character (Play), caused by the statue `zen` (unique flag, no row); with `clear_unique_flags` a fresh character saves, exits and loads again with 0 assertions (`fix7b`, `final1`); before: 1 per load (`ctrl`, `expB`, `expC`). Chronicle ruled out |
| #3 `IMghhth.COF` | FIXED, verified | stand-in COFs removed; `necromorb` `mKB` cleared; a fresh character enters the Rogue Encampment, 0 `Could not add cof` (`v1` crash without stand-in, `v2` inTown off: crash, `v3` / `v4` mKB off: no crash, `final1`) |
| #9 red skill buttons | NOT A BUG | red = skill not usable now: Attack in town (InTown blank, as D2R), Throw without a throwing weapon; white outside town; icons are Median's art (`s9a`, `s9b`, `s9c`, `s9e`) |
| #15 `ptSkill` on Attack click | NOT REPRODUCED | Barbarian, Attack, monster next to it, 2 background clicks: no assertion, but the click started no attack (`bug15`) |
| Shrine message | PASS | Cold Plains, `object 2 3 0` + `objmode <id> 0` + `operate <id> 2`: overhead text "Your experience teaches you well." (`shrine6_op.png`); the 23 `blah` cells were the cause (`shrine_strings`) |
| string_gaps name | PASS for `CouatlInhibitor` (`couatlfather1`, raw key text); Pandora FAILS | class 707 shows D2R's "Lilith" (bug #18); Median-only `Necromorb`, D2R-id `Fallen One` show the mod's names (`names`, `names2`) |
| Other | bug #19 | one `ptUnit->eType == UNIT_PLAYER` assertion after harness spawns / kills |

## Lane qa (2026-10-28, slot 3, background mode, plugin of main 46db757, installed by lane datafix)

Visual QA with PrintWindow captures, HD and classic (the `g` key; the lane brief says Alt+G, a plain posted `g` switches), fresh characters
`QaBarb`, `QaSorc`, `QaNecro` (deleted again), harness verbs `spawn` / `kill` / `missile` / `operate`, D2R's own cheats through the
console (`debug_mode`, `god 1`, `goto 60`, `spawnrand`, `pickup`: `gc.con` / `gc.cheat`) for items and the trip to level 60. The harness
has no `item` / `equip` verb in this plugin (the verb table above is not this plugin's), so items came from `cheat spawnrand` and the
starting kit. Evidence (not in git): `mxl2012-runs/qa/` (`sheet_*.png` are contact sheets of the single captures next to them,
`session*-d2rloader.log` the loader logs, `backup-s3/` the files patched for the experiments, restored byte for byte afterwards).
Scratch drivers (`work/q.py`, `work/sheetlib.py`, `work/patch_slot3.py`) are not committed.

| Check | HD | Classic (G) | Evidence / note |
|---|---|---|---|
| Town | PASS | PASS | `town_hd_barb.png`, `town_classic.png`: classic Rogue Encampment, no black holes |
| Inventory + hover tooltips | PASS (title: bug #30, fixed) | PASS | `inv_hd_start.png`, `inv_classic.png`, `sheet_tip_hd.png`, `sheet_tip_classic.png`, `sheet_tip3_hd.png`: Median panel, 10 x 6 grid, I / II tabs, no pink pixels; names in Median's wording and quality colours (Orb of Annihilation gold with blue property lines, Pearl of Wisdom red, "Median XL 2012 v004" statue text), requirement and class lines in red, unidentified items say "Unidentified" |
| Character sheet | PASS | PASS | `char_hd.png`, `char_classic.png` (D2R's HD sheet; Median's classic sheet) |
| Skill tree, Barbarian / Sorceress / Necromancer | PASS | PASS with bug #33 | `sheet_skilltree_hd_barb.png`, `_sorc`, `_necro`; classic `sheet_skilltree_classic_*`. HD titles: Special / Rage, Stances / Spirits, Throw / Melee; Special / Mana, Poison / Lightning, Cold / Fire; Special / Summoning, Suppression / Battle, Totems II / Totems I. Median's icons, 10 per page, arrows. Classic: the D2R-drawn titles overlap the labels in the art |
| Cube | PASS (title fixed) | PASS | `cube_hd.png`, `fix30_cube.png`, `cube_classic.png`: 10 x 8 grid, transmute button |
| Stash | PASS | PASS | `stash_hd.png`, `stash_classic.png`: D2R's own, Personal / Shared tabs, 10 x 10 |
| Median monsters | PASS names and stand-ins; bug #34 | PASS | `sheet_mon_hd2.png` (Wandering Sarandesh, Living Rock, Flit, Belial Lord of Lies, Shardspawn, Pit Knight, Lucion Son of Mephisto, Sewer Troll, Trained Cougar with Median's description lines and immunity colours), `sheet_mon_classic.png`, `sheet_mon_classic2.png` (Median's own art for `!1` `(s` `ie` `m+` `!7` `x+`) |
| Median map (level 60, `expansion/dystopic/desertpeak`) | PASS as planned: floors, no walls (known gap) | PASS: Median's art | `map_desertpeak_hd.png`, `map_desertpeak_classic.png`: Amazonites and jungle snakes of the map, no wrong monster ids seen |
| Missiles (`rockshock` 2272, `bloodspeakerbolt` 1393, `leapingjumper` 2241) | draw (crowded scene) | draw | `sheet_missiles_hd.png`, `sheet_missiles_classic.png`; looks not judged |
| Round trip, 3 x | PASS | PASS | `sheet_roundtrip.png`; `h state` answered every time, panels as before |
| Steps 1-9 of docs/legacy-graphics.md | | see its section 5 | step 9: modded legacy files ARE served from `mods\mxl2012` (map tiles, monsters, panels, items, missiles) |

Assertions in 4 launches (`session*-d2rloader.log`): `nRadius > 0` (spawn of `belial`, bug #31), `ptSkill->nItemEffect != 0` (spawn of `hornedgods`,
bug #32), `ptUnit->eType == UNIT_PLAYER` (spawn of `jinns`, bug #19 explained), `wPrefix != 0 || wSuffix != 0` (`cheat spawnrand`,
bug #35). None during normal play, character creation, Save and Exit, the panels or the graphics toggles; no crash report. The
bug #18 and #30 fixes were verified by installing the tools' own output on the slot (`merge_string_overrides.py` on the installed
`overrides.json`, `ui_layouts.set_title` on the installed layouts) and restarting; the slot's files were restored afterwards (a full
`tools/build.py` was not run, it needs the extracts).
Experiments on #18: class 707's `NameStr` changed to `mxl2012:Necromorb` and class 708's to `mxl2012:Pandora` in the installed
`monstats.txt` (both banks): labels still "Lilith" and "Duriel" (`sheet_e1_labels.png`), so D2R's names of the Uber classes ignore the table.
For #30: `@strpanel4` -> `@strpanel8` and `@box` -> `@strpanel8` in the installed layouts: still "Missing string" (`sheet_e2_titles.png`);
literal texts: drawn (`sheet_e4_titles.png`).
Tests: `py -3 -I -m unittest discover -s tools/tests` 131 OK (new: `test_string_fixes.py` 4, `test_ui.py` +1), `tools/test_strings.py`,
`test_game_slots.py`, `test_slot_share.py` OK.

## Gameplay lane (2026-10-28, slot 2, background mode, plugin 0.1.0 dev, main 46db757 + lane/gameplay)

`tools/build.py` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`; the art step `hd_skill_anims.py` stopped on a missing
`build/StormLib` in this worktree, so the install had no HD skill animations; `validate.py` run on its own: 0 errors in both banks,
plugin 170, warnings 13), `install_mod.py --slot 2`, then `py -3 tools/game_checks.py all cltdostub pandewp skillprog cltdo83 srvhit23`
with fresh characters (`MXL_CHAR=GpBarb`; the slot's older characters predate bug #7's fix and were set aside for the run, then put
back), plus driver sessions. Evidence (not in git): `mxl2012-runs/gameplay/` (`checks-run1.log`, `run1-d2rloader.log`, the dump
`d2r93847_dump.exe`), run folders `work/runs/checks-20261028-044116-s2` and `work/runs/gameplay`.

| Check / bug | Result | Note |
|---|---|---|
| `cltdostub` (#14) | PASS | `missilescan` client do / client hit / server hit 0 / 0 / 0 after `SLOT_REMAP` blanked desertfireball's client hit 11 |
| `pandewp` (#13) | FAIL in the run (old expectation), then **not a bug** | no waypoint object in 134, also with a unique waypoint number (40) on the row; 1.13c's and D2R's room preset loop skip class 402 in level 134 (docs/plugin-plan.md section 7). The check now expects that; the new version has not run in game |
| `skillprog` (#16) | Blackstorm fixed; FAIL on asserts #15 and #20 | `skill right 514` selected, 4 right clicks; in a session `cast 514` code 0 (mode SC, mana spent) and the zombies around the paladin die over the following seconds; `blackstorm1` never seen by the tracker. Batstrike as before. `ptSkill` (#15) reproduced at the first Attack click after Batstrike charges; `nSkillCastId` (#20) on each Blackstorm cast |
| `cltdo83` | PARTIAL (look only) | static step: same function in 1.14d and D2R (docs/plugin-plan.md section 4.1); `cltdo` returns 0 without a target unit in both |
| `srvhit23` | PARTIAL (effect only) | static step: hit 23 runs skill server do `sHitPar1` (119 / 27) for the missile, same in both; rows 1393 / 2241 fly, no crash |
| #17 | not reproduced | 7 launches with a game entry, 0 crash files (bugs.md #17) |
| Focus / input | PASS | watchdog of the check run: 8,870 samples, foreground window changed 0 times, cursor never moved |

## Lane monitems (2026-10-28, slot 3, background mode, plugin of lane/monitems)

Full `tools/build.py --keep-going` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`; `hd_skill_anims.py` re-run with lane datafix's
`work/d2r-cache`, validate errors 0) + `install_mod.py --slot 3`; slot 3's `mods\mxl2012` backed up before and restored afterwards
(byte-identical). Fresh Sorceress `Monsorc`; scratch driver `work/m.py` (game_ctl / game_checks helpers, not committed). Evidence (not in
git): `mxl2012-runs/monitems/` (`tip_hd_*.png`, `tip_classic_*.png`, contact sheets `sheet_*.png`, `session1/2-d2rloader.log`, `game_ctl.log`).

New harness verbs (plugin/src/harness_cmds.cpp, dev builds only: the release DLL `-DMXL_RELEASE=ON` has neither the verbs nor the
generator hook, checked on the built DLL's strings):

| Command | What it does |
|---|---|
| `item <code> [low\|normal\|superior\|magic\|set\|rare\|unique\|crafted [row]] [q=n] [uniq=row] [set=row] [ilvl=n] [inv\|cube\|ground] [unid] [stat=value ...]` | MakeItem port: the generator `0x43d530`, then backpack / cube (find a spot, place, send) or the ground. A set / unique **row** (0-based record of the built setitems.txt / uniqueitems.txt, "Expansion" lines not counted) is asked of the generator through its block (+0x50 = row + 1, hook on `0x43cd50` installed with the harness, an ItemGenHook) with item level 255; the unique's "already dropped in this game" bit is cleared first. FAIL when the generator made another quality / index (e.g. a row whose base is not `<code>`). `194=<n>` (sockets) also sets the socketed flag 0x800. `unid` makes it unidentified (the generator identifies what it makes). Answers `item id= code= page= x= y= quality= index= identified= ilvl= sockets= flags=` |
| `equip <code> [quality word [row]] [q=n] [uniq=row] [set=row] [ilvl=n] [stat=value ...] <head\|amulet\|body\|rhand\|lhand\|rring\|lring\|belt\|boots\|gloves\|altr\|altl>` / `unequip <bodyloc\|1-12>` | lane states: `equip` makes the item as `item` does and puts it on the body location (body location words only; the place function `0x471500` with the location from `0x382df0`, as the equip packet does, so the owner gets its stats); FAIL when the location is taken or the item does not fit (`unequip` first). `unequip` takes the worn item off and frees it (the inventory change `0x472590`, then the remove packet). `tools/skill_sweep.py` wears skills.txt item types with them (`70=<n>` stacks throwing weapons and quivers) |
| `identify [all\|<item id>]` | sets the identified flag (`0x36d8f0`, 0x10) of the player's items and resends each as D2R does after identifying (`0x535f60`); the tooltip changes at once |
| `items` | every item of the player, one `item ...` line each |

| Check | HD | Classic (G) | Evidence / note |
|---|---|---|---|
| Uniques by row: 1440 Buriza-Do Tsuru (`164`), 600 Shadowmoon (`w24`), 1800 Orc Torque Torc (`rin`) | PASS | PASS | quality 7 and the asked index every time; gold names, Median's property lines and numbers, requirement / class lines in red, no raw keys (`tip_hd_u1440_bow.png`, `tip_hd_u600_w24.png`, `sheet_tips_hd.png`, `sheet_tips_classic.png`) |
| Charm: unique 178 Optical Detector (`a55`) | PASS | PASS | "Keep in Inventory to Gain Bonus", +200 Crafting Points, +2 Light Radius (`tip_hd_u178_charm.png`) |
| Set items by row: 150 Witchhunter's Crucifix (`94@`), 175 Snowstorm (`2@7`), 225 Lend Me Thy Light (`@06`) | PASS | PASS | green names, the set's piece list with the owned piece green and the others red (`tip_hd_s150_94a.png`). Rows 0-126 of setitems.txt are vanilla leftovers whose bases (`lrg`, `7m7`, ...) are not in Median's tables (lvl 126): `item` answers "unknown code", as Median never drops them |
| Rune `r01`, gem `gsb`, magic / rare ring and amulet | PASS | PASS | rune and gem names are purple: Median's strings carry `ÿc;` (faithful); a magic item shows only its base name ("Amulet", "+14 to Mana"): 693 of Median's prefixes are named `NoDesc` = empty (faithful); rare "Rune Loop" in yellow |
| Socket a gem | PASS | PASS | Sapphire (background click) into Shadowmoon (2 sockets): "Cold Resist +18%" added, required level 10 -> 12 (`tip_hd_socketed_w24.png`, `tip_classic_u600_w24_socketed.png`) |
| `identify` | PASS | | `item amu unique 0 unid` (row 0 is on `vip`: the verb reported unique 217 "Angel Heart" instead, as designed) and `item rin magic unid`: "Unidentified" before, full tooltips after `identify 35` / `identify` (`sheet_identify.png`) |
| #31 Belial (`spawn 1627`) | PASS | | no assertion; 17 area aura calls skipped in 8 s (bugs.md #31) |
| #32 hornedgods (`spawn 1715`) | PASS (no assert) | | dies at spawn (#41) |
| #35 forced magic | reproduced | | `item yq9 magic ground` asserts (bugs.md #35: cheat path only) |
| #34 Amazonite corpses | reproduced | | cause found (bugs.md #34) |
| #33 classic skill tree | unchanged | PASS | `sheet_fix33.png`, `sheet_fix33_hd.png` |

Assertions: session 1 (all of the above but `identify` and the #33 fix) 1, the deliberate #35 one; session 2 0. No crash report.
The test character `Monsorc` is still in `mxl2012-s3`: deleting its save was refused by the session's permission rules.
Tests: `py -3 -I -m unittest discover -s tools/tests` 135 OK (new `test_txt_migrate_monprop.py` 3, `test_ui.py` +1); plugin
`tools/build_plugin.ps1 -Release -Tests`: all six suites passed (harness +item / identify parsing, client skills +area aura guard).

## Lane fixes2 (2026-10-28, slot 3, background mode, plugin of lane/fixes2)

Full `tools/build.py --keep-going` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`, `work/d2r-cache` copied from lane monitems; StormLib / CascLib DLLs from
lane boot's `build/`; rc 0, validate errors 0, `hd_skill_anims.py` ran), then the #34 steps re-run by hand (`animdata_merge.py`, `legacy_art.py build`,
`hd_monsters.py build`), `tools/build_plugin.ps1 -Tests` and `install_mod.py --slot 3`. Slot 3's `mods\mxl2012` was copied to
`mxl2012-runs/fixes2/slot3-mod-backup` first and restored with `robocopy /MIR` afterwards (`diff -rq` empty), lock released. Characters `FixBarb` (Barbarian) and
`FixAma` (Amazon) stay in `mxl2012-s3` (deleting saves is not allowed to the lane). Driver: scratch `work/m.py` (not committed). Evidence (not in git):
`mxl2012-runs/fixes2/`.

| Check | Result | Evidence |
|---|---|---|
| #34 Amazonites (class 1175) killed in HD | PASS after the state machine fix: corpses lie down (first two tries, bow death COFs without / with an `lh` bow layer, did not help) | `amz3_dead_hd.png` (before), `amz4_dead_hd.png` (after), `cr_dead.png` (D2R's own cr_archer1 / goatman corpses left, T-poses right) |
| #34 classic (G) | alive and dying animation draw; no crash; corpse invisible (no DD DCC in Median's 9x art, same as before) | `amz4_classic_sheet.png` |
| #40 item event skill without ItemEffect | PASS: Athulua's Command worn by an Amazon, kills by bow shots: `calls answered 4 (last skill 241)`, 0 assertions; control without the guard inconclusive (no countable kills) | `ama_equip2.png`, `session-guard-on-d2rloader.log`, `session-guard-off-d2rloader.log` |
| #41 hornedgods | not a data bug: allied Trap-Poison monsters die at spawn without an enemy around (also with a valid skill); alive with enemies | `trap_ally.png`, bugs.md #41 |
| New: `spawn 1307` (`totemZ`) hangs the game | reproduced twice (bugs.md #60) | `session1-hang-d2rloader.log` |

Tests: `py -3 -I -m unittest discover -s tools/tests` 145 OK (new `test_death_cofs.py` 6, `test_hd_death_bindings.py` 4); plugin `tools/build_plugin.ps1 -Tests`: all seven
suites passed (new `itemeffect_tests`, which CI now also runs together with `clientskills_tests` and `missilestubs_tests`).

## Skills lane (2026-10-28, slot 2, background mode, plugin 0.1.0 dev + lane/skills)

Full `tools/build.py` twice (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`; StormLib / CascLib copied from lane boot's build, so
`hd_skill_anims.py` ran; validate errors 0 both times), `install_mod.py --slot 2`, harness verbs `states` / `cstates` / `asserttrace`
(table above). Evidence (not in git): `mxl2012-runs/skills/` (`probe1`, `probe2-control`, `sweep/sweep.json` with the D2RLoader /
plugin log tails, `sweep-run1.out`, `sweep-redo1.out`, build and install logs). Fresh characters `SkProbePal`, `SkProbeAsn`,
`Sweep<Class>` (deleted from the slot afterwards, their saves kept in the evidence folder).

| What | Result | Note |
|---|---|---|
| #20 Blackstorm `nSkillCastId` | FIXED, verified | `cstates player 43`: client `350=511` with 9 send bits (assert on each cast, control run), `350=514 351=10 202=1` with 11 (0 asserts, server cast and right click) |
| #15 Batstrike `ptSkill` | cause found | `asserttrace` chain: summon do 119 -> pet skill step -> set level 0 -> remove on a pet without skills; 12 asserts for 3 bats x 4 sumskills; plugin guard proposed |
| Skill sweep, 7 classes x 30 skills (`tools/skill_sweep.py`) | 122 ok, 10 assert, 0 broken, 37 blocked, 41 passive | docs/skill-sweep.md; new bugs #50-#54, #51 fixed and verified in a redo; 0 crashes |
| Focus / input | PASS | main run: 98,993 watchdog samples, foreground window changed 0 times, the real cursor never moved |

Harness notes: `asserttrace` counts every engine assert (D2RLoader's log names only the first of a kind per launch), so a run can credit asserts to the
step that raised them. A kill re-reads the character level from experience: a check that raises only stat 12 sees the level fall back to 1 at the
first kill (the sweep sets experience 13 to level 120's 7022000 as well). Median's skill paths are exclusive (`skpoints` costs more than any pool
while a rival named in the formula has points; the Ennead / Black Road skills want stats 504 / 505): the sweep zeroes the rivals before raising a
skill. Not covered: the 37 blocked skills need a weapon type the starting kit lacks (javelin, spear, throwing axe, crossbow, scythe, knife, axe) or a
druid form state; the harness has no `equip` verb yet.


## Lane states (2026-10-28, slot 2, background mode, plugin 0.1.0 dev + lane/states)

Full `tools/build.py` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`; StormLib / CascLib copied from lane boot's build, the HD
state machines from lane skills' `work/d2r-cache`; validate errors 0 in both banks, states.txt 317 rows), plugin built with the
read-only PluginSDK (`build_plugin.ps1 -Release -Tests`: 9 test suites pass), `install_mod.py --slot 2` (three times, for
the plugin fixes). Probe script `mxl2012-runs/states/scratch/probe_states.py` (fresh StatesBarb / StatesAsn / StatesSor /
StatesPal), then `tools/skill_sweep.py run --redo` of the 47 blocked and assert skills (fresh Sweep characters). Evidence (not in
git): `mxl2012-runs/states/` (`probe1`..`probe4-control`, `sweep/sweep.json` with the log tails, build / install logs,
`slot2-before.json` / `slot2-after.json`).

| What | Result | Note |
|---|---|---|
| #50 Force Shout (`shellshock` relocated 13 -> 305) | FIXED, verified | zombie holds state 305 after a right click and a server cast (server and client list `25:0=-33 105:0=-50`), 0 asserts; sweep redo ok |
| #52 Superbeast after Rapture (`raptured` 22 -> 306) | FIXED, verified | paladin holds 306, Superbeast's form 161 comes on, 0 asserts; sweep redo ok |
| #53 dodge / avoid / evade (`hList`) | FIXED, verified (plugin `dodgelist`) | relocation alone: 6 and 11 asserts in the fight test (75 dodge / avoid / evade on the Barbarian, zombies, fallen shamans, walking zombies with the stats); with `dodgelist`: 0; control with `dodgelist` off: 13; sweep redo: Lion / Snake Stance, Shadow Refuge, Twin Fang Strike, Fireball Sentry ok |
| #15 Batstrike release (`ptSkill`) | FIXED, verified (plugin `skillremove`) | fresh Assassin without the Ways: guard on 0 asserts, `skill removes without skills 4 (last 350)`; control with `skillremove` off: 28 `ptSkill`; sweep redo: Summon Rampagor / Lamia ok |
| Harness `equip` / `unequip` | PASS | throwing weapons with `70=<maxstack>`, crossbow + bolts (`cqv`), knives, axes, maces worn; the starting weapon and quiver taken off |
| Skill sweep redo (47 skills) | 45 ok, 1 assert (#54 Fortress, reproduced), 1 blocked | docs/skill-sweep.md: 167 ok, 1 assert, 0 broken, 1 blocked, 41 passive of 210. Blocked: Blood Thorns (506), the sweep's Arcane Strike did not always give Evocation before the cast (test timing). Broadside's cast without a target is refused by its own lockout state: verdict ok from the server cast at the target |
| Focus / input | PASS | sweep watchdog 45,899 samples, foreground window changed 0 times, cursor never moved; the off-word control probe saw the foreground window change 6 times (cursor unmoved; no focus call in our tools, not explained) |

`skill_sweep.py` notes: a skill with item type needs gets gear first (`gear_for`: strength / dexterity 1000, the lowest-level base of a
wanted type the class may use, its quiver or the itypeb weapon in the left hand), a `restrict` 2 skill its form (the class skill whose
aurastate is State1-3); a short non-shapeshift form (Evocation) is taken again before each cast (`reform`).

## Lane statefaith (2026-10-28, slot 2, background mode, plugin 0.1.0 dev + lane/statefaith)

Median's 15 states on vanilla ids D2R's code names are kept where lane states had moved them (docs/id-mapping.md "States D2R's code
names by number": every D2R call site has a 1.14d counterpart doing the same). Full `tools/build.py` (MXL_D2R_EXTRACT = the machine-local
read-only `extract_dir`; StormLib / CascLib, `work/d2r-cache` and the HD caches copied from lane states' worktree; validate errors 0, states.txt
302 rows with Median's rows at 13 22 47 57 65 66 68 78 84 87 93 101 138 143 184), plugin built with the read-only PluginSDK
(`build_plugin.ps1 -Release -Tests`: 10 suites pass, new `statelists_tests`), `install_mod.py --slot 2` (twice: the second for the
harness `mcast ... at`). Slot 2's `mods\mxl2012` was copied to `mxl2012-runs/statefaith/slot2-mod-backup` first and restored with
`robocopy /MIR` afterwards (`diff -rq` empty; `slot2-compare.txt`: only the game's own logs changed), lock released. Probe scripts
`mxl2012-runs/statefaith/scratch/probe_faith.py` / `probe_faith2.py`, fresh FaithSor / FaithPal / FaithBarb / FaithAsn (they stay in
`mxl2012-s2`). Evidence (not in git): `mxl2012-runs/statefaith/` (`probe1`..`probe4-control`, build / install logs).

| What | Result | Note |
|---|---|---|
| 13 Force Shout (`shellshock` kept at 13) | PASS | zombie holds state 13, list `25:0=-33 105:0=-50`, 0 asserts with `statelist`; control with `statelist` off: 3 `nSkill` asserts (SkillsSor.cpp `21ee93`, bug #50) |
| 22 Rapture, walk, Superbeast (`raptured` kept at 22) | PASS (no assert) | paladin holds state 22, list `67:0=65 68:0=23 69:0=23 105:0=23`, 0 asserts; the control raised none either (22 blocks checked by bytes only). 1.14d's spider-goo trail is not drawn (docs/unported.md) |
| 65 Shamanic Trance in a fight (75 dodge / avoid / evade) | PASS | state 65 with `350:0=627` in 10 of 10 samples, 0 asserts (`dodgelist` on) |
| 66 Broadside (throwing knife `148`) in a fight | PASS | state 66 with `350:0=345` in 6 samples, 0 asserts; the first probe's Broadside failed for want of the knife (`equip tkni` is a type, not a code) |
| 184 uber minions | PASS | `spawn 704` (Uber Mephisto) in Bloody Foothills: its 5 minions (ids 42-46) hold state 184, Median's `porkulator` (disguise, gfxclass 1747), 0 asserts |
| 143 Act 5 imp attach | NOT REPRODUCED (static only) | imps (`spawn 492`) next to a Siege Beast (`spawn 441`) never attached, also with `mcast 270 10 unit <imp> at <beast>` (the imps went to mode S1): D2R's Imp Teleport do (`0x586900`) attaches only when the skill's target (`0x48fe20`) is a free Barricade Tower / Siege Beast and the move onto it succeeds, which the harness cast did not give; Median's levels.txt places no imps or siege beasts. Same code in 1.14d (`0x5d1955`) |
| Focus watchdog | PASS | 4 sessions (8,051 + 6,087 + 2,349 + 1,900 samples): foreground window changed 0 times, cursor never moved; the 6 foreground changes lane states saw were not seen |

## Lane monsweep (2026-10-28, slot 3, background mode, plugin of lane/monsweep)

Slot 3's `mods\mxl2012` was copied to `mxl2012-runs/monsweep/slot3-mod-backup` first and restored with `robocopy /MIR` at the end (`diff -rq` empty), lock released.
Characters `Monsweepbarb` (Barbarian, the sweep, level 120, life 8,000,000 by `setstat`) and `Monsweepnec` (Necromancer, the #60 tests) stay in `mxl2012-s3` (deleting saves is
not allowed to the lane). The real-input watchdog of every run: cursor never moved into the game, foreground window never taken. Evidence (not in git): `mxl2012-runs/monsweep/`.

| Check | Result | Evidence |
|---|---|---|
| #60 `spawn 1307` client assert (`SkillsNec.cpp:164`) | FIXED: cltstfunc 19 reads `cltmissilec`; plugin guard `CltStMissileC19` (like start 18, #6); `cltst 1009` returns 1 without the assert | bugs.md #60, `trial1-3/` |
| #60 `spawn 1307` hang | NOT the assert: a harness-spawned (ownerless) `reanimate` pet hangs the game when it kills; bisected in the slot copy (monprop `reanimate`), sampled with `tools/hang_probe.py`; an owned one is untested | `hangprobe1.txt`, `hang*-d2rloader.log` |
| Monster sweep, all 1839 monstats rows | 1795 spawn, 44 do not (35 disabled rows #70, 9 D2R-only rows #71); 0 hangs, 0 crashes with the rows alone; 3 rows assert alone (#74) besides the owner-bound summons of #19, 7 + 3 rows carry asserts seen only in groups (#73) or after the asset cache filled (#72, #74); 5 rows die at once or in groups (#75) | `docs/monster-sweep.md`, `sweep2/sweep.json` |

Method and limits: `docs/monster-sweep.md` (generated) and the docstring of `tools/monster_sweep.py`. Passes of this lane: the full run (groups of 6 hostile rows, allied rows
alone, hazards last; one crash of a group, restarted by the watchdog), a redo of the 71 rows the `state` caps hid, a redo of the died / gone / failed rows one per group, and
`--attribute` (each row with an assert alone in a fresh launch, because D2R logs an assert once per launch). `drew` (pixels) is off by default: corpses and debris made it
noisy; the HD verdict is the token table.

Tests: `py -3 -I -m unittest discover -s tools/tests` 171 OK (new `test_monster_sweep.py` 26); plugin `tools/build_plugin.ps1 -Tests`: all seven suites passed (the new wrapper
has no unit test: it needs a unit and the client skill table; it is covered by the in-game check above).

## Lane integ: first build and boot of the combined main (2026-10-28, slots 3 and 2, background mode, main d495d6f, then 0bb0e26)

First build of main after the five merges of the day (qol, warlock, text, tokens, monsweep). Full `tools/build.py` (MXL_D2R_EXTRACT = the
machine-local read-only `extract_dir`; StormLib / CascLib, `work/d2r-cache`, `work/d2r-baseline`, `work/hd_monsters`, `work/art_provenance` copied
from lane monsweep's worktree): every step ran, no step failed, **validate errors 0 in both banks** (plugin 170, warnings 13 each), **text
audit 0 hits** (54 tables, run by `strings_check.py` after chronicle -> warlock_scale -> string_gaps and again after the art writers), no
integration fix was needed (step order already chronicle, warlock_scale, string_gaps; inventory 10x6 for all classes, cube 10x8, big
bank 10x10; Chronicle columns in uniqueitems / setitems; 257 Warlock cells). Plugin `build_plugin.ps1 -Release -Tests` with the
read-only PluginSDK: all suites pass (10, then 11 with `melt_trail_tests` after merging 0bb0e26). `install_mod.py --slot 3` / `--slot 2`.
Scratch drivers in `mxl2012-runs/integ/scratch/` (over `game_checks` / `game_ctl`), evidence in `mxl2012-runs/integ/` (not in git). Every
run: watchdog 0 cursor moves by the game, foreground never taken; shared slot files restored by `slot_share` after each launch.

| What | Result | Evidence |
|---|---|---|
| Main menu, mod + plugin loaded | PASS | `smoke1/menu_main.png`; `mxl2012` line `0.1.0 (dev)`, every part on |
| New character of each of the 7 classes enters Act 1 (Integama, Integsor, Integnec, Integpal, Integbar, Integdru, Integasn) | PASS, 7 of 7 | `h state` area 1 and the right class each; `smoke1/result.json` |
| HD and classic (G) in town for each class | PASS, 14 screenshots | `smoke1/town_<class>_hd.png`, `town_<class>_legacy.png` |
| Asserts / crash files | PASS: 0 asserts (`asserttrace` per class), 0 crash files, 0 ERROR / ASSERT lines in d2rloader.log | `smoke1/smoke.log` |
| Inventory 10x6 drawn | PASS in HD and classic | `smoke1/inventory_hd.png`, `smoke5/cube_legacy.png` |
| Horadric Cube 10x8 drawn | PASS in HD and classic (right click on the cube in the inventory) | `smoke5/cube_hd.png`, `smoke5/cube_legacy.png` |
| Median uniques identified, names in words | PASS: Fateweaver (Bone Wand), Dubhdroiacht (Gnarled Staff), King of the Dreadlands made by `item <code> q=7 uniq=<row>`; tooltips in words. One wrong line on Dubhdroiacht: `FLYING POLAR BUFFALO ERROR` for its oskill Pyroclastic Flow (new bug #140) | `smoke3/uniq_l24_hd.png`, `uniq_425_hd.png` |
| Slayer and Couatl Father spawn in classic | PASS: `slayer` (1035) and `couatlfather1` (1792) spawned in the Blood Moor in classic graphics, 0 asserts | `smoke1/spawn_slayer_legacy.png`, `spawn_couatlfather1_legacy.png` |
| `game_checks.py all melttrail` (main 0bb0e26, slot 2) | PARTIAL by design (the trail's look is judged by eye): client trail 29 in state 22, 0 on the control walk, 0 asserts; server 0 (as 1.14d: monsters only, bugs.md #52) | `work/runs/checks-20261028-*-s2/report.md`, `melttrail_walk.png` |
| melttrail probe and control | client 45 trails, light-blue melt behind the paladin in classic; `MXL_CONTROL=melttrail`: part off, no trail, 0 asserts | `melt2/`, `melt3-control/` |

Fixes of this lane: `check_melttrail` walked 5 subtiles without checking that the paladin moved (it did not, so the first run counted 0
trails) and required server trails and missile 143, which neither D2R nor 1.14d make for a player: it now verifies the walk and passes on
the client counter. `KNOWN_ASSERTS` tags `nDirectionIndex < nDirections` (bugs #54 / #73, explained and harmless). Harness `dump mon
<class> [offset]` reads any 0x40 bytes of a monstats record (used for #75).

Bugs: #54 / #73 explained (srvdofunc 15 masks the direction right after the assert), #75 explained (Median's own monstats.bin: Skill2 -1
with Sk2mode 0 = death mode), #74 haunt rows explained (no art and no animation for their TH / SC modes; all six rows, not only Vasily),
#52 server side of melttrail untested (needs a raptured walking monster), new #140 (Buffalo line). Details in bugs.md.

The characters Integ* stay in `mxl2012-s3`; the slot-2 runs played the slot's existing paladin (`be_class(3)`). Both slots hold this lane's last clean
`install_mod.py` build; locks released with `game_slots.py unlock`.

## Lane elixir (2026-10-28, slot 2, background mode, plugin of main d495d6f)

Bug #104: the Greater Elixirs of Strength / Dexterity / Energy / Vitality as in the original. `py -3 tools/game_checks.py all elixirs` with `MXL_CHAR=ElixBarb` (the character stays in `mxl2012-s2`, deleting saves is not allowed to the lane); slot 2 locked, the build installed with `install_mod.py` (no mirror of the mods folder), lock released. Evidence (not in git): `mxl2012-runs/elixir/`.

| Check | Result | Evidence |
|---|---|---|
| `elixirs` before the `pSpell` 0 cells | D2R asserted `spellState > 0 && spellState < DataTablesGetNumStates` (`SkillItem.cpp:823`) on each of the four and used them up | `evidence/run1-before-fix/` |
| `elixirs` after | **PARTIAL** (tooltips read by hand): `0g3` `0g4` `0g5` `0g6` show the red name and the drop hint only; a right click leaves the item (3 -> 3 of each), stat 0 -> 0, no new state, 0 asserts; control `0g1` drunk and used up (stat 80 -> 350, state 276) | `evidence/run3/` (`report.md`, `elixir_*_tip.png`, `elixir_*_used.png`) |

Tests: `py -3 -I -m unittest discover -s tools/tests` and `cd tools && py -3 -I -m unittest discover -p "test_*.py"` (`test_string_gaps.py` +2); `tools/build.py` ends with validate 0 errors, text audit 0 findings.

## Lane fixes3: +skill tooltips, haunt token, melt trail server half, main re-smoke (2026-10-28, slot 2, background mode, main bdcb28f + 551b179)

Full `tools/build.py` (MXL_D2R_EXTRACT = the machine-local read-only `extract_dir`; StormLib / CascLib, `work/d2r-cache`, `work/d2r-baseline`,
`work/hd_monsters`, `work/art_provenance` copied from lane integ's worktree), plugin `build_plugin.ps1 -Release -Tests` with the
read-only PluginSDK, `install_mod.py --slot 2`. Scratch driver `mxl2012-runs/fixes3/scratch/fix3.py` (over `game_checks` / `game_ctl`),
evidence in `mxl2012-runs/fixes3/` (not in git). Fresh paladin `Fixespal` in `mxl2012-s2`.

| What | Result | Evidence |
|---|---|---|
| Re-smoke of main after the Warlock round 2 merge: a new paladin enters Act 1, HD and classic (G) | PASS: area 1, class 3, both graphics modes, 0 asserts (`asserttrace`) | `run1/town_hd.png`, `town_legacy.png`, `result.json` |
| Bug #140, +skill lines (descfunc 27 / 28) | PASS: Dubhdroiacht `+22 to Pyroclastic Flow` (HD), Canis Venator `+5 to Wolf Companion (Barbarian Only)` (classic); no Buffalo line | `run1/tip_425_hd.png`, `tip_35x_legacy.png` |
| Bug #74, the six haunt rows alone, 6 s each, HD then classic | esu, fiaclagear, sorceress, druid: 0 asserts in both (drawn as bow archers); vasily 14, amazon 2-12 `hAnimSequence` (Sk1mode `TH` -> mode 14, open) | `run3/fix3.log`, `run3/haunt_*_{hd,legacy}.png` |
| Bug #52 server half: `py -3 tools/game_checks.py --slot 2 all meltmon` (new check) | PASS twice: a raptured Zakarum cleric walks, server trails 0 -> 32 / 23, missile 143 on the server, 0 asserts; 20 raptured clerics: 25.0 / 25.2 frames/s (they did not walk: cost not measured) | `meltmon/checks-20261028-120450-s2/report.md`, `meltmon_walk.png` |

Not done in game: Trang-Oul's Avatar's set bonuses (#180, needs the set), goatpriest2's Pain Spirit (#181, explained from the data).

## Lane triage (2026-10-28, slot 2, background mode, plugin 0.1.0 dev of lane/triage)

Phase 3: the open engine-triage verdicts (docs/engine-triage.md section 7). `MXL_RUN=triage MXL_SLOT=2 MXL_CHAR=Triagebarb
py -3 tools/game_checks.py all <checks>`; slot 2 locked for the lane, build installed with `install_mod.py` (build with
`MXL_D2R_EXTRACT` set: validate 0 errors, text audit 0 findings). New harness verb `watch cltdo|srvhit <index>`: counts the calls
of one table slot (calls, non-zero returns, last skill id / missile class), so a check sees the slot run on the real path.
Only mana and character level are raised (no god mode) except `frenzy` (life raised so the monsters' hits land on a live player).

| Check | Result | Evidence |
|---|---|---|
| `mxl2012` | PASS (runs 1, 2) | `checks-20261028-122637-s2`, `-123849-s2` |
| `srvhit23` | **PASS** (run 3): Bloodspeakers Mark on a spear (`137`) by left clicks (2 hits), right clicks (3), server casts (3): hit 23 `exe+0x4533c0`, last missile 1393; 8 bloodspeakerpets (one per hit, no petmax in srvdo 119, either game); leapingjumper by the harness 1 call; known assert #270 | `checks-20261028-124921-s2` |
| `cltdo83` | **PARTIAL** (runs 4-7): Titan Strike learnt: left 3 / right 3 calls on `exe+0x2b25e0`, last 8, 0 made (no cltmissile, as 1.14d), zombie life 55 -> 13; Soulshatter learnt: never starts on a zombie (srvstfunc 3 = Unsummon's start: own pet only); Mana Sweep (oskill: `setskill` refused, sorceress skill): server missiles 1119 / 1121 but no client do 83; control `watch cltdo 19`: Aerials Disaster learnt 3 + 3 calls with missiles | `checks-20261028-125445-s2` .. `-130609-s2` |
| `frenzy` | PASS (run 2): Feral Strike 3 clicks, zombie life 62 -> 33; MonFrenzy 3 casts (player life 29999 -> 29804), BloodLordFrenzy 3 casts; 0 town portals | `checks-20261028-123849-s2` |
| `skillprog` | FAIL (Batstrike only): no assassin playable (`be_class(6)` failed, runs 1 and 2); Blackstorm right clicks reach cltprg 28 (4 and 2 calls, last 514) | same |
| `pandewp` | PARTIAL (run 1): arrived in 134 by the waypoint warp (kind 13), no class-402 object (as 1.13c), Valley bit 17 = 1, panel opened; the list is judged by eye (`pandewp_valley_panel.png`) | `checks-20261028-122637-s2` |

Harness findings (kept in `check_cltdo83`'s docstring):
- **An oskill clicked runs the client's previous skill.** The client follows `skill left|right` only for a skill in its own
  list. Clicks with an oskill selected went to the old skill: `watch cltdo 19` showed last 351 during Bloodspeakers Mark.
  Learn the skill with `setskill` when a check needs its client do.
- **Server-side `cast <id> unit` reaches no client do** (0 calls, also for the learnt control), so client slots need the clicks.
- **Weapon types matter:** Bloodspeakers Mark needs a spear, Soulshatter a scythe or knife.

Static (1.14d `Game.exe`, read only):
- Client start bound is 70 in both games (#3).
- Rite of Passage values are the same (#28).
- The client do dispatcher and its current-skill caller match (#5).
- srvdo 119 has no petmax test, and 1.14d skips the target-list add silently (#10, bug #270).

New bug: #270 (explained, harmless).
Left for later:
- Batstrike (an assassin in a slot).
- The cltdo 83 missile branch in game (Soulshatter at its own pet, Mana Sweep on a sorceress).
- #16 / #18 / #24 on the player path (lane realpath's verbs).

## Lane fixes4: what 1.13c did for #74 (TH haunts, flyingscimitar), #180, #181 (2026-10-28, slot 1, background mode, main 5f91194 + lane/fixes4)

Static reading of 1.14d `Game.exe` (capstone, read only) and the D2R dump for all three (docs/bugs.md rows). Full `tools/build.py`
(caches copied from lane fixes3's worktree; the first try after the merge stopped on an out-of-memory error in `art_provenance.py`, the
retry passed): validate 0 errors, text audit 0 hits / 0 allowed. Plugin `build_plugin.ps1 -Release -Tests`: 14 suites pass (new
`origasserts_tests`). `install_mod.py --slot 1`. Scratch driver `mxl2012-runs/fixes4/fix4.py` (over `game_checks` / `game_ctl`),
evidence in `mxl2012-runs/fixes4/` (not in git). Fresh paladin `Fixfourpal` in `mxl2012-s1`, god mode, Blood Moor.

| What | Result | Evidence |
|---|---|---|
| #74 haunt_vasily, haunt_amazon alone, 110 s each, `asserttrace` | 0 asserts; mode 14 from 0.5 s to the end of the watch; no missile (1.14d: mode 14 on the default animdata record, no event frame) | `run1/fix4.log`, `result.json`, `haunt_*_{hd,legacy}.png` |
| #74 flyingscimitar alone | 0 asserts | `run1/flyingscimitar_hd.png` |
| #181 three goatpriest2, 15 s | 0 asserts; Pain Spirit's missiles 764 / 763 still made (52 / 49) | `run1/result.json` |
| #180 Trang-Oul's Avatar worn | not possible: `equip` "unknown code" for all five (Median 2012 has no `uh9` `xul` `xmg` `utc`; `ne9` is a misc item); stat 97 layers 0 / 51 = 0 | `run1/fix4.log` |
| Control, `MXL_CONTROL="animseq monequip aurastate"` | vasily 14 `hAnimSequence`, flyingscimitar 1 `count > 0`, goatpriest2 53 `wAuraState` | `run2-control/fix4.log` |

Tests: `py -3 -I -m unittest discover -s tools/tests` (338 OK after the merge of main) and `-s tools -p "test_*.py"` (277 OK, 1 skipped); `check_public` 0 hits.
Slot 1 locked only for the install and the two runs, then unlocked (shared files restored by the tools).

## Lane pluginplan2 (2026-10-28, slots 1 and 3, background mode, plugin 0.1.0 dev)

Round-1 parts `uniquecarry` (#280) and `whirlwind` (#281), their controls, and the checks plan items B, C, H, K wait for (docs/plugin-plan.md
section 14.5). Builds: (1) the round-1 tree (4f8da11, `tools/build.py` validate 0) with its DLL, slot 1; (2) main 5f91194 merged + this
branch (`uniquecarry` as data, plugin part removed; validate 0 errors in both banks, text audit 0), slots 3 and 1. Each batch: lock,
`install_mod.py`, `game_checks.py all ...`, unlock; the control data (Median's `1` in every carry1 cell) was made in the build by a scratch
script, installed with `install_mod.py`, then the build was restored byte for byte (sha1 checked) and reinstalled before unlocking. Evidence
(not in git): `mxl2012-runs/pluginplan2/run1.log` .. `run3b.log`, run folders `work/runs/checks-20261028-134826-s1` (batch 1),
`-140954-s3` (batch 2), `-141944-s1` (uniquecarry), `-142032-s1` (controls) and run4's `-s1` folder. Every run: watchdog 0 cursor moves by the game,
foreground never taken, 0 new crash files.

| Check | Result | Note |
|---|---|---|
| `mxl2012` | PASS (build 2); build 1 FAIL only on the check's own pattern | build 1 line `uniquecarry ... table loads 1, carry1 uniques 90, rewritten 90`: the part worked on both banks (45 each); the pattern wanted 45 |
| `uniquecarry` (data) | **PASS** | 45 distinct built numbers; Cursed Shadowfang, Optical Detector, Laser Focus Crystal placed; a second Cursed Shadowfang refused (`placing failed`); Azmodan's Heart picked up from the ground by a background click on its spot. Earlier runs: build 1 found no rows (the check read the blank `*ID` column), build 2's first try clicked fixed neighbour subtiles and missed the item |
| `uniquecarry` control (Median's `1` cells) | as expected (FAIL) | with relics already carried every further carry1 unique is refused, in the backpack and from the ground: bug #280 as it was |
| `whirlwind` | PARTIAL (feel by eye) | slots 1 and 3: `stat68 110, IAS 0, D2R speed 110 -> 5 frames; 1.13c speed 110 -> hit every 4`: stat 68 carries 1.13c's base 100 |
| `whirlwind` control (`MXL_CONTROL=whirlwind`) | as expected | `mxl2012` line missing `whirlwind` (off), 0 hit delays answered |
| `srvhit6spawn` | PASS | 1388 / 1668 / 1671 -> 1195 / 822 / 1296 alive, 1359 -> one corpse of class 1 (bug #11) |
| `srvhit23` | PASS (build 2) | hit 23 `exe+0x4533c0`: left 1 / right 3 / server 3 calls with missile 1393, 7 bloodspeakerpets, leapingjumper 1 call; assert #270 (known). Build 1 FAILed only because its DLL predates lane triage's `watch` |
| `cltdo83` | PARTIAL | Titan Strike clicks reach `exe+0x2b25e0` (2 + 3 calls, no client missile: none in its row, as 1.14d); Soulshatter / Mana Sweep do not reach the slot (as lane triage) |
| `skillprog` | Batstrike PASS; Blackstorm not run | assassin: charges 2 -> 3, finisher `knocknova` x128, client prg 25 called 2 times (last 326); no paladin in slot 3 (lane triage confirmed cltprg 28) |
| `pandewp` | PARTIAL | 134 reached by the waypoint warp, no class-402 object, Valley bit 17 = 1; the panel shows only the Act I tab on the test character |
| `terrorzones` | PASS | 10 min in Blood Moor, no terror / tremor / desecrated / herald line |

`uniquecarry` ran a second time on the same slot-1 character (run4, PASS, the same four relics: the harness-made relics of the earlier
runs were not carried any more). The check now takes carry1 uniques the character does not carry and asks for a fresh `MXL_CHAR` when
fewer than four are left.
Left: the Act 2 / Act 5 waypoint tab lists (a character with those acts open), the cltdo 83 missile branch on screen, Whirlwind's feel.

## Lane rulescheck: rules audit checks on the player path (2026-10-28, slots 3 and 2, background mode, build of lane/rulescheck)

Full `tools/build.py` (validate 0 errors, text audit 0) + dev plugin, `install_mod.py` before every batch, the slot locked only for
install + run. Owner rule: player path only (no god mode, no stats set, items picked up from the ground by a click, right-click use,
the real cube and NPC menus, a mortal character); a harness shortcut makes the verdict "shortcut only". Verdicts per check:
docs/median-rules-audit.md "In-game verdicts". Fresh Druids `Rcdruid` (slot 3) and `Rcdruidb` (slot 2). Evidence (not in git):
`mxl2012-runs/rulescheck/` (`cal/` = session 1 through the scratch driver `scratch/d.py`, `checks-20261028-144053-s3`,
`checks-20261028-151714-s2`).

New checks in `tools/game_checks.py` (`py -3 tools/game_checks.py all <names>`, MXL_CHAR = a fresh letters-only character; a used one
can carry items in its cube that spoil the cube checks): `rcbook` `rclife` `rcscroll` (#240 quest items), `rctoken` (#240 token via the
cube), `rcdelay` (CH13), `rchire` (#241), `rcdeath` (XP5), `rclevels` (LV2-LV4, shortcut travel), `rprunes` (RP2), `rpdarkring` (RP3,
#311), `rpcharm` (RP5), `rpnames` (RP6), `rpequip` (RP1). Helpers: `rc_obtain` (the harness drops the item, the item line's world x / y
projected like a monster's: hover, then left click; +8 px below the projected point), `rc_use` (right click in the inventory),
`rc_insert` (lift an item, click it onto another: socketing or into the cube), `rc_transmute`. Measured on the 1600 x 900 HD client:
inventory grid `INV_CELL` (1049, 393, 44 x 42) as before, cube grid 10 x 8 at (121, 107) with 44 x 42 cells, Transmute (340, 487),
the weapon slot (1090, 205). `right_panel_open()` now also reads the inventory panel's red close button (bug #333).

| Check | Result | Note |
|---|---|---|
| `rprunes` (RP2) | PASS (session 1) | Dawn (El, grey 1-socket Short Sword), Dawn (jewel, jewel, El, 3-socket Broad Sword), none with El first, none in a magic base, Kyrie (Taha, Taha, 2-socket Long Staff); runeword flag 0x04000000. Tooltips: bug #330 (`'Missing string'` rune letters), chat: bug #331 (Chronicle names Kyrie "Gemmed Horadric Staff") |
| `rpdarkring` (RP3, #311) | PASS (slot 2) | five inputs: nothing; plus El: `s@s` |
| `rpequip` (RP1) | PASS (slot 2) | Short Sword worn by a click, Broad Sword (Str 48) refused |
| `rctoken` (#240) | PARTIAL (slot 2, and by hand in session 1) | the cube makes `toa` (ilvl 99), right click uses it up; no points to refund on a level-1 character |
| `rcbook` / `rclife` / `rcscroll` (#240) | BLOCKED | "I can't" on the pickup, `item ... inv` "placing failed" (bug #332) |
| `rchire` (#241) | BLOCKED | Kashya: Talk / Cancel only before the Act I Blood Raven quest |
| `rcdelay` (CH13) | BLOCKED | Trap Rat / Treewarden Form (learnt by `setskill`) answer "Impossible." in town and Blood Moor |
| `rcdeath` (XP5) | not judged | session 1: a real death on Normal (slain by a Flit, Blood Moor) with 0 experience |
| `rpcharm` (RP5) | not judged | the Scroll of Summons needs level 6 ("Required Level: 6" in red): no bonus for a level-1 character anywhere |
| `rpnames` (RP6) | PARTIAL | magic ring "Ring" (base name only); amulets' automagic line not tellable from a rolled affix |
| `rclevels` (LV2-LV4) | PARTIAL, shortcut only | level 84 dark, no rain; 125-127 dark (bug #242) |

Engine: 0 asserts and 0 crash files during the checks. Every stop of the game by `game_ctl.stop()` logs five teardown asserts
(`s_StatsPool.IsEmpty()`, `m_allocated == 0`, `m_sortedBlockCount == 0`, `_bcObjectPoolBlockListIsEmpty`, `m_freed == 0`) in the
same second as the stop (14:45:03, 15:20:58): the forced exit, not a check. Watchdog: 0 foreground changes, the real cursor never
moved. Harness limits met on main (realpath's verbs not merged yet): no `cursor` verb (`held_item()` is always None), no `interact`
/ `menu` verbs (NPC menus by click and screenshot only).

## Lane savefmt: Save and Exit round-trip of characters and items (2026-10-28, slots 2 and 1, background mode, main e3b4896 + lane)

Tools: `tools/d2save.py` (inspector / round-trip codec of D2RLoader's extended saves), `tools/save_audit.py` (static widths),
docs/save-format.md. Scratch drivers `work/scratch/svf_run.py` / `svf_run2.py` (not in git; harness `item` / `equip` / `stat player ... set`,
Save and Exit through the pause menu, reload from character select). Evidence in `mxl2012-runs/savefmt/game1..3/` (results JSON, copies of
each save after the first Save and Exit (A) and after the reload + second Save and Exit (B), screenshots). The characters `Svf*` stay
in `mxl2012-s2` / `mxl2012-s1`. Locks taken only for the install + run of each batch and released right after.

| What | Result |
|---|---|
| Amazon, Sorceress, Necromancer, Paladin: low / normal / superior / magic / rare / crafted / set / unique items, a 4-socket item, magic items with +948 MF / 2015 str / max life / light 250 and the minima (-75 / -32 / -150 / -5), skill-event stats at layer 65535 and skill 523, a charged skill at layer 1023 << 6 \| 63, an oskill on skill 1109, the uniques mxlname_12 / Angelhost / Skin of Kabraxis, a cube filled with 80 items (one per code character, the rest runes) | PASS: nothing lost or added in game (`items` before / after), every item's content identical in A and B (`d2save.py diff`: the only change is the 0x2000 "new item" flag, cleared on load), all eight qualities present in the files |
| The three uniques of bug #250 after the Save Add fix | PASS: light radius -20, +life -250 / light -2, light -10 in A and B |
| Character stats at the level-120 maxima (level 120, experience 666,666,666, gold 1,200,000, bank 2,500,000, 610 stat / 131 skill points, 4,095 in each attribute) | PASS: identical after the reload |
| Item level 100 / 110 / 120 / 127 | FAIL (bug #251): written as 99 (D2R's serializer; fixed later by the plugin part `ilvl`, lane ilvl, see "Waiting") |
| Files | all 8 + 2 saves re-encode byte for byte (`d2save.py roundtrip`), sidecars consistent (`d2save.py sidecar`); the 24 code characters missing from the inspector were solved from the cube (docs/save-format.md, "code") |
| Not covered | runewords, mercenary gear, personal / shared stash pages (need inventory clicks; this port's harness has no `hire` / `merc` verbs), corpse (covered offline: FixBarb / FixAma round-trip), existing saves of other lanes loaded in game (offline round-trip only: loading would rewrite them) |

## Lane rulescheck2: the same rules with a set-up character (2026-10-28, slot 4, background mode, build of lane/rulescheck2)

Coordinator ruling: a check may SET UP the character (level, points, quest flags, difficulty, gear, mercenary) by the harness or a
save edit with our own code; the judged action stays on the player path. Verdicts: docs/median-rules-audit.md "In-game verdicts with
a set-up character". Character `Rcpalb` (new Paladin, slot 4, saves `mxl2012-s4`). Evidence (not in git): `mxl2012-runs/rulescheck2/`
(`drive.py` keeps the game open between step files `s*.py`; outputs `s*.out`).

New: `tools/rc_setup.py` (save edits of a CLOSED character: progression byte 0x15, quest words after "Woo!", mercenary fields
0xa1-0xab, checksum, D2RLoader's `.d2rl` sidecar: save checksum +0x34, size +0x38, SHA-256 +0x3c, body hash +0x0c; unit tests
`tools/test_rc_setup.py`). Checks (`py -3 tools/game_checks.py all <names>`, `MXL_CHAR=<letters> MXL_CHAR_CLASS=paladin`, rc2setup
first: it edits the save): `rc2setup`, `rc2quest` (#240 items), `rc2refund` (#240 token), `rc2delay` (CH13), `rc2death` (XP5 on
Nightmare and Hell). `enter_game` / `play` take a difficulty. Kashya's hire list was read by hand-driven step files (`s11.py`..`s12.py`):
her first-meeting speech plays before the menu; Esc opens the pause menu instead of closing it.

| Check | Result | Note |
|---|---|---|
| `rc2setup` | INFO | level 30, skills, save edit (progression 10, quest flags); the character loads with the edited save |
| `rc2quest` (#240) | PASS | Book +1 skill point, Potion of Life +20 life, Malah's scroll +10 resistances, each used up |
| `rc2refund` (#240) | PASS | strength 45 -> 25, stat points 0 -> 20, skill points 0 -> 7 |
| `rc2delay` (CH13) | FAIL before the fix | Holy Armor cast 110 frames into Mythal's 245; no `skilldelay` state (bug #335); after the fix: open |
| `rc2death` (XP5) | PASS | Nightmare and Hell: 290 lost (1 % of the level span) |
| `rpcharm` (RP5) | PASS | level 30: oskill 1 in the inventory only |
| Kashya hire list (#241) | PASS | ten Rogues level 29 for a level-30 player |

Lessons: a cast is read from D2R's cooldown stat 359 at the skill's layer (`stat player 359 <skill>`: the end frame), not from mana
(Holy Armor's cost does not show in stat 8). `setskill` refused Retaliate (498) and Divine Apparition (921) but gives another class's
skills (Mythal 471, Blink 346). Black Sleep and Retaliate need a melee weapon (itypea1 `mele`). The harness's gold (stat 14) does not
reach the client's hire panel. The `s_StatsPool.IsEmpty()` assert after Save and Exit is the known exit-only one: `rc2death` takes its
engine mark after re-entering.

## Lane ilvl: item levels 100-127 through Save and Exit and a reload (bug #251, 2026-10-28, background mode)

Plugin part `ilvl` (`plugin/src/item_level.cpp`, off word `ilvl`; docs/plugin-plan.md section 18). Items made by the harness
generator (`h item 632 normal ilvl=<n>`, `h item rin magic ilvl=<n>`) and one cube output (row 541, by clicks); the judged step
is Save and Exit and loading the character again. Scratch driver `mxl2012-runs/ilvl2/ilvl_run.py` (not in git; mode `rerun`).

| Step | Run | Result |
|---|---|---|
| control launch, `ilvl` off | slot 4, `mxl2012-runs/ilvl/game1` | PASS: the save holds 632 [99, 99, 99], rin [99, 99, 99] (D2R's clamp) |
| `mxl2012` line `ilvl item levels 100-127 kept ...`, no FAILED | slot 4 and slot 3 | PASS |
| old save (made at 99) loads | slot 4 | PASS: its items read 99 |
| items made at 99 / 100 / 110 / 120 / 126 / 127 / 200 | slot 4 and slot 3 | PASS (harness `ilvl=` as asked; 200 in memory) |
| cube row 541 on an ilvl-120 `4@A` | slot 4 and slot 3 | PASS: output quality 1 at ilvl 120 |
| save A, `d2save.py show` + `roundtrip` | slot 3, `mxl2012-runs/ilvl2/game1/A_IlvlAma/IlvlAmac.d2s` | PASS: 632 [99, 100, 110, 120, 126, 127, 127], rin [99, 100, 110, 120, 126, 127], 4@A [120]; roundtrip ok |
| reload in a second game launch, `h items` | slot 3, `mxl2012-runs/ilvl2/game1` | PASS: nothing lost / added; only change `ilvl 200 -> 127` (the 7-bit field); 632 + rin read 99..127, the cube output 120 |
| save B (after the reload), `d2save.py show` + `roundtrip` | slot 3, `.../B_IlvlAma/IlvlAmac.d2s` | PASS: same levels as A; roundtrip ok |
| d2rloader.log / mxl2012-core.log, crash files | slot 3 | no asserts, no FAILED, no crash file |

The first try (slot 4) failed after save A only because real input on the PC changed the typed name (`IlvlAma` became
`IlvlAamma`) and the driver kept looking for `IlvlAma`. `create_character` now empties the name box before typing and records
the name the game actually saved (`game_checks.made_name`, unit test `tools/tests/test_game_checks_made_name.py`); the driver
goes on with that name and stops with a clear message when a save is missing. The second-launch run's verdict row for the
reloaded 632s first read only the rings (the parser turns `code=632` into a number); the row was fixed and re-scored from that
run's `results.json` (`run.log`, last block: OVERALL PASS).

## Lane playtest: the player path per class (check `playthrough`, 2026-10-28, slots 2, 3 and 4, background mode, build of lane/playtest)

`py -3 tools/game_checks.py all playthrough` (`MXL_PT_CLASSES=0,4` for a subset of the classes, `MXL_PT_STEPS=kit,vendor` for a
subset of the steps; `tools/playthrough.py`, unit tests
`tools/test_playthrough.py`) plays one **fresh Normal character per classic class** the way a player does: no god mode, no easykill,
no stat, level or item grants. Warlock is skipped (needs Reign of the Warlock). Evidence (not in git): `mxl2012-runs/playtest/`
(`run-*.log`, calibration captures in `cal/`) and the run folders `work/runs/checks-*` (report, `pt_<cls>_*.png`, logs).

What each step does and which input it uses:

| Step | Input | Judged by |
|---|---|---|
| create | Create New, class figure, name typed (letters only: `Pt` + class + time stamp, new every run) | `state`: class, level 1, Rogue Encampment, Normal |
| kit | (reads only) | `items` and `stat 0-3` against the built charstats.txt row (item codes, strength / energy / dexterity / vitality) |
| field | harness `level 2` (the town exit is ~100 sub-tiles of clicks) | area 2 |
| kill | left button **held** on the nearest monster with the virtual mouse (the class's own left skill: Attack at level 1); belt potions by keys 1-4 under 60 % life; under 35 % back to town (harness `level 1`) to regenerate; a monster not hurt in 3 holds is skipped (walls) | corpses of attacked monsters, experience rises |
| pickup | after a kill with no monster within 10: the cursor hovers over the sub-tiles around the kill spot; an item label above the cursor (capture diff) means a drop: left click | `items` / gold before and after; `ground` (read only) lists what is still lying near |
| equip | inventory panel (`i`), click the picked-up item, click its body box; an item worn on pickup is taken off into the backpack and put on again; anything left on the cursor goes into a free cell | `items`: page 255 **and** x = the body location (an item on the cursor also reads page 255) |
| cube | right click the cube, click the kit's Clue Gem, click the cube grid, Transmute | Median's one-item recipe "Clue gem cycle": `01-` gone, `02-` in the cube |
| waypoint | harness `level 3 warp 13` (Cold Plains, at the waypoint), click the waypoint object, click "Rogue Encampment" in the panel | waypoint bit 1 set by the click; area 1 afterwards |
| reload | Esc, Save and Exit, Play the same card | items (code, page, position), level, experience, gold, bank and the waypoint bit unchanged |
| vendor | walk to Charsi / Akara / Gheed (clicks, a round of the town when none is within 40), click, the menu opens after the greeting (found by its gold frame: a 80-220 px top line with an edge going down from both ends; the greeting box has the same frame), Trade, sell kit scrolls (lift, drop on the shop grid), right click the Misc tab's last two columns | gold up per sale; an item arrives and gold falls (PARTIAL when nothing is affordable) |
| death | a death while fighting counts; else stand among the Blood Moor's monsters without potions (half way through, harness `spawn` of six of the nearest class); Esc respawns; harness `level` back to the spot, clicks on the corpse | respawn in town, no experience loss, worn items stay on the corpse and come back from it |

Calibration (HD, 1600 x 900 client; `tools/playthrough.py` `UI`, `SHOP`): backpack 10 x 6 at (1047, 393), cells 43.8 x 42.4 px;
equipment boxes (right hand 1092,205; head 1262,135; torso 1262,255; ...); cube 10 x 8 at (122, 107), 44 x 42.3 px, Transmute
(340, 487); waypoint panel tab I first line (340, 222); shop grid (135, 183), 41 px, Misc tab (497, 170); NPC menu Trade line = frame
top + 57 px. Things found while calibrating:
- **Alt labels do not show in background mode** (D2R's show-items action ignores the harness's virtual modifier); a ground item's
  name does show on hover, which is what the pickup uses.
- **A background click on a town NPC talks** (greeting, then the menu), so vendors are reachable without a talk verb; the older
  note above ("the NPC menu does not open" on a background click) does not hold for this port.
- An item picked up while its body location is empty can go straight onto the body (a Quilted Armor onto a naked Barbarian after a
  death); worn and cursor items both read page 255 in `items`.
- After a death the backpack stays with the character; only the worn items stay on the corpse (as 1.13c).

Results (final runs: `work/runs/checks-20261028-165811-s4` Amazon, Sorceress, Necromancer, Paladin; `checks-20261028-171007-s3`
Barbarian, Druid, Assassin; vendor re-check after the menu-frame fix `checks-20261028-175920-s4`; earlier runs `checks-20261028-14*`
and `-15*`). Every run: 0 engine asserts, no new crash report, watchdog never aborted, `run 0`.

| Class | create | kit | kill (kills, xp, level) | pickup | equip | cube | waypoint | reload | vendor | death |
|---|---|---|---|---|---|---|---|---|---|---|
| Amazon | PASS | PASS | PASS (7, 727, 1) | SKIP | SKIP | PASS | PASS | PASS | FAIL (1) | PASS (died fighting; corpse back) |
| Sorceress | PASS | PASS | PASS (12, 1191, 2) | SKIP (PASS hp1 earlier) | SKIP | BLOCKED (2) (PASS earlier) | PASS | PASS | FAIL (1) | PASS (corpse back) |
| Necromancer | PASS | PASS | PASS (5, 459, 1) | SKIP | SKIP | PASS | PASS | PASS | PASS | PARTIAL (3) |
| Paladin | PASS | PASS | PASS (13, 1169, 2) | SKIP (PASS hp1 earlier) | SKIP | PASS | PASS | PASS | FAIL (1) | PASS (corpse back) |
| Barbarian | PASS | PASS | PASS (3, 252, 1) | SKIP (4) | SKIP (auto-equip seen earlier) | PASS | PASS | PASS | PASS | PARTIAL (3) |
| Druid | PASS | PASS | PASS (2, 274, 1) | SKIP (PASS `100` earlier) | SKIP (PASS earlier: `100` onto rarm) | PASS | PASS | PASS | FAIL (1); re-check BLOCKED (5) | PASS (corpse back) |
| Assassin | PASS | PASS | PASS (7, 822, 1) | SKIP | SKIP | PASS | PASS | PASS | FAIL (1); re-check PASS | PARTIAL (3) |

1. The harness, not the game: the menu finder took the greeting box's top line for the menu, so the Trade click missed. Fixed in
   `menu_frame` (the frame needs vertical edges at both ends). The re-check (Assassin) and the Necromancer and Barbarian passes then
   sold 10 Town Portal scrolls for 1 gold each (Median's vendor pay) and bought one back for 1 gold.
2. The Sorceress was dead when the cube step started (the death is counted at the next step); her earlier run cubed `01-` -> `02-`.
3. Died again on the way back to the corpse (Blood Moor packs at level 1 with no potions left); the respawn, no experience loss and
   worn items on the corpse were all seen; only the pick-up of the corpse is missing. The other classes got their worn items back.
4. `ground` listed a `161` within 25 that the hover scan did not find (the label may lie under the HUD or another label).
5. After the menu fix the Druid's town round found no vendor within 40 (town layout seed); not a game fault.

Against the Median 1.13c rules nothing wrong was seen: kits and attributes match charstats.txt, experience and level 2 at 1000 xp,
no experience loss on a Normal death, worn items stay on the corpse while the backpack stays with the character, the waypoint and
the items survive a save and reload, and the vendor pays 1 gold. Act 1 drops are rare (~14 % of kills, almost no gold), so pickup
and equip are SKIP in most single runs. No new bugs.md rows. Open: compare the 1-gold buy-back of a sold scroll with 1.13c; a
walk-to-vendor verb would remove the town-round guess; the hover scan misses some labels that `ground` lists.

## Lane skillsweep: every class tree skill on the player path (2026-10-28, slots 1 and 4, background mode, build of lane/skillsweep)

Tool `tools/skill_sweep.py` (resumable, `run --classes ... [--redo ids] [--fresh]`, `report`); results in
[skill-sweep.md](skill-sweep.md). Per skill: learnt with `setskill` (level 20), Attack put on both buttons, the skill selected with
`skill left|right`, then background clicks on a live zombie; signs read from the harness (`watch cltdo`, missiles, states, mana,
mode, position, monsters, corpse states). Owner rule kept: no god mode, no easykill; mana 5000, life refilled to 3000, level 120.

| Item | Result | Evidence |
|---|---|---|
| sweep, 210 skills (Warlock skipped) | 168 ok, 1 assert (440 Fortress, #54), 0 broken, 41 passive; client do slot reached on 80 of 92 watched skills | skill-sweep.md |
| Mana Sweep (546), cltdo 83 | slot 83 reached with last 546, no client missile (range none: `0x2b25e0` returns 0 without a target unit, as 1.14d); its sweepcenter 1119 per click | engine-triage.md #5 |
| `skillprog` | Historical FAIL on the old Blackstorm criterion; now accepts cltprg 28 (last 514), state `blackstorm`, or any built Blackstorm missile; Batstrike charges 1 -> 3, finisher `knocknova` x64, cltprg 25 reached (last 326), no assert | engine-triage.md #6 |
| `rc2delay` (#335, CH13) | PASS: Mythal cast at frames 366 and 894 (state `skilldelay` 121); Holy Armor refused at 469 and 1004 (stat 359 stays 0); control: Holy Armor cast at 1493 after the delay | bugs.md #335 |
| Wolf Companion, SorcFamiliar | ok after bug #390's fix: the wolf alive 10 s after the cast | bugs.md #390 |
| Pagan Rites (460) | ok: a right click redeems the corpse beside the zombie (state 99) and heals 1500 -> 3000 within 0.4 s | skill-sweep.md |

Lessons: an item made by the harness `equip` was not used by the client until Save and Exit + Play (bug #391, fixed by lane
equip391 below; `--reenter-gear` keeps the old re-entry). Oskills and server `cast` reach no client function, so only clicks count. Mana regeneration is a share of the
maximum: with a high maximum small costs vanish, so mana is read 0.3 s after the click. A corpse has no position in `state`:
corpse skills are clicked at the spot recorded before the kill.

## Lane equip391: harness `equip` sends D2R's equip update (2026-10-28, slot 3, background mode, build of lane/equip391)

Bug #391 (plugin-plan.md 20). `equip` now sends the item update with command flag 8 (the item-to-body packet 0x1a's own send,
`0x4aa682`) instead of 2 (put in a page), clears item flag 0x4000 first and marks the player's stats changed after, as D2R does.
Plugin tests: all passed (`harness_cmds_test`: `PlaceCmdKind`). Then, without any Save and Exit + Play after the gear:

| Item | Result | Evidence |
|---|---|---|
| `skill_sweep.py run --classes ama --only 316,317,318,320` (no `--reenter-gear`) | 4 ok: SweepAmazon wore a bow (160) and a quiver from its save; `unequip` both, `equip 137 rhand`; Takedown, Hyena Strike (client do slot 19 called with 317 on both buttons), Pounce, Great Hunt | `mxl2012-runs/equip391/sweep/` |
| `skillprog` (re-entry removed), runs 1 and 2 | FAIL on Blackstorm only: "could not play a paladin" (the Save and Exit + card click came back to the assassin, both runs; character switching, not #391). Batstrike after `unequip` + `equip j20 rhand`: 4 of 4 casts, charges 1 -> 3, finisher `knocknova` x64, cltprg 25 called (last 326), no assert | `work/runs/checks-20261028-190709-s3`, `checks-20261028-191007-s3` |
| crash files | run 2: one D2R last-resort report, a first-chance access violation outside the game image (module base `0x7ffeb1c50000`) during the class switch; the game went on. The slot has several of these from earlier today | slot 3 `d2rloader\crashes` |

## Lane phase3: item use pSpell 3 / 10 on the player path (engine-triage #24, 2026-10-29, slot 3, background mode)

Full `tools/build.py` of lane/phase3 (main bdf63a2 plus this check; validate 0 errors), main's plugin of the same commit
(`MXL_PLUGIN`), `install_mod.py --slot 3`, then `MXL_CHAR=Phsigbarb MXL_CHAR_CLASS=barbarian py -3 tools/game_checks.py all mxl2012
rpsignets` (a new level-1 Barbarian: the expected gains assume level 1, no gold, both potion caps 0). Each item: dropped next to the
character by `item <code> ground` (stands in for a monster drop), picked up by a left click, used by a right click in the inventory;
stats read before and after. Run `checks-20261029-184343-s3` (not in git); log `mxl2012-runs/phase3/rpsignets-run1.log`.

| Check | Result | Note |
|---|---|---|
| `mxl2012` | PASS | 27 lines, nothing missing or failed |
| `rpsig_zkw` Signet of Gold | PASS | gold 0 -> 150, used up |
| `rpsig_zku` Signet of Experience | PASS | experience 0 -> 250, used up |
| `rpsig_zkq` Signet of Learning | PASS | stat points 0 -> 1, potion_stat_cap 0 -> 1, used up |
| `rpsig_quz` Bling Bling Signet | PASS | stat points 1 -> 6, potion_stat_cap 1 -> 6, used up |
| `rpsig_zka` Buyable Signet of Gold | PASS | gold bank 0 -> 150, used up |
| `rpsig___B` Signet of Skill (New) | PASS | skill points 0 -> 1, potion_skill_cap 0 -> 1, used up |
| `rpsig_dog` Apple | FAIL (bug #499) | "I can't", Apple kept: D2R's pSpell 10 is the Book of Skill; 1.13c's starts skill 47 (Apple Healing Spell) |

Engine: 0 asserts, 0 crash files; watchdog: 0 foreground changes, the real cursor never moved. Unit test:
`tools/test_game_checks_rulescheck.py` class `Signets`.

## Player-path checks (lane realpath, 2026-10-28, slots 3 and 1, background mode, plugin of lane/realpath)

Why (owner, 2026-10-28): players hit hard crashes that checks never catch when the checks take shortcuts (items made
straight into the backpack, god mode / Tank / life set, harness spawns and warps). The checks `rp_items`, `rp_vendors`, `rp_death`,
`rp_areas`, `rp_persist` and `rp_use` (tools/game_checks.py, section "player-path checks") take the player's paths instead; no god
mode, no Tank, no life stat, no `item ... inv`, no harness kill or spawn (`tools/test_game_checks_realpath.py` greps their code for
those shortcuts). Known D2R crash patterns against this port: [crash-audit.md](crash-audit.md).

How a player's path is driven (background mode, no real input):

| Action | Path | Verified on (2026-10-28) |
|---|---|---|
| item from the ground | harness `item <args> ground` (the generator, as a monster drop), walk next to it, `pickup <id>` = packet 0x16 (id, x, y, to-inventory flag; 17 bytes) | Crown, rings, amulets, circlet, rune |
| backpack / cursor / body | 0x18 cursor -> backpack (id, x, y, page; 17 bytes), 0x19 backpack -> cursor, 0x1a cursor -> body (id, body location), 0x1c body -> cursor (id, body location; 9 bytes) | same |
| tooltip | inventory panel open (`i`), virtual mouse over the backpack cell (screenshot every n-th item) | Crown tooltip read by hand |
| stat points | the stat panel's packet 0x3a (stat, count 4 = shift-click, 5 points) | Str / Dex / Vit |
| level | harness `xp <amount>`: D2R's own experience award (0x44f2e0), so level-ups, life, mana and points are the engine's | RpBarb level 78 -> 120, life 2390 -> 3950 |
| NPC | walk up (`moveto nearest <class>`, a real click when the server path stalls), talk = packet 0x2f, the client opens the menu; `menu <line>` runs the line's own handler (Trade image+0x112f30, Gamble image+0x112c80) | Akara, Charsi, Gheed, Halbu, Malah |
| buy / sell / gamble | right click on the vendor grid (HD panel: grid 137,183, cells 40.8 x 40.9; tabs at y 170), sell = lift the backpack item with a click and drop it on the vendor panel; gamble = right click on an offer | Gheed buy + sell + gamble; Halbu, Malah buy + sell; Charsi buy |
| potion / scroll | right click on it in the backpack | Minor healing potion (state 245, life regeneration) |
| waypoint | click the waypoint object (the client walks up and opens the panel), click the destination's row (y 222 + 51.3 x row; act tabs from x 196, step 72, y 184). Packet 0x49 alone moves nobody; 0x13 on the object opens nothing | Rogue Encampment -> Cold Plains |
| cube | open by right click on the cube, inputs picked up from the ground (0x16) into the cube (0x18 page 3), Transmute clicked (340, 487) | 2 Chipped Amethysts -> Flawed Amethyst |
| socket | the filler picked up onto the cursor (0x16), clicked onto the socketed item in the backpack | Rune, Chipped Amethyst, jewel into a 3-socket Field Plate |
| death | a level-1 character walks into natural packs (no spawn, no life set) until it dies; Esc respawns | Stony Field, died after 9 s |

Set-up shortcuts that stay (each check notes them): `xp` for the level, `gold set` for money, waypoint bits of later acts, the
NPC travel between acts (`level <town>`: D2R shows only the acts the character's quests opened in the panel), `level <id> warp`
for an area entrance, `packclear` / `remove id` to clear the backpack between items. Items are made on the ground by the harness
generator.

New harness verbs (plugin/src/harness_cmds.cpp): `pkt`, `pickup`, `cursor`, `ground`, `move`, `moveto`,
`interact`, `menu`, `packclear`, `remove`, `gold`, `shop`, `gamble`, `usecheck`, `xp`, `tiles`. Our `state` lists no items: the checks
read them with `items`.

Results:

| Check | Run (work/runs/) | Result | Notes |
|---|---|---|---|
| `rp_items`, 6 classes (Amazon, Sorceress, Necromancer, Paladin, Druid, Assassin) | checks-20261028-173925-s1, rerun of the failed codes checks-20261028-181546-s1 | 183 items: PASS 109, REFUSED 73, FAIL 17 after the rerun; no crash | REFUSED = the game refused to wear it, requirement above a level-120 character's stats (a real rule). First run: 38 four-row items did not fit the drop cell (check fixed: cells (4,3), (6,2), (6,0)); 25 set items "not made" were setitems' separator row (index = row - 1, same item; check fixed). Left: 16 class weapons / shields not worn at `rarm` though the requirements are met (azsd, aspe, ajav, nagi, dstf, sdst, 2 HD shields: open, check side, the location or a second hand), 1 set row the generator cannot make (251) |
| `rp_items`, Barbarian items 0-149 of 528 (`MXL_RP_SLICE=0:150`) | checks-20261028-183847-s1 | PASS 119, REFUSED 30, FAIL 1; no crash | FAIL `gld` (a gold pile never enters the backpack; expected). Engine: `wPrefix != 0 \|\| wSuffix != 0` (Items.cpp:906) once: bug #35, the harness generator's path (no magic item was asked for) |
| `rp_vendors` | checks-20261028-144526-s3 | partial | Gheed: buy, sell back, gamble; Halbu, Malah: buy and sell back; Charsi: buy (sell back did not change the gold). Akara, Drognan, Fara, Elzix, Lysander, Ormus, Alkor, Asheara, Hratli, Larzuk, Drehya: no menu (act 2 / 3 NPCs not yet loaded after the travel; the walk-up loop needs them in range); Jamella: trade panel did not open. Engine: bug #190 (harness travel with a panel open, fixed in the check) |
| `rp_death` | checks-20261028-144526-s3, 183847-s1 | died / respawned: PASS; corpse: not checked | a level-1 Sorceress died to natural Stony Field monsters after 9-11 s; Esc respawned in town; Save and Exit + reload fine. After the reload the gear is on the corpse, which the check looks for among ground items only (open) |
| `rp_areas` | realpath-run9 log (cut at 45 min, no report) | partial, no crash | about 45 area entries over acts 1-4 (Blood Moor to the Kurast area), 2 natural deaths, 0 asserts. The waypoint panel's act tabs II-V are not hit by the click: the row click lands in act I's list, so later acts fell back to harness travel |
| `rp_persist` | checks-20261028-173344-s1 | PASS | RpBarb: 25 items before and after Save and Exit |
| `rp_use` | checks-20261028-173344-s1 | sockets, cube, potions: PASS | rune, gem, jewel clicked into a 3-socket Field Plate; recipes 169 and 173 (gems) and 28 (summoning scroll) transmuted (judgement of a unique output fixed after the run); elx, vps, yps, wms, hp1, mp1 drunk; tbk / tsc did nothing in town (a Town Portal does not open there). Engine: bug #191 (`spellState > 0` verify twice, most likely the antidote / thawing potions) |

Not done / open:

- `rp_items`: Barbarian items 150-527 (`MXL_RP_CLASSES=barbarian MXL_RP_SLICE=150:528`, about 65 minutes) not run yet; the 16
  not-worn class weapons / shields (location or a second hand).
- `rp_vendors`: act 2-5 NPCs (wait until the NPC is loaded after the travel), Charsi's sell back, Jamella; repair.
- `rp_death`: find and click the corpse after the reload (a corpse unit, not a ground item).
- `rp_areas`: the waypoint panel's act tab positions for acts II-V; act 5 and the bosses; a run longer than 45 minutes (split
  per act).
- Bug #191: split the verify per potion: done by check `pot_use` (lane potions191, below), run pending.

Tests: `py -3 -I -m unittest discover -s tools/tests` and `cd tools && py -3 -I -m unittest discover -p "test_*.py"` (new
`test_game_checks_realpath.py` 8, `tools/tests/test_sound_rows.py` 3, `tools/tests/test_txt_migrate_crash_rows.py` 5); plugin
`tools/build_plugin.ps1 -Tests` all 15 suites (new `soundguard_tests`, `transguard_tests`); `tools/build.py` validate 0 errors, text
audit 0 findings; `check_public.py` 0 hits.

Rule proposed for the lanes (lane realpath): a fix counts as "verified" only after a player-path run (an `rp_*` check or the same
actions: real pickup, click, NPC dialog, mortal character, no god mode / easykill), listed here with its run folder and log.

## Lane isinside: levels.txt `IsInside` on levels 84 and 125-127 (bug #242, 2026-10-29, static; game run not made)

Verdict: **accepted, no visible effect** (docs/bugs.md #242). Median's engine (1.14d `Game.exe`, read statically) loads
`IsInside` into its levels record and never reads it; D2R does not load it. Light, day/night, rain and mud come from the
Intensity / RGB and Rain / Mud columns in both engines (addresses in #242). Earlier look (lane rulescheck, `rclevels`,
shortcut travel): level 84 dark with no rain, 125-127 dark: what Median's fixed light and the random rain give, not an inside flag.

New check `ins_levels` (`py -3 tools/game_checks.py all ins_levels`, MXL_CHAR = a throwaway character): character level by `xp`
(set-up, `MXL_INS_LEVEL`, default 90), Act III waypoint bit set, the Spider Forest (76) reached through the waypoint panel, then
the forest's entrance warp into 84 (`level 84 warp`, as `rp_areas`); 125-127 by `h level` (no player entrance: uberquest
portals). Per level: screenshot, automap (Tab), more shots 15 s apart for rain, a Scroll of Town Portal read by a right click
(the portal object must appear). Verdict PARTIAL by rule (shortcut travel to 125-127; the look is judged by hand).
**Not run**: slots 2-4 stayed locked by other lanes for the whole wait (00:58-01:48). Unit test: `tools/test_game_checks_isinside.py`.

### Bug #191: item spells per potion (lane potions191, 2026-10-29)

Check `pot_use` (tools/game_checks.py, `pot_use_check`): RpBarb (mortal, no god mode), each code alone: `item <code> ground`, the
pick-up click, the right click in the backpack (the player's own use); `asserttrace on`, and `asserttrace count` read around each
drink (D2RLoader's log names only the first assert of a kind per launch). Before `yps` a `gnat1` uses Poison Flash on the
character, before `wms` a `shadowwarrior` uses Ice Lance (harness set-up `spawn` + `mcast`, in town or the Blood Moor); the drink
must remove the state. Expected: 0 asserts on every drink; `yps`, `wms`, `ey9`, `elx`, `vps`, `hp1`, `mp1`, `rvs` used up (cures
done); `hrb` and `eo7` (pSpell 0, as 1.13c refused them) kept. Subset: `MXL_POT_ONLY=yps,wms`.

    MXL_SLOT=<n> MXL_RUN=potions191 MXL_PLUGIN=<main's build/plugin/Release/mxl2012-core.dll> py -3 tools/install_mod.py --slot <n>
    MXL_SLOT=<n> MXL_RUN=potions191 MXL_CHAR=RpBarb py -3 tools/game_checks.py all pot_use

| Check | Run (work/runs/) | Result | Notes |
|---|---|---|---|
| `pot_use` | not run | PENDING | slots 2-4 (and 1) held by other lanes for the whole 45-minute wait of lane potions191; the fix is checked by the unit test and the built tables only |
| `pot_use` (lane rc3, rc1 package on slot 2) | `checks-20261029-043520-s2`, `checks-20261029-043945-s2` | PASS for the asserts, cure not judged | every drink 0 engine asserts, used / kept as expected; the poison / cold set-up (`mcast`) put no state on the character, so the two cures stay unjudged (release candidate rc1 smoke above) |

## Nightmare/Hell (lane nmhell, 2026-10-29, slot 1, background mode, build of lane/nmhell with main's plugin)

First check of Nightmare and Hell progression (Normal Acts 3-5 are lane acts3). Checks (`tools/nmh_checks.py`, registered in
`tools/game_checks.py`; `MXL_CHAR=Nmhbarb MXL_CHAR_CLASS=barbarian py -3 tools/game_checks.py all nmhsetup nmhnm nmhhell`;
`MXL_NMH_STEPS[_NIGHTMARE|_HELL]=andariel,...` picks steps; unit tests `tools/tests/test_nmh_checks.py`). Evidence (not in git):
run folders `work/runs/checks-<stamp>-s1` and logs `mxl2012-runs/nmhell/run1.log` .. `run6.log`.

SET-UP (named in every evidence row): level 80 (Nightmare) / 120 (Hell) by the game's xp award; stat points by harness (half
strength, half vitality); skills by `setskill`: Aerials Disaster 351:1, Blood Hatred 352 (14 at level 80: Median caps a skill by
character level; 20 at 120), Ancient Blood 439:10, Mountain King 442:10. Then a save edit of the closed character with
`tools/rc_setup.py`: progression byte 0x15 = 5 (Nightmare open) or 10 (Hell open) and the earlier difficulties' boss quests
(6, 14, 23, 26, 40) DONE. This is what the save holds after a player kills Baal: the game reads only these bytes to open the
next difficulty. Entering is the player path (character card, Play, the difficulty dialog's button). Fights use Blood Hatred on the
right button with right clicks on the monster (player path); help gear by harness (`equip`, named in the note). Travel inside a
step (`level 3 warp 13`, legs to the boss) is help; the judged actions are the clicks and NPC dialogs.

| Step | Nightmare | Hell | Path | Evidence |
|---|---|---|---|---|
| Enter Rogue Encampment from the difficulty dialog | PASS difficulty 1, area 1, its quest words empty | PASS difficulty 2, area 1, quest words empty | player | run1 `checks-20261029-010020-s1`, run6 `checks-20261029-015205-s1` |
| Hell refused while only Nightmare is open | PASS progression 5: the Hell click does not enter, back in Nightmare | n/a | player | run2 `checks-20261029-011051-s1` |
| Monster level and life (Blood Moor) | PASS 11/11 at level 53 (`MonLvlEx(N)`), life in the monstats x monlvl range | PASS 6/6 at level 120, life in range (e.g. 93,529 in 93,500-98,500) | harness read | run2, run6 |
| Cold Plains waypoint | PASS activation (run1 panel screenshot) and panel travel to town (area 1, run1 and run2) | activation PASS (bit 0 -> 1 after the operate); panel travel FAIL: the character died to a Fallen One before the click (test death, not a port bug) | operate by harness, panel click player | run1, run2, run6 `nmh_hell_wp_panel.png` |
| Act 1 quests start (Akara: Den of Evil) | PASS quest 1 `0000..` -> `0010..`; Warriv offers only `d35` before Andariel | PASS (same) | player (NPC dialog) | run1, run6 |
| Andariel | level 61, life 257,620 = table: PASS; kill FAIL (best: about 210k damage, 149,668 by 13 right clicks, then 5 deaths, run3) | level 120, life 750,000 = table: PASS; kill FAIL (killed by Catacombs 4 packs before reaching her) | player clicks | run3 `checks-20261029-012137-s1` .. run6 |
| Act 1 -> 2 travel (Warriv) | not reached (Andariel alive) | not reached | | |
| Duriel (Nightmare) | level 69, life 246,300 = table: PASS; kill FAIL (5 deaths) | not tried | player clicks | run2, run4 `checks-20261029-013109-s1` |

Median rules seen: no level gate to enter Nightmare or Hell (only the vanilla "kill Diablo / Baal" strings exist; Nightmare entered at
level 80); Hell monsters are all level 120 with life 50000 % of the monlvl column, as the tables say; entering Catacombs 4 sets quest 6
bit 4 (both difficulties) and Duriel's tomb sets quest 14 bit 2 (Nightmare). No new engine asserts (only the known open #54 / #73
`nDirectionIndex`, MissMode.cpp:2042, in the Duriel fight), no crash files, watchdog never aborted.

REVIEW items, answered by lane nmhell2 below (neither is a port bug):
- the Hell button at progression 5: drawn dimmed (disabled), see "Nightmare/Hell, lane nmhell2".
- Duriel's 870 against Andariel's 11,500 per right click: landed-hit count under a stun-lock, not a damage reduction (same section).

Left: kill Andariel / Duriel on Nightmare and Hell with a stronger build or a mercenary (the Catacombs 4 packs kill a level-80/120
Barbarian with this help gear), then Warriv's Act 2 travel, Act 2-5 Nightmare / Hell, NM/Hell-only drops and quest rewards.

## Lane walls: HD walls of the 8 retextured maps (2026-10-29, slot 3, background mode, build of lane/walls)

Check `wall_maps` (`MXL_RUN=<run> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all wall_maps`; optional
`MXL_WALL_LEVELS=18,60` for some maps only): one launch, god mode on (`cheat god 1`: a level-1 character died in the first
run), each map entered by `h level` in HD, then all again in classic, three shots per map and mode (`wall_<map>_<hd|classic>_<n>.png`,
the arrival and two `place` steps of 12 sub-tiles), engine asserts counted per map. Seen with the harness (travel shortcut,
god mode), not on the player path. Run folders are kept outside the repo.

| run | result |
|---|---|
| `checks-20261029-025757-s3` (final build) | all 8 maps reached in HD and classic, **no assert in any of the 16 visits, 0 crash files**. HD shots compared with classic by eye, below |
| `checks-20261029-023736-s3` (earlier build, larger scenes) | all 8 maps reached; `BC_ASSERT: 0 (AssetCache.h:187)` in classic downtown (12th area of the launch) |
| `checks-20261029-024845-s3` (A/B: maps_hd's minimal scenes, no walls) | the same assert at the same place: not caused by the walls (bug #360) |
| `checks-20261029-025607-s3` (downtown only, fresh launch) | no assert |

HD against classic per map (final build): **desertpeak** stone wall runs and pillars where classic has its cave walls, some
classic walls without an HD wall; **cypherpunk** Kurast stone walls and pillars follow the classic layout, the HD floor is
grass where classic has dark stone (biome, not this lane); **glados** dark Gothic wall runs on both sides of the path;
**downtown** high stone walls and gate pillars around the plaza; **moskvich** low ruin walls and pillars along the classic
ruins; **borgir** pillar and balustrade rows (temple style) around the area, denser than the classic view shows; **macumba**
the graveyard fence, gate pillars and walls as in classic (before this lane only the floor); **charismatic** statues, pillars
and a building corner only: most of classic's cathedral (roofs, arches) has no HD counterpart (366 cells without a D2R
model, 87 set pieces left out), and the HD floor is darker than classic's grey tiles.

## Lane wallsfix: capped wall scenes, generic walls, floors (2026-10-29, slot 3, background mode, build of lane/wallsfix)

Same check `wall_maps` (lane walls above; harness travel `h level` / `place` and god mode, so seen with the harness, not on the
player path), data of this lane's build with main's plugin of 00:05 in the slot. Sheets (HD left, classic right) are kept
outside the repo.

| run | result |
|---|---|
| `checks-20261029-034503-s3` | all 8 maps reached in HD and classic, 0 crash files; `BC_ASSERT: 0 (AssetCache.h:187)` in classic downtown, the 12th area of the launch: the same place as lane walls' earlier run and its A/B run without walls (bug #360) |
| `checks-20261029-035204-s3` (downtown only, fresh launch) | no assert in HD or classic |

HD against classic: **cypherpunk** floor dark stone (Docktown biome) where it was grass, Kurast walls and pillars as before
(4,423 of 5,825 pieces kept by the cap; the props, a third of the buttresses and pillars gone); **moskvich** floor dark stone
(Mesa biome) where it was grass; **downtown** the Harrogath walls of the former gaps stand along the plaza edges;
**charismatic** floor about as dark as before: the generated Fortress mask (zakarum plaza painted as D2R's marble plaza)
shows no visible change in these shots, so whether HD reads a mask entry for a mod .dt1 path is still open; the other maps
look as in lane walls' run.

## Lane hdwalls2: HD walls of the other 9 Median maps (2026-10-30, slot 1, background mode, build of lane/hdwalls2)

Same check `wall_maps` (lane walls above), now over all 17 maps (`WALL_MAPS` has the levels 90, 96, 15, 84, 65, 13, 14, 116
too; level 96 loads temple5 or temple6, identical in Median). Harness travel `h level` / `place` and god mode: seen with the
harness, not on the player path. Data of this lane's build; the plugin was the one already in slot 1 (no plugin change in this
lane). Commands: `MXL_RUN=hdwalls2 MXL_SLOT=1 MXL_CHAR=WallsTwo MXL_CACHE_POLL=3 MXL_WALL_LEVELS=90,96,15,84,65,13,14,116 py -3
tools/game_checks.py all wall_maps`, then the same with `MXL_WALL_LEVELS=60,59,95,18,98,126,125,127`. Run folders and sheets
(HD left, classic right) are kept outside the repo (`mxl2012-runs/hdwalls2/`).

| run | result |
|---|---|
| `checks-20261030-005953-s1` (the 9 maps on stock tiles) | all 8 levels reached in HD and classic, no assert in any of the 16 visits, 0 crash files; VariantTransformTable peak 107 / 128 |
| `checks-20261030-010654-s1` (the 8 retextured maps, with this lane's model variations and floor-tile walls) | all 8 reached in both modes, no assert, 0 crash files; the launch's whole d2rloader.log has no ASSERT line; VTT peak 105 / 128 |

On slot 1 d2rloader.log starts anew at each launch, so the report's "0 new lines" is the size mark of the previous launch;
the per-map assert lines and the copy of the whole log are what count. HD against classic per map: docs/maps-hd.md "Status
per map". In short: dungrm6a, temple5/6, excelsior3, epicwhiners, inarius and rockisdead have their walls where classic has
them; caveroom4 and belial only partly; temple5/6's HD floor is the Kurast biome's grass (biome, not walls).

## Lane cachewalls: asset caches over long sessions, the walls assert (2026-10-29, slots 2 and 4, background mode)

New: `MXL_CACHE_POLL=<seconds>` on any `game_checks.py` run reads every asset cache the probe finds (tools/cache_probe.py `poll`,
read only) into `cache_poll.jsonl` of the run folder, each record labelled with the check and step; the report gets an "Asset
caches" section with the peak of each (`py -3 tools/cache_probe.py peaks <file>` on any poll file). `wall_maps` now names the
cache and path of an AssetCache.h:187 assert per map. `MXL_CACHE_GOD=1` plays `cache_route` in god mode and its `L<id>` steps walk
without fighting (a level-1 character fought one Tamoe Highland monster for 6 min). Commands:
`MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<throwaway> MXL_CACHE_POLL=3 py -3 tools/game_checks.py all wall_maps` and, for the long route,
`MXL_CACHE_GOD=1 MXL_CACHE_ROUTE=v1,L3,L4,L7,L12,L29,L36,v2,L41,L42,L44,L47,L56,L66,v3,L76,L78,L80,L85,L88,L100,v4,L104,L105,L106,L107,L108,v5,L110,L111,L112,L113,L117,L118,L128,L129,v1,L37,v3,L83 ... all cache_route`
(`MXL_GRAPHICS=legacy` for classic). Normal difficulty, new level-1 characters; every level is reached by harness travel
(`h level`, the towns' `vN` sweep), god mode: seen with the harness, not on the player path. Plugin: lane cache360's build (no
plugin change on main since). Run folders are kept outside the repo (`mxl2012-wt/cachewalls/work/runs/`, logs in
`mxl2012-runs/cachewalls/`).

Peak per cache over the run (VTT = VariantTransformTable, default 128; UASM = UnitAnimationStateMachine, 384; the three caches
of default 512 by offset; Popcorn 1024; Model 2750; TileMaskRuleSet 16):

| run | build (own colour tables) | route, mode | VTT (ours / D2R at the peak) | UASM | 512 @0x26780 / @0x26898 / @0x269b0 | Popcorn | Model | TileMask | AssetCache asserts |
|---|---|---|---|---|---|---|---|---|---|
| `checks-20261029-052955-s2` | main 9b0953c (24) | `wall_maps`, HD then classic | **99** (14 / 85), classic cypherpunk | 244 | 274 / 222 / 185 | 560 | 1401 | 3 | **0** (16 visits) |
| `checks-20261029-063903-s4` | A/B: 9b0953c with `COLOUR_SHARE_TOL` -1 (89, no sharing) | `wall_maps`, HD then classic | **128, overflow** (44 / 84) at classic glados, capacity 192 | 244 | 275 / 221 / 184 | 559 | 1441 | 3 | **1**: classic downtown, `DefaultCapacity 128`, path `data/hd/character/enemy/mxl/v_84de0a5a.json` |
| `checks-20261029-091330-s2` | db0f90d = main 086b021+ (30) | `wall_maps`, HD then classic (+ `c4click`) | **106** (21 / 85), classic glados | 244 | 280 / 221 / 184 | 567 | 1608 | 3 | **0** |
| `checks-20261029-055628-s2` | main 9b0953c (24) | long route (40 steps, all acts, twice Act 1 / 3), HD | **97** (15 / 82) | 231 | 291 / 207 / 170 | 567 | 1746 | 2 | **0** |
| `checks-20261029-070157-s2` | db0f90d (30) | long route, HD | **102** (20 / 82) | 240 | 303 / 217 / 180 | 567 | 1756 | 2 | **0** |
| `checks-20261029-080807-s2` | db0f90d (30) | long route, classic | **104** (22 / 82) | 230 | 291 / 207 / 170 | 575 | 1773 | 2 | **0** |

Findings: the walls assert of lanes walls / wallsfix (classic downtown, the 12th area of the launch) is the VariantTransformTable
cache of bug #360: the A/B build without colour sharing brings it back at the same place, naming our own table, and the fixed
builds stay at 99 / 106. Classic mode loads the same HD variant tables as HD (the classic half of `wall_maps` peaks higher than
the HD half: it comes later in the launch). Every other cache stays at 80 % of its default or less (VTT 106 / 128 = 83 % is the
highest; UASM 64 %, the 512s 59 %, Popcorn 56 %, Model 65 %). The D2R part of the VTT peak is 82-85 tables on every route; our
part is 50-73 % of our tables (14 of 24, 20-22 of 30, 44 of 89), so peak = about 85 + 0.7 x our tables: **30 tables give 102-106;
about 50 tables would reach 120** on these routes.

`c4click` (real click into Catacombs 4) in `checks-20261029-091330-s2`, new character `Cachewall`: not entered. The harness
`tiles` verb lists two tile units and then fails (`tiles FAIL crashed (exception in the game call)`, bug #399) on this map seed,
so the stairs down of Catacombs 3 were never found (only the 5 loaded rooms round the arrival have presets); the new wider
`place` rings round the stairs (travel help, real clicks from each spot) did not get to run. Still open: the player-path entry.

## Nightmare/Hell, lane nmhell2 (2026-10-29, slot 1, background mode, build of lane/nmhell2 with main's plugin)

Checks added to `tools/nmh_checks.py` (registered in `tools/game_checks.py`): `nmhhitlog` (hit log on Andariel / Duriel
Nightmare; `MXL_NMH_HITLOG=andariel,duriel`, `MXL_NMH_HITLOG_GEAR=kill` for the kill build), `nmhdialog` (the difficulty dialog of
the characters in `MXL_NMH_DIALOG`, screenshot and Esc, nothing entered; a save below progression 5 is not played) and `nmhkill`
(`MXL_NMH_KILL=nightmare:andariel,nightmare:travel12,nightmare:duriel,hell:andariel`). Character: lane nmhell's `Nmhbarb`
(level 120, progression 10: its Nightmare boss quests were already DONE by nmhell's Hell set-up save edit, so quest bits do not
move on a Nightmare kill). Logs `mxl2012-runs/nmhell2/run1.log` .. `run3.log`; run folders `work/runs/checks-20261029-023811-s1`
(run1), `-030223-s1` (run2), `-034745-s1` (run3).

The plugin carries no `hit`, `avoid` or `skilldmg` verb (the harness table above lists them, `harness_cmds.cpp` has none), so
the hit log is made of reads: before each right click the player's states (`states player`), after it five reads 0.25 s apart of
the boss's life and of both modes (`state`); boss and player stats once per fight. Diagnostic help (named in each row): the
player's life is filled by harness before a click when it is below 70 %.

| Step | Result | Path | Evidence |
|---|---|---|---|
| Hit log Duriel NM (nmhell's gear) | 16 clicks: the player was stunned (state 21) at 15, sat in get-hit / neutral (modes 4 / 1), Duriel attacked without pause (modes 4, 5, 14); 1 click did damage: 52,341. His stats: dodge / avoid / evade 50 (monprop `mon-avall`), block 25, defense 392, **damage resist 35 and defense +300 %** (his `Idol2Scosglen` state 290 was on: 100 + 5 x 40 at skill level 1 + Nightmare's MonsterSkillBonus 4). On the player: Void Archon Amp Aura (state 237): damage -25 %, attack rate 74. With block set to 0: 2 of 16 clicks did damage (37,782 each); dodge / avoid / evade cannot be zeroed by `stat set` (still 50 afterwards: not on the base list) | player clicks, reads by harness | run1 |
| Hit log Andariel NM (nmhell's gear) | not reached: the character died on the way twice (Catacombs 4) | | run1, run2 |
| Hit log, kill build, both bosses | Andariel: stunned at 12 of 16 clicks, 1 did damage: 134,968 (8,435 per click). Duriel: stunned at 8 of 16, 2 did damage: 92,947 each (**11,618 per click, more than Andariel**); his Idol2Scosglen state was off this time (damage resist 0) | player clicks, reads by harness | run3 |
| Difficulty dialog, progression 5 vs 10 | Hell is drawn **dimmed** at progression 5 (plate and frame darker: mean grey 42.6 vs 67.3 at progression 10, text 56 vs 83; Normal and Nightmare identical to the pixel). Normal-only save (progression 0): no dialog, Play starts Normal. Both as D2R / 1.13c: not a bug | player (menu clicks) | run1 `nmh_dialog_card_Nmhbarb.png`, nmhell run1 `nmh_dialog_nightmare.png`, `mxl2012-runs/nmhell2/dialog_prog5_vs_prog10.png` |
| Andariel NM kill | killed: 794 s, 4 deaths; right clicks 13 (0 damage), cast-function fallback 13 (257,618): **cast function (help)**, not the player path. No mercenary (the hire failed: gold fixture 30,000 under Kashya's 80,700) | cast function | run2 |
| Act 1 -> 2 travel NM (Warriv) | PASS: Warriv's `d36` line, arrival in Lut Gholein (area 40). The line was already there before the kill (quest DONE from the save edit), so this shows the travel, not the kill opening it | player (NPC menu) | run2 |
| Duriel NM kill | killed: 507 s, 4 deaths; right clicks 48 (51,329), cast-function fallback 61 (194,969): **cast function (help)**; no mercenary | cast function | run2 |
| Andariel Hell kill | FAIL: Rogue hired from Kashya on the player path (level 119, 66,875 gold; fixtures 200,000 gold and the Burial Grounds gate bit), the Catacombs 4 packs killed the character 6 times before it reached her; the mercenary was dead at the end | player (hire), clicks | run3 |

Kill build (help, named in each row): axe 29,600-59,200 (Nightmare) / 88,800-177,600 (Hell), 400 % AR, 60 % IAS; body armour
+300 % defense, 30 % DR, 100 % FHR; ring 200 % FHR, 50 % DR, +7,200 vitality; belt +36,000 vitality; amulet 75 resist; second ring
+50 / +100 resist; Full Rejuvenation Potions made on the ground, picked up by click into the belt, drunk with the belt keys
below 45 % life.

Duriel's damage, the answer: per landed hit the two bosses take the same damage within Duriel's own Median data: his Void Archon
Amp Aura (-25 % damage and -26 attack rate on the player), and while his Idol2Scosglen state is up 35 % damage resist and +300 %
defense. Per click the numbers are ruled by how few clicks start a swing at all: the player is stunned at 8-15 of 16 clicks
against either boss. Duriel's tables give it: stun 50 frames on his A2 in Nightmare (vanilla D2R 20) and an AI delay of 4
(vanilla 15), so he attacks about four times as often and stuns 2.5 times as long. With 1-2 landed hits per 16 clicks a per-click
average swings with each hit (run3 had Duriel above Andariel); nmhell's 870 vs 11,500 is that noise plus the reductions above,
not a damage hook: the plugin's only part in the damage path is the dodge-list assert skip (`dodge_list.cpp`, after the dodge is decided). All values are Median XL
2012's own (monstats, monprop, skills, difficultylevels); not a port bug. Also Median's: its potions heal over time
(`hpregen` x (1 - `nightmare_no_regen`)), and Duriel's aura sets `nightmare_no_regen`, so potions do nothing near him.

Seen, not filed:
- `cast 352` reports usability code 2 ("passive or requirements") on most calls with the axe worn and the player then swings a
  plain attack (mode 7, A1), not Blood Hatred's sequence (mode 18); during one stretch (run2, 03:31:59-03:32:07) it was 0 and the
  mode was 18. The axe is a `mele` type (axe -> mele -> weap), as Blood Hatred's `itypea1` asks. Same for both bosses, so not
  the Duriel difference; needs a skills lane (is the right click Blood Hatred at all?).
  Answered by bug #397 (lane skilluse): Blood Hatred needs a melee weapon in each hand (Median's rule); the 0 stretch came after the
  corpse pickup had put the old axe in the left hand.
- The stun on the player also shows next to Andariel (12 of 16 clicks), who has no stun element: its source there is not known
  (Catacombs 4's pack or a Median proc).
- `nmhdialog` in run1 played the Normal-only `RpDie` (Play skips the dialog), entered a Normal game and left it: its save in the
  slot's folder was written again (02:47:59; run_all backs saves up at the start). The check now skips saves below progression 5.

Left: a player-path kill (clicks, not the cast function) of both bosses; Andariel Hell (the Catacombs 4 packs); Duriel Hell; a
mercenary with gear in the Nightmare fights; Act 2-5 Nightmare / Hell. (The `usable=2` question above is answered by bug #397.)

## Nightmare/Hell, lane nmhell3 (2026-10-29, slots 1 and 4, background mode, build of lane/nmhell3 with main's plugin)

The boss runs again with an axe in each hand (`axes()`, bug #397), so the right click is Blood Hatred. Character `Nmhbarb`
(as nmhell2: level 120, progression 10, its Nightmare boss quests already DONE in the save, so Nightmare quest bits do not move;
Hell quests start empty). Logs `mxl2012-runs/nmhell3/run2.log` .. `run5.log`; run folders `work/runs/checks-20261029-055258-s1`
(run2), `-070312-s1` (run3), `-073810-s4` (run4), `-094514-s4` (run5).

`nmhkill` now runs every act (`MXL_NMH_KILL=hell:mephisto,hell:diablo,...`; also `travel12/23/34/45` and `ancients`). Per boss:
town of the act (kill gear, Full Rejuvenation potions picked up into the belt by click, mercenary hired only in act 1), harness
travel to the boss's level (help), Diablo's seals and the Baal approach walked with the kill gear, then right clicks (Blood
Hatred) with the cast function as fallback, retries after deaths. New in the rows: player and boss mode 0.35 s after each swing,
the boss's states and stats, wall time, the drops (gold piles and up to 8 items picked up by click, `identify all` as help, the
tooltips hovered in the backpack and screenshotted). Optional: `MXL_NMH_PLACE=<boss,...>` (travel help `place` at the boss's
preset), `MXL_NMH_DIAG=<boss,...>` (units of the boss's class in view; his life set to half by harness and read after 0.2 / 1 /
3 s: tells regeneration from no hits).

| Boss | Result | Path | Help | Deaths | Time to kill | nmhell2 | Run |
|---|---|---|---|---|---|---|---|
| Andariel NM | killed; 4 clicks did 0, 5 cast-function calls 241,518; player mode 1:7 18:2 | cast function (help) | kill gear, merc (Kashya, 80,700 gold, fixture 200,000), harness travel | 1 | 87 s fighting, 111 s wall | 794 s, 4 deaths, cast function | run3 (run2: 5 deaths on the Catacombs 4 walk, 0 clicks on her) |
| Duriel NM | **PASS: 1 right click did all 246,300** | **player (click)** | kill gear, harness travel | 0 | 4 s | 507 s, 4 deaths, cast function | run2 |
| Mephisto NM | FAIL, never hurt: 12 clicks + 16 casts for 0; player mode 18 in 10 of 28 swings, his mode only 1 / 4 (never get-hit 3 or block 6). Life set to half stays half: no regeneration, the hits never land | player (clicks) | kill gear, harness travel | 5 (each of 3 runs) | - | not reached | run3, run4 |
| Diablo NM | FAIL: no Diablo; seals 395 + 396 (run2) / 394 (run4) opened by mouse click, 8 / 7 deaths on the seal walk (60 min in run4) | player (seal clicks) | kill gear, harness travel | 7-8 | - | not reached | run2, run4 |
| Ancients NM | **PASS**: summoned 540-542, quest 39 `0001...` -> `1001000000000100`, gateway to 128 | player (Attack) | kill gear | 0 | - | not reached | run4 (run2 FAIL with the acts gear) |
| Baal NM | FAIL: not reached. He is at 15135,5920 in level 132; the server path refuses (code 4), `place` finds no free spot near him, the walk got from 15167,5888 to 15166,5906; life diagnostic stable | - | kill gear, harness travel | 0 | - | not reached | run2-4 |
| Andariel Hell | **PASS: 22 right clicks did all 750,000** (30 casts 0), player mode 18:27 1:25; quest 6 `0000100000000000` -> `0100100000000100` | **player (clicks)** | kill gear, merc (66,875 gold), harness travel | 1 | 197 s fighting, 218 s wall | FAIL (6 deaths before her) | run4 |
| Duriel Hell | FAIL: 13 clicks for 0; player mode 1:8 4:2 18:1 (stunned), his 14:6 1:4 5:2 4:1; states 105, 237, 290 (Idol2Scosglen: damage resist 35, skill defense % 420) | player (clicks) | kill gear, harness travel | 5 | - | not run | run4 |
| Mephisto Hell | FAIL: 6 clicks + 7 casts for 0 on 1,000,000; his mode 4:7 1:4; life diagnostic stable | player (clicks) | kill gear, harness travel | 5 | - | not run | run4 |
| Diablo Hell | no row: the batch hit the tool's 2 h limit in the seal walk | - | - | - | - | not run | run4 |
| Ancients Hell | **PASS**: killed 540, 541, 542, 0 deaths, quest 39 -> `1000000000000100`, gateway to 128 | player (Attack) | kill gear | 0 | - | not run | run5 |
| Baal Hell | FAIL: not reached (as NM; the walk did not move from 15166,5893), 1 death to the chamber's pack | - | kill gear, harness travel | 1 | - | not run | run5 |

Blood Hatred is used: mode 18 after 27 of 52 swings on Hell Andariel, and the click kills Duriel NM in one swing. The Nightmare
Andariel kill still went to the cast function (her clicks hit get-hit / neutral frames: player mode 1 at 7 of 9).

Drops and gold (screenshots looked at): Duriel NM: Graven Image (unique Gargoyle Head, full tooltip), Ral Rune, `!@7` "Dogma of
Pain" (only its green name: Median's own row, a name string and no stats). Andariel NM: gold 0 -> 96,900 from 4 of 7 piles;
items 405, 817, 294, r15, `!@6`, `2@D`, Pilum tooltip fine. Andariel Hell: 7 gold piles (1 picked up, gold 0 -> 109,141), 12
items; Koth's Lesson (unique mace, full stats), Razordisk (unique buckler, red Dex requirement 75: the character has less),
Io Rune, Chipped Emerald, Dogma of Suffering (name only, as Dogma of Pain). No ERROR string, no blank tooltip.

Asserts: #54/#73 `nDirectionIndex < nDirections` (Duriel Hell, known); #394 `ptCreate->hSource` again in the Nightmare seal walk
(run4, game went on); the exit-only pool asserts (`m_freed == 0` etc.). No crash, no hang from #395.

Seen, not filed (open questions):
- Mephisto (both difficulties): Blood Hatred swings play (mode 18) next to him, yet he is never hit and never in get-hit or block.
  The character stops about 3 sub-tiles from him (17587 vs 17584); the Durance 3 moat edge is the likely cause (the acts lane's bow
  also failed there; only Frigid Sphere hurt him in Normal). Needs a check whether a melee hit can cross that edge in D2R / 1.13c.
  Lane endgame: melee from 2 cells with no blocked cell between hits him (52,984 -> 46,569); across the moat the walk-to-target
  of a melee attack has no path, as in 1.13c: not a port bug (section "Lane endgame").
- Baal (both): 15135,5920 in level 132 has no reachable spot from the harness arrival; his position may be the throne before the
  waves. Needs the wave sequence on the player path (Throne of Destruction, level 131) instead of the travel help. Lane endgame:
  all five waves cleared and 132 entered by a mouse click on portal 563; Baal killed (by the travel help) with quest 40 set.
- Baal Hell: quest 40 went `0010000000000000` -> `1000000000101000` (done bit) on the travel into level 132 without a kill.
  Lane endgame (Normal): three travels into 132 without a kill left quest 40 at `0000000000000000`; not reproduced there.
- Duriel Hell: the stun lock of nmhell2 (his A2 stun, AI delay 4), now with Idol2Scosglen up; Median's data.
- The Diablo seal walk with the kill gear still dies 7-8 times (Chaos Sanctuary packs); deaths put the acts gear back on the walk.

## Player-path checks, round 2 (lane realpath2, 2026-10-28/29, slots 3 and 1, background mode, plugin of main)

The open items of round 1. Plugin: the main checkout's `build/plugin/Release/mxl2012-core.dll` (no plugin change in this lane);
data: `tools/build.py` of the lane (main merged, superunique separator #362 in).

| Item | Run (work/runs/) | Result | Notes |
|---|---|---|---|
| 16 class weapons / shields not worn at rarm (round 1 FAIL) | checks-20261028-193921-s3 | all 16 PASS (rerun of the arm items: 22 items, PASS 19, REFUSED 3) | The check's fault, not the game's: the off hand still held a quiver (Amazon, Druid) or a katar (Assassin) from an earlier round (`d2save.py show` of the round's save backup), so the 1.13c rules refused the new weapon (a two-hander needs the other hand empty; a quiver only next to a weapon that shoots it; no two shields). `rp_item_round` now frees both hands for a hand item. REFUSED: `!07` needs Dex 558 (the character has 240) |
| `skillprog` paladin half ("could not play a paladin") | checks-20261028-193921-s3 | both halves played: Batstrike 4 of 4 casts; Blackstorm 4 casts, cltprg 28 called 4 times, state 43 seen | The paladin was card 18 of 29 saves: the click landed below the list and Play entered the selected assassin. Main's #361 fix (cards past 9 refused) plus `card_on_list`: a character off the list gets the newest time on its own save files first, also in `switch_character` |
| `rp_death` corpse | checks-20261028-195354-s3 | PASS | level-1 Sorceress died to natural Stony Field monsters after 9 s, Esc respawned in town, Save and Exit + reload: the gear stayed on the corpse; two left clicks round the character (rings of 30-110 px) took it back: worn `151@4`, `600@3` again |
| crash-audit C14, C17, C18 (check `crashrows`, not `rp_`: it spawns the witches) | checks-20261028-195354-s3 | PASS | C14: Druid Trap Rat Form (448) and Treewarden Form (463) by right click, Save and Exit, 3 rounds: `transguard` events 44 -> 48, 0 skipped. C17: `soundguard` 12119 sound rows, 0 bad ids; witches 1722 and 1740 (Median Neutral sounds) in view. C18: cube opened by right click and closed with Esc 5 times, no crash. [crash-audit.md](crash-audit.md) updated; C19 (Steam 94995) cannot run here |
| waypoint act tabs (check `wptabs`, a look) | checks-20261028-193921-s3, 195354-s3 | tabs II-IV shown after the set-up; V not | The tabs were missing, not mispositioned: D2R draws a tab only for an act the character's quests opened. Set-up by save edit (`rc_setup.set_quest_bits`, done flag on quest words 7, 15, 23) shows II, III, IV at x 196 + 72 x (act - 1), y 184. Word 28 alone did not show V; 26 + 28 do (run checks-20261029-040618-s1) |
| `rp_vendors` acts 2-5 | checks-20261028-195354-s3 (B), 200728-s1 (C, cut by the tool's time limit), 211447-s3 (D), 223413-s3 (E), 20261029-000330-s3 (F) | partial | Buy + sell back: Jamella (B, also gamble rin), Halbu (B), Fara (D, E), Ormus (D, E, F), Alkor (F, also gamble rin), Malah (B, D, E), Lysander buy (F; the sell back of the key did not take). Not reached: Drognan (the server path and the click walk stop 34 away, at his house wall), Larzuk (42 away, as in round 1), Elzix, Asheara, Hratli, Drehya (Anya is in town only after her quest). Check fixes: NPCs out of view are walked to with the server path (`moveto nearest`, it knows loaded NPCs out of `state`'s 40), legs round the arrival until it does, the click walk when it stalls; endless stock (potions, keys) buys a copy with a new id (E's "bought nothing" at Lysander and Alkor took gold every click and filled the backpack, so Alkor's gamble had no room). Engine: #360 (AssetCache) again in D, E, F; #190 (`activeUnit`, InventoryItemWidget.cpp:378) in D and F |
| `rp_items` Barbarian items 150-527 (slices of about 95, one slot lock each) | 150:245 checks-20261029-005255-s3 (crash), rerun 010902-s3; 245:340 005715-s3; 340:435 012157-s3; 435:528 013505-s3 | 150:245 PASS 92, SKIP 3; 245:340 PASS 95; 340:435 PASS 93, FAIL 2; 435:528 PASS 46, REFUSED 43, FAIL 4; one crash (bug #393) | Crash: the harness-made `cm3` (Median's 0 x 0 "Charm Large", no player source) picked up from the ground: `BC_ASSERT: x >= 0 && x < pPage->bWidth`, game gone; cm1-cm3 are SKIP now. FAIL 340:435: Book of Skill (`ass`) and Horadric Cube (`box`) not taken by the pickup (quest items: one cube per character, the book by quest state; game rules). FAIL 435:528: the harness generator made no item for set rows 128, 129, 134 (MRFrost, MRWater, MRCelestia's Ribbon) and unique 1770 (`key`, SkillsdLastSkillEver): the generator's path, not judged. REFUSED: requirements above a level-120 Barbarian's Str 335 / Dex 210. Engine: #35 (`wPrefix != 0 \|\| wSuffix != 0`) once per slice |
| `rp_areas` act 1 (`MXL_RP_ACTS=1`, 180 s per area) | checks-20261029-015018-s3 | PASS on the game staying up; the fights not judged | 9 of 9 act 1 waypoints reached: 6 by the panel, 3 by the fallback warp (4, 27, 29). Blood Moor, Den of Evil, Burial Grounds, Catacombs 4 entered, game up; one natural death in Catacombs 4 after 40 s. 0 kills and no boss in view: the left button held Throw (skill 2) from RpBarb's save, so the left clicks attacked nothing; `rp_fight` now selects Attack first (rerun open) |
| `rp_areas` acts 1-3 (`MXL_RP_ACTS=1,2,3`, 180 s per area, Attack selected) | checks-20261029-031050-s3 | PASS (game up in every area) | 27 of 27 waypoints of acts I-III reached: 18 by the panel (tabs II and III used, set-up quest words 7 and 15), 9 by the fallback warp (4, 29, 43, 48, 57, 74, 76, 80, 83: the row click missed; not yet looked at). Den of Evil 4 kills, Burial Grounds 1, Duriel in view in his lair; Corpsefire, Blood Raven, Andariel, Mephisto not in view in 180 s. Natural deaths in Burial Grounds (141 s), Catacombs 4 (39 s) and Durance 3 (16 s): the level-120 Barbarian with the starting axe is no match for Median's act bosses' areas. No crash, no new assert |
| `rp_areas` acts 4-5 + `wptabs` (`MXL_RP_ACTS=4,5`, slot 1) | checks-20261029-040618-s1 | PASS (game up); tab V shown | SET-UP: quest words 7, 15, 23, 26, 28 in RpBarb's save; the waypoint panel then shows all five tabs, V lists Harrogath to Worldstone Keep Level 2 (`wptabs_act5.png`): Diablo's quest (26) with word 28 opens act V. 12 of 12 act IV-V waypoints reached, 10 by the panel, 2 by the fallback warp. Chaos Sanctuary, Bloody Foothills, Halls of Vaught entered; natural deaths in Chaos Sanctuary (29 s) and Halls of Vaught (8 s); Diablo (only after the seals) and Nihlathak not in view. No crash |

Not done / open (round 2):

- `rp_vendors`: Drognan, Larzuk (the server path stops at a wall; `rp_ring_approach` added after the last run, not yet run),
  Elzix, Asheara, Hratli, Drehya (Anya only after her quest); Lysander's sell back of a key (gold taken, the lift click did not
  hold it); one Fara round read a menu with only the talk line (flaky, the other rounds traded).
- `rp_areas`: the 11
  waypoint rows that fell back to a warp; a stronger set-up character to reach the act bosses.
- `rp_items`: set rows 128, 129, 134 and unique 1770 are not made by the harness generator (not judged).
- Bug #393 (0 x 0 cm1-cm3): no player source; `spawnable` 0 in the prep step would close it if wanted.

## Lane hdmon2: Act 1-2 Normal HD stand-ins (2026-10-29, slot 3, background mode, build of lane/hdmon2)

Check `hm2_monsters` (`MXL_RUN=<run> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all hm2_monsters`; optional
`MXL_HM2_ONLY=<id,...>`): one launch in HD, `god 1` and Tank, each of the 13 Ids whose stand-in this lane changed (or whose
donor got a clip fill) spawned beside the player in Blood Moor (area 2) or Rocky Waste (area 41) by its `*hcIdx`, shots after
2.5 s and 5 s, then `kill` and a death shot (`hm2_<id>_near|fight|death.png`), engine asserts counted per monster. A
**graphics check, seen with the harness** (spawn, god mode, Tank), not the player path. Run folders are kept outside the repo.

| run | result |
|---|---|
| `checks-20261029-043155-s3` (final) | PARTIAL by design: all 13 spawned, **0 asserts, 0 ERROR/ASSERT in d2rloader.log, 0 crash files**, the player alive throughout; look judged by hand below |
| `checks-20261029-041813-s3` (no god mode) | the same 13 spawned, 0 asserts; a zombie pack killed the tanked level-1 player during zombierags / greenzombie (hence `god 1`) |
| first run | `spawn` refused the monstats Id (`usage: spawn <monster class>`): the check now spawns by `*hcIdx` |

By eye: every stand-in draws as a full HD model (none invisible, none a classic sprite) and walks up, attacks and dies.
hell_dragonknight (doomknight2) and the zombie1 Ids read clearly at their new scale; deathwing1 (vulture1) and centaur1
(clawviper1) are small next to the player and partly hidden by the Rocky Waste ruin they spawn behind. cloakdagger,
hell_dragonknight and dead3 look strongly blue, corpseworm and cultist1 green: that is the per-Id colour variant (lane
`tints`), not the unit choice.

## Lane skilltips: skill tooltip lines (bug #396, 2026-10-29, slot 1, background mode, build of lane/skilltips)

Check `stip_tooltips` (`MXL_RUN=<run> MXL_SLOT=N MXL_STIP_CLASSES=<class> py -3 tools/game_checks.py all stip_tooltips`; one class
per run fits a 10-minute call): a fresh level-1 Normal character per class (mortal, no god mode), the right skill button's popup in
HD and the three skill tree tabs in HD and in classic graphics, every skill hovered by the background cursor and each tooltip shot
(`stip_<cls>_<hd|legacy>_<pop|tree_tabN>_<cell>.png`); the plugin part `skilltext` counts the labels it cut (`mxl2012`). Set-up,
named in the row: the sorceress learns Fire Wall by `setskill` (Median 2012 gives it no class, so a new character has no Fire Wall
in the popup). Classic's popup draws skill names only, so classic is read in the tree. Player path (hovering is what a player
does). Run folders: `mxl2012-runs/skilltips/checks-*-s1` (report.md and the game logs in each).

| run | class | result |
|---|---|---|
| `checks-20261029-042243-s1` (first version: classic popup, no Fire Wall) | sorceress | `mxl2012` lists `skilltext ... (0x287a50 hooked)`; labels cut 0 -> 785; HD tree 18 tooltips; classic popup names only (the check changed to the classic tree) |
| `checks-20261029-042952-s1` | sorceress (+ Fire Wall, set-up) | PASS of the counted part: HD popup 3, HD tree 18, classic tree 18 tooltips; labels cut 0 -> 2,233; 0 asserts, 0 crash files |
| `checks-20261029-043540-s1` | amazon | the same: HD popup 2, HD tree 18, classic tree 18; labels cut 0 -> 984; clean |
| `checks-20261029-044112-s1` | necromancer | the same: HD popup 1, HD tree 18, classic tree 18; labels cut 0 -> 768; clean |

Read by hand (**verified in game**): Fire Wall (`stip_sor_hd_pop_5.png`) reads "Fire Duration: 0.3 seconds", "Average Fire
Damage: 70-93 per second", "4 yards", "Mana Cost: 44", where lane hdicons2's `hdi_popup_sor_hd.png` showed "Fire Duration: %d
seconds0.3 seconds", "Average Fire Damage: %d-%d70-93Mana Cost: %d per second" and "FLYING POLAR BUFFALO ERROR44". Flamefront
(HD and classic tab 3) "Fire Damage: 2-4", "Mana Cost: 10"; Balefire "Magic Damage: 4-5", "Mana Cost: 18"; Angel of Death "Poison
Damage: 143-238 over 0.4 seconds", "Mana Cost: 15"; Frostclaw Totem (classic) "Cold Damage: 3-6", "Mana Cost: 16". No `%d` and no
dummy string in the 8 shots read one by one (the ones named here, the town portal scroll, and Force Wall / HD Flamefront of
the first run); the other 108 of the 114 tooltip shots of the last three runs were not read one by one. The numbers follow 1.13c's formulas on the data: Fire Wall mana
(176 << 6) >> 8 = 44, damage (15..20 << 4) * 25 * 3 / 256 = 70-93 per second; Flamefront mana (20 << 7) >> 8 = 10, damage
(20..40 << 4) / 256 = 1.25-2.5 times the +41 % energy bonus = 2-4 (the renderer's number code is D2R's own, the plugin changes text
only). Left: Median's colour code `ÿc/` (706 texts, the long descriptions) draws as "*/" in HD and "Ø/" in classic.

## Skill usability, lane skilluse (2026-10-29, slot 1, background mode, build of lane/skilluse with main's plugin)

Check `su_use` (`tools/game_checks.py`), run folder `work/runs/checks-20261029-045441-s1`. Set-up by the harness (help, named in
the CHECK line): a level-120 barbarian (the sweep's Session, Blood Moor, zombies with raised life as targets), strength /
dexterity 1000, skills by `setskill`, gear by `equip` (Axe (Grade 1) 400-800, a throwing axe for Bear Claw), mana 200 max and
current before each click. Then real background clicks on the zombie; no god mode, no easykill. The first run
(`checks-20261029-044935-s1`) had the sweep's 5000 mana: regeneration hid every cost (mana -0 on all clicks), so it proved
nothing about mana.

| Item | Result | Evidence |
|---|---|---|
| Blood Hatred (352), one axe, 3 right clicks | VERIFIED refused: modes 1/7 (A1, Attack), mana 0, damage 1254-2337 (the plain swing); `cast` usable=2 | su_use, bug #397 |
| Blood Hatred, an axe in each hand, 3 right clicks | VERIFIED cast: mode 18 (SQ) on 2 clicks, mana -21 / -7 / -10, damage 5668-11403; usable=0 | su_use |
| Bear Claw (443) while Bear Stance (431) holds state 47 `aura_2` | VERIFIED refused: no missile, no damage on 2 left clicks; usable=4 (restrict) | su_use |
| Bear Claw with the stance off | VERIFIED cast: missile 1371 and damage on 2 left clicks | su_use |
| Fortress (440) | VERIFIED cast: state 58 `unfortunate`, mana -55, missiles 2283-2285 | su_use |
| Bear Claw during Fortress's state 58 | VERIFIED refused: no missile, no damage | su_use |
| static audit `py -3 tools/skill_use_audit.py` (built tables, 7 classes) | never 0, dual_wield 1 (352), form 9, gear 64, locked_by 69 | bugs.md #397 |

Seen: Fortress's known assert (bugs #54/#73, `nDirectionIndex < nDirections`) once per run; usability of Bear Claw during Fortress
was read after state 58 ended (recorded None), the clicks are the evidence.

## Lane hdlook: today's HD work looked at in game (2026-10-29, slot 3, background mode, build of lane/hdlook with main's plugin of 00:05)

Check `hdl_look` (tools/game_checks.py, unit tests `tools/tests/test_game_checks_hdlook.py`):
`MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=HdlAma MXL_CHAR_CLASS=amazon MXL_HDL=<stages> [MXL_HDL_CLASSES=paladin,assassin] py -3 tools/game_checks.py all hdl_look`,
stages `fx mons ui items walls` (default all). SET-UP, named here and in the check's note: one character per class (HdlAma,
HdlPal, HdlAss, made when missing), level 120 by the game's xp award, stat points by the stat packet, skill points by `setskill`
(the game's point function; Ennead skills also get the quest stats 504 / 505), mana refilled by `setstat` before each cast,
the Blood Moor reached by `level`, a target zombie spawned with its life raised. JUDGED: the skill picked on the right button
by packet 0x3c (what the skill bar sends) and two background right clicks on the target, eight shots per skill and mode;
`missiles` counts the tinted rows the cast made. Screenshots are kept outside the repo (`mxl2012-runs/hdlook/run1`).

Run `checks-20261029-042207-s3` (stage fx, all three classes): 0 engine asserts, 0 crash files, watchdog clean.

| Item | Result | Path | Evidence |
|---|---|---|---|
| Balefire (Amazon 312: `balefirebolt` x74, `balefireball` x2; tints `ground_fire_083b77`, `diabwa_da45ad`) | PASS: green ground fire in HD as in classic | player cast (set-up above) | `hdl_fx_ama_312_hd_1.png` / `_legacy_1.png` |
| Better Bloodstorm (Amazon 313: `bettercenter` x2; tinted Bone Spirit `bone_cbec0a`) | PASS: purple spirit in HD, purple sparkle in classic | player cast | `hdl_fx_ama_313_hd_0..4.png` / `_legacy_*` |
| Ring of Light (Paladin 509: `barringmakerflame` x128; `ground_fire_a9bb6b`) | PASS: pale gold fire ring in both | player cast | `hdl_fx_pal_509_hd_1.png` / `_legacy_1.png` |
| Holy Trap Advanced (Paladin 510: `holytrail` x295; `ground_fire_a9bb6b`; `sunflames` not made by these casts) | PASS: yellow-white fire star in both | player cast | `hdl_fx_pal_510_hd_2.png` / `_legacy_6.png` |
| Fireball Sentry (Assassin 339: `sentryfireballbolt` x22; the Median fire bolt effect `mxl_ice_blast_cb8e0f3`, same as `barfirebolt` / `magefirebolt1`) | **FAIL**: pale blue-white bolts in HD, orange fire in classic (bug #403) | player cast | `hdl_fx_ass_339_hd_5..7.png` / `_legacy_5..7.png` |
| Dark Power, purple Frost Nova `darkpowernova` (oskill of the unique wand Blackheart; no class has it) | not seen: `equip` refused the wand while the starting weapon was worn; the check now unequips first, not re-run | | run1 log |
| Vampiric Icon (Assassin 614, `vampflame`) | not seen: `setskill` left 0 (the Ennead quest stat was missing); the check now sets it, not re-run | | run1 log |
| Skill trees, Amazon and Paladin, HD and classic | PASS for the opening page: Median's page art, icons crisp in their boxes, Median's tab titles (Special / Defensive ...), classic shows Median's column of labels; level boxes and the other pages not seen (the run's skills are on other pages; the check now clicks each tab, not re-run) | player (T key) | `hdl_tree_ama_hd_0.png`, `hdl_tree_pal_legacy_0.png` |
| Skill bar, HD and classic | PASS: the picked skill's icon on the right button, crisp | player | `hdl_bar_*`, every `hdl_fx_*` shot |

Not run (slot 3 was held by other lanes for over an hour after run 1; the coordinator or a later lane runs them with the line above):
`MXL_HDL=fx MXL_HDL_CLASSES=paladin,assassin` (Dark Power, Vampiric Icon, tree pages), `mons` (Quill Rats 1-5 and Wisps 1-4
spawned alive in a row in HD and classic: harness spawns), `ui` (inventory and cube with Median items), `items` (Charsi's and Akara's
trade windows by talk and the menu's Trade line, every HD tab; the stash walked to and clicked), `walls` (downtown = Crypt 1 A
from the Cold Plains waypoint, glados = Disused Fane from the Kurast Bazaar waypoint: the waypoint panel, then the entrance's own
server warp `level <id> warp` as a shortcut for the walk).

## Lane missiles395: the Heretics' skull swarm load (bug #395, 2026-10-29, slots 2 and 4, background mode, build of lane/missiles395)

Check `swarm` (`MXL_RUN=<run> MXL_SLOT=N MXL_SWARM_N=10 MXL_SWARM_SECS=150 py -3 tools/game_checks.py all swarm`): Tank, then
N Heretics (`cultist2`, class 1609) spawned 6 from the character in the Blood Moor; every ~5 s the game frame, the newest
missile id near the character, the live server missiles (`missiles`) and the game's private memory; life is set back to
30,000 each sample. A **load probe seen with the harness** (spawned monsters, life kept full), not a player-path verdict.
"Before" = Median's values put back into the built missiles.txt for the run only (the clean build was reinstalled after).

| run | build | ids per frame (median) | live server missiles (median / max) | frames/s (median / min) | private MB |
|---|---|---|---|---|---|
| `checks-20261029-055222-s4` | before (Param1 1, NextDelay 4) | 77 | 904 / 1002 | 26.6 / 22.3 | 9359 -> 9045 |
| `checks-20261029-054841-s4` | after (Param1 2, NextDelay 2) | 43 | 520 / 615 | 26.4 / 22.2 | 9442 -> 9455 |
| `checks-20261029-051914-s2` | before (other character) | 73 | 767 / 856 | 26.6 / 22.2 | 9086 -> 9106 |
| `checks-20261029-052254-s2` | first try, SrcDamage 192 (dropped) | 45 | - | 27.0 | 9020 -> 9045 |

Same character on slot 4: about 44% fewer missiles with the fix, no frame drop and no memory growth in 150 s with either
build (the hang of bug #395 came after 9 minutes with more Heretics). The slot-4 character regenerates to full between
samples, so the damage per skull pass could not be compared there; on slot 2 the SrcDamage-192 try killed the 30,000-life
Tank in about 5 s (Median's values: about 300 life per 5 s), which is why the fix raises the hit rate instead. Lane srcdamage: those ~300 were not 5 s of damage (the check set life back and read it in the same second); D2R reads SrcDamage like 1.13c, so 192 doubles the weapon share. The check now reads life before the reset (`MXL_SWARM_LIFE`, `MXL_SWARM_MONSTER`, life lost per sample and deaths in its note).

Lane srcdamage re-ran the probe with the corrected life reading (slot 4, 2026-10-29, `MXL_SWARM_LIFE=200000 MXL_SWARM_N=10
MXL_SWARM_SECS=90`, plugin of main's source; test-only cells set in the built tables for one run each, the clean build
reinstalled after). Life lost per ~5 s sample, Tank character, seen with the harness:

| run | monster | cells | lost per sample (median / max) | live server missiles (median) |
|---|---|---|---|---|
| `checks-20261029-070021-s4` | 10 Heretics | Median's (skull Param1 1, impact NextDelay 4, SrcDamage 96) | 34,888 / 36,653 | 841 |
| `checks-20261029-064912-s4` | 10 Heretics | our build (Param1 2, NextDelay 2, SrcDamage 96) | 35,206 / 42,130 | 419 |
| `checks-20261029-065152-s4` | 10 Heretics | our build, impact SrcDamage 192 | 72,683 / 84,145 | 433 |
| `checks-20261029-065440-s4` | 10 Fire Beetles (`firebeetle`, MissA1 `firebeetle`) | Median's SrcDamage 255 | 12,211 / 13,091 | 13 |
| `checks-20261029-065708-s4` | 10 Fire Beetles | SrcDamage 128 | 5,694 / 6,489 | 11 |

SrcDamage 192 / 96 gives 2.06x and 255 / 128 gives 2.1x the damage: linear, read unsigned (255 is 199%, not -1). The #395
fix deals the same damage as Median's values with half the missiles. Ten Heretics take about 35,000 life per 5 s from this
character either way, so the 30,000-life character of the first try would also have died within 5 s on Median's values. The slot-2
"before" run logged D2R's pool asserts at game exit (`m_freed == 0`, `s_StatsPool.IsEmpty()`, ~800 missiles live at
the close); the other three runs none.

## Lane tints2: stand-in colours (2026-10-29, slot 4, background mode)

Check `hm2_monsters` (lane hdmon2) with `MXL_HM2_ONLY`; a **graphics check, seen with the harness** (spawn, `god 1`, Tank), not
the player path. Run folders are kept outside the repo.

| run | result |
|---|---|
| hdmon2's `checks-20261029-043155-s3`, looked at again | the "green" figure in the corpseworm / cultist1 shots is the player (poison cloud of the orkshaman spawned before), the "blue" is hit sparkles on the player; the stand-ins are not blue or green |
| `checks-20261029-052910-s4` (calibration, test-only build: one colour value per stand-in, sharing off) | 8 spawned, 0 asserts. councilmember1 with hue 0.98, sat +0.12 or val +0.25 alone: natural; zombie1 hue 0.33: green, 0.5: cyan; doomknight2 identity: olive / bronze; maggotbaby1 identity: bright orange stripes. `colorAdjustment.x` is a hue turn that wraps. A clean build was not reinstalled after it: the slot's mods\mxl2012 holds the calibration build until the next install |
| fixed build (`a7b1e48`) | **PENDING**: no slot free for 40 minutes; offline evidence: classic NU renders beside the hdmon2 HD crops (scratch, `mxl2012-runs/tints2/side_by_side_before.png`, `weak_weight_classic.png`) |

## Lane colourcode (2026-10-29): colour codes in skill descriptions, skilldesc type 52 (bugs.md #398)

Check `stip_tooltips` (lane skilltips) on slot 1, necromancer, fresh level-1 Normal character, mortal; hovering the skill tree
is the player path. `MXL_STIP_LIMIT=15` shoots every skill of a tab (Widowmaker's skilldesc is tree page 2, cell 14). Run folders:
`mxl2012-runs/colourcode/checks-*-s1` (report.md and game logs in each).

| run | build | result |
|---|---|---|
| `checks-20261029-052850-s1` | `ÿc/` -> `ÿc0` | HD tree 18, classic tree 18, HD popup 1 tooltips; 0 asserts, 0 crash files |
| `checks-20261029-053518-s1` | the same, `MXL_STIP_LIMIT=15` | HD tree 30, classic tree 30, HD popup 2 tooltips; 0 asserts, 0 crash files |

Read by hand (**verified in game**): `stip_nec_hd_tree_tab1_0.png` / `stip_nec_legacy_tree_tab1_0.png` (Summon Shadows, Median's
`ÿc/summon multiple shadow minions with an aura of blood`): the line reads "summon multiple shadow minions with an aura of blood"
in white, no "*/" (HD) or "Ø/" (classic). `stip_nec_hd_tree_tab2_14.png` / `stip_nec_legacy_tree_tab2_14.png` (Voodoo Shot,
skilldesc `widowmaker`): the type-52 line reads "Crossbow Base Damage: +2-5" in both modes, as 1.14d builds it (no change needed).
The same shots showed the second fault: "targets a minion, unleashing a barrage of homing bolts around it" stayed red after
`ÿc1requires a crossbowÿc0` + line break (D2R drops a code that ends a line). The fix (codes moved behind the line break,
commit "Colour codes that end a line ...") is unit-tested and in the build (audit 0 findings) but **not seen in game yet**: all
four slots were taken for 35 minutes. Only the four shots named here were read one by one.

## Lane hdlook2: fire bolt tint fix and the rest of hdlook's items (2026-10-29, slot 4, background mode, build of lane/hdlook2)

Fix of bug #403 (docs/hd-effects.md 5a, `TINT_OVERRIDES`), then the committed check `hdl_look` with the same set-up as lane
hdlook (named there). Check change: Dark Power moved to a Necromancer (HdlNec): Blackheart is a wand and Median's wands are
Necromancer-only (`itemtypes.txt` Class `nec`), so the Paladin's `equip` was refused (unit test `test_oskill_item_fits_its_class`).

Run 1 `checks-20261029-070319-s4`: `MXL_RUN=hdlook2 MXL_SLOT=4 MXL_CHAR=HdlPal MXL_CHAR_CLASS=paladin MXL_HDL=fx,ui,items,mons,walls
MXL_HDL_CLASSES=paladin,assassin py -3 tools/game_checks.py all hdl_look`. Run 2 `checks-20261029-073523-s4`: the same with
`MXL_CHAR=HdlNec MXL_CHAR_CLASS=necromancer MXL_HDL=fx MXL_HDL_CLASSES=necromancer`. 0 crash files; engine asserts: `wPrefix != 0 ||
wSuffix != 0` once (bug #432), `activeUnit` at the game's close (#190), the pool asserts of the close. Screenshots kept outside the
repo (`mxl2012-runs/hdlook2`).

| Item | Result | Path | Evidence |
|---|---|---|---|
| Fireball Sentry (Assassin 339, the fire bolt effect, now `mxl_ice_blast_c913a3d`) | **PASS** (bug #403 fixed): orange fire bolt heads in HD as in classic; a faint grey-white sparkle trail is left (baked colours) | player cast (set-up as lane hdlook) | `hdl_fx_ass_339_hd_5..7.png` / `_legacy_5..7.png`; before / after / classic crop `firebolt_before_after_classic.png` |
| Dark Power (Blackheart's oskill 669, `darkpowernova` x128 per mode) | **FAIL** (bug #404): pale indigo-blue nova ring in HD, vivid violet in classic | player cast, Necromancer wearing Blackheart (`equip`, set-up) | `hdl_fx_nec_669_hd_0.png`, `_hd_4.png` / `_legacy_0.png`, `_legacy_4.png` |
| Vampiric Icon (Assassin 614, `vampflame` x96 per mode) | PASS: purple fire ring in both | player cast | `hdl_fx_ass_614_hd_2.png`, `_hd_6.png` / `_legacy_2.png`, `_legacy_6.png` |
| Ring of Light, Holy Trap Advanced (Paladin 509, 510) | cast again: 128 / 138 tinted missiles per mode; shots not judged again (PASS in lane hdlook) | player cast | `hdl_fx_pal_509_*`, `hdl_fx_pal_510_*` |
| Skill tree pages and level boxes, Paladin, HD and classic | PASS: each tab opens its page (HD Special / Neutral, Shadows / Wicked, Light / Honor; classic Median's column of labels), every skill has its level box, learned skills show 1 / 20 in both (the HD font draws zero as Ø) | player (T key, tab clicks) | `hdl_tree_pal_hd_0.png`, `_hd_tab0..2.png`, `hdl_tree_pal_legacy_0.png`, `_legacy_tab0..2.png` |
| Quill Rats 1-5 (`quillbear1-5`) | **FAIL** (bug #431): not drawn in HD at all; classic draws all five with their colour levels | harness spawns (5 of 5 spawned) | `hdl_mon_quill_hd_0..2.png` / `_legacy_0..2.png` |
| Wisps 1-4 (`willowisp1-4`) | PASS: white, green, red, blue in both | harness spawns | `hdl_mon_wisp_hd_1.png` / `_legacy_0..2.png` |
| Inventory with Median items | PASS: the ten items in the same cells and colours, HD pictures crisp | `item` (set-up), I key | `hdl_inv_hd.png` / `hdl_inv_legacy.png` |
| Horadric Cube panel (HD) | PASS: Median's cube grid opens by a right click on the cube | player | `hdl_cube_hd.png` |
| Vendor windows (Charsi, Akara: talk, Trade, tabs) | PASS: same goods in HD and classic, HD pictures crisp (weapons, potions, scrolls, keys); Akara's HD tab 2 shot is of the closed window (check timing) | player (NPC dialog) | `hdl_shop_charsi_hd_0.png`, `_hd_1.png`, `hdl_shop_charsi_legacy_0.png`, `hdl_shop_akara_hd_0.png`, `_hd_2.png`, `hdl_shop_akara_legacy_0.png` (the other tab shots not looked at) |
| Stash | partial: HD opened by a click (empty stash, so no item picture to judge); classic not opened by the walk | player | `hdl_stash_hd.png`, `hdl_stash_legacy.png` |
| Walls of downtown (Crypt 1 A) and glados (Disused Fane) | PASS on the arrival shots: walls drawn in HD, the same layout as classic (brick walls and stone piers; arched stone walls). The Paladin died at once in both maps (Citizen, AC-2 Rivet Bot), so the walk shots are under the death screen | waypoint panel + entrance warp (set-up) | `hdl_wall_downtown_hd_0.png` / `_legacy_0.png`, `hdl_wall_glados_hd_0..1.png` / `_legacy_0..1.png` |

## Lane hdmon3: Act 3-5 Normal HD stand-ins (2026-10-29, build of lane/hdmon3)

Check `hm3_monsters` (`MXL_RUN=<run> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all hm3_monsters`; optional
`MXL_HM3_ONLY=<id,...>`): as `hm2_monsters`, the 11 Ids of `HM3_MONSTERS` (the ten re-picked tokens of docs/hd-monsters.md
section 11, the Shardspawn's new A2 state, the Couatl father's cast) spawned in the Blood Moor by `*hcIdx` beside a tanked
player in HD with `god 1`, shots near / fight / death. A **graphics check, seen with the harness**, not the player path.

| run | result |
|---|---|
| in game | **PENDING**: no game slot free during 45 minutes of polling (all four held by other lanes) |
| offline | classic NU frame beside the donor's classic NU frame at our scale for all 47 Act 3-5 tokens and for the ten candidates (scratch, `mxl2012-runs/hdmon3/sheet_before.png`, `cand1.png`); unit tests `test_hd_clip_fill` (state fill on the committed donors, check lists match the mapping); full build 0 validate errors, 30 colour tables |

To judge in game: each stand-in draws as a full HD model, walks up, attacks and dies; the Shardspawn animates its second
attack (attack2) instead of freezing; colours judged on the monster alone (lane tints2: player poison / lightning effects are
not tints).

## Vendors, lane vendors3 (2026-10-29, slot 3, background mode, build of lane/vendors3 with main's plugin)

Check `ven_vendors` (new). It visits every town vendor of acts 1, 2, 3 and 5 on the player path:

- **Travel:** the town by the waypoint panel (`rp_waypoint_to`).
- **Route:** left clicks on the ground, one 9-unit leg at a time in one of 16 directions. The check keeps a map of the legs the
  clicks really walked and backtracks along it to the most promising untried leg (`ven_click_route`). That gets round the
  walls where the server's path stopped in round 2 (Drognan, Larzuk). An NPC that is not loaded yet (Akara) is found by
  clicking legs round the arrival first.
- **Talk and trade:** a click on the NPC, then Trade. One item is bought by right click and sold back (lifted, dropped on the
  panel); one item is gambled where the menu offers Gamble.
- **Repair (smiths):** Repair All on a worn Circlet (below).

`MXL_VEN_TOWNS` and `MXL_VEN_NPCS` pick a part. `MXL_VEN_HRATLI_PIER=1` clears the Act 3 intro word by save (bug #434). `MXL_VEN_HRATLI_HOUSE=1` sets it done (a new character: Hratli at his
house, reached the long way round, lane bugsweep).
`MXL_VEN_WEAR=click` (lane durability, bug #433) wears the Circlet by clicks (dropped by `item ... ground`, picked up, lifted onto
the head slot) instead of the harness `equip`, and takes a tooltip screenshot of it back in town (`ven_wear_tooltip_<town>.png`).

SET-UP: Barbarian VenBarab (level 120 and gold by harness), made for this lane. Quest words 7, 15, 23, 26 and 28 (the acts),
and 37 (Prison of Ice: Anya in town), are set by save (`rp_open_acts`, `rc2_closed_edit`). The town waypoint bits are set by
harness. For the repair, the Circlet `k21` (durability 10) is the only armour and is worn down by natural hits from 12
harness-spawned Zombies in the town's first area until it reads 8 of 10. Then a harness warp back to town. The judged
actions (route, talk, trade, buy, sell, gamble, repair) are clicks.

| Town | Vendor | Path (clicks) | Buy | Sell back | Gamble | Repair | Run (work/runs/) |
|---|---|---|---|---|---|---|---|
| Rogue Encampment | Charsi | click route, 3 | PASS (`124`, 102) | PASS (12) | - | PASS after lift and re-wear (880; first try refused, #433) | checks-20261029-054559-s3 |
| Rogue Encampment | Akara | click route, 11 (with the look-round legs) | PASS (`129`, 102) | PASS (12) | - | - | checks-20261029-063835-s3 |
| Rogue Encampment | Gheed | click route, 7 | PASS (`124`, 102) | PASS (12) | PASS (`rin`, 5000) | - | checks-20261029-054559-s3 |
| Lut Gholein | Drognan | click route, 17 | PASS (`154`, 363) | PASS (45) | - | - | checks-20261029-054559-s3 |
| Lut Gholein | Fara | click route, 13 | PASS (`115`, 150) | PASS (18) | - | PASS after lift and re-wear (685; #433) | checks-20261029-054559-s3 |
| Lut Gholein | Elzix | click route, 8 | PASS (`115`, 704) | PASS (88) | PASS (`rin`, 5000) | - | checks-20261029-054559-s3 |
| Lut Gholein | Lysander | click route, 9 and 15 | PASS (`key`, 315 / 360) | PASS (35 / 40) | - | - | checks-20261029-054559-s3, 061635-s3 |
| Kurast Docks | Ormus | click route, 14 | PASS (`150`, 2600) | PASS (260) | - | - | checks-20261029-061635-s3 |
| Kurast Docks | Alkor | click route, 51 | PASS (`01+`, 1000) | PASS (125) | PASS (`rin`, 5000) | - | checks-20261029-061635-s3 |
| Kurast Docks | Asheara | click route, 69 and 41 | PASS (`121`, 1023 / 1919) | PASS (127 / 239) | - | - | checks-20261029-054559-s3, 061635-s3 |
| Kurast Docks | Hratli | standing next to him on the pier (intro word cleared) | PASS (`j24`, 1743) | PASS (54) | - | **FAIL**: after the talk he goes to his house, which no route reaches (#434) | checks-20261029-074527-s3; house: 063835-s3, 071756-s3 |
| Harrogath | Larzuk | click route, 11 | PASS (`128`, 2694) | PASS (505) | - | PASS after lift and re-wear (919; #433) | checks-20261029-054559-s3 |
| Harrogath | Malah | click route, 5 | PASS (`150`, 3640) | PASS (650) | - | - | checks-20261029-054559-s3 |
| Harrogath | Anya (after Prison of Ice) | click route, 24 | PASS (`j25`, 1158) | PASS (54) | PASS (`rin`, 5000) | - | checks-20261029-054559-s3 |

Findings:

- **Lysander's key (round 2 FAIL):** bought and sold back in both runs. Median's key is 45 gold, stackable to 50 and sold in
  6-9; `npc.txt` gives Lysander buy 128 / sell 1024. Nothing points to a data or port fault. The round 2 failure was the
  check's lift click. The sell-back failure message now names the quantity and the item the lift took, in case it comes back.
- **Repair (bug #433):** the durability loss from the fight is not sent to the client. Repair All reads 0 and is refused
  until the item is lifted and worn again. Then the repair itself works at Charsi, Fara and Larzuk.
  (`equip ... 72=` as a set-up does not work: it adds a minus to the item's magic list, and the server refuses that repair.)
- **Hratli (bug #434):** his house spot after the Act 3 intro is off the walkable Docks. Repair at Hratli is not verified.
- **Akara:** the Rogue Encampment has no preset for her, and she is out of `state`'s view at the arrival. A few look-round
  clicks load her room.
- Engine: one `BC_ASSERT: activeUnit` box in run 054559 (known, #190); no crash.

Not done / open: Repair at Hratli (#434); the vanilla D2R comparison for #433 and #434; act 4 has no vendor besides Jamella
and Halbu, already covered in round 2.

## Lane hdlook3: Dark Power violet (#404), Quill Bears drawn (#431), hdfx2's picks in game (2026-10-29, slot 1, background mode, build of lane/hdlook3)

Check `hdl_look` as in lanes hdlook / hdlook2 (set-up named there), with three changes: stage `picks` (the skills that draw
lane hdfx2's hand-picked stand-ins, `HDL_PICKS`, new characters HdlSor / HdlBar made as the others; then four Skeletons
`skeleton1` spawned next to the player so their Nightmare curse, overlay `cursenightmare`, can land on it), the walls stage's
SET-UP (life and max life 200,000 by `setstat` and every monster near the player killed by the harness after the warp and
before each shot: the maps' hordes killed a 200,000-life Paladin in seconds), and the items stage puts a backpack item into
the stash by two left clicks (pick up, put down) before the HD stash shot (a Median gem is made in the backpack first when
there is no item). Runs: A `checks-20261029-090829-s1` and C1 `checks-20261029-092851-s1` (`MXL_CHAR=HdlNec
MXL_CHAR_CLASS=necromancer MXL_HDL=fx MXL_HDL_CLASSES=necromancer`; A with a first violet ramp, C1 with the committed one), B
`checks-20261029-091110-s1` (`MXL_CHAR=HdlPal MXL_CHAR_CLASS=paladin MXL_HDL=mons,items,walls`, walls with the life set-up only),
C2 `checks-20261029-093043-s1` (`MXL_HDL=picks`), D `checks-20261029-094357-s1` (`MXL_HDL=walls,items`, with the clearing). All
`MXL_RUN=hdlook3 MXL_SLOT=1 ... py -3 tools/game_checks.py all hdl_look`. 0 crash files; engine asserts: `activeUnit`
(InventoryItemWidget.cpp:378) once in B and D (both with the items stage: bug #190's harness travel with an item widget
active), none in A, C1, C2. Screenshots are kept outside the repo (`mxl2012-runs/hdlook3`, contact sheets there).

| Item | Result | Path | Evidence |
|---|---|---|---|
| Dark Power (Blackheart's oskill 669, `darkpowernova` x128 per mode), bug #404 | **PASS** (fixed): violet-purple nova ring in HD, close to classic's violet (the first ramp of run A drew blue-violet; moved toward magenta) | player cast (set-up as lane hdlook2) | C1 `hdl_fx_nec_669_hd_0.png`, `_hd_4.png` / `_legacy_0.png`, `_legacy_4.png`; run A `hdl_fx_nec_669_hd_0.png`, `_hd_1.png`, `_hd_4.png` |
| Quill Bears 1-5 (`quillbear1-5`), bug #431 | **PASS for drawing** (fixed): the five quilled stand-ins (Quill Rat x1.4) are drawn in HD; all in the Quill Rat's brown while classic draws purple / black / teal levels (bug #435) | harness spawns (5 of 5) | B `hdl_mon_quill_hd_0.png`, `_hd_2.png` / `_legacy_0.png`, `_legacy_2.png` |
| Judgement (Paladin 518, `zomgpewpewmallet`, pick `lightandshadowstrike` -> lightning_strike) | **FAIL** (bug #481): a blue-white bolt hangs below the target (its top at the target's feet, about 300 px down-screen); no bolt in the classic shots (`zomgpewpewmallet` 47 in HD, 0 in classic), only small gold sparks at the target | player cast | C2 `hdl_fx_pal_518_hd_1.png`, `_hd_5.png`, `_hd_7.png` / `_legacy_0..7.png` |
| Hammerstrike (Paladin 499, `hammerstrikenova` x128, pick `extra/cursehit` -> teethexplode) | PASS: small orange star sparks around the target in HD; classic a white star flash with red sparks. A blue bolt as Judgement's also shows below the target in HD | player cast | C2 `hdl_fx_pal_499_hd_0.png`, `_hd_4.png` / `_legacy_0.png`, `_legacy_4.png` |
| Lorenado (Sorceress 539, `lorenado` x2, `lorenadobookflip` x80; picks `lorenado` -> expansion_tornado, `flipbook` -> expansion_hurricane_rocks) | **FAIL** (bug #482): HD a small grey-brown tornado and nothing else; classic a green tornado in a wide cloud of green orbs and sparkles (the 80 `lorenadobookflip`: the `flipbook` art is green orbs, the low-confidence pick draws next to nothing) | player cast | C2 `hdl_fx_sor_539_hd_0.png`, `_hd_4.png` / `_legacy_1.png`, `_legacy_4.png` |
| Firedance (Sorceress 527, `firedancecenter` x2, pick `bonfire` -> ground_fire_small) | PASS: a burning pile at the caster in both | player cast | C2 `hdl_fx_sor_527_hd_0.png`, `_hd_4.png` / `_legacy_4.png` |
| Miasma (Sorceress 540; pick `gore20` -> sand_maggot_dirt_pile, overlay `poisondark` -> common/poisonhit) | partial: the target glows green in HD (the overlay); `newhexgraphical` (the `gore20` row) was made in neither mode, so `gore20` not seen; the classic shots are covered by the clouds of the casts before | player cast | C2 `hdl_fx_sor_540_hd_0.png`, `_hd_4.png` / `_legacy_*` |
| Swarm (Sorceress 542, `swarm emitted`, pick `swarmhovers` -> poison_sparks) | PASS: green hovering clouds over an area in HD, green blobs in classic (`swarm emitted` counted 0 in HD, 11 in classic: the HD clouds are in the shots anyway) | player cast | C2 `hdl_fx_sor_542_hd_4..7.png` / `_legacy_0..3.png` |
| Bear Claw (Barbarian 443, `bearbolt`, pick `extra/cursemissle` -> firebolt) | not seen: the skill was picked but made no `bearbolt` in either mode (no missile in the shots) | player cast | C2 `hdl_fx_bar_443_*` |
| Magic Missiles' cast flash (Amazon 314, overlay `mooncast` -> necro/cast_familiar) | not told apart: the missiles' own burst covers the caster. The missiles (`magicmissile`, art TeethExplode, D2R's own effect) draw white-blue in HD, red-orange in classic (not a hand pick; not filed) | player cast | C2 `hdl_fx_ama_314_hd_0.png`, `_hd_4.png` / `_legacy_0.png` |
| Nightmare curse (overlay `cursenightmare`, pick `expansion/steamthick_a` -> common/ice_explode) | not seen: the four `skeleton1` are red-robed casters throwing fire bursts in both modes; no cloud that can be told to be the curse on the player | harness spawns | C2 `hdl_pick_nightmare_hd_0..7.png` / `_legacy_0..7.png` |
| Walls of downtown (Crypt 1 A) and glados (Disused Fane), walk shots | **PASS**: with the clearing the character is alive in every shot; HD brick walls and stone piers, the long arched wall of the Fane, the same layout in classic | waypoint panel + entrance warp (set-up), left-click walks | D `hdl_wall_downtown_hd_1.png`, `_hd_2.png`, `hdl_wall_glados_hd_1.png`, `_hd_2.png`, `hdl_wall_downtown_legacy_2.png`, `hdl_wall_glados_legacy_2.png`; B (life set-up only: still killed in glados) `hdl_wall_glados_hd_1.png`, `_legacy_2.png` |
| Stash with an item | HD **PASS**: the stash opened by a click, a Minor Healing Potion (the first backpack item) put in by two clicks, drawn crisp in the grid. Classic: a left panel with tabs Armor / Weapons / Misc and "Stash 0" opens, its grid is empty and the check's panel test says NOT OPENED (open question) | player (walk, clicks) | B and D `hdl_stash_hd.png` / `hdl_stash_legacy.png` |

Only the shots named in this table were looked at (as contact sheets of 8 HD + 8 classic shots per skill, and full-size crops of
`hdl_fx_pal_518_hd_5.png`, `hdl_fx_ama_314_hd_0.png`, `_hd_4.png`, `_legacy_0.png`). Harness spawns (Quill Bears, Skeletons) are
"seen with the harness".

## Lane hdmonlook: in-game look of the Act 1-5 HD stand-ins (2026-10-29, slots 3 and 1, background mode, build of lane/hdmonlook)

Checks `hm2_monsters` and `hm3_monsters` (`MXL_RUN=hdmonlook MXL_SLOT=N MXL_CHAR=hdmonlook [MXL_HM_GRAPHICS=legacy]
[MXL_HM2_ONLY / MXL_HM3_ONLY=<ids>] py -3 tools/game_checks.py all hm2_monsters`), every Id spawned in HD and again in classic
graphics (the reference look), `god 1` and Tank: a **graphics check, seen with the harness**, not the player path. From round 2
the monster is spawned 8 subtiles to the side with a `far` shot first (`hm2_<id>_far|near|fight|death.png`, classic
`hm2_legacy_<id>_*.png`). Judged by hand per token: silhouette, size, colour, animation playing, drawn at all; colours on the
monster alone (the player's own poison cloud, lightning sparkles and the blue / green tint some casts put on him are not the
monster's). Run folders `work/runs/` of the lane worktree (kept outside git).

| run | what | result |
|---|---|---|
| `checks-20261029-082921-s3` / `-083609-s3` | round 1, hm2 HD / classic | PARTIAL by design, all 13 spawned, 0 asserts; monsters mostly hidden behind the player (hence round 2's side spawn) |
| `checks-20261029-083250-s3` / `-083915-s3` | round 1, hm3 HD / classic | **FAIL**: one engine assert `BC_ASSERT: result` (animation_event_handler.cpp:608) per run, in HD and classic; bisected by `MXL_HM3_ONLY` (`-084552`..`-084928-s3`) to `brainpower` alone (on wraith1) |
| `checks-20261029-091506-s3` / `-091809-s3` | round 2, hm2 HD / classic (side spawn, far shot) | PARTIAL, 13 spawned, 0 asserts |
| `checks-20261029-092119-s3` / `-092401-s3` | round 2, hm3 HD / classic, `!s` on bloodlord1 | PARTIAL, 12 spawned, **0 asserts** |
| `checks-20261029-100625-s1`, `-100842-s1`, `-101023-s1` | round 3, the re-picked / recoloured subset (HD; Harlequin and Priest also classic) | PARTIAL, 0 asserts |
| `checks-20261029-102102-s1`, `-102204-s1` | round 4, troll1 x0.7 and harlequin2's colour | PARTIAL, 0 asserts |

Every token drew a full HD model (none invisible, none a classic sprite) and walked, attacked and died, except where noted.
Final verdict (after this lane's fixes, docs/hd-monsters.md section 12); "fixed" = FAIL before, PASS seen after.

| Act | Token | Id (stand-in) | Shots looked at | Verdict |
|---|---|---|---|---|
| 1 | `#w` | robedagger (councilmember1) | `hm2_robedagger_near/fight` r1, r2 | PASS: brown hooded robe, player-sized |
| 1 | `c@` | cloakdagger (councilmember1) | `hm2_cloakdagger_near/fight` r1, r2 | PASS: tan robed figure (twin of `#w`) |
| 1 | `#y` | zombierags (zombie1) | `hm2_zombierags_near/fight` r1 (green), r2 | **fixed** (hand colour): was bright green, now pale grey-white like the art |
| 1 | `@c` | greenzombie (zombie1) | `hm2_greenzombie_*` r1, r2 | PASS (partly hidden): dark brown zombie |
| 1 | `@3` | orkshaman (fallenshaman1) | `hm2_orkshaman_*` r2, `_far/near` r3 | **fixed** (scale 1.6, hand colour): was a small red imp at half the art's height |
| 1-3 | `(1` | hell_dragonknight (doomknight2) | `hm2_hell_dragonknight_*` r1, r2 | PASS: dark blue-teal armoured knight (no wings: the art's bat wings have no D2R part) |
| 1 | `0k` | corpseworm (maggotbaby1) | `hm2_corpseworm_*` r1, r2 | PASS: pale cream segmented larva |
| 1-5 | `!5` | cultist1 (councilmember1, SC fill) | `hm2_cultist1_far/near` r2 | PASS: red-robed caster, keeps range and casts |
| 1-2 | `#0` | troll1 (irongolem -> thornhulk1) | `hm2_troll1_*` r1, r2 (silver golem), r3 (too big), `hm2_troll1_far/near` r4 | **fixed** (re-pick, x0.7): olive-yellow hunched brute of the player's height |
| 2 | `&b` | deathwing1 (vulture1) | `hm2_deathwing1_*` r1, r2, r3 | **FAIL, fix not seen**: dark brown vulture against the pale bone-white art; hand colour set, but in r3 it stayed behind the Rocky Waste ruin |
| 2-3 | `9!` | centaur1 (clawviper1) | `hm2_centaur1_*` r1, r2, `_far/near` r3 | colour **fixed** (pale white-grey now); shape **FAIL** (known, section 9: a serpent for a horse-bodied centaur; D2R has no centaur) |
| 2 | `ji` | dead3 (sandraider1) | `hm2_dead3_*` r1, r2 | PASS: orange-skinned turbaned fighter |
| 1-5 | `@6` | firewizard1 (firegolem) | `hm2_firewizard1_*` r1 | PASS: humanoid of flame |
| 3 | `!4` | couatlfather1 (clawviper1, SC fill) | `hm3_couatlfather1_far` r2 (and `hm3_legacy_..._far`) | **fixed** (hand colour): was tan-brown, now teal-green; casts (fire walls) |
| 5 | `#m` | belial (baalminion1) | `hm3_belial_far/near` r2, r3 | **FAIL colour**: bright green in HD, art dark grey-brown; not the table (bug #436). Its attack rats are not drawn in HD (likely #431, lane hdlook3) |
| 3 | `&g` | combatdrone1 (irongolem) | `hm3_combatdrone1_*` r1 | PASS: bulky metal walker |
| 3 | `#l` | combatdrone2 (irongolem) | `hm3_combatdrone2_*` r1 | PASS: the slimmer twin, metal |
| 3 | `#q` | cube1 (arach1) | `hm3_cube1_far` r2, r3 | **FAIL colour**: legged shape fits, but a dull red-brown spider against a golden box on legs; a hand colour did not help (dropped) |
| 3 | `$f` | rathma_primus (vampire1) | `hm3_rathma_primus_far` r2, r3 | **FAIL colour**: dark green-grey robed figure against a pale bare-skinned winged man; a hand value +0.9 made it an almost invisible dark column (dropped) |
| 3-5 | `%9` | mahasattva (clawviper1) | `hm3_mahasattva_far` r2 | PASS: tall orange-tan serpent body; summons its fire beetles (`(i`, reddish scarabs) |
| 5 | `(0` | dragonknight3 (doomknight2) | `hm3_dragonknight3_near/fight` r2 | PASS: dark horned armoured knight (no wings) |
| 5 | `!s` | brainpower (wraith1 -> bloodlord1) | round 1 assert; `hm3_brainpower_far` r2 | **fixed** (re-pick): no engine assert; purple winged clawed demon like the art |
| 4 | `2!` | harlequin2 (sandraider1) | `hm3_harlequin2_far/near` r3 (orange-tan), r4 | **fixed** (hand colour): green armoured fighter with blades |
| 5 | `ie` | shardspawn (frozenhorror1, A2 state fill) | `hm3_shardspawn_near/fight` r2 | PASS: pale blue crystal brute, its attacks (A2 included) animate |
| 4 | `1!` | l_priest (sandraider1, new) | `hm3_l_priest_near/fight` r2, `hm3_legacy_l_priest_far` r3 | PASS: orange-tan armoured fighter, fits the brown-orange art |

Counts (25 tokens): Act 1-2 (hm2, 13): 11 PASS (3 of them fixed here), 2 FAIL (`&b` colour fix unseen, `9!` shape). Act 3-5 (hm3,
12): 9 PASS (3 fixed here), 3 FAIL on colour (`#m`, `#q`, `$f`). No token was invisible in HD; `brainpower`'s engine assert is
gone.

## Mana costs, lane manacost (2026-10-29, slot 1, background mode, build of lane/manacost with main's plugin of 00:05)

Question (lane acts3): a level-80 Sorceress kept 2,187 mana while casting Frigid Sphere / Tempest. Data: the `usemanaondo`,
`startmana`, `minmana`, `manashift`, `mana`, `lvlmana` columns of all 1,038 skills rows are equal in Median's skills.txt, in its
compiled skills.bin (what 1.13c ran: offsets 388-396 of the 572-byte record) and in both built banks (Warlock-renamed rows
matched by their `_mxl` name). D2R reads the same columns by the same formula: Fire Wall (176 << 6) >> 8 = 44 in the tooltip.
1.13c cost = max((mana + (slvl - 1) x lvlmana) << manashift, minmana << 8) / 256 (`game_checks.skill_mana_cost`). Median's own
`*Manaat30` comment equals it on 867 rows; the 73 others are stale notes (e.g. Fortress 40, the formula and the game: 60).
acts3's logs: the ring `rin 27=300` (+300 % `manarecoverybonus`) and Median's 20-second ManaRegen refill 2,187 in about
140 frames (run9: 1826 -> 1935 -> 2044 in 7-frame steps), so a 96-point Frigid Sphere was gone before the next look.

Check `su_mana` (`tools/game_checks.py`), run folder `work/runs/checks-20261029-105400-s1`, with
`MXL_SM_SKILLS=530:1,530:10,530:20,535:10`. Set-up by the harness (help): the sweep's level-120 sorceress, Blood Moor, zombies with
raised life, skills by `setskill`, mana 200 max and current before each click. Judged: 3 real background right clicks per skill on
the zombie; the `state` frame counter brackets the cost (the drop seen <= cost <= drop + regeneration since the click).

| Skill (level) | 1.13c cost | Spent (3 clicks) | Result |
|---|---|---|---|
| Frigid Sphere (1) | 18 | 14-32, 14-30, 13-29 | VERIFIED |
| Frigid Sphere (10) | 72 | 68-86, 67-87, 67-85 | VERIFIED |
| Frigid Sphere (20) | 132 | 127-145, 127-143, 127-145 | VERIFIED |
| Tempest (10) | 65 | 60-80, 60-78, 60-78 | VERIFIED |
| regeneration, 200 pool, no bonus | 0.4 a frame (charstats ManaRegen 20) | 3 points per 7-8 frames | seen |

Earlier runs of the lane (`checks-20261029-104620-s4`, `-104945-s4`) used su_use's looks (0.18 s + the console round trip): the
first look came ~16 points of regeneration after the charge, so the drops (2 / 56 / 108 / 46) were below the cost; hence the frame bracket.


## Lane picktint: tinted hand picks, Judgement (#481), Lorenado (#482), Magic Missiles (#483), Quill Bear levels (#435) (2026-10-29, slot 4, background mode, build of lane/picktint)

Check `hdl_look` as in lane hdlook3. Runs on slot 4 (locked for the install and run only, unlocked after each):

| Run | Set-up | Result |
|---|---|---|
| `checks-20261029-105321-s4` | `MXL_CHAR=HdlPal MXL_CHAR_CLASS=paladin MXL_HDL=picks,mons MXL_HDL_CLASSES=amazon,paladin,sorceress` | PARTIAL (pictures judged by hand); 0 crash files; 16 ERROR/ASSERT lines at exit (object pool asserts as in earlier lanes) |
| `checks-20261029-111438-s4` | `MXL_HDL=picks MXL_HDL_CLASSES=paladin`, gold ramp with the core gradients | PARTIAL; 0 crash files, 0 ERROR/ASSERT lines; bolt still white |
| `checks-20261029-112153-s4` | same, saturated gold top stop (committed) | PARTIAL; 0 crash files; 20 ERROR/ASSERT lines at exit (the same pool asserts, `s_StatsPool.IsEmpty()`) |

Rows seen (HD / classic): `zomgpewpewmallet` 45 / 54 (44 / 56 in the last run), `magicmissile` 30, `teethexplodered` 0 (no
caster in the stage), `lorenado` 2, `lorenadobookflip` 80; Quill Bears 5/5 and wisps 4/4 spawned in both modes.

Shots judged:

- Judgement: `hdl_fx_pal_518_hd_1/3/5/7` against `_legacy_1/3/5/7` (first run): white bolt, drawn down-screen of the target.
  Classic `_legacy_7` shows the missile's red light on the same spot as `_hd_5/7`, so the position is the missile's own.
  Last run `_hd_4/5/6/7`: gold glow on the ground, white core (see docs/hd-effects.md section 9a).
- Lorenado: `hdl_fx_sor_539_hd_1/3/5/7` against `_legacy_1/3/5/7`: green tornado and a cloud of green orbs (`_hd_1`, `_hd_5`;
  `_hd_3`, `_hd_7` between casts), classic a wider green cloud.
- Magic Missiles: `hdl_fx_ama_314_hd_1/3/5/7` against `_legacy_1/3/5/7`: red-orange missiles in HD (`_hd_1`, `_hd_5`), red with a
  white core in classic.
- Quill Bears: `hdl_mon_quill_hd_0` against `_legacy_0`: five bears in purple, green, tan, dark and lilac in HD (before: all
  brown); the classic shot is washed green by the poison clouds, so its level colours are not readable there.

## Lane dursync: a worn item's durability loss on the client (bug #433, 2026-10-29, slot 3, background mode, build of lane/dursync)

Check `ven_vendors` with `MXL_VEN_WEAR=click MXL_VEN_TOWNS=1 MXL_VEN_NPCS=Charsi`: the character wears the Circlet, fights
zombies by real clicks until a point of durability is lost, then hovers the item (tooltip shot) and uses Charsi's Repair All.
New in this lane: after the fight the check logs the server's and the client's durability (`istat` / new verb `cistat`, and
`cistat <id> 72 scan` for every layer), and with `MXL_VEN_DURWATCH=1` (default) the new verb `durwatch` counts the packets 0x3e
the server sends, the entries to the client's handler and the raw 8-byte layer slot. `MXL_VEN_WEAR_WEAPON=1` also tracks the
right-hand weapon. The attack clicks now stay within 6 of the player inside the safe screen area, return to the area after a
stray click into a cave, and spawn more zombies when none come near.

| Run | Build | Result |
|---|---|---|
| `checks-20261029-111034-s3` | `dursync` off, no watch | bug seen: server 9, client 10, Repair All refused; after lifting and wearing again it repaired for 372 |
| `checks-20261029-111824-s3` | `dursync` off, watch passes the raw slot on | bug seen: server 8, client 10 (only layer 0 = 10), layer slot `0x140380000`, refused, 893 after re-wear |
| `checks-20261029-110633-s3` | `dursync` off, first watch (re-stored a clean 16-bit layer) | in sync 8/8, repaired at once: the clean slot alone makes the update land |
| `checks-20261029-112522-s3` | `dursync` (5-byte patch) | **PASS**: layer slot `0x0`, server 8 / client 8, 2 points = 2 packets 0x3e (no flood); tooltip "Durability: 8 of 10" right after the fight (`ven_wear_tooltip_1.png`), "Repair all equipment: 572" (`ven_repair_charsi_hover.png`), repaired to 10 at the first try; 0 ERROR/ASSERT lines, no crash file |
| `checks-20261029-113524-s3` | `dursync`, `MXL_VEN_WEAR_WEAPON=1` | weapon 28 -> 26 on the server and the client, 2 packets, slot `0x0` (seen with the harness; no weapon tooltip shot). The check FAILed only because the Circlet took no hit in this run (10/10, "no damaged item") |

Verified on the player path: the Circlet's tooltip and Repair All (run `-112522-s3`). Not run: Fara and Larzuk, mercenary
items (not checked), charged items (#484).

## Lane identify: Scroll / Tome of Identify on the player path (bug #485, 2026-10-29, slot 3, background mode, build of lane/identify)

Player report (play test 0.1.0): "Scroll of Identify, when right clicked on, does not work on identifying an item." New check
`identify` (tools/game_checks.py): `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<new throwaway> py -3 tools/game_checks.py all identify`.
SHORTCUT (so the verdict is PARTIAL at best): two scrolls `isc`, a tome `ibk` with 5 charges (`70=5`) and four unidentified magic
rings are put on the ground by `item ... ground` and picked up by clicks (scrolls first: a carried tome takes picked-up scrolls in,
so the check wants a character without a Tome of Identify). Then per round, the player path: the inventory opened, a right click on
the scroll / tome, the hover over the ring (shot `id_<code>_<gfx>_cursor.png`), a left click on the ring, hover (shot
`..._after.png`); read: the ring's `identified=`, the scroll gone / the tome's charges (`istat <id> 70`), `cursor`. One scroll
round and one tome round in HD, then the same in legacy graphics (G; the legacy grid is `ID_LEGACY_CELL`, and the check opens
and closes the legacy inventory itself: `right_panel_open()` only sees the HD panel). `MXL_ID_HD_ONLY=1` skips legacy.

| Run | Build | Result |
|---|---|---|
| `checks-20261029-125443-s3` | main's data (misc `spellicon` -1) + this worktree's plugin, HD only (first form of the check) | **bug seen**: no identify cursor after the right click; the left click picked the ring up onto the cursor (`cursor id=25 code=rin`); scroll kept; tome 5 -> 5; no assert, no crash file |
| `checks-20261029-130614-s3` | fixed data | set-up FAIL: the character of the first run carried a tome, the new scrolls were not picked up as items (fixed in the check: scrolls first, new character) |
| `checks-20261029-130910-s3` | fixed data | HD scroll, HD tome, legacy scroll PASS; legacy tome: the right click fell into the world ("Not in town"): the HD panel test had left the legacy inventory open and the check's `i` closed it (fixed in the check) |
| `checks-20261029-131228-s3` | fixed data, new Barbarian IdentThree | **all four rounds identified** (PARTIAL only for the shortcut): HD scroll used up, ring "27% Extra Gold from Monsters" (`id_isc_hd_after.png`; the scroll's cell red while the cursor waits, `id_isc_hd_cursor.png`); HD tome 5 -> 4; legacy scroll used up; legacy tome 4 -> 3, ring "26% Extra Gold from Monsters" (`id_ibk_legacy_after.png`); 0 asserts, no crash file |

The cause and fix are in docs/bugs.md #485 (misc `spellicon` from books.txt `SpellIcon`, `txt_migrate.py` `book_cursors`). Not
run: Deckard Cain's identify (D2R native, needs the Act 1 rescue); a Scroll of Identify bought from a vendor (the same base row).
By hand: right click a Scroll of Identify, then click an unidentified item: the cursor turns into the identify cursor and the item
is identified, one scroll used.

## Lane elvensong: Elvensong's charm on the player path (bug #487, 2026-10-29, slot 3, background mode, build of lane/elvensong)

Player report (play test 0.1.1): "Charm doesn't work ... it works like mindblast currently, with no conversion." New check
`elvensong` (tools/game_checks.py): `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<new throwaway> MXL_CHAR_CLASS=druid py -3 tools/game_checks.py
all elvensong` (`MXL_ELV_LEVEL` sets the skill level, default 20; the base level the game's point function reached is reported).
SHORTCUT (so PARTIAL at best): skill points, character level 60 and life / mana (Tank) set by the harness, zombies spawned. Player
path: Elvensong on the right button, a background right click beside the character. Round 1 with nothing near (4 s), round 2 with 5
zombies 2 sub-tiles away (12 s); every ~0.4 s: the spirits (`friendlyelvensong`) alive and their mode, the zombies' life and state 53
(conversion, `states mon:<id> 53`); shots `elv_<round>_1.0s.png` / `_3.0s.png`.

| Run | Build | Result |
|---|---|---|
| `checks-20261029-151834-s3` | lane build before the fix (calc1 / calc2 of Elvensong Spell blank) | **bug seen**: spirit summoned; alone it leaves after 1.1 s (Median's text: "until no target is nearby"); next to the zombies it stays 12 s and casts (mode 5), 1-2 damage per song with curse sparks, **0 of 5 converted**; 0 asserts |
| `checks-20261029-152516-s3` | fixed data (calc1 `dm56`, calc2 `par3`) | **4 of 5 converted** (first at 2.3 s), each charm about 3 s and renewed by later songs, conversion overlay seen, a charmed zombie hits another (`elv_near_3.0s.png`); spirit alone leaves after 1.2 s as before; 0 asserts, no crash file (PARTIAL only for the shortcut) |

The cause and fix are in docs/bugs.md #487 (D2R's srvdo 51 reads the conversion chance / length from calc1 / calc2, 1.13c from
Param5-6 / Param3; `txt_migrate.py` `conversion_calcs`). Not run: the nine other srvdo 51 skills fixed with it (item charms,
Dominate, the Sirens' Charm, the Eastern Sorceror's Merc Possess, Black Sleep); how many songs the spirit sings (Median: 10).
By hand: cast Elvensong next to a pack: monsters around the spirit get the blue conversion swirl and fight for you for about 3 s.

## Lane uiplus: the level-up + buttons (bugs #488 / #489, 2026-10-29, slot 4, background mode, build of lane/uiplus; round 1 with main's plugin)

`py -3 tools/game_checks.py all lvlup_ui` (MXL_RUN / MXL_SLOT as usual; unit tests `tools/test_lvlup_ui.py`). In the Rogue
Encampment: the character's unspent points set to 0 (harness set-up; a slot character at level 120 makes the check switch to its own
Sorceress `UiPlusSor`), a shot per graphics mode, then a level-up by D2R's own experience award (`xp`) **while legacy graphics are
on**, then legacy, HD and legacy again (after the G round trip, `legacy2`): a shot and a click on each + button (`LVLUP_XY`, 1600 x 900
client: classic 532 / 1068 x 866, HD 388 / 1205 x 683). A click counts when the half of the screen where its panel opens changed.
`MXL_LVLUP_SETSTAT=1` adds a shot with points set by the harness in legacy; `MXL_LVLUP_PROBE=1` logs harness `lvlbtn` (round 2).

| Run | What | Result |
|---|---|---|
| `checks-20261029-154210-s4` | the slot's level-120 Paladin, 0 stat / 119 skill points from the save | classic: stat + grey, skill + red (points loaded with the game); HD shows no New Skill button for this character (all its skills may be at their cap; not followed up) |
| `checks-20261029-155405-s4` | level-up 1 -> 11 **in HD**, then G | both modes lit (`lvlup_legacy_points.png`, `lvlup_hd_points.png`: "New Stats" / "New Skill") |
| `checks-20261029-155656-s4` | level-up 11 -> 15 **in legacy** | **#488 reproduced**: both classic buttons grey with 20 / 4 points (`lvlup_legacy_points.png`), the clicks open nothing; HD lit, its clicks open the sheet and the tree |
| `checks-20261029-160651-s4` | as above + `MXL_LVLUP_SETSTAT=1` + the G round trip | harness points (5 / 2) in legacy: grey (`lvlup_legacy_setstat.png`); after the level-up: grey, clicks dead; HD: clicks open the panels; back in legacy (`lvlup_legacy2_*`): red, both clicks open the character sheet / skill tree. FAIL by design (the dead legacy clicks) |
| `checks-20261029-161539-s4` | slot copy of D2R's classic `hudpanel.json` with `"isFloating": true` on StatUp / SkillUp (experiment, not in the build) | no change (same places, grey after the level-up) |
| `checks-20261029-161821-s4` | every plugin part off (`mxl2012-core-off.txt`, 23 words; the harness stays) | the same: grey, dead clicks, lit after G. Not the plugin |

Controls that did not run: an empty mod with only the harness plugin (vanilla tables) and save mode `standard`: the new
character was made but the run never reached the game (`run4/5-vanilla.log`, `run7/8-standard.log`); the throwaway saves were deleted and
the slot's toml put back. #489 is D2R's (and 1.13's) classic place. Evidence copied to `mxl2012-runs/uiplus/`.

Round 2 (the fix, plugin part `lvlupui`, docs/bugs.md #488, docs/plugin-plan.md section 24; dev DLL of lane/uiplus, same slot):

| Run | What | Result |
|---|---|---|
| `checks-20261029-163947-s4` | `MXL_LVLUP_PROBE=1` (harness `lvlbtn`), before the part | legacy after the level-up: StatUp / SkillUp `disabled=1 mask=0`, Updates 0 against 800 Draws in 2 s; `lvlbtn update` (one Update each): `disabled=0 mask=1`, then D2R updated them every frame (306 in 2 s), the clicks opened the panels. HD: panel manager `+0xb9` = 1, buttons floating, updated |
| `checks-20261029-164323-s4` | the part on, plain check | level 25 -> 27 in legacy: both buttons red at once (`lvlup_legacy_points.png`; grey before, `lvlup_legacy_before.png`), clicks open the character sheet / skill tree (panel change 55 / 51); HD the same as before (21 / 22); legacy2 the same; `lvlupui on ...; grey legacy buttons updated 2476 times, draws 6868`; 0 asserts, no crash file. PARTIAL only because the check leaves the look of the buttons to the eye |

By hand: in legacy graphics gain a level: the two + buttons turn red at once and open the panels (before the fix they stayed grey until
G was pressed twice).

## Lane veilking: the Veil King in HD (bug #496, 2026-10-29, slot 3, background mode, build of lane/veilking)

Lab script `mxl2012-runs/veilking/lab.py` (harness set-up, kept outside the repo): `MXL_RUN=veilking MXL_SLOT=3 py -3 lab.py <worktree>
<out> <stages> hd,legacy`. Stage `cand` spawns monsters (`VK_CAND`, monstats Ids) beside a tanked character in the Blood Moor in god
mode and crops the shots; `veil` makes a level-120 Necromancer cast Summon Veil King (476) in the Rogue Encampment in each
graphics mode; `shift` sets states on a skeleton with `setstate` (a server-only state shows no colour on the client: no tint seen
for any index, so it cannot measure HD state colours). Seen with the harness, not on the player path.

| run | build | result |
|---|---|---|
| `run1` | main | HD candidates for `!9` (`candidates.png`); the `shift` stage showed no colours (above) |
| `run2` | `!9` -> doomknight1 x1.6, a `customColorShiftEntries` entry for index 1 in its own table | Doom Knight drawn, twice the player's height, **still neon green**: HD does not read the entry for index 1 |
| `run3` | + `meslayer` colorshift 0 (by hand in work/mod), x0.9 | **no green**: bronze Doom Knight, a little below the player |
| `run4` | full build, x0.9, scored colour; Belial spawned | olive (shared hue +0.10 table); Belial tan-brown, no green (#436) |
| `run6` | final: x1.1, colour val +0.2 (plain table), colorshift 0 | PASS: HD a gold-bronze horned knight with a sword, a little taller than the player, no green; legacy unchanged (Median's crowned skeleton in its pale cloud, own colours). `veil_hd_vs_legacy.png` |

Open: the pale cloud (`slayercloud`) does not show in HD.

## Lane unported: item use pSpell 3 / 10 and mercenary level above 99 (ME9) (2026-10-29, slot 4, background mode, build of lane/unported)

Two rows of docs/unported.md that matter to players, checked on the player path. Evidence in `mxl2012-runs/unported/` (report,
shots, log scan per run). Unit tests: `tools/test_game_checks_itemuse.py` (Median's calcs, the mercenary's experience formula and cap).

**`iu_use`** (tools/game_checks.py): `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<throwaway> MXL_CHAR_CLASS=barbarian py -3
tools/game_checks.py all iu_use` (`MXL_IU_LEVEL`, default 30; `MXL_IU_ONLY=zkq,zoh,...` picks items). SHORTCUT (so PARTIAL at
best): level 30, max life / mana 1000, life at a quarter and mana at 0 before the packs, mana regeneration off (manarecoverybonus
-100: it adds tens a second at that max), each item dropped on the ground by the harness. Player path: the item picked up by a
click, used by a background right click in the backpack. Judged: the item used up, each stat moved by Median 2012's misc.txt calc
(integer arithmetic; Signet of Gold to the carry limit level x 10,000), no other stat moved; the potion caps over Save and Exit.
Lane phase3's `rpsignets` covers six signets the same way; `iu_use` adds the Life / Mana Pack, the exact deltas and the caps.

| Run | Result |
|---|---|
| `checks-20261029-183404-s4` (`iu_use_first`) | Signets of Learning +1 / cap +1, Greater Learning +25 / +25, Experience +7,500, Gold +4,500, Skill +1 / cap +1: all Median's. Life / Mana Pack cut by the character's own max life 80 / mana 5 (set-up, fixed). **Apple kept**, "I can't" (`iu_dog.png`): bug #499 |
| `checks-20261029-184403-s4`, `-184537`, `-184643` | packs alone: Life Pack +300 (Median `ulvl*10`); Mana Pack +504 with regeneration on, +300 with it off |
| `checks-20261029-185035-s4` (`iu_use`) | **PARTIAL (all seven pass)**: zkq, zky, zku, zkw, `!@B`, Life Pack, Mana Pack each used up and moved by Median's calc, nothing else; caps 78 / 3 (ids 370 / 371) kept over Save and Exit; 0 asserts, no crash file |

**`ml_merc`**: `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<throwaway> MXL_CHAR_CLASS=barbarian py -3 tools/game_checks.py all ml_merc`
(`MXL_ML_PLAYER` player level, default 120; `MXL_ML_STEPS` e.g. `115,118,119`; `MXL_ML_AREA` / `MXL_ML_MON` where and what is
killed, default act 5 Siege (110) and `r_alpha` (1183, Exp 2000)). SHORTCUT: Kashya's quest gate and gold, the player's level, the
mercenary's experience set one point below each step's start (Median's hireling Exp/Lvl 1: level L at L x L x (L + 1)) and its
level one below, its life raised (the spawns hit back). Player path: kills next to the mercenary, its share of the experience,
the game's own level-up; then Save and Exit + Play.

| Run | Result |
|---|---|
| `checks-20261029-185326-s4` (`ml_merc_bloodmoor`) | Blood Moor zombies: 99 -> 100 (+6 exp), 109 -> 110 (+42); at 119 nothing: Median's ExpRatio (64 / 1024 at 119) rounds a zombie to 0. Set-up changed to r_alpha in the Siege |
| `checks-20261029-191158-s4` (`ml_merc_player110`) | player 110: mercenary 99 -> 100, 109 -> 110: it reaches the player's own level |
| `checks-20261029-191345-s4` (`ml_merc_115_119`) | player 120: 114 -> 115, 117 -> 118, 118 -> 119 by kills |
| `checks-20261029-191542-s4` (`ml_merc`) | **PARTIAL (pass)**: 100, 110, 119 reached by kills; at 119 (1,742,399 exp, one short of 120) 36 kills add nothing: the engine stops a mercenary one level below experience.txt's MaxLvl, as 1.13c's stops at 98 under MaxLvl 99. Level 119 and its experience kept over Save and Exit; 0 asserts, no crash file |

So ME9 holds with the cap at 119, not 120 as docs/median-rules-audit.md wrote. Not run: the other acts' mercenaries (same hireling
formula, Exp/Lvl 1 on every row), a mercenary that levels with a player who levels at the same time. During runs at 19:00-19:11
the PC's own mouse moved (the user at the desk); the checks use background input only, the results do not depend on it.

## Lane bugsweep: open low bugs looked at again (2026-10-29, slots 1 and 2, background mode, build of lane/bugsweep)

Round 1 on slot 1 (owner-approved), round 2 on slot 2 after merging main. Evidence in `mxl2012-runs/bugsweep/` (run logs
`run*.log`, `evidence/`). The rows of docs/bugs.md have the details.

| Bug | Result | Runs |
|---|---|---|
| #399 `tiles` crash | Fixed (harness): D2R keeps the warp tiles in one chain at game + 0x3630, not a 128-bucket hash; `CmdTiles` walks that chain under SEH (acts5's `hashscan` verb kept) | `checks-20261029-195926-s1`: 6 calls in Catacombs 2 / 3, all `tiles OK` |
| #434 Hratli out of reach | Not a game bug: his house is reached the long way round (south pier, east market). `ven_planned_walk` walks the measured legs (`VEN_VIA`) and plans the rest on `walkmap`; round 2 tries it first | `checks-20261029-213747-s1` PASS (click routes then the walk), `checks-20261029-224222-s2` PASS (new character SweepBarb, `MXL_VEN_HRATLI_HOUSE=1`, the walk only: trade, sell back, Repair All) |
| #436 Belial green | State 232 `meslayer` (colorshift 1) on the units, on server and client; fixed on main by lane veilking (colorshift 0) | `checks-20261029-183600-s1` |
| #484 charges | Not a bug in game: charges used and recharged reach the client without the patch | `checks-20261029-201732-s1` (with `MXL_CONTROL=dursync`) |
| #392 portal into 134 | Not reproduced: a town portal from 134 to Harrogath and back works | `checks-20261029-195926-s1` |
| #432 vendor asserts | Not reproduced in 8 trade rounds; no data cause found statically | `checks-20261029-185149-s1` |
| #292 mercenary in 110 | Not reproduced in 2 tries (bare and equipped Rogue) | `-185149-s1`, `-195926-s1` |
| #17 first-chance report | Not reproduced in 6 launches; a report of the same kind came from an exception the plugin caught itself (D2R's last-resort handler logs caught ones too) | slot 1 runs above |

Run `checks-20261029-224054-s2` was BLOCKED by the check itself: a new character's save has no quest section before its first
Save and Exit (`quest_done` now reads that as "not done"; the closed edit saves first).

## Lane uifix: Ctrl-click quick move to the stash (bug #503, 2026-10-30, slot 4, background mode)

Slot 4's installed build (lane build of 2026-10-29 18:30) with this lane's dev plugin swapped in (slot's own DLL backed up and put back,
sha1 checked), new Sorceress `UifixStash` (still in `mxl2012-s4`). Scratch driver and helpers (not committed):
`mxl2012-runs/uifix/` (`drv.py`, `qm.py`, `sweep.py`, `list1.py`); evidence `mxl2012-runs/uifix/checks-20261030-000212-s4/`.

**Harness first.** A posted Ctrl never reached D2R's item click: the clicks were plain pick-ups (the trace's GetKeyState histogram
never had vk 0x11). user32's `GetKeyState` answers from the thread's cached key state, which posted messages do not update, and only
some calls reach the hooked `NtUserGetKeyState` syscall. The harness now also redirects the game exe's import of `GetKeyState`
(`PatchImport` by the resolved address in the IAT directory; the startup line says `GetKeyState import hooked`), and
`game_ctl.click` takes `mods`. After that a Ctrl-click moved a scroll into the stash (`s6_ctrl_tsc.png`).

**Sweep** (Ctrl-click of each item from the backpack with the stash open, HD; 40 kinds: runes incl. a Great Rune, gems incl. rainbow
stone and onyx, jewel, carry1 charms `a55` / `yq7` (2x2), relic, crystal, arcane crystal, oil, class reward, signet, elixirs, Token of
Absolution, summoning scroll, shrine (1x2), Boss Killer ring, mystic orb, tome, key, magic ring, rare amulet, uniques 600 / 1440, set
150, body armour 2x3, polearm / bows / claw / shield 2x4, class helms, sorceress orb, quest items):

| Target | Result | Evidence |
|---|---|---|
| Personal tab | every kind moves; the two last 2x2 items stayed only because the page had no 2x2 gap left (correct) | `sweep_personal.json`, `sw_personal_end.png` |
| Shared tab | every non-quest kind moves, also the carry1 charms (brought back from the personal tab) | `sweep_shared.json`, `sw_shared_end.png`, `sh4_carry_leg.png` |
| Shared tab, quest items | **refused**: Horadric Cube, Bark Scroll, Wirt's Leg, also on an empty shared page where a normal 2x2 helm goes in | `sh3_page2.png`, `sh4_carry_leg.png` |
| Legacy graphics (G), shared tab | the same: scroll and rune move, Wirt's Leg stays | `lg1_quickmove.png` |

The refused ones are exactly the items with a `quest` value in misc / weapons.txt (26 rows: cube, scrolls, Khalim's parts, staves,
Wirt's Leg, ...): the same codes and values as D2R's own tables, and D2R keeps quest items out of the shared tabs. Median's own
`ques`-type items without a `quest` value (Token of Absolution) move. So no port problem was found (bugs.md #503).

Not done: Ctrl-click from the stash or cube back to the backpack was only used, not swept; the materials tab (D2R 3.3) is not in
this stash. **Left behind:** slot 4's shared stash (`mxl2012-s4`) holds about 40 test items on pages 1-3 (not cleaned: the slot was
taken by another lane right after the run).

**Skill icons / legacy tab titles (dropped from this lane, coordinator 2026-10-30).** Found before the hand-over, nothing changed:
both release-note lines look stale. The notes were written (relprep, 2026-10-29 02:06) after the tab-title fix (bug #33, lane
monitems, 2026-10-28; slot 4's installed classic `skillstreepanel.json` has the seven classes' `textTab0-2` empty) and before lane
hdicons2's shared icon sheet (02:27), which gives Fire Wall D2R's icon and the three item skills class-sheet frames
(docs/hd-icons.md, seen in game there); Moon Queen / Balance / Wings of W are passives, never on a skill button. Not re-checked in
game by this lane.

## Lane sound: Raid (#501) and "ancient armor" noises (#502) (2026-10-30, slot 3, background mode, build of lane/sound)

Dev tool: a dev DLL started with `MXL_SOUND_TRACE=<file>` (plugin `sound_guard.cpp`) counts every sound id that goes through the
five sound record readers, the unit sound `0x107dd0` and the client play `0x1a0780`, and rewrites the file about once a second
(`<id> <c7> <b0> <path> <pick> <variant> <unit sound> <client play>`). Column 6 (variant picks) is a sound that resolved to a
file; column 8 counts every request. The id is sounds.txt's `*Index` column (line 2 of the file is a blank row with id 0).
The lab script (`mxl2012-runs/sound/lab.py`) takes the counts before and after each step and lists the sounds by name.
New harness form: `skill left|right <id> <item id>` selects a charged skill of that item (the game's charge list).

| Run | What | Result |
|-----|------|--------|
| `mxl2012-runs/sound/run2` | Barbarian SndBarb, spirits 433-435 summoned, re-cast, killed; HD and legacy (before the fix) | HD: `ancient_death_hd` (6754) on every spirit death / re-cast (11 in 12 re-casts), legacy none: bug #502 |
| `mxl2012-runs/sound/run3` | the same with part `spiritsound` | HD: 10 requests, 0 plays, `plays skipped 11`; the spirits' own `barbarian_death_1` still plays; legacy unchanged; 0 asserts |
| `mxl2012-runs/sound/run5`, `run6` | Amazon SndAma, Blink level 5 charges (Raid's) on a ring, `skill right 346 <item>`, 12 and 40 right clicks per mode in the Blood Moor | Blink warps, `baal_teleport` plays, `druid_shockwave` asked for 64 times per cast and played once; sounds go on afterwards; 0 asserts, game alive: #501 not reproduced |
| `checks-20261030-004112-s3` | checks `snd_spirits`, `snd_blink` (tools/game_checks.py, with `MXL_SOUND_TRACE`) | `snd_spirits` PASS (HD: 11 requests of `ancient_death_hd`, 0 played, skips 0 -> 11; legacy: none); `snd_blink` PARTIAL (6 casts per mode, `baal_teleport` 6 each, the game alive; the by-ear part not judged); `mxl2012` PASS. Copied to `mxl2012-runs/sound/checks-20261030-004112-s3/` |

The checks: `MXL_RUN=<lock> MXL_SLOT=N MXL_SOUND_TRACE=<file> py -3 tools/game_checks.py all mxl2012 snd_spirits snd_blink`
(each makes its own character: SndBarb, SndAma). Without the trace `snd_spirits` judges by the plugin's skip count only
(PARTIAL). Not judged: what the speakers play (no audio capture on this PC); a stackable javelin cannot be put in the hand by the
harness, so the charges sit on a ring (the same stat 204).

## Lane totems: totems after Bend the Shadows (bug #493, 2026-10-29, slot 3, background mode, build of lane/totems)

The player said: "Totems slow / lose effects after Shadow Blink". The owner ruled that the totems keep warping with the player but
must not stack or slow. Scripts and evidence (the check runs copied too) are in `mxl2012-runs/totems/`. Lab `totemlab.py`
(`MXL_RUN=<lock> MXL_SLOT=N py -3 totemlab.py <worktree> <out> [hd,legacy] [windows]`; `MXL_CONTROL=petspread` gives a control run
with the part off). It runs in each graphics mode:
- 4 totems (488, 495, 493, 497) cast by `cast` on spawned zombie corpses 3 sub-tiles apart;
- 3 windows of 8 s, each with a zombie (life 400000) 6 sub-tiles away. Per window: `missiles reset` / `missiles` (one
  spawner per totem shot), totem attack episodes, time to the first attack, dummy states;
- Bend the Shadows by a background right click on the first totem;
- the same 3 windows again.
It records positions and server / client states, with shots `totem_<mode>_before_*`, `_after_*` and `_end`.

New check `totem_spread` (tools/game_checks.py):
- Command: `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<new throwaway> MXL_CHAR_CLASS=necromancer py -3 tools/game_checks.py all totem_spread`.
- Shortcut (so PARTIAL at best): skill levels, level 120 and Tank are set by the harness, and the totems are cast by `cast`.
- Player path: Bend the Shadows on the right button, a background right click on the first totem.
- PASS needs:
  - the player moved;
  - all totems within 8 sub-tiles;
  - no two totems on one sub-tile, and none on the player's;
  - the `mxl2012` `petspread` line counting a spread.
- Shots: `totem_spread_before.png`, `totem_spread_after.png`.

| Run | Build | Result |
|---|---|---|
| `base1/` (lab) | lane build, `petspread` off | **bug seen**: after the blink all 4 totems are on the player's sub-tile (distance 0) in HD and legacy and stay there. Legacy draws one totem; HD draws one spire plus bare orbs, and orbs are also left at the cast spots. **No slowdown**: missiles per totem per window 3.3 / 2.7 (HD) and 2.7 / 3.3 (legacy) before / after; first attack 0.07-0.64 s; states 105 / 122 / 234 unchanged |
| `fix1/` (lab) | first `petspread`: only the pet warp `0x596d40` hooked | still stacked. Check `checks-20261029-230013-s3` showed "pet warps 0": Bend the Shadows does not use `0x596d40` |
| `checks-20261029-230437-s3` | `0x500a40` / `0x501df0` hooked, collision test only | spread 4, but 1 sub-tile apart round (+3,+3): D2R's collision test does not see a totem placed a moment earlier |
| `checks-20261029-230717-s3` | + spots of the same gather kept 3 apart | **PARTIAL (pass)**: (+3,+3) (-3,+3) (-3,-3) (+3,-3) round the player; "owner moves with pets 1, onto the owner 4, spread 4" |
| `fix2/` (lab) | same | HD and legacy: four separate spires at (+3,+3) (-3,+3) (-3,-3) (+7,-7), the last one where the 3 and 5 rings were blocked. Missiles per totem per window 2.7 / 3.7 (HD) and 2.7 / 3.0 (legacy); states unchanged; the gather is kept. HD still shows two bare orbs at the cast spots (#500) |

The cause and fix are in docs/bugs.md #493 and docs/plugin-plan.md section 26. The dummy's damage does not show a rate: the
totems took 350k-400k of its 400k life in every window. Not run:
- other warp pets after an owner move (mercenary, golems: they now start a few sub-tiles off instead of on the player);
- a waypoint or level change with totems;
- the `0x596d40` path (pets left in an inactive room).
By hand: cast four totems, then Bend the Shadows onto one of them. The totems appear round you, not on you.

## Lane hdgreen: colorshift-1 states, moved totem orbs, empty overlay stubs (bugs #500, #506, #507, 2026-10-30, slot 1, background mode, build of lane/hdgreen with lane/totems merged)

Lab scripts in `mxl2012-runs/hdgreen/` (harness set-up, kept outside the repo). `greenlab.py`: `MXL_RUN=hdgreen MXL_SLOT=1 py -3
greenlab.py <worktree> <out> [modes] [groups] [state ids]`; per group (a class's skills on its own Hdg* character; `mon`: monster
skills given to a Necromancer with `setskill`) and graphics mode, in the Blood Moor in god mode, each skill is learnt, cast
(`cast <id> self` / `unit <zombie>`; passives just learnt), then the client's states of player and zombie (`cstates`) and a shot with
crops. `mksheet.py` makes contact sheets of the crops. `totemlab.py` is lane totems' lab (4 totems, Bend the Shadows by a background
right click); `veillab.py` is lane veilking's (Summon Veil King). Seen with the harness, not on the player path.

| run | build | result |
|---|---|---|
| `g1` | main data (49 states colorshift 1) | 39 of 49 states on the client by real casts; every HD shot neon green, every legacy shot the unit's own colours (`sheet_sor.png`, `sheet_cls.png`, `sheet_mon.png`). Not put on the client: 10 (bugs.md #506) |
| `tot1`, `tot2` | 4 hand-made copies of the `lightningspire` unit on 4 totems | vfx on bone Root: glass shell still left at the cast spot; nfrost particles: magenta squares; no vfx: nothing left; willowisp glow / skmage wrist on the spire: move with it (smoke, small flame) |
| `veil2` | + all 49 colorshift 0, `slayercloud` -> `druid/cyclonearmor_1back` | PASS: HD Veil King with pale swirling bands, no green; legacy unchanged (`veil2_sheet.png`) |
| `g2` | same | PASS: no green in HD for any of the 39 states (neon-green pixel share 0.000 in every crop, 0.007 mean before: `green_metric.txt`; `sheet_after_sor.png`, `sheet_after_all.png`); legacy (Sorceress group) unchanged |
| `tot3` | + `mxl_lightningspire_moved` for the 12 skill-summoned totems (tools/hd_monsters.py) | PASS: HD spires without the glass orb, after Bend the Shadows nothing left at the cast spots; legacy unchanged (`tot3_sheet.png`) |

## Lane uicheck: release-note known issues re-checked, slot 4's shared stash emptied (2026-10-30, slot 4, background mode)

Slot 4's installed build (lane build of 2026-10-29 18:30, after hdicons2 and the #33 fix), no build or install of this lane. Scratch
driver (not committed): `mxl2012-runs/uicheck/` (`drv.py`, `cls.py` per class, `stashclear.py`); evidence
`mxl2012-runs/uicheck/checks-20261030-012114-s4/`. New level 1 characters `UicSor`, `UicAma`, `UicNec`, `UicPal`, `UicBar`,
`UicDru`, `UicAss` (+ a time stamp, in `mxl2012-s4`), each: the skill bar, the three tree tabs in HD and in legacy (G). 0 asserts,
0 crash files, about 13 minutes of slot time.

| Release-note line | Seen | Evidence |
|---|---|---|
| Fire Wall and Moon Queen / Balance / Wings of W show no icon on the skill bar | **gone**. Fire Wall (learnt by `setskill`, put on the right button by `skill right 51`) shows its fire wall in HD and legacy. Moon Queen and Balance learnt (Wings of W: `setskill` refused, level 0): passives, never on a button. Static: their `~shared` rows have cels 92 / 88 / 90, Fire Wall 78, all on the 116-frame shared sheet | `uic_sor_hd_bar.png`, `uic_sor_legacy_bar.png`, `uic_sor_hd_popup.png` |
| The skill trees use D2R's plain background | **gone**: Median's page art in HD (hdicons2) | `uic_*_hd_tree*.png` |
| Legacy (G): the skill tab titles are drawn twice | **gone** for all seven classes, three tabs each: only the art's labels (SPECIAL, MANA, ...). Warlock not made (no RotW on the slots' account); the classic layout keeps D2R's titles for it and the mod ships no Warlock page art, so nothing to double | `uic_legacy_tablabels.png`, `uic_legacy_trees_sheet.png` |

The notes now drop those three lines. Also re-read (static): the walls line said 17 maps without walls in HD, but since lane walls
8 of them have D2R's stock walls in Median's layout (docs/unported.md), so it now says 9 without walls and 8 with D2R's; the item
picture line now says "most" (23 pictures reuse D2R's HD art, lane hditems). Still true as written: Pandemonium 2 by town portal
(#392, open, not reproduced since, no player route), Colossal Summit (#261), long sessions (#360: fixed, the warning can still
come on a very long route), stand-in HD art, made-up names, Chronicle naming the base (#331).

**Slot 4's shared stash.** `SharedStashSoftCoreV2.d2i` held 3 pages with 35 + 1 + 4 items (lane uifix's sweep). No tool or
harness verb clears shared tabs (`packclear` / `remove` take the player's own items), so with the lock held and the game closed
the item list of each page was emptied in the file (header kept, page size 68: `JM` and a count of 0; 1756 -> 204 bytes;
backup `mxl2012-runs/uicheck/stash-backup/`). In game the shared tab then showed pages 1-3 empty (`uic_stash_shared*.png`,
`uic_stash_pages.png`) and the game saved it back unchanged (204 bytes).

## Lane apple: the Apple's item spell and totems-only `petspread` (bugs #499, #493, 2026-10-30, slot 3, background mode, build of lane/apple)

Build: lane/apple (lane/totems merged), plugin `mxl2012-core` 0.1.2 with the new part `appleuse` and `petspread` narrowed to
totems. The data build is `tools/build.py` (validate 0 errors). All runs used slot 3 in background mode, and the real-input
watchdog was clean in every run. Evidence is in `mxl2012-runs/apple/<run>/`, with console logs `run1.log` to `run5.log` next to it.

| Run | Character | Checks | Result |
|---|---|---|---|
| `checks-20261030-004650-s3` | new Barbarian `Applebar` | `mxl2012`, `apple_use`, `rpsignets` | `mxl2012` PASS (29 lines, `appleuse` on); `rpsignets` PASS, all 7 rows: `dog` is used up, no skill point, state `mega_apple` (44) on. `apple_use` BLOCKED: it tried Akara, who does not sell the Apple (misc.txt `dog` has no Akara min / max; Charsi, Fara, Lysander, Hratli, Alkor, Larzuk, Anya and Jamella sell it). The check now buys from Charsi |
| `checks-20261030-005257-s3` | new Barbarian `Applebarb` | `apple_use` | **PASS**: bought from Charsi by a right click in her Trade panel, used by a right click in the backpack, used up; state 44 on, end frame 16795 read at frame 1905 (14890 of 15000 frames left); stats hpregen 6 (= maxhp / 3000 x 100 %), item_vitality_percent 7, damagepercent 9, item_energy_percent 11, item_allskills 1 (= the synergy stats 444 / 498 / 445 / 461 set to 7 / 9 / 11 / 1 by harness); the player's hpregen 0 -> 6; skill points 0 -> 0. **`apple_save` PASS**: after Save and Exit and back in, the Apple is still gone and the state is off (1.13c saves no states). One last-resort crash report at shutdown: the known handled first-chance access violation outside the game image (module base `0x7ffeb1c50000`, as in "Lane equip391"), copied into the run folder |
| `checks-20261030-005552-s3` | new Necromancer `Applenec` | `mxl2012`, `totem_spread`, `pet_keep` | `totem_spread` **PARTIAL (pass)**: four totems at (+1,+7) (-5,+7) (-5,+1) (+1,+1) of the old spot, round the player after Bend the Shadows; "onto the owner 4, spread 4, other pets left 0" (`totem_spread_after.png`). `pet_keep` FAIL: the right click on the walking shadow missed. The check now clicks again, up to 3 times |
| `checks-20261030-005939-s3` | `Applenec` | `pet_keep` | The blink worked (spread +0, other pets left +2). FAIL only on the distance rule: the mercenary was 16 sub-tiles away 0.3 s after the waypoint (4 in the run before), so it had already walked off. The check now judges by the counters |
| `checks-20261030-010127-s3` | `Applenec` | `pet_keep` | **PARTIAL (pass)**. A Kashya mercenary (class 271) and a Summon Shadows pet (473, class 1709): after Bend the Shadows "owner moves with pets +1, onto the owner +2, spread +0, other pets left +2", pets 4 and 5 sub-tiles away; after the waypoint Rogue Encampment -> Cold Plains "+2 / +4 / +0 / +4", mercenary 4 and shadow 9 sub-tiles away (`pet_keep_blink.png`, `pet_keep_waypoint.png`) |

Notes:
- **Not on the player path:**
  - `apple_use`: gold, and the four synergy stats (so that stats 2-5 are not 0).
  - `pet_keep`: the hire-gate quest bit, gold, skill levels, level 120, Tank, the shadow made by `cast`, and the Cold Plains waypoint bit.
- **Pets:** Median 2012 gives players no golem skill (D2R's golem rows are made by no Median skill), so Summon Shadows stands in for "a golem". Both non-totem pets keep D2R's placement on the player's sub-tile and walk off by themselves.
- **Unit tests:** `appleuse_tests` covers the Book / Apple codes and the constants. `petspread_tests` gains `Listed` (the pet-list walk).

By hand, for the Apple:
1. Buy an Apple from Charsi and right-click it in the backpack.
2. It is used up, the regeneration starts, and life refills for 10 minutes.
3. A Book of Skill still gives a skill point.

By hand, for the pets:
1. With a mercenary and shadows, Bend the Shadows onto a shadow.
2. They arrive on you and walk off.
3. Totems cast first are spread round you instead.

## Lane playerbugs: "Goodbye" in the chat and cave snappers (bugs #504 / #505 / #508, 2026-10-30, slot 4, background mode, release build 0.1.2)

Lab scripts and evidence in `mxl2012-runs/playerbugs/` (`lab.py`, `lab2.py` .. `lab5.py`, run logs `run*.out`, shots in
`run1/` .. `run5/`, chat crops `sheet_*.png`). Test character: a new Druid "PbTrapRat". Table edits for a run were made on the
slot's installed tables (`variant.py`, `fixslot.py`) with a backup, and restored and compared afterwards. The rows of
docs/bugs.md have the details.

| Bug | Result | Runs |
|---|---|---|
| #504 `<name> says: Goodbye.` | Reproduced and fixed: Vanquish 678, Other Raven Heart 605 and Female Vanquish 905 (the Act 1 Rogue mercenary's buff) each print the line, HD and legacy; with `player_voice_sounds` applied, 20 casts of 678 / 605 / 685 / 905 print none. Idle and walking 100 s and the numpad "Say" keys print nothing | `run1` (HD + legacy casts, idle, keys), `run2` (sound row variants: the line follows the file), `run3` (after the fix), `run4` (Mana Coil before the fix: harness cast prints nothing) |
| #504 in Trap Rat Form | Not tested: the harness cast of 448 is refused at level 1 (no gear); the morph has no voice sound in its rows | `run1` |
| #505 cave snappers | Median's design: hpregen 2180/256 per frame (~213 life/s) on the Sleeping Cave Snapper, 328/256 on the Cave Snapper; Fire Bolt hurts the Cave Snapper and does not get past the sleeping one's regeneration; no damage reduction | `run4`, `run5` |
| #508 boss / soldier lines | Listed from the tables only (vo.json keys), not tested | none |

## Lane fxpick: overlays on empty D2R HD stubs (bug #507, 2026-10-30, slot 4, background mode, build of lane/fxpick with main's plugin e8d4422)

Lab scripts in `mxl2012-runs/fxpick/` (harness set-up, kept outside the repo; made from lane hdgreen's `greenlab.py`).
`fxlab.py`: `MXL_RUN=fxpick MXL_SLOT=N py -3 fxlab.py <worktree> <out> [modes] [groups] [state ids]`; per entry (built skill and
state ids) the skill is learnt and cast on an Fxp* character (`mon`: monster skills given to a Necromancer), shots 0.3 s (cast
overlays) and 1.5 s / 2.3 s (state overlays) after the cast, crops round the player (and the zombie for unit casts), the client's
states. `fxlab2.py` adds Bend the Shadows at a Death's Fury totem (background right click) and spawned attackers for `slowed`.
`mksheet.py` makes the sheets; `render.py` the offline classic frames (`src_classic.png`, candidates `cand_*.png`). Seen with the
harness, not on the player path. The plugin was not rebuilt (data-only change; `build_plugin.ps1` was not run in this lane).

| run | build | result |
|---|---|---|
| `r1` | 16 picks | stopped: Median's skill ids used, the build renumbers them |
| `r2` | 16 picks | HD: Holy Armor pale blue globe, Thundergod white ring, Firedance flames, Poison Flash green flash, Lightning Shield cast white crackle, Blood Fury gold rays, abolishcurse green flash on the target. Not seen: War Spirit (`srfirehit`, one-shot), Pagan Heart after the cast (`frozenarmor_hit`, one-shot), Amazing Grace after 0.3 s (`ice_explode`, one-shot). Legacy unchanged (Thundergod, Pagan Heart, Amazing Grace, War Spirit, Firedance). `sheet_r2.png` |
| `r3`, `r4` | War Spirit -> `sorceress/enchant` | not seen on the Amazon (drawn on the weapon); the same state with `common/burning` swapped in by hand on the slot: flames (`sheet_r4.png`), so the state does draw overlays in HD. Bend the Shadows / `slowed`: see below |
| `r5` | War Spirit -> `common/burning` | PASS: HD purple cast, then flames; legacy Median's flaming swipe (`sheet_r5_full.png`) |
| `r6` | Pagan Heart -> `paladin/aura_resistcold`, Amazing Grace -> `sorceress/frozenarmor` | Pagan Heart PASS: HD blue ring at 1.5 s and 2.3 s, legacy unchanged. Amazing Grace: hardly visible (a distortion) (`sheet_r6.png`) |
| `r7` | Amazing Grace and `shiversoverlay` -> `common/shrine_resist_cold` | PASS: HD a pale blue sparkle over the unit, still there at 1.5 s; legacy unchanged (`sheet_r7.png`) |

Not seen: `baaldeathhead01` (Bend the Shadows blinks the player to the totem in both modes, but no skull shows in legacy either at
0.3 / 1.5 s), `extra/shiverscast` / `shiversoverlay` (state `slowed` never landed: Spider Lay refused, Vine Attack on the zombie
and spawned plague poppies / spiders gave no `slowed` in 15 s). The four unused arts (`extra/aurablue`, `aurared`, `aurast_bl`,
`aurast_rd`) keep the stub. Unit tests: `test_overlay_picks_not_empty`, `test_no_stub_stand_ins` (tools/test_effects_hd.py).

## Lane maptint: Median's look on the 8 retextured maps (2026-10-30, slot 4, background mode, build of lane/maptint, slot plugin 0.1.2)

Build: `py -3 tools/build.py` (the tint is a step of `walls_hd.py build`), install `MXL_SLOT=4 MXL_RUN=maptint py -3
tools/install_mod.py --slot 4` (data only). Check (harness travel and god mode, new level 1 character MapTint):
`MXL_RUN=maptint MXL_SLOT=4 MXL_CHAR=MapTint MXL_CACHE_POLL=3 MXL_WALL_LEVELS=60,59,95,18,98,126,125,127 py -3 tools/game_checks.py all wall_maps`.
Evidence in `mxl2012-runs/maptint/`; `sheets.py <before run> <after run> <out>` makes the before HD | after HD | legacy sheets.

| run | result |
|---|---|
| `run1-checks-20261030-032500-s4` | first tints: all 8 maps in HD and classic, asserts none, 0 ERROR / ASSERT lines in `d2rloader.log`, no crash file. Charismatic only went neutral grey, cypherpunk too pale (`sheets1/`) |
| `run2-checks-20261030-033400-s4` | final tints (cypherpunk and charismatic stronger): the same 16 visits, asserts none, no errors; peaks VTT 105/128, TileMaskRuleSet 3/16, ModelAsset 1421/2750; load screens as before (cypherpunk 0.72 s vs 0.55 s, glados 2.59 s vs 2.53 s). Per-map results: docs/maps-hd.md "Median's look" (`sheets/`, before = lane hdwalls2's `checks-20261030-010654-s1`) |

Still to look at by a player's eye: whether the tints read as Median's maps at normal play (the harness shots are at level 1,
god mode, mostly at the arrival).

## Lane endgame: Diablo, Act 5 travel, the Throne waves, Baal and Mephisto's moat on the player path (2026-10-29/30, slots 2-4, background mode, main's plugin)

Sorceress `EndSorc` (slot 2) / `EndSorcD` (slot 3) set up by stage `build` as lane acts5 (level by `xp`, stat points by packet
0x3a, skill points by `setskill`, two rings and an amulet, no weapon; travel to each level by `level`), level 98 from the xp award.
Logs `mxl2012-runs/endgame/run1.log` .. `run16-s3.log`, run folders `work/runs/checks-*` below. New in `game_checks.py`:
`acts_planned_walk` (left clicks on paths planned on the game's walk collision, `relp_walk_to` as lane bugsweep's Hratli walk;
fallback after a straight `acts_walk` leg fails: route legs, the Diablo star walk, the spell fight's close-in, the throne),
`acts_rest`, the "lost" loop (Diablo walked off while the character was held at a wall: rest, back to the star, find him, walk up),
a death on the walk up to the boss now counts and starts the retries (it used to start the fight in town and count nothing),
`acts_throne` rewritten (revive, gear again, rest and go back after a death, at most 8 times; passes when the fifth wave boss is
gone and portal 563 stands), `acts_baal_portal` (the `baal` stage enters 132 through that portal by mouse click when the waves
were done in the run), asked-only stage `mephmelee`, `line_blocked`, `ACTS_END_PLUS_SKILLS` (+10 all skills, stat 127, on the
given amulet for diablo / throne / baal: the level 80-98 build died 3-6 times per try without it; named in every row), Diablo
at level 90. Test `tools/test_game_checks_endgame.py`.

**Diablo.** Cause of acts5's "no Diablo": the walk, not the port. 1.13c's rule (D2MOO `A4Q2.cpp`, the 1.13c reimplementation):
the five seals (objects 392-396) opened AND the three seal bosses killed start `ACT4Q2_KillAllMonstersInCS` and a timer that
spawns Diablo at the start point object 255 once that object's room is loaded (`OBJECTS_InitFunction55_DiabloStartPoint` re-arms
the timer when the star loads later). acts5's character never got back to the star, so the star's room never loaded. With the
planned walk legs the character reached the star, and Diablo (class 243, 22,302,720/256 = 87,120 life) spawned there every time
all five seals were open and the bosses dead (4 of 4 runs). Run `-051628-s3` opened 4 seals (394 not found) and skipped De Seis:
no Diablo, as the rule says (its star walk got there, 7794,5292). Quest 26 goes 0000 -> 0001 after the seals. **Diablo killed on
the player path in `checks-20261030-062933-s3`** (all five seals by mouse click, 0 deaths on the seal walk and in the fight, 80 s of fight, Frigid Sphere /
Arcane Torrent right clicks with the +10 amulet; he started that fight at 7,176,018 of 22,302,720, worn down by the seal fight
clicks before he was focused), **quest 26 `0001000000000000` -> `1000000000000100`**, and again `1000000000000000` in a new game.

**Act 5 travel.** Tyrael (367) keeps Talk (d35) only after the kill, also in a new game (`checks-20261030-075529-s3`,
`acts_travel45.png`: the drawn menu is TALK / CANCEL). That is LoD: Tyrael has no travel line; after Diablo's death he opens a red
portal beside him (objects.txt 566 `NotKiddingLastPortal`, name "Harrogath", OperateFn 73), seen in that screenshot. travel45
looked for a menu line (as Warriv / Meshif); it now clicks that portal. **`checks-20261030-075910-s3`: travel45 PASS, one
background mouse click on portal 566 at 5024,5021 -> Harrogath (109, 5098,5023)** (the screenshot of that run fell on the loading
screen; the stage now waits for it).

**Throne and Baal.** `checks-20261030-030049-s2`: **all five wave bosses came and died** (1289 seen at 279 s, gone 315; 1148
328/665; 803 816/825; 1290 837/877; 1281 889/942), portal 563 at 15090,5005 stood, and **a background mouse click 40 px above its
foot took the character into the Worldstone Chamber (132)**: the player's way in works. 2 deaths (revived, back to the throne).
The chamber's minions then killed the character on the walk up to Baal (not counted then; fixed). `checks-20261030-055011-s2`:
**Baal (class 544, 31,897,600/256 = 124,600 life) killed in 322 s with 2 deaths, quest 40 0000000000000000 -> 1000000000000100**
(entry by harness travel `level 132`: that run's throne stage failed). Runs `-022246-s2`, `-023604-s2` and `-041902-s2` entered
132 the same way and quest 40 stayed 0000000000000000 without a kill, so nmhell3's "harness travel sets quest 40" did not
reproduce here. Waves and Baal kill in one run: not achieved (6 tries died 3-6 times in the waves; the build is the limit: wave
bosses, Baal and his minions all took damage and died as expected).

**Mephisto's moat.** `checks-20261030-052336-s4` (`mephmelee`, Sorceress with the acts axe, 1000-2000 damage, Attack by left
clicks): the walk towards him died on the council; `place` on the free spot nearest to him put the character at 17576,8076, 2
cells from Mephisto (17574,8077) with no blocked walk cell on the line: **13 clicks took his life 52,984 -> 46,569** (his mode 4).
So the port lands melee on Mephisto when the attacker stands within reach. nmhell3's "never hits from the moat edge" is the 1.13c
behaviour: a player's melee attack first walks to the target on the walk collision, and the lava moat has no path, so from across
the moat the swing never starts (the "moat trick" is why ranged attacks are used there). Same in 1.14d and D2R; **not a port
bug**, no row filed. Not done: a swing from the far moat edge itself (the walk died before it got there).

**Load notes** (`acts_load_note`: fps from the client's frame counter, missile ids/s from the server's id counter, live server
missiles, private memory of the game process; no Mephisto fight with sampling in this lane, see lanes acts5 / nmhell3):

| Boss | Run | Time | Deaths | fps median (min) | missile ids/s median (max) | live missiles median (max) | private MB start -> end (max) |
|---|---|---|---|---|---|---|---|
| Diablo (seals + fight) | `checks-20261029-234838-s2` | 3959 s | 1 | 25.0 (18.4) | 22.7 (547) | 11 (179) | 9345 -> 9657 (10105) |
| Diablo (seals + fight) | `checks-20261030-034855-s3` | 4746 s | 3 | 25.0 (24.5) | 36.6 (564) | 11 (301) | 9344 -> 9850 (10301) |
| Diablo (seals + fight, killed) | `checks-20261030-062933-s3` | 4929 s | 0 | 25.0 (24.5) | 21.9 (471) | 14 (285) | 8740 -> 8979 (9146) |
| Throne, five waves | `checks-20261030-030049-s2` | 976 s | 2 | 25.0 (24.6) | 138.3 (1615) | 58 (656) | 9084 -> 9433 (9806) |
| Baal (killed) | `checks-20261030-055011-s2` | 467 s | 2 | 25.0 (24.5) | 85.7 (221) | 17 (90) | 9590 -> 9821 (9970) |

No crash. Engine asserts: #394 (`ptCreate->hSource`, known, not a bug) in the Diablo runs `-234838-s2`, `-034855-s3` and `-062933-s3`; the
exit-only pool asserts when `game_ctl.stop()` closes the game (`m_allocated == 0` and the others of the table above, plus
`m_assets.empty()` and `!IsAnyInstanceAnimationLoading()` in `-052336-s4`, all after the last check). The crash file listed in
`-052336-s4` is dated 2026-10-29 20:23 UTC, before the run (an older file of slot 4).

| Run | Stages | Result |
|---|---|---|
| `checks-20261029-234838-s2` | diablo, travel45 | seals 392-396 0 -> 2 by click, Diablo at 7793,5293; the character was held 54 away at the north corridor wall, unit lost; 1 death. travel45 FAIL |
| `checks-20261030-011048-s2` | diablo, travel45 | all seals by click, Diablo at 7793,5288; his pack drove the character off, unit lost; 3 deaths. travel45 FAIL |
| `checks-20261030-022246-s2` | throne, baal | level 80: died on the throne route; baal by harness travel, not killed, quest 40 unchanged |
| `checks-20261030-023604-s2` | throne, baal | 6 deaths: the given gear stayed on the corpse (life 15787 -> 4027); fixed (gear again after a revive) |
| `checks-20261030-030049-s2` | throne, baal | **throne PASS (five waves, portal 563)**, **132 entered by a mouse click on the portal**; Baal not reached (death on the walk, not retried; fixed) |
| `checks-20261030-032352-s2`, `-034828-s2`, `-041902-s2`, `-051628-s2`, `-061108-s2` | throne, baal | throne FAIL: 3-6 deaths, 2-4 of 5 waves gone in the time. `-034828-s2` timed out with the fifth wave alive (its portal click then took nobody), `-051628-s2` read Baal "gone" with 3 waves to come (both fixed in the pass rule). `-061108-s2`: Baal by harness travel down to 14,807,136 of 31,897,600, 5 deaths |
| `checks-20261030-034855-s3` | build, diablo, travel45 | Diablo spawned (all seals by click), down to 7,872,131 of 22,302,720 after 2 retries, 3 deaths; then not found. travel45 FAIL |
| `checks-20261030-051628-s3` | diablo, travel45 | 4 seals (394 not found), De Seis skipped: no Diablo (the rule). travel45 FAIL |
| `checks-20261030-051628-s4` | mephmelee (Barbarian) | life 2450 (the given ring did not lift it); died on the walk. Set-up problem, not judged |
| `checks-20261030-052336-s4` | build, mephmelee | melee hits from 2 cells (52,984 -> 46,569); see above |
| `checks-20261030-055011-s2` | throne, baal | throne FAIL (1 wave, the walk back failed); **Baal killed, quest 40 set** (harness travel in) |
| `checks-20261030-062933-s3` | diablo, travel45 | **Diablo killed** (all seals by click, 80 s, 0 deaths in the fight), quest 26 -> `1000000000000100`; travel45 FAIL (menu only: no line on Tyrael, see above) |
| `checks-20261030-075529-s3` | travel45 | new game: quest 26 still done, Tyrael Talk / Cancel only; red portal by him on the screenshot |
| `checks-20261030-075910-s3` | travel45 | **PASS: portal 566 by a mouse click -> Harrogath** |

## Lane fxleft: the last 3 overlay picks of #507, the boss / soldier subtitles of #508 (2026-10-30, slot 4, background mode, build of lane/fxleft, plugin `build_plugin.ps1 -Release`)

Lab scripts in `mxl2012-runs/fxleft/` (kept outside the repo, made from lane fxpick's `fxlab2.py`):
`MXL_RUN=fxleft MXL_SLOT=4 py -3 lab.py <worktree> <out> [modes] [groups]` on a new Necromancer "FxlNecroman" in the Blood Moor; per entry
a burst of shots (`burst()`: PrintWindow frames kept in memory, about 30 a second, saved afterwards); `sheet.py` makes crop sheets.
Groups: `bts` Bend the Shadows (486) at a Death's Fury totem (488) by a background right click (`click_unit`; legacy: 24 / 12 px per
sub-tile round 800, 450) and by harness `cast`; `slow` `mcast` of SpiderLay 173 (Arach 122, mode 7) and Vine Attack 234 (plague poppy
425, mode 10) on the player; `slowv` `cast 664 self` with `slowvariant.py` applied; `vo` / `vo2` / `vo3` the #508 sounds (harness casts,
harness missiles, click casts). Slot-only table variants (`slowvariant.py`, `vovariant.py`: backup, edit, restore, md5 compared with the
build afterwards, all equal) were on the slot only for runs `r2`-`r4`. `vo3` runs without `debug_mode` and god mode.

| run | groups | result |
|---|---|---|
| `r1` | HD: bts, slow, vo | Bend the Shadows: click cast PASS, `willowispdeath` wisps rise from the head 0 to about 270 ms (`zoom_bts_hd_0.png`); harness cast: warp, no overlay. `slowed`: both monsters start their skill 7 times in 12 s, the state never lands (server and client). vo: no chat line (harness casts and missiles, see `r4`) |
| `r2` | HD + legacy: bts, slowv, vo2 | Bend the Shadows HD click PASS again. `slowed` HD PASS: blue tint, `ice_cast_1` ring at 400-700 ms, then the `shrine_resist_cold` snowflake over the head, still there at 2 s and 4.5 s (`sheet_slowv_hd_0.png`, `slowv_late_hd_legacy.png`). Legacy part unusable (summons of the vo2 casts filled the screen) |
| `r3` | legacy: bts, slowv | Bend the Shadows legacy click: Median's white floating skull 0 to about 320 ms (`zoom_bts_legacy_0.png`); `slowed` legacy: blue tint, cast flash, looping blue arcs (`sheet_slowv_legacy_0.png`) |
| `r4` | HD: vo3 (with `vovariant.py`) | Controls: state onsound `pal_goodbye` -> "FxlNecroman says: Goodbye.", `baallaugh1` -> "Baal says: \*Laughing\*", `sol_helpus` -> "Soldier says: Help us!"; skill stsound `nec_goodbye`: harness cast no line, click cast the line. Build rows: click Spawn Edyrem "Baal says: \*Laughing\*" + "Soldier says: Over here!" (2 of 2), Belial Volcano the laugh (1 of 2), Mon Deathswarm none (2); harness casts and harness missiles (850, 2189) none. Chat log only, no overhead text (`sheet_chat_a.png`, `sheet_chat_b.png`, `full_click998.png`, scan `chat_scan.json`) |

Summary sheet: `mxl2012-runs/fxleft/sheet_507.png`. Lessons: a cast overlay can last under 0.3 s (use bursts); the harness `cast`
draws no skill cast overlay and plays no skill start sound on the client (click the skill to see / hear the player's view); no lab path
made `slowed` land from its two monster skills. bugs.md #507 (closed) and #508 (options for the owner) have the details.

## Lane regress013: regression pass of main e8d4422 before 0.1.3 (2026-10-30, slot 3, background mode, build of lane/regress013 = main)

Build: `tools/build.py` (validate 0 errors), `tools/build_plugin.ps1 -Release` (dev DLL installed by `install_mod.py --slot 3`:
`mxl2012-core 0.1.2 (dev)`, 30 `mxl2012` lines, `appleuse` / `spiritsound` / `petspread` on). Slot 3 held about 02:03-03:40, then
unlocked. The real-input watchdog stayed clean on every check run (cursor did not move, 0 aborts). Evidence is in
`mxl2012-runs/regress013/`: check runs `checks-*`, logs `run*.log` / `session*.log`, scratch drivers `drv.py`, `r_cls.py`,
`r_rat.py`, `r_stash.py`, `r_tp.py`, `qm.py` (not committed).

| # | What | Result | Evidence |
|---|---|---|---|
| 1 | New character of each of the 7 classic classes enters Act 1 (`RgAma`, `RgSor`, `RgNec`, `RgPal`, `RgBar`, `RgDru`, `RgAss`); skill bar and the 3 tree tabs in HD and legacy (G) | **PASS**: 0 asserts per class (`engine_issues` since each entry, harness `asserttrace` on), 0 crash files; all trees show Median's icons, skill bar drawn in both modes | `checks-20261030-022516-s3/rg_<cls>_<mode>_{bar,tree1-3}.png`, `sheet_classes_hd.png`, `sheet_classes_legacy.png`, `session.log` |
| 2a | Raid (#501): Blink charges, `snd_blink` | **PARTIAL (pass)**: 12 right clicks per mode, the player moved, `baal_teleport` 6 / `druid_shockwave` 6 per mode, the game alive, 0 asserts | `checks-20261030-021307-s3`, `runB.log` |
| 2b | Spirit summons (#502), `snd_spirits` with `MXL_SOUND_TRACE` | **PASS**: HD 11 `ancient_death_hd` requests, all skipped by `spiritsound`, 0 played; legacy none. The first two runs FAILED as a test fault: the check's new `SndBarb` is level 1 (spirit skill points refused, 5 mana). The check now runs under `Tank()` + `Level(120)` | `checks-20261030-022248-s3`, `runB3.log`, `soundtrace3.txt`; the failed ones `runB.log`, `runB2.log` |
| 3a | Totems + Bend the Shadows, `totem_spread` (Median's totems and Bend the Shadows are **Necromancer** skills, not Druid) | **1 FAIL in 3 runs, NEW bug #509**: run 1 had 4 totems onto the owner but only 3 spread, and one totem (class 1080) stayed on the player's sub-tile. Runs 2 and 3 (same character, same spot) were PARTIAL (pass) with 4 of 4 spread. No slowdown was measured here. HD shots show spires only, no orb left at the cast spots (#500 holds) | `checks-20261030-020328-s3/totem_spread_after.png` (fail), `checks-20261030-021007-s3`, `checks-20261030-021114-s3` |
| 3b | Other pets keep D2R's placement, `pet_keep` (Kashya mercenary + Summon Shadows; Median 2012 gives the Druid no wolves) | **PARTIAL (pass)**: Bend the Shadows "onto the owner +2, spread +0, other pets left +2"; waypoint to Cold Plains "+4 / +0 / +4", mercenary came along | `checks-20261030-020328-s3/pet_keep_*.png` |
| 4 | Apple (#499), `apple_use` / `apple_save` | **PASS**: bought from Charsi, right-click used up, state 44 on with 14889 frames left, the five stats as designed, hpregen 0 -> 6; after Save and Exit the Apple stays gone, state off | `checks-20261030-021307-s3`, `runB.log` |
| 5 | Druid quill morph (Trap Rat Form 448) idle, #504 | **PARTIAL**. The morph could not be put on: 448 needs a knife-type weapon (skills.txt `itypea1 knif`), and the harness `equip 145` / `equip 142 rhand` refused even with the right hand empty, so the cast is refused ("I can't."). Without the morph: a new Druid idled 60 s HD + 40 s legacy, and Vanquish 678 (a #504 voice source) was cast in both modes. No "says: Goodbye." line appeared in any shot | `checks-20261030-033526-s3/rat_*.png`, `sheet_rat_chat.png`, `session5.log` |
| 6 | Stash quick move (Ctrl-click), personal tab, HD | **PASS** for rune, chipped gem, scroll, magic ring, rare amulet, Field Plate (2x3): each went into the stash. Legacy: not done (the walk-to-stash helper clicks HD screen spots; lane uifix covered legacy and the code did not change). The `cm1` attempt raised `BC_ASSERT: bWidth > 0 && bHeight > 0` (Inventory.cpp:1668) in harness `item`: cm1/cm2/cm3 are retired rows in Median (misc.txt invwidth/invheight 0, type hpot), so this is a test artefact, not a player path | `checks-20261030-022516-s3/st_hd_open.png`, `st_hd_after.png`, `stash_qm.json` |
| 7 | Median maps in HD, `wall_maps` with `MXL_WALL_LEVELS=60,95,126` (desertpeak, glados, borgir) | **PASS by eye** (check PARTIAL: judged by hand): walls drawn in HD where classic has them, nothing floating, 0 asserts | `checks-20261030-020328-s3/wall_<map>_{hd,classic}_*.png` |
| 8 | Waypoint, town portal, Save and Exit, reload (Druid `RgRatKnife`) | **PASS**: Rogue Encampment waypoint -> Cold Plains by clicks, a Scroll of Town Portal by right click opened a portal, walked into it back to area 1, Save and Exit, reloaded in area 1 with the same 23 items | `checks-20261030-032913-s3/tp_*.png`, `session4.log` |

Engine: across all runs, 0 new crash files and no unknown assert on a player path. The only asserts were the harness `cm1` one
above and the shutdown pool asserts (`s_StatsPool.IsEmpty()`, `m_allocated == 0`) of the same session at game exit, after it.
Tests: `unittest` tools/tests 810 OK, tools `test_*.py` 427 OK (1 skipped), `check_docs_links` 0, `check_public` 0.

## Lane unporteda: the class (a) rows of docs/unported.md and the owner's 2026-10-29 answers (2026-10-30, slot 3, background mode, build of lane/unporteda)

The 12 class (a) rows of docs/unported.md are closed (moved to its "Closed rows" with evidence), together with the three owner answers
of 2026-10-29: Whirlwind keeps the plugin's classic hit rate per spin (plugin-plan.md; the feel stays on the final human visual
review list), `cougar` is dropped (`txt_migrate.py` DROPPED_MONSTERS switches the row off in place, the ids after it keep their
numbers), and missing missile / overlay art draws nothing only on the 9 rows no player or monster skill uses (`art_fix.py`
DRAW_NOTHING; the 13 used rows keep a similar stand-in, list in hd-effects.md section 5). Closed without a game: Warlock Cleave /
Mirrored Blades flat damage (a static read of functions 164 / 166: both add `calc2`; the RotW playtest stays for the numbers), the
D2R-native helper Ids (disabled rows, bugs.md #70), text outside the tables (`text_audit.py` kind `text-words`, docs/text-audit.md).
Evidence: `mxl2012-runs/unporteda/evidence/` (run folders), contact sheets `ua_mons_*_sheet.png`, `ua_horned_sheet.png`. Unit
tests: `tools/test_game_checks_unporteda.py`, `tools/tests/test_missile_chains.py` (DroppedMonsterTests), `tools/tests/test_text_audit.py`
(TextWords).

**`ua_look`** (tools/game_checks.py): `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<throwaway> py -3 tools/game_checks.py all ua_look`
(`MXL_UA` picks stages from `mons horned ui item maps drop`; `MXL_UA_MODES` default `hd,legacy`, `MXL_UA_ONLY` one monster).
SET-UP: god mode, the harness travels, spawns and makes items, so PARTIAL at best; looks are judged by hand on the `ua_*` shots.
`drop` is its own result `ua_drop` (the cougar row's spawn makes no unit; D2R's one `MONFLAG_ENABLED` assert is the expected answer).

| Run | Result |
|---|---|
| `checks-20261030-010359-s3` (all stages) | mons PARTIAL: quest_butcher / super_kabraxis (ogre / megademon in HD), sarandesh1, psychorbM spawned, 0 asserts; the classic shots were crowded by the HD round's corpses (rerun alone below). `ua_drop` PASS (row 1770 enabled 0, no unit). ui: classic weapon swap tabs on both arm slots, classic skill tree with Median's labels only. maps: charismatic's objects (chests, stash, shrine, baskets, pillars); automap of excelsior3 drawn, desertpeak blank (as 1.13c: Act 3 wall tiles on the Act 2 tomb level type). item: the check called a harness verb that does not exist (`itemdesc`), fixed below; the shots show both automagic lines |
| `-011444` ... `-011937-s3` (classic, one monster each) | sarandesh1, psychorbM (death included), quest_butcher, super_kabraxis draw Median's art, fight and die; 0 asserts, no crash file. hornedgods alone: nothing (it dies at its first tick, bugs.md #41) |
| `-012558-s3` (horned, item, maps) | item PASS: 7@5 strength_bonus_wpn 76 + socket, 614 no socket (group 401 has a row with and one without the socket per pattern) |
| `-013028-s3`, `-013441-s3` (horned) | hornedgods beside enemies (class 1, lane fixes2's recipe) lives in mode 1 in both modes (`mon id=24 class=1715 mode=1`), drawn in neither: its monprop `fade` hides it; nothing on the player path spawns it. PARTIAL (pass) |

Not run: the RotW playtest for the Warlock numbers (no slot account owns RotW).

## Lane baallol: "Baal says: LOL" at most once every 30 s (bug #508, 2026-10-30, slot 4, background mode, build of lane/baallol, plugin `build_plugin.ps1 -Release`)

Lab script in `mxl2012-runs/baallol/` (kept outside the repo, made from lane fxleft's `lab.py`):
`MXL_RUN=baallol MXL_SLOT=4 MXL_SOUND_TRACE=<file> py -3 lab.py <worktree> <out> [modes] [groups]` on a new Necromancer "BlolNecro" in
the Blood Moor, debug mode and god mode. Groups: `click` Spawn Edyrem (998) by a background right click next to the player at 0, 6,
12, 18, 24, 32 and 38 s, two shots per cast (0.8 s and 2.5 s after); `master` a `dark_master1` (class 1294) next to the player for
45 s, a shot every 3 s. Before and after each group: the `vochat` line of `mxl2012` (lines printed / left out) and the sound trace
of sounds rows 4631 / 10239 (the two rows with the file `baallaugh1`). `sheet.py` makes chat crop sheets.

| run | groups | result |
|---|---|---|
| `r1` | HD: click, master; legacy: click | HD click: "Baal says: LOL" at 0 s, none at 6-32 s (24 s: "Soldier says: Over here!" alone), "Baal says: LOL" at 38 s; counters printed 2, left out 2; trace 4631 +4 (3 of the 7 casts played no laugh). HD master: 29 laughs (trace +29), 1 line printed (about 20 s in, 30 s after the click's last), 28 left out. Legacy (the `dark_master1` still casting): 51 laughs, 1 line (between 21 and 27 s), 50 left out. 0 asserts (`asserttrace`, d2rloader.log), no crash file; `mxl2012-core.log`: "vochat on" |

Evidence: `mxl2012-runs/baallol/sheet_click_hd.png`, `sheet_master_hd.png`, `sheet_click_legacy.png`, shots and `lab.json` in `r1/`,
`r1/sndtrace.txt`, `r1/d2rloader.log`, `r1/mxl2012-core.log`. Lessons: a chat line stays on screen about 10 s; a click cast of Spawn
Edyrem does not play the laugh every time; with a `dark_master1` near, "Soldier says: Over here!" fills the chat (one per summon).

## Lane itemart: the upscaled item pictures and the most-seen monster stand-ins (2026-10-30, slot 4, background mode, build of lane/itemart)

Picture ranking, candidates and review sheets: docs/hd-icons.md "Picture review" (owner rule: nothing switched on; the
candidates were tried only by copying their sprites over the slot's installed mod, `mxl2012-runs/itemart/trial.py`, which
backs up and restores the files with a sha256 manifest; 56 files verified after). Checks (new in `tools/game_checks.py`):
`itemart_pics` (Rainbow Stones, arcane crystals, signet, apple, clue gem, jewel, ring, amulet; and 20 runes: Median's next to
D2R's; HD and legacy inventory shots) and `itemart_mons` (`hm_monsters` over `ITEMART_MONSTERS`, docs/hd-monsters.md
section 16).

| run | what | result |
|---|---|---|
| `checks-20261030-112538-s4` | itemart_pics with `cm1` | FAIL: `cm1` is not made in Median and set off the engine assert `Inventory.cpp:1668`; removed from the set |
| `checks-20261030-112813-s4` | itemart_pics, candidates copied in | PARTIAL (shots only), 0 asserts |
| `checks-20261030-114557-s4` | itemart_pics, the build's pictures | PARTIAL, 0 asserts |
| `checks-20261030-115003-s4` | itemart_mons | BLOCKED: no `work/mod` tables in the worktree (copied from the slot's install, then rerun) |
| `checks-20261030-115135-s4` | itemart_mons, 13 rows HD + legacy | PARTIAL, 0 asserts, no crash |
| `checks-20261030-120008-s4` | itemart_mons, 8 rows HD | PARTIAL, 0 asserts, no crash |

HD: the Rainbow Stones change visibly, the crystals and runes a little; legacy pictures are the same before and after (only
`.sprite` files differ). Ring, amulet and jewel pictures differ between runs: D2R picks one of its pictures at random. Not
tested: the stash (the harness `item` verb places in inv / cube / ground only). Evidence: `mxl2012-runs/itemart/review/`
(`sheet_01.png` .. `sheet_05.png` and `_2x`, `ingame/before_*`, `after_*`, `compare_*`), `mxl2012-runs/itemart/monsters/`.

## Lane itemart2: the Rainbow Stones in D2R's HD gem pictures (2026-10-30, slot 4, background mode, build of lane/itemart2, data only)

Owner decision (2026-10-30): of lane itemart's 28 picture proposals only the five Rainbow Stones `og1`..`og5` are switched
on (D2R's HD sapphires in Median's colours by position); `item_hd` now makes the pictures of the proposals switched on
(docs/hd-icons.md "Picture review"). Build: `py -3 tools/build.py` (validate 0 errors; `picture proposals used: 5`;
item icon check 0 sprite problems), install `MXL_SLOT=4 MXL_RUN=itemart2 py -3 tools/install_mod.py --slot 4` (data only;
the installed `og4.sprite` is byte for byte the build's). Check: `MXL_RUN=itemart2 MXL_SLOT=4 MXL_CHAR=ItemArtTwo
MXL_ITEMART_SETS=rainbow py -3 tools/game_checks.py all itemart_pics` (new set `rainbow` in `ITEMART_SETS`: `yo1`..`yo5`
next to D2R's five sapphires and the perfect ruby, emerald, topaz, amethyst and diamond; `MXL_ITEMART_SETS` picks sets).

| run | what | result |
|---|---|---|
| `checks-20261030-131851-s4` | itemart_pics, set rainbow (15 items) | PARTIAL (shots judged by hand): all 15 made. HD: the five Rainbow Stones are D2R's crisp faceted gems of their cut in Median's rainbow colours, the same look as D2R's gems beside them; legacy (G): Median's classic pixel pictures, unchanged. No assert while playing; only the engine's exit-only pool asserts (`s_StatsPool.IsEmpty()` and its followers, table above: ignored); no crash file |

Not tested: the stash and the cube (same sprite). Unit tests: `tools/tests/test_itemart.py` `BuildProposalTests` (an
entry switched on is used, with the sheets' own render at HD and lowend size; an entry or a file switched off is not) and
`Og4AgainstTheReviewSheetTests` (the build's og4 found on lane itemart's `sheet_01.png`, max pixel difference 0; skipped
without the game files). Evidence: `mxl2012-runs/itemart2/ingame/checks-20261030-131851-s4/` (`itemart_rainbow_hd.png`,
`itemart_rainbow_legacy.png`), `ingame/rainbow_hd_vs_legacy_crop.png`, `og_built_strip.png` (og1..og5 HD and lowend as
built), `og<N>_hd.png` / `og<N>_lowend.png`.

## Lane walls3: the three maps with partial HD walls (2026-10-30, slot 2, background mode, build of lane/walls3, data only)

Build: `py -3 tools/build.py` (validate 0 errors), install `MXL_SLOT=2 MXL_RUN=walls3 py -3 tools/install_mod.py --slot 2` (data
only, no plugin change). Check (harness travel and god mode, new level-1 character WallsThree):
`MXL_RUN=walls3 MXL_SLOT=2 MXL_CHAR=WallsThree MXL_CACHE_POLL=3 MXL_WALL_LEVELS=15,65,127,95,18 py -3 tools/game_checks.py all
wall_maps`. The method (ground heights of raised D2R maps, generic walls for bare partial keys, pieces on no cell hung on the
rarest key next to them, the Arcane terrain mesh that did not work) is in docs/maps-hd.md items 9-12; tests in
`tools/tests/test_walls_hd.py` (GroundTest, AnchorTest, PartialFallbackTest, TerrainTest).

| run | maps | result |
|---|---|---|
| `checks-20261030-120504-s2` | caveroom4, belial, charismatic, glados, downtown (with the belial terrain mesh) | all 5 reached in HD and classic. caveroom4: the stairs at the arrival as in classic (absent before). charismatic: Fortress walls, gargoyle pillars and columns along classic's walls (before: a few pillars and walls floating off their cells); arches and roofs still missing. belial: unchanged, floor over the void. glados: more Travincal/Mesa walls, nothing out of place; downtown: no visible change. 0 ERROR/ASSERT lines in d2rloader.log, no crash file; VariantTransformTable peak 107/128, ModelAsset 1401/2750. Load screens HD 1.67 s (caveroom4; before 1.59), 2.15 (belial; 2.25), 2.24 (charismatic; 2.0), 3.02 (glados; 2.43), 1.81 (downtown; 2.03) |
| `checks-20261030-121037-s2` | belial, its installed scene patched with sancte's terrain physics body | still floor over the void, no assert: the terrain mesh is not used for this floor, so it is left out of the build (`TERRAIN_MAPS = {}`) |
| `checks-20261030-121747-s2` | caveroom4, belial, charismatic (the committed build) | as the first run; 0 asserts, no crash file, VariantTransformTable 101/128 |

Evidence: `mxl2012-runs/walls3/sheets/sheet_<map>.png` (before HD | after HD | legacy G; before = hdwalls2 run
`checks-20261030-005953-s1` for caveroom4 and belial, maptint `run2-checks-20261030-033400-s4` for the retextured maps),
`sheets_final/` for the last run, the run folders `run1-…`, `run2-…`, `run3-…` next to them. Open: belial's void (what paints
the HD floor of a level larger than its preset), charismatic's arches and roofs (no D2R model, custom art).

## Lane walls4: charismatic's arches and roofs, downtown's trees (2026-10-30, slot 3, background mode, build of lane/walls4, data only)

Build: `py -3 tools/build.py` (validate 0 errors), `tools/build_plugin.ps1 -Release` (plugin = main's), install
`MXL_SLOT=3 MXL_RUN=walls4 py -3 tools/install_mod.py --slot 3`. Check (harness travel and god mode, new level-1 character
WallsFour): `MXL_RUN=walls4 MXL_SLOT=3 MXL_CHAR=WallsFour MXL_CACHE_POLL=3 MXL_WALL_LEVELS=127,18,125 py -3 tools/game_checks.py
all wall_maps`. The method (trees on trunk tiles, look-alike tiles by silhouette, set pieces by the wall tiles under them;
D2R models only, owner rule) is in docs/maps-hd.md items 13-15; tests in `tools/tests/test_walls_hd.py` (LookalikeTest,
TreeTest, PieceTest). Slot 3 held about 16:30-17:58, then unlocked.

| run | maps | result |
|---|---|---|
| `checks-20261030-163728-s3` | charismatic, downtown (first build) | both reached in HD and classic; charismatic shows arches on gargoyle columns along the arcades. Exit-only pool asserts (`s_StatsPool.IsEmpty()` and followers, after the check), no crash file |
| `checks-20261030-164621-s3` | same spots in HD and classic (scratch driver, `place` in steps) | the Fortress hut with its slate roof where classic has the roofed building; downtown's trees where classic has them, but a wall block beside the 14/15/3 trees that classic does not have: fixed (a tree cell draws its tree only), rebuilt |
| `checks-20261030-173339-s3` | the same spots with main's scenes for both maps (HD before) | the before column of the sheets |
| `checks-20261030-174616-s3` | the same spots, final build, HD and classic | 0 ERROR/ASSERT lines, no crash file |
| `checks-20261030-175423-s3` | charismatic, downtown, macumba (final build) | all 3 reached in HD and classic; asserts per map: none; only the exit pool asserts after the check; no crash file; VariantTransformTable peak 94/128, ModelAsset 1350/2750 |

Evidence: `mxl2012-runs/walls4/sheets/sheet_charismatic.png` and `sheet_downtown.png` (legacy G | HD before, main 0.1.4 |
HD after, same spot per row), shots in `shots_before/`, `shots_after/`, `shots_after1/` (charismatic hut_10_4 after: the
same scene, the tree fix does not touch charismatic), the final run in `run-checks-20261030-175423-s3/`. Left: charismatic's
tall pointed arch and long roofed walls (no fitting D2R model), belial's void (not this lane).

## Lane runetab: runes into the stash's runes tab (bug #510, 2026-10-30, slot 3, background mode, build of lane/runetab)

Build: `tools/build.py` (validate 0 errors; `d2r_adds` line "AdvancedStashStackable of D2R on 71 rows by code and type, 71
cells set"), `tools/build_plugin.ps1 -Release -Tests` (plugin = main's), `install_mod.py --slot 3`. Slot 3 held about 12:01-12:38,
then unlocked. Scratch drivers (not committed): `mxl2012-runs/runetab/` (`drv.py`, `qm.py`, `r_lib.py`, `r_tab.py`, `r_tab2.py`,
`r_leg1.py`, `r_leg2.py`, `col.py`, `codes.py`), logs `session*.log`; evidence `mxl2012-runs/runetab/evidence/checks-*`.

**Cause (static).** D2R 3.3's runes / gems / materials tab is not a grid: D2R's `bankexpansionlayouthd.json` holds one
`AdvancedStashSlotWidget` per item code (91: 33 runes, 35 gems and skulls, `rvs` / `rvl`, `toa`, keys, organs, essences,
shards, Colossal materials), and D2R's misc.txt marks exactly those rows `AdvancedStashStackable` 1. The mod ships no stash
layout (D2R's is used) and its misc rows on those codes are the same items (same code, type, size), but the built column was
empty on every row: `txt_migrate.py` gives D2R-only columns the neutral default. So the tab took no rune at all, not only Ith.
The `advanced_stash` step of `tools/d2r_adds.py` now copies D2R's flag onto mod rows with the same code and type (71 rows, RotW
bank; D2R's base bank has none); unit test `test_advanced_stash_flag_from_d2r`.

**In game.** The slots' Battle.net account does not own Reign of the Warlock: the stash shows only Personal and Shared and the
character screen's Game Version offers only Expansion (`evidence/checks-20261030-120133-s3/t0_stash_hd.png`, pre-fix install),
so **the runes tab itself could not be opened here**. Checked instead that the flag changes nothing for the normal tabs
(new Sorceress `RuneTabbccb`, items made by harness `item`, moves by the player's clicks):

| What | Result | Evidence |
|---|---|---|
| HD personal tab, Ctrl-click: all 33 runes r01-r33, `gcv` `gpw` `skz` `gsb`, `rvs` `rvl`, `toa` | **PASS** 40 of 40 into the stash as 1x1 items (no stacking) | `checks-20261030-122132-s3/runetab_moves.json`, `t1_hd_personal.png` |
| HD personal tab, drag into free cells: Ith, Tal, Eth, `gcv`, `rvs`, `toa` | **PASS** 6 of 6 | `checks-20261030-122936-s3/runetab_moves2.json`, `u1_hd_personal_drag.png` |
| HD shared tab, Ctrl-click Ith, Eth, Zod, `gcv`, `rvs`, `toa`; drag Ith, Thul | **PASS** 8 of 8 | `u2_hd_shared.png`, `u5_hd_reloaded_shared.png` |
| Legacy (G with the stash open), personal: Ctrl-click Ith, El, Lem, `gpv`, `rvl`, `toa`; drag Ith, Zod, `skc` | **PASS** 9 of 9 | `checks-20261030-123600-s3/runetab_moves3.json`, `v1_legacy_stash_open.png`, `v2_legacy_personal.png` |
| Legacy, shared: Ctrl-click Ith, Sol; drag Ith | **PASS** 3 of 3 | `v3_legacy_shared.png` |
| Save and Exit, reload (three times) | **PASS** items identical (76, 86, 96) | `session2.log`, `session3.log`, `session6.log` |
| Engine | 0 asserts on the play path (only the known Save and Exit pool check), 0 crash files | the same logs |

Test faults on the way (not the game): D2R names take letters only (`RuneTab1211` was typed as `RuneTab`, taken); a drag onto an
occupied cell swapped items and left one on the cursor, which blocked the later moves of `r_tab.py` (redone in `r_tab2.py`);
`hdl_stash_open` clicks HD spots, so in legacy it picked a rune instead of opening the stash (redone: open in HD, then G).
Left behind: slot 3's shared stash page 1 holds 11 test items, `RuneTabbccb` in `mxl2012-s3`.

**For a RotW account (owner / user):** put Ith and a few other runes, gems and a rejuvenation potion into the runes / gems
tabs by drag and Ctrl-click; take them back out; Save and Exit.

## Lane totem509: one totem left on the player after Bend the Shadows (bug #509, 2026-10-30, slot 3, background mode)

Build: lane/totem509 from main 0.1.4, `tools/build.py` (validate 0 errors), `tools/build_plugin.ps1 -Release -Tests`, dev DLL
installed by `install_mod.py --slot 3` (slot 2 was taken by another lane when the build was ready). New Necromancer `Totemnec`.
`totem_spread` now blinks `MXL_TS_ROUNDS` times (default 6), each time by a right click onto the next totem, and fails a totem
within one sub-tile of the player or a `missed` count on the `petspread` line. The totems stand south-west of the Blood Moor
arrival, next to the rocks there. Evidence: `mxl2012-runs/totem509/` (run folders, `run1.log`..`run3.log`, `petspread-tries.log`).

| Run | Build | Blinks | Result |
|---|---|---|---|
| `checks-20261030-155003-s3` | first try: a move kept wherever D2R's search landed it (`Keep`), plus the try log | 6 | **FAIL (bug reproduced)**: blinks 4 and 5 left the fourth totem at +1,-1 from the player; "missed 2". Its tries: the spot test refused every free spot at 5 and 7 sub-tiles and most at 3, the 3-ring spots left were next to placed totems, and the move turned the one spot let through (+3,-3) into +1,-1 |
| `checks-20261030-155355-s3` | fix: pass 2 (move to every ring spot not taken, keep by `Keep`) | 10 | **PARTIAL (pass)**: 4 of 4 spread after every blink, none within one sub-tile of the player; "spread 40, shifted 2, pass 2 0, missed 0" |
| `checks-20261030-155548-s3` | the same | 20 | **PARTIAL (pass)**: 4 of 4 spread after every blink; "spread 80, pass 2 3, missed 0". Pass 2 placed the fourth totem at -3,0, +2,0 and +3,0 at the spots of run 1's misses; -3,0 and +3,0 had been refused by the spot test and the move put the totem exactly there |

Not on the player path: skill levels, level 120, Tank, the corpses (spawned zombies) and the totems cast by `cast` (as in
"Lane totems"). Engine log: only the known shutdown pool asserts at game exit, no crash file, real-input watchdog clean in every run.

By hand:
1. Cast four totems next to rocks or a wall, then Bend the Shadows onto one of them, several times.
2. After every blink the totems stand round you and none is on you.

## Lane uppass: into the Underground Passage with a mercenary (bugs #511 / #292, 2026-10-30, slot 4, background mode, build of lane/uppass on main 0.1.4, plugin `build_plugin.ps1 -Release -Tests`)

Check `uppass` (game_checks.py). Paladin "UpPass" (Normal). The Rogue Scout (class 271) is hired from Kashya (fixture quest bit and
gold) and given Cap, Quilted Armor and Short Battle Bow by clicks on the hireling panel. The player gets god mode and the
mercenary 20,000 life (SET-UP: the walks are not cut short by deaths). The graphics come from `MXL_UP_GRAPHICS` (default
legacy, the player's). Each try: travel to the source area (harness `level`); `level <dest> warp` (SET-UP: next to the link);
walk OUT through the link tile by background clicks; then walk back IN by clicks (the entry that is judged). After 8 s, the check
looks at: the game alive, the area, the mercenary near (the `state` list, server units within 40, mode 0/12 left out), engine
asserts and crash files of the try. At the end: back to the Rogue Encampment (mercenary mode, a shot) and the `reassign` line of
`mxl2012`. Routes come from `MXL_UP_ROUTES` (4-10 Stony Field to Level 1, 10-14 Level 1 to Level 2; 5-10 Dark Wood: its SET-UP
warp lands at the Stony Field side, so not used), with `MXL_UP_ROUNDS` rounds and `MXL_UP_FILL` items. Guard off with
`MXL_CONTROL=reassign`.

| run | guard | graphics | result |
|---|---|---|---|
| `checks-20261030-152733-s4` | off (control) | legacy | 4->10 entered. 10->14: the game closed 23 s after the server warp: `BC_ASSERT: 0` "Could not get act!" (SCmd.cpp:1254), then the object_pool / CommandSystem exit asserts. Crash file RIP 0x141255802, a write to 0: the player's crash, #292's |
| `checks-20261030-153516-s4` | first version (checks the room at x, y before D2R's move; never fired) | legacy | Round 1 both entered. Round 2: the game closed after 10->14, at the harness `level 4`, with the same assert and RIP. The room at the target was there before the move, and the unit had none after it. So the guard was moved to D2R's own no-room branch |
| `checks-20261030-154943-s4` | on | legacy | **8 of 8 entries (4 rounds 4->10, 10->14), game alive, 0 asserts, 0 crash files.** 11 reassigns left the Rogue (type 1, class 271) without a client room. Each time, D2R would have ended the game: to 7877,8020 (Level 1's entrance from Stony Field), 5193,5027 (Stony Field's cave), 8051,8294 / 7528,13142 (Level 1 <-> Level 2). They fell on the walk-through clicks (4->10, 10->4, 10->14, 14->10) and on one harness warp. 53 commands, 0 for the player |
| `checks-20261030-155820-s4` | on | HD | 4 of 4 entries (2 rounds), game alive, 0 crash files, 5 units left without a room. In town after the rounds, the Rogue stands by the player on screen (`uppass_town_after.png`) |
| `checks-20261030-160348-s4` | off (control) | legacy | Round 1 both entered, round 2 4->10 entered. 10->14: the game closed 15 s after the server warp, the same assert chain, RIP 0x141255802 |
| `checks-20261030-161142-s4` | on, first start (`d2rloader\data\compiler` moved aside, put back after) | legacy | 2 of 2 entries (1 round), game alive, 0 crash files. Sounds table 11913 rows (crash-audit C17, as in the player's log), so `soundguard` skipped Median's sounds. 1 reassign caught: the Rogue sent to the town spot 5653,5523 on the harness travel back to the Rogue Encampment |

With the guard off, 3 of 3 runs closed the game within 5 tries (today's main = 0.1.4 plugin plus nothing that touches this
path). With it on, 0 of 3 runs (14 entries, 17 reassigns caught) closed. The mercenary's server mode is 12 after the first round in every run,
guard or not (in `-153516-s4` before any guard fired). `state` then leaves it out ("not in view"), but the client
draws it next to the player.

Evidence: `mxl2012-runs/uppass/evidence/run2-control/` (crash report, d2rloader.log), `evidence/run3/`, `evidence/run6-control/`.
The run logs are `run2.log` to `run7.log`. Lesson: `graphics_mode` reads "legacy" in the dark caves in HD as well (the round-1
row of the HD run); the town reading counts.

## Lane itemart3: D2R HD pictures of the same kind for the upscaled items, for the owner's review (2026-10-30, no game run)

No game run: every new proposal is **off** (owner rule: the owner sees the art first), so a build or an install shows
nothing new; slots 3 and 4 were busy with other lanes. What was checked instead:

| check | result |
|---|---|
| `py -3 -I tools/item_art_review.py sheets ../mxl2012-runs/itemart3/review --lane itemart3` | 9 sheets (+ `_2x`), 66 proposals best first: Median classic, current HD upscale, proposal, proposal at 1920 x 1080 (49 px per cell) |
| every itemart3 entry through `item_art_sheets.candidate` at HD (98) and lowend (49) cell size, as the build would call it if switched on | 132 pictures, none empty |
| `py -3 -I tools/hd_icons.py build` | unchanged: `picture proposals used: 5` (og1..og5), item icon check 0 sprite problems; `item_hd_report.json` lists 76 proposals, 5 ON |
| `tools/tests/test_itemart.py` | 28 tests OK (5 new: `RuneStoneTests` x3, the 66 entries off and in pick order, the 4-column sheet) |

In game once the owner switches some on: the same check as lane itemart2 (`itemart_pics` with a set of the switched-on items,
HD and legacy), and the stash/cube once. Evidence and scratch: `mxl2012-runs/itemart3/` (`review/sheet_01..09.png`,
`rank.txt`, `median_all.png` (all 92 upscaled pictures), `d2r_lib_1..4.png` (all 444 D2R HD item sprites), `explore/`
(the candidates tried, by-position and mean colour side by side)).

**Round 2 (owner verdict, 2026-10-30): 59 switched on, slot 1, background mode, build of lane/itemart3 (data only, the
slot's own plugin).** All itemart3 proposals except the seven signets are on (docs/hd-icons.md "D2R HD art of the same kind").
Build `py -3 tools/build.py`: validate 0 errors; item icon check 0 sprite problems (the proposal sprites now checked pixel for
pixel against their approved candidate: `item_icon_check.check_proposal_sprite`). Install `MXL_SLOT=1 MXL_RUN=itemart3 py -3
tools/install_mod.py --slot 1` (data only, 3387 files). Check: `MXL_RUN=itemart3 MXL_SLOT=1 MXL_CHAR=ItemArtThree
MXL_ITEMART_SETS=itemart3a,itemart3b py -3 tools/game_checks.py all itemart_pics` (new sets in `ITEMART_SETS`: `itemart3a` =
Horadric Malus, Scepter, Jolly Roger, Tome of the Spider (scroll pair), Token of Absolution, Sunless Crystal Bird, Fool's Gold,
Boss Junket, Scroll of Kings, Shadowfang, I Am Rich, Multi Shards, Amazon Class Reward; `itemart3b` = the four Sunstones,
Ingredient Rings 1, 2, 5, Oils of Duplication / Renewal / Absolution, runes Lah, Kur (fine glyphs), Thur, Nas, Kra, Rha, clue
gems 01-, 35-, 27-, 20-).

| run | what | result |
|---|---|---|
| `checks-20261030-161712-s1` | itemart_pics, sets itemart3a (13 items) and itemart3b (20 items) | PARTIAL (shots judged by hand; the check's FAIL is the engine line below): all 33 made. HD: every item shows its new D2R picture (the Malus, the gold scepter with its red crown, the skull, the bird, Shadowfang, the gems, the soul-stone shard, the coins, the parchments, the green flask, the scroll pair; the runes on D2R's stone with Median's signs, the oils as round flasks, the Sunstones as round-cut gems, the rings, the clue gems); legacy (G): Median's classic pictures, unchanged. Engine: `wPrefix != 0 \|\| wSuffix != 0` once, on the harness's `item hdm` (the generator made the Malus quality 7): harness artifact, bug #35; the exit-only pool asserts (`s_StatsPool.IsEmpty()` and its followers): ignored as before. 0 crash files; the real-input watchdog saw no user input |

Not tested in game: the signets (off), the stash and the cube (same sprite). Evidence: `mxl2012-runs/itemart3/ingame/
checks-20261030-161712-s1/` (`itemart_itemart3a_hd.png`, `_legacy.png`, `itemart_itemart3b_hd.png`, `_legacy.png`). Signets,
second try (off): `mxl2012-runs/itemart3/review-signets/sheet_01.png`. Unit tests: `test_itemart.py` 30 OK (new:
`SealTests`, `check_proposal_sprite` against a matching and a wrong sprite, 59 on / signets off).

**Round 3 (owner verdict, 2026-10-30; no game run): the 23 runes off, the rune and signet signs redrawn, two retints.** The
runes are off again (too blobby); every rune and signet sign is redrawn as strokes (`tools/item_glyphs.py`) and chiselled in
crisp (off, for review); the Sunstone of Thunder is retinted yellow and the Oil of Jewelcraft pink (on). Build
`py -3 tools/build.py`: validate 0 errors; item icon check 0 sprite problems (the 82 proposal sprites, 41 pictures in HD and
lowend, equal to their candidates); `hd_icons` "picture proposals used: 41". Unit tests: `test_itemart.py` 37 OK (new:
`ChiselTests`: every sign well formed and inside its picture, the signed distance, the chisel's dark floor / lit far wall /
shadowed near wall / hard edge, `engrave_rune`, the seal with strokes, `tint`, `_round2`). Review sheets
(`py -3 -I tools/item_art_review.py sheets mxl2012-runs/itemart3/review-r3 --round3`): `mxl2012-runs/itemart3/review-r3/
sheet_01..04.png` (+ `_2x`) and `overview_2x.png`. The retints were not looked at in game (same sprite path as round 2's
run).

**Round 4 (owner verdict, 2026-10-30: "the new ones look great, ship em"): the 23 runes and 7 signets on, slot 1, background
mode, build of lane/itemart3 (data only).** Build `py -3 tools/build.py`: validate 0 errors; item icon check 0 sprite problems
(228 sprites; the 142 proposal sprites, 71 pictures in HD and lowend, equal to their candidates); `item_hd_report.json`
`proposal_on` 71. Install `MXL_SLOT=1 MXL_RUN=itemart3 py -3 tools/install_mod.py --slot 1` (data only, 3387 files). Check:
`MXL_RUN=itemart3 MXL_SLOT=1 MXL_CHAR=ItemArtFour MXL_ITEMART_SETS=itemart4a,itemart4b py -3 tools/game_checks.py all
itemart_pics` (new sets: `itemart4a` = the 23 runes `r34`..`r56`; `itemart4b` = the seven signets, the Sunstone of Thunder
`x3x`, the Oil of Jewelcraft `7o^`).

| run | what | result |
|---|---|---|
| `checks-20261030-174311-s1` | itemart_pics, sets itemart4a (23 items) and itemart4b (9 items) | PARTIAL (shots judged by hand; the check's FAIL is the engine line below): all 32 made. HD: the 23 runes on D2R's stone with sharp, chiselled signs (Thur a 3, Sha'ad a bolt, Qor a skull), the seven signets as gold seals with the engraved sign on blue / green / teal / orange enamel, the Sunstone of Thunder yellow, the Oil of Jewelcraft pink; legacy (G): Median's classic pictures, unchanged. Engine: `wPrefix != 0 \|\| wSuffix != 0` once, while the harness made the signets (all items quality 2): harness artifact, bug #35 (round 2 hit it on `hdm`). 0 crash files, 0 mxl2012-core errors; the real-input watchdog saw the user's own mouse, no foreground change |

Evidence: `mxl2012-runs/itemart3/ingame-r4/checks-20261030-174311-s1/` (`itemart_itemart4a_hd.png`, `_legacy.png`,
`itemart_itemart4b_hd.png`, `_legacy.png`). Unit tests: `test_itemart.py` 37 OK (5 + 59 + 7 on, the runes and signets on with
their `chisel` signs).

## Lane savecap: cancelled saves, "Character has too many items" (bug #512, 2026-10-30, slot 3, background mode)

Build: `tools/build_plugin.ps1 -Release -Tests` (all plugin tests pass, `savemode_tests` new). Slot 3 data = lane runetab's install.
For sessions A-C only `mxl2012-core.dll` of this branch was copied in. Slot 3 was locked twice (15:00-15:50 and 15:57-16:08).
Its mod `d2rloader.toml`, shared stash and DLL were backed up first and put back after each session (`cmp` equal). Left
behind: test characters `Savecapbfab` and `Savecaprbffj` in `mxl2012-s3`. Scratch drivers (not committed):
`mxl2012-runs/savecap/` (`drv.py`, `t1.py`-`t4.py`, `sA.py`, `sB.py`, `prep.sh`, `restore.sh`), copies of the run folders in
`mxl2012-runs/savecap/evidence/`.

**Retail format, by hand** (mod toml with the `mode = "extended"` line commented out). The extended shared stash is refused
(`Shared stash rejected ...`, `BadHeader`), so it was set aside and D2RLoader restarted. A new Sorceress got items from harness
`item`; the 30 s autosave was watched in `d2rloader.log` and in the `.d2s` time:

| Run | What | Result |
|---|---|---|
| `checks-20261030-150101-s3` | rune `r01`, shrine `A0+` (escape-coded code), plain magic rings x2 | saved (mtime moves, 0 failure lines) |
| same | ring with stat 511, 514 or 520 | **every save cancelled**: one `!"Character has too many items"` (PlrSave.cpp:1980; the assert dialog shows it once), then per save "Character save failed before the disk write ... format=retail native-result=3 encoding-error=yes ... capacity=65535" and "Save batch cancelled": the player's lines word for word. Item removed: the next save goes through |
| `checks-20261030-154051-s3` | the retail character in **extended** mode (toml back) | loads with all items (24 = 24); rings with stats 511 / 514 / 520 added, Save and Exit, reload: identical, `d2save.py show` lists the stats, `roundtrip` OK |
| same | heavy: inventory and cube full of rings with six stats each (514, 520, 511, 516, 523, 39) | 141 items, `.d2s` 9,046 bytes, 0 failures; all 141 in the file after Save and Exit (the harness `state` lists 120 at most) |

**Part `savemode` in game** (plugin of this branch; `mxl2012-core.log` copied to `mxl2012-runs/savecap/sessionABC-mxl2012-core.log`):

| Run | What | Result |
|---|---|---|
| `checks-20261030-155840-s3` (A) | start with the mod toml commented out (retail) | **PASS**: at load "savemode the mod's d2rloader.toml has no [d2rcore.save_format] mode ... mode = "extended" written, restart the game"; the file has `mode = "extended"` under the header, the old file is `d2rloader.toml.retail-backup`; this start stays retail |
| same | ring with stat 514 in the inventory | **PASS**: 2 cancelled saves -> "savemode 1 cancelled save seen", "2 cancelled saves seen ... notice on screen"; ring removed -> 90 s later "no cancelled save for 90 s, notice cleared" |
| `checks-20261030-160435-s3` (B) | retail again (old file back), reload of the retail character | 20 = 20 items (rune, `A0+`, amulet, starting items), 0 asserts: the player's load asserts are not from these items |
| `checks-20261030-160523-s3` (C) | the file as `savemode` wrote it (extended) | **PASS**: "savemode save format extended", no notice; the retail character and the retail (empty, 204 bytes) shared stash load, 0 rejected / BadHeader; stat-514 ring, Save and Exit, reload: 21 = 21 items, 0 failures |

**The red line itself is not in the screenshots** (`a0_menu_notice.png`, `a1_fail_notice.png`): D2RLoader's overlay is not part
of the PrintWindow capture of a background window (as for `bufficons`). The log shows the calls. **By hand (owner / user):** in
`mods\mxl2012\d2rloader\config\d2rloader.toml`, put `#` before `mode = "extended"`, start the game: a red line at the top says
the saves were set to retail and to restart. Restart: no line, the file has the key again. Not tested: a retail shared stash
that holds items (the one tested was empty) and Steam build 94995 (the player's).

## Lane dlsave: the downloader sets the extended save format in a kept d2rloader.toml (bug #512, 2026-10-30, no game run)

Owner decision 2026-10-30: besides the plugin part `savemode` (lane savecap), the downloader repairs the key after install /
update / repair (docs/launcher.md "Save format of a kept config"). Build: `cmake -S launcher -B build/launcher -A x64`,
`cmake --build build/launcher --config Release` (MSVC x64 Release, no warnings, unsigned, 2,213,376 bytes);
`launcher_tests.exe` **231 checks, 0 failures** (new `TestSaveFormat`: missing table, table without the key (also as the last
line without a newline, and CRLF), `mode = "retail"` with indent and comment, the dotted key, already extended (the same bytes
back, also with BOM / CRLF / single quotes), BOM + CRLF + comments kept, a CRLF file gets a CRLF table; `TestPlan`: the
preserve file's `.retail-backup` is not removed, another `.retail-backup` is).

Local update test (`mxl2012-runs/dlsave/update-test.ps1`, log `update-test.log`): a copy of lane launcher's local test site
(0.0.2-lt1 -> 0.0.3-lt2, `--site <dir>`, channel `test` rewritten per step), a fake D2R folder (`.build.info` 3.3.93847, the
fake `D2RLoader.exe` 1.3.1-beta) and its own `--data-dir`, all inside `mxl2012-runs/dlsave/`; no real game folder.

| step | what | result |
|---|---|---|
| A | fresh `install` of 0.0.2-lt1 | PASS: the shipped toml is `[d2rcore.save_format]` / `mode = "extended"`, untouched, no backup |
| B | the toml replaced by a #512-like player file (BOM, CRLF, comments, `[d2rloader] default_mod = "OtherMod"`, `[d2rcore.stash]`, no save format), `update` to 0.0.3-lt2 | PASS: "Kept your d2rloader/config/d2rloader.toml", then "... had no save format: set [d2rcore.save_format] mode = "extended" ...; nothing else in it changed. The old file is ...retail-backup"; the file is the player's bytes plus `
[d2rcore.save_format]
mode = "extended"
`; the backup is the player's file byte for byte |
| C | second `update` | PASS: up to date, the toml not rewritten (same mtime), the backup stays |
| D | the player sets `mode = "retail"   # test`, `repair` | PASS: "... had save format "retail" ..."; only that line becomes `mode = "extended" # test`; the first backup is kept (not overwritten) |

The first run of the test failed at D: the update in C deleted `d2rloader.toml.retail-backup` as "not part of the release",
and D then made a new backup of the retail file. Fixed in `PlanInstall` (the `<preserve file>.retail-backup` is the player's
too); this also keeps the backup the plugin part `savemode` writes. Not done: a run against a real D2R folder, a GUI run, signing,
publishing.

## Lane standin: better HD stand-ins for the most-seen Median-only monsters (2026-10-30, slot 2, background mode, build of lane/standin, data only)

Proposals for owner review, OFF in the build (`tools/data/hd_monster_proposals.json`, docs/hd-monsters.md section 16.1). Trial
builds: `hd_monsters.py build --out work/mod/data --try-proposals all`, `hd_translvl.py build`, `install_mod.py --slot 2`; the
normal build was installed again at the end. Check `standin_mons` (new: `hm_monsters` over `STANDIN_MONSTERS` with `clear`, the
pack of each monster killed before the next; `MXL_STANDIN_ONLY` picks some). Character `StandinNow` (Barbarian), `mxl2012-s2`.

| Run | Build | Result |
|---|---|---|
| lab `mxl2012-runs/standin/cand1` | normal | 30 D2R candidate units spawned as they are, to compare shapes with the legacy art |
| `checks-20261030-154226-s2` | normal | 13 spawned, 0 asserts (old order: the Siege Beast's corpse hid the later ones) |
| `checks-20261030-154634-s2` | trial 1 | 13 spawned, 0 asserts, 0 crash files; the Smith pack's corpses hid the later ones |
| `checks-20261030-155501-s2` | trial 2 (colours retuned, Porkchop last, `clear`) | 13 spawned, 0 asserts; Clay Golem and Smith keep their own colour whatever the table |
| lab `cand2` | trial 2 | Hephasto = the Smith's grey-blue model; the Overseer brown-red |
| `checks-20261030-161634-s2` | trial 3 (`5$` overseer1, `(l` no colour; ONLY 5 Ids) | 5 spawned, 0 asserts; Pest and Rathma out of the shots |
| lab `cand3` | trial 3 | Pest (fallen1) drawn; Rathma on succubus1 **not drawn** in HD (only its spells), drawn in legacy |
| `checks-20261030-162400-s2` + lab `cand4` | trial 4 (`$f` ancientbarb2) | FAIL: `BC_ASSERT: result` (animation_event_handler.cpp:608, "target mesh was not found") at Rathma's death; its unit holds only `hair.model`. `$f` withdrawn |
| `checks-20261030-163132-s2` | normal | current look for the sheets: 13 spawned, 0 asserts, 0 crash files |
| `checks-20261030-163506-s2` | trial 5 (the final 12 proposals) | **PASS load**: 13 spawned (Rathma on its current vampire1), 0 engine asserts, 0 crash files, no assert line in d2rloader.log; look PARTIAL (owner) |

Review sheets (outside git): `mxl2012-runs/standin/sheet_1.png`, `sheet_2.png`, `sheet_3.png` (legacy art, HD now far / near
from `163132`, HD proposal far / near from `163506`), `sheet_4_pest_close.png`. Owner: approve or reject each token; an approved
one is switched on by its `enabled` and the file's `enabled`.

## Lane rathma: an HD stand-in for Rathma Primus that reads as a necromancer (2026-10-30, slot 3, background mode, build of lane/rathma, data only)

Proposal for owner review, OFF in the build (`$f` in `tools/data/hd_monster_proposals.json`, docs/hd-monsters.md section 16.2).
Trial builds: `hd_monsters.py build --out work/mod/data --try-proposals $f`, `hd_translvl.py build`, `install_mod.py --slot 3`;
the normal build was installed again at the end. Check `MXL_STANDIN_ONLY=rathma_primus game_checks.py all standin_mons`,
character `RathmaLane` (Barbarian, `mxl2012-s3`); the look from the lab copy `mxl2012-runs/rathma/lab.py` (stage `cand`, crops
around the monster's own position: Rathma walks away from the spawn point and casts from range, out of the check's shots).

| Run | Build | Result |
|---|---|---|
| `checks-20261030-203247-s3` + lab `mxl2012-runs/rathma/cand1` | trial 1 (`nihlathakboss` x1.15, no colour) | spawned, 0 engine asserts, 0 crash files; drawn (lab crops; in the check shots small by the rocks on the left), spells show; small and dark |
| `checks-20261030-203859-s3` + lab `cand2` | trial 2 (`nihlathakboss` x1.35, value +0.3: the proposal) | **PASS load**: 0 engine asserts, 0 crash files; drawn, walks, casts frost nova and orbs, dies |
| `checks-20261030-204213-s3` + lab `cand3` | trial 3 (`doomknight3` x1.2) | **PASS load**: 0 engine asserts, 0 crash files; drawn, casts, dies |
| lab `now` | normal (`vampire1` x1.4) | the current look for the sheet |

The only assert lines in each run are the engine's pool checks when the game is closed (`s_StatsPool.IsEmpty()`,
`m_allocated == 0`, ...: exit-only, ignored, see the table above). Review sheet (outside git):
`mxl2012-runs/rathma/sheet_rathma.png`. Owner: Nihlathak, the Oblivion Knight or keep the vampire.

## Lane runehd: Median's runes upscaled again, for the owner's review (2026-10-30)

Owner ruling (2026-10-30): "just upscale the runes again, try to make them look more like HD versions of the original without
losing the symbol feel too much". The 23 rune proposals are now lane `runehd` method entries (`rune-hd`, `rune-crisp` for On
and Qor, `rune-flat` for Auhe; tools/rune_hd.py, docs/hd-icons.md "Runes: Median's own pictures upscaled again"), all
**off** (owner rule: the owner sees the art first), so a normal build or install shows nothing new.

| check | result |
|---|---|
| `py -3 -I tools/item_art_review.py sheets ../mxl2012-runs/runehd/review --runehd` | `sheet_01..03.png` (+ `_2x`): classic, shipped HD, round 4, new at HD size and at 1920 x 1080; `methods_01..03.png` (the three methods); `overview_2x.png` |
| `tools/tests/test_itemart.py` | 43 tests OK (new: `RuneHdTests` x5 on a synthetic rune: sign mask without speckle / rim shading, size, strokes and a 1 px gap kept in every method, anti-aliased edge and the original's colour range, lowend size, `candidate`; lane runehd's 23 entries off) |

**In game (slot 3, background mode, build of lane/runehd, data only, the trial switched on only for this build).** The 23
runehd entries set `enabled` in the working tree (not committed), `MXL2012_HD_OUT=work/mod py -3 -I tools/hd_icons.py build`
("picture proposals used: 71", item icon check 0 sprite problems), install `MXL_SLOT=3 MXL_RUN=runehd py -3
tools/install_mod.py --slot 3` (data only, 3389 files), check `MXL_RUN=runehd MXL_SLOT=3 MXL_CHAR=RuneHdTrial
MXL_ITEMART_SETS=itemart4a py -3 tools/game_checks.py all itemart_pics`; then the file restored (`git checkout`) and the
icons rebuilt ("picture proposals used: 48").

| run | what | result |
|---|---|---|
| `checks-20261030-214917-s3` | itemart_pics, set itemart4a (the 23 runes `r34`..`r56`) | PARTIAL (shots judged by hand): all 23 made; HD: every rune shows the new picture, clean stone outline and the original's sign (Thur a 3, Sha'ad a bolt, Qor a skull over crossbones, Nih's hole open); at 1920 x 1080 the signs are lighter than round 4's chiselled ones (as in Median's own pictures); 0 crash files, d2rloader.log 0 ERROR / ASSERT lines |

Evidence: `mxl2012-runs/runehd/ingame/checks-20261030-214917-s3/` (`itemart_itemart4a_hd.png`, `_legacy.png`) and
`mxl2012-runs/runehd/ingame/runes_hd_crop_3x.png`. Slot 3 keeps this lane's install (runes off in it would need a reinstall
of a normal build).

## Lane itemart5: the 21 unmatched item pictures rebuilt crisp, for the owner's review (2026-10-30)

The 21 pictures with no D2R HD item of their kind (shrine cross, the four arcane crystals, the three catalysts, Apple, goblet,
Goodberry, Moon Icon, the junket eye, the skull star, the skull ring, the bag, the open book, the two Bling Bling piles, the
bones, the candles) are lane `itemart5` method entries (`item-hd` / `item-soft`, tools/item_rebuild.py, docs/hd-icons.md
"Rebuilt pictures"), all **off** (owner rule: the owner sees the art first), so a normal build shows nothing new.

| check | result |
|---|---|
| `py -3 -I tools/item_art_review.py sheets ../mxl2012-runs/itemart5/review --rebuild` | `sheet_01..03.png` (+ `_2x`): classic, HD now, proposal, alternatives (the arcane crystals also as D2R's flawless diamond in Median's colours) at HD size, then classic / now / proposal at 1920 x 1080; `overview_2x.png` (classic and new, all 21) |
| `tools/tests/test_itemart.py` | 49 tests OK (new: `ItemRebuildTests` x5 on a synthetic fruit: size and shape, a 1 px stem kept and still green, the highlight, anti-aliased edge, tones in the original's range, item-soft evens out the speckle only, lowend size, `candidate`, lane itemart5's 21 entries off; `BuildProposalTests` VarInvGfx copies, bug #513) |
| `MXL2012_HD_OUT=work/mod py -3 -I tools/hd_icons.py build` | normal build: "picture proposals used: 48", item icon check 238 sprites, 0 problems (the 10 new ones: the `ring08` variant copies, #513) |

**In game (slot 3, background mode, build of lane/itemart5, data only, the trial switched on only for this build).** The 21
entries set `enabled` in the working tree (not committed), `MXL2012_HD_OUT=work/mod py -3 -I tools/hd_icons.py build`
("picture proposals used: 69"), install `MXL_SLOT=3 MXL_RUN=itemart5 py -3 tools/install_mod.py --slot 3` (data only), check
`MXL_RUN=itemart5 MXL_SLOT=3 MXL_CHAR=ItemArtFive MXL_ITEMART_SETS=itemart5 py -3 tools/game_checks.py all itemart_pics`
(new set `itemart5`: one item per picture; an entry may name a quality, `r@r unique`); then the file restored (`git checkout`)
and the icons rebuilt ("picture proposals used: 48").

| run | what | result |
|---|---|---|
| `checks-20261030-222156-s3` | itemart_pics, set itemart5 (Boss Killer Ring `r@r` normal) | 20 of 21 show the new picture; the ring's cell is empty in HD (legacy: a random classic ring): bug #513 found. FAIL only by the engine note `wPrefix != 0 \|\| wSuffix != 0` (bugs.md #35: making the Retard Mode Charm `yq9`, harness path) and the exit-only `m_freed == 0` |
| `checks-20261030-222616-s3` | the same, `r@r unique` | the unique ring is blank too (so players see it): #513 is not only the harness's normal ring |
| `checks-20261030-223159-s3` | the same after the #513 fix (`ring081..5` written) | PARTIAL (shots judged by hand): **all 21 show the new pictures in HD**, the Boss Killer Ring included; d2rloader.log 0 new ERROR / ASSERT lines (the check's FAIL is #35's engine note again), 0 crash files |

Evidence: `mxl2012-runs/itemart5/ingame/checks-20261030-2*-s3/` (`itemart_itemart5_hd.png`, `_legacy.png`) and
`mxl2012-runs/itemart5/ingame/itemart5_crop_3x.png` (the backpack of the last run at 3x). Slot 3 keeps this lane's trial
install (the 21 on); a normal build reinstalled turns them off again.

## Lane tunnels: Judgement's bolt below the target (bug #481) and the Ancient Tunnels void (2026-10-30, slot 1, background mode)

New check `jdg_path` (tools/game_checks.py). It runs the Paladin `HdlPal` with Judgement (skill 518) on the right button,
in HD and then legacy (`MXL_JDG_MODES`, default `hd,legacy`). For each target in JDG_TARGETS it spawns a zombie, right-clicks
it and polls `missiles` for 3 s, with up to 6 shots `jdg_<mode>_<dx>_<dy>_<n>.png`. The rows give the missiles seen per
Judgement row and each mallet's path from the player. The look is judged by hand.

```
MXL_RUN=tunnels MXL_SLOT=1 MXL_CHAR=HdlPal MXL_CHAR_CLASS=paladin MXL_CACHE_POLL=3 MXL_WALL_LEVELS=65 py -3 tools/game_checks.py all jdg_path wall_maps
```

| run | checks | result |
|---|---|---|
| `checks-20261030-223110-s1` | jdg_path, wall_maps (level 65 only), build with belial's terrain mesh indexed in `model_lod_desc.bin` | jdg_path PARTIAL: mallets (`zomgpewpewmallet`, class 1256) start 1-3 sub-tiles from the player; the ones that find no target fly straight down-screen (legacy +3,+0 → +12,+9; HD +3,+0 → +12,+10) whichever side the zombie stands on, the same in both modes (`jdg_legacy_5_0_2.png`: classic's gold bolt below the target; `jdg_hd_5_0_3.png`, `jdg_hd_0_6_1.png`: HD's bolt on the same spot, white core). wall_maps PARTIAL: belial reached in HD and classic, no engine error, HD still stone floor over the void (`wall_belial_hd_0.png` against `wall_belial_classic_0.png`) |
| `checks-20261030-225247-s1` | jdg_path, build with a gold texture in place of `default/White.texture` in Judgement's `lightningstrike` copy (tried, not shipped) | PARTIAL: same paths (HD +12,+10 and +16,+14 for the misses); the bolt core still white (`jdg_hd_0_6_1.png`), so the swap was reverted |

Results: #481 is explained, not an HD bug. The mallet is Lightning Strike's chain bolt (srvhit 20). When it finds no other
target it flies down-screen, in classic too, and the HD effect is drawn where the missile is. Only the white core differs
from classic, and it is still open (docs/bugs.md). The void cannot be fixed through the scene (docs/maps-hd.md item 12,
closed): `TERRAIN_MAPS` stays empty. No game data changes in this lane.

Evidence: `mxl2012-runs/tunnels/ingame/<run>/` (both runs), `mxl2012-runs/tunnels/jdg_before_grid.png` (HD top, legacy bottom),
`jdg_after_hd_grid.png`, `jdg_core_zoom.png` (core before / after the texture swap), logs `run1.log`, `run2.log`, `build1.log`.

## Lane tunnels65: the Ancient Tunnels as a fixed map, the void in HD (2026-10-31, slot 2, background mode)

Owner (2026-10-31): "try making it a fixed pre made map". Level 65 already is one: levels.txt `DrlgType` 2 is a preset level
(1 maze, 3 outdoors), and Median's 65 has 2 (lvlprest 1091, `act2/arcane/belial.ds1` only); the Arcane Sanctuary is the maze
(docs/maps-hd.md item 12). What was tried instead: the belial terrain mesh named in the scene's `dependencies.models`, as all
of D2R's scenes with a terrain name it (lane tunnels had it in `other`), behind `MXL2012_BELIAL_TERRAIN=1` (default off,
`tools/walls_hd.py` `terrain_maps`).

New check `tunnels65` (tools/game_checks.py, tests `tools/test_game_checks_tunnels65.py`). Per mode (`MXL_T65_MODES`, default
`hd,legacy`, G set in the Act 2 town): SET-UP `h level 65 warp`, out to the Lost City by clicks on 65's warp tile, back in by
clicks on the Lost City's tile (that tile is not loaded from the Lost City's waypoint: `tiles` 0, `presets 5` 0), `move` walks
to the .ds1 cells of `T65_CELLS` (`place` where the walk fails), out again by clicks. Shots `t65_<mode>_<n>`, god mode.

```
MXL_RUN=tunnels65 MXL_SLOT=2 MXL_CHAR=TunnelWalk MXL_CHAR_CLASS=paladin py -3 tools/game_checks.py all tunnels65
```

| run | build | result |
|---|---|---|
| `checks-20261031-141923-s2` | switch on | FAIL (check script): the Lost City's warp to 65 is not loaded from its waypoint; the check now goes in by `level 65 warp` first |
| `checks-20261031-142109-s2` | switch on | PARTIAL: in and out by clicks; the "legacy" round was still HD (the Lost City is too dark for `graphics_mode`; G is now set in town); HD floor over the void |
| `checks-20261031-144449-s2` | switch on | PARTIAL: HD and classic, in and out of 65 by clicks on both warps, no assert, no crash file; HD stone floor over the void, classic the black void |
| `checks-20261031-151341-s2` | switch off (before) | PARTIAL: the same as the run with the switch; HD looks the same |

Results: **no change in HD**, so the switch stays off (no CHANGELOG line). The level's entrance and exit work both ways in both
modes and its monsters (Astral Guardians, 10-13 near the spots) are there. The spot walks mostly ended at the Astral Guardian
pack round the neck (y about 5091-5126; one walk reached spot 3), and `place` found no free spot at spot 1 (cell 16,7, the
north bar): not looked into further. Whether that part of the platform is reached on foot in Median 2012 on 1.13c or only by
Teleport (levels.txt `Teleport` 1) is an open question; the switch only changes the HD scene, so it is the same with it off.

Evidence: `mxl2012-runs/tunnels65/ingame/<run>/` (the last three runs), sheet `mxl2012-runs/tunnels65/t65_before_after.png`
(rows: HD before, HD after, classic; arrival, spot 1, spot 3), logs `build1.log`, `run-on3.log`, `run-off.log`, the switch's
scene, mesh and index in `on-artifacts/`. Plugin: the DLL of worktree nmhell4 (same commit `de8986d`, no plugin change in
this lane; this lane's own plugin build was not allowed to run).

## Lane rotwstash: the RotW stash pages in classic mode (bug #516, 2026-10-30, slot 3, background mode)

Classic layout + art for the Gems / Materials / Runes stash pages, down-rendered from D2R's HD art (`tools/rotw_stash_legacy.py`,
docs/legacy-graphics.md section 9). **Kept out of the mod** by default (`work/rotw_stash_legacy/data`); `MXL2012_ROTW_LEGACY=1
py -3 tools/build.py` puts it in.

| check | result |
|---|---|
| `py -3 -I tools/rotw_stash_legacy.py check --out work/rotw_stash_legacy/data --mod work/mod/data` | no problem: 91 slots (gems 35, materials 23, runes 33), 71 codes are Median items with a classic picture that fits, 20 have no item (as in HD) |
| `tools/tests/test_rotw_stash_legacy.py` | 6 tests OK (DC6 round trip, palette 1-224, classic cell boxes, layout follows HD, unknown `@key`, build + check with a missing picture and an overlap) |
| review sheets (outside git) | `mxl2012-runs/rotwstash/sheet/rotwstash_{gems,materials,runes}.png` (HD page next to the classic mock-up, x2) and `rotwstash_personal_shared.png` |

**In game (slot 3, an account without RotW).** Character `Rotwstash` (Sorceress, `mxl2012-s3`), stash opened in HD, then G;
the classic layout in the slot's install swapped by hand for parts of it (lab scripts in the lane's run folder), the slot's
copy removed at the end.

| classic layout | result |
|---|---|
| D2R's own (the shipped state) | PASS: HD stash 2 tabs; G with the stash open fine |
| the step's full layout | **crash** `D2R.exe+0x23E6A5` (Personal / Shared inside `basicstash_container`) |
| five tabs + new art, Personal / Shared at top level, no RotW pages | PASS |
| + the RotW pages with slots (any form: all, one per page, hidden pages, with child text boxes) | **crash** `D2R.exe+0x154AF2` (null + 0x440) |
| + the pages without slots + the stash cube | no crash; the cube cover and withdraw button draw on Personal, all five tabs show (`mxl2012-runs/rotwstash/flat_noslots_{1hd,2legacy}.png`) |

### Owner test on a RotW account (the slots cannot)

1. Build with `MXL2012_ROTW_LEGACY=1 py -3 tools/build.py` and install. Set `always_enable_rotw_legacy_graphics_keybind = true`
   in the install's `d2rloader\config\d2rloader.toml` by hand (as in docs/legacy-graphics.md 8.4).
2. In a RotW game, put a few gems, runes and materials (keys, essences) into the Gems / Materials / Runes tabs in HD. Open the
   stash on the Personal tab and press **G**. Expected risk: a crash at `D2R.exe+0x23E6A5` (the `basicstash_container`, also seen
   without RotW). Keep the crash file from `d2rloader\crashes\`.
3. If it holds: click each of the five tabs in classic. Look for: page art in place, each item in its recess with its count,
   Personal / Shared widgets not on the RotW pages, the cube window and its cover, the Transmute and Withdraw buttons.
4. Move an item from the inventory onto a RotW tab in classic (the notify mark), take one out, then press G back to HD with a
   RotW tab open.
5. Report to bug #516 with screenshots; the cube's 3 x 4 window vs Median's 10 x 8 cube goes to #515.

## Lane skillhd: sharper HD skill tree pages, for the owner's review (2026-10-30, slot 2, background mode, build of lane/skillhd)

docs/PLAN.md phase 5 "upscaled skill-tree pages". The shipped HD pages are Median's classic pages scaled with Lanczos (soft).
Three candidates (tools/skill_tree_hd.py, docs/hd-ui.md "Skill trees: HD page candidates"): **A `rebuild`** (Median's page,
its frames / rims / arrows / level boxes rebuilt edge-aware by tone levels as tools/rune_hd.py does, stone Lanczos +
sharpen), **B `rebuild-stone`** (A's structure on D2R's own HD stone carrying Median's stone tone), **C `d2r`** (D2R's HD
panel: its stone, its engraved sockets and arrows on Median's cells, Median's tree colours as socket rims, page 3's passive
frame engraved). All **off** (`tools/data/skill_tree_proposals.json` `enabled: false`), so a normal build or install shows
nothing new; no CHANGELOG line. No Median Warlock pages exist (D2R's `waskilltree` stays as it is).

| check | result |
|---|---|
| `py -3 -I tools/skill_tree_review.py ../../mxl2012-runs/skillhd/review` | `sheet_<cls>.png` x 7 (rows = the 3 tabs; legacy, HD now, A, B, C over D2R's tree background, half size), `detail_<cls>.png` x 7 (1:1 HD pixels), `overview_<method>.png` |
| `tools/tests/test_ui.py` | 32 tests OK (new: `SkillTreeHdTests` x4: the switch ships off and a trial overrides it, rebuild edges crisper than Lanczos with the page's own colours, every candidate keeps the cells (sockets on all 10 cells, the tree colour rim, the passive frame), stone spots are no structure) |

**In game (slot 2, background mode, build of lane/skillhd with slot 2's installed plugin, data only).** `py -3 tools/build.py`
(switch off), install, then per candidate `MXL2012_UI_OUT=work/mod py -3 -I tools/skill_tree_art.py --try <method>` +
install. Characters `SkhAma` ... `SkhAss` (level 1, `mxl2012-s2`), per class the tree (T) and its three tabs, cursor parked
left. Scratch driver (not committed): `mxl2012-runs/skillhd/ingame/` (`drv.py`, `cls.py`, `trial.sh`, `ingame_sheet.py`).
Afterwards the normal pages were rebuilt and installed again (slot 2 = lane build, switch off).

| run | what | result |
|---|---|---|
| `checks-20261030-222440-s2` | current build, 7 classes x 3 tabs, HD and legacy (42 shots) | baseline: Median's pages in HD (soft), legacy Median's classic pages |
| `checks-20261030-230307-s2` | trial B `rebuild-stone`, HD (21 shots) | PASS by eye: every icon in its box, level boxes right of the icons, tabs and titles as before, crisp frames on D2R's grain |
| `checks-20261030-231050-s2` | trial C `d2r`, HD (21 shots) | PASS by eye: D2R's sockets on Median's 10 cells, tree colour rims (Sorceress red / blue ...), page 3's passive frame, arrows small at this size |
| `checks-20261030-231900-s2` | trial A `rebuild`, HD (21 shots) | PASS by eye: as the shipped page, frames sharper |

0 crash files, d2rloader.log 0 ERROR / ASSERT lines in the stop of the last run. One failed start in between (not a game bug):
a trial run of `skill_tree_art.py` into `work/mod` wrote `skill_tab_titles.json` back into `lng/strings/mxl2012`, and D2RLoader
stopped startup ("String tables are unavailable", MonType.txt); `trial.sh` deletes it before the install now (docs/hd-ui.md).

Evidence: `mxl2012-runs/skillhd/review/` (static sheets), `mxl2012-runs/skillhd/ingame/ingame_<cls>.png` (per class: legacy |
HD now | A | B | C from the shots, rows = tabs) and the run folders above (copied to `mxl2012-runs/skillhd/ingame/runs/`). Owner: pick A, B, C
or none; switching one on is `enabled: true` + `method` in `tools/data/skill_tree_proposals.json`.

## Lane peticons: pet icons by the portrait (bug #514, 2026-10-30, slots 1 and 2, background mode)

Lab (outside git) `mxl2012-runs/peticons/lab.py <worktree> <out> [nec,other] [hd,legacy]`: Necromancer `PetIconsNec`
(`mxl2012-s1` / `-s2`), level 120 and tanked by the harness, a Kashya mercenary hired (`hire_in`), a real waypoint to Cold
Plains (the mercenary comes along), god mode, then `cast` of the Necromancer / item summons 473 474 475 476 477 631 856 801
83 661 (stage `nec`) and of other classes' summons 433 438 469 472 532 544 507 322 706 (stage `other`), learnt by
`ensure_learned`; after each stage a shot per mode with the debug overlay off, plus a crop of the left side.

| Run | Slot / build | Result |
|---|---|---|
| `before` | 1, the mod build installed there at 22:43 (pettype as on main) | HD: all Necromancer pets show the Necromancer's face; names run together ("Guardian SpiThunderbear"); the row stops at 9 icons. Legacy: the same faces (Median's look), names staggered, 14 icons cut at the screen edge. The mercenary was killed by the lab's `clear_monsters` in this run |
| `trial1` | 1, D2R's layout with `nextIconOffsetSecondSet` 110 and `nameAlternationSecondSetY` 30 copied in by hand (removed after) | still 9 icons: a count limit, not the width; names staggered and readable; at 110 the 120-unit health bars touch |
| `trial2` | 1, the same with `summonsUseSecondSet` false, `nextIconOffset` 170 | all pets in a column down the left edge, 12 seen to the window's bottom: no 9 limit there |
| `normal` | 2, the normal build of this branch (icons off) | names staggered, Median's class faces kept, the mercenary first; 0 assert lines |
| `after` | 2, this branch with `pet_icons.py build --try all` (data only) | **PASS (judged on the shots):** the mercenary first, then each pet type with its own icon (Shadow, Darkling, Rampagor, Lamia, Void Archon, Overlord, Siren, Jinn; Acid Fiend and Guardian Spirit keep Median's faces, they have no entry), names staggered; legacy unchanged (class faces, Median's names); the HD row still stops at 9 with the mercenary; d2rloader.log 0 assert lines, no crash file |

Evidence: `mxl2012-runs/peticons/{before,trial1,trial2,after}/` (`nec_hd.png`, `nec_legacy.png`, `other_*.png`, `crop_*`),
the review sheet `mxl2012-runs/peticons/sheet_peticons.png` (legacy, HD now, HD proposed, per pet type). Slot 2 got the
normal build of this branch again at the end (icons off, the names staggered).

## Lane acts25: Acts 2-5 on Normal with a live mercenary (2026-10-30, slot 4, background mode, build of lane/acts25 = main 0.1.4 + #509 + #511/#292 `reassign`)

Check `acts25` (game_checks.py): `MXL_RUN=<lock> MXL_SLOT=N MXL_CHAR=<new> MXL_CHAR_CLASS=paladin py -3 tools/game_checks.py all acts25`.
Per act (`MXL_A25_ACTS`, default `2,3,4,5`) the parts of `MXL_A25_PARTS` (`travel,town,hire,items,wp,entries,bosses`) run in turn:

- **travel**: into the act the player's way, then (SET-UP) the act boss before it killed by the harness, so the quest hooks run.
  - Act 2: Warriv's line.
  - Act 3: Meshif's line, after quest 14 bit 0.
  - Act 4: Mephisto's portal, by `acts_portal_a4`.
  - Act 5: the Tyrael talk, then a click on his red portal 566.
- **town**: every NPC of `TOWN_NPCS` talked to.
  - To reach an NPC: `moveto`, then the town sweep's spot or the map's `presets 1` spot.
  - Last resort: SET-UP `place` or a spawned copy (named in the row).
  - Trade: buy one item at the act's trader and sell it back.
- **hire**: the act's hireling by `hire_in`, gear worn by clicks on the hireling panel, then SET-UP life 20,000.
- **items**: each quest item dropped next to the character and picked up by a click.
  - Usable items get a right click.
  - The cube recipes go through the Transmute button: the cube is emptied first, then the inputs are put in by `item X cube`.
- **wp**: every waypoint of the act by the HD panel.
- **entries**: every warp-tile link of levels.txt (`a25_routes`) by `up_enter` (lane uppass), in `MXL_A25_GRAPHICS` (legacy or HD).
  - `MXL_A25_ROUTES_MAX` caps the count.
  - A failed SET-UP warp or way out is listed but not judged.
- **bosses** (`A25_BOSSES`): the map's own unit or a SET-UP spawn, fought `MXL_A25_FIGHT_S` s. Life is read before and after.
- Last, the `reassign` counter delta of the act.

Common SET-UP for every act:

- Level 114 by an xp award.
- God mode.
- All waypoint bits.
- A Rogue from Kashya, mercenary life 20,000.

Town, items and waypoints always run in HD (their click spots are the HD panel's); `MXL_A25_GRAPHICS` switches only the entries and the fights. So every row is PARTIAL-grade evidence of the click paths, not a no-help playthrough.

| Act | Run | Travel | Town NPCs / trade / hire | Quest items / waypoints | Click entries | Bosses | `reassign` (commands, units without a room, player) | Result |
|---|---|---|---|---|---|---|---|---|
| 2 (legacy) | `checks-20261030-200614-s4` (`run4-a2.log`), 54 min | Warriv line d36 -> Lut Gholein: OK | 8 of 10 menus (Atma, Fara, Greiz, Elzix, Lysander by spawned copy; Jerhyn by place). Drognan not found; Cain no menu. Fara: buy / sell OK. Greiz (338, level 113) hired, Cap / Quilted / Spear worn by clicks | 0 of 4 picked up: the run was still walking when the item was dropped (harness, fixed with `ven_wait_still`). Waypoints 7 of 9 by the panel (42, 44 by warp) | **17 of 17 judged entered** (9 SET-UP failures: no loaded tile, or the way out failed) | Radament killed in 4 s; Creature of Flame 22.86M -> 20.30M; Summoner killed; Duriel (map's own) 5.47M -> 77k, then the harness kill | 4,0,0 -> 211, 46, 0 | FAIL (harness rows only); game alive, no crash |
| 3 (legacy) | `checks-20261030-210750-s4` (`run6-a3.log`), 71 min | Meshif not found (the travel had no NPC spot then: fixed); harness travel instead | Hratli, Ormus (copy), Meshif: menus. Cain, Asheara, Alkor, Natalya not found (moveto sees loaded rooms only: `presets 1` fallback added). Hratli: buy / sell OK. Asheara (359) hired, Cap / Quilted / Scimitar / Buckler worn | 7 of 9 picked up (g34, xyz missed: click pickup); cube qf1 + eye + brain + heart: no qf2, because the cube still held Act 2's msf / vip (harness; the cube is now emptied first). Waypoints 7 of 9 (76, 80 by warp) | 12 of 15 judged entered (5 SET-UP failures). Not entered: 83->100 (Durance stairs: the Compelling Orb was not smashed, as D2), 81->97 and 82->99 (Kurast temples: 51 clicks on the tile, still outside; 80->94 and 82->98 entered) | Azmodan: the spawn made none (one spot; now 6 spots). Mephisto (map's own): no damage in 166 s (known: across the moat, see the acts rows above) | 4,0,0 -> 181, 33, 0 | FAIL (harness rows, 2 temple entries open); game alive, no crash |
| 4 (legacy) | `checks-20261030-222412-s4` (`run7-a4.log`), 11 min | Mephisto's portal -> Pandemonium Fortress by click: **PASS** | Cain (copy), Tyrael, Jamella, Halbu: all menus. Halbu buy / sell OK. No hirer (Act 3's stays) | mss, hfh picked up. Waypoints 3 of 3 | 106->107: SET-UP failure (no loaded tile), not judged | Izual (spawned) 17.05M -> 0; Hephasto (spawned) killed in 17 s; Diablo (spawned) 22.30M -> 21.51M in 30 s | 4,0,0 -> 38, 0, 0 | **PASS** |
| 5 (legacy) | `checks-20261030-223842-s4` (`run8-a5.log`), 54 min, 18 routes max | No object 566: the run skipped Tyrael's talk (fixed: `acts_end_talk` first); harness travel | Larzuk (copy), Malah, Cain (copy): menus. Drehya, Nihlathak, Tyrael not found (before the `presets 1` fallback). Larzuk buy / sell OK. Qual-Kehk (561) hired after quest 36 bit 0 (fixture), Cap / Quilted / Scimitar worn | ice picked up, tr2 missed (click pickup). Waypoints 8 of 9 (129 by warp) | 4 of 5 judged entered (12 SET-UP failures). Not entered: 120->128 (the Worldstone Keep stays shut until the Ancients die, as D2; they were fought after the entries) | Nihlathak (spawned): no damage (the server refused the path to the copy, 2 attacks); Ancients (spawned) killed in 11 s; Baal (map's own) 31.90M, gone after 93 s (his flight), then the harness kill | 5,0,0 -> 93, 12, 0 | FAIL (harness rows only); game alive, no crash |

Across the four legacy runs: 33 of 37 judged click entries entered, the game alive all the way, the mercenary alive and following (server mode 12 after the first entry in every act, as lane uppass saw; the client draws it). The `reassign` guard caught 91 units left without a client room (0 for the player): each would have closed the game before #511's fix. Engine asserts: only the known `nDirectionIndex < nDirections` (#54 / #73).

One start (`checks-20261030-210445-s4`) did not reach the menu: a failed read of a `.dt1` and a crash report (bug #517). The next start was clean.

Not bugs (checked against the docs):

- **The colossal row:** the first Act 5 run spawned `colossal1` (745) in level 137. That raised D2R's `MONFLAG_ENABLED` assert. These are D2R RotW rows that no table of the port places (#71), and level 137 is #261. The row was taken out of `A25_BOSSES`.
- **Act numbers in `level`:** the plugin's `level` answer prints D2R's 0-based act index ("act 4" in Act 5).

Open:

- **Kurast temples:** two entries (81->97, 82->99) took 51 clicks on the warp tile and the character stayed outside. A mod data bug (the doorway stair's art token), fixed as bug #518; see "Lane kurast".
- **Lut Gholein NPCs:** Drognan was not found and Cain gave no menu (before the `presets 1` fallback).
- **Waypoints:** 5 waypoints (42, 44, 76, 80, 129) came by warp when the panel click missed.
- **Click pickups:** 3 of 15 quest items in Acts 3-5 were not taken by the click (g34, xyz, tr2). The item was 4 from the character; 4 clicks on its projection did nothing.
- **Nightmare / Hell:** not run (time).

Fixes in the harness after these runs (unit tests `tools/test_game_checks_acts25.py`):

- `hostiles_near` leaves out the player's own hireling classes (`HIRELING_CLASSES`). Run 1 fought its own mercenary for two hours.
- `up_click_through` walks to the warp's preset when the tile's room is not loaded.
- The town NPC is found from `presets 1`.
- The cube is emptied before a recipe.
- The spawn is retried on 6 spots.
- Tyrael's talk comes before his portal.
- Lam Esen's Tome is not "used".

HD sample (`MXL_A25_GRAPHICS=hd`, Acts 3 and 5, 4 routes each): 

| Act | Run | Result |
|---|---|---|
| 3 (HD, stopped) | `checks-20261030-233629-s4` | Started as Acts 3 + 5 (`run9-hd-a35.log`). **Meshif's travel line 1 -> Kurast Docks (75): PASS** (the NPC spot fix). The Kurast NPCs came from `presets 1` (Asheara talked to at 1.4, Alkor, Natalya, Ormus by walk or copy). Then `hire_in`'s own talk walk to Asheara (97-104 away) ran 22 min without an end, so the run was stopped. The game closed with it. `unlock 4` restored the shared files (10, verified). Open: give `talk` in `hire_in` a time cap |
| 5 (HD; parts travel, wp, entries, bosses; 4 routes) | `checks-20261031-001845-s4` (`run10-hd-a5.log`), 17 min | **Act 5 travel PASS**: after the Diablo harness kill, Tyrael's talk (`acts_end_talk`), then a mouse click on portal 566 -> Harrogath (109). Waypoints 7 of 9 by the panel (115, 118 by warp). Entries: 113<->114 entered by clicks in HD, 3 SET-UP failures. Ancients (spawned) killed in 18 s. Nihlathak (spawned) no damage: 18 attacks, every one at 10-14 from him, "mode now 1" (the walk does not close in: harness). Baal (map's own) no damage, 0 attacks: he sits on his throne until the waves are done (as D2). `reassign` 5 -> 57 commands, 5 units without a room, 0 player; no engine assert; game alive |


Evidence: run logs `mxl2012-runs/acts25/run1.log` .. `run10-hd-a5.log`, the per-run `report.md` / shots under `work/runs/<run>/`, `mxl2012-runs/acts25/evidence/run5-startup/`.

## Lane rotwgate: RotW stash pages in classic only as RotW allows (bug #516, 2026-10-31, slot 1, background mode)

Plugin part `rotwstash` (docs/plugin-plan.md section 29, docs/legacy-graphics.md 9.6): D2R wires the stash's five pages only in
HD; the part makes its init wire them in classic as well, and D2R's own RotW rule picks the tabs. Build of lane/rotwgate, dev
plugin, mod built with `MXL2012_ROTW_LEGACY=1` (the step's full classic layout: `basicstash_container`, 91 slots, cube).
Slot 1 (no RotW: `mxl2012` "game type 2"), character `RotwGate` (Sorceress, `mxl2012-s1`), stash opened through the harness,
G through `set_graphics`. Scripts: `mxl2012-runs/rotwgate/g1.py` (HD first), `g2.py` (classic first).

| run | part mode | classic layout | result |
|---|---|---|---|
| E0 control | `MXL_ROTWSTASH_TEST=never` (D2R's HD-only rule) | the step's | **crash** on the first G, `D2R.exe+0x23E6A5` (as lane rotwstash; `evidence/e0_crash_head.txt`) |
| E1 | wired in every game | the step's | PASS: classic shows Personal / Shared only, back to HD fine (`e1always_2legacy.png`) |
| final 1 (`checks-20261031-144351-s1`) | default (no variable) | the step's | PASS: 10 cycles HD stash -> G -> G, 0 crash; `mxl2012` "stash inits 21 (classic: pages wired 10, left as D2R 0), item pictures skipped 0; game type 2" |
| final 2 (same run) | default | the step's | PASS: 6 cycles, stash opened fresh in classic, clicks on Shared, Personal and where Gems / Materials / Runes would be (nothing happens there), G to HD and back; Shared shows "Shared with offline characters" and Page 1 / 3 |
| final 3 (`checks-20261031-145750-s1`) | default | D2R's own (the mod's file moved aside for the run, put back after, `cmp` equal to `work/mod`) | PASS: 5 cycles, D2R's two wide tabs, unchanged |

0 new crash files over final 1-3 (logscan at each stop); `mxl2012-core.log` only the usual "assert skipped" status words.
Plugin: `build_plugin.ps1 -Release -Tests`, `rotwstash_tests` all passed. Not tried: the release DLL in game (no harness in
it; it has the same default and no test variable). Cosmetic, without RotW: "Personal" is cut to "PERSON" on the step's
63-pixel tab. Evidence: `mxl2012-runs/rotwgate/evidence/` (shots, `final1-3.log`, the E0 crash head).

### Owner test on a RotW account (the slots cannot)

1. Build with `MXL2012_ROTW_LEGACY=1 py -3 tools/build.py` and install (dev or release plugin: the part is on in both). In the
   install's `d2rloader\config\d2rloader.toml` set `always_enable_rotw_legacy_graphics_keybind = true` (G in a RotW game).
2. Start a **RotW** character in a RotW game. Type `mxl2012` in the console: the `rotwstash` line must say "rotwstash on" and
   **"game type 3"** (2 means a LoD game: the RotW tabs will not show, as in HD).
3. In HD put a few gems, runes, materials (a key, an essence) into the Gems / Materials / Runes tabs, and an item into the stash
   cube window. Close the stash.
4. Open the stash on Personal and press **G**. Expected: no crash, five tabs. `mxl2012` again: "classic: pages wired" went up
   by one.
5. Click each tab in classic: Gems, Materials, Runes show their page art, each stored item in its recess with its count, and no
   Personal / Shared grid or gold on them; Personal / Shared show no RotW slots. The cube window: its cover and its items, the
   Transmute and Withdraw buttons (bug #515: only a 3 x 4 window).
6. Move a gem from the inventory onto the Gems tab and take one out (the notify mark on the tab). Press G back to HD with a RotW
   tab open, then G again with Runes open.
7. `mxl2012` once more: "item pictures skipped" should stay 0 (more than 0 means a slot found an item without its picture
   record: tell us, with a screenshot of that page).
8. If anything crashes: keep the file from `d2rloader\crashes\` and the `mxl2012` line, and note the tab and graphics mode.
   As a check, the dev plugin with `MXL_ROTWSTASH_TEST=never` must crash on step 4 (D2R's own rule), and with `=rotw` must
   behave like the default here (it wires only in a RotW game).
9. Report to bug #516 (and #515 for the cube window). If it all works, `MXL2012_ROTW_LEGACY` can become the default.

## Lane kurast: the Kurast temple entrances 81->97 and 82->99 (bug #518, 2026-10-31, slot 3, background mode, build of lane/kurast)

From lane acts25 (run `checks-20261030-210750-s4`): Upper Kurast (81) -> Forgotten Temple (97) and Kurast Causeway (82) -> Disused
Reliquary (99) did not take the character in; 82 -> 98 (Ruined Fane) did. Probe: `mxl2012-runs/kurast/kurast_probe.py` (check `kprobe`,
imports game_checks: per temple a server warp in, acts25's own way out by clicks, then the walk collision (`walkmap`, step 1) and the
objects round the entrance tile, a shot, and the way in). Paladin, level 114, god mode.

| Run | Build | What | Result |
|---|---|---|---|
| `checks-20261031-141642-s3` (`probe1.log`) | before | legacy; A: clicks on the tile from the exit spot, B: walk 9-13 away, then clicks | 97, 99 not entered (held at tile x+1); 98 entered (control). An object class 194 (UnfoldingStairLeft) in mode 0 stands in both blocked doorways, none at 98 |
| `checks-20261031-143451-s3` (`probe2.log`) | before | legacy + HD; every free cell within 8 of the tile, a click then `move` | 97, 99 not entered in either mode (so not the click projection or the harness); 98 entered |
| `checks-20261031-150631-s3` (`probe3.log`) | after (stair Token `9c`) | legacy + HD, cells | 99 entered (legacy cell 0,-1; HD 0,0), 97 entered (legacy +5,-1; HD +4,0), 98 entered in legacy; HD 98: the SET-UP way out from inside failed (class 62), not judged |
| `checks-20261031-151721-s3` (`probe4.log`) | after | legacy + HD, acts25's own `up_enter` | PASS in both modes: 81<->97, 82<->99, 82<->98 entered (and left again by clicks) |

Cause and fix: bugs.md #518 (objects.txt row 194 Token `sl` -> D2R's `9c` in `tools/txt_migrate.py`). Shots and reports per run:
`mxl2012-runs/kurast/evidence/before/<run>/`, `.../after/<run>/` (`kp_<src>_<dest>_<gfx>_*.png`).

Open: the way out from inside a temple by clicks failed now and then (acts25: 95->80 class 63, 96->81 class 62; here 96 in run 1 and
98 in HD run 3) and worked in the next run. Not looked into in this lane. Also seen, left alone: objects rows 78 (Town1Ambient, Token
`TA`) and 133 (ShrineMagicArcaneSanctuary1, `xx`) carry tokens D2R has no art for (maybe Median's intent; neither blocks a way).

## Lane stashtab: RotW stash tab names that fit in classic (bug #516, 2026-10-31, slot 2, background mode)

The step's classic tab bar (five 63 x 24 tabs, docs/legacy-graphics.md 9.7) showed D2R's own tab text cut: "PERSON",
"MATERIAL:". Now the step draws the names into the tab art (D2R's classic `font6`, capitals, 10 frames) and D2R's text is
left out (empty, and clear for the Personal name D2R writes itself). Build of lane/stashtab, dev plugin, mod by the normal
`py -3 tools/build.py` (the layout is in the mod by default since main 23afb64). Character `StashTab` (Sorceress,
`mxl2012-s2`, no RotW, so only Personal / Shared show). Each run: stash opened in HD by the harness, G to classic, a click on
Shared, a click on Personal, G back to HD. Scratch driver (outside git): `mxl2012-runs/stashtab/{drv,shot,variant}.py`.

| run | classic layout on slot 2 | result |
|---|---|---|
| `checks-20261031-180133-s2` (before) | the step's layout as on main | "PERSON" (cut), "SHARED" |
| `checks-20261031-180430-s2` | + `textStyle` `pointSize` 8 (by hand) | unchanged: classic takes no point size |
| `checks-20261031-180628-s2` | + `textStyle` `spacing` `kerning` 0.75 (by hand) | unchanged |
| `checks-20261031-180800-s2` | + `tabSizingMethod` `fitToContent` (by hand) | no tabs drawn |
| `checks-20261031-181401-s2` | names in the art, `textStrings` empty | Shared fine; Personal shows D2R's "PERSON" over the drawn name |
| `checks-20261031-181550-s2` | + text colours clear (by hand) | PERSONAL and SHARED whole |
| `checks-20261031-182828-s2` (final, normal build, nothing by hand) | the step's layout of this branch | **PASS**: PERSONAL (gold, active) and SHARED (white) whole and readable in classic, the active one swaps on the clicks, the Shared page as before ("Shared with offline characters"); HD stash unchanged |

0 crash files, d2rloader.log 0 ERROR / ASSERT lines, mxl2012-core.log nothing new at the last stop. Gems / Materials / Runes
cannot show on these accounts (no RotW); their names are checked by the step (`tab names in font6: PERSONAL 48, SHARED 37,
GEMS 25, MATERIALS 52, RUNES 31 (room 57)`) and seen in the review sheet `mxl2012-runs/stashtab/sheet/rotwstash_*.png`.
Unit tests `tools/tests/test_rotw_stash_legacy.py`: 9 OK (new: `test_tab_names_fit`, `test_named_frames_carry_the_names`,
`test_build_with_the_classic_font`). Evidence: `mxl2012-runs/stashtab/evidence/` (the run folders above; `crops/` the tab bar
x2: `before_*`, `final_*`, the trial crops).
