#!/usr/bin/env python
"""Machine and per-game resource samples on Linux (lane slotcap, 2026-11-21): the Linux twin of resource_sample.ps1 for
tools/parallel_smoke.py, and the measurement behind <locks>/budget.json.

  python tools/resource_sample_linux.py --slots 2,5 [--interval 1] [--out samples.jsonl]

One JSON object per sample (one line each):
  t          seconds since the start
  cpu        machine CPU busy in % of all logical cores (/proc/stat), cores = logical core count
  load1      one-minute load average
  availMB    MemAvailable, swapMB = SwapTotal - SwapFree
  vramMB / gttMB / gpuBusy   amdgpu sysfs of the busiest card (mem_info_vram_used, mem_info_gtt_used, gpu_busy_percent)
  games      {slot: {"cpu": % of one core, "pssMB": PSS of every process of the slot's prefix, "vramMB": the prefix's
              amdgpu buffers from /proc/<pid>/fdinfo, "gttMB" likewise (each DRM client counted once; every `fdinfo_every` samples, else
              the last value), "procs": count}}
  xvfb       {"cpu": % of one core, "rssMB"} of every Xvfb on a private display (:100 up, lane linctl), together
Read-only: only /proc and /sys are read.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import game_slots  # noqa: E402

PROC = "/proc"
DRM = "/sys/class/drm"
TICK = os.sysconf("SC_CLK_TCK")


def _read(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def cpu_times():
    """(busy, total) jiffies of all cores together."""
    v = [int(x) for x in _read(os.path.join(PROC, "stat")).splitlines()[0].split()[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)
    return sum(v) - idle, sum(v)


def meminfo():
    d = {}
    for ln in _read(os.path.join(PROC, "meminfo")).splitlines():
        k, _, rest = ln.partition(":")
        try:
            d[k] = int(rest.split()[0])
        except (IndexError, ValueError):
            pass
    return d


def proc_jiffies(pid):
    s = _read(os.path.join(PROC, str(pid), "stat"))
    if not s:
        return None
    f = s.rsplit(")", 1)[-1].split()
    return int(f[11]) + int(f[12])  # utime + stime


def pss_mb(pid):
    for ln in _read(os.path.join(PROC, str(pid), "smaps_rollup")).splitlines():
        if ln.startswith("Pss:"):
            return int(ln.split()[1]) / 1024
    return 0.0


def rss_mb(pid):
    for ln in _read(os.path.join(PROC, str(pid), "status")).splitlines():
        if ln.startswith("VmRSS:"):
            return int(ln.split()[1]) / 1024
    return 0.0


def drm_mem_mb(pids):
    """(VRAM MB, GTT MB) of the amdgpu DRM clients the processes hold (fdinfo drm-memory-vram / drm-memory-gtt, each
    drm-client-id once)."""
    seen, total = set(), [0, 0]
    for pid in pids:
        d = os.path.join(PROC, str(pid), "fdinfo")
        try:
            fds = os.listdir(d)
        except OSError:
            continue
        for fd in fds:
            txt = _read(os.path.join(d, fd))
            if "drm-client-id" not in txt:
                continue
            cid, mem = None, [0, 0]
            for ln in txt.splitlines():
                if ln.startswith("drm-client-id:"):
                    cid = ln.split()[1]
                for i, key in enumerate(("drm-memory-vram:", "drm-memory-gtt:")):
                    if ln.startswith(key):
                        p = ln.split()
                        mem[i] = int(p[1]) * (1024 if len(p) > 2 and p[2].lower().startswith("kib") else 1)
            if cid and cid not in seen:
                seen.add(cid)
                total[0] += mem[0]
                total[1] += mem[1]
    return total[0] / 1048576, total[1] / 1048576


def drm_vram_mb(pids):
    """amdgpu VRAM of the DRM clients the processes hold (drm_mem_mb)."""
    return drm_mem_mb(pids)[0]


def gpu():
    """(busy %, vram MB, gtt MB) of the card with the most VRAM in use."""
    best = (0, 0.0, 0.0)
    try:
        cards = [c for c in os.listdir(DRM) if c.startswith("card") and "-" not in c]
    except OSError:
        return best
    for c in cards:
        dev = os.path.join(DRM, c, "device")
        try:
            busy = int(_read(os.path.join(dev, "gpu_busy_percent")) or 0)
            vram = int(_read(os.path.join(dev, "mem_info_vram_used")) or 0) / 1048576
            gtt = int(_read(os.path.join(dev, "mem_info_gtt_used")) or 0) / 1048576
        except ValueError:
            continue
        if vram >= best[1]:
            best = (busy, vram, gtt)
    return best


def xvfb_pids():
    out = []
    for name in os.listdir(PROC):
        if not name.isdigit():
            continue
        argv = _read(os.path.join(PROC, name, "cmdline")).split("\0")
        if argv and os.path.basename(argv[0]) == "Xvfb" and len(argv) > 1 and argv[1].startswith(":"):
            try:
                if int(argv[1][1:].split(".")[0]) >= 100:
                    out.append(int(name))
            except ValueError:
                pass
    return out


class Sampler:
    def __init__(self, slots, fdinfo_every=5):
        self.slots = list(slots)
        self.fdinfo_every = fdinfo_every
        self.t0 = time.time()
        self.last_cpu = cpu_times()
        self.last_wall = time.time()
        self.last_j = {}
        self.vram = {n: 0.0 for n in self.slots}
        self.gtt = {n: 0.0 for n in self.slots}
        self.count = 0

    def _cpu_pct(self, pids, dt):
        j = 0.0
        for pid in pids:
            now = proc_jiffies(pid)
            if now is None:
                continue
            j += max(0, now - self.last_j.get(pid, now))
            self.last_j[pid] = now
        return 100.0 * j / TICK / dt if dt > 0 else 0.0

    def sample(self):
        busy, total = cpu_times()
        now = time.time()
        dt = now - self.last_wall
        db, dtot = busy - self.last_cpu[0], total - self.last_cpu[1]
        self.last_cpu, self.last_wall = (busy, total), now
        m = meminfo()
        gb, vram, gtt = gpu()
        s = {"t": round(now - self.t0, 1), "cpu": round(100.0 * db / dtot, 1) if dtot else 0.0, "cores": os.cpu_count(),
             "load1": float(_read(os.path.join(PROC, "loadavg")).split()[0]),
             "availMB": m.get("MemAvailable", 0) // 1024, "swapMB": (m.get("SwapTotal", 0) - m.get("SwapFree", 0)) // 1024,
             "vramMB": round(vram), "gttMB": round(gtt), "gpuBusy": gb, "games": {}}
        for n in self.slots:
            pids = game_slots.prefix_pids(n)
            if self.count % self.fdinfo_every == 0:
                self.vram[n], self.gtt[n] = drm_mem_mb(pids) if pids else (0.0, 0.0)
            s["games"][str(n)] = {"cpu": round(self._cpu_pct(pids, dt), 1), "pssMB": round(sum(pss_mb(p) for p in pids)),
                                  "vramMB": round(self.vram[n]), "gttMB": round(self.gtt[n]), "procs": len(pids)}
        xp = xvfb_pids()
        s["xvfb"] = {"cpu": round(self._cpu_pct(xp, dt), 1), "rssMB": round(sum(rss_mb(p) for p in xp)), "n": len(xp)}
        self.count += 1
        return s


def summarize(samples, slots):
    """Mean / peak figures of a list of samples (for parallel_smoke's summary and the slotcap table)."""
    if not samples:
        return {}
    run = samples[1:] or samples  # the first sample has no CPU interval
    out = {"samples": len(samples),
           "cpu_mean": sum(s["cpu"] for s in run) / len(run), "cpu_peak": max(s["cpu"] for s in run),
           "load1_peak": max(s["load1"] for s in samples), "avail_min_mb": min(s["availMB"] for s in samples),
           "swap_peak_mb": max(s["swapMB"] for s in samples), "vram_peak_mb": max(s["vramMB"] for s in samples),
           "gtt_peak_mb": max(s["gttMB"] for s in samples),
           "gpu_mean": sum(s["gpuBusy"] for s in run) / len(run), "gpu_peak": max(s["gpuBusy"] for s in run),
           "xvfb_cpu_mean": sum(s["xvfb"]["cpu"] for s in run) / len(run), "games": {}}
    for n in slots:
        g = [s["games"][str(n)] for s in run if str(n) in s["games"] and s["games"][str(n)]["procs"]]
        if g:
            out["games"][str(n)] = {"cpu_mean": sum(x["cpu"] for x in g) / len(g), "cpu_peak": max(x["cpu"] for x in g),
                                    "pss_peak_mb": max(x["pssMB"] for x in g), "vram_peak_mb": max(x["vramMB"] for x in g),
                                    "gtt_peak_mb": max(x.get("gttMB", 0) for x in g), "seconds": len(g)}
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slots", default="")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--out", default="-")
    a = ap.parse_args(argv)
    slots = [int(x) for x in a.slots.split(",") if x]
    s = Sampler(slots)
    f = sys.stdout if a.out == "-" else open(a.out, "a", encoding="utf-8")
    while True:
        time.sleep(a.interval)
        f.write(json.dumps(s.sample()) + "\n")
        f.flush()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
