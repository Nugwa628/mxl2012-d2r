// Test harness: input for unattended test runs (off unless mxl2012-testharness.txt sits next to the DLL).
//
// Stage 1 (this file, mode "trace"): find out which Windows input calls D2R makes. Every user32 call ends in a
// win32u syscall stub of the fixed shape
//     4c 8b d1 / b8 <ssn32> / f6 04 25 08 03 fe 7f 01 / 75 03 / 0f 05 / c3 / cd 2e / c3
// (checked byte for byte before patching, nothing rip-relative in the 16 bytes that are copied). The first 14 bytes
// become `jmp [rip+0]; dq hook`, the trampoline holds the copied 16 bytes and a jump back to stub+16.
#include "testharness.h"


#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <share.h>
#include <cstring>

namespace {

constexpr int MaxCallers = 24;

struct Stat {
	const char* label = nullptr;
	volatile LONG64 calls = 0;
	void* callers[MaxCallers] = {};
	volatile LONG64 callerCalls[MaxCallers] = {};
	int callerCount = 0;
	uint64_t lastArgs[4] = {};
};

SRWLOCK g_lock = SRWLOCK_INIT;
char g_dir[MAX_PATH] = "";
volatile LONG g_running = 0;
HANDLE g_thread = nullptr;

using Fn = int64_t (*)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t,
                       uint64_t, uint64_t);

auto ModuleOf(void* address, char* out, size_t outSize, uint64_t* offset) noexcept -> bool {
	HMODULE module = nullptr;
	if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                        static_cast<LPCSTR>(address), &module) ||
	    module == nullptr) {
		return false;
	}
	char path[MAX_PATH] = "";
	GetModuleFileNameA(module, path, MAX_PATH);
	const char* slash = std::strrchr(path, '\\');
	std::snprintf(out, outSize, "%s", slash != nullptr ? slash + 1 : path);
	*offset = reinterpret_cast<uint64_t>(address) - reinterpret_cast<uint64_t>(module);
	return true;
}

auto IsSystemFrame(void* address) noexcept -> bool {
	char name[64];
	uint64_t offset = 0;
	if (!ModuleOf(address, name, sizeof(name), &offset)) {
		return false;
	}
	return _stricmp(name, "user32.dll") == 0 || _stricmp(name, "win32u.dll") == 0 || _stricmp(name, "ntdll.dll") == 0 ||
	       _stricmp(name, "mxl2012-core.dll") == 0 || _stricmp(name, "gdi32.dll") == 0 || _stricmp(name, "gdi32full.dll") == 0;
}

void Note(Stat* stat, uint64_t a0 = 0, uint64_t a1 = 0, uint64_t a2 = 0, uint64_t a3 = 0) noexcept {
	stat->lastArgs[0] = a0;
	stat->lastArgs[1] = a1;
	stat->lastArgs[2] = a2;
	stat->lastArgs[3] = a3;
	InterlockedIncrement64(&stat->calls);
	void* frames[10];
	const USHORT n = RtlCaptureStackBackTrace(1, 10, frames, nullptr);
	void* caller = n > 0 ? frames[0] : nullptr;
	for (USHORT i = 0; i < n; ++i) {
		if (!IsSystemFrame(frames[i])) {
			caller = frames[i];
			break;
		}
	}
	AcquireSRWLockExclusive(&g_lock);
	int slot = -1;
	for (int i = 0; i < stat->callerCount; ++i) {
		if (stat->callers[i] == caller) {
			slot = i;
			break;
		}
	}
	if (slot < 0 && stat->callerCount < MaxCallers) {
		slot = stat->callerCount++;
		stat->callers[slot] = caller;
	}
	if (slot >= 0) {
		++stat->callerCalls[slot];
	}
	ReleaseSRWLockExclusive(&g_lock);
}

#define HARNESS_FUNCTIONS(X)                                                                                         \
	X(NtUserGetCursorInfo) X(NtUserGetRawInputData) X(NtUserGetRawInputBuffer)                \
	X(NtUserGetAsyncKeyState) X(NtUserGetKeyboardState) X(NtUserGetMessage) \
	X(NtUserGetPointerInfoList) X(NtUserMapWindowPoints) X(NtUserRegisterRawInputDevices)      \
	X(NtUserGetMouseMovePointsEx) X(NtUserGetForegroundWindow) X(NtUserGetKeyNameText) X(NtUserSetCapture)          \
	X(NtUserGetGUIThreadInfo) X(NtUserGetClipCursor) X(NtUserSetCursor) X(NtUserGetKeyboardLayout) \
	X(NtUserGetPointerDevices) X(NtUserGetTouchInputInfo) X(NtUserGetCapture) X(NtUserSetWindowsHookEx) X(NtUserSetFocus) X(NtUserSetWindowPos) X(NtUserSetWindowLongPtr) X(NtUserSetWindowLong)

#define DECLARE(name)                                                                                               \
	Stat g_stat_##name;                                                                                             \
	Fn g_orig_##name = nullptr;                                                                                     \
	int64_t H_##name(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h, \
	                 uint64_t i, uint64_t j, uint64_t k, uint64_t l) {                                                \
		Note(&g_stat_##name, a, b, c, d);                                                                                       \
		return g_orig_##name(a, b, c, d, e, f, g, h, i, j, k, l);                                                   \
	}
HARNESS_FUNCTIONS(DECLARE)
#undef DECLARE

#define HARNESS_ALL(X) HARNESS_FUNCTIONS(X) X(NtUserGetCursorPos) X(NtUserGetKeyState) X(NtUserSetCursorPos) X(NtUserClipCursor) X(NtUserSetForegroundWindow) X(NtUserPeekMessage) X(NtUserTrackMouseEvent) X(NtUserShowWindow) X(NtUserSetActiveWindow) X(NtUserCreateWindowEx)

// Virtual input, shared with tools/game_ctl.py through the mapping "Local\mxl2012-testharness-input-<game PID>". While `active` is
// set, GetCursorPos returns the virtual client position (as screen coordinates of the game window), and GetKeyState
// reports the virtual mouse buttons and modifiers instead of the real ones. The real cursor is never touched.
struct Shared {
	uint32_t magic;  // 0x4d58 when the plugin created it
	uint32_t active;
	int32_t x;  // client coordinates of the game window
	int32_t y;
	uint32_t buttons;  // bit0 left, bit1 right
	uint32_t mods;     // bit0 shift, bit1 ctrl, bit2 alt
	uint32_t seq;
	uint32_t reserved;  // bit0: the game may not bring itself to the front (SetForegroundWindow)
	uint32_t cmdSeq;    // console command mailbox: bump cmdSeq after writing `cmd`, the plugin sets cmdDone = cmdSeq
	uint32_t cmdDone;
	int32_t cmdResult;  // 1 handled, 0 not handled, -2 crashed
	uint32_t inGame;
	uint32_t pad[4];
	char cmd[512];  // offset 64
};
Shared* g_shared = nullptr;
HWND g_hwnd = nullptr;

auto GameWindow() noexcept -> HWND {
	if (g_hwnd != nullptr && IsWindow(g_hwnd) != 0) {
		return g_hwnd;
	}
	g_hwnd = nullptr;
	EnumWindows(
	    [](HWND w, LPARAM) -> BOOL {
		    DWORD pid = 0;
		    GetWindowThreadProcessId(w, &pid);
		    char title[64] = "";
		    if (pid == GetCurrentProcessId() && IsWindowVisible(w) != 0 && GetWindowTextA(w, title, sizeof(title)) > 0 &&
		        std::strncmp(title, "Diablo II: Resurrected", 22) == 0) {  // also "... [s2]" (tag=)
			    g_hwnd = w;
			    return FALSE;
		    }
		    return TRUE;
	    },
	    0);
	return g_hwnd;
}

Stat g_stat_NtUserGetCursorPos;
Fn g_orig_NtUserGetCursorPos = nullptr;
int64_t H_NtUserGetCursorPos(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                             uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserGetCursorPos, a, b, c, d);
	const int64_t result = g_orig_NtUserGetCursorPos(a, b, c, d, e, f, g, h, i, j, k, l);
	if (g_shared != nullptr && g_shared->active != 0 && a != 0) {
		const HWND window = GameWindow();
		POINT pt {g_shared->x, g_shared->y};
		if (window != nullptr && ClientToScreen(window, &pt) != 0) {
			*reinterpret_cast<POINT*>(a) = pt;
		}
	}
	return result;
}

