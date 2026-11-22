#!/usr/bin/env python
"""Run one command with the whole machine's game budget to itself (lane hdmaps2; <locks>/README.md rules).

For a run that must be alone on the PC (a 4K high-settings capture: no other game may share the GPU or VRAM):
  1. wait until no game.lock.*, game.seat.* or game.want.* exists in the shared lock folder, none of our slots has a
     pending run snapshot or a live game process, and that has held for --grace seconds (default 30: a run frees its lock
     before it restores its slot); polling every --poll seconds, at most --wait seconds;
  2. take every MXL slot lock (game_slots.LINUX_SLOTS: 2, 5, 6, 7) through game_slots.acquire, each with its seat, under
     this process's pid (a real pid: if this process dies, every lock and seat is stale and free again). With
     budget.json max_games = 4 that is every seat, so no other run of either project can start: both take a seat first.
     Another project's slot locks are never touched;
  3. run the command (env MXL_RUN = OWNER, so its game_ctl / game_checks find the locks already theirs);
  4. release whatever is still held (the command's own run releases its slot after the slot restore), lock then seat.
If the seats are fewer than the budget (max_games larger than our 4 slots), the run is refused: there is then no clean
way to block every seat and the caller is told.

  python tools/slots_reserve.py OWNER [--wait 7200] [--poll 20] [--grace 30] -- COMMAND ...
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402

OURS = (2, 5, 6, 7)


def busy() -> list:
    """Locks, seats and wants in the shared folder, plus our slots with a pending run snapshot (a run that freed its lock
    but has not restored its slot yet) or a live game process."""
    import slot_share
    root = game_slots.LOCK_ROOT
    out = sorted(n for n in os.listdir(root) if n.startswith(("game.lock", "game.seat.", "game.want.")))
    for n in OURS:
        if slot_share.pending(n):
            out.append("snapshot pending s%d" % n)
        try:
            if game_slots.game_pids(n):
                out.append("game running s%d" % n)
        except Exception:       # a slot folder missing on this PC: nothing runs there
            pass
    return out


def max_games() -> int:
    try:
        with open(os.path.join(game_slots.LOCK_ROOT, "budget.json"), encoding="utf-8") as f:
            return int(json.load(f)["max_games"])
    except (OSError, ValueError, KeyError):
        return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("owner")
    ap.add_argument("--wait", type=float, default=7200)
    ap.add_argument("--poll", type=float, default=20)
    ap.add_argument("--grace", type=float, default=30, help="seconds everything must stay free before the reservation")
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[argv.index("--") + 1:] if "--" in argv else []
    a = ap.parse_args(argv[:argv.index("--")] if "--" in argv else argv)
    if not cmd:
        ap.error("no command")
    mg = max_games()
    if mg > len(OURS):
        print("slots_reserve: budget.json max_games %d is more than our %d slots: no clean way to hold every seat" % (
            mg, len(OURS)), file=sys.stderr)
        return 2
    t0, free_since = time.time(), None
    while True:
        b = busy()
        if not b:                         # free for a grace period first: the last run may still be restoring its slot
            free_since = free_since or time.time()
            if time.time() - free_since >= a.grace:
                break
            time.sleep(min(a.poll, 5))
            continue
        free_since = None
        if time.time() - t0 > a.wait:
            print("slots_reserve: still in use after %d s: %s" % (a.wait, ", ".join(b)), file=sys.stderr)
            return 3
        print("slots_reserve: waiting, in use: %s" % ", ".join(b), file=sys.stderr, flush=True)
        time.sleep(a.poll)
    held = []
    try:
        for n in OURS:
            ok, msg = game_slots.acquire(n, a.owner, pid=os.getpid())
            print("slots_reserve: slot %d: %s" % (n, msg), file=sys.stderr, flush=True)
            if not ok:
                print("slots_reserve: could not take every slot; giving all back", file=sys.stderr)
                return 4
            held.append(n)
        left = [s for s in busy() if s.startswith("game.seat.") or s.startswith("game.want.")]
        print("slots_reserve: holding slots %s; seats/wants now %s" % (held, left), file=sys.stderr, flush=True)
        env = dict(os.environ, MXL_RUN=a.owner)
        return subprocess.call(cmd, env=env)
    finally:
        for n in reversed(held):
            game_slots.release(n, a.owner, manual=True)
        print("slots_reserve: released; in use now: %s" % (", ".join(busy()) or "nothing"), file=sys.stderr, flush=True)


if __name__ == "__main__":
    sys.exit(main())
