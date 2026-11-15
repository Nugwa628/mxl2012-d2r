// Taken from D2R-Legacy169 src/testharness.cpp (0.1.2, MIT, the same authors); only the switch file name differs.
// Test harness (builds with -DSTATBOOK_TEST_HARNESS=ON only; release builds do not contain this file): background input
// for unattended test runs of plain D2R, where mxl2012-core's harness is not there. It is a cut-down copy of mxl2012-core's
// plugin/src/testharness.cpp and shares its input block, so MXL2012-D2R's tools/game_ctl.py drives the game unchanged.
// Off unless statbook-testharness.txt sits next to the DLL. Its text is a list of words; "tag=s1" renames the window
// "Diablo II: Resurrected [s1]".
//
// Every user32 input call ends in a win32u syscall stub of the fixed shape
//     4c 8b d1 / b8 <ssn32> / f6 04 25 08 03 fe 7f 01 / 75 03 / 0f 05 / c3 / cd 2e / c3
// (checked byte for byte before patching). The first 14 bytes become `jmp [rip+0]; dq hook`, the trampoline holds the
// copied 16 bytes and a jump back to stub+16. While the block's `active` is set:
//   GetCursorPos returns the virtual client position, GetKeyState (syscall and the exe's import) the virtual buttons and
//   modifiers; SetCursorPos and ClipCursor only move the virtual cursor; TrackMouseEvent is accepted and ignored (no
//   WM_MOUSELEAVE); the game window never takes the foreground (SetForegroundWindow, SW_SHOW, SetActiveWindow,
//   WS_EX_NOACTIVATE). Console lines in the block run on the UI thread through D2RCore's ExecuteConsoleCommand.
// When the block already exists (mxl2012-core's harness is on in the same game) nothing is installed.
#include "testharness.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>

namespace {

using Fn = int64_t (*)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t,
                       uint64_t, uint64_t);
using Fn15 = int64_t (*)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t,
                         uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);

// The block of tools/game_ctl.py vinput() (int32[8] + the console mailbox at offset 32 and the command text at 64).
struct Shared {
	uint32_t magic;  // 0x4d58
	uint32_t active;
	int32_t x;  // client coordinates of the game window
	int32_t y;
	uint32_t buttons;  // bit0 left, bit1 right
	uint32_t mods;     // bit0 shift, bit1 ctrl, bit2 alt
	uint32_t seq;
	uint32_t reserved;  // bit0: the game may not bring itself to the front
	uint32_t cmdSeq;    // console mailbox: the tool bumps cmdSeq after writing `cmd`, the UI thread sets cmdDone = cmdSeq
	uint32_t cmdDone;
	int32_t cmdResult;  // 1 handled, 0 not handled, -2 crashed
	uint32_t inGame;
	uint32_t pad[4];
	char cmd[512];  // offset 64
};
static_assert(offsetof(Shared, cmd) == 64);

Shared* g_shared = nullptr;
HWND g_hwnd = nullptr;
volatile LONG g_running = 0;
wchar_t g_titleText[64] = L"";

auto FindGameWindow() noexcept -> HWND {
	HWND found = nullptr;
	EnumWindows(
	    [](HWND w, LPARAM out) -> BOOL {
		    DWORD pid = 0;
		    GetWindowThreadProcessId(w, &pid);
		    wchar_t title[96] = L"";
		    if (pid == GetCurrentProcessId() && IsWindowVisible(w) != 0 && GetWindowTextW(w, title, 96) > 0 &&
		        std::wcsncmp(title, L"Diablo II: Resurrected", 22) == 0) {  // also "... [s1]"
			    *reinterpret_cast<HWND*>(out) = w;
			    return FALSE;
		    }
		    return TRUE;
	    },
	    reinterpret_cast<LPARAM>(&found));
	return found;
}

auto GameWindow() noexcept -> HWND {
	if (g_hwnd == nullptr || IsWindow(g_hwnd) == 0) {
		g_hwnd = FindGameWindow();
	}
	return g_hwnd;
}

auto Active() noexcept -> bool {
	return g_shared != nullptr && g_shared->active != 0;
}

auto NoFront() noexcept -> bool {
	return g_shared != nullptr && (g_shared->reserved & 1) != 0;
}

#define HOOK(name)                \
	Fn g_orig_##name = nullptr; \
	int64_t H_##name(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h, uint64_t i, \
	                 uint64_t j, uint64_t k, uint64_t l)

HOOK(NtUserGetCursorPos) {
	const int64_t result = g_orig_NtUserGetCursorPos(a, b, c, d, e, f, g, h, i, j, k, l);
	if (Active() && a != 0) {
		const HWND window = GameWindow();
		POINT pt{g_shared->x, g_shared->y};
		if (window != nullptr && ClientToScreen(window, &pt) != 0) {
			*reinterpret_cast<POINT*>(a) = pt;
		}
	}
	return result;
}

