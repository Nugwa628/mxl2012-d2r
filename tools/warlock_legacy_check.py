"""Warlock in D2R's classic graphics mode (G / Alt+G): every classic file the game can load for a Warlock in this mod, and
whether it is there (docs/legacy-graphics.md section 8 "Warlock in classic mode", docs/bugs.md #498).

D2R blocks the legacy toggle in Reign of the Warlock games; D2RLoader's `always_enable_rotw_legacy_graphics_keybind` lifts the
block. In classic mode the 1.14 renderer then draws the Warlock and everything it makes from the original formats, looked up
in the mod first (work/mod/data/global/...), then in D2R's own CASC (docs/legacy-graphics.md section 1). A file that is in
neither, or a table index past the end of the file it points into, is the likely crash. Sections:

  char     plrtype token; every chars/<ref>/ file (the Necromancer: D2R's Warlock COFs are byte copies of its) has its
           chars/<tok>/ twin; every Warlock COF parses, each layer DCC has the COF's directions and at least its frames,
           and its animdata.d2 record (the merged one of the build) has the COF's frame count
  items    the character graphics of every weapon / armour visual code (alternategfx) Median's items can put on a layer,
           per weapon class; a code missing for the Warlock *and* the reference class is listed as `same-as-ref` (the
           game draws nothing for that layer, as for the reference class, game-checked in classic for the classic classes)
  skills   the Warlock's skills (skills.txt charclass `war`, RotW bank), their missiles (CelFile, closure over SubMissile*,
           HitSubMissile*, Clt*, ExplosionMissile), overlays (skill, state and missile ProgOverlay columns), states and
           summons (monstats Code + monstats2 modes / parts, the summons' own skills followed the same way)
  ui       the classic skill tree layout (the mod's served skillstreepanel.json, else D2R's): the per-class arrays have a
           Warlock entry, the icon sheet and tree back it names exist, every Warlock IconCel (+1, the pressed frame) is
           inside the sheet, SkillRow / SkillColumn inside the layout's grid; inventory.txt Warlock / Warlock2 rows
  kit      the Warlock's starting items (charstats item1-10): inventory and flippy DC6, and the hand graphics of the weapon

  py -3 -I tools/warlock_legacy_check.py [--mod DIR] [--d2r DIR] [--ref ne] [--all] [--notes] [--json FILE]
--mod is the built mod's data folder (default work/mod/data, tools/build.py), --d2r a D2R 93847 extraction (fxpaths.D2R).
Prints the table (missing / out-of-range rows always, noted ones with --notes, found ones with --all) and the counts;
exit 1 when anything is missing or out of range.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
from dc6 import parse_dc6  # noqa: E402
from legacy_art import anim_frames, parse_cof, parse_dcc  # noqa: E402

CLASS = "Warlock"
CHARCLASS = "war"
CLASS_INDEX = 7  # playerclass row: the per-class arrays of the classic layouts are indexed by it
MONSTER_MODES = ("dt", "nu", "wl", "gh", "a1", "a2", "bl", "sc", "s1", "s2", "s3", "s4", "dd", "kb", "sq", "rn")
SKILL_MISSILES = ("srvmissile", "srvmissilea", "srvmissileb", "srvmissilec", "cltmissile", "cltmissilea", "cltmissileb",
                  "cltmissilec", "cltmissiled")
SKILL_OVERLAYS = ("srvoverlay", "castoverlay", "tgtoverlay", "prgoverlay", "cltoverlaya", "cltoverlayb", "sumoverlay",
                  "itemcastoverlay")
SKILL_STATES = ("aurastate", "auratargetstate", "passivestate", "state1", "state2", "state3")
MISSILE_CHILDREN = ("explosionmissile", "submissile1", "submissile2", "submissile3", "hitsubmissile1", "hitsubmissile2",
                    "hitsubmissile3", "hitsubmissile4", "cltsubmissile1", "cltsubmissile2", "cltsubmissile3",
                    "clthitsubmissile1", "clthitsubmissile2", "clthitsubmissile3", "clthitsubmissile4")
STATE_OVERLAYS = ("overlay1", "overlay2", "overlay3", "overlay4", "pgsvoverlay", "castoverlay", "removerlay")
TREE_ARRAYS = ("skillButtonFile", "skillBackgroundFile", "textTab0", "textTab1", "textTab2", "cancelPositionCode")
HAND_OF = {"bow": "lh"}  # the weapon layer a weapon class draws on (bows sit in the left hand, everything else the right)


@dataclass
class Row:
    file: str          # path below data/ (lower case), or a table cell for index rows
    needed_by: str
    found: str         # mod | base | MISSING | same-as-ref | not-drawn | n/a
    problem: str = ""  # index out of range / mismatch that can crash; empty = fine
    note: str = ""     # a mismatch D2R / 1.14 tolerates (the same shape occurs in rows game-checked in classic)


class View:
    """The files classic mode can read: the built mod's data folder first, then D2R's (filelist.txt names)."""

    def __init__(self, mod: Path, d2r: Path):
        self.mod, self.d2r = Path(mod), Path(d2r)
        g = self.mod / "global"
        self.mod_files = {p.relative_to(self.mod).as_posix().lower(): p for p in g.rglob("*") if p.is_file()} \
            if g.exists() else {}
        self.base_files: set[str] = set()
        fl = self.d2r / "filelist.txt"
        if fl.exists():
            for line in fl.read_text("utf-8").splitlines():
                if line.startswith("data:data/"):
                    self.base_files.add(line[len("data:data/"):].lower())
        elif (self.d2r / "data").exists():
            self.base_files = {p.relative_to(self.d2r / "data").as_posix().lower()
                               for p in (self.d2r / "data").rglob("*") if p.is_file()}
        self._cache: dict[str, bytes | None] = {}

    def where(self, rel: str) -> str:
        rel = rel.lower()
        return "mod" if rel in self.mod_files else "base" if rel in self.base_files else "MISSING"

    def read(self, rel: str) -> bytes | None:
        rel = rel.lower()
        if rel not in self._cache:
            p = self.mod_files.get(rel) or (self.d2r / "data" / rel)
            self._cache[rel] = p.read_bytes() if p.is_file() else None
        return self._cache[rel]

    def names(self, prefix: str) -> set[str]:
        return {f for f in (*self.mod_files, *self.base_files) if f.startswith(prefix)}


def read_table(path: Path) -> list[dict[str, str]]:
    """A tab table as dicts with lower-case column names (the first of a duplicated name wins)."""
    with open(path, encoding="latin-1", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    head = [h.strip().lower() for h in rows[0]]
    out = []
    for r in rows[1:]:
        d: dict[str, str] = {}
        for k, v in zip(head, r):
            d.setdefault(k, v.strip())
        out.append(d)
    return out


class Tables:
    def __init__(self, excel: Path):
        self.excel = Path(excel)
        self._t: dict[str, list[dict[str, str]]] = {}

    def __getitem__(self, name: str) -> list[dict[str, str]]:
        if name not in self._t:
            p = self.excel / f"{name}.txt"
            self._t[name] = read_table(p) if p.exists() else []
        return self._t[name]

    def by(self, name: str, key: str) -> dict[str, dict[str, str]]:
        return {r[key].lower(): r for r in self[name] if r.get(key)}


def _int(v: str | None, default: int = 0) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _art(name: str) -> str:
    return re.sub(r"[\\/]+", "/", name.strip()).lower()


# --- character ----------------------------------------------------------------------------------------------------------

def class_token(t: Tables, cls: str = CLASS) -> str:
    for r in t["plrtype"]:
        if r.get("name", "").lower() == cls.lower():
            return r.get("token", "").lower()
    return ""


def check_char(view: View, tok: str, ref: str, frames: dict[str, int] | None) -> list[Row]:
    rows: list[Row] = []
    if not tok:
        return [Row("excel/plrtype.txt", f"{CLASS} row Token", "MISSING", "no plrtype row / token for the class")]
    rows.append(Row("excel/plrtype.txt", f"{CLASS} Token {tok.upper()}", "mod" if view.where(
        "global/excel/plrtype.txt") == "mod" else "base"))
    base, refbase = f"global/chars/{tok}/", f"global/chars/{ref}/"
    own = view.names(base)
    for f in sorted(view.names(refbase)):
        parts = f[len(refbase):].split("/")
        if parts[-1].startswith(ref):
            parts[-1] = tok + parts[-1][len(ref):]
        twin = base + "/".join(parts)
        if twin not in own:
            rows.append(Row(twin, f"twin of {f} (reference class {ref})", "MISSING"))
    for cof in sorted(f for f in own if f.startswith(base + "cof/") and f.endswith(".cof")):
        name = cof.rsplit("/", 1)[1][:-4]
        mode, wc = name[len(tok):len(tok) + 2], name[len(tok) + 2:]
        try:
            c = parse_cof(view.read(cof) or b"")
        except ValueError as e:
            rows.append(Row(cof, "character COF", view.where(cof), f"does not parse: {e}"))
            continue
        prob, note = [], ""
        fr = frames.get(name.upper()) if frames is not None else None
        if frames is not None and fr is None:
            prob.append("no animdata.d2 record")
        elif fr is not None and fr > c["frames"]:
            prob.append(f"animdata {fr} frames > COF {c['frames']}: the last frame index runs past the art")
        elif fr is not None and fr < c["frames"]:
            note = f"animdata {fr} frames < COF {c['frames']}: the animation ends early"
        for comp, lwc in c["layers"]:
            for dcc in sorted(f for f in own if f.startswith(f"{base}{comp}/{tok}{comp}") and f.endswith(
                    f"{mode}{lwc}.dcc") and len(f.rsplit("/", 1)[1]) == len(f"{tok}{comp}xxx{mode}{lwc}.dcc")):
                try:
                    d = parse_dcc(view.read(dcc) or b"")
                except ValueError as e:
                    rows.append(Row(dcc, f"layer {comp} of {name}", view.where(dcc), f"not a DCC: {e}"))
                    continue
                if d["dirs"] != c["dirs"] or d["frames"] < c["frames"]:
                    rows.append(Row(dcc, f"layer {comp} of {name}", view.where(dcc),
                                    f"DCC {d['dirs']} dirs x {d['frames']} frames, COF {c['dirs']} x {c['frames']}"
                                    ))
        rows.append(Row(cof, f"character mode {mode.upper()} {wc}", view.where(cof), "; ".join(prob), note))
    return rows


def item_visuals(t: Tables) -> list[tuple[str, str, str, str]]:
    """(item code, layer, visual code, weapon class or '') of every weapon / shield / helm Median's tables have."""
    out = []
    types = t.by("itemtypes", "code")

    def body(code: str) -> str:
        seen = set()
        while code and code not in seen:
            seen.add(code)
            r = types.get(code)
            if not r:
                return ""
            bl = (r.get("bodyloc1") or "").lower()
            if bl in ("head", "rarm", "larm"):
                return bl
            code = (r.get("equiv1") or "").lower()
        return ""

    for r in t["weapons"]:
        gfx = (r.get("alternategfx") or r.get("code") or "").lower()
        for wc in {(r.get("wclass") or "").lower(), (r.get("2handedwclass") or "").lower()} - {""}:
            out.append((r.get("code", ""), HAND_OF.get(wc, "rh"), gfx, wc))
    for r in t["armor"]:
        loc = body((r.get("type") or "").lower())
        gfx = (r.get("alternategfx") or r.get("code") or "").lower()
        if loc == "head":
            out.append((r.get("code", ""), "hd", gfx, ""))
        elif loc in ("rarm", "larm"):
            out.append((r.get("code", ""), "sh", gfx, ""))
    return out


