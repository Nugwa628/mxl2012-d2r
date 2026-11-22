// hdkit.view browser page: loads an export-web bundle and draws it with the CLI's own shaders.wgsl (served at
// /shaders.wgsl, checked against the sha256 the bundle recorded). The GPU set-up mirrors gpu.Renderer: same bind group
// layout, pipelines (MSAA 4, rgba16float, depth32float, additive self-lit layers), sampler, uniform layout and draw order;
// present.wgsl does the CPU tail of gpu.render (box filter, rig exposure/tone, straight alpha or background).
import * as A from "./anim.js";

const $ = id => document.getElementById(id);
const Q = new URLSearchParams(location.search);
const BUNDLE = (Q.get("bundle") || "bundle/").replace(/\/?$/, "/");
const DT = {f4: Float32Array, f8: Float64Array, u4: Uint32Array, u2: Uint16Array, u1: Uint8Array};
const status = [];
function say(s) { status.push(s); $("status").textContent = status.slice(-14).join("\n"); }

async function fetchBuf(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + ": " + r.status);
  return r.arrayBuffer();
}
async function loadBlob(entry) {
  const buf = await fetchBuf(BUNDLE + entry.file);
  const out = {};
  for (const [k, [off, dt, shape]] of Object.entries(entry.fields)) {
    const n = shape.reduce((a, b) => a * b, 1);
    out[k] = new DT[dt](buf, off, n);
  }
  return out;
}
async function sha256hex(data) {
  const h = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(h)].map(b => b.toString(16).padStart(2, "0")).join("");
}
function srgbDecode1(x) { return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }
function hexLinear(s) { return [1, 3, 5].map(i => srgbDecode1(parseInt(s.slice(i, i + 2), 16) / 255)); }

// ---- state ----------------------------------------------------------------------------------------------------------
const S = {
  scene: null, dev: null, cam: "game", zoom: 1, orbit: {az: 45, el: 30, scale: 1, pan: [0, 0]}, pan: [0, 0],
  dir64: 0, mode: null, t: 0, playing: false, speed: 1, timing: "clip", prev: null, pass: "lit", ss: 2, glow: true,
  hide: new Set(), bodyBlack: false, bg: "#202020", rig: null, rigBase: null, size: [640, 640], dirty: true, aniso: 16,
};

