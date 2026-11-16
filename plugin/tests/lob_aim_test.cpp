// Standalone test of the aimed Laughing Ghost's pure part (lob_aim_logic.h; not part of the plugin DLL).
#include "../src/lob_aim_logic.h"

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
	using namespace lob_aim;
	// laughingghostemerge: Vel 24, VelLev 0, Range 12
	const int32_t v = Velocity(0x420, 0, 24, 0, 20);
	Check(v == 4608, "(24 << 8) * 75 / 100");
	Check(Velocity(0x4, 3, 24, 0, 1) == (3 << 8) * 75 / 100, "flag 4: the params speed << 8");
	Check(Velocity(0x14, 300, 24, 0, 1) == 225, "flags 4 | 0x10: the params speed as it is");
	Check(Velocity(0, 0, 10, 8, 3) == ((10 + 3) << 8) * 75 / 100, "VelLev per 8 levels");

	Check(Distance(10, 0) == 10 && Distance(0, -10) == 10, "straight");
	Check(Distance(10, 10) == 15 && Distance(-10, 4) == 12, "longer axis plus half the shorter");
	Check(Frames(0, v) == 1 * 65536 / 73728, "0 counts as 1");
	Check(Frames(14, v) == 12 && Frames(15, v) == 13, "12 frames reach 14 sub-tiles");
	Check(Frames(10, 0) == 0, "no speed");

	// in range: untouched
	int32_t tx = 5010, ty = 3005;
	Check(!ClampTarget(5000, 3000, &tx, &ty, v, 12) && tx == 5010 && ty == 3005, "a near click stays");
	tx = 5014;
	ty = 3000;
	Check(!ClampTarget(5000, 3000, &tx, &ty, v, 12) && tx == 5014, "the last spot in range stays");

	// far: back to the range on the same line
	tx = 5040;
	ty = 3000;
	Check(ClampTarget(5000, 3000, &tx, &ty, v, 12) && tx == 5014 && ty == 3000, "a far click along x comes back to 14");
	tx = 4970;
	ty = 2970;
	Check(ClampTarget(5000, 3000, &tx, &ty, v, 12), "far diagonal moved");
	Check(Frames(Distance(tx - 5000, ty - 3000), v) <= 12, "diagonal within 12 frames");
	Check(tx - 5000 == ty - 3000 && tx < 5000, "diagonal keeps its direction");
	Check(Frames(Distance(tx - 5000 - 1, ty - 3000 - 1), v) > 12, "diagonal is as far as it goes");
	for (int32_t dx = -60; dx <= 60; dx += 7) {
		for (int32_t dy = -60; dy <= 60; dy += 5) {
			int32_t x = 100 + dx, y = 200 + dy;
			ClampTarget(100, 200, &x, &y, v, 12);
			Check(Frames(Distance(x - 100, y - 200), v) <= 12, "every click ends within the range");
			Check((dx == 0 || (x - 100 > 0) == (dx > 0) || x == 100) && (dy == 0 || (y - 200 > 0) == (dy > 0) || y == 200), "same side");
		}
	}
	tx = 9000;
	Check(!ClampTarget(0, 0, &tx, &ty, 0, 12) && !ClampTarget(0, 0, &tx, &ty, v, 0), "no speed or no range: left alone");

	Check(sizeof(ServerEntry) == 17 && sizeof(ClientEntry) == 22, "entry lengths");
	Check(FlagLob == 0x400 && FlagAbsTarget == 0x20, "D2R's lob and point flags");

	if (failures == 0) {
		std::printf("lob_aim: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}
