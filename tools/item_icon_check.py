"""Check that every inventory-picture reference of the mod's item tables resolves to an HD sprite.

References: invfile / uniqueinvfile / setinvfile of weapons, armor, misc, and invfile of uniqueitems and setitems.
  - an invfile the mod ships a DC6 for must have its HD sprite (mxl/<invfile>.sprite + .lowend.sprite, right size,
    matching the DC6's opaque fraction and colour) and every item that uses it must point at it; a picture made from
    D2R's HD sprite (item_hd_report.json "hd_reuse", tools/item_reuse.py) is D2R's art, so it is held to the looser
    REUSE_* limits, and an exact one may point at D2R's asset itself ("hd_reuse_direct"); a picture made from a picture
    proposal switched on ("proposal_on", tools/data/item_art_proposals.json) is the owner-approved candidate, so it must
    be that candidate pixel for pixel (item_art_sheets.candidate at its size and cell; lane itemart3: several approved
    D2R pictures have another outline than Median's, e.g. coins for Fool's Gold, and fail any classic-look limit)
  - an invfile with only a D2R classic DC6 resolves through D2R's HD asset or a converted classic/<invfile> sprite
  - an invfile with no DC6 in the mod or in D2R is unresolved (reported with its rows)
  - every base item code / unique / set name is in items.json / uniques.json / sets.json and its asset is a D2R sprite
    or a generated one; items that only got an approximate picture (item_hd "fallback") are counted as gaps
Usage: py -3 -I tools/item_icon_check.py   (reads work/hd from tools/item_hd.py; writes work/hd/item_icon_check.json; exit 1 on
a broken sprite, a missing asset or a mod picture that is not used - unresolved invfiles and fallbacks are reported, not failed)
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dc6 import decode_frame, palette, read_dc6, read_sprite, scale, sprite_info, stats  # noqa: E402
from icon_paths import BASE, EXCEL, HD_OUT, OUT  # noqa: E402
from item_art import CELL_CLASSIC, CELL_HD, CELL_LOW, D2R_ITEMS, MOD_ITEMS  # noqa: E402
from item_hd import TABLES, key, load_map, rows, sprite_set  # noqa: E402

FRACTION_LIMIT = 0.03
COLOUR_LIMIT = 4.0
REUSE_FRACTION_LIMIT, REUSE_COLOUR_LIMIT = 0.15, 25.0  # D2R's HD redraw of the picture against the classic one
REF_COLUMNS = {"weapons": ("invfile", "uniqueinvfile", "setinvfile"), "armor": ("invfile", "uniqueinvfile", "setinvfile"),
               "misc": ("invfile", "uniqueinvfile"), "uniqueitems": ("invfile",), "setitems": ("invfile",)}


def references(tables: dict[str, list[dict]]) -> dict[str, list[str]]:
    """invfile (lowercase) -> the rows that name it."""
    out = defaultdict(list)
    for t, cols in REF_COLUMNS.items():
        for r in tables.get(t, []):
            for c in cols:
                if r.get(c):
                    out[r[c].lower()].append(f"{t} {r.get('code') or r.get('index') or r.get('name')} ({c})")
    return out


def check_sprite(path: Path, dc6: Path, pal: list, cell: int, reused: bool = False) -> list[str]:
    """Problems of one generated item sprite against its DC6 ([] when fine); `reused`: made from D2R's HD sprite."""
    if not path.exists():
        return [f"{path.name}: missing"]
    info = sprite_info(path)
    w, h, _x, _y, blk = read_dc6(dc6)[0]
    if info["frames"] != 1 or info["frame_width"] != info["strip_width"]:
        return [f"{path.name}: not a single frame"]
    cw, ch = info["strip_width"] // cell, info["height"] // cell
    if info["strip_width"] % cell or info["height"] % cell or cw * CELL_CLASSIC < w or ch * CELL_CLASSIC < h:
        return [f"{path.name}: size {info['strip_width']}x{info['height']} is not whole cells that hold the {w}x{h} picture"]
    want = stats(scale(decode_frame(w, h, blk, pal, fill=True), info["strip_width"], info["height"], cell / CELL_CLASSIC))
    got = stats(read_sprite(path)[0])
    fl, cl = (REUSE_FRACTION_LIMIT, REUSE_COLOUR_LIMIT) if reused else (FRACTION_LIMIT, COLOUR_LIMIT)
    if abs(want[0] - got[0]) > fl or max(abs(a - b) for a, b in zip(want[1:], got[1:])) > cl:
        return [f"{path.name}: differs from the DC6"]
    return []


