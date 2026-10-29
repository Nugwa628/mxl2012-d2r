"""Donor choice for D2R-XL 2012: family tags, art statistics, donor scoring, colour fit, vanilla-unit pick.

Art is read from the extracted 2012 MPQ and from the reference checkout's cached statistics of D2R's classic art
(no CASC / game-install access), the provenance matcher is not
used (its tool, tools/art_provenance.py, is not part of this repo yet), names come from the monstats NameStr key.
"""
import colorsys
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hd_units  # noqa: E402
from hd_units import MODE_ID, MODES, PART_CODES, load_json, unit_info, variants_cell  # noqa: E402

# ------------------------------------------------------------------ classic art statistics
MXL_MON: Path | None = None   # extracted 2012 MPQ: data/global/monsters
PALETTE: Path | None = None   # D2R baseline data/global/palette/units/pal.dat (BGR)


def configure(mxl_monsters: Path, d2r_root: Path) -> None:
    global MXL_MON, PALETTE
    MXL_MON = Path(mxl_monsters)
    PALETTE = Path(d2r_root) / "data" / "global" / "palette" / "units" / "pal.dat"
    hd_units.configure(d2r_root)


def bare(ref: str) -> str:
    """`mxl2012:<key>` -> `<key>`; other values unchanged (same rule as strings_ns.bare)."""
    return ref.split(":", 1)[1] if ref.startswith("mxl2012:") else ref


def split_variants(v: str) -> list[str]:
    return hd_units.split_variants(v)


slots_of = hd_units.slots_of
modes_of = hd_units.modes_of


class Art:
    """Colour histogram (palette indices) + box of a monster's frame 0, direction 0 of mode NU (2012 art only: the D2R
    side is served from the cached statistics, see ArtCache)."""

    def __init__(self):
        import dcc
        self.dcc = dcc
        d = PALETTE.read_bytes()
        self.pal = [(d[i * 3 + 2], d[i * 3 + 1], d[i * 3]) for i in range(256)]  # stored BGR

    def read(self, side: str, rel: str) -> bytes | None:
        if side != "mxl":
            return None
        p = MXL_MON / rel
        if p.exists():
            return p.read_bytes()
        q = MXL_MON / rel.lower()
        return q.read_bytes() if q.exists() else self._ci(rel)

    _dirs: dict = {}
    
    def _ci(self, rel: str) -> bytes | None:
        d, _, f = rel.rpartition("/")
        key = d.lower()
        if key not in self._dirs:
            base = MXL_MON / d
            self._dirs[key] = {x.name.lower(): x for x in base.iterdir()} if base.exists() else {}
        p = self._dirs[key].get(f.lower())
        return p.read_bytes() if p else None

    def palshift(self, side: str, code: str) -> list[list[int]] | None:
        b = self.read(side, f"{code}/cof/palshift.dat")
        if not b or len(b) < 2048:
            return None
        return [list(b[i * 256:(i + 1) * 256]) for i in range(8)]

    def stats(self, side: str, code: str, row2: dict, weapon: str) -> dict | None:
        """{hist: 256 counts, box: (x0, y0, x1, y1)} over the monster's parts, first listed variants."""
        hist = [0] * 256
        box = None
        n = 0
        for pc in PART_CODES:
            if row2.get(pc) != "1":
                continue
            variants = [v for v in re.split(r"[,\s]+", variants_cell(row2, pc).strip('"')) if v and v != "nil"]
            seen = []
            for v in variants:
                if v in seen:
                    continue
                seen.append(v)
            tried = False
            for v in seen[:3]:
                for w in dict.fromkeys([weapon, "hth"]):
                    b = self.read(side, f"{code}/{pc.lower()}/{code}{pc.lower()}{v}nu{w}.dcc")
                    if b:
                        tried = True
                        try:
                            x0, y0, dw, dh, frames = self.dcc.decode(b)[0]
                        except Exception:
                            b = None
                            continue
                        fx, fy, fw, fh, pix = frames[0]
                        for i in pix:
                            if i:
                                hist[i] += 1
                        bx = (fx, fy, fx + fw, fy + fh)
                        box = bx if box is None else (min(box[0], bx[0]), min(box[1], bx[1]), max(box[2], bx[2]),
                                                      max(box[3], bx[3]))
                        n += 1
                        break
                if tried:
                    break
        if not n or not sum(hist):
            return None
        return {"hist": hist, "box": box, "parts": n}


