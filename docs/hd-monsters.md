# HD monster stand-ins for D2R-XL 2012 (lane `hdmon`, 2026-10-28)

D2R's HD renderer needs a model per monster. Median XL 2012 draws its monsters from classic DCC/COF art (108 art sets, tokens like
`!!`, `9x`, `~k`), which D2R cannot show. Until real HD models exist, every monster of the mod gets a **stand-in**: an existing D2R
HD unit, rescaled and recoloured. Nothing here is new art; no model, texture or Median file is touched.

Tool: `tools/hd_monsters.py` (build step, section 5). Mapping (our own work, no Median art): `tools/data/hd_monster_tokens.json`
(generated), hand picks and reasons: `tools/data/hd_monster_pins.json`. Output of `build` goes to the ignored `work/hd_monsters/`.
Format notes: units are plain JSON (parts, state machine, variant colour table); models are Granny files.

## 1. Result

**Token** = the monstats `Code` of a monster = the folder name `data/global/monsters/<token>/` (checked: every one of the 1,822 monstats
rows has a `Code`; monstats2 is reached through `MonStatsEx`; 1,821 rows have a monstats2 row, `cougar` has none).
The mod's monstats uses 317 distinct tokens (309 on monstats rows, 8 more are art folders no row uses):

| Class | Tokens | Monstats Ids | What it means |
|---|---:|---:|---|
| vanilla | 209 | 1,549 | D2R already has the art of the token: its own HD unit (206 tokens have no art in the mod at all; `e9` `iw` `rt` have a Median copy of the same files) |
| split | 1 | 2 | `ks`: Slayer / Slayer 2, split from `e9` (own token, section 5.1). Vanilla rule of the token they were split from: the unit stays `wakeofdestruction` |
| mixed | 2 | 6 | `fm`, `im`: D2R has the art, the mod asks for a few more mode COFs. Vanilla rule for the Ids D2R has a unit for; 4 Median-only Ids take a stand-in |
| reused | 86 | 246 | the same art set already has a chosen stand-in in the reference mapping: reused (section 3) |
| new | 9 | 13 | 2012 art with no usable reference mapping: hand-picked closest D2R unit (section 4) |
| noart | 3 | 6 | `am`, `dz`, `so`: used by monstats, no art in the mod or in D2R |
| unused | 8 | 0 | art folders (`!k !z &6 @d ^t oy t^ ~5`) that no monstats row uses: nothing to map |

Of the 109 art sets (`ks` is the Median `e9` set under its own token): 101 are used by monstats (86 reused + 9 new + `fm` `im` + `e9` `ks` `iw` `rt`), 8 are not.
The 98 tokens that get a donor (reused + new + noart): **42 high, 46 medium, 10 low** confidence (46 high / 42 medium before lane hdmon3's re-picks, section 11) (low: `!!`, `2(`, `3#`, `7$`, `9!`,
`m+`, `x+` and the three `noart` tokens; since lane hdmon2, section 8). Confidence is the reference rule (family and body plan match, size ratio) for scored picks, mine for pins.
The same numbers are in `tools/data/hd_monster_tokens.json` (`counts`) and in the tables below.

### Coordinator's survey, checked

`docs/graphics-inventory.md` counted 93 shared token folders and 15 without a reference folder. Re-checked against byte content
(`tools/hd_monsters.py classify`):

- 93 tokens have a folder in both: **90 are byte-identical** in every 2012 file (73 with the same file set, 17 where the reference only adds
  files), **3 differ**: `!1` (a different creature, see below), `!h` (one of 14 DCCs differs) and `!k` (unused in 2012).
- **`!1` (Quest Lucion) is a different monster in the reference art**: 2012's is a large multi-legged crawling demon, the reference `!1` is a flame.
  The reference stand-in (`gorgon1`) is wrong for it, so it is class `new`. This is why the reuse rule is "same art", not "same token".
- Of the 15 sets without a reference folder, 7 are unused by monstats (`!z &6 @d ^t oy t^ ~5`); 8 are used (`!e 7$ 8@ 9$ ie k+ m+ x+`), plus
  `!1` makes 9 `new` tokens.
- "token == monstats Code" holds, with two corrections: 8 art folders have no monstats row (above), and 3 tokens used by monstats have
  no folder in the MPQ and no art in D2R (`AM`, `DZ`, `SO`).
- D2R has the classic art of some tokens (`2d 3d 4d bu` ...) that the 2012 mod uses without shipping it; those are `vanilla`.

## Death states (bugs.md #34)

D2R binds an HD unit's animations by weapon class (`animationBindings` per state) and plays the death animation from the class of the death COF. Median ships death COFs for hth only, so `hd_units.adapt_state_machine` also binds hth on every Death / Dead state that lacks it (`death_lacks_hth`; today only the cr_archer1 machine: `sm_cr_archer1_death.json`). Without it the Amazonites (token `9x`) stood in the bind pose after `kill`. `tools/death_cofs.py` additionally derives `9xdtbow` / `9xddbow` COFs and animdata records (not needed for HD).

## Shared colour tables (bugs.md #360)

Each stand-in colour is a VariantTransformTable (`data/hd/character/enemy/mxl/v_<hash>.json`). D2R keeps these in a cache of 128
(Fog `AssetCache<VariantTransformTable, 128>`), and entering an act loads the tables of every monster its levels can spawn: with
one table per colour (93), Act 1 alone held 113 tables (40 ours) and a five-town session overflowed it (`BC_ASSERT: 0`,
AssetCache.h:187). `build` now lets close colours share a table (`share_colours`, `COLOUR_SHARE_TOL` 0.2: hue within 0.1 turn,
saturation, value and tint within 0.2): the most used colours (by monstats Ids) are kept and every other colour takes the nearest
kept one, so 24 tables remain. The token tables below keep each token's own colour; `work/mod/hd_monsters.md` names the shared one
("shared table: ..."). Live counts: `tools/cache_probe.py counts` on a running game. Since lane tints2 (section 10) donors with a
level0 look of their own get tables of their own; `COLOUR_TABLE_LIMIT` (30) caps all colour tables (30 in the build).

Headroom (lane cachewalls, docs/testing.md "Lane cachewalls"): with 30 tables the cache peaked at 102 (HD) and 104 (classic) on a
40-step route through all five acts and at 106 in `wall_maps`; D2R's own tables are 82-85 of that and about 70 % of ours are
loaded at the peak, so roughly 50 tables would reach 120 of 128. Keep `COLOUR_TABLE_LIMIT` at 50 or below, and measure with
`MXL_CACHE_POLL=3` after raising it.

## Token tables (generated by `tools/hd_monsters.py doc`)

<!-- tokens:begin -->

### new (9 tokens)

| Token | Stand-in (D2R unit) | Scale; colour | Confidence | Monsters | Source / reason |
|---|---|---|---|---|---|
| `!1` | arach1 | x1.35; hue +0.03 sat +0.20 val +0.25 | medium | `quest_lucion` | pin: Quest Lucion: 2012's art is a large multi-legged crawling demon (161x116 px); the same token is a flame in the reference art, so the reference stand-in (gorgon1) doe |
| `!e` | baalminion1 | x1.15; hue -0.05 sat +0.12 val -0.02 | medium | `azmo_special` | pin: Azmo special (Dominator): red horned biped demon with a large curved blade, 104x138 px |
| `7$` | wolf | x0.9; hue -0.00 sat +0.05 val +0.29 | low | `cougar` | pin: Trained Cougar: tan big cat on four legs (94x59 px) |
| `8@` | goatman1 | x1; none | medium | `hornedgods` | pin: Horned God: small horned humanoid with a mace and S8 part (58x76 px): the D2R goatman is the horned biped with a weapon; same pick the reference made for the Wereo |
| `9$` | spiritwolf | x0.85; hue -0.00 sat -0.23 val -0.09 | high | `companion` | pin: Wolf companion: small grey wolf (40x38 px): the Druid's spirit wolf is the same animal and colour |
| `ie` | frozenhorror1 | x1.1; hue -0.09 sat -0.22 val -0.18 | medium | `shardspawn` | pin: Shardspawn: hunched crystalline ice creature (79x111 px, blue-white) |
| `k+` | ancientbarb1 | x1.5; hue +0.00 sat +0.12 val +0.14 | medium | `sonofhefaestusM`, `sonofhefaestusM2` | pin: Veteran Son of Hefaestus: tall, muscular, bare-chested human fighter (boss, 75x170 px) |
| `m+` | irongolem | x1.5; hue +0.01 sat +0.16 val -0.15 | low | `bronzeguardian1`, `bronzeguardian_elite`, `uq_bronzeguardian_elite` | pin: Guardian / Sacred Construct: bronze segmented construct with a raised sword (41x114 px) |
| `x+` | arach1 | x1.2; hue +0.01 sat -0.13 val +0.36 | low | `psychorbM`, `psychorbM2` | pin: Veteran Psychorb: round fleshy body with several eye stalks and a mouth (101x106 px); it walks, attacks and casts |

### noart (3 tokens)

| Token | Stand-in (D2R unit) | Scale; colour | Confidence | Monsters | Source / reason |
|---|---|---|---|---|---|
| `hn` (was `am` / `dz` / `so`) | cr_archer1 (the unit itself) | x1; none | low | the six `haunt_*` | The six Haunts' tokens AM / DZ / SO (player class codes) have no art in the MPQ or in D2R; since lane fixes3 they draw D2R's Corrupt Rogue archer under their own token HN (tools/own_tokens.py `borrow`, docs/legacy-graphics.md section 6) and HD binds D2R's `cr_archer1` unit as it is (bugs.md #74) |

### reused (86 tokens)