// ---- GPU set-up (gpu.Renderer.__init__) -----------------------------------------------------------------------------
const G = {};
async function initGpu(sc) {
  if (!navigator.gpu) throw new Error("WebGPU is not available in this browser (use a current Chrome or Edge)");
  const ad = await navigator.gpu.requestAdapter({powerPreference: "high-performance"});
  if (!ad) throw new Error("no WebGPU adapter");
  const dev = await ad.requestDevice({requiredLimits: {maxTextureDimension2D: ad.limits.maxTextureDimension2D}});
  G.dev = dev; G.adapter = ad;
  dev.lost.then(i => say("device lost: " + i.message));
  const text = await (await fetch("shaders.wgsl")).text();
  const sh = await sha256hex(new TextEncoder().encode(text));
  G.shaderSha = sh;
  G.shaderOk = sh === sc.shader.sha256;
  say("shaders.wgsl sha256 " + sh.slice(0, 16) + "... " + (G.shaderOk ? "= the CLI's (bundle)" : "DIFFERS from the bundle's " + sc.shader.sha256.slice(0, 16)));
  const mod = dev.createShaderModule({code: text});
  const ci = await mod.getCompilationInfo();
  for (const m of ci.messages) say("wgsl " + m.type + ": " + m.message);
  const V = GPUShaderStage.VERTEX, F = GPUShaderStage.FRAGMENT;
  G.bgl = dev.createBindGroupLayout({entries: [
    {binding: 0, visibility: V | F, buffer: {type: "uniform"}},
    {binding: 1, visibility: F, sampler: {type: "filtering"}},
    ...[2, 3, 4, 5, 6].map(b => ({binding: b, visibility: F, texture: {sampleType: "float", viewDimension: "2d"}}))]});
  const layout = dev.createPipelineLayout({bindGroupLayouts: [G.bgl]});
  const vb = [{arrayStride: 15 * 4, stepMode: "vertex", attributes: [
    {format: "float32x3", offset: 0, shaderLocation: 0}, {format: "float32x3", offset: 12, shaderLocation: 1},
    {format: "float32x4", offset: 24, shaderLocation: 2}, {format: "float32x2", offset: 40, shaderLocation: 3},
    {format: "float32x3", offset: 48, shaderLocation: 4}]}];
  const add = {color: {srcFactor: "one", dstFactor: "one", operation: "add"},
               alpha: {srcFactor: "zero", dstFactor: "one", operation: "add"}};
  const pipe = (entry, blend, dw, cmp) => dev.createRenderPipeline({
    layout, vertex: {module: mod, entryPoint: "vs", buffers: vb},
    primitive: {topology: "triangle-list", cullMode: "none"},
    depthStencil: {format: "depth32float", depthWriteEnabled: dw, depthCompare: cmp},
    multisample: {count: 4},
    fragment: {module: mod, entryPoint: entry, targets: [blend ? {format: "rgba16float", blend} : {format: "rgba16float"}]}});
  G.pMain = pipe("fs_main", null, true, "less");
  G.pGlow = pipe("fs_glow", add, false, "less-equal");
  // one sampler per anisotropy: viewing uses the bundle's (CLI default 16); Match CLI uses the refs' own (matched: 1 on
  // both sides, as Chrome's D3D12 and the CLI's Vulkan pick different anisotropic samples: up to 26/255 apart at 16)
  G.samplers = {};
  G.sampler = an => G.samplers[an] || (G.samplers[an] = dev.createSampler({addressModeU: "repeat", addressModeV: "repeat",
    magFilter: "linear", minFilter: "linear", mipmapFilter: "linear", maxAnisotropy: Math.max(1, an | 0)}));
  G.viewAniso = sc.render.aniso;
  G.matchAniso = sc.render.ref_aniso || sc.render.aniso;
  G.ufloats = sc.render.uniform_floats || 64;          // gpu.UBUF_BYTES / 4
  G.points = sc.render.points || null;                 // {offset, max} of the point-light block (gpu.pack_points)
  // present (the CPU tail of gpu.render)
  const ptext = await (await fetch("present.wgsl")).text();
  const pmod = dev.createShaderModule({code: ptext});
  for (const m of (await pmod.getCompilationInfo()).messages) say("present.wgsl " + m.type + ": " + m.message);
  G.pbgl = dev.createBindGroupLayout({entries: [
    {binding: 0, visibility: F, buffer: {type: "uniform"}},
    {binding: 1, visibility: F, texture: {sampleType: "unfilterable-float", viewDimension: "2d"}},
    {binding: 2, visibility: F, buffer: {type: "read-only-storage"}},
    {binding: 3, visibility: F, buffer: {type: "read-only-storage"}}]});
  const pl = dev.createPipelineLayout({bindGroupLayouts: [G.pbgl]});
  G.present = {};
  G.presentPipe = fmt => G.present[fmt] || (G.present[fmt] = dev.createRenderPipeline({
    layout: pl, vertex: {module: pmod, entryPoint: "vs_full"}, primitive: {topology: "triangle-list"},
    fragment: {module: pmod, entryPoint: "fs_present", targets: [{format: fmt}]}}));
  G.pubuf = dev.createBuffer({size: 48, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST});
  const tone = await loadBlob(sc.tone);
  G.toneN = tone.xs.length;
  G.xs = dev.createBuffer({size: tone.xs.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST});
  G.ys = dev.createBuffer({size: tone.ys.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST});
  dev.queue.writeBuffer(G.xs, 0, tone.xs);
  dev.queue.writeBuffer(G.ys, 0, tone.ys);
  G.defaults = {};
  for (const [k, px] of Object.entries(sc.render.defaults)) {
    const srgb = k === "alb" || k === "strip";
    const t = dev.createTexture({size: [4, 4], format: srgb ? "rgba8unorm-srgb" : "rgba8unorm",
                                 usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST});
    const d = new Uint8Array(64);
    for (let i = 0; i < 16; i++) d.set(px, i * 4);
    dev.queue.writeTexture({texture: t}, d, {bytesPerRow: 16, rowsPerImage: 4}, [4, 4]);
    G.defaults[k] = t.createView();
  }
  G.info = ad.info || {};
  say("adapter: " + [G.info.vendor, G.info.architecture, G.info.description].filter(Boolean).join(" / "));
  G.canvasFormat = navigator.gpu.getPreferredCanvasFormat();
  G.ctx = $("cv").getContext("webgpu");
  G.ctx.configure({device: dev, format: G.canvasFormat, alphaMode: "opaque"});
}

// textures: every mip as the CLI decoded it (PNG, decoded without colour conversion or premultiplication)
const TEX = [];
async function texture(t) {
  const fmt = t.srgb ? "rgba8unorm-srgb" : "rgba8unorm";
  const m0 = t.mips[0];
  const tex = G.dev.createTexture({size: [m0.w, m0.h], format: fmt, mipLevelCount: t.mips.length,
    usage: GPUTextureUsage.TEXTURE_BINDING | GPUTextureUsage.COPY_DST | GPUTextureUsage.COPY_SRC | GPUTextureUsage.RENDER_ATTACHMENT});
  await Promise.all(t.mips.map(async (m, i) => {
    const blob = await (await fetch(BUNDLE + m.file)).blob();
    const bmp = await createImageBitmap(blob, {premultiplyAlpha: "none", colorSpaceConversion: "none"});
    G.dev.queue.copyExternalImageToTexture({source: bmp}, {texture: tex, mipLevel: i, premultipliedAlpha: false}, [m.w, m.h]);
    bmp.close();
  }));
  TEX.push({tex, t});
  return tex.createView();
}

