// Laughing Ghost explodes where the player clicked (lob_aim.cpp, bug #614, lane ghostaim).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's server and client missile creates (0x5371a0, 0x1b7760): a lob missile of Laughing Ghost whose target lies past
// its missile's Range gets the target moved back to that range (lob_aim_logic.h). The report gets one entry. Returns the
// number of hooks installed (2).
auto InstallLobAim(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Laughing Ghost lob missiles seen since load (both sides), and the targets moved (server, client).
void LobAimCounts(long* seen, long* server, long* client) noexcept;