volatile LONG64 g_vkCounts[256] = {};

// The virtual state of a mouse button or modifier key: true with *down set when the harness answers for `vk`.
auto VirtualKeyState(uint32_t vk, bool* down) noexcept -> bool {
	if (g_shared == nullptr || g_shared->active == 0) {
		return false;
	}
	switch (vk & 0xff) {
	case 0x01: *down = (g_shared->buttons & 1) != 0; return true;
	case 0x02: *down = (g_shared->buttons & 2) != 0; return true;
	case 0x10: case 0xa0: case 0xa1: *down = (g_shared->mods & 1) != 0; return true;
	case 0x11: case 0xa2: case 0xa3: *down = (g_shared->mods & 2) != 0; return true;
	case 0x12: case 0xa4: case 0xa5: *down = (g_shared->mods & 4) != 0; return true;
	default: return false;
	}
}

Stat g_stat_NtUserGetKeyState;
Fn g_orig_NtUserGetKeyState = nullptr;
int64_t H_NtUserGetKeyState(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                            uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserGetKeyState, a, b, c, d);
	InterlockedIncrement64(&g_vkCounts[a & 0xff]);
	int64_t result = g_orig_NtUserGetKeyState(a, b, c, d, e, f, g, h, i, j, k, l);
	if (bool down = false; VirtualKeyState(static_cast<uint32_t>(a), &down)) {
		result = down ? static_cast<int64_t>(static_cast<int16_t>(0x8000)) : 0;
	}
	return result;
}

// user32!GetKeyState mostly answers from the thread's cached key state without the syscall above, and posted key
// messages never update that cache, so a posted Ctrl was invisible to D2R's item clicks (Ctrl-click quick move, bug #503).
// The game exe's import of GetKeyState is redirected here as well.
using GetKeyStateFn = SHORT(WINAPI*)(int);
GetKeyStateFn g_origGetKeyState = nullptr;
volatile LONG64 g_iatKeyStateCalls = 0;
SHORT WINAPI H_GetKeyState(int vk) {
	InterlockedIncrement64(&g_iatKeyStateCalls);
	InterlockedIncrement64(&g_vkCounts[vk & 0xff]);
	if (bool down = false; VirtualKeyState(static_cast<uint32_t>(vk), &down)) {
		return down ? static_cast<SHORT>(0x8000) : 0;
	}
	return g_origGetKeyState(vk);
}

// Replaces the exe's import address table slots that hold `module!name` (matched by the resolved address: the
// game exe keeps no name thunks for every import) with `hook`; false when no slot holds it.
auto PatchImport(HMODULE exe, const char* module, const char* name, void* hook, void** original) noexcept -> bool {
	HMODULE target = GetModuleHandleA(module);
	const auto resolved = target != nullptr ? reinterpret_cast<ULONGLONG>(GetProcAddress(target, name)) : 0;
	if (resolved == 0) {
		return false;
	}
	auto* base = reinterpret_cast<uint8_t*>(exe);
	const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
	const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
	const IMAGE_DATA_DIRECTORY& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IAT];
	if (dir.VirtualAddress == 0 || dir.Size < sizeof(ULONGLONG)) {
		return false;
	}
	auto* slots = reinterpret_cast<ULONGLONG*>(base + dir.VirtualAddress);
	bool patched = false;
	for (size_t n = 0; n < dir.Size / sizeof(ULONGLONG); ++n) {
		if (slots[n] != resolved) {
			continue;
		}
		DWORD old = 0;
		if (!VirtualProtect(&slots[n], sizeof(ULONGLONG), PAGE_READWRITE, &old)) {
			continue;
		}
		*original = reinterpret_cast<void*>(resolved);
		slots[n] = reinterpret_cast<ULONGLONG>(hook);
		VirtualProtect(&slots[n], sizeof(ULONGLONG), old, &old);
		patched = true;
	}
	return patched;
}

// D2R moves and confines the real cursor on its own (SetCursorPos, ClipCursor): while the virtual input is active
// those calls only move the virtual cursor / do nothing, so a test run never touches the user's mouse.
// Console commands: tools/game_ctl.py writes a command into the block and bumps cmdSeq; the UI thread (the one that
// pumps the game window's messages) runs it through D2RCore's ExecuteConsoleCommand export and sets cmdDone.
using ExecuteConsoleCommandFn = bool(__fastcall*)(const char*) noexcept;
using IsInGameFn = bool(__cdecl*)() noexcept;
ExecuteConsoleCommandFn g_execute = nullptr;
IsInGameFn g_isInGame = nullptr;
volatile LONG g_inCommand = 0;
volatile LONG64 g_msgCounts[0x400] = {};
volatile LONG g_ringPos = 0;
uint64_t g_ring[32][2] = {};

auto RunCommandSafe(const char* command) noexcept -> int {
	__try {
		return g_execute(command) ? 1 : 0;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return -2;
	}
}

