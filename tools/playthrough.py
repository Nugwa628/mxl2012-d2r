"""The player-path playthrough of tools/game_checks.py (`playthrough`, lane playtest, docs/testing.md "Playthrough").

One fresh Normal character per classic class (Warlock needs Reign of the Warlock: skipped), played the way a player does it, in
background input mode: no god mode, no easykill, no stat or level grants. Every step goes through the game's own input path
(background clicks with the plugin's virtual cursor, posted keys); the harness only reads (`state`, `items`, `stat ... ` without
`set`, `objects`, `asserttrace`) and, where main has no player verb yet, moves the character between areas (`level`, documented
per step). Steps: create, starting kit, field (`level 2`), kill monsters with the class's own left skill (Attack at level 1),
pick up real drops from the ground (hover scan of the kill spots, click), equip a picked-up item (inventory clicks), Charsi:
talk, Trade, sell a scroll, buy a potion, waypoint (click the Cold Plains waypoint, pick the Rogue Encampment), cube Median's
one-item recipe "Clue gem cycle" (starting kit `01-` -> `02-`, cube panel clicks), Save and Exit + reload (items compared),
die once (to the field's monsters) and respawn.

The pure parts (parsers, the hover label and NPC menu finders, the backpack fit, the class row verdict) are unit-tested in
tools/test_playthrough.py. The game parts take the game_checks module as `gc` (game_checks runs as __main__; importing it here would make a second copy of its state).
"""
import os
import re
import string
import time

# ---------------------------------------------------------------- pure helpers (unit-tested)

CLASS_NAMES = ["amazon", "sorceress", "necromancer", "paladin", "barbarian", "druid", "assassin"]  # `state` class 0-6
STEPS = ["create", "kit", "field", "kill", "pickup", "equip", "cube", "waypoint", "reload", "vendor", "death"]
# A step that ends in one of these is not a defect of the port: BLOCKED (the harness cannot drive it in background mode) and
# SKIP (the game gave nothing to act on, e.g. no equippable drop) only lower the row to PARTIAL.
OK_STATES = ("PASS",)
SOFT_STATES = ("BLOCKED", "SKIP")


def num(v):
    return int(v) if re.fullmatch(r"-?\d+", v) else v


def parse_items(lines):
    """`h items` / `h item` answer lines -> [{id, code, page, x, y, quality, ...}] (page 0 backpack, 3 cube, 4 stash, 255 worn)."""
    out = []
    for ln in lines:
        ln = ln.strip()
        if ln.startswith("item id="):
            out.append({k: (v if k == "code" else num(v)) for k, v in re.findall(r"(\w+)=(\S+)", ln)})  # codes such as 600 stay text
    return out


def parse_objects(lines):
    """`h objects` (`object id=...`) and `h state` (`obj id=...`) lines -> [{id, class, mode, dist, x, y[, dest]}]."""
    out = []
    for ln in lines:
        ln = ln.strip()
        if not (ln.startswith("object id=") or ln.startswith("obj id=")):
            continue
        d = {k: num(v) for k, v in re.findall(r"(\w+)=(-?[\d.]+)", ln)}
        if isinstance(d.get("dist"), str):
            d["dist"] = float(d["dist"])
        m = re.search(r" at (-?\d+),(-?\d+)", ln)
        if m:
            d["x"], d["y"] = int(m.group(1)), int(m.group(2))
        out.append(d)
    return out


def parse_ground(lines):
    """`h ground` lines (`ground id=.. code=.. mode=.. x=.. y=.. dist=..`) -> [{id, code, mode, x, y, dist}] (main's read-only verb)."""
    out = []
    for ln in lines:
        ln = ln.strip()
        if ln.startswith("ground id="):
            d = {k: (v if k == "code" else num(v)) for k, v in re.findall(r"(\w+)=(\S+)", ln)}
            try:
                d["dist"] = float(d.get("dist", 99))
            except (TypeError, ValueError):
                d["dist"] = 99.0
            out.append(d)
    return out


def item_changes(before, after):
    """(new items, items gone, items moved) between two parse_items lists, by unit id; moved = same id, other page / x / y."""
    b = {i["id"]: i for i in before}
    a = {i["id"]: i for i in after}
    new = [a[k] for k in a if k not in b]
    gone = [b[k] for k in b if k not in a]
    moved = [(b[k], a[k]) for k in a if k in b and (b[k].get("page"), b[k].get("x"), b[k].get("y")) != (a[k].get("page"), a[k].get("x"), a[k].get("y"))]
    return new, gone, moved


def kit_signature(items):
    """Sorted (code, page) pairs: what a save / load must keep (unit ids change on every load)."""
    return sorted((str(i.get("code")), i.get("page"), i.get("x"), i.get("y")) for i in items)


def char_name(cls, stamp):
    """A letters-only name (D2R drops digits: Mxl2Barb became MxlBarb) that is new for every run: 'Pt' + class + the stamp in
    letters, at most 15 characters. `stamp` is an int (seconds)."""
    letters = ""
    n = int(stamp)
    for _ in range(6):
        letters = string.ascii_lowercase[n % 26] + letters
        n //= 26
    return ("Pt" + cls[:3].capitalize() + letters)[:15]


def label_hit(found, fx, fy, min_blocks=8, min_width=0.035):
    """A hover label above the cursor among game_checks.clusters() of a capture with the cursor parked away and one with it at
    (fx, fy): changed regions just above the cursor whose blocks add up to `min_blocks` and that span `min_width` of the client
    width (an item's name; slot 2: 'Quilted Armor (1)' made 4 regions, 24 blocks, 0.11 wide). The idle animation of a monster or
    the character changes a few compact regions only."""
    near = [f for f in found if fy - 0.07 <= f[1] <= fy + 0.005 and abs(f[0] - fx) <= 0.13]
    if sum(f[2] for f in near) < min_blocks:
        return False
    xs = [f[0] for f in near]
    return max(xs) - min(xs) >= min_width or max(f[2] for f in near) >= 2 * min_blocks


def body_loc_of(code, tables):
    """Body location name (BodyLoc1 of the item's type chain: 'head', 'tors', 'rarm', ...) of a base code, '' when the item is
    not worn. `tables` = {'weapons': rows, 'armor': rows, 'misc': rows, 'itemtypes': rows} (dict rows of the built tables)."""
    types = {r.get("Code"): r for r in tables.get("itemtypes", []) if r.get("Code")}
    base = None
    for t in ("weapons", "armor", "misc"):
        base = next((r for r in tables.get(t, []) if r.get("code") == code), None)
        if base:
            break
    if not base:
        return ""
    todo, seen = [base.get("type"), base.get("type2")], set()
    while todo:
        t = todo.pop(0)
        if not t or t in seen or t not in types:
            continue
        seen.add(t)
        row = types[t]
        if row.get("Body") == "1" and row.get("BodyLoc1"):
            return row["BodyLoc1"]
        todo += [row.get("Equiv1"), row.get("Equiv2")]
    return ""


