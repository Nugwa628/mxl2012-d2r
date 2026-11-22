// Pure parts of the test harness (testharness.cpp): which win32u syscall stubs may be hooked inline, and which input
// path each harness hook takes. No Windows headers, so tests/testharness_logic_test.cpp runs anywhere.
#pragma once

#include <cstddef>
#include <cstdint>

namespace harness_logic {

// The shapes of a win32u syscall stub the harness hooks. Both start with the same 16 bytes
//     4c 8b d1 / b8 <ssn32> / f6 04 25 08 03 fe 7f 01        mov r10,rcx; mov eax,ssn; test byte [7ffe0308],1
// which are copied to the trampoline (nothing rip-relative in them); the 14-byte jump overwrites bytes 0-13 and the
// tail from byte 16 on stays where it is, so only the head has to be movable. The tail is checked anyway, so an unknown
// stub (another hook, a future layout) is left alone:
//   Windows:     75 03 / 0f 05 / c3 / cd 2e / c3                          jne +3; syscall; ret; int 2e; ret
//   Wine/Proton: 75 03 / 0f 05 / c3 / eb 01 / c3 / ff 14 25 00 10 fe 7f / c3
//                jne +3; syscall; ret; jmp +1; ret; call [7ffe1000] (Wine's syscall dispatcher); ret
// (Proton Experimental 11.0-20261112, measured 2026-11-20 by lane wineinput.)
enum class StubShape { Unknown, Windows, Wine };

constexpr size_t StubBytes = 32;  // bytes ClassifyStub reads (one stub; win32u stubs are 32 bytes apart on both)

inline auto ClassifyStub(const uint8_t* code) noexcept -> StubShape {
	static constexpr uint8_t Head[16] = {0x4c, 0x8b, 0xd1, 0xb8, 0, 0, 0, 0, 0xf6, 0x04, 0x25, 0x08, 0x03, 0xfe, 0x7f, 0x01};
	if (code == nullptr) {
		return StubShape::Unknown;
	}
	for (int i = 0; i < 16; ++i) {
		if ((i < 4 || i >= 8) && code[i] != Head[i]) {
			return StubShape::Unknown;
		}
	}
	static constexpr uint8_t Common[5] = {0x75, 0x03, 0x0f, 0x05, 0xc3};
	for (int i = 0; i < 5; ++i) {
		if (code[16 + i] != Common[i]) {
			return StubShape::Unknown;
		}
	}
	if (code[21] == 0xcd && code[22] == 0x2e && code[23] == 0xc3) {
		return StubShape::Windows;
	}
	static constexpr uint8_t WineTail[11] = {0xeb, 0x01, 0xc3, 0xff, 0x14, 0x25, 0x00, 0x10, 0xfe, 0x7f, 0xc3};
	for (int i = 0; i < 11; ++i) {
		if (code[21 + i] != WineTail[i]) {
			return StubShape::Unknown;
		}
	}
	return StubShape::Wine;
}

inline auto ShapeName(StubShape shape) noexcept -> const char* {
	switch (shape) {
	case StubShape::Windows: return "windows";
	case StubShape::Wine: return "wine";
	default: return "unknown";
	}
}

// Where one harness input hook lives. The win32u stub stays first (every caller, also user32's own, goes through it);
// when it could not be hooked, the game exe's import of the matching user32 function is redirected instead (only the
// game's direct calls; enough for the input it reads). Neither: the part is off and the report says so.
// `forceImport` ("iat" in mxl2012-testharness.txt) skips the stub, to test the import path on a system whose stubs hook.
enum class InputPath { Win32u, Import, Off };

inline auto ChoosePath(bool stubHooked, bool importPatched) noexcept -> InputPath {
	if (stubHooked) {
		return InputPath::Win32u;
	}
	return importPatched ? InputPath::Import : InputPath::Off;
}

// Whether to try the import at all: only when the stub was not hooked (never both: the hook would run twice).
inline auto WantImport(bool stubHooked) noexcept -> bool {
	return !stubHooked;
}

// Counts for the one-line report: "N win32u (wine stubs), M imports, K off".
struct PathCounts {
	int win32u = 0;
	int imports = 0;
	int off = 0;
	void Add(InputPath path) noexcept {
		if (path == InputPath::Win32u) {
			++win32u;
		} else if (path == InputPath::Import) {
			++imports;
		} else {
			++off;
		}
	}
};

// Mode words of mxl2012-testharness.txt are blank-separated; true when `word` is one of them (not a part of another
// word, so "iat" does not match "tag=iatx").
inline auto HasWord(const char* mode, const char* word) noexcept -> bool {
	if (mode == nullptr || word == nullptr || word[0] == '\0') {
		return false;
	}
	size_t wordLength = 0;
	while (word[wordLength] != '\0') {
		++wordLength;
	}
	auto blank = [](char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == ','; };
	for (const char* p = mode; *p != '\0';) {
		while (*p != '\0' && blank(*p)) {
			++p;
		}
		const char* start = p;
		while (*p != '\0' && !blank(*p)) {
			++p;
		}
		if (static_cast<size_t>(p - start) == wordLength) {
			bool same = true;
			for (size_t i = 0; i < wordLength; ++i) {
				if (start[i] != word[i]) {
					same = false;
					break;
				}
			}
			if (same) {
				return true;
			}
		}
	}
	return false;
}

// Fake focus: the game is told it is the active, focused window (deactivation messages dropped, GetForegroundWindow
// answers the game window, SetFocus stays inside), so it acts on posted keys while another window has the real focus.
// Off by default everywhere; the mode word "fakefocus" turns it on, "nofakefocus" (wins) keeps it off. It used to be on
// by default under Wine, but there it hung startup at "Initializing graphics context (15/24)" on the private Xvfb
// display (lane linharness r2/r3), and game runs under Wine only happen on a private display, where the game may hold
// that display's own focus (lane linfix, 2026-11-20). Windows runs keep the measured behaviour (off unless asked).
inline auto WantFakeFocus(const char* mode) noexcept -> bool {
	return HasWord(mode, "fakefocus") && !HasWord(mode, "nofakefocus");
}

}  // namespace harness_logic
