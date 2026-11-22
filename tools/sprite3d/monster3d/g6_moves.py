"""Stage 6: measures and strips of a mon_moves run (g6_movecap.py): 3D against classic (legacy graphics) at equal times.

  python g6_moves.py measure <shots dir> <out.json> [--modes 2,4,5,3] [--shift 8]
  python g6_moves.py sheet <shots dir> <measure.json> <out.png> [--keys 0,2,5] [--modes 2,4,5,3] [--step 0.08]
                                 [--title T] [--base <measure.json of another run>]

Frames with a skill's lightning over the unit (near-white pixels > 4 % of the unit's box) are left out.
Cap: the blue rim pixels (B >= 70, B - max(R,G) > 20, plus bright pale-blue pixels next to them, as capring.py) outside the
player's box, the piece with the best size / distance to
the place over the unit's feet, plus pieces near it, convex hull; tilt = main-axis angle of that hull (s5_clipfit.tilt).
Body: each saved cut minus the same box of the key's empty-spot shot (bg) of the same graphics; a pixel is the unit when some
channel differs by >= 28, it is not a shadow (all channels darkened by the same ratio) and not in the player's box; opened,
kept within 80 px of the cap's centre and below its top, the pieces touching the cap or the foot box, with the cap.
Skill effects (A1's lightning) that touch the unit count as unit in both graphics.
Per key and unit mode, the longest whole run of that mode in each graphics is used, time = t_mode (from the run's first poll).
  iou    per legacy frame, the 3D frame nearest in t_mode (within 0.05 s), IoU after the best shift of at most --shift px
  cap    the same for the cap hulls (cap_iou): the robust measure, as the body mask also takes skill effects and dark
         legacy limbs over dark ground are lost
  tilt   |cap angle 3D - cap angle classic| of the same pairs (where both caps are found)
  lag    the time shift (-0.3 .. 0.3 s) of the 3D run that gives the best mean cap IoU against classic: the timing error
  dip    t_mode of the cap's lowest point in each run (GH: the duck), error = 3D - classic per key
  apex   t_mode of the cap's highest point (A1: the jump), error = 3D - classic per key
  period loops only (WL): the lag (0.35 .. 1.6 s) of the best self-match of each run's cap hulls; error = 3D - classic
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as nd
from skimage.morphology import convex_hull_image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from s5_clipfit import tilt  # noqa: E402

MODES = {0: "DT", 1: "NU", 2: "WL", 3: "GH", 4: "A1", 5: "A2", 12: "DD"}
FOOT = (150, 225)


def box(lab):
    dx, dy = lab["x"] - lab["px"], lab["y"] - lab["py"]
    sx, sy = 800 + 24 * (dx - dy), 428 + 12 * (dx + dy)
    return (sx - 150, sy - 225, sx + 150, sy + 75)


class Run:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.ix = json.loads((self.folder / "monturn_index.json").read_text(encoding="utf-8"))
        self.bg = {(e["graphics"], e["spawn_key"]): e["shot"] for e in self.ix if e["what"] == "bg"}
        self._bg = {}
        self._m = {}

    def bgimg(self, g, k):
        if (g, k) not in self._bg:
            self._bg[(g, k)] = Image.open(self.folder / self.bg[(g, k)]).convert("RGB")
        return self._bg[(g, k)]

    def frames(self, g, k, mode):
        """frames of the longest whole run of `mode` (graphics g, key k), sorted by t_mode; a run cut by the burst's
        start (first frame later than 0.1 s into the mode) only when no other run is there."""
        fr = [e for e in self.ix if e.get("cut") and e["graphics"] == g and e["spawn_key"] == k and e.get("mode") == mode]
        runs = {}
        for e in fr:
            runs.setdefault((e["what"][0], e["mode_run"]), []).append(e)
        if not runs:
            return []
        def rank(r):
            return (min(x["t_mode"] for x in r) <= 0.1, max(x["t_mode"] for x in r), len(r))
        return sorted(max(runs.values(), key=rank), key=lambda e: e["t_mode"])

    def img(self, e):
        return np.asarray(Image.open(self.folder / e["shot"]).convert("RGB")).astype(float)

    def masks(self, e):
        if e["shot"] in self._m:
            return self._m[e["shot"]]
        a = self.img(e)
        b = np.asarray(self.bgimg(e["graphics"], e["spawn_key"]).crop(box(e["before"]))).astype(float)
        diff = np.abs(a - b).max(2) >= 28
        ratio = (a + 1) / (b + 1)
        shadow = (ratio.std(2) < 0.07) & (ratio.mean(2) > 0.2) & (ratio.mean(2) < 0.93)
        lab0 = e["before"]
        dx, dy = lab0["x"] - lab0["px"], lab0["y"] - lab0["py"]
        plx, ply = 150 - 24 * (dx - dy), 225 - 12 * (dx + dy)          # the player's feet in the cut
        yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        player = (np.abs(xx - plx) <= 24) & (yy >= ply - 100) & (yy <= ply + 12)
        fx, fy = FOOT
        R, G, B = a[..., 0], a[..., 1], a[..., 2]
        # cap: the blue rim piece best placed over the unit's feet (other monsters and the player's effects are pieces too)
        L = a @ np.array([0.2126, 0.7152, 0.0722])
        flash = (L >= 200) & (a.max(2) - a.min(2) <= 70)
        if flash[max(0, fy - 200):fy + 40, max(0, fx - 110):fx + 110].mean() > 0.04:
            self._m[e["shot"]] = (np.zeros(L.shape, bool), np.zeros(L.shape, bool))   # a skill's lightning over the unit
            return self._m[e["shot"]]
        bl0 = (B >= 70) & (B - np.maximum(R, G) > 20)
        pale = (L >= 150) & (B >= R) & (B >= G - 6) & nd.binary_dilation(bl0, iterations=3)
        blue = (bl0 | pale) & ~player
        blue[:, :max(0, fx - 100)] = False
        blue[:, fx + 100:] = False
        blue[fy - 10:] = False
        cap = np.zeros(blue.shape, bool)
        blue = nd.binary_closing(blue, iterations=2)
        lab2, n2 = nd.label(blue)
        ccx, ccy = fx, fy - 95
        if n2:
            ids = range(1, n2 + 1)
            sizes = np.array(nd.sum(blue, lab2, ids))
            cms = nd.center_of_mass(blue, lab2, ids)
            score = [sz / (1 + np.hypot(c[0] - (fy - 95), c[1] - fx) / 30) for sz, c in zip(sizes, cms)]
            big = int(np.argmax(score))
            if sizes[big] >= 30:
                ccy, ccx = cms[big]
                part = np.zeros_like(blue)
                for k, (sz, c) in enumerate(zip(sizes, cms)):
                    if k == big or (sz >= 8 and np.hypot(c[0] - ccy, c[1] - ccx) < 40):
                        part |= lab2 == k + 1
                cap = convex_hull_image(part)
        # body: changed pixels (no shadow, no player), the pieces touching the cap or the foot box, near the cap
        m = nd.binary_opening(diff & ~shadow & ~player, iterations=1)
        m = nd.binary_closing(m, iterations=2) & (np.abs(xx - ccx) < 80) & (yy > ccy - 70)
        lab, n = nd.label(m | cap)
        keep = np.zeros_like(m)
        if n:
            seed = nd.binary_dilation(cap, iterations=4)
            seed[fy - 60:fy + 15, fx - 30:fx + 30] = True
            ids = [i for i in np.unique(lab[seed]) if i]
            sizes = nd.sum(m | cap, lab, ids) if ids else []
            keep = np.isin(lab, [i for i, sz in zip(ids, sizes) if sz >= 40])
        self._m[e["shot"]] = (keep, cap)
        return keep, cap


def shift_iou(a, b, s):
    best, bs = -1.0, (0, 0)
    if not a.any() or not b.any():
        return np.nan, bs
    for dy in range(-s, s + 1, 2):
        for dx in range(-s, s + 1, 2):
            bb = np.roll(np.roll(b, dy, 0), dx, 1)
            i = (a & bb).sum() / max((a | bb).sum(), 1)
            if i > best:
                best, bs = float(i), (dy, dx)
    return best, bs


def nearest(fr, t, tol=0.05):
    e = min(fr, key=lambda e: abs(e["t_mode"] - t)) if fr else None
    return e if e is not None and abs(e["t_mode"] - t) <= tol else None


def period(run, fr, s):
    if len(fr) < 8:
        return None
    t = np.array([e["t_mode"] for e in fr])
    best = (-1, None)
    for lag in np.arange(0.35, 1.6, 0.02):
        vals = []
        for i, e in enumerate(fr):
            j = nearest(fr, t[i] + lag, 0.03)
            if j is not None:
                vals.append(shift_iou(run.masks(e)[1], run.masks(j)[1], s)[0])
        vals = [v for v in vals if np.isfinite(v)]
        if len(vals) >= 4 and np.mean(vals) > best[0]:
            best = (float(np.mean(vals)), round(float(lag), 3))
    return best[1]


def measure(folder, out, modes=(2, 4, 5, 3), s=8):
    run = Run(folder)
    keys = sorted({e["spawn_key"] for e in run.ix})
    res = {"folder": str(folder), "modes": {}}
    for mo in modes:
        per = {}
        for k in keys:
            L, H = run.frames("legacy", k, mo), run.frames("hd", k, mo)
            if not L or not H:
                per[k] = {"frames_legacy": len(L), "frames_hd": len(H)}
                continue
            ious, capious, tilts, pairs = [], [], [], []
            for e in L:
                h = nearest(H, e["t_mode"])
                if h is None:
                    continue
                (ml, cl), (mh, ch) = run.masks(e), run.masks(h)
                if not ml.any() or not mh.any():
                    continue                       # lightning over the unit in one of the two frames
                i, sh = shift_iou(ml, mh, s)
                ious.append(i)
                ci = shift_iou(cl, ch, s)[0] if cl.sum() > 30 and ch.sum() > 30 else np.nan
                capious.append(ci)
                a1, a2 = tilt(cl)[0] if cl.sum() > 30 else np.nan, tilt(ch)[0] if ch.sum() > 30 else np.nan
                d = abs((a2 - a1 + 90) % 180 - 90) if np.isfinite(a1) and np.isfinite(a2) else np.nan
                tilts.append(d)
                pairs.append({"t": e["t_mode"], "legacy": e["shot"], "hd": h["shot"], "iou": round(i, 3),
                              "cap_iou": None if not np.isfinite(ci) else round(float(ci), 3),
                              "tilt_legacy": None if not np.isfinite(a1) else round(float(a1), 1),
                              "tilt_hd": None if not np.isfinite(a2) else round(float(a2), 1)})
            span = min(L[-1]["t_mode"], H[-1]["t_mode"])
            lags = []
            for lag in np.arange(-0.3, 0.301, 0.02):
                v = []
                for e in L:
                    if e["t_mode"] + lag < 0 or e["t_mode"] + lag > span:
                        continue
                    h = nearest(H, e["t_mode"] + lag, 0.03)
                    if h is not None:
                        v.append(shift_iou(run.masks(e)[1], run.masks(h)[1], s)[0])
                v = [x for x in v if np.isfinite(x)]
                if len(v) >= 3:
                    lags.append((float(np.mean(v)), round(float(lag), 2)))
            r = {"frames_legacy": len(L), "frames_hd": len(H), "run_legacy_s": L[-1]["t_mode"], "run_hd_s": H[-1]["t_mode"],
                 "dirs": sorted({e["before"].get("dir") for e in L + H if e["before"].get("dir") is not None}),
                 "median_iou": round(float(np.nanmedian(ious)), 3) if np.isfinite(ious).any() else None,
                 "median_cap_iou": round(float(np.nanmedian(capious)), 3) if np.isfinite(capious).any() else None,
                 "median_tilt_err_deg": round(float(np.nanmedian(tilts)), 1) if np.isfinite(tilts).any() else None,
                 "lag_s": max(lags)[1] if lags else None, "iou_at_lag": round(max(lags)[0], 3) if lags else None,
                 "pairs": pairs}
            def dip(fr):
                """t_mode of the cap's lowest point (centroid y of the cap hull; the dive of A1, the duck of GH)."""
                pts = [(nd.center_of_mass(run.masks(e)[1])[0], e["t_mode"]) for e in fr if run.masks(e)[1].sum() > 30]
                return max(pts)[1] if len(pts) >= 4 else None
            def apex(fr):
                """t_mode of the cap's highest point (A1's jump)."""
                pts = [(nd.center_of_mass(run.masks(e)[1])[0], e["t_mode"]) for e in fr if run.masks(e)[1].sum() > 30]
                return min(pts)[1] if len(pts) >= 4 else None
            dl, dh = dip(L), dip(H)
            r.update(dip_legacy_s=dl, dip_hd_s=dh, dip_err_s=round(dh - dl, 3) if dl is not None and dh is not None else None)
            al, ah = apex(L), apex(H)
            r.update(apex_legacy_s=al, apex_hd_s=ah, apex_err_s=round(ah - al, 3) if al is not None and ah is not None else None)
            if mo == 2:
                pl, ph = period(run, L, s), period(run, H, s)
                r.update(period_legacy_s=pl, period_hd_s=ph,
                         period_err_s=round(ph - pl, 3) if pl is not None and ph is not None else None)
            per[k] = r
            print(MODES[mo], "key", k, {x: r.get(x) for x in ("frames_legacy", "frames_hd", "median_iou", "median_cap_iou",
                                                                  "median_tilt_err_deg", "lag_s", "dip_err_s", "apex_err_s", "period_err_s")}, flush=True)
        ok = [v for v in per.values() if v.get("median_iou") is not None]
        summ = {"keys_with_pairs": len(ok),
                "median_iou": round(float(np.median([v["median_iou"] for v in ok])), 3) if ok else None,
                "median_cap_iou": round(float(np.nanmedian([v["median_cap_iou"] if v["median_cap_iou"] is not None else np.nan
                                                            for v in ok])), 3) if ok else None,
                "median_tilt_err_deg": round(float(np.nanmedian([v["median_tilt_err_deg"] if v["median_tilt_err_deg"] is not None
                                                                 else np.nan for v in ok])), 1) if ok else None,
                "median_abs_lag_s": round(float(np.median([abs(v["lag_s"]) for v in ok if v["lag_s"] is not None])), 3)
                if ok else None}
        de = [v["dip_err_s"] for v in ok if v.get("dip_err_s") is not None]
        summ["median_dip_err_s"] = round(float(np.median(de)), 3) if de else None
        summ["median_abs_dip_err_s"] = round(float(np.median(np.abs(de))), 3) if de else None
        dls = [v["dip_legacy_s"] for v in ok if v.get("dip_legacy_s") is not None]
        summ["median_dip_legacy_s"] = round(float(np.median(dls)), 3) if dls else None
        ae = [v["apex_err_s"] for v in ok if v.get("apex_err_s") is not None]
        summ["median_apex_err_s"] = round(float(np.median(ae)), 3) if ae else None
        summ["median_abs_apex_err_s"] = round(float(np.median(np.abs(ae))), 3) if ae else None
        als = [v["apex_legacy_s"] for v in ok if v.get("apex_legacy_s") is not None]
        summ["median_apex_legacy_s"] = round(float(np.median(als)), 3) if als else None
        if mo == 2:
            pe = [v["period_err_s"] for v in ok if v.get("period_err_s") is not None]
            summ["median_period_err_s"] = round(float(np.median(pe)), 3) if pe else None
            summ["median_period_legacy_s"] = round(float(np.median([v["period_legacy_s"] for v in ok
                                                                     if v.get("period_legacy_s")])), 3) if pe else None
        res["modes"][MODES[mo]] = {"summary": summ, "keys": per}
        print(MODES[mo], summ, flush=True)
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")


