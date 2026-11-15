"""The red "Entering ..." banner of every level reads the level's Median XL 2012 name (docs/bugs.md #612, docs/strings.md).

D2R draws levels.txt `LevelEntry` (a string key) in red at the top of the screen on every arrival in a level, in HD and in legacy
graphics alike (D2R's strings-legacy/ has no Entering keys, both modes read strings/). 1.13c has no banner (its EntryFile column
is a picture name), so txt_migrate.level_entries gives a Median row D2R's key of the same level (EnteringTheCaveLevel2). Median
kept vanilla's string KEYS for its levels and changed their TEXT in its .tbl files ("Cave Level 2" reads "Duncraig"), so
tbl2json's `d2r:` overrides rename the automap name, while D2R's Entering key keeps vanilla's text ("Entering The Cave Level 2").

  apply   every level whose banner does not read its name gets a `d2r:<LevelEntry key>` override "Entering <name>" in all 13
          languages (Median is English only, its names fill all 13 the same, docs/strings.md); a name that is already a phrase
          ("Welcome to Toraja", Median's Hell1) is the banner as it is. The records go to strings/mxl2012/level_entries.json and are
          folded into overrides.json at once (tools/merge_string_overrides.py, the file is parked in <mod>/string_extras/).
          Then the check below; exit 1 when a level is still wrong or two levels share a key with different names.
  check   every named level of both banks: the banner (enUS) reads "Entering <name>" or the name; exit 1 otherwise.
          --report FILE writes the table of every level (bank, Id, LevelName key, name, LevelEntry key, banner, ok / WRONG).

  py -3 -I tools/level_entries.py apply|check [--mod work/mod] [--d2r-lng <D2R 93847>/data/local/lng] [--report FILE]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402,F401  (.mxl-local.json defaults)
import merge_string_overrides  # noqa: E402

NAMESPACE = "mxl2012"
PREFIX = NAMESPACE + ":"
D2R_PREFIX = "d2r:"
OUT_FILE = "level_entries.json"
# D2R strings/ files the game does not use for the English client: the Chinese region's renames ("Entering The Scarlet Moor")
OVERLAY_FILES = {"chinese-overlay.json"}
# Median names that are a phrase of their own: the banner is the name, no "Entering" in front
PHRASE_STARTS = ("welcome to ",)


def _norm(text: str) -> str:
    t = " ".join(text.replace("\xa0", " ").split()).lower()
    return t[4:] if t.startswith("the ") else t


def banner_reads(name: str, banner: str) -> bool:
    """The banner names the level: "Entering [The] <name>" or the name itself (case, spaces and a leading "The" aside)."""
    if not name or not banner:
        return False
    b = " ".join(banner.replace("\xa0", " ").split())
    if b.lower().startswith("entering "):
        b = b[len("entering "):]
    return _norm(b) == _norm(name)


def banner_for(name: str) -> str:
    """The banner text for a Median name. Median's names carry their own article ("The Secret Cow Level"), so none is added."""
    name = " ".join(name.split())
    return name if name.lower().startswith(PHRASE_STARTS) else f"Entering {name}"


class Texts:
    """What the player reads for a levels.txt cell: `mxl2012:<key>` from the mod's namespace files, a bare key from the mod's
    `d2r:` override, else D2R's strings/ record (not the Chinese overlay)."""

    def __init__(self, own: dict, overrides: dict, d2r: dict):
        self.own, self.overrides, self.d2r = own, overrides, d2r

    @classmethod
    def load(cls, mod: Path, d2r_lng: Path) -> "Texts":
        ns = mod / "data" / "local" / "lng" / "strings" / NAMESPACE
        own, overrides, d2r = {}, {}, {}
        for p in sorted(ns.glob("*.json")):
            for e in json.loads(p.read_text("utf-8-sig")):
                if p.name == "overrides.json":
                    overrides[e["Key"][len(D2R_PREFIX):]] = e
                else:
                    own[e["Key"]] = e
        files = sorted((d2r_lng / "strings").glob("*.json"), key=lambda p: (p.name in OVERLAY_FILES, p.name))
        for p in files:
            for e in json.loads(p.read_text("utf-8-sig")):
                d2r.setdefault(e["Key"], e)
        return cls(own, overrides, d2r)

    def record(self, cell: str) -> dict | None:
        if cell.startswith(PREFIX):
            return self.own.get(cell[len(PREFIX):])
        return self.overrides.get(cell) or self.d2r.get(cell)

    def text(self, cell: str, lang: str = "enUS") -> str | None:
        r = self.record(cell.strip()) if cell.strip() else None
        return None if r is None else r.get(lang, "")


def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))
    return rows[0], rows[1:]


