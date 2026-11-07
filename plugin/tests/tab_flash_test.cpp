// Standalone test of the stash tab flash rules (tab_flash_logic.h; not part of the plugin DLL). Lane tabhl, bug #550.
#include "../src/tab_flash_logic.h"

#include <cstdio>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}

auto Disp(const uint8_t* p) -> int32_t {
	return static_cast<int32_t>(p[0] | (p[1] << 8) | (p[2] << 16) | (static_cast<uint32_t>(p[3]) << 24));
}
}  // namespace

int main() {
	using namespace tab_flash;

	// D2R's switch: its three exits are the leave 0x23bcdc and the tab store 0x23bbcf
	Check(SwitchRva + 0x0f + 6 + Disp(Switch + 0x11) == LeaveRva, "D2R's jne leaves at 0x23bcdc");
	Check(Switch[0x15] == 0xb3 && Switch[0x16] == 4 && Switch[0x19] == 0xb3 && Switch[0x1a] == 3 && Switch[0x1d] == 0xb3 && Switch[0x1e] == 2,
	      "D2R: kind 3 / 2 / 1 -> bl 4 / 3 / 2");
	// the new switch: ja to the same leave, the short jump to the same store, nothing past 0x23bbcf
	Check(sizeof(SwitchNew) == sizeof(Switch), "same length");
	Check(SwitchNew[6] == 0x0f && SwitchNew[7] == 0x87 && SwitchRva + 12 + Disp(SwitchNew + 8) == LeaveRva, "ja leaves at 0x23bcdc");
	Check(SwitchNew[15] == 0xeb && SwitchRva + 17 + static_cast<int8_t>(SwitchNew[16]) == AfterSwitchRva, "jmp to the tab store 0x23bbcf");
	Check(SwitchNew[3] == 0x83 && SwitchNew[4] == 0xf9 && SwitchNew[5] == 4, "cmp ecx, 4: kinds 1-5");
	Check(SwitchRva + sizeof(Switch) == AfterSwitchRva, "the switch ends at the store");
	Check(Rel32(SwitchRva + 12, LeaveRva) == 0x120, "rel32 of the leave");
	// the shown-tab test calls D2R's getter 0x23af50 and leaves at 0x23bcdc
	Check(ShownTestRva + 5 + Disp(ShownTest + 1) == 0x23af50, "the test calls the tab getter");
	Check(ShownTestRva + 13 + Disp(ShownTest + 9) == LeaveRva, "the test's je leaves");
	Check(ShownTestRva == AfterSwitchRva + 3, "the test follows mov rcx, rdi after the store");
	// every "none" site ends with D2R's 5
	for (const Imm& s : NoFlashSites) {
		Check(s.code[s.size - 1] == NoFlash, "none value 5 at the end of each site");
	}
	Check(NoFlashNew == 7 && NoFlashNew <= 8, "7 tabs, within TabBarWidget's 8 entries");

	// kind -> tab, as the new switch maps it
	Check(TabOfKind(0) == -1 && TabOfKind(6) == -1 && TabOfKind(255) == -1, "no tab for kind 0 and above 5");
	Check(TabOfKind(1) == 2 && TabOfKind(2) == 3 && TabOfKind(3) == 4, "D2R's kinds keep their tabs");
	Check(TabOfKind(KindMedian) == MedianTab && TabOfKind(KindOrbs) == OrbsTab, "MEDIAN / ORBS kinds -> tabs 5 / 6");

	// the flash runs unless the bar shows that tab
	Check(!Flash(1, 2), "a gem with Gems shown: no flash (D2R)");
	Check(Flash(1, 0), "a gem from Personal: Gems flashes");
	Check(Flash(3, MedianTab), "a rune with MEDIAN shown: Runes flashes (the capped getter said Runes)");
	Check(!Flash(KindMedian, MedianTab), "an elixir with MEDIAN shown: no flash");
	Check(Flash(KindOrbs, MedianTab), "an orb with MEDIAN shown: ORBS flashes");
	Check(Flash(KindMedian, 4), "an elixir with Runes shown: MEDIAN flashes");
	Check(!Flash(0, 0), "no page: no flash");

	// codes
	Check(Pack("eo7") == 0x20376f65u, "eo7 packed space padded");
	Check(NamesCode("eo7", Pack("eo7")) && !NamesCode("eo7", Pack("eo8")) && !NamesCode("eo", Pack("eo7")), "names: exact codes");
	Check(NamesCode("b_b", Pack("b@b")) && !NamesCode("b_b", Pack("b_b")), "names: '_' is the '@' of the item code");
	Check(!NamesCode("medtab_median_bg", Pack("medt")), "a picture name names no code");
	Check(NamesCode("&a1", Pack("&a1")) && NamesCode("A0+", Pack("A0+")), "orb and shrine codes");

	// the kind the flash gets
	Check(Kind(3, Pack("eo7"), true) == KindMedian, "elixir -> MEDIAN");
	Check(Kind(3, Pack("b@b"), true) == KindMedian, "Goodberry ('@') -> MEDIAN");
	Check(Kind(3, Pack("A0+"), true) == KindMedian, "full shrine -> MEDIAN");
	Check(Kind(3, Pack("&01"), true) == KindOrbs && Kind(3, Pack("&a5"), true) == KindOrbs, "orbs -> ORBS");
	Check(Kind(3, Pack("r01"), true) == KindRunes, "a rune stays Runes");
	Check(Kind(1, Pack("eo7"), true) == 1 && Kind(2, Pack("6o^"), true) == 2, "Gems / Materials kinds unchanged");
	Check(Kind(3, Pack("eo7"), false) == KindRunes, "not live (classic game, off word medtab, D2R's layout): D2R's kind");
	Check(Kind(3, 0, true) == KindRunes, "no record: D2R's kind");
	Check(Kind(0, Pack("eo7"), true) == 0, "no page: none");

	// every code of the two groups maps, none of them is also in the other
	int median = 0, orbs = 0;
	for (const char* n : medtab_names::Median) {
		if (n[0] != 'm' || n[1] != 'e') {
			char code[5] = {};
			for (int i = 0; i < 4 && n[i] != '\0'; ++i) {
				code[i] = n[i] == medtab_names::Placeholder ? '@' : n[i];
			}
			Check(Kind(3, Pack(code), true) == KindMedian, n);
			++median;
		}
	}
	for (const char* n : medtab_names::Orbs) {
		if (n[0] != 'm' || n[1] != 'e') {
			Check(Kind(3, Pack(n), true) == KindOrbs, n);
			++orbs;
		}
	}
	Check(median == 75 && orbs == 100, "75 MEDIAN slots, 100 ORBS slots");

	if (failures == 0) {
		std::printf("tab_flash_test: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
