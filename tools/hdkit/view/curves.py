"""Granny 2 animation curves: decode every curve kind to knots and control points, and sample them exactly.

Decoders ported from LSLib (Copyright (c) 2015 Norbyte, MIT, github.com/Norbyte/lslib @6f5f698,
LSLib/Granny/Model/CurveData/*.cs): the knot and control layouts, the quantised quaternion of D4nK16uC15u / D4nK8uC7u
(16-entry scale and offset tables, 2-bit swizzle, sign bit, rebuilt 4th component) and the knot scale of the
"...Trunc" kinds (a u16 put into the high half of a float32). The arithmetic is done in float32 as LSLib does it.

Sampling is ours. LSLib and the Reimagined Level Editor read each control point as the value at its knot and lerp or
slerp between them (`method="keys"` reproduces that). Granny evaluates a curve of degree d as a B-spline: for t in the
span [k[i-1], k[i]) (i = first knot greater than t) it blends controls c[i-d] .. c[i] with de Boor's algorithm over
knots k[i-d] .. k[i+d-1]. Degree 0 holds c[i-1], degree 1 is the lerp of c[i-1], c[i] (so "control = key" is exact up to
degree 1), degree 2 is a quadratic B-spline that does not pass through its inner controls. Outside the stored knots the
curve is extended: clamped (first and last knot and control repeated, so the curve starts at c[0] and ends at c[n-1]),
or looped (knots continued with the duration added or subtracted, controls wrapped). Which extension the game uses for
a looping state is not proven; the player picks `loop` for states with loopCount 0.

A decoded curve is `Curve(kind, degree, knots (n,), controls (n, dim), dim)`; `controls is None` for DaIdentity.
Dimensions: 3 for positions, 4 for quaternions (x, y, z, w), 9 for 3x3 scale/shear (row-major).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

import numpy as np

_F = np.float32

# D4nK16uC15u.cs / D4nK8uC7u.cs
_QSCALE = np.array([1.4142135, 0.70710677, 0.35355338, 0.35355338, 0.35355338, 0.17677669, 0.17677669, 0.17677669,
                    -1.4142135, -0.70710677, -0.35355338, -0.35355338, -0.35355338, -0.17677669, -0.17677669,
                    -0.17677669], _F)
_QOFFSET = np.array([-0.70710677, -0.35355338, -0.53033006, -0.17677669, 0.17677669, -0.17677669, -0.088388346, 0.0,
                     0.70710677, 0.35355338, 0.53033006, 0.17677669, -0.17677669, 0.17677669, 0.088388346, -0.0], _F)

KINDS = ("DaKeyframes32f", "DaK32fC32f", "DaIdentity", "DaConstant32f", "D3Constant32f", "D4Constant32f",
         "DaK16uC16u", "DaK8uC8u", "D4nK16uC15u", "D4nK8uC7u", "D3K16uC16u", "D3K8uC8u", "D9I1K16uC16u",
         "D9I3K16uC16u", "D9I1K8uC8u", "D9I3K8uC8u", "D3I1K32fC32f", "D3I1K16uC16u", "D3I1K8uC8u")


class UnsupportedCurve(ValueError):
    pass


@dataclass
class Curve:
    kind: str
    degree: int
    knots: np.ndarray            # (n,) float64, times in seconds
    controls: np.ndarray | None  # (n, dim) float64; None = identity
    dim: int

    @property
    def n(self) -> int:
        return len(self.knots)


def _vals(seq) -> np.ndarray:
    """A list of numbers or of one-field Obj (ControlUInt8 / UInt16 / Real32) as a float64 array."""
    out = []
    for x in seq:
        f = getattr(x, "f", None)
        out.append(next(iter(f.values())) if f is not None else x)
    return np.asarray(out, np.float64)


def knot_scale_trunc(v: int) -> float:
    """ConvertOneOverKnotScaleTrunc: the u16 is the high half of a float32."""
    return struct.unpack("<f", struct.pack("<I", (int(v) & 0xFFFF) << 16))[0]


def _quat_d4n(kc: np.ndarray, n: int, selector: int, bits: int) -> np.ndarray:
    """Quaternions of D4nK16uC15u (bits 16) / D4nK8uC7u (bits 8), as LSLib's QuatFromControl."""
    inv = _F(0.000030518509) if bits == 16 else _F(0.0078740157)
    sc = np.array([_QSCALE[(selector >> s) & 15] * inv for s in (0, 4, 8, 12)], _F)
    of = np.array([_QOFFSET[(selector >> s) & 15] for s in (0, 4, 8, 12)], _F)
    top, low = (0x8000, 0x7FFF) if bits == 16 else (0x80, 0x7F)
    c = kc[n:n + 3 * n].astype(np.int64).reshape(n, 3)
    a, b, cc = c[:, 0], c[:, 1], c[:, 2]
    s1 = (((b & top) != 0).astype(int) << 1) | ((cc & top) != 0).astype(int)
    s2, s3, s4 = (s1 + 1) & 3, (s1 + 2) & 3, (s1 + 3) & 3
    da = (a & low).astype(_F) * sc[s2] + of[s2]
    db = (b & low).astype(_F) * sc[s3] + of[s3]
    dc = (cc & low).astype(_F) * sc[s4] + of[s4]
    dd = np.sqrt(np.maximum(_F(1) - (da * da + db * db + dc * dc), _F(0))).astype(_F)
    dd = np.where((a & top) != 0, -dd, dd)
    q = np.zeros((n, 4), _F)
    r = np.arange(n)
    q[r, s2], q[r, s3], q[r, s4], q[r, s1] = da, db, dc, dd
    return q.astype(np.float64)


