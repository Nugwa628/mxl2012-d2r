"""HD unit emission for D2R-XL 2012: UnitDefinition / variant table / state machine json built from a D2R donor unit.

The D2R baseline root is set with `configure()` instead of a module constant, nothing reads the game install. Units are
plain JSON (docs/hd-monsters.md); models are not touched.
"""
import copy
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

D2R: Path | None = None   # extract/d2r/93847 (read-only D2R baseline)
HDC: Path | None = None


def configure(d2r_root: Path) -> None:
    global D2R, HDC
    D2R = Path(d2r_root)
    HDC = D2R / "data" / "hd" / "character"


PARTS = {"HD": "head", "TR": "torso", "LG": "legs", "RA": "rarm", "LA": "larm", "RH": "rhand", "LH": "lhand",
         "SH": "shield", **{f"S{i}": f"special{i}" for i in range(1, 9)}}
PART_CODES = list(PARTS)
MODES = ["DT", "NU", "WL", "GH", "A1", "A2", "BL", "SC", "S1", "S2", "S3", "S4", "DD", "KB", "SQ", "RN"]
MODE_ID = {"DT": 0, "NU": 1, "WL": 2, "GH": 3, "A1": 4, "A2": 5, "BL": 6, "SC": 7, "S1": 8, "S2": 9, "S3": 10,
           "S4": 11, "DD": 12, "KB": 13, "SQ": 14, "RN": 15}


def load_json(p: Path):
    return json.loads(p.read_text("utf-8-sig"))


def unit_path(unit: str) -> Path | None:
    for sub in ("enemy", "npc"):
        p = HDC / sub / f"{unit}.json"
        if p.exists():
            return p
    return None


def split_variants(v: str) -> list[str]:
    return [x for x in re.split(r"[,\s]+", v.strip('"')) if x]


def variants_cell(row2: dict, pc: str) -> str:
    """The `<part>v` cell of monstats2. 1.13c and D2R spell the arm columns `Rav` / `Lav`; a lookup of
    `RAv` / `LAv` would always fall back to `lit`; both spellings are accepted here."""
    return row2.get(pc + "v") or row2.get(pc[0] + pc[1].lower() + "v") or ""


def slots_of(row2: dict) -> dict[str, list[str]]:
    """Part slot (monstats2 code) -> its variant list for the parts the monster draws."""
    out = {}
    for pc in PART_CODES:
        if row2.get(pc) == "1":
            vs = [v for v in split_variants(variants_cell(row2, pc)) if v != "nil"]
            out[pc] = list(dict.fromkeys(vs)) or ["lit"]
    return out


def modes_of(row2: dict) -> list[str]:
    return [m for m in MODES if row2.get("m" + m) == "1"]


def has_model(unit: str, files: set[str]) -> bool:
    """True when the D2R file list (lower-case paths) holds a model the unit definition names: some of D2R's unit files
    (eagle, quillbear1, gorgon1 ...) name models and skeletons D2R does not ship, so a stand-in made from them is invisible."""
    p = unit_path(unit)
    if p is None:
        return False
    ms = [m["path"].lower() for m in load_json(p)["dependencies"].get("models", [])]
    return any(m in files or m.replace(".model", "_lod0.model") in files for m in ms)


