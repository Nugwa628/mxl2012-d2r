"""Sheets of the game check `mon_turn` (tools/game_checks.py): does a monster's art show the direction it faces.

The check labels every shot with the monster's facing (direction 0-63, key 0-7: key 0 faces the screen's bottom, then
clockwise), its unit mode and where it and the character stand: monturn_index.json in the run's folder. This tool cuts the
monster out of the shots and lays the cuts out, one column per facing key:

    py -3 tools/monster_turn_sheet.py facings OUT.png RUN... [token=2( act=1] [modes=1,2] [cut=300] [view=...]
    py -3 tools/monster_turn_sheet.py grid    OUT.png RUN... [modes=1,2,4,5,3,0,12]
    py -3 tools/monster_turn_sheet.py blocks  OUT.png RUN... [modes=2,4,3,0]
    py -3 tools/monster_turn_sheet.py walk    OUT.png RUN... key=3
    py -3 tools/monster_turn_sheet.py strip   OUT.png "label=picture[@x,y,w,h]"...
    py -3 tools/monster_turn_sheet.py table   OUT.json RUN...
    py -3 tools/monster_turn_sheet.py judge   OUT.json RUN... token=2( [act=1] [scale=1.5]

RUN is "label=folder[:graphics]" (graphics hd or legacy; without it the folder's first). `facings` is one row per RUN (the
best standing or walking shot per key) under a row of the classic files' own frames when token= is given; `grid` is one
row per unit mode and RUN; `blocks` is one block per unit mode with one row per label: RUNs of the same label fill one
row together (the first RUN that holds a key near the character wins, of its shots the middle one in time) and a key no RUN holds stays an
empty cell; `walk` is every shot of one spawned monster in order (it walks, turns, attacks, dies); `strip`
puts pictures (or cuts of them) side by side under their labels; `table` lists which key x unit mode pairs a RUN holds;
`judge` measures which direction of the classic files each steady shot shows (every frame of every file direction of the
shot's unit mode is laid over the cut, the best fit wins; needs OpenCV) and says per unit mode x key whether that is the
direction the key stands for.
Unit modes are the monster's: 0 death, 1 neutral, 2 walk, 3 get hit, 4 attack 1, 5 attack 2, 12 dead.

A shot counts as steady when the facing read before and after it is the same key and unit mode; a sheet takes steady shots
only (a cut labelled with a key the monster had already left would prove nothing).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

KEYS = 8
KEY_NAMES = ("down", "down-left", "left", "up-left", "up", "up-right", "right", "down-right")
MODE_NAMES = {0: "DT death", 1: "NU neutral", 2: "WL walk", 3: "GH get hit", 4: "A1 attack 1", 5: "A2 attack 2", 12: "DD dead"}
# Where the character's feet are in a 1600x900 shot and how many shot pixels one classic pixel is, per graphics mode.
VIEW = {"hd": (800.0, 428.0, 1.5), "legacy": (800.0, 428.0, 1.5)}
BG = (24, 24, 28)
NEAR = 10    # sub-tiles: a monster this close to the character is lit by its light
FEET = 0.64  # where the monster's feet are in a cut, from its top


def project(rec: dict, view) -> tuple[float, float]:
    """Where the monster's feet are in the shot: a sub-tile step (dx, dy) is 16 classic pixels along x - y and 8 along x + y."""
    cx, cy, s = view
    b = rec["before"]
    dx, dy = b["x"] - b["px"], b["y"] - b["py"]
    return cx + (dx - dy) * 16 * s, cy + (dx + dy) * 8 * s


def steady(rec: dict) -> bool:
    b, a = rec.get("before") or {}, rec.get("after") or {}
    return bool(b) and bool(a) and b.get("key") == a.get("key") and b.get("mode") == a.get("mode") and "x" in b and "px" in b