def selected_steps(text):
    """MXL_PT_STEPS ("kit,vendor"): the steps to run (create always runs: every class starts from a fresh character); None = all.
    An unknown step name raises (a misspelt name used to run nothing without a word, game_checks.unknown_checks)."""
    if not text:
        return None
    names = [n.strip() for n in text.split(",") if n.strip()]
    bad = [n for n in names if n not in STEPS]
    if bad:
        raise ValueError("unknown playthrough step(s) %s (steps: %s)" % (bad, ", ".join(STEPS)))
    return {"create"} | set(names)


def class_verdict(steps, only=None):
    """The class row's status from {step: (status, note)}: FAIL when any step failed (a crash, an assert, a broken rule),
    PASS when every step passed, else PARTIAL (BLOCKED / SKIP steps, or steps that did not run)."""
    states = [steps.get(s, ("NOT RUN", ""))[0] for s in STEPS if only is None or s in only]
    if any(s == "FAIL" for s in states):
        return "FAIL"
    if all(s in OK_STATES for s in states):
        return "PASS"
    return "PARTIAL"


def class_note(steps):
    return "; ".join("%s %s%s" % (s, steps[s][0], (" (" + steps[s][1] + ")") if steps[s][1] else "") for s in STEPS if s in steps)


def parse_loader_log_tail(text):
    """Problems D2RLoader logged (besides the asserts game_checks.engine_asserts reads): error / exception / crash lines."""
    bad = []
    for ln in text.splitlines():
        low = ln.lower()
        if ("[error]" in low or "exception" in low or "crash" in low or "could not add" in low) and "0 errors" not in low:
            bad.append(ln.strip()[:160])
    return bad


# ---------------------------------------------------------------- the game side (needs a running game; gc = game_checks)
# Screen positions are fractions of the 1600 x 900 HD client (game_ctl fits the window to it), measured on slot 2/3 by lane
# playtest 2026-10-28. The player stands at (800, 405); one sub-tile is ~27 px along x - y and ~13.5 px along x + y
# (game_checks.click_unit).
PLAYER_PX = (800, 405)
UI = {  # HD graphics, measured on slot 2 (lane playtest, 2026-10-28)
    "inv": (1047, 393, 43.8, 42.4),  # backpack 10 x 6: x0, y0, cell width, cell height (px)
    "body": {k: (x / 1600.0, y / 900.0) for k, (x, y) in {  # equipment boxes (itemtypes BodyLoc1 names)
        "rarm": (1092, 205), "head": (1262, 135), "neck": (1350, 152), "tors": (1262, 255), "larm": (1427, 205),
        "glov": (1092, 343), "rrin": (1180, 362), "belt": (1262, 362), "lrin": (1350, 362), "feet": (1440, 343)}.items()},
    "cube": (122, 107, 44.0, 42.3),  # Horadric Cube panel 10 x 8 (opened by a right click on the cube in the backpack)
    "transmute": (340 / 1600.0, 487 / 900.0),
    "wp_town": (340 / 1600.0, 222 / 900.0),  # waypoint panel, tab I, first line (Rogue Encampment)
}
AREA_TOWN, AREA_BLOODMOOR, AREA_COLDPLAINS = 1, 2, 3
WP_NUMBER_COLDPLAINS = 1  # levels.txt Waypoint of Cold Plains


class Ctx:
    def __init__(self, gc, cid, log):
        self.gc, self.g, self.cid, self.log = gc, gc.g, cid, log
        self.steps = {}
        self.shots = []
        self.picked = []  # items picked up from the ground this session (dicts of parse_items)

    def H(self, cmd, timeout=20):
        return self.gc.Hl(cmd, self.log, timeout)

    def note(self, msg):
        self.log.append("# " + msg)
        self.g.log("playthrough: " + msg)

    def step(self, name, status, note=""):
        self.steps[name] = (status, note)
        self.note("STEP %s %s %s" % (name, status, note))

    def shot(self, name):
        try:
            self.shots.append(self.gc.sh("pt_%s_%s" % (CLASS_NAMES[self.cid][:3], name)))
        except Exception as e:  # a failed capture must not end the class
            self.note("screenshot %s failed: %r" % (name, e))

    def items(self):
        ok, lines = self.gc.H("items", 20)
        return parse_items(lines)

    def stat(self, s, layer=None):
        return self.gc.rd("player", s, layer)

    def player(self):
        return self.gc.hstate()["player"]


def project(p, x, y):
    """Client fractions of a world sub-tile position seen from the player p (`state` player dict)."""
    dx, dy = x - p.get("x", 0), y - p.get("y", 0)
    return (PLAYER_PX[0] + (dx - dy) * 27) / 1600.0, (PLAYER_PX[1] + (dx + dy) * 13.5) / 900.0


def clamp_towards(fx, fy, radius=0.28):
    """A point on the line from the player to (fx, fy) no farther than `radius` (in client fractions, x scaled to the height): a
    click there walks the character towards a target that is off the screen."""
    px, py = PLAYER_PX[0] / 1600.0, PLAYER_PX[1] / 900.0
    dx, dy = (fx - px) * 16 / 9, fy - py
    d = (dx * dx + dy * dy) ** 0.5
    if d <= radius:
        return fx, fy
    k = radius / d
    return px + dx * k * 9 / 16, py + dy * k


