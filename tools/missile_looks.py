"""HD pictures for Median XL 2012's missiles, decided by what each missile does on screen (docs/hd-effects.md section 10).

tools/effects_hd.py gives a row the HD effect of the D2R row that shares its art file. That breaks where the art file says nothing about how
the row is used. This step runs after it and looks at behaviour:

  learn D2R      every vanilla missile row with its HD model: what the row does (flies, trail piece, burst, stays on the ground), and whether
                 the model draws anything at all (56 of D2R's 374 models are empty stubs: an entity with a transform and no effect)
  learn Median   every row of v005: what the row does and what legacy shows while it flies: its own art, or, for a logic row without art, the
                 art of the short client missiles it leaves behind (Forked Lightning, Tempest and Pyroblast are drawn only that way)
  decide         D2R's own convention: the flying row carries the picture and its trail pieces may be stubs. So
                   - a row that flies and draws in legacy needs a model that vanilla uses on a row that travels: an explosion model on a
                     flying row plays once and is gone, and on a missile that fires hundreds of rows it blows out the screen;
                   - a logic row whose client missiles draw in legacy gets such a flying model itself;
                   - a row that does not fly needs a model that draws, of the same kind (burst, ground, trail).
                 The model is the closest of that group by colour, size, element and shape (score()) and scaled to the legacy art.

Rows that already satisfy this keep the effects_hd.py decision, and hand picks (data/hd-effects-picks.tsv) are never overruled: the step only changes
what is demonstrably wrong.
Input: work/mod (after effects_hd.py), D2R's tables and HD definitions, Median's DCCs (the art cache of effects_hd.py).
Writes: work/mod/data/hd/missiles/missiles.json and scaled mxl_* variants, work/mod/missile_looks.md (every changed row, every row left without a
match; row names, so not committed), work/mod/missile_looks.json (the same for tools/skill_looks.py) and work/mod/missiles_before_looks.json (the map
as effects_hd.py left it).
Usage: py -3 tools/missile_looks.py [--work DIR] [--check]  (--check: audit only, exit 1 when a row a skill reaches has no picture in flight)
"""
import argparse
import copy
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import effects_hd as fx  # noqa: E402
import fxpaths  # noqa: E402

# Vel at or above this is a row that travels; below it the row drifts (smoke, chips) and counts as staying
FLYING_VEL = 6
TRAIL_COLS = ("CltSubMissile1", "CltSubMissile2", "CltSubMissile3")
CARRIER_SCALE = 1.5
TRAVELS = {"flight", "ground"}  # what a model must be used for to go on a flying row (a looping ground effect that travels stays a moving fire)
# D2R rows that only start other effects or throw props: no projectile to see
NOT_A_PICTURE = re.compile(r"emitter|indicator|maker|teleport|summon|hurricane|boulder|volcano|_rock|spider|caltrops|skull|_head|blood|ghost|flamethrower|mist")
ELEMENTS = {"fire", "ice", "elec", "poison", "arcane", "holy", "bone", "blood", "dark"}  # what a skill's name may tell (a Tempest is not a wind)


def is_art(name: str) -> bool:
    return name not in ("", "null")


def flies(p) -> bool:
    return max(p.num("Vel"), p.num("MaxVel")) >= FLYING_VEL


def kind_of(p) -> str:
    """What the row does: flight / ground (stays and loops) / trail (a client piece of a flying row) / burst (plays once where it starts)."""
    if flies(p):
        return "flight"
    if p.sub and not p.hit and p.num("Range") <= 40:
        return "trail"
    return "ground" if p.row.get("LoopAnim") == "1" and p.num("Range") >= 20 else "burst"


def stays(p) -> bool:
    """A row of kind `ground` that keeps its picture on screen: at least two passes over its art (a Range about the length of the art plays once
    and is gone, whatever LoopAnim says). Not used on vanilla rows, whose use of a model decides what the model is for."""
    return kind_of(p) == "ground" and not (p.art and p.num("Range") < 2 * p.art["n"])


def needs(p) -> str:
    """Which kind of picture a Median row needs: its kind, but a row of kind `ground` that plays its art once is a burst."""
    k = kind_of(p)
    return "burst" if k == "ground" and not stays(p) else k


