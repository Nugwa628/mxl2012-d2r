#!/usr/bin/env python
"""Monster sweep: every monstats row of the built mod spawned next to a strong test character (docs/monster-sweep.md).

    MXL_RUN=<lane> MXL_SLOT=3 MXL_RUNS=<R>\\mxl2012-runs py -3 tools/monster_sweep.py run [--out DIR] [--batch N] [--wait S]
                                                      [--only HC,HC-HC,..] [--redo HC,..] [--limit N] [--area ID] [--shots] [--cycle N]
    py -3 tools/monster_sweep.py plan [--csv FILE]            # the rows, their source, token, hd class and batch kind (no game)
    py -3 tools/monster_sweep.py report --out DIR [--md docs/monster-sweep.md]

`run` needs the slot lock (`game_slots.py lock N <lane>`), the built mod installed in that slot (`install_mod.py --slot N`) and
game_ctl's background input (the default; never MXL_INPUT=sendinput). It plays a character `Monsweepbarb` (created when missing),
raises its life, mana and level, goes to an open area (default 2, the Blood Moor) and then, per batch of rows:

  1. a baseline capture, then `spawn <hcIdx> 1 x y` per row on a ring around the player (each spawn is followed by a short pause and a
     read of what d2rloader.log got meanwhile: an engine assert in that window belongs to that row);
  2. `--wait` seconds (default 3), a `state` (alive / corpse / gone per unit, life, mode) and a capture (a row "drew" when the pixels
     around its position changed against the baseline: the HD stand-in or the vanilla unit is on screen; best effort, see docs);
  3. every unit near the player is killed (`kill <id>`); a row that stays alive is "unkillable" (killable blank in monstats).

Rows that are allied (Align 1/2: pets, totems, NPCs, traps) and rows with a known hazard (`HAZARDS`) run alone, hazards last, so a
bystander does not fake their outcome. A watchdog probes the game after every batch: a game that stops answering (hang) or a process
that is gone (crash) is recorded for the batch, the process this run started is killed (`game_ctl.stop`: this slot only, its shared
files restored), the game is started again, and the rows of the batch run one by one to find the culprit; the sweep goes on after it.

D2RLoader logs an engine assert once per launch and ID, so a later row that raises the same assert is not seen in the log. Rows are
therefore also classified by what is known (`classify`): an ownerless pet (bug #19) by its AI once one row of that AI asserted, an
allied trap that dies at once (bug #41) by AI and Align. Results go to <out>/sweep.json (resumable: done rows are skipped).
Evidence stays outside git (mxl2012-runs/monsweep/).
"""
import argparse
import csv
import datetime
import json
import os
import re
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TOOLS)
EXCEL = os.path.join(ROOT, "work", "mod", "data", "global", "excel")
TOKENS_JSON = os.path.join(TOOLS, "data", "hd_monster_tokens.json")
R_ROOT = os.path.dirname(os.path.dirname(ROOT))  # <R>/mxl2012-wt/<lane> -> <R>
DEFAULT_OUT = os.path.join(R_ROOT, "mxl2012-runs", "monsweep", "sweep")
sys.path.insert(0, TOOLS)
import localconfig  # noqa: E402  (MXL_D2R_EXTRACT / machine.json extract_dir)
D2R_EXCEL = str(localconfig.default_d2r_extract() / "data" / "global" / "excel")

CHAR_NAME = "Monsweepbarb"
CHAR_CLASS = "barbarian"
AREA = 2  # Blood Moor: open ground around the cave mouth
LIFE = 8000000  # whole points (stat 6 / 7 hold 1/256 points: 8,000,000 << 8 still fits in an int32)
EXP_120 = 7022000  # experience.txt row 119: the experience of character level 120

# `NecroPet` and the other summon AIs ask their owner, which has to be a player; a harness spawn has none (bug #19)
OWNERLESS_ASSERT = "ptUnit->eType == UNIT_PLAYER"
OWNERLESS_ASSERTS = (OWNERLESS_ASSERT, "player && UnitGetType(player) == UNIT_PLAYER")  # the second: Raven (druid hawk) asks its owner player
# asserts that docs/bugs.md already explains: message part -> (class key, bug)
# (open ones only: a fixed bug's assert coming back must show as a problem)
KNOWN_ASSERTS = {"nSkillCastId && nSkillCastId != 0xFFFFFFFFU": ("assert-20", "20")}
# AIs of summons that act for an owner player (skills of the owner, "die with the owner"): a harness spawn has none, so a death / assert of these rows is bug #19
OWNER_BOUND_AIS = ("Hydra", "BoneWall", "BladeCreeper", "AssassinSentry", "Raven", "BaalTentacle", "BaalCrabClone", "NecroPet")
# known hazards (hang or assert) that make a row run alone and last; see docs/bugs.md
HAZARDS = {"reanimate": "bug #60: a pet with the `reanimate` monprop and no owner hangs the game when it kills something"}
SCREEN_CENTER = (800, 405)  # the player on the 1600 x 900 HD client
SUB_PX = (27.0, 13.5)  # pixels per sub-tile along x - y and along x + y
BOX = (80, 150, 30)  # half width, height above the feet, height below the feet of a unit's capture box
RING = [(7, -3), (7, 5), (-7, -3), (-7, 5), (0, 9), (0, -9), (11, 1), (-11, 1)]  # spawn offsets around the player


