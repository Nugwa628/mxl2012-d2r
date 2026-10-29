// Guard of D2R's item-event skill resolver (item_effect.cpp, bug #40).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's resolver of the skill an item property fires on an event (0x589930): a skill without ItemEffect returns 0 (no cast)
// instead of asserting. The report gets one entry. Returns the number installed (1).
auto InstallItemEffectGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Calls the guard answered with 0 for a skill without ItemEffect since load.
auto ItemEffectSkips() noexcept -> long;
// The last such skill id (0 = none yet).
auto ItemEffectLastSkill() noexcept -> long;
