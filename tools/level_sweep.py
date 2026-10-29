#!/usr/bin/env python
"""Level sweep: every levels.txt row of the built mod reached and walked by a strong but normal test character (docs/level-sweep.md).

    MXL_RUN=<lane> MXL_SLOT=3 MXL_RUNS=<R>\\mxl2012-runs py -3 tools/level_sweep.py run [--out DIR] [--difficulty normal|nightmare|hell]
                                     [--act N] [--only 1,5-9] [--redo ..] [--walk S] [--restart N] [--phases levels,waypoints,portals,tp,cow]
    py -3 tools/level_sweep.py plan [--csv FILE]        # the rows, their generator, entry routes and difficulties (no game)
    py -3 tools/level_sweep.py report --out DIR [--md docs/level-sweep.md]

`run` needs the slot lock (`game_slots.py lock N <lane>`; hold it only for one batch, e.g. one `--act`, and reinstall at each lock),
the built mod installed in that slot (`install_mod.py --slot N`) and
game_ctl's background input (the default; never MXL_INPUT=sendinput). It plays `Levelsweepbarb` (created when missing; Nightmare
and Hell are opened by the save's progression byte while the game is closed). The character is strong but normal: character level
120 with its stat points spent (strength, dexterity, the rest vitality) and the life and mana charstats gives that character; no
god mode, monsters deal their real damage. A death is counted, the character respawns in town and goes back to the level.

Phase `levels`, per level of the plan in the difficulty asked for (act order, the town of the act first when the act changes):
  1. `level <id>` (the waypoint warp's move inside an act, the NPC travel across acts; the warp is the reach, not the test);
     a level not reached in 40 s is `unreachable`;
  2. WALK for `--walk` seconds (default 30): background clicks on the ground 6-9 subtiles away; the character keeps a direction
     while it moves and turns when it is stuck, so rooms, presets, objects and natural monsters generate around it (a click on a
     monster is an attack, as for a player); explored = distinct 8 x 8 subtile cells stood on;
  3. the automap: a capture, Tab, a capture, Tab: the pixels the automap overlay changed (`automap_drawn`);
  4. a screenshot (outside git), the engine asserts / [ERROR] lines d2rloader.log got since the arrival, new crash reports, the
     size of the character's map memory files (`<char>.map`, `.ma0`-`.ma3`; D2R writes them when it saves).
A watchdog probes `state` around every step: a game that stops answering (hang) or a process that is gone (crash) is recorded for
the level, the process this run started is stopped (`game_ctl.stop`: this slot only, its shared files restored) and the sweep goes
on in a fresh launch. `--restart N` plays on in a fresh launch every N levels (default 30): many area changes in one launch
(the map memory must survive dozens) and the map memory files written at each exit.

Phase `waypoints` (Normal): every waypoint level, the way the waypoint panel travels: all waypoint numbers set, `level <id> warp 13`
(the waypoint travel's own arrival kind: next to the level's waypoint object), the waypoint object found next to the arrival
(objects.txt OperateFn 23) and its operate function run (the panel opens as for a click; screenshot once per act).
Phase `tp`: in one field level per act and in every Median special area, a Scroll of Town Portal right-clicked in the inventory as a
player does; the blue portal entered to town and the portal in town entered back.
Phase `cow`: the Cow Portal recipe (cubemain row 2, Wirt's Leg + Tome of Town Portal, Median 2012's only portal recipe) by cube
clicks in the Rogue Encampment, Baal's quest set as done in the difficulty (set-up), the new portal entered (phase_cow).
Phase `portals`: the permanent red portals (objects.txt class 60) of the levels that have them, entered with the portal's own use
function; and every other portal object the levels phase saw (the `state` lines print their destination).

Results go to <out>/sweep.json (resumable per difficulty: done levels are skipped). Evidence stays outside git
(mxl2012-runs/levels/).
"""
import argparse
import csv
import datetime
import json
import os
import random
import re
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLS)
import monster_sweep as ms  # noqa: E402  (pure helpers: d2rloader.log parsing, JSON, Hung / Gone)

ROOT = os.path.dirname(TOOLS)
EXCEL = os.path.join(ROOT, "work", "mod", "data", "global", "excel")
R_ROOT = os.path.dirname(os.path.dirname(ROOT))  # <R>/mxl2012-wt/<lane> -> <R>
DEFAULT_OUT = os.path.join(R_ROOT, "mxl2012-runs", "levels", "sweep")

CHAR_NAME = "Levelsweepbarb"
CHAR_CLASS = "barbarian"
CHAR_LEVEL = 120
EXP_120 = 7022000  # experience.txt row 119
TOWNS = {0: 1, 1: 40, 2: 75, 3: 103, 4: 109}  # act -> its town level
DIFFS = ("normal", "nightmare", "hell")
# The red portals D2R's permanent-portal init (objects.txt InitFn 12) opens by level, as 1.13c's: the source level -> the level it
# leads to. Median 2012 keeps these levels' rows and puts its own maps behind them (125 Toraja, 126 Fortress of Bone, 127 Zakarum).
PERMANENT_PORTALS = {111: 125, 112: 126, 117: 127, 109: 121}
# entries that are objects rather than level links (vanilla): the source level, the object class and what opens it
OBJECT_ENTRIES = {38: (4, "the Cairn Stones portal in the Stony Field (Deckard Cain's quest)"),
                  73: (66, "Duriel's tomb portal (objects.txt 100) after the Horadric Staff quest"),
                  74: (54, "the Arcane Sanctuary portal (objects.txt 298) in the Palace Cellar"),
                  103: (102, "the Hellgate (objects.txt 342) after Mephisto"),
                  132: (131, "Baal's portal (objects.txt 563) after Baal's minions"),
                  39: (1, "the Cow Portal: Wirt's Leg + Tome of Town Portal in the cube (cubemain), Baal killed in the difficulty")}
WAYPOINT_OPERATE = 23
SCREEN_CENTER = (800, 405)
SUB_PX = (27.0, 13.5)
# ground click offsets in subtiles (8 directions); the walk keeps one while the character moves
DIRS = [(11, 0), (8, 8), (0, 11), (-8, 8), (-11, 0), (-8, -8), (0, -11), (8, -8)]
CELL = 8  # explored cell size in subtiles
AUTOMAP_BOX = (400, 120, 1200, 720)  # where the automap overlay draws on the 1600 x 900 client
AUTOMAP_MIN = 400  # changed pixels in AUTOMAP_BOX that count as "the automap drew something" (a small explored cave: ~800)
# asserts that are explained elsewhere: message part -> note (they are counted, not listed as new)
KNOWN_ASSERTS = {"AssetCache.h": "D2R's asset cache growing by 50% (a warning; bugs.md #360)",
                 # logged once per launch, by the first goat priest that casts (it may stand in a neighbour level's room)
                 "wAuraState": "bugs.md #181: Mon Pain Spirit (goat priests) has srvdofunc 18 and no aurastate",
                 "nDirectionIndex < nDirections": "bugs.md #54 / #73: a srvdofunc-15 missile's direction index, masked right after the assert",
                 "biomeFilename": "a Median-only map without an HD scene json (docs/maps-hd.md)"}


# ---------------------------------------------------------------- the plan (pure)

# asserts D2R raises while a crashed process shuts down (after the assert that caused it)
TEARDOWN = {"object_pool.cpp", "CommandSystem.cpp"}


def num(s, default=None):
    try:
        return int(str(s).strip())
    except (TypeError, ValueError):
        return default


def read_levels(excel_dir=EXCEL):
    return ms.read_table(os.path.join(excel_dir, "levels.txt"))[1]


def mon_list(row, prefix):
    return [row.get("%smon%d" % (prefix, k), "").strip() for k in range(1, 26)]


