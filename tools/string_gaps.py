"""String keys the migrated tables name that neither Median XL 2012's .tbl files nor D2R define, and the other text fixes of the
text lane (docs/text-audit.md). The decisions are rows of `data/string_gaps.tsv`
(table, column, key, action, text, cells, reason).

Origin: `strings_check.py` reported 104 cells (v005): 46 shrine cells + 58 others. The shrines are a port bug (shrines.txt
StringName / StringPhrase = `blah` in all 23 rows: 1.13c ignores both columns, the shrine text is `ShrId<n>` / `ShrMsg<n>` of the
tbl by row, D2R reads them; txt_migrate.py D2R_ALWAYS makes the rows take D2R's `ShrId<n>` / `ShrMsg<n>`, which the d2r: overrides
carry Median's text for). Every other key is absent from Median's own .tbl too (patch_d2.mpq ships all three), so 1.13c met the
same miss. Until 2026-10-28 such names became their own key as text (`raw`: "CouatlInhibitor" on a monster) and description lines
were emptied. Owner decision 2026-10-28: no raw text anywhere a player sees it, a full translation of Median XL 2012 into D2R. So:

  action `text`   the key gets a text of its own (tbl2json.py adds it to the mxl2012 namespace, txt_migrate.py qualifies the
                  cells; 13 languages the same): a name in words (CamelCase split, Median's typos fixed, the name Median uses
                  elsewhere for the same thing) or a tooltip line in Median's wording style. Optional `cells`
                  (`col=value;col=value`) sets other cells of every row that names the key in `column` (itemstatcost: the
                  function / value cells of the line)
  action `fix`    Median's own text of the key (table and column empty) is replaced: it reads like a key (`PortalKombat`)
  action `cell`   one cell of a row is set: `key` = `<matching column>=<value>`, `column` = the cell to write, `text` = its
                  value (a monster whose NameStr is blank gets D2R's key)
  action `empty`  the cell is emptied (itemstatcost: its function and value cell too). Only for a line the original never showed
                  (the four Greater Elixirs, bug #104): the owner wants every other line shown

  py -3 -I tools/string_gaps.py apply --excel-dir work/mod/data/global/excel [--d2r-lng DIR]   the `empty`, `cell` and `cells`
                                                                         rows; exit 1 when a cell still names an unknown key
  py -3 -I tools/string_gaps.py docs                                     the markdown table for docs/tables-status.md
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
GAPS = ROOT / "data" / "string_gaps.tsv"
ACTIONS = ("text", "fix", "cell", "empty")
# itemstatcost: function + value cells that go with a group of string cells; emptied together
DESC_GROUPS = ((("descfunc", "descval"), ("descstrpos", "descstrneg", "descstr2")),
               (("dgrpfunc", "dgrpval"), ("dgrpstrpos", "dgrpstrneg", "dgrpstr2")))


def load(path: Path = GAPS) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    seen: dict[str, str] = {}
    for r in rows:
        where = f"{path}: {r['table']}.{r['column']} {r['key']!r}"
        if r["action"] not in ACTIONS:
            raise ValueError(f"{where}: action {r['action']!r} is not one of {ACTIONS}")
        if not r["reason"].strip():
            raise ValueError(f"{where}: no reason")
        if r["action"] != "empty" and not r["text"].strip():
            raise ValueError(f"{where}: action {r['action']} needs a text")
        if r["action"] == "cell" and "=" not in r["key"]:
            raise ValueError(f"{where}: a `cell` key is `<column>=<value>`")
        if r["action"] == "fix" and (r["table"] or r["column"]):
            raise ValueError(f"{where}: a `fix` row names the key only (table and column empty)")
        if r["action"] in ("text", "fix"):
            if seen.setdefault(r["action"] + r["key"], r["text"]) != r["text"]:
                raise ValueError(f"{where}: the key has two different texts")
    return rows


def _text(r: dict) -> str:
    return r["text"].replace("\\n", "\n")


def texts(gaps: list[dict] | None = None) -> dict[str, str]:
    """key -> text for the `text` rows (tbl2json.py adds them to the mod's namespace)."""
    return {r["key"]: _text(r) for r in (load() if gaps is None else gaps) if r["action"] == "text"}


def fixes(gaps: list[dict] | None = None) -> dict[str, str]:
    """key -> text for the `fix` rows: Median's own text of a key is replaced (tbl2json.py)."""
    return {r["key"]: _text(r) for r in (load() if gaps is None else gaps) if r["action"] == "fix"}


def split_cells(spec: str) -> list[tuple[str, str]]:
    return [tuple(x.split("=", 1)) for x in spec.split(";") if x.strip()]


def apply_empty(excel: Path, gaps: list[dict] | None = None) -> Counter:
    """Apply the rows that change cells of one bank folder `excel`: `empty` (the cell is emptied), `text` rows with `cells`
    (the other cells of the line are set) and `cell` rows. -> Counter (table.column -> cells)."""
    gaps = load() if gaps is None else gaps
    done: Counter = Counter()
    by_table: dict[str, list[dict]] = {}
    for g in gaps:
        if g["action"] in ("empty", "cell") or (g["action"] == "text" and g["cells"].strip()):
            by_table.setdefault(g["table"], []).append(g)
    for table, gs in by_table.items():
        path = Path(excel) / f"{table}.txt"
        if not path.exists():
            continue
        eol = "\r\n" if b"\r\n" in path.read_bytes() else "\n"
        lines = path.read_bytes().decode("utf-8").split(eol)
        head = lines[0].split("\t")
        low = [h.strip().lower() for h in head]
        empties = {(g["column"].lower(), g["key"].lower()) for g in gs if g["action"] == "empty"}
        cols = {c for c, _k in empties}
        changed = False
        for n in range(1, len(lines)):
            if not lines[n]:
                continue
            cells = lines[n].split("\t")
            touched = set()
            for c in cols:
                if c in low and low.index(c) < len(cells):
                    i = low.index(c)
                    have = cells[i].strip().lower()
                    if (c, have) in empties or (c, have.split(":", 1)[-1]) in empties:  # a key txt_migrate qualified (mxl2012:Key) too
                        cells[i] = ""
                        touched.add(c)
                        done[f"{table}.{c}"] += 1
            if table == "itemstatcost" and touched:
                for fn_cols, str_cols in DESC_GROUPS:
                    if touched & set(str_cols) and all(not cells[low.index(c)] for c in str_cols if c in low):
                        for fc in fn_cols:
                            if fc in low and cells[low.index(fc)]:
                                cells[low.index(fc)] = ""
                                done[f"{table}.{fc}"] += 1
            for g in gs:
                col = g["column"].lower()
                if g["action"] == "text":  # the other cells of the line that names the key
                    if col in low and low.index(col) < len(cells) and \
                            cells[low.index(col)].split(":", 1)[-1].strip().lower() == g["key"].lower():
                        for c, v in split_cells(g["cells"]):
                            if c.lower() in low and cells[low.index(c.lower())] != v:
                                cells[low.index(c.lower())] = v
                                touched.add(c)
                                done[f"{table}.{c.lower()}"] += 1
                elif g["action"] == "cell":
                    mcol, mval = g["key"].split("=", 1)
                    if mcol.lower() in low and col in low and max(low.index(mcol.lower()), low.index(col)) < len(cells) \
                            and cells[low.index(mcol.lower())].strip().lower() == mval.lower():
                        if cells[low.index(col)] != g["text"]:
                            cells[low.index(col)] = g["text"]
                            touched.add(col)
                            done[f"{table}.{col}"] += 1
            if touched:
                lines[n] = "\t".join(cells)
                changed = True
        if changed:
            path.write_bytes(eol.join(lines).encode("utf-8"))
    return done


def docs_table(gaps: list[dict] | None = None) -> str:
    gaps = load() if gaps is None else gaps
    out = ["| Table.column | Key | Text it reads | Why |", "|---|---|---|---|"]
    out.append("| shrines.StringName / StringPhrase | `blah` (23 + 23 cells) | D2R's `ShrId<n>` / `ShrMsg<n>`, Median's wording | "
               "**port bug, fixed**: 1.13c never read the columns (Median's tbl has `ShrId0-22` / `ShrMsg0-22`, the d2r: overrides "
               "carry its wording) |")
    groups: dict[tuple, list[dict]] = {}
    for g in sorted(gaps, key=lambda g: (g["action"], g["table"], g["column"], g["key"])):
        groups.setdefault((g["action"], g["table"], g["key"], g["text"]), []).append(g)  # pos / neg cells share a row
    for (action, table, key, text), gs in groups.items():
        cols = " / ".join(dict.fromkeys(g["column"] for g in gs))
        where = f"{table}.{cols}" if table else "(Median's own text)"
        read = {"empty": "(no line)", "cell": f"cell set to `{text}`"}.get(action, text.replace("|", "/"))
        out.append(f"| {where} | `{key}` | {read} | {gs[0]['reason'].replace('|', '/')} |")
    return "\n".join(out)


def unresolved(excel: Path, d2r_lng: Path | None = None) -> list[str]:
    """Cells of the migrated tables (one bank) naming a key nobody defines, as strings_check.py counts them."""
    import strings_check as sc
    import strings_ns as ns
    if d2r_lng:
        ns.D2R_LNG = Path(d2r_lng)
    errors: list[str] = []
    d2r_loaded, d2r_all = ns.d2r_loaded(), ns.d2r_keys()
    g2, _ = sc.check_files(errors, d2r_loaded)
    missing = defaultdict(list)
    sc.check_cells(Path(excel), True, g2, d2r_all, d2r_loaded, errors, missing, {"cells": 0, "missing_cells": 0})
    return [f"{col}: {v}" for col, vals in sorted(missing.items()) for v in sorted(set(vals))]


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("apply")
    p.add_argument("--excel-dir", type=Path, default=ROOT / "work" / "mod" / "data" / "global" / "excel")
    p.add_argument("--d2r-lng", type=Path)
    sub.add_parser("docs")
    a = ap.parse_args(argv)
    if a.cmd == "docs":
        print(docs_table())
        return 0
    total: Counter = Counter()
    left = []
    for bank in ("base", ""):
        folder = a.excel_dir / bank if bank else a.excel_dir
        total.update(apply_empty(folder))
        left += [f"{bank or 'rotw'}: {x}" for x in unresolved(folder, a.d2r_lng)]
    print("changed cells (both banks): " + (", ".join(f"{k} {n}" for k, n in sorted(total.items())) or "none"))
    for x in left:
        print("UNRESOLVED " + x)
    print(f"string_gaps: {len(left)} cells name a key nobody defines")
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
