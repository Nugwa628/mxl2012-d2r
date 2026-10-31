"""Classic (legacy graphics, G) version of D2R's Reign of the Warlock stash pages: Gems, Materials, Runes (lane rotwstash).

D2R 93847 draws the RotW pages only in HD: `bankexpansionlayouthd.json` has five tabs and one `AdvancedStashSlotWidget` per
item code (91) on the three pages `advancedstash_gems` / `_materials` / `_runes`, plus the stash cube
(`advancedstash_horadriccube`); the slot recesses are painted into the page backgrounds
(`PANEL\\Stash\\AdditionalStash\\PANEL_AdditionalStash_*`). Its classic `bankexpansionlayout.json` has two tabs (Personal,
Shared), two backgrounds (`expandedstash`, `additionalstash`, the shared tab's one) and none of those widgets, and D2R ships no
classic art for the pages (docs/legacy-graphics.md section 9).

This step writes, from the D2R extraction at build time (nothing of Blizzard's is in git):

  data/global/ui/layouts/bankexpansionlayout.json   D2R's classic layout rebuilt in the HD layout's structure: five tabs, the
      Personal / Shared widgets inside `basicstash_container` (as in HD, so the panel hides them on the RotW pages), the three
      RotW pages with the same item codes in the same order as HD, the stash cube; every text written out (bugs #30 / #33)
  data/global/ui/panel/rotwstash_{gems,materials,runes}.dc6   the HD page backgrounds down-rendered to the classic 320 x 432
      panel (4 tiles), the top 29 rows the classic tab band of D2R's `expandedstash.dc6` (so the tab bar sits on the same band
      on all five tabs), every slot recess and the cube window re-rendered at the classic cell size (29 per cell) under the
      widget's rect, then quantised to D2R's units palette (indices 1-224, Floyd-Steinberg)
  data/global/ui/panel/rotwstash_tabs.dc6        HD `MKB_Tabs_195_TGA` (inactive, active) down-rendered to 63 x 24 with the
      tab names drawn in (5 inactive frames, then 5 active) in D2R's classic `font6`, capitals: D2R's own tab text is too wide
      for a 63-pixel tab in classic ("PERSON", "MATERIAL:") and the classic tab bar takes no font or spacing (lane stashtab)
  data/global/ui/panel/rotwstash_cubecover.dc6   HD `HoradricCubeCover` down-rendered to the classic cube grid (87 x 116)
  data/global/ui/panel/rotwstash_button.dc6      HD `FrontEnd_ButtonSmall` (4 frames) down-rendered (the withdraw button)
  data/global/ui/panel/rotwstash_notify.dc6      HD `StashNotification` down-rendered (the "item went to this tab" mark)

HD -> classic: x / (1162 / 320), y / (1507 / 432), the scale tools/ui_panels.py uses the other way.

  py -3 -I tools/rotw_stash_legacy.py build [--d2r DIR] [--out DIR]     write the files above, then the check
  py -3 -I tools/rotw_stash_legacy.py check [--d2r DIR] [--out DIR]     only the check (exit 1 on a problem)
  py -3 -I tools/rotw_stash_legacy.py sheet DIR [--d2r DIR] [--out DIR] review sheet: HD page | classic mock-up, per page

--out is where the files go (default work/mod/data); --mod the mod's data folder with the built tables and item pictures
(default --out). tools/build.py stages the files in work/rotw_stash_legacy/data and puts them into the mod only with
MXL2012_ROTW_LEGACY=1: on a game without RotW, D2R 93847 crashes in classic mode as soon as the layout has an
AdvancedStashSlotWidget (docs/legacy-graphics.md 9.4), and whether it draws them with RotW is the owner's test. The check: the layout parses, the codes and their order equal HD's,
every slot inside the panel and apart from the others, every PANEL file it names exists (mod or D2R) with the frame sizes the
layout needs, every code's item row and classic picture (the picture must fit the slot), no `@key` left. Report:
rotw_stash_legacy.md next to --out. Tests: tools/tests/test_rotw_stash_legacy.py.
"""
import argparse
import csv
import json
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

import dc6  # noqa: E402
import fxpaths  # noqa: E402
import ui_art  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HD_W, HD_H = 1162, 1507
SX, SY = HD_W / ui_art.PANEL_W, HD_H / ui_art.PANEL_H
CELL = 29                       # classic $ItemCellSize (_profilesd.json); an item picture is 28 per cell
HD_CELL = 98
PAGES = ("gems", "materials", "runes")
HD_PAGE_ART = {"gems": "panel_additionalstash_gems", "materials": "panel_additionalstash_consumables",
               "runes": "panel_additionalstash_runes"}
