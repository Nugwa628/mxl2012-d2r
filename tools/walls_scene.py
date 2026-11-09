"""HD walls composed like a level designer would: the classic layout as structures, rebuilt from D2R's own HD kit.

tools/walls_hd.py guesses an HD piece per wall cell from statistics. That fails where D2R builds a wall from a few big models
(the Monastery facade: a 4-tile wall, a 7-tile gateway, pillars between them): most cells of such a wall are learnt empty and
the rest copy whatever stood there. This module works on whole structures instead:

  1. classic layout (find_runs, find_posts): wall runs, i.e. unbroken lines of wall tiles on one cell edge (a right wall,
     orientation 2/3/6/9, lies on the cell's z = y * 10 edge and runs along x; a left wall, 1/4/5/8, on its x = x * 10 edge,
     running along z), with their tiles in order, and the posts (orientation 7: pillars and junctions).
  2. D2R's kit (Kit.add / Kit.finish): on every D2R map that uses the tile set, the scene's wall entities are grouped by pivot
     (a wall with its spikes and crests), measured with their models' bounding boxes and laid over the map's own runs. A group
     whose box is long along a run is a wall piece: the kit records its length in tiles, its pivot against the run line, its
     yaw and mirror, its height, and for each tile it covers the slot (cell index inside the piece). A small group is a post
     (pillar, junction), recorded against the tile under it; a post next to a piece's end is a joint.
     Pieces learnt on left walls are turned into the right-wall frame (x and z swapped: yaw 90 - a and a mirrored local x,
     which is how the classic left and right wall tiles mirror each other on screen), so one piece serves both directions.
  3. composition (compose): per run, consecutive cells whose tiles D2R draws with the same piece, in rising slot order, form a
     segment; the segment gets that piece (several in a row for a long segment), fitted to the segment's length by a stretch
     along the run within STRETCH. Cells no D2R map covers get the tile set's most used piece of their direction (family);
     their height follows the classic tile against the tiles the piece was learnt on (HEIGHT_RANGE). Joints go on every piece
     boundary and run end, posts on the cells D2R gives them.

The result replaces walls_hd's per-cell pick on the tiles it covers (walls_hd.build_scene `structured`); everything else (floor
cells, trees, specials, tile sets without a kit) stays with walls_hd. Tile sets the kit lacks are listed in compose()'s stats.

  py -3 -I tools/walls_scene.py report [--out DIR]   structures, kit and composition stats per map -> DIR/walls_scene.json
"""
import collections
import copy
import functools
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

TILE = 10.0
EDGE_X = {2, 3, 6, 9}        # right walls: on the cell's z = y * TILE edge, running along x
EDGE_Z = {1, 4, 5, 8}        # left walls: on the cell's x = x * TILE edge, running along z
POSTS = {7}                  # south corners: pillars and junctions
LONG = 15.0                  # a group whose box is at least this long along one axis ...
LONG_RATIO = 2.5             # ... and this many times its depth is a wall piece; smaller in both axes than LONG: a post
MIN_OVERLAP = 5.0            # a piece covers a cell when its box overlaps the cell's span along the run by this much
LINE_NEAR = 8.0              # a piece belongs to a run whose line is this close to its box (D2R's walls are ~14 units thick)
STRETCH = (0.8, 1.25)        # a piece is stretched along its run at most this much to fit a segment
HEIGHT_RANGE = (0.6, 1.6)    # family pieces: height scale from the classic tiles, clamped
FULL_PER_PX = 0.028          # full wall height: HD units per pixel of the classic tile (walls_hd.HEIGHT_PER_PX); lower pieces are not used
POST_SHARE = 0.25            # a tile gets the post D2R puts on at least this share of its cells
JOINT_NEAR = 3.0             # a post within this distance of a piece's end is a joint
JOIN_SCALE = (0.6, 2.0)      # a joint between a sprite wall and a D2R piece is scaled in height at most this much (join_fit)
JOIN_FOOT = 7.0              # ... and is a post: its footprint at most this long each way (not a ruin corner, fence or wall slab)
BASE_Y = 5.0                 # group members whose box starts above this are details on top (spikes), not the footprint
OPENING = re.compile(r"gate|door|entrance|portal|arch", re.I)   # pieces with an opening: never a family stand-in
VARIATIONS_KEEP = 3          # a composed piece keeps this many of its model variations (D2R's lists of 16-30 entries made
                             # desertpeak's and dungrm6a's scenes reach the byte cap: 3.7 KB per wall piece)
SHORT = {"ModelDefinitionComponent": "m", "TransformDefinitionComponent": "t", "ModelPlatformTierComponent": "p",
         "WallTransparencyComponent": "w", "ModelVariationDefinitionComponent": "v"}


