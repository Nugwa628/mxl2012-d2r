"""The game's tone chain as far as it is known, for the "game" light rig: scene-linear value -> display sRGB.

Ported (vectorised) from the dump research's emulation `viewer/re/excerpts/tonecurve.py` (lane hdtools, from
ps_tonemap_p and cs_generate_sdr_lut_c of D2R 3.3, disassembled with D3DDisassemble): HDR x 0.008, PQ (ST.2084)
encode, the SDR LUT generator's ICtCp intensity EETF (knee 0.403838, max 0.602558), PQ decode x 125, BT.2020 -> 709,
sRGB encode. What is NOT here, said plainly:
  - the 3D grading LUT (`data/hd/env/lut/default.dds`, two LUTs blended): not decoded, so not applied (`lut: null`);
  - in `apply` (tone "game"), the chroma path of the EETF: colours are mapped hue-preserving through the grey curve of
    their luminance (an approximation). `lut_chain` (tone "lut", below) follows the full colour path of the game's LUT
    build (cs_lut_combine_c), chroma included; only its max-RGB tone curve parameters are unknown (off by default).
Near black the chain is the plain sRGB encode (0.1 -> 0.349, as the research table shows); the shoulder starts at about
0.4 and display white is reached at about 1.05.
"""
import numpy as np

M1, M2, C1, C2, C3 = 0.159302, 78.84375, 0.8359375, 18.8515625, 18.6875
KS, MAXL, MINL = 0.403838, 0.602558, 0.000001
SCALE = 0.008
LMS = np.array([[0.412109, 0.523926, 0.063965], [0.166748, 0.720459, 0.112793], [0.024170, 0.075439, 0.900391]])
TO709 = np.array([[1.660532, -0.587643, -0.072840], [-0.124554, 1.132903, -0.008348], [-0.018151, -0.100579, 1.118581]]) @ \
    np.array([[3.436610, -2.506450, 0.069845], [-0.791330, 1.983600, -0.192271], [-0.025950, -0.098914, 1.124860]])
LUMA = np.array([0.2126, 0.7152, 0.0722])


def pq_enc(x):
    x = np.power(np.abs(x), M1)
    return np.power((C1 + C2 * x) / (1 + C3 * x), M2)


def pq_dec(e):
    e = np.power(np.abs(e), 1 / M2)
    return np.power(np.maximum(e - C1, 0) / (C2 - C3 * e), 1 / M1)


def eetf(i):
    """The intensity roll-off of cs_generate_sdr_lut_c (the asm's Hermite spline above the knee), vectorised."""
    i = np.asarray(i, float)
    e = np.clip(i, 0.0, 1.0)
    y = e - KS
    z = y * 1.677395
    w = z * z
    z3 = z * w
    x2 = -w * 2 + z3
    y2 = (y * 1.677395 + x2) * 0.596162
    w3 = w * 3
    a = z3 * 2 - w3
    b = z3 * -2 + w3
    knee = (a + 1) * KS + y2 + b * MAXL
    out = np.where(e >= KS, knee, e)
    out = np.where(i >= 1, MAXL, np.where(i <= 0, MINL, out))
    return out + ((1 - out) ** 4) * MINL


def grey(v):
    """Display sRGB (unclipped) of a grey scene value v: the research emulation, any array shape."""
    v = np.asarray(v, float)
    w = pq_dec(pq_enc(v * SCALE)) * 125.0          # tonemap PQ encode + LUT address: identity up to LUT sampling
    I = pq_enc(w * SCALE)                          # L'=M'=S' for a grey (LMS rows sum to 1)
    lin = pq_dec(eetf(I)) * 125.0
    x = np.maximum(lin * TO709.sum(1)[1], 0.0)     # grey stays grey; the green row's sum is the luma scale
    return np.where(x < 0.003131, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


_XS = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 2048)])
_YS = grey(_XS)


def srgb_decode(x):
    x = np.asarray(x, float)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))


def apply(rgb, exposure: float = 1.0):
    """Scene-linear rgb (..., 3) times `exposure` -> display sRGB 0..1, colour kept hue-preserving by the luminance's
    grey curve (see the module note)."""
    c = np.maximum(np.asarray(rgb, float) * exposure, 0.0)
    y = c @ LUMA
    d = np.interp(y, _XS, _YS)                     # display value of the luminance
    yl = srgb_decode(np.clip(d, 0.0, 1.0))         # its linear display level
    k = np.where(y > 1e-9, yl / np.maximum(y, 1e-9), 0.0)
    lin = np.clip(c * k[..., None], 0.0, 1.0)
    return np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)