PANEL_DC6 = {p: f"rotwstash_{p}" for p in PAGES}
TABS, COVER, BUTTON, NOTIFY = "rotwstash_tabs", "rotwstash_cubecover", "rotwstash_button", "rotwstash_notify"
TAB_W, TAB_H, TAB_PAD = 63, 24, 1   # five tabs across the 320-pixel panel (D2R's classic two are 79 x 24)
TAB_BAND = 29                   # rows 0-28 of D2R's classic stash: the black band with its gold line, where the tabs sit
TAB_TEXT = ["Personal", "Shared", "Gems", "Materials", "Runes"]  # D2R's English for @personal @shared @gems @materials @runes
TAB_FONT = "font6"              # D2R's classic small font (data/local/font/latin, read through fxpaths.d2r_file)
TAB_TEXT_MARGIN = 3             # free pixels left and right of a name inside the tab's rim
TAB_COLOURS = ((253, 253, 253), (191, 169, 105))  # inactive, active: D2R's classic tab text (lane stashtab's shots)
CLEAR = {"r": 0, "g": 0, "b": 0, "a": 0}
CUBE_CELLS = (3, 4)             # D2R's stash cube window (HD layout); see docs/legacy-graphics.md 9 for Median's 10 x 8 cube
HD_LAYOUT = Path("data/global/ui/layouts/bankexpansionlayouthd.json")
SD_LAYOUT = Path("data/global/ui/layouts/bankexpansionlayout.json")
HD_SPRITES = Path("data/hd/global/ui")
AT_KEY = re.compile(r'"(@[^"\n]*)"')
SD_BASE = Path("data/global/ui/layouts/bankoriginallayout.json")
MOVED = ("gold_max", "gold_amount", "gold_withdraw", "grid")  # into basicstash_container, as HD does


def lenient_json(text: str):
    """D2R's layout json: // comments and trailing commas."""
    text = re.sub(r'^\s*//.*$', "", text, flags=re.M)
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", text))


def find(node: dict, name: str) -> dict | None:
    if node.get("name") == name:
        return node
    for c in node.get("children", []):
        hit = find(c, name)
        if hit:
            return hit
    return None


def hd_pages(hd: dict) -> dict[str, list[tuple[str, tuple[int, int, int, int]]]]:
    """page -> [(item code, HD rect x, y, w, h)] in the HD layout's order."""
    out = {}
    for page in PAGES:
        w = find(hd, f"advancedstash_{page}")
        if w is None:
            raise ValueError(f"HD layout: no advancedstash_{page}")
        out[page] = [(c["fields"]["itemCode"], tuple(c["fields"]["rect"][k] for k in ("x", "y", "width", "height")))
                     for c in w.get("children", []) if c.get("type") == "AdvancedStashSlotWidget"]
    return out