auto VirtualKeyState(uint32_t vk, bool* down) noexcept -> bool {
	if (!Active()) {
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

HOOK(NtUserGetKeyState) {
	int64_t result = g_orig_NtUserGetKeyState(a, b, c, d, e, f, g, h, i, j, k, l);
	if (bool down = false; VirtualKeyState(static_cast<uint32_t>(a), &down)) {
		result = down ? static_cast<int64_t>(static_cast<int16_t>(0x8000)) : 0;
	}
	return result;
}

// user32!GetKeyState mostly answers from the thread's cached key state without the syscall: the exe's import too.
using GetKeyStateFn = SHORT(WINAPI*)(int);
GetKeyStateFn g_origGetKeyState = nullptr;
SHORT WINAPI H_GetKeyState(int vk) {
	if (bool down = false; VirtualKeyState(static_cast<uint32_t>(vk), &down)) {
		return down ? static_cast<SHORT>(0x8000) : 0;
	}
	return g_origGetKeyState(vk);
}

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
		DWORD old = 0;
		if (slots[n] != resolved || !VirtualProtect(&slots[n], sizeof(ULONGLONG), PAGE_READWRITE, &old)) {
			continue;
		}
		*original = reinterpret_cast<void*>(resolved);
		slots[n] = reinterpret_cast<ULONGLONG>(hook);
		VirtualProtect(&slots[n], sizeof(ULONGLONG), old, &old);
		patched = true;
	}
	return patched;
}

using ExecuteConsoleCommandFn = bool(__fastcall*)(const char*) noexcept;
ExecuteConsoleCommandFn g_execute = nullptr;
volatile LONG g_inCommand = 0;

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
	g_shared->cmdResult = RunCommandSafe(command);
	g_shared->cmdDone = seq;
	g_inCommand = 0;
}

HOOK(NtUserPeekMessage) {
	ServiceCommands();
	return g_orig_NtUserPeekMessage(a, b, c, d, e, f, g, h, i, j, k, l);
}

HOOK(NtUserSetCursorPos) {
	if (Active()) {
		const HWND window = GameWindow();
		POINT pt{static_cast<int32_t>(a), static_cast<int32_t>(b)};
		if (window != nullptr && ScreenToClient(window, &pt) != 0) {
			g_shared->x = pt.x;
			g_shared->y = pt.y;
		}
		return 1;
	}
	return g_orig_NtUserSetCursorPos(a, b, c, d, e, f, g, h, i, j, k, l);
}

HOOK(NtUserTrackMouseEvent) {
	return Active() ? 1 : g_orig_NtUserTrackMouseEvent(a, b, c, d, e, f, g, h, i, j, k, l);
}

HOOK(NtUserClipCursor) {
	return Active() ? 1 : g_orig_NtUserClipCursor(a, b, c, d, e, f, g, h, i, j, k, l);
}

HOOK(NtUserSetForegroundWindow) {
	if (NoFront() && a == reinterpret_cast<uint64_t>(GameWindow())) {
		return 1;
	}
	return g_orig_NtUserSetForegroundWindow(a, b, c, d, e, f, g, h, i, j, k, l);
}

HOOK(NtUserShowWindow) {
	if (NoFront() && (b & 0xff) == 5) {
		b = 8;  // SW_SHOW -> SW_SHOWNA
	}
	return g_orig_NtUserShowWindow(a, b, c, d, e, f, g, h, i, j, k, l);
}

HOOK(NtUserSetActiveWindow) {
	return NoFront() ? 0 : g_orig_NtUserSetActiveWindow(a, b, c, d, e, f, g, h, i, j, k, l);
}
#undef HOOK

Fn15 g_orig_NtUserCreateWindowEx = nullptr;
int64_t H_NtUserCreateWindowEx(uint64_t a, uint64_t b, uint64_t c, uint64_t d, uint64_t e, uint64_t f, uint64_t g, uint64_t h,
                               uint64_t i, uint64_t j, uint64_t k, uint64_t l, uint64_t m, uint64_t n, uint64_t o) {
	if (NoFront() && (e & 0x40000000U) == 0) {  // a top-level window (not WS_CHILD)
		a |= 0x08000000U;                       // WS_EX_NOACTIVATE
	}
	return g_orig_NtUserCreateWindowEx(a, b, c, d, e, f, g, h, i, j, k, l, m, n, o);
}

