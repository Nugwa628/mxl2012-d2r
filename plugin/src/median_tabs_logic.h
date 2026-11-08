// The pure rules of the stash's MEDIAN / ORBS tabs (median_tabs.cpp; tests in plugin/tests/median_tabs_test.cpp).
#pragma once

#include "medtab_names.h"

#include <cstddef>

namespace median_tabs {

inline constexpr int MaterialsTab = 3;
inline constexpr int MedianTab = 5;
inline constexpr int OrbsTab = 6;
inline constexpr int LastD2RTab = 4;  // Runes: D2R's panel has 5 pages

// Which widget groups a tab update shows. `live`: the Median tabs are usable (a RotW game, part not off); otherwise tabs 5 and 6
// are hidden and the Materials page shows D2R's page only.
struct Groups {
	bool runesOwn, median, orbs, matVanilla, matMedian, matPicture, selVanilla, selMedian;
};

constexpr auto Visible(int tab, bool materialsMedian, bool live) noexcept -> Groups {
	const bool median = live && materialsMedian;
	const bool materials = tab == MaterialsTab;
	return {tab != MedianTab && tab != OrbsTab, tab == MedianTab, tab == OrbsTab, !median, median,
	        materials && median, materials && live && !median, materials && live && median};
}

// A tab the panel must not keep: 5 and 6 outside a live game (D2R's page table has 5 entries).
constexpr auto Bounce(int tab, bool live) noexcept -> bool {
	return tab > LastD2RTab && !live;
}

// The tab every caller of D2R's tab getter sees (its calls go to the stub, which calls the getter): tabs 5 and 6 run as Runes.
// The getter answers a byte (an index above 255 asserts inside it, as in D2R); the stub caps that byte.
constexpr auto GetterTab(unsigned char tab) noexcept -> unsigned char {
	return tab > LastD2RTab ? static_cast<unsigned char>(LastD2RTab) : tab;
}

// The getter 0x23af50 itself stays as D2R: controller-qol checks its first 128 bytes (0x23af50-0x23afcf). Its direct calls go
// to a stub in the int3 pad after it (0x23afd2, 14 bytes): push rax (keeps the getter's stack aligned) / call 0x23af50 /
// pop rcx / cmp al, 4 / jbe +2 / mov al, 4 / ret. 0x23bbd2 is left out: tabflash takes that call out (tab_flash_logic.h).
inline constexpr unsigned long long GetterRva = 0x23af50;
inline constexpr unsigned long long StubRva = 0x23afd2;
inline constexpr unsigned long long GetterCallers[] = {0x23a749, 0x23ac04, 0x23acd7, 0x23b800, 0x23b870, 0x23ba30, 0x23baa9,
                                                      0x23bb29, 0x23d299, 0x23df03, 0x23df45, 0x23df72, 0x23e57b, 0x23e655,
                                                      0x23e74c, 0x23e84f, 0x23eb41, 0x23eb4d, 0x23ebbd, 0x23ef3e, 0x23ef56};

// `call target` at `site` (e8 + rel32)
inline void CallBytes(unsigned long long site, unsigned long long target, unsigned char (&out)[5]) noexcept {
	const auto rel = static_cast<unsigned>(target - (site + 5));
	out[0] = 0xe8;
	for (int i = 0; i < 4; ++i) {
		out[1 + i] = static_cast<unsigned char>(rel >> (8 * i));
	}
}

inline void StubBytes(unsigned char (&out)[14]) noexcept {
	unsigned char call[5];
	CallBytes(StubRva + 1, GetterRva, call);
	const unsigned char stub[14] = {0x50, call[0], call[1], call[2], call[3], call[4], 0x59, 0x3c, 0x04, 0x76, 0x02, 0xb0, 0x04, 0xc3};
	for (int i = 0; i < 14; ++i) {
		out[i] = stub[i];
	}
}

// The layouts write the codes with "@" with Placeholder ("b_b": D2R's layout loader reads "@key" as a string key). Restores
// the "@" in place when `code` (not 0-terminated, `size` characters) is one of them; true when it changed something.
inline auto RestoreAtCode(char* code, size_t size) noexcept -> bool {
	for (const char* at : medtab_names::AtCodes) {
		size_t n = 0;
		while (at[n] != '\0') {
			++n;
		}
		if (n != size) {
			continue;
		}
		bool same = true;
		for (size_t i = 0; i < n && same; ++i) {
			same = code[i] == at[i];
		}
		if (!same) {
			continue;
		}
		for (size_t i = 0; i < n; ++i) {
			if (code[i] == medtab_names::Placeholder) {
				code[i] = '@';
			}
		}
		return true;
	}
	return false;
}

}  // namespace median_tabs
