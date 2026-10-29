"""Migrate Median XL 2012's named tables (1.13c columns) to D2R 3.3's table layout and merge them with D2R's rows.

Adapted from another port's txt_migrate.py. Kept: the row merge rules (indexed / keyed / replace /
d2r_wins), column mapping and D2R-only column fill, the D2R-engine fixes that apply to any 1.13c mod (treasure class order,
preset / maze claims, set size, skill slot remaps and stop functions, sounds, missiles Range, ...). Dropped: everything that
serves D2Sigma (aura / damage / cooldown / pet / hireling plugin headers, item spells, proxies, extra calc codes, vendors,
stat screen, bin decoders): Median 2012 has no engine DLL and ships real .txt tables.

Input:  work/named/<table>.txt + idmap.json (tools/mxl2012_prep.py)
        extract/d2r/<build>/data/global/excel/{,base/}<table>.txt (D2R 93847 baseline, read-only; MXL_D2R_EXTRACT)
        work/mod/strings_map.json (tools/tbl2json.py --excel-dir work/named; docs/strings.md)
Output: work/mod/data/global/excel/base/<table>.txt   Classic/LoD bank (D2R base header)
        work/mod/data/global/excel/<table>.txt        RotW bank (D2R RotW header)
        work/mod/migrate_report.md, work/mod/overflow/<table>.txt (values D2R has no column for)

Row merge, by table kind:
  indexed   tables the engine reads by row number (idmap.ENTITIES): output row i is the mod row whose new ID is i,
            else D2R's row i. D2R's own additions keep their IDs; the mod's new rows follow them.
  keyed     (default) the mod's rows, then D2R rows whose key the mod does not have.
  replace   the mod's own item / affix / recipe sets: mod rows only (D2R's vanilla bases would drop through auto classes).
  d2r_wins  D2R rows, then mod rows whose key D2R does not have (sounds, calc code lists).

Usage: python tools/txt_migrate.py [--table skills ...]
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import idmap  # noqa: E402
import localconfig  # noqa: E402  (.mxl-local.json defaults, D2R extraction)
import strings_ns  # noqa: E402

import os  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NAMED = ROOT / "work" / "named"
D2R = localconfig.default_d2r_extract() / "data" / "global" / "excel"
OUT = ROOT / "work" / "mod"
CLT_NOVA = "25"  # skills.txt cltdofunc of D2R's client nova ring

# 1.13c column -> D2R column, per table. Case-only differences are matched automatically.
RENAMES = {
    "*": {**{f"Hralti{s}": f"Hratli{s}" for s in ("Min", "Max", "MagicMin", "MagicMax", "MagicLvl")},
          **{f"Drehya{s}": f"Anya{s}" for s in ("Min", "Max", "MagicMin", "MagicMax", "MagicLvl")}},
    "monstats": {f"TreasureClass{n}{d}": f"TreasureClass{s}{d}"
                 for n, s in (("1", ""), ("2", "Champ"), ("3", "Unique"), ("4", "Quest"))
                 for d in ("", "(N)", "(H)")},
    "levels": {"MonLvl1": "MonLvl", "MonLvl2": "MonLvl(N)", "MonLvl3": "MonLvl(H)",
               "MonLvl1Ex": "MonLvlEx", "MonLvl2Ex": "MonLvlEx(N)", "MonLvl3Ex": "MonLvlEx(H)"},
    "difficultylevels": {"HireableBossDamagePercent": "MercenaryDamagePercentVSBoss"},
    # v005 labels the third skill's growth column LvlPerLvl8, between Level3 and Skill4.
    "hireling": {"LvlPerLvl8": "LvlPerLvl3"},
    "uniqueitems": {"enabled": "spawnable"},
    "itemtypes": {"MaxSock1": "MaxSockets1", "MaxSock25": "MaxSockets2", "MaxSock40": "MaxSockets3"},
    "soundenviron": {f"EAX {s}": f"SFX EAX {s}" for s in ("Environ", "Room Vol", "Room HF", "Decay Time", "Decay HF",
                                                        "Reflect", "Reflect Delay", "Reverb", "Rev Delay")},
    "shrines": {"Shrine name": "Name", "Shrine Type": "*Shrine Type", "Effect": "*Effect", "view name": "StringName",
                "niftyphrase": "StringPhrase"},
    "events": {"*desc": "*description"},
    "misscalc": {"*desc": "*description"},
    "skillcalc": {"*desc": "*Description"},
}
# 1.13c NoShldBlock=1 "can block without a shield" == D2R ShieldBlockOverride=1 (2 = never blocks).
RENAMES["monstats"]["NoShldBlock"] = "ShieldBlockOverride"
# One 1.13c column feeding several D2R columns.
SPLITS = {
    # D2R split 1.13c's one unit-wide delay into localdelay (the skill's own cooldown) and globaldelay (the hold on every other
    # skill with a delay); 1.13c's `delay` is both (CH13, lane rulescheck2: with localdelay alone Holy Armor was cast 110 frames
    # into Mythal's 245-frame delay)
    "skills": {"delay": ["localdelay", "globaldelay"]},
    "hireling": {"Resist": ["ResistFire", "ResistCold", "ResistLightning", "ResistPoison"],
                 "Resist/Lvl": ["ResistFire/Lvl", "ResistCold/Lvl", "ResistLightning/Lvl", "ResistPoison/Lvl"]},
}
# Constant D2R columns implied by 1.13c's layout (itemtypes' fixed 25/40 socket thresholds).
CONSTANTS = {"itemtypes": {"MaxSocketsLevelThreshold1": "25", "MaxSocketsLevelThreshold2": "40"},
             # D2R scales potions per class (100-200 %); 1.13c does not
             "charstats": {"HealthPotionPercent": "100", "ManaPotionPercent": "100"},
             # D2R's resurrect cost formula inputs (the same on all 135 rows); the hire level range is hireling_level_difference()
             "hireling": {"resurrectcostmultiplier": "15", "resurrectcostdivisor": "2", "resurrectcostmax": "50000"},
             # transmogrify target: D2R's "no transmog" code
             "armor": {"TMogType": "xxx"}, "weapons": {"TMogType": "xxx"},
             # D2R rolls a set item as a random drop only when spawnable = 1 (1.13c: every set item)
             "setitems": {"spawnable": "1"}}

# The mod replaced the vanilla item bases and affix pools (merging D2R's rows back would let removed items drop again
# through the auto weapN/armoN treasure classes), so item, affix and treasure tables are mod-only.
REPLACE = {"uniqueitems", "setitems", "sets", "magicprefix", "magicsuffix", "automagic", "rareprefix", "raresuffix",
           "cubemain", "runes", "qualityitems", "lowqualityitems", "uniqueprefix", "uniquesuffix",
           "uniqueappellation", "gamble", "monpreset", "weapons", "armor", "misc", "treasureclassex", "hireling"}
D2R_WINS = {"sounds", "soundenviron", "skillcalc", "misscalc", "playerclass", "plrtype", "storepage"}
# D2R's own rows only: D2R's inventory has 2 rows per page (one per screen resolution) and asserts on anything else;
# the mod's grid sizes are copied in by inventory_sizes.
D2R_ONLY = {"inventory"}
MAX_ITEMS_PER_SET = 6  # D2R and D2RLoader
# Columns 1.13c has but D2R fills with new meaning: a mod row that matches a D2R row keeps D2R's value when empty.
# overlay Character is the HD overlay folder (data/hd/overlays/<Character>/<overlay>.json); without it D2R draws no HD overlay.
D2R_WHEN_EMPTY = {"overlay": {"Character"}}
# The same per row: item uses 1.13c runs by item code and D2R by misc pSpell (docs/median-rules-audit.md SK9, QU2). 1.14d's
# Game.exe compares `ass ` / `xyz ` / `tr2 ` / `toa ` in its item-use code (0x55e3d0-0x55e52a); D2R's own rows carry
# pSpell 10 (Book of Skill: +1 skill point), 11 (Potion of Life: +20 life), 12 (Malah's scroll: +10 resistances) and 13
# (Token of Absolution, Median's "Belladonna" respec token). Median kept the rows as vanilla has them (pSpell blank).
D2R_WHEN_EMPTY_ROWS = {"misc": ("code", {"ass", "xyz", "tr2", "toa"}, {"pSpell"})}


# Item spells whose timed state step 1.13c skipped in silence but D2R verifies (bug #191). 1.14d's handler for pSpell 9 (Game.exe
# 0x5beda0) returns 0 before anything is applied when the state is <= 0 (a name not in states.txt loads as -1) or the `len` calc
# is <= 0; pSpell 6 (0x5bef90) first removes cstate1 / cstate2 that exist, then calls the pSpell 9 handler and counts as used
# when either part did something. D2R runs the same steps (use table 0x1d3ea90: pSpell 6 = 0x5807b0, 9 = 0x57fd80) but asserts
# `spellState > 0 && spellState < DataTablesGetNumStates` (SkillItem.cpp:545 in the use, :823 in the can-use checks 0x580c10 /
# 0x580d20) and a `len` > 0 (:548 / :826). Median's Antidote / Thawing Potions (`yps`, `wms`) name D2R's `antidote` / `thawing`,
# which Median's states.txt replaced, and the Elixir of Adrenaline (`ey9`) has no `len`: in 1.13c they only cure.
# A pSpell 6 row of that kind keeps its cures and gets ITEM_SPELL_INERT_STATE for 1 frame with no stats: D2R's state step then
# succeeds and applies nothing. A pSpell 9 row of that kind gets pSpell 0, as bug #104's Greater Elixirs (no item spell: the
# use is refused and the item stays, as in 1.13c).
ITEM_SPELL_INERT_STATE = "healthpot"  # vanilla's state 100: an empty row in Median and D2R, named by no table and not by number in D2R's code
ITEM_SPELL_STAT_COLUMNS = tuple(c for n in (1, 2, 3) for c in (f"stat{n}", f"calc{n}"))


def item_spell_fix(row: dict[str, str], states: set[str]) -> dict[str, str]:
    """The cells to change on a misc row (column -> value) so that D2R's item spell does what 1.13c's did (bug #191); {} when
    the row is fine. `states` holds the state names of the built states.txt."""
    pspell = row.get("pSpell", "").strip()
    if pspell not in ("6", "9"):
        return {}
    length = row.get("len", "").strip()
    if not length:
        length = "0"
    no_len = re.fullmatch(r"-?\d+", length) is not None and int(length) <= 0
    if row.get("state", "").strip() in states and not no_len:
        return {}
    if pspell == "9":
        return {"pSpell": "0"}
    if not any(row.get(c, "").strip() in states for c in ("cstate1", "cstate2")):
        return {"pSpell": "0"}  # nothing to cure either: 1.13c's handler returned 0
    fix = {"state": ITEM_SPELL_INERT_STATE, "len": "1"}
    fix.update({c: "" for c in ITEM_SPELL_STAT_COLUMNS if row.get(c, "").strip()})
    return fix


# Scroll / tome cursor (bug #485). 1.13c takes a scroll's or tome's spell icon (the cursor after a right click: 0 = the identify
# cursor, -1 = none) from books.txt `SpellIcon`: 1.14d's getter 0x62bb30 reads books byte +2 for item types `scro` / `book` and
# misc `spellicon` (record +0x134) only for other items. D2R reads misc `spellicon` for every item (its server use check 0x5817f0
# wants a target item when record +0x144 is not 0xff, and D2R's own `isc` / `ibk` rows carry 0). Median XL 2012 writes -1 in every
# misc row, so its Scroll / Tome of Identify had no identify cursor on D2R: a right click did nothing.
BOOK_CODE_COLUMNS = ("ScrollSpellCode", "BookSpellCode")


# Conversion chance and length of skill server do 51 (bug #487). 1.13c's function (1.14d 0x5d76e0) takes the chance from
# Param5 / Param6 (the diminishing `dm56` of 0x645c10, record +0x158 / +0x15c) and the length from Param3 + rand(Param4)
# (+0x150 / +0x154). D2R's (0x570780, Mind Blast) evaluates calc1 as the chance (rand % 100 <= calc1, 0x572892) and calc2
# as the length (+ rand(Param4), record +0x1c4, 0x5728fc); its own Mind Blast row was moved to calc1 `dm56+...`, calc2
# `par3`. Median's rows leave both blank: 1 % chance, a charm of 0 frames (Elvensong "works like a curse, no conversion").
CONVERSION_DO = "51"
CONVERSION_CALCS = (("calc1", "dm56"), ("calc2", "par3"))


def conversion_calcs(header: list[str], rows: list[list[str]]) -> list[str]:
    """Fill a blank calc1 / calc2 of every srvdofunc 51 row with 1.13c's chance / length (in place); a set cell (Black Sleep's
    calc1, read by its start function too) is kept. Returns 'Id skill: calc1 dm56, ...' lines for the report."""
    if "srvdofunc" not in header or any(c not in header for c, _ in CONVERSION_CALCS):
        return []
    di, ni = header.index("srvdofunc"), header.index("skill")
    ii = header.index("*Id") if "*Id" in header else None
    done = []
    for r in rows:
        if len(r) <= di or r[di].strip() != CONVERSION_DO:
            continue
        set_ = []
        for col, value in CONVERSION_CALCS:
            ci = header.index(col)
            while len(r) <= ci:
                r.append("")
            if not r[ci].strip():
                r[ci] = value
                set_.append(f"{col} {value}")
        if set_:
            done.append(f"{r[ii] if ii is not None else '?'} {r[ni]}: " + ", ".join(set_))
    return done


# states.txt colorshift cells D2R's HD renderer draws far from classic (bug #496 lane veilking, bug #506 lane hdgreen). The
# 1.14d client (STATES_UpdateColorShiftAndLight 0x4d97f0) takes the state of the highest colorpri the unit has and uses its
# colorshift as the unit's palette shift index; 0 is no shift. Median's index-1 table is near the identity (Pal.pl2 hue
# variation 1: 76 of 256 entries one hue step on, reds a little more orange) and every legacy shot shows the unit's own colours.
# HD has a built-in colour per index and draws index 1 bright neon green (a variant table's customColorShiftEntries for index 1
# is not used: tried in game). 0 keeps the classic look and draws no tint in HD; the colorpri winner stays the same state, so a
# lower state's colour (cold, poison) is still hidden as in classic. Every Median row with 1 is here, with what puts it on:
# {state: (Median's value, the value written, what applies it)}. Seen in game: docs/testing.md "Lane hdgreen".
STATE_COLOUR_SHIFTS = {
    "careforabloodbath": ("1", "0", "Innate Bloodbath (65), monster aura"),
    "elementalfury": ("1", "0", "Elemental Fury (654, 703, 743), monster buffs"),
    "earthwaterairfire": ("1", "0", "Sorceress Firedance (527)"),
    "unfortunate": ("1", "0", "Barbarian Fortress (440)"),
    "eatsyou": ("1", "0", "Black Curse (700), monster curse"),
    "beaconsavengerstate": ("1", "0", "Assassin Beacon (623), mercenary Beacon (1070)"),
    "shamanstrance": ("1", "0", "Barbarian Shamanic Trance (627), item Trance (789)"),
    "broadsided": ("1", "0", "Assassin Broadside (345)"),
    "electricshield": ("1", "0", "Lightning Shield (660, 1055), monster aura"),
    "zeraesavengerstate": ("1", "0", "Amazon War Spirit (936), Dark Spirit (986, 987)"),
    "bladesoflight": ("1", "0", "Blades of Light (952), monster aura"),
    "ongoing_thunderdome": ("1", "0", "Lightning Arena (236), monster"),
    "killed3": ("1", "0", "More Mess (1011), monster aura on its targets"),
    "behindenemylines": ("1", "0", "Paladin Colosseum (502)"),
    "hellfireaura": ("1", "0", "Hellfire Aura (1103), monster aura"),
    "ongoing_tezla": ("1", "0", "Sorceress Nova Charge (537)"),
    "ongoing_napalm": ("1", "0", "Path of Flames (827), monster"),
    "qqstate": ("1", "0", "Sorceress Moonstrike (543)"),
    "totemicslow": ("1", "0", "totem auras (899, 980)"),
    "totemicheal": ("1", "0", "totem auras (135, 900, 981)"),
    "deathlordstate": ("1", "0", "Necromancer Deathlord form (487)"),
    "totemicvoodoo": ("1", "0", "totem auras (902, 983)"),
    "queenofthemoon": ("1", "0", "Amazon Moon Queen passive (307), item (705)"),
    "totemicattack": ("1", "0", "totem auras (903, 984)"),
    "totemicmanatide": ("1", "0", "totem auras (923, 985)"),
    "cloak_of_shadows": ("1", "0", "Darkness Falls (112), monster aura"),
    "meslayer": ("1", "0", "Veil King, Slayer bosses' Dark King / Gift of Shadows (bug #496)"),
    "tritonstate": ("1", "0", "Druid Treewarden form (463)"),
    "barbaricheal": ("1", "0", "Gift of Inner Fire (569, 586, 842, 957), monster / mercenary aura"),
    "innerbeast": ("1", "0", "Gift of the Wild / Mark of the Wild (570, 850, 1109), monster aura"),
    "darkpowered": ("1", "0", "Dark Power (669), monster aura"),
    "bloodlusted": ("1", "0", "Bloodlust (96, 99, 619), monster / mercenary aura"),
    "caution": ("1", "0", "Cautious Strike (672, 924)"),
    "banished": ("1", "0", "Banish (598), monster curse"),
    "artofwar": ("1", "0", "Barbarian Mountain King (442), Sorceress Supernature (922), passives"),
    "goodberries": ("1", "0", "Goodberry potion (b@b)"),
    "runforyourlife": ("1", "0", "Demonic Speed (600), monster"),
    "ongoing_typhoidmary": ("1", "0", "Sorceress Swarm (542)"),
    "lion_hearts": ("1", "0", "Amazon Lioness passive (319)"),
    "shower_of_rox": ("1", "0", "Barbarian Shower of Rocks (354, 616, 1102) on its targets"),
    "trapratstate": ("1", "0", "Druid Trap Rat form (448)"),
    "vindicated": ("1", "0", "Vindicate (52, 131), monster / mercenary curse"),
    "charm_crushing": ("1", "0", "Thrill of the Hunt (716, 852)"),
    "lionheartstate": ("1", "0", "Paladin Lionheart (501, 825)"),
    "bloodfountain": ("1", "0", "Bloody Mary (663), monster aura"),
    "purifyingspring": ("1", "0", "Pagan Heart (664), monster aura"),
    "akaratisgoingtodie": ("1", "0", "Weakening Nova (592, 657), monster"),
    "burnedbyburn": ("1", "0", "Paladin Searing Light (508), Dazzle / Sunburn curses (72, 760, 996)"),
    "cowdisguise": ("1", "0", "Cow Disguise (67), monster form"),
}


def state_colour_shift_fix(header: list[str], rows: list[list[str]]) -> list[str]:
    """Writes STATE_COLOUR_SHIFTS into states.txt rows (in place); the names done. A row whose value is not Median's is left
    alone (someone changed it on purpose)."""
    ni, ci = header.index("state"), header.index("colorshift")
    done = []
    for r in rows:
        name = r[ni].strip() if ni < len(r) else ""
        if name in STATE_COLOUR_SHIFTS and ci < len(r) and r[ci].strip() == STATE_COLOUR_SHIFTS[name][0]:
            r[ci] = STATE_COLOUR_SHIFTS[name][1]
            done.append(name)
    return done


def book_spell_icons(header: list[str], rows: list[list[str]]) -> dict[str, str]:
    """books.txt rows -> {misc item code: SpellIcon} for the scroll and tome codes of each row with a numeric SpellIcon."""
    if "SpellIcon" not in header:
        return {}
    si = header.index("SpellIcon")
    out: dict[str, str] = {}
    for r in rows:
        icon = r[si].strip() if si < len(r) else ""
        if not re.fullmatch(r"-?\d+", icon):
            continue
        for col in BOOK_CODE_COLUMNS:
            if col in header and header.index(col) < len(r) and r[header.index(col)].strip():
                out[r[header.index(col)].strip()] = icon
    return out

def d2r_when_empty(table: str, column: str, mrow: list[str], mi: dict[str, int]) -> bool:
    """True when an empty mod cell of `column` takes the matching D2R row's value (D2R_WHEN_EMPTY, D2R_WHEN_EMPTY_ROWS)."""
    if column in D2R_WHEN_EMPTY.get(table, ()):
        return True
    if table not in D2R_WHEN_EMPTY_ROWS:
        return False
    key, codes, cols = D2R_WHEN_EMPTY_ROWS[table]
    return column in cols and key in mi and mrow[mi[key]].strip().lower() in codes
