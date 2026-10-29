"""Warlock balance: scale D2R's Warlock (the 8th class, skills 373-402) to Median XL 2012's power level (lane warlock).

Owner decision 2026-10-28: every Warlock skill is anchored to Median 2012's own class skills of the same tier and role.
Round 1 (lane warlock) changed numbers only. Round 2 (lane warlock2, owner answer 2026-10-28 "go with what you think is best
to match the scaling") also gives the Warlock Median's own rules, copied from Median's rows (`rule_cells`): the skpoints gate,
Median's character-level / energy synergy calcs, Median's summon life pattern and flat weapon-skill damage, and the tooltip
lines that show them. The skill functions, missiles and states stay D2R's. docs/warlock-balance.md has the method, the
reference character and the per-skill table.

  py -3 -I tools/warlock_scale.py fit   [--excel DIR]   compare the Warlock with its comparables on the migrated tables
                                                         (before the balance step) and write data/warlock_rules.tsv (the
                                                         formula / text cells) and data/warlock_balance.tsv (the numbers;
                                                         both: skill, table, row, column, value before, new value) and
                                                         work/warlock/fit_report.md (per-skill curves, slvl 1..40)
  py -3 -I tools/warlock_scale.py apply [--mod work/mod] build step (after d2r_adds.py): writes the rules, then the
                                                         numbers into the RotW bank; a cell whose current value is not the
                                                         recorded one stops the step (D2R or the migration changed it)
  py -3 -I tools/warlock_scale.py ttk   [--excel DIR]   sanity check on the built (balanced) tables: time to kill an
                                                         average Median monster per area level and difficulty, Warlock vs
                                                         the median of its comparables; ratios beyond +-25 % are flagged
                                                         (work/warlock/ttk_report.md, exit 0: a report, not a gate)
  py -3 -I tools/warlock_scale.py probe NAME [...]       print a skill's numbers at slvl 1/10/20/30/40 (any class)

Model (the reference character, the same for the Warlock and for Median's classes; docs/warlock-balance.md):
  slvl s at Median tier T  ->  character level u = min(120, T + 3 (s - 1)), hard points h = 1 + (s - 1) // 2
  synergy skills: blvl = h, lvl = s (same class only; another class's or a hidden skill's is 0)
  energy (stat 'energy'.accr) = 20 + 2 (u - 1); strength / dexterity base = 20 + 1.5 (u - 1); other stats 0 (no items)
  weapon: the 75th percentile of Median's weapon bases' average damage (best of one- / two-handed) with levelreq <= u
  summons: monster level u, life = monstats life x monlvl L-HP x (1 + clc1 %) + flat maxhp passive; damage = A1 x L-DM x
           (1 + damagepercent %) + flat (item_normaldamage / mindamage passives, elemental passives)
Warlock reqlevel 30 skills are compared with Median's top regular tier (24); Median's level 90 skills are not used.
"""
from __future__ import annotations

import argparse
import math
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from idmap import is_record, read_tsv  # noqa: E402

EXCEL = Path("data") / "global" / "excel"
BANKS = ("", "base")
TSV = ROOT / "data" / "warlock_balance.tsv"
RULES_TSV = ROOT / "data" / "warlock_rules.tsv"
OUTDIR = ROOT / "work" / "warlock"
SLVLS = list(range(1, 41))
SHOW = (1, 10, 20, 30, 40)
MAX_U = 120
TIER_MAP = {1: 1, 6: 6, 12: 12, 18: 18, 24: 24, 30: 24}   # Warlock reqlevel -> Median tier
CAST_FRAMES = 13      # frames per cast assumed for a skill without a casting delay (about 0.5 s at moderate FCR)
OUTLIER = 0.25


# --------------------------------------------------------------------------------------------------------------------
# reference character
# --------------------------------------------------------------------------------------------------------------------
def ulvl(s: int, tier: int) -> int:
    return min(MAX_U, tier + 3 * (s - 1))


def hard(s: int) -> int:
    return 1 + (s - 1) // 2


def ref_stat(name: str, kind: str, u: int) -> int:
    if name == "energy":
        return 20 + 2 * (u - 1)
    if name in ("strength", "dexterity"):
        return int(20 + 1.5 * (u - 1))
    return 0


# --------------------------------------------------------------------------------------------------------------------
# formula evaluator (D2's skill / missile calc language, integer arithmetic)
# --------------------------------------------------------------------------------------------------------------------
TOKEN = re.compile(r"\s*(?:(\d+)|('[^']*')|([A-Za-z_][A-Za-z0-9_]*)|(==|!=|>=|<=|[-+*/()?:<>,.]))")


def tokenize(text: str) -> list[str]:
    out, i = [], 0
    text = text.strip().strip('"')
    while i < len(text):
        m = TOKEN.match(text, i)
        if not m or m.end() == i:
            if text[i:].strip() == "":
                break
            raise ValueError(f"bad formula near {text[i:]!r}")
        out.append(next(g for g in m.groups() if g is not None))
        i = m.end()
    return out


def idiv(a: int, b: int) -> int:
    if b == 0:
        return 0
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


class Parser:
    """Recursive descent over the token list; `resolve(name)` gives identifiers, `call(fn, ref, code, args)` the
    functions (skill('X'.code), sklvl('X'.lvl.code), miss('m'.code), stat('s'.accr), min, max, rand)."""

    def __init__(self, tokens, resolve, call):
        self.t, self.i, self.resolve, self.call = tokens, 0, resolve, call

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self, want=None):
        tok = self.peek()
        if want is not None and tok != want:
            raise ValueError(f"expected {want!r}, got {tok!r} in {' '.join(self.t)}")
        self.i += 1
        return tok

    def parse(self):
        v = self.ternary()
        if self.peek() is not None:
            raise ValueError(f"trailing {self.t[self.i:]}")
        return v

    def ternary(self):
        c = self.compare()
        if self.peek() == "?":
            self.take()
            a = self.ternary()
            self.take(":")
            b = self.ternary()
            return a if c else b
        return c

    def compare(self):
        v = self.add()
        while self.peek() in ("<", ">", "<=", ">=", "==", "!="):
            op = self.take()
            w = self.add()
            v = int({"<": v < w, ">": v > w, "<=": v <= w, ">=": v >= w, "==": v == w, "!=": v != w}[op])
        return v

    def add(self):
        v = self.mul()
        while self.peek() in ("+", "-"):
            op = self.take()
            w = self.mul()
            v = v + w if op == "+" else v - w
        return v

    def mul(self):
        v = self.unary()
        while self.peek() in ("*", "/"):
            op = self.take()
            w = self.unary()
            v = v * w if op == "*" else idiv(v, w)
        return v

    def unary(self):
        if self.peek() == "-":
            self.take()
            return -self.unary()
        if self.peek() == "+":
            self.take()
            return self.unary()
        return self.primary()

    def primary(self):
        tok = self.take()
        if tok is None:
            raise ValueError("unexpected end")
        if tok == "(":
            v = self.ternary()
            self.take(")")
            return v
        if tok.isdigit():
            return int(tok)
        if self.peek() == "(" and tok in ("skill", "sklvl", "miss", "stat"):
            self.take("(")
            ref = self.take().strip("'")
            parts = []
            while self.peek() == ".":
                self.take()
                parts.append(self.take())
            self.take(")")
            return self.call(tok, ref, parts, None)
        if self.peek() == "(":
            self.take("(")
            args = [self.ternary()]
            while self.peek() == ",":
                self.take()
                args.append(self.ternary())
            self.take(")")
            return self.call(tok, None, None, args)
        return self.resolve(tok)


# --------------------------------------------------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------------------------------------------------
class Table:
    def __init__(self, path: Path, key: str | None = None):
        self.header, rows = read_tsv(path)
        self.ix = {c: i for i, c in enumerate(self.header)}
        self.low = {c.lower(): i for i, c in enumerate(self.header)}
        self.rows = [r for r in rows if is_record(r)]
        k = self.ix[key] if key else 0
        self.by = {}
        for r in self.rows:
            self.by.setdefault(r[k], r)

    def get(self, row, col, default=""):
        i = self.ix.get(col)
        if i is None:
            i = self.low.get(col.lower())
        return row[i] if i is not None and i < len(row) else default


def num(v, default=0):
    v = (v or "").strip()
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        try:
            return int(float(v))
        except ValueError:
            return default


class Data:
    def __init__(self, excel: Path):
        self.excel = excel
        self.skills = Table(excel / "skills.txt")
        self.missiles = Table(excel / "missiles.txt")
        self.monstats = Table(excel / "monstats.txt")
        self.monlvl = {num(r[0]): r for r in Table(excel / "monlvl.txt").rows}
        self.monlvl_t = Table(excel / "monlvl.txt")
        self.weapons = Table(excel / "weapons.txt")
        self.skilldesc = Table(excel / "skilldesc.txt") if (excel / "skilldesc.txt").exists() else None
        self._weap = {}

    def skill(self, name):
        return self.skills.by.get(name)

    def weapon_avg(self, u: int) -> float:
        if u not in self._weap:
            w, vals = self.weapons, []
            for r in w.rows:
                if num(w.get(r, "levelreq")) > u or not w.get(r, "code"):
                    continue
                one = (num(w.get(r, "mindam")) + num(w.get(r, "maxdam"))) / 2
                two = (num(w.get(r, "2handmindam")) + num(w.get(r, "2handmaxdam"))) / 2
                if max(one, two) > 0:
                    vals.append(max(one, two))
            vals.sort()
            self._weap[u] = vals[int(0.75 * (len(vals) - 1))] if vals else 1.0
        return self._weap[u]


# columns of the damage block, skills vs missiles
SK_COLS = dict(emin="EMin", eminl=[f"EMinLev{i}" for i in range(1, 6)], emax="EMax", emaxl=[f"EMaxLev{i}" for i in range(1, 6)],
               pmin="MinDam", pminl=[f"MinLevDam{i}" for i in range(1, 6)], pmax="MaxDam", pmaxl=[f"MaxLevDam{i}" for i in range(1, 6)],
               src="SrcDam")
MS_COLS = dict(emin="EMin", eminl=[f"MinELev{i}" for i in range(1, 6)], emax="EMax", emaxl=[f"MaxELev{i}" for i in range(1, 6)],
               pmin="MinDamage", pminl=[f"MinLevDam{i}" for i in range(1, 6)], pmax="MaxDamage",
               pmaxl=[f"MaxLevDam{i}" for i in range(1, 6)], src="SrcDamage")


def bracket(base: int, incs: list[int], lvl: int) -> int:
    """1.13c / D2R level brackets: levels 2-8 add Lev1, 9-16 Lev2, 17-22 Lev3, 23-28 Lev4, 29+ Lev5."""
    v = base
    for L in range(2, lvl + 1):
        v += incs[0 if L <= 8 else 1 if L <= 16 else 2 if L <= 22 else 3 if L <= 28 else 4]
    return v


def len_bracket(base: int, incs: list[int], lvl: int) -> int:
    v = base
    for L in range(2, lvl + 1):
        v += incs[0 if L <= 8 else 1 if L <= 16 else 2]
    return v


