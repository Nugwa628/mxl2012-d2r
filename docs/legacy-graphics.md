# Legacy graphics (G / Alt+G): Median XL 2012's own classic art in D2R

Lane `legacy`, 2026-10-28. Tool: `tools/legacy_art.py` (build step after `ui_layouts.py`), tests `tools/tests/test_legacy_art.py`.
First game check: lane qa, 2026-10-28 (section 5). Before that nothing here had been seen in the game; section 4 was the checklist.

## 1. What D2R's legacy mode loads

D2R 3.3 keeps the whole Diablo II 1.14 renderer. The graphics toggle (G / Alt+G) switches the in-game drawing to it; the
front end, the menus and the HUD frame stay D2R's. It reads **the original formats** from `data/global/...`, and a file in
the mod's folder (`mods/mxl2012/mxl2012.mpq/data/global/...`) is looked up before D2R's own CASC copy:

| Kind | Path below `data/global/` (lower case) | Format | Median v005 vs D2R |
|---|---|---|---|
| Inventory pictures | `items/<invfile>.dc6` | DC6 | same format, 1.13c art; 105 Median-only names + files D2R has too that differ |
| Missiles | `missiles/<name>.dcc` | DCC v6 | same; 145 files |
| Overlays | `overlays/common/*.dcc` | DCC v6 | same; 63 files |
| Monsters / NPCs | `monsters/<tok>/cof/<tok><mode><wclass>.cof`, `monsters/<tok>/<part>/<tok><part><variant><mode><wclass>.dcc` | COF + DCC | same; 1582 files (see 2.3) |
| Inventory + cube panel | `ui/panel/invchar6.dc6`, `ui/panel/supertransmogrifier.dc6` | DC6, 4-tile sets of 256x256, 64x256, 256x176, 64x176 | same structure as D2R's; D2R's classic layouts name exactly these two |
| Skill icons | `ui/spells/<xx>skillicon.dc6`, `ui/spells/skillicon.dc6` | DC6 sheet | same sheet structure; 8 files (the shared `skillicon.dc6` is `tools/shared_icons.py`'s paired one, docs/hd-icons.md) |
| Skill trees | `ui/spells/skltree_<xx>_back.dc6` | DC6 | same tile structure; 7 files |
| Tiles | `tiles/**.dt1`, `.ds1` | DT1 / DS1 | owned by `tools/maps_hd.py build` (DS1 with renumbered monster ids), not this tool |
| Animation data | `animdata.d2` | | owned by `tools/animdata_merge.py` |

Facts checked on the real files (Median v005 mpq, D2R 93847 filelist and extraction):

- **Case.** D2R's file list is lower case; Median's MPQ names are mixed case (`Global\Monsters\...`). The tool writes lower-case
  paths and `/`. Monster tokens with odd characters (`!7`, `x+`, `8@`, `&6`) are legal file names and stay as they are.
- **COF.** 28-byte header (layers, frames per direction, directions, 25 bytes), 9-byte layers (composite at +0, weapon class at
  +5), then `frames` keyframe bytes and `frames x dirs x layers` priority bytes. 750 of 753 Median COFs parse exactly; the
  other three (`!7s1hth`, `!7schth`, `x+dthth`) have a few extra/missing bytes. Whether D2R accepts them is not known; they are in the check list (step 5).
- **DCC.** 1046 of 1046 Median DCCs have a valid header (0x74, version 6). No conversion.
- **DC6.** Same container. One thing differs: D2R's UI palette makes indices 225-254 hot pink (D2R's own
  737 item DC6 and Median's two panel files never use them). **41 shipped DC6 do** (34 item pictures and 7 of 8 skill icon sheets, 6-20
  pixels each). The tool rewrites those pixels in place: each takes the units-palette index (1-224) nearest to the mean colour of its
  opaque non-hazard neighbours (the HD pictures' fill; lane hdpolish: the plain nearest colour was near-black, as D2R's units
  palette has 225-254 black), the plain nearest colour only where no neighbour has a colour; the file size and the
  run-length structure stay the same. On extract-mpq: 41 files, 602 pixels, all by neighbour fill.
