"""Validate the generated mod tables against D2R's own data schema.

Schema: D2R's data guide (extract/d2r/<build>/data/global/dataguide/data/files/*.js), which types every field:
reference {file, field}, string (string key), text (max length, optional list of allowed values), int, boolean,
parse (BBE formula or property reference, told apart by the description), plus enum validations in enums.js.

Tables: work/mod/data/global/excel/{base,rotw} (tools/txt_migrate.py); tables the mod does not ship fall back to
D2R's originals. String keys of localization cells are checked by tools/strings_check.py (docs/strings.md), not here.

Findings are grouped by severity:
  error   the game would reject the value or it points at something that does not exist
  plugin  valid only once a D2RLoader plugin provides it (Median formula functions / calc codes, new level types)
  warn    suspicious, probably fine

Output: work/mod/validate_report.md, validate_findings.json. Exit code 1 if there are errors.
Usage: python tools/validate.py [--bank base|rotw|both] [--examples 3]
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import os  # noqa: E402

import localconfig  # noqa: E402  (.mxl-local.json defaults, D2R extraction)
import strings_ns  # noqa: E402
from func_slots import POISON  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
# D2R 93847 baseline tables: the machine's extract_dir (read-only), or MXL_D2R_EXTRACT
D2R = localconfig.default_d2r_extract() / "data"
GUIDE = D2R / "global" / "dataguide" / "data" / "files"
MOD = ROOT / "work" / "mod" / "data"

BBE_FUNCS = {"min", "max", "rand", "skill", "miss", "stat", "sklvl", "sksrc", "cond"}
CONDITIONS = {"IsType", "IsClass", "Desecrated", "Difficulty", "MonsterTestElite", "ItemIsType", "ItemIsModType",
              "MonsterHasMod"}
STAT_MODES = {"accr", "base", "mod"}
MAX_FORMULA_NAME = 31
MAX_ITEMS_PER_SET = 6
ENGINE_AI_ROWS = 155  # D2R build 93847 AI table 0x2396e90
AUTO_TC = re.compile(r"^(weap|armo|mele|bow|mag[a-z]*|rar[a-z]*)\d+$")
SCOPE_CODES = {"Skill": "skillcalc", "Missile": "misscalc", "Monster": "moncalc"}
TOKEN = re.compile(r"\s*(?:(?P<num>\d+)|(?P<str>'[^']*')|(?P<id>[A-Za-z_][A-Za-z0-9_]*)|(?P<op><=|>=|==|!=|[-+*/%^()?:<>,.]))")


# itemtypes rows (0-based) of the mercenaries' weapon and shield types; the same rows in D2R and in v005 (merc_rules)
MERC_ITEM_TYPES = {2: "shie", 27: "bow", 30: "swor", 33: "spea", 34: "pole", 45: "weap", 51: "shld"}


def load_js(path: Path) -> dict:
    t = path.read_text("utf-8")
    return json.loads(t[t.index("=") + 1:].strip().rstrip(";"))


class Schema:
    def __init__(self):
        self.files = {p.stem.lower(): load_js(p) for p in GUIDE.glob("*.js")}
        self.enums = {f["name"]: f for f in self.files.get("enums", {}).get("fields", [])}

    def field(self, table: str, column: str) -> dict | None:
        f = self.files.get(table)
        if not f:
            return None
        # armor/weapons/misc share most fields through SharedItems, the affix tables through SharedItemMods
        fields = list(f["fields"])
        for extra in f.get("appendFiles", []):
            fields += self.files.get(extra.lower(), {}).get("fields", [])
        for fld in fields:
            names = [fld["name"], *fld.get("altNames", [])]
            for n in names:
                if n == column or ("#" in n and re.fullmatch(re.escape(n).replace("\\#", r"\d+"), column)):
                    return fld
        return None

    def formula_scope(self, table: str, column: str) -> str | None:
        """"Skill" / "Missile" / "Item" / "Monster" / "Treasure Class" for a BBE formula column, else None."""
        spec = self.field(table, column)
        if spec is None:
            return None
        typ = spec.get("type", {})
        kind = typ.get("type") if isinstance(typ, dict) else typ
        desc = re.sub(r"\s+", " ", (typ.get("description", "") if isinstance(typ, dict) else "") + " " + spec.get("description", ""))
        m = re.search(r"(Skill|Missile|Item|Monster|Treasure Class) scope BBE", desc)
        return m.group(1) if kind == "parse" and m else None

    @staticmethod
    def allowed(spec_owner: dict) -> set[str] | None:
        v = spec_owner.get("d2rExcel", {}).get("validation", {})
        if v.get("type") == "table" and "table" in spec_owner:
            col = v.get("tableModelColumn", 0)
            return {row[col] for row in spec_owner["table"][v.get("tableStartRow", 1):] if col < len(row)}
        return None


class Data:
    """Tables of one bank: the mod's copy, else D2R's original."""

    def __init__(self, bank: str):
        self.bank = bank
        self.cache: dict[str, tuple[list[str], list[list[str]]] | None] = {}

    def table(self, name: str):
        name = name.lower()
        if name not in self.cache:
            sub = "base" if self.bank == "base" else ""
            hit = None
            for root in (MOD / "global" / "excel" / sub, D2R / "global" / "excel" / sub):
                p = root / f"{name}.txt"
                if p.exists():
                    lines = p.read_text("utf-8-sig", errors="replace").splitlines()
                    rows = [l.split("\t") for l in lines]
                    hit = (rows[0], [r for r in rows[1:] if r and r[0] != "Expansion"])
                    break
            self.cache[name] = hit
        return self.cache[name]

    def values(self, name: str, column: str) -> set[str] | None:
        t = self.table(name)
        if not t:
            return None
        header, rows = t
        idx = next((i for i, h in enumerate(header) if h.lower() == column.lower()), None)
        if idx is None:
            return None
        return {r[idx] for r in rows if idx < len(r) and r[idx] != ""}


class Validator:
    def __init__(self, bank: str, examples: int):
        self.schema = Schema()
        self.data = Data(bank)
        self.bank = bank
        self.examples = examples
        self.findings: dict[tuple, list] = defaultdict(list)
        d2r_codes = lambda t: (self.data_d2r(t) or set())
        self.d2r_calc = {t: d2r_codes(t) for t in ("skillcalc", "misscalc", "moncalc")}

    def data_d2r(self, table: str) -> set[str] | None:
        p = D2R / "global" / "excel" / ("base" if self.bank == "base" else "") / f"{table}.txt"
        if not p.exists():
            return None
        return {l.split("\t")[0] for l in p.read_text("utf-8-sig").splitlines()[1:] if l}

    def data_d2r_rows(self, table: str) -> dict[str, set[tuple[str, str]]]:
        """column -> {(first cell, value)} of D2R's own table, for 'is this row D2R's own use of the value'."""
        p = D2R / "global" / "excel" / ("base" if self.bank == "base" else "") / f"{table}.txt"
        if not p.exists():
            return {}
        lines = [l.split("\t") for l in p.read_text("utf-8-sig", errors="replace").splitlines()]
        return {c: {(r[0], r[i].strip()) for r in lines[1:] if len(r) > i} for i, c in enumerate(lines[0])}

    _vanilla: dict[tuple[str, str, str], set[str]] = {}

    def vanilla_values(self, table: str, column: str) -> set[str]:
        key = (self.bank, table, column)
        if key not in self._vanilla:
            p = D2R / "global" / "excel" / ("base" if self.bank == "base" else "") / f"{table}.txt"
            vals: set[str] = set()
            if p.exists():
                lines = p.read_text("utf-8-sig", errors="replace").splitlines()
                header = lines[0].split("\t")
                if column in header:
                    i = header.index(column)
                    vals = {l.split("\t")[i].strip() for l in lines[1:] if len(l.split("\t")) > i}
            self._vanilla[key] = vals
        return self._vanilla[key]

    def add(self, sev: str, table: str, column: str, problem: str, row: str, value: str) -> None:
        if sev == "error" and value in self.vanilla_values(table, column):
            sev, problem = "warn", f"{problem} (vanilla D2R has the same value)"
        self.findings[(sev, table, column, problem)].append((row, value))

    # ---- formulas ---------------------------------------------------------------------------------------
    def check_bbe(self, table: str, column: str, row: str, text: str, scope: str) -> None:
        tokens, pos = [], 0
        while pos < len(text):
            m = TOKEN.match(text, pos)
            if not m or m.end() == pos:
                self.add("error", table, column, "formula: unreadable text", row, text)
                return
            kind = m.lastgroup
            tokens.append((kind, m.group(kind)))
            pos = m.end()
        depth = 0
        for k, v in tokens:
            depth += (v == "(") - (v == ")") if k == "op" else 0
            if depth < 0:
                break
        if depth != 0:
            self.add("error", table, column, "formula: unbalanced parentheses", row, text)
        for k, v in tokens:
            if k == "str" and len(v) - 2 > MAX_FORMULA_NAME:
                self.add("error", table, column, f"name longer than {MAX_FORMULA_NAME} characters in a formula "
                         "(D2R's parser keeps 32 bytes)", row, v)
        codes_table = SCOPE_CODES.get(scope)
        scope_codes = (self.data.values(codes_table, "code") or set()) if codes_table else set()
        d2r_codes = {c for c in self.d2r_calc.get(codes_table, set())} if codes_table else set()
        skillcalc = self.data.values("skillcalc", "code") or set()
        misscalc = self.data.values("misscalc", "code") or set()
        for i, (k, v) in enumerate(tokens):
            if k != "id":
                continue
            nxt = tokens[i + 1][1] if i + 1 < len(tokens) else ""
            prev = tokens[i - 1][1] if i else ""
            if nxt == "(":
                if v.startswith("mxl_"):
                    self.add("plugin", table, column, f"Median formula function {v}()", row, text)
                elif v not in BBE_FUNCS:
                    self.add("error", table, column, f"unknown function {v}()", row, text)
                elif v in ("skill", "miss", "stat", "sklvl", "sksrc") and i + 2 < len(tokens) and tokens[i + 2][0] == "str":
                    name = tokens[i + 2][1][1:-1]
                    target = {"skill": ("skills", "skill"), "sksrc": ("skills", "skill"), "sklvl": ("skills", "skill"),
                              "miss": ("missiles", "Missile"), "stat": ("itemstatcost", "Stat")}[v]
                    if name not in (self.data.values(*target) or set()):
                        self.add("error", table, column, f"{v}(): unknown {target[0]} '{name}'", row, text)
                    if i + 4 < len(tokens) and tokens[i + 3][1] == "." and tokens[i + 4][0] in ("id", "num"):
                        sub = tokens[i + 4][1]
                        valid = STAT_MODES if v == "stat" else (misscalc if v == "miss" else skillcalc)
                        if sub not in valid:
                            if v == "stat" and sub.isdigit() and int(sub) < 100:
                                self.add("plugin", table, column, f"Median stat() mode {sub}", row, text)
                            else:
                                self.add("error", table, column, f"{v}(): unknown sub-code '{sub}'", row, text)
                        elif v != "stat" and sub not in self.d2r_calc["misscalc" if v == "miss" else "skillcalc"]:
                            self.add("plugin", table, column, f"Median calc code '{sub}'", row, text)
                elif v == "cond" and i + 2 < len(tokens) and tokens[i + 2][0] == "str":
                    if tokens[i + 2][1][1:-1] not in CONDITIONS:
                        self.add("error", table, column, "cond(): unknown condition", row, text)
                continue
            if prev == ".":
                continue  # sub-code inside skill('x'.code); checked above
            if not codes_table:
                self.add("error", table, column, f"{scope} scope has no identifiers: '{v}'", row, text)
            elif v not in scope_codes:
                self.add("error", table, column, f"unknown {codes_table} code '{v}'", row, text)
            elif v not in d2r_codes:
                self.add("plugin", table, column, f"Median calc code '{v}'", row, text)

    # ---- columns ----------------------------------------------------------------------------------------
    def check_table(self, table: str) -> None:
        t = self.data.table(table)
        if not t or table not in self.schema.files:
            return
        header, rows = t
        for ci, col in enumerate(header):
            if not col or col.startswith("*"):
                continue
            spec = self.schema.field(table, col)
            if spec is None:
                self.add("warn", table, col, "column not in D2R's schema", "-", "")
                continue
            typ = spec.get("type", {})
            kind = typ.get("type") if isinstance(typ, dict) else typ
            desc = re.sub(r"\s+", " ", (typ.get("description", "") if isinstance(typ, dict) else "") + " " + spec.get("description", ""))
            allowed = self.schema.allowed(spec)
            v_rule = spec.get("d2rExcel", {}).get("validation", {})
            if v_rule.get("type") == "foreign" and v_rule.get("foreignField") in self.schema.enums:
                allowed = self.schema.allowed(self.schema.enums[v_rule["foreignField"]])
            ref_set = None
            if kind == "reference" and isinstance(typ, dict) and typ.get("file"):
                ref_set = self.data.values(typ["file"], typ.get("field") or "")
            prop_set = None
            if kind == "parse" and "Properties#code" in desc:
                prop_set = (self.data.values("properties", "code") or set()) | (self.data.values("propertygroups", "code") or set())
            param_sets = None
            if kind == "parse" and desc.lstrip().startswith("A number or references"):
                param_sets = set()
                for f, fld in re.findall(r"\$!([^!#]+)#([^!]+)!\$", desc):
                    param_sets |= self.data.values(f, fld) or set()
            scope = None
            m = re.search(r"(Skill|Missile|Item|Monster|Treasure Class) scope BBE", desc)
            if kind == "parse" and m:
                scope = m.group(1)
            for r in rows:
                if ci >= len(r):
                    continue
                v = r[ci].strip()
                if v == "":
                    continue
                rid = r[0]
                if strings_ns.is_localization(table, col):
                    continue  # string keys: tools/strings_check.py
                if kind == "int" and not re.fullmatch(r"-?\d+", v):
                    self.add("error", table, col, "not an integer", rid, v)
                elif kind == "boolean" and v not in ("0", "1"):
                    self.add("error", table, col, "not 0/1", rid, v)
                elif kind in ("text", "parse") and isinstance(typ, dict) and typ.get("dataLength") and len(v) > typ["dataLength"]:
                    self.add("error", table, col, f"longer than {typ['dataLength']} characters", rid, v)
                if allowed is not None and v not in allowed:
                    nums = [int(a) for a in allowed if re.fullmatch(r"-?\d+", a)]
                    if v.startswith("mxl_lvltype_"):
                        self.add("plugin", table, col, "Median level type (D2R's are fixed)", rid, v)
                    elif re.fullmatch(r"-?\d+", v) and nums:
                        self.add("plugin", table, col, "Median value outside D2R's list (engine feature in D2Sigma)", rid, v)
                    else:
                        self.add("error", table, col, "value not in D2R's allowed list", rid, v)
                # SQ (sequence) is not a PlrMode row; D2R's skill loader takes it as a token (126 vanilla skills)
                if ref_set is not None and v not in ref_set and not (typ.get("file") == "PlrMode" and v == "SQ"):
                    self.add("error", table, col, f"no {typ['file']}.{typ.get('field')} '{v}'", rid, v)
                if prop_set is not None and v not in prop_set:
                    self.add("error", table, col, "unknown property code", rid, v)
                if param_sets is not None and not re.fullmatch(r"-?\d+", v) and v not in param_sets:
                    self.add("warn", table, col, "parameter is neither a number nor a known name", rid, v)
                if scope:
                    self.check_bbe(table, col, rid, v, scope)

    def run(self) -> None:
        names = {p.stem for p in (MOD / "global" / "excel" / ("base" if self.bank == "base" else "")).glob("*.txt")}
        for t in sorted(names):
            self.check_table(t)
        self.engine_rules()
        self.cube_outputs()
        self.missile_chains()

    def missile_chains(self) -> None:
        """Missiles that make themselves again (an unbounded chain) and monster attacks whose missile chain is too heavy for
        a pack firing it at the AI's rate (bug #395, tools/missile_chains.py)."""
        import missile_chains
        mis = self.data.table("missiles")
        if not mis:
            return
        mon = self.data.table("monstats")
        for sev, col, row, problem, value in missile_chains.problems(*mis, mon):
            self.add(sev, "missiles" if col == "Missile" else "monstats", col, problem, row, value)
        import srcdamage
        for sev, col, row, problem, value in srcdamage.problems(*mis):
            self.add(sev, "missiles", col, problem, row, value)

    # What D2R resolves in a cubemain output cell: an item code, an item type code, a unique / set item index (the index
    # cell as written: `medianxl:<key>` for a Median-only name), or one of its special words. Median's `void` names nothing:
    # the recipe only destroys its inputs.
    CUBE_OUTPUT_WORDS = {"useitem", "usetype", "Cow Portal", "void"}

    def cube_outputs(self) -> None:
        """Every cubemain output cell resolves to something D2R's compiler knows (bug #19: a quote left in an empty cell
        and an unresolved name both give an empty output slot, which `game_checks.py all cowportals` finds only in game).
        The cell is a name with optional `,qty=2` style modifiers, in quotes when it has a comma."""
        tab = self.data.table("cubemain")
        if not tab:
            return
        known = set(self.CUBE_OUTPUT_WORDS)
        for t, col in (("armor", "code"), ("weapons", "code"), ("misc", "code"), ("itemtypes", "Code"),
                       ("uniqueitems", "index"), ("setitems", "index")):
            known |= self.data.values(t, col) or set()
        header, rows = tab
        cols = [ci for ci, c in enumerate(header) if strings_ns.is_reference("cubemain", c) and c.startswith("output")]
        for r in rows:
            for ci in cols:
                v = r[ci].strip() if ci < len(r) else ""
                if not v:
                    continue
                body = v[1:-1] if len(v) > 1 and v[0] == v[-1] == '"' else v
                if '"' in body:
                    self.add("error", "cubemain", header[ci], "stray quote in an output cell (D2R reads it as part of the name "
                             "and leaves the slot empty)", r[0] if r else "-", v)
                elif body.partition(",")[0] not in known:
                    self.add("error", "cubemain", header[ci], "output D2R cannot resolve (not an item code, item type, "
                             "unique / set index as the index cell reads, or special word)", r[0] if r else "-", v)

    def hit6_spawns(self) -> None:
        """Missile server hit 6 spawns monstats row sHitPar1 at the hit point (D2R 0x45ce90, as 1.13c). The mod's cell is a
        monstats row number; the built cell must be that monster's migrated ID (a known bug: a Den of Evil boss's bone
        spear spawned an unrelated dummy row). The expected ids come from tools/idmap.py on the mod's own tables."""
        mis = self.data.table("missiles")
        named = ROOT / "work" / "named"
        if not mis or not (named / "missiles.txt").exists():
            return
        import idmap
        m = idmap.IdMap.build(named, D2R / "global" / "excel")
        mh, mrows = idmap.read_tsv(named / "missiles.txt")
        msh, mp1 = mh.index("pSrvHitFunc"), mh.index("sHitPar1")
        h, rows = mis
        built = idmap.records(rows)
        sh, p1 = h.index("pSrvHitFunc"), h.index("sHitPar1")
        n = 0
        for i, s_ in enumerate(idmap.records(mrows)):
            if s_[msh] != "6" or not s_[mp1].isdigit():
                continue
            rid = m.new_id("missiles", i)
            if rid >= len(built):
                continue
            r = built[rid]
            n += 1
            want = m.new_id("monstats", int(s_[mp1])) if int(s_[mp1]) < len(m.spaces["monstats"].rows) else int(s_[mp1])
            if r[sh].strip() != "6" or r[p1].strip() != str(want):
                self.add("error", "missiles", "sHitPar1", f"hit 6 spawns monstats row {r[p1]}, the mod's row {s_[mp1]} is ID {want}", r[0], r[p1])
        self.hit6_checked = n

    def carry_numbers(self) -> None:
        """uniqueitems carry1: D2R refuses a carry1 unique when a carried unique has the same non-zero NUMBER (placement test
        0x473960), 1.13c when it is the same unique. Two rows with one number would block each other (bug #280:
        txt_migrate.carry_numbers gives each row its record index + 1)."""
        ui = self.data.table("uniqueitems")
        if not ui or "carry1" not in ui[0]:
            return
        h, rows = ui
        ci = h.index("carry1")
        first: dict[str, str] = {}
        for r in rows:
            v = r[ci].strip() if ci < len(r) else ""
            if not r or r[0] == "Expansion" or v in ("", "0"):
                continue
            if v in first:
                self.add("error", "uniqueitems", "carry1", f"same carry number as {first[v]} (D2R would refuse one while the "
                         "other is carried; 1.13c only refuses a second copy of the same unique)", r[0], v)
            else:
                first[v] = r[0]

    def engine_rules(self) -> None:
        """Rules D2R asserts on at load time that the field schema does not express."""
        d = self.data
        # treasure class items: item code, item type, treasure class, unique/set item index, or an auto class
        tc = d.table("treasureclassex")
        if tc:
            h, rows = tc
            known = set()
            for t, c in (("weapons", "code"), ("armor", "code"), ("misc", "code"), ("itemtypes", "Code"),
                         ("treasureclassex", "Treasure Class"), ("uniqueitems", "index"), ("setitems", "index")):
                # a unique / set item is named by its index, which is a localization cell (medianxl:<key> when Median-only)
                known |= {x.removeprefix(strings_ns.PREFIX) for x in d.values(t, c) or set()}
            pos = {r[0]: i for i, r in enumerate(rows) if r[0]}
            for ci, c in enumerate(h):
                if not re.fullmatch(r"Item\d+", c):
                    continue
                for i, r in enumerate(rows):
                    v = r[ci].strip() if ci < len(r) else ""
                    name = v.strip('"').split(",", 1)[0].removeprefix(strings_ns.PREFIX)  # a unique / set item: medianxl:<key>
                    if name and name not in known and not AUTO_TC.match(name):
                        self.add("error", "treasureclassex", c, "not an item, item type, treasure class, unique or set item", r[0], v)
                    elif pos.get(name, -1) > i:
                        self.add("error", "treasureclassex", c, "names a treasure class defined further down", r[0], v)
        # sets: at most 6 items
        si = d.table("setitems")
        if si:
            h, rows = si
            counts = defaultdict(int)
            for r in rows:
                counts[r[h.index("set")]] += 1
            for name, n in counts.items():
                if n > MAX_ITEMS_PER_SET:
                    self.add("error", "setitems", "set", f"set has {n} items (D2R allows {MAX_ITEMS_PER_SET})", name, str(n))
        self.hit6_spawns()
        self.carry_numbers()
        # monstats: MonStatsEx is required
        ms = d.table("monstats")
        if ms:
            h, rows = ms
            i = h.index("MonStatsEx")
            for r in rows:
                if not r[i].strip() and r[0] != "Expansion":
                    self.add("error", "monstats", "MonStatsEx", "blank (a required link to monstats2)", r[0], "")
            # AI: the engine's AI table has 155 entries (monai rows 0-154, docs/d2r-addresses.md section 12); a monster whose
            # AI is a later row (or no row) runs the "None" think function and stands still
            ai = d.table("monai")
            if ai:
                ai_row = {r[0]: n for n, r in enumerate(ai[1]) if r and r[0]}
                a = h.index("AI")
                for r in rows:
                    name = r[a].strip()
                    if name and ai_row.get(name, ENGINE_AI_ROWS) >= ENGINE_AI_ROWS:
                        self.add("error", "monstats", "AI", f"not in the engine's AI table (monai rows 0-{ENGINE_AI_ROWS - 1})", r[0], name)
        # levels: a preset level (DrlgType 2) must be claimed by a lvlprest row's LevelId
        lv, lp = d.table("levels"), d.table("lvlprest")
        if lv and lp:
            (lh, lrows), (ph, prows) = lv, lp
            claimed = {r[ph.index("LevelId")] for r in prows}
            for r in lrows:
                if r[lh.index("DrlgType")] == "2" and r[lh.index("Id")] not in claimed:
                    self.add("error", "levels", "DrlgType", "preset level that no lvlprest row claims", r[0], r[lh.index("Id")])
        if lv:  # Depend places a level relative to another; a loop recurses until the stack overflows
            lh, lrows = lv
            dep = {r[lh.index("Id")]: r[lh.index("Depend")] for r in lrows}
            for start in dep:
                seen, u = [], start
                while dep.get(u, "") not in ("", "0") and u not in seen:
                    seen.append(u)
                    u = dep[u]
                if u == start and seen:
                    self.add("error", "levels", "Depend", "Depend chain loops back to this level", start, " -> ".join(seen))
        lm = d.table("lvlmaze")
        if lv and lm:
            (lh, lrows), (mh, mrows) = lv, lm
            have = {r[mh.index("Level")] for r in mrows}
            for r in lrows:
                if r[lh.index("DrlgType")] == "1" and r[lh.index("Id")] not in have:
                    self.add("error", "levels", "DrlgType", "maze level without a lvlmaze row", r[0], r[lh.index("Id")])
        # skills: class skills need a skilldesc
        sk = d.table("skills")
        if sk:
            h, rows = sk
            for r in rows:
                if r[h.index("charclass")] and not r[h.index("skilldesc")]:
                    self.add("error", "skills", "skilldesc", "class skill without a skilldesc", r[0], "")
                # function slots D2R renumbered or reused (tools/func_slots.py POISON, docs/function-slots.md): a Median row on
            # the 1.13c number runs another D2R function (srvdofunc 109 is D2R's itemless Town Portal: Feral Strike, Flash
            # and MonFrenzy opened a portal). Allowed: D2R's own row with that value, and town_portal (-> 109 on purpose)
            ref = self.data_d2r_rows("skills")
            for col, slot in POISON:
                if col not in h:
                    continue
                ci = h.index(col)
                own = ref.get(col, set())
                for r in rows:
                    if len(r) > ci and r[ci].strip() == slot and (r[0], slot) not in own:
                        # not self.add: it downgrades a value D2R's vanilla also uses, and every poisoned slot is one
                        problem = f"slot {slot} is {POISON[(col, slot)]}; Median's 1.13c meaning needs the remapped slot (txt_migrate skill_rules)"
                        self.findings[("error", "skills", col, problem)].append((r[0], slot))
        # skill tree: one class skill per slot; class-less skills (item skills, monster skills) have none
            dsc = d.table("skilldesc")
            if dsc:
                dh, drows = dsc
                desc = {r[0]: r for r in drows}
                pg, ro, co = (dh.index(c) for c in ("SkillPage", "SkillRow", "SkillColumn"))
                slots: dict[tuple, str] = {}
                for r in rows:
                    dr = desc.get(r[h.index("skilldesc")])
                    if not dr or dr[pg] in ("", "0"):
                        continue
                    if not r[h.index("charclass")]:
                        if r[h.index("skilldesc")].endswith("~shared"):
                            self.add("error", "skills", "skilldesc", "class-less skill's copy of a skilldesc row keeps a tree slot",
                                     r[0], r[h.index("skilldesc")])
                        continue
                    key = (r[h.index("charclass")], dr[pg], dr[ro], dr[co])
                    if key in slots:
                        self.add("error", "skills", "skilldesc", "two class skills on one skill tree slot", r[0],
                                 f"{slots[key]} / {'/'.join(key)}")
                    slots[key] = r[0]
        self.merc_rules()
        # inventory: D2R expects two rows (resolutions) per page
        inv = d.table("inventory")
        if inv:
            h, rows = inv
            ref = D2R / "global" / "excel" / ("base" if self.bank == "base" else "") / "inventory.txt"
            want = (len([l for l in ref.read_text("utf-8-sig").splitlines()[1:] if l and not l.startswith("Expansion")])
                    if ref.exists() else len(rows))
            if len(rows) != want:
                self.add("error", "inventory", "-", f"{len(rows)} rows; D2R's layout has {want} (2 per page)", "-", "")

    def merc_rules(self) -> None:
        """What D2R's hard-coded mercenary rules rely on (docs/unported.md, lane mercs2). D2R has no WType columns: which weapons a
        mercenary wields comes from its class in code (1.13c read hireling.txt WType1/2: bow; polearm / spear; sword / shield;
        sword, the values v005 keeps), so the hire classes stay D2R's and the item types it tests stay on D2R's rows. Class items
        stay refused (equivalentcharclass empty, merc_classitems); the revive price is 1.13c's (level^2 / 2 x 15, at most 50,000)."""
        d = self.data
        hl = d.table("hireling")
        if hl:
            h, rows = hl
            want_class = {"1": "271", "2": "338", "3": "359", "5": "561"}
            for r in rows:
                rec = dict(zip(h, r))
                if not rec.get("Class"):
                    continue
                if want_class.get(rec.get("Act", "")) != rec["Class"]:
                    self.add("error", "hireling", "Class", "act's hire class is not D2R's (its weapon rules are per class)", r[0],
                             f"act {rec.get('Act')} class {rec['Class']}")
                if rec.get("equivalentcharclass"):
                    self.add("error", "hireling", "equivalentcharclass", "set: D2R lets the mercenary wear that class's items (1.13c: none)",
                             r[0], rec["equivalentcharclass"])
                for col, want in (("resurrectcostmultiplier", "15"), ("resurrectcostdivisor", "2"), ("resurrectcostmax", "50000")):
                    if rec.get(col, want) != want:
                        self.add("error", "hireling", col, f"not 1.13c's revive price ({want})", r[0], rec.get(col, ""))
        it = d.table("itemtypes")
        if it:
            h, rows = it
            code = h.index("Code")
            for row, want in MERC_ITEM_TYPES.items():
                got = rows[row][code] if row < len(rows) and code < len(rows[row]) else ""
                if got != want:
                    self.add("error", "itemtypes", "Code", f"row {row} is not '{want}' (D2R's mercenary weapon rules test that row)",
                             str(row), got)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", choices=["base", "rotw", "both"], default="both")
    ap.add_argument("--examples", type=int, default=3)
    args = ap.parse_args()
    localconfig.require_d2r_extract(D2R.parent, "validate")
    banks = ["base", "rotw"] if args.bank == "both" else [args.bank]
    out = ROOT / "work" / "mod"
    report, all_findings, errors = ["# Validation report", ""], {}, 0
    for bank in banks:
        v = Validator(bank, args.examples)
        v.run()
        sev_counts = defaultdict(int)
        for (sev, *_rest), items in v.findings.items():
            sev_counts[sev] += len(items)
        errors += sev_counts["error"]
        report += [f"## Bank: {bank}", "",
                   f"errors {sev_counts['error']}, plugin {sev_counts['plugin']}, warnings {sev_counts['warn']}", ""]
        for sev in ("error", "plugin", "warn"):
            items = sorted(((k, val) for k, val in v.findings.items() if k[0] == sev), key=lambda kv: -len(kv[1]))
            if not items:
                continue
            report += [f"### {sev}", "", "| Table | Column | Problem | Count | Examples (row: value) |", "|---|---|---|---|---|"]
            for (_s, table, col, problem), vals in items:
                ex = "; ".join(f"{r}: {val[:60]}" for r, val in vals[: args.examples]).replace("|", "\\|")
                report.append(f"| {table} | {col} | {problem} | {len(vals)} | {ex} |")
            report.append("")
        all_findings[bank] = {"|".join(k): vals for k, vals in v.findings.items()}
    (out / "validate_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    (out / "validate_findings.json").write_text(json.dumps(all_findings, indent=0), encoding="utf-8")
    print("\n".join(line for line in report if line.startswith(("#", "errors"))))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
