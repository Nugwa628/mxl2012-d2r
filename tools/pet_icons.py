"""Pet icons by the portrait (bug #514, docs/hd-icons.md "Pet icons").

D2R draws one icon per pet type the player has (pettype.txt `baseicon`): legacy `data/global/ui/hireables/<baseicon>.dc6`,
HD `data/hd/global/ui/hireables/<baseicon>.sprite` (+ `.lowend.sprite`), placed by `data/global/ui/layouts/hireablespanel[hd].json`.

Layout (always): D2R's HD row of summon icons is 175 units per icon and writes each name left-aligned under its icon on one
line (`nameAlternationSecondSetY` 0), so Median's longer names ran into the next one ("Guardian SpiThunderbear"). The mod's
copy of hireablespanelhd.json staggers every other name by NAME_STAGGER, as the legacy panel does (`nameAlternationY` 10).
Seen in game (lane peticons): D2R's HD row shows at most 9 summon types whatever the spacing (the vertical first set, where
the mercenary sits, has no such limit); not changed here.

Icons (tools/data/pet_icons.json, only when its `enabled` and the entry's are on, or with --try): the entry's pettype gets
baseicon `mxl_<pettype>`. HD: D2R's HD icon `icon` with its 10-pixel gold frame kept and the picture inside shifted in hue /
saturation / value. Legacy: `mxl_<pettype>.dc6` is a byte copy of the DC6 the row named before (Median's choice), so legacy
draws exactly what Median drew.

  py -3 tools/pet_icons.py build [--mod work/mod] [--try all|<pettype,...>]
  py -3 tools/pet_icons.py sheet OUT.png [--try ...]     review sheet: legacy (Median), HD now, HD with the entry
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402,F401
import fxpaths  # noqa: E402
import dc6  # noqa: E402
import ui_art  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "tools" / "data" / "pet_icons.json"
MOD = ROOT / "work" / "mod"
LAYOUT = "data/global/ui/layouts/hireablespanelhd.json"
NAME_STAGGER = 30  # HD layout units (1600 px window: about 12 px); the legacy panel staggers by 10 of its 800
HD_DIR, DC6_DIR = "data/hd/global/ui/hireables", "data/global/ui/hireables"
FRAME = {120: 10, 60: 5}  # gold frame width of D2R's HD pet icons (sprite, lowend sprite)
PREFIX = "mxl_"


def load_spec(path: Path = SPEC) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def chosen(spec: dict, trial: str | None = None) -> dict:
    """The entries to build: all when `trial` is "all", the named ones for a list, else the enabled ones of an enabled file."""
    pets = spec.get("pets", {})
    if trial:
        names = set(pets) if trial == "all" else {t.strip() for t in trial.split(",") if t.strip()}
        unknown = names - set(pets)
        if unknown:
            raise SystemExit(f"pet_icons: no entry for {sorted(unknown)}")
        return {k: v for k, v in pets.items() if k in names}
    if not spec.get("enabled"):
        return {}
    return {k: v for k, v in pets.items() if v.get("enabled", True)}


def layout_text(src: str) -> str:
    """D2R's hireablespanelhd.json with the summon names staggered."""
    out, n = re.subn(r'("nameAlternationSecondSetY"\s*:\s*)-?\d+', rf"\g<1>{NAME_STAGGER}", src)
    if n != 1:
        raise ValueError("hireablespanelhd.json: no nameAlternationSecondSetY field")
    return out


def shift(im: Image.Image, e: dict) -> Image.Image:
    """The icon with the picture inside its frame shifted (hue degrees, sat / val factors, mirror); the frame is kept."""
    im = im.convert("RGBA")
    f = FRAME.get(im.width, round(im.width / 12))
    box = (f, f, im.width - f, im.height - f)
    inner = im.crop(box)
    if e.get("mirror"):
        inner = inner.transpose(Image.FLIP_LEFT_RIGHT)
    dh, ks, kv = e.get("hue", 0) / 360.0, e.get("sat", 1.0), e.get("val", 1.0)
    if dh or ks != 1.0 or kv != 1.0:
        alpha = inner.getchannel("A")
        hsv = np.asarray(inner.convert("RGB").convert("HSV")).astype(np.float64)
        hsv[..., 0] = (hsv[..., 0] + dh * 256) % 256
        hsv[..., 1] = np.clip(hsv[..., 1] * ks, 0, 255)
        hsv[..., 2] = np.clip(hsv[..., 2] * kv, 0, 255)
        inner = Image.fromarray(np.rint(hsv).astype(np.uint8), "HSV").convert("RGB")
        inner.putalpha(alpha)
    out = im.copy()
    out.paste(inner, box)
    return out


def table_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    lines = Path(path).read_text("utf-8").split("\n")
    head = lines[0].rstrip("\r").split("\t")
    return head, [ln.rstrip("\r").split("\t") for ln in lines[1:] if ln.strip()]


def set_baseicons(path: Path, icons: dict[str, str]) -> dict[str, str]:
    """pettype.txt with `baseicon` replaced for the rows of `icons` ({pettype: new name}); returns {pettype: old name}."""
    text = Path(path).read_bytes().decode("utf-8")  # no newline translation: the row ends stay as the table has them
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    head = lines[0].split("\t")
    col = head.index("baseicon")
    old = {}
    for i, ln in enumerate(lines[1:], 1):
        cells = ln.split("\t")
        if cells and cells[0] in icons and len(cells) > col:
            old[cells[0]] = cells[col]
            cells[col] = icons[cells[0]]
            lines[i] = "\t".join(cells)
    Path(path).write_bytes(nl.join(lines).encode("utf-8"))
    return old


