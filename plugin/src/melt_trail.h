// State-22 melt trail of Median XL 2012's raptured units (melt_trail.cpp, bug #52, lane melttrail).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's client and server functions of state 22 (0x221650, 0x578680): a state list that names no skill gets 1.14d's
// fixed trail (missile 143, the level of the unit's skill 173; melt_trail_logic.h), any other runs D2R's function. The report
// gets one entry. Returns the number of hooks installed (2).
auto InstallMeltTrail(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Trail missiles the hooks made since load (client, server).
void MeltTrailCounts(long* client, long* server) noexcept;
