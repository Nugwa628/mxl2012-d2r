"""Dump the running game image (D2RLoader.exe, the D2R image D2RLoader runs) from memory into a PE file for Ghidra.

D2R.exe's code is encrypted on disk and D2RLoader.exe stores its sections empty (filled at start-up), so the
code only exists in memory. This reads the main module of the running process (read-only) and writes it with
every section's file offset equal to its RVA ("memory layout"), so Ghidra addresses = exeBase + RVA, the same
RVAs plugins and crash reports use. Unreadable pages are written as zeros.

Usage: python tools/dump_image.py [--pid N] [--out PATH]
       (default: the D2RLoader.exe process, out = ../ghidra/D2RLoader_<timestamp>_dump.exe)
"""
import argparse
import ctypes
import struct
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x0400, 0x0010
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = wintypes.HANDLE
k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
psapi.EnumProcessModulesEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD,
                                       ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]


def find_pid(name: str) -> int:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], capture_output=True,
                         text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if parts and parts[0].lower() == name.lower():
            return int(parts[1])
    raise SystemExit(f"{name} is not running")


def read(h, addr: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t()
    if k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)) and n.value == size:
        return buf.raw
    # fall back page by page; pages that cannot be read stay zero
    out = bytearray(size)
    for off in range(0, size, 0x1000):
        chunk = min(0x1000, size - off)
        b = ctypes.create_string_buffer(chunk)
        if k32.ReadProcessMemory(h, ctypes.c_void_p(addr + off), b, chunk, ctypes.byref(n)):
            out[off:off + n.value] = b.raw[:n.value]
    return bytes(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    pid = args.pid or find_pid("D2RLoader.exe")
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        raise SystemExit(f"OpenProcess failed ({ctypes.get_last_error()})")
    mods = (ctypes.c_void_p * 1)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(needed), 0x03):
        raise SystemExit(f"EnumProcessModulesEx failed ({ctypes.get_last_error()})")
    base = mods[0]
    head = read(h, base, 0x1000)
    pe = struct.unpack_from("<I", head, 0x3C)[0]
    nsec = struct.unpack_from("<H", head, pe + 6)[0]
    timestamp = struct.unpack_from("<I", head, pe + 8)[0]
    opt = pe + 24
    size_of_image = struct.unpack_from("<I", head, opt + 56)[0]
    print(f"pid {pid}, base 0x{base:x}, image 0x{size_of_image:x} bytes, {nsec} sections, timestamp 0x{timestamp:x}")
    image = bytearray(read(h, base, size_of_image))
    # memory layout: raw offset = RVA, raw size = virtual size
    sec = opt + struct.unpack_from("<H", image, pe + 20)[0]
    for i in range(nsec):
        o = sec + 40 * i
        vsize, va = struct.unpack_from("<II", image, o + 8)
        struct.pack_into("<II", image, o + 16, vsize, va)
        name = image[o:o + 8].rstrip(b"\0").decode(errors="replace")
        print(f"  {name:8} rva 0x{va:08x} size 0x{vsize:08x}")
    struct.pack_into("<Q", image, opt + 24, base)  # ImageBase = where it was loaded
    out = args.out or (ROOT.parent / "ghidra" / f"D2RLoader_{timestamp:08x}_dump.exe")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(bytes(image))
    print(f"wrote {out} ({len(image) / 1e6:.0f} MB)")
    k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
