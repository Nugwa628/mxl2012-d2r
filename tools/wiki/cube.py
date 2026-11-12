#!/usr/bin/env python3
"""Horadric Cube recipes for the wiki generator (docs/wiki-plan.md): every enabled cubemain row with readable inputs and outputs.

  py -3 tools/wiki/cube.py                   write work/wiki/cube.json
        [--out FILE]                         another output file
        [--show TEXT ...]                    also print the rows whose description contains TEXT

Reads the built cubemain.txt (work/mod/data/global/excel) and names its references the way the player reads them
(tools/wiki/items.py Data: base names from weapons / armor / misc, item type names, unique and set names from their index
strings). One record per enabled row, in table order:

  row          the one-based data row (header excluded, as tools/cube_reference_audit.py counts)
  description  the description cell; family: it without counts and shrine names (the rows a page groups)
  section      the wiki section the family belongs to (SECTIONS)
  inputs       readable inputs ("2 x Arcane Shard", "any Weapon (unique, non-ethereal)")
  outputs      readable outputs, each {"item": text, "mods": [stat lines]}; the mods print as the tooltip does
  condition    the op / param / value requirement as text, "" when the row has none
  class, min_diff, numinputs, decoy (the row only intercepts items for the next rows: the cube gives them back unchanged)
  codes        the raw input / output cells
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import items  # noqa: E402

ROOT = items.ROOT
OUT = ROOT / "work" / "wiki" / "cube.json"
INPUTS = tuple(f"input {i}" for i in range(1, 8))
OUTPUTS = (("output", ""), ("output b", "b "), ("output c", "c "))
QUALITY = {"low": "low quality", "nor": "normal", "hiq": "superior", "mag": "magic", "set": "set", "rar": "rare",
           "uni": "unique", "crf": "crafted", "tmp": "honorific"}
IN_WORDS = {"nos": "no sockets", "sock": "socketed", "noe": "non-ethereal", "eth": "ethereal", "upg": "upgradable",
            "bas": "basic", "exc": "exceptional", "eli": "elite", "nru": "not a runeword", "id": "identified"}
OUT_WORDS = {"mod": "keeps its modifiers", "uns": "socket fillers destroyed", "rem": "socket fillers returned",
             "reg": "rerolled", "eth": "ethereal", "exc": "exceptional", "eli": "elite", "rep": "repaired",
             "rch": "recharged"}
CLASSES = {"ama": "Amazon", "sor": "Sorceress", "nec": "Necromancer", "pal": "Paladin", "bar": "Barbarian", "dru": "Druid",
           "ass": "Assassin"}
DIFFICULTY = {"1": "Nightmare (Terror)", "2": "Hell (Destruction)"}
OP_TEXT = {3: "{who} {stat} above {v}", 4: "{who} {stat} below {v}", 5: "{who} {stat} not {v}", 6: "{who} {stat} = {v}",
           7: "{who} base {stat} above {v}", 8: "{who} base {stat} below {v}", 9: "{who} base {stat} not {v}",
           10: "{who} base {stat} = {v}", 15: "{who} {stat} above {v}", 16: "{who} {stat} below {v}",
           17: "{who} {stat} not {v}", 18: "{who} {stat} = {v}"}
STAT_LABEL = {"level": "level", "game_craftpoints": "Crafting Points", "blessings_counter": "blessings",
              "item_hasbeenduped": "duplicated", "item_is_honorific": "honorific"}
# description families -> wiki section; first match wins (Brother Laz's cube page names its sections this way)
SECTIONS = (
    (r"disenchant|shards to container", "Disenchanting"),
    (r"uptier", "Uptier recipes"),
    (r"shrine crafting", "Shrine crafting"),
    (r"blessings", "Shrine blessings"),
    (r"affix crystal|^honorific |^full honorifics|apple$", "Mystic Orbs"),
    (r"jewelcrafting", "Jewelcrafting"),
    (r"alchemy", "Alchemy"),
    (r"zomghelp|reroll|enchant|shatter|affix burn|chaos|random modifier|socket creation|upgrade and reroll|veteran",
     "Item quality and modifiers"),
    (r"rune (up|down)grade|gem upgrade|upgrade: ", "Gems and runes"),
    (r"challenge|dragon|black road|stardragon|toraja|edyrem|hard mode|level challenge|witch|window|startle|massacre|"
     r"nu-att|dogma|i am |create quest", "Challenges and uberquests"),
    (r"", "Miscellaneous"),
)
FAMILY = (r":\s*[A-Z][a-z]+:\s*\d+ charges?$", r"\d+")


def num(v) -> int:
    return items.num(v)


class Names:
    """Readable names of the codes a cube cell can hold."""

    def __init__(self, data: items.Data):
        self.data = data
        self.uniques = {}
        for table in ("uniqueitems.txt", "setitems.txt"):
            for r in items.read(table):
                if r.get("index"):
                    shown = items.strip(data.text(r['index']))[0].strip()
                    if not shown:
                        continue
                    parts = [p.strip() for p in shown.split("\n") if p.strip()]
                    self.uniques.setdefault(r['index'],parts[-1])
        self.stat_by_id = {num(r["*ID"]): name for name, r in data.stats.items()}

    def base(self, code: str) -> str:
        row = self.data.bases.get(code)
        if row is None:
            return ""
        return self.data.base_name(code)

    def thing(self, code: str) -> tuple[str, str]:
        """(name, kind): kind is item / type / unique / special."""
        if code in self.data.bases:
            return self.base(code), "item"
        if code in self.data.types:
            return self.data.type_label(code), "type"
        if code in self.uniques:
            return self.uniques[code], "unique"
        if code == "any":
            return "any item", "special"
        if code == 'Cow Portal':
            return 'Cow Portal', 'special'
        raise ValueError('Unresolved cube reference: '+code)

    def stat(self, sid: int) -> str:
        name = self.stat_by_id.get(sid, "stat %d" % sid)
        return STAT_LABEL.get(name, name)


def last_line(text: str) -> str:
    """The name line of a multi-line string (D2 draws the lines from the last one up)."""
    parts = [p.strip() for p in text.split("\n") if p.strip()]
    return parts[-1] if parts else ""


def strings_bare(cell: str) -> str:
    return items.strings_ns.bare(cell)


def cells(cell: str) -> list[str]:
    return [p.strip() for p in cell.strip().strip('"').split(",") if p.strip()]


def describe_input(names: Names, cell: str) -> str:
    parts = cells(cell)
    if not parts:
        return ""
    name, kind = names.thing(parts[0])
    qty, words = 1, []
    for w in parts[1:]:
        key, _, val = w.partition("=")
        if key == "qty":
            qty = num(val)
        elif key == "any":
            continue
        elif key in QUALITY:
            words.append(QUALITY[key])
        elif key == "sock" and val:
            words.append(f"{val} sockets")
        elif key in IN_WORDS:
            words.append(IN_WORDS[key])
        else:
            words.append(w)
    if kind == "type":
        name = "any " + name
    text = name + (f" ({', '.join(words)})" if words else "")
    return f"{qty} x {text}" if qty > 1 else text


def describe_output(names: Names, cell: str) -> str:
    parts = cells(cell)
    if not parts:
        return ""
    head = parts[0]
    if head == "useitem":
        name = "the item"
    elif head == "usetype":
        name = "the item rerolled"
    else:
        name = names.thing(head)[0]
    qty, words = 1, []
    for w in parts[1:]:
        key, _, val = w.partition("=")
        if key == "qty":
            qty = num(val)
        elif key in QUALITY:
            words.append(QUALITY[key])
        elif key == "sock":
            words.append(f"{val} sockets" if val else "socketed")
        elif key == "pre" or key == "suf":
            words.append(f"{'prefix' if key == 'pre' else 'suffix'} {val}")
        elif key in OUT_WORDS:
            words.append(OUT_WORDS[key])
        else:
            words.append(w)
    text = name + (f" ({', '.join(words)})" if words else "")
    return f"{qty} x {text}" if qty > 1 else text


def output_mods(data: items.Data, row: dict, prefix: str) -> list[str]:
    """The stat lines of an output's five mods, a mod below 100% chance marked with it."""
    out = []
    for i in range(1, 6):
        code = row.get(f"{prefix}mod {i}", "")
        if not code:
            continue
        quad = [code, row.get(f"{prefix}mod {i} param", ""), row.get(f"{prefix}mod {i} min", ""),
                row.get(f"{prefix}mod {i} max", "")]
        lines = items.tooltip(data, [quad])[0]
        chance = num(row.get(f"{prefix}mod {i} chance"))
        tag = f" ({chance}% chance)" if 0 < chance < 100 else ""
        out += [ln + tag for ln in lines]
    return out


