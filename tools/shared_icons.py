"""The shared skill icon sheet (Spells\\SubMenu\\Skillicon, `skillicon.dc6`) rebuilt in pairs, and the skilldesc cels that point at it.

Median XL 2012's shared sheet holds one frame per icon (25 frames), but the game draws IconCel as the button and IconCel + 1
as the pressed button, so a class-less skill showed the *next* icon while pressed. And 74 class-less skills name a cel past
the sheet: their skilldesc row is the one of a class skill (`moonqueen`: Amazon's cel 60, so `Item Moon Queen` read frame
60 of the 25-frame sheet) or a de-classed vanilla row (`fire wall`, cel 30 of the vanilla Sorceress sheet).

This tool gives every class-less skill the picture that belongs to it, in a sheet of pairs (icon, pressed icon = the same
picture, as Median's own class sheets store their pressed frames):

  1. the row is also a class skill's (Item Moon Queen, Item Balance, Item Wings of W ...): that class sheet's frame
     (Median's sheet; the Warlock's is D2R's), and the class-less users get a copy of the row, `<row>~shared`, with the new
     cel and no tree slot (the class skill keeps its row, cel and tree slot);
  2. a row of the mod with a cel on the shared sheet: that frame (the 1.13c picture, unchanged);
  3. a row D2R has too (a de-classed vanilla skill: Fire Wall, Teleport) or a row only D2R has (D2R's own class-less
     skills, which name D2R's sheets): D2R's frame (D2R's charclass of the row picks the sheet, D2R's IconCel the frame);
  4. otherwise unresolved: the mod's "?" icon (frame 0).

A skill the player sees (tree / start / bar skills, tools/skill_icons.py tiers) whose row would show the "?" (Median's own
cel 0, or unresolved) gets the closest existing icon named in tools/data/item_skill_icons.tsv instead (lane procicons: the
charges and oskills of Median's items): a D2R class skill's frame, a Median class skill's frame or a Median shared frame.

Only skills the player can see get a picture of their own. Item procs and monster skills keep theirs when it is on the
sheet anyway, else the "?" pair: the sheet then holds 58 icons in 116 frames instead of about 130 icons (260 frames, more
than D2R's 16384-pixel strip holds at 132 px; MAX_FRAMES).

  py -3 -I tools/shared_icons.py tables [--excel DIR]   plan + rewrite skilldesc.txt / skills.txt of both banks of the
                                                         built tables (default work/mod/data/global/excel), plan ->
                                                         work/mod/shared_icons.json (a second run on the rewritten tables
                                                         keeps the plan: the file hashes say so)
  py -3 -I tools/shared_icons.py plan                    print the plan only

The sheets themselves are written by tools/skill_icons.py (HD sprite + lowend) and by sheet_dc6() here (the classic
DC6, which tools/legacy_art.py ships instead of Median's). docs/hd-icons.md, "Shared sheet in pairs".
"""
import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402
import idmap  # noqa: E402
import dc6  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BUILT_EXCEL = ROOT / "work" / "mod" / "data" / "global" / "excel"
PLAN = ROOT / "work" / "mod" / "shared_icons.json"
CLASSIC_OUT = ROOT / "work" / "mod" / "shared_icons" / "skillicon.dc6"
BANKS = ("", "base")
SUFFIX = "~shared"
VISIBLE_TIERS = (0, 1, 2)  # skill_icons TREE, START, BAR
# charclass -> (classic sheet, D2R HD sprite below data/hd/global/ui/spells/); "" is the shared sheet
SHEETS = {
    "ama": ("amskillicon", "amazon/amskillicon"), "sor": ("soskillicon", "sorceress/soskillicon"),
    "nec": ("neskillicon", "necromancer/neskillicon"), "pal": ("paskillicon", "paladin/paskillicon"),
    "bar": ("baskillicon", "barbarian/baskillicon"), "dru": ("drskillicon", "druid/drskillicon"),
    "ass": ("asskillicon", "assassin/asskillicon"), "war": ("waskillicon", "warlock/waskillicon"),
    "": ("skillicon", "submenu/skillicon"),
}
MEDIAN_CLASSES = ("ama", "sor", "nec", "pal", "bar", "dru", "ass")  # the sheets Median ships; the Warlock's is D2R's
DONORS = ROOT / "tools" / "data" / "item_skill_icons.tsv"
NO_CLASSIC_ART = {"war"}   # D2R's classic waskillicon.dc6 holds the Druid's pictures: no donor (HD and classic would differ)
MAX_FRAMES = 16384 // 132  # D2R's strip limit at the 132-pixel stride (skill_icons.strip_geometry); more would shrink the icons
RENAMED = "_mxl"           # txt_migrate's suffix of a Median skill / row D2R also has (Apocalypse -> Apocalypse_mxl)