# --------------------------------------------------------------------------------------------------------------------
# evaluation context
# --------------------------------------------------------------------------------------------------------------------
@dataclass
class Ctx:
    data: Data
    cls: str          # class of the skill being judged: synergies from another class count 0
    s: int            # skill level (with +skills)
    tier: int         # Median tier used for the character level
    unknown: set = field(default_factory=set)

    @property
    def u(self):
        return ulvl(self.s, self.tier)

    def lvl_of(self, row):
        """(lvl, blvl) the reference character has in a skill row."""
        if row is None:
            return 0, 0
        cc = self.data.skills.get(row, "charclass")
        if cc != self.cls:
            return 0, 0
        return self.s, min(hard(self.s), num(self.data.skills.get(row, "maxlvl"), 20) or 20)

    # ---- generic row evaluation --------------------------------------------------------------------------------
    def ev(self, row, table: Table, text: str, lvl: int, blvl: int, missile: bool = False):
        text = (text or "").strip()
        if not text:
            return 0
        if re.fullmatch(r"-?\d+", text):
            return int(text)

        def par(n):
            return num(table.get(row, f"Param{n}"))

        def ln(a, b):
            return par(a) + (lvl - 1) * par(b)

        def dm(a, b):
            return idiv((110 * lvl) * (par(b) - par(a)), 100 * (lvl + 6)) + par(a)

        def resolve(name):
            if name == "lvl":
                return lvl
            if name == "blvl":
                return blvl
            if name == "ulvl":
                return self.u
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
                    return self.ev(row, table, table.get(row, "Range"), lvl, blvl, True)
            m = re.fullmatch(r"clc(\d+)", name)
            if m and not missile:
                return self.ev(row, table, table.get(row, f"calc{m.group(1)}"), lvl, blvl)
            m = re.fullmatch(r"ast(\d)", name)
            if m and not missile:
                return self.ev(row, table, table.get(row, f"aurastatcalc{m.group(1)}"), lvl, blvl)
            m = re.fullmatch(r"pst(\d)|ps(\d\d)", name)
            if m and not missile:
                return self.ev(row, table, table.get(row, f"passivecalc{m.group(1) or m.group(2)}"), lvl, blvl)
            if name == "len" and not missile:
                return self.ev(row, table, table.get(row, "auralencalc"), lvl, blvl)
            if name == "rng" and not missile:
                return self.ev(row, table, table.get(row, "aurarangecalc"), lvl, blvl)
            if name in ("edmn", "enma", "edns", "enms"):
                v = self.elem_raw(row, table, lvl, missile)[0]
                return int(v * 256) if name in ("edns", "enms") else int(v)
            if name in ("edmx", "exma", "edxs", "exms"):
                v = self.elem_raw(row, table, lvl, missile)[1]
                return int(v * 256) if name in ("edxs", "exms") else int(v)
            if name in ("damn", "pnma"):
                return int(self.phys_raw(row, table, lvl, missile)[0])
            if name in ("damx", "pxma"):
                return int(self.phys_raw(row, table, lvl, missile)[1])
            if name in ("edln", "edma"):
                return self.elen(row, table, lvl)
            if name == "toht":
                return num(table.get(row, "ToHit")) + (lvl - 1) * num(table.get(row, "LevToHit"))
            if name in ("mana", "usmc"):
                return int(self.mana(row, lvl) * (256 if name == "usmc" else 1))
            self.unknown.add(name)
            return 0

        def call(fn, ref, parts, args):
            if fn == "min":
                return min(args)
            if fn == "max":
                return max(args)
            if fn == "rand":
                return (args[0] + args[1]) // 2
            if fn == "stat":
                return ref_stat(ref, parts[0] if parts else "accr", self.u) * (256 if ref in ("maxhp", "maxmana", "hitpoints") else 1)
            if fn == "miss":
                mrow = self.data.missiles.by.get(ref)
                return self.ev(mrow, self.data.missiles, "", lvl, blvl, True) if mrow is None else \
                    Ctx.ev(self, mrow, self.data.missiles, parts[-1], lvl, blvl, True)
            # skill / sklvl
            srow = self.data.skill(ref)
            if srow is None:
                return 0
            slv, sblvl = self.lvl_of(srow)
            code = parts[-1]
            if fn == "sklvl":   # sklvl('X'.lvl.code): X evaluated at the caller's level
                slv, sblvl = lvl, blvl
            if code == "blvl":
                return sblvl
            if code == "lvl":
                return slv
            if slv == 0:
                return 0
            return self.ev(srow, self.data.skills, code, slv, sblvl)

        try:
            return Parser(tokenize(text), resolve, call).parse()
        except (ValueError, RecursionError) as e:
            self.unknown.add(f"parse:{text[:40]}:{e}")
            return 0

    # ---- damage blocks ------------------------------------------------------------------------------------------
    def cols(self, missile):
        return MS_COLS if missile else SK_COLS

    def _block(self, row, table, lvl, keys, missile):
        c = self.cols(missile)
        lo = bracket(num(table.get(row, c[keys[0]])), [num(table.get(row, x)) for x in c[keys[0] + "l"]], lvl)
        hi = bracket(num(table.get(row, c[keys[1]])), [num(table.get(row, x)) for x in c[keys[1] + "l"]], lvl)
        shift = num(table.get(row, "HitShift"), 8)
        f = 2 ** shift / 256
        return lo * f, hi * f

    def elem_raw(self, row, table, lvl, missile=False):
        return self._block(row, table, lvl, ("emin", "emax"), missile)

    def phys_raw(self, row, table, lvl, missile=False):
        return self._block(row, table, lvl, ("pmin", "pmax"), missile)

    def elen(self, row, table, lvl):
        return len_bracket(num(table.get(row, "ELen")), [num(table.get(row, f"ELevLen{i}")) for i in (1, 2, 3)], lvl)

    def mana(self, row, lvl):
        sk = self.data.skills
        shift = num(sk.get(row, "manashift"), 8)
        cost = (num(sk.get(row, "mana")) + num(sk.get(row, "lvlmana")) * (lvl - 1)) * 2 ** shift / 256
        return max(cost, num(sk.get(row, "minmana")) if cost > 0 else 0)

    def delay(self, row, lvl, blvl):
        return self.ev(row, self.data.skills, self.data.skills.get(row, "localdelay"), lvl, blvl)


def has_damage(table: Table, row, missile: bool) -> bool:
    c = MS_COLS if missile else SK_COLS
    keys = [c["emin"], c["emax"], c["pmin"], c["pmax"], c["src"], *c["eminl"], *c["emaxl"], *c["pminl"], *c["pmaxl"]]
    return any(num(table.get(row, k)) for k in keys)


MISSILE_LINKS = ("SubMissile1", "SubMissile2", "SubMissile3", "HitSubMissile1", "HitSubMissile2", "HitSubMissile3",
                 "HitSubMissile4", "ExplosionMissile")


def damage_source(data: Data, row):
    """(table, row, is_missile): the skill row when it has damage columns, else the first missile (breadth first through
    srvmissile*, sub / hit-sub / explosion missiles) with damage of its own or naming a skill that has some."""
    if has_damage(data.skills, row, False):
        return data.skills, row, False
    sk, ms = data.skills, data.missiles
    queue = [sk.get(row, c) for c in ("srvmissile", "srvmissilea", "srvmissileb", "srvmissilec") if sk.get(row, c)]
    seen = set()
    while queue:
        name = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        m = ms.by.get(name)
        if m is None:
            continue
        ref = ms.get(m, "Skill")
        if ref and ref != row[0] and data.skill(ref) is not None and has_damage(sk, data.skill(ref), False):
            return sk, data.skill(ref), False
        if has_damage(ms, m, True):
            return ms, m, True
        queue += [ms.get(m, c) for c in MISSILE_LINKS if ms.get(m, c)]
    return None, None, False


@dataclass
class Dmg:
    elem: float = 0.0      # elemental average incl. synergy (poison: total over its length)
    phys: float = 0.0      # skill physical average incl. synergy
    weapon: float = 0.0    # SrcDam share of the reference weapon
    esyn: int = 0
    psyn: int = 0
    etype: str = ""
    flat: float = 0.0      # a Warlock weapon skill's flat damage calc (Cleave calc2: D2R's "Flat Damage")

    @property
    def total(self):
        return self.elem + self.phys + self.weapon + self.flat


def damage(data: Data, name: str, s: int, tier: int, cls: str | None = None, weapon_pct: str | None = None,
           flat_calc: str | None = None) -> Dmg:
    """Average damage per hit of a skill's primary damage source at slvl s for the reference character. A Warlock weapon
    skill's damage % (weapon_pct) multiplies the whole hit (weapon, its flat calc and the skill's own elemental block: Mirrored
    Blades' duplicates repeat all of it)."""
    row = data.skill(name)
    cls = cls or data.skills.get(row, "charclass")
    ctx = Ctx(data, cls, s, tier)
    table, src, missile = damage_source(data, row)
    if src is None:
        return Dmg()
    lvl, blvl = s, hard(s)
    emin, emax = ctx.elem_raw(src, table, lvl, missile)
    pmin, pmax = ctx.phys_raw(src, table, lvl, missile)
    etype = table.get(src, "EType")
    e = (emin + emax) / 2
    if etype == "pois":
        e *= max(ctx.elen(src, table, lvl), 1)
    esyn = ctx.ev(src, table, table.get(src, "EDmgSymPerCalc"), lvl, blvl, missile)
    psyn = ctx.ev(src, table, table.get(src, "DmgSymPerCalc"), lvl, blvl, missile)
    srcdam = num(table.get(src, MS_COLS["src"] if missile else "SrcDam"))
    w = data.weapon_avg(ctx.u) * srcdam / 128
    flat = ctx.ev(row, data.skills, flat_calc, lvl, blvl) if flat_calc else 0
    f = 1 + ctx.ev(row, data.skills, weapon_pct, lvl, blvl) / 100 if weapon_pct else 1   # e.g. Cleave clc1
    return Dmg(e * (100 + esyn) / 100 * f, (pmin + pmax) / 2 * (100 + psyn) / 100 * f, w * f, esyn, psyn, etype, flat * f)


def hit_factor(data: Data, spec, s: int, tier: int) -> float:
    """The multiplier a Warlock weapon skill's damage % calc puts on the whole hit (1 for the other skills)."""
    if not spec.weapon_pct:
        return 1.0
    row = data.skill(spec.name)
    ctx = Ctx(data, data.skills.get(row, "charclass"), s, tier)
    return 1 + ctx.ev(row, data.skills, spec.weapon_pct, s, hard(s)) / 100


def mana_cost(data: Data, name: str, s: int) -> float:
    row = data.skill(name)
    return Ctx(data, data.skills.get(row, "charclass"), s, 1).mana(row, s)


def cast_interval(data: Data, name: str, s: int, tier: int) -> float:
    """Frames between casts: the casting delay when it is longer than CAST_FRAMES."""
    row = data.skill(name)
    ctx = Ctx(data, data.skills.get(row, "charclass"), s, tier)
    return max(CAST_FRAMES, ctx.delay(row, s, hard(s)))


# --------------------------------------------------------------------------------------------------------------------
# summons
# --------------------------------------------------------------------------------------------------------------------
FLAT_DMG_STATS = ("item_normaldamage", "mindamage", "secondary_mindamage", "firemindam", "item_throw_mindamage")
HP_COLS = ("minHP", "maxHP", "MinHP(N)", "MaxHP(N)", "MinHP(H)", "MaxHP(H)")


@dataclass
class Minion:
    life: float      # one minion
    damage: float    # one minion, per hit
    count: int       # petmax

    @property
    def army(self):
        return self.damage * max(self.count, 1)


