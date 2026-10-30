"""HD inventory pictures for the mod's items: sprites + data/hd/items/{items,uniques,sets}.json (adapted from another
port's item_hd.py, which was written for another Median XL release's tables).

D2R draws an item in HD from three maps under data/hd/items/: items.json (base item code -> asset), uniques.json and
sets.json (unique / set item name -> asset for its normal, exceptional and elite base). The name key is the
uniqueitems/setitems `index` lowercased, spaces and hyphens as "_", apostrophes dropped ("Buriza-Do Kyanon" ->
"buriza_do_kyanon"). An asset is a path under data/hd/global/ui/items/<weapon|armor|misc>/, the folder being the base
item's table. The mod's item codes are almost all new (903 of 921 weapon codes are not D2R's), so every item gets a
picture by its *invfile* (the classic picture the item shows), in this order:

  mod        the invfile's DC6 is in the mod's MPQ (99 pictures): converted to HD (item_art: mxl/<invfile>)
  same code  D2R has this code in the same table with the same invfile: D2R's own entry
  invfile    a D2R item of the same table with the same invfile (the same classic picture): its HD asset
  classic    D2R has the classic DC6 of that invfile but no HD asset maps to it: D2R's DC6 converted (classic/<invfile>)
  fallback   no picture for the invfile at all (blank, or no DC6 anywhere): the most common asset of the same item type,
             of its nearest parent type (itemtypes Equiv1/2), or of the table - an APPROXIMATION, listed in the report
Unique and set items use the invfile of their row, else the base item's uniqueinvfile / setinvfile, else its invfile, with
one more first step: D2R's own entry of the same name when its invfile is the same.
The mod's art always wins over D2R's: an invfile the mod ships a DC6 for (even one D2R also has: invrvex) is converted.
A converted picture (mod or classic) that is vanilla art (tools/item_reuse.py: exact, recolour or rescale of a D2R
picture that has an HD sprite) is made from D2R's HD sprite instead of an upscale; an exact one whose D2R sprite has the
right folder and size is not written at all, the map points at D2R's asset ("mod: D2R HD").

Output: work/hd/data/hd/items/{items,uniques,sets}.json, work/hd/data/hd/global/ui/items/** sprites,
work/hd/item_hd_report.json (every item with its method, the fallbacks, unresolved invfiles).
Usage: py -3 -I tools/item_hd.py
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dc6 import palette, read_dc6  # noqa: E402
from icon_paths import BASE, EXCEL, HD_OUT, OUT, read_tsv  # noqa: E402
from item_art import CELL_HD, D2R_ITEMS, MOD_ITEMS, asset_size, make_asset  # noqa: E402

TABLES = {"weapons": "weapon", "armor": "armor", "misc": "misc"}
# Last resort per table (misc's most common picture is Mephisto's key, which would mislead): a neutral small item
DEFAULTS = {"misc": "charm/charm_small"}


def rows(path: Path) -> list[dict]:
    head, body = read_tsv(path)
    return [dict(zip(head, r)) for r in body]


def key(index: str) -> str:
    return re.sub(r"[ \-]", "_", index.lower()).replace("'", "")


def load_map(path: Path) -> dict:
    return {k: v for e in json.loads(path.read_text("utf-8-sig")) for k, v in e.items()}


def sprite_set(filelist: Path) -> set[str]:
    """'weapon/axe/hand_axe' for every HD inventory sprite D2R has."""
    out = set()
    for line in filelist.read_text("utf-8").splitlines():
        if m := re.fullmatch(r"(?:data:)?data/hd/global/ui/items/(.+)\.sprite", line.strip().lower()):
            if not m[1].endswith(".lowend"):
                out.add(m[1])
    return out


def cells(r: dict) -> tuple[int, int]:
    def num(v: str) -> int:
        return int(v) if v and v.strip().isdigit() else 1
    return num(r.get("invwidth", "")), num(r.get("invheight", ""))


class Plan:
    """What the item pictures are: items/uniques/sets maps plus the sprites to convert (no file is written here)."""

    def __init__(self, mod: dict[str, list[dict]], d2r: dict[str, list[dict]], d2r_maps: dict[str, dict],
                 d2r_sprites: set[str], mod_dc6: set[str], d2r_dc6: set[str], mod_types: list[dict],
                 reuse: dict | None = None, hd_items: Path | None = None, dc6_size=None):
        """reuse: "mxl/<inv>" / "classic/<inv>" -> item_reuse.Match; hd_items: D2R's data/hd/global/ui/items;
        dc6_size(group, inv) -> (w, h) of the picture (for the size test of a direct reuse)."""
        self.mod, self.d2r, self.maps, self.have = mod, d2r, d2r_maps, set(d2r_sprites)
        self.reuse, self.hd_items, self.dc6_size = reuse or {}, hd_items, dc6_size
        self.direct: dict[str, str] = {}  # invfile -> D2R asset (folder/asset) an exact mod picture points at
        self.mod_dc6, self.d2r_dc6 = mod_dc6, d2r_dc6
        self.needs: dict[tuple[str, str, str], tuple[int, int]] = {}  # (folder, group, invfile) -> cells
        self.how: Counter = Counter()
        self.report: dict[str, list] = defaultdict(list)
        self.items: dict[str, dict] = {}
        self.repeats: dict[tuple[str, str], int] = {}  # (table, name key) -> rows of that name with another picture
        self.folder_of: dict[str, str] = {}
        self.inv_of: dict[str, str] = {}
        self.cells_of: dict[str, tuple[int, int]] = {}
        self.parents = {r.get("Code", "").lower(): [r.get("Equiv1", "").lower(), r.get("Equiv2", "").lower()]
                        for r in mod_types if r.get("Code")}
        self._index_d2r()

    # -- D2R baseline ---------------------------------------------------------------------------------
    def exists(self, folder: str, asset: str) -> bool:
        return f"{folder}/{asset}".lower() in self.have

    def _index_d2r(self) -> None:
        self.d2r_code: dict[tuple[str, str], str] = {}  # (folder, code) -> invfile
        self.by_inv: dict[tuple[str, str], Counter] = defaultdict(Counter)
        self.by_type: dict[tuple[str, str], Counter] = defaultdict(Counter)
        self.by_table: dict[str, Counter] = defaultdict(Counter)
        d_items = self.maps["items"]
        for table, folder in TABLES.items():
            for r in self.d2r.get(table, []):
                code = r.get("code", "")
                asset = d_items.get(code, {}).get("asset")
                if not code or not asset or not self.exists(folder, asset):
                    continue
                inv = r.get("invfile", "").lower()
                self.d2r_code[folder, code] = inv
                self.by_inv[folder, inv][asset] += 1
                self.by_type[folder, r.get("type", "").lower()][asset] += 1
                self.by_table[folder][asset] += 1
        # D2R's own unique / set entries: name key -> (folder, invfile)
        self.d2r_special: dict[str, dict[str, tuple[str, str]]] = {"uniqueitems": {}, "setitems": {}}
        self.special_by_inv: dict[str, dict[tuple[str, str], str]] = {"uniqueitems": {}, "setitems": {}}
        base = {x.get("code"): (f, x) for t, f in TABLES.items() for x in self.d2r.get(t, [])}
        for txt, mapping, code_col, base_col in (("uniqueitems", self.maps["uniques"], "code", "uniqueinvfile"),
                                                 ("setitems", self.maps["sets"], "item", "setinvfile")):
            for r in self.d2r.get(txt, []):
                entry = mapping.get(key(r.get("index", "")))
                folder, brow = base.get(r.get(code_col), (None, {}))
                own = (r.get("invfile") or brow.get(base_col, "")).lower()  # a picture of its own, not the base item's
                inv = own or brow.get("invfile", "").lower()
                if entry and folder:
                    self.d2r_special[txt][key(r["index"])] = (folder, inv)
                    if own and self.exists(folder, entry["normal"]):
                        self.special_by_inv[txt].setdefault((folder, own), entry["normal"])

    # -- invfile resolution ---------------------------------------------------------------------------
    def want(self, folder: str, group: str, inv: str, size: tuple[int, int]) -> str:
        """Registers a sprite to convert (the biggest cell size of its users) and returns its asset name."""
        k = (folder, group, inv)
        old = self.needs.get(k, (1, 1))
        self.needs[k] = (max(old[0], size[0]), max(old[1], size[1]))
        self.have.add(f"{folder}/{group}/{inv}")
        return f"{group}/{inv}"

    def by_invfile(self, folder: str, inv: str, size: tuple[int, int]) -> tuple[str, str] | None:
        """(asset, how) when the invfile has a picture of its own: the mod's, D2R's HD one, or D2R's classic one."""
        if not inv:
            return None
        if inv in self.mod_dc6:
            if (m := self.reuse.get(f"mxl/{inv}")) and self.dc6_size:
                import item_reuse
                cw, ch = asset_size(*self.dc6_size("mxl", inv), *size)
                if item_reuse.direct(m, folder, (cw * CELL_HD, ch * CELL_HD), self.hd_items):
                    self.direct[inv] = f"{folder}/{m.asset}"
                    return m.asset, "mod: D2R HD"
            return self.want(folder, "mxl", inv, size), "mod"
        if c := self.by_inv.get((folder, inv)):
            return c.most_common(1)[0][0], "invfile"
        for txt in ("uniqueitems", "setitems"):  # the invfile is a D2R unique's / set item's picture
            if a := self.special_by_inv[txt].get((folder, inv)):
                return a, "invfile"
        if inv in self.d2r_dc6:
            return self.want(folder, "classic", inv, size), "classic"
        return None

    def ancestors(self, t: str) -> list[str]:
        out, todo = [], list(self.parents.get(t, []))
        while todo:
            p = todo.pop(0)
            if p and p not in out:
                out.append(p)
                todo += self.parents.get(p, [])
        return out

    def fallback(self, folder: str, type_: str) -> tuple[str, str]:
        if c := self.by_type.get((folder, type_)):
            return c.most_common(1)[0][0], "fallback: same item type"
        if c := next((self.by_type[folder, t] for t in self.ancestors(type_) if (folder, t) in self.by_type), None):
            return c.most_common(1)[0][0], "fallback: parent item type"
        return DEFAULTS.get(folder) or self.by_table[folder].most_common(1)[0][0], "fallback: table default"

    # -- the three maps -------------------------------------------------------------------------------
    def base_items(self) -> None:
        d_items = self.maps["items"]
        for table, folder in TABLES.items():
            for r in self.mod.get(table, []):
                code = r.get("code", "")
                if not code or code in self.items:
                    continue
                inv, size = r.get("invfile", "").lower(), cells(r)
                self.folder_of[code], self.inv_of[code], self.cells_of[code] = folder, inv, size
                asset = d_items.get(code, {}).get("asset")
                if (found := self.by_invfile(folder, inv, size)) and found[1] == "mod":
                    asset, how = found
                elif asset and self.d2r_code.get((folder, code)) == inv and self.exists(folder, asset):
                    how = "same code"
                elif found:
                    asset, how = found
                else:
                    asset, how = self.fallback(folder, r.get("type", "").lower())
                    self.report["fallback"].append(
                        f"{table} {code} {r.get('name', '')!r}: invfile {inv!r} has no picture -> {asset} ({how})")
                self.items[code] = {"asset": asset}
                self.how[f"items: {how}"] += 1
                if inv and not inv in self.mod_dc6 | self.d2r_dc6:
                    self.report["no_dc6"].append(f"{table} {code} {r.get('name', '')!r}: invfile {inv!r}")

    def specials(self, txt: str, mapping: dict, code_col: str, label: str, base_col: str) -> list[dict]:
        out, seen = [], {}
        for r in self.mod.get(txt, []):
            name, code = r.get("index", ""), r.get(code_col, "")
            k, folder = key(name), self.folder_of.get(code)
            if not name or not folder:
                continue
            base = self.base_row.get(code, {})
            own = (r.get("invfile") or base.get(base_col, "")).lower()
            inv = own or base.get("invfile", "").lower()
            if k in seen:  # the maps are keyed by name: the first row of a repeated name decides
                self.repeats[txt, k] = self.repeats.get((txt, k), 0) + (seen[k] != (folder, inv))
                continue
            seen[k] = (folder, inv)
            size = self.cells_of.get(code, (1, 1))
            entry = mapping.get(k)
            found = self.by_invfile(folder, inv, size)
            if found and found[1] == "mod":
                asset, how = found
            elif entry and self.d2r_special[txt].get(k) == (folder, inv) and all(self.exists(folder, a) for a in entry.values()):
                asset, how = entry["normal"], "same name"
            elif own and (a := self.special_by_inv[txt].get((folder, inv))):
                asset, how = a, "unique invfile"
            elif found:
                asset, how = found
            else:
                asset, how = self.items[code]["asset"], "base item"
                self.report["fallback"].append(f"{txt} {name!r}: invfile {inv!r} has no picture -> the base item's {asset}")
            if inv and inv not in self.mod_dc6 | self.d2r_dc6:
                self.report["no_dc6"].append(f"{txt} {name!r}: invfile {inv!r}")
            out.append({k: {"normal": asset, "uber": asset, "ultra": asset}})
            self.how[f"{label}: {how}"] += 1
        return out

    def run(self) -> tuple[list[dict], list[dict], list[dict]]:
        self.base_row = {x["code"]: x for t in TABLES for x in reversed(self.mod.get(t, [])) if x.get("code")}
        self.base_items()
        uniques = self.specials("uniqueitems", self.maps["uniques"], "code", "uniques", "uniqueinvfile")
        sets = self.specials("setitems", self.maps["sets"], "item", "sets", "setinvfile")
        for txt in ("uniqueitems", "setitems"):
            names = [k for t, k in self.repeats if t == txt]
            self.report[f"repeated_names_{txt}"] = [f"{len(names)} names repeat on several rows, "
                                                    f"{sum(1 for k in names if self.repeats[txt, k])} of them with another picture "
                                                    f"(the first row's picture is used for all)"]
        return [{c: v} for c, v in self.items.items()], uniques, sets


