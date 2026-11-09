"""Every skill's whole visual chain in HD, and what still ends in nothing (docs/hd-effects.md section 11, bug #562).

tools/missile_looks.py decides each missile row by what it does. This step walks from the skills down: every row of skills.txt (class,
monster and item skills) through every missile, sub-missile, explosion, client piece, overlay and state it can make, and asks of each
node what legacy draws and what HD draws. A node is one of

  draws      HD has a definition with an effect or a mesh for this row
  accepted   HD draws nothing here and that is right: a client trail piece its flying row carries, an overlay whose partner in the same state
             draws (D2R merged many front / back pairs into one), a hand pick, a D2R row on D2R's own stub while the rest of the skill draws
  gap        legacy draws, HD does not (which way it fails: `CODES`), or a long-lived row sits on a model vanilla plays once
  blank      legacy draws nothing here either (a logic row, a row without art)

A skill is `not visual` when no node of it draws in legacy, `ok` when every node legacy draws has a picture (or is accepted), `partial` when
some do not, and `invisible` when legacy draws something and HD nothing at all: the case the tests stop on. A name in the chain that no table
has is reported, not a gap: the game skips it.

Report statuses: ok; fixed (had a gap in the before state, none now); hand (a gap remains); not visual.

The step also repairs overlays, by the method of missile_looks.py: an overlay row with a legacy picture whose HD definition draws nothing gets
the closest D2R overlay that draws, by colour, size and words, of its own role (a state overlay takes one a vanilla state loops, a cast overlay
one vanilla plays once), scaled to the legacy art, written under the row's own name in its own Character folder. Hand picks
(data/hd-effects-picks.tsv) are never overruled. D2R's own rows on D2R's own stubs are left alone unless a skill would otherwise show nothing.

Output: work/mod/skill_looks.md and skill_looks.tsv (every skill with its status and gaps; row names, so not committed).
Usage: py -3 tools/skill_looks.py [--work DIR] [--check] [--no-fix] [--baseline MISSILES_JSON]
  --check     audit only: exit 1 when a skill reached by a class, an item or a monster shows something in legacy and nothing in HD
  --no-fix    the scan and report only
  --baseline  an earlier missiles.json: `fixed` also counts skills whose gap that map still had (the report's before column)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effects_hd as fx  # noqa: E402
import fxpaths  # noqa: E402
import item_skill_audit as isa  # noqa: E402
import missile_looks as ml  # noqa: E402

SKILL_MISSILES = fx.SKILL_MISSILE_COLS
SKILL_OVERLAYS = ("srvoverlay", "castoverlay", "tgtoverlay", "prgoverlay", "sumoverlay", "cltoverlaya", "cltoverlayb", "ItemCastOverlay")
SKILL_STATES = ("aurastate", "auratargetstate", "passivestate")
STATE_OVERLAYS = ("overlay1", "overlay2", "overlay3", "overlay4", "pgsvoverlay", "castoverlay", "removerlay")
MISSILE_NEXT = (*fx.SUB_COLS, *fx.HIT_COLS)
ITEM_TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic", "gems", "cubemain")

CODES = {
    "stub": "the HD definition has no effect (a stub)",
    "null": "the row has a legacy picture and the map has no model",
    "no_def": "the map names a definition that does not exist",
    "play_once": "the row flies or stays on a model vanilla plays once",
    "filtered": "the definition draws only for skills it names",
    "no_overlay": "no HD definition for this overlay in its Character folder",
}
STATUS_ORDER = {"invisible": 0, "partial": 1, "ok": 2, "not visual": 3}


def is_art(name: str) -> bool:
    return name not in ("", "null")


# ----------------------------------------------------------------------------------------------- what HD draws
def entity_draws(entity: dict, skill: str | None = None) -> bool:
    """An entity draws when it has an effect with a file or a mesh and its source-skill filter (if any) passes: a filter on a name means the entity
    is only for that skill, the empty name is the entity every other skill gets (D2R's ground_fire_small, lightning_strike)."""
    comps = entity.get("components", [])
    has_vfx = any(ml.effect_draws(c) for c in comps)
    has_mesh = any("Model" in c.get("type", "") or "Mesh" in c.get("type", "") for c in comps)
    if not (has_vfx or has_mesh):
        return False
    filters = [c.get("sourceSkill", "") for c in comps if c.get("type") == "UnitSourceSkillFilterComponent"]
    return not filters or "" in filters or skill in filters


def definition_draws(d: dict | None, skill: str | None = None) -> bool:
    """Whether a definition puts anything on screen for a skill (None: for a skill it does not name)."""
    return bool(d) and any(entity_draws(e, skill) for e in d.get("entities", []))


def named_only(d: dict | None) -> bool:
    """The definition has effects, all of them only for skills it names (no entity for "any other skill")."""
    return bool(d) and not definition_draws(d) and any(
        entity_draws(dict(components=[c for c in e.get("components", []) if c.get("type") != "UnitSourceSkillFilterComponent"]))
        for e in d.get("entities", []))


class Hd:
    """Every HD definition the built mod can show: the mod's own files first, then D2R's."""

    def __init__(self, data: Path, d2r_missiles: Path = fx.HDM, d2r_overlays: Path = fx.HDO, current: dict | None = None):
        self.data = data
        self.current = current if current is not None else fx.load_json(data / "hd" / "missiles" / "missiles.json")
        self.models = ml.Models(data / "hd" / "missiles", d2r_missiles)
        self.overlay_dirs = (data / "hd" / "overlays", d2r_overlays)
        self.overlay_memo: dict[str, dict | None] = {}

    def model_of(self, row: str):
        return self.current.get(fx.norm_key(row), self.current.get(row.lower()))

    def overlay_definition(self, folder: str, row: str) -> dict | None:
        rel = f"{folder.lower()}/{fx.norm_key(row)}"
        if rel not in self.overlay_memo:
            self.overlay_memo[rel] = next((fx.load_json(d / f"{rel}.json") for d in self.overlay_dirs if (d / f"{rel}.json").exists()), None)
        return self.overlay_memo[rel]


# ----------------------------------------------------------------------------------------------- the tables
@dataclass
class Tables:
    skills: list[dict]
    missiles: dict[str, fx.Prof]
    overlays: dict[str, fx.Prof]
    states: dict[str, dict]
    d2r_missiles: dict[str, fx.Prof]
    d2r_overlays: dict[str, fx.Prof]
    d2r_states: dict[str, dict]
    d2r_skills: list[dict] = field(default_factory=list)


def load_tables(art: fx.ArtCache, excel: Path | None = None, d2r_excel: Path | None = None) -> Tables:
    excel, d2r_excel = excel or fxpaths.TABLES, d2r_excel or fxpaths.D2R_EXCEL
    mm = fx.missile_profiles(excel, "mxl", art)
    for p in mm.values():  # base-game art: D2R's copy is the one drawn (missile_looks.main does the same)
        if p.art is None and ml.is_art(p.art_name):
            p.art = art.get("d2r", "missiles", p.art_name)
    mo = fx.overlay_profiles(excel, "mxl", art)
    for p in mo.values():
        if p.art is None and is_art(p.art_name):
            p.art = art.get("d2r", "overlays", p.art_name)
    _, states = fx.table(excel / "states.txt")
    _, d2r_states = fx.table(d2r_excel / "states.txt")
    _, skills = fx.table(excel / "skills.txt")
    _, d2r_skills = fx.table(d2r_excel / "skills.txt")
    return Tables(skills=skills, missiles=mm, overlays=mo, states={s["state"].lower(): s for s in states},
                  d2r_missiles=fx.missile_profiles(d2r_excel, "d2r", art), d2r_overlays=fx.overlay_profiles(d2r_excel, "d2r", art),
                  d2r_states={s["state"].lower(): s for s in d2r_states}, d2r_skills=d2r_skills)


def reached_by(t: Tables, excel: Path) -> dict[str, set[str]]:
    """skill name (lowercase) -> who can use it: class:<code>, monster, item."""
    reach: dict[str, set[str]] = defaultdict(set)
    ids, names = {}, set()
    for s in t.skills:
        name = s["skill"].lower()
        names.add(name)
        if s.get("charclass"):
            reach[name].add("class:" + s["charclass"].lower())
        if s.get("*Id", "").isdigit():
            ids[s["*Id"]] = name
    _, mons = fx.table(excel / "monstats.txt")
    for mon in mons:
        for i in range(1, 9):
            v = mon.get(f"Skill{i}", "").lower()
            if v:
                reach[v].add("monster")
    kinds = isa.kinds_and_stats() if (excel / "properties.txt").exists() else {}
    for tb in ITEM_TABLES:
        path = excel / f"{tb}.txt"
        if not path.exists():
            continue
        rows = isa.read(str(path))
        if not rows:
            continue
        cols = isa.groups(rows[0])
        for r in rows[1:]:
            for code_i, par_i, min_i, max_i in cols:
                code = r[code_i] if code_i < len(r) else ""
                kind = kinds.get(code, ("", ""))[0]
                if kind not in ("skill", "skill-range"):
                    continue
                cells = [r[i] for i in (par_i, min_i, max_i) if i is not None and i < len(r) and r[i]]
                for c in (cells[:1] if kind == "skill" else cells):
                    if c in ids:
                        reach[ids[c]].add("item")
                    elif c.lower() in names:
                        reach[c.lower()].add("item")
    return reach


# ----------------------------------------------------------------------------------------------- the walk
@dataclass
class Node:
    kind: str  # missile / overlay
    name: str
    role: str  # missile / sub / clt / explode / state / cast / progressive / ...
    group: str = ""  # the state the overlay belongs to
    status: str = "blank"  # draws / accepted / gap / blank
    code: str = ""  # gap: a CODES key; accepted: why
    model: str = ""
    art: str = ""


@dataclass
class Chain:
    skill: str
    nodes: list[Node] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    summons: bool = False
    status: str = ""

    @property
    def gaps(self) -> list[Node]:
        return [n for n in self.nodes if n.status == "gap"]

    def signature(self) -> str:
        """What the player sees: the same set of HD pictures reads the same on screen (one cast per signature in game)."""
        return "|".join(sorted({f"{n.kind[0]}:{n.model}" for n in self.nodes if n.status == "draws" and n.model}))


def walk(skill: dict, t: Tables) -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """The names a skill's chain reaches: [(kind, name, role, state)], and the names that are in no table."""
    out: dict[tuple[str, str], tuple[str, str]] = {}
    missing: list[str] = []

    def add_overlay(name: str, role: str, group: str = ""):
        k = ("overlay", name.lower())
        if k not in out or (out[k][1] == "" and group):
            out[k] = (role, group)

    todo: list[tuple[str, str]] = [(skill[c].lower(), "missile") for c in SKILL_MISSILES if skill.get(c)]
    for c in SKILL_OVERLAYS:
        if skill.get(c):
            add_overlay(skill[c], "cast" if c in ("castoverlay", "ItemCastOverlay") else c)
    seen_states = set()
    for s in [skill[c].lower() for c in SKILL_STATES if skill.get(c)]:
        if s in seen_states:
            continue
        seen_states.add(s)
        row = t.states.get(s)
        if row is None:
            missing.append(f"state {s}")
            continue
        for oc in STATE_OVERLAYS:
            if row.get(oc):
                add_overlay(row[oc], "cast" if oc in ("castoverlay", "removerlay") else "state", s)
        if row.get("missile"):
            todo.append((row["missile"].lower(), "state"))
    while todo:
        m, role = todo.pop()
        if ("missile", m) in out:
            continue
        out[("missile", m)] = (role, "")
        p = t.missiles.get(m)
        if p is None:
            missing.append(f"missile {m}")
            continue
        for c in MISSILE_NEXT:
            if p.row.get(c):
                todo.append((p.row[c].lower(), "explode" if c == "ExplosionMissile" else "clt" if c.startswith("Clt") else "sub"))
        if p.row.get("ProgOverlay"):
            add_overlay(p.row["ProgOverlay"], "progressive")
    return [(k[0], k[1], r[0], r[1]) for k, r in out.items()], missing


# ----------------------------------------------------------------------------------------------- classification
class Scan:
    """Node and skill classification against one state of the HD files."""

    def __init__(self, t: Tables, hd: Hd, picks_arts: frozenset = frozenset(), tinted: dict | None = None, d2r_map: dict | None = None):
        self.t, self.hd = t, hd
        self.hand_arts = picks_arts
        self.tinted = tinted or {}
        self.d2r_map = d2r_map = fx.load_json(fx.HDM / "missiles.json") if d2r_map is None else d2r_map
        self.lib = ml.learn_d2r(t.d2r_missiles, d2r_map, hd.models)
        self.usable = ml.usable_for(self.lib)
        self.carried = ml.carried_pieces(t.missiles)
        self.own_m = frozenset(n for n, p in t.missiles.items() if n in t.d2r_missiles and t.d2r_missiles[n].art_name == p.art_name
                               and d2r_map.get(fx.norm_key(n)) == hd.model_of(n))

    def gap_code(self, cur) -> str:
        if cur in (None, "", "null"):
            return "null"
        return "no_def" if self.hd.models.get(cur) is None else "stub"

    def missile(self, name: str, role: str) -> Node:
        node = Node("missile", name, role)
        p = self.t.missiles.get(name)
        if p is None:
            return node
        art, art_name = ml.legacy_picture(p, self.t.missiles)
        if art is None:
            return node
        node.art = art_name
        kind = ml.needs(p)
        carrier = not (p.art and ml.is_art(p.art_name))
        if carrier and kind != "flight":  # a logic row that does not travel: its pieces are nodes of their own
            return node
        cur = self.hd.model_of(name)
        node.model = cur if isinstance(cur, str) else ""
        model_ok = self.hd.models.draws(cur)
        origin = ml.origin(cur, self.tinted)
        hand = ml.picked(art_name, name, self.hand_arts)
        if hand or name in self.own_m:
            node.status, node.code = ("draws", "") if model_ok else ("accepted", "hand pick" if hand else "D2R's own row")
        elif kind == "flight":
            good = model_ok and ml.travels(self.usable.get(origin))
            node.status = "draws" if good else "gap"
            node.code = "" if good else "play_once" if model_ok else self.gap_code(cur)
        elif kind == "trail" and name in self.carried and not model_ok:
            node.status, node.code = "accepted", "carried by its flying row"
        elif kind == "ground":
            good = model_ok and not ml.plays_once(self.usable.get(origin))
            node.status = "draws" if good else "gap"
            node.code = "" if good else "play_once" if model_ok else self.gap_code(cur)
        else:
            node.status, node.code = ("draws", "") if model_ok else ("gap", self.gap_code(cur))
        return node

    def overlay(self, name: str, role: str, group: str, skill: str = "") -> Node:
        node = Node("overlay", name, role, group)
        p = self.t.overlays.get(name)
        if p is None or not is_art(p.art_name) or p.art is None:  # no row, no art, or art that exists nowhere: nothing in legacy either
            return node
        node.art = p.art_name
        folder = p.row.get("Character", "") or "common"
        d = self.hd.overlay_definition(folder, name)
        node.model = f"{folder.lower()}/{fx.norm_key(name)}" if d else ""
        own = name in self.t.d2r_overlays and self.t.d2r_overlays[name].art_name == p.art_name
        if d is None:
            node.status, node.code = ("accepted", "D2R's own row, no HD definition") if own else ("gap", "no_overlay")
        elif definition_draws(d, skill):
            node.status = "draws"
        elif named_only(d):
            node.status, node.code = "gap", "filtered"
        else:
            if ml.picked(p.art_name, name, self.hand_arts):
                node.status, node.code = "accepted", "hand pick"
            elif own:
                node.status, node.code = "accepted", "D2R's own stub"
            else:
                node.status, node.code = "gap", "stub"
        return node

    def chain(self, skill: dict) -> Chain:
        items, missing = walk(skill, self.t)
        c = Chain(skill["skill"], missing=missing, summons=bool(skill.get("summon")))
        c.nodes = [self.missile(n, r) if k == "missile" else self.overlay(n, r, g, skill["skill"]) for k, n, r, g in items]
        # D2R merged pairs of a state's overlays into one definition: the state shows when one of them draws
        by_state: dict[str, list[Node]] = defaultdict(list)
        for n in c.nodes:
            if n.group:
                by_state[n.group].append(n)
        for nodes in by_state.values():
            if any(x.status == "draws" for x in nodes):
                for x in nodes:
                    if x.status == "gap" and x.code in ("stub", "no_overlay"):
                        x.status, x.code = "accepted", "another overlay of the state draws"
        legacy = [n for n in c.nodes if n.status != "blank"]
        draws = any(n.status == "draws" for n in c.nodes)
        if not legacy:
            c.status = "not visual"
        elif not draws:  # a chain of accepted stubs still ends in nothing
            for n in legacy:
                if n.status == "accepted" and n.kind == "overlay":
                    n.status, n.code = "gap", "stub"
            c.status = "invisible"
        else:
            c.status = "partial" if c.gaps else "ok"
        return c

    def run(self) -> dict[str, Chain]:
        return {s["skill"]: self.chain(s) for s in self.t.skills}


# ----------------------------------------------------------------------------------------------- repairs
LOOP_COLS = ("overlay1", "overlay2", "overlay3", "overlay4", "pgsvoverlay")
FOLDERS = ("amazon", "assassin", "barbarian", "common", "druid", "item", "monster", "necro", "npcs", "object", "objects", "paladin", "sorceress", "test", "warlock")


def overlay_library(t: Tables) -> tuple[list[fx.Prof], set[str]]:
    """D2R's overlay rows whose definition draws (the candidates) and the names a vanilla state loops."""
    lib = []
    for p in t.d2r_overlays.values():
        key = fx.norm_key(p.name)
        path = fx.HDO / p.folder.lower() / f"{key}.json"
        if p.art and is_art(p.art_name) and path.exists() and definition_draws(fx.load_json(path)):
            lib.append(p)
    return lib, {s[c].lower() for s in t.d2r_states.values() for c in LOOP_COLS if s.get(c)}


def choose_overlay(p: fx.Prof, state_row: bool, lib: list[fx.Prof], loops: set[str]) -> tuple[fx.Prof, float, list[str]]:
    """The closest D2R overlay of the role (loop or one-shot): the same scoring as an overlay stand-in in effects_hd.py."""
    cands = [c for c in lib if (c.name.lower() in loops) == state_row] or lib
    c, sc, _margin, parts = fx.pick(p, cands, False)
    return c, sc, parts


def fix_overlays(scan: Scan, chains: dict[str, Chain], out: Path) -> list[dict]:
    """A D2R overlay that draws for every overlay row that gaps in some skill: the closest of its role (a state's looping overlay vs a cast flash)."""
    need: dict[str, dict] = {}
    for chain in chains.values():
        for n in chain.gaps:
            if n.kind == "overlay":
                r = need.setdefault(n.name, {"code": n.code, "state": False, "skills": []})
                r["state"] = r["state"] or n.role == "state"
                r["skills"].append(chain.skill)
    lib, loops = overlay_library(scan.t)
    decisions = []
    for name, info in sorted(need.items()):
        p = scan.t.overlays[name]
        if not (p.art and is_art(p.art_name)):
            continue
        c, sc, parts = choose_overlay(p, info["state"], lib, loops)
        scale = fx.scale_for(p, c)
        folder = p.row.get("Character", "").lower()
        if folder not in FOLDERS:
            folder = "common"
        key = fx.norm_key(name)
        d = fx.scaled_definition(fx.load_json(fx.HDO / c.folder.lower() / f"{fx.norm_key(c.name)}.json"), key, scale)
        fx.write_json(out / "hd" / "overlays" / folder / f"{key}.json", d)
        scan.hd.overlay_memo[f"{folder}/{key}"] = d
        close = fx.colour_dist(p.art, c.art) < 0.25 or bool(p.words_tags()[0] & c.words_tags()[0])
        decisions.append(dict(name=name, folder=folder, code=info["code"], like=c.name, effect=f"{c.folder.lower()}/{fx.norm_key(c.name)}", scale=scale,
                              role="state" if info["state"] else "cast", art=p.art_name, cost=round(sc, 1), why=", ".join(parts), skills=sorted(set(info["skills"])), close=close))
        p.row["Character"] = folder  # D2R reads the Character column: the table must say the folder (only differs for a row marked `all`)
    return decisions


def write_character_column(excel: Path, rows: dict[str, str]) -> int:
    """overlay.txt Character = the folder, for the rows that changed (both banks)."""
    n = 0
    for f in (excel / "overlay.txt", excel / "base" / "overlay.txt"):
        if not f.exists():
            continue
        text = f.read_bytes().decode("latin-1")
        nl = fx.CRLF if fx.CRLF in text[:4096] else fx.LF
        h, data = fx.read_tsv(f)
        ci, ni = h.index("Character"), h.index("overlay")
        for r in data:
            want = rows.get(r[ni].lower())
            if want is not None and r[ci] != want:
                r[ci] = want
                n += 1
        f.write_bytes((nl.join(fx.TAB.join(x) for x in [h] + data) + nl).encode("latin-1"))
    return n


# ----------------------------------------------------------------------------------------------- report
HAND_FILE = "skill_looks.md"
TSV_FILE = "skill_looks.tsv"
SUMMARY_FILE = "skill_looks.json"


def status_counts(chains: dict[str, Chain]) -> Counter:
    return Counter(c.status for c in chains.values())


def who_label(names: set[str]) -> str:
    classes = sorted(x.split(":", 1)[1] for x in names if x.startswith("class:"))
    return "+".join(([f"{'/'.join(classes)}"] if classes else []) + [x for x in ("item", "monster") if x in names]) or "nobody"


def final_status(before: Chain, after: Chain) -> str:
    """The report's words: ok / fixed / hand / not visual."""
    if after.status == "not visual":
        return "not visual"
    if after.status == "ok":
        return "fixed" if before.status in ("partial", "invisible") else "ok"
    return "hand"


def weak_rows(work: Path, overlay_fixes: list[dict]) -> set[str]:
    """Rows that draw but only on a stand-in without a close match (colour and element): hand work and recolouring want them."""
    weak = {d["name"] for d in overlay_fixes if not d.get("close", True)}
    f = work / "missile_looks.json"
    if f.exists():
        weak |= {d["name"] for d in fx.load_json(f) if d["action"] == "hand" or (d["action"] == "new" and not d.get("close", True))}
    return weak


def only_weak(c: Chain, weak: set[str]) -> bool:
    """Everything that draws is a stand-in without a close match (and at least one thing draws)."""
    drawn = [x for x in c.nodes if x.status == "draws"]
    return bool(drawn) and all(x.name in weak for x in drawn)


def report(work: Path, t: Tables, before: dict[str, Chain], after: dict[str, Chain], reach: dict[str, set[str]], overlay_fixes: list[dict], missile_note: str) -> dict:
    weak = weak_rows(work, overlay_fixes)
    words = {n: "hand" if after[n].status == "ok" and only_weak(after[n], weak) else final_status(before[n], after[n]) for n in after}
    counts = Counter(words.values())
    rows = sorted(after, key=lambda n: ({"hand": 0, "fixed": 1, "ok": 2, "not visual": 3}[words[n]], n))
    ids = {s["skill"]: s.get("*Id", "") for s in t.skills}
    tsv = ["\t".join(("id", "skill", "who", "status", "scan before", "scan now", "legacy nodes", "hd nodes", "signature", "gaps", "accepted", "weak"))]
    for n in rows:
        c = after[n]
        legacy = [x for x in c.nodes if x.status != "blank"]
        tsv.append("\t".join((ids.get(n, ""), n, who_label(reach.get(n.lower(), set())), words[n], before[n].status, c.status, str(len(legacy)),
                              str(sum(1 for x in c.nodes if x.status == "draws")), c.signature(),
                              "; ".join(f"{x.kind[0]}:{x.name}={x.code}" for x in c.gaps),
                              "; ".join(f"{x.kind[0]}:{x.name}={x.code}" for x in c.nodes if x.status == "accepted"),
                              ", ".join(sorted(x.name for x in c.nodes if x.status == "draws" and x.name in weak)))))
    (work / TSV_FILE).write_text("\n".join(tsv) + "\n", encoding="utf-8")
    who = Counter((words[n], "class" if any(x.startswith("class") for x in reach.get(n.lower(), set())) else "item" if "item" in reach.get(n.lower(), set())
                   else "monster" if "monster" in reach.get(n.lower(), set()) else "nobody") for n in after)
    hand = [n for n in rows if words[n] == "hand"]
    md = ["# Every skill's visual chain in HD (tools/skill_looks.py)", "",
          f"{len(after)} skills: " + ", ".join(f"{k} {counts[k]}" for k in ("ok", "fixed", "hand", "not visual")) + ".",
          "By who has the skill: " + ", ".join(f"{a} {b}={c}" for (a, b), c in sorted(who.items())) + ".",
          missile_note, f"Overlays given a picture here: {len(overlay_fixes)}.", ""]
    md += ["## Skills that still need hand work", "", "| Skill | Who | Now | Gaps |", "|-|-|-|-|"]
    for n in hand:
        c = after[n]
        md.append(f"| {n} | {who_label(reach.get(n.lower(), set()))} | {c.status} | " + "; ".join(f"{x.kind[0]}:{x.name} ({x.code}, {x.model})" for x in c.gaps) + " |")
    md += ["", "## Stand-ins without a close match (they draw; hand work or recolouring wants them)", "", "| Row | Skills that reach it |", "|-|-|"]
    for row in sorted(weak):
        users = sorted(n for n, c in after.items() if any(x.name == row and x.status == "draws" for x in c.nodes))
        if users:
            md.append(f"| {row} | {', '.join(users[:8])}{' ...' if len(users) > 8 else ''} |")
    md += ["", "## Overlays given a picture", "", "| Row | Folder | Legacy art | Why | Role | Effect | Scale | Like D2R | Skills |", "|-|-|-|-|-|-|-|-|-|"]
    for d in overlay_fixes:
        md.append(f"| {d['name']} | {d['folder']} | {d['art']} | {d['code']} | {d['role']} | {d['effect']} | {d['scale']} | {d['like']} | {', '.join(d['skills'][:6])} |")
    (work / HAND_FILE).write_text("\n".join(md) + "\n", encoding="utf-8")
    summary = {"counts": dict(counts), "who": {f"{a}/{b}": c for (a, b), c in who.items()}, "hand": hand, "overlay_fixes": len(overlay_fixes), "statuses": words}
    (work / SUMMARY_FILE).write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


# ----------------------------------------------------------------------------------------------- main
def load_context(work: Path):
    art = fx.ArtCache(fxpaths.WORK / "effects_hd_art.json")
    t = load_tables(art)
    hand = fx.picked_names(fx.load_picks(fxpaths.PICKS_TSV))
    report_file = work / "hd_recolour.json"
    recolours = fx.load_json(report_file).get("recolours", []) if report_file.exists() else []
    tinted = {r["to"]: r["from"] for r in recolours if r.get("kind") == "missile"}
    return art, t, hand, tinted


def invisible_reached(chains: dict[str, Chain], reach: dict[str, set[str]]) -> list[str]:
    """Skills somebody can use that draw in legacy and nothing in HD."""
    return sorted(n for n, c in chains.items() if c.status == "invisible" and reach.get(n.lower()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", default=str(fxpaths.MOD))
    ap.add_argument("--check", action="store_true", help="audit only: exit 1 when a skill somebody can use ends in nothing in HD")
    ap.add_argument("--no-fix", action="store_true", help="scan and report without repairing overlays")
    ap.add_argument("--baseline", help="an earlier missiles.json: `fixed` also covers what that map still had wrong")
    args = ap.parse_args()
    work = Path(args.work)
    out = work / "data"
    art, t, hand, tinted = load_context(work)
    reach = reached_by(t, fxpaths.TABLES)
    before_file = Path(args.baseline) if args.baseline else work / "missiles_before_looks.json"
    baseline = fx.load_json(before_file) if before_file.exists() else None
    if args.check:
        chains = Scan(t, Hd(out), hand, tinted).run()
        bad = invisible_reached(chains, reach)
        print(f"skills: {dict(status_counts(chains))}; {len(bad)} skills somebody can use draw in legacy and nothing in HD")
        print("\n".join(bad[:60]))
        return 1 if bad else 0
    before = Scan(t, Hd(out, current=baseline), hand, tinted).run()  # the state to compare with: effects_hd.py's map when the build left a copy
    scan = Scan(t, Hd(out), hand, tinted)
    chains = scan.run()
    fixes = [] if args.no_fix else fix_overlays(scan, chains, out)
    if fixes:
        write_character_column(fxpaths.TABLES, {d["name"]: d["folder"] for d in fixes})
        chains = Scan(t, Hd(out), hand, tinted).run()
    summary = report(work, t, before, chains, reach, fixes, "Missile rows: tools/missile_looks.py (work/mod/missile_looks.md).")
    art.save()
    print(f"skill_looks: {dict(status_counts(chains))}; overlays given a picture: {len(fixes)}; report -> {work / HAND_FILE}")
    print(f"statuses: {dict(summary['counts'])}; hand work: {len(summary['hand'])} skills")
    bad = invisible_reached(chains, reach)
    if bad:
        print(f"invisible (somebody can use them): {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