def colour_stats(hist: list[int], pal, shift: list[int] | None = None) -> dict:
    """Mean RGB, mean hue (turns, weighted by saturation x value), hue confidence, saturation, value (0..1)."""
    tot = r = g = b = hx = hy = hw = s_sum = v_sum = 0.0
    for i, c in enumerate(hist):
        if not c:
            continue
        R, G, B = pal[shift[i] if shift else i]
        h, s, v = colorsys.rgb_to_hsv(R / 255, G / 255, B / 255)
        tot += c
        r += R * c; g += G * c; b += B * c
        w = c * s * v
        hx += w * math.cos(h * 2 * math.pi); hy += w * math.sin(h * 2 * math.pi); hw += w
        s_sum += s * c; v_sum += v * c
    if not tot:
        return {}
    return {"rgb": (r / tot / 255, g / tot / 255, b / tot / 255),
            "hue": (math.atan2(hy, hx) / (2 * math.pi)) % 1.0, "hue_conf": math.hypot(hx, hy) / hw if hw else 0.0,
            "sat": s_sum / tot, "val": v_sum / tot}



class ArtCache:
    def __init__(self, path: Path):
        self.path = path
        self.data = json.loads(path.read_text("utf-8")) if path.exists() else {}
        self.art = None
        self.dirty = False

    def get(self, side: str, code: str, row2: dict) -> dict | None:
        sig = "|".join([side, code, row2.get("BaseW", ""), *(f"{pc}={row2.get(pc + 'v', '')}" for pc in PART_CODES
                                                            if row2.get(pc) == "1")])
        if sig not in self.data:
            if self.art is None:
                self.art = Art()
            self.data[sig] = self.art.stats(side, code, row2, row2.get("BaseW") or "hth")
            self.dirty = True
        return self.data[sig]

    def save(self):
        if self.dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data), encoding="utf-8")
            self.dirty = False


def art_colour(art: Art, side: str, code: str, stats: dict | None, translvl: int) -> dict | None:
    """Colour statistics of cached art stats with the monster's palette shift (TransLvl) applied."""
    if not stats:
        return None
    shifts = art.palshift(side, code)
    shift = shifts[translvl + 2] if shifts and 0 <= translvl + 2 < 8 else None  # table t + 2 (0, 1: cold, poison)
    c = colour_stats(stats["hist"], art.pal, shift)
    x0, y0, x1, y1 = stats["box"]
    c["w"], c["h"], c["box"] = x1 - x0, y1 - y0, stats["box"]
    return c