def generate(plan: Plan, pal: list, hd_root: Path = HD_OUT) -> Counter:
    """Writes the sprites the plan asked for and removes earlier generated ones (mxl/, classic/) it no longer asks for."""
    n = Counter()
    keep = {(f, g, i) for f, g, i in plan.needs}
    for f in TABLES.values():
        for g in ("mxl", "classic"):
            for sp in sorted((hd_root / "global" / "ui" / "items" / f / g).glob("*.sprite")):
                if (f, g, sp.name.split(".")[0]) not in keep:
                    sp.unlink()
                    n["stale removed"] += 1
    for (folder, group, inv), (cw, ch) in sorted(plan.needs.items()):
        m = plan.reuse.get(f"{group}/{inv}")
        if make_asset(group, inv, folder, cw, ch, pal, hd_root, reuse=m, hd_items=plan.hd_items):
            n[f"{group} from D2R HD" if m else f"{group} upscaled"] += 1
        else:
            plan.report["missing_dc6"].append(f"{group}/{inv}")
    return n


def write_maps(items: list, uniques: list, sets: list, hd_root: Path = HD_OUT) -> None:
    out = hd_root / "items"
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("items", items), ("uniques", uniques), ("sets", sets)):
        (out / f"{name}.json").write_text("[\n" + ",\n".join("  " + json.dumps(e) for e in data) + "\n]\n", encoding="utf-8")


