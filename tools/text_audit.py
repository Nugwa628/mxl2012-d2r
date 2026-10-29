"""Audit of the text a player can read (owner decision 2026-10-28: no raw text anywhere a player sees it, docs/text-audit.md).

Scans the built tables (both banks) and the mod's UI layouts against the strings the player reads (D2R's own, replaced by the
mod's `d2r:` overrides, plus the Median-only keys of `mxl2012/median.json`; English) and reports every cell that would show:

  missing-key      the cell names a key nobody defines ("Missing string" / the key itself)
  missing-string   the resolved text is, or contains, "Missing string"
  placeholder      the text is a placeholder word (`blah`, `x`, `tbd`, `Not used`, ...)
  key-text         the text looks like a key or code name instead of words: `CouatlInhibitor`, `btor`, `fissure_2`, `mxl2012:...`
  empty-name       an item (inventory picture), monster (enabled, with a token), skill (icon) or selectable object whose name is blank
  blank-key        a blank cell D2R looks up anyway (BLANK_LOOKUP): levels LevelEntry of a named level is the red "Entering ..."
                   banner on arrival, blank it reads "Missing string" (bug #120, the Rogue Encampment on game start)
  layout-at-key    a `@Key` in a layout the mod serves: D2R draws "Missing string" for it (bugs #30 and #33), write the text out
  layout-key-missing  a `@Key` in such a layout that no string defines either
  stat-format      an itemstatcost row with a tooltip function (descfunc) whose format D2R reads from descstrpos / descstrneg
                   but the cell is blank: D2R prints the dummy string 5382 (`dummy`, "FLYING POLAR BUFFALO ERROR") as the whole line (bug
                   #140: 1.13c hard-codes the text of descfuncs 27 / 28, D2R's formatter 0x2d6520 reads the row's cell)
  skill-name       an item property (unique, set, runeword, affix, gem, recipe output) whose line names a skill (+skill, aura,
                   chance to cast, charges) that has no readable name: no skills row, no skilldesc, a blank or missing
                   `str name`; D2R's name lookup 0x28bcf0 falls back to string 0x1506 = 5382 (`dummy`, the same Buffalo text).
                   The parameter is read as both games' loaders read it (1.14d 0x6336a0, D2R 0x320310): a number as a number,
                   else a skills.txt name, else a montype or states name (its index), else 0, so a name no table has (or a blank
                   cell) is skill 0 (bug #180: Trang-Oul's Avatar's Fire Ball / Meteor / Fire Mastery read "+N to Attack")
  rune-letter      a rune (misc type `rune`) without a gems row, or a gems row whose `letter` cell D2R cannot read: the rune
                   tooltip and the runeword's letter line look the cell up as a key of D2R's own namespace (D2R's strings plus
                   the mod's `d2r:` overrides, not the mod's own keys) in a 5-character field, and draw "Missing string" for
                   anything else (bug #330: Median's cells are the literal names `El`, `Taha`, ...); a literal name that happens to
                   be another D2R key reads that key's text (rune Xar: `Ornate Plate`, bug #334)
  skill-desc       a skill tooltip line (skilldesc descline / dsc2line / dsc3line of a row some skills row names) that D2R's line
                   renderer 0x287a50 draws wrong (bug #396): a mana cost line (type 1) with a blank text A on a skill with a mana
                   cost (1.13c read skilldesc's `str mana`, D2R reads text A: the dummy string 5382 + the cost, "FLYING POLAR
                   BUFFALO ERROR44"); a text whose words carry a printf conversion in a line type that appends text, number and
                   unit (D2R's `StrSkill82` "Fire Duration: %d seconds" shows its raw %d); a type-36 format with no number; and,
                   while FIXED_LABELS_HANDLED is off, the line types whose label D2R hard-codes as a printf format (types 9, 10,
                   11, 14, 22, 25, 27, 28; the plugin part skilltext cuts them back to 1.13c's words in game)
  colour-code      a text of the mod's own (Median-only key or `d2r:` override) with a colour code `ÿc<char>` D2R cannot draw
                   (strings_ns.D2R_COLOURS): D2R prints it as text (bug #398: Median's `ÿc/` read "*/" in HD and "Ø/" in classic
                   on 706 skill descriptions); tbl2json maps the known ones (strings_ns.COLOUR_MAP); or a code that ends a line,
                   which D2R drops (1.14d colours the next line with it; tbl2json moves it behind the line break)

Texts of D2R's own keys that the mod does not replace are D2R's business and skipped (D2R's own `fissure`, a blank guild
stone), unless the cell is blank. Rows the mod keeps on purpose go into data/text_audit_allow.tsv (kind, table, column, key,
reason); a stale row (it matches nothing any more) is an error, so the list cannot rot. Magic affixes whose name is empty are
Median's own design (every one of the 1,706 names is the key `NoDesc`, defined with an empty text in Median's tbl): they are
counted in the report, not findings.

  py -3 -I tools/text_audit.py [--excel-dir DIR] [--layouts-dir DIR] [--d2r-lng DIR] [--report FILE]   exit 1 on a finding
strings_check.py --rewritten runs the same audit, so a hit fails the build.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import idmap  # noqa: E402
import strings_ns as ns  # noqa: E402

ROOT = ns.ROOT
ALLOW = ROOT / "data" / "text_audit_allow.tsv"
D2R_FIXES = ROOT / "data" / "d2r_string_fixes.json"  # merge_string_overrides.py FIXES
COLOUR = re.compile(r"ÿc.")
# whole-text placeholders; a name such as "Do Not Use Ethereal Items Idiot" (Median's joke item) is real text
PLACEHOLDER = re.compile(r"(?i)(x+|blah|tbd|todo|tbc|test|dummy|unused|not used|n/?a|placeholder|temp|asdf|xxx+|\?+|\.+|-+|none|null)")
# D2R tooltip functions (formatter 0x2d6520) that do not read descstrpos: 11 repair (own strings), 13 class skills and 14 skill
# tab (charstats texts), 30 / 31 (Chronicle keys of their own). Every other function prints the row's descstrpos text.
OWN_FORMAT_DESCFUNCS = {"11", "13", "14", "30", "31"}
# tooltip functions whose line names the skill of the property's parameter: 15 on-event, 16 aura, 24 charges, 27 / 28 +skill
SKILL_NAME_DESCFUNCS = {"15", "16", "24", "27", "28"}
# tables whose property slots end up on items the player hovers (monprop is a monster's, not shown)
ITEM_PROPERTY_TABLES = ("uniqueitems", "setitems", "sets", "runes", "magicprefix", "magicsuffix", "automagic", "rareprefix",
                        "raresuffix", "qualityitems", "lowqualityitems", "gems", "cubemain")
CAMEL = re.compile(r"[a-z][A-Z]")
# affix tables whose names are empty by Median's design (reported, not findings)
DESIGN_EMPTY = {"magicprefix": "name", "magicsuffix": "name"}
LAYOUT_AT = re.compile(r'"(@[^"\n]*)"')


@dataclass(frozen=True)
class Finding:
    kind: str
    table: str          # table name, or `layout` for the UI layouts
    column: str
    where: str          # `<bank> <table>.txt row N` / layout file
    key: str            # the key (or `@Key`) involved
    text: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.where} {self.column}={self.key!r} reads {self.text!r}"


class Strings:
    """What the player reads: lower-cased key -> text, and the lower-cased keys the mod defines itself (its own work)."""

    def __init__(self, texts: dict[str, str], own: set[str], d2r: dict[str, str] | None = None):
        self.texts = {k.lower(): v for k, v in texts.items()}
        self.own = {k.lower() for k in own}
        # D2R's own namespace (its strings with the mod's `d2r:` overrides): what a bare key in a fixed-size field reads
        self.d2r = self.texts if d2r is None else {k.lower(): v for k, v in d2r.items()}

    @classmethod
    def load(cls, lang: str = "enUS") -> "Strings":
        """Own = the Median-only keys, and the `d2r:` overrides whose text differs from D2R's (an override that repeats D2R's
        English text, written for another language's sake, is D2R's text: `fissure`)."""
        d2r = ns.d2r_loaded()
        own = {k for k, e in ns.overrides().items() if k not in d2r or plain(e.get(lang, "")) != plain(d2r[k][0].get(lang, ""))}
        p = ns.MOD_STRINGS / ns.NAMESPACE / "median.json"
        if p.exists():
            own |= {e["Key"] for e in json.loads(p.read_text("utf-8-sig"))}
        d2r_texts = {k: e[0].get(lang, "") for k, e in d2r.items()}
        d2r_texts.update({k: e.get(lang, "") for k, e in ns.overrides().items()})
        if D2R_FIXES.exists():  # the hand-made d2r: keys, merged into overrides.json only after the first strings_check
            d2r_texts.update({f["key"].split(":", 1)[1]: f["text"] for f in json.loads(D2R_FIXES.read_text("utf-8-sig"))})
        return cls(ns.effective_texts(lang), own, d2r_texts)

    def resolve(self, cell: str) -> tuple[str, str | None]:
        """-> (bare key, text or None when nobody defines the key)."""
        key = ns.split_key(cell)[1]
        return key, self.texts.get(key.lower())


def plain(text: str) -> str:
    return COLOUR.sub("", text).strip()


def key_like(text: str, key: str) -> bool:
    """The text reads like a key or code name, not words: one token that is snake_case, CamelCase, a lower-case echo of its
    own key, or a qualified key. Several words (even if the text equals the key: "To The Palace Cellar") are words."""
    t = plain(text)
    if not t:
        return False
    if t.lower().startswith((ns.PREFIX, ns.D2R_PREFIX)):
        return True
    if re.search(r"\s", t):
        return False
    if "_" in t or CAMEL.search(t):
        return True
    return t == key and t.islower() and len(t) > 1


def is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER.fullmatch(plain(text).replace("\n", " ")))


def read_table(path: Path):
    lines = path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    head = [h.strip().lower() for h in lines[0].split("\t")]
    return head, [ln.split("\t") for ln in lines[1:] if ln]


def load_allow(path: Path = ALLOW) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f, delimiter="\t") if r.get("kind")]


def cell_of(row: list[str], i: int | None) -> str:
    return row[i] if i is not None and i < len(row) else ""


def empty_name_applies(table: str, head: list[str], row: list[str]) -> bool:
    """Does a blank name matter for this row: an item with an inventory picture, a monster that is enabled and has a token, a
    skill with an icon, an object the player can click."""
    def col(name):
        return cell_of(row, head.index(name) if name in head else None).strip()
    if table in ("armor", "weapons", "misc"):
        return bool(col("invfile"))
    if table == "monstats":
        return col("enabled") == "1" and bool(col("code")) and bool(col("id"))
    if table == "skilldesc":
        return bool(col("skilldesc")) and bool(col("iconcel"))
    if table == "objects":
        return col("selectable0") == "1" or col("selectable1") == "1"
    return False


# columns D2R looks up even when blank (-> "Missing string"), per table: column -> the column that makes the row a real one
BLANK_LOOKUP = {"levels": {"levelentry": "levelname"}}
# columns (per table) whose blank name is a finding
NAME_COLUMNS = {"armor": "namestr", "weapons": "namestr", "misc": "namestr", "monstats": "namestr", "skilldesc": "str name",
                "objects": "name"}


def audit_table(path: Path, table: str, bank: str, strings: Strings, designed: Counter) -> list[Finding]:
    head, rows = read_table(path)
    found: list[Finding] = []
    for col in sorted(ns.LOCALIZATION[table]):
        if col not in head or ns.is_label_column(table, col):
            continue
        ci = head.index(col)
        for n, row in enumerate(rows, 2):
            v = cell_of(row, ci)
            where = f"{bank} {table}.txt row {n}"
            if not v:
                if NAME_COLUMNS.get(table) == col and empty_name_applies(table, head, row):
                    found.append(Finding("empty-name", table, col, where, "", ""))
                need = BLANK_LOOKUP.get(table, {}).get(col)
                if need and need in head and cell_of(row, head.index(need)).strip():
                    found.append(Finding("blank-key", table, col, where, "", "Missing string"))
                continue
            if ns.is_placeholder(table, col, v):
                continue
            key, text = strings.resolve(v)
            if text is None:
                found.append(Finding("missing-key", table, col, where, key, "Missing string"))
                continue
            if "missing string" in text.lower():
                found.append(Finding("missing-string", table, col, where, key, text))
            ours = key.lower() in strings.own
            if not text.strip() and not plain(text):
                if table in DESIGN_EMPTY and col == DESIGN_EMPTY[table] and ours:
                    designed[(table, key)] += 1
                elif NAME_COLUMNS.get(table) == col and ours and empty_name_applies(table, head, row):
                    found.append(Finding("empty-name", table, col, where, key, ""))
                continue
            if not ours:
                continue  # D2R's own text, untouched
            if is_placeholder(text):
                found.append(Finding("placeholder", table, col, where, key, text))
            elif key_like(text, key):
                found.append(Finding("key-text", table, col, where, key, text))
    return found


def audit_layouts(layouts: Path, strings: Strings) -> list[Finding]:
    found: list[Finding] = []
    for p in sorted(layouts.glob("*.json")):
        text = p.read_text("utf-8", errors="replace")
        for n, line in enumerate(text.split("\n"), 1):
            for m in LAYOUT_AT.finditer(line):
                for tok in m.group(1).split():
                    if not tok.startswith("@"):
                        continue
                    key, t = strings.resolve(tok[1:])
                    kind = "layout-key-missing" if t is None else "layout-at-key"
                    found.append(Finding(kind, "layout", p.name, f"{p.name} line {n}", tok, t or "Missing string"))
    return found


def _rows(folder: Path, table: str):
    p = folder / f"{table}.txt"
    if not p.exists():
        return None, []
    head, rows = read_table(p)
    return head, [(n, r) for n, r in enumerate(rows, 2) if r and r[0] and r[0] != "Expansion"]


RUNE_LETTER_KEY = re.compile(r"(?i)r\d\dL")  # D2R's own rune letter keys (r01L El .. r33L Zod); any other cell must read as itself
RUNE_LETTER_MAX = 5  # the gems record's letter field (D2R gems record +0x20; Median's longest name, Shaad, fills it)


def audit_rune_letters(folder: Path, bank: str, strings: Strings) -> list[Finding]:
    """rune-letter (see the module text): every rune has a gems row whose letter cell is a D2R-namespace key with a text."""
    found: list[Finding] = []
    mh, misc = _rows(folder, "misc")
    gh, gems = _rows(folder, "gems")
    if mh is None or gh is None or "letter" not in gh or "code" not in gh:
        return found
    letters = {cell_of(r, gh.index("code")).strip().lower(): (n, cell_of(r, gh.index("letter")).strip()) for n, r in gems}
    for n, r in misc:
        code = cell_of(r, mh.index("code")).strip() if "code" in mh else ""
        if "type" not in mh or cell_of(r, mh.index("type")).strip().lower() != "rune":
            continue
        if code.lower() not in letters:
            found.append(Finding("rune-letter", "misc", "code", f"{bank} misc.txt row {n}", code, "no gems row"))
            continue
        gn, cell = letters[code.lower()]
        where = f"{bank} gems.txt row {gn}"
        text = strings.d2r.get(cell.lower()) if cell else None
        if not cell or len(cell) > RUNE_LETTER_MAX or text is None or not text.strip() or "missing string" in text.lower():
            found.append(Finding("rune-letter", "gems", "letter", where, cell, text if text else "Missing string"))
        elif not RUNE_LETTER_KEY.fullmatch(cell) and plain(text).lower() != cell.lower():
            found.append(Finding("rune-letter", "gems", "letter", where, cell, text))  # a literal name that is another D2R key
    return found


def audit_stat_lines(folder: Path, bank: str, strings: Strings) -> list[Finding]:
    """stat-format and skill-name (see the module text): the two ways a property line prints D2R's `dummy` text."""
    found: list[Finding] = []
    ih, isc = _rows(folder, "itemstatcost")
    if ih is None:
        return found
    ci = {c: ih.index(c) for c in ("stat", "descfunc", "descstrpos", "descstrneg") if c in ih}
    descfunc = {}
    for n, r in isc:
        fn = cell_of(r, ci.get("descfunc")).strip()
        descfunc[cell_of(r, ci.get("stat")).lower()] = fn
        if fn in ("", "0") or fn in OWN_FORMAT_DESCFUNCS:
            continue
        for c in ("descstrpos", "descstrneg"):
            if not cell_of(r, ci.get(c)).strip():
                found.append(Finding("stat-format", "itemstatcost", c, f"{bank} itemstatcost.txt row {n}", r[0],
                                     f"descfunc {fn}: no format key (dummy string 5382)"))
    ph, props = _rows(folder, "properties")
    sh, skills = _rows(folder, "skills")
    dh, descs = _rows(folder, "skilldesc")
    if ph is None or sh is None or dh is None:
        return found
    named = {}  # property code -> stat whose line names a skill
    for _n, r in props:
        st = cell_of(r, ph.index("stat1") if "stat1" in ph else None).lower()
        if descfunc.get(st) in SKILL_NAME_DESCFUNCS:
            named[r[0].lower()] = st
    sid = sh.index("*id") if "*id" in sh else None
    by_skill, by_name = {}, {}
    for n, (_line, r) in enumerate(skills):
        row_id = cell_of(r, sid) or str(n)
        by_skill[row_id] = r
        by_name.setdefault(r[0].lower(), row_id)
    sdc = sh.index("skilldesc")
    desc_name = {r[0].lower(): cell_of(r, dh.index("str name")) for _n, r in descs}
    other_index = {}  # montype / states name -> its index (the loaders' second and third lookups)
    for table in ("montype", "states"):
        p = folder / f"{table}.txt"
        if p.exists():
            for i, r in enumerate(read_table(p)[1]):
                if r and r[0]:
                    other_index.setdefault(table, {}).setdefault(r[0].lower(), str(i))
    checked: dict[str, str | None] = {}

    def skill_id(param: str) -> tuple[str, str]:
        """-> (the skill id the loaders store for a property parameter, how). Both games' parsers (1.14d 0x6336a0, D2R
        0x320310): a cell starting with '-' or a digit is atoi; else the skills, montype and states names in turn; else 0."""
        p = param.strip()
        if p[:1] == "-" or p[:1].isdigit():
            m = re.match(r"-?\d+", p)
            return str(int(m.group())) if m else "0", ""
        r = by_name.get(p.lower())
        if r is not None:
            return r, ""
        for table in ("montype", "states"):
            if p.lower() in other_index.get(table, {}):
                return other_index[table][p.lower()], f"a {table} name, read as {other_index[table][p.lower()]}: "
        return "0", ("blank" if not p else "names nothing") + ", read as 0: "

    def skill_text(param: str) -> str | None:
        """None = readable; else why D2R prints `dummy`."""
        if param in checked:
            return checked[param]
        sid_, how = skill_id(param)
        r = by_skill.get(sid_)
        why = None
        if r is None:
            why = "no skills row"
        else:
            sd = cell_of(r, sdc).strip().lower()
            if not sd or sd not in desc_name:
                why = f"skill {r[0]!r}: no skilldesc"
            elif not desc_name[sd].strip():
                why = f"skill {r[0]!r}: blank str name"
            else:
                key, text = strings.resolve(desc_name[sd])
                if text is None:
                    why = f"skill {r[0]!r}: str name {key!r} missing"
                elif not plain(text) or is_placeholder(text):
                    why = f"skill {r[0]!r}: str name {key!r} reads {text!r}"
        if why:
            why = how + why
        checked[param] = why
        return why

    for table in ITEM_PROPERTY_TABLES:
        head, rows = _rows(folder, table)
        if head is None:
            continue
        slots = idmap.property_columns(head)
        for n, r in rows:
            for code_i, par_i, _mn, _mx in slots:
                code = cell_of(r, code_i).strip().lower()
                if code not in named or par_i is None:
                    continue
                param = cell_of(r, par_i).strip()
                why = skill_text(param)
                if why:
                    found.append(Finding("skill-name", table, head[code_i], f"{bank} {table}.txt row {n}", f"{code} {param}".strip(),
                                         why))
    return found


