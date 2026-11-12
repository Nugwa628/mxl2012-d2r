#!/usr/bin/env python3
"""Monsters for the wiki generator (docs/wiki-plan.md): every monster that spawns in an area, every boss and superunique.

  py -3 tools/wiki/monsters.py               write work/wiki/monsters.json
        [--out FILE]                       another output file
        [--show NAME ...]                  also print the records whose name or Id contains NAME

Reads the built tables (work/mod/data/global/excel: monstats, levels, monlvl, monprop, montype, superuniques, monumod,
monpreset, lvlprest, skills, skilldesc) and the strings the player reads (tools/strings_ns.effective_texts).

Difficulties are Median's names: Hatred, Terror, Destruction (the game's Normal, Nightmare, Hell).

Where a monster spawns: levels.txt mon1..mon25 and umon1..umon25 in Hatred, nmon1..nmon25 in Terror and Destruction.
Its level there is the area's MonLvlEx / (N) / (H); a boss (monstats `boss` 1) and a monster that spawns nowhere keep
monstats Level / Level(N) / Level(H). The figures follow the expansion's rule: monstats life, defense, to-hit, damage and
experience are percentages of the monlvl.txt row of the monster's level (the L- columns), unless `noRatio` is set; one
player, no champion / unique bonus. A regular monster's figures are given at the lowest and the highest level it has in
that difficulty.

Superuniques: the class row's figures at the area level (a boss class: at its monstats level). Where they stand comes from the map presets: a .ds1 monster
preset below the act's monpreset.txt row count names the superunique; the preset's lvlprest row gives the level, or for
the shared sub-presets (LevelId 0) the vanilla level that preset is placed in (SUB_PRESETS). Superuniques the game code
spawns itself are in CODE_PLACED. Both vanilla placements count only where Median kept the level as D2R builds it (same
Name and DrlgType in D2R's levels.txt); Median turned some of those levels into uberquest areas. The unique bonuses (+3 levels, more life, the modifiers) are not applied.

One record per monster:
  kind               "monster" or "superunique"
  id, hc             monstats Id and *hcIdx (superunique: the superunique key and its row)
  name, colour       the shown name without colour codes, its first colour code
  rank               Normal, Elite, Heroic, Veteran, Boss, Special (Median's name colours)
  base, montype      monstats BaseId and MonType; family the BaseId row's shown name
  art_base           the BaseId of the MonStatsEx row (Median's copies of a monster point there)
  category           Undead, Demon or Animal (the monstats lUndead / hUndead / demon flags)
  boss               monstats boss flag
  diff               {Hatred|Terror|Destruction: {levels [lo, hi], life, defense, tohit, exp, damage [lines], resist {...},
                      immune [..], props [lines], areas [names]}}
  skills             the monster's skills (Skill1..8, shown names) with their level
  class (superunique) the monstats Id; mods the monumod names
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import localconfig  # noqa: E402,F401  (MXL_D2R_EXTRACT: D2R's own strings)

if os.environ.get("MXL_D2R_EXTRACT") and not os.environ.get("D2R_LNG"):
    os.environ["D2R_LNG"] = str(Path(os.environ["MXL_D2R_EXTRACT"]) / "data" / "local" / "lng")
import fxpaths  # noqa: E402
import strings_ns  # noqa: E402
from ds1_remap import Ds1  # noqa: E402
from tooltip_audit import read_table  # noqa: E402

EXCEL = ROOT / "work" / "mod" / "data" / "global" / "excel"
MXL_TILES = ROOT / "assets" / "median" / "data" / "global" / "tiles"
D2R_TILES = fxpaths.D2R_DATA / "global" / "tiles"
OUT = ROOT / "work" / "wiki" / "monsters.json"
DIFFS = ("Hatred", "Terror", "Destruction")
SUFFIX = ("", "(N)", "(H)")
COLOUR = re.compile("ÿc(.)")
HIDDEN_SKILLS = ("Monster Effect",)  # hit / death effects every monster casts (art only)
NOT_SKILLS = {"Attack"}
RANKS = {"9": "Elite", "2": "Heroic", ":": "Veteran", "4": "Boss", "8": "Special", "1": "Special", ";": "Boss"}
RESISTS = (("ResDm", "Physical"), ("ResMa", "Magic"), ("ResFi", "Fire"), ("ResLi", "Lightning"), ("ResCo", "Cold"),
           ("ResPo", "Poison"))
ELEMENTS = {"fire": "Fire", "ltng": "Lightning", "cold": "Cold", "pois": "Poison", "mag": "Magic", "life": "Life drain",
            "mana": "Mana drain", "stam": "Stamina drain", "stun": "Stun", "rand": "Random element", "burn": "Burning"}
ATTACKS = (("A1", "Attack 1"), ("A2", "Attack 2"), ("S1", "Skill attack"))
# monprop properties that cast a skill: (text, chance column, level column) read from the property's min / max
SKILL_PROPS = {"hit-skill": "%d%% chance to cast level %d %s on striking",
               "att-skill": "%d%% chance to cast level %d %s on attack",
               "damage-skill": "%d%% chance to cast level %d %s when struck",
               "kill-skill": "%d%% chance to cast level %d %s when it kills",
               "death-skill": "%d%% chance to cast level %d %s when it dies"}
PLAIN_PROPS = {"red-dmg%": "Damage reduced by %s%%", "slow": "Slows target by %s%%", "crush": "%s%% chance of crushing blow",
               "openwounds": "%s%% chance of open wounds", "pierce-fire": "-%s%% to enemy fire resistance",
               "pierce-cold": "-%s%% to enemy cold resistance", "pierce-ltng": "-%s%% to enemy lightning resistance",
               "pierce-pois": "-%s%% to enemy poison resistance", "pierce-all": "-%s%% to all enemy resistances",
               "dmg-stun": "Stuns for %s frames", "ignore-ac": "Ignores target's defense", "att%": "+%s%% attack rating",
               "knock": "Knockback", "freeze": "Freezes target", "avoidance": "%s%% chance to avoid damage",
               "evasion": "%s%% chance to evade", "res-curse": "Curse resistance +%s%%",
               "extra-fire": "+%s%% to fire skill damage", "extra-cold": "+%s%% to cold skill damage",
               "extra-pois": "+%s%% to poison skill damage", "ac-miss": "+%s defense vs. missiles",
               "reanimate": "Reanimates its victims", "reanimate-rand": "Reanimates its victims",
               "howl": "Hit causes the target to flee", "stupidity": "Hit blinds the target"}
# lvlprest sub-presets (LevelId 0) with a superunique and the vanilla level the engine places them in
SUB_PRESETS = {"Act 1 - Fallen Camp Bishibosh": 3, "Act 1 - Crypt Bonebreak": 18, "Act 1 - Cave Coldcrow": 9,
               "Act 1 - Cave Den Of Evil": 8, "Act 1 - Jail Pitspawn": 30, "Act 1 - Cairn Stones": 4,
               "Act 1 - Inifus": 5, "Act 1 - Barracks Forge": 28, "Act 2 - Tomb Kaa": 66, "Act 2 - Desert Oasis 2": 43,
               "Act 2 - Tomb Cube": 59, "Act 2 - Desert Ruins Elder": 44, "Act 2 - Tomb Tainted Sun": 61,
               "Act 2 - Basement SE": 54, "Act 2 - Tomb Leatherarm": 60, "Act 2 - Sewer Radament's Lair": 49,
               "Act 3 - Travincal": 83, "Act 3 - Sewer Drain": 92, "Act 3 - Jungle Tail": 79,
               "Act 3 - Spider Chest": 85, "Act 4 - Lava Forge": 107, "Act 5 - Siege Strip 6": 110,
               "Act 5 - Siege Strip 13": 110, "Act 5 - Barricade Exit": 111, "Act 5 - Barricade To Siege": 111,
               "Act 5 - Barricade To Cave": 112, "Act 5 - Ice River": 114, "Act 5 - Ice Pool": 119}
# superuniques the game code spawns (no map preset): their vanilla level
CODE_PLACED = {"Ancient Barbarian 1": 120, "Ancient Barbarian 2": 120, "Ancient Barbarian 3": 120,
               "Baal Subject 1": 131, "Baal Subject 2": 131, "Baal Subject 3": 131, "Baal Subject 4": 131,
               "Baal Subject 5": 131, "Infector of Souls": 108, "Lord De Seis": 108, "Grand Vizier of Chaos": 108,
               "Nihlathak Boss": 124, "The Cow King": 39, "The Summoner": 74, "Coldworm the Burrower": 64,
               "Boneash": 33, "Bonesaw Breaker": 115}


def num(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def read(name: str):
    return read_table(EXCEL / name)


class Data:
    def __init__(self):
        self.texts = strings_ns.effective_texts()
        self.mon = {r["Id"]: r for r in read("monstats.txt")}
        self.levels = {num(r["Id"]): r for r in read("levels.txt") if num(r.get("Id"))}
        self.monlvl = {num(r["Level"]): r for r in read("monlvl.txt") if num(r.get("Level"))}
        self.monprop = {r["Id"]: r for r in read("monprop.txt")}
        self.montype = {r["type"]: r for r in read("montype.txt")}
        self.umod = {r["id"]: r["uniquemod"] for r in read("monumod.txt")}
        self.supers = read("superuniques.txt")
        desc = {r["skilldesc"]: r for r in read("skilldesc.txt")}
        self.skill_by_key, self.skill_by_id = {}, {}
        for r in read("skills.txt"):
            d = desc.get(r.get("skilldesc", ""))
            shown = self.text(d["str name"]) if d and d.get("str name") else ""
            name = COLOUR.sub('',shown).strip() or r['skill']
            self.skill_by_key[r["skill"]] = name
            if r.get("*Id", "").isdigit():
                self.skill_by_id[int(r["*Id"])] = name

    def text(self, cell: str) -> str:
        return self.texts.get(strings_ns.bare(cell), "") if cell else ""

    def area(self, lid: int) -> str:
        r = self.levels[lid]
        return COLOUR.sub('',self.text(r['LevelName'])).strip()

    def skill(self, par: str) -> str:
        """Resolved name, or an intact diagnostic key for the player's source filter.

        Stripping an unresolved key makes it look like a display name and prevents
        the exporter from recognizing and omitting/translating that reference.
        """
        return self.skill_by_id.get(int(par), "skill " + par) if par.isdigit() else self.skill_by_key.get(par, par)


def shown_name(data: Data, cell: str, fallback: str):
    """(name without colour codes, first colour code or "")."""
    raw = data.text(cell)
    raw = raw.split("\n")[-1]
    m = COLOUR.search(raw)
    name = COLOUR.sub("", raw).strip()
    return name, (m.group(1) if m and raw.startswith("ÿc") else "")


def spawns(data: Data):
    """{monstats Id: [set of level ids per difficulty]} from the levels' mon / umon / nmon columns."""
    out = defaultdict(lambda: [set(), set(), set()])
    for lid, r in data.levels.items():
        for i in range(1, 26):
            for col, diffs in (("mon", (0,)), ("umon", (0,)), ("nmon", (1, 2))):
                m = r.get(f"{col}{i}")
                if m:
                    for d in diffs:
                        out[m][d].add(lid)
    return out


