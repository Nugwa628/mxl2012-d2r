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

// The tab every user of D2R's tab getter sees (0x23af50 through the stub): tabs 5 and 6 run as Runes. The stub caps the low
// byte only, so an index above 255 still reaches D2R's own bounds check.
constexpr auto GetterTab(unsigned tab) noexcept -> unsigned {
	return tab <= 255 && tab > LastD2RTab ? LastD2RTab : tab;
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
