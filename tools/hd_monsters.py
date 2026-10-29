#!/usr/bin/env python
"""HD monster stand-ins for D2R-XL 2012: every monster art token of the mod's monstats -> a D2R HD unit.

Median XL 2012 (1.13c data) draws monsters from classic DCC/COF art; D2R's HD renderer needs a model per monster.
The token is the monstats `Code` (= the art folder `data/global/monsters/<token>/`). Each token is one of

  vanilla  D2R already has the art of the token (its cof set) and a unit for it: the unit of the same Id and code, else the
           best unit of that code (`vanilla_unit`);
  reused   the token's art set is also in the prior mapping (another port's decisions, read from the reference
           checkout): donor unit, scale and colour are reused (modal choice of the prior rows of the token, see `prior_entry`);
  new      Median 2012 art with no prior mapping: a hand-picked closest vanilla HD unit (tools/data/hd_monster_pins.json,
           candidates from `suggest`, which runs the donor scoring on the 2012 art);
  split    an own token (tools/own_tokens.py, Slayer e9 -> KS): Median's rows left a token D2R's art also uses; they take the
           vanilla rule of the token they came from, so the HD unit stays what it was;
  noart    the token has no art in the mod or in D2R: pinned to the unit of the monster it stands for (pins file); also a
           `borrow` own token (tools/own_tokens.py, the Haunts -> HN): D2R's classic art of the pinned unit under a token
           of its own, its missing modes filled;
  unused   art in the MPQ that no monstats row uses: listed, not mapped.

  py -3 -I tools/hd_monsters.py classify          token classes -> work/hd_monsters/classes.json (counts printed)
  py -3 -I tools/hd_monsters.py suggest [TOKEN..] donor ranking for the `new` tokens -> work/hd_monsters/suggest.md
  py -3 -I tools/hd_monsters.py map               tools/data/hd_monster_tokens.json (the committed mapping)
  py -3 -I tools/hd_monsters.py splits            the entries of the split tokens (and of their old tokens) in that file, only
  py -3 -I tools/hd_monsters.py repin TOKEN..     the entries of these tokens again from the pins (changed hand picks), only
  py -3 -I tools/hd_monsters.py recolour TOKEN..  only the colour of these entries again with the current rule (donor kept)
  py -3 -I tools/hd_monsters.py clips DIR         tools/data/d2r_unit_clips.json from extracted combined.animations
  py -3 -I tools/hd_monsters.py build             HD json -> work/hd_monsters/data/hd/character + report
  py -3 -I tools/hd_monsters.py doc               docs/hd-monsters.md

Read-only inputs (all outside git): the extracted 2012 MPQ, the D2R baseline extract and the reference checkout's work/
results (localconfig.reference_dir(): MXL_REFERENCE or machine.json reference_checkout). See docs/hd-monsters.md section 6.
"""
import argparse
import colorsys
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hd_donors as hd  # noqa: E402
import hd_units as hu  # noqa: E402
import fxpaths  # noqa: E402  (D2R baseline: MXL_D2R_EXTRACT, else the repo's or the reference extract)
import own_tokens  # noqa: E402  (split rows: Slayer e9 -> KS)

ROOT = Path(__file__).resolve().parent.parent
RUNS = fxpaths.RUNS   # R\mxl2012-runs (beside the main checkout, or above R\mxl2012-wt\<lane>)
REFERENCE = fxpaths.REFERENCE  # the reference checkout (read-only); None when this machine has none
TOKENS_JSON = ROOT / "tools" / "data" / "hd_monster_tokens.json"
PINS_JSON = ROOT / "tools" / "data" / "hd_monster_pins.json"
# D2R enemy animation folder -> the clip names its combined.animations holds (`clips`, read from a game slot's CASC once; names
# only). The build binds a mode whose clip a donor lacks to a clip it has (hd_units.clip_fill)
CLIPS_JSON = ROOT / "tools" / "data" / "d2r_unit_clips.json"

CONF_WEIGHT = {"high": 3.0, "medium": 2.0, "low": 1.0}


# ------------------------------------------------------------------ tables
def read_rows(path: Path) -> list[dict]:
    with open(path, encoding="latin-1", newline="") as f:
        rows = list(csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE))   # quotes stay in the cells
    head = rows[0]
    return [dict(zip(head, r)) for r in rows[1:]]


def monstats(excel: Path):
    """(monstats rows by Id, monstats2 rows by Id) without the 'Expansion' separators and blank lines."""
    ms = {r["Id"]: r for r in read_rows(excel / "monstats.txt") if r["Id"] and r["Id"] != "Expansion"}
    ms2 = {r["Id"]: r for r in read_rows(excel / "monstats2.txt") if r["Id"] and r["Id"] != "Expansion"}
    return ms, ms2


def d2r_filelist(d2r: Path) -> Path:
    return d2r / "filelist.txt" if (d2r / "filelist.txt").exists() else fxpaths.D2R_FILELIST


def d2r_files(d2r: Path) -> set[str]:
    """Every file of D2R's CASC as a lower-case path (`data/hd/...`), from the baseline's file list."""
    return {line.split(":", 1)[1].lower() for line in d2r_filelist(d2r).read_text("utf-8").splitlines() if ":" in line}


def load_clips(path: Path = CLIPS_JSON) -> dict[str, list[str]]:
    return json.loads(path.read_text("utf-8"))["folders"] if path.exists() else {}


def d2r_cofs(d2r: Path) -> set[str]:
    out = set()
    fl = d2r_filelist(d2r)
    for line in fl.read_text("utf-8").splitlines():
        m = re.search(r"data/global/monsters/[^/]+/cof/([^/]+)\.cof$", line)
        if m:
            out.add(m.group(1))
    return out


def missing_cofs(code: str, row2: dict, cofs: set[str]) -> list[str]:
    """COFs of the monster's modes (KB, SQ excepted) that D2R's own art lacks."""
    w = (row2.get("BaseW") or "hth").lower()
    return [f"{code}{m}{w}".lower() for m in hu.MODES if m not in ("KB", "SQ") and row2.get("m" + m) == "1"
            and f"{code}{m}{w}".lower() not in cofs and not (m in ("DT", "DD") and f"{code}{m}hth".lower() in cofs)]


# ------------------------------------------------------------------ paths
class Paths:
    """Everything the tool reads or writes; all inputs outside the repo are read-only."""

    def __init__(self, a):
        self.mod = Path(a.mod_global)                         # extracted 2012 MPQ: data/global
        d2r = getattr(a, "d2r", None)
        # no reference checkout: a path that does not exist, so a step that needs the prior mapping fails naming the fix
        ref = Path(a.reference) if a.reference else Path("no-reference-checkout (set MXL_REFERENCE or machine.json reference_checkout)")
        self.d2r = Path(d2r) if d2r else ref / "extract" / "d2r" / "93847"   # D2R 93847 baseline (tables, hd json, palette)
        self.s_mon = ref / "assets" / "median" / "data" / "global" / "monsters"   # the prior art sets
        self.s_work = ref / "work"
        self.s_report = self.s_work / "mod" / "hd_monsters.md"
        self.s_ms = self.s_work / "named" / "monstats.txt"
        self.s_hd = self.s_work / "mod" / "data" / "hd" / "character"
        self.s_cache = self.s_work / "hd_monsters_art.json"
        self.out = Path(a.work) / "hd_monsters"
        self.tokens = Path(a.tokens)
        self.pins = Path(a.pins)
        self.clips = Path(getattr(a, "clips", None) or CLIPS_JSON)

    def configure(self):
        hd.configure(self.mod / "monsters", self.d2r)