# ---------------------------------------------------------------- tables (pure)

def read_table(path):
    """(header, rows as dicts) of a tab separated Diablo table."""
    with open(path, encoding="latin-1", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    head = rows[0]
    return head, [dict(zip(head, r + [""] * (len(head) - len(r)))) for r in rows[1:] if r]


def d2r_ids(excel_dir=D2R_EXCEL):
    """Ids of D2R's own monstats (the read-only D2R extract); an empty set when it is not there."""
    p = os.path.join(excel_dir, "monstats.txt")
    if not os.path.exists(p):
        return set()
    return {r["Id"] for r in read_table(p)[1] if r.get("Id")}


def token_table(path=TOKENS_JSON):
    """{token lower case: {class, donor / d2r_units, ...}} of tools/data/hd_monster_tokens.json ({} when missing)."""
    try:
        with open(path, encoding="utf-8") as f:
            return {k.lower(): v for k, v in json.load(f)["tokens"].items()}
    except (OSError, ValueError, KeyError):
        return {}


def hd_status(code, mon_id, tokens):
    """What the HD build gives the monster: ('unit', name) a D2R unit of its own, ('stand-in', donor), ('none', why)."""
    t = tokens.get((code or "").lower())
    if t is None:
        return "none", "token %s has no entry in hd_monster_tokens.json" % code
    cls = t.get("class", "")
    if cls == "vanilla":
        units = t.get("d2r_units") or {}
        if units:
            return "unit", ",".join(sorted(units))
        return "none", "vanilla token without a D2R unit"
    if cls == "noart":
        return ("stand-in", t.get("donor", "?") + " (noart)") if t.get("donor") else ("none", "no art")
    if cls in ("reused", "new"):
        return ("stand-in", t["donor"]) if t.get("donor") else ("none", "no donor")
    if cls == "mixed":
        units = t.get("d2r_units") or {}
        if mon_id in units or not t.get("donor"):
            return "unit", mon_id if mon_id in units else ",".join(sorted(units))
        return "stand-in", t["donor"]
    return "none", "unknown class %r" % cls


def plan_rows(excel_dir=EXCEL, d2r=None, tokens=None, monprops=None):
    """Every monstats row (hcIdx order) with what the sweep needs to know about it."""
    d2r = d2r_ids() if d2r is None else d2r
    tokens = token_table() if tokens is None else tokens
    if monprops is None:
        monprops = reanimating_monprops(os.path.join(excel_dir, "monprop.txt"))
    out = []
    for r in read_table(os.path.join(excel_dir, "monstats.txt"))[1]:
        if not r.get("Id") or r["Id"] == "Expansion" or not str(r.get("*hcIdx", "")).isdigit():
            continue  # a blank line or D2R's "Expansion" separator is no monster
        skills = [r.get("Skill%d" % i, "") for i in range(1, 9) if r.get("Skill%d" % i)]
        kind, detail = hd_status(r.get("Code", ""), r["Id"], tokens)
        row = {"hc": int(r["*hcIdx"]), "id": r["Id"], "ai": r.get("AI", ""), "code": r.get("Code", ""), "align": r.get("Align", ""),
               "monprop": r.get("MonProp", ""), "skills": skills, "killable": r.get("killable", "") == "1",
               "enabled": r.get("enabled", "") == "1", "source": "d2r" if r["Id"] in d2r else ("median" if d2r else "?"),
               "hd": kind, "hd_detail": detail, "level": r.get("Level", "")}
        row["hazard"] = hazard_of(row, monprops)
        out.append(row)
    return out


def reanimating_monprops(path):
    """monprop Ids that carry a `reanimate` property (any difficulty)."""
    if not os.path.exists(path):
        return set()
    head, rows = read_table(path)
    cols = [c for c in head if re.fullmatch(r"prop[1-8]( \([NH]\))?", c)]
    return {r["Id"] for r in rows if any(r.get(c) == "reanimate" for c in cols)}


def hazard_of(row, monprops):
    """The key of HAZARDS a row falls under, or ''. Only allied monsters kill for a player in play; `reanimate` is on pets and totems."""
    if row["monprop"] in monprops and row["align"] in ("1", "2"):
        return "reanimate"
    return ""


def is_solo(row):
    """Allied / neutral rows and hazards run alone: a hostile bystander would decide whether they live."""
    return row["align"] != "" or bool(row["hazard"])


def make_batches(rows, size):
    """[(kind, [rows])] in run order: hostile rows in groups of `size`, allied rows one by one, hazards last."""
    hostile = [r for r in rows if not is_solo(r)]
    allied = [r for r in rows if is_solo(r) and not r["hazard"]]
    hazards = [r for r in rows if r["hazard"]]
    out = [("batch", hostile[i:i + size]) for i in range(0, len(hostile), size)]
    out += [("solo", [r]) for r in allied]
    out += [("hazard", [r]) for r in hazards]
    return out


def parse_hc_list(text):
    """'5,10-12' -> {5, 10, 11, 12}."""
    out = set()
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        out.update(range(int(a), int(b or a) + 1))
    return out


# ---------------------------------------------------------------- d2rloader.log (pure)

ASSERT_BLOCK = re.compile(r"\[(?P<time>[^\]]+)\] \[ERROR\][^\n]*\n(?P<body>(?:\+-+\+\n)?(?:\|[^\n]*\n)+)", re.M)


def parse_asserts(text):
    """The engine asserts of a d2rloader.log excerpt: [{time, message, location, id, scope}] in log order."""
    out = []
    for m in ASSERT_BLOCK.finditer(text or ""):
        body = m.group("body")
        if "ASSERTION" not in body:
            continue

        def field(name):
            f = re.search(r"^\|\s*%s\s*:\s*(.*?)\s*\|\s*$" % name, body, re.M)
            return f.group(1) if f else ""
        out.append({"time": m.group("time"), "message": field("Message").replace("BC_ASSERT: ", ""), "location": field("Location").split("\\")[-1],
                    "id": field("ID"), "scope": field("Scope")})
    return out


def other_errors(text):
    """[ERROR] lines of an excerpt that are not assert blocks (a missing COF, a string reference, ...), one per distinct text."""
    seen, out = set(), []
    for ln in (text or "").splitlines():
        m = re.match(r"\[[^\]]+\] \[ERROR\]\s*(\S.*)$", ln)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1)[:200])
    return out


