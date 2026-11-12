#!/usr/bin/env python3
"""Skills for the wiki generator (docs/wiki-plan.md): every class skill and every item-only skill, with its tooltip lines
per skill level.

  py -3 tools/wiki/skills.py                 write work/wiki/skills.json
        [--out FILE]                         another output file
        [--show NAME ...]                    also print the records whose name or row contains NAME
        [--gaps]                             print the line types and formula names that could not be evaluated, by count

Reads the built tables (work/mod/data/global/excel: skills, skilldesc, missiles, charstats), the strings the player reads
(tools/strings_ns.effective_texts) and, when work/wiki/laz/ holds them, Brother Laz's character pages (tools/wiki/laz.py)
for each skill's flavour text.

One record per skill:
  key, id            the skills.txt row name and its *Id
  name               the shown name (skilldesc `str name`)
  class, class_code  "Amazon" ... or "" for an item-only skill; skills.txt charclass
  tree, page         the tree (tools/skill_tree_art.TAB_LABELS: two trees per page, column 1 and column 3), the page 1-3;
                     "Innate" for a class's start skill, "" for item-only skills
  row, column        the cell in the tree
  reqlevel, maxlvl   required character level, skills.txt maxlvl
  prereqs            shown names of reqskill1-3
  synergies          shown names of the other skills the skill's formulas read (skill('X'.code)), class skills first
  description        the long description (`str long`) top line first
  laz                {"flavour", "effect"} from Laz's pages, when found
  levels             the skill levels of the table: 1 up to the hard-point cap (Median's "maximum level" line evaluated at
                     character level 120 without +skills), at least 20 when maxlvl allows, never above maxlvl
  lines              the tooltip lines in the order the game shows them, each:
                       block      "dsc2" (general), "desc" (per level), "dsc3" (synergies)
                       type       the skilldesc line type
                       values     one text per level (null where the line is empty at that level), or
                       formula    when the line reads something the table can't know (character level, energy, ...):
                                  the line's text with the formula in [brackets]
                       assumes    stats / other skills taken as 0 for the values (item bonuses, points in other skills)
                       note       for damage: the synergy bonus not included in the values

Evaluation (lvl = blvl = the skill level: every level a hard point). Character values (character level, the base stats,
life and mana, energy factor) have no value without a character: a line reading one is kept as its formula. Item-only stats
and other skills read 0 and the line says so. Line texts follow Diablo II 1.14d's tooltip builder (Game.exe 0x4eef00,
line renderer 0x4edea0, read through Redivivus): text A / number / text B as each type joins them. The skilldesc `descdam`
damage block and line types not listed in TYPES are not rendered (--gaps counts them).
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402,F401  (MXL_D2R_EXTRACT: D2R's own strings)

if os.environ.get("MXL_D2R_EXTRACT") and not os.environ.get("D2R_LNG"):
    os.environ["D2R_LNG"] = str(Path(os.environ["MXL_D2R_EXTRACT"]) / "data" / "local" / "lng")
import strings_ns  # noqa: E402
from warlock_scale import Parser, Table, bracket, idiv, len_bracket, num, tokenize  # noqa: E402

EXCEL = ROOT / "work" / "mod" / "data" / "global" / "excel"
OUT = ROOT / "work" / "wiki" / "skills.json"
CLASSES = {"ama": "Amazon", "sor": "Sorceress", "nec": "Necromancer", "pal": "Paladin", "bar": "Barbarian",
           "dru": "Druid", "ass": "Assassin"}
MAX_ULVL = 120
MIN_LEVELS = 20
# stats every character has: a formula reading one has no value without a character
CHARACTER_STATS = {"strength", "dexterity", "vitality", "energy", "hitpoints", "maxhp", "mana", "maxmana", "stamina",
                   "maxstamina", "level", "experience", "enr_factor", "str_factor", "newskills", "statpts", "newskills",
                   "armorclass", "tohit", "gold", "goldbank"}
COLOUR = re.compile("ÿc.", re.S)
BLOCKS = (("descline", "desc", 6), ("dsc2line", "dsc2", 5), ("dsc3line", "dsc3", 7))
ETYPE = {"fire": "Fire Damage: ", "ltng": "Lightning Damage: ", "mag": "Magic Damage: ", "cold": "Cold Damage: ",
         "pois": "Poison Damage: ", "life": "Life Stolen: "}
ELEN = {"cold": "Cold Length: ", "pois": "Poison Length: "}


class Unknown(Exception):
    """The formula reads a character value."""


def clean(text: str) -> str:
    return COLOUR.sub("", text or "").replace("\r", "")


def tooltip_lines(text: str) -> list[str]:
    """A multi-line string as the game shows it: the tooltip is drawn bottom up, so the last line is the top one."""
    return [x.strip() for x in reversed(clean(text).split("\n")) if x.strip()]


class Skills:
    def __init__(self, excel: Path = EXCEL):
        self.texts = strings_ns.effective_texts()
        self.sk = Table(excel / "skills.txt")
        self.sd = Table(excel / "skilldesc.txt")
        self.ms = Table(excel / "missiles.txt")
        self.cs = Table(excel / "charstats.txt")
        self.gaps = Counter()

    def text(self, cell: str) -> str:
        return self.texts.get(strings_ns.bare(cell), "") if cell else ""

    def desc(self, row):
        return self.sd.by.get(self.sk.get(row, "skilldesc"))

    def name(self, row) -> str:
        d = self.desc(row)
        return clean(self.text(self.sd.get(d, "str name"))).strip() if d is not None else ""

    # ---- formula evaluation -------------------------------------------------------------------------------------
    def ev(self, row, table: Table, text: str, lvl: int, used: set, missile: bool = False) -> int:
        """`text` for skill (or missile) `row` at level lvl; raises Unknown on a character value. `used` collects the
        item stats and other skills read as 0."""
        text = (text or "").strip().strip('"')
        if not text:
            return 0
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        sk = self.sk

        def par(n):
            return num(table.get(row, f"Param{n}"))

        def ln(a, b):
            return par(a) + (lvl - 1) * par(b)

        def dm(a, b):
            return idiv((110 * lvl) * (par(b) - par(a)), 100 * (lvl + 6)) + par(a)

        def resolve(name):
            if name in ("lvl", "blvl"):
                return lvl
            if name == "ulvl":
                raise Unknown("ulvl")
            m = re.fullmatch(r"par(\d)|pa(\d\d)", name)
            if m:
                return par(int(m.group(1) or m.group(2)))
            m = re.fullmatch(r"(ln|dm)(12|34|56|78|91|21)", name)
            if m:
                a, b = {"12": (1, 2), "34": (3, 4), "56": (5, 6), "78": (7, 8), "91": (9, 10), "21": (11, 12)}[m.group(2)]
                return ln(a, b) if m.group(1) == "ln" else dm(a, b)
            if missile:
                m = re.fullmatch(r"(sl|sd)(12|34)", name)
                if m:
                    a, b = (1, 2) if m.group(2) == "12" else (3, 4)
                    return ln(a, b) if m.group(1) == "sl" else dm(a, b)
                if name == "rang":
                    return self.ev(row, table, table.get(row, "Range"), lvl, used, True)
            else:
                m = re.fullmatch(r"clc(\d+)", name)
                if m:
                    return self.ev(row, table, table.get(row, f"calc{m.group(1)}"), lvl, used)
                m = re.fullmatch(r"ast(\d)", name)
                if m:
                    return self.ev(row, table, table.get(row, f"aurastatcalc{m.group(1)}"), lvl, used)
                m = re.fullmatch(r"pst(\d)|ps(\d\d)", name)
                if m:
                    return self.ev(row, table, table.get(row, f"passivecalc{m.group(1) or m.group(2)}"), lvl, used)
                if name == "len":
                    return self.ev(row, table, table.get(row, "auralencalc"), lvl, used)
                if name == "rng":
                    return self.ev(row, table, table.get(row, "aurarangecalc"), lvl, used)
                if name in ("edmn", "edmx", "edns", "edxs"):
                    lo, hi = self.elem(row, lvl, used)
                    v = lo if name in ("edmn", "edns") else hi
                    return v * 256 if name in ("edns", "edxs") else v
                if name in ("damn", "damx"):
                    lo, hi = self.phys(row, lvl, used)
                    return lo if name == "damn" else hi
                if name == "edln":
                    return self.elen(row, lvl, used)
                if name == "toht":
                    return self.tohit(row, lvl, used)
                if name in ("mana", "usmc"):
                    return self.mana256(row, lvl) // (1 if name == "usmc" else 256)
            if missile:
                if name in ("edmn", "edmx", "enma", "exma"):
                    lo, hi = self.block(row, table, lvl, True, True)
                    return lo if name in ("edmn", "enma") else hi
                if name in ("damn", "damx", "pnma", "pxma"):
                    lo, hi = self.block(row, table, lvl, False, True)
                    return lo if name in ("damn", "pnma") else hi
            raise Unknown(name)

        def call(fn, ref, parts, args):
            if fn == "min":
                return min(args)
            if fn == "max":
                return max(args)
            if fn == "rand":
                raise Unknown("rand")
            if fn == "stat":
                if ref in CHARACTER_STATS:
                    raise Unknown(f"stat('{ref}')")
                used.add(f"stat {ref}")
                return 0
            if fn == "miss":
                mrow = self.ms.by.get(ref)
                if mrow is None:
                    raise Unknown(f"miss('{ref}')")
                return self.ev(mrow, self.ms, parts[-1], lvl, used, True)
            if fn not in ("skill", "sklvl"):
                raise Unknown(fn)
            srow = self.sk.by.get(ref)
            if srow is None:
                raise Unknown(f"skill('{ref}')")
            code = parts[-1]
            if srow is row and table is sk or fn == "sklvl":
                slv = lvl                      # the skill itself, or sklvl('X'.lvl.code): X at the caller's level
            else:
                used.add(f"skill {ref}")
                slv = 0                        # no points in another skill
            if code in ("blvl", "lvl"):
                return slv
            if slv == 0:
                return 0
            return self.ev(srow, sk, code, slv, used)

        try:
            return Parser(tokenize(text), resolve, call).parse()
        except ValueError as e:
            raise Unknown(f"parse {e}") from None

    # ---- damage, length, mana -----------------------------------------------------------------------------------
    def block(self, row, table, lvl, elem: bool, missile: bool):
        """(min, max) of a damage block in whole points, without synergies."""
        if missile:
            cols = ("EMin", "MinELev", "EMax", "MaxELev") if elem else ("MinDamage", "MinLevDam", "MaxDamage", "MaxLevDam")
        else:
            cols = ("EMin", "EMinLev", "EMax", "EMaxLev") if elem else ("MinDam", "MinLevDam", "MaxDam", "MaxLevDam")
        lo = bracket(num(table.get(row, cols[0])), [num(table.get(row, f"{cols[1]}{i}")) for i in range(1, 6)], lvl)
        hi = bracket(num(table.get(row, cols[2])), [num(table.get(row, f"{cols[3]}{i}")) for i in range(1, 6)], lvl)
        shift = num(table.get(row, "HitShift"), 8)
        return (lo << shift) >> 8, (hi << shift) >> 8

    def sym(self, row, col: str, lvl: int, used: set):
        """The synergy percentage of a damage block, or None when it reads a character value."""
        try:
            return self.ev(row, self.sk, self.sk.get(row, col), lvl, used)
        except Unknown:
            return None

    def elem(self, row, lvl, used):
        lo, hi = self.block(row, self.sk, lvl, True, False)
        pct = self.sym(row, "EDmgSymPerCalc", lvl, used) or 0
        return lo + lo * pct // 100, hi + hi * pct // 100

    def phys(self, row, lvl, used):
        lo, hi = self.block(row, self.sk, lvl, False, False)
        pct = self.sym(row, "DmgSymPerCalc", lvl, used) or 0
        return lo + lo * pct // 100, hi + hi * pct // 100

    def elen(self, row, lvl, used=None):
        """Elemental length in frames, with the ELenSymPerCalc percent bonus when it does not read a character value."""
        n = len_bracket(num(self.sk.get(row, "ELen")), [num(self.sk.get(row, f"ELevLen{i}")) for i in (1, 2, 3)], lvl)
        pct = self.sym(row, "ELenSymPerCalc", lvl, used if used is not None else set()) or 0
        return n + n * pct // 100

    def tohit(self, row, lvl, used):
        calc = self.sk.get(row, "ToHitCalc")
        if calc:
            return self.ev(row, self.sk, calc, lvl, used)
        return num(self.sk.get(row, "ToHit")) + (lvl - 1) * num(self.sk.get(row, "LevToHit"))

    def mana256(self, row, lvl):
        sk = self.sk
        cost = ((lvl - 1) * num(sk.get(row, "lvlmana")) + num(sk.get(row, "mana"))) << num(sk.get(row, "manashift"), 8)
        return max(cost, num(sk.get(row, "minmana")) * 256)

    def sym_note(self, row, cols=("EDmgSymPerCalc",)) -> str:
        notes = []
        for col in cols:
            calc = self.sk.get(row, col)
            if calc and self.sym(row, col, 1, set()) is None:
                notes.append(f"plus {pretty(calc)} percent from synergies")
        return "; ".join(notes)


# ---- line texts -------------------------------------------------------------------------------------------------
def signed(v: int, sign: bool) -> str:
    return f"+{v}" if sign and v >= 0 else str(v)


def seconds(frames: int, sign: bool = False):
    """1.14d SKILLDESC_FormatValueWithSign: frames as seconds with one decimal, " second(s)"."""
    whole, frac = int(frames / 25), int((frames % 25 if frames >= 0 else -(-frames % 25)) * 10 / 25)
    if whole == 0 and frac == 0:
        return None
    v = f"{signed(whole, sign)}.{abs(frac)}" if frac else signed(whole, sign)
    return v + (" second" if whole == 1 and frac == 0 else " seconds")


def yards(v: int):
    """1.14d SKILLDESC_FormatDecimalSigned: distance as yards (x 2/3), one decimal."""
    t = v * 20 // 3
    whole, frac = t // 10, t % 10
    if whole < 1:
        whole = 1
    out = f"{whole}.{frac}" if frac else str(whole)
    return out + (" yard" if whole == 1 else " yards")


def rng(a: int, b: int, sign: bool = False) -> str:
    return signed(a, sign) if a == b else f"{'+' if sign else ''}{a}-{b}"


def printf(fmt: str, *args) -> str:
    vals = iter(args)

    def sub(m):
        if m.group(0) == "%%":
            return "%"
        v = next(vals, "")
        if m.group(2) == "+" and isinstance(v, int) and v >= 0:
            return f"+{v}"
        return str(v)
    return re.sub(r"%%|%(\d\$)?([-+ #0]*)\d*[dius]", sub, fmt)


PRETTY = ((re.compile(r"stat\('([a-z_0-9]+)'\.(?:accr|base)\)"), r"\1"),
          (re.compile(r"skill\('([^']+)'\.blvl\)"), r"\1 hard points"),
          (re.compile(r"skill\('([^']+)'\.lvl\)"), r"\1 level"),
          (re.compile(r"\bulvl\b"), "character level"),
          (re.compile(r"\bblvl\b"), "hard points"),
          (re.compile(r"\blvl\b"), "skill level"))


def pretty(formula: str) -> str:
    out = formula
    for rx, rep in PRETTY:
        out = rx.sub(rep, out)
    return out


class Line:
    """One skilldesc line: text A / B, calc A / B, type."""

    def __init__(self, s: Skills, row, d, line: str, prefix: str, i: int):
        self.s, self.row, self.d = s, row, d
        self.kind = num(s.sd.get(d, f"{line}{i}"))
        self.a_key, self.b_key = s.sd.get(d, f"{prefix}texta{i}"), s.sd.get(d, f"{prefix}textb{i}")
        self.a = clean(s.text(self.a_key)).replace("\n", " ")
        self.b = clean(s.text(self.b_key)).replace("\n", " ")
        self.ca, self.cb = s.sd.get(d, f"{prefix}calca{i}"), s.sd.get(d, f"{prefix}calcb{i}")

    def render(self, lvl: int, used: set):
        """The line's text at lvl (None: nothing shown); raises Unknown."""
        s, row, k, A, B = self.s, self.row, self.kind, self.a, self.b
        need_a = k not in (1, 9, 10, 11, 14, 22, 27, 29)
        ca = s.ev(row, s.sk, self.ca, lvl, used) if need_a else 0
        cb = s.ev(row, s.sk, self.cb, lvl, used) if self.cb and k in (9, 35, 38, 40, 46, 52, 73) else 0
        if k == 1:
            if not (num(s.sk.get(row, "mana")) or num(s.sk.get(row, "lvlmana"))):
                return None
            cost = s.mana256(row, lvl)
            shift = num(s.sk.get(row, "manashift"), 8)
            if shift != 8 and (num(s.sk.get(row, "lvlmana")) << shift) <= 256 and cost <= 0x1900:
                whole, frac = cost >> 8, ((cost & 0xff) * 10) >> 8
                return A + (f"{whole}.{frac}" if frac else str(whole))
            return A + str(cost >> 8)
        if k in (2, 3):
            return None if ca == 0 else A + signed(ca, k == 2) + B
        if k in (4, 5):
            return None if ca == 0 else A + signed(ca, k == 4)
        if k in (6, 7):
            return None if ca == 0 else signed(ca, k == 6) + A
        if k == 8:
            v = s.tohit(row, lvl, used)
            return None if v == 0 else A + B + "To Attack Rating: " + signed(v, True) + " percent"
        if k == 9:
            lo, hi = s.phys(row, lvl, used)
            lo, hi = lo + lo * ca // 100 + cb, hi + hi * ca // 100 + cb
            return None if lo == hi == 0 else A + B + "Damage: " + rng(lo, hi, lo == hi)
        if k in (10, 14):
            lo, hi = s.elem(row, lvl, used)
            lab = ETYPE.get(s.sk.get(row, "EType"))
            if k == 14:
                n = s.elen(row, lvl, used)
                pre = (seconds(n) and "over " + seconds(n) + " ") or ""
                lo, hi = lo * n // 256, hi * n // 256
                return None if not lab else A + B + pre + lab + rng(lo, hi)
            return None if lo == hi == 0 or not lab else A + B + lab + rng(lo, hi)
        if k == 11:
            lab = ELEN.get(s.sk.get(row, "EType"))
            sec = seconds(s.elen(row, lvl, used))
            return None if not lab or not sec else A + B + lab + sec
        if k in (12, 31):
            sec = seconds(ca)
            return None if sec is None else B + A + sec
        if k == 18:
            # a text-only line may hold several lines, drawn bottom up like the whole tooltip
            return "\n".join(tooltip_lines(self.s.text(self.a_key))) or None
        if k == 19:
            return B + A + yards(ca)
        if k == 29:
            m = s.ms.by.get(s.sd.get(self.d, "descmissile1"))
            if m is None:
                return None
            v = ((num(s.ms.get(m, "LevRange")) * (lvl - 1) + num(s.ms.get(m, "Range"))) * 2) // 3
            return None if v == 0 else f"{v} yards"
        if k == 35:
            return A + ": " + f"{ca}-{cb}"
        if k in (38, 52):
            if ca == cb:
                return None if ca == 0 else A + str(ca) + B
            return A + rng(ca, cb, k == 52) + B
        if k == 40:
            return printf(A, B) if A else None
        if k in (63, 67):
            if ca == 0:
                return None
            return (A + ": " if A else "") + signed(ca, True) + ("%" if k == 63 else "") + " " + B
        if k == 65:
            return A + ": " + B if A and B else None
        if k in (66, 74):
            return printf(A, ca) if A else None
        if k == 73:
            return None if ca == 0 or cb < 1 else f"{ca}/{cb} {A}"
        raise Unknown(f"type {k}")

    def formula_text(self, why: str) -> str:
        """The line with its unknown numbers written as formulas."""
        k, A, B = self.kind, self.a, self.b
        fa, fb = f"[{pretty(self.ca)}]", f"[{pretty(self.cb)}]"
        if k in (2, 3):
            return A + fa + B
        if k in (4, 5, 12, 19):
            return B + A + fa if k in (12, 19) else A + fa
        if k in (6, 7):
            return fa + A
        if k in (35, 38, 52):
            return A + fa + "-" + fb + B
        if k in (63, 67):
            return (A + ": " if A else "") + fa + ("%" if k == 63 else "") + " " + B
        if k in (66, 74):
            return printf(A, fa)
        if k == 73:
            return f"{fa}/{fb} {A}"
        return f"{A}{fa}{B} ({why})"