@dataclass(frozen=True, order=True)
class Icon:
    origin: str   # "mxl" (Median's sheet) | "d2r" (D2R's sheet)
    sheet: str    # charclass key of SHEETS
    cel: int


@dataclass
class Plan:
    icons: list = field(default_factory=list)          # [Icon]; icon i is frames 2i and 2i + 1
    rows: dict = field(default_factory=dict)           # skilldesc row -> {"icon": i, "method": .., "split": bool}
    skills: dict = field(default_factory=dict)         # class-less skill -> {"row": new row, "cel": .., "method": .., "tier": ..}
    hashes: dict = field(default_factory=dict)         # bank -> {table: sha1 of the rewritten file}

    def cel_of(self, row: str) -> int:
        return 2 * self.rows[row]["icon"]

    def to_json(self) -> dict:
        return {"icons": [asdict(i) for i in self.icons], "rows": self.rows, "skills": self.skills, "hashes": self.hashes}

    @classmethod
    def from_json(cls, d: dict) -> "Plan":
        return cls([Icon(**i) for i in d["icons"]], d["rows"], d["skills"], d.get("hashes", {}))


def _col(head, name):
    i = idmap.col(head, name)
    if i is None:
        raise ValueError(f"no column {name}")
    return i


def _cel(v: str) -> int | None:
    v = v.strip()
    return int(v) if v.lstrip("-").isdigit() else None


def source_of(row: str, cel: int | None, median_rows: dict, median_shared: int,
              d2r_rows: dict) -> tuple[Icon | None, str]:
    """(icon, method) for the class-less users of one skilldesc row (module text, rules 1-4). median_rows: Median's
    skilldesc row -> the charclasses of Median's skills on it (the source tables: the built ones also have D2R's
    Warlock skills and the hidden class skills txt_migrate points at `attack`, which do not make a row a class row)."""
    if cel is None:
        return None, "no IconCel"
    median = median_rows.get(row, median_rows.get(row.removesuffix("_mxl")))
    if median:
        cls = sorted(median)[0]
        return Icon("mxl" if cls in MEDIAN_CLASSES else "d2r", cls, cel), "class row"
    if median is not None and 0 <= cel < median_shared:
        return Icon("mxl", "", cel), "shared sheet"
    if row in d2r_rows:
        cls, d2r_cel, frames = d2r_rows[row]
        if d2r_cel is not None and 0 <= d2r_cel < frames:
            return Icon("d2r", cls, d2r_cel), "D2R row" if median is None else "vanilla row"
    if median is None and 0 <= cel < median_shared:
        return Icon("mxl", "", cel), "shared sheet"
    return None, "unresolved"


def _median(d: dict, key: str, default=None):
    """d[key] for a key of the built tables, also when txt_migrate renamed it (`<key>_mxl`)."""
    return d.get(key, d.get(key.removesuffix(RENAMED), default))


