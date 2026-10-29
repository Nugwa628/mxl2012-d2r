"""HD stand-ins for Median XL 2012's missiles and overlays (v005 on 1.13c).

D2R draws a missile / overlay in HD from a UnitDefinition / OverlayDefinition (data/hd/missiles/<model>.json,
data/hd/overlays/<Character>/<overlay>.json; PopcornFX particles, see docs/hd-effects.md) found by the lowercased
missiles.txt / overlay.txt name. Median 2012's rows (2,665 missiles, 525 overlays; 1.13c tables) have none of those
that D2R does not already have by name. This step decides every row one by one:

  exact       the row's art file (missile CelFile / overlay Filename) is a D2R one: it gets the HD effect of the D2R row
              that uses the same art and is most like the Median row (name and skill words, speed/range/loop/hit role,
              light); art nothing in D2R draws in HD falls to stand-in
  variant     exact or stand-in effect scaled (TransformDefinitionComponent of every entity; that and the spot light are
              the only fields an HD definition has for size/colour/light, nothing for tint, transparency or speed): a
              stand-in is scaled by the ratio of Median's classic art to the stand-in's
  provenance  Median-only art that tools/art_provenance.py found to be a vanilla animation (exact, rescaled, recoloured,
              retimed or mashed up from vanilla frames): the HD effect of the D2R row that draws that vanilla art; a
              recolour keeps the effect when the colour barely moved, otherwise gets a copy of it with its gradient
              textures shifted to Median's colour (tools/hd_recolour.py); an effect without a colour gradient (or
              whose D2R vfx files are not cached) falls through
  prior       the row and its art file are the same as in the prior mapping (another port's decisions, read-only,
              from the reference checkout) and byte-identical: its stand-in is reused (--no-prior to skip)
  stand-in    the D2R effect whose classic art and row behave most alike: colour sampled from the DCC frames, size,
              frame count, moving / hit / loop role, element and shape words of the row, its art and the skills that
              reach it
  hand        a line of data/hd-effects-picks.tsv names the effect for the art (picked by eye from side-by-sides);
              wins over provenance, prior and stand-in, not over exact (D2R draws that art itself) unless the line
              names the rows it is for; its optional `tint` maps the effect's colour ramps onto a hd_recolour.RAMPS ramp
  no-art      the art file exists nowhere (1.13c would draw nothing): no effect, listed as a gap

D2R's lookup key is the name lowercased with spaces as '_' and an underscore in front of every digit run (spike1 ->
spike_1, cyclonearmor1front -> cyclonearmor_1front); both forms are written.

Inputs: Median's excel tables and DCCs (fxpaths.MXL_EXTRACT), D2R's tables, legacy DCCs and hd json (fxpaths.D2R,
read-only), work/mod/art_provenance.json (tools/art_provenance.py), the reference checkout's work/mod/effects_hd.md (read-only).
Writes (under work/mod/, gitignored): data/hd/missiles/missiles.json + mxl_*_sNN.json variants,
data/hd/overlays/<folder>/<name>.json, overlay.txt with Character = the HD folder (1.13c has 'all' / a class name there:
edited in place when txt_migrate.py made work/mod/data/global/excel, else a copy under data/global/excel/), effects_hd.md (row ->
effect), and the committed table data/hd-effects-map.tsv (art -> effect).
Usage: py -3 tools/effects_hd.py [--work DIR] [--only NAME,NAME] [--no-scale] [--no-provenance] [--no-prior]
"""
import argparse
import colorsys
import copy
import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fxpaths  # noqa: E402

ROOT = fxpaths.ROOT
D2R = fxpaths.D2R
MXL = fxpaths.MXL
HDM, HDO = D2R / "data" / "hd" / "missiles", D2R / "data" / "hd" / "overlays"
BS = chr(92)
CRLF, LF, TAB = chr(13) + chr(10), chr(10), chr(9)

# ----------------------------------------------------------------------------------------------- words
# family = element/theme (strong hint), shape = what it is (weaker hint). Matched as substrings of the name with
# separators removed, so 'violetlightning', 'blackfiresmall' and 'bluenovab' read right.
FAMILY = {
    "fire": ["fire", "flame", "burn", "inferno", "meteor", "lava", "magma", "molten", "ember", "blaze", "hellfire",
             "pyre", "scorch", "immolat", "brimstone", "firestorm"],
    "ice": ["cold", "ice", "frost", "freez", "frozen", "chill", "blizzard", "glaci", "shiver", "icicle", "arctic"],
    "elec": ["lightning", "ltng", "shock", "elec", "thunder", "static", "charged", "volt", "spark", "tesla", "fury"],
    "poison": ["poison", "venom", "toxic", "plague", "acid", "spit", "goo", "sludge", "pestil", "decay", "spore"],
    "arcane": ["magic", "arcane", "mana", "energy", "psychic", "astral", "mystic", "spell", "force", "teleport"],
    "holy": ["holy", "sacred", "bless", "smite", "divine", "paladin", "vengeance", "conviction", "sanctuary",
             "zeal", "fanat", "redempt", "hammer"],
    "bone": ["bone", "skull", "skeleton", "corpse", "grave", "undead", "revive", "ghost", "spirit", "soul",
             "wraith", "death"],
    "blood": ["blood", "gore", "vamp", "leech", "life", "drain"],
    "dark": ["shadow", "dark", "void", "abyss", "curse", "hex", "chaos", "doom", "demon", "hell", "cursed",
             "decrep", "lower", "amplify", "weaken", "confuse", "terror", "blackhole"],
    "wind": ["wind", "cyclone", "nado", "hurricane", "twister", "whirl", "gale", "storm", "tempest", "vortex"],
    "earth": ["stone", "rock", "boulder", "earth", "quake", "seism", "shatter", "debris", "chunk", "sand", "dust"],
    "nature": ["vine", "root", "plant", "briar", "thorn", "wolf", "bear", "raven", "summon", "druid", "feral",
               "nature", "heart"],
    "blade": ["blade", "sword", "spear", "arrow", "dagger", "javelin", "axe", "fist", "claw", "talon", "spike",
              "needle", "dart", "quill", "sting", "slash", "dragon"],
    "trap": ["trap", "sentry", "turret", "mine", "bomb", "grenade", "tower", "totem", "dervish"],
    "buff": ["aura", "shield", "armor", "armour", "ward", "barrier", "guard", "protect", "cast", "boost", "haste",
             "frenzy", "rage", "trance", "heal", "mend", "spiritual", "bless"],
}
SHAPE = {
    "nova": ["nova", "ring", "wave", "shockwave", "pulse", "circle"],
    "orb": ["orb", "ball", "sphere", "globe", "bubble"],
    "bolt": ["bolt", "missile", "projectile", "dart", "shot", "beam", "ray", "lance"],
    "explode": ["explo", "blast", "burst", "impact", "hit", "detonat", "boom", "splash", "shatter"],
    "trail": ["trail", "tail", "streak", "wake", "smoke", "puff", "mist", "fog", "cloud"],
    "wall": ["wall", "ground", "pool", "field", "zone", "pit", "carpet", "inferno", "nest", "circle"],
    "storm": ["storm", "rain", "fall", "shower", "swarm", "barrage", "cascade"],
    "front": ["front"], "back": ["back"],
    "small": ["small", "mini", "tiny", "little", "sm"], "large": ["large", "big", "huge", "giant", "mega", "great"],
    "cast": ["cast", "start", "charge", "channel", "ready"],
}
FAM_W, SHAPE_W, WORD_W = 1.7, 0.7, 0.4
PROV_ART_W = 1.5  # credit for the D2R effect that draws the vanilla art a Median file is a recolour of
# a recolour whose art colour is within SHIFT_MIN of the vanilla art's keeps the vanilla effect (no tint needed)
SHIFT_MIN = 0.12
# Provenance (work/mod/art_provenance.json): matches below these are not trusted over the scoring
PROV_COVER, PROV_Q, PROV_SHARE = 0.6, 0.8, 0.5
PROV_STATS: Counter = Counter()  # rows by what happened to their provenance match (the report)


