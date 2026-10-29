// Guard of D2R's skill remove for units that own no skill (skill_remove.cpp, bug #15).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's skill remove (0x3402d0): a unit without a skill list or without any skill returns at once instead of asserting
// `ptSkill` (Skills.cpp:904). The report gets one entry. Returns the number installed (1).
auto InstallSkillRemoveGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Removes the guard answered since load (the unit owned no skill).
auto SkillRemoveSkips() noexcept -> long;
// The skill id of the last one (0 = none yet).
auto SkillRemoveLastSkill() noexcept -> long;
