"""The in-game cube recipe checks of lane cube: one representative recipe per recipe class, on the player path.

tools/game_checks.py `cubeclasses` runs CASES: every input is made by the item generator on the ground next to the character
(`h item <spec> ground`, a drop), picked up onto the cursor (packet 0x16, the client's click on it) and put into the Horadric
Cube (packet 0x18 page 3, the click on a cube cell); the cube panel is opened by a right click on the cube and the panel's
Transmute button is clicked. The cube's contents (`h items`, page 3) and the output's stats (`h istat`) are then judged here.
Nothing is written into a save and no stat is set; the classes rulescheck's real-path checks cover (gem upgrade, unique
disenchant, five shards, unique reroll, shrine crafts and blessings, trophies and charms, op 28 quest recipes, runewords, the
Boss Killer Ring) are left to that lane (docs/median-rules-audit.md "Items: real-path checks").

This module has no game code: the case table, the parsing of the harness lines and the judgement (unit tests:
tools/tests/test_cube_game.py).
"""
import re
from collections import Counter

# Cube grid placements for packet 0x18: (x, y) cells 2 wide and 3 high (a weapon or a shield fits), Median's 10 x 8 cube.
CUBE_CELLS = [(x, y) for y in (0, 3) for x in (0, 2, 4, 6, 8)] + [(x, 6) for x in (0, 2, 4, 6, 8)]
WEAPON = "4@A"   # a tiered weapon base (types pmac + tier): weap, tier
SHIELD, SHIELD2 = "w23", "w43"   # Aerin Shield (1) / (2): the "uptier" rows; unique Catechumen on both