- **Not read from the mod by D2R's layouts**, so not shipped: `ui/panel/tradestash.dc6` (D2R's classic stash is
  `PANEL\expandedstash` with its own tab bar, shared-stash arrows and gold bar), `local/ui/<lang>/act*` pictures,
  `ui/frontend`, `bigmenu`, `charselect` (D2R draws its own front end), the `.d2` COF caches (`cmncof_a*`, `chars_cof`: D2R reads
  the loose COFs; Median's caches would shadow them with Median-only entries).
- **Control panel**: Median's MPQ has no `ctrlpnl7` / `800ctrlpnl7` / `level` / `levelsocket` art, so the classic HUD and its
  level-up + buttons are D2R's own (`hudpanel.json`, 1.13's places; bugs.md #488 / #489).
- **Conflicts with D2R's legacy UI files**: the two panels and the 8 skill sheets / 7 trees above replace D2R's classic ones, as
  the mod's files should. The classic layouts still say where things go: `tools/ui_layouts.py` moves the inventory grid to
  Median's 10x6 and the cube to 10x8 (docs/hd-ui.md). D2R's own classic stash, trade, vendor and hireling panels stay D2R's
  (Median's equal them in grid size); the classic stash layout stays D2R's (section 9: the RotW pages, built but kept out of the mod).

## 2. What the tool does

`py -3 -I tools/legacy_art.py [build|plan|check] [--median DIR] [--d2r DIR] [--out DIR] [--strict]`; `build` is what
`tools/build.py` runs. It never writes into git: output goes to `work/mod/data/global/...` (gitignored; it goes into the asset pack
/ release from there) plus `work/mod/legacy_art.md` and `.json`.

### 2.1 Selection (1912 files, 137 MB; 429 Median files are not this tool's)

Per file: **new** (no D2R file at that path) is copied; **same as D2R** is skipped; **differs from D2R** is copied (Median wins),
except monster tokens, see 2.2. Everything else is listed in `legacy_art.md` with the tool that owns it (tiles, animdata, strings, tables,
sounds) or why nobody ships it.

### 2.2 Monster tokens D2R has too (fm im iw oy; e9 was one until section 6)

Median's monsters share two-character tokens with D2R. Their COF frame counts have to agree with the merged `animdata.d2`
(`animdata_merge.py` keeps D2R's record when a shared name has another frame count), or the animation runs out of its data. So:

| Token | Differing files | Decision |
|---|---:|---|
| `fm`, `iw` (and `im`, `oy`, same file) | 1, 8 | Median's: the frame counts agree with animdata |
| `e9` | 7 | Median's `E9NUHTH` has 13 frames and `E9S2HTH` 14, D2R's animdata records say 2, so D2R's files had to stay and Slayer / Slayer 2 drew D2R's trap. **Now split**: the two Slayer rows have the own token `KS`, Median's e9 files are shipped as `ks/..` and `e9` stays D2R's alone (section 6) |

### 2.3 Checks (warnings, `--strict` makes them errors)

COF/DCC structure of everything shipped; shipped COFs whose frames differ from animdata (21: `!K..`, `8@..`, `&6..`, `!Z..` rows
that animdata_merge left on D2R's record, step 5); paths over 150 characters; DC6 still on indices 225-254 when no palette was found;
and the **completeness check**: every Median `monstats` row against its `monstats2` row (COF per mode DT NU WL GH A1 A2 BL SC S1-S4 DD, a
DCC for every COF layer and every look in the `HDv`.. lists, `nil` = no part, part flags honoured). Result after section 6: 977 rows
complete, 187 incomplete, 13 without any art.

- **5 rows on Median's tokens are incomplete** (real gaps; 11 before section 6): `9x` (Karcheus / Hefaetrus / Zerae priestess, regular
  Amazon: no `9xddbow.cof` / `9xdtbow.cof` in Median's files; `death_cofs.py` writes them after this check, bugs.md #34) and `iw`
  (Toraja PPL: weapon-class files `iwrhqqq..1hs`). `ji` (dead3, res_dead3), `8@` (hornedgods) and `!4` (the four couatlfather rows)
  are complete now, see section 6. `tools/gfx_placeholders.py` lets a Median-only monster borrow a D2R donor for the HD client.
- **182 rows on D2R's own tokens** (mostly vanilla monsters whose rows ask for a mode D2R has no file for) are D2R's problem too:
  they are listed in `legacy_art.md` and need no action.
- **13 rows have no classic art anywhere**: `chaoshorde1-4`, `bird2`, `act2child`, `fish`, six `haunt_*`. They are in the HD client only.

## 3. What cannot be done

See the rows in `docs/unported.md` (section "Legacy graphics"): the 5 incomplete rows (section 2.3), the 13
art-less rows, the stash picture, menus and act pictures, and the open question below.

**The big unknown** is whether D2RLoader serves *modded* legacy files from `mods/mxl2012/...` in legacy mode at all
(docs/graphics-inventory.md section 7, item 3). Classic UI from loose DC6 files in a mod folder is known to work
(docs/hd-ui.md, "a mechanism verified in game"), which is evidence for UI files only; monsters, missiles, items and tiles take
the same lookup but nobody has tried them for this mod.

## 4. Checks that need the game (for the game-check lane)

Setup: a character in a slot's `mods\mxl2012` install after `tools/build.py` and `tools/maps_hd.py build`; a character
with some Median uniques in the inventory. Press **Alt+G** (or G, whichever the build uses) to switch and read the log
for missing-file messages after each step. Screenshots go to `R\mxl2012-runs`, not to git.

1. **Town in legacy mode.** Alt+G in Act 1 town. Expect classic tiles with no
   black holes; NPCs animate. A black screen or D2R's own town means the tiles / DS1 are not served: check `tools/maps_hd.py` ran.
2. **Inventory (I).** Median's `invchar6` frame, 10x6 grid, weapon swap tabs at the right height (docs/hd-ui.md), item pictures
   are Median's classic ones with **no pink pixels** (open the bag with Median-only items: a uniques stack).
3. **Character sheet (C)** is Median's, **cube** (Horadric Cube open) is the 10x8 Median picture.
4. **Skill tree (T)** per class: Median's sockets and arrows; in classic mode the tab titles are only the labels of Median's art (D2R's
   title text is switched off in the classic layout, bugs.md #33; HD draws them from the `skill_tab_titles.json` strings), skill icons are Median's (the pink check again on the icon sheet).
5. **A Median monster.** Spawn or walk to one whose token Median owns and that has odd bytes: `!7`, `x+`, `8@`, `!K`,
   `!Z`, `&6`; look for stills / one-frame animations (21 COFs differ from animdata), invisible parts, and the 5 rows of
   section 2.3. Compare the `fm` / `iw` rows (Median's). Then a Slayer (own token `KS`, section 6): expect Median's art (not D2R's trap) and no crash, and a `hornedgods` (8@).
6. **A Median map.** Walk through at least one area with Median's own map (docs/maps-hd.md lists them) in legacy mode: floors, walls,
   objects draw (the tile lane's DT1/DS1); none of the monster ids in the area is wrong (renumbered DS1).
7. **Missiles / overlays.** Cast a Median-only skill and wear a Median effect item: the DCC draws in classic mode (same name as
   D2R's HD effect, which HD mode uses instead). Exit legacy mode again (Alt+G) and check HD mode is unchanged.
8. **Alt+G round trip.** In-game toggle both ways three times; no crash, UI panels stay where `ui_layouts.py` put them.
9. **Load order.** If anything above shows D2R's art where Median's file exists in `work/mod`, D2RLoader / CASC precedence is the
   cause: open the question, do not fix it by copying files elsewhere.

Findings go back as rows in `docs/unported.md` (state `verify` -> `approx` / `deviation` / `open`).

## 5. Results of the game check (lane qa, 2026-10-28, slot 3; captures in `mxl2012-runs/qa/`, table in docs/testing.md "Lane qa")

| Step | Result |
|---|---|
| 1 Town | PASS: classic Rogue Encampment, no black holes (`town_classic.png`) |
| 2 Inventory | PASS: Median's `invchar6` frame, 10 x 6 grid, I / II tabs, Median items without pink pixels (`inv_classic.png`, tooltips `sheet_tip_classic.png`) |
| 3 Character sheet, cube | PASS: Median's sheet, the 10 x 8 cube picture (`char_classic.png`, `cube_classic.png`); the stash is D2R's classic one (`stash_classic.png`) |
| 4 Skill tree | PASS with a cosmetic deviation (bugs.md #33): Median's sockets, arrows and icons for Barbarian, Sorceress, Necromancer; D2R's title text is drawn over the labels that are part of the art, so the words overlap. **Fixed** (lane monitems, coordinator decision): the classic layout draws no tab title for the seven classic classes, the art's labels carry them (`mxl2012-runs/monitems/sheet_fix33.png`); HD keeps its string titles. Seen again for all seven classes, three tabs each (lane uicheck, 2026-10-30: `uic_legacy_tablabels.png`, `uic_legacy_trees_sheet.png` in `mxl2012-runs/uicheck/checks-20261030-012114-s4/`) |
| 5 Median monsters | PASS for `quest_lucion` (!1), `giant1` ((s), `shardspawn`, `bronzeguardian1`, `sarandesh1` (!7), `psychorbM` (x+): Median's art draws. `hornedgods` (8@) never appeared (bugs.md #32, its row borrows Andariel's token), `slayer` (e9) spawned without a crash, its D2R look not judged. The other odd-COF tokens (`!K`, `!Z`, `&6`, `8@`) were not seen Lane unporteda: hornedgods lives beside enemies but its monprop `fade` hides it in both modes; nothing on the player path spawns it (bugs.md #41) |
| 6 Median map | PASS: level 60 (`desertpeak`) draws Median's retextured tiles, pillars, a rune circle; its Amazonite / jungle snake monsters are the right classes (`map_desertpeak_classic.png`) |
| 7 Missiles | PASS (they draw): `rockshock`, `bloodspeakerbolt`, `leapingjumper` in classic and in HD (`sheet_missiles_classic.png`) |
| 8 Round trip | PASS: 3 x HD -> classic -> HD, no crash, panels in place (`sheet_roundtrip.png`) |
| 9 Load order | PASS, and the open question of section 3 is answered: D2RLoader serves **modded legacy files** from `mods\mxl2012` in legacy mode (tiles, DS1, monsters, panels, items, missiles all showed Median's version) |

## 6. Own tokens: Median's art no longer shares or borrows a D2R token (lane tokens, 2026-10-28)

Owner decision (2026-10-28): every Median monster, missile, overlay or item whose art differs from D2R's gets its own token or file
name, so classic mode shows Median's art. `tools/own_tokens.py` (data: `tools/data/own_tokens.json`,
tests: `tools/tests/test_own_tokens.py`) does it for the monster tokens; `tools/build.py` runs `own_tokens.py tables` before
`gfx_placeholders.py`, and `gfx_placeholders.py`, `animdata_merge.py`, `legacy_art.py` and `hd_monsters.py` read the same plan.

**Survey** (`py -3 -I tools/own_tokens.py audit`, Median's MPQ against D2R 93847's file list and the built tables):

| What | Result |
|---|---|
| Missile CelFiles (145 Median files) | none of the file names exists in D2R: no collision |
| Overlay Filenames (63) | none exists in D2R: no collision |
| Item inventory pictures / flippy (106) | one name is in both and byte-identical (`same-as-d2r`): no collision |
| Vanilla missile / overlay names that now draw Median's art | 12 missiles remapped in `hd/missiles/missiles.json` (`missile_hd.py`), same names, the new art is in HD and classic by the same name; not a collision |
| Monster tokens shared with D2R: `fm` `im` `iw` `oy` `rt` | same token, the same creature, files extend D2R's set and the frame counts agree with animdata: left as they are (section 2.2) |
| Monster token shared with D2R: `e9` | **collision**, split below |
| Rows that borrowed a D2R Code for want of a COF (`gfx_placeholders.py`) | `8@` `!4` `ji` have Median art: completed below. the six `haunt_*` rows (AM DZ SO) have no Median art at all and now borrow under their own token HN (below, `borrow`); `cougar` (7$ -> PW) has no Median art at all (no folder in the MPQ) and is dropped (owner 2026-10-29: its row is switched off, docs/hd-monsters.md) |

**Split** (new token, the rows leave the shared one):

| Rows | Old token | New token | Why |
|---|---|---|---|
| `slayer`, `slayer2` (both banks) | `e9` | `KS` | Median's Slayer art lived on D2R's `e9` (Wake of Destruction / Inferno Sentry): `E9NUHTH` 13 frames and `E9S2HTH` 14, D2R's animdata says 2, so D2R's files stayed and the Slayer drew D2R's trap. Median's `e9` files are now `ks/cof/ksnuhth.cof`, `kss2hth.cof` and the DCCs `kstrlit{nu,s1,s2,dd,dt}hth.dcc`; D2R's `e9` files stay untouched for the two traps. The modes Median ships no COF for (A1, S1, DD, DT) take D2R's e9 COFs renamed (the frame counts equal Median's DCCs for S1 / DD / DT); only the attack (A1) DCC is the trap's (approximation). Animdata: `KSNUHTH` 13 frames, `KSS2HTH` 14 (Median's timing), `KSA1HTH` `KSDDHTH` `KSDTHTH` `KSS1HTH` copied from D2R's `E9..` records of the same frame count. |

`KS` is a token that has no folder in D2R's file list or in Median's files and no monstats Code (`make_plan` refuses one that has).
HD: the two Slayer rows keep the unit they had (`wakeofdestruction`, "same donor": there is no better D2R model for them); the mapping
file has a new class `split` (`hd_monster_tokens.json` `ks`, `e9` trimmed to its two traps), see docs/hd-monsters.md section 5.

**Complete** (the token stays, the files that were missing are made, so the row keeps its own Code and no longer borrows):

| Rows | Token | What was missing / done | Why |
|---|---|---|---|
| `hornedgods` | `8@` (was `AN`) | no DT COF: `8@dthth.cof` copied from DD with the DD DCC under the DT name (`8@trlitdthth.dcc`); the right-hand (`rh`) and `s8` layers have no DCC in any look: dropped from the 9 COFs (layer records and priority bytes) | Median ships no DT COF and no rh / S8 DCC for the Horned Gods; the row borrowed Andariel's token |
| `couatlfather1-3`, `couatlfather_elite` | `!4` (was `FA`) | no SC COF: `!4schth.cof` copied from A1 with the A1 DCC under the SC name | Median ships no SC COF; the rows borrowed the Fallen's token |
| `dead3`, `res_dead3` | `ji` (was `ZM`) | no S1 COF: `jis1hth.cof` copied from A1 (+ DCC); the heavy / medium looks have no DCC for several modes: copies of the lit look | Median ships no S1 / RN COF and only the lit look for the torso; the rows borrowed D2R's zombie |

The copies are listed per file in `work/mod/legacy_art.md` (section "Own monster tokens") and their animdata records in
`work/mod/animdata_report.md` (`8@DTHTH`, `!4SCHTH`, `JIS1HTH`, the `KS..` ones). Table side: the Code of the split rows is rewritten
in both banks (`own_tokens.py tables`); the completed tokens need no table change, `gfx_placeholders.py` now counts the COFs of the plan
as Median's and stops borrowing. Checked by `legacy_art.py` (the completeness check sees the own files): `slayer` `slayer2`
`hornedgods` `couatlfather*` `dead3` `res_dead3` are complete, the `e9` warning of section 2.2 is gone.

**Borrow** (lane fixes3; rows with no art anywhere get D2R art under a token of their own, so the modes their skills use can be filled):

| Rows | Token | Donor | What was done | Why |
|---|---|---|---|---|
| `haunt_vasily`, `haunt_esu`, `haunt_fiaclagear`, `haunt_amazon`, `haunt_sorceress`, `haunt_druid` | `HN` (was AM / DZ / SO, borrowed CR) | D2R's `cr_archer1` (CR, bow) | CR's bow COFs and the DCCs they name renamed (257 files with the fills), cr_archer1's monstats2 row plus the rows' own modes; A2 and SC copied from A1, BL from NU (COF, DCCs, animdata `HNA2BOW` `HNSCBOW` `HNBLBOW`); HD: `cr_archer1` itself | their MonBow casts in SC, a mode no CR COF has, and the classic stand-in (corruptrogue1, 1hs) and the HD one (cr_archer1 with Median's part slots) disagreed: asserts on every spawn (bugs.md #74) |

Checked in game (slot 2): the four SC rows draw as bow archers in HD and classic with 0 asserts; `haunt_vasily` / `haunt_amazon` still assert because their Sk1mode is `TH` (bugs.md #74). HD visuals are a placeholder for human review.

Rows still without art of their own are in `docs/unported.md` (section "Legacy graphics"). **Not done:** `haunt_*` (AM DZ SO) and
`cougar` (dropped by the owner 2026-10-29: row switched off); Slayer's attack (A1) is D2R's trap animation until someone draws one.

**Game check** (lane tokens, slot 2, 2026-10-28, 7 launches): no assert, no crash. Spawned `slayer`, `slayer2`, `wakeofdestruction`, `infernosentry` in classic and in HD. Classic shows Median's goat-like Slayer art; HD shows the trap unit `wakeofdestruction` (the HD donor, as designed). `couatlfather1` and `dead3` draw Median-style art in classic. `hornedgods` was not spawned (bug #32). The Slayer / Wake sentries die when spawned unowned (AI `AssassinSentry`), so they were seen with the AI set to `Idle` in the installed copy only (not in the build).

## 7. Colour shifts: what classic draws and how HD follows (lane tints, 2026-10-29)

Classic mode recolours art at draw time; HD has to be told. Two kinds matter for this mod:

- **Monster levels (`TransLvl`).** Legacy mode applies the token's `palshift.dat` (D2R's own legacy files; Median's MPQ ships
  none, so Median's own tokens draw one colour). HD follows with the unit's variant table: `tools/hd_translvl.py` fills the
  levels D2R left identity (docs/hd-monsters.md section 8).
- **Recoloured vanilla effects.** Median's recoloured DCCs (`blackfiresmall`, `newfiremissile`, ...) are shipped by this tool
  and draw in Median's colour in legacy mode; HD draws a gradient-tinted copy of the vanilla effect where it has a gradient
  (`tools/hd_recolour.py`, docs/hd-effects.md section 5a).

The side-by-side shots of both modes are made by check `tint_hd` (docs/testing.md "Lane tints").

## 8. Warlock in classic mode (lane wlklegacy, 2026-10-29; static only, not seen in game: no slot account owns RotW)

D2R refuses the graphics toggle in Reign of the Warlock games ("Only Available in Classic and Expansion games"), and the
Warlock exists only there. D2RLoader's `[d2rcore.player] always_enable_rotw_legacy_graphics_keybind = true` lifts the block.
The local D2RLoader (slot 3, read only) says only "Keep the Toggle Renderer keybind available while playing a RotW
character" in its default toml (`D2RLoader.exe` strings, `config/d2rloader.toml.orig`; `D2RCore.dll` has only the key names).
The author's warning "This will crash in Median / Vanilla RotW only!" is not in the local install. It fits D2R's own data:
the first gap below is in D2R's files, so vanilla RotW has it too.

**What a Warlock looks like in classic mode.** D2R's `chars/wk/` files are byte copies of the Necromancer's plus three block COFs
(`wkbl2hs`, `wkbl2ht`, `wkblstf`), so the Warlock looks like a Necromancer. Its skills' classic art is D2R's own classic stand-ins
(`overlays/warlock_*.dcc`, `missiles/grimward*.dcc`, ...). The tree back `skltree_w_back.dc6` is a byte copy of D2R's Necromancer
back, and the icon sheet `waskillicon.dc6` a copy of the Druid's (60 frames). The mod overrides none of these.

### 8.1 The checker

`py -3 -I tools/warlock_legacy_check.py [--all] [--notes] [--json FILE]` (tests: `tools/tests/test_warlock_legacy_check.py`)
lists every classic file the game can load for a Warlock in the built mod, where it is found (mod / base / MISSING) and any
index past the end of the file it points into. Sections:

- **character:** plrtype token `WK`; every `chars/ne/` file's `chars/wk/` twin; every Warlock COF checked against its layer DCCs
  and its record in the merged `animdata.d2`.
- **item graphics:** every weapon / helm / shield visual code in the tables, per weapon class.
- **skills:** the 30 `war` skills of the RotW bank and everything they reach: missiles with their sub, hit, client and explosion
  missiles; overlays; states; summoned monsters with their monstats2 modes and parts; the summons' own skills.
- **UI:** the served `skillstreepanel.json`'s per-class arrays at index 7; the icon sheet and tree back it names; every Warlock
  IconCel + 1 inside the sheet; SkillRow / SkillColumn inside the grid; `inventory.txt` Warlock / Warlock2.
- **starting kit:** inventory and flippy DC6; the dagger's hand graphics in every mode.

The rules come from D2R's classic (LoD) bank, whose rows draw in 1.14 classic:

- A monster mode without a COF in its base weapon class takes the HTH one (26 vanilla DT / DD rows, `goatman1` among them).
- SQ has no COF (482 vanilla rows set `mSQ`).
- KB draws the GH COF (bugs.md #3).
- A layer without a DCC for a look is not drawn (`necroskeleton`, `shadowmaster` and 60 more).
- Missile / overlay NumDirections or AnimLen beyond the DCC is only a note (17 vanilla rows have it: the imp and catapult
  missiles, Exploding Arrow).

The checker counts two things as crash candidates: a file that neither the mod nor D2R has, and **animdata frames above the
art's frames** (the animation's last frame index then runs past the COF / DCC).

### 8.2 Result (built mod, lane wlklegacy)

| | found | missing | out of range | notes |
|---|---:|---:|---:|---:|
| before the fixes (D2R's animdata records, D2R's layout) | 375 | 0 | 3 | 33 |
| after the fixes | 375 | 0 | 0 | 33 |

The notes include 6 layers that are not drawn, 24 item visual codes missing for the reference class too, and 1 file missing for
every class (the Clue Gem's flippy, below).

**Gaps fixed** (bugs.md #498):

| Gap | Cause | Fix |
|---|---|---|
| `WKA1HTH`, `WKA2HTH`: animdata 16 frames, but the classic COFs `wka1hth` / `wka2hth` and their 36 DCCs have 15 | D2R 93847's own data: its Warlock animdata records were made for the HD model, and the classic art is the Necromancer's (`NEA1HTH` 15). An unarmed Warlock attack in classic would ask for frame 15 of a 15-frame DCC. The mod's merge keeps D2R's records (`animdata_merge.py`), so the mod had the gap too | `tools/animdata_merge.py` `CLASSIC_CAPS` caps both records at 15 frames. Speed 256 and the action frames (9, 7) stay, so the hit lands on the same frame. **Side effect:** the unarmed attack is one frame shorter in HD too (animdata is the game's timing in both modes) |
| `skillstreepanel.json` `cancelPositionCode` has 7 entries (Amazon .. Assassin) | D2R's own classic layout. The field is an `int[8]` (exe descriptor at `0x29ea8d0`: element 4 bytes, count 8, panel offset `0x86c`), so the Warlock's slot keeps its default and the close button of its classic tree has no defined position | `tools/ui_layouts.py` `warlock_cancel_position` appends the Necromancer's code (131), since the Warlock's tree back is the Necromancer's picture |

**Notes left (explained, not crash candidates):**

- 12 Warlock A1 / A2 COFs (1hs 1ht 2hs 2ht bow stf xbw) have more frames than D2R's animdata (for example 19 vs 16). The
  classic swing ends a few frames early. Visual only.
- Missiles:
  - Sigil Lethargy / Rancor / Death draw D2R's one-frame `grimward*.dcc` with AnimLen 2.
  - **Flame Wave** (`flamewaveunveiling`, `flamewavefire`) uses D2R's `null.dcc` (2 frames, 1 direction). In classic, Flame Wave
    shows only its `groundfirebig` flames, as in vanilla RotW.
  - Miasma Chains flies on `lightningbolt.dcc` (1 direction; the table says 32).
  - The Miasma Bolt cloud uses `poisonsparks.dcc` (31 frames, AnimLen 37).
- Summon Goatman: the `wargoatman` row's S1 COF (D2R's new `gms12hs.cof`) has an `rh` layer with no DCC in D2R for any of its
  6 weapons. The goatman's weapon is not drawn during S1.
- 24 item visual codes have no Warlock hand / helm / shield DCC. The Necromancer has none for them either, so that layer is not
  drawn, as for the classic classes.
- Every class's starting kit has the Clue Gem (`01-`), whose flippy `flpdss.dc6` is missing from Median's own files. Not
  Warlock-specific; dropping the gem in classic is untested for every class.

### 8.3 What the static check cannot see

- **Skill sequences.** Bind Demon (seqnum 6), Miasma Chains (12), Cleave (24) and Mirrored Blades (25) play sequences, and 24 /
  25 are new in D2R. The sequence tables are in the exe; their frame indices into the Warlock's A1 / A2 / SC modes were not
  read. A sequence frame past the classic COF would be the same kind of overrun as the A1 HTH one.
- Exe code paths keyed on class 7 in the 1.14 renderer (the classic panels other than the skill tree layout, the 1.14 player
  composite code), and missile functions that name other missiles through their parameters (`CltParam`) rather than columns.
- Sounds: a missing sound plays nothing in 1.14; not checked.

**Verdict.** With the two fixes, nothing in the mod's data or D2R's classic files shows a missing file or an index past the art
for a Warlock. Expect the Necromancer look, a Flame Wave without its wave and shortened swings. The remaining risk is in the exe
(the sequences above). The vanilla A1 / A2 HTH overrun is the most likely meaning of the loader author's "crash in Vanilla RotW".

### 8.4 Test on a RotW account (owner / user; the slots cannot)

1. Install a build of this branch into `mods\mxl2012`. Set `always_enable_rotw_legacy_graphics_keybind = true` in that install's
   `d2rloader\config\d2rloader.toml` by hand (the tools never edit the loader toml).
2. Make a new Warlock in a RotW game. In HD first: walk, open I / C / T, cast nothing. Then press **G**: expect a
   Necromancer-looking Warlock.
3. Classic UI: I (10 x 6 grid), C, and T: the tabs Demon / Eldritch / Chaos, and the close button on all three tabs (the #498
   entry). Also the skill select popup (the left / right skill buttons).
4. **Unarmed attack:** take the dagger off and attack a monster several times (A1 / A2 HTH, the fixed records). Then attack
   with the dagger.
5. Raise the level (`cheat level 30`, docs/dev-console.md) and cast every skill once in classic:
   - first the sequences: Cleave and Mirrored Blades (24 / 25), Bind Demon on a demon (6), Miasma Chains (12);
   - Summon Goatman (let it fight until it uses its skills), Summon Tainted, Summon Defiler;
   - the three Sigils, Flame Wave (expect only ground flames), Miasma Bolt, Ring of Fire, Apocalypse, Abyss, Eldritch Blast;
   - Echoing Strike, Blade Warp, Levitate, Psychic Ward, the three Hexes, Death Mark, Engorge, Consume, Blood Boil.
6. Toggle G three times: once during a cast, once with the pets out. Leave the game and come back in classic.
7. On a crash, keep the file in `d2rloader\crashes\`, the log, and the last skill / action. Findings go to bugs.md #498.

## 9. The RotW stash pages in classic mode (lane rotwstash, 2026-10-30; built, not in the mod by default; lane rotwgate, 2026-10-31: the plugin wires the pages in classic, no crash without RotW, 9.6)

Owner request (2026-10-30): "make the new RotW stash pages work in legacy 'down renders'": the Gems, Materials and Runes tabs of
Reign of the Warlock's stash (bug #510) get a classic version, its art down-rendered from D2R's own HD art. No new 3D models.

### 9.1 What D2R 93847 does in classic mode today

Read from D2R's files (extraction 93847). Lane rotwgate (9.6) later read the panel code in the dumped D2R.exe: the stash
init `0x23b1b0` does name the widgets (the packed file hides that), and it wires the pages only in HD.

| | HD (`bankexpansionlayouthd.json`) | Classic (`bankexpansionlayout.json`) |
|---|---|---|
| Tabs | 5: Personal, Shared, Gems, Materials, Runes (`MKB_Tabs_195_TGA`, 195 x 72) | 2: Personal, Shared (`PANEL\buyselltabs`, 79 x 24) |
| `backgroundFile` (one per tab) | 5: the personal and shared pages and `PANEL_AdditionalStash_{Gems,Consumables,Runes}` | 2: `PANEL\expandedstash`, `PANEL\additionalstash` (the shared tab's picture: same panel with the page arrows' boxes) |
| Personal / Shared widgets | inside `basicstash_container` (the panel hides it on the RotW pages) | top level |
| RotW pages | `advancedstash_gems` (35 slots), `_materials` (23), `_runes` (33): one `AdvancedStashSlotWidget` per item code, 91 codes; the recesses are painted into the page pictures | **none** |
| Stash cube | `advancedstash_horadriccube`: a 3 x 4 grid, Transmute, a cover picture, a withdraw button | **none** |
| Classic art | - | **none** for the pages: D2R's classic panel folder has only `expandedstash`, `additionalstash`, `tradestash` |

So in a RotW game with the graphics toggle lifted (`always_enable_rotw_legacy_graphics_keybind`) the classic stash has no way to
the three pages: two tabs, no slots, no pictures. What D2R does when the stash is switched to classic while one of the RotW pages
is open (tab 2-4 of a 2-entry background list, widgets the panel looks for and does not find) cannot be told from the files:
an empty page, the personal page, or a crash. The game slots cannot try it (no RotW).

### 9.2 What the step builds (`tools/rotw_stash_legacy.py build`, a build step after `legacy_art.py`)

All generated from the D2R extraction at build time; nothing of Blizzard's is in git. **`tools/build.py` writes the files to
`work/rotw_stash_legacy/data`, not into the mod**; they go into `work/mod/data` (and so into the package) only with
`MXL2012_ROTW_LEGACY=1`, for the owner test on a RotW account (docs/testing.md "Lane rotwstash"). Why: 9.4.

- **`data/global/ui/layouts/bankexpansionlayout.json`** (classic): D2R's classic layout rebuilt in the HD layout's structure.
  Five tabs (`PANEL\rotwstash_tabs`, 63 x 24 each, 1 apart: the five fill the 320-pixel panel on D2R's classic tab band); five
  backgrounds (D2R's two, then the three new pages); `gold_max`, `gold_amount`, `gold_withdraw`, `grid` (10 x 10) and the shared
  stash arrows inside `basicstash_container` as in HD, written out in full with D2R's classic base fields (HD does the same);
  the three pages with **the same item codes in the same order as HD**, each slot centred where the HD slot lands at the panel
  scale (x / 3.631, y / 3.488) and sized to classic cells (28 x 28, the 1 x 2 Materials slots 28 x 57); the stash cube: a 3 x 4
  grid of 29-pixel cells, D2R's classic `PANEL\miniconvert` as Transmute, the cover and the withdraw button. Every text is
  written out (bugs #30 / #33): "Personal", "Shared", "Gems", "Materials", "Runes", "Page %u / %u", the tooltips.
- **`data/global/ui/panel/rotwstash_{gems,materials,runes}.dc6`**: the HD page pictures (1162 x 1507) down-rendered to the classic
  320 x 432 panel (4 tiles like every classic panel): Lanczos on premultiplied alpha and a light unsharp mask, the top 29 rows
  replaced by the black tab band of D2R's classic `expandedstash.dc6` (so the tab bar looks the same on all five tabs), every
  slot recess and the cube window re-rendered at the classic cell size under the widget's rect (so a 28-pixel item picture sits
  exactly in its recess; the plain panel scale would make them 27 x 28 and the cube cells drift 2 pixels per cell), then
  quantised to D2R's units palette with Floyd-Steinberg (indices 1-224 only: 225-254 draw hot pink in D2R's UI, section 1).
- **`rotwstash_tabs.dc6`** (HD `MKB_Tabs_195_TGA`, inactive and active, 63 x 24), **`rotwstash_cubecover.dc6`** (HD
  `HoradricCubeCover`, 87 x 116 = the classic cube grid), **`rotwstash_button.dc6`** (HD `FrontEnd_ButtonSmall`, 4 frames,
  101 x 27), **`rotwstash_notify.dc6`** (HD `StashNotification`, 54 x 18, the "an item went to this tab" mark).

The Personal and Shared pages keep D2R's classic pictures; only their tab bar changes (five narrower tabs from the HD art instead
of D2R's two `buyselltabs`). In HD a game without RotW shows only the first two tabs; in classic it shows all five (9.4).

### 9.3 The check (`tools/rotw_stash_legacy.py check`; also at the end of `build`, report `work/rotw_stash_legacy/rotw_stash_legacy.md`)

The layout parses; the codes and their order per page equal HD's; every slot is inside the panel below the tab band and
overlaps no other slot; every `PANEL\...` file the layout names exists in the mod or in D2R, with the frame sizes the layout
needs (4 panel tiles, 2 tabs of 63 x 24, the cover of the cube grid's size); each code's item row and classic picture (it must
fit its slot); no `@key` left. Unit tests: `tools/tests/test_rotw_stash_legacy.py` (synthetic files).

Result on the build of lane/rotwstash: no problem; 91 slots (gems 35, materials 23, runes 33); 71 codes are Median items whose
classic pictures (28 x 28) fit their slots, 20 have no item in Median's tables (the keys, organs, essences, `ua*` / `xa*`), the
same empty slots as in HD.

### 9.4 In game: a classic slot widget crashes D2R without RotW (slot 3, 2026-10-30)

Slot 3 (an account without RotW), character in town, stash opened in HD, then G (classic). The mod's classic layout was swapped
for parts of it to find what crashes. Run notes and pictures: the lane's run folder.

| Classic layout in the mod | G with the stash open |
|---|---|
| none (D2R's own) | fine |
| the step's layout (Personal / Shared in `basicstash_container`) | **crash**, `D2R.exe+0x23E6A5` (also without the RotW pages) |
| five tabs, new tab art, the notify mark, Personal / Shared at top level, no RotW pages | fine |
| + the three pages with their slots (without the cube; one slot per page; the pages `"visible": false`; `countText` / `textBox` children in each slot) | **crash**, `D2R.exe+0x154AF2`, a read at 0x440 through a null pointer |
| + the three pages with no slots, + the stash cube | fine, but the cube cover and the withdraw button are drawn on the Personal page, and all five tabs show |

So in classic mode D2R builds and updates an `AdvancedStashSlotWidget` even on a hidden page, and on a game without RotW it reads
through a null pointer (most likely the RotW stash data that the game does not have; in HD the panel keeps the pages out of
use). Whether it works on a RotW account cannot be tried here (no slot account owns RotW). That is why the step's files stay out
of the mod by default: with them every player without RotW would crash on G with the stash open. With
`MXL2012_ROTW_LEGACY=1` the owner can try it on a RotW account; if it works there, the layout can only ship once it can be
limited to RotW games (a classic layout cannot test for that).

The layout also needs the `basicstash_container` crash solved first: the step writes Personal / Shared inside it, as in HD,
and that crashes in classic even without the RotW pages. Next step for the layout if the owner's test is wanted: Personal /
Shared at top level (tested fine above), and accept that they then draw on the RotW pages too.

Also seen: "MATERIALS" does not fit a 63-pixel tab in D2R's classic font (it is cut to "MATERIAL:").

Lane rotwgate found the cause of both crashes in D2R's code and made the plugin wire the pages in classic too (9.6). With it the
step's full layout (`basicstash_container`, slots, cube) no longer crashes without RotW.

### 9.5 Median's 10 x 8 cube in the stash cube window (bug #515, open)

D2R's stash cube window is 3 x 4 (D2R's cube). Median's Horadric Cube is 10 x 8 (`inventory.txt` "Transmogrify Box", the mod's
own cube panel; docs/hd-ui.md). Both layouts (D2R's HD one, the step's classic one) draw the window with 3 x 4 cells. If the
panel shows the cube's contents through this window, items outside the first 3 x 4 cells of Median's cube are not shown there
(nothing is lost: the cube's own panel shows all 80 cells). A 10 x 8 window does not fit the pages (290 x 232 classic pixels
under the slots, 980 x 784 HD pixels). Not changed; to look at on a RotW account (docs/testing.md "Lane rotwstash").

### 9.6 Why it crashed, and the plugin part `rotwstash` (lane rotwgate, 2026-10-31; docs/plugin-plan.md section 29)

Owner (2026-10-31): "we will need to code it so they only work in rotw some how". Read in the dumped D2R.exe (`d2r_find.py`):

- D2R's stash panel init `0x23b1b0` (after the layout is read) calls `0x846210` (HD graphics: the panel manager's byte `+0xb9`)
  at `0x23b204`. Only on yes, and only when the layout has `basicstash_container`, it fills the panel's page table (`+0x278`:
  `basicstash_container` twice, `advancedstash_gems`, `_materials`, `_runes`; `+0x2a0`: `advancedstash_horadriccube`) and
  sets `+0x2a8` (the five pages are in use). The tab update `0x23e630` reads that table: with the step's layout in classic
  the table is empty and it calls through a null entry, `D2R.exe+0x23E6A5`. The pages nobody hid then draw their slots through
  the classic item picture `0x154ac0`, which reads `[item+0x78]` without a check, `D2R.exe+0x154AF2`. So **D2R never wires the
  RotW pages in classic, with or without RotW**: the crashes of 9.4 were not about the account.
- The RotW test itself is the panel's own: in HD, in a game without RotW, the same wired panel shows only Personal / Shared.
  The game type is the client game's (global `0x2a236e0`) byte `+0x5c`: 1 classic, 2 Lord of Destruction, 3 Reign of the
  Warlock (D2R's own test `0x8d3e0`; our slots read 2).
- A layout cannot test for RotW: it is picked by name, and the name is the panel's key. D2RLoader's
  `always_enable_rotw_legacy_graphics_keybind` only lets G work in a RotW game; it does not change the panel.

**The part** (`rotw_stash.cpp`, off word `rotwstash`): the call at `0x23b204` goes through the 14 int3 bytes at `0x2388a2` to the
plugin, which answers yes in HD (D2R's answer) and in classic as well, in every game. The panel then runs as in HD and D2R's
own RotW rule decides which tabs show: without RotW only Personal / Shared, with RotW all five (to be seen on a RotW account).
With D2R's own classic layout nothing changes (it has no `basicstash_container`; the init leaves right after the check). A
guard on `0x154ac0` skips an item picture without its `+0x78` record (not reached once the pages are wired; counted in
`mxl2012`). Dev builds only: `MXL_ROTWSTASH_TEST=rotw` wires in classic only in a RotW game, `=never` keeps D2R's rule.

**In game** (slot 1, no RotW, game type 2; docs/testing.md "Lane rotwgate"): with the step's full layout and the default part,
17 cycles with the stash open, 34 G presses (HD -> classic -> HD; stash opened fresh in classic, tabs clicked, empty clicks
where Gems / Materials / Runes would be): no crash, only Personal / Shared show, Shared's pages work. The control (`never`) crashes at `+0x23E6A5` on the
first G. With D2R's own classic layout: 5 more cycles, no crash, unchanged. 0 crash files.

**Shipped by default since 2026-10-31 (owner)**: `tools/build.py` puts the layout into the mod; `MXL2012_ROTW_LEGACY=0` keeps
it out. The text below is the state before that: a RotW account has not opened the pages in classic, and
without RotW the step's tab bar is a small step back from D2R's own: "Personal" is cut to "PERSON" on the 63-pixel tab (D2R's
own classic tabs are wider). Once the owner test passes, the layout can go into the mod by default; the part is already on.