def difficulties(row):
    """The difficulties a level is swept in: Normal always; Hell when its generation or population differs from Normal (the
    map size, the monster list Nightmare and Hell share, the density or the unique counts; the monster level always differs and
    does not count); Nightmare when it differs from Hell too (its own size, density or unique counts)."""
    def g(c):
        return (row.get(c) or "").strip()
    out = ["normal"]
    size_n = (g("SizeX"), g("SizeY"))
    nm = (g("SizeX(N)"), g("SizeY(N)"), g("MonDen(N)"), g("MonUMin(N)"), g("MonUMax(N)"))
    hell = (g("SizeX(H)"), g("SizeY(H)"), g("MonDen(H)"), g("MonUMin(H)"), g("MonUMax(H)"))
    norm = size_n + (g("MonDen"), g("MonUMin"), g("MonUMax"))
    if mon_list(row, "n") != mon_list(row, "") or hell != norm:
        out.append("hell")
    if nm != hell:
        out.insert(1, "nightmare")
    return out


def incoming_links(levels):
    """{level id: [(source id, 'vis')]}: the levels whose Vis columns lead into the level (the warp tiles a player walks through)."""
    out = {}
    for r in levels:
        src = num(r.get("Id"))
        if src is None:
            continue
        for k in range(8):
            v = num(r.get("Vis%d" % k), 0) or 0
            if v > 0:
                out.setdefault(v, []).append((src, "vis"))
    return out


def entry_routes(lid, row, links, waypoint_names, outdoor_prev=None):
    """How a player enters the level: ['waypoint', 'from 17 (warp tile)', 'red portal in 111', ...] ([] = no route in the data)."""
    out = []
    wp = num(row.get("Waypoint"), 255)
    if wp is not None and wp != 255 and lid not in NO_WAYPOINT_OBJECT:
        out.append("waypoint %d%s" % (wp, " (shared with %s)" % waypoint_names[wp] if waypoint_names.get(wp) else ""))
    for src, _ in links.get(lid, []):
        out.append("from %d (warp tile)" % src)
    for src, dst in PERMANENT_PORTALS.items():
        if dst == lid:
            out.append("red portal in %d" % src)
    if lid in OBJECT_ENTRIES:
        out.append(OBJECT_ENTRIES[lid][1])
    if lid in TOWNS.values():
        out.append("town (the act's start)")
    if num(row.get("DrlgType")) == 3 and outdoor_prev is not None:
        out.append("from %d (outdoor edge)" % outdoor_prev)
    return out


def lvltype_acts(excel_dir=EXCEL):
    """{LevelType id: act 0-4} from lvltypes.txt's names ('Act 2 - Desert 2'); {} when the table is missing."""
    path = os.path.join(excel_dir, "lvltypes.txt")
    if not os.path.exists(path):
        return {}
    out = {}
    for r in ms.read_table(path)[1]:
        m = re.match(r"Act (\d)", r.get("Name", ""))
        if m and num(r.get("Id")) is not None:
            out[num(r.get("Id"))] = int(m.group(1)) - 1
    return out


def plan_levels(excel_dir=EXCEL, levels=None, tile_acts=None):
    """Every levels.txt row with an Id above 0: what the sweep needs to know about it. tile_acts: {LevelType: act} (default: from
    lvltypes.txt when the levels come from the table too)."""
    if tile_acts is None:
        tile_acts = lvltype_acts(excel_dir) if levels is None else {}
    levels = read_levels(excel_dir) if levels is None else levels
    links = incoming_links(levels)
    by_wp = {}
    for r in levels:
        wp = num(r.get("Waypoint"), 255)
        if wp is not None and wp != 255:
            by_wp.setdefault(wp, []).append(r.get("Name", ""))
    out = []
    tile_act = tile_acts
    prev_outdoor = {}  # act -> the last outdoor level id: outdoor levels of an act meet at their edges (no Vis, no warp tile)
    for r in levels:
        lid = num(r.get("Id"))
        if not lid:
            continue
        act = num(r.get("Act"), 0)
        # an outdoor row drawn with another act's tiles meets no edge of this act (134 Pandemonium 2: act 5, Valley of the Kings tiles)
        own_tiles = tile_act.get(num(r.get("LevelType"), 0), act) == act
        outdoor_prev = prev_outdoor.get(act) if num(r.get("DrlgType")) == 3 and own_tiles else None
        if (num(r.get("DrlgType")) == 3 and own_tiles) or lid in TOWNS.values():  # a town's edge leads into the act's first outdoor level
            prev_outdoor[act] = lid
        wp = num(r.get("Waypoint"), 255)
        shared = {wp: ", ".join(n for n in by_wp.get(wp, []) if n != r.get("Name"))} if wp in by_wp else {}
        out.append({"id": lid, "name": r.get("Name", ""), "label": r.get("LevelName", ""), "act": num(r.get("Act"), 0),
                    "drlg": num(r.get("DrlgType"), 0), "ltype": num(r.get("LevelType"), 0), "waypoint": wp if wp != 255 else None,
                    "town": lid in TOWNS.values(), "no_tp": num(r.get("PreventTownPortal"), 0) == 1, "diffs": difficulties(r), "routes": entry_routes(lid, r, links, shared, outdoor_prev)})
    return out


def run_order(plan, difficulty):
    """The levels of a difficulty in act order (fewest act changes), level id order inside an act."""
    return sorted((p for p in plan if difficulty in p["diffs"]), key=lambda p: (p["act"], p["id"]))


def parse_id_list(text):
    return ms.parse_hc_list(text)


# ---------------------------------------------------------------- the character (pure)

def charstats_row(excel_dir=EXCEL, cls="Barbarian"):
    rows = ms.read_table(os.path.join(excel_dir, "charstats.txt"))[1]
    return next((r for r in rows if r.get("class", "").lower() == cls.lower()), None)


def normal_character(cs, level=CHAR_LEVEL):
    """A level-`level` character of the class as the game builds it: base stats + 5 points per level (StatPerLevel), strength 250 and
    dexterity 150 (or the base when higher), the rest in vitality; life and mana from charstats (values in 1/4: hpadd + base vitality
    life, LifePerLevel per level, LifePerVitality per added point; mana the same with energy). {stat id: whole points}."""
    def n(c, d=0):
        return num(cs.get(c), d)
    per_level = n("StatPerLevel", 5) or 5
    base = {"str": n("str"), "dex": n("dex"), "int": n("int"), "vit": n("vit")}
    points = base["str"] + base["dex"] + base["int"] + base["vit"] + per_level * (level - 1)
    st = max(base["str"], 250)
    dx = max(base["dex"], 150)
    en = base["int"]
    vit = points - st - dx - en
    life = base["vit"] + n("hpadd") + (n("LifePerLevel") * (level - 1) + n("LifePerVitality") * (vit - base["vit"])) // 4
    mana = base["int"] + (n("ManaPerLevel") * (level - 1)) // 4
    return {0: st, 1: en, 2: dx, 3: vit, 7: life, 6: life, 9: mana, 8: mana, 12: level}


# ---------------------------------------------------------------- walking / judging (pure)

def screen_frac(dx, dy, centre=SCREEN_CENTER, scale=SUB_PX):
    """Client fraction (1600 x 900) of a ground point dx / dy subtiles from the player."""
    return (centre[0] + scale[0] * (dx - dy)) / 1600.0, (centre[1] + scale[1] * (dx + dy)) / 900.0


def next_direction(d, moved, rng, stuck_min=2):
    """The walk's next direction index: keep it while the character moves (1 in 6 a small turn, to explore), turn by 2-5 when
    it is stuck (a wall, a door, a cliff)."""
    if moved < stuck_min:
        return (d + rng.choice((2, 3, 5))) % len(DIRS)
    if rng.random() < 1 / 6.0:
        return (d + rng.choice((1, -1))) % len(DIRS)
    return d


