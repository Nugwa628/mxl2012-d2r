// Guard of D2R's blaze / spider-lay state list asserts (state_lists.cpp, bugs #50 #52, lane statefaith).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Patches the skill / level / missile range asserts of D2R's client and server functions of states 13 and 22 into the jumps
// D2R takes after them (state_lists_logic.h). The report gets one entry. Returns the number of blocks patched (12).
auto InstallStateListGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
