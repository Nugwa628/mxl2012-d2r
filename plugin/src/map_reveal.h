// Pity map reveal (map_reveal.cpp, map_reveal_logic.h; docs/plugin-plan.md section 34). Off word: mapreveal.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// The Controls action "Reveal Level Map" (mxl_map_level, default L) reveals the rest of the current level's automap once the
// player has explored the threshold of it (mxl2012-core.toml [mapreveal] threshold, default 70 %); a chat line says when it
// becomes available and answers each press. Client side only, no hook. True when on.
auto InstallMapReveal(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// Test harness (UI thread): the current level's numbers and the counters since load ("level=3 rooms=98 ... percent=20 ...").
void MapRevealStatus(char* out, size_t size) noexcept;
// Test harness (UI thread): what a press of the key does, at once. False when the part is off.
auto MapRevealPress() noexcept -> bool;
// Test harness (UI thread): another threshold until the next start (0-101; the settings file is not written).
void MapRevealSetThreshold(int threshold) noexcept;
// The last chat line the part made ("" before the first).
auto MapRevealLastLine() noexcept -> const char*;