# D2R's particle programs that draw nothing by design (a definition can point at one: b_r_smoke_s_1, miasma_smoke_puff)
EMPTY_PARTICLES = re.compile(r"(^|[/_])empty\.particles$|dummy_suppress", re.I)


def effect_draws(c: dict) -> bool:
    """A VfxDefinitionComponent draws when it names a particle program that is not one of D2R's empty ones."""
    return c.get("type") == "VfxDefinitionComponent" and bool(c.get("filename")) and not EMPTY_PARTICLES.search(c["filename"])


def definition_draws(d: dict | None) -> bool:
    """A definition draws when an entity has an effect or a mesh: an empty stub has only the root and a transform."""
    if not d:
        return False
    return any(effect_draws(c) or "Model" in c.get("type", "") or "Mesh" in c.get("type", "")
               for e in d.get("entities", []) for c in e.get("components", []))


class Models:
    """HD definitions by model name: the mod's own variants first, then D2R's."""

    def __init__(self, *dirs: Path):
        self.dirs, self.memo = dirs, {}

    def get(self, model: str) -> dict | None:
        if model not in self.memo:
            self.memo[model] = next((fx.load_json(d / f"{model}.json") for d in self.dirs if (d / f"{model}.json").exists()), None)
        return self.memo[model]

    def draws(self, model: str | None) -> bool:
        return bool(model) and model.lower() != "null" and definition_draws(self.get(model))


def learn_d2r(dm: dict, hd_map: dict, models: Models) -> dict[str, list]:
    """kind -> D2R rows (with .model) whose model draws and which have legacy art to compare with."""
    lib: dict[str, list] = {"flight": [], "ground": [], "burst": [], "trail": []}
    for p in dm.values():
        m = hd_map.get(fx.norm_key(p.name))
        if isinstance(m, str) and models.draws(m) and p.art and is_art(p.art_name):
            p.model = m
            lib[kind_of(p)].append(p)
    return lib


def usable_for(lib: dict[str, list]) -> dict[str, Counter]:
    """Model -> how many vanilla rows of each kind use it."""
    usable: dict[str, Counter] = {}
    for k, rows in lib.items():
        for c in rows:
            usable.setdefault(c.model, Counter())[k] += 1
    return usable


def travels(uses: Counter | None) -> bool:
    """Vanilla mostly puts the model on rows that travel or stay: one vanilla row flying with an explosion does not make it a projectile."""
    return bool(uses) and sum(uses[k] for k in TRAVELS) > sum(uses[k] for k in uses if k not in TRAVELS)


def picked(art_name: str, name: str, hand: frozenset) -> bool:
    """A hand pick covers this row: a line for its art, or a line naming the row."""
    return art_name in hand or fx.ROW_PICK + name.lower() in hand


def plays_once(uses: Counter | None) -> bool:
    """Vanilla only puts this model on rows that play once (a model no vanilla row with art uses, a hand pick or a mod's own, is not judged)."""
    return bool(uses) and not (uses["flight"] or uses["ground"] or uses["trail"])


def is_piece(s) -> bool:
    """A client missile that draws its parent while it flies: short-lived and either directional (a streak along the path) or
    playing once. A long or looping piece without directions is something an emitter leaves on the ground: it draws by itself."""
    return s.num("Range") <= 40 and (s.num("NumDirections") > 1 or s.row.get("LoopAnim") != "1")


def legacy_picture(p, profs: dict):
    """What legacy draws while the row exists: (art statistics, art name). Own art first, else the first client missile that is a
    trail piece of it."""
    if p.art and is_art(p.art_name):
        return p.art, p.art_name
    for c in TRAIL_COLS:
        s = profs.get(p.row.get(c, "").lower())
        if s is not None and s.art and is_art(s.art_name) and is_piece(s):
            return s.art, s.art_name
    return None, ""


def carried_pieces(profs: dict) -> set[str]:
    """Trail pieces of a row that flies: D2R's convention draws them with the flying row (bone spear's trail is a stub)."""
    out = set()
    for p in profs.values():
        if flies(p):
            for c in TRAIL_COLS:
                s = profs.get(p.row.get(c, "").lower())
                if s is not None and is_piece(s):
                    out.add(s.name.lower())
    return out