def unit_info(unit: str) -> dict | None:
    """Parts (part -> variants), scale, state machine and modes per weapon class of a D2R unit definition."""
    p = unit_path(unit)
    if p is None:
        return None
    d = load_json(p)
    parts: dict[str, set] = defaultdict(set)
    scale = None
    sm_path = var_path = None
    for e in d["entities"]:
        for c in e["components"]:
            if c["type"] == "UnitPartComponent":
                parts[c["part"]].add(c["variant"])
            elif c["type"] == "TransformDefinitionComponent" and e["name"] == "entity_root":
                scale = c["scale"]
            elif c["type"] == "UnitRootComponent":
                sm_path = c["state_machine_filename"]
            elif c["type"] == "VariantDefinitionComponent":
                var_path = c["filename"]
    sm = {}
    names = {}
    if sm_path and (D2R / sm_path).exists():
        for s in load_json(D2R / sm_path)["states"]:
            for wc, anims in s["animationBindings"].items():
                if anims:
                    sm.setdefault(wc, set()).add(s["modeId"])
                    names.setdefault(wc, set()).add(s["_name"])
    return {"unit": unit, "parts": {k: sorted(v) for k, v in parts.items()}, "scale": scale, "sm": sm_path,
            "var": var_path, "modes": {k: sorted(v) for k, v in sm.items()},
            "states": {k: sorted(v) for k, v in names.items()}, "path": str(p)}



WEAPON_PARTS = ("rhand", "lhand", "shield")
TIERS = ["lit", "med", "hvy"]
ZERO4 = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0}


def color_transform(name: str, adjust=(0.0, 0.0, 0.0, 1.0), tint=(0.0, 0.0, 0.0, 0.0)) -> dict:
    return {"type": "ColorTransform", "name": name,
            "colorAdjustment": dict(zip("xyzw", (round(a, 4) for a in adjust))),
            "hueAdjustment0": dict(ZERO4), "hueAdjustment1": dict(ZERO4),
            "satAdjustment0": dict(ZERO4), "satAdjustment1": dict(ZERO4),
            "colorTint": dict(zip("xyzw", (round(a, 4) for a in tint)))}


def level0_entry(variant: dict | None) -> dict | None:
    """A D2R unit's `level0` entry (TransLvl 0, entry 2) when it changes the look, else None. Its HD model is drawn
    through it: a stand-in table must keep it (lane tints2: arach1, brute2, maggotbaby1 ... lost their own base look)."""
    if not variant or len(variant.get("entries", [])) < 3:
        return None
    e = variant["entries"][2]
    for t in e.get("transforms", []):
        adj = [t["colorAdjustment"][k] for k in "xyzw"]
        if adj != [0.0, 0.0, 0.0, 1.0] or t["colorTint"]["w"] or any(
                any(t.get(f, ZERO4).values()) for f in ("hueAdjustment0", "hueAdjustment1", "satAdjustment0", "satAdjustment1")):
            return e
    return None


def compose_transform(name: str, base: dict, adjust, tint) -> dict:
    """The colour shift (adjust, tint) on top of a D2R transform `base` of the same mask: hue turns add, saturation and
    value add (clipped to -1..1 unless the base value is already outside, D2R's own y 10), weight kept; the shift's tint
    wins when it has one, else the base's; the base's hue/sat adjustments are kept."""
    ba, bt = base["colorAdjustment"], base["colorTint"]

    def add(b, a):
        return b + a if abs(b) > 1.0 else max(-1.0, min(1.0, b + a))
    adj = ((ba["x"] + adjust[0]) % 1.0, add(ba["y"], adjust[1]), add(ba["z"], adjust[2]), ba["w"])
    t = color_transform(name, adj, tint if tint[3] else [bt[k] for k in "xyzw"])
    for f in ("hueAdjustment0", "hueAdjustment1", "satAdjustment0", "satAdjustment1"):
        t[f] = {k: round(v, 4) for k, v in base.get(f, ZERO4).items()}
    return t


def variant_table(name: str, donor_var: dict, adjust, tint, base: dict | None = None) -> dict:
    """A VariantTransformTable whose 8 colour shifts (monstats TransLvl) all hold the same colour transform; with `base`
    (the donor's level0 entry, `level0_entry`) the shift sits on top of the donor's own transform of each mask."""
    entries = []
    for i in range(8):
        if base:
            bts = base["transforms"]
            ts = [compose_transform(f"ColorTransform_{i:03d}_{j:03d}", bts[j], adjust, tint) if j < len(bts)
                  else color_transform(f"ColorTransform_{i:03d}_{j:03d}", adjust, tint) for j in range(3)]
        else:
            ts = [color_transform(f"ColorTransform_{i:03d}_{j:03d}", adjust, tint) for j in range(3)]
        entries.append({"type": "VariantColorTransform", "name": f"VariantColorTransform_{i:03d}", "transforms": ts})
    return {"dependencies": donor_var["dependencies"], "type": "VariantTransformTable",
            "name": f"{name}_VariantTransformTable", "entries": entries,
            "customColorShiftEntries": donor_var.get("customColorShiftEntries", [])}


