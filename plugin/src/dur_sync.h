// A worn item's durability loss shown on the client (dur_sync.cpp, dur_sync_logic.h; bug #433). Off word: dursync.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Patches D2R's wear dispatcher so its durability update (packet 0x3e) gets a clean layer argument (0x441c4b, 5 bytes). The
// report gets one entry. Returns true when the patch went in; on any byte difference nothing is written.
auto InstallDurSync(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
