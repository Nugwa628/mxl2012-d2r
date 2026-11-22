// Standalone test of the health bar and damage number keys' pure part (overlay_keys_logic.h; not part of the plugin DLL).
#include "../src/overlay_keys_logic.h"

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
	using namespace overlay_keys;

	// the modes read from Enemy Health Bars' bits (enabled, show_full_health, uniques_bosses_only)
	Check(ModeOf(BarsValid) == BarsMode::Off, "disabled is Off");
	Check(ModeOf(BarsValid | BarsFull | BarsUniques) == BarsMode::Off, "disabled is Off whatever the other keys say");
	Check(ModeOf(BarsValid | BarsEnabled) == BarsMode::DamagedAll, "the shipped default: when damaged, all monsters");
	Check(ModeOf(BarsValid | BarsEnabled | BarsFull) == BarsMode::AlwaysAll, "full life too: always, all monsters");
	Check(ModeOf(BarsValid | BarsEnabled | BarsFull | BarsUniques) == BarsMode::AlwaysUniques, "always, uniques/bosses");
	Check(ModeOf(BarsValid | BarsEnabled | BarsUniques) == BarsMode::DamagedUniques, "when damaged, uniques/bosses");

	// the cycle (owner, 2026-11-22): Off -> Always all -> Always uniques -> Damaged all -> Damaged uniques -> Off
	Check(NextMode(BarsMode::Off) == BarsMode::AlwaysAll, "Off -> always, all");
	Check(NextMode(BarsMode::AlwaysAll) == BarsMode::AlwaysUniques, "always, all -> always, uniques");
	Check(NextMode(BarsMode::AlwaysUniques) == BarsMode::DamagedAll, "always, uniques -> damaged, all");
	Check(NextMode(BarsMode::DamagedAll) == BarsMode::DamagedUniques, "damaged, all -> damaged, uniques");
	Check(NextMode(BarsMode::DamagedUniques) == BarsMode::Off, "damaged, uniques -> Off");

	// five presses from any mode come back to it; each mode's bits read back as that mode
	for (int start = 0; start < BarsModeCount; ++start) {
		uint32_t bits = BitsOf(static_cast<BarsMode>(start), BarsValid | BarsEnabled);
		Check(ModeOf(bits) == static_cast<BarsMode>(start), "BitsOf / ModeOf round trip");
		int seen = 0;
		for (int i = 0; i < BarsModeCount; ++i) {
			const BarsMode next = NextMode(ModeOf(bits));
			bits = BitsOf(next, bits);
			Check(ModeOf(bits) == next, "a press sets the next mode");
			Check((bits & BarsValid) != 0, "the bits a press sends are valid");
			seen |= 1 << static_cast<int>(next);
		}
		Check(seen == 0x1f, "five presses go through all five modes");
		Check(ModeOf(bits) == static_cast<BarsMode>(start), "five presses come back to the start");
	}
	// Off keeps the other two keys, so the file keeps the player's last choice next to enabled = false
	Check(BitsOf(BarsMode::Off, BarsValid | BarsEnabled | BarsUniques) == (BarsValid | BarsUniques), "Off keeps uniques_bosses_only");
	Check(BitsOf(BarsMode::Off, BarsValid | BarsEnabled | BarsFull) == (BarsValid | BarsFull), "Off keeps show_full_health");
	Check(BitsOf(BarsMode::AlwaysAll, BarsValid | BarsUniques) == (BarsValid | BarsEnabled | BarsFull), "after Off: always, all monsters");

	// the lines (owner's examples)
	char line[160];
	BarsLine(line, sizeof(line), BarsMode::DamagedUniques, ApplySaved);
	Check(std::strcmp(line, "Health bars: when damaged, uniques/bosses") == 0, "the owner's example line");
	BarsLine(line, sizeof(line), BarsMode::Off, ApplySaved);
	Check(std::strcmp(line, "Health bars: off") == 0, "Health bars: off");
	BarsLine(line, sizeof(line), BarsMode::AlwaysAll, ApplySaved);
	Check(std::strcmp(line, "Health bars: always, all monsters") == 0, "always, all monsters");
	BarsLine(line, sizeof(line), BarsMode::AlwaysUniques, ApplyNotSaved);
	Check(std::strcmp(line, "Health bars: always, uniques/bosses (not saved)") == 0, "a setting not saved says so");
	BarsLine(line, sizeof(line), BarsMode::DamagedAll, ApplyMissing);
	Check(std::strstr(line, "not loaded") != nullptr, "no Enemy Health Bars: says so");
	DamageLine(line, sizeof(line), false, ApplySaved);
	Check(std::strcmp(line, "Floating damage: off") == 0, "the owner's example line (damage)");
	DamageLine(line, sizeof(line), true, ApplySaved);
	Check(std::strcmp(line, "Floating damage: on") == 0, "Floating damage: on");
	DamageLine(line, sizeof(line), true, ApplyRefused);
	Check(std::strstr(line, "enabled = false") != nullptr, "master switch off: says where");
	DamageLine(line, sizeof(line), true, ApplyMissing);
	Check(std::strstr(line, "not loaded") != nullptr, "no Floating Damage: says so");

	// no line while an NPC talks (speech, menu, trade): it would freeze the speech
	Check(LineAllowed(0, 0), "no NPC: the line shows");
	Check(!LineAllowed(1, 0), "NPC speech: no line");
	Check(!LineAllowed(1, 1) && !LineAllowed(0, 1) && !LineAllowed(0, 2), "NPC menu or trade: no line");

	if (failures == 0) {
		std::printf("overlay_keys_test: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