def make_plan(banks: dict, median_rows: dict, median_shared: int, d2r_rows: dict, tiers: dict,
              donors: dict | None = None) -> Plan:
    """banks: bank -> (skilldesc header, rows, skills header, rows) of the built tables; median_rows: Median's skilldesc
    row -> charclasses of Median's skills on it; d2r_rows: D2R skilldesc row -> (D2R charclass of its skills, IconCel, frames of that sheet);
    tiers: skill name -> skill_icons tier (missing = monster); donors: Median's skilldesc row -> (Icon, donor text), the
    closest icon for a visible row that would show the "?" (donor_icons)."""
    users, class_users, cels = defaultdict(set), defaultdict(set), {}
    for dh, drows, sh, srows in banks.values():
        ic = _col(dh, "IconCel")
        for r in drows:
            if idmap.is_record(r) and not r[0].endswith(SUFFIX):
                cels.setdefault(r[0], _cel(r[ic]))
        cc, sd = _col(sh, "charclass"), _col(sh, "skilldesc")
        for r in srows:
            if not idmap.is_record(r) or not r[sd]:
                continue
            if r[cc]:
                class_users[r[sd]].add(r[cc])
            else:
                users[r[sd]].add(r[0])
    plan = Plan()
    donors = donors or {}
    fallback = Icon("mxl", "", 0)
    wanted = {}  # row -> (icon or None, method, visible)
    for row, names in users.items():
        if row not in cels:
            continue  # no such row: nothing to rewrite (the check reports it)
        icon, method = source_of(row, cels[row], median_rows, median_shared, d2r_rows)
        visible = any(_median(tiers, n, 4) in VISIBLE_TIERS for n in names)
        donor = _median(donors, row)
        if visible and donor and method != "no IconCel" and icon in (None, fallback):
            icon, method = donor[0], f"closest icon ({donor[1]})"
        wanted[row] = (icon, method, visible)
    chosen = {i for i, _m, v in wanted.values() if i and v} | {fallback}
    if 2 * len(chosen) > MAX_FRAMES:
        raise ValueError(f"shared sheet: {len(chosen)} icons need {2 * len(chosen)} frames, the strip holds {MAX_FRAMES} at "
                         f"full size: let more skills share a donor in {DONORS.name}")
    # Median's shared frames first in their order, then the class / D2R frames
    plan.icons = sorted(chosen, key=lambda i: (i.origin != "mxl" or i.sheet != "", i))
    index = {i: n for n, i in enumerate(plan.icons)}
    for row in sorted(wanted):
        icon, method, visible = wanted[row]
        if icon is None:
            if method == "no IconCel":
                continue  # a row without a picture on purpose (mxl_blank): left as it is
            icon, method = fallback, "unresolved: ?"
        elif icon not in index:
            icon, method = fallback, method + ", not visible: ?"
        plan.rows[row] = {"icon": index[icon], "method": method, "split": bool(class_users[row]), "visible": visible}
        new_row = row + SUFFIX if class_users[row] else row
        for n in sorted(users[row]):
            plan.skills[n] = {"row": new_row, "cel": plan.cel_of(row), "method": method, "tier": _median(tiers, n, 4)}
    return plan


def apply(plan: Plan, dh: list, drows: list, sh: list, srows: list) -> tuple[list, list, Counter]:
    """The plan on one bank's tables (in place, returned): IconCel of the class-less rows, `~shared` copies of the class rows
    with no tree slot, skills.txt `skilldesc` of their class-less users. Setting absolute values, so a second run changes nothing."""
    ic, pg, ro, co = (_col(dh, c) for c in ("IconCel", "SkillPage", "SkillRow", "SkillColumn"))
    cc, sd = _col(sh, "charclass"), _col(sh, "skilldesc")
    n = Counter()
    by_name = {r[0]: r for r in drows if idmap.is_record(r)}
    for row, p in plan.rows.items():
        if row not in by_name:
            continue
        cel = str(plan.cel_of(row))
        if p["split"]:
            copy = by_name.get(row + SUFFIX)
            if copy is None:
                copy = list(by_name[row])
                copy[0] = row + SUFFIX
                drows.append(copy)
                by_name[copy[0]] = copy
                n["rows copied"] += 1
            copy[ic], copy[pg], copy[ro], copy[co] = cel, "0", "0", "0"
        elif by_name[row][ic] != cel:
            by_name[row][ic] = cel
            n["IconCel rewritten"] += 1
    for r in srows:
        if idmap.is_record(r) and not r[cc] and r[sd] in plan.rows and plan.rows[r[sd]]["split"]:
            r[sd] += SUFFIX
            n["skills moved to a copy"] += 1
    return drows, srows, n


# ---- inputs ---------------------------------------------------------------------------------------------------------
def read_donors(path: Path = DONORS) -> dict:
    """tools/data/item_skill_icons.tsv: Median's skilldesc row -> (donor, reason); '#' lines are comments."""
    out = {}
    if not Path(path).exists():
        return out
    for line in Path(path).read_text("utf-8").splitlines():
        f = line.split("\t")
        if line.startswith("#") or not line.strip() or f[0] == "skilldesc":
            continue
        if len(f) != 4 or f[0] in out:
            raise ValueError(f"{Path(path).name}: bad or repeated line {line!r}")
        out[f[0]] = (f[1], f[3])
    return out


