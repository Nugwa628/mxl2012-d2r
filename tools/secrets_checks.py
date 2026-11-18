"""Check `secrets` (tools/game_checks.py; data/secret_items.tsv, tools/secret_items.py): Median's nine secret uniques drop.

Parts, each in the report row:
  - drops: on each of the six sacred bases, `item <code> unique ilvl=120 inv` without a row lets the game's own generator pick
    the unique by its rarity among the spawnable rows (what a drop that rolled unique does). SECRETS_ROLLS times per base;
    PASS needs the secret seen at least once and only spawnable rows. Expected share 1 in 13 (rarity 1 of 4 + 8 + 1).
    The three jewels (1 in 5,751 to 1 in 41,596 of unique jewels) are not rolled: the built table's spawnable cell is checked.
  - tooltips: each of the nine made by its row (`item <code> unique <row> inv`) in the backpack, hovered, a shot in HD and
    in legacy graphics (G); the stat lines (Aeterna's proc, Bard's Joke's skill line, Lady of Storms' level 40) are judged
    on the shots.
"""
import os
import re
import time

SECRETS = ("Lady of Storms2", "Atomus", "Bardslore", "NewGrandArmor", "NewSiggardsRevenge", "NewAeterna", "NewWhiteVoid",
           "NewFuryHell", "NewSoulReaver")
JEWELS = SECRETS[:3]
BATCHES = (("Lady of Storms2", "Atomus", "Bardslore", "NewAeterna", "NewGrandArmor", "NewSiggardsRevenge"),
           ("NewWhiteVoid", "NewFuryHell", "NewSoulReaver"))


def unique_rows(gc):
    """index (without the mxl2012: namespace) -> (row, code, spawnable) of the built uniqueitems.txt; row = the 0-based record
    the harness takes (Expansion lines not counted, as game_checks.carry1_rows)."""
    recs = [r for r in gc.table("uniqueitems") if (r.get("index") or "") not in ("", "Expansion")]
    out = {}
    for i, r in enumerate(recs):
        k = r["index"].split(":", 1)[-1]
        out.setdefault(k, (i, r["code"], (r.get("spawnable") or "").strip()))
    return out, recs


def size(gc, code):
    for t in ("armor", "weapons", "misc"):
        r = gc.row_of(t, "code", code)
        if r:
            return int(r.get("invwidth") or 1), int(r.get("invheight") or 1)
    return 1, 1


def drops(gc, rows, recs, log, notes, bad):
    n = int(os.environ.get("SECRETS_ROLLS", "60"))
    for k in SECRETS:
        row, code, _sp = rows[k]
        if k in JEWELS:
            continue
        seen = {}
        for _ in range(n):
            gc.H("packclear")
            _ok, ln = gc.Hl("item %s unique ilvl=120 inv" % code, log) if not seen else gc.H("item %s unique ilvl=120 inv" % code)
            m = next((re.search(r" quality=(\d+) index=(-?\d+) ", x) for x in ln if x.startswith("item id=")), None)
            if not m:
                continue
            q, idx = int(m.group(1)), int(m.group(2))
            name = recs[idx]["index"].split(":", 1)[-1] if q == 7 and 0 <= idx < len(recs) else "quality %d" % q
            seen[name] = seen.get(name, 0) + 1
        unspawnable = [s for s in seen if s in rows and rows[s][2] != "1"]
        notes.append("%s (%s) x%d: %s" % (k, code, n, ", ".join("%s %d" % kv for kv in sorted(seen.items(), key=lambda x: -x[1]))))
        if not seen.get(k):
            bad.append("%s never rolled on %s" % (k, code))
        if unspawnable:
            bad.append("unspawnable rows rolled: %s" % unspawnable)
    gc.H("packclear")
    for k in JEWELS:
        if rows[k][2] != "1":
            bad.append("%s not spawnable in the built table" % k)


def tooltips(gc, rows, log, shots, bad):
    for b, batch in enumerate(BATCHES):
        gc.set_graphics("hd")
        gc.close_right_panel()
        gc.Hl("packclear", log)
        made = {}
        for k in batch:
            row, code, _ = rows[k]
            _ok, ln = gc.Hl("item %s unique %d inv" % (code, row), log)
            it = next((gc.item_lines([x])[0] for x in ln if x.startswith("item id=")), None)
            if not it or it.get("index") != row:
                bad.append("%s not made" % k)
                continue
            made[k] = it
        for mode in ("hd", "legacy"):
            if not gc.set_graphics(mode):
                bad.append("graphics mode %s not reached" % mode)
                continue
            time.sleep(1.0)
            if mode == "hd":
                if not gc.right_panel_open():
                    gc.g.press("i")
                    time.sleep(1.5)
            else:
                gc.g.press("i")  # right_panel_open() reads the HD panel only: opened blind
                time.sleep(2.0)
            items = {it["id"]: it for it in gc.rp_items_now()}
            for k, it in made.items():
                it = items.get(it["id"], it)
                px, py = gc.id_px(it["x"], it["y"], mode)
                w, h = size(gc, it["code"])  # hover the item's centre
                cx, cy = gc.id_px(it["x"] + (w - 1) / 2.0, it["y"] + (h - 1) / 2.0, mode)
                gc.hover_px(cx, cy)
                time.sleep(0.8)
                shots.append(gc.sh("secrets_%s_%s" % (re.sub(r"[^A-Za-z0-9]+", "", k), mode)))
                gc.hover(0.45, 0.30)
            if mode == "legacy":
                gc.g.press("i")
                time.sleep(1.0)
            else:
                gc.close_right_panel()
    gc.set_graphics("hd")
    gc.Hl("packclear", log)


def run(gc):
    mark = gc.engine_mark()
    if not gc.need_game():
        return gc.add("secrets", "BLOCKED", "not in a game")
    log, shots, notes, bad = [], [], [], []
    rows, recs = unique_rows(gc)
    missing = [k for k in SECRETS if k not in rows]
    if missing:
        return gc.add("secrets", "FAIL", "built uniqueitems.txt lacks %s" % missing)
    gc.goto(1)
    gc.set_graphics("hd")
    if os.environ.get("SECRETS_PART", "all") in ("all", "drops"):
        drops(gc, rows, recs, log, notes, bad)
    if os.environ.get("SECRETS_PART", "all") in ("all", "tooltips"):
        tooltips(gc, rows, log, shots, bad)
    if not gc.game_alive():
        bad.append("the game died")
    gc.finish("secrets", not bad, "; ".join(notes) + ("; PROBLEMS: " + "; ".join(bad) if bad else ""), mark, shots, log,
              partial="the tooltip lines are judged on the shots")
