// Standalone test of the item-event skill guard rule (item_effect_logic.h; not part of the plugin DLL).
#include "../src/item_effect_logic.h"

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
	using item_effect::SkipsEventSkill;
	// bug #40: a skill whose row has no ItemEffect is answered with 0 (no cast) instead of D2R's assert
	Check(SkipsEventSkill(116, true, 0), "Innate Detonate (116) without ItemEffect is skipped");
	Check(SkipsEventSkill(241, true, 0), "Blindside (241) without ItemEffect is skipped");
	// a skill with an ItemEffect takes D2R's own path
	Check(!SkipsEventSkill(36, true, 1), "Fire Bolt (ItemEffect 1) runs");
	Check(!SkipsEventSkill(36, true, 0x7fff), "any non-zero ItemEffect runs");
	// skill 0 is D2R's own "no skill" result, an unknown skill (no record) is D2R's business too
	Check(!SkipsEventSkill(0, true, 0), "skill 0 is left to D2R");
	Check(!SkipsEventSkill(-1, true, 0), "a negative skill is left to D2R");
	Check(!SkipsEventSkill(99999, false, 0), "a skill without a record is left to D2R");

	if (failures == 0) {
		std::printf("item effect tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