# ------------------------------------------------------------------ family tags
# Median's monster ids are descriptive ("undead_lancer_3", "carrion_worm_2"): keywords of the id, the NameStr and the
# MonType give a family and a body plan; D2R's units get theirs from their names and a few overrides.
KEYWORDS = [
    (r"skelet|bone|skull|returned|reanimated|risen|leoric|lich|boneg|bony", {"skel", "undead"}),
    (r"zombie|ghoul|ghast|walker|husk|rotted|rotfiend|rotspawn|corpse|flesh|remade|putrid|afflicted|plague|living|"
     r"pest|contagion|bloated|corpulent|sunken|drowned|foulblooded|hemoplague|rotten|decay|undead|sinner|damned|"
     r"condemned|scorned|enslaved|forsaken", {"zombie", "undead"}),
    (r"ghost|spirit|wraith|phantom|phantasm|spectr|spectral|specter|soul|shade|banshee|ether|wisp|unseen|vision|"
     r"unformed|wailer|veil|apparition|nightmare|haunt", {"ghost"}),
    (r"spider|arach|widow|web|arthropod|broodling|broodmother|astrogha|tarantula", {"spider", "arachnid"}),
    (r"scarab|beetle|mantis|ankheg|scorpion|mosquito|hive|vermin|elytron|scytheclaw|insect|locust|wasp|crawler|"
     r"infestor|stirge|leech|tick", {"insect", "arachnid"}),
    (r"worm|maggot|larva|slimer|eel|grub|mawl|leech", {"worm", "serpent"}),
    (r"snake|serpent|viper|basilisk|couatl|adder|naga|cobra", {"snake", "serpent"}),
    (r"frog|toad|lizard|saurian|gecko|scincid|croc|newt|salamander|leaper|raptor|iguana|drowned_beast", {"lizard"}),
    (r"fish|eel|piranha|shark|leviathan|kraken|squid|jelly", {"fish"}),
    (r"wolf|worg|hound|dog|jackal|warg|direwolf|coyote|fenris|hellhound|cerberus", {"canine", "quad"}),
    (r"lion|panther|cat\b|tiger|leopard|cougar|feline|lynx|cheetah|sabertooth", {"feline", "quad"}),
    (r"bear|yeti|ape\b|baboon|gnoll|boar|rhino|buffalo|porkchop|behemoth|bull|ox\b|minotaur|bovine|beast|centaur|"
     r"horse|steed|mount|pig|hog|stag|deer|elk|goat|sheep|rat\b|rodent|mole|badger|sloth", {"beast", "quad"}),
    (r"bat\b|bird|harpy|wyvern|dragon|drake|gryphon|griffin|crow|raven|hawk|owl|wing|flyer|flit|hexwing|dreadwing|"
     r"fairy|pixie|fly\b|moth|vulture|eagle|condor|phoenix|roc\b", {"flying"}),
    (r"giant|ogre|troll|titan|goliath|gigas|colossus|colossal|hulk|golem|juggernaut|siegebreaker|brute|maul|"
     r"behemoth|ent\b|armored|obsidian|stone|rock", {"giant"}),
    (r"golem|elemental|construct|servant|sentinel|guardian|automaton|statue|sentry|gargoyle", {"golem"}),
    (r"demon|fiend|hellion|imp\b|ravager|fury|succubus|vixen|concubine|balrog|baron|pit|infernal|diabol|abyss|"
     r"hell|nephalem|tiefling|devil|incubus|archon|wicked|malign|horror|terror|fell", {"demon"}),
    (r"goblin|gremlin|hobgoblin|leprechaun|fallen|devilkin|carver|ratfink|kobold|gnome|troll_|imp\b|sprite|"
     r"spriggan|familiar|hoarder|scavenger|thief", {"goblin"}),
    (r"fetish|shaman|tribe|tribal|khazra|savage|witch.?doctor|nomad|gothi|ratman|rat_man", {"tribal"}),
    (r"warrior|knight|soldier|centurion|barbarian|amazon|rogue|hunter|archer|marksman|scout|assassin|ranger|paladin|"
     r"lancer|spear|halbedier|retiarius|defender|fanatic|zealot|templar|guard|bandit|raider|berserker|captain|"
     r"general|gladiator|champion|slayer|mercenary|crusader|inquisitor|warlord|jailor|butcher|executioner|"
     r"black_knight|sapphire_knight|onyx_knight|warleader|swordsman|duelist|bruiser", {"human", "warrior"}),
    (r"necromancer|mage|witch|priest|cleric|cabalist|warlock|seer|sorcer|wizard|enchanter|magineer|scholar|heretic|"
     r"druid|summoner|hexer|illusionist|elder|prophet|oracle|conjurer|pyromancer|bishop|vicar|magistrate|"
     r"cultist|acolyte|emissary|councillor|council|architect|alchemist|diviner|mystic|dame|matriarch|mistress|"
     r"naturist|consort|siren|lazarus|cultist", {"human", "caster"}),
    (r"archer|bow|marksman|dead_?shot|ranger|sniper|slinger|javelin|hunter|crossbow|gunner|thrower", {"archer"}),
    (r"altar|shrine|gate|pillar|chest|spire|tower|trap|crystal|egg\b|nest|fountain|obelisk|portal|door|cage|"
     r"sarcophag|coffin|well\b|void_trap|barricade|totem|brazier|lantern|machine|control_system|orb|beacon|"
     r"monolith|stele|cairn|grave\b|tombstone|lever|rift_storm|storm\b", {"object"}),
    (r"fungus|tree|treewarden|sapling|spore|vine|shroom|flower|poppy|mushroom|bush|plant|dryad|rooted|moss", {"plant"}),
    (r"lord|king|queen|prime|archmage|herald|prince|ancient|primus|azmodan|belial|samael|malthael|lilith|kabraxis|"
     r"mephisto|diablo|baal|tyrael|imperius|zagraal|astrogha|sescheron|tathamet|sovereign|archbishop|warleader|"
     r"avatar|skeleton_king|the_butcher|aranoch|arreat|tal_rasha|nithogur|deimoss|horazon|assur|mefis|"
     r"emissary_of_destruction|goddess|baron_of_hell|dark_star", {"boss"}),
]
KEY_RE = [(re.compile(k), v) for k, v in KEYWORDS]
FAMILY = {"skel", "zombie", "ghost", "spider", "insect", "worm", "snake", "lizard", "fish", "canine", "feline", "beast",
          "flying", "giant", "golem", "demon", "goblin", "tribal", "human", "object", "plant"}