void ServiceCommands() noexcept {
	if (g_shared == nullptr || g_execute == nullptr || g_shared->cmdSeq == g_shared->cmdDone || g_inCommand != 0) {
		return;
	}
	const HWND window = GameWindow();
	if (window == nullptr || GetWindowThreadProcessId(window, nullptr) != GetCurrentThreadId()) {
		return;  // only the UI thread runs console commands
	}
	g_inCommand = 1;
	const uint32_t seq = g_shared->cmdSeq;
	char command[512];
	std::memcpy(command, g_shared->cmd, sizeof(command));
	command[sizeof(command) - 1] = '\0';
	// "h <verb> ..." are the harness's own gameplay commands (harness_cmds.cpp), anything else is a console line.
	g_shared->cmdResult = (command[0] == 'h' && (command[1] == ' ' || command[1] == '\0')) ? HarnessCommand(command)
	                                                                                       : RunCommandSafe(command);
	g_shared->cmdDone = seq;
	g_inCommand = 0;
}

Stat g_stat_NtUserPeekMessage;
Fn g_orig_NtUserPeekMessage = nullptr;
int64_t H_NtUserPeekMessage(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                            uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserPeekMessage, a, b, c, d);
	ServiceCommands();
	const int64_t result = g_orig_NtUserPeekMessage(a, b, c, d, e, f, g, h, i, j, k, l);
	if ((result & 0xff) != 0 && a != 0) {
		const auto* msg = reinterpret_cast<const uint32_t*>(a);
		const uint32_t id = msg[2];  // MSG: hwnd (8), message (4), ...
		if (id < 0x400) {
			InterlockedIncrement64(&g_msgCounts[id]);
		}
		if ((id >= 0x100 && id <= 0x105) || (id >= 0x200 && id <= 0x20a && id != 0x200)) {
			const LONG pos = InterlockedIncrement(&g_ringPos) & 31;
			g_ring[pos][0] = id;
			g_ring[pos][1] = *reinterpret_cast<const uint64_t*>(a + 16);
		}
	}
	return result;
}

Stat g_stat_NtUserSetCursorPos;
Fn g_orig_NtUserSetCursorPos = nullptr;
int64_t H_NtUserSetCursorPos(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                             uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserSetCursorPos, a, b, c, d);
	if (g_shared != nullptr && g_shared->active != 0) {
		const HWND window = GameWindow();
		POINT pt {static_cast<int32_t>(a), static_cast<int32_t>(b)};
		if (window != nullptr && ScreenToClient(window, &pt) != 0) {
			g_shared->x = pt.x;
			g_shared->y = pt.y;
		}
		return 1;
	}
	return g_orig_NtUserSetCursorPos(a, b, c, d, e, f, g, h, i, j, k, l);
}

// The game asks Windows for WM_MOUSELEAVE after every mouse move (TrackMouseEvent). The real cursor is never over the game window
// in background mode, so Windows answered each move with a leave and the game dropped its hover state at once: no tooltips, no
// highlighted monsters or buttons (lane bug-backlog-b, bugs #9 / #22: the message log of the trace showed 46 moves, 46 leaves). With
// the virtual input active the request is accepted and ignored, so no leave is ever sent.
Stat g_stat_NtUserTrackMouseEvent;
Fn g_orig_NtUserTrackMouseEvent = nullptr;
int64_t H_NtUserTrackMouseEvent(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                                uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserTrackMouseEvent, a, b, c, d);
	if (g_shared != nullptr && g_shared->active != 0) {
		return 1;
	}
	return g_orig_NtUserTrackMouseEvent(a, b, c, d, e, f, g, h, i, j, k, l);
}

Stat g_stat_NtUserClipCursor;
Fn g_orig_NtUserClipCursor = nullptr;
int64_t H_NtUserClipCursor(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                           uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserClipCursor, a, b, c, d);
	if (g_shared != nullptr && g_shared->active != 0) {
		return 1;
	}
	return g_orig_NtUserClipCursor(a, b, c, d, e, f, g, h, i, j, k, l);
}

// Focus: with bit 0 of `reserved` set the game cannot bring itself to the front.
Stat g_stat_NtUserSetForegroundWindow;
Fn g_orig_NtUserSetForegroundWindow = nullptr;
int64_t H_NtUserSetForegroundWindow(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g,
                                    uint64_t h, uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserSetForegroundWindow, a, b, c, d);
	if (g_shared != nullptr && (g_shared->reserved & 1) != 0 && a == reinterpret_cast<uint64_t>(GameWindow())) {
		return 1;
	}
	return g_orig_NtUserSetForegroundWindow(a, b, c, d, e, f, g, h, i, j, k, l);
}

// The loader shows the new game window with SW_SHOW and activates it, which takes the user's focus. With bit 0 of
// `reserved` set (always, while the harness is on) it is shown with SW_SHOWNA instead and SetActiveWindow does nothing.
Stat g_stat_NtUserShowWindow;
Fn g_orig_NtUserShowWindow = nullptr;
int64_t H_NtUserShowWindow(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                           uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserShowWindow, a, b, c, d);
	if (g_shared != nullptr && (g_shared->reserved & 1) != 0 && (b & 0xff) == 5) {
		b = 8;  // SW_SHOW -> SW_SHOWNA
	}
	return g_orig_NtUserShowWindow(a, b, c, d, e, f, g, h, i, j, k, l);
}

Stat g_stat_NtUserSetActiveWindow;
Fn g_orig_NtUserSetActiveWindow = nullptr;
int64_t H_NtUserSetActiveWindow(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                                uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	Note(&g_stat_NtUserSetActiveWindow, a, b, c, d);
	if (g_shared != nullptr && (g_shared->reserved & 1) != 0) {
		return 0;
	}
	return g_orig_NtUserSetActiveWindow(a, b, c, d, e, f, g, h, i, j, k, l);
}

// Top-level windows get WS_EX_NOACTIVATE so the game window never becomes the foreground window by itself (it is
// created in front of the user's windows otherwise, for about a second). NtUserCreateWindowEx has 15 arguments.
using Fn15 = int64_t (*)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t,
                         uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
Stat g_stat_NtUserCreateWindowEx;
Fn15 g_orig_NtUserCreateWindowEx = nullptr;
// "tag=s2" in mxl2012-testharness.txt: a thread renames the game window to "Diablo II: Resurrected [s2]" as soon as it
// exists (and again if the game sets the title back). Tools of other lanes that close or screenshot "the window titled
// Diablo II: Resurrected" then never pick a test instance by mistake.
wchar_t g_titleText[64] = L"";

auto FindOwnWindow() noexcept -> HWND {
	HWND found = nullptr;
	EnumWindows(
	    [](HWND w, LPARAM out) -> BOOL {
		    DWORD pid = 0;
		    GetWindowThreadProcessId(w, &pid);
		    wchar_t title[96] = L"";
		    if (pid == GetCurrentProcessId() && IsWindowVisible(w) != 0 && GetWindowTextW(w, title, 96) > 0 &&
		        std::wcsncmp(title, L"Diablo II: Resurrected", 22) == 0) {
			    *reinterpret_cast<HWND*>(out) = w;
			    return FALSE;
		    }
		    return TRUE;
	    },
	    reinterpret_cast<LPARAM>(&found));
	return found;
}