# ---------------------------------------------------------------- state / classification (pure)

def parse_spawn(lines):
    """[(class, unit id, x, y)] of the `spawned class N id=U at X,Y` lines of a spawn answer."""
    out = []
    for ln in lines:
        m = re.search(r"spawned class (\d+) id=(\d+) at (-?\d+),(-?\d+)", ln)
        if m:
            out.append(tuple(int(g) for g in m.groups()))
    return out


def parse_units(lines):
    """{unit id: {state: 'alive'|'corpse', class, mode, life, maxlife, x, y}} of a `state` answer's mon / corpse lines."""
    out = {}
    for ln in lines:
        m = re.match(r"(mon|corpse) id=(\d+) class=(\d+) mode=(-?\d+)", ln.strip())
        if not m:
            continue
        d = {"state": "alive" if m.group(1) == "mon" else "corpse", "class": int(m.group(3)), "mode": int(m.group(4))}
        life = re.search(r"life=(\d+)/(\d+)", ln)
        if life:
            d["life"], d["maxlife"] = int(life.group(1)), int(life.group(2))
        pos = re.search(r"mx=(-?\d+) my=(-?\d+)", ln)
        if pos:
            d["x"], d["y"] = int(pos.group(1)), int(pos.group(2))
        out[int(m.group(2))] = d
    return out


def parse_player_xy(lines):
    for ln in lines:
        m = re.match(r"player id=\d+ .*?area=(\d+) x=(-?\d+) y=(-?\d+)", ln)
        if m:
            return int(m.group(2)), int(m.group(3))
    return None


def outcome_of(spawned, unit):
    """alive / died (a corpse) / gone (not listed any more) / failed (the spawn did not make a unit)."""
    if not spawned:
        return "failed"
    if unit is None:
        return "gone"
    return "alive" if unit["state"] == "alive" else "died"


def classify(row, res, owner_ais=()):
    """The known classes a row's result falls under: [(key, text)]. `owner_ais`: AIs whose rows asserted ownerless (bug #19) in this run."""
    cls = []
    asserts = res.get("asserts", [])
    if any(m in a["message"] for a in asserts for m in OWNERLESS_ASSERTS):
        cls.append(("ownerless-pet", "bug #19: the AI asks its owner, a harness spawn has none"))
    elif row["ai"] in OWNER_BOUND_AIS and (asserts or res.get("outcome") == "died"):
        cls.append(("ownerless-pet", "bug #19 family: an owner-bound summon (AI %s) made without an owner" % row["ai"]))
    elif row["ai"] in owner_ais and res.get("spawned"):
        cls.append(("ownerless-pet", "bug #19 by AI %s (the assert was logged for an earlier row, once per launch)" % row["ai"]))
    if row["ai"].startswith("Trap") and res.get("outcome") == "died":
        cls.append(("trap-dies", "bug #41: a trap spawned by the harness (no owner, nothing to shoot at) dies at its first tick"))
    for a in list(asserts) + [{"message": m} for m in res.get("batch_asserts", [])]:
        for part, (key, bug) in KNOWN_ASSERTS.items():
            if part in a["message"] and key not in [k for k, _ in cls]:
                cls.append((key, "bugs.md #%s: the same assert" % bug))
    if not res.get("spawned") and not row["enabled"]:
        cls.append(("disabled-row", "enabled is blank in monstats (Median's own table too): D2R refuses to make the unit"))
    if row["hazard"]:
        cls.append(("hazard-" + row["hazard"], HAZARDS[row["hazard"]]))
    if res.get("outcome") == "alive" and res.get("unkillable"):
        cls.append(("unkillable", "killable is blank in monstats (D2R's death function leaves the unit alive)" if not row["killable"]
                    else "kill left the unit alive although killable is 1"))
    return cls