def norm_key(name: str) -> str:
    """D2R's HD lookup key for a missiles.txt / overlay.txt name."""
    return re.sub(r"(?<=[^_\d])(\d+)", r"_\1", name.lower().replace(" ", "_"))


def squash(s: str) -> str:
    return re.sub(r"[^a-z]+", "", s.lower())


def words(s: str) -> set[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return {w for w in re.split(r"[^a-zA-Z]+", s.lower()) if len(w) >= 4}


def tags(*texts: str) -> tuple[set[str], set[str], set[str]]:
    fam, shp, wds = set(), set(), set()
    for t in texts:
        if not t:
            continue
        sq = squash(t)
        wds |= words(t)
        for k, stems in FAMILY.items():
            if any(s in sq for s in stems):
                fam.add(k)
        for k, stems in SHAPE.items():
            if any(s in sq for s in stems):
                shp.add(k)
    return fam, shp, wds


def norm_art(path: str) -> str:
    p = path.lower().replace("/", BS).strip()
    return p[:-4] if p.endswith(".dcc") else p


# ----------------------------------------------------------------------------------------------- D2R HD data
def check_inputs() -> None:
    """The inputs are read-only extractions made elsewhere; say which one is missing instead of guessing."""
    for p, what in ((fxpaths.MXL_EXCEL / "missiles.txt", "Median's extract (MXL_EXTRACT)"),
                    (fxpaths.D2R_EXCEL / "missiles.txt", "D2R's baseline tables (MXL_D2R_BASE)"),
                    (HDM / "missiles.json", "D2R's hd/missiles"), (HDO / "paladin" / "aura_resistfire.json", "D2R's hd/overlays"),
                    (fxpaths.PALETTE, "D2R's units palette")):
        if not p.exists():
            raise SystemExit(f"missing {p} ({what})")


# hand-picked look-alikes: CelFile (lowercase) -> D2R HD model, for classic art no D2R
# missile draws in HD
LOOKALIKE = {
    # Whirlpool's body: stationary looping blue swirl
    "coldfuse": "expansion_tornado",
    # one-frame cold bolts, velocity 14; Frozen Orb's bolts are the same kind
    "extra" + BS + "frostnova2": "ice_bolt",
}


def read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    """Header and rows of a Median table (CRLF, latin-1; short rows padded)."""
    text = path.read_bytes().decode("latin-1")
    lines = text.split(CRLF if CRLF in text[:4096] else LF)
    if lines and lines[-1] == "":
        lines.pop()
    h = lines[0].split(TAB)
    return h, [(r + [""] * len(h))[:len(h)] for r in (l.split(TAB) for l in lines[1:])]


def load_json(p: Path):
    return json.loads(p.read_text("utf-8-sig"))


# ----------------------------------------------------------------------------------------------- classic art
class ArtCache:
    def __init__(self, path: Path):
        self.path = path
        self.d = json.loads(path.read_text("utf-8")) if path.exists() else {}
        self.dirty = False
        self.pal = None
        self.files: dict[str, dict[str, Path]] = {}

    def locate(self, side: str, kind: str, rel: str) -> Path | None:
        base = (MXL if side == "mxl" else fxpaths.D2R_DATA / "global") / kind
        key = f"{side}/{kind}"
        if key not in self.files:
            self.files[key] = {p.relative_to(base).with_suffix("").as_posix().lower(): p
                               for p in base.rglob("*.dcc")} if base.exists() else {}
        return self.files[key].get(rel.replace(BS, "/").lower())

    def get(self, side: str, kind: str, rel: str) -> dict | None:
        """Statistics of direction 0 of a DCC: frames n, box w x h (classic pixels), mean colour, hue/sat/val."""
        key = f"{side}/{kind}/{rel.lower()}"
        if key in self.d:
            return self.d[key]
        p = self.locate(side, kind, rel)
        st = None
        if p is not None:
            try:
                st = self.stats(p.read_bytes())
            except Exception as e:  # undecodable art: no statistics
                print(f"   art {key}: {e}")
        self.d[key] = st
        self.dirty = True
        return st

    def stats(self, data: bytes, remap: bytes | None = None) -> dict | None:
        import dcc
        import struct
        if self.pal is None:
            self.pal = np.array(fxpaths.palette(), np.float64)
        dirs = data[2]
        fpd = struct.unpack_from("<I", data, 3)[0]
        offs = list(struct.unpack_from(f"<{dirs}I", data, 15)) + [len(data)]
        x0, y0, dw, dh, frames = dcc.decode_direction(data[offs[0]:offs[1]], fpd)
        n = len(frames)
        pick = sorted({int(i * n / 12) for i in range(12)}) if n > 12 else range(n)
        sum_rgb, sum_w = np.zeros(3), 0.0
        minx = miny = 10 ** 9
        maxx = maxy = -1
        hue_h = np.zeros(12)
        for i in range(n):
            fx, fy, fw, fh, pix = frames[i]
            a = np.frombuffer(pix, np.uint8).reshape(fh, fw)
            ys, xs = np.nonzero(a)
            if len(xs):
                minx, maxx = min(minx, fx + xs.min()), max(maxx, fx + xs.max())
                miny, maxy = min(miny, fy + ys.min()), max(maxy, fy + ys.max())
            if i in pick and len(xs):
                idx = a[ys, xs]
                rgb = self.pal[np.frombuffer(remap, np.uint8)[idx] if remap is not None else idx]
                w = rgb.max(axis=1) / 255.0
                sum_rgb += (rgb * w[:, None]).sum(axis=0)
                sum_w += w.sum()
                mx, mn = rgb.max(axis=1), rgb.min(axis=1)
                sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
                hue = _hues(rgb, mx, mn)
                np.add.at(hue_h, (hue * 12).astype(int) % 12, w * sat)
        if sum_w == 0 or maxx < 0:
            return None
        mean = sum_rgb / sum_w
        h, s, v = colorsys.rgb_to_hsv(*(mean / 255.0))
        return dict(n=n, w=int(maxx - minx + 1), h=int(maxy - miny + 1), rgb=[round(float(c)) for c in mean],
                    hsv=[round(h, 3), round(s, 3), round(v, 3)],
                    hue=[round(float(x), 1) for x in hue_h / max(1e-9, hue_h.sum()) * 100])

    def save(self) -> None:
        if self.dirty:
            self.path.write_text(json.dumps(self.d, separators=(",", ":")), "utf-8")


def _hues(rgb: np.ndarray, mx: np.ndarray, mn: np.ndarray) -> np.ndarray:
    """Hue 0..1 of (n, 3) rgb rows."""
    d = np.maximum(mx - mn, 1e-9)
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4))
    return np.where(mx == mn, 0, h / 6) % 1.0


def colour_dist(a: dict, b: dict) -> float:
    """0 (same) .. 1 (opposite): hue distance weighted by the lower saturation, plus saturation and value."""
    (h1, s1, v1), (h2, s2, v2) = a["hsv"], b["hsv"]
    dh = min(abs(h1 - h2), 1 - abs(h1 - h2)) * 2
    return min(1.0, dh * min(1.0, 1.6 * min(s1, s2)) + 0.5 * abs(s1 - s2) + 0.3 * abs(v1 - v2))


