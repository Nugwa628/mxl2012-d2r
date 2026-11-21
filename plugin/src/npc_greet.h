// A vendor's first-meeting greeting no longer closes a trade picked while it plays (npc_greet.cpp, lane bugs128).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's "NPC speech finished" callback 0x10da20 and the NPC menu opener 0x1141d0 (npc_greet_logic.h). The report gets
// one entry. Returns true when both hooks are in; on any byte difference nothing is written.
auto InstallNpcGreet(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Greetings that ended while a vendor panel was open (the panel kept) since load.
auto NpcGreetKept() noexcept -> long;
