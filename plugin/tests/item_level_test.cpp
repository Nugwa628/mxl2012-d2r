// Standalone test of the item level patch (item_level_logic.h; not part of the plugin DLL).
#include "../src/item_level_logic.h"

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
	using namespace item_level;
	Check(FieldMax == 127, "7-bit field maximum");
	Check(PatchInExpected == 0x11 && PatchInExpected + PatchSize <= ExpectedSize, "the patched bytes lie inside the compared block");
	bool oldInCheck = true;
	for (size_t i = 0; i < PatchSize; ++i) {
		oldInCheck = oldInCheck && item_level::Expected[PatchInExpected + i] == Old[i];
	}
	Check(oldInCheck, "Old is the compared block at 0x37d744");
	Check(Old[ImmCmp] == D2RClamp && Old[ImmMov] == D2RClamp, "D2R's two immediates are 99");
	Check(item_level::Expected[BitsInExpected] == FieldBits && item_level::Expected[BitsInExpected - 2] == 0x41 && item_level::Expected[BitsInExpected - 1] == 0xb8,
	      "mov r8d,7: the field is 7 bits");
	Check(item_level::Expected[ExpectedSize - 1] == 0xe8, "the block ends at the write's call");
	Check(Mask[2] == FieldMax, "r15d holds the field maximum");

	const Bytes d2r = PatchBytes(D2RClamp);
	const Bytes ours = PatchBytes(FieldMax);
	int diff = 0;
	for (size_t i = 0; i < PatchSize; ++i) {
		Check(d2r.b[i] == Old[i], "PatchBytes(99) is D2R's code");
		diff += ours.b[i] != Old[i];
	}
	Check(diff == 2 && ours.b[ImmCmp] == 0x7f && ours.b[ImmMov] == 0x7f && ours.b[ImmMov + 1] == 0, "only the two immediates change, to 0x7f");
	Check(ours.b[3] == 0x0f && ours.b[4] == 0x8c && ours.b[9] == 0xb8, "jl rel32 and mov eax,imm32 kept");

	// D2R as it is: bug #251
	Check(Written(100, D2RClamp) == 99 && Written(120, D2RClamp) == 99 && Written(98, D2RClamp) == 98, "D2R clamps at 99");
	// patched
	const int keep[] = {1, 2, 98, 99, 100, 110, 120, 126, 127};
	for (int v : keep) {
		Check(Written(v, FieldMax) == v, "levels 1-127 written as they are");
		Check(Read(static_cast<uint32_t>(Written(v, FieldMax))) == v, "and read back the same");
	}
	Check(Written(0, FieldMax) == 1 && Written(-5, FieldMax) == 1, "below 1 -> 1 (D2R)");
	Check(Written(128, FieldMax) == 127 && Written(255, FieldMax) == 127 && Written(100000, FieldMax) == 127, "never more than 7 bits");
	for (int v = -3; v < 400; ++v) {
		const int w = Written(v, FieldMax);
		Check(w >= 1 && w <= FieldMax, "written value fits the field");
	}
	Check(Read(0) == 1 && Read(99) == 99 && Read(0x80 | 5) == 5, "reader: 7 bits, < 1 -> 1");

	if (failures == 0) {
		std::printf("item level tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
