"""Review of the upscaled HD item pictures (lane itemart, docs/hd-icons.md "Picture review"): which of them players see
most, side-by-side sheets for the owner, and the proposal list of better pictures (switched OFF until approved).

  py -3 -I tools/item_art_review.py rank [--top N]          the upscaled pictures by how often players see them
  py -3 -I tools/item_art_review.py sheets <out_dir> [--top N]   review sheets: Median classic | current HD | candidate

Visibility of a picture (the sum over the items that show it) is built from the tables:
  drop     expected drops per kill, summed over every enabled monster row (TreasureClass1 of normal / nightmare / hell),
           through the treasureclassex tree (Picks > 0: each pick takes ItemN with ProbN / (sum + NoDrop); Picks < 0:
           ItemN ProbN times); a rough "how often it falls on the floor", not a real drop rate (no area densities)
  vendor   a vendor sells it (any <Vendor>Min / MagicMin > 0)
  cube     cubemain rows that output it
  kept     the item type is one players keep in the inventory or stash for a long time (charms, crystals, runes, gems,
           signets, the Mega Ring): seen every time the inventory opens
and ranked by score = log10(1 + 1e4 * drop) + 2 vendor + log2(1 + cube) + 2 kept + 1 for level <= 30 (base level 0
counts as low: Median's misc items are level 0).

The candidates are in tools/data/item_art_proposals.json ("enabled": false for all until the owner approves one): per
picture either a D2R HD sprite recoloured like item_reuse (`reuse`: folder, asset, hue / sat / val) or another upscale
method (`method`). Owner rule (2026-10-30): the owner sees the pictures first; item_hd uses only the entries switched
on (the file's `enabled` and the entry's: enabled_proposals), the five Rainbow Stones og1-og5 since lane itemart2.
Needs numpy and Pillow; game art is read from the extraction and written only to <out_dir> (keep it out of git).
"""
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from icon_paths import EXCEL, read_tsv  # noqa: E402

PROPOSALS = Path(__file__).resolve().parent / "data" / "item_art_proposals.json"
KEPT_TYPES = {"grtz", "asaa", "rune", "gemx", "kill", "poti", "char", "scha", "mcha", "lcha", "jewl", "ring", "amul"}
LOW_LEVEL = 30
TC_DEPTH = 40


def table(path: Path) -> list[dict]:
    head, body = read_tsv(path)
    return [dict(zip(head, r)) for r in body]


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


class TreasureClasses:
    """Expected count of every item code per draw of a treasure class (treasureclassex rows)."""

    def __init__(self, rows: list[dict]):
        self.rows = {r.get("Treasure Class", ""): r for r in rows if r.get("Treasure Class")}
        self.memo: dict[str, dict[str, float]] = {}

    def entries(self, r: dict) -> list[tuple[str, float]]:
        out = []
        for i in range(1, 11):
            item, p = r.get(f"Item{i}", ""), _num(r.get(f"Prob{i}"))
            if item and p > 0:
                out.append((item, p))
        return out

    def expect(self, tc: str, depth: int = 0) -> dict[str, float]:
        if tc in self.memo:
            return self.memo[tc]
        r = self.rows.get(tc)
        out: dict[str, float] = defaultdict(float)
        if r is None or depth > TC_DEPTH:
            return out
        self.memo[tc] = out  # a cycle (none in the tables) reads as empty
        picks, entries = int(_num(r.get("Picks")) or 1), self.entries(r)
        if picks < 0:
            weights = [(item, p) for item, p in entries]  # each entry ProbN times, in turn
        else:
            total = sum(p for _i, p in entries) + _num(r.get("NoDrop"))
            weights = [(item, picks * p / total) for item, p in entries] if total else []
        for item, w in weights:
            if item in self.rows:
                for code, n in self.expect(item, depth + 1).items():
                    out[code] += w * n
            else:
                out[item.split(",")[0]] += w
        return out


def monster_drops(monstats: list[dict], tcs: TreasureClasses) -> dict[str, float]:
    """Item code -> expected drops per kill, summed over the enabled monster rows and the three difficulties."""
    out: dict[str, float] = defaultdict(float)
    for m in monstats:
        if m.get("enabled", "1") not in ("1", "") or m.get("killable") == "0":
            continue
        for col in ("TreasureClass1", "TreasureClass1(N)", "TreasureClass1(H)"):
            if tc := m.get(col):
                for code, n in tcs.expect(tc).items():
                    out[code] += n
    return out


def vendor_sold(misc_rows: list[dict]) -> set[str]:
    return {r["code"] for r in misc_rows if r.get("code") and any(
        _num(v) > 0 for k, v in r.items() if k and (k.endswith("Min") and k[:-3].isalpha() or k.endswith("MagicMin")))}


