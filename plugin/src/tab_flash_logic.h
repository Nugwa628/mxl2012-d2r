// Pure part of the stash's tab flash after a Ctrl-click deposit (tab_flash.cpp, bug #550, lane tabhl; unit test
// plugin/tests/tab_flash_test.cpp). No Windows headers, no game calls.
#pragma once

#include "medtab_names.h"

#include <cstddef>
#include <cstdint>

namespace tab_flash {

// A Ctrl-click from the backpack into an advanced stash page (InventoryItemManager 0x159a30 / 0x15f8b0) asks
// 0x15ef70(item class id) for the page kind (the stash init's map of the pages' direct-child slot codes: 1 Gems, 2 Materials,
// 3 Runes, 0 none) and hands it to the BankPanel's tab flash 0x23bb50(kind). That maps kind 1 / 2 / 3 to tab 2 / 3 / 4, skips
// the tab D2R's getter 0x23af50 shows and the tab already flashing (panel +0x260), and flashes the tab: +0x260 = tab, the
// flash times +0x250 / +0x258 (tabNotificationDurationSeconds +0x240 x tabNotificationFadeOccurrences +0x244), and the tab
// bar's highlight 0x879470(bar, i, i == +0x260) for i 0-4. The tab update 0x23de70 fades it and puts the "none" value 5 back.
// The MEDIAN and ORBS slots are direct children of advancedstash_runes (tools/median_tabs.py), so their items are kind 3 and
// flashed RUNES (#550). The part:
//   - 0x15ef70 (called by those two sites only) answers kind 4 for a MEDIAN code and 5 for an ORBS code while the Median tabs
//     are live (medtab), else D2R's kind;
//   - the flash's kind -> tab switch maps kind 1-5 to tab 2-6, the "none" value 5 becomes 7 (panel init, the tab click that
//     ends a flash, the tab update's test and reset) and the highlight loop runs over 7 tabs (TabBarWidget keeps 8 entries,
//     a tab without its highlight widget is skipped by 0x879470 / 0x879d20);
//   - the flash's own "shown tab" test (the getter, which medtab caps at 4) is taken out; the hook of 0x23bb50 skips the
//     flash when the tab bar's real tab (+0x16c4) is the item's tab, as D2R does for its own tabs.
inline constexpr uint64_t KindRva = 0x15ef70;
inline constexpr uint8_t KindEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x48, 0x89, 0x7c, 0x24, 0x18};
inline constexpr uint64_t FlashRva = 0x23bb50;
inline constexpr uint8_t FlashEntry[] = {0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48, 0x83, 0xec, 0x20, 0x0f, 0xb6, 0xf1,
                                         0xb9, 0x18, 0x00, 0x00, 0x00};  // ..., movzx esi, cl, mov ecx, 0x18
inline constexpr uint64_t PanelByIdRva = 0x846190;  // (0x18) -> the BankPanel, as the flash itself asks
inline constexpr uint32_t BankPanelId = 0x18;

// The switch on esi (the kind), 0x23bbb0-0x23bbcf: kind 1 / 2 / 3 -> bl 2 / 3 / 4, anything else leaves (0x23bcdc).
inline constexpr uint64_t SwitchRva = 0x23bbb0;
inline constexpr uint8_t Switch[31] = {0x8b, 0xce, 0x83, 0xe9, 0x01, 0x74, 0x16, 0x83, 0xe9, 0x01, 0x74, 0x0d, 0x83, 0xf9, 0x01, 0x0f,
                                       0x85, 0x17, 0x01, 0x00, 0x00, 0xb3, 0x04, 0xeb, 0x06, 0xb3, 0x03, 0xeb, 0x02, 0xb3, 0x02};
// lea ecx, [rsi-1] / cmp ecx, 4 / ja 0x23bcdc / lea ebx, [rsi+1] / jmp 0x23bbcf (int3 fill): kind 1-5 -> tab 2-6
inline constexpr uint8_t SwitchNew[31] = {0x8d, 0x4e, 0xff, 0x83, 0xf9, 0x04, 0x0f, 0x87, 0x20, 0x01, 0x00, 0x00, 0x8d, 0x5e, 0x01,
                                          0xeb, 0x0e, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc, 0xcc};
inline constexpr uint64_t LeaveRva = 0x23bcdc;
inline constexpr uint64_t AfterSwitchRva = 0x23bbcf;

// call 0x23af50 / cmp bl, al / je 0x23bcdc: the shown-tab test, made 13 nops (the hook tests the real tab)
inline constexpr uint64_t ShownTestRva = 0x23bbd2;
inline constexpr uint8_t ShownTest[13] = {0xe8, 0x79, 0xf3, 0xff, 0xff, 0x3a, 0xd8, 0x0f, 0x84, 0xfd, 0x00, 0x00, 0x00};

