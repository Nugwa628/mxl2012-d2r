"""Median XL 2012's look on its 8 retextured maps in HD: a light of each map's own colour (docs/maps-hd.md "Median's look").

Measured (lane maptint, `measure`): Median's 51 retextured .dt1 are **not recoloured**. Every pixel matches its stock
donor's at the same place within a few RGB steps (mean 0.3 - 5.9 of 441, no pixel more than 24 off in the walls and floors
the maps use); what changed is the palette index. Median moved each tile onto the 226 palette entries that the five act
palettes share (the donors draw up to 46% of their pixels with act-only entries), so a tile set looks the same in any act.
D2R's wall models, which tools/walls_hd.py places, already have the donors' colours.

What makes the maps look like Median in legacy mode (G) is their light: the maps place invisible light monsters
(`idleredlight`, `idlegreenlight`, `idlebluelight`, `idleyellowlight`, monstats2 Light 4-7 with a colour) and Act 5 light
the cathedral, so classic shows cypherpunk in indigo neon, glados in teal, charismatic in cool lavender and macumba in dim
sepia. D2R HD lights every map of a biome with that biome's directional key light (data/hd/env/vis/*.json,
`global_key_light`: white for the Fortress, warm grey for the Mesa and Docktown) and shows none of that.

The build gives each of the 8 maps a biome of its own (`mxl2012_tint_<map>`: a copy of the biome its scene uses, the floor
biomes of maps_hd included) whose visual data is one copy of that biome's day file with the key light in the map's colour and
power (`TINTS`). Every time-of-day slot names that one file, so the map keeps its look at any hour. The light only reaches
what the key light lights (lightMask 9: the scene and the ground); the player, monster and item lights are unchanged.

  py -3 -I tools/map_tint.py measure [--out DIR]   retexture against donor per .dt1 and per map -> DIR/map_tint.md
  py -3 -I tools/map_tint.py docs [FILE]           refresh the generated table in docs/maps-hd.md

The build step is `apply()`, called by tools/walls_hd.py build for each map it writes. D2R's biomes, visual data and act
palettes are read through tools/fxpaths.py d2r_file (the extraction or the shared cache); nothing of D2R's goes into the repo.
"""
import argparse
import collections
import colorsys
import copy
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
PREFIX = "mxl2012_tint_"
BIOME = "data/hd/env/biome/%s.json"
VIS = "data/hd/env/vis/%s.json"
KEY_LIGHT = "global_key_light"
FAR = 24          # RGB distance counted as a visible change of a pixel (measure)
DOCS_BEGIN, DOCS_END = "<!-- map_tint:begin (generated: py -3 -I tools/map_tint.py docs) -->", "<!-- map_tint:end -->"


class Tint:
    """The key light of a map: colour (0..1, applied as the light's colour) and the factor on the base light's power."""
    __slots__ = ("rgb", "power", "classic")

    def __init__(self, rgb, power, classic):
        self.rgb, self.power, self.classic = tuple(rgb), power, classic


# The light colour of each map in classic (legacy mode, G; brightest channel 1.0, the brightness is in the power), read from lane hdwalls2's classic shots and Median's own light
# monsters in each map; checked against legacy in game (docs/testing.md "Lane maptint"). Power: classic is darker than HD
# where its light is a few coloured spots in the dark (macumba, borgir), brighter where Act 5's light floods the cathedral.
TINTS = {
    "expansion/dystopic/desertpeak.ds1": Tint((1.0, 0.80, 0.45), 0.8, "dark gold, green glow on the floor rings"),
    "expansion/ghetto/cypherpunk.ds1": Tint((0.65, 0.42, 1.0), 0.9, "indigo with magenta neon"),
    "expansion/glados/glados.ds1": Tint((0.45, 0.85, 1.0), 1.0, "teal / cyan"),
    "expansion/neonmile/downtown.ds1": Tint((1.0, 0.58, 0.42), 0.9, "red-orange brick, green neon near the crowds"),
    "expansion/redsquare/moskvich.ds1": Tint((1.0, 0.72, 0.42), 1.0, "warm orange"),
    "expansion/terror/borgir.ds1": Tint((0.62, 1.0, 0.97), 0.5, "dark, teal floor lattice, yellow torches"),
    "expansion/voodoo/macumba.ds1": Tint((1.0, 0.72, 0.48), 0.6, "dim sepia"),
    "expansion/zakarum/charismatic.ds1": Tint((0.70, 0.68, 1.0), 2.0, "bright cool lavender-grey marble and slate"),
}