# the plugin part skilltext rewrites the labels of SKILLDESC_FIXED_LABELS in the rendered line (bug #396)
FIXED_LABELS_HANDLED = True
PRINTF = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[dis]")


def audit_skill_lines(folder: Path, bank: str, strings: Strings) -> list[Finding]:
    """skill-desc (see the module text): the lines of every skilldesc row a skills row names, read as D2R's line renderer
    reads them (strings_ns.SKILLDESC_FORMAT / SKILLDESC_FIXED_LABELS)."""
    found: list[Finding] = []
    sh, skills = _rows(folder, "skills")
    dh, descs = _rows(folder, "skilldesc")
    if sh is None or dh is None or "skilldesc" not in sh:
        return found
    used = {cell_of(r, sh.index("skilldesc")).strip().lower() for _n, r in skills} - {""}
    # the mana cost line (type 1) is drawn only for a skill with mana or lvlmana (both games return before the label)
    costs = {cell_of(r, sh.index("skilldesc")).strip().lower() for _n, r in skills
             if any(cell_of(r, sh.index(c) if c in sh else None).strip() not in ("", "0") for c in ("mana", "lvlmana"))}
    for n, r in descs:
        if r[0].lower() not in used:
            continue
        where = f"{bank} skilldesc.txt row {n}"
        for line, prefix, count in ns.SKILLDESC_GROUPS:
            for i in range(1, count + 1):
                col = f"{line}{i}"
                kind = cell_of(r, dh.index(col) if col in dh else None).strip()
                if not kind.isdigit():
                    continue
                k, fmt = int(kind), ns.skilldesc_format(int(kind))
                if k in ns.SKILLDESC_FIXED_LABELS and not FIXED_LABELS_HANDLED:
                    found.append(Finding("skill-desc", "skilldesc", col, where, r[0],
                                         f"type {k}: D2R appends its own printf label {'/'.join(ns.SKILLDESC_FIXED_LABELS[k])}"))
                for slot in ("A", "B"):
                    if fmt and slot not in fmt and k != 40:
                        continue  # a formatting type reads its format text only (40 also names a skill in text B)
                    c = f"{prefix}text{slot.lower()}{i}"
                    cell = cell_of(r, dh.index(c) if c in dh else None).strip()
                    if not cell:
                        if k == 1 and slot == "A" and r[0].lower() in costs:  # 1.13c's `str mana`; D2R reads text A
                            found.append(Finding("skill-desc", "skilldesc", c, where, r[0], "type 1: blank label (dummy string 5382)"))
                        continue
                    key, text = strings.resolve(cell)
                    if text is None:
                        continue  # missing-key reports it
                    if slot in fmt:
                        if k == 36 and not PRINTF.search(text):
                            found.append(Finding("skill-desc", "skilldesc", c, where, key, f"type {k} formats {text!r}: no number"))
                    elif PRINTF.search(text):
                        found.append(Finding("skill-desc", "skilldesc", c, where, key, f"type {k} appends {text!r}: raw placeholder"))
    return found


