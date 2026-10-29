"""Lane act1start: a play tester's first hour of Act 1 on the player path (check `act1_hour` of tools/game_checks.py).

Per class of MXL_HOUR_CLASSES (default sorceress, barbarian, amazon) a fresh level-1 Normal character, mortal (no god mode,
no harness levels, no travel help): out of the Rogue Encampment by clicks (the gate found on the game's walk collision,
game_checks.relp_walk_level), fights in the Blood Moor with the left button held on the monster (playthrough.hold_attack),
belt potions under half life, ground drops picked up by a click on them, on into the Cold Plains, its waypoint clicked, back
into the Blood Moor and into the Den of Evil by a click on its entrance, and fights there until the class's time is up
(MXL_HOUR_MIN, default 20 minutes). A death: Esc on the death screen (respawn in town), out of the camp again, the corpse
clicked. Reads only (the harness's `state`, `walkmap`, `presets`, `objects`, `ground`, `stat`, `waypoint ... get`) steer the
clicks; nothing is moved, granted or killed by the harness.

Recorded per class: deaths (and what stood near), level and experience reached, kills by monster class, drops seen and picked
up, the life lost per held attack (the monsters' hits), the level and life of the first Blood Moor monsters, engine asserts,
ERROR text is judged on the screenshots. Not done (limits of the script, not of the game): stat and skill points stay unspent.
"""
import os
import time

AREA_TOWN, AREA_BLOODMOOR, AREA_COLDPLAINS, AREA_DEN = 1, 2, 3, 8
CLASSES = ("sorceress", "barbarian", "amazon")
SAMPLE_MONSTERS = 8  # Blood Moor monsters whose level and life are read (stat 12, `state` life)


class Died(Exception):
    """The character died: the phase stops, the class recovers (respawn, walk out, corpse) and goes on."""


def fight_summary(hits):
    """hits: [(life lost in one held attack, monsters within 5)] -> (holds with a loss, largest loss, mean loss per monster)."""
    lost = [(d, n) for d, n in hits if d > 0]
    if not lost:
        return 0, 0, 0.0
    return len(lost), max(d for d, _ in lost), sum(d for d, _ in lost) / max(1, sum(max(1, n) for _, n in lost))