def build(mod: Path = MOD, trial: str | None = None) -> int:
    mod = Path(mod)
    (mod / LAYOUT).parent.mkdir(parents=True, exist_ok=True)
    (mod / LAYOUT).write_bytes(layout_text(fxpaths.d2r_file(LAYOUT).read_bytes().decode("utf-8")).encode("utf-8"))
    print(f"layout: {LAYOUT} (summon names staggered by {NAME_STAGGER})")
    pets = chosen(load_spec(), trial)
    if not pets:
        print("icons: off (tools/data/pet_icons.json `enabled`; the owner's review comes first)")
        return 0
    excel = mod / "data" / "global" / "excel"
    banks = [p for p in (excel / "pettype.txt", excel / "base" / "pettype.txt") if p.exists()]
    if not banks:
        raise SystemExit(f"pet_icons: no pettype.txt under {excel}")
    names = {k: PREFIX + k.lower() for k in pets}
    olds = {}
    for p in banks:
        for k, v in set_baseicons(p, names).items():
            olds.setdefault(k, v)
    if any(v.lower().startswith(PREFIX) for v in olds.values()):  # a second run over the same tables: Median's names
        median = median_baseicons()
        olds = {k: median.get(k, "") if v.lower().startswith(PREFIX) else v for k, v in olds.items()}
    missing = sorted(set(pets) - set(olds))
    if missing:
        raise SystemExit(f"pet_icons: pettype rows not in the built table: {missing}")
    for k, e in pets.items():
        for suffix in (".sprite", ".lowend.sprite"):
            src = ui_art.read_sprite(fxpaths.d2r_file(f"{HD_DIR}/{e['icon']}{suffix}"))[0]
            ui_art.write_sprite(mod / HD_DIR / f"{names[k]}{suffix}", [shift(src, e)])
        dst = mod / DC6_DIR / f"{names[k]}.dc6"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(fxpaths.d2r_file(f"{DC6_DIR}/{olds[k].lower()}.dc6").read_bytes())
        print(f"icon: {k:16} legacy {olds[k]} (copy), HD {e['icon']} hue {e.get('hue', 0)} sat {e.get('sat', 1.0)} val {e.get('val', 1.0)}")
    print(f"icons: {len(pets)} pet types, pettype.txt baseicon in {len(banks)} bank(s)")
    return 0


def median_baseicons() -> dict[str, str]:
    head, rows = table_rows(fxpaths.MXL_EXCEL / "pettype.txt")
    c = head.index("baseicon")
    return {r[0]: r[c] for r in rows if len(r) > c}


def sheet(out: Path, trial: str | None = "all") -> Path:
    """Per entry: Median's legacy icon (DC6, x2), D2R's HD icon now (the same name), the proposed HD icon, the why."""
    pal = dc6.palette(fxpaths.d2r_file("data/global/palette/units/pal.dat"))
    pets = chosen(load_spec(), trial)
    base = median_baseicons()
    cw, rh = 1100, 136
    im = Image.new("RGB", (cw, 30 + rh * len(pets)), (28, 28, 28))
    d = ImageDraw.Draw(im)
    d.text((8, 8), "pet type      legacy (Median, unchanged)   HD now   HD proposed   source", fill=(255, 220, 120))
    for i, (k, e) in enumerate(pets.items()):
        y = 30 + i * rh
        old = base.get(k, "")
        w, h, _ox, _oy, blk = dc6.read_dc6(fxpaths.d2r_file(f"{DC6_DIR}/{old.lower()}.dc6"))[0]
        leg = ui_art.to_image(dc6.decode_frame(w, h, blk, pal)).resize((w * 2, h * 2), Image.NEAREST)
        now = ui_art.read_sprite(fxpaths.d2r_file(f"{HD_DIR}/{old.lower()}.sprite"))[0]
        new = shift(ui_art.read_sprite(fxpaths.d2r_file(f"{HD_DIR}/{e['icon']}.sprite"))[0], e)
        d.text((8, y + 4), k, fill=(255, 255, 255))
        d.text((8, y + 20), f"was {old}", fill=(170, 170, 170))
        im.paste(leg.convert("RGB"), (150, y + 20))
        im.paste(now.convert("RGB"), (260, y + 4))
        im.paste(new.convert("RGB"), (400, y + 4))
        d.text((540, y + 8), f"{e['icon']}  hue {e.get('hue', 0)}  sat {e.get('sat', 1.0)}  val {e.get('val', 1.0)}", fill=(200, 200, 120))
        d.text((540, y + 30), e.get("why", "")[:90], fill=(220, 220, 220))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--mod", type=Path, default=MOD)
    b.add_argument("--try", dest="trial")
    s = sub.add_parser("sheet")
    s.add_argument("out", type=Path)
    s.add_argument("--try", dest="trial", default="all")
    a = ap.parse_args(argv)
    if a.cmd == "build":
        return build(a.mod, a.trial)
    print(sheet(a.out, a.trial))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