def area_level(data: Data, lid: int, d: int) -> int:
    return num(data.levels[lid]["MonLvlEx" + SUFFIX[d]])


def scaled(data: Data, row: dict, col: str, lvl: int, d: int, kind: str) -> int:
    """A monstats value as the game applies it: a percentage of the monlvl row (L- columns) unless noRatio is set."""
    v = num(row.get(col))
    if row.get("noRatio") == "1":
        return v
    ml = data.monlvl.get(min(max(lvl, 1), max(data.monlvl)))
    return v * num(ml["L-" + kind + SUFFIX[d]]) // 100


def rng(lo: int, hi: int) -> str:
    return f"{lo:,}" if lo == hi else f"{lo:,}–{hi:,}"


def span(values) -> str:
    """'a–b' over the low and high level's figures (each a (lo, hi) pair)."""
    los = [v[0] for v in values]
    his = [v[1] for v in values]
    return rng(min(los), max(his))


def col(name: str, d: int) -> str:
    """The monstats column of difficulty d (the (N) / (H) suffix; some columns spell the first letter in capitals)."""
    if d == 0:
        return name
    return name + SUFFIX[d]


def difficulty(data: Data, row: dict, d: int, lvls: list) -> dict:
    """The figures of one difficulty at the levels in lvls (the lowest and highest)."""
    def get(c):
        for cand in (col(c, d), col(c[0].upper() + c[1:], d), col(c[0].lower() + c[1:], d)):
            if cand in row:
                return cand
        return col(c, d)

    lo_hi = sorted({min(lvls), max(lvls)})
    life = [(scaled(data, row, get("minHP"), lv, d, "HP"), scaled(data, row, get("maxHP"), lv, d, "HP")) for lv in lo_hi]
    out = {"levels": [min(lvls), max(lvls)], "life": span(life),
           "defense": span([(scaled(data, row, get("AC"), lv, d, "AC"),) * 2 for lv in lo_hi]),
           "exp": span([(scaled(data, row, get("Exp"), lv, d, "XP"),) * 2 for lv in lo_hi])}
    damage, tohit = [], []
    for code, label in ATTACKS:
        lo_c, hi_c = get(code + "MinD"), get(code + "MaxD")
        if num(row.get(hi_c)):
            dmg = [(scaled(data, row, lo_c, lv, d, "DM"), scaled(data, row, hi_c, lv, d, "DM")) for lv in lo_hi]
            damage.append(f"{label}: {span(dmg)}")
            th = get(code + "TH")
            if num(row.get(th)):
                tohit.append(span([(scaled(data, row, th, lv, d, "TH"),) * 2 for lv in lo_hi]))
    for i in (1, 2, 3):
        kind = row.get(f"El{i}Type", "")
        if not kind:
            continue
        mode = dict(ATTACKS).get(row.get(f"El{i}Mode", ""), row.get(f"El{i}Mode", ""))
        pct = num(row.get(get(f"El{i}Pct")))
        lo_c, hi_c = get(f"El{i}MinD"), get(f"El{i}MaxD")
        text = ELEMENTS.get(kind, kind)
        if num(row.get(hi_c)) or num(row.get(lo_c)):
            dmg = [(scaled(data, row, lo_c, lv, d, "DM"), scaled(data, row, hi_c, lv, d, "DM") or
                    scaled(data, row, lo_c, lv, d, "DM")) for lv in lo_hi]
            text += f" {span(dmg)}"
        if pct and pct < 100:
            text += f" ({pct}%)"
        damage.append(f"{text} on {mode}" if mode else text)
    out["damage"] = damage
    out["tohit"] = tohit[0] if tohit else ""
    resist, immune = {}, []
    for c, label in RESISTS:
        v = num(row.get(col(c, d)))
        if v:
            resist[label] = v
        if v >= 100:
            immune.append(label)
    out["resist"], out["immune"] = resist, immune
    out["props"] = props(data, row.get("MonProp", ""), d)
    return out


