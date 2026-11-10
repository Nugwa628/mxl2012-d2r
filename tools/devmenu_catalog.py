"""The developer menu's catalog (plugin part `devmenu`): what can be spawned or visited, by in-game name, with native row ids.

Reads the built tables (work/mod/data/global/excel) and the strings as the player sees them (strings_ns.effective_texts), and writes
one UTF-8 text file into the mod's data:

  work/mod/data/mxl2012-devmenu/catalog.tsv

The plugin reads it from the installed mod folder (`<mod>.mpq/data/mxl2012-devmenu/catalog.tsv`), so the catalog cannot drift from
the tables it was built with and no Median text is committed. Line kinds (tab separated; a name is the last field, cleaned of
colour codes, newlines and tabs):

  #devmenu <format> <tables hash>
  I <cat> <code> <quality> <row> <sockets> <name> [tag]
                                                  items: cat U unique, S set, C charm, Q misc / quest, B base; quality 0 base,
                                                  5 set, 7 unique (Items::Quality); row is the zero-based native row, -1 for bases;
                                                  sockets: the empty sockets a spawned normal item gets (its maximum, `max_sockets`);
                                                  0 for uniques and sets, whose sockets are their row's fixed `sock` property or none
  K <basecode> <sockets> <rune codes, comma separated> <name>      runeword kit: the base with empty sockets and the runes in order
  L <id> <act> <note> <waypoint> <name>           level; note 0 none, 1 map only (uber arena), 2 portal-only area; waypoint number or 255
  U <level> <entry> <how> <name>                  uber level (its entrance says "DANGER - Uberquest Area"): the menu warps to the entry level,
                                                  the area right before it; how 0 its entrance is there, 1 its red portal is there
  X <class> <120 thresholds>                      experience.txt per class: total experience to reach level 1..120 (level 1 = 0)

Native row ids follow the games: uniqueitems and setitems lines 'Expansion' are not records. Charms come from uniqueitems rows
whose base type reaches `char` through itemtypes Equiv1 / Equiv2 (46 rows, retired ones tagged), not from a name filter. Which
base a runeword kit uses is worked out here: the smallest compatible armour or weapon with the sockets the runes need.

  py -3 tools/devmenu_catalog.py                 write the catalog (a tools/build.py data step)
  py -3 tools/devmenu_catalog.py --check FILE    print the counts of an existing catalog
"""
import hashlib
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401
import localconfig  # noqa: E402,F401
import strings_ns  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXCEL = Path(os.environ.get("MXL_DEVMENU_EXCEL") or ROOT / "work" / "mod" / "data" / "global" / "excel")
OUT = ROOT / "work" / "mod" / "data" / "mxl2012-devmenu" / "catalog.tsv"
FORMAT = 3
SPAWN_ITEM_LEVEL = 99  # the item level the plugin gives a spawned base or misc item (devmenu.cpp ItemLevel)

# level ids that have no ordinary entrance: Median's uber arenas (map only: the fight needs its normal summon) and the portal areas
UBER_ARENAS = {125, 126, 127, 133, 134, 135, 136, 137}
PORTAL_AREAS = {38, 39}
CLASSES = ("Amazon", "Sorceress", "Necromancer", "Paladin", "Barbarian", "Druid", "Assassin", "Warlock")
MAX_LEVEL = 120

COLOUR = re.compile(r"ÿc.|\[[a-z]{2}\]", re.I)


def table(name: str) -> list[dict[str, str]]:
    with open(EXCEL / f"{name}.txt", encoding="utf-8-sig", errors="replace", newline="") as f:
        header = f.readline().rstrip("\r\n").split("\t")
        rows = []
        for line in f:
            parts = line.rstrip("\r\n").split("\t")
            if parts != [""]:
                rows.append(dict(zip(header, parts + [""] * (len(header) - len(parts)))))
    return rows


def tables_hash() -> str:
    h = hashlib.sha256()
    for name in ("uniqueitems", "setitems", "runes", "misc", "armor", "weapons", "itemtypes", "levels", "experience"):
        h.update((EXCEL / f"{name}.txt").read_bytes())
    return h.hexdigest()[:16]


