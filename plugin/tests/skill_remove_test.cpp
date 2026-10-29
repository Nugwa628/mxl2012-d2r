// Standalone test of the skill-remove guard rule (skill_remove_logic.h; not part of the plugin DLL).
#include "../src/skill_remove_logic.h"

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
	using skill_remove::SkipsRemove;
	// bug #15: a pet that owns no skill (Batstrike's bats, Rampagor, Lamia) gets a sumskill at level 0: the remove returns quietly
	Check(SkipsRemove(true, true, false), "a skill list without a first skill is skipped");
	Check(SkipsRemove(true, false, false), "a unit without a skill list is skipped");
	// a unit with skills takes D2R's own remove, and so does a null unit (D2R's assert names a real fault there)
	Check(!SkipsRemove(true, true, true), "a unit with skills runs D2R's remove");
	Check(!SkipsRemove(false, false, false), "a null unit is left to D2R");

	if (failures == 0) {
		std::printf("skill remove tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