def check_items(view: View, t: Tables, tok: str, ref: str) -> list[Row]:
    rows, seen = [], set()
    for code, comp, gfx, wc in item_visuals(t):
        key = (comp, gfx, wc)
        if not gfx or key in seen:
            continue
        seen.add(key)
        mode_wc = f"nu{wc}" if wc else "nuhth"
        rel = f"global/chars/{tok}/{comp}/{tok}{comp}{gfx}{mode_wc}.dcc"
        where = view.where(rel)
        if where == "MISSING":
            refrel = f"global/chars/{ref}/{comp}/{ref}{comp}{gfx}{mode_wc}.dcc"
            where = "same-as-ref" if view.where(refrel) == "MISSING" else "MISSING"
        rows.append(Row(rel, f"item {code} ({comp} {gfx} {wc or 'hth'})", where))
    return rows


# --- skills, missiles, overlays, states, summons ------------------------------------------------------------------------

class Closure:
    """Follows a set of skills to every missile, overlay, state and summoned monster they reach."""

    def __init__(self, view: View, t: Tables, frames: dict[str, int] | None):
        self.view, self.t, self.frames = view, t, frames
        self.skills = t.by("skills", "skill")
        self.missiles = t.by("missiles", "missile")
        self.overlays = t.by("overlay", "overlay")
        self.states = t.by("states", "state")
        self.monstats = t.by("monstats", "id")
        self.monstats2 = t.by("monstats2", "id")
        self.rows: list[Row] = []
        self.done: set[tuple[str, str]] = set()

    def _once(self, kind: str, name: str) -> bool:
        k = (kind, name.lower())
        if not name or name.lower() in ("", "0", "xx", "none") or k in self.done:
            return False
        self.done.add(k)
        return True

    def skill(self, name: str, by: str) -> None:
        if not self._once("skill", name):
            return
        r = self.skills.get(name.lower())
        if r is None:
            self.rows.append(Row(f"excel/skills.txt:{name}", by, "MISSING", "skill row not found"))
            return
        who = f"skill {r.get('skill')} ({r.get('*id') or r.get('id', '')})"
        for c in SKILL_MISSILES:
            self.missile(r.get(c, ""), f"{who} {c}")
        for c in SKILL_OVERLAYS:
            self.overlay(r.get(c, ""), f"{who} {c}")
        for c in SKILL_STATES:
            self.state(r.get(c, ""), f"{who} {c}")
        if r.get("summon"):
            self.monster(r["summon"], f"{who} summon")

    def missile(self, name: str, by: str) -> None:
        if not self._once("missile", name):
            return
        r = self.missiles.get(name.lower())
        if r is None:
            self.rows.append(Row(f"excel/missiles.txt:{name}", by, "MISSING", "missile row not found"))
            return
        cel = _art(r.get("celfile", ""))
        if cel:
            rel = f"global/missiles/{cel}.dcc"
            where, prob, note = self.view.where(rel), "", ""
            if where != "MISSING":
                try:
                    note = missile_index_note(r, parse_dcc(self.view.read(rel) or b""))
                except ValueError as e:
                    prob = f"not a DCC: {e}"
            self.rows.append(Row(rel, f"missile {name} ({by})", where, prob, note if where != "MISSING" else ""))
        for c in MISSILE_CHILDREN:
            self.missile(r.get(c, ""), f"missile {name} {c}")
        self.overlay(r.get("progoverlay", ""), f"missile {name} ProgOverlay")

    def overlay(self, name: str, by: str) -> None:
        if not self._once("overlay", name):
            return
        r = self.overlays.get(name.lower())
        if r is None:
            self.rows.append(Row(f"excel/overlay.txt:{name}", by, "MISSING", "overlay row not found"))
            return
        fn = _art(r.get("filename", ""))
        if not fn:
            return
        rel = f"global/overlays/{fn}.dcc"
        where, prob, note = self.view.where(rel), "", ""
        if where != "MISSING":
            try:
                d = parse_dcc(self.view.read(rel) or b"")
                nd = _int(r.get("numdirections"), 0)
                if nd > d["dirs"]:
                    note = f"NumDirections {nd} > DCC directions {d['dirs']}"
            except ValueError as e:
                prob = f"not a DCC: {e}"
        self.rows.append(Row(rel, f"overlay {name} ({by})", where, prob, note))

    def state(self, name: str, by: str) -> None:
        if not self._once("state", name):
            return
        r = self.states.get(name.lower())
        if r is None:
            self.rows.append(Row(f"excel/states.txt:{name}", by, "MISSING", "state row not found"))
            return
        for c in STATE_OVERLAYS:
            self.overlay(r.get(c, ""), f"state {name} {c}")
        self.missile(r.get("missile", ""), f"state {name} missile")

    def monster(self, mid: str, by: str) -> None:
        if not self._once("monster", mid):
            return
        r = self.monstats.get(mid.lower())
        if r is None:
            self.rows.append(Row(f"excel/monstats.txt:{mid}", by, "MISSING", "monstats row not found"))
            return
        tok = r.get("code", "").lower()
        r2 = self.monstats2.get((r.get("monstatsex") or mid).lower())
        if not tok or r2 is None:
            self.rows.append(Row(f"excel/monstats2.txt:{mid}", by, "MISSING", "no Code / monstats2 row"))
        else:
            self.rows.extend(monster_rows(self.view, tok, r2, f"summon {mid} ({by})", self.frames))
        for i in range(1, 9):
            self.skill(r.get(f"skill{i}", ""), f"monster {mid} Skill{i}")
        for c in ("missa1", "missa2", "misss1", "misss2", "misss3", "misss4", "missc", "misssq"):
            self.missile(r.get(c, ""), f"monster {mid} {c}")