def file_index(root: Path) -> dict[str, Path]:
    """Lower-cased relative path -> file for every file under root (D2 is case-insensitive)."""
    if not root.exists():
        return {}
    return {p.relative_to(root).as_posix().lower(): p for p in root.rglob("*") if p.is_file()}


def tok_of(mid: str, code: str) -> str:
    """The token a monstats row draws in the build: its Code, but the own token of a split row (tools/own_tokens.py)."""
    return own_tokens.row_token(mid, code).lower()


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def art_compare(tok: str, mod_files: dict, sis_files: dict) -> dict:
    """How the token's art folder in the 2012 MPQ relates to the same folder of the prior set (the reference assets)."""
    a = {k for k in mod_files if k.split("/")[0] == tok}
    b = {k for k in sis_files if k.split("/")[0] == tok}
    if not a:
        return {"relation": "no mod folder", "mod_files": 0, "prior_files": len(b)}
    if not b:
        return {"relation": "no prior folder", "mod_files": len(a), "prior_files": 0}
    both = sorted(a & b)
    same = [k for k in both if md5(mod_files[k]) == md5(sis_files[k])]
    if len(a) == len(b) == len(same):
        rel = "identical"
    elif len(same) == len(a):
        rel = "identical, the prior set has extra files"   # every 2012 file is byte-identical to the prior set's
    else:
        rel = "differs"
    return {"relation": rel, "mod_files": len(a), "prior_files": len(b), "common": len(both), "identical_files": len(same),
            "only_mod": sorted(a - b), "only_prior": len(b - a),
            "differing": sorted(k for k in both if k not in set(same))}


# ------------------------------------------------------------------ prior results
def parse_prior_report(path: Path) -> list[dict]:
    """Rows of the prior work/mod/hd_monsters.md: prior Id, name, code, donor, scale, colour, confidence, why."""
    rows = []
    for line in path.read_text("utf-8").splitlines():
        if not line.startswith("| ") or line.startswith(("| Median", "| ---", "| Stats")):
            continue
        c = [x.strip() for x in line.strip().strip("|").split(" | ")]
        if len(c) == 8:
            rows.append(dict(zip(("id", "name", "code", "donor", "scale", "colour", "conf", "why"), c)))
    return rows


def prior_variant(paths: Paths, unit: str) -> tuple[list, list] | None:
    """(colorAdjustment, colorTint) of a unit the prior mapping built (entry 0 / transform 0 of its variant table)."""
    up = paths.s_hd / "enemy" / f"{unit}.json"
    if not up.exists():
        return None
    d = hu.load_json(up)
    for e in d["entities"]:
        for c in e["components"]:
            if c["type"] == "VariantDefinitionComponent":
                vp = paths.s_hd.parent.parent / c["filename"].removeprefix("data/")
                if vp.exists():
                    t = hu.load_json(vp)["entries"][0]["transforms"][0]
                    return [t["colorAdjustment"][k] for k in "xyzw"], [t["colorTint"][k] for k in "xyzw"]
    return None


def prior_vmap(paths: Paths, unit: str) -> list | None:
    """(Median part, Median variant, donor part, donor variant) rows the prior unit was built with. Only needed for
    provenance units: their entities are named entity_<tp>_<tv>_<dp>_<dv> (tools/hd_units.build_unit)."""
    up = paths.s_hd / "enemy" / f"{unit}.json"
    if not up.exists():
        return None
    out = []
    for e in hu.load_json(up)["entities"]:
        m = re.match(r"entity_([a-z0-9]+)_([A-Za-z0-9]+)_([a-z0-9]+)_([A-Za-z0-9]+)$", e["name"])
        if m:
            out.append(list(m.groups()))
    return out or None


def prior_entry(paths: Paths, rows: list[dict], prior_mj: dict[str, str]) -> dict | None:
    """The token's mapping from the prior rows of the same code: the donor with the most confidence-weighted rows
    (high 3, medium 2, low 1); scale, colour and part mapping from the first row of that donor with the most common
    scale and colour. Vanilla and `kept` rows (D2R art / graphics borrowed) carry no donor choice and are ignored."""
    cand = [r for r in rows if r["conf"] in CONF_WEIGHT and r["donor"]]
    if not cand:
        return None
    w = Counter()
    for r in cand:
        w[r["donor"]] += CONF_WEIGHT[r["conf"]]
    donor, dw = w.most_common(1)[0]
    mine = [r for r in cand if r["donor"] == donor]
    key = Counter((r["scale"], r["colour"]) for r in mine).most_common(1)[0][0]
    pick = next(r for r in mine if (r["scale"], r["colour"]) == key)
    var = prior_variant(paths, prior_mj.get(pick["id"], ""))
    prov = "provenance" in pick["why"]
    conf_rank = {"high": 3, "medium": 2, "low": 1}
    return {
        "donor": donor, "scale": float(pick["scale"]), "colour": pick["colour"],
        "adjust": var[0] if var else [0.0, 0.0, 0.0, 1.0], "tint": var[1] if var else [0.0, 0.0, 0.0, 0.0],
        "confidence": max((r["conf"] for r in mine), key=conf_rank.get) if len({r["conf"] for r in mine}) == 1 else
        Counter(r["conf"] for r in mine).most_common(1)[0][0],
        "prior_rows": len(cand), "agree": round(dw / sum(w.values()), 2),
        "alternatives": {d: len([r for r in cand if r["donor"] == d]) for d in w if d != donor},
        "prior_ids": [r["id"] for r in mine[:3]], "prior_why": pick["why"],
        "vmap": prior_vmap(paths, prior_mj.get(pick["id"], "")) if prov else None,
    }


def hist_overlap(a: list[int], b: list[int]) -> float:
    ta, tb = sum(a) or 1, sum(b) or 1
    return sum(min(x / ta, y / tb) for x, y in zip(a, b))


def prior_art_stats(paths: Paths, tok: str) -> list[dict]:
    """The reference checkout's cached NU-frame statistics of the prior art of a token (any part/variant signature)."""
    cache = json.loads(paths.s_cache.read_text("utf-8"))
    return [v for k, v in cache.items() if k.startswith(f"mxl|{tok}|") and v]


def art_similarity(paths: Paths, tok: str, row2: dict, cache: "hd.ArtCache") -> dict | None:
    """Size ratio and palette overlap between the 2012 art of a token and the cached prior art (best match)."""
    mine = cache.get("mxl", tok, row2)
    if not mine:
        return None
    best = None
    for st in prior_art_stats(paths, tok):
        h1, h2 = mine["box"][3] - mine["box"][1], st["box"][3] - st["box"][1]
        ov = hist_overlap(mine["hist"], st["hist"])
        r = {"height_ratio": round(h1 / h2, 2) if h2 else 0.0, "palette_overlap": round(ov, 2)}
        if best is None or ov > best["palette_overlap"]:
            best = r
    return best


# ------------------------------------------------------------------ classification
def load_all(paths: Paths):
    ms, ms2 = monstats(paths.mod / "excel")
    cofs = d2r_cofs(paths.d2r)
    mod_files = file_index(paths.mod / "monsters")
    mod_files.update(own_tokens.virtual_index())   # the renamed copies of the own tokens (their files exist only in the build)
    sis_files = file_index(paths.s_mon)
    return ms, ms2, cofs, mod_files, sis_files