def map_name(ds1: str) -> str:
    """'expansion/zakarum/charismatic.ds1' -> 'charismatic'."""
    return ds1.rsplit("/", 1)[-1][:-4]


def _d2r_json(rel: str):
    import fxpaths
    return json.loads(fxpaths.d2r_file(rel).read_text("utf-8-sig"))


def day_vis(biome: dict) -> str:
    """The biome's day visual data file (the one named *_day, else the first)."""
    names = [v["visualDataFilename"] for v in biome.get("visualDataFilenames", ())]
    if not names:
        raise ValueError("biome %s has no visual data" % biome.get("name"))
    return next((n for n in names if n.lower().endswith("_day.json")), names[0])


def tinted_vis(vis: dict, name: str, tint: Tint) -> dict:
    """A copy of a visual data file whose global key light has the tint's colour and power x tint.power."""
    out = copy.deepcopy(vis)
    out["name"] = name
    hit = 0
    for e in out.get("entities", ()):
        if e.get("name") != KEY_LIGHT:
            continue
        for c in e.get("components", ()):
            if c.get("type") == "DirectionalLightDefinitionComponent":
                c["color"] = {"x": tint.rgb[0], "y": tint.rgb[1], "z": tint.rgb[2]}
                c["power"] = round(float(c.get("power", 0.0)) * tint.power, 4)
                hit += 1
    if not hit:
        raise ValueError("visual data %s has no %s" % (vis.get("name"), KEY_LIGHT))
    return out


def tinted_biome(biome: dict, name: str, vis_rel: str) -> dict:
    """A copy of a biome named `name` whose every time-of-day slot is `vis_rel` (the scene's look does not change with the
    hour) and whose dependencies name that file instead of the old ones."""
    out = copy.deepcopy(biome)
    old = {v["visualDataFilename"] for v in out.get("visualDataFilenames", ())}
    out["name"] = name
    for v in out.get("visualDataFilenames", ()):
        v["visualDataFilename"] = vis_rel
    deps = out.setdefault("dependencies", {}).setdefault("json", [])
    deps[:] = [d for d in deps if d.get("path") not in old] + [{"path": vis_rel}]
    return out


def base_biome(data_dir: Path, biome: str, plan_biome: str) -> str:
    """The biome a map's scene had before apply(): `biome` itself, or for a scene already tinted by an earlier build into the
    same folder (walls_hd build run again) maps_hd's floor biome of the plan's biome when that is in data_dir, else the plan's."""
    if not biome.startswith(PREFIX):
        return biome
    import maps_hd
    floor = maps_hd.FLOOR_PREFIX + plan_biome
    return floor if (Path(data_dir) / (BIOME % floor)[len("data/"):]).exists() else plan_biome


def apply(data_dir: Path, ds1: str, biome: str, read=None) -> str:
    """Write the tinted biome and visual data of map `ds1` into data_dir and return the biome its scene should name (the
    base biome unchanged for a map without a tint). `biome` is the scene's biome: one of D2R's, or a generated one
    (maps_hd.floor_biomes) already in data_dir. read(rel) -> parsed D2R json (default: tools/fxpaths.py d2r_file)."""
    tint = TINTS.get(ds1)
    if tint is None:
        return biome
    read = read or _d2r_json
    own = Path(data_dir) / (BIOME % biome)[len("data/"):]
    base = json.loads(own.read_text("utf-8-sig")) if own.exists() else read(BIOME % biome)
    name = PREFIX + map_name(ds1)
    vis_rel = VIS % name
    for rel, js in ((vis_rel, tinted_vis(read(day_vis(base)), name, tint)), (BIOME % name, tinted_biome(base, name, vis_rel))):
        dest = Path(data_dir) / rel[len("data/"):]
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(js, separators=(",", ":")), encoding="utf-8")
    return name


