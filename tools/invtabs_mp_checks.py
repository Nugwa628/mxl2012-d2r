#!/usr/bin/env python
"""Two-client TCP/IP check for D2R-XL 2012 (lane invtabs-mp, docs/invtabs-mp.md "Test rig").

One test slot hosts a LAN-only, unlisted TCP/IP game; a second slot joins it over 127.0.0.1. Background input only
(tools/game_ctl.py), throwaway characters only (MpHost<nn> / MpJoin<nn>, made fresh), each slot's shared D2RLoader files
restored by game_ctl's slot_share snapshot, the slot's d2rloader.toml network keys restored by this tool.

  py -3 tools/invtabs_mp_checks.py run --host-slot 4 --join-slot 3 [--scenario charminv] [--stage-charminv]
  py -3 tools/invtabs_mp_checks.py preflight --host-slot 4 --join-slot 3

`run` starts two worker processes, each under the host-wide game token
(`mxl2012-runs\\tools\\heavy_lock.py game invtabs-mp -- ... worker`): two clients at most on the PC, one token each. A
worker only starts its game once BOTH tokens are held (else it gives its token back after TOKEN_WAIT_S), and does
start -> checks -> stop in its own process, so it owns the slot lock for the whole session (one game_ctl process per
command would lose the lock pid and leave the shared files unrestored). The workers meet at file barriers in the run
folder (work/runs/invtabs-mp-<time>/sync); either side writing sync/abort ends both.

Scenario `charminv` (today's install, CharmInv 1.0.1 bundled):
  joiner, single player: a fresh character; `item x1x inv 0=7` (Sunstone, +7 strength) stays in the backpack,
  `item x2x inv 0=3` (+3) is moved into CharmInv (page 6) with real clicks; strength read by `stat player 0`;
  Save and Exit.
  host: a fresh character, Save and Exit, Multiplayer -> Host Game, name, Unlisted, LAN Only, Create Game.
  joiner: Multiplayer -> Direct Join 127.0.0.1 with the same character; `cstat 0` (the client's copy, which the
  hosting server's stat updates fill: the bonuses as the server counts them); then a CharmInv move as a joiner
  (backpack charm into the CharmInv grid, the page-6 charm back to the backpack) with `cstat 0` after each.
  Server verbs (`stat`, `item`, `items`) answer only on the hosting game (docs/testing.md: they need the server's
  player), so the host's server view of the JOINER is read through the joiner's client copy; a harness verb that
  reads another player's stat (`stat plr:<id> <stat>`) is the core's to add.

Scenario `invtabs` (both slots carry invtabs.dll; docs/invtabs-mp.md "What was built"): the charm tab of a JOINED player.
  joiner, single player: a fresh character with two charms (x1x +7 strength, x2x +3) and a rune in the backpack; Save
  and Exit. host: a fresh character with one charm and a rune; Save and Exit; hosts.
  joiner in the hosted game: the link must read "joined, full" (`invtabs` status line); opens the tab; drags a charm in,
  Ctrl+clicks the other in, drags one out, Ctrl+clicks the other out; a rune by drag and by Ctrl+click (refused); a held
  charm on the panel outside the grid (refused); both charms into the tab again. After every step the HOST reads the
  joiner's items, cursor and strength on the server (its server verbs act on the newest player) and takes a screenshot.
  host, with the joiner in the game: the same moves with its own charm and rune (screenshots on both sides; its own
  items are read on the server once the joiner left). Both Save and Exit, the host hosts again, the joiner joins again:
  the items are where they were. The saves of both characters are kept at set-up, after the first game and after the
  second (<run>/<role>/saves), and `tools/d2save.py diff` of each pair is written to <run>/diff-*.txt.
  --join-char NAME: the joiner plays an existing character of its slot instead (one saved with CharmInv: Butcher's
  Tooth at page cell 0,0 and the Sacred Worldstone Key at 9,2, as `game_checks.py invtabs_seed` makes it); its items
  must show where CharmInv saved them, the tooth goes out and in again by Ctrl+click.
  --join-rows N: the joiner's charm tab gets N rows for the run (another tab table than the host's): its link must read
  "joined, read-only", a charm comes out of the tab and is refused on the way in (drag and Ctrl+click).

--stage-charminv: a slot whose mod has no CharmInv gets it for the run (tools/install_mod.py install_charminv: the
pinned 1.0.1 bytes, checked, and our charm-inv.toml) with the slot lock held, and loses it again after the game stopped;
a slot that had it keeps it.

Network: before the game starts each worker sets `automatic_port_mapping = false` and `hosting_check = false` in the
slot's d2rloader.toml (the dialog otherwise asks the router for a port mapping and probes the port from outside) and
puts the file back byte for byte afterwards.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HEAVY_LOCK = os.path.normpath(os.path.join(ROOT, "..", "..", "mxl2012-runs", "tools", "heavy_lock.py"))
LANE = "invtabs-mp"
TOKEN_WAIT_S = 600       # a worker holding its token waits this long for the other worker's token, then gives it back
STEP_WAIT_S = 600        # longest wait at any other barrier
CHARM_CODES = {"bag": ("x1x", 7), "page6": ("x2x", 3)}  # Sunstone of Fire / Ice, + strength
# Scenario `full`: each charm also carries maximum life (stat 7, 1/256 units in the stat call). The client draws its own
# copy of every item stat (docs/d2r-addresses.md 22c, client refresh), so `cstat 0` / `cstat 7` are the JOINER's own count.
# The hosting server's count shows in current life: it is set by the server (life packets) and the server clamps it to ITS
# maximum, so a joiner whose page-6 charm the server ignores sees current life below the client's maximum after a move
# into page 6 (and after a join, where the server fills life to its maximum).
FULL_CHARMS = {"bag": ("x1x", 7, 2560), "page6": ("x2x", 3, 5120)}
HOST_CHARM = ("x1x", 5)
UNIQUE = ("a60", "ButchersTooth", 183, 10, 40)  # Butcher's Tooth: carry1, +10 all attributes, level 40; row of the 0.1.19 build

# Fractions of the 1600 x 900 client rect, measured on slot 2 (2026-11-11, HD menu) and slot 2 CharmInv (2026-11-10).
UI = {
    "menu_scenery": (0.620, 0.400),     # the menu swallows its first click
    "multiplayer": (0.605, 0.897),      # main menu: Multiplayer (D2RLoader's TCP/IP dialog)
    "mp_close": (0.742, 0.077),
    "mp_host_tab": (0.465, 0.157),
    "mp_browse_tab": (0.534, 0.157),
    "mp_game_name": (0.384, 0.278),
    "mp_unlisted": (0.299, 0.529),
    "mp_lan_only": (0.394, 0.529),
    "mp_create": (0.500, 0.717),
    "mp_direct_join": (0.345, 0.745),   # Browse Games: Direct Join
    "dj_ip_box": (0.497, 0.433),
    "dj_join": (0.425, 0.549),
    "dj_cancel": (0.566, 0.549),
    # CharmInv's inventory button: the arrow on the inventory's left edge (run 2026-11-11 16:07: the button at 0.669, 0.744
    # is the stock "send storable items to stash", "not available when joined to another player's game")
    "charminv_button": (0.644, 0.437),
}
# server reads of the joiner, taken by the host at each joiner step (on the host every server verb acts on the joiner:
# the harness's FindPlayer returns the first client of the game's list, the newest one)
SERVER_VIEWS = ("joined", "bag_in", "page_out", "dup_try", "rejoined")


# Scenario `invtabs`: what each side makes in its single-player game (code, harness stat arguments). The x2x charm and
# the two different runes tell a server read of the joiner from one of the host.
IT_JOIN_ITEMS = {"a": ("x1x", "0=7"), "b": ("x2x", "0=3"), "rune": ("r01", "")}
IT_HOST_ITEMS = {"c": ("x1x", "0=5"), "rune": ("r02", "")}
IT_AREA = (10, 6)                 # the shipped charm tab
IT_PANEL_OUTSIDE = (0.2125, 0.34)  # the HD tab panel above its grid (the summary's well): inside the panel, no cell
IT_HOST_STEPS = ("tab", "drag_in", "drag_out", "ctrl_in", "rune", "outside", "placed", "ctrl_out")
IT_FREE_CELL = (3, 4)             # a backpack cell that is empty on the seeded character (`invtabs_seed`)

TICK_MIN_BRIGHT = 15  # pixels > 160 in the 16 x 16 box: 30-34 ticked, 0 unticked (slot 2, 2026-11-11)


def checkbox_ticked(gray, fx, fy):
    """`gray`: an L-mode PIL image of the 1600 x 900 client. True when the checkbox centred at fx, fy shows its tick.
    The Multiplayer dialog remembers its boxes between games, so a box is read before it is clicked."""
    w, h = gray.size
    cx, cy = int(fx * w), int(fy * h)
    box = gray.crop((cx - 8, cy - 8, cx + 8, cy + 8))
    return sum(1 for v in box.tobytes() if v > 160) >= TICK_MIN_BRIGHT


def inv_cell(col, row):
    """HD backpack cell (10 x 8 grid at 1048,393, 43.8 x 42.2 px)."""
    return ((1048 + 43.8 * (col + .5)) / 1600, (393 + 42.2 * (row + .5)) / 900)


def charminv_cell(col, row):
    """HD CharmInv grid cell (10 x 4 at 137,518, 40.6 px)."""
    return ((137 + 40.6 * (col + .5)) / 1600, (518 + 40.6 * (row + .5)) / 900)


# ---------------------------------------------------------------- pure helpers (tools/test_invtabs_mp_checks.py)

def set_toml_keys(text, values):
    """`text` with each `key = ...` line of `values` set (first occurrence, any section; comments kept). Keys that are
    not in the file are left out: the loader's own default applies then, and the caller is told by the returned list."""
    missing = []
    out = text
    for key, val in values.items():
        lit = "true" if val is True else "false" if val is False else str(val)
        pat = re.compile(r"^(\s*%s\s*=\s*)([^\r\n#]*?)(\s*(#.*)?)$" % re.escape(key), re.M)
        if not pat.search(out):
            missing.append(key)
            continue
        out = pat.sub(lambda m: m.group(1) + lit + (m.group(3) or ""), out, count=1)
    return out, missing


def toml_value(text, key):
    m = re.search(r"^\s*%s\s*=\s*([^\r\n#]*?)\s*(#.*)?$" % re.escape(key), text, re.M)
    return m.group(1) if m else None


NET_KEYS = {"automatic_port_mapping": False, "hosting_check": False}