def classify(paths: Paths) -> dict:
    ms, ms2, cofs, mod_files, sis_files = load_all(paths)
    mpq_tokens = {k.split("/")[0] for k in mod_files}
    by_tok: dict[str, list[str]] = defaultdict(list)
    for i, r in ms.items():
        by_tok[tok_of(i, r["Code"])].append(i)
    split_new = {e["new"].lower(): e["old"].lower() for e in own_tokens.splits()}
    borrow_new = {e["new"].lower() for e in own_tokens.borrows()}
    srows = defaultdict(list)
    for r in parse_prior_report(paths.s_report):
        srows[r["code"].lower()].append(r)
    out = {}
    for tok in sorted(set(by_tok) | mpq_tokens):
        ids = by_tok.get(tok, [])
        id_state = {}
        for i in ids:
            r2 = ms2.get(ms[i]["MonStatsEx"])
            id_state[i] = "nomonstats2" if r2 is None else "vanilla" if not missing_cofs(tok, r2, cofs) else "mod"
        states = set(id_state.values())
        cmp_ = art_compare(tok, mod_files, sis_files) if tok in mpq_tokens else {"relation": "no mod folder"}
        usable = [r for r in srows.get(tok, []) if r["conf"] in CONF_WEIGHT and r["donor"]]
        if not ids:
            cls = "unused"
        elif tok in split_new:
            cls = "split"   # D2R's art under the old token: the rows take the unit they took before the rename
        elif tok in borrow_new:
            cls = "noart"   # D2R's art of the pinned donor under an own token (copies): the donor's unit
        elif states == {"vanilla"}:
            cls = "vanilla"
        elif tok not in mpq_tokens:
            cls = "noart"
        elif "vanilla" in states:
            cls = "mixed"
        else:
            # the prior donor only fits when the art is the same art: at least half of the 2012 files are byte-identical
            # to the prior set's (`!1` is a different creature there, `!h` differs in one frame set)
            same_art = cmp_["relation"] != "no prior folder" and cmp_.get("identical_files", 0) * 2 >= cmp_["mod_files"]
            cls = "reused" if usable and same_art else "new"
        out[tok] = {"token": tok, "class": cls, "ids": ids, "id_state": id_state, "mod_folder": tok in mpq_tokens,
                    "art_vs_prior": cmp_, "prior_rows": len(usable)}
        if cls == "split":
            out[tok]["split_of"] = split_new[tok]
    return out


# ------------------------------------------------------------------ scoring on the 2012 art
FALLBACK_ROW2 = {"BaseW": "hth", "TR": "1", "TRv": "lit", "mDT": "1", "mNU": "1", "mWL": "1", "mGH": "1", "mA1": "1",
                 "mDD": "1"}


class Ctx:
    """D2R donors (units + classic-art statistics) and the 2012 tables; built on first use (needs the 2012 DCC decoder)."""

    def __init__(self, paths: Paths):
        paths.configure()
        self.paths = paths
        self.ms, self.ms2, self.cofs, self.mod_files, self.sis_files = load_all(paths)
        self.dms, self.dms2 = monstats(paths.d2r / "data" / "global" / "excel")
        self.mj = hu.load_json(paths.d2r / "data" / "hd" / "character" / "monsters.json")
        cache_path = paths.out / "art_cache.json"
        self.cache = hd.ArtCache(cache_path)
        # seed with the reference checkout's statistics of D2R's classic art (reading D2R's own art needs the game install,
        # which this project does not touch); its prior-set entries ("mxl|...") are not ours and are not taken
        for k, v in json.loads(paths.s_cache.read_text("utf-8")).items():
            if k.startswith("d2r|") and v and not self.cache.data.get(k):
                self.cache.data[k] = v
                self.cache.dirty = True
        self.art = hd.Art()
        self.donors = hd.build_donors(self.dms, self.dms2, {}, self.art, self.cache, self.mj)
        # a unit whose model D2R does not ship (eagle, quillbear1) would draw nothing: never a donor
        files = d2r_files(paths.d2r)
        self.no_model = sorted(u for u in self.donors if not hu.has_model(u, files))
        for u in self.no_model:
            del self.donors[u]
        # D2R unit by classic art code. All of D2R's units count here: a donor picker's by_code skips town folk, guards and
        # helpers (NOT_DONORS) because it picks donors from it, but a monster that draws a vanilla token wants the unit of
        # that very token
        self.by_code: dict[str, dict[str, str]] = defaultdict(dict)
        for i, r in self.dms.items():
            if r["Code"] and i in self.mj:
                self.by_code[r["Code"].lower()].setdefault(self.mj[i], i)

    def row2(self, mid: str) -> tuple[dict, bool]:
        r2 = self.ms2.get(self.ms[mid]["MonStatsEx"])
        return (r2, True) if r2 is not None else (FALLBACK_ROW2, False)

    def subject(self, mid: str, art: bool = True) -> "hd.Subject":
        r = self.ms[mid]
        r2, _ = self.row2(mid)
        tok = r["Code"].lower()
        col = None
        if art:
            col = hd.art_colour(self.art, "mxl", tok, self.cache.get("mxl", tok, r2), int(r["TransLvl"] or 0))
        return hd.Subject(mid, r, r2, hd.bare(r["NameStr"]), col)

    def save(self):
        self.cache.save()


def quantised_colour(sub: "hd.Subject", d: "hd.Donor") -> tuple[list, list, str]:
    """(colorAdjustment, colorTint, label) turning the donor's classic colour into the monster's (quantised)."""
    if not sub.col:
        return [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0], "none"
    adj, tint, label = hd.tint_of(sub.col, d.col)
    adj = [hd.q(adj[0], 0.02) % 1.0, hd.q(adj[1], 0.05), hd.q(adj[2], 0.05), 1.0]
    tint = [hd.q(t, 0.1) for t in tint[:3]] + [hd.q(tint[3], 0.05)]
    return adj, tint, label


def scale_of(ratio: float) -> float:
    sq = hd.q(max(0.5, min(2.5, ratio)), 0.05)
    return 1.0 if abs(sq - 1) < 0.06 else sq


def rescore_token(ctx: Ctx, tok: str, ids: list[str], only: set[str] | None = None, pinned: str | None = None) -> dict:
    """Donor scoring on the 2012 art, for every monster Id of the token: confidence-weighted modal donor (or the pinned
    donor), with its scale and colour. `only`: donor units to choose from (the prior ones, for a consensus check)."""
    votes: Counter = Counter()
    best: dict[str, tuple] = {}
    ranking: Counter = Counter()
    for mid in ids:
        s = ctx.subject(mid)
        if pinned:
            d = ctx.donors[pinned]
            sc, ratio, why = hd.score(s, d)
            conf = hd.confidence(s, d, sc, ratio, 0.0) if s.col else "low"
            res = (d, sc, ratio, why, 0.0)
        else:
            pool = ctx.donors if not only else {u: d for u, d in ctx.donors.items() if u in only}
            res = hd.choose(s, pool)
            d, sc, ratio, why, margin = res
            conf = hd.confidence(s, d, sc, ratio, margin) if s.col else "low"
            for u, dd in pool.items():
                ranking[u] += hd.score(s, dd)[0]
        votes[res[0].unit] += CONF_WEIGHT[conf]
        if res[0].unit not in best or CONF_WEIGHT[conf] > CONF_WEIGHT[best[res[0].unit][1]]:
            best[res[0].unit] = (s, conf, res)
    unit, w = votes.most_common(1)[0]
    s, conf, (d, sc, ratio, why, margin) = best[unit]
    adj, tint, label = quantised_colour(s, d)
    return {"donor": unit, "scale": scale_of(ratio), "colour": label, "adjust": adj, "tint": tint, "confidence": conf,
            "agree": round(w / sum(votes.values()), 2), "alternatives": {u: round(v, 1) for u, v in votes.items() if u != unit},
            "why": "; ".join(why) + f"; score {sc:.1f}, size x{ratio:.2f}", "ids_scored": len(ids), "scored_on": s.id,
            "top": [u for u, _ in ranking.most_common(5)]}


