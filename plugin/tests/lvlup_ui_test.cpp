// Standalone test of the legacy level-up button refresh (lvlup_ui_logic.h; not part of the plugin DLL).
#include "../src/lvlup_ui_logic.h"

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
}  // namespace

int main() {
	using namespace lvlup_ui;
	// the slots and the compared bytes
	Check(UpdateSlotRva == 0x1fd9ef0 && DrawSlotRva == 0x1fd9ef8, "Update / Draw are slots 2 / 3 of vtable 0x1fd9ee0");
	Check(sizeof(UpdateEntry) == 16 && sizeof(DrawEntry) == 16, "16 entry bytes each");
	Check(UpdateEntry[0] == 0x40 && UpdateEntry[1] == 0x55 && DrawEntry[0] == 0x40 && DrawEntry[1] == 0x55, "both start with push rbp");
	Check(DisableStore[0] == 0xc6 && DisableStore[1] == 0x81 && DisableStore[6] == 0x01, "mov byte ptr [rcx+disp32], 1");
	uint32_t disp = 0;
	std::memcpy(&disp, DisableStore + 2, sizeof(disp));
	Check(disp == DisabledOffset, "the disable stores the byte the wrapper reads (+0x67a)");
	int32_t rip = 0;
	std::memcpy(&rip, HdModeCode + 3, sizeof(rip));
	Check(HdModeCode[0] == 0x48 && HdModeCode[1] == 0x8b && HdModeCode[2] == 0x05 && RipTarget(HdModeRva, rip) == 0x3440170,
	      "0x846210 loads the panel manager global 0x3440170");
	Check(HdModeCode[12] == 0x0f && HdModeCode[13] == 0xb6 && HdModeCode[15] == 0xb9 && HdModeCode[sizeof(HdModeCode) - 1] == 0xc3,
	      "and returns its byte +0xb9");

	// the decision
	Check(NeedsUpdate(false, 1), "legacy, grey button: Update first");
	Check(!NeedsUpdate(false, 0), "legacy, lit button: D2R updates it itself");
	Check(!NeedsUpdate(true, 1) && !NeedsUpdate(true, 0), "HD: left as D2R runs it");

	if (failures == 0) {
		std::printf("lvlupui_tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