DEATH_MODES = (0, 12)   # DT (State_Death) and DD (State_Dead)


def death_lacks_hth(sm: dict) -> bool:
    """True when a death state of the machine is bound to a weapon class other than hth only. D2R binds the death animation by
    the weapon class of the death COF, and Median's monsters ship their death COFs for hth only (bugs.md #34): the Amazonites'
    stand-in (cr_archer1) binds Death / Dead to bow alone, found no animation and stood in its bind pose."""
    for s in sm["states"]:
        have = {k for k, v in s["animationBindings"].items() if v}
        if s.get("modeId") in DEATH_MODES and have and "hth" not in have:
            return True
    return False


# A D2R unit's state machine binds every mode to a clip name (attack1, cast, ...) whether or not its combined.animations has that
# clip: D2R's own monster never enters a mode it has no art for, a Median monster does (darkwanderer has no attack1, so the
# robed ones it stood in for did not animate when they attacked). A missing clip is bound to the first of these the unit has.
CLIP_FALLBACK = {
    "attack1": ("attack2", "skill1", "cast"), "attack2": ("attack1", "skill1", "cast"),
    "cast": ("skill1", "attack2", "attack1"), "skill1": ("cast", "attack2", "attack1"),
    "skill2": ("skill1", "cast", "attack2", "attack1"), "skill3": ("skill1", "cast", "attack2", "attack1"),
    "skill4": ("skill1", "cast", "attack2", "attack1"),
    "gethit": ("knockback", "neutral"), "knockback": ("gethit", "neutral"), "block": ("gethit", "neutral"),
    "run": ("walk",), "walk": ("run", "neutral"), "neutral": ("walk",),
    "death": ("knockback", "gethit"), "dead": ("death", "knockback", "gethit"),
}
FILLED_MODES = {m for k, m in MODE_ID.items() if k != "SQ"}   # the plain mode states (not sequences / layers, modeId 14 / 100)


def sm_clips(sm: dict, index: dict[str, list[str]]) -> set[str] | None:
    """The clips the machine's animation folders really hold (index: folder -> clip names, tools/data/d2r_unit_clips.json);
    None when a folder is not in the index (then nothing is filled)."""
    dirs = {a["filename"].split("/animation/")[0].rsplit("/", 1)[-1] for a in sm.get("animations", [])
            if "/animation/" in a.get("filename", "")}
    if not dirs or any(d not in index for d in dirs):
        return None
    return {c.lower() for d in dirs for c in index[d]}   # clip names are matched without case (act5barb1: Fidget01)


def clip_fill(sm: dict, clips: set[str] | None) -> dict[str, str]:
    """{missing clip: clip bound instead} for the plain mode states of the machine."""
    out = {}
    if not clips:
        return out
    for s in sm["states"]:
        if s.get("modeId") not in FILLED_MODES:
            continue
        for names in s["animationBindings"].values():
            for n in names:
                if n.lower() not in clips and n not in out:
                    sub = next((f for f in CLIP_FALLBACK.get(n, ()) if f in clips), None)
                    if sub:
                        out[n] = sub
    return out


