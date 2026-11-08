// Level map reveal (map_reveal.cpp, map_reveal_logic.h; docs/plugin-plan.md section 34). Off word: mapreveal.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// The Controls action "Reveal Level Map" (mxl_map_level, default L) reveals the current level's automap on every press (no
// explored share needed since bug #559); levels in mxl2012-core.toml [mapreveal] exclude are refused. A chat line answers each
// press. Client side only, no hook. True when on.
auto InstallMapReveal(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// Test harness (UI thread): the counters since load and the last press ("level=34 presses=2 reveals=2 ... lastmade=60 ...").
void MapRevealStatus(char* out, size_t size) noexcept;
// Test harness (UI thread): what a press of the key does, at once. False when the part is off.
auto MapRevealPress() noexcept -> bool;
// The last chat line the part made ("" before the first).
auto MapRevealLastLine() noexcept -> const char*;
