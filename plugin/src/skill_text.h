// Skill tooltip labels in 1.13c's words (skill_text.cpp, bug #396).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's skill tooltip line renderer (0x287a50): after it draws a line, each raw printf label it appended (D2R's text of
// 1.13c's hard-coded StrSkill4-8 / 13 / 18 / 20 / 34 / 39) is cut back to 1.13c's words (skill_text_logic.h). The report gets
// one entry. Returns true when the hook went in; on any byte difference nothing is written.
auto InstallSkillText(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Labels cut since load.
auto SkillTextCuts() noexcept -> long;
