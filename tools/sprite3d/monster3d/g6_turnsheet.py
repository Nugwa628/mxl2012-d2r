"""Stage 6: contact sheet of a mon_turn run (the 8 facings of lane hdtools-monster's check): one column per facing key.

  python g6_turnsheet.py <shots folder> <out.png> [--lift 2.2] [--note "<line>"] [--graphics hd|legacy]

Rows: two live shots whose label is steady (the monster's direction is the same before and after the shot), a death shot and
the corpse, all as shot, of one graphics mode (hd unless --graphics says legacy; a run may hold both); with --lift a last row repeats the first live shot with that gamma (to read a dark body, labelled so).
The cut is the one of monsterdir\\CAPTURE.md: one sub-tile step (dx, dy) from the character is 24 shot pixels along dx - dy
and 12 along dx + dy, the character's feet are at 800, 428 of the 1600x900 shot, the cut is a 300 px square with the
monster's feet a quarter above its bottom edge.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

MODES = {0: "DT", 1: "NU", 2: "WL", 3: "GH", 4: "A1", 5: "A2", 12: "DD"}
BG = (24, 24, 30)


def cut(folder, e):
    lab = e["after"] if e["after"].get("x") is not None else e["before"]
    dx, dy = lab["x"] - lab["px"], lab["y"] - lab["py"]
    sx, sy = 800 + 24 * (dx - dy), 428 + 12 * (dx + dy)
    img = Image.open(folder / e["shot"]).convert("RGB")
    return img.crop((sx - 150, sy - 225, sx + 150, sy + 75))


def main():
    a = sys.argv[1:]
    folder, out = Path(a[0]), a[1]
    lift = float(a[a.index("--lift") + 1]) if "--lift" in a else 0
    note = a[a.index("--note") + 1] if "--note" in a else ""
    graphics = a[a.index("--graphics") + 1] if "--graphics" in a else "hd"
    index = [e for e in json.loads((folder / "monturn_index.json").read_text(encoding="utf-8"))
             if e.get("graphics", "hd") == graphics]
    rows = ["live 1", "live 2", "death", "corpse"] + (["live 1, gamma %g" % lift] if lift else [])
    sheet = Image.new("RGB", (90 + 8 * 304, 44 + len(rows) * 322), BG)
    dr = ImageDraw.Draw(sheet)
    dr.text((6, 6), note, fill=(230, 230, 230))
    for k in range(8):
        shots = [e for e in index if e["spawn_key"] == k]
        steady = [e for e in shots if e["what"][0] in "el" and e["before"].get("dir") is not None
                  and e["before"]["dir"] == e["after"]["dir"] and e["before"]["mode"] == e["after"]["mode"]]
        pick = steady[:1] + [e for e in steady[1:] if e["after"]["mode"] != steady[0]["after"]["mode"]][:1]
        if len(pick) < 2:
            pick += [e for e in steady if e not in pick][-1:]
        pick += [e for e in shots if e["what"] == "d1"] + [e for e in shots if e["what"] == "c0"]
        if lift and pick:
            pick.append(pick[0])
        dr.text((94 + k * 304, 26), "key %d" % k, fill=(230, 200, 90))
        for r, e in enumerate(pick):
            tile = cut(folder, e)
            if lift and r == len(rows) - 1:
                tile = Image.fromarray((255 * (np.asarray(tile) / 255.0) ** (1 / lift)).astype(np.uint8))
            x, y = 90 + k * 304, 44 + r * 322
            sheet.paste(tile, (x, y))
            lab = e["after"]
            dr.text((x + 4, y + 302), "%s dir %s %s" % (e["what"], lab.get("dir"), MODES.get(lab.get("mode"), lab.get("mode"))),
                    fill=(200, 200, 200))
    for r, name in enumerate(rows):
        dr.text((6, 44 + r * 322 + 140), name, fill=(230, 230, 230))
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