def suggest(ctx: Ctx, classes: dict, tokens: list[str]) -> str:
    lines = ["# Donor suggestions (donor scoring on the 2012 art)", "",
             "Per token: the donors with the best summed score over the monster Ids that use it, and the winner's scale and "
             "colour. Reviewed by hand: tools/data/hd_monster_pins.json holds the picks and why.", ""]
    for tok in tokens:
        c = classes[tok]
        ids = c["ids"]
        if not ids:
            continue
        res = rescore_token(ctx, tok, ids)
        lines.append(f"## `{tok}` ({', '.join(ids[:6])}{' ...' if len(ids) > 6 else ''})")
        s = ctx.subject(ids[0])
        lines.append(f"- tags {sorted(s.tags)}, body {s.body}, montype {s.row['MonType']}, ai {s.row['AI']}, "
                     f"modes {hd.modes_of(s.row2)}, slots {s.slots}; art box {s.col['w']}x{s.col['h']}" if s.col else "- no art stats")
        lines.append(f"- winner **{res['donor']}** x{res['scale']:g} ({res['colour']}), {res['confidence']}; {res['why']}")
        for u in res["top"]:
            d = ctx.donors[u]
            sc, ratio, why = hd.score(s, d)
            lines.append(f"  - {u}: {sc:.1f}, size x{ratio:.2f}, tags {sorted(d.tags)}, body {d.body}"
                         + (f", {'; '.join(w for w in why if w.startswith('missing'))}" if any(w.startswith('missing') for w in why) else ""))
        lines.append("")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ mapping
def load_pins(path: Path) -> dict:
    return json.loads(path.read_text("utf-8")) if path.exists() else {"tokens": {}, "noart": {}}


def vanilla_unit(ctx: Ctx, mid: str, pins: dict | None = None) -> tuple[str | None, str]:
    """(D2R unit, how) for a monster that draws a token D2R has the art of. Rule: the unit of the same Id and
    code, else the best unit of the code. Added: the unit of the same Id when the code differs (the 2012 Cain, Tyrael
    ...), then a hand pick from the pins file (`vanilla_ids`); None when D2R has no HD unit for it (D2R draws its own
    helpers, orbs and nests without one)."""
    s = ctx.subject(mid, art=False)
    u, how = hd.vanilla_unit(s, ctx.dms, ctx.mj, ctx.dms2, ctx.by_code)
    if u:
        return u, how
    if mid in ctx.mj:
        return ctx.mj[mid], "unit of the same Id in D2R (the 2012 token differs)"
    pin = (pins or {}).get("vanilla_ids", {}).get(mid)
    if pin:
        return pin["unit"], "pinned: " + pin["reason"]
    return None, "D2R has no HD unit for this token"


def vanilla_units(ctx: Ctx, ids: list[str], pins: dict | None = None) -> dict[str, tuple[str | None, str]]:
    return {mid: vanilla_unit(ctx, mid, pins) for mid in ids}


def pinned_entry(ctx: Ctx, tok: str, ids: list[str], pin: dict) -> dict:
    res = rescore_token(ctx, tok, ids, pinned=pin["donor"])
    res["donor"] = pin["donor"]
    if "scale" in pin:
        res["scale"] = pin["scale"]
    res["confidence"] = pin.get("confidence", res["confidence"])
    if "adjust" in pin:   # a colour set by hand after an in-game look (the scored one is measured on classic art only)
        res["adjust"] = [float(x) for x in pin["adjust"]][:3] + [1.0]
        res["tint"] = [float(x) for x in pin.get("tint", [0.0, 0.0, 0.0, 0.0])]
        res["colour"] = colour_label(res["adjust"], res["tint"]) + " (hand)"
    return {k: res[k] for k in ("donor", "scale", "colour", "adjust", "tint", "confidence")} | {
        "source": "pin", "reason": pin["reason"], "score": res["why"]}


def donor_entry(ctx: Ctx, paths: Paths, tok: str, c: dict, todo: list[str], pin: dict | None, srows: dict, smj: dict) -> dict:
    """Stand-in donor, scale and colour of a token for the monster Ids in `todo`: the hand pick, else the prior mapping
    of the same art, else (the prior rows disagree) the donors the prior mapping used, chosen on the 2012 monsters' names."""
    if pin:
        return pinned_entry(ctx, tok, todo, pin)
    if c["class"] == "new":
        raise SystemExit(f"token {tok} needs a pin in {paths.pins} (run `suggest`)")
    se = prior_entry(paths, srows.get(tok, []), smj)
    if se is None:
        raise SystemExit(f"token {tok}: no usable prior rows")
    keys = ("donor", "scale", "colour", "adjust", "tint", "confidence")
    if se["agree"] >= 0.7 and se["confidence"] != "low":
        return {**{k: se[k] for k in keys}, "source": "reused", "vmap": se["vmap"],
                "reason": f"same art files; reused donor {se['donor']} ({se['prior_rows']} rows, "
                          f"{int(se['agree'] * 100)}% agree)", "prior_alternatives": se["alternatives"]}
    pool = {r["donor"] for r in srows[tok] if r["conf"] in CONF_WEIGHT and r["donor"]}
    rs = rescore_token(ctx, tok, todo, only=pool)
    return {**{k: rs[k] for k in keys}, "source": "reused donors, 2012 names", "vmap": None, "review": True,
            "reason": f"the reference rows for this art disagree ({int(se['agree'] * 100)}% for {se['donor']}, others "
                      f"{se['alternatives']}); 2012 monster names pick {rs['donor']} among them. {rs['why']}",
            "prior_alternatives": se["alternatives"]}


def token_entry(ctx: Ctx, paths: Paths, tok: str, c: dict, pins: dict, srows: dict, smj: dict) -> dict:
    """The mapping entry of one token (see `map`)."""
    e = {"class": c["class"], "ids": len(c["ids"]), "art_vs_prior": c["art_vs_prior"]["relation"]}
    todo = [i for i in c["ids"] if c["id_state"][i] != "vanilla"]
    pin = pins["tokens"].get(tok)
    # `mixed`: D2R has the art but not every mode COF the monster asks for (the MPQ adds a few COFs to vanilla art):
    # the art is still D2R's, so every Id takes the vanilla rule. `split`: an own token (tools/own_tokens.py) whose rows
    # took the vanilla rule of the token they were split from and keep the unit they had
    if c["class"] in ("vanilla", "mixed", "split"):
        vu = vanilla_units(ctx, c["ids"], pins)
        e["d2r_units"] = dict(Counter(u or "-" for u, _ in vu.values()).most_common())
        e["how"] = dict(Counter(how for _, how in vu.values()).most_common())
        # Median Ids (not D2R's own) that draw D2R's art but have no HD unit to take: a stand-in like any other token
        lacking = [i for i, (u, _) in vu.items() if u is None and i not in ctx.dms]
        # D2R's own Ids whose D2R unit ships no model draw nothing in HD. D2R's own helpers and traps are meant to be
        # invisible, so only a pinned token takes a stand-in for them (bug #431: Median brings back the unused Quill Bears,
        # `s7`, whose unit quillbear1 has no model)
        if pin:
            lacking += [i for i, (u, _) in vu.items() if u in ctx.no_model]
        if lacking:
            e.update(donor_entry(ctx, paths, tok, c, lacking, pin, srows, smj))
            e["stand_in_ids"] = lacking
        e["no_unit_ids"] = [i for i, (u, _) in vu.items() if u is None and i not in lacking]
        if c["class"] == "split":
            e["split_of"] = c["split_of"]
    elif c["class"] == "unused":
        e["reason"] = "art in the MPQ, no monstats row uses the token: nothing to map"
    elif c["class"] == "noart":
        n = pins["noart"][tok]
        e.update(donor=n["donor"], scale=1.0, colour="none", adjust=[0.0, 0.0, 0.0, 1.0], tint=[0.0, 0.0, 0.0, 0.0],
                 confidence="low", source="pin", reason=n["reason"])
    else:   # reused / new
        e.update(donor_entry(ctx, paths, tok, c, todo, pin, srows, smj))
        e["ids_mapped"] = len(todo)
    e["monsters"] = c["ids"][:5]
    return e