def donor_icon(donor: str, median_rows: dict, median_cels: dict, median_shared: int, d2r_rows: dict) -> Icon:
    """The icon a donor names: `d2r:<D2R skilldesc row>` (D2R's frame, on the sheet of the row's class), `mxl:<row>` (the
    frame of a Median class skill's row), `shared:<cel>` (a frame of Median's shared sheet)."""
    origin, _, name = donor.partition(":")
    if origin == "shared":
        cel = _cel(name)
        if cel is not None and 0 < cel < median_shared:
            return Icon("mxl", "", cel)
    elif origin == "mxl":
        cls = sorted(median_rows.get(name) or {""})[0]
        if cls in MEDIAN_CLASSES and median_cels.get(name) is not None:
            return Icon("mxl", cls, median_cels[name])
    elif origin == "d2r" and name in d2r_rows:
        cls, cel, frames = d2r_rows[name]
        if cls and cls not in NO_CLASSIC_ART and cel is not None and 0 <= cel < frames:
            return Icon("d2r", cls, cel)
    raise ValueError(f"icon donor {donor!r}: no such frame (d2r: a D2R class skill's row, mxl: a Median class skill's "
                     f"row, shared: frame 1-{median_shared - 1} of Median's shared sheet)")


def donor_icons(table: dict, median_rows: dict, median_cels: dict, median_shared: int, d2r_rows: dict) -> dict:
    """read_donors() -> {row: (Icon, donor)} for make_plan."""
    return {row: (donor_icon(d, median_rows, median_cels, median_shared, d2r_rows), d) for row, (d, _why) in table.items()}


def _sha(p: Path) -> str:
    return hashlib.sha1(p.read_bytes()).hexdigest()


def d2r_rows(d2r: Path) -> dict:
    """D2R skilldesc row -> (charclass of D2R's skills on it, IconCel, frames of that sheet)."""
    ex = d2r / "data" / "global" / "excel"
    dh, drows = idmap.read_tsv(ex / "skilldesc.txt")
    sh, srows = idmap.read_tsv(ex / "skills.txt")
    cls = defaultdict(str)
    for r in srows:
        if r[_col(sh, "skilldesc")] and r[_col(sh, "charclass")]:
            cls.setdefault(r[_col(sh, "skilldesc")], r[_col(sh, "charclass")])
    frames = {}
    for c, (name, _t) in SHEETS.items():
        p = d2r / "data" / "global" / "ui" / "spells" / f"{name}.dc6"
        frames[c] = len(dc6.read_dc6(p)) if p.exists() else 0
    ic = _col(dh, "IconCel")
    return {r[0]: (cls[r[0]] if cls[r[0]] in SHEETS else "", _cel(r[ic]), frames[cls[r[0]] if cls[r[0]] in SHEETS else ""])
            for r in drows if idmap.is_record(r)}


def median_inputs() -> tuple[dict, int, dict, dict]:
    """Median's skilldesc rows (-> charclasses of Median's skills on them), the frames of its shared sheet, tiers by skill
    name (tools/skill_icons.py), IconCel by skilldesc row."""
    import skill_icons
    from icon_paths import EXCEL, read_tsv
    dh, rows = read_tsv(EXCEL / "skilldesc.txt")
    sh, srows = read_tsv(EXCEL / "skills.txt")
    out = {r[0]: set() for r in rows}
    cc, sd = _col(sh, "charclass"), _col(sh, "skilldesc")
    for r in srows:
        if r[sd] in out and r[cc]:
            out[r[sd]].add(r[cc])
    shared = len(dc6.read_dc6(skill_icons.SPELLS / "skillicon.dc6"))
    tiers = {s["name"]: s["tier"] for s in skill_icons.load_skills()}
    ic = _col(dh, "IconCel")
    return out, shared, tiers, {r[0]: _cel(r[ic]) for r in rows}


def load_banks(excel: Path) -> dict:
    out = {}
    for b in BANKS:
        d, s = excel / b / "skilldesc.txt", excel / b / "skills.txt"
        if d.exists() and s.exists():
            out[b] = (*idmap.read_tsv(d), *idmap.read_tsv(s))
    return out


def load_plan(path: Path = PLAN) -> Plan | None:
    return Plan.from_json(json.loads(path.read_text("utf-8"))) if Path(path).exists() else None


def inputs(excel: Path, d2r: Path, donors_path: Path = DONORS) -> tuple:
    """make_plan's arguments for the built tables."""
    median_rows, shared, tiers, cels = median_inputs()
    d2r_r = d2r_rows(d2r)
    donors = donor_icons(read_donors(donors_path), median_rows, cels, shared, d2r_r)
    return load_banks(excel), median_rows, shared, d2r_r, tiers, donors