def problem_keys(row, res, owner_ais=()):
    """What is a problem for the report (known classes are counted but not listed as new): [key]."""
    keys = []
    known = {k for k, _ in classify(row, res, owner_ais)}
    if res.get("hang"):
        keys.append("hang")
    if res.get("crash"):
        keys.append("crash")
    if res.get("outcome") == "failed" and not res.get("hang") and not res.get("crash") and "disabled-row" not in known:
        keys.append("spawn-failed")
    for a in res.get("asserts", []):
        if "ownerless-pet" in known and (row["ai"] in OWNER_BOUND_AIS or any(m in a["message"] for m in OWNERLESS_ASSERTS)):
            continue  # an owner-bound summon: whatever it asks of its missing owner is bug #19
        if any(part in a["message"] and key in known for part, (key, _) in KNOWN_ASSERTS.items()):
            continue
        if "disabled-row" in known and "MONFLAG_ENABLED" in a["message"]:
            continue
        keys.append("assert: %s (%s)" % (a["message"], a["location"]))
    # `run --attribute`: seen in the full run (while the row ran in a batch / after hundreds of other rows in the launch), not when it ran alone in a fresh launch
    for label, ms_ in (("assert in a batch, not repeated alone", res.get("batch_asserts", [])), ("assert in the full run, not repeated alone", res.get("first_run_asserts", []))):
        for m in ms_:
            if any(part in m and key in known for part, (key, _) in KNOWN_ASSERTS.items()) or any(o in m for o in OWNERLESS_ASSERTS):
                continue
            if not any(a["message"] == m for a in res.get("asserts", [])) and "%s: %s" % (label, m) not in keys:
                keys.append("%s: %s" % (label, m))
    if res.get("errors"):
        keys += ["log: " + e for e in res["errors"]]
    if res.get("outcome") == "died" and "trap-dies" not in known and "ownerless-pet" not in known and row["align"] == "" and res.get("alone"):
        keys.append("died-alone")
    if row.get("hd") == "none" and res.get("spawned"):
        keys.append("no-hd-art: %s" % row.get("hd_detail", ""))
    if res.get("drew") is False and res.get("outcome") in ("alive", "died") and res.get("shot"):
        keys.append("not-drawn")
    return keys


# ---------------------------------------------------------------- screenshots (pure geometry + numpy)

def screen_xy(player, mon, centre=SCREEN_CENTER, scale=SUB_PX):
    """Client pixel of a unit's feet from the sub-tile coordinates of the player and the unit (isometric)."""
    dx, dy = mon[0] - player[0], mon[1] - player[1]
    return centre[0] + scale[0] * (dx - dy), centre[1] + scale[1] * (dx + dy)


def unit_box(feet, size, box=BOX):
    """(x0, y0, x1, y1) around a unit standing at `feet`, clipped to a capture of `size` (w, h)."""
    w, h = size
    x0, y0 = int(feet[0] - box[0]), int(feet[1] - box[1])
    x1, y1 = int(feet[0] + box[0]), int(feet[1] + box[2])
    return max(0, x0), max(0, y0), min(w, x1), min(h, y1)


def changed_pixels(a, b, region, thr=120):
    """How many pixels of `region` (x0, y0, x1, y1) differ by more than `thr` (sum over the channels) between two captures."""
    import numpy as np
    x0, y0, x1, y1 = region
    if x1 <= x0 or y1 <= y0:
        return 0
    d = np.abs(a[y0:y1, x0:x1].astype(int) - b[y0:y1, x0:x1].astype(int)).sum(axis=2)
    return int((d > thr).sum())


DREW_MIN = 350  # changed pixels in a unit's box that count as "something was drawn there" (rain and torches change ~0-60)


def drew(count, noise=0):
    return count >= max(DREW_MIN, 4 * noise)


# ---------------------------------------------------------------- the report (pure)

def summarize(plan, results, owner_ais=()):
    """Counts for the report: {total, tested, spawned, failed, alive, died, gone, hang, crash, asserts, drew, notdrawn, unkillable, known{}}."""
    rows = {r["hc"]: r for r in plan}
    s = {"total": len(plan), "tested": 0, "spawned": 0, "failed": 0, "alive": 0, "died": 0, "gone": 0, "hang": 0, "crash": 0, "assert_rows": 0,
         "drew": 0, "not_drawn": 0, "unshot": 0, "hd_art": 0, "no_hd_art": 0, "unkillable": 0, "known": {}, "problems": {}}
    for hc, res in results.items():
        row = rows.get(int(hc))
        if row is None:
            continue
        s["tested"] += 1
        s["spawned"] += 1 if res.get("spawned") else 0
        s["failed"] += 1 if res.get("outcome") == "failed" else 0
        if res.get("outcome") in ("alive", "died", "gone"):
            s[res["outcome"]] += 1
        s["hang"] += 1 if res.get("hang") else 0
        s["crash"] += 1 if res.get("crash") else 0
        s["assert_rows"] += 1 if res.get("asserts") else 0
        s["unkillable"] += 1 if res.get("unkillable") else 0
        if res.get("spawned"):
            s["hd_art" if row["hd"] != "none" else "no_hd_art"] += 1
        if res.get("shot"):
            s["drew" if res.get("drew") else "not_drawn"] += 1
        elif res.get("spawned"):
            s["unshot"] += 1
        for k, _ in classify(row, res, owner_ais):
            s["known"][k] = s["known"].get(k, 0) + 1
        for k in problem_keys(row, res, owner_ais):
            s["problems"].setdefault(k, []).append(row)
    return s