| Token | Stand-in (D2R unit) | Scale; colour | Confidence | Monsters | Source / reason |
|---|---|---|---|---|---|
| `!!` | wraith1 | x1; hue -0.27 sat -0.17 val -0.52 | low | `glowingM`, `glowingM2` | pin: lane hdmon2 (Act 1-2 pass): Glowing one: hunched dark green figure with a glowing head (52x83 px) |
| `!2` | councilmember1 | x0.75; hue +0.43 sat -0.04 val +0.51 | medium | `sumelite_1269`, `midnightfaes`, `darkfey1` +3 | pin: Small green-haired fey woman (Midnight Faes, Dark Fey): the reference modal donor (maggotbaby1) came from other monsters on the token; a small robed human |
| `!3` | clawviper1 | x1; hue +0.42 sat -0.46 val +0.05 | high (review) | `res_couatlchild1`, `res_couatlchild2`, `res_couatlchild3` +3 | reused donors, 2012 names: the reference rows for this art disagree (43% for clawviper1, others {'sk_archer1': 2, 'nihlathakboss': 2}); 2012 monster names pick clawviper1 among them |
| `!4` | clawviper1 | x1.4; hue +0.42 sat -0.10 val +0.05 (hand) | medium | `sumelite_1261`, `couatlfather1`, `couatlfather2` +3 | pin: lane hdmon3 (Act 3-5 pass): Couatl (NiVa, Couatl fathers): upright feathered serpent with a humanoid torso (82x116 px) |
| `!5` | councilmember1 | x1; hue -0.03 sat +0.12 val +0.25 | high | `sumelite_1273`, `res_cultist1`, `cultist1` +4 | reused: same art files; reused donor councilmember1 (11 rows, 84% agree) |
| `!6` | firegolem | x0.8; none | medium | `jinns` | pin: Jinn: a flame-bodied spirit; the reference pick (firegolem) kept, confirmed on the art. |
| `!7` | fetishblow1 | x1.7; hue -0.03 sat +0.05 val +0.60 | medium (review) | `sarandesh1`, `sarandesh_elite`, `uq_sarandesh_elite` | reused donors, 2012 names: the reference rows for this art disagree (67% for fetishblow1, others {'irongolem': 1}); 2012 monster names pick fetishblow1 among them |
| `!8` | thornhulk1 | x0.9; hue -0.02 sat +0.02 val +0.44 | medium | `sumelite_1282`, `treeppl1`, `treeppl2` +1 | pin: Tree Folk: big gnarled walking tree; the Thornhulk is D2R's tree giant |
| `!9` | doomknight1 | x1.1; hue +0.00 sat +0.00 val +0.20 (hand) | medium | `veilkings`, `veilking_rean` | pin: Veil King: a crowned skeleton king with a long sword, gold-yellow bones and crown, black pauldrons and torso (75x127 px) |
| `!a` | batdemon1 | x1.4; hue +0.00 sat -0.68 val +0.18 | medium | `sumelite_1333`, `gargoylebeast1`, `gargoylebeast2` +2 | pin: Gargoyle Beast: winged grey demon; the Bat Demon is D2R's winged fiend (the reference modal donor was quillbear1, a bear). |
| `!d` | willowisp1 | x1.2; hue +0.00 sat -0.00 val -0.11 | high | `darkstardragon`, `reandarkstar` | reused: same art files; reused donor willowisp1 (3 rows, 100% agree) |
| `!h` | suicideminion1 | x1.15; hue +0.21 sat -0.09 val +0.46 | high (review) | `hostileleprechaun` | reused donors, 2012 names: the reference rows for this art disagree (50% for suicideminion1, others {'vilemother1': 1}); 2012 monster names pick suicideminion1 among them |
| `!i` | willowisp1 | x1.25; hue +0.00 sat +0.36 val -0.37 tint 0.40 | high | `cubedragon1`, `cubedragon2`, `cubedragon3` +2 | reused: same art files; reused donor willowisp1 (4 rows, 100% agree) |
| `!s` | bloodlord1 | x1; hue -0.28 sat -0.16 val +0.11 | medium | `brainpower`, `malewitch`, `malewitch_trist` | pin: lane hdmon3 (Act 3-5 pass): Howling (brainpower, Act 5 Hell 2): dark purple ghost with scythe claws (100x114 px) |
| `#0` | thornhulk1 | x0.7; hue +0.04 sat +0.20 val +0.70 | medium | `sumelite_1307`, `troll1`, `troll2` +2 | pin: lane hdmonlook (in game): Troll: tall lanky olive-yellow troll with long arms and claws |
| `#5` | clawviper1 | x1; hue +0.06 sat -0.18 val +0.16 | high | `sumelite_1281`, `creepshow1`, `creepshow2` +2 | reused: same art files; reused donor clawviper1 (5 rows, 80% agree) |
| `#6` | snowyeti1 | x0.5; hue +0.00 sat +0.49 val -0.04 tint 0.46 | medium | `thepack_elite`, `thepack_elite2` | reused: same art files; reused donor snowyeti1 (3 rows, 100% agree) |
| `#i` | cantor1 | x1; hue +0.05 sat -0.12 val +0.35 | medium | `sunlessreveler` | pin: Sunless Reveler: robed caster with a staff; not skeletal (reference: skmage_cold1). |
| `#l` | irongolem | x1; none | medium | `combatdrone2` | pin: lane hdmon3 (Act 3-5 pass): Light Drone (Act 3 Temple 2): slimmer white walking machine (49x77 px), the Heavy Drone's small twin |
| `#m` | baalminion1 | x0.75; hue -0.02 sat -0.21 val +0.09 | medium | `belial` | pin: lane hdmon3 (Act 3-5 pass): Belial (Act 5 Ice Cave boss): hunched horned demon with claws (53x86 px) |
| `#q` | arach1 | x0.85; hue +0.03 sat +0.04 val +0.65 | medium | `cube1` | pin: lane hdmon3 (Act 3-5 pass): Enforcer with Laser (Act 3 Temple 2): tan machine on long jointed legs (87x72 px) |
| `#r` | scarab1 | x1.3; hue +0.05 sat +0.18 val +0.70 | high | `cube2` | reused: same art files; reused donor scarab1 (3 rows, 100% agree) |
| `#w` | councilmember1 | x1; hue +0.03 sat -0.09 val +0.34 | medium | `robedagger` | pin: lane hdmon2 (Act 1-2 pass): Robe Dagger: hooded robed figure (45x77 px) |
| `#y` | zombie1 | x1.4; hue +0.00 sat -0.70 val +0.25 (hand) | high | `zombierags` | pin: lane hdmon2 (Act 1-2 pass): Zombie Rags: tall thin ragged zombie (25x84 px) |
| `$a` | wraith1 | x1; hue +0.00 sat -0.26 val -0.05 | high | `veilterror_rean` | reused: same art files; reused donor wraith1 (3 rows, 100% agree) |
| `$f` | vampire1 | x1.4; hue +0.00 sat +0.08 val +0.70 | medium | `rathma_primus` | pin: lane hdmon3 (Act 3-5 pass): Rathma Primus (Act 3 superunique): pale winged humanoid caster (68x109 px, wings included) |
| `$g` | barricadewall2 | x1.85; hue -0.01 sat +0.02 val +0.11 | medium | `mcsboss` | reused: same art files; reused donor barricadewall2 (1 rows, 100% agree) |
| `$h` | bonefetish1 | x1.85; hue +0.00 sat +0.32 val +0.19 tint 0.40 | medium | `sunlessmutant` | reused: same art files; reused donor bonefetish1 (1 rows, 100% agree) |
| `%4` | quillrat1 | x1.55; hue -0.04 sat -0.01 val +0.08 | medium | `henchman`, `evil1spw` | pin: Henchman / Evil 1 SPW: a large rat on the art; the Quill Rat is D2R's rat (rescored pick was warputriddefiler x0.5). |
| `%9` | clawviper1 | x1.5; hue +0.02 sat -0.15 val +0.03 | medium | `mahasattva`, `uq_mahasattva` | pin: lane hdmon3 (Act 3-5 pass): Mahasattva: multi-armed naga, snake tail and a humanoid torso with weapons (87x131 px) |
| `&b` | vulture1 | x1.2; hue +0.00 sat -0.50 val +0.70 tint 0.50 (hand) | medium | `sumelite_1290`, `deathwing1`, `deathwing2` +1 | pin: lane hdmon2 (Act 1-2 pass): Deathwing: bony winged flyer (76x58 px) |
| `&d` | mummy1 | x0.5; hue -0.11 sat +0.57 val +0.70 | medium | `blotM_stage4`, `blotM_stage3`, `blotM_stage2` +1 | reused: same art files; reused donor mummy1 (6 rows, 100% agree) |
| `&g` | irongolem | x1.3; hue +0.00 sat +0.12 val -0.01 | medium | `combatdrone1` | pin: lane hdmon3 (Act 3-5 pass): Heavy Drone (Act 3 Temple 2): bulky grey walking machine with a gun arm (85x83 px) |
| `(0` | doomknight2 | x1.25; hue -0.10 sat -0.19 val +0.05 | high | `dragonknight3`, `su_dragon3`, `baalset_dragon3` +1 | pin: lane hdmon3 (Act 3-5 pass): Dragon knight (Coldkill Iceguard, Act 5 Baal temple and World Stone): horned armoured knight with a long sword (109x95 px) |
| `(1` | doomknight2 | x1.25; hue +0.44 sat -0.31 val +0.09 | high | `quest_inarius`, `res_dragonknight2`, `dragonknight2` +1 | pin: lane hdmon2 (Act 1-2 pass): Dragon knight (Inarius, Hell Dragonknight): armoured knight with a long sword (109x102 px) |
| `(2` | doomknight2 | x1.25; hue -0.14 sat +0.17 val +0.24 | high | `res_dragonknight1`, `dragonknight1` | reused: same art files; reused donor doomknight2 (3 rows, 100% agree) |
| `(a` | quillrat1 | x1.3; hue -0.05 sat -0.11 val +0.34 | high | `porkulated` | reused: same art files; reused donor quillrat1 (2 rows, 100% agree) |
| `(c` | clawviper1 | x0.9; hue +0.03 sat -0.52 val -0.27 | high | `junglesnake` | reused: same art files; reused donor clawviper1 (1 rows, 100% agree) |
| `(g` | druidhawk | x0.8; hue +0.00 sat -0.10 val +0.69 | high | `flit1`, `flit_summoned1`, `flit_summoned2` +1 | reused: same art files; reused donor druidhawk (4 rows, 82% agree) |
| `(i` | scarab1 | x0.85; hue +0.01 sat +0.07 val +0.31 | high (review) | `firebeetle` | reused donors, 2012 names: the reference rows for this art disagree (67% for scarab1, others {'mummy1': 1}); 2012 monster names pick scarab1 among them |
| `(l` | deathmauler1 | x1.15; hue -0.02 sat +0.03 val -0.26 | high | `sumelite_1286`, `res_magmademon1`, `res_magmademon2` +7 | reused: same art files; reused donor deathmauler1 (13 rows, 100% agree) |
| `(m` | wraith1 | x0.8; hue -0.02 sat -0.11 val +0.27 | medium (review) | `shadows_new` | reused donors, 2012 names: the reference rows for this art disagree (50% for irongolem, others {'wraith1': 1}); 2012 monster names pick wraith1 among them |
| `(n` | arach1 | x1.2; hue +0.00 sat -0.33 val -0.19 | high | `astrogha` | reused: same art files; reused donor arach1 (4 rows, 100% agree) |
| `(o` | brute2 | x1; hue -0.02 sat +0.19 val +0.04 | medium (review) | `sumelite_1302`, `berserk1`, `berserk2` +3 | reused donors, 2012 names: the reference rows for this art disagree (67% for doomknight1, others {'brute2': 2}); 2012 monster names pick brute2 among them |
| `(r` | hephasto | x0.9; hue -0.04 sat -0.06 val +0.21 | medium | `feyr` | reused: same art files; reused donor hephasto (1 rows, 100% agree) |
| `(s` | blunderbore1 | x1.65; hue -0.02 sat -0.32 val +0.01 | medium | `giant1`, `giant2` | pin: Giant: huge muscular human giant; Blunderbore is D2R's giant (reference: hellbovine, a minotaur). |
| `(x` | frogdemon1 | x1; hue +0.19 sat +0.06 val +0.21 | medium | `sumelite_1295`, `slimer1`, `slimer2` | pin: Slimer: green frog-like humanoid; Frog Demon (2 of the 7 reference rows). |
| `0!` | summoner | x0.8; hue +0.00 sat -0.21 val +0.20 | high (review) | `quest_subboss`, `super_tehboss`, `quest_malic` | reused donors, 2012 names: the reference rows for this art disagree (55% for councilmember1, others {'summoner': 2}); 2012 monster names pick summoner among them |
| `0(` | wolf | x1; hue -0.00 sat -0.13 val -0.18 | high | `fallenwolf1`, `fallenwolfE` | reused: same art files; reused donor wolf (3 rows, 100% agree) |
| `08` | warputriddefiler | x0.85; hue +0.01 sat +0.16 val +0.01 | high | `fellfiend1`, `fellfiend2`, `baalset_fellfiend2` | reused: same art files; reused donor warputriddefiler (4 rows, 100% agree) |
| `0k` | maggotbaby1 | x1.5; hue +0.03 sat -0.38 val +0.22 | medium | `res_corpseworm`, `corpseworm` | pin: lane hdmon2 (Act 1-2 pass): Corpse Worm: pale segmented larva (87x70 px) |
| `0n` | sandraider1 | x1.15; hue +0.03 sat -0.09 val -0.02 | high | `sumelite_1275`, `res_onyxknight`, `onyxknight1` +4 | reused: same art files; reused donor sandraider1 (18 rows, 92% agree) |
| `1!` | sandraider1 | x0.8; hue -0.00 sat -0.03 val +0.47 | medium | `l_priest` | pin: lane hdmonlook: Priest: armoured human fighter with blades (41x75 px), the same classic art as the Harlequin 2! in other colours, so the same donor and scale as |
| `1c` | hephasto | x0.85; hue +0.00 sat -0.49 val -0.31 | high | `shadowcreeperM`, `shadowcreeperM2` | reused: same art files; reused donor hephasto (4 rows, 75% agree) |
| `2!` | sandraider1 | x0.8; hue +0.25 sat -0.10 val +0.20 (hand) | medium | `sumelite_1291`, `res_harlequin1`, `harlequin1` +1 | pin: lane hdmon3 (Act 3-5 pass): Harlequin (Act 4): armoured human fighter with blades (41x75 px; the same art as the Priest 1! in other colours) |
| `2#` | summoner | x0.8; hue -0.03 sat +0.30 val +0.51 | high | `omgitslaz`, `l_slayer` | reused: same art files; reused donor summoner (24 rows, 100% agree) |
| `2(` | thornhulk1 | x0.75; hue -0.49 sat -0.03 val +0.60 | low | `sumelite_1272`, `fungus1`, `fungus2` +1 | pin: Fungus man: biped with a big blue mushroom cap (small); the plant-like Thornhulk is the nearest vegetable biped (the reference pick was boneprison3, a prop). |
| `3#` | spiritwolf | x1.8; hue +0.01 sat -0.16 val +0.16 | low | `nighthorse` | pin: lane hdmon2 (Act 1-2 pass): Nighthorse: skeletal horse on four legs (82x90 px) |
| `5$` | siegebeast1 | x1.5; hue -0.02 sat +0.09 val -0.02 | high | `porkchop_elite`, `porkchop_elite2` | reused: same art files; reused donor siegebeast1 (3 rows, 100% agree) |
| `5(` | deathmauler1 | x1; hue -0.04 sat -0.07 val -0.10 | high (review) | `toraja_morlufiend` | reused donors, 2012 names: the reference rows for this art disagree (50% for deathmauler1, others {'doomknight2': 9}); 2012 monster names pick deathmauler1 among them |
| `7#` | councilmember1 | x1; hue +0.03 sat +0.13 val +0.68 | high | `sirens` | reused: same art files; reused donor councilmember1 (1 rows, 100% agree) |
| `8#` | regurgitator1 | x0.8; hue -0.01 sat -0.17 val +0.16 | high | `oathbreaker_rean` | reused: same art files; reused donor regurgitator1 (1 rows, 100% agree) |
| `8$` | sk_archer1 | x1.15; hue -0.00 sat -0.47 val -0.57 | high | `morph_blackpanther`, `blackpantherM`, `blackpantherM2` +1 | reused: same art files; reused donor sk_archer1 (3 rows, 100% agree) |
| `9!` | clawviper1 | x1.3; hue +0.00 sat -0.90 val +0.30 tint 0.45 (hand) | low | `sumelite_1309`, `res_centaur1`, `res_centaur2` +4 | pin: lane hdmon2 (Act 1-2 pass): Centaur: horse body, human torso with a spear (101x97 px) |
| `9(` | councilmember1 | x0.9; hue +0.10 sat -0.14 val +0.31 | high (review) | `runepriest1`, `runepriest2`, `hell_runepriest` +2 | reused donors, 2012 names: the reference rows for this art disagree (47% for foulcrow1, others {'councilmember1': 1, 'goatman1': 2}); 2012 monster names pick councilmember1 among them |
| `9x` | cr_archer1 | x0.75; hue -0.00 sat +0.33 val +0.53 | high (review) | `karcheuspriestess`, `hefaetruspriestess`, `zeraepriestess` +1 | reused donors, 2012 names: the reference rows for this art disagree (64% for sk_archer1, others {'cr_archer1': 10, 'foulcrow1': 1}); 2012 monster names pick cr_archer1 among them |
| `@1` | wraith1 | x1.4; hue -0.00 sat -0.26 val -0.18 | medium | `vengeances`, `l4dwitch`, `l4dwitch2` | pin: Vengeance / L4D Witch: pale long-haired ghostly woman; Wraith (the reference modal donor was colbarbwhirl, a barbarian). |
| `@3` | fallenshaman1 | x1.6; hue +0.08 sat -0.10 val +0.25 (hand) | high | `orkshaman` | pin: lane hdmon2 (Act 1-2 pass): Orc Shaman: small hunched horned caster (41x66 px) |
| `@5` | warputriddefiler | x0.9; hue +0.03 sat +0.33 val +0.45 | medium | `assur` | reused: same art files; reused donor warputriddefiler (12 rows, 88% agree) |
| `@6` | firegolem | x1.1; none | medium | `sumelite_1311`, `firewizard1`, `firewizard2` +7 | pin: lane hdmon2 (Act 1-2 pass): Fire Wizard: a humanoid of living flame (65x89 px) |
| `@c` | zombie1 | x1.15; hue +0.02 sat +0.04 val -0.36 | high | `greenzombie` | pin: lane hdmon2 (Act 1-2 pass): Green Zombie: a shambling zombie (24x70 px) |
| `@e` | summoner | x0.85; hue -0.01 sat +0.34 val +0.65 | high (review) | `friendlyelvensong`, `faewitchM`, `faewitchM2` | reused donors, 2012 names: the reference rows for this art disagree (60% for summoner, others {'vilemother1': 1, 'darkwanderer': 1}); 2012 monster names pick summoner among them |
| `@f` | brute2 | x1.2; hue +0.02 sat -0.04 val +0.19 | high (review) | `sumelite_1262`, `bugbear1`, `bugbearE` +2 | reused donors, 2012 names: the reference rows for this art disagree (67% for brute2, others {'thornhulk1': 3}); 2012 monster names pick brute2 among them |
| `^3` | wolf | x0.9; hue +0.00 sat +0.02 val +0.13 | high | `sumelite_1316`, `res_wyrdwolf1`, `wyrdwolf1` +2 | reused: same art files; reused donor wolf (5 rows, 100% agree) |
| `b#` | cantor1 | x1; hue +0.03 sat +0.15 val +0.70 | high | `sumelite_1268`, `sumelite_1284`, `crystal1` +2 | reused: same art files; reused donor cantor1 (7 rows, 86% agree) |
| `c#` | firegolem | x0.9; hue -0.02 sat -0.24 val -0.12 | high | `totembounds` | reused: same art files; reused donor firegolem (1 rows, 100% agree) |
| `c@` | councilmember1 | x1.1; hue +0.03 sat -0.05 val +0.47 | medium | `cloakdagger` | pin: lane hdmon2 (Act 1-2 pass): Cloak Dagger: hooded robed figure (40x82 px), the twin of Robe Dagger |
| `g7` | brute2 | x0.55; hue -0.00 sat +0.02 val +0.21 | medium (review) | `sumelite_1287`, `res_pest1`, `pest1` +3 | reused donors, 2012 names: the reference rows for this art disagree (56% for brute2, others {'councilmember1': 2}); 2012 monster names pick brute2 among them |
| `ji` | sandraider1 | x0.85; hue -0.02 sat +0.16 val +0.46 | medium | `dead3`, `res_dead3` | pin: lane hdmon2 (Act 1-2 pass): Dead (dead3): turbaned undead swordsman with a scimitar (64x87 px) |
| `n#` | act5pow | x1; hue +0.02 sat -0.00 val +0.54 | medium | `saclamb` | pin: Sacrificial lamb: peasant in an orange tunic; the Act 5 prisoner of war is the same kind of human (reference pick kept). |
| `~2` | brute2 | x1; hue +0.04 sat +0.03 val +0.02 | high (review) | `sumelite_1292`, `cavetroll1`, `cavetroll_elite` +1 | reused donors, 2012 names: the reference rows for this art disagree (62% for brute2, others {'painworm1': 3}); 2012 monster names pick brute2 among them |
| `~3` | cantor1 | x1.15; hue +0.01 sat +0.22 val +0.41 | high | `magineer` | reused: same art files; reused donor cantor1 (4 rows, 75% agree) |
| `~b` | hephasto | x1.15; hue -0.02 sat +0.11 val -0.14 | medium | `rampagors_new`, `landmassM`, `landmassM2` | reused: same art files; reused donor hephasto (4 rows, 75% agree) |
| `~k` | bonefetish1 | x2.3; hue -0.01 sat +0.44 val +0.21 tint 0.44 | medium | `hardliner` | reused: same art files; reused donor bonefetish1 (1 rows, 100% agree) |
| `~m` | quillrat1 | x0.5; hue -0.03 sat -0.03 val +0.35 | medium (review) | `attackrat`, `rean_attackrat` | reused donors, 2012 names: the reference rows for this art disagree (50% for bonefetish1, others {'snowyeti1': 2, 'quillrat1': 1}); 2012 monster names pick quillrat1 among them |
| `~z` | baalminion1 | x1; hue -0.05 sat +0.01 val -0.23 | medium | `dark_master1`, `dark_master2`, `r_darkmaster1` +1 | reused: same art files; reused donor baalminion1 (17 rows, 100% agree) |