def summon_stats(data: Data, name: str, s: int, tier: int, monster_skill: str | None = None) -> Minion:
    """One minion at slvl s: monster base at monster level u (monstats life x monlvl L-HP, A1 x L-DM) plus the flat maxhp
    passive, x the skill's clc1 life %, damagepercent passives / auras and flat damage passives (only the first of the flat damage
    stats counts: Median writes the same edmx into several of them for melee / ranged / thrown attacks). A caster demon
    (monster_skill) deals that skill's damage instead of its melee attack."""
    row = data.skill(name)
    sk = data.skills
    ctx = Ctx(data, sk.get(row, "charclass"), s, tier)
    u = ctx.u
    mon = data.monstats.by.get(sk.get(row, "summon"))
    lv = data.monlvl.get(u) or data.monlvl[max(data.monlvl)]
    mt = data.monlvl_t
    life = dmg = 0.0
    if mon is not None:
        ms = data.monstats
        life = (num(ms.get(mon, "minHP")) + num(ms.get(mon, "maxHP"))) / 2 * num(mt.get(lv, "L-HP")) / 100
        dmg = (num(ms.get(mon, "A1MinD")) + num(ms.get(mon, "A1MaxD"))) / 2 * num(mt.get(lv, "L-DM")) / 100
    pct, flat, got_flat, life_pct = 0, 0.0, False, 0
    for i in range(1, 15):
        st = sk.get(row, f"passivestat{i}")
        if not st:
            continue
        v = ctx.ev(row, sk, sk.get(row, f"passivecalc{i}"), s, hard(s))
        if st == "maxhp":
            life += v / 256
        elif st == "item_maxhp_percent":
            life_pct += v
        elif st == "damagepercent":
            pct += v
        elif st in FLAT_DMG_STATS and not got_flat:
            flat += v
            got_flat = True
    # Median's own tooltip: life = (base + maxhp passive) x (100 + clc1) / 100 (clc1: the skill's life %)
    life *= (1 + ctx.ev(row, sk, sk.get(row, "calc1"), s, hard(s)) / 100) * (1 + life_pct / 100)
    for i in range(1, 7):
        if sk.get(row, f"aurastat{i}") == "damagepercent":
            pct += ctx.ev(row, sk, sk.get(row, f"aurastatcalc{i}"), s, hard(s))
    if monster_skill:
        dmg = damage(data, monster_skill, s, tier, cls=sk.get(row, "charclass")).total
    count = ctx.ev(row, sk, sk.get(row, "petmax"), s, hard(s)) if sk.get(row, "petmax") else 1
    return Minion(life, (dmg + flat) * (1 + pct / 100), count)


# --------------------------------------------------------------------------------------------------------------------
# the 30 Warlock skills: tier, role, element, comparables and what may change
# --------------------------------------------------------------------------------------------------------------------
@dataclass
class StatCmp:
    """A buff / curse stat of the Warlock skill against Median skills that grant the same stat (absolute values: a
    debuff's -50 and a comparable's -40 compare as 50 vs 40). knobs: Params to fit; empty = compare and report only."""
    stat: str
    comparables: list[str]
    knobs: list[str] = field(default_factory=list)
    comp_stat: str | None = None   # the comparables' stat when it has another name (item_ vs skill_ armour percent)


@dataclass
class Spec:
    name: str
    role: str                 # damage / weapon / summon / buff / curse / passive / utility
    elem: str
    comparables: list[str]
    why: str
    knobs: list[str] = field(default_factory=list)   # 'elem', 'phys', 'Param<n>', 'mana'
    weapon_pct: str | None = None                    # Warlock weapon skill: the calc that adds weapon damage %
    extra_rows: list[tuple[str, str]] = field(default_factory=list)  # (table, row) copies of the damage block (abysscenter)
    monster_skill: str | None = None                 # summon whose damage is a monster skill (Tainted Fire Ball)
    life_knobs: list[str] = field(default_factory=list)   # 'hp' (the demon's monstats life) and / or 'Param<n>'
    damage_knobs_monster: bool = False               # summon damage may also scale the demon's monstats A1 damage
    elem_only: bool = False   # compare the elemental part only (a hex adds it to the Warlock's own attack, like the
    #                           comparables' flat part rides on their weapon hit)
    stats: list[StatCmp] = field(default_factory=list)
    mana_comps: list[str] | None = None              # mana comparables when not the damage comparables
    note: str = ""
    # ---- round 2: Median's rules (rule_cells) and the numbers they need ------------------------------------------
    median_syn: str = ""      # 'spell': Median's spell synergy calc (character level x energy); 'hybrid': Median's
    #                           weapon / hybrid skills' 10*ulvl (their flat part)
    syn_cols: tuple = ("EDmgSymPerCalc",)            # the synergy columns that take it
    flat_calc: str | None = None                     # a weapon skill's flat damage calc (Cleave clc2)
    weapon_knobs: list[str] = field(default_factory=list)  # Params fitted to the comparables' weapon share first
    fixed: list[tuple[str, str, str, int]] = field(default_factory=list)  # (table, row, column, value) set before the fit:
    #                           Median's base values (summon life 1, attack 1-6) and seeds of the new Params / blocks


# Median 2012's own buffs and curses (mana comparables of the Warlock's buffs, sigils and hexes; any tier: their cost is
# a flat cast price, not a damage scale)
MEDIAN_BUFFS = ["Holy Armor", "Lionheart", "Rapture", "Tainted Blood", "Fortress"]
MEDIAN_CURSES = ["Bane", "Bend the Shadows", "Mythal", "Doom", "Colosseum"]
MEDIAN_DEBUFF_SLOW = ["Miasma", "Colosseum", "Screaming Eagle", "Shower of Rocks"]
A1_COLS = ("A1MinD", "A1MaxD", "A1MinD(N)", "A1MaxD(N)", "A1MinD(H)", "A1MaxD(H)")


def median_summon(mon: str, life_seed: tuple[int, int], attack: bool = True) -> list[tuple[str, str, str, int]]:
    """Median's summon base: monstats life 1 and attack 1-6 on every difficulty (shadows_new, lamias, veilkings, ...): the
    minion's life and damage come from the skill (rule_cells adds the maxhp passive), so the demon's monster level (D2R's
    function 56 sets it, not Median's calc2 = ulvl) moves them little. Param1 (D2R's life % per level) 0: Median's life
    per level is the passive's. life_seed: Param15 / Param16 start values (a Median summon's ln34) for the fit."""
    cells = [("monstats", mon, c, 1) for c in HP_COLS]
    if attack:
        cells += [("monstats", mon, c, 1 if "Min" in c else 6) for c in A1_COLS]
    return cells + [("skills", "", "Param1", 0), ("skills", "", "Param15", life_seed[0]), ("skills", "", "Param16", life_seed[1])]


def seed_block(vals: tuple[int, ...]) -> list[tuple[str, str, str, int]]:
    """Start values of a skill row's elemental block (base, Lev1..Lev5; min = max) copied from a Median skill."""
    cols = (SK_COLS["emin"], *SK_COLS["eminl"]), (SK_COLS["emax"], *SK_COLS["emaxl"])
    return [("skills", "", c, v) for half in cols for c, v in zip(half, vals)]