QUAD, ARACH, SERP, FLY, STATIC = "quad", "arachnid", "serpent", "flying", "static"

# D2R unit -> extra tags (what the name does not say)
DONOR_TAGS = {
    "skeleton1": {"skel", "human", "warrior"}, "necroskeleton": {"skel", "human", "warrior"},
    "sk_archer1": {"skel", "human", "archer"}, "necromage": {"skel", "human", "caster"},
    "skmage_cold1": {"skel", "human", "caster"}, "skmage_fire1": {"skel", "human", "caster"},
    "skmage_ltng1": {"skel", "human", "caster"}, "skmage_pois1": {"skel", "human", "caster"},
    "mummy1": {"zombie", "undead"}, "zombie1": {"zombie", "undead"}, "reanimatedhorde1": {"zombie", "undead"},
    "bighead1": {"zombie", "undead"}, "warbighead": {"zombie", "undead"}, "brute2": {"zombie", "giant"},
    "unraveler1": {"zombie", "undead"}, "vampire1": {"human", "caster", "undead"}, "griswold": {"zombie", "undead"},
    "fallen1": {"goblin"}, "fallenshaman1": {"goblin", "caster"}, "minion1": {"demon", "goblin"},
    "suicideminion1": {"demon", "goblin"}, "imp1": {"demon", "goblin", "caster"},
    "fetish1": {"goblin", "tribal"}, "fetish11": {"goblin", "tribal"}, "fetishblow1": {"goblin", "tribal", "archer"},
    "fetishshaman1": {"goblin", "tribal", "caster"}, "bonefetish1": {"goblin", "tribal", "skel"},
    "goatman1": {"beast", "tribal"}, "wargoatman": {"beast", "tribal"},
    "wraith1": {"ghost"}, "willowisp1": {"ghost", "flying"}, "trappedsoul1": {"ghost"}, "trappedsoul2": {"ghost"},
    "spiritofbarbs": {"ghost", "object"}, "arach1": {"spider", "arachnid"}, "scarab1": {"insect", "arachnid"},
    "mosquito1": {"insect", "flying"}, "swarm1": {"insect", "flying"}, "bladecreeper": {"insect", "arachnid"},
    "maggotbaby1": {"worm", "serpent"}, "sandmaggot1": {"worm", "serpent"}, "maggotqueen1": {"worm", "serpent", "boss"},
    "painworm1": {"worm", "serpent"}, "larva": {"worm", "serpent"}, "vilechild1": {"beast", "demon"},
    "vilemother1": {"demon", "beast"}, "clawviper1": {"snake", "serpent", "lizard"},
    "frogdemon1": {"lizard", "demon"}, "sandleaper1": {"lizard"}, "quillrat1": {"beast", "quad"},
    "quillbear1": {"beast", "quad", "giant"}, "baboon1": {"beast", "human"}, "baboon6": {"beast", "human"},
    "snowyeti1": {"beast", "giant"}, "bear": {"beast", "quad"}, "druidbear": {"beast", "quad"},
    "wolf": {"canine", "quad"}, "spiritwolf": {"canine", "quad"}, "hellbovine": {"beast", "giant", "demon"}, "cowking": {"beast", "giant", "demon"}, "druidbear": {"beast", "quad"},
    "batdemon1": {"flying", "demon"}, "foulcrow1": {"flying"}, "vulture1": {"flying"}, "eagle": {"flying"},
    "druidhawk": {"flying"}, "blunderbore1": {"giant"}, "siegebeast1": {"giant", "beast", "quad"},
    "thornhulk1": {"plant", "giant"}, "bloodgolem": {"golem", "giant"}, "claygolem": {"golem"},
    "firegolem": {"golem"}, "irongolem": {"golem", "giant"}, "doomknight1": {"demon", "human", "warrior"},
    "doomknight2": {"demon", "human", "warrior"}, "doomknight3": {"demon", "human", "caster"},
    "bloodlord1": {"demon", "giant"}, "deathmauler1": {"demon", "giant"}, "megademon1": {"demon", "giant", "boss"},
    "succubus1": {"demon", "caster"}, "succubuswitch1": {"demon", "caster"}, "overseer1": {"demon", "caster"},
    "cantor1": {"human", "caster"}, "councilmember1": {"human", "caster"}, "summoner": {"human", "caster", "boss"},
    "fingermage1": {"demon", "caster", "giant"}, "corruptrogue1": {"human", "warrior"},
    "cr_lancer1": {"human", "warrior"}, "cr_archer1": {"human", "archer"}, "bloodraven": {"human", "archer", "boss"},
    "sandraider1": {"human", "warrior"}, "pantherwoman1": {"human", "warrior"}, "slinger1": {"human", "archer"},
    "slinger5": {"human", "archer"}, "act5barb1": {"human", "warrior"}, "act5barb2": {"human", "warrior"},
    "act5barb3": {"human", "warrior"}, "ancientbarb1": {"human", "warrior", "giant", "boss"},
    "ancientbarb2": {"human", "warrior", "giant", "boss"}, "ancientbarb3": {"human", "warrior", "giant", "boss"},
    "zealot1": {"human", "warrior"}, "andariel": {"demon", "boss"}, "diablo": {"demon", "boss"},
    "duriel": {"demon", "boss", "giant"}, "izual": {"demon", "boss"}, "mephisto": {"demon", "boss", "caster"},
    "radament": {"zombie", "boss"}, "venomlord": {"demon", "giant", "boss"}, "hephasto": {"demon", "giant"},
    "sarcophagus": {"object"}, "turret1": {"object"}, "firetower": {"object"}, "lightningspire": {"object"},
    "chargeboltsentry": {"object"}, "deathsentry": {"object"}, "infernosentry": {"object"},
    "lightningsentry": {"object"}, "gargoyletrap": {"object"}, "barricadetower": {"object"},
    "barricadewall1": {"object"}, "barricadewall2": {"object"}, "barricadedoor1": {"object"},
    "barricadedoor2": {"object"}, "prisondoor": {"object"}, "bonewall": {"object"}, "evilhut": {"object"},
    "minionspawner1": {"object"}, "catapult1": {"object"}, "window1": {"object"}, "window2": {"object"},
    "crownest1": {"object"}, "trap-melee": {"object"}, "maggotegg1": {"object"}, "hydra1": {"object", "serpent"},
    "hydra2": {"object", "serpent"}, "hydra3": {"object", "serpent"}, "tentacle1": {"object", "serpent"},
    "tentaclehead1": {"object", "serpent"}, "baaltentacle1": {"object", "serpent"}, "flyingscimitar": {"object"},
    "boneprison1": {"object"}, "boneprison2": {"object"}, "boneprison3": {"object"}, "boneprison4": {"object"},
    "frozenhorror1": {"demon", "giant"}, "regurgitator1": {"zombie", "giant"}, "darkwanderer": {"ghost", "human"},
    "gorgon1": {"beast", "quad"}, "baalminion1": {"demon", "giant"}, "bloodlord": {"demon", "giant"},
    "valkyrie": {"human", "warrior"}, "colbarbfrenzy": {"human", "warrior"}, "colbarbthrow": {"human", "warrior"},
    "colbarbwhirl": {"human", "warrior"},
}
# Specials that must never be donors (invisible helpers, towns folk, cinematic duplicates, tiny dummies)
NOT_DONORS = re.compile(r"^(act2|act3|baal(clone|crab|taunt|throne|high)|trap-|invis|cycle|worldstone|seventombs|"
                        r"catapultspotter|plaguepoppy|vinecreature|hellmeteor|compellingorb|dopplezon|shadow|"
                        r"driver_|bat$|bird|fish|horse|rat$|chicken|bunny|bug|snake$|scorpion$|maggot$|parrot|"
                        r"seagull|cow$|pig$|camel|tyrael|izualghost|mephistospirit|evilhole|colossal|injured|"
                        r"cain|kashya|warriv|akara|gheed|charsi|natalya|drognan|fara|elzix|greiz|jerhyn|"
                        r"lysander|meshif|atma|asheara|alkor|hratli|geglash|halbu|jamella|larzuk|malah|"
                        r"malachai|nihlathak$|qual|smith|navi|rogue[123]|roguehire|ormus|drehya|ancientstatue|"
                        r"fire(tower)$|spiritofbarbs|corpsefire|uberancient|wakeof|window)")


