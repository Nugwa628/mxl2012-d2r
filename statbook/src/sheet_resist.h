// Magic and Physical Resistance on D2R's character sheet (sheet_resist.cpp; docs/hd-ui.md "Magic and Physical Resistance on the
// character sheet").
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Part sheetres: a UI-thread tick fills the sheet's Magic / Physical Resistance rows (the text boxes the mod's sheet layouts add,
// tools/sheet_resists.py) with the client player's values as the damage code applies them (sheet_resist_logic.h). The report gets
// one entry. False when a loader service is missing.
auto InstallSheetResist(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Ticks, texts sent, sheets found without the rows, faults, and the last values shown.
void SheetResistStatus(char* out, size_t outSize) noexcept;
