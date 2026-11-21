// Standalone test of the first-meeting greeting fix (npc_greet_logic.h; not part of the plugin DLL).
#include "../src/npc_greet_logic.h"

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
	using namespace npc_greet;
	int32_t disp = 0;
	std::memcpy(&disp, MenuStateStore + 2, sizeof(disp));
	Check(MenuStateStore[0] == 0xc7 && MenuStateStore[1] == 0x05 && MenuStateStore[6] == 1, "mov dword ptr [rip+disp], 1");
	Check(RipTarget(MenuStateStoreRva, sizeof(MenuStateStore), disp) == StateRva, "the speech end stores the NPC state 0x2a486a4");
	std::memcpy(&disp, MenuCall + 1, sizeof(disp));
	Check(MenuCall[0] == 0xe8 && RipTarget(MenuCallRva, sizeof(MenuCall), disp) == MenuOpenRva, "and calls the NPC menu opener 0x1141d0");
	std::memcpy(&disp, Register + 3, sizeof(disp));
	Check(RipTarget(RegisterRva, sizeof(Register), disp) == SpeechDoneRva, "0x10da20 is the callback the speech code registers");
	Check(sizeof(SpeechDoneEntry) >= 14 && sizeof(MenuOpenEntry) >= 14, "room for an absolute jump at both entries");

	Check(KeepsPanel(2), "trade or gamble open: kept");
	Check(KeepsPanel(5), "the other vendor states: kept");
	Check(!KeepsPanel(0) && !KeepsPanel(1), "no panel, or the menu: D2R opens the menu");
	Check(!KeepsPanel(6), "state 6 is not the vendor panel: left to D2R");

	if (failures == 0) {
		std::printf("npcgreet_tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