# name, recipe class, built cubemain row (1-based, = Median's), inputs (`item` arguments, one per item), expectation:
#   cube   the codes the cube holds afterwards (Counter); "type:<t>" = any base of item type t; [] with refused = nothing changes
#   out    the code (or "type:<t>") of the output whose quality / stats are judged
#   quality, stats {stat name: value} (raw stat values: maxhp is shifted by 8), skill_layer (stat name, skill id) for a
#   skill-parameter stat, refused (the transmute must change nothing), level (the character level the row needs)
CASES = [
    dict(name="rune upgrade", cls="gem / rune upgrades", row=290, inputs=["r01", "r01"], cube=["r02"], out="r02"),
    dict(name="rune downgrade", cls="gem / rune upgrades", row=435, inputs=["r02"], cube=["r01"], out="r01"),
    dict(name="unsocket (magic, rem)", cls="socketing", row=490, inputs=[f"{WEAPON} magic 194=2", "2o^"], cube=[WEAPON], out=WEAPON,
         quality=4),
    dict(name="socket creation (sock 1)", cls="socketing", row=845, inputs=[f"{WEAPON} normal !nosock", "jew"], cube=[WEAPON], out=WEAPON,
         stats={"item_numsockets": 1}),  # `nos`: a roll without sockets
    dict(name="reroll low (usetype,low ilvl 100)", cls="rerolls", row=541, inputs=[f"{WEAPON} low", "5o^"], cube=["type:pmac"],
         out="type:pmac", quality=1),
    dict(name="gem shatter (usetype,rar)", cls="rerolls", row=839, inputs=[f"{WEAPON} magic", "4o^", "r01"], cube=["type:pmac"],
         out="type:pmac", quality=6),
    dict(name="zomghelp (op 10: base level == 1)", cls="op conditions", row=580, level=1,
         inputs=[f"{WEAPON} magic", "amu magic", "rin magic"], cube=["type:pmac"], out="type:pmac", quality=4,
         also=["item_maxdamage_percent", "item_mindamage_percent"]),  # read 0 on every layer by `istat` although the tooltip
         # shows "+25% Enhanced Damage" and the damage line has it (16-25 -> 20-31, run checks-20261028-163101-s2): judged on the shot
    dict(name="jewelcrafting refused (op 3: craft points > 50, character has 0)", cls="op conditions", row=565,
         inputs=["jew magic", "7o^", "r03"], cube=[], refused=True),
    dict(name="dupe (op 18 == 0, two useitem outputs)", cls="op conditions", row=8397, inputs=[f"{WEAPON} normal", "qum", "1o^"],
         cube=[WEAPON, WEAPON], out=WEAPON, stats={"item_hasbeenduped": 1}, again="dupe refused"),
    dict(name="dupe refused (op 18: the copy has item_hasbeenduped 1)", cls="op conditions", row=8397, inputs=["@dupe", "qum", "1o^"],
         cube=[], refused=True),
    dict(name="disenchant as signet (catalyst back)", cls="disenchanting", row=869, inputs=["@weapon_unique", "0o^"],
         cube=["zkq", "0o^"], out="zkq"),
    dict(name="shard shatter (usetype,uni)", cls="rerolls", row=881, inputs=[f"{WEAPON} normal", "qum", "qum", "4o^"],
         cube=["type:pmac"], out="type:pmac", quality=7),
    dict(name="Apple of Discord (skill parameter)", cls="Mystic Orbs", row=8226, inputs=[f"{WEAPON} normal", "&75"], cube=[WEAPON],
         out=WEAPON, stats={"item_levelreq": 10, "maxhp": 20 << 8, "maxmana": 20 << 8}, skill_layer=("item_skillonattack", "Dire Charm L")),
    dict(name="honorific + Mystic Orb (op 15 on input 1 only)", cls="op conditions", row=7581, inputs=["@honorific", "01+"],
         cube=[WEAPON], out=WEAPON, stats={"strength": 2, "x_signet01": 1}),
    dict(name="any uptier (output mod)", cls="uptier", row=9521, inputs=[f"{SHIELD} normal", "qum"], cube=[SHIELD2], out=SHIELD2),
    dict(name="unique uptier (version 10)", cls="uptier", row=8421, inputs=["@shield_unique", "qum", "r01"], cube=[SHIELD2],
         out=SHIELD2, quality=7),
    dict(name="RIP (catalyst back)", cls="item mods", row=10621, inputs=[f"{WEAPON} normal", "9o^", "qum"], cube=[WEAPON, "9o^"],
         out=WEAPON, stats={"item_restinpeace": 1}),
    dict(name="destruction (numinputs 2, one unlisted item eaten)", cls="destruction", row=11399, inputs=["9o^", "hp1"], cube=["9o^"],
         out="9o^"),
    dict(name="clue gem cycle", cls="quest / uber keys", row=8282, inputs=["01-"], cube=["02-"], out="02-"),
    dict(name="summoning scroll (unique output)", cls="quest / uber keys", row=29, inputs=["mec"] * 3 + ["vic"] * 3,
         cube=["@ScrollOfSummons"], out="@ScrollOfSummons", quality=7),
    dict(name="Token of Absolution", cls="Token of Absolution", row=28, inputs=["8o^", "r01"], cube=["toa"], out="toa", use=True),
]
# `!nosock`: the generator is asked again until the drop has no socket (a normal base may roll one; `nos` refuses it).
# `also`: stats read and reported, not judged.
# Inputs made by an earlier step: "@honorific" = the output of `full honorifics` (row 8394: magic weapon + Sacrificial Heart +
# Meditation Candle), "@dupe" = one copy from the dupe case, "@weapon_unique" / "@shield_unique" = `item <code> unique`.
PREP_HONORIFIC = dict(name="full honorifics (prepares the honorific weapon)", cls="op conditions", row=8394,
                      inputs=[f"{WEAPON} magic", "vic", "mec"], cube=["type:pmac"], out="type:pmac", quality=9,
                      stats={"item_is_honorific": 1, "item_numsockets": 1})  # `sock 6` capped by the base's gemsockets 1
                                                                                 # (Median's weapons.txt too: 1.13c's cap)


def kv(line: str) -> dict:
    out = {}
    for k, v in re.findall(r"(\w+)=(\S+)", line):
        out[k] = int(v) if re.fullmatch(r"-?\d+", v) else (int(v, 16) if re.fullmatch(r"0x[0-9a-fA-F]+", v) else v)
    return out