DWORD WINAPI TitleThread(LPVOID) noexcept {
	while (g_running != 0) {
		const HWND window = FindOwnWindow();
		if (window != nullptr) {
			wchar_t now[96] = L"";
			GetWindowTextW(window, now, 96);
			if (std::wcscmp(now, L"Diablo II: Resurrected") == 0) {
				DWORD_PTR result = 0;
				SendMessageTimeoutW(window, WM_SETTEXT, 0, reinterpret_cast<LPARAM>(g_titleText), SMTO_ABORTIFHUNG | SMTO_NOTIMEOUTIFNOTHUNG,
				                    500, &result);
			}
		}
		Sleep(250);
	}
	return 0;
}

int64_t H_NtUserCreateWindowEx(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                               uint64_t i, uint64_t j, uint64_t k, uint64_t l, uint64_t m, uint64_t n, uint64_t o) {
	Note(&g_stat_NtUserCreateWindowEx, a, e, 0, 0);
	if (g_shared != nullptr && (g_shared->reserved & 1) != 0 && (e & 0x40000000U) == 0) {  // not WS_CHILD
		a |= 0x08000000U;  // WS_EX_NOACTIVATE
	}
	return g_orig_NtUserCreateWindowEx(a, b, c, d, e, f, g, h, i, j, k, l, m, n, o);
}

// Diagnostics (mxl2012-testharness.txt containing "diag"): log the named kernel objects and window lookups the game makes,
// and who ends the process, to mxl2012-testharness-diag-<pid>.log. This is how the single-instance check was found
// (docs/testing.md, parallel slots).
FILE* g_diag = nullptr;
SRWLOCK g_diagLock = SRWLOCK_INIT;

void DiagLine(const char* kind, const wchar_t* name, int length, void* const* frames, USHORT n, uint64_t extra) noexcept {
	if (g_diag == nullptr) {
		return;
	}
	AcquireSRWLockExclusive(&g_diagLock);
	std::fprintf(g_diag, "%s %.*ls extra=%llx", kind, name != nullptr ? length : 0, name != nullptr ? name : L"",
	             static_cast<unsigned long long>(extra));
	for (USHORT i = 0; i < n && i < 24; ++i) {
		char module[64] = "?";
		uint64_t offset = 0;
		ModuleOf(frames[i], module, sizeof(module), &offset);
		std::fprintf(g_diag, " | %s+0x%llx", module, static_cast<unsigned long long>(offset));
	}
	std::fprintf(g_diag, "\n");
	std::fflush(g_diag);
	ReleaseSRWLockExclusive(&g_diagLock);
}

void DiagUnicodeString(const char* kind, const void* us, uint64_t extra) noexcept {
	void* frames[8];
	const USHORT n = RtlCaptureStackBackTrace(2, 8, frames, nullptr);
	if (us == nullptr) {
		DiagLine(kind, nullptr, 0, frames, n, extra);
		return;
	}
	const auto length = *reinterpret_cast<const uint16_t*>(us);
	const auto* buffer = *reinterpret_cast<const wchar_t* const*>(static_cast<const uint8_t*>(us) + 8);
	DiagLine(kind, buffer, length / 2, frames, n, extra);
}

auto ObjectName(uint64_t objectAttributes) noexcept -> const void* {
	return objectAttributes != 0 ? *reinterpret_cast<const void* const*>(objectAttributes + 16) : nullptr;
}

