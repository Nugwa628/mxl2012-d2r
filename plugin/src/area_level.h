// The area level on the automap's top-right text (area_level.cpp, off word arealvl).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's automap terror-zone level lookup 0x90c70 so a level that is not terrorized shows its area level (levels.txt
// MonLvlEx of the game's difficulty) on that line. The report gets one entry. True when the hook is on.
auto InstallAreaLevel(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Lines filled since load, the last level id and area level, the difficulty seen on the server frame (-1: none yet).
void AreaLevelCounts(long* filled, int* levelId, int* areaLevel, int* difficulty) noexcept;
