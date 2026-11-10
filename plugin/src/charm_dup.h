// Carry1 duplicates (charm_dup.cpp, off word charmdup).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Lets more copies of one carry1 unique through D2R's carry test and keeps the stats of all but the active copy out (D2R's
// "requirements not met"). The report gets one entry. Returns the number of the four hooks installed (4 = on).
auto InstallCharmDup(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Since load: carry tests run without the unique half, requirement checks answered "not met" for an inactive copy, merged
// copies taken out by the refresh.
void CharmDupCounts(long* carryPassed, long* inactive, long* disabled) noexcept;