def walk_to(c, x, y, reach=4, timeout=60):
    """Left clicks on the ground towards (x, y) until the character is within `reach` sub-tiles (the walk the player does)."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        c.gc.guard()
        p = c.player()
        if not p or c.gc.player_dead(p):  # a click on the death screen can hit its Continue button
            return False
        if ((p["x"] - x) ** 2 + (p["y"] - y) ** 2) ** 0.5 <= reach:
            return True
        fx, fy = clamp_towards(*project(p, x, y))
        c.g.click(fx, fy)
        time.sleep(1.5)
    return False


def hostile(st, max_dist=30):
    """Live monsters near the player (town NPCs excluded by being in town: the field has none)."""
    return [m for m in st["mons"] if m.get("dist", 99) <= max_dist and m.get("life", 1) > 0]


# ---------------------------------------------------------------- steps


def charstats_row(gc, cid):
    want = ["Amazon", "Sorceress", "Necromancer", "Paladin", "Barbarian", "Druid", "Assassin"][cid]
    return next((r for r in gc.table("charstats") if r.get("class") == want), {})


def step_create(c, name):
    """Save and Exit the character that is open (if any), Create New with this class and a new name: a level-1 Normal character."""
    gc, g = c.gc, c.g
    if g.in_game():
        for _ in range(3):
            gc.skip_cinematic()
            g.key("esc")
            time.sleep(1.5)
            g.click(*g.UI["save_exit"])
            time.sleep(8)
            for _ in range(10):
                if not g.in_game():
                    break
                time.sleep(3)
            if not g.in_game():
                break
        if g.in_game():
            return c.step("create", "BLOCKED", "Save and Exit of the previous character did not reach the menu")
        time.sleep(2)
        if not g.menu_visible():
            g.clear_intro(60)
            time.sleep(2)
            g.click(0.62, 0.40)
            time.sleep(1)
    ok = gc.create_character(CLASS_NAMES[c.cid], name)
    time.sleep(3)
    p = c.player() if ok else {}
    if not ok or p.get("class") != c.cid:
        return c.step("create", "FAIL" if ok else "BLOCKED", "in game %s, class %s" % (ok, p.get("class")))
    good = p.get("level") == 1 and p.get("area") == AREA_TOWN and p.get("difficulty") == 0
    c.shot("town")
    c.step("create", "PASS" if good else "FAIL", "%s level %s area %s difficulty %s life %s mana %s" % (
        name, p.get("level"), p.get("area"), p.get("difficulty"), p.get("life"), p.get("mana")))


def step_kit(c):
    """The starting kit and attributes against the built charstats.txt (Median's rows): item codes (belt potions counted by
    code) and strength / dexterity / vitality / energy."""
    row = charstats_row(c.gc, c.cid)
    have = c.items()
    c.kit = have
    want = {}
    for i in range(1, 11):
        code, n = row.get("item%d" % i), row.get("item%dcount" % i)
        if code:
            want[code] = want.get(code, 0) + int(n or 1)
    got = {}
    for it in have:
        got[it["code"]] = got.get(it["code"], 0) + 1
    missing = {k: v for k, v in want.items() if got.get(k, 0) < min(v, 1)}
    extra = sorted(k for k in got if k not in want)
    attrs = [(name, int(row.get(col) or 0), c.stat(sid)) for name, col, sid in
             (("str", "str", 0), ("ene", "int", 1), ("dex", "dex", 2), ("vit", "vit", 3))]
    bad_attr = [(n, w, h) for n, w, h in attrs if h != w]
    notes = "kit %s; attributes %s" % (", ".join("%s x%d" % kv for kv in sorted(got.items())),
                                       ", ".join("%s %s" % (n, h) for n, _, h in attrs))
    if missing or extra or bad_attr:
        return c.step("kit", "FAIL", notes + "; missing %s, not in charstats %s, attributes off %s" % (missing, extra, bad_attr))
    c.step("kit", "PASS", notes)


def step_field(c):
    """To the Blood Moor: the harness `level 2` (main has no walk verb yet; the town exit is ~100 sub-tiles of clicks)."""
    st = c.gc.goto(AREA_BLOODMOOR)
    ok = st["player"].get("area") == AREA_BLOODMOOR
    time.sleep(2)
    c.shot("field")
    c.step("field", "PASS" if ok else "BLOCKED", "area %s (by harness `level 2`)" % st["player"].get("area"))


def life_of(p):
    m = re.match(r"(\d+)/(\d+)", str(p.get("life", "")))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def belt_potions(items):
    """Healing potions in the belt (page 255 with a potion code: the belt shares the worn page, x = belt slot)."""
    return [i for i in items if i.get("page") == 255 and str(i.get("code", "")).startswith("hp")]


def hold_attack(c, mon_id, secs=2.5):
    """The left button held on a monster (as a player holds it): the virtual cursor follows the monster every 0.3 s, the game
    repeats the left skill while GetKeyState reports the button down. Returns the monster's last `state` dict or None (gone)."""
    g = c.g
    v = g.vinput()
    h = g.need_window()
    lp = lambda a, b: ((b & 0xFFFF) << 16) | (a & 0xFFFF)
    last, t0, down = None, time.time(), False
    try:
        while time.time() - t0 < secs:
            st = c.gc.hstate()
            p = st["player"]
            m = next((m for m in st["mons"] if m.get("id") == mon_id), None)
            if not p or m is None or c.gc.player_dead(p):
                break
            last = m
            fx, fy = project(p, m["mx"], m["my"])
            x, y = int(fx * 1600), int(fy * 900)
            v[2], v[3], v[1] = x, y, 1
            g.user32.PostMessageW(h, g.WM_MOUSEMOVE, 1 if down else 0, lp(x, y))
            if not down:
                time.sleep(0.15)
                v[4] |= 1
                g.user32.PostMessageW(h, g.WM_LBUTTONDOWN, 1, lp(x, y))
                down = True
            time.sleep(0.3)
    finally:
        v[4] &= ~1
        g.user32.PostMessageW(h, g.WM_LBUTTONUP, 0, lp(v[2], v[3]))
    return last


def spot_offsets(radius=3):
    """Sub-tile offsets around a kill spot, nearest first: where its drops can lie (a drop lands up to ~3 sub-tiles away)."""
    pts = [(dx, dy) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1) if dx * dx + dy * dy <= radius * radius + 1]
    return sorted(pts, key=lambda d: (d[0] * d[0] + d[1] * d[1], d))


def hover_label(c, fx, fy):
    """True when an item label shows above the cursor at (fx, fy): one capture with the cursor parked away, one with it there,
    compared in the strip above the cursor (D2R draws a ground item's name there on hover; Alt labels need a real key)."""
    g = c.g
    g.click(0.04, 0.06, move_only=True)
    time.sleep(0.15)
    a = c.gc.grab()
    g.click(fx, fy, move_only=True)
    time.sleep(0.35)
    b = c.gc.grab()
    found = c.gc.clusters(a, b, (fx - 0.13, fy - 0.08, fx + 0.13, fy + 0.005), thr=120, minblocks=2)
    return label_hit(found, fx, fy)


def scan_spot(c, x, y, budget=40):
    """Hover over the sub-tiles around (x, y); a label means an item (or gold) lies there: a left click picks it up (the character
    walks there). Returns the number of pickups (new items or more gold)."""
    if not walk_to(c, x, y, reach=3, timeout=25):
        return 0
    c.scans = getattr(c, "scans", 0) + 1
    if c.scans <= 3:
        c.shot("scan%d" % c.scans)
    got, t0 = 0, time.time()
    for dx, dy in spot_offsets():
        if time.time() - t0 > budget:
            break
        p = c.player()
        if not p or c.gc.player_dead(p) or [m for m in hostile(c.gc.hstate(), 10)]:
            break  # a monster came: the fight goes on first
        fx, fy = project(p, x + dx, y + dy)
        if not (0.03 < fx < 0.97 and 0.06 < fy < 0.84) or not hover_label(c, fx, fy):
            continue
        before, gold0 = c.items(), c.stat(14) or 0
        c.g.click(fx, fy)
        time.sleep(2.5)
        after, gold1 = c.items(), c.stat(14) or 0
        new, _, _ = item_changes(before, after)
        if new or gold1 > gold0:
            got += 1
            c.picked += new
            c.gold_picked = getattr(c, "gold_picked", 0) + max(0, gold1 - gold0)
            c.note("picked up at %+d,%+d of a kill spot: %s, gold %d -> %d" % (dx, dy, [(i["code"], i["page"], i["x"], i["y"]) for i in new], gold0, gold1))
    return got


