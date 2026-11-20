"""ctypes loaders for the StormLib and CascLib builds: this checkout's build/, else the shared build (MXL_NATIVE_DIR,
<runs>/shared/native/build; tools/lane_setup.py makes it, tools/build_native.ps1 builds either).

Windows loads StormLib.dll / CascLib.dll with WinDLL. Linux loads libstorm.so / libcasc.so (docs/setup.md, "Linux") with
CDLL, and the Windows types are shimmed to what StormPort.h / CascPort.h define there: DWORD and LCID are 32-bit
`unsigned int` (ctypes.wintypes.DWORD is a 64-bit c_ulong on Linux), the API returns C++ `bool`, MAX_PATH is 1024 and
TCHAR paths are UTF-8 char*. tools/tests/test_native_abi.py checks the struct layouts against the headers."""
import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import localconfig  # noqa: E402  (.mxl-local.json defaults: MXL_NATIVE_DIR)

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = sys.platform == "win32"

if WINDOWS:
    DWORD, BOOL, HANDLE = wintypes.DWORD, wintypes.BOOL, wintypes.HANDLE
    MAX_PATH = 260
    ENCODING = "mbcs"  # StormLib and CascLib are built ANSI (STORM_UNICODE / CASC_UNICODE off)
else:
    DWORD, BOOL, HANDLE = ctypes.c_uint32, ctypes.c_bool, ctypes.c_void_p  # StormPort.h / CascPort.h, !WINDOWS branch
    MAX_PATH = 1024
    ENCODING = "utf-8"


def _load(name: str):
    path = str(localconfig.find_native_dll(name))
    return ctypes.WinDLL(path) if WINDOWS else ctypes.CDLL(path)


def _encode(text: str) -> bytes:
    return text.encode(ENCODING) if WINDOWS else text.encode(ENCODING, "surrogateescape")


def _decode(raw: bytes) -> str:
    return raw.decode(ENCODING) if WINDOWS else raw.decode(ENCODING, "surrogateescape")


storm = _load("StormLib")
storm.SFileOpenArchive.argtypes = [ctypes.c_char_p, DWORD, DWORD, ctypes.POINTER(HANDLE)]
storm.SFileOpenArchive.restype = BOOL
storm.SFileCloseArchive.argtypes = [HANDLE]
storm.SFileCloseArchive.restype = BOOL

# StormLib is built ANSI (STORM_UNICODE off), so TCHAR paths are char*.
storm.SFileExtractFile.argtypes = [HANDLE, ctypes.c_char_p, ctypes.c_char_p, DWORD]
storm.SFileExtractFile.restype = BOOL
storm.SFileGetFileInfo.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD)]
storm.SFileGetFileInfo.restype = BOOL


class SFILE_FIND_DATA(ctypes.Structure):
    _fields_ = [
        ("cFileName", ctypes.c_char * MAX_PATH),
        ("szPlainName", ctypes.c_char_p),
        ("dwHashIndex", DWORD),
        ("dwBlockIndex", DWORD),
        ("dwFileSize", DWORD),
        ("dwFileFlags", DWORD),
        ("dwCompSize", DWORD),
        ("dwFileTimeLo", DWORD),
        ("dwFileTimeHi", DWORD),
        ("lcLocale", DWORD),  # LCID
    ]


storm.SFileFindFirstFile.argtypes = [HANDLE, ctypes.c_char_p, ctypes.POINTER(SFILE_FIND_DATA), ctypes.c_char_p]
storm.SFileFindFirstFile.restype = HANDLE
storm.SFileFindNextFile.argtypes = [HANDLE, ctypes.POINTER(SFILE_FIND_DATA)]
storm.SFileFindNextFile.restype = BOOL
storm.SFileFindClose.argtypes = [HANDLE]
storm.SFileFindClose.restype = BOOL

if not WINDOWS:  # no thread error slot to read with ctypes.GetLastError: StormLib keeps its own
    storm.SErrGetLastError.argtypes = []
    storm.SErrGetLastError.restype = DWORD


def _storm_error() -> int:
    return ctypes.GetLastError() if WINDOWS else storm.SErrGetLastError()


STREAM_FLAG_READ_ONLY = 0x100
SFILE_INFO_NUMBER_OF_FILES = 36  # SFileInfoClass::SFileMpqNumberOfFiles


def mpq_file_count(handle: HANDLE) -> int:
    n = DWORD()
    storm.SFileGetFileInfo(handle, SFILE_INFO_NUMBER_OF_FILES, ctypes.byref(n), 4, None)
    return n.value


def mpq_files(handle: HANDLE, listfile: str | None = None) -> list[tuple[str, int]]:
    """Names (and sizes) StormLib can resolve, from the internal (listfile) plus an optional external one."""
    data = SFILE_FIND_DATA()
    lf = _encode(listfile) if listfile else None
    find = storm.SFileFindFirstFile(handle, b"*", ctypes.byref(data), lf)
    out = []
    if not find:
        return out
    seen = set()
    try:
        while True:
            name = _decode(data.cFileName)
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