def missile_index_note(r: dict[str, str], d: dict) -> str:
    """Table numbers past the DCC: directions and the frame columns of the animation. Notes, not crashes: 17 rows of D2R's
    classic (LoD) bank have the same (imp / catapult missiles NumDirections, Exploding Arrow's AnimLen, Throwing Star's
    SubStop) and draw in 1.14."""
    prob = []
    nd = _int(r.get("numdirections"), 1)
    if nd > d["dirs"]:
        prob.append(f"NumDirections {nd} > DCC directions {d['dirs']}")
    alen = _int(r.get("animlen"), 0)
    if alen > d["frames"]:
        prob.append(f"AnimLen {alen} > DCC frames {d['frames']}")
    if _int(r.get("subloop"), 0):
        for c in ("substart", "substop"):
            v = _int(r.get(c), 0)
            if v >= d["frames"]:
                prob.append(f"{c} {v} >= DCC frames {d['frames']}")
    return "; ".join(prob)


def monster_rows(view: View, tok: str, r2: dict[str, str], by: str, frames: dict[str, int] | None) -> list[Row]:
    """The COF of every mode the monstats2 row enables and the DCC of every COF layer and look it uses. The rules are the
    ones D2R's classic (LoD) bank shows working in 1.14: KB draws the GH COF (docs/bugs.md #3); a mode without a COF in the
    base weapon class takes the HTH one (26 vanilla DT / DD rows, goatman1 among them); SQ has no COF (a sequence plays
    other modes' frames; 482 vanilla rows set mSQ); a layer without a DCC for a look is not drawn (necroskeleton,
    shadowmaster and 60 more vanilla rows)."""
    rows, wc = [], (r2.get("basew") or "hth").lower()
    for mode in MONSTER_MODES:
        if r2.get("m" + mode, "") != "1" or mode == "sq":
            continue
        m = "gh" if mode == "kb" else mode
        cof = f"global/monsters/{tok}/cof/{tok}{m}{wc}.cof"
        cwc = wc
        if view.where(cof) == "MISSING" and view.where(f"global/monsters/{tok}/cof/{tok}{m}hth.cof") != "MISSING":
            cof, cwc = f"global/monsters/{tok}/cof/{tok}{m}hth.cof", "hth"
        where = view.where(cof)
        if where == "MISSING":
            rows.append(Row(cof, f"{by} mode {mode.upper()}", where))
            continue
        try:
            c = parse_cof(view.read(cof) or b"")
        except ValueError as e:
            rows.append(Row(cof, f"{by} mode {mode.upper()}", where, f"does not parse: {e}"))
            continue
        prob, note = "", ""
        fr = frames.get(f"{tok}{m}{cwc}".upper()) if frames is not None else None
        if frames is not None and fr is None:
            prob = "no animdata.d2 record"
        elif fr is not None and fr > c["frames"]:
            prob = f"animdata {fr} frames > COF {c['frames']}: the last frame index runs past the art"
        elif fr is not None and fr < c["frames"]:
            note = f"animdata {fr} frames < COF {c['frames']}: the animation ends early"
        rows.append(Row(cof, f"{by} mode {mode.upper()}", where, prob, note))
        for comp, lwc in c["layers"]:
            if r2.get(comp, "") != "1":
                continue
            for var in (v.strip().lower() for v in (r2.get(comp + "v") or "").split(",")):
                if not var or var == "nil":
                    continue
                stem = f"global/monsters/{tok}/{comp}/{tok}{comp}{var}{m}{lwc}"
                rel = next((f"{stem}.{x}" for x in ("dcc", "dc6") if view.where(f"{stem}.{x}") != "MISSING"), stem + ".dcc")
                w, p, n = view.where(rel), "", ""
                if w == "MISSING":
                    w, n = "not-drawn", "no DCC for this look: the layer is not drawn (as in vanilla rows)"
                elif rel.endswith(".dcc"):
                    try:
                        d = parse_dcc(view.read(rel) or b"")
                        if d["dirs"] != c["dirs"] or d["frames"] < c["frames"]:
                            p = f"DCC {d['dirs']} dirs x {d['frames']} frames, COF {c['dirs']} x {c['frames']}"
                    except ValueError as e:
                        p = f"not a DCC: {e}"
                rows.append(Row(rel, f"{by} {mode.upper()} layer {comp}", w, p, n))
    return rows


