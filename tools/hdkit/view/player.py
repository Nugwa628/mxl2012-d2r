"""Play a unit's modes from its HD state machine: mode -> state -> clip, loops, one-shots, crossfades.

The state machine JSON (`AnimationStateMachine`, named by the unit's UnitRootComponent) gives per state: `modeId` (the
game's unit mode: 0 DT death, 1 NU neutral, 2 WL walk, 3 GH get-hit, 4 A1, 5 A2, 6 BL, 7 SC, 8-11 S1-S4, 12 DD dead,
13 KB knockback, 15 RN run), `loopCount` (0 = loops, 1 = plays once and holds its last pose), `animationBindings`
(weapon class token -> clip names, `hth` for monsters) and per state pair a `crossfadeSeconds`.

Timing, as far as our data tells it:
  - "clip" (default): a clip plays at its own speed (its Duration), as monster3d METHOD rule 20 measured for the death
    clip in game;
  - "classic": the clip is stretched to the classic mode length, frames / (25 * speed / 256) s from the COF
    (METHOD rule 26: the round 10 Fungus clips were written with Duration = that length, so both agree for them).
  Neither is proven for stock clips (NU of mummy1 is 4.0 s against classic's 0.6 s); calibration (in-game frame times)
  settles it.
Loops wrap with the curves continued across the end (curves.py, `loop`), one-shots clamp. A mode change crossfades in
local bone space over the transition's crossfadeSeconds (gr2.blend_locals), from the pose the old state had when it
was left. Classic-side conventions (mode tokens, rates) follow tools/sprite3d/monster3d (s5_clipfit, METHOD rule 26).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from hdkit.view import gr2

MODE_TOKENS = {0: "dt", 1: "nu", 2: "wl", 3: "gh", 4: "a1", 5: "a2", 6: "bl", 7: "sc", 8: "s1", 9: "s2", 10: "s3",
               11: "s4", 12: "dd", 13: "kb", 14: "sq", 15: "rn"}
TOKEN_MODES = {v: k for k, v in MODE_TOKENS.items()}


@dataclass
class State:
    name: str
    state_id: int
    mode: int
    loop: bool
    bindings: dict             # weapon class -> [clip names]


@dataclass
class StateMachine:
    name: str
    states: list
    crossfade: dict = field(default_factory=dict)     # (from state_id, to state_id) -> seconds

    @classmethod
    def from_json(cls, data):
        if isinstance(data, (bytes, str)):
            data = json.loads(data)
        states = [State(s.get("name", ""), int(s["stateId"]), int(s["modeId"]), int(s.get("loopCount", 1)) == 0,
                        dict(s.get("animationBindings") or {})) for s in data.get("states", [])]
        cf = {}
        for g in data.get("transitions", []):
            for it in g.get("settings", []):
                cf[(int(g["from"]), int(it["to"]))] = float(it.get("crossfadeSeconds", 0.0))
        return cls(data.get("name", ""), states, cf)

    def state(self, mode) -> State:
        m = TOKEN_MODES[mode.lower()] if isinstance(mode, str) else int(mode)
        for s in self.states:
            if s.mode == m:
                return s
        raise KeyError("no state for mode %s" % mode)

    def clip_name(self, mode, wclass: str = "hth", variant: int = 0) -> str:
        b = self.state(mode).bindings
        names = b.get(wclass) or b.get("hth") or next(iter(b.values()), [])
        return names[variant % len(names)] if names else ""


@dataclass
class Frame:
    time: float
    mode: int
    clip: str
    clip_t: float
    loop: bool
    prev_clip: str = ""
    prev_t: float = 0.0
    prev_loop: bool = False
    weight: float = 1.0       # weight of the current state (1 = no crossfade left)


class Player:
    def __init__(self, sm: StateMachine, clips: dict, classic: dict | None = None, timing: str = "clip",
                 wclass: str = "hth", method: str = "bspline"):
        """clips: name -> gr2.Clip. classic: mode token -> {"frames": n, "speed": s} (the COF data, e.g. frames.json)."""
        self.sm, self.clips, self.classic = sm, clips, classic or {}
        self.timing, self.wclass, self.method = timing, wclass, method

    def length(self, mode) -> float:
        """Seconds one pass of the mode takes."""
        clip = self.clips.get(self.sm.clip_name(mode, self.wclass))
        own = clip.duration if clip else 0.0
        if self.timing == "classic":
            st = self.sm.state(mode)
            c = self.classic.get(MODE_TOKENS.get(st.mode, ""))
            if c and c.get("frames"):
                return float(c["frames"]) / (25.0 * float(c.get("speed", 256)) / 256.0)
        return own

    def clip_time(self, mode, t: float) -> float:
        """Clip-local time of the mode t seconds after it started (before loop wrap or clamp)."""
        clip = self.clips.get(self.sm.clip_name(mode, self.wclass))
        L = self.length(mode)
        if clip is None or L <= 0:
            return 0.0
        return t * clip.duration / L

    def timeline(self, steps, fps: float = 25.0):
        """steps: [(mode, seconds)] played one after the other. Returns [Frame] at 1/fps."""
        out = []
        t0, prev = 0.0, None        # prev = (state, mode, start time)
        for mode, secs in steps:
            st = self.sm.state(mode)
            fade = self.sm.crossfade.get((prev[0].state_id, st.state_id), 0.0) if prev else 0.0
            n = max(1, int(round(secs * fps)))
            for i in range(n):
                local = i / fps
                f = Frame(t0 + local, st.mode, self.sm.clip_name(mode, self.wclass), self.clip_time(mode, local), st.loop)
                if prev and fade > 0 and local < fade:
                    pst, pmode, pstart = prev
                    f.prev_clip = self.sm.clip_name(pmode, self.wclass)
                    f.prev_t = self.clip_time(pmode, t0 - pstart)      # frozen where it was left
                    f.prev_loop = pst.loop
                    f.weight = local / fade
                out.append(f)
            prev = (st, mode, t0)
            t0 += n / fps
        return out

    def pose(self, sk: gr2.Skeleton, mode=None, t: float = 0.0, frame: Frame | None = None) -> gr2.Pose:
        """Pose of `mode` t seconds after it started, or of a timeline Frame (crossfade included)."""
        if frame is None:
            st = self.sm.state(mode)
            frame = Frame(t, st.mode, self.sm.clip_name(mode, self.wclass), self.clip_time(mode, t), st.loop)
        cur, tc, uns, used = gr2.locals_at(sk, self.clips.get(frame.clip), frame.clip_t, method=self.method,
                                           loop=frame.loop)
        if frame.prev_clip and frame.weight < 1.0:
            prv, _tp, uns2, _u = gr2.locals_at(sk, self.clips.get(frame.prev_clip), frame.prev_t, method=self.method,
                                              loop=frame.prev_loop)
            cur = gr2.blend_locals(prv, cur, frame.weight)
            for k, v in uns2.items():
                uns[k] = uns.get(k, 0) + v
        return gr2.pose_from_locals(sk, cur, frame.clip, tc, uns, used)

    def poser(self, mode=None, t: float = 0.0, frame: Frame | None = None):
        """A `poser(skeleton)` for gpu.Renderer.prepare."""
        return lambda sk: self.pose(sk, mode, t, frame)