def text_of(*parts: str) -> str:
    out = []
    for p in parts:
        p = re.sub(r"([a-z])([A-Z])", r"\1_\2", p or "")
        out.append(re.sub(r"[^a-z0-9]+", "_", p.lower()))
    return " ".join(out)


def tags_of(text: str) -> set[str]:
    tags: set[str] = set()
    for rx, tg in KEY_RE:
        if rx.search(text):
            tags |= tg
    return tags


def body_of(tags: set[str], w: int, h: int, translate: bool = True) -> str:
    """Body plan from tags, else from the art's aspect."""
    if "object" in tags and not tags & {"human", "golem"}:
        return STATIC
    if "plant" in tags and "giant" not in tags:
        return STATIC
    if tags & {"serpent"}:
        return SERP
    if tags & {"arachnid"}:
        return ARACH
    if "flying" in tags and not tags & {"human", "warrior", "caster", "demon", "giant", "zombie", "skel"}:
        return FLY
    if "quad" in tags and not tags & {"human", "warrior", "caster"}:
        return QUAD
    if tags & FAMILY and tags & {"human", "warrior", "caster", "skel", "zombie", "goblin", "tribal", "demon", "giant",
                                 "golem", "ghost", "lizard"}:
        return "biped"
    if h and w / h > 1.5:
        return QUAD
    return "biped"


