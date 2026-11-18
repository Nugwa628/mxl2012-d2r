// Standalone test of the aimed lob skills' pure part (lob_aim_logic.h; not part of the plugin DLL).
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

	Check(IsAimedSkill(453) && IsAimedSkill(512), "two aimed skills");
	Check(!IsAimedSkill(0) && !IsAimedSkill(454), "other skills untouched");
	Check(!IsAimedSkill(526) && !IsAimedSkill(312), "Pyroblast and Balefire keep hitting the first monster");
	Check(Frames(60, v) > 12, "a far click flies longer than the old 12 frames");

	for (int32_t dx = -200; dx <= 200; dx += 5) {
		for (int32_t dy = -200; dy <= 200; dy += 5) {
			int32_t tx = dx, ty = dy;
			Check(ResolvePoint(FlagRelTarget | FlagLob, 5000, 3000, &tx, &ty), "relative point accepted");
			Check(tx == 5000 + dx && ty == 3000 + dy, "near and far points kept as they are");
			Check(ResolvePoint(FlagAbsTarget | FlagLob, 5000, 3000, &tx, &ty), "absolute point accepted");
			Check(tx == 5000 + dx && ty == 3000 + dy, "absolute points unchanged");
		}
	}
	int32_t tx = 42, ty = 12;
	Check(!ResolvePoint(FlagLob, 5000, 3000, &tx, &ty), "missing target flags refused");

	Check(sizeof(ServerEntry) == 17 && sizeof(ClientEntry) == 22, "entry lengths");
	Check(FlagLob == 0x400 && FlagAbsTarget == 0x20, "D2R's lob and point flags");

	if (failures == 0) {
		std::printf("lob_aim: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}