def find_reuse(plan: Plan) -> dict:
    """item_reuse matches of the mod's pictures and of the referenced D2R classic pictures without an HD sprite, against
    every D2R classic picture that has one."""
    import item_reuse
    library = {}
    for (folder, inv), c in sorted(plan.by_inv.items()):
        library.setdefault(inv, (folder, c.most_common(1)[0][0]))
    for txt in ("uniqueitems", "setitems"):
        for (folder, inv), a in sorted(plan.special_by_inv[txt].items()):
            library.setdefault(inv, (folder, a))
    refs = {r.get(c, "").lower() for t in plan.mod.values() for r in t
            for c in ("invfile", "uniqueinvfile", "setinvfile")} - {""}
    sources = {f"mxl/{i}": MOD_ITEMS / f"{i}.dc6" for i in sorted(plan.mod_dc6)}
    sources |= {f"classic/{i}": D2R_ITEMS / f"{i}.dc6" for i in sorted(refs & plan.d2r_dc6 - plan.mod_dc6 - set(library))}
    return item_reuse.find(sources, library, D2R_ITEMS)


def proposals_report() -> dict:
    """tools/data/item_art_proposals.json as listed in the report (lane itemart; not used by the build yet)."""
    import item_art_review
    return item_art_review.report_entry(item_art_review.load_proposals())


