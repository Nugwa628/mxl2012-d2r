// Standalone test of the test harness's stub shapes and input paths (testharness_logic.h; not part of the plugin DLL).
#include "../src/testharness_logic.h"

#include <cstdio>
#include <cstring>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

// NtUserGetCursorPos as Windows 11 and Proton Experimental 11.0 (2026-11-12) ship it.
const uint8_t WindowsStub[32] = {0x4c, 0x8b, 0xd1, 0xb8, 0x0e, 0x10, 0x00, 0x00, 0xf6, 0x04, 0x25, 0x08, 0x03, 0xfe, 0x7f, 0x01,
                                 0x75, 0x03, 0x0f, 0x05, 0xc3, 0xcd, 0x2e, 0xc3, 0x0f, 0x1f, 0x84, 0x00, 0x00, 0x00, 0x00, 0x00};
const uint8_t WineStub[32] = {0x4c, 0x8b, 0xd1, 0xb8, 0xea, 0x13, 0x00, 0x00, 0xf6, 0x04, 0x25, 0x08, 0x03, 0xfe, 0x7f, 0x01,
                              0x75, 0x03, 0x0f, 0x05, 0xc3, 0xeb, 0x01, 0xc3, 0xff, 0x14, 0x25, 0x00, 0x10, 0xfe, 0x7f, 0xc3};
}  // namespace

int main() {
	using namespace harness_logic;

	Check(ClassifyStub(WindowsStub) == StubShape::Windows, "Windows syscall stub");
	Check(ClassifyStub(WineStub) == StubShape::Wine, "Wine/Proton syscall stub");
	Check(ClassifyStub(nullptr) == StubShape::Unknown, "no stub");

	uint8_t b[32];
	std::memcpy(b, WineStub, 32);
	b[4] = 0x99;
	b[5] = 0x77;
	Check(ClassifyStub(b) == StubShape::Wine, "any syscall number");
	std::memcpy(b, WindowsStub, 32);
	b[0] = 0xff;
	b[1] = 0x25;  // already hooked (jmp [rip+0])
	Check(ClassifyStub(b) == StubShape::Unknown, "a hooked stub is left alone");
	std::memcpy(b, WindowsStub, 32);
	b[15] = 0x00;
	Check(ClassifyStub(b) == StubShape::Unknown, "another head");
	std::memcpy(b, WineStub, 32);
	b[27] = 0x20;  // call [7ffe2000]: another dispatcher
	Check(ClassifyStub(b) == StubShape::Unknown, "another Wine dispatcher address");
	std::memcpy(b, WineStub, 32);
	b[17] = 0x05;
	Check(ClassifyStub(b) == StubShape::Unknown, "another jump distance");
	std::memcpy(b, WindowsStub, 32);
	b[22] = 0x2f;
	Check(ClassifyStub(b) == StubShape::Unknown, "another Windows tail");
	Check(std::strcmp(ShapeName(StubShape::Wine), "wine") == 0 && std::strcmp(ShapeName(StubShape::Unknown), "unknown") == 0,
	      "shape names");

	// win32u first; the import only when the stub is not hooked; neither: off.
	Check(ChoosePath(true, false) == InputPath::Win32u, "stub hooked: win32u");
	Check(ChoosePath(true, true) == InputPath::Win32u, "stub hooked wins over an import");
	Check(ChoosePath(false, true) == InputPath::Import, "no stub, import there: import");
	Check(ChoosePath(false, false) == InputPath::Off, "neither: off");
	Check(!WantImport(true) && WantImport(false), "the import is tried only without the stub hook");

	PathCounts counts;
	counts.Add(InputPath::Win32u);
	counts.Add(InputPath::Import);
	counts.Add(InputPath::Import);
	counts.Add(InputPath::Off);
	Check(counts.win32u == 1 && counts.imports == 2 && counts.off == 1, "path counts");

	Check(HasWord("iat", "iat") && HasWord("tag=s2 iat", "iat") && HasWord("diag,iat\r\n", "iat"), "mode word found");
	Check(!HasWord("tag=iatx", "iat") && !HasWord("diagiat", "iat") && !HasWord("", "iat") && !HasWord(nullptr, "iat") &&
	          !HasWord("iat", ""),
	      "mode word not found inside another word");

	Check(!WantFakeFocus("tag=s2") && !WantFakeFocus("volserial tag=s5 diag"), "fake focus off by default (also under Wine)");
	Check(WantFakeFocus("tag=s2 fakefocus") && WantFakeFocus("fakefocus,volserial"), "fakefocus word turns it on");
	Check(!WantFakeFocus("nofakefocus tag=s2") && !WantFakeFocus("fakefocus nofakefocus"), "nofakefocus wins");
	Check(!WantFakeFocus("xfakefocus") && !WantFakeFocus(nullptr) && !WantFakeFocus(""), "whole words only, no mode text");

	if (failures == 0) {
		std::printf("testharness_logic: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}