# ------------------------------------------------------------------ donor choice
class Donor:
    def __init__(self, unit, ref, ms_row, ms2_row, name, info, col):
        self.unit, self.ref, self.name, self.info, self.col = unit, ref, name, info, col
        self.montype, self.ai, self.basew = ms_row["MonType"], ms_row["AI"], ms2_row["BaseW"]
        self.code = ms_row["Code"]
        txt = text_of(unit, name, ms_row["MonType"])
        self.tags = set(DONOR_TAGS[unit]) if unit in DONOR_TAGS else tags_of(txt)
        self.fam = self.tags & FAMILY
        self.body = body_of(self.tags, col["w"], col["h"])
        self.boss = "boss" in self.tags
        self.modes = set()
        for ms in info["modes"].values():
            self.modes |= set(ms)
        names = set(sum(info["states"].values(), []))
        if "Walk" in names:
            self.modes.add(2)
        if "Run" in names:
            self.modes.add(15)
        self.keys = set(info["modes"])
        self.n_parts = len(info["parts"])


def build_donors(ms, ms2, names, art: Art, cache: ArtCache, mj: dict) -> dict[str, Donor]:
    ref: dict[str, tuple] = {}
    for i, r in ms.items():
        u = mj.get(i)
        if not u or not r["Code"] or r["npc"] == "1" or NOT_DONORS.match(u) or ms2.get(r["MonStatsEx"]) is None:
            continue
        key = (r["enabled"] != "1", int(r["TransLvl"] or 0))
        if u not in ref or key < ref[u][0]:
            ref[u] = (key, i)
    out = {}
    for u, (_, i) in ref.items():
        r = ms[i]
        r2 = ms2[r["MonStatsEx"]]
        info = unit_info(u)
        if not info or not info["modes"]:
            continue
        code = r["Code"].lower()
        col = art_colour(art, "d2r", code, cache.get("d2r", code, r2), int(r["TransLvl"] or 0))
        if not col or col["h"] < 20 or col["w"] < 8:
            continue
        out[u] = Donor(u, i, r, r2, names.get(bare(r["NameStr"]), bare(r["NameStr"])), info, col)
    return out


