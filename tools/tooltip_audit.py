#!/usr/bin/env python3
"""Item tooltip text audit (docs/item-tooltips.md): what Median prints for every stat that has a property line, against what
D2R prints in game.

  py -3 tools/tooltip_audit.py commands                  the `h tipfmt` lines the in-game check sends (one per displayed stat)
  py -3 tools/tooltip_audit.py report --results F        the table of docs/item-tooltips.md from the answers in F
        [--baseline F]  the answers of the build before the fix (the "before" column and counts)
        [--out FILE]    default docs/item-tooltips.md (only the part between the table markers is replaced)

`tools/game_checks.py tooltiptext` writes the answers (work/tooltip_audit/results.txt) and runs the whole thing in game.

The expected text is what Median's descfunc (D2Sigma D2ItemDesc.cpp: the shared functions 1-13, 20-23 and Median's 31-38,
read in the decompile; docs/item-tooltips.md) writes for the sample value, from Median's own stat table (work/named) and the
strings the player reads (tools/strings_ns.effective_texts). Stats whose line needs a skill, a class, an event or a monster
type from the item (descfunc 11, 13-18, 22-24, 27-29) are checked on real items instead (the sweep of the in-game check).
"""
import argparse
import ast
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import strings_ns  # noqa: E402

NAMED = ROOT / "work" / "named" / "itemstatcost.txt"
MOD = ROOT / "work" / "mod" / "data" / "global" / "excel" / "base" / "itemstatcost.txt"
DOC = ROOT / "docs" / "item-tooltips.md"
START, END = "<!-- table:start -->", "<!-- table:end -->"

VALUE = 12
SKILL_SAMPLE = 623  # Jitan's Gate: a skill with a name in Median's skill table (the unique "Weather Control" rolls its cooldown)
SAMPLES = {  # stat -> (value, layer) where the plain 12 / 0 does not show the line
    289: (2, 0),                  # Median's honorific line shows at the value 2 only
    444: (45, (3 << 8) | 2),      # 45% of Vitality as cold damage
    309: (50, SKILL_SAMPLE),      # 50 frames
    478: (VALUE, SKILL_SAMPLE),
    456: (VALUE, 0),
    492: (4, 0),                  # class lock: Paladin
    404: (9, 11278), 406: (9, 12185), 407: (9, 12376), 414: (1, 11278),
}
# The lines that name a skill, a class or an event of the item (the D2R functions) are checked on real items.
ITEM_FUNCS = {11, 13, 14, 15, 16, 17, 18, 22, 23, 24, 27, 28, 29}
VALUE_FIRST = {1, 2, 3, 4, 6, 7, 8, 9, 12, 20, 21, 22, 23}
PRINTF = re.compile(r"(?<!%)%[-+#0-9.]*[diuxfs]")
CLASS_ONLY = ["(Amazon Only)", "(Sorceress Only)", "(Necromancer Only)", "(Paladin Only)", "(Barbarian Only)", "(Druid Only)",
              "(Assassin Only)"]
COLOUR = re.compile("(?:\u00ffc|\ue07e).")  # Median's \u00ffc<char> and D2R's U+E07E<char> colour codes


def read_table(path: Path):
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:] if len(r) > 3 and r[0]]


def key_of(cell: str) -> str:
    return cell.split(":", 1)[-1] if cell else ""


def displayed_stats():
    """Every Median stat with a property line: (mod stat id, name, Median descfunc, Median row, built row)."""
    mod = {r["Stat"]: r for r in read_table(MOD)}
    out = []
    for r in read_table(NAMED):
        if not r.get("descfunc"):
            continue
        m = mod.get(r["Stat"])
        if m is None:
            continue
        out.append((int(m["*ID"]), r["Stat"], int(r["descfunc"]), r, m))
    out.sort(key=lambda x: x[0])
    # the class lock stat has no line in Median's table (the item's requirement text names the class); the port gives it one
    if not any(s[0] == 492 for s in out):
        m = next((r for r in mod.values() if r["*ID"] == "492"), None)
        if m is not None:
            out.append((492, m["Stat"], 0, m, m))
    return out


