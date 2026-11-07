// Standalone test of the advanced stash slot's tooltip call (stash_tip_logic.h; not part of the plugin DLL). Lane orbtab, bug #551.
#include "../src/stash_tip_logic.h"

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
	using namespace stash_tip;

	// the addresses: the thunk's slot, the call inside the compared bytes, its rel32 lands on the thunk
	Check(SlotRva == 0x3e2af58, "thunk slot 0x3e2af58");
	Check(ReturnRva == 0x2ce71b, "return address 0x2ce71b");
	Check(SiteSize == 58 && CallInSite + 5 == SiteSize, "the call ends the compared bytes");
	Check(Site[CallInSite] == 0xe8, "e8 at the call");
	const int32_t disp = static_cast<int32_t>(Site[CallInSite + 1] | (Site[CallInSite + 2] << 8) | (Site[CallInSite + 3] << 16) |
	                                          (static_cast<uint32_t>(Site[CallInSite + 4]) << 24));
	Check(CallTarget(CallRva, disp) == ThunkRva, "the call goes to the thunk 0x3e2b826");
	// the stash slot's own set-up: 7th and 6th from r14b (mov [rsp+0x30] / [rsp+0x28], r14b), 5th from [rdi+0x5c0]
	Check(Site[0x22] == 0x44 && Site[0x23] == 0x88 && Site[0x24] == 0x74 && Site[0x25] == 0x24 && Site[0x26] == 0x30, "7th from r14b");
	Check(Site[0x12] == 0x8f && Site[0x13] == 0xc0 && Site[0x14] == 0x05, "5th from widget +0x5c0");

	// the slot's call (5th 0, 6th 1, 7th 1, seen in game) is built as the backpack's: 7th 0, the others as they were
	Args a = Apply({0, 1, 1});
	Check(a.fifth == 0 && a.sixth == 1 && a.seventh == 0, "slot call: short flag cleared");
	// only the low byte of the 7th is the flag; the register's upper bytes are left
	a = Apply({7, 0x101, 0xabcd01});
	Check(a.fifth == 7 && a.sixth == 0x101 && a.seventh == 0xabcd00, "upper bytes kept");
	a = Apply({0, 0, 0});
	Check(a.seventh == 0, "already whole: unchanged");

	if (failures == 0) {
		std::printf("stash_tip_test: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