def classic_box(hd_rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """The classic rect of an HD slot: centred where the HD box lands at the panel scale, sized to classic cells (29 per
    cell less the 1-pixel grid line: 28 x 28, 28 x 57)."""
    x, y, w, h = hd_rect
    cw, ch = max(1, round(w / HD_CELL)), max(1, round(h / HD_CELL))
    bw, bh = CELL * cw - 1, CELL * ch - 1
    cx, cy = (x + w / 2) / SX, (y + h / 2) / SY
    return round(cx - bw / 2), round(cy - bh / 2), bw, bh


def cube_grid(hd: dict) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """(HD box of the stash cube grid, classic grid rect at 29 per cell, centred on the same place)."""
    g = find(hd, "horadriccube_grid")["fields"]
    cx, cy = g["cellCount"]["x"], g["cellCount"]["y"]
    hx, hy = g["rect"]["x"], g["rect"]["y"]
    box = (hx, hy, cx * HD_CELL, cy * HD_CELL)
    w, h = cx * CELL, cy * CELL
    return box, (round((hx + box[2] / 2) / SX - w / 2), round((hy + box[3] / 2) / SY - h / 2), w, h)


def scaled(x: float, y: float) -> dict:
    return {"x": round(x / SX), "y": round(y / SY)}


def rect(x: int, y: int, w: int | None = None, h: int | None = None) -> dict:
    r = {"x": x, "y": y}
    if w is not None:
        r.update(width=w, height=h)
    return r


def merged(base: dict | None, child: dict) -> dict:
    """A child with its base layout's fields under its own (D2R's HD layout writes the children it moves into
    `basicstash_container` out in full; this does the same for the classic ones)."""
    if base is None:
        return child
    out = json.loads(json.dumps(child))
    out["fields"] = {**base.get("fields", {}), **child.get("fields", {})}
    return out


def classic_layout(hd: dict, sd: dict, sd_base: dict | None = None, named_tabs: bool = True) -> dict:
    """D2R's classic bankexpansionlayout.json in the HD layout's structure (see the module doc); `sd_base` is its basedOn
    file (BankOriginalLayout.json), whose fields the moved children carry in full. `named_tabs`: the tab art carries the
    names (frames 0-4 inactive, 5-9 active) and D2R draws no tab text; else D2R's text on two frames (cut in classic)."""
    base = {c["name"]: c for c in (sd_base or {}).get("children", [])}
    kids = {c["name"]: merged(base.get(c["name"]), c) if c["name"] in MOVED else c for c in sd["children"]}
    for need in ("click_catcher", "background", "gold_max", "gold_amount", "gold_withdraw", "close", "grid",
                 "SharedStashTabContainer", "BankTabs"):
        if need not in kids:
            raise ValueError(f"classic layout: no {need}")
    pages = hd_pages(hd)
    hd_bg = hd["fields"]["backgroundFile"]
    sd_bg = sd["fields"]["backgroundFile"]
    if len(hd_bg) != 5 or len(sd_bg) != 2:
        raise ValueError(f"backgroundFile: HD {len(hd_bg)}, classic {len(sd_bg)} (5 and 2 expected)")
    tabs = json.loads(json.dumps(find(hd, "BankTabs")["fields"]))
    if tabs.get("tabCount") != 5:
        raise ValueError("HD BankTabs: tabCount 5 expected")
    _box, grid = cube_grid(hd)
    conv = find(hd, "convert")["fields"]["rect"]
    wd = find(hd, "withdraw_button")["fields"]
    root = {
        "basedOn": sd.get("basedOn", "BankOriginalLayout.json"),
        "type": sd["type"], "name": sd["name"],
        "fields": {"backgroundFile": [*sd_bg, *(f"PANEL\\{PANEL_DC6[p]}" for p in PAGES)],
                   **{k: v for k, v in hd["fields"].items() if k.startswith("tabNotification")}},
        "children": [
            kids["click_catcher"], kids["background"], kids["close"],
            {"type": "TabBarWidget", "name": "BankTabs", "fields": {
                "tabCount": 5, "filename": f"PANEL\\{TABS}",
                **({"inactiveFrames": list(range(5)), "activeFrames": list(range(5, 10)),
                    "disabledFrames": [f if f < 0 else i for i, f in enumerate(tabs["disabledFrames"])],
                    # D2R writes the Personal tab's name itself whatever textStrings says: drawn clear, it hides
                    "textStrings": [""] * 5, "activeTextColor": CLEAR, "inactiveTextColor": CLEAR} if named_tabs else
                   {"inactiveFrames": [0] * 5, "activeFrames": [1] * 5, "disabledFrames": tabs["disabledFrames"],
                    "textStrings": TAB_TEXT}),
                "tabSize": {"x": TAB_W, "y": TAB_H}, "tabPadding": {"x": TAB_PAD, "y": 0},
                "onSwitchTabMessage": tabs["onSwitchTabMessage"],
                "notificationIconTemplate": {"filename": f"PANEL\\{NOTIFY}"}}},
            {"type": "Widget", "name": "basicstash_container", "children": [
                kids["gold_max"], kids["gold_amount"], kids["gold_withdraw"], kids["grid"], kids["SharedStashTabContainer"]]},
            *({"type": "Widget", "name": f"advancedstash_{p}", "children": [
                {"type": "AdvancedStashSlotWidget", "name": code,
                 "fields": {"rect": rect(*classic_box(r)), "itemCode": code}} for code, r in pages[p]]} for p in PAGES),
            {"type": "Widget", "name": "advancedstash_horadriccube", "children": [
                {"type": "InventoryGridWidget", "name": "horadriccube_grid", "fields": {
                    "rect": rect(grid[0], grid[1]), "cellCount": {"x": CUBE_CELLS[0], "y": CUBE_CELLS[1]},
                    "cellSize": "$ItemCellSize", "gemSocketFilename": "PANEL\\gemsocket"}},
                {"type": "ButtonWidget", "name": "convert", "fields": {
                    "rect": scaled(conv["x"], conv["y"]), "filename": "PANEL\\miniconvert", "tooltipString": "Transmute",
                    "tooltipOffset": {"x": 0, "y": -3}, "onClickMessage": find(hd, "convert")["fields"]["onClickMessage"]}},
                {"type": "ImageWidget", "name": "horadriccube_cover", "fields": {
                    "rect": rect(grid[0], grid[1]), "filename": f"PANEL\\{COVER}"}},
                {"type": "ButtonWidget", "name": "withdraw_button", "fields": {
                    "rect": scaled(wd["rect"]["x"], wd["rect"]["y"]), "filename": f"PANEL\\{BUTTON}",
                    "textString": "Withdraw", "pointSize": "$MediumFontSize",
                    "tooltipString": "Withdraw items from the previous season's advanced stash.\n"
                                     "Any items that won't fit must be removed manually.",
                    "onClickMessage": wd["onClickMessage"]}}]}]}
    text = json.dumps(root)
    left = AT_KEY.findall(text)
    if left:   # a `@key` in a served layout draws "Missing string" (bugs #30 / #33)
        root = json.loads(write_literals(text, left))
    return root


# D2R's English (ui.json) for the keys D2R's classic stash children carry
LITERALS = {"@stashRemoveOnly": "Remove Only", "@SharedStashPage": "Page %u / %u",
            "@SharedStashPreviousSeasonToggleTooltip": "Enable this to view your previous ladder season's shared stash tabs.\n"
            "Items can only be removed from these shared stash tabs and will be deleted when the next season starts.",
            "@strGoldWithdraw": "Withdraw", "@strClose": "Close", "@strUiMenu2": "Transmute"}


def write_literals(text: str, keys: list[str]) -> str:
    missing = sorted(set(keys) - set(LITERALS))
    if missing:
        raise ValueError(f"layout keys without a literal: {missing}")
    for k in set(keys):
        text = text.replace(json.dumps(k), json.dumps(LITERALS[k]))
    return text


# ---- pictures ----------------------------------------------------------------------------------------------------------

def down(im: Image.Image, w: int, h: int) -> Image.Image:
    """Lanczos on premultiplied alpha (no dark fringes), then a light unsharp mask: the HD art is soft at 1/3.5."""
    out = im.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
    a = out.getchannel("A")
    out = out.filter(ImageFilter.UnsharpMask(radius=1, percent=50, threshold=2))
    out.putalpha(a)
    return out


def quantise(im: Image.Image, pal: list[tuple[int, int, int]], dither: bool = True) -> np.ndarray:
    """Palette indices (0 = transparent) in D2R's units palette, only 1-224 (225-254 are black in D2R's palette and draw hot
    pink in its UI, docs/legacy-graphics.md 1)."""
    usable = pal[1:225]
    p = Image.new("P", (1, 1))
    p.putpalette([c for rgb in usable for c in rgb] + list(usable[0]) * (256 - len(usable)))
    q = im.convert("RGB").quantize(palette=p, dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE)
    idx = np.asarray(q).astype(np.int32)
    idx = np.where(idx >= len(usable), 0, idx) + 1
    idx[np.asarray(im.getchannel("A")) < 128] = 0
    return idx


def to_rgba(idx: np.ndarray, pal) -> Image.Image:
    lut = np.array([(*c, 255) for c in pal], dtype=np.uint8)
    lut[0] = (0, 0, 0, 0)
    return Image.fromarray(lut[idx], "RGBA")


def encode_frame(idx: np.ndarray) -> bytes:
    """DC6 block of a frame (rows stored bottom-up; 0x80 ends a line, 0x80|n skips n, n < 0x80 is a run of n indices)."""
    out = bytearray()
    for row in idx[::-1]:
        row = [int(v) for v in row]
        end = len(row)
        while end and row[end - 1] == 0:
            end -= 1
        x = 0
        while x < end:
            start = x
            if row[x] == 0:
                while x < end and row[x] == 0 and x - start < 0x7F:
                    x += 1
                out.append(0x80 | (x - start))
            else:
                while x < end and row[x] != 0 and x - start < 0x7F:
                    x += 1
                out.append(x - start)
                out += bytes(row[start:x])
        out.append(0x80)
    return bytes(out)


def dc6_bytes(frames: list[np.ndarray]) -> bytes:
    return dc6.build_dc6([(f.shape[1], f.shape[0], 0, 0, encode_frame(f)) for f in frames])


def panel_tiles(idx: np.ndarray) -> list[np.ndarray]:
    """A 320 x 432 panel as D2R's 4 tiles (ui_art.TILES: 256 x 256, 64 x 256, 256 x 176, 64 x 176)."""
    return [idx[y0:y1, x0:x1] for x0, y0, x1, y1 in ui_art.TILES]


class D2R:
    def __init__(self, root: Path, use_cache: bool = False):
        self.root = Path(root)
        self.data = self.root / "data" if (self.root / "data").exists() else self.root
        self.pal = dc6.palette(self.data / "global" / "palette" / "units" / "pal.dat")
        self.use_cache = use_cache

    def layout(self, rel: Path) -> dict:
        return lenient_json((self.data.parent / rel).read_text("utf-8-sig"))

    def sprite(self, rel: str) -> list[Image.Image]:
        return ui_art.read_sprite(self.data / "hd" / "global" / "ui" / f"{rel}.sprite")

    def classic_panel(self, name: str) -> Image.Image:
        return ui_art.panel_sets(self.data / "global" / "ui" / "panel" / f"{name}.dc6", self.pal)[0]

    def font(self, name: str) -> "Font | None":
        """A classic font of this extraction, else (`use_cache`) through fxpaths.d2r_file (the shared cache or a slot's
        CASC: the baseline extraction has no fonts); None when neither has it."""
        files = []
        for ext in ("tbl", "dc6"):
            rel = f"local/font/latin/{name}.{ext}"
            p = self.data / rel
            if not p.exists() and self.use_cache:
                try:
                    p = fxpaths.d2r_file(f"data/{rel}")
                except SystemExit:
                    return None
            if not p.exists():
                return None
            files.append(p)
        return Font(files[0].read_bytes(), dc6.read_dc6(files[1]), self.pal)


class Font:
    """A classic D2 font: the .tbl ("Woo!", a 12-byte head, then 14 bytes per glyph: char u16, u8, advance u8, height u8,
    u8, u16, frame u16, u32) and its DC6 (one fixed cell per glyph, drawn from the cell's top left)."""

    def __init__(self, tbl: bytes, frames: list, pal):
        if tbl[:4] != b"Woo!":
            raise ValueError("font .tbl: no Woo! head")
        self.glyphs = {}
        for i in range((len(tbl) - 12) // 14):
            char, _a, adv, _h, _b, _c, frame, _d = struct.unpack_from("<HBBBBHHI", tbl, 12 + i * 14)
            self.glyphs[char] = (adv, frame)
        self.frames, self.pal = frames, pal

    def width(self, text: str) -> int:
        """Ink width of `text` as drawn."""
        return self.render(text, (255, 255, 255)).width

    def render(self, text: str, colour: tuple[int, int, int]) -> Image.Image:
        """`text` in `colour` (the glyph's grey level scales it), cropped to its ink."""
        cells = [self.glyphs.get(ord(c), self.glyphs.get(ord("?"), (0, 0))) for c in text]
        h = max((self.frames[f][1] for _a, f in cells if f < len(self.frames)), default=1)
        im = Image.new("RGBA", (sum(a for a, _f in cells) + 32, h))
        x = 0
        for adv, f in cells:
            if f < len(self.frames):
                w, fh, _ox, _oy, block = self.frames[f]
                g = ui_art.to_image(dc6.decode_frame(w, fh, block, self.pal))
                lum = g.convert("L")
                im.alpha_composite(Image.merge("RGBA", [lum.point(lambda v, k=k: v * k // 255) for k in colour]
                                               + [g.getchannel("A")]), (x, 0))
            x += adv
        box = im.getbbox()
        return im.crop(box) if box else Image.new("RGBA", (0, h))


def tab_label_fit(font: Font, labels: list[str] = TAB_TEXT) -> list[tuple[str, int, bool]]:
    """(name as drawn, ink width, fits) per tab: a name fits inside TAB_W less TAB_TEXT_MARGIN on both sides."""
    room = TAB_W - 2 * TAB_TEXT_MARGIN
    return [(t.upper(), w, w <= room) for t, w in ((t, font.width(t.upper())) for t in labels)]


def named_tab_frames(tabs: list[Image.Image], font: Font, pal) -> list[np.ndarray]:
    """10 tab frames: the inactive art (tabs[0]) with each name, then the active art (tabs[1]) with each; the art
    dithered as before, the names put on after it without dither (crisp glyphs)."""
    out = []
    for state in (0, 1):
        base = quantise(tabs[state], pal)
        for label in TAB_TEXT:
            text = font.render(label.upper(), TAB_COLOURS[state])
            layer = Image.new("RGBA", tabs[state].size)
            layer.alpha_composite(text, ((TAB_W - text.width) // 2, (TAB_H - text.height) // 2))
            ink = np.asarray(layer.getchannel("A")) >= 128
            idx = base.copy()
            idx[ink] = quantise(layer, pal, dither=False)[ink]
            out.append(idx)
    return out


def page_picture(d2r: D2R, page: str, slots: list[tuple[str, tuple]], cube: tuple[tuple, tuple]) -> Image.Image:
    """The classic 320 x 432 page (RGBA, before quantising)."""
    hd = d2r.sprite(f"panel/stash/additionalstash/{HD_PAGE_ART[page]}")[0]
    if hd.size != (HD_W, HD_H):
        raise ValueError(f"{HD_PAGE_ART[page]}: {hd.size}, {HD_W} x {HD_H} expected")
    im = down(hd, ui_art.PANEL_W, ui_art.PANEL_H)
    im.paste(d2r.classic_panel("expandedstash").crop((0, 0, ui_art.PANEL_W, TAB_BAND)), (0, 0))
    boxes = [(r, classic_box(r)) for _code, r in slots] + [cube]
    for (hx, hy, hw, hh), (cx, cy, cw, ch) in boxes:
        im.paste(down(hd.crop((hx, hy, hx + hw, hy + hh)), cw, ch), (cx, cy))
    return im


def build(d2r: D2R, out: Path) -> list[str]:
    hd, sd = d2r.layout(HD_LAYOUT), d2r.layout(SD_LAYOUT)
    font = d2r.font(TAB_FONT)
    named = font is not None and all(fits for _t, _w, fits in tab_label_fit(font))
    lay = classic_layout(hd, sd, d2r.layout(SD_BASE), named_tabs=named)
    lp = out / "global" / "ui" / "layouts" / SD_LAYOUT.name
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps(lay, indent=1, ensure_ascii=False) + "\n", "utf-8", newline="")
    panel = out / "global" / "ui" / "panel"
    panel.mkdir(parents=True, exist_ok=True)
    pages, cube = hd_pages(hd), cube_grid(hd)
    report = [f"layout {lp.name}: 5 tabs, {sum(len(v) for v in pages.values())} slots"]
    for page in PAGES:
        idx = quantise(page_picture(d2r, page, pages[page], cube), d2r.pal)
        (panel / f"{PANEL_DC6[page]}.dc6").write_bytes(dc6_bytes(panel_tiles(idx)))
        report.append(f"{PANEL_DC6[page]}.dc6: {HD_PAGE_ART[page]} -> 320 x 432, {len(pages[page])} slot recesses + cube window")
    singles = {TABS: ("panel/stash/mkb_tabs_195_tga", (TAB_W, TAB_H)),
               COVER: ("panel/stash/additionalstash/horadriccubecover", tuple(cube[1][2:])),
               BUTTON: ("frontend/hd/final/frontend_buttonsmall", None),
               NOTIFY: ("panel/stash/additionalstash/stashnotification", None)}
    for name, (src, size) in singles.items():
        frames = d2r.sprite(src)
        w, h = size or (round(frames[0].width / SX), round(frames[0].height / SY))
        if name == TABS and named:
            idx = named_tab_frames([down(f, w, h) for f in frames[:2]], font, d2r.pal)
            note = f", the tab names drawn in {TAB_FONT}"
        else:
            idx = [quantise(down(f, w, h), d2r.pal) for f in frames]
            note = f"; no classic font {TAB_FONT}: D2R draws the names (cut in classic)" if name == TABS else ""
        (panel / f"{name}.dc6").write_bytes(dc6_bytes(idx))
        report.append(f"{name}.dc6: {src} -> {len(idx)} x {w} x {h}{note}")
    return report


# ---- check -------------------------------------------------------------------------------------------------------------

def read_tsv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def panel_file(name: str, out: Path, d2r: D2R, mod: Path | None = None) -> Path | None:
    rel = Path("global") / "ui" / "panel" / f"{name.lower()}.dc6"
    return next((p for p in (out / rel, (mod or out) / rel, d2r.data / rel) if p.exists()), None)


def check(d2r: D2R, out: Path, mod: Path | None = None) -> tuple[list[str], list[str]]:
    """`out`: where the step wrote; `mod`: the mod's data folder with the built tables and item pictures (default `out`)."""
    mod = mod or out
    problems, notes = [], []
    lp = out / "global" / "ui" / "layouts" / SD_LAYOUT.name
    if not lp.exists():
        return [f"{lp} missing (run build)"], notes
    text = lp.read_text("utf-8")
    lay = lenient_json(text)
    if AT_KEY.findall(text):
        problems.append(f"{lp.name}: @keys left: {sorted(set(AT_KEY.findall(text)))}")
    hd = d2r.layout(HD_LAYOUT)
    want = hd_pages(hd)
    got = {p: [(c["fields"]["itemCode"], tuple(c["fields"]["rect"][k] for k in ("x", "y", "width", "height")))
               for c in (find(lay, f"advancedstash_{p}") or {}).get("children", [])] for p in PAGES}
    for p in PAGES:
        if [c for c, _ in got[p]] != [c for c, _ in want[p]]:
            problems.append(f"page {p}: codes differ from HD's ({len(got[p])} vs {len(want[p])})")
        boxes = [r for _c, r in got[p]]
        for i, (x, y, w, h) in enumerate(boxes):
            if x < 0 or y < TAB_BAND or x + w > ui_art.PANEL_W or y + h > ui_art.PANEL_H:
                problems.append(f"page {p}: {got[p][i][0]} {boxes[i]} outside the panel below the tab band")
            for j in range(i):
                a = boxes[j]
                if x < a[0] + a[2] and a[0] < x + w and y < a[1] + a[3] and a[1] < y + h:
                    problems.append(f"page {p}: {got[p][i][0]} overlaps {got[p][j][0]}")
    codes = [c for p in PAGES for c, _ in got[p]]
    if len(codes) != len(set(codes)):
        problems.append("an item code has two slots")
    notes.append(f"{len(codes)} slots: " + ", ".join(f"{p} {len(got[p])}" for p in PAGES))
    named_tabs = not any((find(lay, "BankTabs") or {}).get("fields", {}).get("textStrings", ["?"]))
    if named_tabs:   # the names are in the tab art: each must fit its tab
        font = d2r.font(TAB_FONT)
        if font is None:
            notes.append(f"tab names: classic font {TAB_FONT} not found, their fit not checked")
        else:
            fit = tab_label_fit(font)
            room = TAB_W - 2 * TAB_TEXT_MARGIN
            problems += [f"tab name {t}: {w} wide in {TAB_FONT}, more than {room}" for t, w, ok in fit if not ok]
            notes.append(f"tab names in {TAB_FONT}: " + ", ".join(f"{t} {w}" for t, w, _ok in fit) + f" (room {room})")
    else:
        notes.append(f"tab names drawn by D2R (no classic font {TAB_FONT} at build time): cut in classic (PERSON, MATERIAL:)")
    # the files the layout names, with the frame sizes it needs
    need = {**{PANEL_DC6[p]: [(256, 256), (64, 256), (256, 176), (64, 176)] for p in PAGES},
            "expandedstash": None, "additionalstash": None, TABS: [(TAB_W, TAB_H)] * (10 if named_tabs else 2), COVER: None, BUTTON: None,
            NOTIFY: None, "miniconvert": None, "gemsocket": None, "buysellbtn": None, "goldcoinbtn": None}
    named = {m.lower() for m in re.findall(r'PANEL\\\\(\w+)', text)}
    for name in sorted(named - set(need)):
        problems.append(f"{lp.name}: PANEL\\{name} not in the check list")
    for name in sorted(named):
        p = panel_file(name, out, d2r, mod)
        if p is None:
            problems.append(f"PANEL\\{name}: no DC6 in the mod or D2R")
            continue
        sizes = [(w, h) for w, h, *_ in dc6.read_dc6(p)]
        if need.get(name) and sizes != need[name]:
            problems.append(f"{p.name}: frames {sizes}, expected {need[name]}")
    _box, grid = cube_grid(hd)
    cover = panel_file(COVER, out, d2r, mod)
    if cover and [(w, h) for w, h, *_ in dc6.read_dc6(cover)] != [tuple(grid[2:])]:
        problems.append(f"{COVER}.dc6 is not the cube grid's size {grid[2:]}")
    # every code's item and classic picture
    excel = mod / "global" / "excel"
    items = {}
    for t in ("misc", "armor", "weapons"):
        if (excel / f"{t}.txt").exists():
            for r in read_tsv(excel / f"{t}.txt"):
                items.setdefault(r.get("code"), r)
    if not items:
        notes.append(f"{excel}: no built tables, item codes not checked")
        return problems, notes
    rows = []
    for p in PAGES:
        for code, (x, y, w, h) in got[p]:
            r = items.get(code)
            if r is None:
                rows.append((p, code, "-", "-", "no item in Median's tables (empty slot, as in HD)"))
                continue
            inv = r.get("invfile", "")
            rel = Path("global") / "items" / f"{inv.lower()}.dc6"
            pic = next((q for q in (out / rel, mod / rel, d2r.data / rel) if q.exists()), None)
            stack = r.get("AdvancedStashStackable") == "1"
            if pic is None:
                problems.append(f"{code}: classic picture {inv}.dc6 missing")
                rows.append((p, code, r.get("name", ""), inv, "picture MISSING"))
                continue
            pw, ph = dc6.read_dc6(pic)[0][:2]
            fits = pw <= w + 1 and ph <= h + 1
            if not fits:
                problems.append(f"{code}: picture {pw} x {ph} larger than its slot {w} x {h}")
            where = "mod" if pic.is_relative_to(out) else "D2R"
            rows.append((p, code, r.get("name", ""), inv, f"{pw} x {ph} ({where}) in {w} x {h}"
                         + ("" if stack else "; AdvancedStashStackable not 1: the tab does not take it")))
    have = sum(1 for r in rows if r[2] != "-")
    notes.append(f"{have} of {len(rows)} codes are Median items, {len(rows) - have} have no item")
    check.rows = rows
    return problems, notes


check.rows = []


def report_md(problems: list[str], notes: list[str], built: list[str]) -> str:
    lines = ["# RotW stash pages in classic mode (tools/rotw_stash_legacy.py)", "", *(f"- {b}" for b in built), "",
             "## Check", "", *(f"- PROBLEM: {p}" for p in problems), *(f"- {n}" for n in notes), "",
             "| Page | Code | Item | invfile | Classic picture |", "|---|---|---|---|---|",
             *(f"| {' | '.join(r)} |" for r in check.rows), ""]
    return "\n".join(lines)


# ---- review sheet ------------------------------------------------------------------------------------------------------

def item_picture(code: str, out: Path, d2r: D2R, mod: Path) -> Image.Image | None:
    excel = mod / "global" / "excel"
    for t in ("misc", "armor", "weapons"):
        if (excel / f"{t}.txt").exists():
            for r in read_tsv(excel / f"{t}.txt"):
                if r.get("code") == code:
                    rel = Path("global") / "items" / f"{r.get('invfile', '').lower()}.dc6"
                    p = next((q for q in (out / rel, mod / rel, d2r.data / rel) if q.exists()), None)
                    if p:
                        w, h, _ox, _oy, block = dc6.read_dc6(p)[0]
                        return ui_art.to_image(dc6.decode_frame(w, h, block, d2r.pal))
    return None


def mock_up(d2r: D2R, out: Path, page: str, tab: int, mod: Path, with_items: bool = True) -> Image.Image:
    """The classic page as the layout puts it together: background, tab bar, items in their slots."""
    lay = lenient_json((out / "global" / "ui" / "layouts" / SD_LAYOUT.name).read_text("utf-8"))
    panel = out / "global" / "ui" / "panel"
    im = ui_art.panel_sets(panel / f"{PANEL_DC6[page]}.dc6", d2r.pal)[0] if page in PANEL_DC6 else d2r.classic_panel(page)
    tabs = [ui_art.to_image(dc6.decode_frame(w, h, b, d2r.pal)) for w, h, _x, _y, b in dc6.read_dc6(panel / f"{TABS}.dc6")]
    draw = ImageDraw.Draw(im)
    f = find(lay, "BankTabs")["fields"]
    for i, label in enumerate(f["textStrings"]):
        x = i * (TAB_W + TAB_PAD)
        im.alpha_composite(tabs[(f["activeFrames"] if i == tab else f["inactiveFrames"])[i]], (x, 0))
        if not label:   # the name is in the art
            continue
        tw = draw.textlength(label.upper())
        draw.text((x + (TAB_W - tw) / 2, 7), label.upper(), fill=(199, 179, 119) if i == tab else (150, 150, 150))
    def button(name: str, frame: int, widget: str) -> None:
        w, h, _x, _y, b = dc6.read_dc6(panel_file(name, out, d2r))[frame]
        r = find(lay, widget)["fields"]["rect"]
        im.alpha_composite(ui_art.to_image(dc6.decode_frame(w, h, b, d2r.pal)), (r["x"], r["y"]))
    button("buysellbtn", 10, "close")
    if page in PANEL_DC6:   # the cube window drawn open (the cover hides it when the stash holds no cube)
        button("miniconvert", 0, "convert")
        for c in find(lay, f"advancedstash_{page}")["children"]:
            r = c["fields"]["rect"]
            pic = item_picture(c["fields"]["itemCode"], out, d2r, mod) if with_items else None
            if pic:
                im.alpha_composite(pic, (r["x"] + (r["width"] - pic.width) // 2, r["y"] + (r["height"] - pic.height) // 2))
                draw.text((r["x"] + 1, r["y"] + r["height"] - 10), "1", fill=(255, 255, 255))
    return im


def sheet(d2r: D2R, out: Path, dest: Path, mod: Path | None = None) -> list[Path]:
    mod = mod or out
    dest.mkdir(parents=True, exist_ok=True)
    tabs_hd = d2r.sprite("panel/stash/mkb_tabs_195_tga")
    done = []
    for i, page in enumerate(PAGES):
        hd = d2r.sprite(f"panel/stash/additionalstash/{HD_PAGE_ART[page]}")[0].copy()
        for t in range(5):
            hd.alpha_composite(tabs_hd[1 if t == i + 2 else 0], (82 + t * 195, 146))
        hd_small = hd.resize((HD_W * 864 // HD_H, 864), Image.LANCZOS)
        cl = mock_up(d2r, out, page, i + 2, mod).resize((640, 864), Image.NEAREST)
        canvas = Image.new("RGBA", (hd_small.width + 640 + 60, 864 + 50), (24, 24, 24, 255))
        canvas.alpha_composite(hd_small, (20, 40))
        canvas.alpha_composite(cl, (hd_small.width + 40, 40))
        d = ImageDraw.Draw(canvas)
        d.text((20, 12), f"HD (D2R's page, scaled to 864 high): {page}", fill=(230, 230, 230))
        d.text((hd_small.width + 40, 12), f"classic mock-up (320 x 432 shown x2): {page}, classic item pictures, '1' = stack count",
               fill=(230, 230, 230))
        p = dest / f"rotwstash_{page}.png"
        canvas.convert("RGB").save(p)
        done.append(p)
    # the two pages that did not change art, with the new tab bar
    row = Image.new("RGBA", (2 * 640 + 60, 864 + 50), (24, 24, 24, 255))
    for i, name in enumerate(("expandedstash", "additionalstash")):
        row.alpha_composite(mock_up(d2r, out, name, i, mod).resize((640, 864), Image.NEAREST), (20 + i * 660, 40))
    ImageDraw.Draw(row).text((20, 12), "classic Personal and Shared (D2R's art) with the new five-tab bar", fill=(230, 230, 230))
    p = dest / "rotwstash_personal_shared.png"
    row.convert("RGB").save(p)
    return [*done, p]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("build", "check", "sheet"))
    ap.add_argument("dest", nargs="?", type=Path)
    ap.add_argument("--d2r", type=Path, default=fxpaths.D2R)
    ap.add_argument("--out", type=Path, default=ROOT / "work" / "mod" / "data")
    ap.add_argument("--mod", type=Path, help="the mod's data folder (tables, item pictures) when --out is elsewhere")
    a = ap.parse_args(argv)
    d2r = D2R(a.d2r, use_cache=True)
    built = build(d2r, a.out) if a.cmd == "build" else []
    if a.cmd == "sheet":
        for p in sheet(d2r, a.out, a.dest or Path("rotwstash-sheet"), a.mod):
            print(p)
        return 0
    problems, notes = check(d2r, a.out, a.mod)
    print("\n".join([*built, *notes, *(f"PROBLEM: {p}" for p in problems)]))
    if a.cmd == "build":
        (a.out.parent / "rotw_stash_legacy.md").write_text(report_md(problems, notes, built), "utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
