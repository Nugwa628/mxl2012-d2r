"""Read D2R's HD asset caches from a running game (bug #360): how full each one is and which files it holds.

D2R keeps every HD asset it has loaded in a fixed-capacity cache per kind (Fog `AssetCache<T, DefaultCapacity>`). When a load
finds the cache full (entry count == capacity) it raises `BC_ASSERT: 0` at Fog AssetCache.h:187 ("The size of the asset cache
has been exceeded!"), grows the capacity by half and goes on (`0x68a4ea`..`0x68a5d5`, the growth in the FindOrLoadAsset at
`0x68a380`). Seen in game (bugs.md #360): entering an act loads the variant tables of the monsters the act's levels can spawn
and drops part of the previous act's (Act 1 113 tables, Act 2 102, Act 3 122, Act 5 128, Act 1 again 137 with the earlier
build of 93 stand-in colour tables).

The caches live in the render asset manager, a singleton whose pointer is at RVA 0x34f6480 (read by `0xe21140`). Offsets of the
cache objects in it (found at run time by their layout, CANDIDATE_OFFSETS): +0x11618 VariantTransformTable (capacity 128, keys
`*_variant.json`), +0x26648 ModelAsset (2750), +0x26ac8 UnitAnimationStateMachine (384), +0x26be0 TileMaskRuleSet (16),
+0x26cf8 PopcornAsset (1024), three of capacity 512. Cache layout: +0x50 bucket count, +0x58 bucket array (node pointers),
+0x60 entry count, +0x70 capacity; a node is [next, key data, key length, ...]. Read-only (ReadProcessMemory), only on the
game of this slot (game_ctl.game_pids).

  py -3 tools/cache_probe.py counts [--pid N]          # entry count / capacity of every cache found
  py -3 tools/cache_probe.py paths <kind> [--pid N]    # the keys (file paths) of one cache, e.g. VariantTransformTable
  py -3 tools/cache_probe.py asserts <d2rloader.log>   # the AssetCache asserts of a loader log (capacity, path)
  py -3 tools/cache_probe.py poll <out.jsonl> [--every S] [--secs N] [--pid N]   # read the counts every S seconds
  py -3 tools/cache_probe.py peaks <poll.jsonl>        # the peak of every cache in a poll file (and when it was reached)

game_checks.py polls on its own with MXL_CACHE_POLL=<seconds> (cache_poll.jsonl in the run folder, peaks in the report).
"""
import argparse
import ctypes
import json
import re
import struct
import sys
from ctypes import wintypes

SINGLETON_RVA = 0x34f6480
# Cache objects in the asset manager: offsets from the `lea rcx, [rax + off]` that follow the singleton getter, kept when the
# object there has a cache's layout (plausible); DefaultCapacity per type from the 93847 dump's FindOrLoadAsset names.
VARIANT_OFFSET = 0x11618
CANDIDATE_OFFSETS = (0x11618, 0x26648, 0x26780, 0x26898, 0x269b0, 0x26ac8, 0x26be0, 0x26cf8)
KNOWN_CAPACITIES = {"VariantTransformTable": 128, "PhysicsClothAsset": 128, "UnitAnimationStateMachine": 384,
                    "SkeletonAsset": 512, "AnimationAsset": 512, "AnimationTimelineAsset": 512, "PhysicsTreeMeshAsset": 512,
                    "PopcornAsset": 1024, "ModelAsset": 2750, "TileMaskRuleSet": 16}
OFF_BUCKETS_N, OFF_BUCKETS, OFF_COUNT, OFF_CAPACITY = 0x50, 0x58, 0x60, 0x70
# Kind per offset where it is known (keys read live); the three caches of DefaultCapacity 512 are not told apart yet.
OFFSET_KINDS = {0x11618: "VariantTransformTable", 0x26648: "ModelAsset", 0x26ac8: "UnitAnimationStateMachine",
                0x26be0: "TileMaskRuleSet", 0x26cf8: "PopcornAsset"}


def cache_header(raw):
    """(bucket count, bucket array, entry count, capacity) from the bytes of a cache object (at least 0x78)."""
    return (struct.unpack_from("<Q", raw, OFF_BUCKETS_N)[0], struct.unpack_from("<Q", raw, OFF_BUCKETS)[0],
            struct.unpack_from("<Q", raw, OFF_COUNT)[0], struct.unpack_from("<Q", raw, OFF_CAPACITY)[0])


def plausible(header):
    """A cache object: a power-of-two bucket count, a bucket array, count <= capacity, capacity a grown default."""
    nb, arr, count, cap = header
    if not (nb and nb & (nb - 1) == 0 and nb <= 1 << 20 and arr and 0 < cap < 1 << 20 and count <= cap):
        return False
    return any(grown(d, cap) for d in set(KNOWN_CAPACITIES.values()))