# Engine tokens D2R renamed: a matching row always takes D2R's value. plrmode/monmode Code: 1.13c spells Sequence and
# Knockback "GH" like Get Hit; D2R's are SQ and KB, and skills.txt's SQ resolves through them (trap 1).
D2R_ALWAYS = {"plrmode": {"Code"}, "monmode": {"code"}}
# 32-bit fields printed unsigned by some tools: -1 as 4294967295 (trap 4). The .txt files hold real values, so this only
# catches stray ones. experience.txt holds real unsigned 32-bit values (D2R's own Warlock column).
UNSIGNED_32_TABLES = {"experience"}
ID_COMMENT_COLUMNS = {"*id", "*hcidx", "*index"}
KEYS = {"weapons": "code", "armor": "code", "misc": "code", "itemtypes": "Code", "treasureclassex": "Treasure Class",
        "objects": "Name", "gems": "code"}  # gems by item code: D2R's "Sapphire" is Median's "Saphire" (same codes)
# Tables merged by row position (the mod's row i is D2R's row i): books.txt, where the mod calls its three rows "unused"
# and D2R names its tomes; a keyed merge would add D2R's three rows after the mod's. lvlwarp.txt: the mod's 89 rows are 1.13c's
# in D2R's order, but 1.13c names both directions of five Act 5 warps alike ("Act 5 Ice Caves Up") where D2R says "... L" /
# "... R": keyed by Name, those 10 rows got no UniqueId / NoInteract and D2R's 10 rows were appended again (Ids 71-82 twice).
BY_ROW = {"books", "lvlwarp"}
# hiredesc.txt code -> the string key D2R's hireling.txt Normal rows use for the same description (ui.json strhirespecial*,
# skills.json skillname*: Fire Arrow, Cold Arrow, Lightning / Cold / Fire; Desert Mercenary Combat -> Prayer, Defensive ->
# Defiance, Offensive -> Blessed Aim)
HIREDESC_KEYS = {"farw": "strhirespecial1", "carw": "strhirespecial2", "ltng": "strhirespecial5", "cold": "strhirespecial6",
                 "fire": "strhirespecial7", "comb": "skillname99", "def": "skillname104", "off": "skillname108"}
# D2R-only columns (no 1.13c column) that a mod row matching a D2R row takes from it, because the game needs them. Every
# other D2R-only column gets the neutral default (empty), also on matched rows: the mod never had the feature, and D2R's
# values carried its own (ladder seasons, sunder charm flags, mercenary class items, ...). Columns of mapped data that
# D2R keeps on top are D2R_WHEN_EMPTY / D2R_ALWAYS; stop functions are skill_rules.
NEEDED_FROM_D2R: dict[str, set[str]] = {
    # difficultylevels: PvP / mercenary / Prime Evil damage percentages, hit-react buffers (0 would mean 0 % damage)
    "difficultylevels": {"*"},
    # charstats: light radius, casting delay floor, skill points per level, quality of the starting items (the potion
    # percentages are CONSTANTS: D2R scales them per class, 1.13c does not)
    "charstats": {"SkillsPerLevel", "LightRadius", "MinimumCastingDelay", *(f"item{n}quality" for n in range(1, 11))},
    # the towns and the Pandemonium finale: 1.13c refuses the town portal there in code, D2R reads this flag
    "levels": {"PreventTownPortal"},
    # level warp identity and the trap doors that cannot be clicked
    "lvlwarp": {"NoInteract", "UniqueId"},
    "objects": {"Class"},  # the class name D2R's code references the object by
    "belts": {"defaultItemTypeCol1", "defaultItemTypeCol2", "defaultItemTypeCol3", "defaultItemTypeCol4", "defaultItemCodeCol4"},
    # skills: 0 on passives and non-assignable skills, so they stay off the right-button list (blank = assignable);
    # skill_rules derives it for the mod's own passives
    "skills": {"rightskill"},
}
# Columns D2R's parser reads for a table although D2R's own file of it lacks them: the column is added to that table's header
# (before *eol) so the mod's values reach the game. misc `auto prefix` (bug #310): D2R loads weapons, armor and misc with ONE
# field list (0x318290-0x318423: three loads with the same list at [rbp-0x10] and record size 0x1c0) that holds
# "auto prefix" (0x1cfaff0), and Median's compiled misc.bin carries it at +0xf8 on 116 rows (amulet groups 491-497, 401).
EXTRA_COLUMNS = {"misc": ["auto prefix"]}


def with_extra_columns(table: str, header: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """D2R's header and rows plus EXTRA_COLUMNS[table] (empty cells), inserted before a trailing *eol column."""
    extra = [c for c in EXTRA_COLUMNS.get(table, []) if c not in header]
    if not extra:
        return header, rows
    at = len(header) - 1 if header and header[-1].lower() == "*eol" else len(header)
    return (header[:at] + extra + header[at:],
            [r[:at] + [""] * len(extra) + r[at:] for r in rows])


# (mod key column, D2R key column) where they differ
KEY_PAIRS = {"playerclass": ("Player Class", "Code"), "storepage": ("Store Page", "Code")}
# Mod columns D2R dropped on purpose; not copied to overflow/.
OBSOLETE = {"*": {"Beta", "Expansion", "eol", "EOL", "OpenBetaGfx", "Source Art", "Game Art"},
            "itemstatcost": {"ID"}, "states": {"id"}, "skills": {"Id"}, "missiles": {"Id"},
            "monstats": {"hcIdx"}, "objects": {"Id"}, "pettype": {"idx"}, "overlay": {"Frames"},
            "sounds": {"Index", "Volume", "Reverb", "Stereo", "Cache", "Async Only"},
            "soundenviron": {"EAX Env Size", "EAX Env Diff", "EAX Air Absorb"}, "gems": {"nummods"},
            "qualityitems": {"nummods"}, "runes": {"Rune Name"}}
# Tables with item property slots (code/param/min/max columns), for remap_property_params.
PROPERTY_TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic",
                   "rareprefix", "raresuffix", "qualityitems", "lowqualityitems", "gems", "cubemain", "monprop")
# Stat tooltip functions whose parameter is a skill: 15 on-event, 16 aura, 24 charges, 27/28 +skill.
SKILL_PARAM_DESCFUNCS = {"15", "16", "24", "27", "28"}
# Stat tooltip functions whose text D2R formats itself (reanimate, charged skill, skill on event): they keep D2R's key.
OWN_TEXT_FUNCS = {"22", "23", "24"}
# Stat tooltip functions whose format 1.13c hard-codes but D2R reads from descstrpos / descstrneg (D2R's formatter 0x2d6520,
# cases 27 / 28: the format is the row's descstrpos text, the arguments value, skill name and class-only text). Median's rows
# leave the cells empty, so D2R printed the dummy string 5382 ("FLYING POLAR BUFFALO ERROR", the id 1.13c gives any unknown key), bug #140. The D2R keys have 1.13c's
# words ("+%d to %s (%s Only)", "+%d to %s"); Median's string tables have no text of their own for them.
FORMAT_KEY_FUNCS = {"27": "ItemModifierClassSkill", "28": "ItemModifierNonClassSkill"}
# Missile cells changed to cut the missiles one launch makes, row -> column -> (Median's value, ours); Migrator.missile_load.
# Bug #395 (the Heretics' skull swarm): an impact every 2nd frame (do 15 Param1 = frequency), each impact hits twice as often
# (NextDelay, frames between two hits on a unit). Not SrcDamage 192: that doubles each hit's weapon share (D2R reads SrcDamage
# like 1.13c, tools/srcdamage.py) and the swarm then killed a 30,000-life character within 5 s (checks-20261029-052254-s2).
MISSILE_LOAD = {**{f"skullswarm{i}": {"Param1": ("1", "2")} for i in range(5)},
                "skullswarmimpact": {"NextDelay": ("4", "2")}}


read_tsv = idmap.read_tsv  # one record rule for the whole pipeline (tools/idmap.py)