GROUP = 10000  # results key of a stat's group line (flag 1): GROUP + stat


def group_stats():
    """Every stat that joins a group line ("+N to all Attributes": the dgrp columns): (mod stat id, name, dgrpfunc, Median row, built
    row), the rows with the dgrp columns under the names of the description columns."""
    mod = {r["Stat"]: r for r in read_table(MOD)}

    def as_desc(r):
        return {"descfunc": r.get("dgrpfunc", ""), "descval": r.get("dgrpval", ""), "descstrpos": r.get("dgrpstrpos", ""),
                "descstrneg": r.get("dgrpstrneg", ""), "descstr2": r.get("dgrpstr2", "")}

    out = []
    for r in read_table(NAMED):
        m = mod.get(r["Stat"])
        if m is not None and r.get("dgrp") and r.get("dgrpfunc"):
            out.append((int(m["*ID"]), r["Stat"], int(r["dgrpfunc"]), as_desc(r), as_desc(m)))
    out.sort(key=lambda x: x[0])
    return out


def sample(stat: int):
    return SAMPLES.get(stat, (VALUE, 0))


def commands():
    """The tipfmt lines of the check: `tipfmt <stat> <value> <layer> 4 [1]` (the flag 1 lines are the group lines)."""
    return (["tipfmt %d %d %d 4" % ((s[0],) + sample(s[0])) for s in displayed_stats()] +
            ["tipfmt %d %d 0 4 1" % (s[0], VALUE) for s in group_stats()])


def printf(text: str, value: int) -> str:
    """snprintf(text, value) as D2R's function 19 does it (one integer argument; %% is a percent sign)."""
    def one(m):
        spec = m.group(0)
        return (spec % value) if spec[-1] in "diux" else spec
    return PRINTF.sub(one, text).replace("%%", "%")


def number(v: int, plus: bool = True) -> str:
    return ("+%d" % v) if (plus and v > 0) else "%d" % v


KEPT = re.compile(r"^\s*- kept `([^`]+)`: D2R (.+?) / Median (.+)$")


def kept_d2r_texts() -> dict:
    """key -> the text D2R keeps for a key whose placeholders differ from Median's (work/mod/strings_report.md of tbl2json.py)."""
    out = {}
    report = ROOT / "work" / "mod" / "strings_report.md"
    for ln in report.read_text("utf-8").splitlines() if report.exists() else []:
        m = KEPT.match(ln)
        if m:
            try:
                out[m.group(1)] = ast.literal_eval(m.group(2))
            except (ValueError, SyntaxError):
                pass
    return out


def median_text(texts: dict, cell: str) -> str:
    """Median's text of a description cell: the alias `<key>_mxl` of a key whose D2R text was kept (tbl2json.py)."""
    key = key_of(cell)
    return texts.get(key + "_mxl", texts.get(key, "")) if key else ""