def _prior_inputs(paths: Paths):
    srows = defaultdict(list)
    for r in parse_prior_report(paths.s_report):
        srows[r["code"].lower()].append(r)
    return srows, hu.load_json(paths.s_hd / "monsters.json")


def map_tokens(paths: Paths) -> dict:
    ctx = Ctx(paths)
    classes = classify(paths)
    pins = load_pins(paths.pins)
    srows, smj = _prior_inputs(paths)
    out = {tok: token_entry(ctx, paths, tok, c, pins, srows, smj) for tok, c in classes.items()}
    ctx.save()
    return out


def apply_splits(paths: Paths) -> list[str]:
    """Bring the committed mapping up to date with tools/data/own_tokens.json without a full `map`: the entry of every
    split token (new) and of the token it was split from (old) is made again; the rest of the file stays."""
    doc = json.loads(paths.tokens.read_text("utf-8"))
    ctx = Ctx(paths)
    classes = classify(paths)
    pins = load_pins(paths.pins)
    srows, smj = _prior_inputs(paths)
    out = []
    for sp in own_tokens.splits():
        for tok in (sp["old"].lower(), sp["new"].lower()):
            doc["tokens"][tok] = token_entry(ctx, paths, tok, classes[tok], pins, srows, smj)
            out.append(f"{tok}: {doc['tokens'][tok]['class']}, {doc['tokens'][tok]['ids']} Ids, units {doc['tokens'][tok].get('d2r_units')}")
    for b in own_tokens.borrows():
        tok = b["new"].lower()
        doc["tokens"][tok] = token_entry(ctx, paths, tok, classes[tok], pins, srows, smj)
        out.append(f"{tok}: {doc['tokens'][tok]['class']}, {doc['tokens'][tok]['ids']} Ids, donor {doc['tokens'][tok].get('donor')}")
    for tok in [t for t in doc["tokens"] if t not in classes]:   # the tokens the borrowed rows left (no row, no art)
        del doc["tokens"][tok]
        out.append(f"{tok}: removed (no row draws it any more)")
    doc["tokens"] = dict(sorted(doc["tokens"].items()))
    doc["counts"] = counts(doc["tokens"])
    paths.tokens.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ctx.save()
    return out


def apply_repins(paths: Paths, tokens: list[str]) -> list[str]:
    """Make the entries of the given tokens again from the pins (a changed hand pick) without a full `map`; the rest of the
    committed mapping stays as it is."""
    doc = json.loads(paths.tokens.read_text("utf-8"))
    ctx = Ctx(paths)
    classes = classify(paths)
    pins = load_pins(paths.pins)
    srows, smj = _prior_inputs(paths)
    out = []
    for tok in tokens:
        doc["tokens"][tok] = e = token_entry(ctx, paths, tok, classes[tok], pins, srows, smj)
        out.append(f"{tok}: {e['class']}, donor {e.get('donor')} x{e.get('scale')} ({e.get('colour')}), {e.get('confidence')}")
    doc["counts"] = counts(doc["tokens"])
    paths.tokens.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ctx.save()
    return out


def apply_recolours(paths: Paths, tokens: list[str]) -> list[str]:
    """The colour of the given stand-in tokens worked out again with the current rule (hd_donors.tint_of) on the token's own
    donor; donor, scale and the rest of the entry stay. For colours a changed rule moves (lane tints2), also those of `reused`
    tokens, whose colour came from the reference mapping."""
    doc = json.loads(paths.tokens.read_text("utf-8"))
    ctx = Ctx(paths)
    by_tok = defaultdict(list)
    for i, r in ctx.ms.items():
        by_tok[tok_of(i, r["Code"])].append(i)
    out = []
    hand = {t for t, p in load_pins(paths.pins)["tokens"].items() if "adjust" in p}
    for tok in tokens:
        e = doc["tokens"][tok]
        if tok in hand:
            out.append(f"{tok}: colour set by hand in the pins, kept ({e['colour']})")
            continue
        ids = e.get("stand_in_ids") or by_tok[tok]
        res = rescore_token(ctx, tok, ids, pinned=e["donor"])
        before = e["colour"]
        e.update(colour=res["colour"], adjust=res["adjust"], tint=res["tint"])
        out.append(f"{tok}: {e['donor']} {before} -> {e['colour']}")
    paths.tokens.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    ctx.save()
    return out


def clip_index(extract: Path) -> dict[str, list[str]]:
    """{enemy animation folder: clip names} from data/hd/character/enemy/<folder>/animation/combined.animations under
    `extract` (tools/sprite3d/extract_anims.py writes that tree from a game slot's CASC)."""
    import d2r_model as dm
    out = {}
    for f in sorted((extract / "data" / "hd" / "character" / "enemy").glob("*/animation/combined.animations")):
        tree = dm.parse_tree(dm.Gr2File.read(f.read_bytes()))
        out[f.parent.parent.name] = sorted({a["Name"] for a in tree["Animations"]})
    return out


# ------------------------------------------------------------------ build
def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def part_vmap(rows: list | None, slots: dict) -> dict | None:
    """The prior provenance rows as {(Median part, variant): (donor part, variant)}, kept for slots this Id draws."""
    if not rows:
        return None
    have = {(hu.PARTS[pc], v) for pc, vs in slots.items() for v in vs}
    out = {(tp, tv): (dp, dv) for tp, tv, dp, dv in rows if (tp, tv) in have}
    return out or None


# D2R's VariantTransformTable cache holds 128 tables (Fog AssetCache, DefaultCapacity 128); every act preloads the tables of the
# monsters its levels can spawn and keeps some of the acts before. One colour table per distinct stand-in colour put 40 of them
# into Act 1 alone and overflowed the cache in a five-town session (bugs.md #360). Stand-ins whose colours lie within
# COLOUR_SHARE_TOL of a more used colour share that colour's table.
COLOUR_SHARE_TOL = 0.2
COLOUR_CLASSES = ("reused", "new", "noart", "mixed")  # mapping classes whose Ids get a stand-in unit (mixed: its stand_in_ids)


def has_standin(e: dict) -> bool:
    """A mapping entry that builds a stand-in unit: a stand-in class, or a vanilla token with pinned stand-in Ids (#431)."""
    return "adjust" in e and (e.get("class") in COLOUR_CLASSES or bool(e.get("stand_in_ids")))


def standin_weight(e: dict) -> int:
    """The monstats Ids drawing a token's stand-in: its stand_in_ids where D2R has the art (mixed, vanilla), else all."""
    return max(1, len(e.get("stand_in_ids") or []) if e.get("class") in ("mixed", "vanilla", "split") else e.get("ids", 1))