class Subject:
    """A Median monster that needs an HD look."""

    def __init__(self, mid, ms_row, ms2_row, name, col):
        self.id, self.row, self.row2, self.name, self.col = mid, ms_row, ms2_row, name, col
        self.code = ms_row["Code"]
        self.translvl = int(ms_row["TransLvl"] or 0)
        self.basew = ms2_row["BaseW"] or "hth"
        self.modes = modes_of(ms2_row)
        self.slots = slots_of(ms2_row)
        root = re.sub(r"_\d+$", "", mid)
        self.text = text_of(root, bare(ms_row["NameStr"]), name if name != bare(ms_row["NameStr"]) else "")
        self.tags = tags_of(self.text)
        self.type_tags = tags_of(text_of(ms_row["MonType"]))
        self.ai_tags = tags_of(text_of(ms_row["AI"]))
        self.keyword_family = bool(self.tags & FAMILY)
        if not self.keyword_family:  # nothing in the name: fall back on MonType, then on AI
            self.tags |= self.type_tags or self.ai_tags
        self.fam = self.tags & FAMILY
        self.body = body_of(self.tags, col["w"], col["h"]) if col else "biped"
        if not self.slots:
            self.slots = {"TR": ["lit"]}


def circ(a: float, b: float) -> float:
    d = (a - b + 0.5) % 1.0 - 0.5
    return d


def score(s: Subject, d: Donor) -> tuple[float, float, list[str]]:
    """(score, art size ratio, reasons) of donor d for subject s."""
    why = []
    sc = 0.0
    shared = s.fam & d.fam
    if s.keyword_family:
        sc += 3.0 * len(shared) / len(s.fam) if s.fam else 0
        if shared:
            why.append("family " + "+".join(sorted(shared)))
        elif d.fam:
            sc -= 1.0
    else:
        sc += 1.5 * len(shared) / len(s.fam) if s.fam else 0
    if "archer" in s.tags and "archer" in d.tags:
        sc += 1.5
        why.append("archer")
    if "caster" in s.tags and "caster" in d.tags:
        sc += 1.0
    if s.body == d.body:
        sc += 2.5
        why.append("body " + d.body)
    elif {s.body, d.body} == {QUAD, "biped"} or STATIC in (s.body, d.body):
        sc -= 4.0 if STATIC in (s.body, d.body) else 3.0
    else:
        sc -= 1.5
    if ("boss" in s.tags) != d.boss:
        sc += 1.0 if d.boss else -1.5 if "boss" not in s.tags else 0
    if d.boss and "boss" not in s.tags:
        sc -= 2.5
    if s.row["MonType"] == d.montype and s.row["MonType"]:
        sc += 0.8
    if s.row["AI"] == d.ai:
        sc += 1.2
    # animations: the modes Median's monstats2 asks for, and the weapon class
    need = {MODE_ID[m] for m in s.modes if m not in ("SQ", "KB")}
    miss = [m for m in need if m not in d.modes and not (m in (0, 12) and (0 in d.modes or 12 in d.modes))]
    if miss:
        sc -= 2.0 * len(miss)
        why.append(f"missing modes {sorted(miss)}")
    if s.basew in d.keys:
        sc += 0.8
    elif s.basew in ("bow", "xbw") and "archer" not in d.tags:
        sc -= 1.0
    # size
    ratio = 1.0
    if s.col and d.col:
        hr = s.col["h"] / d.col["h"]
        wr = s.col["w"] / d.col["w"]
        ratio = hr ** 0.7 * wr ** 0.3 if s.body in (QUAD, ARACH, SERP) else hr
        sc -= 1.4 * abs(math.log(ratio))
        # colour
        dc = math.dist(s.col["rgb"], d.col["rgb"])
        sc -= 2.0 * dc
        if d.n_parts > 3 and len(s.slots) <= 2:
            sc -= 0.3  # a donor of many parts folded into one slot
    return sc, ratio, why


def choose(s: Subject, donors: dict[str, Donor]) -> tuple[Donor, float, float, list[str], float]:
    ranked = sorted(((score(s, d), d) for d in donors.values()), key=lambda t: -t[0][0])
    (sc, ratio, why), d = ranked[0]
    margin = sc - ranked[1][0][0] if len(ranked) > 1 else 0.0
    return d, sc, ratio, why, margin


