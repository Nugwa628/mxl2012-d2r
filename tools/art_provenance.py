"""Where does Median's art come from? Match Median's classic DCC animations against D2R's own (vanilla) ones by image.

effects_hd.py and hd_monsters.py used to give Median's own art the "closest" D2R HD effect / model by description (name
words, mean colour, size, role). Much of Median's art is vanilla art renamed, recoloured, rescaled, retimed or mashed up,
and then D2R's exact HD effect or model, plus a tint or a scale, is the right answer. This tool finds that out from the
pictures:

  exact      every frame is a vanilla frame (content hash of the tight pixel crop), same palette indices
  recolour   same silhouette (alpha mask), the palette indices of one image map onto the other consistently;
             the hue / saturation / brightness shift of the mapping is reported
  rescale    same silhouette at another size (uniform scale factor; nearest-neighbour resampling at the smaller size)
  retime     flag on top of the above: the matched frames come in another number or order (animation speed, loops)
  mashup     the frames come from several vanilla animations, none of them from 75% of the frames; the dominant source
             is reported first
  new        fewer than half of the frames match anything

Libraries: effects (Median missiles + overlays against vanilla missiles + overlays) and monsters (Median monster
parts against vanilla monster parts; the part and variant of every file name <code><part><variant><mode><weapon> are
kept, so a weapon or a shield matches on its own, and the per code/part/variant roll-up is what hd_monsters.py reads).

Method (all offline, features cached in work/art_provenance/ so a second run takes seconds):
  1. every DCC is decoded (tools/dcc.py) in direction 0 and the middle direction: per frame the hash of the tight crop
     (exact) and of its mask (recolour), the crop size, and for direction 0 a 16 x 16 area-resampled mask descriptor
  2. candidate vanilla files per Median file: frame hash hits and nearest descriptors (matrix product) of up to 8 sample
     frames vote; the top 10 files (and the vanilla file of the same name) are verified
  3. verification, frame by frame: the best candidate frames by descriptor are compared pixel by pixel (mask IoU, equal
     indices, palette index mapping consistency, brightness correlation) and classified; the animation takes the
     dominant source (frames of other sources only where they are clearly better = mashup)

Writes work/mod/art_provenance.json and .md (Median file -> vanilla sources, kind, confidence, shift; the per category
match rates); work/art_provenance/ holds the caches.
Usage: python tools/art_provenance.py [--groups effects,monsters] [--jobs N] [--rebuild] [--selftest] [--only SUBSTR]
"""
import argparse
import hashlib
import json
import math
import os
import pickle
import re
import struct
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# One BLAS thread per worker: with the default (one per core) in every pool worker a fresh cache ran the PC out of memory
# ("OpenBLAS error: Memory allocation still failed", BrokenProcessPool) while games ran next to the build.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dcc  # noqa: E402

import fxpaths  # noqa: E402

ROOT = fxpaths.ROOT
MXL = fxpaths.MXL                              # Median XL 2012 (extract-mpq) data/global
VAN = fxpaths.D2R_DATA / "global"              # D2R's legacy (classic) DCCs
PALETTE = fxpaths.PALETTE
CACHE_DIR = fxpaths.WORK / "art_provenance"
OUT_DEFAULT = fxpaths.MOD

GROUPS = {"effects": ("missiles", "overlays"), "monsters": ("monsters",)}
DESC = 16            # descriptor resolution
TINY = 24            # frames with fewer opaque pixels make no claims
SAMPLES = 8          # frames per Median file that vote for candidates
TOPK = 8             # nearest vanilla frames per sample
CANDS = 10           # vanilla files verified per Median file
MAX_HASH_FILES = 30  # a frame hash shared by more files than this is generic
MONSTER_NAME = re.compile(r"^(?P<code>..)(?P<part>hd|tr|lg|ra|la|rh|lh|sh|s[1-8])(?P<var>...)(?P<mode>..)(?P<weapon>...)$")

TRACE = None  # debugging: list that compare() appends its metrics to
ALGO = 3  # bump when compare() / verify() change: verification caches are keyed by it
KIND_RANK = {"exact": 0, "recolour": 1, "rescale": 2, "rescale+recolour": 3}


# ---------------------------------------------------------------------------------------------- palette
_pal = None


def palette() -> np.ndarray:
    global _pal
    if _pal is None:
        d = PALETTE.read_bytes()
        _pal = np.array([(d[i * 3 + 2], d[i * 3 + 1], d[i * 3]) for i in range(256)], np.float64)  # stored BGR
    return _pal


def pal_hsv() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rgb = palette() / 255.0
    mx, mn = rgb.max(1), rgb.min(1)
    d = mx - mn
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    dd = np.maximum(d, 1e-9)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    h = np.where(d == 0, 0.0, h) % 1.0
    s = np.where(mx > 0, d / np.maximum(mx, 1e-9), 0.0)
    return h, s, mx


