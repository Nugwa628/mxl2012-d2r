// Signature patterns of the game code the charm-tab summary calls (D2R 3.3 build 93847).
// Each pattern matches exactly once in .text; ?? covers rel32 call targets and RIP displacements.
// Checked against the 93847 dump by `py -3 invtabs/tests/summary_sigs.py` (expected RVA = last field).
// Most are call sites, not entries: D2RCore (D2RLoader) turns the entries of several stat functions into `jmp [slot]`
// thunks, so a call site is what stays stable. `rip` is then the offset of the call's rel32 in the pattern.
// docs/invtabs-summary.md "Game functions" has what each one does and where it was read.
#pragma once

#include <cstdint>

namespace invtabs::summary {

struct SummaryPattern {
	const char*   name;
	const char*   pattern;
	int           rip;      // >= 0: the target is RIP-relative (call rel32 or data), disp32 at this offset of the match
	int           adjust;   // otherwise: target = match + adjust
	std::uint64_t rva93847; // where the dump has it (log hint only)
};

enum SummaryNative : int {
	GetStatList,    // StatList* (Unit* unit, int state, uint32_t flags): flags 0x40 = the item's own (magic) list
	AllocStatList,  // StatList* (uint32_t flags, int timeout, int ownerType, uint32_t ownerId)
	DataFlag,       // uint8_t (Unit* unit): which data tables (client / server) the unit uses
	StatListAdd,    // void (uint8_t dataFlag, StatList* list, int stat, int value, int layer)
	StatListText,   // void (uint8_t dataFlag, char* out, int outSize, Unit* ctx, StatList* list, int newline, int* hasLine,
	                //       void* chronicle, ChronicleSpan* span, uint8_t bullet): the item tooltip's stat block
	FreeStatList,   // void (uint8_t dataFlag, StatList* list)
	Merged,         // StatList* (Unit* item, uint32_t* active): non-null while the item's stats are merged into its owner
	FormatOne,      // bool (const StatRecord* rec, int value, char* out, int layer): one stat, the local player as context
	StatRecord,     // const StatRecord* (uint8_t dataFlag, int stat): the itemstatcost row
	UiRoot,         // data: void* the root widget
	UiFindPanel,    // void* (void* root, const char name[128])
	UiFindChild,    // void* (void* widget, const char* name): searches below the widget
	TextBoxSetText, // void (void* textBox, const StringView* text)
	SummaryNativeCount
};

inline constexpr SummaryPattern SummaryPatterns[SummaryNativeCount] {
	// in the tooltip stat block builder 0x2dc4b0 (SKILLDESC_BuildStatBuffDesc in 1.14d)
	{ "GetStatList", "E8 ?? ?? ?? ?? 48 8B F8 48 85 C0 74 E4 41 B8 68", 1, 0, 0x2F5A00 },
	{ "AllocStatList", "E8 ?? ?? ?? ?? 49 8B CF 48 89 45 A8 4C 8B E8 E8", 1, 0, 0x2F7300 },
	{ "DataFlag", "E8 ?? ?? ?? ?? 4C 8B C7 88 44 24 60 49 8B D5 0F", 1, 0, 0x34A0E0 },
	{ "StatListAdd", "E8 ?? ?? ?? ?? 48 8B 5C 24 60 85 FF 7E 23 48 89", 1, 0, 0x2F3330 },
	{ "StatListText", "89 7C 24 28 48 89 44 24 20 E8 ?? ?? ?? ?? 49 8B CF", 10, 0, 0x2DA760 },
	{ "FreeStatList", "E8 ?? ?? ?? ?? 4C 85 75 F0 75 16 48 8B 5D E0 E8", 1, 0, 0x2F4180 },
	// in the client charm refresh 0x1c9610 (docs/d2r-addresses.md 22c)
	{ "Merged", "E8 ?? ?? ?? ?? 48 85 C0 75 30 48 8B D7 48 8B CB", 1, 0, 0x2F8120 },
	// in the Advanced Stats panel 0x14eb280
	{ "FormatOne", "4C 89 7F 08 45 33 C9 44 88 38 E8 ?? ?? ?? ?? 84", 11, 0, 0x2D97E0 },
	// in the per-level stat value 0x2db700
	{ "StatRecord", "0F B7 55 52 0F B6 C8 E8 ?? ?? ?? ?? 4C 8B F8 48", 8, 0, 0x2D9730 },
	// UI text setters (plugin/src/devmenu.cpp uses the same functions)
	{ "UiRoot", "48 8B 0D ?? ?? ?? ?? 48 85 C9 74 2C 48 8B 89 D0", 3, 0, 0x3440170 },
	{ "UiFindPanel", "E8 ?? ?? ?? ?? 48 8B F8 48 85 C0 74 4B 48 89 5C", 1, 0, 0x89F760 },
	{ "UiFindChild", "40 53 55 56 57 41 54 48 83 EC 20 4C 89 7C 24 68", -1, 0, 0x855C90 },
	{ "TextBoxSetText", "40 53 48 83 EC 20 4C 8B 42 08 48 8B D9 48 8B 12 48 81", -1, 0, 0x86DD50 },
};

// The summary works without these (with less): FormatOne is the fallback for StatListText, StatRecord orders that fallback.
// Everything else is required for the summary to show.
inline constexpr bool SummaryNativeOptional(int n) { return n == FormatOne || n == StatRecord; }

} // namespace invtabs::summary
