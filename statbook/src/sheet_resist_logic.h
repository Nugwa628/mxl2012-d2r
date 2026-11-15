// Pure rules of part sheetres (sheet_resist.cpp): the Magic and Physical Resistance rows of D2R's character sheet. No Windows or D2R
// headers, so plugin/tests/sheet_resist_test.cpp builds it alone.
//
// The numbers are the ones D2R's damage code applies (resist step 0x4523e0, the damage type table built in 0x44df10; docs/hd-ui.md
// "Magic and Physical Resistance on the character sheet"): physical damage uses stat 36 `damageresist` with no maximum-resistance stat, so its ceiling is 50; magic damage uses stat 37
// `magicresist` with stat 38 `maxmagicresist`, ceiling 75 + maxmagicresist. Every ceiling is held to at most 95, the floor is -100,
// and neither type gets the difficulty penalty of the elements. The sheet's own elemental rows show the value the same way (cap,
// -100 floor; 0x14e728f) and colour it: at the cap gold, below 0 red, else white.
#pragma once

#include <cstddef>
#include <cstdio>

namespace sheet_resist {

inline constexpr int StatDamageResist = 36;     // itemstatcost damageresist
inline constexpr int StatMagicResist = 37;      // itemstatcost magicresist
inline constexpr int StatMaxMagicResist = 38;   // itemstatcost maxmagicresist
inline constexpr int PhysicalCeiling = 50;      // 0x4524d0: no max stat and stat 0x24 -> 50
inline constexpr int BaseCeiling = 75;          // 0x4524a5 / 0x4524bb: 75 (+ the max stat)
inline constexpr int HardCeiling = 95;          // 0x4524dd
inline constexpr int Floor = -100;              // 0x4524e7

enum class Tone { Normal, Capped, Negative };

struct Row {
	int value = 0;  // what the game applies, in percent
	int cap = 0;    // the ceiling it is held to
	Tone tone = Tone::Normal;
};

inline auto Clamp(int raw, int cap) noexcept -> Row {
	Row r;
	r.cap = cap;
	r.value = raw < Floor ? Floor : raw > cap ? cap : raw;
	r.tone = r.value >= cap ? Tone::Capped : r.value < 0 ? Tone::Negative : Tone::Normal;
	return r;
}

inline auto Physical(int damageResist) noexcept -> Row {
	return Clamp(damageResist, PhysicalCeiling);
}

inline auto Magic(int magicResist, int maxMagicResist) noexcept -> Row {
	// the sum in 64 bits: a huge max stat must not wrap below the ceiling
	const long long ceiling = static_cast<long long>(BaseCeiling) + maxMagicResist;
	return Clamp(magicResist, ceiling > HardCeiling ? HardCeiling : static_cast<int>(ceiling));
}

// "50%", as the HD and gamepad sheets write their elemental values; the legacy sheet writes them without the sign ("50").
inline void Text(const Row& r, char* out, size_t size, bool percent = true) noexcept {
	std::snprintf(out, size, percent ? "%d%%" : "%d", r.value);
}

// One sheet row: the three value boxes at the same place (one per colour; a text box has the one colour of its style, colour codes
// print as text), as the layouts tools/sheet_resists.py writes name them. The row titles are literal texts of those layouts.
struct Names {
	const char* normal;
	const char* capped;
	const char* negative;
};

inline constexpr Names MagicNames{"MxlMagicText", "MxlMagicTextCapped", "MxlMagicTextNegative"};
inline constexpr Names PhysicalNames{"MxlPhysicalText", "MxlPhysicalTextCapped", "MxlPhysicalTextNegative"};

// The value box that shows a row of this tone (the other two are emptied).
inline auto BoxFor(const Names& n, Tone t) noexcept -> const char* {
	return t == Tone::Capped ? n.capped : t == Tone::Negative ? n.negative : n.normal;
}

// An empty widget only the legacy layout has: its values go without the percent sign.
inline constexpr const char* LegacyMarker = "MxlSheetLegacy";

inline constexpr const char* PanelName = "CharacterStatsPanel";  // the root of D2R's sheet layouts (PC HD, legacy, gamepad)

}  // namespace sheet_resist
