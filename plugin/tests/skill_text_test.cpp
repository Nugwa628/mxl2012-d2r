// Standalone test of the skill tooltip label cut (skill_text_logic.h; not part of the plugin DLL).
#include "../src/skill_text_logic.h"

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
auto Cut(const char* line, const char* label, bool suffix, const char* want, int wantN) -> bool {
	char buf[256];
	std::snprintf(buf, sizeof(buf), "%s", line);
	const int n = skill_text::CutLabel(buf, label, suffix);
	if (n != wantN || std::strcmp(buf, want) != 0) {
		std::printf("  got %d '%s', want %d '%s'\n", n, buf, wantN, want);
		return false;
	}
	return true;
}
}  // namespace

int main() {
	using namespace skill_text;
	Check(ConversionLength("%d-%d") == 2 && ConversionLength("%+d") == 3 && ConversionLength("%%d") == 0 && ConversionLength("% x") == 0,
	      "printf conversions");
	// type 27 / 22: "Average " + StrSkill5 + numbers + StrSkill34 (1.13c: "Average Fire Damage: 12-15 per second")
	char line[256] = "Average Fire Damage: %d-%d12-15Mana Cost: %d per second\n";
	Check(CutLabel(line, "Fire Damage: %d-%d", false) == 1, "StrSkill5 cut");
	Check(CutLabel(line, "Mana Cost: %d per second", true) == 1, "StrSkill34 cut to its suffix");
	Check(std::strcmp(line, "Average Fire Damage: 12-15 per second\n") == 0, "type 27 line reads as in 1.13c");
	Check(Cut("Radius: %d yards3.3 yards", "Radius: %d yards", false, "Radius: 3.3 yards", 1), "type 28 radius");
	Check(Cut("Cold Length: %d seconds4 seconds", "Cold Length: %d seconds", false, "Cold Length: 4 seconds", 1), "type 11 cold length");
	Check(Cut("Damage: %d-%d1-2Damage: %d-%d3-4", "Damage: %d-%d", false, "Damage: 1-2Damage: 3-4", 2), "every occurrence");
	// a formatted line has no raw label; D2R's own 75 line "Fire Damage: 12-15" is left alone
	Check(Cut("Fire Damage: 12-15", "Fire Damage: %d-%d", false, "Fire Damage: 12-15", 0), "formatted line untouched");
	Check(Cut("Poison Length: 3 seconds", "Poison Length: ", false, "Poison Length: 3 seconds", 0), "a label without a conversion is no cut");
	Check(Cut("x", nullptr, false, "x", 0), "no text from the game");
	// the table: StrSkill34 is the only suffix label
	int suffixes = 0;
	for (const auto& l : Labels) {
		suffixes += l.keepSuffix ? 1 : 0;
	}
	Check(suffixes == 1 && Labels[9].id == 4286 && Labels[9].keepSuffix, "StrSkill34 keeps its suffix");
	Check(RendererRva == 0x287a50 && GetStringRva == 0x3e2b730, "addresses");
	if (failures == 0) {
		std::printf("skill_text: all checks passed\n");
	}
	return failures == 0 ? 0 : 1;
}
