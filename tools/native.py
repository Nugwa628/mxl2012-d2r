"""ctypes loaders for the StormLib and CascLib builds: this checkout's build/, else the shared build (MXL_NATIVE_DIR,
<runs>/shared/native/build; tools/lane_setup.py makes it, tools/build_native.ps1 builds either)."""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402  (.mxl-local.json defaults: MXL_NATIVE_DIR)

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str) -> ctypes.WinDLL:
    return ctypes.WinDLL(str(localconfig.find_native_dll(name)))


storm = _load("StormLib")
storm.SFileOpenArchive.argtypes = [ctypes.c_char_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
storm.SFileOpenArchive.restype = wintypes.BOOL
storm.SFileCloseArchive.argtypes = [wintypes.HANDLE]
storm.SFileCloseArchive.restype = wintypes.BOOL

# StormLib is built ANSI (STORM_UNICODE off), so TCHAR paths are char*.
storm.SFileExtractFile.argtypes = [wintypes.HANDLE, ctypes.c_char_p, ctypes.c_char_p, wintypes.DWORD]
storm.SFileExtractFile.restype = wintypes.BOOL
storm.SFileGetFileInfo.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
storm.SFileGetFileInfo.restype = wintypes.BOOL


class SFILE_FIND_DATA(ctypes.Structure):
    _fields_ = [
        ("cFileName", ctypes.c_char * 260),  # MAX_PATH
        ("szPlainName", ctypes.c_char_p),
        ("dwHashIndex", wintypes.DWORD),
        ("dwBlockIndex", wintypes.DWORD),
        ("dwFileSize", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwCompSize", wintypes.DWORD),
        ("dwFileTimeLo", wintypes.DWORD),
        ("dwFileTimeHi", wintypes.DWORD),
        ("lcLocale", wintypes.DWORD),
    ]


storm.SFileFindFirstFile.argtypes = [wintypes.HANDLE, ctypes.c_char_p, ctypes.POINTER(SFILE_FIND_DATA), ctypes.c_char_p]
storm.SFileFindFirstFile.restype = wintypes.HANDLE
storm.SFileFindNextFile.argtypes = [wintypes.HANDLE, ctypes.POINTER(SFILE_FIND_DATA)]
storm.SFileFindNextFile.restype = wintypes.BOOL
storm.SFileFindClose.argtypes = [wintypes.HANDLE]
storm.SFileFindClose.restype = wintypes.BOOL

STREAM_FLAG_READ_ONLY = 0x100
SFILE_INFO_NUMBER_OF_FILES = 36  # SFileInfoClass::SFileMpqNumberOfFiles


def mpq_file_count(handle: wintypes.HANDLE) -> int:
    n = wintypes.DWORD()
    storm.SFileGetFileInfo(handle, SFILE_INFO_NUMBER_OF_FILES, ctypes.byref(n), 4, None)
    return n.value


def mpq_files(handle: wintypes.HANDLE, listfile: str | None = None) -> list[tuple[str, int]]:
    """Names (and sizes) StormLib can resolve, from the internal (listfile) plus an optional external one."""
    data = SFILE_FIND_DATA()
    lf = listfile.encode("mbcs") if listfile else None
    find = storm.SFileFindFirstFile(handle, b"*", ctypes.byref(data), lf)
    out = []
    if not find:
        return out
    seen = set()
    try:
        while True:
            name = data.cFileName.decode("mbcs")
            # Median's archives make SFileFindNextFile repeat the last entry forever instead of failing.
            if name in seen:
                break
            seen.add(name)
            out.append((name, data.dwFileSize))
            if not storm.SFileFindNextFile(find, ctypes.byref(data)):
                break
    finally:
        storm.SFileFindClose(find)
    return out


def extract(handle: wintypes.HANDLE, name: str, dest: str | Path) -> bool:
    return bool(storm.SFileExtractFile(handle, name.encode("mbcs"), str(dest).encode("mbcs"), 0))


casc = _load("CascLib")
# CascLib is built ANSI (CASC_UNICODE off).
casc.CascOpenStorage.argtypes = [ctypes.c_char_p, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
casc.CascOpenStorage.restype = wintypes.BOOL
casc.CascCloseStorage.argtypes = [wintypes.HANDLE]
casc.CascCloseStorage.restype = wintypes.BOOL
casc.CascOpenFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
casc.CascOpenFile.restype = wintypes.BOOL
casc.CascGetFileSize.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
casc.CascGetFileSize.restype = wintypes.DWORD
casc.CascReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
casc.CascReadFile.restype = wintypes.BOOL
casc.CascCloseFile.argtypes = [wintypes.HANDLE]
casc.CascCloseFile.restype = wintypes.BOOL


class CASC_FIND_DATA(ctypes.Structure):
    _fields_ = [
        ("szFileName", ctypes.c_char * 260),  # MAX_PATH
        ("CKey", ctypes.c_ubyte * 16),
        ("EKey", ctypes.c_ubyte * 16),
        ("TagBitMask", ctypes.c_uint64),
        ("FileSize", ctypes.c_uint64),
        ("szPlainName", ctypes.c_char_p),
        ("dwFileDataId", wintypes.DWORD),
        ("dwLocaleFlags", wintypes.DWORD),
        ("dwContentFlags", wintypes.DWORD),
        ("dwSpanCount", wintypes.DWORD),
        ("bFileAvailable", wintypes.DWORD),  # 1-bit bitfield in a DWORD
        ("NameType", ctypes.c_int),
    ]


casc.CascFindFirstFile.argtypes = [wintypes.HANDLE, ctypes.c_char_p, ctypes.POINTER(CASC_FIND_DATA), ctypes.c_char_p]
casc.CascFindFirstFile.restype = wintypes.HANDLE
casc.CascFindNextFile.argtypes = [wintypes.HANDLE, ctypes.POINTER(CASC_FIND_DATA)]
casc.CascFindNextFile.restype = ctypes.c_bool
casc.CascFindClose.argtypes = [wintypes.HANDLE]
casc.CascFindClose.restype = ctypes.c_bool


def casc_files(storage: wintypes.HANDLE, mask: str = "*") -> list[tuple[str, int, bool]]:
    """(name, size, available locally) for every named file matching mask."""
    data = CASC_FIND_DATA()
    find = casc.CascFindFirstFile(storage, mask.encode("mbcs"), ctypes.byref(data), None)
    out = []
    if not find:
        return out
    try:
        while True:
            if data.NameType == 0:  # CascNameFull
                out.append((data.szFileName.decode("mbcs"), data.FileSize, bool(data.bFileAvailable & 1)))
            if not casc.CascFindNextFile(find, ctypes.byref(data)):
                break
    finally:
        casc.CascFindClose(find)
    return out


def open_casc(game_dir: str | Path) -> wintypes.HANDLE:
    handle = wintypes.HANDLE()
    if not casc.CascOpenStorage(str(game_dir).encode("mbcs"), 0, ctypes.byref(handle)):
        raise OSError(ctypes.GetLastError(), f"CascOpenStorage failed: {game_dir}")
    return handle


def casc_read(storage: wintypes.HANDLE, name: str) -> bytes:
    """Read a whole file, e.g. 'data:data/global/excel/skills.txt'."""
    fh = wintypes.HANDLE()
    if not casc.CascOpenFile(storage, name.encode("mbcs"), 0, 0, ctypes.byref(fh)):
        raise FileNotFoundError(ctypes.GetLastError(), name)
    try:
        size = casc.CascGetFileSize(fh, None)
        buf = ctypes.create_string_buffer(size)
        read = wintypes.DWORD()
        if not casc.CascReadFile(fh, buf, size, ctypes.byref(read)):
            raise OSError(ctypes.GetLastError(), f"CascReadFile failed: {name}")
        return buf.raw[: read.value]
    finally:
        casc.CascCloseFile(fh)


def open_mpq(path: str | Path) -> wintypes.HANDLE:
    handle = wintypes.HANDLE()
    if not storm.SFileOpenArchive(str(path).encode("mbcs"), 0, STREAM_FLAG_READ_ONLY, ctypes.byref(handle)):
        raise OSError(ctypes.GetLastError(), f"SFileOpenArchive failed: {path}")
    return handle