def score(art: dict, m_tags: tuple, c) -> float:
    """Lower is closer: colour first (a missile's name is a nickname: Pyroblast's row is called pbthunder), then size, element, shape."""
    mf, ms, _ = m_tags
    cf, cs, _ = c.words_tags()
    s = 3.0 * fx.colour_dist(art, c.art) + 1.2 * min(3.0, fx.log2r(fx.size_of(art), fx.size_of(c.art)))
    s -= 1.7 * min(2, len(mf & cf))
    if mf and cf and not mf & cf:
        s += 0.8
    if "nova" in cs and "nova" not in ms:
        s += 2.0  # a ring is not a projectile
    if "blade" in cf and "blade" not in mf:
        s += 2.5  # an arrow or a blade shows its shaft
    if not c.skills:
        s += 0.4  # monster-only effects last
    return s


def colour_family(art: dict | None) -> set[str]:
    """The element a saturated art colour shows: orange is fire, blue is cold or lightning, green is poison."""
    if not art or art["hsv"][1] < 0.4:
        return set()
    h = art["hsv"][0]
    if h <= 0.14 or h >= 0.95:
        return {"fire"}
    if 0.2 <= h <= 0.45:
        return {"poison"}
    return {"elec", "ice"} if 0.5 <= h <= 0.72 else set()


def row_tags(p, art_name: str, carrier: bool, sources: dict | None = None) -> tuple:
    """(element, shape, words) of the row's picture: the art's name, the vanilla art it was made from, the row's own name where it has
    art (a logic row's name is a nickname), and only the elements of its skills' names."""
    fam, shape, words = fx.tags(art_name.replace(fx.BS, " "), (sources or {}).get(art_name.lower(), ""), *([] if carrier else [p.name]))
    fam = set(fam) | (set(fx.tags(*p.skills)[0]) & ELEMENTS) | colour_family(p.art if p.art else None)
    if "explode" in shape:  # a fire arrow's explosion is fire, not an arrow
        fam.discard("blade")
    return fam, shape, words


def art_sources(work: Path) -> dict[str, str]:
    """Art name (lowercase) -> the vanilla animation tools/art_provenance.py found it was made from."""
    p = work / "art_provenance.json"
    if not p.exists():
        return {}
    out = {}
    for name, r in fx.load_json(p).get("effects", {}).get("files", {}).items():
        if name.startswith("missiles/") and r.get("sources"):
            out[name[len("missiles/"):].lower()] = r["sources"][0]["file"].rsplit("/", 1)[-1]
    return out


def scaled_base(model: str | None) -> str | None:
    """The D2R model of a scaled variant `mxl_<model>_s<percent>` (effects_hd.py), else the model itself."""
    m = re.fullmatch(r"mxl_(.+)_s\d+", model or "")
    return m.group(1) if m else model


def origin(model: str | None, tinted: dict) -> str | None:
    """The D2R model behind a tinted copy or a scaled variant."""
    base = scaled_base(model)
    return tinted.get(base, base)