def md_cell(x):
    return str(x).replace("|", "/").replace("\n", " ")


def render_report(plan, data):
    """docs/monster-sweep.md from the plan and a sweep.json."""
    results = data.get("rows", {})
    owner_ais = set(data.get("owner_ais", []))
    s = summarize(plan, results, owner_ais)
    L = ["# Monster sweep", "",
         "Generated by `py -3 tools/monster_sweep.py report` from the sweep run's `sweep.json` (evidence outside git: `mxl2012-runs/monsweep/`). "
         "How rows are spawned, what the columns mean and the limits: the docstring of `tools/monster_sweep.py`.", "",
         "Run: started %s, finished %s; character `%s` (life %s), area %s, batch %s, wait %s s; mod build %s. Real input watchdog: %s" % (
             data.get("started", "-"), data.get("finished", "-"), CHAR_NAME, "{:,}".format(LIFE), data.get("area", "-"), data.get("batch", "-"),
             data.get("wait", "-"), data.get("build", "-"), data.get("watchdog", "-")), "",
         "## Summary", "",
         "| | Rows |", "|---|---:|",
         "| monstats rows in the built mod | %d |" % s["total"], "| rows tested | %d |" % s["tested"], "| spawned (the game made a unit) | %d |" % s["spawned"],
         "| spawn failed | %d |" % s["failed"], "| alive after the wait | %d |" % s["alive"], "| dead after the wait (a corpse) | %d |" % s["died"],
         "| gone after the wait (no longer listed) | %d |" % s["gone"], "| left alive by `kill` (unkillable) | %d |" % s["unkillable"],
         "| hung the game | %d |" % s["hang"], "| crashed the game | %d |" % s["crash"], "| raised an engine assert | %d |" % s["assert_rows"],
         "| spawned with HD art in the token table (a D2R unit or a stand-in) | %d |" % s["hd_art"],
         "| spawned with no HD art (`no-hd-art`) | %d |" % s["no_hd_art"]]
    if s["drew"] + s["not_drawn"]:
        L += ["| judged by a capture: something changed around the unit | %d |" % s["drew"], "| judged by a capture: nothing changed | %d |" % s["not_drawn"]]
    L.append("")
    by_src = {}
    for r in plan:
        by_src.setdefault(r["source"], [0, 0])[0] += 1
        if str(r["hc"]) in results:
            by_src[r["source"]][1] += 1
    L += ["Rows by source (`d2r` = the Id exists in D2R's own monstats, `median` = Median's own): " + ", ".join(
        "%s %d (%d tested)" % (k, v[0], v[1]) for k, v in sorted(by_src.items())) + ".", ""]
    by_hd = {}
    for r in plan:
        by_hd[r["hd"]] = by_hd.get(r["hd"], 0) + 1
    L += ["HD art by the token table (`tools/data/hd_monster_tokens.json`): " + ", ".join("%s %d" % (k, v) for k, v in sorted(by_hd.items())) + ".", ""]
    if s["known"]:
        L += ["## Known classes (not new problems)", "", "| Class | Rows | Where it is explained |", "|---|---:|---|"]
        notes = {"ownerless-pet": "bugs.md #19 (a harness spawn has no owner; Median's own spawns of these rows have one)",
                 "trap-dies": "bugs.md #41 (a harness-spawned trap dies at its first tick: allied ones, and the hostile Trap-* rows too)",
                 "assert-20": "bugs.md #20 (`nSkillCastId` assert of a client cast; non-fatal)",
                 "disabled-row": "bugs.md #70 (enabled blank in monstats, as in Median's own table: D2R makes no unit)",
                 "unkillable": "bugs.md #11 (killable blank in monstats: D2R's death function leaves the unit alive)",
                 "hazard-reanimate": "bugs.md #60 (a `reanimate` pet without an owner hangs the game when it kills; run alone)"}
        for k, v in sorted(s["known"].items()):
            L.append("| %s | %d | %s |" % (k, v, notes.get(k, "")))
        L.append("")
    L += ["## Problem clusters", "", "| Problem | Rows | Examples |", "|---|---:|---|"]
    if not s["problems"]:
        L.append("| none | 0 | |")
    for k, v in sorted(s["problems"].items(), key=lambda kv: (-len(kv[1]), kv[0])):
        L.append("| %s | %d | %s |" % (md_cell(k), len(v), md_cell(", ".join("%d %s" % (r["hc"], r["id"]) for r in v[:8]) + (" ..." if len(v) > 8 else ""))))
    L += ["", "## Per-row problems", "",
          "Only rows with a problem of the clusters above; `hc` is the monstats `*hcIdx` (the class id `spawn` takes). "
          "Known classes are in the table above and not repeated here.", "",
          "| hc | Id | AI | Token / HD | Source | Outcome | Problems |", "|---:|---|---|---|---|---|---|"]
    rows = {r["hc"]: r for r in plan}
    for hc in sorted(int(k) for k in results):
        row, res = rows.get(hc), results[str(hc)]
        if row is None:
            continue
        keys = problem_keys(row, res, owner_ais)
        if keys:
            L.append("| %d | %s | %s | %s %s | %s | %s | %s |" % (hc, row["id"], row["ai"], row["code"], row["hd"], row["source"],
                                                               res.get("outcome", "-") + (" (hang)" if res.get("hang") else "") + (" (crash)" if res.get("crash") else ""),
                                                               md_cell("; ".join(keys))))
    if data.get("notes"):
        L += ["", "## Notes of the run", ""] + ["- " + md_cell(n) for n in data["notes"]]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- JSON helpers