def check_skills(view: View, t: Tables, frames: dict[str, int] | None) -> list[Row]:
    cl = Closure(view, t, frames)
    for r in t["skills"]:
        if r.get("charclass", "").lower() == CHARCLASS:
            cl.skill(r["skill"], f"{CLASS} skill")
    return cl.rows


# --- UI -----------------------------------------------------------------------------------------------------------------

def layout_arrays(text: str) -> dict[str, list[str]]:
    """The flat arrays of a D2R layout file (`"name": [ a, b, ... ]`), // comments dropped, values unquoted."""
    out = {}
    for m in re.finditer(r'"(\w+)"\s*:\s*\[([^\[\]{}]*)\]', re.sub(r"//[^\n]*", "", text)):
        out.setdefault(m.group(1), [v.strip().strip('"') for v in m.group(2).split(",") if v.strip()])
    return out


def check_ui(view: View, t: Tables) -> list[Row]:
    rows = []
    lay = "global/ui/layouts/skillstreepanel.json"
    text = view.read(lay)
    if text is None:
        return [Row(lay, "classic skill tree", "MISSING")]
    arr = layout_arrays(text.decode("utf-8", "replace"))
    for a in TREE_ARRAYS:
        v = arr.get(a, [])
        rows.append(Row(f"{lay}:{a}", f"{CLASS} entry (index {CLASS_INDEX})", view.where(lay),
                        "" if len(v) > CLASS_INDEX else f"{len(v)} entries, no index {CLASS_INDEX}"))
    sheet_frames = 0
    for a in ("skillButtonFile", "skillBackgroundFile"):
        v = arr.get(a, [])
        if len(v) > CLASS_INDEX:
            rel = f"global/ui/{_art(v[CLASS_INDEX])}.dc6"
            where, prob = view.where(rel), ""
            if where != "MISSING":
                try:
                    n = len(parse_dc6(view.read(rel) or b""))
                    if a == "skillButtonFile":
                        sheet_frames = n
                    elif n < 16:
                        prob = f"{n} frames, the tree back has 16 tiles"
                except Exception as e:  # noqa: BLE001  (any parse error is the finding)
                    prob = f"not a DC6: {e}"
            rows.append(Row(rel, f"classic skill tree {a}[{CLASS_INDEX}]", where, prob))
    nrow, ncol = len(arr.get("skillRow", [])), len(arr.get("skillColumn", []))
    descs = t.by("skilldesc", "skilldesc")
    for s in t["skills"]:
        if s.get("charclass", "").lower() != CHARCLASS:
            continue
        d = descs.get((s.get("skilldesc") or "").lower())
        if d is None:
            rows.append(Row(f"excel/skilldesc.txt:{s.get('skilldesc')}", f"skill {s['skill']}", "MISSING",
                            "skilldesc row not found"))
            continue
        cel, page, row, col = (_int(d.get(k), -1) for k in ("iconcel", "skillpage", "skillrow", "skillcolumn"))
        prob = []
        if sheet_frames and not 0 <= cel < sheet_frames - 1:
            prob.append(f"IconCel {cel} (+1 pressed) outside the sheet's {sheet_frames} frames")
        if page > 0 and not (1 <= row <= nrow and 1 <= col <= ncol and 1 <= page <= 3):
            prob.append(f"page {page} row {row} column {col} outside the tree's {nrow} x {ncol}")
        rows.append(Row(f"excel/skilldesc.txt:{d['skilldesc']}", f"skill {s['skill']} IconCel {cel}", "n/a",
                        "; ".join(prob)))
    inv = t.by("inventory", "class")
    ama = inv.get("amazon", {})
    for name in (CLASS, CLASS + "2"):
        r = inv.get(name.lower())
        if r is None:
            rows.append(Row(f"excel/inventory.txt:{name}", "classic inventory panel", "MISSING", "no row"))
            continue
        diff = [k for k in ("gridx", "gridy", "gridleft", "gridtop") if ama and r.get(k) != inv.get(
            "amazon" + ("2" if name.endswith("2") else ""), ama).get(k)]
        rows.append(Row(f"excel/inventory.txt:{name}", "classic inventory panel", "n/a",
                        f"grid differs from Amazon's in {diff}" if diff else ""))
    for panel in ("global/ui/panel/invchar6.dc6",):
        rows.append(Row(panel, "classic inventory panel (shared by all classes)", view.where(panel)))
    return rows


