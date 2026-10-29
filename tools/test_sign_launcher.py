"""Unit tests of tools/sign_launcher.py's PE check (runs anywhere: synthetic PE files, no signtool).

  cd tools && python -m unittest test_sign_launcher
"""
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import struct
import unittest

import sign_launcher as sl


def pe(body: bytes = b"code" * 100, pe32plus: bool = True) -> bytearray:
    """A minimal PE: DOS header, PE signature, COFF header, optional header with 16 data directories, a body."""
    opt_size = 240 if pe32plus else 224
    d = bytearray(0x40)
    d[0:2] = b"MZ"
    struct.pack_into("<I", d, 0x3C, 0x40)
    d += b"PE\0\0" + struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, opt_size, 0x22)
    opt = bytearray(opt_size)
    struct.pack_into("<H", opt, 0, 0x20B if pe32plus else 0x10B)
    return d + opt + body


def sign(unsigned: bytes, blob: bytes = b"PKCS7-signature-blob") -> bytearray:
    """What signtool does: checksum set, zero padding to 8, the certificate table appended, the security entry set."""
    d = bytearray(unsigned)
    chk, sec, _, _ = sl.pe_layout(d)
    d += b"\0" * (-len(d) % 8)
    off = len(d)
    d += blob
    struct.pack_into("<II", d, sec, off, len(blob))
    struct.pack_into("<I", d, chk, 0x12345)
    return d


class SignLauncherTest(unittest.TestCase):
    def test_layout(self):
        for plus in (True, False):
            d = pe(pe32plus=plus)
            chk, sec, off, size = sl.pe_layout(d)
            self.assertEqual(chk, 0x40 + 24 + 64)
            self.assertEqual(sec, 0x40 + 24 + (112 if plus else 96) + 32)
            self.assertEqual((off, size), (0, 0))

    def test_signed_is_same_program(self):
        for n in (400, 401, 403, 407):  # every padding length
            u = pe(b"x" * n)
            s = sign(u)
            self.assertTrue(sl.pe_layout(s)[3])
            self.assertTrue(sl.same_program(u, s), n)
            self.assertEqual(sl.program_bytes(u), sl.program_bytes(s))

    def test_changed_code_is_refused(self):
        u = pe(b"x" * 401)
        s = sign(u)
        s[0x40 + 24 + 240 + 10] ^= 1
        self.assertFalse(sl.same_program(u, s))

    def test_extra_bytes_are_refused(self):
        u = pe(b"x" * 400)
        s = sign(bytes(u) + b"EVIL" * 4)
        self.assertFalse(sl.same_program(u, s))

    def test_signature_must_be_last(self):
        s = sign(pe())
        with self.assertRaises(ValueError):
            sl.program_bytes(bytes(s) + b"trailing")

    def test_not_a_pe(self):
        with self.assertRaises(ValueError):
            sl.pe_layout(b"ZM" + b"\0" * 300)


if __name__ == "__main__":
    unittest.main()