SPECS = [
    # ---- Demon tree (summoner) ---------------------------------------------------------------------------------
    Spec("Summon Goatman", "summon", "phys", ["Summon Shadows", "Guardian Spirit", "Wolf Companion"],
         "tier 1 melee summons (Necromancer, Barbarian x2)", knobs=["eblock", "Param5", "Param6", "mana"],
         life_knobs=["Param15", "Param16"],
         fixed=median_summon("wargoatman", (14, 15)) + seed_block((4, 5, 8, 10, 10, 10))),   # Guardian Spirit's block
    Spec("Demonic Mastery", "passive", "", [], "summon mastery: its numbers feed the demon skills' calcs (speed, damage %, "
         "attack rating), so it is judged through the summons", note="Kept."),
    Spec("Death Mark", "curse", "", [], "mark: the target takes flat extra physical / magic damage (D2R: negative damage "
         "reduction); Doom is Median's skill with the same stat", knobs=["mana"],
         stats=[StatCmp("normal_damage_reduction", ["Doom"], ["Param1", "Param2"])], mana_comps=MEDIAN_CURSES,
         note="Flat damage taken fitted to Doom (magic follows: same calc); mana from Median's curses."),
    Spec("Summon Tainted", "summon", "fire", ["Summon Lamia", "Protector Spirit", "Summon Rampagor"],
         "tier 12 summons (tier 6 Rampagor as the third: Median has two tier-12 summons)",
         knobs=["mana"], life_knobs=["Param15", "Param16"], monster_skill="Tainted Fire Ball",
         fixed=median_summon("warbighead", (59, 20), attack=False)),
    Spec("Summon Defiler", "summon", "phys", ["Summon Veil King", "Summon Lamia", "Summon Void Archon"],
         "tier 18 summon (Veil King) with the tier 12 / 24 summons around it",
         knobs=["eblock", "Param2", "mana"], life_knobs=["Param15", "Param16"],
         fixed=median_summon("warputriddefiler", (199, 50)) + seed_block((239, 60, 60, 60, 60, 60))),   # Veil King's
    Spec("Blood Oath", "passive", "", [], "passive for the demons (damage share, resists, life %)",
         note="Kept, but for its demon life % (Param5 / 6, read only by the demons' clc1): fitted with the three demons' life."),
    Spec("Engorge", "buff", "", [], "demon buff (life steal, attack speed, damage reduction)", knobs=["mana"],
         stats=[StatCmp("lifedrainmindam", ["Eagle Stance", "FamineX"], ["Param11", "Param12"]),
                StatCmp("attackrate", ["Rapture", "Wolf Stance", "Ancient Blood"])],
         mana_comps=MEDIAN_BUFFS, note="Life steal fitted to Median's life-steal skills; mana from Median's buffs."),
    Spec("Blood Boil", "damage", "fire", ["Rain of Fire", "Blood Thorns", "Fireball Sentry"],
         "tier 18 fire area spells", knobs=["elem", "phys", "mana"], median_syn="spell",
         syn_cols=("EDmgSymPerCalc", "DmgSymPerCalc")),
    Spec("Consume", "utility", "", [], "sacrifices a demon for a life / speed buff", knobs=["mana"],
         stats=[StatCmp("item_maxhp_percent", ["Bacchanalia", "Ancient Blood", "Embalming", "Ice Queen"])],
         mana_comps=MEDIAN_BUFFS, note="Life % compared (in range); mana from Median's buffs."),
    Spec("Bind Demon", "utility", "", [], "turns a monster into a demon (bind chance, life, damage %); a channel skill "
         "(mana per frame, manashift 2)", note="Kept: its mana is a channel cost, Median has no channel to compare."),
    # ---- Eldritch tree (blades / hexes) ------------------------------------------------------------------------
    Spec("Levitate", "passive", "", [], "weapon mastery (crit, attack rating, damage %)",
         stats=[StatCmp("passive_mastery_melee_dmg", ["Elfin Arrows"])],
         note="Kept (Median's only same-stat mastery is tier 18; compared in the table)."),
    Spec("Eldritch Blast", "damage", "mag", ["Rising Dawn", "Freezing Gale", "Lava Pit"],
         "tier 24 area spells (magic first)", knobs=["elem", "mana"], median_syn="spell"),
    Spec("Hex Bane", "damage", "mag", ["Ghost Arrow", "Moonbeam", "Laughing Ghost"],
         "tier 1 skills that put flat magic damage on the attack (their flat part)", knobs=["elem", "mana"], elem_only=True,
         median_syn="hybrid",
         stats=[StatCmp("skill_armor_percent", ["Colosseum"]), StatCmp("item_tohit_percent", ["Miasma", "Searing Light"])]),
    Spec("Hex Siphon", "utility", "", [], "hex: life / mana after kill, enemy damage -33 %", knobs=["mana"],
         stats=[StatCmp("damagepercent", ["Miasma", "Colosseum", "Screaming Eagle"])], mana_comps=MEDIAN_CURSES,
         note="Kept; enemy damage -33 % is a literal in the calc (compared in the table); mana from Median's curses."),
    Spec("Psychic Ward", "buff", "", [], "absorb shield; Median has no absorb-amount buff", knobs=["mana"],
         mana_comps=MEDIAN_BUFFS, note="Absorb amount kept (playtest); mana from Median's buffs."),
    Spec("Echoing Strike", "weapon", "phys", ["Enfilade", "Rebound", "Spore Shot"],
         "tier 12 weapon projectiles with flat damage on top", knobs=["phys", "mana"], median_syn="hybrid",
         syn_cols=("DmgSymPerCalc",)),
    Spec("Hex Purge", "damage", "mag", ["Rebound", "Spore Shot", "Egg Trap"],
         "tier 12 skills with a flat magic / fire part (their flat part, like the hex explosion)",
         knobs=["elem", "mana"], elem_only=True, median_syn="hybrid"),
    Spec("Blade Warp", "damage", "mag", ["Barrier Strike", "Dragon Shot", "ParasiteSkill"],
         "tier 18 magic weapon skills (the Warlock's is magic only, no weapon share)", knobs=["elem", "mana"],
         median_syn="hybrid"),
    Spec("Cleave", "weapon", "phys", ["Stampede", "Hyena Strike", "Crucify"],
         "tier 6 melee / weapon skills", knobs=["Param1", "Param2", "Param13", "Param14", "mana"], weapon_pct="clc1",
         flat_calc="clc2", weapon_knobs=["Param1", "Param2", "Param9"],
         fixed=[("skills", "", "Param13", 3), ("skills", "", "Param14", 3)]),
    Spec("Mirrored Blades", "weapon", "phys", ["Great Hunt", "Bladestorm", "Stormblast"],
         "tier 24 weapon skills", knobs=["Param1", "Param2", "elem", "mana"], weapon_pct="(clc5*clc6)-100",
         weapon_knobs=["Param1", "Param2"], median_syn="hybrid",
         fixed=seed_block((4, 4, 4, 4, 4, 4))),   # Bladestorm's flat magic block
    # ---- Chaos tree (sigils / fire / miasma) ---------------------------------------------------------------------
    Spec("Sigil Lethargy", "curse", "", [], "area slow / defence sigil", knobs=["mana"],
         stats=[StatCmp("velocitypercent", MEDIAN_DEBUFF_SLOW), StatCmp("attackrate", ["Shower of Rocks", "Screaming Eagle"]),
                StatCmp("item_armor_percent", ["Colosseum"], comp_stat="skill_armor_percent")],
         mana_comps=MEDIAN_CURSES, note="Percentages kept (compared in the table); mana from Median's curses."),
    Spec("Ring of Fire", "damage", "fire", ["Hunting Banshee", "Thunderstone", "Frigid Sphere"],
         "tier 6 area spells (Ring of Light, the fire one, hits many small ticks and is no per-hit match)",
         knobs=["elem", "mana"], median_syn="spell"),
    Spec("Miasma Bolt", "damage", "mag", ["Magic Missiles", "Searing Light", "Forked Lightning Sor"],
         "tier 1 bolt spells (magic first)", knobs=["elem", "mana"], median_syn="spell"),
    Spec("Sigil Rancor", "curse", "", [], "area sigil: enraged monsters (damage %, attack speed, enrage chance)",
         knobs=["mana"], mana_comps=MEDIAN_CURSES, note="Percentages kept (no Median skill enrages monsters); mana from "
         "Median's curses."),
    Spec("Enhanced Entropy", "passive", "", [], "radius / duration passive for miasma and Abyss", note="Kept."),
    Spec("Flame Wave", "damage", "fire", ["Rain of Fire", "Blood Thorns", "Fireball Sentry"],
         "tier 18 fire spells", knobs=["elem", "mana"], median_syn="spell"),
    Spec("Miasma Chains", "damage", "mag", ["Tempest", "Flamestrike", "Better Bloodstorm"],
         "tier 12 spells (chain lightning first)", knobs=["elem", "mana"], median_syn="spell"),
    Spec("Sigil Death", "curse", "fire", [], "execute sigil (slays below a life %, the explosion is a % of the slain "
         "monster's life)", knobs=["mana"], mana_comps=MEDIAN_CURSES, note="Threshold and explosion % kept (they scale "
         "with the monster by themselves); mana from Median's curses."),
    Spec("Apocalypse", "damage", "fire", ["Lava Pit", "Rising Dawn", "Freezing Gale"],
         "tier 24 area spells (fire first); Warlock reqlevel 30 = Median's top tier", knobs=["elem", "mana"],
         median_syn="spell"),
    Spec("Abyss", "damage", "mag", ["Rising Dawn", "Lava Pit", "Freezing Gale"],
         "tier 24 area spells (magic first); Warlock reqlevel 30 = Median's top tier", knobs=["elem", "mana"],
         extra_rows=[("missiles", "abysscenter")], median_syn="spell"),
]


# --------------------------------------------------------------------------------------------------------------------
# round 2: Median's rules on the Warlock's rows (formula / text cells, data/warlock_rules.tsv)
# --------------------------------------------------------------------------------------------------------------------
MEDIAN_SPELL_FROM = "Rain of Fire"   # Median's spell synergy calc and its tooltip lines are copied from this row
HYBRID_SYN = "10*ulvl"               # Median's weapon / hybrid skills (Ghost Arrow, Great Hunt, Barrier Strike, ...)
SYN_TEXTS = {"Magdplev", "Firedplev", "Damplev"}   # D2R's "+x % damage per level of <skill>" tooltip lines
ELEM_SYN_TEXT = {"fire": "mxl2012:DescFireSyn", "mag": "mxl2012:DescMagSyn", "cold": "mxl2012:DescColdSyn"}
# Cleave: D2R's function 164 adds clc2 ("Flat Damage"); the amount follows Median's weapon skills' flat part x (100 + 10 ulvl) %
CLEAVE_FLAT = "((pa13+((lvl-1)*pa14))*(100+(10*ulvl)))/100"
# the demons: Median's summon life (Summon Shadows / Lamia / Veil King: ((ln34*256)*(100+(ulvl/2)))/100) on Param15 / 16
DEMON_LIFE = "(((pa15+((lvl-1)*pa16))*256)*(100+(ulvl/2)))/100"
# the demons' flat damage: Median's summons read their skill row's (typeless) elemental block, min(edmx,2000) (Summon
# Shadows, Guardian Spirit) / min(edmx,4000) (Veil King, Void Archon): (stat, calc, an existing passive slot to take or None)
DEMONS = {"Summon Goatman": ("item_normaldamage", "min(edmx,2000)", 9), "Summon Tainted": None,
          "Summon Defiler": ("item_normaldamage", "min(edmx,4000)", None)}
DSC3 = ("dsc3line", "dsc3texta", "dsc3textb", "dsc3calca", "dsc3calcb")


def gate_level(data: Data, name: str) -> int:
    """The character level the skill's skpoints gate counts from: its reqlevel, and 0 for reqlevel 1 (Median's tier-1 rows
    write `ulvl`, the others `ulvl-<reqlevel>`)."""
    rl = num(data.skills.get(data.skill(name), "reqlevel"), 1)
    return 0 if rl <= 1 else rl


def skpoints_formula(t: int) -> str:
    """Median 2012's class skill cost (every regular row of the seven classes): one point while the skill has at most one
    hard point per 6 character levels past t (plus the skill_more stat), else more points than the character can have."""
    u = "ulvl" if t == 0 else f"ulvl-{t}"
    return f"(({u})<((blvl-1-stat('skill_more'.accr))*6))?(stat('newskills'.accr)+1):1"