def lum() -> np.ndarray:
    p = palette()
    return (0.30 * p[:, 0] + 0.59 * p[:, 1] + 0.11 * p[:, 2]) / 255.0


# ---------------------------------------------------------------------------------------------- frames
def tight(frame) -> tuple[int, int, np.ndarray] | None:
    """(anchor x, anchor y, crop) of the opaque part of a decoded frame; None when empty."""
    x, y, w, h, pix = frame
    a = np.frombuffer(pix, np.uint8).reshape(h, w)
    nz = a > 0
    if not nz.any():
        return None
    rows, cols = np.nonzero(nz.any(1))[0], np.nonzero(nz.any(0))[0]
    y0, y1, x0, x1 = rows[0], rows[-1], cols[0], cols[-1]
    return x + int(x0), y + int(y0), a[y0:y1 + 1, x0:x1 + 1]


def h64(*parts: bytes) -> int:
    return int.from_bytes(hashlib.blake2b(b"".join(parts), digest_size=8).digest(), "little")


def descriptor(crop: np.ndarray) -> np.ndarray:
    """Silhouette resampled to DESC x DESC (area average) plus the aspect ratio: float32 vector of DESC*DESC+1."""
    h, w = crop.shape
    m = Image.fromarray(((crop > 0) * 255).astype(np.uint8)).resize((DESC, DESC), Image.Resampling.BOX)
    v = np.asarray(m, np.float32).reshape(-1) / 255.0
    return np.append(v, np.float32(6.0 * math.log2(w / h)))


def decode_dir(data: bytes, d: int):
    dirs = data[2]
    fpd = struct.unpack_from("<I", data, 3)[0]
    offs = list(struct.unpack_from(f"<{dirs}I", data, 15)) + [len(data)]
    return dcc.decode_direction(data[offs[d]:offs[d + 1]], fpd)[4]


def crops_of(frames) -> list[tuple[int, int, np.ndarray] | None]:
    return [tight(f) for f in frames]