def check_proposal_sprite(path: Path, dc6: Path, pal: list, cell: int, prop: dict, hd_items: Path) -> list[str]:
    """Problems of a sprite made from a proposal switched on: whole cells, and pixel for pixel the approved candidate."""
    import numpy as np
    import item_art_sheets
    import upscale
    if not path.exists():
        return [f"{path.name}: missing"]
    info = sprite_info(path)
    if info["frames"] != 1 or info["strip_width"] % cell or info["height"] % cell:
        return [f"{path.name}: size {info['strip_width']}x{info['height']} is not one frame of whole cells"]
    w, h, _x, _y, blk = read_dc6(dc6)[0]
    want, _label = item_art_sheets.candidate(prop, upscale.rows_to_array(decode_frame(w, h, blk, pal, fill=True)),
                                             info["strip_width"], info["height"], hd_items, cell)
    got = upscale.rows_to_array(read_sprite(path)[0])
    if got.shape != want.shape or np.abs(got.astype(int) - want.astype(int)).max() > 0:
        return [f"{path.name}: not the approved proposal picture"]
    return []


def check_items(tables: dict[str, list[dict]], items: dict, uniques: dict, sets: dict, have: set[str], mod_dc6: set[str],
                d2r_dc6: set[str], out_dir: Path = HD_OUT, direct: dict[str, str] | None = None) -> dict:
    """Pure part of the check (the sprite pixels are checked by check_sprite). `direct`: invfile -> "folder/asset" of D2R
    that the mod's exact copy of a vanilla picture points at instead of mxl/<invfile>."""
    direct = direct or {}

    def own(folder: str, inv: str, asset: str) -> bool:
        return asset == f"mxl/{inv}" or direct.get(inv) == f"{folder}/{asset}"
    refs = references(tables)
    folder_of = {}
    for t, folder in TABLES.items():
        for r in tables.get(t, []):
            if r.get("code"):
                folder_of.setdefault(r["code"], (folder, t, r))

    def asset_ok(folder: str, asset: str) -> bool:
        a = f"{folder}/{asset}".lower()
        return a in have or ((out_dir / "global" / "ui" / "items" / folder / f"{asset}.sprite").exists()
                             and (out_dir / "global" / "ui" / "items" / folder / f"{asset}.lowend.sprite").exists())

    problems: list[str] = []
    unresolved = {i: r for i, r in refs.items() if i not in mod_dc6 and i not in d2r_dc6}
    kinds = {"mod": sum(i in mod_dc6 for i in refs), "d2r classic": sum(i not in mod_dc6 and i in d2r_dc6 for i in refs),
             "none": len(unresolved)}
    # base items
    unmapped = [c for c in folder_of if c not in items]
    bad_asset = [f"{c}: {items[c]['asset']}" for c, (f, _t, _r) in folder_of.items() if c in items and not asset_ok(f, items[c]["asset"])]
    own_wrong = [c for c, (f, _t, r) in folder_of.items() if c in items and r.get("invfile", "").lower() in mod_dc6
                 and not own(f, r["invfile"].lower(), items[c]["asset"])]
    # uniques / sets (name key -> entry; the key's folder is its base item's)
    sp_problems, seen, repeated = [], set(), []
    for txt, mapping, code_col in (("uniqueitems", uniques, "code"), ("setitems", sets, "item")):
        for r in tables.get(txt, []):
            name = r.get("index", "")
            folder = folder_of.get(r.get(code_col, ""), (None,))[0]
            if not name or not folder:
                continue
            if (txt, key(name)) in seen:  # the maps are keyed by name: the first row of a repeated name decides
                repeated.append(f"{txt} {name!r}")
                continue
            seen.add((txt, key(name)))
            e = mapping.get(key(name))
            if e is None:
                sp_problems.append(f"{txt} {name!r}: not in the map")
            elif not all(asset_ok(folder, a) for a in e.values()):
                sp_problems.append(f"{txt} {name!r}: asset missing ({e['normal']})")
            elif r.get("invfile", "").lower() in mod_dc6 and not own(folder, r["invfile"].lower(), e["normal"]):
                sp_problems.append(f"{txt} {name!r}: does not use the mod's {r['invfile']}")
    return {"references": len(refs), "kinds": kinds, "unresolved": {i: r for i, r in sorted(unresolved.items())},
            "unmapped_codes": unmapped, "bad_assets": bad_asset, "mod_art_not_used": own_wrong, "special_problems": sp_problems,
            "repeated_names": repeated,
            "problems": problems}