LOADER_PATTERNS = [
    ("hosting", re.compile(r"TCP/IP hosting is using TCP port (\d+)")),
    ("mapping_off", re.compile(r"Automatic port mapping is disabled")),
    ("mapping_on", re.compile(r"(NAT-PMP|UPnP|port mapping (created|requested|added))", re.I)),
    ("joined", re.compile(r"(joined|connected to) (the )?(TCP/IP )?(game|host)", re.I)),
    ("refused", re.compile(r"(refus|reject|incompatible|mismatch)\w*", re.I)),
    ("plugin_history", re.compile(r"plugin history", re.I)),
    ("registration", re.compile(r"\[HOSTING\] Host registration", re.I)),  # the online game directory: never wanted
    ("env_rejected", re.compile(r"environment (rejected|admission denied)", re.I)),
]


def classify_loader_lines(lines):
    """{tag: [lines]} for the D2RLoader / plugin log lines that tell how hosting and joining went."""
    out = {}
    for ln in lines:
        for tag, pat in LOADER_PATTERNS:
            if pat.search(ln):
                out.setdefault(tag, []).append(ln.strip()[-300:])
    return out


def charminv_verdict(sp, mp):
    """Compare the joiner's strength values. `sp`: single player {base, bag, both} from `stat player 0`; `mp`: joined
    {joined, bag_to_page6, page6_to_bag} from `cstat 0` (None when not read). Returns a list of (name, ok, note)."""
    rows = []
    bag_bonus, page_bonus = CHARM_CODES["bag"][1], CHARM_CODES["page6"][1]
    base = sp.get("base")
    rows.append(("sp: backpack charm counts", base is not None and sp.get("bag") == base + bag_bonus, "%s -> %s" % (base, sp.get("bag"))))
    rows.append(("sp: CharmInv charm counts", base is not None and sp.get("both") == base + bag_bonus + page_bonus,
                 "%s -> %s" % (sp.get("bag"), sp.get("both"))))
    want = sp.get("both")
    rows.append(("joiner: both charms count after joining", want is not None and mp.get("joined") == want,
                 "want %s, client copy %s" % (want, mp.get("joined"))))
    if "bag_to_page6" in mp:
        rows.append(("joiner: backpack charm moved into CharmInv still counts", mp.get("bag_to_page6") == want,
                     "want %s, got %s (moved: %s)" % (want, mp.get("bag_to_page6"), mp.get("bag_moved"))))
    if "page6_to_bag" in mp:
        rows.append(("joiner: CharmInv charm moved back to the backpack still counts", mp.get("page6_to_bag") == want,
                     "want %s, got %s (moved: %s)" % (want, mp.get("page6_to_bag"), mp.get("page6_moved"))))
    return rows


def life_pts(v):
    return None if v is None else v >> 8


def full_verdict(sp, mp, host=None, panels=()):
    """Scenario `full`. `sp`: the joiner's single-player set-up and the final single-player read ({base, bag, page,
    uniq_a, uniq_b, life_*, final}); `mp`: the joiner's client reads in the TCP/IP game, each {str, life, maxlife}
    (raw 1/256 life); `host`: the host's own charm reads ({bag, page6, out}, each {srv, cli}). (name, ok, note) rows."""
    rows = []
    want = sp.get("uniq_b")  # strength with both charms and one counting Butcher's Tooth (+ the second copy)
    base = sp.get("base")
    if base is not None:
        b7, b3, u = FULL_CHARMS["bag"][1], FULL_CHARMS["page6"][1], UNIQUE[3]
        rows.append(("sp: backpack charm counts", sp.get("bag") == base + b7, "%s -> %s" % (base, sp.get("bag"))))
        # Butcher's Tooth A is made (backpack) before the x2x move, so it counts from then on
        rows.append(("sp: CharmInv charm counts", sp.get("page") == base + b7 + b3 + u, "-> %s" % sp.get("page")))
        rows.append(("sp: Butcher's Tooth in CharmInv counts", sp.get("uniq_a") == base + b7 + b3 + u, "-> %s" % sp.get("uniq_a")))
        rows.append(("sp: second copy in the backpack, +10 once", want == base + b7 + b3 + u, "-> %s" % want))
    for name, v in ((mp or {}).get("server") or {}).items():
        if isinstance(v, dict) and v.get("str") is not None and "skipped" not in str(v.get("joiner_note") or ""):
            rows.append(("server counts the joiner's charms (%s)" % name, want is not None and v["str"] == want,
                         "want %s, server %s, life %s / %s" % (want, v["str"], life_pts(v.get("life")), life_pts(v.get("maxlife")))))
    for where, how in panels:
        rows.append(("CharmInv panel opens %s" % where, bool(how), how or "did not open"))
    for name, seen in (("bag", "host_seen_bag"), ("charminv", "host_seen_in"), ("back", "host_seen_out")):
        v = ((mp or {}).get(seen) or {}).get("str")
        if v is not None:
            rows.append(("joiner's client copy of the host, host charm %s (info)" % name, True, "strength %s" % v))
    fin = sp.get("final")
    if fin:
        rows.append(("joiner save after the TCP/IP game: strength", fin.get("str") == want, "want %s, got %s" % (want, fin.get("str"))))
        rows.append(("joiner save after the TCP/IP game: items", fin.get("page6_codes") is not None,
                     "page 6 %s, backpack %s" % (fin.get("page6_codes"), fin.get("bag_codes"))))
    return rows


def it_where(items, code):
    """(page, x, y) as ints of the first `items` row (the harness verb's key=value rows) with this code, else None."""
    for it in items or []:
        if it.get("code") == code:
            try:
                return int(it["page"]), int(it["x"]), int(it["y"])
            except (KeyError, ValueError):
                return None
    return None


def it_outside(items, area=IT_AREA):
    """The page-6 rows that are not inside the tab's area (1 x 1 items and the 1 x 2 key: the top-left cell and, for the
    rows this scenario uses, the cell below it are checked by the caller's choice of cells)."""
    out = []
    for it in items or []:
        if it.get("page") == "6" and not (0 <= int(it.get("x", -1)) < area[0] and 0 <= int(it.get("y", -1)) < area[1]):
            out.append((it.get("code"), it.get("x"), it.get("y")))
    return out


def diff_codes(lines):
    """(lost codes, new codes), sorted, of `d2save.py diff` output: a moved item is one LOST and one NEW line of its
    code (the item key holds its place), so equal lists mean no item left or joined the character."""
    lost = sorted(ln.rsplit(":", 1)[-1].strip() for ln in lines if ln.startswith("LOST "))
    new = sorted(ln.rsplit(":", 1)[-1].strip() for ln in lines if ln.startswith("NEW "))
    return lost, new


def invtabs_verdict(join, host, diffs=None):
    """Rows (name, ok, values) of scenario `invtabs` from the two workers' results (and the save diffs' lines by name)."""
    join, host = join or {}, host or {}
    mp, sp, own = join.get("mp") or {}, join.get("sp") or {}, host.get("own") or {}
    views = mp.get("server") or {}
    rows = []

    def view(name):
        return views.get(name) or {}

    def where(name, code):
        return it_where(view(name).get("items"), code)

    def held(name):
        c = view(name).get("cursor")
        return c[1] if c else None

    def row(name, ok, note):
        rows.append((name, bool(ok), str(note)))

    readonly = bool(join.get("readonly"))
    row("joiner link: %s" % ("read-only (other tab table)" if readonly else "full"),
        ("link joined, read-only" if readonly else "link joined, full") in (mp.get("link") or ""), (mp.get("link") or "")[-90:])
    if not readonly:
        row("host: one joined player welcomed", "1 joined" in (own.get("link") or ""), (own.get("link") or "")[-60:])
    outside = sorted({(n, c, x, y) for n, v in views.items() for c, x, y in it_outside(v.get("items"))})
    row("no item of the joiner on the page outside the tab's area, at any step", views and not outside, outside or "%d reads" % len(views))
    if join.get("adopt"):
        tooth, key = join["adopt"]["tooth"], join["adopt"]["key"]
        row("joiner saved with CharmInv: items where CharmInv saved them", where("joined", tooth) == (6, 0, 0) and where("joined", key) == (6, 9, 2),
            "tooth %s, key %s" % (where("joined", tooth), where("joined", key)))
        if readonly:
            row("read-only: a charm comes out of the tab (drag)", (where("ro_out", tooth) or (None,))[0] == 0, where("ro_out", tooth))
            row("read-only: drag into the tab refused (stays on the cursor)", held("ro_drag_in") == tooth and (where("ro_drag_in", tooth) or (None,))[0] != 6,
                "cursor %s, item %s" % (held("ro_drag_in"), where("ro_drag_in", tooth)))
            row("read-only: Ctrl+click into the tab refused", (where("ro_ctrl_in", tooth) or (None,))[0] == 0, where("ro_ctrl_in", tooth))
            final = {tooth: 0, key: 6}
        else:
            row("Ctrl+click out of the tab (joiner, by the host)", (where("ctrl_out", tooth) or (None,))[0] == 0, where("ctrl_out", tooth))
            row("Ctrl+click into the tab (joiner, by the host): first free cell", where("ctrl_in", tooth) == (6, 0, 0), where("ctrl_in", tooth))
            final = {tooth: 6, key: 6}
        codes = [tooth, key]
    else:
        a, b, rune = (IT_JOIN_ITEMS[k][0] for k in ("a", "b", "rune"))
        row("drag into the tab (joiner): charm at 2,1", where("drag_in", a) == (6, 2, 1), where("drag_in", a))
        row("Ctrl+click into the tab (joiner, by the host): first free cell", where("ctrl_in", b) == (6, 0, 0), where("ctrl_in", b))
        row("drag out of the tab (joiner)", (where("drag_out", a) or (None,))[0] == 0, where("drag_out", a))
        row("Ctrl+click out of the tab (joiner, by the host)", (where("ctrl_out", b) or (None,))[0] == 0, where("ctrl_out", b))
        row("rune dragged to the tab: refused (stays on the cursor)", held("rune_held") == rune and (where("rune_held", rune) or (None,))[0] != 6,
            "cursor %s, rune %s" % (held("rune_held"), where("rune_held", rune)))
        row("rune Ctrl+clicked: refused (stays in the backpack)", (where("rune_ctrl", rune) or (None,))[0] == 0, where("rune_ctrl", rune))
        row("held charm on the panel outside the grid: refused (stays on the cursor)", held("outside_held") == a and (where("outside_held", a) or (None,))[0] != 6,
            "cursor %s, charm %s" % (held("outside_held"), where("outside_held", a)))
        base = sp.get("str")
        strs = {n: view(n).get("str") for n in ("joined", "drag_in", "ctrl_in", "after_host", "rejoined")}
        row("charm bonus on the server for the joiner: same in the backpack and in the tab", base is not None and all(v == base for v in strs.values()),
            "single player %s, hosted game %s" % (base, strs))
        row("a held charm gives nothing (server)", base is not None and view("outside_held").get("str") == base - 7,
            "%s with the +7 charm held" % view("outside_held").get("str"))
        row("joiner's log: the hosting game refused the rune", any("does not take this item" in ln for ln in join.get("invtabs_log") or []), "")
        final = {a: 6, b: 6, rune: 0}
        codes = [a, b, rune]
        row("charms in the tab at the end (3,2 by drag, first free cell by Ctrl+click)", where("after_host", a) == (6, 3, 2) and where("after_host", b) == (6, 0, 0),
            "%s %s" % (where("after_host", a), where("after_host", b)))
    row("joiner's items after the host's own moves", all((where("after_host", c) or (None,))[0] == p for c, p in final.items()),
        {c: where("after_host", c) for c in final})
    row("joiner after Save and Exit and a new game: items where they were", views.get("rejoined") and all(where("rejoined", c) == where("after_host", c) for c in codes),
        {c: where("rejoined", c) for c in codes})
    hc, hr = IT_HOST_ITEMS["c"][0], IT_HOST_ITEMS["rune"][0]
    after, again = own.get("after_items"), own.get("rejoin_items")
    want = (6, 0, 0) if own.get("ctrl_out_back") else (6, 5, 3)
    row("host's own moves with a joined player in the game: charm in the tab at %d,%d, rune in the backpack" % want[1:],
        it_where(after, hc) == want and (it_where(after, hr) or (None,))[0] == 0, "charm %s, rune %s; steps %s" % (it_where(after, hc), it_where(after, hr), own.get("moves")))
    row("host: Ctrl+click on a charm in the tab moves it to the backpack", own.get("ctrl_out_back"), "back in its backpack cell: %s" % own.get("ctrl_out_back"))
    row("host after Save and Exit and a new game: items where they were", again is not None and all(it_where(again, c) == it_where(after, c) for c in (hc, hr)),
        "charm %s, rune %s" % (it_where(again, hc), it_where(again, hr)))
    if not readonly:
        row("host's log: moves run for the joined player", any("a joined player's item" in ln for ln in host.get("invtabs_log") or []), "")
    for name, lines in sorted((diffs or {}).items()):
        if lines is None:
            row("save diff %s" % name, False, "no diff (a save is missing)")
            continue
        lost, new = diff_codes(lines)
        if name.endswith("1-after-to-2-rejoin"):
            row("save diff %s: no item moved, lost or new" % name, not lost and not new, "lost %s, new %s" % (lost, new))
        else:
            row("save diff %s: items moved, none lost or new" % name, lost == new, "lost %s, new %s" % (lost, new))
    return rows


