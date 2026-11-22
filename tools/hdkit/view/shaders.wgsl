// hdkit.view: one shader set for the offline renderer (and later the browser page).
// Vertices come posed and skinned in world space (CPU). Colour targets are linear rgba16float, premultiplied alpha;
// the CPU encodes sRGB after the MSAA resolve.
//
// Lit model (uncalibrated, monster3d METHOD rules 1, 10, 13, 15): albedo (sRGB texture), stock D2R normal map (DXT5nm:
// x in alpha, y in green), ORM (R occlusion, G roughness, B metal, A specular level). Diffuse = albedo (1 - metal)
// (ambient * occlusion + key * N.L); specular = GGX key highlight + a rough Fresnel term of the environment colour, F0 =
// mix(0.08 * specular level, albedo, metal), so a black dielectric still reflects about 4 % (rule 15) and ORM A = 0 is matte
// (rule 10). The floor at y = 0 hides what lies below it (rule 3).
// Local point lights (up to MAX_POINTS; diffuse only, as the game's map lights carry specularContribution 0): colour x
// power x f(d) x N.L with f(d) = (1 - (d / radius)^2)^attenuation inside the radius (form fitted to the player's light pool
// on the ground of game shots, viewer/p5), world units.
// Depth fog (the vis file's depthFogColor and depthFogDensity, rig.from_vis): lit colour x (1 - f) + fog rgb, with
// fog.rgb = colour x f and f = density, the same over a unit (orthographic camera). It is the floor a black albedo
// still shows in game (monster3d METHOD rule 13). 0 = off.

struct U {
  mvp: mat4x4<f32>,
  view_dir: vec4<f32>,     // xyz: towards the camera
  ambient: vec4<f32>,      // rgb
  key_dir: vec4<f32>,      // xyz: towards the key light
  key_col: vec4<f32>,      // rgb
  env_col: vec4<f32>,      // rgb
  p0: vec4<f32>,           // x: pass (0 lit, 1 albedo, 2 normals, 3 depth, 4 wire, 5 unlit, 6 glow alone, 7-10 ORM r/g/b/a), y: glow gain, z: normal-map green sign, w: alpha cut
  p1: vec4<f32>,           // x: depth of the far end, y: depth of the near end, z: floor clip (1 on), w: specular gain
  p2: vec4<f32>,           // x: number of point lights, y: emissive gain (x mask r x albedo), z: blend (alpha x z; 0 = opaque)
  pts: array<vec4<f32>, 64>,   // per light i: [2i] xyz position, w radius; [2i+1] rgb colour x power, w attenuation
  fog: vec4<f32>,          // rgb: fog colour x f (added), w: f (the lit colour's share lost to fog)
  p3: vec4<f32>,           // terrain: xy world (x, z) of the weight map's corner, zw its size in world units
  p4: vec4<f32>,           // terrain: x world units per layer texture repeat, y number of layers, z height-blend sharpness
};

@group(0) @binding(0) var<uniform> u: U;
@group(0) @binding(1) var samp: sampler;
@group(0) @binding(2) var t_alb: texture_2d<f32>;
@group(0) @binding(3) var t_nrm: texture_2d<f32>;
@group(0) @binding(4) var t_orm: texture_2d<f32>;
@group(0) @binding(5) var t_mask: texture_2d<f32>;
@group(0) @binding(6) var t_strip: texture_2d<f32>;

struct VIn {
  @location(0) pos: vec3<f32>,
  @location(1) nrm: vec3<f32>,
  @location(2) tan: vec4<f32>,
  @location(3) uv: vec2<f32>,
  @location(4) bary: vec3<f32>,
};

struct VOut {
  @builtin(position) clip: vec4<f32>,
  @location(0) wpos: vec3<f32>,
  @location(1) nrm: vec3<f32>,
  @location(2) tan: vec4<f32>,
  @location(3) uv: vec2<f32>,
  @location(4) bary: vec3<f32>,
};

@vertex
fn vs(v: VIn) -> VOut {
  var o: VOut;
  o.clip = u.mvp * vec4<f32>(v.pos, 1.0);
  o.wpos = v.pos;
  o.nrm = v.nrm;
  o.tan = v.tan;
  o.uv = v.uv;
  o.bary = v.bary;
  return o;
}

const PI: f32 = 3.14159265;

fn shading_normal(i: VOut, front: bool, s: vec4<f32>) -> vec3<f32> {
  var ng = normalize(i.nrm);
  if (!front) { ng = -ng; }
  let t = i.tan.xyz - ng * dot(ng, i.tan.xyz);
  if (dot(t, t) < 1e-8) { return ng; }
  let tn = normalize(t);
  let bn = cross(ng, tn) * select(1.0, -1.0, i.tan.w < 0.0);
  let x = s.a * 2.0 - 1.0;
  let y = (s.g * 2.0 - 1.0) * u.p0.z;
  let z = sqrt(max(0.0, 1.0 - x * x - y * y));
  return normalize(tn * x + bn * y + ng * z);
}