def cube_items(lines) -> list[dict]:
    """The `h items` lines of the cube (page 3) as dicts."""
    return [kv(ln) for ln in lines if ln.startswith("item ") and kv(ln).get("page") == 3]


def item_id(lines) -> int | None:
    """The unit id an `item ... ground` answer names."""
    m = re.search(r"item id=(\d+)", " ".join(lines))
    return int(m.group(1)) if m else None


def istat_value(lines) -> int | None:
    m = re.search(r"istat \d+ \d+:\d+ = (-?\d+)", " ".join(lines))
    return int(m.group(1)) if m else None


def istat_layers(lines) -> dict[int, int]:
    """`istat <id> <stat> scan` -> {layer: value}."""
    return {int(a): int(b) for a, b in re.findall(r"istat \d+ \d+:(\d+) = (-?\d+)", "\n".join(lines))}


def code_matches(want: str, code: str, types: dict[str, tuple]) -> bool:
    """`want` is a code, "type:<t>" (the base's type or type2 is t) or "@<unique index>" resolved by the caller to a code."""
    if want.startswith("type:"):
        return want[5:] in types.get(code, ())
    return want == code


def match_cube(want: list[str], items: list[dict], types: dict[str, tuple]) -> bool:
    """The cube holds exactly the wanted codes (each item matched once)."""
    left = list(items)
    for w in want:
        hit = next((i for i in left if code_matches(w, str(i.get("code")), types)), None)
        if hit is None:
            return False
        left.remove(hit)
    return not left


def output_item(case: dict, items: list[dict], types: dict[str, tuple], inputs: set[int] = frozenset()) -> dict | None:
    """The cube item the case judges: the first one of the output code, a new unit before a kept one."""
    cands = [i for i in items if case.get("out") and code_matches(case["out"], str(i.get("code")), types)]
    cands.sort(key=lambda i: i.get("id") in inputs)
    return cands[0] if cands else None


def judge(case: dict, before: list[dict], after: list[dict], types: dict[str, tuple], stats: dict[str, int] | None = None,
          skill: tuple[int, int] | None = None) -> tuple[bool, str]:
    """(passed, note) for one transmute. `stats`: {stat name: value read with istat on the output}; `skill`: (wanted skill
    id, skill ids found on the skill-parameter stat)."""
    got = sorted(str(i.get("code")) for i in after)
    if case.get("refused"):
        same = Counter((i.get("id"), i.get("code")) for i in before) == Counter((i.get("id"), i.get("code")) for i in after)
        return same, "refused as wanted, the cube is unchanged" if same else f"NOT refused: the cube became {got}"
    if not match_cube(case["cube"], after, types):
        return False, f"cube holds {got}, wanted {case['cube']}"
    notes = [f"cube holds {got}"]
    ok = True
    out = output_item(case, after, types)
    if case.get("quality") is not None:
        q = out.get("quality") if out else None
        ok &= q == case["quality"]
        notes.append(f"quality {q} (want {case['quality']})")
    for name, want in (case.get("stats") or {}).items():
        v = (stats or {}).get(name)
        ok &= v == want
        notes.append(f"{name} {v} (want {want})")
    for name, want in (case.get("stats_min") or {}).items():
        v = (stats or {}).get(name)
        ok &= v is not None and v >= want
        notes.append(f"{name} {v} (want >= {want})")
    if case.get("skill_layer"):
        want_id, found = skill if skill else (None, [])
        ok &= want_id is not None and want_id in found
        notes.append(f"{case['skill_layer'][0]} skills {found} (want {case['skill_layer'][1]} = {want_id})")
    return bool(ok), "; ".join(notes)


def skill_ids(layers: dict[int, int], encode: str) -> list[int]:
    """Skill ids of a skill-parameter stat's layers: encode 2 / 3 keep the level in the low 6 bits."""
    return sorted({(lay >> 6) if encode in ("2", "3") else lay for lay in layers})