def grown(default, cap, steps=12):
    """True when `cap` is `default` grown by half 0..steps times (the capacity after each overflow, `shr rbx,1; add`)."""
    c = default
    for _ in range(steps + 1):
        if c == cap:
            return True
        c += c >> 1
    return False


def overflows(default, cap):
    """How many times a cache of DefaultCapacity `default` has overflowed to reach capacity `cap` (None: not a growth of it)."""
    c, n = default, 0
    while c < cap:
        c += c >> 1
        n += 1
    return n if c == cap else None


ASSERT_RE = re.compile(r"Location: Fog\\include\\Fog\\AssetCache\.h:187(.*?)Stack", re.S)


def asserts_in_log(text):
    """[{default, capacity, path}] of every AssetCache.h:187 block in a d2rloader.log text, in order."""
    out = []
    for m in ASSERT_RE.finditer(text):
        body = m.group(1)
        d = re.search(r"DefaultCapacity = (\d+)", body)
        c = re.search(r"m_capacity = (\d+)", body)
        p = re.search(r'path = "([^"]*)"', body)
        out.append({"default": int(d.group(1)) if d else None, "capacity": int(c.group(1)) if c else None,
                    "path": p.group(1) if p else None})
    return out


def kind_of_path(path):
    """The cache kind a path belongs to, by its file name (the assert names only DefaultCapacity and the path)."""
    p = (path or "").lower()
    for suffix, kind in (("_variant.json", "VariantTransformTable"), (".skeleton", "SkeletonAsset"), (".model", "ModelAsset"),
                         ("_state_machine.json", "UnitAnimationStateMachine"), (".animation", "AnimationAsset"),
                         (".popcorn", "PopcornAsset")):
        if p.endswith(suffix):
            return kind
    if "/mxl/v_" in p:
        return "VariantTransformTable"
    return None


def default_of(cap):
    """The DefaultCapacity a capacity grew from (the smallest known default it is a growth of), or None."""
    return next((d for d in sorted(set(KNOWN_CAPACITIES.values())) if cap and grown(d, cap)), None)


def cache_name(off, cap=None):
    """A readable name of the cache at `off` ("VariantTransformTable", "cache512@0x26780")."""
    off = int(off, 16) if isinstance(off, str) else off
    if off in OFFSET_KINDS:
        return OFFSET_KINDS[off]
    return "cache%s@%#x" % (default_of(cap) or "?", off)


def peaks(records):
    """{name: {"peak", "capacity", "default", "t", "overflows"}} over poll records ({"t", "caches": {off: [count, cap]}}):
    the highest entry count, when it was first read, the largest capacity and how often it grew past its DefaultCapacity."""
    out = {}
    for rec in records:
        for off, (n, cap) in (rec.get("caches") or {}).items():
            name = cache_name(off, cap)
            cur = out.setdefault(name, {"peak": -1, "capacity": cap, "default": default_of(cap) or cap, "t": None})
            cur["capacity"] = max(cur["capacity"], cap)
            if n > cur["peak"]:
                cur["peak"], cur["t"] = n, rec.get("t")
    for v in out.values():
        v["overflows"] = overflows(v["default"], v["capacity"]) or 0
    return out


def peaks_text(pk):
    """One line per cache: name peak/default (overflows) at time."""
    return "; ".join("%s %d/%d%s at %s" % (k, v["peak"], v["default"], " (%d overflow%s, capacity %d)" % (
        v["overflows"], "s" if v["overflows"] > 1 else "", v["capacity"]) if v["overflows"] else "", v["t"])
        for k, v in sorted(pk.items(), key=lambda kv: -kv[1]["peak"] / max(kv[1]["default"], 1)))


# ---------------------------------------------------------------- live process (Windows only)


class Proc:
    def __init__(self, pid):
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        self.k32.OpenProcess.restype = wintypes.HANDLE
        self.k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                               ctypes.POINTER(ctypes.c_size_t)]
        psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
        self.h = self.k32.OpenProcess(0x0400 | 0x0010, False, pid)  # QUERY_INFORMATION | VM_READ
        if not self.h:
            raise OSError("OpenProcess(%d) failed (%d)" % (pid, ctypes.get_last_error()))
        mods = (ctypes.c_void_p * 1)()
        need = wintypes.DWORD()
        if not psapi.EnumProcessModulesEx(self.h, mods, ctypes.sizeof(mods), ctypes.byref(need), 0x03):
            raise OSError("EnumProcessModulesEx failed (%d)" % ctypes.get_last_error())
        self.base = mods[0]

    def read(self, addr, size):
        buf = ctypes.create_string_buffer(size)
        n = ctypes.c_size_t()
        if not self.k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)) or n.value != size:
            raise OSError("read %#x+%#x failed" % (addr, size))
        return buf.raw

    def q(self, addr):
        return struct.unpack("<Q", self.read(addr, 8))[0]

    def close(self):
        self.k32.CloseHandle(self.h)