fn ggx(n: vec3<f32>, v: vec3<f32>, l: vec3<f32>, rough: f32, f0: vec3<f32>) -> vec3<f32> {
  let h = normalize(v + l);
  let nl = max(dot(n, l), 0.0);
  let nv = max(dot(n, v), 1e-4);
  let nh = max(dot(n, h), 0.0);
  let a = max(rough * rough, 0.02);
  let a2 = a * a;
  let d = a2 / (PI * pow(nh * nh * (a2 - 1.0) + 1.0, 2.0));
  let k = a / 2.0;
  let g = (nl / (nl * (1.0 - k) + k)) * (nv / (nv * (1.0 - k) + k));
  let f = f0 + (vec3<f32>(1.0) - f0) * pow(1.0 - max(dot(h, v), 0.0), 5.0);
  return d * g * f / max(4.0 * nl * nv, 1e-4) * nl;
}

@fragment
fn fs_main(i: VOut, @builtin(front_facing) front: bool) -> @location(0) vec4<f32> {
  // every sample and derivative first: they need uniform control flow
  let alb = textureSample(t_alb, samp, i.uv);
  let nmap = textureSample(t_nrm, samp, i.uv);
  let orm = textureSample(t_orm, samp, i.uv);
  let emask = textureSample(t_mask, samp, i.uv).r;
  let w = fwidth(i.bary);
  if (u.p1.z > 0.5 && i.wpos.y < 0.0) { discard; }
  if (alb.a < u.p0.w) { discard; }
  let pass_id = i32(u.p0.x + 0.5);
  if (pass_id == 11) { return vec4<f32>(vec3<f32>(clamp(i.wpos.y / 20.0, 0.0, 1.0)), 1.0); }   // height above the ground
  if (pass_id == 1 || pass_id == 5) { return vec4<f32>(alb.rgb, 1.0); }
  if (pass_id == 6) { return vec4<f32>(0.0, 0.0, 0.0, 1.0); }      // glow alone: the body is black but still hides
  if (pass_id >= 7 && pass_id <= 10) {                               // one ORM channel as grey (data, not colour)
    var ch = array<f32, 4>(orm.r, orm.g, orm.b, orm.a);
    return vec4<f32>(vec3<f32>(ch[pass_id - 7]), 1.0);
  }
  let n = shading_normal(i, front, nmap);
  if (pass_id == 2) { return vec4<f32>(n * 0.5 + vec3<f32>(0.5), 1.0); }
  if (pass_id == 3) {
    let d = (dot(i.wpos, u.view_dir.xyz) - u.p1.x) / max(u.p1.y - u.p1.x, 1e-6);
    return vec4<f32>(vec3<f32>(clamp(d, 0.0, 1.0)), 1.0);
  }
  if (pass_id == 4) {
    let e = smoothstep(vec3<f32>(0.0), w * 1.2, i.bary);
    let edge = 1.0 - min(min(e.x, e.y), e.z);
    return vec4<f32>(mix(alb.rgb * 0.35, vec3<f32>(1.0, 0.85, 0.2), edge), 1.0);
  }
  let ao = orm.r;
  let rough = clamp(orm.g, 0.04, 1.0);
  let metal = orm.b;
  let spec_level = orm.a;
  let v = normalize(u.view_dir.xyz);
  let l = normalize(u.key_dir.xyz);
  let nl = max(dot(n, l), 0.0);
  let f0 = mix(vec3<f32>(0.08 * spec_level), alb.rgb, metal);
  var local = vec3<f32>(0.0);
  let npt = i32(u.p2.x + 0.5);
  for (var k = 0; k < npt; k = k + 1) {
    let a = u.pts[2 * k];
    let b = u.pts[2 * k + 1];
    let dv = a.xyz - i.wpos;
    let d = length(dv);
    let q = clamp(1.0 - (d * d) / max(a.w * a.w, 1e-6), 0.0, 1.0);
    local = local + b.rgb * pow(q, b.w) * max(dot(n, dv / max(d, 1e-4)), 0.0);
  }
  let diffuse = alb.rgb * (1.0 - metal) * (u.ambient.rgb * ao + u.key_col.rgb * nl + local);
  let spec_key = ggx(n, v, l, rough, f0) * u.key_col.rgb * u.p1.w;
  let nv = max(dot(n, v), 0.0);
  let fr = f0 + (max(vec3<f32>(1.0 - rough), f0) - f0) * pow(1.0 - nv, 5.0);
  let env = fr * u.env_col.rgb * ao;
  let emis = alb.rgb * emask * u.p2.y;
  let col = (diffuse + spec_key + env + emis) * (1.0 - u.fog.w) + u.fog.rgb;
  if (u.p2.z > 0.0) {                     // alpha-blended material (AlphaIntensity): premultiplied
    let a = clamp(alb.a * u.p2.z, 0.0, 1.0);
    return vec4<f32>(col * a, a);
  }
  return vec4<f32>(col, 1.0);
}

