// Leap Attack and Cherub Strike stun for Median's skill length (stun_len.cpp, bug #580).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Hooks D2R's server damage function 7 (0x453e30): after it, a missile of Leap Attack, Cherub Strike or Level 90 Cherub
// whose dParam1 is 0 gets the 1.13c stun length, Param1 + Param2 * (lvl - 1). Returns the hooks installed (1).
auto InstallStunLen(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Function 7 calls seen since load, and the lengths written.
void StunLenCounts(long* calls, long* written) noexcept;