def manager(proc):
    return proc.q(proc.base + SINGLETON_RVA)


def live_caches(proc, offsets=CANDIDATE_OFFSETS):
    """{offset: (count, capacity)} of the candidate offsets that look like a cache object."""
    mgr = manager(proc)
    out = {}
    if not mgr:
        return out
    for off in offsets:
        try:
            h = cache_header(proc.read(mgr + off, 0x78))
        except OSError:
            continue
        if plausible(h):
            out[off] = (h[2], h[3])
    return out


def live_keys(proc, off, limit=20000):
    """The key strings (asset paths) of the cache at `off`, every node once."""
    mgr = manager(proc)
    nb, arr, _count, _cap = cache_header(proc.read(mgr + off, 0x78))
    slots = proc.read(arr, nb * 8)
    seen, keys = set(), []
    for i in range(nb):
        node = struct.unpack_from("<Q", slots, i * 8)[0]
        while node and node not in seen and len(seen) < limit:
            seen.add(node)
            nxt, data, ln = struct.unpack("<QQQ", proc.read(node, 24))
            if data and 0 < ln < 1024:
                keys.append(proc.read(data, ln).decode("utf-8", "replace"))
            node = nxt
    return sorted(set(keys))


def snapshot(pid):
    """{"caches": {hex offset: [count, capacity]}, "variants": [paths]} of a running game, or {"error": ...}."""
    try:
        p = Proc(pid)
    except OSError as e:
        return {"error": str(e)}
    try:
        caches = live_caches(p)
        snap = {"caches": {"%#x" % o: list(v) for o, v in caches.items()}}
        if VARIANT_OFFSET in caches:
            snap["variants"] = live_keys(p, VARIANT_OFFSET)
        return snap
    except OSError as e:
        return {"error": str(e)}
    finally:
        p.close()


def poll(pid_fn, path, every=3.0, stop=None, secs=None, tag_fn=None):
    """Append a record to `path` (jsonl) every `every` seconds while a game runs: time, counts of every cache and the variant
    table keys when they changed ("new" / "gone"). `pid_fn()` gives the game's pid (None: wait), `stop()` ends the loop,
    `tag_fn()` (optional) a label of what the game is doing (the step of a check). Read-only. Returns the records' peaks."""
    import datetime
    import time
    recs, prev, t0 = [], None, time.time()
    with open(path, "a", encoding="utf-8") as out:
        while not (stop and stop()) and not (secs and time.time() - t0 > secs):
            pid = pid_fn()
            if pid:
                snap = snapshot(pid)
                if "caches" in snap:
                    keys = set(snap.get("variants") or [])
                    rec = {"t": datetime.datetime.now().strftime("%H:%M:%S"), "caches": snap["caches"],
                           "variants_mxl": sum(1 for k in keys if "/mxl/" in k)}
                    if tag_fn:
                        try:
                            rec["tag"] = tag_fn()
                        except Exception:  # noqa: BLE001 - the label is a nice-to-have
                            pass
                    if prev is None or keys != prev:
                        rec["new"] = sorted(keys - (prev or set()))
                        rec["gone"] = sorted((prev or set()) - keys)
                        prev = keys
                    recs.append(rec)
                    out.write(json.dumps(rec) + "\n")
                    out.flush()
            time.sleep(every)
    return peaks(recs)


def read_poll(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("counts", "paths", "asserts", "poll", "peaks"))
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--every", type=float, default=3.0)
    ap.add_argument("--secs", type=float)
    a = ap.parse_args(argv)
    if a.cmd == "asserts":
        print(json.dumps(asserts_in_log(open(a.arg, encoding="utf-8", errors="replace").read()), indent=1))
        return 0
    if a.cmd == "peaks":
        print(peaks_text(peaks(read_poll(a.arg))))
        return 0
    if a.cmd == "poll":
        import game_ctl
        pid_fn = (lambda: a.pid) if a.pid else (lambda: (game_ctl.game_pids() or [None])[0])
        print(peaks_text(poll(pid_fn, a.arg, a.every, secs=a.secs)))
        return 0
    if not a.pid:
        import game_ctl
        pids = game_ctl.game_pids()
        if not pids:
            print("no game of this slot is running (MXL_SLOT)")
            return 1
        a.pid = pids[0]
    p = Proc(a.pid)
    try:
        if a.cmd == "counts":
            for off, (n, cap) in sorted(live_caches(p).items()):
                print("%#x count %d capacity %d" % (off, n, cap))
        else:
            off = VARIANT_OFFSET if (a.arg or "VariantTransformTable") == "VariantTransformTable" else int(a.arg, 16)
            for k in live_keys(p, off):
                print(k)
    finally:
        p.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
