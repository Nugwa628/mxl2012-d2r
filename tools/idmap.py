r"""ID mapping layer for Median XL 2012 (v005, a classic 1.13c txt mod) -> D2R 3.3 build 93847 (docs/id-mapping.md).

The engine addresses skills, states, stats, missiles, monsters, overlays, ... by ROW INDEX. D2R appended its own rows
after 1.13c's and its code depends on them, so:

  * indexed tables: a mod row below the 1.13c row count keeps its index (it is the vanilla row); the mod's rows
    above it are renumbered to start after D2R's last row. Exception: a slot 1.13c left unused ("unused183") that
    D2R filled and the mod also uses -> the mod row moves to the new range, D2R keeps the slot.
  * itemtypes: D2R inserted `warl` at 67 and its code tests types by fixed number (75 rune, 77 hpot, ...). Every D2R
    row goes to its D2R number, the mod's own types follow; types are referenced by code, so nothing else changes.
    `check_item_type_ids` FAILS THE BUILD when a fixed id differs.
  * function slots: 1.13c slots D2R renumbered (srvdofunc 109 -> 9, ...) are remapped; mod rows on slots D2R took
    for its own functions get a planned free slot (re-implemented by the plugin later).

Txt references are mostly by name (they survive renumbering); `NUMERIC_REFS` lists the columns that hold row numbers
and must be rewritten, `NAME_REFS` the name columns (only renamed keys change there).

Library use (tables lane):
    import idmap
    m = idmap.IdMap.build(mod_excel_dir, d2r_excel_dir)
    m.order("skills")              # [("mod", mod_row) | ("d2r", d2r_index)] in final ID order
    m.new_id("skills", mod_row)    # final ID of a mod row
    m.remap_table("levels", header, rows)   # mod table, in place: numeric refs, own-id column, renames, slots
    rows = idmap.align_item_types(mod_h, mod_rows, d2r_h, d2r_rows)[0]
    errors = idmap.check_built(built_excel_dir, d2r_excel_dir)   # after the migration: non-empty -> fail

CLI:
    py -3 -I tools/idmap.py build --mod <mod excel dir> [--d2r <D2R excel dir>] [--out work/idmap]
          writes idmap.json + report.md; exit 1 when the mod data has a hard conflict the layer cannot fix itself
    py -3 -I tools/idmap.py check --built <built excel dir (base bank)> [--d2r ...]   exit 1 on a fixed-id mismatch
    py -3 -I tools/idmap.py refs [--guide <dataguide/data/files>]   print the reference registry (and diff it with D2R's guide)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402  (.mxl-local.json defaults, D2R extraction)

ROOT = Path(__file__).resolve().parent.parent
# D2R 93847's extracted excel folder (contains base/ for Classic/LoD and the RotW tables). Read-only.
D2R_CANDIDATES = (ROOT / "extract" / "d2r" / "93847" / "data" / "global" / "excel",
                  localconfig.default_d2r_extract() / "data" / "global" / "excel")  # MXL_D2R_EXTRACT, else the machine's extract_dir (read-only)

# ---------------------------------------------------------------------------------------------------------------------
# Engine facts (build 93847; sources: function-slot notes, plugin/src/item_type_ids.cpp, porting-playbook.md)

# Item types D2R.exe 93847 tests by an immediate (call 0x373890(item, N)); 25 call sites, all types >= 67.
D2R_FIXED_TYPE_IDS = {"h2h": 68, "pelt": 73, "rune": 75, "hpot": 77, "apot": 81, "wpot": 82, "scha": 83, "mcha": 84,
                      "gem4": 96}
STAT_SAVE_ID_LIMIT = 511   # 9-bit stat id in the classic/D2R save; 0x1ff ends the list. D2RLoader 1.3.1 saves 16 bits.
STATE_SYNC_LIMIT = 512     # states D2R sends per unit; D2RLoader 1.3.1 syncs wider state ids itself (playbook trap 12)
CLASS_SKILL_SAVE = 30      # bytes per class in the .d2s "if" section; D2RLoader's extended save widens it
ENGINE_AI_ROWS = 155       # D2R AI function table 0x2396e90: a monai row >= 155 has no AI without a plugin
TABLE_ROW_LIMIT = 32768    # rows per table D2R loads
SRVDO_D2R_TAKEN = range(153, 172)  # srvdofunc slots D2R 3.x uses for its newer skills (D2Sigma had them too)
# Vanilla state ids D2R.exe 93847 names by number that Median 2012 repurposed. Found by a scan of the dump (lane states):
# immediate state ids passed in edx to the state test 0x3351b0, 0x3354c0, 0x2d11d0, 0x48e820, 0x46d8f0 and the state stat
# list getter 0x2f5940 (`mxl2012-runs/states/scratch/statescan.py`), plus 65 / 66 / 68 that the damage code 0x44b100 picks
# by the hit's result flags (bug #53). Lane statefaith compared every call site with 1.14d's Game.exe (read statically;
# state test 0x639df0, state set 0x639db0, state stat list 0x6256b0; `mxl2012-runs/statefaith/scratch/`): where 1.14d (our
# proxy for 1.13c) tests / sets / reads the same id in the same situation, Median's row at that id WAS the 1.13c behaviour,
# so it is KEPT there ("keep"); only ids that D2R names in D2R-only code, or that cannot be kept, are MOVED ("move": the
# mod row gets a new id and D2R's row comes back, map_space's `relocate`). Asserts of D2R's code on a kept row are taken by
# plugin guards that keep the 1.13c flow (statelist: 13 / 22, dodgelist: 65 / 66 / 68). docs/id-mapping.md has the table.
# id: (D2R key, decision, D2R code, 1.14d counterpart, reason)
D2R_FIXED_STATES = {
    13: ("blaze", "keep",
         "client trail 0x21edc0 and server 0x551450 read stat 350 of the list as a skill; walk tests 0xf9aac 0x445d38 0x429a67",
         "client 0x4e3ab0 / server 0x5c9d90, same code (list, stat 350 / 351, the skill's missile); tests 0x4807cb 0x5a8499 0x580c38",
         "same functions in 1.14d: shellshocked units ran them in 1.13c; D2R only adds range asserts (bug #50), plugin statelist "
         "skips them, the flow is 1.14d's"),
    22: ("spiderlay", "keep",
         "client 0x221650 / server 0x578680 read stat 350 of the list as a skill; walk tests 0xf9aca 0x445d54, test 0x5b4b9d",
         "client 0x4e2d40 / server 0x5ce4f0 make missile 143 (Median's spidergoolay) with skill 173; tests 0x4807de 0x5a84ae 0x5f46ef",
         "1.13c ran its state-22 code on raptured units; D2R's asserts (bug #52) skipped by plugin statelist; 1.14d's fixed "
         "missile trail is not made by D2R's list-driven version (docs/unported.md)"),
    47: ("sanctuary", "keep", "damage code test 0x452508", "damage code test 0x57beea",
         "same test in 1.14d: the Sanctuary rule met Bear Stance in 1.13c"),
    57: ("attract", "keep", "monster target pick test 0x433fd0", "test 0x56ea43",
         "same test in 1.14d: monsters treated Black Mass targets as Attract targets in 1.13c"),
    65: ("dodge", "keep", "damage code 0x44b100 reads the defender's list (stat 350) on a dodge",
         "damage code 0x57d186 (list 0x6256b0), same flow",
         "same read in 1.14d (a dodge sets or clears no state in either); no list: plugin dodgelist skips D2R's assert (#53)"),
    66: ("avoid", "keep", "damage code 0x44b100 on an avoid", "damage code 0x57d19c", "as 65 (Broadside's lockout state)"),
    68: ("evade", "keep", "damage code list 0x44b148, client 0x106444", "damage code 0x57d210, client 0x4cbe6e",
         "as 65; the 57 monprop `state` cells naming 68 keep it"),
    78: ("throwingmastery", "keep", "client tests 0x27fef9 0x281470 0x28e3e9", "client tests 0x4e91c5 0x4ea6eb 0x4ea8ce",
         "same three tests in 1.14d"),
    84: ("fingermagecurse", "keep", "monster AI test 0x5afb1d", "AI test 0x5fa628", "same test in 1.14d"),
    87: ("slowmissiles", "keep", "missile creation 0x5374d7 tests it and reads stat 161 of its list; client 0x1b7a5d",
         "server 0x59fb51 / client 0x4cd69d, same reads",
         "same code in 1.14d: Lightning Arena slowed missiles in 1.13c; no assert there"),
    93: ("valkyrie", "keep", "set by srvdofunc 16 0x558218", "set 0x5dc32f, test 0x5722b1",
         "same set in 1.14d (no Median skill uses srvdofunc 16)"),
    101: ("holyshield", "keep", "block code 0x347bad (list 0x347bc2, no assert), 5 more tests incl. the HD stats panel 0x14e601c",
          "block code 0x5ceabc / 0x62243b with lists, 7 more tests (classic stats panel)",
          "same code in 1.14d; the HD panel's test is D2R-only UI that shows what the classic panel shows"),
    138: ("fenris_rage", "keep", "monster AI test 0x5c9e26", "AI test 0x5ed572", "same test in 1.14d"),
    143: ("attached", "keep", "set by srvdofunc 129 (Imp Teleport) 0x586a6e 0x586c6e, 9 tests", "set 0x5d1955 0x5d1a43, 8 tests",
          "same sets in 1.14d: attaching Act 5 imps got Median's Ring of Light state in 1.13c"),
    184: ("uberminion", "keep", "Uber AIs set it on their minions 0x5a95b2 0x5aba53 0x5ae5ef, client test 0x1a49c1",
          "Uber AIs set 0x5f8002 0x5fb555 0x5fd1f1, client test 0x4afc2f",
          "same sets in 1.14d: the ubers' minions got Median's Porkulator form in 1.13c"),
}
STATE_DECISIONS = ("keep", "move")
# entity -> vanilla ids whose repurposed mod row gets a new id (D2R's row comes back there)
RELOCATE = {"states": {i for i, v in D2R_FIXED_STATES.items() if v[1] == "move"}}
# entity -> every vanilla id D2R's code names by number, kept or moved: D2R's key there must not be reached by mod references
FIXED_IDS = {"states": set(D2R_FIXED_STATES)}

# 1.13c skill function slots D2R renumbered (func_slots audit): mod value -> D2R value ("" = none).
SLOT_REMAP = {
    ("skills", "srvdofunc"): {"109": "9"},   # MonFrenzy melee + frenzy state; D2R 109 = Townportal O Skill
    ("skills", "srvstfunc"): {"64": "67"},   # MonFrenzy start; D2R 64 = Bind Demon start
    ("skills", "cltstfunc"): {"82": ""},     # Baal Corpse Explode start; D2R's client start table ends at 55
    # desertfireball client hit: D2R's slot 11 is empty and D2R blanked its own row (bug #14, docs/unported.md)
    ("missiles", "pCltHitFunc"): {"11": ""},
}
SLOT_REMAP_WITH = {("skills", "srvstfunc", "37", "srvdofunc", "109"): "67"}  # BloodLordFrenzy: Zeal start + frenzy do
# 1.13c slots whose function D2R dropped (row blank in D2R): the mod rows lose the effect unless the plugin
# re-implements it in a free slot.
SLOT_DROPPED = {
    ("skills", "cltdofunc"): {"22": "Lightning Strike client half (D2R slot empty)"},
}
# 1.13c slots D2R blanked on its own vanilla rows but whose number is kept for the mod (info only, no move):
# the functions for 12 and 26 still exist in D2R's binary (engine-triage #8).
# 11 is empty in D2R: SLOT_REMAP blanks it as D2R did for its own desertfireball.
SLOT_KEEP = {
    ("missiles", "pCltHitFunc"): {"12": "immolationarrow client hit: function still at 12 in D2R",
                                  "26": "fistoftheheavensdelay client hit: function still at 26 in D2R"},
}
# Slots D2R added for its own skills/missiles (no 1.13c skill used them): a mod row there runs D2R's function.
# With D2R's tables at hand this is computed (`IdMap.build`: values D2R's rows use that no 1.13c row used); this list
# is the fallback. srvstfunc 65 is Throw's in both games, 67 is the remap target.
D2R_OWN_SLOTS = {
    ("skills", "srvdofunc"): set(map(str, SRVDO_D2R_TAKEN)),
    ("skills", "srvstfunc"): {"68", "69", "70"},
    ("skills", "cltstfunc"): {"54", "55"},
    ("skills", "cltdofunc"): {"97", "98", "99"},
    ("missiles", "pSrvDmgFunc"): {"15"},
    ("missiles", "CltCalc1"): {"3"},
}
# Free slots inside D2R's dispatch tables for plugin re-implementations (verified empty unless noted).
FREE_SLOTS = {
    ("skills", "srvdofunc"): list(range(172, 191)),   # table 0x238ea00, 191 slots
    ("skills", "srvstfunc"): list(range(71, 91)),     # table 0x238e710, 91 slots (71/72 verified, rest by bound)
    ("skills", "cltdofunc"): [113, 110, 111, 112],    # client do 0x235f7d0, bound 130; another plugin runs 22 from 113
    ("skills", "cltstfunc"): [],                      # table ends at 55: needs a hook, no free slot
    ("missiles", "pSrvHitFunc"): list(range(61, 71)),  # 0x2391030, bound 71, 61-70 empty
    ("missiles", "pCltHitFunc"): [6, 7, 20],          # 0x2358710, bound 81; 6/7/20 empty
    ("missiles", "pCltDoFunc"): [14],
    ("missiles", "pSrvDoFunc"): [46],
}
SKILL_SLOT_COLS = ("srvstfunc", "srvdofunc", "srvstopfunc", "srvprgfunc1", "srvprgfunc2", "srvprgfunc3",
                   "cltstfunc", "cltdofunc", "cltstopfunc", "cltprgfunc1", "cltprgfunc2", "cltprgfunc3")
MISSILE_SLOT_COLS = ("pSrvDoFunc", "pSrvHitFunc", "pCltDoFunc", "pCltHitFunc", "pSrvDmgFunc", "SrvCalc1", "CltCalc1")

# ---------------------------------------------------------------------------------------------------------------------
# The 1.13c view (tools/vanilla113.py): D2R's base tables are 1.13c's plus appended rows.

# Raw rows after the header in 1.13c (separator rows included).
ROW_COUNTS_113C = {
    "cubemain": 151, "difficultylevels": 3, "events": 13, "itemratio": 6, "itemstatcost": 359, "levels": 138,
    "lvlmaze": 82, "lvlprest": 1092, "lvlsub": 35, "lvltypes": 37, "misc": 152, "missiles": 684, "monai": 148,
    "monlvl": 111, "monplace": 37, "monprop": 13, "monseq": 1010, "monsounds": 141, "monstats": 735,
    "monstats2": 610, "montype": 59, "monumod": 43, "objects": 574, "overlay": 294, "pettype": 20, "properties": 269,
    "sets": 33, "shrines": 23, "skilldesc": 221, "skills": 357, "states": 185, "superuniques": 67,
}
# Keys D2R changed in a 1.13c row: table -> {raw row: 1.13c key}.
KEY_113C = {
    "itemstatcost": {**{r: f"unused{r}" for r in (*range(183, 188), *range(189, 194), 200, 202, 203)},
                     **{r: f"unused{r - 1}" for r in range(205, 214)}},
    "states": {74: "swordmastery"},
    "skills": {127: "Sword Mastery"},
    "missiles": {606: "nehlithakcontrol", 607: "nehlithakswoosh", 608: "nehlithakdebris1", 609: "nehlithakdebris2",
                 610: "nehlithakdebris3", 611: "nehlithakdebris4", 612: "nehlithakglow", 617: "nehlithakhole",
                 618: "nehlithakholelight", 620: "nehlithakglow2", 621: "nehlithakbonechips"},
    "monstats": {724: "cr_lancer8"},
}
# Function slot cells D2R changed in a 1.13c row: table -> {(raw row, column): 1.13c value}.
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
UNUSED = re.compile(r"^(unused\d*|not used)$", re.I)


@dataclass(frozen=True)
class Entity:
    """An id space: rows of `table`, identity = record index. `own_id` is a column that repeats the index."""
    name: str
    key: str
    own_id: str | None = None


# Indexed tables (engine reads them by row number). monstats2 is its own id space (monstats.MonStatsEx names it).
ENTITIES = {e.name: e for e in (
    Entity("skills", "skill", "Id"), Entity("states", "state", "id"), Entity("itemstatcost", "Stat", "ID"),
    Entity("missiles", "Missile", "Id"), Entity("monstats", "Id", "hcIdx"), Entity("monstats2", "Id"),
    Entity("overlay", "overlay"), Entity("properties", "code"), Entity("levels", "Name", "Id"),
    Entity("objects", "Name", "Id"), Entity("superuniques", "Superunique", "hcIdx"), Entity("events", "event"),
    Entity("pettype", "pet type", "idx"), Entity("montype", "type"), Entity("monumod", "uniquemod", "id"),
    Entity("monprop", "Id"), Entity("monsounds", "Id"), Entity("monai", "AI"), Entity("lvltypes", "Name", "Id"),
    Entity("lvlprest", "Name", "Def"), Entity("lvlmaze", "Name"), Entity("lvlsub", "Name"),
    Entity("objgroup", "GroupName"), Entity("shrines", "Name"), Entity("soundenviron", "Handle"),
    Entity("belts", "name"), Entity("playerclass", "Player Class"), Entity("charstats", "class"),
)}
# Mod rows (not vanilla ones) on pCltDoFunc 11 that are corpse explosions: D2R split 1.13c's 11 and moved the corpse
# explosion to 69 (vanilla corpseexplosion row); the others (grimward*stop, andydebris*, ...) stay on D2R's 11.
CORPSE_EXPLOSION = re.compile(r"corpse.?explo", re.I)

# Columns holding ROW NUMBERS of an id space: (table, column regex, entity, condition). The condition is
# (column, predicate) on the same row; None = always. These cells must be rewritten with new ids.
NUMERIC_REFS = [
    ("levels", r"Vis[0-7]|Depend", "levels", None),
    ("levels", r"LevelType", "lvltypes", None),
    ("levels", r"ObjGrp[0-7]", "objgroup", None),
    ("levels", r"SoundEnv", "soundenviron", None),
    ("lvlprest", r"LevelId", "levels", None),
    ("lvlmaze", r"Level", "levels", None),
    ("shrines", r"LevelMin", "levels", None),
    ("objgroup", r"ID[0-7]", "objects", None),
    ("hireling", r"Class|Seller", "monstats", None),
    ("pettype", r"mclass[1-4]", "monstats", None),
    ("superuniques", r"Mod[1-3]", "monumod", None),
    ("skills", r"sumumod", "monumod", None),
    ("weapons|armor|misc", r"missiletype", "missiles", None),
    ("weapons|armor|misc", r"belt", "belts", None),
    ("states", r"gfxclass", "monstats", ("gfxtype", lambda v: v == "1")),
    ("missiles", r"sHitPar1", "monstats", ("pSrvHitFunc", lambda v: v == "6")),  # hit 6 spawns monster sHitPar1
    ("cubemain", r"param", "itemstatcost", ("op", lambda v: v not in ("", "0"))),
]
# Columns holding KEY NAMES of an id space (D2R's data guide + 1.13c names): renumbering does not touch them, only
# renamed keys (D2R spelling, collisions) do.
NAME_REFS = [
    ("books", r"ScrollSkill|BookSkill", "skills"), ("charstats", r"StartSkill|Skill ?\d+", "skills"),
    ("hireling", r"Skill[1-6]", "skills"), ("missiles", r"Skill", "skills"), ("monsounds", r"CvtSk[1-3]", "skills"),
    ("monstats", r"Skill[1-8]|SkillDamage", "skills"), ("monstats2", r"ResurrectSkill", "skills"),
    ("skills", r"sumskill[1-5]|reqskill[1-3]", "skills"), ("states", r"skill", "skills"),
    ("missiles", r"ExplosionMissile|SubMissile[1-3]|HitSubMissile[1-4]|CltSubMissile[1-3]|CltHitSubMissile[1-4]",
     "missiles"),
    ("monstats", r"Miss(A1|A2|S1|S2|S3|S4|C|SQ)", "missiles"), ("skilldesc", r"descmissile[1-3]", "missiles"),
    ("skills", r"srvmissile[a-c]?|cltmissile[a-d]?", "missiles"), ("states", r"missile", "missiles"),
    ("misc", r"state|cstate[12]", "states"),
    ("skills", r"aurastate|auratargetstate|passivestate|State[1-3]", "states"),
    ("itemstatcost", r"op base|op stat[1-3]|maxstat", "itemstatcost"), ("misc", r"stat[1-3]", "itemstatcost"),
    ("properties", r"stat[1-7]", "itemstatcost"), ("skills", r"aurastat[1-6]|passivestat\d+", "itemstatcost"),
    ("states", r"stat", "itemstatcost"),
    ("levels", r"mon\d+|nmon\d+|umon\d+|cmon\d+", "monstats"), ("monequip", r"monster", "monstats"),
    ("monstats", r"BaseId|NextInClass|spawn|minion[12]", "monstats"), ("npc", r"npc", "monstats"),
    ("skills", r"summon", "monstats"), ("superuniques", r"Class", "monstats"),
    ("monpreset", r"Place", "monstats|superuniques"),
    ("monstats", r"MonStatsEx", "monstats2"),
    ("missiles", r"ProgOverlay", "overlay"),
    ("skills", r"srvoverlay|sumoverlay|tgtoverlay|prgoverlay|castoverlay|cltoverlay[ab]|ItemCastOverlay", "overlay"),
    ("states", r"overlay[1-4]|pgsvoverlay|castoverlay|removerlay", "overlay"),
    ("itemstatcost", r"itemevent[12]", "events"), ("skills", r"auraevent\d|auratgtevent", "events"),
    ("states", r"cltevent", "events"), ("monpet", r"consumestat\d|BoundStat\d", "itemstatcost"),
    ("monstats2", r"SpawnUniqueMod", "monumod"), ("objpreset", r"ObjectClass", "objects"),
    ("wanderingmon", r"class", "monstats"),
    ("actinfo", r"town|start|classlevelrangestart|classlevelrangeend|waypoint\d", "levels"),
    ("skills", r"charclass", "playerclass"), ("hireling", r"equivalentcharclass", "playerclass"),
    ("itemtypes", r"StaffMods|Class", "playerclass"), ("sets", r"UIClass", "playerclass"),
    ("cubemain", r"class", "playerclass"), ("magicprefix|magicsuffix|automagic|shareditemmods", r"classspecific|class", "playerclass"),
    ("monstats", r"AI", "monai"), ("monstats", r"MonProp", "monprop"),
    ("monstats", r"MonSound|UMonSound", "monsounds"), ("superuniques", r"MonSound", "monsounds"),
    ("monstats", r"MonType", "montype"), ("montype", r"equiv[1-3]", "montype"), ("monumod", r"exclude[12]", "montype"),
    ("skills", r"pettype", "pettype"), ("skills", r"skilldesc", "skilldesc"),
]
# Formula functions that name a row in quotes: skill('Fire Ball'.blvl), miss('x'.range), stat('item_x'.accr).
FORMULA_REF = re.compile(r"\b(skill|miss|stat)\('([^'.]*)")
FORMULA_ENTITY = {"skill": "skills", "miss": "missiles", "stat": "itemstatcost"}
# Property slots in item / affix / recipe tables: (code, param, min, max) column groups.
PROPERTY_TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic",
                   "rareprefix", "raresuffix", "qualityitems", "lowqualityitems", "gems", "cubemain", "monprop")
# Stat tooltip functions whose parameter is a skill: 15 on-event, 16 aura, 24 charges, 27/28 +skill.
SKILL_PARAM_DESCFUNCS = {"15", "16", "24", "27", "28"}


# ---------------------------------------------------------------------------------------------------------------------
# Table IO

def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    """(header, rows), rows padded to the header. D2R's files are UTF-8, 1.13c mods are Latin-1. A cell holding a
    line break (Median 2012's objects.txt row 250 description) splits its row: a short line is joined with the next
    while that still fits the header's column count."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    lines = text.splitlines()
    header = lines[0].split("\t") if lines else []
    tabs = len(header) - 1
    rows, i = [], 1
    while i < len(lines):
        line = lines[i]
        while (line.strip() and line.count("\t") < tabs and i + 1 < len(lines)
               and line.count("\t") + lines[i + 1].count("\t") <= tabs):
            i += 1
            line += " " + lines[i]
        r = line.split("\t")
        rows.append(r + [""] * (len(header) - len(r)))
        i += 1
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    return header, rows


def is_record(row: list[str]) -> bool:
    """A record (an id): every row except "Expansion" separators (label in the FIRST column) and empty lines.
    Blank-key rows ARE records: Median 2012's superuniques row 42 has "Expansion" under Name only, and its .bin
    counts it (84 records), so Median's superuniques from 43 on sit one id above vanilla's."""
    return bool(row) and any(c.strip() for c in row) and row[0] != "Expansion"


def records(rows: list[list[str]]) -> list[list[str]]:
    return [r for r in rows if is_record(r)]


def col(header: list[str], name: str) -> int | None:
    low = name.lower()
    return next((i for i, h in enumerate(header) if h.lower() == low), None)


def bin_records(txt: Path) -> int | None:
    """Record count in the compiled .bin next to a .txt (u32 at offset 0), None without one."""
    b = txt.with_suffix(".bin")
    if not b.exists() or b.stat().st_size < 4:
        return None
    return int.from_bytes(b.read_bytes()[:4], "little")


def find_d2r(arg: str | None) -> Path | None:
    for p in ([Path(arg)] if arg else []) + ([Path(os.environ["MXL2012_D2R_EXCEL"])]
                                              if os.environ.get("MXL2012_D2R_EXCEL") else []) + list(D2R_CANDIDATES):
        if (p / "base" / "skills.txt").exists():
            return p
    return None


class D2RData:
    """D2R's tables: base (Classic/LoD) bank and RotW bank (`excel/`)."""

    def __init__(self, excel: Path):
        self.excel = excel
        self._cache: dict[tuple[str, str], tuple[list[str], list[list[str]]] | None] = {}

    def table(self, name: str, bank: str = "base"):
        k = (name, bank)
        if k not in self._cache:
            p = (self.excel / bank / f"{name}.txt") if bank else (self.excel / f"{name}.txt")
            self._cache[k] = read_tsv(p) if p.exists() else None
        return self._cache[k]

    def largest(self, name: str):
        """The table of the bank with more records (RotW extends base: itemtypes 109 vs 108 with `csch`)."""
        tabs = [t for t in (self.table(name, "base"), self.table(name, "")) if t]
        return max(tabs, key=lambda t: len(records(t[1]))) if tabs else None

    def keys(self, entity: str) -> list[str]:
        """Record keys of the larger bank (RotW extends base; ids are shared)."""
        best: list[str] = []
        for bank in ("base", ""):
            t = self.table(entity, bank)
            if t:
                h, rows = t
                k = col(h, ENTITIES[entity].key) if entity in ENTITIES else 0
                ks = [r[k] if k is not None else "" for r in records(rows)]
                if len(ks) > len(best):
                    best = ks
        return best

    def keys_113c(self, entity: str) -> list[str] | None:
        """Record keys of the 1.13c table, from D2R's base table (None when the 1.13c row count is not known)."""
        if entity not in ROW_COUNTS_113C:
            return None
        t = self.table(entity, "base")
        if not t:
            return None
        h, rows = t
        rows = [list(r) for r in rows[:ROW_COUNTS_113C[entity]]]
        k = col(h, ENTITIES[entity].key)
        for i, key in KEY_113C.get(entity, {}).items():
            rows[i][k] = key
        return [r[k] for r in records(rows)]


# ---------------------------------------------------------------------------------------------------------------------
# Id spaces

@dataclass
class Row:
    row: int          # mod record index (the mod's own id)
    key: str          # mod key
    id: int           # final id
    kind: str         # vanilla | repurposed | moved | relocated | new | blank
    name: str         # final key (after renames)


@dataclass
class SpaceMap:
    entity: str
    n113: int
    nd2r: int
    rows: list[Row]
    d2r_keys: list[str]
    fixed: set[int] = field(default_factory=set)          # vanilla ids D2R's code names by number (FIXED_IDS)
    collisions: list[str] = field(default_factory=list)   # mod new keys equal to a D2R-added key (renamed)
    duplicates: list[str] = field(default_factory=list)   # keys the mod defines twice (name refs hit the first)

    def ids(self) -> dict[int, int]:
        return {r.row: r.id for r in self.rows}

    def renames(self) -> dict[str, str]:
        return {r.key: r.name for r in self.rows if r.key and r.name != r.key}

    def restored_keys(self) -> set[str]:
        """D2R's keys (lower case) at fixed ids (FIXED_IDS) whose row the mod repurposed, kept or relocated: the mod had no
        row of that name, so a mod reference to it named nothing in 1.13c and must still name nothing (at a relocated id
        D2R's row comes back and must not be reached)."""
        mod = {r.key.lower() for r in self.rows if r.key}
        return {self.d2r_keys[r.row].lower() for r in self.rows
                if (r.kind == "relocated" or (r.kind == "repurposed" and r.row in self.fixed)) and r.row < len(self.d2r_keys)
                and self.d2r_keys[r.row] and self.d2r_keys[r.row].lower() not in mod}

    def order(self) -> list[tuple[str, int]]:
        by_id = {r.id: r.row for r in self.rows}
        top = max([self.nd2r - 1, *by_id]) if (by_id or self.nd2r) else -1
        return [("mod", by_id[i]) if i in by_id else ("d2r", i) for i in range(top + 1)]


def map_space(entity: str, mod_keys: list[str], d2r_keys: list[str], v113_keys: list[str] | None,
              adopt_d2r_names: bool = True, first: set[int] | None = None,
              relocate: set[int] | None = None, fixed: set[int] | None = None) -> SpaceMap:
    """Final ids of an indexed table's mod rows (rules in the module docstring). Without a 1.13c count, D2R's count
    stands in (the table was not extended by D2R). Rows in `first` (mod row numbers) get the lowest new ids: item
    parameters with few saved bits name them (charged skills: 10 bits, `state`: 8 bits). `relocate`: vanilla ids D2R's
    code names by number (D2R_FIXED_STATES); a mod row that repurposed one gets a new id (after the other new rows
    unless in `first`) and D2R's row keeps the id. `fixed`: all such ids, kept or relocated (FIXED_IDS, restored_keys)."""
    relocate = relocate or set()
    v113 = v113_keys if v113_keys is not None else d2r_keys
    n113, nd2r = len(v113), len(d2r_keys)
    added = {k.lower() for k in d2r_keys[n113:] if k}
    taken = {k.lower() for k in d2r_keys if k}
    sm = SpaceMap(entity, n113, nd2r, [], d2r_keys, set(fixed or ()) | relocate)
    seen: Counter = Counter(k.lower() for k in mod_keys if k)
    sm.duplicates = sorted(k for k, n in seen.items() if n > 1)
    used_names = {k.lower() for k in mod_keys if k} | taken
    pending: list[Row] = []  # rows that get a new id, numbered after the loop
    for i, key in enumerate(mod_keys):
        if i < n113:
            vkey = v113[i] if i < len(v113) else ""
            dkey = d2r_keys[i] if i < nd2r else ""
            if (UNUSED.match(vkey or "") and dkey and not UNUSED.match(dkey) and key and not UNUSED.match(key)
                    and key.lower() != dkey.lower()):
                sm.rows.append(Row(i, key, -1, "moved", key))
                pending.append(sm.rows[-1])
                continue
            if not key:
                kind = "blank"
            elif key.lower() == vkey.lower():
                kind = "vanilla"
            else:
                kind = "repurposed"
            if kind == "repurposed" and i in relocate and dkey and dkey.lower() == vkey.lower():
                sm.rows.append(Row(i, key, -1, "relocated", key))
                pending.append(sm.rows[-1])
                continue
            name = dkey if (kind == "vanilla" and adopt_d2r_names and dkey and dkey != key
                            and not UNUSED.match(dkey)) else key
            sm.rows.append(Row(i, key, i, kind, name))
        else:
            name = key
            if key and key.lower() in added:
                sm.collisions.append(key)
                n = 2
                name = f"{key}_mxl"
                while name.lower() in used_names:
                    name = f"{key}_mxl{n}"
                    n += 1
                used_names.add(name.lower())
            sm.rows.append(Row(i, key, -1, "new", name))
            pending.append(sm.rows[-1])
    first = first or set()
    next_id = max(nd2r, n113)
    for r in sorted(pending, key=lambda r: (r.row not in first, r.kind == "relocated", r.row)):
        r.id = next_id
        next_id += 1
    return sm


# ---------------------------------------------------------------------------------------------------------------------
# Item types

def align_item_types(mod_h: list[str], mod_rows: list[list[str]], d2r_h: list[str], d2r_rows: list[list[str]]):
    """(rows, report): every D2R item type at its D2R number (the mod's row of the same code replaces D2R's), then the
    mod's own types in their order. A mod row with a blank code at a number where D2R has a type the mod lacks is
    replaced by D2R's row. Rows are in the mod's column layout (D2R rows are mapped by column name)."""
    mc, dc = col(mod_h, "Code"), col(d2r_h, "Code")
    mrec, drec = records(mod_rows), records(d2r_rows)
    by_code = {}
    for i, r in enumerate(mrec):
        if r[mc] and r[mc].lower() not in by_code:
            by_code[r[mc].lower()] = i

    def as_mod(drow):
        return [drow[col(d2r_h, h)] if col(d2r_h, h) is not None else "" for h in mod_h]

    used, out, report = set(), [], defaultdict(list)
    for j, d in enumerate(drec):
        code = d[dc].lower()
        if code in by_code:
            i = by_code[code]
            used.add(i)
            out.append(mrec[i])
            if i != j:
                report["moved"].append(f"{d[dc]} {i}->{j}")
        else:
            if j < len(mrec) and not mrec[j][mc] and j not in used:
                used.add(j)
                report["blank_replaced"].append(f"{j} ({mrec[j][0]!r} -> {d[dc]})")
            out.append(as_mod(d))
            report["d2r_inserted"].append(f"{d[dc]} {j}")
    for i, r in enumerate(mrec):
        if i not in used:
            if len(out) != i:
                report["moved"].append(f"{r[mc] or repr(r[0])} {i}->{len(out)}")
            out.append(r)
    return out, dict(report)


def type_ids(header: list[str], rows: list[list[str]]) -> dict[str, int]:
    c = col(header, "Code")
    out: dict[str, int] = {}
    for i, r in enumerate(records(rows)):
        if r[c] and r[c].lower() not in out:
            out[r[c].lower()] = i
    return out


def check_item_type_ids(header: list[str], rows: list[list[str]], d2r: tuple | None = None) -> list[str]:
    """Errors when a type D2R.exe tests by a fixed number has another id in the table (fail the build)."""
    ids = type_ids(header, rows)
    errors = [f"item type {c}: id {ids.get(c)}, D2R.exe tests {n}" for c, n in D2R_FIXED_TYPE_IDS.items()
              if ids.get(c) != n]
    if d2r:
        dids = type_ids(*d2r)
        errors += [f"item type {c}: D2R's own itemtypes.txt has {dids.get(c)}, the exe constant is {n} (new build?)"
                   for c, n in D2R_FIXED_TYPE_IDS.items() if dids.get(c) != n]
        errors += [f"item type {c}: id {ids.get(c)}, D2R's is {j}" for c, j in dids.items()
                   if ids.get(c) != j and c not in D2R_FIXED_TYPE_IDS]
    return errors


# ---------------------------------------------------------------------------------------------------------------------
# Function slots

@dataclass
class SlotMove:
    table: str
    column: str
    old: str
    new: str | None     # None: no free slot (needs a hook)
    reason: str
    rows: list[str]


def plan_slots(table: str, header: list[str], rows: list[list[str]],
               vanilla_values: dict[str, set[str]] | None = None,
               d2r_own: dict[str, set[str]] | None = None) -> list[SlotMove]:
    """Moves for the mod's function slots: 1.13c slots D2R renumbered (-> D2R's slot), dropped ones and D2R-owned ones
    (-> a free slot for the plugin). `vanilla_values` (column -> values 1.13c's vanilla rows use) adds a warning for
    values no vanilla row used (their 1.13c function is unverified); `d2r_own` (column -> values only D2R's own rows
    use, inferred from the data) adds a "verify" note; only D2R_OWN_SLOTS (verified) moves rows."""
    key = col(header, ENTITIES[table].key)
    cols = SKILL_SLOT_COLS if table == "skills" else MISSILE_SLOT_COLS
    free = {c: list(FREE_SLOTS.get((table, c), [])) for c in cols}
    moves: list[SlotMove] = []
    for c in cols:
        ci = col(header, c)
        if ci is None:
            continue
        users: dict[str, list[str]] = defaultdict(list)
        for r in records(rows):
            if r[ci].strip():
                users[r[ci].strip()].append(r[key])
        remap = SLOT_REMAP.get((table, c), {})
        for v in sorted(users, key=lambda x: int(x) if x.lstrip("-").isdigit() else 1 << 30):
            names = users[v]
            if v in remap:
                special = [k for k in SLOT_REMAP_WITH if k[:3] == (table, c, v)]
                moves.append(SlotMove(table, c, v, remap[v], "1.13c slot D2R renumbered" +
                                      ("" if remap[v] else " (no D2R slot: dropped)"), names))
                continue
            if any(k[:3] == (table, c, v) for k in SLOT_REMAP_WITH):
                continue  # handled per row by apply_slot_moves
            if v in SLOT_KEEP.get((table, c), {}):
                moves.append(SlotMove(table, c, v, v, SLOT_KEEP[(table, c)][v] + "; number kept", names))
                continue
            reason = SLOT_DROPPED.get((table, c), {}).get(v) or (
                "D2R uses this slot for its own function" if v in D2R_OWN_SLOTS.get((table, c), set()) else None)
            if reason:
                new = str(free[c].pop(0)) if free[c] else None
                moves.append(SlotMove(table, c, v, new, reason + "; plugin re-implements the 1.13c function", names))
            elif d2r_own is not None and v in d2r_own.get(c, set()):
                moves.append(SlotMove(table, c, v, v, "only D2R's own rows use it, no 1.13c vanilla row: the 1.13c "
                                      "function is unverified; game-check, else move to a free slot "
                                      f"({', '.join(map(str, free[c][:3])) or 'none'}...) for the plugin", names))
            elif vanilla_values is not None and v not in vanilla_values.get(c, set()) and v != "0":
                moves.append(SlotMove(table, c, v, v, "no 1.13c vanilla row uses it: verify the function in D2R", names))
    return moves


def apply_slot_moves(table: str, header: list[str], rows: list[list[str]], moves: list[SlotMove]) -> Counter:
    """Rewrite the mod's slot cells in place (warnings, new == old, are left alone)."""
    n: Counter = Counter()
    m = {(mv.column, mv.old): mv.new for mv in moves if mv.table == table and mv.new != mv.old}
    for (t, c1, v1, c2, v2), new in SLOT_REMAP_WITH.items():
        if t != table or col(header, c1) is None:
            continue
        a, b = col(header, c1), col(header, c2)
        for r in records(rows):
            if r[a] == v1 and r[b] == v2:
                r[a] = new
                n[c1] += 1
    for r in records(rows):
        for (c, old), new in m.items():
            ci = col(header, c)
            if ci is not None and r[ci].strip() == old and new is not None:
                r[ci] = new
                n[c] += 1
    return n


# ---------------------------------------------------------------------------------------------------------------------
# Property parameters

def property_columns(header: list[str]) -> list[tuple[int, int | None, int | None, int | None]]:
    """(code, param, min, max) column indexes of each property slot in an item/affix/recipe table."""
    lower = {c.lower(): i for i, c in enumerate(header)}
    groups = []
    for i, c in enumerate(header):
        if m := re.fullmatch(r"(a?)prop(\d+[ab]?)((?: \([nh]\))?)", c, re.I):
            keys = [f"{m[1]}{x}{m[2]}{m[3]}" for x in ("par", "min", "max")]
        elif m := re.fullmatch(r"([pf]|t1)code(\d+[ab]?)", c, re.I):
            keys = [f"{m[1]}{x}{m[2]}" for x in ("param", "min", "max")]
        elif m := re.fullmatch(r"(\w*mod\d+)code", c, re.I):
            keys = [f"{m[1]}{x}" for x in ("param", "min", "max")]
        elif m := re.fullmatch(r"((?:[bc] )?mod \d+)", c, re.I):
            keys = [f"{m[1]} {x}" for x in ("param", "min", "max")]
        else:
            continue
        groups.append((i, *(lower.get(k.lower()) for k in keys)))
    return groups


def param_kinds(props: tuple, isc: tuple) -> dict[str, tuple[str, list[str]]]:
    """property code -> (kind, stats): "skill", "skill-range" (func 12: min/max), "monster" (descfunc 23), "state"."""
    ph, prows = props
    ih, irows = isc
    stats = {r[col(ih, "Stat")].lower(): r for r in records(irows)}
    out = {}
    for r in records(prows):
        code = r[col(ph, "code")]
        if not code:
            continue
        st = [r[col(ph, f"stat{n}")] for n in range(1, 8) if col(ph, f"stat{n}") is not None and r[col(ph, f"stat{n}")]]
        s = stats.get(st[0].lower()) if st else None
        func = r[col(ph, "func1")]
        descfunc = s[col(ih, "descfunc")] if s else ""
        encode = s[col(ih, "Encode")] if s else ""
        if func == "12":
            out[code.lower()] = ("skill-range", st)
        elif func in ("11", "19", "22") or descfunc in SKILL_PARAM_DESCFUNCS or encode in ("2", "3"):
            out[code.lower()] = ("skill", st)
        elif descfunc == "23":
            out[code.lower()] = ("monster", st)
        elif st and st[0].lower() == "state":
            out[code.lower()] = ("state", st)
    return out


def param_bits(isc: tuple, stat: str) -> int | None:
    """Bits a stat's parameter id may use when saved: Save Param Bits, minus the level bits for encode 2/3."""
    ih, irows = isc
    for r in records(irows):
        if r[col(ih, "Stat")].lower() == stat.lower():
            spb = r[col(ih, "Save Param Bits")] if col(ih, "Save Param Bits") is not None else ""
            if not spb.isdigit() or int(spb) == 0:
                return None
            bits = int(spb)
            if r[col(ih, "Encode")] in ("2", "3"):
                bits -= 6  # skill << stuff(6) | level
            return bits
    return None


# ---------------------------------------------------------------------------------------------------------------------
# The map

class IdMap:
    def __init__(self, spaces: dict[str, SpaceMap], mod: dict[str, tuple], d2r: D2RData | None):
        self.spaces, self.mod, self.d2r = spaces, mod, d2r
        self.slot_moves: list[SlotMove] = []
        self.bin_mismatch: dict[str, tuple[int, int]] = {}
        self.overflow: dict[str, set[tuple[str, int]]] = {}
        self.low_ids: dict[str, list[int]] = {}
        self.cell_moves: list[tuple[str, int, str, str, str, str]] = []  # (table, mod row, column, old, new, key)
        self._kinds: dict | None = None

    # -- construction
    @classmethod
    def build(cls, mod_excel: Path, d2r_excel: Path | None, adopt_d2r_names: bool = True) -> "IdMap":
        mod = {p.stem.lower(): read_tsv(p) for p in sorted(Path(mod_excel).glob("*.txt"))}
        bins = {p.stem.lower(): bin_records(p) for p in sorted(Path(mod_excel).glob("*.txt"))}
        d2r = D2RData(d2r_excel) if d2r_excel else None
        spaces = {}
        for name, ent in ENTITIES.items():
            if name not in mod:
                continue
            h, rows = mod[name]
            k = col(h, ent.key)
            mkeys = [r[k] if k is not None else "" for r in records(rows)]
            dkeys = d2r.keys(name) if d2r else mkeys
            spaces[name] = map_space(name, mkeys, dkeys, d2r.keys_113c(name) if d2r else None, adopt_d2r_names,
                                     relocate=RELOCATE.get(name) if d2r else None, fixed=FIXED_IDS.get(name) if d2r else None)
        m = cls(spaces, mod, d2r)
        low = m._low_id_rows()
        for name, rows_ in low.items():
            s0 = spaces[name]
            mkeys = [r.key for r in s0.rows]
            spaces[name] = map_space(name, mkeys, s0.d2r_keys, d2r.keys_113c(name) if d2r else None,
                                     adopt_d2r_names, rows_, RELOCATE.get(name) if d2r else None,
                                     FIXED_IDS.get(name) if d2r else None)
        m.low_ids = {k: sorted(v) for k, v in low.items()}
        m.bin_mismatch = {t: (len(records(mod[t][1])), n) for t, n in bins.items()
                          if n is not None and t in ENTITIES and n != len(records(mod[t][1]))}
        for t in ("skills", "missiles"):
            if t in mod:
                vv = m._vanilla_slot_values(t) if d2r else None
                own = m._d2r_own_slots(t, vv) if d2r else None
                m.slot_moves += plan_slots(t, *mod[t], vv, own)
        m.cell_moves = m._cell_moves() if d2r else []
        return m

    def _vanilla_slot_values(self, table: str) -> dict[str, set[str]]:
        t = self.d2r.table(table, "base")
        if not t or table not in ROW_COUNTS_113C:
            return {}
        h, rows = t
        rows = [list(r) for r in rows[:ROW_COUNTS_113C[table]]]
        for (i, c), v in CELLS_113C.get(table, {}).items():
            rows[i][col(h, c)] = v
        out = {}
        for c in (SKILL_SLOT_COLS if table == "skills" else MISSILE_SLOT_COLS):
            ci = col(h, c)
            if ci is not None:
                out[c] = {r[ci] for r in records(rows) if r[ci]}
        for (t2, c), m in SLOT_REMAP.items():
            if t2 == table:
                out.setdefault(c, set()).update(m)
        for (t2, c), m in SLOT_DROPPED.items():
            if t2 == table:
                out.setdefault(c, set()).update(m)
        return out

    def _cell_moves(self) -> list[tuple[str, int, str, str, str, str]]:
        """Vanilla rows whose 1.13c slot D2R changed (CELLS_113C): the mod's row, still on the 1.13c value, takes
        D2R's (corpseexplosion pCltDoFunc 11 -> 69, vine beast death 11 -> 70, ...). Plus mod-new corpse explosions
        on pCltDoFunc 11 -> 69."""
        out = []
        for table, cells in CELLS_113C.items():
            if table not in self.mod or table not in self.spaces or not self.d2r.table(table, "base"):
                continue
            mh, mrows = self.mod[table]
            mrec = records(mrows)
            dh, drows = self.d2r.table(table, "base")
            raw_to_rec, n = {}, 0
            for i, r in enumerate(drows[:ROW_COUNTS_113C[table]]):
                if is_record(r):
                    raw_to_rec[i] = n
                    n += 1
            kinds = {r.row: r.kind for r in self.spaces[table].rows}
            covered = {(m.table, m.column, m.old) for m in self.slot_moves}
            for (i, c), old in cells.items():
                j = raw_to_rec.get(i)
                new = drows[i][col(dh, c)] if col(dh, c) is not None else None
                if j is None or new is None or new == old or kinds.get(j) != "vanilla" or col(mh, c) is None:
                    continue
                if (table, c, old) in covered or (table, c) in SLOT_KEEP:
                    continue  # the column-wide plan covers it (skills 109 / 64 / 82 / cltdo 22, client hits)
                if mrec[j][col(mh, c)] == old:
                    out.append((table, j, c, old, new, mrec[j][col(mh, ENTITIES[table].key)]))
        if "missiles" in self.mod:
            mh, mrows = self.mod["missiles"]
            kinds = {r.row: r.kind for r in self.spaces["missiles"].rows}
            ci, ki = col(mh, "pCltDoFunc"), col(mh, "Missile")
            for j, r in enumerate(records(mrows)):
                if ci is not None and r[ci] == "11" and kinds.get(j) != "vanilla" and CORPSE_EXPLOSION.search(r[ki]):
                    out.append(("missiles", j, "pCltDoFunc", "11", "69", r[ki]))
        return out

    def _d2r_own_slots(self, table: str, vanilla: dict[str, set[str]]) -> dict[str, set[str]]:
        """column -> slot values D2R's rows (both banks) use that no 1.13c row used, plus srvdofunc 153-171."""
        out: dict[str, set[str]] = defaultdict(set)
        for bank in ("base", ""):
            t = self.d2r.table(table, bank)
            if not t:
                continue
            h, rows = t
            for c in (SKILL_SLOT_COLS if table == "skills" else MISSILE_SLOT_COLS):
                ci = col(h, c)
                if ci is not None:
                    out[c] |= {r[ci] for r in records(rows) if r[ci]} - vanilla.get(c, set())
        if table == "skills":
            out["srvdofunc"] |= set(map(str, SRVDO_D2R_TAKEN))
        for (t2, c), m in SLOT_REMAP.items():  # remap targets are D2R's own slots holding the 1.13c function
            if t2 == table:
                out[c] -= set(m.values())
        return dict(out)

    # -- queries
    def new_id(self, entity: str, mod_row: int) -> int:
        return self.spaces[entity].ids()[mod_row]

    def order(self, entity: str) -> list[tuple[str, int]]:
        return self.spaces[entity].order()

    def renames(self) -> dict[str, dict[str, str]]:
        return {e: r for e, s in self.spaces.items() if (r := s.renames())}

    def restored_keys(self) -> dict[str, set[str]]:
        """entity -> D2R keys at fixed ids the mod repurposed (kept or relocated) that its references must not reach."""
        return {e: k for e, s in self.spaces.items() if (k := s.restored_keys())}

    def kinds(self) -> dict:
        if self._kinds is None:
            self._kinds = param_kinds(self.mod["properties"], self.mod["itemstatcost"]) \
                if "properties" in self.mod and "itemstatcost" in self.mod else {}
        return self._kinds

    def _name_to_id(self, entity: str) -> dict[str, int]:
        s = self.spaces.get(entity)
        if not s:
            return {}
        out: dict[str, int] = {}
        for r in s.rows:
            if r.key and r.key.lower() not in out:
                out[r.key.lower()] = r.id
        return out

    # -- rewriting the mod's tables (before merging D2R's rows)
    def remap_table(self, table: str, header: list[str], rows: list[list[str]]) -> Counter:
        """Rewrite one MOD table in place: own-id column, numeric references, renamed keys (key column, name
        reference columns, formula names), property parameters and function slots. Returns change counts."""
        n: Counter = Counter()
        recs = records(rows)
        ent = ENTITIES.get(table)
        if ent and table in self.spaces:
            sm = self.spaces[table]
            if ent.own_id and col(header, ent.own_id) is not None:
                ci = col(header, ent.own_id)
                for r, row in zip(sm.rows, recs):
                    if row[ci] == "" and table == "superuniques":
                        # the blank "Expansion" record (row 42) needs its id too: D2R asserts on a hole in its lookup
                        # (pwSuperUniqueLookup[ii] != SUPERUNIQUE_NONE, MonsterTbls.cpp:1812; docs/bugs.md #2)
                        row[ci] = str(r.id)
                        n[f"{ent.own_id} (own id)"] += 1
                    elif row[ci] != "" and row[ci] != str(r.id):
                        row[ci] = str(r.id)
                        n[f"{ent.own_id} (own id)"] += 1
            ki = col(header, ent.key)
            for r, row in zip(sm.rows, recs):
                if r.name != r.key:
                    row[ki] = r.name
                    n[f"{ent.key} (renamed key)"] += 1
        for tables, cre, entity, cond in NUMERIC_REFS:
            if not re.fullmatch(tables, table) or entity not in self.spaces:
                continue
            ids = self.spaces[entity].ids()
            cidx = col(header, cond[0]) if cond else None
            for ci, h in enumerate(header):
                if not re.fullmatch(cre, h, re.I):
                    continue
                for row in recs:
                    v = row[ci].strip()
                    if not v.isdigit() or (cond and (cidx is None or not cond[1](row[cidx]))):
                        continue
                    new = ids.get(int(v))
                    if new is not None and new != int(v):
                        row[ci] = str(new)
                        n[h] += 1
        renames = self.renames()
        restored = self.restored_keys()
        for tables, cre, entity in NAME_REFS:
            if not re.fullmatch(tables, table):
                continue
            gone = set().union(*(restored.get(e, set()) for e in entity.split("|")))
            if gone:
                for ci, h in enumerate(header):
                    if re.fullmatch(cre, h, re.I):
                        for row in recs:
                            if row[ci].lower() in gone:
                                row[ci] = ""
                                n[f"{h} (vanilla name the mod had no row for: emptied)"] += 1
            rn = {k.lower(): v for e in entity.split("|") for k, v in renames.get(e, {}).items()}
            if not rn:
                continue
            for ci, h in enumerate(header):
                if re.fullmatch(cre, h, re.I):
                    for row in recs:
                        if row[ci].lower() in rn:
                            row[ci] = rn[row[ci].lower()]
                            n[h] += 1
        if any(renames.get(e) for e in FORMULA_ENTITY.values()):
            def sub(m):
                rn = renames.get(FORMULA_ENTITY[m[1]], {})
                low = {k.lower(): v for k, v in rn.items()}
                return f"{m[1]}('{low.get(m[2].lower(), m[2])}"
            for row in recs:
                for ci, v in enumerate(row):
                    if "('" in v:
                        new = FORMULA_REF.sub(sub, v)
                        if new != v:
                            row[ci] = new
                            n["formula names"] += 1
        if table in PROPERTY_TABLES:
            n.update(self._remap_params(header, recs, renames))
        if table in ("skills", "missiles"):
            for t, j, c, old, new, _k in self.cell_moves:
                if t == table and col(header, c) is not None and recs[j][col(header, c)] == old:
                    recs[j][col(header, c)] = new
                    n[f"{c} (vanilla row slot)"] += 1
            n.update(apply_slot_moves(table, header, rows, self.slot_moves))
        return n

    def dry_run(self) -> dict[str, Counter]:
        """remap_table on a copy of every mod table: what the rewrite changes, per table."""
        out = {}
        for t, (h, rows) in self.mod.items():
            c = self.remap_table(t, list(h), [list(r) for r in rows])
            if c:
                out[t] = c
        return out

    def _remap_params(self, header, recs, renames) -> Counter:
        n: Counter = Counter()
        kinds = self.kinds()
        space = {"skill": "skills", "skill-range": "skills", "monster": "monstats", "state": "states"}
        restored = self.restored_keys()
        for code, par, lo, hi in property_columns(header):
            for row in recs:
                k = kinds.get(row[code].lower())
                if not k:
                    continue
                entity = space[k[0]]
                ids = self.spaces.get(entity).ids() if entity in self.spaces else {}
                rn = {a.lower(): b for a, b in renames.get(entity, {}).items()}
                for c in ([lo, hi] if k[0] == "skill-range" else [par]):
                    if c is None:
                        continue
                    v = row[c].strip()
                    if v.lower() in restored.get(entity, set()):
                        row[c] = ""
                        n[f"property param ({entity}, vanilla name the mod had no row for: emptied)"] += 1
                    elif v.isdigit() and ids.get(int(v), int(v)) != int(v):
                        row[c] = str(ids[int(v)])
                        n[f"property param ({entity})"] += 1
                    elif v.lower() in rn:
                        row[c] = rn[v.lower()]
                        n[f"property param ({entity})"] += 1
        return n

    # -- conflicts
    def conflicts(self) -> dict[str, list[str]]:
        """Report: "error" (the build must not ship this), "warn" (needs the plugin / owner), "info"."""
        out: dict[str, list[str]] = defaultdict(list)
        for t, (n_txt, n_bin) in self.bin_mismatch.items():
            out["error"].append(f"{t}: {n_txt} records read from the .txt, the mod's .bin has {n_bin}: ids would be wrong")
        if "itemtypes" in self.mod:
            h, rows = self.mod["itemtypes"]
            ids = type_ids(h, rows)
            bad = [f"{c} {ids.get(c)} (D2R {n})" for c, n in D2R_FIXED_TYPE_IDS.items() if ids.get(c) != n]
            if bad:
                out["info"].append("itemtypes: the mod's ids of D2R's fixed types differ (fixed by align_item_types; "
                                   "check_built fails if they still differ after the migration): " + ", ".join(bad))
            if self.d2r and self.d2r.largest("itemtypes"):
                d2h, d2rows = self.d2r.largest("itemtypes")
                rows2, rep = align_item_types(h, rows, d2h, d2rows)
                errs = check_item_type_ids(h, rows2, None)
                out["error" if errs else "info"].append(
                    "itemtypes after align_item_types: " + ("; ".join(errs) if errs else "fixed ids all match D2R") +
                    f"; D2R rows inserted: {', '.join(rep.get('d2r_inserted', [])) or 'none'}; "
                    f"blank rows replaced: {', '.join(rep.get('blank_replaced', [])) or 'none'}; "
                    f"{len(rep.get('moved', []))} mod types change id")
        for mv in self.slot_moves:
            sev = "warn" if mv.new != mv.old or "verif" in mv.reason else "info"
            tgt = "no free slot (needs a hook)" if mv.new is None else ("blank" if mv.new == "" else mv.new)
            out[sev].append(f"{mv.table}.{mv.column} {mv.old} -> {tgt}: {mv.reason}; {len(mv.rows)} rows: "
                            f"{', '.join(mv.rows[:12])}{' ...' if len(mv.rows) > 12 else ''}")
        for t, j, c, old, new, k in self.cell_moves:
            what = "D2R renumbered" if old else "D2R added"
            out["warn"].append(f"{t}.{c} {old or 'blank'} -> {new or 'blank'} on vanilla row {j} {k} "
                               f"({what} this vanilla row's slot; the mod's row follows D2R)")
        for e in ("skills", "playerclass", "charstats"):
            s = self.spaces.get(e)
            if s and self.d2r:
                order = s.order()
                lo = min(s.n113, len(s.rows))
                own = range(lo, s.nd2r)
                if not own:
                    continue
                kept = all(order[i] == ("d2r", i) for i in own)
                out["info" if kept else "error"].append(
                    f"{e}: D2R's own rows {lo}-{s.nd2r - 1} ({', '.join(s.d2r_keys[lo:lo + 4])}"
                    f"{' ...' if len(own) > 4 else ''}) {'stay at D2R ids' if kept else 'DO NOT stay at D2R ids'}")
        if self.d2r and self.d2r.table("skills", ""):
            h, rows = self.d2r.table("skills", "")
            war = [i for i, r in enumerate(records(rows)) if r[col(h, "charclass")] == "war"]
            s = self.spaces.get("skills")
            if war and s:
                ok = all(s.order()[i] == ("d2r", i) for i in war)
                out["info" if ok else "error"].append(
                    f"skills: D2R's {len(war)} Warlock skills (ids {war[0]}-{war[-1]}) "
                    f"{'stay at their D2R ids' if ok else 'are displaced by mod rows'}")
        sd = [r for r in records(self.mod.get("skills", ([], []))[1])]
        if sd:
            h = self.mod["skills"][0]
            ci = col(h, "srvdofunc")
            on = [r[col(h, "skill")] for r in sd if ci is not None and r[ci].isdigit() and int(r[ci]) in SRVDO_D2R_TAKEN]
            out["info"].append(f"skills.srvdofunc 153-171 (D2R's newer skills): {len(on)} mod rows" +
                               (f": {', '.join(on)}" if on else ""))
        for e, s in self.spaces.items():
            c = Counter(r.kind for r in s.rows)
            final = max([r.id for r in s.rows] + [s.nd2r - 1]) + 1
            line = (f"{e}: mod {len(s.rows)}, 1.13c {s.n113}, D2R {s.nd2r} -> final {final}; "
                    + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
            out["info"].append(line)
            moved = [f"{r.key} {r.row}->{r.id}" for r in s.rows if r.kind == "moved"]
            if moved:
                out["warn"].append(f"{e}: mod rows in 1.13c-unused slots D2R filled, moved: {', '.join(moved)}")
            reloc = [f"{r.key} {r.row}->{r.id} ({s.d2r_keys[r.row]} back at {r.row})" for r in s.rows if r.kind == "relocated"]
            if reloc:
                out["info"].append(f"{e}: {len(reloc)} repurposed vanilla rows on ids D2R's code names, relocated "
                                   f"(D2R's row keeps the id): {', '.join(reloc)}")
            kept = [f"{r.key} {r.row} ({s.d2r_keys[r.row]})" for r in s.rows if r.kind == "repurposed" and r.row in s.fixed]
            if kept:
                out["info"].append(f"{e}: {len(kept)} repurposed vanilla rows on ids D2R's code names, kept as 1.13c ran them "
                                   f"(D2R_FIXED_STATES; plugin guards statelist / dodgelist): {', '.join(kept)}")
            if s.restored_keys():
                out["info"].append(f"{e}: references to D2R keys at those ids the mod had no row for are emptied: "
                                   f"{', '.join(sorted(s.restored_keys()))}")
            rep = [f"{r.row} {s.d2r_keys[r.row] if r.row < len(s.d2r_keys) else '?'}->{r.key}"
                   for r in s.rows if r.kind == "repurposed"]
            if rep:
                out["warn"].append(f"{e}: {len(rep)} vanilla rows repurposed by the mod (D2R code that names the id "
                                   f"by number hits the mod's row): {', '.join(rep[:15])}{' ...' if len(rep) > 15 else ''}")
            if s.collisions:
                out["warn"].append(f"{e}: mod keys equal to D2R-added keys, renamed *_mxl: {', '.join(s.collisions)}")
            if s.duplicates:
                out["info"].append(f"{e}: keys defined twice by the mod (name refs hit the first): "
                                   f"{', '.join(s.duplicates[:15])}{' ...' if len(s.duplicates) > 15 else ''}")
            if final > TABLE_ROW_LIMIT:
                out["error"].append(f"{e}: {final} rows > D2R's {TABLE_ROW_LIMIT}")
        out.update({k: out[k] + v for k, v in self._limits().items()})
        return dict(out)

    def _limits(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = defaultdict(list)
        s = self.spaces.get("itemstatcost")
        if s:
            h, rows = self.mod["itemstatcost"]
            recs = records(rows)
            sv, sb = col(h, "Saved"), col(h, "Save Bits")

            def is_saved(row):
                return (sv is not None and row[sv] == "1") or (sb is not None and row[sb] not in ("", "0"))
            saved = sorted((r.id, r.name) for r, row in zip(s.rows, recs) if r.id >= STAT_SAVE_ID_LIMIT and is_saved(row))
            top = max(r.id for r in s.rows)
            out["warn" if saved else "info"].append(
                f"itemstatcost: highest id {top} (9-bit save id, {STAT_SAVE_ID_LIMIT} ends the list); "
                f"saved stats at/above {STAT_SAVE_ID_LIMIT}: {len(saved)}"
                + (f" ({', '.join(f'{n} {i}' for i, n in saved[:20])}{' ...' if len(saved) > 20 else ''}) -> need "
                   "D2RLoader's extended (16-bit) save format" if saved else ""))
        s = self.spaces.get("states")
        if s:
            final = max([r.id for r in s.rows] + [s.nd2r - 1]) + 1
            out["warn" if final > STATE_SYNC_LIMIT else "info"].append(
                f"states: {final} after the merge vs D2R's per-unit sync of {STATE_SYNC_LIMIT}"
                + (" -> states above it need D2RLoader's wide state sync" if final > STATE_SYNC_LIMIT else " (fits)"))
        if "skills" in self.mod:
            h, rows = self.mod["skills"]
            cc = Counter(r[col(h, "charclass")] for r in records(rows) if r[col(h, "charclass")])
            over = {k: v for k, v in cc.items() if v > CLASS_SKILL_SAVE}
            out["warn" if over else "info"].append(
                f"skills per class: {dict(sorted(cc.items()))} (classic save holds {CLASS_SKILL_SAVE} per class)"
                + (" -> needs D2RLoader's extended save" if over else ""))
        if "monai" in self.mod and "monstats" in self.mod:
            ai = {k.lower(): i for i, k in enumerate(r[col(self.mod["monai"][0], "AI")] for r in records(self.mod["monai"][1]))}
            h, rows = self.mod["monstats"]
            bad = Counter(r[col(h, "AI")] for r in records(rows) if ai.get(r[col(h, "AI")].lower(), -1) >= ENGINE_AI_ROWS)
            out["warn" if bad else "info"].append(
                f"monai: {len(ai)} rows (D2R AI table {ENGINE_AI_ROWS})" +
                (f"; monsters on AI rows >= {ENGINE_AI_ROWS}: {dict(bad)}" if bad else "; all monsters on D2R's AI rows"))
        if all(t in self.mod for t in ("properties", "itemstatcost")):
            out.update({k: out[k] + v for k, v in self._param_overflow().items()})
        return out

    def _low_id_rows(self) -> dict[str, set[int]]:
        """entity -> mod rows that an item parameter with a bit limit names (number or key) and that would get a new
        id: they are numbered first, so they fit (skills referenced by charges, states by the `state` property)."""
        if not all(t in self.mod for t in ("properties", "itemstatcost")):
            return {}
        isc, kinds = self.mod["itemstatcost"], self.kinds()
        space = {"skill": "skills", "monster": "monstats", "state": "states"}
        out: dict[str, set[int]] = defaultdict(set)
        for table in PROPERTY_TABLES:
            if table not in self.mod:
                continue
            h, rows = self.mod[table]
            for code, par, _lo, _hi in property_columns(h):
                for row in records(rows):
                    k = kinds.get(row[code].lower())
                    if not k or k[0] not in space or par is None or space[k[0]] not in self.spaces:
                        continue
                    if not any(param_bits(isc, st) is not None for st in k[1]):
                        continue
                    sm = self.spaces[space[k[0]]]
                    v = row[par].strip()
                    by_key = {r.key.lower(): r.row for r in sm.rows if r.key}
                    j = int(v) if v.isdigit() else by_key.get(v.lower())
                    if j is not None and j < len(sm.rows) and sm.rows[j].kind in ("new", "moved", "relocated"):
                        out[space[k[0]]].add(j)
        return dict(out)

    def _param_overflow(self) -> dict[str, list[str]]:
        """Property parameters whose FINAL id does not fit the stat's saved parameter bits."""
        out: dict[str, list[str]] = defaultdict(list)
        isc = self.mod["itemstatcost"]
        kinds = self.kinds()
        space = {"skill": "skills", "skill-range": "skills", "monster": "monstats", "state": "states"}
        bad: Counter = Counter()
        examples: dict[str, str] = {}
        maxid: dict[str, int] = {}
        for table in PROPERTY_TABLES:
            if table not in self.mod:
                continue
            h, rows = self.mod[table]
            for code, par, lo, hi in property_columns(h):
                for row in records(rows):
                    k = kinds.get(row[code].lower())
                    if not k or k[0] == "skill-range":
                        continue
                    entity = space[k[0]]
                    v = row[par].strip() if par is not None else ""
                    names = self._name_to_id(entity)
                    if v.isdigit():
                        fid = self.spaces[entity].ids().get(int(v), int(v)) if entity in self.spaces else int(v)
                    elif v.lower() in names:
                        fid = names[v.lower()]
                    else:
                        continue
                    for st in k[1]:
                        bits = param_bits(isc, st)
                        if bits is None:
                            continue
                        maxid[st] = max(maxid.get(st, 0), fid)
                        if fid >= 1 << bits:
                            bad[(row[code], st, bits)] += 1
                            examples.setdefault(f"{row[code]}/{st}", f"{table}: {row[0]} param {v} -> {fid}")
                            self.overflow.setdefault(f"{row[code]}/{st}/{bits}", set()).add((v, fid))
        for (code, st, bits), n in sorted(bad.items()):
            vals = sorted(self.overflow.get(f"{code}/{st}/{bits}", set()), key=lambda x: x[1])
            ent = space[kinds[code.lower()][0]]
            names = {r.id: r.name for r in self.spaces[ent].rows} if ent in self.spaces else {}
            out["error"].append(f"property {code} (stat {st}, {bits} param bits, max id {(1 << bits) - 1}): {n} params "
                                f"overflow after renumbering, e.g. {examples[f'{code}/{st}']}; distinct {ent}: "
                                + ", ".join(f"{names.get(f, '?')} {v}->{f}" for v, f in vals))
        if not bad:
            out["info"].append("property parameters: every final skill/monster/state id fits its stat's param bits "
                               "(rows numbered first for that: " + ", ".join(
                                   f"{e} {len(v)}" for e, v in self.low_ids.items()) + ")")
        return out

    # -- output
    def to_json(self) -> dict:
        return {
            "spaces": {e: {"n113": s.n113, "nd2r": s.nd2r,
                           "rows": [{"row": r.row, "key": r.key, "id": r.id, "kind": r.kind, "name": r.name}
                                    for r in s.rows],
                           "collisions": s.collisions, "duplicates": s.duplicates}
                       for e, s in self.spaces.items()},
            "renames": self.renames(),
            "slot_moves": [vars(m) for m in self.slot_moves],
            "cell_moves": [dict(zip(("table", "row", "column", "old", "new", "key"), c)) for c in self.cell_moves],
            "low_ids": self.low_ids,
        }


def ref_columns(header_by_table: dict[str, list[str]]) -> list[tuple[str, str, str, str]]:
    """(table, column, entity, mode) for every reference column present in the given headers."""
    out = []
    for t, h in header_by_table.items():
        for tables, cre, entity, cond in NUMERIC_REFS:
            if re.fullmatch(tables, t):
                out += [(t, c, entity, "id" + (f" if {cond[0]}" if cond else "")) for c in h if re.fullmatch(cre, c, re.I)]
        for tables, cre, entity in NAME_REFS:
            if re.fullmatch(tables, t):
                out += [(t, c, entity, "name") for c in h if re.fullmatch(cre, c, re.I)]
    return out


def check_built(built: Path, d2r_excel: Path | None) -> list[str]:
    """Checks on a MIGRATED table folder (one bank): fixed item type ids. Non-empty -> fail the build."""
    p = Path(built) / "itemtypes.txt"
    if not p.exists():
        return [f"{p} missing"]
    d2r = None
    if d2r_excel:
        d2r = D2RData(Path(d2r_excel)).largest("itemtypes")  # both banks get D2R's full list at the same ids
    return check_item_type_ids(*read_tsv(p), d2r)


def guide_refs(guide: Path) -> list[tuple[str, str, str]]:
    """(table, field, target file) of every reference field in D2R's data guide."""
    out = []
    for p in sorted(Path(guide).glob("*.js")):
        t = p.read_text("utf-8")
        d = json.loads(t[t.index("=") + 1:].strip().rstrip(";"))
        for f in d.get("fields", []) if isinstance(d, dict) else []:
            typ = f.get("type")
            if isinstance(typ, dict) and typ.get("type") == "reference":
                for name in f.get("altNames") or [f["name"]]:
                    out.append((p.stem.lower(), name, str(typ.get("file", "")).lower()))
    return out


def write_report(m: IdMap, path: Path, mod_dir: Path) -> None:
    conf = m.conflicts()
    lines = [f"# idmap report\n\nMod tables: `{mod_dir}`\n"]
    for sev in ("error", "warn", "info"):
        lines.append(f"\n## {sev} ({len(conf.get(sev, []))})\n")
        lines += [f"- {x}" for x in conf.get(sev, [])]
    lines.append("\n## What remap_table rewrites in the mod's tables (dry run)\n")
    lines.append("| table | column | cells |\n|---|---|---|")
    for t, c in sorted(m.dry_run().items()):
        lines += [f"| {t} | {k} | {v} |" for k, v in sorted(c.items())]
    lines.append("\n## Reference columns present in the mod's tables\n")
    lines.append("| table | column | id space | mode |\n|---|---|---|---|")
    lines += [f"| {t} | {c} | {e} | {mo} |" for t, c, e, mo in ref_columns({t: h for t, (h, _r) in m.mod.items()})]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--mod", required=True, type=Path)
    b.add_argument("--d2r")
    b.add_argument("--out", type=Path, default=ROOT / "work" / "idmap")
    c = sub.add_parser("check")
    c.add_argument("--built", required=True, type=Path)
    c.add_argument("--d2r")
    r = sub.add_parser("refs")
    r.add_argument("--guide", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        d2r = find_d2r(a.d2r)
        if d2r is None:
            print("idmap: D2R's excel folder not found (--d2r / MXL2012_D2R_EXCEL); ids cannot be mapped")
            return 2
        m = IdMap.build(a.mod, d2r)
        a.out.mkdir(parents=True, exist_ok=True)
        (a.out / "idmap.json").write_text(json.dumps(m.to_json(), indent=1), encoding="utf-8")
        write_report(m, a.out / "report.md", a.mod)
        conf = m.conflicts()
        print(f"idmap: {len(conf.get('error', []))} errors, {len(conf.get('warn', []))} warnings -> {a.out}")
        for x in conf.get("error", []):
            print("  ERROR", x)
        return 1 if conf.get("error") else 0
    if a.cmd == "check":
        errs = check_built(a.built, find_d2r(a.d2r))
        for e in errs:
            print("ERROR", e)
        print(f"idmap check: {'FAIL' if errs else 'ok'} ({len(errs)} errors)")
        return 1 if errs else 0
    if a.cmd == "refs":
        for tables, cre, entity, cond in NUMERIC_REFS:
            print(f"id    {tables}.{cre} -> {entity}{f' (if {cond[0]})' if cond else ''}")
        for tables, cre, entity in NAME_REFS:
            print(f"name  {tables}.{cre} -> {entity}")
        if a.guide:
            known = [(t, cre, e) for t, cre, e in NAME_REFS]
            missing = [(t, f, tgt) for t, f, tgt in guide_refs(a.guide) if tgt in ENTITIES and not any(
                re.fullmatch(tt, t) and re.fullmatch(cre, f, re.I) for tt, cre, _e in known)]
            print(f"\nguide reference fields to an id space not in NAME_REFS: {len(missing)}")
            for x in missing:
                print("  ", *x)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