def by_row_merge(mod_rows: list[list[str]], d2r_rows: list[list[str]], convert) -> list[list[str]]:
    """BY_ROW tables: the mod's row i is D2R's row i. A record takes D2R's row at its position as the match; a separator
    ("Expansion") keeps D2R's own separator row there (the classic bank's expansion marker); D2R rows past the mod's end follow."""
    out = []
    for i, r in enumerate(mod_rows):
        d = d2r_rows[i] if i < len(d2r_rows) else None
        if not idmap.is_record(r):
            out.append(d if d is not None and not idmap.is_record(d) else r)
        else:
            out.append(convert(r, d if d is not None and idmap.is_record(d) else None, None))
    return out + d2r_rows[len(mod_rows):]


def write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.writelines("\t".join(r) + "\r\n" for r in [header, *rows])

is_record = idmap.is_record


def larger_grid(mod: tuple[str, str], d2r: tuple[str, str]) -> bool:
    """True when the mod's grid (gridX, gridY) holds more cells than D2R's (inventory_sizes; D2R's wins a tie)."""
    def cells(g):
        x, y = (int(v) if re.fullmatch(r"-?\d+", v or "") else 0 for v in g)
        return max(x, 0) * max(y, 0)
    return cells(mod) > cells(d2r)


class Migrator:
    def __init__(self):
        self.m = idmap.IdMap.build(NAMED, D2R)
        self.report: list[str] = []
        self.dropped: dict[str, Counter] = defaultdict(Counter)
        self.overflow: dict[str, tuple[list[str], int]] = {}
        self.dangling: dict[str, int] = defaultdict(int)
        self.remapped: dict[str, Counter] = {}
        self.left_out: dict[str, Counter] = defaultdict(Counter)  # D2R-only columns whose D2R value was not copied
        self.type_report: dict = {}
        self.skilldesc_renames = self.colliding_skilldescs()
        smap = OUT / "strings_map.json"
        self.smap = json.loads(smap.read_text("utf-8")) if smap.exists() else None
        if self.smap is None:
            print("txt_migrate: work/mod/strings_map.json missing (run tools/tbl2json.py --excel-dir work/named): "
                  "localization cells stay unqualified", file=sys.stderr)

    def colliding_skilldescs(self) -> dict[str, str]:
        """skilldesc keys of the mod's skills that idmap renamed (Abyss, Ring of Fire, Apocalypse: the mod's row has the key of a
        D2R skill added later) and D2R also has a skilldesc row of: the description follows its skill (`<key>_mxl`), or the
        keyed merge would give D2R's Warlock skill Median's description and tree slot (two class skills on one slot)."""
        mh, mrows = idmap.read_tsv(NAMED / "skills.txt")
        sd = mh.index("skilldesc")
        d2r = set()
        for bank in ("base", ""):
            t = self.m.d2r.table("skilldesc", bank)
            if t:
                d2r |= {r[t[0].index("skilldesc")].lower() for r in idmap.records(t[1])}
        out = {}
        for row, srow in zip(self.m.spaces["skills"].rows, idmap.records(mrows)):
            if row.name != row.key and srow[sd] and srow[sd].lower() in d2r:
                out[srow[sd]] = srow[sd] + "_mxl"
        return out

    def kind(self, table: str) -> str:
        if table in D2R_ONLY:
            return "d2r_only"
        if table in BY_ROW:
            return "by_row"
        if table in REPLACE:
            return "replace"
        if table == "itemtypes":
            return "itemtypes"
        if table in idmap.ENTITIES and table in self.m.spaces:
            return "d2r_wins_indexed" if table in D2R_WINS else "indexed"
        if table in D2R_WINS:
            return "d2r_wins"
        return "keyed"

    def migrate(self, table: str) -> None:
        mh, mall = idmap.read_tsv(NAMED / f"{table}.txt")
        if table == "hireling" and "HireDesc" in mh:
            # hireling.HireDesc is a hiredesc code ("farw"); D2R's column holds a string key, and the mod's hiredesc.txt
            # names keys no string table has ("Cold Arrow"): the code maps to the key D2R's own Normal rows use for it
            hi = mh.index("HireDesc")
            for r in idmap.records(mall):
                r[hi] = HIREDESC_KEYS.get(r[hi], r[hi])
        if table == "missiles" and "LevRange" in mh and "Range" in mh:
            # D2R merged LevRange into Range (now an expression): range + levrange * level
            ri, li = mh.index("Range"), mh.index("LevRange")
            for r in mall:
                if r[li] not in ("", "0"):
                    r[ri] = f"{r[ri] or 0}+{r[li]}*lvl"
            mh = [("*LevRange" if c == "LevRange" else c) for c in mh]
        # ids, renames, slots and hidden references of the MOD table, before any D2R row is merged in (tools/idmap.py)
        changes = self.m.remap_table(table, mh, mall)
        if changes:
            self.remapped[table] = changes
        mall = [[c.rstrip() for c in r] for r in mall]  # .bin codes are space-padded ("gps ")
        if self.skilldesc_renames and table in ("skills", "skilldesc"):
            ci = mh.index("skilldesc")
            for r in idmap.records(mall):
                r[ci] = self.skilldesc_renames.get(r[ci], r[ci])
        mrecs = idmap.records(mall)
        banks = {"base": D2R / "base" / f"{table}.txt", "rotw": D2R / f"{table}.txt"}
        banks = {k: v for k, v in banks.items() if v.exists()}
        if not banks:
            self.report.append(f"| {table} | no D2R table | {len(mrecs)} | | | skipped (needs a custom table or plugin) |")
            return
        d2r = {k: with_extra_columns(table, *idmap.read_tsv(v)) for k, v in banks.items()}
        kind = self.kind(table)
        for bank, (dh, drows_all) in d2r.items():
            drows = idmap.records(drows_all)
            cmap = self.column_map(table, mh, dh)
            mi = {c: i for i, c in enumerate(mh)}
            di = {c: i for i, c in enumerate(dh)}
            consts = CONSTANTS.get(table, {})
            needed = NEEDED_FROM_D2R.get(table, set())

            dead_refs = self.refs_into_replaced(table, dh)
            string_cols, bool_cols = self.typed_columns(table, dh)

            def median_value(dc: str, v: str) -> str:
                # string keys Median only had as numbers are mxl_<id> after tools/tbl2json.py
                if dc in string_cols and v.isdigit() and v in self.idkeys:
                    # the bare key: every pass below sees plain keys, namespace_cells() qualifies the cells at the end
                    return strings_ns.bare(self.idkeys[v])
                # the first decoder wrote a few small numbers as raw control characters ("")
                if v and dc in self._int_cols.get(table, ()) and len(v) == 1 and ord(v) < 32:
                    return str(ord(v))
                if table not in UNSIGNED_32_TABLES and v.isdigit() and 2**31 <= int(v) < 2**32:
                    return str(int(v) - 2**32)
                # D2R booleans are 0/1; 1.13c sometimes stored other non-zero flags
                if dc in bool_cols and re.fullmatch(r"-?\d+", v) and v not in ("0", "1"):
                    return "1"
                return v

            def convert(mrow: list[str], match: list[str] | None, row_id: int | None) -> list[str]:
                out = []
                for dc in dh:
                    if dc in cmap:
                        v = median_value(dc, mrow[mi[cmap[dc]]])
                        if match is not None and dc in D2R_ALWAYS.get(table, ()):
                            v = match[di[dc]]
                        elif v == "" and match is not None and d2r_when_empty(table, dc, mrow, mi):
                            v = match[di[dc]]
                        out.append(v)
                    elif match is not None and (dc in needed or "*" in needed) and dc not in dead_refs:
                        out.append(match[di[dc]])  # D2R-only column the game needs on this row (NEEDED_FROM_D2R)
                    elif dc in consts:
                        out.append(consts[dc])
                    elif dc.lower() in ID_COMMENT_COLUMNS and row_id is not None:
                        out.append(str(row_id))
                    else:
                        # a D2R-only column (ladder season, sunder flag, merc class item ...) takes the neutral default
                        # even where a D2R row matches: the mod never had that feature
                        if match is not None and dc in di and match[di[dc]] not in ("", "0") and not dc.startswith("*"):
                            self.left_out[table][dc] += 1
                        out.append("")
                return out

            def d2r_rows_by_id() -> list[list[str]]:
                # D2R rows by ID; the smaller bank borrows the IDs it lacks from the other bank (same IDs in both)
                by_id = list(drows)
                for b, (oh, orows) in d2r.items():
                    if b != bank:
                        for r in idmap.records(orows)[len(by_id):]:
                            by_id.append([r[oh.index(c)] if c in oh else "" for c in dh])
                return by_id

            if kind in ("indexed", "d2r_wins_indexed"):
                by_id = d2r_rows_by_id()
                space = self.m.spaces[table]
                rows = []
                for src, i in self.m.order(table):
                    if src == "d2r":
                        rows.append(self.drop_dangling(by_id[i], dh, dead_refs, table, i) if i < len(by_id)
                                    else convert([""] * len(mh), None, i))
                        continue
                    row = space.rows[i]
                    match = by_id[row.id] if row.kind == "vanilla" and row.id < len(by_id) else None
                    if match is not None and kind == "d2r_wins_indexed":
                        rows.append(match)
                    else:
                        rows.append(convert(mrecs[i], match, row.id))
            elif kind == "by_row":
                rows = by_row_merge([r for r in mall if any(r)], [r for r in drows_all if any(r)], convert)
            else:
                kcol = KEYS.get(table) or mh[0]
                dkey = kcol if kcol in di else dh[0]
                mkey = kcol if kcol in mi else mh[0]
                if table in KEY_PAIRS and KEY_PAIRS[table][1] in di:
                    mkey, dkey = KEY_PAIRS[table]
                d_by_key = {}
                for r in drows:
                    d_by_key.setdefault(r[di[dkey]].lower(), r)
                m_keys = {r[mi[mkey]].lower() for r in mrecs}
                if kind == "d2r_only":
                    rows = list(drows_all)  # exactly D2R's file, "Expansion" marker rows included
                elif kind == "d2r_wins":
                    rows = list(drows) + [convert(r, None, None) for r in mrecs if r[mi[mkey]].lower() not in d_by_key]
                elif kind == "itemtypes":
                    # every D2R type at its D2R number, the mod's own types after them (the engine tests fixed numbers)
                    conv = [convert(r, d_by_key.get(r[mi[mkey]].lower()), None) for r in mrecs]
                    rows, rep = idmap.align_item_types(dh, conv, *self.m.d2r.largest("itemtypes"))
                    self.type_report[bank] = rep
                else:
                    src = [r for r in mall if any(r)]  # the mod's rows, "Expansion" separators included
                    rows = [convert(r, d_by_key.get(r[mi[mkey]].lower()), None) for r in src]
                    if kind == "keyed":
                        rows += [r for r in drows if r[di[dkey]].lower() not in m_keys]

            write_tsv(OUT / "data" / "global" / "excel" / ("base" if bank == "base" else "") / f"{table}.txt", dh, rows)
            if bank == next(iter(d2r)):
                used = set(cmap.values())
                obsolete = OBSOLETE["*"] | OBSOLETE.get(table, set())
                keep = []
                for c in mh:
                    if c in used or c.startswith("*") or not c:
                        continue
                    n = sum(1 for r in mrecs if r[mi[c]] not in ("", "0"))
                    if n:
                        self.dropped[table][c] = n
                        if c not in obsolete:
                            keep.append(c)
                if keep:  # values D2R has no column for: kept for plugins / later decisions
                    rows_o = [[r[0]] + [r[mi[c]] for c in keep] for r in mrecs
                              if any(r[mi[c]] not in ("", "0") for c in keep)]
                    write_tsv(OUT / "overflow" / f"{table}.txt", [mh[0]] + keep, rows_o)
                    self.overflow[table] = (keep, len(rows_o))
                defaulted = [c for c in dh if c not in cmap and not c.startswith("*")]
                self.report.append(f"| {table} | {kind} | {len(mrecs)} | {len(drows)} | {len(rows)} | "
                                   f"{len(cmap)} mapped, {len(defaulted)} D2R-only |")

    def skill_rules(self) -> None:
        """Skill rules for 1.13c rows on D2R (playbook traps 1 and 6). The slot renumbering itself (109 -> 9, 64 / 37 -> 67,
        cltstfunc 82 -> none, cltdofunc 22 -> 113) is tools/idmap.py's, applied to the mod table before the merge.
        - anim / seqtrans: a 1.13c Sequence skill may carry GH (the plrmode.txt code of mode 18 in some tools' output);
          D2R spells it SQ and reads GH as get hit (knockback frames, server never starts the skill).
        - stop functions: D2R gives Whirlwind (srvdofunc 76 / cltdofunc 45) srvstopfunc / cltstopfunc 1; mod rows on a do
          function D2R pairs with a stop function get the same one (1.13c has no stop columns)."""
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "skills.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            dh, drows = idmap.read_tsv(D2R / bank / "skills.txt")
            drows = idmap.records(drows)
            ss, cs = h.index("srvstopfunc"), h.index("cltstopfunc")
            do, cdo = h.index("srvdofunc"), h.index("cltdofunc")
            an, st = h.index("anim"), h.index("seqtrans")
            srv_stop = {r[dh.index("srvdofunc")]: r[dh.index("srvstopfunc")] for r in drows
                        if r[dh.index("srvstopfunc")] not in ("", "0")}
            clt_stop = {r[dh.index("cltdofunc")]: r[dh.index("cltstopfunc")] for r in drows
                        if r[dh.index("cltstopfunc")] not in ("", "0")}
            n_stop = n_seq = n_right = n_right1 = 0
            plugin, no_nova = [], []
            cma = h.index("cltmissilea")
            rs = h.index("rightskill")
            pst, pst1, au = h.index("passivestate"), h.index("passivestat1"), h.index("aura")
            used = [h.index(c) for c in ("srvstfunc", "srvdofunc", "srvmissile", "srvmissilea", "cltstfunc", "cltdofunc", "aura")]
            for r in rows:
                if not is_record(r):
                    continue
                if r[an] == "GH" or r[st] == "GH":
                    r[an] = "SQ" if r[an] == "GH" else r[an]
                    r[st] = "SQ" if r[st] == "GH" else r[st]
                    n_seq += 1
                if r[do] in srv_stop and r[ss] in ("", "0"):
                    r[ss] = srv_stop[r[do]]
                    n_stop += 1
                if r[cdo] in clt_stop and r[cs] in ("", "0"):
                    r[cs] = clt_stop[r[cdo]]
                if r[cdo] == CLT_NOVA and not r[cma]:
                    # D2R's client nova (cltdofunc 25, 0x220140) asserts `nMissile >= 0` without a cltmissilea and then draws
                    # nothing (returns 0); no client function at all is the same without the assert (bug #51: Black Mass,
                    # Hymn, Darkness Falls, the Totemic buffs)
                    r[cdo] = ""
                    no_nova.append(r[0])
                if r[cdo] == "113":
                    plugin.append(r[0])
                if r[rs] == "" and (r[pst] or r[pst1]) and not r[au] and not r[do]:
                    r[rs] = "0"  # a passive of the mod: not assignable to the right button (D2R's own passives say 0)
                    n_right += 1
                elif r[rs] == "":
                    # D2R reads a blank rightskill as 0 (bug #16: Blackstorm, no leftskill, could not be selected at all);
                    # 1.13c has no such column and puts every usable skill on the right button: 1 for a row that does
                    # something when used, 0 (D2R's passives) for one that does not
                    r[rs] = "1" if any(r[i] not in ("", "0") for i in used) else "0"
                    n_right1 += r[rs] == "1"
                    n_right += r[rs] == "0"
            write_tsv(p, h, rows)
            if bank == "base":
                self.report.append(f"\nskills: {n_stop} given D2R's stop function for their do function (Whirlwind); {n_seq} "
                                   f"anim/seqtrans GH -> SQ; {n_right} passives given rightskill 0, {n_right1} usable skills rightskill 1; rows on the plugin's cltdofunc 113 (was 22): {', '.join(plugin) or 'none'}; "
                                   f"client nova (cltdofunc 25) without cltmissilea, cltdofunc emptied (bug #51): {', '.join(no_nova) or 'none'}")

    def stat_send_bits(self) -> None:
        """A state's stat list goes to the client with each stat cut to its itemstatcost `Send Bits`. `modifierlist_skill` (350,
        the skill a state belongs to) has 9 bits in D2R and in 1.13c, enough for D2R's skill ids but not for Median's (up to 1109):
        the client then holds skill & 511, and D2R's client skill do dispatcher (0x216920), which looks for the caster's
        aurastate list of the skill it runs, finds none and asserts `nSkillCastId` (bug #20: Blackstorm, 514 -> 2). The column
        gets the bits of the highest skill id (1.13c had no such client check)."""
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "itemstatcost.txt").exists() or not (d / "skills.txt").exists():
                continue
            sh, srows = read_tsv(d / "skills.txt")
            ids = [int(r[sh.index("*Id")]) for r in srows if is_record(r) and re.fullmatch(r"\d+", r[sh.index("*Id")])]
            need = max(ids, default=0).bit_length()
            h, rows = read_tsv(d / "itemstatcost.txt")
            sb = h.index("Send Bits")
            for r in rows:
                if is_record(r) and r[0] == "modifierlist_skill" and int(r[sb] or 0) < need:
                    if bank == "base":
                        self.report.append(f"\nitemstatcost: modifierlist_skill Send Bits {r[sb] or 0} -> {need} (skill ids up to {max(ids)}, bug #20)")
                    r[sb] = str(need)
            write_tsv(d / "itemstatcost.txt", h, rows)

    def stat_save_add(self) -> None:
        """An item stat is saved as value + `Save Add` in `Save Bits` (docs/save-format.md). Median's own tables give three
        level-120 uniques values below -Save Add (mxlname_12 / Skin of Kabraxis: light radius -20 / -10 with Add 5;
        Angelhost: +life -250 with Add 150): value + Add is negative, does not fit the field and the item came back changed after
        Save and Exit (in 1.13c too, same columns). Save Add is raised to the lowest value the item tables give the stat
        (save_audit.stat_ranges), Save Bits widened if the highest one then no longer fits. Changes the saved form of that stat:
        items saved before keep their old bits, read with the new Add (test characters only)."""
        import save_audit  # noqa: E402  (imports d2save; both only read tables)
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "itemstatcost.txt").exists() or not (d / "properties.txt").exists():
                continue
            ranges = save_audit.stat_ranges(str(d))
            h, rows = read_tsv(d / "itemstatcost.txt")
            sb, sa = h.index("Save Bits"), h.index("Save Add")
            changed = []
            for r in rows:
                if not is_record(r) or r[0] not in ranges or not re.fullmatch(r"\d+", r[sb] or ""):
                    continue
                bits, add = int(r[sb]), int(r[sa] or 0) if re.fullmatch(r"-?\d+", r[sa] or "") else 0
                low, high = ranges[r[0]]
                if bits == 0 or low + add >= 0:
                    continue
                new_add, new_bits = -low, bits
                while high + new_add >= 1 << new_bits:
                    new_bits += 1
                changed.append(f"{r[0]} Save Add {add} -> {new_add}" + (f", Save Bits {bits} -> {new_bits}" if new_bits != bits else "")
                               + f" (item values {low}..{high})")
                r[sa], r[sb] = str(new_add), str(new_bits)
            write_tsv(d / "itemstatcost.txt", h, rows)
            if bank == "base" and changed:
                self.report.append("\nitemstatcost: saved item values below -Save Add (docs/save-format.md): " + "; ".join(changed))

    def missile_slot_report(self) -> None:
        """Missiles on slots that need a game check (docs/id-mapping.md: pSrvHitFunc 6 = monster spawners, 23, cltdofunc 83).
        A function cell that is not a number (`*12` of royalstrikechainlightning, a commented-out value: 1.13c reads it as 0)
        is emptied in both banks; D2R's RotW table fixed that row, its Classic table still has the text."""
        n = 0
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "missiles.txt"
            h, rows = read_tsv(p)
            cols = [h.index(c) for c in idmap.MISSILE_SLOT_COLS if c in h]
            for r in rows:
                for ci in cols:
                    if r[ci] and not re.fullmatch(r"-?\d+", r[ci]):
                        r[ci] = ""
                        n += bank == "base"
            write_tsv(p, h, rows)
        h, rows = read_tsv(OUT / "data" / "global" / "excel" / "base" / "missiles.txt")
        hit6 = [r[0] for r in rows if is_record(r) and r[h.index("pSrvHitFunc")] == "6"]
        self.report.append(f"\nmissiles: {n} non-numeric function cells emptied; {len(hit6)} rows on pSrvHitFunc 6 (spawn the "
                           f"monster row in sHitPar1, remapped through the monstats id map; game-check)")



    def missile_load(self) -> None:
        """Bug #395: the Heretics' attack (`skullswarmcenter`, monstats MissA1 of cultist2 / hell_cultist and their elite
        rows, FetishBlowgun AI) makes about 425 server missiles per shot (tools/missile_chains.py): 4 skulls, each hit
        chaining up to 5 more (hit 20, one target), and every skull lays a `skullswarmimpact` each frame (do 15, Param1 1)
        for its 10 frames; each impact can spawn `teethexplodered`. A pack of Heretics kept D2R at ~100 new missiles per
        frame until it hung. Same numbers in Median's missiles.bin and the D2R functions read the same columns, so this is
        load, not a conversion bug. The skulls now lay an impact every 2nd frame and each impact may hit a unit every 2
        frames instead of 4 (13-frame life: about 6 hits instead of 3), so a skull pass deals about the same damage with
        half the missiles. A cell that no longer holds Median's value is left alone and reported."""
        done, skipped = [], []
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "missiles.txt"
            h, rows = read_tsv(p)
            for r in rows:
                for col, (old, new) in MISSILE_LOAD.get(r[0], {}).items():
                    ci = h.index(col)
                    if r[ci].strip() == old:
                        r[ci] = new
                        done += [f"{r[0]}.{col} {old}->{new}"] if bank == "base" else []
                    elif r[ci].strip() != new and bank == "base":
                        skipped.append(f"{r[0]}.{col}={r[ci]!r} (expected {old})")
            write_tsv(p, h, rows)
        self.report.append(f"\nmissiles: load rules (bug #395) applied {len(done)}: " + ", ".join(done)
                           + (f"; NOT applied (Median's value changed): {', '.join(skipped)}" if skipped else ""))

    @property
    def idkeys(self) -> dict[str, str]:
        """Median string id -> placeholder key (`mxl_<id>`) for strings the .tbl gives no usable key (strings_map.json)."""
        if not hasattr(self, "_idkeys"):
            ids = (self.smap or {}).get("id_keys", {})
            self._idkeys = {k: v for k, v in ids.items() if strings_ns.bare(v).startswith("mxl_")}
        return self._idkeys

    def inventory_sizes(self) -> None:
        """D2R's inventory.txt has 2 rows per screen resolution and page and asserts on any other layout (trap 11), so the
        file is D2R's with the mod's grid sizes (gridX / gridY of 2012's inventory.txt: player 10x6, transmog box 10x8, ...)
        copied into every row of the same class name. D2R's Warlock rows take the Assassin's. Classic panel art and slot
        positions stay D2R's (2012's art is the art lane's).
        Owner decision 2026-10-28: per panel the grid with MORE cells wins (Median's or D2R's; D2R's on a tie), so the
        player inventory (10x6 > 10x4) and the cube (10x8 > 3x4) are Median's, the stash / shared stash tabs, trade,
        vendor and the classic bank stay D2R's (equal sizes). docs/hd-ui.md has the table."""
        mh, mrows = read_tsv(NAMED / "inventory.txt")
        grid = {r[0]: (r[mh.index("gridX")], r[mh.index("gridY")]) for r in mrows if r[0] and r[0] != "Expansion"}
        n = 0
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "inventory.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            gx, gy = h.index("gridX"), h.index("gridY")
            for r in rows:
                size = grid.get(r[0]) or (grid.get(r[0].replace("Warlock", "Assassin")) if "Warlock" in r[0] else None)
                if size and larger_grid(size, (r[gx], r[gy])) and (r[gx], r[gy]) != size:
                    r[gx], r[gy] = size
                    n += 1
            write_tsv(p, h, rows)
        self.report.append(f"\ninventory: {n} rows set to the mod's larger grid sizes (D2R's 2-rows-per-page layout kept)")



    def shrine_strings(self) -> None:
        """shrines.txt StringName / StringPhrase: Median writes `blah` in all 23 rows. 1.13c never read the columns (the shrine
        text is the tbl's ShrId<n> / ShrMsg<n> by row; Median's tbl has all 46), D2R reads them. Row i takes D2R's cells of
        row i (`ShrId<i>` / `ShrMsg<i>`, which the d2r: overrides give Median's wording); tools/string_gaps.py."""
        n = 0
        for bank in ("base", ""):
            mine, theirs = OUT / "data" / "global" / "excel" / bank / "shrines.txt", D2R / bank / "shrines.txt"
            if not (mine.exists() and theirs.exists()):
                continue
            h, rows = read_tsv(mine)
            dh, drows = read_tsv(theirs)
            cols = [(h.index(c), dh.index(c)) for c in ("StringName", "StringPhrase")]
            for r, d in zip(idmap.records(rows), idmap.records(drows)):
                for mi, di in cols:
                    if r[mi] == "blah":
                        r[mi] = d[di]
                        n += 1
            write_tsv(mine, h, rows)
        self.report.append(f"\nshrines: {n} `blah` text cells take D2R's ShrId<n> / ShrMsg<n> (1.13c ignored the columns)")

    def clear_unique_flags(self) -> None:
        """An item base with `unique` 1 is always created as a unique, and D2R then stores the index of its uniqueitems row.
        With no row the index is -1 (saved as 4095), and loading the character asserts `nIndex >= 0 && nIndex < uniqueItemsTbl.size()`
        (bug #7: the starting kit's Median Statue `zen`). D2R's own quest bases carry the flag without a row too and are created by
        quest code that works, so only a base D2R does not flag itself loses the flag; it is then a normal item."""
        cleared: list[str] = []
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "uniqueitems.txt").exists():
                continue
            uh, urows = read_tsv(d / "uniqueitems.txt")
            with_row = {r[uh.index("code")].strip() for r in idmap.records(urows)}
            for table in ("weapons", "armor", "misc"):
                h, rows = read_tsv(d / f"{table}.txt")
                low = [c.lower() for c in h]
                if "unique" not in low:
                    continue
                ui, ci = low.index("unique"), h.index("code")
                theirs = D2R / bank / f"{table}.txt"
                d2r_flagged: set[str] = set()
                if theirs.exists():
                    dh, drows = read_tsv(theirs)
                    dlow = [c.lower() for c in dh]
                    if "unique" in dlow:
                        d2r_flagged = {r[dh.index("code")] for r in idmap.records(drows) if r[dlow.index("unique")] not in ("", "0")}
                for r in idmap.records(rows):
                    if r[ui] not in ("", "0") and r[ci] not in with_row and r[ci] not in d2r_flagged:
                        r[ui] = "0"
                        if bank == "base":
                            cleared.append(f"{table}:{r[ci]}")
                write_tsv(d / f"{table}.txt", h, rows)
        self.report.append("\nalways-unique bases without a uniqueitems row (bug #7), `unique` set to 0: " + (", ".join(cleared) or "none"))

    def carry_numbers(self) -> None:
        """uniqueitems.txt `carry1`: 1.13c reads it as a flag (refuse a second copy of the same unique), D2R 3.3 as a number
        (record +0x30): its placement test (0x473960) refuses a carry1 unique when a carried unique has the same non-zero number,
        and D2R's own rows use 1001 / 1002 / 1003 (Gheed's Fortune, Annihilus, Hellfire Torch). Median XL 2012 writes 1 on all 45
        carry1 rows (relics, quest charms), so on D2R one of them blocked every other (bug #280). Each carry1 row gets its own
        number, record index + 1: two copies of one row still match, two rows never do, as in 1.13c."""
        n = 0
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "uniqueitems.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            if "carry1" not in h:
                continue
            ci = h.index("carry1")
            for i, r in enumerate(idmap.records(rows)):
                v = r[ci].strip()
                if v and v.lstrip("-").isdigit() and int(v) > 0 and v != str(i + 1):
                    r[ci] = str(i + 1)
                    n += bank == "base"
            write_tsv(p, h, rows)
        self.report.append(f"\nuniqueitems: {n} carry1 cells set to the record index + 1 (D2R compares the number, 1.13c the unique; bug #280)")

    def item_spell_states(self) -> None:
        """misc rows whose item spell names a state D2R refuses (bug #191, item_spell_fix): run after clean_references, which
        empties the state names states.txt does not have."""
        done: list[str] = []
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "misc.txt").exists() or not (d / "states.txt").exists():
                continue
            sh, srows = read_tsv(d / "states.txt")
            states = {r[0].strip() for r in idmap.records(srows) if r[0].strip()}
            inert = next((r for r in idmap.records(srows) if r[0].strip() == ITEM_SPELL_INERT_STATE), None)
            if inert is None or any(v.strip() for c, v in zip(sh[1:], inert[1:]) if not c.startswith("*")):
                raise SystemExit(f"txt_migrate: states {ITEM_SPELL_INERT_STATE!r} is missing or not empty in {d}")
            h, rows = read_tsv(d / "misc.txt")
            for r in idmap.records(rows):
                fix = item_spell_fix(dict(zip(h, r)), states)
                for c, v in fix.items():
                    r[h.index(c)] = v
                if fix and bank == "base":
                    cells = ", ".join(c + " " + (v or "empty") for c, v in fix.items())
                    done.append(f"{r[h.index('code')]} ({cells})")
            write_tsv(d / "misc.txt", h, rows)
        self.report.append("\nitem spells with a state D2R refuses (bug #191): " + ("; ".join(done) or "none"))

    def state_colour_shifts(self) -> None:
        """states.txt colorshift values HD draws far from classic (STATE_COLOUR_SHIFTS, bug #496)."""
        done: list[str] = []
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "states.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            names = state_colour_shift_fix(h, idmap.records(rows))
            write_tsv(p, h, rows)
            if bank == "base":
                done = [f"{n} {STATE_COLOUR_SHIFTS[n][0]} -> {STATE_COLOUR_SHIFTS[n][1]}" for n in names]
        self.report.append("\nstates colorshift for HD (bug #496): " + (", ".join(done) or "none"))

    def book_cursors(self) -> None:
        """misc `spellicon` of the scroll and tome codes from books.txt `SpellIcon`, as 1.13c reads it (bug #485, book_spell_icons)."""
        done: list[str] = []
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "misc.txt").exists() or not (d / "books.txt").exists():
                continue
            icons = book_spell_icons(*read_tsv(d / "books.txt"))
            h, rows = read_tsv(d / "misc.txt")
            if "spellicon" not in h:
                continue
            ci, si = h.index("code"), h.index("spellicon")
            for r in idmap.records(rows):
                code = r[ci].strip()
                if code in icons and r[si].strip() != icons[code]:
                    if bank == "base":
                        done.append(f"{code} {r[si].strip() or 'empty'} -> {icons[code]}")
                    r[si] = icons[code]
            write_tsv(d / "misc.txt", h, rows)
        self.report.append("\nmisc spellicon of scrolls / tomes from books.txt SpellIcon (bug #485): " + (", ".join(done) or "none"))

    def conversion_calcs(self) -> None:
        """calc1 / calc2 of the srvdofunc 51 rows: 1.13c's conversion chance and length where D2R reads them (bug #487)."""
        done: list[str] = []
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "skills.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            lines = conversion_calcs(h, list(idmap.records(rows)))
            write_tsv(p, h, rows)
            if bank == "base":
                done = lines
        self.report.append("\nskills srvdofunc 51 conversion chance / length into calc1 / calc2 (bug #487): " + ("; ".join(done) or "none"))

    def hireling_level_difference(self) -> None:
        """hireling.HiringMaxLevelDifference is D2R's column for a rule 1.13c keeps in code: how far a mercenary's level may
        lie from the player's when the hire list is made. D2R's own rows give it per Version (classic 0: 5, expansion 100: 1);
        a key match would give every Median row the first D2R row's value (Rogue Scout, classic: 5). Each Median row takes the
        value D2R uses for its Version (docs/median-rules-audit.md ME4)."""
        done = []
        for bank in ("base", ""):
            ours, theirs = OUT / "data" / "global" / "excel" / bank / "hireling.txt", D2R / bank / "hireling.txt"
            if not (ours.exists() and theirs.exists()):
                continue
            dh, drows = read_tsv(theirs)
            if "HiringMaxLevelDifference" not in dh or "Version" not in dh:
                continue
            by_version: dict[str, set[str]] = {}
            for r in idmap.records(drows):
                by_version.setdefault(r[dh.index("Version")].strip(), set()).add(r[dh.index("HiringMaxLevelDifference")].strip())
            h, rows = read_tsv(ours)
            vi, li = h.index("Version"), h.index("HiringMaxLevelDifference")
            n = 0
            for r in idmap.records(rows):
                values = by_version.get(r[vi].strip(), set())
                if len(values) == 1:
                    r[li] = next(iter(values))
                    n += 1
            write_tsv(ours, h, rows)
            done.append(f"{bank or 'rotw'} {n}")
        self.report.append("\nhireling HiringMaxLevelDifference by Version from D2R's rows: " + (", ".join(done) or "none"))

    # difficultylevels columns for rules 1.13c keeps in code (DF11, lane rulescheck2): the Fire Enchanted death explosion is 3/4
    # of the damage on Normal, 2/3 on Nightmare and 1/8 on Hell in 1.14d (0x5a2725-0x5a2766, the same rule as 1.13c); D2R's own
    # rows have 75 / 50 / 13 %, so Nightmare takes 67 (the nearest whole percent of 2/3)
    DIFFICULTY_CODE_RULES = {"MonsterFireEnchantExplosionDamagePercent": {"Normal": "75", "Nightmare": "67", "Hell": "13"}}

    def difficulty_code_rules(self) -> None:
        """Writes DIFFICULTY_CODE_RULES into difficultylevels.txt by the row's Name (the D2R-only columns came from D2R's rows)."""
        done = []
        for bank in ("base", ""):
            ours = OUT / "data" / "global" / "excel" / bank / "difficultylevels.txt"
            if not ours.exists():
                continue
            h, rows = read_tsv(ours)
            n = 0
            for col, by_name in self.DIFFICULTY_CODE_RULES.items():
                if col not in h:
                    continue
                ci = h.index(col)
                for r in idmap.records(rows):
                    if r[0].strip() in by_name and r[ci] != by_name[r[0].strip()]:
                        r[ci] = by_name[r[0].strip()]
                        n += 1
            write_tsv(ours, h, rows)
            done.append(f"{bank or 'rotw'} {n}")
        self.report.append("\ndifficultylevels rules from 1.13c's code (DIFFICULTY_CODE_RULES): " + (", ".join(done) or "none"))

    EVENT_STATS = {"item_skillonattack", "item_skillonkill", "item_skillondeath", "item_skillonhit", "item_skillonlevelup",
                   "item_skillongethit"}

    def monprop_event_skills(self) -> None:
        """A monprop event property (hit-skill, kill-skill, death-skill, att-skill, gethit-skill, levelup-skill) whose skill has
        no `ItemEffect` makes D2R assert `ptSkill->nItemEffect != 0` (D2Game SkillItemEffect.cpp:136) when the event fires
        (bug #32: `hornedgods` death-skill 524 Living Flame; also elite_goatpriest5 Widowmaker, dark_master1 AngirisChosen,
        dragoncompanions Dragon Firebolt Wave). 1.13c runs no item effect for such a row, so the property did nothing in Median;
        it is emptied (monsters show no property text). The same case on items (tooltips) is left alone: bug #40."""
        dropped: list[str] = []
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "monprop.txt").exists() or not (d / "skills.txt").exists():
                continue
            ph, prows = read_tsv(d / "properties.txt")
            stat_cols = [i for i, c in enumerate(ph) if re.fullmatch(r"stat\d", c)]
            events = {r[ph.index("code")] for r in idmap.records(prows) if any(r[i] in self.EVENT_STATS for i in stat_cols)}
            sh, srows = read_tsv(d / "skills.txt")
            sid, sname, seff = idmap.col(sh, "*Id"), sh.index("skill"), sh.index("ItemEffect")
            no_effect: set[str] = set()
            for n, r in enumerate(idmap.records(srows)):
                if r[seff] in ("", "0"):
                    no_effect |= {r[sid] if sid is not None else str(n), r[sname].lower()}
            mh, mrows = read_tsv(d / "monprop.txt")
            for r in idmap.records(mrows):
                for i, c in enumerate(mh):
                    m = re.fullmatch(r"prop(\d)( \([NH]\))?", c)
                    if not m or r[i] not in events:
                        continue
                    par = mh.index(f"par{m[1]}{m[2] or ''}")
                    if r[par].lower() not in no_effect:
                        continue
                    if bank == "base":
                        dropped.append(f"{r[0]} {c} {r[i]} {r[par]}")
                    for name in ("prop", "chance", "par", "min", "max"):
                        r[mh.index(f"{name}{m[1]}{m[2] or ''}")] = ""
            write_tsv(d / "monprop.txt", mh, mrows)
        self.report.append(f"\nmonprop event properties on skills without ItemEffect (bug #32), emptied: {len(dropped)}: "
                           + (", ".join(dropped) or "none"))

    def median_stat_wording(self) -> None:
        """The mod's wording for stat lines: tbl2json keeps D2R's text for a key whose printf placeholders differ and puts the
        mod's text under `<key>_mxl` (strings_map kept_alias). itemstatcost description cells name that alias, except for the
        functions that format a D2R text of their own (OWN_TEXT_FUNCS)."""
        kept = (self.smap or {}).get("kept_alias", {})
        moved = skipped = 0
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "itemstatcost.txt"
            if not p.exists() or not kept:
                continue
            h, rows = read_tsv(p)
            sets = (("descfunc", ("descstrpos", "descstrneg", "descstr2")), ("dgrpfunc", ("dgrpstrpos", "dgrpstrneg", "dgrpstr2")))
            moved = skipped = 0
            for r in rows:
                if not is_record(r):
                    continue
                for fn_col, str_cols in sets:
                    for c in (h.index(x) for x in str_cols):
                        if r[c] in kept:
                            if r[h.index(fn_col)] in OWN_TEXT_FUNCS:
                                skipped += 1
                            else:
                                r[c] = kept[r[c]]
                                moved += 1
            write_tsv(p, h, rows)
        self.report.append(f"\nstat wording (itemstatcost): {moved} description cells name the mod's text (<key>_mxl), {skipped} keep D2R's")

    def median_skill_wording(self) -> None:
        """Skill tooltip lines (bug #396). D2R's line renderer (0x287a50) still builds 1.13c's line types 1-73 by appending:
        text A / B, then the number, then a hard-coded unit, as 1.13c did; only types 13, 34, 36, 40 (text A), 53-56, 66, 74, 75 and
        D2R's own 76-79 use the text as a printf format (strings_ns.SKILLDESC_FORMAT). A key tbl2json kept with D2R's text because the
        placeholders differ (D2R rewrote `StrSkill82` "Fire Duration: " as "Fire Duration: %d seconds") then shows its raw
        `%d` in an appending line: such a cell names the mod's text `<key>_mxl` instead, as itemstatcost does
        (median_stat_wording). Type 1 (mana cost) took its label from skilldesc's `str mana` in 1.13c; D2R dropped the column
        and reads text A, so a blank text A printed the dummy string 5382 ("FLYING POLAR BUFFALO ERROR44"): the line gets the
        row's own `str mana` key."""
        kept = (self.smap or {}).get("kept_alias", {})
        mh, mrows = idmap.read_tsv(NAMED / "skilldesc.txt")
        mana = {}
        if "str mana" in mh:
            for r in idmap.records(mrows):
                key = self.skilldesc_renames.get(r[0], r[0])
                mana[key] = r[mh.index("str mana")]
        counts = Counter()
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "skilldesc.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            for r in idmap.records(rows):
                for line, prefix, count in self.DESCLINE_GROUPS:
                    for i in range(1, count + 1):
                        if f"{line}{i}" not in h:
                            continue
                        kind = r[h.index(f"{line}{i}")]
                        if not kind.isdigit():
                            continue
                        ca = h.index(f"{prefix}texta{i}")
                        if kind == "1" and not r[ca] and mana.get(r[0]):
                            r[ca] = mana[r[0]]
                            counts["mana"] += 1
                        fmt = strings_ns.skilldesc_format(int(kind))
                        for slot, c in (("A", ca), ("B", h.index(f"{prefix}textb{i}"))):
                            if slot not in fmt and r[c] in kept:
                                r[c] = kept[r[c]]
                                counts["alias"] += 1
            write_tsv(p, h, rows)
        self.report.append(f"\nskill wording (skilldesc, both banks, bug #396): {counts['mana']} mana cost lines (type 1) given the row's "
                           f"`str mana`; {counts['alias']} text cells of appending line types name the mod's text (<key>_mxl)")

    def misc_spell_values(self) -> None:
        """Item use lines (misc spelldesc 2, bug #490): 1.13c drew spelldescstr, a space and the spelldesccalc value; D2R uses
        spelldescstr as the printf format of the value, so Median's "Right-click: Gold in Bank:" showed no amount. The cell
        names tbl2json's `<key>_val` (the text and " %d", strings_map value_alias) instead."""
        alias = (self.smap or {}).get("value_alias", {})
        moved = []
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "misc.txt"
            if not p.exists() or not alias:
                continue
            h, rows = read_tsv(p)
            kind, key = h.index("spelldesc"), h.index("spelldescstr")
            for r in rows:
                if is_record(r) and r[kind] in strings_ns.SPELLDESC_VALUE_KINDS and r[key] in alias:
                    r[key] = alias[r[key]]
                    if bank == "base":
                        moved.append(r[h.index("code")])
            write_tsv(p, h, rows)
        self.report.append(f"\nitem use lines (misc spelldesc 2, bug #490): {len(moved)} rows name `<key>_val`: " + (", ".join(moved) or "none"))

    def stat_format_keys(self) -> None:
        """Descfunc 27 / 28 rows with no description text get D2R's format key (FORMAT_KEY_FUNCS, bug #140)."""
        filled = []
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "itemstatcost.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            fn, pos, neg = h.index("descfunc"), h.index("descstrpos"), h.index("descstrneg")
            for r in rows:
                key = FORMAT_KEY_FUNCS.get(r[fn]) if is_record(r) else None
                if key is None:
                    continue
                for c in (pos, neg):
                    if not r[c]:
                        r[c] = key
                        if bank == "base":
                            filled.append(f"{r[0]} {h[c]}")
            write_tsv(p, h, rows)
        self.report.append(f"\nstat format keys (descfunc 27 / 28, D2R reads the format from descstrpos): {len(filled)} cells: "
                           + (", ".join(filled) or "none"))

    def namespace_cells(self) -> None:
        """Last pass: every localization cell of both banks that names a mod-only (group 2) key is written through
        strings_ns.cell_value (`mxl2012:<key>`, the short alias where the field is too small); references to unique / set item
        names (cubemain input / output, treasureclassex Item#) follow the index cells (strings_ns.qualify_reference).
        Cells that name a D2R key stay unqualified (= `d2r:`). Needs work/mod/strings_map.json."""
        if not self.smap:
            self.report.append("\nlocalization cells: NOT qualified (work/mod/strings_map.json missing)")
            return
        group2, aliases = self.smap["group2"], self.smap["aliases"]
        self.prefixed: Counter = Counter()
        self.retargeted: Counter = Counter()
        files = [(bank, p) for bank in ("base", "") for p in sorted((OUT / "data" / "global" / "excel" / bank).glob("*.txt"))]
        item_names: set[str] = set()
        for _bank, path in files:
            if path.stem not in ("uniqueitems", "setitems"):
                continue
            lines = path.read_bytes().decode("utf-8").split("\r\n")
            ci = lines[0].split("\t").index("index")
            item_names |= {c[ci] for c in (l.split("\t") for l in lines[1:]) if ci < len(c) and c[ci] in group2}
        for bank, path in files:
            table = path.stem
            lines = path.read_bytes().decode("utf-8").split("\r\n")
            header = lines[0].split("\t")
            cols = {i for i, c in enumerate(header) if table in strings_ns.LOCALIZATION and strings_ns.is_localization(table, c)
                    and not strings_ns.is_range_column(table, c)}
            refs = {i for i, c in enumerate(header) if strings_ns.is_reference(table, c)}
            changed = False
            for n in range(1, len(lines)):
                if not cols and not refs:
                    break
                cells = lines[n].split("\t")
                if cells[0] == "Expansion":
                    continue
                for i, cell in enumerate(cells):
                    if i in cols and cell:
                        new = strings_ns.cell_value(table, header[i], cell, group2, aliases)
                    elif i in refs and cell:
                        new = strings_ns.qualify_reference(cell, item_names, aliases)
                    else:
                        continue
                    if new != cell:
                        cells[i] = new
                        (self.prefixed if i in cols else self.retargeted)[(bank or "rotw", table, header[i])] += 1
                        changed = True
                lines[n] = "\t".join(cells)
            if changed:
                path.write_text("\r\n".join(lines), encoding="utf-8", newline="")

    _schema = None
    _median_values: dict[tuple[str, str], set[str]] = {}
    _int_cols: dict[str, set[str]] = {}


    def clean_treasure_classes(self) -> None:
        """Treasure class entries must name an item code, item type, treasure class, unique or set item (D2R's
        format). Case-only mismatches are fixed; anything else (Median's sacred auto classes "sarm93"/"swea93",
        which D2Sigma generates, or names that exist nowhere) is cleared with its Prob and reported, because D2R
        asserts on it at load."""
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            p = d / "treasureclassex.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            known: dict[str, str] = {}
            for t, c in (("weapons", "code"), ("armor", "code"), ("misc", "code"), ("itemtypes", "Code"),
                         ("treasureclassex", "Treasure Class"), ("uniqueitems", "index"), ("setitems", "index")):
                if (d / f"{t}.txt").exists():
                    th, trows = read_tsv(d / f"{t}.txt")
                    if c in th:
                        known.update({r[th.index(c)].lower(): r[th.index(c)] for r in trows if r[th.index(c)]})
            auto = re.compile(r"^(weap|armo|mele|bow|mag[a-z]*|rar[a-z]*)\d+$")
            cleared = []
            for ci, c in enumerate(h):
                m = re.fullmatch(r"Item(\d+)", c)
                if not m:
                    continue
                pi = h.index(f"Prob{m.group(1)}") if f"Prob{m.group(1)}" in h else None
                for r in rows:
                    v = r[ci]
                    quoted = len(v) > 1 and v[0] == v[-1] == '"'
                    body = v[1:-1] if quoted else v
                    name, sep, rest = body.partition(",")
                    if not name or auto.match(name) or name in known.values():
                        continue
                    if name.lower() in known:  # case-only difference
                        body = known[name.lower()] + sep + rest
                        r[ci] = f'"{body}"' if quoted else body
                        continue
                    cleared.append(f"{r[0]}: {name}")
                    r[ci] = ""
                    if pi is not None:
                        r[pi] = ""
            # D2R resolves a treasure class's items against the classes above it only, so a class that names one
            # defined further down asserts ("Couldn't parse treasure class item"). Move each such class up to just
            # before its first user (D2R references classes by name, so the row shift is harmless).
            items = [i for i, c in enumerate(h) if re.fullmatch(r"Item\d+", c)]
            moved = []
            for _ in range(len(rows)):
                pos = {r[0]: i for i, r in enumerate(rows) if r[0] and r[0] != "Expansion"}
                fwd = next(((i, pos[r[c]]) for i, r in enumerate(rows) for c in items
                            if r[c] in pos and pos[r[c]] > i), None)
                if not fwd:
                    break
                user, target = fwd
                moved.append(f"{rows[target][0]} (before {rows[user][0]})")
                rows.insert(user, rows.pop(target))
            write_tsv(p, h, rows)
            if bank == "base" and moved:
                self.report.append(f"\ntreasureclassex: moved {len(moved)} classes above their first user "
                                   f"(D2R only resolves backward references): {'; '.join(moved)}")
            if bank == "base" and cleared:
                self.report.append(f"\ntreasureclassex: cleared {len(cleared)} entries D2R cannot resolve "
                                   f"(D2Sigma-generated classes or missing names): {'; '.join(cleared)}")

    def claim_presets(self) -> None:
        """A level with DrlgType 2 (preset) needs a lvlprest row whose LevelId names it. 1.10 fell back to preset 0
        ("None") when none did, and Median relies on that for levels it no longer uses; D2R asserts and crashes
        building the act. Each such level gets a copy of the "None" row that claims it."""
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "levels.txt").exists() or not (d / "lvlprest.txt").exists():
                continue
            lh, lrows = read_tsv(d / "levels.txt")
            ph, prows = read_tsv(d / "lvlprest.txt")
            li, di = ph.index("LevelId"), ph.index("Def")
            claimed = {r[li] for r in prows if is_record(r)}
            idc, dt = lh.index("Id"), lh.index("DrlgType")
            unclaimed = [r[idc] for r in lrows if is_record(r) and r[dt] == "2" and r[idc] not in claimed]
            none = next(r for r in prows if is_record(r))
            n = sum(1 for r in prows if is_record(r))
            for k, lid in enumerate(unclaimed):
                row = list(none)
                row[0], row[di], row[li] = f"mxl_unclaimed_{lid}", str(n + k), lid
                prows.append(row)
            write_tsv(d / "lvlprest.txt", ph, prows)
            if bank == "base" and unclaimed:
                self.report.append(f"\nlvlprest: {len(unclaimed)} preset levels had no preset (1.10 used preset 0); "
                                   f"added 'None' copies claiming levels {', '.join(unclaimed)}")

    def claim_mazes(self) -> None:
        """A level with DrlgType 1 (maze) needs a lvlmaze row. Median leaves a few without one (D2Sigma or unused
        levels); D2R sizes every level of an act when the act loads and asserts, then crashes, on them. Each gets
        a copy of the lvlmaze row of a level with the same LevelType (else the first row)."""
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "levels.txt").exists() or not (d / "lvlmaze.txt").exists():
                continue
            lh, lrows = read_tsv(d / "levels.txt")
            mh, mrows = read_tsv(d / "lvlmaze.txt")
            mi = mh.index("Level")
            have = {r[mi] for r in mrows if is_record(r)}
            idc, dt, ti = lh.index("Id"), lh.index("DrlgType"), lh.index("LevelType")
            ltype = {r[idc]: r[ti] for r in lrows if is_record(r)}
            missing = [r[idc] for r in lrows if is_record(r) and r[dt] == "1" and r[idc] not in have]
            records = [r for r in mrows if is_record(r)]
            for lid in missing:
                src = next((r for r in records if ltype.get(r[mi]) == ltype[lid]), records[0])
                row = list(src)
                row[0], row[mi] = f"mxl_unclaimed_{lid}", lid
                mrows.append(row)
            write_tsv(d / "lvlmaze.txt", mh, mrows)
            if bank == "base" and missing:
                self.report.append(f"\nlvlmaze: {len(missing)} maze levels had no lvlmaze row; added copies of a "
                                   f"same-LevelType row for levels {', '.join(missing)}")

    def fix_maze_positions(self) -> None:
        """Levels.txt `Position` (level record +0x90, bug #27): when set, the level entry finder 0x3da650 picks the
        arrival spot from a table of entry rooms the maze generator fills for the level (a random room of the requested
        type, 0x3dac20). D2R's own mazes that set it (54, 74, 125-127) have such rooms in their presets; with none the
        table is empty, the spot is (0, 0), no room is there and the next call (0x3289a0) reads +0x50 of null: the
        process dies on `cheat goto 184` (Maggot Lair, Median sets Position on it, the vanilla lair levels 62-64 do not).
        A maze level D2R does not have itself gets Position cleared; the arrival spot then comes from the level's
        warp tile as in every other maze."""
        n = 0
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            dr = D2R / bank / "levels.txt"
            if not (d / "levels.txt").exists() or not dr.exists():
                continue
            lh, lrows = read_tsv(d / "levels.txt")
            dh, drows = read_tsv(dr)
            pi, lid, dt = lh.index("Position"), lh.index("Id"), lh.index("DrlgType")
            d2r_ids = {r[dh.index("Id")] for r in drows if is_record(r)}
            n = 0
            for r in lrows:
                if is_record(r) and r[dt] == "1" and r[pi] == "1" and r[lid] not in d2r_ids:
                    r[pi] = ""
                    n += 1
            write_tsv(d / "levels.txt", lh, lrows)
        self.report.append(f"\nlevels: {n} Median-only maze levels had Position set (no entry room in the maze, the "
                           f"game dies on arrival); cleared")

    def level_entries(self) -> None:
        """Levels.txt `LevelEntry` (bug #120): D2R shows the key's text as the red "Entering ..." banner on every arrival in a
        level, and a blank cell reads "Missing string" (the Rogue Encampment on game start). 1.13c has no such column (its
        EntryFile is not mapped), so the merge left it blank on every Median row. A level whose LevelName is the one D2R's
        row of the same Id has gets D2R's key (EnteringTheRogueEncampment); any other named level gets its LevelName key (the
        banner then reads the area name; namespace_cells qualifies it like the name)."""
        counts = Counter()
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            dr = D2R / bank / "levels.txt"
            if not (d / "levels.txt").exists():
                continue
            lh, lrows = read_tsv(d / "levels.txt")
            if "LevelEntry" not in lh or "LevelName" not in lh:
                continue
            d2r = {}
            if dr.exists():
                dh, drows = read_tsv(dr)
                if {"Id", "LevelName", "LevelEntry"} <= set(dh):
                    d2r = {r[dh.index("Id")]: (r[dh.index("LevelName")], r[dh.index("LevelEntry")]) for r in drows if is_record(r)}
            ni, ei, ii = lh.index("LevelName"), lh.index("LevelEntry"), lh.index("Id")
            for r in lrows:
                if not is_record(r) or not r[ni].strip() or r[ei].strip():
                    continue
                name, entry = d2r.get(r[ii], ("", ""))
                if entry and name.lower() == r[ni].lower():
                    r[ei] = entry
                    counts["D2R's key"] += 1
                else:
                    r[ei] = r[ni]
                    counts["the level's name"] += 1
            write_tsv(d / "levels.txt", lh, lrows)
        self.report.append("\nlevels: blank LevelEntry (the 'Entering ...' banner, else 'Missing string') filled in both banks: "
                           + (", ".join(f"{n} with {k}" for k, n in sorted(counts.items())) or "none blank"))




    def sound_rows(self) -> None:
        """Median's own sound rows (appended after D2R's: sounds is d2r_wins) come from 1.13c's format and miss D2R's
        audio columns: no Channel, no HD Redirect, no Volume Min/Max (1.13c had one Volume, dropped as obsolete) and
        a .wav name where D2R's files are .flac. Rows that reuse a vanilla file (Whirlpool's "distilledwater" plays
        object\\sewerwater) copy those columns from the D2R row playing the same file, so they get its HD sound;
        Median's Volume becomes Volume Min/Max. Rows with Median's own audio (taunts etc.) get the channel D2R uses
        for that folder and a .flac name: they stay silent until the audio itself is ported."""
        mh_src, mrows_src = read_tsv(NAMED / "sounds.txt")
        volume = {r[0]: r[mh_src.index("Volume")] for r in mrows_src if r and r[0]}
        copied = custom = 0
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "sounds.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            dh, drows = read_tsv(D2R / bank / "sounds.txt")
            vanilla = {r[dh.index("Sound")] for r in drows if r}
            stem = lambda f: f.lower().replace("/", "\\").rsplit(".", 1)[0]
            by_file: dict[str, list[str]] = {}
            channel_of: dict[str, Counter] = defaultdict(Counter)
            for r in drows:
                if not r or not r[dh.index("FileName")]:
                    continue
                f = stem(r[dh.index("FileName")])
                by_file.setdefault(f, r)
                if r[dh.index("Channel")].endswith("_sd"):
                    channel_of[f.split("\\")[0]][r[dh.index("Channel")]] += 1
            audio = ["Redirect", "Channel", "FileName", "IsLocal", "IsMusic", "IsAmbientScene", "IsAmbientEvent",
                     "IsUI", "Pitch Min", "Pitch Max", "LFEMix", "3dSpread", "Is2D", "HDOptOut", "Delay"]
            for r in rows:
                name = r[h.index("Sound")]
                if not name or name in vanilla:
                    continue
                f = stem(r[h.index("FileName")])
                twin = by_file.get(f)
                if twin is not None:
                    for c in audio:
                        r[h.index(c)] = twin[dh.index(c)]
                    copied += bank == "base"
                else:
                    top = f.split("\\")[0]
                    if channel_of[top]:
                        r[h.index("Channel")] = channel_of[top].most_common(1)[0][0]
                    if r[h.index("FileName")]:
                        r[h.index("FileName")] = r[h.index("FileName")].rsplit(".", 1)[0] + ".flac"
                    for c, v in (("Pitch Min", "100"), ("Pitch Max", "100"), ("3dSpread", "60")):
                        if not r[h.index(c)]:
                            r[h.index(c)] = v
                    custom += bank == "base"
                v = volume.get(name, "")
                if v:
                    r[h.index("Volume Min")] = r[h.index("Volume Max")] = v
            write_tsv(p, h, rows)
        self.report.append(f"\nsounds: {copied} Median rows took a vanilla file's D2R audio columns, "
                           f"{custom} play Median's own audio (silent until it is ported)")

    def fill_skilldesc(self) -> None:
        """D2R asserts when a class skill has no skilldesc (Median's hidden class skills, granted at character
        creation, have none). They point at the "attack" description, which has no skill tree page."""
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "skills.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            cc, sd = h.index("charclass"), h.index("skilldesc")
            filled = [r[0] for r in rows if is_record(r) and r[cc] and not r[sd]]
            for r in rows:
                if is_record(r) and r[cc] and not r[sd]:
                    r[sd] = "attack"
            write_tsv(p, h, rows)
            if bank == "base" and filled:
                self.report.append(f"\nskills: {len(filled)} class skills had no skilldesc; set to 'attack'")

    BLANK_SKILLDESC = "mxl_blank"

    def blank_item_skilldesc(self) -> None:
        """docs/crash-audit.md C11: the client reads the skilldesc row of a skill an item tooltip names
        (oskill, charges, chance to cast, aura) and asserts `nDesc >= 0 && nDesc < skillDescTbl.size()` (D2Common
        CmnAccess.h:1092) for a skill without one. 1.13c printed an empty name. A skill an item property names that has no
        skilldesc gets the row `mxl_blank` (no name, no icon cel, no tree page), so the tooltip prints the same empty name
        without the assert. Skills that only monsters cast (monprop) are left alone (an assert once per cast, harmless)."""
        named: set[str] = set()
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            sp, dp = d / "skills.txt", d / "skilldesc.txt"
            if not (sp.exists() and dp.exists() and (d / "properties.txt").exists() and (d / "itemstatcost.txt").exists()):
                continue
            kinds = idmap.param_kinds(read_tsv(d / "properties.txt"), read_tsv(d / "itemstatcost.txt"))
            skill_codes = {c for c, (k, _st) in kinds.items() if k == "skill"}
            params: set[str] = set()
            for table in PROPERTY_TABLES:
                if table == "monprop" or not (d / f"{table}.txt").exists():
                    continue
                th, trows = read_tsv(d / f"{table}.txt")
                for code, par, _lo, _hi in idmap.property_columns(th):
                    if par is None:
                        continue
                    params |= {r[par].strip().lower() for r in idmap.records(trows)
                               if r[code].lower() in skill_codes and r[par].strip()}
            h, rows = read_tsv(sp)
            sid, sd = idmap.col(h, "*Id"), h.index("skilldesc")
            todo = [r for n, r in enumerate(idmap.records(rows)) if not r[sd] and
                    (r[0].lower() in params or (r[sid] if sid is not None else str(n)) in params)]
            if not todo:
                continue
            for r in todo:
                r[sd] = self.BLANK_SKILLDESC
                if bank == "base":
                    named.add(r[0])
            write_tsv(sp, h, rows)
            dh, drows = read_tsv(dp)
            if not any(r and r[0] == self.BLANK_SKILLDESC for r in drows):
                new = [""] * len(dh)
                new[0] = self.BLANK_SKILLDESC  # IconCel blank (= 0): the row is never drawn as a skill button
                if "*eol" in dh:
                    new[dh.index("*eol")] = "0"
                drows.append(new)
                write_tsv(dp, dh, drows)
        self.report.append(f"\nskills: {len(named)} skills named by item properties had no skilldesc (crash-audit C11, nDesc "
                           f"assert); set to '{self.BLANK_SKILLDESC}' (empty name): {', '.join(sorted(named)) or 'none'}")

    # Which strings D2R's skill description line types read (D2Client UI/SkillDesc.cpp, 0x287a50, a switch on the
    # line type that asserts "stringIndex1 != strdummy [&& stringIndex2 != strdummy]" when one is missing).
    DESCLINE_NEEDS = {2: "AB", 3: "AB", 4: "A", 5: "A", 6: "A", 7: "A", 12: "A", 13: "A", 15: "AB", 17: "A",
                      18: "A", 19: "A", 20: "AB", 21: "AB", 23: "A", 24: "A", 25: "A", 30: "A", 31: "A", 32: "AB",
                      33: "AB", 34: "A", 35: "A", 37: "A", 38: "AB", 40: "AB", 41: "A", 42: "A", 46: "AB", 47: "A",
                      49: "A", 50: "A", 51: "A", 53: "A", 54: "A", 55: "A", 56: "A", 57: "A", 58: "AB", 59: "A",
                      62: "AB", 63: "A", 64: "A", 65: "AB", 69: "A", 70: "AB", 71: "AB", 72: "A", 73: "A", 74: "A",
                      76: "AB", 77: "AB", 78: "A", 79: "AB"}
    DESCLINE_GROUPS = (("descline", "desc", 6), ("dsc2line", "dsc2", 5), ("dsc3line", "dsc3", 7))

    def skilldesc_lines(self) -> None:
        """docs/crash-audit.md C1: D2R's skill tooltip renderer asserts `stringIndex1 != strdummy` when a
        line type's text A / B is missing. 1.13c hard-coded the text of some types (13 "Life: %d", 34 "Damage: %d-%d",
        41 "Fire Damage: %d-%d"); D2R moved it into text A, and Median's rows leave it blank (Valkyrie, Raise Skeleton, the
        golems, ...). A line missing a string its type needs takes the text D2R's own rows use for that type when they all use
        the same one; otherwise (a Median data slip such as Lion Stance's type 7 without text) the line is dropped."""
        filled = dropped = 0
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "skilldesc.txt"
            dp = D2R / bank / "skilldesc.txt"
            if not p.exists():
                continue
            fixed_text: dict[int, tuple[str, str]] = {}
            if dp.exists():
                dh, drows = read_tsv(dp)
                seen: dict[int, set[tuple[str, str]]] = defaultdict(set)
                for r in idmap.records(drows):
                    for line, prefix, count in self.DESCLINE_GROUPS:
                        for i in range(1, count + 1):
                            if f"{line}{i}" in dh and r[dh.index(f"{line}{i}")].isdigit():
                                seen[int(r[dh.index(f"{line}{i}")])].add(
                                    (r[dh.index(f"{prefix}texta{i}")], r[dh.index(f"{prefix}textb{i}")]))
                fixed_text = {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}
            h, rows = read_tsv(p)
            n_fill = n_drop = 0
            for r in idmap.records(rows):
                for line, prefix, count in self.DESCLINE_GROUPS:
                    for i in range(1, count + 1):
                        if f"{line}{i}" not in h:
                            continue
                        cols = [h.index(c) for c in (f"{line}{i}", f"{prefix}texta{i}", f"{prefix}textb{i}",
                                                     f"{prefix}calca{i}", f"{prefix}calcb{i}")]
                        kind, a, b = r[cols[0]], r[cols[1]], r[cols[2]]
                        if not kind.isdigit():
                            continue
                        needs = self.DESCLINE_NEEDS.get(int(kind), "")
                        if not (("A" in needs and not a) or ("B" in needs and not b)):
                            continue
                        ta, tb = fixed_text.get(int(kind), ("", ""))
                        a, b = a or ta, b or tb
                        if ("A" in needs and not a) or ("B" in needs and not b):
                            for c in cols:
                                r[c] = ""
                            n_drop += 1
                        else:
                            r[cols[1]], r[cols[2]] = a, b
                            n_fill += 1
            write_tsv(p, h, rows)
            if bank == "base":
                filled, dropped = n_fill, n_drop
        self.report.append(f"\nskilldesc (D2R line types, crash-audit C1): {filled} lines given the text D2R's own rows use for "
                           f"their type (1.13c hard-coded it); {dropped} lines D2R can't draw dropped")

    def raven_counts(self) -> None:
        """Bug #390: the Raven AI (monai Raven) gives its unit a hit counter
        when it first thinks and kills the unit when the counter is 0 (each attack takes one off). The counter comes from the
        unit's monstats Skill1 at the unit's level of it: 1.13c reads Param1 + (lvl - 1) * Param2 of that skill, D2R evaluates
        its calc3. Median's companions on that AI (Wolf Companion -> companion, SorcFamiliar -> devilcat) have Param1 -2 and no
        calc3: in Median the counter starts at -2 and never reaches 0 (a permanent pet), in D2R it was 0 and the pet died on
        its first think. Those skills get calc3 ln12 (par1 + (lvl - 1) * par2). A skill without params keeps its empty calc3
        (0 either way); one with a calc3 of its own is left alone and reported."""
        mh, mrows = read_tsv(NAMED / "monstats.txt")
        ai, s1 = mh.index("AI"), mh.index("Skill1")
        skills = {r[s1] for r in mrows if is_record(r) and len(r) > s1 and r[ai] == "Raven" and r[s1]}
        written, kept = [], []
        for bank in ("base", ""):
            p = OUT / "data" / "global" / "excel" / bank / "skills.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            c3, p1, p2 = h.index("calc3"), h.index("Param1"), h.index("Param2")
            for r in rows:
                if not is_record(r) or r[0] not in skills or not (r[p1].strip() or r[p2].strip()):
                    continue
                if r[c3].strip():
                    kept.append(f"{r[0]} ({r[c3]})")
                    continue
                r[c3] = "ln12"
                written.append(r[0])
            write_tsv(p, h, rows)
        self.report.append(f"\nraven counters: calc3 ln12 (Median's par1 + (lvl-1) * par2 hit counter) on "
                           f"{', '.join(sorted(set(written))) or 'none'}; own calc3 kept: {', '.join(sorted(set(kept))) or 'none'}")

    def hireling_skilldesc(self) -> None:
        """D2R's hireling panel draws the mercenary's skills (1.13c's panel shows none) and asserts on a skill without a skilldesc
        (HirelingInventoryPanel.cpp:890 `skillDesc`, CmnAccess.h:1092 `nDesc`; lane mercs2). Nine of v005's 49 hireling skills
        have none. Each takes the description of the skill it is a copy of (hireling_desc_source), else "attack" as fill_skilldesc
        does for class skills. Display only: the skill rows' behaviour is unchanged."""
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "skills.txt").exists() or not (d / "hireling.txt").exists():
                continue
            h, rows = read_tsv(d / "skills.txt")
            hh, hrows = read_tsv(d / "hireling.txt")
            si, sd = h.index("skill"), h.index("skilldesc")
            used = {r[hh.index(f"Skill{n}")] for r in hrows for n in range(1, 7) if is_record(r) and r[hh.index(f"Skill{n}")]}
            desc = {r[si]: r[sd] for r in rows if is_record(r)}
            filled = []
            for r in rows:
                if is_record(r) and r[si] in used and not r[sd]:
                    r[sd] = hireling_desc_source(r[si], desc)
                    filled.append(f"{r[si]} -> {r[sd]}")
            write_tsv(d / "skills.txt", h, rows)
            if bank == "base" and filled:
                self.report.append(f"\nhireling skills without a skilldesc (D2R's hireling panel asserts): {'; '.join(filled)}")

    def split_large_sets(self) -> None:
        """D2R allows 6 items per set; Median's "Orphan's Call" has 9. Items 7+ go to a copy of the set named
        "<set> (2)" so the tables load; the full set needs a plugin (reported)."""
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "setitems.txt").exists():
                continue
            ih, irows = read_tsv(d / "setitems.txt")
            sh, srows = read_tsv(d / "sets.txt")
            si, key = ih.index("set"), sh.index("index")
            members: dict[str, list[list[str]]] = defaultdict(list)
            for r in irows:
                members[r[si]].append(r)
            for name, items in members.items():
                if len(items) <= MAX_ITEMS_PER_SET:
                    continue
                for n, start in enumerate(range(MAX_ITEMS_PER_SET, len(items), MAX_ITEMS_PER_SET), 2):
                    new = f"{name} ({n})"
                    for r in items[start:start + MAX_ITEMS_PER_SET]:
                        r[si] = new
                    base_row = next(r for r in srows if r[key] == name)
                    clone = list(base_row)
                    clone[key] = new
                    srows.append(clone)
                if bank == "base":
                    self.report.append(f"\nsets: '{name}' has {len(items)} items; D2R allows {MAX_ITEMS_PER_SET}. "
                                       f"Items 7+ moved to '{name} (2)' (needs a plugin for the real set bonus).")
            write_tsv(d / "setitems.txt", ih, irows)
            write_tsv(d / "sets.txt", sh, srows)

    def refs_into_replaced(self, table: str, dh: list[str]) -> dict[str, tuple[str, str]]:
        """D2R columns that are references (per D2R's data guide) into a table Median replaces wholesale:
        column -> (target table, target column)."""
        if Migrator._schema is None:
            import validate
            Migrator._schema = validate.Schema()
        out = {}
        for c in dh:
            f = Migrator._schema.field(table, c)
            typ = (f or {}).get("type", {})
            if isinstance(typ, dict) and typ.get("type") == "reference" and str(typ.get("file", "")).lower() in REPLACE:
                out[c] = (typ["file"].lower(), typ.get("field", ""))
        return out


    def drop_dangling(self, row: list[str], dh: list[str], dead_refs: dict, table: str, row_id: int) -> list[str]:
        """A row kept from D2R (e.g. RotW's Colossal monsters) may point into a table Median replaced; such
        references are emptied when Median's version has no such entry."""
        row = list(row)
        for c, (tfile, tcol) in dead_refs.items():
            v = row[dh.index(c)]
            if not v:
                continue
            key = (tfile, tcol)
            if key not in self._median_values:
                h, rows = read_tsv(NAMED / f"{tfile}.txt") if (NAMED / f"{tfile}.txt").exists() else ([], [])
                i = next((k for k, x in enumerate(h) if x.lower() == tcol.lower()), None)
                self._median_values[key] = {r[i].rstrip() for r in rows} if i is not None else set()
            if v not in self._median_values[key]:
                row[dh.index(c)] = ""
                self.dangling[table] += 1
        return row

    def typed_columns(self, table: str, dh: list[str]) -> tuple[set[str], set[str]]:
        """(string-key columns, boolean columns) per D2R's data guide."""
        self.refs_into_replaced(table, [])  # loads the schema
        strings, bools = set(), set()
        for c in dh:
            f = Migrator._schema.field(table, c)
            typ = (f or {}).get("type", {})
            kind = typ.get("type") if isinstance(typ, dict) else typ
            if kind == "string":
                strings.add(c)
            elif kind == "boolean":
                bools.add(c)
            elif kind == "int":
                self._int_cols.setdefault(table, set()).add(c)
        return strings, bools

    def column_map(self, table: str, mh: list[str], dh: list[str]) -> dict[str, str]:
        """D2R column -> Median column."""
        renames = {**RENAMES["*"], **RENAMES.get(table, {})}
        lower = {c.lower(): c for c in mh}
        out = {}
        for dc in dh:
            if dc in mh:
                out[dc] = dc
            elif dc.lower() in lower and not dc.startswith("*"):
                out[dc] = lower[dc.lower()]
        for mc, dc in renames.items():
            if mc in mh and dc in dh:
                out[dc] = mc
        for mc, dcs in SPLITS.get(table, {}).items():
            for dc in dcs:
                if mc in mh and dc in dh:
                    out[dc] = mc
        return out

    # Required links: a blank cell is an error too, so a dangling value stays (reported) instead of being emptied.
    REQUIRED_LINKS = {("monstats", "MonStatsEx")}
    # (table, column) -> value for cells D2R's enum list rejects (monstats2 BaseW 'pil' / 'lst' / 'cst' of six haunt_* monsters)
    ENUM_FALLBACK = {("monstats2", "BaseW"): "hth"}
    FORMULA_FUNCS = {"skill": ("skills", "skill"), "sksrc": ("skills", "skill"), "sklvl": ("skills", "skill"),
                     "miss": ("missiles", "Missile"), "stat": ("itemstatcost", "Stat")}

    @staticmethod
    def enum_values(schema, spec) -> set[str]:
        rule = (spec.get("d2rExcel") or {}).get("validation", {})
        owner = schema.enums[rule["foreignField"]] if rule.get("type") == "foreign" and rule.get("foreignField") in schema.enums else spec
        return schema.allowed(owner) or set()

    def cube_unresolved_inputs(self) -> None:
        """A cubemain input naming no item code, item type, unique or set item is an empty slot in 1.13c (Median's
        cubemain.bin keeps numinputs and leaves the slot zero); D2R passes an empty slot too (tools/cube_reference_audit.py).
        Such cells are emptied, so D2R gets 1.13c's record instead of a name it cannot resolve (bug #311)."""
        import cube_reference_audit as cra
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            if not (d / "cubemain.txt").exists():
                continue
            known: set[str] = set()
            for t, c in cra.TABLES:
                th, trows = read_tsv(d / f"{t}.txt")
                if c in th:
                    known.update(r[th.index(c)] for r in idmap.records(trows) if r[th.index(c)])
            h, rows = read_tsv(d / "cubemain.txt")
            recs = idmap.records(rows)
            found = cra.unresolved_inputs([dict(zip(h, r)) for r in recs], known)
            for n, col, name in found:
                recs[n - 1][h.index(col)] = ""
                if bank == "base":
                    self.report.append(f"\ncubemain: row {n} ({recs[n - 1][0]}) {col} '{name}' names nothing: emptied, "
                                       "as 1.13c compiles it (bug #311)")
            if found:
                write_tsv(d / "cubemain.txt", h, rows)

    def clean_references(self) -> None:
        """The mod's own data names things that do not exist (1.13c's compiler tolerates them, D2R's loader refuses the
        value or the formula): rows the mod repurposed and left in other tables (`coldpot` state, `Clay Golem` skill),
        typos, missing sounds / overlays / missiles. Per bank, over every table in work/mod:
          * a reference cell (D2R's data guide types it as a reference into another table) whose value differs from the
            target key only in case takes the target's spelling;
          * a reference to a row that does not exist is emptied (listed in work/mod/dangling_refs.tsv), except the required
            links (REQUIRED_LINKS), which are only listed;
          * formulas (formula_fix.fix): calls naming a missing skill / missile / stat become 0, case is corrected, negative
            literals / ternary branches / stray quotes are fixed for D2R's parser."""
        import formula_fix
        import validate
        if Migrator._schema is None:
            Migrator._schema = validate.Schema()
        schema = Migrator._schema
        listing: list[str] = []
        counts: Counter = Counter()
        for bank in ("base", ""):
            d = OUT / "data" / "global" / "excel" / bank
            tables = {p.stem: read_tsv(p) for p in sorted(d.glob("*.txt"))}

            def target(name: str, field: str, tables=tables, bank=bank):
                t = tables.get(name.lower())
                if t is None:
                    p = D2R / bank / f"{name.lower()}.txt"
                    t = read_tsv(p) if p.exists() else None
                if t is None:
                    return None
                h, rows = t
                i = next((k for k, c in enumerate(h) if c.lower() == field.lower()), None)
                if i is None:
                    return None
                return {r[i].lower(): r[i] for r in rows if len(r) > i and r[i]}

            cache: dict[tuple[str, str], dict[str, str] | None] = {}

            def values(name: str, field: str):
                if (name.lower(), field.lower()) not in cache:
                    cache[(name.lower(), field.lower())] = target(name, field)
                return cache[(name.lower(), field.lower())]

            def exists(func: str, name: str):
                vals = values(*self.FORMULA_FUNCS[func])
                return None if vals is None else vals.get(name.lower())

            # calc codes a formula may name, per scope (Item and Treasure Class formulas take no identifiers)
            calc_codes = {sc: {c.lower() for c in (values(t, "code") or {})}
                          for sc, t in (("Skill", "skillcalc"), ("Missile", "misscalc"), ("Monster", "moncalc"))}
            prop_codes = {c.lower() for t in ("properties", "propertygroups") for c in (values(t, "code") or {})}

            for table, (h, rows) in tables.items():
                if table not in schema.files:
                    continue
                refcols, fcols, propcols, enumcols = [], [], [], []
                for ci, c in enumerate(h):
                    if not c or c.startswith("*"):
                        continue
                    spec = schema.field(table, c)
                    typ = (spec or {}).get("type", {})
                    if isinstance(typ, dict) and typ.get("type") == "reference" and typ.get("file") and typ.get("file") != "Enums":
                        vals = values(typ["file"], typ.get("field") or "")
                        if vals:
                            refcols.append((ci, vals))
                    scope = schema.formula_scope(table, c)
                    if scope:
                        fcols.append((ci, scope))
                    if spec and "Properties#code" in str((spec.get("type") or {}).get("description", "")) + spec.get("description", ""):
                        propcols.append(ci)
                    if (table, c) in self.ENUM_FALLBACK:
                        enumcols.append((ci, self.enum_values(schema, spec), self.ENUM_FALLBACK[(table, c)]))
                changed = False
                for r in rows:
                    if not is_record(r):
                        continue
                    for ci, vals in refcols:
                        v = r[ci]
                        if not v or v in vals.values() or schema.field(table, h[ci]) is None:
                            continue
                        if table == "playerclass" or v == "SQ" and h[ci] in ("anim", "seqtrans"):
                            continue
                        if v.lower() in vals:
                            r[ci] = vals[v.lower()]
                            counts[(bank or "rotw", "case fixed")] += 1
                            changed = True
                        elif (table, h[ci]) in self.REQUIRED_LINKS:
                            first = next(iter(vals.values()))
                            if bank == "base":
                                listing.append(f"{table}\t{h[ci]}\t{r[0]}\t{v}\tset to the first row of the target table ({first}): required link")
                            counts[(bank or "rotw", "required link -> first row")] += 1
                            r[ci] = first
                            changed = True
                        else:
                            if bank == "base":
                                listing.append(f"{table}\t{h[ci]}\t{r[0]}\t{v}\temptied")
                            counts[(bank or "rotw", "emptied")] += 1
                            r[ci] = ""
                            changed = True
                    for ci in propcols:
                        if r[ci] and r[ci].lower() not in prop_codes:
                            if bank == "base":
                                listing.append(f"{table}	{h[ci]}	{r[0]}	{r[ci]}	emptied (no such property)")
                            counts[(bank or "rotw", "property code emptied")] += 1
                            r[ci] = ""
                            changed = True
                    for ci, allowed, fallback in enumcols:
                        if r[ci] and allowed and r[ci] not in allowed:
                            if bank == "base":
                                listing.append(f"{table}	{h[ci]}	{r[0]}	{r[ci]}	set to {fallback} (not in D2R's list)")
                            counts[(bank or "rotw", "enum value replaced")] += 1
                            r[ci] = fallback
                            changed = True
                    for ci, scope in fcols:
                        v = r[ci]
                        if not v:
                            continue
                        new, notes = formula_fix.fix(v, scope, exists, calc_codes.get(scope))
                        if new != v:
                            if bank == "base":
                                listing.append(f"{table}\t{h[ci]}\t{r[0]}\t{v[:120]}\tformula: {'; '.join(notes) or 'normalised'}")
                            for n in notes:
                                counts[(bank or "rotw", re.sub(r"'[^']*'", "'..'", n) if "no such row" not in n else "call to a missing row -> 0")] += 1
                            r[ci] = new
                            changed = True
                if changed:
                    write_tsv(d / f"{table}.txt", h, rows)
        (OUT / "dangling_refs.tsv").write_text("table\tcolumn\trow\tvalue\taction\n" + "\n".join(listing) + "\n", encoding="utf-8")
        self.report.append("\nreference clean-up (work/mod/dangling_refs.tsv): " +
                           ", ".join(f"{b} {k}: {n}" for (b, k), n in sorted(counts.items())))


