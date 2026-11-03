// The 1.13c conversion length of skill server do 51 (charm_length.cpp, charm_length_logic.h; bug #527). Off word: charmlen.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Routes 0x570780's calc2 call (0x57091b) to Param3: the charm lasts Param3 + rand(Param4) frames as in 1.13c.
auto InstallCharmLength(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Lengths answered since load, the last skill and its length in frames.
void CharmLengthStats(long* calls, long* lastSkill, long* lastLength) noexcept;
