"""Static, read-only PE summary (no pefile): machine, timestamp, sections, imports, exports, version resource,
and notable strings (assert source paths, version-like strings, D2 DLL names).

Usage: py -3 -I tools/pe_info.py <file> [<file> ...]
"""
import hashlib
import re
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path


def u16(b, o): return struct.unpack_from("<H", b, o)[0]
def u32(b, o): return struct.unpack_from("<I", b, o)[0]


def cstr(b, o):
    e = b.index(b"\0", o)
    return b[o:e].decode("latin-1")


class PE:
    def __init__(self, data: bytes):
        self.b = data
        pe = u32(data, 0x3C)
        assert data[pe:pe + 4] == b"PE\0\0"
        self.machine = u16(data, pe + 4)
        nsec = u16(data, pe + 6)
        self.timestamp = u32(data, pe + 8)
        optsz = u16(data, pe + 20)
        self.characteristics = u16(data, pe + 22)
        opt = pe + 24
        self.magic = u16(data, opt)
        self.linker = f"{data[opt + 2]}.{data[opt + 3]}"
        dd = opt + (96 if self.magic == 0x10B else 112)
        self.dirs = [(u32(data, dd + 8 * i), u32(data, dd + 8 * i + 4)) for i in range(16)]
        self.sections = []
        so = opt + optsz
        for i in range(nsec):
            o = so + 40 * i
            name = data[o:o + 8].rstrip(b"\0").decode("latin-1")
            vsz, va, rsz, rptr = u32(data, o + 8), u32(data, o + 12), u32(data, o + 16), u32(data, o + 20)
            self.sections.append((name, va, vsz, rptr, rsz))

    def off(self, rva):
        for _, va, vsz, rptr, rsz in self.sections:
            if va <= rva < va + max(vsz, rsz):
                return rva - va + rptr
        return None

    def imports(self):
        rva, size = self.dirs[1]
        out = {}
        if not rva:
            return out
        o = self.off(rva)
        while True:
            oft, _, _, name, ft = struct.unpack_from("<IIIII", self.b, o)
            if not name:
                break
            dll = cstr(self.b, self.off(name))
            thunk = self.off(oft or ft)
            fns = []
            while thunk is not None:
                t = u32(self.b, thunk)
                if not t:
                    break
                if t & 0x80000000:
                    fns.append(f"#{t & 0xFFFF}")
                else:
                    fns.append(cstr(self.b, self.off(t) + 2))
                thunk += 4
            out[dll] = fns
            o += 20
        return out

    def exports(self):
        rva, size = self.dirs[0]
        if not rva:
            return None, []
        o = self.off(rva)
        name = cstr(self.b, self.off(u32(self.b, o + 12)))
        nfun, nnames = u32(self.b, o + 20), u32(self.b, o + 24)
        names_o = self.off(u32(self.b, o + 32)) if nnames else None
        names = [cstr(self.b, self.off(u32(self.b, names_o + 4 * i))) for i in range(nnames)]
        return name, (names, nfun)

    def version(self):
        """Fixed file info + string table from the resource section (scan for VS_VERSION_INFO)."""
        key = "VS_VERSION_INFO".encode("utf-16-le")
        i = self.b.find(key)
        if i < 0:
            return None
        sig = self.b.find(struct.pack("<I", 0xFEEF04BD), i)
        fixed = None
        if 0 <= sig - i < 64:
            ms, ls, pms, pls = struct.unpack_from("<IIII", self.b, sig + 8)
            fixed = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF} (product {pms >> 16}.{pms & 0xFFFF}.{pls >> 16}.{pls & 0xFFFF})"
        blob = self.b[i:i + 4096].decode("utf-16-le", "ignore")
        strs = {}
        for k in ("CompanyName", "FileDescription", "FileVersion", "InternalName", "LegalCopyright",
                  "OriginalFilename", "ProductName", "ProductVersion"):
            m = re.search(k + r"\x00+([^\x00]+)", blob)
            if m:
                strs[k] = m.group(1)
        return fixed, strs


STR_RE = re.compile(rb"[\x20-\x7e]{5,}")
WSTR_RE = re.compile(rb"(?:[\x20-\x7e]\x00){5,}")
INTEREST = re.compile(r"(\.cpp|\.c\b|\.h\b|\.pdb|\\src\\|1\.1[0-4]|v1\.|version|D2[A-Za-z]+\.dll|Fog\.dll|Storm\.dll|"
                      r"Game\.exe|\.mpq|patch|Median|PlugY|D2SE|D2GL|glide|Sigma|D2Mod|copyright|http)", re.I)


def notable_strings(b: bytes, limit=120):
    seen, out = set(), []
    for m in STR_RE.finditer(b):
        s = m.group().decode("latin-1")
        if INTEREST.search(s) and s not in seen:
            seen.add(s)
            out.append(s)
    for m in WSTR_RE.finditer(b):
        s = m.group().decode("utf-16-le")
        if INTEREST.search(s) and s not in seen:
            seen.add(s)
            out.append("W:" + s)
    return out[:limit], len(out)


def main():
    for arg in sys.argv[1:]:
        p = Path(arg)
        b = p.read_bytes()
        print("=" * 100)
        print(f"{p.name}  size={len(b)}  sha256={hashlib.sha256(b).hexdigest()}")
        if b[:2] != b"MZ":
            print("  not a PE")
            continue
        pe = PE(b)
        ts = datetime.fromtimestamp(pe.timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  machine=0x{pe.machine:x} magic=0x{pe.magic:x} linker={pe.linker} timestamp={ts} (0x{pe.timestamp:08x}) "
              f"dll={bool(pe.characteristics & 0x2000)}")
        print("  sections: " + ", ".join(f"{n}(v{vs:#x}/r{rs:#x})" for n, _, vs, _, rs in pe.sections))
        v = pe.version()
        if v:
            print(f"  version: {v[0]}  {v[1]}")
        name, ex = pe.exports()
        if name:
            names, nfun = ex
            print(f"  exports: dllname={name} functions={nfun} named={len(names)}: {', '.join(names[:40])}")
        try:
            imps = pe.imports()
        except Exception as e:  # noqa: BLE001
            imps = {}
            print(f"  imports: parse error {e}")
        for dll, fns in imps.items():
            show = ", ".join(fns[:25]) + (" ..." if len(fns) > 25 else "")
            print(f"  import {dll} ({len(fns)}): {show}")
        strs, total = notable_strings(b)
        print(f"  notable strings ({total}, first {len(strs)}):")
        for s in strs:
            print("    " + s[:160])


if __name__ == "__main__":
    main()
