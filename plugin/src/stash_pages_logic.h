// Pure part of `stashpage2` (stash_pages.cpp; unit test plugin/tests/stash_pages_test.cpp). No Windows headers, no game calls.
#pragma once

#include <cstdint>
#include <cstring>

namespace stash_pages {

// The stock stash's tab bar sends "BankPanelMessage:SelectTab" (bankexpansionlayout(hd).json `onSwitchTabMessage`) with the tab
// index as text: 0 Personal, 1 Shared, 2-4 the RotW pages (Gems, Materials, Runes). -1: not a tab switch, or no index in it.
inline auto SelectedTab(const char* target, const char* command, const char* text) noexcept -> int {
	if (target == nullptr || command == nullptr || std::strcmp(target, "BankPanelMessage") != 0 || std::strcmp(command, "SelectTab") != 0 ||
	    text == nullptr || *text == '\0') {
		return -1;
	}
	int value = 0;
	for (const char* p = text; *p != '\0'; ++p) {
		if (*p < '0' || *p > '9' || value > 100) {
			return -1;
		}
		value = value * 10 + (*p - '0');
	}
	return value;
}

// Opening or building the stock stash panel ("PanelManager:OpenPanel:BankExpansionLayout", "...:LoadPanel:..."): the strip is
// set again then, the panel opens on its Personal tab.
inline auto StockStashOpens(const char* command, const char* text, const char* stockPanel) noexcept -> bool {
	return command != nullptr && text != nullptr && stockPanel != nullptr && std::strcmp(text, stockPanel) == 0 &&
	       (std::strcmp(command, "LoadPanel") == 0 || std::strcmp(command, "OpenPanel") == 0);
}

// The page 2 arrows on the stock stash: only with the page registered and its panel bound (else they lead nowhere), and only on
// the Personal tab when a tab index is known (D2R 3.3's SelectTab text is empty: the tab stays 0; on the Shared tab D2R's own
// arrows draw over ours, the RotW pages hide the whole container).
inline auto StripVisible(bool pageReady, int tab) noexcept -> bool {
	return pageReady && tab == 0;
}

// The harness `stashpage move <id> <page> [x y]` packs x and y into one value: -1 automatic placement, else x | y << 8.
inline auto PackCell(long long x, long long y) noexcept -> long long {
	return x < 0 || y < 0 ? -1 : ((y & 0xff) << 8) | (x & 0xff);
}
inline auto CellX(long long packed) noexcept -> long long { return packed < 0 ? -1 : packed & 0xff; }
inline auto CellY(long long packed) noexcept -> long long { return packed < 0 ? -1 : (packed >> 8) & 0xff; }

// A four-letter item code from text ("r05" -> 'r','0','5',' '), as D2R's item codes are padded with spaces.
inline auto PaddedCode(const char* text, char out[5]) noexcept -> bool {
	std::memcpy(out, "    ", 5);
	if (text == nullptr || *text == '\0') {
		return false;
	}
	for (int i = 0; i < 4 && text[i] != '\0'; ++i) {
		out[i] = text[i];
	}
	return std::strlen(text) <= 4;
}

}  // namespace stash_pages
