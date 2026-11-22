// hdkit.view browser page: the per-frame maths, ported from the Python the CLI runs (no decoding here: the bundle
// holds decoded meshes and pre-sampled clips). Every function names its Python original; matrices are row-major
// Float64Array(16) as numpy holds them. Pure functions, no DOM, so Node can test them against the Python.

// camera.py basis (= tools/sprite3d/cam_fit.py basis): right r, up u, towards the camera w
export function basis(az, el) {
  const a = az * Math.PI / 180, e = el * Math.PI / 180;
  return [[Math.cos(a), 0, -Math.sin(a)],
          [-Math.sin(a) * Math.sin(e), Math.cos(e), -Math.cos(a) * Math.sin(e)],
          [Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e)]];
}

// camera.OrthoCamera.matrix: world -> clip of the pixel rectangle (x0, y0, tw, th); depth 0 at dmax, 1 at dmin
export function orthoMatrix(az, el, k, origin, rect, dmin, dmax) {
  const [r, u, w] = basis(az, el);
  const [x0, y0, tw, th] = rect;
  const span = Math.max(dmax - dmin, 1e-6);
  const M = new Float64Array(16);
  for (let i = 0; i < 3; i++) {
    M[i] = 2 * k / tw * r[i];
    M[4 + i] = 2 * k / th * u[i];
    M[8 + i] = -w[i] / span;
  }
  M[3] = 2 * (origin[0] - x0) / tw - 1;
  M[7] = 1 - 2 * (origin[1] - y0) / th;
  M[11] = dmax / span;
  M[15] = 1;
  return M;
}

// camera.rot_y
export function rotY(deg) {
  const c = Math.cos(deg * Math.PI / 180), s = Math.sin(deg * Math.PI / 180);
  return [c, 0, s, 0, 1, 0, -s, 0, c];
}

// camera.facing_yaw
export function facingYaw(dir64, yaw0 = 45, sign = -1) { return yaw0 + sign * dir64 * (360 / 64); }

// gr2.qmat of a normalised quaternion (x, y, z, w) times scale/shear, translation: gr2.compose
export function compose(L, o, out, oo) {
  // L: Float64Array of bone locals, o: offset of (pos 3, quat 4, ss 9)
  let x = L[o + 3], y = L[o + 4], z = L[o + 5], w = L[o + 6];
  const n = Math.max(Math.sqrt(x * x + y * y + z * z + w * w), 1e-12);
  x /= n; y /= n; z /= n; w /= n;
  const q = [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
             2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
             2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)];
  for (let i = 0; i < 3; i++) {
    for (let j = 0; j < 3; j++) {
      out[oo + i * 4 + j] = q[i * 3] * L[o + 7 + j] + q[i * 3 + 1] * L[o + 7 + 3 + j] + q[i * 3 + 2] * L[o + 7 + 6 + j];
    }
    out[oo + i * 4 + 3] = L[o + i];
  }
  out[oo + 12] = 0; out[oo + 13] = 0; out[oo + 14] = 0; out[oo + 15] = 1;
}

function mul4(A, ao, B, bo, C, co) {
  for (let i = 0; i < 4; i++) {
    for (let j = 0; j < 4; j++) {
      C[co + i * 4 + j] = A[ao + i * 4] * B[bo + j] + A[ao + i * 4 + 1] * B[bo + 4 + j] +
                          A[ao + i * 4 + 2] * B[bo + 8 + j] + A[ao + i * 4 + 3] * B[bo + 12 + j];
    }
  }
}

// gr2.Skeleton.worlds(rest/clip locals) @ iwt: the skin matrices (bones x 16)
export function skinMatrices(locals, parent, iwt) {
  const nb = parent.length;
  const loc = new Float64Array(nb * 16), W = new Float64Array(nb * 16), S = new Float64Array(nb * 16);
  for (let b = 0; b < nb; b++) {
    compose(locals, b * 16, loc, b * 16);
    if (parent[b] < 0) W.set(loc.subarray(b * 16, b * 16 + 16), b * 16);
    else mul4(W, parent[b] * 16, loc, b * 16, W, b * 16);
    mul4(W, b * 16, iwt, b * 16, S, b * 16);
  }
  return S;
}

