"""Unit tests of tools/hd_cbvm.py (the PopcornFX CPU VM bytecode in D2R's particle files) and the `tint` edit of
tools/hd_authored.py, on a synthetic particle file built here (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_hd_cbvm.py" """
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import hd_authored as ha  # noqa: E402
import hd_cbvm as hc  # noqa: E402
import hd_particles as hp  # noqa: E402

STRINGS = [hc.BLOB, "CPU/CPU_VM", "Color", "Age", "Other"]
T = {n: hc.TYPES.index(n) for n in ("float", "float4", "int", "bool", "class")}


def u32(*v) -> bytes:
    return struct.pack(f"<{len(v)}I", *v)


def reg(cls: str, idx: int, typ: str, flag: bool = False) -> int:
    return T[typ] << 24 | int(flag) << 23 | hc.CLASS.index(cls) << 21 | idx


def arr(words: bytes) -> bytes:
    return u32(len(words) // 4) + words


def blob(code: list, consts: list[bytes] = (), kind: int | None = 4, names=(2, 3)) -> bytes:
    """A CCompilerBlobCache object: backend, kind, program (header, code, constants, pad), externals Color and Age."""
    c = hc.encode(code)
    head = [3, len(c), 0, 32 * len(consts), 0, len(consts), 0, 0, 0]
    prog = u32(*head) + c + b"".join(consts)
    prog += b"\0" * (-len(prog) % 4)
    f = [(0, u32(1))] + ([] if kind is None else [(1, u32(kind))])
    f += [(2, arr(prog)), (4, arr(u32(*range(5 * len(names))))), (5, arr(u32(*names)))]
    body = b"\x20" + struct.pack("<IH", 0, len(f)) + b"".join(struct.pack("<H", k) + v for k, v in f)
    return u32(len(body)) + body


def particle_file(objs: list[bytes]) -> bytes:
    body = b"".join(objs)
    classes = u32(0, 6)
    stro = 0x1C + len(classes) + len(body)
    head = u32(hp.MAGIC, 0x01050902, 0x1F40, len(objs), 1, stro, 0)
    tail = u32(len(STRINGS)) + b"".join(bytes([len(s)]) + s.encode() for s in STRINGS)
    return head + classes + body + tail


def grey_code() -> list:
    """Age -> a grey level broadcast to float4 -> Color: the shape of D2R's tower mist colour."""
    return [hc.Ins(0x69, [reg("s", 0, "float")], [1]),
            hc.Ins(0x73, [reg("s", 0, "float"), reg("s", 0, "float"), reg("c", 0, "float")]),
            hc.Ins(0x6E, [reg("s", 1, "float4"), reg("s", 0, "float")], [0, 0, 0]),
            hc.Ins(0x6A, [reg("s", 1, "float4")], [0]),
            hc.Ins(0x7D)]


HALF = struct.pack("<8f", *[0.5] * 8)


class Instructions(unittest.TestCase):
    def test_every_opcode_round_trips(self):
        r = [reg("s", 1, "float4"), reg("u", 2, "float"), reg("c", 3, "float"), reg("s", 4, "int", True), reg("s", 5, "bool")]
        code = [hc.Ins(0x69, r[:1], [5]), hc.Ins(0x6A, r[:1], [-1]), hc.Ins(0x6B, [], [7]), hc.Ins(0x6C, r[:2]),
                hc.Ins(0x6D, r[:3]), hc.Ins(0x6D, r[:5]), hc.Ins(0x6E, r[:2], [0xD9, 0x6D, 0x11]), hc.Ins(0x6F, r[:2]),
                hc.Ins(0x70, r[:3], [13])] + [hc.Ins(op, r[:3]) for op in (0x71, 0x72, 0x73, 0x74)] + [
                hc.Ins(0x75, r[:4]), hc.Ins(0x7A, r[:4]), hc.Ins(0x76, r[:5]),
                hc.Ins(0x77, r[:2], [hc.MATH.index("sqrt")]), hc.Ins(0x78, r[:3], [hc.MATH.index("dot")]),
                hc.Ins(0x79, r[:4], [2]), hc.Ins(0x7B, r[:1], [6, -1, 5], [(8, r[1]), (0, r[2])]),
                hc.Ins(0x7C, [], [1, 2, 3]), hc.Ins(0x7D)]
        b = hc.encode(code)
        self.assertEqual(hc.decode(b), code)
        self.assertEqual(hc.encode(hc.decode(b)), b)
        self.assertEqual(len(hc.encode([hc.Ins(0x7B, r[:1], [6, -1, 5], [(8, r[1])])])), 16)  # 11 + 5 per argument

    def test_illegal_and_truncated_code_is_refused(self):
        with self.assertRaises(ValueError):
            hc.decode(b"\x42")
        with self.assertRaises(ValueError):
            hc.decode(hc.encode([hc.Ins(0x71, [1, 2, 3])])[:-1])

    def test_register_text(self):
        for r in (reg("s", 21, "float4"), reg("c", 0, "float"), reg("u", 7, "int", True)):
            self.assertEqual(hc.reg_parse(hc.reg_text(r)), r)
        self.assertEqual(hc.reg_text(reg("s", 1, "float4")), "s1.float4")

    def test_instruction_text(self):
        for i in grey_code():
            self.assertEqual(hc.ins_parse(hc.ins_text(i)), i)


class Scripts(unittest.TestCase):
    def setUp(self):
        self.data = particle_file([blob(grey_code(), [HALF]), blob(grey_code(), [HALF], kind=None)])

    def test_scripts_are_read(self):
        ss = hc.scripts(hp.ParticleFile(self.data))
        self.assertEqual([s.obj for s in ss], [0, 1])
        self.assertEqual((ss[0].backend, ss[0].kind, ss[1].kind), ("CPU/CPU_VM", 4, None))
        self.assertEqual(ss[0].ext_names, ["Color", "Age"])
        self.assertEqual(ss[0].consts, [HALF])
        self.assertEqual(ss[0].code, grey_code())

    def test_text_round_trip_is_byte_exact(self):
        self.assertEqual(hc.roundtrip(self.data), (2, True))
        s = hc.scripts(hp.ParticleFile(self.data))[0]
        self.assertIn("swz", hc.script_text(s))

    def test_edited_text_rebuilds(self):
        pf = hp.ParticleFile(self.data)
        s = hc.scripts(pf)[0]
        text = hc.script_text(s).replace("0.5", "0.25")
        new = hc.write_scripts(pf, [hc.script_parse(text, s.obj)])
        s2 = hc.scripts(hp.ParticleFile(new))[0]
        self.assertEqual(struct.unpack_from("<f", s2.consts[0])[0], 0.25)

    def test_grey_colour_streams(self):
        self.assertEqual(hc.colour_streams(self.data), ["Color"])

    def test_tint_multiplies_before_each_store(self):
        new, n = hc.tint(self.data, "Color", [0.2, 0.4, 1.6])
        self.assertEqual(n, 2)
        pf = hp.ParticleFile(new)  # the moved string table is found again
        self.assertEqual(pf.strings, STRINGS)
        for s in hc.scripts(pf):
            self.assertEqual(len(s.consts), 2)
            self.assertEqual(s.consts[1], struct.pack("<8f", *(0.2, 0.4, 1.6, 1.0) * 2))
            st = next(k for k, i in enumerate(s.code) if i.op == 0x6A)
            mul = s.code[st - 1]
            self.assertEqual((mul.op, mul.regs[0], mul.regs[1]), (0x73, reg("s", 1, "float4"), reg("s", 1, "float4")))
            self.assertEqual(mul.regs[2], reg("c", 1, "float4"))
            self.assertEqual(s.head[1], len(hc.encode(s.code)))
            self.assertEqual((s.head[3], s.head[5]), (64, 2))
        self.assertEqual(struct.unpack_from("<I", new, 20)[0], hp.ParticleFile(new).str_at)
        self.assertEqual(len(new) - len(self.data), 2 * 48)  # per script a 13-byte mul and a 32-byte constant, 4-aligned

    def test_tint_of_an_unknown_stream_is_refused(self):
        with self.assertRaises(ValueError):
            hc.tint(self.data, "Other", [1, 0, 0])


class AuthoredTint(unittest.TestCase):
    def test_tint_edit_colours_every_grey_stream(self):
        data = particle_file([blob(grey_code(), [HALF])])
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ha.hr, "casc_read", return_value=data):
            path, _t = ha.edit_particles(Path(d), "rapture_test", "data/hd/vfx/particles/x/mist.particles",
                                         {"tint": [0.35, 0.6, 1.6, 1.0]}, {})
            new = (Path(d) / path.split("/", 1)[1]).read_bytes()
        s = hc.scripts(hp.ParticleFile(new))[0]
        self.assertEqual(struct.unpack("<4f", s.consts[1][:16]), struct.unpack("<4f", struct.pack("<4f", 0.35, 0.6, 1.6, 1.0)))

    def test_tint_edit_without_a_grey_colour_stops(self):
        code = [hc.Ins(0x69, [reg("s", 1, "float4")], [1]), hc.Ins(0x6A, [reg("s", 1, "float4")], [0]), hc.Ins(0x7D)]
        data = particle_file([blob(code)])
        with mock.patch.object(ha.hr, "casc_read", return_value=data), self.assertRaises(SystemExit):
            ha.edit_particles(None, "rapture_test", "data/hd/vfx/particles/x/mist.particles", {"tint": [1, 0, 0]}, {})


if __name__ == "__main__":
    unittest.main()