// The ground: a splat of up to 16 terrain layers (texture arrays), weights from a map over the level in world (x, z)
// (4 rgba layers = 16 weights), each layer's albedo alpha used as its height for the blend (D2R's height blend,
// approximated: weight x (height + 0.5)^sharpness). Lit like fs_main.
@group(0) @binding(7) var t_lalb: texture_2d_array<f32>;
@group(0) @binding(8) var t_lnrm: texture_2d_array<f32>;
@group(0) @binding(9) var t_lorm: texture_2d_array<f32>;
@group(0) @binding(10) var t_wts: texture_2d_array<f32>;

@fragment
fn fs_terrain(i: VOut, @builtin(front_facing) front: bool) -> @location(0) vec4<f32> {
  let wuv = (i.wpos.xz - u.p3.xy) / u.p3.zw;
  let luv = i.wpos.xz / u.p4.x;
  let dx = dpdx(luv);
  let dy = dpdy(luv);
  var w: array<f32, 16>;
  for (var q = 0; q < 4; q = q + 1) {
    let s = textureSampleLevel(t_wts, samp, wuv, q, 0.0);
    w[4 * q] = s.r; w[4 * q + 1] = s.g; w[4 * q + 2] = s.b; w[4 * q + 3] = s.a;
  }
  let nl_ = i32(u.p4.y + 0.5);
  var alb = vec3<f32>(0.0);
  var nm = vec4<f32>(0.0);
  var orm = vec4<f32>(0.0);
  var tot = 0.0;
  for (var k = 0; k < nl_; k = k + 1) {
    if (w[k] < 0.004) { continue; }
    let a = textureSampleGrad(t_lalb, samp, luv, k, dx, dy);
    let hw = w[k] * pow(a.a + 0.5, u.p4.z);
    alb = alb + a.rgb * hw;
    nm = nm + textureSampleGrad(t_lnrm, samp, luv, k, dx, dy) * hw;
    orm = orm + textureSampleGrad(t_lorm, samp, luv, k, dx, dy) * hw;
    tot = tot + hw;
  }
  if (tot <= 0.0) { discard; }
  alb = alb / tot; nm = nm / tot; orm = orm / tot;
  let pass_id = i32(u.p0.x + 0.5);
  if (pass_id == 11) { return vec4<f32>(vec3<f32>(clamp(i.wpos.y / 20.0, 0.0, 1.0)), 1.0); }
  if (pass_id == 1 || pass_id == 5) { return vec4<f32>(alb, 1.0); }
  let n = shading_normal(i, front, nm);
  if (pass_id == 2) { return vec4<f32>(n * 0.5 + vec3<f32>(0.5), 1.0); }
  let ao = orm.r;
  let rough = clamp(orm.g, 0.04, 1.0);
  let v = normalize(u.view_dir.xyz);
  let l = normalize(u.key_dir.xyz);
  let nl = max(dot(n, l), 0.0);
  let f0 = vec3<f32>(0.08 * orm.a);
  var local = vec3<f32>(0.0);
  let npt = i32(u.p2.x + 0.5);
  for (var k = 0; k < npt; k = k + 1) {
    let a = u.pts[2 * k];
    let b = u.pts[2 * k + 1];
    let dv = a.xyz - i.wpos;
    let d = length(dv);
    let q = clamp(1.0 - (d * d) / max(a.w * a.w, 1e-6), 0.0, 1.0);
    local = local + b.rgb * pow(q, b.w) * max(dot(n, dv / max(d, 1e-4)), 0.0);
  }
  let diffuse = alb * (u.ambient.rgb * ao + u.key_col.rgb * nl + local);
  let spec_key = ggx(n, v, l, rough, f0) * u.key_col.rgb * u.p1.w;
  let nv = max(dot(n, v), 0.0);
  let fr = f0 + (max(vec3<f32>(1.0 - rough), f0) - f0) * pow(1.0 - nv, 5.0);
  let env = fr * u.env_col.rgb * ao;
  return vec4<f32>((diffuse + spec_key + env) * (1.0 - u.fog.w) + u.fog.rgb, 1.0);
}

// The self-lit layer: the same skinned model again, additive, mask (one channel, model UVs) times its gradient strip.
// Alpha 0: the layer adds light, not coverage.
@fragment
fn fs_glow(i: VOut) -> @location(0) vec4<f32> {
  let m = textureSample(t_mask, samp, i.uv).r;
  let c = textureSample(t_strip, samp, vec2<f32>(clamp(m, 0.002, 0.998), 0.5)).rgb;
  if (u.p1.z > 0.5 && i.wpos.y < 0.0) { discard; }
  return vec4<f32>(c * m * u.p0.y, 0.0);
}
