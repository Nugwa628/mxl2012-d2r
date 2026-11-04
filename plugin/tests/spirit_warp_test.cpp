// Standalone test of the Barbarian spirits' owner warp rule (spirit_warp_logic.h; not part of the plugin DLL).
#include "../src/spirit_warp_logic.h"

#include <cstdio>
#include <cstdlib>

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
	using namespace spirit_warp;
	Check(DistanceSq(4940, 4663, 4940, 4663) == 0 && DistanceSq(4960, 4663, 4940, 4663) == 400 &&
	          DistanceSq(4937, 4667, 4940, 4663) == 25,
	      "squared distance in sub-tiles");
	// the lane summonai readings (bug #534): spirits stood 32-51 sub-tiles off after a fight, once 91
	Check(Decide(DistanceSq(0, 0, 32, 0), false) == Verdict::Warp, "32 sub-tiles off, no target: warp");
	Check(Decide(DistanceSq(0, 0, 51, 0), true) == Verdict::Warp, "51 off, fighting: warp (beyond 40)");
	Check(Decide(DistanceSq(0, 0, 91, 0), false) == Verdict::Warp, "91 off: warp");
	Check(Decide(DistanceSq(0, 0, 20, 0), false) == Verdict::Stay, "exactly 20: stays");
	Check(Decide(DistanceSq(0, 0, 14, 14), false) == Verdict::Stay, "14,14 (19.8): stays");
	Check(Decide(DistanceSq(0, 0, 15, 14), false) == Verdict::Warp, "15,14 (20.5): warp");
	Check(Decide(DistanceSq(0, 0, 11, 0), true) == Verdict::Stay, "fighting at 11: stays");
	Check(Decide(DistanceSq(0, 0, 30, 0), true) == Verdict::Held, "fighting at 30: keeps fighting");
	Check(Decide(DistanceSq(0, 0, 40, 0), true) == Verdict::Held, "fighting at 40: keeps fighting");
	Check(Decide(DistanceSq(0, 0, 41, 0), true) == Verdict::Warp, "fighting at 41: warp");
	Check(Decide(DistanceSq(0, 0, 30, 0), false) == Verdict::Warp, "30 off, not fighting: warp");
	// fighting: a live target in reach, or within 40 of the owner (a spirit walking out to it is not warped back)
	Check(Fighting(true, true, DistanceSq(0, 0, 60, 0)), "a live target in reach");
	Check(Fighting(true, false, DistanceSq(0, 0, 30, 0)), "a live target 30 from the owner");
	Check(Fighting(true, false, DistanceSq(0, 0, 40, 0)), "a live target 40 from the owner");
	Check(!Fighting(true, false, DistanceSq(0, 0, 41, 0)), "a target left 41 behind: not fighting");
	Check(!Fighting(false, true, 0), "a dead target (or none): not fighting");
	Check(Alive(4) && Alive(15) && Alive(1) && !Alive(ModeDeath) && !Alive(ModeDead), "modes DT and DD are dead");
	Check(SpiritPetTypes[0] == 30 && SpiritPetTypes[1] == 31 && SpiritPetTypes[2] == 32, "pettype rows guardianspet..protectorspet");

	// the frame check: once every 25 server frames (a second)
	Check(FrameDue(0) && FrameDue(25) && FrameDue(2500) && !FrameDue(1) && !FrameDue(24) && !FrameDue(26), "every 25th frame");

	// fight notes from the think: fresh for 1.5 s, cleared by a think that saw no fight
	Slot slots[SlotCount] = {};
	Check(!FightingRecently(slots, 18, 5000), "no note: not fighting");
	Note(slots, 18, true, 5000);
	Check(FightingRecently(slots, 18, 5000) && FightingRecently(slots, 18, 6500), "noted fighting, up to 1.5 s later");
	Check(!FightingRecently(slots, 18, 6501), "a note older than 1.5 s (the think stopped: idle): not fighting");
	Check(!FightingRecently(slots, 19, 5100), "another spirit has its own note");
	Note(slots, 18, false, 5600);
	Check(!FightingRecently(slots, 18, 5700), "a think without a fight clears the note");
	Note(slots, 18, false, 5800);
	Check(!FightingRecently(slots, 18, 5900), "no fight, no note: nothing stored");
	Note(slots, 7, true, 0);
	Check(FightingRecently(slots, 7, 1), "a note at time 0 still counts");
	// more spirits than slots: the oldest note gives way
	Slot full[SlotCount] = {};
	for (uint32_t id = 100; id < 100 + SlotCount + 4; ++id) {
		Note(full, id, true, 10000 + id);
	}
	Check(!FightingRecently(full, 100, 10200) && FightingRecently(full, 100 + SlotCount + 3, 10200), "the oldest note gave way");

	if (failures != 0) {
		std::printf("spiritwarp_tests: %d failure(s)\n", failures);
		return EXIT_FAILURE;
	}
	std::printf("spiritwarp_tests: all passed\n");
	return EXIT_SUCCESS;
}
