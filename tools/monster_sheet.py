#!/usr/bin/env python
"""Classic monster art of one token as pictures: the reference a monster's HD picture is judged against.

  py -3 -I tools/monster_sheet.py info TOKEN                 modes, directions, frames, layers, boxes (JSON on stdout)
  py -3 -I tools/monster_sheet.py sheet TOKEN OUT_DIR        one contact sheet PNG per mode (rows = directions, columns = frames)
                  [--act N] [--scale K] [--bg R,G,B]
  py -3 -I tools/monster_sheet.py frames TOKEN OUT_DIR       every frame as an RGBA PNG on one common canvas per token
                  [--modes NU,WL] [--act N]                  (<mode>/<dir>_<frame>.png + frames.json with the anchor)

Reads Median's extracted MPQ (fxpaths.MXL: data/global/monsters/<token>/cof/*.cof and the layers' DCCs) and an act palette
of D2R (fxpaths.d2r_file). A frame is composed the way the classic client does it: the COF's layers in the COF's draw
order per direction and frame, palette index 0 transparent. Layer blend modes other than normal are drawn as normal and
named in `info`.

Directions are numbered as in the files. For 8 directions the file order is: 0 down-left, 1 up-left, 2 up-right,
3 down-right, 4 down, 5 left, 6 up, 7 right (screen directions).
"""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dcc  # noqa: E402
import fxpaths  # noqa: E402