def tree_of(s: Skills, cls: str, page: int, column: int) -> str:
    try:
        from skill_tree_art import TAB_LABELS
    except ImportError:
        return f"Page {page}"
    labels = TAB_LABELS.get(cls)
    if not labels or page not in (1, 2, 3):
        return f"Page {page}"
    i = 2 * (3 - page) + (0 if column == 3 else 1)
    name = labels[i]
    return "Uberskills" if name == "Special" else name


def skill_refs(s: Skills, row) -> list[str]:
    """Row names of the other skills the skill's own formulas read."""
    out = []
    for c in s.sk.header:
        v = s.sk.get(row, c)
        for ref in re.findall(r"(?:skill|sklvl)\('([^']+)'", v):
            if ref != row[0] and ref not in out and c != "skpoints":
                out.append(ref)
    d = s.desc(row)
    if d is not None:
        for c in s.sd.header:
            if "calc" in c:
                for ref in re.findall(r"(?:skill|sklvl)\('([^']+)'", s.sd.get(d, c)):
                    if ref != row[0] and ref not in out:
                        out.append(ref)
    return out


def hard_cap(s: Skills, row) -> int | None:
    """The hard-point cap of Median's "maximum level" line (type 73 calc B) at character level 120, without +skills."""
    d = s.desc(row)
    for line, prefix, n in BLOCKS:
        for i in range(1, n + 1):
            if s.sd.get(d, f"{line}{i}") == "73":
                calc = s.sd.get(d, f"{prefix}calcb{i}")
                calc = re.sub(r"\bulvl\b", str(MAX_ULVL), calc)
                calc = re.sub(r"stat\('skill_more'\.accr\)", "0", calc)
                try:
                    return s.ev(row, s.sk, calc, 1, set())
                except Unknown:
                    return None
    return None


