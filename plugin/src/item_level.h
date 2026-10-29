// Item levels 100-127 kept by D2R's item serializer (item_level.cpp, bug #251, lane ilvl).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Raises the serializer's item level clamp from 99 to 127, the save field's maximum (item_level_logic.h). The report gets one
// entry. Returns true when the patch went in; on any byte difference nothing is written.
auto InstallItemLevel(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