def size_of(st: dict) -> float:
    return math.sqrt(max(1, st["w"]) * max(1, st["h"]))


# ----------------------------------------------------------------------------------------------- profiles
class Prof:
    """What a missiles.txt / overlay.txt row looks like: art statistics, behaviour and the words around it."""

    def __init__(self, kind: str, name: str, art_name: str, row: dict, art: dict | None):
        self.kind, self.name, self.art_name, self.row, self.art = kind, name, art_name, row, art
        self.skills: set[str] = set()
        self.hit = self.sub = False
        self.shift = 0  # PalShift: 1.13c missiles.txt has none
        self.prov_art = ""  # the vanilla art (same kind) it was made from: its own D2R effect is a shape match
        self.prov_src = ""  # file name of the vanilla animation the art was made from (scoring words)
        self.prov_note = ""  # art_provenance said "recolour of vanilla X" but no tint was possible
        self.via = ""  # 'provenance' / 'provenance+tint' when art_provenance.json decided the effect
        self.model = ""  # D2R: the HD model
        self.folder = ""
        self._tags = None

    def num(self, col: str) -> float:
        try:
            return float(self.row.get(col) or 0)
        except ValueError:
            return 0.0

    @property
    def moving(self) -> bool:
        return max(self.num("Vel"), self.num("MaxVel")) > 0

    def words_tags(self):
        if self._tags is None:
            self._tags = tags(self.name, self.art_name.replace(BS, " "), self.prov_src, *self.skills)
        return self._tags


HIT_COLS = ["ExplosionMissile", "HitSubMissile1", "HitSubMissile2", "HitSubMissile3", "HitSubMissile4",
            "CltHitSubMissile1", "CltHitSubMissile2", "CltHitSubMissile3", "CltHitSubMissile4"]
SUB_COLS = ["SubMissile1", "SubMissile2", "SubMissile3", "CltSubMissile1", "CltSubMissile2", "CltSubMissile3"]
SKILL_MISSILE_COLS = ["srvmissile", "srvmissilea", "srvmissileb", "srvmissilec", "cltmissile", "cltmissilea",
                      "cltmissileb", "cltmissilec", "cltmissiled"]
SKILL_OVERLAY_COLS = ["srvoverlay", "sumoverlay", "tgtoverlay", "prgoverlay", "castoverlay", "cltoverlaya",
                      "cltoverlayb"]
STATE_OVERLAY_COLS = ["overlay1", "overlay2", "overlay3", "overlay4", "pgsvoverlay", "castoverlay", "removerlay"]


def table(path: Path) -> tuple[list[str], list[dict]]:
    h, rows = read_tsv(path)
    return h, [dict(zip(h, r)) for r in rows if r and r[0]]


def missile_profiles(excel: Path, side: str, art: ArtCache) -> dict[str, Prof]:
    _, rows = table(excel / "missiles.txt")
    _, skills = table(excel / "skills.txt")
    profs: dict[str, Prof] = {}
    for r in rows:
        cel = norm_art(r["CelFile"])
        st = art.get(side, "missiles", cel) if cel not in ("", "null") else None
        profs[r["Missile"].lower()] = Prof("missile", r["Missile"], cel, r, st)
    for p in profs.values():
        for c in HIT_COLS:
            t = profs.get(p.row.get(c, "").lower())
            if t:
                t.hit = True
        for c in SUB_COLS + ["CltSubMissile1"]:
            t = profs.get(p.row.get(c, "").lower())
            if t:
                t.sub = True
    # skill words flow down the missile chain (skill -> missile -> sub / hit missiles)
    todo = []
    for s in skills:
        for c in SKILL_MISSILE_COLS:
            t = profs.get(s.get(c, "").lower())
            if t and s["skill"] not in t.skills:
                t.skills.add(s["skill"])
                todo.append((t, s["skill"]))
    while todo:
        t, sk = todo.pop()
        for c in HIT_COLS + SUB_COLS + ["ProgOverlay"]:
            u = profs.get(t.row.get(c, "").lower())
            if u and sk not in u.skills and len(u.skills) < 6:
                u.skills.add(sk)
                todo.append((u, sk))
    return profs


def overlay_profiles(excel: Path, side: str, art: ArtCache) -> dict[str, Prof]:
    _, rows = table(excel / "overlay.txt")
    _, skills = table(excel / "skills.txt")
    _, states = table(excel / "states.txt")
    profs: dict[str, Prof] = {}
    for r in rows:
        if not r["overlay"] or r["overlay"] == "Expansion":
            continue
        fn = norm_art(r["Filename"])
        st = art.get(side, "overlays", fn) if fn not in ("", "null") else None
        p = Prof("overlay", r["overlay"], fn, r, st)
        p.folder = r["Character"]
        profs[r["overlay"].lower()] = p
    for s in skills:
        for c in SKILL_OVERLAY_COLS:
            t = profs.get(s.get(c, "").lower())
            if t and len(t.skills) < 6:
                t.skills.add(s["skill"])
    for s in states:
        for c in STATE_OVERLAY_COLS:
            t = profs.get(s.get(c, "").lower())
            if t and len(t.skills) < 6:
                t.skills.add(s["state"])
    return profs


# ----------------------------------------------------------------------------------------------- scoring
def log2r(a: float, b: float) -> float:
    return abs(math.log2(max(a, 1) / max(b, 1)))


def cost(m: Prof, c: Prof, same_art: bool) -> tuple[float, list[str]]:
    """Lower is closer. same_art: both rows use the same art file (colour and size are then equal)."""
    s, why = 0.0, []
    if not same_art:
        if m.art and c.art:
            cd = colour_dist(m.art, c.art)
            s += 3.0 * cd + 1.2 * min(3.0, log2r(size_of(m.art), size_of(c.art))) \
                + 0.35 * min(3.0, log2r(m.art["n"], c.art["n"]))
            why.append(f"colour {cd:.2f}")
        else:
            s += 3.0
    if m.kind == "missile":
        s += 1.5 * (m.moving != c.moving) + 1.0 * (m.hit != c.hit) + 0.5 * (m.sub != c.sub)
        s += 0.6 * ((m.row.get("LoopAnim") == "1") != (c.row.get("LoopAnim") == "1"))
        if same_art:  # same art: the closer rows are the closer movement, light and range
            s += 0.25 * min(4, log2r(max(m.num("Vel"), 1), max(c.num("Vel"), 1)))
            s += 0.2 * min(4, log2r(m.num("Range") + 1, c.num("Range") + 1))
            s += 0.15 * min(4, abs(m.num("Light") - c.num("Light")) / 3)
            s += 0.1 * (m.row.get("Trans") != c.row.get("Trans"))
    else:
        s += 0.8 * ((m.row.get("PreDraw") == "1") != (c.row.get("PreDraw") == "1"))
        s += 0.15 * min(4, abs(m.num("Height1") - c.num("Height1")) / 20)
    mf, ms, mw = m.words_tags()
    cf, cs, cw = c.words_tags()
    if m.shift:  # the name's element (fire, cold...) is the colour before the shift: no family credit
        mf = set()
    s -= FAM_W * min(3, len(mf & cf)) + SHAPE_W * min(3, len(ms & cs)) + WORD_W * min(3, len(mw & cw))
    if mf and cf and not (mf & cf):
        s += 0.8
    for opposed in (("front", "back"),):
        if (opposed[0] in ms and opposed[1] in cs) or (opposed[1] in ms and opposed[0] in cs):
            s += 1.5
    if not c.skills and not same_art:
        s += 0.4  # monster-only effects last
    if m.prov_art and c.art_name == m.prov_art and not same_art:
        s -= PROV_ART_W  # recoloured vanilla art: the effect of the vanilla original has the right shape
    return s, why


