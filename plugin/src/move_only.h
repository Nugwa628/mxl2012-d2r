// Move Only's start function (move_only.cpp, move_only_logic.h). Off word: moveonly.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Writes srvstfunc slot 71 of D2R's server start table: a function that refuses every cast of Move Only.
auto InstallMoveOnly(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Casts refused since load, and the last skill id refused.
void MoveOnlyStats(long* refused, long* lastSkill) noexcept;