# --- starting kit -------------------------------------------------------------------------------------------------------

def check_kit(view: View, t: Tables, tok: str) -> list[Row]:
    rows = []
    cs = next((r for r in t["charstats"] if r.get("class", "").lower() == CLASS.lower()), None)
    if cs is None:
        return [Row("excel/charstats.txt", CLASS, "MISSING", "no charstats row")]
    items = {}
    for tab in ("weapons", "armor", "misc"):
        for r in t[tab]:
            items.setdefault(r.get("code", "").lower(), (tab, r))
    own = view.names(f"global/chars/{tok}/")
    kits = [{(r.get(f"item{i}") or "").lower() for i in range(1, 11)} for r in t["charstats"]
            if r.get("class") and r.get("class", "").lower() != CLASS.lower() and r.get("item1")]
    for i in range(1, 11):
        code = (cs.get(f"item{i}") or "").lower()
        if not code or code == "0":
            continue
        tab, r = items.get(code, (None, None))
        if r is None:
            rows.append(Row(f"excel/*:{code}", f"start item{i}", "MISSING", "item code not found"))
            continue
        for col in ("invfile", "flippyfile"):
            if r.get(col):
                rel = f"global/items/{_art(r[col])}.dc6"
                where, note = view.where(rel), ""
                if where == "MISSING" and kits and all(code in k for k in kits):
                    where, note = "all-classes", "missing for every class's kit alike: not Warlock-specific"
                rows.append(Row(rel, f"start item{i} {code} {col}", where, "", note))
        if tab == "weapons":
            gfx = (r.get("alternategfx") or code).lower()
            for wc in {(r.get("wclass") or "").lower(), (r.get("2handedwclass") or "").lower()} - {""}:
                comp = HAND_OF.get(wc, "rh")
                for cof in sorted(f for f in own if f.endswith(f"{wc}.cof") and "/cof/" in f):
                    mode = cof.rsplit("/", 1)[1][len(tok):len(tok) + 2]
                    try:
                        layers = parse_cof(view.read(cof) or b"")["layers"]
                    except ValueError:
                        continue
                    if any(c == comp for c, _ in layers):
                        rel = f"global/chars/{tok}/{comp}/{tok}{comp}{gfx}{mode}{wc}.dcc"
                        rows.append(Row(rel, f"start item{i} {code} in hand, mode {mode.upper()}", view.where(rel)))
    return rows


