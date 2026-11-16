"""Unit tests of tools/hd_particles.py (D2R's baked PopcornFX particle files) and tools/hd_authored.py (authored HD
effects) on a synthetic particle file built here (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_hd_particles.py" """
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import hd_authored as ha  # noqa: E402
import hd_particles as hp  # noqa: E402
import hd_recolour as hr  # noqa: E402

GRAD = "data/hd/vfx/textures/gradient/T_FX_flame_gradient_02.texture"
MESH = "data/hd/vfx/meshes/fx_mesh_ring.model"
STRINGS = [hp.PROPERTY, hp.RENDERER, "EnableRendering", "GradientRemap.GradientMap", GRAD,
           "vfx/materials/Diablo_Uber.pkma", "Transparent.CameraSortOffset", "General.Mesh", MESH]


def obj(cls: int, fields: list[tuple[int, bytes]]) -> bytes:
    body = b"\x20" + struct.pack("<IH", cls, len(fields)) + b"".join(struct.pack("<H", f) + v for f, v in fields)
    return struct.pack("<I", len(body)) + body


def u32(*v) -> bytes:
    return struct.pack(f"<{len(v)}I", *v)


def prop(name: int, typ: int, value: bytes | None = None, string: int | None = None) -> bytes:
    f = [(0, u32(name)), (1, u32(typ))]
    if value is not None:
        f.append((2, value))
    if string is not None:
        f.append((3, u32(string)))
    return obj(0, f)


def renderer(kind: int | None, refs: list[int]) -> bytes:
    f = [] if kind is None else [(0, u32(kind))]
    return obj(1, f + [(2, u32(len(refs), *refs)), (4, u32(5))])


def particle_file() -> bytes:
    """A mesh renderer (switch on, a gradient, a mesh, a float) and a billboard renderer (switch on, the gradient)."""
    objs = [prop(2, hp.T_BOOL, hp.ON), prop(3, hp.T_TEXTURE, string=4), prop(6, hp.T_FLOAT, struct.pack("<4f", 0, 0, 0, 0)),
            prop(7, hp.T_MESH, string=8), renderer(2, [1, 2, 3, 4]),
            prop(2, hp.T_BOOL, hp.ON), prop(3, hp.T_TEXTURE, string=4), renderer(None, [6, 7])]
    body = b"".join(objs)
    classes = u32(0, 6, 1, 2)
    stro = 0x1C + len(classes) + len(body)
    head = u32(hp.MAGIC, 0x01050902, 0x1F40, len(objs), 2, stro, 0)
    tail = u32(len(STRINGS)) + b"".join(bytes([len(s)]) + s.encode() for s in STRINGS)
    return head + classes + body + tail


class Reading(unittest.TestCase):
    def test_round_trip_and_renderers(self):
        data = particle_file()
        pf = hp.ParticleFile(data)
        self.assertEqual(pf.data(), data)
        rs = pf.renderers()
        self.assertEqual([r.kind for r in rs], ["mesh", "billboard"])
        self.assertTrue(all(r.enabled for r in rs))
        self.assertEqual(pf.prop_string(rs[0].props["General.Mesh"]), MESH)
        self.assertEqual(rs[1].material, "vfx/materials/Diablo_Uber.pkma")
        self.assertEqual(pf.textures(), [GRAD, MESH])

    def test_rejects_other_files(self):
        with self.assertRaises(ValueError):
            hp.ParticleFile(b"PKFX" + b"\0" * 40)
        with self.assertRaises(ValueError):
            hp.ParticleFile(particle_file() + b"x")   # the string table must end the file

    def test_select(self):
        pf = hp.ParticleFile(particle_file())
        self.assertEqual([r.kind for r in hp.select(pf, "mesh")], ["mesh"])
        self.assertEqual(len(hp.select(pf, "*")), 2)
        self.assertEqual(len(hp.select(pf, "flame_gradient")), 2)       # a path fragment
        self.assertEqual([r.kind for r in hp.select(pf, "fx_mesh_ring")], ["mesh"])
        self.assertEqual([r.kind for r in hp.select(pf, "light,billboard")], ["billboard"])
        self.assertEqual([r.kind for r in hp.select(pf, [1])], ["billboard"])