class Barrier:
    """File barriers in <run>/sync. `post(name, data)` writes atomically; `wait(name)` returns its data or raises on
    timeout or when sync/abort appears (written by `abort`)."""

    def __init__(self, folder, sleep=time.sleep, clock=time.time):
        self.dir = os.path.join(folder, "sync")
        os.makedirs(self.dir, exist_ok=True)
        self.sleep, self.clock = sleep, clock

    def _p(self, name):
        if not re.fullmatch(r"[a-z0-9_-]+", name):
            raise ValueError("barrier name %r" % name)
        return os.path.join(self.dir, name)

    def post(self, name, data=None):
        tmp = self._p(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, self._p(name))

    def has(self, name):
        return os.path.exists(self._p(name))

    def get(self, name):
        with open(self._p(name), encoding="utf-8") as f:
            return json.load(f)

    def abort(self, why):
        if not self.has("abort"):
            self.post("abort", why)

    def aborted(self):
        return self.get("abort") if self.has("abort") else None

    def wait(self, name, timeout):
        t0 = self.clock()
        while True:
            if self.has(name):
                return self.get(name)
            why = self.aborted()
            if why is not None:
                raise RuntimeError("other side aborted: %s" % why)
            if self.clock() - t0 > timeout:
                raise TimeoutError("no %r in %d s" % (name, timeout))
            self.sleep(1)


def plugin_set(game_dir, mod="mxl2012"):
    """Plugin files (dll / mpq) of the slot's mod and the game-wide folder: what has to match for a TCP/IP join."""
    out = {}
    for rel in (os.path.join("mods", mod, "d2rloader", "plugins"), os.path.join("d2rloader", "plugins")):
        d = os.path.join(game_dir, rel)
        if os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                if n.lower().endswith((".dll", ".mpq")):
                    p = os.path.join(d, n)
                    if n.lower().endswith(".dll"):  # D2RLoader admits a joiner only with byte-identical shared plugins
                        with open(p, "rb") as f:
                            out[os.path.join(rel, n)] = hashlib.sha256(f.read()).hexdigest()
                    else:
                        out[os.path.join(rel, n)] = os.path.getsize(p)
    return out


def plugin_diff(a, b):
    """Names present on one side only, and names whose bytes differ (DLL sha256, MPQ size). D2RLoader refuses a joiner
    whose shared plugin has another identity hash ("shared plugin changed identity", 2026-11-11 run)."""
    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    size = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    return only_a, only_b, size


def report_md(meta, host, join, verdicts):
    lines = ["# invtabs-mp two-client run %s" % meta.get("run", "?"), "",
             "host slot %s, joiner slot %s, scenario %s, started %s" % (meta.get("host_slot"), meta.get("join_slot"),
                                                                       meta.get("scenario"), meta.get("started")), ""]
    for role, r in (("host", host), ("joiner", join)):
        lines.append("## %s" % role)
        if not r:
            lines.append("- no result (worker did not finish)")
        else:
            for step in r.get("steps", []):
                lines.append("- %s: %s%s" % (step[0], "ok" if step[1] else "FAILED", (" (%s)" % step[2]) if step[2] else ""))
            if r.get("error"):
                lines.append("- error: %s" % r["error"])
        lines.append("")
    if verdicts:
        lines += ["## verdicts", "", "| check | result | values |", "|-|-|-|"]
        for name, ok, note in verdicts:
            lines.append("| %s | %s | %s |" % (name, "PASS" if ok else "FAIL", note))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- orchestrator

