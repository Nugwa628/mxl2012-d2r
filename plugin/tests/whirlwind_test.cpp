// Standalone test of Whirlwind's 1.13c hit rate (whirlwind_logic.h; not part of the plugin DLL). Bug #281.
#include "../src/whirlwind_logic.h"

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
	using namespace whirlwind;
	// 1.13c's table, edges included
	Check(ClassicDelay(0) == 4 && ClassicDelay(11) == 4, "< 12 frames: a hit every 4");
	Check(ClassicDelay(12) == 6 && ClassicDelay(14) == 6, "< 15: 6");
	Check(ClassicDelay(15) == 8 && ClassicDelay(17) == 8, "< 18: 8");
	Check(ClassicDelay(18) == 10 && ClassicDelay(19) == 10, "< 20: 10");
	Check(ClassicDelay(20) == 12 && ClassicDelay(22) == 12, "< 23: 12");
	Check(ClassicDelay(23) == 14 && ClassicDelay(25) == 14, "< 26: 14");
	Check(ClassicDelay(26) == 16 && ClassicDelay(200) == 16, "else 16");

	// D2R's speed term: diminishing IAS, clamp 15..max
	Check(D2RSpeed(100, 0, 175) == 100, "no IAS: stat 68 alone");
	Check(D2RSpeed(100, 120, 175) == 160, "120 IAS counts 60 in D2R");
	Check(D2RSpeed(100, 1000, 175) == 175, "capped at the unit's max");
	Check(D2RSpeed(0, -50, 175) == 15, "floored at 15");
	Check(D2RSpeed(100, -120, 175) == 100, "no division by zero at IAS -120");

	// 1.13c's speed: the 100 base once
	Check(ClassicSpeed(100, 0) == 100, "stat 68 already 100 (D2R's units)");
	Check(ClassicSpeed(0, 0) == 100, "stat 68 without the base: 1.13c adds 100");
	Check(ClassicSpeed(100, 120) == 220, "IAS adds in full in 1.13c");

	// whole rule: no IAS, D2R waits 16 frames -> same speed, table 8
	Check(HitDelay(16, 100, 0, 175, true) == 8, "16 frames at 100 speed: 1.13c hits every 8");
	// 120 IAS: D2R speed 160 vs 1.13c 220, 20 D2R frames -> 14 at 1.13c's speed -> 6
	Check(HitDelay(20, 100, 120, 175, true) == 6, "fast weapon with IAS: a hit every 6");
	// slow weapon: D2R 30 frames, no IAS -> 16
	Check(HitDelay(30, 100, 0, 175, true) == 16, "slow weapon: 16");
	// A barbarian run: about half D2R's hits before -> D2R's frame count is always >= the classic delay here
	for (int f = 8; f <= 40; ++f) {
		if (HitDelay(f, 100, 0, 175, true) > f) {
			Check(false, "never slower than D2R's own count at the same speed");
			break;
		}
	}
	Check(HitDelay(30, 100, 0, 175, false) == NoWeaponDelay, "no weapon: 10");
	Check(HitDelay(18, -200, 0, 175, true) == ClassicDelay(18), "a non-positive classic speed keeps D2R's frames for the table");

	if (failures == 0) {
		std::printf("whirlwind tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