def clean(text: str) -> str:
    # a multi-line item name reads bottom-up in the game: the last line is the name itself
    text = COLOUR.sub("", text).replace("\t", " ").replace("\r", "\n")
    lines = [" ".join(ln.split()) for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return lines[-1] if lines else ""


class Names:
    def __init__(self):
        self.texts = strings_ns.effective_texts()

    def __call__(self, ref: str) -> str:
        ref = (ref or "").strip()
        if not ref:
            return ""
        bare = strings_ns.bare(ref)
        if bare.startswith("d2r:"):
            bare = bare[4:]
        text = self.texts.get(bare, "")
        return clean(text) or ""


def equiv_chain(types: dict[str, dict[str, str]], code: str) -> set[str]:
    """code and everything it reaches through Equiv1 / Equiv2."""
    seen = set()
    todo = [code]
    while todo:
        c = todo.pop()
        if not c or c in seen:
            continue
        seen.add(c)
        row = types.get(c)
        if row:
            todo += [row.get("Equiv1", ""), row.get("Equiv2", "")]
    return seen


def bases_with_type() -> dict[str, tuple[str, str, int, int]]:
    """item code -> (type, type2, width, height) of armor, weapons and misc."""
    out = {}
    for name in ("armor", "weapons", "misc"):
        for r in table(name):
            if r.get("code"):
                out[r["code"]] = (r.get("type", ""), r.get("type2", ""), int(r.get("invwidth") or 1), int(r.get("invheight") or 1))
    return out


def max_sockets(item_type: dict[str, str] | None, gemsockets: str, item_level: int) -> int:
    """The most sockets an item of this base can have at this item level, as 1.13c's (and D2R's) socket rule: the item type's MaxSockets1 / 2 / 3
    by item level (up to MaxSocketsLevelThreshold1, up to MaxSocketsLevelThreshold2, above; 25 / 40 on every Median type, itemtypes
    MaxSock1/25/40), never more than the base's own gemsockets. A type that allows none (rings, amulets, jewels, charms, potions) gives 0."""
    if item_type is None:
        return 0

    def num(key, fallback=0):
        try:
            return int((item_type.get(key) or "").strip() or fallback)
        except ValueError:
            return fallback

    if item_level <= num("MaxSocketsLevelThreshold1", 25):
        by_level = num("MaxSockets1")
    elif item_level <= num("MaxSocketsLevelThreshold2", 40):
        by_level = num("MaxSockets2")
    else:
        by_level = num("MaxSockets3")
    try:
        own = int((gemsockets or "").strip() or 0)
    except ValueError:
        own = 0
    return max(0, min(by_level, own))


def native_records(rows: list[dict[str, str]], key: str = "index") -> list[dict[str, str]]:
    """The records the game counts: the 'Expansion' separator lines are not records."""
    return [r for r in rows if (r.get(key) or "") not in ("", "Expansion")]


CLASS_CODES = {"ama": "Amazon", "sor": "Sorceress", "nec": "Necromancer", "pal": "Paladin", "bar": "Barbarian", "dru": "Druid", "ass": "Assassin", "war": "Warlock"}


def skill_names(names) -> dict[str, tuple[str, str]]:
    """skill id (and skill key) -> (name as the player sees it, class name or "")."""
    descs = {r["skilldesc"]: r for r in table("skilldesc") if r.get("skilldesc")}
    out = {}
    for r in table("skills"):
        key = r.get("skill", "")
        sid = (r.get("*Id") or r.get("Id") or "").strip()
        if not key or not sid:
            continue
        desc = descs.get(r.get("skilldesc", ""))
        name = (names(desc.get("str name", "")) if desc else "") or clean(key)
        out[sid] = out[key] = (name, CLASS_CODES.get(r.get("charclass", ""), ""))
    return out


def skill_label(name: str, skill: tuple[str, str]) -> str:
    """'Cornerstone of the World: Ghost Arrow (Amazon)'; a skill of no class has no class part."""
    return f"{name}: {skill[0]} ({skill[1]})" if skill[1] else f"{name}: {skill[0]}"


def row_skill(r: dict[str, str], skills: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """The one skill a unique row gives (Cornerstone of the World: one row per skill, `oskill` with the skill as parameter), else None."""
    granted = [r.get(f"par{i}", "") for i in range(1, 13) if r.get(f"prop{i}", "") == "oskill"]
    return skills.get(granted[0].strip()) if len(granted) == 1 else None


def collect_uniques(names, types, bases, skills=None) -> list[str]:
    charm_cells = {c for c in types if "char" in equiv_chain(types, c)}
    records = native_records(table("uniqueitems"))
    shared = {}
    for r in records:
        shared[r["index"]] = shared.get(r["index"], 0) + 1
    lines = []
    for row, r in enumerate(records):
        code = r.get("code", "")
        base = bases.get(code)
        is_charm = base is not None and (base[0] in charm_cells or base[1] in charm_cells)
        spawnable = r.get("spawnable", "") == "1" and not r.get("disabled")
        if not is_charm and (not spawnable or base is None):
            continue
        name = names(r["index"]) or clean(r["index"])
        if not name or name.lower() == "expansion":
            continue
        # rows that share one name and differ only by the skill they give are told apart (and found) by that skill
        skill = row_skill(r, skills) if skills and shared[r["index"]] > 1 else None
        if skill:
            name = skill_label(name, skill)
        tag = "" if spawnable else "retired row"
        lines.append("\t".join(["I", "C" if is_charm else "U", code, "7", str(row), "0", name] + ([tag] if tag else [])))
    return lines


def collect_sets(names, bases) -> list[str]:
    sets = {r["index"]: names(r.get("name", "")) or clean(r["index"]) for r in table("sets") if r.get("index")}
    lines = []
    for row, r in enumerate(native_records(table("setitems"))):
        if r.get("spawnable") != "1" or r.get("disabled") or r.get("item") not in bases:
            continue  # a vanilla row whose base Median removed cannot be created
        name = names(r["index"]) or clean(r["index"])
        label = f"{name} ({sets.get(r.get('set', ''), r.get('set', ''))})" if r.get("set") else name
        lines.append("\t".join(["I", "S", r["item"], "5", str(row), "0", label]))
    return lines


def collect_misc(names, types=None) -> list[str]:
    types = types or {}
    lines = []
    for r in table("misc"):
        code = r.get("code", "")
        if not code or r.get("name") in ("", "Expansion"):
            continue
        name = names(r.get("namestr", "")) or clean(r["name"])
        if name:
            sockets = max_sockets(types.get(r.get("type", "")), r.get("gemsockets", ""), SPAWN_ITEM_LEVEL)
            lines.append("\t".join(["I", "Q", code, "0", "-1", str(sockets), name]))
    return lines


def collect_bases(names, types=None) -> list[str]:
    types = types or {}
    lines = []
    for name in ("armor", "weapons"):
        for r in table(name):
            code = r.get("code", "")
            if not code or r.get("name") in ("", "Expansion"):
                continue
            label = names(r.get("namestr", ""))
            if label:
                sockets = max_sockets(types.get(r.get("type", "")), r.get("gemsockets", ""), SPAWN_ITEM_LEVEL)
                lines.append("\t".join(["I", "B", code, "0", "-1", str(sockets), label]))
    return lines


def kit_base(types, candidates, itypes, etypes, sockets):
    """the compatible armour / weapon for a runeword: smallest area then lowest level with `sockets` sockets, else (some Median
    words want more sockets than any base's table limit) the compatible base with the most sockets; the plugin asks for `sockets`
    and reports what it got. None when no base type fits."""
    allowed = {t for t in itypes if t}
    excluded = {t for t in etypes if t}
    best, widest = None, None
    for (w, h, lvl, code, type1, type2, max_sockets) in candidates:
        chain = equiv_chain(types, type1) | equiv_chain(types, type2)
        if not (chain & allowed) or chain & excluded:
            continue
        key = (w * h, lvl, code)
        if max_sockets >= sockets and (best is None or key < best):
            best = key
        if widest is None or (-max_sockets, key) < widest:
            widest = (-max_sockets, key)
    if best is not None:
        return best[2]
    return widest[1][2] if widest is not None else None


def collect_runewords(names, types) -> list[str]:
    candidates = []
    for name in ("armor", "weapons"):
        for r in table(name):
            code = r.get("code", "")
            if not code or r.get("name") in ("", "Expansion"):
                continue
            try:
                sockets = int(r.get("gemsockets") or 0)
            except ValueError:
                sockets = 0
            candidates.append((int(r.get("invwidth") or 1), int(r.get("invheight") or 1), int(r.get("level") or 0), code, r.get("type", ""),
                               r.get("type2", ""), sockets))
    lines, unplaced = [], 0
    for r in table("runes"):
        if r.get("complete") != "1":
            continue
        runes = [r.get(f"Rune{i}", "").strip() for i in range(1, 7)]
        runes = [c for c in runes if c]
        if not runes:
            continue
        base = kit_base(types, candidates, [r.get(f"itype{i}", "") for i in range(1, 7)], [r.get(f"etype{i}", "") for i in range(1, 4)], len(runes))
        if base is None:
            unplaced += 1
            continue
        name = names(r.get("Name", "")) or clean(r.get("Name", ""))
        lines.append("\t".join(["K", base, str(len(runes)), ",".join(runes), name]))
    print(f"runeword kits: {len(lines)}, no compatible base with enough sockets: {unplaced}")
    return lines


def collect_levels(names) -> list[str]:
    lines = []
    for r in table("levels"):
        lid = int(r.get("Id") or 0)
        if lid == 0 or r.get("Name") in ("", "Expansion"):
            continue
        name = names(r.get("LevelName", "")) or clean(r.get("Name", ""))
        note = "1" if lid in UBER_ARENAS else "2" if lid in PORTAL_AREAS else "0"
        waypoint = (r.get("Waypoint") or "255").strip() or "255"
        lines.append("\t".join(["L", str(lid), r.get("Act", "0") or "0", note, waypoint, name]))
    return lines


UBER_WARP_TEXT = "DANGER - Uberquest Area"
# The three uber levels without a `Vis` link (Welcome to Toraja, Old Bremmtown, Khalimgrad: the Hell1-3 slots) are entered by the red
# portals the game itself places (lvlprest "Act 5 - Barricade Hell Portal N / W", `hellwrpN` / `hellwrpW`) in a fixed level each.
RED_PORTALS = {125: 111, 126: 112, 127: 117}  # uber level -> the level holding its red portal (Frigid Highlands, Arreat Plateau, Frozen Tundra)


def uber_entries(levels: list[dict[str, str]], names) -> list[tuple[int, int, int, str]]:
    """(uber level, entry level, how, name) for each uber level, by levels.txt id order. An uber level is one whose entrance label
    (`LevelWarp`, the text a player reads on the way in) says "DANGER - Uberquest Area"; its entry level is the area with that entrance:
    its `Vis` link (how 0, an entrance) or the level of its red portal (how 1)."""
    out = []
    for r in levels:
        lid = int(r.get("Id") or 0)
        if lid == 0 or names(r.get("LevelWarp", "")) != UBER_WARP_TEXT:
            continue
        links = [int(r.get(f"Vis{i}") or 0) for i in range(8)]
        links = [v for v in links if v > 0]
        if links:
            entry, how = links[0], 0
        elif lid in RED_PORTALS:
            entry, how = RED_PORTALS[lid], 1
        else:
            raise SystemExit(f"uber level {lid} has no entrance link and no red portal")
        out.append((lid, entry, how, names(r.get("LevelName", "")) or clean(r.get("Name", ""))))
    return out


def collect_ubers(names) -> list[str]:
    return ["\t".join(["U", str(lid), str(entry), str(how), name]) for lid, entry, how, name in uber_entries(table("levels"), names)]


def collect_experience() -> list[str]:
    rows = {r["Level"]: r for r in table("experience") if r.get("Level")}
    lines = []
    for index, cls in enumerate(CLASSES):
        # experience.txt: row L is the total experience that gives level L + 1 (row 0 = 0 = level 1)
        thresholds = [rows[str(level - 1)][cls] for level in range(1, MAX_LEVEL + 1)]
        lines.append("\t".join(["X", str(index)] + thresholds))
    return lines


def build() -> list[str]:
    names = Names()
    types = {r["Code"]: r for r in table("itemtypes") if r.get("Code")}
    bases = bases_with_type()
    lines = [f"#devmenu\t{FORMAT}\t{tables_hash()}"]
    for part in (collect_uniques(names, types, bases, skill_names(names)), collect_sets(names, bases), collect_misc(names, types), collect_bases(names, types), collect_runewords(names, types),
                 collect_levels(names), collect_ubers(names), collect_experience()):
        lines += part
    return lines


def counts(lines: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in lines:
        cols = line.split("\t")
        key = cols[1] if cols[0] == "I" else "uber" if cols[0] == "U" else cols[0]  # item category U (uniques) is not uber line U
        out[key] = out.get(key, 0) + 1
    return out


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        print(counts(Path(sys.argv[2]).read_text("utf-8").splitlines()))
        return 0
    if len(sys.argv) != 1:
        print(__doc__)
        return 2
    lines = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", "utf-8", newline="\n")
    print(f"catalog: {OUT.relative_to(ROOT)} {counts(lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