def props(data: Data, key: str, d: int) -> list:
    r = data.monprop.get(key)
    if not r:
        return []
    out = []
    sfx = ["", " (N)", " (H)"][d]
    for i in range(1, 7):
        code = r.get(f"prop{i}{sfx}", "")
        if not code:
            continue
        par, lo, hi = r.get(f"par{i}{sfx}", ""), num(r.get(f"min{i}{sfx}")), num(r.get(f"max{i}{sfx}"))
        chance = num(r.get(f"chance{i}{sfx}"))
        if code in SKILL_PROPS:
            if data.skill(par).endswith(HIDDEN_SKILLS):
                continue
            text = SKILL_PROPS[code] % (lo, hi, data.skill(par))
        elif code == "aura":
            text = f"Level {rng(lo, hi)} {data.skill(par)} aura"
        elif code in PLAIN_PROPS:
            text = PLAIN_PROPS[code] % rng(lo, hi) if "%s" in PLAIN_PROPS[code] else PLAIN_PROPS[code]
        else:
            continue  # states, fade, swing, mon-buff, ... (art and AI, not a figure a player reads)
        if chance and chance < 100:
            text += f" ({chance}% of them)"
        out.append(text)
    return out


def category(row: dict) -> str:
    if row.get("lUndead") == "1" or row.get("hUndead") == "1":
        return "Undead"
    if row.get("demon") == "1":
        return "Demon"
    return "Animal"