def decide(mm: dict, lib: dict[str, list], current: dict, models: Models, tinted: dict | None = None,
           hand_arts: frozenset = frozenset(), sources: dict | None = None, own: frozenset = frozenset()) -> list[dict]:
    """One decision per row that legacy draws: keep, or a new model. Rows without a legacy picture are not touched, nor those of a hand pick."""
    tinted = tinted or {}
    usable = usable_for(lib)
    carried = carried_pieces(mm)
    out = []
    for name, p in mm.items():
        art, art_name = legacy_picture(p, mm)
        if art is None:
            continue
        kind = needs(p)
        carrier = not (p.art and is_art(p.art_name))
        if carrier and kind != "flight":  # a logic row that does not travel: its pieces draw on their own
            continue
        cur = current.get(fx.norm_key(name))
        draws = models.draws(cur)
        if kind == "flight":
            good = draws and travels(usable.get(origin(cur, tinted)))
            why = "flying row on a model made to play once" if draws else "flying row with no picture in HD"
        elif kind == "trail" and name in carried and not draws:
            good, why = True, ""  # the flying row carries it, as in D2R
        elif kind == "ground":
            good = draws and not plays_once(usable.get(origin(cur, tinted)))
            why = "row that stays on a model made to play once" if draws else "model draws nothing"
        else:
            good, why = draws, "model draws nothing"
        if good or picked(art_name, name, hand_arts) or name in own:  # D2R's own row on D2R's own model stays, a stub there is D2R's choice
            out.append({"name": name, "kind": kind, "carrier": carrier, "model": cur, "was": cur, "action": "keep", "why": "", "art": art_name})
            continue
        cands = [c for c in lib[kind] if not NOT_A_PICTURE.search(c.model) and (kind != "flight" or (travels(usable.get(c.model)) and usable[c.model]["flight"] > usable[c.model]["ground"]))] or lib["burst"]
        q = copy.copy(p)
        q.art, q.art_name = art, art_name
        m_tags = row_tags(p, art_name, carrier, sources)
        c = min(cands, key=lambda x: score(art, m_tags, x))
        if draws and origin(cur, tinted) == c.model:  # the scoring ends up where the row already is
            out.append({"name": name, "kind": kind, "carrier": carrier, "model": cur, "was": cur, "action": "keep", "why": "", "art": art_name})
            continue
        close = fx.colour_dist(art, c.art) < 0.2 or (bool(m_tags[0] & c.words_tags()[0]) and fx.colour_dist(art, c.art) < 0.45)
        if not close and draws and kind != "ground":  # nothing close enough to justify a change: keep what draws and list it
            # (a row that stays is the exception: a looping picture of another colour beats one that is gone after a second)
            out.append({"name": name, "kind": kind, "carrier": carrier, "model": cur, "was": cur, "action": "hand", "why": why, "art": art_name,
                        "like": c.name})
            continue
        scale = fx.scale_for(q, c)
        if carrier:  # legacy draws a logic row as a chain of pieces along its path: one projectile must fill more than one piece does
            scale = min(1.8, round(scale * CARRIER_SCALE, 1))
        out.append({"name": name, "kind": kind, "carrier": carrier, "model": c.model, "was": cur, "action": "new", "close": close,
                    "scale": scale, "why": why, "art": art_name, "like": c.name})
    return out


def apply(decisions: list[dict], current: dict, out: Path, models: Models) -> int:
    """The new model of each changed row into missiles.json (both key forms), with a scaled copy when the art size asks for one."""
    written = 0
    final = dict(current)
    for d in decisions:
        if d["action"] != "new":
            continue
        model = d["model"]
        if d["scale"] != 1:
            vname = f"mxl_{model}_s{round(d['scale'] * 100)}"
            if not (out / "hd" / "missiles" / f"{vname}.json").exists():
                fx.write_json(out / "hd" / "missiles" / f"{vname}.json", fx.scaled_definition(models.get(model), vname, d["scale"]))
                written += 1
            model = vname
        d["final"] = model
        final[fx.norm_key(d["name"])] = model
        final[d["name"].lower()] = model
    fx.write_json(out / "hd" / "missiles" / "missiles.json", final)
    return written


def report(work: Path, decisions: list[dict], lib: dict, n_stubs: int) -> None:
    new = [d for d in decisions if d["action"] == "new"]
    hand = [d for d in decisions if d["action"] == "hand" or (d["action"] == "new" and not d["close"])]
    head = ["# HD pictures by what the missile does (tools/missile_looks.py)", "",
            f"D2R models that draw nothing: {n_stubs}. Library of D2R rows by kind: " + ", ".join(f"{k} {len(v)}" for k, v in lib.items()) + ".",
            f"Rows legacy draws, looked at: {len(decisions)}; kept: {len(decisions) - len(new)}; changed: {len(new)} (logic rows given a flying model: "
            f"{sum(d['carrier'] for d in new)}); no close match, for hand work: {len(hand)}.", "",
            "## Rows for hand work", "", "| Row | Kind | Legacy art | Model now | Closest D2R row | Why |", "|-|-|-|-|-|-|",
            *[f"| {d['name']} | {d['kind']} | {d['art']} | {d.get('final', d['model'])} | {d['like']} | {d['why']} |" for d in sorted(hand, key=lambda x: x["name"])], "",
            "## Changed rows", "",
            "| Row | Kind | Legacy art | Was | Now | Scale | Like D2R row | Why |", "|-|-|-|-|-|-|-|-|"]
    body = [f"| {d['name']} | {d['kind']}{' (logic)' if d['carrier'] else ''} | {d['art']} | {d['was']} | {d.get('final', d['model'])} | {d['scale']} | "
            f"{d['like']} | {d['why']} |" for d in sorted(new, key=lambda x: (x["kind"], x["name"]))]
    (work / "missile_looks.md").write_text("\n".join(head + body) + "\n", encoding="utf-8")


