"""Formula text fix-ups for D2R's BBE parser (playbook trap 8). Median XL 2012 writes 1.13c formula text, which already
uses the `skill('Name'.blvl)` / `stat('name'.accr)` syntax D2R keeps, so only D2R's stricter parser needs help:

  * bare negative literals are rejected: `-1`, `min(0,-1*x)` -> `(0-1)`; `(0-N)` is what D2R's own formulas use
  * the branches of a ternary must be bracketed when they are not a single term: `c?a+b:d` -> `c?(a+b):d`
  * a cell wrapped in double quotes with `;` for `,` (`"max((a);50)"`, a typo of the mod) -> `max((a),50)`
  * `ulvl` (the player's level) is a skill / missile / monster scope code but not an item scope one: in item formulas it
    is `stat('level'.accr)`
  * calls to names that do not exist (`skill('Clay Golem'.blvl)` where the mod repurposed the row) -> `0`
    (the compiler of 1.13c evaluates an unknown name to 0; D2R refuses the cell)

`fix(text, scope, exists)` returns (new text, list of notes). `exists(func, name)` answers whether skill / miss / stat /
sksrc / sklvl `name` exists (case-insensitively; the real spelling is substituted).
"""
from __future__ import annotations

import re

CALL = re.compile(r"\b(skill|sksrc|sklvl|miss|stat)\('([^']*)'((?:\.[A-Za-z0-9_]+)+)\)")
TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<str>'[^']*')|(?P<id>[A-Za-z_][A-Za-z0-9_]*)|(?P<op><=|>=|==|!=|&&|\|\||[-+*/%^()?:<>,.!]))")


def tokens(text: str) -> list[tuple[str, str]] | None:
    out, pos = [], 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m or m.end() == pos:
            return None
        out.append((m.lastgroup, m.group(m.lastgroup)))
        pos = m.end()
    return out


def balanced(text: str) -> bool:
    depth = 0
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            return False
    return depth == 0


def negatives(text: str) -> str:
    """`-N` at the start of an operand (after `(`, `,`, `?`, `:`, an operator or at the start) -> `(0-N)`."""
    toks = tokens(text)
    if toks is None:
        return text
    out: list[str] = []
    i = 0
    prev_operand = False
    while i < len(toks):
        kind, v = toks[i]
        if kind == "op" and v == "-" and not prev_operand and i + 1 < len(toks) and toks[i + 1][0] == "num":
            out.append(f"(0-{toks[i + 1][1]})")
            i += 2
            prev_operand = True
            continue
        out.append(v)
        prev_operand = kind in ("num", "str", "id") or (kind == "op" and v == ")")
        i += 1
    return "".join(out)


def _top_ops(s: str) -> str:
    """The characters of `s` outside brackets and quotes."""
    out, depth, quoted = [], 0, False
    for ch in s:
        if ch == "'":
            quoted = not quoted
            continue
        if quoted:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def _is_term(branch: str) -> bool:
    return not re.search(r"[-+*/%<>=!&|?:\s]", _top_ops(branch.strip()))


def ternary(text: str) -> str:
    """Bracket ternary branches that are not a single term (`c?a+b:d` -> `c?(a+b):d`), at every bracket level."""
    if "?" not in text:
        return text
    # 1. recurse into bracket groups
    out, i = [], 0
    quoted = False
    while i < len(text):
        ch = text[i]
        if ch == "'":
            quoted = not quoted
        if ch == "(" and not quoted:
            depth, j = 0, i
            while j < len(text):
                if text[j] == "'":
                    quoted = not quoted
                if not quoted:
                    depth += (text[j] == "(") - (text[j] == ")")
                if depth == 0:
                    break
                j += 1
            out.append("(" + ternary(text[i + 1:j]) + ")")
            i = j + 1
            continue
        out.append(ch)
        i += 1
    s = "".join(out)
    # 2. this level: first top-level `?` and its matching `:`
    depth, quoted, q, c, nest = 0, False, None, None, 0
    for k, ch in enumerate(s):
        if ch == "'":
            quoted = not quoted
        if quoted:
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and ch == "?":
            if q is None:
                q = k
            else:
                nest += 1
        elif depth == 0 and ch == ":" and q is not None:
            if nest:
                nest -= 1
            else:
                c = k
                break
    if q is None or c is None:
        return s
    cond, yes, no = s[:q], s[q + 1:c], s[c + 1:]
    yes = ternary(yes) if "?" in _top_ops(yes) else yes
    no = ternary(no) if "?" in _top_ops(no) else no
    wrap = lambda b: b if _is_term(b) else f"({b.strip()})"
    return f"{cond}?{wrap(yes)}:{wrap(no)}"


def calls(text: str, scope: str, exists, notes: list[str]) -> str:
    def sub(m: re.Match) -> str:
        func, name, rest = m.group(1), m.group(2), m.group(3)
        real = exists(func, name)
        if real is None:
            notes.append(f"{func}('{name}'): no such row -> 0")
            return "0"
        return m.group(0) if real == name else f"{func}('{real}'{rest})"
    text = CALL.sub(sub, text)
    return text


def unknown_codes(text: str, codes: set[str], notes: list[str]) -> str:
    """Bare identifiers that are no calc code of the scope (`elen`, a typo of the mod) evaluate to 0 in 1.13c."""
    toks = tokens(text)
    if toks is None:
        return text
    out, bad = [], False
    for i, (k, v) in enumerate(toks):
        nxt = toks[i + 1][1] if i + 1 < len(toks) else ""
        prev = toks[i - 1][1] if i else ""
        if k == "id" and nxt != "(" and prev != "." and v.lower() not in codes:
            notes.append(f"unknown code '{v}' -> 0")
            out.append("0")
            bad = True
        else:
            out.append(v)
    return "".join(out) if bad else text


def fix(text: str, scope: str, exists, codes: set[str] | None = None) -> tuple[str, list[str]]:
    notes: list[str] = []
    new = text
    if len(new) > 1 and new[0] == new[-1] == '"':
        new = new[1:-1].replace(";", ",")
        notes.append("quotes removed")
    if scope == "Item":
        new = re.sub(r"\bulvl\b", "stat('level'.accr)", new)
    if "(" in new or "'" in new:
        new = calls(new, scope, exists, notes)
    if codes is not None:
        new = unknown_codes(new, codes, notes)
    depth = 0
    for ch in new:
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            break
    if depth > 0:
        new += ")" * depth
        notes.append(f"{depth} closing bracket(s) appended")
    new2 = negatives(new)
    if new2 != new:
        notes.append("negative literal bracketed")
        new = new2
    if "?" in new:
        new2 = ternary(new)
        if new2 != new:
            notes.append("ternary branches bracketed")
            new = new2
    return new, notes