# Some machines have no state at all for a mode a Median monster uses (lane hdmon3): colbarbwhirl has no Block / Cast / Skill
# states (the Couatl fathers cast), frozenhorror1 plays its attack2 only as a skill sequence (modeId 14), so the Shardspawn's
# A2 had nothing to play. Such a mode gets a copy of the state that plays its own clip, else the first CLIP_FALLBACK clip.
STATE_FILL_MODES = {0: "death", 3: "gethit", 4: "attack1", 5: "attack2", 6: "block", 7: "cast", 8: "skill1", 9: "skill2",
                    10: "skill3", 11: "skill4", 12: "dead", 13: "knockback"}   # walk / run are often named layers (modeId 100)


def state_fill(sm: dict) -> dict[int, int]:
    """{missing modeId: stateId of the state copied for it}."""
    bound = [s for s in sm["states"] if any(s["animationBindings"].values())]
    have = {s.get("modeId") for s in bound}
    bound = [s for s in bound if "stateId" in s]
    out = {}
    for mode, clip in STATE_FILL_MODES.items():
        if mode in have:
            continue
        for want in (clip,) + CLIP_FALLBACK.get(clip, ()):
            src = next((s for s in bound if any(want in [n.lower() for n in v] for v in s["animationBindings"].values())), None)
            if src:
                out[mode] = src["stateId"]
                break
    return out


def _add_fill_states(sm: dict, fill: dict[int, int]) -> None:
    by_id = {s["stateId"]: s for s in sm["states"]}
    nid = max(by_id) + 1
    for mode, src in sorted(fill.items()):
        label = STATE_FILL_MODES[mode].capitalize()
        st = copy.deepcopy(by_id[src])
        st.update(name=f"State_{label}_Fill", _name=f"{label}_Fill", stateId=nid, modeId=mode, skillIndex=-1, stepIndex=0,
                  enterEvents=[], exitEvents=[])
        sm["states"].append(st)
        # the same transitions as the copied state: into it from every state, and out of it to every state
        groups = sm.get("transitions", [])
        for g in list(groups):
            g["settings"] += [dict(i, name=i["name"] + "_fill", to=nid) for i in g["settings"] if i["to"] == src]
            if g["from"] == src:
                groups.append(dict(copy.deepcopy(g), name=f"{label}_Fill_transitions"))
                groups[-1]["from"] = nid
        nid += 1


def adapt_state_machine(sm: dict, weapon: str | None, name: str, clips: set[str] | None = None) -> dict:
    """The donor's state machine with every state also bound for Median's weapon class (animations of the donor's), its death
    states also bound for hth (the class of Median's death COFs), and, given the clips the unit has, every plain mode state
    bound to a clip that exists (`clip_fill`); a mode with no state at all gets a copy of a state (`state_fill`)."""
    fill = clip_fill(sm, clips)
    sfill = state_fill(sm)
    sm = copy.deepcopy(sm)
    sm["name"] = name
    if sfill:
        _add_fill_states(sm, sfill)
    for s in sm["states"]:
        if fill and s.get("modeId") in FILLED_MODES:
            for wc, names in s["animationBindings"].items():
                s["animationBindings"][wc] = [fill.get(n, n) for n in names]
        ab = s["animationBindings"]
        have = {k: v for k, v in ab.items() if v}
        if have and weapon and weapon not in have:
            ab[weapon] = list(have.get("hth") or next(iter(have.values())))
        if have and s.get("modeId") in DEATH_MODES and not ab.get("hth"):
            ab["hth"] = list(next(iter(have.values())))
    return sm


def pick_variant(have: list[str], want: str) -> str:
    if want in have:
        return want
    if want in TIERS:
        ts = [v for v in have if v in TIERS]
        if ts:
            return min(ts, key=lambda v: abs(TIERS.index(v) - TIERS.index(want)))
    return have[0]


