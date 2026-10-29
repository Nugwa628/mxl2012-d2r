# Copied from another port's vanilla113.py; D2R_BASE points at a read-only D2R extract.
"""The "1.13c view" of the vanilla tables, built from D2R's own extracted tables.

The build used to read Blizzard's classic 1.13c tables (`..\\D2R Modding Tools\\D2Compare_102\\TXT\\113c`), which a D2R-only
PC does not have and which we do not ship. D2R's tables are those tables plus the rows D2R appended, so the vanilla
rows are the first rows of D2R's (`extract/d2r/<build>/data/global/excel/base`, written by tools/casc_extract.py).
`load()` returns one table cut to its 1.13c row count, with the few cells the readers depend on and D2R changed put
back to their 1.13c value.

What the readers use (so what the view has to get right; every other column is D2R's value):
  * tools/mxl_names.py     the key column of 33 tables: its row count, the row order, and the key text (unused
                           slots, "Sword Mastery", the Nihlathak missiles, misc / cubemain labels);
  * tools/func_slots*.py   the key plus the srv/clt function slot columns of skills and missiles, whose 1.13c numbers
                           are what the audit compares D2R against.

misc.txt `name` and cubemain.txt `description` are comment columns (D2R's data guide); mxl_names.py gives Median's vanilla
rows the label of the vanilla row, which is now D2R's wording (rows line up: same code / input / output) instead of 1.13c's.

`tools/vanilla113.py` itself is the record of what D2R changed in those cells: `py -3 tools/vanilla113.py` prints the
view's row counts and the overrides.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402  (.mxl-local.json defaults, D2R extraction)

D2R_BASE = localconfig.default_d2r_extract() / "data" / "global" / "excel" / "base"

# Rows after the header in the 1.13c tables (separator rows such as "Expansion" included), as counted by
# mxl_names.read_tsv. Derived once from the 1.13c files; D2R appended rows to the end of every one of these.
ROW_COUNTS = {
    "cubemain": 151, "difficultylevels": 3, "events": 13, "inventory": 33, "itemratio": 6, "itemstatcost": 359,
    "levels": 138, "lvlmaze": 82, "lvlprest": 1092, "lvlsub": 35, "lvltypes": 37, "misc": 152, "missiles": 684,
    "monai": 148, "monlvl": 111, "monplace": 37, "monprop": 13, "monseq": 1010, "monsounds": 141, "monstats": 735,
    "monstats2": 610, "montype": 59, "monumod": 43, "objects": 574, "overlay": 294, "pettype": 20, "properties": 269,
    "sets": 33, "shrines": 23, "skilldesc": 221, "skills": 357, "states": 185, "superuniques": 67,
}

# D2R renamed or moved a column; the view carries the 1.13c name (shrines: D2R's "Name" is the shrine's name,
# "*Shrine Type" the Recharge / Booster group).
HEADER_113C = {"shrines": {"*Shrine Type": "Shrine Type", "Name": "Shrine name"}}

# Key text of rows where D2R put another name into a 1.13c row: table -> (key column, {row after the header: 1.13c key}).
# itemstatcost: slots 1.13c left unused and D2R filled (mxl_names.py moves a Median row out of such a slot; row 205 on
# is "unused" + the row number - 1). skills / states / skilldesc: D2R's "Blade Mastery" is 1.13c's "Sword Mastery".
# missiles: D2R fixed the spelling of Nihlathak. monstats: cr_lancer8 became cr_lancer9.
KEY_113C = {
    "itemstatcost": ("Stat", {**{r: f"unused{r}" for r in (*range(183, 188), *range(189, 194), 200, 202, 203)},
                              **{r: f"unused{r - 1}" for r in range(205, 214)}}),
    "states": ("state", {74: "swordmastery"}),
    "skills": ("skill", {127: "Sword Mastery"}),
    "skilldesc": ("skilldesc", {127: "sword mastery"}),
    "missiles": ("Missile", {606: "nehlithakcontrol", 607: "nehlithakswoosh", 608: "nehlithakdebris1",
                             609: "nehlithakdebris2", 610: "nehlithakdebris3", 611: "nehlithakdebris4",
                             612: "nehlithakglow", 617: "nehlithakhole", 618: "nehlithakholelight",
                             620: "nehlithakglow2", 621: "nehlithakbonechips"}),
    "monstats": ("Id", {724: "cr_lancer8"}),
}

# inventory: D2R dropped the Guild Vault and Trophy Case rows and added Warlock ones, so no prefix of D2R's table is the
# 1.13c list. Only the class column is read; the other columns of the view are empty.
INVENTORY_CLASSES = (
    "Amazon", "Sorceress", "Necromancer", "Paladin", "Barbarian", "Monster", "Trade Page 1", "Trade Page 2",
    "Bank Page 1", "Transmogrify Box Page 1", "Guild Vault Page 1", "Trophy Case Page 1", "Expansion",
    "Big Bank Page 1", "Hireling", "Druid", "Assassin", "Amazon2", "Sorceress2", "Necromancer2", "Paladin2",
    "Barbarian2", "Monster2", "Trade Page 1-2", "Trade Page 2-2", "Bank Page2", "Transmogrify Box2",
    "Guild Vault Page2", "Trophy Case Page2", "Big Bank Page2", "Hireling2", "Druid2", "Assassin2",
)

# Function slot cells (skills.txt srv*/clt* columns, missiles.txt p*Func / *Calc1 columns) D2R changed in a 1.13c row:
# table -> {(row after the header, column): 1.13c value}. These are the slots tools/func_slots.py audits (docs/function-slots.md);
# D2R's own values would make the audit compare D2R with itself.
CELLS_113C = {
    "skills": {
        (19, "cltstfunc"): "", (34, "cltdofunc"): "22", (133, "srvstfunc"): "", (147, "srvstfunc"): "",
        (178, "cltstfunc"): "", (215, "srvstfunc"): "64", (215, "srvdofunc"): "109", (244, "cltdofunc"): "",
        (285, "cltstfunc"): "82", (317, "cltstfunc"): "", (319, "cltstfunc"): "", (323, "cltstfunc"): "",
        (328, "srvstfunc"): "37", (328, "srvdofunc"): "109",
    },
    "missiles": {
        (55, "pSrvDmgFunc"): "", (85, "pCltHitFunc"): "12", (115, "pCltDoFunc"): "11", (233, "pCltHitFunc"): "26",
        (234, "pSrvDmgFunc"): "", (283, "pCltHitFunc"): "11", (470, "pCltDoFunc"): "11", (648, "CltCalc1"): "",
    },
}
# Columns D2R added that 1.13c's tables do not have; the view leaves them out so the readers see the 1.13c layout
# (skills / missiles: tools/func_slots.py skips a slot column the 1.13c table lacks; objects: "Class" is D2R's new first
# column, 1.13c's first column "Name" is D2R's second).
NOT_113C_COLUMNS = {"skills": ("srvstopfunc", "cltstopfunc"), "objects": ("Class",),
                    "missiles": ("pCltSrcTownFunc", "pCltTgtTownFunc", "pCltDmgFunc")}


def load(table: str, read=None, d2r: Path | None = None) -> tuple[list[str], list[list[str]]]:
    """(header, rows) of the 1.13c view of `table` (no ".txt"). `read` is the caller's own table reader,
    path -> (header, rows), so the cells are split the way that caller always split them."""
    if read is None:
        from mxl_names import read_tsv
        read = lambda p: read_tsv(p, "utf-8-sig")
    header, rows = read((d2r or D2R_BASE) / f"{table}.txt")
    header = [HEADER_113C.get(table, {}).get(c, c) for c in header]
    if table == "inventory":
        k = header.index("class")
        return header, [[*[""] * k, name, *[""] * (len(header) - k - 1)] for name in INVENTORY_CLASSES]
    rows = [list(r) for r in rows[:ROW_COUNTS[table]]]
    for r in rows:
        r.extend([""] * (len(header) - len(r)))
    if table in KEY_113C:
        col, keys = KEY_113C[table]
        for i, key in keys.items():
            rows[i][header.index(col)] = key
    for (i, col), value in CELLS_113C.get(table, {}).items():
        rows[i][header.index(col)] = value
    if table == "objects":  # D2R keeps the "Expansion" separator row's label in the new "Class" column
        for r in rows:
            if r[header.index("Class")] == "Expansion":
                r[header.index("Name")] = "Expansion"
    drop = {header.index(c) for c in NOT_113C_COLUMNS.get(table, ()) if c in header}
    if drop:
        header = [c for j, c in enumerate(header) if j not in drop]
        rows = [[c for j, c in enumerate(r) if j not in drop] for r in rows]
    return header, rows


if __name__ == "__main__":
    for t, n in sorted(ROW_COUNTS.items()):
        print(f"{t:18} {n:5d} rows" + (f", {len(KEY_113C[t][1])} key overrides" if t in KEY_113C else "")
              + (f", {len(CELLS_113C[t])} slot cells" if t in CELLS_113C else ""))
