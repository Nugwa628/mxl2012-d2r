#!/usr/bin/env python
"""Runs a command and stops it cleanly when its memory passes a limit (the PC is shared: a job that grows is stopped with a
message instead of being taken down by the kernel's OOM killer with everything around it).

  python tools/memwatch.py [--gb 10] [--every 1.0] -- COMMAND ...

The limit is on the resident memory (RSS) of the command and all its children, read from /proc every `every` seconds. An
address-space cap (ulimit -v, prlimit --as) does not work for the GPU tools: the Vulkan driver reserves several GB of
address space, so a render fails at about a third of the cap. Exit code: the command's own, or 137 when it was stopped (a
line on stderr says so). Linux only.
"""
import argparse
import os
import signal
import subprocess
import sys
import time

PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


def _children(pid: int) -> list:
    out = []
    try:
        for t in os.listdir("/proc/%d/task" % pid):
            with open("/proc/%d/task/%s/children" % (pid, t)) as f:
                out += [int(c) for c in f.read().split()]
    except OSError:
        pass
    return out


def tree_rss(pid: int) -> int:
    """Bytes resident in pid and all its descendants."""
    total, todo, seen = 0, [pid], set()
    while todo:
        p = todo.pop()
        if p in seen:
            continue
        seen.add(p)
        try:
            with open("/proc/%d/statm" % p) as f:
                total += int(f.read().split()[1]) * PAGE
        except (OSError, IndexError, ValueError):
            continue
        todo += _children(p)
    return total


def run(cmd: list, limit: int, every: float = 1.0, log=None) -> int:
    log = log or (lambda s: print(s, file=sys.stderr, flush=True))
    proc = subprocess.Popen(cmd, start_new_session=True)       # its own group: stopping it stops its children too

    def _stop(signum, _frame):                                  # memwatch itself stopped: take the command down with it
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        sys.exit(128 + signum)
    old = {sig: signal.signal(sig, _stop) for sig in (signal.SIGTERM, signal.SIGHUP)}
    peak = 0
    try:
        while proc.poll() is None:
            rss = tree_rss(proc.pid)
            peak = max(peak, rss)
            if rss > limit:
                log("memwatch: stopped %s at %.1f GB resident (limit %.1f GB)" % (cmd[0], rss / 2 ** 30, limit / 2 ** 30))
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                return 137
            time.sleep(every)
    except KeyboardInterrupt:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait()
        raise
    finally:
        for sig, h in old.items():
            signal.signal(sig, h)
    log("memwatch: peak %.1f GB resident" % (peak / 2 ** 30))
    return proc.returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gb", type=float, default=10.0)
    ap.add_argument("--every", type=float, default=1.0)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        ap.error("no command")
    return run(cmd, int(a.gb * 2 ** 30), a.every)


if __name__ == "__main__":
    sys.exit(main())
