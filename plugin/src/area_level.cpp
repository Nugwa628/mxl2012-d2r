// The area level on the automap's top-right text, "Area Level 75" under the area name (owner request 2026-11-06, off word
// arealvl, docs/plugin-plan.md section 28).
//
// D2R already has the line: in a terror zone the automap text shows "Terrorized: <level>" (area_level_logic.h). The hook on
// its level lookup 0x90c70 fills a level that is not terrorized with the area level, and the mod's string fix renames the
// line to "Area Level %d". The client has no difficulty this part could read cheaply, so it takes the game's difficulty
// (game +0x104) and data flag (+0x106) on the shared server frame: single player and a host's own game. A client that joined
// another host's game has no server frame here and keeps D2R's text.
#include "area_level.h"

#include "area_level_logic.h"
#include "d2r.h"
#include "server_frame.h"

#include <atomic>
#include <cstdint>
#include <cstdio>

namespace {

using namespace area_level;

using LookupFn = DesecratedLevel* (*)(DesecratedLevel* out, int32_t levelId) noexcept;
using TablesFn = const uint8_t* (*)(uint32_t dataFlag) noexcept;

LookupFn g_original = nullptr;
TablesFn g_tables = nullptr;
std::atomic<int> g_difficulty{-1};
std::atomic<int> g_dataFlag{0};
std::atomic<long> g_filled{0};
std::atomic<int> g_lastLevel{0};
std::atomic<int> g_lastArea{0};

void Frame(d2r::Game* game) noexcept {
	g_difficulty = d2r::At<uint8_t>(game, 0x104);
	g_dataFlag = d2r::At<uint8_t>(game, d2r::GameDataFlag);
}

DesecratedLevel* LookupHook(DesecratedLevel* out, int32_t levelId) noexcept {
	DesecratedLevel* r = g_original(out, levelId);
	const int difficulty = g_difficulty.load();
	if (r == nullptr || r->has != 0 || difficulty < 0) {
		return r;
	}
	const uint8_t* tables = g_tables(static_cast<uint32_t>(g_dataFlag.load()));
	if (tables == nullptr) {
		return r;
	}
	const int32_t area = AreaLevel(d2r::At<const uint8_t*>(tables, LevelsData), d2r::At<int64_t>(tables, LevelsCount), levelId, difficulty, true);
	g_lastLevel = levelId;
	g_lastArea = area;
	if (Fill(r, area)) {
		++g_filled;
	}
	return r;
}

}  // namespace

auto InstallAreaLevel(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_tables = reinterpret_cast<TablesFn>(context->exeBase + RvaDataTables);
	if (!InstallServerFrame(context) || !AddServerFrameCallback(&Frame)) {
		std::snprintf(report, reportSize, "arealvl off: no server frame callback for the difficulty");
		return false;
	}
	const bool ok = context->InstallInlineHook(RvaDesecratedLevel, DesecratedLevelEntry, sizeof(DesecratedLevelEntry), reinterpret_cast<void*>(&LookupHook),
	                                           reinterpret_cast<void**>(&g_original));
	std::snprintf(report, reportSize,
	              ok ? "arealvl on: the automap text shows the area level (levels.txt MonLvlEx) on D2R's terror-zone line (0x90c70)"
	                 : "arealvl off: the automap level lookup hook 0x90c70 FAILED");
	return ok;
}

void AreaLevelCounts(long* filled, int* levelId, int* areaLevel, int* difficulty) noexcept {
	*filled = g_filled.load();
	*levelId = g_lastLevel.load();
	*areaLevel = g_lastArea.load();
	*difficulty = g_difficulty.load();
}