class Hour:
    def __init__(self, gc, cls, stamp, log):
        import playthrough as pt
        self.gc, self.pt, self.cls, self.log = gc, pt, cls, log
        self.c = pt.Ctx(gc, pt.CLASS_NAMES.index(cls), log)
        self.name = "Hr" + pt.char_name(cls, stamp)[2:]
        self.deaths, self.kills, self.hits, self.sample, self.drops, self.picked = [], {}, [], {}, [], []
        self.phases, self.counted, self.skip = {}, set(), set()
        self.t_end = 0

    # -------------------------------------------------------------- fighting (player path: held left button, potions)
    def hostile(self, st):
        p = st["player"]
        if p.get("area") == AREA_TOWN:
            return []
        return [m for m in self.pt.hostile(st, 12) if m.get("area") == p.get("area") and m["id"] not in self.skip]

    def check_dead(self, p):
        if p and self.gc.player_dead(p):
            raise Died("area %s at %s,%s" % (p.get("area"), p.get("x"), p.get("y")))

    def drink(self, p):
        life, top = self.pt.life_of(p)
        if top and life < 0.5 * top and time.time() - getattr(self, "drank", 0) > 3:
            belt = self.pt.belt_potions(self.c.items())
            if belt:
                self.c.g.press(str(min(i["x"] for i in belt) + 1))
                self.drank = time.time()
                self.c.note("life %d/%d: belt potion" % (life, top))

    def fight(self, holds=40):
        """Fights every monster within 12 (nearest first) until none is left; counts kills, the life lost per held attack and
        samples the level / life of the first monsters. Raises Died."""
        tries = {}
        for _ in range(holds):
            self.gc.guard()
            st = self.gc.hstate()
            p = st["player"]
            self.check_dead(p)
            self.count_kills(st)
            mons = self.hostile(st)
            if not mons:
                return
            self.drink(p)
            m = min(mons, key=lambda m: m["dist"])
            self.read_sample(m)
            life0 = self.pt.life_of(p)[0]
            near = len([q for q in mons if q["dist"] <= 5])
            last = self.pt.hold_attack(self.c, m["id"])
            p1 = self.c.player()
            self.check_dead(p1)
            self.hits.append((life0 - self.pt.life_of(p1)[0], near))
            t = tries.setdefault(m["id"], [0, m.get("life")])
            t[0] += 1
            if last and t[0] >= 4 and last.get("life") == t[1]:
                self.skip.add(m["id"])  # not hurt in 4 holds: out of reach (a wall, a cliff), another target
        self.count_kills(self.gc.hstate())

    def read_sample(self, m):
        if len(self.sample) >= SAMPLE_MONSTERS or m["id"] in self.sample or m.get("area") != AREA_BLOODMOOR:
            return
        lvl = self.gc.rd("mon:%d" % m["id"], 12)
        self.sample[m["id"]] = (m.get("class"), lvl, m.get("life"))

    def count_kills(self, st):
        for m in st["corpses"]:
            if m["id"] not in self.counted and m.get("area") == st["player"].get("area"):
                self.counted.add(m["id"])
                self.kills[m.get("class")] = self.kills.get(m.get("class"), 0) + 1
                self.pick_up()

    def pick_up(self):
        """Items that fell near the character: a click on each (the character walks there and picks it up), nearest first."""
        _, lines = self.gc.H("ground", 15)
        for it in sorted(self.pt.parse_ground(lines), key=lambda d: d["dist"])[:4]:
            if it["dist"] > 12 or it["id"] in {d["id"] for d in self.drops}:
                continue
            self.drops.append(it)
            p = self.c.player()
            fx, fy = self.pt.project(p, it["x"], it["y"])
            if not (0.05 < fx < 0.95 and 0.08 < fy < 0.80):
                continue
            before = {i.get("id") for i in self.c.items()}
            self.c.g.click(fx, fy)
            time.sleep(2.5)
            new = [i for i in self.c.items() if i.get("id") not in before]
            if new:
                self.picked += [i["code"] for i in new]
                self.c.note("picked up %s" % [i["code"] for i in new])

    def fight_cb(self):
        if time.time() > self.t_end:
            raise TimeoutError("class time up")
        self.fight()

    # -------------------------------------------------------------- phases
    def walk_out(self):
        ok, _, note = self.gc.relp_walk_out(self.c, self.log, budget=480, fight=self.fight_cb)
        self.phases["walk out"] = ("PASS" if ok else "BLOCKED", note)
        return ok

    def cold_plains(self):
        if self.c.player().get("area") == AREA_TOWN and not self.walk_out():
            return False
        ok, note = self.gc.relp_walk_level(self.c, AREA_COLDPLAINS, self.log, budget=600, fight=self.fight_cb,
                                           anchor=self.town_centre, plans_max=30)
        self.phases["Cold Plains"] = ("PASS" if ok else "BLOCKED", note)
        return ok

    def waypoint(self):
        c, gc, pt = self.c, self.gc, self.pt
        fn23 = {int(r["*ID"]) for r in gc.table("objects") if r.get("OperateFn") == "23" and str(r.get("*ID", "")).isdigit()}
        spot = [q for q in gc.parse_presets(gc.H("presets 2")[1]) if q["class"] in fn23]
        objs = [o for o in pt.waypoint_objects(c)]
        where = (objs[0]["x"], objs[0]["y"]) if objs else ((spot[0]["x"], spot[0]["y"]) if spot else None)
        if where is None:
            self.phases["waypoint"] = ("BLOCKED", "no waypoint preset or object in Cold Plains")
            return False
        gc.relp_walk_to(c, where[0], where[1], lambda: abs(c.player()["x"] - where[0]) + abs(c.player()["y"] - where[1]) < 9,
                        self.log, budget=300, fight=self.fight_cb)
        b0 = pt.wp_bit(c)
        b1 = b0
        for _ in range(4):
            self.fight()
            objs = pt.waypoint_objects(c)
            if objs:
                wp = min(objs, key=lambda o: o["dist"])
                c.g.click(*pt.project(c.player(), wp["x"], wp["y"]))
            time.sleep(3)
            b1 = pt.wp_bit(c)
            if b1 == 1:
                break
        c.shot("hour_wp")
        c.g.key("esc")
        time.sleep(1)
        self.phases["waypoint"] = ("PASS" if b1 == 1 else "FAIL", "Cold Plains waypoint bit %s -> %s after the click" % (b0, b1))
        return b1 == 1

    def den(self):
        c, gc = self.c, self.gc
        if c.player().get("area") == AREA_TOWN and not self.walk_out():
            return False
        if c.player().get("area") != AREA_BLOODMOOR:
            ok, note = gc.relp_walk_level(c, AREA_BLOODMOOR, self.log, budget=400, fight=self.fight_cb, plans_max=20)
            if not ok:
                self.phases["Den of Evil"] = ("BLOCKED", "back to the Blood Moor: " + note)
                return False
        tiles = [q for q in gc.parse_presets(gc.H("presets 5")[1])]
        if not tiles:
            self.phases["Den of Evil"] = ("BLOCKED", "no warp preset in the Blood Moor")
            return False
        t = tiles[0]
        inside = lambda: c.player().get("area") == AREA_DEN  # noqa: E731
        gc.relp_walk_to(c, t["x"], t["y"], lambda: inside() or abs(c.player()["x"] - t["x"]) + abs(c.player()["y"] - t["y"]) < 8,
                        self.log, budget=400, fight=self.fight_cb)
        for ox, oy in ((0, 0), (1, 1), (-1, 1), (1, -1), (2, 2)):
            if inside():
                break
            self.fight()
            c.g.click(*self.pt.project(c.player(), t["x"] + ox, t["y"] + oy))
            time.sleep(4)
        if not inside():
            self.phases["Den of Evil"] = ("BLOCKED", "entrance at %s,%s clicked, still in area %s" % (t["x"], t["y"], c.player().get("area")))
            return False
        c.shot("hour_den")
        k0 = sum(self.kills.values())
        p0 = c.player()
        gc.relp_walk_level(c, 9999, self.log, budget=max(0, self.t_end - time.time() - 30), fight=self.fight_cb,
                           anchor=(p0["x"], p0["y"]), plans_max=40)
        self.phases["Den of Evil"] = ("PASS", "entered by a click on the entrance; %d kills inside" % (sum(self.kills.values()) - k0))
        return True

    # -------------------------------------------------------------- deaths
    def recover(self, why):
        c, pt = self.c, self.pt
        p = c.player()
        spot = (p.get("area"), p.get("x"), p.get("y"))
        near = sorted({m.get("class") for m in c.gc.hstate()["mons"] if m.get("dist", 99) < 12})
        time.sleep(2)
        c.shot("hour_dead%d" % (len(self.deaths) + 1))
        self.deaths.append({"where": spot, "level": c.stat(12), "near": near, "why": why})
        c.note("death %d: %s, monsters near %s" % (len(self.deaths), why, near))
        if not pt.respawn(c):
            return False
        if spot[0] in (AREA_BLOODMOOR,) and self.walk_out():
            c.gc.relp_walk_to(c, spot[1], spot[2], lambda: abs(c.player()["x"] - spot[1]) + abs(c.player()["y"] - spot[2]) < 3,
                              self.log, budget=240, fight=self.fight_cb)
            for dx, dy in pt.spot_offsets(2)[:6]:
                c.g.click(*pt.project(c.player(), spot[1] + dx, spot[2] + dy))
                time.sleep(2)
        return True

    # -------------------------------------------------------------- the class
    def run(self, minutes):
        c, gc, pt = self.c, self.gc, self.pt
        pt.step_create(c, self.name)
        if c.steps.get("create", ("",))[0] != "PASS":
            self.phases["create"] = c.steps.get("create", ("FAIL", ""))
            return
        self.phases["create"] = c.steps["create"]
        gc.relp_wait_loaded()
        rooms = [(int(r["x"]), int(r["y"])) for r in (gc.kv(ln) for ln in gc.H("presets rooms")[1] if ln.startswith("room x="))]
        p = c.player()
        self.town_centre = (sum(x for x, _ in rooms) / len(rooms) + 20, sum(y for _, y in rooms) / len(rooms) + 20) if rooms else (p["x"], p["y"])
        self.t_end = time.time() + 60 * minutes
        todo = [("walk out", self.walk_out), ("Cold Plains", self.cold_plains), ("waypoint", self.waypoint), ("Den of Evil", self.den)]
        k = 0
        while k < len(todo) and time.time() < self.t_end:
            label, fn = todo[k]
            try:
                ok = fn()
            except Died as e:
                if not self.recover(str(e)):
                    self.phases[label] = ("FAIL", "no respawn after the death")
                    break
                continue  # the same phase again from town
            except TimeoutError:
                break
            if not gc.game_alive():
                self.phases[label] = ("FAIL", "the game died")
                break
            if not ok:
                break
            k += 1
        c.shot("hour_end")
        for label, _ in todo:
            self.phases.setdefault(label, ("NOT RUN", "class time up or an earlier phase stopped"))

    def report(self):
        p = self.c.player()
        n, big, mean = fight_summary(self.hits)
        rows = ["%s %s %s" % (k, v[0], v[1]) for k, v in self.phases.items()]
        rows.append("level %s, experience %s, life %s, area %s" % (p.get("level"), self.c.stat(13), p.get("life"), p.get("area")))
        rows.append("deaths %d%s" % (len(self.deaths), (": " + "; ".join("%s near %s (level %s)" % (d["where"], d["near"], d["level"])
                                                                       for d in self.deaths)) if self.deaths else ""))
        rows.append("kills %d %s" % (sum(self.kills.values()), dict(sorted(self.kills.items(), key=lambda kv: str(kv[0])))))
        rows.append("hits: %d held attacks lost life, largest %d, mean %.1f per monster near" % (n, big, mean))
        rows.append("Blood Moor monsters (class, level, life): %s" % list(self.sample.values()))
        rows.append("drops seen %s, picked up %s" % ([d["code"] for d in self.drops], self.picked))
        return rows


def run(gc):
    classes = [x for x in (os.environ.get("MXL_HOUR_CLASSES") or ",".join(CLASSES)).split(",") if x]
    minutes = float(os.environ.get("MXL_HOUR_MIN") or 20)
    stamp = int(time.time())
    for k, cls in enumerate(classes):
        mark = gc.engine_mark()
        log = []
        h = Hour(gc, cls, stamp + 7 * k, log)
        try:
            h.run(minutes)
        except Exception as e:
            if "ABORT" in str(e):
                raise
            h.phases["script"] = ("BLOCKED", "script error %r" % (e,))
        rows = h.report()
        bad = [r for r in rows if " FAIL " in r]
        blocked = [r for r in rows if " BLOCKED " in r or " NOT RUN " in r]
        gc.finish("act1_hour %s (%s)" % (cls, h.name), not bad, "; ".join(rows), mark, h.c.shots, rows + log[-300:],
                  partial="; ".join(blocked) or None)
        if not gc.g.game_pids():
            gc.to_menu()