// ---- scene -> draws (gpu.Renderer.prepare) ---------------------------------------------------------------------------
const D = {parts: [], draws: [], clips: {}, nb: 0};
async function loadScene(sc) {
  for (const p of sc.parts) {
    const part = {name: p.name, meshes: [], sk: null, layers: []};
    if (p.skeleton) {
      const b = await loadBlob(p.skeleton);
      part.sk = {parent: p.skeleton.parent, iwt: b.iwt, rest: b.rest, names: p.skeleton.names};
      D.nb = p.skeleton.names.length;
    }
    const views = {};
    for (const k of ["alb", "nrm", "orm"]) views[k] = p.textures[k] ? await texture(p.textures[k]) : G.defaults[k];
    const layers = [];
    for (const L of p.layers) layers.push({name: L.name, mask: await texture(L.mask), strip: await texture(L.strip)});
    for (const m of p.meshes) {
      const b = await loadBlob(m);
      const w = b.weights ? Float64Array.from(b.weights, x => x / 255) : b.weights_f64;
      const mesh = {name: m.name, vertices: m.vertices, pos: b.pos, nrm: b.nrm, tan: b.tan, uv: b.uv, tris: b.tris,
                    joints: m.skinned ? b.joints : null, weights: w};
      const nt = m.triangles;
      const vbuf = G.dev.createBuffer({size: nt * 45 * 4, usage: GPUBufferUsage.VERTEX | GPUBufferUsage.COPY_DST});
      const ub = G.dev.createBuffer({size: G.ufloats * 4, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST});
      const bind = mkBind(ub, views.alb, views.nrm, views.orm, G.defaults.mask, G.defaults.strip);
      const lay = layers.map(L => {
        const lub = G.dev.createBuffer({size: G.ufloats * 4, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST});
        return {name: L.name, ub: lub, bind: mkBind(lub, views.alb, views.nrm, views.orm, L.mask, L.strip)};
      });
      D.draws.push({part, mesh, vbuf, count: nt * 3, ub, bind, layers: lay, name: m.name, partName: p.name,
                    material: m.material, vb: null, dmin: 0, dmax: 0});
    }
    D.parts.push(part);
  }
  for (const [name, c] of Object.entries(sc.clips)) D.clips[name] = {meta: c, data: (await loadBlob(c)).locals};
}
function mkBind(ub, alb, nrm, orm, mask, strip) {
  const cache = {};       // anisotropy -> bind group
  return an => cache[an] || (cache[an] = G.dev.createBindGroup({layout: G.bgl, entries: [
    {binding: 0, resource: {buffer: ub}}, {binding: 1, resource: G.sampler(an)},
    {binding: 2, resource: alb}, {binding: 3, resource: nrm}, {binding: 4, resource: orm},
    {binding: 5, resource: mask}, {binding: 6, resource: strip}]}));
}

// pose: {clip, t, loop, prev...} -> bone locals (gr2.pose_at / player.Player.pose)
function localsOf(f) {
  const nb = D.nb, sk = D.parts.find(p => p.sk)?.sk;
  if (!sk) return null;
  const at = (clip, t, loop) => {
    const c = clip && D.clips[clip];
    return c ? A.clipLocals(c.meta, c.data, nb, t, loop) : sk.rest;
  };
  let cur = at(f.clip, f.clipT, f.loop);
  if (f.prevClip && f.weight < 1) cur = A.blendLocals(at(f.prevClip, f.prevT, f.prevLoop), cur, f.weight, nb);
  return cur;
}
let poseKey = "";
function pose(f, yaw, w) {
  const key = JSON.stringify([f, yaw, w]);
  if (key === poseKey) return;
  poseKey = key;
  const loc = localsOf(f);
  for (const dr of D.draws) {
    const sk = dr.part.sk;
    const Sm = sk && loc ? A.skinMatrices(loc, sk.parent, sk.iwt) : null;
    const r = A.buildVertices(dr.mesh, Sm, yaw, S.scene.root_scale, w, dr.vb);
    dr.vb = r.vb; dr.dmin = r.dmin; dr.dmax = r.dmax;
    G.dev.queue.writeBuffer(dr.vbuf, 0, r.vb);
  }
}

// Prepared.select: mesh:/part:/material:/layer:<name or *>, body
function selected(hide) {
  const H = [...hide].map(h => h.toLowerCase());
  const hit = (kind, v) => H.some(h => {
    if (!h.startsWith(kind + ":")) return false;
    const a = h.slice(kind.length + 1);
    v = (v || "").toLowerCase();
    return a === "*" || a === v || (kind === "material" && a && v.includes(a));
  });
  const body = H.includes("body");
  return D.draws.filter(d => !(hit("mesh", d.name) || hit("part", d.partName) || hit("material", d.material)))
    .map(d => ({d, layers: d.layers.filter(L => !hit("layer", L.name)), hiddenBody: body}));
}