def tables(excel: Path = BUILT_EXCEL, plan_path: Path = PLAN, d2r: Path = fxpaths.D2R, donors_path: Path = DONORS) -> Plan:
    old = load_plan(plan_path)
    donor_sha = {donors_path.name: _sha(donors_path)} if donors_path.exists() else {}
    if old and old.hashes and old.hashes.get("donors", {}) == donor_sha and all(
            (excel / b / t).exists() and _sha(excel / b / t) == h
            for b, hs in old.hashes.items() if b in BANKS for t, h in hs.items()):
        print("shared icons: the tables are already rewritten by this plan; nothing to do")
        return old
    banks, *rest = inputs(excel, d2r, donors_path)
    plan = make_plan(banks, *rest)
    for b, (dh, drows, sh, srows) in banks.items():
        _d, _s, n = apply(plan, dh, drows, sh, srows)
        from txt_migrate import write_tsv
        write_tsv(excel / b / "skilldesc.txt", dh, drows)
        write_tsv(excel / b / "skills.txt", sh, srows)
        plan.hashes[b] = {"skilldesc.txt": _sha(excel / b / "skilldesc.txt"), "skills.txt": _sha(excel / b / "skills.txt")}
        print(f"  bank {b or 'rotw'}: " + ", ".join(f"{k} {v}" for k, v in sorted(n.items())))
    plan.hashes["donors"] = donor_sha
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan.to_json(), indent=1), "utf-8")
    return plan


# ---- the sheet itself -----------------------------------------------------------------------------------------------
def frame_sources(plan: Plan, median_spells: Path, d2r: Path) -> list[tuple[Icon, Path]]:
    """(icon, classic DC6 it comes from) per icon."""
    out = []
    for i in plan.icons:
        name = SHEETS[i.sheet][0]
        out.append((i, (median_spells if i.origin == "mxl" else d2r / "data" / "global" / "ui" / "spells") / f"{name}.dc6"))
    return out


def classic_frames(plan: Plan, median_spells: Path, d2r: Path) -> list[tuple[int, int, int, int, bytes]]:
    """The DC6 frames of the paired sheet: every icon twice, the bytes of its source frame."""
    cache, out = {}, []
    for icon, path in frame_sources(plan, median_spells, d2r):
        if path not in cache:
            cache[path] = dc6.read_dc6(path)
        out += [cache[path][icon.cel]] * 2
    return out


def sheet_dc6(plan: Plan, median_spells: Path, d2r: Path, out: Path = CLASSIC_OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(dc6.build_dc6(classic_frames(plan, median_spells, d2r)))
    return out


def unused_donors(plan: Plan, table: dict) -> list[str]:
    """Rows of the donor table the plan did not need (stale lines)."""
    used = {r.removesuffix(RENAMED) for r, p in plan.rows.items() if p["method"].startswith("closest icon")}
    return sorted(set(table) - used)


def summary(plan: Plan) -> str:
    m = Counter(s["method"].partition(" (")[0] for s in plan.skills.values())   # "closest icon (<donor>)" counted as one
    vis = Counter(s["method"].partition(" (")[0] for s in plan.skills.values() if s["tier"] in VISIBLE_TIERS)
    split = sum(1 for r in plan.rows.values() if r["split"])
    lines = [f"shared icons: {len(plan.icons)} icons -> {2 * len(plan.icons)} frames; {len(plan.rows)} class-less skilldesc rows "
             f"({split} split into {SUFFIX} copies), {len(plan.skills)} class-less skills",
             "  all skills by source: " + ", ".join(f"{k} {v}" for k, v in sorted(m.items())),
             "  player-visible (tree/start/bar): " + ", ".join(f"{k} {v}" for k, v in sorted(vis.items()))]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["tables", "plan"])
    ap.add_argument("--excel", type=Path, default=BUILT_EXCEL)
    ap.add_argument("--d2r", type=Path, default=fxpaths.D2R)
    args = ap.parse_args(argv)
    if args.cmd == "plan":
        plan = make_plan(*inputs(args.excel, args.d2r))
    else:
        plan = tables(args.excel, PLAN, args.d2r)
    print(summary(plan))
    bad = [n for n, s in plan.skills.items() if s["tier"] in VISIBLE_TIERS and s["method"].startswith("unresolved")]
    for n in bad:
        print(f"  visible skill without a picture of its own: {n}")
    for n in unused_donors(plan, read_donors()):
        print(f"  {DONORS.name}: row {n} is not used (it has a picture of its own, or no visible skill)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