def colour_distance(a, b) -> float:
    """Distance of two (adjust, tint) colours: the largest difference of hue (circular, counted twice: 0.1 = 36 degrees),
    saturation, value and the tint's components."""
    (ha, sa, va, _wa), ta = a
    (hb, sb, vb, _wb), tb = b
    dh = abs(ha - hb) % 1.0
    dh = min(dh, 1.0 - dh)
    return max(2 * dh, abs(sa - sb), abs(va - vb), max(abs(x - y) for x, y in zip(ta, tb)))


def share_colours(weights: dict, tol: float = COLOUR_SHARE_TOL) -> dict:
    """{colour key: shared colour key} for colour keys (json [adjust, tint]) weighted by the Ids that use them. The most used
    colours come first and become shared colours; every other one takes the nearest shared colour within `tol`, else its own."""
    centres: list[str] = []
    out = {}
    for key in sorted(weights, key=lambda k: (-weights[k], k)):
        c = json.loads(key)
        best = min(centres, key=lambda x: (colour_distance(json.loads(x), c), x), default=None)
        if best is not None and colour_distance(json.loads(best), c) <= tol + 1e-9:
            out[key] = best
        else:
            centres.append(key)
            out[key] = key
    return out


def colour_label(adj, tint) -> str:
    """The token tables' colour text (hd_donors.tint_of) for an (adjust, tint) pair."""
    if list(adj) == [0.0, 0.0, 0.0, 1.0] and not tint[3]:
        return "none"
    hue = adj[0] - 1.0 if adj[0] > 0.5 else adj[0]
    return f"hue {hue:+.2f} sat {adj[1]:+.2f} val {adj[2]:+.2f}" + (f" tint {tint[3]:.2f}" if tint[3] else "")


def colour_weights(mapping: dict) -> Counter:
    """Colour key -> monstats Ids of the tokens that build a stand-in with that colour."""
    w = Counter()
    for e in mapping.values():
        if has_standin(e):
            w[json.dumps([e["adjust"], e["tint"]])] += standin_weight(e)
    return w


# A D2R unit draws its HD model through its variant table's level0 entry; for some (arach1, brute2, clawviper1, maggotbaby1 ...)
# that entry changes the look a lot (tints, value +1). The stand-in colour is measured against the donor's classic art, the look
# that entry gives in HD, so a stand-in table must hold the shift on top of it (hd_units.variant_table `base`, lane tints2).
# Such a table belongs to its donor and cannot be shared with other donors: they are made, most used first, while all colour
# tables stay within COLOUR_TABLE_LIMIT; the rest keep the plain shared table (reported).
COLOUR_TABLE_LIMIT = 30


def colour_tables(mapping: dict, based: set[str], tol: float = COLOUR_SHARE_TOL, limit: int = COLOUR_TABLE_LIMIT,
                  levelled: set[str] = frozenset()) -> dict:
    """{token: (donor or None, colour key)} for the stand-in tokens of the mapping: (None, shared key) is a plain shared table,
    (donor, key) a table on top of the donor's level0 entry (`based`: donors whose level0 entry changes the look), (LEVELS,
    key) a table of the token's own whose TransLvl entries hold the classic level colours (`levelled`: tokens whose stand-in
    Ids are on several levels, bug #435). Colours of one based donor share within `tol` like the plain ones; a levelled
    token never shares. Own tables are chosen most used first while all tables stay within `limit`."""
    toks = {t: e for t, e in mapping.items() if has_standin(e)}
    weight = {t: standin_weight(e) for t, e in toks.items()}
    own = {t: json.dumps([e["adjust"], e["tint"]]) for t, e in toks.items()}
    shared = share_colours(colour_weights(mapping), tol)
    per_donor: dict[str, Counter] = defaultdict(Counter)
    for t, e in toks.items():
        if e["donor"] in based:
            per_donor[e["donor"]][own[t]] += weight[t]
    cand = Counter()   # (donor, shared key within the donor) -> Ids
    dshare = {}
    for u, w in per_donor.items():
        dshare[u] = share_colours(w, tol)
        for k, n in w.items():
            cand[(u, dshare[u][k])] += n

    def cand_of(t: str) -> tuple:
        e = toks[t]
        return (LEVELS + t, own[t]) if t in levelled else (e["donor"], dshare.get(e["donor"], {}).get(own[t]))
    for t in levelled & set(toks):
        cand[cand_of(t)] += weight[t]
    chosen: set = set()

    def count(ch: set) -> int:
        plain = {shared[own[t]] for t in toks if cand_of(t) not in ch}
        return len(plain) + len(ch)
    for c in sorted(cand, key=lambda c: (-cand[c], c)):
        if count(chosen | {c}) <= limit:
            chosen.add(c)
    out = {}
    for t in toks:
        c = cand_of(t)
        out[t] = c if c in chosen else (None, shared[own[t]])
    return out


LEVELS = "levels:"  # colour_tables: the owner of a levelled token's own table


def levelled_tokens(ctx: "Ctx", mapping: dict) -> dict[str, dict[int, list[tuple[str, str]]]]:
    """{token: {TransLvl: [(Id, MonStatsEx)]}} for the vanilla tokens whose pinned stand-in Ids (#431) are on TransLvl 1-5
    and whose classic art has a palshift.dat: classic draws each level in its own colour (bug #435: the Quill Bears)."""
    import hd_translvl as tl
    out: dict[str, dict] = {}
    for tok, e in mapping.items():
        if not (has_standin(e) and e.get("stand_in_ids")):
            continue
        if not (ctx.paths.d2r / "data" / "global" / "monsters" / tok / "cof" / "palshift.dat").exists():
            continue
        lv: dict[int, list] = defaultdict(list)
        for mid in e["stand_in_ids"]:
            r = ctx.ms.get(mid)
            t = int((r or {}).get("TransLvl") or 0)
            if r and 0 < t <= tl.MAX_LEVEL and tl.enabled(r):
                lv[t].append((mid, r.get("MonStatsEx", "")))
        if lv:
            out[tok] = dict(lv)
    return out


def level_entries(ctx: "Ctx", table: dict, tok: str, levels: dict[int, list]) -> dict[int, str]:
    """Fills the TransLvl entries of a levelled token's own table with the classic palette shift of each level
    (tools/hd_translvl.py measures it as for D2R's units), on top of the table's level-0 entry. {level: shift label}."""
    import hd_translvl as tl
    p = {tok: {t: {"state": "fill", "token": tok, "ids": [i for i, _ in ids], "rows2": [x for _, x in ids]}
               for t, ids in levels.items()}}
    tl.measure(p, ctx.paths.mod / "excel", ctx.paths.d2r, ctx.paths.mod / "monsters")
    done = {}
    for t, e in sorted(p[tok].items()):
        if e["state"] == "fill":
            table["entries"][t + tl.LEVEL0] = tl.fill_entry(table["entries"][t + tl.LEVEL0], table["entries"][tl.LEVEL0],
                                                            e["adj"], e["tint"])
            done[t] = e["label"]
        else:
            done[t] = e["state"]
    return done