def condition(names: Names, row: dict) -> str:
    op = num(row.get("op"))
    if not op:
        return ""
    param, value = num(row.get("param")), num(row.get("value"))
    stat = names.stat(param)
    if op == 3 and stat == "Crafting Points":
        return f"more than {value} Crafting Points"
    if op == 16 and stat == "blessings" and value <= 1:
        return "the item has not been blessed yet"
    if op == 15 and stat == "honorific":
        return "honorific items only"
    if op in (6, 10) and stat == "level":
        return f"character level {value}"
    if op == 18 and stat == "duplicated" and value == 0:
        return "the item has not been duplicated yet"
    if op == 28:
        return "quest item recipe"
    if op in OP_TEXT:
        who = "character" if op < 15 else "item"
        return OP_TEXT[op].format(who=who, stat=stat, v=value)
    return f"op {op} ({param}, {value})"


def family(desc: str) -> str:
    text = re.sub(FAMILY[0], "", re.sub(r"\s+", " ", desc.strip()))
    return re.sub(FAMILY[1], "N", text).strip()


def section(fam: str, data: items.Data, codes: list) -> str:
    """The family's section; a row that takes a Mystic Orb (item type asaa) is an orb recipe whatever its description."""
    if any(data.bases.get(cells(c)[0] if cells(c) else "", {}).get("type") == "asaa" for c in codes):
        return "Mystic Orbs"
    for pattern, name in SECTIONS:
        if re.search(pattern, fam, re.I):
            return name
    return "Miscellaneous"