def max_level_calc(t: int, maxlvl: int) -> str:
    """Median's tooltip line "Base Skill Level (Maximum Level Based on Character Level)": the highest base level the gate
    allows, capped where clvl 120 (or the row's maxlvl) stops it."""
    u = "ulvl" if t == 0 else f"(ulvl-{t})"
    cap = min(maxlvl, 2 + (MAX_U - t) // 6)
    return f"max((min((2+({u}/6)),{cap})),2)+stat('skill_more'.accr)"


def dsc3_lines(desc: Table, row) -> list[tuple[str, ...]]:
    return [tuple(desc.get(row, f"{c}{i}") for c in DSC3) for i in range(1, 8) if desc.get(row, f"dsc3line{i}")]


def rebuilt_dsc3(lines: list[tuple[str, ...]], energy: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """The synergy block after the damage synergies left the calc: D2R's per-skill damage lines go, Median's energy lines
    (spells) come right after the header, every other line stays in its order; no header when nothing is left under it."""
    head = [ln for ln in lines if ln[1] == "Sksyn"][:1]
    kept = [ln for ln in lines if ln[1] != "Sksyn" and ln[1] not in SYN_TEXTS]
    body = energy + kept
    return (head + body) if body else []


def rule_cells(data: Data) -> list[tuple[str, str, str, str, str]]:
    """(skill, table, row, column, value) for Median's rules on the Warlock (owner answer 2026-10-28):
    1. skpoints: Median's gate on all 30 rows, and Median's "maximum level" tooltip line (skilldesc dsc2line5);
    2. character-level scaling: Median's spell synergy calc (copied from Rain of Fire) on the 8 spells, 10*ulvl on the
       hybrid / weapon skills' own damage (hexes, Blade Warp, Echoing Strike, Mirrored Blades); D2R's per-skill damage
       synergy lines leave the tooltip, the spells get Median's energy lines;
    3. outliers: Cleave's flat damage (clc2), Mirrored Blades' flat magic damage (EType mag + the block, like Great Hunt /
       Bladestorm), the demons' life (maxhp passive) and the Defiler's flat damage, with their tooltip lines."""
    sk, desc = data.skills, data.skilldesc
    out = []
    src = sk.by.get(MEDIAN_SPELL_FROM)
    spell_syn = sk.get(src, "EDmgSymPerCalc") if src is not None else ""
    if not spell_syn or "ulvl" not in spell_syn:
        raise SystemExit(f"{MEDIAN_SPELL_FROM}: no Median spell synergy calc to copy")
    dsrc = desc.by.get(sk.get(src, "skilldesc")) if desc else None
    src_lines = dsc3_lines(desc, dsrc) if dsrc is not None else []
    energy_tmpl = [ln for ln in src_lines if ln[0] in ("65", "67")]
    maxline = None
    if dsrc is not None:
        for i in range(1, 6):
            if desc.get(dsrc, f"dsc2texta{i}") == "mxl2012:DescMaxLevel2":
                maxline = (desc.get(dsrc, f"dsc2line{i}"), desc.get(dsrc, f"dsc2textb{i}"))
    for sp in SPECS:
        row = sk.by.get(sp.name)
        if row is None:
            continue
        key = sk.get(row, "skilldesc")
        drow = desc.by.get(key) if desc else None
        t = gate_level(data, sp.name)
        out.append((sp.name, "skills", sp.name, "skpoints", skpoints_formula(t)))
        if drow is not None and maxline:
            # the last line of the second block, as Median's rows have it (its highest free slot)
            i = next((i for i in range(5, 0, -1) if not desc.get(drow, f"dsc2line{i}")), None)
            if i is None:
                raise SystemExit(f"skilldesc {key}: no free dsc2line slot for the maximum level line")
            out += [(sp.name, "skilldesc", key, f"dsc2line{i}", maxline[0]),
                    (sp.name, "skilldesc", key, f"dsc2texta{i}", "mxl2012:DescMaxLevel2"),
                    (sp.name, "skilldesc", key, f"dsc2textb{i}", maxline[1]),
                    (sp.name, "skilldesc", key, f"dsc2calca{i}", "blvl"),
                    (sp.name, "skilldesc", key, f"dsc2calcb{i}", max_level_calc(t, num(sk.get(row, "maxlvl"), 20)))]
        if sp.median_syn:
            calc = spell_syn if sp.median_syn == "spell" else HYBRID_SYN
            out += [(sp.name, "skills", sp.name, c, calc) for c in sp.syn_cols]
            if sp.median_syn == "spell":
                # Median's spells count their block in 1/16 points (HitShift 4): with the character-level synergy (up to
                # ~5,800 % at clvl 120) whole points would be far too coarse
                out.append((sp.name, "skills", sp.name, "HitShift", sk.get(src, "HitShift")))
            if drow is not None:
                energy = []
                if sp.median_syn == "spell":
                    if len(energy_tmpl) != 2:
                        raise SystemExit(f"{MEDIAN_SPELL_FROM}'s skilldesc has no energy lines (65 / 67) to copy")
                    a, b = energy_tmpl
                    energy = [(a[0], a[1], ELEM_SYN_TEXT.get(sp.elem, a[2]), a[3], a[4]), b]
                new = rebuilt_dsc3(dsc3_lines(desc, drow), energy)
                for i in range(1, 8):
                    vals = new[i - 1] if i <= len(new) else ("",) * 5
                    for c, v in zip(DSC3, vals):
                        out.append((sp.name, "skilldesc", key, f"{c}{i}", v))
    # 3. the outliers' own formulas and lines
    cl = "Cleave"
    if cl in sk.by:
        out += [(cl, "skills", cl, "calc2", CLEAVE_FLAT)]
        out += _desc_line(data, cl, "descline", ("74", "StrSkillDamageFlat", "", "clc2", ""))
    mb = "Mirrored Blades"
    if mb in sk.by:
        out += [(mb, "skills", mb, "EType", "mag")]
        out += _desc_line(data, mb, "descline", ("75", "StrSkill39", "", "enma", "exma"))
    for name, dmg in DEMONS.items():
        row = sk.by.get(name)
        if row is None:
            continue
        free = _free_passives(sk, row)
        if len(free) < (2 if dmg and not dmg[2] else 1):
            raise SystemExit(f"{name}: no free passivestat slot")
        out += [(name, "skills", name, f"passivestat{free[0]}", "maxhp"),
                (name, "skills", name, f"passivecalc{free[0]}", DEMON_LIFE)]
        life = f"((1+({calc_code(free[0])}/256))*(100+clc1))/100"   # Median's own Life line (Summon Shadows, Veil King)
        out += _replace_desc(data, name, ("13", "StrSkill42"), ("3", "mxl2012:DescPainless", "mxl2012:DescHitPointz", life, ""))
        if dmg:
            stat, calc, slot = dmg
            if slot and sk.get(row, f"passivestat{slot}") != stat:
                raise SystemExit(f"{name}: passivestat{slot} is not {stat}")
            slot = slot or free[1]
            out += [(name, "skills", name, f"passivestat{slot}", stat), (name, "skills", name, f"passivecalc{slot}", calc)]
            if not slot == dmg[2]:   # a new flat damage passive: Median's damage line (Veil King: (1-6 + flat) x damage %)
                dcode = calc_code(slot)
                pct = next((calc_code(i) for i in range(1, 15) if sk.get(row, f"passivestat{i}") == "damagepercent"), "0")
                out += _desc_line(data, name, "descline", ("75", "StrSkill4", "", f"((1+{dcode})*(100+{pct}))/100",
                                                            f"((6+{dcode})*(100+{pct}))/100"))
    return out


def calc_code(slot: int) -> str:
    """The skilldesc calc code of passivecalc<slot> (pst1..pst9, ps10..ps14)."""
    return f"pst{slot}" if slot <= 9 else f"ps{slot}"


def _free_passives(sk: Table, row) -> list[int]:
    return [i for i in range(1, 15) if not sk.get(row, f"passivestat{i}") and not sk.get(row, f"passivecalc{i}")]


DESC_FIELDS = ("line", "texta", "textb", "calca", "calcb")


def _desc_line(data: Data, name: str, prefix: str, vals: tuple[str, ...]) -> list[tuple[str, str, str, str, str]]:
    """Put a line in the first free <prefix> slot (descline1..6) of the skill's skilldesc row."""
    desc = data.skilldesc
    if desc is None:
        return []
    key = data.skills.get(data.skill(name), "skilldesc")
    row = desc.by[key]
    p = "desc" if prefix == "descline" else prefix[:-4]
    for i in range(1, 7):
        if not desc.get(row, f"{prefix}{i}"):
            return [(name, "skilldesc", key, f"{p}{f}{i}", v) for f, v in zip(DESC_FIELDS, vals)]
    raise SystemExit(f"skilldesc {key}: no free {prefix} slot")


def _replace_desc(data: Data, name: str, match: tuple[str, str], vals: tuple[str, ...]) -> list[tuple[str, str, str, str, str]]:
    """Rewrite the descline whose (line type, texta) is `match` (D2R's own Life line of a summon)."""
    desc = data.skilldesc
    if desc is None:
        return []
    key = data.skills.get(data.skill(name), "skilldesc")
    row = desc.by[key]
    for i in range(1, 7):
        if (desc.get(row, f"descline{i}"), desc.get(row, f"desctexta{i}")) == match:
            return [(name, "skilldesc", key, f"desc{f}{i}", v) for f, v in zip(DESC_FIELDS, vals)]
    raise SystemExit(f"skilldesc {key}: no line {match}")


def apply_rules(data: Data, ed: "Edit") -> int:
    """Write rule_cells into the in-memory tables (Edit remembers each cell's value before)."""
    n = 0
    for skill, tname, rowkey, col, value in rule_cells(data):
        t = ed.table(tname)
        if t is None or rowkey not in t.by:
            continue
        if col not in t.ix:
            raise SystemExit(f"{tname}: no column {col!r}")
        if t.get(t.by[rowkey], col) != value:
            ed.set(skill, tname, rowkey, col, value)
            n += 1
    return n


def tier_of(data: Data, name: str) -> int:
    rl = num(data.skills.get(data.skill(name), "reqlevel"), 1)
    return TIER_MAP.get(rl, min(rl, 24))


def target_curve(values: dict[str, list[float]]) -> list[float]:
    return [statistics.median(v[i] for v in values.values()) for i in range(len(SLVLS))]


def comp_damage(data: Data, spec: Spec, tier: int) -> dict[str, list[float]]:
    return {c: [(lambda d: d.elem if spec.elem_only else d.total)(damage(data, c, s, tier)) for s in SLVLS]
            for c in spec.comparables}


def war_damage(data: Data, spec: Spec, tier: int) -> list[float]:
    return [(lambda d: d.elem if spec.elem_only else d.total)(damage(data, spec.name, s, tier, weapon_pct=spec.weapon_pct,
                                                                     flat_calc=spec.flat_calc)) for s in SLVLS]


def cd_factor(data: Data, name: str, tier: int) -> list[float]:
    return [cast_interval(data, name, s, tier) / CAST_FRAMES for s in SLVLS]


def summon_curves(data: Data, name: str, tier: int, monster_skill=None) -> tuple[list[float], list[float]]:
    """(life of one minion, damage of the whole pack) per slvl."""
    ms = [summon_stats(data, name, s, tier, monster_skill) for s in SLVLS]
    return [m.life for m in ms], [m.army for m in ms]


# --------------------------------------------------------------------------------------------------------------------
# small solvers (pure Python: the tool runs under py -3 -I, without site packages)
# --------------------------------------------------------------------------------------------------------------------
def solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting (a is n x n)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-15:
            continue
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-15 else 0.0 for i in range(n)]


def least_squares(resid, x0: list[float], iters: int = 200) -> list[float]:
    """Levenberg-Marquardt with a forward-difference Jacobian; returns x minimising sum(resid(x)^2)."""
    x = list(x0)
    r = resid(x)
    cost = sum(v * v for v in r)
    lam = 1e-3
    for _ in range(iters):
        h = 1e-6
        jac = []
        for j in range(len(x)):
            xp = x[:]
            xp[j] += h
            rp = resid(xp)
            jac.append([(a - b) / h for a, b in zip(rp, r)])
        jtj = [[sum(jac[i][k] * jac[j][k] for k in range(len(r))) for j in range(len(x))] for i in range(len(x))]
        jtr = [sum(jac[i][k] * r[k] for k in range(len(r))) for i in range(len(x))]
        improved = False
        for _ in range(20):
            a = [[jtj[i][j] + (lam * (jtj[i][i] or 1.0) if i == j else 0.0) for j in range(len(x))] for i in range(len(x))]
            step = solve(a, [-v for v in jtr])
            xn = [xi + si for xi, si in zip(x, step)]
            rn = resid(xn)
            cn = sum(v * v for v in rn)
            if cn < cost:
                x, r, cost, lam, improved = xn, rn, cn, max(lam / 10, 1e-9), True
                break
            lam *= 10
        if not improved or max(abs(s) for s in step) < 1e-9:
            break
    return x


def pattern_search(cost, x0: list[float], step: float = 1.0, tol: float = 1e-3, max_evals: int = 6000) -> list[float]:
    """Hooke-Jeeves search (cost may be piecewise constant: the cells are rounded integers)."""
    x = list(x0)
    best = cost(x)
    evals = 1
    while step > tol and evals < max_evals:
        moved = False
        for j in range(len(x)):
            for d in (step, -step):
                xn = x[:]
                xn[j] += d
                c = cost(xn)
                evals += 1
                if c < best - 1e-12:
                    x, best, moved = xn, c, True
                    break
        if not moved:
            step /= 2
    return x


# --------------------------------------------------------------------------------------------------------------------
# fitting
# --------------------------------------------------------------------------------------------------------------------
class Edit:
    """Cell edits on the in-memory tables (rows are shared, so damage() sees them at once); remembers D2R's value."""

    def __init__(self, data: Data):
        self.data, self.cells = data, {}

    def table(self, name) -> Table:
        return {"skills": self.data.skills, "missiles": self.data.missiles, "monstats": self.data.monstats,
                "skilldesc": self.data.skilldesc}[name]

    def set(self, skill, tname, rowkey, col, value):
        t = self.table(tname)
        row = t.by[rowkey]
        i = t.ix[col]
        key = (tname, rowkey, col)
        if key not in self.cells:
            self.cells[key] = [skill, row[i], None]
        row[i] = str(value)
        self.cells[key][2] = str(value)


def block_cols(kind: str, missile: bool) -> list[str]:
    c = MS_COLS if missile else SK_COLS
    a, b = ("emin", "emax") if kind == "elem" else ("pmin", "pmax")
    return [c[a], *c[a + "l"], c[b], *c[b + "l"]]


def level_counts(s: int) -> list[int]:
    """How many times each position (base, Lev1..Lev5) counts at slvl s."""
    c = [1, 0, 0, 0, 0, 0]
    for L in range(2, s + 1):
        c[1 + (0 if L <= 8 else 1 if L <= 16 else 2 if L <= 22 else 3 if L <= 28 else 4)] += 1
    return c


def fit_block(data: Data, ed: Edit, owner: str, skill: str, kind: str, target_part: list[float], tier: int, cls: str,
              mult_extra: list[float] | None = None, tname: str = "skills") -> None:
    """Scale the six positions (base, Lev1..Lev5) of a row's elemental / physical block (a skill row, or a missile row with
    tname="missiles"), min and max alike (D2R's min / max shape kept), so the block lands on target_part over slvl 1..40.
    The block is linear in its values once the synergy % (the row's own calc) and the poison length are known, so this is a
    smooth least-squares problem on the log ratio, with a smoothness term between neighbouring positions; the result is
    rounded to whole cells. mult_extra: a per-slvl factor on the block (a weapon skill's damage % on the whole hit)."""
    missile = tname == "missiles"
    t = ed.table(tname)
    row = t.by[skill]
    cols = block_cols(kind, missile)
    orig = [num(t.get(row, c)) for c in cols]
    avg = [(orig[i] + orig[i + 6]) / 2 for i in range(6)]
    if not any(avg):
        return
    ctx = Ctx(data, cls, 1, tier)
    f = 2 ** num(t.get(row, "HitShift"), 8) / 256
    mult = []
    for j, s in enumerate(SLVLS):
        ctx.s = s
        syn = ctx.ev(row, t, t.get(row, "EDmgSymPerCalc" if kind == "elem" else "DmgSymPerCalc"), s, hard(s), missile)
        ln = ctx.elen(row, t, s) if kind == "elem" and t.get(row, "EType") == "pois" else 1
        mult.append(f * (100 + syn) / 100 * max(ln, 1) * (mult_extra[j] if mult_extra else 1))
    counts = [level_counts(s) for s in SLVLS]
    active = [i for i in range(6) if avg[i]]

    def model(k):
        return [m * sum(c[i] * avg[i] * k[i] for i in range(6)) for m, c in zip(mult, counts)]

    def full(x):
        k = [1.0] * 6
        for j, i in enumerate(active):
            k[i] = math.exp(x[j])
        return k

    def resid(x):
        got = model(full(x))
        r = [math.log(max(g, 1e-9)) - math.log(max(tg, 1e-9)) for g, tg in zip(got, target_part)]
        return r + [0.5 * (x[j] - x[j + 1]) for j in range(len(active) - 1)]

    k = full(least_squares(resid, [0.0] * len(active)))
    new = [max(0, round(orig[i] * k[i % 6])) for i in range(12)]
    for i in range(6):
        if orig[i] and not new[i]:
            new[i] = 1
        if orig[i + 6] and not new[i + 6]:
            new[i + 6] = 1
        new[i + 6] = max(new[i + 6], new[i])
    for c, o, v in zip(cols, orig, new):
        if v != o:
            ed.set(owner, tname, skill, c, v if v else "")


def missile_elem(data: Data, mrow_key: str, s: int, tier: int, cls: str) -> float:
    """Average elemental damage of a missile row's own block with its own synergy calc (abysscenter)."""
    ms = data.missiles
    row = ms.by[mrow_key]
    ctx = Ctx(data, cls, s, tier)
    lo, hi = ctx.elem_raw(row, ms, s, True)
    syn = ctx.ev(row, ms, ms.get(row, "EDmgSymPerCalc"), s, hard(s), True)
    return (lo + hi) / 2 * (100 + syn) / 100


def fit_cells(data: Data, ed: Edit, owner: str, groups: list[list[tuple[str, str, str]]], metric, target: list[float],
              more: list[tuple] = ()) -> None:
    """Scale groups of integer cells (each group by one factor, signs kept) so metric(s) lands on the target: Powell search
    on the log scale factors with the cells rounded as they will be written (the calcs use integer arithmetic). more:
    further (metric, target) curves fitted at the same time (cells shared by several skills: Blood Oath's demon life)."""
    curves = [(metric, target), *more]
    cells = [[(tn, rk, c, num(ed.table(tn).get(ed.table(tn).by[rk], c))) for tn, rk, c in g] for g in groups]
    cells = [g for g in cells if any(o for *_, o in g)]
    if not cells:
        return

    def put(x):
        for g, v in zip(cells, x):
            k = math.exp(v)
            for tn, rk, c, o in g:
                if not o:
                    continue
                t = ed.table(tn)
                n = int(round(o * k))
                if n == 0:
                    n = 1 if o > 0 else -1
                t.by[rk][t.ix[c]] = str(n)

    def cost(x):
        put(x)
        r = [math.log(max(m(s), 1e-9)) - math.log(max(t[i], 1e-9)) for m, t in curves for i, s in enumerate(SLVLS)]
        return sum(v * v for v in r) / len(curves) + 0.001 * sum(v * v for v in x)

    best = pattern_search(cost, [0.0] * len(cells))
    put([0.0] * len(cells))
    for g, v in zip(cells, best):
        k = math.exp(v)
        for tn, rk, c, o in g:
            if not o:
                continue
            n = int(round(o * k))
            if n == 0:
                n = 1 if o > 0 else -1
            if n != o:
                ed.set(owner, tn, rk, c, n)


def mana_comps(data: Data, spec: Spec, tier: int) -> list[str]:
    if spec.mana_comps:
        return spec.mana_comps
    return spec.comparables if spec.role in ("damage", "weapon", "summon") else MANA_TIER_COMPS[tier]


def fit_mana(data: Data, ed: Edit, spec: Spec, comps: list[str]) -> None:
    """mana / lvlmana (manashift kept) by linear least squares on the median of the comparables' cost, slvl 1..40."""
    sk = data.skills
    row = data.skill(spec.name)
    target = [statistics.median(mana_cost(data, c, s) for c in comps) for s in SLVLS]
    f = 2 ** num(sk.get(row, "manashift"), 8) / 256
    n = len(SLVLS)
    xs = [s - 1 for s in SLVLS]
    ys = [t / f for t in target]
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    a = my - b * mx
    a, b = max(1, round(a)), round(b)
    if a + b * 39 < 1:
        b = 0
    for col, v in (("mana", a), ("lvlmana", b)):
        if num(sk.get(row, col)) != v:
            ed.set(spec.name, "skills", spec.name, col, v)


MANA_TIER_COMPS = {1: ["Magic Missiles", "Searing Light", "Forked Lightning Sor", "Flamefront", "Cold Blood"],
                   6: ["Hunting Banshee", "Thunderstone", "Frigid Sphere", "Lemures", "Mind Flay"],
                   12: ["Tempest", "Flamestrike", "Better Bloodstorm", "Fireheart Totem", "Miasma"],
                   18: ["Rain of Fire", "Blood Thorns", "Fireball Sentry", "Carpet of Spiders", "Abyss_mxl"],
                   24: ["Rising Dawn", "Freezing Gale", "Lava Pit", "Stormeye Totem", "Nova Charge"]}


def hp_group(data: Data, spec: Spec) -> list[tuple[str, str, str]]:
    mon = data.skills.get(data.skill(spec.name), "summon")
    return [("monstats", mon, c) for c in HP_COLS]


CALC_COLS = ([f"calc{i}" for i in range(1, 11)] + [f"aurastatcalc{i}" for i in range(1, 7)] +
             [f"passivecalc{i}" for i in range(1, 15)] + ["auralencalc", "aurarangecalc", "petmax"])
LN_PAIRS = {"12": (1, 2), "34": (3, 4), "56": (5, 6), "78": (7, 8), "91": (9, 10), "21": (11, 12)}


def params_in_calcs(data: Data, name: str) -> set[int]:
    """Param numbers a skill row's own calc columns read (parN / paNN, lnXY / dmXY)."""
    row, sk, used = data.skill(name), data.skills, set()
    for c in CALC_COLS:
        text = sk.get(row, c)
        for m in re.finditer(r"\b(?:par(\d)|pa(\d\d))\b", text):
            used.add(int(m.group(1) or m.group(2)))
        for m in re.finditer(r"\b(?:ln|dm)(12|34|56|78|91|21)\b", text):
            used.update(LN_PAIRS[m.group(1)])
    return used


def param_group(spec: Spec, p: str, skill: str | None = None, data: Data | None = None) -> list[tuple[str, str, str]]:
    """A Param knob; only Params a calc of the row reads (D2R's do functions also read Params directly, as radius, count
    or timing: those are mechanics and stay)."""
    if data is not None and int(p[5:]) not in params_in_calcs(data, skill or spec.name):
        raise SystemExit(f"{skill or spec.name} {p}: no calc of the row reads it (a do function may: not a knob)")
    return [("skills", skill or spec.name, p)]


def a1_group(data: Data, spec: Spec) -> list[tuple[str, str, str]]:
    mon = data.skills.get(data.skill(spec.name), "summon")
    return [("monstats", mon, c) for c in A1_COLS]


def stat_value(data: Data, name: str, stat: str, s: int, tier: int) -> float:
    """The value a skill grants for a stat at slvl s (first aurastat / passivestat naming it), absolute."""
    row, sk = data.skill(name), data.skills
    ctx = Ctx(data, sk.get(row, "charclass"), s, tier)
    for col, calc in [(f"aurastat{i}", f"aurastatcalc{i}") for i in range(1, 7)] + \
                     [(f"passivestat{i}", f"passivecalc{i}") for i in range(1, 15)]:
        if sk.get(row, col) == stat:
            return abs(ctx.ev(row, sk, sk.get(row, calc), s, hard(s)))
    return 0.0


def fit_spec(data: Data, ed: Edit, spec: Spec) -> dict:
    """Fit one skill; returns the curves (before / after / target) for the report."""
    tier = tier_of(data, spec.name)
    cls = data.skills.get(data.skill(spec.name), "charclass")
    info = {"tier": tier}
    for tname, rk, col, v in spec.fixed:   # Median's base values and the seeds of the new Params / blocks
        ed.set(spec.name, tname, rk or spec.name, col, v)
    if spec.role in ("damage", "weapon"):
        comps = comp_damage(data, spec, tier)
        cdf = cd_factor(data, spec.name, tier)
        target = [t * f for t, f in zip(target_curve(comps), cdf)]
        info.update(comps=comps, target=target, cd=cdf, before=war_damage(data, spec, tier))

        def wd(s):
            return damage(data, spec.name, s, tier, weapon_pct=spec.weapon_pct, flat_calc=spec.flat_calc)
        if spec.weapon_knobs:
            # weapon share against the comparables' weapon share; their flat / elemental part is then the rest (below)
            t_w = [statistics.median(damage(data, c, s, tier).weapon for c in spec.comparables) * f
                   for s, f in zip(SLVLS, cdf)]
            fit_cells(data, ed, spec.name, [param_group(spec, p, data=data) for p in spec.weapon_knobs],
                      lambda s: wd(s).weapon, t_w)
            info["target_weapon"] = t_w
        parts = [wd(s) for s in SLVLS]
        hf = [hit_factor(data, spec, s, tier) for s in SLVLS] if spec.weapon_pct else None
        for kind in [k for k in ("elem", "phys") if k in spec.knobs]:
            own = [p.elem if kind == "elem" else p.phys for p in parts]
            if not any(own):
                continue
            # each block takes the share of the target it has of the skill's own damage now; the weapon share stays
            fixed = [0.0 if spec.elem_only else p.weapon + p.flat for p in parts]
            mine = [p.elem if spec.elem_only else p.elem + p.phys for p in parts]
            tgt = [max(t - fx, t * 0.05) * (o / m if m else 0) for t, fx, o, m in zip(target, fixed, own, mine)]
            fit_block(data, ed, spec.name, spec.name, kind, tgt, tier, cls, mult_extra=hf)
        for tname, rkey in spec.extra_rows:
            # a missile with a copy of the block (abysscenter, Abyss' damage over time) keeps its own D2R synergy calc
            # (missile calcs have no ulvl / energy): its block is fitted to the skill row's new damage
            row_dmg = [damage(data, spec.name, s, tier).elem for s in SLVLS]
            fit_block(data, ed, spec.name, rkey, "elem", row_dmg, tier, cls, tname=tname)
            info.setdefault("copies", {})[rkey] = (row_dmg, [missile_elem(data, rkey, s, tier, cls) for s in SLVLS])
        pk = [k for k in spec.knobs if k.startswith("Param") and k not in spec.weapon_knobs]
        if pk:
            fit_cells(data, ed, spec.name, [param_group(spec, p, data=data) for p in pk], lambda s: wd(s).total, target)
        info["after"] = war_damage(data, spec, tier)
    elif spec.role == "summon":
        cl = {c: summon_curves(data, c, tier) for c in spec.comparables}
        t_life = target_curve({c: v[0] for c, v in cl.items()})
        t_dmg = target_curve({c: v[1] for c, v in cl.items()})
        b_life, b_dmg = summon_curves(data, spec.name, tier, spec.monster_skill)
        info.update(comps_life={c: v[0] for c, v in cl.items()}, comps_dmg={c: v[1] for c, v in cl.items()},
                    target_life=t_life, target_dmg=t_dmg, before_life=b_life, before_dmg=b_dmg)
        groups = [hp_group(data, spec) if k == "hp" else param_group(spec, k, data=data) for k in spec.life_knobs]
        fit_cells(data, ed, spec.name, groups, lambda s: summon_stats(data, spec.name, s, tier, spec.monster_skill).life,
                  t_life)
        dk = [k for k in spec.knobs if k.startswith("Param")]
        if dk or "eblock" in spec.knobs:
            # the flat damage block (min and max of each position together) with the damage % Params
            eb = [[("skills", spec.name, a), ("skills", spec.name, b)] for a, b in
                  zip((SK_COLS["emin"], *SK_COLS["eminl"]), (SK_COLS["emax"], *SK_COLS["emaxl"]))] if "eblock" in spec.knobs else []
            fit_cells(data, ed, spec.name, eb + [param_group(spec, p, data=data) for p in dk] + ([a1_group(data, spec)] if spec.damage_knobs_monster else []),
                      lambda s: summon_stats(data, spec.name, s, tier, spec.monster_skill).army, t_dmg)
        elif spec.monster_skill:   # a caster demon: its monster skill's elemental block, per pack
            per = [summon_stats(data, spec.name, s, tier, spec.monster_skill) for s in SLVLS]
            own = [damage(data, spec.monster_skill, s, tier, cls=cls).elem for s in SLVLS]
            tgt = [t * o / max(m.army, 1e-9) for t, o, m in zip(t_dmg, own, per)]
            fit_block(data, ed, spec.name, spec.monster_skill, "elem", tgt, tier, cls)
        a_life, a_dmg = summon_curves(data, spec.name, tier, spec.monster_skill)
        info.update(after_life=a_life, after_dmg=a_dmg)
    if spec.stats:
        info["stats"] = []
        for sc in spec.stats:
            before = [stat_value(data, spec.name, sc.stat, s, tier) for s in SLVLS]
            comps = {c: [stat_value(data, c, sc.comp_stat or sc.stat, s, tier) for s in SLVLS] for c in sc.comparables}
            target = target_curve(comps)
            if sc.knobs:
                fit_cells(data, ed, spec.name, [param_group(spec, p, data=data) for p in sc.knobs],
                          lambda s, sc=sc: stat_value(data, spec.name, sc.stat, s, tier), target)
            after = [stat_value(data, spec.name, sc.stat, s, tier) for s in SLVLS]
            info["stats"].append((sc, comps, target, before, after))
    if "mana" in spec.knobs:
        comps = mana_comps(data, spec, tier)
        info["mana_comps"] = comps
        info["mana_before"] = [mana_cost(data, spec.name, s) for s in SLVLS]
        info["mana_target"] = [statistics.median(mana_cost(data, c, s) for c in comps) for s in SLVLS]
        fit_mana(data, ed, spec, comps)
        info["mana_after"] = [mana_cost(data, spec.name, s) for s in SLVLS]
    return info


# --------------------------------------------------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------------------------------------------------
def default_excel() -> Path:
    return ROOT / "work" / "mod" / EXCEL


def fmt(v: float) -> str:
    return f"{v:.0f}" if abs(v) >= 10 or v == 0 else f"{v:.1f}"


def pick(curve: list[float]) -> str:
    return " / ".join(fmt(curve[s - 1]) for s in SHOW)


def cmd_fit(excel: Path) -> int:
    data = Data(excel)
    missing = [c for sp in SPECS for c in [sp.name, *sp.comparables] if data.skill(c) is None]
    if missing:
        print("missing skills:", missing)
        return 1
    if any(num(data.skills.get(data.skill(sp.name), "*Id")) not in range(373, 403) for sp in SPECS):
        print("Warlock rows are not at D2R's ids 373-402")
        return 1
    # refit from D2R's tables: a cell the previous fit / rules set (and the build applied) goes back to its value before
    revert(data, load_tsv(TSV))
    revert(data, load_tsv(RULES_TSV))
    pre = {sp.name: measures(data, sp) for sp in SPECS}   # D2R's Warlock, before the rules and the numbers
    rules = Edit(data)
    apply_rules(data, rules)
    nr = write_cells(RULES_TSV, rules.cells)
    ed = Edit(data)
    infos = {}
    for sp in SPECS:
        infos[sp.name] = fit_spec(data, ed, sp)
        infos[sp.name].update(pre[sp.name])
    fit_shared_life(data, ed, infos)
    nb = write_cells(TSV, ed.cells)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "fit_report.md").write_text(report(data, infos, ed.cells, rules.cells), encoding="utf-8")
    print(f"{nr} rule cells -> {RULES_TSV.relative_to(ROOT)}, {nb} number cells -> {TSV.relative_to(ROOT)}; "
          f"report {OUTDIR.relative_to(ROOT) / 'fit_report.md'}")
    return 0