def pick(index: list[dict], graphics: str, key: int, modes) -> dict | None:
    """The steady shot of `graphics` that shows facing `key` in one of the unit `modes`: the first mode of `modes` that was
    shot wins, within it the monster that was spawned to face this key, then the earliest shot."""
    best = None
    for rec in index:
        if rec.get("graphics") != graphics or not steady(rec) or rec["before"]["key"] != key or rec["before"]["mode"] not in modes:
            continue
        rank = (list(modes).index(rec["before"]["mode"]), rec.get("spawn_key") != key, rec.get("t", 0.0))
        if best is None or rank < best[0]:
            best = (rank, rec)
    return best[1] if best else None


def middle(runs: list[dict], key: int, mode: int):
    """(run, shot) for a facing key in a unit mode out of several runs: the first run with a steady shot of it, and of that
    run's shots the middle one in time (an animation is best seen half way). Shots with the monster within NEAR sub-tiles
    of the character go first (further out it is outside the character's light, in classic graphics too). None when no
    run holds one."""
    for near in (True, False):
        for run in runs:
            recs = sorted((r for r in run["index"] if r.get("graphics") == run["graphics"] and steady(r)
                           and r["before"]["key"] == key and r["before"]["mode"] == mode
                           and (not near or max(abs(r["before"]["x"] - r["before"]["px"]), abs(r["before"]["y"] - r["before"]["py"])) <= NEAR)),
                          key=lambda r: r.get("t", 0.0))
            if recs:
                return run, recs[len(recs) // 2]
    return None


def coverage(index: list[dict], graphics: str) -> dict[int, list[int]]:
    """{unit mode: [keys with a steady shot]}."""
    out: dict[int, set] = {}
    for rec in index:
        if rec.get("graphics") == graphics and steady(rec):
            out.setdefault(rec["before"]["mode"], set()).add(rec["before"]["key"])
    return {m: sorted(k) for m, k in sorted(out.items())}


COF_MODE = {0: "dt", 1: "nu", 2: "wl", 3: "gh", 4: "a1", 5: "a2", 12: "dd"}
SHRINK = 2         # cuts and classic frames are compared at half the shot's size (16 times less work)
FIT_MIN = 0.45     # a fit below this is no reading (lightning over the monster, another unit in front of it)
FIT_MARGIN = 0.02  # the best direction must beat the next one by this much


def templates(token: str, act: int, mode: str, scale: float) -> dict:
    """{(file direction, frame): (colour, mask)} of one unit mode, each cut to its opaque pixels and `scale` times its size."""
    import cv2
    import numpy as np
    import monster_sheet
    entry = monster_sheet.load(token, (mode,))[mode]
    box, pal = monster_sheet.mode_box(entry), monster_sheet.act_palette(act)
    out = {}
    for d in range(entry["cof"]["dirs"]):
        for f in range(entry["cof"]["frames"]):
            a = np.asarray(monster_sheet.compose(entry, d, f, box, pal))
            ys, xs = np.nonzero(a[..., 3])
            if len(ys) < 50:
                continue
            a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            size = (max(8, round(a.shape[1] * scale / SHRINK)), max(8, round(a.shape[0] * scale / SHRINK)))
            colour = cv2.resize(a[..., :3], size, interpolation=cv2.INTER_AREA).astype(np.float32)
            mask = (cv2.resize(a[..., 3], size, interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
            out[(d, f)] = (colour, np.dstack([mask] * 3))
    return out


def fit(picture, temps: dict) -> dict[int, float]:
    """{file direction: its best frame's fit to the picture (masked, mean-free correlation: 1 is the same picture)}."""
    import cv2
    import numpy as np
    img = np.asarray(picture)
    img = cv2.resize(img, (img.shape[1] // SHRINK, img.shape[0] // SHRINK), interpolation=cv2.INTER_AREA).astype(np.float32)
    best: dict[int, float] = {}
    for (d, _f), (colour, mask) in temps.items():
        if colour.shape[0] > img.shape[0] or colour.shape[1] > img.shape[1]:
            continue
        r = cv2.matchTemplate(img, colour, cv2.TM_CCOEFF_NORMED, mask=mask)
        r = np.nan_to_num(r, nan=-1.0, posinf=-1.0, neginf=-1.0)
        best[d] = max(best.get(d, -1.0), float(r[r <= 1.0001].max(initial=-1.0)))
    return best


def reading(scores: dict[int, float]) -> tuple[int | None, float, float]:
    """(the direction a shot shows or None, its fit, its lead over the next direction)."""
    order = sorted(scores.items(), key=lambda kv: -kv[1])
    if not order:
        return None, 0.0, 0.0
    lead = order[0][1] - (order[1][1] if len(order) > 1 else -1.0)
    return (order[0][0] if order[0][1] >= FIT_MIN and lead >= FIT_MARGIN else None), order[0][1], lead


def verdict(votes: list[int | None], want: int) -> str:
    """yes / no / unclear for the readings of one unit mode x key."""
    read = [v for v in votes if v is not None]
    if not read:
        return "unclear"
    top = max(set(read), key=read.count)
    if read.count(top) * 2 <= len(read):
        return "unclear"
    return "yes" if top == want else "no"


templates.cache = {}


def parse_run(arg: str) -> dict:
    label, _, rest = arg.partition("=")
    folder, graphics = rest, None
    if rest.rsplit(":", 1)[-1] in ("hd", "legacy"):
        folder, graphics = rest.rsplit(":", 1)
    index = json.loads((Path(folder) / "monturn_index.json").read_text(encoding="utf-8"))
    return {"label": label, "folder": Path(folder), "graphics": graphics or (index[0]["graphics"] if index else "hd"), "index": index}


def font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # an older Pillow: its one small font
        return ImageFont.load_default()


def cut(run: dict, rec: dict, size: int, views: dict):
    """The square around the monster of one shot (its feet FEET of the way down: a corpse lies around them)."""
    from PIL import Image
    x, y = project(rec, views[rec["graphics"]])
    img = Image.open(run["folder"] / rec["shot"]).convert("RGB")
    left, top = int(round(x - size / 2)), int(round(y - size * FEET))
    out = Image.new("RGB", (size, size), BG)
    out.paste(img.crop((max(left, 0), max(top, 0), min(left + size, img.width), min(top + size, img.height))),
              (max(-left, 0), max(-top, 0)))
    return out


def square(im, size: int):
    """A picture as a square cell: scaled to fit, centred."""
    from PIL import Image
    k = size / max(im.width, im.height)
    im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
    out = Image.new("RGB", (size, size), BG)
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2))
    return out


def classic_cell(token: str, act: int, mode: str, key: int, size: int, scale: int):
    """The classic files' own frame for a facing key (frame 0 of `mode`), `scale` times its size."""
    from PIL import Image
    import monster_sheet
    data = monster_sheet.load(token, (mode,))
    entry = data[mode]
    box = monster_sheet.mode_box(entry)
    fr = monster_sheet.compose(entry, monster_sheet.CLOCKWISE_8[key], 0, box, monster_sheet.act_palette(act))
    fr = fr.resize((fr.width * scale, fr.height * scale), Image.NEAREST)
    out = Image.new("RGB", (size, size), BG)
    # the frame's anchor (0, 0 of the box space) is the unit's feet: put it where a cut has them
    ax, ay = -box[0] * scale, -box[1] * scale
    out.paste(fr, (int(size / 2 - ax), int(size * FEET - ay)), fr)
    return out


def layout(rows: list[tuple[str, list]], size: int, title: str, heads: list[str], empty: str = "not shot"):
    """rows: (row label, [cell image or caption string or None per column])."""
    from PIL import Image, ImageDraw
    label_w, head = 190, 54
    cols = max(len(c) for _, c in rows)
    img = Image.new("RGB", (label_w + cols * size, head + len(rows) * size), BG)
    dr = ImageDraw.Draw(img)
    big, small = font(18), font(14)
    dr.text((8, 6), title, fill=(255, 255, 255), font=big)
    for c, h in enumerate(heads[:cols]):
        dr.text((label_w + c * size + 6, 32), h, fill=(255, 220, 90), font=small)
    for r, (label, cells) in enumerate(rows):
        y = head + r * size
        dr.multiline_text((8, y + 8), label, fill=(255, 255, 255), font=small)
        for c, cell in enumerate(cells):
            x = label_w + c * size
            if cell is None or isinstance(cell, str):
                dr.rectangle((x + 2, y + 2, x + size - 3, y + size - 3), outline=(70, 70, 76))
                dr.text((x + 10, y + size // 2 - 8), cell or empty, fill=(150, 150, 156), font=small)
                continue
            picture, caption = cell
            img.paste(picture, (x, y))
            dr.rectangle((x, y, x + size - 1, y + size - 1), outline=(70, 70, 76))
            if caption:
                dr.text((x + 5, y + size - 20), caption, fill=(255, 255, 255), font=small, stroke_width=2, stroke_fill=(0, 0, 0))
    return img


def caption(rec: dict) -> str:
    b = rec["before"]
    return "dir %d  %s  %.1f s" % (b["dir"], MODE_NAMES.get(b["mode"], "mode %d" % b["mode"]).split()[0], rec.get("t", 0.0))


def options(args: list[str]) -> tuple[list[str], dict]:
    names = ("token", "act", "modes", "cut", "view", "key", "scale", "title")
    plain, opt = [], {}
    for a in args:
        k, eq, v = a.partition("=")
        if eq and k in names:
            opt[k] = v
        else:
            plain.append(a)
    return plain, opt


def views_of(opt: dict) -> dict:
    """view=hd:800,428,1.5;legacy:800,428,1.5"""
    views = dict(VIEW)
    for part in (opt.get("view") or "").split(";"):
        if part:
            name, _, vals = part.partition(":")
            views[name] = tuple(float(v) for v in vals.split(","))
    return views


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd, out = argv[0], Path(argv[1])
    plain, opt = options(argv[2:])
    size = int(opt.get("cut") or 300)
    heads = ["key %d  %s" % (k, KEY_NAMES[k]) for k in range(KEYS)]
    out.parent.mkdir(parents=True, exist_ok=True)
    if cmd == "strip":
        from PIL import Image
        cells, labels = [], []
        for a in plain:
            label, _, src = a.partition("=")
            path, _, box = src.partition("@")
            im = Image.open(path).convert("RGB")
            if box:
                x, y, w, h = (int(v) for v in box.split(","))
                im = im.crop((x, y, x + w, y + h))
            cells.append((square(im, size), ""))
            labels.append(label)
        layout([(opt.get("title") or "", cells)], size, opt.get("title") or "one monster, four looks", labels).save(out)
        print("wrote", out)
        return 0
    runs = [parse_run(a) for a in plain]
    views = views_of(opt)
    modes = [int(m) for m in (opt.get("modes") or ("1,2" if cmd == "facings" else "1,2,4,5,3,0,12")).split(",")]
    if cmd == "table":
        table = {r["label"]: {MODE_NAMES.get(m, str(m)): keys for m, keys in coverage(r["index"], r["graphics"]).items()} for r in runs}
        out.write_text(json.dumps(table, indent=1), encoding="utf-8")
        print(json.dumps(table))
        return 0
    if cmd == "judge":
        import monster_sheet
        token, act, scale = opt["token"], int(opt.get("act") or 1), float(opt.get("scale") or 1.5)
        result = {}
        for r in runs:
            cells: dict = {}
            for rec in r["index"]:
                if rec.get("graphics") != r["graphics"] or not steady(rec) or rec["before"]["mode"] not in COF_MODE:
                    continue
                mode = COF_MODE[rec["before"]["mode"]]
                temps = templates.cache.setdefault(mode, templates(token, act, mode, scale))
                d, score, lead = reading(fit(cut(r, rec, size, views), temps))
                cell = cells.setdefault("%s key %d" % (mode.upper(), rec["before"]["key"]), {"want": monster_sheet.CLOCKWISE_8[rec["before"]["key"]], "shots": []})
                cell["shots"].append({"shot": rec["shot"], "shows": d, "fit": round(score, 3), "lead": round(lead, 3)})
            for cell in cells.values():
                cell["verdict"] = verdict([s["shows"] for s in cell["shots"]], cell["want"])
            result[r["label"]] = dict(sorted(cells.items()))
            print(r["label"])
            for mode in ("NU", "WL", "A1", "A2", "GH", "DT", "DD"):
                line = ["%d:%s" % (k, result[r["label"]]["%s key %d" % (mode, k)]["verdict"]) if "%s key %d" % (mode, k) in cells else "%d:-" % k
                        for k in range(KEYS)]
                print("  %s  %s" % (mode, "  ".join(line)))
        out.write_text(json.dumps(result, indent=1), encoding="utf-8")
        return 0
    rows = []
    if cmd == "facings":
        if opt.get("token"):
            scale = int(opt.get("scale") or 2)
            rows.append(("classic files\n(frame 0 of NU,\nx%d)" % scale,
                         [(classic_cell(opt["token"], int(opt.get("act") or 1), "nu", k, size, scale),
                           "file direction %d" % __import__("monster_sheet").CLOCKWISE_8[k]) for k in range(KEYS)]))
        for r in runs:
            cells = []
            for k in range(KEYS):
                rec = pick(r["index"], r["graphics"], k, modes)
                cells.append((cut(r, rec, size, views), caption(rec)) if rec else None)
            rows.append(("%s\n(%s graphics)" % (r["label"], r["graphics"]), cells))
        title = opt.get("title") or "the 8 facings: one column per facing key (standing or walking)"
    elif cmd == "grid":
        for m in modes:
            for r in runs:
                cells = []
                for k in range(KEYS):
                    rec = pick(r["index"], r["graphics"], k, (m,))
                    cells.append((cut(r, rec, size, views), caption(rec)) if rec else None)
                rows.append(("%s\n%s\n(%s graphics)" % (MODE_NAMES.get(m, "mode %d" % m), r["label"], r["graphics"]), cells))
        title = opt.get("title") or "unit mode x facing key"
    elif cmd == "blocks":
        from PIL import Image
        labels = list(dict.fromkeys(r["label"] for r in runs))
        blocks = []
        for m in [int(v) for v in (opt.get("modes") or "2,4,3,0").split(",")]:
            rows = []
            for label in labels:
                cells = []
                for k in range(KEYS):
                    hit = middle([r for r in runs if r["label"] == label], k, m)
                    cells.append((cut(hit[0], hit[1], size, views), "%s  %s" % (caption(hit[1]), hit[0]["folder"].name[-14:])) if hit else None)
                rows.append((label, cells))
            blocks.append(layout(rows, size, MODE_NAMES.get(m, "mode %d" % m), heads, "not captured"))
        top = 34 if opt.get("title") else 0
        sheet = Image.new("RGB", (blocks[0].width, top + sum(b.height + 12 for b in blocks)), BG)
        if top:
            from PIL import ImageDraw
            ImageDraw.Draw(sheet).text((8, 6), opt["title"], fill=(255, 255, 255), font=font(20))
        y = top
        for b in blocks:
            sheet.paste(b, (0, y))
            y += b.height + 12
        sheet.save(out)
        print("wrote", out)
        return 0
    elif cmd == "walk":
        key = int(opt.get("key") or 0)
        heads = []
        for r in runs:
            recs = [x for x in r["index"] if x.get("graphics") == r["graphics"] and x.get("spawn_key") == key and x.get("before", {}).get("px") is not None]
            cells = []
            for rec in recs:
                b = rec["before"]
                cells.append((cut(r, rec, size, views), "key %d %s %.1f s%s" % (
                    b["key"], MODE_NAMES.get(b["mode"], str(b["mode"])).split()[0], rec.get("t", 0.0), "" if steady(rec) else " (turning)")))
            rows.append(("%s\n(%s graphics)" % (r["label"], r["graphics"]), cells or [None]))
            heads = [x["what"] for x in recs] if len(recs) > len(heads) else heads
        title = opt.get("title") or "one monster from its spawn to its corpse (spawned to face key %d %s)" % (key, KEY_NAMES[key])
    else:
        print(__doc__)
        return 2
    layout(rows, size, title, heads).save(out)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
