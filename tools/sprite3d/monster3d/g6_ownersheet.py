"""Stage 6: the owner's sheet of a mon_turn run: the 3D model (hd) against classic (legacy), as the game drew them.

  python g6_ownersheet.py <shots folder> <out.png> [--preview <death_preview.png>] [--title "<line>"] [--tile 220]

Blocks, one column per facing key (0..7) where the block is per facing:
- 8 facings: a steady live shot (same direction and mode before and after the shot, not walking, not lit by a lightning
  flash when the key has another), classic row then 3D row;
- walk: per key the brightest WL shot (WL before and after first, else WL on one side), gaps filled from other keys;
- death: per key the death shot still in DT after the shot (no flash-lit frame when another is in DT, else d0),
  classic then 3D, and the corpse (c0) of each key; for a death burst of g6_deathcap.py (shots with t_kill) the DT frame
  at FALL_AT of the key's own DT window (mid-fall);
- with --preview: s5_death.py's preview (the clip frame by frame against classic DT) below, scaled to the sheet's width.
The cut of a shot is g6_turnsheet.cut (the 300 px square of monsterdir\\CAPTURE.md).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from g6_turnsheet import BG, MODES, cut

FALL_AT = 0.7   # where in a key's DT window the dying cell is taken (0 = kill, 1 = last DT frame)


def steady(e):
    b, a = e["before"], e["after"]
    return e["what"][0] in "el" and b.get("dir") is not None and b["dir"] == a["dir"] and b["mode"] == a["mode"]


def bright(folder, e) -> float:
    """How well the monster shows in a shot: the 97th luminance percentile of the middle of the cut."""
    im = cut(folder, e).convert("L")
    w, h = im.size
    return float(np.percentile(np.asarray(im.crop((w // 4, h // 6, 3 * w // 4, 5 * h // 6))), 97))


def flashed(folder, entries, factor=1.3) -> set:
    """Shots lit by a lightning flash (the Fungus's own lightning or a bolt nearby): the cut's mean luminance above
    `factor` x the median of the given shots. Returns their file names."""
    mean = {e["shot"]: float(np.asarray(cut(folder, e).convert("L")).mean()) for e in entries}
    if not mean:
        return set()
    med = float(np.median(list(mean.values())))
    return {s for s, v in mean.items() if v > factor * med}


def walk_cells(folder, entries) -> list:
    """8 walk cells: for each key the shot with WL before and after (a walker may turn between the two reads), else WL on
    one side, the brightest first (a shot of a monster in shadow or half out of the cut says nothing); keys without a walk
    shot take the next best of the other keys, so the row is full when the run has 8 walk shots at all."""
    walk = [e for e in entries if e["what"][0] in "el" and 2 in (e["before"].get("mode"), e["after"].get("mode"))]
    score = {id(e): (e["before"].get("mode") == 2 == e["after"].get("mode"), bright(folder, e)) for e in walk}
    walk.sort(key=lambda e: score[id(e)], reverse=True)
    cells, used = [], set()
    for k in range(8):
        e = next((e for e in walk if e["spawn_key"] == k and id(e) not in used), None)
        cells.append(e)
        if e is not None:
            used.add(id(e))
    for i, c in enumerate(cells):
        if c is None:
            e = next((e for e in walk if id(e) not in used), None)
            if e is not None:
                cells[i] = e
                used.add(id(e))
    return cells


def dying_cell(folder, entries):
    """the dying shot of one key: among its death shots (d0, d1, ...) those still in DT (mode 0) after the shot, a
    frame not lit by a lightning flash first, the earliest of them (nearest mid-fall); d0 when none is in DT."""
    d = sorted((e for e in entries if e["what"][0] == "d"), key=lambda e: e["what"])
    if not d:
        return None
    if any("t_kill" in e for e in d):
        # a death burst of g6_deathcap.py: the DT frame at FALL_AT of the key's own DT window (the same fraction for
        # classic and 3D, so both show the same moment of their fall; the falls are not timed alike: classic falls in the
        # middle of DT, the 3D clip late, round 9), lightning-lit frames last
        dt = [e for e in d if e.get("t_kill", -1) >= 0 and e["after"].get("mode") == 0]
        if dt:
            t0, t1 = min(e["t_kill"] for e in dt), max(e["t_kill"] for e in dt)
            at = t0 + FALL_AT * (t1 - t0)
            flash = flashed(folder, d)
            dt.sort(key=lambda e: (e["shot"] in flash, abs(e["t_kill"] - at)))
            return dt[0]
    dt = [e for e in d if e["after"].get("mode") == 0] or d[:1]
    flash = flashed(folder, d) if len(d) > 1 else set()
    dt.sort(key=lambda e: e["shot"] in flash)
    return dt[0]


def main():
    a = sys.argv[1:]
    folder, out = Path(a[0]), a[1]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    tile, title, preview = int(opt("--tile", "220")), opt("--title", ""), opt("--preview", "")
    index = json.loads((folder / "monturn_index.json").read_text(encoding="utf-8"))
    by = {g: [e for e in index if e.get("graphics", "hd") == g] for g in ("legacy", "hd")}
    name = {"legacy": "classic", "hd": "3D"}
    rows = []      # (block title or None, row label, [entries or None])
    for g in ("legacy", "hd"):
        cells = []
        steady_live = [e for e in by[g] if steady(e) and e["after"]["mode"] != 2]
        flash = flashed(folder, steady_live)       # a flash-lit frame only when the key has no other
        for k in range(8):
            live = [e for e in steady_live if e["spawn_key"] == k]
            live.sort(key=lambda e: e["shot"] in flash)
            cells.append(live[0] if live else None)
        rows.append(("8 facings (live, as drawn)" if g == "legacy" else None, name[g], cells))
    for g in ("legacy", "hd"):
        rows.append(("walk (WL shots, the brightest of each key)" if g == "legacy" else None, name[g] + " walk",
                     walk_cells(folder, by[g])))
    for what, label in (("d0", "dying"), ("c0", "corpse")):
        for g in ("legacy", "hd"):
            if what == "d0":
                cells = [dying_cell(folder, [e for e in by[g] if e["spawn_key"] == k]) for k in range(8)]
            else:
                cells = [next((e for e in by[g] if e["spawn_key"] == k and e["what"] == what), None) for k in range(8)]
            rows.append(("death per facing (DT shot, mid-fall when the run has a death burst; then corpse)" if (what, g) == ("d0", "legacy") else None,
                         "%s %s" % (name[g], label), cells))
    lw, gap, head = 110, 4, 22
    width = lw + 8 * (tile + gap)
    height = 30 + sum(tile + 18 + (head if r[0] else 0) for r in rows)
    prev = None
    if preview:
        prev = Image.open(preview).convert("RGB")
        prev = prev.resize((width - 8, round(prev.height * (width - 8) / prev.width)), Image.LANCZOS)
        height += head + prev.height + 8
    sheet = Image.new("RGB", (width, height), BG)
    dr = ImageDraw.Draw(sheet)
    dr.text((6, 8), title, fill=(235, 235, 235))
    y = 30
    for block, label, cells in rows:
        if block:
            dr.text((6, y + 4), block, fill=(230, 200, 90))
            y += head
        dr.text((6, y + tile // 2), label, fill=(230, 230, 230))
        for k, e in enumerate(cells):
            if e is None:
                continue
            x = lw + k * (tile + gap)
            sheet.paste(cut(folder, e).resize((tile, tile), Image.LANCZOS), (x, y))
            m = e["after"]
            dr.text((x + 3, y + tile + 3), "key %d %s dir %s %s" % (e["spawn_key"], e["what"], m.get("dir"), MODES.get(m.get("mode"), m.get("mode"))),
                    fill=(190, 190, 190))
        y += tile + 18
    if prev is not None:
        dr.text((6, y + 4), "death clip frame by frame (offline render: 3D front / classic DT d4 / 3D side / classic DT d5)", fill=(230, 200, 90))
        sheet.paste(prev, (4, y + head))
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