def record(s: Skills, row, laz: dict) -> dict:
    d = s.desc(row)
    cls = s.sk.get(row, "charclass")
    maxlvl = num(s.sk.get(row, "maxlvl"), 20) or 20
    cap = hard_cap(s, row)
    top = min(maxlvl, max(MIN_LEVELS, cap or 0))
    levels = list(range(1, top + 1))
    rec = {"key": row[0], "id": num(s.sk.get(row, "*Id")), "name": s.name(row),
           "class": CLASSES.get(cls, ""), "class_code": cls, "tree": "", "page": num(s.sd.get(d, "SkillPage")),
           "row": num(s.sd.get(d, "SkillRow")), "column": num(s.sd.get(d, "SkillColumn")),
           "reqlevel": max(1, num(s.sk.get(row, "reqlevel"), 1)), "maxlvl": maxlvl, "hard_cap": cap}
    if cls in CLASSES and rec["page"]:
        rec["tree"] = tree_of(s, cls, rec["page"], rec["column"])
    rec["prereqs"] = [name for r in (s.sk.get(row, f"reqskill{i}") for i in (1,2,3))
                      if r and r in s.sk.by and (name := s.name(s.sk.by[r]))]
    refs = [s.sk.by[r] for r in skill_refs(s, row) if r in s.sk.by]
    refs.sort(key=lambda r: s.sk.get(r, "charclass") != cls)
    rec["synergies"] = [n for n in dict.fromkeys(s.name(r) for r in refs) if n and n != rec["name"]]
    # SkillsdSecret is the shared placeholder text of item and monster skills
    long = s.sd.get(d, "str long")
    rec["description"] = [] if long.endswith("SkillsdSecret") else tooltip_lines(s.text(long))
    if laz.get(rec["name"].upper()):
        rec["laz"] = laz[rec["name"].upper()]
    rec["levels"] = levels
    lines = []
    for line, prefix, n in (BLOCKS[1], BLOCKS[0], BLOCKS[2]):
        block = []
        for i in range(1, n + 1):
            if not s.sd.get(d, f"{line}{i}"):
                continue
            ln = Line(s, row, d, line, prefix, i)
            entry = {"block": prefix, "type": ln.kind}
            used = set()
            try:
                vals = [ln.render(L, used) for L in levels]
                if not any(vals):
                    continue
                if len(set(vals)) == 1:
                    entry["text"] = vals[0]
                else:
                    entry["values"] = vals
            except Unknown as e:
                why = str(e)
                if why.startswith("type "):
                    s.gaps[why] += 1
                    continue
                s.gaps[why] += 1
                entry["formula"] = ln.formula_text(why)
            if used:
                entry["assumes"] = sorted(used)
            if ln.kind in (9, 10, 14) or "edm" in ln.ca + ln.cb or "dam" in ln.ca + ln.cb:
                note = s.sym_note(row, ("DmgSymPerCalc",) if ln.kind == 9 else ("EDmgSymPerCalc",))
                if note:
                    entry["note"] = note
            block.append(entry)
        # descline and dsc2line are drawn bottom up (line 1 lowest); dsc3 top down
        lines += block if prefix == "dsc3" else block[::-1]
    rec["lines"] = lines
    return rec