def expected(stat: int, fn: int, row: dict, texts: dict):
    """(text, kind): kind 'text' = exact, 'regex' = text is a pattern, 'none' = no line, 'item' = needs a real item."""
    value, _ = sample(stat)
    dv = int(row.get("descval") or 0)
    pos, neg, s2 = (median_text(texts, row.get(c, "")) for c in ("descstrpos", "descstrneg", "descstr2"))
    text = neg if value < 0 and neg else pos
    if stat == 492:
        return CLASS_ONLY[value - 1], "text"
    if fn in (31, 34):
        import tbl2json
        return tbl2json.load_median()[0][sample(stat)[1]][1], "text"
    if fn == 0:
        return "", "none"
    if fn in ITEM_FUNCS:
        return "(skill, class or event of the item)", "item"
    if not text:
        return "", "none"
    if fn == 32 or fn == 38:
        n = max(value // 10, 1) if fn == 32 else value
        num = number(n)
        return {1: "%s %s" % (num, text), 2: "%s %s" % (text, num)}.get(dv, text), "text"
    if fn == 33:
        return "[A-Za-z' ]+ Cooldown (Reduced|Decreased) by [0-9.e+-]+", "regex"
    if fn == 35:
        return r"Innate \w+ Damage: \d+ \(\d+\.\d% of \w+\)", "regex"
    if fn == 36:
        return (text if value == 2 else ""), ("text" if value == 2 else "none")
    if fn == 37:
        return r"[A-Za-z' ]+ Maximum Skill Level Increased by %d" % value, "regex"
    if fn == 19 or (fn in VALUE_FIRST and PRINTF.search(text)):
        line = printf(text, value)
        return (line + (" " + s2 if s2 else "")), "text"
    if fn == 5:
        if PRINTF.search(text):
            return printf(text, value * 100 // 128), "text"
        pct = "%d%%" % (value * 100 // 128)
        return {1: "%s %s" % (pct, text), 2: "%s %s" % (text, pct)}.get(dv, text), "text"
    if fn in (1, 12, 6):
        num, plus = number(value), True
    elif fn in (4, 8):
        num, plus = number(value) + "%", True
    elif fn in (2, 7):
        num = "%d%%" % value
    elif fn in (3, 9):
        num = "%d" % value
    elif fn == 20:
        num = "%d%%" % -value
    elif fn == 21:
        num = "%d" % -value
    else:
        return "(descfunc %d)" % fn, "item"
    line = {1: "%s %s" % (num, text), 2: "%s %s" % (text, num)}.get(dv, text)
    if fn in (6, 7, 8, 9) and s2:
        line += " " + s2
    return line, "text"


RESULT = re.compile(r"tipfmt stat=(-?\d+) value=(-?\d+) layer=(-?\d+) mode=(-?\d+)(?: flag=(\d+))? ret=(-?\d+) text=\[(.*)\]$")


def parse_results(lines):
    """stat (GROUP + stat for a group line) -> (value, layer, ret, text) of the `tipfmt` answers (the last answer wins)."""
    out = {}
    for ln in lines:
        m = RESULT.search(ln.strip())
        if m:
            out[int(m.group(1)) + (GROUP if m.group(5) == "1" else 0)] = (int(m.group(2)), int(m.group(3)), int(m.group(6)), m.group(7))
    return out


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", COLOUR.sub("", text)).strip()


def leaks(text: str) -> str:
    """What is wrong with a printed line by itself: '' when nothing."""
    if "FLYING POLAR BUFFALO" in text:
        return "missing string"
    if PRINTF.search(text.replace("%%", "")) or "%%" in text:
        return "printf placeholder"
    if "Chronicle" in text or "Random Class" in text:
        return "Chronicle text"
    return ""


def verdict(stat: int, exp, kind: str, shown):
    """(verdict, why) of one stat."""
    if shown is None:
        return "NOT RUN", ""
    value, layer, ret, text = shown
    text = norm(text)
    bad = leaks(text)
    if bad:
        return "WRONG", bad
    if kind == "none":
        return ("OK", "no line") if not text else ("WRONG", "a line where Median prints none")
    if kind == "item":
        return ("ITEM", "checked on real items") if text else ("ITEM", "no text at this sample; real items")
    if not text:
        return "WRONG", "empty line"
    ok = re.fullmatch(exp, text) if kind == "regex" else text == norm(exp)
    return ("OK", "") if ok else ("DIFF", "differs from the rule")


def md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def was_wrong(kind: str, text: str) -> bool:
    """Whether a line of the unfixed build was wrong: a leaked placeholder or missing string, a line where Median has none, or no
    line where Median has one."""
    text = norm(text)
    if leaks(text):
        return True
    if kind == "none":
        return bool(text)
    return kind != "item" and not text


def judge(results):
    """One dict per displayed stat: stat, name, fn (Median's), fn_built, exp, kind, verdict, why, shown (the readback or None)."""
    all_texts = strings_ns.effective_texts()
    kept = kept_d2r_texts()
    out = []
    for group, (stat, name, fn, mrow, built) in [(False, e) for e in displayed_stats()] + [(True, e) for e in group_stats()]:
        median_fn = fn
        texts = all_texts
        if not any(mrow.get(c) for c in ("descstrpos", "descstrneg", "descstr2")) and built.get("descstrpos"):
            mrow, fn = built, int(built.get("descfunc") or 0)  # Median draws the line in code: the port restores D2R's description
            texts = {**{k: v for k, v in texts.items() if not k.endswith("_mxl")}, **kept}
        exp, kind = expected(stat, fn, mrow, texts)
        key = GROUP + stat if group else stat
        shown = results.get(key)
        v, why = verdict(stat, exp, kind, shown)
        out.append({"stat": stat, "key": key, "label": "%d%s" % (stat, " (group)" if group else ""),
                    "name": name, "fn": median_fn, "fn_built": built.get("descfunc") or "-", "exp": exp, "kind": kind,
                    "verdict": v, "why": why, "shown": shown})
    return out


def problems(results):
    """The stats whose line is wrong (verdict WRONG / DIFF / NOT RUN): 'stat name: why (shown text)'."""
    return ["%s %s: %s %s [%s]" % (j["label"], j["name"], j["verdict"], j["why"], norm(j["shown"][3]) if j["shown"] else "")
            for j in judge(results) if j["verdict"] in ("WRONG", "DIFF", "NOT RUN")]


def table(results, baseline):
    rows, counts, wrong_before = [], {}, 0
    head = "\n".join(("| stat | name | descfunc | expected | before (unfixed build) | shown | verdict |", "|---|---|---|---|---|---|---|"))
    for j in judge(results):
        stat, kind, exp, shown, v, why = j["stat"], j["kind"], j["exp"], j["shown"], j["verdict"], j["why"]
        counts[v] = counts.get(v, 0) + 1
        b = baseline.get(j["key"])
        if b is not None and was_wrong(kind, b[3]):
            wrong_before += 1
        fn_text = "%s" % (j["fn"] or "-") + ("" if not j["fn"] or str(j["fn"]) == j["fn_built"] else " -> " + j["fn_built"])
        exp_text = "_(item)_" if kind == "item" else (md(exp) if exp else "_(no line)_")
        before = (md(norm(b[3])) or "_(no line)_") if b is not None else ""
        now = (md(norm(shown[3])) or "_(no line)_") if shown is not None else ""
        rows.append("| %s | %s | %s | %s | %s | %s | %s%s |" % (j["label"], md(j["name"]), fn_text, exp_text, before, now, v,
                                                           (" (%s)" % why) if why else ""))
    summary = "%d property lines (stats and group lines): %s." % (len(rows), ", ".join("%d %s" % (n, k) for k, n in sorted(counts.items())))
    if baseline:
        summary += " The unfixed build had %d wrong lines among them." % wrong_before
    return summary, "\n".join([head] + rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("commands", "report"))
    ap.add_argument("--results")
    ap.add_argument("--baseline")
    ap.add_argument("--out", default=str(DOC))
    a = ap.parse_args()
    if a.what == "commands":
        print("\n".join(commands()))
        return 0
    if not a.results:
        ap.error("report needs --results")
    results = parse_results(Path(a.results).read_text("utf-8", errors="replace").splitlines())
    baseline = parse_results(Path(a.baseline).read_text("utf-8", errors="replace").splitlines()) if a.baseline else {}
    summary, body = table(results, baseline)
    out = Path(a.out)
    doc = out.read_text("utf-8") if out.exists() else ""
    block = "%s\n%s\n\n%s\n%s" % (START, summary, body, END)
    if START in doc and END in doc:
        doc = doc[:doc.index(START)] + block + doc[doc.index(END) + len(END):]
    else:
        doc += "\n" + block + "\n"
    out.write_text(doc, "utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