COMPS = ("hd", "tr", "lg", "ra", "la", "rh", "lh", "sh", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8")
MODES = ("dt", "nu", "wl", "gh", "a1", "a2", "bl", "sc", "s1", "s2", "s3", "s4", "dd", "kb", "sq", "rn")
DIR_NAMES_8 = ("down-left", "up-left", "up-right", "down-right", "down", "left", "up", "right")
# the order the eight directions turn clockwise on screen, starting at "down" (file direction numbers)
CLOCKWISE_8 = (4, 0, 5, 1, 6, 2, 7, 3)


def parse_cof(b: bytes) -> dict:
    """COF: layers, frames, directions, version; 4 unknown bytes; box (4 x i32); speed (u32, 256 = one frame per tick at
    25 fps); 9 bytes per layer (composite, shadow, selectable, transparent, draw mode, weapon class[4]); one key byte per
    frame; the layer draw order (directions x frames x layers)."""
    n, frames, dirs = b[0], b[1], b[2]
    want = 28 + 9 * n + frames + frames * dirs * n
    if len(b) != want:
        raise ValueError("COF size %d, expected %d" % (len(b), want))
    layers = []
    for i in range(n):
        o = 28 + 9 * i
        layers.append({"comp": COMPS[b[o]], "shadow": b[o + 1], "selectable": b[o + 2], "transparent": b[o + 3],
                       "draw_mode": b[o + 4], "wclass": b[o + 5:o + 9].split(b"\0")[0].decode("latin-1").lower()})
    o = 28 + 9 * n
    keys = list(b[o:o + frames])
    o += frames
    order = [[list(b[o + (d * frames + f) * n:o + (d * frames + f + 1) * n]) for f in range(frames)] for d in range(dirs)]
    return {"layers": layers, "frames": frames, "dirs": dirs, "speed": struct.unpack_from("<I", b, 24)[0],
            "box": struct.unpack_from("<4i", b, 8), "keys": keys, "order": order}


def token_dir(token: str) -> Path:
    base = fxpaths.MXL / "monsters"
    for p in base.iterdir():
        if p.name.lower() == token.lower():
            return p
    raise SystemExit("no art folder for token %s under %s" % (token, base))


def find_file(folder: Path, name: str) -> Path | None:
    if not folder.is_dir():
        return None
    for p in folder.iterdir():
        if p.name.lower() == name.lower():
            return p
    return None


def monstats2_looks(token: str) -> dict[str, str]:
    """The first look (`lit` ...) of each composite, from the monstats2 row of the first monster that uses the token."""
    import csv
    def rows(name):
        with open(fxpaths.MXL_EXCEL / name, encoding="latin-1", newline="") as f:
            r = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
        return [dict(zip(r[0], x)) for x in r[1:]]
    ex = next((r["MonStatsEx"] for r in rows("monstats.txt") if r.get("Code", "").lower() == token.lower()), None)
    row = next((r for r in rows("monstats2.txt") if r["Id"] == ex), None)
    looks = {}
    if row:
        low = {k.lower(): v for k, v in row.items()}
        for c in COMPS:
            v = low.get(c + "v", "").strip('"')
            if v:
                looks[c] = v.split(",")[0].strip().lower()
    return looks


def load(token: str, modes=None) -> dict:
    """{mode: {"cof": parsed COF, "wclass": str, "layers": {comp: decoded DCC directions}}} for the modes the token has."""
    folder = token_dir(token)
    looks = monstats2_looks(token)
    out = {}
    cofs = folder / "cof" if (folder / "cof").is_dir() else find_file(folder, "cof")
    for p in sorted(cofs.iterdir()):
        name = p.stem.lower()
        if p.suffix.lower() != ".cof" or len(name) < 7:
            continue
        mode, wclass = name[len(token):len(token) + 2], name[len(token) + 2:]
        if modes and mode not in modes:
            continue
        cof = parse_cof(p.read_bytes())
        layers = {}
        for lay in cof["layers"]:
            comp = lay["comp"]
            look = looks.get(comp, "lit")
            f = find_file(find_file(folder, comp) or folder, "%s%s%s%s%s.dcc" % (token, comp, look, mode, lay["wclass"]))
            if f is None:
                lay["missing"] = True
                continue
            layers[comp] = dcc.decode(f.read_bytes())
            lay["file"] = f.name.lower()
            lay["bytes"] = f.stat().st_size
        out[mode] = {"cof": cof, "wclass": wclass, "layers": layers}
    return dict(sorted(out.items(), key=lambda kv: MODES.index(kv[0]) if kv[0] in MODES else 99))


def mode_box(entry: dict) -> tuple[int, int, int, int]:
    """Union of every frame box of every layer of a mode: x0, y0, x1, y1 (exclusive) in anchor space."""
    xs0, ys0, xs1, ys1 = [], [], [], []
    for dirs in entry["layers"].values():
        for _dx, _dy, _dw, _dh, frames in dirs:
            for x, y, w, h, _pix in frames:
                if w and h:
                    xs0.append(x), ys0.append(y), xs1.append(x + w), ys1.append(y + h)
    return (min(xs0), min(ys0), max(xs1), max(ys1)) if xs0 else (0, 0, 1, 1)


def compose(entry: dict, d: int, f: int, box, pal):
    """One frame as an RGBA image on the canvas `box`."""
    from PIL import Image
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    canvas = bytearray(w * h * 4)
    cof = entry["cof"]
    for li in cof["order"][d][f]:
        comp = COMPS[li] if li < len(COMPS) else None
        dirs = entry["layers"].get(comp)
        if not dirs or d >= len(dirs):
            continue
        frames = dirs[d][4]
        if not frames:
            continue
        fx, fy, fw, fh, pix = frames[f % len(frames)]
        for row in range(fh):
            base = ((fy - y0 + row) * w + (fx - x0)) * 4
            line = pix[row * fw:(row + 1) * fw]
            for col, c in enumerate(line):
                if c:
                    r, g, b = pal[c]
                    o = base + col * 4
                    canvas[o:o + 4] = bytes((r, g, b, 255))
    return Image.frombytes("RGBA", (w, h), bytes(canvas))


def act_palette(act: int):
    d = fxpaths.d2r_file("data/global/palette/act%d/pal.dat" % act).read_bytes()
    return [(d[i * 3 + 2], d[i * 3 + 1], d[i * 3]) for i in range(256)]


def info(token: str) -> dict:
    data = load(token)
    out = {"token": token.lower(), "modes": {}}
    for mode, e in data.items():
        cof = e["cof"]
        x0, y0, x1, y1 = mode_box(e)
        out["modes"][mode] = {
            "wclass": e["wclass"], "directions": cof["dirs"], "frames": cof["frames"], "speed": cof["speed"],
            "layers": [{k: v for k, v in lay.items()} for lay in cof["layers"]],
            "box": [x0, y0, x1, y1], "size": [x1 - x0, y1 - y0],
            "dcc_bytes": sum(lay.get("bytes", 0) for lay in cof["layers"])}
    out["frames_total"] = sum(m["directions"] * m["frames"] for m in out["modes"].values())
    out["dcc_bytes"] = sum(m["dcc_bytes"] for m in out["modes"].values())
    return out


def sheet(token: str, out_dir: Path, act: int, scale: int, bg) -> list[Path]:
    from PIL import Image, ImageDraw
    pal = act_palette(act)
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for mode, e in load(token).items():
        cof = e["cof"]
        box = mode_box(e)
        w, h = box[2] - box[0], box[3] - box[1]
        label_w, head = 74, 30
        img = Image.new("RGB", (label_w + cof["frames"] * w * scale, head + cof["dirs"] * h * scale), bg)
        dr = ImageDraw.Draw(img)
        dr.text((4, 4), "%s %s%s: %d directions x %d frames, cell %dx%d px, layers %s, act %d palette%s"
                % (token.lower(), mode.upper(), e["wclass"], cof["dirs"], cof["frames"], w, h,
                   "+".join(lay["comp"] for lay in cof["layers"]), act, ", x%d" % scale if scale > 1 else ""), fill=(255, 255, 255))
        for d in range(cof["dirs"]):
            name = DIR_NAMES_8[d] if cof["dirs"] == 8 else ""
            dr.text((4, head + d * h * scale + 4), "dir %d\n%s" % (d, name), fill=(255, 255, 0))
            for f in range(cof["frames"]):
                fr = compose(e, d, f, box, pal)
                if scale > 1:
                    fr = fr.resize((w * scale, h * scale), Image.NEAREST)
                img.paste(fr, (label_w + f * w * scale, head + d * h * scale), fr)
        p = out_dir / ("%s_%s_sheet.png" % (safe(token), mode))
        img.save(p)
        made.append(p)
    return made


def safe(token: str) -> str:
    """A file-name-safe spelling of a token (`~k` -> `7ek`)."""
    return "".join(c if c.isalnum() else "%02x" % ord(c) for c in token.lower())


def frames(token: str, out_dir: Path, act: int, modes) -> dict:
    pal = act_palette(act)
    data = load(token, modes)
    boxes = [mode_box(e) for e in data.values()]
    box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
    meta = {"token": token.lower(), "act": act, "box": list(box), "size": [box[2] - box[0], box[3] - box[1]],
            "anchor": [-box[0], -box[1]], "modes": {}}
    for mode, e in data.items():
        cof = e["cof"]
        (out_dir / mode).mkdir(parents=True, exist_ok=True)
        for d in range(cof["dirs"]):
            for f in range(cof["frames"]):
                compose(e, d, f, box, pal).save(out_dir / mode / ("%d_%02d.png" % (d, f)))
        meta["modes"][mode] = {"directions": cof["dirs"], "frames": cof["frames"], "speed": cof["speed"]}
    (out_dir / "frames.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("info")
    a.add_argument("token")
    a = sub.add_parser("sheet")
    a.add_argument("token")
    a.add_argument("out", type=Path)
    a.add_argument("--act", type=int, default=1)
    a.add_argument("--scale", type=int, default=1)
    a.add_argument("--bg", default="40,40,48")
    a = sub.add_parser("frames")
    a.add_argument("token")
    a.add_argument("out", type=Path)
    a.add_argument("--act", type=int, default=1)
    a.add_argument("--modes", default="")
    args = ap.parse_args(argv)
    if args.cmd == "info":
        print(json.dumps(info(args.token), indent=1))
    elif args.cmd == "sheet":
        for p in sheet(args.token, args.out, args.act, args.scale, tuple(int(v) for v in args.bg.split(","))):
            print(p)
    else:
        m = frames(args.token, args.out, args.act, [x.lower() for x in args.modes.split(",") if x] or None)
        print(json.dumps(m))
    return 0


if __name__ == "__main__":
    sys.exit(main())