def start_skills(s: Skills) -> dict[str, str]:
    """skills.txt row -> class code of each class's own start skill (charstats Skill 1-10 not shared by classes)."""
    seen = Counter()
    per = {}
    for r in s.cs.rows:
        names = [s.cs.get(r, f"Skill {i}") for i in range(1, 11)]
        for nm in names:
            if nm:
                seen[nm] += 1
        per[r[0]] = names
    out = {}
    code = {v: k for k, v in CLASSES.items()}
    for cname, names in per.items():
        for nm in names:
            if nm and seen[nm] == 1 and cname in code and nm in s.sk.by:
                out[nm] = code[cname]
    return out


# Laz's item-only names that differ from the skill's own string: skilldesc row -> (Laz's name, page name)
LAZ_ALIASES = {"demonbloodaura": ("DEMON BLOOD AURA", "Demon Blood Aura"),
               "tknife": ("THROWING KNIFE", "Throwing Knife"),
               "callhenchman": ("CALL HENCHMEN", "Call Henchmen"),
               "ohman": ("O.H.M.A.N.", "O.H.M.A.N.")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--show", nargs="+")
    ap.add_argument("--gaps", action="store_true")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    import laz as lazmod
    s = Skills()
    flavour = lazmod.skill_texts()
    item_only = lazmod.item_only_names()
    starts = start_skills(s)
    out = []
    by_name = {}
    for row in s.sk.rows:
        d = s.desc(row)
        if d is None:
            continue
        cls = s.sk.get(row, "charclass")
        name = s.name(row)
        alias = LAZ_ALIASES.get(d[0])
        if alias and alias[0] not in by_name:
            rec = record(s, row, flavour)
            rec["name"] = alias[1]
            rec["laz"] = flavour.get(alias[0], rec.get("laz"))
            rec["item_only"] = item_only[alias[0]]
            by_name[alias[0]] = rec
            out.append(rec)
            continue
        tree_skill = cls in CLASSES and num(s.sd.get(d, "SkillPage")) > 0
        if tree_skill or row[0] in starts:
            rec = record(s, row, flavour)
            if row[0] in starts and not tree_skill:
                rec["class"], rec["class_code"], rec["tree"] = CLASSES[starts[row[0]]], starts[row[0]], "Innate"
            out.append(rec)
        elif name and name.upper() in item_only and name.upper() not in by_name:
            rec = record(s, row, flavour)
            rec["item_only"] = item_only[name.upper()]
            by_name[name.upper()] = rec
            out.append(rec)
    names = Counter(r["name"] for r in out)
    for r in out:
        r["page_title"] = r["name"] if names[r["name"]] == 1 else f"{r['name']} ({r['class'] or 'item skill'})"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    missing = sorted(set(item_only) - set(by_name))
    print(f"{len(out)} skills ({sum(1 for r in out if r['class'])} class, {len(by_name)} item-only) -> {args.out}")
    if missing:
        print(f"{len(missing)} item-only skills of Laz's page with no skills row of that name: {', '.join(missing)}")
    if args.show:
        for r in out:
            if any(x.lower() in (r["name"] + " " + r["key"]).lower() for x in args.show):
                print(json.dumps(r, ensure_ascii=False, indent=1))
    if args.gaps:
        for k, v in s.gaps.most_common():
            print(f"{v:5} {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