# ---- measure: Median's retexture against its donor ---------------------------------------------------------------------------
def act_palette(act: int, read_bytes=None):
    """D2R's palette of an act (1-5): 256 (r, g, b); pal.dat is stored BGR."""
    if read_bytes is None:
        import fxpaths
        read_bytes = lambda rel: fxpaths.d2r_file(rel).read_bytes()   # noqa: E731
    d = read_bytes("data/global/palette/act%d/pal.dat" % act)
    return [(d[i * 3 + 2], d[i * 3 + 1], d[i * 3]) for i in range(256)]


def act_of(path: str) -> int:
    """The act whose palette a stock tile set is drawn with: 'act3/kurast/walls.dt1' -> 3, 'expansion/...' -> 5."""
    return 5 if path.startswith("expansion") else int(path[3])


class Diff(collections.Counter):
    """Sums over pixel pairs (new, donor) at the same place of the same tile: n, dist, far, dsat, dval, dhue (on nh pairs
    where both are coloured), shared (new pixels on palette entries all acts share), moved (pixels only one side has)."""

    def add(self, other):
        self.update(other)
        return self

    def row(self):
        n = max(1, self["n"])
        return {"pixels": self["n"], "mean_dist": self["dist"] / n, "far": self["far"] / n, "dhue": self["dhue"] / max(1, self["nh"]),
                "dsat": self["dsat"] / n, "dval": self["dval"] / n, "shared": self["shared"] / max(1, self["n"] + self["only_new"]),
                "moved": (self["only_new"] + self["only_old"]) / n}


def compare(new_tiles: dict, old_tiles: dict, pal_new, pal_old, shared=frozenset()) -> Diff:
    """new_tiles / old_tiles: dt1_pixels.tiles() of a new .dt1 and its donor."""
    d = Diff()
    hsv_new, hsv_old = [colorsys.rgb_to_hsv(*(c / 255 for c in p)) for p in pal_new], [colorsys.rgb_to_hsv(*(c / 255 for c in p)) for p in pal_old]
    for k, px in new_tiles.items():
        if k not in old_tiles:
            continue
        a = {(x, y): c for x, y, c in px if c}
        b = {(x, y): c for x, y, c in old_tiles[k] if c}
        d["only_new"] += len(a.keys() - b.keys())
        d["only_old"] += len(b.keys() - a.keys())
        for xy in a.keys() & b.keys():
            ca, cb = a[xy], b[xy]
            dist = math.dist(pal_new[ca], pal_old[cb])
            (ha, sa, va), (hb, sb, vb) = hsv_new[ca], hsv_old[cb]
            d["n"] += 1
            d["dist"] += dist
            d["far"] += dist > FAR
            d["dsat"] += sa - sb
            d["dval"] += va - vb
            d["shared"] += ca in shared
            if sa > 0.15 and sb > 0.15:
                d["dhue"] += ((ha - hb + 0.5) % 1.0) - 0.5
                d["nh"] += 1
    return d


def shared_entries(palettes) -> frozenset:
    """Palette indices whose colour is the same in every palette (1-255; 0 is transparent)."""
    return frozenset(i for i in range(1, 256) if len({p[i] for p in palettes}) == 1)


def cells_per_file(ds, files, tiles_of):
    """Counter(.dt1 path -> wall and floor cells of the map it draws): each cell's tile resolves to the first file in the
    level type's order that has its key (maps_hd's resolution)."""
    import ds1_remap
    idx = {}
    for p in files:
        for t in tiles_of(p) or ():
            idx.setdefault(t.key, p)
    out = collections.Counter()
    for lay, ori in ds.wall_layers():
        for c, o in zip(lay, ori):
            if c:
                p = idx.get((o & 0xFF,) + ds1_remap.cell_key(c))
                if p:
                    out[p] += 1
    for lay in ds.floor_layers():
        for c in lay:
            if c:
                p = idx.get((0,) + ds1_remap.cell_key(c))
                if p:
                    out[p] += 1
    return out