# Blood Oath's demon life % (ln56 = Param5 + Param6 per level) is read only by the three demons' clc1 (and its own tooltip
# line): a shared knob of their life, fitted on all three curves at once
SHARED_LIFE = ("Blood Oath", ("Param5", "Param6"))


def fit_shared_life(data: Data, ed: Edit, infos: dict, rounds: int = 2) -> None:
    """Blood Oath's life % against the three demons' life targets, then each demon's own life Params again."""
    owner, params = SHARED_LIFE
    if data.skill(owner) is None:
        return
    demons = [sp for sp in SPECS if sp.role == "summon" and sp.life_knobs and sp.name in infos]
    if not demons:
        return

    def life_of(sp):
        tier = infos[sp.name]["tier"]
        return lambda s: summon_stats(data, sp.name, s, tier, sp.monster_skill).life

    for _ in range(rounds):
        curves = [(life_of(sp), infos[sp.name]["target_life"]) for sp in demons]
        fit_cells(data, ed, owner, [[("skills", owner, p)] for p in params], *curves[0], more=curves[1:])
        for sp in demons:
            fit_cells(data, ed, sp.name, [param_group(sp, k, data=data) for k in sp.life_knobs], *curves[demons.index(sp)])
    for sp in demons:
        a_life, a_dmg = summon_curves(data, sp.name, infos[sp.name]["tier"], sp.monster_skill)
        infos[sp.name].update(after_life=a_life, after_dmg=a_dmg)


