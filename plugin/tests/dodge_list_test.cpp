// Standalone test of the dodge / avoid / evade list guard's patch bytes (dodge_list_logic.h; not part of the plugin DLL).
#include "../src/dodge_list_logic.h"

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
	using namespace dodge_list;
	// bug #53: the jmp at 0x44b152 lands on 0x44b27d, where D2R goes after its own "hList" assert (je 0x44b27d at 0x44b162)
	Check(Rel32(RvaAssertBlock, RvaLeave) == 0x126, "rel32 of the jump");
	constexpr Jump j = JumpBytes();
	Check(j.bytes[0] == 0xe9 && j.bytes[1] == 0x26 && j.bytes[2] == 0x01 && j.bytes[3] == 0 && j.bytes[4] == 0, "jmp bytes e9 26 01 00 00");
	// the expected bytes start with the assert's lea rcx,[rsp+0x40] and hold the call to the assert reporter 0x449c40
	Check(Expected[0] == 0x48 && Expected[9] == 0xe8, "expected bytes: lea, then the call");
	const int32_t callRel = static_cast<int32_t>(Expected[10] | (Expected[11] << 8) | (Expected[12] << 16) | (static_cast<uint32_t>(Expected[13]) << 24));
	Check(RvaAssertBlock + 9 + 5 + callRel == 0x449c40, "the call in the expected bytes is the assert reporter 0x449c40");
	Check(Rel32(0x1000, 0x1000) == -5, "rel32 to itself");
	Check(PatchSize == sizeof(j.bytes) && PatchSize < sizeof(Expected), "the patch check covers exactly the 5 bytes written");

	if (failures == 0) {
		std::printf("dodge list tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