def recipes(data: items.Data):
    names = Names(data)
    out = []
    last_desc = ""
    for n, r in enumerate(items.read("cubemain.txt"), 1):
        if r.get("enabled") != "1":
            continue
        desc = r.get("description", "").strip() or last_desc
        last_desc = desc
        inputs = [describe_input(names, r.get(c, "")) for c in INPUTS]
        inputs = [x for x in inputs if x]
        outputs = []
        for col, prefix in OUTPUTS:
            text = describe_output(names, r.get(col, ""))
            if not text:
                continue
            o = {"item": text}
            mods = output_mods(data, r, prefix)
            if mods:
                o["mods"] = mods
            lvl = {k: num(r.get(prefix + k)) for k in ("lvl", "plvl", "ilvl") if num(r.get(prefix + k))}
            if lvl:
                o["level"] = lvl
            outputs.append(o)
        fam = family(desc)
        rec = {"row": n, "description": desc, "family": fam, "section": section(fam, data, [r.get(c, "") for c in INPUTS]), "inputs": inputs,
               "outputs": outputs, "condition": condition(names, r), "numinputs": num(r.get("numinputs"))}
        if "decoy" in desc.lower() or "dev-null" in desc.lower():
            rec["decoy"] = True
        if r.get("class"):
            rec["class"] = CLASSES.get(r["class"], r["class"])
        if r.get("min diff") in DIFFICULTY:
            rec["min_diff"] = DIFFICULTY[r["min diff"]]
        rec["codes"] = {"inputs": [r[c] for c in INPUTS if r.get(c)],
                        "outputs": [r[c] for c, _p in OUTPUTS if r.get(c)]}
        orbs = [cells(c)[0] for c in rec['codes']['inputs']
                if data.bases.get(cells(c)[0],{}).get('type') == 'asaa']
        if orbs:
            if len(orbs) != 1:
                raise ValueError('Expected one orb reagent')
            code = orbs[0]
            rec['orb'] = {'code':code, 'name':data.base_name(code),
                          'description':items.strip(data.shown(data.bases[code].get('spelldescstr','')))[0]}
        out.append(rec)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--show", nargs="*", default=[])
    a = ap.parse_args()
    recs = recipes(items.Data())
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(recs, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print("%d enabled rows -> %s" % (len(recs), out))
    sys.stdout.reconfigure(encoding="utf-8")
    for want in a.show:
        for rec in recs:
            if want.lower() in rec["description"].lower():
                print("\nrow %d %s [%s]%s" % (rec["row"], rec["description"], rec["section"],
                                              " " + rec["condition"] if rec["condition"] else ""))
                print("  in: " + " + ".join(rec["inputs"]))
                for o in rec["outputs"]:
                    print("  out: " + o["item"] + "".join("\n     " + m for m in o.get("mods", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
