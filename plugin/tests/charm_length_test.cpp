// Standalone test of the 1.13c conversion length (charm_length_logic.h; not part of the plugin DLL).
#include "../src/charm_length_logic.h"

#include <cstdio>
#include <cstring>

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
	using namespace charm_length;
	// the compared bytes
	int32_t rel = 0;
	std::memcpy(&rel, LengthCall + 1, sizeof(rel));
	Check(LengthCall[0] == 0xe8 && Rel32Call(LengthCallRva, CalcEvalRva) == rel, "0x57091b calls the calc evaluator 0x3b5160");
	int32_t disp = 0;
	std::memcpy(&disp, LengthLoad + 3, sizeof(disp));
	Check(LengthLoad[0] == 0x45 && LengthLoad[1] == 0x8b && LengthLoad[2] == 0x86 && disp == static_cast<int32_t>(Calc2Offset),
	      "0x57090f loads calc2 (record +0x194) into r8d");
	Check(LengthLoadRva + sizeof(LengthLoad) == LengthCallRva, "the load and the level store lead straight to the call");
	Check(PadRva + sizeof(Pad) <= ConvertRva && sizeof(Pad) == sizeof(AbsJump::bytes), "the absolute jump fits the pad before 0x570780");
	Check(Pad[0] == 0xcc && Pad[sizeof(Pad) - 1] == 0xcc, "the pad is int3");
	Check(Rel32Call(LengthCallRva, PadRva) < 0 && Rel32Call(LengthCallRva, PadRva) > -0x200, "the call reaches the pad (rel32)");
	Check(Param3Offset == 0x1c0 && Param3Offset + 4 == Param4Offset, "Param3 sits just before Param4 (0x570937 reads +0x1c4)");

	// the jump
	const AbsJump j = AbsJumpBytes(0x1122334455667788ull);
	Check(j.bytes[0] == 0x48 && j.bytes[1] == 0xb8 && j.bytes[2] == 0x88 && j.bytes[9] == 0x11 && j.bytes[10] == 0xff && j.bytes[11] == 0xe0,
	      "movabs rax / jmp rax");

	// the length: Param3 as 1.13c; Batstrike 250 frames (10 s) at every level, where D2R's calc2 `ulvl` gave 60 at level 60
	Check(ClassicLength(true, 250) == 250, "Batstrike: Param3 250 frames");
	Check(ClassicLength(true, 15000) == 15000, "Greater Charm: Param3 15000");
	Check(ClassicLength(true, 0) == 0, "Param3 0: no charm time");
	Check(ClassicLength(false, 250) == 0, "no record: 0 as an empty calc");

	if (failures == 0) {
		std::printf("charmlength_tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