# --- The game's full colour path (viewer cal3) -------------------------------------------------------------------------
# Read from D2R 3.3's cs_lut_combine_c.bin blob 1 (the compute shader that builds the 65^3 LUT that ps_tonemap_p samples
# at PQ(v x 0.008)); disassembled with Windows' d3dcompiler_47 D3DDisassemble. Per LUT cell, exposed scene value v:
#   1. sRGB/709 -> AP1 (the matrix includes the D65 -> D60 adaptation)
#   2. gamut expansion of bright saturated colours: luma = AP1 Y; d = |v/luma - 1|^2;
#      amount = (1 - 2^(-4 d)) (1 - 2^(-4 luma^2)); v += amount (EXPAND v - v)
#   3. a max-RGB tone curve (channel ratios kept, so hue and saturation are kept): toe A m^B / line / shoulder
#      W - A'(W - m)^B'; its parameters sit in frame constants (cb10[66].y = W, cb10[67] = two points) whose values
#      are in no data file found, so the curve is OFF (identity) unless `curve=(W, x0, y0, x1, y1)` is given
#   4. AP1 -> BT.2020, x 0.008, PQ, the grading LUT (default.dds: identity), colour-blind filter (strength 0)
#   5. ICtCp EETF to the display peak (cb10[52].x nits; 250 nits is the peak the SDR LUT generator hard-codes:
#      PQ 0.602558, knee 1.5 P - 0.5 = 0.403838): I is rolled off, Ct and Cp are scaled by min(I/I', I'/I)^5
#   6. LMS -> BT.2020 -> BT.709, clamp at 0, sRGB encode (gamma 1/2.4, slope 12.92; cb10[52].z / cb10[49].w)
# Above display 1.0 each channel clips on its own (8-bit output).
SRGB_AP1 = np.array([[0.613191, 0.339512, 0.047366], [0.070207, 0.916336, 0.013450], [0.020619, 0.109567, 0.869607]])
AP1_Y = np.array([0.272229, 0.674082, 0.053690])
EXPAND = np.array([[1.370413, -0.329291, -0.063683], [-0.083434, 1.097091, -0.010862], [-0.025793, -0.098626, 1.203694]])
AP1_2020 = np.array([[1.025799, -0.020053, -0.005771], [-0.002235, 1.004583, -0.002352], [-0.005014, -0.025293, 1.030440]])
LMS_2020 = np.array([[3.436610, -2.506450, 0.069845], [-0.791330, 1.983600, -0.192271], [-0.025950, -0.098914, 1.124860]])
B2020_709 = np.array([[1.660532, -0.587643, -0.072840], [-0.124554, 1.132903, -0.008348], [-0.018151, -0.100579, 1.118581]])
PEAK_NITS = 250.0


def gamut_expand(ap1):
    y = ap1 @ AP1_Y
    ch = ap1 / np.maximum(y, 1e-5)[..., None] - 1.0
    d = (ch * ch).sum(-1)
    amt = (1.0 - np.exp2(-4.0 * d)) * (1.0 - np.exp2(-4.0 * y * y))
    return ap1 + amt[..., None] * (ap1 @ EXPAND.T - ap1)


def max_rgb_curve(m, W, x0, y0, x1, y1):
    """The max-channel curve of step 3 (piecewise power: toe, line, shoulder), points in units of W; clips at W."""
    m = np.asarray(m, float)
    a, b, c, d = W * x0, W * y0, W * x1, W * y1
    k = (d - b) / (c - a)
    mm = np.maximum(m, 1e-12)
    if a > 0 and b > 0:
        tb = a * k / b
        toe = np.exp(np.log(b) - tb * np.log(a) + tb * np.log(mm))
    else:
        toe = k * m
    lin = k * m + (b - a * k)
    if c < W and d < W:
        sb = k * (W - c) / (W - d)
        sh = W - np.exp(np.log(W - d) - sb * np.log(W - c) + sb * np.log(np.maximum(W - m, 1e-12)))
    else:
        sh = lin
    out = np.where(m > a, lin, toe)
    return np.where(m > c, np.where(m >= W, W, sh), out)


def eetf_peak(i, peak_pq):
    """The ICtCp intensity roll-off of cs_lut_combine_c (at 250 nits the same as cs_generate_sdr_lut_c's)."""
    i = np.asarray(i, float)
    ks = 1.5 * peak_pq - 0.5
    e = np.minimum(i, 1.0)
    t = (e - ks) / (1.0 - ks)
    t2, t3 = t * t, t * t * t
    p = (2 * t3 - 3 * t2 + 1) * ks + (t3 - 2 * t2 + t) * (1.0 - ks) + (-2 * t3 + 3 * t2) * peak_pq
    out = np.where(e >= ks, p, e)
    out = out + ((1.0 - out) ** 4) * MINL
    return np.where(i >= 1.0, peak_pq, np.where(i <= 0.0, MINL, out))