# ---- classic layout ----------------------------------------------------------------------------------------------------
Run = collections.namedtuple("Run", "axis line start tiles")   # axis 'x' (line = row y) or 'z' (line = column x); tiles per cell


def axis_of(orientation: int):
    return "x" if orientation in EDGE_X else "z" if orientation in EDGE_Z else None


def edge_tiles(cells: dict) -> dict:
    """{(axis, line, index): tile} for every wall-edge tile of `cells` ({(x, y): tuple of (folder, o, s, q)}, walls_hd's
    wall_cells). A cell with two tiles on one edge keeps the first (sorted) one; unresolved tiles (folder None) are left out."""
    out = {}
    for (x, y), key in cells.items():
        for t in key:
            a = axis_of(t[1])
            if a is None or t[0] is None:
                continue
            out.setdefault((a, y, x) if a == "x" else (a, x, y), t)
    return out


def find_runs(cells: dict) -> list:
    """The wall runs: maximal unbroken lines of edge tiles of one tile set folder along one axis, in (axis, line, start) order."""
    edges = edge_tiles(cells)
    runs = []
    for (a, line, i), t in sorted(edges.items()):
        prev = edges.get((a, line, i - 1))
        if runs and prev is not None and prev[0] == t[0] and runs[-1].axis == a and runs[-1].line == line \
                and runs[-1].start + len(runs[-1].tiles) == i:
            runs[-1].tiles.append(t)
        else:
            runs.append(Run(a, line, i, [t]))
    return runs


def find_posts(cells: dict) -> list:
    """[((x, y), tile)] of the post tiles (POSTS)."""
    return sorted((xy, t) for xy, key in cells.items() for t in key if t[1] in POSTS and t[0] is not None)


def run_cells(run: Run) -> list:
    """The (x, y) cells of a run in order."""
    return [(run.start + i, run.line) if run.axis == "x" else (run.line, run.start + i) for i in range(len(run.tiles))]


# ---- frames ------------------------------------------------------------------------------------------------------------
def yaw_of(t: dict) -> float:
    q = t.get("orientation") or {}
    return math.degrees(2 * math.atan2(float(q.get("y", 0.0)), float(q.get("w", 1.0))))


def quat(yaw: float) -> dict:
    a = math.radians(yaw) / 2
    return {"x": 0.0, "y": round(math.sin(a), 6), "z": 0.0, "w": round(math.cos(a), 6)}


def rotate(bx: float, bz: float, yaw: float):
    """A model-local (x, z) offset turned by yaw (walls_hd.footprint's convention)."""
    a = math.radians(yaw)
    return bx * math.cos(a) + bz * math.sin(a), -bx * math.sin(a) + bz * math.cos(a)


def swap_member(m: dict) -> dict:
    """A member (see Kit) mirrored across the x = z diagonal: a left-wall placement as a right-wall one and back."""
    return dict(m, du=m["dv"], dv=m["du"], yaw=(90.0 - m["yaw"]) % 360.0, scale=(-m["scale"][0], m["scale"][1], m["scale"][2]))


def world_box(box, x: float, z: float, yaw: float, scale):
    """(x0, z0, x1, z1, y0, y1) of a model box placed at (x, z) with yaw and scale."""
    (lx, ly, lz), (hx, hy, hz) = box
    sx, sy, sz = scale
    pts = [rotate(sx * bx, sz * bz, yaw) for bx in (lx, hx) for bz in (lz, hz)]
    ys = (sy * ly, sy * hy)
    return (x + min(p[0] for p in pts), z + min(p[1] for p in pts), x + max(p[0] for p in pts), z + max(p[1] for p in pts),
            min(ys), max(ys))


# ---- D2R's kit ---------------------------------------------------------------------------------------------------------
def _transform(e):
    return next((c for c in e.get("components", ()) if c.get("type") == "TransformDefinitionComponent"), None)