# --- main ---------------------------------------------------------------------------------------------------------------

def run(mod: Path, d2r: Path, ref: str = "ne") -> dict[str, list[Row]]:
    view = View(mod, d2r)
    excel = Path(mod) / "global" / "excel"
    t = Tables(excel if (excel / "skills.txt").exists() else Path(d2r) / "data" / "global" / "excel")
    ad = view.read("global/animdata.d2")
    frames = anim_frames(ad) if ad else None
    tok = class_token(t)
    return {"char": check_char(view, tok, ref, frames), "items": check_items(view, t, tok, ref),
            "skills": check_skills(view, t, frames), "ui": check_ui(view, t), "kit": check_kit(view, t, tok)}


def summary(res: dict[str, list[Row]]) -> dict[str, Counter]:
    out = {}
    for sec, rows in res.items():
        c = Counter()
        for r in rows:
            if r.found in ("same-as-ref", "not-drawn", "all-classes"):
                c[r.found] += 1
            else:
                c["MISSING" if r.found == "MISSING" else "found"] += 1
            if r.note:
                c["notes"] += 1
            if r.problem:
                c["out-of-range"] += 1
        out[sec] = c
    return out


def bad(r: Row) -> bool:
    return r.found in ("MISSING", "all-classes") or bool(r.problem)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--mod", type=Path, default=fxpaths.OUT)
    ap.add_argument("--d2r", type=Path, default=fxpaths.D2R)
    ap.add_argument("--ref", default="ne", help="the reference class token (default ne: D2R's Warlock files copy it)")
    ap.add_argument("--all", action="store_true", help="list the found rows too")
    ap.add_argument("--notes", action="store_true", help="list the rows with a note (tolerated mismatches) too")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    res = run(a.mod, a.d2r, a.ref)
    print("| section | file | needed by | found in | problem | note |\n|---|---|---|---|---|---|")
    for sec, rows in res.items():
        for r in rows:
            if a.all or bad(r) or (a.notes and r.note):
                print(f"| {sec} | {r.file} | {r.needed_by} | {r.found} | {r.problem} | {r.note} |")
    tot = Counter()
    print()
    for sec, c in summary(res).items():
        tot.update(c)
        print(f"{sec:7} found {c['found']:5}  missing {c['MISSING']:3}  out-of-range {c['out-of-range']:3}"
              f"  notes {c['notes']:3}  (layer not drawn {c['not-drawn']}, item gfx missing for the reference class too"
              f" {c['same-as-ref']}, missing for all classes {c['all-classes']})")
    print(f"total   found {tot['found']:5}  missing {tot['MISSING']:3}  out-of-range {tot['out-of-range']:3}"
          f"  notes {tot['notes']:3}")
    if a.json:
        a.json.write_text(json.dumps({k: [asdict(r) for r in v] for k, v in res.items()}, indent=1), "utf-8")
    return 1 if tot["MISSING"] or tot["out-of-range"] else 0


if __name__ == "__main__":
    sys.exit(main())
