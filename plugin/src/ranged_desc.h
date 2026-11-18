// Ctrl stat range line for descfuncs D2R has no range case for (ranged_desc.cpp, bug #617).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's ranged mod string (0x2d7850): the descfuncs without a range case (Reanimate as) get D2R's plain line at min and
// max merged into "(min-max)"; other lines run D2R's code. The report gets one entry. Returns 1 when installed, else 0.
auto InstallRangedDesc(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;

// Lines the hook built (since launch) and the descfunc of the last one.
auto RangedDescLines() noexcept -> long;
auto RangedDescLastDescfunc() noexcept -> long;