def decode(curve, dim_hint: int | None = None) -> Curve:
    """Decode a CurveData variant (d2r_model.Variant / Obj, or a track's *Curve object) to knots and controls."""
    v = curve
    if getattr(v, "f", None) is not None and "CurveData" in v.f:
        v = v["CurveData"]
    o = v.obj if hasattr(v, "obj") else v
    head = list(o.f)[0]
    kind = head.replace("CurveDataHeader_", "")
    hdr = o[head]
    degree = int(hdr["Degree"])
    g = o.f.get

    def tk(kc, n):
        return kc[:n].astype(_F) / _F(knot_scale_trunc(g("OneOverKnotScaleTrunc")))

    if kind == "DaIdentity":
        d = int(g("Dimension") or dim_hint or 0)
        return Curve(kind, 0, np.zeros(1), None, d)
    if kind in ("DaConstant32f", "D3Constant32f", "D4Constant32f"):
        c = _vals(g("Controls")).astype(_F).astype(np.float64)
        return Curve(kind, 0, np.zeros(1), c.reshape(1, -1), len(c))
    if kind == "DaKeyframes32f":
        d = int(g("Dimension"))
        c = _vals(g("Controls")).astype(_F).astype(np.float64)
        n = len(c) // d
        return Curve(kind, degree, np.arange(n, dtype=np.float64), c[:n * d].reshape(n, d), d)
    if kind == "DaK32fC32f":
        k = _vals(g("Knots")).astype(_F)
        c = _vals(g("Controls")).astype(_F)
        n = len(k)
        d = len(c) // max(n, 1)
        return Curve(kind, degree, k.astype(np.float64), c[:n * d].reshape(n, d).astype(np.float64), d)
    kc = _vals(g("KnotsControls"))
    if kind in ("D4nK16uC15u", "D4nK8uC7u"):
        n = len(kc) // 4
        knots = kc[:n].astype(_F) / _F(g("OneOverKnotScale"))
        q = _quat_d4n(kc, n, int(g("ScaleOffsetTableEntries")), 16 if kind == "D4nK16uC15u" else 8)
        return Curve(kind, degree, knots.astype(np.float64), q, 4)
    if kind in ("DaK16uC16u", "DaK8uC8u"):
        so = _vals(g("ControlScaleOffsets")).astype(_F)
        d = len(so) // 2
        n = len(kc) // (d + 1)
        c = kc[n:n + n * d].astype(_F).reshape(n, d) * so[:d] + so[d:2 * d]
        return Curve(kind, degree, tk(kc, n).astype(np.float64), c.astype(np.float64), d)
    if kind in ("D3K16uC16u", "D3K8uC8u"):
        sc, of = _vals(g("ControlScales")).astype(_F), _vals(g("ControlOffsets")).astype(_F)
        n = len(kc) // 4
        c = kc[n:4 * n].astype(_F).reshape(n, 3) * sc + of
        return Curve(kind, degree, tk(kc, n).astype(np.float64), c.astype(np.float64), 3)
    if kind in ("D3I1K32fC32f", "D3I1K16uC16u", "D3I1K8uC8u"):
        sc, of = _vals(g("ControlScales")).astype(_F), _vals(g("ControlOffsets")).astype(_F)
        n = len(kc) // 2
        k = kc[:n].astype(_F) if kind == "D3I1K32fC32f" else tk(kc, n)
        c = kc[n:2 * n].astype(_F)[:, None] * sc + of
        return Curve(kind, degree, k.astype(np.float64), c.astype(np.float64), 3)
    if kind in ("D9I1K16uC16u", "D9I1K8uC8u"):
        s, off = _F(g("ControlScale")), _F(g("ControlOffset"))
        n = len(kc) // 2
        u = (kc[n:2 * n].astype(_F) * s + off).astype(np.float64)
        c = np.zeros((n, 9))
        c[:, 0] = c[:, 4] = c[:, 8] = u
        return Curve(kind, degree, tk(kc, n).astype(np.float64), c, 9)
    if kind in ("D9I3K16uC16u", "D9I3K8uC8u"):
        sc, of = _vals(g("ControlScales")).astype(_F), _vals(g("ControlOffsets")).astype(_F)
        n = len(kc) // 4
        u = (kc[n:4 * n].astype(_F).reshape(n, 3) * sc + of).astype(np.float64)
        c = np.zeros((n, 9))
        c[:, 0], c[:, 4], c[:, 8] = u[:, 0], u[:, 1], u[:, 2]
        return Curve(kind, degree, tk(kc, n).astype(np.float64), c, 9)
    raise UnsupportedCurve(kind)