class Kit:
    """D2R's wall pieces, posts and joints per tile set, learnt from its own maps.

    A member is {entity, model, du, dv, dy, yaw, scale}: one entity of a group, its offset from the group's pivot in the
    right-wall frame (u along the run, v across), its height offset, yaw and scale in that frame. A piece is
    {members, u0, u1, v0, v1, height, cells, folder}: the members, its footprint box against the first cell it covers (u) and
    the run line (v), and the number of cells it covers."""

    def __init__(self, box_of=None, model_of=None, keep=None):
        self.box_of = functools.lru_cache(maxsize=None)(box_of) if box_of else None   # model files are parsed once
        self.model_of = model_of
        self.keep = keep or (lambda model: True)      # model -> whether it may be part of a wall group
        self.heights = {}                             # (folder, o, s, q) -> classic tile height in pixels
        self._maps = []                               # [(name, cells, [(entity, x, z)])] until finish()
        self.pieces = {}                              # piece id -> piece
        self.slots = collections.defaultdict(collections.Counter)    # tile -> Counter((piece id, slot))
        self.family = collections.defaultdict(collections.Counter)   # (folder, style) and (folder, None) -> Counter(piece id)
        self.posts = collections.defaultdict(collections.Counter)    # tile -> Counter(post id) (cell-local)
        self.post_tiles = collections.Counter()                     # tile -> cells seen (POST_SHARE)
        self.post_defs = {}                                         # post id -> [member] (du, dv from the cell's origin)
        self.joints = collections.defaultdict(collections.Counter)  # folder -> Counter(joint id)
        self.joint_defs = {}                                        # joint id -> [member] (du, dv from the piece's end)
        self.learnt = collections.Counter()                         # folder -> D2R maps learnt

    def add(self, name: str, cells: dict, ents):
        """cells: walls_hd.wall_cells of a D2R map; ents: walls_hd.wall_entities of its scene ([(entity, x, z)])."""
        self._maps.append((name, cells, list(ents)))

    def finish(self):
        for name, cells, ents in self._maps:
            self._learn(name, cells, ents)
        self._maps = []

    # groups -----------------------------------------------------------------------------------------------------------
    def _groups(self, ents):
        """Entities sharing a pivot (within 1 unit) and a yaw: a wall and its details. -> [[(entity, model, x, y, z, yaw, scale, box)]]"""
        groups = {}
        for e, x, z in ents:
            m = self.model_of(e)
            if not m or not self.keep(m):
                continue
            box = self.box_of(m)
            if not box:
                continue
            t = _transform(e)
            s = t.get("scale") or {}
            scale = (float(s.get("x", 1.0)), float(s.get("y", 1.0)), float(s.get("z", 1.0)))
            y = float((t.get("position") or {}).get("y", 0.0))
            yaw = round(yaw_of(t)) % 360
            k = (round(x), round(z), yaw)
            groups.setdefault(k, []).append((e, m, x, y, z, yaw, scale, box))
        return list(groups.values())

    @staticmethod
    def _footprint(group):
        """Union world box of the members standing on the ground (BASE_Y), with the group's height (all members)."""
        boxes = [world_box(b, x, z, yaw, sc) for _e, _m, x, y, z, yaw, sc, b in group]
        base = [wb for wb, g in zip(boxes, group) if g[3] + wb[4] < BASE_Y] or boxes
        top = max(g[3] + wb[5] for wb, g in zip(boxes, group))
        return (min(b[0] for b in base), min(b[1] for b in base), max(b[2] for b in base), max(b[3] for b in base), top)

    @staticmethod
    def _members(group, px, pz, swap):
        out = []
        for e, m, x, y, z, yaw, sc, _b in sorted(group, key=lambda g: g[1]):
            mem = {"entity": e, "model": m, "du": x - px, "dv": z - pz, "dy": y, "yaw": float(yaw), "scale": sc}
            out.append(swap_member(mem) if swap else mem)
        return out

    def _learn(self, name, cells, ents):
        runs = find_runs(cells)
        if not runs:
            return
        for f in {t[0] for r in runs for t in r.tiles}:
            self.learnt[f] += 1
        lines = collections.defaultdict(list)   # (axis, line) -> runs
        for r in runs:
            lines[(r.axis, r.line)].append(r)
        posts = []
        ends = []    # (folder, x, z, end direction in the right-wall frame (+1: piece's high end), axis)
        for group in self._groups(ents):
            if min(g[3] + world_box(g[7], g[2], g[4], g[5], g[6])[4] for g in group) > BASE_Y:
                continue        # roofs, crests: nothing standing on the ground
            x0, z0, x1, z1, top = self._footprint(group)
            ex, ez = x1 - x0, z1 - z0
            if ex >= LONG and ex >= LONG_RATIO * ez:
                axis = "x"
            elif ez >= LONG and ez >= LONG_RATIO * ex:
                axis = "z"
            elif ex < LONG and ez < LONG:
                posts.append(group)
                continue
            else:
                continue        # corners, buildings: neither a run piece nor a post
            # in the run frame: u along the run, v across it
            u0, u1, v0, v1 = (x0, x1, z0, z1) if axis == "x" else (z0, z1, x0, x1)
            best = None
            for line in range(int(v0 // TILE) - 1, int(v1 // TILE) + 2):
                if not (v0 - LINE_NEAR <= line * TILE <= v1 + LINE_NEAR):
                    continue
                for r in lines.get((axis, line), ()):
                    cov = [i for i in range(len(r.tiles))
                           if min(u1, (r.start + i + 1) * TILE) - max(u0, (r.start + i) * TILE) >= MIN_OVERLAP]
                    if cov and (best is None or len(cov) > len(best[1])):
                        best = (r, cov)
            if best is None or len(best[1]) < 2:
                continue
            r, cov = best
            first = r.start + cov[0]
            _e, _m, px, _py, pz, _yaw, _sc, _b = max(group, key=lambda g: (g[7][1][0] - g[7][0][0]) * (g[7][1][2] - g[7][0][2]))
            pu, pv = (px, pz) if axis == "x" else (pz, px)
            members = self._members(group, px, pz, axis == "z")
            folder = r.tiles[cov[0]][0]
            pid = (folder, tuple((mm["model"], round(mm["yaw"]) % 360, mm["scale"][0] < 0) for mm in members))
            if pid not in self.pieces:
                self.pieces[pid] = {"members": members, "u0": u0 - first * TILE, "u1": u1 - first * TILE,
                                    "pu": pu - first * TILE, "pv": pv - r.line * TILE, "height": top, "cells": len(cov),
                                    "folder": folder, "tiles": [r.tiles[i] for i in cov], "seen": 0}
            piece = self.pieces[pid]
            piece["seen"] += 1
            for j, i in enumerate(cov):
                self.slots[r.tiles[i]][(pid, j)] += 1
            if not is_opening(self.pieces[pid]):
                self.family[(folder, r.tiles[cov[0]][1], r.tiles[cov[0]][2])][pid] += len(cov)
                self.family[(folder, r.tiles[cov[0]][2])][pid] += len(cov)
                self.family[(folder, None)][pid] += len(cov)
            ends.append((folder, axis, r.line, u0, u1))
        # posts: cell-local per tile, and joints at piece ends
        post_at = collections.defaultdict(list)
        for group in posts:
            _e, _m, px, _py, pz, _yaw, _sc, _b = group[0]
            post_at[(int(px // TILE), int(pz // TILE))].append(group)
            for folder, axis, line, u0, u1 in ends:
                pu, pv = (px, pz) if axis == "x" else (pz, px)
                if abs(pv - line * TILE) > LINE_NEAR + 6:
                    continue
                for end in (u0, u1):
                    if abs(pu - end) <= JOINT_NEAR:
                        members = self._members(group, px, pz, axis == "z")
                        jid = (folder, tuple((mm["model"], round(mm["yaw"]) % 360) for mm in members))
                        self.joints[folder][jid] += 1
                        self.joint_defs.setdefault(jid, [dict(mm, dv=mm["dv"] + pv - line * TILE) for mm in members])
        for xy, key in cells.items():
            for t in key:
                if t[0] is None or t[1] not in (POSTS | EDGE_X | EDGE_Z):
                    continue
                self.post_tiles[t] += 1
                for group in post_at.get(xy, ()):
                    _e, _m, px, _py, pz, _yaw, _sc, _b = group[0]
                    members = [dict(mm, du=mm["du"] + px - xy[0] * TILE, dv=mm["dv"] + pz - xy[1] * TILE)
                               for mm in self._members(group, px, pz, False)]
                    oid = tuple((mm["model"], round(mm["du"], 1), round(mm["dv"], 1), round(mm["yaw"]) % 360) for mm in members)
                    self.post_defs.setdefault(oid, members)
                    self.posts[t][oid] += 1

    # picks --------------------------------------------------------------------------------------------------------------
    def slot(self, tile, openings=False):
        """(piece id, slot) D2R draws the tile with most often (openings: among the pieces with an opening only), or None."""
        c = {k: n for k, n in (self.slots.get(tile) or {}).items() if not openings or is_opening(self.pieces[k[0]])}
        return max(c.items(), key=lambda kv: (kv[1], -kv[0][1]))[0] if c else None

    def plain(self, tiles):
        """The plain piece for a stretch of tiles: the one without an opening D2R draws most of them with, else the family
        piece of the first tile, or None."""
        votes = collections.Counter()
        for t in tiles:
            for (pid, _j), n in (self.slots.get(t) or {}).items():
                if not is_opening(self.pieces[pid]):
                    votes[pid] += n
        if votes:
            return max(votes.items(), key=lambda kv: kv[1])[0]
        return self.family_piece(tiles[0])

    def family_piece(self, tile):
        """The tile set's piece covering the most cells for the tile's style, else for the tile set, or None (pieces with an
        opening never: a gate where classic has a plain wall)."""
        for k in ((tile[0], tile[1], tile[2]), (tile[0], tile[2]), (tile[0], None)):
            c = self.family.get(k)
            if c:
                return max(c.items(), key=lambda kv: kv[1])[0]
        return None

    def post(self, tile):
        c = self.posts.get(tile)
        if not c:
            return None
        oid, n = max(c.items(), key=lambda kv: kv[1])
        return oid if n >= POST_SHARE * self.post_tiles[tile] else None

    def joint(self, folder):
        c = self.joints.get(folder)
        return max(c.items(), key=lambda kv: kv[1])[0] if c else None

    def joint_top(self, jid):
        """Height of a joint's top (members' dy + box top), or None when no member's box is known."""
        tops = []
        for m in self.joint_defs.get(jid, ()):
            box = self.box_of(m["model"]) if self.box_of else None
            if box:
                tops.append(m["dy"] + box[1][1] * m["scale"][1])
        top = max(tops, default=None)
        return top if top and top > 0 else None

    def joint_foot(self, jid):
        """(x, z) extent of a joint's footprint (its members' boxes), or None when no member's box is known."""
        boxes = [world_box(b, m["du"], m["dv"], m["yaw"], m["scale"]) for m in self.joint_defs.get(jid, ())
                 for b in [self.box_of(m["model"]) if self.box_of else None] if b]
        if not boxes:
            return None
        return max(b[2] for b in boxes) - min(b[0] for b in boxes), max(b[3] for b in boxes) - min(b[1] for b in boxes)

    def join_fit(self, folders, top):
        """The joint for a sprite <-> D2R join `top` units high, between tile sets `folders` (the D2R side's first):
        -> (joint id, height scale, 'own' | 'similar') or None. 'own': a joint of those tile sets, most used first; 'similar':
        a joint of another tile set of the same act folder (act3/kurast's own joints are footings), the one needing the
        least scaling. A joint is used only when it is a post (JOIN_FOOT) and within JOIN_SCALE of its height."""
        def scale(jid):
            foot = self.joint_foot(jid)
            if foot is None or max(foot) > JOIN_FOOT:
                return None
            t = self.joint_top(jid)
            s = top / t if t else 0.0
            return s if JOIN_SCALE[0] <= s <= JOIN_SCALE[1] else None
        for f in folders:
            for jid, _n in sorted((self.joints.get(f) or {}).items(), key=lambda kv: (-kv[1], repr(kv[0]))):
                s = scale(jid)
                if s:
                    return jid, s, "own"
        acts = {f.split("/")[0] for f in folders}
        best = None
        for f in sorted(self.joints):
            if f in folders or f.split("/")[0] not in acts:
                continue
            for jid in sorted(self.joints[f], key=repr):
                s = scale(jid)
                if s and (best is None or abs(math.log(s)) < abs(math.log(best[1])) - 1e-9):
                    best = (jid, s, "similar")
        return best


# ---- composition ----------------------------------------------------------------------------------------------------------
def is_opening(piece) -> bool:
    return any(OPENING.search(m["model"].rsplit("/", 1)[-1]) for m in piece["members"])


def segments(run: Run, kit: Kit) -> list:
    """[(start index, end index (inclusive), piece id, how)] covering the run, as a designer reads it: openings first, i.e.
    consecutive cells whose tiles D2R draws with the same gate, door or arch piece in rising slots, kept when they hold at least
    half of that piece's cells ('opening'); the stretches between are plain walls ('plain': the plain piece D2R draws most of
    the stretch's tiles with, else the tile set's family piece) or have no piece (None)."""
    marks = [None] * len(run.tiles)
    i = 0
    while i < len(run.tiles):
        s = kit.slot(run.tiles[i], openings=True)
        if s is None:
            i += 1
            continue
        pid, j = s
        k = i + 1
        while k < len(run.tiles):
            n = kit.slot(run.tiles[k], openings=True)
            if n is None or n[0] != pid or n[1] <= j:
                break
            j = n[1]
            k += 1
        if 2 * (k - i) >= kit.pieces[pid]["cells"]:
            for c in range(i, k):
                marks[c] = pid
        i = k
    out = []
    i = 0
    while i < len(run.tiles):
        k = i
        while k + 1 < len(run.tiles) and marks[k + 1] == marks[i]:
            if marks[i] is not None and kit.slot(run.tiles[k + 1], openings=True)[1] <= kit.slot(run.tiles[k], openings=True)[1]:
                break       # the same opening again (Duncraig's two gateways side by side)
            k += 1
        if marks[i] is not None:
            out.append((i, k, marks[i], "opening"))
        else:
            out.append((i, k, kit.plain(run.tiles[i:k + 1]), "plain"))
        i = k + 1
    return out


def fit(length: float, piece: float):
    """(pieces, stretch) to cover `length` units with pieces of `piece` units end to end: as many as fit with a stretch within
    STRETCH, at least one (then at its minimum, centred, when even one is too long)."""
    k = max(1, round(length / piece))
    s = length / (k * piece)
    if s < STRETCH[0] and k > 1:
        k -= 1
        s = length / (k * piece)
    return k, (max(STRETCH[0], min(STRETCH[1], s)) if k == 1 else s)


def _height(tiles, piece, kit):
    """Height scale of a plain piece: the classic tiles' height against the tiles it was learnt on (HEIGHT_RANGE)."""
    mine = [kit.heights.get(t) for t in tiles if kit.heights.get(t)]
    theirs = [kit.heights.get(t) for t in piece["tiles"] if kit.heights.get(t)]
    if not mine or not theirs:
        return 1.0
    r = (sum(mine) / len(mine)) / (sum(theirs) / len(theirs))
    return max(HEIGHT_RANGE[0], min(HEIGHT_RANGE[1], r))


def _emit(members, axis, line, u, v_off, stretch=1.0, hscale=1.0):
    """[(entity template, x, y, z, yaw, scale)] of members placed with their group pivot at run coordinate u, `v_off` across."""
    out = []
    for m in members:
        mm = m if axis == "x" else swap_member(m)
        yaw, (sx, sy, sz) = mm["yaw"], mm["scale"]
        along = abs(math.cos(math.radians(yaw))) >= abs(math.sin(math.radians(yaw)))   # local x lies along world x
        if axis == "x":
            sx, sz = (sx * stretch, sz) if along else (sx, sz * stretch)
            x, z = u + m["du"] * stretch, line * TILE + v_off + m["dv"]
        else:
            sx, sz = (sx, sz * stretch) if along else (sx * stretch, sz)
            x, z = line * TILE + v_off + m["dv"], u + m["du"] * stretch
        out.append((m["entity"], x, m["dy"] * hscale, z, yaw, (sx, sy * hscale, sz)))
    return out


def compose_run(run: Run, kit: Kit, stats=None, gaps=None):
    """-> ([(entity template, x, y, z, yaw, scale)], covered tile indices) for one run: each segment's pieces with their boxes
    end to end over the segment (centred when one piece is longer even at its minimum stretch), a joint on every boundary.
    gaps (a set): gets the indices of the tiles left without a full-height piece (no kit piece, or only a footing or trim)."""
    stats = stats if stats is not None else collections.Counter()
    gaps = gaps if gaps is not None else set()
    out, covered, bounds = [], set(), []
    for i0, i1, pid, how in segments(run, kit):
        n = i1 - i0 + 1
        if pid is None:
            stats["cells_no_kit"] += n
            gaps.update(range(i0, i1 + 1))
            continue
        piece = kit.pieces[pid]
        length = piece["u1"] - piece["u0"]
        k, s = fit(n * TILE, length)
        a = (run.start + i0) * TILE + (n * TILE - k * length * s) / 2
        h = _height(run.tiles[i0:i1 + 1], piece, kit) if how == "plain" else 1.0
        px = [kit.heights[t] for t in run.tiles[i0:i1 + 1] if kit.heights.get(t)]
        if px and piece["height"] * h < FULL_PER_PX * sum(px) / len(px):
            stats["cells_too_low"] += n      # a footing or trim, not the wall: the per-tile walls stay
            gaps.update(range(i0, i1 + 1))
            continue
        for j in range(k):
            u0 = a + j * length * s
            out += _emit(piece["members"], run.axis, run.line, u0 + (piece["pu"] - piece["u0"]) * s, piece["pv"], s, h)
            bounds += [u0, u0 + length * s]
        stats["cells_" + how] += n
        stats["pieces"] += k
        covered.update(range(i0, i1 + 1))
    jid = kit.joint(run.tiles[0][0])
    if jid and out:
        last = None
        for u in sorted(bounds):
            if last is not None and u - last < 3.0:
                continue
            out += _emit(kit.joint_defs[jid], run.axis, run.line, u, 0.0)
            stats["joints"] += 1
            last = u
    return out, covered


def edge_points(axis, line, i):
    """The two grid points (cell corners, in cells) an edge tile (edge_tiles' (axis, line, index)) runs between."""
    return ((i, line), (i + 1, line)) if axis == "x" else ((line, i), (line, i + 1))


def join_points(sprite_edges: dict, d2r_edges: dict) -> list:
    """Where a sprite wall meets a D2R piece: grid points that end an edge drawn as a sprite and an edge drawn by D2R, in a
    line or at a corner. sprite_edges: {(axis, line, index): (top height, folder)}; d2r_edges: {(axis, line, index): folder}.
    -> [((x, y) point, axis of the sprite edge, top: highest sprite edge there, folders: D2R sides' then the sprite's)]."""
    at = collections.defaultdict(lambda: ([], []))
    for e, v in sprite_edges.items():
        for p in edge_points(*e):
            at[p][0].append((e, v))
    for e, f in d2r_edges.items():
        if e in sprite_edges:
            continue
        for p in edge_points(*e):
            at[p][1].append((e, f))
    out = []
    for p in sorted(at):
        sp, dp = at[p]
        if sp and dp:
            sp.sort()
            folders = list(dict.fromkeys([f for _e, f in sorted(dp)] + [v[1] for _e, v in sp]))
            out.append((p, sp[0][0][0], max(v[0] for _e, v in sp), folders))
    return out


def place_joins(points, kit: Kit, taken=(), stats=None):
    """Joints on join_points(): the tile set's joint (Kit.join_fit), its height scaled to the sprite wall's top. taken: grid
    points that have a joint already (a composed run's end). -> ([[(entity template, x, y, z, yaw, scale)] per joint placed],
    [points left])."""
    stats = stats if stats is not None else collections.Counter()
    out, left = [], []
    for p, axis, top, folders in points:
        if p in taken:
            stats["joins_taken"] += 1
            continue
        fit_ = kit.join_fit(folders, top)
        if fit_ is None:
            left.append(p)
            stats["joins_left"] += 1
            continue
        jid, s, how = fit_
        line, u = (p[1], p[0] * TILE) if axis == "x" else (p[0], p[1] * TILE)
        out.append(_emit(kit.joint_defs[jid], axis, line, u, 0.0, 1.0, s))
        stats["joins_" + how] += 1
    return out, left


def joint_points(placed, kit: Kit) -> set:
    """Grid points with a joint already (compose()'s placements): the nearest point to each placed joint member, when it is
    within LINE_NEAR (a joint's pivot lies off the run line by D2R's wall depth)."""
    models = {m["model"] for d in kit.joint_defs.values() for m in d}
    out = set()
    for e, x, _y, z, _yaw, _s in placed:
        if kit.model_of and kit.model_of(e) in models:
            p = (round(x / TILE), round(z / TILE))
            if math.hypot(x - p[0] * TILE, z - p[1] * TILE) <= LINE_NEAR:
                out.add(p)
    return out


def compose(cells: dict, kit: Kit, folders=None, gaps=None):
    """The structured walls of a map. cells: walls_hd's map cells. folders: tile set folders to compose (default: every folder
    the kit learnt). gaps (a set): gets the (x, y) of the run and post cells no full-height D2R piece covers (walls_sprite fills
    them where the per-tile pick stays low too). -> ([(entity template, x, y, z, yaw, scale)], {(x, y): tiles composed}, stats)."""
    gaps = gaps if gaps is not None else set()
    folders = set(kit.learnt) if folders is None else set(folders)
    stats = collections.Counter()
    out, done = [], collections.defaultdict(set)
    missing = collections.Counter()
    for run in find_runs(cells):
        folder = run.tiles[0][0]
        if folder not in folders:
            missing[folder] += len(run.tiles)
            gaps.update(run_cells(run))
            continue
        stats["runs"] += 1
        stats["run_cells"] += len(run.tiles)
        low = set()
        ents, covered = compose_run(run, kit, stats, low)
        out += ents
        for i in covered:
            done[run_cells(run)[i]].add(run.tiles[i])
        gaps.update(run_cells(run)[i] for i in low)
    for xy, t in find_posts(cells):
        if t[0] not in folders:
            continue
        oid = kit.post(t)
        if oid is not None:
            for m in kit.post_defs[oid]:
                out.append((m["entity"], xy[0] * TILE + m["du"], m["dy"], xy[1] * TILE + m["dv"], m["yaw"], m["scale"]))
            stats["posts"] += 1
            done[xy].add(t)
        elif xy not in done:
            gaps.add(xy)
    stats["missing_folders"] = dict(missing)
    return out, dict(done), stats


def entities(placed, prefix="mxs", strip=copy.deepcopy, id_base=0x6D700000):
    """Scene entities of compose()'s placements: copies (strip(entity), e.g. walls_hd.strip_entity) with a new transform,
    names and ids (id_base on; the default 0x6D700000 lies below walls_hd's per-cell range)."""
    out = []
    for n, (e, x, y, z, yaw, scale) in enumerate(placed):
        e = strip(e)
        for c in e["components"]:
            if c.get("type") == "ModelVariationDefinitionComponent" and len(c.get("variations") or ()) > VARIATIONS_KEEP:
                c["variations"] = c["variations"][:VARIATIONS_KEEP]
        t = _transform(e)
        t["position"] = {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)}
        t["orientation"] = quat(yaw)
        t["scale"] = {"x": round(scale[0], 4), "y": round(scale[1], 4), "z": round(scale[2], 4)}
        e["name"] = "%s_%d" % (prefix, n)
        e["id"] = id_base + n % 0x80000
        for c in e["components"]:
            if "name" in c:
                c["name"] = "%s_%s" % (e["name"], SHORT.get(c["type"], c["type"]))
        out.append(e)
    return out


# ---- floors ---------------------------------------------------------------------------------------------------------------
def floor_folders(ds, idx, donor_of=lambda p: p) -> dict:
    """{(x, y): tile set folder} of each cell's first floor tile (any floor layer, walls or not; idx: walls_hd.floor_index)."""
    import ds1_remap
    import maps_hd
    out = {}
    for lay in ds.floor_layers():
        for i, c in enumerate(lay):
            xy = (i % ds.width, i // ds.width)
            if c == 0 or xy in out:
                continue
            p = idx.get((0,) + ds1_remap.cell_key(c))
            if p:
                out[xy] = maps_hd.tiledir(donor_of(p))
    return out


# D2R asserts `visibleTileBiomes.size() < BiomeVisibleCountMax` (terrain.cpp:664) when too many biomes are in view: seen in
# game at Fauztinville's arrival with its scene biome plus 4 and also plus 3 override biomes (lane hdscene2).
OVERRIDE_BIOMES = 2


def biome_overrides(folders: dict, biome: str, biome_of) -> list:
    """D2R's per-tile biome overrides (`perTileBiomeOverrides`, 41 of its own scenes use them; tileX / tileY are cells) for the
    cells whose classic floor tile set has a biome of its own other than the scene's: HD paints those cells with their own
    tile set's ground (the gate's cathedral rugs in the cave biome, glados' Kurast and Travincal floors on the mesa). Only the
    OVERRIDE_BIOMES biomes with the most cells get overrides, the other cells keep the scene's biome."""
    want = {}
    for f in folders.values():
        b = biome_of(f)
        if b and b != biome:
            want[b] = want.get(b, 0) + 1
    kept = set(sorted(want, key=lambda b: (-want[b], b))[:OVERRIDE_BIOMES])
    out = []
    for (x, y), f in sorted(folders.items(), key=lambda t: (t[0][1], t[0][0])):
        b = biome_of(f)
        if b in kept:
            out.append({"type": "TileBiomeOverride", "name": "mxb_%d_%d" % (x, y), "tileX": x, "tileY": y,
                        "biomeFilename": "data/hd/env/biome/%s.json" % b})
    return out


def add_overrides(text: str, overrides: list, max_bytes: int):
    """The scene with `overrides` (biome_overrides) as long as it stays within max_bytes (the rest dropped, in row order)
    and their biomes in its json dependencies. -> (text, overrides kept)."""
    import json
    scene = json.loads(text)
    room = max_bytes - len(text.encode("utf-8"))
    keep, size = [], 0
    for o in overrides:
        n = len(json.dumps(o, separators=(",", ":"))) + 1
        if size + n + 200 > room:
            break
        keep.append(o)
        size += n
    scene["perTileBiomeOverrides"] = keep
    deps = scene.setdefault("dependencies", {}).setdefault("json", [])
    have = {d.get("path") for d in deps}
    for b in sorted({o["biomeFilename"] for o in keep} - have):
        deps.append({"path": b})
    return json.dumps(scene, separators=(",", ":")), len(keep)


def tile_heights(tiles: dict) -> dict:
    """{(folder, o, s, q): classic height in pixels} from parsed .dt1 files (path -> [Tile]); the first file of a key wins."""
    import maps_hd
    out = {}
    for path in sorted(tiles):
        for t in tiles[path] or ():
            if t.orientation:
                out.setdefault((maps_hd.tiledir(path),) + tuple(t.key), abs(t.height))
    return out


def main(argv=None):
    import argparse
    import json
    import walls_hd
    import maps_hd
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["report"])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "work" / "maps_hd"))
    ap.add_argument("--map", action="append", help="only these maps")
    a = ap.parse_args(argv)
    inp = maps_hd.Inputs.load()
    wanted, cells, lib = walls_hd.run(inp, a.map)
    rep = {}
    for e in wanted:
        _placed, done, st = compose(cells[e["map"]], lib.kit)
        rep[e["map"]] = dict(st, cells_done=len(done))
        print(e["map"], dict(st))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "walls_scene.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