// ---- one image (gpu.Renderer.render_rect + render) -------------------------------------------------------------------
const targets = {};
function target(w, h) {
  const k = w + "x" + h;
  if (!targets[k]) {
    for (const t of Object.values(targets)) { t.col.destroy(); t.res.destroy(); t.dep.destroy(); }
    for (const kk in targets) delete targets[kk];
    const U = GPUTextureUsage;
    targets[k] = {
      col: G.dev.createTexture({size: [w, h], format: "rgba16float", sampleCount: 4, usage: U.RENDER_ATTACHMENT}),
      res: G.dev.createTexture({size: [w, h], format: "rgba16float", usage: U.RENDER_ATTACHMENT | U.TEXTURE_BINDING}),
      dep: G.dev.createTexture({size: [w, h], format: "depth32float", sampleCount: 4, usage: U.RENDER_ATTACHMENT})};
  }
  return targets[k];
}
// v: {az, el, k, origin, W, H, ss, pass, glow, hide, rig (Rig.as_dict), bg: null | [r,g,b] linear | "checker", yaw, frame}
function draw(v, outView, outFormat) {
  const P = S.scene.render.passes;
  const [, , w] = A.basis(v.az, v.el);
  pose(v.frame, v.yaw, w);
  const sel = selected(v.hide);
  let dmin = Infinity, dmax = -Infinity;
  for (const s of sel) { dmin = Math.min(dmin, s.d.dmin); dmax = Math.max(dmax, s.d.dmax); }
  if (!sel.length) { dmin = 0; dmax = 0; }
  dmin -= 1; dmax += 1;
  const Wss = v.W * v.ss, Hss = v.H * v.ss;
  const M = A.orthoMatrix(v.az, v.el, v.k * v.ss, [v.origin[0] * v.ss, v.origin[1] * v.ss], [0, 0, Wss, Hss], dmin, dmax);
  const L = forClass(v.rig.light, "unit"), pid = P[v.pass];
  const kd = L.key_dir, kn = Math.max(Math.hypot(kd[0], kd[1], kd[2]), 1e-9);
  const uni = p => {
    const u = new Float32Array(G.ufloats);
    for (let r = 0; r < 4; r++) for (let c = 0; c < 4; c++) u[c * 4 + r] = M[r * 4 + c];
    u.set(w, 16); u.set(L.ambient, 20); u.set([kd[0] / kn, kd[1] / kn, kd[2] / kn], 24);
    u.set(L.key_col, 28); u.set(L.env_col, 32);
    u.set([p, L.glow_gain, L.nrm_green, 0], 36); u.set([dmin, dmax, L.floor_clip ?? 1, L.spec_gain], 40);
    if (G.points) {
      const pts = (L.points || []).slice(0, G.points.max), o0 = G.points.offset;
      u[o0] = pts.length;
      pts.forEach((q, i) => { const o = o0 + 4 + 8 * i;
        u.set(q.pos, o); u[o + 3] = q.radius; u.set(q.color, o + 4); u[o + 7] = q.atten ?? 1; });
    }
    return u;
  };
  for (const s of sel) {
    const bodyPid = s.hiddenBody && (pid === 0 || pid === 5) ? P.glow : pid;
    G.dev.queue.writeBuffer(s.d.ub, 0, uni(bodyPid));
    for (const l of s.layers) G.dev.queue.writeBuffer(l.ub, 0, uni(pid));
  }
  const T = target(Wss, Hss);
  const enc = G.dev.createCommandEncoder();
  const rp = enc.beginRenderPass({
    colorAttachments: [{view: T.col.createView(), resolveTarget: T.res.createView(), loadOp: "clear", storeOp: "discard",
                        clearValue: [0, 0, 0, 0]}],
    depthStencilAttachment: {view: T.dep.createView(), depthLoadOp: "clear", depthStoreOp: "discard", depthClearValue: 1}});
  rp.setPipeline(G.pMain);
  for (const s of sel) { rp.setBindGroup(0, s.d.bind(v.aniso)); rp.setVertexBuffer(0, s.d.vbuf); rp.draw(s.d.count); }
  if (v.glow && ["lit", "unlit", "glow"].includes(v.pass)) {
    rp.setPipeline(G.pGlow);
    for (const s of sel) for (const l of s.layers) { rp.setBindGroup(0, l.bind(v.aniso)); rp.setVertexBuffer(0, s.d.vbuf); rp.draw(s.d.count); }
  }
  rp.end();
  // present: gpu.to_uint8(box_down(...), pass, bg, rig.encode)
  const R = S.scene.render;
  const mode = R.rig_passes.includes(v.pass) ? 0 : R.srgb_passes.includes(v.pass) ? 1 : 2;
  const bgm = v.bg === null ? 0 : v.bg === "checker" ? 2 : 1;
  const bgc = Array.isArray(v.bg) ? v.bg : [0, 0, 0];
  G.dev.queue.writeBuffer(G.pubuf, 0, new Float32Array([v.ss, mode, v.rig.tone === "game" ? 1 : 0, v.rig.exposure,
                                                        bgc[0], bgc[1], bgc[2], bgm, G.toneN, 0, 0, 0]));
  const pb = G.dev.createBindGroup({layout: G.pbgl, entries: [
    {binding: 0, resource: {buffer: G.pubuf}}, {binding: 1, resource: T.res.createView()},
    {binding: 2, resource: {buffer: G.xs}}, {binding: 3, resource: {buffer: G.ys}}]});
  const pp = enc.beginRenderPass({colorAttachments: [{view: outView, loadOp: "clear", storeOp: "store", clearValue: [0, 0, 0, 1]}]});
  pp.setPipeline(G.presentPipe(outFormat));
  pp.setBindGroup(0, pb);
  pp.draw(3);
  pp.end();
  G.dev.queue.submit([enc.finish()]);
}

async function readRGBA(v) {
  const tex = G.dev.createTexture({size: [v.W, v.H], format: "rgba8unorm",
                                   usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC});
  draw(v, tex.createView(), "rgba8unorm");
  const bpr = Math.ceil(v.W * 4 / 256) * 256;
  const buf = G.dev.createBuffer({size: bpr * v.H, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ});
  const enc = G.dev.createCommandEncoder();
  enc.copyTextureToBuffer({texture: tex}, {buffer: buf, bytesPerRow: bpr}, [v.W, v.H]);
  G.dev.queue.submit([enc.finish()]);
  await buf.mapAsync(GPUMapMode.READ);
  const src = new Uint8Array(buf.getMappedRange()), out = new Uint8Array(v.W * v.H * 4);
  for (let y = 0; y < v.H; y++) out.set(src.subarray(y * bpr, y * bpr + v.W * 4), y * v.W * 4);
  buf.unmap(); buf.destroy(); tex.destroy();
  return out;
}

