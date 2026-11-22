// hdkit.view browser page: the CPU step of the CLI after the GPU draw, as a shader. Not a model shader: the unit is
// drawn by ../shaders.wgsl, the CLI's own file. This pass does what gpu.render does on the CPU after the MSAA resolve:
//   box_down(out, ss)                        the ss x ss box filter of the supersampled, resolved linear image
//   to_uint8(lin, pass, bg, rig.encode)      straight alpha or compositing over bg; the rig's exposure and tone on the lit
//                                            and glow passes (rig.Rig.encode: plain sRGB, or tone.apply through the
//                                            luminance table tone._XS / tone._YS exported to the bundle's tone.bin)
// The 8-bit rounding is the render target's (rgba8unorm).

struct P {
  a: vec4<f32>,    // x: ss, y: mode (0 rig encode, 1 sRGB encode, 2 clip only), z: tone (0 srgb, 1 game), w: exposure
  bg: vec4<f32>,   // rgb: linear background, w: 0 straight alpha, 1 composite over rgb, 2 display over a checker
  n: vec4<f32>,    // x: table length
};

@group(0) @binding(0) var<uniform> p: P;
@group(0) @binding(1) var src: texture_2d<f32>;
@group(0) @binding(2) var<storage, read> xs: array<f32>;
@group(0) @binding(3) var<storage, read> ys: array<f32>;

@vertex
fn vs_full(@builtin(vertex_index) i: u32) -> @builtin(position) vec4<f32> {
  var q = array<vec2<f32>, 3>(vec2(-1.0, -1.0), vec2(3.0, -1.0), vec2(-1.0, 3.0));
  return vec4<f32>(q[i], 0.0, 1.0);
}

fn enc1(x: f32) -> f32 {
  let c = clamp(x, 0.0, 1.0);
  return select(1.055 * pow(c, 1.0 / 2.4) - 0.055, 12.92 * c, c <= 0.0031308);
}
fn srgb_encode(v: vec3<f32>) -> vec3<f32> { return vec3<f32>(enc1(v.x), enc1(v.y), enc1(v.z)); }
fn dec1(x: f32) -> f32 { return select(pow((x + 0.055) / 1.055, 2.4), x / 12.92, x <= 0.04045); }
fn srgb_decode(v: vec3<f32>) -> vec3<f32> { return vec3<f32>(dec1(v.x), dec1(v.y), dec1(v.z)); }

// numpy.interp(y, xs, ys) for increasing xs
fn interp(y: f32) -> f32 {
  let n = u32(p.n.x);
  if (y <= xs[0]) { return ys[0]; }
  if (y >= xs[n - 1u]) { return ys[n - 1u]; }
  var lo = 0u;
  var hi = n - 1u;
  loop {
    if (hi - lo <= 1u) { break; }
    let mid = (lo + hi) / 2u;
    if (xs[mid] <= y) { lo = mid; } else { hi = mid; }
  }
  let f = (y - xs[lo]) / (xs[hi] - xs[lo]);
  return ys[lo] + f * (ys[hi] - ys[lo]);
}

fn tone_game(rgb: vec3<f32>, exposure: f32) -> vec3<f32> {
  let c = max(rgb * exposure, vec3<f32>(0.0));
  let y = dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
  let d = interp(y);
  let yl = dec1(clamp(d, 0.0, 1.0));
  let k = select(0.0, yl / max(y, 1e-9), y > 1e-9);
  return srgb_encode(clamp(c * k, vec3<f32>(0.0), vec3<f32>(1.0)));
}

@fragment
fn fs_present(@builtin(position) pos: vec4<f32>) -> @location(0) vec4<f32> {
  let ss = i32(p.a.x + 0.5);
  let xy = vec2<i32>(floor(pos.xy)) * ss;
  var sum = vec4<f32>(0.0);
  for (var j = 0; j < ss; j++) {
    for (var i = 0; i < ss; i++) {
      sum += textureLoad(src, xy + vec2<i32>(i, j), 0);
    }
  }
  let lin = sum / f32(ss * ss);
  let c = lin.rgb;
  let a = clamp(lin.a, 0.0, 1.0);
  let straight = select(vec3<f32>(0.0), c / max(a, 1e-6), a > 1e-6);
  let mode = i32(p.a.y + 0.5);
  var bgl = p.bg.rgb;
  let bgm = i32(p.bg.w + 0.5);
  if (bgm == 2) {
    let ch = (i32(floor(pos.x / 8.0)) + i32(floor(pos.y / 8.0))) % 2;
    bgl = srgb_decode(vec3<f32>(select(0.16, 0.22, ch == 0)));
  }
  if (mode == 0) {
    var disp: vec3<f32>;
    if (i32(p.a.z + 0.5) == 1) { disp = tone_game(straight, p.a.w); } else { disp = srgb_encode(straight * p.a.w); }
    disp = clamp(disp, vec3<f32>(0.0), vec3<f32>(1.0));
    if (bgm == 0) { return vec4<f32>(disp, a); }
    return vec4<f32>(srgb_encode(srgb_decode(disp) * a + bgl * (1.0 - a)), 1.0);
  }
  if (bgm == 0) {
    if (mode == 1) { return vec4<f32>(srgb_encode(straight), a); }
    return vec4<f32>(clamp(straight, vec3<f32>(0.0), vec3<f32>(1.0)), a);
  }
  let comp = c + bgl * (1.0 - a);
  if (mode == 1) { return vec4<f32>(srgb_encode(comp), 1.0); }
  return vec4<f32>(clamp(comp, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