def levels(excel: Path):
    """(bank, Id, LevelName cell, LevelEntry cell) of every named level of both banks (rotw = data/global/excel, base)."""
    for bank in ("", "base"):
        p = (excel / bank if bank else excel) / "levels.txt"
        if not p.exists():
            continue
        h, rows = read_tsv(p)
        ii, ni, ei = h.index("Id"), h.index("LevelName"), h.index("LevelEntry")
        for r in rows:
            if len(r) > max(ii, ni, ei) and r[ni].strip():
                yield bank or "rotw", r[ii], r[ni], r[ei]


def survey(rows, texts: Texts) -> list[dict]:
    """One entry per level: its name, banner and whether the banner reads the name."""
    out = []
    for bank, lid, name_cell, entry_cell in rows:
        name, banner = texts.text(name_cell), texts.text(entry_cell)
        out.append({"bank": bank, "id": lid, "name_key": name_cell, "name": name, "entry_key": entry_cell,
                    "banner": banner, "ok": bool(name) and banner_reads(name, banner or "")})
    return out


def plan(entries: list[dict]) -> tuple[dict[str, str], list[str]]:
    """(LevelEntry key -> new banner text, problems). Only bare (D2R) keys can take a `d2r:` override; a key two levels share
    must give both the same banner."""
    want: dict[str, str] = {}
    problems = []
    by_key: dict[str, set[str]] = {}
    for e in entries:
        if e["name"]:
            by_key.setdefault(e["entry_key"], set()).add(e["name"])
    for e in entries:
        if e["ok"] or not e["name"]:
            continue
        key = e["entry_key"].strip()
        where = f"{e['bank']} level {e['id']} ({e['name']!r})"
        if not key or key.startswith(PREFIX):
            problems.append(f"{where}: LevelEntry {key!r} is not a D2R key, no override can reach it")
            continue
        if len(by_key[e["entry_key"]]) > 1:
            problems.append(f"{where}: LevelEntry {key!r} is shared by levels named {sorted(by_key[e['entry_key']])}")
            continue
        want[key] = banner_for(e["name"])
    return want, problems


def records(want: dict[str, str], langs: list[str]) -> list[dict]:
    return [{"Key": D2R_PREFIX + k, **{lang: v for lang in langs}} for k, v in sorted(want.items())]


def report(entries: list[dict]) -> str:
    lines = ["bank\tId\tLevelName\tname\tLevelEntry\tbanner\tstate"]
    for e in entries:
        lines.append("\t".join([e["bank"], e["id"], e["name_key"], e["name"] or "(no text)", e["entry_key"],
                                e["banner"] if e["banner"] is not None else "(no text)", "ok" if e["ok"] else "WRONG"]))
    return "\n".join(lines) + "\n"


def check(mod: Path, d2r_lng: Path, out=None) -> list[dict]:
    entries = survey(levels(mod / "data" / "global" / "excel"), Texts.load(mod, d2r_lng))
    if out:
        Path(out).write_text(report(entries), encoding="utf-8")
    return entries


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=("apply", "check"))
    ap.add_argument("--mod", type=Path, default=ROOT / "work" / "mod")
    ap.add_argument("--d2r-lng", type=Path, default=None)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args(argv)
    if a.d2r_lng is None:
        import fxpaths
        a.d2r_lng = Path(fxpaths.D2R) / "data" / "local" / "lng"
    strings_dir = a.mod / "data" / "local" / "lng" / "strings" / NAMESPACE
    entries = check(a.mod, a.d2r_lng)
    if a.cmd == "apply":
        want, problems = plan(entries)
        for p in problems:
            print("PROBLEM " + p)
        langs = [k for k in json.loads((strings_dir / "overrides.json").read_text("utf-8-sig"))[0] if k != "Key"]
        (strings_dir / OUT_FILE).write_text(json.dumps(records(want, langs), ensure_ascii=False, indent=2), encoding="utf-8")
        added, replaced, _ = merge_string_overrides.merge(strings_dir, [OUT_FILE], a.mod / "string_extras")
        print(f"level_entries: {len(want)} banners renamed to the level's Median name ({added} added, {replaced} replaced "
              f"in overrides.json)")
        entries = check(a.mod, a.d2r_lng)
        if problems:
            return 1
    wrong = [e for e in entries if not e["ok"]]
    if a.report:
        a.report.write_text(report(entries), encoding="utf-8")
    for e in wrong:
        print(f"WRONG {e['bank']} level {e['id']}: name {e['name']!r} ({e['name_key']}), banner {e['banner']!r} "
              f"({e['entry_key']})")
    print(f"level_entries check: {len(entries)} named levels, {len(wrong)} whose 'Entering' banner does not read the name")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
