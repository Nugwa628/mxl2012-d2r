"""The Stat Book's data (docs/statbook.md): data/statbook_pages.tsv (the themed pages) and data/advanced_stats.tsv (the All
Stats list) -> the book file the statbook plugin reads, with every stat name resolved to the id of one game's itemstatcost.

The book is plain text, one record per line, fields split by tabs (statbook/src/book_logic.h ParseBook reads it):
  statbook  1                                         first line, the format version
  page      <id>  <tab title>                         a themed page; the records after it belong to it
  section   <heading>                                 a heading line of the page
  row       <label> <stats> <format> <colour> <cap> <base> <size>
            stats   ids joined by "," (two for a range); "<id>:c" = the player's class as the stat's param
            format  %d %+d %% only, or yesno / block            colour  w r b y p m gold blue green
            cap     "-" or <n> or <n>+<id><=<max> (gold at or over it)   base  "-" or n[,n]: added to each value
            size    h (a half line) or f (a full line)
  group     <key> <heading>                           an All Stats group heading
  all       <kind> <ids> <key> <english>              an All Stats row: stat (the game's own item line), range, value, avoid

Rows whose stats the game's itemstatcost lacks are left out (a Median row in the plain D2R book), so one data file makes both
books. The pages of D2R-XL 2012 go into the mod (MOD_FILE, read by the plugin from the mod); the plain D2R book is compiled into
the plugin (statbook/src/default_book.inc) and used when no mod gives one.

  py -3 tools/statbook.py book [--isc <itemstatcost.txt>] [--out <file>]   (defaults: work/mod's, MOD_FILE under work/mod/data)
  py -3 tools/statbook.py default [--isc <D2R itemstatcost.txt>]           writes statbook/src/default_book.inc
  py -3 tools/statbook.py check                                             fails when default_book.inc is out of date
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

PAGES_TSV = ROOT / "data" / "statbook_pages.tsv"
ALL_TSV = ROOT / "data" / "advanced_stats.tsv"
DEFAULT_INC = ROOT / "statbook" / "src" / "default_book.inc"
MOD_FILE = Path("statbook") / "statbook.txt"   # under the mod's data folder (as data/mxl2012-wiki/): the plugin reads it
BUILT_ISC = ROOT / "work" / "mod" / "data" / "global" / "excel" / "itemstatcost.txt"

COLOURS = {"w", "r", "b", "y", "p", "m", "gold", "blue", "green"}
SPECIAL_FORMATS = {"yesno", "block"}
FORMAT_TOKEN = re.compile(r"%(%|\+d|d)")
HALF_LABEL = 22            # labels up to this many characters fit a half line beside a short value
HALF_VALUE = 7             # the longest sample value of a half line ("+1000%")


def read_tsv(path: Path) -> list[list[str]]:
    """The data lines of a tab file: no comments, no empty lines, the header dropped."""
    lines = [ln for ln in path.read_text("utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    return [ln.split("\t") for ln in lines[1:]]


def stat_ids(isc: Path) -> dict[str, int]:
    """itemstatcost row name -> stat id (its row number: D2R reads the table by row)."""
    lines = isc.read_text("latin-1").splitlines()[1:]
    return {ln.split("\t")[0]: i for i, ln in enumerate(lines) if ln.split("\t")[0]}


def sample(fmt: str) -> str:
    """The format with each value a wide sample, for the half / full choice."""
    if fmt in SPECIAL_FORMATS:
        return "100%" if fmt == "block" else "yes"
    return FORMAT_TOKEN.sub(lambda m: "%" if m.group(1) == "%" else "+1000", fmt)


def check_format(fmt: str, values: int) -> None:
    if fmt in SPECIAL_FORMATS:
        if values != 1:
            raise ValueError(f"format {fmt} takes one stat")
        return
    stripped = FORMAT_TOKEN.sub("", fmt)
    if "%" in stripped:
        raise ValueError(f"format {fmt!r}: only %d, %+d and %% are allowed")
    if len([m for m in FORMAT_TOKEN.finditer(fmt) if m.group(1) != "%"]) != values:
        raise ValueError(f"format {fmt!r} does not take {values} value(s)")


def resolve_stat(token: str, ids: dict[str, int]) -> str | None:
    name, _, param = token.partition(":")
    if name not in ids:
        return None
    if param not in ("", "class"):
        raise ValueError(f"stat {token}: the only param is :class")
    return f"{ids[name]}:c" if param == "class" else str(ids[name])


def resolve_cap(cap: str, ids: dict[str, int]) -> str | None:
    """"" -> "-"; "50" -> "50"; "75+maxfireresist<=95" -> "75+40<=95"; None when its stat is missing."""
    if not cap:
        return "-"
    m = re.fullmatch(r"(\d+)(?:\+(\w+)<=(\d+))?", cap)
    if not m:
        raise ValueError(f"cap {cap!r}: N or N+stat<=M")
    if m.group(2) is None:
        return m.group(1)
    if m.group(2) not in ids:
        return None
    return f"{m.group(1)}+{ids[m.group(2)]}<={m.group(3)}"


def page_records(rows: list[list[str]], ids: dict[str, int], dropped: list[str]) -> list[str]:
    out, pages, page = [], set(), None
    for r in rows:
        r = r + [""] * (8 - len(r))
        kind, pid, text, stat, fmt, colour, cap, base = (c.strip() for c in r[:8])
        if kind == "page":
            if pid in pages:
                raise ValueError(f"page {pid} twice")
            pages.add(pid)
            page = pid
            out.append(f"page\t{pid}\t{text}")
        elif kind == "section":
            if pid != page:
                raise ValueError(f"section {text!r} outside its page {pid}")
            out.append(f"section\t{text}")
        elif kind == "row":
            if pid != page:
                raise ValueError(f"row {text!r} outside its page {pid}")
            stats = [s.strip() for s in stat.split(",")]
            if not 1 <= len(stats) <= 2:
                raise ValueError(f"row {text!r}: one or two stats")
            check_format(fmt, len(stats))
            if colour not in COLOURS:
                raise ValueError(f"row {text!r}: colour {colour!r}")
            if base and len(base.split(",")) != len(stats):
                raise ValueError(f"row {text!r}: base {base!r} needs one number per stat")
            if base and not all(re.fullmatch(r"-?\d+", b) for b in base.split(",")):
                raise ValueError(f"row {text!r}: base {base!r}")
            got = [resolve_stat(s, ids) for s in stats]
            c = resolve_cap(cap, ids)
            if None in got or c is None:
                dropped.append(text)
                continue
            half = len(text) <= HALF_LABEL and len(sample(fmt)) <= HALF_VALUE
            out.append("\t".join(["row", text, ",".join(got), fmt, colour, c, base or "-", "h" if half else "f"]))
        else:
            raise ValueError(f"unknown kind {kind!r}")
    # a section or page left empty by dropped rows goes too
    kept: list[str] = []
    for i, rec in enumerate(out):
        nxt = out[i + 1] if i + 1 < len(out) else ""
        if rec.startswith("section\t") and not nxt.startswith("row\t"):
            continue
        kept.append(rec)
    final: list[str] = []
    for i, rec in enumerate(kept):
        nxt = kept[i + 1] if i + 1 < len(kept) else ""
        if rec.startswith("page\t") and (nxt == "" or nxt.startswith("page\t")):
            continue
        final.append(rec)
    return final


def all_records(ids: dict[str, int], dropped: list[str]) -> list[str]:
    import advanced_stats as adv
    out, group = [], None
    for r in adv.read_rows(ALL_TSV):
        if any(s not in ids for s in r["stats"]):
            dropped.append(",".join(r["stats"]))
            continue
        if r["group"] != group:
            group = r["group"]
            key, english = adv.GROUPS[group]
            out.append(f"group\t{key}\t{english}")
        key = r["key"] or "-"
        english = adv.TEXTS.get(r["key"], "-") if r["key"] else "-"
        out.append("\t".join(["all", r["kind"] or "stat", ",".join(str(ids[s]) for s in r["stats"]), key, english]))
    return out


def book_text(ids: dict[str, int], dropped: list[str] | None = None) -> str:
    dropped = [] if dropped is None else dropped
    recs = ["statbook\t1"] + page_records(read_tsv(PAGES_TSV), ids, dropped) + all_records(ids, dropped)
    return "\n".join(recs) + "\n"


def inc_text(book: str) -> str:
    """The plain D2R book as a C++ raw string (statbook/src/statbook.cpp includes it)."""
    return ("// Generated by tools/statbook.py from data/statbook_pages.tsv and data/advanced_stats.tsv for plain D2R's\n"
            "// itemstatcost; do not edit (py -3 tools/statbook.py default).\n"
            f'R"BOOK({book})BOOK"\n')


def d2r_isc() -> Path:
    import fxpaths
    return Path(fxpaths.D2R) / "data" / "global" / "excel" / "itemstatcost.txt"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("book")
    b.add_argument("--isc", type=Path, default=BUILT_ISC)
    b.add_argument("--out", type=Path, default=ROOT / "work" / "mod" / "data" / MOD_FILE)
    d = sub.add_parser("default")
    d.add_argument("--isc", type=Path)
    c = sub.add_parser("check")
    c.add_argument("--isc", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "book":
        dropped: list[str] = []
        text = book_text(stat_ids(a.isc), dropped)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, "utf-8", newline="\n")
        print(f"wrote {a.out}: {text.count(chr(10) + 'page')} pages, {text.count(chr(10) + 'row')} rows, "
              f"{text.count(chr(10) + 'all')} All Stats rows; left out (not in this itemstatcost): {len(dropped)}")
        return 0
    text = inc_text(book_text(stat_ids(a.isc or d2r_isc())))
    if a.cmd == "default":
        DEFAULT_INC.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_INC.write_text(text, "utf-8", newline="\n")
        print(f"wrote {DEFAULT_INC}")
        return 0
    if not DEFAULT_INC.is_file() or DEFAULT_INC.read_text("utf-8").replace("\r\n", "\n") != text:
        print(f"{DEFAULT_INC} is out of date: py -3 tools/statbook.py default")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