def step_kill(c, want=4, timeout=600):
    """The character's own left skill (Attack at level 1) held on the nearest monster; after a kill with no monster near, the
    kill spot is scanned for drops (scan_spot). Goes on until `want` kills and at least one picked-up item, or the time is up
    (Median's Act 1 monsters drop an item on ~14 % of the kills: NoDrop 75 of 170 in `Act 1 H2H A`; gold almost never). Belt potions (keys 1-4) under half life; with none left and life under a quarter the character goes back to town
    (harness `level 1`) to regenerate, as a player runs away. Rule check: experience rises with the kills."""
    if c.steps.get("field", ("",))[0] != "PASS":
        return c.step("kill", "BLOCKED", "not in the field")
    xp0, lvl0 = c.stat(13), c.stat(12)
    kills, t0, holds, potions, retreats = 0, time.time(), 0, 0, 0
    counted, spots, hit, last_pos, tries, skip = set(), [], set(), {}, {}, set()
    while time.time() - t0 < timeout:
        if kills >= want and c.picked:
            break
        c.gc.guard()
        st = c.gc.hstate()
        p = st["player"]
        if not p:
            time.sleep(1)
            continue
        if c.gc.player_dead(p):
            handle_death(c, "died fighting in the Blood Moor")
            c.died_fighting = True
            if c.player().get("area") != AREA_BLOODMOOR:
                c.gc.goto(AREA_BLOODMOOR)
            spots = []
            continue
        if time.time() - getattr(c, "alive", {}).get("t", 0) > 15:
            snapshot(c)
        else:
            c.alive.update(x=p.get("x"), y=p.get("y"), area=p.get("area"))
        for m in st["corpses"]:
            if m["id"] in hit and m["id"] not in counted:
                counted.add(m["id"])
                kills += 1
                if m["id"] in last_pos:
                    spots.append(last_pos[m["id"]])
                c.note("kill %d: monster %d (class %d)" % (kills, m["id"], m.get("class", -1)))
        life, top = life_of(p)
        if top and life < 0.6 * top and time.time() - getattr(c, "drank", 0) > 3:
            belt = belt_potions(c.items())
            if belt:
                c.g.press(str(min(i["x"] for i in belt) + 1))
                c.drank = time.time()
                potions += 1
                time.sleep(0.4)
        if top and life < 0.35 * top:
            retreats += 1
            c.note("life %d/%d: back to town to regenerate" % (life, top))
            c.gc.goto(AREA_TOWN)
            t1 = time.time()
            while time.time() - t1 < 120 and life_of(c.player())[0] < 0.8 * top:
                time.sleep(5)
            c.gc.goto(AREA_BLOODMOOR)
            spots = []
            continue
        mons = hostile(st)
        near = [m for m in mons if m["dist"] <= 10]
        if not near and spots:
            scan_spot(c, *spots.pop())
            continue
        if not mons:
            c.g.click(*clamp_towards(0.75, 0.25))  # walk into the level: the next pack comes
            time.sleep(1.5)
            continue
        mons = [m for m in mons if m["id"] not in skip]
        if not mons:  # only unreachable ones near: walk elsewhere (a different direction every time)
            k = holds % 4
            c.g.click(*clamp_towards(*[(0.75, 0.25), (0.25, 0.25), (0.25, 0.7), (0.75, 0.7)][k]))
            holds += 1
            time.sleep(2)
            continue
        m = min(mons, key=lambda m: m["dist"])
        hit.add(m["id"])
        tries.setdefault(m["id"], [0, m.get("life")])
        last = hold_attack(c, m["id"])
        if last:
            last_pos[m["id"]] = (last["mx"], last["my"])
            tries[m["id"]][0] += 1
            if tries[m["id"]][0] >= 3 and last.get("life") == tries[m["id"]][1]:
                skip.add(m["id"])  # out of reach (behind a wall: the necromancer's run, slot 2): another target
                c.note("monster %d not hurt in 3 holds: skipped" % m["id"])
        holds += 1
    xp1, lvl1 = c.stat(13), c.stat(12)
    c.kills = kills
    c.shot("fight")
    note = "%d kills (%d holds, %d potions, %d retreats), experience %s -> %s, level %s -> %s" % (
        kills, holds, potions, retreats, xp0, xp1, lvl0, lvl1)
    if kills == 0:
        return c.step("kill", "PARTIAL" if getattr(c, "died_fighting", False) else "FAIL", note)
    if (xp1 or 0) <= (xp0 or 0):
        return c.step("kill", "FAIL", note + "; no experience for the kills")
    c.step("kill", "PASS", note)


def step_pickup(c):
    """The summary of the drops scan_spot picked up during the fight: items (by code and where they went: page 0 backpack, 255
    worn / belt) and gold."""
    if not getattr(c, "kills", 0):
        return c.step("pickup", "BLOCKED", "no kills")
    gold = getattr(c, "gold_picked", 0)
    _, lines = c.gc.H("ground", 20)  # the cross-check: what lies on the ground near the character now (the scan's misses)
    near = [d for d in parse_ground(lines) if d["dist"] <= 25]
    note = "items %s, gold +%d; `ground` lists %d item(s) within 25 now %s" % (
        [(i["code"], i["page"]) for i in c.picked], gold, len(near), [d.get("code") for d in near][:8])
    if c.picked:
        return c.step("pickup", "PASS", note)
    c.step("pickup", "PARTIAL" if gold else "SKIP", note + ("; gold only" if gold else "; no drop found around the kill spots"))


def inv_cell(x, y):
    x0, y0, cw, ch = UI["inv"]
    return (x0 + (x + 0.5) * cw) / 1600.0, (y0 + (y + 0.5) * ch) / 900.0


def cube_cell(x, y):
    x0, y0, cw, ch = UI["cube"]
    return (x0 + (x + 0.5) * cw) / 1600.0, (y0 + (y + 0.5) * ch) / 900.0


INV_PATCHES = ((1150, 140, 1210, 280), (1320, 200, 1380, 320))  # grey stone between the equipment boxes of the inventory panel


def grey_patches(means):
    """[(r, g, b) mean of each patch] -> the inventory panel is open: every patch is neutral grey stone (the scene behind is
    warm-tinted and darker; the panel has no red banner)."""
    return all(min(m) > 45 and max(m) - min(m) < 6 for m in means)