def revert(data: Data, edits: list[dict]) -> None:
    ed0 = Edit(data)
    for e in edits:
        t = ed0.table(e["table"])
        r = t.by.get(e["row"]) if t is not None else None
        if r is not None and e["column"] in t.ix and r[t.ix[e["column"]]] == e["new"]:
            r[t.ix[e["column"]]] = e["d2r"]


def write_cells(path: Path, cells: dict) -> int:
    """skill, table, row, column, value before, new value (sorted by the skill's place in SPECS, then the cell)."""
    order = [s.name for s in SPECS]
    lines = ["\t".join(("skill", "table", "row", "column", "d2r", "new"))]
    for (tname, rowkey, col), (skill, old, new) in sorted(cells.items(), key=lambda kv: (order.index(kv[1][0]), kv[0])):
        if old != new:
            lines.append("\t".join((skill, tname, rowkey, col, str(old), str(new))))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(lines) - 1


def measures(data: Data, sp: Spec) -> dict:
    """The skill's measures on the tables as they are (cmd_fit: D2R's), for the report's "D2R" column."""
    tier = tier_of(data, sp.name)
    if sp.role in ("damage", "weapon"):
        return {"before": war_damage(data, sp, tier)}
    if sp.role == "summon":
        life, dmg = summon_curves(data, sp.name, tier, sp.monster_skill)
        return {"before_life": life, "before_dmg": dmg}
    return {}


TABLE_SLVLS = (1, 20, 40)


def tri(curve: list[float]) -> str:
    return " / ".join(fmt(curve[s - 1]) for s in TABLE_SLVLS)


def summary_table(infos: dict, cells: dict) -> list[str]:
    """The per-skill table of docs/warlock-balance.md: values at slvl 1 / 20 / 40."""
    out = ["| Skill | Tier | Role | Comparables | Measure | D2R | Median target | New | Cells |", "|---|---|---|---|---|---|---|---|---|"]
    for sp in SPECS:
        i = infos[sp.name]
        n = sum(1 for k, (sk, old, new) in cells.items() if sk == sp.name and old != new)
        comps = ", ".join(sp.comparables or dict.fromkeys(c for sc in sp.stats for c in sc.comparables)) or "-"
        if sp.mana_comps:
            comps += "; mana: Median's " + ("curses" if sp.mana_comps is MEDIAN_CURSES else "buffs")
        role = f"{sp.role}{' ' + sp.elem if sp.elem else ''}"
        rows = []
        if "target" in i:
            rows.append(("damage" + (" (flat part)" if sp.elem_only else ""), i["before"], i["target"], i["after"]))
        if "target_life" in i:
            rows.append(("minion life", i["before_life"], i["target_life"], i["after_life"]))
            rows.append(("pack damage", i["before_dmg"], i["target_dmg"], i["after_dmg"]))
        for sc, cmp, target, before, after in i.get("stats", []):
            rows.append((f"{sc.stat}{'' if sc.knobs else ' (kept)'}", before, target, after))
        if "mana_before" in i:
            rows.append(("mana", i["mana_before"], i["mana_target"], i["mana_after"]))
        if not rows:
            what = "kept" if not n else "demon life % fitted with the demons" if sp.name == SHARED_LIFE[0] else "changed"
            out.append(f"| {sp.name} | {i['tier']} | {role} | {comps} | - | | | {what} | {n} |")
        for j, (what, b, t, a) in enumerate(rows):
            head = f"| {sp.name} | {i['tier']} | {role} | {comps}" if j == 0 else "| | | |"
            out.append(f"{head} | {what} | {tri(b)} | {tri(t)} | {tri(a)} | {n if j == 0 else ''} |")
    return out