def cell_of(x, y, size=CELL):
    return (x // size, y // size)


def parse_player(lines):
    """`state`'s player line -> dict (area, x, y, life, mode, difficulty ...) or None."""
    for ln in lines:
        if ln.startswith("player "):
            d = {k: v for k, v in re.findall(r"(\w+)=(\S+)", ln)}
            out = {}
            for k, v in d.items():
                if re.fullmatch(r"-?\d+", v):
                    out[k] = int(v)
                elif re.fullmatch(r"-?\d+/-?\d+", v):
                    out[k] = int(v.split("/")[0])
                    out[k + "_max"] = int(v.split("/")[1])
            return out
    return None


def parse_portals(lines):
    """[(object id, class, destination level)] of `state`'s portal lines (classes 59 / 60 / 600 carry dest=)."""
    out = []
    for ln in lines:
        m = re.match(r"obj id=(\d+) class=(\d+) .*dest=(\d+)", ln.strip())
        if m:
            out.append(tuple(int(x) for x in m.groups()))
    return out


def parse_objects(lines):
    """[(object id, class, dist)] of `objects` answer lines."""
    out = []
    for ln in lines:
        m = re.match(r"object id=(\d+) class=(\d+) mode=-?\d+ dist=(\d+)", ln.strip())
        if m:
            out.append(tuple(int(x) for x in m.groups()))
    return out


def player_dead(p):
    return bool(p) and (p.get("mode") in (0, 17) or p.get("life", 1) == 0)


def automap_drawn(changed, minimum=AUTOMAP_MIN):
    return changed >= minimum


def automap_of(res):
    """True / False / None: judged from the stored pixel count (so a new threshold re-judges old runs), else the stored verdict."""
    if res.get("automap_px") is not None:
        if res.get("automap_dead") and not automap_drawn(res["automap_px"]):
            return None  # captured on a death screen: little explored, not judged
        return automap_drawn(res["automap_px"])
    return res.get("automap")


def known_assert(message):
    return next((note for part, note in KNOWN_ASSERTS.items() if part in message), None)


# ---------------------------------------------------------------- the report (pure)

def killed_on_arrival(res):
    """The level loads but its monsters kill the character at the entry again and again before it can walk (95 Disused Fane,
    132 World Stone with a normal character): such a level is judged on its load (reached, no hang / crash / new assert, the
    arrival screenshot and objects), not on the walk or the automap the dead character cannot draw."""
    return bool(res.get("reached")) and res.get("walked", 0) == 0 and res.get("deaths", 0) >= 2


def problem_keys(res):
    """What a level's result counts as a problem: [key]."""
    keys = []
    for k in ("hang", "crash"):
        if res.get(k):
            keys.append(k)
    if not res.get("reached") and not res.get("hang") and not res.get("crash"):
        keys.append("unreachable")
    for a in res.get("asserts", []):
        if res.get("crash") and a.get("location", "").split(":")[0] in TEARDOWN:
            continue  # the dying process's own clean-up, after the cause
        if not known_assert(a["message"]):
            keys.append("assert: %s (%s)" % (a["message"], a.get("location", "")))
    keys += ["log: " + e for e in res.get("errors", [])]
    if res.get("reached") and not res.get("hang") and not res.get("crash") and not killed_on_arrival(res):  # see summarize
        if res.get("walked", 0) == 0:
            keys.append("no-walk (the character never moved)")
        if automap_of(res) is False:
            keys.append("automap-empty")
    return keys


def summarize(plan, data):
    s = {"levels": len(plan), "visits_planned": sum(len(p["diffs"]) for p in plan), "visits": 0, "reached": 0, "hang": 0, "crash": 0,
         "assert_visits": 0, "deaths": 0, "automap_drawn": 0, "automap_empty": 0, "walked": 0, "problems": {}, "known": {}}
    names = {p["id"]: p for p in plan}
    for diff, rows in data.get("levels", {}).items():
        for lid, res in rows.items():
            if int(lid) not in names:
                continue
            s["visits"] += 1
            s["reached"] += 1 if res.get("reached") else 0
            s["hang"] += 1 if res.get("hang") else 0
            s["crash"] += 1 if res.get("crash") else 0
            s["assert_visits"] += 1 if res.get("asserts") else 0
            s["deaths"] += res.get("deaths", 0)
            s["walked"] += 1 if res.get("walked", 0) > 0 else 0
            if automap_of(res) is True:
                s["automap_drawn"] += 1
            elif automap_of(res) is False:
                s["automap_empty"] += 1
            if killed_on_arrival(res):
                note = "killed on arrival (judged on the level load: its monsters kill the character at the entry before it can walk)"
                s["known"][note] = s["known"].get(note, 0) + 1
            for a in res.get("asserts", []):
                note = known_assert(a["message"])
                if note:
                    s["known"][note] = s["known"].get(note, 0) + 1
            for k in problem_keys(res):
                s["problems"].setdefault(k, []).append("%s %s" % (diff[0].upper(), lid))
    return s


ROUTE_BUGS = {("tp", "134"): "bugs.md #392"}  # route rows whose failure is a filed bug


def tp_rejudge(r, prevented):
    """A tp row taken before the sweep knew PreventTownPortal: no portal in such a level is the right result."""
    if prevented and r.get("ok") is False and r.get("note") == "no portal after the scroll was used":
        return dict(r, ok=True, note=r["note"] + " (expected: PreventTownPortal is set)")
    return r


def portal_rejudge(r):
    """A red-portal search the level's monsters cut short (the character died twice or more while walking) is not judged: the
    portal's room may never have been reached. Also re-judges rows written before this rule (from their note)."""
    m = re.search(r"no red portal .* \((\d+) 8x8 cells, (\d+) deaths\)", r.get("note", ""))
    if r.get("ok") is False and m and int(m.group(2)) >= 2:
        return dict(r, ok=None, note="not judged: " + r["note"])
    return r


def route_verdict(r):
    """A route row's verdict: ok, FAIL, or not judged (ok None: the character died before the step could be judged)."""
    return {True: "ok", None: "not judged"}.get(r.get("ok"), "**FAIL**")


def md_cell(x):
    return ms.md_cell(x)


def render_report(plan, data):
    s = summarize(plan, data)
    names = {p["id"]: p for p in plan}
    L = ["# Level sweep", "",
         "Generated by `py -3 tools/level_sweep.py report` from the runs' `sweep.json` (evidence outside git: `mxl2012-runs/levels/`, `mxl2012-runs/levels2/`). "
         "How levels are reached and walked, what the columns mean and the limits: the docstring of `tools/level_sweep.py`.", "",
         "Runs: %s. Character `%s` (character level %d, stat points spent, life and mana as charstats gives them, no god mode); "
         "walk %s s per level; fresh launch every %s levels; mod build %s. Real input watchdog: %s" % (
             "; ".join("%s %s - %s" % (k, v.get("started", "-"), v.get("finished", "-")) for k, v in sorted(data.get("runs", {}).items())) or "-",
             CHAR_NAME, CHAR_LEVEL, data.get("walk", "-"), data.get("restart", "-"), data.get("build", "-"), data.get("watchdog", "-")), "",
         "## Summary", "", "| | Count |", "|---|---:|",
         "| levels.txt rows (Id above 0) | %d |" % s["levels"],
         "| visits planned (level x difficulty where the level's generation differs) | %d |" % s["visits_planned"],
         "| visits done | %d |" % s["visits"], "| reached | %d |" % s["reached"], "| walked (the character moved) | %d |" % s["walked"],
         "| automap drew | %d |" % s["automap_drawn"], "| automap drew nothing | %d |" % s["automap_empty"],
         "| hung the game | %d |" % s["hang"], "| crashed the game | %d |" % s["crash"],
         "| visits with an engine assert | %d |" % s["assert_visits"], "| deaths of the test character (respawned) | %d |" % s["deaths"], ""]
    if s["known"]:
        L += ["Known asserts (counted, not problems): " + "; ".join("%s x%d" % (k, v) for k, v in sorted(s["known"].items())) + ".", ""]
    L += ["## Problem clusters", "", "| Problem | Visits | Levels (N/M/H id) |", "|---|---:|---|"]
    if not s["problems"]:
        L.append("| none | 0 | |")
    for k, v in sorted(s["problems"].items(), key=lambda kv: (-len(kv[1]), kv[0])):
        L.append("| %s | %d | %s |" % (md_cell(k), len(v), md_cell(", ".join(v[:12]) + (" ..." if len(v) > 12 else ""))))
    L += ["", "## Levels", "",
          "`Gen`: DrlgType (1 maze, 2 preset, 3 outdoor) / LevelType. Per difficulty: reached in s / explored 8x8 cells / distinct "
          "monsters seen / automap (A drew, - nothing, ? not judged: captured on a death screen) / deaths; `K` killed on arrival (judged on the level load); `!` a problem (clusters above). `Routes`: how a player enters it.", "",
          "| Id | Level | Gen | Normal | Nightmare | Hell | Routes | Problems |", "|---:|---|---|---|---|---|---|---|"]
    for p in sorted(plan, key=lambda p: p["id"]):
        cells, probs = [], []
        for d in DIFFS:
            res = data.get("levels", {}).get(d, {}).get(str(p["id"]))
            if d not in p["diffs"]:
                cells.append("(as above)")
            elif res is None:
                cells.append("not run")
            else:
                keys = problem_keys(res)
                probs += ["%s: %s" % (d[0].upper(), k) for k in keys]
                if res.get("reached"):
                    cells.append("%s s / %d / %d / %s / %d%s%s" % (res.get("load_s", "?"), res.get("explored", 0), res.get("monsters", 0),
                                                              {True: "A", False: "-", None: "?"}[automap_of(res)], res.get("deaths", 0),
                                                              " K" if killed_on_arrival(res) else "", " !" if keys else ""))
                else:
                    cells.append("**%s**" % ("hang" if res.get("hang") else "crash" if res.get("crash") else "not reached"))
        L.append("| %d | %s (%s) | %d/%d | %s | %s | %s |" % (
            p["id"], md_cell(p["name"]), md_cell(p["label"]), p["drlg"], p["ltype"], " | ".join(cells),
            md_cell("; ".join(p["routes"]) or "none in the data"), md_cell("; ".join(probs))))
    for title, key in (("Waypoints", "waypoints"), ("Town portals", "tp"), ("Portals", "portals")):
        rows = data.get(key, {})
        if not rows:
            continue
        L += ["", "## %s" % title, "", "| Level | Result | Notes |", "|---:|---|---|"]
        for lid, r in sorted(rows.items(), key=lambda kv: (int(kv[0].split(":")[0]), kv[0])):
            if key == "tp":
                r = tp_rejudge(r, names.get(int(lid), {}).get("no_tp"))
            elif key == "portals":
                r = portal_rejudge(r)
            L.append("| %s %s | %s | %s |" % (lid, md_cell(names.get(int(lid.split(":")[0]), {}).get("name", "")),
                                             route_verdict(r), md_cell("; ".join(x for x in (r.get("note", ""), ROUTE_BUGS.get((key, lid))) if x))))
    if data.get("mapmem"):
        L += ["", "## Map memory files", "", "Sizes of `%s.map` / `.ma0`-`.ma3` (D2R's per-character explored-room memory) at each "
              "fresh launch: the sweep's many area changes must neither hang D2R nor grow them without bound." % CHAR_NAME, "",
              "| When | Levels visited before | Files (bytes) |", "|---|---:|---|"]
        for m in data["mapmem"]:
            L.append("| %s | %d | %s |" % (m["when"], m["visited"], md_cell(", ".join("%s %d" % kv for kv in sorted(m["files"].items())))))
    if data.get("notes"):
        L += ["", "## Notes of the runs", ""] + ["- " + md_cell(n) for n in data["notes"]]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- save patching (closed game)

def set_progression(path, difficulty="hell"):
    """Open Nightmare and Hell for the closed character (rc_setup: the v105 header's progression byte, the checksum and
    D2RLoader's `.d2rl` sidecar). True when the save was changed."""
    import rc_setup
    s = open(path, "rb").read()
    if rc_setup.set_progression(s, difficulty) == s:
        return False
    rc_setup.edit(os.path.dirname(path), os.path.splitext(os.path.basename(path))[0], lambda b: rc_setup.set_progression(b, difficulty))
    return True


# ---------------------------------------------------------------- the game session

class Session:
    def __init__(self, gc, out, data, plan, walk_s):
        self.gc, self.g, self.out, self.data, self.plan, self.walk_s = gc, gc.g, out, data, plan, walk_s
        self.byid = {p["id"]: p for p in plan}
        self.crash_seen = set(os.listdir(self.g.CRASH_DIR)) if os.path.isdir(self.g.CRASH_DIR) else set()
        self.visited = 0
        self.difficulty = None
        self.stats = normal_character(charstats_row() or {})
        os.makedirs(os.path.join(out, "shots"), exist_ok=True)

    # --- game life
    def alive(self):
        return bool(self.g.game_pids())

    def probe(self, tries=2, gap=5.0):
        for _ in range(tries):
            if not self.alive():  # game_ctl's console exits the program when no game runs: a crash is seen here first
                raise ms.Gone()
            ok, lines = self.g.hcmd("state", 10)
            if ok:
                return lines
            if not self.alive():
                raise ms.Gone()
            time.sleep(gap)
        raise ms.Hung()

    def player(self):
        return parse_player(self.probe()) or {}

    def mapmem(self):
        files = {}
        for ext in (".map", ".ma0", ".ma1", ".ma2", ".ma3"):
            p = os.path.join(self.g.SAVES, CHAR_NAME + ext)
            if os.path.exists(p):
                files[ext] = os.path.getsize(p)
        return files

    def start(self, difficulty):
        gc, g = self.gc, self.g
        self.data.setdefault("mapmem", []).append({"when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                   "visited": self.visited, "files": self.mapmem()})
        save = os.path.join(g.SAVES, CHAR_NAME + ".d2s")
        if difficulty != "normal" and os.path.exists(save) and not g.game_pids():
            if set_progression(save):
                g.log("level sweep: %s progression set (Nightmare and Hell open)" % CHAR_NAME)
        if not gc.to_menu():
            raise RuntimeError("game did not reach the main menu")
        card = gc.card_of(CHAR_NAME)
        if card is None:
            ok = gc.create_character(CHAR_CLASS, CHAR_NAME)
        else:
            g.click(0.87, 0.076 + 0.091 * (card - 1))
            time.sleep(0.8)
            ok = gc.play(difficulty)
        if not ok:
            raise RuntimeError("could not play %s in %s" % (CHAR_NAME, difficulty))
        gc.STATE["in_game"] = True
        gc.skip_cinematic()
        p = self.player()
        want = DIFFS.index(difficulty)
        if p.get("difficulty") != want:
            raise RuntimeError("playing %s in difficulty %s, not %s (%d)" % (CHAR_NAME, p.get("difficulty"), difficulty, want))
        self.difficulty = difficulty
        self.equip()
        self.log_mark = g._size(g.LOADER_LOG)

    def equip(self):
        """The character's normal stats (set every launch: the save keeps them, the set is idempotent)."""
        for sid, v in self.stats.items():
            self.gc.setstat("player", sid, v << 8 if sid in (6, 7, 8, 9) else v)
        self.gc.setstat("player", 13, EXP_120)

    def restart(self, why):
        self.save_log_tail(why)
        self.g.stop()
        time.sleep(3)
        self.start(self.difficulty)

    def save_log_tail(self, why):
        g = self.g
        tail = g._read_from(g.LOADER_LOG, getattr(self, "log_mark", 0)) or ""
        with open(os.path.join(self.out, "logtail-%s.log" % re.sub(r"\W+", "-", why)), "w", encoding="utf-8") as f:
            f.write(tail)
        return self.new_crashes()

    def new_crashes(self):
        g = self.g
        crashes = sorted(set(os.listdir(g.CRASH_DIR)) - self.crash_seen) if os.path.isdir(g.CRASH_DIR) else []
        for c in crashes:
            src = os.path.join(g.CRASH_DIR, c)
            if os.path.isfile(src):
                import shutil
                shutil.copy2(src, self.out)
        self.crash_seen |= set(crashes)
        return crashes

    # --- moving
    def travel(self, lid, warp_kind=None, timeout=40):
        """`level <id>` (`warp <kind>` when given) and wait for the area; the act's town first when the act changes. -> seconds or None."""
        p = self.player()
        if p.get("area") == lid:
            return 0.0
        row = self.byid.get(lid)
        here = self.byid.get(p.get("area"))
        if row and here and row["act"] != here["act"]:
            if row["town"]:
                warp_kind = None  # across acts only the NPC travel (a forced warp there ended the game, run n-routes)
            else:
                self.travel(TOWNS[row["act"]], timeout=timeout)
        t0 = time.time()
        self.g.hcmd("level %d%s" % (lid, " warp %d" % warp_kind if warp_kind is not None else ""), 10)
        time.sleep(2.5)  # no second travel while one loads
        while time.time() - t0 < timeout:
            p = self.player()
            if p.get("area") == lid:
                return round(time.time() - t0, 1)
            time.sleep(1.5)
        return None

    def ensure_alive(self):
        """Respawn a dead character (between steps of the route phases: a deadly level can kill it while a step waits)."""
        if player_dead(self.player()):
            self.gc.revive_if_dead()
            self.equip()
            return True
        return False

    def revive(self, lid, res):
        """A dead character: respawn (game_checks.revive_if_dead), normal stats back, return to the level."""
        res["deaths"] = res.get("deaths", 0) + 1
        self.gc.revive_if_dead()
        self.equip()
        if self.travel(lid) is None:
            res.setdefault("notes", []).append("not back in the level after a death")
            return False
        return True

    def walk(self, lid, seconds, res):
        rng = random.Random(lid * 7 + DIFFS.index(self.difficulty))
        d = rng.randrange(len(DIRS))
        cells, mons, objs, portals = set(), set(), set(), {}
        walked = 0
        t0 = time.time()
        lines = self.probe()
        while time.time() - t0 < seconds:
            self.gc.guard()
            p = parse_player(lines) or {}
            if player_dead(p):
                if not self.revive(lid, res):
                    break
                if res["deaths"] <= 2:  # the respawn and the way back do not count as walking time
                    t0 = time.time()
                lines = self.probe()
                continue
            if p.get("area") != lid:  # walked through a warp tile into the next level: back (counted)
                res["left_level"] = res.get("left_level", 0) + 1
                if self.travel(lid) is None:
                    break
                lines = self.probe()
                continue
            for m in ms.parse_units(lines).values():
                mons.add(m["class"])
            for ln in lines:
                mo = re.match(r"obj id=(\d+) class=(\d+)", ln)
                if mo:
                    objs.add(int(mo.group(1)))
            for oid, ocls, dest in parse_portals(lines):
                portals[oid] = [ocls, dest]
            x0, y0 = p.get("x", 0), p.get("y", 0)
            cells.add(cell_of(x0, y0))
            dx, dy = DIRS[d]
            self.g.click(*screen_frac(dx, dy))
            time.sleep(1.2)
            lines = self.probe()
            p1 = parse_player(lines) or {}
            moved = abs(p1.get("x", x0) - x0) + abs(p1.get("y", y0) - y0)
            walked += moved
            cells.add(cell_of(p1.get("x", x0), p1.get("y", y0)))
            d = next_direction(d, moved, rng)
        res.update({"walked": walked, "explored": len(cells), "monsters": len(mons), "objects": len(objs),
                    "portals": {str(k): v for k, v in portals.items()}})

    def automap(self, lid):
        import numpy as np
        a = np.asarray(self.g.grab_client().convert("RGB"))
        self.g.key("tab")
        time.sleep(1.2)
        im = self.g.grab_client()
        b = np.asarray(im.convert("RGB"))
        self.g.key("tab")
        time.sleep(0.6)
        h, w = b.shape[:2]
        box = (AUTOMAP_BOX[0] * w // 1600, AUTOMAP_BOX[1] * h // 900, AUTOMAP_BOX[2] * w // 1600, AUTOMAP_BOX[3] * h // 900)
        cnt = ms.changed_pixels(a, b, box)
        im.convert("RGB").save(os.path.join(self.out, "shots", "%s-%03d-map.jpg" % (self.difficulty[0], lid)), quality=60)
        return cnt

    def visit(self, lid, walk_s):
        g = self.g
        res = {"reached": False, "asserts": [], "errors": [], "deaths": 0}
        mark = self.visit_mark = g._size(g.LOADER_LOG)
        p = self.player()
        if player_dead(p):
            self.gc.revive_if_dead()
            self.equip()
        load = self.travel(lid)
        if load is None:
            res["area"] = self.player().get("area")
        else:
            res.update({"reached": True, "load_s": load})
            # the level load's own evidence, first (deadly levels kill the character within seconds): the arrival screen and
            # what stands around it
            g.grab_client().convert("RGB").save(os.path.join(self.out, "shots", "%s-%03d-arrive.jpg" % (self.difficulty[0], lid)), quality=60)
            arrive = self.probe()
            res["arrival_objects"] = sum(1 for ln in arrive if ln.startswith("obj id="))
            res["arrival_monsters"] = len(ms.parse_units(arrive))
            self.equip()
            self.walk(lid, walk_s, res)
            if player_dead(self.player()):  # killed at the end of the walk: the automap is judged alive, in the level
                self.revive(lid, res)
            res["automap_dead"] = player_dead(self.player())  # killed again before the capture: a death screen
            cnt = self.automap(lid)
            res["automap_px"], res["automap"] = cnt, automap_drawn(cnt)
            g.grab_client().convert("RGB").save(os.path.join(self.out, "shots", "%s-%03d.jpg" % (self.difficulty[0], lid)), quality=60)
        self.probe()
        text = g._read_from(g.LOADER_LOG, mark) or ""
        res["asserts"] = ms.parse_asserts(text)
        res["errors"] = ms.other_errors(ms.ASSERT_BLOCK.sub("", text))
        res["crashes"] = self.new_crashes()
        self.visited += 1
        return res


# ---------------------------------------------------------------- phases

def phase_levels(sess, args, plan, data, save):
    diff = sess.difficulty
    rows = data["levels"].setdefault(diff, {})
    only, redo = parse_id_list(args.only), parse_id_list(args.redo)
    todo = [p for p in run_order(plan, diff) if (not only or p["id"] in only) and (not args.act or p["act"] + 1 == args.act)
            and (str(p["id"]) not in rows or p["id"] in redo)]
    sess.g.log("level sweep %s: %d levels to visit (%d done before)" % (diff, len(todo), len(rows)))
    since = 0
    for p in todo:
        sess.gc.guard()
        if args.restart and since >= args.restart:
            sess.restart("restart-%s-%d" % (diff, p["id"]))
            since = 0
        try:
            res = sess.visit(p["id"], args.walk)
        except (ms.Hung, ms.Gone) as e:
            why = "hang" if isinstance(e, ms.Hung) else "crash"
            sess.g.log("LEVEL SWEEP %s in %d %s" % (why.upper(), p["id"], p["name"]))
            res = {"reached": False, why: True, "asserts": [], "errors": [], "deaths": 0}
            res["crashes"] = sess.save_log_tail("%s-%s-%d" % (why, diff, p["id"]))
            res["asserts"] = ms.parse_asserts(sess.g._read_from(sess.g.LOADER_LOG, sess.visit_mark) or "")
            data["notes"].append("%s %s in %s level %d %s; the game was restarted" % (
                datetime.datetime.now().strftime("%H:%M:%S"), why, diff, p["id"], p["name"]))
            sess.g.stop()
            time.sleep(3)
            sess.start(diff)
            since = 0
        rows[str(p["id"])] = res
        save()
        since += 1
        sess.g.log("LEVEL %s %d %s: %s" % (diff, p["id"], p["name"], "; ".join(problem_keys(res)) or "ok"))


def object_pos(lines, oid):
    """(x, y) of object `oid` in an `objects` answer, or None."""
    for ln in lines:
        m = re.match(r"object id=%d class=\d+ mode=-?\d+ dist=\d+ at (-?\d+),(-?\d+)" % oid, ln.strip())
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def find_waypoint(sess, classes, walk_to=False):
    """The nearest waypoint object (id, class, dist); with walk_to, a waypoint farther than WP_NEAR is walked to first (the player
    walks up to it before clicking it: a town reached by the NPC travel stands away from its waypoint)."""
    _, ln = sess.g.hcmd("objects", 10)
    objs = [o for o in parse_objects(ln) if o[1] in classes]
    objs = [o for o in objs if o[2] <= WP_FAR]  # the object hash still holds other acts' objects, thousands of subtiles away
    wp = min(objs, key=lambda o: o[2]) if objs else None
    if wp and walk_to and wp[2] > WP_NEAR:
        pos = object_pos(ln, wp[0])
        if pos:
            sess.g.hcmd("move %d %d" % (pos[0] + 2, pos[1] + 2), 10)
            for _ in range(12):
                time.sleep(1.5)
                _, ln = sess.g.hcmd("objects", 10)
                near = [o for o in parse_objects(ln) if o[0] == wp[0]]
                if near and near[0][2] <= WP_NEAR:
                    return near[0]
            wp = near[0] if near else wp
    return wp


WP_NEAR = 12
WP_FAR = 150
# waypoint rows without a waypoint object, as in 1.13c: level -> note
NO_WAYPOINT_OBJECT = {134: "no waypoint object, as Median 2012 on 1.13c (bugs.md #13: the server's preset loop skips class 402 in level 134)"}


def phase_waypoints(sess, plan, data, save, redo=()):
    rows = data.setdefault("waypoints", {})
    for lid in redo:
        rows.pop(str(lid), None)
    wp_classes = {int(r["*ID"]) for r in ms.read_table(os.path.join(EXCEL, "objects.txt"))[1]
                  if r.get("OperateFn") == str(WAYPOINT_OPERATE) and str(r.get("*ID", "")).isdigit()}
    for p in sorted((p for p in plan if p["waypoint"] is not None), key=lambda p: (p["act"], p["id"])):
        sess.g.hcmd("waypoint n %d set" % p["waypoint"], 8)
    shot_acts = set()
    for p in sorted((p for p in plan if p["waypoint"] is not None), key=lambda p: (p["act"], p["id"])):
        if str(p["id"]) in rows:
            continue
        sess.gc.guard()
        sess.ensure_alive()
        mark = sess.g._size(sess.g.LOADER_LOG)
        t = sess.travel(p["id"], warp_kind=13)
        if t is not None and p["town"]:
            # a town reached by the NPC travel (across acts) stands away from its waypoint, whose room may not be loaded yet:
            # the waypoint travel inside the act (kind 13 lands next to the waypoint), from another waypoint level of the act
            hop = next((q["id"] for q in plan if q["act"] == p["act"] and q["waypoint"] is not None and not q["town"]
                        and q["id"] not in NO_WAYPOINT_OBJECT), None)
            if hop is not None and sess.travel(hop, warp_kind=13) is not None:
                t = sess.travel(p["id"], warp_kind=13)
        r = {"ok": False}
        if t is None:
            r["note"] = "the waypoint travel did not arrive (area %s)" % sess.player().get("area")
        else:
            wp = find_waypoint(sess, wp_classes, walk_to=p["town"])
            if wp is None:
                r["ok"] = p["id"] in NO_WAYPOINT_OBJECT
                r["note"] = "arrived in %s s; %s" % (t, NO_WAYPOINT_OBJECT.get(p["id"], "no waypoint object in the level"))
            else:
                ok, ln = sess.g.hcmd("operate %d %d" % (wp[0], WAYPOINT_OPERATE), 10)
                time.sleep(1.5)
                if p["act"] not in shot_acts:
                    sess.g.grab_client().convert("RGB").save(os.path.join(sess.out, "shots", "wp-act%d.jpg" % (p["act"] + 1)), quality=60)
                    shot_acts.add(p["act"])
                sess.g.key("esc")
                time.sleep(0.8)
                r["ok"] = ok and wp[2] <= WP_NEAR
                r["note"] = "arrived in %s s%s; waypoint object class %d at distance %d; its operate function: %s" % (
                    t, " (town: by the waypoint travel inside the act)" if p["town"] else "", wp[1], wp[2], "panel opened" if ok else "FAILED " + (ln[-1] if ln else ""))
        text = sess.g._read_from(sess.g.LOADER_LOG, mark) or ""
        new = [a["message"] for a in ms.parse_asserts(text) if not known_assert(a["message"])]
        if new:
            r["ok"] = False
            r["note"] += "; asserts: " + "; ".join(new)
        rows[str(p["id"])] = r
        save()


def tp_levels(plan):
    """One field level per act (the first outdoor or preset non-town level) and every level whose map Median replaced (preset where
    D2R has a maze, the uber areas)."""
    out, acts = [], set()
    for p in sorted(plan, key=lambda p: (p["act"], p["id"])):
        if not p["town"] and p["act"] not in acts and p["drlg"] == 3:
            out.append(p["id"])
            acts.add(p["act"])
    special = [13, 14, 18, 59, 60, 65, 84, 95, 116, 125, 126, 127, 133, 134, 135, 136]
    return out + [i for i in special if i not in out and any(p["id"] == i for p in plan)]


def use_scroll(sess, code="tsc"):
    """Right-click a scroll of the code in the inventory, as a player does; -> new portal objects."""
    import game_checks as gc
    before = {o for o, _, _ in parse_portals(sess.probe())}
    ok, ln = sess.g.hcmd("item %s inv" % code, 10)
    cx, cy = gc.first(ln, r" x=(\d+) y="), gc.first(ln, r" y=(\d+) quality")
    if cx is None:
        return []
    sess.g.press("i")
    time.sleep(1.5)
    left, top, cw, ch = gc.INV_CELL
    sess.g.click((left + (cx + 0.5) * cw) / 1600, (top + (cy + 0.5) * ch) / 900, button="right")
    time.sleep(2.0)
    sess.g.press("i")
    time.sleep(1.0)
    return [pt for pt in parse_portals(sess.probe()) if pt[0] not in before]


def phase_tp(sess, plan, data, save, redo=()):
    rows = data.setdefault("tp", {})
    for lid in redo:
        rows.pop(str(lid), None)
    no_tp = {p["id"] for p in plan if p.get("no_tp")}
    for lid in tp_levels(plan):
        if str(lid) in rows:
            continue
        try:
            r = tp_step(sess, lid, lid in no_tp)
        except (ms.Hung, ms.Gone) as e:
            why = "hang" if isinstance(e, ms.Hung) else "crash"
            sess.g.log("LEVEL SWEEP %s in the tp phase, level %d" % (why.upper(), lid))
            r = {"ok": False, why: True, "note": "the game %s during the town portal round trip of level %d (last step: %s)" % (
                "hung" if why == "hang" else "ended", lid, getattr(sess, "tp_step_name", "?"))}
            r["crashes"] = sess.save_log_tail("%s-tp-%d" % (why, lid))
            sess.g.stop()
            time.sleep(3)
            sess.start(sess.difficulty)
        rows[str(lid)] = r
        save()


def tp_step(sess, lid, prevented=False):
    """One level's town portal round trip (phase_tp). prevented: levels.txt PreventTownPortal is set, so the right result is no
    portal at all."""
    sess.gc.guard()
    sess.ensure_alive()
    r = {"ok": False, "note": ""}
    sess.tp_step_name = "travel"
    if sess.travel(lid) is None:
        r["note"] = "level not reached"
    else:
        sess.tp_step_name = "scroll"
        new = use_scroll(sess)
        if not new and player_dead(sess.player()):
            r["ok"] = None
            r["note"] = "not judged: the level's monsters killed the character before the scroll was read"
        elif not new:
            r["ok"] = prevented
            r["note"] = "no portal after the scroll was used" + (" (expected: PreventTownPortal is set)" if prevented else "")
        elif prevented:
            r["note"] = "a portal opened although PreventTownPortal is set"
        else:
            oid, _, dest = new[0]
            deaths = 0
            sess.tp_step_name = "the portal to town"
            if not sess.ensure_alive():  # a dead player clicks no portal (entering one dead ended the game, run n-routes2)
                sess.g.hcmd("enter %d" % oid, 10)
                time.sleep(4)
            else:
                deaths += 1
            town = sess.player().get("area")
            deaths += 1 if sess.ensure_alive() else 0  # killed by what followed it through: respawned in town
            back = [pt for pt in parse_portals(sess.probe()) if pt[2] == lid]
            sess.tp_step_name = "the portal in town back to the level"
            if back:
                sess.g.hcmd("enter %d" % back[0][0], 10)
                time.sleep(4)
            again = sess.player().get("area")
            r["ok"] = town == dest and town in TOWNS.values() and again == lid
            if not r["ok"] and deaths and town == dest:
                r["ok"] = None  # respawned in town away from the portal: the way back is not judged
            r["note"] = "portal to %d; entered -> area %s; the portal in town back -> area %s%s" % (
                dest, town, again, "; the character died %d time(s) on the way (respawned)" % deaths if deaths else "")
    return r


PORTAL_SEARCH_S = 120  # walking time to find a red portal: class 60 is no preset object (objpreset.txt has no row for it), so
# its room must be walked into before the object exists


def phase_portals(sess, plan, data, save, redo=(), search_s=PORTAL_SEARCH_S):
    rows = data.setdefault("portals", {})
    for key in list(rows):
        if int(key.split(":")[0]) in redo:
            rows.pop(key)
    jobs = [(src, dst) for src, dst in PERMANENT_PORTALS.items() if src != 109]  # Anya's portal (109 -> 121) needs her quest
    for diff_rows in data.get("levels", {}).values():
        for lid, res in diff_rows.items():
            for _, (ocls, dest) in res.get("portals", {}).items():
                if ocls != 59 and (int(lid), dest) not in jobs and dest:
                    jobs.append((int(lid), dest))
    for src, dst in jobs:
        key = "%d:%d" % (src, dst)
        if key in rows:
            continue
        sess.gc.guard()
        sess.ensure_alive()
        r = {"ok": False}
        if sess.travel(src) is None:
            r["note"] = "source level %d not reached" % src
        else:
            _, ln = sess.g.hcmd("objects 60", 10)
            objs = [o for o in parse_objects(ln) if o[2] <= WP_FAR]  # not another act's portal still in the hash
            walked = {}
            if not objs:
                # walk the level as the levels phase does until a class-60 portal stands in a loaded room
                t0 = time.time()
                while not objs and time.time() - t0 < search_s and sess.player().get("area") == src:
                    sess.walk(src, 20, walked)
                    _, ln = sess.g.hcmd("objects 60", 10)
                    objs = [o for o in parse_objects(ln) if o[2] <= WP_FAR]
            if not objs:
                r["note"] = "no red portal (objects.txt 60) found in level %d after %d s of walking (%s 8x8 cells, %s deaths)" % (
                    src, search_s, walked.get("explored", 0), walked.get("deaths", 0))
                r = portal_rejudge(r)
            elif objs[0][2] > WP_NEAR and object_pos(ln, objs[0][0]):
                sess.g.hcmd("move %d %d" % object_pos(ln, objs[0][0]), 10)  # walk up to it (a loaded room: the path is short)
                time.sleep(4)
            if objs:
                ok, ln = sess.g.hcmd("enter %d" % objs[0][0], 10)
                time.sleep(5)
                area = sess.player().get("area")
                r["ok"] = area == dst
                r["note"] = "red portal id %d (distance %d) entered: %s -> area %s (want %d)" % (objs[0][0], objs[0][2], ln[-1] if ln else "", area, dst)
        rows[key] = r
        save()


COW_INPUTS = ("leg", "tbk")  # cubemain row 2 (Median 2012's only portal recipe): Wirt's Leg + Tome of Town Portal, op 28
COW_LEVEL = 39


def cow_verdict(new_portals, area_after):
    """(ok, portal id or None): a new portal object to the Moo Moo Farm appeared and entering it arrived there."""
    cow = [pt for pt in new_portals if pt[2] == COW_LEVEL]
    return bool(cow) and area_after == COW_LEVEL, (cow[0][0] if cow else None)


def phase_cow(sess, plan, data, save):
    """The Cow Portal as a player opens it: in the Rogue Encampment, Wirt's Leg and a Tome of Town Portal put into the Horadric
    Cube by pick-up and cube-cell clicks, the panel's Transmute button clicked, the red portal entered. Set-up (harness, documented):
    Baal killed in the difficulty (`quest 40 0 set`, the condition of D2R's and 1.13c's Cow handler) and a cube in the backpack;
    the leg is made in the difficulty played (op 28: a quest item must carry the game's difficulty)."""
    import game_checks as gc
    rows = data.setdefault("portals", {})
    key = "1:39 cow %s" % sess.difficulty
    if key in rows:
        return
    sess.gc.guard()
    sess.ensure_alive()
    log, r = [], {"ok": False}
    if sess.travel(TOWNS[0]) is None:
        r["note"] = "Rogue Encampment not reached"
    else:
        gc.Hl("quest 40 0 set", log)
        gc.ensure_cube()
        gc.release_held_item()
        if not gc._cube_panel_open(log):
            r["note"] = "no Horadric Cube in the backpack"
        else:
            gc._cube_clear(log)
            put = [gc._cube_put(code, cell, log) for cell, code in enumerate(COW_INPUTS)]
            before = {pt[0] for pt in parse_portals(sess.probe())}
            for _ in range(2):  # the pick-ups can close the panel (run n-routes5: Transmute clicked on the bare town)
                if gc.right_panel_open():
                    break
                gc._cube_panel_open(log)
            r["panel_open"] = gc.right_panel_open()
            sess.g.click(gc.CUBE_TRANSMUTE[0] / 1600, gc.CUBE_TRANSMUTE[1] / 900)
            time.sleep(2.5)
            sess.g.grab_client().convert("RGB").save(os.path.join(sess.out, "shots", "%s-cow-transmute.jpg" % sess.difficulty[0]), quality=60)
            left = [it.get("code") for it in gc._cube_now(log)]
            gc._cube_panel_close()
            gc.close_right_panel()
            new = [pt for pt in parse_portals(sess.probe()) if pt[0] not in before]
            area = None
            cow = [pt for pt in new if pt[2] == COW_LEVEL]
            if cow:
                for _ in range(3):  # the first enter right after the portal opens can fail (docs/testing.md `enter`)
                    ok, _ln = sess.g.hcmd("enter %d" % cow[0][0], 10)
                    time.sleep(5)
                    area = sess.player().get("area")
                    if area == COW_LEVEL:
                        break
            r["ok"], _pid = cow_verdict(new, area)
            r["note"] = "inputs in the cube %s; Transmute: cube holds %s afterwards; new portals %s; entered -> area %s" % (
                ["ok" if i else "FAILED" for i in put], left, [(pt[1], pt[2]) for pt in new] or "none", area)
            if area == COW_LEVEL:
                sess.g.grab_client().convert("RGB").save(os.path.join(sess.out, "shots", "%s-cow-arrive.jpg" % sess.difficulty[0]), quality=60)
                sess.travel(TOWNS[0])
    with open(os.path.join(sess.out, "cow-%s.log" % sess.difficulty), "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    rows[key] = r
    save()


# ---------------------------------------------------------------- run / plan / report commands

def build_stamp():
    """The commit the installed build was made from (the build writes no stamp file)."""
    import subprocess
    try:
        return subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "?"
    except OSError:
        return "?"


def run(args):
    if "--foreground" in sys.argv or os.environ.get("MXL_INPUT", "").lower() == "sendinput":
        raise SystemExit("the sweep runs in background input mode only")
    runs = os.environ.get("MXL_RUNS", "")
    if not runs or os.path.commonpath([os.path.abspath(runs), R_ROOT]) != R_ROOT:
        raise SystemExit("MXL_RUNS must point inside %s (got %r)" % (R_ROOT, runs))
    import game_checks as gc  # noqa: E402  (game_ctl reads MXL_SLOT / MXL_RUN at import)
    g = gc.g
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    g.current_run = lambda create=False: out
    data_p = os.path.join(out, "sweep.json")
    data = ms.load_json(data_p, {"levels": {}, "notes": [], "runs": {}})
    data.update({"walk": args.walk, "restart": args.restart, "build": build_stamp()})
    data.setdefault("runs", {}).setdefault(args.difficulty, {})["started"] = datetime.datetime.now().isoformat(timespec="seconds")

    def save():
        ms.save_json(data_p, data)

    plan = plan_levels()
    if not gc.lock():
        print("slot lock not available")
        return 2
    gc.WD = gc.Watchdog()
    gc.WD.start()
    sess = Session(gc, out, data, plan, args.walk)
    phases = [x.strip() for x in args.phases.split(",") if x.strip()]
    try:
        sess.start(args.difficulty)
        for ph in phases:
            g.log("level sweep: phase %s (%s)" % (ph, args.difficulty))
            try:
                sess.ensure_alive()
                if ph == "levels":
                    phase_levels(sess, args, plan, data, save)
                elif ph == "waypoints":
                    phase_waypoints(sess, plan, data, save, parse_id_list(args.redo))
                elif ph == "tp":
                    phase_tp(sess, plan, data, save, parse_id_list(args.redo))
                elif ph == "portals":
                    phase_portals(sess, plan, data, save, parse_id_list(args.redo), args.portal_search)
                elif ph == "cow":
                    phase_cow(sess, plan, data, save)
            except (ms.Hung, ms.Gone) as e:
                why = "hang" if isinstance(e, ms.Hung) else "crash"
                data["notes"].append("%s %s during phase %s; the phase was ended there" % (datetime.datetime.now().strftime("%H:%M:%S"), why, ph))
                sess.save_log_tail("%s-phase-%s" % (why, ph))
                g.stop()
                time.sleep(3)
                sess.start(args.difficulty)
            save()
    finally:
        gc.WD.stop_flag = True
        try:
            g.stop()
        finally:
            data["watchdog"] = gc.WD.summary()
            data["runs"][args.difficulty]["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
            data.setdefault("mapmem", []).append({"when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + " (end)",
                                                  "visited": sess.visited, "files": sess.mapmem()})
            save()
            print(gc.WD.summary())
    return 0


def cmd_plan(args):
    plan = plan_levels()
    n = {d: sum(1 for p in plan if d in p["diffs"]) for d in DIFFS}
    print("%d levels; visits per difficulty %s; no entry route in the data: %s" % (
        len(plan), n, ", ".join("%d %s" % (p["id"], p["name"]) for p in plan if not p["routes"]) or "none"))
    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "name", "label", "act", "drlg", "ltype", "waypoint", "diffs", "routes"])
            for p in plan:
                w.writerow([p["id"], p["name"], p["label"], p["act"] + 1, p["drlg"], p["ltype"], p["waypoint"], "/".join(p["diffs"]),
                            "; ".join(p["routes"])])
        print("wrote", args.csv)
    return 0


def merge_runs(parts):
    """One report's data from several batches' sweep.json ({name: data}, in --out order: a later batch's row replaces an earlier
    one's): levels per difficulty, the phases, notes, map memory."""
    out = {"levels": {}, "notes": [], "runs": {}, "mapmem": [], "watchdog": []}
    for name, d in parts.items():
        for diff, rows in d.get("levels", {}).items():
            out["levels"].setdefault(diff, {}).update(rows)
        for key in ("waypoints", "tp", "portals"):
            if d.get(key):
                out.setdefault(key, {}).update(d[key])
        out["notes"] += ["%s: %s" % (name, n) for n in d.get("notes", [])]
        out["mapmem"] += [dict(m, when="%s %s" % (name, m["when"])) for m in d.get("mapmem", [])]
        for diff, r in d.get("runs", {}).items():
            out["runs"]["%s %s" % (name, diff)] = r
        if d.get("watchdog"):
            out["watchdog"].append("%s: %s" % (name, d["watchdog"]))
        for k in ("walk", "restart", "build"):
            if d.get(k) is not None:
                out.setdefault(k, set()).add(str(d[k]))
    for k in ("walk", "restart", "build"):
        out[k] = "/".join(sorted(out.get(k, set()))) or "-"
    out["watchdog"] = " | ".join(out["watchdog"]) or "-"
    return out


def cmd_report(args):
    parts = {}
    for o in [x for x in args.out.split(",") if x.strip()]:
        d = ms.load_json(os.path.join(os.path.abspath(o), "sweep.json"), None)
        if d is None:
            print("no sweep.json in %s" % o)
            return 2
        name = os.path.basename(os.path.normpath(o))
        if name in parts:  # two lanes' batches of the same name: tell them apart by the parent folder
            name = "%s/%s" % (os.path.basename(os.path.dirname(os.path.normpath(os.path.abspath(o)))), name)
        parts[name] = d
    data = merge_runs(parts)
    text = render_report(plan_levels(), data)
    if args.md:
        with open(args.md, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote %s" % args.md)
    else:
        print(text)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", default=DEFAULT_OUT)
    r.add_argument("--difficulty", choices=DIFFS, default="normal")
    r.add_argument("--only", default="", help="level ids, e.g. 1,5-9 (a trial run)")
    r.add_argument("--act", type=int, default=0, help="only the levels of this act (1-5): one batch per slot lock")
    r.add_argument("--portal-search", type=int, default=PORTAL_SEARCH_S, help="seconds of walking to find a red portal (portals phase)")
    r.add_argument("--redo", default="", help="level ids to visit again in the levels, waypoints and tp phases (their old results are replaced)")
    r.add_argument("--walk", type=float, default=30.0, help="seconds of walking per level")
    r.add_argument("--restart", type=int, default=30, help="a fresh launch every N levels (0: never)")
    r.add_argument("--phases", default="levels", help="levels,waypoints,tp,portals,cow")
    p = sub.add_parser("plan")
    p.add_argument("--csv", default="")
    q = sub.add_parser("report")
    q.add_argument("--out", default=DEFAULT_OUT, help="one or more run folders (comma-separated: the batches of one sweep)")
    q.add_argument("--md", default="")
    a = ap.parse_args()
    return {"run": run, "plan": cmd_plan, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
