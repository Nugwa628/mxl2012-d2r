"""The gamepad (controller) UI's skill trees for Median's seven classes (lane wltree).

D2R's controller layout (`layouts/controller/skillstreepanelhd.json`, basedOn the PC one) draws each tab's tree from its own
art, `Controller/Panel/Spells/V2/<xx>SkillTree` (3 frames, frame n = tab n), over the shared stone
`CenterPanelBG_SkillTrees`. Each frame is transparent but for the tab highlight strip at the top and the engraved socket +
level box of every vanilla skill cell (3 columns x 6 rows) with vanilla's arrows. The mod shipped none, so Median's trees
(columns 1 and 3, rows 1-5) sat on vanilla's art: 12-14 empty sockets per class and arrows to nothing.

This step writes, from D2R's own V2 art (nothing of it is in git), for am so ne pa ba dr as:

  data/hd/global/ui/controller/panel/spells/v2/<xx>skilltree.sprite (+ .lowend.sprite, half size)
      frame n: D2R's frame n of the same class above STRIP_H (the tab strip), then D2R's own socket (cut from its Sorceress
      art, SOCKET_FROM) on every cell of SkillPage 3 - n that holds a skill, at the same offset from the layout's
      skillColumn / skillRow as D2R's art has it, and D2R's own short arrow (ARROW_FROM) on every chain link of
      skill_tree_art.page_arrows (the same links the HD and classic pages draw).

The Warlock keeps D2R's own V2 art (its cells are D2R's). The layout is not changed: it names these files already.

  py -3 -I tools/pad_skill_trees.py [build] [--preview DIR]   build into ui_paths.HD_OUT (the hd_ui.py build step), then check
  py -3 -I tools/pad_skill_trees.py check                     only the check (exit 1 on a problem)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import skill_tree_art as sta  # noqa: E402
import ui_art  # noqa: E402
from rotw_stash_legacy import lenient_json  # noqa: E402
from ui_paths import BASE_UI, HD_OUT, OUT  # noqa: E402

V2 = Path("controller/panel/spells/v2")                     # under BASE_UI (baseline) and HD_OUT (output)
LAYOUT = Path("layouts/controller/skillstreepanelhd.json")
PREFIXES = {cls: prefix for cls, (prefix, _l, _k) in sta.CLASSES.items()}
TABS = 3
STRIP_H = 125                                               # the tab highlight strip at the top of each frame
SOCKET_FROM = ("so", 0, 5, 1)                               # D2R's Sorceress, frame 0, row 6, column 2: a lone socket
SOCKET_CROP = (-2, -12, 236, 150)                           # relative to the button: socket + level box (+ margin)
SOCKET_BOX = (12, -3, 158, 139)                             # D2R's socket ring relative to the button (its outer edge)
RING_ALPHA = 100                                            # the ring's edge: alpha above this
ARROW_FROM = ("so", 0, 1)                                   # its frame 0, column 2: the arrow from row 1 down to row 2
ARROW_CROP = (50, -40, 120, -3)                             # relative to the lower cell's button: the arrow head


def layout_geometry(lay: dict | None = None) -> tuple[list[int], list[int], tuple[int, int]]:
    """(skillColumn, skillRow, where a tree frame's top left sits) of D2R's controller skill tree layout."""
    lay = lay or lenient_json((BASE_UI / LAYOUT).read_text("utf-8-sig"))
    f = lay["fields"]
    tab = next(c for c in lay["children"] if c["name"] == "Tab0")
    bg = next(c for c in tab["children"] if c["name"] == "Background")["fields"]["rect"]
    r = tab["fields"].get("rect", {})
    return f["skillColumn"], f["skillRow"], (r.get("x", 0) + bg.get("x", 0), r.get("y", 0) + bg.get("y", 0))


def d2r_frames(prefix: str) -> list[Image.Image]:
    return ui_art.read_sprite(BASE_UI / V2 / f"{prefix}skilltree.sprite")


def pieces(geo) -> tuple[Image.Image, Image.Image]:
    """(D2R's socket + level box, D2R's arrow head), cut relative to a button."""
    cols, rows, (fx, fy) = geo
    p, f, r, c = SOCKET_FROM
    src = d2r_frames(p)[f]
    x, y = cols[c] - fx, rows[r] - fy
    socket = src.crop((x + SOCKET_CROP[0], y + SOCKET_CROP[1], x + SOCKET_CROP[2], y + SOCKET_CROP[3]))
    p, f, c = ARROW_FROM
    src = d2r_frames(p)[f] if p != SOCKET_FROM[0] or f != SOCKET_FROM[1] else src
    x, y = cols[c] - fx, rows[1] - fy
    arrow = src.crop((x + ARROW_CROP[0], y + ARROW_CROP[1], x + ARROW_CROP[2], y + ARROW_CROP[3]))
    return socket, arrow


def links(cells: dict[str, tuple[int, int]], reqs: dict[str, list[str]]) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    return sta.page_arrows(cells, reqs)


def frame(d2r: Image.Image, cells, arrows, socket, arrow, geo) -> Image.Image:
    cols, rows, (fx, fy) = geo
    im = Image.new("RGBA", d2r.size)
    im.paste(d2r.crop((0, 0, d2r.width, STRIP_H)), (0, 0))
    for (ra, ca), (rb, cb) in arrows:
        if ca != cb or rb != ra + 1:
            raise ValueError(f"arrow {(ra, ca)} -> {(rb, cb)}: only links to the cell right below are drawn")
        im.alpha_composite(arrow, (cols[cb] - fx + ARROW_CROP[0], rows[rb] - fy + ARROW_CROP[1]))
    for r, c in cells:
        im.alpha_composite(socket, (cols[c] - fx + SOCKET_CROP[0], rows[r] - fy + SOCKET_CROP[1]))
    return im


def build(out: Path = HD_OUT, preview: Path | None = None) -> list[str]:
    trees, reqs = sta.load_trees(), sta.load_reqs()
    geo = layout_geometry()
    socket, arrow = pieces(geo)
    lines = []
    for cls, prefix in PREFIXES.items():
        d2r = d2r_frames(prefix)
        if len(d2r) != TABS:
            raise ValueError(f"D2R's {prefix}skilltree.sprite (V2) has {len(d2r)} frames, {TABS} expected")
        frames, n_cells, n_arrows = [], 0, 0
        for tab in range(TABS):
            cells = trees[cls].get(sta.page_of(tab), {})
            arr = links(cells, reqs)
            frames.append(frame(d2r[tab], cells.values(), arr, socket, arrow, geo))
            n_cells, n_arrows = n_cells + len(cells), n_arrows + len(arr)
        info = ui_art.dc6.sprite_info(BASE_UI / V2 / f"{prefix}skilltree.sprite")
        stride = info["strip_width"] // TABS
        dest = out / V2 / f"{prefix}skilltree.sprite"
        ui_art.write_sprite(dest, frames, stride)
        w, h = frames[0].size
        low = ui_art.dc6.sprite_info(BASE_UI / V2 / f"{prefix}skilltree.lowend.sprite")
        ui_art.write_sprite(out / V2 / f"{prefix}skilltree.lowend.sprite",
                            [f.resize((low["frame_width"], low["height"]), Image.LANCZOS) for f in frames],
                            low["strip_width"] // TABS)
        lines.append(f"{(V2 / dest.name).as_posix()}: {TABS} frames, {n_cells} sockets, {n_arrows} arrows")
        if preview:
            sh = Image.new("RGBA", (w * TABS // 3, h // 3))
            for i, f in enumerate(frames):
                sh.alpha_composite(f.resize((w // 3, h // 3), Image.LANCZOS), (i * w // 3, 0))
            ui_art.save_png(Path(preview) / f"pad_{prefix}skilltree.png", sh)
    return lines


# ---- the check --------------------------------------------------------------------------------------------------------
def socket_box(alpha: np.ndarray, x: int, y: int) -> tuple[int, int, int, int] | None:
    """The socket ring's extent (alpha > RING_ALPHA) round the button at (x, y), relative to it: across its middle row,
    and down a column just inside its left edge (the arrows run in the middle, ARROW_CROP, so they are not measured)."""
    mid = y + (SOCKET_BOX[1] + SOCKET_BOX[3]) // 2
    x0 = max(0, x - 20)
    row = np.nonzero(alpha[mid, x0:x + 180] > RING_ALPHA)[0]
    y0 = max(0, y - 20)
    colm = np.nonzero(alpha[y0:y + 170, x + SOCKET_BOX[0] + 4] > RING_ALPHA)[0]
    if not len(row) or not len(colm):
        return None
    return int(row.min() + x0 - x), int(colm.min() + y0 - y), int(row.max() + x0 - x), int(colm.max() + y0 - y)


def reference_box(geo) -> tuple[int, int, int, int]:
    """socket_box of D2R's own art at the vanilla button the socket piece is cut from (where D2R puts it)."""
    cols, rows, (fx, fy) = geo
    p, f, r, c = SOCKET_FROM
    box = socket_box(np.asarray(d2r_frames(p)[f])[..., 3], cols[c] - fx, rows[r] - fy)
    if box is None:
        raise ValueError("no socket in D2R's art where SOCKET_FROM points")
    return box


def socket_at(alpha: np.ndarray, x: int, y: int) -> bool:
    """A socket ring round the button at (x, y): opaque at its left and right edges on the middle row."""
    mid = y + (SOCKET_BOX[1] + SOCKET_BOX[3]) // 2
    return alpha[mid, x + SOCKET_BOX[0] + 2:x + SOCKET_BOX[0] + 14].max() > RING_ALPHA and         alpha[mid, x + SOCKET_BOX[2] - 14:x + SOCKET_BOX[2] - 2].max() > RING_ALPHA


def arrow_at(alpha: np.ndarray, x: int, y_lower: int) -> bool:
    """D2R's arrow head above the lower cell's button (x, y_lower): opaque at its centre line in the gap."""
    cx = x + (ARROW_CROP[0] + ARROW_CROP[2]) // 2
    return alpha[y_lower - 30:y_lower - 12, cx - 2:cx + 3].max() > 150


def check(out: Path = HD_OUT) -> list[str]:
    """Problems of the built frames: every skill's button (layout skillColumn / skillRow) inside a socket placed as D2R's own
    art places one round a vanilla button (reference_box, within 2 px), no socket without a skill, an arrow on every chain link and on no other gap."""
    problems = []
    trees, reqs = sta.load_trees(), sta.load_reqs()
    geo = layout_geometry()
    cols, rows, (fx, fy) = geo
    ref_box = reference_box(geo)
    for cls, prefix in PREFIXES.items():
        path = out / V2 / f"{prefix}skilltree.sprite"
        low = out / V2 / f"{prefix}skilltree.lowend.sprite"
        if not path.exists() or not low.exists():
            problems.append(f"missing {path.name} or its .lowend")
            continue
        ref = ui_art.dc6.sprite_info(BASE_UI / V2 / path.name)
        info = ui_art.dc6.sprite_info(path)
        if (info["frame_width"], info["height"], info["frames"]) != (ref["frame_width"], ref["height"], ref["frames"]):
            problems.append(f"{path.name}: {info['frame_width']}x{info['height']}x{info['frames']}, D2R's is "
                            f"{ref['frame_width']}x{ref['height']}x{ref['frames']}")
        lref, linfo = ui_art.dc6.sprite_info(BASE_UI / V2 / low.name), ui_art.dc6.sprite_info(low)
        if (linfo["frame_width"], linfo["height"]) != (lref["frame_width"], lref["height"]):
            problems.append(f"{low.name}: {linfo['frame_width']}x{linfo['height']}, D2R's is {lref['frame_width']}x{lref['height']}")
        for tab, im in enumerate(ui_art.read_sprite(path)):
            page = sta.page_of(tab)
            cells = trees[cls].get(page, {})
            occupied = set(cells.values())
            a = np.asarray(im)[..., 3]
            for r in range(len(rows)):
                for c in range(len(cols)):
                    x, y = cols[c] - fx, rows[r] - fy
                    has = socket_at(a, x, y)
                    if (r, c) in occupied:
                        box = socket_box(a, x, y)
                        if not has or box is None or any(abs(u - v) > 2 for u, v in zip(box, ref_box)):
                            problems.append(f"{prefix} page {page}: skill at row {r + 1} column {c + 1}: socket {box}, "
                                            f"D2R's art has {ref_box} round its button")
                    elif has:
                        problems.append(f"{prefix} page {page}: empty socket at row {r + 1} column {c + 1}")
            want = set(links(cells, reqs))
            for r in range(1, len(rows)):
                for c in range(len(cols)):
                    seen = arrow_at(a, cols[c] - fx, rows[r] - fy)
                    link = ((r - 1, c), (r, c)) in want
                    if link and not seen:
                        problems.append(f"{prefix} page {page}: no arrow from row {r} to row {r + 1}, column {c + 1}")
                    if seen and not link:
                        problems.append(f"{prefix} page {page}: arrow from row {r} to row {r + 1}, column {c + 1} without a prerequisite")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", nargs="?", default="build", choices=("build", "check"))
    ap.add_argument("--preview", type=Path)
    args = ap.parse_args(argv)
    if args.what == "build":
        for line in build(preview=args.preview):
            print(line)
    problems = check()
    for p in problems:
        print(f"PROBLEM: {p}")
    print(f"controller skill trees: {'OK' if not problems else f'{len(problems)} problem(s)'} ({OUT})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