def build() -> Plan:
    import fxpaths
    names = ("weapons", "armor", "misc", "uniqueitems", "setitems")
    d2r_maps = {n: load_map(BASE / "hd-items" / f"{n}.json") for n in ("items", "uniques", "sets")}
    hd_items = fxpaths.D2R_DATA / "hd" / "global" / "ui" / "items"

    def dc6_size(group: str, inv: str) -> tuple[int, int]:
        return read_dc6((MOD_ITEMS if group == "mxl" else D2R_ITEMS) / f"{inv}.dc6")[0][:2]
    plan = Plan({n: rows(EXCEL / f"{n}.txt") for n in names}, {n: rows(BASE / "excel" / f"{n}.txt") for n in names},
                d2r_maps, sprite_set(BASE / "filelist.txt"),
                {p.stem.lower() for p in MOD_ITEMS.glob("*.dc6")}, {p.stem.lower() for p in D2R_ITEMS.glob("*.dc6")},
                rows(EXCEL / "itemtypes.txt"), hd_items=hd_items, dc6_size=dc6_size)
    if hd_items.is_dir():
        plan.reuse = find_reuse(plan)
    else:
        plan.report["notes"].append(f"no D2R HD item sprites at {hd_items}: every picture is upscaled")
    return plan


def main() -> int:
    plan = build()
    items, uniques, sets = plan.run()
    n = generate(plan, palette(BASE / "palette" / "pal.dat"))
    write_maps(items, uniques, sets)
    bad = [c for e in items for c, v in e.items() if not plan.exists(plan.folder_of[c], v["asset"])]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "item_hd_report.json").write_text(json.dumps(
        {"items": len(items), "uniques": len(uniques), "sets": len(sets), "how": dict(sorted(plan.how.items())),
         "sprites": dict(n), "missing_assets": bad,
         "hd_reuse": {k: m.label() for k, m in sorted(plan.reuse.items())}, "hd_reuse_direct": plan.direct,
         "picture_proposals": proposals_report(),
         **plan.report}, indent=1), "utf-8")
    print(f"items.json {len(items)}, uniques.json {len(uniques)}, sets.json {len(sets)}; sprites: "
          + ", ".join(f"{k} {v}" for k, v in sorted(n.items())) + "; " + ", ".join(f"{k} {v}" for k, v in sorted(plan.how.items())))
    print(f"pictures that are vanilla art, made from D2R's HD sprite: {len(plan.reuse)} "
          f"({len(plan.direct)} used directly); fallbacks {len(plan.report['fallback'])}, invfiles without a DC6 {len(plan.report['no_dc6'])}, missing assets {len(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
