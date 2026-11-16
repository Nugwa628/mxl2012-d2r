// Standalone test of Move Only's start rule (move_only_logic.h; not part of the plugin DLL).
#include "../src/move_only_logic.h"

#include <cstdio>

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
	using namespace move_only;
	Check(StartSlot == 71, "Move Only's srvstfunc is 71 (tools/move_only.py START_SLOT)");
	Check(SlotFree(StartSlot, 0), "an empty slot 71 takes the function");
	Check(!SlotFree(StartSlot, 0x140001000ull), "a slot D2R fills is never overwritten");
	Check(!SlotFree(StartSlots, 0), "no slot past the table's 91 entries");
	Check(!SlotFree(0, 0), "slot 0 is \"no start function\"");
	Check(Start() == 0, "the start refuses: no cast, no mana, no hit");
	if (failures == 0) {
		std::printf("move_only_tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
