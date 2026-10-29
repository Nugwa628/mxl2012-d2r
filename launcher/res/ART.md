# Downloader art (D2R-XL 2012)

The background is the owner's art; the panel and the icon are original and procedural, made by the scripts in
`tools/launcher_art/` from noise, gradients and polygons (no source images, no AI image service).

| File | Size / format | Used for |
|---|---|---|
| `background.png` | 960 x 640, PNG RGB | window background, drawn 1:1 (the canvas is its size). **Owner art**, made by the project owner for the downloader (2026-10-28, "option B"): a black eclipse over rune-carved spires, with the title "D2R-XL 2012" and the subtitle "MEDIAN XL 2012 FOR DIABLO II: RESURRECTED" baked in. Converted from the owner's `D2R_XL_top_center_loop.webp` (960 x 640, one frame) to PNG with no scaling. No generator: do not regenerate or edit it with the tools |
| `popup-window.png` | 500 x 170, PNG RGBA (transparent corners, ~98 % opaque stone) | the status panel at (230,262) |
| `icon.ico` | 256 (PNG), 128, 64, 48, 32, 16 (BMP), 32-bit alpha | exe icon |

`docs/icon.png` (512 x 512) is the same icon for the README.

## Zones of the background

The title and subtitle fill the top, down to about y 255: nothing is drawn there. Everything else sits below
(`launcher/src/win/window.cpp`):

| Zone | Rect | Background there |
|---|---|---|
| title, subtitle | x 130..830, y 0..255 | bright (the art's focus); keep clear |
| status panel, progress line, bar | panel (230,262) 500 x 170; status from (270,284), 19 px a line; bar (272,389) 416 x 9 | covered by the opaque panel |
| Install / Stop | (360,444) 240 x 60 | dark ground (mean luminance ~44 of 255) |
| Default mod, Move plugin (only when needed) | (195,457) and (615,457), 150 x 34 | either side of Install, over the spires' feet; the buttons have their own dark fill |
| small buttons | one row at y 516, h 34: Repair (175, w 140), Uninstall or Get D2RLoader (325, w 140 / 170), D2R folder (475, w 150), Mods folder (635, w 150); the row is centred | lava-lit ground (mean ~68, bright spots); the buttons have their own dark fill |
| how to play | centred from y 570, two lines, wrap width 740 | dark (mean ~25) |
| footer, link icon | text centred on y 616; icon (918,602) 28 x 28 | darkest (mean ~18) |

Light text there has a 1 px black shadow (window.cpp `Text`).

## Regenerate the panel and the icon

```
py -3 -m venv .venv-art && .venv-art\Scripts\pip install -r tools/launcher_art/requirements.txt
.venv-art\Scripts\python tools/launcher_art/make_all.py [--fonts <folder with RobotoCondensed.ttf>] [--preview preview.png]
```

Output goes to `launcher/res/` and `docs/icon.png` (`--out`, `--icon-png`, `--only panel|icon`); `background.png` is
never written. Fixed seeds: the output is deterministic for a given Pillow/numpy. `--preview` (or
`py -3 tools/launcher_art/make_preview.py <preview.png>`) renders the background and panel with mock text and buttons at
the layout rects of `launcher/src/win/window.cpp`, in Exocet and Roboto Condensed read from `--fonts`,
`$MXL_LAUNCHER_RES` or `launcher/res/`; it is for review and is not committed.

If the window layout moves (PanelRect, button rects, HowToPlayRect, FooterRect), update `make_preview.py` and check the
zones above in the preview.
