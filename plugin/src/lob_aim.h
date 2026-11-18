// Laughing Ghost and Rising Dawn land where the player clicked (lob_aim.cpp, bugs #614 / #618).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's server and client missile creates (0x5371a0, 0x1b7760): a lob missile of the two skills gets its target as a
// fixed world point (a monster target becomes its position at the cast), at any distance. Returns the hooks installed (2).
auto InstallLobAim(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Lob missiles of the two skills seen since load (both sides), and the targets set (server, client).
void LobAimCounts(long* seen, long* server, long* client) noexcept;