class Editing(unittest.TestCase):
    def test_hide_switches_one_layer_off(self):
        out = hp.apply(particle_file(), {"hide": "mesh"})
        self.assertEqual(len(out), len(particle_file()))
        self.assertEqual([r.enabled for r in hp.ParticleFile(out).renderers()], [False, True])
        back = hp.apply(out, {"show": "*"})
        self.assertEqual(back, particle_file())

    def test_texture_of_any_length(self):
        new = "data/hd/vfx/textures/mxl/authored/a_much_longer_name_for_the_new_gradient.texture"
        out = hp.apply(particle_file(), {"textures": {GRAD: new}})
        pf = hp.ParticleFile(out)
        self.assertEqual(pf.textures(), [new, MESH])
        self.assertEqual(len(out), len(particle_file()) + len(new) - len(GRAD))
        with self.assertRaises(ValueError):
            hp.apply(particle_file(), {"textures": {"data/hd/none.texture": new}})

    def test_set_texture_on_one_renderer_only(self):
        pf = hp.ParticleFile(particle_file())
        r = pf.renderers()[1]
        pf.set_texture(r, "GradientRemap.GradientMap", "data/hd/x.texture")
        rs = hp.ParticleFile(pf.data()).renderers()
        self.assertEqual(pf.prop_string(rs[0].props["GradientRemap.GradientMap"]), GRAD)
        self.assertEqual(pf.prop_string(rs[1].props["GradientRemap.GradientMap"]), "data/hd/x.texture")

    def test_float_property(self):
        out = hp.apply(particle_file(), {"props": [{"renderers": "mesh", "name": "Transparent.CameraSortOffset",
                                                    "value": 2.5}]})
        p = hp.ParticleFile(out).renderers()[0].props["Transparent.CameraSortOffset"]
        self.assertEqual(struct.unpack("<4f", p.value), (2.5,) * 4)
        pf = hp.ParticleFile(particle_file())
        with self.assertRaises(ValueError):    # a texture is set with set_texture
            pf.set_property(pf.renderers()[0], "GradientRemap.GradientMap", 1)


