// The classic HUD's level-up + buttons after a level-up in legacy graphics (lvlup_ui.cpp, bug #488, lane uiplus).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Wraps LevelUpButtonWidget's Draw slot: in legacy graphics a disabled button runs its own Update first, so stat / skill
// points lighten it as HD does (lvlup_ui_logic.h). The report gets one entry. Returns true when the slot was taken over; on
// any byte difference nothing is written.
auto InstallLevelUpUi(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Updates run by the wrapper since load (legacy, disabled button), Draws seen.
void LevelUpUiCounts(long* updates, long* draws) noexcept;