def skills(data: Data, row: dict) -> list:
    out = []
    for i in range(1, 9):
        s = row.get(f"Skill{i}", "")
        if s and data.skill(s) not in NOT_SKILLS:
            out.append({"name": data.skill(s), "level": num(row.get(f"Sk{i}lvl"))})
    return out


def base_record(data: Data, row: dict) -> dict:
    name, colour = shown_name(data, row.get("NameStr", ""), row["Id"])
    rank = RANKS.get(colour, "Normal")
    if row.get("boss") == "1" and rank in ("Normal", "Special"):
        rank = "Boss"
    return {"id": row["Id"], "hc": num(row.get("*hcIdx")), "name": name, "colour": colour, "rank": rank,
            "base": row.get("BaseId", ""), "art_base": data.mon.get(row.get("MonStatsEx", ""), {}).get("BaseId", ""),
            "montype": row.get("MonType", ""), "category": category(row),
            "boss": row.get("boss") == "1", "skills": skills(data, row)}


def monster(data: Data, row: dict, where) -> dict:
    rec = dict(base_record(data, row), kind="monster", diff={})
    for d, diff in enumerate(DIFFS):
        lids = sorted(where[d]) if where else []
        if lids and not rec["boss"]:
            lvls = [area_level(data, lid, d) for lid in lids]
        else:
            lvls = [num(row.get(col("Level", d)))]
        rec["diff"][diff] = difficulty(data, row, d, lvls)
        rec["diff"][diff]["areas"] = sorted({data.area(lid) for lid in lids})
    return rec