// ---- the interactive view -------------------------------------------------------------------------------------------
function modes() { return S.scene.state_machine && S.scene.state_machine.modes ? S.scene.state_machine.modes : null; }
let player = null;
function currentFrame() {
  const ms = modes();
  if (ms && ms[S.mode]) return player.frame(S.mode, S.t, S.prev);
  const clip = S.scene.mode_clip[S.mode] || S.mode;
  return {clip: D.clips[clip] ? clip : null, clipT: S.t, loop: false, weight: 1};
}
function modeLength() {
  const ms = modes();
  if (ms && ms[S.mode]) return player.length(S.mode);
  const c = D.clips[S.scene.mode_clip[S.mode] || S.mode];
  return c ? c.meta.duration : 0;
}
function viewSpec() {
  const cam = S.scene.camera, [W, H] = S.size;
  let az = cam.game_az, el = cam.game_el, k, origin;
  if (S.cam === "game") {
    k = H * S.zoom / cam.view_height_units;
    origin = [W / 2 + S.pan[0], H * 0.75 + S.pan[1]];
  } else {
    az = S.orbit.az; el = S.orbit.el;
    k = cam.k_1600x900 * S.orbit.scale;
    origin = [W / 2 + S.orbit.pan[0], H * 0.75 + S.orbit.pan[1]];
  }
  const hide = new Set(S.hide);
  if (S.bodyBlack) hide.add("body");
  return {az, el, k, origin, W, H, ss: S.ss, pass: S.pass, glow: S.glow, hide, rig: S.rig,
          bg: S.bg === "checker" ? "checker" : hexLinear(S.bg), yaw: A.facingYaw(S.dir64, cam.yaw0, cam.sign),
          frame: currentFrame(), aniso: S.aniso};
}
let last = performance.now(), frames = 0, fpsT = performance.now();
function tick(now) {
  const dt = (now - last) / 1000;
  last = now;
  if (S.playing && S.mode) {
    const L = modeLength(), m = modes() && modes()[S.mode];
    S.t += dt * S.speed;
    if (L > 0 && S.t > L) S.t = (m && !m.loop) ? L : S.t % L;
    syncTime();
    S.dirty = true;
  }
  if (S.dirty) {
    S.dirty = false;
    const v = viewSpec();
    draw(v, G.ctx.getCurrentTexture().createView(), G.canvasFormat);
    $("camInfo").textContent = `az ${v.az.toFixed(1)}  el ${v.el.toFixed(1)}  k ${v.k.toFixed(3)} px/unit  ` +
      `(CLI --scale ${(v.k / S.scene.camera.k_1600x900).toFixed(3)})  yaw ${v.yaw.toFixed(3)}`;
    frames++;
  }
  if (now - fpsT > 1000) { $("clipInfo").dataset.fps = (frames * 1000 / (now - fpsT)).toFixed(0); frames = 0; fpsT = now; }
  requestAnimationFrame(tick);
}
function syncTime() {
  const L = modeLength();
  $("time").max = Math.max(L, 0.001);
  $("time").value = S.t;
  $("timeV").textContent = S.t.toFixed(3);
  const f = currentFrame();
  const m = modes() && modes()[S.mode];
  $("clipInfo").textContent = `clip ${f.clip || "(rest)"} at ${f.clipT.toFixed(3)} s, ${m ? (m.loop ? "loops" : "plays once") : "no state machine"}, ` +
    `mode length ${L.toFixed(3)} s (${S.timing})` + (f.prevClip ? `, crossfade from ${f.prevClip} w ${f.weight.toFixed(2)}` : "") +
    ($("clipInfo").dataset.fps ? `, ${$("clipInfo").dataset.fps} fps` : "");
}

// gpu.Light.for_class: the light a draw of light class `cls` sees (a unit's draws are class "unit")
function forClass(L, cls) {
  const o = (L.classes || {})[cls];
  if (!o) return L;
  const r = Object.assign({}, L);
  for (const k of ["ambient", "key_dir", "key_col", "env_col"]) if (k in o) r[k] = o[k];
  const g = o.point_gain ?? 1;
  if (g !== 1) r.points = (L.points || []).map(q => Object.assign({}, q, {color: q.color.map(c => c * g)}));
  return r;
}

// ---- rig editing (rig.Rig.as_dict format) ---------------------------------------------------------------------------
const RIG_TRIPS = ["ambient", "key_dir", "key_col", "env_col"], RIG_NUMS = ["glow_gain", "spec_gain", "nrm_green"];
function setRig(d) {
  S.rig = JSON.parse(JSON.stringify(d));
  const box = $("rigFields");
  box.innerHTML = "";
  for (const k of RIG_TRIPS) {
    const lab = document.createElement("label");
    lab.innerHTML = `<span>${k}</span><span class="trip">` + [0, 1, 2].map(i =>
      `<input type="number" step="0.01" data-k="${k}" data-i="${i}" value="${+S.rig.light[k][i].toFixed(6)}">`).join("") + "</span>";
    box.appendChild(lab);
  }
  for (const k of RIG_NUMS) {
    const lab = document.createElement("label");
    lab.innerHTML = `<span>${k}</span><input type="number" step="0.01" data-k="${k}" value="${S.rig.light[k]}">`;
    box.appendChild(lab);
  }
  const ex = document.createElement("label");
  ex.innerHTML = `<span>exposure</span><input type="number" step="0.001" id="rigExp" value="${S.rig.exposure}">`;
  box.appendChild(ex);
  const tn = document.createElement("label");
  tn.innerHTML = `<span>tone</span><select id="rigTone"><option>srgb</option><option>game</option></select>`;
  box.appendChild(tn);
  $("rigTone").value = S.rig.tone;
  box.querySelectorAll("input[data-k]").forEach(inp => inp.addEventListener("input", () => {
    const k = inp.dataset.k, x = parseFloat(inp.value);
    if (!Number.isFinite(x)) return;
    if (inp.dataset.i !== undefined) S.rig.light[k][+inp.dataset.i] = x; else S.rig.light[k] = x;
    S.dirty = true;
  }));
  $("rigExp").addEventListener("input", () => { const x = parseFloat($("rigExp").value); if (Number.isFinite(x)) { S.rig.exposure = x; S.dirty = true; } });
  $("rigTone").addEventListener("change", () => { S.rig.tone = $("rigTone").value; S.dirty = true; });
  $("rigInfo").textContent = `${S.rig.name}: ${(S.rig.unknown || []).length} unknowns, LUT ${S.rig.lut || "none"}`;
  S.dirty = true;
}