def inventory_open(c):
    from PIL import ImageStat
    im = c.g.grab_client(c.g.need_window()).convert("RGB")
    return grey_patches([ImageStat.Stat(im.crop(b)).mean for b in INV_PATCHES])


def open_inventory(c):
    if not inventory_open(c):
        c.g.key("i")
        time.sleep(1.2)
    return inventory_open(c)


def close_panels(c):
    for _ in range(3):
        if not inventory_open(c):
            return
        c.g.key("esc")
        time.sleep(0.8)


def item_size(code, tables):
    for t in ("weapons", "armor", "misc"):
        r = next((r for r in tables.get(t, []) if r.get("code") == code), None)
        if r:
            return int(r.get("invwidth") or 1), int(r.get("invheight") or 1)
    return 1, 1


def free_cell(items, tables, w=1, h=1, cols=10, rows=6):
    """Top-left (x, y) of the first backpack spot where a w x h item fits, None when the backpack is full."""
    used = set()
    for i in items:
        if i.get("page") == 0:
            iw, ih = item_size(str(i.get("code")), tables)
            used |= {(i["x"] + a, i["y"] + b) for a in range(iw) for b in range(ih)}
    for y in range(rows - h + 1):
        for x in range(cols - w + 1):
            if not any((x + a, y + b) in used for a in range(w) for b in range(h)):
                return x, y
    return None


BODY_NUM = {"head": 1, "neck": 2, "tors": 3, "rarm": 4, "larm": 5, "rrin": 6, "lrin": 7, "belt": 8, "feet": 9, "glov": 10}


def worn(items, tables):
    """Worn items: page 255 with a body location type (the belt's potions share page 255, x = belt slot; an item on the cursor
    reads page 255 too, so `worn_on` checks x as well)."""
    return [i for i in items if i.get("page") == 255 and body_loc_of(str(i.get("code")), tables)]


def worn_on(item, loc):
    """The item is worn on that body location: page 255 and x = the location's number (torso 3, right hand 4 ...; slot 2: the kit's
    600 read x=3, 151 x=4). Weapons and shields may sit in either hand."""
    if not item or item.get("page") != 255:
        return False
    nums = {BODY_NUM[loc]} | ({4, 5} if loc in ("rarm", "larm") else set()) | ({6, 7} if loc in ("rrin", "lrin") else set())
    return item.get("x") in nums


def put_down_cursor(c, tables):
    """A click on a free backpack cell with the inventory open: whatever hangs on the cursor goes there (nothing happens when the
    cursor is empty). An item on the cursor blocks every later click (cube, waypoint line, skills)."""
    if not open_inventory(c):
        return False
    cell = free_cell(c.items(), tables, 2, 4) or free_cell(c.items(), tables, 1, 1)
    if cell:
        c.g.click(*inv_cell(*cell))
        time.sleep(1.0)
    return True


def step_equip(c):
    """A picked-up wearable item worn through the inventory panel. A pickup with the matching body location empty puts the item
    on at once (seen on slot 2: a Quilted Armor picked up by a naked character went onto the torso); such an item is taken off
    into the backpack and put on again, so the clicks are exercised either way. A refusal (requirements) is a SKIP."""
    tables = {t: c.gc.table(t) for t in ("itemtypes", "armor", "weapons", "misc")}
    have = c.items()
    picked_ids = {i["id"] for i in c.picked}
    cands = [i for i in have if i["id"] in picked_ids and body_loc_of(str(i["code"]), tables)
             and (i.get("page") == 0 or worn_on(i, body_loc_of(str(i["code"]), tables)))]
    if not cands:
        return c.step("equip", "SKIP", "no wearable item among the pickups %s" % [i["code"] for i in c.picked])
    it = cands[0]
    code, loc = str(it["code"]), body_loc_of(str(it["code"]), tables)
    if not open_inventory(c):
        return c.step("equip", "BLOCKED", "the inventory panel did not open")
    notes = []
    if worn_on(it, loc):
        notes.append("%s was worn on pickup (%s empty)" % (code, loc))
        cell = free_cell(have, tables, *item_size(code, tables))
        if cell is None:
            close_panels(c)
            return c.step("equip", "SKIP", "; ".join(notes) + "; backpack full, not taken off")
        c.g.click(*UI["body"][loc])
        time.sleep(0.8)
        c.g.click(*inv_cell(*cell))
        time.sleep(1.0)
        it = next((i for i in c.items() if i["id"] == it["id"]), {})
        notes.append("taken off to the backpack: page %s at %s,%s" % (it.get("page"), it.get("x"), it.get("y")))
        if it.get("page") != 0:
            close_panels(c)
            return c.step("equip", "FAIL", "; ".join(notes))
    c.g.click(*inv_cell(it["x"], it["y"]))
    time.sleep(0.8)
    c.g.click(*UI["body"][loc])
    time.sleep(1.2)
    c.shot("equip")
    after = c.items()
    now = next((i for i in after if i["id"] == it["id"]), {})
    if worn_on(now, loc):
        put_down_cursor(c, tables)  # a swapped-out item (the Druid's two-handed bow) hangs on the cursor
        close_panels(c)
        return c.step("equip", "PASS", "; ".join(notes + ["%s put on %s with the inventory clicks (x=%s)" % (code, loc, now.get("x"))]))
    put_down_cursor(c, tables)  # not worn: a refused item stays on the cursor
    c.shot("equip_refused")
    close_panels(c)
    c.step("equip", "SKIP", "; ".join(notes + ["%s on %s not taken (page %s; requirements? level %s, str %s, dex %s)" % (
        code, loc, now.get("page"), c.stat(12), c.stat(0), c.stat(2))]))


VENDORS = {154: "Charsi", 148: "Akara", 147: "Gheed"}  # Trade is the second option of all three (line 3 with the name)
SHOP = {"grid": (135, 183, 41.0), "misc_tab": (497 / 1600.0, 170 / 900.0), "sell_at": (480 / 1600.0, 450 / 900.0)}
MENU_TRADE_PX = 57  # Charsi's box, slot 2: frame top 192, lines at 208 (name), 229 (Talk), 249 (Trade/Repair), 269 (Cancel)


def shop_cell(x, y):
    x0, y0, cs = SHOP["grid"]
    return (x0 + (x + 0.5) * cs) / 1600.0, (y0 + (y + 0.5) * cs) / 900.0