def extract(handle: HANDLE, name: str, dest: str | Path) -> bool:
    return bool(storm.SFileExtractFile(handle, _encode(name), _encode(str(dest)), 0))


casc = _load("CascLib")
# CascLib is built ANSI (CASC_UNICODE off).
casc.CascOpenStorage.argtypes = [ctypes.c_char_p, DWORD, ctypes.POINTER(HANDLE)]
casc.CascOpenStorage.restype = BOOL
casc.CascCloseStorage.argtypes = [HANDLE]
casc.CascCloseStorage.restype = BOOL
casc.CascOpenFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, DWORD, ctypes.POINTER(HANDLE)]
casc.CascOpenFile.restype = BOOL
casc.CascGetFileSize.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
casc.CascGetFileSize.restype = DWORD
casc.CascReadFile.argtypes = [HANDLE, ctypes.c_void_p, DWORD, ctypes.POINTER(DWORD)]
casc.CascReadFile.restype = BOOL
casc.CascCloseFile.argtypes = [HANDLE]
casc.CascCloseFile.restype = BOOL


if not WINDOWS:
    casc.GetCascError.argtypes = []
    casc.GetCascError.restype = DWORD


def _casc_error() -> int:
    return ctypes.GetLastError() if WINDOWS else casc.GetCascError()


class CASC_FIND_DATA(ctypes.Structure):
    _fields_ = [
        ("szFileName", ctypes.c_char * MAX_PATH),
        ("CKey", ctypes.c_ubyte * 16),
        ("EKey", ctypes.c_ubyte * 16),
        ("TagBitMask", ctypes.c_uint64),
        ("FileSize", ctypes.c_uint64),
        ("szPlainName", ctypes.c_char_p),
        ("dwFileDataId", DWORD),
        ("dwLocaleFlags", DWORD),
        ("dwContentFlags", DWORD),
        ("dwSpanCount", DWORD),
        ("bFileAvailable", DWORD),  # 1-bit bitfield in a DWORD
        ("NameType", ctypes.c_int),  # CASC_NAME_TYPE enum
    ]


casc.CascFindFirstFile.argtypes = [HANDLE, ctypes.c_char_p, ctypes.POINTER(CASC_FIND_DATA), ctypes.c_char_p]
casc.CascFindFirstFile.restype = HANDLE
casc.CascFindNextFile.argtypes = [HANDLE, ctypes.POINTER(CASC_FIND_DATA)]
casc.CascFindNextFile.restype = ctypes.c_bool
casc.CascFindClose.argtypes = [HANDLE]
casc.CascFindClose.restype = ctypes.c_bool


def casc_files(storage: HANDLE, mask: str = "*") -> list[tuple[str, int, bool]]:
    """(name, size, available locally) for every named file matching mask."""
    data = CASC_FIND_DATA()
    find = casc.CascFindFirstFile(storage, _encode(mask), ctypes.byref(data), None)
    out = []
    if not find:
        return out
    try:
        while True:
            if data.NameType == 0:  # CascNameFull
                out.append((_decode(data.szFileName), data.FileSize, bool(data.bFileAvailable & 1)))
            if not casc.CascFindNextFile(find, ctypes.byref(data)):
                break
    finally:
        casc.CascFindClose(find)
    return out


def open_casc(game_dir: str | Path) -> HANDLE:
    handle = HANDLE()
    if not casc.CascOpenStorage(_encode(str(game_dir)), 0, ctypes.byref(handle)):
        raise OSError(_casc_error(), f"CascOpenStorage failed: {game_dir}")
    return handle


def casc_read(storage: HANDLE, name: str) -> bytes:
    """Read a whole file, e.g. 'data:data/global/excel/skills.txt'."""
    fh = HANDLE()
    if not casc.CascOpenFile(storage, _encode(name), 0, 0, ctypes.byref(fh)):
        raise FileNotFoundError(_casc_error(), name)
    try:
        size = casc.CascGetFileSize(fh, None)
        buf = ctypes.create_string_buffer(size)
        read = DWORD()
        if not casc.CascReadFile(fh, buf, size, ctypes.byref(read)):
            raise OSError(_casc_error(), f"CascReadFile failed: {name}")
        return buf.raw[: read.value]
    finally:
        casc.CascCloseFile(fh)


def open_mpq(path: str | Path) -> HANDLE:
    handle = HANDLE()
    if not storm.SFileOpenArchive(_encode(str(path)), 0, STREAM_FLAG_READ_ONLY, ctypes.byref(handle)):
        raise OSError(_storm_error(), f"SFileOpenArchive failed: {path}")
    return handle