def audit_colours(strings: Strings) -> list[Finding]:
    """The mod's own texts (every one a player may read, used by a table or not) with a colour code D2R prints as text."""
    found = []
    for key in sorted(strings.own):
        text = strings.texts.get(key, "")
        bad = [f"ÿc{c}" for c in dict.fromkeys(ns.bad_colours(text))]
        bad += [f"ÿc{c} before a line break" for c in dict.fromkeys(m.group(1)[-1] for m in ns.EOL_COLOUR.finditer(text))]
        if bad:
            found.append(Finding("colour-code", "strings", "text", "string", key, ", ".join(bad)))
    return found


def apply_allow(found: list[Finding], allow: list[dict]) -> tuple[list[Finding], list[str], list[dict]]:
    """-> (findings left, allowed lines for the report, stale allow rows)."""
    used, left, allowed = set(), [], []
    for f in found:
        hit = next((i for i, a in enumerate(allow)
                    if a["kind"] == f.kind and a["table"] == f.table and a["column"].lower() == f.column.lower()
                    and a["key"].lower() in (f.key.lower(), "*")), None)
        if hit is None:
            left.append(f)
        else:
            used.add(hit)
            allowed.append(f"{f} -- allowed: {allow[hit]['reason']}")
    return left, allowed, [a for i, a in enumerate(allow) if i not in used]