def measure(inp=None, palette=act_palette):
    """-> (files, maps): per new .dt1 its donor and Diff().row(); per retextured map the rows weighted by its cells."""
    import ds1_remap
    import dt1_pixels
    import maps_hd
    inp = inp or maps_hd.Inputs.load()
    maps, dt1s, _levels = maps_hd.plan(inp)
    pals = {a: palette(a) for a in range(1, 6)}
    shared = shared_entries(pals.values())
    donors = {d["path"]: d["donor"] for d in dt1s if d.get("donor") and d.get("jaccard", 0) >= 0.99}
    files, diffs = {}, {}
    for new, old in sorted(donors.items()):
        # Median's tiles sit on the shared entries, so any act's palette draws them alike; Act 5 is the expansion's
        diffs[new] = compare(dt1_pixels.tiles(inp.mod_tiles.read(new)), dt1_pixels.tiles(inp.d2r_tiles.read(old)),
                             pals[5], pals[act_of(old)], shared)
        files[new] = dict(diffs[new].row(), donor=old)
    stock = maps_hd.parse_tiles(inp.d2r_tiles)
    tiles = dict(stock)
    tiles.update(maps_hd.parse_tiles(inp.mod_tiles))
    out = {}
    for e in maps:
        if e["map"] not in TINTS:
            continue
        use = cells_per_file(ds1_remap.Ds1(inp.mod_tiles.read(e["map"])), e["dt1_files"], tiles.get)
        tot = Diff()
        for p, n in use.items():
            if p in diffs:   # the file's per-pixel means, weighted by the map's cells on it
                tot.add(Diff({k: v * n / max(1, diffs[p]["n"]) for k, v in diffs[p].items()}))
        cells = sum(use.values())
        out[e["map"]] = dict(tot.row(), cells=cells, new_cells=sum(n for p, n in use.items() if p in diffs),
                             files=", ".join("%s %d" % (p.rsplit("/", 2)[-2] + "/" + p.rsplit("/", 1)[-1], n)
                                             for p, n in use.most_common() if p in diffs))
    return files, out


def md_table(files: dict, maps: dict) -> str:
    lines = ["| map | cells on new .dt1 (of all) | mean RGB distance | pixels > %d off | hue shift | saturation | brightness | "
             "classic light (TINTS) | HD key light |" % FAR, "|---|---|---|---|---|---|---|---|---|"]
    for m, r in maps.items():
        t = TINTS[m]
        lines.append("| %s | %d (%d) | %.1f | %.2f%% | %+.3f | %+.3f | %+.4f | %s | rgb %.2f %.2f %.2f, power x%.1f |" % (
            m, r["new_cells"], r["cells"], r["mean_dist"], 100 * r["far"], r["dhue"], r["dsat"], r["dval"], t.classic, *t.rgb, t.power))
    lines += ["", "Per new .dt1 (all 51 copies; pixel pairs at the same place of the same tile key, new against donor):", "",
              "| new .dt1 | donor | pixels | mean RGB distance | > %d off | hue shift | saturation | brightness | on shared palette entries |" % FAR,
              "|---|---|---|---|---|---|---|---|---|"]
    for p, r in files.items():
        lines.append("| %s | %s | %d | %.1f | %.2f%% | %+.3f | %+.3f | %+.4f | %.0f%% |" % (
            p, r["donor"], r["pixels"], r["mean_dist"], 100 * r["far"], r["dhue"], r["dsat"], r["dval"], 100 * r["shared"]))
    lines += ["", "Distances are in RGB units (0-441): Median's tile under the Act 5 palette against the donor under its own act's. "
              "Hue in turns (1 = 360 degrees), only over pixels coloured on both sides; saturation and brightness on the HSV 0-1 scale. "
              "Map rows weight each file by the map's wall and floor cells drawn from it."]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["measure", "docs"])
    ap.add_argument("path", nargs="?", help="docs: the file (default docs/maps-hd.md)")
    ap.add_argument("--out", default=str(ROOT / "work" / "maps_hd"))
    a = ap.parse_args(argv)
    files, maps = measure()
    table = md_table(files, maps)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "map_tint.md").write_text("# Median's retexture against its donors\n\n" + table + "\n", encoding="utf-8")
    if a.cmd == "docs":
        target = Path(a.path or ROOT / "docs" / "maps-hd.md")
        text = target.read_text("utf-8")
        if DOCS_BEGIN not in text:
            raise SystemExit("%s lacks the %s ... %s markers" % (target, DOCS_BEGIN, DOCS_END))
        head, rest = text.split(DOCS_BEGIN, 1)
        new = head + DOCS_BEGIN + "\n\n" + table + "\n\n" + DOCS_END + rest.split(DOCS_END, 1)[1]
        if new != text:
            target.write_text(new, encoding="utf-8")
        print("updated" if new != text else "unchanged", target)
    print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