def lut_chain(v, peak_nits: float = PEAK_NITS, curve=None, expand: bool = True):
    """Exposed scene rgb (..., 3) -> display sRGB (not clipped above 1): the game's LUT path (module note above)."""
    v = np.maximum(np.asarray(v, float), 0.0)
    c = v @ SRGB_AP1.T
    if expand:
        c = gamut_expand(c)
    if curve is not None:
        m = c.max(-1)
        nm = max_rgb_curve(m, *curve)
        c = np.where(m[..., None] > 0, c / np.maximum(m, 1e-12)[..., None] * nm[..., None], 0.0)
    c = np.maximum(c, 0.0) @ AP1_2020.T
    E = pq_enc(np.maximum(c @ LMS.T, 0.0) * SCALE)                  # L'M'S'
    L_, M_, S_ = E[..., 0], E[..., 1], E[..., 2]
    I = 0.5 * (L_ + M_)
    ct = 1.613770 * L_ - 3.323486 * M_ + 1.709717 * S_
    cp = 4.378174 * L_ - 4.245605 * M_ - 0.132568 * S_
    I2 = eetf_peak(I, float(pq_enc(peak_nits * 0.0001)))
    r = np.minimum(I / np.maximum(I2, 1e-12), I2 / np.maximum(I, 1e-12))
    s = np.abs(r) ** 5
    ct, cp = ct * s, cp * s
    lms = pq_dec(np.stack([I2 + 0.008609 * ct + 0.111030 * cp, I2 - 0.008609 * ct - 0.111030 * cp,
                           I2 + 0.560031 * ct - 0.320627 * cp], -1)) * 125.0
    x = np.maximum(lms @ LMS_2020.T @ B2020_709.T, 0.0)
    return np.where(x < 0.003131, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def value_curve(v, brightness: float = 0.0, points=(0.25, 0.25, 0.75, 0.99), strength: float = 0.0):
    """The unit value curve at the end of ps_models_p, gated by a per-draw flag (cb2[19].w): the exposed colour goes to
    HSV and V becomes (V + cb2[19].y x poly(sat(V))) x (1 + cb2[19].x), hue and saturation kept; poly = cb2[18] .
    (1, V, V^2, V^3). The CPU code that fills cb2[18..19] was not found, so the mapping is a hypothesis: poly = P(V) - V
    with P the cubic through (0, 0), the vis characterContrastPoints and (1, 1), strength = cb2[19].y, brightness =
    cb2[19].x. Identity at the defaults."""
    v = np.asarray(v, float)
    V = v.max(-1)
    x0, y0, x1, y1 = points
    A = np.array([[x0, x0 ** 2, x0 ** 3], [x1, x1 ** 2, x1 ** 3], [1.0, 1.0, 1.0]])
    a1, a2, a3 = np.linalg.solve(A, [y0, y1, 1.0])
    Vs = np.clip(V, 0.0, 1.0)
    poly = (a1 - 1.0) * Vs + a2 * Vs ** 2 + a3 * Vs ** 3
    nV = (V + strength * poly) * (1.0 + brightness)
    return np.where(V[..., None] > 0, v * (nV / np.maximum(V, 1e-12))[..., None], 0.0)


def _down(x):
    h, w = x.shape[0] // 2 * 2, x.shape[1] // 2 * 2
    return 0.25 * (x[:h:2, :w:2] + x[1:h:2, :w:2] + x[:h:2, 1:w:2] + x[1:h:2, 1:w:2])


def bloom(v, cutoff: float = 1.0, intensity: float = 1.0, levels: int = 5, gain: float = 1.0):
    """The bloom of ps_bloom_cutoff_p / ps_bloom_downsample_p / ps_upsample_p / ps_combine_p on an exposed HDR image
    (H, W, 3): pixels whose BT.709 luma is at least `cutoff` (vis bloomCutoff) pass as c / (1 + luma), are halved
    `levels` times (4-tap box, then a 13-tap kernel), upsampled and summed, and the sum is added to the scene before the
    tone map (ps_combine_p: a + b). Not known from the bytecode alone: the level count, the per-level weights and the
    upsample's cb4 term, so the levels are weighted equally, intensity x gain / levels (an assumption, fitted by gain)."""
    from scipy import ndimage
    v = np.asarray(v, float)
    y = v @ LUMA
    c = np.where((y >= cutoff)[..., None], v / (1.0 + y)[..., None], 0.0)
    acc = np.zeros_like(v)
    x = c
    for _ in range(levels):
        if min(x.shape[:2]) < 4:
            break
        x = ndimage.uniform_filter(_down(x), (3, 3, 1))
        z = ndimage.zoom(x, (v.shape[0] / x.shape[0], v.shape[1] / x.shape[1], 1), order=1)
        acc += z[:v.shape[0], :v.shape[1]]
    return acc * (intensity * gain / max(levels, 1))