class Authored(unittest.TestCase):
    PART = "data/hd/vfx/particles/missiles/x/vfx_x_trail.particles"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.hdm, self.hdo, self.out = r / "missiles", r / "overlays", r / "out"
        (self.hdo / "common").mkdir(parents=True)
        self.hdm.mkdir()
        (self.hdm / "rock.json").write_text(json.dumps({"dependencies": {"particles": [{"path": "data/hd/rock.particles"}]},
            "entities": [
                {"type": "Entity", "name": "entity_root", "id": 1, "components": [{"type": "UnitRootComponent"}]},
                {"type": "Entity", "name": "entity_rock", "id": 2, "components": [
                    {"type": "VfxDefinitionComponent", "filename": "data/hd/rock.particles"},
                    {"type": "TransformDefinitionComponent", "position": {"x": 0, "y": 4, "z": 0},
                     "scale": {"x": 1, "y": 1, "z": 1}}]},
                {"type": "Entity", "name": "entity_only_one_skill", "id": 3, "components": [
                    {"type": "VfxDefinitionComponent", "filename": "data/hd/other.particles"},
                    {"type": "UnitSourceSkillFilterComponent", "sourceSkill": "shiver_armor"}]}]}))
        (self.hdo / "common" / "zap.json").write_text(json.dumps({"entities": [
            {"type": "Entity", "name": "entity_zap", "id": 9, "components": [
                {"type": "VfxDefinitionComponent", "filename": "data/hd/zap.particles"}]}]}))
        self.patch = mock.patch.object(hr, "casc_read", lambda p: particle_file() if p.endswith(".particles") else b"")
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def load(self, effects):
        p = Path(self.tmp.name) / "authored.json"
        p.write_text(json.dumps({"effects": effects}))
        return ha.load(p)

    def test_load_checks_entries(self):
        good = {"name": "e", "kind": "missile", "base": "rock", "layers": [{"from": "missile:rock"}]}
        self.assertEqual(list(self.load([good])), ["e"])
        for bad in ({**good, "kind": "monster"}, {**good, "layers": [{"from": "missile:rock", "particles": "x"}]},
                    {**good, "layers": [{"particles": "x", "edit": {"ramps": {GRAD: "plaid"}}}]}):
            with self.assertRaises(SystemExit):
                self.load([bad])
        with self.assertRaises(SystemExit):
            self.load([good, good])

    def test_place_scales_and_adds_a_transform_only_when_needed(self):
        e = {"components": [{"type": "VfxDefinitionComponent"}]}
        self.assertEqual(ha.place(e, 1.0, (0, 0, 0)), e)
        t = ha.place(e, 2.0, (0, 0.5, 0))["components"][-1]
        self.assertEqual((t["scale"]["x"], t["position"]["y"]), (2.0, 0.5))
        e2 = {"components": [{"type": "TransformDefinitionComponent", "position": {"x": 0, "y": 4, "z": 0},
                              "scale": {"x": 1, "y": 1, "z": 1}}]}
        t2 = ha.place(e2, 1.5, (0, 0, 0))["components"][0]
        self.assertEqual((t2["scale"]["y"], t2["position"]["y"]), (1.5, 6.0))

    def test_build_layers_a_missile(self):
        entry = {"name": "mxl_stone", "kind": "missile", "base": "rock", "layers": [
            {"from": "missile:rock", "scale": 1.5}, {"from": "overlay:common/zap", "scale": 0.5}]}
        d = ha.build(entry, self.hdm, self.hdo, None)
        self.assertEqual(d["type"], "UnitDefinition")
        names = [e["name"] for e in d["entities"]]
        self.assertEqual(names, ["entity_root", "entity_rock_l0", "entity_zap_l1"])   # the skill-only entity is left out
        self.assertEqual(len({e["id"] for e in d["entities"]}), 3)
        rock = d["entities"][1]["components"][1]
        self.assertEqual((rock["scale"]["x"], rock["position"]["y"]), (1.5, 6.0))
        self.assertEqual({x["path"] for x in d["dependencies"]["particles"]},
                         {"data/hd/rock.particles", "data/hd/zap.particles"})
        self.assertEqual(d, ha.build(entry, self.hdm, self.hdo, None))   # deterministic

    def test_build_edits_and_writes_particles(self):
        entry = {"name": "trail", "kind": "overlay", "base": "common/zap", "layers": [
            {"from": "overlay:common/zap"},
            {"particles": self.PART, "scale": 2.0, "offset": [0, 0.3, 0],
             "edit": {"hide": "mesh", "ramps": {GRAD: "blue"}}}]}
        grad = np.zeros((16, 256, 4), np.uint8)
        grad[..., 0], grad[..., 3] = np.arange(256)[None, :], 255
        written = {}
        with mock.patch.object(hr, "gradient_pixels", return_value=grad), \
                mock.patch.object(hr, "parse_texture", return_value=(0, 256, 16, [b""] * 3)):
            d = ha.build(entry, self.hdm, self.hdo, self.out, written)
        self.assertEqual(d["type"], "OverlayDefinition")
        vfx = d["entities"][1]["components"][0]["filename"]
        self.assertEqual(vfx, f"{ha.PART_DIR}/trail/vfx_x_trail.particles")
        pf = hp.ParticleFile((self.out / vfx.split("/", 1)[1]).read_bytes())
        self.assertEqual([r.enabled for r in pf.renderers()], [False, True])
        tex = ha.derived_texture(GRAD, "blue")
        self.assertEqual(pf.textures()[0], tex)
        self.assertTrue((self.out / tex.split("/", 1)[1]).exists())
        self.assertEqual(written[vfx], self.PART)
        self.assertIn({"path": tex}, d["dependencies"]["textures"])
        self.assertNotIn({"path": self.PART}, d["dependencies"]["particles"])


if __name__ == "__main__":
    unittest.main()
