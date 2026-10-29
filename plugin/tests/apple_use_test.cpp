// Standalone test of the Apple's item-spell rule (apple_use_logic.h; not part of the plugin DLL).
#include "../src/apple_use_logic.h"

#include <cstdio>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
constexpr auto Code(const char (&s)[5]) -> uint32_t {
	return static_cast<uint32_t>(static_cast<unsigned char>(s[0])) | static_cast<uint32_t>(static_cast<unsigned char>(s[1])) << 8 |
	       static_cast<uint32_t>(static_cast<unsigned char>(s[2])) << 16 | static_cast<uint32_t>(static_cast<unsigned char>(s[3])) << 24;
}
}  // namespace

int main() {
	using namespace apple_use;
	Check(Code("ass ") == BookCode, "the Book of Skill's code");
	Check(!RunsApple(Code("ass ")), "bug #240: the Book of Skill keeps D2R's pSpell 10 (+1 skill point)");
	Check(RunsApple(Code("dog ")), "bug #499: the Apple casts 1.13c's skill 47");
	Check(!RunsApple(0), "an item without a record stays D2R's");
	Check(AppleSkill == 47 && AppleLevel == 1 && CastFlag == 0, "1.14d 0x5bf170: skill 0x2f, level 1, flag 0");
	Check(CheckSlot == 7 && UseSlot == 10, "pSpell 10's descriptor {7, 10, 0}");
	if (failures == 0) {
		std::printf("apple use tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