def remap_parts(dparts: dict[str, list[str]], slots: dict[str, list[str]]) -> tuple[list[tuple], list[str]]:
    """(donor part, donor variant, Median part, Median variant) rows and notes on what could not be placed.

    Median's monstats2 says which part slots a monster draws and with which variants. A donor part without a slot
    of its own goes to a slot the donor does not use (most Median monsters draw TR only: their whole body is one
    sprite), so a donor made of head/torso/legs/arms still shows complete."""
    mslots = {PARTS[c]: vs for c, vs in slots.items()}
    notes = []
    rows = []
    free = [p for p in mslots if p not in dparts and p not in WEAPON_PARTS]
    for dp, dvs in dparts.items():
        if dp in mslots:
            tgt = dp
        elif dp in WEAPON_PARTS:
            notes.append(f"{dp} dropped")
            continue
        elif free:
            tgt = free.pop(0)
        else:
            body = [p for p in mslots if p not in WEAPON_PARTS]
            if not body:
                notes.append(f"{dp} dropped")
                continue
            tgt = "torso" if "torso" in body else body[0]
        for mv in mslots[tgt]:
            rows.append((dp, pick_variant(dvs, mv), tgt, mv))
    return rows, notes


def build_unit(donor: str, name: str, slots: dict, scale: float | None, adjust, tint, weapon: str,
               sm_name: str | None, var_name: str, vmap: dict | None = None) -> tuple[dict, list[str]]:
    """UnitDefinition json (dict) for a Median monster look; (unit, notes)."""
    d = copy.deepcopy(load_json(unit_path(donor)))
    d["name"] = name
    dparts: dict[str, list[str]] = defaultdict(list)
    ents_by_key: dict[tuple, dict] = {}
    base, others = [], []
    for e in d["entities"]:
        pc = next((c for c in e["components"] if c["type"] == "UnitPartComponent"), None)
        if pc is None:
            base.append(e)
            continue
        dparts[pc["part"]].append(pc["variant"])
        ents_by_key[(pc["part"], pc["variant"])] = e
    rows, notes = remap_parts(dict(dparts), slots)
    if vmap:  # provenance: the (part, variant) the art was made from is drawn at that Median slot
        done = {(tp, tv) for tp, tv in vmap}
        rows = [r for r in rows if (r[2], r[3]) not in done] + [(sp, sv, tp, tv) for (tp, tv), (sp, sv) in vmap.items()]
    for dp, dv, tp, tv in rows:
        e = copy.deepcopy(ents_by_key[(dp, dv)])
        nm = f"entity_{tp}_{tv}_{dp}_{dv}"
        e["name"] = nm
        e["id"] = int(hashlib.md5((name + nm).encode()).hexdigest()[:8], 16)
        for c in e["components"]:
            if "part" in c:
                c["part"] = tp
            if "variant" in c:
                c["variant"] = tv
            c["name"] = c["name"].replace(f"_{dp}_{dv}", f"_{tp}_{tv}_{dp}_{dv}") if f"_{dp}_{dv}" in c["name"] else c["name"] + f"_{tp}_{tv}"
        others.append(e)
    d["entities"] = base + others
    for e in base:
        for c in e["components"]:
            if c["type"] == "UnitRootComponent" and sm_name:
                c["state_machine_filename"] = sm_name
            elif c["type"] == "VariantDefinitionComponent":
                c["filename"] = var_name
    if scale:
        root = next(e for e in base if e["name"] == "entity_root")
        tc = next((c for c in root["components"] if c["type"] == "TransformDefinitionComponent"), None)
        if tc is None:
            tc = {"type": "TransformDefinitionComponent", "name": "entity_root_TransformDefinition",
                  "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                  "scale": {"x": 1.0, "y": 1.0, "z": 1.0}, "inheritOnlyPosition": False}
            root["components"].append(tc)
        for k in "xyz":
            tc["scale"][k] = round(tc["scale"][k] * scale, 4)
    deps = d["dependencies"]
    if sm_name:
        deps["json"] = [j for j in deps["json"] if not j["path"].endswith("_state_machine.json")] + [{"path": sm_name}]
    deps["variantdata"] = [{"path": var_name}]
    return d, notes