def load_json(p, default):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(p, data):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, p)


# ---------------------------------------------------------------- the game session

class Hung(Exception):
    """The game process is alive but the harness has stopped answering."""


class Gone(Exception):
    """The game process is gone."""


class Session:
    def __init__(self, gc, out, data, want_shots=True):
        self.gc, self.g, self.out, self.data = gc, gc.g, out, data
        self.shots = want_shots
        self.restarts = 0
        self.crash_seen = set(os.listdir(self.g.CRASH_DIR)) if os.path.isdir(self.g.CRASH_DIR) else set()
        self.log_mark = self.g._size(self.g.LOADER_LOG)

    # --- game life
    def alive(self):
        return bool(self.g.game_pids())

    def probe(self, tries=2, gap=5.0):
        """True when the harness answers `state`; Gone when the process is not there; Hung when it lives and stays silent."""
        for i in range(tries):
            ok, lines = self.g.hcmd("state", 8)
            if ok:
                return lines
            if not self.alive():
                raise Gone()
            time.sleep(gap)
        raise Hung()

    def start(self, area):
        gc, g = self.gc, self.g
        if not gc.to_menu():
            raise RuntimeError("game did not reach the main menu")
        card = gc.card_of(CHAR_NAME)
        ok = gc.create_character(CHAR_CLASS, CHAR_NAME) if card is None else gc.enter_game(card)
        if not ok:
            raise RuntimeError("could not play %s" % CHAR_NAME)
        self.tank()
        gc.goto(area)
        self.tank()
        self.log_mark = g._size(g.LOADER_LOG)

    def tank(self):
        for s in (7, 6, 9, 8):
            self.gc.setstat("player", s, LIFE << 8)
        self.gc.setstat("player", 13, EXP_120)
        self.gc.setstat("player", 12, 120)

    def refresh_area(self, area):
        """Another area and back: D2R frees the units of a level nobody is in."""
        other = 3 if area != 3 else 2
        for a in (other, area):
            self.gc.goto(a)
            time.sleep(1.5)
        self.tank()

    def kill_and_restart(self, area, why):
        """Kill what this run started (game_ctl.stop: this slot's processes only, shared files restored) and play again."""
        g = self.g
        self.save_log_tail(why)
        g.stop()
        time.sleep(3)
        self.restarts += 1
        self.start(area)

    def save_log_tail(self, why):
        g = self.g
        tail = g._read_from(g.LOADER_LOG, self.log_mark) or ""
        with open(os.path.join(self.out, "logtail-%s.log" % re.sub(r"\W+", "-", why)), "w", encoding="utf-8") as f:
            f.write(tail)
        crashes = sorted(set(os.listdir(g.CRASH_DIR)) - self.crash_seen) if os.path.isdir(g.CRASH_DIR) else []
        for c in crashes:
            src = os.path.join(g.CRASH_DIR, c)
            if os.path.isfile(src):
                shutil.copy2(src, self.out)
        self.crash_seen |= set(crashes)
        return crashes

    # --- one batch
    def grab(self):
        import numpy as np
        return np.asarray(self.g.grab_client().convert("RGB"))

    def save_capture(self, img, box, hc, cnt):
        """The capture a row was judged on with its box (red: nothing changed there) for a look at what the sweep saw; at most 80 files."""
        from PIL import Image, ImageDraw
        folder = os.path.join(self.out, "shots")
        os.makedirs(folder, exist_ok=True)
        if len(os.listdir(folder)) >= 80:
            return
        im = Image.fromarray(img)
        dr = ImageDraw.Draw(im)
        dr.rectangle(box, outline=(255, 0, 0))
        dr.text((box[0] + 3, box[1] + 3), "%d:%d" % (hc, cnt), fill=(255, 255, 0))
        im.save(os.path.join(folder, "hc%d.jpg" % hc), quality=70)

    def run_batch(self, rows, wait, area):
        """Spawn `rows` (a batch / solo / hazard group), return {hc: result}. Raises Hung / Gone when the game stops."""
        gc, g = self.gc, self.g
        lines = self.probe()
        pxy = parse_player_xy(lines)
        if pxy is None:
            raise RuntimeError("no player in state: %s" % lines[:2])
        self.tank()
        res, ids = {}, {}
        batch_mark = g._size(g.LOADER_LOG)
        prev = self.grab() if self.shots else None
        for i, row in enumerate(rows):
            r = {"id": row["id"], "spawned": False, "asserts": [], "errors": [], "alone": len(rows) == 1}
            res[row["hc"]] = r
            mark = g._size(g.LOADER_LOG)
            for k in range(len(RING)):  # a spot with no room answers "nothing spawned": the next ring spot
                dx, dy = RING[(i + k) % len(RING)]
                ok, ans = g.hcmd("spawn %d 1 %d %d" % (row["hc"], pxy[0] + dx, pxy[1] + dy), 10)
                got = parse_spawn(ans)
                if ok and got:
                    r["spawned"], r["unit"], r["at"] = True, got[0][1], [got[0][2], got[0][3]]
                    ids[got[0][1]] = row["hc"]
                    break
                if any("no answer" in a for a in ans):
                    break
            time.sleep(0.35)  # the unit's first frames are on screen, and an assert of the spawn / the first ticks is in the log
            if self.shots and r["spawned"]:
                after = self.grab()
                h, w = after.shape[:2]
                box = unit_box(screen_xy(pxy, tuple(r["at"])), (w, h))
                cnt = changed_pixels(prev, after, box)
                r["shot"], r["changed"], r["drew"] = True, cnt, drew(cnt)
                if not r["drew"]:
                    self.save_capture(after, box, row["hc"], cnt)
                prev = after
            text = g._read_from(g.LOADER_LOG, mark) or ""
            r["asserts"] = [dict(a, when="spawn") for a in parse_asserts(text)]
            r["errors"] = other_errors(ASSERT_BLOCK.sub("", text))
            if not self.alive():
                raise Gone()
        time.sleep(max(0.0, wait))
        lines = self.probe(tries=1)
        units = parse_units(lines)
        for uid, hc in ids.items():
            u = units.get(uid)
            r = res[hc]
            r["outcome"] = outcome_of(True, u)
            if u:
                r["mode"], r["life"] = u["mode"], u.get("life")
        for hc, r in res.items():
            if not r["spawned"]:
                r["outcome"] = "failed"
        late = parse_asserts(g._read_from(g.LOADER_LOG, batch_mark) or "")
        seen = {a["id"] for r in res.values() for a in r["asserts"]}
        for a in late:  # an assert that came after its spawn window: the whole batch is the suspect
            if a["id"] not in seen:
                for r in res.values():
                    if r["spawned"]:
                        r["asserts"].append(dict(a, when="batch" if len(res) > 1 else "late"))
        self.cleanup(units, ids, res)
        return res

    def cleanup(self, units, ids, res):
        """Kill every unit near the player (each spawned row's result learns whether its unit stayed alive)."""
        g = self.g
        for uid, u in sorted(units.items()):
            if u["state"] != "alive":
                continue
            ok, ans = g.hcmd("kill %d" % uid, 8)
            if uid in ids and not ok and any("alive" in a for a in ans):
                res[ids[uid]]["unkillable"] = True
        # whatever the units spawned (minions) stays until the next batch's kill pass; the area is re-entered every so often


