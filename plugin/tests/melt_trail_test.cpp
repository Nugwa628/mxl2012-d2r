// Standalone test of the state-22 melt trail's pure part (melt_trail_logic.h; not part of the plugin DLL).
#include "../src/melt_trail_logic.h"

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
	using namespace melt_trail;
	// the ids 1.14d's Game.exe uses (0x4e2d40: mov [ebp-0x68],0x8f / edx 0xad / ecx 0x726; 0x5ce4f0: [ebp-0x48] 0xad)
	Check(State == 0x16 && Missile == 0x8f && Skill == 0xad && Sound == 0x726, "1.14d's state, missile, skill and sound");
	Check(ClientFlags == 0x25 && ServerFlags == 0x21 && Velocity == 3, "flags and +0x38 as both games set them");
	Check(ClientSkill == 0 && ServerSkill == Skill, "1.14d's client passes no skill, its server skill 173");

	// D2R's own trail when the list names a skill in range; Median's lists (no stat 350) get the fixed one
	Check(FixedTrail(0, 500), "no skill in the list (Median's raptured)");
	Check(FixedTrail(-1, 500), "a negative skill");
	Check(FixedTrail(500, 500), "a skill past the table");
	Check(!FixedTrail(1, 500), "skill 1 is D2R's trail");
	Check(!FixedTrail(499, 500), "the last skill is D2R's trail");

	// the step table both games build on the stack (D2R: dwords 0x1416080a 0x0c0e1012)
	constexpr uint8_t d2r[8] = {0x0a, 0x08, 0x16, 0x14, 0x12, 0x10, 0x0e, 0x0c};
	for (uint32_t i = 0; i < 8; ++i) {
		uint8_t d = 0xff;
		Check(StepDirection(i, &d) && d == d2r[i], "step table entry");
	}
	uint8_t untouched = 0x77;
	Check(!StepDirection(8, &untouched) && untouched == 0x77, "index past the table makes nothing");
	Check(!StepDirection(255, &untouched), "index 255");

	// one step on, then two more: x + dx, target x + 3 dx
	constexpr Spot s = SpotFrom(5000, 6000, -1, 1);
	Check(s.x == 4999 && s.y == 6001 && s.targetX == 4997 && s.targetY == 6003, "spot and target");
	constexpr Spot z = SpotFrom(10, 20, 0, 0);
	Check(z.x == 10 && z.y == 20 && z.targetX == 10 && z.targetY == 20, "no step");

	// the entry bytes the hooks expect: whole instructions, long enough for the loader's jump
	Check(sizeof(ClientEntry) == 15 && ClientEntry[0] == 0x48 && ClientEntry[14] == 0x20, "client entry: three movs");
	Check(sizeof(ServerEntry) == 16 && ServerEntry[5] == 0x55 && ServerEntry[15] == 0x57, "server entry: mov and seven pushes");
	Check(RvaClient == 0x221650 && RvaServer == 0x578680, "D2R's state-22 functions");

	if (failures == 0) {
		std::printf("melt trail tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
