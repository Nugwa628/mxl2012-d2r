"""One extra tooltip line on the 20 crafting shrines (all 200 charge rows, both string folders): what the shrine's Cube recipes give.
A deliberate departure from Median XL 2012, whose tooltip is only the name and the verse (docs/bugs.md #563).

    <blue> Cube: Strength, Crushing Blow      (the bottom line of the tooltip)

The tooltip is the item's name string, whose lines run bottom to top, so the new line goes first with its own colour code, in front of
the unchanged verse (`ÿc3Cube: ...\\nÿc8verse2\\nverse1\\nname`). The stats are read from the shrine's own cubemain rows: a recipe mod with no
entry in MOD_LABELS stops the build. A label of None leaves a stat out on purpose (OMITTED says why). Kinds with no stat at all in their
recipes (5 of the 20 in v005: only the sockets and doubled orbs every shrine craft gives) say that instead (NO_STATS).

Stat names use D2R's own translation where it has the whole word (TRANSLATED); the others and the "Cube:" prefix stay English in every
language, as the verses do.
"""
import argparse
import csv
import glob
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import projtemp  # noqa: E402,F401
import tbl2json  # noqa: E402

KINDS = [chr(65 + k) for k in range(20)]  # A..T, codes `<kind><0-9>+`: 0 = 10 charges ... 9 = 1 charge
CODE = re.compile(r"^([A-T])\d\+$")
PREFIX = "Cube: "
COLOUR = "ÿc3"  # blue, the magic-item colour
MAX_WIDTH = 38  # the shrines' name lines are 25-31 wide and their verses at most 28
STRING_FILES = ("strings/mxl2012/median.json", "strings-legacy/mxl2012/median.json")

# recipe mod -> label on the line; None = left out on purpose (OMITTED says why)
OMITTED = {"uninterrupt": "Gloomy's chance of uninterruptable attacks: too long for the line beside its two main stats"}
MOD_LABELS = {
    "str": "Strength", "str%": "Strength", "crush": "Crushing Blow",
    "dex": "Dexterity", "dex%": "Dexterity", "att%": "Attack Rating",
    "vit": "Vitality", "vit%": "Vitality", "pot-rate": "Apple Healing",
    "enr": "Energy", "enr%": "Energy", "enr-factor": "Energy Factor",
    "dmg-max": "Damage", "dmg-min": "Damage", "dmg%": "Damage",
    "uninterrupt": None, "red-dmg": "Damage Reduced", "ac%": "Defense",
    "dmg-minion": "Minion Damage", "att%-minion": "Minion Attack",
    "hp-minion": "Minion Life", "res-all-minion": "Minion Resists",
    "extra-fire": "Fire Damage", "pierce-fire": "Pierce", "extra-ltng": "Lightning Damage", "pierce-ltng": "Pierce",
    "extra-cold": "Cold Damage", "pierce-cold": "Pierce", "extra-pois": "Poison Damage", "pierce-pois": "Pierce",
    "mana%": "Mana", "gold%": "Gold Find", "mag%": "Magic Find", "reanimate-rand": "Reanimate",
    "res-all": "All Resists", "red-mag": "Magic Reduced"}
# in every shrine craft, or the blessing bookkeeping: never named on a line
SHARED_MODS = {"sock", "desc-honorific", "blessings-counter"}
NO_STATS = "6 Sockets, Doubled Orbs"
# label -> D2R string key with a translation of that whole word (data/local/lng/strings/ui.json)
TRANSLATED = {"Strength": "strchrstr", "Dexterity": "strchrdex", "Vitality": "strchrvit", "Energy": "strchreng", "Mana": "strchrman",
              "Defense": "strchrdef", "Damage": "Damage"}


def kind_labels(rows):
    """{kind: [English labels, in recipe order]} from cubemain rows. Unknown mods stop the build."""
    out = {k: [] for k in KINDS}
    for r in rows:
        kinds = {m[1] for c in range(1, 8) if (m := CODE.match(r.get(f"input {c}", "").split(",")[0]))}
        if not kinds:
            continue
        kind = kinds.pop()
        for n in range(1, 6):
            mod = r.get(f"mod {n}", "")
            if not mod or mod in SHARED_MODS:
                continue
            if mod not in MOD_LABELS:
                raise SystemExit(f"shrine_lines: unknown recipe mod {mod!r} of shrine {kind}: add it to MOD_LABELS")
            label = MOD_LABELS[mod]
            if label is not None and label not in out[kind]:
                out[kind].append(label)
    return out


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def translations(d2r_lng):
    """{label: {locale: word}} for TRANSLATED, the words as D2R has them, without the trailing dot of a few German labels."""
    found = {}
    for path in sorted(glob.glob(str(Path(d2r_lng) / "strings" / "*.json"))):
        for rec in json.loads(Path(path).read_text("utf-8-sig")):
            found.setdefault(rec.get("Key"), rec)
    table = {}
    for label, key in TRANSLATED.items():
        if key not in found:
            raise SystemExit(f"shrine_lines: D2R string {key} ({label}) not found in {d2r_lng}")
        table[label] = {k: v.strip().rstrip(".") for k, v in found[key].items() if k != "Key" and isinstance(v, str) and v.strip()}
    return table


def line(labels, locale, table):
    """The line for one kind and locale, without colour."""
    names = [table.get(lb, {}).get(locale, lb) for lb in labels] if labels else [NO_STATS]
    return PREFIX + ", ".join(names)


def lines_for(rows, table):
    """{kind: {locale: line}}; stops when a line does not fit."""
    labels = kind_labels(rows)
    locales = {loc for t in table.values() for loc in t} or {"enUS"}
    out = {}
    for kind in KINDS:
        out[kind] = {loc: line(labels[kind], loc, table) for loc in locales}
        for loc, text in out[kind].items():
            if display_width(text) > MAX_WIDTH:
                raise SystemExit(f"shrine_lines: {kind} {loc}: {text!r} is wider than {MAX_WIDTH}")
    return out


def with_line(old, new):
    """`old` name string with the blue line in front; a second run replaces the line."""
    if old.startswith(COLOUR + PREFIX):
        old = old.split("\n", 1)[1]
    if not old.startswith("ÿc8"):
        raise SystemExit(f"shrine_lines: unexpected shrine string: {old[:30]!r}")
    return f"{COLOUR}{new}\n{old}"


def apply(data, d2r_lng):
    with (data / "global" / "excel" / "cubemain.txt").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    lines = lines_for(rows, translations(d2r_lng))
    for rel in STRING_FILES:
        path = data / "local" / "lng" / rel
        recs = json.loads(path.read_text("utf-8-sig"))
        done = 0
        for rec in recs:
            m = CODE.match(rec.get("Key", ""))
            if not m:
                continue
            for loc in lines[m[1]]:
                if loc in rec:
                    rec[loc] = with_line(rec[loc], lines[m[1]][loc])
            done += 1
        if done != 200:
            raise SystemExit(f"shrine_lines: {path}: expected 200 shrine strings, got {done}")
        tbl2json.write_json(path, recs)
    for kind in KINDS:
        print(kind, lines[kind]["enUS"])
    print("200 shrine strings x 2 folders")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["apply"])
    ap.add_argument("data", type=Path, nargs="?", default=ROOT / "work/mod/data")
    ap.add_argument("--d2r-lng", type=Path, required=True)
    a = ap.parse_args()
    apply(a.data, a.d2r_lng)
