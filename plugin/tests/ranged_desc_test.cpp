// Standalone test of the Ctrl stat range line for descfuncs without a range case (ranged_desc_logic.h; not part of the plugin DLL).
#include "../src/ranged_desc_logic.h"

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
void Merge(const char* lo, const char* hi, const char* want, bool wantOk, const char* what) {
	char out[256];
	const bool ok = ranged_desc::MergeRange(lo, hi, out, sizeof(out));
	if (ok != wantOk || std::strcmp(out, want) != 0) {
		std::printf("  got \"%s\" (%d)\n", out, ok ? 1 : 0);
		Check(false, what);
	}
}
}  // namespace

int main() {
	using namespace ranged_desc;
	// the seven descfuncs of jump table 0x2d8b44 that go to the assert block 0x2d8aa4 (93847 dump), and only those
	int count = 0;
	for (int d = 0; d < 40; ++d) {
		count += NoRangeCase(d) ? 1 : 0;
	}
	Check(count == 7 && NoRangeCase(23) && NoRangeCase(5) && NoRangeCase(11) && !NoRangeCase(24) && !NoRangeCase(1), "descfuncs 5 10 11 17 18 22 23");
	Check(SwitchDescfunc(23, 0, false, 0) == 23 && SwitchDescfunc(23, 0, false, 2) == 30 && SwitchDescfunc(23, 0, false, 3) == 31 &&
	          SwitchDescfunc(23, 4, true, 2) == 4,
	      "descfunc as 0x2d7850 picks it");

	Merge("3% Reanimate as: Crimson Templar", "5% Reanimate as: Crimson Templar", "(3-5)% Reanimate as: Crimson Templar", true, "reanimate 3-5");
	Merge("13% Reanimate as: Crimson Templar", "15% Reanimate as: Crimson Templar", "(13-15)% Reanimate as: Crimson Templar", true,
	      "whole numbers, not their last digit");
	Merge("9% Reanimate as: X", "11% Reanimate as: X", "(9-11)% Reanimate as: X", true, "numbers of different length");
	Merge("5% Reanimate as: X", "5% Reanimate as: X", "5% Reanimate as: X", true, "equal lines stay");
	Merge("Hit Causes Monster to Flee 10%", "Hit Causes Monster to Flee 25%", "Hit Causes Monster to Flee (10-25)%", true, "howl");
	Merge("Repairs 1 Durability in 100 Seconds", "Repairs 1 Durability in 20 Seconds", "Repairs 1 Durability in (100-20) Seconds", true,
	      "only the numbers that differ");
	Merge("\xC3\xBF" "c33% Reanimate as: X", "\xC3\xBF" "c35% Reanimate as: X", "\xC3\xBF" "c3(3-5)% Reanimate as: X", true,
	      "colour code digit is not part of the number (UTF-8)");
	Merge("\xFF" "c13% X", "\xFF" "c15% X", "\xFF" "c1(3-5)% X", true, "colour code digit is not part of the number (Latin-1)");
	Merge("3% Reanimate as: Fallen", "5% Reanimate as: Templar", "5% Reanimate as: Templar", false, "other text: the max line");
	Merge("3% X", "5% X Y", "5% X Y", false, "longer line: the max line");
	{
		char small[6];
		Check(!MergeRange("3% Reanimate", "5% Reanimate", small, sizeof(small)) && std::strlen(small) == 5 && std::strncmp(small, "5% Re", 5) == 0,
		      "small buffer: the max line, cut and terminated");
	}
	{
		char out[8] = "xxxxxxx";
		Check(!MergeRange(nullptr, "5%", out, sizeof(out)) && std::strcmp(out, "5%") == 0, "no min line: the max line");
		Check(!MergeRange("5%", nullptr, out, sizeof(out)) && out[0] == '\0', "no max line: empty");
	}

	if (failures == 0) {
		std::printf("ranged desc tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
