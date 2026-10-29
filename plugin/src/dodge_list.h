// Guard of D2R's dodge / avoid / evade state list assert (dodge_list.cpp, bug #53).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Patches the "hList" assert of D2R's damage code into the jump D2R takes after it (dodge_list_logic.h). The report gets one
// entry. Returns the number installed (1).
auto InstallDodgeListGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