# Name prefixes of v005's hireling copies of player / monster skills ("Female Vanquish", "Merc Glacial Nova", "Mon Hireling Tremor").
HIRELING_SKILL_PREFIXES = ("Female ", "Merc ", "Mon Hireling ", "Mon Super ", "Hireling ")


def hireling_desc_source(name: str, desc: dict[str, str]) -> str:
    """The skilldesc a hireling skill without one shows: that of the skill its name copies (prefix dropped, also as a "Mon "
    skill), else "attack"."""
    for pre in HIRELING_SKILL_PREFIXES:
        if name.startswith(pre):
            base = name[len(pre):]
            for cand in (base, "Mon " + base):
                if desc.get(cand):
                    return desc[cand]
    return "attack"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", action="append")
    args = ap.parse_args()
    localconfig.require_d2r_extract(D2R.parents[2], "txt_migrate")  # no extraction: every table would be skipped, the mod written empty
    m = Migrator()
    tables = args.table or sorted(p.stem for p in NAMED.glob("*.txt") if p.stem != "report")  # report.txt: a leftover of an older prep
    m.report += ["# txt-migrate report", "", "| Table | Kind | Mod rows | D2R rows | Output rows | Columns |",
                 "|---|---|---|---|---|---|"]
    for t in tables:
        m.migrate(t)
    m.split_large_sets()
    m.clean_treasure_classes()
    m.inventory_sizes()
    m.claim_presets()
    m.claim_mazes()
    m.fix_maze_positions()
    m.level_entries()
    m.sound_rows()
    m.clean_references()
    m.item_spell_states()
    m.state_colour_shifts()
    m.book_cursors()
    m.conversion_calcs()
    m.cube_unresolved_inputs()
    m.fill_skilldesc()
    m.blank_item_skilldesc()
    m.skilldesc_lines()
    m.raven_counts()
    m.hireling_skilldesc()
    m.shrine_strings()
    m.clear_unique_flags()
    m.carry_numbers()
    m.monprop_event_skills()
    m.hireling_level_difference()
    m.difficulty_code_rules()
    m.skill_rules()
    m.stat_send_bits()
    m.stat_save_add()
    m.missile_slot_report()
    m.missile_load()
    m.median_stat_wording()
    m.median_skill_wording()
    m.misc_spell_values()
    m.stat_format_keys()
    m.namespace_cells()
    m.report += ["", "## ID mapping (tools/idmap.py remap_table, applied to the mod's tables before the merge)", "",
                 "| Table | Cells rewritten |", "|---|---|"]
    for t, c in sorted(m.remapped.items()):
        m.report.append(f"| {t} | " + ", ".join(f"{k}: {n}" for k, n in sorted(c.items())) + " |")
    for bank, rep in sorted(m.type_report.items()):
        m.report.append(f"\nitemtypes ({bank}): " + "; ".join(f"{k}: {len(v)}" for k, v in sorted(rep.items())))
    m.report += ["", "## D2R-only columns left at the neutral default on rows that match a D2R row "
                 "(rows whose D2R value was not copied)", ""]
    for t, cols in sorted(m.left_out.items()):
        m.report.append(f"- {t}: " + ", ".join(f"{c} ({n})" for c, n in sorted(cols.items())))
    errors = []
    for bank_dir in (OUT / "data" / "global" / "excel" / "base", OUT / "data" / "global" / "excel"):
        errors += [f"{bank_dir.name}: {e}" for e in idmap.check_built(bank_dir, D2R)]
    m.report += ["", "## idmap.check_built (fixed item type ids)", ""] + ([f"- ERROR {e}" for e in errors] or ["- 0 errors"])
    if m.dangling:
        m.report += ["", "## References emptied in rows kept from D2R (target only existed in D2R's replaced tables)", ""]
        m.report += [f"- {t}: {n} cells" for t, n in sorted(m.dangling.items())]
    if m.smap:
        m.report += ["", "## Cells written as `mxl2012:<key>` (mod-only strings, docs/strings.md)", "",
                     "| Table | Column | rotw bank | base bank |", "|---|---|---|---|"]
        for t, c in sorted({(t, c) for (_b, t, c) in m.prefixed}):
            m.report.append(f"| {t} | {c} | {m.prefixed[('rotw', t, c)]} | {m.prefixed[('base', t, c)]} |")
        m.report += ["", "Reference cells (unique / set item names) written as `mxl2012:<key>`:", "",
                     "| Table | Column | rotw bank | base bank |", "|---|---|---|---|"]
        for t, c in sorted({(t, c) for (_b, t, c) in m.retargeted}):
            m.report.append(f"| {t} | {c} | {m.retargeted[('rotw', t, c)]} | {m.retargeted[('base', t, c)]} |")
    m.report += ["", "## Overflow: mod values with no D2R column (kept in work/mod/overflow/<table>.txt)", ""]
    for t, (cols, n) in sorted(m.overflow.items()):
        m.report.append(f"- **{t}** ({n} rows): " + ", ".join(f"{c} ({m.dropped[t][c]})" for c in cols))
    m.report += ["", "## Dropped as obsolete in D2R (non-empty counts)", ""]
    for t, cols in sorted(m.dropped.items()):
        obs = [c for c in cols if c not in m.overflow.get(t, ([], 0))[0]]
        if obs:
            m.report.append(f"- {t}: " + ", ".join(f"{c} ({cols[c]})" for c in obs))
    (OUT / "migrate_report.md").write_text("\n".join(m.report) + "\n", encoding="utf-8")
    print("\n".join(m.report))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
