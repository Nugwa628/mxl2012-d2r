// Standalone test of part sheetres's rules (sheet_resist_logic.h; not part of the plugin DLL).
#include "../src/sheet_resist_logic.h"

#include <climits>
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
auto Shows(const sheet_resist::Row& r, const char* want, bool percent = true) -> bool {
	char text[16];
	sheet_resist::Text(r, text, sizeof(text), percent);
	return std::strcmp(text, want) == 0;
}
}  // namespace

int main() {
	using namespace sheet_resist;
	Check(StatDamageResist == 36 && StatMagicResist == 37 && StatMaxMagicResist == 38, "the stat ids D2R's damage table names");
	// physical: ceiling 50, no maximum stat
	Check(Physical(0).value == 0 && Physical(0).tone == Tone::Normal, "physical 0");
	Check(Physical(30).value == 30 && Physical(30).cap == 50, "physical below the cap");
	Check(Physical(50).value == 50 && Physical(50).tone == Tone::Capped, "physical at the cap is gold");
	Check(Physical(80).value == 50 && Physical(80).tone == Tone::Capped, "physical above the cap shows the cap");
	Check(Physical(-20).value == -20 && Physical(-20).tone == Tone::Negative, "physical below 0 is red");
	Check(Physical(-500).value == -100, "the floor is -100");
	// magic: 75 + maxmagicresist, at most 95
	Check(Magic(40, 0).value == 40 && Magic(40, 0).cap == 75 && Magic(40, 0).tone == Tone::Normal, "magic below the cap");
	Check(Magic(150, 0).value == 75 && Magic(150, 0).tone == Tone::Capped, "magic held at 75");
	Check(Magic(150, 10).value == 85 && Magic(150, 10).cap == 85, "max magic resist raises the cap");
	Check(Magic(80, 10).value == 80 && Magic(80, 10).tone == Tone::Normal, "below a raised cap");
	Check(Magic(150, 20).value == 95 && Magic(150, 50).value == 95 && Magic(150, 50).cap == 95, "never above 95");
	Check(Magic(150, -10).cap == 65 && Magic(150, -10).value == 65, "a negative max lowers the cap");
	Check(Magic(150, INT_MAX).value == 95, "a huge max does not wrap");
	Check(Magic(-150, 0).value == -100 && Magic(-150, 0).tone == Tone::Negative, "magic floor and red");
	Check(Magic(INT_MIN, 0).value == -100 && Magic(INT_MAX, 0).value == 75, "extreme stat values");
	// text
	Check(Shows(Physical(25), "25%") && Shows(Magic(-30, 0), "-30%") && Shows(Physical(0), "0%"), "values as the sheet writes them");
	Check(Shows(Physical(25), "25", false) && Shows(Magic(-30, 0), "-30", false), "legacy values without the sign");
	// boxes
	Check(std::strcmp(BoxFor(MagicNames, Tone::Normal), "MxlMagicText") == 0, "the white box");
	Check(std::strcmp(BoxFor(MagicNames, Tone::Capped), "MxlMagicTextCapped") == 0, "the gold box");
	Check(std::strcmp(BoxFor(PhysicalNames, Tone::Negative), "MxlPhysicalTextNegative") == 0, "the red box");
	if (failures == 0) {
		std::printf("sheetres tests: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