DWORD WINAPI TitleThread(LPVOID) noexcept {
	while (g_running != 0) {
		if (const HWND window = FindGameWindow(); window != nullptr) {
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

auto PatchStub(void* stub, void* hook, void** original) noexcept -> bool {
	static const uint8_t Shape[24] = {0x4c, 0x8b, 0xd1, 0xb8, 0, 0, 0, 0, 0xf6, 0x04, 0x25, 0x08,
	                                  0x03, 0xfe, 0x7f, 0x01, 0x75, 0x03, 0x0f, 0x05, 0xc3, 0xcd, 0x2e, 0xc3};
	const auto* code = static_cast<const uint8_t*>(stub);
	if (code == nullptr) {
		return false;
	}
	for (int i = 0; i < 24; ++i) {
		if ((i < 4 || i >= 8) && code[i] != Shape[i]) {
			return false;  // another build of win32u, or already hooked
		}
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
	*original = trampoline;
	std::memcpy(stub, jump, 14);
	VirtualProtect(stub, 16, old, &old);
	FlushInstructionCache(GetCurrentProcess(), stub, 16);
	return true;
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
	std::snprintf(slash + 1, sizeof(path) - static_cast<size_t>(slash + 1 - path), "statbook-testharness.txt");
	FILE* f = nullptr;
	if (fopen_s(&f, path, "rb") != 0 || f == nullptr) {
		return false;
	}
	const size_t n = std::fread(mode, 1, size - 1, f);
	mode[n] = '\0';
	std::fclose(f);
	return true;
}

}  // namespace

auto InstallTestHarness(char* report, size_t reportSize) noexcept -> bool {
	char mode[128] = "";
	if (!ReadMode(mode, sizeof(mode))) {
		std::snprintf(report, reportSize, "test harness off (no statbook-testharness.txt)");
		return false;
	}
	char mappingName[64];
	std::snprintf(mappingName, sizeof(mappingName), "Local\\mxl2012-testharness-input-%lu", static_cast<unsigned long>(GetCurrentProcessId()));
	HANDLE mapping = CreateFileMappingA(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE, 0, 4096, mappingName);
	if (mapping == nullptr || GetLastError() == ERROR_ALREADY_EXISTS) {
		if (mapping != nullptr) {
			CloseHandle(mapping);
		}
		std::snprintf(report, reportSize, "test harness not installed: the input block exists already (mxl2012-core's harness?)");
		return false;
	}
	g_shared = static_cast<Shared*>(MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(Shared)));
	if (g_shared == nullptr) {
		std::snprintf(report, reportSize, "test harness not installed: the input block could not be mapped");
		return false;
	}
	std::memset(g_shared, 0, sizeof(Shared));
	g_shared->magic = 0x4d58;
	g_shared->x = 800;
	g_shared->y = 450;
	g_shared->reserved = 1;
	g_shared->active = 1;

	int hooked = 0, missing = 0;
	HMODULE win32u = GetModuleHandleA("win32u.dll");
	if (win32u == nullptr) {
		win32u = LoadLibraryA("win32u.dll");
	}
#define INSTALL(name)                                                                                                      \
	if (win32u != nullptr && PatchStub(reinterpret_cast<void*>(GetProcAddress(win32u, #name)), reinterpret_cast<void*>(&H_##name), \
	                                   reinterpret_cast<void**>(&g_orig_##name))) {                                         \
		++hooked;                                                                                                          \
	} else {                                                                                                               \
		++missing;                                                                                                         \
	}
	INSTALL(NtUserGetCursorPos)
	INSTALL(NtUserGetKeyState)
	INSTALL(NtUserSetCursorPos)
	INSTALL(NtUserClipCursor)
	INSTALL(NtUserSetForegroundWindow)
	INSTALL(NtUserPeekMessage)
	INSTALL(NtUserTrackMouseEvent)
	INSTALL(NtUserShowWindow)
	INSTALL(NtUserSetActiveWindow)
	INSTALL(NtUserCreateWindowEx)
#undef INSTALL
	const bool keyStateImport = PatchImport(GetModuleHandleA(nullptr), "user32.dll", "GetKeyState", reinterpret_cast<void*>(&H_GetKeyState),
	                                        reinterpret_cast<void**>(&g_origGetKeyState));
	if (HMODULE core = GetModuleHandleA("D2RCore.dll"); core != nullptr) {
		FARPROC execute = GetProcAddress(core, "ExecuteConsoleCommand");
		if (execute == nullptr) {
			execute = GetProcAddress(core, MAKEINTRESOURCEA(14));
		}
		g_execute = reinterpret_cast<ExecuteConsoleCommandFn>(execute);
	}
	g_running = 1;
	if (const char* tag = std::strstr(mode, "tag="); tag != nullptr) {
		char word[24] = "";
		sscanf_s(tag + 4, "%23[^ \t\r\n]", word, static_cast<unsigned>(sizeof(word)));
		std::swprintf(g_titleText, 64, L"Diablo II: Resurrected [%hs]", word);
		if (HANDLE t = CreateThread(nullptr, 0, TitleThread, nullptr, 0, nullptr); t != nullptr) {
			CloseHandle(t);
		}
	}
	std::snprintf(report, reportSize, "TEST HARNESS ON (test build): %d input calls hooked, %d not, GetKeyState import %s, console %s", hooked,
	              missing, keyStateImport ? "hooked" : "not found", g_execute != nullptr ? "on" : "off (no D2RCore export)");
	return true;
}