def extract(path: str) -> dict:
    """Per-file features (worker)."""
    data = Path(path).read_bytes()
    out = {"size": len(data), "err": None}
    try:
        dirs = data[2]
        out["dirs"], out["fpd"] = dirs, struct.unpack_from("<I", data, 3)[0]
        out["sel"] = {}
        for d in sorted({0, dirs // 2}):
            frames = decode_dir(data, d)
            cr = crops_of(frames)
            n = len(cr)
            ch, mh = np.zeros(n, np.uint64), np.zeros(n, np.uint64)
            box, nnz = np.zeros((n, 4), np.int16), np.zeros(n, np.int32)
            for i, c in enumerate(cr):
                if c is None:
                    continue
                tx, ty, a = c
                hh = struct.pack("<HH", *a.shape)
                ch[i] = h64(hh, a.tobytes())
                mh[i] = h64(hh, np.packbits(a > 0).tobytes())
                box[i] = (tx, ty, a.shape[1], a.shape[0])
                nnz[i] = int((a > 0).sum())
            out["sel"][d] = {"ch": ch, "mh": mh, "box": box, "nnz": nnz}
            if d == 0:
                out["desc"] = np.array([descriptor(c[2]) if c is not None else np.zeros(DESC * DESC + 1, np.float32)
                                        for c in cr], np.float16).reshape(n, -1)
                hist = np.zeros(256, np.int64)
                for c in cr:
                    if c is not None:
                        hist += np.bincount(c[2].ravel(), minlength=256)
                hist[0] = 0
                out["hist"] = hist
    except Exception as e:  # undecodable art
        out["err"] = f"{type(e).__name__}: {e}"
    return out


# ---------------------------------------------------------------------------------------------- comparison
def nn_resize(a: np.ndarray, h: int, w: int) -> np.ndarray:
    if a.shape == (h, w):
        return a
    ys = np.minimum(((np.arange(h) + 0.5) * a.shape[0] / h).astype(np.int64), a.shape[0] - 1)
    xs = np.minimum(((np.arange(w) + 0.5) * a.shape[1] / w).astype(np.int64), a.shape[1] - 1)
    return a[ys][:, xs]


def _detail_corr(a: np.ndarray, b: np.ndarray, sel: np.ndarray) -> float:
    def hp(x):
        p = np.pad(x, 1, mode="edge")
        blur = sum(p[i:i + x.shape[0], j:j + x.shape[1]] for i in range(3) for j in range(3)) / 9.0
        return x - blur
    ra, rb = hp(a)[sel], hp(b)[sel]
    if ra.std() < 0.01 or rb.std() < 0.01:
        return 1.0 if ra.std() < 0.01 and rb.std() < 0.01 else 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def compare(mc: np.ndarray, vc: np.ndarray) -> dict | None:
    """Compare Median's crop to a vanilla crop. {kind, q, scale, iou, eq, cons, corr, co} or None when unrelated.
    co is the 256 x 256 palette index co-occurrence (median index, vanilla index) over the overlapping pixels."""
    hm, wm = mc.shape
    hv, wv = vc.shape
    if (hm, wm) == (hv, wv) and np.array_equal(mc, vc):
        return {"kind": "exact", "q": 1.0, "scale": 1.0, "iou": 1.0, "eq": 1.0, "cons": 1.0, "corr": 1.0, "co": None}
    sx, sy = wm / wv, hm / hv
    if abs(math.log(sx / sy)) > max(0.12, 1.5 / min(hm, wm, hv, wv)):
        uniform = False
    else:
        uniform = True
    th, tw = min(hm, hv), min(wm, wv)
    m = nn_resize(mc, th, tw)
    v = nn_resize(vc, th, tw)
    mm, vm = m > 0, v > 0
    union = int((mm | vm).sum())
    both = mm & vm
    nb = int(both.sum())
    if not union or nb < TINY // 2:
        return None
    iou = nb / union
    if iou < 0.78:
        if TRACE is not None:
            TRACE.append((iou, 0, 0, 0, 0, math.sqrt(sx * sy), None))
        return None
    mi, vi = m[both].astype(np.int64), v[both].astype(np.int64)
    eq = float((mi == vi).mean())
    co = np.bincount(mi * 256 + vi, minlength=65536).reshape(256, 256)
    cons = float(co.max(axis=1).sum() / nb)
    L = lum()
    lm, lv = L[mi], L[vi]
    corr = float(np.corrcoef(lm, lv)[0, 1]) if lm.std() > 1e-6 and lv.std() > 1e-6 else (1.0 if eq > 0.98 else 0.0)
    # fine structure: brightness minus its 3 x 3 mean, correlated over the shared pixels (a smooth blob of the same size
    # matches any other smooth blob, a recoloured or rescaled sprite keeps its texture)
    LI = np.zeros(m.shape, np.float64)
    LJ = np.zeros(m.shape, np.float64)
    LI[mm], LJ[vm] = L[m[mm]], L[v[vm]]
    dcorr = _detail_corr(LI, LJ, both)
    scale = math.sqrt(sx * sy)
    same = abs(scale - 1) < 0.03 and uniform
    kind = None
    if same:
        if eq >= 0.995 and iou >= 0.995:
            kind = "exact"
        elif iou >= 0.97 and (cons >= 0.92 or corr >= 0.85):
            kind = "recolour"
    else:
        if not 0.3 <= scale <= 3.5:
            kind = None
        elif iou >= 0.88 and eq >= 0.8:
            kind = "rescale"
        elif iou >= 0.88 and cons >= 0.85 and corr >= 0.85:
            kind = "rescale+recolour"
        elif iou >= 0.88 and corr >= 0.93:
            kind = "rescale"
    if kind is not None and kind != "exact" and dcorr < 0.55:
        kind = None
    if TRACE is not None:
        TRACE.append((iou, eq, cons, corr, dcorr, scale, kind))
    if kind is None:
        return None
    q = min(1.0, 0.5 * iou + 0.3 * max(eq, cons) + 0.2 * max(corr, 0.0))
    if not uniform:
        q *= 0.9
    return {"kind": kind, "q": float(q), "scale": float(scale), "iou": float(iou), "eq": eq, "cons": cons,
            "corr": corr, "dcorr": dcorr, "co": co if kind in ("recolour", "rescale+recolour") else None}


def shift_of(co: np.ndarray) -> dict:
    """Colour shift of a palette index co-occurrence (median, vanilla): Median relative to vanilla."""
    h, s, v = pal_hsv()
    cnt = co.sum(axis=1).astype(np.float64)
    best = co.argmax(axis=1)
    w = cnt
    tot = w.sum()
    if tot <= 0:
        return {"hue": 0.0, "sat": 0.0, "val": 0.0}
    hw = w * np.minimum(s, s[best]) * np.minimum(v, v[best])
    dh = h - h[best]
    ang = np.arctan2((hw * np.sin(2 * np.pi * dh)).sum(), (hw * np.cos(2 * np.pi * dh)).sum()) / (2 * np.pi) if hw.sum() > 1e-9 else 0.0
    sat = float((w * (s - s[best])).sum() / tot)
    val = math.log2(max((w * v).sum(), 1e-6) / max((w * v[best]).sum(), 1e-6))
    pal = palette()
    return {"hue": round(float(ang), 3), "sat": round(sat, 3), "val": round(float(val), 3),
            "rgb_m": [round(float(c)) for c in (w[:, None] * pal).sum(0) / tot],
            "rgb_v": [round(float(c)) for c in (w[:, None] * pal[best]).sum(0) / tot]}


# ---------------------------------------------------------------------------------------------- verification (worker)
_lru: dict = {}


def load_crops(path: str):
    """(crops of direction 0, descriptors) of a DCC, cached per worker."""
    if path in _lru:
        return _lru[path]
    if len(_lru) > 160:
        _lru.pop(next(iter(_lru)))
    data = Path(path).read_bytes()
    cr = crops_of(decode_dir(data, 0))
    desc = np.array([descriptor(c[2]) if c is not None else np.full(DESC * DESC + 1, 99.0, np.float32) for c in cr],
                    np.float32)
    _lru[path] = (cr, desc)
    return _lru[path]


def verify(task: tuple[str, list[str]]) -> dict:
    """Frame-by-frame verification of one Median file against its candidate vanilla files."""
    mpath, cpaths = task
    out = {"frames": [], "err": None}
    try:
        mcr, mdesc = load_crops(mpath)
        cands = []
        for p in cpaths:
            try:
                cands.append((p, *load_crops(p)))
            except Exception:
                continue
        allv = []  # (cand index, frame index)
        for ci, (_p, cr, _d) in enumerate(cands):
            allv += [(ci, j) for j, c in enumerate(cr) if c is not None and (c[2] > 0).sum() >= TINY // 2]
        if allv:
            vd = np.array([cands[ci][2][j] for ci, j in allv], np.float32)
        out["n"] = len(mcr)
        co_sum = [np.zeros((256, 256), np.int64) for _ in cands]
        for i, mc in enumerate(mcr):
            fr = {"src": None}
            if mc is None or not allv or (mc[2] > 0).sum() < TINY:
                out["frames"].append(fr)
                continue
            d2 = ((vd - mdesc[i][None, :]) ** 2).sum(1)
            order = np.argsort(d2)[:6]
            best = None
            for o in order:
                if d2[o] > 40.0:
                    break
                ci, j = allv[o]
                r = compare(mc[2], cands[ci][1][j][2])
                if r is not None and (best is None or r["q"] > best[2]["q"]):
                    best = (ci, j, r)
                if r is not None and r["kind"] == "exact":
                    break
            # frames of every candidate at the same position (retimes keep their order): cheap second chance
            if best is None or best[2]["q"] < 0.97:
                for ci, (_p, cr, _d) in enumerate(cands):
                    if not cr:
                        continue
                    j = min(len(cr) - 1, int(round(i * len(cr) / max(1, len(mcr)))))
                    if cr[j] is None:
                        continue
                    r = compare(mc[2], cr[j][2])
                    if r is not None and (best is None or r["q"] > best[2]["q"] + 0.02):
                        best = (ci, j, r)
            if best is not None:
                ci, j, r = best
                fr = {"src": ci, "j": j, "kind": r["kind"], "q": round(r["q"], 3), "scale": round(r["scale"], 3),
                      "nnz": int((mc[2] > 0).sum())}
                if r["co"] is not None:
                    co_sum[ci] += r["co"]
            out["frames"].append(fr)
        out["sources"] = [{"path": cands[ci][0], "n": len(cands[ci][1]),
                           "shift": shift_of(co_sum[ci]) if co_sum[ci].sum() else None} for ci in range(len(cands))]
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {e}"
    return out


def mid_dir_equal(mpath: str, vpath: str) -> bool:
    """Do the middle directions of two DCCs also match frame for frame (content hash)? (exact files)"""
    try:
        a, b = Path(mpath).read_bytes(), Path(vpath).read_bytes()
        if a[2] != b[2]:
            return False
        d = a[2] // 2
        fa, fb = crops_of(decode_dir(a, d)), crops_of(decode_dir(b, d))
        return len(fa) == len(fb) and all(
            (x is None and y is None) or (x is not None and y is not None and x[2].shape == y[2].shape
                                           and np.array_equal(x[2], y[2])) for x, y in zip(fa, fb))
    except Exception:
        return False


# ---------------------------------------------------------------------------------------------- inventory
def inventory(side: str, kinds: tuple[str, ...]) -> dict[str, Path]:
    base = MXL if side == "mxl" else VAN
    out = {}
    for k in kinds:
        for p in (base / k).rglob("*.dcc"):
            out[p.relative_to(base).with_suffix("").as_posix().lower()] = p
    return out


def load_cache(name: str) -> dict:
    p = CACHE_DIR / name
    if p.exists():
        try:
            return pickle.loads(p.read_bytes())
        except Exception:
            pass
    return {}


def save_cache(name: str, obj) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / name).write_bytes(pickle.dumps(obj, protocol=4))


def sig(p: Path) -> tuple[int, int]:
    s = p.stat()
    return s.st_size, s.st_mtime_ns


def features(files: dict[str, Path], side: str, pool, rebuild: bool) -> dict[str, dict]:
    cache = {} if rebuild else load_cache(f"features_{side}.pkl")
    todo = [k for k, p in files.items() if k not in cache or cache[k]["sig"] != sig(p)]
    if todo:
        t = time.time()
        print(f"  decoding {len(todo)} {side} DCCs ...", flush=True)
        res = pool.map(extract, [str(files[k]) for k in todo], chunksize=4)
        for k, r in zip(todo, res):
            r["sig"] = sig(files[k])
            cache[k] = r
        print(f"  decoded in {time.time() - t:.0f}s", flush=True)
        save_cache(f"features_{side}.pkl", cache)
    return {k: cache[k] for k in files}


# ---------------------------------------------------------------------------------------------- candidates
def candidates(mf: dict[str, dict], vf: dict[str, dict], vfiles: dict[str, Path]) -> dict[str, list[str]]:
    """Per Median file the vanilla files worth verifying (hash hits + nearest silhouettes vote)."""
    vkeys = [k for k, f in vf.items() if not f["err"]]
    vid = {k: i for i, k in enumerate(vkeys)}
    rows, owner = [], []
    hashes: dict[int, set] = defaultdict(set)
    maskh: dict[int, set] = defaultdict(set)
    for k in vkeys:
        f = vf[k]
        s0 = f["sel"][0]
        for j in range(len(s0["nnz"])):
            if s0["nnz"][j] >= TINY:
                rows.append(f["desc"][j])
                owner.append(vid[k])
                hashes[int(s0["ch"][j])].add(vid[k])
                maskh[int(s0["mh"][j])].add(vid[k])
    V = np.array(rows, np.float32)
    vv = (V * V).sum(1)
    owner = np.array(owner)
    print(f"  {len(vkeys)} vanilla files, {len(V)} frames", flush=True)
    names = [k for k in mf if not mf[k]["err"]]
    samples, sown = [], []
    votes = {k: Counter() for k in names}
    for k in names:
        f = mf[k]
        s0 = f["sel"][0]
        good = [j for j in range(len(s0["nnz"])) if s0["nnz"][j] >= TINY]
        if not good:
            continue
        for j in good:
            for h, tab, w in ((int(s0["ch"][j]), hashes, 3.0), (int(s0["mh"][j]), maskh, 2.0)):
                fs = tab.get(h)
                if fs and len(fs) <= MAX_HASH_FILES:
                    for v in fs:
                        votes[k][v] += w / len(fs) ** 0.5
        pick = good if len(good) <= SAMPLES else [good[int(i * (len(good) - 1) / (SAMPLES - 1))] for i in range(SAMPLES)]
        for j in pick:
            samples.append(f["desc"][j])
            sown.append(k)
    S = np.array(samples, np.float32)
    ss = (S * S).sum(1)
    print(f"  {len(names)} Median files, {len(S)} sample frames; nearest-silhouette search ...", flush=True)
    step = 512
    for a in range(0, len(S), step):
        d2 = ss[a:a + step, None] + vv[None, :] - 2.0 * (S[a:a + step] @ V.T)
        kk = min(TOPK, d2.shape[1] - 1)
        idx = np.argpartition(d2, kk, axis=1)[:, :kk]
        for r in range(idx.shape[0]):
            k = sown[a + r]
            dr = d2[r, idx[r]]
            for c, dist in zip(idx[r], dr):
                if dist < 8.0:
                    votes[k][int(owner[c])] += 1.0 / (1.0 + dist)
    out = {}
    for k in names:
        top = [vkeys[v] for v, _w in votes[k].most_common(CANDS)]
        if k in vf and k not in top and not vf[k]["err"]:
            top.append(k)
        out[k] = top
    return out


# ---------------------------------------------------------------------------------------------- aggregation
def confidence_of(cov: float, qm: float, nnz_med: float) -> str:
    if cov >= 0.9 and qm >= 0.9 and nnz_med >= 60:
        return "high"
    if cov >= 0.7 and qm >= 0.8:
        return "medium"
    return "low"


def aggregate(mk: str, ver: dict, cpaths: list[str], mfeat: dict, vkey_of: dict[str, str]) -> dict:
    """One Median file's verified frames -> category, sources, flags."""
    frames = ver["frames"]
    n = len(frames)
    matched = [(i, f) for i, f in enumerate(frames) if f["src"] is not None]
    res = {"frames": n, "dirs": mfeat.get("dirs"), "category": "new", "retime": False, "coverage": 0.0,
           "confidence": "low", "sources": []}
    if n == 0 or not matched:
        return res
    cnt = Counter(f["src"] for _i, f in matched)
    dom = max(cnt, key=lambda s: (cnt[s], -s))
    # frames follow the dominant source unless another one is clearly better
    chosen = {}
    for i, f in matched:
        chosen[i] = f
    # re-score: the verification already picked per frame the best candidate; prefer the dominant one when it matched
    cov = len(matched) / n
    if cov < 0.5:
        res["coverage"] = round(cov, 3)
        return res
    shares = {s: c / len(matched) for s, c in cnt.items()}
    mash = shares[dom] < 0.75 and sum(1 for s in shares.values() if s >= 0.2) >= 2
    order = sorted(cnt, key=lambda s: -cnt[s])
    srcs = []
    for s in order:
        fs = [f for _i, f in matched if f["src"] == s]
        kinds = Counter(f["kind"] for f in fs)
        scale = float(np.median([f["scale"] for f in fs]))
        kind = max(kinds, key=lambda k: KIND_RANK[k]) if kinds else "exact"
        # a minority of odd frames does not decide the kind: majority by rank
        tot = len(fs)
        rec = sum(c for k, c in kinds.items() if "recolour" in k)
        resc = sum(c for k, c in kinds.items() if "rescale" in k)
        if resc >= 0.3 * tot:
            kind = "rescale+recolour" if rec >= 0.3 * tot else "rescale"
        elif rec >= 0.3 * tot:
            kind = "recolour"
        else:
            kind = "exact"
        vp = cpaths[s]
        sh = ver["sources"][s]["shift"] if s < len(ver["sources"]) else None
        srcs.append({"file": vkey_of[vp], "frames": len(fs), "share": round(cnt[s] / len(matched), 3), "kind": kind,
                     "scale": round(scale, 3) if "rescale" in kind else 1.0,
                     "q": round(float(np.mean([f["q"] for f in fs])), 3),
                     "shift": sh if "recolour" in kind else None, "vframes": ver["sources"][s]["n"]})
    d = srcs[0]
    qm = float(np.mean([f["q"] for _i, f in matched]))
    nnz_med = float(np.median([f["nnz"] for _i, f in matched]))
    # retime: the dominant source's frame sequence is not the identity
    js = [f["j"] for i, f in matched if f["src"] == dom]
    idx = [i for i, f in matched if f["src"] == dom]
    retime = d["vframes"] != n or any(abs(j - i) > 0 for i, j in zip(idx, js))
    cat = "mashup" if mash else d["kind"] if d["kind"] in ("exact", "recolour") else "rescale"
    if cov < 0.75 and not mash:
        pass
    res.update(category=cat, retime=bool(retime), coverage=round(cov, 3), confidence=confidence_of(cov, qm, nnz_med),
               sources=srcs[:4], q=round(qm, 3))
    return res


def parse_monster(key: str):
    m = MONSTER_NAME.match(key.rsplit("/", 1)[-1])
    return (m["code"], m["part"], m["var"], m["mode"], m["weapon"]) if m else None


def rollup_monsters(files: dict[str, dict]) -> dict:
    """Median code -> part -> variant -> best source (code, part, variant) pooled over the modes."""
    groups: dict[tuple, list] = defaultdict(list)
    for k, r in files.items():
        p = parse_monster(k)
        if p is None or not r["sources"]:
            continue
        groups[(p[0], p[1], p[2])].append((k, r))
    out: dict = {}
    for (code, part, var), items in groups.items():
        pool: dict[tuple, dict] = {}
        total = sum(r["frames"] for _k, r in items)
        for _k, r in items:
            s = r["sources"][0]
            vp = parse_monster(s["file"])
            if vp is None:
                continue
            key = (vp[0], vp[1], vp[2])
            e = pool.setdefault(key, {"frames": 0, "scales": [], "kinds": Counter(), "q": 0.0, "shift": [], "mash": 0})
            w = s["frames"]
            e["frames"] += w
            e["scales"].append(s["scale"])
            e["kinds"][s["kind"]] += w
            e["q"] += s["q"] * w
            if s["shift"]:
                e["shift"].append((w, s["shift"]))
            e["mash"] += r["category"] == "mashup"
        if not pool:
            continue
        best = max(pool, key=lambda k: pool[k]["frames"])
        e = pool[best]
        kind = e["kinds"].most_common(1)[0][0]
        sh = None
        if e["shift"]:
            tw = sum(w for w, _s in e["shift"])
            sh = {k: round(sum(w * s[k] for w, s in e["shift"]) / tw, 3) for k in ("hue", "sat", "val")}
        out.setdefault(code, {}).setdefault(part, {})[var] = {
            "source": "/".join(best), "kind": kind, "frames": e["frames"], "of": total,
            "coverage": round(e["frames"] / max(1, total), 3), "q": round(e["q"] / max(1, e["frames"]), 3),
            "scale": round(float(np.median(e["scales"])), 3) if "rescale" in kind else 1.0, "shift": sh,
            "files": len(items),
            "alt": ["/".join(k) for k in sorted((k for k in pool if k != best), key=lambda k: -pool[k]["frames"])[:3]]}
    return out


# ---------------------------------------------------------------------------------------------- main
def run_group(name: str, args, pool, results: dict) -> None:
    kinds = GROUPS[name]
    print(f"== {name}", flush=True)
    mfiles, vfiles = inventory("mxl", kinds), inventory("d2r", kinds)
    if args.only:
        mfiles = {k: p for k, p in mfiles.items() if args.only in k}
    gsig = hashlib.sha1(repr((ALGO, sorted((k, sig(p)) for k, p in inventory("mxl", kinds).items()),
                              sorted((k, sig(p)) for k, p in vfiles.items()))).encode()).hexdigest()
    done = None if (args.rebuild or args.only) else load_cache(f"result_{name}.pkl")
    if done and done.get("gsig") == gsig:
        print(f"  unchanged inputs: results of {name} from the cache", flush=True)
        results[name] = done["data"]
        return
    mf = features(inventory("mxl", kinds), "mxl_" + name, pool, args.rebuild)
    vf = features(vfiles, "d2r_" + name, pool, args.rebuild)
    mf = {k: v for k, v in mf.items() if k in mfiles}
    cand = candidates(mf, vf, vfiles)
    rcache = {} if args.rebuild else load_cache(f"verify_{name}.pkl")
    tasks, keys = [], []
    for k in mf:
        if mf[k]["err"]:
            continue
        cps = [str(vfiles[c]) for c in cand.get(k, [])]
        s = (ALGO, mf[k]["sig"], tuple((c, vf[c]["sig"]) for c in cand.get(k, [])))
        if k in rcache and rcache[k][0] == s:
            continue
        tasks.append((str(mfiles[k]), cps))
        keys.append((k, s))
    if tasks:
        t = time.time()
        print(f"  verifying {len(tasks)} Median files ...", flush=True)
        for (k, s), r in zip(keys, pool.map(verify, tasks, chunksize=2)):
            rcache[k] = (s, r)
        print(f"  verified in {time.time() - t:.0f}s", flush=True)
        save_cache(f"verify_{name}.pkl", rcache)
    vkey_of = {str(p): k for k, p in vfiles.items()}
    files = {}
    for k in mf:
        if mf[k]["err"]:
            files[k] = {"frames": 0, "category": "error", "error": mf[k]["err"], "sources": []}
            continue
        ver = rcache[k][1]
        if ver["err"]:
            files[k] = {"frames": 0, "category": "error", "error": ver["err"], "sources": []}
            continue
        cps = [str(vfiles[c]) for c in cand.get(k, [])]
        r = aggregate(k, ver, cps, mf[k], vkey_of)
        r["median_only"] = k not in vfiles
        r["pixels"] = int(mf[k]["hist"].sum())
        files[k] = r
    # exact files: do the other directions agree too?
    ex = [k for k, r in files.items() if r["category"] == "exact" and not r["retime"] and r["sources"]
          and r["sources"][0]["share"] >= 0.95]
    for k in ex:
        r = files[k]
        r["all_directions"] = mid_dir_equal(str(mfiles[k]), str(vfiles[r["sources"][0]["file"]]))
    results[name] = {"files": files}
    if name == "monsters":
        results[name]["parts"] = rollup_monsters(files)
    if not args.only:
        save_cache(f"result_{name}.pkl", {"gsig": gsig, "data": results[name]})


def summary(results: dict) -> dict:
    """Per group and library kind: files by category and the match rate."""
    out = {}
    for g, data in results.items():
        by_kind: dict[str, Counter] = defaultdict(Counter)
        for k, r in data["files"].items():
            by_kind[k.split("/", 1)[0]][r["category"]] += 1
            if r.get("median_only"):
                by_kind[k.split("/", 1)[0] + " (Median-only)"][r["category"]] += 1
            if r.get("retime"):
                by_kind[k.split("/", 1)[0]]["retime flag"] += 1
        out[g] = {kind: dict(c) for kind, c in by_kind.items()}
    return out


def write_reports(results: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    summ = summary(results)
    (out / "art_provenance.json").write_text(
        json.dumps({"version": 1, "summary": summ, **{g: d for g, d in results.items()}}, separators=(",", ":")),
        encoding="utf-8")
    md = ["# Art provenance: Median's DCC animations against D2R's own (tools/art_provenance.py)", "",
          "Categories: exact (frame for frame), recolour (same silhouette, palette mapped), rescale (same silhouette at another "
          "size, `rescale+recolour` counts here), mashup (frames from several vanilla animations), new (< 50% of the "
          "frames match). `retime` is a flag on top: the matched frames come in another number or order.", ""]
    cats = ["exact", "recolour", "rescale", "mashup", "new"]
    for g, kinds in summ.items():
        md += [f"## {g}", "", "| Library | Files | " + " | ".join(cats) + " | retime flag | match rate |",
               "|---|---|" + "---|" * (len(cats) + 2)]
        for kind, c in sorted(kinds.items()):
            tot = sum(c.get(x, 0) for x in cats) + c.get("error", 0)
            md.append(f"| {kind} | {tot} | " + " | ".join(str(c.get(x, 0)) for x in cats) + f" | {c.get('retime flag', 0)} | "
                      f"{100 * (tot - c.get('new', 0) - c.get('error', 0)) / max(1, tot):.1f}% |")
        md.append("")
    for g in ("effects", "monsters"):
        if g not in results:
            continue
        md += [f"## {g}: Median-only files", "",
               "| Median file | Category | Retime | Conf | Cover | Source(s) | Kind | Scale | Shift hue/sat/val |",
               "|---|---|---|---|---|---|---|---|---|"]
        rows = [(k, r) for k, r in results[g]["files"].items() if r.get("median_only")]
        for k, r in sorted(rows, key=lambda t: (t[1]["category"], t[0])):
            if g == "monsters" and r["category"] == "new":
                continue
            s = r["sources"][0] if r["sources"] else None
            more = f" (+{len(r['sources']) - 1})" if len(r["sources"]) > 1 else ""
            sh = s["shift"] if s else None
            md.append(f"| {k} | {r['category']} | {'yes' if r.get('retime') else ''} | {r.get('confidence', '')} | "
                      f"{r.get('coverage', '')} | {(s['file'] + more) if s else ''} | {s['kind'] if s else ''} | "
                      f"{s['scale'] if s else ''} | {('%+.2f/%+.2f/%+.2f' % (sh['hue'], sh['sat'], sh['val'])) if sh else ''} |")
        md.append("")
    (out / "art_provenance.md").write_text("\n".join(md) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------------- self test
def hue_remap(turns: float) -> np.ndarray:
    """Palette index map that rotates every colour's hue (nearest palette entry), index 0 stays."""
    import colorsys
    pal = palette()
    out = np.arange(256)
    for i in range(1, 256):
        h, sat, v = colorsys.rgb_to_hsv(*(pal[i] / 255.0))
        tgt = np.array(colorsys.hsv_to_rgb((h + turns) % 1.0, sat, v)) * 255.0
        out[i] = 1 + int(((pal[1:] - tgt) ** 2).sum(1).argmin())
    return out


def selftest() -> int:
    """Synthetic edits of vanilla frames must be classified as what they are."""
    import random
    rng = random.Random(1)
    files = sorted((VAN / "missiles").glob("*.dcc"))
    rng.shuffle(files)
    pal = palette()
    ok = Counter()
    tot = Counter()
    for p in files[:60]:
        try:
            cr = [c for c in crops_of(decode_dir(p.read_bytes(), 0)) if c is not None and (c[2] > 0).sum() > 120]
        except Exception:
            continue
        if not cr:
            continue
        a = cr[len(cr) // 2][2]
        perm = hue_remap(0.33)
        tests = {"exact": a, "recolour": perm[a].astype(np.uint8)}
        for f in (0.5, 0.75, 1.5, 2.0):
            h, w = a.shape
            nh, nw = max(2, round(h * f)), max(2, round(w * f))
            tests[f"rescale {f} nn"] = nn_resize(a, nh, nw)
            rgb = pal[a]
            im = Image.fromarray(rgb.astype(np.uint8)).resize((nw, nh), Image.Resampling.BILINEAR)
            mk = Image.fromarray(((a > 0) * 255).astype(np.uint8)).resize((nw, nh), Image.Resampling.BILINEAR)
            arr = np.asarray(im, np.float64).reshape(-1, 3)
            d = ((arr[:, None, :] - pal[None, 1:, :]) ** 2).sum(2)
            q = (d.argmin(1) + 1).astype(np.uint8).reshape(nh, nw)
            q[np.asarray(mk) < 128] = 0
            tests[f"rescale {f} bilinear"] = q
        for name, t in tests.items():
            r = compare(t, a)
            tot[name] += 1
            want = "exact" if name == "exact" else "recolour" if name == "recolour" else "rescale"
            if r is not None and want in r["kind"]:
                ok[name] += 1
    for k in tot:
        print(f"{k:24s} {ok[k]}/{tot[k]}")
    return 0 if all(ok[k] >= 0.9 * tot[k] for k in tot) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--groups", default="effects,monsters", help="effects (missiles + overlays) and/or monsters")
    ap.add_argument("--jobs", type=int, default=max(1, min(12, (os.cpu_count() or 4) - 4)))
    ap.add_argument("--rebuild", action="store_true", help="ignore the caches")
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--only", help="substring of the Median file key (debugging)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    results: dict = {}
    t0 = time.time()
    with ProcessPoolExecutor(args.jobs) as pool:
        for g in args.groups.split(","):
            run_group(g, args, pool, results)
    write_reports(results, Path(args.out))
    print(json.dumps(summary(results)))
    print(f"done in {time.time() - t0:.0f}s -> {Path(args.out) / 'art_provenance.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