def menu_frame(rgb, y0=40, y1=500, min_run=80, max_run=220, edge=25):
    """The NPC menu's gold frame in a capture (rows x columns x RGB, ints): the topmost run of `min_run` .. `max_run` frame-coloured
    pixels in rows y0..y1 (slot 2: (140, 117, 68) along the box top, ~120 px wide for Charsi's menu) with a vertical frame edge going
    down from both of its ends (`edge` rows). The greeting's text box has the same frame but is ~330 px wide, and its top line is cut
    into shorter pieces by ornaments whose ends have no edge below (slot 4, the Amazon's runs: the click went into it).
    Returns (centre x, top y) in px or None."""
    def gold(px):
        return 110 <= px[0] <= 170 and 90 <= px[1] <= 140 and 45 <= px[2] <= 90 and px[0] - px[2] > 45

    def vertical(x, y):
        rows = rgb[y + 2:y + 2 + edge]
        hits = sum(1 for r in rows if any(gold(r[xx]) for xx in range(max(0, x - 2), min(len(r), x + 3))))
        return len(rows) == edge and hits >= 0.7 * edge

    for y in range(y0, min(y1, len(rgb) - edge - 2)):
        row = rgb[y]
        x = 0
        while x < len(row):
            if not gold(row[x]):
                x += 1
                continue
            start = x
            while x < len(row) and gold(row[x]):
                x += 1
            if min_run <= x - start <= max_run and vertical(start, y) and vertical(x - 1, y):
                return (start + x - 1) / 2.0, y
    return None


