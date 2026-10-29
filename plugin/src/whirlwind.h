// Whirlwind's 1.13c hit rate (whirlwind.cpp, whirlwind_logic.h; bug #281). Off word: whirlwind.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's Whirlwind hit delay (0x56ac00): 1.13c's table on 1.13c's attack speed instead of D2R 2.4's frame count.
auto InstallWhirlwind(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Hit delays answered since load, and the last one: D2R's frames and the delay returned.
void WhirlwindStats(long* calls, long* lastD2R, long* lastDelay) noexcept;
