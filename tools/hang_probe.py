"""Where is a hung game process spinning? Samples every thread of the process (RIP and return-address-looking stack qwords, mapped to modules).
Usage: py -3 tools/hang_probe.py <pid> [samples]. Only for a game process this lane started (a slot we hold): it suspends each thread for one read and resumes it."""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE
PROCESS_VM_READ = 0x10
PROCESS_QUERY_INFORMATION = 0x400
THREAD_ALL = 0x1F03FF
CONTEXT_CONTROL = 0x100001
CONTEXT_INTEGER = 0x100002


class THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
                ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


def threads(pid):
    snap = k32.CreateToolhelp32Snapshot(4, 0)
    te = THREADENTRY32()
    te.dwSize = ctypes.sizeof(te)
    out = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid:
            out.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    return out


def modules(h):
    arr = (ctypes.c_void_p * 1024)()
    need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, arr, ctypes.sizeof(arr), ctypes.byref(need), 3)
    mods = []
    for i in range(need.value // 8):
        name = ctypes.create_unicode_buffer(260)
        psapi.GetModuleFileNameExW(h, ctypes.c_void_p(arr[i]), name, 260)
        info = (ctypes.c_uint64 * 3)()  # MODULEINFO: base, size, entry
        psapi.GetModuleInformation(h, ctypes.c_void_p(arr[i]), ctypes.byref(info), 24)
        mods.append((info[0], info[1], name.value.split("\\")[-1]))
    return mods


def where(mods, a):
    for base, size, name in mods:
        if base <= a < base + size:
            return "%s+0x%x" % (name, a - base)
    return None


def main():
    pid = int(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    hp = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    if not hp:
        raise SystemExit("OpenProcess failed %d" % ctypes.get_last_error())
    mods = modules(hp)
    print("modules:", [(hex(b), n_) for b, s, n_ in mods if n_.lower().startswith(("d2r", "mxl"))])
    for sample in range(n):
        print("== sample", sample)
        for tid in threads(pid):
            ht = k32.OpenThread(THREAD_ALL, False, tid)
            if not ht:
                continue
            raw = ctypes.create_string_buffer(1232 + 32)
            off = (-ctypes.addressof(raw)) % 16
            ctx = (ctypes.c_char * 1232).from_buffer(raw, off)
            struct.pack_into("<I", ctx, 0x30, CONTEXT_CONTROL | CONTEXT_INTEGER)
            if k32.SuspendThread(ht) == 0xFFFFFFFF:
                k32.CloseHandle(ht)
                continue
            try:
                if not k32.GetThreadContext(ht, ctypes.byref(ctx)):
                    continue
                rsp = struct.unpack_from("<Q", ctx, 0x98)[0]
                rip = struct.unpack_from("<Q", ctx, 0xF8)[0]
                w = where(mods, rip)
                buf = ctypes.create_string_buffer(0x800)
                got = ctypes.c_size_t()
                k32.ReadProcessMemory(hp, ctypes.c_void_p(rsp), buf, 0x800, ctypes.byref(got))
                rets = []
                for i in range(0, got.value - 7, 8):
                    q = struct.unpack_from("<Q", buf.raw, i)[0]
                    ww = where(mods, q)
                    if ww and ww.lower().startswith(("d2r", "mxl")):
                        rets.append("%s@%x" % (ww, i))
                print("tid %d rip %s  stack: %s" % (tid, w or hex(rip), " ".join(rets[:18])))
            finally:
                k32.ResumeThread(ht)
                k32.CloseHandle(ht)
        time.sleep(0.4)


main()
