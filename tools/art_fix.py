"""Missile and overlay art that exists nowhere: point every such row at the closest art that does exist.

Median's missiles.txt CelFile and overlay.txt Filename name 12 missile and 12 overlay animations that are neither in D2R
nor in Median's own files (some are Median typos of D2R names, some are vanilla's dead rows: nul, gore20, pentacle).
Classic mode (G) crashes or draws nothing when such a row spawns, and the HD effect maps (tools/missile_hd.py by
CelFile, tools/effects_hd.py per row) cannot give a row without art a stand-in. So after txt_migrate.py:

  1. general repairs: a stray ".dcc" / ".dc6" in the name is dropped when the file without it exists (Median writes
     "extra\\firesmoke.dcc"; the engine adds the extension itself), and the "|" Median's table conversion left in
     place of the path separator ("expansion|baaldeathghostie01") becomes "\\";
  2. REDIRECT: what is still missing is read from this table (lowercase name -> existing file, D2R's or Median's),
     chosen by element / shape words, colour and size of the row (docs/hd-effects.md section 7);
  3. anything left is reported and fails validate.py ("art": missing animation).

The new CelFile / Filename is a D2R file wherever one fits, so missile_hd.py and effects_hd.py (which run next) find the
exact HD model of that D2R row. Median-only art (blackpentacle) goes through effects_hd.py's closest-effect scoring.

Writes work/mod/data/global/excel/{base,}/missiles.txt and overlay.txt (in place), work/mod/art_fix.md (report).
Usage: python tools/art_fix.py [--check]   (--check: only list what is missing, change nothing)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from txt_migrate import read_tsv, write_tsv  # noqa: E402
import fxpaths  # noqa: E402  (where the D2R baseline and Median's files are: env, repo or the read-only sources)

ROOT = fxpaths.ROOT
D2R = fxpaths.D2R
MXL = fxpaths.MXL
OUT = ROOT / "work" / "mod"
EXCEL = OUT / "data" / "global" / "excel"
# table -> (art column, art folder under data/global)
TABLES = {"missiles": ("CelFile", "missiles"), "overlay": ("Filename", "overlays")}

# Lowercase name as written in the table -> existing art (without extension, backslashes as D2R's own tables).
# Missile art: data/global/missiles; overlay art: data/global/overlays.
REDIRECT = {
    "missiles": {
        "poisonspark": "poisonsparks",                                   # D2R's file is plural
        "expansion\\baaldeathghostie01": "expansion\\baaldeathghostie01",  # (the "|" repair, kept for the report)
        "greenflare": "fireball",                                        # searing_orb_missile: orange orb, 16 directions
        "teethexplodeyellow": "teethexplode",
        "dopplezonexplodex": "dopplezonexplode",
        "extra\\spikefiendmamamissile": "extra\\spikefiendmamamissle",   # D2R's own spelling
        "extra\\icestormimpactvar3": "extra\\icestormimpactvar03",
        "kabraxis_horadric": "horadriclightbeamstreaks",                 # blue looping beam, 1 direction
        "chainlightning": "lightningbolt",                               # miasmachains, binddemonchannel (rotw bank only)
        "mageblizzard": "blizzard",
        "scosblizzard": "blizzard",
        "nul": "null",                                                   # vanilla's dead row; D2R draws nothing for null
        # Median XL 2012 v005 rows (lane boot):
        "xxxxx": "null",                                                 # whyaretherealways: placeholder name, dead row
        "cherub": "yellowballglow2",                                     # cherubcenter: yellow light, 1 direction
        "lazbloodmissile": "bloodlarge01",                               # twinklesmash: red blood splash
        "andarielflamedeath2": "andarielflamedeath",                     # nephalemweapons: D2R has the first variant only
    },
    "overlay": {
        "dopplezonexplodeblue": "dopplezonappear",
        "dopplezonexplodelilac": "dopplezonappear",
        "extra\\auraresistcoldcast": "auraresistcoldcast",
        "pentacle": "blackpentacle",                                     # Median's own file
        "extra\\genericsplash": "extra\\generic_splash",
        "ceilingchunkvanish01": "expansion\\seigebeast_dust",            # D2R has the chunk as a missile, not an overlay
        "lazblood": "bloodripple",
        "whiteblinding": "extra\\whiteflash",
        "threeflames": "firecast_for_sorceress",
        "gore20": "bloodripple",                                         # vanilla's dead row
        "zombiesparx": "extra\\goohit",
        "spoverlray2": "holyshockhit",
    },
}

_filelist: set[str] | None = None


def d2r_files() -> set[str]:
    global _filelist
    if _filelist is None:
        p = fxpaths.D2R_FILELIST  # the extraction's (or gfx_placeholders.py's cached) list of D2R's CASC data names
        _filelist = set(p.read_text("utf-8").splitlines()) if p.exists() else set()
    return _filelist


def norm(name: str) -> str:
    return name.replace("/", "\\").lower()


def art_exists(table: str, name: str) -> str | None:
    """'d2r' or 'mxl' when the animation named in the table is a .dcc / .dc6 in D2R's data or Median's files."""
    folder = TABLES[table][1]
    rel = name.replace("\\", "/").lower()
    for ext in ("dcc", "dc6"):
        if f"data:data/global/{folder}/{rel}.{ext}" in d2r_files():
            return "d2r"
        if (MXL / folder / f"{rel}.{ext}").exists():
            return "mxl"
    return None


def resolve(table: str, name: str) -> tuple[str, str]:
    """(new name, how): 'ok' already exists, 'repaired' by the general rules, 'redirected', 'missing'."""
    if not name or art_exists(table, name):
        return name, "ok"
    fixed = name.replace("|", "\\")
    for ext in (".dcc", ".dc6"):
        if fixed.lower().endswith(ext):
            fixed = fixed[:-len(ext)]
    if fixed != name and art_exists(table, fixed):
        return fixed, "repaired"
    target = REDIRECT[table].get(norm(fixed))
    if target and art_exists(table, target):
        return target, "redirected"
    return name, "missing"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only list the missing art")
    args = ap.parse_args()
    if not d2r_files():
        print(f"{fxpaths.D2R_FILELIST} is missing (set MXL_D2R_EXTRACT to an extraction with filelist.txt, "
              "or run gfx_placeholders.py once with MXL_SLOT)")
        return 1
    report = ["# Missing missile / overlay art", "",
              "| Table | Row | Was | Now | How |", "|---|---|---|---|---|"]
    missing = changed = 0
    for bank in ("base", ""):
        for table, (col, _folder) in TABLES.items():
            p = EXCEL / bank / f"{table}.txt"
            if not p.exists():
                continue
            h, rows = read_tsv(p)
            c = h.index(col)
            for r in rows:
                if not r or not r[0]:
                    continue
                new, how = resolve(table, r[c])
                if how == "missing":
                    missing += 1
                    report.append(f"| {table} | {r[0]} | `{r[c]}` | | **missing, no redirect** |")
                elif how != "ok":
                    if bank == "base":
                        report.append(f"| {table} | {r[0]} | `{r[c]}` | `{new}` | {how} |")
                    changed += 1
                    r[c] = new
            if not args.check:
                write_tsv(p, h, rows)
    if args.check:
        print("\n".join(report))
    else:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "art_fix.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"art_fix: {changed} rows re-pointed (both banks), {missing} left without art")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
