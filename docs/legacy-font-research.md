# Legacy font file-copy investigation

Lane `legfont`, D2R 3.3 build 93847, D2RLoader 1.3.1-beta, target 0.1.16.
The player reported clearer numbers, a less blurry T and clearer red entrance text after copying unspecified
"D2R font files". The player's screenshots now identify 22 classic files; their exact bytes and source have not been supplied.

## Font paths

The classic renderer loads `data/local/font/<lang>/<name>.dc6` and the matching `.tbl` (glyph metrics).
For English `<lang>` is `latin`. D2R's own classic assets use the old format; they are not the HD TrueType fonts.
The loader and font-id table are described, with dump addresses, in
[the earlier renderer research](legacy-hd-text-research.md#1-how-d2r-picks-the-font).
That investigation is independent of this file-copy experiment; its crashing HD-path probe was not repeated.

The Latin directory in D2R's CASC filelist contains these DC6/TBL pairs:
`font6`, `font8`, `font16`, `font24`, `font30`, `font42`, `fontexocet8`, `fontexocet10`,
`fontformal10`, `fontformal11`, `fontformal12`, `fontingamechat`, `fontridiculous`, `reallythelastsucker`.
There are also `default.map`, `default.tbl`, `fonter.tbl`, `readme.txt` and six `.txt` files
(`font16`, `font24`, `font30`, `font42`, `reallythelastsucker` plus the readme).
The filelist also has Chinese (`chi`), Korean (`kor`), `latin2` and locale-specific development assets.
The test is English only; copying Latin assets says nothing about the other languages.

`data/hd/ui/fonts/` contains:

- `arfangxinshuh7c95b5_eb_t.ttf`
- `blizzardglobal-v5_81.ttf`
- `blizzardglobaltcunicode.ttf`
- `bljap_v8_3.ttf`
- `exocetblizzardot-medium.otf`
- `formal436bt.ttf`
- `ik4ll3.ttf`
- `irisl.ttf`
- `kodia.ttf`
- `philosopher-bolditalic.ttf`
- `tbgdb_0pp.ttf`

These are HD font faces. The official [D2RLoader changelog](https://d2rloader.net/changelog.html)
(1.0.0 beta, Gameplay and mod support) says fonts are softmoddable and gives this directory.
It does not promise HD fonts in classic graphics. The installed `d2rloader/config/d2rloader.toml` describes
its `fonts` log switch as TrueType/OpenType font loading. No loader source or changelog was present in this
lane's third_party or the installed loader directory; the official changelog supplies the release claim.

## Override audit

The reference build's `work/mod`, installed slot-2 `mods/mxl2012/mxl2012.mpq/data`, Median's extracted named
files, and the complete 0.1.15 package manifest contain no files in either font directory.
The lane was fresh (no work/mod). The shared baseline extraction does not include fonts; absence there is
an extraction omission, not absence from D2R. The candidate files were read directly from slot 2's CASC,
without changing the shared baseline.

Median's original v005 `patch_d2.mpq` was also probed directly by all 160 common font paths in the D2R filelist with StormLib
`SFileHasFile`, rather than relying on its incomplete listfile: zero hits. There is no evidence of Median-specific
glyphs in these files, nor an older Median font replacing D2R's font. The install and packaging paths copy
`work/mod/data`; they do not install a separate font set.

Evidence outside git: `mxl2012-runs/legfont/audit.json` (paths, sizes and SHA256 of all candidates),
`median-mpq-font-probe.json` (original archive probe), `candidate/` (48 files: 37 Latin and 11 HD).
The after experiment copies all 48 to `mods/mxl2012/mxl2012.mpq/data/...`, their normal virtual paths,
then removes them after the game closes. This covers both plausible meanings of "D2R font files".

## In-game comparison

Results and paired captures are recorded in [testing](testing.md#lane-legfont-legacy-font-copy-investigation).
No renderer hooks or HD-path changes are part of this lane.

## Release decision and unresolved report

Do not ship copies of D2R fonts, and do not remove or replace any Median glyphs. The mod already falls back to
D2R's own classic font assets. Copying those same assets cannot restore a missing newer font in the audited build.
The 4:3 life and mana captures have identical bright glyph masks before and after the copy (0 changed pixels;
`43-pixels.json`). Both still show the same pixel-shaped, scaled classic letters and digits. This experiment does
not establish the cause of the player's claimed improvement: their files may be a custom font rather than the
unmodified game assets, or their settings/install may differ. Obtain the exact file paths and hashes, locale,
loader version, graphics settings and matched screenshots before recommending a replacement.

The initial investigation was research-only. The crash follow-up below adds the safe set; the [in-game setting](#in-game-setting-lane-fonttoggle) makes it a player choice, off by default.
A custom DC6 replacement needs its matching metrics and a separate
review of non-ASCII glyph coverage. A TTF copy does not select the classic renderer's font.

## Player screenshots and a local custom-font lead

`player_latin.png` and `player_font.png` show `data/local/font/latin`, created by the player, with 11 DC6/TBL pairs:
`font6`, `font8`, `font16`, `font30`, `fontexocet8`, `fontformal8`, `fontformal10`, `fontformal11`, `fontformal12`,
`fontingamechat`, `ReallyTheLastSucker`. All displayed dates are 2023-02-20. Every displayed DC6 size differs from
stock D2R 3.3 (or the name is absent: `fontformal8`); the TBLs display 4 KB, consistent with 3596 bytes but not proof
of equal contents. For example font30 is 41 KB in the screenshot versus 84155 bytes stock; ReallyTheLastSucker is
67 KB versus 23069 bytes stock. These are not plain copies of this build's stock fonts.

The already-downloaded D2SE/D2GL repack contains `data/local/font.zip`: all 22 names, 10/11 matching displayed DC6
sizes, and the same unusual extra formal8 and large ReallyTheLastSucker. Its font16 is 26461 bytes (26 KB), versus
27 KB in the screenshot; three DC6 dates are Feb 21 instead of Feb 20. This is a probable related font modification,
not a verified identification. The repack's loose DC6s have the same sizes; their metrics are under `backup/`.
They are [repack additions](source-inventory.md), absent from Median v005's original MPQ and excluded from this port.
No internet download was used to obtain this lead.

Evidence: `mxl2012-runs/legfont/PLAYER-FONT-FINDINGS.md` and `player22-stock-repack.json` record exact stock/repack
sizes and SHA256 of the 20 stock counterparts (formal8's pair is explicitly absent), plus all 22 local candidate hashes.
`repack-fonts.json` records archive dates. The project's native Diablo II 1.14d d2data/d2exp fonts largely match stock
D2R byte-for-byte, including font6/8/16/30; they do not match the player's size pattern (`native-114d-fonts.json`).
No older D2R font extraction was identified in the project's existing named font assets. The installed loader's bundled
MPQ has none of the 22 virtual paths (`loader-mpq-font-probe.json`); no alternate case/folder override was found in
the mod tree. The test does not instrument individual engine file reads, but the stock-copy controls and asset audit
provide no evidence of a hidden older-font fallback.

The harness accepts `MXL_FONT_SOURCE` pointing at a candidate tree under the lane evidence directory containing
`data/local/font/latin/`. It records exact copied sizes/hashes, copies only font-related extensions, retains the slot
lock through restoration, and removes the experiment files after stopping the game. Exact player-file testing remains
pending. Local repack-candidate screenshots must not be presented as the player's exact fonts.


The local repack candidate was drawn in 4:3: unlike stock-copy controls, it visibly changes the classic typeface
and gives thinner digits and a clearer red title (`43_repack_*_pair.png`). This supports a custom font replacement
as the explanation, without identifying the player's exact variant. Exact-file reproduction remains blocked on
those inputs; the ready harness and hashes are in the evidence directory. This was the initial research result;
the crash follow-up below adds a conservative optional set from the audited local repack.

## Crash follow-up: repack metrics and a conservative optional set

The player's later crash report identifies `EXCEPTION_INT_DIVIDE_BY_ZERO` at D2R 93847 RVA `0x90DD16`,
with `latin\\fontformal11.tbl` on the stack. The local repack's matching file has **zero at byte offset `0x0A`**:
the nominal line height in its 12-byte `Woo!` header. Stock D2R sets it to **11**. The header layout is
signature (4 bytes), version (u32, 1), count (u16, 256), line height (u8), and another byte.
All 256 glyph records follow, each 14 bytes. This is a font-metrics table, unrelated to localized string TBLs.

D2R's `0x90DCD6` reads that header byte; the layout function scales it by the selected font size and text scale,
then `0x90DD16` executes `idiv ecx` to calculate the number of lines fitting the rectangle. A zero header height
makes the divisor zero regardless of which glyph is being measured. It is not a bad letter or a DC6 decoding fault.
All 11 repack tables are 3596 bytes, version 1, 256 records; formal11 alone has zero nominal line height.
Their header heights are font6=8, font8=10, font16=12, font30=18, exocet8=10, formal8=10, formal10=10,
formal11=0, formal12=12, chat=12, ReallyTheLastSucker=12. None of their glyph advances, glyph heights,
or DC6 frame widths/heights is zero. All 11 DC6s contain 256 frames. Every formal11 glyph record differs
from stock; replacing only its picture does not restore matching stock metrics.

The fault reproduces by opening the legacy quest log with the full repack set. Changing only offset `0x0A`
from 0 to 11 permits the same panel to open. This proves the reported divisor's cause but does not establish
that every custom dialogue font fits every text box. Classic layouts explicitly use `11ptF` in
`questlogpaneloriginal.json`, `questlogspeechpanel.json`, and `scrollspeechpanel.json`.

The owner subsequently relayed a player workaround replacing dialogue and chat pictures with stock assets.
The build option uses **matching pairs**, with both DC6 and TBL from the same source:

| Font pairs | Optional build output |
|---|---|
| font6, font8, font16, font30, fontexocet8, fontformal8, reallythelastsucker | 14 unchanged repack files in `data/local/font/latin/` |
| fontformal10, fontformal11, fontformal12, fontingamechat | Neither file overridden; D2R supplies its own matching stock pair |

The source is the **2023 D2SE/D2GL repack of Median XL 2012**, its `data\\local.zip` (also `data/local/font.zip`),
already present locally. These fonts are not original Median XL 2012 v005 assets and are not stock D2R fonts.
The owner considers the fonts covered by the old game's existing credits; no additional font-author credit is assigned.
`tools/data/legacy-font-repack.json` pins the size and SHA256 of all 22 archive members, including excluded pairs.
No binary font files are added to git or downloaded by the build.

`tools/build.py` runs `tools/legacy_fonts.py` after the classic art and layouts. Lane legfont made this an opt-in
build step writing D2R's own names; lane fonttoggle replaced that with the in-game setting below. The build now always
stages the set in `data/local/font/latin/clear/` from `MXL2012_LEGACY_FONT_ARCHIVE` (default: the repack's
`local.zip` in `<MXL2012_RUNS>/extract-merged` under data); `MXL2012_LEGACY_FONTS=0` leaves it out. Files of the earlier
option are removed by the same manifest; edited or unrelated fonts are not silently replaced or removed. No HD fonts change.

Both the font step and release packager reject zero line-height fields, malformed tables, invalid frame references,
missing pairs and empty DC6 frames. A regression test supplies the exact zero-header shape that crashes D2R
and checks that a hand-copied bad pair is rejected before replacing an existing package staging directory.
The validator deliberately allows zero glyph advances, which occur in stock exocet8 and are not this divisor.
Game coverage and evidence are recorded in [testing](testing.md#lane-legfont-repack-crash-and-stock-dialogue-fallback).

## In-game setting (lane fonttoggle)

Owner request 2026-11-07: an on/off option in game instead of the build option. Plugin part `clearfonts`
([plugin plan section 36](plugin-plan.md#36-clear-legacy-fonts-setting-lane-fonttoggle-2026-11-07-owner-request),
addresses in [d2r-addresses](d2r-addresses.md#classic-font-loading-lane-fonttoggle-2026-11-07-pluginsrcclear_fontscpp)).

- **Shipped set:** font6, font8, font16, font30, fontexocet8, ReallyTheLastSucker (12 files, under `latin/clear/`).
  fontformal8 is dropped: D2R 93847 has no font id or path for it (its bytes equal fontexocet8's anyway).
  Formal10/11/12 and chat stay stock in both states.
- **When D2R loads fonts:** per font id at first use (SetFont `0x90e230`), not once at start; D2R itself frees idle fonts
  and reloads them later. So the setting applies at once: the part swaps the six names and frees those fonts' pictures the
  way D2R's idle unload does; DC6 and TBL of one font always come from the same set, so sizes never mix within a font. Open
  panels show the new font on their next draw; a wrapped dialogue box keeps its stock font in both states.
- **Where the switch lives:** D2RLoader 1.3.1's in-game settings (General, Startup, Locale, Advanced and the Extensions list)
  have no page for a plugin's TOML (its string table has none), so the brief's "D2RLoader plugin settings" does not exist in
  this version. D2R's own options have no plugin API. The in-game switch is therefore the Controls action "Clear Legacy Fonts"
  (Options > Controls, category D2R-XL 2012, default Ctrl+F, rebindable), which flips the setting and saves it to
  `mxl2012-core.toml` `[fonts] legacy_clear_fonts` (default `false`, editable by hand too).
- **Default off:** the player's exact files, other locales, online/BNet screens, the chat input widget and
  ReallyTheLastSucker's BNet use remain unverified (sections above).
- **Safety:** the part checks the six TBLs on disk at start (size, header, line height not 0) and refuses the clear set if any
  fails or is missing, so a broken or absent font can never be loaded through it; the build and packager keep their checks and
  the packager refuses a release without the set. Non-Latin language dirs keep D2R's names.
- Game coverage: [testing](testing.md#lane-fonttoggle-in-game-clear-fonts-setting).