// bone locals of a pre-sampled clip at clip time t (gr2.locals_at: clamped, or wrapped when loop). On a sample time the
// sample itself (what the CLI poses with); between samples position and scale/shear are lerped and the rotation
// nlerped (gr2.blend_locals' rule).
export function clipLocals(clip, data, nb, t, loop) {
  const d = clip.duration, fps = clip.fps, n = clip.samples;
  if (loop && d > 0) t = ((t % d) + d) % d; else t = Math.min(Math.max(t, 0), d);
  const f = t * fps, r = Math.round(f);
  const at = i => data.subarray(i * nb * 16, (i + 1) * nb * 16);
  if (Math.abs(f - r) < 1e-6 && r <= n - 1) return at(r);
  const i0 = Math.min(Math.floor(f), n - 1), i1 = Math.min(i0 + 1, n - 1);
  const t0 = Math.min(i0 / fps, d), t1 = Math.min(i1 / fps, d);
  const wgt = t1 > t0 ? (t - t0) / (t1 - t0) : 0;
  return blendLocals(at(i0), at(i1), wgt, nb);
}

// gr2.blend_locals
export function blendLocals(a, b, w, nb) {
  const out = new Float64Array(nb * 16);
  for (let k = 0; k < nb; k++) {
    const o = k * 16;
    let dot = 0;
    for (let i = 3; i < 7; i++) dot += a[o + i] * b[o + i];
    const sg = dot < 0 ? -1 : 1;
    for (let i = 0; i < 16; i++) {
      if (i >= 3 && i < 7) out[o + i] = (1 - w) * a[o + i] + w * sg * b[o + i];
      else out[o + i] = (1 - w) * a[o + i] + w * b[o + i];
    }
    let n = 0;
    for (let i = 3; i < 7; i++) n += out[o + i] * out[o + i];
    n = Math.max(Math.sqrt(n), 1e-12);
    for (let i = 3; i < 7; i++) out[o + i] /= n;
  }
  return out;
}