def audit(excel: Path, strings: Strings, layouts: Path | None = None, allow: list[dict] | None = None):
    """-> (findings, report lines). `excel` is the mod's excel folder: its tables are the rotw bank, `base/` the other bank."""
    designed: Counter = Counter()
    found: list[Finding] = []
    checked = 0
    for bank, folder in (("rotw", Path(excel)), ("base", Path(excel) / "base")):
        for table in sorted(ns.LOCALIZATION):
            path = folder / f"{table}.txt"
            if path.exists():
                found += audit_table(path, table, bank, strings, designed)
                checked += 1
        found += audit_stat_lines(folder, bank, strings)
        found += audit_rune_letters(folder, bank, strings)
        found += audit_skill_lines(folder, bank, strings)
    if layouts and Path(layouts).exists():
        found += audit_layouts(Path(layouts), strings)
    found += audit_colours(strings)
    left, allowed, stale = apply_allow(found, load_allow() if allow is None else allow)
    report = [f"text_audit: {checked} tables, {len(found)} hits, {len(allowed)} allowed, {len(left)} findings"]
    report += [f"  allowed: {a}" for a in allowed]
    report += [f"  designed empty (Median's own `{k}` has no text): {t}: {n} names" for (t, k), n in sorted(designed.items())]
    for a in stale:
        left.append(Finding("stale-allow", a["table"], a["column"], str(ALLOW.name), a["key"], a["reason"]))
    return left, report


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--excel-dir", type=Path, default=ROOT / "work" / "mod" / "data" / "global" / "excel")
    ap.add_argument("--layouts-dir", type=Path, default=ROOT / "work" / "mod" / "data" / "global" / "ui" / "layouts")
    ap.add_argument("--d2r-lng", type=Path)
    ap.add_argument("--report", type=Path, help="also write the findings to this file")
    a = ap.parse_args(argv)
    if a.d2r_lng:
        ns.D2R_LNG = a.d2r_lng
    found, report = audit(a.excel_dir, Strings.load(), a.layouts_dir)
    lines = report + [f"FINDING {f}" for f in found]
    print("\n".join(lines))
    if a.report:
        a.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
