// Guard for the client's "Could not get act!" exit on server command 0x15 (bugs #511 / #292; reassign_guard.cpp,
// reassign_guard_logic.h). Off word `reassign`.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Takes D2R's no-room branch of the client's command 0x15 handler (0x12ab40, branch 0x12addb): a unit other than the local player
// left without a client room is left so (logged) instead of the end of the game; everything else is D2R's handler unchanged.
auto InstallReassignGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;

// Commands seen, units left without a room, and the local player without a room (D2R's end) (`mxl2012`).
void ReassignGuardStats(unsigned* seen, unsigned* left, unsigned* ended) noexcept;
