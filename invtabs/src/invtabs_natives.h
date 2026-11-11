// Signature patterns of the game code invtabs calls or wraps (D2R 3.3 build 93847).
// Each pattern matches exactly once in .text; ?? covers rel32 call targets and RIP displacements.
// Checked against the 93847 dump by `py -3 tools/invtabs_sigs.py` (expected RVA = last field).
// The addresses equal wild-healer's aaa-player-page-host natives for 93787 / 94995 (docs/invtabs.md).
#pragma once

#include <cstdint>

namespace invtabs {

struct NativePattern {
	const char* name;
	const char* pattern;
	int         rip;      // >= 0: the target is RIP-relative, disp32 at this offset of the match
	int         adjust;   // otherwise: target = match + adjust
	std::uint64_t rva93847; // where the dump has it (log hint only)
};

enum Native : int { InventoryOf, FirstItem, NextItem, NodeMode, CursorItem, GridOwner, PointToCell, ItemSize, GridVtable, NativeCount };

inline constexpr NativePattern NativePatterns[NativeCount] {
	// the unit's inventory: void* (void* unit, const char* file, int line)
	{ "InventoryOf", "48 89 5C 24 18 56 48 83 EC 20 48 8B F1 48 85", -1, 0, 0x34A360 },
	// first item of an inventory: uint8_t* (void* inventory)
	{ "FirstItem", "40 53 48 83 EC 20 48 8B D9 48 85 C9 74 2E 81", -1, 0, 0x388C10 },
	// next item of an inventory: uint8_t* (void* item)
	{ "NextItem", "40 53 48 83 EC 20 48 8B D9 48 85 C9 75 10 88 4C 24 30 48 8D 4C 24 30 E8 ?? ?? ?? ?? EB 67 E8 ?? ?? ?? ?? 83 F8 04 74 14 48 8D 4C 24 30 C6 44 24 30 00 E8 ?? ?? ?? ?? 84 C0 74 01 CC 48 8B CB E8 ?? ?? ?? ?? 83 F8 04 75 41 48 8B CB E8 ?? ?? ?? ?? 83 F8 04 75 20 48 8B CB E8 ?? ?? ?? ?? 48 85 C0 75 2F 48 8D 4C 24 30 88 44 24 30 E8 ?? ?? ?? ?? 84 C0 74 01 CC 48 8D 4C 24 30 C6 44 24 30 00 E8 ?? ?? ?? ?? 84 C0 74 01 CC 33 C0 48 83 C4 20 5B C3 48 05 A0 00 00 00 74 DC 48 8B 40 10 48 83 C4 20 5B C3", -1, 0, 0x38ABA0 },
	// how an item is held (1 = in a grid): int (void* item)
	{ "NodeMode", "40 53 48 83 EC 20 48 8B D9 48 85 C9 75 10 88 4C 24 30 48 8D 4C 24 30 E8 ?? ?? ?? ?? EB 67 E8 ?? ?? ?? ?? 83 F8 04 74 14 48 8D 4C 24 30 C6 44 24 30 00 E8 ?? ?? ?? ?? 84 C0 74 01 CC 48 8B CB E8 ?? ?? ?? ?? 83 F8 04 75 41 48 8B CB E8 ?? ?? ?? ?? 83 F8 04 75 20 48 8B CB E8 ?? ?? ?? ?? 48 85 C0 75 2F 48 8D 4C 24 30 88 44 24 30 E8 ?? ?? ?? ?? 84 C0 74 01 CC 48 8D 4C 24 30 C6 44 24 30 00 E8 ?? ?? ?? ?? 84 C0 74 01 CC 33 C0 48 83 C4 20 5B C3 48 05 A0 00 00 00 74 DC 0F BE 40 19 48 83 C4 20 5B C3", -1, 0, 0x38A930 },
	// the local player's held item: void* ()
	{ "CursorItem", "48 83 EC 28 E8 ?? ?? ?? ?? 8B C8 E8 ?? ?? ?? ?? 48 85 C0 74 21", -1, 0, 0x15F100 },
	// the unit a grid widget shows: void* (void* widget)
	{ "GridOwner", "48 83 EC 28 44 8B 81 C4", -1, 0, 0x2A7810 },
	// grid cell under a point, held item's size included: void (void* widget, uint64_t* out, uint64_t point)
	{ "PointToCell", "48 8B C4 4C 89 40 18 53 55 56 57 41 56", -1, 0, 0x2C6300 },
	// item size in cells: void (void* item, uint8_t* w, uint8_t* h, const char* file, int line)
	{ "ItemSize", "48 89 74 24 18 48 89 7C 24 20 41 56 48 83 EC 20 49 8B F0 4C 8B F2 48 8B F9 48 85 C9 74 0A E8 ?? ?? ?? ?? 83 F8 04 74 19 48 8D 4C 24 30 C6 44 24 30 00 E8 ?? ?? ?? ?? 84 C0 74 01 CC 48 85 FF 74 7F", -1, 0, 0x371850 },
	// InventoryGridWidget vtable, from the lea in its constructor (disp32 at +3)
	{ "GridVtable", "48 8D 05 ?? ?? ?? ?? 48 89 03 33 D2", 3, 0, 0x1CF3800 },
};

// Optional: without it only the summary's "left out" count is less exact (it then counts every backpack item).
// The item type test: BOOL (void* item, int itemTypeRow), Equiv parents included; from its call with row 13 (char) in
// the charm-usable check 0x36ae00 (docs/d2r-addresses.md 22c), rel32 at +9.
inline constexpr int           CharmTypeRow = 13; // itemtypes.txt row of `char`, the same in Median XL 2012
inline constexpr NativePattern TypeCheckPattern { "ItemIsType", "BA 0D 00 00 00 48 8B CB E8 ?? ?? ?? ?? 85 C0 74 58", 9, 0, 0x373890 };

} // namespace invtabs