def report(data: Data, infos: dict, cells: dict | None = None, rule_cells_: dict | None = None) -> str:
    out = ["# Warlock balance fit (generated by tools/warlock_scale.py fit)", "",
           f"Values at slvl {' / '.join(map(str, SHOW))}; damage = average per hit / cast incl. synergy for the reference "
           "character; target = median of the comparables x casting-delay factor.", "",
           "## Summary (slvl 1 / 20 / 40)", "", *summary_table(infos, cells or {}), ""]
    for sp in SPECS:
        i = infos[sp.name]
        out.append(f"## {sp.name} (tier {i['tier']}, {sp.role}{', ' + sp.elem if sp.elem else ''})")
        out.append(f"Comparables: {', '.join(sp.comparables) or '-'} ({sp.why}). {sp.note}")
        out.append("")
        if "target" in i:
            for c, v in i["comps"].items():
                out.append(f"- {c}: {pick(v)}")
            out.append(f"- target: {pick(i['target'])} (delay factor {pick(i['cd'])})")
            out.append(f"- Warlock before: {pick(i['before'])}")
            out.append(f"- Warlock after: {pick(i['after'])}")
        if "target_life" in i:
            for c in sp.comparables:
                out.append(f"- {c}: life {pick(i['comps_life'][c])}; damage {pick(i['comps_dmg'][c])}")
            out.append(f"- target: life {pick(i['target_life'])}; damage {pick(i['target_dmg'])}")
            out.append(f"- Warlock before: life {pick(i['before_life'])}; damage {pick(i['before_dmg'])}")
            out.append(f"- Warlock after: life {pick(i['after_life'])}; damage {pick(i['after_dmg'])}")
        for sc, comps, target, before, after in i.get("stats", []):
            cmp = "; ".join(f"{c} {pick(v)}" for c, v in comps.items())
            out.append(f"- {sc.stat} (absolute): Warlock {pick(before)} -> {pick(after)}; Median {cmp}; median {pick(target)}"
                       f"{' (fitted)' if sc.knobs else ' (compared only)'}")
        if "mana_before" in i:
            out.append(f"- mana: before {pick(i['mana_before'])}, target {pick(i['mana_target'])}, after {pick(i['mana_after'])}")
        out.append("")
    return "\n".join(out) + "\n"


def load_tsv(path: Path = TSV) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t") + [""] * (len(head) - len(ln.split("\t"))))) for ln in lines[1:] if ln.strip()]


def apply(mod: Path, edits: list[dict], label: str = "") -> list[str]:
    """Write the edits into the RotW bank (the only bank with the Warlock: the Classic / LoD bank has id placeholders for
    its rows and is not touched). A cell whose value is neither the recorded one before nor already the new one stops the
    step (D2R or the migration changed the row: refit)."""
    from txt_migrate import write_tsv
    log = []
    d = mod / EXCEL / BANKS[0]
    for tname in sorted({e["table"] for e in edits}):
        p = d / f"{tname}.txt"
        if not p.exists():
            raise SystemExit(f"warlock_scale: rotw {tname}.txt is missing")
        h, rows = read_tsv(p)
        ix = {c: i for i, c in enumerate(h)}
        by = {}
        for r in rows:
            if is_record(r):
                by.setdefault(r[0], r)
        n = 0
        for e in edits:
            if e["table"] != tname:
                continue
            r = by.get(e["row"])
            if r is None or e["column"] not in ix:
                raise SystemExit(f"warlock_scale: rotw {tname}: no row {e['row']!r} / column {e['column']!r}")
            while len(r) < len(h):
                r.append("")
            cur = r[ix[e["column"]]]
            if cur == e["new"]:
                continue
            if cur != e["d2r"]:
                raise SystemExit(f"warlock_scale: rotw {tname} {e['row']} {e['column']} is {cur!r}, "
                                 f"expected {e['d2r']!r}: refit (tools/warlock_scale.py fit)")
            r[ix[e["column"]]] = e["new"]
            n += 1
        write_tsv(p, h, rows)
        log.append(f"rotw {tname}: {n} {label}cells")
    return log


def cmd_apply(mod: Path) -> int:
    rules, edits = load_tsv(RULES_TSV), load_tsv()
    if not rules and not edits:
        print("warlock_scale: no data/warlock_rules.tsv / warlock_balance.tsv, nothing to do")
        return 0
    for line in apply(mod, rules, "rule ") + apply(mod, edits):   # the rules first: the numbers' Params sit in their calcs
        print(f"   {line}")
    print(f"warlock_scale: {len(rules)} rule cells (data/warlock_rules.tsv) and {len(edits)} number cells "
          "(data/warlock_balance.tsv) set on the Warlock (docs/warlock-balance.md)")
    return 0


# ---- sanity check: time to kill ---------------------------------------------------------------------------------
DIFFS = (("normal", "", "L-HP"), ("nightmare", "(N)", "L-HP(N)"), ("hell", "(H)", "L-HP(H)"))


def average_monster_life(data: Data) -> dict[str, float]:
    """Median of the regular monsters' average base life per difficulty (enabled, killable, no npc / boss / town)."""
    ms = data.monstats
    out = {}
    for diff, suf, _ in DIFFS:
        vals = []
        for r in ms.rows:
            if ms.get(r, "enabled") != "1" or ms.get(r, "killable") != "1" or ms.get(r, "npc") == "1" \
                    or ms.get(r, "boss") == "1" or ms.get(r, "inTown") == "1" or not num(ms.get(r, "Level" + suf)):
                continue
            v = (num(ms.get(r, "minHP" if not suf else f"MinHP{suf}")) + num(ms.get(r, "maxHP" if not suf else f"MaxHP{suf}"))) / 2
            if v > 0:
                vals.append(v)
        out[diff] = statistics.median(vals) if vals else 1.0
    return out


def slvl_at(u: int, tier: int) -> int:
    return max(1, min(40, 1 + (u - tier) // 3)) if u >= tier else 0


def dps(data: Data, sp: Spec, name: str, s: int, tier: int, warlock: bool) -> float:
    if sp.role == "summon":
        m = summon_stats(data, name, s, tier, sp.monster_skill if warlock else None)
        return m.army * 25 / CAST_FRAMES   # the whole pack, one hit each per CAST_FRAMES
    dd = damage(data, name, s, tier, weapon_pct=sp.weapon_pct if warlock else None, flat_calc=sp.flat_calc if warlock else None)
    d = dd.elem if sp.elem_only else dd.total   # a hex: its flat part vs the comparables' flat part (weapon on both sides)
    return d * 25 / cast_interval(data, name, s, tier)


def cmd_ttk(excel: Path) -> int:
    data = Data(excel)
    base = average_monster_life(data)
    out = ["# Warlock time-to-kill check (tools/warlock_scale.py ttk)", "",
           "Average Median monster (median base life of regular monsters) x monlvl L-HP at the area level; character level = "
           "area level, slvl from the reference model; one target, no resistances, casts every "
           f"{CAST_FRAMES} frames or the casting delay. Ratio = Warlock TTK / median comparable TTK; flagged beyond "
           f"+-{int(OUTLIER * 100)} %.", "",
           f"Base life: " + ", ".join(f"{k} {v:.0f}" for k, v in base.items()), "",
           "| Skill | Area level | slvl | Normal TTK s (W / cmp) | Nightmare | Hell | Ratio | Flag |", "|---|---|---|---|---|---|---|---|"]
    flagged = []
    for sp in SPECS:
        if sp.role not in ("damage", "weapon", "summon") or not sp.comparables:
            continue
        tier = tier_of(data, sp.name)
        for area in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120):
            s = slvl_at(area, tier)
            if s < 1:
                continue
            w = dps(data, sp, sp.name, s, tier, True)
            c = statistics.median(dps(data, sp, x, s, tier, False) for x in sp.comparables)
            ratio = (c / w) if w > 0 else float("inf")
            lv = data.monlvl.get(area) or data.monlvl[max(data.monlvl)]
            cells = []
            for diff, _, col in DIFFS:
                life = base[diff] * num(data.monlvl_t.get(lv, col)) / 100
                cells.append(f"{life / max(w, 1e-9):.1f} / {life / max(c, 1e-9):.1f}")
            flag = "OUT" if abs(ratio - 1) > OUTLIER else ""
            if flag:
                flagged.append((sp.name, area, s, ratio))
            out.append(f"| {sp.name} | {area} | {s} | {' | '.join(cells)} | {ratio:.2f} | {flag} |")
    out += ["", f"Outliers: {len(flagged)}", ""] + [f"- {n} area {a} (slvl {s}): ratio {r:.2f}" for n, a, s, r in flagged]
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "ttk_report.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"ttk: {len(flagged)} outliers (>{int(OUTLIER * 100)} %), report {OUTDIR.relative_to(ROOT) / 'ttk_report.md'}")
    for n, a, s, r in flagged:
        print(f"   {n}: area {a} slvl {s} ratio {r:.2f}")
    return 0


def cmd_probe(excel: Path, names: list[str]) -> int:
    data = Data(excel)
    for n in names:
        row = data.skill(n)
        if row is None:
            print(n, "?")
            continue
        tier = tier_of(data, n)
        t, src, missile = damage_source(data, row)
        print(f"{n}: tier {tier}, class {data.skills.get(row, 'charclass')}, source "
              f"{'missile ' if missile else ''}{src[0] if src else '-'}")
        for s in SHOW:
            d = damage(data, n, s, tier)
            line = (f"  s{s:>2} u{ulvl(s, tier):>3}: elem {fmt(d.elem)} ({d.etype} syn {d.esyn}%) phys {fmt(d.phys)} "
                    f"weapon {fmt(d.weapon)} total {fmt(d.total)} mana {fmt(mana_cost(data, n, s))} "
                    f"interval {cast_interval(data, n, s, tier)}")
            if data.skills.get(row, "summon"):
                m = summon_stats(data, n, s, tier)
                line += f" | minion life {fmt(m.life)} dmg {fmt(m.damage)} x{m.count}"
            print(line)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fit")
    f.add_argument("--excel", type=Path, default=default_excel())
    a = sub.add_parser("apply")
    a.add_argument("--mod", type=Path, default=ROOT / "work" / "mod")
    t = sub.add_parser("ttk")
    t.add_argument("--excel", type=Path, default=default_excel())
    p = sub.add_parser("probe")
    p.add_argument("names", nargs="+")
    p.add_argument("--excel", type=Path, default=default_excel())
    args = ap.parse_args(argv)
    if args.cmd == "fit":
        return cmd_fit(args.excel)
    if args.cmd == "apply":
        return cmd_apply(args.mod)
    if args.cmd == "ttk":
        return cmd_ttk(args.excel)
    return cmd_probe(args.excel, args.names)


if __name__ == "__main__":
    sys.exit(main())
