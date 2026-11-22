"""Stage 5c: a self-lit (emissive) layer for an HD unit of s5_build.py, made from D2R's own object effect.

  venv python s5_glow.py [--token T] <overlay dir> <albedo.png> <albedo_relit.png> <part.png> [--report <json>]
        [--cap 1.0] [--body 0.45] [--body-base 0.35] [--cap-rgb 70,150,255] [--body-rgb 190,215,255] [--die-fade]
        [--mask level|sprite] [--cap-lo 40] [--cap-hi 220] [--body-lo 110] [--body-hi 230] [--vfx-parts body,cap]
        [--cap-pale 0..1]  (sprite mask: pale-white cap texels glow too, so classic's white rim specks stay bright)
        [--strip F]   (the same F as s5_build.py --strip: the input maps are squeezed into its atlas layout, no glow in the strip)
        [--cap-gamma G] (cap mask ^ G, normalised by --cap: a sharper mask, the band's weak glow falls off)
        [--cap-speck K,SIGMA] (the albedo's positive luminance high-pass, times K, added on the cap: specks glow above the band)
        [--cap-ring <cap_radius.png>,R0,R1] (s3_tone.py's radius map: no cap glow inside R0, full from R1: a dark centre)
        [--mask-size 1024] (2048 keeps texel-sized specks one mip longer)

Why: D2R's character material (VariantMaterial, every monster's) is lit only by the scene. It has an EmissiveIntensity value,
but that does nothing in game (lane hdtools-monster, run upC), and it has no emissive map. Monsters that glow in D2R (Fire Golem,
Finger Mage, Wraith, Will o' Wisp) draw the glow with an ObjectEffectDefinitionComponent: a PopcornFX mesh layer with the
material `Diablo_Uber_Mesh.pkma` and `ModelInstanceTracking`, which draws the entity's own skinned model a second time,
additive, through the layer's textures. The Fire Golem's (`vfx_firegolem_objFX.particles`, on an entity of its own with its
own shell model) takes its shape from `AlphaMask.Mask`, a mask in the MODEL's UV layout (`T_FX_FireGolem_ShellMask_B`).
That is an emissive map in all but name.

What it does, per glowing part (the cap rim and the body):
- a mask in the unit's UV atlas (BC4, 1024^2): cap = cap texels (part.png) by the blue of the projected sprite colours, so the
  dark centre stays dark and the bright blue rim and specks glow; body = body texels by the relit luminance on a base level;
- a colour strip (RGBA8 256 x 16, one colour) for `GradientRemap.GradientMap`;
- a copy of the Fire Golem's object effect: Blend textures -> D2R's White.texture, AlphaMask -> the part's mask,
  GradientRemap -> the strip; UVDistortion and AlphaRemap (the flame wobble and the dissolve curve) switched off; its scripts'
  four UV transforms (scale 2.5 / 2, random offsets, scroll) made identity, so the mask stays on the model's own UVs. Without --die-fade the layer's MonsterFade feature is switched off and its scripts' fade-out
  on death (rate 3.33/s, constant c13 of the evolve scripts) is set to 0, the script's kill call gets false and its
  isRenderingEnabled true, so the corpse keeps its glow as classic's corpse
  does (the DD frames are pale blue-white);
- an entity per part in the unit JSON: the unit's own torso.model + the ObjectEffectDefinitionComponent (Fire Golem's pattern),
  and the files in the unit's dependencies.
--mask sprite (instead of the default `level`): the masks follow the projected sprite colours texel by texel, so the pattern
is classic's own and nothing is invented: cap = cap texels by their luminance between --cap-lo and --cap-hi, on blue or pale
texels only (B - R from 10 to 60), so classic's speckled rim (bright specks in a blue band, darker toward the dark centre)
keeps its specks and its inward fade; body = only the pale blue highlights of the sprite (luminance --body-lo..--body-hi,
B >= R) on --body-base. `level` (round 3) is the smoothstep of the blue alone: a flat, even band.
--vfx-parts: those parts carry the layer in a VfxDefinitionComponent instead of an ObjectEffectDefinitionComponent (both on an
entity with the unit's torso.model). The engine ends an object effect when its unit becomes a corpse.
Writes the files into the overlay (hd/vfx/particles/mxl/m3d/<name>/, hd/vfx/textures/mxl/m3d/<name>/) and a report.
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage as nd
from PIL import Image

import common

sys.path.insert(0, str(common.WT / "tools"))
import d2r_texture  # noqa: E402
import hd_cbvm  # noqa: E402
import hd_particles as hp  # noqa: E402

SRC = common.EV / "d2r" / "data" / "hd/vfx/particles/character/enemy/firegolem/vfx_firegolem_objfx.particles"
WHITE = "data/hd/vfx/textures/default/White.texture"
OFF_FEATURES = ("UVDistortion", "AlphaRemap")
FADE = 10.0 / 3.0          # the death fade-out rate of the Fire Golem's evolve scripts
# the evolve scripts' UV scale and scroll constants (four UVScaleAndOffset streams: scale 2.5/2, scroll 0.1-0.65 per s):
# identity, so the mask sits in the model's own UV layout and does not move
UV_CONSTS = {2.5: 1.0, 2.0: 1.0, 0.2: 0.0, 0.65: 0.0, -0.2: 0.0, 0.25: 0.0, 0.1: 0.0, -0.5: 0.0}


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def lum(c):
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def masks_sprite(albedo, part, cap_k, body_k, body_base, cap_lo, cap_hi, body_lo, body_hi, cap_pale=0.0):
    """Masks that follow the sprite's own colours (see --mask sprite)."""
    a = albedo.astype(np.float32)
    cap = part > 127
    L = lum(a)
    cool = smoothstep(10, 60, a[..., 2] - a[..., 0])
    if cap_pale:   # classic's pale-white rim specks are not "cool" (B - R small): let them glow too, or the rim glows as an even band
        cool = np.maximum(cool, cap_pale * smoothstep(150, 220, L))
    m_cap = np.where(cap, np.clip(cap_k * np.clip((L - cap_lo) / (cap_hi - cap_lo), 0, 1) * cool, 0, 1), 0)
    pale = smoothstep(body_lo, body_hi, L) * (a[..., 2] >= a[..., 0])
    m_body = np.where(~cap, np.clip(body_k * (body_base + (1 - body_base) * pale), 0, 1), 0)
    return m_cap, m_body


