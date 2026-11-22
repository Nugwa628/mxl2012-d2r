"""May a GPU job run now? Lock folders first, then the GPU's own utilisation, then the CPU.

A machine that runs game tests next to offline renders needs one rule: no render while a test run holds its lock, and none
while the GPU or CPU is already busy. `nvidia-smi` only exists on NVIDIA machines; Windows has a vendor-neutral reading, the
performance counter set "GPU Engine" (per process and engine, in percent). The busiest engine is the GPU's load: the
per-process instances of one engine (same adapter LUID, same engine index) are summed, then the largest engine wins.
On Linux the gate uses the amdgpu driver's /sys/class/drm/card*/device/gpu_busy_percent (median of the busiest card in
each sample) and the one-minute load average as a percentage of the logical CPU count. Without an AMD GPU counter the
gate uses the locks and CPU load. Linux waits when a reading reaches its limit, as in lane hdtools-cal3's lingate.py.

  python -m hdkit.gpugate [--locks GLOB ...] [--gpu-max 20] [--cpu-max 60]     prints the reading, exit 0 = free, 1 = busy

Lock globs: the arguments, else the environment variable HDKIT_LOCK_GLOBS (os.pathsep separated), else `lock_globs()` of
an optional module `hdkit_site` (the site adapter of the repository hdkit lives in), else none. Any existing path that
matches a glob counts as a held lock.
"""
import argparse
import csv
import glob
import importlib
import io
import operator
import os
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field

COUNTERS = (r"\GPU Engine(*engtype_3D)\Utilization Percentage",
            r"\GPU Engine(*engtype_Compute*)\Utilization Percentage",
            r"\Processor(_Total)\% Processor Time")
_ENGINE = re.compile(r"GPU Engine\(pid_\d+_luid_(0x[0-9A-Fa-f]+_0x[0-9A-Fa-f]+)_phys_(\d+)_eng_(\d+)_engtype_([^)]+)\)")


@dataclass
class Reading:
    locks: list = field(default_factory=list)     # held lock paths
    gpu: float | None = None                      # busiest GPU engine, percent (None: no counter on this machine)
    gpu_engine: str = ""                          # its engine type
    cpu: float | None = None                      # total CPU, percent
    free: bool = False
    why: str = ""

    def as_dict(self) -> dict:
        return {"free": self.free, "why": self.why, "locks": [os.path.basename(p) for p in self.locks],
                "gpu_percent": None if self.gpu is None else round(self.gpu, 1), "gpu_engine": self.gpu_engine,
                "cpu_percent": None if self.cpu is None else round(self.cpu, 1)}


def parse_typeperf(text: str) -> tuple[float | None, str, float | None]:
    """(busiest engine percent, its engine type, cpu percent) from `typeperf ... -sc 1` CSV output."""
    rows = [r for r in csv.reader(io.StringIO(text)) if r]
    head = next((r for r in rows if r and r[0].startswith("(PDH-CSV")), None)
    if head is None:
        return None, "", None
    data = [r for r in rows[rows.index(head) + 1:] if len(r) == len(head)]
    if not data:
        return None, "", None
    vals = data[-1]
    engines, cpu = {}, None
    for name, v in zip(head[1:], vals[1:]):
        try:
            x = float(v)
        except ValueError:
            continue
        m = _ENGINE.search(name)
        if m:
            key = (m.group(1), m.group(2), m.group(3), m.group(4))
            engines[key] = engines.get(key, 0.0) + x
        elif "Processor" in name:
            cpu = x
    if not engines:
        return None, "", cpu
    key = max(engines, key=engines.get)
    return min(100.0, engines[key]), key[3], cpu


