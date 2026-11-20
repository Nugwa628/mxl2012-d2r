"""tools/native.py against the real StormLib/CascLib headers and builds (lane linux-tools).

- test_layouts: compiles a small C program with the libraries' own headers (StormLib.h, CascLib.h; on Linux their
  StormPort.h/CascPort.h define DWORD as 32-bit `unsigned int` and MAX_PATH as 1024) and compares every sizeof/offsetof
  with native.py's ctypes structs. Needs a C compiler and the sources (the worktree's submodules, MXL_NATIVE_REF, the
  shared clone or the reference checkout); skips without them.
- test_mpq_roundtrip: makes a small MPQ with StormLib, then lists and extracts it through native.py.
Both skip when the libraries are not built (tools/lane_setup.py, docs/setup.md "Linux").
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import lane_setup  # noqa: E402
import localconfig  # noqa: E402

try:
    import native  # noqa: E402
except (FileNotFoundError, OSError) as e:  # library not built here
    native = None
    NATIVE_ERROR = str(e)

FIELDS = {
    "SFILE_FIND_DATA": ["cFileName", "szPlainName", "dwHashIndex", "dwBlockIndex", "dwFileSize", "dwFileFlags",
                        "dwCompSize", "dwFileTimeLo", "dwFileTimeHi", "lcLocale"],
    # bFileAvailable is a 1-bit bitfield (no offsetof); its DWORD sits between dwSpanCount and NameType
    "CASC_FIND_DATA": ["szFileName", "CKey", "EKey", "TagBitMask", "FileSize", "szPlainName", "dwFileDataId",
                       "dwLocaleFlags", "dwContentFlags", "dwSpanCount", "NameType"],
}


def header_dir(lib: str) -> Path | None:
    cands = [r / "src" for r in lane_setup.reference_repos(localconfig.ROOT, lib)]
    cands.append(localconfig.shared_dir() / "native" / "src" / lib / "src")
    return next((c for c in cands if (c / f"{lib}.h").exists()), None)


@unittest.skipIf(native is None, f"StormLib/CascLib not built: {globals().get('NATIVE_ERROR')}")
class NativeAbi(unittest.TestCase):
    def test_scalar_types_match_the_platform(self):
        self.assertEqual(ctypes.sizeof(native.DWORD), 4)
        self.assertEqual(native.MAX_PATH, 260 if sys.platform == "win32" else 1024)

    def test_layouts(self):
        cc = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if sys.platform == "win32" or not cc:
            self.skipTest("needs a POSIX C compiler")
        storm, casc = header_dir("StormLib"), header_dir("CascLib")
        if storm is None or casc is None:
            self.skipTest("StormLib/CascLib sources not found (MXL_NATIVE_REF or the submodules)")
        lines = []
        for struct, fields in FIELDS.items():
            lines.append(f'printf("{struct} size %zu\\n", sizeof({struct}));')
            lines += [f'printf("{struct} {f} %zu\\n", offsetof({struct}, {f}));' for f in fields]
        # the two headers each define the Windows types, so each struct is measured in its own unit
        out = {}
        with tempfile.TemporaryDirectory() as tmp:
            for header, inc, struct in (("StormLib.h", storm, "SFILE_FIND_DATA"), ("CascLib.h", casc, "CASC_FIND_DATA")):
                body = "\n    ".join(ln for ln in lines if f'"{struct} ' in ln)
                src = Path(tmp) / f"{struct}.cpp"
                src.write_text(f"#include <stddef.h>\n#include <stdio.h>\n#include \"{header}\"\n"
                               f"int main(void) {{\n    {body}\n    return 0;\n}}\n")
                exe = Path(tmp) / struct
                cxx = shutil.which("c++") or shutil.which("g++") or cc
                r = subprocess.run([cxx, "-I", str(inc), "-o", str(exe), str(src)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr[-2000:])
                for ln in subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout.splitlines():
                    s, f, v = ln.split()
                    out[(s, f)] = int(v)
        for struct, fields in FIELDS.items():
            cls = getattr(native, struct)
            with self.subTest(struct=struct):
                self.assertEqual(ctypes.sizeof(cls), out[(struct, "size")])
                for f in fields:
                    self.assertEqual(getattr(cls, f).offset, out[(struct, f)], f"{struct}.{f}")

    def test_mpq_roundtrip(self):
        s = native.storm
        s.SFileCreateArchive.argtypes = [ctypes.c_char_p, native.DWORD, native.DWORD, ctypes.POINTER(native.HANDLE)]
        s.SFileCreateArchive.restype = native.BOOL
        s.SFileAddFileEx.argtypes = [native.HANDLE, ctypes.c_char_p, ctypes.c_char_p, native.DWORD, native.DWORD,
                                     native.DWORD]
        s.SFileAddFileEx.restype = native.BOOL
        payload = b"Id\tname\n1\tlinux\n" * 50
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "in.txt").write_bytes(payload)
            mpq = tmp / "t.mpq"
            h = native.HANDLE()
            self.assertTrue(s.SFileCreateArchive(str(mpq).encode(), 0x00100000, 16, ctypes.byref(h)))  # MPQ_CREATE_LISTFILE
            self.assertTrue(s.SFileAddFileEx(h, str(tmp / "in.txt").encode(), b"data\\global\\excel\\t.txt",
                                             0x200, 0x02, 0x02))  # MPQ_FILE_COMPRESS, ZLIB
            s.SFileCloseArchive(h)
            h = native.open_mpq(mpq)
            try:
                files = dict(native.mpq_files(h))
                self.assertEqual(files.get("data\\global\\excel\\t.txt"), len(payload))
                self.assertGreaterEqual(native.mpq_file_count(h), 1)
                self.assertTrue(native.extract(h, "data\\global\\excel\\t.txt", tmp / "out.txt"))
                self.assertEqual((tmp / "out.txt").read_bytes(), payload)
            finally:
                s.SFileCloseArchive(h)
        with self.assertRaises(OSError) as cm:
            native.open_mpq(tmp / "missing.mpq")
        self.assertNotEqual(cm.exception.errno, 0)

    @unittest.skipUnless(os.environ.get("MXL_TEST_CASC_DIR"), "set MXL_TEST_CASC_DIR to a D2R install folder (read-only) to read its CASC")
    def test_casc_read(self):
        storage = native.open_casc(os.environ["MXL_TEST_CASC_DIR"])
        try:
            self.assertTrue(native.casc_read(storage, "data:data/global/excel/monstats.txt").startswith(b"Id\t"))
            names = [n for n, _, _ in native.casc_files(storage, "data:data/global/excel/*.txt")]
            self.assertIn("data:data\\global\\excel\\monstats.txt", names)
            with self.assertRaises(FileNotFoundError):
                native.casc_read(storage, "data:no/such/file.txt")
        finally:
            native.casc.CascCloseStorage(storage)


if __name__ == "__main__":
    unittest.main()