// gr2.skin, then the world transform of gpu.Renderer.prepare (R = rot_y(yaw) * root scale, Rn = rot_y(yaw)), then the
// vertex layout of gpu.Renderer._vbuf (pos 3, nrm 3, tan 4, uv 2, barycentric 3 per triangle corner, float32).
// Returns {vb: Float32Array, dmin, dmax} with the depth range of camera.depth over these vertices (towards-camera w).
export function buildVertices(mesh, S, yaw, rootScale, w, out) {
  const nv = mesh.vertices, P = mesh.pos, N = mesh.nrm, T = mesh.tan, J = mesh.joints, Wt = mesh.weights;
  const pos = new Float64Array(nv * 3), nrm = new Float64Array(nv * 3), tan = new Float64Array(nv * 3);
  if (S && J) {
    for (let v = 0; v < nv; v++) {
      const px = P[v * 3], py = P[v * 3 + 1], pz = P[v * 3 + 2];
      let ox = 0, oy = 0, oz = 0;
      const R = [0, 0, 0, 0, 0, 0, 0, 0, 0];
      for (let k = 0; k < 4; k++) {
        const b = J[v * 4 + k] * 16, wk = Wt[v * 4 + k];
        ox += wk * (S[b] * px + S[b + 1] * py + S[b + 2] * pz + S[b + 3]);
        oy += wk * (S[b + 4] * px + S[b + 5] * py + S[b + 6] * pz + S[b + 7]);
        oz += wk * (S[b + 8] * px + S[b + 9] * py + S[b + 10] * pz + S[b + 11]);
        for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) R[i * 3 + j] += wk * S[b + i * 4 + j];
      }
      pos[v * 3] = ox; pos[v * 3 + 1] = oy; pos[v * 3 + 2] = oz;
      for (const [src, dst, so] of [[N, nrm, 3], [T, tan, 4]]) {
        const a = src[v * so], bb = src[v * so + 1], c = src[v * so + 2];
        const x = R[0] * a + R[1] * bb + R[2] * c, y = R[3] * a + R[4] * bb + R[5] * c, z = R[6] * a + R[7] * bb + R[8] * c;
        const n = Math.max(Math.sqrt(x * x + y * y + z * z), 1e-12);
        dst[v * 3] = x / n; dst[v * 3 + 1] = y / n; dst[v * 3 + 2] = z / n;
      }
    }
  } else {
    for (let v = 0; v < nv; v++) {
      for (let i = 0; i < 3; i++) { pos[v * 3 + i] = P[v * 3 + i]; nrm[v * 3 + i] = N[v * 3 + i]; tan[v * 3 + i] = T[v * 4 + i]; }
    }
  }
  const Rn = rotY(yaw), R = Rn.map(x => x * rootScale);
  const tris = mesh.tris, nt = tris.length / 3, uv = mesh.uv;
  const vb = out && out.length === nt * 45 ? out : new Float32Array(nt * 45);
  let dmin = Infinity, dmax = -Infinity;
  const wp = new Float64Array(nv * 3), wn = new Float64Array(nv * 3), wt = new Float64Array(nv * 3);
  for (let v = 0; v < nv; v++) {
    for (let i = 0; i < 3; i++) {
      wp[v * 3 + i] = R[i * 3] * pos[v * 3] + R[i * 3 + 1] * pos[v * 3 + 1] + R[i * 3 + 2] * pos[v * 3 + 2];
      wn[v * 3 + i] = Rn[i * 3] * nrm[v * 3] + Rn[i * 3 + 1] * nrm[v * 3 + 1] + Rn[i * 3 + 2] * nrm[v * 3 + 2];
      wt[v * 3 + i] = Rn[i * 3] * tan[v * 3] + Rn[i * 3 + 1] * tan[v * 3 + 1] + Rn[i * 3 + 2] * tan[v * 3 + 2];
    }
  }
  for (let t = 0; t < nt; t++) {
    for (let c = 0; c < 3; c++) {
      const v = tris[t * 3 + c], o = (t * 3 + c) * 15;
      vb[o] = wp[v * 3]; vb[o + 1] = wp[v * 3 + 1]; vb[o + 2] = wp[v * 3 + 2];
      vb[o + 3] = wn[v * 3]; vb[o + 4] = wn[v * 3 + 1]; vb[o + 5] = wn[v * 3 + 2];
      vb[o + 6] = wt[v * 3]; vb[o + 7] = wt[v * 3 + 1]; vb[o + 8] = wt[v * 3 + 2]; vb[o + 9] = T[v * 4 + 3];
      vb[o + 10] = uv[v * 2]; vb[o + 11] = uv[v * 2 + 1];
      vb[o + 12] = c === 0 ? 1 : 0; vb[o + 13] = c === 1 ? 1 : 0; vb[o + 14] = c === 2 ? 1 : 0;
      const d = wp[v * 3] * w[0] + wp[v * 3 + 1] * w[1] + wp[v * 3 + 2] * w[2];
      if (d < dmin) dmin = d;
      if (d > dmax) dmax = d;
    }
  }
  return {vb, dmin, dmax};
}

// player.Player: mode -> state -> clip, loops, one-shots, crossfades in local space, timing "clip" or "classic"
export class Player {
  constructor(sm, clips, timing = "clip") {
    this.sm = sm; this.clips = clips; this.timing = timing;
    this.fade = new Map((sm ? sm.crossfade : []).map(([a, b, s]) => [a + ">" + b, s]));
  }
  mode(tok) { return this.sm.modes[tok]; }
  length(tok) {
    const m = this.mode(tok), c = this.clips[m.clip];
    if (this.timing === "classic" && m.length_classic) return m.length_classic;
    return c ? c.duration : 0;
  }
  clipTime(tok, t) {
    const m = this.mode(tok), c = this.clips[m.clip], L = this.length(tok);
    if (!c || L <= 0) return 0;
    return t * c.duration / L;
  }
  crossfade(fromTok, toTok) {
    return this.fade.get(this.mode(fromTok).state_id + ">" + this.mode(toTok).state_id) || 0;
  }
  // the timeline frame of player.Player.timeline at `local` seconds into `tok`, entered from `prev` = {tok, left}
  // (left = seconds the previous mode had run when it was left)
  frame(tok, local, prev) {
    const m = this.mode(tok);
    const f = {clip: m.clip, clipT: this.clipTime(tok, local), loop: m.loop, weight: 1};
    if (prev && prev.tok !== undefined) {
      const fade = this.crossfade(prev.tok, tok);
      if (fade > 0 && local < fade) {
        const pm = this.mode(prev.tok);
        Object.assign(f, {prevClip: pm.clip, prevT: this.clipTime(prev.tok, prev.left), prevLoop: pm.loop,
                          weight: local / fade});
      }
    }
    return f;
  }
}