// The "none" value of panel +0x260 and the highlight loop's bound: an 8-bit immediate at the end of each instruction.
struct Imm {
	uint64_t rva;
	uint8_t code[8];
	uint32_t size;  // the immediate is code[size - 1]
};
inline constexpr uint8_t NoFlash = 5;     // D2R's value: the five tabs
inline constexpr uint8_t NoFlashNew = 7;  // the 7-tab stash
inline constexpr Imm NoFlashSites[] = {
	{0x23aa17, {0xc6, 0x83, 0x60, 0x02, 0x00, 0x00, 0x05}, 7},        // panel init: mov byte [rbx+0x260], 5
	{0x23c1c2, {0xc6, 0x83, 0x60, 0x02, 0x00, 0x00, 0x05}, 7},        // the flashing tab clicked: mov byte [rbx+0x260], 5
	{0x23e2fe, {0x41, 0x80, 0xbe, 0x60, 0x02, 0x00, 0x00, 0x05}, 8},  // tab update: cmp byte [r14+0x260], 5 / jae (no flash)
	{0x23e379, {0x41, 0xc6, 0x86, 0x60, 0x02, 0x00, 0x00, 0x05}, 8},  // tab update, flash over: mov byte [r14+0x260], 5
	{0x23bcd7, {0x80, 0xfb, 0x05}, 3},                                // the flash's highlight loop: cmp bl, 5 / jb
};

inline constexpr int MedianTab = 5;
inline constexpr int OrbsTab = 6;
inline constexpr uint8_t KindRunes = 3;
inline constexpr uint8_t KindMedian = 4;
inline constexpr uint8_t KindOrbs = 5;

// The tab the flash's switch gives a kind (SwitchNew), -1 when it leaves.
constexpr auto TabOfKind(unsigned kind) noexcept -> int {
	return kind >= 1 && kind <= 5 ? static_cast<int>(kind) + 1 : -1;
}

// The hook of 0x23bb50: true when D2R's flash runs; false for a kind without a tab or the tab the bar shows.
constexpr auto Flash(unsigned kind, int realTab) noexcept -> bool {
	const int t = TabOfKind(kind);
	return t >= 0 && t != realTab;
}

// `name` (a layout slot name: the item code with "@" written Placeholder) names the item code `code` (4 bytes, little-endian,
// space padded: "eo7 " = 0x20376f65).
constexpr auto NamesCode(const char* name, uint32_t code) noexcept -> bool {
	for (int i = 0; i < 4; ++i) {
		const char c = static_cast<char>((code >> (8 * i)) & 0xff);
		const char n = name[i] == medtab_names::Placeholder ? '@' : name[i];
		if (name[i] == '\0') {
			for (int j = i; j < 4; ++j) {
				if (static_cast<char>((code >> (8 * j)) & 0xff) != ' ') {
					return false;
				}
			}
			return true;
		}
		if (n != c) {
			return false;
		}
	}
	return name[4] == '\0';
}

template <size_t N>
constexpr auto InGroup(const char* const (&names)[N], uint32_t code) noexcept -> bool {
	for (const char* n : names) {
		if (NamesCode(n, code)) {
			return true;
		}
	}
	return false;
}

// The kind the flash gets: a Runes-page code of the MEDIAN or ORBS tab gets that tab's kind while the Median tabs are live.
constexpr auto Kind(uint8_t d2rKind, uint32_t code, bool live) noexcept -> uint8_t {
	if (!live || d2rKind != KindRunes || code == 0) {
		return d2rKind;
	}
	return InGroup(medtab_names::Median, code) ? KindMedian : InGroup(medtab_names::Orbs, code) ? KindOrbs : d2rKind;
}

// Code packing as items.txt keeps it (+0x80 of the record).
constexpr auto Pack(const char* s) noexcept -> uint32_t {
	uint32_t v = 0;
	bool end = false;
	for (int i = 0; i < 4; ++i) {
		end = end || s[i] == '\0';
		v |= static_cast<uint32_t>(static_cast<uint8_t>(end ? ' ' : s[i])) << (8 * i);
	}
	return v;
}

// rel32 of a jump / call that ends at `next` and goes to `to`.
constexpr auto Rel32(uint64_t next, uint64_t to) noexcept -> int32_t {
	return static_cast<int32_t>(static_cast<int64_t>(to) - static_cast<int64_t>(next));
}

}  // namespace tab_flash