// ---- match CLI -------------------------------------------------------------------------------------------------------
async function pngPixels(url) {
  const bmp = await createImageBitmap(await (await fetch(url)).blob(), {premultiplyAlpha: "none", colorSpaceConversion: "none"});
  const c = new OffscreenCanvas(bmp.width, bmp.height), g = c.getContext("2d", {willReadFrequently: true});
  g.drawImage(bmp, 0, 0);
  return {w: bmp.width, h: bmp.height, data: g.getImageData(0, 0, bmp.width, bmp.height).data};
}
function refSpec(a) {
  const [W, H] = a.size.split("x").map(Number);
  const hide = new Set(a.hide || []);
  return {az: a.az, el: a.el, k: S.scene.camera.k_1600x900 * a.scale, origin: a.origin, W, H, ss: a.ss, pass: a.pass_name,
          glow: a.glow, hide, rig: a.rig_dict, bg: (!a.bg || a.bg === "transparent" || a.bg === "none") ? null : hexLinear(a.bg),
          yaw: a.yaw, frame: {clip: a.clip && D.clips[a.clip] ? a.clip : null, clipT: a.time, loop: false, weight: 1},
          aniso: a.aniso || G.matchAniso};
}
function toCanvas(w, h, rgba) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  c.getContext("2d").putImageData(new ImageData(new Uint8ClampedArray(rgba), w, h), 0, 0);
  return c;
}
async function post(name, body) {
  try { await fetch("__result/" + name, {method: "POST", body}); } catch (e) { /* read-only server */ }
}
async function verifyTextures() {
  let ok = 0, bad = 0;
  for (const {tex, t} of TEX) {
    for (let i = 0; i < t.mips.length; i++) {
      const m = t.mips[i], bpr = Math.ceil(m.w * 4 / 256) * 256;
      const buf = G.dev.createBuffer({size: bpr * m.h, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ});
      const enc = G.dev.createCommandEncoder();
      enc.copyTextureToBuffer({texture: tex, mipLevel: i}, {buffer: buf, bytesPerRow: bpr}, [m.w, m.h]);
      G.dev.queue.submit([enc.finish()]);
      await buf.mapAsync(GPUMapMode.READ);
      const src = new Uint8Array(buf.getMappedRange()), px = new Uint8Array(m.w * m.h * 4);
      for (let y = 0; y < m.h; y++) px.set(src.subarray(y * bpr, y * bpr + m.w * 4), y * m.w * 4);
      buf.unmap(); buf.destroy();
      if (await sha256hex(px) === m.sha256) ok++; else { bad++; say("texture mip differs: " + m.file); }
    }
  }
  return {mips: ok + bad, identical: ok, differ: bad};
}
async function matchCli() {
  const box = $("check");
  box.innerHTML = "<p>checking...</p>";
  const res = {shader_sha256: G.shaderSha, shader_same_as_bundle: G.shaderOk, adapter: G.info.description || G.info.vendor,
               textures: await verifyTextures(), refs: []};
  const tbl = document.createElement("table");
  tbl.innerHTML = "<tr><th>ref</th><th>pass</th><th>dir64</th><th>size</th><th>aniso</th><th>max diff</th><th>channels &gt;1</th><th>mean</th><th>CLI</th><th>page</th><th>|diff| x16</th></tr>";
  for (const r of S.scene.refs) {
    const v = refSpec(r.args);
    const mine = await readRGBA(v);
    const ref = await pngPixels(BUNDLE + r.png);
    let mx = 0, over = 0, sum = 0;
    const diff = new Uint8Array(mine.length);
    for (let i = 0; i < mine.length; i++) {
      const d = Math.abs(mine[i] - ref.data[i]);
      if (d > mx) mx = d;
      if (d > 1) over++;
      sum += d;
      diff[i] = (i % 4 === 3) ? 255 : Math.min(255, d * 16);
    }
    const e = {id: r.id, pass: v.pass, dir64: r.args.dir64, size: r.args.size, aniso: v.aniso, max_diff: mx, channels_over_1: over,
               mean_diff: +(sum / mine.length).toFixed(5), channels: mine.length};
    res.refs.push(e);
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${e.id}</td><td>${e.pass}</td><td>${e.dir64}</td><td>${e.size}</td><td>${e.aniso}</td><td class="${mx <= 1 ? "ok" : "bad"}">${mx}</td><td>${over}</td><td>${e.mean_diff}</td><td></td><td></td><td></td>`;
    const cv = [toCanvas(v.W, v.H, ref.data), toCanvas(v.W, v.H, mine), toCanvas(v.W, v.H, diff)];
    cv.forEach((c, i) => tr.children[8 + i].appendChild(c));
    tbl.appendChild(tr);
    if (Q.get("auto")) {
      await post(r.id + "_page.png", await new Promise(ok => cv[1].toBlob(ok, "image/png")));
      await post(r.id + "_diff.png", await new Promise(ok => cv[2].toBlob(ok, "image/png")));
    }
  }
  res.max_diff = Math.max(...res.refs.map(e => e.max_diff));
  box.innerHTML = `<p>shader: <b class="${G.shaderOk ? "ok" : "bad"}">${G.shaderOk ? "same file as the CLI" : "differs"}</b>; ` +
    `texture mips identical: <b class="${res.textures.differ ? "bad" : "ok"}">${res.textures.identical}/${res.textures.mips}</b>; ` +
    `max pixel difference over ${res.refs.length} stills: <b class="${res.max_diff <= 1 ? "ok" : "bad"}">${res.max_diff}</b>/255</p>`;
  box.appendChild(tbl);
  say("match CLI: max diff " + res.max_diff + ", textures " + res.textures.identical + "/" + res.textures.mips);
  S.dirty = true;
  return res;
}

// ---- UI wiring ---------------------------------------------------------------------------------------------------------
function setCam(c) {
  S.cam = c;
  $("camGame").classList.toggle("on", c === "game");
  $("camOrbit").classList.toggle("on", c === "orbit");
  S.dirty = true;
}
function setMode(tok) {
  if (S.mode && S.mode !== tok && modes()) S.prev = {tok: S.mode, left: S.t};
  else S.prev = null;
  S.mode = tok; S.t = 0;
  $("mode").value = tok;
  syncTime();
  S.dirty = true;
}
function setDir(d) {
  S.dir64 = ((d % 64) + 64) % 64;
  $("dir64").value = S.dir64; $("dir64V").textContent = S.dir64;
  document.querySelectorAll("#keys button").forEach((b, i) => b.classList.toggle("on", i * 8 === S.dir64));
  S.dirty = true;
}
function wire() {
  const sc = S.scene;
  $("camGame").onclick = () => setCam("game");
  $("camOrbit").onclick = () => setCam("orbit");
  $("camReset").onclick = () => { S.zoom = 1; S.pan = [0, 0]; S.orbit = {az: 45, el: 30, scale: 1, pan: [0, 0]}; $("zoom").value = 1; $("zoomV").textContent = "1.00"; S.dirty = true; };
  $("zoom").oninput = () => { S.zoom = +$("zoom").value; $("zoomV").textContent = S.zoom.toFixed(2); S.dirty = true; };
  $("size").onchange = () => { S.size = $("size").value.split("x").map(Number); $("cv").width = S.size[0]; $("cv").height = S.size[1]; S.dirty = true; };
  $("aniso").onchange = () => { S.aniso = +$("aniso").value; S.dirty = true; };
  $("ss").onchange = () => { S.ss = +$("ss").value; S.dirty = true; };
  for (let k = 0; k < 8; k++) {
    const b = document.createElement("button");
    b.textContent = k; b.title = "facing key " + k + " = dir64 " + k * 8;
    b.onclick = () => setDir(k * 8);
    $("keys").appendChild(b);
  }
  $("dir64").oninput = () => setDir(+$("dir64").value);
  const ms = modes();
  const toks = ms ? Object.keys(ms).filter(t => D.clips[ms[t].clip]) : Object.keys(sc.mode_clip).filter(t => D.clips[sc.mode_clip[t]]);
  for (const t of toks) {
    const o = document.createElement("option");
    o.value = t; o.textContent = t + " - " + (ms ? ms[t].clip : sc.mode_clip[t]) + (ms ? (ms[t].loop ? " (loop)" : "") : "");
    $("mode").appendChild(o);
  }
  $("mode").onchange = () => setMode($("mode").value);
  $("play").onclick = () => { S.playing = !S.playing; $("play").textContent = S.playing ? "Pause" : "Play"; $("play").classList.toggle("on", S.playing); };
  $("speed").onchange = () => { S.speed = +$("speed").value; };
  $("timing").onchange = () => { S.timing = $("timing").value; player.timing = S.timing; syncTime(); S.dirty = true; };
  $("time").oninput = () => { S.t = +$("time").value; S.prev = null; syncTime(); S.dirty = true; };
  $("pass").onchange = () => { S.pass = $("pass").value; S.dirty = true; };
  $("bg").onchange = () => { S.bg = $("bg").value; S.dirty = true; };
  $("glow").onchange = () => { S.glow = $("glow").checked; S.dirty = true; };
  $("bodyBlack").onchange = () => { S.bodyBlack = $("bodyBlack").checked; S.dirty = true; };
  const lt = $("layerToggles");
  const items = [];
  for (const p of sc.parts) {
    items.push(["part:" + p.name, "part " + p.name]);
    for (const m of p.meshes) items.push(["mesh:" + m.name, "mesh " + m.name]);
    for (const L of p.layers) items.push(["layer:" + L.name, "layer " + L.name]);
  }
  for (const [key, label] of items) {
    const l = document.createElement("label");
    l.innerHTML = `<input type="checkbox" checked> ${label}`;
    l.firstChild.onchange = e => { if (e.target.checked) S.hide.delete(key); else S.hide.add(key); S.dirty = true; };
    lt.appendChild(l);
  }
  for (const name of Object.keys(sc.rigs)) {
    const o = document.createElement("option"); o.textContent = name; $("rigPreset").appendChild(o);
  }
  $("rigPreset").onchange = () => setRig(sc.rigs[$("rigPreset").value]);
  $("rigLoadBtn").onclick = () => $("rigFile").click();
  $("rigFile").onchange = async () => {
    const f = $("rigFile").files[0];
    if (!f) return;
    const d = JSON.parse(await f.text());
    const base = JSON.parse(JSON.stringify(sc.rigs.default));
    d.light = Object.assign(base.light, d.light || {});
    setRig(Object.assign(base, d));
    say("rig loaded from " + f.name);
  };
  $("rigSave").onclick = () => {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([JSON.stringify(S.rig, null, 1) + "\n"], {type: "application/json"}));
    a.download = (S.rig.name || "rig") + ".json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  $("match").onclick = () => matchCli().catch(e => say("check failed: " + e.message));
  // mouse: orbit drag / wheel zoom / shift-drag pan
  const cv = $("cv");
  let drag = null;
  cv.onpointerdown = e => { drag = {x: e.clientX, y: e.clientY, shift: e.shiftKey}; cv.setPointerCapture(e.pointerId); };
  cv.onpointerup = () => { drag = null; };
  cv.onpointermove = e => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    drag.x = e.clientX; drag.y = e.clientY;
    const pan = S.cam === "game" ? S.pan : S.orbit.pan;
    if (drag.shift || S.cam === "game") { pan[0] += dx; pan[1] += dy; }
    else { S.orbit.az -= dx * 0.4; S.orbit.el = Math.max(-89, Math.min(89, S.orbit.el + dy * 0.4)); }
    S.dirty = true;
  };
  cv.onwheel = e => {
    e.preventDefault();
    if (S.cam === "game") { S.zoom = Math.max(1, Math.min(2.25, S.zoom - Math.sign(e.deltaY) * 0.05)); $("zoom").value = S.zoom; $("zoomV").textContent = S.zoom.toFixed(2); }
    else S.orbit.scale *= Math.exp(-Math.sign(e.deltaY) * 0.1);
    S.dirty = true;
  };
}

// ---- start ---------------------------------------------------------------------------------------------------------------
async function main() {
  const sc = await (await fetch(BUNDLE + "scene.json")).json();
  S.scene = sc;
  document.title = "hdkit viewer: " + sc.name;
  say(`bundle ${sc.name} (${sc.asset}), ${(sc.bytes / 1048576).toFixed(1)} MB, ${Object.keys(sc.clips).length} clips, ${sc.refs.length} CLI stills`);
  await initGpu(sc);
  await loadScene(sc);
  player = new A.Player(sc.state_machine && sc.state_machine.modes ? sc.state_machine : null, Object.fromEntries(
    Object.entries(D.clips).map(([k, c]) => [k, c.meta])), S.timing);
  S.aniso = G.viewAniso;
  const fo = $("aniso");
  fo.innerHTML = [...new Set([G.viewAniso, G.matchAniso])].map(a =>
    `<option value="${a}">${a}${a === G.matchAniso ? " (matched, as Match CLI)" : " (view)"}</option>`).join("");
  fo.value = S.aniso;
  wire();
  setRig(sc.rigs[Q.get("rig") || "game"] || Object.values(sc.rigs)[0]);
  $("rigPreset").value = S.rig.name;
  for (const [k, v] of Q) {     // ?pass=normals&dir64=24&mode=a1&t=0.3&cam=orbit&az=..&el=..&zoom=..&ss=..&bg=..&play=1
    if (k === "pass") { S.pass = v; $("pass").value = v; }
    if (k === "ss") { S.ss = +v; $("ss").value = v; }
    if (k === "aniso") { S.aniso = +v; $("aniso").value = v; }
    if (k === "bg") { S.bg = v; }
    if (k === "zoom") { S.zoom = +v; $("zoom").value = v; $("zoomV").textContent = (+v).toFixed(2); }
    if (k === "cam") setCam(v);
    if (k === "az") S.orbit.az = +v;
    if (k === "el") S.orbit.el = +v;
    if (k === "scale") S.orbit.scale = +v;
  }
  setDir(+(Q.get("dir64") || 0));
  const toks = [...$("mode").options].map(o => o.value);
  setMode(Q.get("mode") && toks.includes(Q.get("mode")) ? Q.get("mode") : (toks.includes("nu") ? "nu" : toks[0]));
  if (Q.get("t")) { S.t = +Q.get("t"); syncTime(); }
  if (Q.get("play")) $("play").click();
  requestAnimationFrame(tick);
  say("ready");
  if (Q.get("auto") === "check") {
    const res = await matchCli();
    await post("check.json", JSON.stringify(res, null, 1));
  }
  if (Q.get("auto")) {
    await new Promise(r => setTimeout(r, 400));
    document.body.dataset.ready = "1";
    await post("ready.json", JSON.stringify({ready: true, status}));
  }
}
main().catch(e => { say("error: " + e.message); console.error(e); post("error.json", JSON.stringify({error: String(e), stack: e.stack, status})); });