def confidence(s: Subject, d: Donor, sc: float, ratio: float, margin: float) -> str:
    fam = s.keyword_family and bool(s.fam & d.fam)
    size_ok = 0.6 <= ratio <= 1.7
    body_ok = s.body == d.body
    if fam and body_ok and size_ok:
        return "high"
    if (fam or (not s.keyword_family and body_ok and s.fam & d.fam)) and body_ok:
        return "medium"
    return "low"



# ------------------------------------------------------------------ tint
def hue_weight(c: dict) -> float:
    """How well defined a colour's hue is (grey art has none)."""
    return min(1.0, c["hue_conf"]) * min(1.0, c["sat"] / 0.25)


# The hue turns all the way when both arts have a hue: their coloured pixels agree on it (hue_conf) and there is some colour at
# all (mean saturation), else not at all. A turn scaled by how colourful the art is on average stops on a hue in between: the
# olive Doom Knight turned a quarter of the way to Inarius's blue came out green, and Inarius's blue armour (much grey and
# white beside it, mean saturation 0.09) is a real hue (lane tints2).
HUE_MIN_CONF = 0.45
HUE_MIN_SAT = 0.08


def has_hue(c: dict) -> bool:
    return c["hue_conf"] >= HUE_MIN_CONF and c["sat"] >= HUE_MIN_SAT


def tint_of(m: dict, d: dict) -> tuple[tuple, tuple, str]:
    """(colorAdjustment, colorTint, label): turns the donor's classic-art colour into Median's.

    colorAdjustment holds (hue shift in turns, saturation, value) offsets of the albedo, colorTint an (r, g, b, amount)
    blend; see docs/hd-monsters.md for what each does in game. The hue turns all the way or not at all (has_hue); a grey
    Median monster is reached by the saturation offset alone."""
    dh = circ(m["hue"], d["hue"])
    hue = dh if has_hue(m) and has_hue(d) else 0.0
    sat = max(-0.8, min(0.8, (m["sat"] - d["sat"]) * 1.0))
    val = max(-0.7, min(0.7, math.log2(max(m["val"], 0.03) / max(d["val"], 0.03)) * 0.45))
    tint = (0.0, 0.0, 0.0, 0.0)
    # donor without a hue (bone, grey) against a clearly coloured Median monster: blend towards its colour
    if hue_weight(m) > 0.3 and hue_weight(d) < 0.5 and m["sat"] > 0.3:
        r, g, b = colorsys.hsv_to_rgb(m["hue"], min(1.0, m["sat"] * 1.4), 1.0)
        tint = (r, g, b, round(min(0.6, 0.25 + m["sat"] * 0.4), 2))
    adj = (round(hue % 1.0, 3), round(sat, 3), round(val, 3), 1.0)
    if abs(hue) < 0.02 and abs(sat) < 0.08 and abs(val) < 0.08 and not tint[3]:
        return (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 0.0), "none"
    return adj, tint, f"hue {hue:+.2f} sat {sat:+.2f} val {val:+.2f}" + (f" tint {tint[3]:.2f}" if tint[3] else "")


def q(x: float, step: float) -> float:
    return round(round(x / step) * step, 4)



# ------------------------------------------------------------------ vanilla art
def vanilla_unit(s: Subject, ms: dict, mj: dict, ms2: dict, by_code: dict[str, dict[str, str]]) -> tuple[str | None, str]:
    """Unit for a Median monster that uses a D2R code (D2R's own art): D2R's unit of the same Id and code, else the
    unit of that code that fits best by AI, MonType and weapon class."""
    d = ms.get(s.id)
    if d and d["Code"].lower() == s.code.lower() and s.id in mj:
        return mj[s.id], "same Id and code in D2R"
    cand = by_code.get(s.code.lower())
    if not cand:
        return None, "code has no D2R unit"
    if len(cand) == 1:
        return next(iter(cand)), "only unit of the code"
    best, bs = None, -9.0
    for u, i in cand.items():
        r = ms[i]
        r2 = ms2.get(r["MonStatsEx"], {})
        sc = (3.0 if r["AI"] == s.row["AI"] else 0) + (2.0 if r["MonType"] == s.row["MonType"] and r["MonType"] else 0)
        sc += 1.0 if r2.get("BaseW", "hth") == s.basew else 0
        sc += 1.0 * len(tags_of(text_of(u)) & s.tags)
        if sc > bs:
            best, bs = u, sc
    return best, f"best of {len(cand)} units of the code"