def superunique_places(data: Data) -> dict:
    """{superunique key: set of level ids} from the map presets and CODE_PLACED."""
    places = defaultdict(list)
    for ln in (EXCEL / "monpreset.txt").read_text("utf-8-sig").splitlines()[1:]:
        act, _, place = ln.partition("\t")
        if act.strip().isdigit():
            places[int(act)].append(place.strip())
    keys = {r["Superunique"] for r in data.supers}
    vanilla = {num(r["Id"]): r for r in read_table(fxpaths.D2R_EXCEL / "levels.txt") if num(r.get("Id"))}
    # levels Median kept as the vanilla engine builds them (same DrlgType): the vanilla placements hold there only
    unchanged = {lid for lid, r in data.levels.items()
                 if lid in vanilla and r["Name"] == vanilla[lid]["Name"] and r["DrlgType"] == vanilla[lid]["DrlgType"]}
    out = defaultdict(set)
    for r in read("lvlprest.txt"):
        for i in range(1, 7):
            f = r.get(f"File{i}", "")
            if not f or f == "0":
                continue
            rel = f.replace("\\", "/")
            path = MXL_TILES / rel if (MXL_TILES / rel).exists() else D2R_TILES / rel
            if not path.exists():
                continue
            ds1 = Ds1(path.read_bytes())
            table = places[ds1.act + 1]
            for kind, oid, *_ in ds1.objects:
                if kind != 1 or oid >= len(table) or table[oid] not in keys:
                    continue
                lid = num(r["LevelId"])
                if not lid:
                    lid = next((v for k, v in SUB_PRESETS.items() if r["Name"].startswith(k)), 0)
                    lid = lid if lid in unchanged else 0
                if lid:
                    out[table[oid]].add(lid)
    for key, lid in CODE_PLACED.items():
        if lid in unchanged:
            out.setdefault(key, set()).add(lid)
    return out


def superuniques(data: Data) -> list:
    places = superunique_places(data)
    out = []
    for i, su in enumerate(data.supers):
        row = data.mon.get(su.get("Class", ""))
        if not row:
            continue
        name, colour = shown_name(data, su.get("Name", ""), su["Superunique"])
        lids = sorted(places.get(su["Superunique"], ()))
        rec = dict(base_record(data, row), kind="superunique", id=su["Superunique"], hc=i, name=name, colour=colour,
                   rank="Superunique", diff={}, **{"class": row["Id"]})
        rec["mods"] = [data.umod.get(su.get(f"Mod{k}", ""), "") for k in (1, 2, 3) if num(su.get(f"Mod{k}"))]
        rec["located"] = bool(lids)
        for d, diff in enumerate(DIFFS):
            if lids and row.get("boss") != "1":
                lvls = [area_level(data, lid, d) for lid in lids]
            else:
                lvls = [num(row.get(col("Level", d)))]  # a boss class keeps its own level, as for monsters
            rec["diff"][diff] = difficulty(data, row, d, lvls)
            rec["diff"][diff]["areas"] = sorted({data.area(lid) for lid in lids})
        out.append(rec)
    return out


def family_names(data: Data, recs: list) -> None:
    """rec["family"]: the shown name of the BaseId row, or the record's own name."""
    for rec in recs:
        base = data.mon.get(rec["base"])
        rec["family"] = shown_name(data, base.get("NameStr", ""), base["Id"])[0] if base else rec["name"]


def monsters(data: Data) -> list:
    where = spawns(data)
    recs = []
    for mid, row in data.mon.items():
        if row.get("enabled") == "0" or (mid not in where and row.get("boss") != "1"):
            continue
        name, _ = shown_name(data, row.get("NameStr", ""), "")
        if not name:
            continue
        recs.append(monster(data, row, where.get(mid)))
    family_names(data, recs)
    sups = superuniques(data)
    family_names(data, sups)
    return recs + sups


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--show", nargs="*", default=[])
    args = ap.parse_args()
    data = Data()
    recs = monsters(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", "utf-8")
    kinds = defaultdict(int)
    for r in recs:
        kinds[r["kind"]] += 1
    print("%d monsters, %d superuniques (%d located) -> %s" % (
        kinds["monster"], kinds["superunique"], sum(r.get("located", False) for r in recs), out))
    if args.show:
        sys.stdout.reconfigure(encoding="utf-8")
        for r in recs:
            if any(s.lower() in (r["name"] + " " + r["id"]).lower() for s in args.show):
                print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