def sheet(folder, mjson, out, keys=(0, 2, 5), modes=(2, 4, 5, 3), step=0.08, title="", base=None):
    run = Run(folder)
    m = json.loads(Path(mjson).read_text(encoding="utf-8"))
    b = json.loads(Path(base).read_text(encoding="utf-8")) if base else None
    font, small = ImageFont.load_default(size=16), ImageFont.load_default(size=13)
    S, LW, TH, MH = 150, 92, 30, 26
    ncol = 11
    blocks = [(mo, k) for mo in modes for k in keys]
    W = LW + ncol * S
    H = TH + len(modes) * MH + len(blocks) * (2 * S + 20)
    sh = Image.new("RGB", (W, H), (24, 24, 30))
    d = ImageDraw.Draw(sh)
    d.text((6, 6), title or "3D against classic at equal times in the mode (s); classic above 3D", fill=(230, 200, 120), font=font)
    y = TH
    for mo in modes:
        sm = m["modes"].get(MODES[mo], {}).get("summary", {})
        txt = "%s  IoU body %s cap %s | cap tilt err %s deg | lag %s s | cap high %+.2f s, low %+.2f s (classic %s, %s)" % (
            MODES[mo], sm.get("median_iou"), sm.get("median_cap_iou"), sm.get("median_tilt_err_deg"), sm.get("median_abs_lag_s"),
            sm.get("median_apex_err_s") or 0, sm.get("median_dip_err_s") or 0, sm.get("median_apex_legacy_s"),
            sm.get("median_dip_legacy_s"))
        if mo == 2:
            txt += "  period err %s s (classic %s s)" % (sm.get("median_period_err_s"), sm.get("median_period_legacy_s"))
        if b:
            bs = b["modes"].get(MODES[mo], {}).get("summary", {})
            txt += "   [donor clip: IoU %s / %s, tilt %s, lag %s]" % (bs.get("median_iou"), bs.get("median_cap_iou"),
                                                                    bs.get("median_tilt_err_deg"), bs.get("median_abs_lag_s"))
        d.text((6, y + 4), txt, fill=(220, 220, 160), font=font)
        y += MH
        for k in keys:
            L, Hh = run.frames("legacy", k, mo), run.frames("hd", k, mo)
            kv = m["modes"].get(MODES[mo], {}).get("keys", {}).get(str(k), {})
            d.text((4, y + 4), "%s k%d" % (MODES[mo], k), fill=(230, 230, 230), font=font)
            d.text((4, y + 24), "IoU %s/%s" % (kv.get("median_iou"), kv.get("median_cap_iou")), fill=(200, 200, 200), font=small)
            d.text((4, y + 40), "tilt %s" % kv.get("median_tilt_err_deg"), fill=(200, 200, 200), font=small)
            d.text((4, y + 56), "lag %s" % kv.get("lag_s"), fill=(200, 200, 200), font=small)
            d.text((4, y + S - 14), "classic", fill=(170, 170, 170), font=small)
            d.text((4, y + 2 * S - 14), "3D", fill=(170, 170, 170), font=small)
            for c in range(ncol):
                t = round(c * step, 3)
                for ri, fr in enumerate((L, Hh)):
                    e = nearest(fr, t, step / 2 + 0.01)
                    if e is None:
                        continue
                    im = Image.open(run.folder / e["shot"]).convert("RGB").crop((50, 60, 250, 260)).resize((S, S), Image.LANCZOS)
                    sh.paste(im, (LW + c * S, y + ri * S))
                d.text((LW + c * S + 3, y + 2 * S + 2), "%.2f" % t, fill=(190, 190, 190), font=small)
            y += 2 * S + 20
    sh.save(out)
    print(out, sh.size)


def opt(a, name, default, cast=str):
    return cast(a[a.index(name) + 1]) if name in a else default


if __name__ == "__main__":
    a = sys.argv[1:]
    ints = lambda s: tuple(int(x) for x in s.split(","))  # noqa: E731
    if a[0] == "measure":
        measure(a[1], a[2], opt(a, "--modes", (2, 4, 5, 3), ints), opt(a, "--shift", 8, int))
    elif a[0] == "sheet":
        sheet(a[1], a[2], a[3], opt(a, "--keys", (0, 2, 5), ints), opt(a, "--modes", (2, 4, 5, 3), ints),
              opt(a, "--step", 0.08, float), opt(a, "--title", ""), opt(a, "--base", None))