def read_counters(timeout: float = 20.0) -> tuple[float | None, str, float | None]:
    """The Windows GPU engine and CPU counters, one sample (typeperf); on Linux read_linux(). (None, "", None)
    where neither can be read."""
    if sys.platform.startswith("linux"):
        return read_linux()
    if os.name != "nt":
        return None, "", None
    try:
        r = subprocess.run(["typeperf", *COUNTERS, "-sc", "1"], capture_output=True, text=True, timeout=timeout,
                           errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None, "", None
    return parse_typeperf(r.stdout)


DRM_GLOB = "/sys/class/drm/card*/device/gpu_busy_percent"
PROC_STAT = "/proc/stat"


def _cpu_times(proc_stat: str) -> tuple[int, int] | None:
    """(idle, total) jiffies of the "cpu" line of /proc/stat; None when unreadable."""
    try:
        with open(proc_stat) as f:
            first = f.readline().split()
    except OSError:
        return None
    if not first or first[0] != "cpu":
        return None
    v = [int(x) for x in first[1:]]
    idle = v[3] + (v[4] if len(v) > 4 else 0)  # idle + iowait
    return idle, sum(v[:8])                     # guest time is already inside user / nice


def _gpu_busy(drm_glob: str) -> float | None:
    vals = []
    for path in glob.glob(drm_glob):
        try:
            with open(path) as f:
                value = float(f.read().strip())
        except (OSError, ValueError):
            continue
        if 0 <= value <= 100:
            vals.append(value)
    return max(vals) if vals else None


def _cpu_load() -> float | None:
    """One-minute system load as a percentage of the logical CPU count. It can exceed 100%."""
    cores = os.cpu_count()
    if not cores:
        return None
    try:
        return 100.0 * os.getloadavg()[0] / cores
    except OSError:
        return None


def read_linux(samples: int = 5, every: float = 0.4, drm_glob: str = DRM_GLOB, proc_stat: str = PROC_STAT,
               sleep=time.sleep) -> tuple[float | None, str, float | None]:
    """(median GPU busy percent, GPU engine label, normalized one-minute load) on Linux.

    An alternate `proc_stat` path still measures the CPU busy share over the sampling window for existing callers.
    Unavailable measurements return None.
    """
    c0 = _cpu_times(proc_stat) if proc_stat != PROC_STAT else None
    gpus = []
    for i in range(max(1, samples)):
        if i:
            sleep(every)
        g = _gpu_busy(drm_glob)
        if g is not None:
            gpus.append(g)
    if proc_stat == PROC_STAT:
        cpu = _cpu_load()
    else:
        c1 = _cpu_times(proc_stat)
        cpu = None
        if c0 and c1 and c1[1] > c0[1]:
            cpu = 100.0 * (1.0 - (c1[0] - c0[0]) / (c1[1] - c0[1]))
    gpu = statistics.median(gpus) if gpus else None
    return gpu, "amdgpu" if gpu is not None else "", cpu


def default_lock_globs() -> list:
    env = os.environ.get("HDKIT_LOCK_GLOBS")
    if env:
        return [g for g in env.split(os.pathsep) if g]
    try:
        site = importlib.import_module("hdkit_site")
    except ImportError:
        return []
    return list(site.lock_globs())


def held_locks(globs) -> list:
    out = []
    for g in globs:
        out += sorted(glob.glob(g))
    return out


def check(globs=None, gpu_max: float = 20.0, cpu_max: float = 60.0, counters=None) -> Reading:
    """One reading. Locks are checked first: a held lock makes the job wait whatever the counters say. `counters`
    defaults to this module's read_counters, looked up at call time (so a patched read_counters takes effect)."""
    rd = Reading()
    rd.locks = held_locks(default_lock_globs() if globs is None else globs)
    if rd.locks:
        rd.why = "lock held: " + ", ".join(os.path.basename(p) for p in rd.locks)
        return rd
    rd.gpu, rd.gpu_engine, rd.cpu = (counters or read_counters)()
    linux = sys.platform.startswith("linux")
    over_limit, comparison = (operator.ge, ">=") if linux else (operator.gt, ">")
    if rd.gpu is None and rd.cpu is None:
        rd.why = "counters unreadable (typeperf or Linux GPU and CPU readings unavailable): not taken as free"
    elif rd.gpu is not None and over_limit(rd.gpu, gpu_max):
        rd.why = "GPU busy: %.1f%% (%s) %s %g%%" % (rd.gpu, rd.gpu_engine, comparison, gpu_max)
    elif rd.cpu is not None and over_limit(rd.cpu, cpu_max):
        rd.why = "CPU busy: %.1f%% %s %g%%" % (rd.cpu, comparison, cpu_max)
    else:
        rd.free = True
        rd.why = "free" if rd.gpu is not None else "free (no GPU counter on this machine: locks and CPU only)"
    return rd


def wait_free(globs=None, gpu_max=20.0, cpu_max=60.0, every=60.0, most=None, log=print) -> Reading:
    """Check until free; `most` seconds at most (None: no limit). Returns the last reading."""
    t0 = time.time()
    while True:
        rd = check(globs, gpu_max, cpu_max)
        if rd.free or (most is not None and time.time() - t0 >= most):
            return rd
        log("gpugate: %s; next check in %ds" % (rd.why, every))
        time.sleep(every)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hdkit.gpugate", description=__doc__.split("\n")[0])
    ap.add_argument("--locks", nargs="*", default=None, help="lock globs (default: HDKIT_LOCK_GLOBS / hdkit_site)")
    ap.add_argument("--gpu-max", type=float, default=20.0)
    ap.add_argument("--cpu-max", type=float, default=60.0)
    a = ap.parse_args(argv)
    rd = check(a.locks, a.gpu_max, a.cpu_max)
    import json
    print(json.dumps(rd.as_dict()))
    return 0 if rd.free else 1


if __name__ == "__main__":
    sys.exit(main())
