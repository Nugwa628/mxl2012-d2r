// The cube's second `useitem` output: Median XL 2012's Oil of Duplication (cube_dupe.cpp, bug #350, lane cube2).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's recipe executor 0x5269c0: after it made a recipe whose output a and a later output are `useitem`, a copy of
// output a goes into the cube per further `useitem` output, as 1.13c made (cube_dupe_logic.h). The report gets one entry.
// Returns true when the hook went in.
auto InstallCubeDupe(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Copies made since load, copies that found no room (cube nor backpack) and were dropped, copies the duplicate refused.
void CubeDupeCounts(long* made, long* noRoom, long* failed) noexcept;