# ---------------------------------------------------------------- run

def build_stamp():
    p = os.path.join(ROOT, "work", "mod", "data", "dataversionbuild.txt")
    try:
        return open(p, encoding="latin-1").read().strip()
    except OSError:
        return "?"


def run(args):
    sys.path.insert(0, TOOLS)
    for forbidden in ("--foreground",):
        if forbidden in sys.argv or os.environ.get("MXL_INPUT", "").lower() == "sendinput":
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
    data = load_json(data_p, {"started": datetime.datetime.now().isoformat(timespec="seconds"), "rows": {}, "owner_ais": [], "notes": []})
    data.update({"area": args.area, "batch": args.batch, "wait": args.wait, "build": build_stamp()})
    plan = plan_rows()
    only = parse_hc_list(args.only)
    redo = parse_hc_list(args.redo)
    todo = [r for r in plan if (not only or r["hc"] in only) and (str(r["hc"]) not in data["rows"] or r["hc"] in redo)]
    if args.attribute:  # rows with an assert (not an owner / disabled-row one): each alone, in a fresh launch (D2R logs an assert once per launch)
        def _suspect(res):
            return not res.get("attributed") and any(not any(m in a["message"] for m in OWNERLESS_ASSERTS + ("MONFLAG_ENABLED",)) for a in res["asserts"])
        todo = [r for r in plan if str(r["hc"]) in data["rows"] and (not only or r["hc"] in only) and _suspect(data["rows"][str(r["hc"])])]
    if args.limit:
        todo = todo[:args.limit]
    batches = [("attr", [r]) for r in todo] if args.attribute else make_batches(todo, args.batch)
    g.log("sweep: %d rows to test in %d groups (%d done before)" % (len(todo), len(batches), len(data["rows"])))
    if not gc.lock():
        print("slot lock not available")
        return 2
    gc.WD = gc.Watchdog()
    gc.WD.start()
    sess = Session(gc, out, data, want_shots=args.shots)
    owner_ais = set(data["owner_ais"])
    started = False
    done_groups = 0
    try:
        for kind, rows in batches:
            gc.guard()
            queue = [rows]
            while queue:
                grp = queue.pop(0)
                try:
                    if not started or not sess.alive() or kind == "attr":
                        if started:
                            g.stop()
                            time.sleep(3)
                        sess.start(args.area)
                        started = True
                    elif args.restart and done_groups and done_groups % args.restart == 0:
                        g.stop()  # a launch that loads hundreds of different monsters fills D2R's asset cache (AssetCache.h:187) and the renderer
                        time.sleep(3)
                        sess.start(args.area)
                        sess.restarts += 1
                    elif kind == "hazard" or (args.cycle and done_groups and done_groups % args.cycle == 0):
                        sess.refresh_area(args.area)  # a clean area: no corpses, no leftover minions to be a hazard's victim
                    res = sess.run_batch(grp, args.wait, args.area)
                except (Hung, Gone) as e:
                    why = "hang" if isinstance(e, Hung) else "crash"
                    names = ", ".join("%d %s" % (r["hc"], r["id"]) for r in grp)
                    g.log("SWEEP %s on %s: %s" % (why.upper(), kind, names))
                    data.setdefault("notes", []).append("%s %s of a group (%s): %s; the game was restarted and %s" % (
                        datetime.datetime.now().strftime("%H:%M:%S"), why, kind, names,
                        "the rows were run one by one" if len(grp) > 1 else "this row is marked"))
                    sess.kill_and_restart(args.area, "%s-%s" % (why, grp[0]["hc"]))
                    if len(grp) > 1:  # one by one to find the culprit
                        queue = [[r] for r in grp] + queue
                    else:
                        res = {grp[0]["hc"]: {"id": grp[0]["id"], "spawned": True, why: True, "outcome": "gone", "asserts": [], "errors": [], "alone": True}}
                        data["rows"].update({str(k): v for k, v in res.items()})
                    save_json(data_p, data)
                    continue
                for hc, r in res.items():
                    if kind == "attr":
                        old = data["rows"][str(hc)]
                        r["batch_asserts"] = [a["message"] for a in old["asserts"] if a.get("when") in ("batch", "late")]
                        r["first_run_asserts"] = [a["message"] for a in old["asserts"] if a.get("when") == "spawn"]
                        r["attributed"] = True
                    data["rows"][str(hc)] = r
                    if any(m in a["message"] for a in r["asserts"] for m in OWNERLESS_ASSERTS):
                        row = next(x for x in plan if x["hc"] == hc)
                        owner_ais.add(row["ai"])
                data["owner_ais"] = sorted(owner_ais)
                save_json(data_p, data)
                done_groups += 1
                g.log("SWEEP %s %s" % (kind, " ".join("%d:%s%s" % (hc, r["outcome"], "!" if (r["asserts"] or r["errors"]) else "") for hc, r in res.items())))
    finally:
        gc.WD.stop_flag = True
        try:
            if started:
                g.stop()
        finally:
            data["watchdog"] = gc.WD.summary()
            data["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
            data["restarts"] = sess.restarts
            save_json(data_p, data)
            print(gc.WD.summary())
    return 0


# ---------------------------------------------------------------- plan / report commands

def cmd_plan(args):
    plan = plan_rows()
    batches = make_batches(plan, args.batch)
    print("%d rows, %d groups (%d solo, %d hazards)" % (len(plan), len(batches), sum(1 for k, _ in batches if k == "solo"), sum(1 for k, _ in batches if k == "hazard")))
    for key in ("source", "hd", "align", "hazard"):
        counts = {}
        for r in plan:
            counts[r[key]] = counts.get(r[key], 0) + 1
        print("%-7s %s" % (key, counts))
    if args.csv:
        with open(args.csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["hc", "id", "ai", "code", "align", "monprop", "source", "hd", "hd_detail", "hazard", "killable"])
            for r in plan:
                w.writerow([r["hc"], r["id"], r["ai"], r["code"], r["align"], r["monprop"], r["source"], r["hd"], r["hd_detail"], r["hazard"], int(r["killable"])])
        print("wrote", args.csv)
    return 0


def cmd_report(args):
    data = load_json(os.path.join(os.path.abspath(args.out), "sweep.json"), None)
    if data is None:
        print("no sweep.json in %s" % args.out)
        return 2
    text = render_report(plan_rows(), data)
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
    r.add_argument("--batch", type=int, default=6)
    r.add_argument("--wait", type=float, default=3.0)
    r.add_argument("--area", type=int, default=AREA)
    r.add_argument("--only", default="", help="monstats hcIdx list, e.g. 5,10-20 (a trial run)")
    r.add_argument("--redo", default="", help="hcIdx list to test again (their old results are replaced)")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--restart", type=int, default=0, help="play again in a fresh launch every N groups (0: never; the full run of lane monsweep filled the asset cache after ~240 rows)")
    r.add_argument("--attribute", action="store_true", help="run each row that has an assert alone in a fresh launch (which row raises it; an assert that appears only after many rows is the asset cache filling up)")
    r.add_argument("--shots", action="store_true", help="also judge by pixels whether a unit appeared (noisy: corpses and debris move; off by default)")
    r.add_argument("--cycle", type=int, default=40, help="leave and re-enter the area every N groups (frees the corpses)")
    p = sub.add_parser("plan")
    p.add_argument("--batch", type=int, default=6)
    p.add_argument("--csv", default="")
    q = sub.add_parser("report")
    q.add_argument("--out", default=DEFAULT_OUT)
    q.add_argument("--md", default="")
    a = ap.parse_args()
    return {"run": run, "plan": cmd_plan, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