### mixed (2 tokens)

| Token | D2R unit | Monsters | How |
|---|---|---|---|
| `fm` | - | `firebeast`, `regu_elemental` | D2R has no HD unit for this token; 1 Median-only Ids (regu_elemental) get claygolem x1 (low) |
| `im` | - | `iceglobe`, `ulti_elemental`, `necromorb` +1 | D2R has no HD unit for this token; 3 Median-only Ids (ulti_elemental, necromorb, lantern) get claygolem x1 (low) |

### split (1 tokens)

| Token | D2R unit | Monsters | How |
|---|---|---|---|
| `ks` | wakeofdestruction | `slayer2`, `slayer` | own token, split from `e9`: best of 2 units of the code |

### vanilla (209 tokens)

| Token | D2R unit | Monsters | How |
|---|---|---|---|
| `0a` | act5barb1 (21), act5barb3 (2), act5hire1 (2) | `act5barb1`, `act5barb2`, `act5pow` +24 | best of 8 units of the code, same Id and code in D2R |
| `0b` | succubus1 | `succubus1`, `succubus2`, `succubus3` +4 | same Id and code in D2R |
| `0c` | succubuswitch1 | `succubuswitch1`, `succubuswitch2`, `succubuswitch3` +27 | only unit of the code, same Id and code in D2R |
| `0d` | ancientbarb1 | `ancientbarb1`, `defenders` | same Id and code in D2R, best of 2 units of the code |
| `0e` | ancientbarb3 | `ancientbarb3`, `protectors` | same Id and code in D2R, best of 2 units of the code |
| `0f` | ancientbarb2 | `ancientbarb2`, `quest_koth`, `quest_shaman` +1 | best of 2 units of the code, same Id and code in D2R |
| `0g` | ancientstatue1 | `ancientstatue1` | same Id and code in D2R |
| `0h` | ancientstatue1 | `ancientstatue2` | same Id and code in D2R |
| `0i` | ancientstatue1 | `ancientstatue3` | same Id and code in D2R |
| `0j` | nihlathak | `nihlathak` | same Id and code in D2R |
| `10` | trappedsoul1 | `trappedsoul1` | same Id and code in D2R |
| `13` | trappedsoul2 | `trappedsoul2` | same Id and code in D2R |
| `17` | izualghost | `izualghost` | same Id and code in D2R |
| `1d` | cain5 | `cain5` | same Id and code in D2R |
| `1z` | darkwanderer | `darkwanderer` | same Id and code in D2R |
| `20` | halbu | `halbu` | same Id and code in D2R |
| `21` | hydra2 | `hydra2` | same Id and code in D2R |
| `22` | izual | `izual`, `uberizual`, `overlords` | same Id and code in D2R, only unit of the code |
| `2c` | act2child | `act2child` | same Id and code in D2R |
| `2d` | cain2 | `cain2` | unit of the same Id in D2R (the 2012 token differs) |
| `2f` | act2female | `act2female` | same Id and code in D2R |
| `2m` | act2male | `act2male` | same Id and code in D2R |
| `2q` | prisondoor | `prisondoor` | same Id and code in D2R |
| `2t` | evilhut | `evilhut` | same Id and code in D2R |
| `36` | malachai | `malachai` | same Id and code in D2R |
| `3d` | cain3 | `cain3` | unit of the same Id in D2R (the 2012 token differs) |
| `40` | wolf | `wolf`, `rathma_werewolf` | same Id and code in D2R, only unit of the code |
| `41` | baalthrone | `baalthrone` | same Id and code in D2R |
| `42` | baalcrab (3), baalcrabstairs (1), baalclone (1) | `baalcrab`, `baalcrabstairs`, `baalclone` +2 | same Id and code in D2R, best of 3 units of the code |
| `43` | baalminion1 | `baalminion1`, `baalminion2`, `baalminion3` +2 | same Id and code in D2R, only unit of the code |
| `44` | baaltentacle1 | `baaltentacle1`, `baaltentacle2`, `baaltentacle3` +2 | same Id and code in D2R |
| `45` | putriddefiler1 | `putriddefiler1`, `putriddefiler2`, `putriddefiler3` +2 | same Id and code in D2R |
| `46` | painworm1 | `painworm1`, `painworm2`, `painworm3` +4 | same Id and code in D2R, only unit of the code |
| `48` | bunny | `bunny` | same Id and code in D2R |
| `4d` | cain4 | `cain4` | unit of the same Id in D2R (the 2012 token differs) |
| `5p` | smith (4), hephasto (1) | `smith`, `hephasto`, `quest_overlord` +2 | best of 2 units of the code, same Id and code in D2R |
| `64` | catapult1 | `catapult2`, `catapult3` | same Id and code in D2R |
| `65` | catapult1 | `catapult1` | same Id and code in D2R |
| `66` | boneprison2 | `boneprison2` | same Id and code in D2R |
| `67` | boneprison1 | `boneprison1` | same Id and code in D2R |
| `68` | boneprison4 | `boneprison4` | same Id and code in D2R |
| `69` | boneprison3 | `boneprison3` | same Id and code in D2R |
| `6z` | injuredbarb1 | `injuredbarb1` | same Id and code in D2R |
| `7i` | injuredbarb3 | `injuredbarb3` | same Id and code in D2R |
| `7j` | injuredbarb2 | `injuredbarb2` | same Id and code in D2R |
| `9a` | trap-firebolt (1), trap-horzmissile (1), trap-vertmissile (1) | `trap-firebolt`, `trap-horzmissile`, `trap-vertmissile` +5 | same Id and code in D2R |
| `a6` | barricadewall1 | `barricadewall1` | same Id and code in D2R |
| `ac` | barricadetower | `barricadetower` | same Id and code in D2R |
| `ae` | lightningspire | `lightningspire`, `totem1`, `totem2` +19 | only unit of the code, same Id and code in D2R |
| `ag` | barricadedoor2 | `barricadedoor2` | same Id and code in D2R |
| `ah` | asheara | `asheara` | same Id and code in D2R |
| `aj` | barricadedoor1 | `barricadedoor1` | same Id and code in D2R |
| `ak` | barricadewall2 | `barricadewall2` | same Id and code in D2R |
| `al` | alkor | `alkor` | same Id and code in D2R |
| `an` | andariel | `andariel`, `uberandariel`, `anguish_special` +1 | same Id and code in D2R, only unit of the code |
| `as` | atma | `atma` | same Id and code in D2R |
| `b7` | druidbear | `druidbear`, `th_bear` | same Id and code in D2R, only unit of the code |
| `b8` | bladecreeper | `bladecreeper` | same Id and code in D2R |
| `b9` | bat | `bat` | same Id and code in D2R |
| `bb` | baboon1 (22), baboon6 (1) | `baboon1`, `baboon2`, `baboon3` +20 | best of 2 units of the code, same Id and code in D2R |
| `bg` | bug | `bug` | same Id and code in D2R |
| `bh` | bighead1 | `bighead1`, `bighead2`, `bighead3` +23 | best of 2 units of the code, same Id and code in D2R |
| `bk` | foulcrow1 | `foulcrow1`, `foulcrow2`, `foulcrow3` +6 | same Id and code in D2R, only unit of the code |
| `bl` | bird2 | `bird2` | same Id and code in D2R |
| `bn` | crownest1 | `crownest1`, `crownest2`, `crownest3` +1 | same Id and code in D2R |
| `bs` | bird1 | `bird1` | same Id and code in D2R |
| `bt` | batdemon1 | `batdemon1`, `batdemon2`, `batdemon3` +21 | only unit of the code, same Id and code in D2R |
| `bu` | blunderbore1 (1), megademon1 (1) | `quest_butcher`, `super_kabraxis` | pinned: The Butcher: token BU has classic art in D2R but D2R has no HD unit or monstats row for it. Heavy ogre-like cleaver wielder: Blunderbore is the closest big brute. Unseen (D2R's classic art is not readable here); revisit with the in-game look., pinned: Kabraxis Himself uses the Butcher's token BU; as a boss demon the Mega Demon (Baal's/Diablo-class big demon) fits better than the Butcher stand-in. Unseen; revisit in game. |
| `bw` | bonewall | `bonewall` | same Id and code in D2R |
| `ch` | - | `chaoshorde1`, `chaoshorde2`, `chaoshorde3` +1 | D2R has no HD unit for this token |
| `ci` | charsi | `charsi` | same Id and code in D2R |
| `ck` | chicken | `chicken`, `defaultchicken` | same Id and code in D2R, only unit of the code |
| `cm` | camel | `camel` | same Id and code in D2R |
| `co` | snake | `snake` | same Id and code in D2R |
| `cr` | cr_archer1 (23), cr_lancer1 (17), corruptrogue1 (16) | `corruptrogue1`, `corruptrogue2`, `corruptrogue3` +54 | best of 4 units of the code, same Id and code in D2R |
| `cs` | regurgitator1 | `regurgitator1`, `regurgitator2`, `regurgitator3` +8 | only unit of the code, same Id and code in D2R |
| `cw` | cow | `cow`, `goldencalf` | same Id and code in D2R, best of 3 units of the code |
| `dc` | cain1 (1), cain6 (1) | `cain1`, `cain6` | same Id and code in D2R |
| `dh` | - | `suckernest1`, `suckernest2`, `suckernest3` +1 | D2R has no HD unit for this token |
| `di` | diablo | `diablo`, `diabloclone`, `uberdiablo` +2 | same Id and code in D2R, only unit of the code |
| `dm` | megademon1 (18), venomlord (1) | `megademon1`, `megademon2`, `megademon3` +16 | best of 2 units of the code, same Id and code in D2R |
| `dr` | drognan | `drognan` | same Id and code in D2R |
| `ds` | scorpion | `scorpion` | same Id and code in D2R |
| `du` | duriel | `duriel`, `uberduriel`, `pain_special` | same Id and code in D2R, only unit of the code |
| `e9` | wakeofdestruction (1), infernosentry (1) | `wakeofdestruction`, `infernosentry` | same Id and code in D2R |
| `ec` | hellbovine | `hellbovine`, `steak1`, `steak2` +4 | best of 2 units of the code, same Id and code in D2R |
| `eg` | eagle | `eagle` | same Id and code in D2R |
| `eh` | evilhole1 | `evilhole1`, `evilhole2`, `evilhole3` +2 | only unit of the code, same Id and code in D2R |
| `el` | elzix | `elzix` | same Id and code in D2R |
| `f0` | frozenhorror1 | `frozenhorror1`, `frozenhorror2`, `frozenhorror3` +16 | only unit of the code, same Id and code in D2R |
| `fa` | fallen1 | `fallen1`, `fallen2`, `fallen3` +22 | only unit of the code, same Id and code in D2R |
| `fc` | fetishblow1 | `fetishblow1`, `fetishblow2`, `fetishblow3` +18 | only unit of the code, same Id and code in D2R |
| `fd` | frogdemon1 | `frogdemon1`, `frogdemon2`, `frogdemon3` +14 | only unit of the code, same Id and code in D2R |
| `fe` | fetish1 (20), fetish11 (1) | `fetish1`, `fetish2`, `fetish3` +18 | best of 2 units of the code, same Id and code in D2R |
| `fi` | - | `familiar` | D2R has no HD unit for this token |
| `fj` | fish | `fish` | same Id and code in D2R |
| `fk` | bonefetish1 | `bonefetish1`, `bonefetish2`, `bonefetish3` +4 | same Id and code in D2R |
| `fr` | fingermage1 | `fingermage1`, `fingermage2`, `fingermage3` +11 | only unit of the code, same Id and code in D2R |
| `fs` | fallenshaman1 | `fallenshaman1`, `fallenshaman2`, `fallenshaman3` +20 | only unit of the code, same Id and code in D2R |
| `fw` | fetishshaman1 | `fetishshaman1`, `fetishshaman2`, `fetishshaman3` +5 | same Id and code in D2R |
| `g1` | claygolem | `claygolem` | same Id and code in D2R |
| `g2` | bloodgolem | `bloodgolem`, `hiddenminion`, `evil2spw` | only unit of the code, same Id and code in D2R |
| `g3` | firegolem | `firegolem` | same Id and code in D2R |
| `g4` | irongolem | `irongolem`, `robotnik`, `r_alpha` +5 | only unit of the code, same Id and code in D2R |
| `ge` | geglash | `geglash` | same Id and code in D2R |
| `gh` | gheed | `gheed` | same Id and code in D2R |
| `gm` | goatman1 | `goatman1`, `goatman2`, `goatman3` +35 | best of 2 units of the code, same Id and code in D2R |
| `go` | gorgon1 | `gorgon1`, `gorgon2`, `gorgon3` +1 | same Id and code in D2R |
| `gr` | greiz | `greiz` | same Id and code in D2R |
| `gt` | gargoyletrap | `gargoyletrap`, `quest_spitter`, `ureh_fireturret` +5 | only unit of the code, same Id and code in D2R |
| `gu` | act2guard1 (4), act2guard2 (1), act2hire (1) | `act2guard1`, `act2guard2`, `act2hire` +5 | same Id and code in D2R, best of 5 units of the code |
| `gy` | unraveler1 | `unraveler1`, `unraveler2`, `unraveler3` +21 | only unit of the code, same Id and code in D2R |
| `gz` | griswold | `griswold` | same Id and code in D2R |
| `hk` | druidhawk | `druidhawk` | same Id and code in D2R |
| `hp` | baalhighpriest (11), councilmember1 (10) | `councilmember1`, `councilmember2`, `councilmember3` +18 | best of 2 units of the code, same Id and code in D2R |
| `hr` | hratli | `hratli` | same Id and code in D2R |
| `hx` | hydra1 | `hydra1` | same Id and code in D2R |
| `hz` | hydra3 | `hydra3` | same Id and code in D2R |
| `io` | snowyeti1 | `snowyeti1`, `snowyeti2`, `snowyeti3` +3 | same Id and code in D2R, only unit of the code |
| `ip` | imp1 | `imp1`, `imp2`, `imp3` +4 | same Id and code in D2R |
| `iw` | act3hire | `act3hire`, `quest_talrasha`, `quest_horadric` +1 | only unit of the code, same Id and code in D2R |
| `ja` | jamella | `jamella` | same Id and code in D2R |
| `je` | jerhyn | `jerhyn` | same Id and code in D2R |
| `k9` | hellmeteor (11), worldstoneeffect (6), catapultspotter1 (4) | `hellmeteor`, `invisospawner`, `invisopet` +29 | best of 11 units of the code, same Id and code in D2R |
| `l3` | bloodlord1 | `bloodlord1`, `bloodlord2`, `bloodlord3` +24 | only unit of the code, same Id and code in D2R |
| `lg` | chargeboltsentry (1), lightningsentry (1), deathsentry (1) | `chargeboltsentry`, `lightningsentry`, `deathsentry` | same Id and code in D2R |
| `ls` | minispider | `minispider` | same Id and code in D2R |
| `lv` | larva | `larva` | same Id and code in D2R |
| `ly` | lysander | `lysander` | same Id and code in D2R |
| `m1` | act2vendor1 | `act2vendor1` | same Id and code in D2R |
| `m2` | act2vendor2 | `act2vendor2` | same Id and code in D2R |
| `m3` | meshif2 | `meshif2` | same Id and code in D2R |
| `m4` | trap-melee | `trap-melee` | same Id and code in D2R |
| `m5` | deathmauler1 | `deathmauler1`, `deathmauler2`, `deathmauler3` +20 | only unit of the code, same Id and code in D2R |
| `m6` | mephistospirit | `mephistospirit` | same Id and code in D2R |
| `ma` | maggot | `maggot` | same Id and code in D2R |
| `mg` | sarcophagus | `sarcophagus` | same Id and code in D2R |
| `mm` | mummy1 | `mummy1`, `mummy2`, `mummy3` +3 | same Id and code in D2R |
| `mo` | mosquito1 | `mosquito1`, `mosquito2`, `mosquito3` +13 | only unit of the code, same Id and code in D2R |
| `mp` | mephisto | `mephisto`, `ubermephisto`, `hatred_special` | same Id and code in D2R, only unit of the code |
| `mq` | maggotqueen1 | `maggotqueen1`, `maggotqueen2`, `maggotqueen3` +2 | same Id and code in D2R |
| `ms` | meshif1 | `meshif1` | same Id and code in D2R |
| `n3` | act3female | `act3female` | same Id and code in D2R |
| `n4` | act3male | `act3male` | same Id and code in D2R |
| `of` | fara | `fara` | same Id and code in D2R |
| `or` | ormus | `ormus` | same Id and code in D2R |
| `os` | overseer1 | `overseer1`, `overseer2`, `overseer3` +3 | same Id and code in D2R, only unit of the code |
| `ox` | siegebeast1 | `siegebeast1`, `siegebeast2`, `siegebeast3` +2 | same Id and code in D2R |
| `pb` | turret1 (7), firetower (4) | `turret1`, `turret2`, `turret3` +8 | best of 2 units of the code, same Id and code in D2R |
| `pm` | - | `poisonorb` | D2R has no HD unit for this token |
| `pn` | blunderbore1 | `blunderbore1`, `blunderbore2`, `blunderbore3` +5 | same Id and code in D2R, only unit of the code |
| `pr` | parrot | `parrot` | same Id and code in D2R |
| `ps` | akara | `akara` | same Id and code in D2R |
| `pw` | slinger1 (34), pantherwoman1 (15), slinger5 (2) | `pantherwoman1`, `pantherwoman2`, `pantherwoman3` +48 | best of 3 units of the code, same Id and code in D2R |
| `rc` | kashya | `kashya` | same Id and code in D2R |
| `rd` | radament | `radament` | same Id and code in D2R |
| `re` | reanimatedhorde1 | `reanimatedhorde1`, `reanimatedhorde2`, `reanimatedhorde3` +16 | only unit of the code, same Id and code in D2R |
| `rg` | rogue1 (2), navi (1), rogue2 (1) | `rogue1`, `navi`, `rogue2` +3 | same Id and code in D2R, best of 5 units of the code |
| `rt` | rat | `rat` | same Id and code in D2R |
| `s7` | quillbear1 | `quillbear1`, `quillbear2`, `quillbear3` +10 | only unit of the code, same Id and code in D2R; 13 Ids whose D2R unit has no model (quillbear1, quillbear2, quillbear3) get quillrat1 x1.4 (medium) |
| `sb` | maggotbaby1 | `maggotbaby1`, `maggotbaby2`, `maggotbaby3` +7 | same Id and code in D2R, only unit of the code |
| `sc` | scarab1 | `scarab1`, `scarab2`, `scarab3` +18 | only unit of the code, same Id and code in D2R |
| `sd` | clawviper1 | `clawviper1`, `clawviper2`, `clawviper3` +23 | only unit of the code, same Id and code in D2R |
| `se` | maggotegg1 | `maggotegg1`, `maggotegg2`, `maggotegg3` +7 | same Id and code in D2R, only unit of the code |
| `si` | quillrat1 | `quillrat1`, `quillrat2`, `quillrat3` +16 | only unit of the code, same Id and code in D2R |
| `sk` | skmage_pois1 (37), sk_archer1 (35), skeleton1 (26) | `skeleton2`, `skeleton3`, `skeleton4` +115 | best of 9 units of the code, same Id and code in D2R |
| `sl` | sandleaper1 | `sandleaper1`, `sandleaper2`, `sandleaper3` +24 | only unit of the code, same Id and code in D2R |
| `sm` | sandmaggot1 | `sandmaggot1`, `sandmaggot2`, `sandmaggot3` +3 | same Id and code in D2R |
| `sp` | arach1 | `arach1`, `arach2`, `arach3` +14 | only unit of the code, same Id and code in D2R |
| `sr` | sandraider1 | `sandraider1`, `sandraider2`, `sandraider3` +21 | only unit of the code, same Id and code in D2R |
| `st` | flyingscimitar | `flyingscimitar` | same Id and code in D2R |
| `su` | summoner | `summoner` | same Id and code in D2R |
| `sw` | swarm1 | `swarm1`, `swarm2`, `swarm3` +2 | same Id and code in D2R, only unit of the code |
| `te` | tentaclehead1 | `tentaclehead1`, `tentaclehead2`, `tentaclehead3` | same Id and code in D2R |
| `tg` | bear | `bear` | same Id and code in D2R |
| `th` | thornhulk1 | `thornhulk1`, `thornhulk2`, `thornhulk3` +4 | same Id and code in D2R, only unit of the code |
| `tn` | tentacle1 | `tentacle1`, `tentacle2`, `tentacle3` | same Id and code in D2R |
| `tx` | tyrael1 | `tyrael1`, `tyrael2` | same Id and code in D2R, only unit of the code |
| `ty` | tyrael2 (2), tyrael3 (1) | `tyrael3`, `quest_zakarum`, `super_zakarum` | best of 2 units of the code, same Id and code in D2R |
| `tz` | natalya | `natalya` | same Id and code in D2R |
| `ua` | catapult1 | `catapult4` | same Id and code in D2R |
| `um` | doomknight2 (9), doomknight1 (6), doomknight3 (3) | `doomknight1`, `doomknight2`, `doomknight3` +15 | best of 3 units of the code, same Id and code in D2R |
| `va` | vampire1 | `vampire1`, `vampire2`, `vampire3` +24 | only unit of the code, same Id and code in D2R |
| `vc` | vilechild1 | `vilechild1`, `vilechild2`, `vilechild3` +3 | same Id and code in D2R, only unit of the code |
| `vd` | vulture1 | `vulture1`, `vulture2`, `vulture3` +13 | only unit of the code, same Id and code in D2R |
| `vh` | window1 | `window1` | same Id and code in D2R |
| `vj` | window2 | `window2` | same Id and code in D2R |
| `vk` | valkyrie (2), dopplezon (1) | `dopplezon`, `valkyrie`, `crusaders` | same Id and code in D2R, best of 2 units of the code |
| `vm` | vilemother1 | `vilemother1`, `vilemother2`, `vilemother3` +3 | same Id and code in D2R, only unit of the code |
| `wa` | warriv1 | `warriv1` | same Id and code in D2R |
| `wf` | spiritwolf | `spiritwolf`, `fenris`, `reanimatedwolf` | same Id and code in D2R, only unit of the code |
| `wr` | wraith1 | `wraith1`, `wraith2`, `wraith3` +26 | only unit of the code, same Id and code in D2R |
| `ww` | willowisp1 | `willowisp1`, `willowisp2`, `willowisp3` +19 | only unit of the code, same Id and code in D2R |
| `wx` | warriv2 | `warriv2` | same Id and code in D2R |
| `x3` | spiritofbarbs | `heartofwolverine` | same Id and code in D2R |
| `x4` | spiritofbarbs | `spiritofbarbs`, `rathma_ghost` | same Id and code in D2R, only unit of the code |
| `xa` | minionspawner1 | `minionspawner1`, `minionspawner2`, `minionspawner3` +5 | same Id and code in D2R |
| `xr` | larzuk | `larzuk` | same Id and code in D2R |
| `xs` | drehya (1), drehyaiced (1) | `drehya`, `drehyaiced` | same Id and code in D2R |
| `xt` | malah | `malah` | same Id and code in D2R |
| `xu` | nihlathakboss | `nihlathakboss` | same Id and code in D2R |
| `xv` | qual-kehk | `qual-kehk` | same Id and code in D2R |
| `xw` | spiritofbarbs | `oaksage` | same Id and code in D2R |
| `xx` | minion1 | `darkguard1`, `darkguard2`, `darkguard3` +34 | only unit of the code, same Id and code in D2R |
| `xy` | suicideminion1 | `suicideminion1`, `suicideminion2`, `suicideminion3` +5 | same Id and code in D2R |
| `ye` | brute2 | `brute2`, `brute3`, `brute4` +13 | only unit of the code, same Id and code in D2R |
| `zm` | zombie1 | `zombie1`, `zombie2`, `zombie3` +17 | best of 2 units of the code, same Id and code in D2R |
| `zp` | cantor1 | `skeleton1`, `cantor1`, `cantor2` +18 | only unit of the code, same Id and code in D2R |
| `zz` | zealot1 | `zealot1`, `zealot2`, `zealot3` +22 | only unit of the code, same Id and code in D2R |

### unused (8 tokens)

| Token | - | - | Note |
|---|---|---|---|
| `!k` | - | - | art in the MPQ, no monstats row uses it |
| `!z` | - | - | art in the MPQ, no monstats row uses it |
| `&6` | - | - | art in the MPQ, no monstats row uses it |
| `@d` | - | - | art in the MPQ, no monstats row uses it |
| `^t` | - | - | art in the MPQ, no monstats row uses it |
| `oy` | - | - | art in the MPQ, no monstats row uses it |
| `t^` | - | - | art in the MPQ, no monstats row uses it |
| `~5` | - | - | art in the MPQ, no monstats row uses it |

<!-- tokens:end -->

## 2. Token classes and how they are decided (`tools/hd_monsters.py classify`)

For every monstats row: token = `Code` (case-insensitive), modes = the `m*` flags of its monstats2 row (via `MonStatsEx`).

1. **vanilla**: D2R's file list has the COF of every mode (KB and SQ ignored, DT/DD fall back to `hth`, `missing_cofs`) of
   every Id of the token. The art is D2R's, so D2R has (or deliberately lacks) the model. Unit per Id, rule `vanilla_unit`:
   the D2R unit of the same Id and code, else the best unit of the code (AI, MonType, weapon class). Added here: all of D2R's units
   count (the reference list skips town folk and guards, which the token itself needs), then the unit of the same Id when the code
   differs (the 2012 `cain2-4`, `tyrael2`), then a hand pick (`vanilla_ids` in the pins: `quest_butcher`, `super_kabraxis`).
   **Left without a unit** (D2R has none either: invisible helpers, spawners, orbs; they stay as D2R does them): `chaoshorde1-4`,
   `suckernest1-4`, `familiar`, `poisonorb`, `firebeast`, `iceglobe`.
2. **mixed**: some Ids of the token are vanilla by that test, others ask for modes D2R lacks. The art is still D2R's: vanilla rule;
   the Median-only Ids that get no unit that way (`regu_elemental`, `ulti_elemental`, `necromorb`, `lantern`) take the reference stand-in
   (`claygolem`, low).
3. **noart**: no art in the MPQ and not complete in D2R: pinned (`am dz so`, section 4).
4. otherwise the token has MPQ art: **reused** when the reference mapping has the same code *and at least half of the 2012 files are
   byte-identical to the reference art's*; else **new**.
5. a token with art but no monstats row is **unused**.

## 3. Reusing the reference mapping (class reused, `tools/hd_monsters.py map`)

The reference mapping (a `hd_monsters.md` report) is keyed by monster Id and Code. Several of its monsters share one art set and it
scored each by its *name* (keywords, MonType, AI) against D2R's units, so one token can have several donors. Rule per token:

- donor = the one with the most confidence-weighted reference rows (high 3, medium 2, low 1); scale, colour (hue/saturation/value offsets
  plus tint, read from the reference's built variant table) and, for the reference's provenance matches, the part mapping come from the first
  row of that donor with the most common scale and colour;
- **54 tokens**: that donor holds at least 70% of the weight and the confidence is not low: taken as is;
- **32 tokens** (the reference rows disagree): the 2012 monsters of the token are scored with the reference scoring against the donors
  the reference used for that token (2012 monster names differ from the reference's, e.g. `sumelite_1269`, `treeppl1`). I then looked at the
  classic art of each of those 32 (NU frame) and **overrode 12** by hand where the pick was plainly the wrong creature (a rat mapped to
  a demon, a gargoyle to a bear, a tree to a prison door; see `hd_monster_pins.json`); **20 are still the scored choice, flagged
  "(review)"** in the table.
- Not carried over: the reference's per-Id palette-shift (`TransLvl`) colours; one colour per token. The 2012 MPQ has no `palshift.dat`
  files: Median's own tokens draw every level in one colour in classic too, so one colour per stand-in is what classic shows.
  The levels that do differ in classic are those of D2R's tokens: section 8.

## 4. New mappings (classes new and noart)

Candidates come from `py -3 -I tools/hd_monsters.py suggest` (the reference scoring on the 2012 art: family/body plan from the monster
Id, NameStr and MonType, animation modes of monstats2, art size from the DCC frame, mean colour) and a look at the art itself (a
contact sheet of the NU frame of each token, rendered with `dcc.py`). Scale and colour then come from the reference rules
for the pinned donor. Picks and reasons are in `tools/data/hd_monster_pins.json`:

| Token | Monster | Stand-in | Why in one line |
|---|---|---|---|
| `!1` | Quest Lucion | arach1 | large multi-legged crawling demon: the giant spider |
| `!e` | Azmo special (Dominator) | baalminion1 | red horned biped demon with a blade (alt: hephasto) |
| `7$` | Trained Cougar | wolf | big cat; D2R has no cat (monster is broken in 2012: no monstats2 row) |
| `8@` | Horned God | goatman1 | horned biped with a weapon (same donor the reference uses for the Wereowl) |
| `9$` | Wolf companion | spiritwolf | small grey wolf |
| `ie` | Shardspawn | frozenhorror1 | hunched crystalline ice giant (its attack2 is only a skill sequence; since lane hdmon3 A2 has a state of its own that plays it, section 11) |
| `k+` | Veteran Son of Hefaestus | ancientbarb1 | tall muscular bare-chested boss fighter (x1.5) |
| `m+` | Guardian / Sacred Construct | irongolem | metal construct, bronze tint (the reference ranking preferred a human; judged wrong) |
| `x+` | Veteran Psychorb | arach1 | round body with eye stalks that walks, attacks and casts |
| `hn` (`am` `dz` `so`) | Haunt Amazon / Druid / Sorceress | cr_archer1 | no art anywhere (player-class codes); D2R's Corrupt Rogue archer art under the own token HN, HD the unit itself (bugs.md #74) |

Nothing was run in game (no game runs in this lane). Which stand-ins look wrong is for an in-game pass: `build` writes
`mxl_*` units the plugin can load.

## 5. The build step

```
py -3 -I tools/hd_monsters.py classify            token classes             -> work/hd_monsters/classes.json
py -3 -I tools/hd_monsters.py suggest [TOKEN ..]  donor ranking             -> work/hd_monsters/suggest.md
py -3 -I tools/hd_monsters.py map                 the mapping               -> tools/data/hd_monster_tokens.json
py -3 -I tools/hd_monsters.py repin TOKEN ..      only these entries again from the pins (a changed hand pick, section 8)
py -3 -I tools/hd_monsters.py recolour TOKEN ..   only the colour of these entries again with the current rule (section 10)
py -3 -I tools/hd_monsters.py clips DIR           clip names per D2R enemy animation folder -> tools/data/d2r_unit_clips.json
py -3 -I tools/hd_monsters.py build               HD json for every monstats Id -> work/hd_monsters/data/hd/character/ + hd_monsters.md
py -3 -I tools/hd_monsters.py doc                 regenerate the token tables of this file
```

### 5.1 Own tokens (lane tokens, 2026-10-28; docs/legacy-graphics.md section 6)

Median's art that used to share or borrow a D2R token has its own token in the classic client (`tools/own_tokens.py`), and the HD
mapping follows the monstats Code the build writes (`hd_monsters.tok_of`, `row_token` on the raw Median row):

| Rows | Old token | New token | HD effect | Why |
|---|---|---|---|---|
| `slayer`, `slayer2` | `e9` | `KS` | class `split`, same donor: unit `wakeofdestruction` (`splits` rewrote the entries `ks` and `e9` in `hd_monster_tokens.json`; `e9` keeps `wakeofdestruction`, `infernosentry`) | D2R's e9 animdata (2 frames) did not fit Median's Slayer COFs (13 / 14 frames); Median's art now has its own files |
| `hornedgods` | `AN` (borrowed) | `8@` | none: pinned donor of the `8@` entry as before | the row now keeps its Code, the missing DT COF and rh layer are made (`complete`) |
| `couatlfather1-3`, `couatlfather_elite` | `FA` (borrowed) | `!4` | none (the `!4` entry) | the missing SC COF is made |
| `dead3`, `res_dead3` | `ZM` (borrowed) | `ji` | none (the `ji` entry) | the missing S1 COF and looks are made |

`hd_monsters.py splits` updates only the split entries of the committed mapping (a full `map` needs the reference reports); `classify`
reads the virtual files of the plan (`own_tokens.virtual_index`) so `ks` counts as a token with MPQ art.

`classify`, `suggest` and `map` read the extracted 2012 MPQ (`R\mxl2012-runs\extract-mpq`), the D2R baseline extract
(`extract_dir` in the machine-local config, docs/setup.md: tables, HD json, palette, file list), the reference art folders (hash comparison) and the
reference `hd_monsters.md` report plus built units (donor, scale, colour, part mapping); all read-only, paths are options. **`build` needs only
the committed mapping, the 2012 monstats and the D2R baseline**: it writes, for the 1,822 Ids, `monsters.json` (D2R's, plus every
2012 Id), the `mxl_<donor>_<hash>.json` unit definitions (104), the colour tables (`mxl/v_*.json`, 93) and the adapted state machines
(`mxl/sm_*.json`, 7; a donor's state machine bound for the weapon class Median uses). Install into the mod folder is the plugin /
packaging lane's job.

D2R's classic art is not readable here (it lives in the game's CASC archive; this project does not open the owner's install). The
colour/size statistics of D2R's units come from a cached `hd_monsters_art.json` of the reference (D2R entries only); the 2012 art side
is decoded from the MPQ extraction.

## 6. Files

| File | Part | Notes |
|---|---|---|
| `tools/dcc.py` | `tools/dcc.py` | copied unchanged (DCC decoder: size and colour of the 2012 art) |
| `tools/hd_units.py` | `tools/hd_monsters.py` (unit definitions part) | copied: unit / variant table / state machine builders. Changed: D2R root via `configure()`; `variants_cell()` reads the `Rav` / `Lav` spelling of the arm columns (looking up `RAv` / `LAv` made arm part variants always fall back to `lit`) |
| `tools/hd_donors.py` | `tools/hd_monsters.py` (tags, art stats, donors, scoring, tint, `vanilla_unit`) | no CASC / game access (D2R art stats from the reference cache), art read from the 2012 MPQ extraction, `bare()` local, pinned-donor and provenance code dropped, `choose` works with a single candidate |
| `tools/hd_monsters.py` | `tools/hd_monsters.py` | **new** main program: classes, reference reuse, rescoring on 2012 names, pins, `build`, doc table. No per-Id scoring of every monster, provenance matching or wereowl pin |
| `tools/data/hd_monster_tokens.json`, `tools/data/hd_monster_pins.json` | - | new (our mapping and hand picks) |
| `tools/data/d2r_unit_clips.json` | - | new (lane hdmon2): clip names per D2R enemy animation folder, section 9.1 |
| `tools/tests/test_hd_clip_fill.py` | - | new (lane hdmon2): clip fallback, model check, committed donors have a model; lane hdmon3: state fill, the hm2 / hm3 check lists |
| `tools/tests/test_hd_monsters.py` | - | new |

Not here: `tools/model_lod_desc.py` and `tools/d2r_model.py` (only needed for **new** models, section 7), `art_provenance.py`
(exact-art matches against vanilla DCCs; the reference's provenance part mappings are carried through where it used them),
`wereowl_models.py`.

## 7. What still needs custom art (deferred)

Everything in the reused, new, noart tables is a stand-in; the real look needs new `.model` meshes + skeleton + animations
(formats decoded, Writer works, an exporter and the art are missing). Each look then becomes its own
unit through the same plumbing (unit, variant, state machine) and `model_lod_desc.py add` for the model index. Not started here.

- **All 95 Median-art tokens that get a donor** (86 reused + 9 new, 259 Ids) look like another monster until then. Priority by Ids using
  the token: `@6` (10), `(l` (10), `9!` `0n` `!5` (7 each), then bosses and quest monsters.
- **Weak stand-ins** (low confidence): `2(` (mushroom man), `7$` (cougar, also broken in the table), `m+` (bronze guardian), `x+`
  (psychorb), `9!` (centaur), `3#` (nighthorse), `!!` (glowing one), and `am` `dz` `so` (no art at all: nothing to base a look on).
- **Two tokens D2R has art for but no model**: `fm`, `im` stand-ins are `claygolem` (low); the Butcher / Kabraxis (`bu`) are pinned
  to `blunderbore1` / `megademon1` unseen.
- **8 unused art sets** (`!k !z &6 @d ^t oy t^ ~5`): nothing to do unless another table (objects, missiles, cube) references them.
- **Not done**: weapons and shields of the donor are dropped when Median has no slot for them (18 parts);
  no animation retargeting beyond the donor's own clips (a mode a donor has no clip for plays the nearest clip it has, section 9.1).

`cougar`: **dropped** (owner 2026-10-29): Median's row is broken (no monstats2 row, author's status "WERKT NIET") and nothing spawns it. `txt_migrate.dropped_monsters` keeps the row (the ids after it stay) but switches it off (`enabled` 0, `isSpawn` 0) and drops its links (MonProp, minion); its `7$` wolf stand-in is now unused (lane unporteda).

## 8. Per-TransLvl colours (`tools/hd_translvl.py`, lane tints 2026-10-29)

Classic Diablo II recolours the monsters of one token per level: the token's `palshift.dat` has 8 tables of 256 palette
indices and a monster of TransLvl t draws through table **t + 2** (0 and 1 are the cold and poison tints). Seen in game (lane
tints, run 3): Median's `quillbear4` (TransLvl 3) is black in classic = table 5, `quillbear5` (4) purple = table 6; tables 3
and 4 would be purple and green. D2R's HD unit has the same layout in its variant table (`<unit>_variant.json`): entries
`cold`, `poison`, `level0` .. `level4`, `misc`; TransLvl t takes entry t + 2 (`fallen1` .. `fallen5` share the unit
`fallen1` and differ only there). `hd_donors.art_colour` read table t until 2026-10-29 (fixed: it only feeds `map` /
`suggest`, the committed mapping is unchanged). Each entry has 3 colour transforms (the red / green / blue mask regions of the model): `colorAdjustment` (hue turn,
saturation, value) and `colorTint` (r, g, b, amount).

Survey of the build (both banks), enabled Ids on D2R HD units with TransLvl 1 or more:

| Case | (unit, level) pairs | Ids | What classic does | HD |
|---|---:|---:|---|---|
| D2R authored the level | 225 | 809 | palette shift | D2R's own entry (nothing to do) |
| token without `palshift.dat` | 47 | 85 | no shift | level-0 look, as classic |
| D2R uses the level but left it identity (Quill Rats, Wisps, Wraiths, Zakarum clerics, Dark Elder, Pain Worm, Minion) | 12 | 48 | palette shift | **filled** (10 levels, 35 Ids) or below the threshold (2: Zakarum cleric 3, Wraith 1) |
| TransLvl 6 / 7 (`minion1`, `minionspawner1`, `suicideminion1`) | 6 | 11 | palette shift | no entry in the 8-entry table: open |
| unit without a variant table (`ancientbarb2/3`, `ancientstatue1`, barricades, `colossal2/3`, `cowking`) | 9 | 11 | palette shift | open (no table to fill) |

Stand-in units (`mxl_*`, Median's own tokens) are not this step's: no `palshift.dat`, one colour in classic too. Their Ids
differ by look in one token only (`9x`: Regular Amazon vs the priestesses), below `tint_of`'s threshold.

`hd_translvl.py build` (after `hd_monsters.py build` in `tools/build.py`) measures the classic art of each such level (frame 0
of mode NU, the build's monstats2 looks; disabled rows (`enabled` not 1) are left out; Median's file where it ships one, else
D2R's from the baseline extraction) through table 2 (level 0) and through the level's table and writes the difference as the
entry (`hd_donors.tint_of`, quantised, added to the
level-0 entry's transform). The unit's table goes to `work/mod/data/hd/character/enemy/<unit>/<unit>_variant.json` (the
mod's copy shadows D2R's), compact and never larger than D2R's file (filled transforms get short names, then 1-decimal values,
when needed). `--keep-d2r-levels` leaves the levels D2R uses as D2R has them. Report `work/mod/hd_translvl.md` (+ `.json` for
the game check).

Result (2026-10-29): 10 levels filled in 5 tables, 35 Ids, **48,521 bytes** (each table 0-12 bytes under D2R's):

| Unit | Level | Token | Shift | Ids (some) |
|---|---:|---|---|---|
| `quillbear1` | 1 | `s7` | hue -0.13 sat +0.16 val +0.00 | `quillbear2` |
| `quillbear1` | 2 | `s7` | hue +0.16 sat -0.06 val -0.20 | `quillbear3`, `empty_quills4`, `uq_quills4` |
| `quillbear1` | 3 | `s7` | hue -0.00 sat -0.26 val -0.61 (black) | `quillbear4`, `elite_quillsA` |
| `quillbear1` | 4 | `s7` | hue -0.21 sat +0.15 val +0.03 (purple) | `quillbear5` |
| `willowisp1` | 1 | `ww` | hue +0.00 sat +0.17 val -0.17 | `willowisp2`, `wisp4`, `hell_wisp` |
| `willowisp1` | 2 | `ww` | hue -0.00 sat +0.26 val -0.16 | `willowisp3`, `wisp2` |
| `willowisp1` | 3 | `ww` | hue -0.01 sat +0.11 val -0.35 | `willowisp4`, `wisp1` |
| `minion1` | 3 | `xx` | hue -0.05 sat -0.28 val -0.28 | `minion4`, `minion10`, `turtle2` |
| `darkelder` | 4 | `zm` | hue +0.06 sat -0.28 val -0.52 | `darkelder` |
| `painworm1` | 4 | `46` | hue -0.04 sat +0.01 val -0.04 | `painworm5` |

Seen in game (harness, lane tints run 3, slot 3, `work/runs/checks-20261029-030506-s3`, shots in `mxl2012-runs/tints/run3/`):
the mod's variant table is loaded: the `minion1` corpses differ in HD, level 3 darker and greyer than level 0, where D2R's own
entry is identity (that run still used table t; the colours above are the corrected ones). Quill Rat corpses are not drawn in
HD after a harness `kill` (classic draws them), so the check now also shoots the monsters alive.

Tests: `tools/tests/test_hd_translvl.py`. Game check `tint_hd` (tools/game_checks.py): docs/testing.md "Lane tints".

## 9. Act 1-2 Normal pass (lane hdmon2, 2026-10-29)

Play testers meet Act 1-2 Normal first, so every Median-only monster that can spawn there was reviewed: the `mon1-25` / `umon1-25`
columns of the Act 1 and Act 2 levels, the Act 1-2 `monpreset` places (superuniques by their `Class`, quest monsters), and their
minions, `spawn` monsters and summons (monstats `minion1/2`, `spawn`, summon skills). 75 Ids on 46 tokens draw a stand-in; Ids of
tokens D2R has its own unit for are not listed. A contact sheet (Median's classic NU frame beside the donor's classic NU frame at
our scale; scratch, not in git) was made for all 46 and for the candidates.

### 9.1 Two checks the first pass did not have

- **Donors without a model.** Some D2R unit files name a model and skeleton D2R does not ship (`eagle`, `quillbear1`, also
  `gorgon1`, `bird2`, `fish`, `act2child` and the trap / helper units). A stand-in made from them draws **nothing** in HD. `eagle` stood
  in for `!!` `&b` `1!` and `quillbear1` for `3#` `9!`, so the Deathwings (Act 2 desert) and the Centaurs (Act 2 palace cellars) were
  invisible. `Ctx` now drops every donor whose models are not in D2R's file list (`hd_units.has_model`, from the baseline's
  `filelist.txt`), `build` stops on a stand-in that is not a usable donor, and a unit test checks the committed mapping.
  The same gap hid a whole vanilla token (bug #431, lane hdlook3): Median brings back D2R's unused Quill Bears (`s7`,
  `quillbear1-5` and 8 more Ids) and D2R's unit `quillbear1` has no model, so they drew nothing in HD (classic draws them).
  A vanilla token with a pin now gives its Ids whose D2R unit has no model a stand-in (`stand_in_ids`, as `mixed` does for
  Median-only Ids); without a pin D2R's unit stays (D2R's own invisible helpers and traps). `s7` is pinned to quillrat1 x1.4;
  the colour tables count those Ids (`has_standin`), still 30 tables. All its colour levels draw alike in HD for now (the
  stand-in has one colour; `hd_translvl.py` fills levels of D2R units only).
- **Modes without a clip.** A D2R unit's state machine binds all 15 modes to clip names whether or not its `combined.animations`
  holds the clip; D2R's own monster never enters a mode it has no art for, a Median monster does. `darkwanderer` (stand-in of 4 tokens)
  has only `neutral` `walk` `death` `dead`: the robed and undead fighters on it stood still when they attacked or were hit.
  `tools/data/d2r_unit_clips.json` lists the clip names of every D2R enemy animation folder (170; names only, read once from a game
  slot's CASC: `tools/sprite3d/extract_anims.py <dir>`, then `tools/hd_monsters.py clips <dir>`). `build` binds every plain mode state
  (modeId 0-13, 15) whose clip the donor lacks to the first clip it has of `hd_units.CLIP_FALLBACK` (attack2 -> attack1, cast ->
  skill1 / attack2 / attack1, gethit -> knockback / neutral, run -> walk, death -> knockback / gethit ...), in an adapted state machine
  `mxl/sm_<donor>_fill.json` (or the `_<weapon>` / `_death` one it already had). 45 donors get one; the build report lists every
  substitution. Sequences and layers (modeId 14 / 100) are not touched.

### 9.2 Changed stand-ins (hand picks in `hd_monster_pins.json`, entries made again with `tools/hd_monsters.py repin`)

Colour is what the existing donor scoring works out for the new donor (no colour code changed). D2R units already loaded in the same
act were preferred (#360 asset cache): zombie1, fallenshaman1, councilmember1 (Cultists) in Act 1; vulture1, sandraider1, clawviper1,
maggotbaby1 in Act 2.

| Token | Monsters | Before | Now | Why |
|---|---|---|---|---|
| `&b` | Deathwing (Act 2) | eagle x0.7 | vulture1 x1.2 | eagle has no HD model (invisible); bony winged flyer: the Act 2 carrion bird |
| `9!` | Centaurs (Act 2) | quillbear1 x1 | clawviper1 x1.3 | quillbear1 has no HD model (invisible); D2R has no centaur: beast lower body plus armed human torso, Act 2 unit (low) |
| `!!` | Glowing one | eagle x1 | wraith1 x1 | eagle has no HD model (invisible); ghostly hunched figure (low; not in Act 1-2, fixed with its donor) |
| `1!` | Priest | eagle x1 | cantor1 x0.9 | eagle has no HD model (invisible); robed human priest (not in Act 1-2) |
| `3#` | Nighthorse | quillbear1 x1 | spiritwolf x1.8 | quillbear1 has no HD model (invisible); D2R has no horse: nearest lean quadruped (low; not in Act 1-2) |
| `#w` | Robe Dagger (Act 1 cave boss pack) | darkwanderer x1 | councilmember1 x1 | darkwanderer has no attack / gethit clip; hooded robed figure |
| `c@` | Cloak Dagger (same pack) | wraith1 x1.25 | councilmember1 x1.1 | twin of Robe Dagger; the floating Wraith was three times as wide as the art |
| `(1` | Inarius, Hell Dragonknight | darkwanderer x1.35 | doomknight2 x1.25 | darkwanderer has no attack clip; the same knight family as `(2` |
| `@c` | Green Zombie | darkwanderer x0.9 | zombie1 x1.15 | darkwanderer has no attack clip; it is a zombie |
| `#y` | Zombie Rags | wraith1 x1.3 | zombie1 x1.4 | a tall ragged zombie, not a floating ghost |
| `ji` | Dead (dead3, Act 2 palace) | darkwanderer x1.15 | sandraider1 x0.85 | darkwanderer has no attack clip; turbaned scimitar fighter: the Act 2 Sand Raider |
| `@6` | Fire Wizards (Act 2 Valley, Fleshdoom) | doomknight3 x1.15 | firegolem x1.1 | a humanoid of living flame; doomknight3 has neither attack1 nor attack2 |
| `@3` | Orc Shaman | wraith1 x1 | fallenshaman1 x1 | small horned caster, the same size; native to Act 1 |
| `0k` | Corpse Worm (Act 1 graveyard) | painworm1 x0.9 | maggotbaby1 x1.5 | pale segmented larva; the Pain Worm draws as a burrowing glow |

Scales follow the art: Median's NU frame height over the donor's classic one, evened out with the width for flyers and beasts.

### 9.3 All reviewed tokens

"Modes without a clip": the Median modes (monstats2, KB / SQ left out) the stand-in has no clip for; since 9.1 they play the fallback
clip. Kept as they are: the picks whose silhouette, size and attack style match well enough for a stand-in (`#0` troll on irongolem,
`2(` fungus on thornhulk1 and `^3` wyrdwolf on the werewolf `wolf`, whose missing death clips fall back to knockback / gethit, are
the weakest).

| Token | Act 1-2 Ids | Where | Stand-in before | Now | Confidence | Modes without a clip (now filled) |
|---|---|---|---|---|---|---|
| `!2` | `uq_darkfey3` | A1 Cave 5 Treasure | councilmember1 x0.75 | same | medium | A2 |
| `!3` | `couatlchild1`, `couatlchild2`, `couatlchild3` | A1 Wilderness 5; A2 Desert 1; A2 Desert 3; A2 Desert 4 +3 | clawviper1 x1 | same | high | - |
| `!5` | `cultist1`, `hell_cultist`, `uq_cultist2` | A1 Barracks; A1 Cave 5 Treasure; A1 Courtyard 1; A1 Crypt 2 A +3 | councilmember1 x1 | same | high | SC |
| `!7` | `sarandesh1`, `uq_sarandesh_elite` | A1 Cave 5 Treasure; A1 Wilderness 2; A1 Wilderness 3 | fetishblow1 x1.7 | same | medium | - |
| `!8` | `treeppl1` | A1 Graveyard; A1 Wilderness 2 | thornhulk1 x0.9 | same | medium | - |
| `!a` | `gargoylebeast1`, `hell_gargoylebeast`, `uq_gargoylebeast2` | A1 Cave 5 Treasure; A1 Crypt 2 A; A2 Basement 1; A2 Basement 2 +3 | batdemon1 x1.4 | same | medium | - |
| `#0` | `troll1`, `troll2`, `uq_troll_elite` | A1 Cave 5 Treasure; A2 Basement 1; A2 Basement 2; A2 Basement 3 +4 | irongolem x1.1 | same | high | GH A2 |
| `#5` | `creepshow1`, `hell_creepshow`, `uq_creepshow2` | A1 Cave 3; A1 Cave 5 Treasure; A1 Crypt 2 A; A1 Wilderness 4 +1 | clawviper1 x1 | same | high | - |
| `#6` | `thepack_elite`, `thepack_elite2` | A2 Sewer 1 A; A2 Sewer 1 B; A2 Sewer 1 C; with thepack_elite2 | snowyeti1 x0.5 | same | medium | - |
| `#w` | `robedagger` | A1 Cave 2 Treasure; A1 superunique WycBoss1 | darkwanderer x1 | **councilmember1 x1** | medium | A2 |
| `#y` | `zombierags` | A1 Cave 2 Treasure; A1 superunique WycBoss2 | wraith1 x1.3 | **zombie1 x1.4** | high | - |
| `%9` | `uq_mahasattva` | A1 Cave 5 Treasure | baalminion1 x1.1 | same | medium | SC S1 |
| `&b` | `deathwing1` | A2 Desert 4; A2 Valley of the Kings | eagle x0.7 | **vulture1 x1.2** | medium | A2 |
| `(0` | `uq_dragonknight3` | A1 Cave 5 Treasure | hephasto x1 | same | high | A2 |
| `(1` | `hell_dragonknight`, `quest_inarius` | A1 Crypt 2 A; A1 superunique Inarius; A2 Tomb 1 A | darkwanderer x1.35 | **doomknight2 x1.25** | high | A2 |
| `(2` | `dragonknight1` | A2 Desert 1; A2 Desert 2; A2 Desert 3 | doomknight2 x1.25 | same | high | A2 |
| `(c` | `junglesnake` | A2 Tomb 2 Treasure | clawviper1 x0.9 | same | high | - |
| `(g` | `flit1`, `flit2` | A1 Wilderness 1; A2 Tomb Tal 1; A2 Tomb Tal 2; A2 Tomb Tal 3 +1 | druidhawk x0.8 | same | high | GH A2 |
| `(i` | `firebeetle` | with uq_mahasattva | scarab1 x0.85 | same | high | - |
| `(l` | `hell_magmademon`, `magmademon1` | A1 Crypt 2 A; A2 Tomb 1 A; A2 Tomb Tal 1; A2 Tomb Tal 2 +2 | deathmauler1 x1.15 | same | high | - |
| `(n` | `astrogha` | A1 Crypt 2 A | arach1 x1.2 | same | high | SC |
| `(o` | `berserk1`, `uq_berserk2` | A1 Cave 5 Treasure; A2 Desert 3; A2 Desert 4 | brute2 x1 | same | medium | - |
| `0!` | `quest_subboss` | A1 superunique High Cleric Dorian; A1 superunique High Cleric Gray | summoner x0.8 | same | high | A1 |
| `08` | `fellfiend1` | A2 Sewer 1 A; A2 Sewer 1 B; A2 Sewer 1 C; A2 Tomb 2 A | warputriddefiler x0.85 | same | high | A2 |
| `0k` | `corpseworm` | A1 Graveyard | painworm1 x0.9 | **maggotbaby1 x1.5** | medium | - |
| `0n` | `onyxknight1`, `uq_onyxknight2` | A1 Catacombs 1; A1 Catacombs 2; A1 Catacombs 3; A1 Catacombs 4 +1 | sandraider1 x1.15 | same | high | S1 S2 S3 |
| `2!` | `harlequin1` | A1 Cathedral; A1 Tristram; A1 Wilderness 3; A1 Wilderness 4 | warputriddefiler x0.7 | same | medium | A2 |
| `2#` | `omgitslaz` | A2 Tomb 1 A | summoner x0.8 | same | high | A2 |
| `2(` | `fungus1` | A1 Cave 3; A1 Wilderness 3; A1 Wilderness 4 | thornhulk1 x0.75 | same | low | - |
| `5$` | `porkchop_elite`, `porkchop_elite2` | A1 Crypt 3 A; A1 Crypt 3 B; A1 Crypt 3 C; A1 Crypt 3 D +1 | siegebeast1 x1.5 | same | high | - |
| `9!` | `centaur1`, `centaur2`, `uq_centaur3` | A1 Cave 5 Treasure; A2 Basement 1; A2 Basement 2; A2 Basement 3 +2 | quillbear1 x1 | **clawviper1 x1.3** | low | - |
| `9(` | `hell_runepriest`, `runepriest1` | A1 Crypt 2 A; A2 Desert 1; A2 Desert 2; A2 Tomb 1 A | councilmember1 x0.9 | same | high | A2 SC |
| `9x` | `regularamazon` | A2 Tomb 2 Treasure | cr_archer1 x0.75 | same | high | SC |
| `@3` | `orkshaman` | A1 Cave 2 Treasure; A1 superunique WycBoss5 | wraith1 x1 | **fallenshaman1 x1** | high | SC |
| `@6` | `firewizard1`, `hell_firewizard`, `horazonastralguard` +2 | A1 Cave 5 Treasure; A1 Crypt 2 A; A2 Sewer 2 A; A2 Tomb 1 A +2 | doomknight3 x1.15 | **firegolem x1.1** | medium | GH A2 |
| `@c` | `greenzombie` | A1 Cave 2 Treasure; A1 superunique WycBoss3 | darkwanderer x0.9 | **zombie1 x1.15** | high | - |
| `@f` | `bugbear1`, `uq_bugbearE` | A1 Cave 5 Treasure; A2 Lair 1 A; A2 Lair 1 B; A2 Lair 1 Treasure | brute2 x1.2 | same | high | - |
| `^3` | `uq_wyrdwolf2` | A1 Cave 5 Treasure | wolf x0.9 | same | high | DT DD |
| `b#` | `crystal1` | A1 Crypt 3 A; A1 Crypt 3 B; A1 Crypt 3 C; A1 Crypt 3 D | cantor1 x1 | same | high | A2 |
| `bu` | `quest_butcher` | A1 Cave 4 Treasure | blunderbore1 (vanilla_ids pin) | same | unseen | - |
| `c@` | `cloakdagger` | A1 Cave 2 Treasure; A1 superunique WycBoss4 | wraith1 x1.25 | **councilmember1 x1.1** | medium | A2 |
| `g7` | `pest1`, `uq_overseer_pest` | A1 Cave 5 Treasure; A2 Desert 1; A2 Sewer 1 A; A2 Sewer 1 B +1 | brute2 x0.55 | same | medium | - |
| `im` | `necromorb` | A1 Cave 2 Treasure | claygolem x1 | same | low | - |
| `ji` | `dead3` | A2 Basement 1; A2 Basement 2; A2 Basement 3; A2 Corrupt Harem 1 | darkwanderer x1.15 | **sandraider1 x0.85** | medium | - |
| `~2` | `cavetroll1`, `cavetroll_afk`, `cavetroll_elite` | A1 Cave 3; A1 Cave 4; A1 Cave 5; A1 Wilderness 3 +3 | brute2 x1 | same | high | - |
| `~k` | `hardliner` | A2 Tomb 1 Treasure | bonefetish1 x2.3 | same | medium | A2 |

### 9.4 In game

See docs/testing.md "Lane hdmon2" for the harness run (graphics check in HD, seen with the harness, not a player-path verification).

## 10. Stand-in colour fixes (lane tints2, 2026-10-29)

hdmon2's harness shots (9.4) were read as cloakdagger, hell_dragonknight and dead3 blue and corpseworm and cultist1 green. Looked
at again (crops of `checks-20261029-043155-s3`): the bright green figure in the corpseworm and cultist1 shots is **the player**
(the bald barbarian, standing where he stood all run; the orkshaman spawned before them threw a poison cloud), and the blue is
the lightning / cold hit sparkles on the player; dead3 is not in its frame at all. The stand-ins themselves are not blue or green.
A calibration run (test build, one colour per stand-in, `checks-20261029-052910-s4`) confirmed D2R's `colorAdjustment.x` is a
hue turn that wraps: 0.98 on councilmember1 looks like 0 (natural), 0.33 on zombie1 green, 0.5 cyan; saturation +0.12 and
value +0.25 alone stay natural.

Two real faults of the colour step were found on the way and fixed in the tools:

- **Partial hue turns** (`hd_donors.tint_of`). The hue turned by the difference times a hue weight (hue agreement times mean
  saturation / 0.25). A turn scaled down stops on a hue in between, and the mean saturation undercounts art with much grey: Inarius /
  hell_dragonknight (`(1`) is blue armour beside grey and white (classic render; mean saturation 0.09, weight 0.26), and on the
  olive Doom Knight it turned +0.12, a quarter of the way, which is green. Now the hue turns all the way when both arts have a
  hue (`has_hue`: hue agreement `HUE_MIN_CONF` 0.45 and mean saturation `HUE_MIN_SAT` 0.08), else not at all (grey art is
  reached by the saturation offset). Checked on classic renders of the tokens this moves: dark fey `!2` is cyan, the Glowing One
  `!!` green, Inarius blue (all turned now); the Dark Star Dragon `!d`, Flit `(g` and the yeti donor of `#6` are grey (no turn).
  `hd_monsters.py recolour` redid the 11 tokens whose hue moves by 0.04 or more: `!!` -0.27, `!2` +0.43, `!3` +0.42, `(1` +0.44,
  `(2` -0.14, `(a` -0.05, `2(` -0.49, `9(` +0.10, and `!d` `#6` `(g` 0.
- **The donor's own level0 look was dropped** (`hd_units.variant_table`). A stand-in table replaced the donor's whole variant
  table, but D2R draws a TransLvl-0 monster through the `level0` entry, and for 10 donors that entry changes the look a lot
  (`arach1` value +1 and tints, `brute2` and `warputriddefiler` tints, `clawviper1`, `scarab1`, `blunderbore1`, `frogdemon1`
  value, `mummy1` and `suicideminion1` tints, `maggotbaby1` value -0.34). The colour is measured against the donor's classic art,
  the look that entry gives, so the shift now sits on top of it (`hd_units.level0_entry` / `compose_transform`: hue turns add,
  saturation and value add and clip, D2R's own out-of-range values are kept, the donor's tint stays unless ours has one).
  Such tables cannot be shared across donors: `hd_monsters.colour_tables` gives them out most used first while all tables stay
  within `COLOUR_TABLE_LIMIT` (30, the build has 30). The tokens with the most Ids get theirs; 7 tokens of one or two Ids stay on
  the plain shared table (reported "donor's level0 not kept"; 60 Ids on 15 tokens keep it): `!1` `(n` (arach1), `#r` `(i` (scarab1), `$f` (warputriddefiler),
  `(c` (clawviper1), `!h` (suicideminion1).

Of the five tokens of the report: `(1` changed (hue +0.44: blue; it shares the table hue +0.42 sat -0.45 val +0.05), `0k`
(corpseworm) now on maggotbaby1's level0; `c@` `ji` `!5` unchanged (their colours fit the classic art: tan robe, orange-skinned
fighter, red robe). Tests: `tools/tests/test_hd_monsters.py`
(`StandInColour`, `ColourTables`, the committed-mapping table count). In game: docs/testing.md "Lane tints2".

## 11. Act 3-5 Normal pass (lane hdmon3, 2026-10-29)

The same review as section 9 for Act 3, 4 and 5 Normal: the `mon1-25` / `umon1-25` of the levels of Acts 3-5, the Act 3-5
`monpreset` places (superuniques by their `Class`), their minions, `spawn` monsters and summons. 92 Ids on **47 tokens** draw a
stand-in (Act 3: 37 tokens, Act 4: 10, Act 5: 28; many spawn in more than one act; 30 of the 47 were already in section 9).
Ids of tokens D2R has its own unit for are not listed. A contact sheet (Median's classic NU frame beside the donor's classic NU
frame at our scale, rendered offline as in section 9; scratch, not in git) was made for all 47 and for the candidates.

### 11.1 Modes with no state at all (`hd_units.state_fill`)

Section 9.1's clip fill rebinds a state whose clip the donor lacks; it cannot help when the machine has **no state** for the
mode. Two donors had that: `colbarbwhirl` (no Block, Cast or Skill1-4 states; it stood in for the Couatl fathers `!4`, which cast)
and `frozenhorror1` (its attack2 is only a skill sequence, modeId 14, so the Shardspawn `ie`'s A2 had nothing to play; section
4 said "A2 plays attack1", which the build never did). `build` now adds, in the adapted machine, a state for every mode of
DT, GH, A1-S4, DD, KB that has none: a copy of the state that plays the mode's own clip (also a sequence state), else of the
first `CLIP_FALLBACK` clip, as a plain state (no skill index, no events) with the copied state's transitions in and out (walk
and run are often named layers, modeId 100, and are never added). The build report lists it ("Modes a donor has no state
for"). After the re-picks below only `frozenhorror1` needs it (Shardspawn A2 plays attack2); `colbarbwhirl` is no donor any more.

### 11.2 Changed stand-ins (hand picks in `hd_monster_pins.json`, `tools/hd_monsters.py repin`)

Colour is what the donor scoring works out for the new donor (no colour code changed). The colour tables stay at 30
(`COLOUR_TABLE_LIMIT`, bug #360); `$f` (vampire1) and `#q` (arach1) are among the 7 tokens left on a plain shared table
("donor's level0 not kept", section 10), as `$f` was before.

| Token | Monsters | Before | Now | Why |
|---|---|---|---|---|
| `!4` | Couatl (NiVa, Couatl fathers; Act 3 Kurast) | colbarbwhirl x1.25 | clawviper1 x1.4 | an upright feathered serpent with a humanoid torso, not a barbarian; colbarbwhirl has no Cast state and the fathers cast. The Couatl children `!3` already stand on the Claw Viper |
| `#m` | Belial (Act 5 Ice Cave boss) | colbarbwhirl x0.9 | baalminion1 x0.75 | hunched horned demon with claws, not a human barbarian; Act 5 unit |
| `&g` | Heavy Drone (Act 3 Temple 2) | colbarbwhirl x0.9 | irongolem x1.3 | bulky walking machine with a gun arm: D2R's only metal construct |
| `#l` | Light Drone (Act 3 Temple 2) | bonefetish1 x1.95 | irongolem x1 | the Heavy Drone's slim white twin, not a skeletal fetish |
| `#q` | Enforcer with Laser (Act 3 Temple 2) | hydra1 x1 | arach1 x0.85 | a machine on long jointed legs; the hydra is a head that cannot walk (walk / gethit clips missing) |
| `$f` | Rathma Primus (Act 3 superunique) | warputriddefiler x1 | vampire1 x1.4 | pale winged humanoid caster, not a hunched beast; the Vampire is a humanoid caster with attack1 / cast and the AI Median gives it (D2R has no winged man) |
| `%9` | Mahasattva (Act 5 Baal temple; Act 1 Cave 5 Treasure) | baalminion1 x1.1 | clawviper1 x1.5 | multi-armed naga: a snake tail under an armed torso. Section 9 kept it (medium); the serpent body is the defining shape |
| `(0` | Dragon knight 3 (Coldkill Iceguard, Act 5 Baal temple, World Stone) | hephasto x1 | doomknight2 x1.25 | horned armoured knight with a long sword; the fat smith demon did not fit. Same donor and scale as the family's other knights `(1` `(2`. Section 9 kept it for one Act 1 Id |
| `!s` | Howling (brainpower, Act 5 Hell 2; also the male witches) | cantor1 x1.35 | wraith1 x1.4 | dark purple ghost with scythe claws, not a red-robed priest |
| `2!` | Harlequin (Act 4; Act 1 harlequin1) | warputriddefiler x0.7 | sandraider1 x0.8 | an armoured human fighter with blades (the same art as the Priest `1!`), not a hunched beast |

Scales follow the art as in 9.2 (Median's NU frame height over the donor's classic one, evened out with the width).

Kept, but weak (no D2R unit is clearly closer): `&d` Hemoplague (a red blob on mummy1 x0.5), `~3` Magineer (a winged contraption
with cannons on cantor1), `(r` Feyr (a red crouching flesh beast on hephasto x0.9), `(i` Fire Beetle (a crawling beetle on the
upright scarab1), `#5` Creepshow (a crawling spiny lizard on the upright clawviper1), `1!` Priest (an armoured fighter on cantor1;
`2!` has the same art and moved to sandraider1, `1!` was left as section 9 chose it), `!2` Dark Fey (a slender woman on the
hunched councilmember1). `im` Lantern draws D2R's own art (class mixed) on claygolem.

### 11.3 All reviewed tokens

"Modes filled": the Median modes the stand-in has no clip (9.1) or no state (11.1) for, now bound to one it has. Walk and run
are not listed (named layers in most machines; every donor here has a walk clip).

| Token | Act 3-5 Ids | Where | Stand-in before | Now | Confidence | Modes filled |
|---|---|---|---|---|---|---|
| `!1` | `quest_lucion` | A5 superunique Lucion | arach1 x1.35 | same | medium | SC |
| `!2` | `darkfey1`, `darkfey2`, `uq_darkfey3` | A3 Jungle 1; A3 Jungle 2; A3 Sewer 1; A3 Sewer 2 +12 | councilmember1 x0.75 | same | medium | A2 |
| `!4` | `couatlchild_elite` | A3 Kurast 1; A3 Kurast 2; A3 Kurast 3 | colbarbwhirl x1.25 | **clawviper1 x1.4** | medium | - |
| `!5` | `cultist2`, `hell_cultist`, `su_cultist2` +1 | A3 Mephisto 3; A4 Mesa 1; A4 Mesa 2; A5 Ice Cave 3A +2 | councilmember1 x1 | same | high | SC |
| `!7` | `sarandesh_elite`, `uq_sarandesh_elite` | A4 Mesa 2; A3 Temple 3 | fetishblow1 x1.7 | same | medium | - |
| `!8` | `baalset_treeppl2`, `treeppl2` | A5 World Stone; A3 Jungle 1; A3 Jungle 2; A3 Jungle 3 | thornhulk1 x0.9 | same | medium | - |
| `!a` | `gargoylebeast2`, `hell_gargoylebeast`, `uq_gargoylebeast2` | A5 Barricade Snow; A5 Ice Cave 1; A5 Ice Cave 1A; A5 Ice Cave 2 +2 | batdemon1 x1.4 | same | medium | - |
| `!e` | `azmo_special` | A3 superunique Azmodan | baalminion1 x1.15 | same | medium | SC S1 |
| `!s` | `brainpower` | A5 Hell 2 | cantor1 x1.35 | **wraith1 x1.4** | medium | - |
| `#0` | `troll_elite`, `uq_troll_elite` | A4 Diablo 1; A3 Temple 3 | irongolem x1.1 | same | high | GH A2 |
| `#5` | `creepshow2`, `hell_creepshow`, `uq_creepshow2` | A4 Diablo 1; A4 Lava 1; A4 Mesa 2; A5 Ice Cave 3A +1 | clawviper1 x1 | same | high | - |
| `#l` | `combatdrone2` | A3 Temple 2 | bonefetish1 x1.95 | **irongolem x1** | medium | GH A2 |
| `#m` | `belial` | A5 Ice Cave 3A | colbarbwhirl x0.9 | **baalminion1 x0.75** | medium | - |
| `#q` | `cube1` | A3 Temple 2 | hydra1 x1 | **arach1 x0.85** | medium | - |
| `#r` | `cube2` | A3 Temple 2 | scarab1 x1.3 | same | high | - |
| `$f` | `rathma_primus` | A3 superunique RathmaPrimus | warputriddefiler x1 | **vampire1 x1.4** | medium | A2 |
| `%9` | `mahasattva`, `uq_mahasattva` | A5 Baal Temple 2; A5 Baal Temple 3; A3 Temple 3 | baalminion1 x1.1 | **clawviper1 x1.5** | medium | SC S1 |
| `&b` | `deathwing2`, `deathwing3` | A3 Mephisto 2; A3 Mephisto 3; A5 Ice Cave 3; A5 Temple 1 +1 | vulture1 x1.2 | same | medium | A2 |
| `&d` | `blotM2`, `blotM_stage2` | A3 Jungle 2; from blotM2 | mummy1 x0.5 | same | medium | SC |
| `&g` | `combatdrone1` | A3 Temple 2 | colbarbwhirl x0.9 | **irongolem x1.3** | medium | GH A2 |
| `(0` | `baalset_dragon3`, `dragonknight3`, `su_dragon3` +1 | A5 World Stone; A5 Baal Temple 1; A5 Baal Temple 2; A5 Baal Temple 3 +3 | hephasto x1 | **doomknight2 x1.25** | high | A2 |
| `(1` | `dragonknight2`, `hell_dragonknight` | A3 Mephisto 1; A3 Mephisto 2; A3 Mephisto 3; A3 Travincal +1 | doomknight2 x1.25 | same | high | A2 |
| `(i` | `firebeetle` | from uq_mahasattva | scarab1 x0.85 | same | high | - |
| `(l` | `hell_magmademon`, `magmademon2`, `magmademon3` +2 | A5 Ice Cave 3A; A4 Mesa 2; A4 Mesa 3; A4 Diablo 1 +6 | deathmauler1 x1.15 | same | high | - |
| `(o` | `baalset_berserk2`, `berserk2`, `uq_berserk2` | A5 World Stone; A3 Mephisto 1; A3 Mephisto 2; A4 Mesa 1 +2 | brute2 x1 | same | medium | - |
| `(r` | `feyr` | A5 Ice Cave 2A | hephasto x0.9 | same | medium | A2 |
| `(s` | `giant1`, `giant2` | A3 Temple 1; A3 Temple 4; A3 Temple 6; A5 Ice Cave 1A +1 | blunderbore1 x1.65 | same | medium | - |
| `(x` | `slimer1`, `slimer2` | A3 Kurast 1; A3 Kurast 2 | frogdemon1 x1 | same | medium | - |
| `0!` | `quest_malic` | A5 superunique NewMalic | summoner x0.8 | same | high | A1 |
| `0(` | `fallenwolf1`, `fallenwolfE` | A3 Kurast 2; A3 Travincal; A5 Ice Cave 3; A5 Temple 1 +2 | wolf x1 | same | high | DT DD |
| `08` | `baalset_fellfiend2`, `fellfiend2` | A5 World Stone; A4 Diablo 1; A4 Lava 1; A4 Mesa 3 +1 | warputriddefiler x0.85 | same | high | A2 |
| `0n` | `onyxknight2`, `su_onyxknight2`, `uq_onyxknight2` | A3 Jungle 1; A3 Jungle 2; A3 Jungle 3; A4 superunique Bluehorn The Flayer +1 | sandraider1 x1.15 | same | high | S1 S2 S3 |
| `1!` | `l_priest` | from l_slayer | cantor1 x0.9 | same | medium | A2 |
| `2!` | `harlequin2` | A4 Diablo 1; A4 Lava 1 | warputriddefiler x0.7 | **sandraider1 x0.8** | medium | - |
| `2#` | `l_slayer` | A3 Dungeon 1 Treasure | summoner x0.8 | same | high | A2 |
| `2(` | `fungus2` | A3 Dungeon 2 A; A3 Dungeon 2 B; A3 Kurast 1; A3 Kurast 2 +1 | thornhulk1 x0.75 | same | low | - |
| `9!` | `centaur2`, `centaur3`, `uq_centaur3` | A3 Kurast 3; A3 Mephisto 2; A3 Sewer 1; A3 Sewer 2 +5 | clawviper1 x1.3 | same | low | - |
| `9(` | `hell_runepriest`, `runepriest2`, `su_runepriest2` | A5 Ice Cave 3A; A4 Diablo 1; A4 Lava 1; A4 Mesa 3 +1 | councilmember1 x0.9 | same | high | A2 SC |
| `@6` | `firewizard2`, `firewizardE`, `hell_firewizard` +2 | A3 Mephisto 1; A3 Mephisto 2; A3 Mephisto 3; A5 Ice Cave 1 +5 | firegolem x1.1 | same | medium | GH A2 |
| `@f` | `bugbearE`, `su_bugbearE`, `uq_bugbearE` | A5 Barricade 1; A5 Barricade 2; A5 Siege 1; A3 superunique Bilefroth the Pit Master +1 | brute2 x1.2 | same | high | - |
| `^3` | `uq_wyrdwolf2`, `wyrdwolf1`, `wyrdwolf2` | A3 Temple 3; A3 Dungeon 1 A; A3 Dungeon 1 B; A3 Dungeon 2 A +5 | wolf x0.9 | same | high | DT DD |
| `b#` | `crystal2` | A3 Travincal | cantor1 x1 | same | high | A2 |
| `g7` | `overseer_pest`, `pest2`, `uq_overseer_pest` | A5 Barricade 1; A5 Siege 1; A3 Temple 3 | brute2 x0.55 | same | medium | - |
| `ie` | `shardspawn` | A5 World Stone | frozenhorror1 x1.1 | same | medium | A2 |
| `im` | `lantern` | A5 Hell 3 | claygolem x1 | same | low | - |
| `~3` | `magineer` | A3 Temple 2 | cantor1 x1.15 | same | high | SC |
| `~m` | `attackrat` | from belial | quillrat1 x0.5 | same | medium | - |

### 11.4 In game

Check `hm3_monsters` (`tools/game_checks.py`, the list `HM3_MONSTERS`: the ten re-picked tokens plus the Shardspawn's new A2
state and the Couatl father's cast) spawns each in HD beside a tanked character, shots near / fight / death, judged by hand.
It shares the routine of `hm2_monsters` (`hm_monsters`). See docs/testing.md "Lane hdmon3" for the run or why it is pending.

## 12. In-game look of the Act 1-5 stand-ins (lane hdmonlook, 2026-10-29)

`hm2_monsters` and `hm3_monsters` were run in HD and in classic graphics (`MXL_HM_GRAPHICS=legacy`, new) on one slot; each
token's HD shots were judged by hand against the same monster in classic (silhouette, size, colour, animation, drawn at all).
Results per token: docs/testing.md "Lane hdmonlook". The check now spawns each monster 8 subtiles to the screen left or right
and takes a `far` shot first: next to the player the monster was hidden by the player, his poison / lightning effects and the
corpses of the ones before.

Pins can now hold a colour set by hand (`adjust` [hue turn, saturation, value], optional `tint` [r, g, b, amount]): the scored
colour is measured on classic art only, and some HD skins differ from their classic sprite (zombie1 is green in HD).
`pinned_entry` takes it over the scored one (the tables show "(hand)"), `recolour` leaves it alone. Test: `HandColours`.

| Token | Change | Why (seen in game) |
|---|---|---|
| `1!` Priest | cantor1 x0.9 -> **sandraider1 x0.8** | the same classic art as the Harlequin `2!` (coordinator: same donor as `2!`); seen: orange-tan armoured fighter, fits the brown-orange art |
| `!s` Howling | wraith1 x1.4 -> **bloodlord1 x1.0** | every Howling spawn logged an engine assert (`BC_ASSERT: result`, animation_event_handler.cpp:608; bisected to brainpower alone); wraith1 has no attack2 clip and Howling attacks in A1 and A2. On the Blood Lord (attack1 + attack2 clips): no assert in 4 runs, a purple winged demon |
| `#y` Zombie Rags | colour by hand: sat -0.7, val +0.25 | zombie1 drew bright green; the art is pale grey-white. Seen after: pale grey-white |
| `!4` Couatl father | colour by hand: hue +0.42 (as `!3`), sat -0.1 | the Claw Viper drew tan-brown; the art is teal-green with a magenta crest. Seen after: teal-green |
| `@3` Orc Shaman | scale 1.0 -> **1.6**, colour by hand: hue +0.08, sat -0.1, val +0.25 | the Fallen Shaman stood at about half the art's height (about 0.9 of the player's) and red. Seen after: about the player's height, olive-tan with its staff |
| `#0` Troll | irongolem x1.1 -> **thornhulk1 x0.7** (new pin) | the Iron Golem drew as a bulky silver metal golem (its yellow tint did not show); the art is a lanky olive-yellow troll. x1.0 was half again the player's height; x0.7 seen: olive-yellow hunched brute of the player's height |
| `9!` Centaur | colour by hand: sat -0.9, val +0.3, white tint 0.45 | the Claw Viper drew brown; the art is a white horse body. Seen after: pale white-grey. The shape stays a serpent (D2R has no centaur) |
| `2!` Harlequin | colour by hand: hue +0.25, sat -0.1, val +0.2 | the Sand Raider drew orange-tan; the art is green armour with purple claws. Seen after: green armoured fighter |
| `&b` Deathwing | colour by hand: sat -0.5, val +0.7, bone-white tint 0.5 | the Vulture drew dark brown; the art is a pale bone-white winged skeleton. **Not seen after**: in the Rocky Waste it stayed behind a ruin in every shot |

Tried and dropped (no visible effect, back to the scored colour): `#m` Belial (bright green in HD whatever its table says:
bug #436; the cause was state `meslayer`'s colour shift, section 14), `$f` Rathma Primus (a hand value +0.9 drew it as a dark, almost invisible column; the scored colour draws a dark
green-grey robed figure where the art is a pale bare-skinned man), `#q` Enforcer (the spider stays dull red-brown, the art is a
golden box on legs). These three stay FAIL on colour in docs/testing.md. The colour tables stay at 30.

## 13. Quill Bear level colours (lane picktint, 2026-10-29, bug #435)

The Quill Bears 1-5 (`quillbear1-5`, token `s7`) draw one vanilla stand-in, while classic gives each TransLvl its own
`palshift.dat` colour. `hd_monsters.levelled_tokens` finds such tokens (a vanilla stand-in whose classic token has `palshift.dat`
and whose Ids sit on TransLvl 1-4); each gets a table of its own whose `level0`..`level4` entries are measured by
`hd_translvl` (`level_entries`). These tables are never shared: the nearest shared table (`v_3632852f`) also serves the clay
golem elementals, Toraja and henchmen at TransLvl 2. `colour_tables` weighs them by Ids like the donor-level0 tables.

Only `s7` qualifies. Its table `v_f3dbcad4`: level 1 hue -0.28 sat +0.16, level 2 hue +0.26 sat -0.06 val -0.20, level 3 sat
-0.26 val -0.61 (black), level 4 hue -0.31 sat +0.15. The build stays at **30 tables** (`COLOUR_TABLE_LIMIT`): the token with the
fewest Ids among the donor-level0 tables, Astrogha `(n` (arach1 donor, 1 Id), went to the plain shared table (reported "donor's level0
not kept"). The limit could go to 31 (measured safe up to 50) to keep both. Tests:
`test_levelled_token_gets_its_own_table_within_the_limit`, `test_committed_tables_stay_at_the_limit_with_the_quill_bear_levels`.
In game: five Quill Bears in five colours (`hdl_mon_quill_hd_0.png`, docs/testing.md "Lane picktint").

## 14. Veil King and state colour shifts (lane veilking, 2026-10-29, bug #496)

`!9` (Summon Veil King, `veilkings`, `veilking_rean`): the art is a crowned skeleton king, gold-yellow bones and crown, black
pauldrons, a long sword (75x127 px). Stand-ins compared in game in HD (`mxl2012-runs/veilking/candidates.png`: legacy frames,
then each candidate spawned beside the player): **doomknight1** (gold-bronze skeletal knight, horned crown-like helm, sword:
picked), doomknight2 (the same body with a cape, casts fire), doomknight3 (caster, green glow), reanimatedhorde1 (dark horned
undead), unraveler1 (golden headdress, but a mummy with a blade), radament, skmage_cold1, vampire1, the plain skeleton.

| Change | Why (seen in game) |
|---|---|
| skeleton1 x1.75 -> **doomknight1 x1.1** | x1.6 (the size rule) drew it twice the player's height; x0.9 a little below the player; x1.1 about the legacy 1.15 |
| colour by hand: val +0.2 (shares the plain table) | the scored hue +0.02 sat -0.26 shared the hue +0.10 table and drew olive; the plain table keeps the Doom Knight's own gold-bronze |
| state `meslayer` colorshift 1 -> 0 (`txt_migrate.py` `STATE_COLOUR_SHIFTS`) | see below |

**State colour shifts in HD.** A states.txt `colorshift` recolours a unit while the state is on. Classic draws the unit through
the act palette's colour-shift table of that index (tables 0 and 1 are both the identity); D2R's HD renderer has a colour of
its own per index and draws **1 bright green** whatever the unit's variant table holds. A variant table's
`customColorShiftEntries` (`CustomVariantColorShiftMap`, `colorShiftIndex` + one colour entry; D2R uses it for index 130, the
Warlock's bound demons) for index 1 was tried and is **not** used: still green. `meslayer` (Median 186, built 232) now has
colorshift 0: identity in classic, no tint in HD. Every unit with the state changes the same way (bugs.md #496 lists them;
Belial, #436, was one). 48 more Median states use colorshift 1 (curses, auras, buffs such as `ongoing_typhoidmary`,
`banished`, `vindicated`): all changed by lane hdgreen (section 15).

## 15. All colorshift-1 states, totem orbs, empty overlay stubs (lane hdgreen, 2026-10-30, bugs #500, #506, #507)

**The other 48 colorshift-1 states (bug #506).** All 48 now have colorshift 0, like `meslayer`: one table in
`tools/txt_migrate.py` (`STATE_COLOUR_SHIFTS`, state -> old, new, what applies it). Why 0 for every one: 1.14d picks the
colour of the active state with the highest `colorpri` (`STATES_UpdateColorShiftAndLight`, 0x4d97f0) and recolours through
that index's table; in Median's `Pal.pl2` table 1 is the identity but for 76 of 256 entries that move one hue step (reds a
touch more orange), so classic shows the unit in its own colours. HD draws index 1 neon green. No state needs a tint index
instead. The priority winner does not change (colorpri is kept), so a lower state's colour (cold, poison) stays hidden under
these states as in classic. In game (slot 1, `mxl2012-runs/hdgreen/g1/`, `g2/`, sheets `sheet_*.png`): 39 of the 49 states
were put on the client by real casts (class skills on Hdg* characters, monster skills given to a Necromancer); before, every
HD shot is green and every legacy shot is the unit's own colours; after, HD shows no green. The 10 not seen on the client
(`careforabloodbath`, `broadsided`, `behindenemylines`, `tritonstate`, `trapratstate`, `barbaricheal`, `caution`,
`goodberries`, `lionheartstate`, `burnedbyburn`: cast refused or the state lands elsewhere) use the same index, so the same
rule holds.

**Moved totems leave their orb (bug #500).** D2R's `lightningspire` unit draws its glass orb with a vfx entity
(`fx_lightningspire_ambient_ball.particles`) whose particles live in world space: the spire never moves in vanilla. Tried
(`mxl2012-runs/hdgreen/tot1/`, `tot2/`): attaching the vfx to bone Root (the shell still stays), the nfrost copies of the
particle (missing-texture squares), and other units' glows on the spire (willowisp: white smoke; skmage wrist: a small flame,
both move with it). The build now gives the 12 skill-summoned Ids drawn with `lightningspire` (`WORLD_VFX` and
`skill_summons` in `tools/hd_monsters.py`: totem1, 3-9, A, Z, QQ, HOWL) the unit `mxl_lightningspire_moved`, a copy without
that vfx entity: the spire, its lightning and its death are kept, the glass orb is gone. Ids nothing moves (quest crystals,
monster-only totems) keep D2R's unit with its orb.

**Overlay picks on empty D2R stubs (bug #507).** D2R ships 86 HD overlay definitions with no components (e.g.
`monster/fetishdeath_2`, `necro/cast_familiar`); a stand-in copied from one draws nothing. That is why `slayercloud` (the
Veil King's pale cloud) was not seen in HD. Hand picks fixed: `slayercloud` -> `druid/cyclonearmor_1back` (pale swirling
bands; `veil2/`), `mooncast` -> `sorceress/teleport`. `tools/effects_hd.py` now stops on a hand pick that is an empty stub.
The 20 overlays the reference mapping still pointed at empty stubs were done by lane fxpick (2026-10-30): 16 hand picks
(bugs.md #507 lists them), 4 arts no skill or state uses keep the stub (`extra/aurablue`, `aurared`, `aurast_bl`, `aurast_rd`).
**A state overlay loops, so its stand-in must loop too:** a one-shot D2R effect (a hit or burst such as
`sorceress/frozenarmor_hit`, `common/ice_explode`, `sorceress/srfirehit`) shows once when the state starts and then nothing,
where classic keeps drawing the overlay; aura rings, `common/burning` and the shrine glows loop. `sorceress/enchant` draws on the
weapon only and `sorceress/frozenarmor` is a distortion: neither is seen on another unit. Tests: `test_overlay_picks_not_empty`,
`test_no_stub_stand_ins` (tools/test_effects_hd.py).

## 16. Most-seen Median-only stand-ins that look most wrong (lane itemart, 2026-10-30, report only)

Ranked by the number of areas whose levels.txt `mon` / `nmon` / `umon` columns name the monster (monstats `Code`, lower
case, against the tokens of `hd_monsters`), then the 21 most-seen Median-only rows looked at in HD (check `itemart_mons`,
`hm_monsters` far / near / fight / death shots, slot 4; the first 13 also in legacy). Nothing changed; suggestions for a
later round (owner picks):

| # | Id (areas) | HD stand-in now | what looks wrong | suggestion |
|---|---|---|---|---|
| 1 | `9!` Centaur (24) | pale serpent `clawviper1` | a snake for a horse-bodied spear fighter | `goatman1` pale tint, or new art |
| 2 | `!2` Dark Fey (17) | slender horned reddish staff figure | Median's art: a small green-haired fey woman | `succubus1` green tint; the table names `councilmember1`, which it does not look like: check |
| 3 | `&b` Deathwing (7) | dark brown vulture | Median's art is bone white | `batdemon1` (pale, as for the gargoyle) |
| 4 | `0n` Onyx Knight (10, Act 1 Catacombs) | thin brown sand raider | a heavy black knight | `doomknight1` dark tint |
| 5 | `2(` Fungus (8, from level 10) | teal furry `thornhulk` | a mushroom biped | smaller scale, or new art |
| 6 | `(l` Magma Demon (18) | plain brown `deathmauler` | no lava colour | a lava tint (check the classic colours) |
| 7 | `08` Fell Fiend (11) | putrid defiler | legacy: orange-red crawler | hand colour |
| 8 | `5$` Porkchop (7) | siege beast with its tower | the tower | `overseer1` |
| 9 | `g7` Pest (8) | brown yeti `brute2` | not checked against the art | look again |
| 10 | `b#` Crystal (5, `cantor1`) | not seen in the HD shots | maybe drawn invisible | check |

Bosses `#m` Belial, `#q` Enforcer, `$f` Rathma are the known FAILs of section 12. Not judged: `runepriest1`, `treeppl1`
(hidden in the shots). Shots and sheets: `mxl2012-runs/itemart/monsters/` (`mon_sheet_1-4.png` legacy+HD, `mon_hd_1-4.png`,
`mon_hd_near.png`; game art, outside git).