def pick(m: Prof, cands: list[Prof], same_art: bool):
    best = sorted(((cost(m, c, same_art)[0], i, c) for i, c in enumerate(cands)), key=lambda t: (t[0], t[1]))
    sc, _, c = best[0]
    margin = best[1][0] - sc if len(best) > 1 else 9.9
    return c, sc, margin, cost(m, c, same_art)[1]


# ----------------------------------------------------------------------------------------------- definitions
def scaled_definition(d: dict, name: str, k: float) -> dict:
    d = copy.deepcopy(d)
    d["name"] = name
    if k != 1:
        for e in d.get("entities", []):
            for c in e.get("components", []):
                if c["type"] == "TransformDefinitionComponent":
                    for ax in "xyz":
                        c["scale"][ax] = round(c["scale"][ax] * k, 4)
                        c["position"][ax] = round(c["position"][ax] * k, 4)
    return d


def write_json(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")


def scale_for(m: Prof, c: Prof) -> float:
    """Scale of the stand-in so it fills about the space Median's art does: ratio of the classic arts, damped."""
    if not (m.art and c.art):
        return 1.0
    ratio = size_of(m.art) / size_of(c.art)
    k = min(1.8, max(0.6, ratio ** 0.7))
    k = round(k * 10) / 10
    return 1.0 if 0.85 <= k <= 1.15 else k


def confidence(kind: str, sc: float, margin: float, ncand: int, m: Prof, c: Prof) -> str:
    """exact: sure unless several D2R models share the art and the rows hardly tell them apart. stand-in: high when
    the element/theme words agree and the colours are close, medium when one of them does."""
    if kind == "exact":
        return "high" if ncand == 1 or margin > 0.5 else "medium"
    fam = bool(m.words_tags()[0] & c.words_tags()[0])
    col = colour_dist(m.art, c.art) if m.art and c.art else 1.0
    if fam and col <= 0.25:
        return "high"
    if fam or col <= 0.25:
        return "medium"
    return "low"


# ----------------------------------------------------------------------------------------------- provenance
def load_provenance(path: Path) -> dict:
    """Median art file ('missiles/<name>', '/' separators) -> match record of tools/art_provenance.py (effects group)."""
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8")).get("effects", {}).get("files", {})


def prov_pick(prov: dict, m: Prof, by_art: dict[str, list[Prof]], folder: str, recolour):
    """The HD effect of the vanilla animation Median's art was made from. None when the art is not a vanilla animation
    with an HD effect of the same kind (missile / overlay), or when the colour changed and cannot be reproduced (the
    scoring then picks the effect of the nearest colour). Returns a dict: c (D2R row), kind, scale, conf, why, model."""
    r = prov.get(f"{folder}/{m.art_name.replace(BS, '/')}")
    if not r or r.get("category") in (None, "new", "error") or r.get("coverage", 0) < PROV_COVER:
        return None
    PROV_STATS["rows with a vanilla match"] += 1
    for s in r["sources"]:
        if s["q"] >= PROV_Q and s["share"] >= PROV_SHARE:
            m.prov_src = s["file"].rsplit("/", 1)[-1]  # a vanilla animation's name tells what the art is (any kind)
            if s["file"].startswith(folder + "/"):
                m.prov_art = s["file"][len(folder) + 1:].replace("/", BS)
            break
    for s in r["sources"]:
        if not s["file"].startswith(folder + "/") or s["q"] < PROV_Q or s["share"] < PROV_SHARE:
            continue
        rows = by_art.get(s["file"][len(folder) + 1:].replace("/", BS))
        if not rows:
            PROV_STATS["vanilla source has no HD effect"] += 1
            continue
        c, sc, margin, _ = pick(m, rows, True)
        k = 1.0
        if "rescale" in s["kind"]:
            k = min(2.5, max(0.4, round(s["scale"] * 20) / 20))
            k = 1.0 if 0.85 <= k <= 1.15 else k
        tint = None
        if "recolour" in s["kind"] and m.art and c.art and colour_dist(m.art, c.art) > SHIFT_MIN:
            tint = recolour(c, s.get("shift"), m.art, c.art, m.art_name)
            if tint is None:
                PROV_STATS["recolour not reproducible (no colour gradient, vfx not cached or larger), nearest-colour scoring"] += 1
                m.prov_note = f"art is a recolour of vanilla {s['file']} ({s['frames']} of {r['frames']} frames)"
                return None  # colour cannot be reproduced: the nearest-colour scoring decides
        what = {"exact": "exact", "recolour": "recoloured" if tint else "recoloured (colour close)",
                "rescale": "rescaled", "rescale+recolour": "rescaled, recoloured"}[s["kind"]]
        why = (f"provenance: art is {what} vanilla {s['file']} ({s['frames']} of {r['frames']} frames, q {s['q']:.2f}"
               f"{', retimed' if r.get('retime') else ''}{', mashup' if r['category'] == 'mashup' else ''}); "
               f"D2R {c.name} draws it" + (f" ({len({x.model or x.folder for x in rows})} effects)" if len(rows) > 1 else ""))
        PROV_STATS["exact" if not tint and k == 1 else "scaled" if not tint else "tinted"] += 1
        return {"c": c, "kind": "variant" if k != 1 else "exact", "scale": k, "conf": r["confidence"], "why": why,
                "tint": tint, "margin": margin}
    return None


# ----------------------------------------------------------------------------------------------- the prior mapping
_REF = fxpaths.REFERENCE  # None: no reference checkout, no prior mapping
PRIOR_ASSETS = _REF / "assets" / "median" / "data" / "global" if _REF else None
PRIOR_REPORT = _REF / "work" / "mod" / "effects_hd.md" if _REF else None
PRIOR_VARIANT = re.compile(r"^mxl_(?P<base>.+)_s(?P<pct>\d+)$")
PRIOR_TINT = re.compile(r"^mxl_.+_c[0-9a-f]{6}$")


class Prior:
    """The prior mapping's decisions: by row name and by art file."""

    def __init__(self, rows: dict[tuple[str, str], dict]):
        self.rows = rows
        self.by_art: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for (kind, _), r in rows.items():
            self.by_art[(kind, r["art"])].append(r)


def adoptable(r: dict) -> bool:
    """A prior decision we can rebuild: its own stand-in (or scaled exact), not a gradient-tinted copy."""
    return (r["cls"] in ("stand-in", "variant") and r["effect"] not in ("", "null") and not PRIOR_TINT.match(r["effect"])
            and "palette shift" not in r["why"])  # v005's 1.13c tables have no PalShift: those were chosen by shifted colour


def load_prior(path: Path | None) -> Prior:
    """The rows of the prior mapping's work/mod/effects_hd.md: kind, row, art, effect, scale, class, confidence, why."""
    out: dict[tuple[str, str], dict] = {}
    if path is not None and path.exists():
        for line in path.read_text("utf-8").splitlines():
            if not (line.startswith("| missile |") or line.startswith("| overlay |")):
                continue
            f = [x.strip() for x in line.strip().strip("|").split(" | ")]
            if len(f) >= 8:
                out[(f[0], f[1].lower())] = dict(art=f[2].lower(), effect=f[3], scale=float(f[4]), cls=f[5], conf=f[6],
                                                 why=" | ".join(f[7:]), row=f[1])
    return Prior(out)


def prior_art_state(kind: str, art: str, mod_file: Path | None, where: str) -> str:
    """The prior set against this art: 'base' (base-game art, the same D2R file), 'identical' / 'differs' (same file
    name in the prior assets, same / other bytes), 'absent', or 'n/a' (no art)."""
    if where == "base":
        return "base"
    if mod_file is None:
        return "n/a"
    if PRIOR_ASSETS is None:
        return "absent"
    p = PRIOR_ASSETS / kind / (art.replace(BS, "/") + ".dcc")
    if not p.exists():
        return "absent"
    same = hashlib.sha1(p.read_bytes()).digest() == hashlib.sha1(mod_file.read_bytes()).digest()
    return "identical" if same else "differs"


def prior_pick(sis: Prior, kind: str, m: Prof, state: str, by_effect: dict[str, Prof]):
    """The prior effect for this art when its file is the same (base-game art or byte-identical Median file): its choice
    for the row of the same name, else the one of its choices for that art that is closest to this row (cost()).
    Returns (Prof, scale, conf, why) or None (no adoptable choice, or the prior one was a tinted copy)."""
    if state not in ("base", "identical"):
        return None
    r = sis.rows.get((kind, m.name.lower()))
    cand = [r] if r is not None and r["art"] == m.art_name and adoptable(r) else         [x for x in sis.by_art.get((kind, m.art_name), []) if adoptable(x)]
    opts: dict[tuple[str, float], tuple[Prof, dict]] = {}
    for x in cand:
        var = PRIOR_VARIANT.match(x["effect"])
        c = by_effect.get(var["base"] if var else x["effect"])
        if c is not None:
            opts.setdefault((c.model or f"{c.folder}/{norm_key(c.name)}", x["scale"]), (c, x))
    if not opts:
        return None
    (c, x) = min(opts.values(), key=lambda t: cost(m, t[0], False)[0])
    same = r is not None and x is r
    scale = next(k[1] for k, v in opts.items() if v[1] is x)
    return c, scale, x["conf"], (f"the prior choice for the {'same row' if same else 'same art'} ({len(cand)} of its rows, "
                                  f"{len(opts)} effects{'' if same else '; the closest to this row'}): {x['why']}")


PRIOR_ART_FIX = _REF / "work" / "mod" / "art_fix.md" if _REF else None


def load_art_fix(path: Path | None) -> dict[tuple[str, str], str]:
    """(kind, art name as the table spells it, lowercase) -> the D2R art the prior art_fix.py points it at.
    Median names art that exists nowhere; 1.13c then draws nothing. This is only a suggestion, never applied."""
    out: dict[tuple[str, str], str] = {}
    if path is not None and path.exists():
        for line in path.read_text("utf-8").splitlines():
            f = [x.strip().strip("`") for x in line.strip().strip("|").split(" | ")]
            if len(f) >= 5 and f[0] in ("missiles", "overlay") and f[4] in ("redirected", "repaired"):
                out.setdefault(("missile" if f[0] == "missiles" else "overlay", f[2].lower()), f[3])
    return out


PICK_COLS = ["kind", "art", "effect", "scale", "confidence", "reason"]
PICK_OPT = ["tint", "rows"]  # optional (lane picktint): a ramp of hd_recolour.RAMPS; the only rows the line is for


def load_picks(path: Path | None) -> dict[tuple, dict]:
    """data/hd-effects-picks.tsv: (kind, art as norm_art) -> effect, scale (None = by art size), confidence, reason, tint
    ('' = none). A line with `rows` is keyed (kind, art, row) per row (lowercase) and wins over the art's own line for
    those rows, also where D2R draws the art itself (exact)."""
    import hd_recolour as hr
    out: dict[tuple, dict] = {}
    if path is None or not path.exists():
        return out
    for n, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split(TAB)
        if f in (PICK_COLS, PICK_COLS + PICK_OPT[:1], PICK_COLS + PICK_OPT):
            continue
        if not len(PICK_COLS) <= len(f) <= len(PICK_COLS) + len(PICK_OPT):
            raise SystemExit(f"{path}:{n}: {len(f)} columns, want {len(PICK_COLS)} ({', '.join(PICK_COLS)}) "
                             f"and optionally {', '.join(PICK_OPT)}")
        kind, art, effect, scale, conf, why, tint, rows = (x.strip() for x in f + [""] * (len(PICK_COLS) + len(PICK_OPT) - len(f)))
        if kind not in ("missile", "overlay") or not effect or conf not in ("high", "medium", "low") or not why:
            raise SystemExit(f"{path}:{n}: bad line (kind missile/overlay, an effect, confidence high/medium/low, a reason)")
        try:
            hr.parse_tint(tint)
        except ValueError as ex:
            raise SystemExit(f"{path}:{n}: {ex}")
        hp = dict(effect=effect, scale=None if scale in ("", "auto") else float(scale), conf=conf, why=why, tint=tint,
                  rows=tuple(r.strip().lower() for r in rows.split(",") if r.strip()), line=n)
        for key in ([(kind, norm_art(art), r) for r in hp["rows"]] or [(kind, norm_art(art))]):
            if key in out:
                raise SystemExit(f"{path}:{n}: {kind} {art}{' row ' + key[2] if len(key) > 2 else ''} picked twice")
            out[key] = hp
    return out


def pick_line(picks: dict, kind: str, m: "Prof") -> dict | None:
    """The pick of m: the line for its row, else the line for its art."""
    return picks.get((kind, m.art_name, m.name.lower())) or picks.get((kind, m.art_name))


def hand_pick(picks: dict, kind: str, m: "Prof", cands: list["Prof"], no_scale: bool):
    """The hand-picked effect of m's art: (D2R profile it stands for, scale, confidence, why), None without a pick.
    cands: the D2R profiles that draw the picked effect (an unknown effect is an error, not a silent fall-through)."""
    hp = pick_line(picks, kind, m)
    if hp is None:
        return None
    if not cands:
        raise SystemExit(f"data/hd-effects-picks.tsv line {hp['line']}: {kind} {m.art_name}: D2R has no effect {hp['effect']!r}")
    c = pick(m, cands, False)[0]
    scale = 1.0 if no_scale else (hp["scale"] if hp["scale"] is not None else scale_for(m, c))
    return c, scale, hp["conf"], f"hand pick (data/hd-effects-picks.tsv): {hp['why']}; D2R {c.name} ({c.art_name})"


def no_tint(*_args, **_kw):
    """--no-tint: no gradient tint (a recolour falls through to the nearest-colour scoring, a pick stays untinted)."""
    return None


# ----------------------------------------------------------------------------------------------- main
def no_art_why(fixes: dict, kind: str, m: Prof) -> str:
    sug = fixes.get((kind, m.art_name))
    return ("art file exists nowhere (not in patch_d2.mpq, not in the base game): 1.13c draws nothing"
            + (f"; the prior art_fix.py points it at D2R's {sug} (suggestion, not applied)" if sug else ""))


def art_exists(art: ArtCache, kind: str, art_name: str) -> str:
    """Where the art file is: 'mod' (Median's patch_d2.mpq), 'base' (the base game, D2R ships it), '' (nowhere)."""
    if art_name in ("", "null"):
        return ""
    if art.locate("mxl", kind, art_name):
        return "mod"
    return "base" if art.locate("d2r", kind, art_name) else ""


def write_overlay_character(out: Path, mod_excel: Path, chars: dict[str, str]) -> int:
    """overlay.txt with Character = the HD folder. 1.13c has 'all' / a class name there (D2R: the folder of the HD
    overlay definition), so the column is wrong for every row. Tables made by txt_migrate.py (work/mod/data/global/excel,
    both banks) are edited in place, Median's own table is left alone and a copy goes under <out>/global/excel/."""
    dest_dir = out / "global" / "excel"
    in_place = mod_excel.resolve() == dest_dir.resolve()
    if in_place:
        targets = [(p, p) for p in (dest_dir / "overlay.txt", dest_dir / "base" / "overlay.txt") if p.exists()]
    else:
        targets = [(mod_excel / "overlay.txt", dest_dir / "overlay.txt")]
    n = 0
    for src, dest in targets:
        text = src.read_bytes().decode("latin-1")
        nl = CRLF if CRLF in text[:4096] else LF
        h, rows = read_tsv(src)
        ci, ni = h.index("Character"), h.index("overlay")
        n = 0
        for r in rows:
            want = chars.get(r[ni].lower())
            if want is not None and r[ci] != want:
                r[ci], n = want, n + 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((nl.join(TAB.join(x) for x in [h] + rows) + nl).encode("latin-1"))
    return n


MAP_COLS = ["kind", "art", "art_in", "provenance", "rows", "class", "effect", "scale", "confidence", "effects",
            "prior_file", "prior_effect", "reason"]
CLASS_ORDER = {"hand": -1, "stand-in": 0, "prior": 1, "provenance": 2, "exact": 3, "variant": 4, "no-art": 5, "unreferenced": 6}


def art_table(results: list[dict], files: dict[str, dict[str, Path]], prov: dict, sis: Prior,
              art_state: dict[tuple[str, str], str]) -> list[list[str]]:
    """One line per art file (a missile CelFile / an overlay Filename): the decision most of its rows took."""
    by_art: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in results:
        by_art[(r["kind"], r["art"])].append(r)
    lines = []
    for (kind, a), rows in by_art.items():
        folder = "missiles" if kind == "missile" else "overlays"
        if a in ("", "null"):
            continue
        dom = Counter((r["effect"], r["scale"]) for r in rows).most_common(1)[0][0]
        r0 = next(r for r in rows if (r["effect"], r["scale"]) == dom)
        pv = prov.get(f"{folder}/{a.replace(BS, '/')}")
        pvs = ""
        if pv and pv.get("category") == "new":
            pvs = "new"
        elif pv and pv.get("category") not in (None, "error") and pv.get("sources"):
            s0 = pv["sources"][0]
            pvs = f"{pv['category']}: {s0['kind']} of {s0['file'].split('/', 1)[-1]}"
        sr = Counter(x["effect"] for x in sis.by_art.get((kind, a), []))
        none = r0["cls"] == "no-art"
        lines.append([kind, a.replace(BS, "/"), r0["art_in"], pvs, str(len(rows)), r0["cls"], r0["effect"],
                      "" if none else f"{r0['scale']:g}", r0["conf"],
                      "0" if none else str(len({(r['effect'], r['scale']) for r in rows})),
                      art_state.get((kind, a), "n/a"), sr.most_common(1)[0][0] if sr else "", r0["why"].replace("\t", " ")])
    used = set(by_art)
    for kind, fl in (("missile", files["missiles"]), ("overlay", files["overlays"])):
        for a in fl:
            if (kind, a.replace("/", BS)) not in used:
                pv = prov.get(f"{'missiles' if kind == 'missile' else 'overlays'}/{a}")
                lines.append([kind, a, "mod", (pv or {}).get("category", ""), "0", "unreferenced", "", "", "", "0",
                              art_state.get((kind, a.replace("/", BS)), "n/a"), "",
                              "no missiles.txt / overlay.txt row uses this file"])
    lines.sort(key=lambda l: (l[0], CLASS_ORDER.get(l[5], 9), l[1]))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--work", default=str(fxpaths.MOD), help="work dir with data/ (default work/mod)")
    ap.add_argument("--only", help="comma separated row names (missiles and overlays)")
    ap.add_argument("--no-scale", action="store_true")
    ap.add_argument("--no-provenance", action="store_true", help="skip tools/art_provenance.py matches")
    ap.add_argument("--no-prior", action="store_true", help="do not reuse the prior mapping's per-row decisions")
    ap.add_argument("--no-tint", action="store_true", help="no gradient tint of recoloured vanilla effects (hd_recolour.py)")
    ap.add_argument("--map", default=str(fxpaths.MAP_TSV), help="art -> effect table (default data/hd-effects-map.tsv)")
    ap.add_argument("--picks", default=str(fxpaths.PICKS_TSV), help="hand-picked effects (default data/hd-effects-picks.tsv; '' for none)")
    args = ap.parse_args()
    work = Path(args.work)
    out = work / "data"
    only = {x.lower() for x in args.only.split(",")} if args.only else None
    check_inputs()
    prov = {} if args.no_provenance else load_provenance(work / "art_provenance.json")
    if not args.no_provenance and not prov:
        print("no art_provenance.json: run tools/art_provenance.py for exact-art matches")
    sis = Prior({}) if args.no_prior else load_prior(PRIOR_REPORT)
    fixes = {} if args.no_prior else load_art_fix(PRIOR_ART_FIX)
    art = ArtCache(fxpaths.WORK / "effects_hd_art.json")
    picks = load_picks(Path(args.picks) if args.picks else None)
    d2r_excel, mod_excel = fxpaths.D2R_EXCEL, fxpaths.TABLES

    import hd_recolour as hr
    hr.clean(work / "hd_recolour.json", out)
    tint_m = no_tint if args.no_tint else hr.plan_missile(HDM)
    tint_o = no_tint if args.no_tint else hr.plan_overlay(HDO, norm_key)
    tint_pm = no_tint if args.no_tint else hr.plan_pick_missile(HDM)  # a hand pick's `tint` column
    tint_po = no_tint if args.no_tint else hr.plan_pick_overlay(HDO)
    tinted: dict[tuple[str, str], str] = {}  # (D2R model, tag) -> recoloured model
    recolours: list[dict] = []

    def tint_missile(model: str, spec: dict, row: str, src_row: str) -> str:
        key = (model, hr.tag_of(spec))
        if key not in tinted:
            nd = hr.recolour_missile(out, model, spec, HDM)
            write_json(out / "hd" / "missiles" / f"{nd['name']}.json", nd)
            hr.WRITTEN[f"data/hd/missiles/{nd['name']}.json"] = f"data/hd/missiles/{model}.json"
            tinted[key] = nd["name"]
            recolours.append({"kind": "missile", "from": model, "src_row": src_row, "to": nd["name"], "shift": spec["label"],
                              "rows": []})
        next(r for r in recolours if r["to"] == tinted[key])["rows"].append(row)
        return tinted[key]

    d2r_hd_m = load_json(HDM / "missiles.json")
    deps = d2r_hd_m.pop("dependencies", None)
    hd_m = dict(d2r_hd_m)
    hdo_files = {p.relative_to(HDO).with_suffix("").as_posix().lower() for p in HDO.rglob("*.json")
                 if "/" in p.relative_to(HDO).as_posix()}
    results: list[dict] = []  # one per Median row that needs an effect of ours
    art_state: dict[tuple[str, str], str] = {}

    def res(kind, m, cls, effect, scale, conf, why, c=None, art_in=""):
        results.append(dict(kind=kind, name=m.name, art=m.art_name, art_in=art_in, cls=cls, effect=effect,
                            scale=scale, conf=conf, why=why, m=m, c=c))

    def state(kind: str, m: Prof) -> str:
        k = (kind, m.art_name)
        if k not in art_state:
            folder = "missiles" if kind == "missile" else "overlays"
            art_state[k] = prior_art_state(folder, m.art_name, art.locate("mxl", folder, m.art_name),
                                            (where_m if kind == "missile" else where_o).get(m.art_name, ""))
        return art_state[k]

    # ---------------------------------------------------------------- missiles
    dm, mm = missile_profiles(d2r_excel, "d2r", art), missile_profiles(mod_excel, "mxl", art)
    where_m: dict[str, str] = {}
    for p in mm.values():
        if p.art_name not in where_m:
            where_m[p.art_name] = art_exists(art, "missiles", p.art_name)
        if p.art is None and where_m[p.art_name] == "base":  # base-game art: the D2R copy is the one drawn
            p.art = art.get("d2r", "missiles", p.art_name)
    by_art: dict[str, list[Prof]] = defaultdict(list)
    by_model: dict[str, Prof] = {}
    for p in dm.values():
        if norm_key(p.name) in d2r_hd_m and d2r_hd_m[norm_key(p.name)] != "null":
            p.model = d2r_hd_m[norm_key(p.name)]
            by_art[p.art_name].append(p)
            by_model.setdefault(p.model, p)
    library = [p for p in dm.values() if p.model and p.art and p.art_name not in ("", "null")]
    d2r_arts = {p.art_name for p in dm.values()}
    changed_vanilla = {norm_key(n) for n, m in mm.items() if n in dm and dm[n].art_name != m.art_name}
    new_models: dict[str, tuple[str, float]] = {}  # variant model name -> (base model, scale)
    keys: dict[str, str] = {}
    raw: dict[str, str] = {}
    n_own_m = 0
    for name, m in mm.items():
        if only and name not in only:
            continue
        v = dm.get(name)
        if v is not None and v.art_name == m.art_name and norm_key(name) in d2r_hd_m:
            n_own_m += 1
            continue  # D2R's own missile with D2R's art and HD effect
        c, art_in = None, where_m[m.art_name]
        if m.art_name in ("", "null"):
            model, cls, scale, conf, why = "null", "exact", 1.0, "high", "no art (logic missile)"
        elif not art_in:
            res("missile", m, "no-art", "", 1.0, "", no_art_why(fixes, "missile", m), art_in="missing")
            continue
        else:
            src = by_art.get(m.art_name)
            hpl = pick_line(picks, "missile", m)
            if src and not (hpl and hpl["rows"]):  # a pick for the row wins over D2R's own art
                c, sc, margin, _ = pick(m, src, True)
                cls, scale, model = "exact", 1.0, c.model
                conf = confidence("exact", sc, margin, len({s.model for s in src}), m, c)
                nm = len({s.model for s in src})
                why = f"D2R {c.name} uses the art" + (f" ({nm} models)" if nm > 1 else "")
            elif (hp := hand_pick(picks, "missile", m, [p for p in dm.values() if p.model == (hpl or {}).get("effect")],
                                  args.no_scale)):
                c, scale, conf, why = hp
                cls, model = "hand", c.model
                if hpl["tint"]:
                    spec = tint_pm(model, hpl["tint"])
                    if spec:
                        model = tint_missile(model, spec, name, c.name)
                        why += f"; gradient tint {spec['label']}"
                    else:
                        why += f"; tint {hpl['tint']} not made (--no-tint, no such gradient, or the D2R vfx files not cached)"
            elif (pv := prov_pick(prov, m, by_art, "missiles", tint_m)):
                c, scale, conf, why, model = pv["c"], pv["scale"], pv["conf"], pv["why"], pv["c"].model
                cls = "provenance"
                if pv["tint"]:
                    model = tint_missile(model, pv["tint"], name, c.name)
                    why += f"; gradient tint {pv['tint']['label']}"
                if args.no_scale:
                    scale = 1.0
            elif (sp := prior_pick(sis, "missile", m, state("missile", m), by_model)):
                c, scale, conf, why = sp
                cls, model = "prior", c.model
                if args.no_scale:
                    scale = 1.0
            else:
                hand = [p for p in library if p.model == LOOKALIKE.get(m.art_name)]
                c, sc, margin, parts = pick(m, hand or library, False)
                scale = 1.0 if args.no_scale else scale_for(m, c)
                cls, model = "stand-in", c.model
                conf = "high" if hand else confidence("stand-in", sc, margin, len(library), m, c)
                parts = (["hand-picked look-alike"] if hand else []) + parts
                if m.prov_note:
                    parts = [m.prov_note + "; no gradient tint, colour chosen by scoring"] + parts
                has_d2r_art = m.art_name in d2r_arts
                why = (f"{'base-game art without a D2R HD effect' if has_d2r_art else 'Median-only art'}; like D2R {c.name} "
                       f"({c.art_name}); score {sc:.1f}, margin {margin:.1f}; " + ", ".join(parts))
            if scale != 1:
                vname = f"mxl_{model}_s{round(scale * 100)}"
                new_models[vname] = (model, scale)
                model = vname
        res("missile", m, cls, model, scale, conf, why, c, art_in=art_in)
        keys[norm_key(name)] = model
        raw[name.lower()] = model
    for vname, (base, k) in new_models.items():
        src = HDM / f"{base}.json"
        if base in tinted.values():
            src = out / "hd" / "missiles" / f"{base}.json"
        write_json(out / "hd" / "missiles" / f"{vname}.json", scaled_definition(load_json(src), vname, k))
    final = dict(hd_m)
    kept = 0
    for key, model in {**{k: v for k, v in raw.items() if k not in keys}, **keys}.items():
        if key in d2r_hd_m and d2r_hd_m[key] != model and key not in changed_vanilla:
            kept += 1  # a Median name that normalises onto a D2R key: D2R's effect stays
            continue
        final[key] = model
    if deps is not None:
        final = {"dependencies": deps, **final}
    write_json(out / "hd" / "missiles" / "missiles.json", final)
    for r in recolours:  # Median rows that draw the untinted source effect (a side-by-side look, check tint_hd)
        r["src_rows"] = [n for n in mm if final.get(norm_key(n)) == r["from"]][:5]
    n_missile_rows = len(results)
    stats_m = Counter(PROV_STATS)

    # ---------------------------------------------------------------- overlays
    do, mo = overlay_profiles(d2r_excel, "d2r", art), overlay_profiles(mod_excel, "mxl", art)
    where_o: dict[str, str] = {}
    for p in mo.values():
        if p.art_name not in where_o:
            where_o[p.art_name] = art_exists(art, "overlays", p.art_name)
        if p.art is None and where_o[p.art_name] == "base":
            p.art = art.get("d2r", "overlays", p.art_name)
    by_file: dict[str, list[Prof]] = defaultdict(list)
    by_effect: dict[str, Prof] = {}
    for p in do.values():
        if f"{p.folder}/{norm_key(p.name)}".lower() in hdo_files:
            by_file[p.art_name].append(p)
            by_effect.setdefault(f"{p.folder}/{norm_key(p.name)}", p)
    olib = [p for p in do.values() if f"{p.folder}/{norm_key(p.name)}".lower() in hdo_files and p.art and p.art_name]
    d2r_oarts = {p.art_name for p in do.values()}
    chars: dict[str, str] = {}  # overlay name -> Character (HD folder)
    n_own_o = 0
    for name, m in mo.items():
        if only and name not in only:
            continue
        v = do.get(name)
        if v is not None and v.art_name == m.art_name:
            n_own_o += 1  # D2R's own overlay: D2R's own HD folder is the Character
            if f"{v.folder}/{norm_key(v.name)}".lower() in hdo_files:
                chars[name] = v.folder
            continue
        art_in = where_o[m.art_name]
        if m.art_name in ("", "null"):
            res("overlay", m, "exact", "", 1.0, "high", "no art", None, art_in="")
            continue
        if not art_in:
            res("overlay", m, "no-art", "", 1.0, "", no_art_why(fixes, "overlay", m), art_in="missing")
            continue
        src = by_file.get(m.art_name)
        hpl, ptint = pick_line(picks, "overlay", m), None
        if src and not (hpl and hpl["rows"]):
            c, sc, margin, _ = pick(m, src, True)
            cls, scale, conf = "exact", 1.0, confidence("exact", sc, margin, len(src), m, c)
            why = f"D2R {c.name} uses the art"
        elif (hp := hand_pick(picks, "overlay", m, [p for p in do.values() if f"{p.folder}/{norm_key(p.name)}".lower()
                                                     == (hpl or {}).get("effect", "").lower()],
                              args.no_scale)):
            c, scale, conf, why = hp
            cls = "hand"
            if hpl["tint"]:
                ptint = tint_po(f"{c.folder}/{norm_key(c.name)}", hpl["tint"])
                why += (f"; gradient tint {ptint['label']}" if ptint else
                        f"; tint {hpl['tint']} not made (--no-tint, no such gradient, or the D2R vfx files not cached)")
        elif (pv := prov_pick(prov, m, by_file, "overlays", tint_o)):
            c, scale, conf, why = pv["c"], pv["scale"], pv["conf"], pv["why"]
            cls = "provenance"
            if pv["tint"]:
                why += f"; gradient tint {pv['tint']['label']}"
            if args.no_scale:
                scale = 1.0
        elif (sp := prior_pick(sis, "overlay", m, state("overlay", m), by_effect)):
            c, scale, conf, why = sp
            cls = "prior"
            if args.no_scale:
                scale = 1.0
        else:
            c, sc, margin, parts = pick(m, olib, False)
            scale = 1.0 if args.no_scale else scale_for(m, c)
            cls, conf = "stand-in", confidence("stand-in", sc, margin, len(olib), m, c)
            if m.prov_note:
                parts = [m.prov_note + "; no gradient tint, colour chosen by scoring"] + parts
            has_d2r_art = m.art_name in d2r_oarts
            why = (f"{'base-game art without a D2R HD effect' if has_d2r_art else 'Median-only art'}; like D2R {c.name} "
                   f"({c.art_name}); score {sc:.1f}, margin {margin:.1f}; " + ", ".join(parts))
        res("overlay", m, cls, f"{c.folder}/{norm_key(c.name)}", scale, conf, why, c, art_in=art_in)
        d = scaled_definition(load_json(HDO / c.folder / f"{norm_key(c.name)}.json"), norm_key(name), scale)
        spec = ptint if cls == "hand" else pv["tint"] if cls == "provenance" else None
        if spec:
            d = hr.recolour_overlay(out, d, spec)
            hr.WRITTEN[f"data/hd/overlays/{c.folder}/{norm_key(name)}.json"] = f"data/hd/overlays/{c.folder}/{norm_key(c.name)}.json"
            recolours.append({"kind": "overlay", "from": f"{c.folder}/{norm_key(c.name)}", "to": norm_key(name),
                              "shift": spec["label"], "rows": [name]})
        write_json(out / "hd" / "overlays" / c.folder / f"{norm_key(name)}.json", d)
        chars[name] = c.folder
    n_char = write_overlay_character(out, mod_excel, chars) if not only else 0

    # ---------------------------------------------------------------- reports
    files = {k: {p.relative_to(fxpaths.MXL / k).with_suffix("").as_posix().lower(): p
                 for p in (fxpaths.MXL / k).rglob("*.dcc")} for k in ("missiles", "overlays")}
    rows_m, rows_o = results[:n_missile_rows], results[n_missile_rows:]
    rep = ["# HD effects of Median XL 2012's missiles and overlays (tools/effects_hd.py)", "",
           f"Missile rows {len(mm)}: {n_own_m} are D2R's own (same name and art, D2R's HD effect stays), {len(rows_m)} "
           f"decided here. Overlay rows {len(mo)}: {n_own_o} D2R's own, {len(rows_o)} decided here. "
           f"overlay.txt Character rewritten on {n_char} rows (1.13c: 'all' / a class name).", ""]
    for label, rows in (("Missiles", rows_m), ("Overlays", rows_o)):
        kinds = Counter(r["cls"] for r in rows)
        confs = Counter((r["cls"], r["conf"]) for r in rows)
        rep += [f"## {label}: {len(rows)} rows", "", "| Class | Rows | high | medium | low |", "|---|---|---|---|---|"]
        for k in ("exact", "hand", "provenance", "prior", "variant", "stand-in", "no-art"):
            rep.append(f"| {k} | {kinds.get(k, 0)} | {confs.get((k, 'high'), 0)} | {confs.get((k, 'medium'), 0)} | "
                       f"{confs.get((k, 'low'), 0)} |")
        scaled = sum(1 for r in rows if r["cls"] in ("stand-in", "prior", "provenance", "hand") and r["scale"] != 1)
        rep += ["", f"Scaled to Median's art size: {scaled}.", ""]
        st = stats_m if label == "Missiles" else PROV_STATS - stats_m
        if prov:
            rep += ["Provenance (tools/art_provenance.py): " + ", ".join(f"{k} {v}" for k, v in sorted(st.items())) + ".", ""]
    rep += ["## Gradient tints (tools/hd_recolour.py)", "",
            f"{len(recolours)} recoloured effects for {sum(len(r['rows']) for r in recolours)} rows; D2R vfx files missing: "
            f"{len(hr.MISSING)}; too large: {len(set(hr.TOO_LARGE))}. Files written: {len(hr.WRITTEN)}.", "",
            "| Kind | D2R effect | Recoloured | Shift | Rows |", "|---|---|---|---|---|"]
    rep += [f"| {r['kind']} | {r['from']} | {r['to']} | {r['shift']} | {', '.join(r['rows'])} |" for r in recolours]
    rep += [""]
    rep += ["## Rows", "", "| Kind | Row | Art | HD effect | Scale | Class | Confidence | Why |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda r: (r["kind"], r["cls"], r["conf"], r["name"])):
        rep.append(f"| {r['kind']} | {r['name']} | {r['art']} | {r['effect']} | {r['scale']:g} | {r['cls']} | {r['conf']} | "
                   f"{r['why'].replace('|', '/')} |")
    work.mkdir(parents=True, exist_ok=True)
    (work / "effects_hd.md").write_text("\n".join(rep) + "\n", encoding="utf-8")
    table_lines = art_table(results, files, prov, sis, art_state)
    if not only:
        Path(args.map).parent.mkdir(parents=True, exist_ok=True)
        Path(args.map).write_text("\n".join("\t".join(l) for l in [MAP_COLS] + table_lines) + "\n", encoding="utf-8")
    art.save()
    tint_bytes, tint_larger = hr.write_report(work / "hd_recolour.json", recolours, out)
    km, ko = Counter(r["cls"] for r in rows_m), Counter(r["cls"] for r in rows_o)
    print(f"missiles {len(rows_m)} (+{n_own_m} D2R's own): {dict(km)}; overlays {len(rows_o)} (+{n_own_o}): {dict(ko)}; "
          f"{len(new_models)} scaled missile models; {len(recolours)} gradient tints ({len(hr.WRITTEN)} files, {tint_bytes} bytes, "
          f"{len(tint_larger)} larger than D2R's, {len(hr.MISSING)} vfx files missing); "
          f"{len(table_lines)} art files in the table; "
          f"report -> {work / 'effects_hd.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