def cube_outputs(cube: list[dict]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for r in cube:
        if r.get("enabled") != "1":
            continue
        for c in ("output", "output b", "output c"):
            if v := r.get(c, "").strip('"'):
                out[v.split(",")[0]] += 1
    return out


@dataclass
class Picture:
    key: str                  # "mxl/<inv>" / "classic/<inv>"
    folder: str
    users: list[dict] = field(default_factory=list)   # {"table", "code", "name", "type", "level"}
    drop: float = 0.0
    vendor: bool = False
    cube: int = 0
    kept: bool = False
    low: bool = False

    @property
    def score(self) -> float:
        return (math.log10(1 + 1e4 * self.drop) + 2 * self.vendor + math.log2(1 + self.cube) + 2 * self.kept
                + 1 * self.low)

    def why(self) -> str:
        bits = [f"drop {self.drop:.2g}/kill" if self.drop else "no drop"]
        if self.vendor:
            bits.append("sold")
        if self.cube:
            bits.append(f"cube x{self.cube}")
        if self.kept:
            bits.append("kept")
        if self.low:
            bits.append("low level")
        return ", ".join(bits)


def rank(pictures: dict[str, Picture], drops: dict[str, float], sold: set[str], cube: dict[str, int]) -> list[Picture]:
    for p in pictures.values():
        codes = {u["code"] for u in p.users if u["table"] in ("weapons", "armor", "misc")}
        p.drop = sum(drops.get(c, 0.0) for c in codes)
        p.vendor = bool(codes & sold)
        p.cube = sum(cube.get(c, 0) for c in codes)
        p.kept = any(u["type"] in KEPT_TYPES for u in p.users)
        p.low = any(u["table"] in ("weapons", "armor", "misc") and _num(u["level"]) <= LOW_LEVEL for u in p.users)
    return sorted(pictures.values(), key=lambda p: (-p.score, p.key))


def upscaled(plan) -> dict[str, Picture]:
    """The pictures item_hd upscales (not made from D2R's HD art) with the items that show them."""
    out = {f"{g}/{i}": Picture(f"{g}/{i}", f) for (f, g, i) in plan.needs if f"{g}/{i}" not in plan.reuse}
    by_inv = defaultdict(list)
    for k in out:
        by_inv[k.split("/", 1)[1]].append(k)
    for t in ("weapons", "armor", "misc", "uniqueitems", "setitems"):
        for r in plan.mod.get(t, []):
            code = r.get("code") or r.get("item", "")
            cols = ("invfile", "uniqueinvfile", "setinvfile") if t in ("weapons", "armor", "misc") else ("invfile",)
            for c in cols:
                for k in by_inv.get(r.get(c, "").lower(), []):
                    out[k].users.append({"table": t, "code": code, "name": r.get("name") or r.get("index", ""),
                                         "type": r.get("type", ""), "level": r.get("level") or r.get("lvl", "")})
    return out


def review_order(ranked: list[Picture], top: int, proposals: dict) -> list[tuple[int, Picture, bool]]:
    """(rank, picture, has a proposal) for the sheets: the pictures with a proposal (the top `top` and any lower one of
    the same set) in rank order, then the top ones kept as they are."""
    props = proposals.get("pictures", {})
    pos = [(n, p, True) for n, p in enumerate(ranked, 1) if p.key in props]
    keep = [(n, p, False) for n, p in enumerate(ranked[:top], 1) if p.key not in props]
    return pos + keep


def load_proposals(path: Path = PROPOSALS) -> dict:
    return json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else {"enabled": False, "pictures": {}}


def enabled_proposals(data: dict) -> dict:
    """The proposals the build may use: only those switched on one by one, and only when the file's switch is on."""
    if not data.get("enabled"):
        return {}
    return {k: v for k, v in data.get("pictures", {}).items() if v.get("enabled")}


def report_entry(data: dict) -> dict:
    """The proposals for item_hd_report.json: what each would change and whether it is used (only when switched on)."""
    on = enabled_proposals(data)
    out = {}
    for k, v in sorted(data.get("pictures", {}).items()):
        r = v.get("reuse")
        if r:
            what = f"D2R {r['folder']}/{r['asset']}" + (", colours by position" if r.get("colour") == "by position" else "")
        else:
            what = f"upscale {v.get('method')}"
        out[k] = f"{what} ({'ON' if k in on else 'off: owner review'})"
    return out


def build_ranking():
    import item_hd
    plan = item_hd.build()
    plan.run()
    tcs = TreasureClasses(table(EXCEL / "treasureclassex.txt"))
    drops = monster_drops(table(EXCEL / "monstats.txt"), tcs)
    ranked = rank(upscaled(plan), drops, vendor_sold(plan.mod["misc"]), cube_outputs(table(EXCEL / "cubemain.txt")))
    return plan, ranked


def main(argv: list[str]) -> int:
    top = 25
    if "--top" in argv:
        i = argv.index("--top")
        top = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if argv[:1] == ["rank"]:
        _plan, ranked = build_ranking()
        for n, p in enumerate(ranked[:top] if top else ranked, 1):
            names = sorted({u["name"] for u in p.users})
            print(f"{n:3} {p.score:5.2f} {p.key:24} {len(p.users):3} items  {p.why():40}  {', '.join(names[:3])}"
                  + (" ..." if len(names) > 3 else ""))
        return 0
    if argv[:1] == ["sheets"] and len(argv) == 2:
        import item_art_sheets
        plan, ranked = build_ranking()
        props = load_proposals()
        return item_art_sheets.write_all(Path(argv[1]), plan, review_order(ranked, top, props), props)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