def letters_tag(t):
    """Two letters for the throwaway names (D2R names take letters only: digits are dropped)."""
    n = int(t) // 60
    return chr(ord("a") + n % 26) + chr(ord("a") + (n // 26) % 26)


def run_dir(name=None):
    name = name or "invtabs-mp-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    d = os.path.join(os.environ.get("MXL_RUNS") or os.path.join(ROOT, "work", "runs"), name)
    os.makedirs(d, exist_ok=True)
    return name, d


def save_diffs(folder, roles=("host", "join"), out=print):
    """`d2save.py diff` of each role's kept saves (0-setup -> 1-after -> 2-rejoin), written to <run>/diff-<role>-<a>-to-<b>.txt.
    Returns {name: lines, or None when a save is missing}."""
    import glob
    got = {}
    for role in roles:
        for a, b in (("0-setup", "1-after"), ("1-after", "2-rejoin")):
            name = "%s-%s-to-%s" % (role, a, b)
            fa, fb = (glob.glob(os.path.join(folder, role, "saves", x, "*.d2s")) for x in (a, b))
            if not fa or not fb:
                got[name] = None
                continue
            r = subprocess.run([sys.executable, os.path.join(HERE, "d2save.py"), "diff", fa[0], fb[0]], cwd=ROOT, capture_output=True, text=True)
            lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
            with open(os.path.join(folder, "diff-%s.txt" % name), "w", encoding="utf-8") as f:
                f.write("d2save.py diff %s %s (exit %d)\n" % (os.path.relpath(fa[0], folder), os.path.relpath(fb[0], folder), r.returncode))
                f.write("\n".join(lines) + "\n")
            got[name] = lines if r.returncode in (0, 1) else None
            out("diff %s: %d line(s)" % (name, len(lines)))
    return got


def slot_dir(slot):
    sys.path.insert(0, HERE)
    import game_slots
    return game_slots.slot_dir(slot)


def session_owner(session, slot):
    """MXL_RUN of a worker inside a lane session: the slot stays locked by the session (game_slots.py lock N <owner>) for
    set-up, run and restore; the worker neither takes nor releases it."""
    return "%s-s%d" % (session, slot) if session else None


def preflight(host_slot, join_slot, out=print, session=None, scenario=None):
    ok = True
    if host_slot == join_slot:
        out("host and joiner need two different slots")
        return False
    sys.path.insert(0, HERE)
    import game_slots
    for s in (host_slot, join_slot):
        d = game_slots.slot_dir(s)
        if not os.path.isdir(d):
            out("slot %d: %s missing" % (s, d))
            ok = False
            continue
        info = game_slots.lock_info(s)
        own = session_owner(session, s)
        if info and own and info[1] and info[1].split()[0] == own:
            out("slot %d: locked by this session (%s)" % (s, own))
        elif info:
            out("slot %d: locked (%s)" % (s, info[1] if len(info) > 1 else info))
            ok = False
        if game_slots.slot_processes(d):
            out("slot %d: a game runs there" % s)
            ok = False
    if ok:
        a, b = plugin_set(game_slots.slot_dir(host_slot)), plugin_set(game_slots.slot_dir(join_slot))
        only_a, only_b, size = plugin_diff(a, b)
        for n in only_a:
            out("only on the host slot: %s" % n)
        for n in only_b:
            out("only on the joiner slot: %s" % n)
        for n in size:
            out("other bytes: %s (D2RLoader will refuse the join if it is a shared plugin)" % n)
            ok = False
        if scenario == "invtabs":
            if not any(n.endswith("invtabs.dll") for n in a) or not any(n.endswith("invtabs.dll") for n in b):
                out("invtabs.dll is not installed on both slots (scenario invtabs needs it)")
                ok = False
        elif not any(n.endswith("d2rl-charm-inv.dll") for n in a) or not any(n.endswith("d2rl-charm-inv.dll") for n in b):
            out("CharmInv is not installed on both slots (scenario charminv needs it, or --stage-charminv)")
    return ok


def cmd_run(args):
    if not preflight(args.host_slot, args.join_slot, session=args.session, scenario=args.scenario):
        return 2
    name, d = run_dir()
    meta = {"run": name, "host_slot": args.host_slot, "join_slot": args.join_slot, "scenario": args.scenario,
            "started": datetime.datetime.now().isoformat(timespec="seconds"), "port": args.port, "stage_charminv": args.stage_charminv, "tag": args.tag or letters_tag(time.time()),
            "session": args.session, "join_char": args.join_char, "join_rows": args.join_rows}
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    procs = []
    for role, slot in (("host", args.host_slot), ("join", args.join_slot)):
        env = dict(os.environ, MXL_SLOT=str(slot), MXL_RUN=session_owner(args.session, slot) or "%s-%s" % (name, role))
        cmd = [sys.executable, HEAVY_LOCK, "game", LANE, "--", sys.executable, os.path.abspath(__file__), "worker",
               "--role", role, "--dir", d]
        log = open(os.path.join(d, "%s-worker.out" % role), "w", encoding="utf-8")
        procs.append((role, subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT), log))
        time.sleep(5)  # the host's heavy_lock first: it takes the first free token
    rc = 0
    for role, p, log in procs:
        rc |= p.wait()
        log.close()
    res = {}
    for role in ("host", "join"):
        try:
            with open(os.path.join(d, role, "result.json")) as f:
                res[role] = json.load(f)
        except OSError:
            res[role] = None
    verdicts = []
    if args.scenario == "charminv" and res.get("join"):
        verdicts = charminv_verdict(res["join"].get("sp", {}), res["join"].get("mp", {}))
    elif args.scenario == "full" and res.get("join"):
        verdicts = full_verdict(res["join"].get("sp", {}), res["join"].get("mp", {}), (res.get("host") or {}).get("own"),
                                [tuple(x) for r in ("join", "host") for x in (res.get(r) or {}).get("panel", [])])
    elif args.scenario == "invtabs":
        verdicts = invtabs_verdict(res.get("join"), res.get("host"), save_diffs(d))
    if any((r or {}).get("registration") for r in res.values()):
        verdicts.insert(0, ("hosting game stayed off the online directory", False, str(res["host"].get("registration"))))
    with open(os.path.join(d, "report.md"), "w", encoding="utf-8") as f:
        f.write(report_md(meta, res.get("host"), res.get("join"), verdicts))
    print(open(os.path.join(d, "report.md"), encoding="utf-8").read())
    print("run folder", d)
    return rc or (1 if any(not ok for _, ok, _ in verdicts) else 0)


# ---------------------------------------------------------------- worker (one slot, one process, one token)

class Worker:
    def __init__(self, role, folder):
        self.role, self.folder = role, folder
        self.meta = json.load(open(os.path.join(folder, "meta.json")))
        self.out = os.path.join(folder, role)
        os.makedirs(self.out, exist_ok=True)
        self.sync = Barrier(folder)
        self.result = {"role": role, "steps": [], "sp": {}, "mp": {}}
        sys.path.insert(0, HERE)
        import game_checks as gc  # MXL_SLOT / MXL_RUN come from the orchestrator
        self.gc, self.g = gc, gc.g
        self.g.current_run = lambda create=False: self.out
        self.toml = os.path.join(self.g.GAME_DIR, "d2rloader", "config", "d2rloader.toml")
        self.toml_backup = None
        self.mod = os.path.join(self.g.GAME_DIR, "mods", "mxl2012")
        self.staged_charminv = False
        self.watch_stop = threading.Event()

    # -- bookkeeping
    def step(self, name, ok, note=""):
        self.result["steps"].append([name, bool(ok), str(note)])
        self.g.log("STEP %s: %s %s" % (name, "ok" if ok else "FAILED", note))
        self.save()
        return ok

    def must(self, name, ok, note=""):
        if not self.step(name, ok, note):
            raise RuntimeError("%s failed" % name)

    def save(self):
        with open(os.path.join(self.out, "result.json"), "w") as f:
            json.dump(self.result, f, indent=1)

    def shot(self, name):
        try:
            self.g.shot(os.path.join(self.out, name + ".png"))
        except Exception as e:  # a missing screenshot never ends the run
            self.g.log("shot %s failed: %r" % (name, e))

    def click(self, key_or_xy, wait=1.0):
        xy = UI[key_or_xy] if isinstance(key_or_xy, str) else key_or_xy
        self.g.click(*xy)
        time.sleep(wait)

    def loader_lines(self, mark):
        text = self.g._read_from(self.g.LOADER_LOG, mark) or ""
        return text.splitlines()

    # -- network keys of the slot's loader config
    def net_keys_off(self):
        with open(self.toml, "rb") as f:
            self.toml_backup = f.read()
        text = self.toml_backup.decode("utf-8")
        new, missing = set_toml_keys(text, NET_KEYS)
        if missing:
            raise RuntimeError("d2rloader.toml has no %s: not hosting with the router mapping on" % ", ".join(missing))
        with open(self.toml, "wb") as f:
            f.write(new.encode("utf-8"))
        with open(os.path.join(self.out, "d2rloader.toml.orig"), "wb") as f:
            f.write(self.toml_backup)

    def net_keys_restore(self):
        if self.toml_backup is None:
            return True
        with open(self.toml, "wb") as f:
            f.write(self.toml_backup)
        with open(self.toml, "rb") as f:
            ok = f.read() == self.toml_backup
        self.g.log("d2rloader.toml network keys restored: %s" % ok)
        return ok

    # -- CharmInv for the run (install_mod's own staging, checked bytes)
    def stage_charminv(self):
        if os.path.isfile(os.path.join(self.mod, "d2rloader", "plugins", "d2rl-charm-inv.dll")):
            return
        import install_mod
        from pathlib import Path
        self.g.log(install_mod.install_charminv(Path(self.mod), True))
        self.staged_charminv = True

    def unstage_charminv(self):
        if not self.staged_charminv:
            return True
        import install_mod
        from pathlib import Path
        self.g.log(install_mod.install_charminv(Path(self.mod), False))
        return not os.path.exists(os.path.join(self.mod, "d2rloader", "plugins", "d2rl-charm-inv.dll"))

    # -- menu steps
    def to_menu_with(self, name, cls="amazon"):
        self.must("main menu", self.gc.to_menu())
        ok = self.gc.create_character(cls, name)
        self.result["char"] = self.gc.STATE.get("char_name", name)
        self.must("character %s made" % self.result["char"], ok)

    def save_exit(self):
        return self.gc.rc2_save_exit()

    def select_own(self):
        """Click our character's card. The Multiplayer dialog hosts / joins with the SELECTED card, which is not the
        character just made and saved (2026-11-11 14:31: both sides entered with another lane's character)."""
        name = self.result.get("char")
        card = self.gc.card_of(name) if name else None
        y = self.gc.card_y(card) if card else None
        if y is None:
            raise RuntimeError("character %s is not on the visible card list (card %s): not hosting / joining" % (name, card))
        self.click("menu_scenery")
        self.g.click(0.87, y)
        time.sleep(1.2)
        self.shot("selected_%s" % self.role)
        self.result["card"] = card

    def open_multiplayer(self, tab):
        self.select_own()
        self.click("menu_scenery")
        self.click("multiplayer", 3)
        self.click(tab, 2)

    def host_game(self, game_name):
        self.open_multiplayer("mp_host_tab")
        self.click("mp_game_name", 0.5)
        for _ in range(16):
            self.g.press("backspace")
        self.g.type_text(game_name)
        if not self.ensure_lan_only():
            self.click("mp_close", 1)
            raise RuntimeError("LAN Only could not be confirmed ticked: no game created")
        self.shot("host_form")
        mark = self.g._size(self.g.LOADER_LOG)
        self.watch_registration(mark)
        self.click("mp_create", 2)
        ok = self.gc.wait_in_game(90)
        tags = classify_loader_lines(self.loader_lines(mark))
        self.result["host_log"] = tags
        return ok, tags

    def lan_only_ticked(self):
        self.g.click(0.5, 0.95, move_only=True)  # no hover tooltip over the boxes
        time.sleep(0.6)
        return checkbox_ticked(self.g.grab_client().convert("L"), *UI["mp_lan_only"])

    def ensure_lan_only(self):
        """LAN Only on (it turns router mapping and the public directory off). Read first, click only when off, read again."""
        if self.lan_only_ticked():
            return self.step("LAN Only already ticked", True)
        self.click("mp_lan_only", 0.8)
        return self.step("LAN Only ticked", self.lan_only_ticked())

    def direct_join(self, ip):
        self.open_multiplayer("mp_browse_tab")
        self.click("mp_direct_join", 2)
        mark = self.g._size(self.g.LOADER_LOG)
        ok = False
        # The address box keeps its last text; a typed address once came out "127.0.0.1." (2026-11-11 14:48) and the join
        # did nothing, the dialog stayed open. A second try types the address again into the same dialog.
        for attempt, wait in ((1, 45), (2, 90)):
            self.click("dj_ip_box", 0.5)
            for _ in range(24):
                self.g.press("backspace")
                time.sleep(0.03)
            for ch in ip:  # one character at a time: typed in one go the box once read "127.70.00.1" (2026-11-11 16:34)
                self.g.type_text(ch)
                time.sleep(0.25)
            time.sleep(0.5)
            self.shot("join_form%s" % ("" if attempt == 1 else attempt))
            self.click("dj_join", 2)
            ok = self.gc.wait_in_game(wait)
            if ok or self.loader_lines(mark) and any("Joined TCP/IP game" in ln for ln in self.loader_lines(mark)):
                break
            self.step("direct join try %d did not join" % attempt, False)
            self.g.press("enter")  # an "Unable to join this game" box covers the form until it is dismissed
            time.sleep(1.5)
        tags = classify_loader_lines(self.loader_lines(mark))
        self.result["join_log"] = tags
        if not ok:
            self.shot("join_failed")
        return ok, tags

    # -- in-game helpers
    def strength_server(self):
        return self.gc.rd("player", 0)

    def strength_client(self):
        _, lines = self.gc.H("cstat 0")
        return self.gc.stat_of(lines)

    def make_charm(self, code, bonus):
        ok, lines = self.gc.H("item %s inv 0=%d" % (code, bonus))
        it = self.gc.kv(lines[0]) if ok and lines else {}
        return ok, it

    def move_item(self, src, dst):
        self.click(src, 0.8)
        held = None
        try:
            held = self.gc.held_item()
        except Exception:
            pass  # a joiner has no server cursor read: the screenshot shows it
        self.click(dst, 1.2)
        return held

    # -- scenario charminv
    def joiner_sp(self):
        tag = self.meta["tag"]
        self.to_menu_with("MpJoin" + tag)
        sp = self.result["sp"]
        sp["base"] = self.strength_server()
        bag_code, bag_bonus = CHARM_CODES["bag"]
        page_code, page_bonus = CHARM_CODES["page6"]
        ok, bag = self.make_charm(bag_code, bag_bonus)
        self.must("backpack charm %s made" % bag_code, ok, bag)
        time.sleep(1)
        sp["bag"] = self.strength_server()
        ok, page = self.make_charm(page_code, page_bonus)
        self.must("charm %s made" % page_code, ok, page)
        sp["bag_item"], sp["page_item"] = bag, page
        self.g.press("i")
        time.sleep(1)
        self.g.console_bg("charminv open")
        time.sleep(1.5)
        self.move_item(inv_cell(int(page["x"]), int(page["y"])), charminv_cell(0, 0))
        time.sleep(1)
        sp["both"] = self.strength_server()
        _, il = self.gc.H("items")
        sp["items"] = [self.gc.kv(x) for x in il if x.startswith("item ")]
        sp["page6"] = [x for x in sp["items"] if x.get("page") == "6"]
        self.shot("sp_charms")
        self.step("single player strength base/bag/both", True, "%s/%s/%s" % (sp["base"], sp["bag"], sp["both"]))
        self.g.press("esc")
        time.sleep(1)
        self.must("save and exit", self.save_exit())

    def joiner_mp(self):
        mp = self.result["mp"]
        sp = self.result["sp"]
        ok, tags = self.direct_join("127.0.0.1")
        self.must("joined 127.0.0.1", ok, "; ".join(sum(tags.values(), []))[:400])
        time.sleep(4)
        self.shot("joined")
        mp["joined"] = self.strength_client()
        self.step("client strength after join", mp["joined"] is not None, mp["joined"])
        _, cl = self.gc.H("state")
        mp["server_verbs"] = cl[-1] if cl else None  # expected FAIL on a joiner (no server player)
        self.g.press("i")
        time.sleep(1)
        self.g.console_bg("charminv open")
        time.sleep(1.5)
        self.shot("joiner_charminv")
        bag = sp.get("bag_item") or {}
        if bag:
            self.move_item(inv_cell(int(bag["x"]), int(bag["y"])), charminv_cell(2, 0))
            time.sleep(1.5)
            mp["bag_to_page6"] = self.strength_client()
            self.shot("joiner_bag_to_charminv")
            mp["bag_moved"] = "see joiner_bag_to_charminv.png"
        self.move_item(charminv_cell(0, 0), inv_cell(0, 6))
        time.sleep(1.5)
        mp["page6_to_bag"] = self.strength_client()
        self.shot("joiner_page6_to_bag")
        mp["page6_moved"] = "see joiner_page6_to_bag.png"
        self.step("joiner moves done", True, json.dumps({k: mp.get(k) for k in ("joined", "bag_to_page6", "page6_to_bag")}))

    def host_side(self):
        tag = self.meta["tag"]
        self.to_menu_with("MpHost" + tag)
        self.must("host save and exit", self.save_exit())
        self.sync.wait("join-sp-done", STEP_WAIT_S)
        ok, tags = self.host_game("mpt" + tag)
        self.shot("hosted")
        if tags.get("registration"):
            raise RuntimeError("the hosting game contacted the online directory: %s" % tags["registration"][0])
        port = tags.get("hosting", [""])[0]
        self.must("hosting", ok, port or "no hosting line")
        if tags.get("mapping_on"):
            self.step("router mapping stayed off", False, tags["mapping_on"][0])
        self.sync.post("hosted", {"port": self.meta["port"]})
        self.sync.wait("join-mp-done", STEP_WAIT_S)
        self.shot("host_after_joiner")
        self.result["host_charminv_lines"] = [ln.strip()[-300:] for ln in self.charm_log_lines()]
        self.sync.wait("join-left", 180)
        self.must("host save and exit", self.save_exit())

    def charm_log_lines(self):
        p = os.path.join(self.g.GAME_DIR, "mods", "mxl2012", "d2rloader", "logs")
        out = []
        if os.path.isdir(p):
            for n in os.listdir(p):
                if "charm" in n.lower():
                    out += open(os.path.join(p, n), encoding="utf-8", errors="replace").read().splitlines()[-60:]
        return out

    def joiner_side(self):
        self.joiner_sp()
        self.sync.post("join-sp-done", self.result["sp"].get("both"))
        self.sync.wait("hosted", STEP_WAIT_S)
        try:
            self.joiner_mp()
        finally:
            self.sync.post("join-mp-done", self.result["mp"])
            left = False
            try:
                self.g.press("esc")
                time.sleep(1)
                left = self.save_exit()
            finally:
                self.sync.post("join-left", left)

    # -- the online directory watchdog (host): any "[HOSTING] Host registration" line ends the game at once
    def watch_registration(self, mark):
        pat = dict(LOADER_PATTERNS)["registration"]

        def loop():
            while not self.watch_stop.is_set():
                for ln in self.loader_lines(mark):
                    if pat.search(ln):
                        self.result["registration"] = ln.strip()[-300:]
                        self.save()
                        for pid in self.g.game_pids():  # our own game of this slot (game_ctl started it)
                            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
                        self.g.log("HOSTING REGISTRATION SEEN, host game killed: %s" % ln.strip())
                        self.sync.abort("host: online directory registration seen: game killed")
                        return
                self.watch_stop.wait(0.5)

        threading.Thread(target=loop, name="registration-watch", daemon=True).start()

    # -- scenario full
    def reads(self):
        """The client copy of the player: strength, current life (set by the hosting server), maximum life (client)."""
        r = {}
        for key, st in (("str", 0), ("life", 6), ("maxlife", 7), ("level", 12)):
            _, lines = self.gc.H("cstat %d" % st)
            r[key] = self.gc.stat_of(lines)
        return r

    def verify_joiner(self):
        """No harness read of the joiner itself exists in a joined game: `cstat` reads the unit id of the last server verb,
        which on a joiner is the single-player id 1, i.e. the HOST's unit as the joiner's client sees it (run
        2026-11-11 15:18: level 1, strength 25 = MpHost). The joiner's own values come from the character sheet
        screenshots; the selected card is in selected_join.png."""
        r = self.reads()
        self.step("host unit as the joiner's client sees it (cstat, id 1)", True, r)

    def sheet(self, name):
        """The character sheet: strength and maximum life as the client counts them, current life as the server sent it
        (the client copy has no stat 6 / 7 in a TCP/IP game: cstat reads 0)."""
        was = getattr(self, "panels_open", False)
        if was:
            self.panels(False)
        self.g.press("c")
        time.sleep(1.2)
        self.shot(name)
        self.g.press("c")
        time.sleep(0.6)
        if was:
            self.panels(True, "again after the sheet")

    def srv(self, st):
        return self.gc.rd("player", st)

    def server_view(self, name, note=None):
        """Joiner: ask the host for the joiner's server values at this point and wait for them."""
        self.sync.post("j-" + name, note)
        v = self.sync.wait("h-" + name, STEP_WAIT_S)
        self.result["mp"].setdefault("server", {})[name] = v
        self.step("server view of the joiner: %s" % name, True, v)
        return v

    def answer_view(self, name):
        """Host: the joiner's values on the server (strength, life, maximum life) when the joiner asks."""
        note = self.sync.wait("j-" + name, STEP_WAIT_S)
        time.sleep(1.0)
        v = {"str": self.srv(0), "life": self.srv(6), "maxlife": self.srv(7), "joiner_note": note,
             "host_client_copy_of_joiner": self.reads().get("str")}
        self.result.setdefault("joiner_server", {})[name] = v
        self.sync.post("h-" + name, v)

    def charm_events(self):
        """(open, closed) line counts of CharmInv's own log: the panel's state as the plugin reports it."""
        p = os.path.join(self.g.GAME_DIR, "mods", "mxl2012", "d2rloader", "logs", "charm-inv.log")
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except OSError:
            return 0, 0
        return txt.count("panel is now open"), txt.count("panel is now closed")

    def panel_visible(self):
        """A left panel is on screen: its red close box (0.352, 0.114) shows. With the character sheet closed that is
        CharmInv's panel. CharmInv logs "panel is now open" only for its console command, not for its button."""
        im = self.g.grab_client().convert("RGB")
        r, g, b = im.getpixel((int(0.352 * im.size[0]), int(0.114 * im.size[1])))
        return r > 130 and g < 100 and b < 70

    def probe_button(self):
        """Single player: does the inventory button open CharmInv (CharmInv's log)? The mouse stays on it for the tooltip."""
        self.g.press("i")
        time.sleep(1.2)
        before = self.charm_events()
        self.click("charminv_button", 1.5)
        opened = self.charm_events()[0] > before[0] or self.panel_visible()
        self.shot("button_probe_sp")
        self.result.setdefault("panel", []).append(["by the inventory button in single player", "button" if opened else None])
        self.step("CharmInv inventory button opens the panel in single player", opened, "")
        if opened:
            self.click("charminv_button", 1.0)
            self.step("the button closes it again", not self.panel_visible(), "")
        self.g.press("i")
        time.sleep(0.8)

    def panels(self, on, where=""):
        """Inventory plus the CharmInv panel. Opening tries the console command, then the inventory button, and checks
        CharmInv's log for "panel is now open"; returns whether the panel opened (moves need it: a drop on a closed
        panel lands in the world)."""
        self.panels_open = on
        if on:
            self.g.press("i")
            time.sleep(1.2)
            before = self.charm_events()[0]
            self.g.console_bg("charminv open")
            time.sleep(1.5)
            how = "console" if self.charm_events()[0] > before or self.panel_visible() else None
            if not how:
                self.click("charminv_button", 1.5)
                how = "button" if self.charm_events()[0] > before or self.panel_visible() else None
            self.charm_how = how
            self.result.setdefault("panel", []).append([where, how])
            self.step("CharmInv panel opens %s" % where, bool(how), how or "no panel after console and button")
            return bool(how)
        before = self.charm_events()[1]
        self.g.console_bg("charminv close")
        time.sleep(0.8)
        if getattr(self, "charm_how", None) and self.panel_visible():
            self.click("charminv_button", 0.8)
        self.charm_how = None
        self.g.press("i")
        time.sleep(0.8)
        return True

    def items_of(self):
        _, il = self.gc.H("items")
        return [self.gc.kv(x) for x in il if x.startswith("item ")]

    def unique_row(self):
        try:
            rows = [r for r in self.gc.carry1_rows() if r[2].split(":")[-1] == UNIQUE[1]]
            if rows:
                return rows[0][0]
        except Exception:
            pass
        return UNIQUE[2]

    def joiner_full_sp(self):
        """Single player (the joiner's own server): charms, Butcher's Tooth twice, stats read on the server."""
        tag = self.meta["tag"]
        self.to_menu_with("MpJoin" + tag)
        sp = self.result["sp"]
        self.gc.H("xp 2000000000")  # Butcher's Tooth needs level 40
        time.sleep(2)
        sp["level"] = self.srv(12)
        sp["base"], sp["life_base"] = self.srv(0), self.srv(7)
        (bc, bs, bl), (pc, ps, pl) = FULL_CHARMS["bag"], FULL_CHARMS["page6"]
        ok, bag = self.make_stat_item("%s 0=%d 7=%d inv" % (bc, bs, bl))
        self.must("backpack charm %s made" % bc, ok, bag)
        time.sleep(1)
        sp["bag"], sp["life_bag"] = self.srv(0), self.srv(7)
        ok, page = self.make_stat_item("%s 0=%d 7=%d inv" % (pc, ps, pl))
        self.must("charm %s made" % pc, ok, page)
        row = self.unique_row()
        ok, ua = self.make_stat_item("%s unique %d inv" % (UNIQUE[0], row))
        self.must("Butcher's Tooth A made", ok, ua)
        sp["bag_item"], sp["page_item"], sp["uniq_a_item"] = bag, page, ua
        self.probe_button()
        self.panels(True, "in single player")
        self.move_item(inv_cell(int(page["x"]), int(page["y"])), charminv_cell(0, 0))
        time.sleep(1)
        sp["page"], sp["life_page"] = self.srv(0), self.srv(7)
        self.move_item(inv_cell(int(ua["x"]), int(ua["y"])), charminv_cell(3, 1))
        time.sleep(1)
        sp["uniq_a"] = self.srv(0)
        ok, ub = self.make_stat_item("%s unique %d inv" % (UNIQUE[0], row))
        self.step("Butcher's Tooth B (second copy) into the backpack", ok, ub)
        sp["uniq_b_item"] = ub
        time.sleep(1.5)
        sp["uniq_b"], sp["life_all"], sp["life_now"] = self.srv(0), self.srv(7), self.srv(6)
        sp["client"] = self.reads()
        sp["items"] = self.items_of()
        self.shot("sp_setup")
        self.step("single player set-up", True, json.dumps({k: sp.get(k) for k in (
            "level", "base", "bag", "page", "uniq_a", "uniq_b", "life_base", "life_bag", "life_page", "life_all", "life_now")}))
        self.panels(False)
        self.must("save and exit", self.save_exit())

    def make_stat_item(self, args):
        ok, lines = self.gc.H("item " + args)
        line = next((x for x in lines if " id=" in x), lines[0] if lines else "")
        it = self.gc.kv(line) if ok and line else {}
        return ok and "x" in it, it

    def joiner_full_mp(self):
        mp, sp = self.result["mp"], self.result["sp"]
        ok, tags = self.direct_join("127.0.0.1")
        self.must("joined 127.0.0.1", ok, "; ".join(sum(tags.values(), []))[:400])
        time.sleep(5)
        self.verify_joiner()
        self.shot("joined")
        self.sheet("sheet_joined")
        self.server_view("joined")
        opened = self.panels(True, "on the joiner in the TCP/IP game")
        self.shot("joiner_charminv_joined")
        bag, ub = sp.get("bag_item") or {}, sp.get("uniq_b_item") or {}
        if not opened:
            for name in SERVER_VIEWS[1:4]:
                self.server_view(name, "skipped: the CharmInv panel did not open")
            self.panels(False)
            return
        if bag:
            self.move_item(inv_cell(int(bag["x"]), int(bag["y"])), charminv_cell(6, 0))
            time.sleep(2)
            self.shot("joiner_bag_to_charminv")
            self.sheet("sheet_joiner_bag_to_charminv")
        self.server_view("bag_in", "backpack charm (x1x +7) into CharmInv (6,0)")
        self.move_item(charminv_cell(0, 0), inv_cell(4, 3))
        time.sleep(2)
        self.shot("joiner_charminv_to_bag")
        self.sheet("sheet_joiner_charminv_to_bag")
        self.server_view("page_out", "CharmInv charm (x2x +3) to the backpack (4,3)")
        if ub.get("x") is not None:
            src = inv_cell(int(ub["x"]), int(ub["y"]))
            self.move_item(src, charminv_cell(8, 2))
            time.sleep(1.5)
            self.shot("joiner_dup_try")
            self.sheet("sheet_joiner_dup_try")
            self.server_view("dup_try", "second Butcher's Tooth into CharmInv (8,2)")
            self.move_item(charminv_cell(8, 2), src)  # placed: back to the backpack; refused it is still on the cursor
            time.sleep(1.2)
            self.shot("joiner_dup_after")
        else:
            self.server_view("dup_try", "skipped: no second copy")
        self.panels(False)

    def joiner_full(self):
        self.joiner_full_sp()
        self.sync.post("join-sp-done", self.result["sp"].get("uniq_b"))
        self.result["mp"] = {}
        self.sync.wait("hosted", STEP_WAIT_S)
        try:
            self.joiner_full_mp()
            self.sync.post("join-moves-done", self.result["mp"])
            mp = self.result["mp"]
            for key in ("bag", "in"):
                self.sync.wait("host-" + key, STEP_WAIT_S)
                time.sleep(1.5)
                mp["host_seen_" + key] = self.reads()
                self.sync.post("seen-" + key, mp["host_seen_" + key])
            self.sync.wait("host-moves-done", STEP_WAIT_S)
            time.sleep(1.5)
            mp["host_seen_out"] = self.reads()
            self.step("host strength as the joiner's client sees it (bag / CharmInv / back)", True,
                      [mp["host_seen_" + k].get("str") for k in ("bag", "in", "out")])
            self.must("joiner save and exit", self.save_exit())
            ok, tags = self.direct_join("127.0.0.1")
            self.must("joined again", ok, "; ".join(sum(tags.values(), []))[:400])
            time.sleep(5)
            self.verify_joiner()
            self.sheet("sheet_rejoined")
            self.server_view("rejoined")
            self.panels(True, "on the joiner after rejoining")
            self.shot("joiner_rejoined_charminv")
            self.panels(False)
        finally:
            left = False
            try:
                left = self.save_exit()
            finally:
                self.sync.post("join-left", left)
        # the save the TCP/IP game wrote, read back in single player (server verbs answer there)
        card = self.gc.card_of(self.result.get("char")) if left else None
        if card and self.gc.enter_game(card):
            time.sleep(3)
            self.must("single player: own character again", self.srv(12) == self.result["sp"].get("level"), self.srv(12))
            items = self.items_of()
            fin = {"str": self.srv(0), "maxlife": self.srv(7), "items": items,
                   "page6_codes": sorted((x.get("code"), x.get("x"), x.get("y")) for x in items if x.get("page") == "6"),
                   "bag_codes": sorted((x.get("code"), x.get("x"), x.get("y")) for x in items if x.get("page") == "0")}
            self.result["sp"]["final"] = fin
            self.panels(True)
            self.shot("sp_final")
            self.panels(False)
            self.step("single player after the TCP/IP game", True, json.dumps({k: fin[k] for k in ("str", "maxlife", "page6_codes", "bag_codes")}))
            self.save_exit()

    def host_full(self):
        """The host's own charm is made in its single-player game: once a joiner is in, every server verb on the host
        acts on the joiner (FindPlayer: first client of the list), which gives the joiner's server values (answer_view)."""
        tag = self.meta["tag"]
        self.to_menu_with("MpHost" + tag)
        own = self.result["own"] = {}
        ok, it = self.make_stat_item("%s 0=%d inv" % HOST_CHARM)
        self.must("host charm made in single player", ok, it)
        time.sleep(1)
        own["item"], own["sp_str"] = it, self.srv(0)
        self.must("host save and exit", self.save_exit())
        self.sync.wait("join-sp-done", STEP_WAIT_S)
        ok, tags = self.host_game("mpt" + tag)
        self.shot("hosted")
        if tags.get("registration") or self.result.get("registration"):
            raise RuntimeError("the hosting game contacted the online directory: %s" % (self.result.get("registration") or tags["registration"][0]))
        self.must("hosting", ok, tags.get("hosting", ["no hosting line"])[0])
        if tags.get("mapping_on"):
            self.step("router mapping stayed off", False, tags["mapping_on"][0])
        _, sl = self.gc.H("state")
        who = self.gc.kv(sl[0]) if sl else {}
        self.must("host plays its own character (amazon, level 1)", who.get("class") == "0" and who.get("level") == "1",
                  "class %s level %s" % (who.get("class"), who.get("level")))
        own["mp_alone"] = {"srv": self.srv(0), "cli": self.reads().get("str")}
        self.sync.post("hosted", {"port": self.meta["port"]})
        for name in SERVER_VIEWS[:4]:
            self.answer_view(name)
        self.sync.wait("join-moves-done", STEP_WAIT_S)
        self.shot("host_with_joiner")
        self.sheet("host_sheet_bag")
        self.sync.post("host-bag", own.get("mp_alone"))
        self.sync.wait("seen-bag", STEP_WAIT_S)
        cell = inv_cell(int(it["x"]), int(it["y"])) if it.get("x") is not None else None
        if self.panels(True, "on the host in the TCP/IP game") and cell:
            self.move_item(cell, charminv_cell(0, 3))
            time.sleep(1.5)
            self.shot("host_charm_in_charminv")
            self.sheet("host_sheet_in_charminv")
            self.sync.post("host-in", None)
            self.sync.wait("seen-in", STEP_WAIT_S)
            self.move_item(charminv_cell(0, 3), cell)
            time.sleep(1.5)
            self.shot("host_charm_back")
        else:
            self.sync.post("host-in", "no panel")
            self.sync.wait("seen-in", STEP_WAIT_S)
        self.panels(False)
        self.sheet("host_sheet_back")
        self.result["host_charminv_lines"] = [ln.strip()[-300:] for ln in self.charm_log_lines()]
        self.sync.post("host-moves-done", own)
        self.answer_view("rejoined")
        self.sync.wait("join-left", STEP_WAIT_S)
        self.shot("host_after_joiner")
        self.must("host save and exit", self.save_exit())

    # -- scenario invtabs
    def it_make(self, spec):
        out = {}
        for key, (code, stats) in spec.items():
            ok, it = self.make_stat_item(" ".join(x for x in (code, stats, "inv") if x))
            self.must("item %s (%s) made" % (key, code), ok, it)
            out[key] = it
            time.sleep(0.6)
        return out

    def keep_saves(self, label):
        """The character's save files as they are now, into <run>/<role>/saves/<label> (the game is at the menu)."""
        import glob
        import shutil
        time.sleep(2)
        d = os.path.join(self.out, "saves", label)
        os.makedirs(d, exist_ok=True)
        got = []
        for p in glob.glob(os.path.join(self.gc.SAVES, self.result.get("char", "?") + ".*")):
            shutil.copy2(p, d)
            got.append(os.path.basename(p))
        self.result.setdefault("saves", {})[label] = got
        self.step("save kept: %s" % label, any(n.lower().endswith(".d2s") for n in got), got)

    def it_status(self):
        return self.gc._invtabs_status_line([])

    def it_link(self, want, timeout=45):
        """The `invtabs` status line once it holds "link <want>" (the link needs a few seconds after the game starts)."""
        t0, st = time.time(), ""
        while time.time() - t0 < timeout:
            st = self.it_status()
            if "link " + want in st:
                break
            time.sleep(2)
        return st

    def it_open(self, where):
        self.g.press("i")
        time.sleep(1.3)
        self.click(self.gc.INVTABS_BUTTON, 1.5)
        st, how = self.it_status(), "the Charms button"
        if self.gc._invtabs_open_state(st, None) != "open":
            self.g.console_bg("invtabs open")
            time.sleep(1.5)
            st, how = self.it_status(), "the console command (the button did not open it)"
        ok = self.gc._invtabs_open_state(st, None) == "open" and "drawn charms" in st
        self.step("charm tab opens %s" % where, ok, "%s; %s" % (how, st[st.find("charm tab"):][-150:]))
        return ok

    def it_close(self):
        self.g.console_bg("invtabs close")
        time.sleep(0.8)
        self.g.press("i")
        time.sleep(0.8)

    def it_log(self):
        return [ln.strip()[-230:] for ln in self.gc._invtabs_log_since(0) if "multiplayer" in ln or "Ctrl+click" in ln][-120:]

    def ctrl(self, xy, wait=2.0):
        self.g.click(xy[0], xy[1], mods=("ctrl",))
        time.sleep(wait)

    def view(self, name, note=None):
        """Joiner: the host reads this player's items, cursor and strength on the server now (and takes its screenshot)."""
        n = self.views = getattr(self, "views", 0) + 1
        self.sync.post("j-v%d" % n, {"name": name, "note": note})
        v = self.sync.wait("h-v%d" % n, STEP_WAIT_S)
        self.result["mp"].setdefault("server", {})[name] = v
        short = sorted((x.get("code"), x.get("page"), x.get("x"), x.get("y")) for x in v.get("items", []) if x.get("page") in ("6",) or x.get("code") in self.it_codes)
        self.step("server view of the joiner: %s" % name, True, "strength %s, cursor %s, %s" % (v.get("str"), v.get("cursor"), short))
        return v

    def answer_views(self, done):
        """Host: answers the joiner's views in order until the barrier `done` is there."""
        t0 = time.time()
        while not self.sync.has(done):
            n = getattr(self, "answered", 0) + 1
            if self.sync.has("j-v%d" % n):
                req = self.sync.get("j-v%d" % n)
                time.sleep(1.0)
                v = {"name": req["name"], "note": req.get("note"), "str": self.srv(0), "cursor": self.gc.held_item(),
                     "items": [{k: x.get(k) for k in ("id", "code", "page", "x", "y")} for x in self.items_of()]}
                self.shot("host_at_%s" % req["name"])
                self.result.setdefault("joiner_server", {})[req["name"]] = v
                self.save()
                self.sync.post("h-v%d" % n, v)
                self.answered = n
                t0 = time.time()
                continue
            why = self.sync.aborted()
            if why is not None:
                raise RuntimeError("other side aborted: %s" % why)
            if time.time() - t0 > STEP_WAIT_S:
                raise TimeoutError("no %r and no view request in %d s" % (done, STEP_WAIT_S))
            time.sleep(0.5)

    def bag(self, v, code):
        """The backpack cell (client fraction) of `code` in a server view."""
        w = it_where(v.get("items"), code)
        if not w or w[0] != 0:
            raise RuntimeError("%s is not in the backpack on the server: %s" % (code, w))
        return inv_cell(w[1], w[2])

    def it_join(self, again=""):
        ok, tags = self.direct_join("127.0.0.1")
        self.must("joined 127.0.0.1%s" % again, ok, "; ".join(sum(tags.values(), []))[:400])
        time.sleep(5)
        want = "joined, read-only" if self.result.get("readonly") else "joined, full"
        st = self.it_link(want)
        self.result["mp"]["link" + again.strip().replace(" ", "_")] = st
        self.must("link%s: %s" % (again, want), "link " + want in st, st[-110:])
        self.shot("join_joined" + again.strip().replace(" ", "_"))

    def joiner_it_moves(self):
        a, b, rune = (IT_JOIN_ITEMS[k][0] for k in ("a", "b", "rune"))
        tab = self.gc._invtabs_cell
        v = self.view("joined")
        self.must("charm tab opens on the joiner", self.it_open("on the joiner in the hosted game"))
        self.shot("join_tab_open")
        self.move_item(self.bag(v, a), tab(2, 1))
        time.sleep(1.5)
        self.shot("join_drag_in")
        v = self.view("drag_in", "charm %s dragged from the backpack to tab cell 2,1" % a)
        self.ctrl(self.bag(v, b))
        self.shot("join_ctrl_in")
        v = self.view("ctrl_in", "charm %s Ctrl+clicked in the backpack" % b)
        home = it_where(self.result["mp"]["server"]["joined"].get("items"), a)[1:]  # its own cell, free again
        self.move_item(tab(2, 1), inv_cell(*home))
        time.sleep(1.5)
        self.shot("join_drag_out")
        v = self.view("drag_out", "charm %s dragged from tab cell 2,1 to backpack cell %d,%d" % ((a,) + home))
        wb = it_where(v.get("items"), b)
        if wb and wb[0] == 6:
            self.ctrl(tab(wb[1], wb[2]))
        self.shot("join_ctrl_out")
        v = self.view("ctrl_out", "charm %s Ctrl+clicked in the tab" % b)
        rune_cell = self.bag(v, rune)
        self.click(rune_cell, 0.8)
        self.click(tab(4, 4), 1.2)
        self.shot("join_rune_over_tab")
        self.view("rune_held", "rune lifted and clicked on tab cell 4,4")
        self.click(rune_cell, 1.2)
        v = self.view("rune_back", "rune put back")
        self.ctrl(self.bag(v, rune))
        self.shot("join_rune_ctrl")
        v = self.view("rune_ctrl", "rune Ctrl+clicked in the backpack")
        self.click(self.bag(v, a), 0.8)
        self.click(IT_PANEL_OUTSIDE, 1.2)
        self.shot("join_outside_held")
        self.view("outside_held", "charm %s lifted and clicked on the panel above the grid" % a)
        self.click(tab(3, 2), 1.5)
        v = self.view("placed", "the held charm put into tab cell 3,2")
        if (it_where(v.get("items"), b) or (None,))[0] == 0:
            self.ctrl(self.bag(v, b))
        self.shot("join_final")
        self.view("final", "charm %s Ctrl+clicked in the backpack again" % b)

    def joiner_it_adopt(self):
        tooth, key = self.result["adopt"]["tooth"], self.result["adopt"]["key"]
        rows = self.meta.get("join_rows") or IT_AREA[1]  # the grid hangs from the panel's bottom: fewer rows start lower
        tab = lambda c, r: self.gc._invtabs_hd_cell(IT_AREA[0], rows, c, r)  # noqa: E731
        v = self.view("joined")
        self.step("items where CharmInv saved them (server)", it_where(v.get("items"), tooth) == (6, 0, 0) and it_where(v.get("items"), key) == (6, 9, 2),
                  "tooth %s, key %s" % (it_where(v.get("items"), tooth), it_where(v.get("items"), key)))
        self.must("charm tab opens on the joiner", self.it_open("on the joiner in the hosted game"))
        self.shot("join_tab_open")
        if self.result.get("readonly"):
            free = inv_cell(*IT_FREE_CELL)
            self.move_item(tab(0, 0), free)
            time.sleep(1.5)
            self.shot("join_ro_out")
            self.view("ro_out", "tooth dragged from tab cell 0,0 to backpack cell %d,%d" % IT_FREE_CELL)
            self.click(free, 0.8)
            self.click(tab(0, 0), 1.2)
            self.shot("join_ro_drag_in")
            self.view("ro_drag_in", "tooth lifted and clicked on tab cell 0,0")
            self.click(free, 1.2)
            self.ctrl(free)
            self.shot("join_ro_ctrl_in")
            self.view("ro_ctrl_in", "tooth put back and Ctrl+clicked in the backpack")
            return
        self.ctrl(tab(0, 0))
        self.shot("join_ctrl_out")
        v = self.view("ctrl_out", "tooth Ctrl+clicked in the tab")
        if (it_where(v.get("items"), tooth) or (None,))[0] == 0:
            self.ctrl(self.bag(v, tooth))
        self.shot("join_ctrl_in")
        self.view("ctrl_in", "tooth Ctrl+clicked in the backpack")

    def joiner_it(self):
        tag, sp, adopt = self.meta["tag"], self.result["sp"], self.meta.get("join_char")
        self.result["readonly"] = bool(self.meta.get("join_rows"))
        if adopt:
            self.must("main menu", self.gc.to_menu())
            self.result["char"] = adopt
            self.must("character %s is in this slot" % adopt, self.gc.card_of(adopt) is not None)
            (_, tooth), (_, key) = self.gc._invtabs_unique("ButchersTooth"), self.gc._invtabs_unique("SacredWorldstoneKey")
            self.result["adopt"] = {"tooth": tooth, "key": key}
            self.it_codes = (tooth, key)
        else:
            self.to_menu_with("MpJoin" + tag)
            sp["base"] = self.srv(0)
            sp["made"] = self.it_make(IT_JOIN_ITEMS)
            time.sleep(1)
            sp["str"], sp["items"] = self.srv(0), self.items_of()
            self.shot("sp_setup")
            self.must("save and exit", self.save_exit())
            self.it_codes = tuple(v[0] for v in IT_JOIN_ITEMS.values())
        self.keep_saves("0-setup")
        self.sync.post("join-sp-done", sp.get("str"))
        self.result["mp"] = {}
        self.sync.wait("hosted", STEP_WAIT_S)
        try:
            self.it_join()
            self.joiner_it_adopt() if adopt else self.joiner_it_moves()
            self.sync.post("join-moves-done", None)
            for key in IT_HOST_STEPS:  # the host's own moves: this joined player's window at each of them
                self.sync.wait("host-" + key, STEP_WAIT_S)
                self.shot("join_while_host_" + key)
                self.sync.post("seen-" + key, None)
            self.sync.wait("host-moves-done", STEP_WAIT_S)
            self.view("after_host", "after the host's own moves")
            self.it_close()
            self.sync.post("join-views-done", None)
            self.must("joiner save and exit", self.save_exit())
            self.keep_saves("1-after")
            self.sync.post("join-left", True)
            self.sync.wait("hosted2", STEP_WAIT_S)
            self.it_join(" again")
            self.it_open("on the joiner after joining again")
            self.shot("join_rejoined_tab")
            self.view("rejoined", "after Save and Exit and a new hosted game")
            self.it_close()
            self.sync.post("join-views2-done", None)
            self.must("joiner save and exit again", self.save_exit())
            self.keep_saves("2-rejoin")
            self.sync.post("join-left2", True)
        finally:
            self.result["invtabs_log"] = self.it_log()
            self.save()

    def cell_differs(self, xy, base):
        """The 24 x 24 box at client fraction xy differs from the same box of `base` (an earlier grab): an item is there
        now that was not, or the other way round."""
        now = self.g.grab_client().convert("L")
        w, h = now.size
        cx, cy = int(xy[0] * w), int(xy[1] * h)
        box = (cx - 12, cy - 12, cx + 12, cy + 12)
        a, b = now.crop(box).tobytes(), base.crop(box).tobytes()
        return sum(abs(x - y) for x, y in zip(a, b)) / max(1, len(a)) > 12

    def host_step(self, key, note=""):
        self.shot("host_" + key)
        self.result["own"].setdefault("moves", []).append([key, note])
        self.save()
        self.sync.post("host-" + key, note)
        self.sync.wait("seen-" + key, STEP_WAIT_S)

    def host_it_moves(self):
        """The host's own charm and rune with a joined player in the game. The server verbs act on the joiner now, so
        each step is a screenshot and the plugin's log line; the host's items are read once the joiner left."""
        own = self.result["own"]
        made = own["made"]
        cell = lambda k: inv_cell(int(made[k]["x"]), int(made[k]["y"]))  # noqa: E731
        tab = self.gc._invtabs_cell
        self.must("charm tab opens on the host", self.it_open("on the host with a joined player in the game"))
        self.host_step("tab")
        self.g.click(0.5, 0.62, move_only=True)
        time.sleep(0.5)
        full = self.g.grab_client().convert("L")  # the charm in its backpack cell
        self.click(cell("c"), 0.8)
        self.click(tab(2, 1), 1.5)
        self.host_step("drag_in", "charm dragged to tab cell 2,1")
        self.click(tab(2, 1), 0.8)
        self.click(cell("c"), 1.5)
        self.host_step("drag_out", "charm dragged back to its backpack cell")
        self.ctrl(cell("c"))
        self.host_step("ctrl_in", "charm Ctrl+clicked in the backpack")
        self.click(cell("rune"), 0.8)
        self.click(tab(4, 4), 1.2)
        self.shot("host_rune_over_tab")
        self.click(cell("rune"), 1.2)
        self.ctrl(cell("rune"))
        self.host_step("rune", "rune dragged to tab cell 4,4 (stays on the cursor), put back, Ctrl+clicked")
        self.click(tab(0, 0), 0.8)
        self.click(IT_PANEL_OUTSIDE, 1.2)
        self.host_step("outside", "charm lifted from tab cell 0,0 and clicked on the panel above the grid")
        self.click(tab(5, 3), 1.5)
        self.host_step("placed", "the held charm put into tab cell 5,3")
        # Ctrl+click on the charm in the tab (D2RLoader's own move to the backpack on the hosting game); when it is back
        # in its backpack cell it is Ctrl+clicked into the tab once more (first free cell: 0,0)
        self.ctrl(tab(5, 3))
        self.g.click(0.5, 0.62, move_only=True)
        time.sleep(0.5)
        back = not self.cell_differs(cell("c"), full)
        if back:
            self.ctrl(cell("c"))
        own["ctrl_out_back"] = back
        self.host_step("ctrl_out", "charm Ctrl+clicked in the tab; back in its backpack cell: %s%s" % (back, ", Ctrl+clicked into the tab again" if back else ""))
        self.it_close()

    def it_host_game(self, name):
        ok, tags = self.host_game(name)
        self.shot("hosted_" + name)
        if tags.get("registration") or self.result.get("registration"):
            raise RuntimeError("the hosting game contacted the online directory: %s" % (self.result.get("registration") or tags["registration"][0]))
        self.must("hosting %s" % name, ok, tags.get("hosting", ["no hosting line"])[0])
        if tags.get("mapping_on"):
            self.step("router mapping stayed off", False, tags["mapping_on"][0])

    def host_it(self):
        tag = self.meta["tag"]
        self.to_menu_with("MpHost" + tag)
        own = self.result["own"] = {}
        own["base"] = self.srv(0)
        own["made"] = self.it_make(IT_HOST_ITEMS)
        time.sleep(1)
        own["sp_str"], own["sp_items"] = self.srv(0), self.items_of()
        self.must("host save and exit", self.save_exit())
        self.keep_saves("0-setup")
        self.sync.wait("join-sp-done", STEP_WAIT_S)
        self.it_host_game("mpt" + tag)
        hr = IT_HOST_ITEMS["rune"][0]
        self.must("host plays its own character", it_where(self.items_of(), hr) is not None, "its rune %s is in the server's item list" % hr)
        self.sync.post("hosted", {"port": self.meta["port"]})
        try:
            self.answer_views("join-moves-done")
            own["link"] = self.it_status()
            self.step("host status with the joined player", True, own["link"][-70:])
            self.host_it_moves()
            self.sync.post("host-moves-done", None)
            self.answer_views("join-views-done")
            self.sync.wait("join-left", STEP_WAIT_S)
            time.sleep(4)
            own["after_items"], own["after_str"] = self.items_of(), self.srv(0)  # alone again: the host's own
            self.step("host's own items on the server after its moves", it_where(own["after_items"], hr) is not None,
                      "charm %s, rune %s" % (it_where(own["after_items"], IT_HOST_ITEMS["c"][0]), it_where(own["after_items"], hr)))
            self.must("host save and exit", self.save_exit())
            self.keep_saves("1-after")
            self.it_host_game("mpu" + tag)
            self.sync.post("hosted2", None)
            self.answer_views("join-views2-done")
            self.it_open("on the host after hosting again")
            self.shot("host_rejoined_tab")
            self.it_close()
            self.sync.wait("join-left2", STEP_WAIT_S)
            time.sleep(4)
            own["rejoin_items"] = self.items_of()
            self.step("host's own items on the server in the second game", True,
                      "charm %s, rune %s" % (it_where(own["rejoin_items"], IT_HOST_ITEMS["c"][0]), it_where(own["rejoin_items"], hr)))
            self.must("host save and exit again", self.save_exit())
            self.keep_saves("2-rejoin")
        finally:
            self.result["invtabs_log"] = self.it_log()
            self.save()

    # -- the joiner's charm tab with another number of rows for the run (--join-rows): another tab table than the host's
    def rows_for_run(self):
        rows = self.meta.get("join_rows")
        if not rows or self.role != "join":
            return
        cfg = os.path.join(self.mod, "d2rloader", "config")
        self.it_toml = os.path.join(cfg, "invtabs.toml")
        with open(self.it_toml, "rb") as f:
            self.it_toml_backup = f.read()
        text, n = re.subn(r"(?m)^rows = \d+", "rows = %d" % rows, self.it_toml_backup.decode("utf-8"), count=1)
        if n != 1:
            raise RuntimeError("invtabs.toml has no rows line to change")
        with open(self.it_toml, "wb") as f:
            f.write(text.encode("utf-8"))
        for p in (os.path.join(cfg, "invtabs-layout.txt"), os.path.join(cfg, "invtabs-layout.txt.tmp")):
            if os.path.exists(p):  # the tab's remembered reach would widen it again
                os.remove(p)
        self.g.log("invtabs.toml: charm tab rows = %d for this run" % rows)

    def rows_restore(self):
        if getattr(self, "it_toml_backup", None) is None:
            return True
        with open(self.it_toml, "wb") as f:
            f.write(self.it_toml_backup)
        cfg = os.path.dirname(self.it_toml)
        for p in (os.path.join(cfg, "invtabs-layout.txt"), os.path.join(cfg, "invtabs-layout.txt.tmp")):
            if os.path.exists(p):
                os.remove(p)
        with open(self.it_toml, "rb") as f:
            ok = f.read() == self.it_toml_backup
        self.g.log("invtabs.toml restored: %s" % ok)
        return ok

    # -- whole worker
    def run(self):
        self.sync.post("token-" + self.role, os.getpid())
        other = "join" if self.role == "host" else "host"
        try:
            self.sync.wait("token-" + other, TOKEN_WAIT_S)
        except (TimeoutError, RuntimeError) as e:
            self.result["error"] = "no second game token: %s" % e
            self.sync.abort("%s: %s" % (self.role, self.result["error"]))
            self.save()
            return 3
        # A session lock (pid 0) for the whole worker: game_ctl's stop() keeps it, so the slot stays ours until the
        # loader config is back; released below.
        slots = self.g.game_slots
        ok, msg = slots.acquire(self.g.SLOT, self.g.LOCK_OWNER, pid=0)
        self.g.log("slot %d: %s" % (self.g.SLOT, msg))
        if not ok:
            self.result["error"] = "slot lock: %s" % msg
            self.sync.abort("%s: %s" % (self.role, self.result["error"]))
            self.save()
            return 3
        rc = 0
        try:
            self.net_keys_off()
            if self.meta.get("stage_charminv"):
                self.stage_charminv()
            self.rows_for_run()
            scenario = self.meta.get("scenario")
            host, join = {"full": (self.host_full, self.joiner_full), "invtabs": (self.host_it, self.joiner_it)}.get(scenario, (self.host_side, self.joiner_side))
            host() if self.role == "host" else join()
        except Exception as e:
            rc = 1
            self.result["error"] = "%s: %s" % (type(e).__name__, e)
            self.g.log(traceback.format_exc())
            self.shot("error")
            self.sync.abort("%s: %s" % (self.role, self.result["error"]))
        finally:
            self.watch_stop.set()
            try:
                self.g.stop()
            finally:
                restored = self.net_keys_restore()
                if not self.rows_restore():
                    self.result["error"] = (self.result.get("error") or "") + "; invtabs.toml NOT restored"
                    restored = False
                if not self.unstage_charminv():
                    self.result["error"] = (self.result.get("error") or "") + "; staged CharmInv NOT removed"
                    restored = False
                if not restored:
                    self.result["error"] = (self.result.get("error") or "") + "; d2rloader.toml NOT restored"
                    rc = 1
                # release() puts a pending shared-file snapshot back first and keeps the lock when it can't
                if self.meta.get("session"):
                    self.g.log("slot %d stays locked by the session %s" % (self.g.SLOT, self.g.LOCK_OWNER))
                elif restored and not slots.slot_processes(self.g.GAME_DIR) and slots.release(self.g.SLOT, self.g.LOCK_OWNER, manual=True):
                    self.g.log("slot %d lock released" % self.g.SLOT)
                else:
                    self.g.log("slot %d lock kept: game still running or shared files not restored" % self.g.SLOT)
                self.save()
        return rc


def cmd_worker(args):
    return Worker(args.role, args.dir).run()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--host-slot", type=int, required=True)
    r.add_argument("--join-slot", type=int, required=True)
    r.add_argument("--scenario", default="charminv", choices=["charminv", "full", "invtabs"])
    r.add_argument("--join-char", help="scenario invtabs: the joiner plays this existing character of its slot (saved with CharmInv)")
    r.add_argument("--join-rows", type=int, help="scenario invtabs: rows of the joiner's charm tab for the run (another tab table: read-only)")
    r.add_argument("--session", help="lane session name: both slots are locked as <session>-s<N> before the run and stay locked after")
    r.add_argument("--port", type=int, default=4000)
    r.add_argument("--stage-charminv", action="store_true", help="put CharmInv into a slot that lacks it for the run")
    r.add_argument("--tag", help="two characters for the throwaway names (default: minutes of the clock)")
    p = sub.add_parser("preflight")
    p.add_argument("--host-slot", type=int, required=True)
    p.add_argument("--join-slot", type=int, required=True)
    p.add_argument("--session")
    w = sub.add_parser("worker")
    w.add_argument("--role", choices=["host", "join"], required=True)
    w.add_argument("--dir", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "preflight":
        return 0 if preflight(a.host_slot, a.join_slot, session=a.session) else 2
    return cmd_worker(a)


if __name__ == "__main__":
    sys.exit(main())
