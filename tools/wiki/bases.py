#!/usr/bin/env python3
"""Base items for the wiki generator (docs/wiki-plan.md): every weapon, armor and jewellery base the game can drop.

  py -3 tools/wiki/bases.py                  write work/wiki/bases.json
        [--out FILE]                         another output file
        [--show NAME ...]                    also print the records whose name contains NAME

Reads the built weapons / armor / misc tables, itemtypes and the strings the player reads (tools/wiki/items.py Data). A row
is kept when its `spawnable` column is 1; from misc.txt only the equippable kinds (MISC_TYPES: rings, amulets, jewels,
quivers). Rows keep the table order (weapons, armor, misc).

One record per row:
  code, name        the item code and the shown name with its tier ("Giant Axe (3)"); base: the name without the tier
  table             weapons / armor / misc
  type, type_code   the item type's name and code; group: the type name of the base's first tier (the list page's groups)
  class             "(Sorceress Only)" for a class item, missing otherwise
  tier              1..6 or "sacred" (items.tier_of), missing for untiered bases
  lvl, lvlreq, reqstr, reqdex, speed, sockets (gemsockets), durability (0 = indestructible), width, height
  damage            weapons: {"one": [min, max], "two": [min, max], "throw": [min, max]} as the item has them
  defense, block    armor: [minac, maxac] and the block chance (shields)
  smite, kick       a shield's smite / boots' kick damage [min, max] when it has one
  meta              the base lines the tooltip prints above the required level, as the game words them
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import items  # noqa: E402

OUT = items.ROOT / "work" / "wiki" / "bases.json"
TABLES = ("weapons.txt", "armor.txt", "misc.txt")
MISC_TYPES = {"ring", "amul", "jewl", "bowq", "xboq"}
TIER = re.compile(r"\s*\((\d+|Sacred)\)\s*$")
num = items.num


class Types:
    """itemtypes.txt: names, the Equiv chain and the class an item type belongs to."""

    def __init__(self):
        self.rows = {r["Code"]: r for r in items.read("itemtypes.txt") if r.get("Code")}

    def chain(self, code: str) -> list:
        out, todo = [], [code]
        while todo:
            c = todo.pop(0)
            if c and c not in out and c in self.rows:
                out.append(c)
                todo += [self.rows[c].get("Equiv1", ""), self.rows[c].get("Equiv2", "")]
        return out

    def is_a(self, code: str, kind: str) -> bool:
        return kind in self.chain(code)

    def klass(self, code: str) -> str:
        return next((self.rows[c]["Class"] for c in self.chain(code) if self.rows[c].get("Class")), "")


def pair(r: dict, lo: str, hi: str):
    a, b = num(r.get(lo)), num(r.get(hi))
    return [a, b] if a or b else None


def meta_lines(data: items.Data, rec: dict) -> list:
    """The lines D2 prints between the name and the required level (ItemStats1* strings)."""
    t = data.text
    out = []
    dmg = rec.get("damage", {})
    if "throw" in dmg:
        out.append(items.fill(t("ItemStats1n"), [dmg["throw"][0]]) + f" {t('ItemStast1k')} {dmg['throw'][1]}")
    if "one" in dmg:
        out.append(items.fill(t("ItemStats1l"), dmg["one"]))
    if "two" in dmg:
        out.append(items.fill(t("ItemStats1m"), dmg["two"]))
    if rec.get("defense"):
        lo, hi = rec["defense"]
        out.append(items.fill(t("ItemStats1h"), [(lo, hi)]))
    if rec.get("block"):
        out.append(items.fill(t("ItemStats1r"), [rec["block"]]))
    if rec.get("smite"):
        out.append(items.fill(t("ItemStats1o"), rec["smite"]))
    if rec.get("kick"):
        out.append("Kick Damage: %d to %d" % tuple(rec["kick"]))  # boots: D2 words it with a hardcoded string
    if rec.get("durability"):
        out.append(items.fill(t("ItemStats1d"), [rec["durability"], rec["durability"]]))
    if rec.get("reqdex"):
        out.append(items.fill(t("ItemStats1f"), [rec["reqdex"]]))
    if rec.get("reqstr"):
        out.append(items.fill(t("ItemStats1e"), [rec["reqstr"]]))
    return [items.strip(x)[0].strip() for x in out]


def class_only(data: items.Data, code: str) -> str:
    idx = data.class_index.get(code)
    if idx is None or idx >= len(data.charstats):
        return ""
    return items.strip(data.text(data.charstats[idx].get("StrClassOnly", "")))[0].strip()


def bases(data: items.Data):
    types = Types()
    out = []
    for table in TABLES:
        for r in items.read(table):
            code, tcode = r.get("code", ""), r.get("type", "")
            if r.get("spawnable") != "1" or not code:
                continue
            if table == "misc.txt" and not any(types.is_a(tcode, k) for k in MISC_TYPES):
                continue
            name = data.base_name(code)
            name = [p.strip() for p in name.split("\n") if p.strip()][-1]
            rec = {"code": code, "name": name, "base": TIER.sub("", name), "table": table[:-4],
                   "type": data.types.get(tcode, tcode), "type_code": tcode}
            klass = class_only(data, types.klass(tcode))
            if klass:
                rec["class"] = klass
            tier = items.tier_of(name)
            if tier is not None:
                rec["tier"] = tier
            rec.update(lvl=num(r.get("level")), lvlreq=num(r.get("levelreq")), reqstr=num(r.get("reqstr")),
                       reqdex=num(r.get("reqdex")), speed=num(r.get("speed")), sockets=num(r.get("gemsockets")),
                       durability=0 if r.get("nodurability") == "1" else num(r.get("durability")),
                       width=num(r.get("invwidth")), height=num(r.get("invheight")))
            if table == "weapons.txt":
                dmg = {}
                if r.get("2handed") != "1" or r.get("1or2handed") == "1":
                    if pair(r, "mindam", "maxdam"):
                        dmg["one"] = pair(r, "mindam", "maxdam")
                if r.get("2handed") == "1" and pair(r, "2handmindam", "2handmaxdam"):
                    dmg["two"] = pair(r, "2handmindam", "2handmaxdam")
                if types.is_a(tcode, "thro") and pair(r, "minmisdam", "maxmisdam"):
                    dmg["throw"] = pair(r, "minmisdam", "maxmisdam")
                rec["damage"] = dmg
            elif table == "armor.txt":
                rec["defense"] = pair(r, "minac", "maxac") or [0, 0]
                if types.is_a(tcode, "shie"):
                    rec["block"] = num(r.get("block"))
                    if pair(r, "mindam", "maxdam"):
                        rec["smite"] = pair(r, "mindam", "maxdam")
                elif types.is_a(tcode, "boot") and pair(r, "mindam", "maxdam"):
                    rec["kick"] = pair(r, "mindam", "maxdam")
            rec["meta"] = meta_lines(data, rec)
            out.append(rec)
    first_type = {}
    for rec in out:
        if rec.get("tier") in (1, None):
            first_type.setdefault(rec["base"], rec["type"])
    for rec in out:
        rec["group"] = first_type.get(rec["base"], rec["type"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--show", nargs="*", default=[])
    a = ap.parse_args()
    recs = bases(items.Data())
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("%d bases (%d names) -> %s" % (len(recs), len({r["base"] for r in recs}), out))
    sys.stdout.reconfigure(encoding="utf-8")
    for want in a.show:
        for rec in recs:
            if want.lower() in rec["name"].lower():
                print("\n%s [%s] %s / %s%s lvl %d req %d" % (rec["name"], rec["code"], rec["type"], rec["group"],
                                                          " " + rec["class"] if rec.get("class") else "", rec["lvl"],
                                                          rec["lvlreq"]))
                for ln in rec["meta"]:
                    print("   ", ln)
                print("    sockets %d, speed %d, %dx%d" % (rec["sockets"], rec["speed"], rec["width"], rec["height"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