def main() -> int:
    names = ("weapons", "armor", "misc", "uniqueitems", "setitems")
    tables = {n: rows(EXCEL / f"{n}.txt") for n in names}
    maps = {n: load_map(HD_OUT / "items" / f"{n}.json") for n in ("items", "uniques", "sets")}
    mod_dc6 = {p.stem.lower() for p in MOD_ITEMS.glob("*.dc6")}
    d2r_dc6 = {p.stem.lower() for p in D2R_ITEMS.glob("*.dc6")}
    hd_report = json.loads((OUT / "item_hd_report.json").read_text("utf-8")) if (OUT / "item_hd_report.json").exists() else {}
    reused = set(hd_report.get("hd_reuse", {}))  # D2R's HD art
    copies = dict(hd_report.get("variant_copies", []))  # "<group>/<inv><n>" -> "<group>/<inv>"
    import fxpaths
    from item_art_review import enabled_proposals, load_proposals
    proposals = {k: v for k, v in enabled_proposals(load_proposals()).items() if k in set(hd_report.get("proposal_on", []))}
    hd_items = fxpaths.D2R_DATA / "hd" / "global" / "ui" / "items"
    report = check_items(tables, maps["items"], maps["uniques"], maps["sets"], sprite_set(BASE / "filelist.txt"), mod_dc6, d2r_dc6,
                         direct=hd_report.get("hd_reuse_direct", {}))
    pal = palette(BASE / "palette" / "pal.dat")
    sprite_problems, checked = [], 0
    for folder_dir in sorted((HD_OUT / "global" / "ui" / "items").glob("*/*")):
        group = {"mxl": MOD_ITEMS, "classic": D2R_ITEMS}.get(folder_dir.name)
        if group is None:
            continue
        for sp in sorted(folder_dir.glob("*.sprite")):
            low = sp.name.endswith(".lowend.sprite")
            inv = sp.name[:-len(".lowend.sprite" if low else ".sprite")]
            checked += 1
            k = f"{folder_dir.name}/{inv}"
            if k in copies:  # a VarInvGfx variant (item_hd, bugs.md #513): the same bytes as its picture
                base = folder_dir / sp.name.replace(inv, copies[k].split("/", 1)[1], 1)
                if not base.exists() or base.read_bytes() != sp.read_bytes():
                    sprite_problems.append(f"{sp}: variant copy differs from {base.name}")
            elif k in proposals:
                sprite_problems += check_proposal_sprite(sp, group / f"{inv}.dc6", pal, CELL_LOW if low else CELL_HD,
                                                         proposals[k], hd_items)
            else:
                sprite_problems += check_sprite(sp, group / f"{inv}.dc6", pal, CELL_LOW if low else CELL_HD, k in reused)
    report.update({"sprites_checked": checked, "sprite_problems": sprite_problems})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "item_icon_check.json").write_text(json.dumps(report, indent=1), "utf-8")
    fb = hd_report.get("fallback", [])
    print(f"item icons: {report['references']} invfiles referenced ({report['kinds']['mod']} mod DC6, {report['kinds']['d2r classic']} "
          f"D2R classic, {report['kinds']['none']} with no DC6); {checked} sprites checked, {len(sprite_problems)} sprite problems; "
          f"unmapped codes {len(report['unmapped_codes'])}, missing assets {len(report['bad_assets'])}, mod art not used "
          f"{len(report['mod_art_not_used'])}, unique/set problems {len(report['special_problems'])} (repeated names skipped: {len(report['repeated_names'])}); fallbacks {len(fb)}")
    for i, r in report["unresolved"].items():
        print(f"  unresolved invfile {i!r}: {', '.join(r[:4])}")
    bad = sprite_problems or report["unmapped_codes"] or report["bad_assets"] or report["mod_art_not_used"] or report["special_problems"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