def find_vendor(c):
    """A vendor within 40 of the character; when none, the character walks a round of the town (8 directions, ~15 sub-tiles)."""
    for d in [(0, 0), (1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]:
        if d != (0, 0):
            p = c.player()
            walk_to(c, p["x"] + 15 * d[0], p["y"] + 15 * d[1], reach=4, timeout=15)
        npc = next((m for m in sorted(c.gc.hstate()["mons"], key=lambda m: m["dist"]) if m.get("class") in VENDORS), None)
        if npc:
            return npc
    return None


def step_vendor(c):
    """A town vendor (Charsi, Akara or Gheed, whoever is in reach): walk there (clicks), click them (the first talk plays a
    greeting, the menu opens when it ends), Trade (the second option: line 3 of the box), sell Town Portal scrolls of the kit (lift,
    drop on the shop grid: gold rises; Median buys for 1 gold, npc.txt buy mult 128), then right click the Misc tab's last column
    until something is bought (gold falls, the item arrives)."""
    if c.player().get("area") != AREA_TOWN:
        c.gc.goto(AREA_TOWN)
    close_panels(c)
    npc = find_vendor(c)
    if npc is None:
        return c.step("vendor", "BLOCKED", "no vendor (Charsi, Akara, Gheed) found in town")
    who = VENDORS[npc["class"]]
    walk_to(c, npc["mx"], npc["my"], reach=5)
    frame = None
    for attempt in range(3):
        npc = next((m for m in c.gc.hstate()["mons"] if m.get("id") == npc["id"]), npc)
        c.gc.click_unit(npc["id"])
        c.g.click(0.04, 0.06, move_only=True)  # the cursor off the menu (hover tints the lines)
        for _ in range(8):  # the first talk plays the greeting (~10 s); the menu follows
            time.sleep(2)
            frame = menu_frame(c.gc.grab().tolist())
            if frame:
                break
        if frame:
            break
    if not frame:
        c.shot("vendor_nomenu")
        return c.step("vendor", "FAIL", "no NPC menu after 3 talks to %s" % who)
    c.shot("vendor_menu")
    c.g.click(frame[0] / 1600.0, (frame[1] + MENU_TRADE_PX) / 900.0)
    time.sleep(2.5)
    if not inventory_open(c):
        c.shot("vendor_notrade")
        close_panels(c)
        return c.step("vendor", "FAIL", "Trade did not open %s's trade window (menu frame at %s)" % (who, frame))
    notes = ["%s's trade window open" % who]
    have = c.items()
    gold0 = c.stat(14) or 0
    sold = 0
    for scroll in [i for i in have if i["code"] == "tsc" and i.get("page") == 0]:  # 1 gold each (npc.txt buy mult 128)
        if (c.stat(14) or 0) >= 40:
            break
        c.g.click(*inv_cell(scroll["x"], scroll["y"]))
        time.sleep(0.8)
        c.g.click(*SHOP["sell_at"])
        time.sleep(1.2)
        sold += not any(i["id"] == scroll["id"] for i in c.items())
    notes.append("sold %d Town Portal scrolls, gold %d -> %d" % (sold, gold0, c.stat(14) or 0))
    c.g.click(*SHOP["misc_tab"])
    time.sleep(1.2)
    c.shot("shop")
    bought = None
    for col, row in [(9, r) for r in range(10)] + [(8, r) for r in range(10)]:  # Median's potions, then the scrolls just sold
        before, g0 = c.items(), c.stat(14) or 0
        c.g.click(*shop_cell(col, row), button="right")
        time.sleep(1.0)
        new, _, _ = item_changes(before, c.items())
        g1 = c.stat(14) or 0
        if new:
            bought = (new[0]["code"], g0, g1)
            break
    if not bought:  # the price of a scroll bought back, for the record (the tooltip shows "Cost: n")
        c.g.click(*shop_cell(8, 1), move_only=True)
        time.sleep(1.0)
        c.shot("shop_price")
    close_panels(c)
    if bought:
        notes.append("bought %s for %d gold (%d -> %d)" % (bought[0], bought[1] - bought[2], bought[1], bought[2]))
        ok = bought[2] < bought[1]
        return c.step("vendor", "PASS" if ok else "FAIL", "; ".join(notes) + ("" if ok else "; no gold taken"))
    c.step("vendor", "PARTIAL", "; ".join(notes + ["nothing affordable in the Misc tab's last two columns with %d gold (Median: "
                                                   "vendors pay 1 gold, gold drops are rare; price tooltip in shop_price)" % (c.stat(14) or 0)]))


def step_cube(c):
    """Median's one-item recipe 'Clue gem cycle' (cubemain: input 01-, output 02-): the starting kit's Clue Gem into the cube,
    Transmute. The cube opens with a right click on it in the backpack."""
    have = c.items()
    box = next((i for i in have if i["code"] == "box" and i.get("page") == 0), None)
    gem = next((i for i in have if i["code"] == "01-" and i.get("page") == 0), None)
    if not box or not gem:
        return c.step("cube", "SKIP", "kit without cube or clue gem (box %s, 01- %s)" % (bool(box), bool(gem)))
    if not open_inventory(c):
        return c.step("cube", "BLOCKED", "the inventory panel did not open")
    put_down_cursor(c, {t: c.gc.table(t) for t in ("itemtypes", "armor", "weapons", "misc")})
    have = c.items()
    box = next((i for i in have if i["code"] == "box" and i.get("page") == 0), None)
    gem = next((i for i in have if i["code"] == "01-" and i.get("page") == 0), None)
    if not box or not gem:
        close_panels(c)
        return c.step("cube", "SKIP", "kit without cube or clue gem in the backpack (box %s, 01- %s)" % (bool(box), bool(gem)))
    c.g.click(*inv_cell(box["x"], box["y"]), button="right")
    time.sleep(1.5)
    c.g.click(*inv_cell(gem["x"], gem["y"]))
    time.sleep(0.8)
    c.g.click(*cube_cell(0, 0))
    time.sleep(0.8)
    mid = c.items()
    in_cube = any(i["id"] == gem["id"] and i.get("page") == 3 for i in mid)
    c.g.click(*UI["transmute"])
    time.sleep(1.5)
    c.shot("cube")
    after = c.items()
    out = [i for i in after if i["code"] == "02-"]
    close_panels(c)
    note = "01- into the cube: %s; cube after Transmute: %s" % (in_cube, [(i["code"], i.get("page")) for i in after if i.get("page") == 3])
    if out and not any(i["code"] == "01-" for i in after):
        return c.step("cube", "PASS", note)
    c.step("cube", "FAIL" if in_cube else "BLOCKED", note)


def waypoint_objects(c):
    fn23 = {int(r["*ID"]) for r in c.gc.table("objects") if r.get("OperateFn") == "23" and re.fullmatch(r"\d+", r.get("*ID", ""))}
    ok, lines = c.gc.H("objects", 20)
    return [o for o in parse_objects(lines) if o.get("class") in fn23]


def wp_bit(c):
    _, lines = c.gc.H("waypoint n %d get" % WP_NUMBER_COLDPLAINS)
    m = re.search(r"= (\d)", " ".join(lines))
    return int(m.group(1)) if m else None


def step_waypoint(c):
    """Cold Plains (harness `level 3 warp 13`: arrives at the waypoint), a click on the waypoint object (it activates and the
    panel opens), a click on the Rogue Encampment line: the character is in town."""
    c.gc.revive_if_dead()
    c.H("level %d warp 13" % AREA_COLDPLAINS)
    t0 = time.time()
    while time.time() - t0 < 40 and c.player().get("area") != AREA_COLDPLAINS:
        time.sleep(2)
    if c.player().get("area") != AREA_COLDPLAINS:
        return c.step("waypoint", "BLOCKED", "did not reach Cold Plains")
    time.sleep(2)
    wps = waypoint_objects(c)
    if not wps:
        return c.step("waypoint", "FAIL", "no waypoint object in Cold Plains")
    wp = min(wps, key=lambda o: o["dist"])
    b0 = wp_bit(c)
    b1 = b0
    for _ in range(3):
        c.g.click(*project(c.player(), wp["x"], wp["y"]))
        time.sleep(3)
        b1 = wp_bit(c)
        if b1 == 1:
            break
    c.shot("wp_panel")
    c.g.click(*UI["wp_town"])
    t0 = time.time()
    while time.time() - t0 < 20 and c.player().get("area") != AREA_TOWN:
        time.sleep(2)
    area = c.player().get("area")
    note = "Cold Plains waypoint bit %s -> %s after the click; area after the town line %s" % (b0, b1, area)
    if b1 == 1 and area == AREA_TOWN:
        return c.step("waypoint", "PASS", note)
    c.step("waypoint", "FAIL" if b1 != 1 else "PARTIAL", note)


def leave_game(gc):
    gc.g.key("esc")
    time.sleep(1.5)
    gc.g.click(*gc.g.UI["save_exit"])
    time.sleep(9)
    for _ in range(8):
        if not gc.g.in_game():
            break
        time.sleep(3)
    return not gc.g.in_game()


def step_reload(c, name):
    """Save and Exit, Play the same character: the items (code, page, position), level, experience, gold and the Cold Plains
    waypoint come back."""
    gc = c.gc
    close_panels(c)
    before = kit_signature(c.items())
    vals0 = [c.stat(s) for s in (12, 13, 14, 15)]
    w0 = wp_bit(c)
    if not leave_game(gc):
        return c.step("reload", "BLOCKED", "Save and Exit did not leave the game")
    time.sleep(2)
    card = gc.card_of(name)
    if card is None or not gc.enter_game(card):
        return c.step("reload", "FAIL", "the character did not load again (card %s)" % card)
    time.sleep(3)
    after = kit_signature(c.items())
    vals1 = [c.stat(s) for s in (12, 13, 14, 15)]
    w1 = wp_bit(c)
    lost = [x for x in before if x not in after]
    new = [x for x in after if x not in before]
    note = "items %d -> %d, level/xp/gold/bank %s -> %s, waypoint %s -> %s" % (len(before), len(after), vals0, vals1, w0, w1)
    if lost or new or vals0 != vals1 or w0 != w1:
        return c.step("reload", "FAIL", note + "; lost %s, new %s" % (lost, new))
    c.step("reload", "PASS", note)


def snapshot(c):
    """What a death changes: gold, experience, worn items, where the character stands."""
    tables = {t: c.gc.table(t) for t in ("itemtypes", "armor", "weapons", "misc")}
    p = c.player()
    c.alive = {"gold": c.stat(14), "xp": c.stat(13), "worn": sorted(i["code"] for i in worn(c.items(), tables)),
               "x": p.get("x"), "y": p.get("y"), "area": p.get("area"), "t": time.time()}
    return c.alive


def respawn(c):
    """Esc on the death screen until the character stands in town again; True when alive."""
    for _ in range(8):
        c.g.press("esc")
        time.sleep(3)
        p = c.player()
        if p and not c.gc.player_dead(p):
            return True
    return False


def recover_corpse(c, area, x, y):
    """Back to the death spot (harness `level <area>`: the walk from town is ~100 sub-tiles of clicks) and a click on the corpse
    (clicks on the sub-tiles around the spot until the worn items are back). Returns the worn codes afterwards."""
    tables = {t: c.gc.table(t) for t in ("itemtypes", "armor", "weapons", "misc")}
    c.gc.goto(area)
    walk_to(c, x, y, reach=2, timeout=40)
    p = c.player()
    if p and c.gc.player_dead(p):
        c.note("died again on the way back to the corpse")
        respawn(c)
        return None
    for dx, dy in spot_offsets(2)[:9]:
        if worn(c.items(), tables):
            break
        p = c.player()
        if p and c.gc.player_dead(p):  # killed again on the way (naked, the same pack waits at the corpse): no recovery
            c.note("died again on the way back to the corpse")
            respawn(c)
            return None
        if not p:
            break
        c.g.click(*project(p, x + dx, y + dy))
        time.sleep(2.5)
    return sorted(i["code"] for i in worn(c.items(), tables))


def handle_death(c, cause):
    """The character died (`cause`): screenshot, respawn, the 1.13c rules on what is kept (no experience loss in Normal, the worn
    items stay on the corpse), the corpse picked up again. The first death is the class's `death` step."""
    before = dict(getattr(c, "alive", None) or {})
    p_dead = c.player()  # the dead character's `state` still says where it fell: the corpse lies there
    if p_dead:
        before.update(x=p_dead.get("x"), y=p_dead.get("y"), area=p_dead.get("area"))
    time.sleep(2)
    c.shot("dead%d" % (len([k for k in c.steps if k == "death"]) + getattr(c, "deaths", 0)))
    c.deaths = getattr(c, "deaths", 0) + 1
    gold_dead = c.stat(14)
    if not respawn(c):
        return c.step("death", "FAIL", "%s; no respawn after Esc" % cause) if "death" not in c.steps else None
    time.sleep(2)
    p = c.player()
    c.shot("respawn")
    tables = {t: c.gc.table(t) for t in ("itemtypes", "armor", "weapons", "misc")}
    worn_now = sorted(i["code"] for i in worn(c.items(), tables))
    xp_now, gold_now = c.stat(13), c.stat(14)
    back = recover_corpse(c, before.get("area") or AREA_BLOODMOOR, before.get("x", 0), before.get("y", 0)) if before.get("worn") else []
    note = "%s; respawn area %s; gold %s -> %s (at death %s), experience %s -> %s, worn %s -> %s after the respawn, corpse picked up: %s" % (
        cause, p.get("area"), before.get("gold"), gold_now, gold_dead, before.get("xp"), xp_now, before.get("worn"), worn_now,
        back if before.get("worn") else "nothing worn")
    bad = []
    if p.get("area") != AREA_TOWN:
        bad.append("respawn not in town")
    if before.get("xp") is not None and xp_now is not None and xp_now < before["xp"]:
        bad.append("experience lost in Normal")
    if before.get("worn") and worn_now:
        bad.append("worn items not left on the corpse")
    if before.get("worn") and back is not None and sorted(back) != sorted(before["worn"]):
        bad.append("corpse did not give the worn items back")
    partial = before.get("worn") and back is None  # killed again before reaching the corpse: a gameplay outcome, not a defect
    if "death" in c.steps:
        return c.note("another death: " + note + ("; " + ", ".join(bad) if bad else ""))
    c.step("death", "FAIL" if bad else ("PARTIAL" if partial else "PASS"), note + ("; " + ", ".join(bad) if bad else "") + (
        "; died again on the way back to the corpse (not recovered)" if partial and not bad else ""))


def step_death(c, timeout=150):
    """Die once to the field's monsters, unless the character died already while fighting (then that death was the step). Stand
    among the Blood Moor's monsters without potions; half way through the time the harness spawns six of the nearest monster's
    class next to the character (`spawn`, documented). Then handle_death."""
    if "death" in c.steps:
        return
    gc = c.gc
    st = gc.goto(AREA_BLOODMOOR)
    if st["player"].get("area") != AREA_BLOODMOOR:
        return c.step("death", "BLOCKED", "not in the field")
    snapshot(c)
    t0, spawned = time.time(), False
    while time.time() - t0 < timeout:
        gc.guard()
        st = gc.hstate()
        p = st["player"]
        if p and gc.player_dead(p):
            return handle_death(c, "died to the field's monsters" + (" (after the spawn)" if spawned else ""))
        if p:
            c.alive.update(x=p.get("x"), y=p.get("y"), area=p.get("area"))  # the corpse lies where the character fell
        mons = hostile(st)
        if p and mons and min(m["dist"] for m in mons) > 6:
            m = min(mons, key=lambda m: m["dist"])  # walk into the pack
            c.g.click(*clamp_towards(*project(p, m["mx"], m["my"])))
        elif p and not mons:
            c.g.click(0.70, 0.30)
        if not spawned and time.time() - t0 > timeout / 2:
            cls = mons[0]["class"] if mons else 0
            c.note("not dead after %d s: harness `spawn %d 6` next to the character" % (time.time() - t0, cls))
            c.H("spawn %d 6" % cls)
            spawned = True
        time.sleep(3)
    c.step("death", "BLOCKED", "the character did not die in %d s" % timeout)


# ---------------------------------------------------------------- one class, all classes


def play_class(gc, cid, stamp):
    """The whole path for one class; returns (Ctx, name)."""
    log = []
    c = Ctx(gc, cid, log)
    name = char_name(CLASS_NAMES[cid], stamp)
    steps = [("create", lambda: step_create(c, name)), ("kit", lambda: step_kit(c)), ("field", lambda: step_field(c)),
             ("kill", lambda: step_kill(c)), ("pickup", lambda: step_pickup(c)), ("equip", lambda: step_equip(c)),
             ("cube", lambda: step_cube(c)), ("waypoint", lambda: step_waypoint(c)), ("reload", lambda: step_reload(c, name)),
             ("vendor", lambda: step_vendor(c)), ("death", lambda: step_death(c))]
    only = selected_steps(os.environ.get("MXL_PT_STEPS"))
    for sname, fn in steps:
        if sname != "create" and c.steps.get("create", ("",))[0] != "PASS":
            break
        if only and sname not in only:
            continue
        p = c.player() if sname != "create" else {}
        if p and gc.player_dead(p):  # a death the step before did not handle
            handle_death(c, "found dead before %s" % sname)
        elif p:
            snapshot(c)  # what a death in this step is compared with
        try:
            fn()
        except Exception as e:  # the next step still runs: one broken step must not hide the rest
            c.step(sname, "BLOCKED", "script error %r" % (e,))
            if "ABORT" in str(e):
                raise
        if not gc.g.game_pids():
            c.step(sname, "FAIL", "the game process is gone (crash?)")
            break
    return c, name


def run(gc, classes=None):
    """game_checks `playthrough`: every classic class (MXL_PT_CLASSES=0,4 for a subset; MXL_PT_STEPS=kit,vendor for a subset of
    the steps), one row per class."""
    sel = classes
    if sel is None:
        env = os.environ.get("MXL_PT_CLASSES")
        sel = [int(x) for x in env.split(",")] if env else list(range(7))
    stamp = int(time.time())
    for cid in sel:
        mark = gc.engine_mark()
        c, name = play_class(gc, cid, stamp + cid)
        only = selected_steps(os.environ.get("MXL_PT_STEPS"))
        verdict = class_verdict(c.steps, only)
        gc.finish("playthrough %s (%s)" % (CLASS_NAMES[cid], name), verdict != "FAIL", class_note(c.steps), mark, c.shots, c.log,
                  partial=None if verdict == "PASS" else "steps not PASS: " + ", ".join(
                      s for s in STEPS if (only is None or s in only) and c.steps.get(s, ("NOT RUN",))[0] != "PASS"))
        if not gc.g.game_pids():  # a crash: back to the menu for the next class
            gc.to_menu()