# ---- sampling ----------------------------------------------------------------------------------------------------------------

def _extended(c: Curve, p: int, loop: bool, duration: float | None):
    """Knots and controls with p entries added at each end (clamped or looped); index shift p."""
    k, C, n = c.knots, c.controls, c.n
    if loop and n > 2:
        D = float(duration if duration is not None else k[-1] - k[0])
        # k[0] and k[n-1] are the same instant of the loop: wrap over the n-1 distinct keys
        pre_k = np.array([k[n - 1 - m] - D for m in range(p, 0, -1)])
        post_k = np.array([k[m] + D for m in range(1, p + 1)])
        pre_c = np.stack([C[n - 1 - m] for m in range(p, 0, -1)])
        post_c = np.stack([C[m] for m in range(1, p + 1)])
    else:
        pre_k, post_k = np.full(p, k[0]), np.full(p, k[-1])
        pre_c, post_c = np.repeat(C[:1], p, 0), np.repeat(C[-1:], p, 0)
    return np.concatenate([pre_k, k, post_k]), np.concatenate([pre_c, C, post_c])


def deboor(K: np.ndarray, C: np.ndarray, p: int, i: int, t: float) -> np.ndarray:
    """B-spline value on span [K[i-1], K[i]): controls C[i-p..i], knots K[i-p..i+p-1] (Granny's window)."""
    d = [C[i - p + r].astype(np.float64).copy() for r in range(p + 1)]
    for r in range(1, p + 1):
        for s in range(p, r - 1, -1):
            lo = K[i - p + s - 1]
            hi = K[i + s - r]
            den = hi - lo
            a = 0.0 if den <= 0 else (t - lo) / den
            d[s] = (1.0 - a) * d[s - 1] + a * d[s]
    return d[p]


def sample(c: Curve, t: float, method: str = "bspline", loop: bool = False, duration: float | None = None,
           normalize: bool | None = None) -> np.ndarray | None:
    """Value of the curve at time t (seconds). None for an identity curve.
    method "bspline": Granny's evaluation at the stored degree (exact); "keys": LSLib/LE reading (control = key at its
    knot, lerp between keys; quaternions are lerped and normalised, which equals slerp to first order).
    Quaternions (dim 4) are normalised unless normalize=False."""
    if c.controls is None:
        return None
    C, k, n = c.controls, c.knots, c.n
    norm = (c.dim == 4) if normalize is None else normalize
    if n == 1:
        out = C[0].copy()
    else:
        lo, hi = k[0], k[-1]
        if loop and n > 2:
            D = float(duration if duration is not None else hi - lo)
            t = lo + ((t - lo) % D) if D > 0 else lo
        else:
            t = min(max(t, lo), hi)
        if method == "keys" or c.degree <= 1:
            i = int(np.searchsorted(k, t, side="right"))
            if i >= n:
                out = C[-1].copy()
            elif i == 0:
                out = C[0].copy()
            elif c.degree == 0 and method != "keys":
                out = C[i - 1].copy()
            else:
                s = (t - k[i - 1]) / max(k[i] - k[i - 1], 1e-12)
                a, b = C[i - 1], C[i]
                if c.dim == 4 and float(np.dot(a, b)) < 0:
                    b = -b
                out = (1 - s) * a + s * b
        else:
            p = c.degree
            K, CC = _extended(c, p, loop, duration)
            i = int(np.searchsorted(k, t, side="right"))     # first knot > t in the stored knots
            i = min(max(i, 1), n - 1)
            out = deboor(K, CC, p, i + p, t)
    if norm:
        out = out / max(float(np.linalg.norm(out)), 1e-12)
    return out


def sample_many(c: Curve, ts, **kw) -> np.ndarray:
    return np.stack([sample(c, float(t), **kw) for t in ts])


def quat_flips(c: Curve) -> int:
    """Neighbouring quaternion controls in opposite hemispheres (a B-spline then blends through a wrong rotation)."""
    if c.controls is None or c.dim != 4 or c.n < 2:
        return 0
    return int((np.einsum("ij,ij->i", c.controls[:-1], c.controls[1:]) < 0).sum())