def build(paths: Paths, out: Path | None = None) -> dict:
    """HD json for every monstats Id of the mod (units mxl_*.json, colour tables, adapted state machines, monsters.json)
    and a per-Id report. Needs only the committed mapping, the 2012 tables and the D2R baseline."""
    mapping = json.loads(paths.tokens.read_text("utf-8"))["tokens"]
    pins = load_pins(paths.pins)
    ctx = Ctx(paths)
    out = out or paths.out / "data"
    hdc = out / "hd" / "character"
    hd_json = dict(ctx.mj)
    units: dict[str, dict] = {}
    variants: dict[str, tuple] = {}
    rows = []
    borrow_new = {b["new"].lower() for b in own_tokens.borrows()}
    level0 = {}
    for e in mapping.values():
        u = e.get("donor")
        if has_standin(e) and u in ctx.donors and u not in level0:
            var = ctx.donors[u].info.get("var")
            level0[u] = hu.level0_entry(hu.load_json(ctx.paths.d2r / var)) if var and (ctx.paths.d2r / var).exists() else None
    levelled = levelled_tokens(ctx, mapping)
    tables = colour_tables(mapping, {u for u, b in level0.items() if b}, levelled=set(levelled))
    shared = share_colours(colour_weights(mapping))
    for mid, r in ctx.ms.items():
        tok = tok_of(mid, r["Code"])
        e = mapping[tok]
        if tok in borrow_new:
            # a `borrow` token draws the donor's classic art with the donor's monstats2 row (parts, looks, weapon class): the
            # donor's own D2R unit, as it is (a unit made from Median's part slots asked for looks the row never picks, bug #74)
            hd_json[mid] = e["donor"]
            rows.append((mid, tok, e["class"], e["donor"], e["donor"], "1", "none", "borrow: the donor's own unit"))
            continue
        r2, has_row2 = ctx.row2(mid)
        s = ctx.subject(mid, art=False)
        if e["class"] in ("vanilla", "mixed", "split"):
            u, how = vanilla_unit(ctx, mid, pins)
            if mid not in e.get("stand_in_ids", []):   # a stand-in Id has no unit or one without a model (#431)
                if u:
                    hd_json[mid] = u
                rows.append((mid, tok, e["class"], u or hd_json.get(mid, ""), "-", "-", "-", how))
                continue
        if e["donor"] not in ctx.donors:
            raise SystemExit(f"token {tok}: stand-in {e['donor']} is not a usable donor"
                             + (" (D2R ships no model for it)" if e["donor"] in ctx.no_model else ""))
        d = ctx.donors[e["donor"]]
        own = json.dumps([e["adjust"], e["tint"]])
        based, vkey = tables.get(tok, (None, shared.get(own, own)))
        adj, tint = json.loads(vkey)
        scale = None if e["scale"] == 1.0 else e["scale"]
        # a donor whose own level0 entry changes its look keeps it under the shift (COLOUR_TABLE_LIMIT): a table of its own
        lvl = tok if based and based.startswith(LEVELS) else None
        if lvl:
            based = None
        base = level0[based] if based else None
        vname = "v_" + hashlib.sha1((json.dumps([LEVELS + lvl, vkey]) if lvl else vkey if base is None
                                     else json.dumps([based, vkey])).encode()).hexdigest()[:8]
        variants[vname] = (adj, tint, base, lvl)
        wk = s.basew if s.basew not in d.keys else None
        vmap = part_vmap(e.get("vmap"), s.slots)
        key = json.dumps([d.unit, scale, sorted(s.slots.items()), vname, wk, sorted(vmap.items()) if vmap else None])
        uname = f"mxl_{d.unit}_" + hashlib.sha1(key.encode()).hexdigest()[:7]
        units[uname] = dict(donor=d.unit, scale=scale, slots=s.slots, vname=vname, weapon=wk, basew=s.basew, vmap=vmap)
        hd_json[mid] = uname
        colour = e["colour"] if vkey == own else "%s (shared table: %s)" % (e["colour"], colour_label(adj, tint))
        if base:
            colour += " on the donor's level0"
        elif lvl:
            colour += " (own table with the classic TransLvl colours)"
        elif tok in levelled:
            colour += " (levels not coloured: COLOUR_TABLE_LIMIT)"
        elif level0.get(d.unit):
            colour += " (donor's level0 not kept: COLOUR_TABLE_LIMIT)"
        rows.append((mid, tok, e["class"], uname, d.unit, f"{e['scale']:g}", colour, e["confidence"]
                     + ("" if has_row2 else "; no monstats2 row: default torso slot")))
    donor_var = hu.load_json(ctx.paths.d2r / "data/hd/character/enemy/zombie1/zombie1_variant.json")
    level_notes = []
    for vname, (adj, tint, base, lvl) in variants.items():
        table = hu.variant_table(vname, donor_var, adj, tint, base)
        if lvl:
            done = level_entries(ctx, table, lvl, levelled[lvl])
            level_notes.append(f"`{lvl}` ({vname}): " + "; ".join(f"level {t} {x}" for t, x in done.items()))
        write_json(hdc / "enemy" / "mxl" / f"{vname}.json", table)
    sms = set()
    notes = Counter()
    clip_index = load_clips(paths.clips)
    fills, state_fills = {}, {}
    for uname, u in units.items():
        info = ctx.donors[u["donor"]].info
        sm_name = None
        donor_sm = hu.load_json(ctx.paths.d2r / info["sm"])
        clips = hu.sm_clips(donor_sm, clip_index)
        fill = hu.clip_fill(donor_sm, clips)
        if fill:
            fills[u["donor"]] = fill
        sfill = hu.state_fill(donor_sm)
        if sfill:
            state_fills[u["donor"]] = {hu.STATE_FILL_MODES[m]: s for m, s in sorted(sfill.items())}
        if u["weapon"] or hu.death_lacks_hth(donor_sm) or fill or sfill:
            tag = u["weapon"] or ("death" if hu.death_lacks_hth(donor_sm) else "fill")
            sm_name = f"data/hd/character/enemy/mxl/sm_{u['donor']}_{tag}.json"
            if sm_name not in sms:
                sms.add(sm_name)
                sm = hu.adapt_state_machine(donor_sm, u["weapon"], Path(sm_name).stem, clips)
                write_json(out / sm_name.replace("data/", "", 1), sm)
        vp = f"data/hd/character/enemy/mxl/{u['vname']}.json"
        d, nn = hu.build_unit(u["donor"], uname, u["slots"], u["scale"], None, None, u["basew"], sm_name, vp, u["vmap"])
        notes.update(nn)
        write_json(hdc / "enemy" / f"{uname}.json", d)
    (hdc / "monsters.json").parent.mkdir(parents=True, exist_ok=True)
    (hdc / "monsters.json").write_text(json.dumps(hd_json, indent=2), encoding="utf-8")
    rep = ["# HD monster stand-ins (tools/hd_monsters.py build)", "",
           f"{len(rows)} monstats Ids; {len(units)} unit definitions, {len(variants)} colour tables "
           f"({len(set(shared))} stand-in colours, close ones share a table: COLOUR_SHARE_TOL {COLOUR_SHARE_TOL}), {len(sms)} adapted "
           f"state machines. Part notes: {dict(notes)}", "",
           "Stand-in tables with the classic TransLvl colours (bug #435): " + ("; ".join(level_notes) or "none"), "",
           "Clips a donor lacks, bound to one it has: " + ("; ".join(f"{d} {f}" for d, f in sorted(fills.items())) or "none"), "",
           "Modes a donor has no state for, given a copy of state (stateId): "
           + ("; ".join(f"{d} {f}" for d, f in sorted(state_fills.items())) or "none"), "",
           "| Id | Token | Class | Unit | Donor | Scale | Colour | Confidence / note |", "|---|---|---|---|---|---|---|---|"]
    rep += ["| " + " | ".join(str(x).replace("|", "/") for x in r) + " |" for r in rows]
    (out.parent / "hd_monsters.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    ctx.save()
    return {"ids": len(rows), "units": len(units), "variants": len(variants), "state_machines": len(sms), "clip_fills": len(fills),
            "state_fills": len(state_fills),
            "notes": dict(notes), "classes": dict(Counter(r[2] for r in rows))}


# ------------------------------------------------------------------ doc table
# docs/hd-monsters.md keeps a few rows as they were cut or written by hand; `doc` reproduces them, so it leaves the doc as is.
DOC_CUT = {"!1": 165, "8@": 163, "!2": 154, "@6": 161}  # token -> note length (default 160)
# token -> (the tokens it stands for, counted in its class heading; the row as the doc has it)
DOC_ROWS = {
    "hn": (("am", "dz", "so"),
           "| `hn` (was `am` / `dz` / `so`) | cr_archer1 (the unit itself) | x1; none | low | the six `haunt_*` | The six Haunts' "
           "tokens AM / DZ / SO (player class codes) have no art in the MPQ or in D2R; since lane fixes3 they draw D2R's Corrupt "
           "Rogue archer under their own token HN (tools/own_tokens.py `borrow`, docs/legacy-graphics.md section 6) and HD binds "
           "D2R's `cr_archer1` unit as it is (bugs.md #74) |"),
}


def token_table(mapping: dict) -> str:
    def row(tok, e):
        if tok in DOC_ROWS:
            return DOC_ROWS[tok][1]
        mon = ", ".join(f"`{m}`" for m in e["monsters"][:3]) + (f" +{e['ids'] - 3}" if e["ids"] > 3 else "")
        if e["class"] in ("vanilla", "mixed", "split"):
            us = ", ".join(f"{u} ({n})" if len(e["d2r_units"]) > 1 else u for u, n in list(e["d2r_units"].items())[:3])
            how = ", ".join(e["how"])
            if e.get("split_of"):
                how = f"own token, split from `{e['split_of']}`: " + how
            if e.get("stand_in_ids"):
                what = "Ids whose D2R unit has no model" if e["class"] == "vanilla" else "Median-only Ids"
                how += f"; {len(e['stand_in_ids'])} {what} ({', '.join(e['stand_in_ids'][:3])}) get {e['donor']} x{e['scale']:g} ({e['confidence']})"
            return f"| `{tok}` | {us} | {mon} | {how} |"
        if e["class"] == "unused":
            return f"| `{tok}` | - | - | art in the MPQ, no monstats row uses it |"
        note = e.get("reason", "").split(". ")[0]
        flag = " (review)" if e.get("review") else ""
        return (f"| `{tok}` | {e['donor']} | x{e['scale']:g}; {e['colour']} | {e['confidence']}{flag} | {mon} | "
                f"{e['source']}: {note[:DOC_CUT.get(tok, 160)]} |")
    heads = {"vanilla": "| Token | D2R unit | Monsters | How |\n|---|---|---|---|\n",
             "unused": "| Token | - | - | Note |\n|---|---|---|---|\n"}
    full = "| Token | Stand-in (D2R unit) | Scale; colour | Confidence | Monsters | Source / reason |\n|---|---|---|---|---|---|\n"
    parts = []
    for cls in ("new", "noart", "reused", "mixed", "split", "vanilla", "unused"):
        toks = [t for t, e in sorted(mapping.items()) if e["class"] == cls]
        rows = [row(t, mapping[t]) for t in toks]
        n = sum(len(DOC_ROWS[t][0]) if t in DOC_ROWS else 1 for t in toks)
        h = heads.get(cls, full) if cls not in ("mixed", "split") else heads["vanilla"]
        parts.append(f"### {cls} ({n} tokens)\n\n" + h + "\n".join(rows) + "\n")
    return "\n".join(parts)


def counts(mapping: dict) -> dict:
    return dict(Counter(e["class"] for e in mapping.values()))


# ------------------------------------------------------------------ cli
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["classify", "suggest", "map", "splits", "repin", "recolour", "clips", "build", "doc"])
    ap.add_argument("tokens_arg", nargs="*", help="suggest: tokens (default: the `new` ones); repin: tokens; clips: the folder "
                    "tools/sprite3d/extract_anims.py wrote")
    ap.add_argument("--mod-global", default=str(fxpaths.MXL))
    ap.add_argument("--reference", default=str(REFERENCE or ""), help="the reference checkout (read-only)")
    ap.add_argument("--d2r", default=str(fxpaths.D2R), help="D2R 93847 baseline extract (default: MXL_D2R_EXTRACT, "
                    "the repo's extract/d2r/93847 or the reference one)")
    ap.add_argument("--out", help="build: the data folder to write into (default <work>/hd_monsters/data; tools/build.py "
                    "passes work/mod/data)")
    ap.add_argument("--work", default=str(ROOT / "work"))
    ap.add_argument("--tokens", default=str(TOKENS_JSON))
    ap.add_argument("--pins", default=str(PINS_JSON))
    ap.add_argument("--clips", default=str(CLIPS_JSON))
    ap.add_argument("--doc", default=str(ROOT / "docs" / "hd-monsters.md"))
    a = ap.parse_args()
    paths = Paths(a)
    paths.out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "classify":
        paths.configure()
        c = classify(paths)
        (paths.out / "classes.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
        print(dict(Counter(v["class"] for v in c.values())), "-> classes.json")
    elif a.cmd == "suggest":
        c = classify(paths)
        ctx = Ctx(paths)
        toks = a.tokens_arg or [t for t, v in c.items() if v["class"] == "new"]
        (paths.out / "suggest.md").write_text(suggest(ctx, c, toks), encoding="utf-8")
        ctx.save()
        print(f"{len(toks)} tokens -> {paths.out / 'suggest.md'}")
    elif a.cmd == "map":
        m = map_tokens(paths)
        paths.tokens.parent.mkdir(parents=True, exist_ok=True)
        about = ("token -> D2R HD stand-in for D2R-XL 2012; generated by tools/hd_monsters.py map "
                 "(hand picks: hd_monster_pins.json); see docs/hd-monsters.md")
        paths.tokens.write_text(json.dumps({"_about": about, "counts": counts(m), "tokens": m}, indent=1,
                                           ensure_ascii=False) + "\n", encoding="utf-8")
        print(counts(m), "->", paths.tokens)
    elif a.cmd == "splits":
        print("\n".join(apply_splits(paths)), "->", paths.tokens)
    elif a.cmd == "repin":
        if not a.tokens_arg:
            raise SystemExit("repin: name the tokens")
        print("\n".join(apply_repins(paths, a.tokens_arg)), "->", paths.tokens)
    elif a.cmd == "recolour":
        if not a.tokens_arg:
            raise SystemExit("recolour: name the tokens")
        print("\n".join(apply_recolours(paths, a.tokens_arg)), "->", paths.tokens)
    elif a.cmd == "clips":
        idx = clip_index(Path(a.tokens_arg[0]))
        about = ("D2R enemy animation folder -> clip names of its combined.animations (names only; tools/hd_monsters.py clips, "
                 "from a game slot's CASC via tools/sprite3d/extract_anims.py); docs/hd-monsters.md section 8")
        rows = ",\n".join(f"  {json.dumps(k)}: {json.dumps(v)}" for k, v in idx.items())
        paths.clips.write_text(f'{{\n "_about": {json.dumps(about)},\n "folders": {{\n{rows}\n }}\n}}\n', encoding="utf-8")
        print(len(idx), "folders ->", paths.clips)
    elif a.cmd == "build":
        paths.configure()
        print(build(paths, Path(a.out) if a.out else None))
    elif a.cmd == "doc":
        text = Path(a.doc).read_text("utf-8")
        mapping = json.loads(paths.tokens.read_text("utf-8"))["tokens"]
        b, e = "<!-- tokens:begin -->", "<!-- tokens:end -->"
        i, j = text.index(b) + len(b), text.index(e)
        Path(a.doc).write_text(text[:i] + "\n\n" + token_table(mapping) + "\n" + text[j:], encoding="utf-8")
        print("table ->", a.doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