def audit(mm: dict, current: dict, models: Models, usable: dict, tinted: dict | None = None, hand_arts: frozenset = frozenset(),
          reached_only: bool = True, own: frozenset = frozenset()) -> list[str]:
    """Rows legacy draws in flight and HD does not: the check of the build and of the tests. `reached_only`: rows some skill reaches."""
    bad = []
    for name, p in mm.items():
        art, art_name = legacy_picture(p, mm)
        if art is None or not flies(p) or picked(art_name, name, hand_arts) or name in own or (reached_only and not p.skills):
            continue
        cur = current.get(fx.norm_key(name))
        if not models.draws(cur) or not travels(usable.get(origin(cur, tinted or {}))):
            bad.append(f"{name}: {cur}")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", default=str(fxpaths.MOD))
    ap.add_argument("--check", action="store_true", help="audit only: exit 1 when a row a skill reaches has no picture in flight")
    args = ap.parse_args()
    work = Path(args.work)
    out = work / "data"
    art = fx.ArtCache(fxpaths.WORK / "effects_hd_art.json")
    d2r_map = fx.load_json(fx.HDM / "missiles.json")
    current = fx.load_json(out / "hd" / "missiles" / "missiles.json")
    models = Models(out / "hd" / "missiles", fx.HDM)
    dm, mm = fx.missile_profiles(fxpaths.D2R_EXCEL, "d2r", art), fx.missile_profiles(fxpaths.TABLES, "mxl", art)
    for p in mm.values():  # base-game art: D2R's copy is the one drawn
        if p.art is None and is_art(p.art_name):
            p.art = art.get("d2r", "missiles", p.art_name)
    lib = learn_d2r(dm, d2r_map, models)
    report_file = work / "hd_recolour.json"
    recolours = fx.load_json(report_file).get("recolours", []) if report_file.exists() else []
    tinted = {r["to"]: r["from"] for r in recolours if r.get("kind") == "missile"}
    hand_arts = fx.picked_names(fx.load_picks(fxpaths.PICKS_TSV), "missile")
    own = frozenset(n for n, p in mm.items() if n in dm and dm[n].art_name == p.art_name and d2r_map.get(fx.norm_key(n)) == current.get(fx.norm_key(n)))
    if args.check:
        no_match = {d["name"] for d in decide(mm, lib, current, models, tinted, hand_arts, art_sources(work), own) if d["action"] == "hand"}
        bad = [b for b in audit(mm, current, models, usable_for(lib), tinted, hand_arts, own=own) if b.split(":")[0] not in no_match]
        print(f"{len(bad)} rows a skill reaches fly in legacy with no flying HD model ({len(no_match)} more are listed for hand work)")
        print("\n".join(bad[:60]))
        return 1 if bad else 0
    n_stubs = sum(1 for f in fx.HDM.glob("*.json") if f.stem != "missiles" and not models.draws(f.stem))
    fx.write_json(work / "missiles_before_looks.json", current)  # the map as effects_hd.py left it: what tools/skill_looks.py compares with
    decisions = decide(mm, lib, current, models, tinted, hand_arts, art_sources(work), own)
    written = apply(decisions, current, out, models)
    report(work, decisions, lib, n_stubs)
    fx.write_json(work / "missile_looks.json", [{k: d[k] for k in ("name", "kind", "carrier", "action", "why", "art", "close") if k in d}
                                                for d in decisions if d["action"] != "keep"])
    art.save()
    new = [d for d in decisions if d["action"] == "new"]
    hand = [d for d in decisions if d["action"] == "hand" or (d["action"] == "new" and not d["close"])]
    print(f"missile_looks: {len(decisions)} rows looked at, {len(new)} changed ({dict(Counter(d['kind'] for d in new))}), {written} scaled models, "
          f"{len(hand)} for hand work; report -> {work / 'missile_looks.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