#define DIAG_OBJECT_HOOK(name, attrArg)                                                                              \
	Fn g_orig_##name = nullptr;                                                                                      \
	int64_t H_##name(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h, \
	                 uint64_t i, uint64_t j, uint64_t k, uint64_t l) {                                                \
		DiagUnicodeString(#name, ObjectName(attrArg), 0);                                                           \
		return g_orig_##name(a, b, c, d, e, f, g, h, i, j, k, l);                                                   \
	}
DIAG_OBJECT_HOOK(NtCreateMutant, c)
DIAG_OBJECT_HOOK(NtOpenMutant, c)
DIAG_OBJECT_HOOK(NtCreateEvent, c)
DIAG_OBJECT_HOOK(NtOpenEvent, c)
DIAG_OBJECT_HOOK(NtCreateSemaphore, c)
DIAG_OBJECT_HOOK(NtOpenSemaphore, c)
DIAG_OBJECT_HOOK(NtCreateSection, c)
DIAG_OBJECT_HOOK(NtOpenSection, c)

// Offline-cookie shield ("nocookie" in mxl2012-testharness.txt). D2RLoader reads %LOCALAPPDATA%\Blizzard Entertainment\
// ClientSdk\cookie.bin at the frontend launch and decrypts the Battle.net session record in it with a passphrase that
// only the install Battle.net knows (C:\Program Files (x86)\Diablo II Resurrected); a copy of the game in another
// folder throws Botan::Decoding_Error there and the process dies. With this flag every open of that file fails with
// STATUS_OBJECT_NAME_NOT_FOUND, which D2R handles as "no offline cookie" (and the user's real cookie.bin is never
// read or rewritten by a test instance).
bool g_noCookie = false;

auto IsCookiePath(uint64_t objectAttributes) noexcept -> bool {
	const auto* us = static_cast<const uint8_t*>(ObjectName(objectAttributes));
	if (us == nullptr) {
		return false;
	}
	const auto length = static_cast<size_t>(*reinterpret_cast<const uint16_t*>(us)) / 2;
	const auto* name = *reinterpret_cast<const wchar_t* const*>(us + 8);
	static constexpr wchar_t Tail[] = L"ClientSdk\\cookie.bin";
	constexpr size_t TailLength = (sizeof(Tail) / sizeof(wchar_t)) - 1;
	return name != nullptr && length >= TailLength && _wcsnicmp(name + length - TailLength, Tail, TailLength) == 0;
}

// "volserial": the passphrase is derived from MachineGuid and the VOLUME SERIAL NUMBER of the drive D2RLoader.exe runs
// from (FUN_1419ed830: GetModuleFileNameW, GetVolumeInformationW, SHA-1, base64), so a copy of the game on another
// drive cannot decrypt a cookie written by the Battle.net-launched install on C:. With this flag the volume
// information the process reads reports the serial of C:. The cookie file itself is then opened read-only (writes
// are refused), so the user's real cookie.bin is never rewritten by a test instance.
uint32_t g_spoofSerial = 0;
Fn g_orig_NtQueryVolumeInformationFile = nullptr;
int64_t H_NtQueryVolumeInformationFile(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g,
                                       uint64_t h, uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	const int64_t result = g_orig_NtQueryVolumeInformationFile(a, b, c, d, e, f, g, h, i, j, k, l);
	// (FileHandle, IoStatusBlock, FsInformation, Length, FsInformationClass); class 1 = FileFsVolumeInformation
	if (result >= 0 && g_spoofSerial != 0 && static_cast<uint32_t>(e) == 1 && static_cast<uint32_t>(d) >= 12 && c != 0) {
		*reinterpret_cast<uint32_t*>(c + 8) = g_spoofSerial;  // FILE_FS_VOLUME_INFORMATION.VolumeSerialNumber
	}
	return result;
}
bool g_keepCookieReadOnly = false;

#define FILE_OPEN_HOOK(name)                                                                                         \
	Fn g_orig_##name = nullptr;                                                                                      \
	int64_t H_##name(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h, \
	                 uint64_t i, uint64_t j, uint64_t k, uint64_t l) {                                                \
		if (g_noCookie && IsCookiePath(c)) {                                                                        \
			DiagUnicodeString(#name " (denied)", ObjectName(c), 0);                                                 \
			return static_cast<int64_t>(static_cast<int32_t>(0xC0000034));                                          \
		}                                                                                                           \
		if (g_keepCookieReadOnly && (static_cast<uint32_t>(b) & (0x40000000U | 0x10000000U | 0x2U | 0x4U | 0x10000U)) != 0 && \
		    IsCookiePath(c)) {                                                                                      \
			DiagUnicodeString(#name " (write refused)", ObjectName(c), static_cast<uint32_t>(b));                   \
			return static_cast<int64_t>(static_cast<int32_t>(0xC0000022));                                          \
		}                                                                                                           \
		const int64_t status = g_orig_##name(a, b, c, d, e, f, g, h, i, j, k, l);                                   \
		if (g_diag != nullptr) { /* extra = the NTSTATUS: 0 opened, c0000034 / c000003a not there */               \
			DiagUnicodeString(#name, ObjectName(c), static_cast<uint32_t>(status));                                 \
		}                                                                                                           \
		return status;                                                                                              \
	}
FILE_OPEN_HOOK(NtCreateFile)
FILE_OPEN_HOOK(NtOpenFile)

// NtUserFindWindowEx(parent, child, className UNICODE_STRING*, windowName UNICODE_STRING*, type)
Fn g_orig_NtUserFindWindowEx = nullptr;
int64_t H_NtUserFindWindowEx(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                             uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	DiagUnicodeString("FindWindow.class", reinterpret_cast<const void*>(c), 0);
	DiagUnicodeString("FindWindow.title", reinterpret_cast<const void*>(d), 0);
	return g_orig_NtUserFindWindowEx(a, b, c, d, e, f, g, h, i, j, k, l);
}

Fn g_orig_NtTerminateProcess = nullptr;
int64_t H_NtTerminateProcess(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                             uint64_t i, uint64_t j, uint64_t k, uint64_t l) {
	if (a == 0 || a == static_cast<uint64_t>(-1) || GetProcessId(reinterpret_cast<HANDLE>(a)) == GetCurrentProcessId()) {
		void* frames[10];
		const USHORT n = RtlCaptureStackBackTrace(1, 10, frames, nullptr);
		DiagLine("NtTerminateProcess", L"self", 4, frames, n, b);
	}
	return g_orig_NtTerminateProcess(a, b, c, d, e, f, g, h, i, j, k, l);
}

// C++ exceptions (code 0xe06d7363): log the thrown type and, for std::exception-like objects, the message.
LONG CALLBACK DiagVectoredHandler(PEXCEPTION_POINTERS info) noexcept {
	const EXCEPTION_RECORD* rec = info->ExceptionRecord;
	if (g_diag == nullptr || rec->ExceptionCode != 0xe06d7363U || rec->NumberParameters < 4) {
		return EXCEPTION_CONTINUE_SEARCH;
	}
	char type[200] = "?";
	char what[200] = "";
	__try {
		const auto base = static_cast<uint64_t>(rec->ExceptionInformation[3]);
		const auto* throwInfo = reinterpret_cast<const int32_t*>(rec->ExceptionInformation[2]);
		const auto* array = reinterpret_cast<const int32_t*>(base + static_cast<uint32_t>(throwInfo[3]));  // pCatchableTypeArray
		const auto* catchable = reinterpret_cast<const int32_t*>(base + static_cast<uint32_t>(array[1]));
		const auto* descriptor = reinterpret_cast<const char*>(base + static_cast<uint32_t>(catchable[1]));
		std::snprintf(type, sizeof(type), "%.190s", descriptor + 16);  // TypeDescriptor: vftable, spare, name
		const auto* object = reinterpret_cast<const uint64_t*>(rec->ExceptionInformation[1]);
		const char* text = reinterpret_cast<const char*>(object[1]);
		if (text != nullptr && reinterpret_cast<uint64_t>(text) > 0x10000) {
			std::snprintf(what, sizeof(what), "%.190s", text);
		}
		// Botan::Exception keeps its message in a std::string right after std::exception (24 bytes)
		const auto* message = reinterpret_cast<const uint64_t*>(reinterpret_cast<const uint8_t*>(object) + 24);
		const char* data = message[2] >= 16 ? *reinterpret_cast<const char* const*>(message) : reinterpret_cast<const char*>(message);
		if (message[1] < 200) {
			std::snprintf(what + std::strlen(what), sizeof(what) - std::strlen(what), " msg='%.100s'", data);
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
	void* frames[16];
	const USHORT n = RtlCaptureStackBackTrace(0, 16, frames, nullptr);
	char line[420];
	std::snprintf(line, sizeof(line), "%s what='%s'", type, what);
	wchar_t wide[420];
	MultiByteToWideChar(CP_ACP, 0, line, -1, wide, 420);
	DiagLine("CxxException", wide, static_cast<int>(std::wcslen(wide)), frames, n, 0);
	// The loader is protected: its code has no unwind data, so walk the raw stack for return addresses into it.
	{
		const auto exe = reinterpret_cast<uint64_t>(GetModuleHandleA(nullptr));
		IMAGE_NT_HEADERS* nt = reinterpret_cast<IMAGE_NT_HEADERS*>(exe + reinterpret_cast<IMAGE_DOS_HEADER*>(exe)->e_lfanew);
		const uint64_t size = nt->OptionalHeader.SizeOfImage;
		void* hits[24];
		USHORT count = 0;
		__try {
			const auto* sp = reinterpret_cast<const uint64_t*>(info->ContextRecord->Rsp);
			for (int i = 0; i < 1024 && count < 24; ++i) {
				if (sp[i] > exe && sp[i] < exe + size) {
					hits[count++] = reinterpret_cast<void*>(sp[i]);
				}
			}
		} __except (EXCEPTION_EXECUTE_HANDLER) {
		}
		DiagLine("CxxException.stack", L"", 0, hits, count, 0);
	}
	return EXCEPTION_CONTINUE_SEARCH;
}

// Inline hook on a function in D2RLoader.exe's decrypted image: the first `copyLength` bytes must be exactly
// `expected` (instruction boundary, nothing rip-relative among them); they move to a trampoline that jumps back.
auto PatchRaw(void* target, const uint8_t* expected, size_t copyLength, void* hook, void** original) noexcept -> bool {
	if (copyLength < 14 || copyLength > 32 || std::memcmp(target, expected, copyLength) != 0) {
		return false;
	}
	auto* trampoline = static_cast<uint8_t*>(VirtualAlloc(nullptr, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
	if (trampoline == nullptr) {
		return false;
	}
	std::memcpy(trampoline, target, copyLength);
	trampoline[copyLength] = 0xff;
	trampoline[copyLength + 1] = 0x25;
	std::memset(trampoline + copyLength + 2, 0, 4);
	const uint64_t back = reinterpret_cast<uint64_t>(target) + copyLength;
	std::memcpy(trampoline + copyLength + 6, &back, 8);
	DWORD old = 0;
	if (!VirtualProtect(target, copyLength, PAGE_EXECUTE_READWRITE, &old)) {
		return false;
	}
	uint8_t jump[14] = {0xff, 0x25, 0, 0, 0, 0};
	const uint64_t destination = reinterpret_cast<uint64_t>(hook);
	std::memcpy(jump + 6, &destination, 8);
	std::memcpy(target, jump, 14);
	for (size_t i = 14; i < copyLength; ++i) {
		static_cast<uint8_t*>(target)[i] = 0xcc;
	}
	VirtualProtect(target, copyLength, old, &old);
	FlushInstructionCache(GetCurrentProcess(), target, copyLength);
	*original = trampoline;
	return true;
}

// D2RLoader 1.3.1 (image base 0x140000000): the signature check + CryptoBox decrypt of one offline-cookie record.
// struct {out, verifier, pemHeader, pemFooter, const char** passphrase}, record. Diagnostics only.
using CookieRecordFn = int64_t (*)(void*, void*);
CookieRecordFn g_origCookieRecord = nullptr;
int64_t H_CookieRecord(void* self, void* record) {
	if (g_diag != nullptr) {
		char pass[160] = "?";
		__try {
			const char* const* p = *reinterpret_cast<const char* const* const*>(static_cast<uint8_t*>(self) + 32);
			std::snprintf(pass, sizeof(pass), "%.150s", *p);
		} __except (EXCEPTION_EXECUTE_HANDLER) {
		}
		wchar_t wide[200];
		MultiByteToWideChar(CP_ACP, 0, pass, -1, wide, 200);
		void* frames[2] = {};
		DiagLine("CookieRecord.passphrase", wide, static_cast<int>(std::wcslen(wide)), frames, 0, reinterpret_cast<uint64_t>(record));
		for (int field = 6; field <= 10; ++field) {  // what the record holds: text fields as std::string-like {data, size}
			char text[200] = "?";
			__try {
				const auto* s = *reinterpret_cast<const uint64_t* const*>(static_cast<uint8_t*>(record) + field * 8);
				const uint64_t size = s[1];
				const char* data = size >= 16 ? *reinterpret_cast<const char* const*>(s) : reinterpret_cast<const char*>(s);
				std::snprintf(text, sizeof(text), "field %d size %llu: %.120s", field, static_cast<unsigned long long>(size),
				              size < 4096 ? data : "(big)");
			} __except (EXCEPTION_EXECUTE_HANDLER) {
			}
			MultiByteToWideChar(CP_ACP, 0, text, -1, wide, 200);
			DiagLine("CookieRecord.field", wide, static_cast<int>(std::wcslen(wide)), frames, 0, 0);
		}
	}
	return g_origCookieRecord(self, record);
}

// The CryptoBox decrypt (0x1bb9510): (out vector, PEM text, length, passphrase). Diagnostics only.
using CryptoBoxFn = void (*)(void*, const char*, int64_t, void*);
CryptoBoxFn g_origCryptoBox = nullptr;
void H_CryptoBox(void* out, const char* data, int64_t length, void* pass) {
	if (g_diag != nullptr) {
		char text[260] = "?";
		__try {
			std::snprintf(text, sizeof(text), "len %lld: %.200s", static_cast<long long>(length), data);
			for (char* c = text; *c != '\0'; ++c) {
				if (*c == '\n') {
					*c = '|';
				}
			}
		} __except (EXCEPTION_EXECUTE_HANDLER) {
		}
		wchar_t wide[300];
		MultiByteToWideChar(CP_ACP, 0, text, -1, wide, 300);
		void* frames[1] = {};
		DiagLine("CryptoBox.input", wide, static_cast<int>(std::wcslen(wide)), frames, 0, 0);
	}
	g_origCryptoBox(out, data, length, pass);
}

auto Patch(void* stub, void* hook, void** original) noexcept -> bool {
	static const uint8_t Shape[16] = {0x4c, 0x8b, 0xd1, 0xb8, 0, 0, 0, 0, 0xf6, 0x04, 0x25, 0x08, 0x03, 0xfe, 0x7f, 0x01};
	const auto* code = static_cast<const uint8_t*>(stub);
	for (int i = 0; i < 16; ++i) {
		if (i >= 4 && i < 8) {
			continue;  // syscall number
		}
		if (code[i] != Shape[i]) {
			return false;
		}
	}
	if (code[16] != 0x75 || code[17] != 0x03 || code[18] != 0x0f || code[19] != 0x05 || code[20] != 0xc3 || code[21] != 0xcd ||
	    code[22] != 0x2e || code[23] != 0xc3) {
		return false;
	}
	auto* trampoline = static_cast<uint8_t*>(VirtualAlloc(nullptr, 64, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE));
	if (trampoline == nullptr) {
		return false;
	}
	std::memcpy(trampoline, code, 16);
	trampoline[16] = 0xff;
	trampoline[17] = 0x25;
	std::memset(trampoline + 18, 0, 4);
	const uint64_t back = reinterpret_cast<uint64_t>(stub) + 16;
	std::memcpy(trampoline + 22, &back, 8);
	DWORD old = 0;
	if (!VirtualProtect(stub, 16, PAGE_EXECUTE_READWRITE, &old)) {
		return false;
	}
	uint8_t jump[14] = {0xff, 0x25, 0, 0, 0, 0};
	const uint64_t target = reinterpret_cast<uint64_t>(hook);
	std::memcpy(jump + 6, &target, 8);
	std::memcpy(stub, jump, 14);
	VirtualProtect(stub, 16, old, &old);
	FlushInstructionCache(GetCurrentProcess(), stub, 16);
	*original = trampoline;
	return true;
}

void DumpTrace() noexcept {
	char path[MAX_PATH];
	std::snprintf(path, sizeof(path), "%smxl2012-testharness-trace.log", g_dir);
	FILE* f = nullptr;
	if (fopen_s(&f, path, "wb") != 0 || f == nullptr) {
		return;
	}
#define DUMP(name)                                                                                                  \
	if (g_stat_##name.label != nullptr) {                                                                            \
		std::fprintf(f, "%s calls=%lld last args %llx %llx %llx %llx\n", g_stat_##name.label,                       \
		             static_cast<long long>(g_stat_##name.calls),                                                   \
		             static_cast<unsigned long long>(g_stat_##name.lastArgs[0]),                                    \
		             static_cast<unsigned long long>(g_stat_##name.lastArgs[1]),                                    \
		             static_cast<unsigned long long>(g_stat_##name.lastArgs[2]),                                    \
		             static_cast<unsigned long long>(g_stat_##name.lastArgs[3]));                                   \
		AcquireSRWLockShared(&g_lock);                                                                              \
		for (int i = 0; i < g_stat_##name.callerCount; ++i) {                                                       \
			char module[64] = "?";                                                                                  \
			uint64_t offset = 0;                                                                                    \
			ModuleOf(g_stat_##name.callers[i], module, sizeof(module), &offset);                                    \
			std::fprintf(f, "    %lld x %s+0x%llx\n", static_cast<long long>(g_stat_##name.callerCalls[i]), module, \
			             static_cast<unsigned long long>(offset));                                                  \
		}                                                                                                           \
		ReleaseSRWLockShared(&g_lock);                                                                              \
	}
	HARNESS_ALL(DUMP)
	std::fprintf(f, "GetKeyState import calls %lld; vk histogram (syscall and import):", static_cast<long long>(g_iatKeyStateCalls));
	for (int vk = 0; vk < 256; ++vk) {
		if (g_vkCounts[vk] != 0) {
			std::fprintf(f, " %02x:%lld", vk, static_cast<long long>(g_vkCounts[vk]));
		}
	}
	std::fprintf(f, "\nmessages the game took from PeekMessage:");
	for (int id = 0; id < 0x400; ++id) {
		if (g_msgCounts[id] != 0) {
			std::fprintf(f, " %x:%lld", id, static_cast<long long>(g_msgCounts[id]));
		}
	}
	std::fprintf(f, "\nlast key/mouse-button messages (id wparam):");
	for (int n = 0; n < 32; ++n) {
		const int idx = (g_ringPos + 1 + n) & 31;
		if (g_ring[idx][0] != 0) {
			std::fprintf(f, " %llx/%llx", static_cast<unsigned long long>(g_ring[idx][0]), static_cast<unsigned long long>(g_ring[idx][1]));
		}
	}
	std::fprintf(f, "\nExecuteConsoleCommand %s, IsInGame %s, UI-thread commands run: seq %u done %u result %d\n",
	             g_execute != nullptr ? "found" : "MISSING", g_isInGame != nullptr ? "found" : "missing",
	             g_shared != nullptr ? g_shared->cmdSeq : 0, g_shared != nullptr ? g_shared->cmdDone : 0,
	             g_shared != nullptr ? g_shared->cmdResult : 0);
#undef DUMP
	std::fclose(f);
}

DWORD WINAPI TraceThread(LPVOID) noexcept {
	while (g_running != 0) {
		Sleep(3000);
		DumpTrace();
	}
	return 0;
}

auto ReadMode(char* mode, size_t size) noexcept -> bool {
	HMODULE self = nullptr;
	char path[MAX_PATH] = "";
	if (!GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
	                        reinterpret_cast<LPCSTR>(&ReadMode), &self) ||
	    GetModuleFileNameA(self, path, MAX_PATH) == 0) {
		return false;
	}
	char* slash = std::strrchr(path, '\\');
	if (slash == nullptr) {
		return false;
	}
	slash[1] = '\0';
	std::snprintf(g_dir, sizeof(g_dir), "%s", path);
	std::snprintf(slash + 1, sizeof(path) - static_cast<size_t>(slash + 1 - path), "mxl2012-testharness.txt");
	FILE* f = nullptr;
	if (fopen_s(&f, path, "rb") == 0 && f != nullptr) {
		const size_t n = std::fread(mode, 1, size - 1, f);
		mode[n] = '\0';
		std::fclose(f);
		return true;
	}
	char env[64] = "";
	if (GetEnvironmentVariableA("MXL_TESTHARNESS", env, sizeof(env)) > 0) {
		std::snprintf(mode, size, "%s", env);
		return true;
	}
	return false;
}

}  // namespace

auto InstallTestHarness(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	char mode[128] = "";
	if (!ReadMode(mode, sizeof(mode))) {
		std::snprintf(report, reportSize, "off: no mxl2012-testharness.txt next to the plugin (normal play)");
		return false;
	}
	int hooked = 0;
	int missing = 0;
	HMODULE win32u = GetModuleHandleA("win32u.dll");
	if (win32u == nullptr) {
		win32u = LoadLibraryA("win32u.dll");
	}
#define INSTALL(name)                                                                                               \
	{                                                                                                               \
		void* stub = win32u != nullptr ? reinterpret_cast<void*>(GetProcAddress(win32u, #name)) : nullptr;          \
		if (stub != nullptr && Patch(stub, reinterpret_cast<void*>(&H_##name), reinterpret_cast<void**>(&g_orig_##name))) {                   \
			g_stat_##name.label = #name;                                                                             \
			++hooked;                                                                                               \
		} else {                                                                                                    \
			++missing;                                                                                              \
		}                                                                                                           \
	}
	HARNESS_ALL(INSTALL)
#undef INSTALL
	const bool keyStateImport = PatchImport(GetModuleHandleA(nullptr), "user32.dll", "GetKeyState",
	                                        reinterpret_cast<void*>(&H_GetKeyState), reinterpret_cast<void**>(&g_origGetKeyState));
	if (std::strstr(mode, "diag") != nullptr) {
		char path[MAX_PATH];
		std::snprintf(path, sizeof(path), "%smxl2012-testharness-diag-%lu.log", g_dir, static_cast<unsigned long>(GetCurrentProcessId()));
		g_diag = _fsopen(path, "wb", _SH_DENYWR);  // readable while the game runs (lane medsounds)
		HMODULE ntdll = GetModuleHandleA("ntdll.dll");
#define DIAG_INSTALL(module, name)                                                                                  \
	if (void* stub = GetProcAddress(module, #name); stub != nullptr) {                                               \
		Patch(stub, reinterpret_cast<void*>(&H_##name), reinterpret_cast<void**>(&g_orig_##name));                   \
	}
		DIAG_INSTALL(ntdll, NtCreateMutant) DIAG_INSTALL(ntdll, NtOpenMutant) DIAG_INSTALL(ntdll, NtCreateEvent)
		DIAG_INSTALL(ntdll, NtOpenEvent) DIAG_INSTALL(ntdll, NtCreateSemaphore) DIAG_INSTALL(ntdll, NtOpenSemaphore)
		DIAG_INSTALL(ntdll, NtCreateSection) DIAG_INSTALL(ntdll, NtOpenSection) DIAG_INSTALL(ntdll, NtTerminateProcess)
		DIAG_INSTALL(ntdll, NtCreateFile) DIAG_INSTALL(ntdll, NtOpenFile)
		DIAG_INSTALL(win32u, NtUserFindWindowEx)
#undef DIAG_INSTALL
		AddVectoredExceptionHandler(1, DiagVectoredHandler);
		static const uint8_t cookieEntry[19] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x41, 0x56, 0x48, 0x8d, 0x6c,
		                                        0x24, 0xc9, 0x48, 0x81, 0xec, 0xe0, 0x00, 0x00, 0x00};
		const auto exe = reinterpret_cast<uint64_t>(GetModuleHandleA(nullptr));
		if (exe == 0x140000000ULL) {
			const bool hooked = PatchRaw(reinterpret_cast<void*>(exe + 0x19ed090), cookieEntry, sizeof(cookieEntry),
			                             reinterpret_cast<void*>(&H_CookieRecord), reinterpret_cast<void**>(&g_origCookieRecord));
			static const uint8_t cryptoBoxEntry[18] = {0x40, 0x55, 0x56, 0x57, 0x41, 0x57, 0x48, 0x8d, 0x6c,
			                                           0x24, 0xd8, 0x48, 0x81, 0xec, 0x28, 0x01, 0x00, 0x00};
			PatchRaw(reinterpret_cast<void*>(exe + 0x1bb9510), cryptoBoxEntry, sizeof(cryptoBoxEntry),
			         reinterpret_cast<void*>(&H_CryptoBox), reinterpret_cast<void**>(&g_origCryptoBox));
			void* frames[1] = {};
			DiagLine("CookieHook", hooked ? L"installed" : L"entry bytes differ (not decrypted yet or other loader build)", hooked ? 9 : 55,
			         frames, 0, 0);
		}
	}
	if (const char* tag = std::strstr(mode, "tag="); tag != nullptr) {
		char word[24] = "";
		std::sscanf(tag + 4, "%23[^ \t\r\n]", word);
		std::swprintf(g_titleText, 64, L"Diablo II: Resurrected [%hs]", word);
	}
	const bool wantNoCookie = std::strstr(mode, "nocookie") != nullptr;
	const bool wantVolSerial = std::strstr(mode, "volserial") != nullptr;
	if (wantNoCookie || wantVolSerial) {
		HMODULE ntdll = GetModuleHandleA("ntdll.dll");
		bool both = true;
		if (g_orig_NtCreateFile == nullptr) {
			both = Patch(GetProcAddress(ntdll, "NtCreateFile"), reinterpret_cast<void*>(&H_NtCreateFile),
			             reinterpret_cast<void**>(&g_orig_NtCreateFile)) && both;
			both = Patch(GetProcAddress(ntdll, "NtOpenFile"), reinterpret_cast<void*>(&H_NtOpenFile),
			             reinterpret_cast<void**>(&g_orig_NtOpenFile)) && both;
		}
		g_noCookie = wantNoCookie && both;
		if (wantVolSerial && both) {
			DWORD serial = 0;
			if (GetVolumeInformationW(L"C:\\", nullptr, 0, &serial, nullptr, nullptr, nullptr, 0) != 0 && serial != 0 &&
			    Patch(GetProcAddress(ntdll, "NtQueryVolumeInformationFile"), reinterpret_cast<void*>(&H_NtQueryVolumeInformationFile),
			          reinterpret_cast<void**>(&g_orig_NtQueryVolumeInformationFile))) {
				g_spoofSerial = serial;
				g_keepCookieReadOnly = true;
			}
		}
	}
	// One block per game process (the name ends with the PID), so up to three instances run side by side.
	char mappingName[64];
	std::snprintf(mappingName, sizeof(mappingName), "Local\\mxl2012-testharness-input-%lu",
	              static_cast<unsigned long>(GetCurrentProcessId()));
	if (HANDLE mapping = CreateFileMappingA(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, 4096, mappingName);
	    mapping != nullptr) {
		g_shared = static_cast<Shared*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(Shared)));
		if (g_shared != nullptr) {
			std::memset(g_shared, 0, sizeof(Shared));
			g_shared->magic = 0x4d58;
			// On from the first moment: the real cursor, focus and Ctrl state are none of the game's business in a test run.
			g_shared->x = 800;
			g_shared->y = 450;
			g_shared->reserved = 1;
			g_shared->active = 1;
		}
	}
	if (HMODULE core = GetModuleHandleA("D2RCore.dll"); core != nullptr) {
		FARPROC execute = GetProcAddress(core, "ExecuteConsoleCommand");
		if (execute == nullptr) {
			execute = GetProcAddress(core, MAKEINTRESOURCEA(14));
		}
		g_execute = reinterpret_cast<ExecuteConsoleCommandFn>(execute);
		g_isInGame = reinterpret_cast<IsInGameFn>(GetProcAddress(core, "IsInGame"));
	}
	HarnessCmdsInit(context->exeBase);
	HarnessCmdsContext(context);
	g_running = 1;
	g_thread = CreateThread(nullptr, 0, TraceThread, nullptr, 0, nullptr);
	if (g_titleText[0] != L'\0') {
		CreateThread(nullptr, 0, TitleThread, nullptr, 0, nullptr);
	}
	std::snprintf(report, reportSize,
	              "on (mode '%.20s'): %d win32u input calls traced to mxl2012-testharness-trace.log (%d not present), GetKeyState import %s%s",
	              mode, hooked, missing, keyStateImport ? "hooked" : "not found", g_spoofSerial != 0 ? "; volume serial of C: reported (offline cookie readable from another drive)"
	                                 : (g_noCookie ? "; offline cookie.bin hidden" : ""));
	return true;
}

void HarnessEcho(const char* line) noexcept {
	if (g_running == 0 || line == nullptr) {
		return;
	}
	char path[MAX_PATH];
	std::snprintf(path, sizeof(path), "%smxl2012-testharness-console.txt", g_dir);
	// One append per line, the open retried: tools/game_ctl.py hcmd polls this file every 100 ms (and a scanner may read it),
	// and a failed fopen_s used to drop the line silently - about 7% of the 50-line replies of `cubeslots` lost a line
	// (docs/testing.md, harness). Full sharing, the line and its newline in one WriteFile.
	char buf[512];
	const int len = std::snprintf(buf, sizeof(buf), "%s\n", line);
	if (len <= 0) {
		return;
	}
	const DWORD size = static_cast<DWORD>(len < static_cast<int>(sizeof(buf)) ? len : static_cast<int>(sizeof(buf)) - 1);
	for (int attempt = 0; attempt < 500; ++attempt) {
		HANDLE h = CreateFileA(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_ALWAYS,
		                       FILE_ATTRIBUTE_NORMAL, nullptr);
		if (h != INVALID_HANDLE_VALUE) {
			DWORD written = 0;
			WriteFile(h, buf, size, &written, nullptr);
			CloseHandle(h);
			return;
		}
		Sleep(1);
	}
}

void StopTestHarness() noexcept {
	g_running = 0;
}
