// Pure part of the automap's area level line (area_level.cpp; unit test plugin/tests/area_level_test.cpp). No Windows
// headers, no game calls.
#pragma once

#include <cstddef>
#include <cstdint>

namespace area_level {

// D2R's top-right automap text (HUDWarningsPanel, the same panel in HD and legacy graphics: layouts hudwarnings[hd].json,
// `showAutomapDesecratedLevel` true in both) is built by 0x1475215. For the player's level (0x2efc10 of the room 0x9a180) it
// calls 0x90c70(&out, level id), its only caller, and with out.has set appends the line `DesecratedAutomapLevel`
// ("Terrorized: %d") with out.level, then 0x1474ee0 with out.next (0 prints nothing). The hook fills a level that is not
// terrorized with its area level; the mod's string fix makes the line "Area Level %d" (data/d2r_string_fixes.json).
inline constexpr uint64_t RvaDesecratedLevel = 0x90c70;
inline constexpr uint8_t DesecratedLevelEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x10, 0x57, 0x48, 0x83, 0xec, 0x20};

struct DesecratedLevel {
	int32_t level;  // +0
	uint8_t has;    // +4
	uint8_t pad[3];
	int32_t next;   // +8: when not terrorized, the first non-zero +0xc of the zone list
};
static_assert(sizeof(DesecratedLevel) == 12);
static_assert(offsetof(DesecratedLevel, next) == 8);

// The area level as D2R's monster setup reads it: 0x32c700(dataFlag, level, difficulty, expansion) takes the levels.txt
// record (`*(0x300a90(dataFlag) + 0x1460)`, count at +0x1468, 0x18c bytes each) and returns MonLvlEx[difficulty] (i16 at
// +0x1e) for an expansion game, MonLvl[difficulty] (+0x18) for classic. mxl2012-core's monster level gate (0x543d32) makes
// Normal use it too, so it is the level of every monster of the area in every difficulty.
inline constexpr uint64_t RvaDataTables = 0x300a90;  // (dataFlag) -> data tables
inline constexpr int LevelsData = 0x1460;
inline constexpr int LevelsCount = 0x1468;
inline constexpr size_t LevelsStride = 0x18c;
inline constexpr int LevelsMonLvl = 0x18;
inline constexpr int LevelsMonLvlEx = 0x1e;

// The area level of `levelId`, or 0 (no line) for a level outside the table, an unknown difficulty or a level without one.
inline auto AreaLevel(const uint8_t* records, int64_t count, int32_t levelId, int32_t difficulty, bool expansion) noexcept -> int32_t {
	if (records == nullptr || levelId <= 0 || levelId >= count || difficulty < 0 || difficulty > 2) {
		return 0;
	}
	const uint8_t* rec = records + static_cast<size_t>(levelId) * LevelsStride + (expansion ? LevelsMonLvlEx : LevelsMonLvl) + 2 * difficulty;
	const int32_t value = static_cast<int16_t>(rec[0] | (rec[1] << 8));
	return value > 0 ? value : 0;
}

// D2R's own answer stays for a terrorized level; otherwise a known area level is shown on the same line.
inline auto Fill(DesecratedLevel* out, int32_t areaLevel) noexcept -> bool {
	if (out == nullptr || out->has != 0 || areaLevel <= 0) {
		return false;
	}
	out->level = areaLevel;
	out->has = 1;
	out->next = 0;
	return true;
}

}  // namespace area_level