def masks(albedo, relit, part, cap_k, body_k, body_base):
    a = albedo.astype(np.float32)
    cap = part > 127
    blue = a[..., 2]
    rim = smoothstep(90, 210, blue) * smoothstep(25, 80, blue - a[..., 0])
    m_cap = np.where(cap, np.clip(cap_k * rim, 0, 1), 0)
    L = lum(relit.astype(np.float32))
    m_body = np.where(~cap, np.clip(body_k * (body_base + (1 - body_base) * smoothstep(90, 230, L)), 0, 1), 0)
    return m_cap, m_body


def effect(data: bytes, mask: str, strip: str, keep_dead: bool) -> tuple[bytes, dict]:
    pf = hp.ParticleFile(data)
    rs = pf.renderers()
    done = {"renderers": len(rs), "off": [], }
    for r in rs:
        pf.set_texture(r, "Blend.TextureBase", WHITE)
        pf.set_texture(r, "Blend.TextureBlend", WHITE)
        pf.set_texture(r, "AlphaMask.Mask", mask)
        pf.set_texture(r, "GradientRemap.GradientMap", strip)
        for f in OFF_FEATURES:
            p = r.props[f]
            pf.raw[p.value_at:p.value_at + 16] = hp.OFF
            done["off"].append(f)
    if keep_dead:
        # the engine fades the layer out when the monster dies (__a_Fade -> MonsterFade.Fade): off, so the corpse glows
        for r in rs:
            p = r.props["MonsterFade"]
            pf.raw[p.value_at:p.value_at + 16] = hp.OFF
            done["off"].append("MonsterFade")
    data = pf.data()
    pf = hp.ParticleFile(data)
    changed = []
    for sc in hd_cbvm.scripts(pf):
        text = hd_cbvm.script_text(sc)
        lines = []
        for line in text.splitlines():
            code = line.split(";")[0].rstrip()
            if "rand_float_float_RandCtx" in line and code.startswith("call"):
                # the spawn script's random UV offsets: rand(0, 1) -> rand(0, 0)
                line = code.replace("a:c0.float, a:c1.float,", "a:c0.float, a:c0.float,")
                done["uv_rand"] = done.get("uv_rand", 0) + 1
            elif line.startswith(".const") and "isRenderingEnabled" in text:
                parts = line.split()
                if parts[2] == "f":
                    v = round(float(parts[3]), 4)
                    if v in UV_CONSTS or (keep_dead and v == round(FADE, 4)):
                        nv = UV_CONSTS.get(v, 0.0)
                        line = " ".join(parts[:3] + [repr(nv)] * 8)
                        done["consts"] = done.get("consts", 0) + 1
            elif keep_dead and code.startswith("call") and "self.kill_bool" in line:
                lines.append("sel s2.bool, c1.bool, c1.bool, s2.bool")    # never killed by the script (c1 = 0)
                done["kill_off"] = done.get("kill_off", 0) + 1
            lines.append(line)
            if keep_dead and code.startswith("call") and "isRenderingEnabled" in line:
                lines.append("sel u1.bool, c3.bool, c3.bool, u1.bool")    # rendering stays on (c3 = -1)
                done["render_on"] = done.get("render_on", 0) + 1
        new_text = "\n".join(lines) + "\n"
        if new_text.strip() != text.strip():
            changed.append(hd_cbvm.script_parse(new_text, sc.obj))
    if changed:
        data = hd_cbvm.write_scripts(pf, changed)
    hp.ParticleFile(data)    # still parses
    return data, done


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    out, name = Path(a[0]), common.NAME
    albedo = np.asarray(Image.open(a[1]).convert("RGB"))
    relit = np.asarray(Image.open(a[2]).convert("RGB"))
    part = np.asarray(Image.open(a[3]).convert("L"))
    strip = float(opt("--strip", "0"))
    albedo, relit, part = (common.squash_u(x, strip) for x in (albedo, relit, part))
    mode = opt("--mask", "level")
    if mode == "sprite":
        m_cap, m_body = masks_sprite(albedo, part, float(opt("--cap", "1.0")), float(opt("--body", "0.45")),
                                     float(opt("--body-base", "0.0")), float(opt("--cap-lo", "40")),
                                     float(opt("--cap-hi", "220")), float(opt("--body-lo", "110")),
                                     float(opt("--body-hi", "230")), float(opt("--cap-pale", "0")))
    else:
        m_cap, m_body = masks(albedo, relit, part, float(opt("--cap", "1.0")), float(opt("--body", "0.45")),
                              float(opt("--body-base", "0.35")))
    extra = {}
    cap_px = part > 127
    if "--cap-gamma" in a:
        # a sharper mask: the weak glow of the band falls off faster than the strong glow of the bright specks
        ck = max(float(opt("--cap", "1.0")), 1e-6)
        g = float(opt("--cap-gamma", "1"))
        m_cap = np.where(cap_px, ck * np.clip(m_cap / ck, 0, 1) ** g, 0)
        extra["cap_gamma"] = g
    if "--cap-speck" in a:
        # the rim specks on their own: the positive part of the albedo's luminance minus its Gaussian local mean, added to the
        # mask so a speck glows clearly above the band (a speck the size of a few texels survives the mips only when its
        # contrast is high)
        # contrast is high). The local mean takes cap texels only (normalised convolution) and texels nearer than 2 sigma to
        # the edge of the cap's UV charts are left out: the atlas puts unrelated charts side by side, and a high-pass across
        # a seam draws the chart outlines instead of specks. Only bright texels (L >= 90) count as specks.
        k, sig = (float(x) for x in opt("--cap-speck", "0.3,3").split(","))
        Lc = lum(albedo.astype(np.float32))
        if Lc.shape != cap_px.shape:
            Lc = np.asarray(Image.fromarray(Lc).resize(cap_px.shape[::-1], Image.BILINEAR))
        cw = cap_px.astype(np.float32)
        mean = nd.gaussian_filter(Lc * cw, sig) / np.maximum(nd.gaussian_filter(cw, sig), 1e-3)
        inner = nd.distance_transform_edt(cap_px) >= 2 * sig
        hp = np.clip((Lc - mean) / 40.0, 0, 1) * inner * (Lc >= 90)
        m_cap = np.where(cap_px, np.clip(m_cap + k * hp * (m_cap > 0), 0, 1), 0)
        extra["cap_speck_texels"] = int((hp > 0.25).sum())
        extra["cap_speck"] = [k, sig]
    if "--cap-ring" in a:
        # the glow on the outer ring only: s3_tone.py's cap_radius.png (r * 255 on top-facing cap texels) gives the radius;
        # inside R0 nothing glows, rising to full at R1 (classic's centre is nearly black)
        rp, r0, r1 = opt("--cap-ring", "").split(",")
        rad = np.asarray(Image.open(rp).convert("L"))
        rad = common.squash_u(rad, strip) if strip else rad
        if rad.shape != m_cap.shape:
            rad = np.asarray(Image.fromarray(rad).resize(m_cap.shape[::-1], Image.NEAREST))
        r = rad.astype(np.float32) / 255
        w = np.where(rad > 0, smoothstep(float(r0), float(r1), r), 1.0)
        m_cap = m_cap * w
        extra["cap_ring"] = [float(r0), float(r1)]
    msize = int(opt("--mask-size", "1024"))
    vfx_parts = set(filter(None, opt("--vfx-parts", "").split(",")))
    rgb = {"cap": [int(x) for x in opt("--cap-rgb", "70,150,255").split(",")],
           "body": [int(x) for x in opt("--body-rgb", "190,215,255").split(",")]}
    keep_dead = "--die-fade" not in a
    tex_dir, fx_dir = "hd/vfx/textures/mxl/m3d/" + name, "hd/vfx/particles/mxl/m3d/" + name
    unit_path = out / "hd/character/enemy" / ("mxl_m3d_%s.json" % name)
    unit = json.loads(unit_path.read_text(encoding="utf-8"))
    torso = next(c["filename"] for e in unit["entities"] if e["name"] == "entity_torso"
                 for c in e["components"] if c["type"] == "ModelDefinitionComponent")
    model_tmpl = next(c for e in unit["entities"] if e["name"] == "entity_torso"
                      for c in e["components"] if c["type"] == "ModelDefinitionComponent")
    unit["entities"] = [e for e in unit["entities"] if not e["name"].startswith("vfx_glow_")]
    dep = unit["dependencies"]
    report = {"source": str(SRC.relative_to(common.EV)), "mask": mode, "vfx_parts": sorted(vfx_parts), "parts": {},
              "mask_size": msize, **extra}
    src = SRC.read_bytes()
    for k, (part_name, m) in enumerate((("cap", m_cap), ("body", m_body))):
        mask_rel = "%s/%s_glow_%s_mask.texture" % (tex_dir, name, part_name)
        strip_rel = "%s/%s_glow_%s_strip.texture" % (tex_dir, name, part_name)
        fx_rel = "%s/%s_glow_%s.particles" % (fx_dir, name, part_name)
        px = (np.asarray(Image.fromarray(np.round(m * 255).astype(np.uint8)).resize((msize, msize), Image.BILINEAR)))
        (out / mask_rel).parent.mkdir(parents=True, exist_ok=True)
        d2r_texture.write_bc4(out / mask_rel, px, int(np.log2(msize)) + 1)
        strip = np.zeros((16, 256, 4), np.uint8)
        strip[...] = rgb[part_name] + [255]
        d2r_texture.write_rgba(out / strip_rel, strip, 1)
        data, done = effect(src, "data/" + mask_rel, "data/" + strip_rel, keep_dead)
        (out / fx_rel).parent.mkdir(parents=True, exist_ok=True)
        (out / fx_rel).write_bytes(data)
        mdl = dict(model_tmpl, name="vfx_glow_%s_ModelDefinition" % part_name, filename=torso)
        if part_name in vfx_parts:
            fx = {"type": "VfxDefinitionComponent", "name": "vfx_glow_%s_VfxDefinition" % part_name,
                  "filename": "data/" + fx_rel, "hardKillOnDestroy": False}
            dep["particles"] = [d for d in dep.get("particles", []) if d["path"] != "data/" + fx_rel] + [
                {"path": "data/" + fx_rel}]
        else:
            fx = {"type": "ObjectEffectDefinitionComponent", "name": "vfx_glow_%s_ObjectEffectDefinition" % part_name,
                  "filename": "data/" + fx_rel, "isWarlockWeaponVfx": False}
            dep["objecteffects"] = [d for d in dep.get("objecteffects", []) if d["path"] != "data/" + fx_rel] + [
                {"path": "data/" + fx_rel, "dependency": ""}]
        unit["entities"].append({"type": "Entity", "name": "vfx_glow_" + part_name, "id": 4100000000 + 17 * k + 1,
                                 "components": [mdl, fx]})
        dep["textures"] = [t for t in dep["textures"] if t["path"] not in ("data/" + mask_rel, "data/" + strip_rel)] + [
            {"path": "data/" + mask_rel}, {"path": "data/" + strip_rel}]
        report["parts"][part_name] = {"mask": mask_rel, "strip": strip_rel, "particles": fx_rel, "rgb": rgb[part_name],
                                      "route": "vfx" if part_name in vfx_parts else "objecteffect",
                                      "mask_mean": round(float(m.mean()), 4), "mask_p90_on_part": round(float(
                                          np.percentile(m[m > 0], 90)) if (m > 0).any() else 0.0, 3),
                                      "texels_over_0.5": int((m > 0.5).sum()), "bytes": len(data), **done}
        Image.fromarray(np.round(m * 255).astype(np.uint8)).resize((512, 512)).save(
            out.parent / ("glow_mask_%s.png" % part_name))
    unit_path.write_text(json.dumps(unit, separators=(",", ":")), encoding="utf-8")
    report["keep_glow_on_corpse"] = keep_dead
    Path(opt("--report", str(out.parent / "glow.json"))).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
